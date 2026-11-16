"""Dynamic topsoil bulk density, surface structural crusting, and compaction feedback.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13, Line ``L16``).
Maturity: ``FRONTIER`` | Data Availability: ``LOCAL_MEASUREMENT_REQUIRED``.
This module is standalone and is strictly NOT wired into
``engine/water/__init__.py``, ``engine/water/exposure.py``,
``engine/water/runoff/curve_number.py``, or normative EP3; nothing here takes
effect until reviewed and approved.

Implements Frontier Line ``L16``:
1. ``step_bulk_density_state``: updates topsoil dry ``bulk_density`` (``g cm-3``)
   within caller-supplied physical bounds ``(min_bulk_density, max_bulk_density)``
   via additive compaction increments (axle/traffic load events), additive
   tillage loosening, and caller-parameterized biological relaxation toward
   ``baseline_bulk_density``, deriving total porosity
   ``1 - bulk_density / particle_density``.
2. ``compute_surface_crusting_factor``: attenuates effective saturated
   conductivity / infiltrability monotonically with cumulative rainfall kinetic
   energy since the last tillage event, parameterized purely by caller
   arguments.
3. ``evaluate_soil_structure_feedback``: evaluates a coupled time series of
   ``bulk_density``, ``porosity``, ``crusting_factor``, effective
   ``infiltrability_ratio``, and exploratory ``cn_delta_estimate`` diagnostics
   (explicitly marked ``"EXPLORATORY"`` / ``"PROPOSED"`` and
   ``normative_ep3_wired=False``), or returns typed
   ``Missing(reason="MISSING_INPUT" | "NOT_AVAILABLE", detail=...)`` when
   time-series pedon measurements or parameters are absent.

Zero hardcoded empirical constants or defaults: every physical bound,
particle density, relaxation rate, crusting decay sensitivity, infiltrability
exponent, and CN sensitivity is supplied by the caller.

Pure function (G1): pure Python 3.12 stdlib plus
``contracts.results.models.Missing`` only; no numpy, no file I/O, no network
calls, no clock, no global mutable state, and arguments are never modified.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.results.models import Missing

__all__ = [
    "DATA_AVAILABILITY_TAG",
    "DIAGNOSTIC_TIER",
    "FRONTIER_LINE",
    "MATURITY_TAG",
    "NORMATIVE_EP3_WIRED",
    "STATUS_TAG",
    "UNIT_BULK_DENSITY",
    "UNIT_DIMENSIONLESS",
    "UNIT_POROSITY",
    "BulkDensityState",
    "SoilStructureFeedbackSeries",
    "SoilStructureFeedbackSpec",
    "SoilStructureStepInput",
    "SoilStructureStepResult",
    "compute_surface_crusting_factor",
    "evaluate_soil_structure_feedback",
    "step_bulk_density_state",
]

FRONTIER_LINE = "L16"
STATUS_TAG = "PROPOSED"
MATURITY_TAG = "FRONTIER"
DATA_AVAILABILITY_TAG = "LOCAL_MEASUREMENT_REQUIRED"
DIAGNOSTIC_TIER = "EXPLORATORY"
NORMATIVE_EP3_WIRED = False

UNIT_BULK_DENSITY = "g cm-3"
UNIT_POROSITY = "m3 m-3"
UNIT_DIMENSIONLESS = "dimensionless"

_ZERO = 0.0
_ONE = 1.0


@dataclass(frozen=True)
class BulkDensityState:
    """Result of one dynamic topsoil bulk density state step."""

    bulk_density: float | Missing
    porosity: float | Missing
    delta_bulk_density: float | Missing
    clamped_low: bool
    clamped_high: bool
    unit_bulk_density: str
    unit_porosity: str
    status: str
    frontier_line: str
    data_availability: str


@dataclass(frozen=True)
class SoilStructureFeedbackSpec:
    """Caller-supplied specification for coupled soil structure feedback.

    Zero hardcoded scientific constants or defaults: every physical and
    empirical parameter must be explicitly supplied by the caller.
    """

    model_id: str
    particle_density: float | Missing
    min_bulk_density: float | Missing
    max_bulk_density: float | Missing
    baseline_bulk_density: float | Missing
    biological_relaxation_rate: float | Missing
    crust_decay_rate: float | Missing
    min_crust_factor: float | Missing
    porosity_infiltrability_exponent: float | Missing
    cn_sensitivity: float | Missing


@dataclass(frozen=True)
class SoilStructureStepInput:
    """One time-series step of forcing and optional pedon measurements."""

    step_id: str
    compaction_increment: float | Missing | Sequence[float | Missing]
    tillage_event: bool
    tillage_loosening: float | Missing
    rainfall_kinetic_energy: float | Missing
    measured_bulk_density: float | Missing | None = None


@dataclass(frozen=True)
class SoilStructureStepResult:
    """Per-step coupled soil structure and exploratory runoff diagnostic."""

    step_id: str
    bulk_density: float | Missing
    porosity: float | Missing
    cumulative_kinetic_energy: float | Missing
    crusting_factor: float | Missing
    infiltrability_ratio: float | Missing
    cn_delta_estimate: float | Missing
    clamped_low: bool
    clamped_high: bool
    cn_delta_diagnostic_tier: str
    status: str
    frontier_line: str
    maturity: str
    data_availability: str
    normative_ep3_wired: bool


@dataclass(frozen=True)
class SoilStructureFeedbackSeries:
    """Coupled soil structure feedback time-series evaluation output."""

    model_id: str
    steps: tuple[SoilStructureStepResult, ...]
    final_bulk_density: float | Missing
    final_porosity: float | Missing
    final_crusting_factor: float | Missing
    final_infiltrability_ratio: float | Missing
    final_cn_delta_estimate: float | Missing
    series_missing: Missing | None
    cn_delta_diagnostic_tier: str
    status: str
    frontier_line: str
    maturity: str
    data_availability: str
    normative_ep3_wired: bool


# ---------------------------------------------------------------------------
# Internal validation and Missing propagation helpers (G4 / G5)


def _is_number(value: object) -> bool:
    """True for ``int`` or ``float``, excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_sequence_not_text(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _require_non_blank_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank (G5)")
    return value


def _require_number_or_missing(name: str, value: object) -> None:
    if not isinstance(value, Missing) and not _is_number(value):
        raise TypeError(
            f"{name}: expected float, int, or Missing, got {type(value).__name__} (G5)"
        )


def _format_missing_item(name: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"{name} ({missing.reason})"
    return f"{name} ({missing.reason}: {missing.detail})"


def _aggregate_missing(items: Sequence[tuple[str, Missing]], context: str) -> Missing:
    """Combine one or more ``Missing`` inputs, preserving MISSING_INPUT / NOT_AVAILABLE."""
    reasons = {m.reason for _, m in items}
    target_reason = "NOT_AVAILABLE" if reasons == {"NOT_AVAILABLE"} else "MISSING_INPUT"
    details = ", ".join(_format_missing_item(name, m) for name, m in items)
    return Missing(
        reason=target_reason,
        detail=f"{context}: {details}",
    )


def _validate_compaction_input(name: str, value: object) -> float | Missing:
    """Validate scalar or sequence of additive compaction increments."""
    if isinstance(value, Missing) or _is_number(value):
        _require_number_or_missing(name, value)
        if isinstance(value, Missing):
            return value
        assert isinstance(value, (int, float))
        if not _is_finite(value):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{name} is not a finite number",
            )
        val = float(value)
        if val < _ZERO:
            return Missing(
                reason="CONTROL_FAILED",
                detail=f"{name} must be >= 0, got {val}",
            )
        return val

    if not _is_sequence_not_text(value):
        raise TypeError(
            f"{name}: expected float, int, Missing, or Sequence thereof, "
            f"got {type(value).__name__} (G5)"
        )
    assert isinstance(value, Sequence)
    missing_items: list[tuple[str, Missing]] = []
    numeric_events: list[float] = []
    for idx, item in enumerate(value):
        item_name = f"{name}[{idx}]"
        _require_number_or_missing(item_name, item)
        if isinstance(item, Missing):
            missing_items.append((item_name, item))
        else:
            assert isinstance(item, (int, float))
            if not _is_finite(item):
                return Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"{item_name} is not a finite number",
                )
            numeric_events.append(float(item))

    if missing_items:
        return _aggregate_missing(missing_items, f"{name} missing event increment(s)")
    for idx, event_val in enumerate(numeric_events):
        if event_val < _ZERO:
            return Missing(
                reason="CONTROL_FAILED",
                detail=f"{name}[{idx}] must be >= 0, got {event_val}",
            )
    total = _ZERO
    for event_val in numeric_events:
        total += event_val
    if not _is_finite(total):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"sum of {name} is not finite",
        )
    return total


