"""The bounded matrix through the decision (unit l2/bounded-matrix-decision).

This module runs the bounded matrix of ``demo/bounded.py`` - the three
rotation templates of D72 over the demonstration point of D83, in the one
admitted residue-cover level of D115 and D171 (the lower level; the upper
level is missing for R2 and R3, so it is not run and not admitted, and is
listed with its reason), every cell missing under the real-or-missing
rule - through the decision functions of ``decision/functions.py``: the
counts by year (D1, with no limit declared, so D60 judges nothing; the
water cells are per agricultural year, D157, so they are counted too),
the paired differences and their ranges (D2, D92: every difference is
missing ``MISSING_INPUT`` naming its sides, so no range exists to
compute), the counts of the cells of a pair and the coverage (D87, D99,
D91, one count per carbon model and computation, D169), the state of
each pair (D7, D85 with D166 and D175, read from ``pair_state`` and the
coverage from ``dominance``, never written by hand here), dominance
(D5), the ranking of an indicator (D6: every value of every indicator is
missing, so nothing is ranked) and the measurement priority (D4: no
uncertain input's mapping can be declared over this table, so the
machinery answers over none and the list is empty) - and emits what the
decision output contract of ``contracts/decision_output/`` carries.

What the honest state of the demo gives, and this module reports rather
than hides (the contract is never changed here):

- every cell is missing ``MISSING_INPUT``, "input not available: climate
  (site data: climate)". The six engines are built and the runner wires
  them (EP1 to EP6, ``api/engines.py``), but the demonstration holds no
  climate record of the point, so the runner calls none of them and
  gives that answer for every part alike (see ``demo/bounded.py``);
- the admitted set of the table is the lower level of the block alone
  (D171): D115 leaves the upper level missing for R2 and R3, so that
  level is not run for them, is listed with its reason beside the table,
  and no pair is evaluated at it; under D176, condition 2, that level
  makes the member not evaluated and is never read as a tipping point of
  the cover;
- no limit is declared for any indicator of the bounded case (none is
  approved; D89 keeps the user's limit apart from the verified T, and no
  T is verified), so every count of D1 judges nothing (D60) and the
  range across scenarios of D96 is missing with its reason for every
  rotation and indicator;
- no tolerance of "equal" is set by the designer of the case for any
  indicator (D87), so the count by the sign of the point value stays
  missing (C3.1) and only the count by the range exists - all zeros, no
  cell being compared;
- the counts of the cells of a pair are one per carbon model and
  computation (D169): the six carbon cells of the admitted level are six
  counts of one cell each, and every item of the document names its
  model and its computation, so the cells of AMG and of RothC are never
  added in one count (D155, D169);
- the state of each pair comes from ``pair_state`` and its coverage from
  ``dominance``, both of the machinery: over the one admitted scenario
  no paired difference holds a value, so the pair is not evaluated and
  has no state (D85, D151), and the computation of the trend that enters
  the state is ``end_minus_start`` (D173, C1.6), the default no user has
  overridden. The rule of D165 and the worst-case arithmetic of D92 have
  no cell to speak of on this table - no difference holds a value, so no
  range exists to touch or cross zero;
- the tipping point of D3 is not computed: the ``UncertainInput`` form
  cannot honestly carry the residue-cover block (the cover drives no
  cell of the table, D116; its upper level is not admitted at all for
  R2 and R3 under D171 and holds no single declared value for R1
  either), so no ``(value, scenario)`` mapping is declared - a gap
  reported beside the document, to be settled with the form when a
  climate record of the point is admitted. D176 answers the form of the
  question for #267 - yes, this block at its two levels is the input of
  the sweep - with four conditions, all four open today: (1) the phases
  of D117 are not built (the gap below); (2) a level D115 leaves missing
  makes that member not evaluated and is never read as a tipping point
  of the cover; (3) with the declared ``C`` of D148 and D158 EP1 does
  not read the cover and gives one figure for both rotations, and the
  only engine that reads the declared cover, the water balance (D110,
  D116), has no number, so the expected result of a real sweep is "no
  tipping point", for that reason; (4) the measured input of D10 and the
  check of D12 wait for a path that reruns the engines with the measured
  cover;
- the phases of D109 nested inside each level (D117) are not
  materialized: the rotations hold one, two and four phases, and the
  results contract requires the same cells for every rotation, so
  per-phase scenarios cannot be written without inventing rows; the one
  admitted level stands as one scenario, the degenerate single-phase
  reading the machinery accepts and names as such (see
  ``demo/bounded.py``). When they materialize, the scenarios of a pair
  are every combination of the phases of the two rotations, N x M of
  them (D172).

The return path this unit documents: when a climate record of the point
is admitted, the cells of ``demo/bounded.py`` fill with real engine
values, the mapping of the cover block onto the filled cells is declared
to the machinery, and the same tests of ``demo/test_bounded.py`` assert
real values - the arithmetic of D92 over whatever ranges exist then
replaces the missing differences asserted today.

Pure functions only: no network, no file access, no clock. Run, from the
repository root::

    python -m demo.run_bounded
"""

