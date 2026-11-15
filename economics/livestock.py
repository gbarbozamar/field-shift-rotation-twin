"""Simple forage-to-beef economic evaluator for livestock enterprises.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
References: ``27_PLAN_DE_FRONTERA.md`` §12.3, §13 and
``28_PLAN_INTEGRADO_REV13.md`` §4.

This module is standalone and pure: no network call, no file access, no clock,
no parameter defaults, and zero default utilization or feed-conversion
coefficients. Missing livestock inputs never collapse to ``0.0`` margin and
beef yield is never inferred from water balance or botanical mix alone.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)

from contracts.economic_facts import MARGIN_UNIT
from contracts.inputs.common import Missing, NonEmptyStr

__all__ = [
    "FORAGE_STATUS_DECLARED",
    "FORAGE_STATUS_HYPOTHESIS_UNVALIDATED",
    "PASTURE_INCOMPLETE_DETAIL",
    "PROPOSED_STATUS",
    "BuyFattenSellEnterprise",
    "ForageModelStatus",
    "ForageOption",
    "LivestockEnterprise",
    "LivestockEvaluation",
    "LivestockScheme",
    "OperatingCostItem",
    "OwnProductionEnterprise",
    "WeightBasis",
    "evaluate_livestock_enterprise",
]

PROPOSED_STATUS = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
PASTURE_INCOMPLETE_DETAIL = "pasture without livestock module is incomplete"
FORAGE_STATUS_DECLARED = "DECLARED"
FORAGE_STATUS_HYPOTHESIS_UNVALIDATED = "HYPOTHESIS_UNVALIDATED"

WeightBasis = Literal["liveweight", "carcass"]
LivestockScheme = Literal["own_production", "buy_fatten_sell"]
ForageOption = Literal["declared_pasture", "water_dependent_annual"]
ForageModelStatus = Literal["DECLARED", "HYPOTHESIS_UNVALIDATED"]

_WEIGHT_BASES: tuple[str, ...] = ("liveweight", "carcass")
_FORAGE_OPTIONS: tuple[str, ...] = ("declared_pasture", "water_dependent_annual")


def _check_finite_real(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{what}: expected a real number")  # noqa: TRY004
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what}: expected a finite number")
    return number


def _check_non_negative(value: float, what: str) -> float:
    number = _check_finite_real(value, what)
    if number < 0.0:
        raise ValueError(f"{what}: must not be negative")
    return number


def _check_positive(value: float, what: str) -> float:
    number = _check_finite_real(value, what)
    if number <= 0.0:
        raise ValueError(f"{what}: must be strictly positive")
    return number


def _check_unit_interval(value: float, what: str) -> float:
    number = _check_finite_real(value, what)
    if not (0.0 <= number <= 1.0):
        raise ValueError(f"{what}: must lie between 0.0 and 1.0 inclusive")
    return number


class _StrictFrozenModel(BaseModel):
    """Base model: strict types, no extra fields, finite numbers, immutable."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class OperatingCostItem(_StrictFrozenModel):
    """One operating cost item in USD per hectare.

    ``includes_animal_purchase`` defaults to ``False``; setting it to ``True``
    triggers the double-count guard in ``evaluate_livestock_enterprise``.
    """

    label: NonEmptyStr
    amount_usd_ha: FiniteFloat
    includes_animal_purchase: bool = False

    @model_validator(mode="after")
    def _validate_amount(self) -> OperatingCostItem:
        _check_non_negative(self.amount_usd_ha, f"operating_costs[{self.label!r}]")
        return self


def _freeze_operating_costs(
    items: Sequence[OperatingCostItem],
) -> tuple[OperatingCostItem, ...]:
    return tuple(items)


OperatingCostTuple = Annotated[
    Sequence[OperatingCostItem],
    AfterValidator(_freeze_operating_costs),
]


