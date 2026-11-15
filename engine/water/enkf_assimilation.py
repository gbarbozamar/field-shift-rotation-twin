"""Pure-Python Ensemble Kalman Filter (EnKF) state assimilation for water storage.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
References: ``27_PLAN_DE_FRONTERA.md`` (§5.2, §5.7) and
``28_PLAN_INTEGRADO_REV13.md`` (§§3, 5).

This module is standalone and is not wired into ``engine/water/__init__.py``,
EP3, or the API runner; nothing here takes effect until people approve it.

Scientific and architectural laws enforced:
1. **True EnKF covariance update (no proximity heuristic):** computes the
   unbiased sample covariance ``P_f`` across the forecast ensemble matrix ``X``
   (``n_members x n_state``), maps through the explicit observation operator
   ``H`` (``n_obs x n_state``) and explicit observation error covariance ``R``
   (``n_obs x n_obs``), solves ``K = P_f H^T (H P_f H^T + R)^{-1}`` using a
   pure-Python Gaussian elimination linear solver with partial pivoting, and
   updates members against perturbed observations drawn deterministically from
   ``seed``.
2. **Explicit analysis increment and water mass conservation:** every
   assimilation step records ``analysis_increment_mm = mean_posterior -
   mean_forecast`` in ``AssimilationStepRecord``, enforces
   ``storage_after == storage_before + physical_inflow - physical_outflow +
   analysis_increment``, and sets ``attributed_to_precipitation=False`` so an
   assimilation correction is never disguised as rainfall.
3. **Strict holdout separation ("assimilating is not validating"):**
   ``HoldoutSplit`` enforces disjoint ``assimilation_dates`` and
   ``validation_dates`` and raises ``ValueError`` on any date overlap or any
   attempt to assimilate on a validation date.
4. **Typed missingness:** missing observations or invalid/singular matrices
   return ``contracts.results.models.Missing`` (``MISSING_INPUT`` or
   ``NOT_COMPUTABLE``), never silent ``0.0``.

Pure Python 3.12 standard library plus ``contracts.results.models.Missing``
(zero third-party numeric dependencies). Pure function (G1): no file access,
no network call, no clock, no environment variable, no global mutable state,
and arguments are never modified.
"""

from __future__ import annotations

import datetime
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.results.models import Missing

__all__ = [
    "AssimilationStepRecord",
    "EnKFUpdateResult",
    "HoldoutSplit",
    "assimilate_water_step",
    "enkf_update_state",
]

_SYMMETRY_RTOL = 1e-10
_CHOLESKY_TOL = 1e-12
_PIVOT_RTOL = 1e-14
_CONSERVATION_RTOL = 1e-9


