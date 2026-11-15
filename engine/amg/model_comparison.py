"""Rev13 Carbon Model Trajectory Comparator, Dependence Guard, and Continuity Checker.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Specification: ``27_PLAN_DE_FRONTERA.md`` §5.3, §13 and ``28_PLAN_INTEGRADO_REV13.md`` §5.
This module is standalone under ``engine/amg/`` and is not wired into EP5 or
``engine/amg/__init__.py`` until approved by people.

PROPOSED laws enforced (Rev13 §5 / §13):
---------------------------------------
1. **Default side-by-side comparison:** ``compare_carbon_trajectories`` returns all
   available trajectories (``amg_a``, ``amg_m``, ``rothc``) side-by-side in
   ``separate_trajectories`` and sets ``default_averaged=False``. Weighted averaging
   is never performed unless weights are explicitly supplied and pass the guard.
2. **Structural dependence & homology guard:** ``validate_ensemble_weights`` refuses
   (``ValueError`` with explicit ``structural_dependency_violation`` reason) any
   weighted ensemble that gives voting weights to both ``amg_a`` and ``amg_m``
   without all three conditions:
   - declared ``amg_dependence_handled=True``,
   - matched ``(depth_cm, bulk_density_basis, boundary_condition, initialization_protocol)``
     homology (``homology_verified=True``), and
   - independent holdout validation evidence (``independent_validation_proven=True``).
3. **Monthly–annual–cycle continuity checker:** ``check_stock_continuity`` verifies
   stock continuity across adjacent steps/periods (``end_stock_t == start_stock_{t+1}``
   within tolerance) and across hierarchical monthly/annual/cycle boundaries when
   provided, detects double-counted C inputs (``duplicate_c_input``), and preserves
   missing periods as typed ``Missing`` (never ``0``).

Pure Python 3.12 stdlib + ``contracts.*``. G1 pure: no I/O, no network, no clock,
no environment variables, no mutable global state, and inputs are never mutated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from contracts.carbon_balance import CarbonBalance, FlowSeries
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import TREND_COMPUTATIONS
from contracts.results.models import Missing as ResultMissing

__all__ = [
    "DUPLICATE_C_INPUT_REASON",
    "MISSING_PERIOD_REASON",
    "STOCK_CONTINUITY_BREAK_REASON",
    "STRUCTURAL_DEPENDENCY_VIOLATION",
    "TRAJECTORY_MODEL_IDS",
    "CarbonComparisonResult",
    "CarbonInputRecord",
    "CarbonTrajectorySummary",
    "DuplicateCInput",
    "EnsembleWeightValidation",
    "HomologyProtocol",
    "MissingPeriod",
    "MissingValue",
    "StockContinuityBreak",
    "StockContinuityResult",
    "StockPeriod",
    "TrajectoryModelId",
    "WeightedEnsembleTrajectory",
    "check_stock_continuity",
    "compare_carbon_trajectories",
    "summarize_trajectory",
    "validate_ensemble_weights",
]

TrajectoryModelId = Literal["amg_a", "amg_m", "rothc"]
TRAJECTORY_MODEL_IDS: tuple[TrajectoryModelId, ...] = ("amg_a", "amg_m", "rothc")
Granularity = Literal["monthly", "annual", "cycle"]

MissingValue = InputMissing | ResultMissing
MISSING_TYPES = (InputMissing, ResultMissing)

STRUCTURAL_DEPENDENCY_VIOLATION = "structural_dependency_violation"
DUPLICATE_C_INPUT_REASON = "duplicate_c_input"
STOCK_CONTINUITY_BREAK_REASON = "stock_continuity_break"
MISSING_PERIOD_REASON = "missing_period"

_C_INPUT_FLOW_QUANTITIES: frozenset[str] = frozenset(
    {
        "amg_humified_input",
        "rothc_carbon_input",
        "carbon_input",
        "humified_input",
    }
)
_MONTHS_PER_YEAR = 12


def _is_missing(value: object) -> bool:
    return isinstance(value, MISSING_TYPES)


def _is_strict_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_strict_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name}: expected bool, got {type(value).__name__} (G5)")
    return value


def _require_finite_float(name: str, value: object) -> float:
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected finite number, got {type(value).__name__} (G5)"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name}: expected finite number, got {value!r}")
    return number


def _require_non_empty_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank")
    return value


def _require_year_month(name: str, value: object) -> YearMonth:
    if not isinstance(value, YearMonth):
        raise TypeError(f"{name}: expected YearMonth, got {type(value).__name__} (G5)")
    return value


def _require_number_or_missing(name: str, value: object) -> float | MissingValue:
    if isinstance(value, MISSING_TYPES):
        return value
    return _require_finite_float(name, value)


def _month_index(month: YearMonth) -> int:
    return month.year * _MONTHS_PER_YEAR + (month.month - 1)


def _month_from_index(index: int) -> YearMonth:
    year, zero_month = divmod(index, _MONTHS_PER_YEAR)
    return YearMonth(year=year, month=zero_month + 1)


def _intervals_overlap(
    start_a: YearMonth, end_a: YearMonth, start_b: YearMonth, end_b: YearMonth
) -> bool:
    return _month_index(start_a) <= _month_index(end_b) and _month_index(
        start_b
    ) <= _month_index(end_a)


def _format_period(start: YearMonth, end: YearMonth) -> str:
    return f"{start.year:04d}-{start.month:02d}..{end.year:04d}-{end.month:02d}"


def _freeze_mapping(mapping: Mapping[str, object]) -> MappingProxyType:
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True)
class HomologyProtocol:
    """Matched structural homology protocol across carbon models (Rev13 §5).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    depth_cm: float
    bulk_density_basis: str
    boundary_condition: str
    initialization_protocol: str

    def __post_init__(self) -> None:
        depth = _require_finite_float("depth_cm", self.depth_cm)
        if depth <= 0.0:
            raise ValueError(f"depth_cm: must be positive, got {depth}")
        object.__setattr__(self, "depth_cm", depth)
        _require_non_empty_str("bulk_density_basis", self.bulk_density_basis)
        _require_non_empty_str("boundary_condition", self.boundary_condition)
        _require_non_empty_str("initialization_protocol", self.initialization_protocol)

    def matches(
        self, other: HomologyProtocol, *, depth_tolerance: float = 1e-9
    ) -> bool:
        """Return True when all four homology dimensions match."""
        return (
            math.isclose(
                self.depth_cm, other.depth_cm, rel_tol=0.0, abs_tol=depth_tolerance
            )
            and self.bulk_density_basis == other.bulk_density_basis
            and self.boundary_condition == other.boundary_condition
            and self.initialization_protocol == other.initialization_protocol
        )

    def mismatch_fields(
        self, other: HomologyProtocol, *, depth_tolerance: float = 1e-9
    ) -> tuple[str, ...]:
        """Return the tuple of homology field names that differ from ``other``."""
        mismatches: list[str] = []
        if not math.isclose(
            self.depth_cm, other.depth_cm, rel_tol=0.0, abs_tol=depth_tolerance
        ):
            mismatches.append("depth_cm")
        if self.bulk_density_basis != other.bulk_density_basis:
            mismatches.append("bulk_density_basis")
        if self.boundary_condition != other.boundary_condition:
            mismatches.append("boundary_condition")
        if self.initialization_protocol != other.initialization_protocol:
            mismatches.append("initialization_protocol")
        return tuple(mismatches)


