"""Tests for ``engine/water/surface_moisture_wcm.py``.

Covers Water Cloud Model (WCM) forward backscatter, bounded bisection
inversion verified against the exact closed-form monotonic inverse, pixel/parcel
QA aggregation, Rev13 §3 depth/role/transfer/anti-circularity guards, G1 purity
and AST hygiene (zero hardcoded calibration constants, zero numpy, zero impure
imports), G4 typed ``Missing`` propagation, and G5 caller validation.

Every WCM parameter, backscatter, vegetation, and moisture value in this file
is synthetic PLACEHOLDER test data, plainly not real field calibration.
"""

from __future__ import annotations

import ast
import copy
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing
from engine.water import surface_moisture_wcm as wcm
from engine.water.surface_moisture_wcm import (
    DEPTH_BAND_SURFACE,
    ESTIMATOR_ROLE_SURFACE,
    PROPOSED_STATUS,
    UNIT_VOLUMETRIC_MOISTURE,
    ParcelWcmObservation,
    PixelWcmSample,
    SurfaceMoistureBenchmarkReport,
    SurfaceMoistureEstimate,
    WcmForwardResult,
    WcmParameters,
    aggregate_parcel_qa,
    db_to_linear,
    estimate_surface_moisture,
    linear_to_db,
    validate_surface_moisture_benchmark,
    wcm_closed_form_moisture,
    wcm_forward_backscatter,
    wcm_invert_moisture,
)

# Synthetic PLACEHOLDER calibration parameters (not real field coefficients).
PLACEHOLDER_PARAMS = WcmParameters(
    a_param=0.12,
    b_param=0.45,
    c_soil=-14.0,
    d_soil=22.0,
    theta_deg=38.0,
    mv_min=0.05,
    mv_max=0.48,
    max_s1_s2_gap_days=5.0,
    polarization="VV",
    vegetation_descriptor="NDVI",
    soil_model="db_linear",
    min_valid_pixel_count=4,
    min_valid_pixel_fraction=0.5,
    sigma0_min_db=-22.0,
    sigma0_max_db=-2.0,
    veg_min=0.0,
    veg_max=1.0,
    max_incidence_angle_delta_deg=5.0,
)

PLACEHOLDER_LINEAR_PARAMS = WcmParameters(
    a_param=0.08,
    b_param=0.35,
    c_soil=0.02,
    d_soil=0.45,
    theta_deg=40.0,
    mv_min=0.04,
    mv_max=0.45,
    max_s1_s2_gap_days=4.0,
    polarization="VH",
    vegetation_descriptor="LAI",
    soil_model="linear",
)


def _sample_observation(
    *,
    sigma0: float | Missing | InputMissing | None = -10.5,
    sigma0_unit: str = "dB",
    polarization: str = "VV",
    vegetation_value: float | Missing | InputMissing | None = 0.42,
    vegetation_descriptor: str = "NDVI",
    valid_pixel_count: int = 9,
    total_pixel_count: int = 10,
    effective_support_m: float | Missing | InputMissing | None = 30.0,
    orbit_direction: str | None = "ASCENDING",
    incidence_angle_deg: float | Missing | InputMissing | None = 38.0,
    s1_s2_delta_days: float | Missing | InputMissing | None = 2.0,
    qa_passed: bool = True,
    qa_detail: str | None = None,
) -> ParcelWcmObservation:
    return ParcelWcmObservation(
        sigma0=sigma0,
        sigma0_unit=sigma0_unit,  # type: ignore[arg-type]
        polarization=polarization,  # type: ignore[arg-type]
        vegetation_value=vegetation_value,
        vegetation_descriptor=vegetation_descriptor,  # type: ignore[arg-type]
        valid_pixel_count=valid_pixel_count,
        total_pixel_count=total_pixel_count,
        effective_support_m=effective_support_m,
        orbit_direction=orbit_direction,  # type: ignore[arg-type]
        incidence_angle_deg=incidence_angle_deg,
        s1_s2_delta_days=s1_s2_delta_days,
        qa_passed=qa_passed,
        qa_detail=qa_detail,
    )


