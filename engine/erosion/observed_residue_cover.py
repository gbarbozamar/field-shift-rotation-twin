"""Observed satellite dry-cover / residue subfactor evaluator.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements the frontier ``HYPOTHESIS`` evaluator for satellite-observed dry
residue cover alongside the normative tabular ``C`` surface-cover subfactor
(``exp(-b * cover_percent)`` with caller-supplied ``b`` and zero hardcoded
coefficients), following the frontier rules:

1. Raw ``HLS`` ``NDTI`` MUST NOT be treated directly as residue mass or cover
   percentage without a locally calibrated :class:`TransectCalibrationModel`
   (``calibrated_locally=True``, ``slope``, ``intercept``, ``standard_error``,
   and optional valid ``ndti_range``). Missing or uncalibrated local
   calibration returns ``Missing(reason="NOT_COMPUTABLE", detail="...uncalibrated NDTI...")``
   for quantitative residue cover and preserves the tabular fallback.
2. Masked, cloudy, or sparse scenes (``cloud_masked=True`` or
   ``valid_pixel_fraction < min_valid_fraction``) or empty scene lists return
   ``NO_COVERAGE`` / ``MISSING_INPUT``, never ``0.0``.
3. Side-by-side comparison (:class:`ResidueCoverSubfactorComparison`) keeps
   ``tabular_subfactor`` and ``observed_hypothesis_subfactor`` separate and
   is tagged ``never_overwrites_normative_c=True``.

Pure functions (G1): no file I/O, no network calls, no clock reads, no
environment variables, and no mutation of caller arguments.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from contracts.results.models import Range
from engine.erosion.c_factor.subfactors import surface_cover_subfactor_percent

__all__ = [
    "AGGREGATION_MODES",
    "CALIBRATION_OUTPUT_UNITS",
    "OBSERVATION_CLASS",
    "STATUS",
    "SUPPORTED_SENSORS",
    "ObservedResidueCoverEstimate",
    "ResidueCoverSubfactorComparison",
    "SatelliteSceneObservation",
    "TransectCalibrationModel",
    "compare_residue_cover_subfactors",
    "evaluate_observed_residue_cover",
    "ndti_to_residue_cover",
]

STATUS = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
OBSERVATION_CLASS: Literal["HYPOTHESIS"] = "HYPOTHESIS"
SUPPORTED_SENSORS: tuple[str, ...] = ("EMIT", "HLS")
AGGREGATION_MODES: tuple[str, ...] = ("mean", "latest", "weighted_by_valid_pixels")
CALIBRATION_OUTPUT_UNITS: tuple[str, ...] = ("fraction", "percent")

# Universal definition of percent (parts per hundred), not a method constant.
_PERCENT_PER_FRACTION = 100.0
_MISSING_TYPES = (InputMissing, ResultMissing)

Number = int | float
NumberOrMissing = int | float | InputMissing | ResultMissing
SensorType = Literal["EMIT", "HLS"]
AggregationMode = Literal["mean", "latest", "weighted_by_valid_pixels"]
CalibrationOutputUnit = Literal["fraction", "percent"]


@dataclass(frozen=True)
class TransectCalibrationModel:
    """Local field-transect regression mapping HLS NDTI to residue cover.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    ``cover = intercept + slope * ndti`` in ``output_unit`` (``"fraction"`` in
    ``[0, 1]`` or ``"percent"`` in ``[0, 100]``). ``calibrated_locally`` must
    be ``True`` before any quantitative cover or subfactor may be computed.
    """

    calibrated_locally: bool
    slope: NumberOrMissing
    intercept: NumberOrMissing
    standard_error: NumberOrMissing
    ndti_range: tuple[float, float] | None = None
    output_unit: CalibrationOutputUnit = "fraction"
    calibration_id: str | None = None


@dataclass(frozen=True)
class SatelliteSceneObservation:
    """One satellite scene observation for dry-cover / residue evaluation.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Supports ``EMIT`` fractional non-photosynthetic vegetation
    (``npv_fraction``) and ``HLS`` ``NDTI`` observations.
    """

    sensor: SensorType
    observation_date: dt.date
    valid_pixel_fraction: NumberOrMissing
    npv_fraction: NumberOrMissing | None = None
    ndti: NumberOrMissing | None = None
    cloud_masked: bool = False
    uncertainty: NumberOrMissing | None = None
    source: str | None = None


@dataclass(frozen=True)
class ObservedResidueCoverEstimate:
    """Evaluated satellite residue cover and ``HYPOTHESIS`` surface-cover subfactor.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    cover_fraction: float | ResultMissing
    subfactor: float | ResultMissing
    sensor: SensorType | None
    cover_range: Range | None
    cover_range_missing: ResultMissing | None
    subfactor_range: Range | None
    subfactor_range_missing: ResultMissing | None
    scene_count: int
    valid_scene_count: int
    rejected_scene_count: int
    rejection_reasons: tuple[str, ...]
    aggregation: AggregationMode
    status: str = STATUS
    observation_class: Literal["HYPOTHESIS"] = OBSERVATION_CLASS
    never_overwrites_normative_c: bool = True

    def __post_init__(self) -> None:
        if self.never_overwrites_normative_c is not True:
            raise ValueError("never_overwrites_normative_c must remain True")
        if self.observation_class != OBSERVATION_CLASS:
            raise ValueError(f"observation_class must be '{OBSERVATION_CLASS}'")


