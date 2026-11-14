"""Entry point EP3 of contracts/ENTRYPOINTS.md: ``compute_water_deficit_exposure``.

Mechanical form only (issue #134), after the precedent of EP1
(engine/erosion/soil_loss.py, issue #115). The function lays out the
agricultural years of the climate record (decision D47 of issue #77) and
returns one ``WaterDeficitExposure`` per agricultural year, each missing with
the reason that applies. It returns no number: the parameters are not passed
to the entry point yet (decision D46, not in force), and the definition of the
indicator is incomplete (convention C1.4). See EXPOSURE.md in this folder.

It reads, without changing them, what the two internal parts of the water
engine need: the constant groups of engine/water/et0/constants.py, the daily
climate quantities of engine/water/et0/quantities.py, the keyword arguments
of ``run_balance`` and the fields of ``CropDay`` in engine/water/balance/. It
calls neither part: neither can run without a value this module would have
to invent (EXPOSURE.md, "PROPOSED choices").

Status: PROPOSED (blueprint section 3.7): the order of the checks, the reason
of each item, the time basis of each case and the format of every ``detail``.

Pure function (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. The only integer is the one of month and
day arithmetic, listed in EXPOSURE.md.
"""

from __future__ import annotations

import datetime as dt
import inspect
from dataclasses import fields
from typing import get_args

from contracts.inputs.common import Value
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_WATER_DEFICIT_EXPOSURE,
    Missing,
    WaterDeficitExposure,
)
from engine.water.balance import CropDay, run_balance
from engine.water.et0 import Et0Constants
from engine.water.et0.quantities import CLIMATE_QUANTITIES

__all__ = ["compute_water_deficit_exposure"]

# The identifier of the indicator, read from the results model (C1.1).
(INDICATOR,) = get_args(WaterDeficitExposure.model_fields["indicator"].annotation)

# The quantity identifier of daily precipitation (decision D23 of issue #77).
# It is the series that marks the record (PROPOSED: the same series as EP1, so
# that EP1 and EP3 list the same years, D47), and the precipitation of each
# day of the balance (``DayInput.precipitation`` of engine/water/balance/).
PRECIPITATION = "precipitation"

# Every daily series the water chain reads: precipitation for the balance, then
# the five inputs of the reference evapotranspiration, in their own order.
DAILY_INPUTS: tuple[str, ...] = (PRECIPITATION, *CLIMATE_QUANTITIES)

# What the two internal parts need that the entry point is not given, read
# from the parts themselves so that the names cannot drift.
ET0_CONSTANT_GROUPS: tuple[str, ...] = tuple(item.name for item in fields(Et0Constants))
BALANCE_PARAMETERS: tuple[str, ...] = tuple(
    name
    for name, parameter in inspect.signature(run_balance).parameters.items()
    if parameter.kind is inspect.Parameter.KEYWORD_ONLY
)
CROP_DAY_FIELDS: tuple[str, ...] = tuple(item.name for item in fields(CropDay))

# The two values of the point of the series that the reference
# evapotranspiration reads (engine/water/et0/daily.py); longitude is not read.
POINT_VALUES: tuple[str, ...] = ("latitude", "elevation")

# Day and month arithmetic (C5.1, C5.3): months and days counted from one.
_FIRST = 1
_ONE_DAY = dt.timedelta(days=_FIRST)

# --- detail texts: PROPOSED, English for developers -------------------------

START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the agricultural years cannot be laid out; one item for the "
    "whole rotation is returned in their place (EP3, Q4)"
)
RECORD_MISSING = (
    f"the climate record has no daily series with quantity '{PRECIPITATION}' "
    "(decision D23 of issue #77), so the agricultural years of the record cannot "
    "be laid out (decision D47 of issue #77; G4, third row); one item for the "
    "whole rotation is returned in their place"
)
INFEASIBLE = (
    "the rotation calendar is infeasible (feasibility.feasible is false), so no "
    "value that depends on it is computed (G4, first row)"
)
MIXED_TIME_ZONES = (
    "the daily series the water engine reads ("
    + ", ".join(f"'{name}'" for name in DAILY_INPUTS)
    + ") do not share one time zone, and an engine never combines them (C6.3; "
    "G4, sixth row)"
)

