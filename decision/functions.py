"""Pure decision functions on a results table.

Each public function implements the logic of one D entry of
``docs/VALIDATION.md`` (D1 to D7, D10, D12), as the lead developer
decided it on 14 November 2026 together with the decisions D74 and D85
to D99 of issue #77 that those entries record and, for D3, D4, D10 and
D12, with D103 and D117 of the same issue and with the person-approved
case of issue #223 (the v2.1 tables of #177, approved by the table
designer and confirmed by the lead developer in review of #177). The
decisions D151 to D156 and D165 to D176 of the same issue (15 November
2026) settle how the state reads a range that touches zero (D165), a set
of scenarios and the phases of an input value (D166, D175, D117), the
counts of the carbon trend (D169), the computation of the trend that
enters the state (D173) and the label of dominance (D174); unit
l2/decision-rule-d165-d176 brought this module in line with them. What
those entries leave OPEN stays OPEN and is marked where it touches this
module.

The functions are pure: no network call, no file access, no clock, no
global state. They read a ``ResultsTable`` of ``contracts/results/`` and
never change it. This module holds no threshold and no expected value of
the science: every limit comes in as an argument, declared by a person
(``DeclaredLimit``), every bracket and rank is read off the table and
the person's mapping of the uncertain inputs (``UncertainInput``), and
the only number the decided logic names, zero as the point a difference
is read against (D74, D93, D98), appears as that constant of the
decisions. The forms of ``DeclaredLimit``, ``UncertainInput``,
``Measurement`` and of the result records are PROPOSED (blueprint
section 3.7); the logic they carry is the decided part.

The names of the states of a pair are exactly those of D88 with the
name D97 adds (entry D7); no synonym is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from contracts.results import models
from contracts.results.models import (
    DEFAULT_TREND_COMPUTATION,
    TREND_COMPUTATIONS,
    Missing,
    Range,
    ResultsTable,
    ResultsTableRow,
)

# --- the names of the states of a pair (D88, with the name D97 adds) -----------
#
# D88 on #77: "Not evaluated" (D85) · "Identical" · "Not separated:
# uncertainty missing" · "Not robust across scenarios" · "Robust
# preference" (D74); D97 adds "Not separated: within uncertainty".
# "Not evaluated" is the absence of a state (D85: the pair is "not
# evaluated", with no state), so ``PairState.state`` is ``None`` for it.
# D151 decides it: "Not evaluated" is "the label shown for that absence,
# not a sixth state name".
NOT_EVALUATED = "Not evaluated"
IDENTICAL = "Identical"
NOT_SEPARATED_UNCERTAINTY_MISSING = "Not separated: uncertainty missing"
NOT_SEPARATED_WITHIN_UNCERTAINTY = "Not separated: within uncertainty"
NOT_ROBUST_ACROSS_SCENARIOS = "Not robust across scenarios"
ROBUST_PREFERENCE = "Robust preference"

# --- the classes of one paired cell (D93, as D98 amends it) --------------------
#
# D93 on #77, read in the direction of the indicator (C1.1): a "strict
# improvement" only when the whole range of the difference lies on the
# better side of zero; a "deterioration" only when the whole range lies
# on the worse side; a range that touches or crosses zero is "not
# separated" for that cell (the count by range of D99 keeps these three
# classes, D167). Whether a cell blocks a robust preference is another
# question, which D98 answers as D165 reads it: a cell is non-deteriorating
# when the whole range of its difference lies on the side of zero that is
# not worse, zero included, so a cell that touches zero from that side is
# "not separated" and still does not block; a range that crosses zero, or
# that touches it from the worse side, blocks (see ``_blocks``).
NOT_SEPARATED = "not separated"
STRICT_IMPROVEMENT = "strict improvement"
DETERIORATION = "deterioration"

# D174 on #77: the output of dominance "is labelled "by point value", as
# D99 labels its second count".
BY_POINT_VALUE = "by point value"


# --- a limit declared by a person (D1) ----------------------------------------


class DeclaredLimit(BaseModel):
    """A limit a person declares for one indicator (D1).

    It travels like a value: with the provenance label ``DECLARED``
    (C4.1) and its source (C4.2). The preferred side of the limit is not
    a field: it is read from the ``direction`` of the indicator's rows
    (C1.1), so a limit of ``soil_loss`` is an upper limit and a limit of
    ``soil_carbon_trend`` a lower limit. Whether a value equal to the
    limit counts as within is decided inclusive (D90); the counting
    function keeps it as a required argument with no default, and
    callers pass ``True``.

    PROPOSED form (blueprint section 3.7): no contract fixes yet how a
    declared limit travels.
    """

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False
    )

    indicator: models.IndicatorId
    limit: float
    provenance: Literal["DECLARED"]
    source: models.Text


# --- D1: counts by year against a declared limit -------------------------------


@dataclass(frozen=True)
class NotEvaluated:
    """One row that holds no value: not evaluated, with its reason (C3.2)."""

    rotation_id: str
    scenario_id: str
    indicator: str
    ag_year: int | None
    carbon_model: str | None
    computation: str | None
    missing: Missing


@dataclass(frozen=True)
class LimitCounts:
    """The counts of one rotation, scenario, indicator, carbon model and
    computation against a limit (D1, keyed by D94).

    Only rows whose ``time_basis`` is ``ag_year`` are counted (D95): an
    indicator on another time basis has no count of years at all. Of
    those, ``evaluated`` rows hold a value; ``within`` are on the
    preferred side of the limit and ``outside`` are not. A row without a
    value is in ``not_evaluated``, with its reason: it never counts as
    within or outside, and never as zero. Without a declared limit for
    the indicator nothing is judged (D60): no row is evaluated and both
    ``within`` and ``outside`` are ``None``.
    """

    rotation_id: str
    scenario_id: str
    indicator: str
    carbon_model: str | None
    computation: str | None
    limit: DeclaredLimit | None
    evaluated: int
    within: int | None
    outside: int | None
    not_evaluated: tuple[NotEvaluated, ...]


def _is_on_the_preferred_side(
    row: ResultsTableRow, limit: float, equal_is_within: bool
) -> bool:
    """Which side is the preferred one is read from the row's direction (C1.1)."""
    if row.direction == "lower_is_better":
        return row.value <= limit if equal_is_within else row.value < limit
    return row.value >= limit if equal_is_within else row.value > limit