from __future__ import annotations

import json
from collections.abc import Mapping

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
    LimitCounts,
    NOT_EVALUATED,
    dominance,
    indicator_ranking,
    limit_counts,
    measurement_priority,
    pair_counts,
    pair_state,
    paired_differences,
)

from demo import bounded

# The three pairs of the bounded matrix, in a fixed order.
PAIRS: tuple[tuple[str, str], ...] = (
    ("R1", "R2"),
    ("R1", "R3"),
    ("R2", "R3"),
)

# The paired-difference method is OPEN (issue #96, OPEN 2); the example of
# the contract keeps this text, and so does the demo.
DIFFERENCE_METHOD = "OPEN: paired-difference method and citation, person-supplied"

# The indicators of the document, in the order of the conventions sheet.
INDICATORS: tuple[str, ...] = (
    "soil_loss",
    "water_deficit_exposure",
    "soil_carbon_trend",
)

_UNITS: dict[str, str] = {
    "soil_loss": "t ha-1 yr-1",
    "water_deficit_exposure": "dimensionless",
    "soil_carbon_trend": "t C ha-1 yr-1",
}

# No uncertain input's mapping can be declared over this table (see the
# module docstring): the machinery of D4 is called with none.
UNCERTAIN_INPUTS: tuple = ()

_DOCUMENT_STATE_MISSING = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "no decision says how the document's one state relates to the "
        "states of its pairs (issue #96, OPEN 5, to be settled with the "
        "tipping point of D3), and over this matrix no pair is evaluated "
        "at all, so the decision layer gives no document-level state; the "
        "states of the pairs are in 'pair_states'"
    ),
)

# D86 writes no reason for the state "Not separated: within uncertainty"
# (D97) and no reason code is decided for it (K3, OPEN 12); the cases of
# the contract use NOT_AVAILABLE (the text of demo/run.py).
_REASON_MISSING_OF_D97 = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "D86 writes no reason for the state 'Not separated: within "
        "uncertainty' (D97) and no reason code is decided for it "
        "(contracts/decision_output/README.md, K3 and OPEN 12)"
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
) -> dict[tuple[str, str, str, str | None, str | None], LimitCounts]:
    """The counts of D1 on the bounded matrix (D94, D95, D60: no limit is
    declared, so no year is judged and every row is not evaluated).

    D157 puts the water cells on the agricultural year too, so soil loss
    and water deficit exposure are both counted by year; only the soil
    carbon trend, one value per rotation (C1.5), has no count of years
    (D95).
    """
    return limit_counts(
        bounded.bounded_matrix() if table is None else table,
        {},  # no declared limit for any indicator of the bounded case
        equal_to_limit_counts_as_within=True,  # D90; callers pass True
    )


