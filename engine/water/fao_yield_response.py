"""Pure-Python FAO-33 water-limited crop yield response and multi-model contrast bundle.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

This module implements:
1. ``compute_fao_water_limited_yield``: pure-Python FAO Irrigation and Drainage
   Paper No. 33 water-limited yield response function supporting seasonal
   (``1 - Ya/Ym = Ky * (1 - ETa/ETc)``), stagewise multiplicative, and
   stagewise most-sensitive formulations with caller-supplied ``Ky``, ``Ym``
   (potential/reference yield in ``kg ha-1``), and ``ETa``/``ETc`` inputs.
   Zero crop ``Ky`` or ``Ym`` numbers are hardcoded here.
2. ``YieldModelContrastBundle`` and ``build_yield_model_contrast_bundle``:
   side-by-side yield estimates across four distinct model slots:
   - ``"DECLARED"``
   - ``"FAO_WATER_KY"``
   - ``"AQUACROP_OSPY_CONTRAST"`` (caller-supplied external interface envelope)
   - ``"GECROS_HYPOTHESIS"`` (always marked ``license_verified=False``,
     ``label="HYPOTHESIS"``)

Invariants enforced:
- Never averages across heterogeneous crop models
  (``allow_multi_model_average=False``; reports min/max range and per-model
  trajectory).
- Pastures without a declared livestock utilization/conversion module return
  typed ``Missing(reason="MISSING_INPUT", detail="pasture yield without
  livestock module is incomplete")``, never ``0.0``.
- Zero ``ETc`` or missing ``ETa``/``Ky``/``Ym`` returns typed ``Missing``
  (``NOT_APPLICABLE`` / ``MISSING_INPUT``), clamping ``ETa <= ETc`` or flagging
  excess explicitly according to ``excess_eta_policy``.

Pure function (G1): pure Python 3.12 stdlib + ``contracts.*``, no file I/O, no
network calls, no clock, no environment variables, no global mutable state, and
arguments are never mutated.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.results.models import Missing, ProvenanceLabel

__all__ = [
    "CROP_PURPOSES",
    "EXCESS_ETA_POLICIES",
    "FAO_YIELD_METHODS",
    "GECROS_REQUIRED_LABEL",
    "PASTURE_INCOMPLETE_DETAIL",
    "PROPOSED_STATUS_LABEL",
    "UNIT_YIELD_KG_HA",
    "YIELD_MODEL_IDS",
    "CropPurpose",
    "ExcessEtaPolicy",
    "ExternalYieldContrastEnvelope",
    "FaoAnnualYieldInput",
    "FaoWaterLimitedYieldResult",
    "FaoYieldMethod",
    "LivestockUtilizationStatus",
    "ModelYieldEstimate",
    "ModelYieldPoint",
    "ModelYieldRange",
    "StageWaterInput",
    "StageYieldResponse",
    "YieldModelContrastBundle",
    "YieldModelId",
    "build_yield_model_contrast_bundle",
    "compute_fao_water_limited_yield",
]

PROPOSED_STATUS_LABEL = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
UNIT_YIELD_KG_HA = "kg ha-1"
PASTURE_INCOMPLETE_DETAIL = "pasture yield without livestock module is incomplete"
GECROS_REQUIRED_LABEL = "HYPOTHESIS"

CropPurpose = Literal["grain", "cover", "pasture"]
CROP_PURPOSES: tuple[str, ...] = ("grain", "cover", "pasture")

FaoYieldMethod = Literal[
    "seasonal",
    "stagewise_multiplicative",
    "stagewise_most_sensitive",
]
FAO_YIELD_METHODS: tuple[str, ...] = (
    "seasonal",
    "stagewise_multiplicative",
    "stagewise_most_sensitive",
)

ExcessEtaPolicy = Literal["clamp", "not_computable"]
EXCESS_ETA_POLICIES: tuple[str, ...] = ("clamp", "not_computable")

YieldModelId = Literal[
    "DECLARED",
    "FAO_WATER_KY",
    "AQUACROP_OSPY_CONTRAST",
    "GECROS_HYPOTHESIS",
]
YIELD_MODEL_IDS: tuple[str, ...] = (
    "DECLARED",
    "FAO_WATER_KY",
    "AQUACROP_OSPY_CONTRAST",
    "GECROS_HYPOTHESIS",
)


def _is_strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _pasture_missing() -> Missing:
    return Missing(reason="MISSING_INPUT", detail=PASTURE_INCOMPLETE_DETAIL)


def _check_non_blank_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank (G5)")
    return value


def _check_strict_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name}: expected bool, got {type(value).__name__} (G5)")
    return value


def _check_crop_purpose(value: object) -> CropPurpose:
    if not isinstance(value, str):
        raise TypeError(f"crop_purpose: expected str, got {type(value).__name__} (G5)")
    if value not in CROP_PURPOSES:
        raise ValueError(
            f"crop_purpose: expected one of {CROP_PURPOSES}, got {value!r} (G5)"
        )
    return value  # type: ignore[return-value]


def _validate_numeric_or_missing(name: str, value: object) -> float | Missing:
    """Validate an input number (non-negative finite float) or Missing."""
    if isinstance(value, Missing):
        return value
    if value is None:
        return Missing(reason="MISSING_INPUT", detail=f"{name} is missing")
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected float, int, Missing, or None, "
            f"got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite(value):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{name} is not a finite number",
        )
    numeric = float(value)
    if numeric < 0.0:
        raise ValueError(f"{name}: must not be negative, got {numeric} (G5)")
    return numeric


def _check_method(value: object) -> FaoYieldMethod:
    if not isinstance(value, str):
        raise TypeError(f"method: expected str, got {type(value).__name__} (G5)")
    if value not in FAO_YIELD_METHODS:
        raise ValueError(
            f"method: expected one of {FAO_YIELD_METHODS}, got {value!r} (G5)"
        )
    return value  # type: ignore[return-value]


def _check_excess_policy(value: object) -> ExcessEtaPolicy:
    if not isinstance(value, str):
        raise TypeError(
            f"excess_eta_policy: expected str, got {type(value).__name__} (G5)"
        )
    if value not in EXCESS_ETA_POLICIES:
        raise ValueError(
            f"excess_eta_policy: expected one of {EXCESS_ETA_POLICIES}, "
            f"got {value!r} (G5)"
        )
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class StageWaterInput:
    """Caller-supplied evapotranspiration and optional Ky for one growth stage.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    stage: str
    eta_mm: float | Missing | None
    etc_mm: float | Missing | None
    ky: float | Missing | None = None

    def __post_init__(self) -> None:
        _check_non_blank_str("stage", self.stage)
        for field_name in ("eta_mm", "etc_mm", "ky"):
            val = getattr(self, field_name)
            if val is not None and not isinstance(val, Missing):
                if not _is_strict_number(val):
                    raise TypeError(
                        f"StageWaterInput.{field_name}: expected float, int, "
                        f"Missing, or None, got {type(val).__name__} (G5)"
                    )
                assert isinstance(val, (int, float))
                if _is_finite(val) and float(val) < 0.0:
                    raise ValueError(
                        f"StageWaterInput.{field_name}: must not be negative, "
                        f"got {val} (G5)"
                    )


