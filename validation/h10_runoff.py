"""The H10 runoff comparison: EP3's yearly runoff for the La Estanzuela
runoff plots set next to the measured yearly runoff (entry H10 of
``docs/VALIDATION.md``; unit l0/validation-h10-d230, issue #355).

Decision D229 of issue #77, 15 November 2026: H10 is "the yearly runoff of
EP3 for the La Estanzuela runoff plots in 2017, 2018 and 2019, set next to
the yearly average runoff printed by Grahmann et al. (2022), Table 5". The
runoff experiment stays separate from the demonstration (D71).

Decision D230 of issue #77, 15 November 2026 (taken under the delegation of
D161, before any result): "H10 passes when both conditions hold. (1) The
percent bias of EP3's three yearly runoff values [...] is within [the bound]. [...]
PBIAS = 100 × Σ(measured − modelled) / Σ measured over the three years
(Moriasi et al. 2007, Eq. 2); a positive value means EP3 underestimates.
(2) EP3 ranks the three years as the source does." Each year's relative
error is reported with no pass mark. One run of EP3 is set against the
six-plot mean, by calendar year. A modelled single event above the cap the
source states for the plot tanks is reported, and the rule does not change.

This module holds no value of the science. The measured values, the
modelled values, the bound of the percent bias and the cap of an event are
all arguments, and the bound and the cap have no default: the caller passes
the numbers of D230, and the measured values come from a fixture a person
transcribes and signs (D34, D66). The only number written here, apart
from zero, is the 100 of the formula of D230, which turns a ratio into a
percent.

Pure function: no file, no clock, no network. Sums, the percent bias and the
orders are computed exactly, as rational numbers built from the stored
values, so a value at the edge of the bound is not moved by rounding.

What this module adds to D230, all PROPOSED (blueprint section 3.7):

- **The years compared** are the years of the measured values. A measured
  year with no modelled value, or a modelled year with no measured value,
  gives no verdict, with its reason: the two sides must cover the same years.
- **A missing value** (a ``Missing`` of ``contracts/results/``, C3.2) or a
  value that is not a finite number, on either side, gives no verdict, with
  its reason. Nothing is filled and nothing is read as zero. The relative
  error of each year where both values are numbers is still reported.
- **No percent bias** when the sum of the measured values is not above zero:
  the formula divides by it, and below zero its sign would no longer mean
  what D230 says. D230 does not say what happens then.
- **"Within" the bound** is read as ``abs(PBIAS) <= bound``: a value exactly at
  the bound passes.
- **The order** of the years is highest runoff first, as D230 states the
  source's order ("2018, then 2019, then 2017"). A tie of two years on
  either side gives no order, with the reason, as entry D0 does for a tie of
  two means; the order condition then has no verdict.
- **The relative error** of a year is ``100 × (measured − modelled) /
  measured``, in percent, with the sign of the percent bias: positive means
  EP3 underestimates that year. A year whose measured value is zero has
  none, with its reason. It carries no pass mark (D230).
- **The verdict of H10** is "pass" when both conditions pass, "fail" when
  either fails (one failed condition is enough for "both conditions hold" to
  be false), and no verdict otherwise, with the reasons.
- **An event** is one day of the modelled daily runoff. The flag is raised
  when a day is above the cap (strictly above: D230 says "above"); it is
  lowered only when every day given is a number not above the cap; a day
  with no number and no day above the cap give no flag, with the reason.
  When no daily runoff is given there is no flag, with the reason. The flag
  never changes a verdict (D230).

OPEN, for the lead developer (D230 does not say; this module does what is
written above):

1. A tie in an order. Options: (a) no order and no verdict for the
   condition, as here; (b) tied years at the same rank, matched when the
   other side ties the same years.
2. The verdict of H10 when one condition has no verdict. Options: (a) "fail"
   when the other fails, no verdict otherwise, as here; (b) no verdict
   whenever either condition has none.
3. The sign of the relative error of a year. Options: (a) the sign of the
   percent bias, as here; (b) ``(modelled − measured) / measured``.
4. Modelled years beyond the measured ones (a longer run). Options: (a) no
   verdict, as here, so the caller passes exactly the years compared;
   (b) the extra years left out of the comparison and listed.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from contracts.results.models import Missing

PERCENT = 100  # the 100 of the formula of D230: a ratio written as a percent

Verdict = Literal["pass", "fail"]


@dataclass(frozen=True)
class YearError:
    """One year of the comparison: the two values and the relative error, in
    percent, with the sign of the percent bias. ``measured`` or ``modelled``
    is ``None`` when that side has no number for the year, and
    ``relative_error_percent`` is ``None`` with ``reason`` when it cannot be
    computed. No pass mark (D230)."""

    year: int
    measured: float | None
    modelled: float | None
    relative_error_percent: float | None
    reason: str | None


@dataclass(frozen=True)
class YearOrder:
    """The years ordered by runoff, highest first; ``None`` with ``reason``
    when no order is given."""

    order: tuple[int, ...] | None
    reason: str | None


@dataclass(frozen=True)
class Condition:
    """The verdict of one condition of D230, or of H10 itself; ``None`` with
    ``reason`` when there is no verdict. A failed verdict also says why."""

    verdict: Verdict | None
    reason: str | None


@dataclass(frozen=True)
class LargeEvents:
    """The modelled days whose runoff is above the cap (D230). ``flagged`` is
    ``True`` when there is at least one, ``False`` when every day given is a
    number not above the cap, and ``None`` with ``reason`` otherwise.
    ``days_without_value`` lists, with their reason, the days given with no
    number."""

    flagged: bool | None
    days_above_cap: tuple[tuple[dt.date, float], ...]
    days_without_value: tuple[tuple[dt.date, str], ...]
    reason: str | None


@dataclass(frozen=True)
class H10Result:
    """Everything the H10 comparison reports (D230)."""

    years: tuple[int, ...]
    pbias_percent: float | None
    pbias_reason: str | None
    year_errors: tuple[YearError, ...]
    measured_order: YearOrder
    modelled_order: YearOrder
    orders_match: bool | None
    pbias_condition: Condition
    order_condition: Condition
    h10: Condition
    large_events: LargeEvents


def _number(value: object) -> float | None:
    """The value as a float when it is a finite number, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _why_not_a_number(value: object) -> str:
    if value is None:
        return "not given"
    if isinstance(value, Missing):
        detail = f": {value.detail}" if value.detail else ""
        return f"missing with the reason {value.reason}{detail}"
    return "not a finite number"


