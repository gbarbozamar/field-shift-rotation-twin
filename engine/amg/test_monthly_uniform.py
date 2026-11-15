"""Tests of ``engine/amg/monthly.py``: uniform-forcing annual vs substep check.

Unit ``l1/amg-monthly-uniform-check`` (blueprint section 8 and D80). Every
constant in this file is a PLACEHOLDER (repeated digits or small whole numbers):
no real value of AMG is written anywhere.
"""

from __future__ import annotations

import ast
import inspect
import math
import re
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.amg.monthly import (
    UniformComparison,
    compare_annual_and_substeps_uniform,
    run_uniform_substeps,
)
from engine.amg.pools import SCHEMES, PoolState, Run, StepResult, initial_state

TIME = "PLACEHOLDER_time"
ABSENT_INPUT = InputMissing(reason="NOT_DECLARED")
ABSENT_RESULT = ResultMissing(reason="NO_COVERAGE", detail="placeholder detail")
BOTH_SHAPES = [ABSENT_INPUT, ABSENT_RESULT]
NOT_FINITE = [math.nan, math.inf, -math.inf, 10**400]
STATE = PoolState(active=44.4, stable=22.2)


def run_substeps(**changes):
    arguments = dict(
        initial_state=STATE,
        annual_humified_input=3.33,
        rate_coefficient=0.222,
        rate_coefficient_per_unit=TIME,
        annual_duration=1.0,
        duration_unit=TIME,
        years=5,
        substeps_per_year=12,
        scheme="exponential",
    )
    return run_uniform_substeps(**{**arguments, **changes})


def compare_uniform(**changes):
    arguments = dict(
        initial_state=STATE,
        annual_humified_input=3.33,
        rate_coefficient=0.222,
        rate_coefficient_per_unit=TIME,
        annual_duration=1.0,
        duration_unit=TIME,
        years=5,
        substeps_per_year=12,
        scheme="exponential",
    )
    return compare_annual_and_substeps_uniform(**{**arguments, **changes})


def assert_missing(result, reason, *words):
    assert isinstance(result, ResultMissing), result
    assert result.reason == reason, result
    for word in words:
        assert word in (result.detail or ""), (word, result.detail)


def assert_run_mass_balance(result: Run):
    assert not isinstance(result.initial_state, ResultMissing)
    for item in result.steps:
        assert isinstance(item, StepResult)
        change = item.end.total - item.start.total
        assert change == pytest.approx(
            item.humified_input - item.mineralised, rel=1e-12, abs=1e-12
        )
        assert item.end.stable == result.initial_state.stable
        assert item.mineralised >= 0.0
    total_in = math.fsum(item.humified_input for item in result.steps)
    total_out = math.fsum(item.mineralised for item in result.steps)
    total_change = result.steps[-1].end.total - result.initial_state.total
    assert total_change == pytest.approx(total_in - total_out, rel=1e-12, abs=1e-12)


# --- exponential uniform-forcing equivalence and mass balance -----------------


@pytest.mark.parametrize("substeps", [1, 2, 4, 12, 52, 365])
@pytest.mark.parametrize("years", [1, 5, 20])
def test_exponential_uniform_substeps_match_annual_across_years(substeps, years):
    comp = compare_uniform(years=years, substeps_per_year=substeps, scheme="exponential")
    assert isinstance(comp, UniformComparison)
    assert comp.scheme == "exponential"
    assert comp.substeps_per_year == substeps
    assert len(comp.annual_run.steps) == years
    assert len(comp.monthly_run.steps) == years * substeps

    annual_final = comp.annual_run.steps[-1].end
    monthly_final = comp.monthly_run.steps[-1].end
    assert monthly_final.active == pytest.approx(
        annual_final.active, rel=1e-12, abs=1e-12
    )
    assert monthly_final.total == pytest.approx(
        annual_final.total, rel=1e-12, abs=1e-12
    )
    assert abs(comp.active_difference) <= max(1e-12, 1e-12 * abs(annual_final.active))
    assert abs(comp.total_difference) <= max(1e-12, 1e-12 * abs(annual_final.total))
    assert comp.monthly_run.elapsed_times()[-1] == pytest.approx(
        comp.annual_run.elapsed_times()[-1], rel=1e-12, abs=1e-12
    )

    for year in range(1, years + 1):
        annual_end = comp.annual_run.steps[year - 1].end
        substep_end = comp.monthly_run.steps[year * substeps - 1].end
        assert substep_end.active == pytest.approx(annual_end.active, rel=1e-12, abs=1e-12)
        assert substep_end.stable == annual_end.stable
        assert substep_end.total == pytest.approx(annual_end.total, rel=1e-12, abs=1e-12)

    assert_run_mass_balance(comp.annual_run)
    assert_run_mass_balance(comp.monthly_run)
    annual_min = math.fsum(s.mineralised for s in comp.annual_run.steps)
    monthly_min = math.fsum(s.mineralised for s in comp.monthly_run.steps)
    assert monthly_min == pytest.approx(annual_min, rel=1e-12, abs=1e-12)


