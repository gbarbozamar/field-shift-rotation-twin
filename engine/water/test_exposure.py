"""Acceptance test of units l1/water-ep3-parameters (issue #153),
l1/water-ep3-identifiers (issue #191), l1/water-crop-stages (issue #206;
the stages themselves are checked in ``test_stages.py``) and
l1/water-fallow-residue (issue #217; ``fallow.py`` alone is checked in
``test_fallow.py``), l1/water-ep3-repeat-d47 (issue #253: the rotation
repeated over the record, D47, D109, D132, D141) and l1/water-indicator-d157
(issue #264: the ratio of D157 for a year computed on every day).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``EXPOSURE.md`` under "PROPOSED cases"; a test checks that the two lists
agree. The identifier of a case is the name of its test function without
``test_``, with hyphens.

Inputs are built from the PLACEHOLDER examples of ``contracts/inputs/examples/``,
loaded and changed in memory. Every number written here is a PLACEHOLDER,
plainly not real: none is a value of the method, none comes from a source.

The parameter catalogue of a test is built in the record format of
``params/README.md``, every record carrying the word PLACEHOLDER. The readers
of ``params.catalogue`` refuse such a record, and ``check_catalogue`` rejects
it, so a test passes the in-memory copy in which the word is replaced by
``UNMARKED_TEST_ONLY``, as ``params/test_layout.py`` does (question 12 of
``params/README.md``). The crop identifiers of the test calendar are unmarked
the same way, so that a crop scope of the catalogue names them. Nothing
without the word is written to a file.

Run from the repository root: ``py -3.12 -m pytest engine/water/test_exposure.py``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_WATER_DEFICIT_EXPOSURE,
    Missing,
    ReasonCode,
    ResultsPerRotation,
    WaterDeficitExposure,
)
from engine.calendar.repeat import (
    components_crossing_phase,
    list_phases,
    phase_calendar,
)
from engine.water import _parameters
from engine.water import exposure as module
from engine.water.et0.quantities import CLIMATE_QUANTITIES
from engine.water.stages import GROWTH_STAGES, STAGE_LENGTH_PARAMETERS
from params.catalogue import check_catalogue, check_record

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
INDICATOR = "water_deficit_exposure"
PRECIPITATION = "precipitation"  # decision D23 of issue #77
DAILY_INPUTS = (PRECIPITATION, *CLIMATE_QUANTITIES)
REASON_CODES = set(get_args(ReasonCode))
ONE_DAY = dt.timedelta(days=1)
MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
NO_CROP_SCOPE = '{"management": "no_crop"}'

# --- PLACEHOLDER numbers: plainly not real, chosen only so that every part
# accepts them and the chain gives a number every day. They are written with
# repeated digits, or as zero or one where the structure of a form needs the
# identity element; each zero and one is explained where it is written. None
# is a value of the method and none comes from a source. ---------------------

# The daily values of each series, repeated in turn. A precipitation of zero is
# a dry day, needed so that the layers dry out between wet days.
PLACEHOLDER_DAILY = {
    PRECIPITATION: [0.0, 0.0, 6.66, 0.0, 1.11, 0.0, 0.0, 14.44, 0.0, 0.0, 0.0, 0.0],
    "air_temperature_max_2m": [3.33, 4.44, 5.55],
    "air_temperature_min_2m": [1.11, 2.22],
    "dew_point_temperature_2m": [0.55],
    "wind_speed_2m": [1.11, 2.22],
    "solar_radiation": [2.22, 3.33, 4.44],
}
# Every constant of the method not listed here is one: the identity element of
# the factor, exponent or divisor it is in the PROPOSED forms of the parts.
PLACEHOLDER_SITE = {
    # Zero, structurally: with no albedo and no longwave term the net radiation
    # is the solar radiation, so it stays above the soil heat flux and the
    # reference evapotranspiration stays above zero, which the balance needs.
    "net_shortwave_albedo": 0.0,
    "net_longwave_stefan_boltzmann": 0.0,
    # Zero, structurally: the inverse distance and the declination stay
    # constant, so the sunset hour angle exists on every day of the year.
    "inverse_relative_distance_amplitude": 0.0,
    "solar_declination_amplitude": 0.0,
    # Zero, structurally: the pressure does not depend on the elevation, so
    # the bracket of its form stays above zero at any elevation.
    "atmospheric_pressure_lapse_rate": 0.0,
    # The two bounds of D82 (PC-4), plainly not their values. With no
    # longwave term (the Stefan-Boltzmann constant above is zero) the bound of
    # Rs/Rso changes nothing; the bound of the wind speed lies below every
    # placeholder wind speed, so it changes nothing either.
    "net_longwave_relative_shortwave_maximum": 7.77,
    "penman_monteith_minimum_wind_speed": 0.111,
    "soil_heat_flux_daily_value": 1.11,
    "initial_abstraction_ratio": 0.555,
    "retention_numerator": 2.22,
    "retention_unit_factor": 4.44,
    "initial_depletion": 1.11,
    # The total evaporable water is computed from these (with a unit factor,
    # a wilting-point weight and a layer depth of one): 5.55 - 1.11.
    "field_capacity_water_content": 5.55,
    "wilting_point_water_content": 1.11,
    "readily_evaporable_water": 2.22,
    "wetted_fraction": 0.777,
    "margin_above_basal": 0.555,
    "minimum_crop_coefficient": 0.222,
    "minimum_relative_humidity": 3.33,
    "column_capacity": 22.2,
    "column_depth": 2.22,
    "initial_storage": 11.1,
    # The two constants of the reduction of the total evaporable water on a
    # fallow day (D110), plainly not the "5 % for each 10 %" of the method.
    "mulch_total_evaporable_water_reduction": 0.0333,
    "mulch_cover_increment": 0.111,
}
PLACEHOLDER_DAY = {
    # On a day with a crop the basal crop coefficient is read by crop and
    # stage (PLACEHOLDER_STAGE); here, the one of a day with no crop.
    "basal_crop_coefficient": {"no_crop": 0.333},
    "crop_height": {"crop-a": 1.11, "crop-b": 2.22, "no_crop": 0.111},
    "curve_number": {"crop-a": 1.11, "crop-b": 0.555, "no_crop": 1.11},
}
# Read by crop only: on a day with no crop the cover fraction is a record
# (PLACEHOLDER_FALLOW), not computed from the basal coefficient (D110).
PLACEHOLDER_EXPONENT = {"crop-a": 1.11, "crop-b": 2.22}
# The cover fraction and the wetted fraction of the surface layer on a day
# with no crop, plainly not the fc = 0 and fw = 1 of D110.
PLACEHOLDER_FALLOW = {"cover_fraction": 0.111, "wetted_fraction": 0.888}
# The surface residue cover of a fallow, by the crop sown after it (D110,
# D115): a fraction of the soil surface.
PLACEHOLDER_RESIDUE_COVER = {"crop-a": 0.444, "crop-b": 0.222}
# The root depths lie above zero and not deeper than the column (column_depth).
PLACEHOLDER_CROP = {
    "cover_fraction_exponent": PLACEHOLDER_EXPONENT,
    "maximum_root_depth": {"crop-a": 1.11, "crop-b": 2.22},
    "initial_root_depth": {"crop-a": 0.111, "crop-b": 0.222},
    "readily_available_fraction": {"crop-a": 0.444, "crop-b": 0.888},
}
# The value of every record read by crop and growth stage.
PLACEHOLDER_STAGE = {"initial": 0.444, "mid": 0.555, "end": 0.666}
CROPS = ("crop-a", "crop-b")
# The length in days of the first three growth stages of each crop. The late
# stage takes the days left of the first period of the crop in the example
# calendar (placeholder_stage_lengths), so that the four fill it; the test
# calendar gives every period of a crop that many days (chain_calendar).
PLACEHOLDER_STAGE_LENGTHS = {
    "crop-a": {"initial": 11.0, "development": 22.0, "mid": 111.0},
    "crop-b": {"initial": 11.0, "development": 33.0, "mid": 111.0},
}

# The water records drafted for the lead developer's check
# (params_borrador/agua/, outside the repository, issue #191): exactly their
# id, scope and unit, and none of their values. Three of their unit strings
# carry the value of the record in a note; that note is left out here, so
# that no value of a draft is written in this file.
DRAFTED_RECORDS: tuple[tuple[str, dict[str, str], str], ...] = (
    ("atmospheric_pressure_exponent", {}, "dimensionless (not printed)"),
    ("atmospheric_pressure_lapse_rate", {}, "K m-1 (not printed; z in [m])"),
    (
        "atmospheric_pressure_reference_temperature",
        {},
        "K (the draft's note on this unit carries the value and is left out)",
    ),
    (
        "atmospheric_pressure_sea_level_pressure",
        {},
        "kPa (not printed with the value; symbol list: P [kPa])",
    ),
    ("basal_crop_coefficient", {"crop": "alfalfa", "stage": "end"}, "dimensionless"),
    (
        "basal_crop_coefficient",
        {"crop": "alfalfa", "stage": "initial"},
        "dimensionless",
    ),
    ("basal_crop_coefficient", {"crop": "alfalfa", "stage": "mid"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "maize", "stage": "end"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "maize", "stage": "initial"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "maize", "stage": "mid"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "soybean", "stage": "end"}, "dimensionless"),
    (
        "basal_crop_coefficient",
        {"crop": "soybean", "stage": "initial"},
        "dimensionless",
    ),
    ("basal_crop_coefficient", {"crop": "soybean", "stage": "mid"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "wheat", "stage": "end"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "wheat", "stage": "initial"}, "dimensionless"),
    ("basal_crop_coefficient", {"crop": "wheat", "stage": "mid"}, "dimensionless"),
    ("clear_sky_radiation_base", {}, "dimensionless (not printed)"),
    ("clear_sky_radiation_elevation_coefficient", {}, "m-1 (not printed; z in [m])"),
    ("evaporation_layer_depth", {}, "m"),
    ("extraterrestrial_radiation_solar_constant", {}, "MJ m-2 min-1"),
    (
        "extraterrestrial_radiation_time_factor",
        {},
        "min day-1 (the draft's note on this unit carries the value and is left out)",
    ),
    ("initial_abstraction_ratio", {}, "dimensionless"),
    ("inverse_relative_distance_amplitude", {}, "dimensionless (not printed)"),
    ("inverse_relative_distance_days_in_year", {}, "day (not printed)"),
    ("inverse_relative_distance_offset", {}, "dimensionless (not printed)"),
    ("margin_above_basal", {}, "dimensionless"),
    ("maximum_root_depth", {"crop": "alfalfa"}, "m"),
    ("maximum_root_depth", {"crop": "maize"}, "m"),
    ("maximum_root_depth", {"crop": "soybean"}, "m"),
    ("maximum_root_depth", {"crop": "wheat"}, "m"),
    ("minimum_crop_coefficient", {}, "dimensionless"),
    ("net_longwave_cloudiness_multiplier", {}, "dimensionless (not printed)"),
    ("net_longwave_cloudiness_offset", {}, "dimensionless (not printed)"),
    ("net_longwave_humidity_intercept", {}, "dimensionless (not printed)"),
    ("net_longwave_humidity_slope", {}, "kPa-0.5 (not printed; ea in [kPa])"),
    (
        "net_longwave_kelvin_offset",
        {},
        "K (the draft's note on this unit carries the value and is left out)",
    ),
    ("net_longwave_relative_shortwave_maximum", {}, "dimensionless (not printed)"),
    ("net_longwave_stefan_boltzmann", {}, "MJ K-4 m-2 day-1"),
    ("net_shortwave_albedo", {}, "dimensionless"),
    ("penman_monteith_denominator_constant", {}, "s m-1 (not printed; u2 in [m s-1])"),
    ("penman_monteith_kelvin_offset", {}, "K (not printed; T in [°C])"),
    ("penman_monteith_minimum_wind_speed", {}, "m s-1"),
    ("penman_monteith_numerator_constant", {}, "not printed"),
    (
        "penman_monteith_radiation_factor",
        {},
        "mm day-1 per MJ m-2 day-1 (not printed in Eq. 6; Eq. 20 converts [MJ m-2 day-1] to [mm day-1])",
    ),
    (
        "psychrometric_coefficient",
        {},
        "kPa-1 x kPa °C-1, as printed: gamma [kPa °C-1] = coefficient x P [kPa]",
    ),
    ("readily_available_fraction", {"crop": "alfalfa"}, "dimensionless"),
    ("readily_available_fraction", {"crop": "maize"}, "dimensionless"),
    ("readily_available_fraction", {"crop": "soybean"}, "dimensionless"),
    ("readily_available_fraction", {"crop": "wheat"}, "dimensionless"),
    ("readily_evaporable_water", {}, "mm"),
    ("retention_numerator", {}, "dimensionless (CN dimensionless)"),
    ("retention_offset", {}, "in (S in inches, Eq. 10-12)"),
    ("retention_unit_factor", {}, "mm in-1"),
    ("saturation_vapour_pressure_numerator", {}, "dimensionless (not printed)"),
    ("saturation_vapour_pressure_offset", {}, "°C (not printed; T in [°C])"),
    (
        "saturation_vapour_pressure_scale",
        {},
        "kPa (not printed with the value; e°(T) in [kPa])",
    ),
    ("slope_multiplier", {}, "°C (not printed; Delta in [kPa °C-1])"),
    ("soil_heat_flux_daily_value", {}, "MJ m-2 day-1"),
    (
        "solar_declination_amplitude",
        {},
        "rad (not printed with the value; delta in [rad])",
    ),
    ("solar_declination_days_in_year", {}, "day (not printed)"),
    ("solar_declination_phase", {}, "rad (not printed)"),
    (
        "total_evaporable_water_unit_factor",
        {},
        "mm m-1 (theta in m3 m-3, Ze in m, TEW in mm)",
    ),
    ("total_evaporable_water_wilting_point_weight", {}, "dimensionless"),
    ("upper_limit_base", {}, "dimensionless"),
    ("upper_limit_height_exponent", {}, "dimensionless"),
    ("upper_limit_humidity_coefficient", {}, "percent-1 (RHmin in %)"),
    ("upper_limit_reference_crop_height", {}, "m (h in [m])"),
    ("upper_limit_reference_minimum_relative_humidity", {}, "percent"),
    ("upper_limit_reference_wind_speed", {}, "m s-1"),
    ("upper_limit_wind_coefficient", {}, "s m-1 (u2 in m s-1)"),
    ("wetted_fraction", {}, "dimensionless"),
)


# --- the catalogue -------------------------------------------------------------


def placeholder_record(parameter_id: str, value: float, scope: dict) -> dict:
    """One record in the format of params/README.md, marked PLACEHOLDER."""
    return {
        "id": parameter_id,
        "scope": scope,
        "value": value,
        "unit": "PLACEHOLDER_unit",
        "range": {
            "low": value,
            "high": value,
            "basis": "PLACEHOLDER: not a range of any source",
        },
        "citation": {
            "reference": "PLACEHOLDER reference. This is not a publication.",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
    }


def crop_word(crop: str) -> str:
    return f"PLACEHOLDER-{crop}"


def scope_of(label: str) -> dict:
    """The scope of a label: ``no_crop``, ``fallow:<crop>`` (a day with no crop
    before that crop), a crop, or ``<crop>:<stage>``."""
    if label == "no_crop":
        return {"management": "no_crop"}
    if label.startswith("fallow:"):
        return {"crop": crop_word(label.split(":", 1)[1]), "management": "no_crop"}
    crop, _, stage = label.partition(":")
    if stage:
        return {"crop": crop_word(crop), "stage": stage}
    return {"crop": crop_word(crop)}


def label_of(scope: dict) -> str | None:
    """The label of a scope of the test catalogue; ``None`` for the empty scope."""
    if not scope:
        return None
    if "management" in scope and "crop" in scope:
        return f"fallow:{scope['crop'].split('-', 1)[1]}"
    if "management" in scope:
        return "no_crop"
    crop = scope["crop"].split("-", 1)[1]
    return f"{crop}:{scope['stage']}" if "stage" in scope else crop


def period_days(crop: str) -> int:
    """The days of the first period of the crop in the example calendar."""
    for component in calendar_document()["components"]:
        if component["crop_id"] == crop_word(crop):
            start, end = (
                dt.date.fromisoformat(component[edge]["date"])
                for edge in ("start", "end")
            )
            return (end - start).days + 1
    raise AssertionError(f"no period of {crop} in the example calendar")


def placeholder_stage_lengths(crop: str) -> dict[str, float]:
    """The four stage lengths of a crop: PLACEHOLDER_STAGE_LENGTHS and the late
    stage, the days left of the period (period_days)."""
    lengths = dict(PLACEHOLDER_STAGE_LENGTHS[crop])
    lengths["late"] = float(period_days(crop) - sum(lengths.values()))
    assert lengths["late"] >= 1
    return {stage: lengths[stage] for stage in GROWTH_STAGES}


def marked_catalogue() -> dict[str, dict]:
    """Every parameter the chain reads, keyed as load_folder keys a record."""
    records = []
    for parameter_id in (*module.SITE_PARAMETERS, *module.FALLOW_SITE_PARAMETERS):
        value = PLACEHOLDER_SITE.get(parameter_id, 1.0)
        records.append(placeholder_record(parameter_id, value, {}))
    for parameter_id, value in PLACEHOLDER_FALLOW.items():
        records.append(placeholder_record(parameter_id, value, scope_of("no_crop")))
    for crop, value in PLACEHOLDER_RESIDUE_COVER.items():
        records.append(
            placeholder_record(
                module.SURFACE_RESIDUE_COVER, value, scope_of(f"fallow:{crop}")
            )
        )
    for parameter_id, by_crop in (*PLACEHOLDER_DAY.items(), *PLACEHOLDER_CROP.items()):
        for crop, value in by_crop.items():
            records.append(placeholder_record(parameter_id, value, scope_of(crop)))
    for parameter_id in module.STAGE_PARAMETERS:
        for crop in CROPS:
            for stage in module.STAGES:
                records.append(
                    placeholder_record(
                        parameter_id,
                        PLACEHOLDER_STAGE[stage],
                        scope_of(f"{crop}:{stage}"),
                    )
                )
    for crop in CROPS:
        for stage, length in placeholder_stage_lengths(crop).items():
            records.append(
                placeholder_record(
                    STAGE_LENGTH_PARAMETERS[stage], length, scope_of(crop)
                )
            )
    return {
        f"PLACEHOLDER_{position}.json": record
        for position, record in enumerate(records)
    }


def unmarked(item: Any) -> Any:
    """The in-memory copy in which the word PLACEHOLDER is replaced."""
    return json.loads(json.dumps(item).replace(MARK, UNMARKED))


def catalogue() -> dict[str, dict]:
    return unmarked(marked_catalogue())


def catalogue_with(
    changes: dict[tuple[str, str | None], dict | None],
) -> dict[str, dict]:
    """The catalogue with some records replaced (or removed, ``None``).

    A key is ``(id, label)``; the label is ``None`` for a parameter of the
    site, ``no_crop``, a crop, or ``<crop>:<stage>`` (``scope_of``).
    """
    records = marked_catalogue()
    for name, record in list(records.items()):
        key = (record["id"], label_of(record["scope"]))
        if key in changes:
            if changes[key] is None:
                del records[name]
            else:
                records[name] = changes[key]
    return unmarked(records)


# --- inputs built from the examples ------------------------------------------


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"PLACEHOLDER_{name}.json").read_text("utf-8"))


def calendar_document() -> dict[str, Any]:
    return load("rotation_calendar")


def climate_document() -> dict[str, Any]:
    return load("site_climate")


def soil_document() -> dict[str, Any]:
    return load("site_soil_slope")


def start_month() -> int:
    return calendar_document()["ag_year_start"]["month"]


def example_precipitation() -> dict[str, Any]:
    (series,) = [
        item
        for item in climate_document()["daily_series"]
        if item["quantity"] == PRECIPITATION
    ]
    return series


def first_day_of(ag_year: int) -> dt.date:
    return dt.date(ag_year, start_month(), 1)


def last_day_of(ag_year: int) -> dt.date:
    return first_day_of(ag_year + 1) - ONE_DAY


def several_full_years() -> tuple[dt.date, dt.date]:
    """Three agricultural years, from the one that begins in the example's first year."""
    first_ag_year = dt.date.fromisoformat(example_precipitation()["start_date"]).year
    return first_day_of(first_ag_year), last_day_of(first_ag_year + 2)


