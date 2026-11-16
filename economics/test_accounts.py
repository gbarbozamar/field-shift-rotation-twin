"""Acceptance test of unit l2/economics-rev13-accounts.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Run from the repository root::

    uv run pytest economics/test_accounts.py

Every number in this file is invented test data (no market, no producer, no
survey, no source), using PLACEHOLDER identifiers. Expected outputs are
worked out by arithmetic on those invented test inputs.
"""

from __future__ import annotations

import datetime as dt
import json
import socket

import pytest
from pydantic import ValidationError

from contracts.economic_facts import COST_UNIT, MARGIN_UNIT, PRICE_UNIT, YIELD_UNIT
from contracts.inputs.common import Missing, Value
from economics.accounts import (
    DEFAULT_ACCOUNTING_DEFINITION_NOTE,
    ActivityAccountInput,
    ActivitySaleSpec,
    AgYearAccountInput,
    CashFlowEvent,
    DepreciationSpec,
    DoubleCountError,
    EconomicAccountsSummary,
    PostHarvestDeduction,
    RotationAccountInput,
    compute_activity_accounts,
    compute_ag_year_accounts,
    compute_rotation_accounts,
)

# ---------------------------------------------------------------------------
# Invented test-data builders (not parameters, from no source)
# ---------------------------------------------------------------------------

_RANGE_MISSING = {"reason": "NOT_DECLARED"}


def _val(
    number: float,
    unit: str = COST_UNIT,
    *,
    provenance: str = "DECLARED",
    source: str = "user",
) -> Value:
    return Value.model_validate(
        {
            "value": number,
            "unit": unit,
            "provenance": provenance,
            "source": source,
            "range_missing": _RANGE_MISSING,
        }
    )


def _missing(unit: str = COST_UNIT, reason: str = "NOT_DECLARED") -> Value:
    return Value.model_validate(
        {
            "value": None,
            "unit": unit,
            "missing": {"reason": reason},
        }
    )


def _gross_sale(
    *,
    price: float = 400.0,
    yield_: float = 3.0,
    harvest: float | Value | PostHarvestDeduction | None = 60.0,
    drying: float | Value | PostHarvestDeduction | None = 15.0,
    freight: float | Value | PostHarvestDeduction | None = 45.0,
    selling: float | Value | PostHarvestDeduction | None = 30.0,
    yield_provenance: str = "DECLARED",
) -> ActivitySaleSpec:
    def _wrap(
        v: float | Value | PostHarvestDeduction | None,
    ) -> Value | PostHarvestDeduction | None:
        if isinstance(v, (int, float)):
            return _val(float(v), COST_UNIT)
        return v

    return ActivitySaleSpec(
        price=_val(price, PRICE_UNIT),
        yield_=_val(yield_, YIELD_UNIT, provenance=yield_provenance),
        price_basis="gross",
        harvest=_wrap(harvest),
        drying=_wrap(drying),
        freight=_wrap(freight),
        selling=_wrap(selling),
    )


def _net_sale(
    *,
    price: float = 350.0,
    yield_: float = 3.0,
    included_in_price: tuple[str, ...] | None = None,
    harvest: Value | PostHarvestDeduction | None = None,
    drying: Value | PostHarvestDeduction | None = None,
    freight: Value | PostHarvestDeduction | None = None,
    selling: Value | PostHarvestDeduction | None = None,
) -> ActivitySaleSpec:
    kwargs: dict = {
        "price": _val(price, PRICE_UNIT),
        "yield_": _val(yield_, YIELD_UNIT),
        "price_basis": "net",
        "harvest": harvest,
        "drying": drying,
        "freight": freight,
        "selling": selling,
    }
    if included_in_price is not None:
        kwargs["included_in_price"] = included_in_price
    return ActivitySaleSpec(**kwargs)


def _assert_missing_input(val: Value, expected_unit: str, fragment: str = "") -> None:
    assert val.value is None
    assert val.unit == expected_unit
    assert isinstance(val.missing, Missing)
    assert val.missing.reason == "MISSING_INPUT"
    if fragment:
        assert val.missing.detail is not None
        assert fragment in val.missing.detail


# ---------------------------------------------------------------------------
# Account 1: Gross margin & gross vs net farm-gate price mutual exclusion
# ---------------------------------------------------------------------------


def test_gross_price_deducts_all_four_post_harvest_items_once_each() -> None:
    # Revenue = 400 * 3.0 = 1200.0 USD ha-1
    # Direct costs = 500 + 60 (harvest) + 15 (drying) + 45 (freight) + 30 (selling) = 650.0
    # Gross margin = 1200.0 - 650.0 = 550.0 USD ha-1
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_soy_2024",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    gm = res.gross_margin_account
    assert gm.revenue.value == pytest.approx(1200.0)
    assert gm.direct_costs.value == pytest.approx(650.0)
    assert gm.gross_margin.value == pytest.approx(550.0)
    assert gm.gross_margin.unit == COST_UNIT
    assert gm.gross_margin.provenance == "DERIVED"
    assert gm.price_basis == "gross"
    assert gm.deducted_post_harvest_items == ("harvest", "drying", "freight", "selling")
    assert gm.included_in_price == ()


