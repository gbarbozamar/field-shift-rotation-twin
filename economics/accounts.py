"""Rev13 three-account economic evaluation for crop activities, years, and rotations.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements three strictly separate economic accounts per crop activity,
agricultural year, and full rotation:

1. **Gross margin** (``gross_margin = revenue - direct_costs``):
   Enforces mutual exclusion between ``"gross"`` and ``"net"`` farm-gate price
   bases. A ``"gross"`` price deducts ``(harvest, drying, freight, selling)``
   once each and refuses if any deducted item is already tagged included in
   the price. A ``"net"`` price rejects re-deducting post-harvest selling
   expenses that are already included in the price.
2. **Accounting result** (``accounting_result = gross_margin - structure_cost -
   paid_rent - relevant_depreciation``):
   Stores ``definition_note`` and keeps ``paid_rent`` strictly separate from
   ``own_land_opportunity_cost``; never calls this partial result
   ``net_profit``.
3. **Cash flow** (``cash_flow = collections - payments - investments +
   residual_values`` by date):
   Strictly excludes non-monetary depreciation
   (``non_monetary_depreciation_excluded=True``) and refuses machinery
   depreciation when ``machinery_tariff_includes_depreciation=True``.

Any missing revenue or cost component makes the affected account typed
``Missing(reason="MISSING_INPUT")`` (never ``0.0``), while unaffected accounts
remain computable independently. Zero hardcoded prices or cost rates.
"""

from __future__ import annotations

import math
import numbers
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Annotated, Any, Literal, TypeVar

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from contracts.economic_facts import COST_UNIT, MARGIN_UNIT, PRICE_UNIT, YIELD_UNIT
from contracts.inputs.common import (
    ContractModel,
    IsoDate,
    Missing,
    NonEmptyStr,
    Provenance,
    Value,
)

# ---------------------------------------------------------------------------
# Constants and types (PROPOSED — Blueprint §3.7 Frontier Vision Rev13)
# ---------------------------------------------------------------------------

PriceBasis = Literal["gross", "net"]
PostHarvestItem = Literal["harvest", "drying", "freight", "selling"]
CashFlowKind = Literal["collection", "payment", "investment", "residual_value"]

POST_HARVEST_ITEMS: tuple[PostHarvestItem, ...] = (
    "harvest",
    "drying",
    "freight",
    "selling",
)
PRICE_BASES: tuple[PriceBasis, ...] = ("gross", "net")
CASH_FLOW_KINDS: tuple[CashFlowKind, ...] = (
    "collection",
    "payment",
    "investment",
    "residual_value",
)

DEFAULT_ACCOUNTING_DEFINITION_NOTE = (
    "PROPOSED (Rev13): Partial accounting result equals gross_margin minus "
    "structure_cost, paid_rent, and relevant_depreciation; excludes "
    "own_land_opportunity_cost, income taxes, and financing costs."
)

_FORBIDDEN_PROFIT_LABEL_RE = re.compile(r"\bnet[_\s]+profit\b", re.IGNORECASE)
_ACCOUNTS_SOURCE = "Rev13 economic accounts (PROPOSED)"
_RANGE_NOT_AVAILABLE = Missing(
    reason="NOT_AVAILABLE",
    detail="uncertainty range propagation is not computed by Rev13 economic accounts",
)


class DoubleCountError(ValueError):
    """Raised when an input configuration would double-count an expense or depreciation.

    Subclasses ``ValueError`` so callers guarding either ``DoubleCountError`` or
    ``ValueError`` catch the double-count violation. PROPOSED.
    """


class _DoubleCountSignal(Exception):
    """Internal non-ValueError signal so Pydantic does not wrap DoubleCountError."""


_T = TypeVar("_T")


def _list_to_tuple(value: Any) -> Any:
    """Allow JSON arrays (lists) to validate into strict immutable tuples."""
    if isinstance(value, list):
        return tuple(value)
    return value


StrictTuple = Annotated[tuple[_T, ...], BeforeValidator(_list_to_tuple)]


