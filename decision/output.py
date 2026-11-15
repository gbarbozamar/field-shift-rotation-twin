"""The decision output document of a results table (sub-lane L2b).

``contracts/decision_output/README.md`` names the producer of the document:
"Platform, decision (L2b, ``decision/``)". Until now the document was
assembled only in ``demo/run.py``, for the thin matrix of #240. This module
assembles it for any ``ResultsTable``, from the functions of
``decision/functions.py``, so that the platform's route
``POST /api/decisions/run`` (``api/decisions.py``) can serve it: the route
finds ``assemble_decision_output`` by name and never imports it.

**PROPOSED by an AI session working for the lead developer (D159, D161 of
#77), for the interface developer to accept, change or replace: this is his
sub-lane.** Every choice below is marked; none adds a rule of the science.

What the document holds, for a table with no limit, no tolerance of "equal"
and no uncertain input declared (what the route has today):

- ``rotations`` and ``scenarios``: those of the table, in the order they
  first appear.
- ``limits``: every indicator of the table, missing ``NOT_DECLARED`` in the
  unit it has in the table (D60: a limit that is not declared is a missing
  value, kept in the list).
- ``counts_by_year``: ``limit_counts`` (D1, D94, D95). No row is evaluated
  and ``years_within_limits`` is null (D60). Every agricultural-year row is
  listed not evaluated (D60: "every row 'not evaluated' with its reason"): a
  row without a value with its own reason, a row with a value with
  ``NOT_DECLARED``, the candidate code that the contract's case
  ``soil-loss-limit-not-declared`` uses (OPEN 6 of the README).
- ``range_across_scenarios``: one per count key, missing ``NOT_DECLARED``
  when no year of the key is judged (D60, D96); otherwise minimum, maximum and
  the first scenario, in table order, at the minimum (OPEN 11 of the README).
- ``paired_differences``: ``paired_differences`` of each pair, second minus
  first, pairs in the order of the rotations (D2, D92). A computed difference
  is labelled ``DERIVED`` (C4.1: computed by a fixed formula) with this
  module's source; the method stays the contract example's ``OPEN`` text
  (#96, OPEN 2).
- ``equal_tolerances``: every indicator, missing ``NOT_DECLARED`` (D87: set
  by the designer of the case; none is declared). So every count by the sign
  of the point value is missing with that reason (D87, C3.1).
- ``pair_cell_counts``: ``pair_counts`` by pair, scenario and indicator; the
  count by range of D99 is given, the count by sign is missing (above).
- ``pair_states``: one state per pair across the scenarios (below), with the
  coverage of D91 over every cell of the pair and the reason of D86.
- ``state``: null with its reason (OPEN 5 of the README: no decision says
  how the document's one state relates to the states of its pairs), the
  indicators the pairs do not resolve (D7), and one reason text per pair and
  per scenario (D152: "The conditions that did not give the state are still
  shown").
- ``measure_first``: empty. The priority list of D4 needs the person's
  mapping of the uncertain inputs (``UncertainInput``), which the table does
  not carry.

**The state of a pair across the scenarios (D103, D117, D152; PROPOSED
reading).** In each scenario the state is read alone, by ``pair_state`` on
the rows of that scenario, in the order of D152. A robust preference is
looked for in both orders of the pair, so that the state does not depend on
which rotation comes first (``pair_state`` detects a preference for its
second rotation only); ``preferred_rotation_id`` names the rotation preferred.
With one scenario, the pair takes the state of that scenario. With several,
the pair is a robust preference only if it is one in every scenario, for the
same rotation; otherwise it is "Not robust across scenarios", with the reason
of D86 "not robust across the admitted scenarios" (D103: "when any member is
not a robust preference"; D117 for phases). A pair none of whose differences
holds a value has no state (D85, D151). This differs from ``demo/run.py``,
which reads every scenario's cells together in one ``pair_state``.

Pure: no network, no file access, no clock.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable

from contracts.decision_output import (
    CountByDifferenceRange,
    CountByYear,
    Coverage,
    DecisionOutput,
    EqualToleranceItem,
    LimitItem,
    NotEvaluated,
    PairCellCount,
    PairedDifferenceItem,
    PairState,
    RangeAcrossScenarios,
    State,
)
from contracts.decision_output.models import REASON_OF_A_STATE
from contracts.inputs.common import Missing, Range, Value
from contracts.results.models import ResultsTable
from decision.functions import (
    NOT_ROBUST_ACROSS_SCENARIOS,
    ROBUST_PREFERENCE,
    limit_counts,
    pair_counts,
    pair_state,
    paired_differences,
)

__all__ = ["assemble_decision_output"]

# The paired-difference method is OPEN (issue #96, OPEN 2); the contract
# example keeps this text.
DIFFERENCE_METHOD = "OPEN: paired-difference method and citation, person-supplied"
# PROPOSED: the source of a difference this module computes.
DIFFERENCE_SOURCE = (
    "decision layer: paired difference of entry D2 of docs/VALIDATION.md, second "
    "rotation minus first, range by D92 (decision/functions.py)"
)
# C4.1: a value computed from other values by a fixed formula.
DIFFERENCE_PROVENANCE = "DERIVED"

# PROPOSED detail texts (English, for developers and the screens' reasons).
NO_LIMIT = "no limit is declared for this indicator, so no year is judged (D60)"
NO_TOLERANCE = (
    "no tolerance of 'equal' is declared for this indicator (D87: set by the "
    "designer of the case)"
)
NO_COUNT_BY_SIGN = (
    "no tolerance of 'equal' is declared for this indicator, so its cells are "
    "counted by the range of their difference only (D87, D99)"
)
NOT_EVALUATED = "no paired difference of the pair holds a value: the pair is not evaluated and has no state (D85, D151)"
NO_REASON_OF_D86 = (
    "D86 writes no reason for the state 'Not separated: within uncertainty' (D97) "
    "and no reason code is decided for it (contracts/decision_output/README.md, K3)"
)
NO_DOCUMENT_STATE = (
    "no decision says how the document's one state relates to the states of its "
    "pairs (contracts/decision_output/README.md, OPEN 5); the states of the pairs "
    "are in 'pair_states'"
)


def _in_order(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def _missing(part) -> Missing | None:
    """A missing part of the results contract, in the shape of the inputs."""
    return None if part is None else Missing(reason=part.reason, detail=part.detail)


def _range(part) -> Range | None:
    return None if part is None else Range(low=part.low, high=part.high, kind=part.kind)


def _not_declared(unit: str, detail: str) -> Value:
    return Value(
        value=None, unit=unit, missing=Missing(reason="NOT_DECLARED", detail=detail)
    )


def _scenario_table(table: ResultsTable, scenario_id: str) -> ResultsTable:
    return ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[row for row in table.rows if row.scenario_id == scenario_id],
    )


def _state_in_one_scenario(
    table: ResultsTable, first: str, second: str
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """The state of a pair in one scenario, its preferred rotation and the
    indicators it does not resolve. A robust preference is looked for in both
    orders (module docstring)."""
    forward = pair_state(table, first, second)
    if forward.state == ROBUST_PREFERENCE:
        return ROBUST_PREFERENCE, second, ()
    backward = pair_state(table, second, first)
    if backward.state == ROBUST_PREFERENCE:
        return ROBUST_PREFERENCE, first, ()
    return forward.state, None, forward.indicators_not_resolved


def _pair_state(
    table: ResultsTable, scenarios: list[str], first: str, second: str
) -> tuple[PairState, tuple[str, ...], list[str]]:
    """The state of one pair across the scenarios (D103, D117, D152), the
    indicators it does not resolve, and one reason text per scenario."""
    differences = paired_differences(table, first, second)
    coverage = Coverage(
        cells_compared=sum(1 for d in differences if d.value is not None),
        cells_of_the_pair=len(differences),
    )
    pair = [first, second]
    if coverage.cells_compared == 0:
        state = PairState(
            pair=pair,
            value=None,
            missing=Missing(reason="NOT_AVAILABLE", detail=NOT_EVALUATED),
            coverage=coverage,
        )
        return state, (), [f"the pair ('{first}', '{second}') is not evaluated (D85)"]

    members = {
        scenario: _state_in_one_scenario(
            _scenario_table(table, scenario), first, second
        )
        for scenario in scenarios
    }
    not_resolved = tuple(
        sorted({indicator for _, _, names in members.values() for indicator in names})
    )
    texts = [
        f"in scenario '{scenario}' the pair ('{first}', '{second}') is "
        f"'{value or 'Not evaluated'}'"
        + (f", preferring '{preferred}'" if preferred else "")
        for scenario, (value, preferred, _) in members.items()
    ]
    preferred = {member[1] for member in members.values()}
    if len(members) == 1:
        ((value, chosen, _),) = members.values()
    elif (
        all(m[0] == ROBUST_PREFERENCE for m in members.values()) and len(preferred) == 1
    ):
        value, chosen = ROBUST_PREFERENCE, next(iter(preferred))
    else:
        value, chosen = NOT_ROBUST_ACROSS_SCENARIOS, None
    if value is None:
        # One scenario, and it holds no computed difference: no state (D85).
        state = PairState(
            pair=pair,
            value=None,
            missing=Missing(reason="NOT_AVAILABLE", detail=NOT_EVALUATED),
            coverage=coverage,
        )
        return state, (), texts
    if value == ROBUST_PREFERENCE:
        state = PairState(
            pair=pair, value=value, preferred_rotation_id=chosen, coverage=coverage
        )
        return state, (), texts
    reason = REASON_OF_A_STATE.get(value)
    state = PairState(
        pair=pair,
        value=value,
        reason=reason,
        reason_missing=(
            None
            if reason is not None
            else Missing(reason="NOT_AVAILABLE", detail=NO_REASON_OF_D86)
        ),
        coverage=coverage,
    )
    return state, not_resolved, texts


def assemble_decision_output(
    table: ResultsTable, *, example_data: bool
) -> DecisionOutput:
    """The decision output document of ``table`` (module docstring). PROPOSED."""
    rotations = _in_order(row.rotation_id for row in table.rows)
    scenarios = _in_order(row.scenario_id for row in table.rows)
    indicators = _in_order(row.indicator for row in table.rows)
    unit_of = {row.indicator: row.unit for row in table.rows}
    pairs = list(itertools.combinations(rotations, 2))

    counts = limit_counts(table, {}, equal_to_limit_counts_as_within=True)
    counts_by_year = []
    for count in counts.values():
        rows = [
            row
            for row in table.rows
            if (
                row.rotation_id,
                row.scenario_id,
                row.indicator,
                row.carbon_model,
                row.computation,
            )
            == (
                count.rotation_id,
                count.scenario_id,
                count.indicator,
                count.carbon_model,
                count.computation,
            )
            and row.time_basis == "ag_year"
        ]
        counts_by_year.append(
            CountByYear(
                rotation_id=count.rotation_id,
                scenario_id=count.scenario_id,
                indicator=count.indicator,
                carbon_model=count.carbon_model,
                computation=count.computation,
                years_evaluated=count.evaluated,
                years_within_limits=count.within,
                not_evaluated=[
                    NotEvaluated(
                        time_basis="ag_year",
                        ag_year=row.ag_year,
                        carbon_model=row.carbon_model,
                        computation=row.computation,
                        missing=(
                            _missing(row.missing)
                            if row.value is None
                            else Missing(reason="NOT_DECLARED", detail=NO_LIMIT)
                        ),
                    )
                    for row in rows
                ],
            )
        )

    ranges = []
    for key in _in_order(
        f"{c.rotation_id}\x00{c.indicator}\x00{c.carbon_model or ''}\x00{c.computation or ''}"
        for c in counts.values()
    ):
        rotation_id, indicator, carbon_model, computation = key.split("\x00")
        of_key = [
            c
            for c in counts.values()
            if (c.rotation_id, c.indicator, c.carbon_model or "", c.computation or "")
            == (rotation_id, indicator, carbon_model, computation)
        ]
        within = {c.scenario_id: c.within for c in of_key if c.within is not None}
        common = dict(
            rotation_id=rotation_id,
            indicator=indicator,
            carbon_model=carbon_model or None,
            computation=computation or None,
        )
        if not within:
            ranges.append(
                RangeAcrossScenarios(
                    **common,
                    minimum=None,
                    maximum=None,
                    scenario_of_the_minimum=None,
                    missing=Missing(reason="NOT_DECLARED", detail=NO_LIMIT),
                )
            )
            continue
        minimum = min(within.values())
        ranges.append(
            RangeAcrossScenarios(
                **common,
                minimum=minimum,
                maximum=max(within.values()),
                scenario_of_the_minimum=next(
                    s for s in scenarios if within.get(s) == minimum
                ),
            )
        )

    # A difference carries no time basis; it is the one of its cell.
    time_basis_of = {
        (
            row.rotation_id,
            row.scenario_id,
            row.indicator,
            row.ag_year,
            row.carbon_model,
            row.computation,
        ): row.time_basis
        for row in table.rows
    }
    differences = []
    cell_counts = []
    pair_states = []
    not_resolved: set[str] = set()
    reasons: list[str] = []
    for first, second in pairs:
        for difference in paired_differences(table, first, second):
            time_basis = time_basis_of[
                (
                    first,
                    difference.scenario_id,
                    difference.indicator,
                    difference.ag_year,
                    difference.carbon_model,
                    difference.computation,
                )
            ]
            if difference.value is None:
                value = Value(
                    value=None,
                    unit=difference.unit,
                    missing=_missing(difference.missing),
                )
            else:
                value = Value(
                    value=difference.value,
                    unit=difference.unit,
                    range=_range(difference.range),
                    range_missing=_missing(difference.range_missing),
                    provenance=DIFFERENCE_PROVENANCE,
                    source=DIFFERENCE_SOURCE,
                )
            differences.append(
                PairedDifferenceItem(
                    pair=[first, second],
                    scenario_id=difference.scenario_id,
                    indicator=difference.indicator,
                    time_basis=time_basis,
                    ag_year=difference.ag_year,
                    carbon_model=difference.carbon_model,
                    computation=difference.computation,
                    difference=value,
                    method=DIFFERENCE_METHOD,
                )
            )
        # The tolerance only matters for the count by sign, which is not
        # given without a declared tolerance.
        for count in pair_counts(table, first, second, equal_tolerance=0.0):
            cell_counts.append(
                PairCellCount(
                    pair=[first, second],
                    scenario_id=count.scenario_id,
                    indicator=count.indicator,
                    by_difference_range=CountByDifferenceRange(
                        strict_improvement=count.by_range.strict_improvement,
                        deterioration=count.by_range.deterioration,
                        not_separated=count.by_range.not_separated,
                    ),
                    by_sign_of_point_value=None,
                    by_sign_of_point_value_missing=Missing(
                        reason="NOT_DECLARED", detail=NO_COUNT_BY_SIGN
                    ),
                )
            )
        state, names, texts = _pair_state(table, scenarios, first, second)
        pair_states.append(state)
        not_resolved.update(names)
        reasons.append(
            f"the pair ('{first}', '{second}') is '{state.value or 'Not evaluated'}'"
            f" over {len(scenarios)} scenario(s); indicators not resolved: "
            f"{', '.join(names) or 'none'}"
        )
        reasons.extend(texts)

    return DecisionOutput(
        contract="decision_output",
        example_data=example_data,
        case_id=table.case_id,
        field_id=table.field_id,
        rotations=rotations,
        scenarios=scenarios,
        limits=[
            LimitItem(
                indicator=indicator, limit=_not_declared(unit_of[indicator], NO_LIMIT)
            )
            for indicator in indicators
        ],
        counts_by_year=counts_by_year,
        range_across_scenarios=ranges,
        paired_differences=differences,
        equal_tolerances=[
            EqualToleranceItem(
                indicator=indicator,
                tolerance=_not_declared(unit_of[indicator], NO_TOLERANCE),
            )
            for indicator in indicators
        ],
        pair_cell_counts=cell_counts,
        pair_states=pair_states,
        state=State(
            value=None,
            missing=Missing(reason="NOT_AVAILABLE", detail=NO_DOCUMENT_STATE),
            indicators_not_resolved=sorted(not_resolved),
            reasons=reasons,
        ),
        measure_first=[],
    )
