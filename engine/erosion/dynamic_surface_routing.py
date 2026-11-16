"""Dynamic post-tillage surface routing and channel export guard (L06). PROPOSED.

Implements Frontier Line ``L06`` (Blueprint §3.7 — Frontier Vision Rev13):
``PROPOSED``, ``FRONTIER``, ``LOCAL_MEASUREMENT_REQUIRED``.

Provides four pure, parameter-free-of-constants components:

1. ``surface_roughness_trajectory``: post-tillage surface random roughness
   exponential decay over cumulative precipitation and/or cumulative rainfall
   kinetic energy, bounding ``Rr(t)`` within ``[r_min, r_initial]`` and
   computing the dimensionless roughness index and roughness subfactor::

       Rr(t) = r_min + (r_initial - r_min)
               * exp(-(precip_decay_coef * P_cum + energy_decay_coef * E_cum))
       roughness_index = (Rr(t) - r_min) / (r_initial - r_min)   (or 0 if equal)
       roughness_subfactor = exp(-roughness_coef * (Rr(t) - roughness_ref))

2. ``consolidation_trajectory``: post-disturbance soil consolidation multiplier
   tracking stabilization over elapsed days and/or cumulative precipitation::

       decay = exp(-(day_decay_coef * elapsed_days + precip_decay_coef * P_cum))
       stabilization_fraction = 1 - decay
       consolidation_multiplier = c_consolidated
                                  + (c_disturbed - c_consolidated) * decay

3. ``evaluate_dynamic_surface_routing`` / ``DynamicSurfacePeriod``: dynamic
   time-varying segmented hillslope ``LS`` wrapper calling
   ``engine.erosion.dynamic_ls.dynamic_segmented_ls`` per period and combining
   it with surface roughness and consolidation subfactors under explicit
   ``"EXPLORATORY"`` / ``"PROPOSED"`` provenance while leaving normative RUSLE
   EP1 (``engine.erosion.soil_loss``) completely untouched.

4. ``evaluate_channel_sediment_export``: explicit channel-sediment mass export
   guard that refuses to equate dimensionless topological ``IC`` with
   dimensional sediment yield (``t ha-1 yr-1``) whenever calibrated channel
   hydraulics or sediment delivery ratio (SDR) parameters are absent, returning
   typed ``Missing(reason="NOT_AVAILABLE", detail=...)`` (never ``0.0``).

Units and coefficients
----------------------
- **Zero hardcoded science constants or default parameters.** Every physical
  coefficient, threshold, decay rate, and reference value is keyword-only with
  no default value.
- Pure functions (``contracts/ENTRYPOINTS.md`` G1): stdlib +
  ``contracts.*`` + ``engine.erosion.dynamic_ls`` only; no file I/O, no
  network, no clock, no environment reads, and no input mutation.
- Missing and out-of-domain results follow G4 (``contracts.results.models.Missing``);
  invalid caller types or blank calibration references raise ``TypeError`` /
  ``ValueError`` (G5).
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion.dynamic_ls import (
    SlopeSegment,
    SlopeUnit,
    dynamic_segmented_ls,
)

__all__ = [
    "CHANNEL_EXPORT_UNIT",
    "DATA_AVAILABILITY",
    "FRONTIER_LINE_ID",
    "GOVERNANCE_PROPOSED",
    "METHOD_MATURITY",
    "PROVENANCE_EXPLORATORY",
    "STATUS",
    "ChannelSedimentExportResult",
    "ConsolidationForcingPoint",
    "ConsolidationStep",
    "DynamicSurfacePeriod",
    "DynamicSurfacePeriodResult",
    "DynamicSurfaceRoutingResult",
    "RoughnessForcingPoint",
    "SurfaceRoughnessStep",
    "consolidation_trajectory",
    "evaluate_channel_sediment_export",
    "evaluate_dynamic_surface_routing",
    "surface_roughness_trajectory",
]

STATUS: Final[str] = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
FRONTIER_LINE_ID: Final[Literal["L06"]] = "L06"
METHOD_MATURITY: Final[Literal["FRONTIER"]] = "FRONTIER"
DATA_AVAILABILITY: Final[Literal["LOCAL_MEASUREMENT_REQUIRED"]] = (
    "LOCAL_MEASUREMENT_REQUIRED"
)
PROVENANCE_EXPLORATORY: Final[Literal["EXPLORATORY"]] = "EXPLORATORY"
GOVERNANCE_PROPOSED: Final[Literal["PROPOSED"]] = "PROPOSED"
CHANNEL_EXPORT_UNIT: Final[Literal["t ha-1 yr-1"]] = "t ha-1 yr-1"

NumberOrMissing = float | InputMissing | ResultMissing

_MISSING = (InputMissing, ResultMissing)


@dataclass(frozen=True)
class RoughnessForcingPoint:
    """Cumulative forcing since tillage for one trajectory point. PROPOSED."""

    point_id: Hashable
    cumulative_precip: NumberOrMissing
    cumulative_kinetic_energy: NumberOrMissing


@dataclass(frozen=True)
class SurfaceRoughnessStep:
    """Evaluated post-tillage surface random roughness and subfactor. PROPOSED."""

    point_id: Hashable
    random_roughness: float | ResultMissing
    roughness_subfactor: float | ResultMissing
    roughness_index: float | ResultMissing
    provenance: Literal["EXPLORATORY"]
    governance_status: Literal["PROPOSED"]


@dataclass(frozen=True)
class ConsolidationForcingPoint:
    """Post-disturbance elapsed days and cumulative precipitation. PROPOSED."""

    point_id: Hashable
    elapsed_days: NumberOrMissing
    cumulative_precip: NumberOrMissing


@dataclass(frozen=True)
class ConsolidationStep:
    """Evaluated post-disturbance soil consolidation multiplier. PROPOSED."""

    point_id: Hashable
    consolidation_multiplier: float | ResultMissing
    stabilization_fraction: float | ResultMissing
    provenance: Literal["EXPLORATORY"]
    governance_status: Literal["PROPOSED"]


@dataclass(frozen=True)
class DynamicSurfacePeriod:
    """One period for dynamic segmented LS and surface state routing. PROPOSED."""

    period_id: Hashable
    segments: Sequence[SlopeSegment]
    cumulative_precip_since_tillage: NumberOrMissing
    cumulative_kinetic_energy_since_tillage: NumberOrMissing
    elapsed_days_since_disturbance: NumberOrMissing
    cumulative_precip_since_disturbance: NumberOrMissing


@dataclass(frozen=True)
class DynamicSurfacePeriodResult:
    """Evaluated dynamic surface routing factors for one period. PROPOSED."""

    period_id: Hashable
    segmented_ls: float | ResultMissing
    random_roughness: float | ResultMissing
    roughness_subfactor: float | ResultMissing
    roughness_index: float | ResultMissing
    consolidation_multiplier: float | ResultMissing
    stabilization_fraction: float | ResultMissing
    effective_surface_factor: float | ResultMissing
    provenance: Literal["EXPLORATORY"]
    governance_status: Literal["PROPOSED"]


@dataclass(frozen=True)
class DynamicSurfaceRoutingResult:
    """Multi-period dynamic LS + surface roughness/consolidation bundle. PROPOSED."""

    periods: tuple[DynamicSurfacePeriodResult, ...]
    provenance: Literal["EXPLORATORY"]
    governance_status: Literal["PROPOSED"]
    frontier_line: Literal["L06"]
    method_maturity: Literal["FRONTIER"]
    data_availability: Literal["LOCAL_MEASUREMENT_REQUIRED"]
    normative_ep1_untouched: Literal[True]
    overwrites_normative_ep1: Literal[False]

    def __post_init__(self) -> None:
        if self.provenance != PROVENANCE_EXPLORATORY:
            raise ValueError("provenance must be 'EXPLORATORY'")
        if self.governance_status != GOVERNANCE_PROPOSED:
            raise ValueError("governance_status must be 'PROPOSED'")
        if self.frontier_line != FRONTIER_LINE_ID:
            raise ValueError("frontier_line must be 'L06'")
        if self.method_maturity != METHOD_MATURITY:
            raise ValueError("method_maturity must be 'FRONTIER'")
        if self.data_availability != DATA_AVAILABILITY:
            raise ValueError("data_availability must be 'LOCAL_MEASUREMENT_REQUIRED'")
        if self.normative_ep1_untouched is not True:
            raise ValueError("normative_ep1_untouched must be True")
        if self.overwrites_normative_ep1 is not False:
            raise ValueError("overwrites_normative_ep1 must be False")


@dataclass(frozen=True)
class ChannelSedimentExportResult:
    """Calibrated exploratory channel-sediment mass export estimate. PROPOSED."""

    exported_sediment_yield: float
    sediment_delivery_ratio: float
    unit: Literal["t ha-1 yr-1"]
    calibration_ref: str
    provenance: Literal["EXPLORATORY"]
    governance_status: Literal["PROPOSED"]
    frontier_line: Literal["L06"]
    overwrites_normative_ep1: Literal[False]

    def __post_init__(self) -> None:
        if self.unit != CHANNEL_EXPORT_UNIT:
            raise ValueError("unit must be 't ha-1 yr-1'")
        if self.provenance != PROVENANCE_EXPLORATORY:
            raise ValueError("provenance must be 'EXPLORATORY'")
        if self.governance_status != GOVERNANCE_PROPOSED:
            raise ValueError("governance_status must be 'PROPOSED'")
        if self.frontier_line != FRONTIER_LINE_ID:
            raise ValueError("frontier_line must be 'L06'")
        if self.overwrites_normative_ep1 is not False:
            raise ValueError("overwrites_normative_ep1 must be False")


def _check_number_or_missing(name: str, item: object) -> None:
    """G5: reject anything other than a real number (not bool) or ``Missing``."""
    if isinstance(item, _MISSING):
        return
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise TypeError(
            f"{name}: expected a number, or a Missing of the contract models "
            f"with its reason; got {type(item).__name__}. A missing value is "
            "never passed as None"
        )


def _check_hashable(name: str, item: object) -> None:
    try:
        hash(item)
    except TypeError as exc:
        raise TypeError(
            f"{name}: expected a Hashable identifier, got {type(item).__name__}"
        ) from exc


def _check_bool(name: str, item: object) -> None:
    if type(item) is not bool:
        raise TypeError(f"{name}: expected bool, got {type(item).__name__}")


def _check_slope_unit(name: str, item: object) -> None:
    if not isinstance(item, SlopeUnit):
        raise TypeError(f"{name}: expected a SlopeUnit, got {type(item).__name__}")


def _check_str_or_missing(name: str, item: object) -> None:
    if isinstance(item, _MISSING):
        return
    if not isinstance(item, str):
        raise TypeError(f"{name}: expected str or Missing, got {type(item).__name__}")
    if item.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank")


def _check_scalar_mapping(scalars: Mapping[str, object]) -> None:
    for name, item in scalars.items():
        _check_number_or_missing(name, item)


def _describe_missing(name: str, item: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {item.reason}"
    if item.detail is not None:
        text += f": {item.detail}"
    return text


def _finite(item: object) -> float | None:
    try:
        number = float(item)  # type: ignore[arg-type]
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _collect_finite_scalars(
    scalars: Mapping[str, object],
) -> dict[str, float] | ResultMissing:
    """Validate G4 missingness and finiteness for scalar numeric arguments."""
    absent = [
        _describe_missing(name, item)
        for name, item in scalars.items()
        if isinstance(item, _MISSING)
    ]
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))

    values: dict[str, float] = {}
    not_finite: list[str] = []
    for name, item in scalars.items():
        value = _finite(item)
        if value is None:
            not_finite.append(name)
        else:
            values[name] = value

    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    return values


def _resolve_pair(
    first_name: str,
    first_item: object,
    second_name: str,
    second_item: object,
) -> tuple[float, float] | ResultMissing:
    """Resolve two per-step forcing inputs or return typed ``Missing``."""
    absent: list[str] = []
    if isinstance(first_item, _MISSING):
        absent.append(_describe_missing(first_name, first_item))
    if isinstance(second_item, _MISSING):
        absent.append(_describe_missing(second_name, second_item))
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))

    first_val = _finite(first_item)
    second_val = _finite(second_item)
    not_finite: list[str] = []
    if first_val is None:
        not_finite.append(first_name)
    if second_val is None:
        not_finite.append(second_name)
    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    assert first_val is not None and second_val is not None
    return first_val, second_val


def surface_roughness_trajectory(
    points: Sequence[RoughnessForcingPoint],
    *,
    r_initial: NumberOrMissing,
    r_min: NumberOrMissing,
    precip_decay_coef: NumberOrMissing,
    energy_decay_coef: NumberOrMissing,
    roughness_coef: NumberOrMissing,
    roughness_ref: NumberOrMissing,
) -> tuple[SurfaceRoughnessStep, ...] | ResultMissing:
    """Evaluate post-tillage surface random roughness exponential decay. PROPOSED.

    All physical parameters are keyword-only with zero default values.
    """
    if isinstance(points, (str, bytes, bytearray)) or not isinstance(points, Sequence):
        raise TypeError(
            "points: expected a sequence of RoughnessForcingPoint, "
            f"got {type(points).__name__}"
        )
    for index, point in enumerate(points):
        if not isinstance(point, RoughnessForcingPoint):
            raise TypeError(
                f"points[{index}]: expected RoughnessForcingPoint, "
                f"got {type(point).__name__}"
            )
        _check_hashable(f"points[{index}].point_id", point.point_id)
        _check_number_or_missing(
            f"points[{index}].cumulative_precip", point.cumulative_precip
        )
        _check_number_or_missing(
            f"points[{index}].cumulative_kinetic_energy",
            point.cumulative_kinetic_energy,
        )

    scalars: dict[str, object] = {
        "r_initial": r_initial,
        "r_min": r_min,
        "precip_decay_coef": precip_decay_coef,
        "energy_decay_coef": energy_decay_coef,
        "roughness_coef": roughness_coef,
        "roughness_ref": roughness_ref,
    }
    _check_scalar_mapping(scalars)

    values = _collect_finite_scalars(scalars)
    if isinstance(values, ResultMissing):
        return values

    r0 = values["r_initial"]
    r_lo = values["r_min"]
    k_p = values["precip_decay_coef"]
    k_e = values["energy_decay_coef"]
    c_r = values["roughness_coef"]
    r_ref = values["roughness_ref"]

    domain_errors: list[str] = []
    if r0 <= 0.0:
        domain_errors.append(f"r_initial must be > 0, got {r0}")
    if r_lo < 0.0:
        domain_errors.append(f"r_min must be >= 0, got {r_lo}")
    if r_lo > r0:
        domain_errors.append(f"r_min ({r_lo}) must be <= r_initial ({r0})")
    if k_p < 0.0:
        domain_errors.append(f"precip_decay_coef must be >= 0, got {k_p}")
    if k_e < 0.0:
        domain_errors.append(f"energy_decay_coef must be >= 0, got {k_e}")
    if c_r < 0.0:
        domain_errors.append(f"roughness_coef must be >= 0, got {c_r}")
    if r_ref < 0.0:
        domain_errors.append(f"roughness_ref must be >= 0, got {r_ref}")
    if domain_errors:
        return ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(domain_errors))

    span = r0 - r_lo
    if not math.isfinite(span):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="r_initial - r_min is not a finite real number",
        )

    steps: list[SurfaceRoughnessStep] = []
    for index, point in enumerate(points):
        resolved = _resolve_pair(
            f"points[{index}].cumulative_precip",
            point.cumulative_precip,
            f"points[{index}].cumulative_kinetic_energy",
            point.cumulative_kinetic_energy,
        )
        if isinstance(resolved, ResultMissing):
            steps.append(
                SurfaceRoughnessStep(
                    point_id=point.point_id,
                    random_roughness=resolved,
                    roughness_subfactor=resolved,
                    roughness_index=resolved,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        p_cum, e_cum = resolved
        negatives: list[str] = []
        if p_cum < 0.0:
            negatives.append(
                f"points[{index}].cumulative_precip must be >= 0, got {p_cum}"
            )
        if e_cum < 0.0:
            negatives.append(
                f"points[{index}].cumulative_kinetic_energy must be >= 0, got {e_cum}"
            )
        if negatives:
            miss = ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(negatives))
            steps.append(
                SurfaceRoughnessStep(
                    point_id=point.point_id,
                    random_roughness=miss,
                    roughness_subfactor=miss,
                    roughness_index=miss,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        try:
            exponent_arg = k_p * p_cum + k_e * e_cum
            if not math.isfinite(exponent_arg):
                raise OverflowError
            decay_factor = math.exp(-exponent_arg)
            raw_rr = r_lo + span * decay_factor
            rr = min(r0, max(r_lo, raw_rr))
            if not math.isfinite(rr):
                raise OverflowError
            if span > 0.0:
                idx = min(1.0, max(0.0, (rr - r_lo) / span))
            else:
                idx = 0.0
            subfactor = math.exp(-c_r * (rr - r_ref))
            if not math.isfinite(idx) or not math.isfinite(subfactor):
                raise OverflowError
        except ArithmeticError:
            miss = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"points[{index}]: roughness trajectory step is not a finite "
                    "real number"
                ),
            )
            steps.append(
                SurfaceRoughnessStep(
                    point_id=point.point_id,
                    random_roughness=miss,
                    roughness_subfactor=miss,
                    roughness_index=miss,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        steps.append(
            SurfaceRoughnessStep(
                point_id=point.point_id,
                random_roughness=rr,
                roughness_subfactor=subfactor,
                roughness_index=idx,
                provenance=PROVENANCE_EXPLORATORY,
                governance_status=GOVERNANCE_PROPOSED,
            )
        )

    return tuple(steps)


def consolidation_trajectory(
    points: Sequence[ConsolidationForcingPoint],
    *,
    c_disturbed: NumberOrMissing,
    c_consolidated: NumberOrMissing,
    day_decay_coef: NumberOrMissing,
    precip_decay_coef: NumberOrMissing,
) -> tuple[ConsolidationStep, ...] | ResultMissing:
    """Evaluate post-disturbance soil consolidation multiplier trajectory. PROPOSED.

    All physical parameters are keyword-only with zero default values.
    """
    if isinstance(points, (str, bytes, bytearray)) or not isinstance(points, Sequence):
        raise TypeError(
            "points: expected a sequence of ConsolidationForcingPoint, "
            f"got {type(points).__name__}"
        )
    for index, point in enumerate(points):
        if not isinstance(point, ConsolidationForcingPoint):
            raise TypeError(
                f"points[{index}]: expected ConsolidationForcingPoint, "
                f"got {type(point).__name__}"
            )
        _check_hashable(f"points[{index}].point_id", point.point_id)
        _check_number_or_missing(f"points[{index}].elapsed_days", point.elapsed_days)
        _check_number_or_missing(
            f"points[{index}].cumulative_precip", point.cumulative_precip
        )

    scalars: dict[str, object] = {
        "c_disturbed": c_disturbed,
        "c_consolidated": c_consolidated,
        "day_decay_coef": day_decay_coef,
        "precip_decay_coef": precip_decay_coef,
    }
    _check_scalar_mapping(scalars)

    values = _collect_finite_scalars(scalars)
    if isinstance(values, ResultMissing):
        return values

    c_hi = values["c_disturbed"]
    c_lo = values["c_consolidated"]
    k_d = values["day_decay_coef"]
    k_p = values["precip_decay_coef"]

    domain_errors: list[str] = []
    if c_hi <= 0.0:
        domain_errors.append(f"c_disturbed must be > 0, got {c_hi}")
    if c_lo <= 0.0:
        domain_errors.append(f"c_consolidated must be > 0, got {c_lo}")
    if c_lo > c_hi:
        domain_errors.append(f"c_consolidated ({c_lo}) must be <= c_disturbed ({c_hi})")
    if k_d < 0.0:
        domain_errors.append(f"day_decay_coef must be >= 0, got {k_d}")
    if k_p < 0.0:
        domain_errors.append(f"precip_decay_coef must be >= 0, got {k_p}")
    if domain_errors:
        return ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(domain_errors))

    span = c_hi - c_lo
    if not math.isfinite(span):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="c_disturbed - c_consolidated is not a finite real number",
        )

    steps: list[ConsolidationStep] = []
    for index, point in enumerate(points):
        resolved = _resolve_pair(
            f"points[{index}].elapsed_days",
            point.elapsed_days,
            f"points[{index}].cumulative_precip",
            point.cumulative_precip,
        )
        if isinstance(resolved, ResultMissing):
            steps.append(
                ConsolidationStep(
                    point_id=point.point_id,
                    consolidation_multiplier=resolved,
                    stabilization_fraction=resolved,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        days, p_cum = resolved
        negatives: list[str] = []
        if days < 0.0:
            negatives.append(f"points[{index}].elapsed_days must be >= 0, got {days}")
        if p_cum < 0.0:
            negatives.append(
                f"points[{index}].cumulative_precip must be >= 0, got {p_cum}"
            )
        if negatives:
            miss = ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(negatives))
            steps.append(
                ConsolidationStep(
                    point_id=point.point_id,
                    consolidation_multiplier=miss,
                    stabilization_fraction=miss,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        try:
            exponent_arg = k_d * days + k_p * p_cum
            if not math.isfinite(exponent_arg):
                raise OverflowError
            decay_factor = math.exp(-exponent_arg)
            stabilization = min(1.0, max(0.0, 1.0 - decay_factor))
            raw_mult = c_lo + span * decay_factor
            multiplier = min(c_hi, max(c_lo, raw_mult))
            if not math.isfinite(stabilization) or not math.isfinite(multiplier):
                raise OverflowError
        except ArithmeticError:
            miss = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"points[{index}]: consolidation trajectory step is not a "
                    "finite real number"
                ),
            )
            steps.append(
                ConsolidationStep(
                    point_id=point.point_id,
                    consolidation_multiplier=miss,
                    stabilization_fraction=miss,
                    provenance=PROVENANCE_EXPLORATORY,
                    governance_status=GOVERNANCE_PROPOSED,
                )
            )
            continue

        steps.append(
            ConsolidationStep(
                point_id=point.point_id,
                consolidation_multiplier=multiplier,
                stabilization_fraction=stabilization,
                provenance=PROVENANCE_EXPLORATORY,
                governance_status=GOVERNANCE_PROPOSED,
            )
        )

    return tuple(steps)


def _combine_three_factors(
    ls_val: float | ResultMissing,
    rough_val: float | ResultMissing,
    consol_val: float | ResultMissing,
    period_id: Hashable,
) -> float | ResultMissing:
    """Multiply three factors when finite, or propagate typed ``Missing`` (C3.3)."""
    factors = (ls_val, rough_val, consol_val)
    missing_inputs = [
        item
        for item in factors
        if isinstance(item, ResultMissing) and item.reason == "MISSING_INPUT"
    ]
    if missing_inputs:
        details = [item.detail for item in missing_inputs if item.detail is not None]
        return ResultMissing(
            reason="MISSING_INPUT",
            detail="; ".join(details)
            if details
            else f"period {period_id!r} missing input",
        )
    other_missing = [item for item in factors if isinstance(item, ResultMissing)]
    if other_missing:
        first_reason = other_missing[0].reason
        details = [item.detail for item in other_missing if item.detail is not None]
        return ResultMissing(
            reason=first_reason,
            detail="; ".join(details) if details else None,
        )

    assert isinstance(ls_val, float)
    assert isinstance(rough_val, float)
    assert isinstance(consol_val, float)
    try:
        product = ls_val * rough_val * consol_val
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"period {period_id!r}: effective_surface_factor overflowed",
        )
    if not math.isfinite(product):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"period {period_id!r}: effective_surface_factor is not finite",
        )
    return product


def evaluate_dynamic_surface_routing(
    periods: Sequence[DynamicSurfacePeriod],
    *,
    slope_unit: SlopeUnit,
    a1: NumberOrMissing,
    a2: NumberOrMissing,
    a3: NumberOrMissing,
    a4: NumberOrMissing,
    s_break: NumberOrMissing,
    lambda_unit: NumberOrMissing,
    b1: NumberOrMissing,
    b2: NumberOrMissing,
    b3: NumberOrMissing,
    b4: NumberOrMissing,
    r_initial: NumberOrMissing,
    r_min: NumberOrMissing,
    roughness_precip_decay_coef: NumberOrMissing,
    roughness_energy_decay_coef: NumberOrMissing,
    roughness_coef: NumberOrMissing,
    roughness_ref: NumberOrMissing,
    c_disturbed: NumberOrMissing,
    c_consolidated: NumberOrMissing,
    consolidation_day_decay_coef: NumberOrMissing,
    consolidation_precip_decay_coef: NumberOrMissing,
) -> DynamicSurfaceRoutingResult:
    """Evaluate dynamic segmented LS combined with surface roughness & consolidation.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13, Line L06).
    Calls ``engine.erosion.dynamic_ls.dynamic_segmented_ls`` per period and
    keeps normative RUSLE EP1 untouched.
    """
    if isinstance(periods, (str, bytes, bytearray)) or not isinstance(
        periods, Sequence
    ):
        raise TypeError(
            "periods: expected a sequence of DynamicSurfacePeriod, "
            f"got {type(periods).__name__}"
        )
    for index, period in enumerate(periods):
        if not isinstance(period, DynamicSurfacePeriod):
            raise TypeError(
                f"periods[{index}]: expected DynamicSurfacePeriod, "
                f"got {type(period).__name__}"
            )
        _check_hashable(f"periods[{index}].period_id", period.period_id)

    _check_slope_unit("slope_unit", slope_unit)
    ls_scalars: dict[str, object] = {
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "a4": a4,
        "s_break": s_break,
        "lambda_unit": lambda_unit,
        "b1": b1,
        "b2": b2,
        "b3": b3,
        "b4": b4,
    }
    _check_scalar_mapping(ls_scalars)

    roughness_points = [
        RoughnessForcingPoint(
            point_id=period.period_id,
            cumulative_precip=period.cumulative_precip_since_tillage,
            cumulative_kinetic_energy=period.cumulative_kinetic_energy_since_tillage,
        )
        for period in periods
    ]
    consolidation_points = [
        ConsolidationForcingPoint(
            point_id=period.period_id,
            elapsed_days=period.elapsed_days_since_disturbance,
            cumulative_precip=period.cumulative_precip_since_disturbance,
        )
        for period in periods
    ]

    roughness_result = surface_roughness_trajectory(
        roughness_points,
        r_initial=r_initial,
        r_min=r_min,
        precip_decay_coef=roughness_precip_decay_coef,
        energy_decay_coef=roughness_energy_decay_coef,
        roughness_coef=roughness_coef,
        roughness_ref=roughness_ref,
    )
    consolidation_result = consolidation_trajectory(
        consolidation_points,
        c_disturbed=c_disturbed,
        c_consolidated=c_consolidated,
        day_decay_coef=consolidation_day_decay_coef,
        precip_decay_coef=consolidation_precip_decay_coef,
    )

    # Validate each period's segments via dynamic_segmented_ls after trajectory checks.
    period_results: list[DynamicSurfacePeriodResult] = []
    for index, period in enumerate(periods):
        seg_ls = dynamic_segmented_ls(
            period.segments,
            slope_unit=slope_unit,
            a1=a1,
            a2=a2,
            a3=a3,
            a4=a4,
            s_break=s_break,
            lambda_unit=lambda_unit,
            b1=b1,
            b2=b2,
            b3=b3,
            b4=b4,
        )
        if isinstance(roughness_result, ResultMissing):
            rr: float | ResultMissing = roughness_result
            r_sub: float | ResultMissing = roughness_result
            r_idx: float | ResultMissing = roughness_result
        else:
            r_step = roughness_result[index]
            rr = r_step.random_roughness
            r_sub = r_step.roughness_subfactor
            r_idx = r_step.roughness_index

        if isinstance(consolidation_result, ResultMissing):
            c_mult: float | ResultMissing = consolidation_result
            stab: float | ResultMissing = consolidation_result
        else:
            c_step = consolidation_result[index]
            c_mult = c_step.consolidation_multiplier
            stab = c_step.stabilization_fraction

        effective = _combine_three_factors(seg_ls, r_sub, c_mult, period.period_id)
        period_results.append(
            DynamicSurfacePeriodResult(
                period_id=period.period_id,
                segmented_ls=seg_ls,
                random_roughness=rr,
                roughness_subfactor=r_sub,
                roughness_index=r_idx,
                consolidation_multiplier=c_mult,
                stabilization_fraction=stab,
                effective_surface_factor=effective,
                provenance=PROVENANCE_EXPLORATORY,
                governance_status=GOVERNANCE_PROPOSED,
            )
        )

    return DynamicSurfaceRoutingResult(
        periods=tuple(period_results),
        provenance=PROVENANCE_EXPLORATORY,
        governance_status=GOVERNANCE_PROPOSED,
        frontier_line=FRONTIER_LINE_ID,
        method_maturity=METHOD_MATURITY,
        data_availability=DATA_AVAILABILITY,
        normative_ep1_untouched=True,
        overwrites_normative_ep1=False,
    )


def evaluate_channel_sediment_export(
    *,
    gross_hillslope_soil_loss: NumberOrMissing,
    connectivity_index_ic: NumberOrMissing,
    channel_hydraulics_calibrated: bool,
    sdr_max: NumberOrMissing,
    ic_zero: NumberOrMissing,
    k_ic: NumberOrMissing,
    channel_transmission_efficiency: NumberOrMissing,
    calibration_ref: str | InputMissing | ResultMissing,
) -> ChannelSedimentExportResult | ResultMissing:
    """Explicit channel-sediment mass export guard for topological IC. PROPOSED.

    Refuses to equate dimensionless Borselli ``IC`` with dimensional sediment
    yield (``t ha-1 yr-1``) when calibrated channel hydraulics or sediment
    delivery ratio (SDR) parameters are absent, returning typed
    ``Missing(reason="NOT_AVAILABLE", detail=...)`` (never ``0.0``).
    """
    _check_bool("channel_hydraulics_calibrated", channel_hydraulics_calibrated)
    numeric_args: dict[str, object] = {
        "gross_hillslope_soil_loss": gross_hillslope_soil_loss,
        "connectivity_index_ic": connectivity_index_ic,
        "sdr_max": sdr_max,
        "ic_zero": ic_zero,
        "k_ic": k_ic,
        "channel_transmission_efficiency": channel_transmission_efficiency,
    }
    _check_scalar_mapping(numeric_args)
    _check_str_or_missing("calibration_ref", calibration_ref)

    calibration_gaps: list[str] = []
    if not channel_hydraulics_calibrated:
        calibration_gaps.append("channel_hydraulics_calibrated is False")
    calibration_params: dict[str, object] = {
        "sdr_max": sdr_max,
        "ic_zero": ic_zero,
        "k_ic": k_ic,
        "channel_transmission_efficiency": channel_transmission_efficiency,
        "calibration_ref": calibration_ref,
    }
    for name, item in calibration_params.items():
        if isinstance(item, _MISSING):
            calibration_gaps.append(_describe_missing(name, item))

    if calibration_gaps:
        return ResultMissing(
            reason="NOT_AVAILABLE",
            detail=(
                "channel-sediment mass export (t ha-1 yr-1) cannot be equated "
                "with dimensionless topological IC without calibrated channel "
                "hydraulics and SDR parameters: " + "; ".join(calibration_gaps)
            ),
        )

    assert isinstance(calibration_ref, str)
    values = _collect_finite_scalars(numeric_args)
    if isinstance(values, ResultMissing):
        return values

    gross_loss = values["gross_hillslope_soil_loss"]
    ic = values["connectivity_index_ic"]
    sdr_cap = values["sdr_max"]
    ic0 = values["ic_zero"]
    k_val = values["k_ic"]
    tx_eff = values["channel_transmission_efficiency"]

    domain_errors: list[str] = []
    if gross_loss < 0.0:
        domain_errors.append(
            f"gross_hillslope_soil_loss must be >= 0, got {gross_loss}"
        )
    if sdr_cap <= 0.0 or sdr_cap > 1.0:
        domain_errors.append(f"sdr_max must be in (0, 1], got {sdr_cap}")
    if k_val <= 0.0:
        domain_errors.append(f"k_ic must be > 0, got {k_val}")
    if tx_eff <= 0.0 or tx_eff > 1.0:
        domain_errors.append(
            f"channel_transmission_efficiency must be in (0, 1], got {tx_eff}"
        )
    if domain_errors:
        return ResultMissing(reason="NOT_COMPUTABLE", detail="; ".join(domain_errors))

    try:
        exponent = (ic0 - ic) / k_val
        if not math.isfinite(exponent):
            raise OverflowError
        exp_term = math.exp(exponent)
        sdr = sdr_cap / (1.0 + exp_term)
        exported = gross_loss * sdr * tx_eff
        if not math.isfinite(sdr) or not math.isfinite(exported):
            raise OverflowError
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="channel sediment export SDR calculation is not a finite real number",
        )

    return ChannelSedimentExportResult(
        exported_sediment_yield=exported,
        sediment_delivery_ratio=sdr,
        unit=CHANNEL_EXPORT_UNIT,
        calibration_ref=calibration_ref,
        provenance=PROVENANCE_EXPLORATORY,
        governance_status=GOVERNANCE_PROPOSED,
        frontier_line=FRONTIER_LINE_ID,
        overwrites_normative_ep1=False,
    )
