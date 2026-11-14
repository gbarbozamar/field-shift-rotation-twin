"""Acceptance test of units l1/water-ep3-parameters (issue #153) and
l1/water-ep3-identifiers (issue #191).

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
from engine.water import _parameters
from engine.water import exposure as module
from engine.water.et0.quantities import CLIMATE_QUANTITIES
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
}
PLACEHOLDER_DAY = {
    # On a day with a crop the basal crop coefficient is read by crop and
    # stage (PLACEHOLDER_STAGE); here, the one of a day with no crop.
    "basal_crop_coefficient": {"no_crop": 0.333},
    "crop_height": {"crop-a": 1.11, "crop-b": 2.22, "no_crop": 0.111},
    "cover_fraction_exponent": {"crop-a": 1.11, "crop-b": 2.22, "no_crop": 1.11},
    "curve_number": {"crop-a": 1.11, "crop-b": 0.555, "no_crop": 1.11},
}
PLACEHOLDER_CROP = {
    "maximum_root_depth": {"crop-a": 1.11, "crop-b": 2.22},
    "readily_available_fraction": {"crop-a": 0.444, "crop-b": 0.888},
}
# The value of every record read by crop and growth stage.
PLACEHOLDER_STAGE = {"initial": 0.444, "mid": 0.555, "end": 0.666}
# The root depth of a day with a crop in the case with synthetic stages: above
# zero and not deeper than the column (column_depth).
PLACEHOLDER_GROWTH_ROOT_DEPTH = 1.11
CROPS = ("crop-a", "crop-b")

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
    """The scope of a label: ``no_crop``, a crop, or ``<crop>:<stage>``."""
    if label == "no_crop":
        return {"management": "no_crop"}
    crop, _, stage = label.partition(":")
    if stage:
        return {"crop": crop_word(crop), "stage": stage}
    return {"crop": crop_word(crop)}


def label_of(scope: dict) -> str | None:
    """The label of a scope of the test catalogue; ``None`` for the empty scope."""
    if not scope:
        return None
    if "management" in scope:
        return "no_crop"
    crop = scope["crop"].split("-", 1)[1]
    return f"{crop}:{scope['stage']}" if "stage" in scope else crop


def marked_catalogue() -> dict[str, dict]:
    """Every parameter the chain reads, keyed as load_folder keys a record."""
    records = []
    for parameter_id in module.SITE_PARAMETERS:
        value = PLACEHOLDER_SITE.get(parameter_id, 1.0)
        records.append(placeholder_record(parameter_id, value, {}))
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


def chain_calendar_document() -> dict[str, Any]:
    """The example calendar over the three years of ``several_full_years``.

    One component is added, copied from the second with its dates moved into
    the third year, and the crop identifiers are unmarked.
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
    for component in document["components"]:
        component["crop_id"] = unmarked(component["crop_id"])
    return document


def chain_calendar() -> RotationCalendar:
    return RotationCalendar.model_validate(chain_calendar_document())


def bare_calendar() -> RotationCalendar:
    """The calendar of ``chain_calendar`` with no component: no day has a crop.

    On a day with a crop the chain has no value, because the growth stage of
    the day is not known (D79, OPEN 4 of EXPOSURE.md), and the states carried
    from day to day stay missing after it. The cases that check the chain
    itself run on this calendar, so that every day is computed.
    """
    document = chain_calendar_document()
    document["components"] = []
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


def assert_definition_incomplete(item: WaterDeficitExposure) -> None:
    assert item.missing.reason == "NOT_AVAILABLE"
    assert "C1.4" in item.missing.detail
    assert "D61" in item.missing.detail
    assert "computed on every day of the year" in item.missing.detail


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
        assert item.value is None
        assert_definition_incomplete(item)


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
        assert b.transpiration == 0  # no day of the calendar has a crop
    assert all(count > 0 for count in branches.values()), branches


def synthetic_stage(day: dt.date) -> str:
    """A growth stage given directly by the test, in turn day after day."""
    return module.STAGES[day.toordinal() % len(module.STAGES)]


