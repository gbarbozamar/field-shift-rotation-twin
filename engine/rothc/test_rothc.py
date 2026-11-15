"""Tests of engine/rothc/: the PROPOSED cases listed in README.md.

Every number in this file is a PLACEHOLDER: plainly not a real value of the
method. Repeated digits are used, or small whole numbers where the
arithmetic is done by hand. No case holds an expected value of the science:
the person-transcribed values of the reference case live in
``test_reference_case.py``.

Run from the repository root: ``python -m pytest engine/rothc/``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import math
import re
import sys
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from engine.rothc._numbers import numbers_or_missing
from contracts.results.models import DEFAULT_TREND_COMPUTATION, TREND_COMPUTATIONS
from contracts.results.models import Missing as ResultMissing
from engine.rothc import (
    MONTHS_PER_YEAR,
    InputSplit,
    MonthInput,
    PoolState,
    Run,
    StepResult,
    TrendMeasures,
    advance_deficit,
    clay_partition,
    cover_modifier,
    end_minus_start,
    fitted_slope,
    initial_state,
    input_additions,
    inert_organic_matter,
    maximum_tsmd,
    mean_over_cycles,
    moisture_modifier,
    plant_fractions,
    rate_modifying_factor,
    run,
    run_rothc,
    step,
    temperature_modifier,
    trend_measures,
)

HERE = Path(__file__).parent
README = HERE / "README.md"
MODULES = sorted(
    path for path in HERE.glob("*.py") if not path.name.startswith("test_")
)

# PLACEHOLDER unit strings: any text, the same text where two must agree, and
# the relations of maximum_tsmd where they must (intercept, clay and -1/-2).
DEGREE = "PLACEHOLDER_degree"
WATER = "PLACEHOLDER_water"
CLAY = "PLACEHOLDER_clay"
DEPTH = "PLACEHOLDER_depth"
CLAY_PER = f"{WATER} {CLAY}-1"
CLAY_SQUARED = f"{WATER} {CLAY}-2"

ABSENT_INPUT = InputMissing(reason="NOT_DECLARED")
ABSENT_RESULT = ResultMissing(reason="NO_COVERAGE", detail="placeholder detail")
BOTH_SHAPES = [ABSENT_INPUT, ABSENT_RESULT]


def assert_missing(result, reason, *words) -> None:
    assert isinstance(result, ResultMissing), result
    assert result.reason == reason, result
    for word in words:
        assert word in result.detail, result.detail


# --- callers with PLACEHOLDER arguments --------------------------------------


def temperature(**changes):
    arguments = dict(
        temperature=11.1,
        temperature_unit=DEGREE,
        maximum=44.4,
        exponent_scale=99.9,
        exponent_scale_unit=DEGREE,
        offset=22.2,
        offset_unit=DEGREE,
    )
    return temperature_modifier(**{**arguments, **changes})


def partition(**changes):
    arguments = dict(
        clay_content=33.3,
        clay_content_unit=CLAY,
        scale=1.11,
        intercept=2.22,
        clay_coefficient=3.33,
        clay_decay=0.44,
        clay_decay_unit=CLAY,
    )
    return clay_partition(**{**arguments, **changes})


def maximum(**changes):
    arguments = dict(
        clay_content=33.3,
        clay_content_unit=CLAY,
        depth=55.5,
        depth_unit=DEPTH,
        intercept=66.6,
        intercept_unit=WATER,
        clay_coefficient=1.33,
        clay_coefficient_unit=CLAY_PER,
        clay_squared_coefficient=0.011,
        clay_squared_coefficient_unit=CLAY_SQUARED,
        reference_depth=55.5,
        reference_depth_unit=DEPTH,
    )
    return maximum_tsmd(**{**arguments, **changes})


def advance(**changes):
    arguments = dict(
        deficit=-33.3,
        maximum=-66.6,
        maximum_unit=WATER,
        rainfall=22.2,
        rainfall_unit=WATER,
        pan_evaporation=44.4,
        pan_evaporation_unit=WATER,
        pan_factor=0.77,
    )
    return advance_deficit(**{**arguments, **changes})


def moisture(**changes):
    arguments = dict(
        deficit=-22.2,
        maximum=-55.5,
        threshold_fraction=0.44,
        minimum=0.22,
    )
    return moisture_modifier(**{**arguments, **changes})


def cover(**changes):
    arguments = dict(
        cover_state=1.0,
        vegetated_factor=0.66,
        bare_factor=1.0,
    )
    return cover_modifier(**{**arguments, **changes})


def combined(**changes):
    arguments = dict(
        temperature_factor=1.11,
        moisture_factor=0.55,
        cover_factor=0.66,
    )
    return rate_modifying_factor(**{**arguments, **changes})


def initial(**changes):
    arguments = dict(dpm=1.11, rpm=2.22, bio=3.33, hum=4.44, iom=5.55)
    return initial_state(**{**arguments, **changes})


def inert(**changes):
    arguments = dict(total_organic_carbon=33.3, coefficient=0.044, exponent=1.11)
    return inert_organic_matter(**{**arguments, **changes})


def additions(**changes):
    arguments = dict(
        carbon_inputs={"input_a": 2.22, "input_b": 1.11},
        compositions={
            "input_a": InputSplit(dpm=0.5, rpm=0.5, bio=0.0, hum=0.0),
            "input_b": InputSplit(dpm=0.1, rpm=0.2, bio=0.0, hum=0.7),
        },
    )
    return input_additions(**{**arguments, **changes})


def one_step(**changes):
    arguments = dict(
        state=PoolState(dpm=1.11, rpm=2.22, bio=3.33, hum=4.44, iom=5.55),
        additions=InputSplit(dpm=0.111, rpm=0.222, bio=0.0, hum=0.333),
        rate_modifying_factor=0.55,
        rate_constants={"dpm": 1.11, "rpm": 0.222, "bio": 0.333, "hum": 0.044},
        partition_ratio=3.33,
        bio_share=0.44,
    )
    return step(**{**arguments, **changes})


def a_run(months):
    return run(
        initial_state=initial(),
        months=months,
        rate_constants={"dpm": 1.11, "rpm": 0.222, "bio": 0.333, "hum": 0.044},
        partition_ratio=3.33,
        bio_share=0.44,
    )


def a_month(**changes):
    arguments = dict(
        additions=InputSplit(dpm=0.111, rpm=0.222, bio=0.0, hum=0.333),
        rate_modifying_factor=0.55,
    )
    return MonthInput(**{**arguments, **changes})


# --- initial state, inputs and the split of the material ----------------------


def test_initial_state_takes_the_five_pools():
    state = initial()
    assert (state.dpm, state.rpm, state.bio, state.hum, state.iom) == (
        1.11,
        2.22,
        3.33,
        4.44,
        5.55,
    )
    assert state.total == pytest.approx(1.11 + 2.22 + 3.33 + 4.44 + 5.55)


def test_initial_state_refuses_negative_stocks_and_names_them():
    for pool in ("dpm", "rpm", "bio", "hum", "iom"):
        assert_missing(initial(**{pool: -0.1}), "NOT_COMPUTABLE", pool, "is negative")


@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_initial_state_missing_pool_is_named_with_its_reason(shape):
    result = initial(rpm=shape)
    assert_missing(result, "MISSING_INPUT", "rpm", shape.reason)
    result = initial(dpm=shape, hum=shape)
    assert_missing(result, "MISSING_INPUT", "dpm", "hum")


def test_plant_fractions_follow_the_ratio():
    for ratio in (0.11, 0.22, 1.33, 3.33):
        split = plant_fractions(dpm_rpm_ratio=ratio)
        assert split.dpm == pytest.approx(ratio / (ratio + 1))
        assert split.rpm == pytest.approx(1 / (ratio + 1))
        assert split.bio == 0.0 and split.hum == 0.0
        assert split.dpm + split.rpm == pytest.approx(1.0)
    assert plant_fractions(dpm_rpm_ratio=0.0) == InputSplit(
        dpm=0.0, rpm=1.0, bio=0.0, hum=0.0
    )


def test_plant_fractions_refuse_a_negative_ratio():
    # A negative ratio is refused before the form runs, so also at minus one.
    for ratio in (-0.1, -1.0):
        assert_missing(
            plant_fractions(dpm_rpm_ratio=ratio), "NOT_COMPUTABLE", "is negative"
        )


def test_inert_organic_matter_follows_the_form():
    for total, coefficient, exponent in (
        (33.3, 0.044, 1.11),
        (44.4, 0.111, 2.22),
        (0.0, 0.044, 1.11),
    ):
        assert inert_organic_matter(
            total_organic_carbon=total, coefficient=coefficient, exponent=exponent
        ) == pytest.approx(coefficient * total**exponent)


def test_input_additions_split_each_input_by_its_composition():
    result = additions()
    assert result.dpm == pytest.approx(2.22 * 0.5 + 1.11 * 0.1)
    assert result.rpm == pytest.approx(2.22 * 0.5 + 1.11 * 0.2)
    assert result.bio == 0.0
    assert result.hum == pytest.approx(1.11 * 0.7)
    assert result.total == pytest.approx(2.22 + 1.11)


@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_input_additions_without_a_composition_or_with_a_missing_one_name_it(shape):
    assert_missing(
        additions(compositions={"input_a": InputSplit(0.5, 0.5, 0.0, 0.0)}),
        "MISSING_INPUT",
        "composition of carbon input 'input_b'",
    )
    result = input_additions(
        carbon_inputs={"input_a": 1.11},
        compositions={"input_a": shape},
    )
    assert_missing(result, "MISSING_INPUT", "composition of 'input_a'", shape.reason)


def test_input_additions_refuse_negative_inputs_and_shares_that_do_not_sum_to_one():
    assert_missing(
        additions(carbon_inputs={"input_a": -0.1, "input_b": 1.11}),
        "NOT_COMPUTABLE",
        "carbon input 'input_a'",
    )
    assert_missing(
        additions(
            compositions={
                "input_a": InputSplit(0.5, 0.4, 0.0, 0.0),  # sums to 0.9
                "input_b": InputSplit(0.1, 0.2, 0.0, 0.7),
            }
        ),
        "NOT_COMPUTABLE",
        "sum to",
    )
    assert_missing(
        additions(
            compositions={
                "input_a": InputSplit(-0.1, 1.1, 0.0, 0.0),
                "input_b": InputSplit(0.1, 0.2, 0.0, 0.7),
            }
        ),
        "NOT_COMPUTABLE",
        "is negative",
    )


def test_input_additions_with_no_input_is_not_computed():
    assert_missing(input_additions(carbon_inputs={}, compositions={}), "NOT_COMPUTABLE")


# --- one month -----------------------------------------------------------------


def test_step_follows_the_form():
    result = one_step()
    state = PoolState(dpm=1.11, rpm=2.22, bio=3.33, hum=4.44, iom=5.55)
    additions_of_month = InputSplit(dpm=0.111, rpm=0.222, bio=0.0, hum=0.333)
    rates = {"dpm": 1.11, "rpm": 0.222, "bio": 0.333, "hum": 0.044}
    abc = 0.55
    x = 3.33
    bio_share = 0.44
    with_input = {
        pool: getattr(state, pool) + getattr(additions_of_month, pool)
        for pool in ("dpm", "rpm", "bio", "hum")
    }
    decayed = {
        pool: with_input[pool] * math.exp(-rates[pool] * abc / MONTHS_PER_YEAR)
        for pool in with_input
    }
    decomposed = math.fsum(with_input[p] - decayed[p] for p in with_input)
    formed = decomposed / (x + 1)
    assert result.co2 == pytest.approx(decomposed * x / (x + 1))
    assert result.end.dpm == pytest.approx(decayed["dpm"])
    assert result.end.rpm == pytest.approx(decayed["rpm"])
    assert result.end.bio == pytest.approx(decayed["bio"] + bio_share * formed)
    assert result.end.hum == pytest.approx(decayed["hum"] + (1 - bio_share) * formed)
    assert result.end.iom == state.iom
    assert result.duration == pytest.approx(1 / MONTHS_PER_YEAR)


def test_step_keeps_the_mass_balance():
    for abc in (0.0, 0.11, 0.99, 9.99):
        result = one_step(rate_modifying_factor=abc)
        stocks_in = result.start.total + result.additions.total
        stocks_out = result.end.total
        assert stocks_out + result.co2 == pytest.approx(stocks_in, rel=1e-12)
        for pool in ("dpm", "rpm", "bio", "hum", "iom"):
            assert getattr(result.end, pool) >= 0


def test_step_with_no_additions_and_no_factor_decays_the_pools_only():
    nothing = InputSplit(dpm=0.0, rpm=0.0, bio=0.0, hum=0.0)
    frozen = one_step(additions=nothing, rate_modifying_factor=0.0)
    assert frozen.end == frozen.start
    assert frozen.co2 == 0.0
    warm = one_step(additions=nothing)
    assert warm.co2 > 0.0
    # DPM and RPM receive nothing back, so they can only fall; BIO and HUM
    # receive the formed material; the inert pool does not change; the total
    # falls by the CO2 of the month.
    for pool in ("dpm", "rpm"):
        assert getattr(warm.end, pool) < getattr(warm.start, pool)
    assert warm.end.iom == warm.start.iom
    assert warm.start.total - warm.end.total == pytest.approx(warm.co2, rel=1e-12)


def test_step_refuses_negative_values_and_a_share_outside_zero_to_one():
    assert_missing(
        one_step(state=PoolState(dpm=-0.1, rpm=2.2, bio=3.3, hum=4.4, iom=5.5)),
        "NOT_COMPUTABLE",
        "state.dpm",
    )
    assert_missing(
        one_step(additions=InputSplit(-0.1, 0.2, 0.0, 0.3)),
        "NOT_COMPUTABLE",
        "additions.dpm",
    )
    assert_missing(one_step(rate_modifying_factor=-0.1), "NOT_COMPUTABLE", "rate_modifying_factor")  # fmt: skip
    assert_missing(one_step(rate_constants={"dpm": -0.1, "rpm": 2.2, "bio": 3.3, "hum": 4.4}), "NOT_COMPUTABLE", "rate_constants[dpm]")  # fmt: skip
    assert_missing(one_step(partition_ratio=-0.1), "NOT_COMPUTABLE", "partition_ratio")
    assert_missing(one_step(partition_ratio=0.0), "NOT_COMPUTABLE", "partition_ratio")
    assert_missing(one_step(bio_share=1.1), "NOT_COMPUTABLE", "bio_share")
    assert_missing(one_step(bio_share=-0.1), "NOT_COMPUTABLE", "bio_share")


@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_step_missing_argument_gives_missing_input_that_names_it(shape):
    assert_missing(
        one_step(state=shape), "MISSING_INPUT", "the state at the start of the month", shape.reason  # fmt: skip
    )
    assert_missing(one_step(additions=shape), "MISSING_INPUT", "the additions of the month", shape.reason)  # fmt: skip
    assert_missing(one_step(rate_modifying_factor=shape), "MISSING_INPUT", "rate_modifying_factor", shape.reason)  # fmt: skip
    rates = {"dpm": shape, "rpm": 2.2, "bio": 3.3, "hum": 4.4}
    assert_missing(one_step(rate_constants=rates), "MISSING_INPUT", "rate_constants[dpm]", shape.reason)  # fmt: skip
    assert_missing(one_step(partition_ratio=shape), "MISSING_INPUT", "partition_ratio", shape.reason)
    assert_missing(one_step(bio_share=shape), "MISSING_INPUT", "bio_share", shape.reason)


def test_step_rate_constants_hold_the_four_active_pools():
    for wrong in ({"dpm": 1.1}, {"dpm": 1.1, "rpm": 2.2, "bio": 3.3}, {"dpm": 1.1, "rpm": 2.2, "bio": 3.3, "hum": 4.4, "iom": 5.5}):  # fmt: skip
        with pytest.raises(TypeError, match="rate_constants"):
            one_step(rate_constants=wrong)


# --- a run over months ----------------------------------------------------------


def test_run_equals_steps_applied_one_after_another():
    months = [a_month(), a_month(rate_modifying_factor=0.11), a_month()]
    the_run = a_run(months)
    state = initial()
    for position, month in enumerate(months):
        expected = step(
            state=state,
            additions=month.additions,
            rate_modifying_factor=month.rate_modifying_factor,
            rate_constants={"dpm": 1.11, "rpm": 0.222, "bio": 0.333, "hum": 0.044},
            partition_ratio=3.33,
            bio_share=0.44,
        )
        assert the_run.steps[position] == expected
        state = expected.end


def test_run_mass_balance_holds_at_every_month_over_a_long_series():
    months = []
    for position in range(3000):
        shape = position % 5
        months.append(
            MonthInput(
                additions=InputSplit(
                    dpm=0.111 * (shape + 1),
                    rpm=0.0,
                    bio=0.0,
                    hum=0.033 if shape == 2 else 0.0,
                ),
                rate_modifying_factor=(0.11, 0.55, 1.11, 2.22, 0.0)[shape],
            )
        )
    the_run = a_run(months)
    state = the_run.initial_state
    for position, item in enumerate(the_run.steps):
        assert isinstance(item, StepResult), position
        stocks_in = state.total + item.additions.total
        assert item.end.total + item.co2 == pytest.approx(
            stocks_in, rel=1e-12, abs=1e-9
        )
        for pool in ("dpm", "rpm", "bio", "hum", "iom"):
            assert getattr(item.end, pool) >= 0
        state = item.end


@pytest.mark.parametrize("shape", BOTH_SHAPES)
def test_run_missing_month_makes_that_month_and_every_later_month_missing(shape):
    months = [a_month(), a_month(), a_month()]
    months[1] = MonthInput(additions=a_month().additions, rate_modifying_factor=shape)
    the_run = a_run(months)
    assert isinstance(the_run.steps[0], StepResult)
    for position in (1, 2):
        assert_missing(
            the_run.steps[position], "MISSING_INPUT", f"month {position}", shape.reason
        )
    stocks = the_run.total_stocks()
    assert stocks[1] is not None and not isinstance(stocks[1], ResultMissing)
    for position in (2, 3):
        assert isinstance(stocks[position], ResultMissing)
    missing_additions = MonthInput(additions=shape, rate_modifying_factor=0.55)
    the_run = a_run([a_month(), missing_additions, a_month()])
    assert_missing(the_run.steps[2], "MISSING_INPUT", "month 2", "month 1")


def test_run_missing_initial_state_makes_every_month_missing():
    for broken in (ABSENT_INPUT, initial(dpm=-0.1)):
        the_run = run(
            initial_state=broken,
            months=[a_month(), a_month()],
            rate_constants={"dpm": 1.11, "rpm": 0.222, "bio": 0.333, "hum": 0.044},
            partition_ratio=3.33,
            bio_share=0.44,
        )
        for item in the_run.steps:
            assert isinstance(item, ResultMissing)
            assert "initial state" in item.detail or "state" in item.detail
        assert isinstance(the_run.total_stocks()[0], (InputMissing, ResultMissing))


def test_run_elapsed_times_and_total_stocks():
    the_run = a_run([a_month(), a_month(), a_month()])
    assert the_run.elapsed_times() == pytest.approx(
        [0.0, 1 / MONTHS_PER_YEAR, 2 / MONTHS_PER_YEAR, 3 / MONTHS_PER_YEAR]
    )
    stocks = the_run.total_stocks()
    assert stocks[0] == pytest.approx(the_run.initial_state.total)
    for position, item in enumerate(the_run.steps):
        assert stocks[position + 1] == pytest.approx(item.end.total)


# --- the rate modifying factors ---------------------------------------------------


def test_temperature_modifier_follows_the_form():
    for temperature_value in (-9.9, 0.0, 4.4, 11.1, 22.2, 44.4, 99.9):
        assert temperature(temperature=temperature_value) == pytest.approx(
            44.4 / (1 + math.exp(99.9 / (temperature_value + 22.2)))
        )
    assert temperature(temperature=-22.2 + 1.1) == pytest.approx(
        44.4 / (1 + math.exp(99.9 / 1.1))
    )


def test_clay_partition_follows_the_form():
    for clay_content in (0.0, 11.1, 33.3, 99.9):
        assert partition(clay_content=clay_content) == pytest.approx(
            1.11 * (2.22 + 3.33 * math.exp(-0.44 * clay_content))
        )


def test_maximum_tsmd_follows_the_form():
    for clay_content, depth in ((0.0, 55.5), (33.3, 55.5), (33.3, 11.1)):
        assert maximum(clay_content=clay_content, depth=depth) == pytest.approx(
            -(66.6 + 1.33 * clay_content - 0.011 * clay_content**2)
            * depth
            / 55.5
        )


def test_maximum_tsmd_refuses_a_depth_of_zero_or_a_clay_that_makes_no_deficit():
    assert_missing(maximum(depth=0.0), "NOT_COMPUTABLE")
    assert_missing(maximum(reference_depth=0.0), "NOT_COMPUTABLE")
    # A clay content so large that the form makes no negative deficit.
    assert_missing(maximum(clay_content=9999.9), "NOT_COMPUTABLE")


def test_advance_deficit_accumulates_and_holds_at_the_limits():
    maximum_deficit = -66.6
    # A dry month: the deficit grows in magnitude by 0.77 * pan - rain.
    assert advance() == pytest.approx(-33.3 - (0.77 * 44.4 - 22.2))
    # A wet month: the soil wets up and is held at field capacity (zero).
    assert advance(rainfall=99.9, pan_evaporation=0.0) == 0.0
    # A very dry month: the deficit is held at the maximum.
    held = advance(rainfall=0.0, pan_evaporation=999.9)
    assert held == maximum_deficit
    # The accumulation starts from field capacity on the first month.
    assert advance(deficit=0.0) == pytest.approx(0.0 - (0.77 * 44.4 - 22.2))


def test_moisture_modifier_follows_the_form():
    maximum_deficit = -55.5
    threshold = 0.44 * maximum_deficit
    minimum = 0.22
    # Above the threshold the modifier is one.
    assert moisture(deficit=threshold + 1.1) == 1.0
    assert moisture(deficit=0.0) == 1.0
    # Below it the form applies, written a second time.
    for deficit in (threshold - 1.1, -33.3, maximum_deficit):
        assert moisture(deficit=deficit) == pytest.approx(
            minimum
            + (1 - minimum) * (maximum_deficit - deficit) / (maximum_deficit - threshold)
        )
    assert moisture(deficit=maximum_deficit) == pytest.approx(minimum)


def test_cover_modifier_takes_one_of_the_two_states():
    assert cover(cover_state=1.0) == 0.66
    assert cover(cover_state=0.0) == 1.0
    assert_missing(cover(cover_state=0.5), "NOT_COMPUTABLE", "neither of the two states")  # fmt: skip
    assert_missing(cover(cover_state=2.0), "NOT_COMPUTABLE", "neither of the two states")  # fmt: skip


def test_rate_modifying_factor_is_the_product():
    assert combined() == pytest.approx(1.11 * 0.55 * 0.66)
    assert combined(temperature_factor=0.0) == 0.0
    assert_missing(
        combined(moisture_factor=ABSENT_INPUT),
        "MISSING_INPUT",
        "moisture_factor",
        "NOT_DECLARED",
    )
    assert_missing(combined(cover_factor=-0.1), "NOT_COMPUTABLE", "is negative")


def test_modifier_negative_or_missing_value_is_not_computed():
    assert_missing(advance(rainfall=-0.1), "NOT_COMPUTABLE", "rainfall")
    assert_missing(advance(pan_evaporation=-0.1), "NOT_COMPUTABLE", "pan_evaporation")
    assert_missing(advance(pan_factor=1.1), "NOT_COMPUTABLE", "pan_factor")
    assert_missing(advance(pan_factor=-0.1), "NOT_COMPUTABLE", "pan_factor")
    assert_missing(partition(clay_content=-0.1), "NOT_COMPUTABLE", "clay_content")
    assert_missing(maximum(clay_content=-0.1), "NOT_COMPUTABLE", "clay_content")
    assert_missing(maximum(depth=-0.1), "NOT_COMPUTABLE", "depth")
    assert_missing(advance(maximum=11.1), "NOT_COMPUTABLE", "not negative")
    assert_missing(advance(deficit=11.1), "NOT_COMPUTABLE", "outside")
    assert_missing(moisture(deficit=11.1), "NOT_COMPUTABLE", "outside")
    assert_missing(advance(rainfall=ABSENT_INPUT), "MISSING_INPUT", "rainfall")
    assert_missing(cover(vegetated_factor=ABSENT_INPUT), "MISSING_INPUT", "vegetated_factor")  # fmt: skip
    assert_missing(cover(cover_state=ABSENT_INPUT), "MISSING_INPUT", "cover_state")


def test_modifier_units_that_differ_are_not_computed():
    assert_missing(
        temperature(temperature_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "temperature_unit")  # fmt: skip
    assert_missing(
        temperature(offset_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "offset_unit")
    assert_missing(advance(pan_evaporation_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "pan_evaporation_unit")  # fmt: skip
    assert_missing(advance(maximum_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "maximum_unit")  # fmt: skip
    assert_missing(
        partition(clay_decay_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "clay_decay_unit")  # fmt: skip
    assert_missing(
        maximum(clay_coefficient_unit=f"{WATER} {CLAY}-2"), "NOT_COMPUTABLE", "clay_coefficient_unit")  # fmt: skip
    assert_missing(
        maximum(clay_squared_coefficient_unit=CLAY_PER), "NOT_COMPUTABLE", "clay_squared_coefficient_unit")  # fmt: skip
    assert_missing(maximum(depth_unit="PLACEHOLDER_other"), "NOT_COMPUTABLE", "depth_unit")  # fmt: skip


# --- trend measures of C1.6 --------------------------------------------------------


def test_end_minus_start_is_the_change_over_the_horizon_per_unit_time():
    stocks = [10.0, 11.0, 12.5, 13.0]
    times = [0.0, 1.0, 2.0, 4.0]
    assert end_minus_start(stocks=stocks, times=times) == pytest.approx(
        (13.0 - 10.0) / 4.0
    )
    with_missing = list(stocks)
    with_missing[1] = ABSENT_INPUT
    assert end_minus_start(stocks=with_missing, times=times) == pytest.approx(0.75)


def test_fitted_slope_recovers_the_slope_of_a_straight_line():
    assert fitted_slope(stocks=[1.0, 2.0, 3.0], times=[0.0, 1.0, 2.0]) == pytest.approx(1.0)  # fmt: skip
    assert fitted_slope(stocks=[5.0, 3.0], times=[0.0, 2.0]) == pytest.approx(-1.0)


def test_mean_over_cycles_is_the_mean_change_per_unit_time_of_the_whole_cycles():
    stocks = [10.0, 12.0, 14.0, 15.0, 99.0]
    times = [0.0, 2.0, 4.0, 6.0, 7.0]
    # One whole cycle over the first three points; the last point is not used.
    assert mean_over_cycles(
        stocks=stocks, times=times, cycle_boundaries=[0, 2]
    ) == pytest.approx((14.0 - 10.0) / 4.0)
    assert mean_over_cycles(
        stocks=stocks, times=times, cycle_boundaries=[0, 2, 3]
    ) == pytest.approx(((14.0 - 10.0) / 4.0 + (15.0 - 14.0) / 2.0) / 2)


def test_trend_measures_name_the_three_computations_of_c16():
    stocks = [10.0, 11.0, 12.0, 13.0]
    times = [0.0, 1.0, 2.0, 3.0]
    measures = trend_measures(
        stocks=stocks, times=times, cycle_boundaries=[0, 3]
    )
    assert list(measures.values) == list(TREND_COMPUTATIONS)
    assert DEFAULT_TREND_COMPUTATION in measures.values
    assert measures.time_unit == "yr"
    assert measures.values["end_minus_start"] == end_minus_start(
        stocks=stocks, times=times
    )
    assert measures.values["fitted_slope"] == fitted_slope(stocks=stocks, times=times)
    assert measures.values["mean_over_cycles"] == mean_over_cycles(
        stocks=stocks, times=times, cycle_boundaries=[0, 3]
    )


def test_trend_of_a_series_with_a_missing_point_is_missing_with_its_reason():
    stocks = [10.0, ABSENT_INPUT, 12.0]
    times = [0.0, 1.0, 2.0]
    measures = trend_measures(stocks=stocks, times=times, cycle_boundaries=[0, 2])
    # A missing point stops only the measures that use it.
    assert_missing(measures.values["fitted_slope"], "MISSING_INPUT", "stocks[1]")
    assert isinstance(measures.values["end_minus_start"], float)
    assert isinstance(measures.values["mean_over_cycles"], float)
    # A missing point at a boundary stops the measure over cycles.
    measures = trend_measures(stocks=stocks, times=times, cycle_boundaries=[0, 1])
    assert_missing(measures.values["mean_over_cycles"], "MISSING_INPUT", "stocks[1]")


def test_trend_without_a_span_of_time_is_not_computed():
    for function in (end_minus_start, fitted_slope):
        assert_missing(function(stocks=[10.0], times=[0.0]), "NOT_COMPUTABLE", "fewer than two points")  # fmt: skip
        assert_missing(function(stocks=[], times=[]), "NOT_COMPUTABLE", "fewer than two points")  # fmt: skip
        assert_missing(function(stocks=[10.0, 11.0], times=[1.0, 1.0]), "NOT_COMPUTABLE", "not after")  # fmt: skip
        assert_missing(function(stocks=[10.0, 11.0], times=[2.0, 1.0]), "NOT_COMPUTABLE", "not after")  # fmt: skip
    assert_missing(fitted_slope(stocks=[1.0, 2.0, 3.0], times=[0.0, 2.0, 1.0]), "NOT_COMPUTABLE", "times[2]")  # fmt: skip
    measures = trend_measures(stocks=[1.0], times=[0.0], cycle_boundaries=[0])
    for value in measures.values.values():
        assert value.reason == "NOT_COMPUTABLE"
    with pytest.raises(ValueError, match="one item each"):
        end_minus_start(stocks=[1.0, 2.0], times=[0.0])


# --- every number argument ------------------------------------------------------

NUMBER_ARGUMENTS = [
    (temperature, "temperature"),
    (temperature, "maximum"),
    (temperature, "exponent_scale"),
    (temperature, "offset"),
    (partition, "clay_content"),
    (partition, "scale"),
    (partition, "intercept"),
    (partition, "clay_coefficient"),
    (partition, "clay_decay"),
    (maximum, "clay_content"),
    (maximum, "depth"),
    (maximum, "intercept"),
    (maximum, "clay_coefficient"),
    (maximum, "clay_squared_coefficient"),
    (maximum, "reference_depth"),
    (advance, "deficit"),
    (advance, "maximum"),
    (advance, "rainfall"),
    (advance, "pan_evaporation"),
    (advance, "pan_factor"),
    (moisture, "deficit"),
    (moisture, "maximum"),
    (moisture, "threshold_fraction"),
    (moisture, "minimum"),
    (cover, "cover_state"),
    (cover, "vegetated_factor"),
    (cover, "bare_factor"),
    (combined, "temperature_factor"),
    (combined, "moisture_factor"),
    (combined, "cover_factor"),
    (inert, "total_organic_carbon"),
    (inert, "coefficient"),
    (inert, "exponent"),
    (initial, "dpm"),
    (initial, "iom"),
]
NOT_FINITE = [math.nan, math.inf, -math.inf, 10**400]


@pytest.mark.parametrize("call, name", NUMBER_ARGUMENTS)
@pytest.mark.parametrize("value", NOT_FINITE)
def test_argument_that_is_not_finite_is_not_computed(call, name, value):
    assert_missing(call(**{name: value}), "NOT_COMPUTABLE", name, "not a finite number")


@pytest.mark.parametrize("value", NOT_FINITE)
def test_items_that_are_not_finite_are_not_computed(value):
    assert_missing(combined(cover_factor=value), "NOT_COMPUTABLE", "cover_factor")
    assert_missing(additions(carbon_inputs={"input_a": value, "input_b": 1.11}), "NOT_COMPUTABLE", "input_a")  # fmt: skip
    assert_missing(one_step(state=PoolState(dpm=value, rpm=2.2, bio=3.3, hum=4.4, iom=5.5)), "NOT_COMPUTABLE", "state.dpm")  # fmt: skip
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
    with pytest.raises(TypeError, match="carbon_inputs"):
        additions(carbon_inputs=None)
    with pytest.raises(TypeError, match="compositions"):
        additions(compositions={1: InputSplit(0.5, 0.5, 0.0, 0.0)})
    with pytest.raises(TypeError, match="state"):
        one_step(state=(44.4, 22.2))
    with pytest.raises(TypeError, match="state.dpm"):
        one_step(state=PoolState(dpm=None, rpm=2.2, bio=3.3, hum=4.4, iom=5.5))
    with pytest.raises(TypeError, match="additions"):
        one_step(additions=(1.11, 0.222, 0.0, 0.333))
    with pytest.raises(TypeError, match="additions.dpm"):
        one_step(additions=InputSplit(None, 0.222, 0.0, 0.333))
    with pytest.raises(TypeError, match="months"):
        a_run(None)
    with pytest.raises(TypeError, match=re.escape("months[0]")):
        a_run([(1.11, 0.55)])
    with pytest.raises(TypeError, match=re.escape("months[0].rate_modifying_factor")):
        a_run([MonthInput(additions=InputSplit(0.1, 0.2, 0.0, 0.7), rate_modifying_factor=None)])  # fmt: skip
    with pytest.raises(TypeError, match="temperature_unit"):
        temperature(temperature_unit=None)
    with pytest.raises(TypeError, match="rate_constants"):
        one_step(rate_constants=None)
    with pytest.raises(TypeError, match="stocks"):
        end_minus_start(stocks=None, times=[0.0])
    with pytest.raises(TypeError, match="cycle_boundaries"):
        mean_over_cycles(stocks=[1.0, 2.0], times=[0.0, 1.0], cycle_boundaries=[0.5, 1])  # fmt: skip


# --- the shapes of the package -----------------------------------------------------

PUBLIC_FUNCTIONS = [
    advance_deficit,
    clay_partition,
    cover_modifier,
    end_minus_start,
    fitted_slope,
    initial_state,
    input_additions,
    inert_organic_matter,
    maximum_tsmd,
    mean_over_cycles,
    moisture_modifier,
    plant_fractions,
    rate_modifying_factor,
    run,
    step,
    temperature_modifier,
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
    for model in (InputSplit, MonthInput, PoolState, Run, StepResult, TrendMeasures):
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
        assert numbers <= {0, 1, 0.0, 1.0}, (path.name, numbers)


def test_entry_point_is_run_rothc_of_entry_module():
    """contracts/ENTRYPOINTS.md EP6: module ``engine.rothc``, function ``run_rothc``.

    The runner of api/engines.py holds EntryPoint("EP6", "rothc",
    "engine.rothc", "run_rothc"); ``importlib`` and ``getattr`` are its
    lookup. Whether the runner lists EP6 among the entries it imports is the
    platform developer's (README.md, OPEN).
    """
    module = importlib.import_module("engine.rothc")
    assert getattr(module, "run_rothc") is run_rothc
    assert callable(run_rothc)


def section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written, sorted(listed ^ written)


def test_a_uniform_run_of_missing_arguments_is_summarized_not_enumerated():
    # Missing arguments that share one reason and one detail are written
    # once: how many they are, their run by its first and its last name, the
    # reason and the detail. Here 277 stocks share one PLACEHOLDER detail.
    # Arguments that share nothing keep the enumeration, one by one.
    one_reason = InputMissing(reason="NOT_AVAILABLE", detail="the month is missing")
    many = {f"stocks[{i}]": one_reason for i in range(277)}
    many.update({f"times[{i}]": float(i) for i in range(277)})
    summarized = numbers_or_missing(many)
    assert summarized.reason == "MISSING_INPUT"
    assert summarized.detail == (
        "277 arguments are missing (from stocks[0] to stocks[276]), "
        "reason NOT_AVAILABLE: the month is missing"
    )
    other = InputMissing(reason="NOT_DECLARED")
    mixed = {"a": one_reason, "b": other}
    enumerated = numbers_or_missing(mixed)
    assert enumerated.detail == (
        "a is missing, reason NOT_AVAILABLE: the month is missing; "
        "b is missing, reason NOT_DECLARED"
    )


def test_missing_arguments_with_a_gap_are_named_as_separate_runs():
    # Stocks 0 to 49 and 200 to 276 are missing and the 150 between them are
    # present: two runs. No run spans an argument that is present.
    gone = InputMissing(reason="NOT_AVAILABLE", detail="the month is missing")
    stocks = [gone if i < 50 or i >= 200 else float(i) for i in range(277)]
    result = fitted_slope(stocks=stocks, times=[float(i) for i in range(277)])
    assert result.reason == "MISSING_INPUT"
    assert result.detail == (
        "127 arguments are missing (from stocks[0] to stocks[49], "
        "from stocks[200] to stocks[276]), reason NOT_AVAILABLE: the month is missing"
    )
    # A stock that is present inside a run ends it, and a missing stock with
    # no missing neighbour is named alone.
    stocks = [gone, gone, 2.2, gone, 4.4, gone, gone, gone]
    result = fitted_slope(stocks=stocks, times=[float(i) for i in range(len(stocks))])
    assert result.detail == (
        "6 arguments are missing (from stocks[0] to stocks[1], stocks[3], "
        "from stocks[5] to stocks[7]), reason NOT_AVAILABLE: the month is missing"
    )


def test_missing_pools_around_a_present_one_are_each_named():
    # Arguments without an index are never written "from X to Y": a reader
    # does not know which names lie between two of them, so each is named.
    gone = InputMissing(reason="NOT_AVAILABLE", detail="placeholder detail")
    result = initial_state(dpm=gone, rpm=22.2, bio=gone, hum=gone, iom=55.5)
    assert result.reason == "MISSING_INPUT"
    assert result.detail == (
        "3 arguments are missing (dpm, bio, hum), reason NOT_AVAILABLE: "
        "placeholder detail"
    )
    result = initial_state(dpm=gone, rpm=gone, bio=gone, hum=gone, iom=gone)
    assert result.detail == (
        "5 arguments are missing (dpm, rpm, bio, hum, iom), reason NOT_AVAILABLE: "
        "placeholder detail"
    )


def test_details_that_differ_only_by_their_month_are_one_group():
    # The form run() gives a month that is not computed: "month <position>: …".
    def gone(detail, reason="MISSING_INPUT"):
        return ResultMissing(reason=reason, detail=detail)

    after = "the state at its start is missing"
    numbers = {
        "stocks[0]": gone("the initial state is missing"),
        "times[0]": 0.0,
        "stocks[1]": gone(f"month 0: {after}"),
        "times[1]": gone(f"month 0: {after}"),
        "stocks[2]": gone(f"month 1: {after}"),
        "times[2]": gone(f"month 0: {after}"),
        "stocks[3]": gone(f"month 2: {after}"),
        "times[3]": gone(f"month 0: {after}"),
    }
    assert numbers_or_missing(numbers).detail == (
        "stocks[0] is missing, reason MISSING_INPUT: the initial state is missing; "
        "6 arguments are missing (from stocks[1] to stocks[3], from times[1] to "
        "times[3]), reason MISSING_INPUT, each detail naming a month from 0 to 2 "
        f"and otherwise the same: {after}"
    )
    # The same month in every detail: the detail is written as it is.
    same = {"a": gone("month 4: one text"), "b": gone("month 4: one text")}
    assert numbers_or_missing(same).detail == (
        "2 arguments are missing (a, b), reason MISSING_INPUT: month 4: one text"
    )
    # Not one group: another reason, another text after the month, a month
    # that is not a number, a month that is not at the opening. With no two
    # arguments in one group the detail is the enumeration of before.
    apart = {
        "a": gone("month 0: one text"),
        "b": gone("month 1: one text", reason="NOT_COMPUTABLE"),
        "c": gone("month 2: another text"),
        "d": gone("month x: one text"),
        "e": gone("one text, at month 3: one text"),
    }
    assert numbers_or_missing(apart).detail == "; ".join(
        f"{name} is missing, reason {item.reason}: {item.detail}"
        for name, item in apart.items()
    )


def test_trend_detail_of_a_run_stopped_at_a_month_does_not_grow_with_the_months():
    # run() stops at month 1: the stock and the times after it carry that
    # month, and every later stock names its own month. Two groups, whatever
    # the number of months.
    def detail_of(count):
        months = [a_month() for _ in range(count)]
        months[1] = MonthInput(
            additions=a_month().additions, rate_modifying_factor=ABSENT_RESULT
        )
        the_run = a_run(months)
        result = fitted_slope(
            stocks=list(the_run.total_stocks()), times=list(the_run.elapsed_times())
        )
        assert result.reason == "MISSING_INPUT"
        return result.detail

    short, long = detail_of(12), detail_of(240)
    assert re.sub(r"\d+", "N", short) == re.sub(r"\d+", "N", long)
    stopped = (
        "month 1: rate_modifying_factor is missing, reason NO_COVERAGE: "
        "placeholder detail"
    )
    assert long == (
        "240 arguments are missing (stocks[2], from times[2] to times[240]), "
        f"reason MISSING_INPUT: {stopped}; "
        "238 arguments are missing (from stocks[3] to stocks[240]), reason "
        "MISSING_INPUT, each detail naming a month from 2 to 239 and otherwise "
        "the same: the state at its start is missing; month 1 is missing, reason "
        "MISSING_INPUT: rate_modifying_factor is missing, reason NO_COVERAGE: "
        "placeholder detail"
    )
