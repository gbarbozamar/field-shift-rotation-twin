"""Tests for ``engine.erosion.dynamic_surface_routing`` (Frontier Line L06).

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Every coefficient in this file is a PLACEHOLDER (plainly synthetic numbers
for algebraic, sensitivity, and invariant verification). No case holds an
expected value of the science.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
import itertools
import math
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import dynamic_surface_routing as dsr
from engine.erosion.dynamic_ls import SlopeSegment, SlopeUnit, dynamic_segmented_ls
from engine.erosion.dynamic_surface_routing import (
    CHANNEL_EXPORT_UNIT,
    DATA_AVAILABILITY,
    FRONTIER_LINE_ID,
    GOVERNANCE_PROPOSED,
    METHOD_MATURITY,
    PROVENANCE_EXPLORATORY,
    ChannelSedimentExportResult,
    ConsolidationForcingPoint,
    ConsolidationStep,
    DynamicSurfacePeriod,
    DynamicSurfacePeriodResult,
    DynamicSurfaceRoutingResult,
    RoughnessForcingPoint,
    SurfaceRoughnessStep,
    consolidation_trajectory,
    evaluate_channel_sediment_export,
    evaluate_dynamic_surface_routing,
    surface_roughness_trajectory,
)

FLOAT_TOL = 1e-12
NOT_FINITE = [math.nan, math.inf, -math.inf]
INVALID_NUMBERS = [None, "5.0", True, False, [5.0]]

# PLACEHOLDER LS coefficients (repeated digits, matching test_dynamic_ls.py style).
PLACEHOLDER_LS_PARAMS = {
    "slope_unit": SlopeUnit.PERCENT,
    "a1": 11.0,
    "a2": 2.2,
    "a3": 22.0,
    "a4": 1.1,
    "s_break": 55.0,
    "lambda_unit": 22.0,
    "b1": 0.11,
    "b2": 2.2,
    "b3": 1.1,
    "b4": 4.4,
}

# PLACEHOLDER roughness coefficients (never real method values).
PLACEHOLDER_ROUGHNESS_PARAMS = {
    "r_initial": 33.0,
    "r_min": 6.0,
    "precip_decay_coef": 0.02,
    "energy_decay_coef": 0.05,
    "roughness_coef": 0.04,
    "roughness_ref": 6.0,
}

# PLACEHOLDER consolidation coefficients (never real method values).
PLACEHOLDER_CONSOLIDATION_PARAMS = {
    "c_disturbed": 1.0,
    "c_consolidated": 0.44,
    "day_decay_coef": 0.01,
    "precip_decay_coef": 0.005,
}

# PLACEHOLDER calibrated channel export parameters (never real method values).
PLACEHOLDER_EXPORT_PARAMS = {
    "gross_hillslope_soil_loss": 12.0,
    "connectivity_index_ic": -1.5,
    "channel_hydraulics_calibrated": True,
    "sdr_max": 0.8,
    "ic_zero": -1.5,
    "k_ic": 0.5,
    "channel_transmission_efficiency": 0.9,
    "calibration_ref": "PLACEHOLDER_CALIBRATION_REF",
}


def a_missing(shape: type, reason: str = "NOT_AVAILABLE"):
    return shape(reason=reason, detail="PLACEHOLDER: missing input")


def assert_missing(result: object, reason: str) -> None:
    assert type(result) is ResultMissing
    assert not isinstance(result, (int, float))
    assert result.reason == reason
    assert result.detail


def named(missing: ResultMissing) -> set[str]:
    return {part.split()[0] for part in missing.detail.split("; ")}


def call_roughness(points, **changes):
    params = dict(PLACEHOLDER_ROUGHNESS_PARAMS)
    params.update(changes)
    return surface_roughness_trajectory(points, **params)


def call_consolidation(points, **changes):
    params = dict(PLACEHOLDER_CONSOLIDATION_PARAMS)
    params.update(changes)
    return consolidation_trajectory(points, **params)


def call_routing(periods, **changes):
    params = {
        **PLACEHOLDER_LS_PARAMS,
        "r_initial": PLACEHOLDER_ROUGHNESS_PARAMS["r_initial"],
        "r_min": PLACEHOLDER_ROUGHNESS_PARAMS["r_min"],
        "roughness_precip_decay_coef": PLACEHOLDER_ROUGHNESS_PARAMS[
            "precip_decay_coef"
        ],
        "roughness_energy_decay_coef": PLACEHOLDER_ROUGHNESS_PARAMS[
            "energy_decay_coef"
        ],
        "roughness_coef": PLACEHOLDER_ROUGHNESS_PARAMS["roughness_coef"],
        "roughness_ref": PLACEHOLDER_ROUGHNESS_PARAMS["roughness_ref"],
        "c_disturbed": PLACEHOLDER_CONSOLIDATION_PARAMS["c_disturbed"],
        "c_consolidated": PLACEHOLDER_CONSOLIDATION_PARAMS["c_consolidated"],
        "consolidation_day_decay_coef": PLACEHOLDER_CONSOLIDATION_PARAMS[
            "day_decay_coef"
        ],
        "consolidation_precip_decay_coef": PLACEHOLDER_CONSOLIDATION_PARAMS[
            "precip_decay_coef"
        ],
    }
    params.update(changes)
    return evaluate_dynamic_surface_routing(periods, **params)


def call_export(**changes):
    params = dict(PLACEHOLDER_EXPORT_PARAMS)
    params.update(changes)
    return evaluate_channel_sediment_export(**params)


# --- 1. Surface roughness trajectory: algebraic & domain checks --------------


def test_roughness_zero_forcing_reproduces_initial_roughness_and_unit_index() -> None:
    points = [
        RoughnessForcingPoint(
            point_id="t0",
            cumulative_precip=0.0,
            cumulative_kinetic_energy=0.0,
        )
    ]
    steps = call_roughness(points)
    assert isinstance(steps, tuple) and len(steps) == 1
    step = steps[0]
    assert step.point_id == "t0"
    assert step.random_roughness == pytest.approx(33.0, abs=FLOAT_TOL)
    assert step.roughness_index == pytest.approx(1.0, abs=FLOAT_TOL)
    expected_subfactor = math.exp(-0.04 * (33.0 - 6.0))
    assert step.roughness_subfactor == pytest.approx(expected_subfactor, rel=FLOAT_TOL)
    assert step.provenance == PROVENANCE_EXPLORATORY
    assert step.governance_status == GOVERNANCE_PROPOSED


def test_roughness_analytical_exponential_decay_and_bounds() -> None:
    # Choose k_p * P + k_e * E = ln(2) so decay_factor == 0.5 exactly.
    ln2 = math.log(2.0)
    points = [
        RoughnessForcingPoint(
            "half_p", cumulative_precip=ln2, cumulative_kinetic_energy=0.0
        ),
        RoughnessForcingPoint(
            "half_e", cumulative_precip=0.0, cumulative_kinetic_energy=ln2
        ),
        RoughnessForcingPoint(
            "extreme", cumulative_precip=1e9, cumulative_kinetic_energy=1e9
        ),
    ]
    steps = call_roughness(
        points,
        r_initial=26.0,
        r_min=6.0,
        precip_decay_coef=1.0,
        energy_decay_coef=1.0,
        roughness_coef=0.1,
        roughness_ref=6.0,
    )
    assert isinstance(steps, tuple)
    # Halfway between 26.0 and 6.0 is 16.0.
    for idx in (0, 1):
        assert steps[idx].random_roughness == pytest.approx(16.0, rel=FLOAT_TOL)
        assert steps[idx].roughness_index == pytest.approx(0.5, rel=FLOAT_TOL)
        assert steps[idx].roughness_subfactor == pytest.approx(
            math.exp(-1.0), rel=FLOAT_TOL
        )

    # Extreme forcing settles strictly within [r_min, r_initial].
    assert 6.0 <= steps[2].random_roughness <= 26.0
    assert steps[2].random_roughness == pytest.approx(6.0, abs=FLOAT_TOL)
    assert steps[2].roughness_index == pytest.approx(0.0, abs=FLOAT_TOL)
    assert steps[2].roughness_subfactor == pytest.approx(1.0, abs=FLOAT_TOL)


def test_roughness_equal_bounds_and_zero_roughness_coef_identities() -> None:
    points = [
        RoughnessForcingPoint(
            "p1", cumulative_precip=15.0, cumulative_kinetic_energy=3.0
        ),
        RoughnessForcingPoint(
            "p2", cumulative_precip=100.0, cumulative_kinetic_energy=20.0
        ),
    ]
    steps = call_roughness(
        points,
        r_initial=12.0,
        r_min=12.0,
        roughness_coef=0.0,
        roughness_ref=6.0,
    )
    assert isinstance(steps, tuple)
    for step in steps:
        assert step.random_roughness == pytest.approx(12.0, abs=FLOAT_TOL)
        assert step.roughness_index == pytest.approx(0.0, abs=FLOAT_TOL)
        assert step.roughness_subfactor == pytest.approx(1.0, abs=FLOAT_TOL)


def test_roughness_empty_points_returns_empty_tuple() -> None:
    assert call_roughness([]) == ()


# --- 2. Consolidation trajectory: algebraic & domain checks ------------------


def test_consolidation_zero_forcing_reproduces_c_disturbed_and_zero_stabilization() -> (
    None
):
    points = [
        ConsolidationForcingPoint(
            point_id="d0", elapsed_days=0.0, cumulative_precip=0.0
        )
    ]
    steps = call_consolidation(points)
    assert isinstance(steps, tuple) and len(steps) == 1
    step = steps[0]
    assert step.point_id == "d0"
    assert step.consolidation_multiplier == pytest.approx(1.0, abs=FLOAT_TOL)
    assert step.stabilization_fraction == pytest.approx(0.0, abs=FLOAT_TOL)
    assert step.provenance == PROVENANCE_EXPLORATORY
    assert step.governance_status == GOVERNANCE_PROPOSED


def test_consolidation_analytical_decay_and_equal_bounds_identity() -> None:
    ln2 = math.log(2.0)
    points = [
        ConsolidationForcingPoint("days_only", elapsed_days=ln2, cumulative_precip=0.0),
        ConsolidationForcingPoint(
            "precip_only", elapsed_days=0.0, cumulative_precip=ln2
        ),
        ConsolidationForcingPoint("settled", elapsed_days=1e9, cumulative_precip=1e9),
    ]
    steps = call_consolidation(
        points,
        c_disturbed=1.0,
        c_consolidated=0.4,
        day_decay_coef=1.0,
        precip_decay_coef=1.0,
    )
    assert isinstance(steps, tuple)
    for idx in (0, 1):
        assert steps[idx].consolidation_multiplier == pytest.approx(0.7, rel=FLOAT_TOL)
        assert steps[idx].stabilization_fraction == pytest.approx(0.5, rel=FLOAT_TOL)
    assert 0.4 <= steps[2].consolidation_multiplier <= 1.0
    assert steps[2].consolidation_multiplier == pytest.approx(0.4, abs=FLOAT_TOL)
    assert steps[2].stabilization_fraction == pytest.approx(1.0, abs=FLOAT_TOL)

    steady = call_consolidation(
        points,
        c_disturbed=0.5,
        c_consolidated=0.5,
        day_decay_coef=0.1,
        precip_decay_coef=0.1,
    )
    assert isinstance(steady, tuple)
    for step in steady:
        assert step.consolidation_multiplier == pytest.approx(0.5, abs=FLOAT_TOL)


# --- 3. Dynamic surface routing wrapper & provenance -------------------------


def test_dynamic_surface_routing_reduces_exactly_to_dynamic_segmented_ls_when_unit_factors() -> (
    None
):
    segs_a = [
        SlopeSegment(length_m=15.0, steepness=3.0),
        SlopeSegment(length_m=25.0, steepness=9.0),
    ]
    segs_b = [SlopeSegment(length_m=30.0, steepness=12.0)]
    periods = [
        DynamicSurfacePeriod(
            period_id="p_a",
            segments=segs_a,
            cumulative_precip_since_tillage=20.0,
            cumulative_kinetic_energy_since_tillage=5.0,
            elapsed_days_since_disturbance=10.0,
            cumulative_precip_since_disturbance=20.0,
        ),
        DynamicSurfacePeriod(
            period_id="p_b",
            segments=segs_b,
            cumulative_precip_since_tillage=80.0,
            cumulative_kinetic_energy_since_tillage=18.0,
            elapsed_days_since_disturbance=45.0,
            cumulative_precip_since_disturbance=80.0,
        ),
    ]
    res = call_routing(
        periods,
        roughness_coef=0.0,
        c_disturbed=1.0,
        c_consolidated=1.0,
    )
    assert isinstance(res, DynamicSurfaceRoutingResult)
    assert res.provenance == PROVENANCE_EXPLORATORY
    assert res.governance_status == GOVERNANCE_PROPOSED
    assert res.frontier_line == FRONTIER_LINE_ID
    assert res.method_maturity == METHOD_MATURITY
    assert res.data_availability == DATA_AVAILABILITY
    assert res.normative_ep1_untouched is True
    assert res.overwrites_normative_ep1 is False

    for period, p_res in zip(periods, res.periods):
        expected_ls = dynamic_segmented_ls(period.segments, **PLACEHOLDER_LS_PARAMS)
        assert p_res.period_id == period.period_id
        assert p_res.segmented_ls == pytest.approx(expected_ls, rel=FLOAT_TOL)
        assert p_res.roughness_subfactor == pytest.approx(1.0, abs=FLOAT_TOL)
        assert p_res.consolidation_multiplier == pytest.approx(1.0, abs=FLOAT_TOL)
        assert p_res.effective_surface_factor == pytest.approx(
            expected_ls, rel=FLOAT_TOL
        )


def test_dynamic_surface_routing_multiplies_ls_roughness_and_consolidation() -> None:
    periods = [
        DynamicSurfacePeriod(
            period_id=("rot", 1),
            segments=[
                SlopeSegment(length_m=20.0, steepness=4.0),
                SlopeSegment(length_m=20.0, steepness=10.0),
            ],
            cumulative_precip_since_tillage=25.0,
            cumulative_kinetic_energy_since_tillage=6.0,
            elapsed_days_since_disturbance=15.0,
            cumulative_precip_since_disturbance=25.0,
        ),
        DynamicSurfacePeriod(
            period_id=("rot", 2),
            segments=[
                SlopeSegment(length_m=20.0, steepness=4.0),
                SlopeSegment(length_m=20.0, steepness=10.0),
            ],
            cumulative_precip_since_tillage=120.0,
            cumulative_kinetic_energy_since_tillage=30.0,
            elapsed_days_since_disturbance=90.0,
            cumulative_precip_since_disturbance=120.0,
        ),
    ]
    res = call_routing(periods)
    assert len(res.periods) == 2
    for p_res in res.periods:
        assert isinstance(p_res.segmented_ls, float)
        assert isinstance(p_res.roughness_subfactor, float)
        assert isinstance(p_res.consolidation_multiplier, float)
        assert p_res.effective_surface_factor == pytest.approx(
            p_res.segmented_ls
            * p_res.roughness_subfactor
            * p_res.consolidation_multiplier,
            rel=FLOAT_TOL,
        )


def test_dynamic_surface_routing_isolates_missing_periods_without_corrupting_valid_ones() -> (
    None
):
    valid_seg = [SlopeSegment(length_m=22.0, steepness=6.0)]
    periods = [
        DynamicSurfacePeriod("ok_1", valid_seg, 10.0, 2.0, 5.0, 10.0),
        DynamicSurfacePeriod(
            "missing_p", valid_seg, a_missing(InputMissing), 2.0, 5.0, 10.0
        ),
        DynamicSurfacePeriod("bad_seg", [], 10.0, 2.0, 5.0, 10.0),
        DynamicSurfacePeriod("bad_days", valid_seg, 10.0, 2.0, -3.0, 10.0),
        DynamicSurfacePeriod("ok_2", valid_seg, 30.0, 6.0, 20.0, 30.0),
    ]
    res = call_routing(periods)
    by_id = {p.period_id: p for p in res.periods}

    assert isinstance(by_id["ok_1"].effective_surface_factor, float)
    assert isinstance(by_id["ok_2"].effective_surface_factor, float)

    assert_missing(by_id["missing_p"].random_roughness, "MISSING_INPUT")
    assert_missing(by_id["missing_p"].effective_surface_factor, "MISSING_INPUT")
    assert isinstance(by_id["missing_p"].segmented_ls, float)
    assert isinstance(by_id["missing_p"].consolidation_multiplier, float)

    assert_missing(by_id["bad_seg"].segmented_ls, "NOT_COMPUTABLE")
    assert_missing(by_id["bad_seg"].effective_surface_factor, "NOT_COMPUTABLE")

    assert_missing(by_id["bad_days"].consolidation_multiplier, "NOT_COMPUTABLE")
    assert_missing(by_id["bad_days"].effective_surface_factor, "NOT_COMPUTABLE")


def test_dynamic_surface_routing_empty_periods_preserves_provenance() -> None:
    res = call_routing([])
    assert res.periods == ()
    assert res.provenance == PROVENANCE_EXPLORATORY
    assert res.normative_ep1_untouched is True


def test_provenance_tampering_rejected_in_post_init() -> None:
    with pytest.raises(ValueError, match="overwrites_normative_ep1"):
        DynamicSurfaceRoutingResult(
            periods=(),
            provenance=PROVENANCE_EXPLORATORY,
            governance_status=GOVERNANCE_PROPOSED,
            frontier_line=FRONTIER_LINE_ID,
            method_maturity=METHOD_MATURITY,
            data_availability=DATA_AVAILABILITY,
            normative_ep1_untouched=True,
            overwrites_normative_ep1=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="normative_ep1_untouched"):
        DynamicSurfaceRoutingResult(
            periods=(),
            provenance=PROVENANCE_EXPLORATORY,
            governance_status=GOVERNANCE_PROPOSED,
            frontier_line=FRONTIER_LINE_ID,
            method_maturity=METHOD_MATURITY,
            data_availability=DATA_AVAILABILITY,
            normative_ep1_untouched=False,  # type: ignore[arg-type]
            overwrites_normative_ep1=False,
        )
    with pytest.raises(ValueError, match="unit"):
        ChannelSedimentExportResult(
            exported_sediment_yield=1.0,
            sediment_delivery_ratio=0.5,
            unit="dimensionless",  # type: ignore[arg-type]
            calibration_ref="ref",
            provenance=PROVENANCE_EXPLORATORY,
            governance_status=GOVERNANCE_PROPOSED,
            frontier_line=FRONTIER_LINE_ID,
            overwrites_normative_ep1=False,
        )


# --- 4. Channel-sediment mass export guard -----------------------------------


def test_channel_export_refuses_uncalibrated_channel_hydraulics_flag() -> None:
    result = call_export(channel_hydraulics_calibrated=False)
    assert_missing(result, "NOT_AVAILABLE")
    assert "IC" in result.detail
    assert CHANNEL_EXPORT_UNIT in result.detail


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize(
    "param",
    [
        "sdr_max",
        "ic_zero",
        "k_ic",
        "channel_transmission_efficiency",
        "calibration_ref",
    ],
)
def test_channel_export_refuses_missing_sdr_or_calibration_params(shape, param) -> None:
    result = call_export(**{param: a_missing(shape)})
    assert_missing(result, "NOT_AVAILABLE")
    assert param in result.detail


def test_channel_export_refusal_takes_precedence_over_missing_hillslope_loss() -> None:
    result = call_export(
        channel_hydraulics_calibrated=False,
        gross_hillslope_soil_loss=a_missing(InputMissing),
    )
    assert_missing(result, "NOT_AVAILABLE")


def test_channel_export_computes_calibrated_sdr_and_yield() -> None:
    # At connectivity_index_ic == ic_zero, SDR == sdr_max / (1 + 1) == 0.5 * sdr_max.
    res = call_export(
        gross_hillslope_soil_loss=10.0,
        connectivity_index_ic=-2.0,
        ic_zero=-2.0,
        sdr_max=0.6,
        k_ic=0.5,
        channel_transmission_efficiency=0.8,
        calibration_ref="CAL-UY-2026",
    )
    assert isinstance(res, ChannelSedimentExportResult)
    assert res.unit == CHANNEL_EXPORT_UNIT
    assert res.provenance == PROVENANCE_EXPLORATORY
    assert res.governance_status == GOVERNANCE_PROPOSED
    assert res.frontier_line == FRONTIER_LINE_ID
    assert res.overwrites_normative_ep1 is False
    assert res.calibration_ref == "CAL-UY-2026"
    assert res.sediment_delivery_ratio == pytest.approx(0.3, rel=FLOAT_TOL)
    assert res.exported_sediment_yield == pytest.approx(2.4, rel=FLOAT_TOL)


def test_channel_export_missing_gross_loss_or_ic_when_calibrated_returns_missing_input() -> (
    None
):
    r1 = call_export(gross_hillslope_soil_loss=a_missing(InputMissing))
    assert_missing(r1, "MISSING_INPUT")
    assert named(r1) == {"gross_hillslope_soil_loss"}

    r2 = call_export(connectivity_index_ic=a_missing(ResultMissing))
    assert_missing(r2, "MISSING_INPUT")
    assert named(r2) == {"connectivity_index_ic"}


# --- 5. Sensitivity & monotonicity invariants --------------------------------


def test_roughness_and_subfactor_sensitivity_to_cumulative_precip_and_ke() -> None:
    precip_levels = [0.0, 20.0, 60.0, 150.0]
    pts_p = [
        RoughnessForcingPoint(i, cumulative_precip=p, cumulative_kinetic_energy=0.0)
        for i, p in enumerate(precip_levels)
    ]
    steps_p = call_roughness(pts_p)
    assert isinstance(steps_p, tuple)
    assert all(
        a.random_roughness > b.random_roughness for a, b in itertools.pairwise(steps_p)
    )
    assert all(
        a.roughness_subfactor < b.roughness_subfactor
        for a, b in itertools.pairwise(steps_p)
    )

    ke_levels = [0.0, 5.0, 15.0, 40.0]
    pts_e = [
        RoughnessForcingPoint(i, cumulative_precip=0.0, cumulative_kinetic_energy=e)
        for i, e in enumerate(ke_levels)
    ]
    steps_e = call_roughness(pts_e)
    assert isinstance(steps_e, tuple)
    assert all(
        a.random_roughness > b.random_roughness for a, b in itertools.pairwise(steps_e)
    )


def test_consolidation_sensitivity_to_days_and_precip() -> None:
    days_levels = [0.0, 15.0, 60.0, 180.0]
    steps = call_consolidation(
        [
            ConsolidationForcingPoint(i, elapsed_days=d, cumulative_precip=0.0)
            for i, d in enumerate(days_levels)
        ]
    )
    assert isinstance(steps, tuple)
    assert all(
        a.consolidation_multiplier > b.consolidation_multiplier
        for a, b in itertools.pairwise(steps)
    )
    assert all(
        a.stabilization_fraction < b.stabilization_fraction
        for a, b in itertools.pairwise(steps)
    )


def test_channel_export_monotonic_in_ic_and_gross_loss() -> None:
    ic_vals = [-4.0, -2.0, 0.0, 2.0]
    exports = [call_export(connectivity_index_ic=ic) for ic in ic_vals]
    assert all(isinstance(r, ChannelSedimentExportResult) for r in exports)
    assert all(
        a.sediment_delivery_ratio < b.sediment_delivery_ratio
        for a, b in itertools.pairwise(exports)
    )
    assert all(
        a.exported_sediment_yield < b.exported_sediment_yield
        for a, b in itertools.pairwise(exports)
    )


# --- 6. G4 Missing propagation & NOT_COMPUTABLE domain checks ----------------


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("param", list(PLACEHOLDER_ROUGHNESS_PARAMS))
def test_roughness_missing_scalar_params_propagate(shape, param) -> None:
    res = call_roughness(
        [RoughnessForcingPoint("p0", 10.0, 2.0)], **{param: a_missing(shape)}
    )
    assert_missing(res, "MISSING_INPUT")
    assert named(res) == {param}


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("param", list(PLACEHOLDER_CONSOLIDATION_PARAMS))
def test_consolidation_missing_scalar_params_propagate(shape, param) -> None:
    res = call_consolidation(
        [ConsolidationForcingPoint("p0", 10.0, 2.0)], **{param: a_missing(shape)}
    )
    assert_missing(res, "MISSING_INPUT")
    assert named(res) == {param}


@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "minus-inf"])
def test_non_finite_inputs_return_not_computable(number) -> None:
    assert_missing(
        call_roughness([RoughnessForcingPoint("p0", 10.0, 2.0)], r_initial=number),
        "NOT_COMPUTABLE",
    )
    assert_missing(
        call_consolidation(
            [ConsolidationForcingPoint("p0", 10.0, 2.0)], c_disturbed=number
        ),
        "NOT_COMPUTABLE",
    )
    assert_missing(call_export(gross_hillslope_soil_loss=number), "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"r_initial": 0.0},
        {"r_initial": -5.0},
        {"r_min": -1.0},
        {"r_min": 50.0, "r_initial": 20.0},
        {"precip_decay_coef": -0.1},
        {"energy_decay_coef": -0.1},
        {"roughness_coef": -0.1},
        {"roughness_ref": -0.1},
    ],
)
def test_roughness_out_of_domain_scalars_return_not_computable(bad_kwargs) -> None:
    res = call_roughness([RoughnessForcingPoint("p0", 10.0, 2.0)], **bad_kwargs)
    assert_missing(res, "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"c_disturbed": 0.0},
        {"c_consolidated": 0.0},
        {"c_consolidated": 1.5, "c_disturbed": 1.0},
        {"day_decay_coef": -0.1},
        {"precip_decay_coef": -0.1},
    ],
)
def test_consolidation_out_of_domain_scalars_return_not_computable(bad_kwargs) -> None:
    res = call_consolidation([ConsolidationForcingPoint("p0", 10.0, 2.0)], **bad_kwargs)
    assert_missing(res, "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"gross_hillslope_soil_loss": -0.1},
        {"sdr_max": 0.0},
        {"sdr_max": 1.2},
        {"k_ic": 0.0},
        {"k_ic": -0.5},
        {"channel_transmission_efficiency": 0.0},
        {"channel_transmission_efficiency": 1.1},
    ],
)
def test_channel_export_out_of_domain_returns_not_computable(bad_kwargs) -> None:
    assert_missing(call_export(**bad_kwargs), "NOT_COMPUTABLE")


def test_scalar_missing_propagates_inside_evaluate_dynamic_surface_routing() -> None:
    periods = [
        DynamicSurfacePeriod(
            "p0",
            [SlopeSegment(22.0, 5.0)],
            10.0,
            2.0,
            5.0,
            10.0,
        )
    ]
    res = call_routing(periods, r_initial=a_missing(InputMissing))
    p = res.periods[0]
    assert isinstance(p.segmented_ls, float)
    assert isinstance(p.consolidation_multiplier, float)
    assert_missing(p.random_roughness, "MISSING_INPUT")
    assert_missing(p.roughness_subfactor, "MISSING_INPUT")
    assert_missing(p.effective_surface_factor, "MISSING_INPUT")


# --- 7. G5 TypeError & ValueError caller defect checks -----------------------


@pytest.mark.parametrize("bad_val", INVALID_NUMBERS, ids=lambda x: repr(x))
def test_invalid_number_types_raise_type_error(bad_val) -> None:
    with pytest.raises(TypeError):
        call_roughness([RoughnessForcingPoint("p0", bad_val, 2.0)])
    with pytest.raises(TypeError):
        call_roughness([RoughnessForcingPoint("p0", 2.0, 2.0)], r_initial=bad_val)
    with pytest.raises(TypeError):
        call_consolidation([ConsolidationForcingPoint("p0", bad_val, 2.0)])
    with pytest.raises(TypeError):
        call_consolidation(
            [ConsolidationForcingPoint("p0", 2.0, 2.0)], c_disturbed=bad_val
        )
    with pytest.raises(TypeError):
        call_export(gross_hillslope_soil_loss=bad_val)


def test_invalid_container_and_metadata_types_raise_type_error_or_value_error() -> None:
    with pytest.raises(TypeError):
        call_roughness("not-a-sequence")
    with pytest.raises(TypeError):
        call_roughness([("p0", 1.0, 1.0)])
    with pytest.raises(TypeError):
        call_consolidation("not-a-sequence")
    with pytest.raises(TypeError):
        call_consolidation([("p0", 1.0, 1.0)])
    with pytest.raises(TypeError):
        call_routing("not-a-sequence")
    with pytest.raises(TypeError):
        call_routing([("p0",)])
    with pytest.raises(TypeError):
        call_routing([], slope_unit="percent")
    with pytest.raises(TypeError):
        call_export(channel_hydraulics_calibrated=1)
    with pytest.raises(TypeError):
        call_export(calibration_ref=123)
    with pytest.raises(ValueError):
        call_export(calibration_ref="   ")


# --- 8. G1 purity, zero defaults, and AST hygiene checks ---------------------


def test_frozen_dataclasses_have_no_defaults_and_are_immutable() -> None:
    classes = (
        RoughnessForcingPoint,
        SurfaceRoughnessStep,
        ConsolidationForcingPoint,
        ConsolidationStep,
        DynamicSurfacePeriod,
        DynamicSurfacePeriodResult,
        DynamicSurfaceRoutingResult,
        ChannelSedimentExportResult,
    )
    for cls in classes:
        assert dataclasses.is_dataclass(cls)
        for field in dataclasses.fields(cls):
            assert field.default is dataclasses.MISSING, (cls.__name__, field.name)
            assert field.default_factory is dataclasses.MISSING, (
                cls.__name__,
                field.name,
            )

    pt = RoughnessForcingPoint("p0", 1.0, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pt.cumulative_precip = 2.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("func", "positional_count"),
    [
        (surface_roughness_trajectory, 1),
        (consolidation_trajectory, 1),
        (evaluate_dynamic_surface_routing, 1),
        (evaluate_channel_sediment_export, 0),
    ],
)
def test_zero_default_parameter_values_and_keyword_only_coefficients(
    func, positional_count
) -> None:
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    assert params
    for param in params:
        assert param.default is inspect.Parameter.empty, param.name
    for param in params[positional_count:]:
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, param.name


def test_ast_hygiene_zero_constants_and_allowed_imports_only() -> None:
    source = Path(dsr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Zero hardcoded numerical science constants (only 0 and 1 allowed).
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, (
        f"unexpected numeric constants in dynamic_surface_routing.py: {numbers}"
    )

    # Zero default parameter values in AST.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.args.defaults == []
            assert all(d is None for d in node.args.kw_defaults)

    # G1 purity: no I/O, network, clock, random, or normative soil_loss references.
    forbidden_names = {
        "open",
        "read_text",
        "write_text",
        "os",
        "pathlib",
        "socket",
        "time",
        "datetime",
        "random",
        "httpx",
        "urllib",
        "soil_loss",
        "compute_soil_loss",
        "A_norm",
    }
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            used_names.add(node.attr)
        elif isinstance(node, ast.alias):
            used_names.add(node.name)
    assert used_names.isdisjoint(forbidden_names), used_names & forbidden_names
    assert "C:\\" not in source

    # Allowed imports only: stdlib + contracts.* + engine.erosion.dynamic_ls.
    import sys

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in sys.stdlib_module_names, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            top = node.module.split(".")[0]
            assert (
                top in sys.stdlib_module_names
                or node.module.startswith("contracts.")
                or node.module == "engine.erosion.dynamic_ls"
            ), node.module


def test_g1_determinism_and_input_immutability() -> None:
    periods = [
        DynamicSurfacePeriod(
            period_id="p1",
            segments=[SlopeSegment(22.0, 6.0), SlopeSegment(18.0, 9.0)],
            cumulative_precip_since_tillage=25.0,
            cumulative_kinetic_energy_since_tillage=6.0,
            elapsed_days_since_disturbance=14.0,
            cumulative_precip_since_disturbance=25.0,
        )
    ]
    snapshot = copy.deepcopy(periods)
    first = call_routing(periods)
    second = call_routing(periods)
    assert periods == snapshot
    assert first == second
