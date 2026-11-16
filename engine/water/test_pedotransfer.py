"""Tests for ``engine/water/pedotransfer.py`` (Frontier Unit F-07).

Covers:
- Parametric pedotransfer evaluation (linear, quadratic, and interaction terms)
  with caller-supplied ``PedotransferModelSpec`` and zero hardcoded empirical
  coefficients.
- Uncertainty range ``[low, high]`` generation (symmetric, asymmetric, clamped,
  missing deltas, ``None`` spec, zero-width rejection per C2.2).
- Rev13 Rule 1: three-tier source hierarchy (``MEASURED_LOCAL_PROFILE``,
  ``DERIVED_PEDOTRANSFER``, ``PRIOR_REGIONAL_MAP`` including SoilGrids 2.0 /
  CONEAT priors and mixed-source horizons).
- Rev13 Rule 2: texture sum sanity (``abs((sand + silt + clay) - 100) <= tol``)
  and hydraulic ordering (``0 <= pwp < fc <= porosity <= 1``) returning
  ``Missing(reason="CONTROL_FAILED")`` or ``"NOT_COMPUTABLE"``.
- Rev13 Rule 3: explicit soil depth requirement for profile AWC (``mm``),
  returning ``Missing(reason="MISSING_INPUT", detail=...)`` whenever any
  effective layer depth or rooting depth is ``None`` or ``Missing``, never
  ``0.0`` or guessed depth; plus multi-layer integration, rooting depth cap,
  and depth-splitting invariance.
- G1 purity, immutability, non-mutation, determinism, AST hygiene (zero
  hardcoded empirical constants or forbidden imports), and G5 caller checks.

All coefficients, horizon properties, and depths in this file are synthetic
PLACEHOLDER test values, not from any publication or field dataset.
"""

from __future__ import annotations

import ast
import copy
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.results.models import Missing, Range
from engine.water import pedotransfer
from engine.water.pedotransfer import (
    FEATURE_NAMES,
    SOIL_SOURCE_TAGS,
    HorizonInput,
    LayerWaterProperties,
    PedotransferModelSpec,
    ProfileAwcResult,
    PtfTerm,
    RetentionEquationSpec,
    UncertaintySpec,
    evaluate_pedotransfer_layer,
    evaluate_profile_awc,
)

# PLACEHOLDER synthetic coefficients chosen strictly for exact arithmetic tests.
PLACEHOLDER_PARTICLE_DENSITY = 2.5  # PLACEHOLDER
PLACEHOLDER_TEXTURE_TOLERANCE = 1.0  # PLACEHOLDER


def _placeholder_linear_spec(
    *,
    uncertainty: UncertaintySpec | None = None,
    particle_density: float | Missing = PLACEHOLDER_PARTICLE_DENSITY,
    tolerance: float | Missing = PLACEHOLDER_TEXTURE_TOLERANCE,
) -> PedotransferModelSpec:
    if uncertainty is None:
        uncertainty = UncertaintySpec.symmetric(
            kind="PLACEHOLDER_interval",
            fc_half_width=0.02,
            pwp_half_width=0.01,
            awc_half_width=0.025,
        )
    fc_eq = RetentionEquationSpec.from_linear(
        intercept=0.10,
        sand_pct=-0.001,
        silt_pct=0.001,
        clay_pct=0.004,
        organic_matter_pct=0.01,
        bulk_density=0.02,
    )
    pwp_eq = RetentionEquationSpec.from_linear(
        intercept=0.02,
        sand_pct=-0.0002,
        silt_pct=0.0003,
        clay_pct=0.0025,
        organic_matter_pct=0.002,
        bulk_density=0.01,
    )
    return PedotransferModelSpec(
        model_id="placeholder_linear_ptf",
        field_capacity_eq=fc_eq,
        wilting_point_eq=pwp_eq,
        particle_density=particle_density,
        texture_sum_tolerance_pct=tolerance,
        uncertainty=uncertainty,
    )