# --- AST hygiene, purity, frozen dataclasses --------------------------------


def test_module_contains_no_calibration_constants_or_impure_imports() -> None:
    source_path = Path(wcm.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    # Only exact equation / geometry literals (0, 1, 2, 10, 90) are permitted.
    assert numeric_constants.issubset({0, 1, 2, 10, 90})

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    forbidden = {
        "numpy",
        "scipy",
        "os",
        "pathlib",
        "datetime",
        "time",
        "random",
        "urllib",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "json",
    }
    assert imported_modules.isdisjoint(forbidden)


def test_all_dataclasses_are_frozen() -> None:
    fwd = wcm_forward_backscatter(0.25, vegetation=0.35, params=PLACEHOLDER_PARAMS)
    obs = _sample_observation()
    est = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)
    px = PixelWcmSample(
        sigma0=-10.0,
        sigma0_unit="dB",
        polarization="VV",
        vegetation_value=0.3,
        vegetation_descriptor="NDVI",
        qa_valid=True,
        incidence_angle_deg=38.0,
        orbit_direction="ASCENDING",
        s1_s2_delta_days=1.0,
    )
    report = validate_surface_moisture_benchmark(
        calibration_reference="SMAP",
        validation_reference="LOCAL_PROBE_NET",
        claimed_level="INDEPENDENT_FIELD_VALIDATION",
    )

    with pytest.raises(FrozenInstanceError):
        PLACEHOLDER_PARAMS.a_param = 0.99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        fwd.sigma0_db = -1.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        obs.valid_pixel_count = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        est.observes_root_zone = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        px.qa_valid = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.local_transfer_validated = False  # type: ignore[misc]


def test_pure_deterministic_and_does_not_mutate_inputs() -> None:
    obs = _sample_observation()
    obs_before = copy.deepcopy(obs)
    params_before = copy.deepcopy(PLACEHOLDER_PARAMS)

    first = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)
    second = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)

    assert first == second
    assert obs == obs_before
    assert PLACEHOLDER_PARAMS == params_before


# --- WCM forward equations & bisection vs closed-form inversion -------------