@dataclass(frozen=True)
class StockPeriod:
    """One simulation step or period with start/end stocks and optional C input.

    Missing values must be typed ``Missing`` (``contracts.inputs.common.Missing`` or
    ``contracts.results.models.Missing``), never ``0`` or ``None`` for stocks.
    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    start: YearMonth
    end: YearMonth
    start_stock: float | MissingValue
    end_stock: float | MissingValue
    c_input: float | MissingValue | None = None
    c_input_id: str | None = None
    granularity: Granularity | None = None

    def __post_init__(self) -> None:
        start = _require_year_month("start", self.start)
        end = _require_year_month("end", self.end)
        if _month_index(end) < _month_index(start):
            raise ValueError(
                f"StockPeriod: end ({end.year:04d}-{end.month:02d}) precedes "
                f"start ({start.year:04d}-{start.month:02d})"
            )
        start_stock = _require_number_or_missing("start_stock", self.start_stock)
        end_stock = _require_number_or_missing("end_stock", self.end_stock)
        object.__setattr__(self, "start_stock", start_stock)
        object.__setattr__(self, "end_stock", end_stock)
        if self.c_input is not None:
            c_input = _require_number_or_missing("c_input", self.c_input)
            object.__setattr__(self, "c_input", c_input)
        if self.c_input_id is not None:
            _require_non_empty_str("c_input_id", self.c_input_id)
        if self.granularity is not None and self.granularity not in (
            "monthly",
            "annual",
            "cycle",
        ):
            raise ValueError(
                f"granularity: expected 'monthly', 'annual', or 'cycle', got {self.granularity!r}"
            )


@dataclass(frozen=True)
class CarbonInputRecord:
    """Standalone carbon-input record for duplicate-input detection across scales.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    start: YearMonth
    end: YearMonth
    amount: float | MissingValue
    c_input_id: str | None = None
    scale: Granularity | None = None

    def __post_init__(self) -> None:
        start = _require_year_month("start", self.start)
        end = _require_year_month("end", self.end)
        if _month_index(end) < _month_index(start):
            raise ValueError("CarbonInputRecord: end precedes start")
        amount = _require_number_or_missing("amount", self.amount)
        object.__setattr__(self, "amount", amount)
        if self.c_input_id is not None:
            _require_non_empty_str("c_input_id", self.c_input_id)
        if self.scale is not None and self.scale not in ("monthly", "annual", "cycle"):
            raise ValueError(f"scale: invalid value {self.scale!r}")


@dataclass(frozen=True)
class CarbonTrajectorySummary:
    """Typed summary of one carbon model trajectory (AMG-A, AMG-M, or RothC).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    model_id: TrajectoryModelId
    variant: str
    unit: str
    initial_stock: float | MissingValue
    end_stock: float | MissingValue
    steps: tuple[StockPeriod, ...]
    trends: Mapping[str, float | MissingValue]
    case_id: str | None = None
    field_id: str | None = None
    rotation_id: str | None = None
    soil_depth_cm: float | MissingValue | None = None
    homology: HomologyProtocol | None = None

    def __post_init__(self) -> None:
        if self.model_id not in TRAJECTORY_MODEL_IDS:
            raise ValueError(
                f"model_id: expected one of {TRAJECTORY_MODEL_IDS}, got {self.model_id!r}"
            )
        _require_non_empty_str("variant", self.variant)
        _require_non_empty_str("unit", self.unit)
        object.__setattr__(
            self,
            "initial_stock",
            _require_number_or_missing("initial_stock", self.initial_stock),
        )
        object.__setattr__(
            self,
            "end_stock",
            _require_number_or_missing("end_stock", self.end_stock),
        )
        if isinstance(self.steps, (str, bytes)) or not isinstance(self.steps, Sequence):
            raise TypeError(
                f"steps: expected sequence of StockPeriod, got {type(self.steps).__name__} (G5)"
            )
        steps_tuple = tuple(self.steps)
        if not steps_tuple:
            raise ValueError("steps: trajectory summary must contain at least one step")
        for idx, step in enumerate(steps_tuple):
            if not isinstance(step, StockPeriod):
                raise TypeError(
                    f"steps[{idx}]: expected StockPeriod, got {type(step).__name__} (G5)"
                )
        object.__setattr__(self, "steps", steps_tuple)
        if not isinstance(self.trends, Mapping):
            raise TypeError(
                f"trends: expected mapping, got {type(self.trends).__name__} (G5)"
            )
        validated_trends: dict[str, float | MissingValue] = {}
        for comp, val in self.trends.items():
            _require_non_empty_str("trends key", comp)
            validated_trends[comp] = _require_number_or_missing(
                f"trends[{comp!r}]", val
            )
        object.__setattr__(self, "trends", _freeze_mapping(validated_trends))
        if self.soil_depth_cm is not None:
            object.__setattr__(
                self,
                "soil_depth_cm",
                _require_number_or_missing("soil_depth_cm", self.soil_depth_cm),
            )
        if self.homology is not None and not isinstance(
            self.homology, HomologyProtocol
        ):
            raise TypeError(
                f"homology: expected HomologyProtocol, got {type(self.homology).__name__} (G5)"
            )


@dataclass(frozen=True)
class StockContinuityBreak:
    """Detected discontinuity between ``end_stock_t`` and ``start_stock_{t+1}``."""

    index_from: int
    index_to: int
    period_from: tuple[YearMonth, YearMonth]
    period_to: tuple[YearMonth, YearMonth]
    end_stock: float
    next_start_stock: float
    difference: float
    scale: str = "adjacent_step"


@dataclass(frozen=True)
class DuplicateCInput:
    """Detected double-counted carbon input across periods or scales."""

    detail: str
    periods: tuple[tuple[YearMonth, YearMonth], ...]
    reason: str = DUPLICATE_C_INPUT_REASON
    c_input_id: str | None = None
    amounts: tuple[float, ...] = ()


@dataclass(frozen=True)
class MissingPeriod:
    """Missing step/period preserving typed ``Missing`` (never coerced to ``0``)."""

    start: YearMonth
    end: YearMonth
    missing: MissingValue
    field: str
    granularity: Granularity | None = None


@dataclass(frozen=True)
class StockContinuityResult:
    """Result of ``check_stock_continuity`` (Rev13 §5 / §13).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    is_continuous: bool
    all_periods_present: bool
    duplicate_c_input_detected: bool
    passed: bool
    continuity_breaks: tuple[StockContinuityBreak, ...]
    duplicate_c_inputs: tuple[DuplicateCInput, ...]
    missing_periods: tuple[MissingPeriod, ...]
    timeline_gaps: tuple[tuple[YearMonth, YearMonth], ...]
    reasons: tuple[str, ...]
    checked_transitions: int