def limit_counts(
    table: ResultsTable,
    limits: Mapping[str, DeclaredLimit],
    *,
    equal_to_limit_counts_as_within: bool,
) -> dict[tuple[str, str, str, str | None, str | None], LimitCounts]:
    """Count, per rotation, scenario, indicator, carbon model and computation,
    the agricultural-year rows that hold a value and those within a
    declared limit (D1, D94, D95, D60).

    One count per rotation, scenario, indicator, carbon model and
    computation; nothing is counted across them (D94). Years are counted
    only over rows whose ``time_basis`` is ``ag_year``; an indicator on
    another time basis (the soil carbon trend; the water ratio when it is
    per rotation) has no count of years (D95), so a limit declared for
    it is not used in the counts. Without a declared limit for the
    indicator no row is evaluated: ``within`` and ``outside`` are
    ``None`` (D60). A row with a missing value is never counted as
    within or outside the limit: it is reported in ``not_evaluated``
    with its reason. ``equal_to_limit_counts_as_within`` carries D90: a
    value equal to the limit counts as within; callers pass ``True``.
    """
    indicators = {row.indicator for row in table.rows}
    unknown = sorted(set(limits) - indicators)
    if unknown:
        raise ValueError(
            "a limit is declared for an indicator the table does not hold: "
            f"{unknown}; the table holds {sorted(indicators)}"
        )
    groups: dict[
        tuple[str, str, str, str | None, str | None], list[ResultsTableRow]
    ] = {}
    for row in table.rows:
        groups.setdefault(
            (
                row.rotation_id,
                row.scenario_id,
                row.indicator,
                row.carbon_model,
                row.computation,
            ),
            [],
        ).append(row)
    counts: dict[tuple[str, str, str, str | None, str | None], LimitCounts] = {}
    for key in sorted(
        groups,
        key=lambda item: (item[0], item[1], item[2], item[3] or "", item[4] or ""),
    ):
        rows = groups[key]
        # D95: only rows on the time basis 'ag_year' carry a count of years.
        year_rows = [row for row in rows if row.time_basis == "ag_year"]
        if not year_rows:
            continue
        limit = limits.get(key[2])
        with_value = [row for row in year_rows if row.value is not None]
        if limit is None:
            # D60: without a declared limit nothing is judged: no row is
            # evaluated and the years within the limit are null.
            evaluated, within, outside = 0, None, None
        else:
            evaluated = len(with_value)
            within = sum(
                1
                for row in with_value
                if _is_on_the_preferred_side(
                    row, limit.limit, equal_to_limit_counts_as_within
                )
            )
            outside = evaluated - within
        counts[key] = LimitCounts(
            rotation_id=key[0],
            scenario_id=key[1],
            indicator=key[2],
            carbon_model=key[3],
            computation=key[4],
            limit=limit,
            evaluated=evaluated,
            within=within,
            outside=outside,
            not_evaluated=tuple(
                NotEvaluated(
                    rotation_id=row.rotation_id,
                    scenario_id=row.scenario_id,
                    indicator=row.indicator,
                    ag_year=row.ag_year,
                    carbon_model=row.carbon_model,
                    computation=row.computation,
                    missing=row.missing,
                )
                for row in year_rows
                if row.value is None
            ),
        )
    return counts


# --- D2: paired differences between two rotations ------------------------------


@dataclass(frozen=True)
class PairedDifference:
    """The difference of the two rows of one pair: second minus first (D2).

    It carries the cell of the pair and the unit and direction the two
    rows share, and either a value or a ``missing`` part with reason
    ``MISSING_INPUT`` naming the side or sides that hold no value (C3.3).
    Its range is computed by interval arithmetic, worst case (D92): with
    the first value A in [a_low, a_high] and the second B in
    [b_low, b_high], the range of B − A is [b_low − a_high,
    b_high − a_low], of the kind the two ranges share. If either range is
    missing or the kinds differ, the range of the difference is missing
    with its reason (D92).
    """

    first_rotation: str
    second_rotation: str
    scenario_id: str
    indicator: str
    ag_year: int | None
    carbon_model: str | None
    computation: str | None
    unit: str | None
    direction: str
    value: float | None
    missing: Missing | None
    range: Range | None
    range_missing: Missing | None


def _range_of_a_difference_missing(
    first: ResultsTableRow, second: ResultsTableRow
) -> Missing:
    """Why the range of a difference of two valued rows is missing (D92).

    D92: both ranges must carry the same ``kind`` (C2.3); if either
    range is missing or the kinds differ, the range of the difference is
    missing with its reason. The detail wording is PROPOSED.
    """
    without_a_range = [
        row.rotation_id for row in (first, second) if row.range is None
    ]
    if without_a_range:
        sides = " and ".join(f"'{rotation_id}'" for rotation_id in without_a_range)
        detail = (
            f"the value of the pair's side {sides} of this cell carries no "
            "range, so the range of the difference is missing (D92, C2.2)"
        )
    else:
        detail = (
            "the ranges of the two sides of the pair carry different kinds "
            f"('{first.range.kind}' and '{second.range.kind}'), so the range "
            "of the difference is missing (D92, C2.3)"
        )
    return Missing(reason="NOT_AVAILABLE", detail=detail)


def paired_difference(
    first: ResultsTableRow, second: ResultsTableRow
) -> PairedDifference:
    """The difference of the two rows of one pair, second minus first (D2).

    The two rows must be a pair: the same cell, that is the same
    ``scenario_id``, indicator, time basis, agricultural year, carbon
    model and computation. A difference is never taken across cells, and
    rows whose units differ are refused, with no conversion (C1.1). If
    either value is missing the difference is missing with reason
    ``MISSING_INPUT``, naming the missing side (C3.3). Swapping the two
    rows changes only the sign. The range of a computed difference
    follows D92: interval arithmetic, worst case, over the ranges of the
    two values when they carry the same kind.
    """
    if first.cell() != second.cell():
        raise ValueError(
            "a difference is computed only between the two rows of a pair, "
            f"never across cells: {first.cell()} and {second.cell()}"
        )
    if first.unit != second.unit:
        raise ValueError(
            "the units of the two rows of a pair differ; they are refused, "
            f"with no conversion (C1.1): '{first.unit}' and '{second.unit}'"
        )
    shared = dict(
        first_rotation=first.rotation_id,
        second_rotation=second.rotation_id,
        scenario_id=first.scenario_id,
        indicator=first.indicator,
        ag_year=first.ag_year,
        carbon_model=first.carbon_model,
        computation=first.computation,
        unit=first.unit,
        direction=first.direction,
    )
    missing_sides = [row.rotation_id for row in (first, second) if row.value is None]
    if missing_sides:
        sides = " and ".join(f"'{rotation_id}'" for rotation_id in missing_sides)
        return PairedDifference(
            **shared,
            value=None,
            missing=Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"the value of the pair's side {sides} of this cell is "
                    "missing (C3.3)"
                ),
            ),
            range=None,
            range_missing=None,
        )
    if (
        first.range is not None
        and second.range is not None
        and first.range.kind == second.range.kind
    ):
        # D92: the range of B − A is [b_low − a_high, b_high − a_low].
        difference_range = Range(
            low=second.range.low - first.range.high,
            high=second.range.high - first.range.low,
            kind=first.range.kind,
        )
        range_missing = None
    else:
        difference_range = None
        range_missing = _range_of_a_difference_missing(first, second)
    return PairedDifference(
        **shared,
        value=second.value - first.value,
        missing=None,
        range=difference_range,
        range_missing=range_missing,
    )


