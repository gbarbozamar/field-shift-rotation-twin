"""The daily reference evapotranspiration: one day, and every day of a climate record.

Status: PROPOSED (blueprint section 3.7). The order of the steps follows the
order in which Example 18 cites the equations (issue #13, section 4), without
the steps that decisions D25 to D27 of issue #77 replace: wind arrives at 2 m
(no conversion, D26), solar radiation arrives as all-sky solar radiation (no
estimate from sunshine, D27), and humidity arrives as dew point (the
PROPOSED route of D25 replaces relative humidity). Mean temperature and
pressure are derived (D30).

``reference_evapotranspiration_day`` takes the actual vapour pressure as an
input, so that a worked example given another form of humidity can enter it
(the [H2] test). ``reference_evapotranspiration_from_climate`` reads the
daily series of ``SiteClimate`` and computes the actual vapour pressure from
dew point.

Pure functions: no file, no network, no clock. Arguments are not changed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.results.models import Missing, ReasonCode

from . import equations as eq
from .constants import Et0Constants
from .equations import Quantity
from .quantities import (
    ACCEPTED_UNITS,
    CLIMATE_QUANTITIES,
    DEW_POINT,
    SOLAR_RADIATION,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WIND_SPEED_2M,
    InputValue,
    PointUnits,
    check_reason_code,
    read_input,
)


@dataclass(frozen=True)
class Et0Steps:
    """Every intermediate quantity of one day, and the result; each a number or missing."""

    atmospheric_pressure: Quantity
    psychrometric_constant: Quantity
    mean_temperature: Quantity
    slope: Quantity
    mean_saturation_vapour_pressure: Quantity
    actual_vapour_pressure: Quantity
    vapour_pressure_deficit: Quantity
    inverse_relative_distance: Quantity
    solar_declination: Quantity
    sunset_hour_angle: Quantity
    extraterrestrial_radiation: Quantity
    clear_sky_solar_radiation: Quantity
    net_shortwave_radiation: Quantity
    net_longwave_radiation: Quantity
    net_radiation: Quantity
    soil_heat_flux: Quantity
    reference_evapotranspiration: Quantity


def _check_constants(constants: object) -> None:
    if not isinstance(constants, Et0Constants):
        raise TypeError(
            f"argument 'constants' must be an Et0Constants, not {type(constants).__name__}"
        )


def reference_evapotranspiration_day(
    *,
    day_of_year: Quantity,
    latitude_radians: Quantity,
    elevation: Quantity,
    temperature_max: Quantity,
    temperature_min: Quantity,
    actual_vapour_pressure: Quantity,
    wind_speed_2m: Quantity,
    solar_radiation: Quantity,
    constants: Et0Constants,
) -> Et0Steps:
    """All the steps of one day. Each step is missing, with its reason, when it cannot be computed.

    A missing input makes missing only the steps that depend on it.
    """
    _check_constants(constants)
    c = constants
    pressure = eq.atmospheric_pressure(elevation, c.atmospheric_pressure)
    gamma = eq.psychrometric_constant(pressure, c.psychrometric)
    tmean = eq.mean_temperature(temperature_max, temperature_min)
    delta = eq.slope_of_saturation_vapour_pressure_curve(
        tmean, c.saturation_vapour_pressure, c.slope
    )
    es = eq.mean_saturation_vapour_pressure(
        temperature_max, temperature_min, c.saturation_vapour_pressure
    )
    ea = eq.pass_through("actual_vapour_pressure", actual_vapour_pressure)
    deficit = eq.vapour_pressure_deficit(es, ea)
    dr = eq.inverse_relative_distance(day_of_year, c.inverse_relative_distance)
    declination = eq.solar_declination(day_of_year, c.solar_declination)
    ws = eq.sunset_hour_angle(latitude_radians, declination)
    ra = eq.extraterrestrial_radiation(
        latitude_radians, dr, declination, ws, c.extraterrestrial_radiation
    )
    rso = eq.clear_sky_solar_radiation(elevation, ra, c.clear_sky_radiation)
    rns = eq.net_shortwave_radiation(solar_radiation, c.net_shortwave)
    rnl = eq.net_longwave_radiation(
        temperature_max, temperature_min, ea, solar_radiation, rso, c.net_longwave
    )
    rn = eq.net_radiation(rns, rnl)
    g = eq.soil_heat_flux_daily(c.soil_heat_flux)
    et0 = eq.reference_evapotranspiration(
        slope=delta,
        net_radiation=rn,
        soil_heat_flux=g,
        psychrometric_constant=gamma,
        mean_temperature=tmean,
        wind_speed_2m=wind_speed_2m,
        mean_saturation_vapour_pressure=es,
        actual_vapour_pressure=ea,
        constants=c.penman_monteith,
    )
    return Et0Steps(
        atmospheric_pressure=pressure,
        psychrometric_constant=gamma,
        mean_temperature=tmean,
        slope=delta,
        mean_saturation_vapour_pressure=es,
        actual_vapour_pressure=ea,
        vapour_pressure_deficit=deficit,
        inverse_relative_distance=dr,
        solar_declination=declination,
        sunset_hour_angle=ws,
        extraterrestrial_radiation=ra,
        clear_sky_solar_radiation=rso,
        net_shortwave_radiation=rns,
        net_longwave_radiation=rnl,
        net_radiation=rn,
        soil_heat_flux=g,
        reference_evapotranspiration=et0,
    )


@dataclass(frozen=True)
class DailyReferenceEvapotranspiration:
    """The steps of one day of the climate record, with its date (C6.1)."""

    date: dt.date
    steps: Et0Steps

    @property
    def value(self) -> Quantity:
        """The reference evapotranspiration of the day, or why there is none."""
        return self.steps.reference_evapotranspiration


def _as_results_missing(missing: InputsMissing) -> Missing:
    """The same reason and detail, in the ``Missing`` of contracts/results/models.py."""
    return Missing(reason=missing.reason, detail=missing.detail)


def _point_value(value: Value) -> InputValue:
    """One value of the point of the series (D9), as an input with its unit string."""
    if value.missing is not None:
        return InputValue(value=_as_results_missing(value.missing), unit=value.unit)
    return InputValue(value=value.value, unit=value.unit)


def _missing_for_every_input(missing: Missing) -> dict[str, Quantity]:
    return {quantity: missing for quantity in CLIMATE_QUANTITIES}


def _series_values(
    series: DailySeries, unit_guard_reason: ReasonCode
) -> dict[dt.date, Quantity]:
    """The number or the missing value of each day of one series, after the unit guard."""
    name = series.quantity
    values: dict[dt.date, Quantity] = {}
    for day in series.days:
        if day.missing is not None:
            value: float | Missing = _as_results_missing(day.missing)
        else:
            value = day.value
        values[day.date] = read_input(
            name,
            InputValue(value=value, unit=series.unit),
            ACCEPTED_UNITS[name],
            unit_guard_reason,
        )
    return values


def reference_evapotranspiration_from_climate(
    climate: SiteClimate,
    *,
    point_units: PointUnits,
    constants: Et0Constants,
    unit_guard_reason: ReasonCode,
) -> list[DailyReferenceEvapotranspiration]:
    """The steps of every day of the climate record, in date order.

    The days are every day covered by at least one of the five series of
    engine/water/et0/quantities.py. For each day:

    - a quantity with no series in ``daily_series``: every day misses it,
      reason ``MISSING_INPUT``, naming the quantity (rule G4);
    - a series in a unit string other than the accepted one: every value of
      it is missing with ``unit_guard_reason`` (C1.1, Q11); nothing is
      converted;
    - a day that a series does not cover: that input is missing, reason
      ``MISSING_INPUT``, naming the series (PROPOSED; README, OPEN list);
    - a day that a series holds as missing: that input is missing, reason
      ``MISSING_INPUT``, carrying the reason of the series;
    - the series of the five do not share one time zone: every climate
      input of every day is missing, reason ``NOT_COMPUTABLE``, and so is
      the reference evapotranspiration of every day (C6.3, rule G4).

    Latitude and elevation are read from ``climate.point``, the point the
    series are valid for (D9, D18). They pass through the same unit guard,
    with the unit strings of ``point_units``; a value of the point that is
    missing keeps its reason. Longitude is not read: no equation of the
    method uses it.

    With none of the five series there is no day to answer for, and the list
    is empty (README, OPEN list).
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"argument 'climate' must be a SiteClimate, not {type(climate).__name__}"
        )
    if not isinstance(point_units, PointUnits):
        raise TypeError(
            f"argument 'point_units' must be a PointUnits, not {type(point_units).__name__}"
        )
    _check_constants(constants)
    check_reason_code(unit_guard_reason)

    latitude_degrees = read_input(
        "latitude",
        _point_value(climate.point.latitude),
        point_units.latitude_decimal_degrees,
        unit_guard_reason,
    )
    elevation_value = read_input(
        "elevation",
        _point_value(climate.point.elevation),
        point_units.elevation,
        unit_guard_reason,
    )
    latitude_radians = eq.latitude_in_radians(latitude_degrees)

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in CLIMATE_QUANTITIES
    }
    days = sorted({day.date for series in by_quantity.values() for day in series.days})
    time_zones = {series.time_zone for series in by_quantity.values()}
    one_time_zone = not time_zones or time_zones == {min(time_zones)}
    values = {
        quantity: _series_values(series, unit_guard_reason)
        for quantity, series in by_quantity.items()
    }

    mixed_time_zones = Missing(
        reason="NOT_COMPUTABLE",
        detail="the daily series of the climate record do not share one time zone",
    )

    result: list[DailyReferenceEvapotranspiration] = []
    for date in days:
        if not one_time_zone:
            inputs = _missing_for_every_input(mixed_time_zones)
        else:
            inputs = {}
            for quantity in CLIMATE_QUANTITIES:
                if quantity not in by_quantity:
                    inputs[quantity] = Missing(
                        reason="MISSING_INPUT",
                        detail=f"the climate record has no series '{quantity}'",
                    )
                elif date not in values[quantity]:
                    inputs[quantity] = Missing(
                        reason="MISSING_INPUT",
                        detail=f"the series '{quantity}' does not cover this day",
                    )
                else:
                    inputs[quantity] = values[quantity][date]
        ea = eq.actual_vapour_pressure_from_dew_point(
            inputs[DEW_POINT], constants.saturation_vapour_pressure
        )
        steps = reference_evapotranspiration_day(
            day_of_year=eq.day_of_year(date),
            latitude_radians=latitude_radians,
            elevation=elevation_value,
            temperature_max=inputs[TEMPERATURE_MAX],
            temperature_min=inputs[TEMPERATURE_MIN],
            actual_vapour_pressure=ea,
            wind_speed_2m=inputs[WIND_SPEED_2M],
            solar_radiation=inputs[SOLAR_RADIATION],
            constants=constants,
        )
        if not one_time_zone:
            steps = replace(steps, reference_evapotranspiration=mixed_time_zones)
        result.append(DailyReferenceEvapotranspiration(date=date, steps=steps))
    return result