def test_gross_price_supports_per_tonne_post_harvest_deductions() -> None:
    # Revenue = 300 * 4.0 = 1200.0 USD ha-1
    # Direct costs = 400 + 50 (harvest ha-1) + 5*4 (drying t-1) + 10*4 (freight t-1) + 20 (selling ha-1)
    #              = 400 + 50 + 20 + 40 + 20 = 530.0
    # Gross margin = 1200.0 - 530.0 = 670.0 USD ha-1
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_corn_2024",
        crop_id="PLACEHOLDER_maize",
        ag_year=2024,
        sale=_gross_sale(
            price=300.0,
            yield_=4.0,
            harvest=_val(50.0, COST_UNIT),
            drying=_val(5.0, PRICE_UNIT),
            freight=_val(10.0, PRICE_UNIT),
            selling=_val(20.0, COST_UNIT),
        ),
        pre_harvest_direct_cost=_val(400.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.revenue.value == pytest.approx(1200.0)
    assert res.gross_margin_account.direct_costs.value == pytest.approx(530.0)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(670.0)


@pytest.mark.parametrize("item", ["harvest", "drying", "freight", "selling"])
def test_gross_price_refuses_item_tagged_already_included_in_spec(item: str) -> None:
    with pytest.raises(DoubleCountError) as exc_info:
        ActivitySaleSpec(
            price=_val(400.0, PRICE_UNIT),
            yield_=_val(3.0, YIELD_UNIT),
            price_basis="gross",
            included_in_price=(item,),  # type: ignore[arg-type]
            harvest=_val(60.0, COST_UNIT),
            drying=_val(15.0, COST_UNIT),
            freight=_val(45.0, COST_UNIT),
            selling=_val(30.0, COST_UNIT),
        )
    assert isinstance(exc_info.value, ValueError)


@pytest.mark.parametrize("item", ["harvest", "drying", "freight", "selling"])
def test_gross_price_refuses_deduction_item_tagged_included(item: str) -> None:
    kwargs: dict = {
        "harvest": _val(60.0, COST_UNIT),
        "drying": _val(15.0, COST_UNIT),
        "freight": _val(45.0, COST_UNIT),
        "selling": _val(30.0, COST_UNIT),
    }
    kwargs[item] = PostHarvestDeduction(
        amount=_val(20.0, COST_UNIT),
        included_in_price=True,
    )
    with pytest.raises(DoubleCountError):
        _gross_sale(**kwargs)


def test_net_price_avoids_post_harvest_deductions_when_all_included() -> None:
    # Revenue = 350 * 3.0 = 1050.0 USD ha-1
    # Direct costs = 500.0 (pre-harvest only)
    # Gross margin = 550.0 USD ha-1
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_soy_net",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    gm = res.gross_margin_account
    assert gm.revenue.value == pytest.approx(1050.0)
    assert gm.direct_costs.value == pytest.approx(500.0)
    assert gm.gross_margin.value == pytest.approx(550.0)
    assert gm.deducted_post_harvest_items == ()
    assert gm.included_in_price == ("harvest", "drying", "freight", "selling")


@pytest.mark.parametrize("item", ["harvest", "drying", "freight", "selling"])
def test_net_price_rejects_re_deducting_included_post_harvest_expense(
    item: str,
) -> None:
    with pytest.raises(DoubleCountError) as exc_info:
        _net_sale(**{item: _val(25.0, COST_UNIT)})
    assert isinstance(exc_info.value, ValueError)


def test_net_price_partial_inclusion_deducts_only_excluded_item_and_blocks_rest() -> (
    None
):
    # Net of drying, freight, selling; harvest is paid separately.
    sale = _net_sale(
        price=370.0,
        yield_=3.0,
        included_in_price=("drying", "freight", "selling"),
        harvest=_val(60.0, COST_UNIT),
    )
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_soy_partial_net",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=sale,
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.direct_costs.value == pytest.approx(560.0)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(550.0)
    assert res.gross_margin_account.deducted_post_harvest_items == ("harvest",)

    with pytest.raises(DoubleCountError):
        _net_sale(
            included_in_price=("drying", "freight", "selling"),
            harvest=_val(60.0, COST_UNIT),
            selling=_val(10.0, COST_UNIT),
        )


def test_net_price_refuses_empty_included_in_price() -> None:
    with pytest.raises(ValueError, match="included_in_price"):
        _net_sale(included_in_price=())


def test_zero_price_or_yield_is_valid_number_never_missing() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_failed_crop",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(
            price=400.0,
            yield_=0.0,
            harvest=0.0,
            drying=0.0,
            freight=0.0,
            selling=0.0,
        ),
        pre_harvest_direct_cost=_val(200.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.revenue.value == pytest.approx(0.0)
    assert res.gross_margin_account.direct_costs.value == pytest.approx(200.0)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(-200.0)


# ---------------------------------------------------------------------------
# Account 2: Accounting result, paid_rent vs own_land_opportunity_cost, note
# ---------------------------------------------------------------------------


def test_accounting_result_keeps_paid_rent_separate_from_opportunity_cost() -> None:
    # gross_margin = 550.0
    # structure_cost = 40.0, paid_rent = 120.0, relevant_depreciation = 30.0 (20 mach + 10 other)
    # accounting_result = 550.0 - 40.0 - 120.0 - 30.0 = 360.0
    # own_land_opportunity_cost = 180.0 (stored separately, NEVER subtracted!)
    base_kwargs = {
        "activity_id": "PLACEHOLDER_soy_acc",
        "crop_id": "PLACEHOLDER_soybean",
        "ag_year": 2024,
        "sale": _gross_sale(),
        "pre_harvest_direct_cost": _val(500.0, COST_UNIT),
        "structure_cost": _val(40.0, COST_UNIT),
        "paid_rent": _val(120.0, COST_UNIT),
        "depreciation": DepreciationSpec(
            machinery_depreciation=_val(20.0, COST_UNIT),
            other_depreciation=_val(10.0, COST_UNIT),
        ),
    }
    res_low_opp = compute_activity_accounts(
        ActivityAccountInput(
            **base_kwargs,
            own_land_opportunity_cost=_val(180.0, COST_UNIT),
        )
    )
    res_high_opp = compute_activity_accounts(
        ActivityAccountInput(
            **base_kwargs,
            own_land_opportunity_cost=_val(999.0, COST_UNIT),
        )
    )
    res_missing_opp = compute_activity_accounts(
        ActivityAccountInput(
            **base_kwargs,
            own_land_opportunity_cost=_missing(COST_UNIT),
        )
    )

    for res in (res_low_opp, res_high_opp, res_missing_opp):
        acc = res.accounting_result_account
        assert acc.accounting_result.value == pytest.approx(360.0)
        assert acc.paid_rent.value == pytest.approx(120.0)
        assert acc.relevant_depreciation.value == pytest.approx(30.0)
        assert acc.definition_note == DEFAULT_ACCOUNTING_DEFINITION_NOTE

    assert (
        res_low_opp.accounting_result_account.own_land_opportunity_cost.value
        == pytest.approx(180.0)
    )
    assert (
        res_high_opp.accounting_result_account.own_land_opportunity_cost.value
        == pytest.approx(999.0)
    )
    _assert_missing_input(
        res_missing_opp.accounting_result_account.own_land_opportunity_cost,
        COST_UNIT,
        "own_land_opportunity_cost",
    )


def test_accounting_result_never_called_net_profit() -> None:
    with pytest.raises(ValueError, match="net_profit"):
        ActivityAccountInput(
            activity_id="PLACEHOLDER_bad_note",
            crop_id="PLACEHOLDER_soybean",
            ag_year=2024,
            sale=_net_sale(),
            pre_harvest_direct_cost=_val(500.0, COST_UNIT),
            definition_note="This is the net_profit of the field",
        )
    with pytest.raises(ValueError, match="net_profit"):
        AgYearAccountInput(
            ag_year=2024,
            activities=(
                ActivityAccountInput(
                    activity_id="PLACEHOLDER_a1",
                    crop_id="PLACEHOLDER_soybean",
                    ag_year=2024,
                    sale=_net_sale(),
                    pre_harvest_direct_cost=_val(500.0, COST_UNIT),
                ),
            ),
            definition_note="Net Profit for 2024",
        )


def test_overhead_double_count_between_activity_and_year_rejected() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_a1",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        paid_rent=_val(100.0, COST_UNIT),
    )
    with pytest.raises(DoubleCountError):
        AgYearAccountInput(
            ag_year=2024,
            activities=(act,),
            paid_rent=_val(100.0, MARGIN_UNIT),
        )


