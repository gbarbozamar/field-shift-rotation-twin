"""Monthly fraction of R from a published monthly erosivity climatology (D69).

PROPOSED (blueprint section 3.7). Decision D69 of issue #77 (14 November 2026)
sets the route of the first release while sources S5 and S6 stay behind
paywalls: the fraction of a month is that month's published erosivity over the
sum of the twelve. Decision USER-G of the lead developer (the same day) defers
the variation between years, so the same twelve fractions hold for every
agricultural year. Both are recorded in ``docs/SCIENCE_DECISIONS.md``.

Nothing here is a value of the method. The twelve monthly values and the mean
annual level are arguments without a default; the caller reads them from
where a person put them after checking them against the source (D34, D66).
The licence of the climatology named by D69 is still to be confirmed by the
team (D69, "Still open"), and no value of it is in this repository.
``README.md`` in this folder, section "Climatological monthly fraction (D69)",
says what is PROPOSED and what is OPEN.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

from ._checks import (
    MISSING,
    REASON_UNIT_NOT_ACCEPTED,
    YearMonth,
    check_constant_types,
    check_start_month,
    check_text,
    constants_or_missing,
    describe_missing,
    finite,
    is_year,
    label,
    months_of_ag_year,
    real,
)
from .erosivity import R_UNIT

CALENDAR_MONTHS = tuple(range(1, 12 + 1))


def _month_name(month: int) -> str:
    return f"month {month:02d}"


def climatological_monthly_fractions(
    *,
    monthly_erosivity: Mapping[int, float | InputMissing | ResultMissing],
) -> dict[int, float | ResultMissing] | ResultMissing:
    """The share of each calendar month in the published annual erosivity. PROPOSED form.

    ``monthly_erosivity`` holds exactly the twelve calendar months, keyed by
    their number (January is 1, C5.1), each a number or a ``Missing`` of
    either contract shape. All twelve come in one table, so they share one
    unit and the fraction has none.

    Returns the twelve fractions keyed by month number, adding up to one
    within floating point, or a single ``Missing``:

    - ``MISSING_INPUT`` naming every missing month: the sum of the twelve is
      not defined without them (C3.3). No month is filled;
    - ``NOT_COMPUTABLE`` naming every month that is not a finite number, or
      that is below zero (never clipped);
    - ``NOT_COMPUTABLE`` when the twelve add up to zero: no fraction is
      defined, and the year is not split equally.
    """
    if not isinstance(monthly_erosivity, Mapping):
        raise TypeError(
            "monthly_erosivity: expected a dict of the twelve calendar months; "
            f"got {type(monthly_erosivity).__name__}"
        )
    keys = set(monthly_erosivity)
    for key in keys:
        if isinstance(key, bool) or not isinstance(key, int):
            raise TypeError(
                f"monthly_erosivity: every key is a month number; got {key!r}"
            )
    if keys != set(CALENDAR_MONTHS):
        raise ValueError(
            "monthly_erosivity: expected exactly the twelve calendar months 1 to 12 "
            "(C5.1); a month that has no value is given as a Missing with its reason"
        )
    numbers = {_month_name(m): monthly_erosivity[m] for m in CALENDAR_MONTHS}
    check_constant_types(numbers)

    values = constants_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    negative = [name for name, value in values.items() if value < 0]
    if negative:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(
                f"{name} is below zero; it is not clipped" for name in negative
            ),
        )
    total = finite(math.fsum(values.values()))
    if total is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="the sum of the twelve months is not a finite number",
        )
    if total == 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "the twelve months add up to zero: no monthly fraction is defined; "
                "it is not zero and not split equally"
            ),
        )
    fractions: dict[int, float | ResultMissing] = {}
    for month in CALENDAR_MONTHS:
        try:
            fractions[month] = real(values[_month_name(month)] / total)
        except ArithmeticError:
            fractions[month] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"the fraction of {_month_name(month)} is not a finite number",
            )
    return fractions


def climatological_r_by_year_and_month(
    *,
    mean_annual_r: float | InputMissing | ResultMissing,
    mean_annual_r_unit: str,
    fractions: dict[int, float | ResultMissing] | ResultMissing,
    ag_years: Iterable[int],
    start_month: int,
) -> dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing:
    """``R`` for each year and month: ``mean_annual_r * fraction(month)``. PROPOSED form.

    The same twelve fractions hold for every agricultural year: the variation
    between years is deferred (USER-G) and the climatology gives none (D69).
    The table has the shape of ``r_by_year_and_month`` of ``erosivity.py``, so
    a caller can take either.

    Arguments, all by name and none with a default:

    - ``mean_annual_r``: the mean annual level of ``R`` at the field. An input
      only: nothing here computes or corrects it. How the published level
      reaches the field is not settled here.
    - ``mean_annual_r_unit``: its unit string; it must be ``R_UNIT`` (D11).
    - ``fractions``: what ``climatological_monthly_fractions`` returns.
    - ``ag_years``: the agricultural years to lay out (D47), each an integer.
    - ``start_month``: the start month of the case (C5.4).

    Returns, for each agricultural year, its twelve months keyed by
    ``(year, month)`` (C5.3), or a single ``Missing``: ``MISSING_INPUT``
    naming ``mean_annual_r`` or ``fractions`` when one is missing;
    ``NOT_COMPUTABLE`` when the level is not a finite number;
    ``REASON_UNIT_NOT_ACCEPTED`` when its unit is not ``R_UNIT``. A month
    whose fraction is missing is ``MISSING_INPUT`` naming it. The twelve
    months of a year add up to ``mean_annual_r``. The unit string of a
    monthly value is OPEN, as in ``erosivity.py``.
    """
    constants = {"mean_annual_r": mean_annual_r}
    check_constant_types(constants)
    check_text("mean_annual_r_unit", mean_annual_r_unit)
    start = check_start_month(start_month)
    if isinstance(ag_years, (str, bytes)) or not isinstance(ag_years, Iterable):
        raise TypeError(
            f"ag_years: expected the agricultural years as integers; got {type(ag_years).__name__}"
        )
    years = list(ag_years)
    for year in years:
        if not is_year(year):
            raise TypeError(f"ag_years: every item is an integer year; got {year!r}")
    if not isinstance(fractions, ResultMissing):
        if not isinstance(fractions, Mapping) or set(fractions) != set(CALENDAR_MONTHS):
            raise TypeError(
                "fractions: expected what climatological_monthly_fractions returns: "
                "the twelve calendar months, or one Missing"
            )
        for month, item in fractions.items():
            if isinstance(item, ResultMissing):
                continue
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise TypeError(
                    f"fractions: every item is a number or a Missing; got "
                    f"{type(item).__name__} for month {month}"
                )

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
    if isinstance(fractions, ResultMissing):
        return ResultMissing(
            reason="MISSING_INPUT", detail=describe_missing("fractions", fractions)
        )

    level = values["mean_annual_r"]
    result: dict[int, dict[YearMonth, float | ResultMissing]] = {}
    for ag_year in sorted(set(years)):
        cells: dict[YearMonth, float | ResultMissing] = {}
        for year_month in months_of_ag_year(ag_year, start):
            fraction = fractions[year_month[1]]
            if isinstance(fraction, MISSING):
                cells[year_month] = ResultMissing(
                    reason="MISSING_INPUT",
                    detail=describe_missing(
                        f"the climatological fraction of {_month_name(year_month[1])}",
                        fraction,
                    ),
                )
                continue
            try:
                cells[year_month] = real(level * fraction)
            except ArithmeticError:
                cells[year_month] = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=f"R of {label(year_month)} is not a finite number",
                )
        result[ag_year] = cells
    return result
