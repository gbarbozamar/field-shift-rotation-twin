"""The thin matrix through the decision (unit l2/thin-matrix-decision).

This module runs the approved matrix of ``demo/matrix.py`` through the
decision functions of ``decision/functions.py`` — the counts by year
against the declared limit (D1), the paired differences and their ranges
(D2, D92), the counts of the cells of a pair and the coverage (D87, D99,
D91), the state of each pair (D7, D74, D93, D97, D98), dominance (D5),
the ranking of an indicator (D6), the tipping point of the uncertain
input (D3) and the measurement priority (D4) — and emits what the
decision output contract of ``contracts/decision_output/`` carries.

Where the designer-read expectations of the brief (issue #240) and the
decided machinery diverge, this module emits the machinery's output and
the tests of ``test_demo.py`` mark each place. The divergences, all
forced by the worst-case interval arithmetic of D92 over the approved
ranges, are:

1. A vs B, soil loss, 2021: the difference range is
   [6.2 - 7.4, 6.8 - 6.6] = [-1.2, +0.2], which crosses zero, so the
   cell is not separated (D93) and blocks (D98) in EVERY scenario — the
   brief's "every valued year's difference range wholly better for B at
   s1 and s2" holds at 2020 and 2022 but not at 2021. The pair is
   "Not separated: within uncertainty" at every admitted value, and the
   tipping point of u the brief reads (the state changing between s2 and
   s3) does not appear: the state never changes, so no bracket is
   reported (D3). Over the set it is "Not robust across scenarios", as
   the brief reads it (D166: each scenario is read on its own).
2. B vs C, carbon: the difference range is [0.4 - 0.4, 0.6 - 0.2] =
   [0.0, +0.4], which touches zero from the side that is not worse, so
   the cell is not a strict improvement (D93) and does not block (D165)
   — the brief reads +0.2 [0.1, 0.3] wholly better for C and a "Robust
   preference (C)". The pair is still not a robust preference: its
   soil-loss cells cross zero (3. below), so it is "Not separated:
   within uncertainty" in each scenario and "Not robust across
   scenarios" over the set.
3. B vs C, soil loss: every difference is zero, but every range crosses
   zero ([-0.6, +0.6] at each shared year), so the cells are not
   separated and block; and the pair as a whole is never "Identical"
   (D85), because its carbon difference (+0.2) is not zero. The brief's
   "Identical" is a per-indicator reading; the machinery and the
   contract give one state per pair over all indicators.
4. The counts by year: B and C hold a valued 2023 row (6.8), so the
   machinery counts 4 of 4 years within the limit at s1 and s2 and 3 of
   4 at s3, and the range across scenarios (D96) is 3 to 4 with the
   minimum at s3; the brief reads 3 of 3, 2 of 3 and 2 to 3, the counts
   of a table without the 2023 values of B and C.

What the contract does not carry, emitted as far as it goes and reported
as a gap (the contract is never changed here):

- the tipping point of D3 (no field; ``README.md``: "The tipping point
  is not here: it is the Block 2 unit [D3]") — ``tipping_points()``
  returns it for the report and ``main`` prints it;
- a per-indicator state of a pair (``PairState`` has no indicator), so
  the readings "A vs B soil loss", "B vs C soil loss: Identical" and
  "water: every pair Not evaluated" cannot travel as states; water
  enters no state at all (D6: a missing value does not enter the state)
  and its not being evaluated is carried by ``indicator_ranking`` and by
  a reason of the document's state;
- ``measure_first`` is not keyed by a pair, so each item names its pair
  in ``what`` (three items, one per pair; the ranks stay the machinery's);
- the document's one ``state`` (D7): no decision says how it relates to
  the states of the pairs (issue #96, OPEN 5, to be settled with the
  tipping point), so it is null with its reason; its
  ``indicators_not_resolved`` is the union of the pairs'.

Pure functions only: no network, no file access, no clock. Run, from
the repository root::

    python -m demo.run
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from contracts.decision_output import (
    CountByDifferenceRange,
    CountBySignOfPointValue,
    CountByYear,
    Coverage,
    DecisionOutput,
    EqualToleranceItem,
    LimitItem,
    MeasureFirstItem,
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
    NOT_EVALUATED,
    DeclaredLimit,
    LimitCounts,
    TippingPoint,
    indicator_ranking,
    limit_counts,
    measurement_priority,
    pair_counts,
    pair_state,
    paired_differences,
    tipping_point,
)

from demo import matrix

# The three pairs of the matrix, in a fixed order.
PAIRS: tuple[tuple[str, str], ...] = (("A", "B"), ("A", "C"), ("B", "C"))

# The paired-difference method is OPEN (issue #96, OPEN 2); the example
# of the contract keeps this text, and so does the demo.
DIFFERENCE_METHOD = "OPEN: paired-difference method and citation, person-supplied"

# The provenance a difference carries: the label of the rows it comes
# from (DERIVED for soil loss, C4.6; SIMULATED for the carbon trend, as
# the matrix labels its carbon values).
_PROVENANCE_OF = {"soil_loss": "DERIVED", "soil_carbon_trend": "SIMULATED"}

# Which indicator the demo counts by the sign of the point value: the
# one whose tolerance of "equal" it declared (D87). Water and carbon
# carry no tolerance, so their by-sign counts stay missing (C3.1).
_TOLERANCE_DECLARED_FOR = ("soil_loss",)

# The reason a "Not separated: within uncertainty" state gives no reason:
# D86 writes none for it (K3), and no reason code is decided for that
# case (OPEN 12); the cases of the contract use NOT_AVAILABLE.
_REASON_MISSING_OF_D97 = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "D86 writes no reason for the state 'Not separated: within "
        "uncertainty' (D97) and no reason code is decided for it "
        "(contracts/decision_output/README.md, K3 and OPEN 12)"
    ),
)

_DOCUMENT_STATE_MISSING = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "no decision says how the document's one state relates to the "
        "states of its pairs (issue #96, OPEN 5, to be settled with the "
        "tipping point of D3), so the decision layer gives no document-"
        "level state; the states of the pairs are in 'pair_states'"
    ),
)


def _missing(part) -> Missing | None:
    """A missing part of the results contract, in the shape of the inputs."""
    if part is None:
        return None
    return Missing(reason=part.reason, detail=part.detail)


def _range(part) -> Range | None:
    """A range of the results contract, in the shape of the inputs."""
    if part is None:
        return None
    return Range(low=part.low, high=part.high, kind=part.kind)


def counts_by_year(
    table: ResultsTable | None = None,
    limits: Mapping[str, DeclaredLimit] | None = None,
) -> dict[tuple[str, str, str, str | None, str | None], LimitCounts]:
    """The counts of D1 on the matrix (D94, D95, D90; D60 without a limit)."""
    return limit_counts(
        table if table is not None else matrix.thin_matrix(),
        matrix.LIMITS if limits is None else limits,
        equal_to_limit_counts_as_within=True,
    )


def ranges_across_scenarios(
    counts: dict[
        tuple[str, str, str, str | None, str | None], LimitCounts
    ] | None = None,
) -> list[RangeAcrossScenarios]:
    """The summary of D96: minimum to maximum of the years within the limit
    across the scenarios, naming the scenario of the minimum.

    The decision functions give no such summary (it is the producer's);
    when several scenarios share the minimum, the demo names the first
    in the person's order — which one to name is OPEN (issue #96, OPEN
    item 11). A key no scenario judges (D60: no declared limit) is
    summarised as missing with its reason, never as zero.
    """
    if counts is None:
        counts = counts_by_year()
    items: list[RangeAcrossScenarios] = []
    for key in sorted({(key[0], *key[2:]) for key in counts}, key=repr):
        rotation_id, indicator, carbon_model, computation = key
        withins = {
            count.scenario_id: count.within
            for count in counts.values()
            if (count.rotation_id, count.indicator, count.carbon_model,
                count.computation) == key
            and count.within is not None
        }
        if not withins:
            items.append(
                RangeAcrossScenarios(
                    rotation_id=rotation_id,
                    indicator=indicator,
                    carbon_model=carbon_model,
                    computation=computation,
                    minimum=None,
                    maximum=None,
                    scenario_of_the_minimum=None,
                    missing=Missing(
                        reason="NOT_DECLARED",
                        detail=(
                            "no year of this key is judged against a limit, "
                            "so the range across scenarios is not given (D60)"
                        ),
                    ),
                )
            )
            continue
        minimum = min(withins.values())
        maximum = max(withins.values())
        scenario_of_the_minimum = next(
            scenario
            for scenario in matrix.SCENARIOS
            if withins[scenario] == minimum
        )
        items.append(
            RangeAcrossScenarios(
                rotation_id=rotation_id,
                indicator=indicator,
                carbon_model=carbon_model,
                computation=computation,
                minimum=minimum,
                maximum=maximum,
                scenario_of_the_minimum=scenario_of_the_minimum,
            )
        )
    return items


def paired_difference_items(
    table: ResultsTable | None = None,
) -> list[PairedDifferenceItem]:
    """Every paired difference of the matrix as a contract item (D2, D92)."""
    table = matrix.thin_matrix() if table is None else table
    items: list[PairedDifferenceItem] = []
    for first, second in PAIRS:
        for difference in paired_differences(table, first, second):
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
                    provenance=_PROVENANCE_OF[difference.indicator],
                    source=matrix.SOURCE,
                )
            items.append(
                PairedDifferenceItem(
                    pair=[first, second],
                    scenario_id=difference.scenario_id,
                    indicator=difference.indicator,
                    time_basis=(
                        "ag_year"
                        if difference.indicator == "soil_loss"
                        else "rotation"
                    ),
                    ag_year=difference.ag_year,
                    carbon_model=difference.carbon_model,
                    computation=difference.computation,
                    difference=value,
                    method=DIFFERENCE_METHOD,
                )
            )
    return items


def _tolerance_values() -> dict[str, float | None]:
    """The declared tolerance of "equal" per indicator (D87): soil loss only."""
    return {
        indicator: (
            matrix.EQUAL_TOLERANCE
            if indicator in _TOLERANCE_DECLARED_FOR
            else None
        )
        for indicator in ("soil_loss", "water_deficit_exposure", "soil_carbon_trend")
    }


def pair_cell_count_items(
    table: ResultsTable | None = None,
) -> list[PairCellCount]:
    """The two counts of the cells of each pair (D87 with D99), and the
    tolerance each needs (D87).

    The count by the sign of the point value is given only for the
    indicator whose tolerance of "equal" the demo declared; without a
    tolerance it is missing with its reason (C3.1, D87). Each count of the
    soil carbon trend names its carbon model and computation, as
    ``pair_counts`` gives them (D169): on this matrix, amg and
    end_minus_start; the other indicators name neither.
    """
    table = matrix.thin_matrix() if table is None else table
    tolerances = _tolerance_values()
    items: list[PairCellCount] = []
    for first, second in PAIRS:
        for count in pair_counts(
            table, first, second, equal_tolerance=matrix.EQUAL_TOLERANCE
        ):
            tolerance = tolerances[count.indicator]
            by_sign = (
                CountBySignOfPointValue(
                    better=count.by_point_sign.better,
                    worse=count.by_point_sign.worse,
                    equal=count.by_point_sign.equal,
                    missing_side=count.by_point_sign.missing_side,
                )
                if tolerance is not None
                else None
            )
            by_sign_missing = (
                None
                if tolerance is not None
                else Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "the designer of the case set no tolerance of "
                        f"'equal' for '{count.indicator}', so its cells are "
                        "counted by the range of their difference only (D87)"
                    ),
                )
            )
            items.append(
                PairCellCount(
                    pair=[first, second],
                    scenario_id=count.scenario_id,
                    indicator=count.indicator,
                    carbon_model=count.carbon_model,  # D169
                    computation=count.computation,  # D169
                    by_difference_range=CountByDifferenceRange(
                        strict_improvement=count.by_range.strict_improvement,
                        deterioration=count.by_range.deterioration,
                        not_separated=count.by_range.not_separated,
                    ),
                    by_sign_of_point_value=by_sign,
                    by_sign_of_point_value_missing=by_sign_missing,
                )
            )
    return items


def pair_states_of_the_set(
    table: ResultsTable | None = None,
) -> list[PairState]:
    """The state of each pair over the whole admitted set (D7, D74), with the
    coverage of D91 and the reason of D86 — or its missing part, for the
    state D86 writes no reason for (D97, K3)."""
    table = matrix.thin_matrix() if table is None else table
    items: list[PairState] = []
    for first, second in PAIRS:
        state = pair_state(table, first, second)
        differences = paired_differences(table, first, second)
        coverage = Coverage(
            cells_compared=sum(
                1 for difference in differences if difference.value is not None
            ),
            cells_of_the_pair=len(differences),
        )
        if state.state is None:
            items.append(
                PairState(
                    pair=[first, second],
                    value=None,
                    missing=Missing(
                        reason="NOT_AVAILABLE",
                        detail=(
                            "no paired difference of the pair holds a value: "
                            "the pair is not evaluated and has no state (D85)"
                        ),
                    ),
                    coverage=coverage,
                )
            )
            continue
        reason = REASON_OF_A_STATE.get(state.state)
        items.append(
            PairState(
                pair=[first, second],
                value=state.state,
                reason=reason,
                reason_missing=None if reason is not None else _REASON_MISSING_OF_D97,
                preferred_rotation_id=None,
                coverage=coverage,
            )
        )
    return items


def the_state(table: ResultsTable | None = None) -> State:
    """The document's one state (D7): null with its reason (OPEN 5), with the
    indicators the pairs do not resolve and one reason per pair.

    Water is never among the indicators not resolved: it was not
    evaluated, and what was not evaluated does not enter the state (D6).
    """
    table = matrix.thin_matrix() if table is None else table
    states = [pair_state(table, first, second) for first, second in PAIRS]
    not_resolved = sorted(
        {
            indicator
            for state in states
            for indicator in state.indicators_not_resolved
        }
    )
    # D152: "The conditions that did not give the state are still shown";
    # D166: the state of each scenario is shown beside the state of the set.
    reasons = [
        (
            f"the pair ('{first}', '{second}') is '{state.state}' "
            "(indicators not resolved: "
            f"{', '.join(state.indicators_not_resolved) or 'none'})"
            + (
                "; in each scenario: "
                + ", ".join(
                    f"'{scenario_id}' '{member or NOT_EVALUATED}'"
                    for scenario_id, member in state.by_scenario
                )
                if state.by_scenario
                else ""
            )
        )
        for (first, second), state in zip(PAIRS, states)
    ]
    water = indicator_ranking(table, "water_deficit_exposure")
    if water.every_value_missing:
        reasons.append(
            "water_deficit_exposure is not evaluated on this matrix: every "
            "value is missing NOT_AVAILABLE, so it enters no state and no "
            "ranking (D6)"
        )
    return State(
        value=None,
        missing=_DOCUMENT_STATE_MISSING,
        indicators_not_resolved=not_resolved,
        reasons=reasons,
    )


def measure_first(table: ResultsTable | None = None) -> list[MeasureFirstItem]:
    """The measurement priority of each pair (D4) as contract items.

    The contract's list is not keyed by a pair, so each item names its
    pair in ``what``; the ranks are the machinery's and the list stays in
    rank order. Each item is qualitative: no monetary value (#96).
    """
    table = matrix.thin_matrix() if table is None else table
    items: list[MeasureFirstItem] = []
    for first, second in PAIRS:
        priority = measurement_priority(table, first, second, matrix.UNCERTAIN_INPUTS)
        for item in priority.items:
            items.append(
                MeasureFirstItem(
                    rank=item.rank,
                    what=(
                        f"'{item.input_name}' (the 2022 soil loss of rotations "
                        f"B and C, {item.unit}) for the pair "
                        f"('{first}', '{second}')"
                    ),
                    why=item.why,
                )
            )
    return items


def _limits() -> list[LimitItem]:
    """The declared limit of soil loss, and the limits not declared (D60)."""
    return [
        LimitItem(
            indicator="soil_loss",
            limit=Value(
                value=matrix.SOIL_LOSS_LIMIT.limit,
                unit="t ha-1 yr-1",
                range_missing=Missing(
                    reason="NOT_DECLARED",
                    detail="the approved matrix declares the limit without a range",
                ),
                provenance="DECLARED",
                source=matrix.SOURCE,
            ),
        ),
        LimitItem(
            indicator="water_deficit_exposure",
            limit=Value(
                value=None,
                unit="dimensionless",
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "no limit is declared for water_deficit_exposure in "
                        "the approved matrix"
                    ),
                ),
            ),
        ),
        LimitItem(
            indicator="soil_carbon_trend",
            limit=Value(
                value=None,
                unit="t C ha-1 yr-1",
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "no limit is declared for soil_carbon_trend in the "
                        "approved matrix"
                    ),
                ),
            ),
        ),
    ]


def _equal_tolerances() -> list[EqualToleranceItem]:
    """The tolerance of "equal" (D87): declared for soil loss (see
    ``demo/matrix.py``), not set for the other indicators."""
    return [
        EqualToleranceItem(
            indicator="soil_loss",
            tolerance=Value(
                value=matrix.EQUAL_TOLERANCE,
                unit="t ha-1 yr-1",
                range_missing=Missing(
                    reason="NOT_DECLARED",
                    detail="the tolerance of 'equal' carries no range",
                ),
                provenance="DECLARED",
                source=(
                    "demo reading of issue #240: exact point equality — the "
                    "expected point-sign counts hold for every tolerance "
                    "below 0.5; to be confirmed by the designer of the case"
                ),
            ),
        ),
        EqualToleranceItem(
            indicator="water_deficit_exposure",
            tolerance=Value(
                value=None,
                unit="dimensionless",
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "the designer of the case set no tolerance of "
                        "'equal' for water_deficit_exposure"
                    ),
                ),
            ),
        ),
        EqualToleranceItem(
            indicator="soil_carbon_trend",
            tolerance=Value(
                value=None,
                unit="t C ha-1 yr-1",
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "the designer of the case set no tolerance of "
                        "'equal' for soil_carbon_trend"
                    ),
                ),
            ),
        ),
    ]


def _counts_by_year_items(
    counts: Mapping[tuple[str, str, str, str | None, str | None], LimitCounts]
) -> list[CountByYear]:
    """The counts of D1 as contract items (D94: nothing across scenarios)."""
    return [
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
                    missing=_missing(row.missing),
                )
                for row in count.not_evaluated
            ],
        )
        for count in counts.values()
    ]


def build_decision_output(table: ResultsTable | None = None) -> DecisionOutput:
    """The decision output document of the contract, over the matrix.

    Everything the document carries comes from the decision functions or
    from the approved matrix; the one number the demo itself sets is the
    tolerance of "equal" (see ``demo/matrix.py``).
    """
    table = matrix.thin_matrix() if table is None else table
    counts = counts_by_year(table)
    return DecisionOutput(
        contract="decision_output",
        example_data=True,
        case_id=table.case_id,
        field_id=table.field_id,
        rotations=list(matrix.ROTATIONS),
        scenarios=list(matrix.SCENARIOS),
        limits=_limits(),
        counts_by_year=_counts_by_year_items(counts),
        range_across_scenarios=ranges_across_scenarios(counts),
        paired_differences=paired_difference_items(table),
        equal_tolerances=_equal_tolerances(),
        pair_cell_counts=pair_cell_count_items(table),
        pair_states=pair_states_of_the_set(table),
        state=the_state(table),
        measure_first=measure_first(table),
    )


def tipping_points(
    table: ResultsTable | None = None,
) -> tuple[tuple[str, str, TippingPoint], ...]:
    """The tipping point of u for each pair (D3, as D103 reads it).

    The decision output contract carries no tipping point, so this stays
    beside the document; ``main`` prints it.
    """
    table = matrix.thin_matrix() if table is None else table
    return tuple(
        (first, second, tipping_point(table, first, second, matrix.UNCERTAIN_INPUT))
        for first, second in PAIRS
    )


def main() -> None:
    """Print the decision output document and the tipping points."""
    document = build_decision_output()
    print(json.dumps(document.model_dump(mode="json"), indent=2))
    print()
    print(
        "Tipping points of the uncertain input u "
        "(D3; the contract carries no field for them):"
    )
    for first, second, point in tipping_points():
        states = ", ".join(f"{value} -> '{state}'" for value, state in point.states)
        print(f"  pair ('{first}', '{second}'): {states};")
        print(f"    bracket {point.bracket} — {point.reason}")


if __name__ == "__main__":
    main()
