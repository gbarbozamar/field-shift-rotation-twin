"""Parametric pedotransfer function evaluator and soil-profile AWC integrator.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). This module is
standalone and is not wired into ``engine/water/__init__.py``, EP3, or the API
runner; nothing here takes effect until people approve it.

Implements:
- ``evaluate_pedotransfer_layer``: evaluates volumetric field capacity (FC),
  permanent wilting point (PWP), available water capacity (AWC = FC - PWP),
  total porosity, and uncertainty ranges ``[low, high]`` for a single soil
  horizon from caller-supplied horizon properties and a caller-supplied
  ``PedotransferModelSpec``.
- ``evaluate_profile_awc``: integrates available water (mm) across soil
  horizons with known effective layer depths (and optional rooting depth cap).

Rev13 rules enforced:
1. **Source hierarchy:** tracks three distinct source tags
   (``"MEASURED_LOCAL_PROFILE"``, ``"DERIVED_PEDOTRANSFER"``,
   ``"PRIOR_REGIONAL_MAP"`` — e.g. regional soil grid or polygon priors).
   A regional map prior is never promoted to ``"MEASURED_LOCAL_PROFILE"`` or
   ``"DERIVED_PEDOTRANSFER"``, and ``is_lab_measured`` is ``True`` only for
   ``"MEASURED_LOCAL_PROFILE"`` water measurements.
2. **Texture and hydraulic sanity:** checks
   ``abs((sand_pct + silt_pct + clay_pct) - 100) <= tolerance`` and
   ``0 <= pwp < fc <= porosity <= 1``; violations yield
   ``Missing(reason="CONTROL_FAILED", ...)`` (or ``"NOT_COMPUTABLE"`` for
   non-finite values).
3. **Explicit soil-depth requirement:** computing total profile available
   water in ``mm`` requires known effective layer depths (and known rooting
   depth when supplied). If any layer depth is ``None`` or ``Missing``, total
   profile AWC MUST return ``Missing(reason="MISSING_INPUT", detail=...)``,
   never ``0.0`` and never a guessed depth.
4. **Zero hardcoded empirical regression coefficients:** every regression
   intercept, polynomial term coefficient, particle density, texture-sum
   tolerance, and uncertainty delta is supplied by the caller in
   ``PedotransferModelSpec``.

Pure function (G1): pure Python 3.12 stdlib plus ``contracts.results.models``;
no file access, no network call, no clock, no environment variable, no global
mutable state, and arguments are never modified.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from contracts.results.models import Missing, ProvenanceLabel, Range

__all__ = [
    "FEATURE_NAMES",
    "SOIL_SOURCE_TAGS",
    "FeatureName",
    "HorizonInput",
    "LayerWaterProperties",
    "PedotransferModelSpec",
    "ProfileAwcResult",
    "PtfTerm",
    "RetentionEquationSpec",
    "SoilSourceTag",
    "UncertaintySpec",
    "evaluate_pedotransfer_layer",
    "evaluate_profile_awc",
]

SoilSourceTag = Literal[
    "MEASURED_LOCAL_PROFILE",
    "DERIVED_PEDOTRANSFER",
    "PRIOR_REGIONAL_MAP",
]
SOIL_SOURCE_TAGS: tuple[str, ...] = get_args(SoilSourceTag)

# Hierarchy rank from highest locality (0) to regional prior (2).
_SOURCE_HIERARCHY_RANK: dict[str, int] = {
    "MEASURED_LOCAL_PROFILE": 0,
    "DERIVED_PEDOTRANSFER": 1,
    "PRIOR_REGIONAL_MAP": 2,
}

FeatureName = Literal[
    "sand_pct",
    "silt_pct",
    "clay_pct",
    "organic_matter_pct",
    "bulk_density",
]
FEATURE_NAMES: tuple[str, ...] = get_args(FeatureName)

UNIT_VOLUMETRIC = "m3 m-3"
UNIT_DEPTH_MM = "mm"

_PERCENT_SUM = 100.0
_ZERO = 0.0
_ONE = 1.0


@dataclass(frozen=True)
class PtfTerm:
    """One additive regression term ``coefficient * prod(feature ** power)``.

    Caller supplies ``coefficient`` (never hardcoded). ``factors`` is a tuple
    of ``(feature_name, integer_power)`` pairs with ``integer_power >= 1``.
    """

    coefficient: float | Missing
    factors: tuple[tuple[FeatureName, int], ...] = ()


@dataclass(frozen=True)
class RetentionEquationSpec:
    """Parametric equation for one volumetric water content (FC or PWP).

    Evaluates ``intercept + sum(term.coefficient * prod(x ** p))``. All
    coefficients are caller-supplied with no defaults.
    """

    intercept: float | Missing
    terms: tuple[PtfTerm, ...]

    @classmethod
    def from_linear(
        cls,
        *,
        intercept: float | Missing,
        sand_pct: float | Missing = _ZERO,
        silt_pct: float | Missing = _ZERO,
        clay_pct: float | Missing = _ZERO,
        organic_matter_pct: float | Missing = _ZERO,
        bulk_density: float | Missing = _ZERO,
    ) -> RetentionEquationSpec:
        """Build a linear equation over the five standard horizon properties."""
        return cls(
            intercept=intercept,
            terms=(
                PtfTerm(coefficient=sand_pct, factors=(("sand_pct", 1),)),
                PtfTerm(coefficient=silt_pct, factors=(("silt_pct", 1),)),
                PtfTerm(coefficient=clay_pct, factors=(("clay_pct", 1),)),
                PtfTerm(
                    coefficient=organic_matter_pct,
                    factors=(("organic_matter_pct", 1),),
                ),
                PtfTerm(coefficient=bulk_density, factors=(("bulk_density", 1),)),
            ),
        )


@dataclass(frozen=True)
class UncertaintySpec:
    """Caller-supplied uncertainty deltas for volumetric FC, PWP, and AWC (C2.1-C2.3).

    All deltas are non-negative numbers in volumetric water content units
    (``m3 m-3``), or ``Missing`` when unavailable. By C2.2, a range is never
    invented or narrowed by default (``clamp_to_physical_bounds=False``).
    """

    kind: str
    fc_lower_delta: float | Missing
    fc_upper_delta: float | Missing
    pwp_lower_delta: float | Missing
    pwp_upper_delta: float | Missing
    awc_lower_delta: float | Missing
    awc_upper_delta: float | Missing
    clamp_to_physical_bounds: bool = False

    @classmethod
    def symmetric(
        cls,
        *,
        kind: str,
        fc_half_width: float | Missing,
        pwp_half_width: float | Missing,
        awc_half_width: float | Missing,
        clamp_to_physical_bounds: bool = False,
    ) -> UncertaintySpec:
        """Build a symmetric uncertainty specification from caller half-widths."""
        return cls(
            kind=kind,
            fc_lower_delta=fc_half_width,
            fc_upper_delta=fc_half_width,
            pwp_lower_delta=pwp_half_width,
            pwp_upper_delta=pwp_half_width,
            awc_lower_delta=awc_half_width,
            awc_upper_delta=awc_half_width,
            clamp_to_physical_bounds=clamp_to_physical_bounds,
        )


@dataclass(frozen=True)
class PedotransferModelSpec:
    """Caller-supplied pedotransfer model specification (zero hardcoded parameters).

    Every empirical parameter — equations for field capacity and wilting point,
    ``particle_density`` (for total porosity ``1 - bulk_density / particle_density``),
    ``texture_sum_tolerance_pct``, and ``uncertainty`` — comes from the caller.
    """

    model_id: str
    field_capacity_eq: RetentionEquationSpec
    wilting_point_eq: RetentionEquationSpec
    particle_density: float | Missing
    texture_sum_tolerance_pct: float | Missing
    uncertainty: UncertaintySpec | None = None


@dataclass(frozen=True)
class HorizonInput:
    """Input properties for one soil horizon.

    - ``layer_id``: non-blank layer label used in diagnostics.
    - ``sand_pct``, ``silt_pct``, ``clay_pct``, ``organic_matter_pct``:
      mass percentages in ``[0, 100]``.
    - ``bulk_density``: dry bulk density in the same mass-per-volume unit as
      ``PedotransferModelSpec.particle_density``.
    - ``source_tag``: primary Rev13 source classification for the horizon inputs.
    - ``source_detail``: non-blank attribution string naming the source.
    - ``effective_depth_mm``: effective thickness of the horizon in ``mm``, or
      ``None`` / ``Missing`` when unknown.
    - ``property_sources``: optional per-property source tags when properties of
      one horizon originate from different tiers (e.g. lab texture paired with
      a regional soil map prior for SOC/BD).
    """

    layer_id: str
    sand_pct: float | Missing
    silt_pct: float | Missing
    clay_pct: float | Missing
    organic_matter_pct: float | Missing
    bulk_density: float | Missing
    source_tag: SoilSourceTag
    source_detail: str
    effective_depth_mm: float | None | Missing = None
    property_sources: tuple[tuple[FeatureName, SoilSourceTag], ...] | None = None


@dataclass(frozen=True)
class LayerWaterProperties:
    """Evaluated hydraulic properties of one soil horizon."""

    layer_id: str
    effective_depth_mm: float | None | Missing
    porosity: float | Missing
    field_capacity: float | Missing
    wilting_point: float | Missing
    available_water_capacity: float | Missing
    awc_mm: float | Missing
    unit_volumetric: str
    fc_range: Range | None
    fc_range_missing: Missing | None
    pwp_range: Range | None
    pwp_range_missing: Missing | None
    awc_range: Range | None
    awc_range_missing: Missing | None
    source_tag: SoilSourceTag
    input_source_tags: tuple[SoilSourceTag, ...]
    is_lab_measured: bool
    provenance: ProvenanceLabel | None
    source: str | None


@dataclass(frozen=True)
class ProfileAwcResult:
    """Integrated available water capacity (mm) across a soil profile."""

    total_awc_mm: float | Missing
    unit: str
    effective_depth_mm: float | Missing
    total_awc_range: Range | None
    total_awc_range_missing: Missing | None
    source_tag: SoilSourceTag | None
    layer_source_tags: tuple[SoilSourceTag, ...]
    is_lab_measured: bool
    provenance: ProvenanceLabel | None
    source: str | None
    layers: tuple[LayerWaterProperties, ...]
    layer_depths_used_mm: tuple[float, ...] | None


# ---------------------------------------------------------------------------
# Internal validation helpers (G5 caller defects vs G4 typed absences)


def _is_number(value: object) -> bool:
    """True for an ``int`` or ``float``, excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


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