def paired_differences(
    table: ResultsTable, first_rotation: str, second_rotation: str
) -> tuple[PairedDifference, ...]:
    """Every difference of one pair of rotations, in cell order (D2).

    Only cells that both rotations hold are paired; the contract gives
    every rotation of the table the same cells, so nothing is left out.
    """
    first_rows = _rows_of(table, first_rotation)
    second_rows = _rows_of(table, second_rotation)
    return tuple(
        paired_difference(first_rows[cell], second_rows[cell])
        for cell in sorted(set(first_rows) & set(second_rows))
    )


def _rows_of(table: ResultsTable, rotation_id: str) -> dict[tuple, ResultsTableRow]:
    """The rows of one rotation of the table, by cell."""
    rows = {row.cell(): row for row in table.rows if row.rotation_id == rotation_id}
    if not rows:
        known = sorted({row.rotation_id for row in table.rows})
        raise ValueError(
            f"rotation '{rotation_id}' is not one of the rotations of the "
            f"table: {known}"
        )
    return rows


# --- D5: dominance between two rotations ---------------------------------------


def _no_worse(candidate: float, other: float, direction: str) -> bool:
    if direction == "lower_is_better":
        return candidate <= other
    return candidate >= other


def _better(candidate: float, other: float, direction: str) -> bool:
    if direction == "lower_is_better":
        return candidate < other
    return candidate > other


def never_preferred_less(
    table: ResultsTable, first_rotation: str, second_rotation: str
) -> bool:
    """Whether ``second_rotation`` is never preferred less than
    ``first_rotation`` (D5).

    True when ``second_rotation`` is no worse than ``first_rotation`` in
    every cell where both rotations hold a value, and better in at least
    one. A cell where either side holds no value counts neither for nor
    against either rotation (D6: a missing value does not enter the
    state). The direction of each row is read from the row and never
    assumed, so one indicator may be ``lower_is_better`` and another
    ``higher_is_better``. "No worse" and "better" are comparisons of the
    two values (D156: "Dominance compares the point values over the cells
    that hold a value on both sides"); the record of ``dominance`` carries
    this result with its label "by point value" (D174) and the coverage
    "k of N" of D91.
    """

    first_rows = _rows_of(table, first_rotation)
    second_rows = _rows_of(table, second_rotation)
    better_somewhere = False
    for cell in sorted(set(first_rows) & set(second_rows)):
        first, second = first_rows[cell], second_rows[cell]
        if first.value is None or second.value is None:
            continue
        if not _no_worse(second.value, first.value, second.direction):
            return False
        if _better(second.value, first.value, second.direction):
            better_somewhere = True
    return better_somewhere


@dataclass(frozen=True)
class Dominance:
    """Dominance of one pair, with its label and its coverage (D5, D156,
    D174, D91).

    ``never_preferred_less`` is the result of the function of that name;
    ``basis`` is always "by point value" (D174: the comparison returns its
    basis); ``cells_compared`` counts the cells of the pair with a value
    on both sides, with or without a range, out of ``cells_of_the_pair``
    (D156: "The coverage "k of N" of D91 counts the cells with a value on
    both sides, with or without a range"). It is descriptive and never
    names a preference: the state of a pair is ``pair_state`` (D156).
    PROPOSED form.
    """

    first_rotation: str
    second_rotation: str
    never_preferred_less: bool
    basis: str
    cells_compared: int
    cells_of_the_pair: int


def dominance(
    table: ResultsTable, first_rotation: str, second_rotation: str
) -> Dominance:
    """Whether ``second_rotation`` is never preferred less than
    ``first_rotation``, labelled "by point value", with the coverage of
    the cells compared (D5, D156, D174, D91)."""
    differences = paired_differences(table, first_rotation, second_rotation)
    return Dominance(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        never_preferred_less=never_preferred_less(
            table, first_rotation, second_rotation
        ),
        basis=BY_POINT_VALUE,
        cells_compared=sum(
            1 for difference in differences if difference.value is not None
        ),
        cells_of_the_pair=len(differences),
    )


# --- D6: missing values in the decision ----------------------------------------


@dataclass(frozen=True)
class IndicatorRanking:
    """What the decision can rank of one indicator (D6).

    When every value of the indicator is missing, the decision gives no
    ranking for it, with the reasons carried through in ``reasons``: no
    rotation is then in ``rotations_with_a_value``, so none is counted
    best or worst. The order of the rotations when values exist is a
    matter of the test plan (blueprint section 5) and is OPEN
    (docs/VALIDATION.md, D7); this record computes none of it.
    """

    indicator: str
    every_value_missing: bool
    rotations_with_a_value: frozenset[str]
    reasons: tuple[tuple[str, Missing], ...]


def indicator_ranking(table: ResultsTable, indicator: str) -> IndicatorRanking:
    """Whether one indicator can be ranked at all, with the reasons carried (D6).

    A missing value is never counted as zero, as within a limit, or as
    best or worst: a rotation enters ``rotations_with_a_value`` only
    through rows that hold a value, and every row without one stays in
    ``reasons`` with its reason. An indicator whose every value is
    missing (an indicator that is ``NOT_AVAILABLE``, C3.2) gives no
    ranking for any rotation.
    """
    rows = [row for row in table.rows if row.indicator == indicator]
    if not rows:
        known = sorted({row.indicator for row in table.rows})
        raise ValueError(f"the table holds no row of '{indicator}': it holds {known}")
    with_a_value = frozenset(
        row.rotation_id for row in rows if row.value is not None
    )
    reasons = tuple(
        (row.rotation_id, row.missing)
        for row in sorted(rows, key=lambda row: (row.rotation_id, row.cell()))
        if row.value is None
    )
    return IndicatorRanking(
        indicator=indicator,
        every_value_missing=not with_a_value,
        rotations_with_a_value=with_a_value,
        reasons=reasons,
    )


