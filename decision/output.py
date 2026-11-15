"""The decision output document of a results table (sub-lane L2b).

``contracts/decision_output/README.md`` names the producer of the document:
"Platform, decision (L2b, ``decision/``)". Until now the document was
assembled only in ``demo/run.py``, for the thin matrix of #240. This module
assembles it for any ``ResultsTable``, from the functions of
``decision/functions.py``, so that the platform's route
``POST /api/decisions/run`` (``api/decisions.py``, D198) can serve it: the
route finds ``assemble_decision_output`` by name and never imports it.

**PROPOSED by an AI session working for the lead developer (D159, D161 of
#77; brief #315), for the interface developer to accept, change or replace:
this is his sub-lane.** Every choice below is marked; none adds a rule of the
science. Every rule of the state, the counts and the coverage is
``decision/functions.py``'s, as #309 brought it to D165 to D176.

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
- ``pair_cell_counts``: ``pair_counts`` (D87, D99, D169), one count per pair,
  scenario, indicator, carbon model and computation, each naming its
  ``carbon_model`` and ``computation`` (``None`` for the indicators that name
  neither; the key of D169 in the contract, #331). Counts of different models
  or computations are never added (D169). The count by range of D99 is given,
  the count by sign is missing (above).
- ``pair_states``: one state per pair (below), with the coverage "k of N" of
  ``dominance`` (D91, D156) and the reason of D86.
- ``state``: null with its reason (OPEN 5 of the README: no decision says
  how the document's one state relates to the states of its pairs), the
  indicators the pairs do not resolve (D7), and one reason text per pair and
  per scenario (D152: "The conditions that did not give the state are still
  shown").
- ``measure_first``: empty. The priority list of D4 needs the person's
  mapping of the uncertain inputs (``UncertainInput``), which the table does
  not carry.

**The state of a pair is ``pair_state``'s, unchanged** (D152, D165, D166,
D173, D175): over the scenarios of the table it reads each scenario on its
own and gives the state of the set; only the computation of the soil carbon
trend used to compare rotations enters it (``end_minus_start``: the table
carries no choice of the user, C1.6). This module composes and decides
nothing. Its one PROPOSED step: ``pair_state`` finds a robust preference for
its second rotation, so the pair is read in both orders, and a robust
preference in either names its rotation in ``preferred_rotation_id``; the
state does not depend on which rotation comes first. The state of each
scenario (``PairState.by_scenario``) is shown in the reasons of the document
(D152: "The conditions that did not give the state are still shown"); the
contract has no field for it (OPEN 5 of its README).

**The indicators not resolved do depend on the order, and this module keeps
``pair_state``'s list as it is.** ``pair_state`` names an indicator with a
cell that blocks a robust preference of its second rotation (D165), and a
cell that deteriorates in one order is a strict improvement in the other. The
list is the one of the order the state was read in: the robust order when the
pair is a robust preference (an empty list), otherwise the order of the
rotations in the table, which is the order of the request. Choosing a list
that does not depend on the order (the indicators that block in both orders,
or in either) would be a rule of the state, so it is left to
``decision/functions.py`` (OPEN for sub-lane L2b); the reason texts of the
document name the pair in the order read.

**A pair not evaluated** (no state, D85, D151) says why: either no paired
difference holds a value, or the only ones that do are of computations of
the soil carbon trend that do not enter the state (D173); those are still in
``paired_differences`` and in the counts.

Pure: no network, no file access, no clock.
"""

from __future__ import annotations

import itertools
from collections.abc import Hashable, Iterable

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
    NOT_EVALUATED as NOT_EVALUATED_LABEL,
)
from decision.functions import (
    ROBUST_PREFERENCE,
    dominance,
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
NOT_EVALUATED = (
    "no paired difference of the pair holds a value: the pair is not evaluated "
    "and has no state (D85, D151)"
)
NOT_EVALUATED_BY_THE_COMPUTATION = (
    "no paired difference that enters the state holds a value: the only ones "
    "that do are of computations of the soil carbon trend that do not enter it "
    "(D173: only the computation used to compare rotations does, end_minus_start "
    "when the user has not chosen); the pair is not evaluated and has no state "
    "(D85, D151)"
)
NO_REASON_OF_D86 = (
    "D86 writes no reason for the state 'Not separated: within uncertainty' (D97) "
    "and no reason code is decided for it (contracts/decision_output/README.md, K3)"
)
NO_DOCUMENT_STATE = (
    "no decision says how the document's one state relates to the states of its "
    "pairs (contracts/decision_output/README.md, OPEN 5); the states of the pairs "
    "are in 'pair_states'"
)


def _in_order(items: Iterable[Hashable]) -> list:
    seen: dict = {}
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


def _pair_state(
    table: ResultsTable, first: str, second: str
) -> tuple[PairState, tuple[str, ...], list[str]]:
    """The state of one pair, the indicators it does not resolve, and one
    reason text per scenario of the table, from ``pair_state`` and
    ``dominance`` of ``decision/functions.py`` (module docstring)."""
    covered = dominance(table, first, second)
    coverage = Coverage(
        cells_compared=covered.cells_compared,
        cells_of_the_pair=covered.cells_of_the_pair,
    )
    pair = [first, second]
    read = pair_state(table, first, second)
    preferred = second if read.state == ROBUST_PREFERENCE else None
    if preferred is None:
        backward = pair_state(table, second, first)
        if backward.state == ROBUST_PREFERENCE:
            read, preferred = backward, first
    texts = [
        f"in scenario '{scenario}' the pair ('{first}', '{second}') is "
        f"'{value or NOT_EVALUATED_LABEL}'"
        for scenario, value in read.by_scenario
    ]
    if read.state is None:
        detail = (
            NOT_EVALUATED
            if coverage.cells_compared == 0
            else NOT_EVALUATED_BY_THE_COMPUTATION
        )
        state = PairState(
            pair=pair,
            value=None,
            missing=Missing(reason="NOT_AVAILABLE", detail=detail),
            coverage=coverage,
        )
        return state, (), texts
    if read.state == ROBUST_PREFERENCE:
        state = PairState(
            pair=pair,
            value=read.state,
            preferred_rotation_id=preferred,
            coverage=coverage,
        )
        return state, read.indicators_not_resolved, texts
    reason = REASON_OF_A_STATE.get(read.state)
    state = PairState(
        pair=pair,
        value=read.state,
        reason=reason,
        reason_missing=(
            None
            if reason is not None
            else Missing(reason="NOT_AVAILABLE", detail=NO_REASON_OF_D86)
        ),
        coverage=coverage,
    )
    return state, read.indicators_not_resolved, texts


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
        (c.rotation_id, c.indicator, c.carbon_model, c.computation)
        for c in counts.values()
    ):
        rotation_id, indicator, carbon_model, computation = key
        of_key = [
            c
            for c in counts.values()
            if (c.rotation_id, c.indicator, c.carbon_model, c.computation) == key
        ]
        within = {c.scenario_id: c.within for c in of_key if c.within is not None}
        common = dict(
            rotation_id=rotation_id,
            indicator=indicator,
            carbon_model=carbon_model,
            computation=computation,
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
                    # D169: the key of a count names its model and computation.
                    carbon_model=count.carbon_model,
                    computation=count.computation,
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
        state, names, texts = _pair_state(table, first, second)
        pair_states.append(state)
        not_resolved.update(names)
        reasons.append(
            f"the pair ('{first}', '{second}') is "
            f"'{state.value or NOT_EVALUATED_LABEL}' over {len(scenarios)} "
            "scenario(s); indicators not resolved: "
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
