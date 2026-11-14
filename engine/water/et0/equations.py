"""One function per intermediate quantity of the daily FAO-56 Penman-Monteith method.

Status: PROPOSED (blueprint section 3.7). The method is decision D44 of issue
#77. The equation numbers are those issue #13 reports (section 4). The forms
written in the docstrings were written by a builder session and are PROPOSED:
a person checks each against the equation of the method before any number of
this module is used (engine/water/et0/README.md, OPEN list).

Every constant of the method is an argument supplied by the caller
(engine/water/et0/constants.py). This module holds no number. The only
mathematical constant it uses is pi (``math.pi``, ``math.tau`` and
``math.radians``); means are taken with ``statistics.fmean``, squares and
fourth powers are written as products.

Rules of every function here (rule G4 of contracts/ENTRYPOINTS.md, section 3
of contracts/CONVENTIONS.md):

- An operand (an input or a constant) is a number, or the ``Missing`` of
  contracts/results/models.py. Anything else is a defect of the caller and
  raises ``TypeError``.
- An operand that is missing gives a missing result, reason
  ``MISSING_INPUT``, whose ``detail`` names every missing operand. Never
  zero and never a default.
- An operand that is not a finite number is not computed: the result is
  missing, reason ``NOT_COMPUTABLE``, and ``detail`` names it.
- When the arithmetic has no finite real result (division by zero, the
  arc cosine or the square root outside its domain, a power that is not
  real, an overflow), the result is missing, reason ``NOT_COMPUTABLE``.
  This is arithmetic, not a limit of the method.
- The only limits of the method applied here are the two bounds of
  decision D82 of issue #77 (PC-4), each in its own function and each with
  its value supplied by the caller: ``relative_shortwave_radiation`` (the
  ratio of Eq. 39, bounded above) and ``wind_speed_for_penman_monteith``
  (the wind speed of Eq. 6, bounded below). No other limit the method may
  state is applied (README, OPEN list).

The temperatures are in the unit of the climate quantities that the caller
checked (engine/water/et0/quantities.py); the functions do not know units.

Pure functions: no file, no network, no clock, no global state.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Callable
from dataclasses import fields

from contracts.results.models import Missing

from .constants import (
    AtmosphericPressureConstants,
    ClearSkyRadiationConstants,
    ExtraterrestrialRadiationConstants,
    InverseRelativeDistanceConstants,
    NetLongwaveConstants,
    NetShortwaveConstants,
    PenmanMonteithConstants,
    PsychrometricConstants,
    RelativeShortwaveBound,
    SaturationVapourPressureConstants,
    SlopeConstants,
    SoilHeatFluxConstants,
    SolarDeclinationConstants,
    WindSpeedBound,
)

# An operand or a result: a number, or missing with its reason (C3.1).
Quantity = float | Missing


# --- shared checks ------------------------------------------------------------


def _is_number(value: object) -> bool:
    """True for an ``int`` or a ``float``; a boolean is not a number here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large to be a float
        return False


def _describe_missing(label: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"{label} is missing (reason {missing.reason})"
    return f"{label} is missing (reason {missing.reason}: {missing.detail})"


def _inputs(**operands: object) -> dict[str, object]:
    return {f"input '{name}'": value for name, value in operands.items()}


def _constants(group: str, constants: object, expected: type) -> dict[str, object]:
    if not isinstance(constants, expected):
        raise TypeError(
            f"the constants of '{group}' must be a {expected.__name__}, "
            f"not {type(constants).__name__}"
        )
    return {
        f"constant '{group}.{item.name}'": getattr(constants, item.name)
        for item in fields(constants)
    }


def check_operands(operands: dict[str, object]) -> Missing | None:
    """Raise for an operand of the wrong type; return why no value, or ``None``."""
    for label, value in operands.items():
        if not isinstance(value, Missing) and not _is_number(value):
            raise TypeError(
                f"{label} must be a number or the Missing of "
                f"contracts/results/models.py, not {type(value).__qualname__} "
                f"of module {type(value).__module__}"
            )
    missing = [
        _describe_missing(label, value)
        for label, value in operands.items()
        if isinstance(value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing))
    not_finite = [
        f"{label} is not a finite number"
        for label, value in operands.items()
        if not _is_finite(value)
    ]
    if not_finite:
        return Missing(reason="NOT_COMPUTABLE", detail="; ".join(not_finite))
    return None


def _compute(
    what: str, operands: dict[str, object], formula: Callable[[], object]
) -> Quantity:
    """Check the operands, then evaluate ``formula``; a missing result names ``what``."""
    absent = check_operands(operands)
    if absent is not None:
        return absent
    try:
        result = formula()
    except (ArithmeticError, ValueError):
        result = None
    if not _is_number(result) or not _is_finite(result):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"the {what} has no finite real value for these operands",
        )
    return float(result)