# --- D7: the state of a pair (D74 with D88 names) ------------------------------


def _cell_class(difference: PairedDifference) -> str | None:
    """The class of one paired cell by the range of its difference (D93, D98).

    ``None`` when the difference carries no range: such a cell cannot be
    classed (D92). Read in the direction of the indicator (C1.1): the
    whole range strictly on the better side of zero, not touching it, is
    a strict improvement; the whole range on the worse side is a
    deterioration; a range that touches or crosses zero is not separated
    for that cell (D93). These are the three classes of the count by range
    of D99 (D167). Which of them block a robust preference is
    ``_blocks``: a cell that is not separated because its range touches
    zero from the side that is not worse does not (D165).
    """
    if difference.range is None:
        return None
    low, high = difference.range.low, difference.range.high
    if difference.direction == "lower_is_better":
        if high < 0.0:
            return STRICT_IMPROVEMENT
        if low > 0.0:
            return DETERIORATION
    else:
        if low > 0.0:
            return STRICT_IMPROVEMENT
        if high < 0.0:
            return DETERIORATION
    return NOT_SEPARATED


def _non_deteriorating(difference: PairedDifference) -> bool:
    """Whether a computed difference shows non-deterioration (D98, D165).

    D98: "A cell is non-deteriorating only when the whole range of its
    difference lies on the side of zero that is not worse, zero included
    (consistent with D90)." A difference without its range cannot show it
    (D92).
    """
    if difference.range is None:
        return False
    if difference.direction == "lower_is_better":
        return difference.range.high <= 0.0
    return difference.range.low >= 0.0


def _blocks(difference: PairedDifference) -> bool:
    """Whether a computed difference blocks a robust preference (D165).

    D165: "A cell blocks a robust preference when its range is missing
    (D92), crosses zero, touches zero from the worse side (it is not
    non-deteriorating), or lies wholly on the worse side (D93)." That is
    every computed difference that is not non-deteriorating.
    """
    return not _non_deteriorating(difference)


def _enters_the_state(difference: PairedDifference, trend_computation: str) -> bool:
    """Whether a paired cell enters the state (D173).

    D173: the computation of the soil carbon trend that enters the
    separation rule is "the one used to compare rotations: the one the user
    chose, and `end_minus_start` when the user has not chosen" (C1.6); "The
    other two are shown and counted (D99, by computation, D169) and do not
    enter the state."
    """
    return (
        difference.computation is None
        or difference.computation == trend_computation
    )


@dataclass(frozen=True)
class PairState:
    """The state of one pair of rotations (D7): the separation rule of D74
    with the cell classes of D93 as D98 amends them, in the names of D88
    with the name D97 adds.

    ``state`` is ``None`` when no paired difference of the pair holds a
    value: the pair is not evaluated and has no state (D85; D151: "Not
    evaluated" is the label shown for that absence). In one scenario the
    state is the first that applies in the order of D152: "Robust
    preference" when no cell blocks (D165: a range that is missing,
    crosses zero, touches zero from the worse side or lies wholly on the
    worse side) and at least one cell is a strict improvement (D74, D93,
    D98, D153); "Identical" (D85: at least one difference holds a value
    and every difference is zero); "Not separated: uncertainty missing" (a
    computed difference without its range, D92); "Not separated: within
    uncertainty" (a known range that touches or crosses zero, D97);
    otherwise "Not robust across scenarios".

    Over a table of more than one scenario the state is the one D166
    gives: each scenario is read on its own, in the order above, and the
    pair is a robust preference only if it is one in every member;
    otherwise "Not robust across scenarios", even when every member has
    the same state that is not a robust preference; a member without a
    state is not a robust preference (D175). The cells of different
    scenarios are never read as one scenario. ``by_scenario`` carries the
    state of each member, in scenario order, so that it is shown beside
    the state of the set (D152: "The conditions that did not give the
    state are still shown"); it is empty for a table of one scenario. The
    table is the admitted set: which scenarios it holds is the caller's
    (D171).

    The cells of the carbon models are separate cells (D155). Of the soil
    carbon trend only the computation used to compare rotations enters
    the state (D173). A cell where either side holds no value counts
    neither for nor against either rotation (D59, D6) and never blocks:
    D91 sets no minimum coverage. ``identical_rows`` follows D85: at least
    one difference holds a value and every difference of an indicator the
    pair evaluated is zero; a difference of an indicator the pair never
    evaluated (no difference of it holds a value) does not enter the state
    (D6), and a missing difference within an indicator the pair evaluated
    makes the pair never identical. Over several scenarios it is true only
    when it is true in every member.
    """

    first_rotation: str
    second_rotation: str
    state: str | None
    identical_rows: bool
    indicators_not_resolved: tuple[str, ...]
    by_scenario: tuple[tuple[str, str | None], ...] = ()


def _pair_state_in_one_scenario(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    trend_computation: str,
) -> PairState:
    """The state of one pair in a table of one scenario (D152, D165, D173)."""
    differences = [
        difference
        for difference in paired_differences(table, first_rotation, second_rotation)
        if _enters_the_state(difference, trend_computation)
    ]
    computed = [
        difference for difference in differences if difference.value is not None
    ]
    # D85 with D6: a difference of an indicator no difference of which
    # holds a value (water on the supplied table) does not enter the
    # state; a missing difference within an evaluated indicator does, and
    # makes the pair never identical.
    evaluated_indicators = {difference.indicator for difference in computed}
    identical_rows = bool(computed) and all(
        difference.value == 0.0
        for difference in differences
        if difference.indicator in evaluated_indicators
    )
    if not computed:
        # D85: no paired difference holds a value; the pair is not
        # evaluated, with no state (a missing value does not enter the
        # state, D6).
        return PairState(
            first_rotation=first_rotation,
            second_rotation=second_rotation,
            state=None,
            identical_rows=False,
            indicators_not_resolved=(),
        )
    # Brief #304 (unit l2/decision-rule-d165-d176): "`indicators_not_resolved`
    # names only indicators with a blocking cell". Which cell blocks is D165;
    # the naming rule is the brief's, not a decision of #77.
    indicators_not_resolved = tuple(
        sorted(
            {difference.indicator for difference in computed if _blocks(difference)}
        )
    )
    classes = [_cell_class(difference) for difference in computed]
    a_range_missing = any(cell is None for cell in classes)
    a_not_separated = any(cell == NOT_SEPARATED for cell in classes)
    a_strict_improvement = any(cell == STRICT_IMPROVEMENT for cell in classes)
    a_blocking_cell = any(_blocks(difference) for difference in computed)
    if not a_blocking_cell and a_strict_improvement:
        state = ROBUST_PREFERENCE
    elif identical_rows:
        state = IDENTICAL
    elif a_range_missing:
        state = NOT_SEPARATED_UNCERTAINTY_MISSING
    elif a_not_separated:
        state = NOT_SEPARATED_WITHIN_UNCERTAINTY
    else:
        state = NOT_ROBUST_ACROSS_SCENARIOS
    return PairState(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        state=state,
        identical_rows=identical_rows,
        indicators_not_resolved=indicators_not_resolved,
    )