def daily_series(
    quantity: str,
    first: dt.date,
    last: dt.date,
    *,
    held_missing: tuple[dt.date, ...] = (),
) -> dict[str, Any]:
    """One series of the chain in its accepted unit, from ``first`` to ``last``."""
    series = copy.deepcopy(example_precipitation())
    values = PLACEHOLDER_DAILY[quantity]
    days = []
    day = first
    position = 0
    while day <= last:
        if day in held_missing:
            days.append(
                {
                    "date": day.isoformat(),
                    "value": None,
                    "missing": {
                        "reason": "SOURCE_UNAVAILABLE",
                        "detail": "PLACEHOLDER",
                    },
                }
            )
        else:
            days.append(
                {"date": day.isoformat(), "value": values[position % len(values)]}
            )
        day += ONE_DAY
        position += 1
    series.update(
        quantity=quantity,
        unit=module.ACCEPTED_DAILY_UNITS[quantity],
        start_date=first.isoformat(),
        end_date=last.isoformat(),
        days=days,
    )
    return series


def climate_with(
    series: list[dict[str, Any]], *, point_units: bool = True
) -> SiteClimate:
    document = climate_document()
    others = [
        item
        for item in document["daily_series"]
        if item["quantity"] not in DAILY_INPUTS
    ]
    document["daily_series"] = others + series
    if point_units:
        document["point"]["latitude"]["unit"] = (
            module.POINT_UNITS.latitude_decimal_degrees
        )
        document["point"]["elevation"]["unit"] = module.POINT_UNITS.elevation
    return SiteClimate.model_validate(document)


def climate(
    span: tuple[dt.date, dt.date] | None = None,
    *,
    quantities: tuple[str, ...] = DAILY_INPUTS,
    held_missing: tuple[dt.date, ...] = (),
) -> SiteClimate:
    """The six daily series the water chain reads, over one span."""
    first, last = span or several_full_years()
    return climate_with(
        [
            daily_series(name, first, last, held_missing=held_missing)
            for name in quantities
        ]
    )


def calendar() -> RotationCalendar:
    """The example calendar as it is."""
    return RotationCalendar.model_validate(calendar_document())


def sown_on_the_last_day(document: dict[str, Any]) -> dict[str, Any]:
    """A component of crop-a sown on the last day of the record.

    It is copied from the first component of the example calendar. It gives
    the fallow at the end of the record a crop that follows it, which names
    the record of its surface residue cover (D110, D115; OPEN 31). Since unit
    #253 the sowing has to lie inside the record: nothing is laid out past
    the record (D109), so a fallow whose next sowing lies after it has no
    following crop (OPEN 41 of EXPOSURE.md). The last day of the record is
    therefore the one day of this component in the record, the first of its
    initial stage. The end date of the calendar is moved to its last day.
    """
    _, last = several_full_years()
    added = copy.deepcopy(calendar_document()["components"][0])
    added["component_id"] = "PLACEHOLDER-component-on-the-last-day"
    sowing = last
    added["start"]["date"] = sowing.isoformat()
    end = sowing + ONE_DAY * (period_days("crop-a") - 1)
    added["end"]["date"] = end.isoformat()
    added["periods"] = []
    document["end_date"] = end.isoformat()
    return added


def chain_calendar_document(*, fill_periods: bool = True) -> dict[str, Any]:
    """The example calendar over the three years of ``several_full_years``.

    One component is added, copied from the second with its dates moved into
    the third year, and the crop identifiers are unmarked. With
    ``fill_periods``, the end of each component is moved so that every period
    of a crop holds the days of its first one (``period_days``), which the
    four PLACEHOLDER stage lengths of the crop fill; without it, the third and
    fourth periods are each one day off from the first period of their crop.
    A last component is sown on the last day of the record
    (``sown_on_the_last_day``), so that every day of the record with no crop
    has a crop that follows it.
    """
    document = calendar_document()
    first, last = several_full_years()
    document["start_date"] = first.isoformat()
    document["end_date"] = last.isoformat()
    added = copy.deepcopy(document["components"][1])
    added["component_id"] = "PLACEHOLDER-component-4"
    added["start"]["date"] = (
        first_day_of(first.year + 2) + dt.timedelta(days=62)
    ).isoformat()
    added["end"]["date"] = (last - dt.timedelta(days=91)).isoformat()
    document["components"].append(added)
    document["components"].append(sown_on_the_last_day(document))
    for component in document["components"]:
        if fill_periods:
            crop = component["crop_id"].split("-", 1)[1]
            start = dt.date.fromisoformat(component["start"]["date"])
            end = start + ONE_DAY * (period_days(crop) - 1)
            component["end"]["date"] = end.isoformat()
        component["crop_id"] = unmarked(component["crop_id"])
    return document


def chain_calendar() -> RotationCalendar:
    return RotationCalendar.model_validate(chain_calendar_document())


def bare_calendar() -> RotationCalendar:
    """The calendar of ``chain_calendar`` with only the component sown on the
    last day of the record: no day of the record before its last has a crop.

    Every day of the record but the last is a day of one fallow, before
    crop-a (D110); the last day is the sowing day of crop-a. The cases that
    check the chain itself and the parameters of the site run on this
    calendar, so that no crop parameter is needed before that day.
    """
    document = chain_calendar_document()
    *_, after = document["components"]
    document["components"] = [after]
    return RotationCalendar.model_validate(document)


def soil() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(soil_document())


def run(
    calendar_: RotationCalendar | None = None,
    climate_: SiteClimate | None = None,
    soil_: SiteSoilSlope | None = None,
    parameters: dict | None = None,
) -> list[WaterDeficitExposure]:
    return module.compute_water_deficit_exposure(
        calendar=calendar_ if calendar_ is not None else bare_calendar(),
        climate=climate_ if climate_ is not None else climate(),
        soil_slope=soil_ if soil_ is not None else soil(),
        parameters=parameters if parameters is not None else catalogue(),
    )


def chain(
    calendar_: RotationCalendar | None = None,
    climate_: SiteClimate | None = None,
    parameters: dict | None = None,
) -> list[module.ChainDay]:
    """The daily chain the entry point reduces, over the days it runs on."""
    calendar_ = calendar_ if calendar_ is not None else bare_calendar()
    climate_ = climate_ if climate_ is not None else climate()
    by_quantity = {
        series.quantity: series
        for series in climate_.daily_series
        if series.quantity in DAILY_INPUTS
    }
    return module._run_chain(
        calendar_,
        climate_,
        _parameters.Catalogue(parameters if parameters is not None else catalogue()),
        by_quantity,
        module._chain_days(by_quantity[PRECIPITATION], list(by_quantity), by_quantity),
        module._Notes(),
    )


def expected_ag_years(first: dt.date, last: dt.date) -> list[int]:
    """Every agricultural year with at least one day in the span, day by day."""
    month = start_month()
    years = set()
    day = first
    while day <= last:
        years.add(day.year if day.month >= month else day.year - 1)
        day += ONE_DAY
    return sorted(years)


def infeasible_calendar() -> RotationCalendar:
    document = chain_calendar_document()
    document["feasibility"] = {
        "feasible": False,
        "violations": [{"rule": "PLACEHOLDER-rule", "component_ids": []}],
    }
    return RotationCalendar.model_validate(document)


def calendar_without_start_month() -> RotationCalendar:
    document = chain_calendar_document()
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER"},
    }
    return RotationCalendar.model_validate(document)


def items_of(detail: str) -> list[str]:
    """The items of a detail of a year the chain did not compute, after its first sentence."""
    return detail.split("); ", 1)[1].split("; ")


def assert_loads(result: list[WaterDeficitExposure]) -> None:
    for item in result:
        assert isinstance(item, WaterDeficitExposure)
        assert item.indicator == INDICATOR
        assert item.direction == DIRECTION_OF[INDICATOR]
        assert item.unit == UNIT_WATER_DEFICIT_EXPOSURE
        document = item.model_dump(mode="json")
        assert WaterDeficitExposure.model_validate(document) == item
        assert WaterDeficitExposure.model_validate_json(json.dumps(document)) == item


# The label of decision D105, which D162 places at the start of the source.
WINDOW_LABEL = "whole cycle, not critical period"


def is_computed(item: WaterDeficitExposure) -> bool:
    """The daily balance of the year was computed on every day (D157): the
    item is a number, or ``NOT_APPLICABLE`` for a year with no living crop."""
    return item.value is not None or item.missing.reason == "NOT_APPLICABLE"


def assert_is_a_value(item: WaterDeficitExposure) -> None:
    """A number of the indicator, as D157 and D162 and the results model ask."""
    assert item.missing is None
    assert is_number(item.value)
    # The balance transpires at most what is demanded, and never below zero.
    assert 0 <= item.value <= 1
    assert item.time_basis == "ag_year" and item.ag_year is not None
    assert item.source.startswith(f"{WINDOW_LABEL} (")
    assert "D105" in item.source and "D157" in item.source
    assert f"agricultural year {item.ag_year}" in item.source
    assert item.assumption is False
    assert item.provenance == "SIMULATED"  # PROPOSED (C4.1, C4.3)
    assert item.range is None
    assert item.range_missing.reason == "NOT_AVAILABLE"  # PROPOSED
    assert "C2.3" in item.range_missing.detail


def assert_computed(item: WaterDeficitExposure) -> None:
    """The year was computed on every day: the ratio of D157, or
    ``NOT_APPLICABLE`` when no day of the year has a living crop."""
    if item.value is not None:
        assert_is_a_value(item)
        return
    assert item.missing.reason == "NOT_APPLICABLE"
    assert "computed on every day of the year" in item.missing.detail
    assert "no day of the year has a living crop" in item.missing.detail
    assert "D157" in item.missing.detail
    assert item.provenance is None and item.source is None
    assert item.range is None and item.range_missing is None


def no_record_item(detail: str, scope: str) -> str:
    """The item naming the parameters with no record in one scope, or ''."""
    prefix = f"parameter MISSING_INPUT: parameters with no record in parameters (D56), scope {scope}: "
    found = [entry for entry in detail.split("; ") if entry.startswith(prefix)]
    return found[0] if found else ""


def is_number(value: object) -> bool:
    return isinstance(value, float) and math.isfinite(value)


# --- the cases: the catalogue -------------------------------------------------


def test_placeholder_catalogue_passes_check_catalogue_and_every_year_is_computed():
    parameters = catalogue()
    assert check_catalogue(parameters) == []
    assert all(check_record(record) == [] for record in marked_catalogue().values())
    assert check_catalogue(marked_catalogue()) != []  # the marked records are refused
    result = run(parameters=parameters)
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*several_full_years())
    for item in result:
        assert_computed(item)


def test_the_chain_gives_a_number_every_day_from_each_part():
    days = chain()
    first, last = several_full_years()
    assert [day.date for day in days] == [
        first + ONE_DAY * position for position in range((last - first).days + 1)
    ]
    for day in days:
        assert is_number(day.reference_evapotranspiration)
        assert is_number(day.runoff.runoff)
        assert is_number(day.surface_layer.evaporation_coefficient)
        assert is_number(day.surface_layer.depletion_end)
        assert is_number(day.balance.storage_start)
        assert is_number(day.balance.storage_end)
    # The chain passes each part's output to the next one, unchanged.
    for day in days:
        assert day.balance.runoff == day.runoff.runoff
        assert day.surface_layer.runoff == day.runoff.runoff
        assert day.balance.evaporation_demanded == pytest.approx(
            day.surface_layer.evaporation_coefficient * day.reference_evapotranspiration
        )
    # The balance is never reset: each day starts where the day before ended.
    for before, after in zip(days, days[1:]):
        assert after.balance.storage_start == before.balance.storage_end
        assert after.surface_layer.depletion_start == before.surface_layer.depletion_end
    assert days[0].balance.storage_start == PLACEHOLDER_SITE["initial_storage"]


def test_daily_balance_closes_its_mass_every_day():
    days = chain()
    capacity = PLACEHOLDER_SITE["column_capacity"]
    branches = {"drainage": 0, "runoff": 0}
    for day in days:
        b = day.balance
        flows = (b.precipitation, b.runoff, b.evaporation, b.transpiration, b.drainage)
        assert all(is_number(flow) and flow >= 0 for flow in flows)
        change = b.storage_end - b.storage_start
        balance = (
            b.precipitation - b.runoff - b.evaporation - b.transpiration - b.drainage
        )
        scale = max(abs(term) for term in (b.storage_start, b.storage_end, *flows))
        assert abs(change - balance) <= 64 * sys.float_info.epsilon * max(scale, 1.0)
        assert 0 <= b.storage_end <= capacity
        branches["drainage"] += b.drainage > 0
        branches["runoff"] += b.runoff > 0
        if day is not days[-1]:
            # No day before the last has a crop; the last is a sowing day.
            assert b.transpiration == 0
    assert all(count > 0 for count in branches.values()), branches


def crop_period_of(
    calendar_: RotationCalendar, day: dt.date
) -> tuple[str, dt.date] | None:
    """The crop label and the first day of the component covering ``day``."""
    for component in calendar_.components:
        if component.start.date <= day <= component.end.date:
            return component.crop_id.split("-", 1)[1], component.start.date
    return None


def expected_by_stage(
    crop: str, day_number: int, initial: float, mid: float, end: float
) -> float:
    """The value of day ``day_number`` of a period (counted from one), written
    out here from the PROPOSED form of FAO-56 Eq. 66, independently of
    ``stages.py``."""
    lengths = placeholder_stage_lengths(crop)
    ini, dev, mid_days, late = (lengths[stage] for stage in GROWTH_STAGES)
    if day_number <= ini:
        return initial
    if day_number <= ini + dev:
        return initial + (day_number - ini) / dev * (mid - initial)
    if day_number <= ini + dev + mid_days:
        return mid
    return mid + (day_number - ini - dev - mid_days) / late * (end - mid)


def test_daily_balance_closes_its_mass_on_days_with_transpiration_given_stage_lengths(
    monkeypatch,
):
    # The balance is wrapped to see the crop of each day it is given.
    crops_given: dict[dt.date, Any] = {}
    step = module.balance.step

    def spy(storage, day, **kwargs):
        crops_given[day.date] = day.crop
        return step(storage, day, **kwargs)

    monkeypatch.setattr(module.balance, "step", spy)
    calendar_ = chain_calendar()
    days = chain(calendar_)
    capacity = PLACEHOLDER_SITE["column_capacity"]
    with_transpiration = 0
    sloped = {"development": 0, "late": 0}
    for day in days:
        b = day.balance
        flows = (b.precipitation, b.runoff, b.evaporation, b.transpiration, b.drainage)
        assert all(is_number(flow) and flow >= 0 for flow in flows)
        change = b.storage_end - b.storage_start
        balance = (
            b.precipitation - b.runoff - b.evaporation - b.transpiration - b.drainage
        )
        scale = max(abs(term) for term in (b.storage_start, b.storage_end, *flows))
        assert abs(change - balance) <= 64 * sys.float_info.epsilon * max(scale, 1.0)
        assert 0 <= b.storage_end <= capacity
        period = crop_period_of(calendar_, day.date)
        if period is None:
            assert b.transpiration == 0
            assert crops_given[day.date] is None
            continue
        crop, sowing = period
        day_number = (day.date - sowing).days + 1
        # The basal coefficient of the stage of the day, interpolated.
        kcb = expected_by_stage(crop, day_number, *PLACEHOLDER_STAGE.values())
        assert b.transpiration_demanded == pytest.approx(
            kcb * day.reference_evapotranspiration
        )
        # The root depth grows from the initial to the maximum root depth.
        maximum = PLACEHOLDER_CROP["maximum_root_depth"][crop]
        root_depth = expected_by_stage(
            crop,
            day_number,
            PLACEHOLDER_CROP["initial_root_depth"][crop],
            maximum,
            maximum,
        )
        given = crops_given[day.date]
        assert given.root_depth == pytest.approx(root_depth)
        assert given.transpiration_coefficient == pytest.approx(kcb)
        assert is_number(b.stress_coefficient)
        with_transpiration += b.transpiration > 0
        lengths = placeholder_stage_lengths(crop)
        ini, dev, mid_days = (lengths[s] for s in GROWTH_STAGES[:3])
        sloped["development"] += ini < day_number <= ini + dev
        sloped["late"] += day_number > ini + dev + mid_days
    assert with_transpiration > 0
    assert all(count > 0 for count in sloped.values()), sloped
    # Every year is computed, so it is missing only for the definition (D61).
    result = run(calendar_=calendar_)
    assert_loads(result)
    for item in result:
        assert_computed(item)


def test_crop_of_each_day_follows_the_calendar():
    calendar_ = chain_calendar()
    first_crop_day = min(component.start.date for component in calendar_.components)
    days = chain(calendar_)
    assert days[0].date < first_crop_day
    for day in days:
        b = day.balance
        assert is_number(b.storage_end)
        if crop_period_of(calendar_, day.date) is None:
            # A day with no crop: computed, with no transpiration.
            assert b.transpiration == 0
            assert isinstance(b.transpiration_demanded, Missing)
            assert b.transpiration_demanded.reason == "NOT_APPLICABLE"
        else:
            # A day with a crop: the crop of the balance is given.
            assert is_number(b.transpiration_demanded)
            assert is_number(b.root_zone_depletion)


def stage_length_key(crop: str, stage: str) -> tuple[str, str]:
    return (STAGE_LENGTH_PARAMETERS[stage], crop)


def test_without_stage_lengths_crop_days_are_missing_with_the_reason_of_d79():
    calendar_ = chain_calendar()
    first_crop_day = min(component.start.date for component in calendar_.components)
    parameters = catalogue_with(
        {
            stage_length_key(crop, stage): None
            for crop in CROPS
            for stage in GROWTH_STAGES
        }
    )
    days = chain(calendar_, parameters=parameters)
    for day in days:
        b = day.balance
        if day.date < first_crop_day:
            assert is_number(b.storage_end)
        elif day.date == first_crop_day:
            # The basal coefficient and the crop of the balance are missing,
            # because the stage of the day is not known (D79).
            assert isinstance(b.storage_end, Missing)
            assert b.storage_end.reason == "MISSING_INPUT"
            assert "crop (MISSING_INPUT)" in b.storage_end.detail
            ke = day.surface_layer.evaporation_coefficient
            assert isinstance(ke, Missing)
            assert "basal_crop_coefficient (MISSING_INPUT)" in ke.detail
        else:
            # The storage carried from that day stays missing (no reset).
            assert isinstance(b.storage_start, Missing)
            assert "missing since" in b.storage_start.detail
    result = run(calendar_=calendar_, parameters=parameters)
    assert_loads(result)
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert f"chain MISSING_INPUT: {module.STAGE_UNKNOWN}" in items_of(detail)
        assert "D79" in detail
        named = no_record_item(detail, json.dumps(unmarked(scope_of("crop-a"))))
        for parameter_id in STAGE_LENGTH_PARAMETERS.values():
            assert f"'{parameter_id}'" in named
    assert f"the first on {first_crop_day.isoformat()}" in result[0].missing.detail


def test_one_crop_without_stage_lengths_leaves_the_other_crop_computed():
    calendar_ = chain_calendar()
    first_b = min(
        component.start.date
        for component in calendar_.components
        if component.crop_id.endswith("crop-b")
    )
    parameters = catalogue_with({stage_length_key("crop-b", "late"): None})
    days = chain(calendar_, parameters=parameters)
    for day in days:
        b = day.balance
        if day.date < first_b:
            # Crop-a days before it, and days with no crop, are computed.
            assert is_number(b.storage_end)
        else:
            assert isinstance(b.storage_end, Missing)
    (first_missing,) = [day for day in days if day.date == first_b]
    assert "crop (MISSING_INPUT)" in first_missing.balance.storage_end.detail


