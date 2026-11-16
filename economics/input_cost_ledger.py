"""Eight-rubric farm input cost ledger.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements the Rev13 §12.2 / §13 eight-rubric farm input cost ledger
(``seed``, ``fertilizer``, ``crop_protection``, ``field_operations``,
``harvest_freight``, ``pasture_establishment``, ``livestock``,
``structure_rent``) with explicit price-book provenance, typed missingness
(``contracts.inputs.common.Missing``), fertilizer ``(N, P, K, S)`` nutrient
mass balance against declared crop harvest nutrient removal, explicit cover
crop herbicide/spray savings enforcement, declared-year pasture establishment
concentration (no silent amortization), and linear yield scaling for
harvest/freight.

Pure Python 3.12 stdlib + ``contracts.*`` + ``pydantic``. No network calls,
no invented prices, no fabricated crop nutrient contents, and no currency FX
estimation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    FiniteFloat,
    model_validator,
)

from contracts.inputs.common import IsoDate, Missing, NonEmptyStr

STATUS_MARKER = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"

RUBRICS: tuple[str, ...] = (
    "seed",
    "fertilizer",
    "crop_protection",
    "field_operations",
    "harvest_freight",
    "pasture_establishment",
    "livestock",
    "structure_rent",
)

Rubric = Literal[
    "seed",
    "fertilizer",
    "crop_protection",
    "field_operations",
    "harvest_freight",
    "pasture_establishment",
    "livestock",
    "structure_rent",
]

NUTRIENTS: tuple[str, ...] = ("N", "P", "K", "S")
NutrientSymbol = Literal["N", "P", "K", "S"]

LedgerStatus = Literal["complete", "incomplete", "not_computable"]
RubricStatus = Literal["computed", "pending", "not_applicable", "not_computable"]
NutrientBalanceStatus = Literal[
    "net_mining", "surplus", "balanced", "pending", "not_applicable"
]
MismatchPolicy = Literal["raise", "not_computable"]
PastureAllocationMode = Literal[
    "concentrated_in_declared_year", "explicitly_amortized", "not_applicable"
]
ActivityKind = Literal["grain", "cover", "pasture", "livestock", "fallow", "other"]


def _non_negative(value: float) -> float:
    if value < 0:
        raise ValueError("value must be non-negative")
    return value


def _no_surrounding_whitespace(text: str) -> str:
    if text != text.strip():
        raise ValueError("identifier/code must not have leading or trailing whitespace")
    return text


def _sequence_to_tuple(value: Any) -> Any:
    if isinstance(value, (str, bytes, bytearray, Mapping, set)):
        raise TypeError("expected a sequence (tuple or list), not a text or mapping")
    if isinstance(value, list):
        return tuple(value)
    return value


def _parse_int_key(value: Any) -> Any:
    """Allow JSON-serialized integer dict keys during strict round-trip."""
    if isinstance(value, str) and (
        value.isdigit() or (value.startswith("-") and value[1:].isdigit())
    ):
        return int(value)
    return value


NonNegativeFiniteFloat = Annotated[FiniteFloat, AfterValidator(_non_negative)]
CleanCodeStr = Annotated[NonEmptyStr, AfterValidator(_no_surrounding_whitespace)]
YearKey = Annotated[int, BeforeValidator(_parse_int_key)]
ConceptTuple = Annotated[tuple[NonEmptyStr, ...], BeforeValidator(_sequence_to_tuple)]
RubricTuple = Annotated[tuple[Rubric, ...], BeforeValidator(_sequence_to_tuple)]
NutrientTuple = Annotated[
    tuple[NutrientSymbol, ...], BeforeValidator(_sequence_to_tuple)
]
StrTuple = Annotated[tuple[str, ...], BeforeValidator(_sequence_to_tuple)]
YearTuple = Annotated[tuple[int, ...], BeforeValidator(_sequence_to_tuple)]
FloatTuple = Annotated[
    tuple[NonNegativeFiniteFloat, ...], BeforeValidator(_sequence_to_tuple)
]


class _LedgerModel(BaseModel):
    """Strict, immutable Pydantic base model for the input cost ledger."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False
    )


class PriceBookEntry(_LedgerModel):
    """One quoted unit price entry with explicit provenance and tax basis.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    item_id: CleanCodeStr
    currency: CleanCodeStr
    unit: CleanCodeStr
    quote_date: IsoDate
    source: NonEmptyStr
    tax_basis: NonEmptyStr
    included_concepts: ConceptTuple
    unit_price: NonNegativeFiniteFloat | None
    missing: Missing | None = None

    @model_validator(mode="after")
    def _check_price_and_missing(self) -> PriceBookEntry:
        if self.unit_price is not None and self.missing is not None:
            raise ValueError(
                f"price book item {self.item_id!r}: present unit_price cannot "
                "carry a missing part"
            )
        return self


class NutrientVector(_LedgerModel):
    """Mass of macronutrients (N, P, K, S).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    N: NonNegativeFiniteFloat = 0.0
    P: NonNegativeFiniteFloat = 0.0
    K: NonNegativeFiniteFloat = 0.0
    S: NonNegativeFiniteFloat = 0.0

    def get(self, symbol: NutrientSymbol) -> float:
        """Return the mass for nutrient ``symbol``."""
        return float(getattr(self, symbol))