class _BaseLivestockEnterprise(_StrictFrozenModel):
    """Shared forage conversion, weight-basis, and pasture inputs."""

    product_basis: WeightBasis
    price_basis: WeightBasis
    conversion_ratio_basis: WeightBasis

    # Zero default utilization/conversion coefficients: None means undeclared.
    forage_dm_kg_ha: FiniteFloat | Missing | None = None
    utilization_fraction: FiniteFloat | Missing | None = None
    feed_conversion_ratio: FiniteFloat | Missing | None = None
    price_usd_kg: FiniteFloat | Missing | None = None

    forage_option: ForageOption = "declared_pasture"
    forage_model_status: ForageModelStatus | None = None

    # Optional context only: beef yield is NEVER inferred from these alone.
    water_balance_mm: FiniteFloat | Missing | None = None
    botanical_mix: NonEmptyStr | None = None

    operating_costs: OperatingCostTuple = ()

    @model_validator(mode="after")
    def _validate_common(self) -> _BaseLivestockEnterprise:
        _validate_bases(
            self.product_basis, self.price_basis, self.conversion_ratio_basis
        )
        _resolve_forage_model_status(self.forage_option, self.forage_model_status)
        _validate_pasture_numeric_bounds(self)
        return self


class OwnProductionEnterprise(_BaseLivestockEnterprise):
    """Integrated own-production livestock enterprise.

    Strictly separated from ``buy_fatten_sell``: requires an explicit
    ``transfer_or_opportunity_value`` declaration (or ``Missing``), and forbids
    animal purchase cost or finished sale revenue fields.
    """

    scheme: Literal["own_production"] = "own_production"
    transfer_or_opportunity_value: FiniteFloat | Missing

    @model_validator(mode="after")
    def _validate_own_production(self) -> OwnProductionEnterprise:
        if not isinstance(self.transfer_or_opportunity_value, Missing):
            _check_non_negative(
                self.transfer_or_opportunity_value, "transfer_or_opportunity_value"
            )
        return self


class BuyFattenSellEnterprise(_BaseLivestockEnterprise):
    """Buy-fatten-sell livestock enterprise.

    Strictly separated from ``own_production``: purchase cost and finished sale
    revenue are registered once, and operating costs tagged
    ``includes_animal_purchase=True`` are rejected by the double-count guard.
    """

    scheme: Literal["buy_fatten_sell"] = "buy_fatten_sell"
    animal_purchase_cost_usd_ha: FiniteFloat | Missing
    finished_sale_revenue_usd_ha: FiniteFloat | Missing

    @model_validator(mode="after")
    def _validate_buy_fatten_sell(self) -> BuyFattenSellEnterprise:
        if not isinstance(self.animal_purchase_cost_usd_ha, Missing):
            _check_non_negative(
                self.animal_purchase_cost_usd_ha, "animal_purchase_cost_usd_ha"
            )
        if not isinstance(self.finished_sale_revenue_usd_ha, Missing):
            _check_non_negative(
                self.finished_sale_revenue_usd_ha, "finished_sale_revenue_usd_ha"
            )
        return self


LivestockEnterprise = Annotated[
    OwnProductionEnterprise | BuyFattenSellEnterprise,
    Field(discriminator="scheme"),
]


class LivestockEvaluation(_StrictFrozenModel):
    """Evaluated forage-to-beef physical output and economic margin."""

    scheme: LivestockScheme
    product_basis: WeightBasis
    forage_option: ForageOption
    forage_model_status: ForageModelStatus

    forage_dm_kg_ha: float
    utilization_fraction: float
    feed_conversion_ratio: float
    meat_kg_ha: float
    price_usd_kg: float

    gross_revenue_usd_ha: float
    operating_cost_usd_ha: float
    animal_purchase_cost_usd_ha: float | None = None
    finished_sale_revenue_usd_ha: float | None = None
    transfer_or_opportunity_value_usd_ha: float | None = None
    margin_usd_ha: float
    unit: str = MARGIN_UNIT
    status: str = PROPOSED_STATUS


def _validate_bases(
    product_basis: object,
    price_basis: object,
    conversion_ratio_basis: object,
) -> None:
    for name, basis in (
        ("product_basis", product_basis),
        ("price_basis", price_basis),
        ("conversion_ratio_basis", conversion_ratio_basis),
    ):
        if basis not in _WEIGHT_BASES:
            raise ValueError(f"{name}: expected one of {_WEIGHT_BASES}, got {basis!r}")
    if product_basis != price_basis or product_basis != conversion_ratio_basis:
        raise ValueError(
            "mismatched weight bases: product_basis "
            f"({product_basis!r}), price_basis ({price_basis!r}), and "
            f"conversion_ratio_basis ({conversion_ratio_basis!r}) must match"
        )


