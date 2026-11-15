"""The order between systems (entry E2 of ``docs/VALIDATION.md``; decision
D225 of issue #77; unit l0/validation-e2-d225, issue #346).

D225: "The order of the rotations by the full ``soil_loss``, read as in D0,
against an expected order given as an input, on hand-made tables. The
expected order on real data and its source stay OPEN."

What is called, not re-implemented: the order of the rotations by the full
``soil_loss`` is the one ``trivial_orders`` of
``validation/trivial_comparator.py`` gives (entry D0): per scenario, by the
mean over agricultural years of the values, read in the direction of the
rows (C1.1), ignoring ranges. Each phase is a scenario (D109, D166), so the
order is given per scenario and phase, and nothing is ordered across
scenarios. A tie, a missing year and a single rotation give no order, with
the reason D0 gives; nothing is filled and nothing is read as zero.

What this module adds: the expected order, an argument, lists the rotations
best first (for ``soil_loss``, lower is better: the lowest first), as the
order of D0 does. For each scenario of the table, the report says whether
the order of the full ``soil_loss`` equals the expected order, and how many
rotations that order holds.

The expected order is the same for every scenario: it is an order of
systems, which a source would give without phases (OPEN 2).

Where the expected order and the table do not name the same rotations (one
names a rotation the other lacks), the scenario is not compared, with the
reason naming the rotations of each side (OPEN 1). An order over other
rotations is neither equal nor different.

The expected order is checked before anything is read: it is a sequence of
rotation identifiers (text), at least one, none twice. Another type raises
``TypeError``; an empty order or one that names a rotation twice raises
``ValueError``. So is a table that is not a ``ResultsTable``.

Pure functions: no file, no clock, no network. The module holds no value of
the method and no threshold. It does not say which order is right on real
data: the expected order on real data and its source are OPEN (D225).

OPEN, for the lead developer:

1. An expected order that names a rotation the table lacks, or that lacks a
   rotation the table holds, for a scenario. Options: (a) as built, that
   scenario is not compared, with the reason; (b) refuse the inputs
   (``ValueError``); (c) compare over the rotations both name.
2. One expected order for every scenario and phase. Options: (a) as built,
   one order, the same for every scenario; (b) an expected order per
   scenario or phase.
3. The expected order on real data and its source (D225): a person
   transcribes it from its source and signs it (D34, D66); which systems it
   covers. Until a ``C`` by rotation exists, the full ``soil_loss`` gives
   every rotation the same value (D158), so on real data the report states
   that the full method gives no order.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.results.models import ResultsTable
from validation.trivial_comparator import TrivialOrder, trivial_orders

SOIL_LOSS = "soil_loss"

Outcome = Literal[
    "equal",
    "different",
    "no order from the full method",
    "not compared",
]


@dataclass(frozen=True)
class SystemsComparison:
    """One line of the report of entry E2, for one scenario (each phase is a
    scenario).

    ``full`` is the order of the full ``soil_loss`` as ``trivial_orders``
    gives it (entry D0), or ``None`` when the scenario holds no ``soil_loss``.
    ``outcome`` is "equal" or "different" only when that order exists and
    names the same rotations as ``expected``; otherwise ``reason`` says why.
    ``rotations_ordered`` is how many rotations the order of the full
    ``soil_loss`` holds (zero when it gives none).
    """

    scenario_id: str
    expected: tuple[str, ...]
    full: TrivialOrder | None
    outcome: Outcome
    reason: str | None
    rotations_ordered: int


def _checked_expected(expected: object) -> tuple[str, ...]:
    """The expected order as a tuple, after checking what it may be."""
    if isinstance(expected, (str, bytes)) or not isinstance(expected, Sequence):
        raise TypeError(
            "expected: an expected order is a sequence of rotation identifiers, "
            f"best first; got {type(expected).__name__}"
        )
    for item in expected:
        if not isinstance(item, str) or not item:
            raise TypeError(
                "expected: each rotation of the expected order is a non-empty text; "
                f"got {item!r}"
            )
    if not expected:
        raise ValueError("expected: the expected order names no rotation")
    twice = sorted(item for item, count in Counter(expected).items() if count > 1)
    if twice:
        raise ValueError(f"expected: the expected order names {twice} more than once")
    return tuple(expected)


def _rotations_of(table: ResultsTable, scenario_id: str) -> set[str]:
    return {
        row.rotation_id
        for row in table.rows
        if row.scenario_id == scenario_id and row.indicator == SOIL_LOSS
    }


def compare_with_expected_order(
    table: ResultsTable, expected: Sequence[str]
) -> tuple[SystemsComparison, ...]:
    """The report of entry E2 (D225): for each scenario of the table, whether
    the order of the rotations by the full ``soil_loss`` (``trivial_orders``,
    the reading of entry D0) equals ``expected``, the rotations best first,
    and how many rotations that order holds; or why it is not compared."""
    if not isinstance(table, ResultsTable):
        raise TypeError(f"table: expected a ResultsTable, got {type(table).__name__}")
    wanted = _checked_expected(expected)
    full = {
        item.scenario_id: item
        for item in trivial_orders(table)
        if item.indicator == SOIL_LOSS
    }
    items = []
    for scenario_id in sorted({row.scenario_id for row in table.rows}):
        order = full.get(scenario_id)
        if order is None:
            items.append(
                SystemsComparison(
                    scenario_id,
                    wanted,
                    None,
                    "no order from the full method",
                    f"the table holds no '{SOIL_LOSS}' of scenario '{scenario_id}'",
                    0,
                )
            )
            continue
        held = _rotations_of(table, scenario_id)
        ordered = len(order.order or ())
        if held != set(wanted):
            items.append(
                SystemsComparison(
                    scenario_id,
                    wanted,
                    order,
                    "not compared",
                    f"the expected order names {sorted(set(wanted))} and the table "
                    f"holds the rotations {sorted(held)} of '{SOIL_LOSS}' in scenario "
                    f"'{scenario_id}': an order is compared only over the same "
                    "rotations (OPEN 1)",
                    ordered,
                )
            )
            continue
        if order.order is None:
            outcome: Outcome = "no order from the full method"
            reason = order.reason
        else:
            outcome = "equal" if order.order == wanted else "different"
            reason = None
        items.append(
            SystemsComparison(scenario_id, wanted, order, outcome, reason, ordered)
        )
    return tuple(items)
