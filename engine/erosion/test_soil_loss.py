"""Acceptance test of units l0/erosion-entrypoint (issue #115),
l0/erosion-ep1-parameters (issue #154), l0/erosion-ep1-c-r (issue #173) and,
for the wiring of the repetition of D47, l1/calendar-repeat-d47 (issue #207).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``SOIL_LOSS.md`` under "PROPOSED cases"; a test checks that the two lists
agree. The identifier of a case is the name of its test function without
``test_``, with hyphens.

Every input is built from the PLACEHOLDER examples of
``contracts/inputs/examples/``, loaded and then changed in memory:

- the daily values of a longer "precipitation" series repeat the items of the
  example series in order (it holds a day without data, so R is never
  computed from it);
- a *computable* series repeats ``RAIN`` instead, in ``mm day-1``, with every
  day present;
- a *computable* calendar places the two PLACEHOLDER crops in every
  agricultural year, from the agricultural year before the record of
  ``several_full_years``;
- the daily-index route reads the calendar repeated over the years of the
  record (D47, ``engine/calendar/repeat.py``), whose first cycle starts in the
  first agricultural year of the record and has nothing before it. So the
  record of the daily-route tests (``daily_years``) begins one month before
  the first agricultural year it covers, as the record of D29 does with a July
  start: that partly covered year is the computable calendar's first year,
  laid out unchanged, and every covered day has a crop (or none) and a last
  harvest. Expected crops and harvests come from the repetition computed again
  here (``repeated_windows``).

Expected agricultural years are computed from the dates of the series, day by
day, independently of the module under test. Expected soil loss is computed
again here from the PROPOSED forms of ``r_factor/README.md`` and
``c_factor/README.md``, day by day, without calling the module.

Test catalogues: every record is built here in the record format of
``params/README.md`` and carries the word PLACEHOLDER in its citation, its
persons and its reasons. ``params.catalogue`` refuses a record with that word,
so, as ``params/test_layout.py`` does, the catalogue passed to the entry point
is an in-memory copy in which the word is replaced by ``UNMARKED_TEST_ONLY``;
that copy passes ``check_catalogue``. Its numbers are not values of the
method: ``placeholder_values`` and ``CHOSEN`` say how they are made.

Run from the repository root: ``py -3.12 -m pytest engine/erosion/test_soil_loss.py``.
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
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    ReasonCode,
    SoilLossResults,
)
from engine.calendar.repeat import list_phases, phase_calendar
from engine.erosion import equation, ls
from engine.erosion import soil_loss as module
from params.catalogue import check_catalogue, load_folder, read_value

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
INDICATOR = "soil_loss"
PRECIPITATION = "precipitation"  # decision D23 of issue #77
MM_PER_DAY = "mm day-1"  # CQ1 of contracts/CLIMATE_QUANTITIES.md
ONE_DAY = dt.timedelta(days=1)
WORD = "PLACEHOLDER"
EMPTY_SCOPE = "scope {}"


def unmarked(item: Any) -> Any:
    """An in-memory copy with the word PLACEHOLDER replaced (params/test_layout.py)."""
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {unmarked(key): unmarked(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmarked(value) for value in item]
    return item


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


def example_start() -> dt.date:
    return dt.date.fromisoformat(example_precipitation()["start_date"])


def days_between(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + k * ONE_DAY for k in range((last - first).days + 1)]


def precipitation_series(first: dt.date, last: dt.date) -> dict[str, Any]:
    """The example series stretched from ``first`` to ``last``.

    Each day takes, in turn, the value or missing part of the example days.
    """
    series = copy.deepcopy(example_precipitation())
    items = series["days"]
    days = []
    for position, day in enumerate(days_between(first, last)):
        item = {k: v for k, v in items[position % len(items)].items() if k != "date"}
        days.append({"date": day.isoformat(), **item})
    series.update(start_date=first.isoformat(), end_date=last.isoformat(), days=days)
    return series


# PLACEHOLDER daily precipitation of a computable series, repeated in turn.
# Plainly not weather: repeated digits, and zero for a dry day. Some days lie
# above the PLACEHOLDER threshold of the daily index and some at or below it.
RAIN = (0.0, 5.55, 33.3, 0.0, 1.11, 22.2, 0.0, 44.4, 2.22)


def rain_series(first: dt.date, last: dt.date, value_of: Any = None) -> dict[str, Any]:
    """A series in mm day-1 with every day present, from ``first`` to ``last``.

    ``value_of(day, position)`` gives the value of a day; by default ``RAIN``
    in turn.
    """
    series = copy.deepcopy(example_precipitation())
    days = []
    for position, day in enumerate(days_between(first, last)):
        value = (
            RAIN[position % len(RAIN)] if value_of is None else value_of(day, position)
        )
        days.append({"date": day.isoformat(), "value": value})
    series.update(
        unit=MM_PER_DAY,
        start_date=first.isoformat(),
        end_date=last.isoformat(),
        days=days,
        source="PLACEHOLDER: repeated test values, not weather, no real source",
    )
    return series


def climate_with(
    series: dict[str, Any] | None, document: dict[str, Any] | None = None
) -> SiteClimate:
    document = copy.deepcopy(document) if document is not None else climate_document()
    others = [
        item for item in document["daily_series"] if item["quantity"] != PRECIPITATION
    ]
    document["daily_series"] = others + ([series] if series is not None else [])
    return SiteClimate.model_validate(document)


def ag_year_of(day: dt.date) -> int:
    return day.year if day.month >= start_month() else day.year - 1


def first_day_of(ag_year: int) -> dt.date:
    return dt.date(ag_year, start_month(), 1)


def last_day_of(ag_year: int) -> dt.date:
    return first_day_of(ag_year + 1) - ONE_DAY


# Three spans of the record, all from the dates of the example series.
def several_full_years() -> tuple[dt.date, dt.date]:
    """From the first day of the agricultural year that begins in the calendar
    year of the example's first day, to the last day of the agricultural year
    two later."""
    first_ag_year = example_start().year
    return first_day_of(first_ag_year), last_day_of(first_ag_year + 2)


def partial_years() -> tuple[dt.date, dt.date]:
    """From the first day of the example series to the last day of the first
    month of the agricultural year after ``several_full_years``: the first and
    the last years are not covered whole."""
    _, last = several_full_years()
    following = last + ONE_DAY
    return example_start(), month_bounds(following.year, following.month)[1]


def daily_years() -> tuple[dt.date, dt.date]:
    """The years of ``several_full_years`` with the last month before them:
    the agricultural year before is only partly covered, as the first year of
    the D29 record is with a July start."""
    first, last = several_full_years()
    before = first - ONE_DAY
    return dt.date(before.year, before.month, 1), last


def calendar() -> RotationCalendar:
    return RotationCalendar.model_validate(calendar_document())


def soil() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(soil_document())


def climate(span: tuple[dt.date, dt.date] | None = None) -> SiteClimate:
    return climate_with(precipitation_series(*(span or several_full_years())))


def computable_climate(
    span: tuple[dt.date, dt.date] | None = None, value_of: Any = None
) -> SiteClimate:
    return climate_with(rain_series(*(span or several_full_years()), value_of))


def run(
    calendar_: RotationCalendar | None = None,
    climate_: SiteClimate | None = None,
    soil_: SiteSoilSlope | None = None,
    parameters: dict[str, dict] | None = None,
    daily: bool = False,
) -> SoilLossResults | Missing:
    """EP1 on the main route, or with ``daily`` the daily-index route."""
    function = (
        module.compute_soil_loss_daily_index if daily else module.compute_soil_loss
    )
    return function(
        calendar=calendar_ if calendar_ is not None else calendar(),
        climate=climate_ if climate_ is not None else climate(),
        soil_slope=soil_ if soil_ is not None else soil(),
        parameters=parameters if parameters is not None else {},
    )


def expected_ag_years(first: dt.date, last: dt.date) -> list[int]:
    """Every agricultural year with at least one day in the span, day by day."""
    return sorted({ag_year_of(day) for day in days_between(first, last)})


def is_covered(first: dt.date, last: dt.date, span: tuple[dt.date, dt.date]) -> bool:
    return span[0] <= first and last <= span[1]


def covered_ag_years(span: tuple[dt.date, dt.date]) -> list[int]:
    return [
        year
        for year in expected_ag_years(*span)
        if is_covered(first_day_of(year), last_day_of(year), span)
    ]


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    return first, following - ONE_DAY


def infeasible_calendar() -> RotationCalendar:
    document = calendar_document()
    document["feasibility"] = {
        "feasible": False,
        "violations": [{"rule": "PLACEHOLDER-rule", "component_ids": []}],
    }
    return RotationCalendar.model_validate(document)


def calendar_without_start_month() -> RotationCalendar:
    document = calendar_document()
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: not declared"},
    }
    return RotationCalendar.model_validate(document)


def shift_years(text: str, years: int) -> str:
    day = dt.date.fromisoformat(text)
    return day.replace(year=day.year + years).isoformat()


def moved_past(document: dict[str, Any], last: dt.date) -> RotationCalendar:
    """The calendar document moved past ``last``, whole years at a time."""
    document = copy.deepcopy(document)
    years = last.year - dt.date.fromisoformat(document["start_date"]).year + 1
    years += -years % 4  # whole leap cycles, so that a 29 February stays a date
    document["start_date"] = shift_years(document["start_date"], years)
    document["end_date"] = shift_years(document["end_date"], years)
    for component in document["components"]:
        for edge in ("start", "end"):
            component[edge]["date"] = shift_years(component[edge]["date"], years)
        for period in component["periods"]:
            for edge in ("start", "end"):
                period[edge]["date"] = shift_years(period[edge]["date"], years)
    built = RotationCalendar.model_validate(document)
    assert built.start_date > last
    return built


def calendar_outside_the_record() -> RotationCalendar:
    """The example calendar moved past the last day of the record."""
    return moved_past(calendar_document(), several_full_years()[1])


def soil_with_missing(*names: str, document: dict | None = None) -> SiteSoilSlope:
    document = copy.deepcopy(document) if document is not None else soil_document()
    for name in names:
        document[name] = {
            "value": None,
            "unit": document[name]["unit"],
            "missing": {
                "reason": "NO_COVERAGE",
                "detail": f"PLACEHOLDER: {name} not available for this place",
            },
        }
    return SiteSoilSlope.model_validate(document)


def values(result: SoilLossResults) -> list[AnnualSoilLoss | MonthlySoilLoss]:
    return [*result.annual, *result.monthly]


# --- the computable calendar -------------------------------------------------

CROP_A = unmarked("PLACEHOLDER-crop-a")
CROP_B = unmarked("PLACEHOLDER-crop-b")
CROPS = (CROP_A, CROP_B)


def dated(day: dt.date) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "provenance": "DECLARED",
        "source": "PLACEHOLDER: test calendar, not a real declaration",
    }


def component(
    component_id: str, crop_id: str, start: dt.date | None, end: dt.date | None
) -> dict[str, Any]:
    def edge(day: dt.date | None) -> dict[str, Any]:
        if day is not None:
            return dated(day)
        return {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: no date"},
        }

    return {
        "component_id": component_id,
        "crop_id": crop_id,
        "start": edge(start),
        "end": edge(end),
        "periods": [],
    }


def crop_windows(ag_year: int) -> list[tuple[str, dt.date, dt.date]]:
    """The PLACEHOLDER dates of the two crops in one agricultural year.

    Crop A from the third month to the end of the eighth, crop B from the
    tenth month to the end of the eleventh; no crop between. Months counted
    from the start month of the example calendar.
    """
    month = start_month()

    def month_of(position: int) -> tuple[int, int]:
        index = ag_year * 12 + month - 1 + position
        return index // 12, index % 12 + 1

    a_first, a_last = month_of(2), month_of(7)
    b_first, b_last = month_of(9), month_of(10)
    return [
        (CROP_A, dt.date(*a_first, 1), month_bounds(*a_last)[1]),
        (CROP_B, dt.date(*b_first, 1), month_bounds(*b_last)[1]),
    ]


def computable_calendar_document(
    span: tuple[dt.date, dt.date] | None = None,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A feasible calendar from the agricultural year before the span to the
    last day of the span, with the crops of ``crop_windows`` in every year."""
    first, last = span or several_full_years()
    start = first_day_of(ag_year_of(first) - 1)
    document = calendar_document()
    document.update(identity or {})
    document["start_date"] = start.isoformat()
    document["end_date"] = last.isoformat()
    components = []
    for ag_year in range(ag_year_of(start), ag_year_of(last) + 1):
        for crop_id, begins, ends in crop_windows(ag_year):
            if start <= begins and ends <= last:
                position = len(components) + 1
                components.append(
                    component(f"PLACEHOLDER-c{position}", crop_id, begins, ends)
                )
    document["components"] = components
    return document


def computable_calendar(
    span: tuple[dt.date, dt.date] | None = None,
) -> RotationCalendar:
    return RotationCalendar.model_validate(computable_calendar_document(span))


# --- test catalogues ----------------------------------------------------------

