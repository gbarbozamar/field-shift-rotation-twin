"""Mutant-killing tests for engine/water/evaporation/surface_layer.py.

Every value in this file is a PLACEHOLDER chosen solely to exercise boundary,
clamping, ULP rounding, overflow, missing-detail, and input-validation paths.
None comes from FAO-56 or any other source.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from contracts.results.models import Missing
from engine.water.evaporation import (
    DayInput,
    UpperLimitClimateConstants,
    climate_adjusted_upper_limit,
    cover_fraction_from_basal_coefficient,
    evaporation_coefficient,
    evaporation_reduction_coefficient,
    run_surface_layer,
    step,
    total_evaporable_water,
    upper_limit_of_crop_coefficient,
)

START = datetime.date(2001, 1, 1)  # PLACEHOLDER
TEW = 100.0  # PLACEHOLDER
REW = 25.0  # PLACEHOLDER
FW = 0.5  # PLACEHOLDER
MARGIN = 0.5  # PLACEHOLDER
CONSTANTS = {
    "total_evaporable_water": TEW,
    "readily_evaporable_water": REW,
    "wetted_fraction": FW,
    "margin_above_basal": MARGIN,
}
CLIMATE_CONSTANTS = UpperLimitClimateConstants(
    base=2.0,  # PLACEHOLDER
    wind_coefficient=0.25,  # PLACEHOLDER
    reference_wind_speed=3.0,  # PLACEHOLDER
    humidity_coefficient=0.125,  # PLACEHOLDER
    reference_minimum_relative_humidity=10.0,  # PLACEHOLDER
    reference_crop_height=4.0,  # PLACEHOLDER
    height_exponent=2.0,  # PLACEHOLDER
)


def _day(
    offset: int = 0,
    *,
    p: float | Missing = 0.0,
    q: float | Missing = 0.0,
    et0: float | Missing = 0.0,
    kcb: float | Missing = 1.5,  # PLACEHOLDER
    fc: float | Missing = 0.25,  # PLACEHOLDER
    climate: float | Missing = 3.0,  # PLACEHOLDER
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


def test_total_evaporable_water_zero_is_computable_and_overflow_is_not_computable():
    # Kills `value < 0` -> `value <= 0` and missing `isfinite` check in total_evaporable_water.
    zero_tew = total_evaporable_water(
        1.5,  # PLACEHOLDER
        2.0,  # PLACEHOLDER
        5.0,  # PLACEHOLDER
        wilting_point_weight=0.75,  # PLACEHOLDER
        unit_factor=7.0,  # PLACEHOLDER
    )
    assert zero_tew == 0.0
    overflow_tew = total_evaporable_water(
        1e308,  # PLACEHOLDER
        0.0,
        1e10,  # PLACEHOLDER
        wilting_point_weight=0.5,  # PLACEHOLDER
        unit_factor=1.0,  # PLACEHOLDER
    )
    assert isinstance(overflow_tew, Missing) and overflow_tew.reason == "NOT_COMPUTABLE"


def test_zero_readily_evaporable_water_is_allowed():
    # Kills mutant rejecting `readily_evaporable_water == 0.0`.
    assert (
        evaporation_reduction_coefficient(
            0.0,
            total_evaporable_water=TEW,
            readily_evaporable_water=0.0,
        )
        == 1.0
    )
    assert evaporation_reduction_coefficient(
        20.0,  # PLACEHOLDER
        total_evaporable_water=TEW,
        readily_evaporable_water=0.0,
    ) == pytest.approx(0.8)


def test_negative_climate_adjusted_upper_limit_is_accepted():
    # Kills `_real` -> `_non_negative` in upper_limit_of_crop_coefficient and _check_day.
    assert (
        upper_limit_of_crop_coefficient(
            1.5,  # PLACEHOLDER
            -2.0,  # PLACEHOLDER
            margin_above_basal=MARGIN,
        )
        == 2.0
    )
    result = step(
        10.0,  # PLACEHOLDER
        _day(et0=2.0, climate=-2.0),  # PLACEHOLDER
        **CONSTANTS,
    )
    assert result.upper_limit == 2.0


def test_cover_fraction_endpoints_and_power_errors():
    # Kills `ratio <= 0`, `ratio >= 1`, and missing ZeroDivisionError/OverflowError catch.
    assert (
        cover_fraction_from_basal_coefficient(
            1.0,  # PLACEHOLDER
            minimum_crop_coefficient=1.0,  # PLACEHOLDER
            upper_limit=5.0,  # PLACEHOLDER
            exponent=2.0,  # PLACEHOLDER
        )
        == 0.0
    )
    assert (
        cover_fraction_from_basal_coefficient(
            5.0,  # PLACEHOLDER
            minimum_crop_coefficient=1.0,  # PLACEHOLDER
            upper_limit=5.0,  # PLACEHOLDER
            exponent=2.0,  # PLACEHOLDER
        )
        == 1.0
    )
    zero_neg_exp = cover_fraction_from_basal_coefficient(
        1.0,  # PLACEHOLDER
        minimum_crop_coefficient=1.0,  # PLACEHOLDER
        upper_limit=5.0,  # PLACEHOLDER
        exponent=-1.0,  # PLACEHOLDER
    )
    assert isinstance(zero_neg_exp, Missing) and zero_neg_exp.reason == "NOT_COMPUTABLE"
    overflow_exp = cover_fraction_from_basal_coefficient(
        3.0,  # PLACEHOLDER
        minimum_crop_coefficient=1.0,  # PLACEHOLDER
        upper_limit=5.0,  # PLACEHOLDER
        exponent=-1e308,  # PLACEHOLDER
    )
    assert isinstance(overflow_exp, Missing) and overflow_exp.reason == "NOT_COMPUTABLE"


def test_evaporation_coefficient_allows_upper_limit_equal_to_basal():
    # Kills `kc_max < kcb` -> `kc_max <= kcb` in evaporation_coefficient.
    assert evaporation_coefficient(1.0, 1.5, 1.5, 0.5) == 0.0  # PLACEHOLDER


def test_step_missing_depletion_without_detail_omits_none_suffix():
    # Kills `if depletion_start.detail is not None:` -> `if True:`.
    result = step(
        Missing(reason="NO_COVERAGE"),
        _day(),
        **CONSTANTS,
    )
    assert isinstance(result.depletion_end, Missing)
    assert result.depletion_end.reason == "MISSING_INPUT"
    assert result.depletion_end.detail == "depletion at the start of the day"


def test_step_clamps_evaporation_to_demanded_on_ulp_overshoot():
    # Kills removing `min(few * room, evaporation_demanded)` in step.
    # At these PLACEHOLDER values, `after_inflow + evaporation_demanded / few > tew`,
    # entering the room-limited branch while `few * room` exceeds `evaporation_demanded` by 1 ULP.
    result = step(
        17.46,  # PLACEHOLDER
        _day(
            et0=35.52902439024391,  # PLACEHOLDER
            kcb=2.18,  # PLACEHOLDER
            fc=0.0,
            climate=3.0,  # PLACEHOLDER
        ),
        total_evaporable_water=96.2,  # PLACEHOLDER
        readily_evaporable_water=20.0,  # PLACEHOLDER
        wetted_fraction=0.37,  # PLACEHOLDER
        margin_above_basal=0.0,
    )
    assert result.depletion_end == 96.2
    assert result.evaporation <= result.evaporation_demanded
    assert result.evaporation_shortfall >= 0.0
    assert result.evaporation == result.evaporation_demanded
    assert result.evaporation_shortfall == 0.0


def test_run_surface_layer_preserves_original_missing_cause_without_nesting():
    # Kills mutant overwriting `cause` on subsequent missing days (`if cause is None:`).
    days = [
        _day(0, et0=1.0),
        _day(1, p=Missing(reason="NO_COVERAGE"), et0=1.0),
        _day(2, et0=1.0),
        _day(3, et0=1.0),
    ]
    results = run_surface_layer(days, initial_depletion=0.0, **CONSTANTS)
    expected_cause = f"input of {days[1].date.isoformat()}: precipitation (NO_COVERAGE)"
    for idx in (2, 3):
        detail = results[idx].depletion_end.detail
        assert detail == (
            f"depletion at the start of the day: depletion after {days[idx - 1].date.isoformat()}, "
            f"missing since: {expected_cause}"
        )


def test_huge_integer_raises_value_error_not_overflow_error():
    # Kills mutant removing `except OverflowError:` in `_real`.
    with pytest.raises(ValueError, match="finite"):
        step(
            10**400,  # PLACEHOLDER
            _day(),
            **CONSTANTS,
        )


@pytest.mark.parametrize("empty_seq", ["", b""])
def test_run_surface_layer_rejects_empty_str_or_bytes(empty_seq):
    # Kills mutant removing `isinstance(days, (str, bytes))` guard.
    with pytest.raises(TypeError, match="sequence"):
        run_surface_layer(
            empty_seq,  # type: ignore[arg-type]
            initial_depletion=0.0,
            **CONSTANTS,
        )


def test_step_rejects_datetime_subclass_as_date():
    # Kills mutant dropping `isinstance(day.date, datetime.datetime)` check.
    bad_day = DayInput(
        date=datetime.datetime(2001, 1, 1, 12, 0),  # type: ignore[arg-type]  # PLACEHOLDER
        precipitation=0.0,
        runoff=0.0,
        reference_evapotranspiration=0.0,
        basal_crop_coefficient=1.5,  # PLACEHOLDER
        cover_fraction=0.25,  # PLACEHOLDER
        climate_adjusted_upper_limit=3.0,  # PLACEHOLDER
    )
    with pytest.raises(TypeError, match="datetime.date"):
        step(0.0, bad_day, **CONSTANTS)


def test_step_rejects_negative_constant_even_when_another_constant_is_missing():
    # Kills mutant omitting `_non_negative(name, value)` check for non-missing constants.
    with pytest.raises(ValueError, match="negative"):
        step(
            0.0,
            _day(),
            **{
                **CONSTANTS,
                "total_evaporable_water": -1.0,  # PLACEHOLDER
                "readily_evaporable_water": Missing(reason="NOT_AVAILABLE"),
            },
        )


def test_climate_adjusted_upper_limit_overflow_is_not_computable():
    # Kills mutant removing `OverflowError` catch in `climate_adjusted_upper_limit`.
    result = climate_adjusted_upper_limit(
        5.0,  # PLACEHOLDER
        30.0,  # PLACEHOLDER
        1e308,  # PLACEHOLDER
        constants=dataclasses.replace(
            CLIMATE_CONSTANTS, height_exponent=2.0
        ),  # PLACEHOLDER
    )
    assert isinstance(result, Missing) and result.reason == "NOT_COMPUTABLE"
