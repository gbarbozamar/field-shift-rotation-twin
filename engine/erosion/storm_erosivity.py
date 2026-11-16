"""Sub-hourly storm separation, EI30 erosivity, and official climatology anchoring.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
References: ``27_PLAN_DE_FRONTERA.md`` (§5.1) and ``28_PLAN_INTEGRADO_REV13.md`` (§2).

This standalone module implements sub-hourly (e.g. 30-minute step) rainfall
event separation, kinetic-energy intensity integration (unit KE ``e_j`` and
peak 30-minute intensity ``I30``), ``EI30`` event erosivity, and optional
multiplicative anchoring to an official ``R`` climatology. It is not wired into
``engine/erosion/__init__.py`` or EP1 (``compute_soil_loss``).

Strict configuration and calibration discipline:
- Every domain/method parameter in ``StormErosivityConfig`` is caller-supplied
  with **no hardcoded domain defaults** and **zero magic method constants** in
  code.
- Any interval with ``None`` / missing precipitation within an active storm, or
  any timestamp continuity gap breaking an active storm, propagates typed
  ``Missing(reason="MISSING_INPUT", detail=...)`` (never filled with ``0.0``).
- Negative or non-finite interval precipitation values propagate typed
  ``Missing(reason="NOT_COMPUTABLE", detail=...)`` (never clipped to ``0.0``).
- When ``uruguay_calibrated=False``, outputs carry
  ``method_status="EXPLORATORY_UNVALIDATED"`` and refuse to be labelled as
  ``official_uruguay_calibrated`` or ``EROSION_NORMATIVA``.

Pure functions (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and caller arguments are never mutated.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

__all__ = [
    "CALIBRATION_LABEL_EXPLORATORY",
    "CALIBRATION_LABEL_OFFICIAL",
    "EI30_UNIT",
    "FORBIDDEN_UNVALIDATED_LABELS",
    "I30_WINDOW_MINUTES",
    "METHOD_STATUS_CALIBRATED",
    "METHOD_STATUS_EXPLORATORY",
    "MINUTES_PER_HOUR",
    "NORM_TIER_OFFICIAL",
    "PROVENANCE_DERIVED",
    "StormErosivityConfig",
    "StormErosivitySummary",
    "StormEventErosivity",
    "StormInterval",
    "anchor_erosivity",
    "compute_storm_erosivity",
    "resolve_erosivity_label",
    "unit_kinetic_energy",
]

EI30_UNIT = "MJ mm ha-1 h-1"
PROVENANCE_DERIVED = "DERIVED"

METHOD_STATUS_EXPLORATORY = "EXPLORATORY_UNVALIDATED"
METHOD_STATUS_CALIBRATED = "CALIBRATED_URUGUAY"

CALIBRATION_LABEL_EXPLORATORY = "exploratory_unvalidated"
CALIBRATION_LABEL_OFFICIAL = "official_uruguay_calibrated"
NORM_TIER_OFFICIAL = "EROSION_NORMATIVA"

FORBIDDEN_UNVALIDATED_LABELS = frozenset(
    {CALIBRATION_LABEL_OFFICIAL, NORM_TIER_OFFICIAL}
)

_FORBIDDEN_LABEL_PATTERN = re.compile(
    r"(?<!\w)(?:official_uruguay_calibrated|erosion_normativa)(?!\w)",
    re.IGNORECASE,
)

# SI time-unit conversion (60 min/h) and definitional I30 peak window (30 min).
MINUTES_PER_HOUR = int(dt.timedelta(hours=1) // dt.timedelta(minutes=1))
I30_WINDOW_MINUTES = 30


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_number(value: object) -> bool:
    """True for ``int`` or ``float`` excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_float(name: str, value: object) -> float:
    """Validate a finite numeric parameter (G5)."""
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected float or int, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}: value overflows float") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{name}: expected a finite number, got {value!r}")
    return numeric


def _check_positive_int(name: str, value: object, *, minimum: int) -> int:
    if not _is_strict_int(value):
        raise TypeError(f"{name}: expected int, got {type(value).__name__} (G5)")
    assert isinstance(value, int)
    if value < minimum:
        raise ValueError(f"{name}: expected >= {minimum}, got {value}")
    return value