PERCENT = ls.SlopeUnit.PERCENT
LENGTH_UNIT = "PLACEHOLDER_length_unit"
HEIGHT_UNIT = "PLACEHOLDER_height_unit"
MASS_UNIT = "PLACEHOLDER_mass_per_area_unit"

# PLACEHOLDER base of the test numbers: plainly unreal, far above any value a
# factor or a coefficient of RUSLE takes, so that no test number lands on a
# published coefficient. Not a value of the method.
PLACEHOLDER_BASE = 123456.25

# PLACEHOLDER numbers of the records whose forms need a number of a certain
# size to give a result: the exponent and the threshold of the daily index (a
# threshold below some days of RAIN), and the coefficients of c_factor/ (zero
# or more). Repeated digits, not values of the method.
CHOSEN: dict[str, float] = {
    module.R_EXPONENT_ID: 1.11,
    module.R_THRESHOLD_ID: 2.22,
    module.FALL_HEIGHT_COEFFICIENT_ID: 0.333,
    module.SURFACE_COVER_B_PER_PERCENT_ID: 0.00666,
    module.MASS_COVER_COEFFICIENT_ID: 0.222,
}

NO_CROP = "no_crop"
# Scope words of the crop records: a crop of the computable calendar, or the
# word of a day with no crop (scope key "management").
CROP_SCOPES: dict[str, dict[str, str]] = {
    CROP_A: {"crop": CROP_A},
    CROP_B: {"crop": CROP_B},
    NO_CROP: dict(module.NO_CROP_SCOPE),
}

# PLACEHOLDER numbers of the crop records, by identifier and scope word. A
# canopy cover is a fraction; every other number only has to be zero or more.
# Repeated digits, not values of the method.
CROP_VALUES: dict[tuple[str, str], float] = {
    (module.CANOPY_COVER_ID, CROP_A): 0.555,
    (module.CANOPY_COVER_ID, CROP_B): 0.444,
    (module.CANOPY_COVER_ID, NO_CROP): 0.111,
    (module.FALL_HEIGHT_ID, CROP_A): 2.22,
    (module.FALL_HEIGHT_ID, CROP_B): 1.11,
    (module.FALL_HEIGHT_ID, NO_CROP): 0.555,
    (module.RESIDUE_MASS_ID, CROP_A): 7.77,
    (module.RESIDUE_MASS_ID, CROP_B): 3.33,
    (module.DECAY_COEFFICIENT_ID, CROP_A): 0.0333,
    (module.DECAY_COEFFICIENT_ID, CROP_B): 0.0444,
}


# Every identifier read with the empty scope, by either route.
SITE_IDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *module.PARAMETER_IDS,
            *module.MONTHLY_EROSIVITY_IDS,
            *module.DAILY_ROUTE_PARAMETER_IDS,
        )
    )
)
MONTHLY_UNIT = "PLACEHOLDER_monthly_erosivity_unit"


def placeholder_values() -> dict[str, float]:
    """One PLACEHOLDER number per record with the empty scope: ``CHOSEN``, or
    else ``PLACEHOLDER_BASE`` plus its position in the list of identifiers.
    Not values of the method."""
    return {
        pid: CHOSEN.get(pid, PLACEHOLDER_BASE + position)
        for position, pid in enumerate(SITE_IDS)
    }


def unit_of(pid: str) -> str:
    """The unit string a site record carries: the accepted one for the level
    of R, K, C and P; one PLACEHOLDER unit shared by the twelve monthly
    erosivity records; mm day-1 for the threshold; percent-1 for b of S1
    Eq. 6.6 (PC-1); a
    slope unit for the break slope; the length unit of the slope length for
    the unit length; the inverse of the height and of the mass per area for
    the coefficients that multiply them; dimensionless for the exponent; a
    PLACEHOLDER unit for every other coefficient."""
    accepted = module.ACCEPTED_UNITS
    return {
        module.R_ID: accepted.r,
        module.C_ID: accepted.c,
        **dict.fromkeys(module.MONTHLY_EROSIVITY_IDS, MONTHLY_UNIT),
        module.R_EXPONENT_ID: module.DIMENSIONLESS,
        module.R_THRESHOLD_ID: MM_PER_DAY,
        module.K_ID: accepted.k,
        module.P_ID: accepted.p,
        module.S_BREAK_ID: PERCENT.value,
        module.LAMBDA_UNIT_ID: LENGTH_UNIT,
        module.FALL_HEIGHT_COEFFICIENT_ID: f"{HEIGHT_UNIT}-1",
        module.SURFACE_COVER_B_PER_PERCENT_ID: f"{module.PERCENT}-1",
        module.MASS_COVER_COEFFICIENT_ID: f"({MASS_UNIT})-1",
    }.get(pid, "PLACEHOLDER_unit")


def crop_unit_of(pid: str) -> str:
    return {
        module.CANOPY_COVER_ID: module.DIMENSIONLESS,
        module.FALL_HEIGHT_ID: HEIGHT_UNIT,
        module.RESIDUE_MASS_ID: MASS_UNIT,
        module.DECAY_COEFFICIENT_ID: f"{module.DAY}-1",
    }[pid]