def test_daily_balance_closes_its_mass_on_days_with_transpiration_given_synthetic_stages(
    monkeypatch,
):
    # The calendar contract carries no growth stage, so the stages and the
    # root depth of each day with a crop are given by replacing the one
    # function of EP3 that would read them (_growth_of_day). Synthetic: they
    # come from no phenology and no root-growth curve.
    def synthetic_growth(calendar_):
        return lambda day, crop: module.Growth(
            stage=synthetic_stage(day), root_depth=PLACEHOLDER_GROWTH_ROOT_DEPTH
        )

    monkeypatch.setattr(module, "_growth_of_day", synthetic_growth)
    calendar_ = chain_calendar()
    components = [
        (component.start.date, component.end.date) for component in calendar_.components
    ]
    days = chain(calendar_)
    capacity = PLACEHOLDER_SITE["column_capacity"]
    with_transpiration = 0
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
        if any(start <= day.date <= end for start, end in components):
            # The basal coefficient of the stage given for the day.
            kcb = PLACEHOLDER_STAGE[synthetic_stage(day.date)]
            assert b.transpiration_demanded == pytest.approx(
                kcb * day.reference_evapotranspiration
            )
            assert is_number(b.stress_coefficient)
            with_transpiration += b.transpiration > 0
        else:
            assert b.transpiration == 0
    assert with_transpiration > 0
    # Every year is computed, so it is missing only for the definition (D61).
    result = run(calendar_=calendar_)
    assert_loads(result)
    for item in result:
        assert_definition_incomplete(item)


def test_crop_of_each_day_follows_the_calendar():
    calendar_ = chain_calendar()
    components = [
        (component.start.date, component.end.date) for component in calendar_.components
    ]
    first_crop_day = min(start for start, _ in components)
    days = chain(calendar_)
    assert days[0].date < first_crop_day
    for day in days:
        covered = any(start <= day.date <= end for start, end in components)
        b = day.balance
        if day.date < first_crop_day:
            # A day with no crop: computed, with no transpiration.
            assert not covered
            assert is_number(b.storage_end)
            assert b.transpiration == 0
            assert isinstance(b.transpiration_demanded, Missing)
            assert b.transpiration_demanded.reason == "NOT_APPLICABLE"
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
    result = run(calendar_=calendar_)
    assert_loads(result)
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"chain MISSING_INPUT: {module.STAGE_UNKNOWN}" in items_of(
            item.missing.detail
        )
        assert "D79" in item.missing.detail
    assert f"the first on {first_crop_day.isoformat()}" in result[0].missing.detail


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
        for parameter_id in module.SITE_PARAMETERS:
            assert f"'{parameter_id}'" in site
        no_crop = no_record_item(detail, NO_CROP_SCOPE)
        for parameter_id in (*module.DAY_PARAMETERS, *module.STAGE_PARAMETERS):
            assert f"'{parameter_id}'" in no_crop
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
    + [(name, crop) for name in module.CROP_PARAMETERS for crop in CROPS],
)
def test_parameter_with_no_record_is_missing_input_naming_it_and_no_other(key):
    parameter_id, label = key
    # A parameter of the site or of a day with no crop is checked on the
    # calendar with no crop, on which every year is computed with the whole
    # catalogue; a parameter of a crop on the calendar with crops, on which the
    # years are missing anyway (the stage of a crop day is not known, D79).
    with_crops = label not in (None, "no_crop")
    calendar_ = chain_calendar() if with_crops else bare_calendar()
    result = run(calendar_=calendar_, parameters=catalogue_with({key: None}))
    scope = "{}" if label is None else json.dumps(unmarked(scope_of(label)))
    missing = [item for item in result if item.missing.reason != "NOT_AVAILABLE"]
    assert missing, "the parameter is needed by some year"
    if not with_crops:
        assert missing == result  # removing the record makes every year missing
    for item in missing:
        assert item.missing.reason == "MISSING_INPUT"
        named = no_record_item(item.missing.detail, scope)
        assert named.endswith(f": '{parameter_id}'")
        assert item.missing.detail.count("parameters with no record") == 1
    # The years before the one that first needs it are computed.
    computed = [item for item in result if item.missing.reason == "NOT_AVAILABLE"]
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
        missing = [item for item in result if item.missing.reason != "NOT_AVAILABLE"]
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
    """The calendar of ``chain_calendar``, one component per crop of the drafts."""
    document = chain_calendar_document()
    assert len(document["components"]) == len(DRAFTED_CROPS)
    for component, crop in zip(document["components"], DRAFTED_CROPS, strict=True):
        component["crop_id"] = crop
    return RotationCalendar.model_validate(document)


