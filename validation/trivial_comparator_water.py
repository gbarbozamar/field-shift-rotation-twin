"""The trivial comparator of the water-deficit exposure, and its report against
the full indicator (entry H0 of ``docs/VALIDATION.md``; unit
l0/trivial-comparator-h0-d212, issue #312).

Decision D212 of issue #77, 15 November 2026 (taken under the delegation of
D161): the trivial comparator of the water-deficit exposure is
"precipitation over demanded transpiration on the days with a living crop:
the window and the denominator of D157 with the daily balance removed, per
rotation, scenario, phase and agricultural year, ordered by its mean over
agricultural years (higher is better), compared with the order of the full
indicator by the reading of D0. Not bounded at one."

It is not a water-deficit exposure and is never shown as one. It validates
neither method: it says whether the daily soil water balance (storage
carried between crops, runoff, soil evaporation and the stress coefficient)
changes the order of the rotations. Every result of this module carries the
label "whole cycle, not critical period" (D157, D162, D191).

What is taken from EP3 (``engine/water/exposure.py`` since #296), and not
redefined here:

- The inputs. One ``WaterDay`` per day of an agricultural year, holding the
  two daily series EP3 reads:

  - ``precipitation`` is ``ChainDay.precipitation``: the daily
    precipitation of the climate record, as the chain of EP3 reads it.
  - ``transpiration_demanded`` is ``ChainDay.balance.transpiration_demanded``
    (``engine/water/balance/bucket.py``, ``DayResult``): the basal crop
    coefficient times the reference evapotranspiration, the denominator of
    D157, and ``NOT_APPLICABLE`` on a day the balance was given no crop.

  The days of an agricultural year are the ones EP3 lays out for that year
  (``_first_day`` to ``_last_day`` of its start month, lines 460 to 465):
  the caller gives
  them, and a cycle that crosses the start of the year gives its days to
  each year, as in D157 and D47.
- The window: a day counts when its demanded transpiration is a number, and
  is left out when it is missing with the reason ``NOT_APPLICABLE`` (a day
  with no crop, or of the tail after maturity: D106, D136). This is the
  test of ``_computed`` in ``engine/water/exposure.py`` (lines 1416 to 1425
  at main ``da23c2c``), applied to the same field.
- The states of a year with no ratio, in the order ``_computed`` applies
  them:

  1. a day whose demanded transpiration is missing for another reason: the
     year is missing with the reason of that day (``_computed``, lines 1421
     to 1425, ``_not_a_number``);
  2. no day with a living crop: ``NOT_APPLICABLE`` (``_computed``, lines
     1426 and 1427; ``_no_living_crop``, line 1339);
  3. a day with a living crop whose precipitation is missing: the year is
     missing with the reason of that day. EP3 does the same for the
     transpiration of such a day (lines 1428 to 1433); this module reads
     precipitation where EP3 reads transpiration;
  4. a demanded sum that is not above zero, or a ratio that is not finite:
     ``NOT_COMPUTABLE`` (``_computed``, lines 1436 to 1440;
     ``_nothing_demanded``, line 1352). Decision D214 of issue #77 takes
     that reason code as built, for EP3 and for the denominator of H0
     (it answers OPEN 43 of ``engine/water/EXPOSURE.md``), and so is it
     here.

  Nothing is filled and nothing is read as zero.
- The sums: ``math.fsum`` of each series over the counted days, the first
  over the second, as ``_computed`` sums transpiration and demand.

What is taken from entry D0 (``validation/trivial_comparator.py``, #298),
and not written a second time: the order of the full indicator,
``trivial_orders`` on the ``ResultsTable`` of ``water_deficit_exposure``
(the mean over agricultural years of the values, read in the direction of
the row, C1.1, ignoring ranges), with its ``TrivialOrder`` and its reasons
for giving none.

The order of this comparator follows the rules D0 gives its own order: each
scenario on its own (D166); a missing year, a ``NOT_APPLICABLE`` year, a tie
of two means and a single rotation give no order, with the reason; the means
are compared exactly, as rational numbers built from the stored values
(OPEN 7 of D0). Pure functions: no file, no clock, no network. The module
holds no value of the method, no threshold and no tolerance.

OPEN, for the lead developer (D212 does not say; this module does as
stated):

1. The phase. D212 orders "per rotation, scenario, phase and agricultural
   year", and a ``ResultsTableRow`` has no field for the phase. This module
   reads one ``scenario_id`` as one scenario and phase: a phase must reach
   it, and the table, under a ``scenario_id`` of its own. Options: (a) that;
   (b) a field for the phase in both inputs, which is a contract change.
2. A year for which this comparator has a ratio and EP3 has none (the daily
   balance was not computed on every day). The full side then gives no order
   (a missing year, D0) and the report says so. Options: (a) that; (b) leave
   out of the comparator every year EP3 does not compute.
3. Two sides that order different sets of rotations. The report gives
   neither "equal" nor "different", and says why. Options: (a) that; (b)
   compare only the rotations both sides hold.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from contracts.results.models import Missing, ResultsTable
from engine.water.exposure import INDICATOR, NO_CROP_ON_THE_DAY, WINDOW_LABEL
from validation.trivial_comparator import TrivialOrder, trivial_orders

NOT_COMPUTABLE = "NOT_COMPUTABLE"

Outcome = Literal[
    "equal",
    "different",
    "not the same rotations",
    "no order from the trivial comparator",
    "no order from the full indicator",
    "no order from either",
]


@dataclass(frozen=True)
class WaterDay:
    """One day of an agricultural year, as EP3 reads it (see the module
    docstring): ``precipitation`` is ``ChainDay.precipitation`` and
    ``transpiration_demanded`` is ``ChainDay.balance.transpiration_demanded``,
    each a number or a ``Missing`` with its reason."""

    date: dt.date
    precipitation: float | Missing
    transpiration_demanded: float | Missing


@dataclass(frozen=True)
class YearRatio:
    """The ratio of one rotation, scenario and agricultural year: precipitation
    over demanded transpiration, both summed over the days with a living crop.
    ``ratio`` is ``None`` when it has no value, and ``missing`` then says why.
    ``crop_days`` counts the days that entered the sums."""

    rotation_id: str
    scenario_id: str
    ag_year: int
    ratio: float | None
    missing: Missing | None
    crop_days: int
    label: str = WINDOW_LABEL


@dataclass(frozen=True)
class WaterOrder:
    """The order this comparator gives one scenario: the rotations best first
    (higher is better), by the mean of their ratio over agricultural years;
    ``None`` with its reason when it gives none. ``means`` is ``None``
    whenever a mean cannot be taken without filling a year."""

    scenario_id: str
    years: tuple[YearRatio, ...]
    means: tuple[tuple[str, float], ...] | None
    order: tuple[str, ...] | None
    reason: str | None
    label: str = WINDOW_LABEL


@dataclass(frozen=True)
class WaterComparisonItem:
    """One line of the report of entry H0, for one scenario.

    ``trivial`` is the order of this comparator; ``full`` is the order of the
    full ``water_deficit_exposure`` values by the reading of D0. ``outcome``
    is "equal" or "different" only when both orders exist over the same
    rotations; otherwise it names which side gives no order, and the reasons
    say why. ``rotations_ordered`` counts the rotations in the order of this
    comparator, and ``rotations_ordered_full`` those in the order of the full
    indicator (zero where a side gives no order)."""

    scenario_id: str
    trivial: WaterOrder
    full: TrivialOrder
    outcome: Outcome
    rotations_ordered: int
    rotations_ordered_full: int
    label: str = WINDOW_LABEL


def _missing_on(ag_year: int, what: str, day: dt.date, missing: Missing) -> Missing:
    return Missing(
        reason=missing.reason,
        detail=(
            f"the ratio of entry H0 is not computed for agricultural year {ag_year}: "
            f"the {what} has no value on {day.isoformat()} ({missing.reason}: "
            f"{missing.detail}); nothing is filled and nothing is read as zero"
        ),
    )


def year_ratio(
    rotation_id: str, scenario_id: str, ag_year: int, days: Sequence[WaterDay]
) -> YearRatio:
    """The ratio of entry H0 for one agricultural year: the sum of
    precipitation over the sum of demanded transpiration, both over the days
    with a living crop that D157 counts; or no value, with the state EP3 gives
    the full indicator in the same case (see the module docstring)."""

    def none(missing: Missing, crop_days: int) -> YearRatio:
        return YearRatio(rotation_id, scenario_id, ag_year, None, missing, crop_days)

    living: list[WaterDay] = []
    for day in days:
        demanded = day.transpiration_demanded
        if not isinstance(demanded, Missing):
            living.append(day)
        elif demanded.reason != NO_CROP_ON_THE_DAY:
            return none(
                _missing_on(ag_year, "demanded transpiration", day.date, demanded), 0
            )
    if not living:
        return none(
            Missing(
                reason=NO_CROP_ON_THE_DAY,
                detail=(
                    f"the ratio of entry H0 does not apply to agricultural year "
                    f"{ag_year}: no day of the year has a living crop (a day with no "
                    "crop and a day of the tail after maturity do not enter it: D106, "
                    "D136, D157), as EP3 gives the full indicator"
                ),
            ),
            0,
        )
    for day in living:
        if isinstance(day.precipitation, Missing):
            return none(
                _missing_on(ag_year, "precipitation", day.date, day.precipitation),
                len(living),
            )
    supplied = math.fsum(day.precipitation for day in living)
    demanded_sum = math.fsum(day.transpiration_demanded for day in living)
    nothing_demanded = Missing(
        reason=NOT_COMPUTABLE,
        detail=(
            f"the ratio of entry H0 is not computed for agricultural year {ag_year}: "
            "the demanded transpiration summed over its "
            f"{len(living)} day(s) with a living crop is not above zero, so it has "
            "no denominator, as EP3 gives the full indicator (reason code of "
            "decision D214 of issue #77, which answers OPEN 43 of "
            "engine/water/EXPOSURE.md)"
        ),
    )
    if not demanded_sum > 0:
        return none(nothing_demanded, len(living))
    ratio = supplied / demanded_sum
    if not math.isfinite(ratio):
        return none(nothing_demanded, len(living))
    return YearRatio(rotation_id, scenario_id, ag_year, ratio, None, len(living))


def _order_one(scenario_id: str, years: list[YearRatio]) -> WaterOrder:
    """The order of entry H0 in one scenario, by the rules of entry D0."""
    years = sorted(years, key=lambda year: (year.rotation_id, year.ag_year))
    held = tuple(years)

    def none(
        reason: str, means: tuple[tuple[str, float], ...] | None = None
    ) -> WaterOrder:
        return WaterOrder(scenario_id, held, means, None, reason)

    rotations = sorted({year.rotation_id for year in years})
    if len(rotations) < 2:
        return none(
            f"the scenario holds one rotation ('{rotations[0]}'): the definition of "
            "entry D0, which entry H0 follows, does not say what order a single "
            "rotation has (OPEN)"
        )
    missing = [year for year in years if year.ratio is None]
    if missing:
        listed = "; ".join(
            f"'{year.rotation_id}' in {year.ag_year} ({year.missing.reason})"
            for year in missing
        )
        return none(
            f"a rotation has no ratio of entry H0 in an agricultural year ({listed}): "
            "the definition of entry D0, which entry H0 follows, does not say how "
            "such a year enters the mean, and a missing value is never filled or "
            "taken as zero (OPEN)"
        )
    exact: dict[str, Fraction] = {}
    for rotation_id in rotations:
        ratios = [Fraction(y.ratio) for y in years if y.rotation_id == rotation_id]
        exact[rotation_id] = sum(ratios, Fraction(0)) / len(ratios)
    means = tuple((rotation_id, float(exact[rotation_id])) for rotation_id in rotations)
    tied = [
        (first, second)
        for first, second in itertools.combinations(rotations, 2)
        if exact[first] == exact[second]
    ]
    if tied:
        listed = "; ".join(f"'{first}' and '{second}'" for first, second in tied)
        return none(
            f"the means of {listed} are equal: the definition of entry D0, which "
            "entry H0 follows, does not say how a tie is ordered (OPEN)",
            means,
        )
    order = tuple(
        sorted(rotations, key=lambda rotation_id: exact[rotation_id], reverse=True)
    )
    return WaterOrder(scenario_id, held, means, order, None)


def _years(
    series: Mapping[tuple[str, str, int], Sequence[WaterDay]],
) -> dict[str, list[YearRatio]]:
    by_scenario: dict[str, list[YearRatio]] = {}
    for (rotation_id, scenario_id, ag_year), days in series.items():
        by_scenario.setdefault(scenario_id, []).append(
            year_ratio(rotation_id, scenario_id, ag_year, days)
        )
    return by_scenario


def water_orders(
    series: Mapping[tuple[str, str, int], Sequence[WaterDay]],
) -> tuple[WaterOrder, ...]:
    """The trivial comparator of entry H0: for each scenario, the rotations
    ordered best first by the mean over agricultural years of their ratio
    (higher is better); or no order, with its reason. ``series`` maps
    ``(rotation_id, scenario_id, ag_year)`` to the days of that agricultural
    year."""
    return tuple(
        _order_one(scenario_id, years)
        for scenario_id, years in sorted(_years(series).items())
    )


def _full_order(table: ResultsTable, scenario_id: str) -> TrivialOrder:
    """The order of the full indicator in one scenario, by the reading of D0."""
    for order in trivial_orders(table):
        if order.scenario_id == scenario_id and order.indicator == INDICATOR:
            return order
    return TrivialOrder(
        scenario_id,
        INDICATOR,
        None,
        None,
        None,
        f"the table holds no row of '{INDICATOR}' in scenario '{scenario_id}'",
    )


def _no_input(scenario_id: str) -> WaterOrder:
    return WaterOrder(
        scenario_id,
        (),
        None,
        None,
        f"no daily series of scenario '{scenario_id}' was given to entry H0",
    )


def compare_with_full_indicator(
    series: Mapping[tuple[str, str, int], Sequence[WaterDay]], table: ResultsTable
) -> tuple[WaterComparisonItem, ...]:
    """The report of entry H0: for each scenario, whether the order of this
    comparator equals the order of the full ``water_deficit_exposure`` values
    of ``table`` by the reading of D0, and how many rotations each side
    ordered. Where either side gives no order, the outcome says which, and
    never "equal" or "different"."""
    trivial_of = {order.scenario_id: order for order in water_orders(series)}
    scenarios = sorted(
        set(trivial_of)
        | {row.scenario_id for row in table.rows if row.indicator == INDICATOR}
    )
    items = []
    for scenario_id in scenarios:
        trivial = trivial_of.get(scenario_id) or _no_input(scenario_id)
        full = _full_order(table, scenario_id)
        if trivial.order is None and full.order is None:
            outcome: Outcome = "no order from either"
        elif trivial.order is None:
            outcome = "no order from the trivial comparator"
        elif full.order is None:
            outcome = "no order from the full indicator"
        elif set(trivial.order) != set(full.order):
            outcome = "not the same rotations"
        elif trivial.order == full.order:
            outcome = "equal"
        else:
            outcome = "different"
        items.append(
            WaterComparisonItem(
                scenario_id,
                trivial,
                full,
                outcome,
                len(trivial.order or ()),
                len(full.order or ()),
            )
        )
    return tuple(items)