def _check_non_negative_float(name: str, value: object) -> float:
    numeric = _finite_float(name, value)
    if numeric < 0.0:
        raise ValueError(f"{name}: expected >= 0, got {numeric}")
    return numeric


def _to_result_missing(
    name: str, missing: ResultMissing | InputMissing
) -> ResultMissing:
    """Convert any contract ``Missing`` into ``contracts.results.models.Missing``."""
    detail = f"{name} is missing (reason {missing.reason})"
    if missing.detail is not None:
        detail = f"{detail}: {missing.detail}"
    return ResultMissing(reason="MISSING_INPUT", detail=detail)


@dataclass(frozen=True)
class StormInterval:
    """Single sub-hourly precipitation observation interval.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    When ``precipitation_mm`` is ``None``, the interval represents a missing
    observation (never treated as ``0.0`` rain). ``missing`` may carry an
    optional typed contract ``Missing`` reason and detail.
    """

    timestamp: dt.datetime
    precipitation_mm: float | None
    missing: ResultMissing | InputMissing | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, dt.datetime):
            raise TypeError(
                "timestamp: expected datetime.datetime, "
                f"got {type(self.timestamp).__name__} (G5)"
            )
        if self.precipitation_mm is not None and not _is_strict_number(
            self.precipitation_mm
        ):
            raise TypeError(
                "precipitation_mm: expected float or None, "
                f"got {type(self.precipitation_mm).__name__} (G5)"
            )
        if self.missing is not None and not isinstance(
            self.missing, (ResultMissing, InputMissing)
        ):
            raise TypeError(
                "missing: expected contracts Missing or None, "
                f"got {type(self.missing).__name__} (G5)"
            )
        if self.precipitation_mm is not None and self.missing is not None:
            raise ValueError(
                "StormInterval holds either precipitation_mm or missing, never both (C3.1)"
            )


@dataclass(frozen=True)
class StormErosivityConfig:
    """Caller-supplied storm separation, kinetic-energy, and calibration config.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    All fields are required without defaults so no domain constant or calibration
    assumption is hardcoded in the engine.

    Attributes:
        step_minutes: Duration of each regular observation step in minutes.
        min_dry_gap_intervals: Consecutive observed dry (``0.0`` mm) intervals
            required to close an active storm and separate events.
        min_event_depth_mm: Minimum cumulative depth (mm) for a separated wet
            episode to qualify as an erosive storm event.
        ke_e_max: Maximum unit kinetic energy ``e_max`` (MJ ha-1 mm-1).
        ke_a: Dimensionless coefficient ``a`` in ``e_max * (1 - a * exp(-b * I))``.
        ke_b: Intensity decay parameter ``b`` (h mm-1) in ``exp(-b * I)``.
        ke_c: Optional fourth KE additive parameter ``c`` (MJ ha-1 mm-1); pass
            ``None`` or ``0.0`` for pure ``e_max * (1 - a * exp(-b * I))``.
        official_climatology_anchor_factor: Optional multiplicative factor
            anchoring ``EI30`` to an official ``R`` climatology (or ``Missing`` /
            ``None`` when unanchored).
        uruguay_calibrated: Whether the parameterization has official Uruguay
            validation. ``False`` enforces ``EXPLORATORY_UNVALIDATED`` status.
        bias_correction_source: Explicit provenance citation/source for official
            calibration or climatology anchoring. Required whenever
            ``uruguay_calibrated=True`` or a numeric anchor factor is supplied.
    """

    step_minutes: int
    min_dry_gap_intervals: int
    min_event_depth_mm: float
    ke_e_max: float
    ke_a: float
    ke_b: float
    ke_c: float | None
    official_climatology_anchor_factor: float | ResultMissing | InputMissing | None
    uruguay_calibrated: bool
    bias_correction_source: str | None

    def __post_init__(self) -> None:
        _check_positive_int("step_minutes", self.step_minutes, minimum=1)
        _check_positive_int(
            "min_dry_gap_intervals", self.min_dry_gap_intervals, minimum=1
        )
        _check_non_negative_float("min_event_depth_mm", self.min_event_depth_mm)
        _check_non_negative_float("ke_e_max", self.ke_e_max)
        _check_non_negative_float("ke_a", self.ke_a)
        _check_non_negative_float("ke_b", self.ke_b)
        if self.ke_c is not None:
            _finite_float("ke_c", self.ke_c)

        anchor = self.official_climatology_anchor_factor
        has_numeric_anchor = False
        if anchor is not None and not isinstance(anchor, (ResultMissing, InputMissing)):
            anchor_val = _finite_float("official_climatology_anchor_factor", anchor)
            if anchor_val <= 0.0:
                raise ValueError(
                    "official_climatology_anchor_factor: expected > 0, "
                    f"got {anchor_val}"
                )
            has_numeric_anchor = True

        if not isinstance(self.uruguay_calibrated, bool):
            raise TypeError(
                "uruguay_calibrated: expected bool, "
                f"got {type(self.uruguay_calibrated).__name__} (G5)"
            )

        if self.bias_correction_source is not None:
            if not isinstance(self.bias_correction_source, str):
                raise TypeError(
                    "bias_correction_source: expected str or None, "
                    f"got {type(self.bias_correction_source).__name__} (G5)"
                )
            if self.bias_correction_source.strip() == "":
                raise ValueError(
                    "bias_correction_source: must not be empty or blank when provided"
                )

        if has_numeric_anchor and self.bias_correction_source is None:
            raise ValueError(
                "bias_correction_source is required when "
                "official_climatology_anchor_factor is supplied"
            )
        if self.uruguay_calibrated and self.bias_correction_source is None:
            raise ValueError(
                "bias_correction_source is required when uruguay_calibrated=True"
            )
        if (
            not self.uruguay_calibrated
            and self.bias_correction_source is not None
            and _FORBIDDEN_LABEL_PATTERN.search(self.bias_correction_source)
        ):
            raise ValueError(
                "refusing bias_correction_source claiming official_uruguay_calibrated "
                "or EROSION_NORMATIVA while uruguay_calibrated=False"
            )