def test_depreciation_spec_rejects_both_relevant_and_parts() -> None:
    with pytest.raises(DoubleCountError):
        DepreciationSpec(
            machinery_depreciation=_val(20.0, COST_UNIT),
            relevant_depreciation=_val(30.0, COST_UNIT),
        )


# ---------------------------------------------------------------------------
# Account 3: Cash flow by date & non-monetary depreciation / tariff guards
# ---------------------------------------------------------------------------


def test_cash_flow_by_date_chronological_and_exact() -> None:
    # Supply events deliberately out of chronological order
    events = (
        CashFlowEvent(
            date=dt.date(2025, 4, 15),
            kind="collection",
            amount=_val(1100.0, COST_UNIT),
            description="grain sale collection",
        ),
        CashFlowEvent(
            date=dt.date(2024, 10, 1),
            kind="payment",
            amount=_val(400.0, COST_UNIT),
            description="seed and fertilizer payment",
        ),
        CashFlowEvent(
            date=dt.date(2024, 7, 15),
            kind="investment",
            amount=_val(300.0, COST_UNIT),
            description="storage upgrade",
        ),
        CashFlowEvent(
            date=dt.date(2025, 4, 15),
            kind="payment",
            amount=_val(150.0, COST_UNIT),
            description="harvest contractor payment",
        ),
        CashFlowEvent(
            date=dt.date(2025, 6, 30),
            kind="residual_value",
            amount=_val(100.0, COST_UNIT),
            description="storage residual value",
        ),
    )
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_cf",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        cash_events=events,
    )
    res = compute_activity_accounts(act)
    cf = res.cash_flow_account
    assert cf.non_monetary_depreciation_excluded is True
    assert cf.collections.value == pytest.approx(1100.0)
    assert cf.payments.value == pytest.approx(550.0)
    assert cf.investments.value == pytest.approx(300.0)
    assert cf.residual_values.value == pytest.approx(100.0)
    # 1100 - 550 - 300 + 100 = 350.0
    assert cf.cash_flow.value == pytest.approx(350.0)

    assert [row.date for row in cf.by_date] == [
        dt.date(2024, 7, 15),
        dt.date(2024, 10, 1),
        dt.date(2025, 4, 15),
        dt.date(2025, 6, 30),
    ]
    assert [row.net_cash_flow.value for row in cf.by_date] == pytest.approx(
        [-300.0, -400.0, 950.0, 100.0]
    )
    assert [row.cumulative_cash_flow.value for row in cf.by_date] == pytest.approx(
        [-300.0, -700.0, 250.0, 350.0]
    )