def _failed_bulk_density_state(failure: Missing) -> BulkDensityState:
    return BulkDensityState(
        bulk_density=failure,
        porosity=failure,
        delta_bulk_density=failure,
        clamped_low=False,
        clamped_high=False,
        unit_bulk_density=UNIT_BULK_DENSITY,
        unit_porosity=UNIT_POROSITY,
        status=STATUS_TAG,
        frontier_line=FRONTIER_LINE,
        data_availability=DATA_AVAILABILITY_TAG,
    )


def _validate_spec(spec: object) -> None:
    if not isinstance(spec, SoilStructureFeedbackSpec):
        raise TypeError(
            f"spec: expected SoilStructureFeedbackSpec, got {type(spec).__name__} (G5)"
        )
    _require_non_blank_str("spec.model_id", spec.model_id)
    for field_name in (
        "particle_density",
        "min_bulk_density",
        "max_bulk_density",
        "baseline_bulk_density",
        "biological_relaxation_rate",
        "crust_decay_rate",
        "min_crust_factor",
        "porosity_infiltrability_exponent",
        "cn_sensitivity",
    ):
        _require_number_or_missing(f"spec.{field_name}", getattr(spec, field_name))


def _validate_step_input(idx: int, step: object) -> None:
    if not isinstance(step, SoilStructureStepInput):
        raise TypeError(
            f"steps[{idx}]: expected SoilStructureStepInput, "
            f"got {type(step).__name__} (G5)"
        )
    _require_non_blank_str(f"steps[{idx}].step_id", step.step_id)
    if not isinstance(step.tillage_event, bool):
        raise TypeError(
            f"steps[{idx}].tillage_event: expected bool, "
            f"got {type(step.tillage_event).__name__} (G5)"
        )
    _require_number_or_missing(
        f"steps[{idx}].tillage_loosening", step.tillage_loosening
    )
    _require_number_or_missing(
        f"steps[{idx}].rainfall_kinetic_energy", step.rainfall_kinetic_energy
    )
    if step.measured_bulk_density is not None:
        _require_number_or_missing(
            f"steps[{idx}].measured_bulk_density", step.measured_bulk_density
        )
    # Validate compaction_increment structure eagerly (G5).
    if not isinstance(step.compaction_increment, Missing) and not _is_number(
        step.compaction_increment
    ):
        if not _is_sequence_not_text(step.compaction_increment):
            raise TypeError(
                f"steps[{idx}].compaction_increment: expected float, int, Missing, "
                f"or Sequence thereof, got {type(step.compaction_increment).__name__} (G5)"
            )
        assert isinstance(step.compaction_increment, Sequence)
        for ev_idx, ev in enumerate(step.compaction_increment):
            _require_number_or_missing(
                f"steps[{idx}].compaction_increment[{ev_idx}]", ev
            )