@dataclass(frozen=True)
class EnsembleWeightValidation:
    """Validated ensemble weights with Rev13 dependence/homology/holdout evidence.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    weights: Mapping[str, float]
    normalized_weights: Mapping[str, float]
    active_models: tuple[TrajectoryModelId, ...]
    amg_dependence_handled: bool
    homology_verified: bool
    independent_validation_proven: bool
    matched_homology: HomologyProtocol | None = None
    valid: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", _freeze_mapping(self.weights))
        object.__setattr__(
            self, "normalized_weights", _freeze_mapping(self.normalized_weights)
        )


@dataclass(frozen=True)
class WeightedEnsembleTrajectory:
    """Explicit weighted ensemble summary (only produced when explicitly validated)."""

    weights: Mapping[str, float]
    unit: str
    initial_stock: float | MissingValue
    end_stock: float | MissingValue
    trends: Mapping[str, float | MissingValue]
    contributing_models: tuple[TrajectoryModelId, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", _freeze_mapping(self.weights))
        object.__setattr__(self, "trends", _freeze_mapping(self.trends))


@dataclass(frozen=True)
class CarbonComparisonResult:
    """Side-by-side comparison of carbon model trajectories (Rev13 §5 / §13).

    ``default_averaged`` is always ``False`` for default comparison, returning all
    available trajectories separately in ``separate_trajectories``.
    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    separate_trajectories: Mapping[str, CarbonTrajectorySummary]
    default_averaged: bool
    available_models: tuple[TrajectoryModelId, ...]
    missing_models: Mapping[str, ResultMissing]
    continuity_reports: Mapping[str, StockContinuityResult]
    ensemble_validation: EnsembleWeightValidation | None = None
    weighted_ensemble: WeightedEnsembleTrajectory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "separate_trajectories", _freeze_mapping(self.separate_trajectories)
        )
        object.__setattr__(self, "missing_models", _freeze_mapping(self.missing_models))
        object.__setattr__(
            self, "continuity_reports", _freeze_mapping(self.continuity_reports)
        )


# --- CarbonBalance normalization ---------------------------------------------


def _resolve_model_id(balance: CarbonBalance) -> TrajectoryModelId:
    if balance.carbon_model == "amg":
        if balance.variant == "amg_a":
            return "amg_a"
        if balance.variant == "amg_m":
            return "amg_m"
        raise ValueError(
            f"unsupported AMG variant {balance.variant!r} for trajectory comparison; "
            "expected 'amg_a' or 'amg_m'"
        )
    if balance.carbon_model == "rothc":
        return "rothc"
    raise ValueError(f"unsupported carbon_model {balance.carbon_model!r}")


def _extract_c_input_series(
    flows: Sequence[FlowSeries],
) -> list[float | MissingValue] | None:
    matching = [flow for flow in flows if flow.quantity in _C_INPUT_FLOW_QUANTITIES]
    if not matching:
        return None
    primary = matching[0]
    extracted: list[float | MissingValue] = []
    for step in primary.steps:
        if step.value is not None:
            extracted.append(float(step.value))
        else:
            assert step.missing is not None
            extracted.append(step.missing)
    return extracted


def _infer_granularity(start: YearMonth, end: YearMonth) -> Granularity | None:
    span_months = _month_index(end) - _month_index(start) + 1
    if span_months == 1:
        return "monthly"
    if span_months == _MONTHS_PER_YEAR:
        return "annual"
    return None


def _balance_to_summary(
    balance: CarbonBalance, *, homology: HomologyProtocol | None = None
) -> CarbonTrajectorySummary:
    model_id = _resolve_model_id(balance)
    total = balance.total_stock
    initial_stock: float | MissingValue
    if total.initial.value is not None:
        initial_stock = float(total.initial.value)
    else:
        assert total.initial.missing is not None
        initial_stock = total.initial.missing

    c_inputs = _extract_c_input_series(balance.flows)
    steps: list[StockPeriod] = []
    prev_stock: float | MissingValue = initial_stock
    for idx, step in enumerate(total.steps):
        end_stock: float | MissingValue
        if step.value is not None:
            end_stock = float(step.value)
        else:
            assert step.missing is not None
            end_stock = step.missing
        c_input = c_inputs[idx] if c_inputs is not None else None
        steps.append(
            StockPeriod(
                start=step.start,
                end=step.end,
                start_stock=prev_stock,
                end_stock=end_stock,
                c_input=c_input,
                granularity=_infer_granularity(step.start, step.end),
            )
        )
        prev_stock = end_stock

    trends: dict[str, float | MissingValue] = {}
    for trend in balance.soil_carbon_trend:
        if trend.value is not None:
            trends[trend.computation] = float(trend.value)
        else:
            assert trend.missing is not None
            trends[trend.computation] = trend.missing

    soil_depth_cm: float | MissingValue
    if balance.soil_depth.value is not None:
        soil_depth_cm = float(balance.soil_depth.value)
    else:
        assert balance.soil_depth.missing is not None
        soil_depth_cm = balance.soil_depth.missing

    return CarbonTrajectorySummary(
        model_id=model_id,
        variant=balance.variant,
        unit=total.unit,
        initial_stock=initial_stock,
        end_stock=steps[-1].end_stock,
        steps=tuple(steps),
        trends=trends,
        case_id=balance.case_id,
        field_id=balance.field_id,
        rotation_id=balance.rotation_id,
        soil_depth_cm=soil_depth_cm,
        homology=homology,
    )


