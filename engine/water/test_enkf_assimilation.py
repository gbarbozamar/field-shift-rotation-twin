"""Tests for pure-Python EnKF water state assimilation (Frontier Unit F-06).

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

EVERY NUMERIC VALUE IN THIS FILE IS A SYNTHETIC PLACEHOLDER chosen to verify
EnKF covariance algebra, linear solver precision, perturbed observations,
mass conservation, holdout separation, typed missingness, and G1/G5 invariants.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import datetime
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water.enkf_assimilation import (
    AssimilationStepRecord,
    EnKFUpdateResult,
    HoldoutSplit,
    assimilate_water_step,
    enkf_update_state,
)

# PLACEHOLDER synthetic dates and identity/simple matrices
DAY_1 = datetime.date(2024, 1, 10)
DAY_2 = datetime.date(2024, 1, 11)
DAY_3 = datetime.date(2024, 1, 12)
DAY_4 = datetime.date(2024, 1, 13)


def _matmul(
    a: list[list[float]] | tuple[tuple[float, ...], ...],
    b: list[list[float]] | tuple[tuple[float, ...], ...],
) -> list[list[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
        for i in range(len(a))
    ]


# ---------------------------------------------------------------------------
# Core EnKF mathematics (sample covariance, H, R, Kalman gain, perturbations)
# ---------------------------------------------------------------------------


def test_scalar_enkf_matches_exact_analytic_kalman_equations() -> None:
    """1D EnKF update matches exact sample variance, S, K, and posterior mean."""
    # PLACEHOLDER ensemble: mean = 13.0, anomalies = [-3, -1, 1, 3], P_f = 20 / 3
    ensemble = [[10.0], [12.0], [14.0], [16.0]]
    observation = [19.0]
    h_op = [[1.0]]
    r_cov = [[2.0]]

    result = enkf_update_state(ensemble, observation, h_op, r_cov, seed=7)
    assert isinstance(result, EnKFUpdateResult)

    expected_pf = 20.0 / 3.0
    expected_s = expected_pf + 2.0
    expected_k = expected_pf / expected_s  # 10 / 13
    expected_mean = 13.0 + expected_k * (19.0 - 13.0)
    expected_inc = expected_mean - 13.0

    assert result.forecast_mean == pytest.approx((13.0,), rel=1e-12, abs=1e-12)
    assert result.forecast_cov[0][0] == pytest.approx(expected_pf, rel=1e-12, abs=1e-12)
    assert result.innovation_cov[0][0] == pytest.approx(
        expected_s, rel=1e-12, abs=1e-12
    )
    assert result.kalman_gain[0][0] == pytest.approx(expected_k, rel=1e-12, abs=1e-12)
    assert result.posterior_mean[0] == pytest.approx(
        expected_mean, rel=1e-12, abs=1e-12
    )
    assert result.analysis_increment[0] == pytest.approx(
        expected_inc, rel=1e-12, abs=1e-12
    )
    assert result.clamped is False


def test_multivariate_enkf_solves_linear_system_and_propagates_cross_covariance() -> (
    None
):
    """Multi-state, multi-obs EnKF with correlated R and non-diagonal H."""
    # PLACEHOLDER 3-state, 5-member ensemble
    ensemble = [
        [20.0, 50.0, 10.0],
        [22.0, 54.0, 9.0],
        [24.0, 58.0, 11.0],
        [26.0, 62.0, 10.0],
        [28.0, 66.0, 10.0],
    ]
    # Observe state 0 + 0.5*state 2, and state 2 directly (state 1 is unobserved!)
    h_op = [
        [1.0, 0.0, 0.5],
        [0.0, 0.0, 1.0],
    ]
    # Correlated symmetric positive-definite observation error covariance R
    r_cov = [
        [1.5, 0.3],
        [0.3, 0.8],
    ]
    observation = [32.0, 11.5]

    result = enkf_update_state(ensemble, observation, h_op, r_cov, seed=19)
    assert isinstance(result, EnKFUpdateResult)

    # Verify K @ S == P_f @ H^T (linear system accuracy)
    h_t = [[h_op[r][c] for r in range(len(h_op))] for c in range(len(h_op[0]))]
    p_f_ht = _matmul(result.forecast_cov, h_t)
    k_s = _matmul(result.kalman_gain, result.innovation_cov)
    for i in range(3):
        for j in range(2):
            assert k_s[i][j] == pytest.approx(p_f_ht[i][j], rel=1e-11, abs=1e-11)

    # State 1 is unobserved directly, yet strictly positively correlated with state 0.
    # Positive innovation on state 0 must increase state 1 via sample cross-covariance!
    assert result.forecast_cov[1][0] > 0.0
    assert result.analysis_increment[1] > 0.0
    assert result.posterior_mean[1] > result.forecast_mean[1]


def test_cross_covariance_negative_and_zero_correlation_not_proximity_heuristic() -> (
    None
):
    """Law 1: update direction on unobserved state follows P_f sign, not proximity."""
    # PLACEHOLDER: state 0 and state 1 are negatively correlated
    neg_ensemble = [
        [10.0, 90.0],
        [12.0, 86.0],
        [14.0, 82.0],
        [16.0, 78.0],
    ]
    h_op = [[1.0, 0.0]]
    r_cov = [[1.0]]
    res_neg = enkf_update_state(neg_ensemble, [20.0], h_op, r_cov, seed=3)
    assert isinstance(res_neg, EnKFUpdateResult)
    assert res_neg.forecast_cov[1][0] < 0.0
    assert res_neg.analysis_increment[0] > 0.0
    assert res_neg.analysis_increment[1] < 0.0

    # Zero cross-covariance between state 0 and state 1 -> state 1 increment is zero
    zero_cov_ensemble = [
        [10.0, 50.0],
        [10.0, 60.0],
        [20.0, 50.0],
        [20.0, 60.0],
    ]
    res_zero = enkf_update_state(zero_cov_ensemble, [25.0], h_op, r_cov, seed=3)
    assert isinstance(res_zero, EnKFUpdateResult)
    assert res_zero.forecast_cov[1][0] == pytest.approx(0.0, abs=1e-12)
    assert res_zero.analysis_increment[1] == pytest.approx(0.0, abs=1e-12)


def test_kalman_gain_decreases_monotonically_as_observation_error_increases() -> None:
    """Law 1: larger R reduces K and shifts posterior mean back toward forecast."""
    ensemble = [[10.0], [12.0], [14.0], [16.0]]
    h_op = [[1.0]]
    obs = [20.0]

    res_low_r = enkf_update_state(ensemble, obs, h_op, [[0.5]], seed=5)
    res_high_r = enkf_update_state(ensemble, obs, h_op, [[50.0]], seed=5)
    assert isinstance(res_low_r, EnKFUpdateResult)
    assert isinstance(res_high_r, EnKFUpdateResult)

    assert res_low_r.kalman_gain[0][0] > res_high_r.kalman_gain[0][0]
    assert res_low_r.posterior_mean[0] > res_high_r.posterior_mean[0] > 13.0


def test_perturbed_observations_seed_determinism_and_centered_mean() -> None:
    """Same seed is deterministic; different seeds perturb members while preserving mean."""
    ensemble = [[40.0, 10.0], [42.0, 12.0], [44.0, 14.0], [46.0, 16.0]]
    obs = [50.0, 18.0]
    h_op = [[1.0, 0.0], [0.0, 1.0]]
    r_cov = [[2.0, 0.5], [0.5, 1.5]]

    r1_a = enkf_update_state(ensemble, obs, h_op, r_cov, seed=101)
    r1_b = enkf_update_state(ensemble, obs, h_op, r_cov, seed=101)
    r2 = enkf_update_state(ensemble, obs, h_op, r_cov, seed=202)
    assert isinstance(r1_a, EnKFUpdateResult)
    assert isinstance(r1_b, EnKFUpdateResult)
    assert isinstance(r2, EnKFUpdateResult)

    assert r1_a == r1_b
    assert r1_a.perturbed_observations != r2.perturbed_observations
    assert r1_a.posterior_ensemble != r2.posterior_ensemble

    # Centered perturbations ensure mean(perturbed_obs) == obs and exact Kalman mean
    for obs_idx in range(2):
        mean_pert = sum(row[obs_idx] for row in r1_a.perturbed_observations) / 4.0
        assert mean_pert == pytest.approx(obs[obs_idx], rel=1e-12, abs=1e-12)
    assert r1_a.posterior_mean == pytest.approx(r2.posterior_mean, rel=1e-12, abs=1e-12)


def test_zero_observation_noise_covariance_psd_edge_case() -> None:
    """Zero-noise observation (R = [[0.0]]) is valid when H P_f H^T is positive."""
    ensemble = [[10.0], [14.0], [18.0]]
    res = enkf_update_state(ensemble, [20.0], [[1.0]], [[0.0]], seed=0)
    assert isinstance(res, EnKFUpdateResult)
    assert res.kalman_gain[0][0] == pytest.approx(1.0, rel=1e-12, abs=1e-12)
    assert res.posterior_mean[0] == pytest.approx(20.0, rel=1e-12, abs=1e-12)
    assert all(row == (20.0,) for row in res.perturbed_observations)


# ---------------------------------------------------------------------------
# Optional state bounds clamping [min_bound, max_bound]
# ---------------------------------------------------------------------------


def test_state_bounds_clamping_scalar_and_per_state() -> None:
    """Clamping constrains posterior members and updates analysis_increment consistently."""
    ensemble = [[10.0, 2.0], [15.0, 4.0], [20.0, 6.0], [25.0, 8.0]]
    h_op = [[1.0, 0.0], [0.0, 1.0]]
    r_cov = [[0.5, 0.0], [0.0, 0.5]]

    # Push state 0 above 25 and state 1 below 0
    res = enkf_update_state(
        ensemble,
        [30.0, -5.0],
        h_op,
        r_cov,
        seed=11,
        min_bound=[0.0, 0.0],
        max_bound=[24.0, None],
    )
    assert isinstance(res, EnKFUpdateResult)
    assert res.clamped is True
    for member in res.posterior_ensemble:
        assert 0.0 <= member[0] <= 24.0
        assert member[1] >= 0.0

    # analysis_increment must still match clamped posterior_mean - forecast_mean
    for j in range(2):
        assert res.analysis_increment[j] == pytest.approx(
            res.posterior_mean[j] - res.forecast_mean[j], rel=1e-12, abs=1e-12
        )

    # Scalar bounds when no clamping is triggered
    res_unclamped = enkf_update_state(
        ensemble,
        [18.0, 5.0],
        h_op,
        r_cov,
        seed=11,
        min_bound=-100.0,
        max_bound=100.0,
    )
    assert isinstance(res_unclamped, EnKFUpdateResult)
    assert res_unclamped.clamped is False


def test_invalid_state_bounds_raise_value_or_type_error() -> None:
    """Inverted, mismatched, non-finite, or wrong-type bounds raise G5 errors."""
    ensemble = [[10.0, 20.0], [12.0, 22.0]]
    h_op = [[1.0, 0.0]]
    r_cov = [[1.0]]

    with pytest.raises(ValueError, match="min_bound"):
        enkf_update_state(ensemble, [11.0], h_op, r_cov, min_bound=10.0, max_bound=5.0)
    with pytest.raises(ValueError, match="expected length 2"):
        enkf_update_state(ensemble, [11.0], h_op, r_cov, min_bound=[0.0])
    with pytest.raises(ValueError, match="finite"):
        enkf_update_state(ensemble, [11.0], h_op, r_cov, max_bound=float("inf"))
    with pytest.raises(TypeError, match="G5"):
        enkf_update_state(ensemble, [11.0], h_op, r_cov, min_bound=True)


# ---------------------------------------------------------------------------
# Law 2: Mass conservation & attributed_to_precipitation=False
# ---------------------------------------------------------------------------


def test_assimilate_water_step_tracks_increment_and_conserves_mass() -> None:
    """Law 2: storage_after == storage_before + inflow - outflow + analysis_increment."""
    # PLACEHOLDER: storage_before=45, inflow=12, outflow=7 => forecast_mean=50
    storage_before = 45.0
    inflow = 12.0
    outflow = 7.0
    # Forecast ensemble centered at 50.0
    ensemble = [[46.0], [48.0], [52.0], [54.0]]
    split = HoldoutSplit(
        assimilation_dates={DAY_1, DAY_2},
        validation_dates={DAY_3, DAY_4},
    )

    record = assimilate_water_step(
        date=DAY_1,
        storage_before_mm=storage_before,
        physical_inflow_mm=inflow,
        physical_outflow_mm=outflow,
        ensemble=ensemble,
        observation=[58.0],
        observation_operator=[[1.0]],
        observation_error_cov=[[2.0]],
        seed=42,
        min_bound=0.0,
        max_bound=80.0,
        holdout_split=split,
    )
    assert isinstance(record, AssimilationStepRecord)
    assert record.attributed_to_precipitation is False
    assert record.mean_forecast_mm == pytest.approx(50.0, abs=1e-12)
    assert record.analysis_increment_mm == pytest.approx(
        record.mean_posterior_mm - record.mean_forecast_mm, rel=1e-12, abs=1e-12
    )
    assert record.storage_after_mm == pytest.approx(
        storage_before + inflow - outflow + record.analysis_increment_mm,
        rel=1e-12,
        abs=1e-12,
    )
    assert abs(record.mass_balance_residual_mm) < 1e-12


def test_assimilate_water_step_clamped_still_conserves_mass() -> None:
    """Law 2 holds identically even when state clamping restricts the posterior."""
    ensemble = [[46.0], [48.0], [52.0], [54.0]]
    record = assimilate_water_step(
        date=DAY_1,
        storage_before_mm=45.0,
        physical_inflow_mm=10.0,
        physical_outflow_mm=5.0,
        ensemble=ensemble,
        observation=[90.0],
        observation_operator=[[1.0]],
        observation_error_cov=[[1.0]],
        seed=7,
        min_bound=0.0,
        max_bound=55.0,
    )
    assert isinstance(record, AssimilationStepRecord)
    assert record.update_result is not None
    assert record.update_result.clamped is True
    assert record.attributed_to_precipitation is False
    assert record.storage_after_mm == pytest.approx(
        45.0 + 10.0 - 5.0 + record.analysis_increment_mm, rel=1e-12, abs=1e-12
    )


def test_assimilation_step_record_rejects_precip_attribution_and_broken_balance() -> (
    None
):
    """Law 2 rejects attributed_to_precipitation=True or inconsistent mass balance."""
    with pytest.raises(ValueError, match="attributed_to_precipitation"):
        AssimilationStepRecord(
            date=DAY_1,
            storage_before_mm=40.0,
            physical_inflow_mm=10.0,
            physical_outflow_mm=5.0,
            mean_forecast_mm=45.0,
            mean_posterior_mm=48.0,
            analysis_increment_mm=3.0,
            storage_after_mm=48.0,
            attributed_to_precipitation=True,
        )

    # Disguising increment inside physical_inflow breaks the balance identity
    with pytest.raises(ValueError, match="mass balance conservation violated"):
        AssimilationStepRecord(
            date=DAY_1,
            storage_before_mm=40.0,
            physical_inflow_mm=13.0,
            physical_outflow_mm=5.0,
            mean_forecast_mm=45.0,
            mean_posterior_mm=48.0,
            analysis_increment_mm=3.0,
            storage_after_mm=48.0,
            attributed_to_precipitation=False,
        )

    # Mismatched analysis_increment_mm vs mean_posterior - mean_forecast
    with pytest.raises(ValueError, match="analysis_increment_mm"):
        AssimilationStepRecord(
            date=DAY_1,
            storage_before_mm=40.0,
            physical_inflow_mm=10.0,
            physical_outflow_mm=5.0,
            mean_forecast_mm=45.0,
            mean_posterior_mm=48.0,
            analysis_increment_mm=2.0,
            storage_after_mm=47.0,
            attributed_to_precipitation=False,
        )

    # Ensemble forecast mean mismatching storage_before + inflow - outflow
    with pytest.raises(ValueError, match="ensemble forecast mean"):
        assimilate_water_step(
            date=DAY_1,
            storage_before_mm=40.0,
            physical_inflow_mm=10.0,
            physical_outflow_mm=5.0,
            ensemble=[[58.0], [62.0]],  # mean 60 != 45
            observation=[50.0],
            observation_operator=[[1.0]],
            observation_error_cov=[[1.0]],
        )


# ---------------------------------------------------------------------------
# Law 3: Holdout guard ("assimilating is not validating")
# ---------------------------------------------------------------------------


def test_holdout_split_rejects_overlap_and_blocks_validation_assimilation() -> None:
    """Law 3: HoldoutSplit raises ValueError on overlap and blocks validation dates."""
    with pytest.raises(ValueError, match="assimilating is not validating"):
        HoldoutSplit(
            assimilation_dates=[DAY_1, DAY_2],
            validation_dates=[DAY_2, DAY_3],
        )

    split = HoldoutSplit(
        assimilation_dates=[DAY_1, DAY_2],
        validation_dates=[DAY_3, DAY_4],
    )
    assert split.is_assimilation_date(DAY_1) is True
    assert split.is_validation_date(DAY_1) is False
    assert split.is_validation_date(DAY_3) is True
    assert split.is_assimilation_date(DAY_3) is False

    # Assimilating on a validation date must raise ValueError
    with pytest.raises(ValueError, match="assimilating is not validating"):
        assimilate_water_step(
            date=DAY_3,
            storage_before_mm=45.0,
            physical_inflow_mm=10.0,
            physical_outflow_mm=5.0,
            ensemble=[[48.0], [52.0]],
            observation=[51.0],
            observation_operator=[[1.0]],
            observation_error_cov=[[1.0]],
            holdout_split=split,
        )

    # Assimilating on a date not in assimilation_dates also raises ValueError
    day_unlisted = datetime.date(2024, 2, 1)
    with pytest.raises(ValueError, match="not in assimilation_dates"):
        assimilate_water_step(
            date=day_unlisted,
            storage_before_mm=45.0,
            physical_inflow_mm=10.0,
            physical_outflow_mm=5.0,
            ensemble=[[48.0], [52.0]],
            observation=[51.0],
            observation_operator=[[1.0]],
            observation_error_cov=[[1.0]],
            holdout_split=split,
        )


def test_holdout_split_rejects_non_date_types() -> None:
    """G5: HoldoutSplit rejects datetime.datetime and non-date objects."""
    dt = datetime.datetime(2024, 1, 10, 12, 0)
    with pytest.raises(TypeError, match="G5"):
        HoldoutSplit(assimilation_dates=[dt], validation_dates=[DAY_2])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="G5"):
        HoldoutSplit(assimilation_dates="2024-01-10", validation_dates=[DAY_2])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Law 4: Typed Missing (MISSING_INPUT / NOT_COMPUTABLE), never silent 0
# ---------------------------------------------------------------------------


def test_missing_observations_return_typed_missing_never_zero() -> None:
    """Law 4: absent or Missing observations return Missing(MISSING_INPUT)."""
    ensemble = [[10.0, 20.0], [12.0, 22.0], [14.0, 24.0]]
    h_op = [[1.0, 0.0], [0.0, 1.0]]
    r_cov = [[1.0, 0.0], [0.0, 1.0]]

    r_none = enkf_update_state(ensemble, None, h_op, r_cov)
    assert isinstance(r_none, Missing)
    assert r_none.reason == "MISSING_INPUT"

    r_missing = enkf_update_state(
        ensemble,
        Missing(reason="MISSING_INPUT", detail="satellite overpass clouded"),
        h_op,
        r_cov,
    )
    assert isinstance(r_missing, Missing)
    assert r_missing.reason == "MISSING_INPUT"
    assert "clouded" in (r_missing.detail or "")

    r_partial_none = enkf_update_state(ensemble, [12.0, None], h_op, r_cov)
    assert isinstance(r_partial_none, Missing)
    assert r_partial_none.reason == "MISSING_INPUT"

    r_partial_missing = enkf_update_state(
        ensemble,
        [12.0, Missing(reason="NO_COVERAGE", detail="swath edge")],
        h_op,
        r_cov,
    )
    assert isinstance(r_partial_missing, Missing)
    assert r_partial_missing.reason == "MISSING_INPUT"


@pytest.mark.parametrize(
    ("ensemble", "obs", "h_op", "r_cov"),
    [
        # Empty observation vector
        ([[10.0], [12.0]], [], [[1.0]], [[1.0]]),
        # Non-finite observation
        ([[10.0], [12.0]], [float("nan")], [[1.0]], [[1.0]]),
        ([[10.0], [12.0]], [float("inf")], [[1.0]], [[1.0]]),
        # Fewer than 2 ensemble members
        ([], [10.0], [[1.0]], [[1.0]]),
        ([[10.0]], [10.0], [[1.0]], [[1.0]]),
        # Ragged ensemble matrix
        ([[10.0, 1.0], [12.0]], [10.0], [[1.0, 0.0]], [[1.0]]),
        # Non-finite ensemble entry
        ([[10.0], [float("nan")]], [10.0], [[1.0]], [[1.0]]),
        # Shape mismatch on H
        ([[10.0, 20.0], [12.0, 22.0]], [10.0], [[1.0]], [[1.0]]),
        # Shape mismatch on R
        ([[10.0], [12.0]], [10.0], [[1.0]], [[1.0, 0.0], [0.0, 1.0]]),
        # Asymmetric R
        (
            [[10.0, 20.0], [12.0, 22.0]],
            [10.0, 20.0],
            [[1.0, 0.0], [0.0, 1.0]],
            [[1.0, 0.5], [0.1, 1.0]],
        ),
        # Negative variance in R
        ([[10.0], [12.0]], [10.0], [[1.0]], [[-1.0]]),
        # Indefinite R (eigenvalues 3 and -1)
        (
            [[10.0, 20.0], [12.0, 22.0]],
            [10.0, 20.0],
            [[1.0, 0.0], [0.0, 1.0]],
            [[1.0, 2.0], [2.0, 1.0]],
        ),
        # Singular S = H P_f H^T + R (zero spread ensemble and zero R)
        ([[10.0], [10.0]], [12.0], [[1.0]], [[0.0]]),
    ],
)
def test_invalid_or_singular_matrices_return_not_computable_missing(
    ensemble: list[list[float]],
    obs: list[float],
    h_op: list[list[float]],
    r_cov: list[list[float]],
) -> None:
    """Law 4: invalid, ragged, non-PSD, or singular matrices return NOT_COMPUTABLE."""
    result = enkf_update_state(ensemble, obs, h_op, r_cov, seed=0)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"


def test_assimilate_water_step_propagates_missing_physical_or_obs_inputs() -> None:
    """Law 4: missing physical inputs or observations propagate Missing cleanly."""
    ensemble = [[48.0], [52.0]]
    missing_obs = assimilate_water_step(
        date=DAY_1,
        storage_before_mm=45.0,
        physical_inflow_mm=10.0,
        physical_outflow_mm=5.0,
        ensemble=ensemble,
        observation=None,
        observation_operator=[[1.0]],
        observation_error_cov=[[1.0]],
    )
    assert isinstance(missing_obs, Missing)
    assert missing_obs.reason == "MISSING_INPUT"

    missing_inflow = assimilate_water_step(
        date=DAY_1,
        storage_before_mm=45.0,
        physical_inflow_mm=Missing(reason="MISSING_INPUT", detail="precip gap"),
        physical_outflow_mm=5.0,
        ensemble=ensemble,
        observation=[51.0],
        observation_operator=[[1.0]],
        observation_error_cov=[[1.0]],
    )
    assert isinstance(missing_inflow, Missing)
    assert missing_inflow.reason == "MISSING_INPUT"

    missing_matrix = enkf_update_state(
        [[48.0], [Missing(reason="MISSING_INPUT", detail="state gap")]],
        [51.0],
        [[1.0]],
        [[1.0]],
    )
    assert isinstance(missing_matrix, Missing)
    assert missing_matrix.reason == "MISSING_INPUT"


def test_assimilate_water_step_supports_non_zero_storage_state_index() -> None:
    """Mass conservation tracks whichever state index holds column storage."""
    # State vector: [surface_wetness, column_storage_mm]
    ensemble = [[0.2, 46.0], [0.3, 48.0], [0.4, 52.0], [0.5, 54.0]]
    record = assimilate_water_step(
        date=DAY_2,
        storage_before_mm=45.0,
        physical_inflow_mm=12.0,
        physical_outflow_mm=7.0,
        ensemble=ensemble,
        observation=[0.45],
        observation_operator=[[1.0, 0.0]],
        observation_error_cov=[[0.02]],
        seed=15,
        storage_state_index=1,
    )
    assert isinstance(record, AssimilationStepRecord)
    assert record.mean_forecast_mm == pytest.approx(50.0, abs=1e-12)
    assert record.analysis_increment_mm > 0.0
    assert record.storage_after_mm == pytest.approx(
        45.0 + 12.0 - 7.0 + record.analysis_increment_mm, rel=1e-12, abs=1e-12
    )
    assert record.attributed_to_precipitation is False


# ---------------------------------------------------------------------------
# G1 purity, G5 strict types, immutability, and zero-numpy verification
# ---------------------------------------------------------------------------


def test_g1_purity_no_argument_mutation_and_frozen_results() -> None:
    """G1: inputs are never mutated and returned dataclasses are frozen."""
    ensemble = [[10.0, 20.0], [12.0, 24.0], [14.0, 28.0]]
    obs = [13.0]
    h_op = [[1.0, 0.0]]
    r_cov = [[1.5]]

    ensemble_orig = copy.deepcopy(ensemble)
    obs_orig = copy.deepcopy(obs)
    h_orig = copy.deepcopy(h_op)
    r_orig = copy.deepcopy(r_cov)

    res = enkf_update_state(ensemble, obs, h_op, r_cov, seed=9)
    assert isinstance(res, EnKFUpdateResult)

    assert ensemble == ensemble_orig
    assert obs == obs_orig
    assert h_op == h_orig
    assert r_cov == r_orig

    with pytest.raises(dataclasses.FrozenInstanceError):
        res.clamped = True  # type: ignore[misc]


def test_g5_bool_and_type_rejection() -> None:
    """G5: booleans and wrong container types raise TypeError."""
    with pytest.raises(TypeError, match="G5"):
        enkf_update_state([[10.0], [12.0]], [11.0], [[1.0]], [[1.0]], seed=True)
    with pytest.raises(TypeError, match="G5"):
        enkf_update_state([[True], [12.0]], [11.0], [[1.0]], [[1.0]])
    with pytest.raises(TypeError, match="G5"):
        enkf_update_state([[10.0], [12.0]], [False], [[1.0]], [[1.0]])
    with pytest.raises(TypeError, match="G5"):
        enkf_update_state("not-a-matrix", [11.0], [[1.0]], [[1.0]])  # type: ignore[arg-type]


def test_module_uses_pure_stdlib_and_contracts_only_zero_numpy() -> None:
    """EnKF module imports only Python stdlib and contracts.results.models."""
    source_path = Path(__file__).with_name("enkf_assimilation.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert "numpy" not in imported_roots
    assert imported_roots <= {
        "__future__",
        "collections",
        "contracts",
        "dataclasses",
        "datetime",
        "math",
        "random",
    }