class PastureAmortizationSpec(_LedgerModel):
    """Explicit pasture establishment/renovation amortization specification.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    By default pasture establishment/renovation costs concentrate in the
    declared year; amortization occurs only when explicitly specified here.
    """

    amortize: bool = False
    target_ag_years: YearTuple = ()
    weights: FloatTuple | None = None

    @model_validator(mode="after")
    def _validate_amortization(self) -> PastureAmortizationSpec:
        if not self.amortize:
            if self.target_ag_years or self.weights is not None:
                raise ValueError(
                    "pasture_amortization: target_ag_years and weights require "
                    "amortize=True"
                )
            return self
        if not self.target_ag_years:
            raise ValueError(
                "pasture_amortization: amortize=True requires non-empty "
                "target_ag_years (never silently amortized)"
            )
        if len(set(self.target_ag_years)) != len(self.target_ag_years):
            raise ValueError(
                "pasture_amortization: target_ag_years must not contain duplicates"
            )
        if self.weights is not None:
            if len(self.weights) != len(self.target_ag_years):
                raise ValueError(
                    "pasture_amortization: weights length must match target_ag_years"
                )
            if abs(sum(self.weights) - 1.0) > 1e-6:
                raise ValueError("pasture_amortization: weights must sum to 1.0")
        return self


class CoverCropSavingSpec(_LedgerModel):
    """Explicit crop-protection saving backed by entered evidence.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Refuses unentered or assumed herbicide/spray savings from cover crops.
    """

    is_explicit: bool
    saving_amount_per_ha: NonNegativeFiniteFloat | None = None
    justification: NonEmptyStr | None = None
    assumed: bool = False

    @model_validator(mode="after")
    def _require_explicit_saving(self) -> CoverCropSavingSpec:
        if self.assumed:
            raise ValueError(
                "crop_protection: assumed herbicide/spray savings from cover crops "
                "are refused (cover_crop_savings_must_be_explicit=True)"
            )
        if not self.is_explicit:
            raise ValueError(
                "crop_protection: cover crop herbicide/spray savings must be "
                "explicitly entered (is_explicit=True)"
            )
        if self.saving_amount_per_ha is None or self.justification is None:
            raise ValueError(
                "crop_protection: explicit cover crop saving requires both "
                "saving_amount_per_ha and justification"
            )
        return self


class ActivityDeclaration(_LedgerModel):
    """Declared agricultural activity in one agricultural year.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ag_year: int
    crop_id: CleanCodeStr
    activity_kind: ActivityKind = "grain"
    required_rubrics: RubricTuple = ()
    yield_t_ha: NonNegativeFiniteFloat | None = None
    yield_missing: Missing | None = None
    harvest_nutrient_removal_kg_ha: NutrientVector | None = None
    nutrient_removal_kg_per_t: NutrientVector | None = None
    pasture_establishment_year: bool = False
    assume_cover_crop_herbicide_savings: bool = False

    @model_validator(mode="after")
    def _validate_activity(self) -> ActivityDeclaration:
        if self.assume_cover_crop_herbicide_savings:
            raise ValueError(
                f"crop_id {self.crop_id!r} (ag_year {self.ag_year}): "
                "crop_protection refuses assuming unentered herbicide/spray "
                "savings from cover crops (cover_crop_savings_must_be_explicit=True)"
            )
        if self.yield_t_ha is not None and self.yield_missing is not None:
            raise ValueError(
                f"crop_id {self.crop_id!r}: yield_t_ha and yield_missing cannot "
                "both be set"
            )
        if (
            self.harvest_nutrient_removal_kg_ha is not None
            and self.nutrient_removal_kg_per_t is not None
        ):
            raise ValueError(
                f"crop_id {self.crop_id!r}: provide either "
                "harvest_nutrient_removal_kg_ha or nutrient_removal_kg_per_t, "
                "not both"
            )
        return self


class CostLineItem(_LedgerModel):
    """One declared input line item assigned to one of the 8 rubrics.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    rubric: Rubric
    item_id: CleanCodeStr
    ag_year: int
    unit: CleanCodeStr
    quantity: NonNegativeFiniteFloat | None = None
    quantity_missing: Missing | None = None
    currency: CleanCodeStr | None = None
    crop_id: CleanCodeStr | None = None
    scale_with_yield: bool = False
    nutrient_kg_per_unit: NutrientVector | None = None
    pasture_amortization: PastureAmortizationSpec | None = None
    cover_crop_saving: CoverCropSavingSpec | None = None
    assume_cover_crop_herbicide_savings: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_line_item(self) -> CostLineItem:
        if self.assume_cover_crop_herbicide_savings:
            raise ValueError(
                f"item_id {self.item_id!r} (ag_year {self.ag_year}): "
                "crop_protection refuses assuming unentered herbicide/spray "
                "savings from cover crops (cover_crop_savings_must_be_explicit=True)"
            )
        if self.quantity is not None and self.quantity_missing is not None:
            raise ValueError(
                f"item_id {self.item_id!r}: quantity and quantity_missing cannot "
                "both be set"
            )
        if self.scale_with_yield and self.rubric != "harvest_freight":
            raise ValueError(
                f"item_id {self.item_id!r}: scale_with_yield=True is valid only "
                "for 'harvest_freight'"
            )
        if self.pasture_amortization is not None and (
            self.rubric != "pasture_establishment"
        ):
            raise ValueError(
                f"item_id {self.item_id!r}: pasture_amortization is valid only "
                "for 'pasture_establishment'"
            )
        if self.cover_crop_saving is not None and self.rubric != "crop_protection":
            raise ValueError(
                f"item_id {self.item_id!r}: cover_crop_saving is valid only "
                "for 'crop_protection'"
            )
        if self.nutrient_kg_per_unit is not None and self.rubric != "fertilizer":
            raise ValueError(
                f"item_id {self.item_id!r}: nutrient_kg_per_unit is valid only "
                "for 'fertilizer'"
            )
        return self


