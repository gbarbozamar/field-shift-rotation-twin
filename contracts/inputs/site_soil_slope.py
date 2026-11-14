"""Contract "Site data: soil and slope" (blueprint section 5). PROPOSED.

Producer: Platform, sub-lane L2a (adapters). Consumers: Lead, Engines, Interface.
The field list is a proposal of a builder session for the producer to correct;
see ``README.md`` in this folder for what is PROPOSED and what is OPEN.

Blueprint section 8 names slope length and slope steepness; they have a field
each. It names no soil property, so soil properties travel in a generic list;
which properties exist, from which source and in which unit is OPEN.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .common import ContractModel, NonEmptyStr, QuantityId, Value


class SoilProperty(Value):
    """One soil property of the field, identified by a generic ``quantity`` identifier."""

    quantity: QuantityId  # vocabulary OPEN


class SiteSoilSlope(ContractModel):
    """Soil and slope data of one field of one case."""

    contract: Literal["site_data_soil_slope"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    slope_length: Value  # unit OPEN
    slope_steepness: Value  # unit OPEN
    soil_properties: list[SoilProperty]

    @model_validator(mode="after")
    def _unique_quantities(self) -> SiteSoilSlope:
        quantities = [item.quantity for item in self.soil_properties]
        if len(quantities) != len(set(quantities)):
            raise ValueError("soil_properties: two items share one quantity identifier")
        return self