def ranges_across_scenarios(
    counts: dict[
        tuple[str, str, str, str | None, str | None], LimitCounts
    ]
    | None = None,
) -> list[RangeAcrossScenarios]:
    """The summary of D96 over the admitted set: missing with its
    reason for every rotation and indicator, no year being judged against
    a limit (D60).

    Which scenario to name were several to share the minimum is OPEN
    (issue #96, OPEN 11); over this matrix no minimum exists to name.
    """
    if counts is None:
        counts = counts_by_year()
    items: list[RangeAcrossScenarios] = []
    for key in sorted({(key[0], *key[2:]) for key in counts}, key=repr):
        rotation_id, indicator, carbon_model, computation = key
        withins = {
            count.scenario_id: count.within
            for count in counts.values()
            if (
                count.rotation_id,
                count.indicator,
                count.carbon_model,
                count.computation,
            )
            == key
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
                            "no limit is declared for this indicator in the "
                            "bounded matrix, so no year is judged against a "
                            "limit and the range across scenarios is not "
                            "given (D60, D96)"
                        ),
                    ),
                )
            )
            continue
        minimum = min(withins.values())
        maximum = max(withins.values())
        scenario_of_the_minimum = next(
            scenario
            for scenario in bounded.SCENARIOS
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
    """Every paired difference of the bounded matrix as a contract item
    (D2, D92): each is missing ``MISSING_INPUT`` naming both sides."""
    table = bounded.bounded_matrix() if table is None else table
    items: list[PairedDifferenceItem] = []
    for first, second in PAIRS:
        for difference in paired_differences(table, first, second):
            value = Value(
                value=difference.value,
                unit=difference.unit,
                missing=_missing(difference.missing),
                range=_range(difference.range),
                range_missing=_missing(difference.range_missing),
            )
            items.append(
                PairedDifferenceItem(
                    pair=[first, second],
                    scenario_id=difference.scenario_id,
                    indicator=difference.indicator,
                    time_basis=(
                        "ag_year"
                        if difference.indicator
                        in ("soil_loss", "water_deficit_exposure")  # D157
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


def pair_cell_count_items(
    table: ResultsTable | None = None,
) -> list[PairCellCount]:
    """The two counts of the cells of each pair (D87 with D99, keyed by
    D169) and the tolerance each needs (D87).

    No tolerance of "equal" is set for any indicator of the bounded case,
    so every count by the sign of the point value is missing with its
    reason (C3.1, D87) and the count by the range alone remains - all
    zeros, no cell holding a value on both sides. D169 ("One count per
    pair, scenario, indicator, carbon model and computation, so that the
    cells of AMG and of RothC, which D155 never reads together, are never
    added in one count") splits the six carbon cells of the admitted
    level into six counts of one cell each: each item names its carbon
    model and its computation, as the machinery's ``PairCounts`` does.
    """
    table = bounded.bounded_matrix() if table is None else table
    items: list[PairCellCount] = []
    for first, second in PAIRS:
        # The tolerance argument satisfies the machinery's signature; no
        # cell holds a value on both sides, so it decides nothing here, and
        # the count it feeds is replaced below by its missing part.
        for count in pair_counts(table, first, second, equal_tolerance=0.0):
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
                    by_sign_of_point_value=None,
                    by_sign_of_point_value_missing=Missing(
                        reason="NOT_DECLARED",
                        detail=(
                            "the designer of the case set no tolerance of "
                            f"'equal' for '{count.indicator}' in the bounded "
                            "matrix, so its cells cannot be counted by the "
                            "sign of the point value (D87, C3.1)"
                        ),
                    ),
                )
            )
    return items


def pair_states_of_the_set(
    table: ResultsTable | None = None,
) -> list[PairState]:
    """The state of each pair over the whole admitted set (D7, D74), read
    from the machinery: the state is ``pair_state``'s and the coverage of
    D91 is ``dominance``'s, both of ``decision/functions.py``; this
    function writes no state of its own.

    Over the one admitted scenario no paired difference holds a value
    (every cell is missing the climate of the point), so the machinery
    gives no state (D85, D151) and the item says why. The test pins that
    the value is the machinery's on a filled variant of the table.
    """
    table = bounded.bounded_matrix() if table is None else table
    items: list[PairState] = []
    for first, second in PAIRS:
        read = pair_state(table, first, second)
        covered = dominance(table, first, second)
        coverage = Coverage(
            cells_compared=covered.cells_compared,
            cells_of_the_pair=covered.cells_of_the_pair,
        )
        if read.state is None:
            items.append(
                PairState(
                    pair=[first, second],
                    value=None,
                    missing=Missing(
                        reason="NOT_AVAILABLE",
                        detail=(
                            "no paired difference of the pair holds a value "
                            "(every cell is missing MISSING_INPUT, the "
                            "climate of the point): the pair is not "
                            "evaluated and has no state (D85, D151)"
                        ),
                    ),
                    coverage=coverage,
                )
            )
            continue
        reason = REASON_OF_A_STATE.get(read.state)
        items.append(
            PairState(
                pair=[first, second],
                value=read.state,
                reason=reason,
                reason_missing=(
                    None if reason is not None else _REASON_MISSING_OF_D97
                ),
                preferred_rotation_id=None,
                coverage=coverage,
            )
        )
    return items


def the_state(table: ResultsTable | None = None) -> State:
    """The document's one state (D7): null with its reason (OPEN 5), with
    the indicators the pairs do not resolve, one reason per pair (the
    machinery's, with the state of each scenario beside the state of the
    set when the admitted set holds several, D152, D166), one per
    indicator not evaluated, and the listing of the level D115 leaves
    missing (D171, D176 condition 2).

    No indicator is named in ``indicators_not_resolved``: what was not
    evaluated does not enter the state (D6), and nothing was evaluated.
    """
    table = bounded.bounded_matrix() if table is None else table
    states = [pair_state(table, first, second) for first, second in PAIRS]
    not_resolved = sorted(
        {
            indicator
            for state in states
            for indicator in state.indicators_not_resolved
        }
    )
    reasons = []
    for (first, second), state in zip(PAIRS, states):
        reason = (
            f"the pair ('{first}', '{second}') is not evaluated: no paired "
            "difference holds a value, so it has no state (D85) and no "
            "indicator is resolved by it"
        )
        if state.by_scenario:
            # D152: "The conditions that did not give the state are still
            # shown"; D166: the state of each scenario is shown beside the
            # state of the set. A member without a state is written with
            # the label D151 gives that absence (D175 keeps it from ever
            # making the set a robust preference).
            reason += (
                "; in each scenario: "
                + ", ".join(
                    f"'{scenario_id}' '{member or NOT_EVALUATED}'"
                    for scenario_id, member in state.by_scenario
                )
            )
        reasons.append(reason)
    for indicator in INDICATORS:
        ranking = indicator_ranking(table, indicator)
        if ranking.every_value_missing:
            reasons.append(
                f"'{indicator}' is not evaluated on this matrix: every value "
                "is missing MISSING_INPUT, 'input not available: climate "
                "(site data: climate)' (the engines are built and the runner "
                "wires them, but the demonstration holds no climate record "
                "of the point), so it enters no state and no ranking (D6)"
            )
    missing_upper = [
        cover
        for cover in bounded.COVER_AT_THE_UPPER_LEVEL
        if cover.upper_missing is not None
    ]
    listed = "; ".join(
        f"{cover.rotation_id} ({cover.fallow}: {cover.upper_missing.reason})"
        for cover in missing_upper
    )
    reasons.append(
        "the upper level of the residue-cover block of D75 is not run and "
        "not admitted: D115 leaves it missing for "
        f"{', '.join(sorted({cover.rotation_id for cover in missing_upper}))} "
        f"({listed}), and a level a decision leaves missing is not run and "
        "is not admitted, but listed with its reason (D171); no pair is "
        "evaluated at it and it is never read as a tipping point of the "
        "cover (D176, condition 2); no uncertain input's mapping can be "
        "declared over the admitted level either (the cover drives no cell "
        "of the table, D116), so the priority list of D4 is the machinery's "
        "answer over no declared inputs (empty) and no tipping point of D3 "
        "is computed"
    )
    return State(
        value=None,
        missing=_DOCUMENT_STATE_MISSING,
        indicators_not_resolved=not_resolved,
        reasons=reasons,
    )


def measurement_priorities(
    table: ResultsTable | None = None,
):
    """The measurement priority of each pair (D4) over the declared inputs
    (none): the machinery's answer is an empty list per pair, the base
    state being that of a pair not evaluated."""
    table = bounded.bounded_matrix() if table is None else table
    return {
        (first, second): measurement_priority(table, first, second, UNCERTAIN_INPUTS)
        for first, second in PAIRS
    }


def _limits() -> list[LimitItem]:
    """The limits of the bounded case: none declared, each missing with its
    reason and never zero (D60, D89)."""
    return [
        LimitItem(
            indicator=indicator,
            limit=Value(
                value=None,
                unit=_UNITS[indicator],
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        f"no limit is declared for '{indicator}' in the "
                        "bounded matrix of the demonstration; admissibility "
                        "is decided only by D74 against a verified T, and "
                        "no T is verified (D89)"
                    ),
                ),
            ),
        )
        for indicator in INDICATORS
    ]