@dataclass(frozen=True)
class ResidueCoverSubfactorComparison:
    """Side-by-side comparison of tabular ``C`` surface-cover subfactor and
    observed satellite ``HYPOTHESIS`` surface-cover subfactor.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Keeps ``tabular_subfactor`` and ``observed_hypothesis_subfactor`` separate
    and tagged ``never_overwrites_normative_c=True``.
    """

    tabular_cover_fraction: float | ResultMissing
    tabular_subfactor: float | ResultMissing
    observed_cover_fraction: float | ResultMissing
    observed_hypothesis_subfactor: float | ResultMissing
    subfactor_difference: float | ResultMissing
    cover_difference: float | ResultMissing
    observed_sensor: SensorType | None
    observed_cover_range: Range | None
    observed_cover_range_missing: ResultMissing | None
    observed_subfactor_range: Range | None
    observed_subfactor_range_missing: ResultMissing | None
    scene_count: int
    valid_scene_count: int
    rejected_scene_count: int
    rejection_reasons: tuple[str, ...]
    status: str = STATUS
    observation_class: Literal["HYPOTHESIS"] = OBSERVATION_CLASS
    never_overwrites_normative_c: bool = True

    def __post_init__(self) -> None:
        if self.never_overwrites_normative_c is not True:
            raise ValueError("never_overwrites_normative_c must remain True")
        if self.observation_class != OBSERVATION_CLASS:
            raise ValueError(f"observation_class must be '{OBSERVATION_CLASS}'")


def _is_missing(item: object) -> bool:
    return isinstance(item, _MISSING_TYPES)