def placeholder_record(
    pid: str, value: float, unit: str, scope: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "id": pid,
        "scope": dict(scope or {}),
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": "PLACEHOLDER: this test record has no range",
        "citation": {
            "reference": "PLACEHOLDER reference. This is not a publication.",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
    }


def site_key(pid: str) -> str:
    return f"{pid}.json"


def crop_key(pid: str, word: str) -> str:
    return f"{pid}.{word}.json"


def marked_catalogue(*leave_out: str | tuple[str, str]) -> dict[str, dict]:
    """Every record EP1 reads, keyed by a file path, still marked PLACEHOLDER.

    ``leave_out`` names a site record by its identifier, or a crop record by
    its identifier and scope word.
    """
    records = {
        site_key(pid): placeholder_record(pid, value, unit_of(pid))
        for pid, value in placeholder_values().items()
        if pid not in leave_out
    }
    for (pid, word), value in CROP_VALUES.items():
        if (pid, word) not in leave_out:
            records[crop_key(pid, word)] = placeholder_record(
                pid, value, crop_unit_of(pid), CROP_SCOPES[word]
            )
    return records


def catalogue(*leave_out: str | tuple[str, str]) -> dict[str, dict]:
    """The unmarked copy, which passes ``check_catalogue``."""
    built = unmarked(marked_catalogue(*leave_out))
    assert check_catalogue(built) == []
    return built


def catalogue_with(key: str, **fields: Any) -> dict[str, dict]:
    """The marked catalogue with fields of one record changed, then unmarked.

    ``key`` is a key of ``marked_catalogue``.
    """
    marked = marked_catalogue()
    marked[key].update(fields)
    return unmarked(marked)


def computable_soil_document(document: dict[str, Any] | None = None) -> dict[str, Any]:
    """The soil data with a slope in percent and a slope length in the unit
    of the unit-length record."""
    document = copy.deepcopy(document) if document is not None else soil_document()
    document["slope_steepness"]["unit"] = PERCENT.value
    document["slope_length"]["unit"] = unmarked(LENGTH_UNIT)
    return document


def computable_soil(document: dict[str, Any] | None = None) -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(computable_soil_document(document))


def run_computable(
    parameters: dict[str, dict] | None = None, **arguments: Any
) -> SoilLossResults:
    """A run with every input computable unless an argument replaces it."""
    result = run(
        **{
            "soil_": computable_soil(),
            "climate_": computable_climate(),
            "calendar_": computable_calendar(),
            **arguments,
            "parameters": catalogue() if parameters is None else parameters,
        }
    )
    assert isinstance(result, SoilLossResults)
    return result


def run_daily(
    parameters: dict[str, dict] | None = None, **arguments: Any
) -> SoilLossResults:
    """``run_computable`` on the daily-index route, by default on the record
    of ``daily_years``. The years the record does not cover whole are checked
    to be ``NO_COVERAGE`` here and left out of the result returned, so that a
    test reads only the years the route computes."""
    arguments.setdefault("climate_", computable_climate(daily_years()))
    result = run_computable(parameters, daily=True, **arguments)
    years = covered_ag_years(series_span(arguments["climate_"]))
    for item in result.annual:
        if item.ag_year not in years:
            assert item.value is None and item.missing.reason == "NO_COVERAGE"
    assert {item.ag_year for item in result.annual} >= set(years)
    return SoilLossResults(
        annual=[item for item in result.annual if item.ag_year in years],
        monthly=[item for item in result.monthly if item.ag_year in years],
    )


def named(pid: str, scope: dict[str, str] | None = None) -> str:
    text = json.dumps(scope or {}, sort_keys=True)
    return f"parameter '{pid}' with scope {text}"


# --- the expected values, computed again from the PROPOSED forms -------------


def expected_ls(numbers: dict[str, float], soil_: SiteSoilSlope | None = None) -> float:
    slope = soil_ if soil_ is not None else computable_soil()
    steepness = ls.slope_steepness_factor(
        slope_steepness=slope.slope_steepness.value,
        slope_unit=PERCENT,
        s_break=numbers[module.S_BREAK_ID],
        s_break_unit=PERCENT,
        **{name: numbers[pid] for name, pid in module.S_COEFFICIENTS.items()},
    )
    length = ls.slope_length_factor(
        slope_length=slope.slope_length.value,
        slope_length_unit=slope.slope_length.unit,
        lambda_unit=numbers[module.LAMBDA_UNIT_ID],
        lambda_unit_unit=unmarked(LENGTH_UNIT),
        slope_steepness=slope.slope_steepness.value,
        slope_unit=PERCENT,
        **{name: numbers[pid] for name, pid in module.L_COEFFICIENTS.items()},
    )
    assert isinstance(steepness, float) and isinstance(length, float)
    return length * steepness


def expected_product(
    numbers: dict[str, float] | None = None, soil_: SiteSoilSlope | None = None
) -> float:
    """The main route: equation.py of the level of R, K, LS, the declared C, P."""
    numbers = placeholder_values() if numbers is None else numbers
    accepted = module.ACCEPTED_UNITS
    product = equation.annual_soil_loss(
        r=equation.Factor(numbers[module.R_ID], accepted.r),
        k=equation.Factor(numbers[module.K_ID], accepted.k),
        ls=equation.Factor(expected_ls(numbers, soil_), accepted.ls),
        c=equation.Factor(numbers[module.C_ID], accepted.c),
        p=equation.Factor(numbers[module.P_ID], accepted.p),
        accepted_units=accepted,
        unit_guard_reason=module.UNIT_NOT_ACCEPTED,
    )
    assert isinstance(product, float)
    return product


def expected_month(
    month: int,
    numbers: dict[str, float] | None = None,
    soil_: SiteSoilSlope | None = None,
) -> float:
    """The main route: the level of R times the share of the calendar month in
    the twelve monthly erosivity records, times K, LS, C and P."""
    numbers = placeholder_values() if numbers is None else numbers
    monthly = [numbers[pid] for pid in module.MONTHLY_EROSIVITY_IDS]
    fraction = monthly[month - 1] / sum(monthly)
    return (
        numbers[module.R_ID]
        * fraction
        * numbers[module.K_ID]
        * expected_ls(numbers, soil_)
        * numbers[module.C_ID]
        * numbers[module.P_ID]
    )


def months_of(ag_year: int) -> list[tuple[int, int]]:
    first = first_day_of(ag_year)
    months = []
    for k in range(12):
        index = first.year * 12 + first.month - 1 + k
        months.append((index // 12, index % 12 + 1))
    return months


def expected_r_and_fractions(
    climate_: SiteClimate, numbers: dict[str, float]
) -> tuple[dict[int, float], dict[int, dict[tuple[int, int], float]]]:
    """The daily-index route: R of every covered year and its monthly
    fractions, by the forms of r_factor/README.md: index = P ** exponent above
    the threshold, else 0; fraction = monthly sum / annual sum; ratio = annual
    sum / mean annual sum; R(year, month) = level * fraction * ratio."""
    (series,) = [s for s in climate_.daily_series if s.quantity == PRECIPITATION]
    exponent = numbers[module.R_EXPONENT_ID]
    threshold = numbers[module.R_THRESHOLD_ID]
    by_month: dict[tuple[int, int], float] = {}
    for item in series.days:
        index = item.value**exponent if item.value > threshold else 0.0
        key = (item.date.year, item.date.month)
        by_month[key] = by_month.get(key, 0.0) + index
    years = covered_ag_years((series.start_date, series.end_date))
    annual = {year: sum(by_month[m] for m in months_of(year)) for year in years}
    mean = sum(annual.values()) / len(annual)
    fractions = {
        year: {m: by_month[m] / annual[year] for m in months_of(year)} for year in years
    }
    r = {
        year: sum(
            numbers[module.R_ID] * fractions[year][m] * (annual[year] / mean)
            for m in months_of(year)
        )
        for year in years
    }
    return r, fractions


def shifted(day: dt.date, years: int) -> dt.date:
    """Point 2 of engine/calendar/repeat.py, computed again."""
    year = day.year + years
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    if (day.month, day.day) == (2, 29) and not leap:
        return dt.date(year, 2, 28)
    return day.replace(year=year)


def repeated_windows(
    calendar_: RotationCalendar, span: tuple[dt.date, dt.date]
) -> list[tuple[str, dt.date, dt.date]]:
    """The dated components of the calendar repeated over the agricultural
    years of the record ``span``, by points 1 to 5 of engine/calendar/repeat.py,
    computed again here: the cycle is the smallest whole number of years after
    which ``start_date`` falls after ``end_date``; the first cycle starts in the
    first agricultural year of the record; a component is laid out while its
    start is not after the last day of the record's years."""
    length = 1
    while shifted(calendar_.start_date, length) <= calendar_.end_date:
        length += 1
    last_day = last_day_of(ag_year_of(span[1]))
    shift = ag_year_of(span[0]) - ag_year_of(calendar_.start_date)
    windows = []
    while shifted(calendar_.start_date, shift) <= last_day:
        for c in calendar_.components:
            start = shifted(c.start.date, shift)
            if start <= last_day:
                windows.append((c.crop_id, start, shifted(c.end.date, shift)))
        shift += length
    return windows


def series_span(climate_: SiteClimate) -> tuple[dt.date, dt.date]:
    (series,) = [s for s in climate_.daily_series if s.quantity == PRECIPITATION]
    return series.start_date, series.end_date


def expected_ratio_of_day(
    day: dt.date,
    windows: list[tuple[str, dt.date, dt.date]],
    numbers: dict[str, float],
) -> float:
    """The daily-index route: the soil-loss ratio of one day by the forms of
    c_factor/README.md under PC-1: the residue cover from the decayed mass of
    the last harvest; the surface-cover sub-factor exp(-b * cover in percent);
    the canopy sub-factor of the effective canopy cover, the canopy cover
    times one minus the residue cover (S1 Eq. 6.5)."""
    crop = next(
        (crop_id for crop_id, start, end in windows if start <= day <= end),
        NO_CROP,
    )
    harvest_crop, _, harvest_end = max(
        (w for w in windows if w[2] < day), key=lambda w: w[2]
    )
    mass = CROP_VALUES[(module.RESIDUE_MASS_ID, harvest_crop)] * math.exp(
        -CROP_VALUES[(module.DECAY_COEFFICIENT_ID, harvest_crop)]
        * (day - harvest_end).days
    )
    residue_cover = 1 - math.exp(-numbers[module.MASS_COVER_COEFFICIENT_ID] * mass)
    surface = math.exp(
        -numbers[module.SURFACE_COVER_B_PER_PERCENT_ID] * residue_cover * 100
    )
    effective = CROP_VALUES[(module.CANOPY_COVER_ID, crop)] * (1 - residue_cover)
    height = CROP_VALUES[(module.FALL_HEIGHT_ID, crop)]
    canopy = 1 - effective * math.exp(
        -numbers[module.FALL_HEIGHT_COEFFICIENT_ID] * height
    )
    return canopy * surface


def expected_daily_soil_loss(
    climate_: SiteClimate,
    calendar_: RotationCalendar,
    numbers: dict[str, float] | None = None,
    soil_: SiteSoilSlope | None = None,
) -> dict[int, float]:
    """The daily-index route: A = R * K * LS * C * P of every covered year,
    C = sum over the months of fraction * mean daily soil-loss ratio, over one
    year (M1.5)."""
    numbers = placeholder_values() if numbers is None else numbers
    r, fractions = expected_r_and_fractions(climate_, numbers)
    product = numbers[module.K_ID] * expected_ls(numbers, soil_) * numbers[module.P_ID]
    windows = repeated_windows(calendar_, series_span(climate_))
    result = {}
    for year, by_month in fractions.items():
        c = 0.0
        for (y, m), fraction in by_month.items():
            ratios = [
                expected_ratio_of_day(day, windows, numbers)
                for day in days_between(*month_bounds(y, m))
            ]
            c += fraction * sum(ratios) / len(ratios)
        result[year] = r[year] * c * product
    return result


def assert_numbers(result: SoilLossResults, expected: dict[int, float]) -> None:
    computed = {
        item.ag_year: item.value for item in result.annual if item.value is not None
    }
    assert computed.keys() == expected.keys()
    for year, value in expected.items():
        assert computed[year] == pytest.approx(value, rel=1e-9), year


# --- cases of #125, kept ------------------------------------------------------


def test_examples_with_several_agricultural_years_load_into_soil_loss_results():
    span = several_full_years()
    cal = calendar()
    result = run(cal, climate(span))
    assert isinstance(result, SoilLossResults)

    ag_years = expected_ag_years(*span)
    assert len(ag_years) > 1
    assert [item.ag_year for item in result.annual] == ag_years
    for ag_year in ag_years:
        months = [item for item in result.monthly if item.ag_year == ag_year]
        assert len(months) == 12
        first = months[0]
        assert (first.year, first.month) == (ag_year, cal.ag_year_start.month)
        positions = [item.year * 12 + item.month for item in months]
        assert positions == list(range(positions[0], positions[0] + 12))

    for item in values(result):
        assert item.indicator == INDICATOR
        assert item.direction == DIRECTION_OF[INDICATOR]
    assert {item.unit for item in result.annual} == {UNIT_SOIL_LOSS_ANNUAL}
    assert {item.unit for item in result.monthly} == {UNIT_SOIL_LOSS_MONTHLY}

    dumped = result.model_dump(mode="json")
    assert SoilLossResults.model_validate_json(json.dumps(dumped)) == result


def test_start_month_missing_returns_one_missing_input():
    for daily in (False, True):
        result = run(calendar_without_start_month(), daily=daily)
        assert isinstance(result, Missing)
        assert result.reason == "MISSING_INPUT"
        assert "start month" in result.detail


def test_infeasible_calendar_makes_every_value_not_computable():
    span = partial_years()
    for daily in (False, True):
        cases = (
            (infeasible_calendar(), climate(span), {}, soil()),
            (
                infeasible_calendar(),
                computable_climate(span),
                catalogue(),
                computable_soil(),
            ),
        )
        for calendar_, climate_, parameters, soil_ in cases:
            result = run(calendar_, climate_, soil_, parameters, daily=daily)
            assert isinstance(result, SoilLossResults)
            reasons = {item.missing.reason for item in values(result)}
            assert reasons == {"NOT_COMPUTABLE"}
            assert all("infeasible" in item.missing.detail for item in values(result))


def test_year_or_month_not_covered_by_precipitation_is_no_coverage():
    span = partial_years()
    result = run(climate_=climate(span))
    assert isinstance(result, SoilLossResults)
    assert [item.ag_year for item in result.annual] == expected_ag_years(*span)

    reasons = set()
    for item in result.annual:
        covered = is_covered(
            first_day_of(item.ag_year), last_day_of(item.ag_year), span
        )
        expected = "MISSING_INPUT" if covered else "NO_COVERAGE"
        assert item.missing.reason == expected, item.ag_year
        reasons.add(expected)
    assert reasons == {"MISSING_INPUT", "NO_COVERAGE"}

    month_reasons = set()
    for item in result.monthly:
        covered = is_covered(*month_bounds(item.year, item.month), span)
        # Changed by the review of #187: a covered month is computed on the
        # main route, so with an empty catalogue it names its records.
        expected = "MISSING_INPUT" if covered else "NO_COVERAGE"
        assert item.missing.reason == expected, (item.year, item.month)
        month_reasons.add(expected)
        if covered:
            assert module.MONTHLY_EROSIVITY_PREFIX in item.missing.detail
        else:
            assert PRECIPITATION in item.missing.detail
    assert month_reasons == {"MISSING_INPUT", "NO_COVERAGE"}
    # A year that is not covered whole still has months that are covered.
    first_year = result.annual[0].ag_year
    assert {
        item.missing.reason for item in result.monthly if item.ag_year == first_year
    } == {"MISSING_INPUT", "NO_COVERAGE"}


def test_series_one_day_short_at_each_end_leaves_first_and_last_not_covered():
    full_first, full_last = several_full_years()
    span = (full_first + ONE_DAY, full_last - ONE_DAY)
    result = run(climate_=climate(span))
    assert isinstance(result, SoilLossResults)
    ag_years = expected_ag_years(*span)
    assert [item.ag_year for item in result.annual] == ag_years

    reasons = {item.ag_year: item.missing.reason for item in result.annual}
    assert reasons[ag_years[0]] == "NO_COVERAGE"
    assert reasons[ag_years[-1]] == "NO_COVERAGE"
    for ag_year in ag_years[1:-1]:
        assert reasons[ag_year] == "MISSING_INPUT", ag_year

    months = result.monthly
    assert months[0].missing.reason == "NO_COVERAGE"
    assert months[-1].missing.reason == "NO_COVERAGE"
    for item in months[1:-1]:
        assert item.missing.reason == "MISSING_INPUT", (item.year, item.month)


def test_calendar_dates_outside_the_record_keep_the_years_of_the_record():
    """D47: the years are those of the record. The main route reads no date of
    the calendar, so a calendar moved past the record gives the same result,
    with an empty and with a complete catalogue."""
    span = several_full_years()
    moved = run(calendar_outside_the_record(), climate(span))
    assert isinstance(moved, SoilLossResults)
    assert [item.ag_year for item in moved.annual] == expected_ag_years(*span)
    assert moved == run(calendar(), climate(span))
    full = run_computable(calendar_=calendar_outside_the_record())
    assert full == run_computable(calendar_=calendar())
    assert all(item.value is not None for item in full.annual)


def test_no_precipitation_series_returns_one_missing_input():
    for daily in (False, True):
        result = run(climate_=climate_with(None), daily=daily)
        assert isinstance(result, Missing)
        assert result.reason == "MISSING_INPUT"
        assert PRECIPITATION in result.detail


@pytest.mark.parametrize(
    "names",
    [("slope_steepness",), ("slope_length",), ("slope_steepness", "slope_length")],
)
def test_missing_slope_input_is_named_in_the_ls_factor(names):
    soil_ = soil_with_missing(*names, document=computable_soil_document())
    for result in (run_computable(soil_=soil_), run_daily(soil_=soil_)):
        for item in result.annual:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            detail = item.missing.detail
            assert "factor 'ls' is missing" in detail
            for name in names:
                assert (
                    f"{name} is missing in the soil-and-slope data, reason NO_COVERAGE"
                    in (detail)
                )
            for name in {"slope_steepness", "slope_length"} - set(names):
                assert f"{name} is missing" not in detail
            for factor in ("r", "k", "c", "p"):
                assert f"factor '{factor}'" not in detail


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_arguments_of_another_case_or_field_raise_value_error(argument, field):
    arguments = {
        "calendar": calendar(),
        "climate": climate(),
        "soil_slope": soil(),
        "parameters": {},
    }
    arguments[argument] = arguments[argument].model_copy(
        update={field: "PLACEHOLDER-other"}
    )
    for function in (module.compute_soil_loss, module.compute_soil_loss_daily_index):
        with pytest.raises(ValueError, match=field):
            function(**arguments)


@pytest.mark.parametrize("argument", ["calendar", "climate", "soil_slope"])
def test_argument_that_is_not_its_model_raises_type_error(argument):
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    wrong = {"calendar": soil(), "climate": calendar(), "soil_slope": climate()}
    for replacement in (arguments[argument].model_dump(mode="json"), wrong[argument]):
        changed = dict(arguments, **{argument: replacement})
        for function in (
            module.compute_soil_loss,
            module.compute_soil_loss_daily_index,
        ):
            with pytest.raises(TypeError, match=argument):
                function(**changed, parameters={})


# --- the argument parameters (D46, D56) on the main route ---------------------


def test_parameters_missing_positional_or_not_a_dict_raises_type_error():
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    with pytest.raises(TypeError, match="parameters"):
        module.compute_soil_loss(**arguments)
    with pytest.raises(TypeError):
        module.compute_soil_loss(*arguments.values(), {})
    for wrong in (None, [], (), "PLACEHOLDER", list(catalogue().items())):
        with pytest.raises(TypeError, match="parameters"):
            module.compute_soil_loss(**arguments, parameters=wrong)
    record = next(iter(catalogue().values()))
    for wrong in ({"a.json": "PLACEHOLDER"}, {"a.json": [record]}, {object(): record}):
        with pytest.raises(TypeError, match="parameters"):
            module.compute_soil_loss(**arguments, parameters=wrong)


def test_empty_catalogue_names_every_parameter_and_keeps_every_year():
    """The annual value names every record it needs, C as the declared value
    (D69, D84, USER-G); every month names the twelve monthly records."""
    span = several_full_years()
    result = run_computable({})
    assert [item.ag_year for item in result.annual] == expected_ag_years(*span)
    assert {item.missing.reason for item in result.annual} == {"MISSING_INPUT"}
    detail = result.annual[0].missing.detail
    assert {item.missing.detail for item in result.annual} == {detail}
    for factor in equation.FACTOR_NAMES:
        assert f"factor '{factor}' is missing" in detail
    for pid in module.PARAMETER_IDS:
        assert f"{named(pid)} has no record in parameters (D56)" in detail
    c_part = detail.split("factor 'c' is missing", 1)[1].split("factor 'p'", 1)[0]
    assert "DECLARED" in c_part and "D69" in c_part and "USER-G" in c_part
    # Changed by unit l0/erosion-c-main-route (#218): C falls back to the
    # declared record and names the records of the computed C that are missing.
    assert "PROPOSED fallback of brief #218" in c_part
    for pid in module.MONTHLY_EROSIVITY_IDS:
        assert f"{named(pid)} has no record in parameters (D56)" in c_part
    stage = {"stage": module.STAGE_SHOWN}
    for crop in CROPS:
        for pid in module.CANOPY_IDS:
            assert f"{named(pid, {'crop': crop, **stage})} has no record" in c_part
        for pid in module.MAIN_C_RESIDUE_IDS:
            assert f"{named(pid, {'crop': crop})} has no record" in c_part
    for pid in module.CANOPY_IDS:
        assert f"{named(pid, module.NO_CROP_SCOPE)} has no record" in c_part
    for pid in (
        module.R_EXPONENT_ID,
        module.R_THRESHOLD_ID,
        module.RESIDUE_MASS_ID,
        module.YIELD_CONVERSION_ID,
    ):
        assert f"'{pid}'" not in detail
    assert {item.missing.reason for item in result.monthly} == {"MISSING_INPUT"}
    for item in result.monthly:
        month_detail = item.missing.detail
        assert "its factors are those of the annual product" in month_detail
        for pid in module.MONTHLY_EROSIVITY_IDS:
            assert f"{named(pid)} has no record in parameters (D56)" in month_detail
        assert "D69" in month_detail and "D84" in month_detail
        assert "M1.2" in month_detail


def test_full_catalogue_gives_the_product_of_equation_py():
    span = partial_years()
    climate_ = computable_climate(span)
    result = run_computable(climate_=climate_)
    product = expected_product()
    years = covered_ag_years(span)
    assert len(years) > 1
    for item in result.annual:
        if item.ag_year not in years:
            assert item.value is None and item.missing.reason == "NO_COVERAGE"
            continue
        # The same number for every covered year: the variation between
        # years is deferred (USER-G, D69).
        assert item.missing is None
        assert item.value == product
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        assert item.source is not None and not item.assumption
        for pid in module.PARAMETER_IDS:
            assert f"{named(pid).removeprefix('parameter ')}" in item.source
        assert "DECLARED" in item.source and "USER-G" in item.source
        assert item.range is None
        assert item.range_missing.reason == "NOT_AVAILABLE"
    for item in result.monthly:
        if not is_covered(*month_bounds(item.year, item.month), span):
            assert item.value is None and item.missing.reason == "NO_COVERAGE"
            continue
        assert item.missing is None
        assert item.value == pytest.approx(expected_month(item.month), rel=1e-9)
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        assert "climatological monthly fraction" in item.source
        for pid in module.MONTHLY_EROSIVITY_IDS:
            assert f"'{pid}'" in item.source
        assert item.range_missing.reason == "NOT_AVAILABLE"
    # The months of a covered year add up to its value (C1.2).
    for year in years:
        total = sum(item.value for item in result.monthly if item.ag_year == year)
        assert total == pytest.approx(product, rel=1e-9)
    dumped = result.model_dump(mode="json")
    assert SoilLossResults.model_validate_json(json.dumps(dumped)) == result


def test_ls_is_computed_through_ls_py_from_the_catalogue():
    """Every LS record, changed, gives the product of ls.py with the change, on
    both sides of the break slope."""
    slope = computable_soil().slope_steepness.value
    for s_break in (placeholder_values()[module.S_BREAK_ID], slope):
        for pid in (None, *module.LS_IDS):
            numbers = dict(placeholder_values(), **{module.S_BREAK_ID: s_break})
            if pid is not None:
                numbers[pid] += 1
            marked = marked_catalogue()
            for key, number in numbers.items():
                marked[site_key(key)]["value"] = number
            result = run_computable(unmarked(marked))
            assert {item.value for item in result.annual} == {
                expected_product(numbers)
            }, pid


@pytest.mark.parametrize("pid", module.PARAMETER_IDS)
def test_removing_any_one_record_makes_the_year_missing_and_names_it(pid):
    result = run_computable(catalogue(pid))
    for item in result.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(pid)} has no record in parameters (D56)" in item.missing.detail
        for other in module.PARAMETER_IDS:
            if other != pid:
                assert f"'{other}'" not in item.missing.detail
    for item in result.monthly:
        assert item.value is None and item.missing.reason == "MISSING_INPUT"
        assert f"'{pid}'" in item.missing.detail


@pytest.mark.parametrize("pid", module.MONTHLY_EROSIVITY_IDS)
def test_removing_any_one_monthly_erosivity_record_leaves_every_month_missing(pid):
    result = run_computable(catalogue(pid))
    assert all(item.value == expected_product() for item in result.annual)
    for item in result.monthly:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert f"{named(pid)} has no record in parameters (D56)" in detail
        assert module.CLIMATOLOGY_PART in detail
        for other in module.MONTHLY_EROSIVITY_IDS:
            if other != pid:
                assert f"'{other}'" not in detail
        assert "annual product" not in detail


def test_monthly_erosivity_records_in_two_units_or_below_zero_are_not_computed():
    first, second, *_ = module.MONTHLY_EROSIVITY_IDS
    cases = (
        (
            catalogue_with(site_key(second), unit="PLACEHOLDER_other_unit"),
            module.UNIT_NOT_ACCEPTED,
            "different unit strings",
        ),
        (
            catalogue_with(site_key(first), value=-1.0),
            "MISSING_INPUT",
            "below zero",
        ),
    )
    for parameters, reason, text in cases:
        result = run_computable(parameters)
        assert all(item.value == expected_product() for item in result.annual)
        for item in result.monthly:
            assert item.value is None
            assert item.missing.reason == reason
            assert text in item.missing.detail


def test_record_with_null_value_repeats_its_reason():
    cases = (
        (site_key(module.R_ID), named(module.R_ID), False),
        (site_key(module.S_BREAK_ID), named(module.S_BREAK_ID), False),
        (site_key(module.C_ID), named(module.C_ID), False),
        (
            crop_key(module.RESIDUE_MASS_ID, CROP_A),
            named(module.RESIDUE_MASS_ID, {"crop": CROP_A}),
            True,
        ),
    )
    for key, name, daily in cases:
        marked = marked_catalogue()
        record = marked[key]
        record["value"] = None
        record["value_missing_reason"] = "PLACEHOLDER: the source gives no value here"
        parameters = unmarked(marked)
        assert check_catalogue(parameters) == []
        for item in run_computable(parameters, daily=daily).annual:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            detail = item.missing.detail
            assert f"the record of {name} has no value" in detail
            assert unmarked("PLACEHOLDER: the source gives no value here") in detail


def test_record_that_read_value_refuses_is_missing_input():
    marked = marked_catalogue()
    malformed = unmarked(marked)
    del malformed[site_key(module.K_ID)]["unit"]
    cases = {
        module.R_ID: dict(
            unmarked(marked), **{site_key(module.R_ID): marked[site_key(module.R_ID)]}
        ),
        module.K_ID: malformed,
    }
    for pid, parameters in cases.items():
        assert check_catalogue(parameters) != []
        for item in run_computable(parameters).annual:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                f"the record of {named(pid)} is refused by params.catalogue.read_value"
                in item.missing.detail
            )


def test_only_a_record_with_the_empty_scope_is_read():
    parameters = catalogue()
    record = parameters.pop(site_key(module.P_ID))
    parameters["scoped.json"] = dict(record, scope={"management": "UNMARKED_TEST_ONLY"})
    assert check_catalogue(parameters) == []
    for item in run_computable(parameters).annual:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(module.P_ID)} has no record" in item.missing.detail