@dataclass(frozen=True)
class StageYieldResponse:
    """Computed FAO-33 response diagnostics for one growth stage.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    stage: str
    eta_mm: float
    etc_mm: float
    effective_eta_mm: float
    ky: float
    relative_yield: float
    yield_reduction_fraction: float
    eta_exceeded_etc: bool
    clamped_at_zero: bool


@dataclass(frozen=True)
class FaoWaterLimitedYieldResult:
    """Result of pure-Python FAO-33 water-limited crop yield response.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    method: FaoYieldMethod
    crop_purpose: CropPurpose
    ya_kg_ha: float
    ym_kg_ha: float
    relative_yield: float
    yield_reduction_fraction: float
    eta_mm: float
    etc_mm: float
    effective_eta_mm: float
    ky: float | None
    eta_exceeded_etc: bool
    excess_eta_policy: ExcessEtaPolicy
    clamped_at_zero: bool
    stages: tuple[StageYieldResponse, ...]
    livestock_conversion_factor: float | None = None
    unit: str = UNIT_YIELD_KG_HA
    provenance: ProvenanceLabel = "DERIVED"
    status_label: str = PROPOSED_STATUS_LABEL


def _apply_excess_eta(
    *,
    eta_mm: float,
    etc_mm: float,
    excess_eta_policy: ExcessEtaPolicy,
    scope_label: str,
) -> tuple[float, bool] | Missing:
    if eta_mm > etc_mm:
        if excess_eta_policy == "not_computable":
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{scope_label}: actual evapotranspiration 'eta_mm' "
                    "exceeds crop evapotranspiration 'etc_mm'"
                ),
            )
        return etc_mm, True
    return eta_mm, False


def _validate_stages_sequence(stages: object) -> tuple[StageWaterInput, ...]:
    if isinstance(stages, (str, bytes, bytearray)) or not isinstance(stages, Sequence):
        raise TypeError(
            f"stages: expected a Sequence of StageWaterInput, got {type(stages).__name__} (G5)"
        )
    items: list[StageWaterInput] = []
    seen_names: set[str] = set()
    for item in stages:
        if not isinstance(item, StageWaterInput):
            raise TypeError(
                f"stages: expected StageWaterInput elements, got {type(item).__name__} (G5)"
            )
        if item.stage in seen_names:
            raise ValueError(
                f"stages: duplicate stage name {item.stage!r} is not allowed (G5)"
            )
        seen_names.add(item.stage)
        items.append(item)
    return tuple(items)


def _compute_seasonal_fao(
    *,
    ym_kg_ha: float,
    ky: float | Missing | None,
    eta_mm: float | Missing | None,
    etc_mm: float | Missing | None,
    stages: Sequence[StageWaterInput] | None,
    crop_purpose: CropPurpose,
    excess_eta_policy: ExcessEtaPolicy,
    conversion_factor: float | None,
) -> FaoWaterLimitedYieldResult | Missing:
    if stages is not None and (eta_mm is not None or etc_mm is not None):
        raise ValueError(
            "seasonal mode accepts either scalar (eta_mm, etc_mm) or stages, not both (G5)"
        )

    checked_ky = _validate_numeric_or_missing("yield response factor 'ky'", ky)
    if isinstance(checked_ky, Missing):
        return checked_ky

    if stages is not None:
        stage_items = _validate_stages_sequence(stages)
        if not stage_items:
            return Missing(
                reason="NOT_APPLICABLE",
                detail="no growth stages supplied; seasonal ETc is zero",
            )
        eta_parts: list[float] = []
        etc_parts: list[float] = []
        for stage_item in stage_items:
            s_eta = _validate_numeric_or_missing(
                f"stage '{stage_item.stage}' eta_mm", stage_item.eta_mm
            )
            if isinstance(s_eta, Missing):
                return s_eta
            s_etc = _validate_numeric_or_missing(
                f"stage '{stage_item.stage}' etc_mm", stage_item.etc_mm
            )
            if isinstance(s_etc, Missing):
                return s_etc
            eta_parts.append(s_eta)
            etc_parts.append(s_etc)
        raw_eta = math.fsum(eta_parts)
        total_etc = math.fsum(etc_parts)
    else:
        checked_eta = _validate_numeric_or_missing(
            "actual evapotranspiration 'eta_mm'", eta_mm
        )
        if isinstance(checked_eta, Missing):
            return checked_eta
        checked_etc = _validate_numeric_or_missing(
            "crop evapotranspiration 'etc_mm'", etc_mm
        )
        if isinstance(checked_etc, Missing):
            return checked_etc
        raw_eta = checked_eta
        total_etc = checked_etc

    if total_etc == 0.0:
        return Missing(
            reason="NOT_APPLICABLE",
            detail="crop evapotranspiration 'etc_mm' is zero; water-limited yield response is not applicable",
        )

    excess_check = _apply_excess_eta(
        eta_mm=raw_eta,
        etc_mm=total_etc,
        excess_eta_policy=excess_eta_policy,
        scope_label="seasonal",
    )
    if isinstance(excess_check, Missing):
        return excess_check
    effective_eta, eta_exceeded_etc = excess_check

    deficit_fraction = 1.0 - (effective_eta / total_etc)
    raw_relative = 1.0 - checked_ky * deficit_fraction
    clamped_at_zero = raw_relative < 0.0
    relative_yield = max(0.0, raw_relative)
    yield_reduction_fraction = 1.0 - relative_yield
    scale = 1.0 if conversion_factor is None else conversion_factor
    ya_kg_ha = ym_kg_ha * relative_yield * scale

    return FaoWaterLimitedYieldResult(
        method="seasonal",
        crop_purpose=crop_purpose,
        ya_kg_ha=ya_kg_ha,
        ym_kg_ha=ym_kg_ha,
        relative_yield=relative_yield,
        yield_reduction_fraction=yield_reduction_fraction,
        eta_mm=raw_eta,
        etc_mm=total_etc,
        effective_eta_mm=effective_eta,
        ky=checked_ky,
        eta_exceeded_etc=eta_exceeded_etc,
        excess_eta_policy=excess_eta_policy,
        clamped_at_zero=clamped_at_zero,
        stages=(),
        livestock_conversion_factor=conversion_factor,
    )