def _describe_missing(name: str, missing: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {missing.reason}"
    if missing.detail is not None:
        text += f": {missing.detail}"
    return text


def _check_number_or_missing(name: str, item: object) -> None:
    if _is_missing(item):
        return
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise TypeError(
            f"{name}: expected a number or a Missing of the contract models, "
            f"got {type(item).__name__}"
        )


def _finite_float(item: Number) -> float | None:
    try:
        value = float(item)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _check_date(name: str, item: object) -> None:
    if isinstance(item, dt.datetime) or not isinstance(item, dt.date):
        raise TypeError(
            f"{name}: expected datetime.date (not datetime), got {type(item).__name__}"
        )


def _check_calibration_type(calibration: object) -> None:
    if calibration is None or _is_missing(calibration):
        return
    if not isinstance(calibration, TransectCalibrationModel):
        raise TypeError(
            "calibration: expected TransectCalibrationModel, Missing, or None, "
            f"got {type(calibration).__name__}"
        )
    if not isinstance(calibration.calibrated_locally, bool):
        raise TypeError(
            "calibration.calibrated_locally: expected bool, "
            f"got {type(calibration.calibrated_locally).__name__}"
        )
    _check_number_or_missing("calibration.slope", calibration.slope)
    _check_number_or_missing("calibration.intercept", calibration.intercept)
    _check_number_or_missing("calibration.standard_error", calibration.standard_error)
    if not isinstance(calibration.output_unit, str):
        raise TypeError(
            "calibration.output_unit: expected str, "
            f"got {type(calibration.output_unit).__name__}"
        )
    if calibration.calibration_id is not None and not isinstance(
        calibration.calibration_id, str
    ):
        raise TypeError(
            "calibration.calibration_id: expected str or None, "
            f"got {type(calibration.calibration_id).__name__}"
        )
    if calibration.ndti_range is not None:
        if (
            not isinstance(calibration.ndti_range, tuple)
            or len(calibration.ndti_range) != 2
        ):
            raise TypeError("calibration.ndti_range: expected a 2-tuple or None")
        _check_number_or_missing("calibration.ndti_range[0]", calibration.ndti_range[0])
        _check_number_or_missing("calibration.ndti_range[1]", calibration.ndti_range[1])


def _check_observation_types(observations: object) -> None:
    if _is_missing(observations):
        return
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise TypeError(
            "observations: expected a Sequence of SatelliteSceneObservation or Missing, "
            f"got {type(observations).__name__}"
        )
    for idx, obs in enumerate(observations):
        if not isinstance(obs, SatelliteSceneObservation):
            raise TypeError(
                f"observations[{idx}]: expected SatelliteSceneObservation, "
                f"got {type(obs).__name__}"
            )
        if not isinstance(obs.sensor, str):
            raise TypeError(
                f"observations[{idx}].sensor: expected str, "
                f"got {type(obs.sensor).__name__}"
            )
        _check_date(f"observations[{idx}].observation_date", obs.observation_date)
        _check_number_or_missing(
            f"observations[{idx}].valid_pixel_fraction", obs.valid_pixel_fraction
        )
        if obs.npv_fraction is not None:
            _check_number_or_missing(
                f"observations[{idx}].npv_fraction", obs.npv_fraction
            )
        if obs.ndti is not None:
            _check_number_or_missing(f"observations[{idx}].ndti", obs.ndti)
        if not isinstance(obs.cloud_masked, bool):
            raise TypeError(
                f"observations[{idx}].cloud_masked: expected bool, "
                f"got {type(obs.cloud_masked).__name__}"
            )
        if obs.uncertainty is not None:
            _check_number_or_missing(
                f"observations[{idx}].uncertainty", obs.uncertainty
            )
        if obs.source is not None and not isinstance(obs.source, str):
            raise TypeError(
                f"observations[{idx}].source: expected str or None, "
                f"got {type(obs.source).__name__}"
            )


def _validate_calibrated_model(
    calibration: TransectCalibrationModel | InputMissing | ResultMissing | None,
) -> (
    tuple[float, float, float, tuple[float, float] | None, CalibrationOutputUnit]
    | ResultMissing
):
    """Validate local NDTI calibration and extract finite parameters."""
    if calibration is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "uncalibrated NDTI: no TransectCalibrationModel provided; raw NDTI "
                "cannot be treated as residue mass or cover percentage"
            ),
        )
    if _is_missing(calibration):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "uncalibrated NDTI: local transect calibration is absent ("
                f"{_describe_missing('calibration', calibration)})"
            ),
        )
    if not calibration.calibrated_locally:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                "uncalibrated NDTI: TransectCalibrationModel has "
                "calibrated_locally=False; local field-transect calibration is required"
            ),
        )
    if calibration.output_unit not in CALIBRATION_OUTPUT_UNITS:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"calibration.output_unit '{calibration.output_unit}' is not accepted; "
                f"expected one of {CALIBRATION_OUTPUT_UNITS}"
            ),
        )
    missing_fields = [
        _describe_missing(name, value)
        for name, value in (
            ("calibration.slope", calibration.slope),
            ("calibration.intercept", calibration.intercept),
            ("calibration.standard_error", calibration.standard_error),
        )
        if _is_missing(value)
    ]
    if missing_fields:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(missing_fields))

    slope = _finite_float(calibration.slope)  # type: ignore[arg-type]
    intercept = _finite_float(calibration.intercept)  # type: ignore[arg-type]
    standard_error = _finite_float(calibration.standard_error)  # type: ignore[arg-type]
    non_finite = [
        name
        for name, val in (
            ("calibration.slope", slope),
            ("calibration.intercept", intercept),
            ("calibration.standard_error", standard_error),
        )
        if val is None
    ]
    if non_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in non_finite),
        )
    assert slope is not None and intercept is not None and standard_error is not None
    if standard_error < 0.0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="calibration.standard_error is negative",
        )

    ndti_bounds: tuple[float, float] | None = None
    if calibration.ndti_range is not None:
        low = _finite_float(calibration.ndti_range[0])
        high = _finite_float(calibration.ndti_range[1])
        if low is None or high is None:
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail="calibration.ndti_range contains a non-finite bound",
            )
        if low > high:
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail="calibration.ndti_range lower bound exceeds upper bound",
            )
        ndti_bounds = (low, high)

    return slope, intercept, standard_error, ndti_bounds, calibration.output_unit


