"""Mutant-killing tests for ``engine/amg/`` (unit l1/amg-mutants).

Every value and record in this file is a PLACEHOLDER (repeated digits or small
whole numbers); no real value of AMG is written anywhere.
"""

from __future__ import annotations

import copy
import math

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.amg import (
    PoolState,
    StepInput,
    carbonate_modifier,
    clay_modifier,
    end_minus_start,
    fitted_slope,
    mean_over_cycles,
    moisture_modifier,
    run_amg,
    temperature_modifier,
    trend_measures,
)
from engine.amg.entry import FORCING_QUANTITIES, METHOD_LABEL, PARAMETERS, STOCK_UNIT
from engine.amg.test_amg import (
    ABSENT_INPUT,
    ABSENT_RESULT,
    CONTENT,
    DEGREE,
    DEPTH,
    a_run,
    assert_missing,
    carbonate,
    clay,
    cn,
    humified,
    initial,
    moisture,
    one_step,
    rate,
    temperature,
)
from engine.amg.test_entry import (
    MARK,
    UNMARKED,
    YEARS,
    annual,
    catalogue,
    catalogue_with,
    forcing,
    forcing_data,
    unmark,
)

# --- _numbers.py: missing precedence, multi-failure details, zero bounds ----


def test_multiple_missing_arguments_are_all_named_in_detail():
    assert_missing(
        temperature(temperature=ABSENT_INPUT, shape_coefficient=ABSENT_RESULT),
        "MISSING_INPUT",
        "temperature",
        "NOT_DECLARED",
        "shape_coefficient",
        "NO_COVERAGE",
    )
    assert_missing(
        cn(cn_ratio=ABSENT_INPUT, minimum=ABSENT_RESULT),
        "MISSING_INPUT",
        "cn_ratio",
        "NOT_DECLARED",
        "minimum",
        "NO_COVERAGE",
    )
    assert_missing(
        initial(total_carbon=ABSENT_INPUT, stable_fraction=ABSENT_RESULT),
        "MISSING_INPUT",
        "total_carbon",
        "NOT_DECLARED",
        "stable_fraction",
        "NO_COVERAGE",
    )
    assert_missing(
        one_step(humified_input=ABSENT_INPUT, duration=ABSENT_RESULT),
        "MISSING_INPUT",
        "humified_input",
        "NOT_DECLARED",
        "duration",
        "NO_COVERAGE",
    )
    assert_missing(
        rate(potential_rate=ABSENT_INPUT, modifiers={"a": ABSENT_RESULT}),
        "MISSING_INPUT",
        "potential_rate",
        "NOT_DECLARED",
        "'a'",
        "NO_COVERAGE",
    )


def test_missing_input_precedes_non_finite_out_of_range_and_unit_mismatch():
    assert_missing(
        temperature(
            temperature=ABSENT_INPUT,
            shape_coefficient=math.nan,
            temperature_unit="PLACEHOLDER_other_unit",
        ),
        "MISSING_INPUT",
        "temperature",
    )
    assert_missing(
        cn(cn_ratio=-1.0, minimum=ABSENT_INPUT),
        "MISSING_INPUT",
        "minimum",
    )
    assert_missing(
        initial(total_carbon=ABSENT_INPUT, stable_fraction=1.5),
        "MISSING_INPUT",
        "total_carbon",
    )
    assert_missing(
        humified(
            carbon_inputs={"origin_a": -4.44, "origin_b": ABSENT_INPUT},
            humification_coefficients={"origin_a": 0.111, "origin_b": 0.222},
        ),
        "MISSING_INPUT",
        "origin_b",
    )
    assert_missing(
        humified(
            carbon_inputs={"origin_a": -4.44, "origin_b": 5.55},
            humification_coefficients={"origin_a": 0.111},
        ),
        "MISSING_INPUT",
        "origin_b",
    )
    assert_missing(
        one_step(
            humified_input=-3.33,
            duration=ABSENT_INPUT,
            duration_unit="PLACEHOLDER_other_unit",
        ),
        "MISSING_INPUT",
        "duration",
    )
    assert_missing(
        rate(potential_rate=-0.444, modifiers={"a": ABSENT_INPUT}),
        "MISSING_INPUT",
        "'a'",
    )


