"""Tests of engine/amg/: the PROPOSED cases listed in README.md.

Every constant in this file is a PLACEHOLDER: plainly not a real value of
any method. Repeated digits are used, or small whole numbers where the
arithmetic is done by hand. No case holds an expected value of the science.
The tests against a published worked example of AMG are the skipped tests at
the end.

Run from the repository root: ``python -m pytest engine/amg/``.
"""

from __future__ import annotations

import ast
import inspect
import math
import re
import sys
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import (
    DEFAULT_TREND_COMPUTATION,
    TREND_COMPUTATIONS,
)
from contracts.results.models import Missing as ResultMissing
from engine.amg import (
    SCHEMES,
    PoolState,
    Run,
    StepInput,
    StepResult,
    TrendMeasures,
    carbonate_modifier,
    clay_modifier,
    end_minus_start,
    fitted_slope,
    humified_input,
    initial_state,
    mean_over_cycles,
    moisture_modifier,
    ph_modifier,
    rate_coefficient,
    run,
    step,
    temperature_modifier,
    trend_measures,
)

HERE = Path(__file__).parent
README = HERE / "README.md"
MODULES = sorted(
    path for path in HERE.glob("*.py") if not path.name.startswith("test_")
)

# PLACEHOLDER unit strings: any text, the same text where two must agree.
TIME = "PLACEHOLDER_time"
DEGREE = "PLACEHOLDER_degree"
DEPTH = "PLACEHOLDER_depth"
CONTENT = "PLACEHOLDER_content"

ABSENT_INPUT = InputMissing(reason="NOT_DECLARED")
ABSENT_RESULT = ResultMissing(reason="NO_COVERAGE", detail="placeholder detail")
BOTH_SHAPES = [ABSENT_INPUT, ABSENT_RESULT]


# --- callers with PLACEHOLDER arguments --------------------------------------


def temperature(**changes):
    arguments = dict(
        temperature=11.1,
        temperature_unit=DEGREE,
        reference_temperature=22.2,
        reference_temperature_unit=DEGREE,
        shape_coefficient=3.33,
        sensitivity_coefficient=0.111,
        sensitivity_coefficient_per_unit=DEGREE,
    )
    return temperature_modifier(**{**arguments, **changes})


def moisture(**changes):
    arguments = dict(
        water_balance=-55.5,
        water_balance_unit=DEPTH,
        shape_coefficient=0.555,
        sensitivity_coefficient=0.0111,
        sensitivity_coefficient_per_unit=DEPTH,
    )
    return moisture_modifier(**{**arguments, **changes})


def clay(**changes):
    arguments = dict(
        clay_content=222.0,
        clay_content_unit=CONTENT,
        sensitivity_coefficient=0.00222,
        sensitivity_coefficient_per_unit=CONTENT,
    )
    return clay_modifier(**{**arguments, **changes})


def carbonate(**changes):
    arguments = dict(
        carbonate_content=33.3,
        carbonate_content_unit=CONTENT,
        sensitivity_coefficient=0.0333,
        sensitivity_coefficient_per_unit=CONTENT,
    )
    return carbonate_modifier(**{**arguments, **changes})


def ph(**changes):
    arguments = dict(ph=6.66, optimum_ph=7.77, sensitivity_coefficient=0.0777)
    return ph_modifier(**{**arguments, **changes})


def rate(**changes):
    arguments = dict(potential_rate=0.444, modifiers={"a": 0.555, "b": 0.666})
    return rate_coefficient(**{**arguments, **changes})


def humified(**changes):
    arguments = dict(
        carbon_inputs={"origin_a": 4.44, "origin_b": 5.55},
        humification_coefficients={"origin_a": 0.111, "origin_b": 0.222},
    )
    return humified_input(**{**arguments, **changes})


def initial(**changes):
    arguments = dict(total_carbon=66.6, stable_fraction=0.333)
    return initial_state(**{**arguments, **changes})


STATE = PoolState(active=44.4, stable=22.2)


def one_step(**changes):
    arguments = dict(
        state=STATE,
        humified_input=3.33,
        rate_coefficient=0.111,
        rate_coefficient_per_unit=TIME,
        duration=1.0,
        duration_unit=TIME,
        scheme="explicit",
    )
    return step(**{**arguments, **changes})


def a_run(steps, scheme="explicit", initial_state=STATE):
    return run(
        initial_state=initial_state,
        steps=steps,
        rate_coefficient_per_unit=TIME,
        duration_unit=TIME,
        scheme=scheme,
    )


def varied_steps(count):
    """A long PLACEHOLDER series: inputs, rates and lengths that change from step to step."""
    inputs = [0.0, 1.11, 2.22, 3.33, 0.555]
    rates = [0.0, 0.0111, 0.111, 0.555, 0.222, 0.999]
    lengths = [1.0, 0.5, 0.25]
    return [
        StepInput(
            humified_input=inputs[i % len(inputs)],
            rate_coefficient=rates[i % len(rates)],
            duration=lengths[i % len(lengths)],
        )
        for i in range(count)
    ]