def test_cash_flow_strictly_excludes_non_monetary_depreciation() -> None:
    with pytest.raises(DoubleCountError):
        CashFlowEvent(
            date=dt.date(2025, 1, 1),
            kind="depreciation",  # type: ignore[arg-type]
            amount=_val(50.0, COST_UNIT),
        )
    with pytest.raises(DoubleCountError):
        CashFlowEvent(
            date=dt.date(2025, 1, 1),
            kind="payment",
            amount=_val(50.0, COST_UNIT),
            is_non_monetary=True,
        )
    with pytest.raises(DoubleCountError):
        ActivityAccountInput(
            activity_id="PLACEHOLDER_bad_cf_flag",
            crop_id="PLACEHOLDER_soybean",
            ag_year=2024,
            sale=_net_sale(),
            pre_harvest_direct_cost=_val(500.0, COST_UNIT),
            non_monetary_depreciation_excluded=False,
        )


def test_machinery_tariff_includes_depreciation_blocks_machinery_depreciation() -> None:
    # Refused directly in DepreciationSpec
    with pytest.raises(DoubleCountError) as exc_info:
        DepreciationSpec(
            machinery_depreciation=_val(25.0, COST_UNIT),
            other_depreciation=_val(10.0, COST_UNIT),
            machinery_tariff_includes_depreciation=True,
        )
    assert isinstance(exc_info.value, ValueError)

    # Refused when relevant_depreciation includes machinery
    with pytest.raises(DoubleCountError):
        DepreciationSpec(
            relevant_depreciation=_val(35.0, COST_UNIT),
            relevant_includes_machinery=True,
            machinery_tariff_includes_depreciation=True,
        )

    # Refused when flag is raised at Activity, AgYear, or Rotation level
    depr_with_mach = DepreciationSpec(
        machinery_depreciation=_val(25.0, COST_UNIT),
        other_depreciation=_val(10.0, COST_UNIT),
    )
    with pytest.raises(DoubleCountError):
        ActivityAccountInput(
            activity_id="PLACEHOLDER_mach_guard",
            crop_id="PLACEHOLDER_soybean",
            ag_year=2024,
            sale=_net_sale(),
            pre_harvest_direct_cost=_val(500.0, COST_UNIT),
            depreciation=depr_with_mach,
            machinery_tariff_includes_depreciation=True,
        )

    act_clean = ActivityAccountInput(
        activity_id="PLACEHOLDER_mach_child",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        structure_cost=_val(40.0, COST_UNIT),
        paid_rent=_val(0.0, COST_UNIT),
        depreciation=depr_with_mach,
    )
    with pytest.raises(DoubleCountError):
        AgYearAccountInput(
            ag_year=2024,
            activities=(act_clean,),
            machinery_tariff_includes_depreciation=True,
        )

    # Valid when machinery_depreciation is omitted (or 0.0) and only other_depreciation is charged
    act_valid = ActivityAccountInput(
        activity_id="PLACEHOLDER_mach_ok",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        structure_cost=_val(40.0, COST_UNIT),
        paid_rent=_val(0.0, COST_UNIT),
        depreciation=DepreciationSpec(
            other_depreciation=_val(10.0, COST_UNIT),
            machinery_tariff_includes_depreciation=True,
        ),
        machinery_tariff_includes_depreciation=True,
    )
    res = compute_activity_accounts(act_valid)
    assert res.accounting_result_account.relevant_depreciation.value == pytest.approx(
        10.0
    )
    assert res.accounting_result_account.accounting_result.value == pytest.approx(500.0)
    assert res.accounting_result_account.machinery_tariff_includes_depreciation is True


# ---------------------------------------------------------------------------
# Missing input propagation (never 0.0) & strict separation across accounts
# ---------------------------------------------------------------------------