def test_two_records_with_one_identity_are_missing_input():
    parameters = catalogue()
    parameters["copy.json"] = copy.deepcopy(parameters[site_key(module.C_ID)])
    assert check_catalogue(parameters) != []
    for item in run_computable(parameters).annual:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(module.C_ID)} has more than one record" in item.missing.detail


def test_record_that_cannot_be_compared_is_reported_not_skipped():
    """F3c of params/README.md: a record without a well-formed id and scope is
    named in the detail of every parameter, never read as "no record"."""
    for broken in ({"id": None}, {"scope": None}, {"id": "0PLACEHOLDER"}):
        parameters = catalogue()
        key = site_key(module.K_ID)
        parameters[key] = dict(parameters[key], **unmarked(broken))
        assert check_catalogue(parameters) != []
        for item in run_computable(parameters).annual:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            detail = item.missing.detail
            assert "has no record" not in detail
            for pid in module.PARAMETER_IDS:
                assert (
                    f"{named(pid)} cannot be looked up: the record(s) '{key}'" in detail
                )


def test_slope_unit_that_ls_py_cannot_read_is_not_computed():
    soil_ = soil()  # the example slope unit is a PLACEHOLDER unit
    document = computable_soil_document()
    document["slope_steepness"]["unit"] = soil_.slope_steepness.unit
    marked = marked_catalogue()
    marked[site_key(module.S_BREAK_ID)]["unit"] = "PLACEHOLDER_unit"
    cases = (
        (SiteSoilSlope.model_validate(document), catalogue(), "slope_steepness"),
        (computable_soil(), unmarked(marked), f"parameter '{module.S_BREAK_ID}'"),
    )
    for soil_slope, parameters, what in cases:
        for item in run_computable(parameters, soil_=soil_slope).annual:
            assert item.value is None
            detail = item.missing.detail
            assert (
                f"factor 'ls' is missing (reason {module.UNIT_NOT_ACCEPTED}" in detail
            )
            assert f"of {what} is not one that engine/erosion/ls.py reads" in detail


def test_factor_in_another_unit_is_stopped_by_the_unit_guard():
    for pid, factor in ((module.R_ID, "r"), (module.C_ID, "c")):
        parameters = catalogue_with(site_key(pid), unit="PLACEHOLDER_unit")
        for item in run_computable(parameters).annual:
            assert item.value is None
            assert item.missing.reason == module.UNIT_NOT_ACCEPTED
            assert f"factor '{factor}' is in the unit" in item.missing.detail


def test_c_is_the_declared_record_on_the_main_route_and_not_read_on_the_daily_route():
    numbers = dict(placeholder_values())
    numbers[module.C_ID] += 1
    changed = catalogue_with(site_key(module.C_ID), value=numbers[module.C_ID])
    assert {item.value for item in run_computable(changed).annual} == {
        expected_product(numbers)
    }
    without = catalogue(module.C_ID)
    assert run_daily(without) == run_daily()
    assert run_daily(changed) == run_daily()
    for item in run_daily().annual:
        assert f"'{module.C_ID}'" not in item.source


def test_no_value_is_a_number_unless_every_factor_is_present():
    codes = set(get_args(ReasonCode))
    dry = computable_climate(value_of=lambda day, position: 0.0)
    cases = [
        run(),
        run(climate_=climate(partial_years())),
        run(infeasible_calendar()),
        run(calendar_outside_the_record()),
        run(calendar_without_start_month()),
        run(climate_=climate_with(None)),
        run(soil_=soil_with_missing("slope_steepness", "slope_length")),
        run(soil_=computable_soil(), parameters=catalogue(module.P_ID)),
        run(soil_=soil(), parameters=catalogue()),
        run_computable(catalogue(module.C_ID)),
        run_computable({}),
        run_daily(catalogue((module.RESIDUE_MASS_ID, CROP_B))),
        run_daily(climate_=dry),
        run_daily({}),
    ]
    for result in cases:
        if isinstance(result, Missing):
            assert result.reason in codes
            continue
        for item in result.annual:
            assert item.value is None
            assert item.value != 0
            assert item.missing is not None and item.missing.reason in codes
            assert item.range is None and item.range_missing is None
            assert item.source is None and item.provenance is None


def test_arguments_unchanged_and_second_call_equal():
    for parameters, soil_, climate_, calendar_ in (
        ({}, soil_with_missing("slope_length"), climate(partial_years()), calendar()),
        (
            catalogue(),
            computable_soil(),
            computable_climate(partial_years()),
            computable_calendar(partial_years()),
        ),
    ):
        arguments = {
            "calendar": calendar_,
            "climate": climate_,
            "soil_slope": soil_,
            "parameters": parameters,
        }
        for function in (
            module.compute_soil_loss,
            module.compute_soil_loss_daily_index,
        ):
            before = {name: copy.deepcopy(value) for name, value in arguments.items()}
            first = function(**arguments)
            assert arguments == before
            assert function(**arguments) == first


# --- the daily-index route, off the main path (D69, D84, USER-G) ------------