class RubricLedgerEntry(_LedgerModel):
    """Ledger summary for one of the 8 rubrics.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    rubric: Rubric
    status: RubricStatus
    total_cost_per_ha: float | None
    annual_average_cost_per_ha: float | None
    cost_by_year: dict[YearKey, float | None]
    currency: NonEmptyStr
    line_item_count: int
    missing: Missing | None = None
    pending_items: StrTuple = ()
    allocation_mode: PastureAllocationMode | None = None


class NutrientElementBalance(_LedgerModel):
    """Mass balance of one nutrient element (N, P, K, or S) in kg ha-1.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    nutrient: NutrientSymbol
    supplied_kg_ha: float | None
    removed_kg_ha: float | None
    balance_kg_ha: float | None
    status: NutrientBalanceStatus
    missing: Missing | None = None


class YearCostSummary(_LedgerModel):
    """Cost summary for one agricultural year.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ag_year: int
    status: LedgerStatus
    total_cost_per_ha: float | None
    rubric_costs_per_ha: dict[Rubric, float | None]
    missing: Missing | None = None


class InputCostLedgerReport(_LedgerModel):
    """Complete output of the 8-rubric farm input cost ledger.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    contract: Literal["input_cost_ledger_report"] = "input_cost_ledger_report"
    ledger_status: LedgerStatus
    currency: NonEmptyStr
    ag_years: YearTuple
    rubrics: dict[Rubric, RubricLedgerEntry]
    by_year: dict[YearKey, YearCostSummary]
    total_cost_per_ha: float | None
    annual_average_cost_per_ha: float | None
    pending_rubrics: RubricTuple
    missing: Missing | None = None
    nutrient_balance_kg_ha: dict[NutrientSymbol, NutrientElementBalance]
    nutrient_balance_by_year: dict[
        YearKey, dict[NutrientSymbol, NutrientElementBalance]
    ]
    net_mining_nutrients: NutrientTuple
    surplus_nutrients: NutrientTuple
    cover_crop_savings_must_be_explicit: Literal[True] = True
    pasture_allocation_mode: PastureAllocationMode
    price_book_audit: dict[str, PriceBookEntry]


def _index_price_book(
    price_book: Sequence[PriceBookEntry] | Mapping[str, PriceBookEntry],
) -> dict[str, PriceBookEntry]:
    if isinstance(price_book, Mapping):
        indexed: dict[str, PriceBookEntry] = {}
        for key, entry in price_book.items():
            if not isinstance(entry, PriceBookEntry):
                raise ValueError(f"price_book[{key!r}]: expected PriceBookEntry")  # noqa: TRY004
            if key != entry.item_id:
                raise ValueError(
                    f"price_book key {key!r} does not match entry.item_id "
                    f"{entry.item_id!r}"
                )
            indexed[key] = entry
        return indexed
    indexed = {}
    for entry in price_book:
        if not isinstance(entry, PriceBookEntry):
            raise ValueError("price_book: every element must be a PriceBookEntry")  # noqa: TRY004
        if entry.item_id in indexed:
            raise ValueError(f"price_book: duplicate item_id {entry.item_id!r}")
        indexed[entry.item_id] = entry
    return indexed


def _index_activities(
    activities: Sequence[ActivityDeclaration],
) -> tuple[
    tuple[int, ...],
    dict[int, list[ActivityDeclaration]],
    dict[tuple[int, str], ActivityDeclaration],
]:
    if not activities:
        raise ValueError("activities: at least one ActivityDeclaration is required")
    by_year: dict[int, list[ActivityDeclaration]] = {}
    by_key: dict[tuple[int, str], ActivityDeclaration] = {}
    for activity in activities:
        key = (activity.ag_year, activity.crop_id)
        if key in by_key:
            raise ValueError(
                f"activities: duplicate (ag_year={activity.ag_year}, "
                f"crop_id={activity.crop_id!r})"
            )
        by_key[key] = activity
        by_year.setdefault(activity.ag_year, []).append(activity)
    ag_years = tuple(sorted(by_year))
    return ag_years, by_year, by_key


def _check_cross_item_units(
    line_items: Sequence[CostLineItem],
    by_year: Mapping[int, list[ActivityDeclaration]],
    by_key: Mapping[tuple[int, str], ActivityDeclaration],
    ledger_currency: str,
    on_mismatch: MismatchPolicy,
) -> dict[Rubric, list[str]]:
    """Validate line-item references and detect cross-item currency/unit mismatches."""
    mismatch_by_rubric: dict[Rubric, list[str]] = {}
    seen_item_units: dict[str, tuple[str, int]] = {}
    for item in line_items:
        if item.ag_year not in by_year:
            raise ValueError(
                f"item_id {item.item_id!r}: ag_year {item.ag_year} is not in "
                "declared activities"
            )
        if item.crop_id is not None and (item.ag_year, item.crop_id) not in by_key:
            raise ValueError(
                f"item_id {item.item_id!r}: crop_id {item.crop_id!r} is not "
                f"declared in ag_year {item.ag_year}"
            )
        if item.pasture_amortization and item.pasture_amortization.amortize:
            for target_year in item.pasture_amortization.target_ag_years:
                if target_year not in by_year:
                    raise ValueError(
                        f"item_id {item.item_id!r}: pasture_amortization target "
                        f"ag_year {target_year} is not in declared activities"
                    )
        if item.currency is not None and item.currency != ledger_currency:
            msg = (
                f"currency mismatch on {item.item_id!r} (ag_year {item.ag_year}): "
                f"line item has {item.currency!r}, ledger currency is "
                f"{ledger_currency!r}"
            )
            if on_mismatch == "raise":
                raise ValueError(msg)
            mismatch_by_rubric.setdefault(item.rubric, []).append(msg)
        if item.item_id in seen_item_units:
            prev_unit, prev_year = seen_item_units[item.item_id]
            if item.unit != prev_unit:
                msg = (
                    f"unit mismatch across line items for {item.item_id!r}: "
                    f"ag_year {prev_year} uses {prev_unit!r}, ag_year "
                    f"{item.ag_year} uses {item.unit!r}"
                )
                if on_mismatch == "raise":
                    raise ValueError(msg)
                mismatch_by_rubric.setdefault(item.rubric, []).append(msg)
        else:
            seen_item_units[item.item_id] = (item.unit, item.ag_year)
    return mismatch_by_rubric