def test_wcm_forward_matches_exact_analytical_equations() -> None:
    mv = 0.27
    veg = 0.55
    theta = 38.0
    cos_theta = math.cos(math.radians(theta))
    expected_tau2 = math.exp(-2.0 * PLACEHOLDER_PARAMS.b_param * veg / cos_theta)
    expected_veg = PLACEHOLDER_PARAMS.a_param * veg * cos_theta * (1.0 - expected_tau2)
    expected_soil = 10.0 ** (
        (PLACEHOLDER_PARAMS.c_soil + PLACEHOLDER_PARAMS.d_soil * mv) / 10.0
    )
    expected_total_lin = expected_veg + expected_tau2 * expected_soil
    expected_total_db = 10.0 * math.log10(expected_total_lin)

    res = wcm_forward_backscatter(mv, vegetation=veg, params=PLACEHOLDER_PARAMS)
    assert isinstance(res, WcmForwardResult)
    assert res.tau2 == pytest.approx(expected_tau2, rel=1e-12, abs=1e-12)
    assert res.sigma_veg_lin == pytest.approx(expected_veg, rel=1e-12, abs=1e-12)
    assert res.sigma_soil_lin == pytest.approx(expected_soil, rel=1e-12, abs=1e-12)
    assert res.sigma0_lin == pytest.approx(expected_total_lin, rel=1e-12, abs=1e-12)
    assert res.sigma0_db == pytest.approx(expected_total_db, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("veg", [0.0, 0.25, 0.60, 0.90])
@pytest.mark.parametrize("mv_true", [0.05, 0.12, 0.25, 0.37, 0.48])
def test_bisection_matches_closed_form_across_db_linear_domain(
    veg: float, mv_true: float
) -> None:
    fwd = wcm_forward_backscatter(mv_true, vegetation=veg, params=PLACEHOLDER_PARAMS)

    inv_db = wcm_invert_moisture(
        fwd.sigma0_db,
        sigma0_unit="dB",
        vegetation=veg,
        params=PLACEHOLDER_PARAMS,
    )
    inv_lin = wcm_invert_moisture(
        fwd.sigma0_lin,
        sigma0_unit="linear",
        vegetation=veg,
        params=PLACEHOLDER_PARAMS,
    )
    closed = wcm_closed_form_moisture(
        fwd.sigma0_db,
        sigma0_unit="dB",
        vegetation=veg,
        params=PLACEHOLDER_PARAMS,
    )

    assert isinstance(inv_db, float)
    assert isinstance(inv_lin, float)
    assert isinstance(closed, float)
    assert inv_db == pytest.approx(mv_true, abs=1e-11)
    assert inv_lin == pytest.approx(mv_true, abs=1e-11)
    assert inv_db == pytest.approx(closed, abs=1e-11)


@pytest.mark.parametrize("lai", [0.0, 1.2, 2.8])
@pytest.mark.parametrize("mv_true", [0.04, 0.18, 0.33, 0.45])
def test_bisection_matches_closed_form_across_linear_soil_model(
    lai: float, mv_true: float
) -> None:
    fwd = wcm_forward_backscatter(
        mv_true,
        vegetation=lai,
        params=PLACEHOLDER_LINEAR_PARAMS,
        incidence_angle_deg=41.5,
    )
    inv = wcm_invert_moisture(
        fwd.sigma0_lin,
        sigma0_unit="linear",
        vegetation=lai,
        params=PLACEHOLDER_LINEAR_PARAMS,
        incidence_angle_deg=41.5,
    )
    closed = wcm_closed_form_moisture(
        fwd.sigma0_lin,
        sigma0_unit="linear",
        vegetation=lai,
        params=PLACEHOLDER_LINEAR_PARAMS,
        incidence_angle_deg=41.5,
    )
    assert isinstance(inv, float)
    assert isinstance(closed, float)
    assert inv == pytest.approx(mv_true, abs=1e-11)
    assert inv == pytest.approx(closed, abs=1e-11)


def test_bisection_respects_caller_tolerance_and_max_iters() -> None:
    params_coarse = WcmParameters(
        a_param=0.12,
        b_param=0.45,
        c_soil=-14.0,
        d_soil=22.0,
        theta_deg=38.0,
        mv_min=0.05,
        mv_max=0.48,
        max_s1_s2_gap_days=5.0,
        bisection_tol=1e-4,
        max_bisection_iters=30,
    )
    mv_true = 0.21
    fwd = wcm_forward_backscatter(mv_true, vegetation=0.4, params=params_coarse)
    inv = wcm_invert_moisture(
        fwd.sigma0_db, sigma0_unit="dB", vegetation=0.4, params=params_coarse
    )
    assert isinstance(inv, float)
    assert abs(inv - mv_true) <= 1e-4


def test_db_linear_roundtrip_conversions() -> None:
    for db_val in (-25.0, -12.3, 0.0, 3.5):
        lin = db_to_linear(db_val)
        assert linear_to_db(lin) == pytest.approx(db_val, abs=1e-12)


# --- Pixel / parcel QA aggregation ------------------------------------------


def test_aggregate_parcel_qa_averages_in_linear_power_and_computes_support() -> None:
    samples = [
        PixelWcmSample(
            sigma0=-10.0,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.30,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=37.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=1.0,
        ),
        PixelWcmSample(
            sigma0=db_to_linear(-12.0),
            sigma0_unit="linear",
            polarization="VV",
            vegetation_value=0.50,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=39.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=-3.0,
        ),
        PixelWcmSample(
            sigma0=-2.0,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.99,
            vegetation_descriptor="NDVI",
            qa_valid=False,  # masked pixel excluded
            incidence_angle_deg=38.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=0.0,
        ),
        PixelWcmSample(
            sigma0=None,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.40,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=38.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=1.0,
        ),
    ]
    parcel = aggregate_parcel_qa(
        samples,
        pixel_spacing_m=10.0,
        polarization="VV",
        vegetation_descriptor="NDVI",
        output_unit="dB",
    )
    expected_lin = 0.5 * (db_to_linear(-10.0) + db_to_linear(-12.0))
    assert parcel.qa_passed is True
    assert parcel.valid_pixel_count == 2
    assert parcel.total_pixel_count == 4
    assert parcel.sigma0 == pytest.approx(linear_to_db(expected_lin), abs=1e-12)
    assert parcel.sigma0_unit == "dB"
    assert parcel.vegetation_value == pytest.approx(0.40, abs=1e-12)
    assert parcel.incidence_angle_deg == pytest.approx(38.0, abs=1e-12)
    assert parcel.s1_s2_delta_days == -3.0
    assert parcel.effective_support_m == pytest.approx(10.0 * math.sqrt(2.0), abs=1e-12)
    assert parcel.orbit_direction == "ASCENDING"


def test_aggregate_parcel_qa_rejects_mixed_orbits_and_mismatched_descriptors() -> None:
    mixed_orbit = [
        PixelWcmSample(
            sigma0=-10.0,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.3,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=38.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=1.0,
        ),
        PixelWcmSample(
            sigma0=-11.0,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.4,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=38.0,
            orbit_direction="DESCENDING",
            s1_s2_delta_days=1.0,
        ),
    ]
    parcel_mixed = aggregate_parcel_qa(
        mixed_orbit,
        pixel_spacing_m=10.0,
        polarization="VV",
        vegetation_descriptor="NDVI",
    )
    assert parcel_mixed.qa_passed is False
    assert parcel_mixed.orbit_direction is None

    est = estimate_surface_moisture(parcel_mixed, params=PLACEHOLDER_PARAMS)
    assert isinstance(est.soil_moisture_m3_m3, Missing)
    assert est.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    wrong_pol = [
        PixelWcmSample(
            sigma0=-10.0,
            sigma0_unit="dB",
            polarization="VH",
            vegetation_value=0.3,
            vegetation_descriptor="NDVI",
            qa_valid=True,
            incidence_angle_deg=38.0,
            orbit_direction="ASCENDING",
            s1_s2_delta_days=1.0,
        )
    ]
    parcel_wrong_pol = aggregate_parcel_qa(
        wrong_pol,
        pixel_spacing_m=10.0,
        polarization="VV",
        vegetation_descriptor="NDVI",
    )
    assert parcel_wrong_pol.qa_passed is False


# --- Rev13 §3 Guard 1: surface depth, role, provenance, metadata -------------


def test_rev13_guard1_depth_role_provenance_and_defaults() -> None:
    fwd = wcm_forward_backscatter(0.24, vegetation=0.35, params=PLACEHOLDER_PARAMS)
    obs = _sample_observation(
        sigma0=fwd.sigma0_db,
        sigma0_unit="dB",
        vegetation_value=0.35,
        incidence_angle_deg=38.0,
    )
    est = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)

    assert est.status == PROPOSED_STATUS
    assert est.unit == UNIT_VOLUMETRIC_MOISTURE == "m3 m-3"
    assert est.depth == DEPTH_BAND_SURFACE == "0_to_5_cm"
    assert est.observes_root_zone is False
    assert est.estimator_role == ESTIMATOR_ROLE_SURFACE == "SURFACE_INPUT_ESTIMATOR"
    assert est.local_transfer_validated is False
    assert est.provenance == "DERIVED"
    assert isinstance(est.soil_moisture_m3_m3, float)
    assert est.soil_moisture_m3_m3 == pytest.approx(0.24, abs=1e-11)
    assert est.tau2 == pytest.approx(fwd.tau2, rel=1e-12)
    assert est.sigma_veg_lin == pytest.approx(fwd.sigma_veg_lin, rel=1e-12)
    assert est.sigma0_obs_db == pytest.approx(fwd.sigma0_db, rel=1e-12)


