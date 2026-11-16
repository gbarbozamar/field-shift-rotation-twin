"""Differentiable sensitivity, KGML residual gating, conformal and Bayesian calibration.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements four composable pure-Python building blocks using only Python 3.12
standard library modules (``math``, ``dataclasses``, ``decimal``, ``types``)
and ``contracts.results.models``:

1. ``Dual`` number arithmetic and ``differentiable_sensitivity`` for exact
   forward-mode automatic differentiation sensitivities, explicitly carrying
   ``derivatives_guarantee_physical_accuracy=False``.
2. ``validate_mass_conserving_residual``: knowledge-guided mass-conservation
   gate verifying ``abs((storage_end - storage_start) - (inflows - outflows +
   residual_fluxes)) <= tol`` and rejecting non-conservative learned residual
   corrections with ``CONTROL_FAILED``.
3. ``split_conformal_calibrate_and_evaluate``: split-conformal nonconformity
   calibration strictly on ``calibration_residuals`` and empirical evaluation on
   disjoint ``reserved_holdout``, rejecting overlaps and undeclared temporal or
   spatial shift blocks, and always setting
   ``unconditional_field_guarantee=False``.
4. ``discrete_bayesian_update``: discrete-grid Bayesian parameter/bias updater
   via likelihood over observations, exposing ``interval_narrowed`` because an
   informative observation can shift the mean/mode or reveal model bias without
   guaranteeing interval narrowing.

Pure functions (G1): no file access, no network call, no clock, no global
mutable state, no environment variable, and inputs are never mutated.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from contracts.results.models import Missing

__all__ = [
    "ConformalSample",
    "DifferentiableSensitivityResult",
    "DiscreteBayesianUpdateResult",
    "Dual",
    "MassConservationGateResult",
    "SplitConformalResult",
    "differentiable_sensitivity",
    "discrete_bayesian_update",
    "dual_exp",
    "dual_log",
    "max_smooth",
    "split_conformal_calibrate_and_evaluate",
    "validate_mass_conserving_residual",
]

_REV13_STATUS_LABEL = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"


def _is_number(value: object) -> bool:
    """Return True for finite-candidate int/float values, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_finite_float(name: str, value: object) -> float:
    """Convert a non-bool int/float to finite float, else raise."""
    if not _is_number(value):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite number")
    return numeric