def calendar_with_tail_and_cut(tail: int, cut: int) -> RotationCalendar:
    """The calendar of ``chain_calendar`` with the third period ``tail`` days
    longer and the fourth ``cut`` days shorter than the days the four
    PLACEHOLDER stage lengths of their crop fill (D135, D136)."""
    document = chain_calendar_document()
    third, fourth = document["components"][2:4]
    for component, change in ((third, tail), (fourth, -cut)):
        end = dt.date.fromisoformat(component["end"]["date"])
        component["end"]["date"] = (end + ONE_DAY * change).isoformat()
    return RotationCalendar.model_validate(document)


@pytest.mark.parametrize(
    ("tail", "cut"),
    [
        (1, 1),  # the calendar of fill_periods=False
        (33, 66),  # a longer tail; a cut inside the mid stage of crop-b
    ],
)
def test_stage_lengths_that_do_not_fill_the_period_leave_a_no_crop_tail_or_are_cut_at_harvest(
    monkeypatch, tail, cut
):
    calendar_ = calendar_with_tail_and_cut(tail, cut)
    if (tail, cut) == (1, 1):
        assert calendar_ == RotationCalendar.model_validate(
            chain_calendar_document(fill_periods=False)
        )
    _, _, third, fourth, _ = calendar_.components
    assert fourth.crop_id.endswith("crop-b")
    tail_days = {third.end.date - ONE_DAY * n for n in range(tail)}
    crops_given: dict[dt.date, Any] = {}
    step = module.balance.step

    def spy(storage, day, **kwargs):
        crops_given[day.date] = day.crop
        return step(storage, day, **kwargs)

    monkeypatch.setattr(module.balance, "step", spy)
    given = spy_surface_layer(monkeypatch)
    days = chain(calendar_)
    assert tail_days <= {day.date for day in days}
    following_tew = mulched(PLACEHOLDER_RESIDUE_COVER["crop-b"])
    for day in days:
        b = day.balance
        flows = (b.precipitation, b.runoff, b.evaporation, b.transpiration, b.drainage)
        assert all(is_number(flow) and flow >= 0 for flow in flows), day.date
        balance = (
            b.precipitation - b.runoff - b.evaporation - b.transpiration - b.drainage
        )
        scale = max(abs(term) for term in (b.storage_start, b.storage_end, *flows))
        assert abs(b.storage_end - b.storage_start - balance) <= (
            64 * sys.float_info.epsilon * max(scale, 1.0)
        )
        if day.date in tail_days:
            # D136: no living crop. Nothing reaches the balance as a crop, so
            # nothing is transpired or demanded (out of the ratio, D106), and
            # the surface layer takes the fallow of the crop sown next (#217).
            assert crops_given[day.date] is None
            assert b.transpiration == 0
            assert b.transpiration_demanded.reason == "NOT_APPLICABLE"
            _, day_input, constants = given[day.date]
            assert day_input.cover_fraction == PLACEHOLDER_FALLOW["cover_fraction"]
            assert constants["wetted_fraction"] == PLACEHOLDER_FALLOW["wetted_fraction"]
            assert constants["total_evaporable_water"] == pytest.approx(following_tew)
            continue
        period = crop_period_of(calendar_, day.date)
        if period is None:
            continue
        crop, sowing = period
        day_number = (day.date - sowing).days + 1
        # The stages keep their lengths: not stretched, not shrunk (D135).
        kcb = expected_by_stage(crop, day_number, *PLACEHOLDER_STAGE.values())
        assert crops_given[day.date].transpiration_coefficient == pytest.approx(kcb)
        assert b.transpiration_demanded == pytest.approx(
            kcb * day.reference_evapotranspiration
        )
    # The cut: the harvest day of the fourth period still has a crop, on the
    # line of its whole stage, so it never reaches the end value (D135).
    harvest = crops_given[fourth.end.date]
    initial, mid, end = PLACEHOLDER_STAGE.values()
    assert harvest is not None
    assert harvest.transpiration_coefficient != pytest.approx(end)
    if cut > placeholder_stage_lengths("crop-b")["late"]:
        assert harvest.transpiration_coefficient == pytest.approx(mid)
    # Every day is computed, so every year is missing only for the definition.
    result = run(calendar_=calendar_)
    assert_loads(result)
    for item in result:
        assert_computed(item)


def test_stage_length_that_is_not_whole_days_is_not_computable():
    record = unmarked(
        placeholder_record(STAGE_LENGTH_PARAMETERS["mid"], 11.5, scope_of("crop-a"))
    )
    parameters = catalogue_with({stage_length_key("crop-a", "mid"): record})
    result = run(calendar_=chain_calendar(), parameters=parameters)
    assert_loads(result)
    for item in result:
        assert not is_computed(item)
        assert (
            "chain NOT_COMPUTABLE: the growth stages of component"
            in item.missing.detail
        )
        assert "not a whole number of days" in item.missing.detail
        assert "11.5" not in item.missing.detail  # no value is repeated


def test_a_record_only_late_days_need_leaves_the_earlier_days_computed():
    # Without the basal coefficient at the end of the late stage, the days of
    # the initial, development and mid stages of the crop are computed.
    calendar_ = chain_calendar()
    first, *_ = calendar_.components
    lengths = placeholder_stage_lengths("crop-a")
    first_late = first.start.date + ONE_DAY * int(
        sum(lengths[stage] for stage in GROWTH_STAGES[:3])
    )
    parameters = catalogue_with({("basal_crop_coefficient", "crop-a:end"): None})
    days = chain(calendar_, parameters=parameters)
    for day in days:
        if day.date < first_late:
            assert is_number(day.balance.storage_end)
        elif day.date == first_late:
            ke = day.surface_layer.evaporation_coefficient
            assert isinstance(ke, Missing)
            assert "basal_crop_coefficient (MISSING_INPUT)" in ke.detail
            assert isinstance(day.balance.storage_end, Missing)
    result = run(calendar_=calendar_, parameters=parameters)
    scope = json.dumps(unmarked(scope_of("crop-a:end")))
    for item in result:
        if is_computed(item):
            assert last_day_of(item.ag_year) < first_late
        else:
            named = no_record_item(item.missing.detail, scope)
            assert named.endswith(": 'basal_crop_coefficient'")


def test_empty_catalogue_makes_every_year_missing_input_naming_each_parameter_by_id_and_scope():
    span = several_full_years()
    calendar_ = chain_calendar()
    result = run(calendar_=calendar_, parameters={})
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    assert result
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        site = no_record_item(detail, "{}")
        for parameter_id in (*module.SITE_PARAMETERS, *module.FALLOW_SITE_PARAMETERS):
            assert f"'{parameter_id}'" in site
        no_crop = no_record_item(detail, NO_CROP_SCOPE)
        for parameter_id in (
            *module.DAY_PARAMETERS,
            *module.STAGE_PARAMETERS,
            *module.FALLOW_PARAMETERS,
        ):
            assert f"'{parameter_id}'" in no_crop
        # The cover of the first fallow, read by the crop sown after it.
        first_crop = calendar_.components[0].crop_id
        fallow = no_record_item(
            detail, json.dumps({"crop": first_crop, "management": "no_crop"})
        )
        for parameter_id in module.FALLOW_COVER_PARAMETERS:
            assert f"'{parameter_id}'" in fallow
        for parameter_id in module.CROP_PARAMETERS:
            assert f"'{parameter_id}'" not in no_crop
        last = last_day_of(item.ag_year)
        for component in calendar_.components:
            scope = json.dumps({"crop": component.crop_id})
            named = no_record_item(detail, scope)
            by_stage = [
                no_record_item(
                    detail, json.dumps({"crop": component.crop_id, "stage": stage})
                )
                for stage in module.STAGES
            ]
            if component.start.date <= last:
                for parameter_id in (*module.DAY_PARAMETERS, *module.CROP_PARAMETERS):
                    assert f"'{parameter_id}'" in named
                for named_by_stage in by_stage:
                    for parameter_id in module.STAGE_PARAMETERS:
                        assert f"'{parameter_id}'" in named_by_stage
            elif not any(
                other.crop_id == component.crop_id and other.start.date <= last
                for other in calendar_.components
            ):
                assert named == ""
                assert by_stage == [""] * len(module.STAGES)
        assert "C1.4" in detail


# Parameters of the site that only a day with a crop uses since unit #217: on
# a fallow day the cover fraction and the wetted fraction are records of a day
# with no crop (D110).
CROP_DAY_SITE = ("wetted_fraction", "minimum_crop_coefficient")


@pytest.mark.parametrize(
    "key",
    [(name, None) for name in module.SITE_PARAMETERS]
    + [(name, crop) for name in module.DAY_PARAMETERS for crop in (*CROPS, "no_crop")]
    + [(name, "no_crop") for name in module.STAGE_PARAMETERS]
    + [
        (name, f"{crop}:{stage}")
        for name in module.STAGE_PARAMETERS
        for crop in CROPS
        for stage in module.STAGES
    ]
    + [(name, crop) for name in module.CROP_PARAMETERS for crop in CROPS]
    + [(name, None) for name in module.FALLOW_SITE_PARAMETERS]
    + [(name, "no_crop") for name in module.FALLOW_PARAMETERS]
    + [
        (name, f"fallow:{crop}")
        for name in module.FALLOW_COVER_PARAMETERS
        for crop in CROPS
    ],
)
def test_parameter_with_no_record_is_missing_input_naming_it_and_no_other(key):
    parameter_id, label = key
    # A parameter of the site or of a day with no crop is checked on the
    # calendar with no crop, on which every year is computed with the whole
    # catalogue; a parameter of a crop, a parameter of the site that only a
    # day with a crop uses (CROP_DAY_SITE) and the cover of a fallow on the
    # calendar with crops, on which every year is computed too with the whole
    # catalogue (issues #206, #217).
    with_crops = label not in (None, "no_crop") or (
        label is None and parameter_id in CROP_DAY_SITE
    )
    calendar_ = chain_calendar() if with_crops else bare_calendar()
    result = run(calendar_=calendar_, parameters=catalogue_with({key: None}))
    scope = "{}" if label is None else json.dumps(unmarked(scope_of(label)))
    missing = [item for item in result if not is_computed(item)]
    assert missing, "the parameter is needed by some year"
    if not with_crops:
        assert missing == result  # removing the record makes every year missing
    for item in missing:
        assert item.missing.reason == "MISSING_INPUT"
        named = no_record_item(item.missing.detail, scope)
        assert named.endswith(f": '{parameter_id}'")
        assert item.missing.detail.count("parameters with no record") == 1
    # The years before the one that first needs it are computed.
    computed = [item for item in result if is_computed(item)]
    assert all(item.ag_year < missing[0].ag_year for item in computed)


def test_record_with_null_value_is_missing_input_repeating_its_reason():
    for key in (
        ("column_capacity", None),
        ("net_shortwave_albedo", None),
        ("curve_number", "crop-a"),
    ):
        parameter_id, crop = key
        record = placeholder_record(
            parameter_id, 1.0, {} if crop is None else scope_of(crop)
        )
        record.update(
            value=None,
            value_missing_reason="PLACEHOLDER reason: no value is recorded",
            range=None,
            range_missing_reason="PLACEHOLDER reason: no range is recorded",
            citation=None,
        )
        assert check_record(record) == []
        parameters = catalogue_with({key: record})
        assert check_catalogue(parameters) == []
        calendar_ = bare_calendar() if crop is None else chain_calendar()
        result = run(calendar_=calendar_, parameters=parameters)
        missing = [item for item in result if not is_computed(item)]
        assert missing
        for item in missing:
            assert item.missing.reason == "MISSING_INPUT"
            assert f"parameter '{parameter_id}'" in item.missing.detail
            assert (
                "the record holds no value: UNMARKED_TEST_ONLY reason: no value is recorded"
                in item.missing.detail
            )
            assert "parameters with no record" not in item.missing.detail


def test_record_that_read_value_refuses_is_missing_input_naming_why():
    marked = placeholder_record("column_depth", 2.0, {})
    same_persons = unmarked(placeholder_record("column_depth", 2.0, {}))
    same_persons["checked_by"] = same_persons["transcribed_by"]
    cases = {
        "contains the word PLACEHOLDER": catalogue_with({("column_depth", None): None})
        | {"marked.json": marked},
        "are the same person": catalogue_with({("column_depth", None): same_persons}),
        "two records share this id and scope": catalogue()
        | {"duplicate.json": unmarked(placeholder_record("column_depth", 2.0, {}))},
    }
    for why, parameters in cases.items():
        result = run(parameters=parameters)
        assert result
        for item in result:
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                "parameter 'column_depth' with scope {}: the record is not read"
                in item.missing.detail
            )
            assert why in item.missing.detail


def test_malformed_record_makes_every_parameter_missing_input_naming_it():
    broken = unmarked(placeholder_record("column_depth", 2.22, {}))
    for defect in ("id", "scope"):
        record = dict(broken)
        del record[defect]
        parameters = catalogue() | {"broken/record.json": record}
        assert check_catalogue(parameters) != []
        result = run(parameters=parameters)
        assert_loads(result)
        assert result
        for item in result:
            assert item.missing.reason == "MISSING_INPUT"
            detail = item.missing.detail
            assert (
                "parameters that cannot be looked up: the record(s) "
                "'broken/record.json' have no well-formed 'id' and 'scope'"
            ) in detail
            assert "F3c" in detail
            assert "parameters with no record" not in detail
            named = [
                entry
                for entry in detail.split("; ")
                if entry.startswith(
                    "parameter MISSING_INPUT: parameters that cannot be looked up, scope {}: "
                )
            ]
            assert len(named) == 1
            for parameter_id in module.SITE_PARAMETERS:
                assert f"'{parameter_id}'" in named[0]


def test_parameter_outside_what_a_part_accepts_is_not_computable_and_raises_nothing():
    # An initial storage above the capacity of the column (both PLACEHOLDER).
    too_full = unmarked(placeholder_record("initial_storage", 33.3, {}))
    result = run(parameters=catalogue_with({("initial_storage", None): too_full}))
    assert_loads(result)
    assert result[0].missing.reason == "NOT_COMPUTABLE"
    assert "the daily balance refuses a value" in result[0].missing.detail
    assert "capacity" in result[0].missing.detail
    for item in result:
        assert item.missing.reason in ("NOT_COMPUTABLE", "MISSING_INPUT")


# --- the cases of #191: the drafted water records ------------------------------

DRAFTED_CROPS = tuple(
    sorted({scope["crop"] for _, scope, _ in DRAFTED_RECORDS if "crop" in scope})
)


def drafted_key(parameter_id: str, scope: dict) -> tuple[str, str]:
    """A record by its id and its scope as JSON text with sorted keys."""
    return (parameter_id, json.dumps(scope, sort_keys=True))


def drafted_calendar() -> RotationCalendar:
    """The calendar of ``chain_calendar``, one component per crop of the drafts
    before its last day; the one sown on that day takes the first crop."""
    document = chain_calendar_document()
    *in_the_record, after = document["components"]
    assert len(in_the_record) == len(DRAFTED_CROPS)
    for component, crop in zip(in_the_record, DRAFTED_CROPS, strict=True):
        component["crop_id"] = crop
    after["crop_id"] = DRAFTED_CROPS[0]
    return RotationCalendar.model_validate(document)


def crops_after_a_fallow(calendar_: RotationCalendar) -> set[str]:
    """The crop sown after each day of the record that no component covers."""
    first, last = several_full_years()
    sowings = sorted((c.start.date, c.crop_id) for c in calendar_.components)
    crops = set()
    day = first
    while day <= last:
        if not any(c.start.date <= day <= c.end.date for c in calendar_.components):
            crops.add(next(crop for start, crop in sowings if start > day))
        day += ONE_DAY
    return crops


def read_by_ep3(
    crops: tuple[str, ...], following: set[str] | None = None
) -> set[tuple[str, str]]:
    """Every (id, scope) EP3 reads for a calendar with these crops and days
    with none, the days with none lying before the crops of ``following``
    (by default the crops of ``drafted_calendar``)."""
    if following is None:
        following = crops_after_a_fallow(drafted_calendar())
    no_crop = scope_of("no_crop")
    read = {
        drafted_key(name, {})
        for name in (*module.SITE_PARAMETERS, *module.FALLOW_SITE_PARAMETERS)
    }
    read |= {drafted_key(name, no_crop) for name in module.FALLOW_PARAMETERS}
    read |= {
        drafted_key(name, {"crop": crop, "management": "no_crop"})
        for name in module.FALLOW_COVER_PARAMETERS
        for crop in following
    }
    read |= {
        drafted_key(name, scope)
        for name in module.DAY_PARAMETERS
        for scope in [*({"crop": crop} for crop in crops), no_crop]
    }
    read |= {
        drafted_key(name, scope)
        for name in module.STAGE_PARAMETERS
        for scope in [
            *(
                {"crop": crop, "stage": stage}
                for crop in crops
                for stage in module.STAGES
            ),
            no_crop,
        ]
    }
    read |= {
        drafted_key(name, {"crop": crop})
        for name in module.CROP_PARAMETERS
        for crop in crops
    }
    return read


def drafted_catalogue(leave_out: tuple[str, str] | None = None) -> dict[str, dict]:
    """The drafted records with PLACEHOLDER values, and the others EP3 reads.

    Each drafted record has its id, scope and unit; its value is a value of
    the test catalogue (PLACEHOLDER), never a value of a draft. The records
    EP3 reads that are not drafted are added with the values of the test
    catalogue. ``leave_out`` removes one drafted record.
    """
    drafted = {drafted_key(i, scope) for i, scope, _ in DRAFTED_RECORDS}
    records = []
    for parameter_id, scope, unit in DRAFTED_RECORDS:
        if drafted_key(parameter_id, scope) == leave_out:
            continue
        value = PLACEHOLDER_SITE.get(parameter_id, 1.0) if not scope else 0.555
        record = placeholder_record(parameter_id, value, scope)
        record["unit"] = unit
        records.append(record)
    for parameter_id, scope_text in sorted(read_by_ep3(DRAFTED_CROPS) - drafted):
        scope = json.loads(scope_text)
        if not scope:
            value = PLACEHOLDER_SITE.get(parameter_id, 1.0)
        elif "management" in scope and "crop" in scope:
            value = PLACEHOLDER_RESIDUE_COVER["crop-a"]
        elif parameter_id in PLACEHOLDER_FALLOW:
            value = PLACEHOLDER_FALLOW[parameter_id]
        elif "management" in scope:
            value = PLACEHOLDER_DAY[parameter_id]["no_crop"]
        else:
            value = 1.11
        records.append(placeholder_record(parameter_id, value, scope))
    return unmarked(
        {f"PLACEHOLDER_{position}.json": item for position, item in enumerate(records)}
    )


def test_drafted_records_pass_check_catalogue_and_ep3_reads_every_one(monkeypatch):
    drafted = {drafted_key(i, scope): unit for i, scope, unit in DRAFTED_RECORDS}
    assert len(drafted) == len(DRAFTED_RECORDS)  # no id and scope twice
    # Every drafted id and scope is one EP3 reads.
    assert set(drafted) <= read_by_ep3(DRAFTED_CROPS)
    parameters = drafted_catalogue()
    assert check_catalogue(parameters) == []
    units = {
        drafted_key(record["id"], record["scope"]): record["unit"]
        for record in parameters.values()
    }
    assert {key: units[key] for key in drafted} == drafted
    # EP3 looks every one of them up, with this catalogue and calendar.
    looked_up: set[tuple[str, str]] = set()

    class Recording(_parameters.Catalogue):
        def value(self, parameter_id, scope, day):
            looked_up.add(drafted_key(parameter_id, dict(scope)))
            return super().value(parameter_id, scope, day)

    monkeypatch.setattr(module, "Catalogue", Recording)
    result = run(calendar_=drafted_calendar(), parameters=parameters)
    assert_loads(result)
    assert looked_up == read_by_ep3(DRAFTED_CROPS)
    for item in result:
        assert "parameters with no record" not in item.missing.detail


