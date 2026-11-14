"""Contract "Rotation definition" (blueprint section 5). PROPOSED.

Producer: Interface. Consumer: Engines (the calendar engine takes it as its
argument, ``contracts/ENTRYPOINTS.md`` entry EP2).

Version 2: the field list the producer proposed in issue #60, with the start
month of the agricultural year and the management fields the producer
proposed in issue #95, and the decisions of issue #77 (D2 to D8, D21, D39),
landed by a builder session. See ``README.md`` in this folder for what is
PROPOSED, what differs from the producer's example and what is OPEN.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Discriminator, Tag, model_validator

from .common import (
    ContractModel,
    DateValue,
    IsoDate,
    Missing,
    MonthNumber,
    NonEmptyStr,
    Provenance,
)

# The closed list the producer proposed in issue #60; kept by decision D6 of
# issue #77.
Purpose = Literal["grain", "cover", "pasture"]

# The closed lists the producer proposed in issue #95; accepted by decision
# D39 of issue #77. Wording, not thresholds.
Residue = Literal["left_on_surface", "incorporated", "removed"]
TerminationMethod = Literal["chemical", "mechanical", "frost"]


class AgYearStart(ContractModel):
    """C5.4: the calendar month in which the agricultural year of the case begins.

    Required in the definition (D7, D8 of issue #77). Mirrors ``AgYearStart``
    of ``contracts/inputs/rotation_calendar.py``, except that the month is
    never missing here: a definition without it is invalid (D7).
    """

    month: MonthNumber
    provisional: bool  # C5.4: declared by a person, marked provisional
    provenance: Provenance  # C4.1
    source: NonEmptyStr | None = None  # C4.2
    assumption: bool = False  # C4.2: the explicit "assumption" mark

    @model_validator(mode="after")
    def _source_or_assumption(self) -> AgYearStart:
        if self.source is None and not self.assumption:
            raise ValueError(
                "ag_year_start: a value carries a reference to its source "
                "or the assumption mark (C4.2)"
            )
        return self


class MissingManagementField(ContractModel):
    """A management field that is not declared: its ``missing`` part, nothing else.

    Decision D39 of issue #77: it travels as an explicit ``missing`` part with
    its reason (C3.1), never as null. The key of the field stays, so a
    consumer knows what is missing (C3.1). PROPOSED form.
    """

    missing: Missing


class Grazing(ContractModel):
    """Grazing of a component, as issue #95 proposes it."""

    intensity: NonEmptyStr  # free text until people define a measure (issue #95)


class Termination(ContractModel):
    """When and how a cover crop ends, as issue #95 proposes it."""

    date: IsoDate  # C5.2
    method: TerminationMethod


def _form(data: Any) -> str:
    # PROPOSED: a management field that is not declared is an object that
    # holds a ``missing`` part. Anything else is read as the declared form,
    # so a null is rejected by the declared form (D39).
    if isinstance(data, MissingManagementField) or (
        isinstance(data, dict) and "missing" in data
    ):
        return "missing"
    return "declared"


def _residue_form(data: Any) -> str:
    # A declared residue is a word of the closed list, never an object.
    if isinstance(data, (dict, MissingManagementField)):
        return "missing"
    return "declared"


ResidueField = Annotated[
    Annotated[Residue, Tag("declared")]
    | Annotated[MissingManagementField, Tag("missing")],
    Discriminator(_residue_form),
]
GrazingField = Annotated[
    Annotated[Grazing, Tag("declared")]
    | Annotated[MissingManagementField, Tag("missing")],
    Discriminator(_form),
]
TerminationField = Annotated[
    Annotated[Termination, Tag("declared")]
    | Annotated[MissingManagementField, Tag("missing")],
    Discriminator(_form),
]


class Management(ContractModel):
    """The management fields of one component (D4, D39 of issue #77; issue #95).

    Each field is required: declared, or missing with its reason.
    """

    residue: ResidueField
    grazing: GrazingField
    termination: TerminationField

    @model_validator(mode="before")
    @classmethod
    def _no_null_in_place_of_a_field(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulls = [
                key for key in cls.model_fields if key in data and data[key] is None
            ]
            if nulls:
                raise ValueError(
                    f"management: {', '.join(nulls)} is null; a field that is not "
                    "declared travels as a missing part with its reason, never as "
                    "null (D39)"
                )
        return data


class RotationComponent(ContractModel):
    """One component of the cycle, as the user declares it."""

    component_id: NonEmptyStr
    position: int  # numbers the components inside the cycle, from 1
    crop_id: NonEmptyStr  # D2: a closed list in params/, not landed yet
    purpose: Purpose
    sowing: DateValue  # D3: an exact date
    harvest: DateValue
    management: Management

    @model_validator(mode="after")
    def _harvest_not_before_sowing(self) -> RotationComponent:
        # Checked only when both dates are present.
        if (
            self.sowing.date is not None
            and self.harvest.date is not None
            and self.harvest.date < self.sowing.date
        ):
            raise ValueError(
                f"component {self.component_id!r}: harvest is before sowing"
            )
        return self


class RotationDefinition(ContractModel):
    """What the user declares for one rotation on one field."""

    contract: Literal["rotation_definition"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    rotation_id: NonEmptyStr
    label: NonEmptyStr
    ag_year_start: AgYearStart  # D7, D8: required, never missing
    repeats: bool  # true: the cycle starts over after the last component
    components: list[RotationComponent]

    @model_validator(mode="after")
    def _consistent(self) -> RotationDefinition:
        ids = [component.component_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("definition: two components share one component_id")
        positions = sorted(component.position for component in self.components)
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError(
                "definition: positions number the components from 1, "
                "none repeated and none skipped"
            )
        # D21 of issue #77: at least one sowing or harvest date is present.
        if not any(
            component.sowing.date is not None or component.harvest.date is not None
            for component in self.components
        ):
            raise ValueError(
                "definition: at least one sowing or harvest date is present (D21)"
            )
        return self