class _AccountsModel(ContractModel):
    """Strict immutable base model for Rev13 economic accounts. PROPOSED."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    def __init__(self, /, **data: Any) -> None:
        try:
            super().__init__(**data)
        except _DoubleCountSignal as exc:
            raise DoubleCountError(str(exc)) from None

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: Any = None,
        from_attributes: bool | None = None,
        context: Any = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Any:
        try:
            return super().model_validate(
                obj,
                strict=strict,
                extra=extra,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except _DoubleCountSignal as exc:
            raise DoubleCountError(str(exc)) from None

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: Any = None,
        context: Any = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Any:
        try:
            return super().model_validate_json(
                json_data,
                strict=strict,
                extra=extra,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except _DoubleCountSignal as exc:
            raise DoubleCountError(str(exc)) from None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _describe_missing_value(label: str, val: Value) -> str:
    """Format a human-readable description of a missing ``Value``."""
    if val.missing is None:
        raise ValueError(
            f"{label}: value is None without a missing part with its reason (C3.1)"
        )
    text = f"{label} ({val.missing.reason})"
    if val.missing.detail is not None:
        text += f": {val.missing.detail}"
    return text


def _check_value(
    val: Value,
    *,
    label: str,
    allowed_units: tuple[str, ...],
    non_negative: bool = True,
) -> Value:
    """Enforce unit, C3.1 presence/absence, finiteness, and sign on a ``Value``."""
    if val.unit not in allowed_units:
        raise ValueError(
            f"{label}: expected unit in {allowed_units!r}, got {val.unit!r} (C1.1)"
        )
    if (val.value is None) == (val.missing is None):
        raise ValueError(
            f"{label}: a Value must carry either a number or a missing part (C3.1)"
        )
    if val.value is not None:
        if isinstance(val.value, bool) or not isinstance(val.value, numbers.Real):
            raise ValueError(f"{label}: value must be a finite real number")
        if not math.isfinite(val.value):
            raise ValueError(f"{label}: value must be finite")
        if non_negative and val.value < 0:
            raise ValueError(f"{label}: value must not be negative (got {val.value})")
        if val.provenance is None:
            raise ValueError(f"{label}: present value requires provenance (C4.1)")
        if val.source is None and not val.assumption:
            raise ValueError(
                f"{label}: present value requires source or assumption=True (C4.2)"
            )
    return val


def _derived_value(
    number: float,
    *,
    unit: str,
    inputs: Sequence[Value],
    source: str = _ACCOUNTS_SOURCE,
) -> Value:
    """Construct a present derived (or simulated) ``Value`` per C2.2 and C4.3."""
    provenance: Provenance = (
        "SIMULATED" if any(v.provenance == "SIMULATED" for v in inputs) else "DERIVED"
    )
    return Value(
        value=float(number),
        unit=unit,
        provenance=provenance,
        source=source,
        range_missing=_RANGE_NOT_AVAILABLE,
    )


def _missing_input_value(*, unit: str, details: Iterable[str]) -> Value:
    """Construct a typed ``Missing(reason='MISSING_INPUT')`` ``Value``."""
    unique_details = list(dict.fromkeys(d for d in details if d))
    if not unique_details:
        unique_details = ["required economic input is missing"]
    return Value(
        value=None,
        unit=unit,
        missing=Missing(
            reason="MISSING_INPUT",
            detail="; ".join(unique_details),
        ),
    )


def _check_definition_note(note: str) -> str:
    """Ensure ``definition_note`` never labels the partial accounting result net_profit."""
    if _FORBIDDEN_PROFIT_LABEL_RE.search(note):
        raise ValueError(
            "definition_note must never call the partial accounting result 'net_profit'"
        )
    return note


# ---------------------------------------------------------------------------
# Input models (PROPOSED — Blueprint §3.7 Frontier Vision Rev13)
# ---------------------------------------------------------------------------


class PostHarvestDeduction(_AccountsModel):
    """One post-harvest expense line with an explicit price-inclusion tag. PROPOSED."""

    amount: Value
    included_in_price: bool = False

    @model_validator(mode="after")
    def _validate_amount(self) -> PostHarvestDeduction:
        _check_value(
            self.amount,
            label="post_harvest_deduction.amount",
            allowed_units=(COST_UNIT, PRICE_UNIT),
            non_negative=True,
        )
        return self


class ActivitySaleSpec(_AccountsModel):
    """Sale price, yield, and gross/net farm-gate expense specification. PROPOSED.

    Enforces strict mutual exclusion between ``"gross"`` and ``"net"`` farm-gate
    prices:
    - ``"gross"`` deducts ``(harvest, drying, freight, selling)`` once each and
      raises ``DoubleCountError`` if any item is tagged as already included in
      the price.
    - ``"net"`` rejects re-deducting any post-harvest selling expense that is
      already included in the net farm-gate price (``DoubleCountError``).
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        populate_by_name=True,
    )

    price: Value
    yield_: Value = Field(alias="yield")
    price_basis: PriceBasis
    included_in_price: StrictTuple[PostHarvestItem] | None = None
    harvest: Value | PostHarvestDeduction | None = None
    drying: Value | PostHarvestDeduction | None = None
    freight: Value | PostHarvestDeduction | None = None
    selling: Value | PostHarvestDeduction | None = None

    @model_validator(mode="after")
    def _validate_sale_spec(self) -> ActivitySaleSpec:
        _check_value(
            self.price,
            label="sale.price",
            allowed_units=(PRICE_UNIT,),
            non_negative=True,
        )
        _check_value(
            self.yield_,
            label="sale.yield",
            allowed_units=(YIELD_UNIT,),
            non_negative=True,
        )

        included: tuple[PostHarvestItem, ...]
        if self.included_in_price is None:
            included = POST_HARVEST_ITEMS if self.price_basis == "net" else ()
        else:
            if len(self.included_in_price) != len(set(self.included_in_price)):
                raise _DoubleCountSignal(
                    "included_in_price must not list the same post-harvest item twice"
                )
            included = self.included_in_price

        if self.price_basis == "gross" and included:
            raise _DoubleCountSignal(
                "gross price_basis cannot tag post-harvest items as already "
                f"included in price: {included}"
            )
        if self.price_basis == "net" and not included:
            raise ValueError(
                "net price_basis must include at least one post-harvest item in "
                "included_in_price; use 'gross' otherwise"
            )

        for item_name in POST_HARVEST_ITEMS:
            raw = getattr(self, item_name)
            if raw is None:
                continue
            item_included = False
            if isinstance(raw, PostHarvestDeduction):
                val = raw.amount
                item_included = raw.included_in_price
            else:
                val = raw
            _check_value(
                val,
                label=f"sale.{item_name}",
                allowed_units=(COST_UNIT, PRICE_UNIT),
                non_negative=True,
            )
            if self.price_basis == "gross" and item_included:
                raise _DoubleCountSignal(
                    f"gross price_basis refuses deducting '{item_name}' because it "
                    "is tagged already included in price"
                )
            if self.price_basis == "net" and (item_name in included or item_included):
                raise _DoubleCountSignal(
                    f"net price_basis refuses re-deducting '{item_name}' because it "
                    "is already included in the net farm-gate price"
                )

        if self.included_in_price is None:
            object.__setattr__(self, "included_in_price", included)

        return self


class DepreciationSpec(_AccountsModel):
    """Relevant non-monetary depreciation inputs for accounting_result. PROPOSED.

    Refuses providing both ``relevant_depreciation`` and decomposed
    ``(machinery_depreciation, other_depreciation)``. Refuses machinery
    depreciation whenever ``machinery_tariff_includes_depreciation=True``.
    """

    machinery_depreciation: Value | None = None
    other_depreciation: Value | None = None
    relevant_depreciation: Value | None = None
    relevant_includes_machinery: bool = False
    machinery_tariff_includes_depreciation: bool = False

    @model_validator(mode="after")
    def _validate_depreciation(self) -> DepreciationSpec:
        has_parts = (
            self.machinery_depreciation is not None
            or self.other_depreciation is not None
        )
        if self.relevant_depreciation is not None and has_parts:
            raise _DoubleCountSignal(
                "specify either relevant_depreciation or decomposed "
                "(machinery_depreciation / other_depreciation), never both"
            )

        for field_name in (
            "machinery_depreciation",
            "other_depreciation",
            "relevant_depreciation",
        ):
            val = getattr(self, field_name)
            if val is not None:
                _check_value(
                    val,
                    label=f"depreciation.{field_name}",
                    allowed_units=(COST_UNIT, MARGIN_UNIT),
                    non_negative=True,
                )

        if self.machinery_tariff_includes_depreciation:
            if (
                self.machinery_depreciation is not None
                and self.machinery_depreciation.value is not None
                and self.machinery_depreciation.value > 0
            ):
                raise _DoubleCountSignal(
                    "machinery_depreciation cannot be charged when "
                    "machinery_tariff_includes_depreciation=True"
                )
            if (
                self.relevant_depreciation is not None
                and self.relevant_includes_machinery
                and self.relevant_depreciation.value is not None
                and self.relevant_depreciation.value > 0
            ):
                raise _DoubleCountSignal(
                    "relevant_depreciation including machinery cannot be charged "
                    "when machinery_tariff_includes_depreciation=True"
                )
        return self