def _compute_stagewise_fao(
    *,
    method: Literal["stagewise_multiplicative", "stagewise_most_sensitive"],
    ym_kg_ha: float,
    eta_mm: float | Missing | None,
    etc_mm: float | Missing | None,
    stages: Sequence[StageWaterInput] | None,
    crop_purpose: CropPurpose,
    excess_eta_policy: ExcessEtaPolicy,
    conversion_factor: float | None,
) -> FaoWaterLimitedYieldResult | Missing:
    if eta_mm is not None or etc_mm is not None:
        raise ValueError(
            f"{method} requires stage series 'stages' and does not accept scalar eta_mm/etc_mm (G5)"
        )
    if stages is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=f"stage water series 'stages' is missing for {method}",
        )

    stage_items = _validate_stages_sequence(stages)
    if not stage_items:
        return Missing(
            reason="NOT_APPLICABLE",
            detail=f"no growth stages supplied for {method}",
        )

    stage_results: list[StageYieldResponse] = []
    for stage_item in stage_items:
        s_ky = _validate_numeric_or_missing(
            f"stage '{stage_item.stage}' ky", stage_item.ky
        )
        if isinstance(s_ky, Missing):
            return s_ky
        s_eta = _validate_numeric_or_missing(
            f"stage '{stage_item.stage}' eta_mm", stage_item.eta_mm
        )
        if isinstance(s_eta, Missing):
            return s_eta
        s_etc = _validate_numeric_or_missing(
            f"stage '{stage_item.stage}' etc_mm", stage_item.etc_mm
        )
        if isinstance(s_etc, Missing):
            return s_etc
        if s_etc == 0.0:
            return Missing(
                reason="NOT_APPLICABLE",
                detail=(
                    f"stage '{stage_item.stage}' has zero ETc; "
                    "water-limited yield response is not applicable"
                ),
            )
        excess_check = _apply_excess_eta(
            eta_mm=s_eta,
            etc_mm=s_etc,
            excess_eta_policy=excess_eta_policy,
            scope_label=f"stage '{stage_item.stage}'",
        )
        if isinstance(excess_check, Missing):
            return excess_check
        eff_eta, exceeded = excess_check
        raw_rel = 1.0 - s_ky * (1.0 - eff_eta / s_etc)
        clamped_zero = raw_rel < 0.0
        rel_yield = max(0.0, raw_rel)
        stage_results.append(
            StageYieldResponse(
                stage=stage_item.stage,
                eta_mm=s_eta,
                etc_mm=s_etc,
                effective_eta_mm=eff_eta,
                ky=s_ky,
                relative_yield=rel_yield,
                yield_reduction_fraction=1.0 - rel_yield,
                eta_exceeded_etc=exceeded,
                clamped_at_zero=clamped_zero,
            )
        )

    if method == "stagewise_multiplicative":
        relative_yield = math.prod(item.relative_yield for item in stage_results)
    else:
        relative_yield = min(item.relative_yield for item in stage_results)

    scale = 1.0 if conversion_factor is None else conversion_factor
    ya_kg_ha = ym_kg_ha * relative_yield * scale

    return FaoWaterLimitedYieldResult(
        method=method,
        crop_purpose=crop_purpose,
        ya_kg_ha=ya_kg_ha,
        ym_kg_ha=ym_kg_ha,
        relative_yield=relative_yield,
        yield_reduction_fraction=1.0 - relative_yield,
        eta_mm=math.fsum(item.eta_mm for item in stage_results),
        etc_mm=math.fsum(item.etc_mm for item in stage_results),
        effective_eta_mm=math.fsum(item.effective_eta_mm for item in stage_results),
        ky=None,
        eta_exceeded_etc=any(item.eta_exceeded_etc for item in stage_results),
        excess_eta_policy=excess_eta_policy,
        clamped_at_zero=any(item.clamped_at_zero for item in stage_results),
        stages=tuple(stage_results),
        livestock_conversion_factor=conversion_factor,
    )