def ndti_to_residue_cover(
    *,
    ndti: NumberOrMissing,
    calibration: TransectCalibrationModel | InputMissing | ResultMissing | None,
) -> float | ResultMissing:
    """Convert raw ``HLS`` ``NDTI`` to residue cover fraction ``[0, 1]``.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Enforces rule 27 §5.6: raw ``NDTI`` MUST NOT be treated directly as
    residue mass or cover percentage without a locally calibrated
    :class:`TransectCalibrationModel` (``calibrated_locally=True``).
    Missing or uncalibrated local calibration returns
    ``Missing(reason="NOT_COMPUTABLE", detail="...uncalibrated NDTI...")``.
    Predicted cover outside ``[0, 1]`` or ``ndti`` outside ``ndti_range`` is
    refused as ``NOT_COMPUTABLE`` and never clipped.
    """
    _check_number_or_missing("ndti", ndti)
    _check_calibration_type(calibration)

    calibrated = _validate_calibrated_model(calibration)
    if isinstance(calibrated, ResultMissing):
        return calibrated
    slope, intercept, _se, ndti_bounds, output_unit = calibrated

    if _is_missing(ndti):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=_describe_missing("ndti", ndti),  # type: ignore[arg-type]
        )
    ndti_val = _finite_float(ndti)  # type: ignore[arg-type]
    if ndti_val is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="ndti is not a finite number"
        )
    if ndti_bounds is not None and not (ndti_bounds[0] <= ndti_val <= ndti_bounds[1]):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"ndti ({ndti_val}) lies outside calibrated transect ndti_range "
                f"[{ndti_bounds[0]}, {ndti_bounds[1]}]"
            ),
        )

    raw_cover = intercept + slope * ndti_val
    cover_fraction = (
        raw_cover / _PERCENT_PER_FRACTION if output_unit == "percent" else raw_cover
    )
    if not math.isfinite(cover_fraction):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="calibrated NDTI cover prediction is not a finite real number",
        )
    if not (0.0 <= cover_fraction <= 1.0):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"calibrated residue cover fraction ({cover_fraction}) lies outside "
                "zero to one; nothing is clipped"
            ),
        )
    return cover_fraction


@dataclass(frozen=True)
class _AcceptedScene:
    date: dt.date
    cover_fraction: float
    valid_pixel_fraction: float
    uncertainty_fraction: float | None


@dataclass(frozen=True)
class _RejectedScene:
    passed_coverage: bool
    missing: ResultMissing