def test_daily_index_route_gives_the_product_of_r_factor_and_c_factor():
    span = partial_years()
    climate_ = computable_climate(span)
    calendar_ = computable_calendar(span)
    result = run_daily(climate_=climate_, calendar_=calendar_)
    expected = expected_daily_soil_loss(climate_, calendar_)
    assert len(expected) > 1
    assert_numbers(result, expected)
    assert sorted(expected) == [item.ag_year for item in result.annual]
    for item in result.annual:
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        assert "daily-index route, off the main path" in item.source
        for pid in module.DAILY_ROUTE_PARAMETER_IDS:
            assert f"{named(pid).removeprefix('parameter ')}" in item.source
        for crop in CROPS:
            for pid in module.CROP_PARAMETER_IDS:
                text = named(pid, CROP_SCOPES[crop]).removeprefix("parameter ")
                assert text in item.source
        assert "PC-1" in item.source
    for item in result.monthly:
        assert item.value is None
        assert item.missing.reason in {"NOT_AVAILABLE", "NO_COVERAGE"}


def test_daily_index_route_chain_example_gives_r_and_names_residue_before_record():
    """The chain example climate (one agricultural year, the same number every
    day, beginning on the first day of the start month), a complete
    PLACEHOLDER catalogue and a calendar of the same field: R is computed from
    r_factor/ (the expected R and fractions agree with the forms), and C is
    missing, naming the residue before the record: the first cycle of the
    repeated rotation starts in that year (D47) and nothing is laid out before
    it, so the days before its first harvest have no residue (OPEN 2)."""
    climate_document_ = load("chain_site_climate")
    climate_ = SiteClimate.model_validate(climate_document_)
    identity = {key: climate_document_[key] for key in ("case_id", "field_id")}
    soil_ = computable_soil(load("chain_site_soil_slope"))
    (series,) = [s for s in climate_.daily_series if s.quantity == PRECIPITATION]
    span = (series.start_date, series.end_date)
    calendar_ = RotationCalendar.model_validate(
        computable_calendar_document(span, identity)
    )
    result = run_daily(calendar_=calendar_, climate_=climate_, soil_=soil_)
    (item,) = result.annual
    assert item.value is None and item.missing.reason == "MISSING_INPUT"
    detail = item.missing.detail
    assert "factor 'c' is missing" in detail
    assert module.NO_HARVEST_BEFORE in detail
    for factor in ("r", "k", "ls", "p"):
        assert f"factor '{factor}'" not in detail
    numbers = placeholder_values()
    r, fractions = expected_r_and_fractions(climate_, numbers)
    ((year, by_month),) = fractions.items()
    days_in_year = (span[1] - span[0]).days + 1
    for (y, m), fraction in by_month.items():
        first, last = month_bounds(y, m)
        assert fraction == pytest.approx(((last - first).days + 1) / days_in_year)
    assert r[year] == pytest.approx(numbers[module.R_ID])


def test_daily_index_route_empty_catalogue_names_every_record_and_method_part():
    result = run_daily({})
    assert {item.missing.reason for item in result.annual} == {"MISSING_INPUT"}
    for item in result.annual:
        detail = item.missing.detail
        for factor in equation.FACTOR_NAMES:
            assert f"factor '{factor}' is missing" in detail
        for pid in module.DAILY_ROUTE_PARAMETER_IDS:
            assert f"{named(pid)} has no record in parameters (D56)" in detail
        r_part = detail.split("factor 'k'", 1)[0]
        assert "M1.2" in r_part and "engine/erosion/r_factor/" in r_part
        c_part = detail.split("factor 'c' is missing", 1)[1].split("factor 'p'", 1)[0]
        assert "M1.5" in c_part and "D45" in c_part and "PC-1" in c_part
        for pid in module.CANOPY_IDS:
            for word in CROP_SCOPES:
                assert f"{named(pid, CROP_SCOPES[word])} has no record" in c_part
        for pid in module.RESIDUE_IDS:
            for crop in CROPS:
                assert f"{named(pid, CROP_SCOPES[crop])} has no record" in c_part
        assert f"'{module.C_ID}'" not in detail
        for pid in module.MONTHLY_EROSIVITY_IDS:
            assert f"'{pid}'" not in detail


@pytest.mark.parametrize("pid", module.DAILY_ROUTE_PARAMETER_IDS)
def test_daily_index_route_removing_any_one_site_record_names_it(pid):
    for item in run_daily(catalogue(pid)).annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(pid)} has no record in parameters (D56)" in item.missing.detail
        for other in (*module.DAILY_ROUTE_PARAMETER_IDS, *module.CROP_PARAMETER_IDS):
            if other != pid:
                assert f"'{other}'" not in item.missing.detail


@pytest.mark.parametrize("pid, word", list(CROP_VALUES))
def test_removing_any_one_crop_record_makes_c_missing_and_names_it_with_its_scope(
    pid, word
):
    result = run_daily(catalogue((pid, word)))
    part = module.CANOPY_PART if pid in module.CANOPY_IDS else module.RESIDUE_PART
    for item in result.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert "factor 'c' is missing" in detail
        for factor in ("r", "k", "ls", "p"):
            assert f"factor '{factor}'" not in detail
        assert (
            f"{named(pid, CROP_SCOPES[word])} has no record in parameters (D56); "
            f"needed by {part}"
        ) in detail
        for other in module.CROP_PARAMETER_IDS:
            if other != pid:
                assert f"'{other}'" not in detail


def test_crop_without_residue_type_or_canopy_record_leaves_c_missing_and_names_it():
    """Crop B has no decay coefficient (no residue type) and crop A no canopy
    cover: C is missing, never zero, and names both, each with its crop."""
    parameters = catalogue(
        (module.DECAY_COEFFICIENT_ID, CROP_B), (module.CANOPY_COVER_ID, CROP_A)
    )
    for item in run_daily(parameters).annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert "factor 'c' is missing (reason MISSING_INPUT" in detail
        decay = named(module.DECAY_COEFFICIENT_ID, {"crop": CROP_B})
        assert f"{decay} has no record" in detail
        assert "residue decay by residue type" in detail
        canopy = named(module.CANOPY_COVER_ID, {"crop": CROP_A})
        assert f"{canopy} has no record" in detail
        assert "canopy sub-factor" in detail


def test_year_without_an_erosive_day_leaves_r_and_c_missing_for_that_year():
    span = daily_years()
    years = covered_ag_years(span)
    dry = years[1]
    threshold = CHOSEN[module.R_THRESHOLD_ID]

    def value_of(day: dt.date, position: int) -> float:
        # Every day of the dry year at the threshold: no erosive day.
        return threshold if ag_year_of(day) == dry else RAIN[position % len(RAIN)]

    result = run_daily(climate_=computable_climate(span, value_of))
    by_year = {item.ag_year: item for item in result.annual}
    item = by_year[dry]
    assert item.value is None
    assert item.missing.reason == "MISSING_INPUT"
    detail = item.missing.detail
    # r_factor/ gives each month of R as MISSING_INPUT, naming the fraction
    # that is NOT_COMPUTABLE; C names the fractions.
    assert "factor 'r' is missing (reason MISSING_INPUT" in detail
    assert "factor 'c' is missing (reason MISSING_INPUT" in detail
    assert detail.count("no erosive day") >= 2
    for factor in ("k", "ls", "p"):
        assert f"factor '{factor}'" not in detail
    for year in years:
        if year != dry:
            assert by_year[year].value is not None and by_year[year].value != 0


def test_missing_day_in_the_series_makes_its_year_missing_and_no_other():
    span = daily_years()
    years = covered_ag_years(span)
    document = rain_series(*span)
    hole = first_day_of(years[0]) + 40 * ONE_DAY
    for item in document["days"]:
        if item["date"] == hole.isoformat():
            item.update(
                value=None,
                missing={"reason": "NO_COVERAGE", "detail": "PLACEHOLDER: no data"},
            )
    result = run_daily(climate_=climate_with(document))
    by_year = {item.ag_year: item for item in result.annual}
    detail = by_year[years[0]].missing.detail
    assert by_year[years[0]].missing.reason == "MISSING_INPUT"
    assert "factor 'r' is missing" in detail and "factor 'c' is missing" in detail
    assert hole.strftime("%Y-%m") in detail
    for year in years[1:]:
        assert by_year[year].value is not None


def one_year_calendar_document(
    first_ag_year: int, undated_end: bool = False
) -> dict[str, Any]:
    """A one-year calendar of the two crops of ``crop_windows``, in the
    agricultural year ``first_ag_year``; with ``undated_end`` crop B has no end
    date."""
    document = calendar_document()
    document["start_date"] = first_day_of(first_ag_year).isoformat()
    document["end_date"] = last_day_of(first_ag_year).isoformat()
    document["components"] = [
        component(
            f"PLACEHOLDER-c{position}",
            crop_id,
            begins,
            None if undated_end and crop_id == CROP_B else ends,
        )
        for position, (crop_id, begins, ends) in enumerate(
            crop_windows(first_ag_year), start=1
        )
    ]
    return document


def test_no_harvest_before_the_first_cycle_or_an_undated_component_leaves_c_missing():
    span = several_full_years()
    years = covered_ag_years(span)
    # A record that begins on the first day of its first agricultural year:
    # the first cycle starts there and no harvest precedes its first one.
    no_harvest = run_daily(
        climate_=computable_climate(span), calendar_=computable_calendar()
    )
    # A component without an end date, in every cycle of a one-year rotation
    # dated after the record.
    undated = run_daily(
        calendar_=RotationCalendar.model_validate(
            one_year_calendar_document(ag_year_of(span[1]) + 30, undated_end=True)
        )
    )
    cases = (
        (no_harvest, [years[0]], module.NO_HARVEST_BEFORE),
        (undated, years, "'PLACEHOLDER-c2'"),
    )
    for result, missing_years, text in cases:
        for item in result.annual:
            if item.ag_year in missing_years:
                assert item.value is None
                assert item.missing.reason == "MISSING_INPUT"
                assert "factor 'c' is missing" in item.missing.detail
                assert text in item.missing.detail
                assert "day(s) of the year, the first on" in item.missing.detail
            else:
                assert item.value is not None, (text, item.ag_year)


def test_real_dated_calendar_gives_a_value_per_covered_agricultural_year():
    """D47 wired into EP1: a calendar dated after the record runs on the years
    of the record. A one-year calendar and the multi-year computable calendar,
    both moved past the record, give on the daily-index route a number for
    every covered agricultural year, the product of R and of C from the
    rotation repeated over the record, computed again here; the main route
    gives its number for every covered year too."""
    span = daily_years()
    climate_ = computable_climate(span)
    years = covered_ag_years(span)
    one_year = RotationCalendar.model_validate(
        one_year_calendar_document(ag_year_of(span[1]) + 23)
    )
    several = moved_past(computable_calendar_document(), span[1])
    for calendar_ in (one_year, several):
        assert calendar_.start_date > span[1]
        result = run_daily(calendar_=calendar_)
        expected = expected_daily_soil_loss(climate_, calendar_)
        assert sorted(expected) == years
        assert_numbers(result, expected)
        main = run_computable(calendar_=calendar_, climate_=climate_)
        for item in main.annual:
            assert (item.value is not None) == (item.ag_year in years)
    # The multi-year calendar moved by whole leap cycles is laid back on the
    # record unchanged, so it gives what it gives on the record.
    assert run_daily(calendar_=several) == run_daily()


def test_unit_strings_of_c_records_that_are_not_read_are_not_computed():
    cases = {
        "canopy cover not dimensionless": (
            catalogue_with(
                crop_key(module.CANOPY_COVER_ID, NO_CROP), unit="PLACEHOLDER_percent"
            ),
            f"of parameter '{module.CANOPY_COVER_ID}' with scope "
            f"{json.dumps(module.NO_CROP_SCOPE)} is not '{module.DIMENSIONLESS}'",
        ),
        "decay coefficient not an inverse": (
            catalogue_with(
                crop_key(module.DECAY_COEFFICIENT_ID, CROP_A), unit=module.DAY
            ),
            f"of parameter '{module.DECAY_COEFFICIENT_ID}' with scope "
            f"{json.dumps({'crop': CROP_A})} is not read as the inverse of a unit",
        ),
        "b of S1 Eq. 6.6 not per percent": (
            catalogue_with(
                site_key(module.SURFACE_COVER_B_PER_PERCENT_ID),
                unit=module.DIMENSIONLESS,
            ),
            f"of parameter '{module.SURFACE_COVER_B_PER_PERCENT_ID}' is not "
            f"'{module.PERCENT}-1'",
        ),
        "fall height and coefficient in two units": (
            catalogue_with(
                site_key(module.FALL_HEIGHT_COEFFICIENT_ID),
                unit="PLACEHOLDER_other_height_unit-1",
            ),
            "canopy_subfactor of engine/erosion/c_factor/",
        ),
    }
    for name, (parameters, text) in cases.items():
        assert check_catalogue(parameters) == [], name
        for item in run_daily(parameters).annual:
            assert item.value is None, name
            detail = item.missing.detail
            assert (
                f"factor 'c' is missing (reason {module.UNIT_NOT_ACCEPTED}" in detail
            ), name
            assert unmarked(text) in detail, name