@dataclass(frozen=True)
class StormEventErosivity:
    """Erosivity (``EI30``) result for a single separated sub-hourly storm event.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    event_index: int
    start_time: dt.datetime
    end_time: dt.datetime
    interval_count: int
    total_depth_mm: float | ResultMissing
    total_energy_mj_ha: float | ResultMissing
    i30_mm_h: float | ResultMissing
    ei30: float | ResultMissing
    anchored_ei30: float | ResultMissing | None
    ei30_unit: str
    provenance: str | None
    method_status: str
    has_missing_intervals: bool
    broken_by_continuity_gap: bool


@dataclass(frozen=True)
class StormErosivitySummary:
    """Series-level summary of separated storms, total ``EI30``, and anchoring.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    events: tuple[StormEventErosivity, ...]
    total_ei30: float | ResultMissing
    anchored_total_ei30: float | ResultMissing | None
    ei30_unit: str
    method_status: str
    calibration_label: str
    uruguay_calibrated: bool
    bias_correction_source: str | None
    official_climatology_anchor_factor: float | ResultMissing | None
    provenance: str | None
    interval_count: int
    missing_interval_count: int
    continuity_gaps: tuple[tuple[dt.datetime, dt.datetime], ...]


def unit_kinetic_energy(
    intensity_mm_h: float,
    *,
    config: StormErosivityConfig,
) -> float:
    """Compute unit rainfall kinetic energy ``e_j`` (MJ ha-1 mm-1).

    Formula:
        ``e_j = ke_e_max * (1 - ke_a * exp(-ke_b * I_j)) [+ ke_c]``

    All KE constants are read from ``config`` with zero hardcoded defaults.
    """
    if not isinstance(config, StormErosivityConfig):
        raise TypeError(
            f"config: expected StormErosivityConfig, got {type(config).__name__} (G5)"
        )
    intensity = _check_non_negative_float("intensity_mm_h", intensity_mm_h)
    ke = config.ke_e_max * (1.0 - config.ke_a * math.exp(-config.ke_b * intensity))
    if config.ke_c is not None:
        ke += float(config.ke_c)
    if not math.isfinite(ke):
        raise ValueError("unit kinetic energy is not a finite number")
    return float(ke)