def _validate_source_tag(name: str, value: object) -> SoilSourceTag:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value not in SOIL_SOURCE_TAGS:
        raise ValueError(
            f"{name}: unknown soil source tag {value!r}; expected one of {SOIL_SOURCE_TAGS} (G5)"
        )
    return value  # type: ignore[return-value]


def _check_numeric_or_missing(name: str, value: object) -> float | Missing:
    if isinstance(value, Missing):
        return value
    if not _is_number(value):
        raise TypeError(
            f"{name}: expected float, int, or Missing, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite(value):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{name} is not a finite number",
        )
    return float(value)


def _format_missing_item(name: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"{name} ({missing.reason})"
    return f"{name} ({missing.reason}: {missing.detail})"


def _weakest_source_tag(tags: Sequence[SoilSourceTag]) -> SoilSourceTag:
    return max(tags, key=lambda tag: _SOURCE_HIERARCHY_RANK[tag])


def _validate_equation_spec(name: str, eq: object) -> None:
    if not isinstance(eq, RetentionEquationSpec):
        raise TypeError(
            f"{name}: expected RetentionEquationSpec, got {type(eq).__name__} (G5)"
        )
    if not isinstance(eq.intercept, Missing) and not _is_number(eq.intercept):
        raise TypeError(
            f"{name}.intercept: expected float, int, or Missing, "
            f"got {type(eq.intercept).__name__} (G5)"
        )
    if not isinstance(eq.terms, tuple):
        raise TypeError(
            f"{name}.terms: expected tuple[PtfTerm, ...], got {type(eq.terms).__name__} (G5)"
        )
    for idx, term in enumerate(eq.terms):
        if not isinstance(term, PtfTerm):
            raise TypeError(
                f"{name}.terms[{idx}]: expected PtfTerm, got {type(term).__name__} (G5)"
            )
        if not isinstance(term.coefficient, Missing) and not _is_number(
            term.coefficient
        ):
            raise TypeError(
                f"{name}.terms[{idx}].coefficient: expected float, int, or Missing, "
                f"got {type(term.coefficient).__name__} (G5)"
            )
        if not isinstance(term.factors, tuple):
            raise TypeError(
                f"{name}.terms[{idx}].factors: expected tuple, "
                f"got {type(term.factors).__name__} (G5)"
            )
        for factor_idx, factor in enumerate(term.factors):
            if not isinstance(factor, tuple) or len(factor) != 2:
                raise TypeError(
                    f"{name}.terms[{idx}].factors[{factor_idx}]: expected (feature, power) pair (G5)"
                )
            feature, power = factor
            if not isinstance(feature, str):
                raise TypeError(
                    f"{name}.terms[{idx}].factors[{factor_idx}][0]: expected str, "
                    f"got {type(feature).__name__} (G5)"
                )
            if feature not in FEATURE_NAMES:
                raise ValueError(
                    f"{name}.terms[{idx}].factors[{factor_idx}]: unknown feature {feature!r}; "
                    f"expected one of {FEATURE_NAMES} (G5)"
                )
            if not _is_strict_int(power):
                raise TypeError(
                    f"{name}.terms[{idx}].factors[{factor_idx}][1]: expected int power, "
                    f"got {type(power).__name__} (G5)"
                )
            if power < 1:
                raise ValueError(
                    f"{name}.terms[{idx}].factors[{factor_idx}]: power must be >= 1, got {power} (G5)"
                )


def _validate_uncertainty_spec(uncertainty: object) -> None:
    if uncertainty is None:
        return
    if not isinstance(uncertainty, UncertaintySpec):
        raise TypeError(
            f"spec.uncertainty: expected UncertaintySpec or None, got {type(uncertainty).__name__} (G5)"
        )
    _require_non_blank_str("spec.uncertainty.kind", uncertainty.kind)
    if not isinstance(uncertainty.clamp_to_physical_bounds, bool):
        raise TypeError(
            "spec.uncertainty.clamp_to_physical_bounds: expected bool, "
            f"got {type(uncertainty.clamp_to_physical_bounds).__name__} (G5)"
        )
    for field_name in (
        "fc_lower_delta",
        "fc_upper_delta",
        "pwp_lower_delta",
        "pwp_upper_delta",
        "awc_lower_delta",
        "awc_upper_delta",
    ):
        val = getattr(uncertainty, field_name)
        if not isinstance(val, Missing) and not _is_number(val):
            raise TypeError(
                f"spec.uncertainty.{field_name}: expected float, int, or Missing, "
                f"got {type(val).__name__} (G5)"
            )


def _validate_spec(spec: object) -> None:
    if not isinstance(spec, PedotransferModelSpec):
        raise TypeError(
            f"spec: expected PedotransferModelSpec, got {type(spec).__name__} (G5)"
        )
    _require_non_blank_str("spec.model_id", spec.model_id)
    _validate_equation_spec("spec.field_capacity_eq", spec.field_capacity_eq)
    _validate_equation_spec("spec.wilting_point_eq", spec.wilting_point_eq)
    if not isinstance(spec.particle_density, Missing) and not _is_number(
        spec.particle_density
    ):
        raise TypeError(
            "spec.particle_density: expected float, int, or Missing, "
            f"got {type(spec.particle_density).__name__} (G5)"
        )
    if not isinstance(spec.texture_sum_tolerance_pct, Missing) and not _is_number(
        spec.texture_sum_tolerance_pct
    ):
        raise TypeError(
            "spec.texture_sum_tolerance_pct: expected float, int, or Missing, "
            f"got {type(spec.texture_sum_tolerance_pct).__name__} (G5)"
        )
    _validate_uncertainty_spec(spec.uncertainty)


def _validate_horizon(
    horizon: object,
) -> tuple[SoilSourceTag, tuple[SoilSourceTag, ...]]:
    if not isinstance(horizon, HorizonInput):
        raise TypeError(
            f"horizon: expected HorizonInput, got {type(horizon).__name__} (G5)"
        )
    _require_non_blank_str("horizon.layer_id", horizon.layer_id)
    _require_non_blank_str("horizon.source_detail", horizon.source_detail)
    primary_tag = _validate_source_tag("horizon.source_tag", horizon.source_tag)

    for field_name in FEATURE_NAMES:
        val = getattr(horizon, field_name)
        if not isinstance(val, Missing) and not _is_number(val):
            raise TypeError(
                f"horizon.{field_name}: expected float, int, or Missing, "
                f"got {type(val).__name__} (G5)"
            )

    depth = horizon.effective_depth_mm
    if depth is not None and not isinstance(depth, Missing) and not _is_number(depth):
        raise TypeError(
            "horizon.effective_depth_mm: expected float, int, None, or Missing, "
            f"got {type(depth).__name__} (G5)"
        )

    distinct_tags: list[SoilSourceTag] = [primary_tag]
    if horizon.property_sources is not None:
        if not isinstance(horizon.property_sources, tuple):
            raise TypeError(
                "horizon.property_sources: expected tuple or None, "
                f"got {type(horizon.property_sources).__name__} (G5)"
            )
        seen_features: set[str] = set()
        for idx, item in enumerate(horizon.property_sources):
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError(
                    f"horizon.property_sources[{idx}]: expected (feature, source_tag) pair (G5)"
                )
            feature, tag_obj = item
            if not isinstance(feature, str):
                raise TypeError(
                    f"horizon.property_sources[{idx}][0]: expected str, "
                    f"got {type(feature).__name__} (G5)"
                )
            if feature not in FEATURE_NAMES:
                raise ValueError(
                    f"horizon.property_sources[{idx}]: unknown feature {feature!r}; "
                    f"expected one of {FEATURE_NAMES} (G5)"
                )
            if feature in seen_features:
                raise ValueError(
                    f"horizon.property_sources: duplicate source tag for feature {feature!r} (G5)"
                )
            seen_features.add(feature)
            tag = _validate_source_tag(f"horizon.property_sources[{idx}][1]", tag_obj)
            if tag not in distinct_tags:
                distinct_tags.append(tag)

    # Map horizon input source tags to output layer source tag:
    # - PRIOR_REGIONAL_MAP stays PRIOR_REGIONAL_MAP (never promoted to lab/local PTF).
    # - MEASURED_LOCAL_PROFILE or DERIVED_PEDOTRANSFER inputs evaluated through a
    #   pedotransfer function become DERIVED_PEDOTRANSFER.
    weakest_input = _weakest_source_tag(distinct_tags)
    output_tag: SoilSourceTag = (
        "PRIOR_REGIONAL_MAP"
        if weakest_input == "PRIOR_REGIONAL_MAP"
        else "DERIVED_PEDOTRANSFER"
    )
    return output_tag, tuple(distinct_tags)


def _evaluate_equation(
    eq: RetentionEquationSpec,
    features: dict[str, float],
) -> float | Missing:
    assert not isinstance(eq.intercept, Missing)
    try:
        total = float(eq.intercept)
        for term in eq.terms:
            assert not isinstance(term.coefficient, Missing)
            product = float(term.coefficient)
            for feature, power in term.factors:
                product *= features[feature] ** power
            total += product
    except OverflowError:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="pedotransfer equation overflowed floating-point range",
        )
    if not _is_finite(total):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="pedotransfer equation produced a non-finite value",
        )
    return total


