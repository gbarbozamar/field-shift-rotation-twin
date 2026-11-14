"""Acceptance test of engine/water/evaporation/ (PROPOSED cases, see README.md).

Every number in this file is a PLACEHOLDER chosen to exercise the code. None
is a real evaporable water, depth, coefficient, fraction, exponent or climate
value, and none comes from FAO-56 or any other source. The checks are
structural (forms written with the placeholders, mass closure, bounds,
stages of drying, missing values); the worked example of FAO-56 chapter 7 is
skipped until a person transcribes and checks it (D34).
"""

from __future__ import annotations

import ast
import dataclasses
import datetime
import inspect
import math
import random
import sys
from pathlib import Path

import pytest

import engine.water.evaporation as evaporation_package
from contracts.results.models import Missing
from engine.water.balance import CropDay
from engine.water.balance import DayInput as BalanceDayInput
from engine.water.balance import step as balance_step
from engine.water.evaporation import (
    RESULT_QUANTITIES,
    DayInput,
    DayResult,
    UpperLimitClimateConstants,
    climate_adjusted_upper_limit,
    cover_fraction_from_basal_coefficient,
    evaporation_coefficient,
    evaporation_reduction_coefficient,
    exposed_and_wetted_fraction,
    run_surface_layer,
    step,
    total_evaporable_water,
    upper_limit_of_crop_coefficient,
)

# PLACEHOLDER values, plainly not real. Depths of water carry no unit here.
TEW = 100.0  # PLACEHOLDER total evaporable water
REW = 25.0  # PLACEHOLDER readily evaporable water
FW = 0.375  # PLACEHOLDER wetted fraction
MARGIN = 0.875  # PLACEHOLDER margin above the basal coefficient
KCB = 1.5  # PLACEHOLDER basal coefficient
CLIMATE = 3.0  # PLACEHOLDER climate term of the upper limit
FC = 0.25  # PLACEHOLDER cover fraction
START = datetime.date(2001, 1, 1)  # PLACEHOLDER first day
EPS = sys.float_info.epsilon
CONSTANTS = dict(
    total_evaporable_water=TEW,
    readily_evaporable_water=REW,
    wetted_fraction=FW,
    margin_above_basal=MARGIN,
)
CLIMATE_CONSTANTS = UpperLimitClimateConstants(  # PLACEHOLDER, every field
    base=2.0,  # PLACEHOLDER
    wind_coefficient=0.25,  # PLACEHOLDER
    reference_wind_speed=3.0,  # PLACEHOLDER
    humidity_coefficient=0.125,  # PLACEHOLDER
    reference_minimum_relative_humidity=10.0,  # PLACEHOLDER
    reference_crop_height=4.0,  # PLACEHOLDER
    height_exponent=2.5,  # PLACEHOLDER
)
DAY_INPUTS = (
    "precipitation",
    "runoff",
    "reference_evapotranspiration",
    "basal_crop_coefficient",
    "cover_fraction",
    "climate_adjusted_upper_limit",
)
MODULE = Path(__file__).with_name("surface_layer.py")


def day(
    offset: int = 0,  # PLACEHOLDER
    *,
    p: float | Missing = 0.0,  # PLACEHOLDER
    q: float | Missing = 0.0,  # PLACEHOLDER
    et0: float | Missing = 0.0,  # PLACEHOLDER
    kcb: float | Missing = KCB,
    fc: float | Missing = FC,
    climate: float | Missing = CLIMATE,
) -> DayInput:
    return DayInput(
        date=START + datetime.timedelta(days=offset),
        precipitation=p,
        runoff=q,
        reference_evapotranspiration=et0,
        basal_crop_coefficient=kcb,
        cover_fraction=fc,
        climate_adjusted_upper_limit=climate,
    )


def run(days, initial_depletion=0.0, **overrides):  # PLACEHOLDER
    return run_surface_layer(
        days, initial_depletion=initial_depletion, **{**CONSTANTS, **overrides}
    )


def long_series(seed: int, years: int = 20) -> list[DayInput]:  # PLACEHOLDER
    """A PLACEHOLDER series: dry spells, storms, fallow and full cover."""
    rng = random.Random(seed)
    days = []
    for offset in range(years * 365):  # PLACEHOLDER
        wet = rng.random() < 0.2  # PLACEHOLDER
        p = rng.uniform(0.0, 200.0) if wet else 0.0  # PLACEHOLDER
        q = rng.choice(
            (0.0, rng.uniform(0.0, 50.0), p + rng.uniform(0.0, 5.0))  # PLACEHOLDER
        )
        days.append(
            day(
                offset,
                p=p,
                q=q,
                et0=rng.uniform(0.0, 20.0),  # PLACEHOLDER
                kcb=rng.uniform(0.0, 2.0),  # PLACEHOLDER
                fc=rng.choice((0.0, 1.0, rng.uniform(0.0, 1.0))),  # PLACEHOLDER
                climate=rng.uniform(0.0, 4.0),  # PLACEHOLDER
            )
        )
    return days


