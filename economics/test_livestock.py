"""Acceptance tests for Frontier Unit F-18 (l2/economics-livestock-forage).

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Every number in this file is invented PLACEHOLDER test data from no source.
Run from the repository root: ``pytest economics/test_livestock.py -q``.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from contracts.economic_facts import MARGIN_UNIT
from contracts.inputs.common import Missing
from economics.livestock import (
    FORAGE_STATUS_DECLARED,
    FORAGE_STATUS_HYPOTHESIS_UNVALIDATED,
    PASTURE_INCOMPLETE_DETAIL,
    PROPOSED_STATUS,
    BuyFattenSellEnterprise,
    LivestockEnterprise,
    LivestockEvaluation,
    OperatingCostItem,
    OwnProductionEnterprise,
    evaluate_livestock_enterprise,
)


def _own_production(**overrides) -> OwnProductionEnterprise:
    data = {
        "product_basis": "liveweight",
        "price_basis": "liveweight",
        "conversion_ratio_basis": "liveweight",
        "forage_dm_kg_ha": 6000.0,
        "utilization_fraction": 0.5,
        "feed_conversion_ratio": 10.0,
        "price_usd_kg": 2.4,
        "transfer_or_opportunity_value": 150.0,
        "operating_costs": [
            OperatingCostItem(label="PLACEHOLDER_pasture_care", amount_usd_ha=120.0),
            OperatingCostItem(label="PLACEHOLDER_animal_health", amount_usd_ha=30.0),
        ],
    }
    data.update(overrides)
    return OwnProductionEnterprise(**data)


def _buy_fatten_sell(**overrides) -> BuyFattenSellEnterprise:
    data = {
        "product_basis": "liveweight",
        "price_basis": "liveweight",
        "conversion_ratio_basis": "liveweight",
        "forage_dm_kg_ha": 8000.0,
        "utilization_fraction": 0.6,
        "feed_conversion_ratio": 12.0,
        "price_usd_kg": 2.2,
        "animal_purchase_cost_usd_ha": 700.0,
        "finished_sale_revenue_usd_ha": 1800.0,
        "operating_costs": [
            OperatingCostItem(label="PLACEHOLDER_pasture_care", amount_usd_ha=140.0),
            OperatingCostItem(label="PLACEHOLDER_supplementation", amount_usd_ha=60.0),
        ],
    }
    data.update(overrides)
    return BuyFattenSellEnterprise(**data)


def test_proposed_status_marker_and_zero_default_coefficients() -> None:
    assert PROPOSED_STATUS == "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
    fields = OwnProductionEnterprise.model_fields
    assert fields["utilization_fraction"].default is None
    assert fields["feed_conversion_ratio"].default is None
    assert fields["forage_dm_kg_ha"].default is None
    assert fields["price_usd_kg"].default is None


def test_own_production_forage_conversion_and_margin_liveweight() -> None:
    enterprise = _own_production()
    result = evaluate_livestock_enterprise(enterprise)

    assert isinstance(result, LivestockEvaluation)
    assert result.scheme == "own_production"
    assert result.product_basis == "liveweight"
    assert result.forage_option == "declared_pasture"
    assert result.forage_model_status == FORAGE_STATUS_DECLARED
    assert result.unit == MARGIN_UNIT
    assert result.status == PROPOSED_STATUS

    # 6000 * 0.5 / 10 = 300 kg/ha; 300 * 2.4 = 720 USD/ha; 720 - 150 - 150 = 420
    assert result.meat_kg_ha == pytest.approx(300.0)
    assert result.gross_revenue_usd_ha == pytest.approx(720.0)
    assert result.operating_cost_usd_ha == pytest.approx(150.0)
    assert result.transfer_or_opportunity_value_usd_ha == pytest.approx(150.0)
    assert result.animal_purchase_cost_usd_ha is None
    assert result.finished_sale_revenue_usd_ha is None
    assert result.margin_usd_ha == pytest.approx(420.0)


def test_carcass_basis_matching_works() -> None:
    enterprise = _own_production(
        product_basis="carcass",
        price_basis="carcass",
        conversion_ratio_basis="carcass",
        forage_dm_kg_ha=5000.0,
        utilization_fraction=0.5,
        feed_conversion_ratio=20.0,
        price_usd_kg=4.0,
        transfer_or_opportunity_value=100.0,
        operating_costs=[],
    )
    result = evaluate_livestock_enterprise(enterprise)

    assert isinstance(result, LivestockEvaluation)
    assert result.product_basis == "carcass"
    # 5000 * 0.5 / 20 = 125 kg/ha; 125 * 4.0 - 100 = 400
    assert result.meat_kg_ha == pytest.approx(125.0)
    assert result.margin_usd_ha == pytest.approx(400.0)


@pytest.mark.parametrize(
    ("product_basis", "price_basis", "conversion_ratio_basis"),
    [
        ("liveweight", "carcass", "liveweight"),
        ("liveweight", "liveweight", "carcass"),
        ("carcass", "liveweight", "liveweight"),
        ("carcass", "carcass", "liveweight"),
        ("carcass", "liveweight", "carcass"),
        ("liveweight", "carcass", "carcass"),
    ],
)
def test_mismatched_weight_bases_raise_value_error(
    product_basis: str,
    price_basis: str,
    conversion_ratio_basis: str,
) -> None:
    with pytest.raises(ValueError, match="mismatched weight bases"):
        _own_production(
            product_basis=product_basis,
            price_basis=price_basis,
            conversion_ratio_basis=conversion_ratio_basis,
        )

    bypassed = OwnProductionEnterprise.model_construct(
        scheme="own_production",
        product_basis=product_basis,
        price_basis=price_basis,
        conversion_ratio_basis=conversion_ratio_basis,
        forage_dm_kg_ha=None,
        utilization_fraction=None,
        feed_conversion_ratio=None,
        price_usd_kg=None,
        forage_option="declared_pasture",
        forage_model_status=None,
        water_balance_mm=None,
        botanical_mix=None,
        operating_costs=(),
        transfer_or_opportunity_value=100.0,
    )
    with pytest.raises(ValueError, match="mismatched weight bases"):
        evaluate_livestock_enterprise(bypassed)


def test_buy_fatten_sell_registers_purchase_and_sale_once() -> None:
    enterprise = _buy_fatten_sell()
    result = evaluate_livestock_enterprise(enterprise)

    assert isinstance(result, LivestockEvaluation)
    assert result.scheme == "buy_fatten_sell"
    # 8000 * 0.6 / 12 = 400 kg/ha (not added on top of finished_sale_revenue)
    assert result.meat_kg_ha == pytest.approx(400.0)
    assert result.animal_purchase_cost_usd_ha == pytest.approx(700.0)
    assert result.finished_sale_revenue_usd_ha == pytest.approx(1800.0)
    assert result.gross_revenue_usd_ha == pytest.approx(1800.0)
    assert result.operating_cost_usd_ha == pytest.approx(200.0)
    assert result.transfer_or_opportunity_value_usd_ha is None
    # 1800 - 700 - 200 = 900
    assert result.margin_usd_ha == pytest.approx(900.0)


def test_buy_fatten_sell_rejects_operating_cost_with_animal_purchase() -> None:
    enterprise = _buy_fatten_sell(
        operating_costs=[
            OperatingCostItem(label="PLACEHOLDER_pasture_care", amount_usd_ha=100.0),
            OperatingCostItem(
                label="PLACEHOLDER_feeder_purchase",
                amount_usd_ha=700.0,
                includes_animal_purchase=True,
            ),
        ]
    )
    with pytest.raises(ValueError, match="includes_animal_purchase=True"):
        evaluate_livestock_enterprise(enterprise)


def test_own_production_also_rejects_operating_cost_with_animal_purchase() -> None:
    enterprise = _own_production(
        operating_costs=[
            OperatingCostItem(
                label="PLACEHOLDER_feeder_purchase",
                amount_usd_ha=500.0,
                includes_animal_purchase=True,
            ),
        ]
    )
    with pytest.raises(ValueError, match="includes_animal_purchase=True"):
        evaluate_livestock_enterprise(enterprise)


def test_strict_scheme_separation_rejects_cross_scheme_fields() -> None:
    with pytest.raises(ValidationError):
        _own_production(animal_purchase_cost_usd_ha=500.0)
    with pytest.raises(ValidationError):
        _own_production(finished_sale_revenue_usd_ha=1000.0)
    with pytest.raises(ValidationError):
        _buy_fatten_sell(transfer_or_opportunity_value=100.0)

    adapter = TypeAdapter(LivestockEnterprise)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "scheme": "unknown_scheme",
                "product_basis": "liveweight",
                "price_basis": "liveweight",
                "conversion_ratio_basis": "liveweight",
            }
        )


def test_own_production_requires_transfer_or_opportunity_value_or_missing() -> None:
    with pytest.raises(ValidationError):
        OwnProductionEnterprise(
            product_basis="liveweight",
            price_basis="liveweight",
            conversion_ratio_basis="liveweight",
            forage_dm_kg_ha=6000.0,
            utilization_fraction=0.5,
            feed_conversion_ratio=10.0,
            price_usd_kg=2.4,
        )  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        _own_production(transfer_or_opportunity_value=None)

    missing_transfer = _own_production(
        transfer_or_opportunity_value=Missing(
            reason="NOT_DECLARED",
            detail="PLACEHOLDER opportunity value not declared",
        )
    )
    result = evaluate_livestock_enterprise(missing_transfer)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "transfer_or_opportunity_value" in (result.detail or "")


def test_buy_fatten_sell_propagates_missing_purchase_or_sale() -> None:
    missing_purchase = _buy_fatten_sell(
        animal_purchase_cost_usd_ha=Missing(reason="NOT_DECLARED")
    )
    res_purchase = evaluate_livestock_enterprise(missing_purchase)
    assert isinstance(res_purchase, Missing)
    assert res_purchase.reason == "MISSING_INPUT"
    assert "animal_purchase_cost_usd_ha" in (res_purchase.detail or "")

    missing_sale = _buy_fatten_sell(
        finished_sale_revenue_usd_ha=Missing(reason="NOT_DECLARED")
    )
    res_sale = evaluate_livestock_enterprise(missing_sale)
    assert isinstance(res_sale, Missing)
    assert res_sale.reason == "MISSING_INPUT"
    assert "finished_sale_revenue_usd_ha" in (res_sale.detail or "")


@pytest.mark.parametrize(
    "missing_field",
    [
        "price_usd_kg",
        "forage_dm_kg_ha",
        "utilization_fraction",
        "feed_conversion_ratio",
    ],
)
@pytest.mark.parametrize(
    "missing_value",
    [None, Missing(reason="NOT_DECLARED")],
)
def test_pasture_completeness_rule_returns_missing_never_zero(
    missing_field: str,
    missing_value: None | Missing,
) -> None:
    enterprise = _own_production(
        **{missing_field: missing_value},
        water_balance_mm=240.0,
        botanical_mix="PLACEHOLDER_alfalfa_fescue",
    )
    result = evaluate_livestock_enterprise(enterprise)

    assert result == Missing(
        reason="MISSING_INPUT",
        detail=PASTURE_INCOMPLETE_DETAIL,
    )
    assert result.detail == "pasture without livestock module is incomplete"


def test_pasture_never_infers_beef_yield_from_water_or_botanical_mix() -> None:
    pasture_only = _buy_fatten_sell(
        forage_dm_kg_ha=None,
        utilization_fraction=None,
        feed_conversion_ratio=None,
        price_usd_kg=None,
        water_balance_mm=310.0,
        botanical_mix="PLACEHOLDER_clover_ryegrass",
    )
    result = evaluate_livestock_enterprise(pasture_only)
    assert result == Missing(
        reason="MISSING_INPUT",
        detail="pasture without livestock module is incomplete",
    )


def test_water_dependent_annual_forage_carries_unvalidated_status() -> None:
    enterprise = _own_production(
        forage_option="water_dependent_annual",
        water_balance_mm=180.0,
    )
    result = evaluate_livestock_enterprise(enterprise)

    assert isinstance(result, LivestockEvaluation)
    assert result.forage_option == "water_dependent_annual"
    assert result.forage_model_status == FORAGE_STATUS_HYPOTHESIS_UNVALIDATED
    assert result.forage_model_status == "HYPOTHESIS_UNVALIDATED"


def test_water_dependent_annual_forage_rejects_declared_status() -> None:
    with pytest.raises(ValueError, match="HYPOTHESIS_UNVALIDATED"):
        _own_production(
            forage_option="water_dependent_annual",
            forage_model_status="DECLARED",
        )

    with pytest.raises(ValueError, match="declared_pasture"):
        _own_production(
            forage_option="declared_pasture",
            forage_model_status="HYPOTHESIS_UNVALIDATED",
        )


def test_water_dependent_annual_forage_still_enforces_pasture_completeness() -> None:
    enterprise = _own_production(
        forage_option="water_dependent_annual",
        forage_dm_kg_ha=None,
        water_balance_mm=200.0,
    )
    result = evaluate_livestock_enterprise(enterprise)
    assert result == Missing(
        reason="MISSING_INPUT",
        detail="pasture without livestock module is incomplete",
    )


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"forage_dm_kg_ha": -1.0},
        {"utilization_fraction": -0.01},
        {"utilization_fraction": 1.01},
        {"feed_conversion_ratio": 0.0},
        {"feed_conversion_ratio": -5.0},
        {"price_usd_kg": -0.1},
        {"transfer_or_opportunity_value": -10.0},
        {"forage_dm_kg_ha": True},
        {"utilization_fraction": float("nan")},
        {"feed_conversion_ratio": float("inf")},
    ],
)
def test_invalid_numeric_inputs_raise_value_error(bad_kwargs: dict) -> None:
    with pytest.raises(ValueError):
        _own_production(**bad_kwargs)


def test_invalid_buy_fatten_sell_amounts_and_non_enterprise_rejected() -> None:
    with pytest.raises(ValueError):
        _buy_fatten_sell(animal_purchase_cost_usd_ha=-1.0)
    with pytest.raises(ValueError):
        _buy_fatten_sell(finished_sale_revenue_usd_ha=-1.0)
    with pytest.raises(ValueError):
        OperatingCostItem(label="PLACEHOLDER_cost", amount_usd_ha=-5.0)
    with pytest.raises(ValueError, match="expected OwnProductionEnterprise"):
        evaluate_livestock_enterprise({"scheme": "own_production"})  # type: ignore[arg-type]


def test_structural_misuse_checked_before_pasture_completeness() -> None:
    incomplete_with_double_count = _buy_fatten_sell(
        forage_dm_kg_ha=None,
        operating_costs=[
            OperatingCostItem(
                label="PLACEHOLDER_purchase_dup",
                amount_usd_ha=500.0,
                includes_animal_purchase=True,
            )
        ],
    )
    with pytest.raises(ValueError, match="includes_animal_purchase=True"):
        evaluate_livestock_enterprise(incomplete_with_double_count)


def test_zero_utilization_explicitly_declared_is_valid() -> None:
    enterprise = _own_production(
        utilization_fraction=0.0,
        transfer_or_opportunity_value=0.0,
        operating_costs=[],
    )
    result = evaluate_livestock_enterprise(enterprise)
    assert isinstance(result, LivestockEvaluation)
    assert result.meat_kg_ha == 0.0
    assert result.margin_usd_ha == 0.0


def test_models_are_frozen() -> None:
    enterprise = _own_production()
    result = evaluate_livestock_enterprise(enterprise)
    assert isinstance(result, LivestockEvaluation)

    with pytest.raises(ValidationError):
        enterprise.price_usd_kg = 999.0  # type: ignore[misc]
    with pytest.raises(ValidationError):
        result.margin_usd_ha = 999.0  # type: ignore[misc]