def summarize_trajectory(
    trajectory: CarbonBalance | CarbonTrajectorySummary,
    *,
    homology: HomologyProtocol | None = None,
) -> CarbonTrajectorySummary:
    """Convert a ``CarbonBalance`` or validate a ``CarbonTrajectorySummary``."""
    if homology is not None and not isinstance(homology, HomologyProtocol):
        raise TypeError(
            f"homology: expected HomologyProtocol, got {type(homology).__name__} (G5)"
        )
    if isinstance(trajectory, CarbonBalance):
        return _balance_to_summary(trajectory, homology=homology)
    if isinstance(trajectory, CarbonTrajectorySummary):
        if homology is None or trajectory.homology == homology:
            return trajectory
        return CarbonTrajectorySummary(
            model_id=trajectory.model_id,
            variant=trajectory.variant,
            unit=trajectory.unit,
            initial_stock=trajectory.initial_stock,
            end_stock=trajectory.end_stock,
            steps=trajectory.steps,
            trends=trajectory.trends,
            case_id=trajectory.case_id,
            field_id=trajectory.field_id,
            rotation_id=trajectory.rotation_id,
            soil_depth_cm=trajectory.soil_depth_cm,
            homology=homology,
        )
    raise TypeError(
        "trajectory: expected CarbonBalance or CarbonTrajectorySummary, "
        f"got {type(trajectory).__name__} (G5)"
    )


# --- Law 2: Ensemble Weight & Dependence Guard -------------------------------


def _check_homology_protocols(
    active_models: tuple[TrajectoryModelId, ...],
    homology_protocols: Mapping[str, HomologyProtocol],
) -> tuple[HomologyProtocol | None, str | None]:
    if not isinstance(homology_protocols, Mapping):
        raise TypeError(
            "homology_protocols: expected Mapping[str, HomologyProtocol], "
            f"got {type(homology_protocols).__name__} (G5)"
        )
    for model_id, proto in homology_protocols.items():
        if model_id not in TRAJECTORY_MODEL_IDS:
            raise ValueError(
                f"homology_protocols: unknown model {model_id!r}; expected one of {TRAJECTORY_MODEL_IDS}"
            )
        if not isinstance(proto, HomologyProtocol):
            raise TypeError(
                f"homology_protocols[{model_id!r}]: expected HomologyProtocol, "
                f"got {type(proto).__name__} (G5)"
            )

    missing_protocols = [m for m in active_models if m not in homology_protocols]
    if missing_protocols:
        return (
            None,
            "homology protocol missing for active model(s): "
            + ", ".join(missing_protocols),
        )

    reference_model = active_models[0]
    reference = homology_protocols[reference_model]
    for model_id in active_models[1:]:
        candidate = homology_protocols[model_id]
        mismatches = reference.mismatch_fields(candidate)
        if mismatches:
            return (
                None,
                f"homology mismatch between {reference_model!r} and {model_id!r} on "
                + ", ".join(mismatches),
            )
    return reference, None


def validate_ensemble_weights(
    weights: Mapping[str, float | int],
    *,
    amg_dependence_handled: bool = False,
    homology_verified: bool = False,
    independent_validation_proven: bool = False,
    homology_protocols: Mapping[str, HomologyProtocol] | None = None,
    weight_sum_tolerance: float = 1e-6,
) -> EnsembleWeightValidation:
    """Validate Rev13 §5 / §13 ensemble weighting rules across AMG-A, AMG-M, and RothC.

    Refuses (``ValueError`` with explicit ``structural_dependency_violation`` reason)
    any weighted ensemble giving voting weights to both ``amg_a`` and ``amg_m``
    without ``amg_dependence_handled=True``, matched ``(depth_cm, bulk_density_basis,
    boundary_condition, initialization_protocol)`` homology (``homology_verified=True``),
    and independent holdout evidence (``independent_validation_proven=True``).
    """
    if not isinstance(weights, Mapping):
        raise TypeError(f"weights: expected Mapping, got {type(weights).__name__} (G5)")
    if not weights:
        raise ValueError("weights: must not be empty")

    dep_handled = _require_strict_bool("amg_dependence_handled", amg_dependence_handled)
    hom_verified = _require_strict_bool("homology_verified", homology_verified)
    indep_proven = _require_strict_bool(
        "independent_validation_proven", independent_validation_proven
    )
    sum_tol = _require_finite_float("weight_sum_tolerance", weight_sum_tolerance)
    if sum_tol < 0.0:
        raise ValueError("weight_sum_tolerance: must be non-negative")

    numeric_weights: dict[str, float] = {}
    for model_id, raw_weight in weights.items():
        if model_id not in TRAJECTORY_MODEL_IDS:
            raise ValueError(
                f"weights: unknown model {model_id!r}; expected one of {TRAJECTORY_MODEL_IDS}"
            )
        weight = _require_finite_float(f"weights[{model_id!r}]", raw_weight)
        if weight < 0.0:
            raise ValueError(
                f"weights[{model_id!r}]: must be non-negative, got {weight}"
            )
        numeric_weights[model_id] = weight

    active_models: tuple[TrajectoryModelId, ...] = tuple(
        model_id
        for model_id in TRAJECTORY_MODEL_IDS
        if numeric_weights.get(model_id, 0.0) > 0.0
    )
    if not active_models:
        raise ValueError("weights: at least one model weight must be positive")

    matched_homology: HomologyProtocol | None = None
    homology_error: str | None = None
    if homology_protocols is not None:
        matched_homology, homology_error = _check_homology_protocols(
            active_models, homology_protocols
        )

    both_amg_weighted = "amg_a" in active_models and "amg_m" in active_models
    if both_amg_weighted:
        violations: list[str] = []
        if not dep_handled:
            violations.append(
                "amg_dependence_handled=True is required when weighting both amg_a and amg_m"
            )
        if not hom_verified:
            violations.append(
                "homology_verified=True is required with matched "
                "(depth_cm, bulk_density_basis, boundary_condition, initialization_protocol)"
            )
        if homology_error is not None:
            violations.append(homology_error)
        if not indep_proven:
            violations.append(
                "independent_validation_proven=True is required for multi-variant AMG ensembles"
            )
        if violations:
            raise ValueError(
                f"{STRUCTURAL_DEPENDENCY_VIOLATION}: {'; '.join(violations)}"
            )
    elif homology_error is not None and len(active_models) > 1:
        raise ValueError(f"homology_mismatch: {homology_error}")

    total_weight = sum(numeric_weights.values())
    if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=sum_tol):
        raise ValueError(
            f"weights: active ensemble weights must sum to 1.0 (within {sum_tol}); "
            f"got {total_weight}"
        )

    normalized = {
        model_id: numeric_weights[model_id] / total_weight
        for model_id in numeric_weights
    }
    return EnsembleWeightValidation(
        weights=numeric_weights,
        normalized_weights=normalized,
        active_models=active_models,
        amg_dependence_handled=dep_handled,
        homology_verified=hom_verified,
        independent_validation_proven=indep_proven,
        matched_homology=matched_homology,
        valid=True,
    )