def closure_error(r: DayResult) -> tuple[float, float]:
    lhs = r.depletion_end - r.depletion_start
    rhs = -r.infiltration + r.deep_percolation + r.evaporation_from_exposed_fraction
    scale = max(
        TEW,
        abs(r.infiltration),
        r.deep_percolation,
        r.evaporation_from_exposed_fraction,
    )
    return abs(lhs - rhs), 8 * EPS * scale  # PLACEHOLDER


# ---------------------------------------------------------------------------
# Intermediate quantities, each with its own test.


def test_total_evaporable_water_follows_its_form():
    value = total_evaporable_water(
        3.0,  # PLACEHOLDER
        2.0,  # PLACEHOLDER
        5.0,  # PLACEHOLDER
        wilting_point_weight=0.75,  # PLACEHOLDER
        unit_factor=7.0,  # PLACEHOLDER
    )
    assert value == 7.0 * (3.0 - 0.75 * 2.0) * 5.0  # PLACEHOLDER


def test_total_evaporable_water_below_zero_is_not_computable():
    value = total_evaporable_water(
        1.0,  # PLACEHOLDER
        4.0,  # PLACEHOLDER
        5.0,  # PLACEHOLDER
        wilting_point_weight=0.75,  # PLACEHOLDER
        unit_factor=7.0,  # PLACEHOLDER
    )
    assert isinstance(value, Missing) and value.reason == "NOT_COMPUTABLE"


def test_total_evaporable_water_names_missing_operands():
    value = total_evaporable_water(
        Missing(reason="NO_COVERAGE"),
        2.0,  # PLACEHOLDER
        5.0,  # PLACEHOLDER
        wilting_point_weight=Missing(reason="NOT_AVAILABLE"),
        unit_factor=7.0,  # PLACEHOLDER
    )
    assert value.reason == "MISSING_INPUT"
    assert "input 'field_capacity_water_content' (NO_COVERAGE)" in value.detail
    assert "constant 'wilting_point_weight' (NOT_AVAILABLE)" in value.detail


def test_reduction_coefficient_is_one_in_stage_one():
    for depletion in (0.0, REW / 2, REW):  # PLACEHOLDER
        assert (
            evaporation_reduction_coefficient(
                depletion,
                total_evaporable_water=TEW,
                readily_evaporable_water=REW,
            )
            == 1.0  # PLACEHOLDER
        )


def test_reduction_coefficient_falls_linearly_to_zero_in_stage_two():
    def kr(de):
        return evaporation_reduction_coefficient(
            de, total_evaporable_water=TEW, readily_evaporable_water=REW
        )

    for depletion in (REW + 1.0, 50.0, 90.0):  # PLACEHOLDER
        assert kr(depletion) == pytest.approx((TEW - depletion) / (TEW - REW))
    assert kr(TEW) == 0.0  # PLACEHOLDER
    values = [kr(TEW * k / 200) for k in range(201)]  # PLACEHOLDER
    assert all(0.0 <= v <= 1.0 for v in values)  # PLACEHOLDER
    assert all(b <= a for a, b in zip(values, values[1:]))  # PLACEHOLDER


def test_reduction_coefficient_with_equal_evaporable_waters_stays_in_stage_one():
    assert (
        evaporation_reduction_coefficient(
            TEW, total_evaporable_water=TEW, readily_evaporable_water=TEW
        )
        == 1.0  # PLACEHOLDER
    )


def test_reduction_coefficient_rejects_caller_defects():
    with pytest.raises(ValueError):
        evaporation_reduction_coefficient(
            TEW + 1.0,  # PLACEHOLDER
            total_evaporable_water=TEW,
            readily_evaporable_water=REW,
        )
    with pytest.raises(ValueError):
        evaporation_reduction_coefficient(
            0.0,  # PLACEHOLDER
            total_evaporable_water=TEW,
            readily_evaporable_water=TEW + 1.0,  # PLACEHOLDER
        )
    with pytest.raises(ValueError):
        evaporation_reduction_coefficient(
            0.0,  # PLACEHOLDER
            total_evaporable_water=0.0,  # PLACEHOLDER
            readily_evaporable_water=0.0,  # PLACEHOLDER
        )


def test_reduction_coefficient_missing_operand_is_missing():
    value = evaporation_reduction_coefficient(
        Missing(reason="MISSING_INPUT", detail="PLACEHOLDER cause"),
        total_evaporable_water=TEW,
        readily_evaporable_water=Missing(reason="NOT_AVAILABLE"),
    )
    assert value.reason == "MISSING_INPUT"
    assert "input 'depletion'" in value.detail
    assert "constant 'readily_evaporable_water' (NOT_AVAILABLE)" in value.detail