def test_non_finite_and_range_checks_precede_unit_mismatch_and_name_all_failures():
    assert_missing(
        clay(clay_content=math.nan, clay_content_unit="PLACEHOLDER_other_unit"),
        "NOT_COMPUTABLE",
        "clay_content",
        "not a finite number",
    )
    assert_missing(
        clay(clay_content=-1.0, clay_content_unit="PLACEHOLDER_other_unit"),
        "NOT_COMPUTABLE",
        "clay_content",
        "negative",
    )
    assert_missing(
        one_step(duration=-1.0, duration_unit="PLACEHOLDER_other_unit"),
        "NOT_COMPUTABLE",
        "duration",
        "negative",
    )
    assert_missing(
        one_step(
            state=PoolState(active=-1.0, stable=22.2),
            humified_input=-2.0,
        ),
        "NOT_COMPUTABLE",
        "state.active",
        "humified_input",
    )
    assert_missing(
        humified(humification_coefficients={}),
        "MISSING_INPUT",
        "origin_a",
        "origin_b",
    )
    assert_missing(
        humified(humification_coefficients={"origin_a": -0.1, "origin_b": 1.1}),
        "NOT_COMPUTABLE",
        "origin_a",
        "origin_b",
    )


def test_zero_boundaries_accepted_and_tiny_negatives_refused():
    zero_rate = rate(potential_rate=0.0, modifiers={"a": 0.555})
    assert zero_rate == 0.0 and isinstance(zero_rate, float)
    assert_missing(rate(potential_rate=-1e-12), "NOT_COMPUTABLE", "potential_rate")
    assert_missing(rate(modifiers={"a": -1e-12}), "NOT_COMPUTABLE", "'a'")

    zero_state = initial(total_carbon=0.0, stable_fraction=0.333)
    assert zero_state == PoolState(active=0.0, stable=0.0)
    assert_missing(initial(total_carbon=-1e-12), "NOT_COMPUTABLE", "total_carbon")

    for scheme in ("explicit", "exponential"):
        res = one_step(
            state=PoolState(active=0.0, stable=0.0),
            humified_input=0.0,
            rate_coefficient=0.0,
            duration=0.0,
            scheme=scheme,
        )
        assert res.end == PoolState(active=0.0, stable=0.0)
        assert res.mineralised == 0.0

    for field, val in [
        ("humified_input", -1e-12),
        ("rate_coefficient", -1e-12),
        ("duration", -1e-12),
    ]:
        assert_missing(one_step(**{field: val}), "NOT_COMPUTABLE", field)
    assert_missing(
        one_step(state=PoolState(active=-1e-12, stable=0.0)),
        "NOT_COMPUTABLE",
        "state.active",
    )
    assert_missing(
        one_step(state=PoolState(active=0.0, stable=-1e-12)),
        "NOT_COMPUTABLE",
        "state.stable",
    )
    assert_missing(clay(clay_content=-1e-12), "NOT_COMPUTABLE", "clay_content")
    assert_missing(
        carbonate(carbonate_content=-1e-12), "NOT_COMPUTABLE", "carbonate_content"
    )
    assert_missing(cn(cn_ratio=-1e-12), "NOT_COMPUTABLE", "cn_ratio")

    with pytest.raises(TypeError, match="modifiers"):
        rate(modifiers={1: 0.5})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="carbon_inputs"):
        humified(carbon_inputs={1: 1.0})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="rate_coefficient_per_unit"):
        one_step(rate_coefficient_per_unit=None)


# --- modifiers.py: f_CN clamp (D192/D199), temperature cut, overflow --------