def anchor_erosivity(
    ei30: float | ResultMissing,
    *,
    config: StormErosivityConfig,
) -> float | ResultMissing | None:
    """Apply optional multiplicative anchoring to an official R climatology."""
    if not isinstance(config, StormErosivityConfig):
        raise TypeError(
            f"config: expected StormErosivityConfig, got {type(config).__name__} (G5)"
        )
    if not isinstance(ei30, ResultMissing) and not _is_strict_number(ei30):
        raise TypeError(
            f"ei30: expected float or Missing, got {type(ei30).__name__} (G5)"
        )

    factor = config.official_climatology_anchor_factor
    if factor is None:
        return None
    if isinstance(factor, (ResultMissing, InputMissing)):
        return _to_result_missing("official_climatology_anchor_factor", factor)
    if isinstance(ei30, ResultMissing):
        return ei30

    try:
        ei30_val = float(ei30)
    except OverflowError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="ei30 overflows float prior to climatology anchoring",
        )
    if not math.isfinite(ei30_val):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="ei30 is not a finite number",
        )
    anchored = ei30_val * float(factor)
    if not math.isfinite(anchored):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="anchored EI30 is not a finite number",
        )
    return anchored


def resolve_erosivity_label(
    summary: StormErosivitySummary,
    *,
    requested_label: str,
) -> str:
    """Validate an output label against ``summary.uruguay_calibrated``.

    Refuses (with ``ValueError``) to label unvalidated output as
    ``official_uruguay_calibrated`` or ``EROSION_NORMATIVA`` when
    ``uruguay_calibrated=False``.
    """
    if not isinstance(summary, StormErosivitySummary):
        raise TypeError(
            "summary: expected StormErosivitySummary, "
            f"got {type(summary).__name__} (G5)"
        )
    if not isinstance(requested_label, str):
        raise TypeError(
            f"requested_label: expected str, got {type(requested_label).__name__} (G5)"
        )
    if requested_label.strip() == "":
        raise ValueError("requested_label: must not be empty or blank")
    if not summary.uruguay_calibrated:
        forbidden = {label.casefold() for label in FORBIDDEN_UNVALIDATED_LABELS}
        if requested_label.strip().casefold() in forbidden:
            raise ValueError(
                f"refusing label {requested_label!r}: uruguay_calibrated is False "
                f"(method_status={METHOD_STATUS_EXPLORATORY})"
            )
    return requested_label


def _status_labels(uruguay_calibrated: bool) -> tuple[str, str]:
    if uruguay_calibrated:
        return METHOD_STATUS_CALIBRATED, CALIBRATION_LABEL_OFFICIAL
    return METHOD_STATUS_EXPLORATORY, CALIBRATION_LABEL_EXPLORATORY


def _validate_intervals(
    intervals: object, step_minutes: int
) -> tuple[tuple[StormInterval, ...], tuple[tuple[dt.datetime, dt.datetime], ...]]:
    """Validate sequence type, element types, timezone consistency, and order."""
    if isinstance(intervals, (str, bytes, bytearray)) or not isinstance(
        intervals, Sequence
    ):
        raise TypeError(
            "intervals: expected a Sequence of StormInterval, "
            f"got {type(intervals).__name__} (G5)"
        )
    items = tuple(intervals)
    for idx, item in enumerate(items):
        if not isinstance(item, StormInterval):
            raise TypeError(
                f"intervals[{idx}]: expected StormInterval, "
                f"got {type(item).__name__} (G5)"
            )
    if not items:
        return items, ()

    first_tz = items[0].timestamp.tzinfo
    for idx, item in enumerate(items):
        tz = item.timestamp.tzinfo
        if (tz is None) != (first_tz is None):
            raise ValueError(
                f"intervals[{idx}]: cannot mix timezone-aware and naive timestamps"
            )
        if first_tz is not None and tz != first_tz:
            raise ValueError(
                f"intervals[{idx}]: cannot mix different time zones in one series (C6.3)"
            )

    step_delta = dt.timedelta(minutes=step_minutes)
    zero_delta = dt.timedelta(0)
    gaps: list[tuple[dt.datetime, dt.datetime]] = []
    for prev_item, curr_item in pairwise(items):
        delta = curr_item.timestamp - prev_item.timestamp
        if delta <= zero_delta:
            raise ValueError(
                "intervals must have strictly increasing timestamps: "
                f"{curr_item.timestamp.isoformat()} follows "
                f"{prev_item.timestamp.isoformat()}"
            )
        if delta < step_delta:
            raise ValueError(
                f"interval spacing {delta} between {prev_item.timestamp.isoformat()} "
                f"and {curr_item.timestamp.isoformat()} is smaller than "
                f"step_minutes={step_minutes}"
            )
        if delta > step_delta:
            gaps.append((prev_item.timestamp, curr_item.timestamp))
    return items, tuple(gaps)