def _equal_tolerances() -> list[EqualToleranceItem]:
    """The tolerance of "equal" (D87): set for no indicator of the bounded
    case, each missing with its reason."""
    return [
        EqualToleranceItem(
            indicator=indicator,
            tolerance=Value(
                value=None,
                unit=_UNITS[indicator],
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "the designer of the case set no tolerance of "
                        f"'equal' for '{indicator}' in the bounded matrix "
                        "(D87)"
                    ),
                ),
            ),
        )
        for indicator in INDICATORS
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
    """The decision output document of the contract, over the bounded matrix.

    Everything the document carries comes from the decision functions or
    from the bounded matrix; the demo itself sets no value, limit,
    tolerance or threshold anywhere.
    """
    table = bounded.bounded_matrix() if table is None else table
    counts = counts_by_year(table)
    return DecisionOutput(
        contract="decision_output",
        example_data=True,
        case_id=table.case_id,
        field_id=table.field_id,
        rotations=list(bounded.ROTATIONS),
        scenarios=list(bounded.SCENARIOS),
        limits=_limits(),
        counts_by_year=_counts_by_year_items(counts),
        range_across_scenarios=ranges_across_scenarios(counts),
        paired_differences=paired_difference_items(table),
        equal_tolerances=_equal_tolerances(),
        pair_cell_counts=pair_cell_count_items(table),
        pair_states=pair_states_of_the_set(table),
        state=the_state(table),
        measure_first=[],
    )


