"""Contract "Rotation definition" (blueprint section 5). PROPOSED.

Producer: Interface. Consumer: Engines (the calendar engine takes it as its
argument, ``contracts/ENTRYPOINTS.md`` entry EP2).

The field list is the one the producer proposed in issue #60, landed by a
builder session. See ``README.md`` in this folder for what is PROPOSED, what
differs from the producer's example and what is OPEN.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .common import ContractModel, DateValue, NonEmptyStr

# The closed list the producer proposed in issue #60. Whether it is the right
# list is OPEN (question 5 of the issue).
Purpose = Literal["grain", "cover", "pasture"]


class RotationComponent(ContractModel):
    """One component of the cycle, as the user declares it."""

    component_id: NonEmptyStr
    position: int  # numbers the components inside the cycle, from 1
    crop_id: NonEmptyStr  # any text that is not blank: the vocabulary is OPEN
    purpose: Purpose
    sowing: DateValue  # an exact date: exact dates or windows is OPEN
    harvest: DateValue

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
        return self
