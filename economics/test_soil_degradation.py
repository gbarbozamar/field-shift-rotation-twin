"""Acceptance tests for Frontier Unit F-19 (``economics/soil_degradation.py``).

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Run from the repository root:
``pytest economics/test_soil_degradation.py -q``.

Every number in this file is invented test data: no field, no record, no
market price, no bulk density, and no source. Each expected output is computed
explicitly by hand from the PROPOSED rules.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from contracts.inputs.common import Missing
from economics.soil_degradation import (
    DEFAULT_QUALITATIVE_VOI_PRIORITY,
    UNIT_T_PER_HA,
    UNIT_USD_PER_HA,
    UNIT_USD_PER_HA_YR,
    UNIT_USD_PER_MG,
    UNIT_USD_PER_T,
    BreakEvenPrice,
    BreakEvenYield,
    CvarResult,
    SoilConservationCost,
    SoilDegradationValuation,
    VoiResult,
    compute_break_even_price,
    compute_break_even_yield,
    compute_cvar_worst_years,
    compute_evpi_and_evsi,
    erosion_mm_per_year,
    mass_per_mm_Mg_ha,
    soil_conservation_cost,
    sum_valuation_methods,
    value_nutrient_replacement,
    value_productivity_loss,
    value_soil_years_land_value,
)

# ---------------------------------------------------------------------------
# 1. Soil-depth conversion helpers
# ---------------------------------------------------------------------------


def test_erosion_mm_per_year_exact_si_conversion() -> None:
    # 1 mm at bulk density 1.3 Mg/m3 = 10 * 1.3 = 13.0 Mg/ha.
    assert mass_per_mm_Mg_ha(1.3) == pytest.approx(13.0)
    assert erosion_mm_per_year(13.0, 1.3) == pytest.approx(1.0)
    assert erosion_mm_per_year(26.0, 1.3) == pytest.approx(2.0)
    assert erosion_mm_per_year(0.0, 1.25) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("loss", "rho_b"),
    [
        (-0.1, 1.3),
        (5.0, 0.0),
        (5.0, -1.3),
        (True, 1.3),
        (5.0, False),
        (math.nan, 1.3),
        (5.0, math.inf),
        ("5.0", 1.3),
    ],
)
def test_erosion_mm_per_year_rejects_invalid_inputs(loss, rho_b) -> None:
    with pytest.raises(ValueError):
        erosion_mm_per_year(loss, rho_b)


# ---------------------------------------------------------------------------
# 2. Mutually exclusive, non-additive analytical valuation methods
# ---------------------------------------------------------------------------


def test_nutrient_replacement_valuation_and_tags() -> None:
    # Invented data: 10 Mg/ha/yr * ER 1.2 * (2.0 kg N * 1.5 USD/kg + 0.5 kg P * 3.0 USD/kg)
    # = 10 * 1.2 * (3.0 + 1.5) = 54.0 USD/ha/yr.
    res = value_nutrient_replacement(
        soil_loss_Mg_ha_yr=10.0,
        nutrient_kg_per_Mg={"N": 2.0, "P": 0.5},
        nutrient_price_usd_per_kg={"N": 1.5, "P": 3.0},
        enrichment_ratio=1.2,
    )
    assert isinstance(res, SoilDegradationValuation)
    assert res.method == "nutrient_replacement"
    assert res.method_maturity == "ANALYTICAL_PROXY"
    assert res.value_usd_ha_yr == pytest.approx(54.0)
    assert res.unit == UNIT_USD_PER_HA_YR
    assert res.not_observed_cash_outflow is True
    assert res.fertilizer_does_not_restore_structure_or_soc is True
    assert res.mutually_exclusive_non_additive is True
    assert res.already_deducted_in_revenue is False


def test_productivity_loss_valuation_and_double_counting_guard() -> None:
    # Invented data: 0.25 t/ha/yr * 320 USD/t + 15 USD/ha/yr = 95.0 USD/ha/yr.
    res = value_productivity_loss(
        annual_yield_loss_t_ha_yr=0.25,
        crop_price_usd_per_t=320.0,
        additional_input_cost_usd_ha_yr=15.0,
        already_deducted_in_revenue=False,
    )
    assert res.method == "productivity_loss"
    assert res.method_maturity == "ANALYTICAL_PROXY"
    assert res.value_usd_ha_yr == pytest.approx(95.0)
    assert res.not_observed_cash_outflow is True
    assert res.fertilizer_does_not_restore_structure_or_soc is True

    with pytest.raises(ValueError, match="already_deducted_in_revenue"):
        value_productivity_loss(
            annual_yield_loss_t_ha_yr=0.25,
            crop_price_usd_per_t=320.0,
            already_deducted_in_revenue=True,
        )


def test_soil_years_land_value_hypothesis_and_guards() -> None:
    # Invented data: 13.0 Mg/ha/yr at rho_b=1.3 -> 1.0 mm/yr.
    # Measured depth 400 mm, min functional 100 mm -> usable 300 mm -> 300 years.
    # Land value 6000 USD/ha -> 6000 / 300 = 20.0 USD/ha/yr.
    res = value_soil_years_land_value(
        soil_loss_Mg_ha_yr=13.0,
        bulk_density_Mg_m3=1.3,
        measured_soil_depth_mm=400.0,
        minimum_functional_depth_mm=100.0,
        land_value_usd_ha=6000.0,
        already_deducted_in_revenue=False,
    )
    assert isinstance(res, SoilDegradationValuation)
    assert res.method == "soil_years_land_value"
    assert res.method_maturity == "HYPOTHESIS"
    assert res.erosion_rate_mm_yr == pytest.approx(1.0)
    assert res.remaining_soil_years == pytest.approx(300.0)
    assert res.value_usd_ha_yr == pytest.approx(20.0)
    assert res.not_observed_cash_outflow is True
    assert res.fertilizer_does_not_restore_structure_or_soc is True

    # Zero erosion yields 0 depletion cost and None remaining_soil_years.
    zero_res = value_soil_years_land_value(
        soil_loss_Mg_ha_yr=0.0,
        bulk_density_Mg_m3=1.3,
        measured_soil_depth_mm=400.0,
        land_value_usd_ha=6000.0,
    )
    assert isinstance(zero_res, SoilDegradationValuation)
    assert zero_res.value_usd_ha_yr == pytest.approx(0.0)
    assert zero_res.remaining_soil_years is None

    # Missing measured soil depth returns Missing(reason="MISSING_INPUT").
    missing_depth = value_soil_years_land_value(
        soil_loss_Mg_ha_yr=13.0,
        bulk_density_Mg_m3=1.3,
        measured_soil_depth_mm=None,
        land_value_usd_ha=6000.0,
    )
    assert isinstance(missing_depth, Missing)
    assert missing_depth.reason == "MISSING_INPUT"
    assert missing_depth.detail is not None
    assert "measured_soil_depth_mm" in missing_depth.detail

    # Double-counting guard raises ValueError.
    with pytest.raises(ValueError, match="already_deducted_in_revenue"):
        value_soil_years_land_value(
            soil_loss_Mg_ha_yr=13.0,
            bulk_density_Mg_m3=1.3,
            measured_soil_depth_mm=400.0,
            land_value_usd_ha=6000.0,
            already_deducted_in_revenue=True,
        )


def test_refuses_summing_valuation_methods_and_mutation() -> None:
    v_nut = value_nutrient_replacement(
        soil_loss_Mg_ha_yr=5.0,
        nutrient_kg_per_Mg={"N": 2.0},
        nutrient_price_usd_per_kg={"N": 1.0},
    )
    v_prod = value_productivity_loss(
        annual_yield_loss_t_ha_yr=0.1,
        crop_price_usd_per_t=200.0,
    )
    v_land = value_soil_years_land_value(
        soil_loss_Mg_ha_yr=13.0,
        bulk_density_Mg_m3=1.3,
        measured_soil_depth_mm=300.0,
        land_value_usd_ha=3000.0,
    )
    assert isinstance(v_land, SoilDegradationValuation)

    with pytest.raises(ValueError, match="non-additive"):
        _ = v_nut + v_prod

    with pytest.raises(ValueError, match="non-additive"):
        _ = sum([v_nut, v_prod])

    with pytest.raises(ValueError, match="non-additive"):
        sum_valuation_methods([v_nut, v_prod, v_land])

    with pytest.raises(ValueError, match="non-additive"):
        sum_valuation_methods([v_nut])

    with pytest.raises(ValidationError):
        v_nut.value_usd_ha_yr = 999.0  # type: ignore[misc]


def test_valuation_input_validation_errors() -> None:
    with pytest.raises(ValueError):
        value_nutrient_replacement(
            soil_loss_Mg_ha_yr=5.0,
            nutrient_kg_per_Mg={},
            nutrient_price_usd_per_kg={"N": 1.0},
        )
    with pytest.raises(ValueError):
        value_nutrient_replacement(
            soil_loss_Mg_ha_yr=5.0,
            nutrient_kg_per_Mg={"N": 1.0, "P": 0.5},
            nutrient_price_usd_per_kg={"N": 1.0},
        )
    with pytest.raises(ValueError):
        value_soil_years_land_value(
            soil_loss_Mg_ha_yr=5.0,
            bulk_density_Mg_m3=1.3,
            measured_soil_depth_mm=100.0,
            minimum_functional_depth_mm=100.0,
            land_value_usd_ha=5000.0,
        )


# ---------------------------------------------------------------------------
# 3. Incremental conservation cost
# ---------------------------------------------------------------------------


def test_soil_conservation_cost_and_symmetry() -> None:
    # (300 - 250) / (10 - 5) = 10.0 USD/Mg.
    res = soil_conservation_cost(
        margin_a=300.0,
        margin_b=250.0,
        loss_a=10.0,
        loss_b=5.0,
        horizon_a=10,
        horizon_b=10,
    )
    assert isinstance(res, SoilConservationCost)
    assert res.cost_usd_per_Mg == pytest.approx(10.0)
    assert res.unit == UNIT_USD_PER_MG
    assert res.horizon_years == 10
    assert res.incremental_indicator_not_universal_soil_price is True
    assert res.is_win_win is False

    # Swapping A and B yields identical cost per Mg conserved.
    swapped = soil_conservation_cost(
        margin_a=250.0,
        margin_b=300.0,
        loss_a=5.0,
        loss_b=10.0,
        horizon_a=10,
        horizon_b=10,
    )
    assert isinstance(swapped, SoilConservationCost)
    assert swapped.cost_usd_per_Mg == pytest.approx(10.0)


def test_soil_conservation_cost_win_win_zero_diff_and_horizon_mismatch() -> None:
    # Lower loss AND higher margin -> negative incremental cost (win-win).
    win_win = soil_conservation_cost(
        margin_a=260.0,
        margin_b=300.0,
        loss_a=12.0,
        loss_b=4.0,
        horizon_a=6,
        horizon_b=6,
    )
    assert isinstance(win_win, SoilConservationCost)
    assert win_win.cost_usd_per_Mg == pytest.approx(-5.0)
    assert win_win.is_win_win is True
    assert win_win.incremental_indicator_not_universal_soil_price is True

    # Equal soil loss -> Missing(reason="NOT_COMPUTABLE").
    zero_diff = soil_conservation_cost(
        margin_a=300.0,
        margin_b=250.0,
        loss_a=5.0,
        loss_b=5.0,
        horizon_a=10,
        horizon_b=10,
    )
    assert isinstance(zero_diff, Missing)
    assert zero_diff.reason == "NOT_COMPUTABLE"

    # Horizon mismatch -> ValueError.
    with pytest.raises(ValueError, match="horizon_a"):
        soil_conservation_cost(
            margin_a=300.0,
            margin_b=250.0,
            loss_a=10.0,
            loss_b=5.0,
            horizon_a=10,
            horizon_b=12,
        )

    # Non-positive horizon or bool -> ValueError.
    with pytest.raises(ValueError):
        soil_conservation_cost(300.0, 250.0, 10.0, 5.0, 0, 0)
    with pytest.raises(ValueError):
        soil_conservation_cost(300.0, 250.0, 10.0, 5.0, True, True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. Financial tail-risk metrics (CVaR & break-even price / yield)
# ---------------------------------------------------------------------------


def test_compute_cvar_worst_years_exact_and_fractional_tails() -> None:
    # Sorted: [-200, -50, 100, 150, 250]; N=5, mean=50.0.
    margins = [150.0, -200.0, 250.0, -50.0, 100.0]

    # tail_fraction=0.2 -> effective_k=1.0 -> worst 1 year = -200.0.
    cvar_20 = compute_cvar_worst_years(margins, 0.2)
    assert isinstance(cvar_20, CvarResult)
    assert cvar_20.cvar_usd_ha_yr == pytest.approx(-200.0)
    assert cvar_20.worst_year_margin_usd_ha_yr == pytest.approx(-200.0)
    assert cvar_20.mean_margin_usd_ha_yr == pytest.approx(50.0)
    assert cvar_20.year_count == 5
    assert cvar_20.unit == UNIT_USD_PER_HA_YR
    assert cvar_20.not_a_probability_forecast is True

    # tail_fraction=0.4 -> effective_k=2.0 -> mean of [-200, -50] = -125.0.
    cvar_40 = compute_cvar_worst_years(margins, 0.4)
    assert cvar_40.cvar_usd_ha_yr == pytest.approx(-125.0)
    assert cvar_40.var_threshold_usd_ha_yr == pytest.approx(-50.0)

    # tail_fraction=1.0 -> overall mean = 50.0.
    cvar_100 = compute_cvar_worst_years(margins, 1.0)
    assert cvar_100.cvar_usd_ha_yr == pytest.approx(50.0)

    # Fractional tail: [-100, 0, 100, 200], tail_fraction=0.3 -> k=1.2.
    # (1.0 * (-100) + 0.2 * 0) / 1.2 = -100 / 1.2.
    cvar_frac = compute_cvar_worst_years([-100.0, 0.0, 100.0, 200.0], 0.3)
    assert cvar_frac.cvar_usd_ha_yr == pytest.approx(-100.0 / 1.2)
    assert cvar_frac.worst_year_margin_usd_ha_yr <= cvar_frac.cvar_usd_ha_yr
    assert cvar_frac.cvar_usd_ha_yr <= cvar_frac.mean_margin_usd_ha_yr


@pytest.mark.parametrize(
    ("margins", "tail_fraction"),
    [
        ([], 0.2),
        ("123", 0.2),
        ([100.0, math.nan], 0.5),
        ([100.0, True], 0.5),
        ([100.0, 200.0], 0.0),
        ([100.0, 200.0], -0.1),
        ([100.0, 200.0], 1.1),
        ([100.0, 200.0], True),
    ],
)
def test_compute_cvar_rejects_invalid_inputs(margins, tail_fraction) -> None:
    with pytest.raises(ValueError):
        compute_cvar_worst_years(margins, tail_fraction)


def test_break_even_price_and_yield() -> None:
    bep = compute_break_even_price(600.0, 3.0)
    assert isinstance(bep, BreakEvenPrice)
    assert bep.break_even_price_usd_per_t == pytest.approx(200.0)
    assert bep.unit == UNIT_USD_PER_T

    bep_target = compute_break_even_price(600.0, 3.0, target_margin_usd_ha=150.0)
    assert isinstance(bep_target, BreakEvenPrice)
    assert bep_target.break_even_price_usd_per_t == pytest.approx(250.0)

    bey = compute_break_even_yield(600.0, 250.0)
    assert isinstance(bey, BreakEvenYield)
    assert bey.break_even_yield_t_ha == pytest.approx(2.4)
    assert bey.unit == UNIT_T_PER_HA

    bey_target = compute_break_even_yield(600.0, 250.0, target_margin_usd_ha=150.0)
    assert isinstance(bey_target, BreakEvenYield)
    assert bey_target.break_even_yield_t_ha == pytest.approx(3.0)

    zero_yld = compute_break_even_price(600.0, 0.0)
    assert isinstance(zero_yld, Missing)
    assert zero_yld.reason == "NOT_COMPUTABLE"

    zero_price = compute_break_even_yield(600.0, 0.0)
    assert isinstance(zero_price, Missing)
    assert zero_price.reason == "NOT_COMPUTABLE"

    with pytest.raises(ValueError):
        compute_break_even_price(600.0, -1.0)
    with pytest.raises(ValueError):
        compute_break_even_yield(600.0, -10.0)


# ---------------------------------------------------------------------------
# 5. Monetary Value of Information (EVPI & EVSI)
# ---------------------------------------------------------------------------


def _sample_voi_inputs() -> dict:
    # Invented 2-state, 2-action Bayesian problem:
    # Prior: P(low)=0.4, P(high)=0.6
    # Utilities (USD/ha):
    #   action_a: low -> 100, high -> 400 => EU = 0.4*100 + 0.6*400 = 280
    #   action_b: low -> 250, high -> 200 => EU = 0.4*250 + 0.6*200 = 220
    # Optimal prior = action_a (280).
    # Perfect info: 0.4*250 + 0.6*400 = 100 + 240 = 340 => EVPI = 340 - 280 = 60.
    # Likelihood P(z | s):
    #   low:  z_low=0.8, z_high=0.2
    #   high: z_low=0.1, z_high=0.9
    # Joint weights:
    #   z_low:  action_a -> 0.8*0.4*100 + 0.1*0.6*400 = 32 + 24 = 56
    #           action_b -> 0.8*0.4*250 + 0.1*0.6*200 = 80 + 12 = 92 (best)
    #   z_high: action_a -> 0.2*0.4*100 + 0.9*0.6*400 = 8 + 216 = 224 (best)
    #           action_b -> 0.2*0.4*250 + 0.9*0.6*200 = 20 + 108 = 128
    # EU_sample = 92 + 224 = 316 => EVSI = 316 - 280 = 36.
    # With measurement_cost = 12 => net_EVSI = 36 - 12 = 24.
    return {
        "economic_utility_matrix": {
            "action_a": {"low": 100.0, "high": 400.0},
            "action_b": {"low": 250.0, "high": 200.0},
        },
        "state_prior": {"low": 0.4, "high": 0.6},
        "measurement_error_likelihood": {
            "low": {"z_low": 0.8, "z_high": 0.2},
            "high": {"z_low": 0.1, "z_high": 0.9},
        },
        "admissible_actions": ["action_a", "action_b"],
        "measurement_cost_usd_ha": 12.0,
    }


def test_compute_evpi_and_evsi_exact_bayesian_values() -> None:
    inputs = _sample_voi_inputs()
    res = compute_evpi_and_evsi(**inputs)
    assert isinstance(res, VoiResult)
    assert res.missing is None
    assert res.reason is None
    assert res.unit == UNIT_USD_PER_HA
    assert res.optimal_prior_action == "action_a"
    assert res.expected_utility_without_info_usd_ha == pytest.approx(280.0)
    assert res.evpi_usd_ha == pytest.approx(60.0)
    assert res.evsi_usd_ha == pytest.approx(36.0)
    assert res.net_evsi_usd_ha == pytest.approx(24.0)
    assert res.evsi_usd_ha is not None and res.evpi_usd_ha is not None
    assert res.evsi_usd_ha <= res.evpi_usd_ha
    assert res.measurement_worthwhile is True


def test_compute_evpi_and_evsi_uninformative_and_noiseless_limits() -> None:
    inputs = _sample_voi_inputs()

    # Completely uninformative signal: P(z | s) identical for all states -> EVSI = 0.
    uninformative = dict(inputs)
    uninformative["measurement_error_likelihood"] = {
        "low": {"z1": 0.5, "z2": 0.5},
        "high": {"z1": 0.5, "z2": 0.5},
    }
    res_uninf = compute_evpi_and_evsi(**uninformative)
    assert res_uninf.evpi_usd_ha == pytest.approx(60.0)
    assert res_uninf.evsi_usd_ha == pytest.approx(0.0)
    assert res_uninf.net_evsi_usd_ha == pytest.approx(-12.0)
    assert res_uninf.measurement_worthwhile is False

    # Noiseless measurement -> EVSI == EVPI.
    noiseless = dict(inputs)
    noiseless["measurement_error_likelihood"] = {
        "low": {"z_low": 1.0, "z_high": 0.0},
        "high": {"z_low": 0.0, "z_high": 1.0},
    }
    res_perf = compute_evpi_and_evsi(**noiseless)
    assert res_perf.evsi_usd_ha == pytest.approx(res_perf.evpi_usd_ha)
    assert res_perf.net_evsi_usd_ha == pytest.approx(48.0)


@pytest.mark.parametrize(
    "omitted_key",
    [
        "economic_utility_matrix",
        "state_prior",
        "measurement_error_likelihood",
        "admissible_actions",
        "measurement_cost_usd_ha",
    ],
)
def test_compute_evpi_and_evsi_returns_missing_when_any_input_is_none(
    omitted_key: str,
) -> None:
    inputs = _sample_voi_inputs()
    inputs[omitted_key] = None

    res = compute_evpi_and_evsi(**inputs)
    assert isinstance(res, VoiResult)
    assert res.evpi_usd_ha is None
    assert res.evsi_usd_ha is None
    assert res.net_evsi_usd_ha is None
    assert isinstance(res.missing, Missing)
    assert res.missing.reason == "MISSING_INPUT"
    assert res.reason == "MISSING_INPUT"
    assert res.missing.detail is not None
    assert omitted_key in res.missing.detail
    assert res.qualitative_priority == DEFAULT_QUALITATIVE_VOI_PRIORITY

    res_custom = compute_evpi_and_evsi(**inputs, qualitative_priority="HIGH_PRIORITY")
    assert res_custom.qualitative_priority == "HIGH_PRIORITY"
    assert res_custom.evpi_usd_ha is None


def test_compute_evpi_and_evsi_rejects_malformed_inputs() -> None:
    bad_prior = _sample_voi_inputs()
    bad_prior["state_prior"] = {"low": 0.4, "high": 0.5}
    with pytest.raises(ValueError, match="sum to 1.0"):
        compute_evpi_and_evsi(**bad_prior)

    bad_likelihood = _sample_voi_inputs()
    bad_likelihood["measurement_error_likelihood"] = {
        "low": {"z_low": 0.5, "z_high": 0.6},
        "high": {"z_low": 0.1, "z_high": 0.9},
    }
    with pytest.raises(ValueError, match="sum to 1.0"):
        compute_evpi_and_evsi(**bad_likelihood)

    bad_cost = _sample_voi_inputs()
    bad_cost["measurement_cost_usd_ha"] = -1.0
    with pytest.raises(ValueError):
        compute_evpi_and_evsi(**bad_cost)

    bad_matrix = _sample_voi_inputs()
    bad_matrix["economic_utility_matrix"] = {"action_a": {"low": 100.0, "high": 400.0}}
    with pytest.raises(ValueError):
        compute_evpi_and_evsi(**bad_matrix)
