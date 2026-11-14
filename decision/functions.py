"""Pure decision functions on a results table.

Each public function implements the logic of one D entry of
``docs/VALIDATION.md`` (D1, D2, D5, D6, D7), as the lead developer
decided it on 14 November 2026. What those entries leave OPEN stays OPEN
and is marked where it touches this module.

The functions are pure: no network call, no file access, no clock, no
global state. They read a ``ResultsTable`` of ``contracts/results/`` and
never change it. This module holds no threshold and no expected value of
the science: every limit comes in as an argument, declared by a person
(``DeclaredLimit``). The forms of ``DeclaredLimit`` and of the result
records are PROPOSED (blueprint section 3.7); the logic they carry is
the decided part.
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

# PROPOSED placeholder for the state of a pair of rotations that the data
# cannot separate. The exact state names and wording are OPEN for the
# science reviewers (docs/VALIDATION.md, D7, and #96): tests assert on
# this constant, never on prose.
NOT_RESOLVED = "NOT_RESOLVED"


# --- a limit declared by a person (D1) ----------------------------------------


class DeclaredLimit(BaseModel):
    """A limit a person declares for one indicator (D1).

    It travels like a value: with the provenance label ``DECLARED``
    (C4.1) and its source (C4.2). The preferred side of the limit is not
    a field: it is read from the ``direction`` of the indicator's rows
    (C1.1), so a limit of ``soil_loss`` is an upper limit and a limit of
    ``soil_carbon_trend`` a lower limit. Whether a value equal to the
    limit counts as within is OPEN (the source of a limit says so); the
    counting function takes it as an argument.

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
    """The counts of one rotation and one indicator against a limit (D1).

    ``evaluated`` rows hold a value; of those, ``within`` are on the
    preferred side of the limit and ``outside`` are not. A row without a
    value is in ``not_evaluated``, with its reason: it never counts as
    within or outside, and never as zero. Without a declared limit for
    the indicator nothing is judged: ``limit`` is ``None`` and both
    ``within`` and ``outside`` are zero.
    """

    rotation_id: str
    indicator: str
    limit: DeclaredLimit | None
    evaluated: int
    within: int
    outside: int
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
) -> dict[tuple[str, str], LimitCounts]:
    """Count, per rotation and indicator, the rows that hold a value and
    those within a declared limit (D1).

    A row with a missing value is never counted as within or outside the
    limit: it is reported in ``not_evaluated`` with its reason. An
    indicator without a declared limit is reported as well, with nothing
    judged. ``equal_to_limit_counts_as_within`` is the OPEN question of
    D1 as an argument: whether a value equal to the limit counts as
    within.
    """
    indicators = {row.indicator for row in table.rows}
    unknown = sorted(set(limits) - indicators)
    if unknown:
        raise ValueError(
            "a limit is declared for an indicator the table does not hold: "
            f"{unknown}; the table holds {sorted(indicators)}"
        )
    counts: dict[tuple[str, str], LimitCounts] = {}
    for rotation_id in sorted({row.rotation_id for row in table.rows}):
        for indicator in sorted(indicators):
            rows = [
                row
                for row in table.rows
                if row.rotation_id == rotation_id and row.indicator == indicator
            ]
            with_value = [row for row in rows if row.value is not None]
            limit = limits.get(indicator)
            within = (
                sum(
                    1
                    for row in with_value
                    if _is_on_the_preferred_side(
                        row, limit.limit, equal_to_limit_counts_as_within
                    )
                )
                if limit is not None
                else 0
            )
            counts[(rotation_id, indicator)] = LimitCounts(
                rotation_id=rotation_id,
                indicator=indicator,
                limit=limit,
                evaluated=len(with_value),
                within=within,
                outside=len(with_value) - within if limit is not None else 0,
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
                    for row in rows
                    if row.value is None
                ),
            )
    return counts


# --- D2: paired differences between two rotations ------------------------------


@dataclass(frozen=True)
class PairedDifference:
    """The difference of the two rows of one pair: second minus first (D2).

    It carries the cell of the pair and the unit the two rows share, and
    either a value or a ``missing`` part with reason ``MISSING_INPUT``
    naming the side or sides that hold no value (C3.3). Its range is
    missing with its reason for as long as the method that gives a
    difference its range is OPEN (docs/VALIDATION.md, D2).
    """

    first_rotation: str
    second_rotation: str
    scenario_id: str
    indicator: str
    ag_year: int | None
    carbon_model: str | None
    computation: str | None
    unit: str | None
    value: float | None
    missing: Missing | None
    range: Range | None
    range_missing: Missing | None


def _range_of_a_difference_missing() -> Missing:
    """Why a computed difference carries no range.

    The range of a difference is OPEN (docs/VALIDATION.md, D2): until a
    person supplies its method, every difference is missing its range,
    with its reason (C2.2). The detail is placeholder wording.
    """
    return Missing(
        reason="NOT_AVAILABLE",
        detail=(
            "PLACEHOLDER detail: the method that gives a paired difference its "
            "range is OPEN (docs/VALIDATION.md, D2), so the difference carries "
            "no range"
        ),
    )


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
    rows changes only the sign.
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
    )
    missing_sides = [
        row.rotation_id for row in (first, second) if row.value is None
    ]
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
    return PairedDifference(
        **shared,
        value=second.value - first.value,
        missing=None,
        range=None,
        range_missing=_range_of_a_difference_missing(),
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
    ``higher_is_better``.
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


# --- D7: the state "not resolved" ----------------------------------------------


@dataclass(frozen=True)
class PairState:
    """The state of one pair of rotations (D7).

    ``state`` is ``NOT_RESOLVED`` when this module can say that the data
    do not separate the two rotations: two rotations with identical rows
    are never resolved, and a paired difference whose range is missing is
    never resolved. It is ``None`` in every other case: the rule that
    says when the data separate two rotations lives in the test plan and
    is OPEN (docs/VALIDATION.md, D7), so this module states nothing
    then. ``identical_rows`` says whether every paired difference of the
    two rotations is zero or missing.
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
    holds at least one computed difference of that indicator and either
    every difference of it is zero (identical rows) or one of them
    carries no range. An indicator with no computed difference for the
    pair is never named: it was not evaluated, and what was not
    evaluated does not enter the state (D6).
    """
    differences = paired_differences(table, first_rotation, second_rotation)
    by_indicator: dict[str, list[PairedDifference]] = {}
    for difference in differences:
        by_indicator.setdefault(difference.indicator, []).append(difference)

    not_resolved = []
    for indicator in sorted(by_indicator):
        of_indicator = by_indicator[indicator]
        computed = [item for item in of_indicator if item.value is not None]
        if not computed:
            continue
        identical = of_indicator == computed and all(
            item.value == 0.0 for item in computed
        )
        a_difference_without_a_range = any(item.range is None for item in computed)
        if identical or a_difference_without_a_range:
            not_resolved.append(indicator)

    identical_rows = all(
        difference.value is None or difference.value == 0.0
        for difference in differences
    )
    return PairState(
        first_rotation=first_rotation,
        second_rotation=second_rotation,
        state=NOT_RESOLVED if not_resolved or identical_rows else None,
        identical_rows=identical_rows,
        indicators_not_resolved=tuple(not_resolved),
    )