def assert_missing(result, reason, *words):
    assert isinstance(result, ResultMissing), result
    assert result.reason == reason, result
    for word in words:
        assert word in (result.detail or ""), (word, result.detail)


# --- humified input and initial state -----------------------------------------


def test_humified_input_is_the_sum_of_inputs_times_their_coefficients():
    assert humified() == pytest.approx(4.44 * 0.111 + 5.55 * 0.222, rel=1e-15)
    # A coefficient of an origin that is not an input is not used.
    extra = {"origin_a": 0.111, "origin_b": 0.222, "origin_c": 0.999}
    assert humified(humification_coefficients=extra) == humified()
    assert humified(carbon_inputs={"origin_a": 0.0}) == 0.0


def test_humified_input_without_a_coefficient_for_an_origin_is_missing_and_names_it():
    result = humified(humification_coefficients={"origin_a": 0.111})
    assert_missing(result, "MISSING_INPUT", "origin_b")
    for shape in BOTH_SHAPES:
        result = humified(
            humification_coefficients={"origin_a": 0.111, "origin_b": shape}
        )
        assert_missing(result, "MISSING_INPUT", "origin_b", shape.reason)


@pytest.mark.parametrize("coefficient", [-0.111, -1e-12, 1.0 + 1e-12, 1.11])
def test_humified_input_coefficient_outside_zero_to_one_is_refused(coefficient):
    result = humified(
        humification_coefficients={"origin_a": coefficient, "origin_b": 0.222}
    )
    assert_missing(result, "NOT_COMPUTABLE", "origin_a", "outside zero to one")
    assert "origin_b" not in result.detail
    for bound in (0.0, 1.0):
        assert isinstance(
            humified(humification_coefficients={"origin_a": bound, "origin_b": bound}),
            float,
        )


def test_humified_input_negative_input_is_refused():
    result = humified(carbon_inputs={"origin_a": -4.44, "origin_b": 5.55})
    assert_missing(result, "NOT_COMPUTABLE", "origin_a", "negative")


def test_humified_input_with_no_origin_is_not_computed():
    assert_missing(humified(carbon_inputs={}), "NOT_COMPUTABLE", "empty")


def test_initial_state_splits_total_carbon_by_the_stable_fraction():
    state = initial()
    assert state.stable == pytest.approx(0.333 * 66.6, rel=1e-15)
    assert state.active == pytest.approx(66.6 - 0.333 * 66.6, rel=1e-15)
    assert state.total == pytest.approx(66.6, rel=1e-15)
    assert initial(stable_fraction=0.0).stable == 0.0
    assert initial(stable_fraction=1.0).active == 0.0


def test_initial_state_refuses_negative_carbon_or_fraction_outside_zero_to_one():
    assert_missing(initial(total_carbon=-66.6), "NOT_COMPUTABLE", "total_carbon")
    for fraction in (-0.333, -1e-12, 1.0 + 1e-12, 1.33):
        assert_missing(
            initial(stable_fraction=fraction), "NOT_COMPUTABLE", "stable_fraction"
        )


# --- one step -------------------------------------------------------------------


def test_explicit_step_follows_the_proposed_form():
    for k, dt, inflow in [
        (0.111, 1.0, 3.33),
        (0.555, 0.5, 0.0),
        (0.0, 1.0, 2.22),
        (1.0, 1.0, 1.11),
    ]:
        result = one_step(rate_coefficient=k, duration=dt, humified_input=inflow)
        mineralised = k * dt * STATE.active
        assert result.mineralised == pytest.approx(mineralised, rel=1e-15)
        assert result.end.active == pytest.approx(
            STATE.active + inflow - mineralised, rel=1e-15
        )
        assert result.start == STATE
        assert result.duration == dt
        assert result.humified_input == inflow


def test_exponential_step_follows_the_proposed_form():
    for k, dt, inflow in [(0.111, 1.0, 3.33), (0.555, 0.5, 0.0), (2.22, 1.0, 1.11)]:
        result = one_step(
            rate_coefficient=k, duration=dt, humified_input=inflow, scheme="exponential"
        )
        x = k * dt
        expected = STATE.active * math.exp(-x) + inflow * (1 - math.exp(-x)) / x
        assert result.end.active == pytest.approx(expected, rel=1e-12)
        assert result.mineralised == pytest.approx(
            STATE.active + inflow - expected, rel=1e-12
        )


def test_exponential_step_with_no_mineralisation_adds_the_input():
    for k, dt in [(0.0, 1.0), (0.111, 0.0)]:
        result = one_step(rate_coefficient=k, duration=dt, scheme="exponential")
        assert result.end.active == STATE.active + 3.33
        assert result.mineralised == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("scheme", SCHEMES)
def test_step_keeps_the_stable_pool(scheme):
    for k in (0.0, 0.111, 0.999):
        assert one_step(rate_coefficient=k, scheme=scheme).end.stable == STATE.stable