def _placeholder_horizon(
    *,
    layer_id: str = "H1",
    sand_pct: float | Missing = 40.0,
    silt_pct: float | Missing = 40.0,
    clay_pct: float | Missing = 20.0,
    organic_matter_pct: float | Missing = 3.0,
    bulk_density: float | Missing = 1.25,
    source_tag: str = "MEASURED_LOCAL_PROFILE",
    source_detail: str = "PLACEHOLDER local soil core",
    effective_depth_mm: float | None | Missing = 300.0,
    property_sources: tuple[tuple[str, str], ...] | None = None,
) -> HorizonInput:
    return HorizonInput(
        layer_id=layer_id,
        sand_pct=sand_pct,
        silt_pct=silt_pct,
        clay_pct=clay_pct,
        organic_matter_pct=organic_matter_pct,
        bulk_density=bulk_density,
        source_tag=source_tag,  # type: ignore[arg-type]
        source_detail=source_detail,
        effective_depth_mm=effective_depth_mm,
        property_sources=property_sources,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Parametric evaluation & uncertainty ranges


def test_linear_pedotransfer_exact_arithmetic_and_ranges() -> None:
    spec = _placeholder_linear_spec()
    horizon = _placeholder_horizon()

    result = evaluate_pedotransfer_layer(horizon, spec)

    # porosity = 1 - 1.25 / 2.5 = 0.50
    expected_porosity = 0.50
    # fc = 0.10 - 0.04 + 0.04 + 0.08 + 0.03 + 0.025 = 0.235
    expected_fc = 0.235
    # pwp = 0.02 - 0.008 + 0.012 + 0.05 + 0.006 + 0.0125 = 0.0925
    expected_pwp = 0.0925
    expected_awc = expected_fc - expected_pwp  # 0.1425

    assert result.porosity == pytest.approx(expected_porosity)
    assert result.field_capacity == pytest.approx(expected_fc)
    assert result.wilting_point == pytest.approx(expected_pwp)
    assert result.available_water_capacity == pytest.approx(expected_awc)
    assert result.awc_mm == pytest.approx(expected_awc * 300.0)
    assert result.unit_volumetric == "m3 m-3"

    assert result.fc_range is not None
    assert result.fc_range.low == pytest.approx(expected_fc - 0.02)
    assert result.fc_range.high == pytest.approx(expected_fc + 0.02)
    assert result.fc_range.kind == "PLACEHOLDER_interval"

    assert result.pwp_range is not None
    assert result.pwp_range.low == pytest.approx(expected_pwp - 0.01)
    assert result.pwp_range.high == pytest.approx(expected_pwp + 0.01)
    assert result.pwp_range.kind == "PLACEHOLDER_interval"

    assert result.awc_range is not None
    assert result.awc_range.low == pytest.approx(expected_awc - 0.025)
    assert result.awc_range.high == pytest.approx(expected_awc + 0.025)
    assert result.awc_range.kind == "PLACEHOLDER_interval"
    assert result.fc_range_missing is None
    assert result.pwp_range_missing is None
    assert result.awc_range_missing is None


def test_polynomial_and_interaction_terms_evaluation() -> None:
    fc_eq = RetentionEquationSpec(
        intercept=0.10,
        terms=(
            PtfTerm(coefficient=0.002, factors=(("clay_pct", 1),)),
            PtfTerm(coefficient=0.0001, factors=(("clay_pct", 2),)),
            PtfTerm(
                coefficient=0.0005,
                factors=(("silt_pct", 1), ("organic_matter_pct", 1)),
            ),
        ),
    )
    pwp_eq = RetentionEquationSpec(
        intercept=0.05,
        terms=(PtfTerm(coefficient=0.001, factors=(("clay_pct", 1),)),),
    )
    spec = PedotransferModelSpec(
        model_id="placeholder_poly_ptf",
        field_capacity_eq=fc_eq,
        wilting_point_eq=pwp_eq,
        particle_density=PLACEHOLDER_PARTICLE_DENSITY,
        texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
        uncertainty=None,
    )
    horizon = _placeholder_horizon(
        sand_pct=40.0,
        silt_pct=40.0,
        clay_pct=20.0,
        organic_matter_pct=3.0,
        bulk_density=1.25,
    )

    result = evaluate_pedotransfer_layer(horizon, spec)

    # fc = 0.10 + 0.002*20 + 0.0001*400 + 0.0005*40*3 = 0.10 + 0.04 + 0.04 + 0.06 = 0.24
    # pwp = 0.05 + 0.001*20 = 0.07
    assert result.field_capacity == pytest.approx(0.24)
    assert result.wilting_point == pytest.approx(0.07)
    assert result.available_water_capacity == pytest.approx(0.17)
    assert result.fc_range is None
    assert isinstance(result.fc_range_missing, Missing)
    assert result.fc_range_missing.reason == "NOT_AVAILABLE"


def test_asymmetric_and_clamped_uncertainty_ranges() -> None:
    unc = UncertaintySpec(
        kind="PLACEHOLDER_asymmetric",
        fc_lower_delta=0.01,
        fc_upper_delta=0.03,
        pwp_lower_delta=0.20,  # exceeds pwp=0.0925 -> clamps to 0.0 when enabled
        pwp_upper_delta=0.02,
        awc_lower_delta=0.015,
        awc_upper_delta=0.04,
        clamp_to_physical_bounds=True,
    )
    spec = _placeholder_linear_spec(uncertainty=unc)
    result = evaluate_pedotransfer_layer(_placeholder_horizon(), spec)

    assert result.pwp_range is not None
    assert result.pwp_range.low == 0.0
    assert result.pwp_range.high == pytest.approx(0.0925 + 0.02)
    assert result.awc_range is not None
    assert result.awc_range.low == pytest.approx(0.1425 - 0.015)
    assert result.awc_range.high == pytest.approx(0.1425 + 0.04)


def test_uncertainty_missing_zero_width_and_negative_deltas() -> None:
    unc = UncertaintySpec(
        kind="PLACEHOLDER_mixed_unc",
        fc_lower_delta=Missing(reason="NOT_AVAILABLE", detail="no lower bound"),
        fc_upper_delta=0.02,
        pwp_lower_delta=0.0,
        pwp_upper_delta=0.0,  # zero width violates C2.2
        awc_lower_delta=-0.01,  # negative delta violates control
        awc_upper_delta=0.02,
    )
    spec = _placeholder_linear_spec(uncertainty=unc)
    result = evaluate_pedotransfer_layer(_placeholder_horizon(), spec)

    assert result.fc_range is None
    assert isinstance(result.fc_range_missing, Missing)
    assert result.fc_range_missing.reason == "MISSING_INPUT"

    assert result.pwp_range is None
    assert isinstance(result.pwp_range_missing, Missing)
    assert result.pwp_range_missing.reason == "CONTROL_FAILED"

    assert result.awc_range is None
    assert isinstance(result.awc_range_missing, Missing)
    assert result.awc_range_missing.reason == "CONTROL_FAILED"


# ---------------------------------------------------------------------------
# Rev13 Rule 1: Source hierarchy


def test_source_hierarchy_all_three_tags_and_soilgrids_never_lab_measured() -> None:
    assert set(SOIL_SOURCE_TAGS) == {
        "MEASURED_LOCAL_PROFILE",
        "DERIVED_PEDOTRANSFER",
        "PRIOR_REGIONAL_MAP",
    }
    spec = _placeholder_linear_spec()

    # 1. Local measured inputs evaluated via PTF -> DERIVED_PEDOTRANSFER
    local_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(
            source_tag="MEASURED_LOCAL_PROFILE",
            source_detail="local lab texture and bulk density",
        ),
        spec,
    )
    assert local_layer.source_tag == "DERIVED_PEDOTRANSFER"
    assert local_layer.is_lab_measured is False
    assert local_layer.provenance == "DERIVED"

    # 2. Regional map prior (SoilGrids 2.0 / CONEAT) -> stays PRIOR_REGIONAL_MAP
    soilgrids_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(
            source_tag="PRIOR_REGIONAL_MAP",
            source_detail="SoilGrids 2.0 0-30 cm prior",
        ),
        spec,
    )
    assert soilgrids_layer.source_tag == "PRIOR_REGIONAL_MAP"
    assert soilgrids_layer.is_lab_measured is False
    assert soilgrids_layer.provenance == "DERIVED"

    coneat_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(
            source_tag="PRIOR_REGIONAL_MAP",
            source_detail="CONEAT soil group prior",
        ),
        spec,
    )
    assert coneat_layer.source_tag == "PRIOR_REGIONAL_MAP"
    assert coneat_layer.is_lab_measured is False

    # 3. Direct lab-measured retention properties -> MEASURED_LOCAL_PROFILE
    measured_layer = LayerWaterProperties(
        layer_id="M1",
        effective_depth_mm=200.0,
        porosity=0.48,
        field_capacity=0.28,
        wilting_point=0.12,
        available_water_capacity=0.16,
        awc_mm=32.0,
        unit_volumetric="m3 m-3",
        fc_range=Range(low=0.26, high=0.30, kind="lab_sd"),
        fc_range_missing=None,
        pwp_range=Range(low=0.11, high=0.13, kind="lab_sd"),
        pwp_range_missing=None,
        awc_range=Range(low=0.14, high=0.18, kind="lab_sd"),
        awc_range_missing=None,
        source_tag="MEASURED_LOCAL_PROFILE",
        input_source_tags=("MEASURED_LOCAL_PROFILE",),
        is_lab_measured=True,
        provenance="OBSERVED",
        source="local retention core",
    )
    measured_profile = evaluate_profile_awc([measured_layer])
    assert measured_profile.source_tag == "MEASURED_LOCAL_PROFILE"
    assert measured_profile.is_lab_measured is True
    assert measured_profile.provenance == "OBSERVED"
    assert measured_profile.total_awc_mm == pytest.approx(32.0)