@pytest.mark.parametrize(
    "drafted",
    [(i, scope) for i, scope, _ in DRAFTED_RECORDS],
    ids=[f"{i}{json.dumps(scope, sort_keys=True)}" for i, scope, _ in DRAFTED_RECORDS],
)
def test_drafted_record_removed_makes_the_result_missing_naming_it(drafted):
    parameter_id, scope = drafted
    key = drafted_key(parameter_id, scope)
    result = run(calendar_=drafted_calendar(), parameters=drafted_catalogue(key))
    assert_loads(result)
    naming = [
        item
        for item in result
        if no_record_item(item.missing.detail, key[1]).endswith(f"'{parameter_id}'")
    ]
    assert naming, "a year names the record"
    first = result.index(naming[0])
    assert result[first:] == naming  # every later year names it too
    for item in naming:
        assert item.missing.reason == "MISSING_INPUT"
        assert item.missing.detail.count("parameters with no record") == 1


# --- the cases of #217: the fallow day (D110, D111, D115, D116) ----------------

# The total evaporable water of the test catalogue, written out from its
# PLACEHOLDER operands (a unit factor, a wilting-point weight and a layer
# depth of one): field capacity less wilting point.
PLACEHOLDER_TEW = (
    PLACEHOLDER_SITE["field_capacity_water_content"]
    - PLACEHOLDER_SITE["wilting_point_water_content"]
)


def mulched(cover: float, reduction: float | None = None) -> float:
    """The total evaporable water of a fallow day, written out here from the
    PROPOSED form of D110 (choice 20), independently of ``fallow.py``."""
    if reduction is None:
        reduction = PLACEHOLDER_SITE["mulch_total_evaporable_water_reduction"]
    increment = PLACEHOLDER_SITE["mulch_cover_increment"]
    return PLACEHOLDER_TEW * (1 - reduction * cover / increment)


def fallow_record(crop: str, value: float) -> dict:
    return unmarked(
        placeholder_record(
            module.SURFACE_RESIDUE_COVER, value, scope_of(f"fallow:{crop}")
        )
    )


def site_record(parameter_id: str, value: float) -> dict:
    return unmarked(placeholder_record(parameter_id, value, {}))


def spy_surface_layer(monkeypatch) -> dict[dt.date, tuple[Any, Any, dict]]:
    """Wrap the daily step of the surface layer; keep what each day is given."""
    given: dict[dt.date, tuple[Any, Any, dict]] = {}
    step = module.evaporation.step

    def spy(depletion_start, day, **kwargs):
        given[day.date] = (depletion_start, day, kwargs)
        return step(depletion_start, day, **kwargs)

    monkeypatch.setattr(module.evaporation, "step", spy)
    return given


def fallow_cover_scope(crop: str) -> str:
    return json.dumps(unmarked(scope_of(f"fallow:{crop}")))


def test_fallow_day_takes_the_records_of_a_day_with_no_crop_and_the_mulched_evaporable_water(
    monkeypatch,
):
    given = spy_surface_layer(monkeypatch)
    # Every day of the record but the last is a day of one fallow, before
    # crop-a, which is sown on the last day (``bare_calendar``).
    *days, sowing_day = chain()
    assert sowing_day.date == several_full_years()[1]
    expected_tew = mulched(PLACEHOLDER_RESIDUE_COVER["crop-a"])
    assert expected_tew < PLACEHOLDER_TEW
    for day in days:
        _, day_input, constants = given[day.date]
        # D110: fc and fw are the records of a day with no crop.
        assert day_input.cover_fraction == PLACEHOLDER_FALLOW["cover_fraction"]
        assert constants["wetted_fraction"] == PLACEHOLDER_FALLOW["wetted_fraction"]
        # D110: the total evaporable water reduced by the cover of the fallow.
        assert constants["total_evaporable_water"] == pytest.approx(expected_tew)
        assert constants["readily_evaporable_water"] == pytest.approx(
            min(PLACEHOLDER_SITE["readily_evaporable_water"], expected_tew)
        )
        assert day.surface_layer.exposed_and_wetted_fraction == pytest.approx(
            min(
                1 - PLACEHOLDER_FALLOW["cover_fraction"],
                PLACEHOLDER_FALLOW["wetted_fraction"],
            )
        )


# A precipitation cycle with long dry spells (PLACEHOLDER), so that the
# surface layer dries into stage 2 and to its total evaporable water.
DRY_SPELLS = [14.44] + [0.0] * 59  # zero: a dry day


def climate_with_dry_spells(
    span: tuple[dt.date, dt.date] | None = None,
) -> SiteClimate:
    first, last = span or several_full_years()
    series = [daily_series(name, first, last) for name in DAILY_INPUTS]
    (precipitation,) = [item for item in series if item["quantity"] == PRECIPITATION]
    for position, day in enumerate(precipitation["days"]):
        day["value"] = DRY_SPELLS[position % len(DRY_SPELLS)]
    return climate_with(series)


def test_residue_cover_reduces_soil_evaporation_on_fallow_days():
    dry = climate_with_dry_spells()
    covered = chain(climate_=dry)
    bare = chain(
        climate_=dry,
        parameters=catalogue_with(
            {("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", 0.0)}
        ),
    )
    assert all(is_number(day.balance.storage_end) for day in [*covered, *bare])
    reduced = mulched(PLACEHOLDER_RESIDUE_COVER["crop-a"])
    rew = PLACEHOLDER_SITE["readily_evaporable_water"]
    # The depletion of the surface layer dries into stage 2 and never passes
    # the reduced total, while the bare soil dries further.
    deepest = max(day.surface_layer.depletion_end for day in covered)
    assert rew < deepest <= reduced
    assert max(day.surface_layer.depletion_end for day in bare) > reduced
    # With no cover the total evaporable water is the one of a day with a crop.
    assert max(day.surface_layer.depletion_end for day in bare) <= PLACEHOLDER_TEW
    # Stage 2 of drying follows the reduced total.
    stage_two = 0
    for day in covered:
        layer = day.surface_layer
        if layer.depletion_start > rew:
            stage_two += 1
            assert layer.reduction_coefficient == pytest.approx(
                (reduced - layer.depletion_start) / (reduced - rew)
            )
    assert stage_two > 0
    # Over the record, the covered fallow evaporates less than the bare one.
    assert sum(day.surface_layer.evaporation for day in covered) < sum(
        day.surface_layer.evaporation for day in bare
    )
    assert sum(day.balance.evaporation for day in covered) < sum(
        day.balance.evaporation for day in bare
    )


def test_readily_evaporable_water_of_a_fallow_day_is_not_above_its_total(
    monkeypatch,
):
    # A larger reduction (still PLACEHOLDER) and a full cover leave a total
    # evaporable water below the readily evaporable water of the site.
    reduction = 0.0777
    full = 1.0  # one, structurally: the whole surface is covered
    expected_tew = mulched(full, reduction)
    assert expected_tew < PLACEHOLDER_SITE["readily_evaporable_water"]
    parameters = catalogue_with(
        {
            ("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", full),
            ("mulch_total_evaporable_water_reduction", None): site_record(
                "mulch_total_evaporable_water_reduction", reduction
            ),
        }
    )
    given = spy_surface_layer(monkeypatch)
    # The fallow days: every day but the last, the sowing day of crop-a.
    *days, _ = chain(parameters=parameters)
    for day in days:
        _, _, constants = given[day.date]
        assert constants["total_evaporable_water"] == pytest.approx(expected_tew)
        assert constants["readily_evaporable_water"] == pytest.approx(expected_tew)
        assert is_number(day.balance.storage_end)
        # REW equal to TEW: the layer dries in stage 1 until it is empty.
        assert day.surface_layer.reduction_coefficient == 1.0


def test_weed_free_fallow_transpires_nothing(monkeypatch):
    crops_given: dict[dt.date, Any] = {}
    step = module.balance.step

    def spy(storage, day, **kwargs):
        crops_given[day.date] = day.crop
        return step(storage, day, **kwargs)

    monkeypatch.setattr(module.balance, "step", spy)
    calendar_ = chain_calendar()
    days = chain(calendar_)
    fallow_days = [day for day in days if crop_period_of(calendar_, day.date) is None]
    assert fallow_days and len(fallow_days) < len(days)
    for day in fallow_days:
        # D111: no crop reaches the balance, so nothing is transpired.
        assert crops_given[day.date] is None
        assert day.balance.transpiration == 0
        assert day.balance.transpiration_demanded.reason == "NOT_APPLICABLE"
        assert day.balance.transpiration_shortfall.reason == "NOT_APPLICABLE"


def test_fallow_and_crop_days_close_their_mass():
    calendar_ = chain_calendar()
    days = chain(calendar_)
    kinds = {"fallow": 0, "crop": 0}
    for day in days:
        kinds["crop" if crop_period_of(calendar_, day.date) else "fallow"] += 1
        layer = day.surface_layer
        terms = (
            layer.depletion_start,
            layer.depletion_end,
            layer.infiltration,
            layer.deep_percolation,
            layer.evaporation_from_exposed_fraction,
        )
        assert all(is_number(term) and term >= 0 for term in terms)
        change = layer.depletion_end - layer.depletion_start
        flows = (
            -layer.infiltration
            + layer.deep_percolation
            + layer.evaporation_from_exposed_fraction
        )
        scale = max(abs(term) for term in terms)
        assert abs(change - flows) <= 64 * sys.float_info.epsilon * max(scale, 1.0)
        b = day.balance
        terms = (b.precipitation, b.runoff, b.evaporation, b.transpiration, b.drainage)
        balance = (
            b.precipitation - b.runoff - b.evaporation - b.transpiration - b.drainage
        )
        scale = max(abs(term) for term in (b.storage_start, b.storage_end, *terms))
        assert abs(b.storage_end - b.storage_start - balance) <= (
            64 * sys.float_info.epsilon * max(scale, 1.0)
        )
    assert all(count > 0 for count in kinds.values()), kinds


def test_crop_days_are_computed_as_before_the_fallow_rules(monkeypatch):
    # On a day with a crop the surface layer is given what unit #206 gave it:
    # the total and readily evaporable water and the wetted fraction of the
    # site, and the cover fraction computed from the basal coefficient.
    given = spy_surface_layer(monkeypatch)
    calendar_ = chain_calendar()
    days = chain(calendar_)
    evaporation = module.evaporation
    crop_days = 0
    for day in days:
        period = crop_period_of(calendar_, day.date)
        if period is None:
            continue
        crop_days += 1
        crop, _ = period
        depletion_start, day_input, constants = given[day.date]
        assert constants == {
            "total_evaporable_water": pytest.approx(PLACEHOLDER_TEW),
            "readily_evaporable_water": PLACEHOLDER_SITE["readily_evaporable_water"],
            "wetted_fraction": PLACEHOLDER_SITE["wetted_fraction"],
            "margin_above_basal": PLACEHOLDER_SITE["margin_above_basal"],
        }
        upper_limit = evaporation.upper_limit_of_crop_coefficient(
            day_input.basal_crop_coefficient,
            day_input.climate_adjusted_upper_limit,
            margin_above_basal=PLACEHOLDER_SITE["margin_above_basal"],
        )
        cover = evaporation.cover_fraction_from_basal_coefficient(
            day_input.basal_crop_coefficient,
            minimum_crop_coefficient=PLACEHOLDER_SITE["minimum_crop_coefficient"],
            upper_limit=upper_limit,
            exponent=PLACEHOLDER_EXPONENT[crop],
        )
        assert day_input.cover_fraction == cover
        assert depletion_start <= PLACEHOLDER_TEW
    assert crop_days > 0


def test_missing_cover_record_names_itself():
    calendar_ = chain_calendar()
    first_b = min(
        c.start.date for c in calendar_.components if c.crop_id.endswith("crop-b")
    )
    # The first day of the fallow before crop-b: the day after the component
    # before it ends.
    first_needed = (
        max(c.end.date for c in calendar_.components if c.end.date < first_b) + ONE_DAY
    )
    assert first_needed < first_b
    result = run(
        calendar_=calendar_,
        parameters=catalogue_with({("surface_residue_cover", "fallow:crop-b"): None}),
    )
    assert_loads(result)
    named_years = 0
    for item in result:
        if last_day_of(item.ag_year) < first_needed:
            assert_computed(item)
            continue
        named_years += 1
        assert item.missing.reason == "MISSING_INPUT"
        named = no_record_item(item.missing.detail, fallow_cover_scope("crop-b"))
        assert named.endswith(": 'surface_residue_cover'")
        assert item.missing.detail.count("parameters with no record") == 1
    assert named_years > 0


def test_cover_record_without_value_repeats_its_reason():
    # D115: where the table gives no cap, the upper level is missing with its
    # reason (the reason here is PLACEHOLDER).
    record = placeholder_record(
        module.SURFACE_RESIDUE_COVER, 1.0, scope_of("fallow:crop-a")
    )
    record.update(
        value=None,
        value_missing_reason="PLACEHOLDER reason: no cap is recorded for this fallow",
        range=None,
        range_missing_reason="PLACEHOLDER reason: no range is recorded",
        citation=None,
    )
    assert check_record(record) == []
    parameters = catalogue_with(
        {("surface_residue_cover", "fallow:crop-a"): unmarked(record)}
    )
    assert check_catalogue(parameters) == []
    result = run(parameters=parameters)
    assert_loads(result)
    scope = fallow_cover_scope("crop-a")
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        assert (
            f"parameter 'surface_residue_cover' with scope {scope}: the record holds "
            "no value: UNMARKED_TEST_ONLY reason: no cap is recorded for this fallow"
        ) in item.missing.detail
        assert "parameters with no record" not in item.missing.detail


def test_fallow_with_no_crop_after_it_is_missing_naming_open_31():
    document = chain_calendar_document()
    *in_the_record, _ = document["components"]
    document["components"] = in_the_record
    _, last = several_full_years()
    document["end_date"] = last.isoformat()
    calendar_ = RotationCalendar.model_validate(document)
    last_crop_day = max(c.end.date for c in calendar_.components)
    assert last_crop_day < last
    result = run(calendar_=calendar_)
    assert_loads(result)
    *before, final = result
    for item in before:
        assert_computed(item)
    assert final.missing.reason == "MISSING_INPUT"
    assert f"chain MISSING_INPUT: {module.fallow.NO_FOLLOWING_CROP}" in items_of(
        final.missing.detail
    )
    assert "OPEN 31" in final.missing.detail
    first_missing = (last_crop_day + ONE_DAY).isoformat()
    assert f"the first on {first_missing}" in final.missing.detail


def test_calendar_with_no_component_has_no_following_crop_naming_open_31():
    # Nothing is ever sown, so no fallow has a crop that follows it.
    document = chain_calendar_document()
    document["components"] = []
    result = run(calendar_=RotationCalendar.model_validate(document))
    assert_loads(result)
    first, _ = several_full_years()
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"chain MISSING_INPUT: {module.fallow.NO_FOLLOWING_CROP}" in items_of(
            item.missing.detail
        )
        assert "OPEN 31" in item.missing.detail
    assert f"the first on {first.isoformat()}" in result[0].missing.detail


def check_carried_depletion(
    days: list[module.ChainDay],
    given: dict[dt.date, tuple[Any, Any, dict]],
    initial: float,
) -> int:
    """Decision D185 of issue #77 (OPEN 30), written out here independently of
    ``exposure._layer_start``, day by day: the step starts from the depletion
    carried in, or from the total of the day when the depletion is above it;
    the infiltration of the day (precipitation less the runoff applied)
    refills the part above the total first, and only the rest is given to the
    step; the part not refilled is carried on top of the depletion at the end
    of the day, and while some is left the layer evaporates nothing. Across
    days the carried depletion closes its mass with the real infiltration:
    its change is -I + DP + E/few. Returns the number of days that started
    above their total."""
    carried = initial
    days_above = 0
    for day in days:
        depletion_start, day_input, constants = given[day.date]
        layer = day.surface_layer
        total = constants["total_evaporable_water"]
        precipitation = day.precipitation
        infiltration = precipitation - min(day.runoff.runoff, precipitation)
        if carried > total:
            days_above += 1
            above = carried - total
            refill = min(above, infiltration)
            left = above - refill
            assert depletion_start == pytest.approx(total)
            assert day_input.precipitation == pytest.approx(precipitation - refill)
            if left > 0:
                # The layer stays at its limit all day: neither it nor the
                # column evaporates, whatever the readily evaporable water.
                assert layer.evaporation == 0
                assert day.balance.evaporation == 0
            expected = layer.depletion_end + left
        else:
            assert depletion_start == pytest.approx(carried)
            assert day_input.precipitation == precipitation
            expected = layer.depletion_end
        assert day.surface_depletion_carried == pytest.approx(expected)
        change = day.surface_depletion_carried - carried
        flows = (
            -infiltration
            + layer.deep_percolation
            + layer.evaporation_from_exposed_fraction
        )
        scale = max(abs(term) for term in (carried, infiltration, change, flows))
        assert abs(change - flows) <= 64 * sys.float_info.epsilon * max(scale, 1.0)
        # The column balance is given the whole precipitation of the day.
        assert day.balance.precipitation == precipitation
        carried = day.surface_depletion_carried
    return days_above


def test_depletion_above_the_reduced_evaporable_water_is_kept_and_refilled_first(
    monkeypatch,
):
    # An initial depletion within the total evaporable water of a day with a
    # crop and above the one of the fallow (both PLACEHOLDER).
    start = 4.22
    reduced = mulched(PLACEHOLDER_RESIDUE_COVER["crop-a"])
    assert reduced < start < PLACEHOLDER_TEW
    above = {("initial_depletion", None): site_record("initial_depletion", start)}
    given = spy_surface_layer(monkeypatch)
    days = chain(parameters=catalogue_with(above))
    # D185: the first day of the fallow starts at its
    # reduced total, with Kr zero and no evaporation, and the depletion above
    # it is carried, not dropped (it is a dry day of the PLACEHOLDER cycle).
    first = days[0]
    assert first.precipitation == 0
    assert first.surface_layer.depletion_start == pytest.approx(reduced)
    assert first.surface_layer.evaporation == 0
    assert first.surface_depletion_carried == pytest.approx(start)
    assert check_carried_depletion(days, given, start) > 0
    assert all(is_number(day.balance.storage_end) for day in days)
    for item in run(parameters=catalogue_with(above)):
        assert_computed(item)
    # With no cover the same depletion lies within the total: unchanged.
    given.clear()
    bare = chain(
        parameters=catalogue_with(
            above
            | {("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", 0.0)}
        )
    )
    assert bare[0].surface_layer.depletion_start == pytest.approx(start)
    assert check_carried_depletion(bare, given, start) == 0


# A precipitation cycle (PLACEHOLDER): two dry days, a rain smaller than the
# depletion above a fully covered fallow's total, two dry days, then a rain
# larger than what is left of it, then dry days.
PARTIAL_REFILL = [0.0, 0.0, 0.555, 0.0, 0.0, 14.44] + [0.0] * 6  # zero: a dry day


def climate_with_partial_refill() -> SiteClimate:
    first, last = several_full_years()
    series = [daily_series(name, first, last) for name in DAILY_INPUTS]
    (precipitation,) = [item for item in series if item["quantity"] == PRECIPITATION]
    for position, day in enumerate(precipitation["days"]):
        day["value"] = PARTIAL_REFILL[position % len(PARTIAL_REFILL)]
    return climate_with(series)


def test_depletion_above_the_total_is_refilled_by_rain_before_evaporation_resumes(
    monkeypatch,
):
    full = 1.0  # one, structurally: the whole surface is covered
    start = 4.4
    reduced = mulched(full)
    assert reduced < start < PLACEHOLDER_TEW
    parameters = catalogue_with(
        {
            ("initial_depletion", None): site_record("initial_depletion", start),
            ("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", full),
        }
    )
    given = spy_surface_layer(monkeypatch)
    days = chain(climate_=climate_with_partial_refill(), parameters=parameters)
    assert check_carried_depletion(days, given, start) > 0

    def infiltration(day: module.ChainDay) -> float:
        return day.precipitation - min(day.runoff.runoff, day.precipitation)

    # Day three's rain refills part of the depletion above the total, not all.
    assert 0 < infiltration(days[2]) < start - reduced
    # Day six's rain refills the rest.
    assert infiltration(days[5]) > start - reduced - infiltration(days[2])
    # Under D185 the layer evaporates nothing while the depletion is at or
    # above the reduced total: on days one to six the step starts at it, and
    # here (the readily evaporable water below the reduced total) Kr is zero
    # there; the column evaporates nothing either. Brought down to the total
    # instead (option (b)), the layer would already evaporate on day four.
    # Here the layer evaporates again from day seven, since Kr follows the
    # depletion at the start of the day; with the readily evaporable water at
    # the total it can do so on the day of the rain that refills the rest
    # (test_column_evaporates_nothing_while_the_layer_is_at_its_limit).
    rew = PLACEHOLDER_SITE["readily_evaporable_water"]
    assert rew < reduced
    for day in days[:6]:
        assert day.surface_layer.depletion_start == pytest.approx(reduced)
        assert day.surface_layer.reduction_coefficient == 0
        assert day.surface_layer.evaporation == 0
        assert day.balance.evaporation == 0
    assert days[2].surface_depletion_carried == pytest.approx(
        start - infiltration(days[2])
    )
    assert days[4].surface_depletion_carried == pytest.approx(
        start - infiltration(days[2])
    )
    assert days[6].surface_layer.evaporation > 0
    for item in run(climate_=climate_with_partial_refill(), parameters=parameters):
        assert_computed(item)