def pass_through(name: str, value: object) -> Quantity:
    """An input given as such: a missing value unchanged, a number checked.

    A value that is not a number or a ``Missing`` raises ``TypeError``; a
    number that is not finite is missing, reason ``NOT_COMPUTABLE``.
    """
    if isinstance(value, Missing):
        return value
    absent = check_operands({f"input '{name}'": value})
    return float(value) if absent is None else absent


def _square(value: float) -> float:
    return value * value


def _fourth_power(value: float) -> float:
    return _square(value) * _square(value)


# --- atmospheric parameters -------------------------------------------------------


def atmospheric_pressure(
    elevation: Quantity, constants: AtmosphericPressureConstants
) -> Quantity:
    """Atmospheric pressure from elevation (FAO-56 Eq. 7; derived, D30). Form PROPOSED.

    ``sea_level_pressure * ((reference_temperature - lapse_rate * elevation)
    / reference_temperature) ** exponent``.
    """
    operands = _inputs(elevation=elevation) | _constants(
        "atmospheric_pressure", constants, AtmosphericPressureConstants
    )

    def formula() -> object:
        c = constants
        ratio = (
            c.reference_temperature - c.lapse_rate * elevation
        ) / c.reference_temperature
        return c.sea_level_pressure * ratio**c.exponent

    return _compute("atmospheric pressure", operands, formula)


def psychrometric_constant(
    pressure: Quantity, constants: PsychrometricConstants
) -> Quantity:
    """Psychrometric constant (FAO-56 Eq. 8). Form PROPOSED: ``coefficient * pressure``."""
    operands = _inputs(pressure=pressure) | _constants(
        "psychrometric", constants, PsychrometricConstants
    )
    return _compute(
        "psychrometric constant", operands, lambda: constants.coefficient * pressure
    )


# --- temperature and humidity --------------------------------------------------------


def mean_temperature(temperature_max: Quantity, temperature_min: Quantity) -> Quantity:
    """Mean air temperature of the day, from the maximum and the minimum (D30).

    Form PROPOSED: the arithmetic mean of the two. Issue #13 reports that
    Example 18 cites no equation for this row and that Eq. 9 sits under the
    heading "Air temperature".
    """
    operands = _inputs(temperature_max=temperature_max, temperature_min=temperature_min)
    return _compute(
        "mean temperature",
        operands,
        lambda: statistics.fmean([temperature_max, temperature_min]),
    )


def _saturation_formula(
    temperature: float, constants: SaturationVapourPressureConstants
) -> float:
    c = constants
    return c.scale * math.exp(c.numerator * temperature / (temperature + c.offset))


def saturation_vapour_pressure(
    temperature: Quantity, constants: SaturationVapourPressureConstants
) -> Quantity:
    """Saturation vapour pressure at a temperature (FAO-56 Eq. 11). Form PROPOSED.

    ``scale * exp(numerator * temperature / (temperature + offset))``.
    """
    operands = _inputs(temperature=temperature) | _constants(
        "saturation_vapour_pressure", constants, SaturationVapourPressureConstants
    )
    return _compute(
        "saturation vapour pressure",
        operands,
        lambda: _saturation_formula(temperature, constants),
    )