def test_climate_term_of_the_upper_limit_follows_its_form():
    c = CLIMATE_CONSTANTS
    u2, rh, h = 5.0, 30.0, 9.0  # PLACEHOLDER
    expected = (
        c.base
        + (
            c.wind_coefficient * (u2 - c.reference_wind_speed)
            - c.humidity_coefficient * (rh - c.reference_minimum_relative_humidity)
        )
        * (h / c.reference_crop_height) ** c.height_exponent
    )
    assert climate_adjusted_upper_limit(u2, rh, h, constants=c) == pytest.approx(
        expected
    )


def test_climate_term_names_a_missing_constant():
    constants = dataclasses.replace(
        CLIMATE_CONSTANTS, height_exponent=Missing(reason="NOT_AVAILABLE")
    )
    value = climate_adjusted_upper_limit(
        5.0,  # PLACEHOLDER
        30.0,  # PLACEHOLDER
        9.0,  # PLACEHOLDER
        constants=constants,
    )
    assert value.reason == "MISSING_INPUT"
    assert "constant 'height_exponent' (NOT_AVAILABLE)" in value.detail


def test_climate_term_with_no_finite_value_is_not_computable():
    constants = dataclasses.replace(
        CLIMATE_CONSTANTS,
        height_exponent=-2.5,  # PLACEHOLDER
    )
    value = climate_adjusted_upper_limit(
        5.0,  # PLACEHOLDER
        30.0,  # PLACEHOLDER
        0.0,  # PLACEHOLDER
        constants=constants,
    )
    assert isinstance(value, Missing) and value.reason == "NOT_COMPUTABLE"


def test_climate_term_rejects_caller_defects():
    with pytest.raises(ValueError):
        climate_adjusted_upper_limit(
            5.0,  # PLACEHOLDER
            30.0,  # PLACEHOLDER
            9.0,  # PLACEHOLDER
            constants=dataclasses.replace(
                CLIMATE_CONSTANTS,
                reference_crop_height=0.0,  # PLACEHOLDER
            ),
        )
    with pytest.raises(TypeError):
        climate_adjusted_upper_limit(
            5.0,  # PLACEHOLDER
            30.0,  # PLACEHOLDER
            9.0,  # PLACEHOLDER
            constants={"base": 2.0},  # PLACEHOLDER
        )
    with pytest.raises(ValueError):
        climate_adjusted_upper_limit(
            -5.0,  # PLACEHOLDER
            30.0,  # PLACEHOLDER
            9.0,  # PLACEHOLDER
            constants=CLIMATE_CONSTANTS,
        )


def test_upper_limit_is_the_larger_of_climate_term_and_basal_plus_margin():
    assert (
        upper_limit_of_crop_coefficient(
            1.0,  # PLACEHOLDER
            3.0,  # PLACEHOLDER
            margin_above_basal=0.875,  # PLACEHOLDER
        )
        == 3.0  # PLACEHOLDER
    )
    assert (
        upper_limit_of_crop_coefficient(
            2.75,  # PLACEHOLDER
            3.0,  # PLACEHOLDER
            margin_above_basal=0.875,  # PLACEHOLDER
        )
        == 3.625  # PLACEHOLDER
    )
    for kcb in (0.0, 1.0, 2.0, 5.0):  # PLACEHOLDER
        assert (
            upper_limit_of_crop_coefficient(
                kcb,
                3.0,  # PLACEHOLDER
                margin_above_basal=0.875,  # PLACEHOLDER
            )
            >= kcb
        )


def test_upper_limit_missing_operand_is_missing():
    value = upper_limit_of_crop_coefficient(
        1.0,  # PLACEHOLDER
        Missing(reason="NO_COVERAGE"),
        margin_above_basal=0.875,  # PLACEHOLDER
    )
    assert value.reason == "MISSING_INPUT"
    assert "input 'climate_adjusted_upper_limit' (NO_COVERAGE)" in value.detail


def test_cover_fraction_follows_its_form():
    value = cover_fraction_from_basal_coefficient(
        2.0,  # PLACEHOLDER
        minimum_crop_coefficient=1.0,  # PLACEHOLDER
        upper_limit=5.0,  # PLACEHOLDER
        exponent=3.0,  # PLACEHOLDER
    )
    assert value == pytest.approx(((2.0 - 1.0) / (5.0 - 1.0)) ** 3.0)  # PLACEHOLDER