def _resolve_forage_model_status(
    forage_option: object,
    declared_status: object,
) -> ForageModelStatus:
    if forage_option not in _FORAGE_OPTIONS:
        raise ValueError(
            f"forage_option: expected one of {_FORAGE_OPTIONS}, got {forage_option!r}"
        )
    if forage_option == "water_dependent_annual":
        if (
            declared_status is not None
            and declared_status != FORAGE_STATUS_HYPOTHESIS_UNVALIDATED
        ):
            raise ValueError(
                "water_dependent_annual forage option must carry "
                f"forage_model_status={FORAGE_STATUS_HYPOTHESIS_UNVALIDATED!r}"
            )
        return FORAGE_STATUS_HYPOTHESIS_UNVALIDATED
    if declared_status is None:
        return FORAGE_STATUS_DECLARED
    if declared_status != FORAGE_STATUS_DECLARED:
        raise ValueError(
            "declared_pasture forage option cannot carry "
            f"forage_model_status={declared_status!r}"
        )
    return FORAGE_STATUS_DECLARED


def _validate_pasture_numeric_bounds(enterprise: _BaseLivestockEnterprise) -> None:
    if enterprise.forage_dm_kg_ha is not None and not isinstance(
        enterprise.forage_dm_kg_ha, Missing
    ):
        _check_non_negative(enterprise.forage_dm_kg_ha, "forage_dm_kg_ha")
    if enterprise.utilization_fraction is not None and not isinstance(
        enterprise.utilization_fraction, Missing
    ):
        _check_unit_interval(enterprise.utilization_fraction, "utilization_fraction")
    if enterprise.feed_conversion_ratio is not None and not isinstance(
        enterprise.feed_conversion_ratio, Missing
    ):
        _check_positive(enterprise.feed_conversion_ratio, "feed_conversion_ratio")
    if enterprise.price_usd_kg is not None and not isinstance(
        enterprise.price_usd_kg, Missing
    ):
        _check_non_negative(enterprise.price_usd_kg, "price_usd_kg")


def _validate_operating_costs(
    operating_costs: Sequence[OperatingCostItem],
    scheme: LivestockScheme,
) -> float:
    amounts: list[float] = []
    for index, item in enumerate(operating_costs):
        if not isinstance(item, OperatingCostItem):
            raise ValueError(  # noqa: TRY004
                f"operating_costs[{index}]: expected OperatingCostItem, "
                f"got {type(item).__name__}"
            )
        if item.includes_animal_purchase:
            raise ValueError(
                f"operating_costs[{index}] ({item.label!r}): "
                "includes_animal_purchase=True is rejected "
                f"(double-count guard in {scheme!r})"
            )
        amounts.append(
            _check_non_negative(item.amount_usd_ha, f"operating_costs[{index}]")
        )
    return math.fsum(amounts)


def _is_absent(value: object) -> bool:
    return value is None or isinstance(value, Missing)


def _missing_input_from(name: str, value: object, scheme: str) -> Missing:
    if isinstance(value, Missing):
        suffix = f": {value.detail}" if value.detail else ""
        return Missing(
            reason="MISSING_INPUT",
            detail=f"{scheme}: {name} is missing ({value.reason}{suffix})",
        )
    return Missing(
        reason="MISSING_INPUT",
        detail=f"{scheme}: {name} is not declared",
    )