def _is_number(value: object) -> bool:
    """True for an ``int`` or ``float``; ``bool`` is rejected (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_date(value: object) -> bool:
    """True for a ``datetime.date`` excluding ``datetime.datetime`` (G5)."""
    return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_sequence_not_text(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _normalize_missing(missing: Missing, context: str) -> Missing:
    """Preserve MISSING_INPUT/NOT_COMPUTABLE or wrap other reasons explicitly."""
    if missing.reason in ("MISSING_INPUT", "NOT_COMPUTABLE"):
        return missing
    detail = f"{context}: unavailable ({missing.reason})"
    if missing.detail:
        detail = f"{detail}: {missing.detail}"
    return Missing(reason="MISSING_INPUT", detail=detail)


@dataclass(frozen=True)
class EnKFUpdateResult:
    """Result of one Ensemble Kalman Filter (EnKF) state update step.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    All matrices and vectors are stored as immutable tuples of floats.
    """

    posterior_ensemble: tuple[tuple[float, ...], ...]
    forecast_mean: tuple[float, ...]
    posterior_mean: tuple[float, ...]
    forecast_cov: tuple[tuple[float, ...], ...]
    kalman_gain: tuple[tuple[float, ...], ...]
    innovation_cov: tuple[tuple[float, ...], ...]
    analysis_increment: tuple[float, ...]
    perturbed_observations: tuple[tuple[float, ...], ...]
    clamped: bool


@dataclass(frozen=True)
class HoldoutSplit:
    """Disjoint split between assimilation dates and validation dates.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Enforces Rev13 §§3, 5 ("assimilating is not validating"): raises
    ``ValueError`` if ``assimilation_dates`` and ``validation_dates`` overlap.
    """

    assimilation_dates: frozenset[datetime.date]
    validation_dates: frozenset[datetime.date]

    def __post_init__(self) -> None:
        assim = _coerce_date_set("assimilation_dates", self.assimilation_dates)
        valid = _coerce_date_set("validation_dates", self.validation_dates)
        object.__setattr__(self, "assimilation_dates", assim)
        object.__setattr__(self, "validation_dates", valid)
        overlap = assim & valid
        if overlap:
            first_overlap = min(overlap).isoformat()
            raise ValueError(
                "assimilating is not validating: assimilation_dates and "
                f"validation_dates overlap on {len(overlap)} date(s), "
                f"first overlap {first_overlap}"
            )

    def is_assimilation_date(self, day: datetime.date) -> bool:
        """Return True if ``day`` belongs to ``assimilation_dates``."""
        if not _is_strict_date(day):
            raise TypeError(
                f"day: expected datetime.date, got {type(day).__name__} (G5)"
            )
        return day in self.assimilation_dates

    def is_validation_date(self, day: datetime.date) -> bool:
        """Return True if ``day`` belongs to ``validation_dates``."""
        if not _is_strict_date(day):
            raise TypeError(
                f"day: expected datetime.date, got {type(day).__name__} (G5)"
            )
        return day in self.validation_dates

    def assert_assimilation_allowed(self, day: datetime.date) -> None:
        """Raise ``ValueError`` if ``day`` is in ``validation_dates`` or excluded."""
        if not _is_strict_date(day):
            raise TypeError(
                f"day: expected datetime.date, got {type(day).__name__} (G5)"
            )
        if day in self.validation_dates:
            raise ValueError(
                f"assimilating is not validating: {day.isoformat()} is in validation_dates"
            )
        if day not in self.assimilation_dates:
            raise ValueError(
                f"{day.isoformat()} is not in assimilation_dates of HoldoutSplit"
            )


def _coerce_date_set(name: str, raw: object) -> frozenset[datetime.date]:
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(
        raw, (set, frozenset, Sequence)
    ):
        raise TypeError(
            f"{name}: expected set, frozenset, or sequence of datetime.date, "
            f"got {type(raw).__name__} (G5)"
        )
    dates: list[datetime.date] = []
    for item in raw:
        if not _is_strict_date(item):
            raise TypeError(
                f"{name}: expected datetime.date items, got {type(item).__name__} (G5)"
            )
        dates.append(item)
    return frozenset(dates)


@dataclass(frozen=True)
class AssimilationStepRecord:
    """Mass-conservation and attribution record for one assimilation step.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Tracks ``analysis_increment_mm = mean_posterior_mm - mean_forecast_mm``
    explicitly, requires ``attributed_to_precipitation=False``, and asserts:

        storage_after_mm == storage_before_mm + physical_inflow_mm
                            - physical_outflow_mm + analysis_increment_mm
    """

    date: datetime.date
    storage_before_mm: float
    physical_inflow_mm: float
    physical_outflow_mm: float
    mean_forecast_mm: float
    mean_posterior_mm: float
    analysis_increment_mm: float
    storage_after_mm: float
    attributed_to_precipitation: bool = False
    mass_balance_residual_mm: float = 0.0
    update_result: EnKFUpdateResult | None = None

    def __post_init__(self) -> None:
        if not _is_strict_date(self.date):
            raise TypeError(
                f"date: expected datetime.date, got {type(self.date).__name__} (G5)"
            )
        if not isinstance(self.attributed_to_precipitation, bool):
            raise TypeError(
                "attributed_to_precipitation: expected bool, got "
                f"{type(self.attributed_to_precipitation).__name__} (G5)"
            )
        if self.attributed_to_precipitation is not False:
            raise ValueError(
                "attributed_to_precipitation must be False: analysis increments "
                "must never be attributed to precipitation"
            )
        if self.update_result is not None and not isinstance(
            self.update_result, EnKFUpdateResult
        ):
            raise TypeError(
                "update_result: expected EnKFUpdateResult or None, got "
                f"{type(self.update_result).__name__} (G5)"
            )

        numeric_fields = (
            "storage_before_mm",
            "physical_inflow_mm",
            "physical_outflow_mm",
            "mean_forecast_mm",
            "mean_posterior_mm",
            "analysis_increment_mm",
            "storage_after_mm",
            "mass_balance_residual_mm",
        )
        for field_name in numeric_fields:
            raw = getattr(self, field_name)
            if not _is_number(raw):
                raise TypeError(
                    f"{field_name}: expected float or int, got {type(raw).__name__} (G5)"
                )
            if not _is_finite(raw):
                raise ValueError(f"{field_name} must be a finite number")
            object.__setattr__(self, field_name, float(raw))

        expected_increment = math.fsum((self.mean_posterior_mm, -self.mean_forecast_mm))
        inc_scale = max(
            1.0,
            abs(self.mean_posterior_mm),
            abs(self.mean_forecast_mm),
            abs(self.analysis_increment_mm),
        )
        if abs(self.analysis_increment_mm - expected_increment) > (
            _CONSERVATION_RTOL * inc_scale
        ):
            raise ValueError(
                "analysis_increment_mm must equal mean_posterior_mm - mean_forecast_mm "
                f"({self.analysis_increment_mm} != {expected_increment})"
            )

        expected_after = math.fsum(
            (
                self.storage_before_mm,
                self.physical_inflow_mm,
                -self.physical_outflow_mm,
                self.analysis_increment_mm,
            )
        )
        balance_scale = max(
            1.0,
            abs(self.storage_before_mm),
            abs(self.physical_inflow_mm),
            abs(self.physical_outflow_mm),
            abs(self.analysis_increment_mm),
            abs(self.storage_after_mm),
        )
        residual = math.fsum((self.storage_after_mm, -expected_after))
        if abs(residual) > _CONSERVATION_RTOL * balance_scale:
            raise ValueError(
                "mass balance conservation violated: storage_after_mm != "
                "storage_before_mm + physical_inflow_mm - physical_outflow_mm "
                f"+ analysis_increment_mm (residual={residual})"
            )
        if abs(self.mass_balance_residual_mm - residual) > (
            _CONSERVATION_RTOL * balance_scale
        ):
            raise ValueError(
                "mass_balance_residual_mm does not match computed conservation residual"
            )


def _validate_matrix(
    name: str,
    raw: object,
) -> list[list[float]] | Missing:
    """Validate a 2D numeric matrix; raise TypeError on bad types, Missing on invalid."""
    if isinstance(raw, Missing):
        return _normalize_missing(raw, name)
    if not _is_sequence_not_text(raw):
        raise TypeError(
            f"{name}: expected 2D sequence of numbers, got {type(raw).__name__} (G5)"
        )
    if len(raw) == 0:
        return Missing(reason="NOT_COMPUTABLE", detail=f"{name} must not be empty")

    rows: list[list[float]] = []
    expected_cols: int | None = None
    for row_idx, row in enumerate(raw):
        if isinstance(row, Missing):
            return _normalize_missing(row, f"{name}[{row_idx}]")
        if not _is_sequence_not_text(row):
            raise TypeError(
                f"{name}[{row_idx}]: expected sequence of numbers, got "
                f"{type(row).__name__} (G5)"
            )
        if expected_cols is None:
            expected_cols = len(row)
            if expected_cols == 0:
                return Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"{name} must have at least one column",
                )
        elif len(row) != expected_cols:
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{name} is ragged: row {row_idx} has length {len(row)}, "
                    f"expected {expected_cols}"
                ),
            )
        parsed_row: list[float] = []
        for col_idx, val in enumerate(row):
            if isinstance(val, Missing):
                return _normalize_missing(val, f"{name}[{row_idx}][{col_idx}]")
            if not _is_number(val):
                raise TypeError(
                    f"{name}[{row_idx}][{col_idx}]: expected float or int, got "
                    f"{type(val).__name__} (G5)"
                )
            assert isinstance(val, (int, float))
            if not _is_finite(val):
                return Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"{name}[{row_idx}][{col_idx}] is not finite",
                )
            parsed_row.append(float(val))
        rows.append(parsed_row)
    return rows


def _validate_observation(raw: object) -> list[float] | Missing:
    """Validate an observation vector; return Missing when absent or non-finite."""
    if raw is None:
        return Missing(reason="MISSING_INPUT", detail="observation is missing")
    if isinstance(raw, Missing):
        return _normalize_missing(raw, "observation")
    if not _is_sequence_not_text(raw):
        raise TypeError(
            f"observation: expected sequence of numbers or Missing, got "
            f"{type(raw).__name__} (G5)"
        )
    if len(raw) == 0:
        return Missing(
            reason="NOT_COMPUTABLE", detail="observation vector must not be empty"
        )
    values: list[float] = []
    for idx, elem in enumerate(raw):
        if elem is None:
            return Missing(
                reason="MISSING_INPUT",
                detail=f"observation[{idx}] is missing (None)",
            )
        if isinstance(elem, Missing):
            return _normalize_missing(elem, f"observation[{idx}]")
        if not _is_number(elem):
            raise TypeError(
                f"observation[{idx}]: expected float, int, or Missing, got "
                f"{type(elem).__name__} (G5)"
            )
        assert isinstance(elem, (int, float))
        if not _is_finite(elem):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"observation[{idx}] is not finite",
            )
        values.append(float(elem))
    return values


def _parse_bound_vector(
    name: str,
    bound: object,
    n_state: int,
) -> list[float | None]:
    """Parse an optional scalar or per-state bound vector (G5)."""
    if bound is None:
        return [None] * n_state
    if _is_number(bound):
        assert isinstance(bound, (int, float))
        if not _is_finite(bound):
            raise ValueError(f"{name} must be a finite number")
        return [float(bound)] * n_state
    if not _is_sequence_not_text(bound):
        raise TypeError(
            f"{name}: expected float, int, sequence, or None, got "
            f"{type(bound).__name__} (G5)"
        )
    if len(bound) != n_state:
        raise ValueError(
            f"{name}: expected length {n_state} matching state dimension, "
            f"got {len(bound)}"
        )
    parsed: list[float | None] = []
    for idx, item in enumerate(bound):
        if item is None:
            parsed.append(None)
            continue
        if not _is_number(item):
            raise TypeError(
                f"{name}[{idx}]: expected float, int, or None, got "
                f"{type(item).__name__} (G5)"
            )
        assert isinstance(item, (int, float))
        if not _is_finite(item):
            raise ValueError(f"{name}[{idx}] must be a finite number")
        parsed.append(float(item))
    return parsed


def _cholesky_psd(matrix: Sequence[Sequence[float]]) -> list[list[float]] | None:
    """Compute lower-triangular Cholesky factor L (A = L L^T) for symmetric PSD A.

    Returns ``None`` if ``matrix`` is asymmetric or not positive semi-definite.
    """
    n = len(matrix)
    for i in range(n):
        for j in range(i + 1, n):
            tol = _SYMMETRY_RTOL * max(1.0, abs(matrix[i][j]), abs(matrix[j][i]))
            if abs(matrix[i][j] - matrix[j][i]) > tol:
                return None

    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            off_sum = math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if lower[j][j] == 0.0:
                if abs(matrix[i][j] - off_sum) > _CHOLESKY_TOL * max(
                    1.0, abs(matrix[i][j])
                ):
                    return None
                lower[i][j] = 0.0
            else:
                lower[i][j] = (matrix[i][j] - off_sum) / lower[j][j]
        diag = matrix[i][i] - math.fsum(lower[i][k] * lower[i][k] for k in range(i))
        diag_tol = _CHOLESKY_TOL * max(1.0, abs(matrix[i][i]))
        if diag < -diag_tol:
            return None
        lower[i][i] = 0.0 if diag <= 0.0 else math.sqrt(diag)
    return lower


def _solve_linear_system(
    a_matrix: Sequence[Sequence[float]],
    b_matrix: Sequence[Sequence[float]],
) -> list[list[float]] | None:
    """Solve ``A @ X = B`` via Gaussian elimination with partial pivoting.

    Pure Python implementation; returns ``None`` if ``A`` is singular.
    """
    n = len(a_matrix)
    m = len(b_matrix[0])
    mat = [list(row) for row in a_matrix]
    rhs = [list(row) for row in b_matrix]

    max_entry = max((abs(val) for row in mat for val in row), default=0.0)
    if max_entry == 0.0:
        return None
    pivot_tol = _PIVOT_RTOL * max(1.0, max_entry)

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(mat[r][col]))
        if abs(mat[pivot_row][col]) <= pivot_tol:
            return None
        if pivot_row != col:
            mat[col], mat[pivot_row] = mat[pivot_row], mat[col]
            rhs[col], rhs[pivot_row] = rhs[pivot_row], rhs[col]

        pivot_val = mat[col][col]
        for row in range(col + 1, n):
            factor = mat[row][col] / pivot_val
            if factor == 0.0:
                continue
            mat[row][col] = 0.0
            for k in range(col + 1, n):
                mat[row][k] -= factor * mat[col][k]
            for j in range(m):
                rhs[row][j] -= factor * rhs[col][j]

    solution = [[0.0] * m for _ in range(n)]
    for row in range(n - 1, -1, -1):
        diag = mat[row][row]
        if abs(diag) <= pivot_tol:
            return None
        for j in range(m):
            acc = rhs[row][j] - math.fsum(
                mat[row][k] * solution[k][j] for k in range(row + 1, n)
            )
            solution[row][j] = acc / diag
    return solution


def _transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    if not matrix:
        return []
    rows = len(matrix)
    cols = len(matrix[0])
    return [[matrix[r][c] for r in range(rows)] for c in range(cols)]


def _matmul(
    left: Sequence[Sequence[float]],
    right: Sequence[Sequence[float]],
) -> list[list[float]]:
    n_rows = len(left)
    n_inner = len(left[0])
    n_cols = len(right[0])
    return [
        [
            math.fsum(left[i][k] * right[k][j] for k in range(n_inner))
            for j in range(n_cols)
        ]
        for i in range(n_rows)
    ]


def _matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    return [math.fsum(row[k] * vector[k] for k in range(len(vector))) for row in matrix]


def enkf_update_state(
    ensemble: Sequence[Sequence[float | int]],
    observation: Sequence[float | int | Missing] | Missing | None,
    observation_operator: Sequence[Sequence[float | int]],
    observation_error_cov: Sequence[Sequence[float | int]],
    seed: int = 0,
    min_bound: float | Sequence[float | int | None] | None = None,
    max_bound: float | Sequence[float | int | None] | None = None,
) -> EnKFUpdateResult | Missing:
    """Perform one Ensemble Kalman Filter (EnKF) state update step.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Computes the sample covariance ``P_f`` across ``ensemble`` (``X``, shape
    ``n_members x n_state``), forms the innovation covariance
    ``S = H P_f H^T + R``, solves ``K = P_f H^T S^{-1}`` via pure-Python
    Gaussian elimination with partial pivoting, perturbs ``observation`` using
    ``R = L L^T`` and deterministic PRNG ``seed``, updates every ensemble
    member, and optionally clamps states to ``[min_bound, max_bound]``.

    Missing observations or invalid/singular matrices return a typed
    ``Missing`` (``MISSING_INPUT`` or ``NOT_COMPUTABLE``), never ``0``.
    Caller type defects (non-sequence inputs, booleans, invalid ``seed`` type,
    or invalid bound specifications) raise ``TypeError`` or ``ValueError`` (G5).
    """
    if not _is_strict_int(seed):
        raise TypeError(f"seed: expected int, got {type(seed).__name__} (G5)")

    obs = _validate_observation(observation)
    if isinstance(obs, Missing):
        return obs

    x_mat = _validate_matrix("ensemble", ensemble)
    if isinstance(x_mat, Missing):
        return x_mat

    h_mat = _validate_matrix("observation_operator", observation_operator)
    if isinstance(h_mat, Missing):
        return h_mat

    r_mat = _validate_matrix("observation_error_cov", observation_error_cov)
    if isinstance(r_mat, Missing):
        return r_mat

    n_members = len(x_mat)
    n_state = len(x_mat[0])
    n_obs = len(obs)

    if n_members < 2:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                "ensemble must have at least 2 members to compute sample "
                f"covariance, got {n_members}"
            ),
        )
    if len(h_mat) != n_obs or len(h_mat[0]) != n_state:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"observation_operator shape ({len(h_mat)}x{len(h_mat[0])}) does "
                f"not match ({n_obs}x{n_state})"
            ),
        )
    if len(r_mat) != n_obs or len(r_mat[0]) != n_obs:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"observation_error_cov shape ({len(r_mat)}x{len(r_mat[0])}) does "
                f"not match ({n_obs}x{n_obs})"
            ),
        )

    lower_bounds = _parse_bound_vector("min_bound", min_bound, n_state)
    upper_bounds = _parse_bound_vector("max_bound", max_bound, n_state)
    for j in range(n_state):
        lo = lower_bounds[j]
        hi = upper_bounds[j]
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(
                f"state bound[{j}] invalid: min_bound ({lo}) > max_bound ({hi})"
            )

    r_chol = _cholesky_psd(r_mat)
    if r_chol is None:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="observation_error_cov must be symmetric positive semi-definite",
        )

    # Forecast mean and sample covariance P_f = (1 / (N - 1)) * A^T A.
    forecast_mean = [
        math.fsum(x_mat[i][j] for i in range(n_members)) / n_members
        for j in range(n_state)
    ]
    anomalies = [
        [x_mat[i][j] - forecast_mean[j] for j in range(n_state)]
        for i in range(n_members)
    ]
    denom = float(n_members - 1)
    p_f = [
        [
            math.fsum(anomalies[i][j] * anomalies[i][k] for i in range(n_members))
            / denom
            for k in range(n_state)
        ]
        for j in range(n_state)
    ]

    # Explicit Kalman gain: K = P_f H^T (H P_f H^T + R)^{-1}.
    h_t = _transpose(h_mat)
    p_f_ht = _matmul(p_f, h_t)
    h_p_f_ht = _matmul(h_mat, p_f_ht)
    innovation_cov = [
        [h_p_f_ht[i][j] + r_mat[i][j] for j in range(n_obs)] for i in range(n_obs)
    ]

    k_transpose = _solve_linear_system(innovation_cov, _transpose(p_f_ht))
    if k_transpose is None:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="innovation covariance matrix (H P_f H^T + R) is singular",
        )
    kalman_gain = _transpose(k_transpose)

    # Perturbed observations: y_tilde_i = y + (eps_i - mean(eps)), eps_i ~ N(0, R).
    rng = random.Random(seed)
    raw_eps: list[list[float]] = []
    for _ in range(n_members):
        z = [rng.gauss(0.0, 1.0) for _ in range(n_obs)]
        raw_eps.append(_matvec(r_chol, z))
    eps_mean = [
        math.fsum(raw_eps[i][j] for i in range(n_members)) / n_members
        for j in range(n_obs)
    ]
    perturbed_obs = [
        [obs[j] + (raw_eps[i][j] - eps_mean[j]) for j in range(n_obs)]
        for i in range(n_members)
    ]

    # Member-by-member EnKF analysis update and optional state clamping.
    clamped = False
    posterior_rows: list[tuple[float, ...]] = []
    for i in range(n_members):
        predicted_obs = _matvec(h_mat, x_mat[i])
        innovation = [perturbed_obs[i][j] - predicted_obs[j] for j in range(n_obs)]
        correction = _matvec(kalman_gain, innovation)
        updated_state: list[float] = []
        for j in range(n_state):
            val = x_mat[i][j] + correction[j]
            if not _is_finite(val):
                return Missing(
                    reason="NOT_COMPUTABLE",
                    detail="updated ensemble state produced a non-finite value",
                )
            lo = lower_bounds[j]
            hi = upper_bounds[j]
            if lo is not None and val < lo:
                val = lo
                clamped = True
            if hi is not None and val > hi:
                val = hi
                clamped = True
            updated_state.append(val)
        posterior_rows.append(tuple(updated_state))

    posterior_mean = tuple(
        math.fsum(posterior_rows[i][j] for i in range(n_members)) / n_members
        for j in range(n_state)
    )
    forecast_mean_tuple = tuple(forecast_mean)
    analysis_increment = tuple(
        math.fsum((post, -fore))
        for post, fore in zip(posterior_mean, forecast_mean_tuple)
    )

    return EnKFUpdateResult(
        posterior_ensemble=tuple(posterior_rows),
        forecast_mean=forecast_mean_tuple,
        posterior_mean=posterior_mean,
        forecast_cov=tuple(tuple(row) for row in p_f),
        kalman_gain=tuple(tuple(row) for row in kalman_gain),
        innovation_cov=tuple(tuple(row) for row in innovation_cov),
        analysis_increment=analysis_increment,
        perturbed_observations=tuple(tuple(row) for row in perturbed_obs),
        clamped=clamped,
    )


def _check_scalar_step_input(name: str, value: object) -> float | Missing:
    if isinstance(value, Missing):
        return _normalize_missing(value, name)
    if not _is_number(value):
        raise TypeError(
            f"{name}: expected float, int, or Missing, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite(value):
        return Missing(reason="NOT_COMPUTABLE", detail=f"{name} is not finite")
    return float(value)


def assimilate_water_step(
    *,
    date: datetime.date,
    storage_before_mm: float | Missing,
    physical_inflow_mm: float | Missing,
    physical_outflow_mm: float | Missing,
    ensemble: Sequence[Sequence[float | int]],
    observation: Sequence[float | int | Missing] | Missing | None,
    observation_operator: Sequence[Sequence[float | int]],
    observation_error_cov: Sequence[Sequence[float | int]],
    seed: int = 0,
    min_bound: float | Sequence[float | int | None] | None = None,
    max_bound: float | Sequence[float | int | None] | None = None,
    storage_state_index: int = 0,
    holdout_split: HoldoutSplit | None = None,
) -> AssimilationStepRecord | Missing:
    """Execute one water storage EnKF assimilation step with conservation tracking.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Checks ``holdout_split`` first (raises ``ValueError`` if ``date`` is a
    validation date or outside ``assimilation_dates``), validates physical
    balance terms, executes ``enkf_update_state``, verifies that the forecast
    ensemble mean at ``storage_state_index`` matches
    ``storage_before_mm + physical_inflow_mm - physical_outflow_mm``, and
    returns an ``AssimilationStepRecord`` with
    ``attributed_to_precipitation=False``.
    """
    if not _is_strict_date(date):
        raise TypeError(f"date: expected datetime.date, got {type(date).__name__} (G5)")
    if not _is_strict_int(storage_state_index):
        raise TypeError(
            "storage_state_index: expected int, got "
            f"{type(storage_state_index).__name__} (G5)"
        )
    if holdout_split is not None:
        if not isinstance(holdout_split, HoldoutSplit):
            raise TypeError(
                "holdout_split: expected HoldoutSplit or None, got "
                f"{type(holdout_split).__name__} (G5)"
            )
        holdout_split.assert_assimilation_allowed(date)

    s_before = _check_scalar_step_input("storage_before_mm", storage_before_mm)
    if isinstance(s_before, Missing):
        return s_before
    inflow = _check_scalar_step_input("physical_inflow_mm", physical_inflow_mm)
    if isinstance(inflow, Missing):
        return inflow
    outflow = _check_scalar_step_input("physical_outflow_mm", physical_outflow_mm)
    if isinstance(outflow, Missing):
        return outflow

    update = enkf_update_state(
        ensemble=ensemble,
        observation=observation,
        observation_operator=observation_operator,
        observation_error_cov=observation_error_cov,
        seed=seed,
        min_bound=min_bound,
        max_bound=max_bound,
    )
    if isinstance(update, Missing):
        return update

    n_state = len(update.forecast_mean)
    if not (0 <= storage_state_index < n_state):
        raise ValueError(
            f"storage_state_index ({storage_state_index}) out of range for "
            f"state dimension {n_state}"
        )

    mean_forecast_mm = update.forecast_mean[storage_state_index]
    mean_posterior_mm = update.posterior_mean[storage_state_index]
    analysis_increment_mm = update.analysis_increment[storage_state_index]

    physical_forecast = math.fsum((s_before, inflow, -outflow))
    scale = max(1.0, abs(s_before), abs(inflow), abs(outflow), abs(mean_forecast_mm))
    if abs(mean_forecast_mm - physical_forecast) > _CONSERVATION_RTOL * scale:
        raise ValueError(
            "ensemble forecast mean at storage_state_index does not match "
            "storage_before_mm + physical_inflow_mm - physical_outflow_mm "
            f"({mean_forecast_mm} != {physical_forecast})"
        )

    storage_after_mm = mean_posterior_mm
    expected_after = math.fsum((s_before, inflow, -outflow, analysis_increment_mm))
    residual = math.fsum((storage_after_mm, -expected_after))

    return AssimilationStepRecord(
        date=date,
        storage_before_mm=s_before,
        physical_inflow_mm=inflow,
        physical_outflow_mm=outflow,
        mean_forecast_mm=mean_forecast_mm,
        mean_posterior_mm=mean_posterior_mm,
        analysis_increment_mm=analysis_increment_mm,
        storage_after_mm=storage_after_mm,
        attributed_to_precipitation=False,
        mass_balance_residual_mm=residual,
        update_result=update,
    )
