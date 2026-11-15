"""Dynamic and segmented RUSLE slope-length and steepness factor ``LS``. PROPOSED.

This module extends the single-slope factors ``S`` and ``L`` of
``engine.erosion.ls`` to:

1. **Segmented irregular hillslopes** (``dynamic_segmented_ls`` and
   ``dynamic_segmented_ls_steps``) via the ``PROPOSED`` Foster & Wischmeier
   (1974) / USDA AH703 / RUSLE2 segment accumulation rule with uniform
   segment length weighting.
2. **Time-varying periods** (``dynamic_ls_by_period``) evaluating one slope
   geometry per period while preserving period identifiers and ``Missing``
   propagation.

Equations and status (``PROPOSED``, blueprint section 3.7)
----------------------------------------------------------
For ``n`` hillslope segments ``i = 1, ..., n`` ordered from top to bottom with
positive lengths ``delta_i > 0`` (in metres), cumulative slope breaks
``lambda_0 = 0 < lambda_1 < ... < lambda_n = Lambda``, and segment steepnesses
``theta_i``:

- Each segment's steepness factor ``S_i`` and length factors
  ``L(lambda_i, theta_i)`` and ``L(lambda_{i-1}, theta_i)`` are computed by
  calling ``slope_steepness_factor`` and ``slope_length_factor`` from
  ``engine.erosion.ls`` directly (no ``S`` or ``L`` math is reimplemented here).
- By the Foster & Wischmeier (1974) / RUSLE2 segment accumulation rule, the
  segment ``LS_i`` over ``[lambda_{i-1}, lambda_i]`` is::

      LS_i = S_i * (lambda_i * L(lambda_i, theta_i)
                    - lambda_{i-1} * L(lambda_{i-1}, theta_i)) / delta_i

  where for the upslope segment (``lambda_0 = 0``), the lower-break term is
  zero so ``LS_1 = S_1 * L(lambda_1, theta_1)``.
- The effective hillslope ``LS`` uses uniform length weighting::

      LS = sum((delta_i / Lambda) * LS_i for i = 1..n)

  For a single segment (``n = 1``), this reproduces ``S * L`` from
  ``engine.erosion.ls`` identically. For a uniform slope split into arbitrary
  positive segments, the telescoping sum reproduces the unsegmented ``S * L``
  within floating-point rounding.

**Science review required:** This effective uniform segment weighting /
Foster & Wischmeier (1974) / RUSLE2 segment accumulation rule is ``PROPOSED``
and requires science review for concave/convex vs uniform hillslopes (in
particular, whether transport-capacity / deposition limits apply on sharply
flattening concave profiles).

Units and coefficients
----------------------
- **This module holds no coefficient and no numeric method constant.** All ten
  RUSLE ``S`` and ``L`` parameters (``a1`` to ``a4``, ``s_break``,
  ``lambda_unit``, ``b1`` to ``b4``) are keyword-only arguments with **no
  default values**.
- Segment lengths ``length_m`` and ``lambda_unit`` are both passed to
  ``engine.erosion.ls`` in metres (``"m"``); ``s_break`` is compared in the
  caller's ``slope_unit``.
- Pure functions (``contracts/ENTRYPOINTS.md`` G1): no file I/O, no network,
  no clock, and no input mutation.
- Missing or out-of-domain results follow G4 (``contracts/results/models.py``
  ``Missing`` with ``MISSING_INPUT`` or ``NOT_COMPUTABLE``); invalid caller
  types raise ``TypeError`` (G5).
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion.ls import (
    SlopeUnit,
    slope_length_factor,
    slope_steepness_factor,
)

__all__ = [
    "DynamicLsStep",
    "SlopeSegment",
    "dynamic_ls_by_period",
    "dynamic_segmented_ls",
    "dynamic_segmented_ls_steps",
]

NumberOrMissing = float | InputMissing | ResultMissing

_MISSING = (InputMissing, ResultMissing)
_METRE_UNIT = "m"


@dataclass(frozen=True)
class SlopeSegment:
    """One hillslope segment for segmented RUSLE ``LS``. PROPOSED.

    - ``length_m``: segment length in metres, or its ``Missing`` part.
    - ``steepness``: segment steepness in the caller's ``SlopeUnit``, or its
      ``Missing`` part.
    """

    length_m: NumberOrMissing
    steepness: NumberOrMissing


@dataclass(frozen=True)
class DynamicLsStep:
    """One segment accumulation step of ``dynamic_segmented_ls``. PROPOSED.

    - ``start_m``: cumulative slope length at the upslope break (m).
    - ``end_m``: cumulative slope length at the downslope break (m).
    - ``length_m``: segment length ``end_m - start_m`` (m).
    - ``steepness``: segment steepness in the caller's ``SlopeUnit``.
    - ``s_factor``: segment steepness factor ``S`` from ``slope_steepness_factor``.
    - ``segment_ls``: segment ``LS`` over ``[start_m, end_m]``.
    - ``weight``: uniform length weight ``length_m / total_length_m``.
    """

    start_m: float
    end_m: float
    length_m: float
    steepness: float
    s_factor: float
    segment_ls: float
    weight: float


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


def _check_slope_unit(name: str, unit: object) -> None:
    if not isinstance(unit, SlopeUnit):
        raise TypeError(f"{name}: expected a SlopeUnit, got {type(unit).__name__}")


def _check_scalar_types(slope_unit: object, scalars: Mapping[str, object]) -> None:
    _check_slope_unit("slope_unit", slope_unit)
    for name, item in scalars.items():
        _check_number_or_missing(name, item)


def _check_segments_types(segments: object) -> None:
    if isinstance(segments, (str, bytes)) or not isinstance(segments, Sequence):
        raise TypeError(
            f"segments: expected a sequence of SlopeSegment, got {type(segments).__name__}"
        )
    for index, segment in enumerate(segments):
        if not isinstance(segment, SlopeSegment):
            raise TypeError(
                f"segments[{index}]: expected SlopeSegment, got {type(segment).__name__}"
            )
        _check_number_or_missing(f"segments[{index}].length_m", segment.length_m)
        _check_number_or_missing(f"segments[{index}].steepness", segment.steepness)


def _check_periods_types(periods: object) -> None:
    if isinstance(periods, (str, bytes)) or not isinstance(periods, Sequence):
        raise TypeError(
            "periods: expected a sequence of (period_id, length_m, steepness) "
            f"tuples, got {type(periods).__name__}"
        )
    for index, entry in enumerate(periods):
        if not isinstance(entry, tuple):
            raise TypeError(
                f"periods[{index}]: expected a 3-tuple (period_id, length_m, "
                f"steepness), got {type(entry).__name__}"
            )
        try:
            period_id, length_m, steepness = entry
        except ValueError as exc:
            raise TypeError(
                f"periods[{index}]: expected a 3-tuple (period_id, length_m, "
                f"steepness), got tuple of length {len(entry)}"
            ) from exc
        try:
            hash(period_id)
        except TypeError as exc:
            raise TypeError(
                f"periods[{index}][0]: period_id must be Hashable, got "
                f"{type(period_id).__name__}"
            ) from exc
        _check_number_or_missing(f"periods[{index}].length_m", length_m)
        _check_number_or_missing(f"periods[{index}].steepness", steepness)


def _describe_missing(name: str, item: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {item.reason}"
    if item.detail is not None:
        text += f": {item.detail}"
    return text


def _finite(item: float) -> float | None:
    """Convert a number to a finite float, or ``None`` if non-finite/overflow."""
    try:
        number = float(item)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _collect_inputs(
    scalars: Mapping[str, object],
    segments: Sequence[SlopeSegment],
) -> tuple[dict[str, float], list[tuple[float, float]]] | ResultMissing:
    """Validate G4 missing inputs, finiteness, and positive/monotonic geometry."""
    absent: list[str] = []
    for name, item in scalars.items():
        if isinstance(item, _MISSING):
            absent.append(_describe_missing(name, item))
    for index, segment in enumerate(segments):
        if isinstance(segment.length_m, _MISSING):
            absent.append(
                _describe_missing(f"segments[{index}].length_m", segment.length_m)
            )
        if isinstance(segment.steepness, _MISSING):
            absent.append(
                _describe_missing(f"segments[{index}].steepness", segment.steepness)
            )
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))

    if len(segments) == 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="segments must not be empty",
        )

    scalar_values: dict[str, float] = {}
    not_finite: list[str] = []
    for name, item in scalars.items():
        value = _finite(item)  # type: ignore[arg-type]
        if value is None:
            not_finite.append(name)
        else:
            scalar_values[name] = value

    segment_values: list[tuple[float, float]] = []
    for index, segment in enumerate(segments):
        seg_length = _finite(segment.length_m)  # type: ignore[arg-type]
        seg_steepness = _finite(segment.steepness)  # type: ignore[arg-type]
        if seg_length is None:
            not_finite.append(f"segments[{index}].length_m")
        if seg_steepness is None:
            not_finite.append(f"segments[{index}].steepness")
        if seg_length is not None and seg_steepness is not None:
            segment_values.append((seg_length, seg_steepness))

    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )

    if scalar_values["lambda_unit"] <= 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"lambda_unit must be positive, got {scalar_values['lambda_unit']}",
        )

    cum_start = float(0)
    for index, (seg_length, _) in enumerate(segment_values):
        if seg_length <= 0:
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"segments[{index}].length_m must be positive, got {seg_length}",
            )
        cum_end = cum_start + seg_length
        if not math.isfinite(cum_end) or cum_end <= cum_start:
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"segments[{index}]: cumulative slope breaks must be "
                    "strictly monotonic and finite"
                ),
            )
        cum_start = cum_end

    return scalar_values, segment_values


def dynamic_segmented_ls_steps(
    segments: Sequence[SlopeSegment],
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
) -> tuple[DynamicLsStep, ...] | ResultMissing:
    """Compute per-segment Foster-Wischmeier ``DynamicLsStep`` entries. PROPOSED.

    All keyword arguments have no defaults and match ``engine.erosion.ls``.
    """
    scalars: dict[str, object] = {
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
    _check_scalar_types(slope_unit, scalars)
    _check_segments_types(segments)

    resolved = _collect_inputs(scalars, segments)
    if isinstance(resolved, ResultMissing):
        return resolved
    values, segment_values = resolved

    try:
        total_length = math.fsum(length for length, _ in segment_values)
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="total slope length is not a finite positive number",
        )
    if not math.isfinite(total_length) or total_length <= 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="total slope length is not a finite positive number",
        )

    steps: list[DynamicLsStep] = []
    cum_start = float(0)
    for index, (seg_length, seg_steepness) in enumerate(segment_values):
        cum_end = cum_start + seg_length
        s_factor = slope_steepness_factor(
            slope_steepness=seg_steepness,
            slope_unit=slope_unit,
            s_break=values["s_break"],
            s_break_unit=slope_unit,
            a1=values["a1"],
            a2=values["a2"],
            a3=values["a3"],
            a4=values["a4"],
        )
        if isinstance(s_factor, ResultMissing):
            return s_factor

        l_end = slope_length_factor(
            slope_length=cum_end,
            slope_length_unit=_METRE_UNIT,
            lambda_unit=values["lambda_unit"],
            lambda_unit_unit=_METRE_UNIT,
            slope_steepness=seg_steepness,
            slope_unit=slope_unit,
            b1=values["b1"],
            b2=values["b2"],
            b3=values["b3"],
            b4=values["b4"],
        )
        if isinstance(l_end, ResultMissing):
            return l_end

        try:
            if cum_start == 0:
                segment_ls = s_factor * l_end
            else:
                l_start = slope_length_factor(
                    slope_length=cum_start,
                    slope_length_unit=_METRE_UNIT,
                    lambda_unit=values["lambda_unit"],
                    lambda_unit_unit=_METRE_UNIT,
                    slope_steepness=seg_steepness,
                    slope_unit=slope_unit,
                    b1=values["b1"],
                    b2=values["b2"],
                    b3=values["b3"],
                    b4=values["b4"],
                )
                if isinstance(l_start, ResultMissing):
                    return l_start
                segment_ls = s_factor * (
                    (cum_end * l_end - cum_start * l_start) / seg_length
                )
            weight = seg_length / total_length
        except ArithmeticError:
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"segments[{index}]: segment LS or weight is not a finite "
                    "real number"
                ),
            )

        if not math.isfinite(segment_ls) or not math.isfinite(weight):
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"segments[{index}]: segment LS or weight is not a finite "
                    "real number"
                ),
            )
        steps.append(
            DynamicLsStep(
                start_m=cum_start,
                end_m=cum_end,
                length_m=seg_length,
                steepness=seg_steepness,
                s_factor=s_factor,
                segment_ls=segment_ls,
                weight=weight,
            )
        )
        cum_start = cum_end

    return tuple(steps)


def dynamic_segmented_ls(
    segments: Sequence[SlopeSegment],
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
) -> float | ResultMissing:
    """Effective length-weighted Foster-Wischmeier RUSLE ``LS``. PROPOSED.

    Reuses ``slope_steepness_factor`` and ``slope_length_factor`` from
    ``engine.erosion.ls`` without reimplementing ``S`` or ``L`` equations.
    For a single segment, reproduces ``L * S`` from ``engine.erosion.ls``
    directly. Needs science review for concave/convex vs uniform hillslopes.
    """
    steps = dynamic_segmented_ls_steps(
        segments,
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
    if isinstance(steps, ResultMissing):
        return steps
    if len(steps) == 1:
        return steps[0].segment_ls
    try:
        effective_ls = math.fsum(step.weight * step.segment_ls for step in steps)
    except ArithmeticError:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="dynamic_segmented_ls: weighted LS is not a finite real number",
        )
    if not math.isfinite(effective_ls):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="dynamic_segmented_ls: weighted LS is not a finite real number",
        )
    return effective_ls


def dynamic_ls_by_period(
    periods: Sequence[tuple[Hashable, NumberOrMissing, NumberOrMissing]],
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
) -> tuple[tuple[Hashable, float | ResultMissing], ...]:
    """Evaluate time-varying ``LS`` across periods ``(period_id, length_m, steepness)``. PROPOSED.

    Each period is evaluated independently via ``dynamic_segmented_ls`` so a
    ``Missing`` or non-computable period yields ``(period_id, ResultMissing)``
    without invalidating other valid periods.
    """
    scalars: dict[str, object] = {
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
    _check_scalar_types(slope_unit, scalars)
    _check_periods_types(periods)

    results: list[tuple[Hashable, float | ResultMissing]] = []
    for period_id, length_m, steepness in periods:
        value = dynamic_segmented_ls(
            (SlopeSegment(length_m=length_m, steepness=steepness),),
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
        results.append((period_id, value))
    return tuple(results)