def test_initial_depletion_above_the_total_of_the_layer_is_still_not_computable():
    # The chain never carries a depletion above the total of the layer before
    # any residue, so one above it can only be a record the part refuses
    # (choice 12): the rule of D185 is not applied to it (PLACEHOLDER value).
    start = 4.444
    assert start > PLACEHOLDER_TEW
    result = run(
        parameters=catalogue_with(
            {("initial_depletion", None): site_record("initial_depletion", start)}
        )
    )
    assert_loads(result)
    refused = (
        "chain NOT_COMPUTABLE: the surface-layer balance refuses a value: "
        "depletion_start must not be greater than total_evaporable_water"
    )
    for item in result:
        # The surface layer is NOT_COMPUTABLE from the first day; the balance
        # that reads its Ke is missing with that input, as after any refused
        # value upstream.
        assert item.missing.reason != "NOT_AVAILABLE"
        assert refused in items_of(item.missing.detail)


def test_carried_depletion_closes_its_mass_across_fallow_and_crop_days(monkeypatch):
    # On the calendar with crops, the first days are a fallow before crop-a
    # whose reduced total lies below this initial depletion (PLACEHOLDER); the
    # later fallows before crop-a and crop-b and the crop days follow.
    start = 4.22
    assert mulched(PLACEHOLDER_RESIDUE_COVER["crop-a"]) < start < PLACEHOLDER_TEW
    parameters = catalogue_with(
        {("initial_depletion", None): site_record("initial_depletion", start)}
    )
    given = spy_surface_layer(monkeypatch)
    calendar_ = chain_calendar()
    days = chain(calendar_, parameters=parameters)
    kinds = {"fallow": 0, "crop": 0}
    for day in days:
        kinds["crop" if crop_period_of(calendar_, day.date) else "fallow"] += 1
    assert all(count > 0 for count in kinds.values()), kinds
    assert check_carried_depletion(days, given, start) > 0
    assert all(is_number(day.balance.storage_end) for day in days)
    # With long dry spells the layer ends crops drier than the reduced total
    # of the fallow that follows: the entry from a crop into a fallow above
    # its total, and the return from a fallow to a crop, both close the mass.
    given.clear()
    days = chain(calendar_, climate_with_dry_spells())
    initial = PLACEHOLDER_SITE["initial_depletion"]
    assert check_carried_depletion(days, given, initial) > 0
    entries = returns = 0
    before = days[0]
    for day in days[1:]:
        crop_before = crop_period_of(calendar_, before.date) is not None
        crop_now = crop_period_of(calendar_, day.date) is not None
        total = given[day.date][2]["total_evaporable_water"]
        if crop_before and not crop_now and before.surface_depletion_carried > total:
            entries += 1
        if crop_now and not crop_before:
            returns += 1
        before = day
    assert entries > 0 and returns > 0, (entries, returns)
    assert all(is_number(day.balance.storage_end) for day in days)


def pass_through(depletion, total, layer_total, precipitation, runoff):
    """The start of the step with no rule: the depletion and the precipitation
    of the day passed through unchanged, as the chain gave them to the step
    before D185 on every day."""
    return module.LayerStart(
        depletion=depletion, precipitation=precipitation, above=None
    )


def test_without_a_depletion_above_the_total_the_chain_is_the_one_before_d185(
    monkeypatch,
):
    # D185 changes nothing where no day starts above its total: on the runs
    # of the existing cases, the chain is identical, day by day and field by
    # field, to the one computed with its two rules replaced by pass-throughs
    # (the start of the step, and the Ke the column is given), which is the
    # chain before this unit. In these runs the readily evaporable water is
    # below every total, so a day at its limit already has Kr of zero.
    runs = {
        "bare calendar": {},
        "calendar with crops": {"calendar_": chain_calendar()},
        "bare calendar, dry spells": {"climate_": climate_with_dry_spells()},
    }
    for name, arguments in runs.items():
        given = spy_surface_layer(monkeypatch)
        days = chain(**arguments)
        carried = PLACEHOLDER_SITE["initial_depletion"]
        for day in days:
            depletion_start, _, constants = given[day.date]
            assert carried <= constants["total_evaporable_water"], (name, day.date)
            assert depletion_start == carried
            carried = day.surface_depletion_carried
        result = run(**arguments)
        monkeypatch.setattr(module, "_layer_start", pass_through)
        monkeypatch.setattr(
            module,
            "_column_evaporation_coefficient",
            lambda surface, start, total, no_crop: surface.evaporation_coefficient,
        )
        assert chain(**arguments) == days, name
        assert run(**arguments) == result, name
        monkeypatch.undo()


def option_b(depletion, total, layer_total, precipitation, runoff):
    """Option (b) of OPEN 30, not taken by D185, written out here: a depletion
    above the total of the day (and within the total of the layer) is brought
    down to the total; nothing is refilled and nothing is carried above it."""
    if (
        isinstance(depletion, Missing)
        or isinstance(total, Missing)
        or isinstance(layer_total, Missing)
        or depletion <= total
        or depletion > layer_total
    ):
        return pass_through(depletion, total, layer_total, precipitation, runoff)
    return module.LayerStart(depletion=total, precipitation=precipitation, above=None)


def test_option_b_evaporates_no_less_and_at_most_the_excess_more(monkeypatch):
    # Two runs with days above their total: the fully covered fallow of the
    # partial refill, and the calendar with crops under long dry spells.
    full = 1.0  # one, structurally: the whole surface is covered
    partial = {
        "climate_": climate_with_partial_refill(),
        "parameters": catalogue_with(
            {
                ("initial_depletion", None): site_record("initial_depletion", 4.4),
                ("surface_residue_cover", "fallow:crop-a"): fallow_record(
                    "crop-a", full
                ),
            }
        ),
    }
    dry = {"calendar_": chain_calendar(), "climate_": climate_with_dry_spells()}
    initial_of = {
        "partial refill": 4.4,
        "dry spells": PLACEHOLDER_SITE["initial_depletion"],
    }
    for name, arguments in (("partial refill", partial), ("dry spells", dry)):
        given = spy_surface_layer(monkeypatch)
        kept = chain(**arguments)
        # The bound rests on the daily step never ending drier from a wetter
        # start: its stage-2 loss per millimetre of depletion is not above
        # one, (Kc_max - Kcb) x ET0 / few <= TEW - REW, on every day.
        for day in kept:
            _, day_input, constants = given[day.date]
            layer = day.surface_layer
            if layer.exposed_and_wetted_fraction == 0:
                continue  # zero: no exposed soil, so Ke is zero that day
            loss = (
                (layer.upper_limit - day_input.basal_crop_coefficient)
                * day_input.reference_evapotranspiration
                / layer.exposed_and_wetted_fraction
            )
            span = (
                constants["total_evaporable_water"]
                - constants["readily_evaporable_water"]
            )
            assert loss <= span, (name, day.date, loss, span)
        # The days that start above their total after a day that did not,
        # with the excess of each.
        excess = {}
        carried = initial_of[name]
        above_before = False
        for day in kept:
            total = given[day.date][2]["total_evaporable_water"]
            above = carried > total
            if above and not above_before:
                excess[day.date] = carried - total
            above_before = above
            carried = day.surface_depletion_carried
        assert excess, name
        few = max(day.surface_layer.exposed_and_wetted_fraction for day in kept)
        monkeypatch.undo()
        monkeypatch.setattr(module, "_layer_start", option_b)
        brought_down = chain(**arguments)
        monkeypatch.undo()
        for b, d in zip(brought_down, kept):
            scale = max(b.surface_layer.evaporation, d.surface_layer.evaporation, 1.0)
            assert b.surface_layer.evaporation >= d.surface_layer.evaporation - (
                64 * sys.float_info.epsilon * scale
            ), (name, d.date)
        sum_b = sum(day.surface_layer.evaporation for day in brought_down)
        sum_d = sum(day.surface_layer.evaporation for day in kept)
        bound = few * sum(excess.values())
        message = (name, sorted(excess), sum_b, sum_d, bound)
        assert sum_b - sum_d >= 0, message
        assert sum_b - sum_d <= bound, message
        if name == "partial refill":
            # The small rain lets option (b) evaporate part of the excess
            # before the large rain wets both layers: it evaporates more.
            assert sum_b - sum_d > 0, message


# A precipitation cycle (PLACEHOLDER): two dry days, a rain whose runoff is
# above zero and whose infiltration is below the depletion above the reduced
# total, two dry days, a rain that refills the rest and more, then dry days.
RUNOFF_REFILL = [0.0, 0.0, 3.33, 0.0, 0.0, 14.44] + [0.0] * 6  # zero: a dry day


def climate_with_runoff_refill() -> SiteClimate:
    first, last = several_full_years()
    series = [daily_series(name, first, last) for name in DAILY_INPUTS]
    (precipitation,) = [item for item in series if item["quantity"] == PRECIPITATION]
    for position, day in enumerate(precipitation["days"]):
        day["value"] = RUNOFF_REFILL[position % len(RUNOFF_REFILL)]
    return climate_with(series)


@pytest.mark.parametrize(
    "reduction",
    [
        0.0555,  # PLACEHOLDER: a full cover leaves the reduced total at REW
        0.0666,  # PLACEHOLDER: a full cover leaves it below REW (REW capped)
    ],
)
def test_column_evaporates_nothing_while_the_layer_is_at_its_limit(
    monkeypatch, reduction
):
    # D185: while the depletion is at or above the reduced total the layer has
    # no evaporable water, whatever the readily evaporable water. With REW at
    # the reduced total (D110: "REW not above TEW") the stage-1 rule of the
    # step gives Kr of one there; the column is still given no evaporation
    # while the layer stays at its limit, and both balances close.
    full = 1.0  # one, structurally: the whole surface is covered
    start = 4.4
    reduced = mulched(full, reduction)
    assert reduced <= PLACEHOLDER_SITE["readily_evaporable_water"]
    assert reduced < start < PLACEHOLDER_TEW
    curve_number = unmarked(
        placeholder_record(module.CURVE_NUMBER, 1.666, scope_of("no_crop"))
    )
    parameters = catalogue_with(
        {
            ("initial_depletion", None): site_record("initial_depletion", start),
            ("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", full),
            ("mulch_total_evaporable_water_reduction", None): site_record(
                "mulch_total_evaporable_water_reduction", reduction
            ),
            ("curve_number", "no_crop"): curve_number,
        }
    )
    given = spy_surface_layer(monkeypatch)
    days = chain(climate_=climate_with_runoff_refill(), parameters=parameters)
    assert check_carried_depletion(days, given, start) > 0
    at_limit = with_kr_one = same_day = 0
    carried = start
    for day in days:
        depletion_start, _, constants = given[day.date]
        total = constants["total_evaporable_water"]
        layer, column = day.surface_layer, day.balance
        if carried >= total:
            at_limit += 1
            assert depletion_start == pytest.approx(total)
            if layer.reduction_coefficient > 0:
                with_kr_one += 1
            if layer.evaporation == 0:
                assert column.evaporation == 0, day.date
            else:
                # A rain refilled the part above the total and more: the layer
                # evaporates that same day, and the column no more than it.
                same_day += 1
                assert column.evaporation <= layer.evaporation * (
                    1 + 64 * sys.float_info.epsilon
                )
        terms = (column.precipitation, column.runoff, column.evaporation)
        balance = (
            column.precipitation
            - column.runoff
            - column.evaporation
            - column.transpiration
            - column.drainage
        )
        scale = max(abs(t) for t in (column.storage_start, column.storage_end, *terms))
        assert abs(column.storage_end - column.storage_start - balance) <= (
            64 * sys.float_info.epsilon * max(scale, 1.0)
        )
        carried = day.surface_depletion_carried
    # The case of the finding is met: days at the limit with Kr above zero,
    # and days on which the layer evaporates on the day of the refill.
    assert at_limit > 0 and with_kr_one > 0 and same_day > 0, (
        at_limit,
        with_kr_one,
        same_day,
    )
    # Day three's rain runs off in part, and its infiltration refills only
    # part of the depletion above the total: the refill is the infiltration,
    # not the precipitation.
    third = days[2]
    infiltration = third.precipitation - min(third.runoff.runoff, third.precipitation)
    assert third.runoff.runoff > 0
    assert infiltration < start - reduced < third.precipitation
    assert third.surface_depletion_carried == pytest.approx(start - infiltration)
    assert third.balance.evaporation == 0
    for item in run(climate_=climate_with_runoff_refill(), parameters=parameters):
        assert_computed(item)


@pytest.mark.parametrize(
    ("precipitation", "runoff", "refill"),
    [
        (3.33, 2.22, 1.11),  # the infiltration refills part of the excess
        (1.11, 2.22, 0.0),  # zero: runoff above the precipitation, nothing infiltrates
        (3.33, 0.0, 2.18),  # zero runoff: the whole excess is refilled
    ],
)
def test_the_refill_is_the_infiltration_not_the_precipitation(
    precipitation, runoff, refill
):
    # D185: infiltration first refills the depletion above the reduced total.
    # The infiltration is the precipitation less the runoff the step applies,
    # min(runoff, precipitation), never the precipitation itself
    # (PLACEHOLDER numbers).
    depletion, total = 4.4, 2.22
    above = depletion - total
    start = module._layer_start(
        depletion, total, PLACEHOLDER_TEW, precipitation, runoff
    )
    expected_refill = min(above, precipitation - min(runoff, precipitation))
    assert expected_refill == pytest.approx(refill)
    assert start.depletion == total
    assert start.precipitation == pytest.approx(precipitation - expected_refill)
    assert start.above == pytest.approx(above - expected_refill)


def test_a_fallow_day_that_starts_exactly_at_a_total_equal_to_rew_evaporates_nothing(
    monkeypatch,
):
    # D185: "while the depletion is at or above the reduced total, Kr is
    # zero". A fully covered fallow with a PLACEHOLDER reduction that leaves
    # the reduced total equal to REW (D110: "REW not above TEW"), and an
    # initial depletion exactly at that total, with no part above it: the
    # first day (dry) starts exactly at the total, the stage-1 rule of the step
    # reports a reduction coefficient of one there, and neither the layer nor
    # the column evaporates. Runs of this shape differ from the chain before
    # D185, whose column took the Ke of the step: shown at the end.
    full = 1.0  # one, structurally: the whole surface is covered
    reduction = 0.0555  # PLACEHOLDER: a full cover leaves the reduced total at REW
    assert mulched(full, reduction) == pytest.approx(
        PLACEHOLDER_SITE["readily_evaporable_water"]
    )
    records = {
        ("surface_residue_cover", "fallow:crop-a"): fallow_record("crop-a", full),
        ("mulch_total_evaporable_water_reduction", None): site_record(
            "mulch_total_evaporable_water_reduction", reduction
        ),
    }
    # The reduced total exactly as the chain computes it, read from its step.
    given = spy_surface_layer(monkeypatch)
    chain(parameters=catalogue_with(records))
    first_day = several_full_years()[0]
    total = given[first_day][2]["total_evaporable_water"]
    assert given[first_day][2]["readily_evaporable_water"] == total
    parameters = catalogue_with(
        records | {("initial_depletion", None): site_record("initial_depletion", total)}
    )
    given.clear()
    first, *_ = chain(parameters=parameters)
    assert first.date == first_day and first.precipitation == 0
    depletion_start, _, constants = given[first_day]
    assert constants["total_evaporable_water"] == total
    assert depletion_start == total
    layer = first.surface_layer
    assert layer.reduction_coefficient == 1.0
    assert layer.evaporation_coefficient > 0
    assert layer.evaporation == 0
    assert first.balance.evaporation == 0
    assert first.surface_depletion_carried == total
    for item in run(parameters=parameters):
        assert_computed(item)
    # Before D185 the column took the Ke of the step on that day.
    monkeypatch.setattr(
        module,
        "_column_evaporation_coefficient",
        lambda surface, start, total, no_crop: surface.evaporation_coefficient,
    )
    before, *_ = chain(parameters=parameters)
    assert before.surface_layer.evaporation == 0
    assert before.balance.evaporation > 0


@pytest.mark.parametrize(
    ("label", "value", "why"),
    [
        ("cover", 1.11, "outside zero to one"),
        ("cover", -0.111, "outside zero to one"),
        ("increment", 0.0, "cover increment of the mulch reduction is not above zero"),
        ("reduction", -0.0333, "per increment of cover is below zero"),
        ("reduction", 0.444, "leaves no evaporable water"),
    ],
)
def test_mulch_values_outside_what_the_method_computes_are_not_computable(
    label, value, why
):
    key, record = {
        "cover": (
            ("surface_residue_cover", "fallow:crop-a"),
            fallow_record("crop-a", value),
        ),
        "increment": (
            ("mulch_cover_increment", None),
            site_record("mulch_cover_increment", value),
        ),
        "reduction": (
            ("mulch_total_evaporable_water_reduction", None),
            site_record("mulch_total_evaporable_water_reduction", value),
        ),
    }[label]
    result = run(parameters=catalogue_with({key: record}))
    assert_loads(result)
    for item in result:
        assert not is_computed(item)
        (entry,) = [
            entry
            for entry in items_of(item.missing.detail)
            if entry.startswith("chain NOT_COMPUTABLE: ")
        ]
        assert why in entry
        assert repr(value) not in entry  # no value is repeated


# --- the cases of #135, with the catalogue ------------------------------------


def test_examples_as_they_are_load_and_every_item_is_missing():
    result = run(
        calendar_=calendar(),
        climate_=SiteClimate.model_validate(climate_document()),
        parameters={},
    )
    assert_loads(result)
    series = example_precipitation()
    span = (
        dt.date.fromisoformat(series["start_date"]),
        dt.date.fromisoformat(series["end_date"]),
    )
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    for item in result:
        assert item.time_basis == "ag_year"
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason in REASON_CODES


def test_several_agricultural_years_load_into_results_per_rotation():
    span = several_full_years()
    result = run(climate_=climate(span))
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    assert len(result) > 1
    assert {item.time_basis for item in result} == {"ag_year"}
    results = json.loads(
        (
            ROOT
            / "contracts"
            / "results"
            / "examples"
            / "PLACEHOLDER_results_per_rotation.json"
        ).read_text("utf-8")
    )
    results["water_deficit_exposure"] = [
        item.model_dump(mode="json") for item in result
    ]
    loaded = ResultsPerRotation.model_validate(results)
    assert list(loaded.water_deficit_exposure) == result


def test_infeasible_calendar_makes_every_item_not_computable():
    first, last = several_full_years()
    span = (first + ONE_DAY, last)  # the first year is not covered whole
    for parameters in (catalogue(), {}):
        result = run(
            calendar_=infeasible_calendar(),
            climate_=climate(span),
            parameters=parameters,
        )
        assert [item.ag_year for item in result] == expected_ag_years(*span)
        for item in result:
            assert item.missing.reason == "NOT_COMPUTABLE"
            assert "infeasible" in item.missing.detail