def mean_saturation_vapour_pressure(
    temperature_max: Quantity,
    temperature_min: Quantity,
    constants: SaturationVapourPressureConstants,
) -> Quantity:
    """Mean saturation vapour pressure of the day (Eq. 11 twice, then the mean; Eq. 12).

    Form PROPOSED: the arithmetic mean of Eq. 11 at the maximum and at the
    minimum temperature.
    """
    operands = _inputs(
        temperature_max=temperature_max, temperature_min=temperature_min
    ) | _constants(
        "saturation_vapour_pressure", constants, SaturationVapourPressureConstants
    )
    return _compute(
        "mean saturation vapour pressure",
        operands,
        lambda: statistics.fmean(
            [
                _saturation_formula(temperature_max, constants),
                _saturation_formula(temperature_min, constants),
            ]
        ),
    )


def slope_of_saturation_vapour_pressure_curve(
    temperature: Quantity,
    saturation_constants: SaturationVapourPressureConstants,
    constants: SlopeConstants,
) -> Quantity:
    """Slope of the saturation vapour pressure curve (FAO-56 Eq. 13). Form PROPOSED.

    ``multiplier * e(T) / ((T + offset) * (T + offset))``, with ``e(T)`` and
    ``offset`` those of Eq. 11. Which temperature it is evaluated at is
    chosen by the caller; the composition of engine/water/et0/daily.py uses
    the mean temperature (PROPOSED).
    """
    operands = (
        _inputs(temperature=temperature)
        | _constants(
            "saturation_vapour_pressure",
            saturation_constants,
            SaturationVapourPressureConstants,
        )
        | _constants("slope", constants, SlopeConstants)
    )
    return _compute(
        "slope of the saturation vapour pressure curve",
        operands,
        lambda: (
            constants.multiplier
            * _saturation_formula(temperature, saturation_constants)
            / _square(temperature + saturation_constants.offset)
        ),
    )


def actual_vapour_pressure_from_dew_point(
    dew_point_temperature: Quantity, constants: SaturationVapourPressureConstants
) -> Quantity:
    """Actual vapour pressure from the dew point temperature (D25). Form PROPOSED, OPEN.

    PROPOSED: Eq. 11 evaluated at the dew point. Decision D25 of issue #77
    leaves this route "to be supplied by a person", read in the method's
    text; issue #13 does not report it, so its equation number is OPEN.
    """
    operands = _inputs(dew_point_temperature=dew_point_temperature) | _constants(
        "saturation_vapour_pressure", constants, SaturationVapourPressureConstants
    )
    return _compute(
        "actual vapour pressure",
        operands,
        lambda: _saturation_formula(dew_point_temperature, constants),
    )


def vapour_pressure_deficit(
    mean_saturation_vapour_pressure: Quantity, actual_vapour_pressure: Quantity
) -> Quantity:
    """Vapour pressure deficit (block of Example 18; Box 7). Form PROPOSED: ``es - ea``."""
    operands = _inputs(
        mean_saturation_vapour_pressure=mean_saturation_vapour_pressure,
        actual_vapour_pressure=actual_vapour_pressure,
    )
    return _compute(
        "vapour pressure deficit",
        operands,
        lambda: mean_saturation_vapour_pressure - actual_vapour_pressure,
    )


# --- radiation -----------------------------------------------------------------------


def day_of_year(date: dt.date) -> int:
    """Number of the day in its calendar year, from the date of the series.

    PROPOSED: the ordinal day of the calendar year (``date.timetuple().tm_yday``).
    Example 18 reads it from Table 2.5 (issue #13, section 4); a person checks
    that the two agree, leap years included (README, OPEN list).
    """
    if isinstance(date, dt.datetime) or not isinstance(date, dt.date):
        raise TypeError(f"date must be a datetime.date, not {type(date).__name__}")
    return date.timetuple().tm_yday