def test_exponential_monthly_matches_annual_across_varied_placeholder_states():
    # Built via pools.initial_state, zero active pool, zero input, and above steady state.
    cases = [
        (initial_state(total_carbon=66.6, stable_fraction=0.333), 3.33, 0.222, 1.0, 10),
        (PoolState(active=0.0, stable=22.2), 4.44, 0.333, 1.0, 8),
        (PoolState(active=99.9, stable=11.1), 0.0, 0.111, 2.0, 6),
        (PoolState(active=55.5, stable=0.0), 1.11, 0.555, 1.0, 12),
    ]
    for init, inflow, rate, duration, years in cases:
        comp = compare_uniform(
            initial_state=init,
            annual_humified_input=inflow,
            rate_coefficient=rate,
            annual_duration=duration,
            years=years,
            substeps_per_year=12,
            scheme="exponential",
        )
        assert comp.active_difference == pytest.approx(0.0, rel=1e-12, abs=1e-12)
        assert comp.total_difference == pytest.approx(0.0, rel=1e-12, abs=1e-12)
        assert_run_mass_balance(comp.annual_run)
        assert_run_mass_balance(comp.monthly_run)


def test_run_uniform_substeps_matches_comparison_monthly_run():
    direct = run_substeps(years=4, substeps_per_year=12, scheme="exponential")
    comp = compare_uniform(years=4, substeps_per_year=12, scheme="exponential")
    assert direct == comp.monthly_run


# --- explicit scheme: mass balance & convergence under substep refinement ------


@pytest.mark.parametrize("years", [1, 5])
def test_explicit_preserves_mass_balance_and_gap_shrinks_as_substeps_increase(years):
    exp_ref = compare_uniform(years=years, substeps_per_year=12, scheme="exponential")
    ref_active = exp_ref.annual_run.steps[-1].end.active
    ref_total = exp_ref.annual_run.steps[-1].end.total

    substep_counts = (4, 12, 365)
    gaps_to_exp_active = []
    gaps_to_exp_total = []
    explicit_active_ends = []

    for substeps in substep_counts:
        comp = compare_uniform(
            years=years, substeps_per_year=substeps, scheme="explicit"
        )
        assert comp.scheme == "explicit"
        assert comp.substeps_per_year == substeps
        assert len(comp.monthly_run.steps) == years * substeps
        assert_run_mass_balance(comp.annual_run)
        assert_run_mass_balance(comp.monthly_run)

        # Explicit 1-step and substep runs differ whenever k > 0 away from steady state.
        assert abs(comp.active_difference) > 0.0
        assert abs(comp.total_difference) > 0.0

        monthly_end = comp.monthly_run.steps[-1].end
        explicit_active_ends.append(monthly_end.active)
        gaps_to_exp_active.append(abs(monthly_end.active - ref_active))
        gaps_to_exp_total.append(abs(monthly_end.total - ref_total))

    # As substeps_per_year increases (4 -> 12 -> 365), explicit substeps converge
    # strictly toward the exact exponential annual reference, and consecutive
    # explicit refinement increments shrink strictly.
    assert gaps_to_exp_active[0] > gaps_to_exp_active[1] > gaps_to_exp_active[2] > 0.0
    assert gaps_to_exp_total[0] > gaps_to_exp_total[1] > gaps_to_exp_total[2] > 0.0
    assert abs(explicit_active_ends[1] - explicit_active_ends[0]) > abs(
        explicit_active_ends[2] - explicit_active_ends[1]
    )


def test_explicit_annual_above_one_refused_while_substeps_compute_gives_missing_diff():
    # rate_coefficient * annual_duration = 1.11 > 1 fails in annual explicit,
    # while 1.11 / 12 < 1 succeeds in monthly explicit.
    comp = compare_uniform(
        rate_coefficient=1.11,
        annual_duration=1.0,
        years=2,
        substeps_per_year=12,
        scheme="explicit",
    )
    assert_missing(comp.annual_run.steps[0], "NOT_COMPUTABLE", "above one")
    assert isinstance(comp.monthly_run.steps[-1], StepResult)
    assert_missing(comp.active_difference, "MISSING_INPUT", "annual_run final step")
    assert_missing(comp.total_difference, "MISSING_INPUT", "annual_run final step")


