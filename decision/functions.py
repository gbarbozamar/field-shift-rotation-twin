"""Pure decision functions on a results table.

Each public function implements the logic of one D entry of
``docs/VALIDATION.md`` (D1, D2, D5, D6, D7), as the lead developer
decided it on 14 November 2026 together with the decisions D74 and D85
to D99 of issue #77 that those entries record. What those entries leave
OPEN stays OPEN and is marked where it touches this module.

The functions are pure: no network call, no file access, no clock, no
global state. They read a ``ResultsTable`` of ``contracts/results/`` and
never change it. This module holds no threshold and no expected value of
the science: every limit comes in as an argument, declared by a person
(``DeclaredLimit``), and the only number the decided logic names, zero
as the point a difference is read against (D74, D93, D98), appears as
that constant of the decisions. The forms of ``DeclaredLimit`` and of
the result records are PROPOSED (blueprint section 3.7); the logic they
carry is the decided part.

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
# evaluated", with no state), so ``PairState.state`` is ``None`` for it;
# whether it is a state or the absence of one is OPEN as K1 of entry D7.
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
# separated" for that cell. D98: such a cell blocks a robust preference.
NOT_SEPARATED = "not separated"
STRICT_IMPROVEMENT = "strict improvement"
DETERIORATION = "deterioration"


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
    ``higher_is_better``. Whether "no worse" and "better" here are read
    by the range of the difference (D93, D98) or stay comparisons of the
    two values is OPEN as K7 of entry D5; this function keeps the
    comparisons of the two values, and the coverage of the cells it
    judges is carried by ``pair_counts`` (D91).
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
    for that cell and blocks a robust preference. A cell whose range
    lies on the side of zero that is not worse, zero included (D98,
    non-deteriorating), without touching zero is exactly a strict
    improvement.
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


@dataclass(frozen=True)
class PairState:
    """The state of one pair of rotations (D7): the separation rule of D74
    with the cell classes of D93 as D98 amends them, in the names of D88
    with the name D97 adds.

    ``state`` is ``None`` when no paired difference of the pair holds a
    value: the pair is not evaluated and has no state (D85; whether that
    absence is itself a state is OPEN as K1 of entry D7). Otherwise the
    state is "Robust preference" when no cell of the pair blocks or
    deteriorates and at least one cell is a strict improvement (D74 with
    D93 and D98), or the first of these reasons that applies, in the
    order the approved unit brief (#202) lists them: "Identical" (D85:
    at least one difference holds a value and every difference is zero);
    "Not separated: uncertainty missing" (a computed difference without
    its range, D92); "Not separated: within uncertainty" (a known range
    that touches or crosses zero, D97); "Not robust across scenarios"
    (D74 asks for paired non-deterioration in every admitted scenario:
    this is the state of a pair that is not a robust preference and none
    of the other reasons applies). Which state comes first when several
    conditions hold is OPEN as K2 of entry D7, which scenarios are
    admitted is OPEN there as well, and so is whether the rule is applied
    per carbon model (K6); this function reads the scenarios and the
    cells of the table it is given, cell by cell.

    A cell where either side holds no value counts neither for nor
    against either rotation (D59, D6) and never blocks: D91 sets no
    minimum coverage. ``identical_rows`` follows D85: at least one
    difference holds a value and every difference of an indicator the
    pair evaluated is zero; a difference of an indicator the pair never
    evaluated (no difference of it holds a value) does not enter the
    state (D6), and a missing difference within an indicator the pair
    evaluated makes the pair never identical.
    """

    first_rotation: str
    second_rotation: str
    state: str | None
    identical_rows: bool
    indicators_not_resolved: tuple[str, ...]


def pair_state(
    table: ResultsTable, first_rotation: str, second_rotation: str
) -> PairState:
    """The state of one pair of rotations, and the indicators not resolved (D7).

    An indicator is named in ``indicators_not_resolved`` when the pair
    holds at least one computed difference of that indicator and one of
    its cells is not a strict improvement. An indicator with no computed
    difference for the pair is never named: it was not evaluated, and
    what was not evaluated does not enter the state (D6).
    """
    differences = paired_differences(table, first_rotation, second_rotation)
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
    by_indicator: dict[str, list[PairedDifference]] = {}
    for difference in computed:
        by_indicator.setdefault(difference.indicator, []).append(difference)
    indicators_not_resolved = tuple(
        indicator
        for indicator in sorted(by_indicator)
        if any(
            _cell_class(difference) != STRICT_IMPROVEMENT
            for difference in by_indicator[indicator]
        )
    )
    classes = [_cell_class(difference) for difference in computed]
    a_range_missing = any(cell is None for cell in classes)
    a_not_separated = any(cell == NOT_SEPARATED for cell in classes)
    a_deterioration = any(cell == DETERIORATION for cell in classes)
    a_strict_improvement = any(cell == STRICT_IMPROVEMENT for cell in classes)
    if not (a_range_missing or a_not_separated or a_deterioration) and (
        a_strict_improvement
    ):
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
    """The two counts of one pair, scenario and indicator, and the coverage
    of the cells compared (D87 with D99; D91).

    ``cells_compared`` is the number of the cells of the pair where both
    rotations hold a value, out of ``cells_of_the_pair``, all the cells
    of the pair for that scenario and indicator (D91: "k of N"); no
    minimum coverage is set (D91). Whether these counts are also keyed
    by carbon model and computation is OPEN (entry D2); they are keyed
    by pair, scenario and indicator, as D87 keys them.
    """

    first_rotation: str
    second_rotation: str
    scenario_id: str
    indicator: str
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
    """The two counts of the cells of one pair of rotations, per scenario and
    indicator, and the coverage of the cells compared (D87 with D99; D91).

    The two counts are shown apart and never added (D99): by the sign of
    the point value of each difference, and, where the difference has a
    range, by the class of the cell (D93, D98). A cell without a range
    appears only in the count of the point signs; a cell with a missing
    side appears only as such. ``equal_tolerance`` is the absolute
    tolerance within which a difference counts as equal: the designer of
    the case sets it (D87); this module sets none.
    """
    if equal_tolerance < 0:
        raise ValueError(
            "equal_tolerance is an absolute tolerance (D87): it cannot be negative"
        )
    differences = paired_differences(table, first_rotation, second_rotation)
    groups: dict[tuple[str, str], list[PairedDifference]] = {}
    for difference in differences:
        groups.setdefault(
            (difference.scenario_id, difference.indicator), []
        ).append(difference)
    counts = []
    for scenario_id, indicator in sorted(groups):
        of_the_group = groups[(scenario_id, indicator)]
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