def latitude_in_radians(latitude_decimal_degrees: Quantity) -> Quantity:
    """Latitude in radians, from decimal degrees (FAO-56 Eq. 22). Form PROPOSED.

    Uses the definition of the radian (``math.radians``). The caller has
    checked that the latitude arrived in the unit string that means decimal
    degrees (engine/water/et0/quantities.py).
    """
    operands = _inputs(latitude_decimal_degrees=latitude_decimal_degrees)
    return _compute(
        "latitude in radians", operands, lambda: math.radians(latitude_decimal_degrees)
    )


def inverse_relative_distance(
    day_of_year: Quantity, constants: InverseRelativeDistanceConstants
) -> Quantity:
    """Inverse relative distance Earth-Sun (FAO-56 Eq. 23). Form PROPOSED.

    ``offset + amplitude * cos(tau * J / days_in_year)``.
    """
    operands = _inputs(day_of_year=day_of_year) | _constants(
        "inverse_relative_distance", constants, InverseRelativeDistanceConstants
    )
    return _compute(
        "inverse relative distance Earth-Sun",
        operands,
        lambda: (
            constants.offset
            + constants.amplitude
            * math.cos(math.tau * day_of_year / constants.days_in_year)
        ),
    )


def solar_declination(
    day_of_year: Quantity, constants: SolarDeclinationConstants
) -> Quantity:
    """Solar declination (FAO-56 Eq. 24). Form PROPOSED.

    ``amplitude * sin(tau * J / days_in_year - phase)``.
    """
    operands = _inputs(day_of_year=day_of_year) | _constants(
        "solar_declination", constants, SolarDeclinationConstants
    )
    return _compute(
        "solar declination",
        operands,
        lambda: (
            constants.amplitude
            * math.sin(
                math.tau * day_of_year / constants.days_in_year - constants.phase
            )
        ),
    )


def sunset_hour_angle(
    latitude_radians: Quantity, solar_declination: Quantity
) -> Quantity:
    """Sunset hour angle (FAO-56 Eq. 25 or 26, as issue #13 reports). Form PROPOSED.

    ``arccos(-tan(latitude) * tan(declination))``. Where the arc cosine has
    no real value the result is missing, ``NOT_COMPUTABLE``; what the method
    says for those days is OPEN (README).
    """
    operands = _inputs(
        latitude_radians=latitude_radians, solar_declination=solar_declination
    )
    return _compute(
        "sunset hour angle",
        operands,
        lambda: math.acos(-math.tan(latitude_radians) * math.tan(solar_declination)),
    )


def extraterrestrial_radiation(
    latitude_radians: Quantity,
    inverse_relative_distance: Quantity,
    solar_declination: Quantity,
    sunset_hour_angle: Quantity,
    constants: ExtraterrestrialRadiationConstants,
) -> Quantity:
    """Extraterrestrial radiation for daily periods (FAO-56 Eq. 21). Form PROPOSED.

    ``time_factor / pi * solar_constant * dr * (ws * sin(phi) * sin(delta) +
    cos(phi) * cos(delta) * sin(ws))``.
    """
    operands = _inputs(
        latitude_radians=latitude_radians,
        inverse_relative_distance=inverse_relative_distance,
        solar_declination=solar_declination,
        sunset_hour_angle=sunset_hour_angle,
    ) | _constants(
        "extraterrestrial_radiation", constants, ExtraterrestrialRadiationConstants
    )

    def formula() -> object:
        phi, delta, ws = latitude_radians, solar_declination, sunset_hour_angle
        bracket = ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(
            delta
        ) * math.sin(ws)
        return (
            constants.time_factor
            / math.pi
            * constants.solar_constant
            * inverse_relative_distance
            * bracket
        )

    return _compute("extraterrestrial radiation", operands, formula)