def test_value_c_factor_refuses_is_not_computed_and_names_the_day():
    parameters = catalogue_with(crop_key(module.CANOPY_COVER_ID, CROP_A), value=1.5)
    for item in run_daily(parameters).annual:
        assert item.value is None
        detail = item.missing.detail
        assert "factor 'c' is missing (reason NOT_COMPUTABLE" in detail
        assert "effective_canopy_cover of engine/erosion/c_factor/" in detail
        assert "canopy_cover" in detail and "outside zero to one" in detail
        assert re.search(r"on \d{4}-\d\d-\d\d, effective_canopy_cover", detail)


def test_r_level_threshold_or_series_in_another_unit_is_refused_by_r_factor():
    document = rain_series(*daily_years())
    document["unit"] = unmarked("PLACEHOLDER_unit")
    cases = (
        (
            catalogue_with(site_key(module.R_ID), unit="PLACEHOLDER_unit"),
            computable_climate(daily_years()),
            ["r"],
        ),
        (
            catalogue_with(site_key(module.R_THRESHOLD_ID), unit="PLACEHOLDER_unit"),
            computable_climate(daily_years()),
            ["r", "c"],
        ),
        (catalogue(), climate_with(document), ["r", "c"]),
    )
    for parameters, climate_, factors in cases:
        for item in run_daily(parameters, climate_=climate_).annual:
            assert item.value is None
            detail = item.missing.detail
            assert unmarked("PLACEHOLDER_unit") in detail
            for factor in ("r", "k", "ls", "c", "p"):
                assert (f"factor '{factor}' is missing" in detail) == (
                    factor in factors
                ), (factor, detail)


def test_per_unit_reads_only_the_proposed_inverse_forms():
    read = {"day-1": "day", "m-1": "m", "(kg m-2)-1": "kg m-2", "(m)-1": "m"}
    for unit, base in read.items():
        assert module._per_unit(unit) == base, unit
    for unit in ("day", "kg m-2-1", "-1", "()-1", "( )-1", "m-2", "m-1 ", "(m-1"):
        assert module._per_unit(unit) is None, unit


def test_month_that_is_not_a_number_is_named_not_dropped():
    """A table of r_factor/ whose month is absent, None or not a number: the
    year is missing, naming each such month; nothing is dropped silently."""
    start = start_month()
    year = example_start().year
    months = months_of(year)
    cells: dict[tuple[int, int], Any] = {m: 1.5 for m in months}
    del cells[months[0]]
    cells[months[1]] = None
    cells[months[2]] = "PLACEHOLDER"
    cells[months[3]] = Missing(reason="NO_COVERAGE", detail="PLACEHOLDER: none")
    table = module._year_table({year: cells}, year, start, "R by month", "the table")
    assert isinstance(table, Missing)
    assert table.reason == "MISSING_INPUT"  # two reasons among the months
    for y, m in months[:4]:
        assert dt.date(y, m, 1).strftime("%Y-%m") in table.detail
    assert "holds a str for the month, not a number" in table.detail
    del cells[months[3]]
    cells[months[2]] = 2.5
    only_absent = module._year_table({year: cells}, year, start, "R", "the table")
    assert isinstance(only_absent, Missing)
    assert only_absent.reason == "NOT_COMPUTABLE"
    whole = module._year_table(
        {year: {m: 1.5 for m in months}}, year, start, "R", "the table"
    )
    assert whole == {m: 1.5 for m in months}


# --- C on the main route (unit l0/erosion-c-main-route, issue #218; D129) ----

# The crops of the two rotations of the demonstration (D128), as PLACEHOLDER
# crop identifiers: soybean with winter fallow, against soybean-wheat-maize.
SOY = unmarked("PLACEHOLDER-soybean")
WHEAT = unmarked("PLACEHOLDER-wheat")
MAIZE = unmarked("PLACEHOLDER-maize")
DEMO_CROPS = (SOY, WHEAT, MAIZE)

# PLACEHOLDER days after planting of the series of D129, not the days of any
# table, and PLACEHOLDER numbers on them: repeated digits, a canopy cover a
# fraction. Not values of the method.
STAGE_DAYS = (11, 22, 44)
C_SERIES: dict[tuple[str, str], tuple[float, ...]] = {
    (module.CANOPY_COVER_ID, SOY): (0.111, 0.555, 0.333),
    (module.CANOPY_COVER_ID, WHEAT): (0.222, 0.444, 0.666),
    (module.CANOPY_COVER_ID, MAIZE): (0.333, 0.777, 0.555),
    (module.FALL_HEIGHT_ID, SOY): (1.11, 2.22, 3.33),
    (module.FALL_HEIGHT_ID, WHEAT): (0.555, 1.11, 2.22),
    (module.FALL_HEIGHT_ID, MAIZE): (2.22, 3.33, 4.44),
}
# PLACEHOLDER numbers of the residue records by crop (D129 (b), (c)).
C_RESIDUE: dict[tuple[str, str], float] = {
    (module.RESIDUE_YIELD_RATIO_ID, SOY): 1.11,
    (module.RESIDUE_YIELD_RATIO_ID, WHEAT): 2.22,
    (module.RESIDUE_YIELD_RATIO_ID, MAIZE): 1.11,
    (module.CROP_YIELD_ID, SOY): 5.55,
    (module.CROP_YIELD_ID, WHEAT): 4.44,
    (module.CROP_YIELD_ID, MAIZE): 6.66,
    (module.DECAY_COEFFICIENT_ID, SOY): 0.0333,
    (module.DECAY_COEFFICIENT_ID, WHEAT): 0.0222,
    (module.DECAY_COEFFICIENT_ID, MAIZE): 0.0111,
    (module.MASS_COVER_COEFFICIENT_ID, SOY): 0.0555,
    (module.MASS_COVER_COEFFICIENT_ID, WHEAT): 0.0444,
    (module.MASS_COVER_COEFFICIENT_ID, MAIZE): 0.0333,
}
YIELD_UNIT = "PLACEHOLDER_yield_unit"
# The yield of these crops is in YIELD_UNIT, so the conversion record turns it
# into MASS_UNIT; the yield of maize is already in MASS_UNIT and needs none.
CONVERTED = (SOY, WHEAT)
CONVERSION = 0.777  # PLACEHOLDER, not a conversion factor of any two units
CONVERSION_UNIT = f"{MASS_UNIT}{module.CONVERSION_SEPARATOR}{YIELD_UNIT}"


def stage_word(days: int) -> str:
    return f"{module.STAGE_PREFIX}{days}"


def c_residue_unit(pid: str, crop: str) -> str:
    return {
        module.RESIDUE_YIELD_RATIO_ID: module.DIMENSIONLESS,
        module.CROP_YIELD_ID: YIELD_UNIT if crop in CONVERTED else MASS_UNIT,
        module.DECAY_COEFFICIENT_ID: f"{module.DAY}-1",
        module.MASS_COVER_COEFFICIENT_ID: f"({MASS_UNIT})-1",
    }[pid]


def c_records() -> dict[str, dict]:
    """The records of the computed C of the main route, still marked."""
    records: dict[str, dict] = {}
    for (pid, crop), numbers in C_SERIES.items():
        unit = crop_unit_of(pid)
        for days, number in zip(STAGE_DAYS, numbers):
            word = stage_word(days)
            records[crop_key(pid, f"{crop}.{word}")] = placeholder_record(
                pid, number, unit, {"crop": crop, "stage": word}
            )
    for (pid, crop), number in C_RESIDUE.items():
        records[crop_key(pid, crop)] = placeholder_record(
            pid, number, c_residue_unit(pid, crop), {"crop": crop}
        )
    records[site_key(module.YIELD_CONVERSION_ID)] = placeholder_record(
        module.YIELD_CONVERSION_ID, CONVERSION, CONVERSION_UNIT
    )
    return records


def marked_c_catalogue(*leave_out: str) -> dict[str, dict]:
    """The complete catalogue with the records of the computed C, marked;
    ``leave_out`` names records by their key."""
    records = {**marked_catalogue(), **c_records()}
    return {key: record for key, record in records.items() if key not in leave_out}


def c_catalogue(*leave_out: str) -> dict[str, dict]:
    built = unmarked(marked_c_catalogue(*leave_out))
    assert check_catalogue(built) == []
    return built


def c_catalogue_with(key: str, **fields: Any) -> dict[str, dict]:
    marked = marked_c_catalogue()
    marked[key].update(fields)
    return unmarked(marked)


def demo_window(
    ag_year: int, first: int, last: int, crop: str
) -> tuple[str, dt.date, dt.date]:
    """A crop from the first day of month position ``first`` of an agricultural
    year to the last day of month position ``last`` (positions from zero)."""
    month = start_month()

    def month_of(position: int) -> tuple[int, int]:
        index = ag_year * 12 + month - 1 + position
        return index // 12, index % 12 + 1

    return crop, dt.date(*month_of(first), 1), month_bounds(*month_of(last))[1]


def demo_calendar(rotation: str, first_ag_year: int) -> RotationCalendar:
    """A PLACEHOLDER calendar of one demonstration rotation (D128), its first
    agricultural year ``first_ag_year``. Soybean with winter fallow: one year,
    soybean and then no crop. Soybean-wheat-maize: two years, wheat then
    soybean, then maize. The month positions are PLACEHOLDER dates."""
    if rotation == "soybean-winter-fallow":
        years = 1
        windows = [demo_window(first_ag_year, 4, 9, SOY)]
    else:
        years = 2
        windows = [
            demo_window(first_ag_year, 0, 4, WHEAT),
            demo_window(first_ag_year, 5, 9, SOY),
            demo_window(first_ag_year + 1, 2, 8, MAIZE),
        ]
    document = calendar_document()
    document["start_date"] = first_day_of(first_ag_year).isoformat()
    document["end_date"] = last_day_of(first_ag_year + years - 1).isoformat()
    document["components"] = [
        component(f"PLACEHOLDER-c{position}", crop, begins, ends)
        for position, (crop, begins, ends) in enumerate(windows, start=1)
    ]
    return RotationCalendar.model_validate(document)


DEMO_ROTATIONS = ("soybean-winter-fallow", "soybean-wheat-maize")


def run_demo(
    rotation: str, parameters: dict[str, dict] | None = None, **arguments: Any
) -> SoilLossResults:
    """The main route on the record of ``daily_years``, whose first,
    partly covered agricultural year is the calendar's first year."""
    span = daily_years()
    arguments.setdefault("climate_", computable_climate(span))
    arguments.setdefault("calendar_", demo_calendar(rotation, ag_year_of(span[0])))
    return run_computable(
        c_catalogue() if parameters is None else parameters, **arguments
    )


def on_series(days: tuple[int, ...], numbers: tuple[float, ...], day: int) -> float:
    """The PROPOSED reading of a series (OPEN 29), computed again: linear
    between two of its days, its first value before them, its last after."""
    if day <= days[0]:
        return numbers[0]
    if day >= days[-1]:
        return numbers[-1]
    for (d0, v0), (d1, v1) in zip(zip(days, numbers), zip(days[1:], numbers[1:])):
        if d0 <= day <= d1:
            return v0 + (v1 - v0) * (day - d0) / (d1 - d0)
    raise AssertionError(day)


def expected_main_ratio(
    day: dt.date,
    windows: list[tuple[str, dt.date, dt.date]],
    numbers: dict[str, float],
) -> float:
    """The soil-loss ratio of one day of the main route, by the forms of
    c_factor/README.md under PC-1 and the design of D129."""
    covering = [(crop, start) for crop, start, end in windows if start <= day <= end]
    if covering:
        ((crop, start),) = covering
        after = (day - start).days
        canopy_cover = on_series(
            STAGE_DAYS, C_SERIES[(module.CANOPY_COVER_ID, crop)], after
        )
        height = on_series(STAGE_DAYS, C_SERIES[(module.FALL_HEIGHT_ID, crop)], after)
    else:
        canopy_cover = CROP_VALUES[(module.CANOPY_COVER_ID, NO_CROP)]
        height = CROP_VALUES[(module.FALL_HEIGHT_ID, NO_CROP)]
    harvest, _, harvest_end = max(
        (w for w in windows if w[2] < day), key=lambda w: w[2]
    )
    mass = (
        C_RESIDUE[(module.RESIDUE_YIELD_RATIO_ID, harvest)]
        * C_RESIDUE[(module.CROP_YIELD_ID, harvest)]
        * (CONVERSION if harvest in CONVERTED else 1.0)
    )
    mass *= math.exp(
        -C_RESIDUE[(module.DECAY_COEFFICIENT_ID, harvest)] * (day - harvest_end).days
    )
    residue_cover = 1 - math.exp(
        -C_RESIDUE[(module.MASS_COVER_COEFFICIENT_ID, harvest)] * mass
    )
    surface = math.exp(
        -numbers[module.SURFACE_COVER_B_PER_PERCENT_ID] * residue_cover * 100
    )
    effective = canopy_cover * (1 - residue_cover)
    canopy = 1 - effective * math.exp(
        -numbers[module.FALL_HEIGHT_COEFFICIENT_ID] * height
    )
    return canopy * surface