def _classify_interval(item: StormInterval) -> float | ResultMissing:
    """Return finite non-negative float precipitation, or typed ``ResultMissing``."""
    ts_text = item.timestamp.isoformat()
    if item.precipitation_mm is None:
        if item.missing is not None:
            return _to_result_missing(f"precipitation at {ts_text}", item.missing)
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=f"precipitation at {ts_text} is missing (None, never filled with 0.0)",
        )
    try:
        value = float(item.precipitation_mm)
    except OverflowError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"precipitation at {ts_text} overflows float",
        )
    if not math.isfinite(value):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"precipitation at {ts_text} is not a finite number",
        )
    if value < 0.0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"precipitation at {ts_text} is negative ({value}); not clipped to zero",
        )
    return value


@dataclass
class _ActiveStorm:
    """Internal mutable accumulator scoped strictly to one ``compute_storm_erosivity`` call."""

    storm_intervals: list[StormInterval]
    pending_dry: list[StormInterval]
    missing_reasons: list[ResultMissing]
    not_computable_reasons: list[ResultMissing]
    continuity_gap: tuple[dt.datetime, dt.datetime] | None = None

    def append_wet_or_internal(
        self, item: StormInterval, parsed: float | ResultMissing
    ) -> None:
        if self.pending_dry:
            self.storm_intervals.extend(self.pending_dry)
            self.pending_dry.clear()
        self.storm_intervals.append(item)
        if isinstance(parsed, ResultMissing):
            if parsed.reason == "MISSING_INPUT":
                self.missing_reasons.append(parsed)
            else:
                self.not_computable_reasons.append(parsed)


def _compute_i30(
    depths: list[float], step_minutes: int
) -> tuple[float | ResultMissing, float]:
    """Compute peak 30-minute intensity ``I30`` (mm h-1) or ``NOT_COMPUTABLE``."""
    if I30_WINDOW_MINUTES % step_minutes != 0:
        return (
            ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"cannot compute {I30_WINDOW_MINUTES}-min peak intensity I30 "
                    f"without sub-step disaggregation for step_minutes={step_minutes}"
                ),
            ),
            0.0,
        )
    window_steps = I30_WINDOW_MINUTES // step_minutes
    if len(depths) <= window_steps:
        max_depth = math.fsum(depths)
    else:
        max_depth = max(
            math.fsum(depths[idx : idx + window_steps])
            for idx in range(len(depths) - window_steps + 1)
        )
    window_hours = I30_WINDOW_MINUTES / MINUTES_PER_HOUR
    i30 = max_depth / window_hours
    if not math.isfinite(i30):
        return (
            ResultMissing(
                reason="NOT_COMPUTABLE",
                detail="peak 30-minute intensity I30 is not finite",
            ),
            max_depth,
        )
    return float(i30), max_depth