def clear_sky_solar_radiation(
    elevation: Quantity,
    extraterrestrial_radiation: Quantity,
    constants: ClearSkyRadiationConstants,
) -> Quantity:
    """Clear-sky solar radiation (FAO-56 Eq. 37, uncalibrated case). Form PROPOSED.

    ``(base + elevation_coefficient * elevation) * Ra``.
    """
    operands = _inputs(
        elevation=elevation, extraterrestrial_radiation=extraterrestrial_radiation
    ) | _constants("clear_sky_radiation", constants, ClearSkyRadiationConstants)
    return _compute(
        "clear-sky solar radiation",
        operands,
        lambda: (
            (constants.base + constants.elevation_coefficient * elevation)
            * extraterrestrial_radiation
        ),
    )


def net_shortwave_radiation(
    solar_radiation: Quantity, constants: NetShortwaveConstants
) -> Quantity:
    """Net shortwave radiation (FAO-56 Eq. 38). Form PROPOSED: ``Rs - albedo * Rs``."""
    operands = _inputs(solar_radiation=solar_radiation) | _constants(
        "net_shortwave", constants, NetShortwaveConstants
    )
    return _compute(
        "net shortwave radiation",
        operands,
        lambda: solar_radiation - constants.albedo * solar_radiation,
    )


def shortwave_ratio(
    solar_radiation: Quantity, clear_sky_radiation: Quantity
) -> Quantity:
    """Ratio of solar radiation to clear-sky solar radiation, before any bound (Eq. 39).

    Form PROPOSED: ``Rs / Rso``.
    """
    operands = _inputs(
        solar_radiation=solar_radiation, clear_sky_radiation=clear_sky_radiation
    )
    return _compute(
        "ratio of solar to clear-sky solar radiation",
        operands,
        lambda: solar_radiation / clear_sky_radiation,
    )


def relative_shortwave_radiation(
    shortwave_ratio: Quantity, constants: RelativeShortwaveBound
) -> Quantity:
    """Relative shortwave radiation used in Eq. 39, after its bound (D82, PC-4).

    Form PROPOSED: the smaller of ``shortwave_ratio`` and ``upper_bound``.
    Decision D82 of issue #77 (PC-4) states this bound, citing FAO-56
    Eq. 39; its value is supplied by the caller and transcribed in the
    README table of constants (D34). Whether
    the bound changed the ratio is read by comparing the two
    (engine/water/et0/daily.py).
    """
    operands = _inputs(shortwave_ratio=shortwave_ratio) | _constants(
        "relative_shortwave_bound", constants, RelativeShortwaveBound
    )
    return _compute(
        "relative shortwave radiation",
        operands,
        lambda: min(shortwave_ratio, constants.upper_bound),
    )


def net_longwave_radiation(
    temperature_max: Quantity,
    temperature_min: Quantity,
    actual_vapour_pressure: Quantity,
    relative_shortwave_radiation: Quantity,
    constants: NetLongwaveConstants,
) -> Quantity:
    """Net longwave radiation (FAO-56 Eq. 39). Form PROPOSED.

    ``stefan_boltzmann * mean(fourth power of (Tmax + kelvin_offset), fourth
    power of (Tmin + kelvin_offset)) * (humidity_intercept - humidity_slope *
    sqrt(ea)) * (cloudiness_multiplier * relative_shortwave_radiation -
    cloudiness_offset)``. ``relative_shortwave_radiation`` is ``Rs / Rso``
    after the bound of D82 (``relative_shortwave_radiation`` above).
    """
    operands = _inputs(
        temperature_max=temperature_max,
        temperature_min=temperature_min,
        actual_vapour_pressure=actual_vapour_pressure,
        relative_shortwave_radiation=relative_shortwave_radiation,
    ) | _constants("net_longwave", constants, NetLongwaveConstants)

    def formula() -> object:
        c = constants
        emission = c.stefan_boltzmann * statistics.fmean(
            [
                _fourth_power(temperature_max + c.kelvin_offset),
                _fourth_power(temperature_min + c.kelvin_offset),
            ]
        )
        humidity = c.humidity_intercept - c.humidity_slope * math.sqrt(
            actual_vapour_pressure
        )
        cloudiness = (
            c.cloudiness_multiplier * relative_shortwave_radiation - c.cloudiness_offset
        )
        return emission * humidity * cloudiness

    return _compute("net longwave radiation", operands, formula)