def pair_state(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    *,
    trend_computation: str = DEFAULT_TREND_COMPUTATION,
) -> PairState:
    """The state of one pair of rotations, and the indicators not resolved (D7).

    In a table of one scenario, the state of that scenario (D152, D165).
    In a table of several, the state of the set (D166, D175), with the
    state of each member in ``by_scenario``. ``trend_computation`` is the
    computation of the soil carbon trend used to compare rotations, the
    one the user chose; ``DEFAULT_TREND_COMPUTATION`` when the user has not
    chosen (D173, C1.6).

    An indicator is named in ``indicators_not_resolved`` when the pair
    holds at least one computed difference of that indicator that blocks
    a robust preference (the rule of brief #304; which cell blocks is
    D165); over several scenarios, when it is named
    in at least one member. An indicator with no computed difference for
    the pair is never named: it was not evaluated, and what was not
    evaluated does not enter the state (D6).
    """
    if trend_computation not in TREND_COMPUTATIONS:
        raise ValueError(
            f"'{trend_computation}' is not a computation of the soil carbon "
            f"trend: {list(TREND_COMPUTATIONS)} (C1.6, D173)"
        )
    scenarios = sorted({row.scenario_id for row in table.rows})
    if len(scenarios) == 1:
        return _pair_state_in_one_scenario(
            table, first_rotation, second_rotation, trend_computation
        )
    members = [
        (
            scenario_id,
            _pair_state_in_one_scenario(
                _scenario_table(table, scenario_id),
                first_rotation,
                second_rotation,
                trend_computation,
            ),
        )
        for scenario_id in scenarios
    ]
    if all(member.state is None for _, member in members):
        # D85: no paired difference of the pair holds a value in any
        # scenario; the pair is not evaluated, with no state.
        state = None
    elif all(member.state == ROBUST_PREFERENCE for _, member in members):
        state = ROBUST_PREFERENCE
    else:
        # D166: "otherwise it is "Not robust across scenarios""; D175: a
        # member without a state is not a robust preference.
        state = NOT_ROBUST_ACROSS_SCENARIOS
    return PairState(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        state=state,
        identical_rows=all(member.identical_rows for _, member in members),
        indicators_not_resolved=tuple(
            sorted(
                {
                    indicator
                    for _, member in members
                    for indicator in member.indicators_not_resolved
                }
            )
        ),
        by_scenario=tuple((scenario_id, member.state) for scenario_id, member in members),
    )


# --- D87 with D99: the counts of the cells of a pair, and D91: the coverage ----


@dataclass(frozen=True)
class PointSignCounts:
    """The cells of one pair, scenario and indicator by the sign of the
    point value of each difference (D87, labelled as such by D99).

    ``better`` counts the cells where the second rotation is better and
    ``worse`` where it is worse, read in the direction of each row
    (C1.1); ``equal`` counts the cells whose difference lies within the
    tolerance the designer of the case sets (D87); ``missing_side``
    counts the cells with a missing side (C3.3). This count never
    resolves a pair, and no statistic or p-value is attached (D87).
    """

    better: int
    worse: int
    equal: int
    missing_side: int


@dataclass(frozen=True)
class RangeClassCounts:
    """The same cells, only those whose difference carries a range, by D93
    as D98 amends it (D99).

    A cell without a range appears only in the count of the point signs
    (D99). The two counts are shown apart and never added (D99).
    """

    strict_improvement: int
    deterioration: int
    not_separated: int


@dataclass(frozen=True)
class PairCounts:
    """The two counts of one pair, scenario, indicator, carbon model and
    computation, and the coverage of the cells compared (D87 with D99; D91;
    D169).

    ``carbon_model`` and ``computation`` are those of the cells counted:
    ``None`` for an indicator that names neither, and one count per carbon
    model and computation for the soil carbon trend (D169: "One count per
    pair, scenario, indicator, carbon model and computation, so that the
    cells of AMG and of RothC, which D155 never reads together, are never
    added in one count"). ``cells_compared`` is the number of those cells
    where both rotations hold a value, out of ``cells_of_the_pair``, all
    of them (D91: "k of N"); no minimum coverage is set (D91).
    """

    first_rotation: str
    second_rotation: str
    scenario_id: str
    indicator: str
    carbon_model: str | None
    computation: str | None
    by_point_sign: PointSignCounts
    by_range: RangeClassCounts
    cells_compared: int
    cells_of_the_pair: int


