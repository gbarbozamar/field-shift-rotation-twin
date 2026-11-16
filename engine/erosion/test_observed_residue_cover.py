"""Tests for ``engine/erosion/observed_residue_cover.py`` (Frontier Unit F-04).

All numeric constants in this file are PLACEHOLDER values for structural,
mathematical, and contract verification only — never calibrated science values.
"""

from __future__ import annotations

import ast
import datetime as dt
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from contracts.results.models import Range
from engine.erosion import observed_residue_cover as module
from engine.erosion.c_factor.subfactors import surface_cover_subfactor_percent
from engine.erosion.observed_residue_cover import (
    OBSERVATION_CLASS,
    STATUS,
    ObservedResidueCoverEstimate,
    ResidueCoverSubfactorComparison,
    SatelliteSceneObservation,
    TransectCalibrationModel,
    compare_residue_cover_subfactors,
    evaluate_observed_residue_cover,
    ndti_to_residue_cover,
)

MODULE_PATH = Path(module.__file__)
TEST_PATH = Path(__file__)

FLOAT_TOL = 1e-12

# PLACEHOLDER constants (never real science values)
PLACEHOLDER_B = 0.0444
PLACEHOLDER_MIN_VALID_FRACTION = 0.70
PLACEHOLDER_TABULAR_COVER = 0.35
PLACEHOLDER_DATE_1 = dt.date(2026, 5, 10)
PLACEHOLDER_DATE_2 = dt.date(2026, 6, 15)
PLACEHOLDER_DATE_3 = dt.date(2026, 7, 20)


def _calibrated_fraction_model(
    *,
    slope: float = 2.5,
    intercept: float = 0.1,
    standard_error: float = 0.05,
    ndti_range: tuple[float, float] | None = (-0.04, 0.36),
) -> TransectCalibrationModel:
    return TransectCalibrationModel(
        calibrated_locally=True,
        slope=slope,
        intercept=intercept,
        standard_error=standard_error,
        ndti_range=ndti_range,
        output_unit="fraction",
        calibration_id="PLACEHOLDER_transect_01",
    )


def _emit_scene(
    *,
    date: dt.date = PLACEHOLDER_DATE_1,
    valid_pixel_fraction: float | InputMissing | ResultMissing = 0.90,
    npv_fraction: float | InputMissing | ResultMissing | None = 0.55,
    cloud_masked: bool = False,
    uncertainty: float | None = None,
) -> SatelliteSceneObservation:
    return SatelliteSceneObservation(
        sensor="EMIT",
        observation_date=date,
        valid_pixel_fraction=valid_pixel_fraction,
        npv_fraction=npv_fraction,
        cloud_masked=cloud_masked,
        uncertainty=uncertainty,
        source="PLACEHOLDER_EMIT_L2B",
    )


def _hls_scene(
    *,
    date: dt.date = PLACEHOLDER_DATE_1,
    valid_pixel_fraction: float | InputMissing | ResultMissing = 0.85,
    ndti: float | InputMissing | ResultMissing | None = 0.16,
    cloud_masked: bool = False,
) -> SatelliteSceneObservation:
    return SatelliteSceneObservation(
        sensor="HLS",
        observation_date=date,
        valid_pixel_fraction=valid_pixel_fraction,
        ndti=ndti,
        cloud_masked=cloud_masked,
        source="PLACEHOLDER_HLS_L30",
    )


# --- G1 purity, static hygiene, and dataclass invariants --------------------


def test_g1_purity_ast_no_io_network_clock_env() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_modules = {
        "os",
        "pathlib",
        "socket",
        "urllib",
        "http",
        "httpx",
        "requests",
        "subprocess",
        "time",
        "random",
        "io",
    }
    imported: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert imported.isdisjoint(forbidden_modules)
    assert "open" not in called_names
    assert "print" not in called_names
    assert "today" not in called_names
    assert "now" not in called_names


def test_no_windows_drive_paths_in_module() -> None:
    drive_sep = ":" + chr(92)
    for path in (MODULE_PATH, TEST_PATH):
        text = path.read_text(encoding="utf-8")
        assert drive_sep not in text