def expected_main_c(
    calendar_: RotationCalendar, climate_: SiteClimate
) -> dict[int, float]:
    """C of every covered year: the mean daily ratio of each month, weighted by
    the share of its calendar month in the twelve monthly records, one year."""
    numbers = placeholder_values()
    monthly = [numbers[pid] for pid in module.MONTHLY_EROSIVITY_IDS]
    span = series_span(climate_)
    windows = repeated_windows(calendar_, span)
    result = {}
    for year in covered_ag_years(span):
        c = 0.0
        for y, m in months_of(year):
            ratios = [
                expected_main_ratio(day, windows, numbers)
                for day in days_between(*month_bounds(y, m))
            ]
            c += monthly[m - 1] / sum(monthly) * sum(ratios) / len(ratios)
        result[year] = c
    return result


def product_with_c(c: float) -> float:
    numbers = dict(placeholder_values(), **{module.C_ID: c})
    return expected_product(numbers)


def covered_only(result: SoilLossResults, span: tuple[dt.date, dt.date]) -> dict:
    years = covered_ag_years(span)
    return {item.ag_year: item for item in result.annual if item.ag_year in years}


def test_computed_c_tells_the_two_demonstration_rotations_apart():
    """With a PLACEHOLDER catalogue holding the records of the computed C, the
    two rotations of D128 give different soil loss; each covered year equals
    R K LS C P with C computed again here (D129), and its months add up to it."""
    span = daily_years()
    climate_ = computable_climate(span)
    by_rotation = {}
    for rotation in DEMO_ROTATIONS:
        calendar_ = demo_calendar(rotation, ag_year_of(span[0]))
        result = run_demo(rotation, climate_=climate_, calendar_=calendar_)
        expected = {
            year: product_with_c(c)
            for year, c in expected_main_c(calendar_, climate_).items()
        }
        years = covered_only(result, span)
        assert sorted(years) == sorted(expected) and len(years) > 1
        for year, item in years.items():
            assert item.missing is None, item.missing
            assert item.value == pytest.approx(expected[year], rel=1e-9), year
            assert item.provenance == PROVENANCE_OF_SOIL_LOSS
            assert module.COMPUTED_C in item.source
            assert "fallback" not in item.source
            assert f"'{module.C_ID}' with scope" not in item.source
            for crop in {SOY} if rotation == DEMO_ROTATIONS[0] else set(DEMO_CROPS):
                assert f"'{module.CROP_YIELD_ID}' with scope" in item.source
                assert json.dumps({"crop": crop}) in item.source
            months = [m for m in result.monthly if m.ag_year == year]
            assert sum(m.value for m in months) == pytest.approx(item.value, rel=1e-9)
            c = expected[year] / product_with_c(1.0)
            for month in months:
                assert month.value == pytest.approx(
                    expected_month(
                        month.month, dict(placeholder_values(), **{module.C_ID: c})
                    ),
                    rel=1e-9,
                )
        by_rotation[rotation] = {year: item.value for year, item in years.items()}
    first, second = (by_rotation[rotation] for rotation in DEMO_ROTATIONS)
    assert first.keys() == second.keys()
    assert all(first[year] != pytest.approx(second[year]) for year in first)
    # The conversion record is read for the crops whose yield needs it only.
    assert (
        f"'{module.YIELD_CONVERSION_ID}'"
        in run_demo(DEMO_ROTATIONS[0]).annual[1].source
    )


def test_without_the_c_records_c_is_the_declared_record_and_the_source_says_so():
    """Without the records of the computed C, C is the declared rusle_c_factor
    (M1.2, D125) for every year and every rotation, by the PROPOSED fallback,
    and the source says so and names what is missing."""
    span = daily_years()
    for rotation in DEMO_ROTATIONS:
        result = run_demo(rotation, parameters=catalogue())
        for item in covered_only(result, span).values():
            assert item.value == expected_product()
            assert "PROPOSED fallback of brief #218" in item.source
            assert "DECLARED" in item.source and "D125" in item.source
            assert f"'{module.C_ID}' with scope {{}}" in item.source
            stage = {"crop": SOY, "stage": module.STAGE_SHOWN}
            assert (
                f"{named(module.CANOPY_COVER_ID, stage)} has no record" in item.source
            )
            assert module.COMPUTED_C not in item.source


def c_record_keys() -> list[str]:
    """One key per kind of record of the computed C, to leave out in turn."""
    return [
        site_key(module.FALL_HEIGHT_COEFFICIENT_ID),
        site_key(module.SURFACE_COVER_B_PER_PERCENT_ID),
        site_key(module.YIELD_CONVERSION_ID),
        site_key(module.MONTHLY_EROSIVITY_IDS[0]),
        crop_key(module.CANOPY_COVER_ID, NO_CROP),
        crop_key(module.FALL_HEIGHT_ID, NO_CROP),
        *(crop_key(pid, SOY) for pid in module.MAIN_C_RESIDUE_IDS),
    ]


def fallback_missing_part(source: str) -> str:
    """The list of missing records that the source of a fallback gives."""
    return source.split(module.DECLARED_C, 1)[1].split("; LS from", 1)[0]


def assert_fallback(parameters: dict[str, dict], text: str) -> None:
    result = run_demo(DEMO_ROTATIONS[0], parameters=parameters)
    for item in covered_only(result, daily_years()).values():
        assert item.value == expected_product()
        assert "PROPOSED fallback of brief #218" in item.source
        missing = fallback_missing_part(item.source)
        assert text in missing, missing
        assert missing.count("parameter '") == 1, missing


@pytest.mark.parametrize("key", c_record_keys())
def test_one_missing_c_record_falls_back_and_names_it(key):
    """Each record of the computed C, left out or with a null value: C is the
    declared record for every year and the source names that record, and no
    other, as missing."""
    record = unmarked(marked_c_catalogue()[key])
    name = named(record["id"], record["scope"])
    reason = unmarked(f"{WORD}: the source gives no value here")
    assert_fallback(c_catalogue(key), f"{name} has no record in parameters (D56)")
    nulled = c_catalogue_with(key, value=None, value_missing_reason=reason)
    assert_fallback(nulled, f"the record of {name} has no value: {reason}")


def test_missing_stage_series_falls_back_and_a_shorter_series_does_not():
    """Every stage record of one canopy series of a crop left out: the fallback
    names the series by its scope with day_<N>. One stage record with a null
    value: the fallback names it. One stage record left out: the series is
    shorter, not missing, and C is computed from the days that remain
    (OPEN 30)."""
    prefix = f"{module.CANOPY_COVER_ID}.{SOY}."
    keys = [key for key in marked_c_catalogue() if key.startswith(prefix)]
    assert len(keys) == len(STAGE_DAYS)
    stage = {"crop": SOY, "stage": module.STAGE_SHOWN}
    assert_fallback(
        c_catalogue(*keys), f"{named(module.CANOPY_COVER_ID, stage)} has no record"
    )
    record = unmarked(marked_c_catalogue()[keys[0]])
    reason = unmarked(f"{WORD}: the source gives no value here")
    nulled = c_catalogue_with(keys[0], value=None, value_missing_reason=reason)
    name = named(module.CANOPY_COVER_ID, record["scope"])
    assert_fallback(nulled, f"the record of {name} has no value: {reason}")
    shorter = run_demo(DEMO_ROTATIONS[0], parameters=c_catalogue(keys[0]))
    for item in covered_only(shorter, daily_years()).values():
        assert item.value is not None and module.COMPUTED_C in item.source


def test_c_record_units_that_disagree_make_c_missing_and_name_the_records():
    """A unit mismatch among the records of the computed C is not a missing
    record: C of every covered year is missing with the unit-guard reason,
    naming the records involved, and the fallback does not apply."""
    soy = {"crop": SOY}
    word = stage_word(STAGE_DAYS[1])
    cases = {
        "yield unit that the conversion does not convert": (
            c_catalogue_with(
                crop_key(module.CROP_YIELD_ID, SOY), unit="PLACEHOLDER_other_unit"
            ),
            [
                named(module.CROP_YIELD_ID, soy),
                named(module.MASS_COVER_COEFFICIENT_ID, soy),
                named(module.YIELD_CONVERSION_ID),
            ],
        ),
        "conversion not written '<to> per <from>'": (
            c_catalogue_with(site_key(module.YIELD_CONVERSION_ID), unit=MASS_UNIT),
            [named(module.YIELD_CONVERSION_ID)],
        ),
        "ratio not dimensionless": (
            c_catalogue_with(
                crop_key(module.RESIDUE_YIELD_RATIO_ID, SOY), unit="PLACEHOLDER_unit"
            ),
            [named(module.RESIDUE_YIELD_RATIO_ID, soy)],
        ),
        "alpha not the inverse of a unit": (
            c_catalogue_with(
                crop_key(module.MASS_COVER_COEFFICIENT_ID, SOY), unit=MASS_UNIT
            ),
            [named(module.MASS_COVER_COEFFICIENT_ID, soy)],
        ),
        "a series in two unit strings": (
            c_catalogue_with(
                crop_key(module.FALL_HEIGHT_ID, f"{SOY}.{word}"),
                unit="PLACEHOLDER_other_height_unit",
            ),
            [f"parameter '{module.FALL_HEIGHT_ID}' for crop '{SOY}'"],
        ),
        "canopy cover not dimensionless": (
            c_catalogue_with(
                crop_key(module.CANOPY_COVER_ID, f"{SOY}.{word}"),
                unit="PLACEHOLDER_unit",
            ),
            [f"parameter '{module.CANOPY_COVER_ID}' for crop '{SOY}'"],
        ),
    }
    span = daily_years()
    for case, (parameters, texts) in cases.items():
        result = run_demo(DEMO_ROTATIONS[0], parameters=parameters)
        for item in covered_only(result, span).values():
            assert item.value is None, case
            detail = item.missing.detail
            assert (
                f"factor 'c' is missing (reason {module.UNIT_NOT_ACCEPTED}" in detail
            ), case
            assert module.NO_FALLBACK in detail, case
            for text in texts:
                assert text in detail, (case, text)


def test_stage_series_is_read_between_and_beyond_its_days():
    """The PROPOSED reading of a series by days after planting (OPEN 29), and
    which stage words are read: ``day_<N>`` with N in ASCII digits."""
    points = tuple(
        module._Point(day=d, value=v)
        for d, v in zip(STAGE_DAYS, C_SERIES[(module.CANOPY_COVER_ID, SOY)])
    )
    series = module._Series(points=points, unit=module.DIMENSIONLESS)
    numbers = C_SERIES[(module.CANOPY_COVER_ID, SOY)]
    for day in (0, 1, STAGE_DAYS[0], 16, STAGE_DAYS[1], 33, STAGE_DAYS[2], 400):
        assert module._on_series(series, day) == pytest.approx(
            on_series(STAGE_DAYS, numbers, day)
        ), day
    one = module._Series(points=(module._Point(day=7, value=0.555),), unit="x")
    assert {module._on_series(one, day) for day in (0, 7, 99)} == {0.555}
    assert module._days_after_planting("day_11") == 11
    assert module._days_after_planting("day_0") == 0
    for word in ("day_", "day_x", "day_-1", "day_1.5", "stage_11", "day_１", "11"):
        assert module._days_after_planting(word) is None, word
    # A stage word that is not day_<N>: C is not computed, no fallback.
    marked = marked_c_catalogue()
    record = copy.deepcopy(marked[crop_key(module.CANOPY_COVER_ID, f"{SOY}.day_11")])
    record["scope"]["stage"] = "PLACEHOLDER_flowering"
    marked["extra.json"] = record
    result = run_demo(DEMO_ROTATIONS[0], parameters=unmarked(marked))
    for item in covered_only(result, daily_years()).values():
        assert item.value is None
        assert "is not read" in item.missing.detail
        assert module.NO_FALLBACK in item.missing.detail


def test_year_without_a_last_harvest_leaves_only_its_c_missing_without_fallback():
    """A record that begins on the first day of its first agricultural year:
    the first cycle has no harvest before its first one, so C of that year is
    missing (OPEN 2) and every other covered year is computed; the records are
    all present, so the fallback does not apply."""
    span = several_full_years()
    climate_ = computable_climate(span)
    calendar_ = demo_calendar(DEMO_ROTATIONS[1], ag_year_of(span[0]))
    result = run_demo(DEMO_ROTATIONS[1], climate_=climate_, calendar_=calendar_)
    years = covered_ag_years(span)
    by_year = {item.ag_year: item for item in result.annual}
    first = by_year[years[0]]
    assert first.value is None
    assert module.NO_HARVEST_BEFORE in first.missing.detail
    assert module.NO_FALLBACK in first.missing.detail
    for year in years[1:]:
        assert by_year[year].value is not None
        assert module.COMPUTED_C in by_year[year].source


