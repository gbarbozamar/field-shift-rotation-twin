"""Contract "Plant answer": the request and the answer of "What should I plant?".

PROPOSED (blueprint section 3.7), unit ``l2/plant-answer-contract`` (brief
S-018a). One field, three to five rotations. The request carries what the user
declares: the site, the rotations, the economic facts, the soil-loss limit and
the four questions (soybean price range, kind of year, heavier rain, how
strict). The answer is the JSON form of the results of the pure functions of
``economics/`` (``choose_rotation``, ``assess_limit``,
``compute_rotation_margin``, ``find_tipping_price``), ``kinds_of_year/``
(``mean_by_kind``, ``classify_agricultural_years``, ``count_kinds``) and
``api/rain_stress.py``, field for field where it can be. See ``README.md``.

Producer of the request: the interface (S-019). Producer of the answer: the
route ``api/plant.py`` (S-018). This module imports contracts only; where a
literal of those modules is needed it is defined here and the acceptance test
checks that it equals the original (``typing.get_args``), so the two cannot
drift.

Models and pure validation only. No network calls, no parameter values, no
computation.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    Field,
    FiniteFloat,
    field_serializer,
    model_validator,
)

from contracts.economic_facts import (
    KINDS_OF_YEAR,
    MARGIN_UNIT,
    PRICE_UNIT,
    EconomicFacts,
    GrainCrop,
)
from contracts.inputs.common import (
    ContractModel,
    Missing,
    MonthNumber,
    NonEmptyStr,
    ReasonCode,
    Value,
)
from contracts.results.models import UNIT_SOIL_LOSS_ANNUAL
from contracts.rotation_definition import RotationDefinition

# --- Literals mirrored from economics/ and api/ (the test keeps them equal) ----

# economics/decide.py
Strictness = Literal["on_average", "every_kind"]
Answer = Literal["chosen", "none_meets", "not_resolved"]
OptionState = Literal["chosen", "meets", "does_not_meet", "not_resolved"]
# economics/limit.py
Verdict = Literal["meets", "does_not_meet", "not_resolved"]
# economics/tipping.py
Direction = Literal["up", "down"]
MarginOf = Literal["average", "el_nino", "neutral", "la_nina"]
MARGINS_OF: tuple[str, ...] = ("average", *KINDS_OF_YEAR)
# api/rain_stress.py
DIMENSIONLESS = "dimensionless"
STRESS_TEST_LABEL = "stress test"

# PROPOSED: which erosivity the soil-loss run used. S-026 may add "per_year".
Erosivity = Literal["mean_annual"]

# PROPOSED: three to five rotations, as the objective states.
MIN_ROTATIONS = 3
MAX_ROTATIONS = 5

DECLARED = "DECLARED"


def _duplicates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for item in items:
        if item in seen and item not in repeated:
            repeated.append(item)
        seen.add(item)
    return repeated


def _declared_value(
    unit: str, *, non_negative: bool, above_zero: bool = False
) -> Callable[[Value], Value]:
    """A value in ``unit`` exactly, ``DECLARED`` when present."""

    def check(value: Value) -> Value:
        if value.unit != unit:
            raise ValueError(f"the unit is {unit!r} (C1.1)")
        if value.value is None:
            return value
        if value.provenance != DECLARED:
            raise ValueError(
                f"a present value here is declared by the user: its provenance "
                f"is {DECLARED} (C4.1)"
            )
        if non_negative and value.value < 0:
            raise ValueError("the value must not be negative")
        if above_zero and value.value <= 0:
            raise ValueError("the value must be above zero")
        return value

    return check


SoilLossLimit = Annotated[
    Value, AfterValidator(_declared_value(UNIT_SOIL_LOSS_ANNUAL, non_negative=True))
]
RainStressFactor = Annotated[
    Value,
    AfterValidator(_declared_value(DIMENSIONLESS, non_negative=True, above_zero=True)),
]


# --- Shared shapes ---------------------------------------------------------------


class SiteReference(ContractModel):
    """The field and the point that stands for it. PROPOSED.

    Copied as a contract model from ``SiteReference`` of ``api/rotations.py``.
    """

    case_id: NonEmptyStr
    field_id: NonEmptyStr
    latitude: Annotated[FiniteFloat, Field(ge=-90, le=90)]
    longitude: Annotated[FiniteFloat, Field(ge=-180, le=180)]


class PriceRange(ContractModel):
    """The soybean price range the user declares, ``PriceRange`` of tipping.py."""

    low: FiniteFloat
    high: FiniteFloat
    unit: NonEmptyStr

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != PRICE_UNIT:
            raise ValueError(f"price range: the unit is {PRICE_UNIT!r} (C1.1)")
        if self.low < 0 or self.high < 0:
            raise ValueError("price range: a price is not negative")
        if not self.low < self.high:
            raise ValueError("price range: low is below high")
        return self


class Questions(ContractModel):
    """The four questions the user can change, plus which crop is soybean."""

    soybean_crop_ids: Annotated[list[NonEmptyStr], Field(min_length=1)]
    soybean_price_range: PriceRange
    margin_of: MarginOf  # the kind-of-year question
    rain_stress_factor: RainStressFactor | None  # null: no stress test
    strictness: Strictness

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        repeated = _duplicates(self.soybean_crop_ids)
        if repeated:
            raise ValueError(f"soybean_crop_ids: repeated {repeated}")
        return self


# --- The request -----------------------------------------------------------------


class PlantRequest(ContractModel):
    """What the user declares to ask "What should I plant?"."""

    contract: Literal["plant_request"]
    example_data: bool
    site: SiteReference
    rotations: Annotated[
        list[RotationDefinition],
        Field(min_length=MIN_ROTATIONS, max_length=MAX_ROTATIONS),
    ]
    economic_facts: EconomicFacts
    soil_loss_limit: SoilLossLimit
    questions: Questions

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        repeated = _duplicates([r.rotation_id for r in self.rotations])
        if repeated:
            raise ValueError(
                f"rotations: two rotations share the rotation_id {repeated}"
            )
        field = (self.site.case_id, self.site.field_id)
        if (self.economic_facts.case_id, self.economic_facts.field_id) != field:
            raise ValueError(
                "economic_facts: the case_id and field_id are those of the site"
            )
        # PROPOSED: every rotation is a rotation of the field of the site.
        for rotation in self.rotations:
            if (rotation.case_id, rotation.field_id) != field:
                raise ValueError(
                    f"rotations: {rotation.rotation_id!r} has the case_id and "
                    "field_id of another field than the site"
                )
        # PROPOSED: find_tipping_price refuses a soybean crop that is not a
        # grain crop of the facts; the request refuses it first.
        grain = {
            crop.crop_id
            for crop in self.economic_facts.crops
            if isinstance(crop, GrainCrop)
        }
        for crop_id in self.questions.soybean_crop_ids:
            if crop_id not in grain:
                raise ValueError(
                    "questions.soybean_crop_ids: each is a grain crop of the "
                    "economic facts"
                )
        # PROPOSED (fix round 2): find_tipping_price refuses soybean crops
        # whose declared prices differ (one soybean price is asked). A missing
        # price is allowed: the tipping price is then missing MISSING_INPUT.
        prices = {
            crop.price.value
            for crop in self.economic_facts.crops
            if crop.crop_id in self.questions.soybean_crop_ids
            and isinstance(crop, GrainCrop)
            and crop.price.value is not None
        }
        if len(prices) > 1:
            raise ValueError(
                "questions.soybean_crop_ids: the named crops carry one declared "
                "price; these carry different prices"
            )
        # PROPOSED (fix round 2): one start month of the agricultural year for
        # every rotation, so the answer holds one kinds_of_year record.
        months = {rotation.ag_year_start.month for rotation in self.rotations}
        if len(months) > 1:
            raise ValueError(
                "rotations: every rotation has the same ag_year_start month"
            )
        # PROPOSED (fix round 1): every crop a rotation sows has its economic
        # facts, else its margin could only be missing.
        declared = {crop.crop_id for crop in self.economic_facts.crops}
        sown = {
            component.crop_id
            for rotation in self.rotations
            for component in rotation.components
        }
        undeclared = sorted(sown - declared)
        if undeclared:
            raise ValueError(
                "rotations: every crop sown is declared in economic_facts; "
                f"not declared: {undeclared}"
            )
        # PROPOSED (fix round 1): a soybean crop that no rotation sows makes
        # the tipping price a question about nothing.
        not_sown = [c for c in self.questions.soybean_crop_ids if c not in sown]
        if not_sown:
            raise ValueError(
                "questions.soybean_crop_ids: each is sown by at least one "
                f"rotation; not sown: {not_sown}"
            )
        return self


# --- Value-or-missing items of the answer ----------------------------------------


def _one_of(value: object, reason: object, what: str) -> None:
    """C3.1: a value, or null with a reason; never both, never neither."""
    if value is not None and reason is not None:
        raise ValueError(f"{what}: a value or a reason, never both (C3.1)")
    if value is None and reason is None:
        raise ValueError(f"{what}: a missing value carries its reason (C3.1)")


class MarginOut(ContractModel):
    """``MarginResult`` of economics/margin.py, in ``MARGIN_UNIT``."""

    value: FiniteFloat | None
    unit: NonEmptyStr
    reason: ReasonCode | None
    detail: NonEmptyStr | None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != MARGIN_UNIT:
            raise ValueError(f"margin: the unit is {MARGIN_UNIT!r} (C1.1)")
        # As MarginResult: a reason may come without a detail; a detail only
        # with a reason.
        _one_of(self.value, self.reason, "margin")
        if self.reason is None and self.detail is not None:
            raise ValueError("margin: a present margin carries no missing detail")
        return self


class MarginByKind(ContractModel):
    average: MarginOut
    el_nino: MarginOut
    neutral: MarginOut
    la_nina: MarginOut


class SoilLossOut(ContractModel):
    """``KindMean`` of kinds_of_year/aggregate.py, in ``t ha-1 yr-1``."""

    value: FiniteFloat | None
    unit: NonEmptyStr
    n_years: Annotated[int, Field(ge=0)]
    ag_years: list[int]
    reason: ReasonCode | None
    detail: NonEmptyStr | None
    sources: list[NonEmptyStr]
    assumption: bool

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != UNIT_SOIL_LOSS_ANNUAL:
            raise ValueError(f"soil loss: the unit is {UNIT_SOIL_LOSS_ANNUAL!r} (C1.2)")
        # As KindMean: a value or a reason; KindMean sets no rule on detail.
        _one_of(self.value, self.reason, "soil loss")
        if self.ag_years != sorted(set(self.ag_years)):
            raise ValueError("soil loss: ag_years are sorted and unique")
        if self.n_years != len(self.ag_years):
            raise ValueError("soil loss: n_years is the number of ag_years")
        if self.value is not None and self.n_years < 1:
            raise ValueError("soil loss: a present mean needs at least one year")
        if self.sources != sorted(set(self.sources)):
            raise ValueError("soil loss: sources are sorted and unique")
        # PROPOSED: stricter than KindMean, which allows a value with no
        # sources and no assumption mark. C4.2 asks a displayed value for its
        # source or the mark, so the route must give one of the two.
        if self.value is not None and not self.sources and not self.assumption:
            raise ValueError(
                "soil loss: a value carries its sources or the assumption mark (C4.2)"
            )
        return self


class SoilLossByKind(ContractModel):
    average: SoilLossOut  # the mean of the whole record (MeansByKind.record)
    el_nino: SoilLossOut
    neutral: SoilLossOut
    la_nina: SoilLossOut


class LimitCheckOut(ContractModel):
    """``LimitCheck`` of economics/limit.py."""

    verdict: Verdict
    reason: ReasonCode | None
    detail: NonEmptyStr | None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        unresolved = self.verdict == "not_resolved"
        if unresolved != (self.reason is not None) or unresolved != (
            self.detail is not None
        ):
            raise ValueError(
                "limit check: a reason and a detail exactly when it is not resolved"
            )
        return self


class LimitByKind(ContractModel):
    el_nino: LimitCheckOut
    neutral: LimitCheckOut
    la_nina: LimitCheckOut


def _kinds(kinds: list[str], what: str) -> None:
    unknown = [k for k in kinds if k not in KINDS_OF_YEAR]
    if unknown:
        raise ValueError(f"{what}: only kinds of KINDS_OF_YEAR {KINDS_OF_YEAR}")
    if kinds != [k for k in KINDS_OF_YEAR if k in kinds]:
        raise ValueError(f"{what}: unique, in KINDS_OF_YEAR order")


class LimitAssessmentOut(ContractModel):
    """``LimitAssessment`` of economics/limit.py."""

    limit: Annotated[FiniteFloat, Field(ge=0)] | None
    unit: NonEmptyStr
    on_average: LimitCheckOut
    every_kind: LimitCheckOut
    by_kind: LimitByKind
    kinds_not_met: list[str]
    kinds_not_resolved: list[str]
    kinds_not_in_record: list[str]

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != UNIT_SOIL_LOSS_ANNUAL:
            raise ValueError(f"limit: the unit is {UNIT_SOIL_LOSS_ANNUAL!r} (C1.2)")
        for name in ("kinds_not_met", "kinds_not_resolved", "kinds_not_in_record"):
            _kinds(getattr(self, name), name)
        # PROPOSED (fix round 2): the lists are what assess_limit gives from
        # by_kind: the kinds in the record whose check does not meet, and
        # those not resolved; a kind not in the record is in neither, and
        # its check is not resolved (its level has no value).
        verdict = {k: getattr(self.by_kind, k).verdict for k in KINDS_OF_YEAR}
        out = self.kinds_not_in_record
        in_record = [k for k in KINDS_OF_YEAR if k not in out]
        not_met = [k for k in in_record if verdict[k] == "does_not_meet"]
        unresolved = [k for k in in_record if verdict[k] == "not_resolved"]
        if self.kinds_not_met != not_met:
            raise ValueError(
                "limit: kinds_not_met are the kinds in the record whose check "
                "does not meet"
            )
        if self.kinds_not_resolved != unresolved:
            raise ValueError(
                "limit: kinds_not_resolved are the kinds in the record whose "
                "check is not resolved"
            )
        if any(verdict[k] != "not_resolved" for k in out):
            raise ValueError(
                "limit: the check of a kind not in the record is not resolved"
            )
        if self.limit is None and (
            self.on_average.verdict != "not_resolved"
            or self.every_kind.verdict != "not_resolved"
            or any(v != "not_resolved" for v in verdict.values())
        ):
            raise ValueError("limit: with no limit, no check is resolved")
        if not_met:
            expected = "does_not_meet"
        elif unresolved or not in_record:
            expected = "not_resolved"
        else:
            expected = "meets"
        if self.every_kind.verdict != expected:
            raise ValueError(
                "limit: every_kind is does_not_meet when a kind in the record does "
                "not meet, else not_resolved when one is not resolved or none is "
                "in the record, else meets"
            )
        return self


class LimitCostOut(ContractModel):
    """``LimitCost`` of economics/decide.py."""

    value: FiniteFloat | None
    against: NonEmptyStr | None
    costs_nothing: bool
    reason: ReasonCode | None
    detail: NonEmptyStr | None
    unit: NonEmptyStr

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != MARGIN_UNIT:
            raise ValueError(f"limit cost: the unit is {MARGIN_UNIT!r} (C1.1)")
        if (self.value is None) != (self.against is None):
            raise ValueError(
                "limit cost: a cost value is set exactly with the rotation it is against"
            )
        if self.value is not None and (
            self.costs_nothing or self.reason is not None or self.detail is not None
        ):
            raise ValueError(
                "limit cost: a cost value carries no costs_nothing, reason or detail"
            )
        if self.costs_nothing and (self.reason is not None or self.detail is not None):
            raise ValueError(
                "limit cost: a cost of nothing carries no reason or detail"
            )
        if (
            self.value is None
            and not self.costs_nothing
            and (self.reason is None or self.detail is None)
        ):
            raise ValueError("limit cost: a missing cost carries a reason and a detail")
        return self


class TippingPointOut(ContractModel):
    """``TippingPoint`` of economics/tipping.py."""

    direction: Direction
    price: FiniteFloat | None
    takes_over: NonEmptyStr | None
    answer_after: Answer | None
    distance_percent: FiniteFloat | None
    reason: ReasonCode | None
    detail: NonEmptyStr | None
    unit: NonEmptyStr

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != PRICE_UNIT:
            raise ValueError(f"tipping point: the unit is {PRICE_UNIT!r} (C1.1)")
        if (self.reason is None) != (self.detail is None):
            raise ValueError("tipping point: a reason travels with its detail")
        if self.price is None:
            if (
                self.takes_over is not None
                or self.answer_after is not None
                or self.distance_percent is not None
                or self.reason is None
            ):
                raise ValueError(
                    "tipping point: a missing tipping price carries only a reason "
                    "and a detail"
                )
            return self
        if self.answer_after is None:
            raise ValueError("tipping point: a tipping price names the answer after it")
        if (self.answer_after == "chosen") != (self.takes_over is not None):
            raise ValueError(
                "tipping point: takes_over names a rotation exactly when the answer "
                "after it is chosen"
            )
        if (self.distance_percent is None) != (self.reason is not None):
            raise ValueError(
                "tipping point: a missing distance carries a reason, a present one none"
            )
        return self


class TippingPriceOut(ContractModel):
    """``TippingPrice`` of economics/tipping.py, without its nested ``Decision``.

    The decision at today's price is the answer itself.
    """

    today: FiniteFloat | None
    unit: NonEmptyStr
    price_range: PriceRange
    up: TippingPointOut
    down: TippingPointOut
    reason: ReasonCode | None
    detail: NonEmptyStr | None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.unit != PRICE_UNIT:
            raise ValueError(f"tipping price: the unit is {PRICE_UNIT!r} (C1.1)")
        if (self.reason is None) != (self.detail is None):
            raise ValueError("tipping price: a reason travels with its detail")
        if self.up.direction != "up" or self.down.direction != "down":
            raise ValueError("tipping price: up looks up and down looks down")
        # PROPOSED (fix round 2), as find_tipping_price builds it.
        if self.reason is not None:
            # A shared cause: both points missing with it.
            for point in (self.up, self.down):
                if point.price is not None or (point.reason, point.detail) != (
                    self.reason,
                    self.detail,
                ):
                    raise ValueError(
                        "tipping price: a shared reason is on both points, which "
                        "have no price"
                    )
        elif self.today is None:
            raise ValueError(
                "tipping price: a missing today's price carries a reason and a detail"
            )
        elif not self.price_range.low <= self.today <= self.price_range.high:
            raise ValueError(
                "tipping price: today's price outside the range carries a reason"
            )
        for point in (self.up, self.down):
            if point.price is not None and not (
                self.price_range.low <= point.price <= self.price_range.high
            ):
                raise ValueError("tipping price: a tipping price is inside the range")
        if self.today is not None:
            if self.up.price is not None and self.up.price < self.today:
                raise ValueError("tipping price: up.price is at or above today")
            if self.down.price is not None and self.down.price > self.today:
                raise ValueError("tipping price: down.price is at or below today")
        up, down = self.up.distance_percent, self.down.distance_percent
        if (up is not None and up < 0) or (down is not None and down > 0):
            raise ValueError(
                "tipping price: the distance is not negative up and not positive down"
            )
        return self


class RainStressApplied(ContractModel):
    """``RainStress`` of api/rain_stress.py: a declared factor, applied or not."""

    factor: FiniteFloat
    declared: RainStressFactor
    detail: NonEmptyStr
    label: NonEmptyStr
    applied: bool

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.label != STRESS_TEST_LABEL:
            raise ValueError(f"rain stress: the label is {STRESS_TEST_LABEL!r}")
        if self.declared.value is None or self.factor != self.declared.value:
            raise ValueError("rain stress: the factor is the declared value")
        return self


class RainStressMissingOut(ContractModel):
    """``RainStressMissing`` of api/rain_stress.py: no stress, with its reason."""

    missing: Missing
    detail: NonEmptyStr
    label: NonEmptyStr

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.label != STRESS_TEST_LABEL:
            raise ValueError(f"rain stress: the label is {STRESS_TEST_LABEL!r}")
        return self


class YearKind(ContractModel):
    """``KindOfYear`` of kinds_of_year/classify.py, with its agricultural year."""

    ag_year: int
    kind: NonEmptyStr | None
    missing_reason: ReasonCode | None
    detail: NonEmptyStr | None
    season: NonEmptyStr | None
    season_year: int | None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.kind is None) == (self.missing_reason is None):
            raise ValueError("kind of year: a kind or a missing_reason, never both")
        if self.kind is not None and self.kind not in KINDS_OF_YEAR:
            raise ValueError(f"kind of year: one of KINDS_OF_YEAR {KINDS_OF_YEAR}")
        # As KindOfYear: a missing kind may come without a detail.
        if self.kind is not None and self.detail is not None:
            raise ValueError("kind of year: a present kind carries no missing detail")
        return self


class KindCounts(ContractModel):
    """``count_kinds``: every count, or every count null when a year is missing."""

    el_nino: Annotated[int, Field(ge=0)] | None
    neutral: Annotated[int, Field(ge=0)] | None
    la_nina: Annotated[int, Field(ge=0)] | None


class KindsOfYearRecord(ContractModel):
    """The kinds of year the answer used. PROPOSED.

    ``source`` is the id of the record (``oni_v6``); ``start_month`` the start
    month of the agricultural year the years were classified with.
    """

    source: NonEmptyStr
    start_month: MonthNumber
    years: Annotated[list[YearKind], Field(min_length=1)]
    counts: KindCounts

    @model_validator(mode="after")
    def _rules(self) -> Self:
        ag_years = [year.ag_year for year in self.years]
        if ag_years != sorted(set(ag_years)):
            raise ValueError("kinds of year: the years are sorted and unique")
        counts = [getattr(self.counts, kind) for kind in KINDS_OF_YEAR]
        if any(year.kind is None for year in self.years):
            if any(count is not None for count in counts):
                raise ValueError(
                    "kinds of year: every count is null when a year has no kind"
                )
            return self
        expected = [
            sum(1 for year in self.years if year.kind == kind) for kind in KINDS_OF_YEAR
        ]
        if counts != expected:
            raise ValueError("kinds of year: the counts are the years of each kind")
        return self


class SourceOut(ContractModel):
    """One source of the answer, the shape of ``SourceOut`` of api/rotations.py."""

    # PROPOSED (fix round 2): the text fields are plain text, as in api/.
    id: str
    contract: str
    state: Literal["fresh", "cached", "unavailable", "example"]
    # strict=False: a JSON text is read as a date and time.
    retrieved_at: Annotated[dt.datetime, Field(strict=False)] | None
    time_zone: str | None
    request: dict[str, Any] | None
    attribution: str | None
    missing_reason: ReasonCode | None
    detail: str | None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.state == "unavailable" and self.missing_reason is None:
            raise ValueError(f"source {self.id!r}: missing_reason required")
        if self.retrieved_at is not None and self.retrieved_at.utcoffset() is None:
            raise ValueError(f"source {self.id!r}: retrieved_at has no time zone")
        return self

    @field_serializer("retrieved_at")
    def _utc(self, value: dt.datetime | None) -> str | None:
        """As ``SourceOut`` of api/rotations.py: UTC, ``YYYY-MM-DDTHH:MM:SSZ``."""
        if value is None:
            return None
        return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- The answer ------------------------------------------------------------------


class PlantOption(ContractModel):
    """What the answer says of one rotation."""

    rotation_id: NonEmptyStr
    state: OptionState
    margin: MarginByKind
    soil_loss: SoilLossByKind
    limit: LimitAssessmentOut
    limit_check: LimitCheckOut  # the check of the strictness used


class PlantAnswer(ContractModel):
    """The answer to "What should I plant?" for one field."""

    contract: Literal["plant_answer"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    questions: Questions  # as applied
    answer: Answer
    chosen: NonEmptyStr | None
    reason: ReasonCode | None
    detail: NonEmptyStr | None
    tied: list[NonEmptyStr]
    options: Annotated[
        list[PlantOption], Field(min_length=MIN_ROTATIONS, max_length=MAX_ROTATIONS)
    ]
    limit_cost: LimitCostOut
    tipping_price: TippingPriceOut
    rain_stress: RainStressApplied | RainStressMissingOut | None
    erosivity: Erosivity
    kinds_of_year: KindsOfYearRecord
    sources: list[SourceOut]

    @model_validator(mode="after")
    def _decision(self) -> Self:
        is_chosen = self.answer == "chosen"
        if is_chosen != (self.chosen is not None):
            raise ValueError(
                "a rotation is named in chosen exactly when the answer is chosen"
            )
        if is_chosen == (self.reason is not None) or is_chosen == (
            self.detail is not None
        ):
            raise ValueError(
                "an answer carries a reason and a detail exactly when nothing is chosen"
            )
        if self.tied and self.answer != "not_resolved":
            raise ValueError("tied rotations only when the answer is not resolved")
        # PROPOSED (fix round 2), as choose_rotation: none_meets only when
        # every option does not meet the limit.
        if self.answer == "none_meets" and any(
            option.state != "does_not_meet" for option in self.options
        ):
            raise ValueError("none_meets: every option is in state does_not_meet")
        # As choose_rotation: tied rotations are at least two, and meet the
        # limit with the same margin.
        if self.tied:
            if len(self.tied) < 2:
                raise ValueError("tied: at least two rotations")
            states = {option.rotation_id: option.state for option in self.options}
            if any(states.get(rotation_id) != "meets" for rotation_id in self.tied):
                raise ValueError(
                    "tied: every tied rotation is an option in state meets"
                )
        return self

    @model_validator(mode="after")
    def _options(self) -> Self:
        ids = [option.rotation_id for option in self.options]
        repeated = _duplicates(ids)
        if repeated:
            raise ValueError(f"options: two options share the rotation_id {repeated}")
        known = set(ids)
        if self.chosen is not None and self.chosen not in known:
            raise ValueError("chosen: the rotation_id of an option")
        if not set(self.tied) <= known or _duplicates(self.tied):
            raise ValueError("tied: distinct rotation_ids of options")
        in_state_chosen = [o.rotation_id for o in self.options if o.state == "chosen"]
        expected = [] if self.chosen is None else [self.chosen]
        if in_state_chosen != expected:
            raise ValueError(
                "options: the state chosen is on the chosen rotation and on no other"
            )
        strictness = self.questions.strictness
        limits = {(o.limit.limit, o.limit.unit) for o in self.options}
        if len(limits) != 1:
            raise ValueError("options: every rotation is judged against one limit")
        for option in self.options:
            check = getattr(option.limit, strictness)
            if option.limit_check != check:
                raise ValueError(
                    f"options: the limit_check of {option.rotation_id!r} is the "
                    f"{strictness} check of its limit"
                )
            if option.state == "chosen":
                if check.verdict != "meets":
                    raise ValueError("options: the chosen rotation meets the limit")
            elif option.state != check.verdict:
                raise ValueError(
                    f"options: the state of {option.rotation_id!r} is the verdict "
                    "of its limit check"
                )
        cost = self.limit_cost
        if cost.against is not None and (
            cost.against not in known or cost.against == self.chosen
        ):
            raise ValueError("limit_cost.against: another option than the chosen one")
        if self.answer != "chosen" and (cost.value is not None or cost.costs_nothing):
            raise ValueError("limit_cost: a cost only when a rotation is chosen")
        for point in (self.tipping_price.up, self.tipping_price.down):
            if point.takes_over is not None and point.takes_over not in known:
                raise ValueError("tipping_price: takes_over names an option")
        return self

    @model_validator(mode="after")
    def _questions(self) -> Self:
        if self.tipping_price.price_range != self.questions.soybean_price_range:
            raise ValueError(
                "tipping_price.price_range: the soybean price range of the questions"
            )
        factor = self.questions.rain_stress_factor
        stress = self.rain_stress
        if factor is None:
            if stress is not None:
                raise ValueError("rain_stress: null when no factor was asked")
        elif factor.value is None:
            if not isinstance(stress, RainStressMissingOut) or (
                stress.missing != factor.missing
            ):
                raise ValueError(
                    "rain_stress: a missing factor is echoed missing with its reason"
                )
        elif not isinstance(stress, RainStressApplied) or stress.declared != factor:
            raise ValueError("rain_stress: the echo of the declared factor")
        return self


def check_answer_against_request(request: PlantRequest, answer: PlantAnswer) -> None:
    """The answer is an answer to this request. PROPOSED.

    Raises ``ValueError`` when the field, the questions, the options (one per
    rotation, in request order), the limit, the example mark, today's price or
    the start month differ. Checks that need both, so no model
    validator can hold them.
    """
    if (answer.case_id, answer.field_id) != (
        request.site.case_id,
        request.site.field_id,
    ):
        raise ValueError("answer: the case_id and field_id of the request's site")
    if answer.questions != request.questions:
        raise ValueError("answer: the questions of the request, as applied")
    asked = [rotation.rotation_id for rotation in request.rotations]
    given = [option.rotation_id for option in answer.options]
    if given != asked:
        raise ValueError("answer: one option per rotation, in request order")
    limit = request.soil_loss_limit.value
    if any(option.limit.limit != limit for option in answer.options):
        raise ValueError("answer: every option is judged against the declared limit")
    # PROPOSED (fix round 2): an answer to example data is example data.
    if request.example_data and not answer.example_data:
        raise ValueError("answer: example_data is true when the request's is")
    # PROPOSED (fix round 2): today's price is the declared soybean price, or
    # null when one named crop has no price (as find_tipping_price reads it).
    prices = [
        crop.price.value
        for crop in request.economic_facts.crops
        if crop.crop_id in request.questions.soybean_crop_ids
        and isinstance(crop, GrainCrop)
    ]
    today = None if None in prices else prices[0]
    if answer.tipping_price.today != today:
        raise ValueError(
            "answer: tipping_price.today is the declared soybean price, or null "
            "when it is missing"
        )
    months = {rotation.ag_year_start.month for rotation in request.rotations}
    if {answer.kinds_of_year.start_month} != months:
        raise ValueError(
            "answer: kinds_of_year.start_month is the rotations' ag_year_start month"
        )
