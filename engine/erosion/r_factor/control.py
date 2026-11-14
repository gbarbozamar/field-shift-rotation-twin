"""Control of the monthly fraction of M1.2: the regression on monthly precipitation. PROPOSED.

M1.2 of ``docs/METHODS.md`` names a control of the monthly fraction: the
regression of ``R`` on monthly precipitation (S7; ``docs/METHODS.md`` says its
equation was taken from S4). This module computes it and puts its monthly
fractions beside those of the daily index. **Comparing them is a report, not a
correction**: nothing here changes a fraction of the index, and no level of
agreement is judged (that would be a threshold, which a person supplies).

The form, PROPOSED until a person checks it against S7 as S4 gives it::

    control(month) = coefficient * P(month) ** exponent

``P(month)`` is the sum of the daily precipitation of the month (unit of the
days: ``mm day-1``, so a depth over the month). Its fractions are those of
``erosivity.monthly_fractions`` applied to ``control(month)``.

**This module holds no coefficient.** ``coefficient`` and ``exponent`` are
arguments without a default, read by the caller from the parameter catalogue.

Pure functions: no file, no network, no clock, no argument changed.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import DailySeries
from contracts.results.models import Missing as ResultMissing

from ._checks import (
    YearMonth,
    check_constant_types,
    check_fraction_table,
    check_series,
    combine_missing,
    constants_or_missing,
    label,
    missing_input,
    real,
)
from .erosivity import checked_daily_precipitation, monthly_sums

__all__ = [
    "FractionComparison",
    "compare_monthly_fractions",
    "control_monthly_erosivity",
]


def control_monthly_erosivity(
    *,
    series: DailySeries,
    coefficient: float | InputMissing | ResultMissing,
    exponent: float | InputMissing | ResultMissing,
) -> dict[YearMonth, float | ResultMissing] | ResultMissing:
    """The control of M1.2 for each calendar month: ``coefficient * P(month) ** exponent``.

    Arguments, all by name and none with a default:

    - ``series``: the daily precipitation (``DailySeries``, unit ``mm day-1``).
    - ``coefficient``, ``exponent``: the coefficients of the regression, from
      the parameter catalogue.

    Returns one item per calendar month with a day in the series, keyed by
    ``(year, month)``, or a single ``Missing``:

    - ``MISSING_INPUT`` when a coefficient is missing (each named);
      ``NOT_COMPUTABLE`` when one is not a finite number;
    - ``REASON_UNIT_NOT_ACCEPTED`` when the series is not in ``mm day-1``.

    A month whose precipitation sum is missing keeps the ``Missing`` of
    ``erosivity.monthly_sums`` (``NO_COVERAGE`` or ``MISSING_INPUT``); a month
    whose value is not a finite real number is ``NOT_COMPUTABLE``.

    Pass the result to ``erosivity.monthly_fractions`` for the fractions of the
    control, then to ``compare_monthly_fractions``.
    """
    constants = {"coefficient": coefficient, "exponent": exponent}
    check_constant_types(constants)
    check_series(series)
    values = constants_or_missing(constants)
    if isinstance(values, ResultMissing):
        return values
    precipitation = checked_daily_precipitation(series=series)
    if isinstance(precipitation, ResultMissing):
        return precipitation
    sums = monthly_sums(daily=precipitation)

    control: dict[YearMonth, float | ResultMissing] = {}
    for year_month, amount in sums.items():
        if isinstance(amount, ResultMissing):
            control[year_month] = amount
            continue
        try:
            control[year_month] = real(
                values["coefficient"] * amount ** values["exponent"]
            )
        except ArithmeticError:
            control[year_month] = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"the control of {label(year_month)} is not a finite real number "
                    "for these arguments"
                ),
            )
    return control


@dataclass(frozen=True)
class FractionComparison:
    """One month of the comparison: the two fractions and their difference.

    ``difference`` is ``index_fraction - control_fraction``. It is reported,
    never applied.
    """

    index_fraction: float | ResultMissing
    control_fraction: float | ResultMissing
    difference: float | ResultMissing


def compare_monthly_fractions(
    *,
    index_fractions: dict[int, dict[YearMonth, float | ResultMissing]] | ResultMissing,
    control_fractions: dict[int, dict[YearMonth, float | ResultMissing]]
    | ResultMissing,
) -> dict[int, dict[YearMonth, FractionComparison]] | ResultMissing:
    """The monthly fractions of the index and of the control, side by side.

    Both arguments are what ``erosivity.monthly_fractions`` returns. For every
    agricultural year and month in either, one ``FractionComparison``. A month
    present in one table only, or missing in either, has a missing difference:
    ``NO_COVERAGE`` when every missing part is, else ``MISSING_INPUT`` naming
    each. A ``Missing`` in place of a whole table gives ``MISSING_INPUT``
    naming it.

    This is a report. Neither fraction is changed, and no agreement is judged.
    """
    check_fraction_table("index_fractions", index_fractions)
    check_fraction_table("control_fractions", control_fractions)
    for name, table in (
        ("index_fractions", index_fractions),
        ("control_fractions", control_fractions),
    ):
        if isinstance(table, ResultMissing):
            return missing_input(name, table)

    report: dict[int, dict[YearMonth, FractionComparison]] = {}
    for ag_year in sorted(set(index_fractions) | set(control_fractions)):
        index_year = index_fractions.get(ag_year, {})
        control_year = control_fractions.get(ag_year, {})
        months: dict[YearMonth, FractionComparison] = {}
        for year_month in sorted(set(index_year) | set(control_year)):
            parts = {}
            for what, year_table in (("index", index_year), ("control", control_year)):
                parts[f"the {what} fraction of {label(year_month)}"] = year_table.get(
                    year_month,
                    ResultMissing(
                        reason="MISSING_INPUT",
                        detail=(
                            f"the {what} fractions have no item for {label(year_month)} "
                            f"in agricultural year {ag_year}"
                        ),
                    ),
                )
            index_value, control_value = parts.values()
            absent = combine_missing(parts)
            if absent is not None:
                difference: float | ResultMissing = absent
            else:
                try:
                    difference = real(index_value - control_value)
                except ArithmeticError:
                    difference = ResultMissing(
                        reason="NOT_COMPUTABLE",
                        detail=f"the difference of {label(year_month)} is not a finite number",
                    )
            months[year_month] = FractionComparison(
                index_fraction=index_value,
                control_fraction=control_value,
                difference=difference,
            )
        report[ag_year] = months
    return report