def pair_counts(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    *,
    equal_tolerance: float,
) -> tuple[PairCounts, ...]:
    """The two counts of the cells of one pair of rotations, per scenario,
    indicator, carbon model and computation, and the coverage of the cells
    compared (D87 with D99; D91; D169).

    The two counts are shown apart and never added (D99): by the sign of
    the point value of each difference, and, where the difference has a
    range, by the class of the cell (D93, D98; the three classes of D167).
    A cell without a range appears only in the count of the point signs; a
    cell with a missing side appears only as such. Every computation of
    the soil carbon trend is counted, each apart (D169, D173).
    ``equal_tolerance`` is the absolute tolerance within which a difference
    counts as equal, inclusive (D168): the designer of the case sets it
    (D87); this module sets none.
    """
    if equal_tolerance < 0:
        raise ValueError(
            "equal_tolerance is an absolute tolerance (D87): it cannot be negative"
        )
    differences = paired_differences(table, first_rotation, second_rotation)
    groups: dict[
        tuple[str, str, str | None, str | None], list[PairedDifference]
    ] = {}
    for difference in differences:
        groups.setdefault(
            (
                difference.scenario_id,
                difference.indicator,
                difference.carbon_model,
                difference.computation,
            ),
            [],
        ).append(difference)
    counts = []
    for key in sorted(
        groups, key=lambda item: (item[0], item[1], item[2] or "", item[3] or "")
    ):
        scenario_id, indicator, carbon_model, computation = key
        of_the_group = groups[key]
        better = worse = equal = missing_side = 0
        strict_improvement = deterioration = not_separated = 0
        compared = 0
        for difference in of_the_group:
            if difference.value is None:
                missing_side += 1
                continue
            compared += 1
            if abs(difference.value) <= equal_tolerance:
                equal += 1
            elif (difference.value < 0.0) == (
                difference.direction == "lower_is_better"
            ):
                better += 1
            else:
                worse += 1
            cell = _cell_class(difference)
            if cell == STRICT_IMPROVEMENT:
                strict_improvement += 1
            elif cell == DETERIORATION:
                deterioration += 1
            elif cell == NOT_SEPARATED:
                not_separated += 1
        counts.append(
            PairCounts(
                first_rotation=first_rotation,
                second_rotation=second_rotation,
                scenario_id=scenario_id,
                indicator=indicator,
                carbon_model=carbon_model,
                computation=computation,
                by_point_sign=PointSignCounts(
                    better=better,
                    worse=worse,
                    equal=equal,
                    missing_side=missing_side,
                ),
                by_range=RangeClassCounts(
                    strict_improvement=strict_improvement,
                    deterioration=deterioration,
                    not_separated=not_separated,
                ),
                cells_compared=compared,
                cells_of_the_pair=len(of_the_group),
            )
        )
    return tuple(counts)


# --- D3: the tipping point of an uncertain input (as D103 and D117 read it) ----


@dataclass(frozen=True)
class UncertainInput:
    """One uncertain input of the decision, as the person who designed the
    case maps it onto the table (PROPOSED form; the D3, D4, D10 and D12
    logic it carries is decided).

    ``name`` is what the person calls the input ("u1" in the approved
    case) and ``unit`` the unit its values are read in. ``cell`` is the
    cell of the table the input drives, as the tuple (rotation_id,
    indicator, time_basis, ag_year, carbon_model, computation) of the
    rows whose value, in every scenario, is the input's value ("u1
    (B2021)" drives the soil-loss cell of rotation B of agricultural
    year 2021). ``values`` is the person's ordered mapping of the
    admitted values: each entry pairs one value with the scenario of the
    table that holds this input at that value with every other uncertain
    input at its reference value, given as one ``scenario_id`` or, when
    the phases of the rotations nest inside the value, as the tuple of the
    ``scenario_id`` of those phases. D103: each value of the input is one
    admitted scenario. D117: "The state at a value of the input is the
    state over all the phases at that value, read as D74 reads a set of
    scenarios"; that is the state ``pair_state`` gives over the scenarios
    the value names (D166, D175). A phase is not an uncertain input
    (D117).
    """

    name: str
    unit: str
    cell: tuple[str, str, str, int | None, str | None, str | None]
    values: tuple[tuple[float, str | tuple[str, ...]], ...]


def _scenarios_of(entry: str | tuple[str, ...]) -> tuple[str, ...]:
    """The scenarios one admitted value of an input names: one scenario, or
    the scenarios of the phases nested inside it (D117)."""
    scenario_ids = (entry,) if isinstance(entry, str) else tuple(entry)
    if not scenario_ids:
        raise ValueError(
            "an admitted value of an uncertain input names no scenario (D103, D117)"
        )
    return scenario_ids


def _scenarios_table(
    table: ResultsTable, scenario_ids: tuple[str, ...]
) -> ResultsTable:
    """The rows of the scenarios one admitted value names, as a table."""
    known = {row.scenario_id for row in table.rows}
    absent = [scenario_id for scenario_id in scenario_ids if scenario_id not in known]
    if absent:
        raise ValueError(
            f"scenarios {absent} are not scenarios of the table: {sorted(known)}"
        )
    wanted = set(scenario_ids)
    return ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[row for row in table.rows if row.scenario_id in wanted],
    )


def _drives_the_cell(row: ResultsTableRow, cell: tuple) -> bool:
    """Whether the row belongs to the cell an uncertain input drives."""
    return (
        row.rotation_id,
        row.indicator,
        row.time_basis,
        row.ag_year,
        row.carbon_model,
        row.computation,
    ) == cell


def _scenario_table(table: ResultsTable, scenario_id: str) -> ResultsTable:
    """The rows of one scenario of the table, as a table of their own."""
    rows = [row for row in table.rows if row.scenario_id == scenario_id]
    if not rows:
        known = sorted({row.scenario_id for row in table.rows})
        raise ValueError(
            f"scenario '{scenario_id}' is not one of the scenarios of the "
            f"table: {known}"
        )
    return ResultsTable(case_id=table.case_id, field_id=table.field_id, rows=rows)


def _named_state(state: str | None) -> str:
    """The name a state carries in the output text; a pair without a state
    (D85) is written with the label D151 gives that absence."""
    return NOT_EVALUATED if state is None else state


@dataclass(frozen=True)
class TippingPoint:
    """The tipping point of one uncertain input of the decision (D3, read
    as D103 decides it and D117 allows it): the bracket between the two
    adjacent admitted values where the state of the pair changes between a
    robust preference and not, with the name and unit of the input.

    ``states`` carries each admitted value, in the person's order, with
    the state of the pair at that value: in the one scenario that holds
    it (D103), or over the phases nested inside it (D117, D166). The change D3
    reads is robust preference against not: a change between two states
    that are both not a robust preference (in the approved case, "Not
    separated: within uncertainty" into "Not robust across scenarios" at
    the last value) is no change of the tipping point. ``bracket`` is
    None when no adjacent pair changes, and ``reason`` then says why. No
    value inside the bracket is interpolated; whether and how one may be
    is OPEN for the science reviewers (entry D3).
    """

    first_rotation: str
    second_rotation: str
    input_name: str
    unit: str
    states: tuple[tuple[float, str | None], ...]
    bracket: tuple[float, float] | None
    reason: str | None