def _problems(
    measured: Mapping[int, object], modelled: Mapping[int, object]
) -> list[str]:
    """Every reason the comparison gives no verdict, in a fixed order."""
    problems = []
    if not measured:
        problems.append("no measured year is given")
    for year in sorted(set(measured) - set(modelled)):
        problems.append(f"the modelled values have no year {year}")
    for year in sorted(set(modelled) - set(measured)):
        problems.append(
            f"the modelled values hold the year {year}, which the measured values "
            "do not: the two sides must cover the same years"
        )
    for side, values in (("measured", measured), ("modelled", modelled)):
        for year in sorted(values):
            if _number(values[year]) is None:
                problems.append(
                    f"the {side} value of {year} is {_why_not_a_number(values[year])}"
                )
    return problems


def _year_error(year: int, measured: object, modelled: object) -> YearError:
    m = _number(measured)
    s = _number(modelled)
    if m is None or s is None:
        sides = [
            f"the {side} value is {_why_not_a_number(value)}"
            for side, value, number in (
                ("measured", measured, m),
                ("modelled", modelled, s),
            )
            if number is None
        ]
        return YearError(year, m, s, None, "; ".join(sides))
    if m == 0:
        return YearError(
            year, m, s, None, "the measured value is zero: no relative error"
        )
    error = PERCENT * (Fraction(m) - Fraction(s)) / Fraction(m)
    return YearError(year, m, s, float(error), None)


def _order(side: str, values: Mapping[int, Fraction]) -> YearOrder:
    years = sorted(values)
    tied = [
        (first, second)
        for first, second in itertools.combinations(years, 2)
        if values[first] == values[second]
    ]
    if tied:
        listed = "; ".join(f"{first} and {second}" for first, second in tied)
        return YearOrder(
            None,
            f"the {side} values of {listed} are equal: a tie gives no order, as in "
            "entry D0 (OPEN)",
        )
    return YearOrder(
        tuple(sorted(years, key=lambda year: values[year], reverse=True)), None
    )


def _large_events(
    modelled_daily: Mapping[dt.date, object] | None, cap: Fraction, cap_mm: float
) -> LargeEvents:
    if modelled_daily is None:
        return LargeEvents(
            None, (), (), "no daily modelled runoff was given: no event is checked"
        )
    above = []
    without = []
    for day in sorted(modelled_daily):
        number = _number(modelled_daily[day])
        if number is None:
            without.append((day, _why_not_a_number(modelled_daily[day])))
        elif Fraction(number) > cap:
            above.append((day, number))
    if above:
        return LargeEvents(True, tuple(above), tuple(without), None)
    if without:
        return LargeEvents(
            None,
            (),
            tuple(without),
            f"no day given is above {cap_mm} mm, but {len(without)} day(s) have no "
            "number, so an event above the cap cannot be ruled out",
        )
    return LargeEvents(False, (), (), None)


