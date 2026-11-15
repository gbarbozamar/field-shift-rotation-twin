"""Monthly frost-day and heat-day counts from daily minimum and maximum air temperature.

Blueprint section 8 (gated extras, lane L1 Engines: "Frost and heat-day counts
per month from NASA POWER daily minimum and maximum temperature") and
``contracts/CLIMATE_QUANTITIES.md`` (Need N3).

Status: PROPOSED (blueprint section 3.7). This module is standalone and is not
wired into ``engine/water/__init__.py``, EP3, or the API runner; nothing here
takes effect until people approve it.

Reads the two decided temperature quantities of ``SiteClimate``:

- ``air_temperature_min_2m`` (``CQ3``, accepted unit ``"degC"``) for frost days;
- ``air_temperature_max_2m`` (``CQ2``, accepted unit ``"degC"``) for heat days.

Strict threshold rule (blueprint section 3.5): both temperature thresholds are
required keyword-only arguments with no default values, and no numeric
temperature threshold appears anywhere in this module.

PROPOSED choices and OPEN questions
-----------------------------------
- **Comparison direction (PROPOSED / OPEN):** a frost day is counted when the
  daily minimum temperature is less than or equal to ``frost_threshold_deg_c``
  (``<=``), and a heat day is counted when the daily maximum temperature is
  greater than or equal to ``heat_threshold_deg_c`` (``>=``). **OPEN** for
  agronomist / science-reviewer confirmation: whether boundary equality counts
  as an event (inclusive ``<=`` / ``>=``) or is excluded (strict ``<`` / ``>``).
- **Independent monthly evaluation (PROPOSED):** frost and heat counts are
  evaluated independently per calendar month, so a missing series, wrong unit,
  incomplete month, missing day, non-finite day, or missing/non-finite
  threshold on one temperature quantity leaves the other count computable.
  Because the two series are never combined in one calculation, differing
  ``time_zone`` values between them do not block either independent count
  (**OPEN**: C6.3 if a combined metric is ever added).
- **Months emitted (PROPOSED):** every calendar ``(year, month)`` that has at
  least one day in either ``air_temperature_min_2m`` or
  ``air_temperature_max_2m``, in chronological order; an empty list when neither
  series is present.
- **Check order per count and month (PROPOSED):**
  1. Caller argument types (``climate``, ``frost_threshold_deg_c``,
     ``heat_threshold_deg_c``) -> ``TypeError`` for wrong types including
     ``bool`` (G5).
  2. Threshold value: ``Missing`` -> propagate unchanged; non-finite
     (``NaN``, ``inf``, ``-inf``, or integer overflow) -> ``Missing`` with
     reason ``NOT_COMPUTABLE``.
  3. Series presence in ``climate.daily_series`` -> ``Missing`` with reason
     ``MISSING_INPUT`` naming the absent quantity (G4).
  4. Series unit string exact match (``"degC"``, no conversion, C1.1) ->
     ``Missing`` with reason ``MISSING_INPUT`` naming the quantity and units
     (Q11).
  5. Complete calendar month coverage (every Gregorian calendar day of
     ``(year, month)``, including leap years) -> ``Missing`` with reason
     ``NO_COVERAGE`` when any day of the month is absent (C5.5).
  6. Daily values in the month: any day with ``missing`` set -> ``Missing``
     with reason ``MISSING_INPUT`` naming the quantity, count, first missing
     date, and day reason (C3.3, C3.4, G4; no gap filling); any day with a
     non-finite value -> ``Missing`` with reason ``NOT_COMPUTABLE`` naming the
     quantity and date.

Pure function (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and arguments are never modified.
"""

from __future__ import annotations

import calendar
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass

from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.results.models import Missing
from engine.water.et0.quantities import ACCEPTED_UNITS, TEMPERATURE_MAX, TEMPERATURE_MIN

__all__ = [
    "MonthlyFrostHeatCount",
    "count_monthly_frost_and_heat_days",
]

_ACCEPTED_MIN_UNIT = ACCEPTED_UNITS[TEMPERATURE_MIN]
_ACCEPTED_MAX_UNIT = ACCEPTED_UNITS[TEMPERATURE_MAX]


@dataclass(frozen=True)
class MonthlyFrostHeatCount:
    """Monthly count of frost days and heat days for one calendar month.

    PROPOSED. ``year`` is the calendar year and ``month`` is the calendar month
    number (C5.1). Each count is a non-negative integer when computable, or
    ``Missing`` with its reason (G4, C3.1) when it cannot be computed.
    """

    year: int
    month: int
    frost_days: int | Missing
    heat_days: int | Missing