class CashFlowEvent(_AccountsModel):
    """One dated monetary cash movement. PROPOSED.

    Non-monetary depreciation is strictly excluded from cash flow.
    """

    date: IsoDate
    kind: CashFlowKind
    amount: Value
    description: NonEmptyStr | None = None
    is_non_monetary: bool = False

    @field_validator("kind", mode="before")
    @classmethod
    def _reject_depreciation_kind(cls, raw: Any) -> Any:
        if isinstance(raw, str) and "depreciation" in raw.lower():
            raise _DoubleCountSignal(
                "non-monetary depreciation is strictly excluded from cash_flow"
            )
        return raw

    @model_validator(mode="after")
    def _validate_event(self) -> CashFlowEvent:
        if self.is_non_monetary:
            raise _DoubleCountSignal(
                "non-monetary items (such as depreciation) are strictly excluded "
                "from cash_flow"
            )
        _check_value(
            self.amount,
            label="cash_flow_event.amount",
            allowed_units=(COST_UNIT,),
            non_negative=True,
        )
        return self


def _enforce_tariff_depreciation_guard(
    depreciation: DepreciationSpec | None,
    *,
    tariff_includes: bool,
    context: str,
    in_validator: bool = False,
) -> None:
    """Enforce machinery_tariff_includes_depreciation across nested scopes."""
    if depreciation is None or not tariff_includes:
        return
    exc_cls = _DoubleCountSignal if in_validator else DoubleCountError
    if (
        depreciation.machinery_depreciation is not None
        and depreciation.machinery_depreciation.value is not None
        and depreciation.machinery_depreciation.value > 0
    ):
        raise exc_cls(
            f"{context}: machinery_depreciation refused when "
            "machinery_tariff_includes_depreciation=True"
        )
    if (
        depreciation.relevant_depreciation is not None
        and depreciation.relevant_includes_machinery
        and depreciation.relevant_depreciation.value is not None
        and depreciation.relevant_depreciation.value > 0
    ):
        raise exc_cls(
            f"{context}: relevant_depreciation including machinery refused when "
            "machinery_tariff_includes_depreciation=True"
        )


def _check_cash_flow_exclusion_flag(flag: bool, *, context: str) -> None:
    if not flag:
        raise _DoubleCountSignal(
            f"{context}: non_monetary_depreciation_excluded must be True"
        )


class ActivityAccountInput(_AccountsModel):
    """Inputs for the three accounts of one crop activity. PROPOSED."""

    activity_id: NonEmptyStr
    crop_id: NonEmptyStr
    ag_year: int
    sale: ActivitySaleSpec
    pre_harvest_direct_cost: Value
    structure_cost: Value | None = None
    paid_rent: Value | None = None
    own_land_opportunity_cost: Value | None = None
    depreciation: DepreciationSpec | None = None
    definition_note: NonEmptyStr = DEFAULT_ACCOUNTING_DEFINITION_NOTE
    cash_events: StrictTuple[CashFlowEvent] | None = None
    machinery_tariff_includes_depreciation: bool = False
    non_monetary_depreciation_excluded: bool = True

    @model_validator(mode="after")
    def _validate_activity(self) -> ActivityAccountInput:
        _check_value(
            self.pre_harvest_direct_cost,
            label=f"activity {self.activity_id!r}.pre_harvest_direct_cost",
            allowed_units=(COST_UNIT,),
            non_negative=True,
        )
        for field_name in ("structure_cost", "paid_rent", "own_land_opportunity_cost"):
            val = getattr(self, field_name)
            if val is not None:
                _check_value(
                    val,
                    label=f"activity {self.activity_id!r}.{field_name}",
                    allowed_units=(COST_UNIT,),
                    non_negative=True,
                )
        _check_definition_note(self.definition_note)
        _check_cash_flow_exclusion_flag(
            self.non_monetary_depreciation_excluded,
            context=f"activity {self.activity_id!r}",
        )
        effective_tariff = self.machinery_tariff_includes_depreciation or (
            self.depreciation is not None
            and self.depreciation.machinery_tariff_includes_depreciation
        )
        _enforce_tariff_depreciation_guard(
            self.depreciation,
            tariff_includes=effective_tariff,
            context=f"activity {self.activity_id!r}",
            in_validator=True,
        )
        return self


class AgYearAccountInput(_AccountsModel):
    """Inputs for one agricultural year containing one or more crop activities. PROPOSED."""

    ag_year: int
    activities: StrictTuple[ActivityAccountInput] = Field(min_length=1)
    structure_cost: Value | None = None
    paid_rent: Value | None = None
    own_land_opportunity_cost: Value | None = None
    depreciation: DepreciationSpec | None = None
    definition_note: NonEmptyStr = DEFAULT_ACCOUNTING_DEFINITION_NOTE
    cash_events: StrictTuple[CashFlowEvent] | None = None
    machinery_tariff_includes_depreciation: bool = False
    non_monetary_depreciation_excluded: bool = True

    @model_validator(mode="after")
    def _validate_ag_year(self) -> AgYearAccountInput:
        _check_definition_note(self.definition_note)
        _check_cash_flow_exclusion_flag(
            self.non_monetary_depreciation_excluded,
            context=f"ag_year {self.ag_year}",
        )
        for field_name in ("structure_cost", "paid_rent", "own_land_opportunity_cost"):
            val = getattr(self, field_name)
            if val is not None:
                _check_value(
                    val,
                    label=f"ag_year {self.ag_year}.{field_name}",
                    allowed_units=(COST_UNIT, MARGIN_UNIT),
                    non_negative=True,
                )

        seen_ids: set[str] = set()
        for act in self.activities:
            if act.ag_year != self.ag_year:
                raise ValueError(
                    f"activity {act.activity_id!r}: ag_year {act.ag_year} does "
                    f"not match enclosing agricultural year {self.ag_year}"
                )
            if act.activity_id in seen_ids:
                raise ValueError(
                    f"ag_year {self.ag_year}: duplicate activity_id {act.activity_id!r}"
                )
            seen_ids.add(act.activity_id)

        # Guard against deducting overheads at both year level and activity level.
        for field_name in (
            "structure_cost",
            "paid_rent",
            "own_land_opportunity_cost",
            "depreciation",
        ):
            year_has = getattr(self, field_name) is not None
            act_has = any(getattr(a, field_name) is not None for a in self.activities)
            if year_has and act_has:
                raise _DoubleCountSignal(
                    f"ag_year {self.ag_year}: {field_name} cannot be supplied at "
                    "both the agricultural-year level and the activity level"
                )

        effective_tariff = self.machinery_tariff_includes_depreciation or (
            self.depreciation is not None
            and self.depreciation.machinery_tariff_includes_depreciation
        )
        _enforce_tariff_depreciation_guard(
            self.depreciation,
            tariff_includes=effective_tariff,
            context=f"ag_year {self.ag_year}",
            in_validator=True,
        )
        for act in self.activities:
            _enforce_tariff_depreciation_guard(
                act.depreciation,
                tariff_includes=effective_tariff
                or act.machinery_tariff_includes_depreciation,
                context=f"activity {act.activity_id!r}",
                in_validator=True,
            )
        return self