# The items that hold whatever the arguments: (part, reason code of C3.2, or
# None when the code is not decided, why). They are written in this order, with
# the items of a missing value of the point after those of ET0.
_ET0_ITEMS: tuple[tuple[str, str | None, str], ...] = (
    (
        "ET0",
        "MISSING_INPUT",
        "the constants of engine/water/et0/constants.py ("
        + ", ".join(ET0_CONSTANT_GROUPS)
        + ") are not passed to the entry point (decision D46 of issue #77 is not in "
        "force: D56 asks contracts/ENTRYPOINTS.md to state the argument first)",
    ),
    (
        "ET0",
        "MISSING_INPUT",
        "the reason code of the unit guard of engine/water/et0/quantities.py is not "
        "decided (Q11 of contracts/ENTRYPOINTS.md)",
    ),
    (
        "ET0",
        "MISSING_INPUT",
        "the unit strings of the point (PointUnits of engine/water/et0/quantities.py) "
        "are not among the arguments of EP3 (decision D55 of issue #77 sets them for "
        "the climate adapter)",
    ),
)
_BALANCE_AND_INDICATOR_ITEMS: tuple[tuple[str, str | None, str], ...] = (
    (
        "balance",
        "MISSING_INPUT",
        "the column ("
        + ", ".join(BALANCE_PARAMETERS)
        + " of run_balance in engine/water/balance/) is not passed to the entry point "
        "(decisions D46 and D49 of issue #77, OPEN 5 and 11 of "
        "engine/water/balance/README.md)",
    ),
    (
        "balance",
        "MISSING_INPUT",
        "the crop of each day (CropDay: "
        + ", ".join(CROP_DAY_FIELDS)
        + ") needs crop parameters that are not passed (decision D46 of issue #77), "
        "and how the rotation is repeated over the years of the record is not "
        "decided (Q5 of contracts/ENTRYPOINTS.md)",
    ),
    (
        "balance",
        "NOT_AVAILABLE",
        "the daily runoff by the Curve Number (decision D44 of issue #77) is a unit "
        "that is not built",
    ),
    (
        "balance",
        "NOT_AVAILABLE",
        "the daily evaporation coefficient from the surface-layer balance (decision "
        "D44 of issue #77) is a unit that is not built, and the single-coefficient "
        "fallback of D44 is not mapped onto it (OPEN 7 of "
        "engine/water/balance/README.md)",
    ),
    (
        "indicator",
        None,
        "the critical period of each crop, and which quantities of the daily balance "
        "are water transpired and water demanded, are not defined (C1.4)",
    ),
)

# How an item whose reason code is not decided is written.
_CODE_NOT_DECIDED = "(reason code OPEN: question 4 of contracts/results/README.md)"


# --- checks of the caller (G5) ----------------------------------------------


def _check_types(calendar: object, climate: object, soil_slope: object) -> None:
    for name, argument, model in (
        ("calendar", calendar, RotationCalendar),
        ("climate", climate, SiteClimate),
        ("soil_slope", soil_slope, SiteSoilSlope),
    ):
        if not isinstance(argument, model):
            raise TypeError(
                f"{name}: expected {model.__name__}, got {type(argument).__name__} (G5)"
            )


def _check_same_field(
    calendar: RotationCalendar, climate: SiteClimate, soil_slope: SiteSoilSlope
) -> None:
    """``ValueError`` when the three arguments do not name one field (G5).

    The message names the identifier fields that differ, never their values.
    """
    differing = [
        field
        for field in ("case_id", "field_id")
        if getattr(climate, field) != getattr(calendar, field)
        or getattr(soil_slope, field) != getattr(calendar, field)
    ]
    if differing:
        raise ValueError(
            f"the arguments calendar, climate and soil_slope name different "
            f"{' and '.join(differing)} (G5)"
        )


# --- agricultural years (C5.3, D47) -------------------------------------------


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - _FIRST


def _first_day(ag_year: int, start_month: int) -> dt.date:
    return dt.date(ag_year, start_month, _FIRST)


def _last_day(ag_year: int, start_month: int) -> dt.date:
    return _first_day(ag_year + _FIRST, start_month) - _ONE_DAY


def _covers(series: DailySeries, first: dt.date, last: dt.date) -> bool:
    return series.start_date <= first and last <= series.end_date


def _mixed_time_zones(series: list[DailySeries]) -> bool:
    """More than one time zone among the series (C6.3); the list is not empty."""
    time_zones = {item.time_zone for item in series}
    return time_zones != {min(time_zones)}


# --- what each item reports ---------------------------------------------------


def _item(part: str, code: str | None, why: str) -> str:
    return f"{part} {code if code is not None else _CODE_NOT_DECIDED}: {why}"


def _point_items(climate: SiteClimate) -> list[str]:
    items = []
    for name in POINT_VALUES:
        value: Value = getattr(climate.point, name)
        if value.missing is not None:
            why = f"{name} is missing in the point of the climate record"
            if value.missing.detail is not None:
                why = f"{why}: {value.missing.detail}"
            items.append(_item("ET0", value.missing.reason, why))
    return items