@pytest.mark.parametrize("scheme", SCHEMES)
def test_step_mass_balance_holds_for_each_scheme(scheme):
    for item in varied_steps(30):
        result = one_step(
            humified_input=item.humified_input,
            rate_coefficient=item.rate_coefficient,
            duration=item.duration,
            scheme=scheme,
        )
        change = result.end.total - result.start.total
        assert change == pytest.approx(
            result.humified_input - result.mineralised, abs=1e-12
        )
        assert result.mineralised >= 0


def test_explicit_step_refuses_more_mineralisation_than_the_active_pool_holds():
    assert_missing(
        one_step(rate_coefficient=1.11, duration=1.0), "NOT_COMPUTABLE", "above one"
    )
    assert_missing(
        one_step(rate_coefficient=0.555, duration=2.22), "NOT_COMPUTABLE", "above one"
    )
    # The exponential scheme never takes more than the pool holds.
    result = one_step(rate_coefficient=5.55, duration=2.22, scheme="exponential")
    assert result.end.active >= 0


@pytest.mark.parametrize(
    "name, changes",
    [
        ("humified_input", {"humified_input": -3.33}),
        ("rate_coefficient", {"rate_coefficient": -0.111}),
        ("duration", {"duration": -1.0}),
        ("state.active", {"state": PoolState(active=-44.4, stable=22.2)}),
        ("state.stable", {"state": PoolState(active=44.4, stable=-22.2)}),
    ],
)
@pytest.mark.parametrize("scheme", SCHEMES)
def test_step_negative_value_is_refused_and_named(name, changes, scheme):
    assert_missing(
        one_step(scheme=scheme, **changes), "NOT_COMPUTABLE", name, "negative"
    )


def test_step_units_that_differ_are_not_computed():
    result = one_step(duration_unit="PLACEHOLDER_other_time")
    assert_missing(result, "NOT_COMPUTABLE", TIME, "PLACEHOLDER_other_time")


@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_step_missing_state_or_argument_gives_missing_input(shape):
    if isinstance(shape, ResultMissing):
        assert_missing(one_step(state=shape), "MISSING_INPUT", "state", shape.reason)
    for name in ("humified_input", "rate_coefficient", "duration"):
        assert_missing(one_step(**{name: shape}), "MISSING_INPUT", name, shape.reason)


def test_step_unknown_scheme_raises_value_error():
    with pytest.raises(ValueError, match="scheme"):
        one_step(scheme="PLACEHOLDER_scheme")
    with pytest.raises(ValueError, match="scheme"):
        a_run([], scheme="PLACEHOLDER_scheme")


# --- modifiers and the rate coefficient ---------------------------------------


def test_temperature_modifier_follows_the_proposed_form():
    for t in (-11.1, 0.0, 11.1, 22.2, 33.3):
        expected = 3.33 / (1 + (3.33 - 1) * math.exp(0.111 * (22.2 - t)))
        assert temperature(temperature=t) == pytest.approx(expected, rel=1e-15)


def test_temperature_modifier_is_one_at_the_reference_temperature():
    for shape, sensitivity in [(3.33, 0.111), (5.55, 0.0555), (1.0, 0.999)]:
        result = temperature(
            temperature=22.2,
            shape_coefficient=shape,
            sensitivity_coefficient=sensitivity,
        )
        assert result == pytest.approx(1.0, rel=1e-15)


def test_moisture_modifier_follows_the_proposed_form():
    for w in (-55.5, 0.0, 55.5):
        expected = 1 / (1 + 0.555 * math.exp(-0.0111 * w))
        assert moisture(water_balance=w) == pytest.approx(expected, rel=1e-15)


def test_clay_modifier_follows_the_proposed_form():
    for content in (0.0, 111.0, 222.0):
        expected = math.exp(-0.00222 * content)
        assert clay(clay_content=content) == pytest.approx(expected, rel=1e-15)
    assert clay(clay_content=0.0) == 1.0


def test_carbonate_modifier_follows_the_proposed_form():
    for content in (0.0, 33.3, 66.6):
        expected = 1 / (1 + 0.0333 * content)
        assert carbonate(carbonate_content=content) == pytest.approx(
            expected, rel=1e-15
        )
    assert carbonate(carbonate_content=0.0) == 1.0


def test_ph_modifier_follows_the_proposed_form():
    for value in (5.55, 6.66, 7.77, 8.88):
        expected = math.exp(-0.0777 * (value - 7.77) ** 2)
        assert ph(ph=value) == pytest.approx(expected, rel=1e-15)
    assert ph(ph=7.77) == 1.0


def test_modifier_negative_content_is_refused():
    assert_missing(
        clay(clay_content=-222.0), "NOT_COMPUTABLE", "clay_content", "negative"
    )
    assert_missing(carbonate(carbonate_content=-33.3), "NOT_COMPUTABLE", "carbonate_content", "negative")  # fmt: skip