def _finalize_storm(
    active: _ActiveStorm,
    *,
    event_index: int,
    config: StormErosivityConfig,
    method_status: str,
) -> StormEventErosivity | None:
    """Finalize one candidate storm; return ``None`` only for clean sub-threshold rain."""
    intervals = active.storm_intervals
    start_time = intervals[0].timestamp
    end_time = intervals[-1].timestamp
    interval_count = len(intervals)
    has_missing = bool(active.missing_reasons)
    broken_gap = active.continuity_gap is not None

    if has_missing or broken_gap:
        parts: list[str] = []
        if active.missing_reasons:
            first_detail = active.missing_reasons[0].detail or "missing interval"
            parts.append(
                f"{len(active.missing_reasons)} missing interval(s) in active storm "
                f"starting {start_time.isoformat()} (first: {first_detail})"
            )
        if active.continuity_gap is not None:
            gap_start, gap_end = active.continuity_gap
            parts.append(
                f"continuity gap between {gap_start.isoformat()} and "
                f"{gap_end.isoformat()} broke active storm"
            )
        missing_obj = ResultMissing(reason="MISSING_INPUT", detail="; ".join(parts))
        return StormEventErosivity(
            event_index=event_index,
            start_time=start_time,
            end_time=end_time,
            interval_count=interval_count,
            total_depth_mm=missing_obj,
            total_energy_mj_ha=missing_obj,
            i30_mm_h=missing_obj,
            ei30=missing_obj,
            anchored_ei30=anchor_erosivity(missing_obj, config=config),
            ei30_unit=EI30_UNIT,
            provenance=None,
            method_status=method_status,
            has_missing_intervals=has_missing,
            broken_by_continuity_gap=broken_gap,
        )

    if active.not_computable_reasons:
        first_bad = active.not_computable_reasons[0]
        bad_obj = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"{len(active.not_computable_reasons)} invalid interval(s) in storm "
                f"starting {start_time.isoformat()} "
                f"(first: {first_bad.detail or 'non-computable precipitation'})"
            ),
        )
        return StormEventErosivity(
            event_index=event_index,
            start_time=start_time,
            end_time=end_time,
            interval_count=interval_count,
            total_depth_mm=bad_obj,
            total_energy_mj_ha=bad_obj,
            i30_mm_h=bad_obj,
            ei30=bad_obj,
            anchored_ei30=anchor_erosivity(bad_obj, config=config),
            ei30_unit=EI30_UNIT,
            provenance=None,
            method_status=method_status,
            has_missing_intervals=False,
            broken_by_continuity_gap=False,
        )

    depths = [float(item.precipitation_mm) for item in intervals]  # type: ignore[arg-type]
    total_depth = math.fsum(depths)
    if not math.isfinite(total_depth):
        overflow_obj = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"storm depth starting {start_time.isoformat()} is not finite",
        )
        return StormEventErosivity(
            event_index=event_index,
            start_time=start_time,
            end_time=end_time,
            interval_count=interval_count,
            total_depth_mm=overflow_obj,
            total_energy_mj_ha=overflow_obj,
            i30_mm_h=overflow_obj,
            ei30=overflow_obj,
            anchored_ei30=anchor_erosivity(overflow_obj, config=config),
            ei30_unit=EI30_UNIT,
            provenance=None,
            method_status=method_status,
            has_missing_intervals=False,
            broken_by_continuity_gap=False,
        )

    if total_depth < config.min_event_depth_mm:
        return None

    step_hours = config.step_minutes / MINUTES_PER_HOUR
    energies: list[float] = []
    for depth in depths:
        intensity = depth / step_hours
        if not math.isfinite(intensity):
            bad_i = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"storm intensity starting {start_time.isoformat()} is not finite",
            )
            return StormEventErosivity(
                event_index=event_index,
                start_time=start_time,
                end_time=end_time,
                interval_count=interval_count,
                total_depth_mm=total_depth,
                total_energy_mj_ha=bad_i,
                i30_mm_h=bad_i,
                ei30=bad_i,
                anchored_ei30=anchor_erosivity(bad_i, config=config),
                ei30_unit=EI30_UNIT,
                provenance=None,
                method_status=method_status,
                has_missing_intervals=False,
                broken_by_continuity_gap=False,
            )
        try:
            e_j = unit_kinetic_energy(intensity, config=config)
        except ValueError as exc:
            bad_e = ResultMissing(reason="NOT_COMPUTABLE", detail=str(exc))
            return StormEventErosivity(
                event_index=event_index,
                start_time=start_time,
                end_time=end_time,
                interval_count=interval_count,
                total_depth_mm=total_depth,
                total_energy_mj_ha=bad_e,
                i30_mm_h=bad_e,
                ei30=bad_e,
                anchored_ei30=anchor_erosivity(bad_e, config=config),
                ei30_unit=EI30_UNIT,
                provenance=None,
                method_status=method_status,
                has_missing_intervals=False,
                broken_by_continuity_gap=False,
            )
        energies.append(e_j * depth)

    total_energy = math.fsum(energies)
    if not math.isfinite(total_energy):
        bad_energy: float | ResultMissing = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"total kinetic energy for storm {start_time.isoformat()} is not finite",
        )
    else:
        bad_energy = float(total_energy)

    i30_result, _ = _compute_i30(depths, config.step_minutes)
    if isinstance(bad_energy, ResultMissing):
        ei30_val: float | ResultMissing = bad_energy
    elif isinstance(i30_result, ResultMissing):
        ei30_val = i30_result
    else:
        product = bad_energy * i30_result
        if not math.isfinite(product):
            ei30_val = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"EI30 for storm {start_time.isoformat()} is not finite",
            )
        else:
            ei30_val = float(product)

    provenance = None if isinstance(ei30_val, ResultMissing) else PROVENANCE_DERIVED
    return StormEventErosivity(
        event_index=event_index,
        start_time=start_time,
        end_time=end_time,
        interval_count=interval_count,
        total_depth_mm=float(total_depth),
        total_energy_mj_ha=bad_energy,
        i30_mm_h=i30_result,
        ei30=ei30_val,
        anchored_ei30=anchor_erosivity(ei30_val, config=config),
        ei30_unit=EI30_UNIT,
        provenance=provenance,
        method_status=method_status,
        has_missing_intervals=False,
        broken_by_continuity_gap=False,
    )