def test_cn_ratio_modifier_d192_d199_no_output_clamping_and_symmetry():
    below = cn(cn_ratio=66.6 - 11.1)
    above = cn(cn_ratio=66.6 + 11.1)
    assert below == pytest.approx(above, rel=1e-15)
    assert below < 1.0

    # No upper clamp to 1.0 when negative sensitivity makes exp > 1 (OPEN 5).
    unclamped = cn(
        cn_ratio=77.7,
        optimum_cn_ratio=66.6,
        sensitivity_coefficient=-0.001,
        minimum=0.444,
    )
    expected = 0.444 + (1.0 - 0.444) * math.exp(0.001 * (77.7 - 66.6) ** 2)
    assert unclamped == pytest.approx(expected, rel=1e-15)
    assert unclamped > 1.0

    # Underflow to 0.0 when minimum == 0.0 stays a float 0.0, not NOT_COMPUTABLE.
    underflow = cn(
        cn_ratio=99.9,
        optimum_cn_ratio=66.6,
        sensitivity_coefficient=100.0,
        minimum=0.0,
    )
    assert underflow == 0.0 and isinstance(underflow, float)

    # Through run_amg: negative cn_ratio or minimum outside [0, 1] is refused, never clamped.
    data = forcing_data()
    data["soil_properties"][-1]["value"] = -1e-12
    step0 = run_amg(forcing(data), parameters=catalogue()).total_stock.steps[0]
    assert step0.value is None and step0.missing.reason == "MISSING_INPUT"
    assert "reason NOT_COMPUTABLE: cn_ratio is negative" in step0.missing.detail

    for bad_min in (-1e-12, 1.0 + 1e-12):
        params = catalogue_with("cn_ratio_minimum", {"value": bad_min})
        step0 = run_amg(forcing(), parameters=params).total_stock.steps[0]
        assert step0.value is None and step0.missing.reason == "MISSING_INPUT"
        assert (
            "reason NOT_COMPUTABLE: minimum is outside zero to one"
            in step0.missing.detail
        )


def test_entry_f_cn_matches_s13_not_max_clamp():
    # Distinguish S13 (minimum + (1 - minimum) * exp) from max(minimum, exp) through run_amg.
    data = forcing_data()
    # Set cn_ratio and sensitivity so 0 < exp(...) < minimum (0.333).
    data["soil_properties"][-1]["value"] = 11.1
    params = catalogue_with("cn_ratio_sensitivity", {"value": 0.001})
    balance = run_amg(forcing(data), parameters=params)

    # Independent hand-computed S13 vs wrong max-clamp.
    s13_fcn = 0.333 + (1.0 - 0.333) * math.exp(-0.001 * (11.1 - 55.5) ** 2)
    wrong_clamp_fcn = max(0.333, math.exp(-0.001 * (11.1 - 55.5) ** 2))
    assert s13_fcn != pytest.approx(wrong_clamp_fcn, rel=1e-6)

    # Compute expected step 0 active pool with S13 vs wrong clamp.
    k_s13 = (
        0.22
        * temperature_modifier(
            temperature=88.8,
            temperature_unit=unmark(DEGREE),
            reference_temperature=99.9,
            reference_temperature_unit=unmark(DEGREE),
            shape_coefficient=2.2,
            sensitivity_coefficient=0.11,
            sensitivity_coefficient_per_unit=unmark(DEGREE),
        )
        * moisture_modifier(
            water_balance=-22.2,
            water_balance_unit=unmark(DEPTH),
            shape_coefficient=0.33,
            sensitivity_coefficient=0.011,
            sensitivity_coefficient_per_unit=unmark(DEPTH),
        )
        * clay_modifier(
            clay_content=999.9,
            clay_content_unit=unmark(CONTENT),
            sensitivity_coefficient=0.0011,
            sensitivity_coefficient_per_unit=unmark(CONTENT),
        )
        * carbonate_modifier(
            carbonate_content=99.9,
            carbonate_content_unit=unmark(CONTENT),
            sensitivity_coefficient=0.0022,
            sensitivity_coefficient_per_unit=unmark(CONTENT),
        )
        * math.exp(-0.044 * (9.99 - 1.11) ** 2)
        * s13_fcn
    )
    active0 = balance.pools[0].initial.value
    inflow0 = balance.flows[0].steps[0].value
    expected_active1 = (
        active0 * math.exp(-k_s13) + inflow0 * (-math.expm1(-k_s13)) / k_s13
    )
    assert balance.pools[0].steps[0].value == pytest.approx(expected_active1, rel=1e-13)