def test_modifier_that_the_form_makes_negative_or_not_finite_is_not_computed():
    # A shape below one makes the denominator negative far below the reference.
    assert_missing(temperature(shape_coefficient=0.5, temperature=-111.0), "NOT_COMPUTABLE", "temperature_modifier")  # fmt: skip
    # A negative sensitivity that cancels the denominator, or overflows the exponential.
    assert_missing(carbonate(sensitivity_coefficient=-1.0, carbonate_content=1.0), "NOT_COMPUTABLE", "carbonate_modifier")  # fmt: skip
    assert_missing(carbonate(sensitivity_coefficient=-1.0, carbonate_content=2.0), "NOT_COMPUTABLE", "negative")  # fmt: skip
    assert_missing(clay(sensitivity_coefficient=-1e3, clay_content=1e3), "NOT_COMPUTABLE", "clay_modifier")  # fmt: skip
    assert_missing(moisture(sensitivity_coefficient=1e3, water_balance=-1e3), "NOT_COMPUTABLE", "moisture_modifier")  # fmt: skip


@pytest.mark.parametrize(
    "call, unit_argument",
    [
        (temperature, "temperature_unit"),
        (temperature, "reference_temperature_unit"),
        (temperature, "sensitivity_coefficient_per_unit"),
        (moisture, "water_balance_unit"),
        (moisture, "sensitivity_coefficient_per_unit"),
        (clay, "clay_content_unit"),
        (clay, "sensitivity_coefficient_per_unit"),
        (carbonate, "carbonate_content_unit"),
        (carbonate, "sensitivity_coefficient_per_unit"),
    ],
)
def test_modifier_units_that_differ_are_not_computed(call, unit_argument):
    result = call(**{unit_argument: "PLACEHOLDER_other_unit"})
    assert_missing(result, "NOT_COMPUTABLE", "PLACEHOLDER_other_unit")


def test_rate_coefficient_is_the_potential_rate_times_the_modifiers():
    assert rate() == pytest.approx(0.444 * 0.555 * 0.666, rel=1e-15)
    assert rate(modifiers={}) == 0.444
    assert rate(modifiers={"a": 0.0}) == 0.0
    # Each modifier function feeds it.
    modifiers = {"temperature": temperature(), "moisture": moisture(), "clay": clay(), "carbonate": carbonate(), "ph": ph()}  # fmt: skip
    expected = 0.444 * math.prod(modifiers.values())
    assert rate(modifiers=modifiers) == pytest.approx(expected, rel=1e-14)


def test_rate_coefficient_missing_or_negative_modifier_is_not_computed():
    for shape in BOTH_SHAPES:
        assert_missing(
            rate(modifiers={"a": 0.555, "b": shape}),
            "MISSING_INPUT",
            "'b'",
            shape.reason,
        )
        assert_missing(rate(potential_rate=shape), "MISSING_INPUT", "potential_rate")
    assert_missing(rate(modifiers={"a": -0.555}), "NOT_COMPUTABLE", "'a'", "negative")
    assert_missing(
        rate(potential_rate=-0.444), "NOT_COMPUTABLE", "potential_rate", "negative"
    )
    # A modifier the function refused arrives missing and keeps the rate missing.
    refused = clay(clay_content=-1.0)
    assert_missing(
        rate(modifiers={"clay": refused}), "MISSING_INPUT", "clay", "NOT_COMPUTABLE"
    )


# --- a run over steps -----------------------------------------------------------


@pytest.mark.parametrize("scheme", SCHEMES)
def test_run_equals_steps_applied_one_after_another(scheme):
    steps = varied_steps(12)
    result = a_run(steps, scheme=scheme)
    state = STATE
    for item, computed in zip(steps, result.steps, strict=True):
        expected = one_step(
            state=state,
            humified_input=item.humified_input,
            rate_coefficient=item.rate_coefficient,
            duration=item.duration,
            scheme=scheme,
        )
        assert computed == expected
        state = expected.end
    assert result.initial_state == STATE
    assert result.duration_unit == TIME


@pytest.mark.parametrize("scheme", SCHEMES)
def test_run_mass_balance_holds_at_every_step_over_a_long_series(scheme):
    result = a_run(varied_steps(3000), scheme=scheme)
    for item in result.steps:
        assert isinstance(item, StepResult)
        change = item.end.total - item.start.total
        assert change == pytest.approx(
            item.humified_input - item.mineralised, abs=1e-12
        )
    inflow = math.fsum(item.humified_input for item in result.steps)
    outflow = math.fsum(item.mineralised for item in result.steps)
    total_change = result.steps[-1].end.total - STATE.total
    assert total_change == pytest.approx(inflow - outflow, abs=1e-9)