def test_mixed_property_sources_soilgrids_soc_bd_never_claimed_lab_measured() -> None:
    spec = _placeholder_linear_spec()
    mixed_horizon = _placeholder_horizon(
        source_tag="MEASURED_LOCAL_PROFILE",
        source_detail="local lab texture + SoilGrids 2.0 SOC/BD",
        property_sources=(
            ("sand_pct", "MEASURED_LOCAL_PROFILE"),
            ("silt_pct", "MEASURED_LOCAL_PROFILE"),
            ("clay_pct", "MEASURED_LOCAL_PROFILE"),
            ("organic_matter_pct", "PRIOR_REGIONAL_MAP"),
            ("bulk_density", "PRIOR_REGIONAL_MAP"),
        ),
    )

    layer = evaluate_pedotransfer_layer(mixed_horizon, spec)

    assert layer.source_tag == "PRIOR_REGIONAL_MAP"
    assert layer.is_lab_measured is False
    assert set(layer.input_source_tags) == {
        "MEASURED_LOCAL_PROFILE",
        "PRIOR_REGIONAL_MAP",
    }


def test_profile_source_hierarchy_uses_weakest_contributing_tier() -> None:
    spec = _placeholder_linear_spec()
    top_local = _placeholder_horizon(
        layer_id="top",
        effective_depth_mm=200.0,
        source_tag="MEASURED_LOCAL_PROFILE",
        source_detail="local core",
    )
    sub_prior = _placeholder_horizon(
        layer_id="sub",
        effective_depth_mm=300.0,
        source_tag="PRIOR_REGIONAL_MAP",
        source_detail="SoilGrids 2.0",
    )

    profile = evaluate_profile_awc([top_local, sub_prior], spec)
    assert profile.source_tag == "PRIOR_REGIONAL_MAP"
    assert profile.layer_source_tags == ("DERIVED_PEDOTRANSFER", "PRIOR_REGIONAL_MAP")
    assert profile.is_lab_measured is False

    # If rooting_depth_mm stops inside top layer, only contributing layers determine profile tag.
    shallow_profile = evaluate_profile_awc(
        [top_local, sub_prior], spec, rooting_depth_mm=150.0
    )
    assert shallow_profile.source_tag == "DERIVED_PEDOTRANSFER"
    assert shallow_profile.effective_depth_mm == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Rev13 Rule 2: Texture sum sanity and physical water retention bounds