# --- Law 3: Monthly-Annual-Cycle Continuity Checker --------------------------


def _collect_missing_fields(periods: Sequence[StockPeriod]) -> list[MissingPeriod]:
    missing: list[MissingPeriod] = []
    for period in periods:
        if isinstance(period.start_stock, MISSING_TYPES):
            missing.append(
                MissingPeriod(
                    start=period.start,
                    end=period.end,
                    missing=period.start_stock,
                    field="start_stock",
                    granularity=period.granularity,
                )
            )
        if isinstance(period.end_stock, MISSING_TYPES):
            missing.append(
                MissingPeriod(
                    start=period.start,
                    end=period.end,
                    missing=period.end_stock,
                    field="end_stock",
                    granularity=period.granularity,
                )
            )
        if isinstance(period.c_input, MISSING_TYPES):
            missing.append(
                MissingPeriod(
                    start=period.start,
                    end=period.end,
                    missing=period.c_input,
                    field="c_input",
                    granularity=period.granularity,
                )
            )
    return missing


def _check_sequence_continuity(
    periods: Sequence[StockPeriod],
    *,
    tolerance: float,
    scale: str,
) -> tuple[
    list[StockContinuityBreak],
    list[tuple[YearMonth, YearMonth]],
    list[MissingPeriod],
    int,
]:
    breaks: list[StockContinuityBreak] = []
    gaps: list[tuple[YearMonth, YearMonth]] = []
    gap_missing: list[MissingPeriod] = []
    checked = 0

    for idx in range(len(periods) - 1):
        before = periods[idx]
        after = periods[idx + 1]
        before_end = _month_index(before.end)
        after_start = _month_index(after.start)
        if after_start > before_end + 1:
            gap_start = _month_from_index(before_end + 1)
            gap_end = _month_from_index(after_start - 1)
            gaps.append((gap_start, gap_end))
            gap_missing.append(
                MissingPeriod(
                    start=gap_start,
                    end=gap_end,
                    missing=ResultMissing(
                        reason="NO_COVERAGE",
                        detail=f"missing period {_format_period(gap_start, gap_end)} in {scale} series",
                    ),
                    field="timeline_gap",
                    granularity=before.granularity or after.granularity,
                )
            )
            continue

        if after_start < before_end + 1:
            # Overlapping periods are checked separately for duplicate C inputs;
            # skip adjacent stock comparison if periods overlap in calendar time.
            continue

        if _is_missing(before.end_stock) or _is_missing(after.start_stock):
            continue

        assert isinstance(before.end_stock, float)
        assert isinstance(after.start_stock, float)
        checked += 1
        diff = after.start_stock - before.end_stock
        if abs(diff) > tolerance:
            breaks.append(
                StockContinuityBreak(
                    index_from=idx,
                    index_to=idx + 1,
                    period_from=(before.start, before.end),
                    period_to=(after.start, after.end),
                    end_stock=before.end_stock,
                    next_start_stock=after.start_stock,
                    difference=diff,
                    scale=scale,
                )
            )
    return breaks, gaps, gap_missing, checked


def _detect_duplicates_within_periods(
    periods: Sequence[StockPeriod], *, label: str
) -> list[DuplicateCInput]:
    duplicates: list[DuplicateCInput] = []
    seen_ids: dict[str, tuple[int, StockPeriod]] = {}

    for idx, period in enumerate(periods):
        if period.c_input_id is not None:
            if period.c_input_id in seen_ids:
                prev_idx, prev = seen_ids[period.c_input_id]
                amounts = tuple(
                    float(val)
                    for val in (prev.c_input, period.c_input)
                    if val is not None and not _is_missing(val)
                )
                duplicates.append(
                    DuplicateCInput(
                        detail=(
                            f"{DUPLICATE_C_INPUT_REASON} in {label}: c_input_id "
                            f"{period.c_input_id!r} repeated at indices {prev_idx} and {idx}"
                        ),
                        periods=((prev.start, prev.end), (period.start, period.end)),
                        c_input_id=period.c_input_id,
                        amounts=amounts,
                    )
                )
            else:
                seen_ids[period.c_input_id] = (idx, period)

    for i in range(len(periods)):
        p_i = periods[i]
        if p_i.c_input is None or _is_missing(p_i.c_input) or float(p_i.c_input) <= 0.0:
            continue
        for j in range(i + 1, len(periods)):
            p_j = periods[j]
            if (
                p_j.c_input is None
                or _is_missing(p_j.c_input)
                or float(p_j.c_input) <= 0.0
            ):
                continue
            if _intervals_overlap(p_i.start, p_i.end, p_j.start, p_j.end):
                duplicates.append(
                    DuplicateCInput(
                        detail=(
                            f"{DUPLICATE_C_INPUT_REASON} in {label}: overlapping periods "
                            f"{_format_period(p_i.start, p_i.end)} and "
                            f"{_format_period(p_j.start, p_j.end)} both inject positive C input"
                        ),
                        periods=((p_i.start, p_i.end), (p_j.start, p_j.end)),
                        amounts=(float(p_i.c_input), float(p_j.c_input)),
                    )
                )
    return duplicates