def test_temperature_cut_boundary_moisture_denominator_and_rate_overflow():
    assert temperature(temperature=-1e-12) == 0.0
    assert temperature(temperature=0.0) == 0.0
    assert temperature(temperature=1e-12) > 0.0

    assert_missing(
        moisture(shape_coefficient=-1.0, water_balance=0.0),
        "NOT_COMPUTABLE",
        "moisture_modifier",
    )
    assert_missing(
        moisture(shape_coefficient=-2.0, water_balance=0.0),
        "NOT_COMPUTABLE",
        "negative",
    )
    assert_missing(
        rate(potential_rate=1e200, modifiers={"a": 1e200}),
        "NOT_COMPUTABLE",
        "rate_coefficient",
    )


# --- pools.py: explicit bound, small-x exponential, uniform forcing, run ----


def test_explicit_step_tight_boundary_and_overflow_checks():
    assert_missing(
        one_step(rate_coefficient=1.0 + 1e-12, duration=1.0, scheme="explicit"),
        "NOT_COMPUTABLE",
        "above one",
    )
    assert_missing(
        one_step(rate_coefficient=0.5, duration=2.0 + 1e-12, scheme="explicit"),
        "NOT_COMPUTABLE",
        "above one",
    )
    assert_missing(
        one_step(
            state=PoolState(active=1e308, stable=1e308),
            humified_input=0.0,
            rate_coefficient=0.0,
            duration=1.0,
            scheme="exponential",
        ),
        "NOT_COMPUTABLE",
        "step",
    )


def test_exponential_step_small_x_avoids_catastrophic_cancellation():
    # (1 - exp(-1e-16)) / 1e-16 gives ~1.1102 instead of 1.0; -expm1(-x)/x gives 1.0.
    result = one_step(
        state=PoolState(active=0.0, stable=22.2),
        humified_input=10.0,
        rate_coefficient=1e-16,
        duration=1.0,
        scheme="exponential",
    )
    assert result.end.active == pytest.approx(10.0, rel=1e-15)
    assert result.end.active <= 10.0
    assert result.mineralised >= 0.0


@pytest.mark.parametrize(
    "active, inflow, k, total_duration",
    [
        (44.4, 3.33, 0.222, 1.0),
        (0.0, 3.33, 0.222, 1.0),
        (44.4, 0.0, 0.222, 1.0),
        (44.4, 3.33, 0.0, 1.0),
        (44.4, 3.33, 0.222, 3.0),
    ],
)
def test_uniform_forcing_composition_checks_pools_and_cumulative_flows(
    active, inflow, k, total_duration
):
    init = PoolState(active=active, stable=22.2)
    one = a_run(
        [
            StepInput(
                humified_input=inflow,
                rate_coefficient=k,
                duration=total_duration,
            )
        ],
        scheme="exponential",
        initial_state=init,
    )
    for parts in (3, 12):
        cut = [
            StepInput(
                humified_input=inflow / parts,
                rate_coefficient=k,
                duration=total_duration / parts,
            )
        ] * parts
        many = a_run(cut, scheme="exponential", initial_state=init)
        assert many.steps[-1].end.active == pytest.approx(
            one.steps[-1].end.active, rel=1e-12, abs=1e-12
        )
        assert many.steps[-1].end.stable == one.steps[-1].end.stable
        assert many.steps[-1].end.total == pytest.approx(
            one.steps[-1].end.total, rel=1e-12, abs=1e-12
        )
        assert math.fsum(s.humified_input for s in many.steps) == pytest.approx(
            one.steps[0].humified_input, rel=1e-12, abs=1e-12
        )
        assert math.fsum(s.mineralised for s in many.steps) == pytest.approx(
            one.steps[0].mineralised, rel=1e-12, abs=1e-12
        )