def test_rev13_guard1_rejects_root_zone_or_wrong_depth_or_role() -> None:
    with pytest.raises(ValueError, match="depth"):
        SurfaceMoistureEstimate(
            soil_moisture_m3_m3=0.2,
            provenance="DERIVED",
            depth="0_to_100_cm",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="observes_root_zone"):
        SurfaceMoistureEstimate(
            soil_moisture_m3_m3=0.2,
            provenance="DERIVED",
            observes_root_zone=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="estimator_role"):
        SurfaceMoistureEstimate(
            soil_moisture_m3_m3=0.2,
            provenance="DERIVED",
            estimator_role="ROOT_ZONE_MODEL",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="provenance"):
        SurfaceMoistureEstimate(
            soil_moisture_m3_m3=Missing(reason="NO_COVERAGE", detail="empty"),
            provenance="DERIVED",
        )
    with pytest.raises(ValueError, match="provenance"):
        SurfaceMoistureEstimate(soil_moisture_m3_m3=0.2, provenance=None)


# --- Rev13 §3 Guard 2: typed Missing rejections -----------------------------


def test_rejects_no_coverage_for_zero_total_or_zero_valid_pixels() -> None:
    empty = aggregate_parcel_qa(
        [],
        pixel_spacing_m=10.0,
        polarization="VV",
        vegetation_descriptor="NDVI",
    )
    est_empty = estimate_surface_moisture(empty, params=PLACEHOLDER_PARAMS)
    assert isinstance(est_empty.soil_moisture_m3_m3, Missing)
    assert est_empty.soil_moisture_m3_m3.reason == "NO_COVERAGE"
    assert est_empty.provenance is None

    all_masked = _sample_observation(
        valid_pixel_count=0,
        total_pixel_count=12,
        sigma0=None,
        vegetation_value=None,
        effective_support_m=None,
    )
    est_masked = estimate_surface_moisture(all_masked, params=PLACEHOLDER_PARAMS)
    assert isinstance(est_masked.soil_moisture_m3_m3, Missing)
    assert est_masked.soil_moisture_m3_m3.reason == "NO_COVERAGE"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sigma0": None},
        {"sigma0": InputMissing(reason="SOURCE_UNAVAILABLE", detail="S1 down")},
        {"vegetation_value": None},
        {"vegetation_value": Missing(reason="MISSING_INPUT", detail="S2 cloudy")},
        {"s1_s2_delta_days": None},
        {"incidence_angle_deg": None},
        {"effective_support_m": None},
        {"orbit_direction": None},
    ],
)
def test_rejects_missing_inputs_with_typed_missing(kwargs: dict[str, object]) -> None:
    obs = _sample_observation(**kwargs)  # type: ignore[arg-type]
    est = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)
    assert isinstance(est.soil_moisture_m3_m3, Missing)
    assert est.soil_moisture_m3_m3.reason in {"MISSING_INPUT", "SOURCE_UNAVAILABLE"}
    assert est.provenance is None