def _make_step_result(
    *,
    step_id: str,
    bulk_density: float | Missing,
    porosity: float | Missing,
    cumulative_kinetic_energy: float | Missing,
    crusting_factor: float | Missing,
    infiltrability_ratio: float | Missing,
    cn_delta_estimate: float | Missing,
    clamped_low: bool,
    clamped_high: bool,
) -> SoilStructureStepResult:
    return SoilStructureStepResult(
        step_id=step_id,
        bulk_density=bulk_density,
        porosity=porosity,
        cumulative_kinetic_energy=cumulative_kinetic_energy,
        crusting_factor=crusting_factor,
        infiltrability_ratio=infiltrability_ratio,
        cn_delta_estimate=cn_delta_estimate,
        clamped_low=clamped_low,
        clamped_high=clamped_high,
        cn_delta_diagnostic_tier=DIAGNOSTIC_TIER,
        status=STATUS_TAG,
        frontier_line=FRONTIER_LINE,
        maturity=MATURITY_TAG,
        data_availability=DATA_AVAILABILITY_TAG,
        normative_ep3_wired=NORMATIVE_EP3_WIRED,
    )


def _missing_series_result(
    *,
    model_id: str,
    steps: tuple[SoilStructureStepResult, ...],
    failure: Missing,
) -> SoilStructureFeedbackSeries:
    return SoilStructureFeedbackSeries(
        model_id=model_id,
        steps=steps,
        final_bulk_density=failure,
        final_porosity=failure,
        final_crusting_factor=failure,
        final_infiltrability_ratio=failure,
        final_cn_delta_estimate=failure,
        series_missing=failure,
        cn_delta_diagnostic_tier=DIAGNOSTIC_TIER,
        status=STATUS_TAG,
        frontier_line=FRONTIER_LINE,
        maturity=MATURITY_TAG,
        data_availability=DATA_AVAILABILITY_TAG,
        normative_ep3_wired=NORMATIVE_EP3_WIRED,
    )


# ---------------------------------------------------------------------------
# Public Frontier L16 API