def test_run_missing_propagation_elapsed_times_and_type_checks():
    with pytest.raises(TypeError, match="steps"):
        a_run("")
    with pytest.raises(TypeError, match="steps"):
        a_run(b"")
    with pytest.raises(TypeError, match="steps"):
        a_run("abc")
    with pytest.raises(TypeError, match="steps"):
        a_run(b"abc")

    assert_missing(
        one_step(state=ABSENT_INPUT), "MISSING_INPUT", "state", "NOT_DECLARED"
    )

    steps = [
        StepInput(humified_input=1.0, rate_coefficient=0.1, duration=1.0),
        StepInput(humified_input=1.0, rate_coefficient=0.1, duration=0.5),
        StepInput(humified_input=ABSENT_INPUT, rate_coefficient=0.1, duration=1.0),
        # A subsequent NOT_COMPUTABLE step must not overwrite the MISSING_INPUT cascade.
        StepInput(humified_input=1.0, rate_coefficient=0.1, duration=-1.0),
        StepInput(humified_input=1.0, rate_coefficient=0.1, duration=2.0),
    ]
    result = a_run(steps, scheme="exponential")
    assert_missing(result.steps[2], "MISSING_INPUT", "step 2", "humified_input")
    assert_missing(result.steps[3], "MISSING_INPUT", "step 3", "step 2")
    assert_missing(result.steps[4], "MISSING_INPUT", "step 4", "step 2")

    times = result.elapsed_times()
    assert times[:3] == (0.0, 1.0, 1.5)
    assert_missing(times[3], "MISSING_INPUT", "step 2", "humified_input")
    assert_missing(times[4], "MISSING_INPUT", "step 2", "humified_input")
    assert_missing(times[5], "MISSING_INPUT", "step 2", "humified_input")

    empty_missing = a_run([], initial_state=ABSENT_RESULT)
    assert empty_missing.total_stocks() == (ABSENT_RESULT,)
    assert empty_missing.elapsed_times() == (0.0,)


# --- trend.py: type checks, boundary guards, missing points, overflow -------


def test_trend_type_checks_and_boundary_validation():
    for bad in ("", b""):
        with pytest.raises(TypeError, match="stocks"):
            end_minus_start(stocks=bad, times=bad)
        with pytest.raises(TypeError, match="stocks"):
            fitted_slope(stocks=bad, times=bad)
        with pytest.raises(TypeError, match="stocks"):
            mean_over_cycles(stocks=bad, times=bad, cycle_boundaries=[0, 1])

    for bad_bounds in ("01", b"01", [False, True]):
        with pytest.raises(TypeError, match="cycle_boundaries"):
            mean_over_cycles(
                stocks=[10.0, 12.0], times=[0.0, 1.0], cycle_boundaries=bad_bounds
            )

    stocks = [10.0, 11.0, 12.0]
    times = [0.0, 1.0, 2.0]
    assert_missing(
        mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[-1, 1]),
        "NOT_COMPUTABLE",
        "outside",
    )
    assert_missing(
        mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 0]),
        "NOT_COMPUTABLE",
        "not after",
    )
    assert_missing(
        mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 1, 1]),
        "NOT_COMPUTABLE",
        "cycle boundary 1 is not after 1",
    )
    assert_missing(
        mean_over_cycles(
            stocks=stocks, times=[0.0, 1.0, 1.0], cycle_boundaries=[0, 1, 2]
        ),
        "NOT_COMPUTABLE",
        "times[2]",
        "not after",
    )
    assert_missing(
        mean_over_cycles(stocks=stocks, times=[1.0, 2.0, 0.5], cycle_boundaries=[0, 2]),
        "NOT_COMPUTABLE",
        "times[2]",
        "not after",
    )
    assert_missing(
        mean_over_cycles(
            stocks=stocks,
            times=times,
            cycle_boundaries=ResultMissing(reason="NOT_AVAILABLE", detail=None),
        ),
        "MISSING_INPUT",
        "cycle_boundaries",
        "NOT_AVAILABLE",
    )