class RotationAccountInput(_AccountsModel):
    """Inputs for the three accounts of one full crop rotation. PROPOSED."""

    case_id: NonEmptyStr
    field_id: NonEmptyStr
    rotation_id: NonEmptyStr
    currency: Literal["USD"] = "USD"
    years: StrictTuple[AgYearAccountInput] = Field(min_length=1)
    cash_events: StrictTuple[CashFlowEvent] | None = None
    machinery_tariff_includes_depreciation: bool = False
    non_monetary_depreciation_excluded: bool = True
    definition_note: NonEmptyStr = DEFAULT_ACCOUNTING_DEFINITION_NOTE

    @model_validator(mode="after")
    def _validate_rotation(self) -> RotationAccountInput:
        _check_definition_note(self.definition_note)
        _check_cash_flow_exclusion_flag(
            self.non_monetary_depreciation_excluded,
            context=f"rotation {self.rotation_id!r}",
        )
        ag_years = [y.ag_year for y in self.years]
        if len(ag_years) != len(set(ag_years)):
            raise ValueError("rotation.years: duplicate ag_year entries are forbidden")

        seen_activity_ids: set[str] = set()
        for year in self.years:
            _enforce_tariff_depreciation_guard(
                year.depreciation,
                tariff_includes=(
                    self.machinery_tariff_includes_depreciation
                    or year.machinery_tariff_includes_depreciation
                ),
                context=f"ag_year {year.ag_year}",
                in_validator=True,
            )
            for act in year.activities:
                if act.activity_id in seen_activity_ids:
                    raise ValueError(
                        f"rotation {self.rotation_id!r}: duplicate activity_id "
                        f"{act.activity_id!r}"
                    )
                seen_activity_ids.add(act.activity_id)
                _enforce_tariff_depreciation_guard(
                    act.depreciation,
                    tariff_includes=(
                        self.machinery_tariff_includes_depreciation
                        or year.machinery_tariff_includes_depreciation
                        or act.machinery_tariff_includes_depreciation
                    ),
                    context=f"activity {act.activity_id!r}",
                    in_validator=True,
                )
        return self


# ---------------------------------------------------------------------------
# Output models (PROPOSED — Blueprint §3.7 Frontier Vision Rev13)
# ---------------------------------------------------------------------------


class GrossMarginAccount(_AccountsModel):
    """Account 1 (crop activity): gross_margin = revenue - direct_costs. PROPOSED."""

    revenue: Value
    direct_costs: Value
    gross_margin: Value
    price_basis: PriceBasis
    deducted_post_harvest_items: StrictTuple[PostHarvestItem]
    included_in_price: StrictTuple[PostHarvestItem]


class AggregateGrossMarginAccount(_AccountsModel):
    """Account 1 (year or rotation aggregate): gross_margin = revenue - direct_costs. PROPOSED."""

    revenue: Value
    direct_costs: Value
    gross_margin: Value
    price_bases_present: StrictTuple[PriceBasis]


class AccountingResultAccount(_AccountsModel):
    """Account 2: gross_margin - structure_cost - paid_rent - relevant_depreciation.

    Keeps ``paid_rent`` strictly separate from ``own_land_opportunity_cost`` and
    stores ``definition_note`` (never naming the partial margin ``net_profit``).
    PROPOSED.
    """

    gross_margin: Value
    structure_cost: Value
    paid_rent: Value
    own_land_opportunity_cost: Value
    relevant_depreciation: Value
    accounting_result: Value
    definition_note: NonEmptyStr
    machinery_tariff_includes_depreciation: bool


class DatedCashFlow(_AccountsModel):
    """Cash flow movements and cumulative balance for one calendar date. PROPOSED."""

    date: IsoDate
    collections: Value
    payments: Value
    investments: Value
    residual_values: Value
    net_cash_flow: Value
    cumulative_cash_flow: Value


class CashFlowAccount(_AccountsModel):
    """Account 3: collections - payments - investments + residual_values by date.

    Strictly excludes non-monetary depreciation. PROPOSED.
    """

    collections: Value
    payments: Value
    investments: Value
    residual_values: Value
    cash_flow: Value
    by_date: StrictTuple[DatedCashFlow]
    non_monetary_depreciation_excluded: Literal[True] = True
    machinery_tariff_includes_depreciation: bool


class ActivityAccountResult(_AccountsModel):
    """Three strictly separate Rev13 economic accounts for one crop activity. PROPOSED."""

    activity_id: NonEmptyStr
    crop_id: NonEmptyStr
    ag_year: int
    gross_margin_account: GrossMarginAccount
    accounting_result_account: AccountingResultAccount
    cash_flow_account: CashFlowAccount


class AgYearAccountResult(_AccountsModel):
    """Three strictly separate Rev13 economic accounts for one agricultural year. PROPOSED."""

    ag_year: int
    activities: StrictTuple[ActivityAccountResult]
    gross_margin_account: AggregateGrossMarginAccount
    accounting_result_account: AccountingResultAccount
    cash_flow_account: CashFlowAccount


class AnnualAverageAccounts(_AccountsModel):
    """Per-agricultural-year averages across a full rotation (USD ha-1 yr-1). PROPOSED."""

    years_count: int
    gross_margin: Value
    accounting_result: Value
    cash_flow: Value
    definition_note: NonEmptyStr