def step_bulk_density_state(
    current_bulk_density: float | Missing,
    *,
    compaction_increment: float | Missing | Sequence[float | Missing],
    tillage_loosening: float | Missing,
    biological_relaxation_rate: float | Missing,
    baseline_bulk_density: float | Missing,
    min_bulk_density: float | Missing,
    max_bulk_density: float | Missing,
    particle_density: float | Missing,
) -> BulkDensityState:
    """Advance topsoil dry bulk density by one step and derive total porosity.

    Updates ``current_bulk_density`` (``g cm-3``) via additive compaction
    increments (axle/traffic load events), additive ``tillage_loosening``, and
    biological relaxation toward ``baseline_bulk_density`` at rate
    ``biological_relaxation_rate``, clamping to
    ``[min_bulk_density, max_bulk_density]`` and computing
    ``porosity = 1 - bulk_density / particle_density``.

    Zero hardcoded empirical constants or defaults. Raises ``TypeError`` on
    caller contract defects (G5) and returns typed ``Missing`` on absent inputs,
    non-finite numbers, or failed physical controls (G4).
    """
    scalar_args: tuple[tuple[str, object], ...] = (
        ("current_bulk_density", current_bulk_density),
        ("tillage_loosening", tillage_loosening),
        ("biological_relaxation_rate", biological_relaxation_rate),
        ("baseline_bulk_density", baseline_bulk_density),
        ("min_bulk_density", min_bulk_density),
        ("max_bulk_density", max_bulk_density),
        ("particle_density", particle_density),
    )
    for name, val in scalar_args:
        _require_number_or_missing(name, val)

    compaction_checked = _validate_compaction_input(
        "compaction_increment", compaction_increment
    )

    missing_items: list[tuple[str, Missing]] = []
    for name, val in scalar_args:
        if isinstance(val, Missing):
            missing_items.append((name, val))
    if isinstance(compaction_checked, Missing):
        if compaction_checked.reason in ("NOT_COMPUTABLE", "CONTROL_FAILED"):
            return _failed_bulk_density_state(compaction_checked)
        missing_items.append(("compaction_increment", compaction_checked))

    if missing_items:
        return _failed_bulk_density_state(
            _aggregate_missing(
                missing_items, "step_bulk_density_state missing input(s)"
            )
        )

    assert not isinstance(compaction_checked, Missing)
    numeric: dict[str, float] = {}
    for name, val in scalar_args:
        assert not isinstance(val, Missing) and _is_number(val)
        if not _is_finite(val):
            return _failed_bulk_density_state(
                Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"{name} is not a finite number",
                )
            )
        numeric[name] = float(val)

    bd_curr = numeric["current_bulk_density"]
    loosening = numeric["tillage_loosening"]
    bio_rate = numeric["biological_relaxation_rate"]
    bd_base = numeric["baseline_bulk_density"]
    bd_min = numeric["min_bulk_density"]
    bd_max = numeric["max_bulk_density"]
    rho_s = numeric["particle_density"]

    # Physical domain sanity controls (CONTROL_FAILED).
    if rho_s <= _ZERO:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=f"particle_density must be > 0, got {rho_s}",
            )
        )
    if bd_min <= _ZERO or bd_min >= bd_max or bd_max >= rho_s:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    "physical bounds must satisfy 0 < min_bulk_density < "
                    f"max_bulk_density < particle_density: min={bd_min}, "
                    f"max={bd_max}, particle_density={rho_s}"
                ),
            )
        )
    if bd_base < bd_min or bd_base > bd_max:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"baseline_bulk_density={bd_base} must lie in [{bd_min}, {bd_max}]"
                ),
            )
        )
    if bd_curr < bd_min or bd_curr > bd_max:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"current_bulk_density={bd_curr} must lie in [{bd_min}, {bd_max}]"
                ),
            )
        )
    if loosening < _ZERO:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=f"tillage_loosening must be >= 0, got {loosening}",
            )
        )
    if bio_rate < _ZERO or bio_rate > _ONE:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=f"biological_relaxation_rate must lie in [0, 1], got {bio_rate}",
            )
        )

    bd_after_events = bd_curr + compaction_checked - loosening
    bd_relaxed = bd_after_events + bio_rate * (bd_base - bd_after_events)
    if not _is_finite(bd_relaxed):
        return _failed_bulk_density_state(
            Missing(
                reason="NOT_COMPUTABLE",
                detail="updated bulk_density overflowed finite range",
            )
        )

    clamped_low = bd_relaxed < bd_min
    clamped_high = bd_relaxed > bd_max
    bd_next = min(bd_max, max(bd_min, bd_relaxed))
    porosity = _ONE - (bd_next / rho_s)
    delta_bd = bd_next - bd_curr

    if not _is_finite(porosity) or not _is_finite(delta_bd):
        return _failed_bulk_density_state(
            Missing(
                reason="NOT_COMPUTABLE",
                detail="derived porosity or delta_bulk_density is not finite",
            )
        )
    if porosity <= _ZERO or porosity >= _ONE:
        return _failed_bulk_density_state(
            Missing(
                reason="CONTROL_FAILED",
                detail=f"derived porosity={porosity} outside (0, 1)",
            )
        )

    return BulkDensityState(
        bulk_density=bd_next,
        porosity=porosity,
        delta_bulk_density=delta_bd,
        clamped_low=clamped_low,
        clamped_high=clamped_high,
        unit_bulk_density=UNIT_BULK_DENSITY,
        unit_porosity=UNIT_POROSITY,
        status=STATUS_TAG,
        frontier_line=FRONTIER_LINE,
        data_availability=DATA_AVAILABILITY_TAG,
    )