def test_rejects_non_finite_inputs_with_not_computable() -> None:
    for bad_val in (math.nan, math.inf, -math.inf):
        obs = _sample_observation(sigma0=bad_val)
        est = estimate_surface_moisture(obs, params=PLACEHOLDER_PARAMS)
        assert isinstance(est.soil_moisture_m3_m3, Missing)
        assert est.soil_moisture_m3_m3.reason == "NOT_COMPUTABLE"


def test_rejects_invalid_qa_excessive_gap_insufficient_pixels_and_out_of_range_sigma0() -> (
    None
):
    # 1. Invalid QA flag
    est_qa = estimate_surface_moisture(
        _sample_observation(qa_passed=False, qa_detail="RFI anomaly detected"),
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(est_qa.soil_moisture_m3_m3, Missing)
    assert est_qa.soil_moisture_m3_m3.reason == "CONTROL_FAILED"
    assert "RFI" in (est_qa.soil_moisture_m3_m3.detail or "")

    # 2. Excessive s1_s2_delta_days (positive and negative)
    for bad_gap in (5.5, -6.0):
        est_gap = estimate_surface_moisture(
            _sample_observation(s1_s2_delta_days=bad_gap),
            params=PLACEHOLDER_PARAMS,
        )
        assert isinstance(est_gap.soil_moisture_m3_m3, Missing)
        assert est_gap.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    # 3. Insufficient valid pixel count
    est_cnt = estimate_surface_moisture(
        _sample_observation(valid_pixel_count=3, total_pixel_count=4),
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(est_cnt.soil_moisture_m3_m3, Missing)
    assert est_cnt.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    # 4. Insufficient valid pixel fraction
    est_frac = estimate_surface_moisture(
        _sample_observation(valid_pixel_count=4, total_pixel_count=10),
        params=PLACEHOLDER_PARAMS,
    )
    assert isinstance(est_frac.soil_moisture_m3_m3, Missing)
    assert est_frac.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    # 5. Out-of-range backscatter (below sigma0_min_db, above sigma0_max_db, non-positive linear)
    for bad_s0, unit in [
        (-25.0, "dB"),
        (-1.0, "dB"),
        (0.0, "linear"),
        (-0.1, "linear"),
    ]:
        est_s0 = estimate_surface_moisture(
            _sample_observation(sigma0=bad_s0, sigma0_unit=unit),
            params=PLACEHOLDER_PARAMS,
        )
        assert isinstance(est_s0.soil_moisture_m3_m3, Missing)
        assert est_s0.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    # 6. Backscatter inside QA dB box but outside WCM [mv_min, mv_max] bracket
    below_min = (
        wcm_forward_backscatter(
            PLACEHOLDER_PARAMS.mv_min, vegetation=0.4, params=PLACEHOLDER_PARAMS
        ).sigma0_db
        - 0.5
    )
    above_max = (
        wcm_forward_backscatter(
            PLACEHOLDER_PARAMS.mv_max, vegetation=0.4, params=PLACEHOLDER_PARAMS
        ).sigma0_db
        + 0.5
    )
    for bracket_s0 in (below_min, above_max):
        est_br = estimate_surface_moisture(
            _sample_observation(sigma0=bracket_s0, vegetation_value=0.4),
            params=PLACEHOLDER_PARAMS,
        )
        assert isinstance(est_br.soil_moisture_m3_m3, Missing)
        assert est_br.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    # 7. Incidence angle mismatch & out-of-range vegetation
    est_ang = estimate_surface_moisture(
        _sample_observation(incidence_angle_deg=45.0), params=PLACEHOLDER_PARAMS
    )
    assert isinstance(est_ang.soil_moisture_m3_m3, Missing)
    assert est_ang.soil_moisture_m3_m3.reason == "CONTROL_FAILED"

    est_veg = estimate_surface_moisture(
        _sample_observation(vegetation_value=-0.05), params=PLACEHOLDER_PARAMS
    )
    assert isinstance(est_veg.soil_moisture_m3_m3, Missing)
    assert est_veg.soil_moisture_m3_m3.reason == "CONTROL_FAILED"


# --- Rev13 §3 Guard 3: benchmark circularity guard --------------------------


def test_validate_benchmark_refuses_smap_vs_smap_independent_claim() -> None:
    with pytest.raises(ValueError, match="SMAP"):
        validate_surface_moisture_benchmark(
            calibration_reference="SMAP",
            validation_reference="SMAP",
            claimed_level="INDEPENDENT_FIELD_VALIDATION",
        )
    with pytest.raises(ValueError, match="SMAP"):
        validate_surface_moisture_benchmark(
            calibration_reference=" smap ",
            validation_reference="SMAP",
            claimed_level="INDEPENDENT_FIELD_VALIDATION",
        )
    with pytest.raises(ValueError, match="identical"):
        validate_surface_moisture_benchmark(
            calibration_reference="FIELD_SITE_A",
            validation_reference="FIELD_SITE_A",
            claimed_level="INDEPENDENT_FIELD_VALIDATION",
        )
    with pytest.raises(ValueError, match="depth"):
        validate_surface_moisture_benchmark(
            calibration_reference="SMAP",
            validation_reference="IN_SITU_NETWORK",
            claimed_level="INDEPENDENT_FIELD_VALIDATION",
            depth="0_to_100_cm",
        )


def test_validate_benchmark_allows_non_circular_and_intercomparison() -> None:
    intercomp = validate_surface_moisture_benchmark(
        calibration_reference="SMAP",
        validation_reference="SMAP",
        claimed_level="SATELLITE_INTERCOMPARISON",
    )
    assert isinstance(intercomp, SurfaceMoistureBenchmarkReport)
    assert intercomp.local_transfer_validated is False
    assert intercomp.depth == "0_to_5_cm"
    assert intercomp.observes_root_zone is False
    assert intercomp.estimator_role == "SURFACE_INPUT_ESTIMATOR"

    indep = validate_surface_moisture_benchmark(
        calibration_reference="SMAP",
        validation_reference="IN_SITU_TDR_0_5CM",
        claimed_level="INDEPENDENT_FIELD_VALIDATION",
        in_situ_probe_count=12,
    )
    assert indep.local_transfer_validated is True
    assert indep.in_situ_probe_count == 12


# --- G5: caller type and domain validation ----------------------------------


@pytest.mark.parametrize("bad_bool", [True, False])
def test_g5_rejects_booleans_and_bad_types(bad_bool: bool) -> None:
    with pytest.raises(TypeError):
        WcmParameters(
            a_param=bad_bool,  # type: ignore[arg-type]
            b_param=0.4,
            c_soil=-14.0,
            d_soil=20.0,
            theta_deg=38.0,
            mv_min=0.05,
            mv_max=0.45,
            max_s1_s2_gap_days=5.0,
        )
    with pytest.raises(TypeError):
        estimate_surface_moisture("not-an-obs", params=PLACEHOLDER_PARAMS)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        estimate_surface_moisture(_sample_observation(), params="not-params")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        estimate_surface_moisture(
            _sample_observation(),
            params=PLACEHOLDER_PARAMS,
            local_transfer_validated="yes",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        ParcelWcmObservation(
            sigma0=-10.0,
            sigma0_unit="dB",
            polarization="VV",
            vegetation_value=0.3,
            vegetation_descriptor="NDVI",
            valid_pixel_count=bad_bool,  # type: ignore[arg-type]
            total_pixel_count=5,
            effective_support_m=20.0,
            orbit_direction="ASCENDING",
            incidence_angle_deg=38.0,
            s1_s2_delta_days=1.0,
        )


def test_wcm_parameters_rejects_invalid_domains() -> None:
    with pytest.raises(ValueError, match="d_soil"):
        WcmParameters(
            a_param=0.1,
            b_param=0.4,
            c_soil=-14.0,
            d_soil=0.0,
            theta_deg=38.0,
            mv_min=0.05,
            mv_max=0.45,
            max_s1_s2_gap_days=5.0,
        )
    with pytest.raises(ValueError, match="theta_deg"):
        WcmParameters(
            a_param=0.1,
            b_param=0.4,
            c_soil=-14.0,
            d_soil=20.0,
            theta_deg=90.0,
            mv_min=0.05,
            mv_max=0.45,
            max_s1_s2_gap_days=5.0,
        )
    with pytest.raises(ValueError, match="mv bounds"):
        WcmParameters(
            a_param=0.1,
            b_param=0.4,
            c_soil=-14.0,
            d_soil=20.0,
            theta_deg=38.0,
            mv_min=0.45,
            mv_max=0.45,
            max_s1_s2_gap_days=5.0,
        )
