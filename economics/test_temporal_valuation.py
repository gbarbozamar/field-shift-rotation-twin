"""Acceptance tests for unit l2/economics-temporal-npv-ae.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Specification: ``27_PLAN_DE_FRONTERA.md`` §13 and ``28_PLAN_INTEGRADO_REV13.md`` §4.

Every number in this file is invented test data from no source; expected
values follow by hand from the exact discounted cash-flow and equivalent
annuity formulas.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing
from economics.temporal_valuation import (
    RotationTemporalOption,
    TemporalValuationInput,
    TemporalValuationResult,
    compare_rotations_common_horizon,
    evaluate_temporal_valuation,
)


def _hand_npv(flows: dict[int, float], r: float) -> float:
    return sum(cf / ((1.0 + r) ** t) for t, cf in flows.items())


def _hand_ae(npv: float, r: float, n: int) -> float:
    if r == 0.0:
        return npv / n
    return npv * r / (1.0 - (1.0 + r) ** (-n))


# 1. Exact formulas: positive discount rate with full timed CF_t components


def test_exact_npv_and_ae_with_all_timed_components():
    # Horizon n = 5, r = 0.08
    # CF_0 = -500.0
    # Transition years 1..2: [-100.0, 50.0]
    # Repeated 2-year cycle [300.0, 400.0] starting in year 3:
    #   t=3 -> 300.0, t=4 -> 400.0, t=5 -> 300.0
    # Establishment/renovation: {3: -150.0} -> t=3 becomes 150.0
    # Terminal residual value: 250.0 -> t=5 becomes 550.0
    res = evaluate_temporal_valuation(
        rotation_id="rot_full",
        horizon_years=5,
        discount_rate=0.08,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-500.0,
        transition_cash_flows=[-100.0, 50.0],
        cycle_cash_flows=[300.0, 400.0],
        establishment_renovation_flows={3: -150.0},
        terminal_residual_value=250.0,
    )

    expected_annual = {1: -100.0, 2: 50.0, 3: 150.0, 4: 400.0, 5: 550.0}
    expected_timed = {0: -500.0, **expected_annual}
    expected_npv = _hand_npv(expected_timed, 0.08)
    expected_ae = _hand_ae(expected_npv, 0.08, 5)

    assert res.rotation_id == "rot_full"
    assert res.annual_cash_flows == expected_annual
    assert res.timed_cash_flows == expected_timed
    assert res.undiscounted_cycle_mean == pytest.approx(350.0)
    assert res.npv == pytest.approx(expected_npv, rel=1e-12)
    assert res.equivalent_annuity == pytest.approx(expected_ae, rel=1e-12)
    assert res.label_npv_as_discounted_present_value is True
    assert res.npv_label == "discounted_present_value"


def test_zero_discount_rate_uses_exact_limit_npv_over_n():
    res = evaluate_temporal_valuation(
        horizon_years=4,
        discount_rate=0.0,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-200.0,
        cycle_cash_flows=[100.0, 300.0],
    )

    assert res.annual_cash_flows == {1: 100.0, 2: 300.0, 3: 100.0, 4: 300.0}
    assert res.undiscounted_cycle_mean == pytest.approx(200.0)
    # NPV = -200 + 100 + 300 + 100 + 300 = 600
    assert res.npv == pytest.approx(600.0)
    # Exact limit ae = npv / n = 600 / 4 = 150
    assert res.equivalent_annuity == pytest.approx(150.0)
    assert res.equivalent_annuity != res.undiscounted_cycle_mean


def test_zero_discount_rate_no_cf0_aligns_ae_with_cycle_mean_over_multiple():
    res = evaluate_temporal_valuation(
        horizon_years=6,
        discount_rate=0.0,
        price_basis="nominal",
        rate_basis="nominal",
        cycle_cash_flows=[120.0, 180.0, 300.0],
    )

    assert res.undiscounted_cycle_mean == pytest.approx(200.0)
    assert res.npv == pytest.approx(1200.0)
    assert res.equivalent_annuity == pytest.approx(200.0)


def test_negative_discount_rate_above_minus_one_is_computable():
    # r = -0.5 > -1.0, n = 2, annual = [100, 100]
    # npv = 100 / 0.5 + 100 / 0.25 = 600.0
    # ae = 600 * (-0.5) / (1 - 0.5**(-2)) = -300 / -3 = 100.0
    res = evaluate_temporal_valuation(
        horizon_years=2,
        discount_rate=-0.5,
        price_basis="real",
        rate_basis="real",
        annual_cash_flows=[100.0, 100.0],
    )
    assert res.npv == pytest.approx(600.0)
    assert res.equivalent_annuity == pytest.approx(100.0)


def test_horizon_one_year_minimum_and_establishment_at_year_zero():
    res = evaluate_temporal_valuation(
        horizon_years=1,
        discount_rate=0.10,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-100.0,
        establishment_renovation_flows={0: -50.0, 1: -20.0},
        annual_cash_flows={1: 300.0},
        terminal_residual_value=40.0,
    )
    # CF_0 = -150, CF_1 = 300 - 20 + 40 = 320
    expected_npv = -150.0 + 320.0 / 1.10
    expected_ae = expected_npv * 0.10 / (1.0 - 1.10 ** (-1))
    assert res.cf0_investment == pytest.approx(-150.0)
    assert res.annual_cash_flows == {1: 320.0}
    assert res.npv == pytest.approx(expected_npv)
    assert res.equivalent_annuity == pytest.approx(expected_ae)


def test_strict_separation_of_annual_mean_npv_and_ae():
    res = evaluate_temporal_valuation(
        horizon_years=3,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[200.0, 350.0, 200.0],
    )
    assert isinstance(res.annual_cash_flows, dict)
    assert isinstance(res.undiscounted_cycle_mean, float)
    assert isinstance(res.npv, float)
    assert isinstance(res.equivalent_annuity, float)
    assert res.undiscounted_cycle_mean == pytest.approx(250.0)
    # Discounting lowers AE relative to undiscounted mean here
    assert res.equivalent_annuity != res.undiscounted_cycle_mean
    assert res.npv != res.undiscounted_cycle_mean
    assert res.label_npv_as_discounted_present_value is True
    dumped = res.model_dump(mode="json")
    assert dumped["label_npv_as_discounted_present_value"] is True
    assert "VAN" not in dumped["npv_label"]


def test_accepts_temporal_valuation_input_model_directly():
    spec = TemporalValuationInput(
        rotation_id="rot_a",
        horizon_years=3,
        discount_rate=0.06,
        price_basis="nominal",
        rate_basis="nominal",
        annual_cash_flows={1: 100.0, 2: 200.0, 3: 300.0},
        transition_cash_flows={2: -25.0},
    )
    res = evaluate_temporal_valuation(spec)
    assert res.annual_cash_flows == {1: 100.0, 2: 175.0, 3: 300.0}
    expected_npv = _hand_npv(res.timed_cash_flows, 0.06)
    assert res.npv == pytest.approx(expected_npv)


# 2. Guard 1: Real vs nominal consistency


@pytest.mark.parametrize(
    ("price_basis", "rate_basis"),
    [("real", "nominal"), ("nominal", "real")],
)
def test_real_vs_nominal_mismatch_raises_value_error(price_basis, rate_basis):
    with pytest.raises(ValueError, match="consistency"):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=0.05,
            price_basis=price_basis,
            rate_basis=rate_basis,
            cycle_cash_flows=[100.0],
        )


# 3. Guard 3: Double deduction guard (non-monetary depreciation + cf0_investment != 0)


def test_double_deduction_guard_rejects_depreciation_with_cf0():
    with pytest.raises(ValueError, match="double deduction"):
        evaluate_temporal_valuation(
            horizon_years=4,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            cf0_investment=-1000.0,
            cycle_cash_flows=[400.0],
            includes_non_monetary_depreciation=True,
        )


def test_double_deduction_guard_rejects_depreciation_with_annual_t0():
    with pytest.raises(ValueError, match="double deduction"):
        evaluate_temporal_valuation(
            horizon_years=2,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            annual_cash_flows={0: -500.0, 1: 300.0, 2: 300.0},
            includes_non_monetary_depreciation=True,
        )


def test_depreciation_allowed_when_cf0_is_zero():
    res = evaluate_temporal_valuation(
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cf0_investment=0.0,
        cycle_cash_flows=[300.0],
        includes_non_monetary_depreciation=True,
    )
    assert res.includes_non_monetary_depreciation is True
    assert res.cf0_investment == 0.0


# 4. Guard 4: r <= -1.0, non-finite values, and Missing propagation


@pytest.mark.parametrize("bad_r", [-1.0, -1.01, -2.5])
def test_discount_rate_at_or_below_minus_one_fails_not_computable(bad_r):
    with pytest.raises(ValueError, match="NOT_COMPUTABLE"):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=bad_r,
            price_basis="real",
            rate_basis="real",
            cycle_cash_flows=[100.0],
        )


@pytest.mark.parametrize("bad_val", [math.nan, math.inf, -math.inf])
def test_non_finite_discount_rate_or_cash_flow_fails_not_computable(bad_val):
    with pytest.raises(ValueError, match="NOT_COMPUTABLE"):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=bad_val,
            price_basis="real",
            rate_basis="real",
            cycle_cash_flows=[100.0],
        )

    with pytest.raises(ValueError, match="NOT_COMPUTABLE"):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            annual_cash_flows=[100.0, bad_val, 100.0],
        )

    with pytest.raises(ValueError, match="NOT_COMPUTABLE"):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            cf0_investment=bad_val,
            cycle_cash_flows=[100.0],
        )


def test_overflow_during_discounting_fails_not_computable():
    with pytest.raises(ValueError, match="NOT_COMPUTABLE"):
        evaluate_temporal_valuation(
            horizon_years=1000,
            discount_rate=-0.9,
            price_basis="real",
            rate_basis="real",
            cycle_cash_flows=[1e200],
        )


def test_missing_year_flow_propagates_missing_input():
    missing_y2 = Missing(reason="MISSING_INPUT", detail="year 2 soybean price missing")
    res = evaluate_temporal_valuation(
        horizon_years=3,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-100.0,
        annual_cash_flows=[200.0, missing_y2, 250.0],
    )

    assert res.annual_cash_flows[1] == 200.0
    assert res.annual_cash_flows[2] == missing_y2
    assert res.annual_cash_flows[3] == 250.0
    assert isinstance(res.npv, Missing)
    assert res.npv.reason == "MISSING_INPUT"
    assert "year 2" in (res.npv.detail or "")
    assert isinstance(res.equivalent_annuity, Missing)
    assert res.equivalent_annuity.reason == "MISSING_INPUT"
    assert isinstance(res.undiscounted_cycle_mean, Missing)
    assert res.undiscounted_cycle_mean.reason == "MISSING_INPUT"


def test_missing_inputs_common_missing_normalized_to_missing_input():
    missing_flow = InputsMissing(reason="NOT_DECLARED", detail="yield not declared")
    res = evaluate_temporal_valuation(
        horizon_years=4,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[300.0, missing_flow],
    )
    assert isinstance(res.annual_cash_flows[2], Missing)
    assert isinstance(res.npv, Missing)
    assert res.npv.reason == "MISSING_INPUT"
    assert isinstance(res.equivalent_annuity, Missing)
    assert res.equivalent_annuity.reason == "MISSING_INPUT"
    assert isinstance(res.undiscounted_cycle_mean, Missing)
    assert res.undiscounted_cycle_mean.reason == "MISSING_INPUT"


def test_missing_cf0_or_residual_propagates_to_npv_and_ae():
    missing_cf0 = Missing(reason="NOT_DECLARED", detail="establishment quote pending")
    res = evaluate_temporal_valuation(
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cf0_investment=missing_cf0,
        cycle_cash_flows=[200.0, 300.0],
    )
    assert isinstance(res.npv, Missing)
    assert res.npv.reason == "MISSING_INPUT"
    assert isinstance(res.equivalent_annuity, Missing)
    assert res.equivalent_annuity.reason == "MISSING_INPUT"
    # Cycle operating mean itself is known from cycle_cash_flows
    assert res.undiscounted_cycle_mean == pytest.approx(250.0)


# 5. Guard 2 & Comparison: compare_rotations_common_horizon


def test_compare_rotations_common_horizon_ranks_different_cycle_lengths():
    # Compare 2-year cycle vs 3-year cycle over LCM horizon n = 6, r = 0.06
    rot_2yr = evaluate_temporal_valuation(
        rotation_id="rot_2yr",
        horizon_years=6,
        discount_rate=0.06,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-400.0,
        cycle_cash_flows=[250.0, 350.0],
    )
    rot_3yr = TemporalValuationInput(
        rotation_id="rot_3yr",
        horizon_years=6,
        discount_rate=0.06,
        price_basis="real",
        rate_basis="real",
        cf0_investment=-200.0,
        cycle_cash_flows=[220.0, 320.0, 260.0],
    )

    comp = compare_rotations_common_horizon([rot_2yr, rot_3yr])

    assert comp.status == "resolved"
    assert comp.horizon_years == 6
    assert comp.discount_rate == 0.06
    assert comp.price_basis == "real"
    assert comp.rate_basis == "real"
    assert comp.missing is None
    assert comp.tied_rotation_ids == ()
    assert comp.best_rotation_id == comp.ranked_rotation_ids[0]
    assert set(comp.ranked_rotation_ids) == {"rot_2yr", "rot_3yr"}
    npv_2 = comp.options["rot_2yr"].npv
    npv_3 = comp.options["rot_3yr"].npv
    assert isinstance(npv_2, float) and isinstance(npv_3, float)
    expected_best = "rot_2yr" if npv_2 > npv_3 else "rot_3yr"
    assert comp.best_rotation_id == expected_best
    assert comp.label_npv_as_discounted_present_value is True


def test_compare_rejects_unequal_horizon():
    a = evaluate_temporal_valuation(
        rotation_id="A",
        horizon_years=4,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[100.0],
    )
    b = evaluate_temporal_valuation(
        rotation_id="B",
        horizon_years=6,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[100.0],
    )
    with pytest.raises(ValueError, match="common horizon"):
        compare_rotations_common_horizon([a, b])


def test_compare_rejects_different_discount_basis_or_rate():
    real_opt = evaluate_temporal_valuation(
        rotation_id="A",
        horizon_years=4,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[100.0],
    )
    nominal_opt = evaluate_temporal_valuation(
        rotation_id="B",
        horizon_years=4,
        discount_rate=0.05,
        price_basis="nominal",
        rate_basis="nominal",
        cycle_cash_flows=[100.0],
    )
    with pytest.raises(ValueError, match="discount basis"):
        compare_rotations_common_horizon([real_opt, nominal_opt])

    diff_rate_opt = evaluate_temporal_valuation(
        rotation_id="C",
        horizon_years=4,
        discount_rate=0.08,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[100.0],
    )
    with pytest.raises(ValueError, match="discount rate"):
        compare_rotations_common_horizon([real_opt, diff_rate_opt])


def test_compare_handles_exact_tie_and_missing_input():
    a = evaluate_temporal_valuation(
        rotation_id="A",
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        annual_cash_flows=[100.0, 200.0],
    )
    b = evaluate_temporal_valuation(
        rotation_id="B",
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        annual_cash_flows=[100.0, 200.0],
    )
    tied = compare_rotations_common_horizon(
        [
            RotationTemporalOption(rotation_id="A", valuation=a),
            RotationTemporalOption(rotation_id="B", valuation=b),
        ]
    )
    assert tied.status == "tied"
    assert tied.best_rotation_id is None
    assert tied.tied_rotation_ids == ("A", "B")
    assert tied.missing is not None
    assert tied.missing.reason == "NOT_COMPUTABLE"

    missing_c = evaluate_temporal_valuation(
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        annual_cash_flows=[100.0, Missing(reason="MISSING_INPUT", detail="y2 missing")],
    )
    unresolved = compare_rotations_common_horizon({"A": a, "C": missing_c})
    assert unresolved.status == "not_resolved"
    assert unresolved.best_rotation_id is None
    assert unresolved.ranked_rotation_ids == ()
    assert unresolved.missing is not None
    assert unresolved.missing.reason == "MISSING_INPUT"
    assert "C" in (unresolved.missing.detail or "")


# 6. Structural misuse and immutability


def test_structural_misuse_and_immutability():
    with pytest.raises(ValueError):
        evaluate_temporal_valuation(
            horizon_years=0,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            cycle_cash_flows=[100.0],
        )

    with pytest.raises(ValueError):
        evaluate_temporal_valuation(
            horizon_years=True,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            cycle_cash_flows=[100.0],
        )

    with pytest.raises(ValueError):
        evaluate_temporal_valuation(
            horizon_years=3,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            annual_cash_flows=[100.0, 200.0],
        )

    with pytest.raises(ValueError):
        evaluate_temporal_valuation(
            horizon_years=2,
            discount_rate=0.05,
            price_basis="real",
            rate_basis="real",
            annual_cash_flows=[100.0, 200.0],
            cycle_cash_flows=[150.0],
        )

    with pytest.raises(ValueError):
        compare_rotations_common_horizon([])

    with pytest.raises(ValueError):
        compare_rotations_common_horizon("AB")

    res = evaluate_temporal_valuation(
        horizon_years=2,
        discount_rate=0.05,
        price_basis="real",
        rate_basis="real",
        cycle_cash_flows=[100.0, 200.0],
    )
    assert isinstance(res, TemporalValuationResult)
    with pytest.raises(ValidationError):
        res.npv = 999.0  # type: ignore[misc]
