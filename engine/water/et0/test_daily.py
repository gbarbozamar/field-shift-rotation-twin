"""Acceptance test of the daily composition and of the climate inputs.

Covers engine/water/et0/daily.py and engine/water/et0/quantities.py. Run
with ``python -m pytest engine/water/et0/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7) and are listed with the same
codes in engine/water/et0/README.md under "PROPOSED cases".

Every number in this file is a PLACEHOLDER (see test_equations.py). The
unit strings of the five climate quantities are the real ones of
contracts/CLIMATE_QUANTITIES.md, because checking them is the point; the
unit strings of the point are PLACEHOLDER, because they are not decided.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from pathlib import Path

import pytest

from contracts.inputs.site_climate import SiteClimate
from contracts.results.models import Missing
from engine.water.et0 import equations as eq
from engine.water.et0.daily import (
    BOUNDS,
    RELATIVE_SHORTWAVE_BOUND,
    WIND_SPEED_BOUND,
    DailyReferenceEvapotranspiration,
    Et0Steps,
    reference_evapotranspiration_day,
    reference_evapotranspiration_from_climate,
    reference_evapotranspiration_from_climate_with_bounds,
)
from engine.water.et0.quantities import (
    ACCEPTED_UNITS,
    CLIMATE_QUANTITIES,
    DEW_POINT,
    SOLAR_RADIATION,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WIND_SPEED_2M,
    InputValue,
    PointUnits,
    read_input,
)
from engine.water.et0.test_equations import (
    NOT_TRANSCRIBED,
    PLACEHOLDER_BOUNDS,
    PLACEHOLDER_CONSTANTS,
)

ROOT = Path(__file__).resolve().parents[3]
CLIMATE_EXAMPLE = (
    ROOT / "contracts" / "inputs" / "examples" / "PLACEHOLDER_site_climate.json"
)
CLIMATE_QUANTITIES_FILE = ROOT / "contracts" / "CLIMATE_QUANTITIES.md"

GUARD = "CONTROL_FAILED"  # PLACEHOLDER: the reason code of the unit guard is Q11

# PLACEHOLDER inputs of one day. Latitude zero keeps the sunset hour angle defined.
DAY = {
    "day_of_year": 4,
    "latitude_radians": 0.0,
    "elevation": 2.0,
    "temperature_max": 7.0,
    "temperature_min": 3.0,
    "actual_vapour_pressure": 4.0,
    "wind_speed_2m": 4.0,
    "solar_radiation": 5.0,
}

POINT_UNITS = PointUnits(
    latitude_decimal_degrees="PLACEHOLDER degrees", elevation="PLACEHOLDER length"
)
LATITUDE = 0.0  # PLACEHOLDER, in "PLACEHOLDER degrees"
ELEVATION = 2.0  # PLACEHOLDER, in "PLACEHOLDER length"
LONGITUDE = 3.0  # PLACEHOLDER; no equation reads it


def point_value(value, unit):
    """A ``Value`` of the point (contracts/inputs/common.py), present or missing."""
    if isinstance(value, dict):  # a missing part
        return {"value": None, "unit": unit, "missing": value}
    return {
        "value": value,
        "unit": unit,
        "provenance": "OBSERVED",
        "source": "PLACEHOLDER: example data, not a real place, no real source",
        "range_missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
    }


def point(*, latitude=None, elevation=None):
    """The point of the series; each argument replaces one value of it."""
    return {
        "latitude": latitude or point_value(LATITUDE, "PLACEHOLDER degrees"),
        "longitude": point_value(LONGITUDE, "PLACEHOLDER degrees"),
        "elevation": elevation or point_value(ELEVATION, "PLACEHOLDER length"),
    }


# PLACEHOLDER daily values of the five quantities.
VALUES = {
    TEMPERATURE_MAX: 7.0,
    TEMPERATURE_MIN: 3.0,
    DEW_POINT: 5.0,
    WIND_SPEED_2M: 4.0,
    SOLAR_RADIATION: 5.0,
}
START = dt.date(2001, 1, 30)  # PLACEHOLDER dates
DATES = [START + dt.timedelta(days=n) for n in range(3)]


def day(*, bounds=PLACEHOLDER_BOUNDS, **changes):
    return reference_evapotranspiration_day(
        **(DAY | changes), constants=PLACEHOLDER_CONSTANTS, bounds=bounds
    )


def series(quantity, *, unit=None, time_zone="UTC", dates=None, missing_on=()):
    dates = DATES if dates is None else dates
    days = []
    for date in dates:
        if date in missing_on:
            days.append(
                {
                    "date": date.isoformat(),
                    "value": None,
                    "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER gap"},
                }
            )
        else:
            days.append({"date": date.isoformat(), "value": VALUES[quantity]})
    return {
        "quantity": quantity,
        "unit": ACCEPTED_UNITS[quantity] if unit is None else unit,
        "time_zone": time_zone,
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "provenance": "OBSERVED",
        "source": "PLACEHOLDER: example data, no real source",
        "range_missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
        "days": days,
    }


def climate(*daily_series, at=None):
    """A SiteClimate built on the placeholder example, with these series and point."""
    document = json.loads(CLIMATE_EXAMPLE.read_text(encoding="utf-8"))
    document["point"] = point() if at is None else at
    document["daily_series"] = list(daily_series)
    document["monthly_series"] = []
    return SiteClimate.model_validate(document)


def all_series(**overrides):
    return [overrides.get(q, series(q)) for q in CLIMATE_QUANTITIES]


def run(record, **changes):
    arguments = {
        "point_units": POINT_UNITS,
        "constants": PLACEHOLDER_CONSTANTS,
        "bounds": PLACEHOLDER_BOUNDS,
        "unit_guard_reason": GUARD,
    } | changes
    return reference_evapotranspiration_from_climate_with_bounds(record, **arguments)


def run_without_bounds(record, **changes):
    arguments = {
        "point_units": POINT_UNITS,
        "constants": PLACEHOLDER_CONSTANTS,
        "unit_guard_reason": GUARD,
    } | changes
    return reference_evapotranspiration_from_climate(record, **arguments)


# The two fields that say what the bounds did; never missing.
BOUND_NOTES = {"bounds_changed", "bounds_not_applied"}


def missing_steps(steps: Et0Steps) -> set[str]:
    return {
        item.name
        for item in dataclasses.fields(steps)
        if isinstance(getattr(steps, item.name), Missing)
    }


ALL_STEPS = {item.name for item in dataclasses.fields(Et0Steps)}


# --- D1: the composition calls each function on the steps before it ---


def test_d1_each_step_is_its_function_applied_to_the_steps_before_it():
    c = PLACEHOLDER_CONSTANTS
    steps = day()
    pressure = eq.atmospheric_pressure(DAY["elevation"], c.atmospheric_pressure)
    tmean = eq.mean_temperature(DAY["temperature_max"], DAY["temperature_min"])
    es = eq.mean_saturation_vapour_pressure(
        DAY["temperature_max"], DAY["temperature_min"], c.saturation_vapour_pressure
    )
    ea = DAY["actual_vapour_pressure"]
    dr = eq.inverse_relative_distance(DAY["day_of_year"], c.inverse_relative_distance)
    decl = eq.solar_declination(DAY["day_of_year"], c.solar_declination)
    ws = eq.sunset_hour_angle(DAY["latitude_radians"], decl)
    ra = eq.extraterrestrial_radiation(
        DAY["latitude_radians"], dr, decl, ws, c.extraterrestrial_radiation
    )
    rso = eq.clear_sky_solar_radiation(DAY["elevation"], ra, c.clear_sky_radiation)
    ratio = eq.shortwave_ratio(DAY["solar_radiation"], rso)
    relative = eq.relative_shortwave_radiation(
        ratio, PLACEHOLDER_BOUNDS.relative_shortwave_bound
    )
    u2 = eq.wind_speed_for_penman_monteith(
        DAY["wind_speed_2m"], PLACEHOLDER_BOUNDS.wind_speed_bound
    )
    rns = eq.net_shortwave_radiation(DAY["solar_radiation"], c.net_shortwave)
    rnl = eq.net_longwave_radiation(
        DAY["temperature_max"],
        DAY["temperature_min"],
        ea,
        relative,
        c.net_longwave,
    )
    rn = eq.net_radiation(rns, rnl)
    gamma = eq.psychrometric_constant(pressure, c.psychrometric)
    delta = eq.slope_of_saturation_vapour_pressure_curve(
        tmean, c.saturation_vapour_pressure, c.slope
    )
    g = eq.soil_heat_flux_daily(c.soil_heat_flux)
    expected = Et0Steps(
        atmospheric_pressure=pressure,
        psychrometric_constant=gamma,
        mean_temperature=tmean,
        slope=delta,
        mean_saturation_vapour_pressure=es,
        actual_vapour_pressure=ea,
        vapour_pressure_deficit=eq.vapour_pressure_deficit(es, ea),
        inverse_relative_distance=dr,
        solar_declination=decl,
        sunset_hour_angle=ws,
        extraterrestrial_radiation=ra,
        clear_sky_solar_radiation=rso,
        shortwave_ratio=ratio,
        relative_shortwave_radiation=relative,
        net_shortwave_radiation=rns,
        net_longwave_radiation=rnl,
        net_radiation=rn,
        soil_heat_flux=g,
        wind_speed_2m=u2,
        reference_evapotranspiration=eq.reference_evapotranspiration(
            slope=delta,
            net_radiation=rn,
            soil_heat_flux=g,
            psychrometric_constant=gamma,
            mean_temperature=tmean,
            wind_speed_2m=u2,
            mean_saturation_vapour_pressure=es,
            actual_vapour_pressure=ea,
            constants=c.penman_monteith,
        ),
        # PLACEHOLDER day: the ratio is below its bound and the wind above its
        # bound, so neither bound changes anything.
        bounds_changed=(),
        bounds_not_applied=(),
    )
    assert steps == expected
    assert missing_steps(steps) == set()
    assert isinstance(steps.reference_evapotranspiration, float)


# --- D2: a missing input makes missing only the steps that depend on it ---

DEPENDS_ON = {
    "temperature_max": {
        "mean_temperature",
        "slope",
        "mean_saturation_vapour_pressure",
        "vapour_pressure_deficit",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
    "actual_vapour_pressure": {
        "actual_vapour_pressure",
        "vapour_pressure_deficit",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
    "wind_speed_2m": {"wind_speed_2m", "reference_evapotranspiration"},
    "solar_radiation": {
        "shortwave_ratio",
        "relative_shortwave_radiation",
        "net_shortwave_radiation",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
    "elevation": {
        "atmospheric_pressure",
        "psychrometric_constant",
        "clear_sky_solar_radiation",
        "shortwave_ratio",
        "relative_shortwave_radiation",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
    "latitude_radians": {
        "sunset_hour_angle",
        "extraterrestrial_radiation",
        "clear_sky_solar_radiation",
        "shortwave_ratio",
        "relative_shortwave_radiation",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
    "day_of_year": {
        "inverse_relative_distance",
        "solar_declination",
        "sunset_hour_angle",
        "extraterrestrial_radiation",
        "clear_sky_solar_radiation",
        "shortwave_ratio",
        "relative_shortwave_radiation",
        "net_longwave_radiation",
        "net_radiation",
        "reference_evapotranspiration",
    },
}
DEPENDS_ON["temperature_min"] = DEPENDS_ON["temperature_max"]


@pytest.mark.parametrize("name", sorted(DEPENDS_ON))
def test_d2_a_missing_input_makes_missing_only_the_steps_that_depend_on_it(name):
    steps = day(**{name: NOT_TRANSCRIBED})
    assert missing_steps(steps) == DEPENDS_ON[name]
    result = steps.reference_evapotranspiration
    assert result.reason == "MISSING_INPUT"
    assert "NOT_DECLARED" in result.detail


def test_d2_a_missing_constant_of_the_equation_makes_missing_only_the_result():
    constants = dataclasses.replace(
        PLACEHOLDER_CONSTANTS,
        penman_monteith=dataclasses.replace(
            PLACEHOLDER_CONSTANTS.penman_monteith, radiation_factor=NOT_TRANSCRIBED
        ),
    )
    steps = reference_evapotranspiration_day(
        **DAY, constants=constants, bounds=PLACEHOLDER_BOUNDS
    )
    assert missing_steps(steps) == {"reference_evapotranspiration"}
    assert "penman_monteith.radiation_factor" in (
        steps.reference_evapotranspiration.detail
    )


def test_d2_with_every_constant_missing_every_step_that_has_one_is_missing():
    def all_missing(group):
        return dataclasses.replace(
            group, **{f.name: NOT_TRANSCRIBED for f in dataclasses.fields(group)}
        )

    constants = type(PLACEHOLDER_CONSTANTS)(
        **{
            f.name: all_missing(getattr(PLACEHOLDER_CONSTANTS, f.name))
            for f in dataclasses.fields(PLACEHOLDER_CONSTANTS)
        }
    )
    steps = reference_evapotranspiration_day(
        **DAY, constants=constants, bounds=PLACEHOLDER_BOUNDS
    )
    # Present: the actual vapour pressure, given as an input here, the mean
    # temperature, the one step with no constant, the wind speed, whose bound
    # is not one of these constants, and the two notes on the bounds.
    assert missing_steps(steps) == ALL_STEPS - BOUND_NOTES - {
        "actual_vapour_pressure",
        "mean_temperature",
        "wind_speed_2m",
    }


def test_d2_a_non_finite_input_is_not_computed():
    steps = day(actual_vapour_pressure=math.nan)
    assert steps.actual_vapour_pressure.reason == "NOT_COMPUTABLE"
    assert steps.reference_evapotranspiration.reason == "MISSING_INPUT"


def test_d2_constants_of_the_wrong_type_raise():
    with pytest.raises(TypeError):
        reference_evapotranspiration_day(
            **DAY, constants=None, bounds=PLACEHOLDER_BOUNDS
        )


# --- Q1: the unit strings are those of contracts/CLIMATE_QUANTITIES.md ---


def _summary_table() -> dict[str, str]:
    """Identifier -> first unit string of each row of the summary table."""
    rows = {}
    for line in CLIMATE_QUANTITIES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `CQ"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        identifier = cells[1].strip("`")
        unit = cells[3].split("`")[1]
        rows[identifier] = unit
    return rows


def test_q1_identifiers_and_unit_strings_match_the_climate_quantities_file():
    table = _summary_table()
    for quantity, unit in ACCEPTED_UNITS.items():
        assert quantity in table, quantity
        assert table[quantity] == unit, quantity


def test_q1_the_five_quantities_are_the_ones_d25_to_d27_and_d35_name():
    assert set(CLIMATE_QUANTITIES) == {
        "air_temperature_max_2m",
        "air_temperature_min_2m",
        "dew_point_temperature_2m",
        "wind_speed_2m",
        "solar_radiation",
    }


# --- Q2: an input is read through the unit guard ---


def test_q2_a_value_in_the_accepted_unit_is_read():
    assert (
        read_input("x", InputValue(3.0, "PLACEHOLDER u"), "PLACEHOLDER u", GUARD) == 3.0
    )


def test_q2_a_missing_value_is_missing_input_and_named():
    result = read_input(
        "x", InputValue(NOT_TRANSCRIBED, "PLACEHOLDER u"), "PLACEHOLDER u", GUARD
    )
    assert result.reason == "MISSING_INPUT"
    assert "input 'x'" in result.detail


def test_q2_another_unit_string_is_not_converted():
    result = read_input(
        "x", InputValue(3.0, "PLACEHOLDER other"), "PLACEHOLDER u", GUARD
    )
    assert isinstance(result, Missing)
    assert result.reason == GUARD
    assert "'x'" in result.detail
    assert "PLACEHOLDER other" in result.detail
    assert "PLACEHOLDER u" in result.detail


def test_q2_a_unit_string_is_compared_exactly():
    result = read_input("x", InputValue(3.0, "degc"), "degC", GUARD)
    assert result.reason == GUARD


def test_q2_a_missing_value_is_reported_before_its_unit():
    result = read_input(
        "x", InputValue(NOT_TRANSCRIBED, "PLACEHOLDER other"), "PLACEHOLDER u", GUARD
    )
    assert result.reason == "MISSING_INPUT"


def test_q2_a_non_finite_value_is_not_computed():
    result = read_input(
        "x", InputValue(math.inf, "PLACEHOLDER u"), "PLACEHOLDER u", GUARD
    )
    assert result.reason == "NOT_COMPUTABLE"


@pytest.mark.parametrize(
    ("item", "accepted", "reason", "error"),
    [
        (3.0, "PLACEHOLDER u", GUARD, TypeError),
        (InputValue("3", "PLACEHOLDER u"), "PLACEHOLDER u", GUARD, TypeError),
        (InputValue(3.0, None), "PLACEHOLDER u", GUARD, TypeError),
        (InputValue(3.0, "PLACEHOLDER u"), None, GUARD, TypeError),
        (InputValue(3.0, "PLACEHOLDER u"), "PLACEHOLDER u", "NOT_A_CODE", ValueError),
        (InputValue("3", "PLACEHOLDER other"), "PLACEHOLDER u", GUARD, TypeError),
    ],
)
def test_q2_a_defect_of_the_caller_raises(item, accepted, reason, error):
    with pytest.raises(error):
        read_input("x", item, accepted, reason)


# --- C1: every day of the climate record ---


def test_c1_every_day_is_the_composition_of_its_own_inputs():
    record = climate(*all_series())
    result = run(record)
    assert [item.date for item in result] == DATES
    for item in result:
        assert isinstance(item, DailyReferenceEvapotranspiration)
        ea = eq.actual_vapour_pressure_from_dew_point(
            VALUES[DEW_POINT], PLACEHOLDER_CONSTANTS.saturation_vapour_pressure
        )
        assert item.steps == reference_evapotranspiration_day(
            day_of_year=eq.day_of_year(item.date),
            latitude_radians=eq.latitude_in_radians(LATITUDE),
            elevation=ELEVATION,
            temperature_max=VALUES[TEMPERATURE_MAX],
            temperature_min=VALUES[TEMPERATURE_MIN],
            actual_vapour_pressure=ea,
            wind_speed_2m=VALUES[WIND_SPEED_2M],
            solar_radiation=VALUES[SOLAR_RADIATION],
            constants=PLACEHOLDER_CONSTANTS,
            bounds=PLACEHOLDER_BOUNDS,
        )
        assert item.value is item.steps.reference_evapotranspiration
        assert isinstance(item.value, float)


def test_c1_other_quantities_of_the_record_are_ignored():
    other = series(TEMPERATURE_MAX) | {"quantity": "precipitation", "unit": "mm day-1"}
    assert run(climate(*all_series(), other)) == run(climate(*all_series()))


# --- C2: a quantity with no series ---


@pytest.mark.parametrize("quantity", CLIMATE_QUANTITIES)
def test_c2_a_quantity_without_a_series_is_missing_input_on_every_day(quantity):
    record = climate(*[s for s in all_series() if s["quantity"] != quantity])
    result = run(record)
    assert [item.date for item in result] == DATES
    for item in result:
        assert item.value.reason == "MISSING_INPUT"
        assert quantity in item.value.detail


# --- C3: a series in another unit string ---


@pytest.mark.parametrize("quantity", CLIMATE_QUANTITIES)
def test_c3_a_series_in_another_unit_is_not_converted(quantity):
    wrong = series(quantity, unit="PLACEHOLDER another unit")
    record = climate(*all_series(**{quantity: wrong}))
    for item in run(record):
        assert item.value.reason == "MISSING_INPUT"
        assert quantity in item.value.detail
        assert GUARD in item.value.detail
        assert "PLACEHOLDER another unit" in item.value.detail


# --- C4: a day held as missing in a series ---


def test_c4_a_missing_day_makes_only_that_day_missing_with_its_reason():
    gap = series(SOLAR_RADIATION, missing_on={DATES[1]})
    result = run(climate(*all_series(**{SOLAR_RADIATION: gap})))
    assert isinstance(result[0].value, float)
    assert isinstance(result[2].value, float)
    assert result[1].value.reason == "MISSING_INPUT"
    assert SOLAR_RADIATION in result[1].value.detail
    assert "NO_COVERAGE" in result[1].value.detail
    assert "net_shortwave_radiation" in missing_steps(result[1].steps)
    assert "extraterrestrial_radiation" not in missing_steps(result[1].steps)


# --- C5: series in different time zones ---


def test_c5_series_in_different_time_zones_are_not_combined():
    other = series(WIND_SPEED_2M, time_zone="PLACEHOLDER zone")
    result = run(climate(*all_series(**{WIND_SPEED_2M: other})))
    assert len(result) == len(DATES)
    for item in result:
        assert item.value.reason == "NOT_COMPUTABLE"
        assert "time zone" in item.value.detail
        assert item.steps.mean_temperature.reason == "MISSING_INPUT"
        assert isinstance(item.steps.atmospheric_pressure, float)


# --- C6: the point of the series ---


def test_c6_latitude_and_elevation_are_read_from_the_point_of_the_record():
    moved = point(
        latitude=point_value(45.0, "PLACEHOLDER degrees"),
        elevation=point_value(1.0, "PLACEHOLDER length"),
    )
    item = run(climate(*all_series(), at=moved))[0]
    c = PLACEHOLDER_CONSTANTS
    assert item.steps.atmospheric_pressure == eq.atmospheric_pressure(
        1.0, c.atmospheric_pressure
    )
    decl = eq.solar_declination(eq.day_of_year(item.date), c.solar_declination)
    assert item.steps.sunset_hour_angle == eq.sunset_hour_angle(
        eq.latitude_in_radians(45.0), decl
    )


def test_c6_the_longitude_of_the_point_is_not_read():
    no_longitude = point()
    no_longitude["longitude"] = point_value(
        {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"}, "PLACEHOLDER degrees"
    )
    assert run(climate(*all_series(), at=no_longitude)) == run(climate(*all_series()))


def test_c6_a_missing_latitude_makes_every_day_missing_with_its_reason():
    missing = point_value(
        {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER no point"},
        "PLACEHOLDER degrees",
    )
    for item in run(climate(*all_series(), at=point(latitude=missing))):
        assert item.value.reason == "MISSING_INPUT"
        assert "input 'latitude'" in item.value.detail
        assert "NO_COVERAGE" in item.value.detail
        assert isinstance(item.steps.atmospheric_pressure, float)


def test_c6_a_missing_elevation_makes_the_steps_that_need_it_missing():
    missing = point_value(
        {"reason": "SOURCE_UNAVAILABLE", "detail": "PLACEHOLDER"}, "PLACEHOLDER length"
    )
    for item in run(climate(*all_series(), at=point(elevation=missing))):
        assert item.steps.atmospheric_pressure.reason == "MISSING_INPUT"
        assert "input 'elevation'" in item.steps.atmospheric_pressure.detail
        assert "SOURCE_UNAVAILABLE" in item.steps.atmospheric_pressure.detail
        assert isinstance(item.steps.extraterrestrial_radiation, float)
        assert item.value.reason == "MISSING_INPUT"


def test_c6_a_latitude_in_another_unit_is_not_converted():
    other = point_value(0.0, "PLACEHOLDER radians")
    for item in run(climate(*all_series(), at=point(latitude=other))):
        assert item.value.reason == "MISSING_INPUT"
        assert GUARD in item.value.detail
        assert "PLACEHOLDER radians" in item.value.detail


def test_c6_an_elevation_in_another_unit_is_not_converted():
    other = point_value(2.0, "PLACEHOLDER other length")
    for item in run(climate(*all_series(), at=point(elevation=other))):
        assert item.steps.atmospheric_pressure.reason == "MISSING_INPUT"
        assert GUARD in item.steps.atmospheric_pressure.detail
        assert item.value.reason == "MISSING_INPUT"


# --- C7: days that one series does not cover ---


def test_c7_a_day_one_series_does_not_cover_is_missing_and_named():
    short = series(WIND_SPEED_2M, dates=DATES[:2])
    result = run(climate(*all_series(**{WIND_SPEED_2M: short})))
    assert [item.date for item in result] == DATES
    assert isinstance(result[1].value, float)
    assert result[2].value.reason == "MISSING_INPUT"
    assert "'wind_speed_2m' does not cover this day" in result[2].value.detail


def test_c7_the_days_are_every_day_any_of_the_series_covers_in_order():
    later = [DATES[-1] + dt.timedelta(days=n) for n in (1, 2)]
    extra = series(TEMPERATURE_MAX, dates=later)
    result = run(climate(*all_series(**{TEMPERATURE_MAX: extra})))
    assert [item.date for item in result] == DATES + later


# --- C8: no series of the five ---


def test_c8_without_any_of_the_five_series_there_is_no_day():
    other = series(TEMPERATURE_MAX) | {"quantity": "precipitation", "unit": "mm day-1"}
    assert run(climate(other)) == []
    assert run(climate()) == []


# --- C9: pure ---


def test_c9_the_arguments_are_not_changed_and_the_result_repeats():
    record = climate(
        *all_series(**{DEW_POINT: series(DEW_POINT, missing_on={DATES[0]})})
    )
    before = record.model_dump(mode="json")
    constants_before = dataclasses.replace(PLACEHOLDER_CONSTANTS)
    first = run(record)
    assert run(record) == first
    assert record.model_dump(mode="json") == before
    assert PLACEHOLDER_CONSTANTS == constants_before


# --- C10: defects of the caller ---


@pytest.mark.parametrize(
    "changes",
    [
        {"point_units": None},
        {"constants": None},
        {"bounds": None},
        {"bounds": PLACEHOLDER_CONSTANTS},
    ],
    ids=["point-units", "constants", "bounds-none", "bounds-of-another-class"],
)
def test_c10_an_argument_of_the_wrong_type_raises(changes):
    with pytest.raises(TypeError):
        run(climate(*all_series()), **changes)


def test_c10_a_climate_record_that_is_not_a_site_climate_raises():
    record = climate(*all_series()).model_dump(mode="json")
    with pytest.raises(TypeError):
        run(record)


def test_c10_a_unit_guard_reason_outside_c3_2_raises():
    with pytest.raises(ValueError):
        run(climate(*all_series()), unit_guard_reason="NOT_A_CODE")


# --- BD2 to BD6: the bounds of D82 (PC-4) in the composition, PLACEHOLDER values ---

# PLACEHOLDER bounds that both change the PLACEHOLDER day: the ratio of the
# day is above an upper bound this small, and the wind of the day is below a
# lower bound this large.
TIGHT_BOUNDS = dataclasses.replace(
    PLACEHOLDER_BOUNDS,
    relative_shortwave_bound=dataclasses.replace(
        PLACEHOLDER_BOUNDS.relative_shortwave_bound, upper_bound=0.001
    ),
    wind_speed_bound=dataclasses.replace(
        PLACEHOLDER_BOUNDS.wind_speed_bound, lower_bound=9.0
    ),
)


def test_bd2_a_bound_that_changes_its_quantity_says_so():
    steps = day(bounds=TIGHT_BOUNDS)
    assert steps.shortwave_ratio > 0.001
    assert steps.relative_shortwave_radiation == 0.001
    assert steps.wind_speed_2m == 9.0
    assert steps.bounds_changed == (RELATIVE_SHORTWAVE_BOUND, WIND_SPEED_BOUND)
    assert steps.bounds_not_applied == ()
    c = PLACEHOLDER_CONSTANTS
    assert steps.net_longwave_radiation == eq.net_longwave_radiation(
        DAY["temperature_max"],
        DAY["temperature_min"],
        DAY["actual_vapour_pressure"],
        0.001,
        c.net_longwave,
    )
    assert steps.reference_evapotranspiration == eq.reference_evapotranspiration(
        slope=steps.slope,
        net_radiation=steps.net_radiation,
        soil_heat_flux=steps.soil_heat_flux,
        psychrometric_constant=steps.psychrometric_constant,
        mean_temperature=steps.mean_temperature,
        wind_speed_2m=9.0,
        mean_saturation_vapour_pressure=steps.mean_saturation_vapour_pressure,
        actual_vapour_pressure=steps.actual_vapour_pressure,
        constants=c.penman_monteith,
    )
    assert steps.reference_evapotranspiration != day().reference_evapotranspiration


def test_bd2_only_the_bound_that_changes_its_quantity_is_named():
    steps = day(wind_speed_2m=0.5)  # below the PLACEHOLDER lower bound 2
    assert steps.bounds_changed == (WIND_SPEED_BOUND,)
    assert steps.wind_speed_2m == 2.0


def test_bd3_a_bound_that_leaves_its_quantity_as_it_was_is_not_named():
    steps = day()
    assert steps.relative_shortwave_radiation == steps.shortwave_ratio
    assert steps.wind_speed_2m == DAY["wind_speed_2m"]
    assert steps.bounds_changed == ()
    assert steps.bounds_not_applied == ()


def test_bd4_without_bounds_nothing_is_bounded_and_the_day_says_so():
    steps = day(bounds=None, wind_speed_2m=0.5)
    assert steps.bounds_not_applied == BOUNDS
    assert steps.bounds_changed == ()
    assert steps.relative_shortwave_radiation == steps.shortwave_ratio
    assert steps.wind_speed_2m == 0.5
    assert isinstance(steps.reference_evapotranspiration, float)


@pytest.mark.parametrize(
    ("group", "field", "identifier", "dependent"),
    [
        (
            "relative_shortwave_bound",
            "upper_bound",
            RELATIVE_SHORTWAVE_BOUND,
            {
                "relative_shortwave_radiation",
                "net_longwave_radiation",
                "net_radiation",
                "reference_evapotranspiration",
            },
        ),
        (
            "wind_speed_bound",
            "lower_bound",
            WIND_SPEED_BOUND,
            {"wind_speed_2m", "reference_evapotranspiration"},
        ),
    ],
)
def test_bd5_a_missing_bound_makes_its_quantity_missing_and_names_it(
    group, field, identifier, dependent
):
    bounds = dataclasses.replace(
        PLACEHOLDER_BOUNDS,
        **{
            group: dataclasses.replace(
                getattr(PLACEHOLDER_BOUNDS, group), **{field: NOT_TRANSCRIBED}
            )
        },
    )
    steps = day(bounds=bounds)
    assert missing_steps(steps) == dependent
    assert steps.reference_evapotranspiration.reason == "MISSING_INPUT"
    assert f"constant '{identifier}'" in steps.reference_evapotranspiration.detail
    assert steps.bounds_changed == ()
    assert steps.bounds_not_applied == ()


def test_bd5_a_missing_quantity_is_not_named_as_changed_by_its_bound():
    steps = day(bounds=TIGHT_BOUNDS, wind_speed_2m=NOT_TRANSCRIBED)
    assert steps.wind_speed_2m.reason == "MISSING_INPUT"
    assert steps.bounds_changed == (RELATIVE_SHORTWAVE_BOUND,)


def test_bd6_every_day_of_the_record_applies_the_bounds_it_is_given():
    result = run(climate(*all_series()), bounds=TIGHT_BOUNDS)
    assert len(result) == len(DATES)
    for item in result:
        steps = item.steps
        # The wind of every PLACEHOLDER day is below the lower bound 9.
        assert steps.wind_speed_2m == 9.0
        assert WIND_SPEED_BOUND in steps.bounds_changed
        # The ratio of each day depends on its date: bounded at 0.001, and the
        # bound named exactly when it changed the ratio of that day.
        assert steps.relative_shortwave_radiation == min(steps.shortwave_ratio, 0.001)
        assert (RELATIVE_SHORTWAVE_BOUND in steps.bounds_changed) == (
            steps.shortwave_ratio > 0.001
        )
        assert steps.bounds_not_applied == ()


def test_bd6_the_record_without_bounds_says_on_every_day_that_none_was_applied():
    bounded = run(climate(*all_series()))
    unbounded = run_without_bounds(climate(*all_series()))
    assert [item.date for item in unbounded] == DATES
    for with_bounds, without in zip(bounded, unbounded, strict=True):
        assert without.steps.bounds_not_applied == BOUNDS
        assert without.steps.bounds_changed == ()
        # The PLACEHOLDER record is inside both bounds: the same numbers.
        assert without.value == with_bounds.value


def test_bd6_bounds_of_the_wrong_type_raise():
    with pytest.raises(TypeError):
        day(bounds=PLACEHOLDER_CONSTANTS)