def compute_fao_water_limited_yield(
    *,
    ym_kg_ha: float | Missing | None,
    ky: float | Missing | None = None,
    eta_mm: float | Missing | None = None,
    etc_mm: float | Missing | None = None,
    stages: Sequence[StageWaterInput] | None = None,
    method: FaoYieldMethod = "seasonal",
    crop_purpose: CropPurpose = "grain",
    livestock_module_declared: bool = False,
    livestock_conversion_factor: float | Missing | None = None,
    excess_eta_policy: ExcessEtaPolicy = "clamp",
) -> FaoWaterLimitedYieldResult | Missing:
    """Compute pure-Python FAO-33 water-limited crop yield response.

    Supports seasonal (``1 - Ya/Ym = Ky * (1 - ETa/ETc)``),
    ``"stagewise_multiplicative"``, and ``"stagewise_most_sensitive"``
    formulations using only caller-supplied ``ym_kg_ha``, ``ky``, and
    ``ETa``/``ETc`` values (zero hardcoded crop ``Ky`` or ``Ym`` numbers).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """
    checked_method = _check_method(method)
    checked_purpose = _check_crop_purpose(crop_purpose)
    checked_livestock = _check_strict_bool(
        "livestock_module_declared", livestock_module_declared
    )
    checked_policy = _check_excess_policy(excess_eta_policy)

    if checked_purpose != "pasture" and livestock_conversion_factor is not None:
        raise ValueError(
            "livestock_conversion_factor applies only when crop_purpose == 'pasture' (G5)"
        )

    if checked_purpose == "pasture" and not checked_livestock:
        return _pasture_missing()

    conversion_factor: float | None = None
    if checked_purpose == "pasture" and livestock_conversion_factor is not None:
        checked_factor = _validate_numeric_or_missing(
            "livestock_conversion_factor", livestock_conversion_factor
        )
        if isinstance(checked_factor, Missing):
            return checked_factor
        conversion_factor = checked_factor

    checked_ym = _validate_numeric_or_missing(
        "potential/reference yield 'ym_kg_ha'", ym_kg_ha
    )
    if isinstance(checked_ym, Missing):
        return checked_ym

    if checked_method == "seasonal":
        return _compute_seasonal_fao(
            ym_kg_ha=checked_ym,
            ky=ky,
            eta_mm=eta_mm,
            etc_mm=etc_mm,
            stages=stages,
            crop_purpose=checked_purpose,
            excess_eta_policy=checked_policy,
            conversion_factor=conversion_factor,
        )

    return _compute_stagewise_fao(
        method=checked_method,
        ym_kg_ha=checked_ym,
        eta_mm=eta_mm,
        etc_mm=etc_mm,
        stages=stages,
        crop_purpose=checked_purpose,
        excess_eta_policy=checked_policy,
        conversion_factor=conversion_factor,
    )


# ---------------------------------------------------------------------------
# Multi-model contrast bundle (never averages across heterogeneous models)
# ---------------------------------------------------------------------------


def _validate_trajectory(name: str, trajectory: object) -> tuple[ModelYieldPoint, ...]:
    if isinstance(trajectory, (str, bytes, bytearray)) or not isinstance(
        trajectory, Sequence
    ):
        raise TypeError(
            f"{name}: expected a Sequence of ModelYieldPoint, "
            f"got {type(trajectory).__name__} (G5)"
        )
    points: list[ModelYieldPoint] = []
    prev_year: int | None = None
    for item in trajectory:
        if not isinstance(item, ModelYieldPoint):
            raise TypeError(
                f"{name}: expected ModelYieldPoint elements, "
                f"got {type(item).__name__} (G5)"
            )
        if prev_year is not None and item.ag_year <= prev_year:
            raise ValueError(
                f"{name}: trajectory ag_year must be strictly increasing "
                f"(got {item.ag_year} after {prev_year}) (G5)"
            )
        prev_year = item.ag_year
        points.append(item)
    return tuple(points)


@dataclass(frozen=True)
class ModelYieldPoint:
    """One agricultural year's yield estimate in a per-model trajectory.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ag_year: int
    value: float | Missing
    unit: str = UNIT_YIELD_KG_HA
    eta_exceeded_etc: bool = False

    def __post_init__(self) -> None:
        if not _is_strict_int(self.ag_year):
            raise TypeError(
                f"ag_year: expected int, got {type(self.ag_year).__name__} (G5)"
            )
        if self.unit != UNIT_YIELD_KG_HA:
            raise ValueError(
                f"unit: expected {UNIT_YIELD_KG_HA!r}, got {self.unit!r} (C1.1)"
            )
        _check_strict_bool("eta_exceeded_etc", self.eta_exceeded_etc)
        if isinstance(self.value, Missing):
            return
        if not _is_strict_number(self.value):
            raise TypeError(
                f"value: expected float, int, or Missing, "
                f"got {type(self.value).__name__} (G5)"
            )
        assert isinstance(self.value, (int, float))
        if not _is_finite(self.value):
            raise ValueError(
                "value: must be finite; use Missing for non-computable (G5)"
            )
        numeric = float(self.value)
        if numeric < 0.0:
            raise ValueError(f"value: must not be negative, got {numeric} (G5)")
        object.__setattr__(self, "value", numeric)


@dataclass(frozen=True)
class ModelYieldEstimate:
    """Independent side-by-side yield trajectory for one model family.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    model_id: YieldModelId
    trajectory: tuple[ModelYieldPoint, ...]
    license_verified: bool
    label: str
    unit: str = UNIT_YIELD_KG_HA
    provenance: ProvenanceLabel | None = None
    source: str | None = None
    missing: Missing | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or self.model_id not in YIELD_MODEL_IDS:
            raise ValueError(
                f"model_id: expected one of {YIELD_MODEL_IDS}, got {self.model_id!r} (G5)"
            )
        _check_strict_bool("license_verified", self.license_verified)
        _check_non_blank_str("label", self.label)
        if self.unit != UNIT_YIELD_KG_HA:
            raise ValueError(
                f"unit: expected {UNIT_YIELD_KG_HA!r}, got {self.unit!r} (C1.1)"
            )
        if self.model_id == "GECROS_HYPOTHESIS":
            if self.license_verified:
                raise ValueError(
                    "GECROS_HYPOTHESIS must be marked license_verified=False"
                )
            if self.label != GECROS_REQUIRED_LABEL:
                raise ValueError(
                    f"GECROS_HYPOTHESIS must carry label={GECROS_REQUIRED_LABEL!r}, "
                    f"got {self.label!r}"
                )
        checked_traj = _validate_trajectory("trajectory", self.trajectory)
        object.__setattr__(self, "trajectory", checked_traj)

        if self.missing is not None and not isinstance(self.missing, Missing):
            raise TypeError(
                f"missing: expected Missing or None, got {type(self.missing).__name__} (G5)"
            )
        has_numeric = any(not isinstance(pt.value, Missing) for pt in checked_traj)
        if has_numeric:
            if self.provenance is None:
                raise ValueError(
                    "a model estimate with numeric values carries a provenance label (C4.1)"
                )
            _check_non_blank_str("source", self.source)
        else:
            if self.provenance is not None:
                raise ValueError(
                    "a model estimate with no numeric values carries no provenance label (C4.1)"
                )
            if not checked_traj and self.missing is None:
                raise ValueError(
                    "an empty trajectory must carry a Missing reason (C3.1)"
                )