def _is_number(value: object) -> bool:
    """True for an ``int`` or ``float``; ``bool`` is rejected as a caller defect."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_threshold(name: str, value: object) -> int | float | Missing:
    """Validate a caller-supplied threshold (G5) and flag non-finite numbers."""
    if isinstance(value, Missing):
        return value
    if not _is_number(value):
        raise TypeError(
            f"{name}: expected float, int, or Missing, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite(value):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{name} is not a finite number",
        )
    return value


def _group_by_month(
    series: DailySeries | None,
) -> dict[tuple[int, int], list[DailyValue]]:
    """Group daily items of a series by calendar ``(year, month)``."""
    if series is None:
        return {}
    grouped: dict[tuple[int, int], list[DailyValue]] = {}
    for day in series.days:
        grouped.setdefault((day.date.year, day.date.month), []).append(day)
    return grouped


def _count_month_axis(
    *,
    year: int,
    month: int,
    series: DailySeries | None,
    month_days: list[DailyValue],
    quantity: str,
    accepted_unit: str,
    threshold: int | float | Missing,
    predicate: Callable[[int | float, int | float], bool],
) -> int | Missing:
    """Count matching days for one temperature axis in one calendar month."""
    if isinstance(threshold, Missing):
        return threshold
    if series is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=f"the climate record has no daily series '{quantity}'",
        )
    if series.unit != accepted_unit:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the daily series '{quantity}' is in the unit '{series.unit}', "
                f"not in the accepted unit '{accepted_unit}' (C1.1)"
            ),
        )
    _, days_in_month = calendar.monthrange(year, month)
    if (
        len(month_days) != days_in_month
        or len({day.date for day in month_days}) != days_in_month
    ):
        return Missing(
            reason="NO_COVERAGE",
            detail=(
                f"the daily series '{quantity}' does not cover every day of "
                f"{year:04d}-{month:02d} (C5.5)"
            ),
        )
    missing_days = [day for day in month_days if day.missing is not None]
    if missing_days:
        first_missing = min(missing_days, key=lambda day: day.date)
        assert first_missing.missing is not None
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the daily series '{quantity}' holds {len(missing_days)} day(s) "
                f"without a value in {year:04d}-{month:02d}, the first on "
                f"{first_missing.date.isoformat()} ({first_missing.missing.reason}), "
                "and no gap is filled (C3.3, C3.4)"
            ),
        )
    values: list[int | float] = []
    for day in sorted(month_days, key=lambda item: item.date):
        value = day.value
        if not _is_number(value):
            raise TypeError(
                f"daily value for '{quantity}' on {day.date.isoformat()} must be "
                f"a number, not {type(value).__name__} (G5)"
            )
        assert isinstance(value, (int, float))
        if not _is_finite(value):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"the daily series '{quantity}' has a non-finite value on "
                    f"{day.date.isoformat()}"
                ),
            )
        values.append(value)
    return sum(1 for value in values if predicate(value, threshold))


def count_monthly_frost_and_heat_days(
    climate: SiteClimate,
    *,
    frost_threshold_deg_c: float | int | Missing,
    heat_threshold_deg_c: float | int | Missing,
) -> list[MonthlyFrostHeatCount]:
    """Count frost and heat days per calendar month from ``SiteClimate``.

    Both ``frost_threshold_deg_c`` and ``heat_threshold_deg_c`` are required
    keyword-only arguments with no default values (blueprint section 3.5).

    Raises ``TypeError`` if ``climate`` is not a ``SiteClimate`` or either
    threshold is not a ``float``, ``int`` (excluding ``bool``), or
    ``contracts.results.models.Missing`` (G3, G5).
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    frost_threshold = _validate_threshold(
        "frost_threshold_deg_c", frost_threshold_deg_c
    )
    heat_threshold = _validate_threshold("heat_threshold_deg_c", heat_threshold_deg_c)

    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in (TEMPERATURE_MIN, TEMPERATURE_MAX)
    }
    min_series = by_quantity.get(TEMPERATURE_MIN)
    max_series = by_quantity.get(TEMPERATURE_MAX)
    min_by_month = _group_by_month(min_series)
    max_by_month = _group_by_month(max_series)

    months: list[tuple[int, int]] = sorted(set(min_by_month) | set(max_by_month))
    results: list[MonthlyFrostHeatCount] = []
    for year, month in months:
        frost_days = _count_month_axis(
            year=year,
            month=month,
            series=min_series,
            month_days=min_by_month.get((year, month), []),
            quantity=TEMPERATURE_MIN,
            accepted_unit=_ACCEPTED_MIN_UNIT,
            threshold=frost_threshold,
            predicate=operator.le,
        )
        heat_days = _count_month_axis(
            year=year,
            month=month,
            series=max_series,
            month_days=max_by_month.get((year, month), []),
            quantity=TEMPERATURE_MAX,
            accepted_unit=_ACCEPTED_MAX_UNIT,
            threshold=heat_threshold,
            predicate=operator.ge,
        )
        results.append(
            MonthlyFrostHeatCount(
                year=year,
                month=month,
                frost_days=frost_days,
                heat_days=heat_days,
            )
        )
    return results