# --- zero-rate (x == 0) checks ------------------------------------------------


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize(
    "rate, duration",
    [(0.0, 1.0), (0.222, 0.0), (0.0, 0.0)],
)
def test_zero_rate_or_duration_adds_input_and_matches_annual(scheme, rate, duration):
    years = 3
    inflow = 3.33
    comp = compare_uniform(
        annual_humified_input=inflow,
        rate_coefficient=rate,
        annual_duration=duration,
        years=years,
        substeps_per_year=12,
        scheme=scheme,
    )
    expected_active = STATE.active + years * inflow
    assert comp.annual_run.steps[-1].end.active == pytest.approx(expected_active, rel=1e-12)
    assert comp.monthly_run.steps[-1].end.active == pytest.approx(expected_active, rel=1e-12)
    assert comp.active_difference == pytest.approx(0.0, abs=1e-12)
    assert comp.total_difference == pytest.approx(0.0, abs=1e-12)
    assert_run_mass_balance(comp.annual_run)
    assert_run_mass_balance(comp.monthly_run)


# --- Missing, negative, non-finite, unit mismatch (G4) ------------------------


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_missing_inputs_propagate_through_runs_and_differences(scheme, shape):
    for field in ("annual_humified_input", "rate_coefficient", "annual_duration"):
        comp = compare_uniform(years=2, substeps_per_year=12, scheme=scheme, **{field: shape})
        assert len(comp.annual_run.steps) == 2
        assert len(comp.monthly_run.steps) == 24
        assert_missing(comp.annual_run.steps[0], "MISSING_INPUT", shape.reason)
        assert_missing(comp.monthly_run.steps[0], "MISSING_INPUT", shape.reason)
        assert_missing(comp.annual_run.steps[-1], "MISSING_INPUT", "step 0")
        assert_missing(comp.monthly_run.steps[-1], "MISSING_INPUT", "step 0")
        assert_missing(
            comp.active_difference,
            "MISSING_INPUT",
            "annual_run final step",
            "monthly_run final step",
        )
        assert_missing(
            comp.total_difference,
            "MISSING_INPUT",
            "annual_run final step",
            "monthly_run final step",
        )

    if isinstance(shape, ResultMissing):
        comp = compare_uniform(
            initial_state=shape, years=2, substeps_per_year=12, scheme=scheme
        )
        for item in comp.annual_run.steps + comp.monthly_run.steps:
            assert_missing(item, "MISSING_INPUT", "initial state", shape.reason)
        assert_missing(comp.active_difference, "MISSING_INPUT", "annual_run final step")
        assert_missing(comp.total_difference, "MISSING_INPUT", "monthly_run final step")

    refused_state = initial_state(total_carbon=66.6, stable_fraction=1.5)
    comp = compare_uniform(
        initial_state=refused_state, years=1, substeps_per_year=12, scheme=scheme
    )
    assert_missing(comp.annual_run.steps[0], "MISSING_INPUT", "NOT_COMPUTABLE")
    assert_missing(comp.monthly_run.steps[0], "MISSING_INPUT", "NOT_COMPUTABLE")
    assert_missing(comp.active_difference, "MISSING_INPUT", "annual_run final step")


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize(
    "name, expected_fragment, changes",
    [
        ("humified_input", "humified_input", {"annual_humified_input": -3.33}),
        ("rate_coefficient", "rate_coefficient", {"rate_coefficient": -0.222}),
        ("duration", "duration", {"annual_duration": -1.0}),
        ("state.active", "state.active", {"initial_state": PoolState(active=-44.4, stable=22.2)}),
        ("state.stable", "state.stable", {"initial_state": PoolState(active=44.4, stable=-22.2)}),
    ],
)
def test_negative_values_are_not_computable_and_never_clipped(
    scheme, name, expected_fragment, changes
):
    comp = compare_uniform(years=2, substeps_per_year=12, scheme=scheme, **changes)
    assert_missing(comp.annual_run.steps[0], "NOT_COMPUTABLE", expected_fragment, "negative")
    assert_missing(comp.monthly_run.steps[0], "NOT_COMPUTABLE", expected_fragment, "negative")
    assert_missing(comp.annual_run.steps[1], "MISSING_INPUT", "step 0", "NOT_COMPUTABLE")
    assert_missing(comp.monthly_run.steps[-1], "MISSING_INPUT", "step 0", "NOT_COMPUTABLE")
    assert_missing(comp.active_difference, "MISSING_INPUT", "annual_run final step")
    assert_missing(comp.total_difference, "MISSING_INPUT", "monthly_run final step")


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("value", NOT_FINITE)
@pytest.mark.parametrize(
    "field, expected_fragment",
    [
        ("annual_humified_input", "humified_input"),
        ("rate_coefficient", "rate_coefficient"),
        ("annual_duration", "duration"),
    ],
)
def test_non_finite_forcing_gives_not_computable(scheme, value, field, expected_fragment):
    comp = compare_uniform(years=1, substeps_per_year=12, scheme=scheme, **{field: value})
    assert_missing(
        comp.annual_run.steps[0], "NOT_COMPUTABLE", expected_fragment, "not a finite number"
    )
    assert_missing(
        comp.monthly_run.steps[0], "NOT_COMPUTABLE", expected_fragment, "not a finite number"
    )
    assert_missing(comp.active_difference, "MISSING_INPUT", "NOT_COMPUTABLE")
    assert_missing(comp.total_difference, "MISSING_INPUT", "NOT_COMPUTABLE")