RECORDS = ROOT / "params" / "records"
# The 61 records that only the computed C reads, taken out of the catalogue
# the service loads (D148, D158 and D164 of issue #77; unit
# l0/computed-c-out-of-catalogue). The six the residue ledger (EP4) also reads,
# the residue/yield ratio and the yield of each crop, stay in the catalogue
# (D164), under params/records/residues/.
WITHDRAWN_C_RECORDS = ROOT / "params" / "withdrawn" / "computed_c"
DEMO_SOIL = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"


# The crop words of the records of the computed C (unit l0/c-records): the
# crop_id of the demonstration calendars of D128 must be the same words.
REPOSITORY_CROP_WORDS = {SOY: "soybean", WHEAT: "wheat", MAIZE: "maize"}

# The headline soil loss of the demonstration point as decisions D146 and D148
# of issue #77 print it, in t ha-1 yr-1, to the three decimals they give.
# Transcribed from the decisions, not computed here.
HEADLINE_SOIL_LOSS_D148 = 2.365


def service_catalogue() -> dict[str, dict]:
    """The catalogue the service loads: every record under params/records/,
    as ``load_folder`` returns it (api/config.py), loaded and checked."""
    records, problems = load_folder(RECORDS)
    assert problems == [] and check_catalogue(records) == []
    return records


def withdrawn_c_records() -> dict[str, dict]:
    """The records of params/withdrawn/computed_c/, loaded by the path of that
    folder and checked, keyed from params/."""
    records, problems = load_folder(WITHDRAWN_C_RECORDS)
    assert problems == [] and check_catalogue(records) == []
    return {f"withdrawn/computed_c/{name}": record for name, record in records.items()}


def computed_c_ids() -> set[str]:
    """Every identifier only the computed C of the main route reads."""
    return {
        *module.MAIN_C_CROP_ONLY_IDS,
        *module.MAIN_C_SITE_ONLY_IDS,
        *module.CANOPY_IDS,
        *module.MAIN_C_RESIDUE_IDS,
        *module.MAIN_C_SITE_IDS,
    }


def repository_demo_inputs() -> tuple[
    SiteSoilSlope, SiteClimate, dict[str, RotationCalendar]
]:
    """The demonstration soil file, a computable record of ``daily_years``
    with its identity, and both rotations of D128 as the PLACEHOLDER calendars
    of ``demo_calendar``, their crops carrying the words of the records."""
    soil_document_ = json.loads(DEMO_SOIL.read_text("utf-8"))
    identity = {k: soil_document_[k] for k in ("case_id", "field_id")}
    climate_document_ = climate_document()
    climate_document_.update(identity)
    span = daily_years()
    calendars = {}
    for rotation in DEMO_ROTATIONS:
        document = demo_calendar(rotation, ag_year_of(span[0])).model_dump(mode="json")
        document.update(identity)
        for item in document["components"]:
            item["crop_id"] = REPOSITORY_CROP_WORDS[item["crop_id"]]
        calendars[rotation] = RotationCalendar.model_validate(document)
    return (
        SiteSoilSlope.model_validate(soil_document_),
        climate_with(rain_series(*span), climate_document_),
        calendars,
    )


def repository_declared_product(
    records: dict[str, dict], soil_: SiteSoilSlope
) -> float:
    """R K LS C P of the main route with the declared C (D125), computed again
    from the records of the repository with the empty scope, each in the unit
    its record states, and the slope of ``soil_``, through equation.py and
    ls.py, without calling the entry point."""
    by_id = {r["id"]: r for r in records.values() if r["scope"] == {}}

    def number(pid: str) -> float:
        value = read_value(by_id[pid])
        assert isinstance(value, float), pid
        return value

    def factor(pid: str) -> equation.Factor:
        return equation.Factor(number(pid), by_id[pid]["unit"])

    slope_unit = ls.SlopeUnit(soil_.slope_steepness.unit)
    steepness = ls.slope_steepness_factor(
        slope_steepness=soil_.slope_steepness.value,
        slope_unit=slope_unit,
        s_break=number(module.S_BREAK_ID),
        s_break_unit=ls.SlopeUnit(by_id[module.S_BREAK_ID]["unit"]),
        **{name: number(pid) for name, pid in module.S_COEFFICIENTS.items()},
    )
    length = ls.slope_length_factor(
        slope_length=soil_.slope_length.value,
        slope_length_unit=soil_.slope_length.unit,
        lambda_unit=number(module.LAMBDA_UNIT_ID),
        lambda_unit_unit=by_id[module.LAMBDA_UNIT_ID]["unit"],
        slope_steepness=soil_.slope_steepness.value,
        slope_unit=slope_unit,
        **{name: number(pid) for name, pid in module.L_COEFFICIENTS.items()},
    )
    assert isinstance(steepness, float) and isinstance(length, float)
    accepted = module.ACCEPTED_UNITS
    product = equation.annual_soil_loss(
        r=factor(module.R_ID),
        k=factor(module.K_ID),
        ls=equation.Factor(length * steepness, accepted.ls),
        c=factor(module.C_ID),
        p=factor(module.P_ID),
        accepted_units=accepted,
        unit_guard_reason=module.UNIT_NOT_ACCEPTED,
    )
    assert isinstance(product, float)
    return product


def test_service_catalogue_gives_the_declared_c_for_both_demo_rotations_in_every_phase():
    """The catalogue the service loads, params/records/, holds none of the
    withdrawn records of the computed C (D148, D158). It holds six of the
    computed C's records, the residue/yield ratio and the yield of each crop,
    because the residue ledger reads them too (D164): a C is not computed from
    those alone. With it, the demonstration soil file and both rotations of
    D128, their crops carrying the words of the records, every covered year of
    every phase (D109, D141) is the declared product: R K LS C P with the
    declared rusle_c_factor (D125), computed again here from the records; the
    source says DECLARED, D125 and the fallback, never the computed C, and
    names as missing the withdrawn records and not the six that are present.
    That product is the headline figure D146 and D148 print, to the decimals
    they give."""
    records = service_catalogue()
    c_only_ids = {record["id"] for record in withdrawn_c_records().values()}
    assert c_only_ids
    assert c_only_ids.isdisjoint(record["id"] for record in records.values())
    # D164: of the identifiers of the computed C, the catalogue holds the two
    # the residue ledger reads, for each crop of D128, and no other.
    kept_ids = set(module.MAIN_C_CROP_ONLY_IDS)
    assert computed_c_ids() - c_only_ids == kept_ids
    kept = [record for record in records.values() if record["id"] in computed_c_ids()]
    assert all(set(record["scope"]) == {"crop"} for record in kept)
    assert sorted((r["id"], r["scope"]["crop"]) for r in kept) == sorted(
        (pid, crop) for pid in kept_ids for crop in REPOSITORY_CROP_WORDS.values()
    )
    soil_, climate_, calendars = repository_demo_inputs()
    expected = repository_declared_product(records, soil_)
    assert round(expected, 3) == HEADLINE_SOIL_LOSS_D148
    span = daily_years()
    phases_of = {}
    for rotation, calendar_ in calendars.items():
        phases_of[rotation] = list_phases(calendar_)
        for phase in phases_of[rotation]:
            result = run(phase_calendar(calendar_, phase), climate_, soil_, records)
            assert isinstance(result, SoilLossResults)
            covered = covered_only(result, span)
            assert sorted(covered) == covered_ag_years(span) and len(covered) > 1
            for item in covered.values():
                where = (rotation, phase, item.ag_year)
                assert item.missing is None, (where, item.missing)
                assert item.value == expected, where
                assert item.provenance == PROVENANCE_OF_SOIL_LOSS
                assert "PROPOSED fallback of brief #218" in item.source, where
                assert "DECLARED" in item.source and "D125" in item.source
                assert f"'{module.C_ID}' with scope {{}}" in item.source
                assert module.COMPUTED_C not in item.source, where
                # The fallback names what is missing: records of the withdrawn
                # identifiers, and none of the six that are present.
                missing = fallback_missing_part(item.source)
                named_ids = set(re.findall(r"parameter '([a-z0-9_]+)'", missing))
                assert named_ids and named_ids <= c_only_ids, (where, named_ids)
                assert named_ids.isdisjoint(kept_ids), where
    # A one-year rotation has one phase; the other has one per year (D109).
    assert [len(phases_of[rotation]) for rotation in DEMO_ROTATIONS] == [1, 2]


def test_withdrawn_c_records_added_to_the_catalogue_compute_c_for_both_demo_rotations():
    """The capability of #229 stays tested after D148: the 61 records that
    only the computed C reads (unit l0/c-records, D129) are loaded from
    params/withdrawn/computed_c/ by its path and added, in memory, to the
    catalogue the service loads, which holds the other six (D164). Together
    they are every record of the computed C. With the demonstration soil file
    and both rotations of D128, whose crops carry the words of the records,
    every covered year is a number computed through c_factor/, none falls
    back to the declared record, and the two rotations do not give the same
    soil loss. No expected value is asserted."""
    service, withdrawn = service_catalogue(), withdrawn_c_records()
    assert set(service).isdisjoint(withdrawn)
    records = {**service, **withdrawn}
    assert check_catalogue(records) == []
    c_ids = computed_c_ids()
    withdrawn_ids = {r["id"] for r in withdrawn.values()}
    assert withdrawn_ids == c_ids - set(module.MAIN_C_CROP_ONLY_IDS)
    assert {r["id"] for r in records.values() if r["id"] in c_ids} == c_ids
    soil_, climate_, calendars = repository_demo_inputs()
    span = daily_years()
    by_rotation = {}
    for rotation in DEMO_ROTATIONS:
        result = run(calendars[rotation], climate_, soil_, records)
        assert isinstance(result, SoilLossResults)
        covered = covered_only(result, span)
        assert covered
        for item in covered.values():
            assert item.value is not None, item.missing
            assert "PROPOSED fallback of brief #218" not in item.source
            assert "engine/erosion/c_factor/" in item.source
        by_rotation[rotation] = tuple(item.value for item in covered.values())
    first, second = (by_rotation[rotation] for rotation in DEMO_ROTATIONS)
    assert first != second


# --- the modules --------------------------------------------------------------


def imported_names(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            names.append(node.module)
    return names


def numbers_in(path: Path) -> set[object]:
    return {
        node.value
        for node in ast.walk(ast.parse(path.read_text("utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }


def test_modules_import_only_allowed_modules_and_hold_only_counting_integers():
    allowed_engine = {
        "engine.calendar.repeat",
        "engine.erosion",
        "engine.erosion._parameters",
        "engine.erosion.equation",
    }
    for name in imported_names(HERE / "soil_loss.py"):
        assert (
            name.split(".")[0] in sys.stdlib_module_names
            or name.startswith("contracts.inputs.")
            or name == "contracts.results.models"
            or name in allowed_engine
        ), name
    tree = ast.parse((HERE / "soil_loss.py").read_text("utf-8"))
    from_package = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "engine.erosion"
        for alias in node.names
    }
    assert from_package == {"c_factor", "ls", "r_factor"}
    for name in imported_names(HERE / "_parameters.py"):
        assert name.split(".")[0] in sys.stdlib_module_names or name in {
            "contracts.results.models",
            "params.catalogue",
        }, name
    # Never load_folder or anything else that reads a file (G1).
    reads_files = {"load_folder", "check_folder", "check_layout", "open", "read_text"}
    for path in (HERE / "soil_loss.py", HERE / "_parameters.py"):
        used = set()
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.alias):
                used.add(node.name)
        assert used.isdisjoint(reads_files), path.name
    assert numbers_in(HERE / "soil_loss.py") == {12, 1}
    assert numbers_in(HERE / "_parameters.py") == {1}
    format_specs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None
    ]
    assert format_specs == [], "a format specification can hide a number"


def test_package_exposes_compute_soil_loss_with_parameters_by_keyword_and_no_default():
    from engine.erosion import compute_soil_loss

    assert compute_soil_loss is module.compute_soil_loss
    for function in (compute_soil_loss, module.compute_soil_loss_daily_index):
        signature = inspect.signature(function)
        assert list(signature.parameters) == [
            "calendar",
            "climate",
            "soil_slope",
            "parameters",
        ]
        parameter = signature.parameters["parameters"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_soil_loss_md_lists_every_parameter_identifier():
    text = (HERE / "SOIL_LOSS.md").read_text("utf-8")
    section = text.split("## Parameters EP1 reads", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(
        r"^\| `[A-Za-z0-9_]+` \| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE
    )
    assert sorted(listed) == sorted(
        dict.fromkeys(
            (
                *SITE_IDS,
                *module.CROP_PARAMETER_IDS,
                *module.MAIN_C_CROP_ONLY_IDS,
                *module.MAIN_C_SITE_ONLY_IDS,
            )
        )
    )


def test_proposed_cases_match_soil_loss_md():
    text = (HERE / "SOIL_LOSS.md").read_text("utf-8")
    section = text.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