@pytest.mark.parametrize("scheme", SCHEMES)
def test_run_with_zero_inputs_active_pool_only_decreases_and_stable_pool_does_not_change(
    scheme,
):
    steps = [
        StepInput(humified_input=0.0, rate_coefficient=0.111, duration=1.0)
        for _ in range(200)
    ]
    result = a_run(steps, scheme=scheme)
    previous = STATE.active
    for item in result.steps:
        assert item.end.active < previous
        assert item.end.active >= 0
        assert item.end.stable == STATE.stable
        previous = item.end.active


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("start", [0.0, 99.9])
def test_run_with_constant_inputs_approaches_the_steady_state_of_the_form(
    scheme, start
):
    inflow, k, dt = 3.33, 0.111, 1.0
    steady = inflow / (k * dt)  # the fixed point of both PROPOSED schemes
    steps = [
        StepInput(humified_input=inflow, rate_coefficient=k, duration=dt)
        for _ in range(600)
    ]
    result = a_run(
        steps, scheme=scheme, initial_state=PoolState(active=start, stable=22.2)
    )
    distances = [abs(item.end.active - steady) for item in result.steps]
    assert all(later <= earlier for earlier, later in zip(distances, distances[1:]))
    assert result.steps[-1].end.active == pytest.approx(steady, rel=1e-9)
    assert result.steps[-1].end.stable == 22.2


def test_exponential_steps_compose_under_uniform_forcing():
    # Blueprint section 8: an annual and a monthly variant are checked against
    # each other under uniform forcing. With the exponential scheme, one step
    # and the same span cut into equal steps, the input spread evenly, agree.
    inflow, k = 3.33, 0.222
    one = a_run([StepInput(humified_input=inflow, rate_coefficient=k, duration=1.0)], "exponential")  # fmt: skip
    for parts in (2, 4, 5):
        cut = [StepInput(humified_input=inflow / parts, rate_coefficient=k, duration=1.0 / parts)] * parts  # fmt: skip
        many = a_run(cut, "exponential")
        assert many.steps[-1].end.active == pytest.approx(
            one.steps[-1].end.active, rel=1e-12
        )
    # The explicit scheme does not: the two differ for a rate above zero.
    explicit_one = a_run(
        [StepInput(humified_input=inflow, rate_coefficient=k, duration=1.0)]
    )
    explicit_cut = a_run([StepInput(humified_input=inflow / 4, rate_coefficient=k, duration=0.25)] * 4)  # fmt: skip
    assert explicit_cut.steps[-1].end.active != pytest.approx(explicit_one.steps[-1].end.active, rel=1e-6)  # fmt: skip


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_run_missing_step_input_makes_that_step_and_every_later_step_missing(
    scheme, shape
):
    for name in ("humified_input", "rate_coefficient", "duration"):
        steps = varied_steps(8)
        old = steps[3]
        steps[3] = StepInput(**{**old.__dict__, name: shape})
        result = a_run(steps, scheme=scheme)
        assert all(isinstance(item, StepResult) for item in result.steps[:3])
        assert_missing(result.steps[3], "MISSING_INPUT", "step 3", name, shape.reason)
        for position in range(4, 8):
            assert_missing(result.steps[position], "MISSING_INPUT", f"step {position}", "step 3", name)  # fmt: skip
        stocks = result.total_stocks()
        assert all(isinstance(item, float) for item in stocks[:4])
        assert all(isinstance(item, ResultMissing) for item in stocks[4:])


@pytest.mark.parametrize("scheme", SCHEMES)
def test_run_refused_step_input_is_never_clipped(scheme):
    for name, value in [("humified_input", -1.11), ("rate_coefficient", -0.111), ("duration", math.nan)]:  # fmt: skip
        steps = varied_steps(6)
        steps[2] = StepInput(**{**steps[2].__dict__, name: value})
        result = a_run(steps, scheme=scheme)
        assert_missing(result.steps[2], "NOT_COMPUTABLE", "step 2", name)
        for position in range(3, 6):
            assert_missing(
                result.steps[position], "MISSING_INPUT", "step 2", "NOT_COMPUTABLE"
            )


@pytest.mark.parametrize("shape", [ABSENT_RESULT, ResultMissing(reason="NOT_DECLARED")])
def test_run_missing_initial_state_makes_every_step_missing(shape):
    result = a_run(varied_steps(4), initial_state=shape)
    for item in result.steps:
        assert_missing(item, "MISSING_INPUT", "initial state", shape.reason)
    assert all(isinstance(item, ResultMissing) for item in result.total_stocks())
    # A refused initial state passed on as a run's start is missing too.
    refused = initial(stable_fraction=1.5)
    assert_missing(a_run(varied_steps(1), initial_state=refused).steps[0], "MISSING_INPUT", "NOT_COMPUTABLE")  # fmt: skip


def test_run_elapsed_times_and_total_stocks():
    steps = [StepInput(humified_input=1.11, rate_coefficient=0.111, duration=d) for d in (1.0, 0.5, 0.25)]  # fmt: skip
    result = a_run(steps)
    assert result.elapsed_times() == (0.0, 1.0, 1.5, 1.75)
    stocks = result.total_stocks()
    assert stocks[0] == STATE.total
    assert stocks[1:] == tuple(item.end.total for item in result.steps)
    assert a_run([]).total_stocks() == (STATE.total,)
    assert a_run([]).elapsed_times() == (0.0,)