def _build_range(
    *,
    quantity: str,
    value: float,
    lower_delta_obj: float | Missing,
    upper_delta_obj: float | Missing,
    kind: str,
    clamp: bool,
    upper_physical_limit: float,
) -> tuple[Range | None, Missing | None]:
    if isinstance(lower_delta_obj, Missing) or isinstance(upper_delta_obj, Missing):
        missing_parts: list[str] = []
        if isinstance(lower_delta_obj, Missing):
            missing_parts.append(
                _format_missing_item(f"{quantity}_lower_delta", lower_delta_obj)
            )
        if isinstance(upper_delta_obj, Missing):
            missing_parts.append(
                _format_missing_item(f"{quantity}_upper_delta", upper_delta_obj)
            )
        return None, Missing(
            reason="MISSING_INPUT",
            detail=f"missing uncertainty bound(s) for {quantity}: {', '.join(missing_parts)}",
        )

    if not _is_finite(lower_delta_obj) or not _is_finite(upper_delta_obj):
        return None, Missing(
            reason="NOT_COMPUTABLE",
            detail=f"non-finite uncertainty delta for {quantity}",
        )

    lower_delta = float(lower_delta_obj)
    upper_delta = float(upper_delta_obj)
    if lower_delta < _ZERO or upper_delta < _ZERO:
        return None, Missing(
            reason="CONTROL_FAILED",
            detail=f"uncertainty deltas for {quantity} must be non-negative",
        )

    low = value - lower_delta
    high = value + upper_delta
    if clamp:
        low = max(_ZERO, low)
        high = min(upper_physical_limit, high)

    if not _is_finite(low) or not _is_finite(high):
        return None, Missing(
            reason="NOT_COMPUTABLE",
            detail=f"non-finite uncertainty bounds for {quantity}",
        )

    if low >= high:
        return None, Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"uncertainty range for {quantity} collapses to zero width "
                f"({low} == {high}, forbidden by C2.2)"
            ),
        )

    return Range(low=low, high=high, kind=kind), None


