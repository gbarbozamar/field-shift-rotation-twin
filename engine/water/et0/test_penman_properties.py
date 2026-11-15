"""Physical property, boundary, symmetry, and missing-propagation tests for daily ET0.

Covers ``engine/water/et0/daily.py``, ``engine/water/et0/equations.py``, and
``engine/water/et0/constants.py``.

Every constant, bound, date, latitude, elevation, and climate input in this
file is a synthetic PLACEHOLDER chosen for clean analytical properties; nothing
is transcribed from FAO-56 Example 37 or any real parameter record.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

import pytest

from contracts.results.models import Missing
from engine.water.et0 import equations as eq
from engine.water.et0.constants import (
    AtmosphericPressureConstants,
    ClearSkyRadiationConstants,
    Et0Bounds,
    Et0Constants,
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
from engine.water.et0.daily import (
    BOUNDS,
    RELATIVE_SHORTWAVE_BOUND,
    WIND_SPEED_BOUND,
    reference_evapotranspiration_day,
    reference_evapotranspiration_from_climate_with_bounds,
)
from engine.water.et0.quantities import (
    CLIMATE_QUANTITIES,
    DEW_POINT,
    SOLAR_RADIATION,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WIND_SPEED_2M,
)
from engine.water.et0.test_daily import (
    ALL_STEPS,
    BOUND_NOTES,
    DATES,
    DEPENDS_ON,
    GUARD,
    POINT_UNITS,
    climate,
    missing_steps,
    point,
    point_value,
    series,
)

# Synthetic PLACEHOLDER constants with positive sensitivities and an even
# calendar cycle (364 days -> exact 182-day half-year shift for symmetry checks).
HALF_CYCLE_DAYS = 182
CYCLE_DAYS = 2.0 * HALF_CYCLE_DAYS

SYNTHETIC_CONSTANTS = Et0Constants(
    atmospheric_pressure=AtmosphericPressureConstants(
        sea_level_pressure=40.0,
        reference_temperature=100.0,
        lapse_rate=0.3,
        exponent=2.0,
    ),
    psychrometric=PsychrometricConstants(coefficient=0.25),
    saturation_vapour_pressure=SaturationVapourPressureConstants(
        scale=2.0, numerator=10.0, offset=40.0
    ),
    slope=SlopeConstants(multiplier=80.0),
    inverse_relative_distance=InverseRelativeDistanceConstants(
        offset=2.0, amplitude=0.2, days_in_year=CYCLE_DAYS
    ),
    solar_declination=SolarDeclinationConstants(
        amplitude=0.3, days_in_year=CYCLE_DAYS, phase=1.2
    ),
    extraterrestrial_radiation=ExtraterrestrialRadiationConstants(
        time_factor=12.0, solar_constant=2.5
    ),
    clear_sky_radiation=ClearSkyRadiationConstants(
        base=0.6, elevation_coefficient=0.004
    ),
    net_shortwave=NetShortwaveConstants(albedo=0.25),
    net_longwave=NetLongwaveConstants(
        stefan_boltzmann=1e-7,
        kelvin_offset=50.0,
        humidity_intercept=2.0,
        humidity_slope=0.2,
        cloudiness_multiplier=1.5,
        cloudiness_offset=0.4,
    ),
    soil_heat_flux=SoilHeatFluxConstants(daily_value=0.4),
    penman_monteith=PenmanMonteithConstants(
        radiation_factor=0.6,
        numerator_constant=200.0,
        kelvin_offset=50.0,
        denominator_constant=0.2,
    ),
)

SYNTHETIC_BOUNDS = Et0Bounds(
    relative_shortwave_bound=RelativeShortwaveBound(upper_bound=0.8),
    wind_speed_bound=WindSpeedBound(lower_bound=1.5),
)

# Synthetic PLACEHOLDER day well inside both D82 bounds.
SYNTHETIC_DAY = {
    "day_of_year": 30,
    "latitude_radians": 0.4,
    "elevation": 10.0,
    "temperature_max": 12.0,
    "temperature_min": 8.0,
    "actual_vapour_pressure": 2.5,
    "wind_speed_2m": 3.0,
    "solar_radiation": 6.0,
}

SYNTHETIC_CLIMATE_VALUES = {
    TEMPERATURE_MAX: 12.0,
    TEMPERATURE_MIN: 8.0,
    DEW_POINT: 2.0,
    WIND_SPEED_2M: 3.0,
    SOLAR_RADIATION: 6.0,
}


def _day(*, constants=SYNTHETIC_CONSTANTS, bounds=SYNTHETIC_BOUNDS, **overrides):
    return reference_evapotranspiration_day(
        **(SYNTHETIC_DAY | overrides), constants=constants, bounds=bounds
    )


def _synthetic_all_series(dates, *, overrides=None):
    overrides = overrides or {}
    built = []
    for quantity in CLIMATE_QUANTITIES:
        if quantity in overrides:
            built.append(overrides[quantity])
            continue
        base = series(quantity, dates=dates)
        base["days"] = [
            {"date": d.isoformat(), "value": SYNTHETIC_CLIMATE_VALUES[quantity]}
            for d in dates
        ]
        built.append(base)
    return built


def _run_climate(
    record,
    *,
    constants=SYNTHETIC_CONSTANTS,
    bounds=SYNTHETIC_BOUNDS,
):
    return reference_evapotranspiration_from_climate_with_bounds(
        record,
        point_units=POINT_UNITS,
        constants=constants,
        bounds=bounds,
        unit_guard_reason=GUARD,
    )


# --- D82 relative shortwave upper clamp & wind speed lower bound --------------


@pytest.mark.parametrize(
    ("raw_ratio", "bound_value", "expected"),
    [
        (0.4, 0.8, 0.4),
        (0.8, 0.8, 0.8),
        (1.4, 0.8, 0.8),
        (3.2, 0.8, 0.8),
    ],
)
def test_bd1_relative_shortwave_upper_clamp_enforced(raw_ratio, bound_value, expected):
    bound = RelativeShortwaveBound(upper_bound=bound_value)
    assert eq.relative_shortwave_radiation(raw_ratio, bound) == expected


@pytest.mark.parametrize(
    ("raw_wind", "bound_value", "expected"),
    [
        (0.0, 1.5, 1.5),
        (0.6, 1.5, 1.5),
        (1.5, 1.5, 1.5),
        (4.2, 1.5, 4.2),
    ],
)
def test_bd1_wind_speed_lower_bound_enforced(raw_wind, bound_value, expected):
    bound = WindSpeedBound(lower_bound=bound_value)
    assert eq.wind_speed_for_penman_monteith(raw_wind, bound) == expected


def test_bd2_relative_shortwave_clamp_caps_net_longwave_in_daily_composition():
    baseline = _day()
    rso = baseline.clear_sky_solar_radiation
    assert isinstance(rso, float) and rso > 0.0
    upper = SYNTHETIC_BOUNDS.relative_shortwave_bound.upper_bound

    # Choose Rs so Rs / Rso exceeds the synthetic upper_bound (0.8).
    rs_high_1 = 1.1 * upper * rso
    rs_high_2 = 1.6 * upper * rso
    steps_1 = _day(solar_radiation=rs_high_1)
    steps_2 = _day(solar_radiation=rs_high_2)

    for steps, rs in ((steps_1, rs_high_1), (steps_2, rs_high_2)):
        assert steps.shortwave_ratio == pytest.approx(rs / rso)
        assert steps.shortwave_ratio > upper
        assert steps.relative_shortwave_radiation == upper
        assert steps.bounds_changed == (RELATIVE_SHORTWAVE_BOUND,)
        assert steps.bounds_not_applied == ()

    # Net longwave is frozen by the clamp when only Rs varies above the bound,
    # while net shortwave still increases linearly with Rs.
    assert steps_1.net_longwave_radiation == pytest.approx(
        steps_2.net_longwave_radiation
    )
    assert steps_2.net_shortwave_radiation > steps_1.net_shortwave_radiation
    assert steps_2.reference_evapotranspiration > steps_1.reference_evapotranspiration


def test_bd2_wind_lower_bound_floors_calm_days_and_makes_et0_invariant_below_bound():
    lower = SYNTHETIC_BOUNDS.wind_speed_bound.lower_bound
    calm = _day(wind_speed_2m=0.0)
    light = _day(wind_speed_2m=0.4 * lower)
    at_bound = _day(wind_speed_2m=lower)

    assert calm.wind_speed_2m == lower
    assert light.wind_speed_2m == lower
    assert calm.bounds_changed == (WIND_SPEED_BOUND,)
    assert light.bounds_changed == (WIND_SPEED_BOUND,)
    assert calm.reference_evapotranspiration == at_bound.reference_evapotranspiration
    assert light.reference_evapotranspiration == at_bound.reference_evapotranspiration


def test_bd3_values_at_d82_bounds_are_unchanged_and_not_flagged():
    baseline = _day()
    rso = baseline.clear_sky_solar_radiation
    upper = SYNTHETIC_BOUNDS.relative_shortwave_bound.upper_bound
    lower = SYNTHETIC_BOUNDS.wind_speed_bound.lower_bound

    at_bounds = _day(solar_radiation=upper * rso, wind_speed_2m=lower)
    assert at_bounds.shortwave_ratio == pytest.approx(upper)
    assert at_bounds.relative_shortwave_radiation == pytest.approx(upper)
    assert at_bounds.wind_speed_2m == lower
    assert at_bounds.bounds_changed == ()
    assert at_bounds.bounds_not_applied == ()


def test_bd4_bounds_none_leaves_excessive_ratio_and_calm_wind_unclamped():
    baseline = _day()
    rso = baseline.clear_sky_solar_radiation
    excessive_rs = 1.5 * SYNTHETIC_BOUNDS.relative_shortwave_bound.upper_bound * rso
    calm_wind = 0.2

    unbounded = _day(bounds=None, solar_radiation=excessive_rs, wind_speed_2m=calm_wind)
    bounded = _day(solar_radiation=excessive_rs, wind_speed_2m=calm_wind)

    assert unbounded.relative_shortwave_radiation == unbounded.shortwave_ratio
    assert unbounded.wind_speed_2m == calm_wind
    assert unbounded.bounds_changed == ()
    assert unbounded.bounds_not_applied == BOUNDS
    assert bounded.bounds_changed == (RELATIVE_SHORTWAVE_BOUND, WIND_SPEED_BOUND)
    assert unbounded.net_longwave_radiation != bounded.net_longwave_radiation
    assert unbounded.reference_evapotranspiration != bounded.reference_evapotranspiration


def test_bd6_climate_record_enforces_d82_bounds_per_day():
    dates = [dt.date(2001, 2, 1), dt.date(2001, 2, 2)]
    low_wind_series = series(WIND_SPEED_2M, dates=dates)
    low_wind_series["days"] = [
        {"date": dates[0].isoformat(), "value": 0.2},  # below lower bound 1.5
        {"date": dates[1].isoformat(), "value": 4.0},  # above lower bound 1.5
    ]
    high_rs_series = series(SOLAR_RADIATION, dates=dates)
    high_rs_series["days"] = [
        {"date": dates[0].isoformat(), "value": 40.0},  # ratio far above 0.8
        {"date": dates[1].isoformat(), "value": 4.0},  # ratio below 0.8
    ]
    record = climate(
        *_synthetic_all_series(
            dates,
            overrides={WIND_SPEED_2M: low_wind_series, SOLAR_RADIATION: high_rs_series},
        )
    )
    results = _run_climate(record)
    assert len(results) == 2

    day0, day1 = results[0].steps, results[1].steps
    assert day0.relative_shortwave_radiation == SYNTHETIC_BOUNDS.relative_shortwave_bound.upper_bound
    assert day0.wind_speed_2m == SYNTHETIC_BOUNDS.wind_speed_bound.lower_bound
    assert day0.bounds_changed == (RELATIVE_SHORTWAVE_BOUND, WIND_SPEED_BOUND)

    assert day1.relative_shortwave_radiation == day1.shortwave_ratio
    assert day1.wind_speed_2m == 4.0
    assert day1.bounds_changed == ()


# --- Leap-day J = 366 --------------------------------------------------------


def test_eq7_leap_day_and_december_31_reach_j_366():
    assert eq.day_of_year(dt.date(2004, 2, 29)) == 60
    assert eq.day_of_year(dt.date(2004, 3, 1)) == 61
    assert eq.day_of_year(dt.date(2004, 12, 31)) == 366
    assert eq.day_of_year(dt.date(2000, 12, 31)) == 366
    assert eq.day_of_year(dt.date(2001, 12, 31)) == 365
    assert eq.day_of_year(dt.date(1900, 12, 31)) == 365


def test_eq7_leap_year_day_366_computes_all_steps_without_missing():
    steps_366 = _day(day_of_year=366)
    steps_365 = _day(day_of_year=365)

    assert missing_steps(steps_366) == set()
    assert isinstance(steps_366.reference_evapotranspiration, float)
    assert math.isfinite(steps_366.reference_evapotranspiration)
    assert steps_366.inverse_relative_distance != steps_365.inverse_relative_distance
    assert steps_366.solar_declination != steps_365.solar_declination

    # On a synthetic 366-day cycle, J=366 completes one full revolution (tau).
    cycle_366_constants = dataclasses.replace(
        SYNTHETIC_CONSTANTS,
        inverse_relative_distance=dataclasses.replace(
            SYNTHETIC_CONSTANTS.inverse_relative_distance, days_in_year=366.0
        ),
        solar_declination=dataclasses.replace(
            SYNTHETIC_CONSTANTS.solar_declination, days_in_year=366.0
        ),
    )
    assert eq.inverse_relative_distance(
        366, cycle_366_constants.inverse_relative_distance
    ) == pytest.approx(
        eq.inverse_relative_distance(0, cycle_366_constants.inverse_relative_distance)
    )
    assert eq.solar_declination(
        366, cycle_366_constants.solar_declination
    ) == pytest.approx(eq.solar_declination(0, cycle_366_constants.solar_declination))


def test_eq7_climate_record_handles_leap_feb_29_and_dec_31_j_366():
    leap_dates = [dt.date(2004, 1, 1) + dt.timedelta(days=n) for n in range(366)]
    record = climate(*_synthetic_all_series(leap_dates))
    results = _run_climate(record)
    assert [item.date for item in results] == leap_dates
    for item in results:
        assert isinstance(item.value, float)
        assert missing_steps(item.steps) == set()

    assert results[59].date == dt.date(2004, 2, 29)
    assert results[-1].date == dt.date(2004, 12, 31)
    assert results[-1].steps.solar_declination == eq.solar_declination(
        366, SYNTHETIC_CONSTANTS.solar_declination
    )


# --- Northern vs southern hemisphere solar symmetry (6-month shift) -----------


@pytest.mark.parametrize("day_j", [1, 45, 91, 130, 182])
@pytest.mark.parametrize("north_lat_rad", [0.15, 0.4, 0.75])
def test_eq1_hemisphere_solar_symmetry_under_half_cycle_shift(day_j, north_lat_rad):
    shifted_j = day_j + HALF_CYCLE_DAYS
    decl_n = eq.solar_declination(day_j, SYNTHETIC_CONSTANTS.solar_declination)
    decl_s = eq.solar_declination(shifted_j, SYNTHETIC_CONSTANTS.solar_declination)
    assert decl_s == pytest.approx(-decl_n)

    ws_n = eq.sunset_hour_angle(north_lat_rad, decl_n)
    ws_s = eq.sunset_hour_angle(-north_lat_rad, decl_s)
    assert ws_s == pytest.approx(ws_n)

    dr_n = eq.inverse_relative_distance(
        day_j, SYNTHETIC_CONSTANTS.inverse_relative_distance
    )
    dr_s = eq.inverse_relative_distance(
        shifted_j, SYNTHETIC_CONSTANTS.inverse_relative_distance
    )
    ra_n = eq.extraterrestrial_radiation(
        north_lat_rad,
        dr_n,
        decl_n,
        ws_n,
        SYNTHETIC_CONSTANTS.extraterrestrial_radiation,
    )
    ra_s = eq.extraterrestrial_radiation(
        -north_lat_rad,
        dr_s,
        decl_s,
        ws_s,
        SYNTHETIC_CONSTANTS.extraterrestrial_radiation,
    )
    # Angular geometry is identical once orbital distance dr is factored out.
    assert ra_s / dr_s == pytest.approx(ra_n / dr_n)


def test_eq1_equator_sunset_hour_angle_is_invariant_across_seasons():
    for day_j in (1, 91, 182, 273, 364):
        decl = eq.solar_declination(day_j, SYNTHETIC_CONSTANTS.solar_declination)
        assert eq.sunset_hour_angle(0.0, decl) == pytest.approx(math.pi / 2.0)


def test_d1_circular_orbit_daily_et0_matches_exactly_across_hemispheres_shifted_half_year():
    # With zero orbital eccentricity (amplitude=0), inverse relative distance is
    # constant so a +lat day and a (-lat, J + HALF_CYCLE_DAYS) day are exact mirrors.
    circular_constants = dataclasses.replace(
        SYNTHETIC_CONSTANTS,
        inverse_relative_distance=dataclasses.replace(
            SYNTHETIC_CONSTANTS.inverse_relative_distance, amplitude=0.0
        ),
    )
    lat_deg = 30.0  # synthetic PLACEHOLDER degrees
    north_date = dt.date(2001, 1, 15)
    south_date = north_date + dt.timedelta(days=HALF_CYCLE_DAYS)  # 6-month shift

    north_record = climate(
        *_synthetic_all_series([north_date]),
        at=point(latitude=point_value(lat_deg, "PLACEHOLDER degrees")),
    )
    south_record = climate(
        *_synthetic_all_series([south_date]),
        at=point(latitude=point_value(-lat_deg, "PLACEHOLDER degrees")),
    )

    north_steps = _run_climate(north_record, constants=circular_constants)[0].steps
    south_steps = _run_climate(south_record, constants=circular_constants)[0].steps

    assert south_steps.solar_declination == pytest.approx(-north_steps.solar_declination)
    assert south_steps.sunset_hour_angle == pytest.approx(north_steps.sunset_hour_angle)
    assert south_steps.extraterrestrial_radiation == pytest.approx(
        north_steps.extraterrestrial_radiation
    )
    assert south_steps.clear_sky_solar_radiation == pytest.approx(
        north_steps.clear_sky_solar_radiation
    )
    assert south_steps.net_radiation == pytest.approx(north_steps.net_radiation)
    assert south_steps.reference_evapotranspiration == pytest.approx(
        north_steps.reference_evapotranspiration
    )


def test_d1_hemisphere_seasonal_peak_reverses_under_6_month_shift():
    # Compare two days separated by half a cycle in both hemispheres.
    north_lat = 0.5
    j_a = 140
    j_b = j_a + HALF_CYCLE_DAYS

    def ra_for(lat_rad: float, day_j: int) -> float:
        dr = eq.inverse_relative_distance(
            day_j, SYNTHETIC_CONSTANTS.inverse_relative_distance
        )
        decl = eq.solar_declination(day_j, SYNTHETIC_CONSTANTS.solar_declination)
        ws = eq.sunset_hour_angle(lat_rad, decl)
        return eq.extraterrestrial_radiation(
            lat_rad,
            dr,
            decl,
            ws,
            SYNTHETIC_CONSTANTS.extraterrestrial_radiation,
        )

    assert ra_for(north_lat, j_a) > ra_for(north_lat, j_b)
    assert ra_for(-north_lat, j_b) > ra_for(-north_lat, j_a)


# --- Strict positive response to radiation, wind, and Tmean-deficit -----------


def test_d1_strict_positive_response_to_solar_radiation_and_net_radiation():
    # Direct equation response to net_radiation.
    et0_rn_low = eq.reference_evapotranspiration(
        slope=0.5,
        net_radiation=2.0,
        soil_heat_flux=0.4,
        psychrometric_constant=9.0,
        mean_temperature=10.0,
        wind_speed_2m=3.0,
        mean_saturation_vapour_pressure=15.0,
        actual_vapour_pressure=2.5,
        constants=SYNTHETIC_CONSTANTS.penman_monteith,
    )
    et0_rn_high = eq.reference_evapotranspiration(
        slope=0.5,
        net_radiation=6.0,
        soil_heat_flux=0.4,
        psychrometric_constant=9.0,
        mean_temperature=10.0,
        wind_speed_2m=3.0,
        mean_saturation_vapour_pressure=15.0,
        actual_vapour_pressure=2.5,
        constants=SYNTHETIC_CONSTANTS.penman_monteith,
    )
    assert et0_rn_high > et0_rn_low

    # Full daily response across an increasing sequence of solar_radiation values
    # spanning both below and above the D82 relative shortwave bound.
    rs_values = [2.0, 4.0, 6.0, 12.0, 20.0, 30.0]
    et0_values = [_day(solar_radiation=rs).reference_evapotranspiration for rs in rs_values]
    for earlier, later in zip(et0_values[:-1], et0_values[1:], strict=True):
        assert later > earlier


def test_d1_strict_positive_response_to_wind_above_d82_lower_bound():
    lower = SYNTHETIC_BOUNDS.wind_speed_bound.lower_bound
    winds = [lower, lower + 0.5, lower + 2.0, lower + 5.0]
    et0_values = [_day(wind_speed_2m=w).reference_evapotranspiration for w in winds]
    for earlier, later in zip(et0_values[:-1], et0_values[1:], strict=True):
        assert later > earlier


def test_d1_strict_positive_response_to_tmean_and_vapour_pressure_deficit():
    # 1. Increasing deficit (es - ea) by lowering ea at fixed temperatures.
    ea_values = [8.0, 5.0, 2.5, 0.5]
    steps_by_ea = [_day(actual_vapour_pressure=ea) for ea in ea_values]
    for wider_ea, tighter_ea in zip(steps_by_ea[1:], steps_by_ea[:-1], strict=True):
        assert wider_ea.vapour_pressure_deficit > tighter_ea.vapour_pressure_deficit
        assert (
            wider_ea.reference_evapotranspiration
            > tighter_ea.reference_evapotranspiration
        )

    # 2. Increasing Tmean (raising Tmax and Tmin together) at fixed ea drives a
    # strictly higher saturation vapour pressure, deficit, slope, and ET0.
    shifts = [0.0, 3.0, 6.0, 9.0]
    steps_by_t = [
        _day(
            temperature_max=SYNTHETIC_DAY["temperature_max"] + dt_shift,
            temperature_min=SYNTHETIC_DAY["temperature_min"] + dt_shift,
        )
        for dt_shift in shifts
    ]
    for cooler, warmer in zip(steps_by_t[:-1], steps_by_t[1:], strict=True):
        assert warmer.mean_temperature > cooler.mean_temperature
        assert warmer.slope > cooler.slope
        assert (
            warmer.mean_saturation_vapour_pressure
            > cooler.mean_saturation_vapour_pressure
        )
        assert warmer.vapour_pressure_deficit > cooler.vapour_pressure_deficit
        assert warmer.reference_evapotranspiration > cooler.reference_evapotranspiration

    # 3. Direct equation check on deficit (es - ea).
    et0_small_vpd = eq.reference_evapotranspiration(
        slope=0.5,
        net_radiation=4.0,
        soil_heat_flux=0.4,
        psychrometric_constant=9.0,
        mean_temperature=10.0,
        wind_speed_2m=3.0,
        mean_saturation_vapour_pressure=6.0,
        actual_vapour_pressure=4.0,
        constants=SYNTHETIC_CONSTANTS.penman_monteith,
    )
    et0_large_vpd = eq.reference_evapotranspiration(
        slope=0.5,
        net_radiation=4.0,
        soil_heat_flux=0.4,
        psychrometric_constant=9.0,
        mean_temperature=10.0,
        wind_speed_2m=3.0,
        mean_saturation_vapour_pressure=12.0,
        actual_vapour_pressure=4.0,
        constants=SYNTHETIC_CONSTANTS.penman_monteith,
    )
    assert et0_large_vpd > et0_small_vpd


# --- Missing propagation across every input quantity --------------------------


@pytest.mark.parametrize("quantity", sorted(SYNTHETIC_DAY))
def test_d2_missing_input_propagates_across_each_day_input_quantity(quantity):
    gap = Missing(reason="SOURCE_UNAVAILABLE", detail=f"PLACEHOLDER missing {quantity}")
    steps = _day(**{quantity: gap})

    assert missing_steps(steps) == DEPENDS_ON[quantity]
    for present_field in ALL_STEPS - BOUND_NOTES - DEPENDS_ON[quantity]:
        assert isinstance(getattr(steps, present_field), float), present_field

    et0 = steps.reference_evapotranspiration
    assert isinstance(et0, Missing)
    assert et0.reason == "MISSING_INPUT"
    assert "SOURCE_UNAVAILABLE" in et0.detail


@pytest.mark.parametrize("quantity", CLIMATE_QUANTITIES)
def test_c4_missing_climate_series_day_propagates_only_to_affected_day(quantity):
    gap_series = series(quantity, dates=DATES, missing_on={DATES[1]})
    record = climate(
        *_synthetic_all_series(DATES, overrides={quantity: gap_series})
    )
    results = _run_climate(record)
    assert [item.date for item in results] == DATES

    assert isinstance(results[0].value, float)
    assert isinstance(results[2].value, float)

    missing_day = results[1]
    assert isinstance(missing_day.value, Missing)
    assert missing_day.value.reason == "MISSING_INPUT"
    assert quantity in missing_day.value.detail
    assert "NO_COVERAGE" in missing_day.value.detail

    # Dew point maps into actual_vapour_pressure in reference_evapotranspiration_day.
    day_input_name = (
        "actual_vapour_pressure" if quantity == DEW_POINT else quantity.removeprefix("air_")
    )
    expected_key = {
        "temperature_max_2m": "temperature_max",
        "temperature_min_2m": "temperature_min",
    }.get(day_input_name, day_input_name)
    assert missing_steps(missing_day.steps) == DEPENDS_ON[expected_key]


@pytest.mark.parametrize("coord", ["latitude", "elevation"])
def test_c6_missing_point_input_propagates_to_every_day_dependent_steps(coord):
    missing_coord = point_value(
        {"reason": "NOT_DECLARED", "detail": f"PLACEHOLDER missing {coord}"},
        "PLACEHOLDER degrees" if coord == "latitude" else "PLACEHOLDER length",
    )
    record = climate(
        *_synthetic_all_series(DATES),
        at=point(**{coord: missing_coord}),
    )
    results = _run_climate(record)
    assert [item.date for item in results] == DATES

    expected_key = "latitude_radians" if coord == "latitude" else "elevation"
    for item in results:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "MISSING_INPUT"
        assert coord in item.value.detail
        assert missing_steps(item.steps) == DEPENDS_ON[expected_key]