def test_trend_missing_points_and_non_finite_measure_and_zero_duration_run():
    # Missing point strictly between cycle boundaries does not stop mean_over_cycles.
    assert (
        mean_over_cycles(
            stocks=[10.0, ABSENT_RESULT, 14.0],
            times=[0.0, 1.0, 2.0],
            cycle_boundaries=[0, 2],
        )
        == 2.0
    )
    # Missing point at an interior boundary makes mean_over_cycles missing.
    assert_missing(
        mean_over_cycles(
            stocks=[10.0, ABSENT_RESULT, 14.0],
            times=[0.0, 1.0, 2.0],
            cycle_boundaries=[0, 1, 2],
        ),
        "MISSING_INPUT",
        "stocks[1]",
    )
    # Missing middle point makes fitted_slope missing.
    assert_missing(
        fitted_slope(stocks=[10.0, ABSENT_RESULT, 14.0], times=[0.0, 1.0, 2.0]),
        "MISSING_INPUT",
        "stocks[1]",
    )

    assert_missing(
        end_minus_start(stocks=[0.0, 1e308], times=[0.0, 1e-10]),
        "NOT_COMPUTABLE",
        "end_minus_start",
    )
    assert_missing(
        fitted_slope(stocks=[0.0, 1.0], times=[0.0, 1e-200]),
        "NOT_COMPUTABLE",
        "fitted_slope",
    )
    assert_missing(
        mean_over_cycles(
            stocks=[0.0, 1e308], times=[0.0, 1e-10], cycle_boundaries=[0, 1]
        ),
        "NOT_COMPUTABLE",
        "mean_over_cycles",
    )

    zero_dt_run = a_run(
        [StepInput(humified_input=1.0, rate_coefficient=0.1, duration=0.0)]
    )
    measures = trend_measures(run=zero_dt_run, cycle_boundaries=[0, 1])
    assert_missing(measures.values["end_minus_start"], "NOT_COMPUTABLE", "not after")
    assert_missing(measures.values["fitted_slope"], "NOT_COMPUTABLE", "not after")
    assert_missing(measures.values["mean_over_cycles"], "NOT_COMPUTABLE", "not after")


# --- entry.py: D210 source prefixes, _steps bounds, catalogue, missing ------


def test_entry_d210_source_prefix_in_full_partial_and_initial_only_runs():
    opening = f"{METHOD_LABEL}; "
    balance = run_amg(forcing(), parameters=catalogue())

    # Derived initial source names starting_carbon and stable_fraction, nothing extra.
    for series in [balance.total_stock, *balance.pools]:
        src = series.initial.source
        assert src is not None and src.startswith(opening)
        assert "starting_state 'soil_organic_carbon'" in src
        assert f"'{PARAMETERS['stable_fraction'][0]}'" in src
        assert f"'{PARAMETERS['potential_rate'][0]}'" not in src

    # Simulated header source names all 7 forcing quantities and all 15 parameter IDs once.
    sim = balance.total_stock.source
    assert sim is not None and sim.startswith(opening)
    for part, quantity in FORCING_QUANTITIES.values():
        assert f"{part} '{quantity}'" in sim
    for pid, _ in PARAMETERS.values():
        assert sim.count(f"'{pid}'") == 1

    # Partial missing run: series headers keep source; missing trend rows have source None.
    data = forcing_data()
    data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [88.8, 99.9, None, 77.7]
    )
    partial = run_amg(forcing(data), parameters=catalogue())
    for series in [partial.total_stock, *partial.pools, *partial.flows]:
        assert series.provenance == "SIMULATED"
        assert series.source is not None and series.source.startswith(opening)
    for item in partial.soil_carbon_trend:
        assert item.value is None and item.source is None

    # Initial-only run: initial keeps D210 source; series headers and trends have source None.
    no_rate = catalogue_with("potential_rate", None)
    init_only = run_amg(forcing(), parameters=no_rate)
    for series in [init_only.total_stock, *init_only.pools]:
        assert series.initial.value is not None
        assert series.initial.source is not None
        assert series.initial.source.startswith(opening)
    for series in [init_only.total_stock, *init_only.pools, *init_only.flows]:
        assert series.provenance is None
        assert series.source is None
    for item in init_only.soil_carbon_trend:
        assert item.value is None and item.source is None