def _evaluate_effective_depth_mm(
    layer_id: str,
    depth: float | None | Missing,
) -> float | Missing:
    if depth is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"effective_depth_mm is None for layer '{layer_id}'; "
                "depth cannot be defaulted or guessed"
            ),
        )
    if isinstance(depth, Missing):
        return Missing(
            reason="MISSING_INPUT",
            detail=_format_missing_item(
                f"effective_depth_mm for layer '{layer_id}'", depth
            ),
        )
    if not _is_finite(depth):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"effective_depth_mm for layer '{layer_id}' is not finite",
        )
    depth_val = float(depth)
    if depth_val <= _ZERO:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"effective_depth_mm for layer '{layer_id}' must be > 0, got {depth_val}",
        )
    return depth_val


def _failed_layer(
    *,
    horizon: HorizonInput,
    output_tag: SoilSourceTag,
    input_tags: tuple[SoilSourceTag, ...],
    failure: Missing,
) -> LayerWaterProperties:
    return LayerWaterProperties(
        layer_id=horizon.layer_id,
        effective_depth_mm=horizon.effective_depth_mm,
        porosity=failure,
        field_capacity=failure,
        wilting_point=failure,
        available_water_capacity=failure,
        awc_mm=failure,
        unit_volumetric=UNIT_VOLUMETRIC,
        fc_range=None,
        fc_range_missing=None,
        pwp_range=None,
        pwp_range_missing=None,
        awc_range=None,
        awc_range_missing=None,
        source_tag=output_tag,
        input_source_tags=input_tags,
        is_lab_measured=False,
        provenance=None,
        source=None,
    )


