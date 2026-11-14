"""Models of the two results contracts of blueprint section 5.

- ``ResultsPerRotation``: what the engines report for one rotation.
- ``ResultsTable``: the values of several rotations side by side, for the
  decision layer.

Status: PROPOSED (blueprint section 3.7). The field lists are described in
contracts/results/README.md and take effect only when people approve them.

The models follow contracts/CONVENTIONS.md; the identifiers in comments
(C1.1, C3.1, ...) are the conventions they enforce. This module holds
models and pure validation only: no value, no threshold, no computation,
no file access and no network call.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal, Self, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    model_validator,
)

# --- closed vocabularies of the conventions sheet ----------------------------

IndicatorId = Literal[
    "soil_loss", "water_deficit_exposure", "soil_carbon_trend"
]  # C1.1
Direction = Literal["lower_is_better", "higher_is_better"]  # C1.1
ProvenanceLabel = Literal["DECLARED", "OBSERVED", "DERIVED", "SIMULATED"]  # C4.1
ReasonCode = Literal[  # C3.2
    "NOT_DECLARED",
    "SOURCE_UNAVAILABLE",
    "NO_COVERAGE",
    "MISSING_INPUT",
    "NOT_COMPUTABLE",
    "CONTROL_FAILED",
    "NOT_AVAILABLE",
    "NOT_APPLICABLE",
]

UNIT_SOIL_LOSS_ANNUAL = "t ha-1 yr-1"  # C1.2
UNIT_SOIL_LOSS_MONTHLY = "t ha-1 month-1"  # C1.2
UNIT_WATER_DEFICIT_EXPOSURE = "dimensionless"  # C1.3
UNIT_SOIL_CARBON_TREND = "t C ha-1 yr-1"  # C1.5

UNITS_OF: dict[str, tuple[str, ...]] = {
    "soil_loss": (UNIT_SOIL_LOSS_ANNUAL, UNIT_SOIL_LOSS_MONTHLY),
    "water_deficit_exposure": (UNIT_WATER_DEFICIT_EXPOSURE,),
    "soil_carbon_trend": (UNIT_SOIL_CARBON_TREND,),
}
DIRECTION_OF: dict[str, str] = {
    "soil_loss": "lower_is_better",  # C1.2
    "water_deficit_exposure": "higher_is_better",  # C1.3
    "soil_carbon_trend": "higher_is_better",  # C1.5
}
PROVENANCE_OF_SOIL_LOSS = "DERIVED"  # C4.6

# --- vocabularies proposed by this unit --------------------------------------

# PROPOSED identifiers of the three computations of C1.6, in its order: end
# minus start over the horizon; slope of a fitted line; mean change over
# whole rotation cycles. The sheet names the computations but not their
# identifiers.
TrendComputation = Literal["end_minus_start", "fitted_slope", "mean_over_cycles"]
TREND_COMPUTATIONS: tuple[str, ...] = get_args(TrendComputation)
DEFAULT_TREND_COMPUTATION = "end_minus_start"  # C1.6

# PROPOSED: what a value that is not monthly refers to. ``rotation`` is one
# value for the rotation over the whole simulation horizon.
TimeBasis = Literal["ag_year", "rotation"]


def _not_blank(text: str) -> str:
    if text.strip() == "":
        raise ValueError("must not be empty or blank")
    return text


Text = Annotated[str, AfterValidator(_not_blank)]


class _Contract(BaseModel):
    """Common settings: unknown fields are errors and nothing is coerced.

    A number is never read from text or from a boolean, and "not a number"
    and infinity are rejected (C3.1).
    """

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False
    )


# --- one value ---------------------------------------------------------------


class Missing(_Contract):
    """Why a value, or a range, is absent (C3.1, C3.2)."""

    reason: ReasonCode
    detail: Text | None = None

    @model_validator(mode="after")
    def _missing_input_is_named(self) -> Self:
        if self.reason == "MISSING_INPUT" and self.detail is None:
            raise ValueError(
                "reason MISSING_INPUT needs a 'detail' naming the missing input (C3.2)"
            )
        return self


class Range(_Contract):
    """An uncertainty range: absolute bounds in the unit of the value (C2.1).

    ``kind`` names what the range represents. The closed list of kinds is
    OPEN (C2.3), so any non-blank label is accepted for now.
    """

    low: float
    high: float
    kind: Text

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> Self:
        if self.low > self.high:
            raise ValueError("'low' is greater than 'high' (C2.1)")
        return self


class IndicatorValue(_Contract):
    """One value of one indicator, as it travels in every results contract.

    Either a number with its provenance, its source and its range (or the
    reason why it has no range), or ``null`` with a ``missing`` part. The
    identifier, the unit and the direction are always present, also when
    the value is missing.
    """

    indicator: IndicatorId
    direction: Direction
    value: float | None
    unit: str
    range: Range | None = None
    range_missing: Missing | None = None
    missing: Missing | None = None
    provenance: ProvenanceLabel | None = None
    source: Text | None = None
    assumption: bool = False

    @model_validator(mode="after")
    def _follows_the_conventions(self) -> Self:
        if self.unit not in UNITS_OF[self.indicator]:
            expected = " or ".join(f"'{unit}'" for unit in UNITS_OF[self.indicator])
            raise ValueError(
                f"unit '{self.unit}' is not the unit of '{self.indicator}': expected {expected} "
                "(C1.1)"
            )
        if self.direction != DIRECTION_OF[self.indicator]:
            raise ValueError(
                f"the direction of '{self.indicator}' is '{DIRECTION_OF[self.indicator]}', "
                f"not '{self.direction}' (C1.1)"
            )
        if self.value is None and self.missing is None:
            raise ValueError(
                "neither a number nor a 'missing' part: a missing value needs its reason (C3.1)"
            )
        if self.value is not None and self.missing is not None:
            raise ValueError(
                "a number together with a 'missing' part: a missing value is never written "
                "as a number (C3.1)"
            )
        problems = (
            self._problems_when_missing() if self.value is None else self._problems()
        )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _problems_when_missing(self) -> list[str]:
        problems = []
        if self.provenance is not None:
            problems.append("a missing value carries no provenance label (C4.1)")
        if self.range is not None or self.range_missing is not None:
            problems.append(
                "a missing value has no range and no 'range_missing' (C2.2)"
            )
        if self.source is not None or self.assumption:
            problems.append("a missing value carries no source and no assumption mark")
        return problems

    def _problems(self) -> list[str]:
        problems = []
        if self.provenance is None:
            problems.append("a value needs a provenance label (C4.1)")
        elif (
            self.indicator == "soil_loss" and self.provenance != PROVENANCE_OF_SOIL_LOSS
        ):
            problems.append(
                f"the soil-loss indicator carries the label '{PROVENANCE_OF_SOIL_LOSS}', "
                f"not '{self.provenance}' (C4.6)"
            )
        if self.source is None and not self.assumption:
            problems.append("a value needs a source or the assumption mark (C4.2)")
        if self.source is not None and self.assumption:
            problems.append(
                "a value carries a source or the assumption mark, not both (C4.2)"
            )
        if self.range is None and self.range_missing is None:
            problems.append(
                "a value without a range says so: give 'range', or 'range_missing' with a "
                "reason (C2.2)"
            )
        if self.range is not None and self.range_missing is not None:
            problems.append(
                "a range together with 'range_missing': keep only one (C2.2)"
            )
        if self.range is not None:
            if not self.range.low <= self.value <= self.range.high:
                problems.append("the value lies outside its own range (C2.1)")
            elif self.range.low == self.range.high:
                problems.append(
                    "an absent range is never written as two bounds equal to the value (C2.2)"
                )
        return problems

    def _require_unit(self, unit: str, where: str) -> None:
        if self.unit != unit:
            raise ValueError(f"{where} is in '{unit}', not in '{self.unit}'")

    def _require_time_basis(self, time_basis: str, ag_year: int | None) -> None:
        if time_basis == "ag_year" and ag_year is None:
            raise ValueError("time basis 'ag_year' needs an 'ag_year' (C5.3)")
        if time_basis == "rotation" and ag_year is not None:
            raise ValueError("time basis 'rotation' carries no 'ag_year'")


# --- results per rotation ----------------------------------------------------


class AnnualSoilLoss(IndicatorValue):
    """Soil loss of one agricultural year (C1.2, C5.3)."""

    indicator: Literal["soil_loss"]
    ag_year: int

    @model_validator(mode="after")
    def _is_annual(self) -> Self:
        self._require_unit(UNIT_SOIL_LOSS_ANNUAL, "an annual value of soil loss (C1.2)")
        return self


class MonthlySoilLoss(IndicatorValue):
    """Soil loss of one calendar month, inside one agricultural year.

    ``year`` is the calendar year of the month (C5.1); ``ag_year`` is the
    agricultural year the month belongs to (C5.3).
    """

    indicator: Literal["soil_loss"]
    year: int
    month: int = Field(ge=1, le=12)
    ag_year: int

    @model_validator(mode="after")
    def _is_monthly(self) -> Self:
        self._require_unit(
            UNIT_SOIL_LOSS_MONTHLY, "a monthly value of soil loss (C1.2)"
        )
        return self


def _repeated(items: list) -> list:
    return sorted(item for item, count in Counter(items).items() if count > 1)


class SoilLossResults(_Contract):
    """Soil loss of a rotation: by agricultural year and by calendar month.

    Every agricultural year has its annual value and its twelve monthly
    values. A value that is not available is there as missing, with its
    reason; it is not left out.
    """

    annual: list[AnnualSoilLoss] = Field(min_length=1)
    monthly: list[MonthlySoilLoss]

    @model_validator(mode="after")
    def _years_and_months_match(self) -> Self:
        ag_years = [item.ag_year for item in self.annual]
        if _repeated(ag_years):
            raise ValueError(
                f"'annual' repeats agricultural year(s) {_repeated(ag_years)}"
            )

        months: dict[int, list[int]] = {}
        for item in self.monthly:
            # Position of the calendar month on one line of months.
            months.setdefault(item.ag_year, []).append(item.year * 12 + item.month - 1)
        if set(months) != set(ag_years):
            unmatched = sorted(set(months) ^ set(ag_years))
            raise ValueError(
                "'annual' and 'monthly' do not cover the same agricultural years: "
                f"{unmatched} is in one and not in the other"
            )

        start_months = set()
        for ag_year, positions in sorted(months.items()):
            positions.sort()
            if len(positions) != 12:
                raise ValueError(
                    f"agricultural year {ag_year} has {len(positions)} monthly values, "
                    "not twelve (C5.3)"
                )
            if len(set(positions)) != 12:
                raise ValueError(
                    f"agricultural year {ag_year} repeats a calendar month"
                )
            first = positions[0]
            if positions[-1] - first != 11 or first // 12 != ag_year:
                raise ValueError(
                    f"the months of agricultural year {ag_year} are not twelve consecutive "
                    f"calendar months beginning in calendar year {ag_year} (C5.3)"
                )
            start_months.add(first % 12 + 1)
        if len(start_months) > 1:
            raise ValueError(
                "the agricultural years do not all begin in the same calendar month: "
                f"{sorted(start_months)} (C5.4)"
            )
        return self


class WaterDeficitExposure(IndicatorValue):
    """Exposure to water deficit of a rotation (C1.3).

    Its time basis is OPEN in the conventions sheet, so the value says
    which one it uses: one agricultural year, or the whole rotation.
    """

    indicator: Literal["water_deficit_exposure"]
    time_basis: TimeBasis
    ag_year: int | None = None

    @model_validator(mode="after")
    def _time_basis_is_consistent(self) -> Self:
        self._require_time_basis(self.time_basis, self.ag_year)
        return self


class SoilCarbonTrend(IndicatorValue):
    """Trend of soil carbon of a rotation, for one model and one computation (C1.5)."""

    indicator: Literal["soil_carbon_trend"]
    carbon_model: Text
    computation: TrendComputation


# --- a part whose engine is not built (decision D12) --------------------------
#
# Decided (lead developer, 14 November 2026, decision D12, issues #18 and
# #77): each part of ``ResultsPerRotation`` may be wholly missing, only when
# the engine that produces it is not built, and only with reason
# ``NOT_AVAILABLE`` (C3.2). A built engine keeps the present form.
#
# PROPOSED by this unit, for the platform developer and the interface
# developer to accept or rename: the form itself. The class names, the field
# ``units`` and the way the two forms are told apart (an object with a
# ``missing`` part for ``soil_loss``; an object in place of the list for
# ``water_deficit_exposure`` and ``soil_carbon_trend``) are proposals, not
# decisions.

REASON_OF_A_PART_NOT_BUILT = "NOT_AVAILABLE"  # D12, C3.2


class PartNotBuilt(_Contract):
    """A whole part of ``ResultsPerRotation`` whose engine is not built (D12).

    PROPOSED form. It keeps the indicator identifier, its direction and its
    units (C3.1): ``units`` lists every unit the part carries in its present
    form, in the order of ``UNITS_OF``, so ``soil_loss`` names both its
    annual and its monthly unit. It carries no value of any kind.
    """

    indicator: IndicatorId
    direction: Direction
    units: list[str]
    missing: Missing

    @model_validator(mode="before")
    @classmethod
    def _carries_no_values(cls, data: object) -> object:
        if isinstance(data, dict):
            found = sorted(set(data) & _FIELDS_OF_THE_PRESENT_FORM)
            if found:
                raise ValueError(
                    "a part that is wholly missing carries no values: "
                    f"{', '.join(repr(key) for key in found)} belong to the present form (D12)"
                )
        return data

    @model_validator(mode="after")
    def _follows_d12_and_the_conventions(self) -> Self:
        if self.missing.reason != REASON_OF_A_PART_NOT_BUILT:
            raise ValueError(
                f"a part is wholly missing only when its engine is not built, with reason "
                f"'{REASON_OF_A_PART_NOT_BUILT}', not '{self.missing.reason}' (D12, C3.2)"
            )
        if self.direction != DIRECTION_OF[self.indicator]:
            raise ValueError(
                f"the direction of '{self.indicator}' is '{DIRECTION_OF[self.indicator]}', "
                f"not '{self.direction}' (C1.1)"
            )
        if tuple(self.units) != UNITS_OF[self.indicator]:
            expected = ", ".join(f"'{unit}'" for unit in UNITS_OF[self.indicator])
            raise ValueError(
                f"the units of a wholly missing '{self.indicator}' are [{expected}], "
                f"in that order (C1.1, C3.1)"
            )
        return self


class SoilLossNotBuilt(PartNotBuilt):
    """``soil_loss`` wholly missing: the erosion engine is not built (D12)."""

    indicator: Literal["soil_loss"]


class WaterDeficitExposureNotBuilt(PartNotBuilt):
    """``water_deficit_exposure`` wholly missing: the water engine is not built (D12)."""

    indicator: Literal["water_deficit_exposure"]


class SoilCarbonTrendNotBuilt(PartNotBuilt):
    """``soil_carbon_trend`` wholly missing: no carbon engine is built (D12)."""

    indicator: Literal["soil_carbon_trend"]


# Keys that belong to the present form of a part or of one of its items and
# never to the wholly missing form.
_FIELDS_OF_THE_PRESENT_FORM = (
    set(SoilLossResults.model_fields)
    | set(AnnualSoilLoss.model_fields)
    | set(MonthlySoilLoss.model_fields)
    | set(WaterDeficitExposure.model_fields)
    | set(SoilCarbonTrend.model_fields)
) - set(PartNotBuilt.model_fields)


def _soil_loss_form(data: object) -> str:
    # PROPOSED: the wholly missing form of ``soil_loss`` is told apart by its
    # ``missing`` part; the present form has none.
    if isinstance(data, PartNotBuilt) or (isinstance(data, dict) and "missing" in data):
        return "not_built"
    return "present"


def _list_part_form(data: object) -> str:
    # PROPOSED: the wholly missing form of a part that is a list in its
    # present form is one object in place of the list.
    if isinstance(data, (dict, PartNotBuilt)):
        return "not_built"
    return "present"


SoilLossPart = Annotated[
    Annotated[SoilLossResults, Tag("present")]
    | Annotated[SoilLossNotBuilt, Tag("not_built")],
    Discriminator(_soil_loss_form),
]
WaterDeficitExposurePart = Annotated[
    Annotated[list[WaterDeficitExposure], Field(min_length=1), Tag("present")]
    | Annotated[WaterDeficitExposureNotBuilt, Tag("not_built")],
    Discriminator(_list_part_form),
]
SoilCarbonTrendPart = Annotated[
    Annotated[list[SoilCarbonTrend], Field(min_length=1), Tag("present")]
    | Annotated[SoilCarbonTrendNotBuilt, Tag("not_built")],
    Discriminator(_list_part_form),
]


def _check_one_time_basis(values: list) -> None:
    """Values of water-deficit exposure in one document share one time basis."""
    if len({item.time_basis for item in values}) > 1:
        raise ValueError(
            "'water_deficit_exposure' mixes the time bases 'ag_year' and 'rotation'"
        )


class ResultsPerRotation(_Contract):
    """Contract "Results per rotation": the three indicators of one rotation.

    Each part is in its present form, or wholly missing when its engine is
    not built (decision D12; the form of that case is PROPOSED).
    """

    case_id: Text
    field_id: Text
    rotation_id: Text
    soil_loss: SoilLossPart
    water_deficit_exposure: WaterDeficitExposurePart
    soil_carbon_trend: SoilCarbonTrendPart

    @model_validator(mode="after")
    def _water_values_are_distinct(self) -> Self:
        values = self.water_deficit_exposure
        if isinstance(values, PartNotBuilt):
            return self
        _check_one_time_basis(values)
        if values[0].time_basis == "rotation" and len(values) > 1:
            raise ValueError(
                "'water_deficit_exposure' has more than one value on the time basis 'rotation'"
            )
        ag_years = [item.ag_year for item in values]
        if _repeated(ag_years):
            raise ValueError(
                f"'water_deficit_exposure' repeats agricultural year(s) {_repeated(ag_years)}"
            )
        return self

    @model_validator(mode="after")
    def _every_model_has_the_three_computations(self) -> Self:
        if isinstance(self.soil_carbon_trend, PartNotBuilt):
            return self
        computations: dict[str, list[str]] = {}
        for item in self.soil_carbon_trend:
            computations.setdefault(item.carbon_model, []).append(item.computation)
        for carbon_model, given in sorted(computations.items()):
            if sorted(given) != sorted(TREND_COMPUTATIONS):
                raise ValueError(
                    f"carbon model '{carbon_model}' must carry each of the three computations "
                    f"once ({', '.join(TREND_COMPUTATIONS)}); it carries {sorted(given)} (C1.6)"
                )
        return self


# --- results table -----------------------------------------------------------


class ResultsTableRow(IndicatorValue):
    """One value of one rotation in the results table.

    Rows of different rotations are paired when they have the same
    ``scenario_id``, indicator, time basis, agricultural year, carbon model
    and computation.
    """

    rotation_id: Text
    scenario_id: Text
    time_basis: TimeBasis
    ag_year: int | None = None
    carbon_model: Text | None = None
    computation: TrendComputation | None = None

    @model_validator(mode="after")
    def _fits_its_indicator(self) -> Self:
        self._require_time_basis(self.time_basis, self.ag_year)
        names_a_model = self.carbon_model is not None or self.computation is not None
        if self.indicator == "soil_carbon_trend":
            if self.time_basis != "rotation":
                raise ValueError("'soil_carbon_trend' is one value per rotation (C1.5)")
            if self.carbon_model is None or self.computation is None:
                raise ValueError(
                    "a value of 'soil_carbon_trend' names its carbon model and its "
                    "computation (C1.5)"
                )
        elif names_a_model:
            raise ValueError(
                f"'carbon_model' and 'computation' belong to 'soil_carbon_trend' only, "
                f"not to '{self.indicator}'"
            )
        if self.indicator == "soil_loss":
            if self.time_basis != "ag_year":
                raise ValueError(
                    "'soil_loss' is one value per agricultural year (C1.2)"
                )
            self._require_unit(
                UNIT_SOIL_LOSS_ANNUAL, "soil loss in the results table (C1.2)"
            )
        return self

    def cell(self) -> tuple:
        """What this row measures, whatever the rotation."""
        return (
            self.scenario_id,
            self.indicator,
            self.time_basis,
            self.ag_year,
            self.carbon_model,
            self.computation,
        )


class ResultsTable(_Contract):
    """Contract "Results table": rotations side by side, for the decision layer.

    Every rotation has the same cells. A value that is not available is a
    row with a missing value and its reason; the row is not left out.
    """

    case_id: Text
    field_id: Text
    rows: list[ResultsTableRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _rotations_have_the_same_cells(self) -> Self:
        _check_one_time_basis(
            [row for row in self.rows if row.indicator == "water_deficit_exposure"]
        )
        cells: dict[str, list[tuple]] = {}
        for row in self.rows:
            cells.setdefault(row.rotation_id, []).append(row.cell())
        for rotation_id, given in sorted(cells.items()):
            if len(set(given)) != len(given):
                raise ValueError(
                    f"rotation '{rotation_id}' has the same cell in two rows"
                )
        reference_id, reference = sorted(cells.items())[0]
        for rotation_id, given in sorted(cells.items()):
            if set(given) != set(reference):
                raise ValueError(
                    f"rotations '{reference_id}' and '{rotation_id}' do not have the same "
                    "cells: a value that is not available is a row with a missing value, "
                    "not an absent row"
                )
        return self