def test_missing_price_or_post_harvest_makes_gm_and_acc_missing_but_cash_flow_computes() -> (
    None
):
    events = (
        CashFlowEvent(
            date=dt.date(2025, 3, 1),
            kind="collection",
            amount=_val(800.0, COST_UNIT),
        ),
        CashFlowEvent(
            date=dt.date(2024, 11, 1),
            kind="payment",
            amount=_val(300.0, COST_UNIT),
        ),
    )
    # Missing drying under gross basis (omitted -> never 0.0)
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_missing_drying",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(drying=None),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        structure_cost=_val(40.0, COST_UNIT),
        paid_rent=_val(100.0, COST_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(20.0, COST_UNIT)),
        cash_events=events,
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.revenue.value == pytest.approx(1200.0)
    _assert_missing_input(res.gross_margin_account.direct_costs, COST_UNIT, "drying")
    _assert_missing_input(res.gross_margin_account.gross_margin, COST_UNIT, "drying")
    _assert_missing_input(
        res.accounting_result_account.accounting_result, COST_UNIT, "gross_margin"
    )
    # Cash flow account remains completely computable!
    assert res.cash_flow_account.cash_flow.value == pytest.approx(500.0)


def test_missing_structure_cost_affects_only_accounting_result() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_missing_struct",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        structure_cost=_missing(COST_UNIT),
        paid_rent=_val(100.0, COST_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(20.0, COST_UNIT)),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2025, 3, 1),
                kind="collection",
                amount=_val(900.0, COST_UNIT),
            ),
        ),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(550.0)
    _assert_missing_input(
        res.accounting_result_account.accounting_result, COST_UNIT, "structure_cost"
    )
    assert res.cash_flow_account.cash_flow.value == pytest.approx(900.0)


def test_missing_cash_flow_amount_affects_only_cash_flow_account() -> None:
    events = (
        CashFlowEvent(
            date=dt.date(2024, 10, 1),
            kind="payment",
            amount=_val(200.0, COST_UNIT),
        ),
        CashFlowEvent(
            date=dt.date(2025, 4, 1),
            kind="collection",
            amount=_missing(COST_UNIT),
        ),
    )
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_missing_cf",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
        structure_cost=_val(40.0, COST_UNIT),
        paid_rent=_val(100.0, COST_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(20.0, COST_UNIT)),
        cash_events=events,
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(550.0)
    assert res.accounting_result_account.accounting_result.value == pytest.approx(390.0)
    _assert_missing_input(res.cash_flow_account.cash_flow, COST_UNIT, "collection")
    # Earlier date cumulative cash flow is known; date with missing collection is missing
    assert res.cash_flow_account.by_date[0].cumulative_cash_flow.value == pytest.approx(
        -200.0
    )
    _assert_missing_input(res.cash_flow_account.by_date[1].net_cash_flow, COST_UNIT)
    _assert_missing_input(
        res.cash_flow_account.by_date[1].cumulative_cash_flow, COST_UNIT
    )


def test_simulated_yield_propagates_simulated_provenance() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_sim",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(yield_provenance="SIMULATED"),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.revenue.provenance == "SIMULATED"
    assert res.gross_margin_account.gross_margin.provenance == "SIMULATED"
    assert res.gross_margin_account.direct_costs.provenance == "DERIVED"


def test_c31_broken_model_construct_value_is_rejected() -> None:
    broken = Value.model_construct(value=None, unit=COST_UNIT, missing=None)
    with pytest.raises(ValueError, match="C3.1"):
        ActivityAccountInput(
            activity_id="PLACEHOLDER_broken",
            crop_id="PLACEHOLDER_soybean",
            ag_year=2024,
            sale=_net_sale(),
            pre_harvest_direct_cost=broken,
        )


# ---------------------------------------------------------------------------
# Full rotation & agricultural year aggregation, roundtrip, immutability
# ---------------------------------------------------------------------------