def evaluate_pedotransfer_layer(
    horizon: HorizonInput,
    spec: PedotransferModelSpec,
) -> LayerWaterProperties:
    """Evaluate volumetric FC, PWP, AWC, porosity, and uncertainty for one horizon.

    All regression coefficients, particle density, texture-sum tolerance, and
    uncertainty bounds come from ``spec`` (zero hardcoded empirical constants).
    Returns typed ``Missing`` (C3.1/C3.2) on missing inputs, non-finite values,
    or failed sanity controls. Raises ``TypeError``/``ValueError`` only on
    caller contract defects (G5).
    """
    output_tag, input_tags = _validate_horizon(horizon)
    _validate_spec(spec)

    # 1. Check for Missing inputs in horizon and spec (G4, C3.3).
    missing_items: list[str] = []
    for field_name in FEATURE_NAMES:
        val = getattr(horizon, field_name)
        if isinstance(val, Missing):
            missing_items.append(_format_missing_item(field_name, val))

    if isinstance(spec.particle_density, Missing):
        missing_items.append(
            _format_missing_item("spec.particle_density", spec.particle_density)
        )
    if isinstance(spec.texture_sum_tolerance_pct, Missing):
        missing_items.append(
            _format_missing_item(
                "spec.texture_sum_tolerance_pct", spec.texture_sum_tolerance_pct
            )
        )
    for eq_name, eq in (
        ("field_capacity_eq", spec.field_capacity_eq),
        ("wilting_point_eq", spec.wilting_point_eq),
    ):
        if isinstance(eq.intercept, Missing):
            missing_items.append(
                _format_missing_item(f"spec.{eq_name}.intercept", eq.intercept)
            )
        for idx, term in enumerate(eq.terms):
            if isinstance(term.coefficient, Missing):
                missing_items.append(
                    _format_missing_item(
                        f"spec.{eq_name}.terms[{idx}].coefficient", term.coefficient
                    )
                )

    if missing_items:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"layer '{horizon.layer_id}' missing required input(s): "
                    + ", ".join(missing_items)
                ),
            ),
        )

    # 2. Check finiteness of numeric inputs and spec parameters (NOT_COMPUTABLE).
    non_finite_items: list[str] = []
    features: dict[str, float] = {}
    for field_name in FEATURE_NAMES:
        raw_val = getattr(horizon, field_name)
        if not _is_finite(raw_val):
            non_finite_items.append(field_name)
        else:
            features[field_name] = float(raw_val)

    for param_name, param_val in (
        ("spec.particle_density", spec.particle_density),
        ("spec.texture_sum_tolerance_pct", spec.texture_sum_tolerance_pct),
    ):
        assert not isinstance(param_val, Missing)
        if not _is_finite(param_val):
            non_finite_items.append(param_name)

    for eq_name, eq in (
        ("field_capacity_eq", spec.field_capacity_eq),
        ("wilting_point_eq", spec.wilting_point_eq),
    ):
        assert not isinstance(eq.intercept, Missing)
        if not _is_finite(eq.intercept):
            non_finite_items.append(f"spec.{eq_name}.intercept")
        for idx, term in enumerate(eq.terms):
            assert not isinstance(term.coefficient, Missing)
            if not _is_finite(term.coefficient):
                non_finite_items.append(f"spec.{eq_name}.terms[{idx}].coefficient")

    if non_finite_items:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"layer '{horizon.layer_id}' has non-finite value(s): "
                    + ", ".join(non_finite_items)
                ),
            ),
        )

    assert not isinstance(spec.particle_density, Missing)
    assert not isinstance(spec.texture_sum_tolerance_pct, Missing)
    particle_density = float(spec.particle_density)
    tolerance_pct = float(spec.texture_sum_tolerance_pct)

    # 3. Domain and texture-sum sanity controls (CONTROL_FAILED).
    if particle_density <= _ZERO:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"spec.particle_density must be > 0, got {particle_density}",
            ),
        )
    if tolerance_pct < _ZERO:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"spec.texture_sum_tolerance_pct must be >= 0, got {tolerance_pct}",
            ),
        )

    for pct_name in ("sand_pct", "silt_pct", "clay_pct", "organic_matter_pct"):
        pct_val = features[pct_name]
        if pct_val < _ZERO or pct_val > _PERCENT_SUM:
            return _failed_layer(
                horizon=horizon,
                output_tag=output_tag,
                input_tags=input_tags,
                failure=Missing(
                    reason="CONTROL_FAILED",
                    detail=(
                        f"layer '{horizon.layer_id}' {pct_name}={pct_val} "
                        f"must lie in [0, 100]"
                    ),
                ),
            )

    bulk_density = features["bulk_density"]
    if bulk_density <= _ZERO or bulk_density >= particle_density:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"layer '{horizon.layer_id}' bulk_density={bulk_density} "
                    f"must satisfy 0 < bulk_density < particle_density ({particle_density})"
                ),
            ),
        )

    texture_sum = features["sand_pct"] + features["silt_pct"] + features["clay_pct"]
    if abs(texture_sum - _PERCENT_SUM) > tolerance_pct:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"layer '{horizon.layer_id}' texture sum ({texture_sum:.6g}%) "
                    f"differs from 100% by more than tolerance ({tolerance_pct:.6g}%)"
                ),
            ),
        )

    # 4. Evaluate porosity, FC, PWP, and check 0 <= pwp < fc <= porosity <= 1.
    porosity = _ONE - (bulk_density / particle_density)
    if not _is_finite(porosity):
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail=f"layer '{horizon.layer_id}' porosity is not finite",
            ),
        )
    if porosity <= _ZERO or porosity > _ONE:
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=f"layer '{horizon.layer_id}' porosity={porosity} outside (0, 1]",
            ),
        )

    fc = _evaluate_equation(spec.field_capacity_eq, features)
    if isinstance(fc, Missing):
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=fc,
        )
    pwp = _evaluate_equation(spec.wilting_point_eq, features)
    if isinstance(pwp, Missing):
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=pwp,
        )

    if not (_ZERO <= pwp < fc <= porosity):
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"layer '{horizon.layer_id}' failed physical ordering "
                    f"0 <= pwp < fc <= porosity: pwp={pwp:.6g}, fc={fc:.6g}, "
                    f"porosity={porosity:.6g}"
                ),
            ),
        )

    awc = fc - pwp
    if not _is_finite(awc):
        return _failed_layer(
            horizon=horizon,
            output_tag=output_tag,
            input_tags=input_tags,
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail=f"layer '{horizon.layer_id}' available water capacity is not finite",
            ),
        )

    # 5. Evaluate uncertainty ranges (C2.1-C2.3).
    if spec.uncertainty is None:
        no_unc = Missing(
            reason="NOT_AVAILABLE",
            detail="no uncertainty specification supplied in PedotransferModelSpec",
        )
        fc_range, fc_range_missing = None, no_unc
        pwp_range, pwp_range_missing = None, no_unc
        awc_range, awc_range_missing = None, no_unc
    else:
        unc = spec.uncertainty
        fc_range, fc_range_missing = _build_range(
            quantity="field_capacity",
            value=fc,
            lower_delta_obj=unc.fc_lower_delta,
            upper_delta_obj=unc.fc_upper_delta,
            kind=unc.kind,
            clamp=unc.clamp_to_physical_bounds,
            upper_physical_limit=porosity,
        )
        pwp_range, pwp_range_missing = _build_range(
            quantity="wilting_point",
            value=pwp,
            lower_delta_obj=unc.pwp_lower_delta,
            upper_delta_obj=unc.pwp_upper_delta,
            kind=unc.kind,
            clamp=unc.clamp_to_physical_bounds,
            upper_physical_limit=porosity,
        )
        awc_range, awc_range_missing = _build_range(
            quantity="available_water_capacity",
            value=awc,
            lower_delta_obj=unc.awc_lower_delta,
            upper_delta_obj=unc.awc_upper_delta,
            kind=unc.kind,
            clamp=unc.clamp_to_physical_bounds,
            upper_physical_limit=porosity,
        )

    # 6. Evaluate layer AWC in mm only when effective_depth_mm is known.
    depth_checked = _evaluate_effective_depth_mm(
        horizon.layer_id, horizon.effective_depth_mm
    )
    if isinstance(depth_checked, Missing):
        awc_mm: float | Missing = depth_checked
    else:
        awc_mm_val = awc * depth_checked
        if not _is_finite(awc_mm_val):
            awc_mm = Missing(
                reason="NOT_COMPUTABLE",
                detail=f"layer '{horizon.layer_id}' awc_mm is not finite",
            )
        else:
            awc_mm = awc_mm_val

    return LayerWaterProperties(
        layer_id=horizon.layer_id,
        effective_depth_mm=horizon.effective_depth_mm,
        porosity=porosity,
        field_capacity=fc,
        wilting_point=pwp,
        available_water_capacity=awc,
        awc_mm=awc_mm,
        unit_volumetric=UNIT_VOLUMETRIC,
        fc_range=fc_range,
        fc_range_missing=fc_range_missing,
        pwp_range=pwp_range,
        pwp_range_missing=pwp_range_missing,
        awc_range=awc_range,
        awc_range_missing=awc_range_missing,
        source_tag=output_tag,
        input_source_tags=input_tags,
        is_lab_measured=False,
        provenance="DERIVED",
        source=(
            f"pedotransfer({spec.model_id}) [{output_tag}] from {horizon.source_detail}"
        ),
    )