def _detect_duplicates_in_records(
    records: Sequence[CarbonInputRecord],
) -> list[DuplicateCInput]:
    duplicates: list[DuplicateCInput] = []
    seen_ids: dict[str, CarbonInputRecord] = {}
    for rec in records:
        if rec.c_input_id is not None:
            if rec.c_input_id in seen_ids:
                prev = seen_ids[rec.c_input_id]
                amounts = tuple(
                    float(v) for v in (prev.amount, rec.amount) if not _is_missing(v)
                )
                duplicates.append(
                    DuplicateCInput(
                        detail=(
                            f"{DUPLICATE_C_INPUT_REASON}: c_input_id {rec.c_input_id!r} "
                            "appears in multiple C-input records"
                        ),
                        periods=((prev.start, prev.end), (rec.start, rec.end)),
                        c_input_id=rec.c_input_id,
                        amounts=amounts,
                    )
                )
            else:
                seen_ids[rec.c_input_id] = rec

    for i in range(len(records)):
        r_i = records[i]
        if _is_missing(r_i.amount) or float(r_i.amount) <= 0.0:
            continue
        for j in range(i + 1, len(records)):
            r_j = records[j]
            if _is_missing(r_j.amount) or float(r_j.amount) <= 0.0:
                continue
            if _intervals_overlap(r_i.start, r_i.end, r_j.start, r_j.end):
                duplicates.append(
                    DuplicateCInput(
                        detail=(
                            f"{DUPLICATE_C_INPUT_REASON}: overlapping C-input records "
                            f"{_format_period(r_i.start, r_i.end)} and "
                            f"{_format_period(r_j.start, r_j.end)} both carry positive C input"
                        ),
                        periods=((r_i.start, r_i.end), (r_j.start, r_j.end)),
                        amounts=(float(r_i.amount), float(r_j.amount)),
                    )
                )
    return duplicates


def _check_cross_scale_alignment(
    parent_periods: Sequence[StockPeriod],
    child_periods: Sequence[StockPeriod],
    *,
    tolerance: float,
    scale_label: str,
) -> tuple[list[StockContinuityBreak], list[DuplicateCInput], int]:
    breaks: list[StockContinuityBreak] = []
    duplicates: list[DuplicateCInput] = []
    checked = 0

    for p_idx, parent in enumerate(parent_periods):
        p_start = _month_index(parent.start)
        p_end = _month_index(parent.end)
        children = [
            child
            for child in child_periods
            if _month_index(child.start) >= p_start and _month_index(child.end) <= p_end
        ]
        if not children:
            continue

        # Only compare boundary stocks when child periods span the exact start and end.
        first_child = children[0]
        last_child = children[-1]
        if (
            _month_index(first_child.start) == p_start
            and not _is_missing(parent.start_stock)
            and not _is_missing(first_child.start_stock)
        ):
            assert isinstance(parent.start_stock, float)
            assert isinstance(first_child.start_stock, float)
            checked += 1
            diff = parent.start_stock - first_child.start_stock
            if abs(diff) > tolerance:
                breaks.append(
                    StockContinuityBreak(
                        index_from=p_idx,
                        index_to=0,
                        period_from=(first_child.start, first_child.end),
                        period_to=(parent.start, parent.end),
                        end_stock=first_child.start_stock,
                        next_start_stock=parent.start_stock,
                        difference=diff,
                        scale=scale_label,
                    )
                )

        if (
            _month_index(last_child.end) == p_end
            and not _is_missing(parent.end_stock)
            and not _is_missing(last_child.end_stock)
        ):
            assert isinstance(parent.end_stock, float)
            assert isinstance(last_child.end_stock, float)
            checked += 1
            diff = parent.end_stock - last_child.end_stock
            if abs(diff) > tolerance:
                breaks.append(
                    StockContinuityBreak(
                        index_from=len(children) - 1,
                        index_to=p_idx,
                        period_from=(last_child.start, last_child.end),
                        period_to=(parent.start, parent.end),
                        end_stock=last_child.end_stock,
                        next_start_stock=parent.end_stock,
                        difference=diff,
                        scale=scale_label,
                    )
                )

        # Check full child coverage for C-input conservation (no double-counting).
        children_contiguous = (
            _month_index(first_child.start) == p_start
            and _month_index(last_child.end) == p_end
            and all(
                _month_index(children[k + 1].start) == _month_index(children[k].end) + 1
                for k in range(len(children) - 1)
            )
        )
        if (
            children_contiguous
            and parent.c_input is not None
            and not _is_missing(parent.c_input)
            and all(
                c.c_input is not None and not _is_missing(c.c_input) for c in children
            )
        ):
            child_sum = sum(float(c.c_input) for c in children if c.c_input is not None)
            parent_input = float(parent.c_input)
            if abs(child_sum - parent_input) > tolerance:
                duplicates.append(
                    DuplicateCInput(
                        detail=(
                            f"{DUPLICATE_C_INPUT_REASON}: {scale_label} C input mismatch for "
                            f"{_format_period(parent.start, parent.end)} "
                            f"(parent={parent_input}, child_sum={child_sum})"
                        ),
                        periods=((parent.start, parent.end),),
                        amounts=(parent_input, child_sum),
                    )
                )
    return breaks, duplicates, checked


def _validate_period_sequence(name: str, seq: object) -> tuple[StockPeriod, ...]:
    if isinstance(seq, (str, bytes)) or not isinstance(seq, Sequence):
        raise TypeError(
            f"{name}: expected sequence of StockPeriod, got {type(seq).__name__} (G5)"
        )
    items = tuple(seq)
    if not items:
        raise ValueError(f"{name}: must not be empty")
    for idx, item in enumerate(items):
        if not isinstance(item, StockPeriod):
            raise TypeError(
                f"{name}[{idx}]: expected StockPeriod, got {type(item).__name__} (G5)"
            )
    return items


