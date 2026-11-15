"""Model of the contract "Decision output" of blueprint section 5.

What the decision layer (``decision/``, sub-lane L2b) gives the decision
screens (lane L3) for one field: the declared limits, the counts by year
against them, the paired differences between rotations, the state and the
measurement priority. Proposed by the interface developer, as producer and
consumer, in issue #96; landed by a lane L0 builder under decision D40 of
issue #77.

Status: PROPOSED (blueprint section 3.7). The field list is described in
``contracts/decision_output/README.md`` and takes effect only when people
approve it. The fields that decisions D85 to D99 of issue #77 ask for (the
state of a pair and its reason, the counts of a pair's cells, the coverage,
the carbon model and computation of a count, counts of years over
agricultural-year rows only, and the range across scenarios) are PROPOSED
by a lane L0 builder; where two of those decisions do not fit together as
written, ``README.md`` lists the clash under OPEN and the model takes no
side beyond what the brief of issue #193 states.

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
from typing import Literal, get_args

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


def _check_declared(value: Value, indicator: str, what: str) -> None:
    """A limit or a tolerance: in the unit of the table, ``DECLARED`` when it holds a number."""
    _check_unit(value, indicator, what)
    if value.value is not None and value.provenance != PROVENANCE_OF_A_LIMIT:
        raise ValueError(
            f"{what} carries the label '{PROVENANCE_OF_A_LIMIT}', not "
            f"'{value.provenance}' (C4.1, C4.5)"
        )


def _check_pair(pair: list[str], what: str) -> None:
    if pair[0] == pair[1]:
        raise ValueError(
            f"{what}: a pair holds two different rotations, not '{pair[0]}' twice (D2)"
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
        _check_declared(self.limit, self.indicator, "a limit")
        return self


class EqualToleranceItem(ContractModel):
    """The tolerance within which a paired difference counts as "equal" (D87).

    PROPOSED. D87: '"Equal" uses the tolerance set by the designer of the
    case'. One value in the shape of C2.1, in the unit of the indicator in the
    results table, labelled ``DECLARED`` when it holds a number; or missing
    with its reason, keeping its unit, when the designer of the case set none.
    """

    indicator: IndicatorId
    tolerance: Value

    @model_validator(mode="after")
    def _follows_the_conventions(self) -> EqualToleranceItem:
        _check_declared(self.tolerance, self.indicator, "a tolerance")
        return self


# --- counts by year (D1) -------------------------------------------------------


class NotEvaluated(ContractModel):
    """One row of the results table that was not evaluated, with its reason (D1).

    It names the rest of the row's cell (the scenario and the indicator are
    those of the count it belongs to) and carries the reason (C3.2). Years
    are counted only over rows whose ``time_basis`` is ``ag_year`` (D95), so
    a row not evaluated is one of those.
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

    D94: one count per rotation, scenario, indicator, carbon model and
    computation; nothing is counted across scenarios or across carbon models.
    ``carbon_model`` and ``computation`` follow the cell rules (only soil
    carbon trend names them). D95: years are counted only over rows whose
    ``time_basis`` is ``ag_year``; an indicator on another time basis has no
    count of years. Soil carbon trend is one value per rotation (C1.5), so it
    has no count, and the two fields of D94 stay empty (README.md, OPEN, K11).
    """

    rotation_id: NonEmptyStr
    scenario_id: NonEmptyStr
    indicator: IndicatorId
    carbon_model: CarbonModel | None = None
    computation: TrendComputation | None = None
    years_evaluated: int = Field(ge=0)
    years_within_limits: int | None = Field(ge=0)
    not_evaluated: list[NotEvaluated]

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> CountByYear:
        if self.indicator == "soil_carbon_trend":
            raise ValueError(
                "'soil_carbon_trend' is one value per rotation (C1.5), and an indicator "
                "whose time basis is not 'ag_year' has no count of years (D95)"
            )
        if self.carbon_model is not None or self.computation is not None:
            raise ValueError(
                "a count: 'carbon_model' and 'computation' belong to 'soil_carbon_trend' "
                f"only, not to '{self.indicator}'"
            )
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
            if item.time_basis != "ag_year":
                raise ValueError(
                    "a row not evaluated: years are counted only over rows whose "
                    f"'time_basis' is 'ag_year', not '{item.time_basis}' (D95)"
                )
            cells.append(
                (item.time_basis, item.ag_year, item.carbon_model, item.computation)
            )
        if _repeated(cells):
            raise ValueError(
                f"'not_evaluated' names the same row twice: {_repeated(cells)}"
            )
        return self

    def key(self) -> tuple:
        """D94: rotation, scenario, indicator, carbon model and computation."""
        return (
            self.rotation_id,
            self.scenario_id,
            self.indicator,
            self.carbon_model,
            self.computation,
        )


# --- the range across scenarios (D96) ---------------------------------------------


class RangeAcrossScenarios(ContractModel):
    """The summary of the counts over many scenarios (D96). PROPOSED.

    D96: "Only the range, from minimum to maximum, of the years within the
    limit across the admitted scenarios, naming the scenario of the minimum.
    No mean, share or percentage of scenarios." One item per rotation,
    indicator, carbon model and computation (the key of D94 without the
    scenario). ``minimum``, ``maximum`` and ``scenario_of_the_minimum`` are
    given together, or all three are ``null`` with the ``missing`` part
    (C3.1), for example when the limit is not declared and no year is judged
    (D60). Which scenarios are admitted (D74) is not a field yet (README.md,
    OPEN).
    """

    rotation_id: NonEmptyStr
    indicator: IndicatorId
    carbon_model: CarbonModel | None = None
    computation: TrendComputation | None = None
    minimum: int | None = Field(ge=0)
    maximum: int | None = Field(ge=0)
    scenario_of_the_minimum: NonEmptyStr | None
    missing: Missing | None = None

    @model_validator(mode="after")
    def _range_or_missing(self) -> RangeAcrossScenarios:
        parts = (self.minimum, self.maximum, self.scenario_of_the_minimum)
        given = [part is not None for part in parts]
        if any(given) and not all(given):
            raise ValueError(
                "a range across scenarios gives 'minimum', 'maximum' and "
                "'scenario_of_the_minimum' together, or none of them (D96)"
            )
        if all(given) and self.missing is not None:
            raise ValueError(
                "a range across scenarios holds a range or a 'missing' part, never both (C3.1)"
            )
        if not any(given) and self.missing is None:
            raise ValueError(
                "a range across scenarios that is not given carries a 'missing' part "
                "with its reason (C3.1)"
            )
        if all(given) and self.minimum > self.maximum:
            raise ValueError(
                "a range across scenarios: 'minimum' is greater than 'maximum' (D96)"
            )
        return self

    def key(self) -> tuple:
        return (self.rotation_id, self.indicator, self.carbon_model, self.computation)


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
        _check_pair(self.pair, "a paired difference")
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


# --- counts of a pair's cells (D87, D99) -----------------------------------------


class CountByDifferenceRange(ContractModel):
    """The cells whose paired difference has a range, classed by that range (D99).

    D99: "Where the difference has a range: strict improvement, deterioration
    and not separated, by D93 and D98." Read in the direction of the
    indicator (C1.1), the difference being the second rotation minus the
    first. A cell whose difference has no range is not counted here.
    """

    strict_improvement: int = Field(ge=0)
    deterioration: int = Field(ge=0)
    not_separated: int = Field(ge=0)

    def cells(self) -> int:
        return self.strict_improvement + self.deterioration + self.not_separated


class CountBySignOfPointValue(ContractModel):
    """Every cell of the pair, classed by the sign of the point value (D87, D99).

    D87: the count of paired cells where the second rotation is better, worse
    or equal, and of cells with a missing side, read in the direction of each
    row (C1.1); "equal" uses the tolerance set by the designer of the case.
    D99: labelled as a count by the sign of the point value; "A cell without a
    range appears only in the second count."
    """

    better: int = Field(ge=0)
    worse: int = Field(ge=0)
    equal: int = Field(ge=0)
    missing_side: int = Field(ge=0)

    def cells_with_a_value(self) -> int:
        return self.better + self.worse + self.equal


class PairCellCount(ContractModel):
    """The counts of one pair of rotations, in one scenario, for one indicator (D87).

    PROPOSED. Two counts, shown apart and never added (D99):
    ``by_difference_range`` and ``by_sign_of_point_value``. Neither resolves
    the pair, and no statistic or p-value is attached (D87). The count by the
    sign of the point value needs the tolerance of "equal" (D87); without it,
    it is ``null`` with ``by_sign_of_point_value_missing`` (C3.1).
    """

    pair: list[NonEmptyStr] = Field(min_length=2, max_length=2)
    scenario_id: NonEmptyStr
    indicator: IndicatorId
    by_difference_range: CountByDifferenceRange
    by_sign_of_point_value: CountBySignOfPointValue | None
    by_sign_of_point_value_missing: Missing | None = None

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> PairCellCount:
        _check_pair(self.pair, "a count of a pair's cells")
        given = self.by_sign_of_point_value is not None
        if given and self.by_sign_of_point_value_missing is not None:
            raise ValueError(
                "'by_sign_of_point_value' holds counts or a 'missing' part, never both (C3.1)"
            )
        if not given and self.by_sign_of_point_value_missing is None:
            raise ValueError(
                "'by_sign_of_point_value' that is not given carries "
                "'by_sign_of_point_value_missing' with its reason (C3.1)"
            )
        if given and (
            self.by_difference_range.cells()
            > self.by_sign_of_point_value.cells_with_a_value()
        ):
            raise ValueError(
                "'by_difference_range' counts more cells than 'by_sign_of_point_value' "
                "counts with a value on both sides: every cell is in the count by the "
                "sign of the point value (D99)"
            )
        return self

    def key(self) -> tuple:
        return (tuple(self.pair), self.scenario_id, self.indicator)


# --- state of a pair (D85, D86, D88, D91, D97) --------------------------------------

# PROPOSED: the state names of D88, with the name D97 adds. "Not evaluated" is
# not among them: by D85 a pair whose differences all lack a value has no
# state. D151 of issue #77 decides that "Not evaluated" is the absence of a
# state, not a state name (README.md, K1, resolved).
StateName = Literal[
    "Identical",
    "Not separated: uncertainty missing",
    "Not separated: within uncertainty",
    "Not robust across scenarios",
    "Robust preference",
]
STATE_NAMES: tuple[str, ...] = get_args(StateName)
ROBUST_PREFERENCE = "Robust preference"

# PROPOSED: the reasons of D86, as D86 writes them, and the state each goes
# with ("The names are those of D88"). D86 writes no reason for the state
# "Not separated: within uncertainty" that D97 adds (README.md, OPEN, K3).
ReasonOfAState = Literal[
    "identical rows",
    "a difference without its range",
    "not robust across the admitted scenarios",
]
REASON_OF_A_STATE: dict[str, str] = {
    "Identical": "identical rows",
    "Not separated: uncertainty missing": "a difference without its range",
    "Not robust across scenarios": "not robust across the admitted scenarios",
}


class Coverage(ContractModel):
    """The coverage of a pair: "k of N" (D91). PROPOSED.

    ``cells_compared`` are the cells of the pair with a value on both sides,
    over which dominance is judged (D59); ``cells_of_the_pair`` are all the
    cells of the pair. No minimum coverage is set (D91).
    """

    cells_compared: int = Field(ge=0)
    cells_of_the_pair: int = Field(ge=0)

    @model_validator(mode="after")
    def _k_of_n(self) -> Coverage:
        if self.cells_compared > self.cells_of_the_pair:
            raise ValueError(
                "'cells_compared' is greater than 'cells_of_the_pair' (D91)"
            )
        return self


class PairState(ContractModel):
    """The state of one pair of rotations across the scenarios (D85, D86, D88, D97).

    PROPOSED. ``value`` is one of the state names of D88 and D97. A pair in
    which no paired difference holds a value is "not evaluated", with no
    state (D85): ``value`` is ``null`` with its ``missing`` part (C3.1). A
    state that is not a robust preference carries its reason (D86) in
    ``reason``, or ``reason_missing`` when no decision writes a reason for it
    (README.md, OPEN, K3). ``preferred_rotation_id`` names the rotation a
    robust preference prefers (README.md, OPEN). ``coverage`` is "k of N"
    (D91).
    """

    pair: list[NonEmptyStr] = Field(min_length=2, max_length=2)
    value: StateName | None
    missing: Missing | None = None
    reason: ReasonOfAState | None = None
    reason_missing: Missing | None = None
    preferred_rotation_id: NonEmptyStr | None = None
    coverage: Coverage

    @model_validator(mode="after")
    def _state_and_reason(self) -> PairState:
        _check_pair(self.pair, "a state of a pair")
        has_reason = self.reason is not None or self.reason_missing is not None
        if self.reason is not None and self.reason_missing is not None:
            raise ValueError(
                "a state of a pair holds a reason or 'reason_missing', never both (C3.1)"
            )
        if self.value is None:
            if self.missing is None:
                raise ValueError(
                    "a pair that is not evaluated has no state and carries a 'missing' "
                    "part with its reason (D85, C3.1)"
                )
            if has_reason or self.preferred_rotation_id is not None:
                raise ValueError(
                    "a pair that is not evaluated has no state, so no reason and no "
                    "preferred rotation (D85)"
                )
            return self
        if self.missing is not None:
            raise ValueError(
                "a state of a pair holds a value or a 'missing' part, never both (C3.1)"
            )
        if self.coverage.cells_compared == 0:
            raise ValueError(
                "a pair in which no paired difference holds a value is not evaluated, "
                "with no state (D85)"
            )
        if self.value == ROBUST_PREFERENCE:
            if has_reason:
                raise ValueError(
                    "a robust preference carries no reason: D86 gives a reason to a "
                    "state that is not a robust preference"
                )
            if self.preferred_rotation_id not in self.pair:
                raise ValueError(
                    "a robust preference names its 'preferred_rotation_id', one of the "
                    "two rotations of the pair (D74)"
                )
            return self
        if self.preferred_rotation_id is not None:
            raise ValueError(
                "'preferred_rotation_id' belongs to a robust preference only, not to "
                f"'{self.value}'"
            )
        if not has_reason:
            raise ValueError(
                f"the state '{self.value}' is not a robust preference, so it carries its "
                "reason, or 'reason_missing' (D86)"
            )
        expected = REASON_OF_A_STATE.get(self.value)
        if self.reason is not None and self.reason != expected:
            raise ValueError(
                f"the state '{self.value}' does not carry the reason '{self.reason}' "
                "(D86: the names are those of D88)"
            )
        return self


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
    range_across_scenarios: list[RangeAcrossScenarios]
    paired_differences: list[PairedDifferenceItem]
    equal_tolerances: list[EqualToleranceItem]
    pair_cell_counts: list[PairCellCount]
    pair_states: list[PairState]
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
        indicators = [item.indicator for item in self.equal_tolerances]
        if _repeated(indicators):
            raise ValueError(
                "'equal_tolerances' gives more than one tolerance of "
                f"{_repeated(indicators)}"
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
            keys.append(count.key())
        if _repeated(keys):
            raise ValueError(
                "'counts_by_year' repeats rotation, scenario, indicator, carbon model "
                f"and computation {_repeated(keys)} (D94)"
            )
        for what in sorted({key[2:] for key in keys}, key=repr):
            given = {(key[0], key[1]) for key in keys if key[2:] == what}
            absent = sorted(
                (rotation, scenario)
                for rotation in rotations
                for scenario in scenarios
                if (rotation, scenario) not in given
            )
            if absent:
                raise ValueError(
                    f"'counts_by_year' of '{what[0]}' leaves out rotation and scenario "
                    f"{absent}: every rotation of every scenario is counted"
                )
        return self

    @model_validator(mode="after")
    def _ranges_summarise_the_counts(self) -> DecisionOutput:
        counts = {count.key(): count for count in self.counts_by_year}
        summarised = {(key[0], *key[2:]) for key in counts}
        keys = []
        for item in self.range_across_scenarios:
            if item.rotation_id not in self.rotations:
                raise ValueError(
                    f"a range across scenarios names rotation '{item.rotation_id}', "
                    "which is not in 'rotations'"
                )
            if item.key() not in summarised:
                raise ValueError(
                    f"a range across scenarios of {item.key()} summarises no count in "
                    "'counts_by_year' (D96)"
                )
            scenario = item.scenario_of_the_minimum
            if scenario is not None:
                if scenario not in self.scenarios:
                    raise ValueError(
                        f"a range across scenarios names scenario '{scenario}', which is "
                        "not in 'scenarios'"
                    )
                count = counts.get((item.rotation_id, scenario, *item.key()[1:]))
                if count is None or count.years_within_limits != item.minimum:
                    raise ValueError(
                        f"a range across scenarios names '{scenario}' as the scenario of "
                        "the minimum, and its count of years within the limit is not "
                        "the minimum (D96)"
                    )
            keys.append(item.key())
        if _repeated(keys):
            raise ValueError(f"'range_across_scenarios' repeats {_repeated(keys)}")
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
    def _pair_counts_have_their_tolerance(self) -> DecisionOutput:
        tolerances = {item.indicator: item.tolerance for item in self.equal_tolerances}
        keys = []
        for item in self.pair_cell_counts:
            for rotation_id in item.pair:
                self._check_listed(
                    rotation_id, item.scenario_id, "a count of a pair's cells"
                )
            if item.indicator not in tolerances:
                raise ValueError(
                    f"a count of a pair's cells of '{item.indicator}' has no item in "
                    "'equal_tolerances': 'equal' uses the tolerance set by the designer "
                    "of the case, and a tolerance not set is a missing value (D87, C3.1)"
                )
            if (
                tolerances[item.indicator].value is None
                and item.by_sign_of_point_value is not None
            ):
                raise ValueError(
                    f"'{item.indicator}' has no tolerance of 'equal', so the count by "
                    "the sign of the point value is not given (D87, C3.1)"
                )
            keys.append(item.key())
        if _repeated(keys):
            raise ValueError(
                "'pair_cell_counts' repeats pair, scenario and indicator "
                f"{_repeated(keys)}"
            )
        return self

    @model_validator(mode="after")
    def _pair_states_name_listed_rotations(self) -> DecisionOutput:
        keys = []
        for item in self.pair_states:
            for rotation_id in item.pair:
                if rotation_id not in self.rotations:
                    raise ValueError(
                        f"a state of a pair names rotation '{rotation_id}', which is not "
                        "in 'rotations'"
                    )
            keys.append(tuple(sorted(item.pair)))
        if _repeated(keys):
            raise ValueError(
                f"'pair_states' gives more than one state of the pair {_repeated(keys)}"
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