# --- trend measures of C1.6 -----------------------------------------------------


def test_end_minus_start_is_the_change_over_the_horizon_per_unit_time():
    assert end_minus_start(stocks=[10.0, 7.0, 13.0], times=[0.0, 1.0, 2.0]) == 1.5
    assert end_minus_start(stocks=[10.0, 13.0, 4.0], times=[1.0, 2.0, 4.0]) == -2.0
    # Only the two ends are needed: a missing middle point does not stop it.
    assert (
        end_minus_start(stocks=[10.0, ABSENT_RESULT, 13.0], times=[0.0, 1.0, 2.0])
        == 1.5
    )


def test_fitted_slope_recovers_the_slope_of_a_straight_line():
    times = [0.0, 1.0, 2.5, 4.0]
    assert fitted_slope(stocks=[5.0 + 2.5 * t for t in times], times=times) == pytest.approx(2.5, rel=1e-14)  # fmt: skip
    # Worked by hand: mean time 1.5, mean stock 1; 4 / 5.
    assert fitted_slope(stocks=[0.0, 1.0, 0.0, 3.0], times=[0.0, 1.0, 2.0, 3.0]) == pytest.approx(0.8, rel=1e-14)  # fmt: skip


def test_mean_over_cycles_is_the_mean_change_per_unit_time_of_the_whole_cycles():
    stocks = [10.0, 12.0, 11.0, 14.0, 13.0]
    times = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert (
        mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 2, 4]) == 0.75
    )
    assert mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 1, 4]) == pytest.approx((2.0 + 1.0 / 3.0) / 2, rel=1e-14)  # fmt: skip
    # Points after the last whole cycle are not used.
    assert mean_over_cycles(stocks=stocks + [ABSENT_RESULT], times=times + [5.0], cycle_boundaries=[0, 2, 4]) == 0.75  # fmt: skip


@pytest.mark.parametrize("scheme", SCHEMES)
def test_trend_measures_name_the_three_computations_of_c16(scheme):
    result = a_run(varied_steps(9), scheme=scheme)
    measures = trend_measures(run=result, cycle_boundaries=[0, 3, 6, 9])
    assert isinstance(measures, TrendMeasures)
    assert tuple(measures.values) == TREND_COMPUTATIONS
    assert DEFAULT_TREND_COMPUTATION in measures.values
    assert measures.time_unit == TIME
    stocks, times = result.total_stocks(), result.elapsed_times()
    assert measures.values["end_minus_start"] == end_minus_start(
        stocks=stocks, times=times
    )
    assert measures.values["fitted_slope"] == fitted_slope(stocks=stocks, times=times)
    assert measures.values["mean_over_cycles"] == mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 3, 6, 9])  # fmt: skip
    assert all(isinstance(value, float) for value in measures.values.values())


def test_trend_of_a_run_with_a_missing_step_is_missing_with_its_reason():
    steps = varied_steps(6)
    steps[4] = StepInput(**{**steps[4].__dict__, "humified_input": ABSENT_INPUT})
    measures = trend_measures(run=a_run(steps), cycle_boundaries=[0, 3, 6])
    assert tuple(measures.values) == TREND_COMPUTATIONS
    for value in measures.values.values():
        assert_missing(value, "MISSING_INPUT", "stocks[6]", "step 4", "NOT_DECLARED")
    assert_missing(measures.values["fitted_slope"], "MISSING_INPUT", "stocks[5]")


def test_mean_over_cycles_without_whole_cycle_or_boundaries_is_missing_with_reason():
    stocks, times = [10.0, 11.0, 12.0], [0.0, 1.0, 2.0]
    for shape in BOTH_SHAPES:
        assert_missing(mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=shape), "MISSING_INPUT", "cycle_boundaries", shape.reason)  # fmt: skip
    for boundaries in ([], [0]):
        assert_missing(mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=boundaries), "NOT_COMPUTABLE", "no whole cycle")  # fmt: skip
    assert_missing(mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[0, 3]), "NOT_COMPUTABLE", "outside")  # fmt: skip
    assert_missing(mean_over_cycles(stocks=stocks, times=times, cycle_boundaries=[2, 0]), "NOT_COMPUTABLE", "not after")  # fmt: skip
    measures = trend_measures(
        run=a_run(varied_steps(2)), cycle_boundaries=ABSENT_RESULT
    )
    assert_missing(
        measures.values["mean_over_cycles"], "MISSING_INPUT", "cycle_boundaries"
    )
    assert isinstance(measures.values["end_minus_start"], float)