def test_cover_fraction_outside_its_domain_is_not_computable():
    for kcb, kc_min, kc_max in (
        (0.375, 1.0, 5.0),  # PLACEHOLDER
        (6.0, 1.0, 5.0),  # PLACEHOLDER
        (2.0, 3.0, 3.0),  # PLACEHOLDER
    ):
        value = cover_fraction_from_basal_coefficient(
            kcb,
            minimum_crop_coefficient=kc_min,
            upper_limit=kc_max,
            exponent=3.0,  # PLACEHOLDER
        )
        assert isinstance(value, Missing) and value.reason == "NOT_COMPUTABLE"


def test_cover_fraction_missing_exponent_is_missing():
    value = cover_fraction_from_basal_coefficient(
        2.0,  # PLACEHOLDER
        minimum_crop_coefficient=1.0,  # PLACEHOLDER
        upper_limit=5.0,  # PLACEHOLDER
        exponent=Missing(reason="NOT_AVAILABLE"),
    )
    assert value.reason == "MISSING_INPUT"
    assert "constant 'exponent'" in value.detail


def test_exposed_and_wetted_fraction_is_the_smaller_of_exposed_and_wetted():
    assert exposed_and_wetted_fraction(0.25, 0.375) == 0.375  # PLACEHOLDER
    assert exposed_and_wetted_fraction(0.75, 0.375) == 0.25  # PLACEHOLDER
    assert exposed_and_wetted_fraction(1.0, 0.375) == 0.0  # PLACEHOLDER
    with pytest.raises(ValueError):
        exposed_and_wetted_fraction(1.5, 0.375)  # PLACEHOLDER
    with pytest.raises(ValueError):
        exposed_and_wetted_fraction(0.25, 1.5)  # PLACEHOLDER
    value = exposed_and_wetted_fraction(
        Missing(reason="NO_COVERAGE"),
        0.375,  # PLACEHOLDER
    )
    assert value.reason == "MISSING_INPUT"


def test_evaporation_coefficient_is_the_smaller_of_its_two_limits():
    # Limited by the reduction coefficient.
    assert evaporation_coefficient(0.375, 3.0, 1.5, 0.75) == 0.375 * (  # PLACEHOLDER
        3.0 - 1.5  # PLACEHOLDER
    )
    # Limited by the exposed and wetted fraction.
    assert evaporation_coefficient(1.0, 3.0, 1.5, 0.25) == 0.25 * 3.0  # PLACEHOLDER
    # Full cover: nothing evaporates from the soil.
    assert evaporation_coefficient(1.0, 3.0, 1.5, 0.0) == 0.0  # PLACEHOLDER
    with pytest.raises(ValueError):
        evaporation_coefficient(1.0, 1.0, 1.5, 0.375)  # PLACEHOLDER
    value = evaporation_coefficient(
        Missing(reason="NOT_AVAILABLE"),
        3.0,  # PLACEHOLDER
        1.5,  # PLACEHOLDER
        0.375,  # PLACEHOLDER
    )
    assert value.reason == "MISSING_INPUT"
    assert "input 'reduction_coefficient' (NOT_AVAILABLE)" in value.detail


# ---------------------------------------------------------------------------
# The daily step.


def test_the_daily_step_combines_the_intermediate_quantities():
    r = step(40.0, day(et0=6.0), **CONSTANTS)  # PLACEHOLDER
    kr = evaporation_reduction_coefficient(
        40.0,  # PLACEHOLDER
        total_evaporable_water=TEW,
        readily_evaporable_water=REW,
    )
    kc_max = upper_limit_of_crop_coefficient(KCB, CLIMATE, margin_above_basal=MARGIN)
    few = exposed_and_wetted_fraction(FC, FW)
    ke = evaporation_coefficient(kr, kc_max, KCB, few)
    assert (r.reduction_coefficient, r.upper_limit) == (kr, kc_max)
    assert (r.exposed_and_wetted_fraction, r.evaporation_coefficient) == (few, ke)
    assert r.evaporation_demanded == ke * 6.0  # PLACEHOLDER
    assert r.evaporation == r.evaporation_demanded
    assert r.evaporation_from_exposed_fraction == pytest.approx(
        ke * 6.0 / few  # PLACEHOLDER
    )
    assert r.depletion_end == pytest.approx(40.0 + ke * 6.0 / few)  # PLACEHOLDER
    assert r.evaporation_shortfall == 0.0  # PLACEHOLDER


def test_rain_refills_the_layer_and_the_excess_passes_below_it():
    r = step(30.0, day(p=50.0, q=5.0), **CONSTANTS)  # PLACEHOLDER
    assert r.infiltration == 45.0  # PLACEHOLDER
    assert r.deep_percolation == 15.0  # PLACEHOLDER
    assert r.depletion_end == 0.0  # PLACEHOLDER
    r = step(30.0, day(p=20.0, q=5.0), **CONSTANTS)  # PLACEHOLDER
    assert (r.deep_percolation, r.depletion_end) == (0.0, 15.0)  # PLACEHOLDER


