"""Calendar-year and daily surface runoff summary from EP3's daily chain (D229, D230).

Status: PROPOSED (blueprint section 3.7). Bridges ``engine.water.exposure``'s
daily water chain to calendar-year runoff evaluation (``validation.h10_runoff``)
without duplicating Curve Number or rotation-repetition math:

- caller validation (``_check_types``, ``_check_same_field``), unit checks,
  time-zone checks, and ``_run_chain`` are imported directly from
  ``engine.water.exposure``;
- daily runoff is read from ``ChainDay.runoff.runoff`` for every day of the
  precipitation record;
- calendar-year runoff sums daily runoff over complete Jan 1–Dec 31 years
  only; incomplete years stay ``Missing("NO_COVERAGE", ...)``, and any year
  with a missing daily runoff value stays ``Missing`` with that day's reason.

Pure function (G1): no file, no network, no clock, no environment variable, and
the arguments are not changed. Holds no parameters or method constants.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing
from engine.water import exposure as ep3
from engine.water._parameters import Catalogue

__all__ = ["CalendarYearRunoffSummary", "compute_calendar_year_runoff"]


@dataclass(frozen=True)
class CalendarYearRunoffSummary:
    """Daily and calendar-year summed surface runoff (mm and mm year-1)."""

    daily_runoff: dict[dt.date, float | Missing]
    yearly_runoff: dict[int, float | Missing]


def _no_coverage(year: int, first: dt.date, last: dt.date) -> Missing:
    return Missing(
        reason="NO_COVERAGE",
        detail=(
            f"the daily series '{ep3.PRECIPITATION}' does not cover calendar year "
            f"{year} from {first.isoformat()} to {last.isoformat()} (C5.5)"
        ),
    )


def _missing_year(year: int, missing_days: list[tuple[dt.date, Missing]]) -> Missing:
    (first_day, first_missing), *_ = missing_days
    first_detail = f": {first_missing.detail}" if first_missing.detail else ""
    return Missing(
        reason=first_missing.reason,
        detail=(
            f"calendar-year runoff is not computed for {year}: daily runoff has no "
            f"value on {len(missing_days)} day(s), the first on "
            f"{first_day.isoformat()} ({first_missing.reason}{first_detail})"
        ),
    )


def _sum_year(
    year: int,
    first: dt.date,
    last: dt.date,
    daily_runoff: dict[dt.date, float | Missing],
) -> float | Missing:
    year_days = ep3._days(first, last)
    missing_days: list[tuple[dt.date, Missing]] = []
    values: list[float] = []
    for day in year_days:
        value = daily_runoff[day]
        if isinstance(value, Missing):
            missing_days.append((day, value))
        elif not math.isfinite(value):
            missing_days.append(
                (day, Missing(reason="NOT_COMPUTABLE", detail="non-finite daily runoff"))
            )
        else:
            values.append(value)
    if missing_days:
        return _missing_year(year, missing_days)
    return math.fsum(values)


def _common_problem(
    calendar: RotationCalendar,
    by_quantity: dict[str, DailySeries],
    present: list[str],
) -> Missing | None:
    if calendar.ag_year_start.month is None:
        return Missing(reason="MISSING_INPUT", detail=ep3.START_MONTH_MISSING)
    if not calendar.feasibility.feasible:
        return Missing(reason="NOT_COMPUTABLE", detail=ep3.INFEASIBLE)
    if ep3._mixed_time_zones([by_quantity[name] for name in present]):
        return Missing(reason="NOT_COMPUTABLE", detail=ep3.MIXED_TIME_ZONES)
    return None


def compute_calendar_year_runoff(
    calendar: RotationCalendar,
    climate: SiteClimate,
    soil_slope: SiteSoilSlope,
    *,
    parameters: dict[str, dict],
) -> CalendarYearRunoffSummary:
    """Compute daily and calendar-year summed runoff using EP3's chain internals.

    ``parameters`` is the parameter catalogue as loaded by the runner, passed by
    keyword with no default.

    Returns ``CalendarYearRunoffSummary`` with:

    - ``daily_runoff``: ``dict[dt.date, float | Missing]`` over every day from
      ``precipitation.start_date`` to ``precipitation.end_date`` (empty when the
      climate record has no daily ``precipitation`` series);
    - ``yearly_runoff``: ``dict[int, float | Missing]`` over every calendar year
      in the precipitation span. Only complete Jan 1–Dec 31 calendar years are
      summed; incomplete years carry ``Missing(reason="NO_COVERAGE")``, and any
      missing daily runoff in a complete year makes that year ``Missing`` with
      the first missing day's reason.

    Raises ``TypeError`` for wrong argument types (G3, G5) and ``ValueError``
    when ``calendar``, ``climate``, and ``soil_slope`` name different fields
    (G5).
    """
    ep3._check_types(calendar, climate, soil_slope, parameters)
    ep3._check_same_field(calendar, climate, soil_slope)

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in ep3.DAILY_INPUTS
    }
    record = by_quantity.get(ep3.PRECIPITATION)
    if record is None:
        return CalendarYearRunoffSummary(daily_runoff={}, yearly_runoff={})

    present = [name for name in ep3.DAILY_INPUTS if name in by_quantity]
    days = ep3._days(record.start_date, record.end_date)
    years = range(record.start_date.year, record.end_date.year + ep3._FIRST)

    common = _common_problem(calendar, by_quantity, present)
    if common is not None:
        return CalendarYearRunoffSummary(
            daily_runoff=dict.fromkeys(days, common),
            yearly_runoff=dict.fromkeys(years, common),
        )

    units = ep3._unit_problems(climate, by_quantity)
    if units:
        unit_missing = ep3._units_not_accepted(units)
        daily_runoff = dict.fromkeys(days, unit_missing)
        yearly_runoff = {
            year: (
                _no_coverage(
                    year,
                    ep3._first_day(year, ep3._FIRST),
                    ep3._last_day(year, ep3._FIRST),
                )
                if not ep3._covers(
                    record,
                    ep3._first_day(year, ep3._FIRST),
                    ep3._last_day(year, ep3._FIRST),
                )
                else unit_missing
            )
            for year in years
        }
        return CalendarYearRunoffSummary(
            daily_runoff=daily_runoff,
            yearly_runoff=yearly_runoff,
        )

    catalogue = Catalogue(parameters)
    notes = ep3._Notes()
    chain = ep3._run_chain(
        calendar,
        climate,
        catalogue,
        by_quantity,
        days,
        notes,
    )
    daily_runoff: dict[dt.date, float | Missing] = {
        item.date: item.runoff.runoff for item in chain
    }

    yearly_runoff: dict[int, float | Missing] = {}
    for year in years:
        first = ep3._first_day(year, ep3._FIRST)
        last = ep3._last_day(year, ep3._FIRST)
        if not ep3._covers(record, first, last):
            yearly_runoff[year] = _no_coverage(year, first, last)
            continue
        yearly_runoff[year] = _sum_year(year, first, last, daily_runoff)

    return CalendarYearRunoffSummary(
        daily_runoff=daily_runoff,
        yearly_runoff=yearly_runoff,
    )