def _resolve_yield_for_item(
    item: CostLineItem,
    by_year: Mapping[int, list[ActivityDeclaration]],
    by_key: Mapping[tuple[int, str], ActivityDeclaration],
) -> tuple[float | None, str | None]:
    """Return (yield_t_ha, missing_detail) for a yield-scaled harvest_freight item."""
    if item.crop_id is not None:
        activity = by_key[(item.ag_year, item.crop_id)]
    else:
        year_activities = by_year[item.ag_year]
        if len(year_activities) != 1:
            raise ValueError(
                f"item_id {item.item_id!r} (ag_year {item.ag_year}): "
                "scale_with_yield=True requires crop_id when multiple activities "
                "exist in the same agricultural year"
            )
        activity = year_activities[0]
    if activity.yield_t_ha is None:
        reason_suffix = (
            f" ({activity.yield_missing.reason})"
            if activity.yield_missing is not None
            else ""
        )
        return None, (
            f"yield_t_ha for crop {activity.crop_id!r} in ag_year "
            f"{item.ag_year} is absent{reason_suffix}"
        )
    return float(activity.yield_t_ha), None


def _evaluate_line_item(
    item: CostLineItem,
    price_book: Mapping[str, PriceBookEntry],
    by_year: Mapping[int, list[ActivityDeclaration]],
    by_key: Mapping[tuple[int, str], ActivityDeclaration],
    ledger_currency: str,
    on_mismatch: MismatchPolicy,
) -> tuple[float | None, list[str], list[str], PriceBookEntry | None]:
    """Evaluate one line item -> (cost_per_ha, mismatch_msgs, pending_msgs, entry)."""
    entry = price_book.get(item.item_id)
    mismatch_msgs: list[str] = []
    pending_msgs: list[str] = []

    if entry is not None:
        if entry.currency != ledger_currency:
            msg = (
                f"currency mismatch for {item.item_id!r}: price book has "
                f"{entry.currency!r}, ledger currency is {ledger_currency!r}"
            )
            if on_mismatch == "raise":
                raise ValueError(msg)
            mismatch_msgs.append(msg)
        if entry.unit != item.unit:
            msg = (
                f"unit mismatch for {item.item_id!r}: line item has "
                f"{item.unit!r}, price book has {entry.unit!r}"
            )
            if on_mismatch == "raise":
                raise ValueError(msg)
            mismatch_msgs.append(msg)

    if mismatch_msgs:
        return None, mismatch_msgs, pending_msgs, entry

    if entry is None:
        pending_msgs.append(
            f"price for {item.item_id!r} (ag_year {item.ag_year}) is not loaded "
            "in price_book"
        )
    elif entry.unit_price is None:
        suffix = f" ({entry.missing.reason})" if entry.missing is not None else ""
        pending_msgs.append(
            f"unit_price for {item.item_id!r} (ag_year {item.ag_year}) is "
            f"absent{suffix}"
        )

    if item.quantity is None:
        suffix = (
            f" ({item.quantity_missing.reason})"
            if item.quantity_missing is not None
            else ""
        )
        pending_msgs.append(
            f"quantity for {item.item_id!r} (ag_year {item.ag_year}) is absent{suffix}"
        )

    effective_qty: float | None = (
        float(item.quantity) if item.quantity is not None else None
    )
    if item.scale_with_yield:
        yield_val, yield_err = _resolve_yield_for_item(item, by_year, by_key)
        if yield_err is not None:
            pending_msgs.append(yield_err)
            effective_qty = None
        elif effective_qty is not None:
            effective_qty *= yield_val

    if (
        pending_msgs
        or entry is None
        or entry.unit_price is None
        or effective_qty is None
    ):
        return None, mismatch_msgs, pending_msgs, entry

    return effective_qty * float(entry.unit_price), mismatch_msgs, pending_msgs, entry


def _distribute_pasture_cost(
    item: CostLineItem,
    cost: float,
    year_costs: dict[int, float | None],
) -> PastureAllocationMode:
    spec = item.pasture_amortization
    if spec is None or not spec.amortize:
        prev = year_costs.get(item.ag_year)
        year_costs[item.ag_year] = (prev or 0.0) + cost
        return "concentrated_in_declared_year"
    targets = spec.target_ag_years
    weights = (
        spec.weights
        if spec.weights is not None
        else tuple(1.0 / len(targets) for _ in targets)
    )
    for target_year, weight in zip(targets, weights, strict=True):
        prev = year_costs.get(target_year)
        year_costs[target_year] = (prev or 0.0) + cost * float(weight)
    return "explicitly_amortized"