def test_runoff_above_the_precipitation_is_limited_and_recorded():
    r = step(30.0, day(p=10.0, q=14.0), **CONSTANTS)  # PLACEHOLDER
    assert (r.runoff, r.runoff_shortfall, r.infiltration) == (
        10.0,  # PLACEHOLDER
        4.0,  # PLACEHOLDER
        0.0,  # PLACEHOLDER
    )
    assert r.depletion_end == 30.0  # PLACEHOLDER


def test_the_reduction_coefficient_follows_the_depletion_at_the_start_of_the_day():
    # Rain refills the layer on this day, yet Kr is that of the start.
    r = step(80.0, day(p=200.0, et0=6.0), **CONSTANTS)  # PLACEHOLDER
    assert r.reduction_coefficient == (TEW - 80.0) / (TEW - REW)  # PLACEHOLDER
    assert r.depletion_end > 0.0  # PLACEHOLDER


# ---------------------------------------------------------------------------
# Bounds and limited evaporation.


def test_evaporation_asking_more_than_the_layer_holds_is_limited_and_recorded():
    r = step(90.0, day(et0=20.0, climate=10.0), **CONSTANTS)  # PLACEHOLDER
    assert r.evaporation_demanded > r.evaporation
    assert r.depletion_end == TEW
    assert r.evaporation_from_exposed_fraction == TEW - 90.0  # PLACEHOLDER
    assert r.evaporation == pytest.approx(
        r.exposed_and_wetted_fraction * (TEW - 90.0)  # PLACEHOLDER
    )
    assert r.evaporation_shortfall == pytest.approx(
        r.evaporation_demanded - r.evaporation
    )
    assert r.evaporation_shortfall > 0.0  # PLACEHOLDER


def test_a_demand_that_nearly_fills_the_layer_never_ends_above_it():
    # Regression found by the verifier of #151; every value is a PLACEHOLDER.
    # The first day's demand nearly fills the room left in the layer; the
    # depletion once ended one rounding step above TEW and the second day
    # raised.
    tew = 60.54  # PLACEHOLDER
    days = [
        day(k, et0=et0, kcb=1.5, fc=0.28, climate=3.0)  # PLACEHOLDER
        for k, et0 in enumerate((28.6944, 1.0))  # PLACEHOLDER
    ]
    results = run_surface_layer(
        days,
        initial_depletion=11.98,  # PLACEHOLDER
        total_evaporable_water=tew,
        readily_evaporable_water=0.76,  # PLACEHOLDER
        wetted_fraction=0.88,  # PLACEHOLDER
        margin_above_basal=0.5,  # PLACEHOLDER
    )
    for r in results:
        assert 0.0 <= r.depletion_end <= tew  # PLACEHOLDER
        assert r.evaporation_shortfall >= 0.0  # PLACEHOLDER
        assert r.evaporation <= r.evaporation_demanded


def test_demands_near_the_room_left_keep_every_bound():
    # Randomized: the demand of the first day is set within a few rounding
    # steps of the room left in the layer. Every value is a PLACEHOLDER.
    rng = random.Random(151)  # PLACEHOLDER seed
    for _ in range(2000):  # PLACEHOLDER number of cases
        tew = rng.uniform(1.0, 300.0)  # PLACEHOLDER
        rew = rng.uniform(0.0, tew)  # PLACEHOLDER
        fw = rng.uniform(0.01, 1.0)  # PLACEHOLDER
        fc = rng.uniform(0.0, 0.99)  # PLACEHOLDER
        kcb = rng.uniform(0.0, 3.0)  # PLACEHOLDER
        climate = rng.uniform(0.0, 5.0)  # PLACEHOLDER
        margin = rng.uniform(0.0, 1.0)  # PLACEHOLDER
        start = rng.uniform(0.0, tew)  # PLACEHOLDER
        constants = dict(
            total_evaporable_water=tew,
            readily_evaporable_water=rew,
            wetted_fraction=fw,
            margin_above_basal=margin,
        )
        kr = evaporation_reduction_coefficient(
            start, total_evaporable_water=tew, readily_evaporable_water=rew
        )
        kc_max = upper_limit_of_crop_coefficient(
            kcb, climate, margin_above_basal=margin
        )
        few = exposed_and_wetted_fraction(fc, fw)
        ke = evaporation_coefficient(kr, kc_max, kcb, few)
        if ke <= 0.0 or few <= 0.0:  # PLACEHOLDER
            continue
        exact = (tew - start) * few / ke
        steps = rng.randint(-4, 4)  # PLACEHOLDER rounding steps
        et0 = exact * (1.0 + steps * EPS)  # PLACEHOLDER
        if not et0 >= 0.0:  # PLACEHOLDER
            continue
        days = [
            day(0, et0=et0, kcb=kcb, fc=fc, climate=climate),  # PLACEHOLDER
            day(1, et0=1.0, kcb=kcb, fc=fc, climate=climate),  # PLACEHOLDER
        ]
        for r in run_surface_layer(days, initial_depletion=start, **constants):
            assert 0.0 <= r.depletion_end <= tew  # PLACEHOLDER
            assert r.evaporation_shortfall >= 0.0  # PLACEHOLDER
            assert r.evaporation <= r.evaporation_demanded
            lhs = r.depletion_end - r.depletion_start
            rhs = (
                -r.infiltration
                + r.deep_percolation
                + r.evaporation_from_exposed_fraction
            )
            assert abs(lhs - rhs) <= 8 * EPS * tew  # PLACEHOLDER factor