def test_status_and_frozen_invariants() -> None:
    assert STATUS == "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
    assert OBSERVATION_CLASS == "HYPOTHESIS"

    model = _calibrated_fraction_model()
    with pytest.raises(FrozenInstanceError):
        model.calibrated_locally = False  # type: ignore[misc]

    est = evaluate_observed_residue_cover(
        observations=[_emit_scene()],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert est.never_overwrites_normative_c is True
    assert est.observation_class == "HYPOTHESIS"
    assert est.status == STATUS
    with pytest.raises(FrozenInstanceError):
        est.never_overwrites_normative_c = False  # type: ignore[misc]

    with pytest.raises(ValueError, match="never_overwrites_normative_c"):
        ObservedResidueCoverEstimate(
            cover_fraction=0.5,
            subfactor=0.5,
            sensor="EMIT",
            cover_range=None,
            cover_range_missing=None,
            subfactor_range=None,
            subfactor_range_missing=None,
            scene_count=1,
            valid_scene_count=1,
            rejected_scene_count=0,
            rejection_reasons=(),
            aggregation="mean",
            never_overwrites_normative_c=False,
        )

    with pytest.raises(ValueError, match="never_overwrites_normative_c"):
        ResidueCoverSubfactorComparison(
            tabular_cover_fraction=0.5,
            tabular_subfactor=0.5,
            observed_cover_fraction=0.5,
            observed_hypothesis_subfactor=0.5,
            subfactor_difference=0.0,
            cover_difference=0.0,
            observed_sensor="EMIT",
            observed_cover_range=None,
            observed_cover_range_missing=None,
            observed_subfactor_range=None,
            observed_subfactor_range_missing=None,
            scene_count=1,
            valid_scene_count=1,
            rejected_scene_count=0,
            rejection_reasons=(),
            never_overwrites_normative_c=False,
        )

    with pytest.raises(ValueError, match="observation_class"):
        ResidueCoverSubfactorComparison(
            tabular_cover_fraction=0.5,
            tabular_subfactor=0.5,
            observed_cover_fraction=0.5,
            observed_hypothesis_subfactor=0.5,
            subfactor_difference=0.0,
            cover_difference=0.0,
            observed_sensor="EMIT",
            observed_cover_range=None,
            observed_cover_range_missing=None,
            observed_subfactor_range=None,
            observed_subfactor_range_missing=None,
            scene_count=1,
            valid_scene_count=1,
            rejected_scene_count=0,
            rejection_reasons=(),
            observation_class="NORMATIVE",  # type: ignore[arg-type]
        )


def test_determinism_and_input_immutability() -> None:
    scenes = [
        _emit_scene(
            date=PLACEHOLDER_DATE_1, npv_fraction=0.40, valid_pixel_fraction=0.8
        ),
        _emit_scene(
            date=PLACEHOLDER_DATE_2, npv_fraction=0.60, valid_pixel_fraction=0.9
        ),
    ]
    snapshot = list(scenes)
    res_a = compare_residue_cover_subfactors(
        tabular_residue_cover=PLACEHOLDER_TABULAR_COVER,
        observations=scenes,
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    res_b = compare_residue_cover_subfactors(
        tabular_residue_cover=PLACEHOLDER_TABULAR_COVER,
        observations=scenes,
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert res_a == res_b
    assert scenes == snapshot


# --- Rule 1: Raw NDTI requires local TransectCalibrationModel ---------------


@pytest.mark.parametrize(
    "calibration",
    [
        None,
        TransectCalibrationModel(
            calibrated_locally=False,
            slope=2.5,
            intercept=0.1,
            standard_error=0.05,
        ),
        InputMissing(reason="NOT_AVAILABLE", detail="no transect survey"),
        ResultMissing(reason="MISSING_INPUT", detail="calibration absent"),
    ],
)
def test_ndti_without_local_calibration_returns_not_computable(calibration) -> None:
    result = ndti_to_residue_cover(ndti=0.16, calibration=calibration)
    assert isinstance(result, ResultMissing)
    assert result.reason == "NOT_COMPUTABLE"
    assert result.detail is not None
    assert "uncalibrated NDTI" in result.detail


def test_hls_uncalibrated_preserves_tabular_fallback_in_comparison() -> None:
    uncalibrated = TransectCalibrationModel(
        calibrated_locally=False,
        slope=2.5,
        intercept=0.1,
        standard_error=0.05,
    )
    comparison = compare_residue_cover_subfactors(
        tabular_residue_cover=PLACEHOLDER_TABULAR_COVER,
        observations=[_hls_scene(ndti=0.16)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        calibration=uncalibrated,
    )

    expected_tabular = surface_cover_subfactor_percent(
        surface_residue_cover=PLACEHOLDER_TABULAR_COVER,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert comparison.never_overwrites_normative_c is True
    assert comparison.tabular_cover_fraction == PLACEHOLDER_TABULAR_COVER
    assert comparison.tabular_subfactor == pytest.approx(
        expected_tabular, abs=FLOAT_TOL
    )
    assert isinstance(comparison.observed_cover_fraction, ResultMissing)
    assert comparison.observed_cover_fraction.reason == "NOT_COMPUTABLE"
    assert "uncalibrated NDTI" in (comparison.observed_cover_fraction.detail or "")
    assert isinstance(comparison.observed_hypothesis_subfactor, ResultMissing)
    assert comparison.observed_hypothesis_subfactor.reason == "NOT_COMPUTABLE"
    assert "uncalibrated NDTI" in (
        comparison.observed_hypothesis_subfactor.detail or ""
    )
    assert isinstance(comparison.subfactor_difference, ResultMissing)
    assert comparison.subfactor_difference.reason == "MISSING_INPUT"


def test_ndti_calibration_domain_bounds_and_no_clipping() -> None:
    model = _calibrated_fraction_model(
        slope=2.5, intercept=0.1, standard_error=0.04, ndti_range=(0.0, 0.30)
    )
    outside_range = ndti_to_residue_cover(ndti=0.35, calibration=model)
    assert isinstance(outside_range, ResultMissing)
    assert outside_range.reason == "NOT_COMPUTABLE"
    assert "ndti_range" in (outside_range.detail or "")

    # Prediction outside [0, 1] is refused, never clipped
    wide_range_model = _calibrated_fraction_model(
        slope=2.5, intercept=0.5, standard_error=0.04, ndti_range=(-0.5, 0.5)
    )
    above_one = ndti_to_residue_cover(ndti=0.3, calibration=wide_range_model)
    assert isinstance(above_one, ResultMissing)
    assert above_one.reason == "NOT_COMPUTABLE"

    below_zero = ndti_to_residue_cover(ndti=-0.3, calibration=wide_range_model)
    assert isinstance(below_zero, ResultMissing)
    assert below_zero.reason == "NOT_COMPUTABLE"


def test_ndti_calibration_missing_or_invalid_fields() -> None:
    missing_slope = TransectCalibrationModel(
        calibrated_locally=True,
        slope=InputMissing(reason="MISSING_INPUT", detail="slope missing"),
        intercept=0.1,
        standard_error=0.02,
    )
    res = ndti_to_residue_cover(ndti=0.1, calibration=missing_slope)
    assert isinstance(res, ResultMissing)
    assert res.reason == "MISSING_INPUT"

    neg_se = TransectCalibrationModel(
        calibrated_locally=True,
        slope=2.0,
        intercept=0.1,
        standard_error=-0.01,
    )
    res_neg = ndti_to_residue_cover(ndti=0.1, calibration=neg_se)
    assert isinstance(res_neg, ResultMissing)
    assert res_neg.reason == "NOT_COMPUTABLE"

    bad_range = TransectCalibrationModel(
        calibrated_locally=True,
        slope=2.0,
        intercept=0.1,
        standard_error=0.01,
        ndti_range=(0.5, 0.1),
    )
    res_bad_range = ndti_to_residue_cover(ndti=0.2, calibration=bad_range)
    assert isinstance(res_bad_range, ResultMissing)
    assert res_bad_range.reason == "NOT_COMPUTABLE"


# --- Rule 2: Masked / cloudy / sparse / empty scenes never return 0.0 --------


def test_empty_scenes_returns_no_coverage_never_zero() -> None:
    est = evaluate_observed_residue_cover(
        observations=[],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(est.cover_fraction, ResultMissing)
    assert est.cover_fraction.reason == "NO_COVERAGE"
    assert isinstance(est.subfactor, ResultMissing)
    assert est.subfactor.reason == "NO_COVERAGE"
    assert est.scene_count == 0
    assert est.valid_scene_count == 0


def test_missing_observations_object_returns_missing_input() -> None:
    est = evaluate_observed_residue_cover(
        observations=InputMissing(
            reason="SOURCE_UNAVAILABLE", detail="satellite archive offline"
        ),
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(est.cover_fraction, ResultMissing)
    assert est.cover_fraction.reason == "MISSING_INPUT"
    assert "SOURCE_UNAVAILABLE" in (est.cover_fraction.detail or "")
    assert isinstance(est.subfactor, ResultMissing)
    assert est.subfactor.reason == "MISSING_INPUT"


def test_cloudy_and_sparse_scenes_return_no_coverage_never_zero() -> None:
    cloudy = _emit_scene(valid_pixel_fraction=1.0, npv_fraction=0.5, cloud_masked=True)
    sparse_zero = _emit_scene(valid_pixel_fraction=0.0, npv_fraction=0.5)
    sparse_below = _emit_scene(valid_pixel_fraction=0.699, npv_fraction=0.5)

    for scene in (cloudy, sparse_zero, sparse_below):
        est = evaluate_observed_residue_cover(
            observations=[scene],
            min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
            surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        )
        assert isinstance(est.cover_fraction, ResultMissing)
        assert est.cover_fraction.reason == "NO_COVERAGE"
        assert isinstance(est.subfactor, ResultMissing)
        assert est.subfactor.reason == "NO_COVERAGE"
        assert est.valid_scene_count == 0
        assert est.rejected_scene_count == 1


def test_mixed_cloudy_and_clear_scenes_filters_and_preserves_counts() -> None:
    scenes = [
        _emit_scene(
            date=PLACEHOLDER_DATE_1, valid_pixel_fraction=0.30, npv_fraction=0.10
        ),
        _emit_scene(
            date=PLACEHOLDER_DATE_2,
            valid_pixel_fraction=0.95,
            npv_fraction=0.60,
            cloud_masked=True,
        ),
        _emit_scene(
            date=PLACEHOLDER_DATE_3, valid_pixel_fraction=0.80, npv_fraction=0.50
        ),
    ]
    est = evaluate_observed_residue_cover(
        observations=scenes,
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert est.scene_count == 3
    assert est.valid_scene_count == 1
    assert est.rejected_scene_count == 2
    assert len(est.rejection_reasons) == 2
    assert est.cover_fraction == pytest.approx(0.50, abs=FLOAT_TOL)
    expected_sc = math.exp(-PLACEHOLDER_B * 50.0)
    assert est.subfactor == pytest.approx(expected_sc, abs=FLOAT_TOL)


def test_missing_scene_measurement_returns_missing_input() -> None:
    est_emit = evaluate_observed_residue_cover(
        observations=[_emit_scene(npv_fraction=None)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(est_emit.cover_fraction, ResultMissing)
    assert est_emit.cover_fraction.reason == "MISSING_INPUT"

    est_hls = evaluate_observed_residue_cover(
        observations=[
            _hls_scene(ndti=InputMissing(reason="NO_COVERAGE", detail="fill"))
        ],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        calibration=_calibrated_fraction_model(),
    )
    assert isinstance(est_hls.cover_fraction, ResultMissing)
    assert est_hls.cover_fraction.reason == "MISSING_INPUT"

    est_vpx = evaluate_observed_residue_cover(
        observations=[
            _emit_scene(
                valid_pixel_fraction=InputMissing(
                    reason="MISSING_INPUT", detail="qa band absent"
                )
            )
        ],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(est_vpx.cover_fraction, ResultMissing)
    assert est_vpx.cover_fraction.reason == "MISSING_INPUT"


# --- Quantitative EMIT & calibrated HLS evaluation and comparison -----------


def test_emit_npv_and_comparison_exact_values() -> None:
    npv = 0.65
    tab = 0.30
    comp = compare_residue_cover_subfactors(
        tabular_residue_cover=tab,
        observations=[_emit_scene(npv_fraction=npv, uncertainty=0.05)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    expected_tab_sc = math.exp(-PLACEHOLDER_B * (tab * 100.0))
    expected_obs_sc = math.exp(-PLACEHOLDER_B * (npv * 100.0))

    assert comp.never_overwrites_normative_c is True
    assert comp.observation_class == "HYPOTHESIS"
    assert comp.observed_sensor == "EMIT"
    assert comp.tabular_cover_fraction == pytest.approx(tab, abs=FLOAT_TOL)
    assert comp.tabular_subfactor == pytest.approx(expected_tab_sc, abs=FLOAT_TOL)
    assert comp.observed_cover_fraction == pytest.approx(npv, abs=FLOAT_TOL)
    assert comp.observed_hypothesis_subfactor == pytest.approx(
        expected_obs_sc, abs=FLOAT_TOL
    )
    assert comp.cover_difference == pytest.approx(npv - tab, abs=FLOAT_TOL)
    assert comp.subfactor_difference == pytest.approx(
        expected_obs_sc - expected_tab_sc, abs=FLOAT_TOL
    )
    assert isinstance(comp.observed_cover_range, Range)
    assert comp.observed_cover_range.low == pytest.approx(0.60, abs=FLOAT_TOL)
    assert comp.observed_cover_range.high == pytest.approx(0.70, abs=FLOAT_TOL)
    assert comp.observed_cover_range.kind == "emit_npv_uncertainty"
    assert comp.observed_subfactor_range is not None
    assert (
        comp.observed_subfactor_range.low
        < comp.observed_hypothesis_subfactor
        < comp.observed_subfactor_range.high
    )


def test_calibrated_hls_percent_unit_and_range_propagation() -> None:
    # cover_percent = 10.0 + 250.0 * 0.16 = 50.0 % -> cover_fraction = 0.50
    model = TransectCalibrationModel(
        calibrated_locally=True,
        slope=250.0,
        intercept=10.0,
        standard_error=5.0,
        ndti_range=(-0.04, 0.36),
        output_unit="percent",
    )
    est = evaluate_observed_residue_cover(
        observations=[_hls_scene(ndti=0.16)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        calibration=model,
    )
    assert est.sensor == "HLS"
    assert est.cover_fraction == pytest.approx(0.50, abs=FLOAT_TOL)
    assert est.subfactor == pytest.approx(
        math.exp(-PLACEHOLDER_B * 50.0), abs=FLOAT_TOL
    )
    assert est.cover_range is not None
    assert est.cover_range.low == pytest.approx(0.45, abs=FLOAT_TOL)
    assert est.cover_range.high == pytest.approx(0.55, abs=FLOAT_TOL)
    assert est.cover_range.kind == "transect_calibration_standard_error"
    assert est.subfactor_range is not None
    assert est.subfactor_range.low == pytest.approx(
        math.exp(-PLACEHOLDER_B * 55.0), abs=FLOAT_TOL
    )
    assert est.subfactor_range.high == pytest.approx(
        math.exp(-PLACEHOLDER_B * 45.0), abs=FLOAT_TOL
    )


def test_zero_b_collapses_subfactor_range_safely() -> None:
    model = _calibrated_fraction_model(standard_error=0.05)
    est = evaluate_observed_residue_cover(
        observations=[_hls_scene(ndti=0.16)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=0.0,
        calibration=model,
    )
    assert est.cover_fraction == pytest.approx(0.50, abs=FLOAT_TOL)
    assert est.subfactor == pytest.approx(1.0, abs=FLOAT_TOL)
    assert est.cover_range is not None
    assert est.subfactor_range is None
    assert isinstance(est.subfactor_range_missing, ResultMissing)
    assert est.subfactor_range_missing.reason == "NOT_APPLICABLE"


def test_aggregation_modes_and_order_invariance() -> None:
    s1 = _emit_scene(
        date=PLACEHOLDER_DATE_1, valid_pixel_fraction=0.70, npv_fraction=0.30
    )
    s2 = _emit_scene(
        date=PLACEHOLDER_DATE_3, valid_pixel_fraction=0.90, npv_fraction=0.70
    )
    s3 = _emit_scene(
        date=PLACEHOLDER_DATE_2, valid_pixel_fraction=0.80, npv_fraction=0.50
    )

    mean_123 = evaluate_observed_residue_cover(
        observations=[s1, s2, s3],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        aggregation="mean",
    )
    mean_321 = evaluate_observed_residue_cover(
        observations=[s3, s2, s1],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        aggregation="mean",
    )
    assert mean_123.cover_fraction == pytest.approx(0.50, abs=FLOAT_TOL)
    assert mean_123.cover_fraction == pytest.approx(
        mean_321.cover_fraction, abs=FLOAT_TOL
    )

    weighted = evaluate_observed_residue_cover(
        observations=[s1, s2, s3],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        aggregation="weighted_by_valid_pixels",
    )
    expected_weighted = (0.70 * 0.30 + 0.90 * 0.70 + 0.80 * 0.50) / (0.70 + 0.90 + 0.80)
    assert weighted.cover_fraction == pytest.approx(expected_weighted, abs=FLOAT_TOL)

    latest = evaluate_observed_residue_cover(
        observations=[s1, s2, s3],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        aggregation="latest",
    )
    assert latest.cover_fraction == pytest.approx(0.70, abs=FLOAT_TOL)


def test_mixed_sensors_rejected_as_not_computable() -> None:
    est = evaluate_observed_residue_cover(
        observations=[_emit_scene(), _hls_scene()],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        calibration=_calibrated_fraction_model(),
    )
    assert isinstance(est.cover_fraction, ResultMissing)
    assert est.cover_fraction.reason == "NOT_COMPUTABLE"
    assert "mix" in (est.cover_fraction.detail or "").lower()


def test_subfactor_strictly_decreasing_in_observed_cover() -> None:
    low_cover = evaluate_observed_residue_cover(
        observations=[_emit_scene(npv_fraction=0.20)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    high_cover = evaluate_observed_residue_cover(
        observations=[_emit_scene(npv_fraction=0.80)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(low_cover.subfactor, float)
    assert isinstance(high_cover.subfactor, float)
    assert 0.0 < high_cover.subfactor < low_cover.subfactor <= 1.0


def test_missing_tabular_cover_still_computes_observed_hypothesis() -> None:
    comp = compare_residue_cover_subfactors(
        tabular_residue_cover=InputMissing(
            reason="NOT_DECLARED", detail="no tabular cover"
        ),
        observations=[_emit_scene(npv_fraction=0.45)],
        min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(comp.tabular_cover_fraction, ResultMissing)
    assert comp.tabular_cover_fraction.reason == "MISSING_INPUT"
    assert isinstance(comp.tabular_subfactor, ResultMissing)
    assert comp.observed_cover_fraction == pytest.approx(0.45, abs=FLOAT_TOL)
    assert comp.observed_hypothesis_subfactor == pytest.approx(
        math.exp(-PLACEHOLDER_B * 45.0), abs=FLOAT_TOL
    )
    assert isinstance(comp.subfactor_difference, ResultMissing)


# --- Validation of invalid thresholds and strict G5 TypeError checks ----------


@pytest.mark.parametrize("bad_min", [0.0, -0.1, 1.1, math.nan, math.inf])
def test_invalid_min_valid_fraction_returns_not_computable(bad_min: float) -> None:
    est = evaluate_observed_residue_cover(
        observations=[_emit_scene()],
        min_valid_fraction=bad_min,
        surface_cover_coefficient_per_percent=PLACEHOLDER_B,
    )
    assert isinstance(est.cover_fraction, ResultMissing)
    assert est.cover_fraction.reason == "NOT_COMPUTABLE"


def test_g5_type_errors() -> None:
    with pytest.raises(TypeError):
        ndti_to_residue_cover(ndti=True, calibration=_calibrated_fraction_model())  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        ndti_to_residue_cover(ndti=0.1, calibration="bad")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        evaluate_observed_residue_cover(
            observations=None,  # type: ignore[arg-type]
            min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
            surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        )

    with pytest.raises(TypeError):
        evaluate_observed_residue_cover(
            observations=[
                SatelliteSceneObservation(
                    sensor="EMIT",
                    observation_date=dt.datetime(2026, 5, 10, 12, 0),  # type: ignore[arg-type]
                    valid_pixel_fraction=0.9,
                    npv_fraction=0.4,
                )
            ],
            min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
            surface_cover_coefficient_per_percent=PLACEHOLDER_B,
        )

    with pytest.raises(ValueError, match="aggregation"):
        evaluate_observed_residue_cover(
            observations=[_emit_scene()],
            min_valid_fraction=PLACEHOLDER_MIN_VALID_FRACTION,
            surface_cover_coefficient_per_percent=PLACEHOLDER_B,
            aggregation="median",  # type: ignore[arg-type]
        )