def compute_surface_crusting_factor(
    cumulative_kinetic_energy: float | Missing,
    *,
    crust_decay_rate: float | Missing,
    min_crust_factor: float | Missing,
) -> float | Missing:
    """Compute dimensionless surface structural crusting multiplier in ``[min_crust_factor, 1]``.

    Attenuates infiltrability monotonically with ``cumulative_kinetic_energy``
    since the last tillage event via:
    ``min_crust_factor + (1 - min_crust_factor) * exp(-crust_decay_rate * cumulative_kinetic_energy)``.

    Zero hardcoded empirical constants or defaults.
    """
    args: tuple[tuple[str, object], ...] = (
        ("cumulative_kinetic_energy", cumulative_kinetic_energy),
        ("crust_decay_rate", crust_decay_rate),
        ("min_crust_factor", min_crust_factor),
    )
    for name, val in args:
        _require_number_or_missing(name, val)

    missing_items: list[tuple[str, Missing]] = [
        (name, val) for name, val in args if isinstance(val, Missing)
    ]
    if missing_items:
        return _aggregate_missing(
            missing_items, "compute_surface_crusting_factor missing input(s)"
        )

    assert not isinstance(cumulative_kinetic_energy, Missing)
    assert not isinstance(crust_decay_rate, Missing)
    assert not isinstance(min_crust_factor, Missing)

    for name, val in args:
        assert _is_number(val)
        if not _is_finite(val):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{name} is not a finite number",
            )

    ke = float(cumulative_kinetic_energy)
    decay = float(crust_decay_rate)
    min_factor = float(min_crust_factor)

    if ke < _ZERO:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"cumulative_kinetic_energy must be >= 0, got {ke}",
        )
    if decay < _ZERO:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"crust_decay_rate must be >= 0, got {decay}",
        )
    if min_factor < _ZERO or min_factor > _ONE:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"min_crust_factor must lie in [0, 1], got {min_factor}",
        )

    exponent = -(decay * ke)
    if not _is_finite(exponent):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="crusting decay exponent is not finite",
        )
    factor = min_factor + (_ONE - min_factor) * math.exp(exponent)
    if not _is_finite(factor):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="crusting factor is not finite",
        )
    return min(_ONE, max(min_factor, factor))


