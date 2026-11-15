"""Tests for Frontier Unit F-14 differentiable/KGML/conformal/Bayesian blocks.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

All numbers in this test file are synthetic placeholders used solely to verify
exact algebraic, conservation, conformal, and Bayesian properties.
"""

from __future__ import annotations

import dataclasses
import math
import sys

import pytest

from contracts.results.models import Missing
from engine.water import twin_calibration as tc
from engine.water.twin_calibration import (
    ConformalSample,
    DifferentiableSensitivityResult,
    Dual,
    SplitConformalResult,
    differentiable_sensitivity,
    discrete_bayesian_update,
    dual_exp,
    dual_log,
    max_smooth,
    split_conformal_calibrate_and_evaluate,
    validate_mass_conserving_residual,
)


def test_module_uses_no_torch_or_numpy_and_dataclasses_are_frozen() -> None:
    assert "torch" not in sys.modules
    assert "numpy" not in sys.modules
    # Verify source module only depends on stdlib + contracts.
    assert tc.DifferentiableSensitivityResult.__dataclass_params__.frozen
    assert tc.MassConservationGateResult.__dataclass_params__.frozen
    assert tc.ConformalSample.__dataclass_params__.frozen
    assert tc.SplitConformalResult.__dataclass_params__.frozen
    assert tc.DiscreteBayesianUpdateResult.__dataclass_params__.frozen
    assert tc.Dual.__dataclass_params__.frozen

    d = Dual(2.0, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.value = 3.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 1. Dual number arithmetic and forward-mode sensitivities
# ---------------------------------------------------------------------------


def test_dual_elementary_arithmetic_and_reflected_ops() -> None:
    x = Dual(3.0, 1.0)
    y = Dual(2.0, 4.0)

    assert (+x) == x
    assert (-x) == Dual(-3.0, -1.0)

    add_res = x + y
    assert add_res.value == pytest.approx(5.0)
    assert add_res.deriv == pytest.approx(5.0)
    assert (2.5 + x) == Dual(5.5, 1.0)

    sub_res = x - y
    assert sub_res.value == pytest.approx(1.0)
    assert sub_res.deriv == pytest.approx(-3.0)
    assert (10.0 - x) == Dual(7.0, -1.0)

    mul_res = x * y
    assert mul_res.value == pytest.approx(6.0)
    assert mul_res.deriv == pytest.approx(1.0 * 2.0 + 3.0 * 4.0)
    assert (2.0 * x) == Dual(6.0, 2.0)

    div_res = x / y
    assert div_res.value == pytest.approx(1.5)
    assert div_res.deriv == pytest.approx((1.0 * 2.0 - 3.0 * 4.0) / 4.0)
    rdiv_res = 6.0 / x
    assert rdiv_res.value == pytest.approx(2.0)
    assert rdiv_res.deriv == pytest.approx(-6.0 / 9.0)


def test_dual_power_exp_log_and_max_smooth_exact_derivatives() -> None:
    x = Dual(2.0, 1.0)

    p_const = x**3
    assert p_const.value == pytest.approx(8.0)
    assert p_const.deriv == pytest.approx(12.0)

    p_zero = x**0
    assert p_zero == Dual(1.0, 0.0)

    p_base_zero = Dual(0.0, 3.0) ** 1.0
    assert p_base_zero == Dual(0.0, 3.0)
    assert (Dual(0.0, 3.0) ** 2.0) == Dual(0.0, 0.0)

    p_neg_base = Dual(-2.0, 1.5) ** 2
    assert p_neg_base == Dual(4.0, -6.0)

    # General u**v with both varying: d/dx (x**x) = x**x * (log(x) + 1)
    p_both = x**x
    assert p_both.value == pytest.approx(4.0)
    assert p_both.deriv == pytest.approx(4.0 * (math.log(2.0) + 1.0))

    # Reflected power: 3**x -> 3**2 * log(3)
    p_refl = 3.0**x
    assert p_refl.value == pytest.approx(9.0)
    assert p_refl.deriv == pytest.approx(9.0 * math.log(3.0))

    ex = x.exp()
    assert ex == dual_exp(x)
    assert ex.value == pytest.approx(math.exp(2.0))
    assert ex.deriv == pytest.approx(math.exp(2.0))

    lg = x.log()
    assert lg == dual_log(x)
    assert lg.value == pytest.approx(math.log(2.0))
    assert lg.deriv == pytest.approx(0.5)

    # max_smooth at tie gives exact average of derivatives
    tie = max_smooth(Dual(5.0, 2.0), Dual(5.0, 6.0), sharpness=20.0)
    assert tie.value == pytest.approx(5.0 + math.log(2.0) / 20.0)
    assert tie.deriv == pytest.approx(4.0)

    # Numerical stability for large inputs and sharpness
    big = Dual(1000.0, 3.0).max_smooth(Dual(990.0, 1.0), sharpness=50.0)
    assert big.value == pytest.approx(1000.0)
    assert big.deriv == pytest.approx(3.0)


def test_differentiable_sensitivity_matches_analytical_and_carries_rev13_flag() -> None:
    def hydrological_surrogate(params):
        # Smooth drainage-like response combining +, -, *, /, **, exp, log, max_smooth
        p = params["precip"]
        cap = params["capacity"]
        alpha = params["alpha"]
        excess = max_smooth(p - cap, 0.0, sharpness=25.0)
        decay = 1.0 - dual_exp(-alpha * (p / cap))
        return (excess + 0.5) * decay + dual_log(cap) ** 1.5

    theta = {"precip": 45.0, "capacity": 30.0, "alpha": 0.4}
    report = differentiable_sensitivity(hydrological_surrogate, theta)

    assert report.derivatives_guarantee_physical_accuracy is False
    assert set(report.sensitivities.keys()) == {"precip", "capacity", "alpha"}

    # Verify against central finite differences
    h = 1e-6
    for name in theta:
        up = dict(theta)
        dn = dict(theta)
        up[name] += h
        dn[name] -= h
        y_up = hydrological_surrogate({k: Dual(v, 0.0) for k, v in up.items()}).value
        y_dn = hydrological_surrogate({k: Dual(v, 0.0) for k, v in dn.items()}).value
        fd = (y_up - y_dn) / (2.0 * h)
        assert report.sensitivities[name] == pytest.approx(fd, rel=1e-7, abs=1e-7)


def test_dual_and_sensitivity_validation_errors() -> None:
    with pytest.raises(ValueError):
        Dual(float("nan"), 0.0)
    with pytest.raises(ValueError):
        Dual(1.0, float("inf"))
    with pytest.raises(TypeError):
        Dual(True, 0.0)
    with pytest.raises(ZeroDivisionError):
        _ = Dual(1.0, 1.0) / Dual(0.0, 0.0)
    with pytest.raises(ValueError):
        _ = Dual(0.0, 1.0).log()
    with pytest.raises(ValueError):
        _ = Dual(-1.0, 1.0) ** 0.5
    with pytest.raises(ValueError):
        _ = Dual(0.0, 1.0) ** 0.5
    with pytest.raises(ValueError):
        _ = max_smooth(Dual(1.0, 0.0), Dual(2.0, 0.0), sharpness=0.0)
    with pytest.raises(ValueError):
        DifferentiableSensitivityResult(
            value=1.0,
            sensitivities={"a": 1.0},
            derivatives_guarantee_physical_accuracy=True,
        )
    with pytest.raises(ValueError):
        differentiable_sensitivity(lambda p: Dual(1.0, 0.0), {})


# ---------------------------------------------------------------------------
# 2. Knowledge-Guided mass-conservation residual gate
# ---------------------------------------------------------------------------


def test_mass_conserving_residual_gate_passes_closed_balance() -> None:
    res = validate_mass_conserving_residual(
        storage_start=50.0,
        storage_end=58.5,
        inflows=20.0,
        outflows=12.0,
        residual_fluxes=0.5,
        tol=1e-9,
    )
    assert res.passed is True
    assert res.status == "PASSED"
    assert res.storage_change == pytest.approx(8.5)
    assert res.net_flux_with_residual == pytest.approx(8.5)
    assert res.discrepancy == pytest.approx(0.0)
    assert res.control_failure is None


def test_mass_conserving_residual_gate_supports_sequence_fluxes() -> None:
    res = validate_mass_conserving_residual(
        storage_start=40.0,
        storage_end=43.0,
        inflows=(10.0, 2.0),
        outflows=(5.0, 3.0, 1.5),
        residual_fluxes=(0.25, 0.25),
        tol=1e-12,
    )
    assert res.passed is True
    assert res.discrepancy == pytest.approx(0.0)


def test_mass_conserving_residual_gate_rejects_non_conservative_residual() -> None:
    # Learned residual adds +4.0 without changing storage_end -> discrepancy 4.0
    res = validate_mass_conserving_residual(
        storage_start=50.0,
        storage_end=58.0,
        inflows=20.0,
        outflows=12.0,
        residual_fluxes=4.0,
        tol=1e-6,
    )
    assert res.passed is False
    assert res.status == "CONTROL_FAILED"
    assert res.discrepancy == pytest.approx(4.0)
    assert isinstance(res.control_failure, Missing)
    assert res.control_failure.reason == "CONTROL_FAILED"


def test_mass_conserving_residual_gate_propagates_missing_and_validates_tol() -> None:
    res = validate_mass_conserving_residual(
        storage_start=50.0,
        storage_end=55.0,
        inflows=Missing(reason="NO_COVERAGE", detail="station gap"),
        outflows=5.0,
        residual_fluxes=0.0,
        tol=1e-6,
    )
    assert res.passed is False
    assert res.status == "MISSING_INPUT"
    assert isinstance(res.control_failure, Missing)
    assert res.control_failure.reason == "MISSING_INPUT"
    assert "inflows" in (res.control_failure.detail or "")

    with pytest.raises(ValueError):
        validate_mass_conserving_residual(1.0, 1.0, 0.0, 0.0, 0.0, tol=-1e-3)


# ---------------------------------------------------------------------------
# 3. Split-conformal prediction evaluator
# ---------------------------------------------------------------------------


def _make_samples(
    prefix: str,
    residuals: list[float],
    temporal_block: str = "2001-2010",
    spatial_block: str = "zone_A",
) -> list[ConformalSample]:
    return [
        ConformalSample(
            sample_id=f"{prefix}_{i}",
            residual=r,
            temporal_block=temporal_block,
            spatial_block=spatial_block,
        )
        for i, r in enumerate(residuals)
    ]


def test_split_conformal_calibration_and_disjoint_holdout_evaluation() -> None:
    # n = 9, alpha = 0.2 -> rank = ceil(10 * 0.8) = 8 -> 8th smallest |r| = 8.0
    cal = _make_samples("cal", [-1.0, 2.0, -3.0, 4.0, -5.0, 6.0, -7.0, 8.0, -9.0])
    holdout = _make_samples("hold", [1.5, -8.0, 8.5, -2.5])

    res = split_conformal_calibrate_and_evaluate(cal, holdout, alpha=0.2)

    assert res.quantile == pytest.approx(8.0)
    assert res.interval_width == pytest.approx(16.0)
    assert res.calibration_count == 9
    assert res.holdout_count == 4
    assert res.covered_count == 3  # 1.5, -8.0, -2.5 are within [-8, +8]
    assert res.empirical_coverage == pytest.approx(0.75)
    assert res.target_coverage == pytest.approx(0.8)
    assert res.temporal_shift_present is False
    assert res.spatial_shift_present is False
    assert res.unconditional_field_guarantee is False


def test_split_conformal_decimal_rank_avoids_float_ceil_drift() -> None:
    # In IEEE 754 float: 10 * (1.0 - 0.7) == 3.0000000000000004 (ceil -> 4)
    # Exact rank for n=9, alpha=0.7 is ceil(10 * 0.3) = 3.
    cal = _make_samples("cal", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    holdout = _make_samples("hold", [3.0])

    res = split_conformal_calibrate_and_evaluate(cal, holdout, alpha=0.7)
    assert res.quantile == pytest.approx(3.0)


def test_split_conformal_rejects_overlap_and_undeclared_shift_blocks() -> None:
    cal = _make_samples("s", [1.0, 2.0, 3.0, 4.0])
    overlapping_holdout = [
        ConformalSample("s_2", 2.5, "2001-2010", "zone_A"),
        ConformalSample("h_1", 1.0, "2001-2010", "zone_A"),
    ]
    with pytest.raises(ValueError, match="overlap"):
        split_conformal_calibrate_and_evaluate(cal, overlapping_holdout, alpha=0.2)

    # Temporal shift mixed without declaration
    hold_temp_shift = _make_samples(
        "hold", [1.0, 2.0], temporal_block="2011-2020", spatial_block="zone_A"
    )
    with pytest.raises(ValueError, match="temporal shift"):
        split_conformal_calibrate_and_evaluate(cal, hold_temp_shift, alpha=0.2)

    # Spatial shift mixed without declaration
    hold_spatial_shift = _make_samples(
        "hold", [1.0, 2.0], temporal_block="2001-2010", spatial_block="zone_B"
    )
    with pytest.raises(ValueError, match="spatial shift"):
        split_conformal_calibrate_and_evaluate(cal, hold_spatial_shift, alpha=0.2)

    # Mixing blocks INSIDE calibration without declaration also fails
    mixed_cal = _make_samples("c1", [1.0, 2.0], temporal_block="2001-2010") + (
        _make_samples("c2", [3.0, 4.0], temporal_block="2011-2020")
    )
    with pytest.raises(ValueError, match="temporal shift"):
        split_conformal_calibrate_and_evaluate(
            mixed_cal, _make_samples("h", [1.0]), alpha=0.2
        )

    # Declared shift succeeds and still keeps unconditional_field_guarantee=False
    declared = split_conformal_calibrate_and_evaluate(
        cal,
        hold_temp_shift,
        alpha=0.2,
        declared_temporal_shift=True,
        shift_declaration="dry-decade out-of-time evaluation",
    )
    assert declared.temporal_shift_present is True
    assert declared.declared_temporal_shift is True
    assert declared.shift_declaration == "dry-decade out-of-time evaluation"
    assert declared.unconditional_field_guarantee is False


def test_split_conformal_guarantee_flag_cannot_be_forced_true_and_size_checks() -> None:
    with pytest.raises(ValueError):
        SplitConformalResult(
            alpha=0.1,
            target_coverage=0.9,
            quantile=1.0,
            interval_width=2.0,
            calibration_count=10,
            holdout_count=5,
            covered_count=5,
            empirical_coverage=1.0,
            temporal_blocks_calibration=("t1",),
            temporal_blocks_holdout=("t1",),
            spatial_blocks_calibration=("s1",),
            spatial_blocks_holdout=("s1",),
            temporal_shift_present=False,
            spatial_shift_present=False,
            declared_temporal_shift=False,
            declared_spatial_shift=False,
            unconditional_field_guarantee=True,
        )

    # Too few calibration samples for alpha=0.1 (requires rank ceil(6*0.9)=6 > 5)
    with pytest.raises(ValueError, match="too small"):
        split_conformal_calibrate_and_evaluate(
            _make_samples("cal", [1.0, 2.0, 3.0, 4.0, 5.0]),
            _make_samples("hold", [1.0]),
            alpha=0.1,
        )


# ---------------------------------------------------------------------------
# 4. Discrete-grid Bayesian parameter / bias updater
# ---------------------------------------------------------------------------


def _gaussian_likelihood(sigma: float):
    def _lik(theta: float, obs: float) -> float:
        z = (obs - theta) / sigma
        return math.exp(-0.5 * z * z)

    return _lik


def test_discrete_bayesian_update_narrows_interval_under_unimodal_evidence() -> None:
    grid = (0.0, 1.0, 2.0)
    prior = (1.0, 1.0, 1.0)
    obs = (1.02, 0.98, 1.01, 0.99)

    res = discrete_bayesian_update(
        grid,
        prior,
        obs,
        _gaussian_likelihood(sigma=0.2),
        credible_level=0.90,
    )

    assert res.prior_interval == (0.0, 2.0)
    assert res.posterior_interval == (1.0, 1.0)
    assert res.interval_narrowed is True
    assert res.posterior_probs[1] > 0.999
    assert res.posterior_mode == 1.0
    assert res.posterior_mean == pytest.approx(1.0, abs=1e-4)


def test_discrete_bayesian_update_shifts_mean_mode_without_narrowing_interval() -> None:
    # Prior heavily concentrated at zero bias (0.0), so 90% prior interval is [0.0, 0.0].
    # An informative observation at +2.0 reveals model bias and shifts posterior mass,
    # shifting mean and mode while widening the 90% credible interval (interval_narrowed=False).
    grid = (0.0, 1.0, 2.0)
    prior = (0.96, 0.02, 0.02)

    def bias_likelihood(theta: float, obs: float) -> float:
        # Observation at obs=2.0 strongly favors theta=2.0 and slightly theta=1.0
        if math.isclose(theta, obs):
            return 0.96
        if math.isclose(theta, 1.0):
            return 0.60
        return 0.02

    res = discrete_bayesian_update(
        grid,
        prior,
        observations=(2.0,),
        likelihood_fn=bias_likelihood,
        credible_level=0.90,
    )

    # Prior: mean=0.06, mode=0.0, 90% CI=[0.0, 0.0] (width 0.0)
    assert res.prior_mode == 0.0
    assert res.prior_interval == (0.0, 0.0)
    assert res.prior_interval_width == pytest.approx(0.0)

    # Posterior unnormalized: (0.0192, 0.0120, 0.0192) -> sum 0.0504
    # Posterior: (~0.381, ~0.238, ~0.381) -> mean=1.0, std widened, 90% CI=[0.0, 2.0]
    assert res.posterior_mean > res.prior_mean
    assert res.mean_shift == pytest.approx(1.0 - 0.06)
    assert res.posterior_std > res.prior_std
    assert res.posterior_interval == (0.0, 2.0)
    assert res.posterior_interval_width > res.prior_interval_width
    assert res.interval_narrowed is False

    # Stronger bias observation shifts mode strictly to 2.0 while still not narrowing!
    def stronger_bias_likelihood(theta: float, obs: float) -> float:
        if math.isclose(theta, obs):
            return 0.98
        if math.isclose(theta, 1.0):
            return 0.10
        return 0.015

    res_mode_shift = discrete_bayesian_update(
        grid,
        prior,
        observations=(2.0,),
        likelihood_fn=stronger_bias_likelihood,
        credible_level=0.90,
    )
    assert res_mode_shift.mode_shifted is True
    assert res_mode_shift.prior_mode == 0.0
    assert res_mode_shift.posterior_mode == 2.0
    assert res_mode_shift.interval_narrowed is False


def test_discrete_bayesian_update_validation_errors() -> None:
    lik = _gaussian_likelihood(sigma=1.0)
    with pytest.raises(ValueError, match="strictly increasing"):
        discrete_bayesian_update(
            (1.0, 1.0), (0.5, 0.5), (1.0,), lik, credible_level=0.9
        )
    with pytest.raises(ValueError, match="negative"):
        discrete_bayesian_update(
            (0.0, 1.0), (-0.1, 1.1), (1.0,), lik, credible_level=0.9
        )
    with pytest.raises(ValueError, match="incompatible"):
        discrete_bayesian_update(
            (0.0, 1.0),
            (0.5, 0.5),
            (1.0,),
            lambda _t, _y: 0.0,
            credible_level=0.9,
        )
    with pytest.raises(ValueError, match="credible_level"):
        discrete_bayesian_update(
            (0.0, 1.0), (0.5, 0.5), (1.0,), lik, credible_level=1.0
        )


# ---------------------------------------------------------------------------
# 5. End-to-end composition across all four building blocks
# ---------------------------------------------------------------------------


def test_composable_twin_calibration_pipeline() -> None:
    # Step 1: Differentiable sensitivity of a smooth drainage model
    def storage_step(params):
        s0 = params["storage_start"]
        rain = params["rain"]
        k_drain = params["k_drain"]
        infil = rain * 0.8
        drain = max_smooth(s0 + infil - 30.0, 0.0, sharpness=40.0) * k_drain
        return s0 + infil - drain

    sens = differentiable_sensitivity(
        storage_step, {"storage_start": 25.0, "rain": 15.0, "k_drain": 0.5}
    )
    assert sens.sensitivities["k_drain"] < 0.0
    assert sens.derivatives_guarantee_physical_accuracy is False

    # Step 2: Gate a conservative vs non-conservative learned residual
    infil = 15.0 * 0.8
    drain = (25.0 + infil - 30.0) * 0.5
    s1_phys = 25.0 + infil - drain
    conservative_gate = validate_mass_conserving_residual(
        storage_start=25.0,
        storage_end=s1_phys + 0.25,
        inflows=infil,
        outflows=drain,
        residual_fluxes=0.25,
        tol=1e-6,
    )
    assert conservative_gate.passed is True

    bad_gate = validate_mass_conserving_residual(
        storage_start=25.0,
        storage_end=s1_phys,
        inflows=infil,
        outflows=drain,
        residual_fluxes=1.5,
        tol=1e-6,
    )
    assert bad_gate.status == "CONTROL_FAILED"

    # Step 3: Split-conformal evaluation on disjoint blocks
    cal = _make_samples("c", [0.1 * i for i in range(1, 10)])
    hold = _make_samples("h", [0.25, -0.75, 0.95])
    conf = split_conformal_calibrate_and_evaluate(cal, hold, alpha=0.2)
    assert conf.unconditional_field_guarantee is False
    assert conf.empirical_coverage == pytest.approx(2.0 / 3.0)

    # Step 4: Discrete Bayesian update over bias grid
    bayes = discrete_bayesian_update(
        grid_values=(-0.5, 0.0, 0.5),
        prior_weights=(0.1, 0.8, 0.1),
        observations=(0.45, 0.52),
        likelihood_fn=_gaussian_likelihood(sigma=0.2),
        credible_level=0.90,
    )
    assert bayes.mode_shifted is True
    assert bayes.posterior_mode == 0.5