def evaluate_livestock_enterprise(
    enterprise: OwnProductionEnterprise | BuyFattenSellEnterprise,
) -> LivestockEvaluation | Missing:
    """Evaluate forage-to-beef physical output and margin for one enterprise.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Raises ``ValueError`` on structural misuse, mismatched weight bases, or
    double-counted animal purchase operating costs. Returns ``Missing`` when
    required livestock or scheme inputs are absent (never ``0.0`` margin).
    """
    if not isinstance(enterprise, (OwnProductionEnterprise, BuyFattenSellEnterprise)):
        raise ValueError(  # noqa: TRY004
            "enterprise: expected OwnProductionEnterprise or "
            f"BuyFattenSellEnterprise, got {type(enterprise).__name__}"
        )

    _validate_bases(
        enterprise.product_basis,
        enterprise.price_basis,
        enterprise.conversion_ratio_basis,
    )
    forage_status = _resolve_forage_model_status(
        enterprise.forage_option, enterprise.forage_model_status
    )
    _validate_pasture_numeric_bounds(enterprise)
    operating_cost_usd_ha = _validate_operating_costs(
        enterprise.operating_costs, enterprise.scheme
    )

    if isinstance(enterprise, OwnProductionEnterprise):
        if enterprise.transfer_or_opportunity_value is None:
            raise ValueError(
                "own_production requires explicit transfer_or_opportunity_value "
                "declaration (or Missing)"
            )
        if not isinstance(enterprise.transfer_or_opportunity_value, Missing):
            _check_non_negative(
                enterprise.transfer_or_opportunity_value,
                "transfer_or_opportunity_value",
            )
    else:
        if not _is_absent(enterprise.animal_purchase_cost_usd_ha):
            _check_non_negative(
                enterprise.animal_purchase_cost_usd_ha, "animal_purchase_cost_usd_ha"
            )
        if not _is_absent(enterprise.finished_sale_revenue_usd_ha):
            _check_non_negative(
                enterprise.finished_sale_revenue_usd_ha, "finished_sale_revenue_usd_ha"
            )

    # Pasture completeness rule: never infer beef yield from water balance or
    # botanical mix, and never collapse incomplete pasture to 0.0 margin.
    if (
        _is_absent(enterprise.price_usd_kg)
        or _is_absent(enterprise.forage_dm_kg_ha)
        or _is_absent(enterprise.utilization_fraction)
        or _is_absent(enterprise.feed_conversion_ratio)
    ):
        return Missing(
            reason="MISSING_INPUT",
            detail=PASTURE_INCOMPLETE_DETAIL,
        )

    forage_dm = float(enterprise.forage_dm_kg_ha)  # type: ignore[arg-type]
    utilization = float(enterprise.utilization_fraction)  # type: ignore[arg-type]
    fcr = float(enterprise.feed_conversion_ratio)  # type: ignore[arg-type]
    price = float(enterprise.price_usd_kg)  # type: ignore[arg-type]

    meat_kg_ha = forage_dm * utilization / fcr
    if not math.isfinite(meat_kg_ha):
        raise ValueError("meat_kg_ha: computed value is not finite")

    if isinstance(enterprise, OwnProductionEnterprise):
        if _is_absent(enterprise.transfer_or_opportunity_value):
            return _missing_input_from(
                "transfer_or_opportunity_value",
                enterprise.transfer_or_opportunity_value,
                enterprise.scheme,
            )
        transfer_val = float(enterprise.transfer_or_opportunity_value)  # type: ignore[arg-type]
        gross_revenue = meat_kg_ha * price
        margin = gross_revenue - operating_cost_usd_ha - transfer_val
        return LivestockEvaluation(
            scheme="own_production",
            product_basis=enterprise.product_basis,
            forage_option=enterprise.forage_option,
            forage_model_status=forage_status,
            forage_dm_kg_ha=forage_dm,
            utilization_fraction=utilization,
            feed_conversion_ratio=fcr,
            meat_kg_ha=meat_kg_ha,
            price_usd_kg=price,
            gross_revenue_usd_ha=gross_revenue,
            operating_cost_usd_ha=operating_cost_usd_ha,
            transfer_or_opportunity_value_usd_ha=transfer_val,
            margin_usd_ha=margin,
        )

    if _is_absent(enterprise.animal_purchase_cost_usd_ha):
        return _missing_input_from(
            "animal_purchase_cost_usd_ha",
            enterprise.animal_purchase_cost_usd_ha,
            enterprise.scheme,
        )
    if _is_absent(enterprise.finished_sale_revenue_usd_ha):
        return _missing_input_from(
            "finished_sale_revenue_usd_ha",
            enterprise.finished_sale_revenue_usd_ha,
            enterprise.scheme,
        )

    purchase_cost = float(enterprise.animal_purchase_cost_usd_ha)  # type: ignore[arg-type]
    sale_revenue = float(enterprise.finished_sale_revenue_usd_ha)  # type: ignore[arg-type]
    margin = sale_revenue - purchase_cost - operating_cost_usd_ha
    return LivestockEvaluation(
        scheme="buy_fatten_sell",
        product_basis=enterprise.product_basis,
        forage_option=enterprise.forage_option,
        forage_model_status=forage_status,
        forage_dm_kg_ha=forage_dm,
        utilization_fraction=utilization,
        feed_conversion_ratio=fcr,
        meat_kg_ha=meat_kg_ha,
        price_usd_kg=price,
        gross_revenue_usd_ha=sale_revenue,
        operating_cost_usd_ha=operating_cost_usd_ha,
        animal_purchase_cost_usd_ha=purchase_cost,
        finished_sale_revenue_usd_ha=sale_revenue,
        margin_usd_ha=margin,
    )