def test_full_rotation_two_years_double_crop_and_cash_events() -> None:
    # Year 2024: Wheat (gross) + 2nd-crop Soybean (net)
    #   Wheat: rev = 220 * 4.0 = 880; dc = 350 + 50+10+30+20 = 460; gm = 420
    #   Soy2:  rev = 340 * 2.0 = 680; dc = 300; gm = 380
    #   Year 2024 GM = 800.0 USD ha-1 yr-1
    #   Year 2024 Overheads: structure=50, paid_rent=100, depreciation=30 (mach=20, other=10)
    #   Year 2024 Accounting Result = 800 - 50 - 100 - 30 = 620.0 USD ha-1 yr-1
    #   Year 2024 Cash Events: -650 (payments), +1400 (collections) -> +750
    # Year 2025: Maize (net)
    #   Maize: rev = 180 * 8.0 = 1440; dc = 600; gm = 840.0 USD ha-1 yr-1
    #   Year 2025 Overheads: structure=50, paid_rent=100, depreciation=30
    #   Year 2025 Accounting Result = 840 - 50 - 100 - 30 = 660.0 USD ha-1 yr-1
    #   Year 2025 Cash Events: -750 (payments), +1440 (collections) -> +690
    # Rotation-level cash events:
    #   2024-06-01 investment -500.0
    #   2026-05-30 residual_value +260.0
    # Rotation totals (2 years):
    #   Revenue = 880 + 680 + 1440 = 3000.0 USD ha-1
    #   Direct costs = 460 + 300 + 600 = 1360.0 USD ha-1
    #   Gross margin = 1640.0 USD ha-1 (annual avg = 820.0 USD ha-1 yr-1)
    #   Accounting result = 620 + 660 = 1280.0 USD ha-1 (annual avg = 640.0 USD ha-1 yr-1)
    #   Cash flow = (1400 + 1440) - (650 + 750) - 500 + 260 = 2840 - 1400 - 500 + 260 = 1200.0
    #     (annual avg = 600.0 USD ha-1 yr-1)
    wheat = ActivityAccountInput(
        activity_id="PLACEHOLDER_wheat_2024",
        crop_id="PLACEHOLDER_wheat",
        ag_year=2024,
        sale=_gross_sale(
            price=220.0,
            yield_=4.0,
            harvest=50.0,
            drying=10.0,
            freight=30.0,
            selling=20.0,
        ),
        pre_harvest_direct_cost=_val(350.0, COST_UNIT),
    )
    soy2 = ActivityAccountInput(
        activity_id="PLACEHOLDER_soy2_2024",
        crop_id="PLACEHOLDER_soybean_second",
        ag_year=2024,
        sale=_net_sale(price=340.0, yield_=2.0),
        pre_harvest_direct_cost=_val(300.0, COST_UNIT),
    )
    yr_2024 = AgYearAccountInput(
        ag_year=2024,
        activities=(wheat, soy2),
        structure_cost=_val(50.0, MARGIN_UNIT),
        paid_rent=_val(100.0, MARGIN_UNIT),
        own_land_opportunity_cost=_val(200.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(
            machinery_depreciation=_val(20.0, MARGIN_UNIT),
            other_depreciation=_val(10.0, MARGIN_UNIT),
        ),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2024, 6, 15),
                kind="payment",
                amount=_val(650.0, COST_UNIT),
            ),
            CashFlowEvent(
                date=dt.date(2025, 4, 20),
                kind="collection",
                amount=_val(1400.0, COST_UNIT),
            ),
        ),
    )

    maize = ActivityAccountInput(
        activity_id="PLACEHOLDER_maize_2025",
        crop_id="PLACEHOLDER_maize",
        ag_year=2025,
        sale=_net_sale(price=180.0, yield_=8.0),
        pre_harvest_direct_cost=_val(600.0, COST_UNIT),
    )
    yr_2025 = AgYearAccountInput(
        ag_year=2025,
        activities=(maize,),
        structure_cost=_val(50.0, MARGIN_UNIT),
        paid_rent=_val(100.0, MARGIN_UNIT),
        own_land_opportunity_cost=_val(200.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(
            machinery_depreciation=_val(20.0, MARGIN_UNIT),
            other_depreciation=_val(10.0, MARGIN_UNIT),
        ),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2025, 9, 15),
                kind="payment",
                amount=_val(750.0, COST_UNIT),
            ),
            CashFlowEvent(
                date=dt.date(2026, 5, 1),
                kind="collection",
                amount=_val(1440.0, COST_UNIT),
            ),
        ),
    )

    rot = RotationAccountInput(
        case_id="test-case",
        field_id="test-field",
        rotation_id="PLACEHOLDER_wheat_soy2_maize",
        years=(yr_2024, yr_2025),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2024, 6, 1),
                kind="investment",
                amount=_val(500.0, COST_UNIT),
            ),
            CashFlowEvent(
                date=dt.date(2026, 5, 30),
                kind="residual_value",
                amount=_val(260.0, COST_UNIT),
            ),
        ),
    )

    summary = compute_rotation_accounts(rot)
    assert isinstance(summary, EconomicAccountsSummary)
    assert summary.years_count == 2
    assert len(summary.activities) == 3
    assert len(summary.by_year) == 2
    assert summary.non_monetary_depreciation_excluded is True
    assert summary.accounts_kept_strictly_separate is True

    # Year checks
    assert summary.by_year[0].gross_margin_account.gross_margin.value == pytest.approx(
        800.0
    )
    assert summary.by_year[0].gross_margin_account.price_bases_present == (
        "gross",
        "net",
    )
    assert summary.by_year[
        0
    ].accounting_result_account.accounting_result.value == pytest.approx(620.0)
    assert summary.by_year[0].cash_flow_account.cash_flow.value == pytest.approx(750.0)

    assert summary.by_year[1].gross_margin_account.gross_margin.value == pytest.approx(
        840.0
    )
    assert summary.by_year[
        1
    ].accounting_result_account.accounting_result.value == pytest.approx(660.0)
    assert summary.by_year[1].cash_flow_account.cash_flow.value == pytest.approx(690.0)

    # Full rotation total checks
    assert summary.gross_margin_account.revenue.value == pytest.approx(3000.0)
    assert summary.gross_margin_account.direct_costs.value == pytest.approx(1360.0)
    assert summary.gross_margin_account.gross_margin.value == pytest.approx(1640.0)
    assert summary.accounting_result_account.paid_rent.value == pytest.approx(200.0)
    assert (
        summary.accounting_result_account.own_land_opportunity_cost.value
        == pytest.approx(400.0)
    )
    assert summary.accounting_result_account.accounting_result.value == pytest.approx(
        1280.0
    )
    assert summary.cash_flow_account.cash_flow.value == pytest.approx(1200.0)
    assert summary.cash_flow_account.by_date[
        -1
    ].cumulative_cash_flow.value == pytest.approx(1200.0)

    # Annual average checks
    assert summary.annual_average.gross_margin.value == pytest.approx(820.0)
    assert summary.annual_average.gross_margin.unit == MARGIN_UNIT
    assert summary.annual_average.accounting_result.value == pytest.approx(640.0)
    assert summary.annual_average.cash_flow.value == pytest.approx(600.0)

    # Never calls partial margin net_profit anywhere in JSON serialization
    dumped = summary.model_dump(mode="json")
    assert "net_profit" not in json.dumps(dumped).lower()

    # Exact JSON roundtrip (both dict and JSON string)
    reloaded = EconomicAccountsSummary.model_validate(dumped)
    assert reloaded == summary
    assert (
        EconomicAccountsSummary.model_validate_json(summary.model_dump_json())
        == summary
    )

    # Frozen immutability
    with pytest.raises(ValidationError):
        summary.years_count = 99  # type: ignore[misc]