def _check_non_blank_str(name: str, value: object) -> str:
    """Validate that value is a non-blank string."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, not {type(value).__name__}")
    if value.strip() == "":
        raise ValueError(f"{name} must not be empty or blank")
    return value


def _coerce_dual(operand: object) -> Dual | None:
    """Convert Dual or finite real number to Dual; return None if unsupported."""
    if isinstance(operand, Dual):
        return operand
    if _is_number(operand):
        return Dual(_check_finite_float("operand", operand), 0.0)
    return None


# ---------------------------------------------------------------------------
# 1. Forward-mode automatic differentiation via Dual numbers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dual:
    """Forward-mode dual number ``value + deriv * eps`` with ``eps**2 == 0``."""

    value: float
    deriv: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _check_finite_float("value", self.value))
        object.__setattr__(self, "deriv", _check_finite_float("deriv", self.deriv))

    def __pos__(self) -> Dual:
        return self

    def __neg__(self) -> Dual:
        return Dual(-self.value, -self.deriv)

    def __add__(self, other: object) -> Dual:
        rhs = _coerce_dual(other)
        if rhs is None:
            return NotImplemented
        return Dual(self.value + rhs.value, self.deriv + rhs.deriv)

    def __radd__(self, other: object) -> Dual:
        lhs = _coerce_dual(other)
        if lhs is None:
            return NotImplemented
        return Dual(lhs.value + self.value, lhs.deriv + self.deriv)

    def __sub__(self, other: object) -> Dual:
        rhs = _coerce_dual(other)
        if rhs is None:
            return NotImplemented
        return Dual(self.value - rhs.value, self.deriv - rhs.deriv)

    def __rsub__(self, other: object) -> Dual:
        lhs = _coerce_dual(other)
        if lhs is None:
            return NotImplemented
        return Dual(lhs.value - self.value, lhs.deriv - self.deriv)

    def __mul__(self, other: object) -> Dual:
        rhs = _coerce_dual(other)
        if rhs is None:
            return NotImplemented
        return Dual(
            self.value * rhs.value,
            self.deriv * rhs.value + self.value * rhs.deriv,
        )

    def __rmul__(self, other: object) -> Dual:
        lhs = _coerce_dual(other)
        if lhs is None:
            return NotImplemented
        return Dual(
            lhs.value * self.value,
            lhs.deriv * self.value + lhs.value * self.deriv,
        )

    def __truediv__(self, other: object) -> Dual:
        rhs = _coerce_dual(other)
        if rhs is None:
            return NotImplemented
        return _dual_div(self, rhs)

    def __rtruediv__(self, other: object) -> Dual:
        lhs = _coerce_dual(other)
        if lhs is None:
            return NotImplemented
        return _dual_div(lhs, self)

    def __pow__(self, other: object) -> Dual:
        rhs = _coerce_dual(other)
        if rhs is None:
            return NotImplemented
        return _dual_pow(self, rhs)

    def __rpow__(self, other: object) -> Dual:
        lhs = _coerce_dual(other)
        if lhs is None:
            return NotImplemented
        return _dual_pow(lhs, self)

    def exp(self) -> Dual:
        """Return ``exp(self)`` with exact chain-rule derivative."""
        return dual_exp(self)

    def log(self) -> Dual:
        """Return ``log(self)`` with exact chain-rule derivative."""
        return dual_log(self)

    def max_smooth(self, other: Dual | float, sharpness: float = 50.0) -> Dual:
        """Return LogSumExp smooth maximum of ``self`` and ``other``."""
        return max_smooth(self, other, sharpness=sharpness)


def _dual_div(num: Dual, den: Dual) -> Dual:
    if den.value == 0.0:
        raise ZeroDivisionError("division by zero in Dual arithmetic")
    val = num.value / den.value
    deriv = (num.deriv * den.value - num.value * den.deriv) / (den.value * den.value)
    return Dual(val, deriv)


def _dual_pow(base: Dual, exponent: Dual) -> Dual:
    u = base.value
    du = base.deriv
    v = exponent.value
    dv = exponent.deriv

    if dv == 0.0:
        if v == 0.0:
            return Dual(1.0, 0.0)
        if u == 0.0:
            if v > 1.0:
                return Dual(0.0, 0.0)
            if v == 1.0:
                return Dual(0.0, du)
            if du == 0.0:
                if v < 0.0:
                    raise ZeroDivisionError("zero cannot be raised to a negative power")
                return Dual(0.0, 0.0)
            raise ValueError("derivative of u**v at u == 0 is singular for v < 1")
        if u < 0.0 and not v.is_integer():
            raise ValueError("negative Dual base requires an integer exponent")
        val = u**v
        deriv = v * (u ** (v - 1.0)) * du
        return Dual(val, deriv)

    if u <= 0.0:
        raise ValueError("general Dual power u**v with varying exponent requires u > 0")
    val = u**v
    deriv = val * (dv * math.log(u) + v * du / u)
    return Dual(val, deriv)


def dual_exp(x: Dual | float) -> Dual:
    """Compute ``exp(x)`` in forward-mode automatic differentiation."""
    d = _coerce_dual(x)
    if d is None:
        raise TypeError(f"x must be Dual or number, not {type(x).__name__}")
    val = math.exp(d.value)
    return Dual(val, val * d.deriv)


def dual_log(x: Dual | float) -> Dual:
    """Compute natural logarithm ``log(x)`` in forward-mode AD."""
    d = _coerce_dual(x)
    if d is None:
        raise TypeError(f"x must be Dual or number, not {type(x).__name__}")
    if d.value <= 0.0:
        raise ValueError("log domain error: value must be strictly positive")
    return Dual(math.log(d.value), d.deriv / d.value)


def max_smooth(
    a: Dual | float,
    b: Dual | float,
    sharpness: float = 50.0,
) -> Dual:
    """LogSumExp smooth maximum ``(1 / sharpness) * log(exp(s*a) + exp(s*b))``.

    Uses max-shifting for numerical stability so large ``sharpness`` never
    overflows, and propagates exact softmax-weighted derivatives.
    """
    da = _coerce_dual(a)
    db = _coerce_dual(b)
    if da is None:
        raise TypeError(f"a must be Dual or number, not {type(a).__name__}")
    if db is None:
        raise TypeError(f"b must be Dual or number, not {type(b).__name__}")
    s = _check_finite_float("sharpness", sharpness)
    if s <= 0.0:
        raise ValueError("sharpness must be strictly positive")

    m = max(da.value, db.value)
    exp_a = math.exp(s * (da.value - m))
    exp_b = math.exp(s * (db.value - m))
    denom = exp_a + exp_b
    val = m + math.log(denom) / s
    weight_a = exp_a / denom
    weight_b = exp_b / denom
    deriv = weight_a * da.deriv + weight_b * db.deriv
    return Dual(val, deriv)


@dataclass(frozen=True)
class DifferentiableSensitivityResult:
    """Exact forward-mode sensitivities ``dy/dtheta`` for a differentiable model.

    Always sets ``derivatives_guarantee_physical_accuracy = False`` per Rev13.
    """

    value: float
    sensitivities: Mapping[str, float]
    derivatives_guarantee_physical_accuracy: bool = False
    status_note: str = _REV13_STATUS_LABEL

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _check_finite_float("value", self.value))
        if self.derivatives_guarantee_physical_accuracy is not False:
            raise ValueError(
                "derivatives_guarantee_physical_accuracy must remain False"
            )
        frozen_sens = {
            _check_non_blank_str("parameter name", key): _check_finite_float(
                f"sensitivity[{key}]", val
            )
            for key, val in self.sensitivities.items()
        }
        object.__setattr__(self, "sensitivities", MappingProxyType(frozen_sens))


def differentiable_sensitivity(
    fn: Callable[[Mapping[str, Dual]], Dual | float | int],
    parameters: Mapping[str, float | int],
) -> DifferentiableSensitivityResult:
    """Compute exact forward-mode sensitivities ``dy/dtheta`` for ``fn``.

    Evaluates ``fn`` once per parameter with a unit seed ``Dual(theta, 1.0)``
    on that parameter and zero derivatives on all others.
    """
    if not callable(fn):
        raise TypeError("fn must be callable")
    if not isinstance(parameters, Mapping):
        raise TypeError("parameters must be a Mapping")
    if len(parameters) == 0:
        raise ValueError("parameters must not be empty")

    clean_params: dict[str, float] = {}
    for key, raw_val in parameters.items():
        name = _check_non_blank_str("parameter name", key)
        clean_params[name] = _check_finite_float(f"parameters[{name}]", raw_val)

    sensitivities: dict[str, float] = {}
    primal_value: float | None = None
    for target_name in clean_params:
        seeded = MappingProxyType(
            {
                name: Dual(val, 1.0 if name == target_name else 0.0)
                for name, val in clean_params.items()
            }
        )
        raw_out = fn(seeded)
        out = _coerce_dual(raw_out)
        if out is None:
            raise TypeError(
                f"fn must return Dual or number, not {type(raw_out).__name__}"
            )
        if primal_value is None:
            primal_value = out.value
        elif not math.isclose(out.value, primal_value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(
                "fn produced inconsistent primal values across parameter seeds"
            )
        sensitivities[target_name] = out.deriv

    assert primal_value is not None
    return DifferentiableSensitivityResult(
        value=primal_value,
        sensitivities=MappingProxyType(sensitivities),
        derivatives_guarantee_physical_accuracy=False,
    )


# ---------------------------------------------------------------------------
# 2. Knowledge-Guided mass-conservation residual gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MassConservationGateResult:
    """Outcome of checking learned/hybrid residual fluxes against mass closure."""

    passed: bool
    status: str
    storage_change: float | Missing
    net_flux_with_residual: float | Missing
    discrepancy: float | Missing
    tolerance: float
    control_failure: Missing | None = None
    status_note: str = _REV13_STATUS_LABEL


def _resolve_flux_or_missing(
    name: str, value: float | Sequence[float | int | Missing] | Missing
) -> tuple[float | None, str | None]:
    """Sum scalar or sequence flux; return (total, None) or (None, detail)."""
    if isinstance(value, Missing):
        detail = f"{name} is missing ({value.reason})"
        if value.detail:
            detail = f"{detail}: {value.detail}"
        return None, detail

    if _is_number(value):
        return _check_finite_float(name, value), None

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        total = 0.0
        for idx, item in enumerate(value):
            if isinstance(item, Missing):
                detail = f"{name}[{idx}] is missing ({item.reason})"
                if item.detail:
                    detail = f"{detail}: {item.detail}"
                return None, detail
            total += _check_finite_float(f"{name}[{idx}]", item)
        return total, None

    raise TypeError(
        f"{name} must be a number, sequence of numbers, or Missing, "
        f"not {type(value).__name__}"
    )


def validate_mass_conserving_residual(
    storage_start: float | Missing,
    storage_end: float | Missing,
    inflows: float | Sequence[float | int | Missing] | Missing,
    outflows: float | Sequence[float | int | Missing] | Missing,
    residual_fluxes: float | Sequence[float | int | Missing] | Missing,
    tol: float,
) -> MassConservationGateResult:
    """Verify exact mass closure of a physical + residual-flux step.

    Verifies:
        ``abs((storage_end - storage_start) - (inflows - outflows + residual_fluxes)) <= tol``

    Non-conservative learned residual corrections are rejected with
    ``Missing(reason="CONTROL_FAILED", ...)`` and ``status="CONTROL_FAILED"``.
    Any missing input propagates as ``Missing(reason="MISSING_INPUT", ...)``
    instead of silently defaulting to zero.
    """
    tol_val = _check_finite_float("tol", tol)
    if tol_val < 0.0:
        raise ValueError("tol must not be negative")

    s_start, miss_start = _resolve_flux_or_missing("storage_start", storage_start)
    s_end, miss_end = _resolve_flux_or_missing("storage_end", storage_end)
    inf_val, miss_inf = _resolve_flux_or_missing("inflows", inflows)
    out_val, miss_out = _resolve_flux_or_missing("outflows", outflows)
    res_val, miss_res = _resolve_flux_or_missing("residual_fluxes", residual_fluxes)

    missing_details = [
        d for d in (miss_start, miss_end, miss_inf, miss_out, miss_res) if d is not None
    ]
    if missing_details:
        missing_obj = Missing(
            reason="MISSING_INPUT",
            detail="; ".join(missing_details),
        )
        return MassConservationGateResult(
            passed=False,
            status="MISSING_INPUT",
            storage_change=missing_obj,
            net_flux_with_residual=missing_obj,
            discrepancy=missing_obj,
            tolerance=tol_val,
            control_failure=missing_obj,
        )

    assert (
        s_start is not None
        and s_end is not None
        and inf_val is not None
        and out_val is not None
        and res_val is not None
    )
    storage_change = s_end - s_start
    net_flux = inf_val - out_val + res_val
    discrepancy = abs(storage_change - net_flux)

    if discrepancy <= tol_val:
        return MassConservationGateResult(
            passed=True,
            status="PASSED",
            storage_change=storage_change,
            net_flux_with_residual=net_flux,
            discrepancy=discrepancy,
            tolerance=tol_val,
            control_failure=None,
        )

    failure = Missing(
        reason="CONTROL_FAILED",
        detail=(
            f"mass conservation check failed: discrepancy {discrepancy} "
            f"exceeds tolerance {tol_val}"
        ),
    )
    return MassConservationGateResult(
        passed=False,
        status="CONTROL_FAILED",
        storage_change=storage_change,
        net_flux_with_residual=net_flux,
        discrepancy=discrepancy,
        tolerance=tol_val,
        control_failure=failure,
    )


# ---------------------------------------------------------------------------
# 3. Split-conformal prediction evaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConformalSample:
    """One residual observation with identity and temporal/spatial block tags."""

    sample_id: str
    residual: float
    temporal_block: str
    spatial_block: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sample_id", _check_non_blank_str("sample_id", self.sample_id)
        )
        object.__setattr__(
            self, "residual", _check_finite_float("residual", self.residual)
        )
        object.__setattr__(
            self,
            "temporal_block",
            _check_non_blank_str("temporal_block", self.temporal_block),
        )
        object.__setattr__(
            self,
            "spatial_block",
            _check_non_blank_str("spatial_block", self.spatial_block),
        )


@dataclass(frozen=True)
class SplitConformalResult:
    """Split-conformal calibration and reserved-holdout coverage evaluation.

    Always sets ``unconditional_field_guarantee = False`` per Rev13.
    """

    alpha: float
    target_coverage: float
    quantile: float
    interval_width: float
    calibration_count: int
    holdout_count: int
    covered_count: int
    empirical_coverage: float
    temporal_blocks_calibration: tuple[str, ...]
    temporal_blocks_holdout: tuple[str, ...]
    spatial_blocks_calibration: tuple[str, ...]
    spatial_blocks_holdout: tuple[str, ...]
    temporal_shift_present: bool
    spatial_shift_present: bool
    declared_temporal_shift: bool
    declared_spatial_shift: bool
    shift_declaration: str | None = None
    unconditional_field_guarantee: bool = False
    status_note: str = _REV13_STATUS_LABEL

    def __post_init__(self) -> None:
        if self.unconditional_field_guarantee is not False:
            raise ValueError(
                "unconditional_field_guarantee must remain False per Rev13"
            )


def _validate_sample_block(
    name: str, samples: Sequence[ConformalSample]
) -> tuple[ConformalSample, ...]:
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of ConformalSample")
    if len(samples) == 0:
        raise ValueError(f"{name} must not be empty")
    seen_ids: set[str] = set()
    validated: list[ConformalSample] = []
    for idx, sample in enumerate(samples):
        if not isinstance(sample, ConformalSample):
            raise TypeError(
                f"{name}[{idx}] must be ConformalSample, not {type(sample).__name__}"
            )
        if sample.sample_id in seen_ids:
            raise ValueError(f"duplicate sample_id {sample.sample_id!r} in {name}")
        seen_ids.add(sample.sample_id)
        validated.append(sample)
    return tuple(validated)


def split_conformal_calibrate_and_evaluate(
    calibration_residuals: Sequence[ConformalSample],
    reserved_holdout: Sequence[ConformalSample],
    *,
    alpha: float,
    declared_temporal_shift: bool = False,
    declared_spatial_shift: bool = False,
    shift_declaration: str | None = None,
) -> SplitConformalResult:
    """Calibrate symmetric split-conformal quantile and evaluate on holdout.

    Raises ``ValueError`` if:
    - ``calibration_residuals`` and ``reserved_holdout`` share any ``sample_id``,
    - temporal or spatial shift blocks are mixed without explicit declaration,
    - ``alpha`` is outside ``(0, 1)``, or
    - ``calibration_residuals`` is too small for finite quantile at ``1 - alpha``.
    """
    alpha_val = _check_finite_float("alpha", alpha)
    if not (0.0 < alpha_val < 1.0):
        raise ValueError("alpha must satisfy 0 < alpha < 1")
    if not isinstance(declared_temporal_shift, bool):
        raise TypeError("declared_temporal_shift must be a bool")
    if not isinstance(declared_spatial_shift, bool):
        raise TypeError("declared_spatial_shift must be a bool")
    if shift_declaration is not None:
        shift_declaration = _check_non_blank_str("shift_declaration", shift_declaration)

    cal = _validate_sample_block("calibration_residuals", calibration_residuals)
    holdout = _validate_sample_block("reserved_holdout", reserved_holdout)

    cal_ids = {s.sample_id for s in cal}
    hold_ids = {s.sample_id for s in holdout}
    overlap = sorted(cal_ids & hold_ids)
    if overlap:
        raise ValueError(
            "calibration_residuals and reserved_holdout overlap on sample_id(s): "
            + ", ".join(overlap)
        )

    cal_temporal = tuple(sorted({s.temporal_block for s in cal}))
    hold_temporal = tuple(sorted({s.temporal_block for s in holdout}))
    all_temporal = set(cal_temporal) | set(hold_temporal)
    temporal_shift_present = len(all_temporal) > 1
    if temporal_shift_present and not declared_temporal_shift:
        raise ValueError(
            "temporal shift blocks are mixed without declaration: "
            f"{sorted(all_temporal)}"
        )

    cal_spatial = tuple(sorted({s.spatial_block for s in cal}))
    hold_spatial = tuple(sorted({s.spatial_block for s in holdout}))
    all_spatial = set(cal_spatial) | set(hold_spatial)
    spatial_shift_present = len(all_spatial) > 1
    if spatial_shift_present and not declared_spatial_shift:
        raise ValueError(
            f"spatial shift blocks are mixed without declaration: {sorted(all_spatial)}"
        )

    n = len(cal)
    # Exact decimal arithmetic prevents float rounding off-by-one in ceil.
    rank = math.ceil(Decimal(str(n + 1)) * (Decimal(1) - Decimal(str(alpha_val))))
    if rank > n:
        raise ValueError(
            f"calibration set size {n} is too small for finite split-conformal "
            f"quantile at alpha={alpha_val} (required rank {rank} > {n})"
        )
    rank = max(1, rank)

    cal_scores = sorted(abs(s.residual) for s in cal)
    quantile = cal_scores[rank - 1]

    covered_count = sum(1 for s in holdout if abs(s.residual) <= quantile)
    empirical_coverage = covered_count / len(holdout)

    return SplitConformalResult(
        alpha=alpha_val,
        target_coverage=1.0 - alpha_val,
        quantile=quantile,
        interval_width=2.0 * quantile,
        calibration_count=n,
        holdout_count=len(holdout),
        covered_count=covered_count,
        empirical_coverage=empirical_coverage,
        temporal_blocks_calibration=cal_temporal,
        temporal_blocks_holdout=hold_temporal,
        spatial_blocks_calibration=cal_spatial,
        spatial_blocks_holdout=hold_spatial,
        temporal_shift_present=temporal_shift_present,
        spatial_shift_present=spatial_shift_present,
        declared_temporal_shift=declared_temporal_shift,
        declared_spatial_shift=declared_spatial_shift,
        shift_declaration=shift_declaration,
        unconditional_field_guarantee=False,
    )


# ---------------------------------------------------------------------------
# 4. Discrete-grid Bayesian parameter / bias updater
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscreteBayesianUpdateResult:
    """Posterior summary over a discrete parameter or bias grid."""

    grid_values: tuple[float, ...]
    prior_probs: tuple[float, ...]
    posterior_probs: tuple[float, ...]
    prior_mean: float
    posterior_mean: float
    mean_shift: float
    prior_mode: float
    posterior_mode: float
    mode_shifted: bool
    prior_std: float
    posterior_std: float
    credible_level: float
    prior_interval: tuple[float, float]
    posterior_interval: tuple[float, float]
    prior_interval_width: float
    posterior_interval_width: float
    interval_narrowed: bool
    effective_sample_size: float
    status_note: str = _REV13_STATUS_LABEL


def _discrete_moments(
    values: tuple[float, ...], probs: tuple[float, ...]
) -> tuple[float, float, float]:
    """Return (mean, mode, std) of a discrete probability distribution."""
    mean = sum(v * p for v, p in zip(values, probs, strict=True))
    var = sum(((v - mean) ** 2) * p for v, p in zip(values, probs, strict=True))
    std = math.sqrt(max(0.0, var))
    best_idx = max(range(len(values)), key=lambda idx: probs[idx])
    mode = values[best_idx]
    return mean, mode, std


def _discrete_quantile(
    values: tuple[float, ...], probs: tuple[float, ...], q: float
) -> float:
    """Return smallest grid value whose cumulative probability reaches ``q``."""
    cumulative = 0.0
    for val, prob in zip(values, probs, strict=True):
        cumulative += prob
        if cumulative + 1e-15 >= q:
            return val
    return values[-1]


def _discrete_credible_interval(
    values: tuple[float, ...], probs: tuple[float, ...], credible_level: float
) -> tuple[float, float]:
    tail = (1.0 - credible_level) / 2.0
    low = _discrete_quantile(values, probs, tail)
    high = _discrete_quantile(values, probs, 1.0 - tail)
    return (low, high)


def discrete_bayesian_update(
    grid_values: Sequence[float | int],
    prior_weights: Sequence[float | int],
    observations: Sequence[float | int],
    likelihood_fn: Callable[[float, float], float | int],
    *,
    credible_level: float,
) -> DiscreteBayesianUpdateResult:
    """Update discrete prior weights via observation likelihoods.

    Computes normalized posterior weights in log space where weights are
    positive, then reports mean/mode shift and whether the equal-tailed
    credible interval narrowed (``interval_narrowed: bool``). Informative
    observations that shift mass or reveal structural bias do not guarantee
    interval narrowing.
    """
    if not isinstance(grid_values, Sequence) or isinstance(grid_values, (str, bytes)):
        raise TypeError("grid_values must be a sequence of numbers")
    if not isinstance(prior_weights, Sequence) or isinstance(
        prior_weights, (str, bytes)
    ):
        raise TypeError("prior_weights must be a sequence of numbers")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise TypeError("observations must be a sequence of numbers")
    if not callable(likelihood_fn):
        raise TypeError("likelihood_fn must be callable")

    level = _check_finite_float("credible_level", credible_level)
    if not (0.0 < level < 1.0):
        raise ValueError("credible_level must satisfy 0 < credible_level < 1")

    if len(grid_values) == 0:
        raise ValueError("grid_values must not be empty")
    if len(grid_values) != len(prior_weights):
        raise ValueError("grid_values and prior_weights must have the same length")
    if len(observations) == 0:
        raise ValueError("observations must not be empty")

    clean_grid = tuple(
        _check_finite_float(f"grid_values[{i}]", v) for i, v in enumerate(grid_values)
    )
    for i in range(1, len(clean_grid)):
        if clean_grid[i] <= clean_grid[i - 1]:
            raise ValueError("grid_values must be strictly increasing")

    clean_weights: list[float] = []
    for i, w in enumerate(prior_weights):
        w_val = _check_finite_float(f"prior_weights[{i}]", w)
        if w_val < 0.0:
            raise ValueError("prior_weights must not be negative")
        clean_weights.append(w_val)

    prior_total = sum(clean_weights)
    if prior_total <= 0.0:
        raise ValueError("prior_weights must sum to a strictly positive value")
    prior_probs = tuple(w / prior_total for w in clean_weights)

    clean_obs = tuple(
        _check_finite_float(f"observations[{i}]", y) for i, y in enumerate(observations)
    )

    log_unnorm: list[float | None] = []
    for theta, p_prior in zip(clean_grid, prior_probs, strict=True):
        if p_prior == 0.0:
            log_unnorm.append(None)
            continue
        log_w = math.log(p_prior)
        zero_lik = False
        for obs in clean_obs:
            lik = _check_finite_float("likelihood", likelihood_fn(theta, obs))
            if lik < 0.0:
                raise ValueError("likelihood_fn must return non-negative values")
            if lik == 0.0:
                zero_lik = True
                break
            log_w += math.log(lik)
        log_unnorm.append(None if zero_lik else log_w)

    active_logs = [lw for lw in log_unnorm if lw is not None]
    if not active_logs:
        raise ValueError(
            "total posterior weight is zero: observations are incompatible "
            "with all positive-prior grid points"
        )

    max_log = max(active_logs)
    unnorm_weights = [
        0.0 if lw is None else math.exp(lw - max_log) for lw in log_unnorm
    ]
    post_total = sum(unnorm_weights)
    posterior_probs = tuple(w / post_total for w in unnorm_weights)

    prior_mean, prior_mode, prior_std = _discrete_moments(clean_grid, prior_probs)
    post_mean, post_mode, post_std = _discrete_moments(clean_grid, posterior_probs)

    prior_iv = _discrete_credible_interval(clean_grid, prior_probs, level)
    post_iv = _discrete_credible_interval(clean_grid, posterior_probs, level)
    prior_width = prior_iv[1] - prior_iv[0]
    post_width = post_iv[1] - post_iv[0]

    ess = 1.0 / sum(p * p for p in posterior_probs)

    return DiscreteBayesianUpdateResult(
        grid_values=clean_grid,
        prior_probs=prior_probs,
        posterior_probs=posterior_probs,
        prior_mean=prior_mean,
        posterior_mean=post_mean,
        mean_shift=post_mean - prior_mean,
        prior_mode=prior_mode,
        posterior_mode=post_mode,
        mode_shifted=(post_mode != prior_mode),
        prior_std=prior_std,
        posterior_std=post_std,
        credible_level=level,
        prior_interval=prior_iv,
        posterior_interval=post_iv,
        prior_interval_width=prior_width,
        posterior_interval_width=post_width,
        interval_narrowed=(post_width < prior_width),
        effective_sample_size=ess,
    )
