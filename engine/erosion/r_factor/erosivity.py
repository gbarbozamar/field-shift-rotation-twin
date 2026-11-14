"""Rainfall erosivity factor ``R`` by year and month (docs/METHODS.md M1.2). PROPOSED.

M1.2 builds ``R`` from two parts:

- the **mean annual level** of ``R`` at the field, from the published national
  values (S4), interpolated to the field. Here it is an input: this package
  neither reads nor interpolates it;
- the **fraction of the annual erosivity that falls in each month** and the
  **variation between years**, from a daily erosivity index of the power-law
  family computed from daily precipitation (S5, S6), used **in relative terms
  only**. The index never gives the level of ``R`` (S8 is the reason).

The forms, all PROPOSED until a person checks them against S5 and S6::

    index(day)      = P(day) ** exponent    when P(day) > threshold
    index(day)      = 0                      when P(day) <= threshold
    sum(month)      = sum of index(day) over the days of the month
    sum(ag_year)    = sum of sum(month) over the twelve months
    fraction(month) = sum(month) / sum(ag_year of the month)
    ratio(ag_year)  = sum(ag_year) / mean of sum(ag_year) over the years with a sum
    R(year, month)  = mean_annual_r * fraction(month) * ratio(ag_year)

``P`` is the daily precipitation of the series (CQ1 of
``contracts/CLIMATE_QUANTITIES.md``, unit ``mm day-1``).

**This module holds no coefficient.** The exponent, the threshold and the mean
annual level are arguments without a default; the caller reads each from the
parameter catalogue, where a person transcribed it and a second person
checked it (issue #77, D34). ``README.md`` lists them.

Pure functions: no file, no network, no clock, no argument changed
(``contracts/ENTRYPOINTS.md`` G1). They are parts of the erosion engine, not
its entry point.

A value that is not computed is the ``Missing`` of
``contracts/results/models.py`` with its reason (section 3 of
``contracts/CONVENTIONS.md``): never zero, never a default, never "not a
number". A missing day is never read as a day without rain.
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
from dataclasses import dataclass

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import DailySeries
from contracts.results.models import Missing as ResultMissing

from ._checks import (
    REASON_UNIT_NOT_ACCEPTED,
    YearMonth,
    ag_year_of,
    check_constant_types,
    check_fraction_table,
    check_mapping,
    check_series,
    check_start_month,
    check_text,
    combine_missing,
    constants_or_missing,
    is_date,
    is_year,
    is_year_month,
    label,
    missing_input,
    months_of_ag_year,
    real,
)

__all__ = [
    "PRECIPITATION_UNIT",
    "R_UNIT",
    "REASON_UNIT_NOT_ACCEPTED",
    "RFactorParts",
    "annual_sums",
    "checked_daily_precipitation",
    "daily_erosivity_index",
    "monthly_fractions",
    "monthly_sums",
    "r_by_year_and_month",
    "r_factor_parts",
    "yearly_ratios",
]

# The unit string of daily precipitation: CQ1 of contracts/CLIMATE_QUANTITIES.md
# (issue #77, D23). A series in another unit is not converted.
PRECIPITATION_UNIT = "mm day-1"

# The unit string of R in the International System: docs/METHODS.md M1.7
# (issue #77, D11). A level in another unit is not converted.
R_UNIT = "MJ mm ha-1 h-1 yr-1"


def checked_daily_precipitation(
    *, series: DailySeries
) -> dict[dt.date, float | ResultMissing] | ResultMissing:
    """The daily precipitation of ``series``, day by day, as this package reads it.

    Returns one item per day of the series, keyed by its date (C6.1), or a
    single ``Missing`` when the series cannot be read at all:

    - ``REASON_UNIT_NOT_ACCEPTED`` when the unit string of the series is not
      ``PRECIPITATION_UNIT``. Nothing is converted.

    Day by day:

    - a finite number of zero or more is the precipitation of that day;
    - a missing day is ``MISSING_INPUT`` naming the date and the reason the
      series gives. It is **never** zero rain;
    - a negative number, or one that is not finite, is ``NOT_COMPUTABLE``
      naming the date. It is never clipped to zero.
    """
    check_series(series)
    if series.unit != PRECIPITATION_UNIT:
        return ResultMissing(
            reason=REASON_UNIT_NOT_ACCEPTED,
            detail=(
                f"series '{series.quantity}' is in '{series.unit}'; daily precipitation "
                f"is read in '{PRECIPITATION_UNIT}' only and is not converted"
            ),
        )
    days: dict[dt.date, float | ResultMissing] = {}
    for item in series.days:
        name = f"precipitation of {item.date.isoformat()}"
        if item.value is None:
            days[item.date] = missing_input(name, item.missing)
        elif not math.isfinite(item.value):
            days[item.date] = ResultMissing(
                reason="NOT_COMPUTABLE", detail=f"{name} is not a finite number"
            )
        elif item.value < 0:
            days[item.date] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"{name} is negative; it is not clipped to zero",
            )
        else:
            days[item.date] = float(item.value)
    return days


def daily_erosivity_index(
    *,
    series: DailySeries,
    exponent: float | InputMissing | ResultMissing,
    threshold: float | InputMissing | ResultMissing,
    threshold_unit: str,
) -> dict[dt.date, float | ResultMissing] | ResultMissing:
    """The daily erosivity index of M1.2, day by day. PROPOSED form.

    ``index = P ** exponent`` on a day whose precipitation ``P`` is above
    ``threshold``, and ``0`` on a day at or below it. Used in relative terms
    only: it never gives the level of ``R``.

    Arguments, all by name and none with a default:

    - ``series``: the daily precipitation (``DailySeries``, unit
      ``PRECIPITATION_UNIT``).
    - ``exponent``: the exponent of the power law, from the parameter catalogue.
    - ``threshold``: the daily precipitation at or below which a day adds
      nothing, from the parameter catalogue.
    - ``threshold_unit``: the unit string the threshold carries; it must be
      ``PRECIPITATION_UNIT``.

    Returns one item per day, or a single ``Missing``:

    - ``MISSING_INPUT`` when the exponent or the threshold is missing (both
      named); ``NOT_COMPUTABLE`` when either is not a finite number;
    - ``REASON_UNIT_NOT_ACCEPTED`` when the threshold or the series is in
      another unit.

    A day whose precipitation is missing, negative or not finite keeps the
    ``Missing`` of ``checked_daily_precipitation``. A day whose index is not a
    finite real number is ``NOT_COMPUTABLE``.
    """
    constants = {"exponent": exponent, "threshold": threshold}
    check_constant_types(constants)
    check_text("threshold_unit", threshold_unit)
    check_series(series)

    values = constants_or_missing(constants)
    if isinstance(values, ResultMissing):
        return values
    if threshold_unit != PRECIPITATION_UNIT:
        return ResultMissing(
            reason=REASON_UNIT_NOT_ACCEPTED,
            detail=(
                f"threshold is in '{threshold_unit}'; it is compared with daily "
                f"precipitation in '{PRECIPITATION_UNIT}' and is not converted"
            ),
        )
    precipitation = checked_daily_precipitation(series=series)
    if isinstance(precipitation, ResultMissing):
        return precipitation

    index: dict[dt.date, float | ResultMissing] = {}
    for date, amount in precipitation.items():
        if isinstance(amount, ResultMissing):
            index[date] = amount
        elif amount <= values["threshold"]:
            index[date] = 0.0
        else:
            try:
                index[date] = real(amount ** values["exponent"])
            except ArithmeticError:
                index[date] = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"the daily index of {date.isoformat()} is not a finite real "
                        "number for these arguments"
                    ),
                )
    return index


def monthly_sums(
    *, daily: dict[dt.date, float | ResultMissing] | ResultMissing
) -> dict[YearMonth, float | ResultMissing] | ResultMissing:
    """The sum of a daily table over each calendar month (C5.1, C6.1).

    ``daily`` is what ``daily_erosivity_index`` or
    ``checked_daily_precipitation`` returns. Every calendar month with at least
    one day in ``daily`` gets one item, keyed by ``(year, month)``:

    - ``NO_COVERAGE`` when ``daily`` does not hold every day of the month (the
      extent of the series; PROPOSED by analogy with C5.5);
    - ``MISSING_INPUT`` when a day of the month is missing, naming each such
      day and its reason. No gap is filled (C3.3, C3.4). PROPOSED;
    - otherwise the sum of the days.

    A ``Missing`` in place of the whole table gives ``MISSING_INPUT`` naming it.
    """
    check_mapping("daily", daily, is_date, "a date")
    if isinstance(daily, ResultMissing):
        return missing_input("daily", daily)

    by_month: dict[YearMonth, dict[dt.date, float | ResultMissing]] = {}
    for date in sorted(daily):
        by_month.setdefault((date.year, date.month), {})[date] = daily[date]

    sums: dict[YearMonth, float | ResultMissing] = {}
    for year_month, days in by_month.items():
        length = calendar.monthrange(*year_month)[1]
        if len(days) < length:
            sums[year_month] = ResultMissing(
                reason="NO_COVERAGE",
                detail=(
                    f"the daily values cover {len(days)} of the {length} days of "
                    f"{label(year_month)}"
                ),
            )
            continue
        absent = [
            f"{date.isoformat()} (reason {item.reason})"
            for date, item in days.items()
            if isinstance(item, ResultMissing)
        ]
        if absent:
            sums[year_month] = ResultMissing(
                reason="MISSING_INPUT",
                detail=f"{label(year_month)}: daily values missing on "
                + ", ".join(absent),
            )
            continue
        try:
            sums[year_month] = real(math.fsum(days.values()))
        except ArithmeticError:
            sums[year_month] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"the sum of {label(year_month)} is not a finite number",
            )
    return sums


def annual_sums(
    *,
    monthly: dict[YearMonth, float | ResultMissing] | ResultMissing,
    start_month: int,
) -> dict[int, float | ResultMissing] | ResultMissing:
    """The sum of a monthly table over each agricultural year (C5.3).

    ``start_month`` is the start month of the agricultural year of the case
    (C5.4); ``1`` gives calendar years. Which year M1.2 means is OPEN.

    Every agricultural year with at least one month in ``monthly`` gets one
    item, keyed by the calendar year it begins in (``ag_year``, C5.3):

    - ``NO_COVERAGE`` when one of its twelve months is not in ``monthly`` or is
      itself ``NO_COVERAGE`` (C5.5);
    - ``MISSING_INPUT`` when a month is missing for another reason, naming it;
    - otherwise the sum of the twelve months.

    The annual sum of the daily index is used in relative terms only.
    """
    check_mapping("monthly", monthly, is_year_month, "a (year, month) pair")
    start_month = check_start_month(start_month)
    if isinstance(monthly, ResultMissing):
        return missing_input("monthly", monthly)

    years = sorted({ag_year_of(year_month, start_month) for year_month in monthly})
    sums: dict[int, float | ResultMissing] = {}
    for ag_year in years:
        months = months_of_ag_year(ag_year, start_month)
        what = f"agricultural year {ag_year} (start month {start_month})"
        uncovered = [
            label(year_month)
            for year_month in months
            if year_month not in monthly
            or (
                isinstance(monthly[year_month], ResultMissing)
                and monthly[year_month].reason == "NO_COVERAGE"
            )
        ]
        if uncovered:
            sums[ag_year] = ResultMissing(
                reason="NO_COVERAGE",
                detail=f"{what} is not covered in full: " + ", ".join(uncovered),
            )
            continue
        absent = [
            f"month {label(year_month)} is missing, reason {monthly[year_month].reason}"
            for year_month in months
            if isinstance(monthly[year_month], ResultMissing)
        ]
        if absent:
            sums[ag_year] = ResultMissing(
                reason="MISSING_INPUT", detail=f"{what}: " + "; ".join(absent)
            )
            continue
        try:
            sums[ag_year] = real(
                math.fsum(monthly[year_month] for year_month in months)
            )
        except ArithmeticError:
            sums[ag_year] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"the sum of {what} is not a finite number",
            )
    return sums


def _carry(name: str, missing: ResultMissing) -> ResultMissing:
    """A value of a year whose annual sum is missing: ``NO_COVERAGE`` stays, else ``MISSING_INPUT``."""
    return combine_missing({name: missing})


def monthly_fractions(
    *,
    monthly: dict[YearMonth, float | ResultMissing] | ResultMissing,
    start_month: int,
) -> dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing:
    """The fraction of the annual sum that falls in each month, year by year.

    ``monthly`` is what ``monthly_sums`` returns: of the daily index for M1.2,
    or of the control of ``control.py``. For each agricultural year that
    ``annual_sums`` lists, twelve items keyed by ``(year, month)``:

    - when the annual sum is a number above or below zero: the sum of the
      month divided by the annual sum. The twelve add up to one;
    - when the annual sum is zero (a year with no erosive day): every month is
      ``NOT_COMPUTABLE``. Never zero, never split equally;
    - when the annual sum is missing: ``NO_COVERAGE`` if it is, else
      ``MISSING_INPUT`` naming it.

    Used in relative terms only.
    """
    sums = annual_sums(monthly=monthly, start_month=start_month)
    if isinstance(sums, ResultMissing):
        return sums

    fractions: dict[int, dict[YearMonth, float | ResultMissing]] = {}
    for ag_year, total in sums.items():
        months = months_of_ag_year(ag_year, start_month)
        name = f"the annual sum of agricultural year {ag_year}"
        if isinstance(total, ResultMissing):
            fractions[ag_year] = {m: _carry(name, total) for m in months}
        elif total == 0:
            zero = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{name} is zero (no erosive day): no monthly fraction is defined; "
                    "it is not zero and not split equally"
                ),
            )
            fractions[ag_year] = {m: zero for m in months}
        else:
            year_fractions: dict[YearMonth, float | ResultMissing] = {}
            for year_month in months:
                try:
                    year_fractions[year_month] = real(monthly[year_month] / total)
                except ArithmeticError:
                    year_fractions[year_month] = ResultMissing(
                        reason="NOT_COMPUTABLE",
                        detail=f"the fraction of {label(year_month)} is not a finite number",
                    )
            fractions[ag_year] = year_fractions
    return fractions


def yearly_ratios(
    *, annual: dict[int, float | ResultMissing] | ResultMissing
) -> dict[int, float | ResultMissing] | ResultMissing:
    """The ratio of each year's sum to the mean over the record.

    ``annual`` is what ``annual_sums`` returns. The mean is taken over the
    years whose sum is a number (PROPOSED); over those years the ratios
    average to one. A year whose sum is missing has a missing ratio
    (``NO_COVERAGE`` if its sum is, else ``MISSING_INPUT``). When the mean is
    zero, every ratio that would divide by it is ``NOT_COMPUTABLE``.

    Used in relative terms only.
    """
    check_mapping("annual", annual, is_year, "an agricultural year")
    if isinstance(annual, ResultMissing):
        return missing_input("annual", annual)

    present = [
        total for total in annual.values() if not isinstance(total, ResultMissing)
    ]
    mean = math.fsum(present) / len(present) if present else None

    ratios: dict[int, float | ResultMissing] = {}
    for ag_year in sorted(annual):
        total = annual[ag_year]
        if isinstance(total, ResultMissing):
            ratios[ag_year] = _carry(
                f"the annual sum of agricultural year {ag_year}", total
            )
        elif mean == 0:
            ratios[ag_year] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"the mean annual sum over the {len(present)} years with a sum is "
                    "zero: no ratio is defined"
                ),
            )
        else:
            try:
                ratios[ag_year] = real(total / mean)
            except ArithmeticError:
                ratios[ag_year] = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=f"the ratio of agricultural year {ag_year} is not a finite number",
                )
    return ratios


def r_by_year_and_month(
    *,
    mean_annual_r: float | InputMissing | ResultMissing,
    mean_annual_r_unit: str,
    monthly_fractions: dict[int, dict[YearMonth, float | ResultMissing]]
    | ResultMissing,
    yearly_ratios: dict[int, float | ResultMissing] | ResultMissing,
) -> dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing:
    """``R`` for each year and month: ``mean_annual_r * fraction * ratio``. PROPOSED form.

    Arguments, all by name and none with a default:

    - ``mean_annual_r``: the mean annual level of ``R`` at the field (S4,
      interpolated to the field by the caller). An input only: nothing here
      computes or corrects it.
    - ``mean_annual_r_unit``: the unit string it carries; it must be ``R_UNIT``.
    - ``monthly_fractions``: what ``monthly_fractions`` returns for the index.
    - ``yearly_ratios``: what ``yearly_ratios`` returns for the index.

    Returns, for each agricultural year of ``monthly_fractions``, its twelve
    months keyed by ``(year, month)``, or a single ``Missing``:

    - ``MISSING_INPUT`` naming ``mean_annual_r`` when the level is missing;
      ``NOT_COMPUTABLE`` when it is not a finite number;
    - ``REASON_UNIT_NOT_ACCEPTED`` when its unit is not ``R_UNIT``;
    - ``MISSING_INPUT`` naming the table when a table is a ``Missing``.

    A month whose fraction or yearly ratio is missing is missing:
    ``NO_COVERAGE`` when every missing part is, else ``MISSING_INPUT`` naming
    each. The twelve months of a year add up to ``mean_annual_r * ratio``.
    The unit string of a monthly value is OPEN.
    """
    constants = {"mean_annual_r": mean_annual_r}
    check_constant_types(constants)
    check_text("mean_annual_r_unit", mean_annual_r_unit)
    check_fraction_table("monthly_fractions", monthly_fractions)
    check_mapping("yearly_ratios", yearly_ratios, is_year, "an agricultural year")

    values = constants_or_missing(constants)
    if isinstance(values, ResultMissing):
        return values
    if mean_annual_r_unit != R_UNIT:
        return ResultMissing(
            reason=REASON_UNIT_NOT_ACCEPTED,
            detail=(
                f"mean_annual_r is in '{mean_annual_r_unit}'; R is read in '{R_UNIT}' "
                "and is not converted"
            ),
        )
    for name, table in (
        ("monthly_fractions", monthly_fractions),
        ("yearly_ratios", yearly_ratios),
    ):
        if isinstance(table, ResultMissing):
            return missing_input(name, table)

    level = values["mean_annual_r"]
    result: dict[int, dict[YearMonth, float | ResultMissing]] = {}
    for ag_year in sorted(monthly_fractions):
        if ag_year in yearly_ratios:
            ratio = yearly_ratios[ag_year]
        else:
            ratio = ResultMissing(
                reason="MISSING_INPUT",
                detail=f"yearly_ratios has no item for agricultural year {ag_year}",
            )
        cells: dict[YearMonth, float | ResultMissing] = {}
        for year_month, fraction in monthly_fractions[ag_year].items():
            absent = combine_missing(
                {
                    f"the monthly fraction of {label(year_month)}": fraction,
                    f"the yearly ratio of agricultural year {ag_year}": ratio,
                }
            )
            if absent is not None:
                cells[year_month] = absent
                continue
            try:
                cells[year_month] = real(level * fraction * ratio)
            except ArithmeticError:
                cells[year_month] = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=f"R of {label(year_month)} is not a finite number",
                )
        result[ag_year] = cells
    return result


@dataclass(frozen=True)
class RFactorParts:
    """Every step of M1.2 for one series, as ``r_factor_parts`` returns them.

    Each field is the table of its step or a single ``Missing``. A missing
    level makes ``r_by_year_and_month`` missing while the fractions and the
    ratios stay.
    """

    daily_index: dict[dt.date, float | ResultMissing] | ResultMissing
    monthly_index_sums: dict[YearMonth, float | ResultMissing] | ResultMissing
    annual_index_sums: dict[int, float | ResultMissing] | ResultMissing
    monthly_fractions: dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing
    yearly_ratios: dict[int, float | ResultMissing] | ResultMissing
    r_by_year_and_month: (
        dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing
    )


def r_factor_parts(
    *,
    series: DailySeries,
    exponent: float | InputMissing | ResultMissing,
    threshold: float | InputMissing | ResultMissing,
    threshold_unit: str,
    start_month: int,
    mean_annual_r: float | InputMissing | ResultMissing,
    mean_annual_r_unit: str,
) -> RFactorParts:
    """The steps of M1.2 one after the other, every intermediate table kept.

    No argument has a default. See each step for what it returns.
    """
    index = daily_erosivity_index(
        series=series,
        exponent=exponent,
        threshold=threshold,
        threshold_unit=threshold_unit,
    )
    sums = monthly_sums(daily=index)
    annual = annual_sums(monthly=sums, start_month=start_month)
    fractions = monthly_fractions(monthly=sums, start_month=start_month)
    ratios = yearly_ratios(annual=annual)
    r_values = r_by_year_and_month(
        mean_annual_r=mean_annual_r,
        mean_annual_r_unit=mean_annual_r_unit,
        monthly_fractions=fractions,
        yearly_ratios=ratios,
    )
    return RFactorParts(
        daily_index=index,
        monthly_index_sums=sums,
        annual_index_sums=annual,
        monthly_fractions=fractions,
        yearly_ratios=ratios,
        r_by_year_and_month=r_values,
    )