def test_entry_steps_horizon_boundaries():
    def run_horizon(start: tuple[int, int], end: tuple[int, int]):
        data = forcing_data()
        data["annual_climate"] = []
        data["annual_carbon_inputs"] = []
        data["horizon"] = {
            "start": {"year": start[0], "month": start[1]},
            "end": {"year": end[0], "month": end[1]},
        }
        return run_amg(forcing(data), parameters=catalogue()).total_stock.steps

    # Exactly 12 months: 1 whole step, no partial step.
    s12 = run_horizon((YEARS[0], 1), (YEARS[0], 12))
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in s12] == [
        (YEARS[0], 1, YEARS[0], 12)
    ]
    assert "not a whole agricultural year" not in s12[0].missing.detail

    # Exactly 11 months: 0 whole steps, 1 partial step.
    s11 = run_horizon((YEARS[0], 1), (YEARS[0], 11))
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in s11] == [
        (YEARS[0], 1, YEARS[0], 11)
    ]
    assert "not a whole agricultural year" in s11[0].missing.detail

    # Exactly 13 months: covered == end -> 1 whole step + 1 single-month partial step.
    s13 = run_horizon((YEARS[0], 1), (YEARS[0] + 1, 1))
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in s13] == [
        (YEARS[0], 1, YEARS[0], 12),
        (YEARS[0] + 1, 1, YEARS[0] + 1, 1),
    ]
    assert "step 0 is missing" in s13[1].missing.detail

    # Exactly 1 month: 1 partial step.
    s1 = run_horizon((YEARS[0], 1), (YEARS[0], 1))
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in s1] == [
        (YEARS[0], 1, YEARS[0], 1)
    ]
    assert "not a whole agricultural year" in s1[0].missing.detail

    # Non-January 12-month agricultural year.
    s_jul = run_horizon((YEARS[0], 7), (YEARS[0] + 1, 6))
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in s_jul] == [
        (YEARS[0], 7, YEARS[0] + 1, 6)
    ]
    assert "not a whole agricultural year" not in s_jul[0].missing.detail


def test_entry_catalogue_malformed_duplicate_and_bare_per_unit():
    # Malformed record in parameters blocks all lookups (F3c).
    malformed = catalogue()
    malformed["records/bad.json"] = {"value": 1.0}
    bal = run_amg(forcing(), parameters=malformed)
    assert bal.total_stock.initial.value is None
    assert bal.total_stock.initial.missing.reason == "MISSING_INPUT"
    assert "'records/bad.json'" in bal.total_stock.initial.missing.detail
    assert "F3c" in bal.total_stock.initial.missing.detail

    # Duplicate record sharing (id, scope).
    dup = catalogue()
    dup["records/stable_fraction_dup.json"] = copy.deepcopy(
        dup["records/stable_fraction.json"]
    )
    bal_dup = run_amg(forcing(), parameters=dup)
    assert bal_dup.total_stock.initial.value is None
    assert (
        "two records share this id and scope"
        in bal_dup.total_stock.initial.missing.detail
    )

    # Bare "-1" unit on a "per" parameter is refused as NOT_COMPUTABLE.
    bare_per = catalogue_with("clay_sensitivity", {"unit": "-1"})
    bal_per = run_amg(forcing(), parameters=bare_per)
    step0 = bal_per.total_stock.steps[0]
    assert step0.value is None
    assert "reason NOT_COMPUTABLE" in step0.missing.detail
    assert "written 'X-1'" in step0.missing.detail