def _evaluate_single_scene(
    obs: SatelliteSceneObservation,
    *,
    min_valid_fraction: float,
    calibration: TransectCalibrationModel | InputMissing | ResultMissing | None,
) -> _AcceptedScene | _RejectedScene:
    if obs.cloud_masked:
        return _RejectedScene(
            passed_coverage=False,
            missing=ResultMissing(
                reason="NO_COVERAGE",
                detail=f"{obs.observation_date.isoformat()}: scene is cloud-masked",
            ),
        )

    if _is_missing(obs.valid_pixel_fraction):
        return _RejectedScene(
            passed_coverage=False,
            missing=ResultMissing(
                reason="MISSING_INPUT",
                detail=(
                    f"{obs.observation_date.isoformat()}: "
                    f"{_describe_missing('valid_pixel_fraction', obs.valid_pixel_fraction)}"  # type: ignore[arg-type]
                ),
            ),
        )

    valid_px = _finite_float(obs.valid_pixel_fraction)  # type: ignore[arg-type]
    if valid_px is None or not (0.0 <= valid_px <= 1.0):
        return _RejectedScene(
            passed_coverage=False,
            missing=ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{obs.observation_date.isoformat()}: valid_pixel_fraction must "
                    "be a finite number in [0, 1]"
                ),
            ),
        )

    if valid_px < min_valid_fraction:
        return _RejectedScene(
            passed_coverage=False,
            missing=ResultMissing(
                reason="NO_COVERAGE",
                detail=(
                    f"{obs.observation_date.isoformat()}: sparse/masked scene "
                    f"(valid_pixel_fraction={valid_px} < min_valid_fraction={min_valid_fraction})"
                ),
            ),
        )

    if obs.sensor == "EMIT":
        if obs.npv_fraction is None:
            return _RejectedScene(
                passed_coverage=True,
                missing=ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"{obs.observation_date.isoformat()}: EMIT scene is missing "
                        "npv_fraction"
                    ),
                ),
            )
        if _is_missing(obs.npv_fraction):
            return _RejectedScene(
                passed_coverage=True,
                missing=ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"{obs.observation_date.isoformat()}: "
                        f"{_describe_missing('npv_fraction', obs.npv_fraction)}"  # type: ignore[arg-type]
                    ),
                ),
            )
        npv = _finite_float(obs.npv_fraction)  # type: ignore[arg-type]
        if npv is None or not (0.0 <= npv <= 1.0):
            return _RejectedScene(
                passed_coverage=True,
                missing=ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"{obs.observation_date.isoformat()}: EMIT npv_fraction must "
                        "be a finite number in [0, 1]"
                    ),
                ),
            )
        uncertainty_fraction: float | None = None
        if obs.uncertainty is not None and not _is_missing(obs.uncertainty):
            u_val = _finite_float(obs.uncertainty)  # type: ignore[arg-type]
            if u_val is None or u_val < 0.0:
                return _RejectedScene(
                    passed_coverage=True,
                    missing=ResultMissing(
                        reason="NOT_COMPUTABLE",
                        detail=(
                            f"{obs.observation_date.isoformat()}: scene uncertainty "
                            "must be a non-negative finite number"
                        ),
                    ),
                )
            uncertainty_fraction = u_val
        return _AcceptedScene(
            date=obs.observation_date,
            cover_fraction=npv,
            valid_pixel_fraction=valid_px,
            uncertainty_fraction=uncertainty_fraction,
        )

    # HLS NDTI path
    if obs.ndti is None:
        return _RejectedScene(
            passed_coverage=True,
            missing=ResultMissing(
                reason="MISSING_INPUT",
                detail=f"{obs.observation_date.isoformat()}: HLS scene is missing ndti",
            ),
        )
    cover = ndti_to_residue_cover(ndti=obs.ndti, calibration=calibration)
    if isinstance(cover, ResultMissing):
        return _RejectedScene(passed_coverage=True, missing=cover)

    se_fraction: float | None = None
    if isinstance(calibration, TransectCalibrationModel):
        se_val = _finite_float(calibration.standard_error)  # type: ignore[arg-type]
        if se_val is not None:
            se_fraction = (
                se_val / _PERCENT_PER_FRACTION
                if calibration.output_unit == "percent"
                else se_val
            )
    return _AcceptedScene(
        date=obs.observation_date,
        cover_fraction=cover,
        valid_pixel_fraction=valid_px,
        uncertainty_fraction=se_fraction,
    )


def _select_no_valid_scene_reason(rejected: Sequence[_RejectedScene]) -> ResultMissing:
    for item in rejected:
        if item.passed_coverage and item.missing.reason == "NOT_COMPUTABLE":
            return item.missing
    for item in rejected:
        if item.passed_coverage and item.missing.reason == "MISSING_INPUT":
            return item.missing
    for item in rejected:
        if not item.passed_coverage and item.missing.reason == "NO_COVERAGE":
            return item.missing
    for item in rejected:
        if not item.passed_coverage and item.missing.reason == "NOT_COMPUTABLE":
            return item.missing
    return rejected[0].missing


def _aggregate_cover(
    accepted: Sequence[_AcceptedScene],
    aggregation: AggregationMode,
) -> tuple[float, float | None]:
    if aggregation == "mean":
        cover = sum(item.cover_fraction for item in accepted) / len(accepted)
        se_vals = [
            item.uncertainty_fraction
            for item in accepted
            if item.uncertainty_fraction is not None
        ]
        uncertainty = (
            max(se_vals) if len(se_vals) == len(accepted) and se_vals else None
        )
        return cover, uncertainty
    if aggregation == "weighted_by_valid_pixels":
        total_weight = sum(item.valid_pixel_fraction for item in accepted)
        cover = (
            sum(item.valid_pixel_fraction * item.cover_fraction for item in accepted)
            / total_weight
        )
        se_vals = [
            item.uncertainty_fraction
            for item in accepted
            if item.uncertainty_fraction is not None
        ]
        uncertainty = (
            max(se_vals) if len(se_vals) == len(accepted) and se_vals else None
        )
        return cover, uncertainty
    # "latest"
    latest = max(accepted, key=lambda item: item.date)
    return latest.cover_fraction, latest.uncertainty_fraction


