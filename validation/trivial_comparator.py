"""The trivial comparator of the decision, and its report against the full
decision (entry D0 of ``docs/VALIDATION.md``; unit l0/trivial-comparator-d0,
issue #291).

Entry D0, as decided by the lead developer on 14 November 2026: "The
trivial comparator orders the rotations, per indicator, by the mean over
agricultural years of the values, read in the direction of each row
(C1.1), ignoring ranges. The test checks that (a) on the hand-made table
the comparator returns the order counted by hand, and (b) the report
states, per indicator, whether the comparator's order equals the order of
the full decision."

What this module adds to that definition, all PROPOSED (blueprint section
3.7):

- The orders are given per scenario and indicator: each scenario of the
  table is read on its own, and nothing is ordered across scenarios
  (D166 of issue #77 never reads the cells of different scenarios as one).
- Where the definition does not say what to do, no order is given for
  that scenario and indicator, with the reason: a rotation with a missing
  value in some agricultural year (the value is never filled and never
  taken as zero), a tie of two means, a single rotation, and an indicator
  whose values are not on the agricultural-year time basis (the soil
  carbon trend; the water ratio when it is per rotation), for which there
  is no mean over agricultural years. Each is OPEN for the lead developer,
  with its options, at the end of this docstring.
- The order of the full decision for one indicator is read from
  ``decision/functions.py`` as it is: the rotation ``y`` is ahead of ``x``
  on an indicator when ``pair_state(table, x, y)`` evaluated that
  indicator (at least one paired difference of it holds a value) and does
  not name it among the indicators not resolved (entry D7: "names the
  indicators that are not resolved"). The full decision gives an order for
  the indicator only when every pair of rotations is separated on it one
  way. Otherwise it gives none, and the report says so instead of "equal"
  or "different".

Pure functions: no file, no clock, no network. The module holds no value of
the method, no threshold and no tolerance; the means are compared exactly,
as rational numbers built from the stored values.

What the reading of the full decision gives today: where both orders exist
they are equal, because the full decision separates two rotations on an
indicator only when the range of every paired difference of it lies wholly
on one side of zero (D93 as ``decision/`` applies it), and each value lies
inside its range (C2.1), so every year then favours the same rotation and
so does the mean. This holds under any reading of the full decision that
separates a pair on an indicator only when every agricultural year
favours the same rotation (or is no worse for it). The report can
therefore say "different" only if the reading of the full decision
changes so that a pair is separated while its years disagree.

OPEN, for the lead developer (entry D0 does not say; this module gives no
order, with the reason):

1. A rotation with no value in some agricultural year. Options: (a) no
   order, as here; (b) the mean over the years where every rotation has a
   value; (c) the mean over each rotation's own years with a value.
2. A tie of two means. Options: (a) no order for the indicator, as here;
   (b) an order that places the tied rotations at the same rank.
3. A single rotation. Options: (a) no order, as here; (b) the order of one.
4. An indicator whose values are not on the agricultural-year time basis
   (the soil carbon trend, one value per rotation, carbon model and
   computation; the water ratio when it is per rotation). Options: (a) no
   order, as here; (b) the single value in place of the mean, per carbon
   model and computation; (c) for the soil carbon trend, only the
   computation used to compare rotations (C1.6, D173).
5. A table with several scenarios. This module orders each scenario on its
   own (D166). Options: (a) that; (b) one order over all scenarios, with the
   cells of every scenario pooled, which D166 does not allow for the state
   of a pair; (c) one order over the set, read as D166 reads a set, without
   pooling cells: a pair ordered over the set only when every scenario
   orders it the same way.
6. How the order of the full decision is read (see above). Options: (a) the
   indicators that ``pair_state`` resolves, as here; (b) only the pairs whose
   state is "Robust preference" over every indicator.
7. How two means are compared. This module compares the stored binary
   values exactly, so means that are equal as written in decimals can
   differ (0.1 and 0.2 against 0.3 and 0.0: both 0.15 as written, ordered
   here). Options: (a) the stored binary values exactly, as here; (b) the
   decimals as written; (c) a tie within a tolerance, which entry D0 does
   not give.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from contracts.results.models import ResultsTable, ResultsTableRow
from decision.functions import pair_state, paired_differences

AG_YEAR = "ag_year"
LOWER_IS_BETTER = "lower_is_better"

Outcome = Literal[
    "equal",
    "different",
    "no order from the trivial comparator",
    "no order from the full decision",
    "no order from either",
]


@dataclass(frozen=True)
class TrivialOrder:
    """The order the trivial comparator gives one indicator in one scenario.

    ``order`` lists the rotations best first, read in the ``direction`` of
    the indicator's rows (C1.1); it is ``None`` when no order is given, and
    ``reason`` then says why. ``means`` holds, by rotation, the mean over
    agricultural years of the values, ignoring ranges; it is ``None``
    whenever a mean cannot be taken without filling a missing value or
    without agricultural-year rows, so a missing value never becomes a
    number.
    """

    scenario_id: str
    indicator: str
    direction: str | None
    means: tuple[tuple[str, float], ...] | None
    order: tuple[str, ...] | None
    reason: str | None


@dataclass(frozen=True)
class DecisionOrder:
    """The order the full decision gives one indicator in one scenario, read
    from ``pair_state`` as the module docstring says; ``None`` with its
    reason when the full decision gives none."""

    scenario_id: str
    indicator: str
    order: tuple[str, ...] | None
    reason: str | None


@dataclass(frozen=True)
class ComparisonItem:
    """One line of the report of entry D0: for one scenario and indicator,
    the two orders and whether they are equal.

    ``outcome`` is "equal" or "different" only when both orders exist;
    otherwise it names which side gives no order, and the reasons say why.
    """

    scenario_id: str
    indicator: str
    trivial: TrivialOrder
    decision: DecisionOrder
    outcome: Outcome


def _scenario_tables(table: ResultsTable) -> dict[str, ResultsTable]:
    """The rows of each scenario of the table, as a table of their own."""
    rows_of: dict[str, list[ResultsTableRow]] = {}
    for row in table.rows:
        rows_of.setdefault(row.scenario_id, []).append(row)
    return {
        scenario_id: ResultsTable(
            case_id=table.case_id, field_id=table.field_id, rows=rows
        )
        for scenario_id, rows in sorted(rows_of.items())
    }


def _indicators(table: ResultsTable) -> list[str]:
    return sorted({row.indicator for row in table.rows})


def _order_one(
    scenario_id: str, indicator: str, rows: list[ResultsTableRow]
) -> TrivialOrder:
    """The trivial order of one indicator in one scenario (entry D0)."""
    directions = sorted({row.direction for row in rows})
    direction = directions[0] if len(directions) == 1 else None

    def none(reason: str) -> TrivialOrder:
        return TrivialOrder(scenario_id, indicator, direction, None, None, reason)

    rotations = sorted({row.rotation_id for row in rows})
    if len(rotations) < 2:
        return none(
            f"the scenario holds one rotation ('{rotations[0]}') of '{indicator}': "
            "the definition of entry D0 does not say what order a single rotation "
            "has (OPEN)"
        )
    if direction is None:
        return none(
            f"the rows of '{indicator}' do not share one direction ({directions}): "
            "the order is read in the direction of each row (C1.1)"
        )
    bases = sorted({row.time_basis for row in rows})
    if bases != [AG_YEAR]:
        return none(
            f"the values of '{indicator}' are on the time basis {bases}, not "
            "'ag_year': the definition of entry D0 orders by the mean over "
            "agricultural years, and gives no rule for another time basis (OPEN)"
        )
    missing = sorted(
        (row.rotation_id, row.ag_year, row.missing.reason)
        for row in rows
        if row.value is None
    )
    if missing:
        listed = "; ".join(
            f"'{rotation_id}' in {ag_year} ({reason})"
            for rotation_id, ag_year, reason in missing
        )
        return none(
            f"a rotation has no value of '{indicator}' in an agricultural year "
            f"({listed}): the definition of entry D0 does not say how a missing "
            "year enters the mean, and a missing value is never filled or taken "
            "as zero (OPEN)"
        )
    exact: dict[str, Fraction] = {}
    for rotation_id in rotations:
        values = [Fraction(row.value) for row in rows if row.rotation_id == rotation_id]
        exact[rotation_id] = sum(values, Fraction(0)) / len(values)
    means = tuple((rotation_id, float(exact[rotation_id])) for rotation_id in rotations)
    tied = [
        (first, second)
        for first, second in itertools.combinations(rotations, 2)
        if exact[first] == exact[second]
    ]
    if tied:
        listed = "; ".join(f"'{first}' and '{second}'" for first, second in tied)
        return TrivialOrder(
            scenario_id,
            indicator,
            direction,
            means,
            None,
            f"the means of {listed} on '{indicator}' are equal: the definition of "
            "entry D0 does not say how a tie is ordered (OPEN)",
        )
    order = tuple(
        sorted(
            rotations,
            key=lambda rotation_id: exact[rotation_id],
            reverse=direction != LOWER_IS_BETTER,
        )
    )
    return TrivialOrder(scenario_id, indicator, direction, means, order, None)


def trivial_orders(table: ResultsTable) -> tuple[TrivialOrder, ...]:
    """The trivial comparator of entry D0: for each scenario and indicator of
    the table, the rotations ordered best first by the mean over
    agricultural years of their values, read in the direction of the rows
    (C1.1), ignoring ranges; or no order, with its reason."""
    orders = []
    for scenario_id, scenario in _scenario_tables(table).items():
        for indicator in _indicators(scenario):
            rows = [row for row in scenario.rows if row.indicator == indicator]
            orders.append(_order_one(scenario_id, indicator, rows))
    return tuple(orders)


def decision_order(
    scenario: ResultsTable, scenario_id: str, indicator: str
) -> DecisionOrder:
    """The order of the full decision for one indicator of one scenario, read
    from ``pair_state`` and ``paired_differences`` of ``decision/`` as they
    are (see the module docstring); ``scenario`` holds the rows of that
    scenario only."""

    def none(reason: str) -> DecisionOrder:
        return DecisionOrder(scenario_id, indicator, None, reason)

    rotations = sorted({row.rotation_id for row in scenario.rows})
    if len(rotations) < 2:
        return none(
            "the scenario holds one rotation: the full decision compares pairs "
            "of rotations, so it gives no order"
        )
    ahead_of: dict[str, set[str]] = {rotation_id: set() for rotation_id in rotations}
    for first, second in itertools.combinations(rotations, 2):
        evaluated = any(
            difference.value is not None
            for difference in paired_differences(scenario, first, second)
            if difference.indicator == indicator
        )
        if not evaluated:
            return none(
                f"no paired difference of '{indicator}' between '{first}' and "
                f"'{second}' holds a value: the full decision does not evaluate "
                "the pair on it (D85, entry D6)"
            )
        for x, y in ((first, second), (second, first)):
            if indicator not in pair_state(scenario, x, y).indicators_not_resolved:
                ahead_of[y].add(x)
        if not (first in ahead_of[second] or second in ahead_of[first]):
            kinds = sorted(
                {
                    (row.carbon_model, row.computation)
                    for row in scenario.rows
                    if row.indicator == indicator and row.carbon_model is not None
                }
            )
            if len(kinds) > 1:
                return none(
                    f"the full decision does not separate '{first}' and '{second}' "
                    f"on '{indicator}' as a whole: pair_state names an indicator, "
                    f"not a carbon model or computation, among the indicators not "
                    f"resolved, and it reads the {len(kinds)} carbon models and "
                    "computations of this indicator together, so one that does not "
                    "separate the pair keeps the whole indicator not resolved even "
                    "where another separates it"
                )
            return none(
                f"the full decision does not separate '{first}' and '{second}' on "
                f"'{indicator}': pair_state names it among the indicators not "
                "resolved in both orders of the pair"
            )
    order = tuple(
        sorted(rotations, key=lambda rotation_id: len(ahead_of[rotation_id]), reverse=True)
    )
    if [len(ahead_of[rotation_id]) for rotation_id in order] != list(
        range(len(rotations) - 1, -1, -1)
    ):
        return none(
            f"the separations of the pairs on '{indicator}' do not form one order"
        )
    return DecisionOrder(scenario_id, indicator, order, None)


def compare_with_decision(table: ResultsTable) -> tuple[ComparisonItem, ...]:
    """The report of entry D0: for each scenario and indicator, whether the
    trivial comparator's order equals the order of the full decision on the
    same table. Where either side gives no order, the outcome says which,
    and never "equal" or "different"."""
    scenarios = _scenario_tables(table)
    items = []
    for trivial in trivial_orders(table):
        decision = decision_order(
            scenarios[trivial.scenario_id], trivial.scenario_id, trivial.indicator
        )
        if trivial.order is None and decision.order is None:
            outcome: Outcome = "no order from either"
        elif trivial.order is None:
            outcome = "no order from the trivial comparator"
        elif decision.order is None:
            outcome = "no order from the full decision"
        elif trivial.order == decision.order:
            outcome = "equal"
        else:
            outcome = "different"
        items.append(
            ComparisonItem(
                trivial.scenario_id, trivial.indicator, trivial, decision, outcome
            )
        )
    return tuple(items)