def _apply_crop_protection_savings(
    items: Sequence[CostLineItem],
    year_costs: dict[int, float | None],
    year_pending: dict[int, list[str]],
    year_mismatch: dict[int, list[str]],
) -> None:
    """Apply explicit cover-crop savings after gross costs are summed."""
    for item in items:
        if item.cover_crop_saving is None:
            continue
        if year_mismatch.get(item.ag_year) or year_pending.get(item.ag_year):
            continue
        gross = year_costs.get(item.ag_year)
        if gross is None:
            continue
        saving = float(item.cover_crop_saving.saving_amount_per_ha)
        if saving > gross:
            raise ValueError(
                f"crop_protection (ag_year {item.ag_year}): explicit cover crop "
                f"saving ({saving}) exceeds gross crop protection cost ({gross})"
            )
        year_costs[item.ag_year] = gross - saving


def _compute_fertilizer_supply_by_year(
    ag_years: Sequence[int],
    fert_items: Sequence[CostLineItem],
    by_year: Mapping[int, list[ActivityDeclaration]],
    fertilizer_compositions: Mapping[str, NutrientVector] | None,
) -> dict[int, tuple[dict[NutrientSymbol, float] | None, str | None]]:
    """Compute supplied (N, P, K, S) in kg ha-1 per year, or missing detail."""
    compositions = fertilizer_compositions or {}
    items_by_year: dict[int, list[CostLineItem]] = {y: [] for y in ag_years}
    for item in fert_items:
        items_by_year[item.ag_year].append(item)

    result: dict[int, tuple[dict[NutrientSymbol, float] | None, str | None]] = {}
    for year in ag_years:
        year_items = items_by_year[year]
        fert_required = any(
            "fertilizer" in act.required_rubrics for act in by_year[year]
        )
        if not year_items:
            if fert_required:
                result[year] = (
                    None,
                    (
                        f"fertilizer is required in ag_year {year} but no line items "
                        "were provided"
                    ),
                )
            else:
                result[year] = ({n: 0.0 for n in NUTRIENTS}, None)
            continue

        missing_reasons: list[str] = []
        totals: dict[NutrientSymbol, float] = {n: 0.0 for n in NUTRIENTS}
        for item in year_items:
            if item.quantity is None:
                missing_reasons.append(
                    f"quantity for fertilizer {item.item_id!r} in ag_year "
                    f"{year} is absent"
                )
                continue
            comp = item.nutrient_kg_per_unit or compositions.get(item.item_id)
            if comp is None:
                missing_reasons.append(
                    f"nutrient composition (N, P, K, S) for {item.item_id!r} in "
                    f"ag_year {year} is absent"
                )
                continue
            for n in NUTRIENTS:
                totals[n] += float(item.quantity) * comp.get(n)
        if missing_reasons:
            result[year] = (None, "; ".join(dict.fromkeys(missing_reasons)))
        else:
            result[year] = (totals, None)
    return result


def _compute_crop_removal_by_year(
    ag_years: Sequence[int],
    by_year: Mapping[int, list[ActivityDeclaration]],
) -> dict[int, tuple[dict[NutrientSymbol, float] | None, str | None]]:
    """Compute declared crop harvest nutrient removal (kg ha-1) per year."""
    result: dict[int, tuple[dict[NutrientSymbol, float] | None, str | None]] = {}
    for year in ag_years:
        totals: dict[NutrientSymbol, float] = {n: 0.0 for n in NUTRIENTS}
        missing_reasons: list[str] = []
        for act in by_year[year]:
            if act.harvest_nutrient_removal_kg_ha is not None:
                for n in NUTRIENTS:
                    totals[n] += act.harvest_nutrient_removal_kg_ha.get(n)
            elif act.nutrient_removal_kg_per_t is not None:
                if act.yield_t_ha is None:
                    missing_reasons.append(
                        f"yield_t_ha for crop {act.crop_id!r} in ag_year {year} "
                        "is absent for nutrient removal calculation"
                    )
                else:
                    for n in NUTRIENTS:
                        totals[n] += float(act.yield_t_ha) * (
                            act.nutrient_removal_kg_per_t.get(n)
                        )
            elif act.activity_kind != "fallow":
                missing_reasons.append(
                    f"declared harvest nutrient removal for crop {act.crop_id!r} "
                    f"in ag_year {year} is absent"
                )
        if missing_reasons:
            result[year] = (None, "; ".join(dict.fromkeys(missing_reasons)))
        else:
            result[year] = (totals, None)
    return result


def _classify_nutrient_balance(
    supplied: float, removed: float
) -> tuple[float, NutrientBalanceStatus]:
    balance = supplied - removed
    if balance < 0.0:
        return balance, "net_mining"
    if balance > 0.0:
        return balance, "surplus"
    return 0.0, "balanced"