def evaluate_soil_structure_feedback(
    steps: Sequence[SoilStructureStepInput],
    spec: SoilStructureFeedbackSpec,
    *,
    initial_bulk_density: float | Missing,
    initial_cumulative_kinetic_energy: float | Missing,
) -> SoilStructureFeedbackSeries:
    """Evaluate coupled bulk density, crusting, infiltrability, and exploratory CN delta.

    Produces a time series of ``SoilStructureStepResult`` records. Exploratory
    ``cn_delta_estimate`` diagnostics are marked ``"EXPLORATORY"`` /
    ``"PROPOSED"`` and ``normative_ep3_wired=False`` so they never feed into
    normative EP3.

    Returns typed ``Missing(reason="MISSING_INPUT" | "NOT_AVAILABLE", detail=...)``
    when time-series pedon measurements or parameters are absent, and
    ``CONTROL_FAILED`` / ``NOT_COMPUTABLE`` on invalid controls or non-finite
    arithmetic.
    """
    if not _is_sequence_not_text(steps):
        raise TypeError(
            f"steps: expected Sequence of SoilStructureStepInput, "
            f"got {type(steps).__name__} (G5)"
        )
    _validate_spec(spec)
    _require_number_or_missing("initial_bulk_density", initial_bulk_density)
    _require_number_or_missing(
        "initial_cumulative_kinetic_energy", initial_cumulative_kinetic_energy
    )
    for idx, step in enumerate(steps):
        _validate_step_input(idx, step)

    # Check required spec parameters and initial state for Missing values.
    missing_items: list[tuple[str, Missing]] = []
    for field_name in (
        "particle_density",
        "min_bulk_density",
        "max_bulk_density",
        "baseline_bulk_density",
        "biological_relaxation_rate",
        "crust_decay_rate",
        "min_crust_factor",
        "porosity_infiltrability_exponent",
        "cn_sensitivity",
    ):
        val = getattr(spec, field_name)
        if isinstance(val, Missing):
            missing_items.append((f"spec.{field_name}", val))

    if isinstance(initial_bulk_density, Missing):
        missing_items.append(("initial_bulk_density", initial_bulk_density))
    if isinstance(initial_cumulative_kinetic_energy, Missing):
        missing_items.append(
            ("initial_cumulative_kinetic_energy", initial_cumulative_kinetic_energy)
        )

    if missing_items:
        failure = _aggregate_missing(
            missing_items,
            "evaluate_soil_structure_feedback missing parameter(s) or initial measurement(s)",
        )
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=failure,
        )

    if not steps:
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="MISSING_INPUT",
                detail="no time-series steps provided to evaluate_soil_structure_feedback",
            ),
        )

    # Check finiteness and domain bounds of spec and initial conditions.
    spec_fields = (
        "particle_density",
        "min_bulk_density",
        "max_bulk_density",
        "baseline_bulk_density",
        "biological_relaxation_rate",
        "crust_decay_rate",
        "min_crust_factor",
        "porosity_infiltrability_exponent",
        "cn_sensitivity",
    )
    spec_nums: dict[str, float] = {}
    for field_name in spec_fields:
        val = getattr(spec, field_name)
        assert not isinstance(val, Missing) and _is_number(val)
        if not _is_finite(val):
            return _missing_series_result(
                model_id=spec.model_id,
                steps=(),
                failure=Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"spec.{field_name} is not a finite number",
                ),
            )
        spec_nums[field_name] = float(val)

    assert not isinstance(initial_bulk_density, Missing)
    assert not isinstance(initial_cumulative_kinetic_energy, Missing)
    if not _is_finite(initial_bulk_density) or not _is_finite(
        initial_cumulative_kinetic_energy
    ):
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail="initial_bulk_density or initial_cumulative_kinetic_energy is not finite",
            ),
        )

    rho_s = spec_nums["particle_density"]
    bd_min = spec_nums["min_bulk_density"]
    bd_max = spec_nums["max_bulk_density"]
    bd_base = spec_nums["baseline_bulk_density"]
    bio_rate = spec_nums["biological_relaxation_rate"]
    crust_decay = spec_nums["crust_decay_rate"]
    min_crust = spec_nums["min_crust_factor"]
    porosity_exp = spec_nums["porosity_infiltrability_exponent"]
    cn_sens = spec_nums["cn_sensitivity"]

    bd_curr = float(initial_bulk_density)
    cum_ke_curr = float(initial_cumulative_kinetic_energy)

    # Validate spec and initial domain constraints.
    init_bd_check = step_bulk_density_state(
        bd_curr,
        compaction_increment=_ZERO,
        tillage_loosening=_ZERO,
        biological_relaxation_rate=_ZERO,
        baseline_bulk_density=bd_base,
        min_bulk_density=bd_min,
        max_bulk_density=bd_max,
        particle_density=rho_s,
    )
    if isinstance(init_bd_check.bulk_density, Missing):
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=init_bd_check.bulk_density,
        )
    if bio_rate < _ZERO or bio_rate > _ONE:
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"spec.biological_relaxation_rate must lie in [0, 1], got {bio_rate}",
            ),
        )
    init_crust_check = compute_surface_crusting_factor(
        cum_ke_curr,
        crust_decay_rate=crust_decay,
        min_crust_factor=min_crust,
    )
    if isinstance(init_crust_check, Missing):
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=init_crust_check,
        )
    if porosity_exp < _ZERO:
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"spec.porosity_infiltrability_exponent must be >= 0, "
                    f"got {porosity_exp}"
                ),
            ),
        )
    if cn_sens < _ZERO:
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"spec.cn_sensitivity must be >= 0, got {cn_sens}",
            ),
        )

    baseline_porosity = _ONE - (bd_base / rho_s)
    if not _is_finite(baseline_porosity) or baseline_porosity <= _ZERO:
        return _missing_series_result(
            model_id=spec.model_id,
            steps=(),
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"baseline_porosity must be > 0, got {baseline_porosity}",
            ),
        )

    results: list[SoilStructureStepResult] = []
    state_failure: Missing | None = None
    first_series_failure: Missing | None = None
    ke_failure: Missing | None = None

    for idx, step in enumerate(steps):
        step_prefix = f"steps[{idx}] ({step.step_id})"

        if state_failure is not None:
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=state_failure,
                    porosity=state_failure,
                    cumulative_kinetic_energy=state_failure,
                    crusting_factor=state_failure,
                    infiltrability_ratio=state_failure,
                    cn_delta_estimate=state_failure,
                    clamped_low=False,
                    clamped_high=False,
                )
            )
            continue

        # Check step-level Missing inputs (pedon measurements / forcing).
        step_missing: list[tuple[str, Missing]] = []
        comp_checked = _validate_compaction_input(
            f"{step_prefix}.compaction_increment", step.compaction_increment
        )
        if isinstance(comp_checked, Missing):
            if comp_checked.reason in ("NOT_COMPUTABLE", "CONTROL_FAILED"):
                state_failure = comp_checked
            else:
                step_missing.append(("compaction_increment", comp_checked))

        if isinstance(step.tillage_loosening, Missing):
            step_missing.append(("tillage_loosening", step.tillage_loosening))
        if isinstance(step.rainfall_kinetic_energy, Missing):
            step_missing.append(
                ("rainfall_kinetic_energy", step.rainfall_kinetic_energy)
            )
        if isinstance(step.measured_bulk_density, Missing):
            step_missing.append(("measured_bulk_density", step.measured_bulk_density))

        if state_failure is None and step_missing:
            state_failure = _aggregate_missing(
                step_missing, f"{step_prefix} missing measurement(s)"
            )

        if state_failure is not None:
            if first_series_failure is None:
                first_series_failure = state_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=state_failure,
                    porosity=state_failure,
                    cumulative_kinetic_energy=state_failure,
                    crusting_factor=state_failure,
                    infiltrability_ratio=state_failure,
                    cn_delta_estimate=state_failure,
                    clamped_low=False,
                    clamped_high=False,
                )
            )
            continue

        assert not isinstance(comp_checked, Missing)
        assert not isinstance(step.tillage_loosening, Missing)
        assert not isinstance(step.rainfall_kinetic_energy, Missing)

        if not _is_finite(step.tillage_loosening):
            state_failure = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}.tillage_loosening is not finite",
            )
        elif not _is_finite(step.rainfall_kinetic_energy):
            state_failure = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}.rainfall_kinetic_energy is not finite",
            )
        elif step.measured_bulk_density is not None and not _is_finite(
            step.measured_bulk_density
        ):
            state_failure = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}.measured_bulk_density is not finite",
            )

        if state_failure is not None:
            if first_series_failure is None:
                first_series_failure = state_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=state_failure,
                    porosity=state_failure,
                    cumulative_kinetic_energy=state_failure,
                    crusting_factor=state_failure,
                    infiltrability_ratio=state_failure,
                    cn_delta_estimate=state_failure,
                    clamped_low=False,
                    clamped_high=False,
                )
            )
            continue

        loosening_val = float(step.tillage_loosening)
        ke_val = float(step.rainfall_kinetic_energy)

        if not step.tillage_event and loosening_val > _ZERO:
            state_failure = Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"{step_prefix}: tillage_loosening={loosening_val} > 0 "
                    "requires tillage_event=True"
                ),
            )
        elif ke_val < _ZERO:
            state_failure = Missing(
                reason="CONTROL_FAILED",
                detail=f"{step_prefix}.rainfall_kinetic_energy must be >= 0, got {ke_val}",
            )
        elif step.measured_bulk_density is not None:
            obs_bd = float(step.measured_bulk_density)
            if obs_bd < bd_min or obs_bd > bd_max:
                state_failure = Missing(
                    reason="CONTROL_FAILED",
                    detail=(
                        f"{step_prefix}.measured_bulk_density={obs_bd} outside "
                        f"[{bd_min}, {bd_max}]"
                    ),
                )

        if state_failure is not None:
            if first_series_failure is None:
                first_series_failure = state_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=state_failure,
                    porosity=state_failure,
                    cumulative_kinetic_energy=state_failure,
                    crusting_factor=state_failure,
                    infiltrability_ratio=state_failure,
                    cn_delta_estimate=state_failure,
                    clamped_low=False,
                    clamped_high=False,
                )
            )
            continue

        bd_state = step_bulk_density_state(
            bd_curr,
            compaction_increment=comp_checked,
            tillage_loosening=loosening_val,
            biological_relaxation_rate=bio_rate,
            baseline_bulk_density=bd_base,
            min_bulk_density=bd_min,
            max_bulk_density=bd_max,
            particle_density=rho_s,
        )
        if isinstance(bd_state.bulk_density, Missing):
            state_failure = bd_state.bulk_density
            if first_series_failure is None:
                first_series_failure = state_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=state_failure,
                    porosity=state_failure,
                    cumulative_kinetic_energy=state_failure,
                    crusting_factor=state_failure,
                    infiltrability_ratio=state_failure,
                    cn_delta_estimate=state_failure,
                    clamped_low=False,
                    clamped_high=False,
                )
            )
            continue

        assert isinstance(bd_state.bulk_density, float)
        assert isinstance(bd_state.porosity, float)
        bd_curr = bd_state.bulk_density
        porosity_curr = bd_state.porosity

        if ke_failure is not None:
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=bd_curr,
                    porosity=porosity_curr,
                    cumulative_kinetic_energy=ke_failure,
                    crusting_factor=ke_failure,
                    infiltrability_ratio=ke_failure,
                    cn_delta_estimate=ke_failure,
                    clamped_low=bd_state.clamped_low,
                    clamped_high=bd_state.clamped_high,
                )
            )
            continue

        cum_ke_next = (_ZERO if step.tillage_event else cum_ke_curr) + ke_val
        if not _is_finite(cum_ke_next):
            ke_failure = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}: cumulative_kinetic_energy is not finite",
            )
            if first_series_failure is None:
                first_series_failure = ke_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=bd_curr,
                    porosity=porosity_curr,
                    cumulative_kinetic_energy=ke_failure,
                    crusting_factor=ke_failure,
                    infiltrability_ratio=ke_failure,
                    cn_delta_estimate=ke_failure,
                    clamped_low=bd_state.clamped_low,
                    clamped_high=bd_state.clamped_high,
                )
            )
            continue

        cum_ke_curr = cum_ke_next
        crust = compute_surface_crusting_factor(
            cum_ke_curr,
            crust_decay_rate=crust_decay,
            min_crust_factor=min_crust,
        )
        if isinstance(crust, Missing):
            ke_failure = crust
            if first_series_failure is None:
                first_series_failure = ke_failure
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=bd_curr,
                    porosity=porosity_curr,
                    cumulative_kinetic_energy=cum_ke_curr,
                    crusting_factor=crust,
                    infiltrability_ratio=crust,
                    cn_delta_estimate=crust,
                    clamped_low=bd_state.clamped_low,
                    clamped_high=bd_state.clamped_high,
                )
            )
            continue

        try:
            porosity_ratio = porosity_curr / baseline_porosity
            infiltrability = crust * (porosity_ratio**porosity_exp)
            cn_delta = cn_sens * (_ONE - infiltrability)
        except OverflowError:
            step_math_fail = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}: coupled feedback overflowed finite range",
            )
            if first_series_failure is None:
                first_series_failure = step_math_fail
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=bd_curr,
                    porosity=porosity_curr,
                    cumulative_kinetic_energy=cum_ke_curr,
                    crusting_factor=crust,
                    infiltrability_ratio=step_math_fail,
                    cn_delta_estimate=step_math_fail,
                    clamped_low=bd_state.clamped_low,
                    clamped_high=bd_state.clamped_high,
                )
            )
            continue

        if not _is_finite(infiltrability) or not _is_finite(cn_delta):
            step_math_fail = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{step_prefix}: infiltrability_ratio or cn_delta_estimate is not finite",
            )
            if first_series_failure is None:
                first_series_failure = step_math_fail
            results.append(
                _make_step_result(
                    step_id=step.step_id,
                    bulk_density=bd_curr,
                    porosity=porosity_curr,
                    cumulative_kinetic_energy=cum_ke_curr,
                    crusting_factor=crust,
                    infiltrability_ratio=step_math_fail,
                    cn_delta_estimate=step_math_fail,
                    clamped_low=bd_state.clamped_low,
                    clamped_high=bd_state.clamped_high,
                )
            )
            continue

        results.append(
            _make_step_result(
                step_id=step.step_id,
                bulk_density=bd_curr,
                porosity=porosity_curr,
                cumulative_kinetic_energy=cum_ke_curr,
                crusting_factor=crust,
                infiltrability_ratio=infiltrability,
                cn_delta_estimate=cn_delta,
                clamped_low=bd_state.clamped_low,
                clamped_high=bd_state.clamped_high,
            )
        )

    last = results[-1]
    return SoilStructureFeedbackSeries(
        model_id=spec.model_id,
        steps=tuple(results),
        final_bulk_density=last.bulk_density,
        final_porosity=last.porosity,
        final_crusting_factor=last.crusting_factor,
        final_infiltrability_ratio=last.infiltrability_ratio,
        final_cn_delta_estimate=last.cn_delta_estimate,
        series_missing=first_series_failure,
        cn_delta_diagnostic_tier=DIAGNOSTIC_TIER,
        status=STATUS_TAG,
        frontier_line=FRONTIER_LINE,
        maturity=MATURITY_TAG,
        data_availability=DATA_AVAILABILITY_TAG,
        normative_ep3_wired=NORMATIVE_EP3_WIRED,
    )