def _argument(name: str, value: float) -> Fraction:
    number = _number(value)
    if number is None or number < 0:
        raise ValueError(f"{name} must be a finite number not below zero")
    return Fraction(number)


def compare_h10_runoff(
    measured: Mapping[int, float | Missing],
    modelled: Mapping[int, float | Missing],
    *,
    pbias_bound_percent: float,
    event_cap_mm: float,
    modelled_daily: Mapping[dt.date, float | Missing] | None = None,
) -> H10Result:
    """The H10 comparison of D230.

    ``measured`` and ``modelled`` map each calendar year to its yearly
    runoff in mm, or to a ``Missing``. ``pbias_bound_percent`` is the bound
    of condition (1) and ``event_cap_mm`` the cap of a single event; neither
    has a default, the caller passes the numbers of D230. ``modelled_daily``
    maps each day of the run to its modelled runoff in mm; when it is not
    given, no event is checked. The module docstring says what is PROPOSED
    and what is OPEN.
    """
    bound = _argument("pbias_bound_percent", pbias_bound_percent)
    cap = _argument("event_cap_mm", event_cap_mm)
    large_events = _large_events(modelled_daily, cap, float(cap))
    year_errors = tuple(
        _year_error(year, measured.get(year), modelled.get(year))
        for year in sorted(set(measured) | set(modelled))
    )
    years = tuple(sorted(measured))

    problems = _problems(measured, modelled)
    if problems:
        reason = "no verdict: " + "; ".join(problems)
        return H10Result(
            years=years,
            pbias_percent=None,
            pbias_reason=reason,
            year_errors=year_errors,
            measured_order=YearOrder(None, reason),
            modelled_order=YearOrder(None, reason),
            orders_match=None,
            pbias_condition=Condition(None, reason),
            order_condition=Condition(None, reason),
            h10=Condition(None, reason),
            large_events=large_events,
        )

    exact_measured = {year: Fraction(_number(measured[year])) for year in years}
    exact_modelled = {year: Fraction(_number(modelled[year])) for year in years}
    total_measured = sum(exact_measured.values(), Fraction(0))
    total_modelled = sum(exact_modelled.values(), Fraction(0))

    if total_measured > 0:
        exact_pbias = PERCENT * (total_measured - total_modelled) / total_measured
        pbias: float | None = float(exact_pbias)
        pbias_reason = None
        if abs(exact_pbias) <= bound:
            pbias_condition = Condition("pass", None)
        else:
            pbias_condition = Condition(
                "fail",
                f"the percent bias {pbias} is outside plus or minus "
                f"{float(bound)} percent",
            )
    else:
        pbias = None
        pbias_reason = (
            "the sum of the measured values is not above zero: the percent bias "
            "divides by it, so there is none"
        )
        pbias_condition = Condition(None, pbias_reason)

    measured_order = _order("measured", exact_measured)
    modelled_order = _order("modelled", exact_modelled)
    if measured_order.order is not None and modelled_order.order is not None:
        orders_match: bool | None = measured_order.order == modelled_order.order
        if orders_match:
            order_condition = Condition("pass", None)
        else:
            order_condition = Condition(
                "fail",
                f"the modelled order {modelled_order.order} is not the measured "
                f"order {measured_order.order}",
            )
    else:
        orders_match = None
        order_condition = Condition(
            None,
            "; ".join(
                order.reason
                for order in (measured_order, modelled_order)
                if order.reason is not None
            ),
        )

    conditions = (
        ("condition (1), the percent bias", pbias_condition),
        ("condition (2), the order of the years", order_condition),
    )
    failed = [f"{name}: {c.reason}" for name, c in conditions if c.verdict == "fail"]
    pending = [f"{name}: {c.reason}" for name, c in conditions if c.verdict is None]
    if failed:
        h10 = Condition("fail", "; ".join(failed))
    elif pending:
        h10 = Condition(None, "; ".join(pending))
    else:
        h10 = Condition("pass", None)

    return H10Result(
        years=years,
        pbias_percent=pbias,
        pbias_reason=pbias_reason,
        year_errors=year_errors,
        measured_order=measured_order,
        modelled_order=modelled_order,
        orders_match=orders_match,
        pbias_condition=pbias_condition,
        order_condition=order_condition,
        h10=h10,
        large_events=large_events,
    )