def test_trend_without_a_span_of_time_is_not_computed():
    for function in (end_minus_start, fitted_slope):
        assert_missing(function(stocks=[10.0], times=[0.0]), "NOT_COMPUTABLE", "fewer than two points")  # fmt: skip
        assert_missing(
            function(stocks=[], times=[]), "NOT_COMPUTABLE", "fewer than two points"
        )
        assert_missing(function(stocks=[10.0, 11.0], times=[1.0, 1.0]), "NOT_COMPUTABLE", "not after")  # fmt: skip
        assert_missing(function(stocks=[10.0, 11.0], times=[2.0, 1.0]), "NOT_COMPUTABLE", "not after")  # fmt: skip
    assert_missing(fitted_slope(stocks=[1.0, 2.0, 3.0], times=[0.0, 2.0, 1.0]), "NOT_COMPUTABLE", "times[2]")  # fmt: skip
    measures = trend_measures(run=a_run([]), cycle_boundaries=[0])
    for value in measures.values.values():
        assert value.reason == "NOT_COMPUTABLE"
    with pytest.raises(ValueError, match="one item each"):
        end_minus_start(stocks=[1.0, 2.0], times=[0.0])


# --- every number argument ------------------------------------------------------

NUMBER_ARGUMENTS = [
    (temperature, "temperature"),
    (temperature, "reference_temperature"),
    (temperature, "shape_coefficient"),
    (temperature, "sensitivity_coefficient"),
    (moisture, "water_balance"),
    (moisture, "shape_coefficient"),
    (moisture, "sensitivity_coefficient"),
    (clay, "clay_content"),
    (clay, "sensitivity_coefficient"),
    (carbonate, "carbonate_content"),
    (carbonate, "sensitivity_coefficient"),
    (ph, "ph"),
    (ph, "optimum_ph"),
    (ph, "sensitivity_coefficient"),
    (rate, "potential_rate"),
    (initial, "total_carbon"),
    (initial, "stable_fraction"),
    (one_step, "humified_input"),
    (one_step, "rate_coefficient"),
    (one_step, "duration"),
]
NOT_FINITE = [math.nan, math.inf, -math.inf, 10**400]


@pytest.mark.parametrize("call, name", NUMBER_ARGUMENTS)
@pytest.mark.parametrize("value", NOT_FINITE)
def test_argument_that_is_not_finite_is_not_computed(call, name, value):
    assert_missing(call(**{name: value}), "NOT_COMPUTABLE", name, "not a finite number")


@pytest.mark.parametrize("value", NOT_FINITE)
def test_items_that_are_not_finite_are_not_computed(value):
    assert_missing(rate(modifiers={"a": value}), "NOT_COMPUTABLE", "'a'")
    assert_missing(humified(carbon_inputs={"origin_a": value, "origin_b": 1.0}), "NOT_COMPUTABLE", "origin_a")  # fmt: skip
    assert_missing(humified(humification_coefficients={"origin_a": value, "origin_b": 0.1}), "NOT_COMPUTABLE", "origin_a")  # fmt: skip
    assert_missing(one_step(state=PoolState(active=value, stable=1.0)), "NOT_COMPUTABLE", "state.active")  # fmt: skip
    for function in (end_minus_start, fitted_slope):
        assert_missing(function(stocks=[1.0, value], times=[0.0, 1.0]), "NOT_COMPUTABLE", "stocks[1]")  # fmt: skip
        assert_missing(function(stocks=[1.0, 2.0], times=[0.0, value]), "NOT_COMPUTABLE", "times[1]")  # fmt: skip
    assert_missing(mean_over_cycles(stocks=[1.0, value], times=[0.0, 1.0], cycle_boundaries=[0, 1]), "NOT_COMPUTABLE", "stocks[1]")  # fmt: skip


@pytest.mark.parametrize("call, name", NUMBER_ARGUMENTS)
@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_missing_argument_gives_missing_input_that_names_it(call, name, shape):
    assert_missing(call(**{name: shape}), "MISSING_INPUT", name, shape.reason)


@pytest.mark.parametrize("call, name", NUMBER_ARGUMENTS)
@pytest.mark.parametrize("value", [None, "1.0", True, [1.0]])
def test_argument_of_another_type_raises_type_error(call, name, value):
    with pytest.raises(TypeError, match=re.escape(name)):
        call(**{name: value})


def test_structured_argument_of_another_type_raises_type_error():
    with pytest.raises(TypeError, match="modifiers"):
        rate(modifiers=[0.5])
    with pytest.raises(TypeError, match="carbon_inputs"):
        humified(carbon_inputs=None)
    with pytest.raises(TypeError, match="humification_coefficients"):
        humified(humification_coefficients={1: 0.5})
    with pytest.raises(TypeError, match="state"):
        one_step(state=(44.4, 22.2))
    with pytest.raises(TypeError, match="state.active"):
        one_step(state=PoolState(active=None, stable=22.2))
    with pytest.raises(TypeError, match="steps"):
        a_run(None)
    with pytest.raises(TypeError, match=re.escape("steps[0]")):
        a_run([(1.0, 0.1, 1.0)])
    with pytest.raises(TypeError, match=re.escape("steps[0].duration")):
        a_run([StepInput(humified_input=1.0, rate_coefficient=0.1, duration=None)])
    with pytest.raises(TypeError, match="duration_unit"):
        one_step(duration_unit=None)
    with pytest.raises(TypeError, match="temperature_unit"):
        temperature(temperature_unit=None)
    with pytest.raises(TypeError, match="scheme"):
        one_step(scheme=None)
    with pytest.raises(TypeError, match="stocks"):
        end_minus_start(stocks=None, times=[0.0])
    with pytest.raises(TypeError, match="cycle_boundaries"):
        mean_over_cycles(
            stocks=[1.0, 2.0], times=[0.0, 1.0], cycle_boundaries=[0.0, 1.0]
        )
    with pytest.raises(TypeError, match="run"):
        trend_measures(run=None, cycle_boundaries=[0, 1])