def _summarize_total_ei30(
    *,
    events: list[StormEventErosivity],
    series_missing: list[ResultMissing],
    series_not_computable: list[ResultMissing],
    continuity_gaps: tuple[tuple[dt.datetime, dt.datetime], ...],
) -> float | ResultMissing:
    """Aggregate event ``EI30`` values with strict G4/C3.3 missing propagation."""
    missing_reasons = [
        item for item in series_missing if item.reason == "MISSING_INPUT"
    ]
    missing_events = [
        ev.ei30
        for ev in events
        if isinstance(ev.ei30, ResultMissing) and ev.ei30.reason == "MISSING_INPUT"
    ]
    if missing_reasons or continuity_gaps or missing_events:
        details: list[str] = []
        if missing_reasons:
            details.append(
                f"{len(missing_reasons)} missing precipitation interval(s) "
                f"(first: {missing_reasons[0].detail})"
            )
        if continuity_gaps:
            first_start, first_end = continuity_gaps[0]
            details.append(
                f"{len(continuity_gaps)} continuity gap(s) "
                f"(first: {first_start.isoformat()} to {first_end.isoformat()})"
            )
        if missing_events and not missing_reasons and not continuity_gaps:
            details.append(missing_events[0].detail or "missing storm event")
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(details))

    not_comp_events = [
        ev.ei30
        for ev in events
        if isinstance(ev.ei30, ResultMissing) and ev.ei30.reason == "NOT_COMPUTABLE"
    ]
    if series_not_computable or not_comp_events:
        first_bad = (
            series_not_computable[0] if series_not_computable else not_comp_events[0]
        )
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=first_bad.detail or "non-computable interval or storm EI30",
        )

    total = math.fsum(
        ev.ei30 for ev in events if not isinstance(ev.ei30, ResultMissing)
    )
    if not math.isfinite(total):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="total EI30 across events is not finite",
        )
    return float(total)