def _build_ranges(
    *,
    cover_fraction: float,
    uncertainty_fraction: float | None,
    range_kind: str,
    subfactor: float | ResultMissing,
    surface_cover_coefficient_per_percent: NumberOrMissing,
) -> tuple[Range | None, ResultMissing | None, Range | None, ResultMissing | None]:
    if uncertainty_fraction is None:
        missing_range = ResultMissing(
            reason="NOT_AVAILABLE",
            detail="no observation uncertainty supplied to build cover range",
        )
        sub_missing = (
            ResultMissing(
                reason="NOT_AVAILABLE",
                detail="no observation uncertainty supplied to build subfactor range",
            )
            if isinstance(subfactor, float)
            else None
        )
        return None, missing_range, None, sub_missing

    if uncertainty_fraction == 0.0:
        zero_cover_missing = ResultMissing(
            reason="NOT_APPLICABLE",
            detail="zero uncertainty collapses cover range to a point",
        )
        zero_sub_missing = (
            ResultMissing(
                reason="NOT_APPLICABLE",
                detail="zero uncertainty collapses subfactor range to a point",
            )
            if isinstance(subfactor, float)
            else None
        )
        return None, zero_cover_missing, None, zero_sub_missing

    c_low = max(0.0, cover_fraction - uncertainty_fraction)
    c_high = min(1.0, cover_fraction + uncertainty_fraction)
    if not (c_low < c_high):
        collapsed = ResultMissing(
            reason="NOT_APPLICABLE",
            detail="bounded cover interval collapsed to a single point",
        )
        return (
            None,
            collapsed,
            None,
            collapsed if isinstance(subfactor, float) else None,
        )

    cover_range = Range(low=c_low, high=c_high, kind=range_kind)

    if not isinstance(subfactor, float):
        return cover_range, None, None, None

    # exp(-b * 100 * cover) decreases monotonically with cover for b >= 0.
    s_low = surface_cover_subfactor_percent(
        surface_residue_cover=c_high,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
    )
    s_high = surface_cover_subfactor_percent(
        surface_residue_cover=c_low,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
    )
    if isinstance(s_low, float) and isinstance(s_high, float) and s_low < s_high:
        return (
            cover_range,
            None,
            Range(low=s_low, high=s_high, kind=range_kind),
            None,
        )
    return (
        cover_range,
        None,
        None,
        ResultMissing(
            reason="NOT_APPLICABLE",
            detail="zero surface-cover coefficient collapses subfactor range to a point",
        ),
    )


def _missing_estimate(
    *,
    missing: ResultMissing,
    sensor: SensorType | None,
    scene_count: int,
    rejected_scene_count: int,
    rejection_reasons: tuple[str, ...],
    aggregation: AggregationMode,
) -> ObservedResidueCoverEstimate:
    return ObservedResidueCoverEstimate(
        cover_fraction=missing,
        subfactor=missing,
        sensor=sensor,
        cover_range=None,
        cover_range_missing=None,
        subfactor_range=None,
        subfactor_range_missing=None,
        scene_count=scene_count,
        valid_scene_count=0,
        rejected_scene_count=rejected_scene_count,
        rejection_reasons=rejection_reasons,
        aggregation=aggregation,
    )