def _build_nutrient_balances(
    ag_years: Sequence[int],
    fert_items: Sequence[CostLineItem],
    by_year: Mapping[int, list[ActivityDeclaration]],
    fertilizer_compositions: Mapping[str, NutrientVector] | None,
) -> tuple[
    dict[NutrientSymbol, NutrientElementBalance],
    dict[int, dict[NutrientSymbol, NutrientElementBalance]],
]:
    supplied_by_year = _compute_fertilizer_supply_by_year(
        ag_years, fert_items, by_year, fertilizer_compositions
    )
    removed_by_year = _compute_crop_removal_by_year(ag_years, by_year)

    per_year: dict[int, dict[NutrientSymbol, NutrientElementBalance]] = {}
    for year in ag_years:
        sup, sup_err = supplied_by_year[year]
        rem, rem_err = removed_by_year[year]
        year_map: dict[NutrientSymbol, NutrientElementBalance] = {}
        for n in NUTRIENTS:
            if sup is not None and rem is not None:
                bal, status = _classify_nutrient_balance(sup[n], rem[n])
                year_map[n] = NutrientElementBalance(
                    nutrient=n,
                    supplied_kg_ha=sup[n],
                    removed_kg_ha=rem[n],
                    balance_kg_ha=bal,
                    status=status,
                )
            else:
                details = [d for d in (sup_err, rem_err) if d is not None]
                year_map[n] = NutrientElementBalance(
                    nutrient=n,
                    supplied_kg_ha=sup[n] if sup is not None else None,
                    removed_kg_ha=rem[n] if rem is not None else None,
                    balance_kg_ha=None,
                    status="pending",
                    missing=Missing(reason="MISSING_INPUT", detail="; ".join(details)),
                )
        per_year[year] = year_map

    all_sup_ok = all(supplied_by_year[y][0] is not None for y in ag_years)
    all_rem_ok = all(removed_by_year[y][0] is not None for y in ag_years)
    overall: dict[NutrientSymbol, NutrientElementBalance] = {}
    for n in NUTRIENTS:
        total_sup = (
            sum(supplied_by_year[y][0][n] for y in ag_years) if all_sup_ok else None
        )
        total_rem = (
            sum(removed_by_year[y][0][n] for y in ag_years) if all_rem_ok else None
        )
        if total_sup is not None and total_rem is not None:
            bal, status = _classify_nutrient_balance(total_sup, total_rem)
            overall[n] = NutrientElementBalance(
                nutrient=n,
                supplied_kg_ha=total_sup,
                removed_kg_ha=total_rem,
                balance_kg_ha=bal,
                status=status,
            )
        else:
            details = [
                msg
                for y in ag_years
                for msg in (supplied_by_year[y][1], removed_by_year[y][1])
                if msg is not None
            ]
            overall[n] = NutrientElementBalance(
                nutrient=n,
                supplied_kg_ha=total_sup,
                removed_kg_ha=total_rem,
                balance_kg_ha=None,
                status="pending",
                missing=Missing(
                    reason="MISSING_INPUT",
                    detail="; ".join(dict.fromkeys(details)),
                ),
            )
    return overall, per_year


def _evaluate_rubric(
    rubric: Rubric,
    ag_years: Sequence[int],
    items: Sequence[CostLineItem],
    activities_by_year: Mapping[int, list[ActivityDeclaration]],
    activities_by_key: Mapping[tuple[int, str], ActivityDeclaration],
    price_book: Mapping[str, PriceBookEntry],
    ledger_currency: str,
    cross_mismatches: Sequence[str],
    on_mismatch: MismatchPolicy,
    price_book_audit: dict[str, PriceBookEntry],
) -> RubricLedgerEntry:
    """Compute one rubric's ledger entry across all agricultural years."""
    year_costs: dict[int, float | None] = {y: None for y in ag_years}
    year_pending: dict[int, list[str]] = {y: [] for y in ag_years}
    year_mismatch: dict[int, list[str]] = {y: [] for y in ag_years}
    all_pending: list[str] = []
    all_mismatch: list[str] = list(cross_mismatches)
    pasture_modes: set[PastureAllocationMode] = set()

    for item in items:
        cost, mismatch_msgs, pending_msgs, entry = _evaluate_line_item(
            item,
            price_book,
            activities_by_year,
            activities_by_key,
            ledger_currency,
            on_mismatch,
        )
        if entry is not None:
            price_book_audit[entry.item_id] = entry
        if mismatch_msgs:
            year_mismatch[item.ag_year].extend(mismatch_msgs)
            all_mismatch.extend(mismatch_msgs)
            continue
        if pending_msgs:
            year_pending[item.ag_year].extend(pending_msgs)
            all_pending.extend(pending_msgs)
            continue
        assert cost is not None
        if rubric == "pasture_establishment":
            mode = _distribute_pasture_cost(item, cost, year_costs)
            pasture_modes.add(mode)
        else:
            prev = year_costs[item.ag_year]
            year_costs[item.ag_year] = (prev or 0.0) + cost

    if rubric == "crop_protection":
        _apply_crop_protection_savings(items, year_costs, year_pending, year_mismatch)

    # Check required rubrics declared on activities where no line item exists.
    for year in ag_years:
        year_items = [it for it in items if it.ag_year == year]
        for act in activities_by_year[year]:
            if rubric not in act.required_rubrics:
                continue
            covered = any(
                it.crop_id is None or it.crop_id == act.crop_id for it in year_items
            )
            if not covered:
                msg = (
                    f"rubric {rubric!r} required for crop {act.crop_id!r} in "
                    f"ag_year {year} has no declared line item"
                )
                year_pending[year].append(msg)
                all_pending.append(msg)

    # Clear year cost if that year has any pending or mismatch item.
    for year in ag_years:
        if year_pending[year] or year_mismatch[year]:
            year_costs[year] = None

    allocation_mode: PastureAllocationMode | None = None
    if rubric == "pasture_establishment":
        if "explicitly_amortized" in pasture_modes:
            allocation_mode = "explicitly_amortized"
        elif "concentrated_in_declared_year" in pasture_modes:
            allocation_mode = "concentrated_in_declared_year"
        else:
            allocation_mode = "not_applicable"

    if all_mismatch:
        return RubricLedgerEntry(
            rubric=rubric,
            status="not_computable",
            total_cost_per_ha=None,
            annual_average_cost_per_ha=None,
            cost_by_year={y: None for y in ag_years},
            currency=ledger_currency,
            line_item_count=len(items),
            missing=Missing(
                reason="NOT_COMPUTABLE",
                detail="; ".join(dict.fromkeys(all_mismatch)),
            ),
            pending_items=tuple(dict.fromkeys(all_pending)),
            allocation_mode=allocation_mode,
        )

    if all_pending:
        dedup_pending = tuple(dict.fromkeys(all_pending))
        return RubricLedgerEntry(
            rubric=rubric,
            status="pending",
            total_cost_per_ha=None,
            annual_average_cost_per_ha=None,
            cost_by_year=year_costs,
            currency=ledger_currency,
            line_item_count=len(items),
            missing=Missing(
                reason="MISSING_INPUT",
                detail="; ".join(dedup_pending),
            ),
            pending_items=dedup_pending,
            allocation_mode=allocation_mode,
        )

    applicable_years = [y for y in ag_years if year_costs[y] is not None]
    if not applicable_years:
        return RubricLedgerEntry(
            rubric=rubric,
            status="not_applicable",
            total_cost_per_ha=None,
            annual_average_cost_per_ha=None,
            cost_by_year=year_costs,
            currency=ledger_currency,
            line_item_count=0,
            missing=Missing(
                reason="NOT_APPLICABLE",
                detail=f"rubric {rubric!r} is not applicable to declared activities",
            ),
            allocation_mode=allocation_mode,
        )

    total = sum(year_costs[y] for y in applicable_years if year_costs[y] is not None)
    return RubricLedgerEntry(
        rubric=rubric,
        status="computed",
        total_cost_per_ha=total,
        annual_average_cost_per_ha=total / len(ag_years),
        cost_by_year=year_costs,
        currency=ledger_currency,
        line_item_count=len(items),
        missing=None,
        allocation_mode=allocation_mode,
    )


