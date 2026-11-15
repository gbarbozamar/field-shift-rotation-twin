"""Agricultural-year frost-day and heat-day counts from monthly thermal counts.

Blueprint section 8 (gated extras, lane L1 Engines: "Frost and heat-day counts
per month from NASA POWER daily minimum and maximum temperature"),
``contracts/CLIMATE_QUANTITIES.md`` (Need N3), and ``contracts/CONVENTIONS.md``
(C5.3, C5.5, D73).

Status: PROPOSED (blueprint section 3.7). This module is standalone and is not
wired into ``engine/water/__init__.py``, EP3, or the API runner; nothing here
takes effect until people approve it.

PROPOSED choices and conventions
--------------------------------
- **Agricultural year mapping (C5.3, D73):** given ``ag_year_start: YearMonth``
  with start month ``M = ag_year_start.month``, agricultural year ``Y`` starts
  at month ``M`` in calendar year ``Y`` and covers twelve consecutive calendar
  months: ``(Y, 1)..(Y, 12)`` when ``M == 1``, or ``(Y, M)..(Y, 12)`` followed
  by ``(Y + 1, 1)..(Y + 1, M - 1)`` when ``M > 1`` (matching ``whole_ag_years``
  in ``api/carbon_forcing.py`` and ``_ag_year_of`` in ``engine/calendar/repeat.py``).
  Every calendar ``(year, month)`` maps to ``year if month >= M else year - 1``.
- **Agricultural years emitted:** every ``ag_year`` that has at least one entry
  in ``monthly_counts``, in ascending chronological order; an empty tuple
  ``()`` when ``monthly_counts`` is empty.
- **Full 12-month coverage (C5.5):** an agricultural year must hold an entry
  for every one of its 12 calendar months. When any calendar month is absent
  from ``monthly_counts``, both ``frost_days`` and ``heat_days`` are
  ``Missing`` with reason ``NO_COVERAGE``.
- **Independent axis evaluation and strict Missing propagation (G4, C3.1,
  C3.3):** once all 12 calendar months are present, ``frost_days`` and
  ``heat_days`` are aggregated independently. If any month's count for an axis
  is ``Missing``, the agricultural-year count for that axis is ``Missing``,
  preserving the chronologically first missing month's ``reason`` (such as
  ``MISSING_INPUT``, ``NOT_COMPUTABLE``, or ``NO_COVERAGE``) and naming the
  axis, missing-month count, first missing month, and detail. Otherwise, the
  count is the exact integer sum across the 12 months.
- **Strict threshold rule (blueprint section 3.5):** ``ag_year_start``,
  ``frost_threshold_deg_c``, and ``heat_threshold_deg_c`` are required
  keyword-only arguments with no default values, and no numeric threshold or
  hardcoded method constant appears anywhere in this module.

Pure function (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and arguments are never modified.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.inputs.site_climate import SiteClimate, YearMonth
from contracts.results.models import Missing
from engine.water.frost_heat import (
    MonthlyFrostHeatCount,
    count_monthly_frost_and_heat_days,
)

__all__ = [
    "AgYearThermalCount",
    "ag_year_thermal_counts",
    "summarize_climate_thermal_counts",
]

_MONTHS_IN_YEAR = len(calendar.month_name[1:])


@dataclass(frozen=True)
class AgYearThermalCount:
    """Agricultural-year count of frost days and heat days.

    PROPOSED. ``ag_year`` is the calendar year in which the agricultural year
    begins (C5.3). Each count is a non-negative integer when computable, or
    ``Missing`` with its reason (G4, C3.1) when it cannot be computed.
    """

    ag_year: int
    frost_days: int | Missing
    heat_days: int | Missing


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_ag_year_start(ag_year_start: object) -> int:
    """Validate ``ag_year_start`` (G5) and return its calendar month number."""
    if not isinstance(ag_year_start, YearMonth):
        raise TypeError(
            f"ag_year_start: expected YearMonth, got {type(ag_year_start).__name__} (G5)"
        )
    month = ag_year_start.month
    if not _is_strict_int(month):
        raise TypeError(
            f"ag_year_start.month: expected int, got {type(month).__name__} (G5)"
        )
    if not (1 <= month <= _MONTHS_IN_YEAR):
        raise ValueError(
            f"ag_year_start.month: expected 1..{_MONTHS_IN_YEAR}, got {month} (C5.1)"
        )
    return month


def _validate_axis_value(
    field: str, year: int, month: int, value: object
) -> int | Missing:
    """Validate a monthly count field as non-negative ``int`` or ``Missing``."""
    if isinstance(value, Missing):
        return value
    if not _is_strict_int(value):
        raise TypeError(
            f"{field} for {year:04d}-{month:02d}: expected int or Missing, "
            f"got {type(value).__name__} (G5)"
        )
    assert isinstance(value, int)
    if value < 0:
        raise ValueError(
            f"{field} for {year:04d}-{month:02d}: expected non-negative int, got {value}"
        )
    return value


def _index_monthly_counts(
    monthly_counts: object,
) -> dict[tuple[int, int], MonthlyFrostHeatCount]:
    """Validate ``monthly_counts`` (G5) and index entries by ``(year, month)``."""
    if isinstance(monthly_counts, (str, bytes, bytearray)) or not isinstance(
        monthly_counts, Sequence
    ):
        raise TypeError(
            "monthly_counts: expected a Sequence of MonthlyFrostHeatCount, "
            f"got {type(monthly_counts).__name__} (G5)"
        )
    by_month: dict[tuple[int, int], MonthlyFrostHeatCount] = {}
    for item in monthly_counts:
        if not isinstance(item, MonthlyFrostHeatCount):
            raise TypeError(
                "monthly_counts: expected MonthlyFrostHeatCount elements, "
                f"got {type(item).__name__} (G5)"
            )
        if not _is_strict_int(item.year):
            raise TypeError(
                f"monthly_counts item year: expected int, got {type(item.year).__name__} (G5)"
            )
        if not _is_strict_int(item.month):
            raise TypeError(
                "monthly_counts item month: expected int, "
                f"got {type(item.month).__name__} (G5)"
            )
        if not (1 <= item.month <= _MONTHS_IN_YEAR):
            raise ValueError(
                f"monthly_counts item month: expected 1..{_MONTHS_IN_YEAR}, "
                f"got {item.month} (C5.1)"
            )
        _validate_axis_value("frost_days", item.year, item.month, item.frost_days)
        _validate_axis_value("heat_days", item.year, item.month, item.heat_days)
        key = (item.year, item.month)
        if key in by_month:
            raise ValueError(
                f"monthly_counts contains duplicate entry for {item.year:04d}-{item.month:02d}"
            )
        by_month[key] = item
    return by_month


def _ag_year_of_month(year: int, month: int, start_month: int) -> int:
    """Calendar year in which the agricultural year containing ``(year, month)`` begins."""
    return year if month >= start_month else year - 1


def _ag_year_months(ag_year: int, start_month: int) -> list[tuple[int, int]]:
    """The 12 consecutive ``(year, month)`` pairs of ``ag_year`` starting at ``start_month``."""
    return [
        (
            ag_year + (start_month - 1 + offset) // _MONTHS_IN_YEAR,
            (start_month - 1 + offset) % _MONTHS_IN_YEAR + 1,
        )
        for offset in range(_MONTHS_IN_YEAR)
    ]


def _aggregate_axis(
    ag_year: int,
    axis_name: str,
    entries: list[tuple[int, int, int | Missing]],
) -> int | Missing:
    """Sum one thermal count axis over a complete 12-month agricultural year."""
    missing_months: list[tuple[int, int, Missing]] = []
    total = 0
    for year, month, value in entries:
        if isinstance(value, Missing):
            missing_months.append((year, month, value))
        else:
            total += value
    if missing_months:
        first_year, first_month, first_missing = missing_months[0]
        first_detail = f": {first_missing.detail}" if first_missing.detail else ""
        return Missing(
            reason=first_missing.reason,
            detail=(
                f"{axis_name} for agricultural year {ag_year} is not computed: "
                f"{len(missing_months)} of {_MONTHS_IN_YEAR} month(s) are missing, "
                f"the first in {first_year:04d}-{first_month:02d} "
                f"({first_missing.reason}{first_detail}) (C3.3)"
            ),
        )
    return total


def ag_year_thermal_counts(
    monthly_counts: Sequence[MonthlyFrostHeatCount],
    *,
    ag_year_start: YearMonth,
) -> tuple[AgYearThermalCount, ...]:
    """Aggregate monthly frost and heat counts into agricultural years (D73, C5.5).

    Raises ``TypeError`` if ``monthly_counts`` is not a sequence of
    ``MonthlyFrostHeatCount`` or ``ag_year_start`` is not a ``YearMonth`` (G5),
    and ``ValueError`` for out-of-range months, negative counts, or duplicate
    ``(year, month)`` entries.
    """
    start_month = _validate_ag_year_start(ag_year_start)
    by_month = _index_monthly_counts(monthly_counts)
    if not by_month:
        return ()

    ag_years = sorted(
        {_ag_year_of_month(year, month, start_month) for year, month in by_month}
    )
    results: list[AgYearThermalCount] = []
    for ag_year in ag_years:
        expected_months = _ag_year_months(ag_year, start_month)
        missing_months = [
            (year, month)
            for year, month in expected_months
            if (year, month) not in by_month
        ]
        if missing_months:
            first_year, first_month = missing_months[0]
            no_coverage = Missing(
                reason="NO_COVERAGE",
                detail=(
                    f"agricultural year {ag_year} (starting month {start_month:02d}) "
                    f"is missing {len(missing_months)} of {_MONTHS_IN_YEAR} calendar "
                    f"month(s), the first being {first_year:04d}-{first_month:02d} (C5.5)"
                ),
            )
            results.append(
                AgYearThermalCount(
                    ag_year=ag_year,
                    frost_days=no_coverage,
                    heat_days=no_coverage,
                )
            )
            continue

        frost_entries = [
            (year, month, by_month[(year, month)].frost_days)
            for year, month in expected_months
        ]
        heat_entries = [
            (year, month, by_month[(year, month)].heat_days)
            for year, month in expected_months
        ]
        results.append(
            AgYearThermalCount(
                ag_year=ag_year,
                frost_days=_aggregate_axis(ag_year, "frost_days", frost_entries),
                heat_days=_aggregate_axis(ag_year, "heat_days", heat_entries),
            )
        )
    return tuple(results)


def summarize_climate_thermal_counts(
    climate: SiteClimate,
    *,
    ag_year_start: YearMonth,
    frost_threshold_deg_c: float | Missing,
    heat_threshold_deg_c: float | Missing,
) -> tuple[tuple[MonthlyFrostHeatCount, ...], tuple[AgYearThermalCount, ...]]:
    """Compute monthly and agricultural-year frost and heat counts from ``SiteClimate``.

    Delegates to ``count_monthly_frost_and_heat_days`` and
    ``ag_year_thermal_counts``. ``ag_year_start``, ``frost_threshold_deg_c``,
    and ``heat_threshold_deg_c`` are required keyword-only arguments with no
    default values (blueprint section 3.5).
    """
    _validate_ag_year_start(ag_year_start)
    monthly = tuple(
        count_monthly_frost_and_heat_days(
            climate,
            frost_threshold_deg_c=frost_threshold_deg_c,
            heat_threshold_deg_c=heat_threshold_deg_c,
        )
    )
    yearly = ag_year_thermal_counts(monthly, ag_year_start=ag_year_start)
    return monthly, yearly
