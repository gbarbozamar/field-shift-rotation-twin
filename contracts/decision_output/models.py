"""Model of the contract "Decision output" of blueprint section 5.

What the decision layer (``decision/``, sub-lane L2b) gives the decision
screens (lane L3) for one field: the declared limits, the counts by year
against them, the paired differences between rotations, the state and the
measurement priority. Proposed by the interface developer, as producer and
consumer, in issue #96; landed by a lane L0 builder under decision D40 of
issue #77.

Status: PROPOSED (blueprint section 3.7). The field list is described in
``contracts/decision_output/README.md`` and takes effect only when people
approve it. The state names and their wording, the paired-difference method
and whether counts also reference an official tolerance are OPEN for the
science reviewers (issue #96, OPEN 1 to 3).

The shared shapes are imported, never copied: the value of C2.1 (``Value``,
``Missing``, ``Range``) from ``contracts.inputs``; the indicator identifiers,
units, time bases, carbon models and trend computations from
``contracts.results``. The identifiers in comments (C1.1, C3.1, ...) are the
conventions of ``contracts/CONVENTIONS.md`` that a rule enforces.

Models and pure validation only: no value, no threshold, no wording of a
state, no computation, no file access and no network call.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from contracts.inputs.common import ContractModel, Missing, NonEmptyStr, Value
from contracts.results.models import (
    UNIT_SOIL_LOSS_ANNUAL,
    UNITS_OF,
    CarbonModel,
    IndicatorId,
    TimeBasis,
    TrendComputation,
)

# PROPOSED: the label of a limit. A limit is stated by the user, or declared
# by the project for a value from the catalogue (C4.1, C4.5); either way it
# is ``DECLARED``, as ``DeclaredLimit`` of ``decision/functions.py`` has it.
PROVENANCE_OF_A_LIMIT = "DECLARED"


def _repeated(items: list) -> list:
    return sorted(
        (item for item, count in Counter(items).items() if count > 1), key=repr
    )


def _unit_in_the_table(indicator: str) -> str:
    """The one unit an indicator has in ``ResultsTable`` (C1.1, C1.2).

    Soil loss is annual in the results table, so a limit or a difference of
    soil loss is in the annual unit; the other indicators have one unit.
    """
    if indicator == "soil_loss":
        return UNIT_SOIL_LOSS_ANNUAL
    (unit,) = UNITS_OF[indicator]
    return unit


def _check_unit(value: Value, indicator: str, what: str) -> None:
    expected = _unit_in_the_table(indicator)
    if value.unit != expected:
        raise ValueError(
            f"{what} of '{indicator}' is in '{expected}', not in '{value.unit}' (C1.1)"
        )


def _check_cell(
    indicator: str,
    time_basis: str,
    ag_year: int | None,
    carbon_model: str | None,
    computation: str | None,
    what: str,
) -> None:
    """The cell rules of ``ResultsTableRow`` of ``contracts/results/``.

    A count or a difference names the cell of the results table it comes
    from, so it obeys the same rules: soil loss is one value per agricultural
    year (C1.2); soil carbon trend is one value per rotation, for one carbon
    model and one computation (C1.5); only soil carbon trend names a model.
    """
    if time_basis == "ag_year" and ag_year is None:
        raise ValueError(f"{what}: time basis 'ag_year' needs an 'ag_year' (C5.3)")
    if time_basis == "rotation" and ag_year is not None:
        raise ValueError(f"{what}: time basis 'rotation' carries no 'ag_year'")
    names_a_model = carbon_model is not None or computation is not None
    if indicator == "soil_carbon_trend":
        if time_basis != "rotation":
            raise ValueError(
                f"{what}: 'soil_carbon_trend' is one value per rotation (C1.5)"
            )
        if carbon_model is None or computation is None:
            raise ValueError(
                f"{what}: a cell of 'soil_carbon_trend' names its carbon model and its "
                "computation (C1.5)"
            )
    elif names_a_model:
        raise ValueError(
            f"{what}: 'carbon_model' and 'computation' belong to 'soil_carbon_trend' "
            f"only, not to '{indicator}'"
        )
    if indicator == "soil_loss" and time_basis != "ag_year":
        raise ValueError(
            f"{what}: 'soil_loss' is one value per agricultural year (C1.2)"
        )


# --- limits ------------------------------------------------------------------


class LimitItem(ContractModel):
    """The limit of one indicator (D1).

    ``limit`` is one value in the shape of C2.1: a number with its unit, its
    provenance, its source (or the assumption mark) and its range or the
    reason it has none; or missing with its reason, keeping its unit, when no
    limit is declared (D60 of issue #77). Its label is ``DECLARED``. The
    preferred side of the limit is not a field: it is the ``direction`` of the
    indicator (C1.1), as ``decision/functions.py`` reads it.
    """

    indicator: IndicatorId
    limit: Value

    @model_validator(mode="after")
    def _follows_the_conventions(self) -> LimitItem:
        _check_unit(self.limit, self.indicator, "a limit")
        if (
            self.limit.value is not None
            and self.limit.provenance != PROVENANCE_OF_A_LIMIT
        ):
            raise ValueError(
                f"a limit carries the label '{PROVENANCE_OF_A_LIMIT}', not "
                f"'{self.limit.provenance}' (C4.1, C4.5)"
            )
        return self


# --- counts by year (D1) -------------------------------------------------------


class NotEvaluated(ContractModel):
    """One row of the results table that was not evaluated, with its reason (D1).

    It names the rest of the row's cell (the scenario and the indicator are
    those of the count it belongs to) and carries the reason (C3.2).
    """

    time_basis: TimeBasis
    ag_year: int | None = None
    carbon_model: CarbonModel | None = None
    computation: TrendComputation | None = None
    missing: Missing


class CountByYear(ContractModel):
    """The counts of one rotation, one scenario and one indicator (D1).

    ``years_evaluated`` rows held a value and were judged against the limit;
    ``years_within_limits`` of those were on the preferred side. Every other
    row is in ``not_evaluated`` with its reason: it never counts as within or
    outside, and never as zero (C3.1, D6). When the indicator has no declared
    limit, nothing is judged (D60): no row is evaluated and
    ``years_within_limits`` is ``null``.
    """

    rotation_id: NonEmptyStr
    scenario_id: NonEmptyStr
    indicator: IndicatorId
    years_evaluated: int = Field(ge=0)
    years_within_limits: int | None = Field(ge=0)
    not_evaluated: list[NotEvaluated]

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> CountByYear:
        if (
            self.years_within_limits is not None
            and self.years_within_limits > self.years_evaluated
        ):
            raise ValueError(
                "'years_within_limits' is greater than 'years_evaluated' (D1)"
            )
        cells = []
        for item in self.not_evaluated:
            _check_cell(
                self.indicator,
                item.time_basis,
                item.ag_year,
                item.carbon_model,
                item.computation,
                "a row not evaluated",
            )
            cells.append(
                (item.time_basis, item.ag_year, item.carbon_model, item.computation)
            )
        if _repeated(cells):
            raise ValueError(
                f"'not_evaluated' names the same row twice: {_repeated(cells)}"
            )
        return self


# --- paired differences (D2) ---------------------------------------------------


class PairedDifferenceItem(ContractModel):
    """The difference of one pair of rotations in one cell: second minus first (D2).

    ``pair`` holds two ``rotation_id`` values. The cell is that of the
    results table (``scenario_id``, ``indicator``, ``time_basis``,
    ``ag_year``, ``carbon_model``, ``computation``): a difference is never
    taken across cells. ``difference`` is one value in the shape of C2.1; when
    a side of the pair holds no value it is missing with its reason (C3.3).
    ``method`` names the paired-difference method, which is OPEN (issue #96,
    OPEN 2).
    """

    pair: list[NonEmptyStr] = Field(min_length=2, max_length=2)
    scenario_id: NonEmptyStr
    indicator: IndicatorId
    time_basis: TimeBasis
    ag_year: int | None = None
    carbon_model: CarbonModel | None = None
    computation: TrendComputation | None = None
    difference: Value
    method: NonEmptyStr

    @model_validator(mode="after")
    def _is_one_pair_in_one_cell(self) -> PairedDifferenceItem:
        if self.pair[0] == self.pair[1]:
            raise ValueError(
                f"a pair holds two different rotations, not '{self.pair[0]}' twice (D2)"
            )
        _check_cell(
            self.indicator,
            self.time_basis,
            self.ag_year,
            self.carbon_model,
            self.computation,
            "a paired difference",
        )
        _check_unit(self.difference, self.indicator, "a difference")
        return self

    def cell(self) -> tuple:
        return (
            self.scenario_id,
            self.indicator,
            self.time_basis,
            self.ag_year,
            self.carbon_model,
            self.computation,
        )


# --- state (D7) and measurement priority (D4) -------------------------------------


class State(ContractModel):
    """The state of the decision (D7).

    ``value`` is the state; its names and wording are OPEN for the science
    reviewers (issue #96, OPEN 1), so any non-blank text is accepted for now.
    A state the decision layer cannot give is ``null`` with its ``missing``
    part (C3.1). ``indicators_not_resolved`` names the indicators the data do
    not separate (D7). ``reasons`` are texts from deterministic templates.
    """

    value: NonEmptyStr | None
    missing: Missing | None = None
    indicators_not_resolved: list[IndicatorId]
    reasons: list[NonEmptyStr]

    @model_validator(mode="after")
    def _value_or_missing(self) -> State:
        if self.value is None and self.missing is None:
            raise ValueError(
                "a state that is not given carries a 'missing' part with its reason (C3.1)"
            )
        if self.value is not None and self.missing is not None:
            raise ValueError(
                "a state holds a value or a 'missing' part, never both (C3.1)"
            )
        if _repeated(self.indicators_not_resolved):
            raise ValueError(
                "'indicators_not_resolved' names an indicator twice: "
                f"{_repeated(self.indicators_not_resolved)}"
            )
        return self


class MeasureFirstItem(ContractModel):
    """One item of the measurement priority (D4): qualitative, no monetary value.

    Inputs that tie share a rank (D4).
    """

    rank: int = Field(ge=1)
    what: NonEmptyStr
    why: NonEmptyStr


# --- the document --------------------------------------------------------------


class DecisionOutput(ContractModel):
    """Contract "Decision output": what the decision screens show for one field.

    Rotations are named by their ``rotation_id`` and scenarios by their
    ``scenario_id``, as in ``ResultsTable`` of ``contracts/results/``. The
    values themselves stay in the results contracts; this document carries
    limits, counts, differences, the state and the measurement priority.
    """

    contract: Literal["decision_output"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    rotations: list[NonEmptyStr] = Field(min_length=2)
    scenarios: list[NonEmptyStr] = Field(min_length=1)
    limits: list[LimitItem]
    counts_by_year: list[CountByYear]
    paired_differences: list[PairedDifferenceItem]
    state: State
    measure_first: list[MeasureFirstItem]

    @model_validator(mode="after")
    def _identifiers_are_listed_once(self) -> DecisionOutput:
        for name in ("rotations", "scenarios"):
            if _repeated(getattr(self, name)):
                raise ValueError(
                    f"'{name}' lists {_repeated(getattr(self, name))} more than once"
                )
        indicators = [item.indicator for item in self.limits]
        if _repeated(indicators):
            raise ValueError(
                f"'limits' gives more than one limit of {_repeated(indicators)}"
            )
        return self

    @model_validator(mode="after")
    def _counts_cover_every_rotation(self) -> DecisionOutput:
        limits = {item.indicator: item.limit for item in self.limits}
        rotations, scenarios = set(self.rotations), set(self.scenarios)
        keys = []
        for count in self.counts_by_year:
            self._check_listed(count.rotation_id, count.scenario_id, "a count")
            if count.indicator not in limits:
                raise ValueError(
                    f"a count of '{count.indicator}' has no item in 'limits': a limit "
                    "that is not declared is a missing value with its reason (C3.1, D60)"
                )
            if limits[count.indicator].value is None:
                if count.years_within_limits is not None or count.years_evaluated:
                    raise ValueError(
                        f"'{count.indicator}' has no declared limit, so no row is evaluated "
                        "and 'years_within_limits' is null (D60)"
                    )
            elif count.years_within_limits is None:
                raise ValueError(
                    f"'{count.indicator}' has a declared limit, so a count gives "
                    "'years_within_limits' (D1)"
                )
            keys.append((count.rotation_id, count.scenario_id, count.indicator))
        if _repeated(keys):
            raise ValueError(
                f"'counts_by_year' repeats rotation, scenario and indicator {_repeated(keys)}"
            )
        for indicator in sorted({key[2] for key in keys}):
            given = {(key[0], key[1]) for key in keys if key[2] == indicator}
            absent = sorted(
                (rotation, scenario)
                for rotation in rotations
                for scenario in scenarios
                if (rotation, scenario) not in given
            )
            if absent:
                raise ValueError(
                    f"'counts_by_year' of '{indicator}' leaves out rotation and scenario "
                    f"{absent}: every rotation of every scenario is counted"
                )
        return self

    @model_validator(mode="after")
    def _differences_name_listed_rotations(self) -> DecisionOutput:
        keys = []
        for item in self.paired_differences:
            for rotation_id in item.pair:
                self._check_listed(rotation_id, item.scenario_id, "a paired difference")
            keys.append((tuple(item.pair), item.cell()))
        if _repeated(keys):
            raise ValueError(
                "'paired_differences' gives the same pair and cell twice: "
                f"{_repeated(keys)}"
            )
        return self

    @model_validator(mode="after")
    def _priorities_are_in_rank_order(self) -> DecisionOutput:
        ranks = [item.rank for item in self.measure_first]
        if ranks != sorted(ranks):
            raise ValueError("'measure_first' is not in rank order (D4)")
        return self

    def _check_listed(self, rotation_id: str, scenario_id: str, what: str) -> None:
        if rotation_id not in self.rotations:
            raise ValueError(
                f"{what} names rotation '{rotation_id}', which is not in 'rotations'"
            )
        if scenario_id not in self.scenarios:
            raise ValueError(
                f"{what} names scenario '{scenario_id}', which is not in 'scenarios'"
            )