@dataclass(frozen=True)
class ModelYieldRange:
    """Min/max yield spread across models for one year (never averaged).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ag_year: int
    min_kg_ha: float
    max_kg_ha: float
    min_model_id: YieldModelId
    max_model_id: YieldModelId
    included_model_ids: tuple[YieldModelId, ...]
    includes_hypothesis: bool
    unit: str = UNIT_YIELD_KG_HA

    def __post_init__(self) -> None:
        if not _is_strict_int(self.ag_year):
            raise TypeError(
                f"ag_year: expected int, got {type(self.ag_year).__name__} (G5)"
            )
        if self.unit != UNIT_YIELD_KG_HA:
            raise ValueError(
                f"unit: expected {UNIT_YIELD_KG_HA!r}, got {self.unit!r} (C1.1)"
            )
        for field_name in ("min_kg_ha", "max_kg_ha"):
            val = getattr(self, field_name)
            if not _is_strict_number(val) or not _is_finite(val) or float(val) < 0.0:
                raise ValueError(
                    f"{field_name}: expected finite non-negative number, got {val!r}"
                )
        if float(self.min_kg_ha) > float(self.max_kg_ha):
            raise ValueError("min_kg_ha must not exceed max_kg_ha (C2.1)")
        if self.min_model_id not in self.included_model_ids:
            raise ValueError("min_model_id must be in included_model_ids")
        if self.max_model_id not in self.included_model_ids:
            raise ValueError("max_model_id must be in included_model_ids")
        _check_strict_bool("includes_hypothesis", self.includes_hypothesis)


@dataclass(frozen=True)
class ExternalYieldContrastEnvelope:
    """Caller-supplied external crop-model interface envelope.

    Holds external trajectory outputs (for example ``AQUACROP_OSPY_CONTRAST``
    or unverified ``GECROS_HYPOTHESIS`` outputs) without importing or calling
    external simulation packages inside pure L1 code.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    model_id: Literal["AQUACROP_OSPY_CONTRAST", "GECROS_HYPOTHESIS"]
    trajectory: tuple[ModelYieldPoint, ...]
    license_verified: bool
    label: str
    source: str
    provenance: ProvenanceLabel = "SIMULATED"
    unit: str = UNIT_YIELD_KG_HA

    def __post_init__(self) -> None:
        if self.model_id not in ("AQUACROP_OSPY_CONTRAST", "GECROS_HYPOTHESIS"):
            raise ValueError(
                "model_id: expected 'AQUACROP_OSPY_CONTRAST' or "
                f"'GECROS_HYPOTHESIS', got {self.model_id!r}"
            )
        _check_strict_bool("license_verified", self.license_verified)
        _check_non_blank_str("label", self.label)
        _check_non_blank_str("source", self.source)
        if self.unit != UNIT_YIELD_KG_HA:
            raise ValueError(
                f"unit: expected {UNIT_YIELD_KG_HA!r}, got {self.unit!r} (C1.1)"
            )
        if self.model_id == "GECROS_HYPOTHESIS":
            if self.license_verified:
                raise ValueError(
                    "GECROS_HYPOTHESIS envelope must have license_verified=False"
                )
            if self.label != GECROS_REQUIRED_LABEL:
                raise ValueError(
                    f"GECROS_HYPOTHESIS envelope must carry label={GECROS_REQUIRED_LABEL!r}"
                )
        checked_traj = _validate_trajectory("trajectory", self.trajectory)
        object.__setattr__(self, "trajectory", checked_traj)


@dataclass(frozen=True)
class LivestockUtilizationStatus:
    """Declared livestock utilization/conversion module status for pastures.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    declared: bool = False
    conversion_factor: float | Missing | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        _check_strict_bool("declared", self.declared)
        if self.declared and self.source is not None:
            _check_non_blank_str("source", self.source)
        if self.conversion_factor is not None and not isinstance(
            self.conversion_factor, Missing
        ):
            if not _is_strict_number(self.conversion_factor):
                raise TypeError(
                    "conversion_factor: expected float, int, Missing, or None, "
                    f"got {type(self.conversion_factor).__name__} (G5)"
                )
            assert isinstance(self.conversion_factor, (int, float))
            if (
                _is_finite(self.conversion_factor)
                and float(self.conversion_factor) < 0.0
            ):
                raise ValueError("conversion_factor: must not be negative (G5)")


@dataclass(frozen=True)
class FaoAnnualYieldInput:
    """Per-year caller inputs for the ``FAO_WATER_KY`` trajectory.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    ag_year: int
    ym_kg_ha: float | Missing | None
    ky: float | Missing | None = None
    eta_mm: float | Missing | None = None
    etc_mm: float | Missing | None = None
    stages: tuple[StageWaterInput, ...] | None = None
    method: FaoYieldMethod = "seasonal"
    excess_eta_policy: ExcessEtaPolicy = "clamp"

    def __post_init__(self) -> None:
        if not _is_strict_int(self.ag_year):
            raise TypeError(
                f"ag_year: expected int, got {type(self.ag_year).__name__} (G5)"
            )
        _check_method(self.method)
        _check_excess_policy(self.excess_eta_policy)