def test_evaporation_supplied_in_full_has_no_shortfall():
    r = step(10.0, day(et0=1.0), **CONSTANTS)  # PLACEHOLDER
    assert r.evaporation_shortfall == 0.0 and r.runoff_shortfall == 0.0  # PLACEHOLDER


def test_full_cover_evaporates_nothing_and_keeps_the_depletion():
    r = step(40.0, day(et0=20.0, fc=1.0), **CONSTANTS)  # PLACEHOLDER
    assert r.exposed_and_wetted_fraction == 0.0  # PLACEHOLDER
    assert (r.evaporation_coefficient, r.evaporation) == (0.0, 0.0)  # PLACEHOLDER
    assert r.depletion_end == 40.0  # PLACEHOLDER


@pytest.mark.parametrize("seed", [1, 2, 3])  # PLACEHOLDER
def test_mass_closure_every_day_on_a_long_series(seed):
    results = run(
        long_series(seed),
        initial_depletion=TEW if seed == 2 else 0.0,  # PLACEHOLDER
    )
    assert len(results) == 20 * 365  # PLACEHOLDER
    for r in results:
        error, tolerance = closure_error(r)
        assert error <= tolerance, r.date


def test_the_long_series_reaches_every_branch_of_the_step():
    results = run(long_series(1))  # PLACEHOLDER
    assert any(r.deep_percolation > 0 for r in results)  # PLACEHOLDER
    assert any(r.evaporation_shortfall > 0 for r in results)  # PLACEHOLDER
    assert any(r.runoff_shortfall > 0 for r in results)  # PLACEHOLDER
    assert any(r.exposed_and_wetted_fraction == 0 for r in results)  # PLACEHOLDER
    assert any(r.reduction_coefficient == 1.0 for r in results)  # PLACEHOLDER
    assert any(0 < r.reduction_coefficient < 1 for r in results)  # PLACEHOLDER
    assert any(r.depletion_end == TEW for r in results)


def test_depletion_never_below_zero_nor_above_total_evaporable_water():
    for seed in (1, 2, 3):  # PLACEHOLDER
        for r in run(long_series(seed)):
            assert 0.0 <= r.depletion_start <= TEW  # PLACEHOLDER
            assert 0.0 <= r.depletion_end <= TEW  # PLACEHOLDER
            for name in (
                "runoff",
                "infiltration",
                "deep_percolation",
                "evaporation",
                "evaporation_from_exposed_fraction",
                "evaporation_shortfall",
                "runoff_shortfall",
            ):
                assert getattr(r, name) >= 0.0  # PLACEHOLDER
            assert r.evaporation + r.evaporation_shortfall == pytest.approx(
                r.evaporation_demanded
            )


def test_the_depletion_is_carried_from_day_to_day_and_never_reset():
    days = long_series(4, years=2)  # PLACEHOLDER
    results = run(days)
    for before, after in zip(results, results[1:]):  # PLACEHOLDER
        assert after.depletion_start == before.depletion_end
    half = len(days) // 2  # PLACEHOLDER
    first = run(days[:half])
    second = run(days[half:], initial_depletion=first[-1].depletion_end)  # PLACEHOLDER
    assert first + second == results


# ---------------------------------------------------------------------------
# Stage 1 and stage 2 of drying (structure only).


def test_drying_goes_through_stage_one_then_stage_two():
    results = run([day(k, et0=4.0) for k in range(200)])  # PLACEHOLDER
    stage_one = [r for r in results if r.depletion_start <= REW]
    stage_two = [r for r in results if r.depletion_start > REW]
    assert stage_one and stage_two
    # Stage 1 comes first, then stage 2, with no return.
    assert results[: len(stage_one)] == stage_one
    assert all(r.reduction_coefficient == 1.0 for r in stage_one)  # PLACEHOLDER
    first = stage_one[0].evaporation  # PLACEHOLDER
    assert all(r.evaporation == first for r in stage_one)
    # Stage 2: evaporation falls day after day while the layer dries.
    assert all(0.0 <= r.reduction_coefficient < 1.0 for r in stage_two)  # PLACEHOLDER
    for a, b in zip(stage_two, stage_two[1:]):  # PLACEHOLDER
        assert b.reduction_coefficient <= a.reduction_coefficient
        assert b.evaporation <= a.evaporation
    assert all(r.depletion_end <= TEW for r in results)