def test_year_not_covered_by_a_series_is_no_coverage():
    first, last = several_full_years()
    # The record starts and ends inside agricultural years.
    span = (first + ONE_DAY, last - ONE_DAY)
    result = run(climate_=climate(span))
    years = expected_ag_years(*span)
    assert [item.ag_year for item in result] == years
    for item in result:
        if item.ag_year in (years[0], years[-1]):
            assert item.missing.reason == "NO_COVERAGE"
            assert f"'{PRECIPITATION}'" in item.missing.detail
            assert "C5.5" in item.missing.detail
        else:
            assert_computed(item)

    # One input of the reference evapotranspiration is shorter than the record.
    for short in CLIMATE_QUANTITIES:
        series = [
            daily_series(name, first, last - ONE_DAY if name == short else last)
            for name in DAILY_INPUTS
        ]
        result = run(climate_=climate_with(series))
        assert [item.ag_year for item in result] == expected_ag_years(first, last)
        assert result[-1].missing.reason == "NO_COVERAGE"
        assert f"'{short}'" in result[-1].missing.detail
        assert f"'{PRECIPITATION}'" not in result[-1].missing.detail
        for item in result[:-1]:
            assert_computed(item)


def test_series_one_day_short_at_each_end_leaves_first_and_last_not_covered():
    first, last = several_full_years()
    exact = run(climate_=climate((first, last)))
    for item in exact:
        assert_computed(item)
    short = run(climate_=climate((first + ONE_DAY, last - ONE_DAY)))
    assert [item.ag_year for item in short] == [item.ag_year for item in exact]
    first_year, *between, last_year = short
    assert first_year.missing.reason == last_year.missing.reason == "NO_COVERAGE"
    assert between
    for item in between:
        assert_computed(item)


def test_absent_daily_series_is_missing_input_naming_it():
    for absent in CLIMATE_QUANTITIES:
        kept = tuple(name for name in DAILY_INPUTS if name != absent)
        result = run(climate_=climate(quantities=kept))
        assert [item.ag_year for item in result] == expected_ag_years(
            *several_full_years()
        )
        for item in result:
            assert item.missing.reason == "MISSING_INPUT"
            first_item = items_of(item.missing.detail)[0]
            assert first_item.startswith("input MISSING_INPUT")
            assert f"no daily series '{absent}'" in first_item
            for other in kept:
                assert f"no daily series '{other}'" not in item.missing.detail


def test_days_held_missing_are_missing_input_naming_the_series():
    first, _ = several_full_years()
    held = first_day_of(first.year + 1) + dt.timedelta(days=100)
    result = run(climate_=climate(held_missing=(held,)))
    computed, holding, after = result
    assert_computed(computed)
    for item in (holding, after):
        assert item.missing.reason == "MISSING_INPUT"
        assert held.isoformat() in item.missing.detail
    inputs = [
        entry for entry in items_of(holding.missing.detail) if entry.startswith("input")
    ]
    assert len(inputs) == len(DAILY_INPUTS)
    for name, entry in zip(DAILY_INPUTS, inputs, strict=True):
        assert entry.startswith("input MISSING_INPUT")
        assert f"'{name}'" in entry
        assert f"agricultural year {holding.ag_year}" in entry
        assert f"the first on {held.isoformat()}" in entry
    # No gap is filled: the balance does not restart after the held day.
    assert not [
        entry for entry in items_of(after.missing.detail) if entry.startswith("input")
    ]
    assert "missing since" in after.missing.detail


@pytest.mark.parametrize(
    "names", [("latitude",), ("elevation",), ("latitude", "elevation"), ("longitude",)]
)
def test_missing_point_value_is_named_in_an_input_item(names):
    document = climate_document()
    document["daily_series"] = [
        daily_series(name, *several_full_years()) for name in DAILY_INPUTS
    ]
    document["point"]["latitude"]["unit"] = module.POINT_UNITS.latitude_decimal_degrees
    document["point"]["elevation"]["unit"] = module.POINT_UNITS.elevation
    for name in names:
        unit = document["point"][name]["unit"]
        document["point"][name] = {
            "value": None,
            "unit": unit,
            "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
        }
    result = run(climate_=SiteClimate.model_validate(document))
    read = [name for name in names if name != "longitude"]
    for item in result:
        if not read:
            assert_computed(item)
            continue
        assert item.missing.reason == "MISSING_INPUT"
        point_items = [
            entry
            for entry in items_of(item.missing.detail)
            if "point of the climate record" in entry
        ]
        assert len(point_items) == len(read)
        for name, entry in zip(read, point_items, strict=True):
            assert entry.startswith(f"input NO_COVERAGE: the {name} of the point")
            assert entry.endswith(": PLACEHOLDER")
        assert "longitude" not in item.missing.detail


def test_series_in_different_time_zones_make_every_item_not_computable():
    first, last = several_full_years()
    series = [daily_series(name, first, last) for name in DAILY_INPUTS]
    series[-1]["time_zone"] = "PLACEHOLDER_other_time_zone"
    result = run(climate_=climate_with(series))
    assert [item.ag_year for item in result] == expected_ag_years(first, last)
    for item in result:
        assert item.missing.reason == "NOT_COMPUTABLE"
        assert "C6.3" in item.missing.detail


def test_input_in_a_unit_not_accepted_is_missing_input_naming_it_and_q11():
    first, last = several_full_years()
    for name in DAILY_INPUTS:
        series = [daily_series(other, first, last) for other in DAILY_INPUTS]
        series[DAILY_INPUTS.index(name)]["unit"] = "PLACEHOLDER_unit"
        result = run(climate_=climate_with(series))
        for item in result:
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                f"the daily series '{name}' is in the unit 'PLACEHOLDER_unit'"
                in item.missing.detail
            )
            assert "Q11" in item.missing.detail
    point = climate_with(
        [daily_series(other, first, last) for other in DAILY_INPUTS], point_units=False
    )
    for item in run(climate_=point):
        assert item.missing.reason == "MISSING_INPUT"
        assert "the latitude of the point" in item.missing.detail
        assert "the elevation of the point" in item.missing.detail
        assert "D55" in item.missing.detail


def test_start_month_missing_returns_one_item_for_the_rotation():
    result = run(calendar_=calendar_without_start_month())
    assert_loads(result)
    (item,) = result
    assert item.time_basis == "rotation"
    assert item.ag_year is None
    assert item.missing.reason == "MISSING_INPUT"
    assert "ag_year_start.month" in item.missing.detail


def test_no_precipitation_series_returns_one_item_for_the_rotation():
    result = run(climate_=climate(quantities=CLIMATE_QUANTITIES))
    assert_loads(result)
    (item,) = result
    assert item.time_basis == "rotation"
    assert item.missing.reason == "MISSING_INPUT"
    assert f"'{PRECIPITATION}'" in item.missing.detail


# --- the cases of #253: the rotation repeated over the record -------------------
#
# The dates below are written by hand, and plainly not those of any rotation:
# every calendar lies thirty years after the record. The start month of the
# example calendar is July (``literal_record`` checks it), so an agricultural
# year runs from 1 July to 30 June.


def literal_record() -> tuple[dt.date, dt.date]:
    """Five agricultural years, 2001 to 2005, written as dates."""
    assert start_month() == 7
    return dt.date(2001, 7, 1), dt.date(2006, 6, 30)


def rotation_calendar(
    start: str, end: str, components: list[tuple[str, str, str, str]]
) -> RotationCalendar:
    """A calendar of the example's field from ``start`` to ``end`` with the
    components given as (name, crop, first day, last day), ISO dates."""
    document = calendar_document()
    template = document["components"][1]
    built = []
    for name, crop, first, last in components:
        component = copy.deepcopy(template)
        component["component_id"] = f"PLACEHOLDER-component-{name}"
        component["crop_id"] = unmarked(crop_word(crop))
        component["start"]["date"] = first
        component["end"]["date"] = last
        component["periods"] = []
        built.append(component)
    document.update(start_date=start, end_date=end, components=built)
    return RotationCalendar.model_validate(document)


# A two-year rotation of three components, none on the field on 1 July. The
# periods of w and x are shorter than the stage lengths of their crops (cut
# at the harvest, D135); y is 21 days longer (a tail, D136).
TWO_YEAR_COMPONENTS = [
    ("w", "crop-a", "2031-08-10", "2031-12-20"),
    ("x", "crop-b", "2032-01-05", "2032-05-25"),
    ("y", "crop-a", "2032-10-01", "2033-04-20"),
]


def two_year_calendar(start: str = "2031-07-01") -> RotationCalendar:
    return rotation_calendar(start, "2033-04-20", TWO_YEAR_COMPONENTS)


# A two-year rotation in which q is on the field on 1 July of its second
# year: sown on 20 May, harvested on 25 November.
CROSSING_COMPONENTS = [
    ("p", "crop-a", "2031-09-01", "2032-02-10"),
    ("q", "crop-b", "2032-05-20", "2032-11-25"),
    ("r", "crop-a", "2033-01-10", "2033-05-31"),
]


def crossing_calendar() -> RotationCalendar:
    return rotation_calendar("2031-07-01", "2033-05-31", CROSSING_COMPONENTS)


# One row of a layout by hand: the first and the last day of a run of days,
# then the crop of those days and the day it was sown, or ``None`` and the
# crop sown after those days (which names the cover of the fallow, D110), or
# ``None`` and NOT_LAID_OUT when that sowing lies after the record: nothing
# is laid out past the record (D109), so the fallow has no following crop
# and its days have no value (OPEN 41 of EXPOSURE.md).
Row = tuple[str, str, str | None, str]
NOT_LAID_OUT = "the next sowing lies after the record"

# The two-year rotation, its first year laid on the first year of the record
# (phase 0; the calendar unchanged). 2001-08-10 is 2031-08-10 thirty years
# earlier, and the cycle starts again every two years. The last living day of
# y is the 181st from its sowing (the four PLACEHOLDER lengths of crop-a);
# the days after it, up to its harvest on 20 April, are its tail.
TWO_YEAR_PHASE_0: dict[int, list[Row]] = {
    2001: [
        ("2001-07-01", "2001-08-09", None, "crop-a"),
        ("2001-08-10", "2001-12-20", "crop-a", "2001-08-10"),
        ("2001-12-21", "2002-01-04", None, "crop-b"),
        ("2002-01-05", "2002-05-25", "crop-b", "2002-01-05"),
        ("2002-05-26", "2002-06-30", None, "crop-a"),
    ],
    2002: [
        ("2002-07-01", "2002-09-30", None, "crop-a"),
        ("2002-10-01", "2003-03-30", "crop-a", "2002-10-01"),
        ("2003-03-31", "2003-06-30", None, "crop-a"),  # the tail, then the fallow
    ],
    2003: [
        ("2003-07-01", "2003-08-09", None, "crop-a"),
        ("2003-08-10", "2003-12-20", "crop-a", "2003-08-10"),
        ("2003-12-21", "2004-01-04", None, "crop-b"),
        ("2004-01-05", "2004-05-25", "crop-b", "2004-01-05"),
        ("2004-05-26", "2004-06-30", None, "crop-a"),
    ],
    2004: [
        ("2004-07-01", "2004-09-30", None, "crop-a"),
        ("2004-10-01", "2005-03-30", "crop-a", "2004-10-01"),
        ("2005-03-31", "2005-06-30", None, "crop-a"),
    ],
    # The third cycle does not fit whole: w and x are laid out, and y, sown
    # on 2006-10-01, lies after the record and is not (D109). So the fallow
    # after x has no following crop.
    2005: [
        ("2005-07-01", "2005-08-09", None, "crop-a"),
        ("2005-08-10", "2005-12-20", "crop-a", "2005-08-10"),
        ("2005-12-21", "2006-01-04", None, "crop-b"),
        ("2006-01-05", "2006-05-25", "crop-b", "2006-01-05"),
        ("2006-05-26", "2006-06-30", None, NOT_LAID_OUT),
    ],
}

# The same rotation with its second year laid on the first year of the
# record (phase 1): y comes first. The y sown on 2003-10-01 crosses 29
# February 2004, so its 181st day is 29 March.
TWO_YEAR_PHASE_1: dict[int, list[Row]] = {
    2001: [
        ("2001-07-01", "2001-09-30", None, "crop-a"),
        ("2001-10-01", "2002-03-30", "crop-a", "2001-10-01"),
        ("2002-03-31", "2002-06-30", None, "crop-a"),
    ],
    2002: [
        ("2002-07-01", "2002-08-09", None, "crop-a"),
        ("2002-08-10", "2002-12-20", "crop-a", "2002-08-10"),
        ("2002-12-21", "2003-01-04", None, "crop-b"),
        ("2003-01-05", "2003-05-25", "crop-b", "2003-01-05"),
        ("2003-05-26", "2003-06-30", None, "crop-a"),
    ],
    2003: [
        ("2003-07-01", "2003-09-30", None, "crop-a"),
        ("2003-10-01", "2004-03-29", "crop-a", "2003-10-01"),
        ("2004-03-30", "2004-06-30", None, "crop-a"),
    ],
    2004: [
        ("2004-07-01", "2004-08-09", None, "crop-a"),
        ("2004-08-10", "2004-12-20", "crop-a", "2004-08-10"),
        ("2004-12-21", "2005-01-04", None, "crop-b"),
        ("2005-01-05", "2005-05-25", "crop-b", "2005-01-05"),
        ("2005-05-26", "2005-06-30", None, "crop-a"),
    ],
    # The w sown on 2006-08-10 lies after the record, so the tail of y and
    # the fallow after it have no following crop.
    2005: [
        ("2005-07-01", "2005-09-30", None, "crop-a"),
        ("2005-10-01", "2006-03-30", "crop-a", "2005-10-01"),
        ("2006-03-31", "2006-06-30", None, NOT_LAID_OUT),
    ],
}

# The crossing rotation, phase 0. In its third cycle q is sown on 2006-05-20
# and harvested after the record: its days up to the last day of the record
# are laid out, and r is not (D109).
CROSSING_PHASE_0: dict[int, list[Row]] = {
    2001: [
        ("2001-07-01", "2001-08-31", None, "crop-a"),
        ("2001-09-01", "2002-02-10", "crop-a", "2001-09-01"),
        ("2002-02-11", "2002-05-19", None, "crop-b"),
        ("2002-05-20", "2002-06-30", "crop-b", "2002-05-20"),
    ],
    2002: [
        ("2002-07-01", "2002-11-25", "crop-b", "2002-05-20"),
        ("2002-11-26", "2003-01-09", None, "crop-a"),
        ("2003-01-10", "2003-05-31", "crop-a", "2003-01-10"),
        ("2003-06-01", "2003-06-30", None, "crop-a"),
    ],
    2003: [
        ("2003-07-01", "2003-08-31", None, "crop-a"),
        ("2003-09-01", "2004-02-10", "crop-a", "2003-09-01"),
        ("2004-02-11", "2004-05-19", None, "crop-b"),
        ("2004-05-20", "2004-06-30", "crop-b", "2004-05-20"),
    ],
    2004: [
        ("2004-07-01", "2004-11-25", "crop-b", "2004-05-20"),
        ("2004-11-26", "2005-01-09", None, "crop-a"),
        ("2005-01-10", "2005-05-31", "crop-a", "2005-01-10"),
        ("2005-06-01", "2005-06-30", None, "crop-a"),
    ],
    2005: [
        ("2005-07-01", "2005-08-31", None, "crop-a"),
        ("2005-09-01", "2006-02-10", "crop-a", "2005-09-01"),
        ("2006-02-11", "2006-05-19", None, "crop-b"),
        ("2006-05-20", "2006-06-30", "crop-b", "2006-05-20"),
    ],
}

# The crossing rotation, phase 1: its second year on the first year of the
# record. q was sown on 20 May, before the first day of the record, and is
# on the field from that first day to its harvest on 25 November (D141).
CROSSING_PHASE_1: dict[int, list[Row]] = {
    2001: [
        ("2001-07-01", "2001-11-25", "crop-b", "2001-05-20"),
        ("2001-11-26", "2002-01-09", None, "crop-a"),
        ("2002-01-10", "2002-05-31", "crop-a", "2002-01-10"),
        ("2002-06-01", "2002-06-30", None, "crop-a"),
    ],
    2002: [
        ("2002-07-01", "2002-08-31", None, "crop-a"),
        ("2002-09-01", "2003-02-10", "crop-a", "2002-09-01"),
        ("2003-02-11", "2003-05-19", None, "crop-b"),
        ("2003-05-20", "2003-06-30", "crop-b", "2003-05-20"),
    ],
    2003: [
        ("2003-07-01", "2003-11-25", "crop-b", "2003-05-20"),
        ("2003-11-26", "2004-01-09", None, "crop-a"),
        ("2004-01-10", "2004-05-31", "crop-a", "2004-01-10"),
        ("2004-06-01", "2004-06-30", None, "crop-a"),
    ],
    2004: [
        ("2004-07-01", "2004-08-31", None, "crop-a"),
        ("2004-09-01", "2005-02-10", "crop-a", "2004-09-01"),
        ("2005-02-11", "2005-05-19", None, "crop-b"),
        ("2005-05-20", "2005-06-30", "crop-b", "2005-05-20"),
    ],
    # The p sown on 2006-09-01 lies after the record.
    2005: [
        ("2005-07-01", "2005-11-25", "crop-b", "2005-05-20"),
        ("2005-11-26", "2006-01-09", None, "crop-a"),
        ("2006-01-10", "2006-05-31", "crop-a", "2006-01-10"),
        ("2006-06-01", "2006-06-30", None, NOT_LAID_OUT),
    ],
}

# The crop of a balance day, by the PLACEHOLDER fraction of its crop.
CROP_OF_FRACTION = {
    value: crop
    for crop, value in PLACEHOLDER_CROP["readily_available_fraction"].items()
}


def spy_balance(monkeypatch) -> dict[dt.date, Any]:
    """Wrap the daily step of the balance; keep the crop each day is given."""
    crops_given: dict[dt.date, Any] = {}
    step = module.balance.step

    def spy(storage, day, **kwargs):
        crops_given[day.date] = day.crop
        return step(storage, day, **kwargs)

    monkeypatch.setattr(module.balance, "step", spy)
    return crops_given


def assert_laid_out_by_hand(
    monkeypatch, calendar_: RotationCalendar, by_hand: dict[int, list[Row]]
) -> list[WaterDeficitExposure]:
    """Every day of ``literal_record`` is given what the layout by hand says.

    A crop day: the balance is given that crop, with the basal coefficient of
    the stage of the day counted from the sowing written by hand
    (``expected_by_stage``). A day with no crop: the balance is given none,
    and the surface layer the total evaporable water reduced by the cover of
    the fallow before the crop written by hand. The rows of a year fill it
    from its first day to its last, and the years are those of the record.

    A row marked NOT_LAID_OUT is a fallow whose next sowing lies after the
    record: the balance is given no crop, the cover of the fallow cannot be
    named, and the day has no value. Every year before it is computed, so it
    is missing for the definition only (D61); the year it falls in is
    ``MISSING_INPUT`` from its first day, saying that the fallow has no
    following crop.
    """
    record = literal_record()
    assert sorted(by_hand) == expected_ag_years(*record)
    with monkeypatch.context() as patch:
        crops_given = spy_balance(patch)
        surface_given = spy_surface_layer(patch)
        days = chain(calendar_, climate(record))
    assert [day.date for day in days] == module._days(*record)
    by_date = {day.date: day for day in days}
    kinds = {"crop": 0, "no crop": 0}
    cut: tuple[int, dt.date] | None = None  # the year and first day with no value
    for ag_year, rows in by_hand.items():
        expected_first = first_day_of(ag_year)
        for first_text, last_text, crop, other in rows:
            first, last = (dt.date.fromisoformat(t) for t in (first_text, last_text))
            assert first == expected_first, (ag_year, first_text)
            assert first <= last
            for day in module._days(first, last):
                given = crops_given[day]
                if other == NOT_LAID_OUT:
                    assert crop is None and given is None, day
                    _, _, constants = surface_given[day]
                    total = constants["total_evaporable_water"]
                    assert isinstance(total, Missing), day
                    assert total.reason == "MISSING_INPUT"
                    assert isinstance(by_date[day].balance.storage_end, Missing)
                    cut = cut or (ag_year, first)
                    continue
                assert cut is None, "a day after the fallow with no following crop"
                assert is_number(by_date[day].balance.storage_end), day
                if crop is None:
                    assert given is None, day
                    _, _, constants = surface_given[day]
                    assert constants["total_evaporable_water"] == pytest.approx(
                        mulched(PLACEHOLDER_RESIDUE_COVER[other])
                    ), day
                    kinds["no crop"] += 1
                    continue
                assert isinstance(given, module.balance.CropDay), day
                assert CROP_OF_FRACTION[given.readily_available_fraction] == crop, day
                day_number = (day - dt.date.fromisoformat(other)).days + 1
                assert given.transpiration_coefficient == pytest.approx(
                    expected_by_stage(crop, day_number, *PLACEHOLDER_STAGE.values())
                ), day
                kinds["crop"] += 1
            expected_first = last + ONE_DAY
        assert expected_first == last_day_of(ag_year) + ONE_DAY, ag_year
    assert all(count > 0 for count in kinds.values()), kinds
    result = run(calendar_=calendar_, climate_=climate(record))
    assert_loads(result)
    assert [item.ag_year for item in result] == sorted(by_hand)
    for item in result:
        assert item.time_basis == "ag_year"
        if cut is None or item.ag_year < cut[0]:
            assert_computed(item)
            continue
        # The year of the fallow with no following crop, and no later year.
        assert item.ag_year == cut[0] == max(by_hand)
        assert item.missing.reason == "MISSING_INPUT"
        assert f"chain MISSING_INPUT: {module.fallow.NO_FOLLOWING_CROP}" in items_of(
            item.missing.detail
        )
        assert f"the first on {cut[1].isoformat()}" in item.missing.detail
        assert "D109" in item.missing.detail and "OPEN 41" in item.missing.detail
    return result