def _missing_profile_result(
    *,
    failure: Missing,
    layers: tuple[LayerWaterProperties, ...],
    source_tag: SoilSourceTag | None,
    layer_source_tags: tuple[SoilSourceTag, ...],
) -> ProfileAwcResult:
    return ProfileAwcResult(
        total_awc_mm=failure,
        unit=UNIT_DEPTH_MM,
        effective_depth_mm=failure,
        total_awc_range=None,
        total_awc_range_missing=None,
        source_tag=source_tag,
        layer_source_tags=layer_source_tags,
        is_lab_measured=False,
        provenance=None,
        source=None,
        layers=layers,
        layer_depths_used_mm=None,
    )


def _validate_evaluated_layer(layer: LayerWaterProperties) -> Missing | None:
    _require_non_blank_str("layer.layer_id", layer.layer_id)
    _validate_source_tag("layer.source_tag", layer.source_tag)
    for field_name in (
        "porosity",
        "field_capacity",
        "wilting_point",
        "available_water_capacity",
    ):
        val = getattr(layer, field_name)
        if not isinstance(val, Missing) and not _is_number(val):
            raise TypeError(
                f"layer.{field_name}: expected float, int, or Missing, "
                f"got {type(val).__name__} (G5)"
            )
    if (
        not isinstance(layer.porosity, Missing)
        and not isinstance(layer.field_capacity, Missing)
        and not isinstance(layer.wilting_point, Missing)
    ):
        porosity = float(layer.porosity)
        fc = float(layer.field_capacity)
        pwp = float(layer.wilting_point)
        if not (_is_finite(porosity) and _is_finite(fc) and _is_finite(pwp)):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"layer '{layer.layer_id}' has non-finite hydraulic properties",
            )
        if not (_ZERO <= pwp < fc <= porosity <= _ONE):
            return Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"layer '{layer.layer_id}' failed physical ordering "
                    f"0 <= pwp < fc <= porosity <= 1: pwp={pwp:.6g}, fc={fc:.6g}, "
                    f"porosity={porosity:.6g}"
                ),
            )
    return None