def check_stock_continuity(
    periods: Sequence[StockPeriod] | CarbonBalance | CarbonTrajectorySummary,
    *,
    annual_periods: Sequence[StockPeriod] | None = None,
    cycle_periods: Sequence[StockPeriod] | None = None,
    c_input_records: Sequence[CarbonInputRecord] | None = None,
    tolerance: float = 1e-6,
    raise_on_violation: bool = False,
) -> StockContinuityResult:
    """Verify monthly–annual–cycle stock continuity and detect double-counted C inputs.

    Checks adjacent ``end_stock_t == start_stock_{t+1}`` within ``tolerance``,
    optional cross-scale alignment across ``annual_periods`` and ``cycle_periods``,
    and double-counted C inputs (``duplicate_c_input``). Missing periods preserve
    typed ``Missing`` and are never defaulted to ``0``.
    """
    tol = _require_finite_float("tolerance", tolerance)
    if tol < 0.0:
        raise ValueError("tolerance: must be non-negative")
    do_raise = _require_strict_bool("raise_on_violation", raise_on_violation)

    if isinstance(periods, (CarbonBalance, CarbonTrajectorySummary)):
        primary = summarize_trajectory(periods).steps
    else:
        primary = _validate_period_sequence("periods", periods)

    annual = (
        _validate_period_sequence("annual_periods", annual_periods)
        if annual_periods is not None
        else None
    )
    cycle = (
        _validate_period_sequence("cycle_periods", cycle_periods)
        if cycle_periods is not None
        else None
    )
    if c_input_records is not None:
        if isinstance(c_input_records, (str, bytes)) or not isinstance(
            c_input_records, Sequence
        ):
            raise TypeError(
                "c_input_records: expected sequence of CarbonInputRecord, "
                f"got {type(c_input_records).__name__} (G5)"
            )
        for idx, rec in enumerate(c_input_records):
            if not isinstance(rec, CarbonInputRecord):
                raise TypeError(
                    f"c_input_records[{idx}]: expected CarbonInputRecord, "
                    f"got {type(rec).__name__} (G5)"
                )

    all_breaks: list[StockContinuityBreak] = []
    all_gaps: list[tuple[YearMonth, YearMonth]] = []
    all_missing: list[MissingPeriod] = []
    all_duplicates: list[DuplicateCInput] = []
    checked_transitions = 0

    all_missing.extend(_collect_missing_fields(primary))
    breaks, gaps, gap_missing, checked = _check_sequence_continuity(
        primary, tolerance=tol, scale="primary"
    )
    all_breaks.extend(breaks)
    all_gaps.extend(gaps)
    all_missing.extend(gap_missing)
    checked_transitions += checked
    all_duplicates.extend(_detect_duplicates_within_periods(primary, label="primary"))

    if annual is not None:
        all_missing.extend(_collect_missing_fields(annual))
        a_breaks, a_gaps, a_gap_missing, a_checked = _check_sequence_continuity(
            annual, tolerance=tol, scale="annual"
        )
        all_breaks.extend(a_breaks)
        all_gaps.extend(a_gaps)
        all_missing.extend(a_gap_missing)
        checked_transitions += a_checked
        all_duplicates.extend(_detect_duplicates_within_periods(annual, label="annual"))
        c_breaks, c_dups, c_checked = _check_cross_scale_alignment(
            annual, primary, tolerance=tol, scale_label="monthly_to_annual"
        )
        all_breaks.extend(c_breaks)
        all_duplicates.extend(c_dups)
        checked_transitions += c_checked

    if cycle is not None:
        all_missing.extend(_collect_missing_fields(cycle))
        y_breaks, y_gaps, y_gap_missing, y_checked = _check_sequence_continuity(
            cycle, tolerance=tol, scale="cycle"
        )
        all_breaks.extend(y_breaks)
        all_gaps.extend(y_gaps)
        all_missing.extend(y_gap_missing)
        checked_transitions += y_checked
        all_duplicates.extend(_detect_duplicates_within_periods(cycle, label="cycle"))
        reference_children = annual if annual is not None else primary
        scale_name = "annual_to_cycle" if annual is not None else "monthly_to_cycle"
        cy_breaks, cy_dups, cy_checked = _check_cross_scale_alignment(
            cycle, reference_children, tolerance=tol, scale_label=scale_name
        )
        all_breaks.extend(cy_breaks)
        all_duplicates.extend(cy_dups)
        checked_transitions += cy_checked

    if c_input_records is not None:
        all_duplicates.extend(_detect_duplicates_in_records(c_input_records))

    reasons: list[str] = []
    if all_breaks or all_gaps:
        reasons.append(STOCK_CONTINUITY_BREAK_REASON)
    if all_duplicates:
        reasons.append(DUPLICATE_C_INPUT_REASON)
    if all_missing:
        reasons.append(MISSING_PERIOD_REASON)

    is_continuous = not all_breaks and not all_gaps
    all_periods_present = not all_missing
    duplicate_detected = bool(all_duplicates)
    passed = is_continuous and not duplicate_detected

    result = StockContinuityResult(
        is_continuous=is_continuous,
        all_periods_present=all_periods_present,
        duplicate_c_input_detected=duplicate_detected,
        passed=passed,
        continuity_breaks=tuple(all_breaks),
        duplicate_c_inputs=tuple(all_duplicates),
        missing_periods=tuple(all_missing),
        timeline_gaps=tuple(all_gaps),
        reasons=tuple(reasons),
        checked_transitions=checked_transitions,
    )
    if do_raise and not result.passed:
        raise ValueError(
            f"stock continuity check failed ({', '.join(result.reasons)}): "
            f"{len(result.continuity_breaks)} break(s), "
            f"{len(result.timeline_gaps)} gap(s), "
            f"{len(result.duplicate_c_inputs)} duplicate C input(s)"
        )
    return result


# --- Law 1: Trajectory Comparator -------------------------------------------


def _weighted_scalar_or_missing(
    values: Sequence[tuple[TrajectoryModelId, float, float | MissingValue]],
) -> float | MissingValue:
    for model_id, _, val in values:
        if isinstance(val, MISSING_TYPES):
            return ResultMissing(
                reason=val.reason,
                detail=f"{model_id}: {val.detail}"
                if val.detail
                else f"{model_id} is missing",
            )
    return sum(weight * float(val) for _, weight, val in values)