def tipping_point(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    uncertain_input: UncertainInput,
    *,
    trend_computation: str = DEFAULT_TREND_COMPUTATION,
) -> TippingPoint:
    """The tipping point of one uncertain input of the decision, or the
    reason there is none (D3, as D103 and D117 read it).

    The state at each admitted value is the state of the pair over the
    scenario of the table that holds the input at that value, or over the
    phases nested inside it (D117), computed by ``pair_state`` (D74 with
    D93, D97, D98, D165 and, over phases, D166 and D175);
    ``trend_computation`` is passed to it (D173). The tipping point is the
    bracket between the two adjacent values, in the person's order, where
    that state changes between a robust preference and not; the approved
    case holds one such bracket, and this function reports the first, in
    the person's order. When no adjacent pair changes, ``bracket`` is
    None and ``reason`` says why: the state is the same at every admitted
    value (the reason of D3), or — a case the approved unit does not
    hold — the state changes only between two states that are both not a
    robust preference.
    """
    states: list[tuple[float, str | None]] = []
    for value, entry in uncertain_input.values:
        at_the_value = _scenarios_table(table, _scenarios_of(entry))
        states.append(
            (
                value,
                pair_state(
                    at_the_value,
                    first_rotation,
                    second_rotation,
                    trend_computation=trend_computation,
                ).state,
            )
        )
    if not states:
        return TippingPoint(
            first_rotation=first_rotation,
            second_rotation=second_rotation,
            input_name=uncertain_input.name,
            unit=uncertain_input.unit,
            states=(),
            bracket=None,
            reason=(
                f"the input '{uncertain_input.name}' holds no admitted value, "
                "so no tipping point is reported"
            ),
        )
    bracket = None
    for (first_value, first_state), (second_value, second_state) in zip(
        states, states[1:]
    ):
        if (first_state == ROBUST_PREFERENCE) != (
            second_state == ROBUST_PREFERENCE
        ):
            bracket = (first_value, second_value)
            break
    if bracket is not None:
        reason = None
    elif len({state for _, state in states}) == 1:
        reason = (
            f"the state of the pair ('{first_rotation}', '{second_rotation}') "
            f"is '{_named_state(states[0][1])}' at every admitted value of "
            f"'{uncertain_input.name}', so no tipping point is reported"
        )
    else:
        reason = (
            f"the pair ('{first_rotation}', '{second_rotation}') is not a "
            f"robust preference at any admitted value of "
            f"'{uncertain_input.name}': its state changes only between two "
            "states that are both not a robust preference, so no tipping "
            "point is reported"
        )
    return TippingPoint(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        input_name=uncertain_input.name,
        unit=uncertain_input.unit,
        states=tuple(states),
        bracket=bracket,
        reason=reason,
    )


# --- D4: the priority of what to measure first ---------------------------------


@dataclass(frozen=True)
class MeasurementPriorityItem:
    """One item of the priority list of D4: qualitative — its rank, what to
    measure (the input's name, the cell of the table it drives and its
    unit) and why.

    ``states`` carries each admitted value of the input, in the person's
    order, with the state of the pair in the scenario that holds the
    input at that value, every other uncertain input at its reference
    value, or over the phases nested inside it (D117): the evidence the
    rank is read from. The values of an input
    change the set's state when those states are not all the same; such
    an input holds rank 1, an input whose values never change it holds
    rank 2. The ordering among the rank-1 inputs is OPEN for the science
    reviewers (entry D4: the measure of how much an input moves the
    decision): they tie and share the rank, and so do the rank-2 inputs.
    No item is monetary (#96, entry D4).
    """

    rank: int
    input_name: str
    unit: str
    cell: tuple[str, str, str, int | None, str | None, str | None]
    why: str
    states: tuple[tuple[float, str | None], ...]


@dataclass(frozen=True)
class MeasurementPriority:
    """The priority list of what to measure first (D4) and the base state it
    is built from.

    ``base_state`` is the state of the pair over the whole admitted
    scenario set, the table as given: the state ``pair_state`` gives over
    a set, each scenario read on its own (D103: "Not robust across
    scenarios" when any member is not a robust preference; D166, D175).
    The list exists
    only from a base that is not a robust preference: a resolved (robust)
    set gives the empty list.
    """

    first_rotation: str
    second_rotation: str
    base_state: str | None
    items: tuple[MeasurementPriorityItem, ...]


def measurement_priority(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    uncertain_inputs: tuple[UncertainInput, ...],
    *,
    trend_computation: str = DEFAULT_TREND_COMPUTATION,
) -> MeasurementPriority:
    """What to measure first, in rank order, and from which base state (D4,
    with the base state of D103).

    The base state is the state of the pair over the whole admitted
    scenario set, the table as given, each scenario read on its own (D103,
    D166, D175); a robust preference there gives the empty list. Otherwise
    every input of ``uncertain_inputs`` is ranked by its admitted values:
    for each value, the state of the pair in the scenario the person's
    mapping names (the scenario that holds the input at that value with
    every other uncertain input at its reference value), or over the
    phases nested inside it (D117). ``trend_computation`` is passed to
    ``pair_state`` (D173). An input whose values change the set's state (those
    states are not all the same) holds rank 1; an input whose values
    never change it holds rank 2. The items of one rank keep the person's
    order, and each carries why it holds its rank.
    """
    base = pair_state(
        table, first_rotation, second_rotation, trend_computation=trend_computation
    )
    if base.state == ROBUST_PREFERENCE:
        return MeasurementPriority(
            first_rotation=first_rotation,
            second_rotation=second_rotation,
            base_state=base.state,
            items=(),
        )
    items: list[MeasurementPriorityItem] = []
    for uncertain_input in uncertain_inputs:
        states: list[tuple[float, str | None]] = []
        for value, entry in uncertain_input.values:
            at_the_value = _scenarios_table(table, _scenarios_of(entry))
            states.append(
                (
                    value,
                    pair_state(
                        at_the_value,
                        first_rotation,
                        second_rotation,
                        trend_computation=trend_computation,
                    ).state,
                )
            )
        changes_the_state = len({state for _, state in states}) > 1
        if not states:
            why = (
                f"the input '{uncertain_input.name}' holds no admitted value, "
                "so its values cannot change the state of the pair"
            )
        elif changes_the_state:
            why = (
                f"the admitted values of '{uncertain_input.name}' change the "
                "state of the pair (every other uncertain input at its "
                "reference value): "
                + ", ".join(
                    f"'{_named_state(state)}' at {value}"
                    for value, state in states
                )
            )
        else:
            why = (
                f"the admitted values of '{uncertain_input.name}' never change "
                "the state of the pair (every other uncertain input at its "
                f"reference value): '{_named_state(states[0][1])}' at every "
                "value"
            )
        items.append(
            MeasurementPriorityItem(
                rank=1 if changes_the_state else 2,
                input_name=uncertain_input.name,
                unit=uncertain_input.unit,
                cell=uncertain_input.cell,
                why=why,
                states=tuple(states),
            )
        )
    # Rank 1 comes before rank 2; the person's order holds inside a rank.
    items.sort(key=lambda item: item.rank)
    return MeasurementPriority(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        base_state=base.state,
        items=tuple(items),
    )