def _cover_block_text() -> str:
    """The residue-cover block of D75 at its two levels of D115, as text,
    with the listing of the level not admitted (D171)."""
    lines = [
        "The admitted uncertainty: the residue-cover block of D75 at the "
        "levels of D115; the admitted set of the table is the lower level "
        "alone (D171).",
        "  lower level (admitted, the one scenario of the table): 0% "
        "residue cover, bare soil (FAO-56 with no mulch), every fallow of "
        "every rotation;",
        "  upper level (not run, not admitted: D115 leaves it missing for "
        "R2 and R3; listed with its reason, D171; never read as a tipping "
        "point of the cover, D176 condition 2): the cap of the MGAP / "
        "Facultad de Agronomia table for the sequence,",
    ]
    for cover in bounded.COVER_AT_THE_UPPER_LEVEL:
        if cover.upper_percent is not None:
            # The "admitted alone" parenthetical is true only where every
            # fallow of the rotation holds a cap (R1): a rotation with one
            # uncapped fallow (R2, R3) has its upper level not admitted at
            # all under D171, whatever this row's own cap says.
            every_fallow_capped = all(
                other.upper_missing is None
                for other in bounded.COVER_AT_THE_UPPER_LEVEL
                if other.rotation_id == cover.rotation_id
            )
            if every_fallow_capped:
                lines.append(
                    f"    {cover.rotation_id}, {cover.fallow}: "
                    f"{cover.upper_percent}% (admitted for this rotation alone; "
                    "no table of the three rotations carries it, the contract "
                    "giving every rotation the same cells)"
                )
            else:
                lines.append(
                    f"    {cover.rotation_id}, {cover.fallow}: "
                    f"{cover.upper_percent}% (the cap of this one fallow; the "
                    "rotation's upper level is still not admitted - another "
                    "fallow has no cap, D115)"
                )
        else:
            lines.append(
                f"    {cover.rotation_id}, {cover.fallow}: MISSING "
                f"({cover.upper_missing.reason}) - {cover.upper_missing.detail}"
            )
    lines.append(
        "    the row 'winter cereal, second-crop soybean, then soybean' "
        f"({bounded.CAP_READ_BY_NO_ROTATION.upper_percent}%) is read by no "
        "rotation of D72; the phases of each rotation (D109: one, two and "
        "four) nest inside each level (D117) and are not materialized in "
        "this table - a gap reported in demo/bounded.py, and condition 1 "
        "of D176 for the sweep of #267."
    )
    return "\n".join(lines)


def main() -> None:
    """Print the decision output document, the cover block and the gaps."""
    document = build_decision_output()
    print(json.dumps(document.model_dump(mode="json"), indent=2))
    print()
    print(_cover_block_text())
    print()
    print(
        "Every cell is missing MISSING_INPUT, 'input not available: climate "
        "(site data: climate)': the six engines are built and the runner "
        "wires them (EP1 to EP6, api/engines.py), but the demonstration "
        "holds no climate record of the point, so the runner calls none of "
        "them (the real-or-missing rule, approved 15 November 2026); when a "
        "climate record of the point is admitted the cells fill and the "
        "same tests assert real values. No tipping point of D3 is computed "
        "and the priority list of D4 is empty: no uncertain input's mapping "
        "can be declared over this table (the cover block drives no cell of "
        "it, and its upper level is not admitted for R2 and R3). D176 "
        "confirms the block, at its two levels, as the input of the sweep "
        "of #267, with its four conditions: the phases of D117 are not "
        "built yet (condition 1, a gap reported above), the upper level "
        "D115 leaves missing makes that member not evaluated and is never "
        "read as a tipping point of the cover (condition 2), until the "
        "water balance carries a number the expected result of the real "
        "sweep is \"no tipping point\" (condition 3), and the measured "
        "input of D10 waits for a path that reruns the engines with the "
        "measured cover (condition 4)."
    )


if __name__ == "__main__":
    main()