def compute_storm_erosivity(
    intervals: Sequence[StormInterval],
    *,
    config: StormErosivityConfig,
) -> StormErosivitySummary:
    """Separate sub-hourly storms, compute ``EI30``, and apply optional anchoring.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Args:
        intervals: Chronologically ordered ``StormInterval`` sequence at
            ``config.step_minutes`` resolution.
        config: Caller-supplied ``StormErosivityConfig`` (keyword-only, no
            default).

    Returns:
        ``StormErosivitySummary`` containing per-event ``StormEventErosivity``
        records, total/anchored ``EI30`` (or typed ``Missing``), calibration
        status, and explicit continuity-gap diagnostics.
    """
    if not isinstance(config, StormErosivityConfig):
        raise TypeError(
            f"config: expected StormErosivityConfig, got {type(config).__name__} (G5)"
        )
    items, continuity_gaps = _validate_intervals(intervals, config.step_minutes)
    method_status, calibration_label = _status_labels(config.uruguay_calibrated)

    if not items:
        no_cov = ResultMissing(
            reason="NO_COVERAGE",
            detail="no sub-hourly precipitation intervals were provided (C5.5)",
        )
        return StormErosivitySummary(
            events=(),
            total_ei30=no_cov,
            anchored_total_ei30=anchor_erosivity(no_cov, config=config),
            ei30_unit=EI30_UNIT,
            method_status=method_status,
            calibration_label=calibration_label,
            uruguay_calibrated=config.uruguay_calibrated,
            bias_correction_source=config.bias_correction_source,
            official_climatology_anchor_factor=config.official_climatology_anchor_factor,
            provenance=None,
            interval_count=0,
            missing_interval_count=0,
            continuity_gaps=(),
        )

    step_delta = dt.timedelta(minutes=config.step_minutes)
    events: list[StormEventErosivity] = []
    series_missing: list[ResultMissing] = []
    series_not_computable: list[ResultMissing] = []
    active: _ActiveStorm | None = None
    prev_ts: dt.datetime | None = None
    next_event_index = 1

    for item in items:
        if (
            prev_ts is not None
            and (item.timestamp - prev_ts) > step_delta
            and active is not None
        ):
            active.continuity_gap = (prev_ts, item.timestamp)
            finalized = _finalize_storm(
                active,
                event_index=next_event_index,
                config=config,
                method_status=method_status,
            )
            if finalized is not None:
                events.append(finalized)
                next_event_index += 1
            active = None

        parsed = _classify_interval(item)
        if isinstance(parsed, ResultMissing):
            if parsed.reason == "MISSING_INPUT":
                series_missing.append(parsed)
            else:
                series_not_computable.append(parsed)
            if active is not None:
                active.append_wet_or_internal(item, parsed)
        elif parsed > 0.0:
            if active is None:
                active = _ActiveStorm(
                    storm_intervals=[item],
                    pending_dry=[],
                    missing_reasons=[],
                    not_computable_reasons=[],
                )
            else:
                active.append_wet_or_internal(item, parsed)
        else:
            # Dry interval (parsed == 0.0): advances dry gap counter if storm active.
            if active is not None:
                active.pending_dry.append(item)
                if len(active.pending_dry) >= config.min_dry_gap_intervals:
                    finalized = _finalize_storm(
                        active,
                        event_index=next_event_index,
                        config=config,
                        method_status=method_status,
                    )
                    if finalized is not None:
                        events.append(finalized)
                        next_event_index += 1
                    active = None

        prev_ts = item.timestamp

    if active is not None:
        finalized = _finalize_storm(
            active,
            event_index=next_event_index,
            config=config,
            method_status=method_status,
        )
        if finalized is not None:
            events.append(finalized)

    total_ei30 = _summarize_total_ei30(
        events=events,
        series_missing=series_missing,
        series_not_computable=series_not_computable,
        continuity_gaps=continuity_gaps,
    )
    anchored_total = anchor_erosivity(total_ei30, config=config)
    provenance = None if isinstance(total_ei30, ResultMissing) else PROVENANCE_DERIVED
    return StormErosivitySummary(
        events=tuple(events),
        total_ei30=total_ei30,
        anchored_total_ei30=anchored_total,
        ei30_unit=EI30_UNIT,
        method_status=method_status,
        calibration_label=calibration_label,
        uruguay_calibrated=config.uruguay_calibrated,
        bias_correction_source=config.bias_correction_source,
        official_climatology_anchor_factor=config.official_climatology_anchor_factor,
        provenance=provenance,
        interval_count=len(items),
        missing_interval_count=len(series_missing),
        continuity_gaps=continuity_gaps,
    )