def test_calendar_dates_after_the_record_give_the_crops_of_the_repetition_laid_out_by_hand(
    monkeypatch,
):
    # D47: a calendar whose own dates lie outside the record still runs on
    # the years of the record. Before unit #253 every year was MISSING_INPUT
    # naming Q5. The last year is still missing, for another reason: the
    # fallow at the end of the record has no following crop (D109, OPEN 41).
    calendar_ = two_year_calendar()
    _, record_end = literal_record()
    assert calendar_.start_date > record_end
    result = assert_laid_out_by_hand(monkeypatch, calendar_, TWO_YEAR_PHASE_0)
    for item in result:
        assert "Q5" not in (
            item.source if item.missing is None else item.missing.detail
        )
    # The same years as a calendar laid on the record itself (D47).
    reference = run(climate_=climate(literal_record()))
    assert [item.ag_year for item in result] == [item.ag_year for item in reference]


def test_each_phase_of_a_two_year_rotation_runs_through_phase_calendar_and_lists_every_year(
    monkeypatch,
):
    # D109, D132: one run per phase, each on the calendar the runner moves
    # with phase_calendar. EP3 takes it like any calendar.
    calendar_ = two_year_calendar()
    assert list_phases(calendar_) == [0, 1]
    by_phase = {0: TWO_YEAR_PHASE_0, 1: TWO_YEAR_PHASE_1}
    assert TWO_YEAR_PHASE_0 != TWO_YEAR_PHASE_1
    for phase in list_phases(calendar_):
        moved = phase_calendar(calendar_, phase)
        assert components_crossing_phase(calendar_, phase) == []
        result = assert_laid_out_by_hand(monkeypatch, moved, by_phase[phase])
        assert [item.ag_year for item in result] == expected_ag_years(*literal_record())


def test_component_that_crosses_the_first_day_of_the_record_is_present_from_that_day(
    monkeypatch,
):
    # D141: q starts before the first agricultural year of the record and
    # ends inside it. It keeps its declared dates, is present from the first
    # day of the record and is computed normally.
    calendar_ = crossing_calendar()
    assert list_phases(calendar_) == [0, 1]
    assert components_crossing_phase(calendar_, 1) == ["PLACEHOLDER-component-q"]
    moved = phase_calendar(calendar_, 1)
    assert all(
        c.start.date is not None and c.end.date is not None for c in moved.components
    )
    first_row, *_ = CROSSING_PHASE_1[2001]
    record_start, _ = literal_record()
    # The crop of the first day was sown before the record.
    assert first_row[0] == record_start.isoformat()
    assert dt.date.fromisoformat(first_row[3]) < record_start
    assert_laid_out_by_hand(monkeypatch, moved, CROSSING_PHASE_1)
    # The stage of the first day is counted from the declared sowing: it is
    # the 43rd day of q, inside its development stage.
    crops_given = spy_balance(monkeypatch)
    chain(moved, climate(literal_record()))
    lengths = placeholder_stage_lengths("crop-b")
    assert lengths["initial"] < 43 <= lengths["initial"] + lengths["development"]
    assert crops_given[record_start].transpiration_coefficient == pytest.approx(
        PLACEHOLDER_STAGE["initial"]
        + (43 - lengths["initial"])
        / lengths["development"]
        * (PLACEHOLDER_STAGE["mid"] - PLACEHOLDER_STAGE["initial"])
    )


def test_cycle_that_does_not_fit_whole_is_cut_at_the_end_of_the_record(monkeypatch):
    # D109. Phase 0 of the crossing rotation: the third cycle starts in the
    # last year of the record. p is whole; q is sown inside the record and
    # harvested after it, so its days up to the last day of the record are
    # laid out with its stages; r is sown after the record and is not.
    calendar_ = crossing_calendar()
    record = literal_record()
    result = assert_laid_out_by_hand(monkeypatch, calendar_, CROSSING_PHASE_0)
    *_, last_row = CROSSING_PHASE_0[2005]
    assert last_row == ("2006-05-20", "2006-06-30", "crop-b", "2006-05-20")
    # The record ends on a crop day, so every year is computed. Where it ends
    # in a fallow, the sowing after it is not laid out either, and the fallow
    # has no following crop: the last rows of the other layouts by hand.
    for item in result:
        assert_computed(item)
    for cut_layout in (TWO_YEAR_PHASE_0, TWO_YEAR_PHASE_1, CROSSING_PHASE_1):
        *_, cut_row = cut_layout[2005]
        assert cut_row[2:] == (None, NOT_LAID_OUT)
    # No day after the record is computed, and no year after it is listed.
    days = chain(calendar_, climate(record))
    assert days[-1].date == record[1]
    assert result[-1].ag_year == 2005


def test_calendar_that_starts_at_its_first_sowing_runs_on_a_record_that_starts_inside_a_year():
    # The calendar as EP2 lays it out starts on its first sowing (10 August),
    # and the record of D29 starts on 1 January, inside an agricultural year.
    # The first cycle starts in the first agricultural year of the record
    # (2000-08-10), before the first day of the record, so every day is
    # described; the years the record covers whole are computed, and the two
    # it covers in part are NO_COVERAGE (C5.5).
    calendar_ = two_year_calendar(start="2031-08-10")
    record = (dt.date(2001, 1, 1), dt.date(2005, 12, 31))
    result = run(calendar_=calendar_, climate_=climate(record))
    assert_loads(result)
    assert [item.ag_year for item in result] == [2000, 2001, 2002, 2003, 2004, 2005]
    first, *whole, last = result
    for item in (first, last):
        assert item.missing.reason == "NO_COVERAGE"
    for item in whole:
        assert_computed(item)


def test_days_before_the_first_cycle_are_not_described_and_leave_the_years_missing():
    # The case keeps the name EXPOSURE.md lists; since D188 (2) it asserts
    # the opposite of what the name says (a follow-up of brief #372).
    # The same calendar on a record that starts on the first day of an
    # agricultural year: the first cycle starts on 2001-08-10 and no
    # component of the cycle before it reaches the record. D188 (2): that
    # cycle is laid out all the same (points 6 and 13 of
    # engine/calendar/repeat.py), so the forty days before the first cycle
    # are days with no crop and the balance runs from the first day. Every
    # year is computed but the last, whose fallow after the last harvest has
    # no crop that follows it inside the record (OPEN 41, not D188).
    calendar_ = two_year_calendar(start="2031-08-10")
    record = literal_record()
    days = chain(calendar_, climate(record))
    before = [day for day in days if day.date < dt.date(2001, 8, 10)]
    assert len(before) == 40 and before[0].date == record[0]
    for day in before:
        assert is_number(day.balance.storage_end)
        assert day.balance.transpiration_demanded.reason == module.NO_CROP_ON_THE_DAY
    result = run(calendar_=calendar_, climate_=climate(record))
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*record)
    *computed, last = result
    for item in computed:
        assert_computed(item)
    assert f"chain MISSING_INPUT: {module.fallow.NO_FOLLOWING_CROP}" in items_of(
        last.missing.detail
    )
    for item in result:
        assert module.CROP_UNKNOWN not in (item.missing.detail if item.missing else "")
    assert "D47" in module.CROP_UNKNOWN and "OPEN 5" in module.CROP_UNKNOWN


def test_crossing_component_that_phase_calendar_cannot_place_leaves_its_days_missing_naming_d141():
    # A component of the first year that runs past the last day of the second
    # cannot lie whole in one cycle of the moved calendar, so phase_calendar
    # gives it missing dates with their reason (OPEN of
    # engine/calendar/repeat.py). EP3 guesses nothing: the days it could
    # cover have no known crop, naming the component and that reason.
    calendar_ = rotation_calendar(
        "2031-07-01",
        "2033-08-15",
        [
            ("p", "crop-a", "2031-09-01", "2032-02-10"),
            ("long", "crop-b", "2032-03-01", "2033-08-15"),
        ],
    )
    assert list_phases(calendar_) == [0, 1, 2]
    assert components_crossing_phase(calendar_, 1) == ["PLACEHOLDER-component-long"]
    moved = phase_calendar(calendar_, 1)
    (long,) = [c for c in moved.components if c.component_id.endswith("long")]
    assert long.start.date is None and long.end.date is None
    record = literal_record()
    result = run(calendar_=moved, climate_=climate(record))
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*record)
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        assert item.value is None
    # The reason of the calendar holds "; ", so the whole detail is read, not
    # its items.
    named = [
        item.missing.detail
        for item in result
        if f"chain MISSING_INPUT: {module.CROP_DATES_MISSING}" in item.missing.detail
    ]
    assert named
    for detail in named:
        assert "component 'PLACEHOLDER-component-long' (start and end date" in detail
        assert "NOT_COMPUTABLE" in detail
        assert "D141" in detail


def every_kind_of_result() -> list[list[WaterDeficitExposure]]:
    """One result of each situation of the cases above."""
    first, last = several_full_years()
    mixed = [daily_series(name, first, last) for name in DAILY_INPUTS]
    mixed[-1]["time_zone"] = "PLACEHOLDER_other_time_zone"
    return [
        run(
            calendar_=calendar(),
            climate_=SiteClimate.model_validate(climate_document()),
            parameters={},
        ),
        run(),
        run(parameters={}),
        run(climate_=climate(held_missing=(first + ONE_DAY,))),
        run(climate_=climate((first + ONE_DAY, last - ONE_DAY))),
        run(climate_=climate(quantities=DAILY_INPUTS[:-1])),
        run(calendar_=infeasible_calendar()),
        run(climate_=climate_with(mixed)),
        run(
            climate_=climate_with(
                [daily_series(name, first, last) for name in DAILY_INPUTS],
                point_units=False,
            )
        ),
        run(calendar_=calendar_without_start_month()),
        run(climate_=climate(quantities=CLIMATE_QUANTITIES)),
        run(calendar_=calendar()),
        # Years with a number (D157), from the calendar with crops.
        run(calendar_=chain_calendar()),
        run(
            calendar_=chain_calendar(),
            climate_=climate_with_dry_spells(),
            parameters=dry_catalogue(),
        ),
    ]


def test_the_list_is_never_empty_and_every_item_is_a_labelled_number_or_missing_with_its_reason():
    numbers = 0
    for result in every_kind_of_result():
        assert isinstance(result, list)
        assert len(result) >= 1
        assert_loads(result)
        for item in result:
            if item.value is None:
                # Missing with a reason of C3.2, and nothing of a value.
                assert item.missing is not None
                assert item.missing.reason in REASON_CODES
                assert item.provenance is None and item.source is None
                assert item.assumption is False
                assert item.range is None and item.range_missing is None
            else:
                # A number of D157: never a zero written for a missing value.
                assert_is_a_value(item)
                numbers += 1
        assert len({item.time_basis for item in result}) == 1
        ag_years = [item.ag_year for item in result]
        assert len(set(ag_years)) == len(ag_years)
    assert numbers > 0


# --- the cases of #264: the ratio of D157 ---------------------------------------


def dry_catalogue() -> dict[str, dict]:
    """The test catalogue with no residue cover on any fallow.

    With the long dry spells of ``climate_with_dry_spells`` the surface layer
    of a crop day dries to its total evaporable water. A fallow with a cover
    has a smaller total, and a depletion above it is not computed (OPEN 30),
    which would leave the years missing. A cover of zero, structurally,
    leaves the total unchanged, so every day is computed.
    """
    no_cover = 0.0
    return catalogue_with(
        {
            (module.SURFACE_RESIDUE_COVER, f"fallow:{crop}"): fallow_record(
                crop, no_cover
            )
            for crop in CROPS
        }
    )


def spy_balance_days(monkeypatch) -> dict[dt.date, tuple[Any, Any]]:
    """Wrap the daily step of the balance; keep the day it is given and the
    day it gives back, so that a case recomputes from the run it checks."""
    seen: dict[dt.date, tuple[Any, Any]] = {}
    step = module.balance.step

    def spy(storage, day, **kwargs):
        result = step(storage, day, **kwargs)
        seen[day.date] = (day, result)
        return result

    monkeypatch.setattr(module.balance, "step", spy)
    return seen


def ratio_by_hand(
    seen: dict[dt.date, tuple[Any, Any]], first: dt.date, last: dt.date
) -> tuple[float | None, list[dt.date]]:
    """The ratio of D157 from ``first`` to ``last``, written out here, and its
    days with a living crop.

    A day with a living crop is a day on which the balance was given a crop.
    Water transpired is the transpiration the balance gave back; water
    demanded is the basal crop coefficient it was given times the reference
    evapotranspiration it was given. Each is summed over those days.
    """
    living = [
        day
        for day in module._days(first, last)
        if isinstance(seen[day][0].crop, module.balance.CropDay)
    ]
    if not living:
        return None, living
    transpired = math.fsum(seen[day][1].transpiration for day in living)
    demanded = math.fsum(
        seen[day][0].crop.transpiration_coefficient
        * seen[day][0].reference_evapotranspiration
        for day in living
    )
    return transpired / demanded, living


def days_in_source(item: WaterDeficitExposure) -> tuple[int, dt.date, dt.date]:
    """The count of days with a living crop, the first and the last, as the
    source of a value states them."""
    found = re.search(
        r"summed over the (\d+) day\(s\) with a living crop of agricultural year "
        r"(\d+), the first on (\d{4}-\d{2}-\d{2}) and the last on (\d{4}-\d{2}-\d{2})",
        item.source,
    )
    assert found, item.source
    assert int(found.group(2)) == item.ag_year
    return (
        int(found.group(1)),
        dt.date.fromisoformat(found.group(3)),
        dt.date.fromisoformat(found.group(4)),
    )


def test_year_computed_on_every_day_gives_the_ratio_recomputed_by_hand_from_the_daily_balance(
    monkeypatch,
):
    # Long dry spells, so that the root zone dries and the balance transpires
    # less than is demanded on some days: a ratio below one.
    seen = spy_balance_days(monkeypatch)
    calendar_ = chain_calendar()
    result = run(
        calendar_=calendar_,
        climate_=climate_with_dry_spells(),
        parameters=dry_catalogue(),
    )
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*several_full_years())
    values = []
    for item in result:
        first, last = first_day_of(item.ag_year), last_day_of(item.ag_year)
        expected, living = ratio_by_hand(seen, first, last)
        assert living, "every year of the calendar with crops has crop days"
        assert_is_a_value(item)
        assert item.value == pytest.approx(expected, rel=1e-12)
        assert days_in_source(item) == (len(living), living[0], living[-1])
        # The days with a living crop are those the calendar gives a crop,
        # and the demanded transpiration of the balance is the product.
        for day in living:
            assert crop_period_of(calendar_, day) is not None
            given, back = seen[day]
            assert back.transpiration_demanded == pytest.approx(
                given.crop.transpiration_coefficient
                * given.reference_evapotranspiration
            )
            assert 0 <= back.transpiration <= back.transpiration_demanded
        values.append(item.value)
    # Some year is short of water, and the years are not all alike.
    assert min(values) < 1
    assert len(set(values)) > 1
    # A second run gives the same numbers (G1).
    again = run(
        calendar_=calendar_,
        climate_=climate_with_dry_spells(),
        parameters=dry_catalogue(),
    )
    assert [item.value for item in again] == values


def test_cycle_that_crosses_the_start_of_the_agricultural_year_gives_its_days_to_each_year(
    monkeypatch,
):
    # D157, D47. In phase 0 of the crossing rotation, q is sown on 20 May
    # and harvested on 25 November: its days up to 30 June count in the year
    # they fall in, and its days from 1 July in the next one.
    seen = spy_balance_days(monkeypatch)
    record = literal_record()
    result = run(
        calendar_=crossing_calendar(),
        climate_=climate_with_dry_spells(record),
        parameters=dry_catalogue(),
    )
    assert_loads(result)
    by_year = {item.ag_year: item for item in result}
    assert sorted(by_year) == sorted(CROSSING_PHASE_0)
    for ag_year, rows in CROSSING_PHASE_0.items():
        # The days with a crop, from the layout by hand of that year.
        by_hand = [
            day
            for first, last, crop, _ in rows
            if crop is not None
            for day in module._days(
                dt.date.fromisoformat(first), dt.date.fromisoformat(last)
            )
        ]
        expected, living = ratio_by_hand(
            seen, first_day_of(ag_year), last_day_of(ag_year)
        )
        assert living == by_hand
        item = by_year[ag_year]
        assert_is_a_value(item)
        assert item.value == pytest.approx(expected, rel=1e-12)
        assert days_in_source(item) == (len(by_hand), by_hand[0], by_hand[-1])
    # The cycle of q that crosses 1 July 2002: 42 days in the year 2001 and
    # 148 in the year 2002, each with the other crop days of its year.
    _, _, last_of_2001 = days_in_source(by_year[2001])
    _, first_of_2002, _ = days_in_source(by_year[2002])
    assert last_of_2001 == dt.date(2002, 6, 30)
    assert first_of_2002 == dt.date(2002, 7, 1)
    whole_cycle, _ = ratio_by_hand(seen, dt.date(2002, 5, 20), dt.date(2002, 11, 25))
    assert by_year[2001].value != pytest.approx(whole_cycle, rel=1e-9)
    assert by_year[2002].value != pytest.approx(whole_cycle, rel=1e-9)


def test_year_with_no_living_crop_is_not_applicable(monkeypatch):
    # The calendar with one component, sown on the last day of the record:
    # the first two years have no crop day; the last has one, its sowing day.
    seen = spy_balance_days(monkeypatch)
    result = run()
    assert_loads(result)
    *fallow_years, last_year = result
    assert len(fallow_years) == 2
    for item in fallow_years:
        assert item.value is None
        assert item.value != 0
        assert item.missing.reason == "NOT_APPLICABLE"
        assert_computed(item)
        assert "D106" in item.missing.detail and "D136" in item.missing.detail
    assert_is_a_value(last_year)
    assert days_in_source(last_year) == (1, *([several_full_years()[1]] * 2))
    expected, _ = ratio_by_hand(
        seen, first_day_of(last_year.ag_year), last_day_of(last_year.ag_year)
    )
    assert last_year.value == pytest.approx(expected, rel=1e-12)