def test_texture_sum_tolerance_boundary_pass_and_fail() -> None:
    spec = _placeholder_linear_spec(tolerance=1.0)

    # Exactly within tolerance: 40 + 40 + 21 = 101 (diff = 1.0 <= 1.0) -> pass
    ok_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(sand_pct=40.0, silt_pct=40.0, clay_pct=21.0), spec
    )
    assert isinstance(ok_layer.available_water_capacity, float)

    # Outside tolerance: 40 + 40 + 21.1 = 101.1 (diff = 1.1 > 1.0) -> CONTROL_FAILED
    bad_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(sand_pct=40.0, silt_pct=40.0, clay_pct=21.1), spec
    )
    assert isinstance(bad_layer.field_capacity, Missing)
    assert bad_layer.field_capacity.reason == "CONTROL_FAILED"
    assert isinstance(bad_layer.available_water_capacity, Missing)
    assert bad_layer.available_water_capacity.reason == "CONTROL_FAILED"
    assert bad_layer.provenance is None
    assert bad_layer.source is None
    assert bad_layer.awc_range is None


@pytest.mark.parametrize(
    ("kwargs", "expected_reason"),
    [
        ({"sand_pct": -0.1, "silt_pct": 60.1, "clay_pct": 40.0}, "CONTROL_FAILED"),
        ({"clay_pct": 100.5, "sand_pct": 0.0, "silt_pct": 0.0}, "CONTROL_FAILED"),
        ({"organic_matter_pct": -1.0}, "CONTROL_FAILED"),
        ({"organic_matter_pct": 101.0}, "CONTROL_FAILED"),
        ({"bulk_density": 0.0}, "CONTROL_FAILED"),
        ({"bulk_density": PLACEHOLDER_PARTICLE_DENSITY}, "CONTROL_FAILED"),
        ({"sand_pct": math.nan}, "NOT_COMPUTABLE"),
        ({"bulk_density": math.inf}, "NOT_COMPUTABLE"),
    ],
)
def test_domain_and_non_finite_controls(
    kwargs: dict[str, float], expected_reason: str
) -> None:
    spec = _placeholder_linear_spec()
    horizon = _placeholder_horizon(**kwargs)
    layer = evaluate_pedotransfer_layer(horizon, spec)

    assert isinstance(layer.available_water_capacity, Missing)
    assert layer.available_water_capacity.reason == expected_reason