def evaluate_observed_residue_cover(
    *,
    observations: Sequence[SatelliteSceneObservation] | InputMissing | ResultMissing,
    min_valid_fraction: NumberOrMissing,
    surface_cover_coefficient_per_percent: NumberOrMissing,
    calibration: TransectCalibrationModel | InputMissing | ResultMissing | None = None,
    aggregation: AggregationMode = "mean",
) -> ObservedResidueCoverEstimate:
    """Evaluate satellite dry-cover / residue fraction and ``HYPOTHESIS`` subfactor.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    All coefficients and thresholds (``min_valid_fraction``,
    ``surface_cover_coefficient_per_percent``, and ``TransectCalibrationModel``)
    are supplied by the caller with zero hardcoded scientific parameters.
    """
    _check_observation_types(observations)
    _check_number_or_missing("min_valid_fraction", min_valid_fraction)
    _check_number_or_missing(
        "surface_cover_coefficient_per_percent", surface_cover_coefficient_per_percent
    )
    _check_calibration_type(calibration)
    if not isinstance(aggregation, str):
        raise TypeError(f"aggregation: expected str, got {type(aggregation).__name__}")
    if aggregation not in AGGREGATION_MODES:
        raise ValueError(
            f"aggregation '{aggregation}' is not supported; expected one of {AGGREGATION_MODES}"
        )

    if _is_missing(observations):
        return _missing_estimate(
            missing=ResultMissing(
                reason="MISSING_INPUT",
                detail=_describe_missing("observations", observations),  # type: ignore[arg-type]
            ),
            sensor=None,
            scene_count=0,
            rejected_scene_count=0,
            rejection_reasons=(),
            aggregation=aggregation,
        )

    scene_list = list(observations)  # type: ignore[arg-type]
    if not scene_list:
        return _missing_estimate(
            missing=ResultMissing(
                reason="NO_COVERAGE",
                detail="no satellite residue-cover scenes provided for this field/period",
            ),
            sensor=None,
            scene_count=0,
            rejected_scene_count=0,
            rejection_reasons=(),
            aggregation=aggregation,
        )

    if _is_missing(min_valid_fraction):
        return _missing_estimate(
            missing=ResultMissing(
                reason="MISSING_INPUT",
                detail=_describe_missing("min_valid_fraction", min_valid_fraction),  # type: ignore[arg-type]
            ),
            sensor=None,
            scene_count=len(scene_list),
            rejected_scene_count=len(scene_list),
            rejection_reasons=(),
            aggregation=aggregation,
        )

    min_valid_val = _finite_float(min_valid_fraction)  # type: ignore[arg-type]
    if min_valid_val is None or not (0.0 < min_valid_val <= 1.0):
        return _missing_estimate(
            missing=ResultMissing(
                reason="NOT_COMPUTABLE",
                detail="min_valid_fraction must be a finite number in (0, 1]",
            ),
            sensor=None,
            scene_count=len(scene_list),
            rejected_scene_count=len(scene_list),
            rejection_reasons=(),
            aggregation=aggregation,
        )

    sensors = {obs.sensor for obs in scene_list}
    unsupported = sorted(s for s in sensors if s not in SUPPORTED_SENSORS)
    if unsupported:
        return _missing_estimate(
            missing=ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"unsupported satellite sensor(s) {unsupported}; "
                    f"expected one of {SUPPORTED_SENSORS}"
                ),
            ),
            sensor=None,
            scene_count=len(scene_list),
            rejected_scene_count=len(scene_list),
            rejection_reasons=(),
            aggregation=aggregation,
        )
    if len(sensors) > 1:
        return _missing_estimate(
            missing=ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    "cannot mix EMIT and HLS observations in a single residue-cover "
                    "estimate; evaluate each sensor separately"
                ),
            ),
            sensor=None,
            scene_count=len(scene_list),
            rejected_scene_count=len(scene_list),
            rejection_reasons=(),
            aggregation=aggregation,
        )

    sensor: SensorType = next(iter(sensors))  # type: ignore[assignment]
    accepted: list[_AcceptedScene] = []
    rejected: list[_RejectedScene] = []
    rejection_reasons: list[str] = []

    for obs in scene_list:
        outcome = _evaluate_single_scene(
            obs, min_valid_fraction=min_valid_val, calibration=calibration
        )
        if isinstance(outcome, _AcceptedScene):
            accepted.append(outcome)
        else:
            rejected.append(outcome)
            if outcome.missing.detail is not None:
                rejection_reasons.append(
                    f"{outcome.missing.reason}: {outcome.missing.detail}"
                )
            else:
                rejection_reasons.append(outcome.missing.reason)

    if not accepted:
        return _missing_estimate(
            missing=_select_no_valid_scene_reason(rejected),
            sensor=sensor,
            scene_count=len(scene_list),
            rejected_scene_count=len(rejected),
            rejection_reasons=tuple(rejection_reasons),
            aggregation=aggregation,
        )

    cover_fraction, uncertainty_fraction = _aggregate_cover(accepted, aggregation)
    subfactor = surface_cover_subfactor_percent(
        surface_residue_cover=cover_fraction,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
    )
    range_kind = (
        "transect_calibration_standard_error"
        if sensor == "HLS"
        else "emit_npv_uncertainty"
    )
    cover_range, cover_range_missing, sub_range, sub_range_missing = _build_ranges(
        cover_fraction=cover_fraction,
        uncertainty_fraction=uncertainty_fraction,
        range_kind=range_kind,
        subfactor=subfactor,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
    )

    return ObservedResidueCoverEstimate(
        cover_fraction=cover_fraction,
        subfactor=subfactor,
        sensor=sensor,
        cover_range=cover_range,
        cover_range_missing=cover_range_missing,
        subfactor_range=sub_range,
        subfactor_range_missing=sub_range_missing,
        scene_count=len(scene_list),
        valid_scene_count=len(accepted),
        rejected_scene_count=len(rejected),
        rejection_reasons=tuple(rejection_reasons),
        aggregation=aggregation,
    )