def test_tail_days_after_maturity_do_not_enter_the_ratio(monkeypatch):
    # D136. One component of crop-a from the first day of the record to the
    # day before its last, far longer than the stage lengths of the crop: its
    # living days lie in the first year, the whole second year is its tail,
    # and the third year holds its tail and the sowing day of the component
    # sown on the last day of the record.
    first, last = several_full_years()
    document = chain_calendar_document()
    *_, closing = document["components"]
    long = copy.deepcopy(closing)
    long["component_id"] = "PLACEHOLDER-component-long"
    long["start"]["date"] = first.isoformat()
    long["end"]["date"] = (last - ONE_DAY).isoformat()
    document["components"] = [long, closing]
    calendar_ = RotationCalendar.model_validate(document)
    seen = spy_balance_days(monkeypatch)
    result = run(calendar_=calendar_)
    assert_loads(result)
    first_year, second_year, third_year = result
    living_days = period_days("crop-a")  # the four stage lengths of crop-a
    assert_is_a_value(first_year)
    assert days_in_source(first_year) == (
        living_days,
        first,
        first + ONE_DAY * (living_days - 1),
    )
    # Every day of the second year is a tail day: the balance was given no
    # crop on any of them, so the year has no living crop.
    for day in module._days(
        first_day_of(second_year.ag_year), last_day_of(second_year.ag_year)
    ):
        assert seen[day][0].crop is None
    assert second_year.value is None
    assert second_year.missing.reason == "NOT_APPLICABLE"
    assert_computed(second_year)
    # The third year: its tail days are left out, its one sowing day counts.
    assert_is_a_value(third_year)
    assert days_in_source(third_year) == (1, last, last)


def test_year_with_one_day_the_chain_could_not_compute_is_missing_with_the_reason_of_that_day():
    first, _ = several_full_years()
    held = first_day_of(first.year + 1) + ONE_DAY * 99
    calendar_ = chain_calendar()
    result = run(calendar_=calendar_, climate_=climate(held_missing=(held,)))
    assert_loads(result)
    before, year, after = result
    # The year before is computed: a number.
    assert_is_a_value(before)
    # The year of the day: not a number, and not NOT_APPLICABLE; the reason
    # of the first day without a value, which is that day.
    assert year.value is None
    assert year.value != 0
    assert year.missing.reason == "MISSING_INPUT"
    assert f"the first on {held.isoformat()}" in year.missing.detail
    assert "no gap is filled" in year.missing.detail
    assert year.provenance is None and year.source is None
    assert year.range is None and year.range_missing is None
    # The 99 days before it were computed, and give no number for the year.
    days = chain(calendar_, climate(held_missing=(held,)))
    computed = [
        day
        for day in days
        if first_day_of(year.ag_year) <= day.date < held
        and is_number(day.balance.storage_end)
    ]
    assert len(computed) == 99
    # The balance does not restart, so the year after is missing too.
    assert after.value is None
    assert after.missing.reason == "MISSING_INPUT"


def test_year_whose_demanded_sum_is_zero_is_not_computable(monkeypatch):
    # A basal crop coefficient of zero in every stage of both crops (and a
    # minimum crop coefficient of zero, so that the cover fraction exists):
    # the balance is computed on every day, the crops demand nothing, and the
    # ratio has no denominator. Zero here is structural, not a value.
    zero = 0.0
    changes: dict[tuple[str, str | None], dict | None] = {
        ("minimum_crop_coefficient", None): site_record(
            "minimum_crop_coefficient", zero
        )
    }
    for crop in CROPS:
        for stage in module.STAGES:
            label = f"{crop}:{stage}"
            changes[("basal_crop_coefficient", label)] = unmarked(
                placeholder_record("basal_crop_coefficient", zero, scope_of(label))
            )
    seen = spy_balance_days(monkeypatch)
    calendar_ = chain_calendar()
    result = run(calendar_=calendar_, parameters=catalogue_with(changes))
    assert_loads(result)
    crop_days = 0
    for day, (given, back) in seen.items():
        assert is_number(back.storage_end), day
        if isinstance(given.crop, module.balance.CropDay):
            assert back.transpiration_demanded == 0
            assert back.transpiration == 0
            crop_days += 1
    assert crop_days > 0
    for item in result:
        assert item.value is None
        assert item.value != 0
        assert item.missing.reason == "NOT_COMPUTABLE"  # D214
        assert "is not above zero" in item.missing.detail
        assert "D157" in item.missing.detail and "D214" in item.missing.detail
        assert "OPEN 43" not in item.missing.detail
        assert item.provenance is None and item.source is None


def test_label_of_d105_is_on_every_value_and_on_no_missing_item():
    numbers = 0
    for result in every_kind_of_result():
        for item in result:
            if item.value is None:
                assert item.source is None
                continue
            # D162: the label, verbatim, at the start of the source text.
            assert item.source.startswith("whole cycle, not critical period")
            assert item.source.count(WINDOW_LABEL) == 1
            numbers += 1
    assert numbers > 0
    assert module.WINDOW_LABEL == "whole cycle, not critical period"


def test_source_ends_with_the_method_facts_of_d215():
    # D215, option S-b: after the label of D162 and the wording built by #264,
    # one clause of method facts, each a fact the code guarantees (choice 23
    # b of EXPOSURE.md names where). D137 is named without saying which table
    # the catalogue holds.
    facts = module.METHOD_FACTS
    assert facts.startswith("method facts of this engine: ")
    for name in ("D111", "D135", "D137", "D189", "FAO-56 Eq. 70 is not applied"):
        assert name in facts, name
    for words in ("weed-free", "never stretched", "not adjusted for climate"):
        assert words in facts, words
    assert "initial_storage" in facts and "initial_depletion" in facts
    assert "Table" not in facts
    numbers = 0
    for result in every_kind_of_result():
        for item in result:
            if item.value is None:
                assert item.source is None
                continue
            assert item.source.endswith(f"; {facts}")
            assert item.source.count(facts) == 1
            assert item.source.index("engine/water/EXPOSURE.md") < item.source.index(
                facts
            )
            numbers += 1
    assert numbers > 0
    # The last fact, on the chain itself: its first day starts from the two
    # declared site states (the records of the test catalogue).
    first, *_ = chain()
    assert first.surface_layer.depletion_start == PLACEHOLDER_SITE["initial_depletion"]
    assert first.balance.storage_start == PLACEHOLDER_SITE["initial_storage"]


def test_exposure_md_names_the_decisions_and_reads_open_30_and_open_41_as_decided():
    # Acceptance check 7 of #292, with the decisions of #333.
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    for number in (*range(185, 192), *range(214, 218)):
        assert re.search(rf"\bD{number}\b", text), number
    open_items = text.split("\n## OPEN", 1)[1]

    def item(number: int) -> str:
        (line,) = [
            line for line in open_items.splitlines() if line.startswith(f"{number}. **")
        ]
        return line

    assert "Closed by [D185]" in item(30)
    assert "Decided by [D187]" in item(41) and "not decided" not in item(41)
    assert "Closed by [D214]" in item(43)
    assert "Closed by [D215 to D217]" in item(44)
    assert "First part closed by [D186]" in item(32)
    assert "CITATION NEEDED" not in item(32)


# --- the caller (G3, G5) and purity (G1) --------------------------------------


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_arguments_of_another_case_or_field_raise_value_error(argument, field):
    loader = {"climate": climate_document, "soil_slope": soil_document}[argument]
    model = {"climate": SiteClimate, "soil_slope": SiteSoilSlope}[argument]
    document = loader()
    document[field] = f"{document[field]}-other"
    arguments = {
        "calendar": chain_calendar(),
        "climate": climate(),
        "soil_slope": soil(),
        "parameters": catalogue(),
    }
    arguments[argument] = model.model_validate(document)
    with pytest.raises(ValueError, match=field):
        module.compute_water_deficit_exposure(**arguments)


@pytest.mark.parametrize("argument", ["calendar", "climate", "soil_slope"])
def test_argument_that_is_not_its_model_raises_type_error(argument):
    arguments = {
        "calendar": chain_calendar(),
        "climate": climate(),
        "soil_slope": soil(),
        "parameters": catalogue(),
    }
    other_model = soil() if argument != "soil_slope" else chain_calendar()
    for wrong in (arguments[argument].model_dump(mode="json"), other_model):
        given = dict(arguments)
        given[argument] = wrong
        with pytest.raises(TypeError, match=argument):
            module.compute_water_deficit_exposure(**given)


def test_parameters_missing_positional_or_not_a_dict_raises_type_error():
    arguments = {
        "calendar": chain_calendar(),
        "climate": climate(),
        "soil_slope": soil(),
    }
    with pytest.raises(TypeError, match="parameters"):
        module.compute_water_deficit_exposure(**arguments)
    with pytest.raises(TypeError):
        module.compute_water_deficit_exposure(*arguments.values(), catalogue())
    records = list(catalogue().values())
    for wrong in (
        records,
        tuple(records),
        json.dumps(catalogue()),
        None,
        {position: record for position, record in enumerate(records)},
        {"records.json": records},
        {"record.json": "PLACEHOLDER"},
    ):
        with pytest.raises(TypeError, match="parameters"):
            module.compute_water_deficit_exposure(**arguments, parameters=wrong)


def test_arguments_unchanged_and_second_call_equal():
    for parameters in (catalogue(), {}):
        arguments = {
            "calendar": chain_calendar(),
            "climate": climate(held_missing=(several_full_years()[1],)),
            "soil_slope": soil(),
            "parameters": parameters,
        }
        before = copy.deepcopy(arguments)
        first = module.compute_water_deficit_exposure(**arguments)
        assert arguments == before
        assert module.compute_water_deficit_exposure(**arguments) == first


# --- the module ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("file_name", "allowed", "allowed_numbers"),
    [
        (
            "exposure.py",
            lambda name: (
                name.startswith("contracts.inputs.")
                or name == "contracts.results.models"
                or name
                in (
                    # The repetition of the rotation over the record (unit
                    # #253): the one place its rule lives.
                    "engine.calendar.repeat",
                    "engine.water",
                    "engine.water._parameters",
                    "engine.water.et0",
                    "engine.water.et0.quantities",
                    "engine.water.runoff",
                    "engine.water.stages",
                )
            ),
            # One, and the zero the demanded sum of a year is compared with
            # (unit #264).
            {0, 1},
        ),
        ("stages.py", lambda name: name == "contracts.results.models", {1}),
        (
            "_parameters.py",
            lambda name: name in ("contracts.results.models", "params.catalogue"),
            {1},
        ),
        # The bounds of a fraction and the whole of the total evaporable water.
        ("fallow.py", lambda name: name == "contracts.results.models", {0, 1}),
    ],
)
def test_modules_import_only_allowed_modules_and_hold_only_the_integer_one(
    file_name, allowed, allowed_numbers
):
    source = (HERE / file_name).read_text("utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            names = [node.module]
            if node.module == "params.catalogue":
                assert {alias.name for alias in node.names} <= {
                    "Missing",
                    "identity",
                    "read_value",
                    "read_range",
                }
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            assert top in sys.stdlib_module_names or allowed(name), name
            assert top not in ("os", "io", "pathlib", "socket", "time", "random")
    assert "load_folder" not in source.replace("``params.catalogue.load_folder``", "")
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= allowed_numbers
    format_specs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None
    ]
    assert format_specs == [], "a format specification can hide a number"


def test_package_exposes_the_entry_point_with_parameters_by_keyword_and_no_default():
    from engine.water import compute_water_deficit_exposure

    assert compute_water_deficit_exposure is module.compute_water_deficit_exposure
    parameters = inspect.signature(compute_water_deficit_exposure).parameters
    assert list(parameters) == ["calendar", "climate", "soil_slope", "parameters"]
    assert all(p.default is inspect.Parameter.empty for p in parameters.values())
    assert parameters["parameters"].kind is inspect.Parameter.KEYWORD_ONLY


def test_parameter_identifiers_are_well_formed_and_unique():
    names = [
        *module.SITE_PARAMETERS,
        *module.STAGE_PARAMETERS,
        *module.DAY_PARAMETERS,
        *module.CROP_PARAMETERS,
        *module.FALLOW_SITE_PARAMETERS,
        *module.FALLOW_COVER_PARAMETERS,
    ]
    assert len(names) == len(set(names))
    # The two records of a fallow day are read with the scope of a day with
    # no crop; the wetted fraction keeps its identifier, read with the empty
    # scope on a day with a crop (D110).
    fallow = list(module.FALLOW_PARAMETERS)
    assert len(fallow) == len(set(fallow))
    assert set(fallow) & set(names) == {"wetted_fraction"}
    for name in [*names, *fallow]:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name), name
    readme = (HERE / "et0" / "README.md").read_text("utf-8")
    for group, fields_ in module.ET0_PARAMETERS.items():
        for field in fields_:
            assert f"| `{group}.{field}` |" in readme
    for part, ids in (
        ("runoff", module.RUNOFF_PARAMETERS),
        (
            "evaporation",
            [n for n in module.SURFACE_LAYER_PARAMETERS if n != "initial_depletion"],
        ),
    ):
        text = (HERE / part / "README.md").read_text("utf-8")
        for name in ids:
            assert f"| `{name}` |" in text, name
    evaporation_readme = (HERE / "evaporation" / "README.md").read_text("utf-8")
    for field in module.UPPER_LIMIT_FIELDS:
        assert f"| `upper_limit.{field}` |" in evaporation_readme


def test_parameter_table_matches_exposure_md():
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    section = text.split("## Parameters", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(
        r"^\| `([A-Za-z0-9_]+)` \| ([^|]+) \|", section, flags=re.MULTILINE
    )
    by_scope: dict[str, list[str]] = {}
    for name, scope in rows:
        by_scope.setdefault(scope.strip(), []).append(name)
    assert sorted(by_scope) == [
        "crop",
        "crop and stage, or no crop",
        "crop or no crop",
        "no crop",
        "no crop, by the crop that follows",
        "site",
        "site, on a day with no crop",
    ]
    assert sorted(by_scope["site"]) == sorted(module.SITE_PARAMETERS)
    assert sorted(by_scope["site, on a day with no crop"]) == sorted(
        module.FALLOW_SITE_PARAMETERS
    )
    assert sorted(by_scope["no crop"]) == sorted(module.FALLOW_PARAMETERS)
    assert sorted(by_scope["no crop, by the crop that follows"]) == sorted(
        module.FALLOW_COVER_PARAMETERS
    )
    assert sorted(by_scope["crop and stage, or no crop"]) == sorted(
        module.STAGE_PARAMETERS
    )
    assert sorted(by_scope["crop or no crop"]) == sorted(module.DAY_PARAMETERS)
    assert sorted(by_scope["crop"]) == sorted(module.CROP_PARAMETERS)


def test_runner_discovers_the_entry_point():
    from api.engines import discover_engine_functions

    found = discover_engine_functions()
    assert found.compute_water_deficit_exposure is module.compute_water_deficit_exposure


def test_route_answers_with_a_water_part_when_the_runner_passes_parameters():
    """In process, with the examples, no network.

    The runner of ``api/engines.py`` passes ``parameters`` to EP3 by keyword
    (D46, D56, #160); here it is given the empty catalogue, the catalogue of
    ``params/records/`` today, and EP3 is passed to it unwrapped. EP2 is
    replaced by the example calendar, which carries a start month, and EP1 is
    left out (not built), so that this case checks the water part alone. The
    next case runs every discovered engine.
    """
    from fastapi.testclient import TestClient

    from adapters.example_soil_slope import ExampleSoilSlopeSource
    from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
    from api.engines import DEFAULT_CARBON_MODELS, EngineFunctions, EntryPointEngines
    from api.main import create_app
    from api.ports import RunSettings

    example_climate = SiteClimate.model_validate(climate_document())
    series = example_precipitation()

    class ExampleClimate:
        source_id = "PLACEHOLDER_CLIMATE"
        contract = "site_data_climate"

        def get_climate(self, request: ClimateRequest) -> ClimateResult:
            return ClimateResult(
                data=example_climate,
                source=SourceInfo(
                    id=self.source_id, contract=self.contract, state="example"
                ),
            )

    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=lambda rotation: calendar(),
            compute_soil_loss=None,
            compute_water_deficit_exposure=module.compute_water_deficit_exposure,
        ),
        carbon_models=DEFAULT_CARBON_MODELS,
        parameters={},
    )
    rotation = json.loads(
        (
            ROOT
            / "contracts"
            / "rotation_definition"
            / "examples"
            / "PLACEHOLDER_rotation_definition.json"
        ).read_text("utf-8")
    )
    example_calendar = calendar_document()
    body = {
        "site": {
            "case_id": example_calendar["case_id"],
            "field_id": example_calendar["field_id"],
            "latitude": example_climate.point.latitude.value,
            "longitude": example_climate.point.longitude.value,
        },
        "rotation": rotation,
    }
    app = create_app(
        [],
        climate=ExampleClimate(),
        soil_slope=ExampleSoilSlopeSource(
            EXAMPLES / "PLACEHOLDER_site_soil_slope.json"
        ),
        engines=engines,
        settings=RunSettings(
            start_date=dt.date.fromisoformat(series["start_date"]),
            end_date=dt.date.fromisoformat(series["end_date"]),
        ),
    )
    response = TestClient(app).post("/api/rotations/run", json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    result = ResultsPerRotation.model_validate(answer["result"])
    water_part = result.water_deficit_exposure
    assert isinstance(water_part, list)
    assert water_part == module.compute_water_deficit_exposure(
        calendar=calendar(), climate=example_climate, soil_slope=soil(), parameters={}
    )
    (water_module,) = [m for m in answer["modules"] if m["id"] == "water"]
    assert water_module["state"] == "not_available"
    assert water_module["reason"] == water_part[0].missing.reason


def test_route_through_the_real_runner_passes_parameters_and_the_water_part_loads():
    """In process, with the examples, no network, nothing wrapped or replaced.

    Every engine is the one ``discover_engine_functions`` finds (EP2, EP1 and
    this EP3), run by ``EntryPointEngines`` with the test catalogue as
    ``parameters``, exactly as the app passes the loaded catalogue (#160).
    The climate source serves the example climate under the identifiers of
    the request, so that the runner calls EP1 and EP3.
    """
    from fastapi.testclient import TestClient

    from adapters.example_soil_slope import ExampleSoilSlopeSource
    from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
    from api.engines import (
        DEFAULT_CARBON_MODELS,
        EntryPointEngines,
        discover_engine_functions,
    )
    from api.main import create_app
    from api.ports import RunSettings
    from api.rotation_validator import load_rotation_definition

    served: list[SiteClimate] = []

    class ExampleClimate:
        source_id = "PLACEHOLDER_CLIMATE"
        contract = "site_data_climate"

        def get_climate(self, request: ClimateRequest) -> ClimateResult:
            document = climate_document()
            document["case_id"] = request.case_id
            document["field_id"] = request.field_id
            served.append(SiteClimate.model_validate(document))
            return ClimateResult(
                data=served[-1],
                source=SourceInfo(
                    id=self.source_id, contract=self.contract, state="example"
                ),
            )

    found = discover_engine_functions()
    assert found.compute_water_deficit_exposure is module.compute_water_deficit_exposure
    parameters = catalogue()
    engines = EntryPointEngines(
        found, carbon_models=DEFAULT_CARBON_MODELS, parameters=parameters
    )
    rotation = json.loads(
        (
            ROOT
            / "contracts"
            / "rotation_definition"
            / "examples"
            / "PLACEHOLDER_rotation_definition.json"
        ).read_text("utf-8")
    )
    series = example_precipitation()
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": 1.0,
            "longitude": 2.0,
        },
        "rotation": rotation,
    }
    app = create_app(
        [],
        climate=ExampleClimate(),
        soil_slope=ExampleSoilSlopeSource(
            EXAMPLES / "PLACEHOLDER_site_soil_slope.json"
        ),
        engines=engines,
        settings=RunSettings(
            start_date=dt.date.fromisoformat(series["start_date"]),
            end_date=dt.date.fromisoformat(series["end_date"]),
        ),
    )
    response = TestClient(app).post("/api/rotations/run", json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    result = ResultsPerRotation.model_validate(answer["result"])
    water_part = result.water_deficit_exposure
    assert isinstance(water_part, list)
    assert_loads(water_part)
    (climate_served,) = served
    the_calendar = found.build_rotation_calendar(load_rotation_definition(rotation))
    assert water_part == module.compute_water_deficit_exposure(
        calendar=the_calendar,
        climate=climate_served,
        soil_slope=soil().model_copy(
            update={"case_id": rotation["case_id"], "field_id": rotation["field_id"]}
        ),
        parameters=parameters,
    )
    (water_module,) = [m for m in answer["modules"] if m["id"] == "water"]
    assert water_module["state"] == "not_available"
    assert water_module["reason"] == water_part[0].missing.reason


def test_proposed_cases_match_exposure_md():
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    section = text.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
