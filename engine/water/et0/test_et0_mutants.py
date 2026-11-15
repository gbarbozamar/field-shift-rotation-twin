"""Targeted mutant-killing tests for the daily ET0 package and public entrypoint.

Covers arithmetic, exponent, sign, boundary, missing-propagation, unit-guard,
constant-schema, and daily-integration mutants across:
- ``engine/water/et0/equations.py``
- ``engine/water/et0/constants.py``
- ``engine/water/et0/daily.py``
- ``engine/water/et0/quantities.py``
- ``engine/water/reference_et0.py``

Every number, constant, bound, date, and catalogue record in this file is a
synthetic PLACEHOLDER value; nothing comes from FAO-56 or any external source.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

from contracts.results.models import Missing
from engine.water import exposure as ep3
from engine.water import reference_et0
from engine.water.et0 import constants as et0_constants
from engine.water.et0 import daily
from engine.water.et0 import equations as eq
from engine.water.et0 import quantities
from engine.water.et0.constants import (
    Et0Bounds,
    Et0Constants,
    RelativeShortwaveBound,
    SoilHeatFluxConstants,
    WindSpeedBound,
)
from engine.water.et0.daily import (
    BOUNDS,
    RELATIVE_SHORTWAVE_BOUND,
)
from engine.water.et0.quantities import (
    WIND_SPEED_2M,
    InputValue,
)
from engine.water.et0.test_daily import (
    DAY,
    DATES,
    ELEVATION,
    GUARD,
    LATITUDE,
    TIGHT_BOUNDS,
    all_series,
    climate,
    day,
    point,
    point_value,
    run,
    series,
)
from engine.water.et0.test_equations import (
    CASES,
    LONGWAVE,
    NOT_TRANSCRIBED,
    PLACEHOLDER_BOUNDS,
    PLACEHOLDER_CONSTANTS,
    PRESSURE,
    PSYCHROMETRIC,
    SATURATION,
    SHORTWAVE,
    SHORTWAVE_BOUND,
    SLOPE,
    SOIL,
    WIND_BOUND,
)

# Synthetic catalogue marker for test_reference_et0 compatibility (params.catalogue
# rejects the literal word PLACEHOLDER in checked records).
_PLACEHOLDER_UNMARKED = "UNMARKED_TEST_ONLY"


def _placeholder_record(parameter_id: str, value: float) -> dict[str, Any]:
    return {
        "id": parameter_id,
        "scope": {},
        "value": value,
        "unit": _PLACEHOLDER_UNMARKED,
        "range": None,
        "range_missing_reason": f"{_PLACEHOLDER_UNMARKED}: synthetic test record",
        "citation": {
            "reference": f"{_PLACEHOLDER_UNMARKED} synthetic reference",
            "locator": f"{_PLACEHOLDER_UNMARKED} locator",
        },
        "transcribed_by": f"{_PLACEHOLDER_UNMARKED}_one",
        "checked_by": f"{_PLACEHOLDER_UNMARKED}_two",
        "note": f"{_PLACEHOLDER_UNMARKED} synthetic constant",
    }


def _placeholder_catalogue(
    *,
    constants: Et0Constants = PLACEHOLDER_CONSTANTS,
    bounds: Et0Bounds = PLACEHOLDER_BOUNDS,
    omit: str | None = None,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for group, names in ep3.ET0_PARAMETERS.items():
        group_obj = getattr(constants, group)
        for name in names:
            param_id = f"{group}_{name}"
            if param_id == omit:
                continue
            records[f"{_PLACEHOLDER_UNMARKED}/{param_id}.json"] = _placeholder_record(
                param_id, getattr(group_obj, name)
            )
    for group, fields_map in ep3.ET0_BOUND_PARAMETERS.items():
        group_obj = getattr(bounds, group)
        for field_name, param_id in fields_map.items():
            if param_id == omit:
                continue
            records[f"{_PLACEHOLDER_UNMARKED}/{param_id}.json"] = _placeholder_record(
                param_id, getattr(group_obj, field_name)
            )
    return records


def _placeholder_ep3_climate(*daily_series: dict[str, Any]):
    ep3_point = point(
        latitude=point_value(LATITUDE, ep3.POINT_UNITS.latitude_decimal_degrees),
        elevation=point_value(ELEVATION, ep3.POINT_UNITS.elevation),
    )
    return climate(*daily_series, at=ep3_point)


# --- Assertion helpers (baseline checks without monkeypatch) ------------------


def _check_eq_slope_square() -> None:
    got = eq.slope_of_saturation_vapour_pressure_curve(5.0, SATURATION, SLOPE)
    assert isinstance(got, float)
    assert got == pytest.approx(21.0 * math.e / 100.0, rel=1e-12, abs=1e-12)


def _check_eq_saturation_offset() -> None:
    got = eq.saturation_vapour_pressure(5.0, SATURATION)
    assert isinstance(got, float)
    assert got == pytest.approx(3.0 * math.e, rel=1e-12, abs=1e-12)
    div_zero = eq.saturation_vapour_pressure(-5.0, SATURATION)
    assert isinstance(div_zero, Missing)
    assert div_zero.reason == "NOT_COMPUTABLE"


def _check_eq_psychrometric_mul() -> None:
    got = eq.psychrometric_constant(5.0, PSYCHROMETRIC)
    assert isinstance(got, float)
    assert got == pytest.approx(15.0, rel=1e-12, abs=1e-12)


def _check_eq_pressure_lapse_sign() -> None:
    got = eq.atmospheric_pressure(2.0, PRESSURE)
    assert isinstance(got, float)
    assert got == pytest.approx(5.0, rel=1e-12, abs=1e-12)


def _check_eq_rns_sign() -> None:
    got = eq.net_shortwave_radiation(5.0, SHORTWAVE)
    assert isinstance(got, float)
    assert got == pytest.approx(-10.0, rel=1e-12, abs=1e-12)


def _check_eq_rnl_fourth_power() -> None:
    got = eq.net_longwave_radiation(1.0, -1.0, 4.0, 2.0, LONGWAVE)
    assert isinstance(got, float)
    assert got == pytest.approx(410.0, rel=1e-12, abs=1e-12)


def _check_eq_rnl_humidity_sign() -> None:
    got = eq.net_longwave_radiation(1.0, -1.0, 4.0, 2.0, LONGWAVE)
    assert isinstance(got, float)
    assert got == pytest.approx(410.0, rel=1e-12, abs=1e-12)


def _check_eq_rn_sign() -> None:
    got = eq.net_radiation(11.0, 4.0)
    assert isinstance(got, float)
    assert got == pytest.approx(7.0, rel=1e-12, abs=1e-12)


def _check_eq_soil_heat_flux() -> None:
    got = eq.soil_heat_flux_daily(SOIL)
    assert isinstance(got, float)
    assert got == pytest.approx(3.0, rel=1e-12, abs=1e-12)
    absent = eq.soil_heat_flux_daily(SoilHeatFluxConstants(daily_value=NOT_TRANSCRIBED))
    assert isinstance(absent, Missing)
    assert absent.reason == "MISSING_INPUT"


def _check_eq_pm_subtracts_g() -> None:
    case = CASES["reference_evapotranspiration"]
    got = eq.reference_evapotranspiration(**case.inputs, **case.constants)
    assert isinstance(got, float)
    assert got == pytest.approx(5.0, rel=1e-12, abs=1e-12)


def _check_eq_pm_denominator_wind() -> None:
    case = CASES["reference_evapotranspiration"]
    got = eq.reference_evapotranspiration(**case.inputs, **case.constants)
    assert isinstance(got, float)
    assert got == pytest.approx(5.0, rel=1e-12, abs=1e-12)


def _check_bd_wind_lower_bound() -> None:
    assert eq.wind_speed_for_penman_monteith(0.25, WIND_BOUND) == 2.0
    assert eq.wind_speed_for_penman_monteith(2.0, WIND_BOUND) == 2.0
    assert eq.wind_speed_for_penman_monteith(5.0, WIND_BOUND) == 5.0


def _check_bd_shortwave_upper_bound() -> None:
    assert eq.relative_shortwave_radiation(9.0, SHORTWAVE_BOUND) == 7.0
    assert eq.relative_shortwave_radiation(7.0, SHORTWAVE_BOUND) == 7.0
    assert eq.relative_shortwave_radiation(3.0, SHORTWAVE_BOUND) == 3.0


def _check_eq_rejects_bool() -> None:
    try:
        eq.net_radiation(True, 4.0)
    except TypeError:
        return
    raise AssertionError("expected TypeError when boolean is passed as operand")


def _check_eq_missing_before_nonfinite() -> None:
    got = eq.net_radiation(math.inf, NOT_TRANSCRIBED)
    assert isinstance(got, Missing)
    assert got.reason == "MISSING_INPUT"


def _check_eq_all_missing_named() -> None:
    got = eq.net_radiation(NOT_TRANSCRIBED, NOT_TRANSCRIBED)
    assert isinstance(got, Missing)
    assert got.detail is not None
    assert "net_shortwave_radiation" in got.detail
    assert "net_longwave_radiation" in got.detail


def _check_eq_domain_error_not_computable() -> None:
    try:
        angle = eq.sunset_hour_angle(1.5, -1.5)
        ratio = eq.shortwave_ratio(4.0, 0.0)
    except (ArithmeticError, ValueError) as exc:
        raise AssertionError(
            "expected NOT_COMPUTABLE Missing instead of exception"
        ) from exc
    assert isinstance(angle, Missing) and angle.reason == "NOT_COMPUTABLE"
    assert isinstance(ratio, Missing) and ratio.reason == "NOT_COMPUTABLE"


def _check_eq_day_of_year_rejects_datetime() -> None:
    assert eq.day_of_year(dt.date(2004, 3, 1)) == 61
    try:
        eq.day_of_year(dt.datetime(2001, 1, 1))
    except TypeError:
        return
    raise AssertionError("expected TypeError for datetime.datetime")


def _check_eq_pass_through_preserves_missing() -> None:
    got = eq.pass_through("x", NOT_TRANSCRIBED)
    assert got is NOT_TRANSCRIBED


def _check_const_frozen_and_no_defaults() -> None:
    cls = et0_constants.SoilHeatFluxConstants
    for field in dataclasses.fields(cls):
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING
    try:
        cls()  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError when omitting required constant")
    instance = cls(daily_value=3.0)
    try:
        instance.daily_value = 0.0  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("expected FrozenInstanceError on constant mutation")


def _check_const_et0_fields() -> None:
    expected_et0 = {
        "atmospheric_pressure",
        "psychrometric",
        "saturation_vapour_pressure",
        "slope",
        "inverse_relative_distance",
        "solar_declination",
        "extraterrestrial_radiation",
        "clear_sky_radiation",
        "net_shortwave",
        "net_longwave",
        "soil_heat_flux",
        "penman_monteith",
    }
    actual_et0 = {item.name for item in dataclasses.fields(et0_constants.Et0Constants)}
    actual_bounds = {item.name for item in dataclasses.fields(et0_constants.Et0Bounds)}
    assert actual_et0 == expected_et0
    assert actual_bounds == {"relative_shortwave_bound", "wind_speed_bound"}
    assert not (actual_et0 & actual_bounds)


def _check_qty_missing_before_unit() -> None:
    got = quantities.read_input(
        "x", InputValue(NOT_TRANSCRIBED, "PLACEHOLDER other"), "PLACEHOLDER u", GUARD
    )
    assert isinstance(got, Missing)
    assert got.reason == "MISSING_INPUT"


def _check_qty_exact_unit_match() -> None:
    got = quantities.read_input("x", InputValue(3.0, "degc"), "degC", GUARD)
    assert isinstance(got, Missing)
    assert got.reason == GUARD


def _check_qty_wrong_unit_checks_value_type() -> None:
    try:
        quantities.read_input(
            "x", InputValue("3", "PLACEHOLDER other"), "PLACEHOLDER u", GUARD
        )  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("expected TypeError for non-numeric value with wrong unit")


def _check_qty_invalid_reason_raises() -> None:
    try:
        quantities.read_input(
            "x", InputValue(3.0, "PLACEHOLDER u"), "PLACEHOLDER u", "NOT_A_CODE"
        )  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid reason code")


def _check_daily_equal_bound_not_changed() -> None:
    at_wind = day(wind_speed_2m=PLACEHOLDER_BOUNDS.wind_speed_bound.lower_bound)
    assert at_wind.bounds_changed == ()
    at_ratio = day(
        bounds=dataclasses.replace(
            PLACEHOLDER_BOUNDS,
            relative_shortwave_bound=RelativeShortwaveBound(
                upper_bound=day().shortwave_ratio
            ),
        )
    )
    assert at_ratio.bounds_changed == ()


def _check_daily_missing_input_not_named_changed() -> None:
    steps = day(bounds=TIGHT_BOUNDS, wind_speed_2m=NOT_TRANSCRIBED)
    assert isinstance(steps.wind_speed_2m, Missing)
    assert steps.wind_speed_2m.reason == "MISSING_INPUT"
    assert steps.bounds_changed == (RELATIVE_SHORTWAVE_BOUND,)


def _check_daily_bounds_none_behavior() -> None:
    steps = daily.reference_evapotranspiration_day(
        **(DAY | {"wind_speed_2m": 0.5}),
        constants=PLACEHOLDER_CONSTANTS,
        bounds=None,
    )
    assert steps.bounds_not_applied == BOUNDS
    assert steps.bounds_changed == ()
    assert steps.wind_speed_2m == 0.5
    assert steps.relative_shortwave_radiation == steps.shortwave_ratio


def _check_daily_mixed_time_zones() -> None:
    other = series(WIND_SPEED_2M, time_zone="PLACEHOLDER zone")
    result = run(climate(*all_series(**{WIND_SPEED_2M: other})))
    assert len(result) == len(DATES)
    for item in result:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "NOT_COMPUTABLE"
        assert item.value.detail is not None and "time zone" in item.value.detail


def _check_daily_uncovered_day_is_missing_and_kept() -> None:
    short = series(WIND_SPEED_2M, dates=DATES[:2])
    result = run(climate(*all_series(**{WIND_SPEED_2M: short})))
    assert [item.date for item in result] == DATES
    assert isinstance(result[1].value, float)
    assert isinstance(result[2].value, Missing)
    assert result[2].value.reason == "MISSING_INPUT"
    assert result[2].value.detail is not None
    assert "'wind_speed_2m' does not cover this day" in result[2].value.detail


def _check_daily_point_unit_guard() -> None:
    bad_lat = point_value(0.0, "PLACEHOLDER radians")
    result = run(climate(*all_series(), at=point(latitude=bad_lat)))
    assert len(result) == len(DATES)
    for item in result:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "MISSING_INPUT"
        assert item.value.detail is not None
        assert GUARD in item.value.detail
        assert "PLACEHOLDER radians" in item.value.detail


def _check_ref_et0_empty_climate() -> None:
    try:
        got = reference_et0.daily_reference_evapotranspiration(
            _placeholder_ep3_climate(), parameters={}
        )
    except ValueError as exc:
        raise AssertionError("expected {} for climate with no daily series") from exc
    assert got == {}


def _check_ref_et0_applies_bounds() -> None:
    record = _placeholder_ep3_climate(*all_series())
    high_wind_bound = dataclasses.replace(
        PLACEHOLDER_BOUNDS, wind_speed_bound=WindSpeedBound(lower_bound=9.0)
    )
    zero_wind_bound = dataclasses.replace(
        PLACEHOLDER_BOUNDS, wind_speed_bound=WindSpeedBound(lower_bound=0.0)
    )
    bounded = reference_et0.daily_reference_evapotranspiration(
        record, parameters=_placeholder_catalogue(bounds=high_wind_bound)
    )
    unbounded = reference_et0.daily_reference_evapotranspiration(
        record, parameters=_placeholder_catalogue(bounds=zero_wind_bound)
    )
    assert list(bounded) == DATES
    for d_day in DATES:
        assert isinstance(bounded[d_day], float)
        assert isinstance(unbounded[d_day], float)
        assert bounded[d_day] != unbounded[d_day]


def _check_ref_et0_missing_constant_propagates() -> None:
    record = _placeholder_ep3_climate(*all_series())
    missing_id = "soil_heat_flux_daily_value"
    got = reference_et0.daily_reference_evapotranspiration(
        record, parameters=_placeholder_catalogue(omit=missing_id)
    )
    assert list(got) == DATES
    for d_day in DATES:
        value = got[d_day]
        assert isinstance(value, Missing)
        assert value.reason == "MISSING_INPUT"
        assert value.detail is not None and missing_id in value.detail


# --- Baseline tests (pass without monkeypatch, fail on in-source mutants) -----


def test_eq1_baseline_equations_arithmetic_exponents_and_signs():
    _check_eq_slope_square()
    _check_eq_saturation_offset()
    _check_eq_psychrometric_mul()
    _check_eq_pressure_lapse_sign()
    _check_eq_rns_sign()
    _check_eq_rnl_fourth_power()
    _check_eq_rnl_humidity_sign()
    _check_eq_rn_sign()
    _check_eq_soil_heat_flux()
    _check_eq_pm_subtracts_g()
    _check_eq_pm_denominator_wind()


def test_bd1_baseline_d82_bounds_extremes_and_directions():
    _check_bd_wind_lower_bound()
    _check_bd_shortwave_upper_bound()


def test_eq2_baseline_missing_and_nonfinite_precedence_and_naming():
    _check_eq_missing_before_nonfinite()
    _check_eq_all_missing_named()


def test_eq5_baseline_domain_errors_become_not_computable():
    _check_eq_domain_error_not_computable()


def test_eq6_baseline_bool_and_datetime_guards():
    _check_eq_rejects_bool()
    _check_eq_day_of_year_rejects_datetime()


def test_eq8_baseline_pass_through_preserves_missing_identity():
    _check_eq_pass_through_preserves_missing()


def test_r2_baseline_constants_frozen_no_defaults_and_separated_bounds():
    _check_const_frozen_and_no_defaults()
    _check_const_et0_fields()


def test_q2_baseline_unit_guard_precedence_exactness_and_reason_validation():
    _check_qty_missing_before_unit()
    _check_qty_exact_unit_match()
    _check_qty_wrong_unit_checks_value_type()
    _check_qty_invalid_reason_raises()


def test_bd3_baseline_equal_to_bound_and_missing_wind_not_in_bounds_changed():
    _check_daily_equal_bound_not_changed()
    _check_daily_missing_input_not_named_changed()


def test_bd4_baseline_bounds_none_leaves_quantities_unclamped_and_noted():
    _check_daily_bounds_none_behavior()


def test_c5_baseline_mixed_time_zones_return_not_computable():
    _check_daily_mixed_time_zones()


def test_c7_baseline_uncovered_day_kept_as_missing_input():
    _check_daily_uncovered_day_is_missing_and_kept()


def test_c6_baseline_point_unit_guard_rejects_unaccepted_unit():
    _check_daily_point_unit_guard()


def test_d1_baseline_reference_et0_empty_bounds_and_missing_propagation():
    _check_ref_et0_empty_climate()
    _check_ref_et0_applies_bounds()
    _check_ref_et0_missing_constant_propagates()


# --- Injected mutant catalog (>= 22 distinct mutants) -------------------------


@dataclasses.dataclass(frozen=True)
class MutantCase:
    """One injected arithmetic, boundary, guard, or integration mutant."""

    mutant_id: str
    inject: Callable[[pytest.MonkeyPatch], None]
    check: Callable[[], None]


def _patch_attr(
    target: object, attr: str, replacement: object
) -> Callable[[pytest.MonkeyPatch], None]:
    def _apply(mp: pytest.MonkeyPatch) -> None:
        mp.setattr(target, attr, replacement)

    return _apply


def _mut_psychrometric(pressure: Any, constants: Any) -> Any:
    operands = eq._inputs(pressure=pressure) | eq._constants(
        "psychrometric", constants, et0_constants.PsychrometricConstants
    )
    return eq._compute(
        "psychrometric constant", operands, lambda: constants.coefficient / pressure
    )


def _mut_atmospheric_pressure(elevation: Any, constants: Any) -> Any:
    operands = eq._inputs(elevation=elevation) | eq._constants(
        "atmospheric_pressure", constants, et0_constants.AtmosphericPressureConstants
    )
    return eq._compute(
        "atmospheric pressure",
        operands,
        lambda: (
            constants.sea_level_pressure
            * (
                (constants.reference_temperature + constants.lapse_rate * elevation)
                / constants.reference_temperature
            )
            ** constants.exponent
        ),
    )


def _mut_net_shortwave(solar_radiation: Any, constants: Any) -> Any:
    operands = eq._inputs(solar_radiation=solar_radiation) | eq._constants(
        "net_shortwave", constants, et0_constants.NetShortwaveConstants
    )
    return eq._compute(
        "net shortwave radiation",
        operands,
        lambda: solar_radiation + constants.albedo * solar_radiation,
    )


def _mut_net_longwave_humidity_sign(
    tmax: Any, tmin: Any, ea: Any, rel_rs: Any, constants: Any
) -> Any:
    operands = eq._inputs(
        temperature_max=tmax,
        temperature_min=tmin,
        actual_vapour_pressure=ea,
        relative_shortwave_radiation=rel_rs,
    ) | eq._constants("net_longwave", constants, et0_constants.NetLongwaveConstants)

    def formula() -> object:
        c = constants
        emission = (
            c.stefan_boltzmann
            * (
                (eq._fourth_power(tmax + c.kelvin_offset))
                + (eq._fourth_power(tmin + c.kelvin_offset))
            )
            / 2.0
        )
        humidity = c.humidity_intercept + c.humidity_slope * math.sqrt(ea)
        cloudiness = c.cloudiness_multiplier * rel_rs - c.cloudiness_offset
        return emission * humidity * cloudiness

    return eq._compute("net longwave radiation", operands, formula)


def _mut_net_radiation_add(rns: Any, rnl: Any) -> Any:
    operands = eq._inputs(net_shortwave_radiation=rns, net_longwave_radiation=rnl)
    return eq._compute("net radiation", operands, lambda: rns + rnl)


def _mut_pm_adds_g(
    *,
    slope: Any,
    net_radiation: Any,
    soil_heat_flux: Any,
    psychrometric_constant: Any,
    mean_temperature: Any,
    wind_speed_2m: Any,
    mean_saturation_vapour_pressure: Any,
    actual_vapour_pressure: Any,
    constants: Any,
) -> Any:
    c = constants
    gamma = psychrometric_constant
    radiative = c.radiation_factor * slope * (net_radiation + soil_heat_flux)
    aerodynamic = (
        gamma
        * (c.numerator_constant / (mean_temperature + c.kelvin_offset))
        * wind_speed_2m
        * (mean_saturation_vapour_pressure - actual_vapour_pressure)
    )
    denominator = slope + gamma + gamma * c.denominator_constant * wind_speed_2m
    return (radiative + aerodynamic) / denominator


def _mut_pm_drops_denom_wind(
    *,
    slope: Any,
    net_radiation: Any,
    soil_heat_flux: Any,
    psychrometric_constant: Any,
    mean_temperature: Any,
    wind_speed_2m: Any,
    mean_saturation_vapour_pressure: Any,
    actual_vapour_pressure: Any,
    constants: Any,
) -> Any:
    c = constants
    gamma = psychrometric_constant
    radiative = c.radiation_factor * slope * (net_radiation - soil_heat_flux)
    aerodynamic = (
        gamma
        * (c.numerator_constant / (mean_temperature + c.kelvin_offset))
        * wind_speed_2m
        * (mean_saturation_vapour_pressure - actual_vapour_pressure)
    )
    denominator = slope + gamma
    return (radiative + aerodynamic) / denominator


def _mut_wind_min(wind_speed_2m: Any, constants: Any) -> Any:
    return min(wind_speed_2m, constants.lower_bound)


def _mut_shortwave_max(ratio: Any, constants: Any) -> Any:
    return max(ratio, constants.upper_bound)


def _mut_check_operands_nonfinite_first(operands: dict[str, object]) -> Missing | None:
    not_finite = [
        f"{label} is not a finite number"
        for label, value in operands.items()
        if not isinstance(value, Missing) and not eq._is_finite(value)  # type: ignore[arg-type]
    ]
    if not_finite:
        return Missing(reason="NOT_COMPUTABLE", detail="; ".join(not_finite))
    missing = [
        eq._describe_missing(label, value)
        for label, value in operands.items()
        if isinstance(value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing))
    return None


def _mut_check_operands_only_first_missing(
    operands: dict[str, object],
) -> Missing | None:
    missing = [
        eq._describe_missing(label, value)
        for label, value in operands.items()
        if isinstance(value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail=missing[0])
    return None


def _mut_compute_no_domain_catch(
    what: str, operands: dict[str, object], formula: Callable[[], object]
) -> Any:
    absent = eq.check_operands(operands)
    if absent is not None:
        return absent
    return float(formula())  # type: ignore[arg-type]


def _mut_day_of_year_allows_datetime(date: Any) -> int:
    if not isinstance(date, dt.date):
        raise TypeError("date must be a datetime.date")
    return date.timetuple().tm_yday


def _mut_pass_through_rewraps(name: str, value: object) -> Any:
    absent = eq.check_operands({f"input '{name}'": value})
    return float(value) if absent is None else absent  # type: ignore[arg-type]


@dataclasses.dataclass
class _MutantSoilConstants:
    daily_value: float = 0.0


@dataclasses.dataclass(frozen=True)
class _MutantEt0Constants:
    atmospheric_pressure: Any
    psychrometric: Any
    saturation_vapour_pressure: Any
    slope: Any
    inverse_relative_distance: Any
    solar_declination: Any
    extraterrestrial_radiation: Any
    clear_sky_radiation: Any
    net_shortwave: Any
    net_longwave: Any
    penman_monteith: Any


def _mut_read_input_unit_before_missing(
    name: str, item: InputValue, accepted_unit: str, unit_guard_reason: Any
) -> Any:
    if item.unit != accepted_unit:
        return Missing(reason=unit_guard_reason, detail=f"input '{name}' wrong unit")
    if isinstance(item.value, Missing):
        return quantities.check_operands({f"input '{name}'": item.value})
    return float(item.value)


def _mut_read_input_case_insensitive(
    name: str, item: InputValue, accepted_unit: str, unit_guard_reason: Any
) -> Any:
    if isinstance(item.value, Missing):
        return quantities.check_operands({f"input '{name}'": item.value})
    if item.unit.lower() != accepted_unit.lower():
        return Missing(reason=unit_guard_reason, detail=f"input '{name}' wrong unit")
    return float(item.value)


def _mut_read_input_skips_value_type_on_wrong_unit(
    name: str, item: InputValue, accepted_unit: str, unit_guard_reason: Any
) -> Any:
    if isinstance(item.value, Missing):
        return quantities.check_operands({f"input '{name}'": item.value})
    if item.unit != accepted_unit:
        return Missing(reason=unit_guard_reason, detail=f"input '{name}' wrong unit")
    return float(item.value)


_REAL_FROM_CLIMATE = daily._from_climate
_REAL_REFERENCE_ET0_DAY = daily.reference_evapotranspiration_day


def _mut_day_drops_bounds_note(**kwargs: Any) -> Any:
    steps = _REAL_REFERENCE_ET0_DAY(**kwargs)
    return dataclasses.replace(steps, bounds_not_applied=())


def _mut_from_climate_drops_uncovered_day(
    climate_record: Any,
    *,
    point_units: Any,
    constants: Any,
    bounds: Any,
    unit_guard_reason: Any,
) -> Any:
    results = _REAL_FROM_CLIMATE(
        climate_record,
        point_units=point_units,
        constants=constants,
        bounds=bounds,
        unit_guard_reason=unit_guard_reason,
    )
    return [item for item in results if not isinstance(item.value, Missing)]


def _mut_daily_read_input_skips_point_unit(
    name: str, item: InputValue, accepted_unit: str, unit_guard_reason: Any
) -> Any:
    if isinstance(item.value, Missing):
        return quantities.check_operands({f"input '{name}'": item.value})
    return float(item.value)


def _mut_ref_et0_no_empty_guard(climate_record: Any, *, parameters: dict) -> Any:
    _ = min(s.start_date for s in climate_record.daily_series)
    return {}


def _mut_ref_et0_calls_unbounded(
    climate_record: Any,
    *,
    point_units: Any,
    constants: Any,
    bounds: Any,
    unit_guard_reason: Any,
) -> Any:
    return daily.reference_evapotranspiration_from_climate(
        climate_record,
        point_units=point_units,
        constants=constants,
        unit_guard_reason=unit_guard_reason,
    )


MUTANTS: list[MutantCase] = [
    MutantCase(
        "M01_eq_slope_missing_square",
        _patch_attr(eq, "_square", lambda v: v),
        _check_eq_slope_square,
    ),
    MutantCase(
        "M02_eq_saturation_subtracts_offset",
        _patch_attr(
            eq,
            "_saturation_formula",
            lambda t, c: c.scale * math.exp(c.numerator * t / (t - c.offset)),
        ),
        _check_eq_saturation_offset,
    ),
    MutantCase(
        "M03_eq_psychrometric_div_instead_of_mul",
        _patch_attr(eq, "psychrometric_constant", _mut_psychrometric),
        _check_eq_psychrometric_mul,
    ),
    MutantCase(
        "M04_eq_pressure_lapse_sign_flip",
        _patch_attr(eq, "atmospheric_pressure", _mut_atmospheric_pressure),
        _check_eq_pressure_lapse_sign,
    ),
    MutantCase(
        "M05_eq_rns_sign_flip",
        _patch_attr(eq, "net_shortwave_radiation", _mut_net_shortwave),
        _check_eq_rns_sign,
    ),
    MutantCase(
        "M06_eq_rnl_fourth_power_to_square",
        _patch_attr(eq, "_fourth_power", eq._square),
        _check_eq_rnl_fourth_power,
    ),
    MutantCase(
        "M07_eq_rnl_humidity_sign_flip",
        _patch_attr(eq, "net_longwave_radiation", _mut_net_longwave_humidity_sign),
        _check_eq_rnl_humidity_sign,
    ),
    MutantCase(
        "M08_eq_rn_sign_flip",
        _patch_attr(eq, "net_radiation", _mut_net_radiation_add),
        _check_eq_rn_sign,
    ),
    MutantCase(
        "M09_eq_soil_heat_flux_hardcoded_zero",
        _patch_attr(eq, "soil_heat_flux_daily", lambda _constants: 0.0),
        _check_eq_soil_heat_flux,
    ),
    MutantCase(
        "M10_eq_pm_adds_soil_heat_flux_g",
        _patch_attr(eq, "reference_evapotranspiration", _mut_pm_adds_g),
        _check_eq_pm_subtracts_g,
    ),
    MutantCase(
        "M11_eq_pm_denominator_drops_wind_term",
        _patch_attr(eq, "reference_evapotranspiration", _mut_pm_drops_denom_wind),
        _check_eq_pm_denominator_wind,
    ),
    MutantCase(
        "M12_eq_wind_bound_inverted_min",
        _patch_attr(eq, "wind_speed_for_penman_monteith", _mut_wind_min),
        _check_bd_wind_lower_bound,
    ),
    MutantCase(
        "M13_eq_shortwave_bound_inverted_max",
        _patch_attr(eq, "relative_shortwave_radiation", _mut_shortwave_max),
        _check_bd_shortwave_upper_bound,
    ),
    MutantCase(
        "M14_eq_bool_accepted_as_number",
        _patch_attr(eq, "_is_number", lambda v: isinstance(v, (int, float))),
        _check_eq_rejects_bool,
    ),
    MutantCase(
        "M15_eq_nonfinite_precedes_missing",
        _patch_attr(eq, "check_operands", _mut_check_operands_nonfinite_first),
        _check_eq_missing_before_nonfinite,
    ),
    MutantCase(
        "M16_eq_missing_only_first_named",
        _patch_attr(eq, "check_operands", _mut_check_operands_only_first_missing),
        _check_eq_all_missing_named,
    ),
    MutantCase(
        "M17_eq_compute_drops_domain_catch",
        _patch_attr(eq, "_compute", _mut_compute_no_domain_catch),
        _check_eq_domain_error_not_computable,
    ),
    MutantCase(
        "M18_eq_day_of_year_allows_datetime",
        _patch_attr(eq, "day_of_year", _mut_day_of_year_allows_datetime),
        _check_eq_day_of_year_rejects_datetime,
    ),
    MutantCase(
        "M19_eq_pass_through_rewraps_missing",
        _patch_attr(eq, "pass_through", _mut_pass_through_rewraps),
        _check_eq_pass_through_preserves_missing,
    ),
    MutantCase(
        "M20_const_group_mutable_with_default",
        _patch_attr(et0_constants, "SoilHeatFluxConstants", _MutantSoilConstants),
        _check_const_frozen_and_no_defaults,
    ),
    MutantCase(
        "M21_const_et0_drops_soil_field",
        _patch_attr(et0_constants, "Et0Constants", _MutantEt0Constants),
        _check_const_et0_fields,
    ),
    MutantCase(
        "M22_qty_unit_checked_before_missing",
        _patch_attr(quantities, "read_input", _mut_read_input_unit_before_missing),
        _check_qty_missing_before_unit,
    ),
    MutantCase(
        "M23_qty_case_insensitive_unit_match",
        _patch_attr(quantities, "read_input", _mut_read_input_case_insensitive),
        _check_qty_exact_unit_match,
    ),
    MutantCase(
        "M24_qty_wrong_unit_skips_value_type_check",
        _patch_attr(
            quantities,
            "read_input",
            _mut_read_input_skips_value_type_on_wrong_unit,
        ),
        _check_qty_wrong_unit_checks_value_type,
    ),
    MutantCase(
        "M25_qty_reason_code_guard_disabled",
        _patch_attr(quantities, "check_reason_code", lambda _r: None),
        _check_qty_invalid_reason_raises,
    ),
    MutantCase(
        "M26_daily_changed_marks_equal_as_changed",
        _patch_attr(
            daily,
            "_changed",
            lambda before, after: (
                not isinstance(before, Missing) and not isinstance(after, Missing)
            ),
        ),
        _check_daily_equal_bound_not_changed,
    ),
    MutantCase(
        "M27_daily_changed_marks_missing_as_changed",
        _patch_attr(daily, "_changed", lambda before, after: after != before),
        _check_daily_missing_input_not_named_changed,
    ),
    MutantCase(
        "M28_daily_bounds_none_omits_not_applied",
        _patch_attr(
            daily, "reference_evapotranspiration_day", _mut_day_drops_bounds_note
        ),
        _check_daily_bounds_none_behavior,
    ),
    MutantCase(
        "M29_daily_mixed_time_zones_not_replaced",
        _patch_attr(daily, "replace", lambda obj, **_kw: obj),
        _check_daily_mixed_time_zones,
    ),
    MutantCase(
        "M30_daily_uncovered_day_dropped",
        _patch_attr(
            daily,
            "_from_climate",
            _mut_from_climate_drops_uncovered_day,
        ),
        _check_daily_uncovered_day_is_missing_and_kept,
    ),
    MutantCase(
        "M31_daily_point_unit_guard_bypassed",
        _patch_attr(daily, "read_input", _mut_daily_read_input_skips_point_unit),
        _check_daily_point_unit_guard,
    ),
    MutantCase(
        "M32_ref_et0_empty_climate_guard_removed",
        _patch_attr(
            reference_et0,
            "daily_reference_evapotranspiration",
            _mut_ref_et0_no_empty_guard,
        ),
        _check_ref_et0_empty_climate,
    ),
    MutantCase(
        "M33_ref_et0_calls_unbounded",
        _patch_attr(
            reference_et0,
            "reference_evapotranspiration_from_climate_with_bounds",
            _mut_ref_et0_calls_unbounded,
        ),
        _check_ref_et0_applies_bounds,
    ),
    MutantCase(
        "M34_ref_et0_missing_constant_returns_zero",
        _patch_attr(ep3, "_site", lambda _cat, _pid, _day: 0.0),
        _check_ref_et0_missing_constant_propagates,
    ),
]


@pytest.mark.parametrize("case", MUTANTS, ids=lambda case: case.mutant_id)
def test_eq1_injected_mutants_are_killed(
    monkeypatch: pytest.MonkeyPatch, case: MutantCase
):
    case.check()
    case.inject(monkeypatch)
    with pytest.raises(AssertionError):
        case.check()


def test_eq1_mutant_harness_also_kills_via_unittest_mock_patch():
    assert len(MUTANTS) >= 22
    with patch.object(eq, "_square", lambda v: v):
        with pytest.raises(AssertionError):
            _check_eq_slope_square()