def _input_items(
    absent: list[str],
    missing_days: dict[str, list[dt.date]],
    first: dt.date,
    last: dt.date,
    ag_year: int,
) -> list[str]:
    items = [
        _item(
            "input",
            "MISSING_INPUT",
            f"the climate record has no daily series '{name}' (G4, third row)",
        )
        for name in absent
    ]
    for name, days in missing_days.items():
        held = [day for day in days if first <= day <= last]
        if held:
            items.append(
                _item(
                    "input",
                    "MISSING_INPUT",
                    f"the daily series '{name}' holds {len(held)} day(s) without a "
                    f"value in agricultural year {ag_year}, the first on "
                    f"{min(held).isoformat()}, and no gap is filled (G4, fourth row, C3.4)",
                )
            )
    return items


def _not_computed(items: list[str]) -> Missing:
    return Missing(
        reason="MISSING_INPUT",
        detail=(
            f"{INDICATOR} needs the reference evapotranspiration, the daily water "
            "balance and the definition of the indicator, and none is available: "
            + "; ".join(items)
        ),
    )


def _not_covered(names: list[str], ag_year: int) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            "the daily series "
            + ", ".join(f"'{name}'" for name in names)
            + f" do not cover agricultural year {ag_year} from its first day to its "
            "last (C5.5)"
        ),
    )


def _for_rotation(missing: Missing) -> WaterDeficitExposure:
    return WaterDeficitExposure(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        missing=missing,
        time_basis="rotation",
    )


def _for_ag_year(ag_year: int, missing: Missing) -> WaterDeficitExposure:
    return WaterDeficitExposure(
        indicator=INDICATOR,
        direction=DIRECTION_OF[INDICATOR],
        value=None,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        missing=missing,
        time_basis="ag_year",
        ag_year=ag_year,
    )


# --- the entry point ----------------------------------------------------------


def compute_water_deficit_exposure(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
) -> list[WaterDeficitExposure]:
    """Exposure to water deficit of one rotation of one field (EP3), mechanical form.

    Returns a list that is never empty and holds no number:

    - one item on the time basis ``rotation``, reason ``MISSING_INPUT``, when
      the agricultural years cannot be laid out: the start month is missing,
      or the record has no daily ``precipitation`` series;
    - otherwise one item per agricultural year of the record (D47), on the
      time basis ``ag_year``, each missing with the first reason that
      applies: ``NOT_COMPUTABLE`` for an infeasible calendar, then
      ``NOT_COMPUTABLE`` for series in different time zones (C6.3), then
      ``NO_COVERAGE`` for a year a series does not cover (C5.5), then
      ``MISSING_INPUT`` naming every absent series, every series with days
      held missing in the year, and what the two internal parts and the
      indicator need that the entry point is not given.

    Raises ``TypeError`` for an argument that is not its model and
    ``ValueError`` when the arguments name different fields (G5).
    """
    _check_types(calendar, climate, soil_slope)
    _check_same_field(calendar, climate, soil_slope)

    start_month = calendar.ag_year_start.month
    if start_month is None:
        return [
            _for_rotation(Missing(reason="MISSING_INPUT", detail=START_MONTH_MISSING))
        ]

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in DAILY_INPUTS
    }
    record = by_quantity.get(PRECIPITATION)
    if record is None:
        return [_for_rotation(Missing(reason="MISSING_INPUT", detail=RECORD_MISSING))]

    present = [name for name in DAILY_INPUTS if name in by_quantity]
    absent = [name for name in DAILY_INPUTS if name not in by_quantity]
    if not calendar.feasibility.feasible:
        common: Missing | None = Missing(reason="NOT_COMPUTABLE", detail=INFEASIBLE)
    elif _mixed_time_zones([by_quantity[name] for name in present]):
        common = Missing(reason="NOT_COMPUTABLE", detail=MIXED_TIME_ZONES)
    else:
        common = None
    missing_days = {
        name: [day.date for day in by_quantity[name].days if day.missing is not None]
        for name in present
    }
    fixed = (
        [_item(*item) for item in _ET0_ITEMS]
        + _point_items(climate)
        + [_item(*item) for item in _BALANCE_AND_INDICATOR_ITEMS]
    )

    result: list[WaterDeficitExposure] = []
    first_ag_year = _ag_year_of(record.start_date, start_month)
    last_ag_year = _ag_year_of(record.end_date, start_month)
    for ag_year in range(first_ag_year, last_ag_year + _FIRST):
        if common is not None:
            result.append(_for_ag_year(ag_year, common))
            continue
        first = _first_day(ag_year, start_month)
        last = _last_day(ag_year, start_month)
        not_covering = [
            name for name in present if not _covers(by_quantity[name], first, last)
        ]
        if not_covering:
            result.append(_for_ag_year(ag_year, _not_covered(not_covering, ag_year)))
            continue
        items = _input_items(absent, missing_days, first, last, ag_year) + fixed
        result.append(_for_ag_year(ag_year, _not_computed(items)))
    return result