def test_rotation_level_machinery_tariff_guard_and_rotation_only_cash_flow() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_rot_guard",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    yr_with_mach = AgYearAccountInput(
        ag_year=2024,
        activities=(act,),
        structure_cost=_val(40.0, MARGIN_UNIT),
        paid_rent=_val(0.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(
            machinery_depreciation=_val(25.0, MARGIN_UNIT),
            other_depreciation=_val(10.0, MARGIN_UNIT),
        ),
    )
    with pytest.raises(DoubleCountError):
        RotationAccountInput(
            case_id="test-case",
            field_id="test-field",
            rotation_id="PLACEHOLDER_bad_rot",
            years=(yr_with_mach,),
            machinery_tariff_includes_depreciation=True,
        )

    # Rotation-only cash_events computes full rotation cash flow while year is missing
    yr_clean = AgYearAccountInput(
        ag_year=2024,
        activities=(act,),
        structure_cost=_val(40.0, MARGIN_UNIT),
        paid_rent=_val(0.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(
            other_depreciation=_val(10.0, MARGIN_UNIT),
            machinery_tariff_includes_depreciation=True,
        ),
    )
    rot_ok = RotationAccountInput(
        case_id="test-case",
        field_id="test-field",
        rotation_id="PLACEHOLDER_rot_cf_only",
        years=(yr_clean,),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2025, 4, 1),
                kind="collection",
                amount=_val(900.0, COST_UNIT),
            ),
        ),
        machinery_tariff_includes_depreciation=True,
    )
    summary = compute_rotation_accounts(rot_ok)
    assert summary.cash_flow_account.cash_flow.value == pytest.approx(900.0)
    assert summary.annual_average.cash_flow.value == pytest.approx(900.0)
    _assert_missing_input(summary.by_year[0].cash_flow_account.cash_flow, MARGIN_UNIT)


def test_missing_price_and_yield_produce_missing_input_never_zero() -> None:
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_no_price",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=ActivitySaleSpec(
            price=_missing(PRICE_UNIT),
            yield_=_missing(YIELD_UNIT),
            price_basis="net",
        ),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    _assert_missing_input(res.gross_margin_account.revenue, COST_UNIT, "price")
    _assert_missing_input(res.gross_margin_account.gross_margin, COST_UNIT, "revenue")
    assert res.gross_margin_account.direct_costs.value == pytest.approx(500.0)
    _assert_missing_input(
        res.accounting_result_account.accounting_result, COST_UNIT, "gross_margin"
    )


def test_partial_year_missing_cash_flow_makes_rotation_cash_flow_missing() -> None:
    act1 = ActivityAccountInput(
        activity_id="PLACEHOLDER_y1",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    act2 = ActivityAccountInput(
        activity_id="PLACEHOLDER_y2",
        crop_id="PLACEHOLDER_maize",
        ag_year=2025,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    yr1 = AgYearAccountInput(
        ag_year=2024,
        activities=(act1,),
        structure_cost=_val(40.0, MARGIN_UNIT),
        paid_rent=_val(0.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(10.0, MARGIN_UNIT)),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2025, 3, 1),
                kind="collection",
                amount=_val(800.0, COST_UNIT),
            ),
        ),
    )
    yr2 = AgYearAccountInput(
        ag_year=2025,
        activities=(act2,),
        structure_cost=_val(40.0, MARGIN_UNIT),
        paid_rent=_val(0.0, MARGIN_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(10.0, MARGIN_UNIT)),
        cash_events=None,
    )
    rot = RotationAccountInput(
        case_id="test-case",
        field_id="test-field",
        rotation_id="PLACEHOLDER_partial_cf",
        years=(yr1, yr2),
        cash_events=(
            CashFlowEvent(
                date=dt.date(2024, 6, 1),
                kind="investment",
                amount=_val(100.0, COST_UNIT),
            ),
        ),
    )
    summary = compute_rotation_accounts(rot)
    assert summary.gross_margin_account.gross_margin.value == pytest.approx(1100.0)
    assert summary.accounting_result_account.accounting_result.value == pytest.approx(
        1000.0
    )
    _assert_missing_input(summary.by_year[1].cash_flow_account.cash_flow, MARGIN_UNIT)
    _assert_missing_input(summary.cash_flow_account.cash_flow, COST_UNIT, "2025")
    _assert_missing_input(summary.annual_average.cash_flow, MARGIN_UNIT, "2025")


