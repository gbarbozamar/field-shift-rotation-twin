"""Contract "Economic facts". PROPOSED (blueprint section 3.7).

The economic facts a producer declares for one field: per grain crop, today's
price, the cost per hectare and the yield in each kind of year; per pasture
(a crop whose margin is declared directly), the declared margin in each kind
of year; per cover crop, its cost.

Producer: the interface, from what the user declares. Consumers: the
classification of kinds of year and the margin engine of later units, which
import ``KINDS_OF_YEAR`` from here. Landed by a builder session of lane L2
(unit ``l2/contracts-economic-facts``). See ``README.md`` in this folder for what is PROPOSED and what is OPEN.

Models and pure validation only. No network calls, no parameter values, no
margin computation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from contracts.inputs.common import ContractModel, NonEmptyStr, Value

# The kinds of year, in this order. PROPOSED. How a year is assigned to a
# kind is OPEN (README.md); this contract only names them.
KINDS_OF_YEAR: tuple[str, ...] = ("el_nino", "neutral", "la_nina")

# The unit strings of this contract, written as C1.1 writes units (spaces,
# negative exponents). PROPOSED: C1.1 does not list ``USD`` (README.md, OPEN).
PRICE_UNIT = "USD t-1"
COST_UNIT = "USD ha-1"
YIELD_UNIT = "t ha-1"
MARGIN_UNIT = "USD ha-1 yr-1"


# Every present value of this contract is declared by the user (C4.1). PROPOSED.
DECLARED = "DECLARED"


def _value_rule(unit: str, *, non_negative: bool) -> Callable[[Value], Value]:
    """A value in ``unit`` exactly, ``DECLARED`` when present.

    When ``non_negative``, a present value and the bounds of its range are
    not below zero.
    """

    def check(value: Value) -> Value:
        if value.unit != unit:
            raise ValueError(f"the unit is {unit!r} (C1.1)")
        if value.value is not None and value.provenance != DECLARED:
            raise ValueError(
                "a present value of this contract is declared by the user: "
                f"its provenance is {DECLARED} (C4.1)"
            )
        if non_negative and value.value is not None and value.value < 0:
            raise ValueError("the value must not be negative; this one is below zero")
        if non_negative and value.range is not None and value.range.low < 0:
            raise ValueError(
                "the range must not be negative; its low bound is below zero"
            )
        return value

    return check


def _no_surrounding_white_space(text: str) -> str:
    if text != text.strip():
        raise ValueError("crop_id has no leading or trailing white space")
    return text


CropId = Annotated[NonEmptyStr, AfterValidator(_no_surrounding_white_space)]


Price = Annotated[Value, AfterValidator(_value_rule(PRICE_UNIT, non_negative=True))]
Cost = Annotated[Value, AfterValidator(_value_rule(COST_UNIT, non_negative=True))]
Yield = Annotated[Value, AfterValidator(_value_rule(YIELD_UNIT, non_negative=True))]
# A declared margin may be negative: a pasture may lose money in a kind of year.
Margin = Annotated[Value, AfterValidator(_value_rule(MARGIN_UNIT, non_negative=False))]


class YieldByYear(ContractModel):
    """The yield of a grain crop in each kind of year; each one required."""

    el_nino: Yield
    neutral: Yield
    la_nina: Yield


class MarginByYear(ContractModel):
    """The declared margin of a pasture in each kind of year; each one required."""

    el_nino: Margin
    neutral: Margin
    la_nina: Margin


class GrainCrop(ContractModel):
    """A crop that is sold: price, cost and yield in each kind of year.

    Time basis (PROPOSED): ``cost`` is per hectare for one crop cycle (one
    sowing of that crop); ``yield`` is per hectare for that cycle. The margin
    engine adds the cycles that fall in one agricultural year.
    """

    # ``yield`` is a Python keyword: the member is ``yield_`` in Python and
    # ``yield`` in the contract. Validation takes either name; output writes
    # ``yield``.
    model_config = ConfigDict(
        serialize_by_alias=True, validate_by_alias=True, validate_by_name=True
    )

    crop_id: CropId
    kind: Literal["grain"]
    price: Price
    cost: Cost
    yield_: YieldByYear = Field(alias="yield")


class CoverCrop(ContractModel):
    """A crop that is not sold: its cost only.

    Time basis (PROPOSED): ``cost`` is per hectare for one crop cycle (one
    sowing of that crop); the margin engine adds the cycles of a year.
    """

    crop_id: CropId
    kind: Literal["cover"]
    cost: Cost


class DeclaredMarginCrop(ContractModel):
    """A crop whose margin the producer declares directly, such as a pasture.

    Time basis (PROPOSED): ``declared_margin`` is per hectare and agricultural
    year (``USD ha-1 yr-1``), in each kind of year.
    """

    crop_id: CropId
    kind: Literal["declared_margin"]
    declared_margin: MarginByYear


Crop = Annotated[
    GrainCrop | CoverCrop | DeclaredMarginCrop, Field(discriminator="kind")
]


class EconomicFacts(ContractModel):
    """The economic facts a producer declares for one field."""

    contract: Literal["economic_facts"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    currency: Literal["USD"]  # OPEN: other currencies
    crops: Annotated[list[Crop], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_crop_ids(self) -> EconomicFacts:
        ids = [crop.crop_id.strip() for crop in self.crops]
        if len(ids) != len(set(ids)):
            raise ValueError("crops: two crops share one crop_id")
        return self