def test_hydraulic_ordering_controls() -> None:
    horizon = _placeholder_horizon()

    # Case 1: pwp < 0 -> CONTROL_FAILED
    neg_pwp_spec = PedotransferModelSpec(
        model_id="neg_pwp",
        field_capacity_eq=RetentionEquationSpec.from_linear(intercept=0.25),
        wilting_point_eq=RetentionEquationSpec.from_linear(intercept=-0.01),
        particle_density=PLACEHOLDER_PARTICLE_DENSITY,
        texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
    )
    res1 = evaluate_pedotransfer_layer(horizon, neg_pwp_spec)
    assert isinstance(res1.available_water_capacity, Missing)
    assert res1.available_water_capacity.reason == "CONTROL_FAILED"

    # Case 2: pwp == fc -> CONTROL_FAILED (strictly pwp < fc required)
    eq_spec = PedotransferModelSpec(
        model_id="equal_fc_pwp",
        field_capacity_eq=RetentionEquationSpec.from_linear(intercept=0.20),
        wilting_point_eq=RetentionEquationSpec.from_linear(intercept=0.20),
        particle_density=PLACEHOLDER_PARTICLE_DENSITY,
        texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
    )
    res2 = evaluate_pedotransfer_layer(horizon, eq_spec)
    assert isinstance(res2.available_water_capacity, Missing)
    assert res2.available_water_capacity.reason == "CONTROL_FAILED"

    # Case 3: fc > porosity (porosity=0.50) -> CONTROL_FAILED
    over_porosity_spec = PedotransferModelSpec(
        model_id="over_porosity",
        field_capacity_eq=RetentionEquationSpec.from_linear(intercept=0.51),
        wilting_point_eq=RetentionEquationSpec.from_linear(intercept=0.10),
        particle_density=PLACEHOLDER_PARTICLE_DENSITY,
        texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
    )
    res3 = evaluate_pedotransfer_layer(horizon, over_porosity_spec)
    assert isinstance(res3.available_water_capacity, Missing)
    assert res3.available_water_capacity.reason == "CONTROL_FAILED"

    # Case 4: boundary valid 0 == pwp < fc == porosity -> succeeds
    boundary_spec = PedotransferModelSpec(
        model_id="boundary_ok",
        field_capacity_eq=RetentionEquationSpec.from_linear(intercept=0.50),
        wilting_point_eq=RetentionEquationSpec.from_linear(intercept=0.0),
        particle_density=PLACEHOLDER_PARTICLE_DENSITY,
        texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
    )
    res4 = evaluate_pedotransfer_layer(horizon, boundary_spec)
    assert res4.wilting_point == 0.0
    assert res4.field_capacity == 0.50
    assert res4.available_water_capacity == 0.50