# ---------------------------------------------------------------------------
# Structural validation & pure-function guards
# ---------------------------------------------------------------------------


def test_structural_guards_reject_bad_units_negatives_and_duplicates() -> None:
    with pytest.raises(ValueError, match="expected unit"):
        ActivitySaleSpec(
            price=_val(400.0, "USD kg-1"),
            yield_=_val(3.0, YIELD_UNIT),
            price_basis="net",
        )
    with pytest.raises(ValueError, match="negative"):
        ActivitySaleSpec(
            price=_val(-10.0, PRICE_UNIT),
            yield_=_val(3.0, YIELD_UNIT),
            price_basis="net",
        )
    with pytest.raises(ValueError, match="negative"):
        CashFlowEvent(
            date=dt.date(2024, 10, 1),
            kind="payment",
            amount=_val(-5.0, COST_UNIT),
        )

    act_a = ActivityAccountInput(
        activity_id="PLACEHOLDER_dup",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_net_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    with pytest.raises(ValueError, match="enclosing agricultural year"):
        AgYearAccountInput(ag_year=2025, activities=(act_a,))
    with pytest.raises(ValueError, match="duplicate activity_id"):
        AgYearAccountInput(ag_year=2024, activities=(act_a, act_a))

    yr = AgYearAccountInput(ag_year=2024, activities=(act_a,))
    with pytest.raises(ValueError, match="duplicate ag_year"):
        RotationAccountInput(
            case_id="test-case",
            field_id="test-field",
            rotation_id="PLACEHOLDER_dup_yr",
            years=(yr, yr),
        )


def test_activity_level_overheads_aggregate_into_ag_year() -> None:
    act1 = ActivityAccountInput(
        activity_id="PLACEHOLDER_a1",
        crop_id="PLACEHOLDER_wheat",
        ag_year=2024,
        sale=_net_sale(price=200.0, yield_=3.0),
        pre_harvest_direct_cost=_val(300.0, COST_UNIT),
        structure_cost=_val(20.0, COST_UNIT),
        paid_rent=_val(40.0, COST_UNIT),
        own_land_opportunity_cost=_val(80.0, COST_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(10.0, COST_UNIT)),
    )
    act2 = ActivityAccountInput(
        activity_id="PLACEHOLDER_a2",
        crop_id="PLACEHOLDER_soybean_second",
        ag_year=2024,
        sale=_net_sale(price=300.0, yield_=2.0),
        pre_harvest_direct_cost=_val(250.0, COST_UNIT),
        structure_cost=_val(30.0, COST_UNIT),
        paid_rent=_val(60.0, COST_UNIT),
        own_land_opportunity_cost=_val(120.0, COST_UNIT),
        depreciation=DepreciationSpec(relevant_depreciation=_val(15.0, COST_UNIT)),
    )
    # act1: gm = 300, acc = 300 - 20 - 40 - 10 = 230
    # act2: gm = 350, acc = 350 - 30 - 60 - 15 = 245
    # year: gm = 650, acc = 475
    yr_res = compute_ag_year_accounts(
        AgYearAccountInput(ag_year=2024, activities=(act1, act2))
    )
    assert yr_res.gross_margin_account.gross_margin.value == pytest.approx(650.0)
    assert yr_res.accounting_result_account.structure_cost.value == pytest.approx(50.0)
    assert yr_res.accounting_result_account.paid_rent.value == pytest.approx(100.0)
    assert (
        yr_res.accounting_result_account.own_land_opportunity_cost.value
        == pytest.approx(200.0)
    )
    assert (
        yr_res.accounting_result_account.relevant_depreciation.value
        == pytest.approx(25.0)
    )
    assert yr_res.accounting_result_account.accounting_result.value == pytest.approx(
        475.0
    )


def test_no_network_calls_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _deny_network(*args, **kwargs):
        raise AssertionError("network calls are forbidden in economics/accounts.py")

    monkeypatch.setattr(socket, "socket", _deny_network)
    act = ActivityAccountInput(
        activity_id="PLACEHOLDER_offline",
        crop_id="PLACEHOLDER_soybean",
        ag_year=2024,
        sale=_gross_sale(),
        pre_harvest_direct_cost=_val(500.0, COST_UNIT),
    )
    res = compute_activity_accounts(act)
    assert res.gross_margin_account.gross_margin.value == pytest.approx(550.0)