@dataclass(frozen=True)
class YieldModelContrastBundle:
    """Side-by-side multi-model yield contrast bundle without model averaging.

    Holds independent estimates from ``"DECLARED"``, ``"FAO_WATER_KY"``,
    ``"AQUACROP_OSPY_CONTRAST"``, and ``"GECROS_HYPOTHESIS"``.

    Enforces:
    - ``allow_multi_model_average == False`` (never averages across models).
    - ``GECROS_HYPOTHESIS`` always carries ``license_verified=False`` and
      ``label="HYPOTHESIS"``.
    - Pastures without a declared livestock module hold typed
      ``Missing(reason="MISSING_INPUT", detail="pasture yield without
      livestock module is incomplete")`` rather than ``0.0``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    crop_id: str
    crop_purpose: CropPurpose
    livestock_module_declared: bool
    declared: ModelYieldEstimate
    fao_water_ky: ModelYieldEstimate
    aquacrop_ospy_contrast: ModelYieldEstimate
    gecros_hypothesis: ModelYieldEstimate
    allow_multi_model_average: bool = False
    unit: str = UNIT_YIELD_KG_HA
    status_label: str = PROPOSED_STATUS_LABEL

    def __post_init__(self) -> None:
        _check_non_blank_str("crop_id", self.crop_id)
        _check_crop_purpose(self.crop_purpose)
        _check_strict_bool("livestock_module_declared", self.livestock_module_declared)
        _check_strict_bool("allow_multi_model_average", self.allow_multi_model_average)
        if self.allow_multi_model_average:
            raise ValueError(
                "allow_multi_model_average must be False: averaging across "
                "heterogeneous crop models is forbidden"
            )
        if self.unit != UNIT_YIELD_KG_HA:
            raise ValueError(
                f"unit: expected {UNIT_YIELD_KG_HA!r}, got {self.unit!r} (C1.1)"
            )
        expected_slots: tuple[tuple[str, YieldModelId], ...] = (
            ("declared", "DECLARED"),
            ("fao_water_ky", "FAO_WATER_KY"),
            ("aquacrop_ospy_contrast", "AQUACROP_OSPY_CONTRAST"),
            ("gecros_hypothesis", "GECROS_HYPOTHESIS"),
        )
        for attr_name, expected_id in expected_slots:
            estimate = getattr(self, attr_name)
            if not isinstance(estimate, ModelYieldEstimate):
                raise TypeError(
                    f"{attr_name}: expected ModelYieldEstimate, "
                    f"got {type(estimate).__name__} (G5)"
                )
            if estimate.model_id != expected_id:
                raise ValueError(
                    f"{attr_name}: expected model_id={expected_id!r}, "
                    f"got {estimate.model_id!r}"
                )

        if self.crop_purpose == "pasture" and not self.livestock_module_declared:
            for attr_name, _ in expected_slots:
                estimate = getattr(self, attr_name)
                for point in estimate.trajectory:
                    if not isinstance(point.value, Missing) or (
                        point.value.reason != "MISSING_INPUT"
                        or point.value.detail != PASTURE_INCOMPLETE_DETAIL
                    ):
                        raise ValueError(
                            f"{attr_name} (ag_year={point.ag_year}): pasture yield "
                            "without livestock module must be Missing("
                            "reason='MISSING_INPUT', detail=PASTURE_INCOMPLETE_DETAIL)"
                        )
                if not estimate.trajectory and (
                    estimate.missing is None
                    or estimate.missing.reason != "MISSING_INPUT"
                    or estimate.missing.detail != PASTURE_INCOMPLETE_DETAIL
                ):
                    raise ValueError(
                        f"{attr_name}: empty pasture trajectory without "
                        "livestock module must carry Missing("
                        "reason='MISSING_INPUT', detail=PASTURE_INCOMPLETE_DETAIL)"
                    )

    @property
    def models(self) -> dict[YieldModelId, ModelYieldEstimate]:
        """Independent side-by-side model estimates keyed by model identifier."""
        return {
            "DECLARED": self.declared,
            "FAO_WATER_KY": self.fao_water_ky,
            "AQUACROP_OSPY_CONTRAST": self.aquacrop_ospy_contrast,
            "GECROS_HYPOTHESIS": self.gecros_hypothesis,
        }

    def per_model_trajectories(self) -> dict[YieldModelId, tuple[ModelYieldPoint, ...]]:
        """Per-model yield trajectories kept separate (never averaged)."""
        return {
            model_id: estimate.trajectory for model_id, estimate in self.models.items()
        }

    def range_by_year(
        self, *, include_hypothesis: bool = True
    ) -> dict[int, ModelYieldRange | Missing]:
        """Min/max yield range per agricultural year across computable models.

        Never computes or returns a multi-model arithmetic mean.
        """
        _check_strict_bool("include_hypothesis", include_hypothesis)
        if self.crop_purpose == "pasture" and not self.livestock_module_declared:
            years = sorted(
                {pt.ag_year for est in self.models.values() for pt in est.trajectory}
            )
            return {year: _pasture_missing() for year in years}

        selected_models: list[tuple[YieldModelId, ModelYieldEstimate]] = [
            (model_id, estimate)
            for model_id, estimate in self.models.items()
            if include_hypothesis or estimate.label != GECROS_REQUIRED_LABEL
        ]

        years = sorted(
            {pt.ag_year for _, est in selected_models for pt in est.trajectory}
        )
        by_model_year: dict[YieldModelId, dict[int, ModelYieldPoint]] = {
            model_id: {pt.ag_year: pt for pt in est.trajectory}
            for model_id, est in selected_models
        }

        out: dict[int, ModelYieldRange | Missing] = {}
        for year in years:
            computable: list[tuple[YieldModelId, float, bool]] = []
            point_missing_reasons: list[Missing] = []
            absent_missing_reasons: list[Missing] = []
            for model_id, est in selected_models:
                point = by_model_year[model_id].get(year)
                if point is None:
                    if est.missing is not None:
                        absent_missing_reasons.append(est.missing)
                    continue
                if isinstance(point.value, Missing):
                    point_missing_reasons.append(point.value)
                else:
                    computable.append(
                        (
                            model_id,
                            float(point.value),
                            est.label == GECROS_REQUIRED_LABEL,
                        )
                    )
            if not computable:
                if point_missing_reasons:
                    out[year] = point_missing_reasons[0]
                elif absent_missing_reasons:
                    out[year] = absent_missing_reasons[0]
                else:
                    out[year] = Missing(
                        reason="NOT_AVAILABLE",
                        detail=f"no model yield available for ag_year {year}",
                    )
                continue

            min_model_id, min_val, _ = min(computable, key=lambda item: item[1])
            max_model_id, max_val, _ = max(computable, key=lambda item: item[1])
            out[year] = ModelYieldRange(
                ag_year=year,
                min_kg_ha=min_val,
                max_kg_ha=max_val,
                min_model_id=min_model_id,
                max_model_id=max_model_id,
                included_model_ids=tuple(mid for mid, _, _ in computable),
                includes_hypothesis=any(is_hyp for _, _, is_hyp in computable),
            )
        return out


def _model_from_external(
    *,
    model_id: Literal["AQUACROP_OSPY_CONTRAST", "GECROS_HYPOTHESIS"],
    envelope: ExternalYieldContrastEnvelope | None,
    default_label: str,
    absent_detail: str,
) -> ModelYieldEstimate:
    if envelope is None:
        return ModelYieldEstimate(
            model_id=model_id,
            trajectory=(),
            license_verified=False,
            label=default_label,
            provenance=None,
            source=None,
            missing=Missing(reason="NOT_AVAILABLE", detail=absent_detail),
        )
    if envelope.model_id != model_id:
        raise ValueError(
            f"expected envelope with model_id={model_id!r}, got {envelope.model_id!r} (G5)"
        )
    has_numeric = any(not isinstance(pt.value, Missing) for pt in envelope.trajectory)
    first_missing = next(
        (pt.value for pt in envelope.trajectory if isinstance(pt.value, Missing)),
        None,
    )
    return ModelYieldEstimate(
        model_id=model_id,
        trajectory=envelope.trajectory,
        license_verified=envelope.license_verified,
        label=envelope.label,
        provenance=envelope.provenance if has_numeric else None,
        source=envelope.source,
        missing=(
            None
            if has_numeric
            else (
                first_missing or Missing(reason="NOT_AVAILABLE", detail=absent_detail)
            )
        ),
    )


def build_yield_model_contrast_bundle(
    *,
    crop_id: str,
    crop_purpose: CropPurpose,
    fao_inputs: Sequence[FaoAnnualYieldInput],
    declared_trajectory: Sequence[ModelYieldPoint] | None = None,
    declared_source: str | None = None,
    aquacrop_contrast: ExternalYieldContrastEnvelope | None = None,
    gecros_hypothesis: ExternalYieldContrastEnvelope | None = None,
    livestock_status: LivestockUtilizationStatus | None = None,
    fao_source: str = "FAO-33 water-limited yield response (caller Ky/Ym)",
) -> YieldModelContrastBundle:
    """Build a ``YieldModelContrastBundle`` from pure inputs and external envelopes.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """
    _check_non_blank_str("crop_id", crop_id)
    checked_purpose = _check_crop_purpose(crop_purpose)
    _check_non_blank_str("fao_source", fao_source)

    if isinstance(fao_inputs, (str, bytes, bytearray)) or not isinstance(
        fao_inputs, Sequence
    ):
        raise TypeError(
            f"fao_inputs: expected Sequence of FaoAnnualYieldInput, "
            f"got {type(fao_inputs).__name__} (G5)"
        )
    seen_fao_years: set[int] = set()
    fao_list: list[FaoAnnualYieldInput] = []
    for item in fao_inputs:
        if not isinstance(item, FaoAnnualYieldInput):
            raise TypeError(
                f"fao_inputs: expected FaoAnnualYieldInput elements, "
                f"got {type(item).__name__} (G5)"
            )
        if item.ag_year in seen_fao_years:
            raise ValueError(
                f"fao_inputs: duplicate ag_year {item.ag_year} is not allowed (G5)"
            )
        seen_fao_years.add(item.ag_year)
        fao_list.append(item)
    fao_list.sort(key=lambda entry: entry.ag_year)

    if livestock_status is None:
        resolved_livestock = LivestockUtilizationStatus(declared=False)
    elif isinstance(livestock_status, LivestockUtilizationStatus):
        resolved_livestock = livestock_status
    else:
        raise TypeError(
            f"livestock_status: expected LivestockUtilizationStatus or None, "
            f"got {type(livestock_status).__name__} (G5)"
        )

    if declared_trajectory is not None:
        checked_declared_traj = _validate_trajectory(
            "declared_trajectory", declared_trajectory
        )
    else:
        checked_declared_traj = ()

    if aquacrop_contrast is not None and not isinstance(
        aquacrop_contrast, ExternalYieldContrastEnvelope
    ):
        raise TypeError(
            f"aquacrop_contrast: expected ExternalYieldContrastEnvelope or None, "
            f"got {type(aquacrop_contrast).__name__} (G5)"
        )
    if gecros_hypothesis is not None and not isinstance(
        gecros_hypothesis, ExternalYieldContrastEnvelope
    ):
        raise TypeError(
            f"gecros_hypothesis: expected ExternalYieldContrastEnvelope or None, "
            f"got {type(gecros_hypothesis).__name__} (G5)"
        )

    if checked_purpose == "pasture" and not resolved_livestock.declared:
        pasture_gap = _pasture_missing()
        all_years = sorted(
            seen_fao_years
            | {pt.ag_year for pt in checked_declared_traj}
            | (
                {pt.ag_year for pt in aquacrop_contrast.trajectory}
                if aquacrop_contrast is not None
                else set()
            )
            | (
                {pt.ag_year for pt in gecros_hypothesis.trajectory}
                if gecros_hypothesis is not None
                else set()
            )
        )
        pasture_points = tuple(
            ModelYieldPoint(ag_year=year, value=pasture_gap) for year in all_years
        )
        return YieldModelContrastBundle(
            crop_id=crop_id,
            crop_purpose=checked_purpose,
            livestock_module_declared=False,
            declared=ModelYieldEstimate(
                model_id="DECLARED",
                trajectory=pasture_points,
                license_verified=True,
                label="DECLARED",
                provenance=None,
                source=declared_source,
                missing=pasture_gap,
            ),
            fao_water_ky=ModelYieldEstimate(
                model_id="FAO_WATER_KY",
                trajectory=pasture_points,
                license_verified=True,
                label="FAO_33_WATER_KY",
                provenance=None,
                source=fao_source,
                missing=pasture_gap,
            ),
            aquacrop_ospy_contrast=ModelYieldEstimate(
                model_id="AQUACROP_OSPY_CONTRAST",
                trajectory=pasture_points,
                license_verified=(
                    aquacrop_contrast.license_verified
                    if aquacrop_contrast is not None
                    else False
                ),
                label=(
                    aquacrop_contrast.label
                    if aquacrop_contrast is not None
                    else "EXTERNAL_CONTRAST"
                ),
                provenance=None,
                source=aquacrop_contrast.source if aquacrop_contrast else None,
                missing=pasture_gap,
            ),
            gecros_hypothesis=ModelYieldEstimate(
                model_id="GECROS_HYPOTHESIS",
                trajectory=pasture_points,
                license_verified=False,
                label=GECROS_REQUIRED_LABEL,
                provenance=None,
                source=gecros_hypothesis.source if gecros_hypothesis else None,
                missing=pasture_gap,
            ),
            allow_multi_model_average=False,
        )

    # FAO-33 model slot
    fao_points: list[ModelYieldPoint] = []
    for item in fao_list:
        outcome = compute_fao_water_limited_yield(
            ym_kg_ha=item.ym_kg_ha,
            ky=item.ky,
            eta_mm=item.eta_mm,
            etc_mm=item.etc_mm,
            stages=item.stages,
            method=item.method,
            crop_purpose=checked_purpose,
            livestock_module_declared=resolved_livestock.declared,
            livestock_conversion_factor=resolved_livestock.conversion_factor,
            excess_eta_policy=item.excess_eta_policy,
        )
        if isinstance(outcome, Missing):
            fao_points.append(ModelYieldPoint(ag_year=item.ag_year, value=outcome))
        else:
            fao_points.append(
                ModelYieldPoint(
                    ag_year=item.ag_year,
                    value=outcome.ya_kg_ha,
                    eta_exceeded_etc=outcome.eta_exceeded_etc,
                )
            )
    fao_has_numeric = any(not isinstance(pt.value, Missing) for pt in fao_points)
    fao_first_missing = next(
        (pt.value for pt in fao_points if isinstance(pt.value, Missing)), None
    )
    fao_estimate = ModelYieldEstimate(
        model_id="FAO_WATER_KY",
        trajectory=tuple(fao_points),
        license_verified=True,
        label="FAO_33_WATER_KY",
        provenance="DERIVED" if fao_has_numeric else None,
        source=fao_source,
        missing=(
            None
            if fao_has_numeric
            else (
                fao_first_missing
                or Missing(
                    reason="MISSING_INPUT",
                    detail="no FAO-33 annual yield inputs supplied",
                )
            )
        ),
    )

    # DECLARED model slot
    declared_has_numeric = any(
        not isinstance(pt.value, Missing) for pt in checked_declared_traj
    )
    if declared_has_numeric:
        _check_non_blank_str("declared_source", declared_source)
    declared_first_missing = next(
        (pt.value for pt in checked_declared_traj if isinstance(pt.value, Missing)),
        None,
    )
    declared_estimate = ModelYieldEstimate(
        model_id="DECLARED",
        trajectory=checked_declared_traj,
        license_verified=True,
        label="DECLARED",
        provenance="DECLARED" if declared_has_numeric else None,
        source=declared_source,
        missing=(
            None
            if declared_has_numeric
            else (
                declared_first_missing
                or Missing(
                    reason="NOT_DECLARED",
                    detail="no declared yield trajectory supplied",
                )
            )
        ),
    )

    # External contrast envelopes
    aquacrop_estimate = _model_from_external(
        model_id="AQUACROP_OSPY_CONTRAST",
        envelope=aquacrop_contrast,
        default_label="EXTERNAL_CONTRAST",
        absent_detail="AquaCrop-OSPy contrast envelope not supplied",
    )
    gecros_estimate = _model_from_external(
        model_id="GECROS_HYPOTHESIS",
        envelope=gecros_hypothesis,
        default_label=GECROS_REQUIRED_LABEL,
        absent_detail="GECROS hypothesis envelope not supplied",
    )

    return YieldModelContrastBundle(
        crop_id=crop_id,
        crop_purpose=checked_purpose,
        livestock_module_declared=resolved_livestock.declared,
        declared=declared_estimate,
        fao_water_ky=fao_estimate,
        aquacrop_ospy_contrast=aquacrop_estimate,
        gecros_hypothesis=gecros_estimate,
        allow_multi_model_average=False,
    )