def test_entry_missing_forcing_preserves_reason_and_cycles_names_missing_stock():
    # Missing ph / soil_cn_ratio with non-dimensionless unit keeps MISSING_INPUT, not unit error.
    for idx, qty in ((2, "ph"), (3, "soil_cn_ratio")):
        data = forcing_data()
        data["soil_properties"][idx] = {
            "quantity": qty,
            "value": None,
            "unit": unmark(CONTENT),
            "missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: absent {qty}"},
        }
        step0 = run_amg(forcing(data), parameters=catalogue()).total_stock.steps[0]
        assert step0.value is None and step0.missing.reason == "MISSING_INPUT"
        assert "reason NOT_AVAILABLE" in step0.missing.detail
        assert "not 'dimensionless'" not in step0.missing.detail

    # Present ph in wrong unit is NOT_COMPUTABLE.
    data_ph = forcing_data()
    data_ph["soil_properties"][2]["unit"] = unmark(CONTENT)
    step_ph = run_amg(forcing(data_ph), parameters=catalogue()).total_stock.steps[0]
    assert step_ph.value is None and "soil property 'ph'" in step_ph.missing.detail
    assert "reason NOT_COMPUTABLE" in step_ph.missing.detail

    # Missing annual carbon input value with wrong unit keeps MISSING_INPUT, not unit error.
    data_in = forcing_data()
    data_in["annual_carbon_inputs"][0] = annual(
        "placeholder_input_a",
        unmark(CONTENT),
        [None, 2.2, 0.0, 3.3],
        origin="test_origin_a",
    )
    step_in = run_amg(forcing(data_in), parameters=catalogue()).total_stock.steps[0]
    assert step_in.value is None and step_in.missing.reason == "MISSING_INPUT"
    assert "reason NO_COVERAGE" in step_in.missing.detail
    assert "converts nothing" not in step_in.missing.detail

    # Present starting_state item with value=None propagates MISSING_INPUT.
    data_st = forcing_data()
    data_st["starting_state"][0] = {
        "quantity": FORCING_QUANTITIES["starting_carbon"][1],
        "value": None,
        "unit": STOCK_UNIT,
        "missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: no starting stock"},
    }
    bal_st = run_amg(forcing(data_st), parameters=catalogue())
    assert bal_st.total_stock.initial.value is None
    assert bal_st.total_stock.initial.missing.reason == "MISSING_INPUT"
    assert "NOT_DECLARED" in bal_st.total_stock.initial.missing.detail
    # mean_over_cycles names BOTH cycle_boundaries AND the missing initial stock.
    cycles_st = bal_st.soil_carbon_trend[2]
    assert cycles_st.computation == "mean_over_cycles"
    assert "cycle_boundaries" in cycles_st.missing.detail
    assert "a stock is missing" in cycles_st.missing.detail

    # Missing water_balance year in middle of run propagates and is named by mean_over_cycles.
    data_wb = forcing_data()
    data_wb["annual_climate"][1] = annual(
        FORCING_QUANTITIES["water_balance"][1], unmark(DEPTH), [-22.2, 33.3, None, 11.1]
    )
    bal_wb = run_amg(forcing(data_wb), parameters=catalogue())
    assert [s.value is None for s in bal_wb.total_stock.steps] == [
        False,
        False,
        True,
        True,
    ]
    cycles_wb = bal_wb.soil_carbon_trend[2]
    assert cycles_wb.computation == "mean_over_cycles"
    assert "cycle_boundaries" in cycles_wb.missing.detail
    assert "a stock is missing, reason MISSING_INPUT" in cycles_wb.missing.detail
    assert "step 2" in cycles_wb.missing.detail
    # Check InputMissing directly in UNMARKED context as sanity.
    assert isinstance(InputMissing(reason="NOT_DECLARED"), InputMissing)
    assert isinstance(ResultMissing(reason="NOT_AVAILABLE"), ResultMissing)
    assert UNMARKED not in MARK