def test_rain_after_stage_two_returns_the_layer_to_stage_one():
    days = [day(k, et0=4.0) for k in range(60)]  # PLACEHOLDER
    days.append(day(60, p=200.0, et0=4.0))  # PLACEHOLDER
    days.append(day(61, et0=4.0))  # PLACEHOLDER
    results = run(days)
    assert results[59].reduction_coefficient < 1.0  # PLACEHOLDER
    assert results[60].deep_percolation > 0.0  # PLACEHOLDER
    assert results[60].depletion_end <= REW  # PLACEHOLDER
    assert results[61].reduction_coefficient == 1.0  # PLACEHOLDER


# ---------------------------------------------------------------------------
# Missing in, missing out.


@pytest.mark.parametrize("name", DAY_INPUTS)
def test_a_missing_input_gives_missing_outputs_that_day_and_after(name):
    days = [
        day(k, p=5.0 if k % 3 == 0 else 0.0, et0=4.0)  # PLACEHOLDER
        for k in range(10)  # PLACEHOLDER
    ]
    days[4] = dataclasses.replace(  # PLACEHOLDER
        days[4],  # PLACEHOLDER
        **{name: Missing(reason="NO_COVERAGE")},
    )
    complete = run(
        [
            day(k, p=5.0 if k % 3 == 0 else 0.0, et0=4.0)  # PLACEHOLDER
            for k in range(10)  # PLACEHOLDER
        ]
    )
    results = run(days)
    assert len(results) == 10  # PLACEHOLDER
    assert results[:4] == complete[:4]  # PLACEHOLDER
    for r in results[4:]:  # PLACEHOLDER
        for quantity in RESULT_QUANTITIES:
            value = getattr(r, quantity)
            assert isinstance(value, Missing)
            assert value.reason == "MISSING_INPUT"
            assert f"{name} (NO_COVERAGE)" in value.detail
            assert "2001-01-05" in value.detail


def test_a_missing_constant_gives_every_day_missing():
    results = run(
        [day(k, et0=4.0) for k in range(3)],  # PLACEHOLDER
        readily_evaporable_water=Missing(reason="NOT_AVAILABLE"),
    )
    for r in results:
        for quantity in RESULT_QUANTITIES:
            value = getattr(r, quantity)
            assert value.reason == "MISSING_INPUT"
            assert "constant 'readily_evaporable_water' (NOT_AVAILABLE)" in value.detail


def test_a_missing_initial_depletion_gives_every_day_missing():
    results = run(
        [day(k, et0=4.0) for k in range(3)],  # PLACEHOLDER
        initial_depletion=Missing(reason="NOT_DECLARED"),
    )
    for r in results:
        assert r.evaporation_coefficient.reason == "MISSING_INPUT"
        assert "initial depletion (NOT_DECLARED)" in r.evaporation_coefficient.detail


def test_missing_is_never_zero():
    days = [day(k, et0=4.0) for k in range(5)]  # PLACEHOLDER
    days[1] = dataclasses.replace(  # PLACEHOLDER
        days[1],  # PLACEHOLDER
        precipitation=Missing(reason="NO_COVERAGE"),
    )
    for r in run(days)[1:]:  # PLACEHOLDER
        for quantity in RESULT_QUANTITIES:
            value = getattr(r, quantity)
            assert value != 0 and not _is_number(value)  # PLACEHOLDER


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# A day with no crop.


def test_a_day_with_no_crop_takes_its_basal_coefficient_and_cover_as_inputs():
    # PLACEHOLDER values of a day with no crop, supplied by the caller.
    bare_a = step(40.0, day(et0=6.0, kcb=1.75, fc=0.0), **CONSTANTS)  # PLACEHOLDER
    bare_b = step(40.0, day(et0=6.0, kcb=2.25, fc=0.75), **CONSTANTS)  # PLACEHOLDER
    assert bare_a.evaporation_coefficient != bare_b.evaporation_coefficient
    assert bare_a.exposed_and_wetted_fraction == FW
    for r in (bare_a, bare_b):
        error, tolerance = closure_error(r)
        assert error <= tolerance


def test_no_input_or_constant_has_a_default():
    for field in dataclasses.fields(DayInput):
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING
    for field in dataclasses.fields(UpperLimitClimateConstants):
        assert field.default is dataclasses.MISSING
    for name in evaporation_package.__all__:
        obj = getattr(evaporation_package, name)
        if inspect.isfunction(obj):
            for parameter in inspect.signature(obj).parameters.values():
                assert parameter.default is inspect.Parameter.empty, (name, parameter)