def net_radiation(
    net_shortwave_radiation: Quantity, net_longwave_radiation: Quantity
) -> Quantity:
    """Net radiation (FAO-56 Eq. 40). Form PROPOSED: ``Rns - Rnl``."""
    operands = _inputs(
        net_shortwave_radiation=net_shortwave_radiation,
        net_longwave_radiation=net_longwave_radiation,
    )
    return _compute(
        "net radiation",
        operands,
        lambda: net_shortwave_radiation - net_longwave_radiation,
    )


def soil_heat_flux_daily(constants: SoilHeatFluxConstants) -> Quantity:
    """Soil heat flux of a daily period (FAO-56 Eq. 42, case "For day and ten-day periods").

    The value is the constant the caller supplies; nothing is computed.
    """
    operands = _constants("soil_heat_flux", constants, SoilHeatFluxConstants)
    return _compute("soil heat flux", operands, lambda: constants.daily_value)


# --- the equation ----------------------------------------------------------------------


def wind_speed_for_penman_monteith(
    wind_speed_2m: Quantity, constants: WindSpeedBound
) -> Quantity:
    """Wind speed at 2 m used in Eq. 6, after its bound (D82, PC-4).

    Form PROPOSED: the larger of ``wind_speed_2m`` and ``lower_bound``.
    Decision D82 of issue #77 (PC-4) states this bound where Eq. 6 is used;
    its value is supplied by the caller and transcribed in the README table
    of constants (D34).
    Whether the bound changed the wind speed is read by comparing the two
    (engine/water/et0/daily.py).
    """
    operands = _inputs(wind_speed_2m=wind_speed_2m) | _constants(
        "wind_speed_bound", constants, WindSpeedBound
    )
    return _compute(
        "wind speed at 2 m used in the Penman-Monteith equation",
        operands,
        lambda: max(wind_speed_2m, constants.lower_bound),
    )


def reference_evapotranspiration(
    *,
    slope: Quantity,
    net_radiation: Quantity,
    soil_heat_flux: Quantity,
    psychrometric_constant: Quantity,
    mean_temperature: Quantity,
    wind_speed_2m: Quantity,
    mean_saturation_vapour_pressure: Quantity,
    actual_vapour_pressure: Quantity,
    constants: PenmanMonteithConstants,
) -> Quantity:
    """Grass reference evapotranspiration, FAO Penman-Monteith (FAO-56 Eq. 6). Form PROPOSED.

    ``(radiation_factor * D * (Rn - G) + g * (numerator_constant / (T +
    kelvin_offset)) * u2 * (es - ea)) / (D + g + g * denominator_constant *
    u2)``, with ``D`` the slope of the curve, ``g`` the psychrometric
    constant and ``T`` the mean temperature. The wind speed is at 2 m and is
    not converted (D26); the composition of engine/water/et0/daily.py passes
    it after the bound of D82 (``wind_speed_for_penman_monteith``).
    """
    operands = _inputs(
        slope=slope,
        net_radiation=net_radiation,
        soil_heat_flux=soil_heat_flux,
        psychrometric_constant=psychrometric_constant,
        mean_temperature=mean_temperature,
        wind_speed_2m=wind_speed_2m,
        mean_saturation_vapour_pressure=mean_saturation_vapour_pressure,
        actual_vapour_pressure=actual_vapour_pressure,
    ) | _constants("penman_monteith", constants, PenmanMonteithConstants)

    def formula() -> object:
        c = constants
        gamma = psychrometric_constant
        radiative = c.radiation_factor * slope * (net_radiation - soil_heat_flux)
        aerodynamic = (
            gamma
            * (c.numerator_constant / (mean_temperature + c.kelvin_offset))
            * wind_speed_2m
            * (mean_saturation_vapour_pressure - actual_vapour_pressure)
        )
        denominator = slope + gamma + gamma * c.denominator_constant * wind_speed_2m
        return (radiative + aerodynamic) / denominator

    return _compute("reference evapotranspiration", operands, formula)