def _compute_weighted_ensemble(
    separate: Mapping[str, CarbonTrajectorySummary],
    validation: EnsembleWeightValidation,
) -> WeightedEnsembleTrajectory:
    active = validation.active_models
    missing_active = [m for m in active if m not in separate]
    if missing_active:
        raise ValueError(
            f"weights reference model(s) not present in trajectories: {', '.join(missing_active)}"
        )

    units = {separate[m].unit for m in active}
    if len(units) > 1:
        raise ValueError(
            f"cannot combine trajectories with differing units: {sorted(units)}"
        )
    unit = next(iter(units))

    norm = validation.normalized_weights
    initial_stock = _weighted_scalar_or_missing(
        [(m, norm[m], separate[m].initial_stock) for m in active]
    )
    end_stock = _weighted_scalar_or_missing(
        [(m, norm[m], separate[m].end_stock) for m in active]
    )

    trends: dict[str, float | MissingValue] = {}
    for comp in TREND_COMPUTATIONS:
        entries: list[tuple[TrajectoryModelId, float, float | MissingValue]] = []
        missing_from: TrajectoryModelId | None = None
        for m in active:
            if comp not in separate[m].trends:
                missing_from = m
                break
            entries.append((m, norm[m], separate[m].trends[comp]))
        if missing_from is not None:
            trends[comp] = ResultMissing(
                reason="NOT_AVAILABLE",
                detail=f"trend {comp!r} is absent from {missing_from!r}",
            )
        else:
            trends[comp] = _weighted_scalar_or_missing(entries)

    return WeightedEnsembleTrajectory(
        weights=norm,
        unit=unit,
        initial_stock=initial_stock,
        end_stock=end_stock,
        trends=trends,
        contributing_models=active,
    )


def compare_carbon_trajectories(
    trajectories: (
        Sequence[CarbonBalance | CarbonTrajectorySummary]
        | Mapping[str, CarbonBalance | CarbonTrajectorySummary]
    ),
    *,
    weights: Mapping[str, float | int] | None = None,
    amg_dependence_handled: bool = False,
    homology_verified: bool = False,
    independent_validation_proven: bool = False,
    homology_protocols: Mapping[str, HomologyProtocol] | None = None,
    continuity_tolerance: float = 1e-6,
    weight_sum_tolerance: float = 1e-6,
) -> CarbonComparisonResult:
    """Compare AMG-A, AMG-M, and RothC trajectories under Rev13 §5 / §13 laws.

    Default comparison (``weights=None``) returns all available trajectories
    side-by-side in ``separate_trajectories`` with ``default_averaged=False`` and
    ``weighted_ensemble=None``.

    When ``weights`` is supplied, ``validate_ensemble_weights`` is strictly enforced
    first; any ensemble weighting both ``amg_a`` and ``amg_m`` without
    ``amg_dependence_handled=True``, matched homology (``homology_verified=True``),
    and ``independent_validation_proven=True`` raises ``ValueError`` with
    ``structural_dependency_violation``.
    """
    separate: dict[str, CarbonTrajectorySummary] = {}
    if isinstance(trajectories, Mapping):
        if not trajectories:
            raise ValueError("trajectories: must not be empty")
        for key, item in trajectories.items():
            if key not in TRAJECTORY_MODEL_IDS:
                raise ValueError(
                    f"trajectories: unknown model key {key!r}; "
                    f"expected one of {TRAJECTORY_MODEL_IDS}"
                )
            proto = (
                homology_protocols.get(key) if homology_protocols is not None else None
            )
            summary = summarize_trajectory(item, homology=proto)
            if summary.model_id != key:
                raise ValueError(
                    f"trajectories[{key!r}]: trajectory identifies as {summary.model_id!r}, "
                    f"not {key!r}"
                )
            separate[key] = summary
    elif isinstance(trajectories, Sequence) and not isinstance(
        trajectories, (str, bytes)
    ):
        if not trajectories:
            raise ValueError("trajectories: must not be empty")
        for item in trajectories:
            summary = summarize_trajectory(item)
            if (
                homology_protocols is not None
                and summary.model_id in homology_protocols
            ):
                summary = summarize_trajectory(
                    summary, homology=homology_protocols[summary.model_id]
                )
            if summary.model_id in separate:
                raise ValueError(
                    f"trajectories: duplicate trajectory for model {summary.model_id!r}"
                )
            separate[summary.model_id] = summary
    else:
        raise TypeError(
            "trajectories: expected Sequence or Mapping of CarbonBalance / "
            f"CarbonTrajectorySummary, got {type(trajectories).__name__} (G5)"
        )

    ordered_separate = {
        model_id: separate[model_id]
        for model_id in TRAJECTORY_MODEL_IDS
        if model_id in separate
    }
    available_models: tuple[TrajectoryModelId, ...] = tuple(ordered_separate)  # type: ignore[assignment]
    missing_models: dict[str, ResultMissing] = {
        model_id: ResultMissing(
            reason="NOT_AVAILABLE",
            detail=f"trajectory for {model_id!r} was not provided",
        )
        for model_id in TRAJECTORY_MODEL_IDS
        if model_id not in ordered_separate
    }

    effective_protocols: dict[str, HomologyProtocol] | None = None
    if homology_protocols is not None:
        effective_protocols = dict(homology_protocols)
    else:
        attached = {
            model_id: summary.homology
            for model_id, summary in ordered_separate.items()
            if summary.homology is not None
        }
        if attached:
            effective_protocols = attached

    continuity_reports = {
        model_id: check_stock_continuity(summary, tolerance=continuity_tolerance)
        for model_id, summary in ordered_separate.items()
    }

    ensemble_validation: EnsembleWeightValidation | None = None
    weighted_ensemble: WeightedEnsembleTrajectory | None = None
    if weights is not None:
        ensemble_validation = validate_ensemble_weights(
            weights,
            amg_dependence_handled=amg_dependence_handled,
            homology_verified=homology_verified,
            independent_validation_proven=independent_validation_proven,
            homology_protocols=effective_protocols,
            weight_sum_tolerance=weight_sum_tolerance,
        )
        weighted_ensemble = _compute_weighted_ensemble(
            ordered_separate, ensemble_validation
        )

    return CarbonComparisonResult(
        separate_trajectories=ordered_separate,
        default_averaged=False,
        available_models=available_models,
        missing_models=missing_models,
        continuity_reports=continuity_reports,
        ensemble_validation=ensemble_validation,
        weighted_ensemble=weighted_ensemble,
    )