def test_missing_horizon_input_and_missing_spec_parameter_propagate() -> None:
    spec = _placeholder_linear_spec()
    missing_horizon = _placeholder_horizon(
        bulk_density=Missing(reason="NO_COVERAGE", detail="no BD value at depth")
    )
    res_h = evaluate_pedotransfer_layer(missing_horizon, spec)
    assert isinstance(res_h.available_water_capacity, Missing)
    assert res_h.available_water_capacity.reason == "MISSING_INPUT"
    assert "bulk_density" in (res_h.available_water_capacity.detail or "")

    missing_spec = _placeholder_linear_spec(
        particle_density=Missing(reason="NOT_DECLARED", detail="awaiting catalogue")
    )
    res_s = evaluate_pedotransfer_layer(_placeholder_horizon(), missing_spec)
    assert isinstance(res_s.available_water_capacity, Missing)
    assert res_s.available_water_capacity.reason == "MISSING_INPUT"
    assert "particle_density" in (res_s.available_water_capacity.detail or "")


# ---------------------------------------------------------------------------
# Rev13 Rule 3: Soil depth rules for profile AWC (mm)


def test_missing_or_none_depth_never_defaults_to_zero_or_guessed_depth() -> None:
    spec = _placeholder_linear_spec()

    # None depth on single horizon -> layer volumetric works, awc_mm and profile AWC return Missing
    no_depth_horizon = _placeholder_horizon(effective_depth_mm=None)
    layer = evaluate_pedotransfer_layer(no_depth_horizon, spec)
    assert isinstance(layer.available_water_capacity, float)
    assert isinstance(layer.awc_mm, Missing)
    assert layer.awc_mm.reason == "MISSING_INPUT"

    profile_none = evaluate_profile_awc([no_depth_horizon], spec)
    assert isinstance(profile_none.total_awc_mm, Missing)
    assert profile_none.total_awc_mm.reason == "MISSING_INPUT"
    assert profile_none.total_awc_mm != 0.0
    assert profile_none.provenance is None
    assert profile_none.source is None

    # Missing depth on second horizon in multi-layer profile -> Missing
    h1 = _placeholder_horizon(layer_id="top", effective_depth_mm=200.0)
    h2 = _placeholder_horizon(
        layer_id="sub",
        effective_depth_mm=Missing(reason="NOT_DECLARED", detail="bedrock unknown"),
    )
    profile_missing = evaluate_profile_awc([h1, h2], spec)
    assert isinstance(profile_missing.total_awc_mm, Missing)
    assert profile_missing.total_awc_mm.reason == "MISSING_INPUT"
    assert "sub" in (profile_missing.total_awc_mm.detail or "")

    # Missing rooting_depth_mm -> Missing
    profile_root_missing = evaluate_profile_awc(
        [h1],
        spec,
        rooting_depth_mm=Missing(
            reason="MISSING_INPUT", detail="crop rooting depth absent"
        ),
    )
    assert isinstance(profile_root_missing.total_awc_mm, Missing)
    assert profile_root_missing.total_awc_mm.reason == "MISSING_INPUT"