# --- D10: a measured value for one input of the priority list ------------------


class Measurement(BaseModel):
    """A value a person measured for one uncertain input of the priority
    list (D10). PROPOSED form.

    It enters with the label ``OBSERVED`` (C4.1), its unit, and its range
    or its ``range_missing`` (C2); ``value`` is ``None`` for a blank
    entry, which ``recompute_with_measurement`` refuses together with a
    value in a unit other than the one of the input's mapping, and
    neither is ever taken as zero (C3.1). The label OBSERVED travels on
    this record: the rows the recompute writes keep the label the results
    contract fixes for their indicator (C4.6 fixes DERIVED for soil
    loss, and a soil-loss row labelled OBSERVED is not contract-valid),
    so the measurement and its label are held beside the table, not
    rewritten into it.
    """

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False
    )

    input_name: str
    value: float | None
    unit: str
    provenance: Literal["OBSERVED"]
    range: Range | None = None
    range_missing: Missing | None = None


def recompute_with_measurement(
    table: ResultsTable, uncertain_input: UncertainInput, measurement: Measurement
) -> ResultsTable:
    """The table with one uncertain input fixed at its measured value, and
    everything else unchanged (D10).

    A blank value is refused, and so is a value in a unit other than the
    unit of the input's mapping; neither is ever taken as zero (C3.1).
    The measurement carries its range or its ``range_missing``, never
    both and never neither (C2.2). The rows of the cell the input drives
    — in every scenario of the table — are rebuilt with the measured
    value and its range (or its ``range_missing``): the scenario's cells
    the input drives change, nothing else. Each rebuilt row keeps its
    identifier, its unit, its direction, its label and its source, and
    passes the validation of the contract as it is built (a value
    outside its own range is refused there, C2.1; so are two bounds
    equal to the value, C2.2).
    """
    if measurement.input_name != uncertain_input.name:
        raise ValueError(
            f"the measurement names the input '{measurement.input_name}', not "
            f"'{uncertain_input.name}' of this mapping"
        )
    if measurement.value is None:
        raise ValueError(
            f"the measured value of '{uncertain_input.name}' is blank: it is "
            "refused and never taken as zero (C3.1, D10)"
        )
    if measurement.unit != uncertain_input.unit:
        raise ValueError(
            f"the measured value of '{uncertain_input.name}' is in "
            f"'{measurement.unit}', not in '{uncertain_input.unit}' (the unit "
            "of the input's mapping): it is refused, with no conversion, and "
            "never taken as zero (C3.1, D10)"
        )
    if measurement.range is not None and measurement.range_missing is not None:
        raise ValueError(
            "a measurement carries a range or a 'range_missing', never both "
            "(C2.2, D10)"
        )
    if measurement.range is None and measurement.range_missing is None:
        raise ValueError(
            "a measurement without a range says so: give 'range', or "
            "'range_missing' with a reason (C2.2, D10)"
        )
    rows: list[ResultsTableRow] = []
    drives_any_row = False
    for row in table.rows:
        if _drives_the_cell(row, uncertain_input.cell):
            drives_any_row = True
            rows.append(
                ResultsTableRow(
                    rotation_id=row.rotation_id,
                    scenario_id=row.scenario_id,
                    time_basis=row.time_basis,
                    ag_year=row.ag_year,
                    indicator=row.indicator,
                    direction=row.direction,
                    value=measurement.value,
                    unit=row.unit,
                    range=measurement.range,
                    range_missing=measurement.range_missing,
                    missing=None,
                    provenance=row.provenance,
                    source=row.source,
                    assumption=row.assumption,
                )
            )
        else:
            rows.append(row)
    if not drives_any_row:
        driven_cell = ", ".join(str(part) for part in uncertain_input.cell)
        raise ValueError(
            f"the cell of the input '{uncertain_input.name}' ({driven_cell}) "
            "is not a cell of the table"
        )
    return ResultsTable(case_id=table.case_id, field_id=table.field_id, rows=rows)


# --- D12: the tipping point, the measurement and the priority agree ------------


@dataclass(frozen=True)
class MeasurementConsistency:
    """What a measured value on one side of a tipping point gives, and the
    priority list that follows it (D12).

    ``side`` places the measured value against the bracket: below it,
    above it or inside it. A value on one side gives the state of that
    side; what a value inside the bracket tells is not decided (D3
    interpolates no value inside), and the state reported for it is
    still the recomputed one of D10. ``state_after_measurement`` is the
    state of the pair over the admitted set with the input fixed at the
    measured value, and ``priority`` is the priority list (D4) over that
    same recomputed set: it is empty exactly when the state has become a
    robust preference.
    """

    first_rotation: str
    second_rotation: str
    measured_value: float
    side: str
    state_after_measurement: str | None
    priority: MeasurementPriority


def measurement_consistency(
    table: ResultsTable,
    first_rotation: str,
    second_rotation: str,
    uncertain_input: UncertainInput,
    measurement: Measurement,
    bracket: tuple[float, float],
    uncertain_inputs: tuple[UncertainInput, ...],
    *,
    trend_computation: str = DEFAULT_TREND_COMPUTATION,
) -> MeasurementConsistency:
    """The state a measured value gives on its side of the tipping point,
    and the priority list over the recomputed set (D12 over D3, D10 and
    D4).

    The decision is recomputed with the input fixed at the measured value
    (D10, ``recompute_with_measurement``); the state is read over that
    recomputed admitted set, each scenario on its own (D166, D175), and
    the priority list is built from it (D4): a robust preference empties
    the list, any other state keeps it. The bracket is the one
    ``tipping_point`` reported (D3). ``trend_computation`` is passed to
    ``pair_state`` (D173).
    """
    recomputed = recompute_with_measurement(table, uncertain_input, measurement)
    state = pair_state(
        recomputed, first_rotation, second_rotation, trend_computation=trend_computation
    ).state
    priority = measurement_priority(
        recomputed,
        first_rotation,
        second_rotation,
        uncertain_inputs,
        trend_computation=trend_computation,
    )
    below, above = bracket
    if measurement.value < below:
        side = "below the bracket"
    elif measurement.value > above:
        side = "above the bracket"
    else:
        side = "inside the bracket"
    return MeasurementConsistency(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        measured_value=measurement.value,
        side=side,
        state_after_measurement=state,
        priority=priority,
    )