@pytest.mark.parametrize("value", NOT_FINITE)
def test_non_finite_initial_state_gives_not_computable(value):
    comp = compare_uniform(
        initial_state=PoolState(active=value, stable=22.2),
        years=1,
        substeps_per_year=12,
    )
    assert_missing(comp.annual_run.steps[0], "NOT_COMPUTABLE", "state.active")
    assert_missing(comp.monthly_run.steps[0], "NOT_COMPUTABLE", "state.active")
    assert_missing(comp.active_difference, "MISSING_INPUT", "NOT_COMPUTABLE")


def test_units_that_differ_are_not_computable():
    comp = compare_uniform(duration_unit="PLACEHOLDER_other_time", years=1, substeps_per_year=12)
    assert_missing(
        comp.annual_run.steps[0], "NOT_COMPUTABLE", TIME, "PLACEHOLDER_other_time"
    )
    assert_missing(
        comp.monthly_run.steps[0], "NOT_COMPUTABLE", TIME, "PLACEHOLDER_other_time"
    )
    assert_missing(comp.active_difference, "MISSING_INPUT", "NOT_COMPUTABLE")


# --- G5 TypeError & ValueError checks, signatures, and no-constants AST -------


@pytest.mark.parametrize("caller", [run_substeps, compare_uniform])
@pytest.mark.parametrize(
    "field", ["annual_humified_input", "rate_coefficient", "annual_duration"]
)
@pytest.mark.parametrize("bad", [None, "1.0", True, [1.0]])
def test_bad_number_type_raises_type_error(caller, field, bad):
    with pytest.raises(TypeError, match=re.escape(field)):
        caller(**{field: bad})


@pytest.mark.parametrize("caller", [run_substeps, compare_uniform])
@pytest.mark.parametrize("field", ["years", "substeps_per_year"])
@pytest.mark.parametrize(
    "bad", [None, True, False, 1.0, "12", ABSENT_INPUT, ABSENT_RESULT]
)
def test_bad_integer_count_type_raises_type_error(caller, field, bad):
    with pytest.raises(TypeError, match=re.escape(field)):
        caller(**{field: bad})


@pytest.mark.parametrize("caller", [run_substeps, compare_uniform])
@pytest.mark.parametrize("field", ["years", "substeps_per_year"])
@pytest.mark.parametrize("bad", [0, -1, -12])
def test_non_positive_integer_count_raises_value_error(caller, field, bad):
    with pytest.raises(ValueError, match=re.escape(field)):
        caller(**{field: bad})


@pytest.mark.parametrize("caller", [run_substeps, compare_uniform])
def test_structured_and_text_bad_types_and_unknown_scheme(caller):
    with pytest.raises(TypeError, match="state"):
        caller(initial_state=(44.4, 22.2))
    with pytest.raises(TypeError, match=re.escape("state.active")):
        caller(initial_state=PoolState(active=None, stable=22.2))
    with pytest.raises(TypeError, match="rate_coefficient_per_unit"):
        caller(rate_coefficient_per_unit=None)
    with pytest.raises(TypeError, match="duration_unit"):
        caller(duration_unit=123)
    with pytest.raises(TypeError, match="scheme"):
        caller(scheme=None)
    with pytest.raises(ValueError, match="scheme"):
        caller(scheme="PLACEHOLDER_scheme")


def test_public_api_has_no_defaults_and_monthly_module_holds_no_constants():
    for fn in (run_uniform_substeps, compare_annual_and_substeps_uniform):
        for param in inspect.signature(fn).parameters.values():
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, (fn, param)
            assert param.default is inspect.Parameter.empty, (fn, param)
    for param in inspect.signature(UniformComparison).parameters.values():
        assert param.default is inspect.Parameter.empty, param

    monthly_path = Path(__file__).parent / "monthly.py"
    tree = ast.parse(monthly_path.read_text(encoding="utf-8"))
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, numbers