# ---------------------------------------------------------------------------
# Integration with engine/water/balance.


def test_the_result_is_the_evaporation_coefficient_of_the_balance_day_input():
    r = step(40.0, day(et0=6.0), **CONSTANTS)  # PLACEHOLDER
    balance_day = BalanceDayInput(
        date=r.date,
        precipitation=0.0,  # PLACEHOLDER
        runoff=0.0,  # PLACEHOLDER
        reference_evapotranspiration=6.0,  # PLACEHOLDER
        evaporation_coefficient=r.evaporation_coefficient,
        crop=CropDay(
            transpiration_coefficient=KCB,
            root_depth=3.5,  # PLACEHOLDER
            readily_available_fraction=0.25,  # PLACEHOLDER
        ),
    )
    out = balance_step(
        30.0,  # PLACEHOLDER
        balance_day,
        capacity=50.0,  # PLACEHOLDER
        column_depth=4.0,  # PLACEHOLDER
    )
    assert out.evaporation_demanded == r.evaporation_coefficient * 6.0  # PLACEHOLDER


def test_a_missing_result_passes_to_the_balance_as_missing():
    days = [day(0, et0=Missing(reason="NO_COVERAGE"))]  # PLACEHOLDER
    r = run(days)[0]  # PLACEHOLDER
    balance_day = BalanceDayInput(
        date=r.date,
        precipitation=0.0,  # PLACEHOLDER
        runoff=0.0,  # PLACEHOLDER
        reference_evapotranspiration=6.0,  # PLACEHOLDER
        evaporation_coefficient=r.evaporation_coefficient,
        crop=None,
    )
    out = balance_step(
        30.0,  # PLACEHOLDER
        balance_day,
        capacity=50.0,  # PLACEHOLDER
        column_depth=4.0,  # PLACEHOLDER
    )
    assert out.evaporation.reason == "MISSING_INPUT"
    assert "evaporation_coefficient (MISSING_INPUT)" in out.evaporation.detail


# ---------------------------------------------------------------------------
# Caller defects, purity, no values.


def test_invalid_constants_raise_value_error():
    for overrides in (
        dict(total_evaporable_water=0.0),  # PLACEHOLDER
        dict(total_evaporable_water=-1.0),  # PLACEHOLDER
        dict(readily_evaporable_water=TEW + 1.0),  # PLACEHOLDER
        dict(wetted_fraction=1.5),  # PLACEHOLDER
        dict(margin_above_basal=-0.875),  # PLACEHOLDER
        dict(total_evaporable_water=math.inf),
    ):
        with pytest.raises(ValueError):
            run([day(0)], **overrides)  # PLACEHOLDER


def test_initial_depletion_outside_the_layer_raises_value_error():
    for value in (-1.0, TEW + 1.0):  # PLACEHOLDER
        with pytest.raises(ValueError):
            run([day(0)], initial_depletion=value)  # PLACEHOLDER


def test_invalid_day_raises():
    with pytest.raises(ValueError):
        run([day(0, p=-1.0)])  # PLACEHOLDER
    with pytest.raises(ValueError):
        run([day(0, fc=1.5)])  # PLACEHOLDER
    with pytest.raises(TypeError):
        run([day(0, et0="PLACEHOLDER")])
    with pytest.raises(TypeError):
        run([day(0, kcb=True)])  # PLACEHOLDER
    with pytest.raises(TypeError):
        run(["not a day"])


def test_days_that_are_not_consecutive_raise_value_error():
    for offsets in ((0, 2), (1, 0), (0, 0)):  # PLACEHOLDER
        with pytest.raises(ValueError):
            run([day(k) for k in offsets])


def test_an_empty_sequence_gives_no_days():
    assert run([]) == []


def test_same_arguments_give_the_same_result_and_are_not_changed():
    days = long_series(5, years=1)  # PLACEHOLDER
    copy = list(days)
    assert run(days) == run(days)
    assert days == copy


def test_the_module_holds_no_number_other_than_zero_and_one():
    numbers = {
        node.value
        for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}  # PLACEHOLDER


# ---------------------------------------------------------------------------
# Skipped, waiting for people.


@pytest.mark.skip(
    reason=(
        "Waits for the worked example of FAO-56 chapter 7 on soil evaporation "
        "(example number OPEN): its inputs, its intermediate results (Kr, "
        "Kc_max, few, Ke, the depletion of each day), its final value and the "
        "tolerance, transcribed from the manual with reference, locator, "
        "verbatim text and date read, and checked by a person (D34)."
    )
)
def test_fao56_chapter_7_worked_example():
    raise AssertionError("not written until the values exist")