def _build_year_summaries(
    ag_years: Sequence[int],
    rubric_entries: Mapping[Rubric, RubricLedgerEntry],
    activities_by_year: Mapping[int, list[ActivityDeclaration]],
    items_by_rubric: Mapping[Rubric, list[CostLineItem]],
) -> dict[int, YearCostSummary]:
    """Assemble per-year cost summaries without substituting 0.0 for missing items."""
    summaries: dict[int, YearCostSummary] = {}
    for year in ag_years:
        costs: dict[Rubric, float | None] = {
            r: rubric_entries[r].cost_by_year[year] for r in RUBRICS
        }
        mismatch_details: list[str] = []
        pending_details: list[str] = []
        for rubric in RUBRICS:
            entry = rubric_entries[rubric]
            year_items = [it for it in items_by_rubric[rubric] if it.ag_year == year]
            amort_targets_year = any(
                it.pasture_amortization is not None
                and it.pasture_amortization.amortize
                and year in it.pasture_amortization.target_ag_years
                for it in items_by_rubric[rubric]
            )
            if entry.status == "not_computable" and (year_items or amort_targets_year):
                if entry.missing and entry.missing.detail:
                    mismatch_details.append(entry.missing.detail)
                continue
            # Check whether this rubric has missing items or unmet requirements in year.
            required = any(
                rubric in act.required_rubrics for act in activities_by_year[year]
            )
            if (required or year_items or amort_targets_year) and costs[rubric] is None:
                if entry.missing is not None and entry.missing.detail is not None:
                    pending_details.append(f"{rubric}: {entry.missing.detail}")
                else:
                    pending_details.append(f"{rubric} in ag_year {year}")

        if mismatch_details:
            summaries[year] = YearCostSummary(
                ag_year=year,
                status="not_computable",
                total_cost_per_ha=None,
                rubric_costs_per_ha=costs,
                missing=Missing(
                    reason="NOT_COMPUTABLE",
                    detail="; ".join(dict.fromkeys(mismatch_details)),
                ),
            )
        elif pending_details:
            summaries[year] = YearCostSummary(
                ag_year=year,
                status="incomplete",
                total_cost_per_ha=None,
                rubric_costs_per_ha=costs,
                missing=Missing(
                    reason="MISSING_INPUT",
                    detail="; ".join(dict.fromkeys(pending_details)),
                ),
            )
        else:
            present = [v for v in costs.values() if v is not None]
            year_total = sum(present) if present else 0.0
            summaries[year] = YearCostSummary(
                ag_year=year,
                status="complete",
                total_cost_per_ha=year_total,
                rubric_costs_per_ha=costs,
                missing=None,
            )
    return summaries