def test_profile_depth_insufficient_for_rooting_depth_returns_missing() -> None:
    spec = _placeholder_linear_spec()
    h1 = _placeholder_horizon(layer_id="top", effective_depth_mm=250.0)

    profile = evaluate_profile_awc([h1], spec, rooting_depth_mm=600.0)
    assert isinstance(profile.total_awc_mm, Missing)
    assert profile.total_awc_mm.reason == "MISSING_INPUT"


def test_multi_horizon_profile_integration_and_depth_splitting_invariance() -> None:
    spec = _placeholder_linear_spec()
    h_full = _placeholder_horizon(layer_id="full", effective_depth_mm=300.0)
    h_part1 = _placeholder_horizon(layer_id="part1", effective_depth_mm=100.0)
    h_part2 = _placeholder_horizon(layer_id="part2", effective_depth_mm=200.0)

    res_full = evaluate_profile_awc([h_full], spec)
    res_split = evaluate_profile_awc([h_part1, h_part2], spec)

    assert isinstance(res_full.total_awc_mm, float)
    assert isinstance(res_split.total_awc_mm, float)
    assert res_split.total_awc_mm == pytest.approx(res_full.total_awc_mm)
    assert res_full.total_awc_range is not None
    assert res_split.total_awc_range is not None
    assert res_split.total_awc_range.low == pytest.approx(res_full.total_awc_range.low)
    assert res_split.total_awc_range.high == pytest.approx(
        res_full.total_awc_range.high
    )
    assert res_split.effective_depth_mm == pytest.approx(300.0)
    assert res_split.layer_depths_used_mm == (100.0, 200.0)


def test_profile_propagates_layer_control_failed() -> None:
    spec = _placeholder_linear_spec(tolerance=0.5)
    bad_h = _placeholder_horizon(
        layer_id="bad",
        sand_pct=50.0,
        silt_pct=40.0,
        clay_pct=20.0,
        effective_depth_mm=200.0,
    )
    profile = evaluate_profile_awc([bad_h], spec)
    assert isinstance(profile.total_awc_mm, Missing)
    assert profile.total_awc_mm.reason == "CONTROL_FAILED"


def test_empty_horizons_returns_missing_input() -> None:
    spec = _placeholder_linear_spec()
    profile = evaluate_profile_awc([], spec)
    assert isinstance(profile.total_awc_mm, Missing)
    assert profile.total_awc_mm.reason == "MISSING_INPUT"


def test_non_positive_and_non_finite_depths_and_invalid_pre_evaluated_layer() -> None:
    spec = _placeholder_linear_spec()
    neg_depth_layer = evaluate_pedotransfer_layer(
        _placeholder_horizon(effective_depth_mm=0.0), spec
    )
    assert isinstance(neg_depth_layer.available_water_capacity, float)
    assert isinstance(neg_depth_layer.awc_mm, Missing)
    assert neg_depth_layer.awc_mm.reason == "CONTROL_FAILED"

    nan_depth_profile = evaluate_profile_awc(
        [_placeholder_horizon(effective_depth_mm=math.nan)], spec
    )
    assert isinstance(nan_depth_profile.total_awc_mm, Missing)
    assert nan_depth_profile.total_awc_mm.reason == "NOT_COMPUTABLE"

    invalid_measured = LayerWaterProperties(
        layer_id="M_bad",
        effective_depth_mm=200.0,
        porosity=0.45,
        field_capacity=0.50,  # exceeds porosity -> CONTROL_FAILED
        wilting_point=0.10,
        available_water_capacity=0.40,
        awc_mm=80.0,
        unit_volumetric="m3 m-3",
        fc_range=None,
        fc_range_missing=Missing(reason="NOT_AVAILABLE", detail="none"),
        pwp_range=None,
        pwp_range_missing=Missing(reason="NOT_AVAILABLE", detail="none"),
        awc_range=None,
        awc_range_missing=Missing(reason="NOT_AVAILABLE", detail="none"),
        source_tag="MEASURED_LOCAL_PROFILE",
        input_source_tags=("MEASURED_LOCAL_PROFILE",),
        is_lab_measured=True,
        provenance="OBSERVED",
        source="local retention core",
    )
    res_bad = evaluate_profile_awc([invalid_measured])
    assert isinstance(res_bad.total_awc_mm, Missing)
    assert res_bad.total_awc_mm.reason == "CONTROL_FAILED"