# --- no constant of the method in the modules ----------------------------------

PUBLIC_FUNCTIONS = [
    temperature_modifier,
    moisture_modifier,
    clay_modifier,
    carbonate_modifier,
    ph_modifier,
    rate_coefficient,
    humified_input,
    initial_state,
    step,
    run,
    end_minus_start,
    fitted_slope,
    mean_over_cycles,
    trend_measures,
]


def test_every_argument_is_passed_by_name_and_none_has_a_default():
    for function in PUBLIC_FUNCTIONS:
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
                function,
                parameter,
            )
            assert parameter.default is inspect.Parameter.empty, (function, parameter)
    for model in (PoolState, StepInput, StepResult, Run, TrendMeasures):
        for parameter in inspect.signature(model).parameters.values():
            assert parameter.default is inspect.Parameter.empty, (model, parameter)


def test_the_modules_hold_no_number_but_zero_and_one():
    assert MODULES, "no module found"
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        numbers = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float, complex))
            and not isinstance(node.value, bool)
        }
        assert numbers <= {0, 1}, (path.name, numbers)


def test_no_entry_point_yet():
    import engine.amg

    assert not hasattr(engine.amg, "run_amg"), "EP5 is OPEN in contracts/ENTRYPOINTS.md"


# --- README.md -------------------------------------------------------------------

CONSTANTS = {
    "humified_input.humification_coefficients",
    "initial_state.stable_fraction",
    "rate_coefficient.potential_rate",
    "temperature_modifier.reference_temperature",
    "temperature_modifier.shape_coefficient",
    "temperature_modifier.sensitivity_coefficient",
    "moisture_modifier.shape_coefficient",
    "moisture_modifier.sensitivity_coefficient",
    "clay_modifier.sensitivity_coefficient",
    "carbonate_modifier.sensitivity_coefficient",
    "ph_modifier.optimum_ph",
    "ph_modifier.sensitivity_coefficient",
}


def section(title):
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def table_rows(text):
    lines = [line for line in text.splitlines() if line.startswith("|")]
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines
    ]


def test_readme_lists_every_constant_with_an_empty_value():
    rows = table_rows(section("Constants a person has to transcribe"))
    header, body = rows[0], rows[2:]
    assert header[0] == "Constant"
    assert header[-1] == "Value"
    assert all(len(row) == len(header) for row in body)
    assert {row[0].strip("`") for row in body} == CONSTANTS
    for row in body:
        function, argument = row[0].strip("`").split(".")
        assert argument in inspect.signature(getattr(sys.modules["engine.amg"], function)).parameters  # fmt: skip
    identifiers = [row[1].strip("`") for row in body]
    assert len(set(identifiers)) == len(identifiers)
    for row in body:
        assert row[-1] == "", f"{row[0]}: a session writes no value"
        assert all(cell for cell in row[:-1]), f"{row[0]}: an empty cell"
    for identifier in identifiers:
        # params/README.md: starts with a letter; letters, digits and "_" only.
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", identifier), identifier


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written


# --- a published worked example of AMG: waiting for a person -------------------

WAITS_FOR = (
    "It waits for a person to choose the source of AMG (OPEN in docs/METHODS.md, "
    "'Not in this file yet'), to transcribe from it, and for a second person to "
    "check (decision D34 of issue #77): {what}; the inputs of the worked example, "
    "its published result and the tolerance of the comparison, with their "
    "locators in the source. All of them are OPEN today."
)


@pytest.mark.skip(reason=WAITS_FOR.format(what="the constants of the yearly step as records of the parameter catalogue, and the scheme of the step"))  # fmt: skip
def test_published_worked_example_of_the_yearly_run():
    """A yearly run against a published worked example. No value written by a session."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="the forms and constants of the modifiers of the rate coefficient"))  # fmt: skip
def test_published_worked_example_of_the_rate_coefficient():
    """The rate coefficient and its modifiers against a published example."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="the form of the monthly adaptation of blueprint section 8 and the uniform forcing of the comparison"))  # fmt: skip
def test_published_comparison_of_the_yearly_and_monthly_variants():
    """The annual reference and the monthly adaptation against each other on a published case."""
    pytest.fail("not written: see the skip reason")