def _validate_tabular_cover(
    tabular_residue_cover: NumberOrMissing,
) -> float | ResultMissing:
    if _is_missing(tabular_residue_cover):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=_describe_missing("tabular_residue_cover", tabular_residue_cover),  # type: ignore[arg-type]
        )
    value = _finite_float(tabular_residue_cover)  # type: ignore[arg-type]
    if value is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="tabular_residue_cover is not a finite number",
        )
    if not (0.0 <= value <= 1.0):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="tabular_residue_cover is outside zero to one",
        )
    return value


def _paired_difference(
    observed: float | ResultMissing,
    tabular: float | ResultMissing,
    *,
    label: str,
) -> float | ResultMissing:
    if isinstance(observed, ResultMissing) or isinstance(tabular, ResultMissing):
        parts = []
        if isinstance(observed, ResultMissing):
            parts.append(_describe_missing(f"observed_{label}", observed))
        if isinstance(tabular, ResultMissing):
            parts.append(_describe_missing(f"tabular_{label}", tabular))
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(parts))
    diff = observed - tabular
    if not math.isfinite(diff):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{label}_difference is not a finite real number",
        )
    return diff


def compare_residue_cover_subfactors(
    *,
    tabular_residue_cover: NumberOrMissing,
    observations: Sequence[SatelliteSceneObservation] | InputMissing | ResultMissing,
    min_valid_fraction: NumberOrMissing,
    surface_cover_coefficient_per_percent: NumberOrMissing,
    calibration: TransectCalibrationModel | InputMissing | ResultMissing | None = None,
    aggregation: AggregationMode = "mean",
) -> ResidueCoverSubfactorComparison:
    """Compare tabular ``C`` surface-cover subfactor with satellite ``HYPOTHESIS``.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Enforces rule 27 §7: ``tabular_subfactor`` and
    ``observed_hypothesis_subfactor`` are kept strictly separate, and the result
    is always tagged ``never_overwrites_normative_c=True``. Failure or absence
    of the satellite path (e.g. uncalibrated NDTI or masked scenes) preserves
    the tabular fallback intact.
    """
    _check_number_or_missing("tabular_residue_cover", tabular_residue_cover)
    _check_number_or_missing(
        "surface_cover_coefficient_per_percent", surface_cover_coefficient_per_percent
    )

    tabular_cover = _validate_tabular_cover(tabular_residue_cover)
    tabular_subfactor = surface_cover_subfactor_percent(
        surface_residue_cover=tabular_residue_cover,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
    )

    observed = evaluate_observed_residue_cover(
        observations=observations,
        min_valid_fraction=min_valid_fraction,
        surface_cover_coefficient_per_percent=surface_cover_coefficient_per_percent,
        calibration=calibration,
        aggregation=aggregation,
    )

    cover_diff = _paired_difference(
        observed.cover_fraction, tabular_cover, label="cover"
    )
    subfactor_diff = _paired_difference(
        observed.subfactor, tabular_subfactor, label="subfactor"
    )

    return ResidueCoverSubfactorComparison(
        tabular_cover_fraction=tabular_cover,
        tabular_subfactor=tabular_subfactor,
        observed_cover_fraction=observed.cover_fraction,
        observed_hypothesis_subfactor=observed.subfactor,
        subfactor_difference=subfactor_diff,
        cover_difference=cover_diff,
        observed_sensor=observed.sensor,
        observed_cover_range=observed.cover_range,
        observed_cover_range_missing=observed.cover_range_missing,
        observed_subfactor_range=observed.subfactor_range,
        observed_subfactor_range_missing=observed.subfactor_range_missing,
        scene_count=observed.scene_count,
        valid_scene_count=observed.valid_scene_count,
        rejected_scene_count=observed.rejected_scene_count,
        rejection_reasons=observed.rejection_reasons,
    )