# ---------------------------------------------------------------------------
# G1 purity, immutability, AST hygiene, and G5 caller contract checks


def test_dataclasses_are_frozen_and_pure_non_mutating() -> None:
    spec = _placeholder_linear_spec()
    horizon = _placeholder_horizon()
    spec_copy = copy.deepcopy(spec)
    horizon_copy = copy.deepcopy(horizon)

    layer1 = evaluate_pedotransfer_layer(horizon, spec)
    layer2 = evaluate_pedotransfer_layer(horizon, spec)
    assert layer1 == layer2
    assert spec == spec_copy
    assert horizon == horizon_copy

    with pytest.raises(FrozenInstanceError):
        layer1.field_capacity = 0.9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        horizon.sand_pct = 10.0  # type: ignore[misc]

    profile = evaluate_profile_awc([horizon], spec)
    assert isinstance(profile, ProfileAwcResult)
    with pytest.raises(FrozenInstanceError):
        profile.total_awc_mm = 0.0  # type: ignore[misc]


def test_ast_hygiene_zero_hardcoded_empirical_coefficients_or_io() -> None:
    module_path = Path(pedotransfer.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_modules = {
        "os",
        "pathlib",
        "urllib",
        "httpx",
        "requests",
        "socket",
        "datetime",
        "time",
        "random",
        "subprocess",
        "io",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden_modules, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden_modules, f"forbidden import: {node.module}"

    # Only structural constants (0, 1, 2, 100.0) may appear in module code.
    allowed_numbers = {0, 1, 2, 100.0}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                continue
            assert node.value in allowed_numbers, (
                f"unexpected numeric literal {node.value!r} in pedotransfer.py"
            )


def test_g5_caller_defects_raise_type_or_value_error() -> None:
    spec = _placeholder_linear_spec()

    with pytest.raises(TypeError):
        evaluate_pedotransfer_layer("not a horizon", spec)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_pedotransfer_layer(_placeholder_horizon(), "not a spec")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_pedotransfer_layer(_placeholder_horizon(sand_pct=True), spec)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        evaluate_pedotransfer_layer(
            _placeholder_horizon(source_tag="UNKNOWN_TAG"), spec
        )
    with pytest.raises(ValueError):
        evaluate_pedotransfer_layer(_placeholder_horizon(layer_id="   "), spec)
    with pytest.raises(TypeError):
        evaluate_profile_awc("not a sequence", spec)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        bad_term = PtfTerm(coefficient=0.1, factors=(("unknown_feature", 1),))  # type: ignore[arg-type]
        bad_spec = PedotransferModelSpec(
            model_id="bad",
            field_capacity_eq=RetentionEquationSpec(intercept=0.1, terms=(bad_term,)),
            wilting_point_eq=RetentionEquationSpec(intercept=0.05, terms=()),
            particle_density=PLACEHOLDER_PARTICLE_DENSITY,
            texture_sum_tolerance_pct=PLACEHOLDER_TEXTURE_TOLERANCE,
        )
        evaluate_pedotransfer_layer(_placeholder_horizon(), bad_spec)
    assert len(FEATURE_NAMES) == 5