def build_input_cost_ledger(
    activities: Sequence[ActivityDeclaration],
    line_items: Sequence[CostLineItem],
    price_book: Sequence[PriceBookEntry] | Mapping[str, PriceBookEntry],
    *,
    currency: str,
    cover_crop_savings_must_be_explicit: bool = True,
    on_mismatch: MismatchPolicy = "raise",
    fertilizer_compositions: Mapping[str, NutrientVector] | None = None,
) -> InputCostLedgerReport:
    """Build the 8-rubric farm input cost ledger report.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Enforces Rev13 §12.2 rules:
    1. Never estimates or invents prices; currency/unit mismatches raise
       ``ValueError`` (default ``on_mismatch="raise"``) or emit
       ``NOT_COMPUTABLE`` (``on_mismatch="not_computable"``).
    2. Any rubric required for a declared activity whose price or quantity is
       unloaded/absent is recorded as ``"pending"`` with typed
       ``Missing(reason="MISSING_INPUT")``, marking ``ledger_status="incomplete"``,
       never ``0.0``.
    3. Fertilizer rubric computes nutrient mass supplied ``(N, P, K, S)`` and
       compares against declared crop harvest nutrient removal
       (``nutrient_balance_kg_ha``), flagging net mining vs surplus without
       fabricating crop nutrient contents.
    4. Crop protection rubric refuses (``ValueError``) assuming unentered
       herbicide/spray savings from cover crops
       (``cover_crop_savings_must_be_explicit=True``).
    5. Pasture establishment/renovation costs concentrate in the declared
       establishment year unless explicitly amortized; harvest/freight scales
       linearly with realized/declared yield of each year.
    """
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency: must be a non-empty string")
    if currency != currency.strip():
        raise ValueError("currency: must not have leading or trailing whitespace")
    if cover_crop_savings_must_be_explicit is not True:
        raise ValueError(
            "crop_protection: cover_crop_savings_must_be_explicit must be True; "
            "unentered herbicide/spray savings from cover crops cannot be assumed"
        )
    if on_mismatch not in ("raise", "not_computable"):
        raise ValueError("on_mismatch: must be 'raise' or 'not_computable'")

    indexed_book = _index_price_book(price_book)
    ag_years, by_year, by_key = _index_activities(activities)
    cross_mismatches = _check_cross_item_units(
        line_items, by_year, by_key, currency, on_mismatch
    )

    items_by_rubric: dict[Rubric, list[CostLineItem]] = {r: [] for r in RUBRICS}
    for item in line_items:
        items_by_rubric[item.rubric].append(item)

    price_book_audit: dict[str, PriceBookEntry] = {}
    rubric_entries: dict[Rubric, RubricLedgerEntry] = {}
    for rubric in RUBRICS:
        rubric_entries[rubric] = _evaluate_rubric(
            rubric=rubric,
            ag_years=ag_years,
            items=items_by_rubric[rubric],
            activities_by_year=by_year,
            activities_by_key=by_key,
            price_book=indexed_book,
            ledger_currency=currency,
            cross_mismatches=cross_mismatches.get(rubric, ()),
            on_mismatch=on_mismatch,
            price_book_audit=price_book_audit,
        )

    year_summaries = _build_year_summaries(
        ag_years, rubric_entries, by_year, items_by_rubric
    )
    nutrient_overall, nutrient_by_year = _build_nutrient_balances(
        ag_years, items_by_rubric["fertilizer"], by_year, fertilizer_compositions
    )

    not_computable = [
        r for r in RUBRICS if rubric_entries[r].status == "not_computable"
    ]
    pending = tuple(r for r in RUBRICS if rubric_entries[r].status == "pending")

    if not_computable:
        details = [
            rubric_entries[r].missing.detail
            for r in not_computable
            if rubric_entries[r].missing and rubric_entries[r].missing.detail
        ]
        ledger_status: LedgerStatus = "not_computable"
        total_cost: float | None = None
        annual_avg: float | None = None
        report_missing: Missing | None = Missing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(dict.fromkeys(details)) or "currency or unit mismatch",
        )
    elif pending:
        details = [
            rubric_entries[r].missing.detail
            for r in pending
            if rubric_entries[r].missing and rubric_entries[r].missing.detail
        ]
        ledger_status = "incomplete"
        total_cost = None
        annual_avg = None
        report_missing = Missing(
            reason="MISSING_INPUT",
            detail="; ".join(dict.fromkeys(details)),
        )
    else:
        computed_totals = [
            rubric_entries[r].total_cost_per_ha
            for r in RUBRICS
            if rubric_entries[r].status == "computed"
            and rubric_entries[r].total_cost_per_ha is not None
        ]
        if not computed_totals and not any(
            rubric_entries[r].status == "computed" for r in RUBRICS
        ):
            ledger_status = "incomplete"
            total_cost = None
            annual_avg = None
            report_missing = Missing(
                reason="MISSING_INPUT",
                detail="no cost rubric was computed for declared activities",
            )
        else:
            ledger_status = "complete"
            total_cost = sum(computed_totals)
            annual_avg = total_cost / len(ag_years)
            report_missing = None

    pasture_mode = (
        rubric_entries["pasture_establishment"].allocation_mode or "not_applicable"
    )
    net_mining = tuple(
        n for n in NUTRIENTS if nutrient_overall[n].status == "net_mining"
    )
    surplus = tuple(n for n in NUTRIENTS if nutrient_overall[n].status == "surplus")

    return InputCostLedgerReport(
        ledger_status=ledger_status,
        currency=currency,
        ag_years=ag_years,
        rubrics=rubric_entries,
        by_year=year_summaries,
        total_cost_per_ha=total_cost,
        annual_average_cost_per_ha=annual_avg,
        pending_rubrics=pending,
        missing=report_missing,
        nutrient_balance_kg_ha=nutrient_overall,
        nutrient_balance_by_year=nutrient_by_year,
        net_mining_nutrients=net_mining,
        surplus_nutrients=surplus,
        pasture_allocation_mode=pasture_mode,
        price_book_audit=price_book_audit,
    )