def evaluate_profile_awc(
    horizons: Sequence[HorizonInput | LayerWaterProperties],
    spec: PedotransferModelSpec | None = None,
    *,
    rooting_depth_mm: float | Missing | None = None,
) -> ProfileAwcResult:
    """Integrate total profile available water (mm) over horizons with known depths.

    Every horizon in ``horizons`` MUST have a known positive finite
    ``effective_depth_mm``; if any horizon depth is ``None`` or ``Missing``,
    returns ``Missing(reason="MISSING_INPUT", detail=...)`` (never ``0.0`` and
    never a guessed depth). When ``rooting_depth_mm`` is provided, integrates
    from the surface down to ``rooting_depth_mm`` and returns ``Missing`` if the
    profile does not cover ``rooting_depth_mm``.
    """
    if isinstance(horizons, (str, bytes, bytearray)) or not isinstance(
        horizons, Sequence
    ):
        raise TypeError(
            f"horizons: expected Sequence of HorizonInput or LayerWaterProperties, "
            f"got {type(horizons).__name__} (G5)"
        )

    if spec is not None:
        _validate_spec(spec)

    if (
        rooting_depth_mm is not None
        and not isinstance(rooting_depth_mm, Missing)
        and not _is_number(rooting_depth_mm)
    ):
        raise TypeError(
            "rooting_depth_mm: expected float, int, None, or Missing, "
            f"got {type(rooting_depth_mm).__name__} (G5)"
        )

    evaluated_layers: list[LayerWaterProperties] = []
    pre_layer_failures: dict[int, Missing] = {}
    for idx, item in enumerate(horizons):
        if isinstance(item, HorizonInput):
            if spec is None:
                raise TypeError(
                    "spec: PedotransferModelSpec is required when horizons contain HorizonInput (G5)"
                )
            evaluated_layers.append(evaluate_pedotransfer_layer(item, spec))
        elif isinstance(item, LayerWaterProperties):
            maybe_failure = _validate_evaluated_layer(item)
            if maybe_failure is not None:
                pre_layer_failures[id(item)] = maybe_failure
            evaluated_layers.append(item)
        else:
            raise TypeError(
                f"horizons[{idx}]: expected HorizonInput or LayerWaterProperties, "
                f"got {type(item).__name__} (G5)"
            )

    layers_tuple = tuple(evaluated_layers)
    layer_tags = tuple(layer.source_tag for layer in layers_tuple)

    if not layers_tuple:
        return _missing_profile_result(
            failure=Missing(
                reason="MISSING_INPUT",
                detail="no soil horizons provided to evaluate_profile_awc",
            ),
            layers=layers_tuple,
            source_tag=None,
            layer_source_tags=layer_tags,
        )

    profile_tag = _weakest_source_tag(layer_tags)

    # Check rooting_depth_mm first if provided as Missing/non-finite/non-positive.
    target_root_depth: float | None = None
    if isinstance(rooting_depth_mm, Missing):
        return _missing_profile_result(
            failure=Missing(
                reason="MISSING_INPUT",
                detail=_format_missing_item("rooting_depth_mm", rooting_depth_mm),
            ),
            layers=layers_tuple,
            source_tag=profile_tag,
            layer_source_tags=layer_tags,
        )
    if rooting_depth_mm is not None:
        if not _is_finite(rooting_depth_mm):
            return _missing_profile_result(
                failure=Missing(
                    reason="NOT_COMPUTABLE",
                    detail="rooting_depth_mm is not a finite number",
                ),
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )
        target_root_depth = float(rooting_depth_mm)
        if target_root_depth <= _ZERO:
            return _missing_profile_result(
                failure=Missing(
                    reason="CONTROL_FAILED",
                    detail=f"rooting_depth_mm must be > 0, got {target_root_depth}",
                ),
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )

    # Rule 3: every horizon must have a known positive finite effective_depth_mm.
    layer_depths: list[float] = []
    for layer in layers_tuple:
        depth_val = _evaluate_effective_depth_mm(
            layer.layer_id, layer.effective_depth_mm
        )
        if isinstance(depth_val, Missing):
            return _missing_profile_result(
                failure=depth_val,
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )
        layer_depths.append(depth_val)

    total_available_depth = sum(layer_depths)
    if not _is_finite(total_available_depth):
        return _missing_profile_result(
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail="sum of layer effective depths is not finite",
            ),
            layers=layers_tuple,
            source_tag=profile_tag,
            layer_source_tags=layer_tags,
        )

    if target_root_depth is not None and total_available_depth < target_root_depth:
        return _missing_profile_result(
            failure=Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"soil horizons cover {total_available_depth:.6g} mm, less than "
                    f"required rooting_depth_mm ({target_root_depth:.6g} mm); "
                    "deeper soil properties are missing and never guessed"
                ),
            ),
            layers=layers_tuple,
            source_tag=profile_tag,
            layer_source_tags=layer_tags,
        )

    # Determine used thickness per layer and check contributing layers.
    remaining = (
        target_root_depth if target_root_depth is not None else total_available_depth
    )
    used_depths: list[float] = []
    contributing: list[tuple[LayerWaterProperties, float]] = []
    for layer, depth in zip(layers_tuple, layer_depths, strict=True):
        if remaining <= _ZERO:
            used_depths.append(_ZERO)
            continue
        take = min(depth, remaining)
        used_depths.append(take)
        remaining -= take
        contributing.append((layer, take))

    # Propagate any failure in contributing layers.
    for layer, _ in contributing:
        if id(layer) in pre_layer_failures:
            return _missing_profile_result(
                failure=pre_layer_failures[id(layer)],
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )
        awc_val = layer.available_water_capacity
        if isinstance(awc_val, Missing):
            return _missing_profile_result(
                failure=awc_val,
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )
        if not _is_finite(awc_val):
            return _missing_profile_result(
                failure=Missing(
                    reason="NOT_COMPUTABLE",
                    detail=f"layer '{layer.layer_id}' available_water_capacity is not finite",
                ),
                layers=layers_tuple,
                source_tag=profile_tag,
                layer_source_tags=layer_tags,
            )

    contributing_tags = tuple(layer.source_tag for layer, _ in contributing)
    effective_profile_tag = _weakest_source_tag(contributing_tags)
    all_measured = all(tag == "MEASURED_LOCAL_PROFILE" for tag in contributing_tags)
    provenance: ProvenanceLabel = "OBSERVED" if all_measured else "DERIVED"

    total_awc_mm = _ZERO
    integrated_depth = _ZERO
    for layer, take in contributing:
        assert not isinstance(layer.available_water_capacity, Missing)
        total_awc_mm += layer.available_water_capacity * take
        integrated_depth += take

    if not _is_finite(total_awc_mm) or not _is_finite(integrated_depth):
        return _missing_profile_result(
            failure=Missing(
                reason="NOT_COMPUTABLE",
                detail="integrated profile AWC is not finite",
            ),
            layers=layers_tuple,
            source_tag=effective_profile_tag,
            layer_source_tags=layer_tags,
        )

    # Aggregate uncertainty range across contributing layers.
    first_missing_range: Missing | None = None
    for layer, _ in contributing:
        if layer.awc_range is None:
            first_missing_range = layer.awc_range_missing or Missing(
                reason="NOT_AVAILABLE",
                detail=f"layer '{layer.layer_id}' has no AWC uncertainty range",
            )
            break

    total_range: Range | None
    total_range_missing: Missing | None
    if first_missing_range is not None:
        total_range = None
        total_range_missing = first_missing_range
    else:
        low_mm = _ZERO
        high_mm = _ZERO
        kinds: set[str] = set()
        for layer, take in contributing:
            assert layer.awc_range is not None
            low_mm += layer.awc_range.low * take
            high_mm += layer.awc_range.high * take
            kinds.add(layer.awc_range.kind)
        if not _is_finite(low_mm) or not _is_finite(high_mm):
            total_range = None
            total_range_missing = Missing(
                reason="NOT_COMPUTABLE",
                detail="integrated profile AWC uncertainty bounds are not finite",
            )
        elif low_mm >= high_mm:
            total_range = None
            total_range_missing = Missing(
                reason="CONTROL_FAILED",
                detail="integrated profile AWC uncertainty range has zero width (C2.2)",
            )
        else:
            range_kind = (
                next(iter(kinds)) if len(kinds) == 1 else "; ".join(sorted(kinds))
            )
            total_range = Range(low=low_mm, high=high_mm, kind=range_kind)
            total_range_missing = None

    layer_sources = [layer.source or layer.layer_id for layer, _ in contributing]
    return ProfileAwcResult(
        total_awc_mm=total_awc_mm,
        unit=UNIT_DEPTH_MM,
        effective_depth_mm=integrated_depth,
        total_awc_range=total_range,
        total_awc_range_missing=total_range_missing,
        source_tag=effective_profile_tag,
        layer_source_tags=layer_tags,
        is_lab_measured=all_measured,
        provenance=provenance,
        source=f"profile_awc [{effective_profile_tag}]: " + "; ".join(layer_sources),
        layers=layers_tuple,
        layer_depths_used_mm=tuple(used_depths),
    )