class EconomicAccountsSummary(_AccountsModel):
    """Complete Rev13 economic summary for one rotation, by activity, year, and total.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    case_id: NonEmptyStr
    field_id: NonEmptyStr
    rotation_id: NonEmptyStr
    currency: Literal["USD"]
    years_count: int
    activities: StrictTuple[ActivityAccountResult]
    by_year: StrictTuple[AgYearAccountResult]
    gross_margin_account: AggregateGrossMarginAccount
    accounting_result_account: AccountingResultAccount
    cash_flow_account: CashFlowAccount
    annual_average: AnnualAverageAccounts
    definition_note: NonEmptyStr
    non_monetary_depreciation_excluded: Literal[True] = True
    machinery_tariff_includes_depreciation: bool
    accounts_kept_strictly_separate: Literal[True] = True


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------


def _sum_values(
    values: Sequence[Value],
    *,
    unit: str,
    missing_label: str,
) -> Value:
    """Sum present ``Value`` items, or return ``Missing(reason='MISSING_INPUT')``."""
    missing_details = [
        _describe_missing_value(missing_label, val)
        for val in values
        if val.value is None
    ]
    if missing_details:
        return _missing_input_value(unit=unit, details=missing_details)
    total = sum(float(val.value) for val in values if val.value is not None)
    return _derived_value(total, unit=unit, inputs=values)


def _resolve_depreciation(
    spec: DepreciationSpec | None,
    *,
    unit: str,
    tariff_includes_machinery: bool,
    context: str,
) -> Value:
    """Compute relevant non-monetary depreciation for Account 2 (accounting_result)."""
    if spec is None:
        return _missing_input_value(
            unit=unit,
            details=[f"{context}: relevant depreciation was not provided"],
        )

    effective_tariff = (
        tariff_includes_machinery or spec.machinery_tariff_includes_depreciation
    )
    _enforce_tariff_depreciation_guard(
        spec,
        tariff_includes=effective_tariff,
        context=context,
    )

    if spec.relevant_depreciation is not None:
        if spec.relevant_depreciation.value is None:
            return _missing_input_value(
                unit=unit,
                details=[
                    _describe_missing_value(
                        f"{context}.relevant_depreciation",
                        spec.relevant_depreciation,
                    )
                ],
            )
        return _derived_value(
            float(spec.relevant_depreciation.value),
            unit=unit,
            inputs=[spec.relevant_depreciation],
        )

    missing_details: list[str] = []
    contributing: list[Value] = []
    total = 0.0

    if not effective_tariff:
        if spec.machinery_depreciation is None:
            missing_details.append(
                f"{context}: machinery_depreciation was not provided"
            )
        elif spec.machinery_depreciation.value is None:
            missing_details.append(
                _describe_missing_value(
                    f"{context}.machinery_depreciation",
                    spec.machinery_depreciation,
                )
            )
        else:
            total += float(spec.machinery_depreciation.value)
            contributing.append(spec.machinery_depreciation)
    elif (
        spec.machinery_depreciation is not None
        and spec.machinery_depreciation.value is not None
    ):
        # Allowed only when 0.0 (tariff already covers machinery depreciation).
        contributing.append(spec.machinery_depreciation)

    if spec.other_depreciation is None:
        missing_details.append(f"{context}: other_depreciation was not provided")
    elif spec.other_depreciation.value is None:
        missing_details.append(
            _describe_missing_value(
                f"{context}.other_depreciation",
                spec.other_depreciation,
            )
        )
    else:
        total += float(spec.other_depreciation.value)
        contributing.append(spec.other_depreciation)

    if missing_details:
        return _missing_input_value(unit=unit, details=missing_details)

    return _derived_value(total, unit=unit, inputs=contributing)


def _compute_gross_margin_account(activity: ActivityAccountInput) -> GrossMarginAccount:
    """Compute Account 1 (gross_margin) for one crop activity."""
    sale = activity.sale
    included = sale.included_in_price or ()
    deducted_items = tuple(item for item in POST_HARVEST_ITEMS if item not in included)

    # Revenue = price * yield
    rev_missing: list[str] = []
    if sale.price.value is None:
        rev_missing.append(
            _describe_missing_value(
                f"activity {activity.activity_id!r}.sale.price", sale.price
            )
        )
    if sale.yield_.value is None:
        rev_missing.append(
            _describe_missing_value(
                f"activity {activity.activity_id!r}.sale.yield", sale.yield_
            )
        )
    if rev_missing:
        revenue = _missing_input_value(unit=COST_UNIT, details=rev_missing)
    else:
        revenue = _derived_value(
            float(sale.price.value) * float(sale.yield_.value),
            unit=COST_UNIT,
            inputs=[sale.price, sale.yield_],
        )

    # Direct costs = pre_harvest_direct_cost + deducted post-harvest items
    dc_missing: list[str] = []
    dc_inputs: list[Value] = []
    dc_total = 0.0

    if activity.pre_harvest_direct_cost.value is None:
        dc_missing.append(
            _describe_missing_value(
                f"activity {activity.activity_id!r}.pre_harvest_direct_cost",
                activity.pre_harvest_direct_cost,
            )
        )
    else:
        dc_total += float(activity.pre_harvest_direct_cost.value)
        dc_inputs.append(activity.pre_harvest_direct_cost)

    for item_name in deducted_items:
        raw = getattr(sale, item_name)
        if raw is None:
            dc_missing.append(
                f"activity {activity.activity_id!r}.sale.{item_name} was not provided"
            )
            continue
        val = raw.amount if isinstance(raw, PostHarvestDeduction) else raw
        if val.value is None:
            dc_missing.append(
                _describe_missing_value(
                    f"activity {activity.activity_id!r}.sale.{item_name}", val
                )
            )
            continue
        if val.unit == COST_UNIT:
            dc_total += float(val.value)
            dc_inputs.append(val)
        elif val.unit == PRICE_UNIT:
            if sale.yield_.value is None:
                dc_missing.append(
                    f"activity {activity.activity_id!r}.sale.{item_name} in "
                    f"{PRICE_UNIT!r} requires yield "
                    f"({_describe_missing_value('sale.yield', sale.yield_)})"
                )
            else:
                dc_total += float(val.value) * float(sale.yield_.value)
                dc_inputs.extend([val, sale.yield_])
        else:  # pragma: no cover - guarded by ActivitySaleSpec validator
            raise ValueError(f"unsupported unit {val.unit!r} for {item_name}")

    if dc_missing:
        direct_costs = _missing_input_value(unit=COST_UNIT, details=dc_missing)
    else:
        direct_costs = _derived_value(dc_total, unit=COST_UNIT, inputs=dc_inputs)

    # Gross margin = revenue - direct_costs
    gm_missing: list[str] = []
    if revenue.value is None:
        gm_missing.append(_describe_missing_value("revenue", revenue))
    if direct_costs.value is None:
        gm_missing.append(_describe_missing_value("direct_costs", direct_costs))
    if gm_missing:
        gross_margin = _missing_input_value(unit=COST_UNIT, details=gm_missing)
    else:
        gross_margin = _derived_value(
            float(revenue.value) - float(direct_costs.value),
            unit=COST_UNIT,
            inputs=[revenue, direct_costs],
        )

    return GrossMarginAccount(
        revenue=revenue,
        direct_costs=direct_costs,
        gross_margin=gross_margin,
        price_basis=sale.price_basis,
        deducted_post_harvest_items=deducted_items,
        included_in_price=included,
    )


def _compute_accounting_result_account(
    *,
    gross_margin: Value,
    structure_cost: Value | None,
    paid_rent: Value | None,
    own_land_opportunity_cost: Value | None,
    depreciation: DepreciationSpec | None,
    definition_note: str,
    tariff_includes_machinery: bool,
    unit: str,
    context: str,
) -> AccountingResultAccount:
    """Compute Account 2: gross_margin - structure_cost - paid_rent - relevant_depreciation."""
    _check_definition_note(definition_note)

    if structure_cost is None:
        resolved_structure = _missing_input_value(
            unit=unit,
            details=[f"{context}: structure_cost was not provided"],
        )
    elif structure_cost.value is None:
        resolved_structure = _missing_input_value(
            unit=unit,
            details=[
                _describe_missing_value(f"{context}.structure_cost", structure_cost)
            ],
        )
    else:
        resolved_structure = _derived_value(
            float(structure_cost.value),
            unit=unit,
            inputs=[structure_cost],
        )

    if paid_rent is None:
        resolved_paid_rent = _missing_input_value(
            unit=unit,
            details=[f"{context}: paid_rent was not provided"],
        )
    elif paid_rent.value is None:
        resolved_paid_rent = _missing_input_value(
            unit=unit,
            details=[_describe_missing_value(f"{context}.paid_rent", paid_rent)],
        )
    else:
        resolved_paid_rent = _derived_value(
            float(paid_rent.value),
            unit=unit,
            inputs=[paid_rent],
        )

    if own_land_opportunity_cost is None:
        resolved_opp = _missing_input_value(
            unit=unit,
            details=[f"{context}: own_land_opportunity_cost was not provided"],
        )
    elif own_land_opportunity_cost.value is None:
        resolved_opp = _missing_input_value(
            unit=unit,
            details=[
                _describe_missing_value(
                    f"{context}.own_land_opportunity_cost",
                    own_land_opportunity_cost,
                )
            ],
        )
    else:
        resolved_opp = _derived_value(
            float(own_land_opportunity_cost.value),
            unit=unit,
            inputs=[own_land_opportunity_cost],
        )

    resolved_depreciation = _resolve_depreciation(
        depreciation,
        unit=unit,
        tariff_includes_machinery=tariff_includes_machinery,
        context=context,
    )

    missing_details: list[str] = []
    for name, val in (
        ("gross_margin", gross_margin),
        ("structure_cost", resolved_structure),
        ("paid_rent", resolved_paid_rent),
        ("relevant_depreciation", resolved_depreciation),
    ):
        if val.value is None:
            missing_details.append(_describe_missing_value(name, val))

    if missing_details:
        accounting_result = _missing_input_value(unit=unit, details=missing_details)
    else:
        accounting_result = _derived_value(
            float(gross_margin.value)
            - float(resolved_structure.value)
            - float(resolved_paid_rent.value)
            - float(resolved_depreciation.value),
            unit=unit,
            inputs=[
                gross_margin,
                resolved_structure,
                resolved_paid_rent,
                resolved_depreciation,
            ],
        )

    return AccountingResultAccount(
        gross_margin=gross_margin,
        structure_cost=resolved_structure,
        paid_rent=resolved_paid_rent,
        own_land_opportunity_cost=resolved_opp,
        relevant_depreciation=resolved_depreciation,
        accounting_result=accounting_result,
        definition_note=definition_note,
        machinery_tariff_includes_depreciation=tariff_includes_machinery,
    )


def _compute_cash_flow_account(
    events: Sequence[CashFlowEvent] | None,
    *,
    unit: str,
    tariff_includes_machinery: bool,
    context: str,
    missing_override_details: Sequence[str] = (),
) -> CashFlowAccount:
    """Compute Account 3: collections - payments - investments + residual_values by date."""
    if missing_override_details:
        missing_val = _missing_input_value(unit=unit, details=missing_override_details)
        return CashFlowAccount(
            collections=missing_val,
            payments=missing_val,
            investments=missing_val,
            residual_values=missing_val,
            cash_flow=missing_val,
            by_date=(),
            non_monetary_depreciation_excluded=True,
            machinery_tariff_includes_depreciation=tariff_includes_machinery,
        )

    if events is None or len(events) == 0:
        missing_val = _missing_input_value(
            unit=unit,
            details=[f"{context}: cash_flow events were not provided"],
        )
        return CashFlowAccount(
            collections=missing_val,
            payments=missing_val,
            investments=missing_val,
            residual_values=missing_val,
            cash_flow=missing_val,
            by_date=(),
            non_monetary_depreciation_excluded=True,
            machinery_tariff_includes_depreciation=tariff_includes_machinery,
        )

    grouped: dict[Any, dict[CashFlowKind, list[Value]]] = defaultdict(
        lambda: {kind: [] for kind in CASH_FLOW_KINDS}
    )
    for event in events:
        if event.is_non_monetary:
            raise DoubleCountError(
                f"{context}: non-monetary items are strictly excluded from cash_flow"
            )
        grouped[event.date][event.kind].append(event.amount)

    dated_rows: list[DatedCashFlow] = []
    running_total = 0.0
    running_missing: list[str] = []

    all_by_kind: dict[CashFlowKind, list[Value]] = {
        kind: [] for kind in CASH_FLOW_KINDS
    }

    for date in sorted(grouped):
        buckets = grouped[date]
        for kind in CASH_FLOW_KINDS:
            all_by_kind[kind].extend(buckets[kind])

        def _bucket_sum(
            kind_name: CashFlowKind,
            *,
            day_buckets: dict[CashFlowKind, list[Value]] = buckets,
            day_date: Any = date,
        ) -> Value:
            items = day_buckets[kind_name]
            if not items:
                return _derived_value(0.0, unit=unit, inputs=())
            return _sum_values(
                items,
                unit=unit,
                missing_label=f"{context}.cash_flow[{day_date}].{kind_name}",
            )

        col = _bucket_sum("collection")
        pay = _bucket_sum("payment")
        inv = _bucket_sum("investment")
        res = _bucket_sum("residual_value")

        date_missing: list[str] = []
        for val in (col, pay, inv, res):
            if val.value is None:
                date_missing.append(_describe_missing_value("cash_flow", val))

        if date_missing:
            net = _missing_input_value(unit=unit, details=date_missing)
            running_missing.extend(date_missing)
            cum = _missing_input_value(unit=unit, details=running_missing)
        else:
            net_val = (
                float(col.value)
                - float(pay.value)
                - float(inv.value)
                + float(res.value)
            )
            net = _derived_value(net_val, unit=unit, inputs=[col, pay, inv, res])
            if running_missing:
                cum = _missing_input_value(unit=unit, details=running_missing)
            else:
                running_total += net_val
                cum = _derived_value(
                    running_total,
                    unit=unit,
                    inputs=[v for k in CASH_FLOW_KINDS for v in all_by_kind[k]],
                )

        dated_rows.append(
            DatedCashFlow(
                date=date,
                collections=col,
                payments=pay,
                investments=inv,
                residual_values=res,
                net_cash_flow=net,
                cumulative_cash_flow=cum,
            )
        )

    def _total_kind(kind_name: CashFlowKind) -> Value:
        items = all_by_kind[kind_name]
        if not items:
            return _derived_value(0.0, unit=unit, inputs=())
        return _sum_values(
            items,
            unit=unit,
            missing_label=f"{context}.cash_flow.{kind_name}",
        )

    tot_col = _total_kind("collection")
    tot_pay = _total_kind("payment")
    tot_inv = _total_kind("investment")
    tot_res = _total_kind("residual_value")

    if running_missing:
        total_cf = _missing_input_value(unit=unit, details=running_missing)
    else:
        total_cf = _derived_value(
            float(tot_col.value)
            - float(tot_pay.value)
            - float(tot_inv.value)
            + float(tot_res.value),
            unit=unit,
            inputs=[tot_col, tot_pay, tot_inv, tot_res],
        )

    return CashFlowAccount(
        collections=tot_col,
        payments=tot_pay,
        investments=tot_inv,
        residual_values=tot_res,
        cash_flow=total_cf,
        by_date=tuple(dated_rows),
        non_monetary_depreciation_excluded=True,
        machinery_tariff_includes_depreciation=tariff_includes_machinery,
    )


def _normalize_to_unit(val: Value, *, target_unit: str) -> Value:
    """Adjust unit metadata between USD ha-1 and USD ha-1 yr-1 when value is per year."""
    if val.unit == target_unit:
        return val
    if val.value is None:
        return Value(value=None, unit=target_unit, missing=val.missing)
    return Value(
        value=val.value,
        unit=target_unit,
        range=val.range,
        range_missing=val.range_missing,
        provenance=val.provenance,
        source=val.source,
        assumption=val.assumption,
    )


# ---------------------------------------------------------------------------
# Public API (PROPOSED — Blueprint §3.7 Frontier Vision Rev13)
# ---------------------------------------------------------------------------


def compute_activity_accounts(
    activity: ActivityAccountInput,
    *,
    machinery_tariff_includes_depreciation: bool = False,
) -> ActivityAccountResult:
    """Compute the 3 strictly separate Rev13 accounts for one crop activity. PROPOSED."""
    effective_tariff = (
        machinery_tariff_includes_depreciation
        or activity.machinery_tariff_includes_depreciation
        or (
            activity.depreciation is not None
            and activity.depreciation.machinery_tariff_includes_depreciation
        )
    )
    _enforce_tariff_depreciation_guard(
        activity.depreciation,
        tariff_includes=effective_tariff,
        context=f"activity {activity.activity_id!r}",
    )

    gm_account = _compute_gross_margin_account(activity)
    acc_account = _compute_accounting_result_account(
        gross_margin=gm_account.gross_margin,
        structure_cost=activity.structure_cost,
        paid_rent=activity.paid_rent,
        own_land_opportunity_cost=activity.own_land_opportunity_cost,
        depreciation=activity.depreciation,
        definition_note=activity.definition_note,
        tariff_includes_machinery=effective_tariff,
        unit=COST_UNIT,
        context=f"activity {activity.activity_id!r}",
    )
    cf_account = _compute_cash_flow_account(
        activity.cash_events,
        unit=COST_UNIT,
        tariff_includes_machinery=effective_tariff,
        context=f"activity {activity.activity_id!r}",
    )

    return ActivityAccountResult(
        activity_id=activity.activity_id,
        crop_id=activity.crop_id,
        ag_year=activity.ag_year,
        gross_margin_account=gm_account,
        accounting_result_account=acc_account,
        cash_flow_account=cf_account,
    )


def compute_ag_year_accounts(
    year: AgYearAccountInput,
    *,
    machinery_tariff_includes_depreciation: bool = False,
) -> AgYearAccountResult:
    """Compute the 3 strictly separate Rev13 accounts for one agricultural year. PROPOSED."""
    effective_tariff = (
        machinery_tariff_includes_depreciation
        or year.machinery_tariff_includes_depreciation
        or (
            year.depreciation is not None
            and year.depreciation.machinery_tariff_includes_depreciation
        )
    )
    _enforce_tariff_depreciation_guard(
        year.depreciation,
        tariff_includes=effective_tariff,
        context=f"ag_year {year.ag_year}",
    )

    act_results = tuple(
        compute_activity_accounts(
            act,
            machinery_tariff_includes_depreciation=effective_tariff,
        )
        for act in year.activities
    )

    revenues = [a.gross_margin_account.revenue for a in act_results]
    direct_costs_list = [a.gross_margin_account.direct_costs for a in act_results]
    gross_margins = [a.gross_margin_account.gross_margin for a in act_results]

    year_revenue = _sum_values(
        revenues,
        unit=MARGIN_UNIT,
        missing_label=f"ag_year {year.ag_year}.revenue",
    )
    year_direct_costs = _sum_values(
        direct_costs_list,
        unit=MARGIN_UNIT,
        missing_label=f"ag_year {year.ag_year}.direct_costs",
    )
    year_gross_margin = _sum_values(
        gross_margins,
        unit=MARGIN_UNIT,
        missing_label=f"ag_year {year.ag_year}.gross_margin",
    )

    bases = tuple(
        dict.fromkeys(a.gross_margin_account.price_basis for a in act_results)
    )
    year_gm_account = AggregateGrossMarginAccount(
        revenue=year_revenue,
        direct_costs=year_direct_costs,
        gross_margin=year_gross_margin,
        price_bases_present=bases,
    )

    # Account 2: either supplied at year level or aggregated from activities.
    has_year_overheads = any(
        getattr(year, attr) is not None
        for attr in (
            "structure_cost",
            "paid_rent",
            "own_land_opportunity_cost",
            "depreciation",
        )
    )
    has_act_overheads = any(
        getattr(act, attr) is not None
        for act in year.activities
        for attr in (
            "structure_cost",
            "paid_rent",
            "own_land_opportunity_cost",
            "depreciation",
        )
    )

    if has_year_overheads or not has_act_overheads:
        year_acc_account = _compute_accounting_result_account(
            gross_margin=year_gross_margin,
            structure_cost=year.structure_cost,
            paid_rent=year.paid_rent,
            own_land_opportunity_cost=year.own_land_opportunity_cost,
            depreciation=year.depreciation,
            definition_note=year.definition_note,
            tariff_includes_machinery=effective_tariff,
            unit=MARGIN_UNIT,
            context=f"ag_year {year.ag_year}",
        )
    else:
        year_structure = _sum_values(
            [a.accounting_result_account.structure_cost for a in act_results],
            unit=MARGIN_UNIT,
            missing_label=f"ag_year {year.ag_year}.structure_cost",
        )
        year_rent = _sum_values(
            [a.accounting_result_account.paid_rent for a in act_results],
            unit=MARGIN_UNIT,
            missing_label=f"ag_year {year.ag_year}.paid_rent",
        )
        year_opp = _sum_values(
            [
                a.accounting_result_account.own_land_opportunity_cost
                for a in act_results
            ],
            unit=MARGIN_UNIT,
            missing_label=f"ag_year {year.ag_year}.own_land_opportunity_cost",
        )
        year_depr = _sum_values(
            [a.accounting_result_account.relevant_depreciation for a in act_results],
            unit=MARGIN_UNIT,
            missing_label=f"ag_year {year.ag_year}.relevant_depreciation",
        )
        year_acc_res = _sum_values(
            [a.accounting_result_account.accounting_result for a in act_results],
            unit=MARGIN_UNIT,
            missing_label=f"ag_year {year.ag_year}.accounting_result",
        )
        year_acc_account = AccountingResultAccount(
            gross_margin=year_gross_margin,
            structure_cost=year_structure,
            paid_rent=year_rent,
            own_land_opportunity_cost=year_opp,
            relevant_depreciation=year_depr,
            accounting_result=year_acc_res,
            definition_note=year.definition_note,
            machinery_tariff_includes_depreciation=effective_tariff,
        )

    # Account 3: merge activity-level and year-level dated cash events.
    combined_events: list[CashFlowEvent] = []
    for act in year.activities:
        if act.cash_events:
            combined_events.extend(act.cash_events)
    if year.cash_events:
        combined_events.extend(year.cash_events)

    # If any activity supplied cash events while another omitted them (None), and no
    # year-level cash_events override exists, report missing activity cash flow.
    missing_cf_details: list[str] = []
    if year.cash_events is None:
        acts_with_cf = [a for a in year.activities if a.cash_events is not None]
        if acts_with_cf and len(acts_with_cf) != len(year.activities):
            for a in year.activities:
                if a.cash_events is None:
                    missing_cf_details.append(
                        f"activity {a.activity_id!r}: cash_events were not provided"
                    )

    year_cf_account = _compute_cash_flow_account(
        combined_events if combined_events else None,
        unit=MARGIN_UNIT,
        tariff_includes_machinery=effective_tariff,
        context=f"ag_year {year.ag_year}",
        missing_override_details=missing_cf_details,
    )

    return AgYearAccountResult(
        ag_year=year.ag_year,
        activities=act_results,
        gross_margin_account=year_gm_account,
        accounting_result_account=year_acc_account,
        cash_flow_account=year_cf_account,
    )


def compute_rotation_accounts(
    rotation: RotationAccountInput,
) -> EconomicAccountsSummary:
    """Compute the 3 strictly separate Rev13 accounts for one full rotation. PROPOSED."""
    tariff_flag = rotation.machinery_tariff_includes_depreciation
    year_results = tuple(
        compute_ag_year_accounts(
            year,
            machinery_tariff_includes_depreciation=tariff_flag,
        )
        for year in rotation.years
    )
    all_activities = tuple(
        act for year_res in year_results for act in year_res.activities
    )
    years_count = len(year_results)

    # 1. Rotation total Gross Margin (USD ha-1)
    rot_rev = _sum_values(
        [yr.gross_margin_account.revenue for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.revenue",
    )
    rot_dc = _sum_values(
        [yr.gross_margin_account.direct_costs for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.direct_costs",
    )
    rot_gm = _sum_values(
        [yr.gross_margin_account.gross_margin for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.gross_margin",
    )
    bases = tuple(
        dict.fromkeys(
            basis
            for yr in year_results
            for basis in yr.gross_margin_account.price_bases_present
        )
    )
    rot_gm_account = AggregateGrossMarginAccount(
        revenue=rot_rev,
        direct_costs=rot_dc,
        gross_margin=rot_gm,
        price_bases_present=bases,
    )

    # 2. Rotation total Accounting Result (USD ha-1)
    rot_struct = _sum_values(
        [yr.accounting_result_account.structure_cost for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.structure_cost",
    )
    rot_rent = _sum_values(
        [yr.accounting_result_account.paid_rent for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.paid_rent",
    )
    rot_opp = _sum_values(
        [yr.accounting_result_account.own_land_opportunity_cost for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.own_land_opportunity_cost",
    )
    rot_depr = _sum_values(
        [yr.accounting_result_account.relevant_depreciation for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.relevant_depreciation",
    )
    rot_acc = _sum_values(
        [yr.accounting_result_account.accounting_result for yr in year_results],
        unit=COST_UNIT,
        missing_label=f"rotation {rotation.rotation_id!r}.accounting_result",
    )
    any_tariff = tariff_flag or any(
        yr.accounting_result_account.machinery_tariff_includes_depreciation
        for yr in year_results
    )
    rot_acc_account = AccountingResultAccount(
        gross_margin=rot_gm,
        structure_cost=rot_struct,
        paid_rent=rot_rent,
        own_land_opportunity_cost=rot_opp,
        relevant_depreciation=rot_depr,
        accounting_result=rot_acc,
        definition_note=rotation.definition_note,
        machinery_tariff_includes_depreciation=any_tariff,
    )

    # 3. Rotation total Cash Flow (USD ha-1) by date across all years + rotation events
    rot_events: list[CashFlowEvent] = []
    for year in rotation.years:
        for act in year.activities:
            if act.cash_events:
                rot_events.extend(act.cash_events)
        if year.cash_events:
            rot_events.extend(year.cash_events)
    if rotation.cash_events:
        rot_events.extend(rotation.cash_events)

    missing_cf_details: list[str] = []
    any_year_has_cf = any(
        yr.cash_events is not None
        or any(act.cash_events is not None for act in yr.activities)
        for yr in rotation.years
    )
    if rotation.cash_events is None or any_year_has_cf:
        for yr in year_results:
            if yr.cash_flow_account.cash_flow.value is None:
                missing_cf_details.append(
                    _describe_missing_value(
                        f"ag_year {yr.ag_year}.cash_flow",
                        yr.cash_flow_account.cash_flow,
                    )
                )

    rot_cf_account = _compute_cash_flow_account(
        rot_events if rot_events else None,
        unit=COST_UNIT,
        tariff_includes_machinery=any_tariff,
        context=f"rotation {rotation.rotation_id!r}",
        missing_override_details=missing_cf_details,
    )

    def _annualize(total_val: Value) -> Value:
        if total_val.value is None:
            return _normalize_to_unit(total_val, target_unit=MARGIN_UNIT)
        return _derived_value(
            float(total_val.value) / years_count,
            unit=MARGIN_UNIT,
            inputs=[total_val],
        )

    annual_avg = AnnualAverageAccounts(
        years_count=years_count,
        gross_margin=_annualize(rot_gm),
        accounting_result=_annualize(rot_acc),
        cash_flow=_annualize(rot_cf_account.cash_flow),
        definition_note=rotation.definition_note,
    )

    return EconomicAccountsSummary(
        case_id=rotation.case_id,
        field_id=rotation.field_id,
        rotation_id=rotation.rotation_id,
        currency=rotation.currency,
        years_count=years_count,
        activities=all_activities,
        by_year=year_results,
        gross_margin_account=rot_gm_account,
        accounting_result_account=rot_acc_account,
        cash_flow_account=rot_cf_account,
        annual_average=annual_avg,
        definition_note=rotation.definition_note,
        non_monetary_depreciation_excluded=True,
        machinery_tariff_includes_depreciation=any_tariff,
        accounts_kept_strictly_separate=True,
    )