def read_by_ep3(crops: tuple[str, ...]) -> set[tuple[str, str]]:
    """Every (id, scope) EP3 reads for a calendar with these crops and days with none."""
    no_crop = scope_of("no_crop")
    read = {drafted_key(name, {}) for name in module.SITE_PARAMETERS}
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
            assert_definition_incomplete(item)

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
            assert_definition_incomplete(item)


def test_series_one_day_short_at_each_end_leaves_first_and_last_not_covered():
    first, last = several_full_years()
    exact = run(climate_=climate((first, last)))
    for item in exact:
        assert_definition_incomplete(item)
    short = run(climate_=climate((first + ONE_DAY, last - ONE_DAY)))
    assert [item.ag_year for item in short] == [item.ag_year for item in exact]
    reasons = [item.missing.reason for item in short]
    assert reasons[0] == reasons[-1] == "NO_COVERAGE"
    assert set(reasons[1:-1]) == {"NOT_AVAILABLE"}


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
    assert_definition_incomplete(computed)
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
            assert_definition_incomplete(item)
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


def test_calendar_dates_outside_the_record_keep_the_years_and_leave_the_crop_unknown():
    span = several_full_years()
    reference = run(climate_=climate(span))
    document = chain_calendar_document()
    start = dt.date.fromisoformat(document["start_date"])
    end = dt.date.fromisoformat(document["end_date"])
    shift = span[1] - start + ONE_DAY
    document["start_date"] = (start + shift).isoformat()
    document["end_date"] = (end + shift).isoformat()
    for component in document["components"]:
        for edge in [component, *component["periods"]]:
            for key in ("start", "end"):
                if edge[key]["date"] is not None:
                    moved = dt.date.fromisoformat(edge[key]["date"]) + shift
                    edge[key]["date"] = moved.isoformat()
    moved_calendar = RotationCalendar.model_validate(document)
    assert moved_calendar.start_date > span[1]
    result = run(calendar_=moved_calendar, climate_=climate(span))
    assert [item.ag_year for item in result] == [item.ag_year for item in reference]
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        assert "Q5" in item.missing.detail
        assert "outside the dates of the calendar" in item.missing.detail


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
    ]


def test_the_list_is_never_empty_and_no_item_is_a_number():
    for result in every_kind_of_result():
        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert item.value is None
            assert item.value != 0
            assert item.missing is not None
            assert item.missing.reason in REASON_CODES
            assert item.provenance is None
            assert item.range is None and item.range_missing is None
        assert len({item.time_basis for item in result}) == 1
        ag_years = [item.ag_year for item in result]
        assert len(set(ag_years)) == len(ag_years)


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
    ("file_name", "allowed"),
    [
        (
            "exposure.py",
            lambda name: (
                name.startswith("contracts.inputs.")
                or name == "contracts.results.models"
                or name
                in (
                    "engine.water",
                    "engine.water._parameters",
                    "engine.water.et0",
                    "engine.water.et0.quantities",
                    "engine.water.runoff",
                )
            ),
        ),
        (
            "_parameters.py",
            lambda name: name in ("contracts.results.models", "params.catalogue"),
        ),
    ],
)
def test_modules_import_only_allowed_modules_and_hold_only_the_integer_one(
    file_name, allowed
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
    assert numbers <= {1}
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
    ]
    assert len(names) == len(set(names))
    for name in names:
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
        "site",
    ]
    assert sorted(by_scope["site"]) == sorted(module.SITE_PARAMETERS)
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
