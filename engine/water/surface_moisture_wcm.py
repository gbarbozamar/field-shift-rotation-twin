"""Sentinel-1/Sentinel-2 Water Cloud Model (WCM) surface soil moisture estimator.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements the Attema–Ulaby Water Cloud Model (WCM) forward backscatter model
and bounded monotonic bisection inversion for 0–5 cm volumetric soil moisture
(``m_v`` in ``m3 m-3``), combining Sentinel-1 ``sigma0`` (``VV`` or ``VH``,
explicitly typed as ``linear`` or ``dB``) and a Sentinel-2 vegetation
descriptor (``NDVI`` or ``LAI``).

Design and scientific guards (Rev13 §3):
1. **Surface-only depth & estimator role:** depth is strictly ``"0_to_5_cm"``;
   ``SurfaceMoistureEstimate`` always carries ``observes_root_zone=False`` and
   ``estimator_role="SURFACE_INPUT_ESTIMATOR"``. This module never substitutes
   for root-zone soil water balance.
2. **Caller-supplied calibration & QA bounds (Blueprint §3.5):** every WCM
   calibration parameter and QA threshold travels in ``WcmParameters`` with zero
   hardcoded calibration values or threshold constants in this module.
3. **Transfer disclosure & typed rejection (C3.1, C3.2, G4):**
   ``local_transfer_validated`` defaults to ``False``. Invalid QA, excessive
   ``s1_s2_delta_days``, out-of-range backscatter, or insufficient valid pixels
   return typed ``Missing`` (``NO_COVERAGE``, ``MISSING_INPUT``, or
   ``CONTROL_FAILED``), never ``0.0``.
4. **Anti-circular validation guard:** ``validate_surface_moisture_benchmark``
   raises ``ValueError`` if ``"INDEPENDENT_FIELD_VALIDATION"`` is claimed when
   ``calibration_reference == "SMAP"`` and ``validation_reference == "SMAP"``
   (or when calibration and validation references are identical).

Pure function (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and arguments are never modified.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing

__all__ = [
    "BACKSCATTER_UNITS",
    "BENCHMARK_LEVELS",
    "DEPTH_BAND_SURFACE",
    "ESTIMATOR_ROLE_SURFACE",
    "ORBIT_DIRECTIONS",
    "POLARIZATIONS",
    "PROPOSED_STATUS",
    "SOIL_MODELS",
    "UNIT_VOLUMETRIC_MOISTURE",
    "VEGETATION_DESCRIPTORS",
    "BackscatterUnit",
    "ClaimedValidationLevel",
    "OrbitDirection",
    "ParcelWcmObservation",
    "PixelWcmSample",
    "Polarization",
    "SoilModel",
    "SurfaceMoistureBenchmarkReport",
    "SurfaceMoistureEstimate",
    "VegetationDescriptor",
    "WcmForwardResult",
    "WcmParameters",
    "aggregate_parcel_qa",
    "db_to_linear",
    "estimate_surface_moisture",
    "linear_to_db",
    "validate_surface_moisture_benchmark",
    "wcm_closed_form_moisture",
    "wcm_forward_backscatter",
    "wcm_invert_moisture",
]

PROPOSED_STATUS = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
DEPTH_BAND_SURFACE: Literal["0_to_5_cm"] = "0_to_5_cm"
ESTIMATOR_ROLE_SURFACE: Literal["SURFACE_INPUT_ESTIMATOR"] = "SURFACE_INPUT_ESTIMATOR"
UNIT_VOLUMETRIC_MOISTURE: Literal["m3 m-3"] = "m3 m-3"

POLARIZATIONS = ("VV", "VH")
BACKSCATTER_UNITS = ("linear", "dB")
VEGETATION_DESCRIPTORS = ("NDVI", "LAI")
ORBIT_DIRECTIONS = ("ASCENDING", "DESCENDING")
SOIL_MODELS = ("db_linear", "linear")
BENCHMARK_LEVELS = (
    "INDEPENDENT_FIELD_VALIDATION",
    "SATELLITE_INTERCOMPARISON",
    "UNVALIDATED_TRANSFER",
)

Polarization = Literal["VV", "VH"]
BackscatterUnit = Literal["linear", "dB"]
VegetationDescriptor = Literal["NDVI", "LAI"]
OrbitDirection = Literal["ASCENDING", "DESCENDING"]
SoilModel = Literal["db_linear", "linear"]
ClaimedValidationLevel = Literal[
    "INDEPENDENT_FIELD_VALIDATION",
    "SATELLITE_INTERCOMPARISON",
    "UNVALIDATED_TRANSFER",
]


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_real_number(value: object) -> bool:
    """True for ``int`` or ``float`` excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: object) -> bool:
    """True when ``value`` is a finite ``int`` or ``float`` (excluding ``bool``)."""
    if not _is_real_number(value):
        return False
    assert isinstance(value, (int, float))
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _require_finite_float(name: str, value: object) -> float:
    """Validate a required caller-supplied finite numeric parameter (G5)."""
    if not _is_real_number(value):
        raise TypeError(
            f"{name}: expected float or int, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name}: expected finite number, got {value!r}")
    return result


def _require_optional_finite_float(name: str, value: object) -> float | None:
    """Validate an optional finite numeric parameter (G5)."""
    if value is None:
        return None
    return _require_finite_float(name, value)


def _require_optional_positive_int(name: str, value: object) -> int | None:
    """Validate an optional strictly positive ``int`` excluding ``bool`` (G5)."""
    if value is None:
        return None
    if not _is_strict_int(value):
        raise TypeError(f"{name}: expected int, got {type(value).__name__} (G5)")
    assert isinstance(value, int)
    if value <= 0:
        raise ValueError(f"{name}: expected positive int, got {value}")
    return value


def _require_choice(name: str, value: object, allowed: tuple[str, ...]) -> str:
    """Validate a closed string vocabulary field (G5)."""
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if value not in allowed:
        raise ValueError(f"{name}: expected one of {allowed}, got {value!r}")
    return value


def _to_result_missing(value: Missing | InputMissing) -> Missing:
    """Normalize an input or result ``Missing`` into ``contracts.results.models.Missing``."""
    if isinstance(value, Missing):
        return value
    return Missing(reason=value.reason, detail=value.detail)


def _missing_or_check_number(
    field: str, value: object
) -> tuple[float | None, Missing | None]:
    """Validate an observation numeric field that may be ``Missing`` or ``None``.

    Returns ``(float_value, None)`` when finite, ``(None, Missing)`` when
    missing or non-finite, and raises ``TypeError`` on wrong caller types (G5).
    """
    if value is None:
        return None, Missing(
            reason="MISSING_INPUT",
            detail=f"required observation input '{field}' is missing",
        )
    if isinstance(value, (Missing, InputMissing)):
        return None, _to_result_missing(value)
    if not _is_real_number(value):
        raise TypeError(
            f"{field}: expected float, int, Missing, or None, "
            f"got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    try:
        numeric = float(value)
    except OverflowError:
        return None, Missing(
            reason="NOT_COMPUTABLE",
            detail=f"observation input '{field}' overflows float range",
        )
    if not math.isfinite(numeric):
        return None, Missing(
            reason="NOT_COMPUTABLE",
            detail=f"observation input '{field}' is non-finite ({value!r})",
        )
    return numeric, None


def db_to_linear(sigma0_db: float) -> float:
    """Convert backscatter in dB to linear power ratio (``10 ** (sigma0_db / 10)``)."""
    val = _require_finite_float("sigma0_db", sigma0_db)
    try:
        lin = 10.0 ** (val / 10.0)
    except OverflowError as exc:
        raise ValueError(
            f"sigma0_db={val!r} overflows linear backscatter conversion"
        ) from exc
    if not math.isfinite(lin) or lin <= 0.0:
        raise ValueError(
            f"sigma0_db={val!r} yields non-positive or non-finite linear value"
        )
    return lin


def linear_to_db(sigma0_lin: float) -> float:
    """Convert strictly positive linear backscatter to dB (``10 * log10(sigma0_lin)``)."""
    val = _require_finite_float("sigma0_lin", sigma0_lin)
    if val <= 0.0:
        raise ValueError(f"sigma0_lin: expected strictly positive value, got {val!r}")
    return 10.0 * math.log10(val)


@dataclass(frozen=True)
class WcmParameters:
    """Caller-supplied Water Cloud Model calibration and QA parameters.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Holds zero hardcoded
    calibration defaults (Blueprint §3.5).
    """

    a_param: float
    b_param: float
    c_soil: float
    d_soil: float
    theta_deg: float
    mv_min: float
    mv_max: float
    max_s1_s2_gap_days: float
    polarization: Polarization = "VV"
    vegetation_descriptor: VegetationDescriptor = "NDVI"
    soil_model: SoilModel = "db_linear"
    min_valid_pixel_count: int | None = None
    min_valid_pixel_fraction: float | None = None
    sigma0_min_db: float | None = None
    sigma0_max_db: float | None = None
    veg_min: float | None = None
    veg_max: float | None = None
    max_incidence_angle_delta_deg: float | None = None
    bisection_tol: float | None = None
    max_bisection_iters: int | None = None

    def __post_init__(self) -> None:
        a = _require_finite_float("a_param", self.a_param)
        b = _require_finite_float("b_param", self.b_param)
        c = _require_finite_float("c_soil", self.c_soil)
        d = _require_finite_float("d_soil", self.d_soil)
        theta = _require_finite_float("theta_deg", self.theta_deg)
        mv_min = _require_finite_float("mv_min", self.mv_min)
        mv_max = _require_finite_float("mv_max", self.mv_max)
        max_gap = _require_finite_float("max_s1_s2_gap_days", self.max_s1_s2_gap_days)

        _require_choice("polarization", self.polarization, POLARIZATIONS)
        _require_choice(
            "vegetation_descriptor", self.vegetation_descriptor, VEGETATION_DESCRIPTORS
        )
        _require_choice("soil_model", self.soil_model, SOIL_MODELS)

        min_px = _require_optional_positive_int(
            "min_valid_pixel_count", self.min_valid_pixel_count
        )
        min_frac = _require_optional_finite_float(
            "min_valid_pixel_fraction", self.min_valid_pixel_fraction
        )
        s_min = _require_optional_finite_float("sigma0_min_db", self.sigma0_min_db)
        s_max = _require_optional_finite_float("sigma0_max_db", self.sigma0_max_db)
        v_min = _require_optional_finite_float("veg_min", self.veg_min)
        v_max = _require_optional_finite_float("veg_max", self.veg_max)
        ang_delta = _require_optional_finite_float(
            "max_incidence_angle_delta_deg", self.max_incidence_angle_delta_deg
        )
        tol = _require_optional_finite_float("bisection_tol", self.bisection_tol)
        max_iters = _require_optional_positive_int(
            "max_bisection_iters", self.max_bisection_iters
        )

        if a < 0.0:
            raise ValueError(f"a_param: expected >= 0, got {a}")
        if b < 0.0:
            raise ValueError(f"b_param: expected >= 0, got {b}")
        if d <= 0.0:
            raise ValueError(
                f"d_soil: expected > 0 for strictly monotonic WCM inversion, got {d}"
            )
        if theta <= 0.0 or theta >= 90.0 or math.cos(math.radians(theta)) <= 0.0:
            raise ValueError(
                f"theta_deg: expected incidence angle strictly in (0, 90), got {theta}"
            )
        if mv_min < 0.0 or mv_min >= mv_max:
            raise ValueError(
                f"mv bounds: expected 0 <= mv_min < mv_max, got [{mv_min}, {mv_max}]"
            )
        if max_gap < 0.0:
            raise ValueError(f"max_s1_s2_gap_days: expected >= 0, got {max_gap}")
        if min_frac is not None and (min_frac <= 0.0 or min_frac > 1.0):
            raise ValueError(
                f"min_valid_pixel_fraction: expected in (0, 1], got {min_frac}"
            )
        if s_min is not None and s_max is not None and s_min > s_max:
            raise ValueError(
                f"sigma0 bounds: expected sigma0_min_db <= sigma0_max_db, "
                f"got [{s_min}, {s_max}]"
            )
        if v_min is not None and v_min < 0.0:
            raise ValueError(f"veg_min: expected >= 0, got {v_min}")
        if v_min is not None and v_max is not None and v_min > v_max:
            raise ValueError(
                f"veg bounds: expected veg_min <= veg_max, got [{v_min}, {v_max}]"
            )
        if ang_delta is not None and ang_delta < 0.0:
            raise ValueError(
                f"max_incidence_angle_delta_deg: expected >= 0, got {ang_delta}"
            )
        if tol is not None and tol <= 0.0:
            raise ValueError(f"bisection_tol: expected > 0, got {tol}")
        if self.soil_model == "linear" and (c + d * mv_min) <= 0.0:
            raise ValueError(
                "linear soil_model requires c_soil + d_soil * mv_min > 0 "
                "across [mv_min, mv_max]"
            )

        object.__setattr__(self, "a_param", a)
        object.__setattr__(self, "b_param", b)
        object.__setattr__(self, "c_soil", c)
        object.__setattr__(self, "d_soil", d)
        object.__setattr__(self, "theta_deg", theta)
        object.__setattr__(self, "mv_min", mv_min)
        object.__setattr__(self, "mv_max", mv_max)
        object.__setattr__(self, "max_s1_s2_gap_days", max_gap)
        object.__setattr__(self, "min_valid_pixel_count", min_px)
        object.__setattr__(self, "min_valid_pixel_fraction", min_frac)
        object.__setattr__(self, "sigma0_min_db", s_min)
        object.__setattr__(self, "sigma0_max_db", s_max)
        object.__setattr__(self, "veg_min", v_min)
        object.__setattr__(self, "veg_max", v_max)
        object.__setattr__(self, "max_incidence_angle_delta_deg", ang_delta)
        object.__setattr__(self, "bisection_tol", tol)
        object.__setattr__(self, "max_bisection_iters", max_iters)


@dataclass(frozen=True)
class WcmForwardResult:
    """Result of the forward Water Cloud Model backscatter evaluation."""

    sigma0_lin: float
    sigma0_db: float
    tau2: float
    sigma_veg_lin: float
    sigma_soil_lin: float
    soil_model: SoilModel


@dataclass(frozen=True)
class PixelWcmSample:
    """Single-pixel Sentinel-1/Sentinel-2 observation for parcel QA aggregation."""

    sigma0: float | Missing | InputMissing | None
    sigma0_unit: BackscatterUnit
    polarization: Polarization
    vegetation_value: float | Missing | InputMissing | None
    vegetation_descriptor: VegetationDescriptor
    qa_valid: bool
    incidence_angle_deg: float | Missing | InputMissing | None
    orbit_direction: OrbitDirection | None
    s1_s2_delta_days: float | Missing | InputMissing | None


@dataclass(frozen=True)
class ParcelWcmObservation:
    """Parcel-level aggregated Sentinel-1/Sentinel-2 input and QA metadata."""

    sigma0: float | Missing | InputMissing | None
    sigma0_unit: BackscatterUnit
    polarization: Polarization
    vegetation_value: float | Missing | InputMissing | None
    vegetation_descriptor: VegetationDescriptor
    valid_pixel_count: int
    total_pixel_count: int
    effective_support_m: float | Missing | InputMissing | None
    orbit_direction: OrbitDirection | None
    incidence_angle_deg: float | Missing | InputMissing | None
    s1_s2_delta_days: float | Missing | InputMissing | None
    qa_passed: bool = True
    qa_detail: str | None = None

    def __post_init__(self) -> None:
        _require_choice("sigma0_unit", self.sigma0_unit, BACKSCATTER_UNITS)
        _require_choice("polarization", self.polarization, POLARIZATIONS)
        _require_choice(
            "vegetation_descriptor", self.vegetation_descriptor, VEGETATION_DESCRIPTORS
        )
        if not _is_strict_int(self.valid_pixel_count):
            raise TypeError(
                f"valid_pixel_count: expected int, got {type(self.valid_pixel_count).__name__} (G5)"
            )
        if not _is_strict_int(self.total_pixel_count):
            raise TypeError(
                f"total_pixel_count: expected int, got {type(self.total_pixel_count).__name__} (G5)"
            )
        if self.valid_pixel_count < 0 or self.total_pixel_count < 0:
            raise ValueError(
                "valid_pixel_count and total_pixel_count must be non-negative"
            )
        if self.valid_pixel_count > self.total_pixel_count:
            raise ValueError(
                f"valid_pixel_count ({self.valid_pixel_count}) cannot exceed "
                f"total_pixel_count ({self.total_pixel_count})"
            )
        if self.orbit_direction is not None:
            _require_choice("orbit_direction", self.orbit_direction, ORBIT_DIRECTIONS)
        if not isinstance(self.qa_passed, bool):
            raise TypeError(
                f"qa_passed: expected bool, got {type(self.qa_passed).__name__} (G5)"
            )
        if self.qa_detail is not None and not isinstance(self.qa_detail, str):
            raise TypeError(
                f"qa_detail: expected str or None, got {type(self.qa_detail).__name__} (G5)"
            )


@dataclass(frozen=True)
class SurfaceMoistureEstimate:
    """0–5 cm volumetric soil moisture estimate from the WCM inversion.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Always enforces:
    - ``depth == "0_to_5_cm"``
    - ``observes_root_zone is False``
    - ``estimator_role == "SURFACE_INPUT_ESTIMATOR"``
    - ``provenance == "DERIVED"`` for numeric estimates and ``None`` for ``Missing`` (C4.1)
    """

    soil_moisture_m3_m3: float | Missing
    unit: Literal["m3 m-3"] = UNIT_VOLUMETRIC_MOISTURE
    depth: Literal["0_to_5_cm"] = DEPTH_BAND_SURFACE
    observes_root_zone: Literal[False] = False
    estimator_role: Literal["SURFACE_INPUT_ESTIMATOR"] = ESTIMATOR_ROLE_SURFACE
    local_transfer_validated: bool = False
    provenance: Literal["DERIVED"] | None = None
    polarization: Polarization = "VV"
    vegetation_descriptor: VegetationDescriptor = "NDVI"
    orbit_direction: OrbitDirection | None = None
    incidence_angle_deg: float | None = None
    s1_s2_delta_days: float | None = None
    valid_pixel_count: int = 0
    total_pixel_count: int = 0
    effective_support_m: float | None = None
    tau2: float | None = None
    sigma_veg_lin: float | None = None
    sigma0_obs_db: float | None = None
    status: str = PROPOSED_STATUS

    def __post_init__(self) -> None:
        if self.unit != UNIT_VOLUMETRIC_MOISTURE:
            raise ValueError(
                f"unit must be '{UNIT_VOLUMETRIC_MOISTURE}', got {self.unit!r}"
            )
        if self.depth != DEPTH_BAND_SURFACE:
            raise ValueError(
                f"Rev13 §3 guard: surface moisture depth must be strictly "
                f"'{DEPTH_BAND_SURFACE}', got {self.depth!r}"
            )
        if self.observes_root_zone is not False:
            raise ValueError(
                "Rev13 §3 guard: observes_root_zone must be strictly False"
            )
        if self.estimator_role != ESTIMATOR_ROLE_SURFACE:
            raise ValueError(
                f"Rev13 §3 guard: estimator_role must be strictly "
                f"'{ESTIMATOR_ROLE_SURFACE}', got {self.estimator_role!r}"
            )
        if not isinstance(self.local_transfer_validated, bool):
            raise TypeError(
                f"local_transfer_validated: expected bool, "
                f"got {type(self.local_transfer_validated).__name__} (G5)"
            )
        if isinstance(self.soil_moisture_m3_m3, Missing):
            if self.provenance is not None:
                raise ValueError(
                    "C4.1: missing soil_moisture_m3_m3 must carry provenance=None"
                )
        else:
            val = _require_finite_float("soil_moisture_m3_m3", self.soil_moisture_m3_m3)
            object.__setattr__(self, "soil_moisture_m3_m3", val)
            if self.provenance != "DERIVED":
                raise ValueError(
                    "C4.1/C4.3: numeric soil_moisture_m3_m3 must carry provenance='DERIVED'"
                )


@dataclass(frozen=True)
class SurfaceMoistureBenchmarkReport:
    """Validation guard report for surface soil moisture benchmarking (Rev13 §3)."""

    calibration_reference: str
    validation_reference: str
    claimed_level: ClaimedValidationLevel
    local_transfer_validated: bool
    depth: Literal["0_to_5_cm"] = DEPTH_BAND_SURFACE
    observes_root_zone: Literal[False] = False
    estimator_role: Literal["SURFACE_INPUT_ESTIMATOR"] = ESTIMATOR_ROLE_SURFACE
    in_situ_probe_count: int | None = None
    status: str = PROPOSED_STATUS


def _resolve_incidence_angle(
    params: WcmParameters, incidence_angle_deg: float | None
) -> float:
    """Return validated incidence angle in degrees."""
    if incidence_angle_deg is None:
        return params.theta_deg
    angle = _require_finite_float("incidence_angle_deg", incidence_angle_deg)
    if angle <= 0.0 or angle >= 90.0 or math.cos(math.radians(angle)) <= 0.0:
        raise ValueError(
            f"incidence_angle_deg: expected angle strictly in (0, 90), got {angle}"
        )
    return angle


def _canopy_components(
    vegetation: float, theta_deg: float, params: WcmParameters
) -> tuple[float, float]:
    """Compute WCM two-way transmissivity ``tau2`` and vegetation backscatter ``sigma_veg``."""
    cos_theta = math.cos(math.radians(theta_deg))
    tau2 = math.exp(-2.0 * params.b_param * vegetation / cos_theta)
    sigma_veg = params.a_param * vegetation * cos_theta * (1.0 - tau2)
    return tau2, sigma_veg


def _soil_backscatter_linear(mv: float, params: WcmParameters) -> float:
    """Compute linear soil backscatter for a given volumetric moisture ``mv``."""
    if params.soil_model == "db_linear":
        soil_db = params.c_soil + params.d_soil * mv
        return 10.0 ** (soil_db / 10.0)
    return params.c_soil + params.d_soil * mv


def wcm_forward_backscatter(
    mv: float,
    *,
    vegetation: float,
    params: WcmParameters,
    incidence_angle_deg: float | None = None,
) -> WcmForwardResult:
    """Evaluate the forward Water Cloud Model backscatter for ``mv`` and ``vegetation``.

    Parameters
    ----------
    mv:
        Volumetric soil moisture (``m3 m-3``), finite and non-negative.
    vegetation:
        Sentinel-2 vegetation descriptor (``NDVI`` or ``LAI``), finite and ``>= 0``.
    params:
        Caller-supplied ``WcmParameters``.
    incidence_angle_deg:
        Optional radar incidence angle in degrees; defaults to ``params.theta_deg``.
    """
    if not isinstance(params, WcmParameters):
        raise TypeError(
            f"params: expected WcmParameters, got {type(params).__name__} (G5)"
        )
    mv_val = _require_finite_float("mv", mv)
    veg_val = _require_finite_float("vegetation", vegetation)
    if mv_val < 0.0:
        raise ValueError(f"mv: expected non-negative moisture, got {mv_val}")
    if veg_val < 0.0:
        raise ValueError(f"vegetation: expected >= 0, got {veg_val}")
    theta = _resolve_incidence_angle(params, incidence_angle_deg)

    tau2, sigma_veg = _canopy_components(veg_val, theta, params)
    sigma_soil_lin = _soil_backscatter_linear(mv_val, params)
    if sigma_soil_lin <= 0.0 or not math.isfinite(sigma_soil_lin):
        raise ValueError(
            f"soil backscatter is non-positive or non-finite ({sigma_soil_lin!r}) at mv={mv_val}"
        )
    sigma_total_lin = sigma_veg + tau2 * sigma_soil_lin
    sigma_total_db = linear_to_db(sigma_total_lin)
    return WcmForwardResult(
        sigma0_lin=sigma_total_lin,
        sigma0_db=sigma_total_db,
        tau2=tau2,
        sigma_veg_lin=sigma_veg,
        sigma_soil_lin=sigma_soil_lin,
        soil_model=params.soil_model,
    )


def _normalize_sigma0(
    sigma0: float, sigma0_unit: BackscatterUnit
) -> tuple[float | None, float | None, Missing | None]:
    """Convert caller-typed ``sigma0`` into ``(sigma0_lin, sigma0_db)`` or ``Missing``."""
    _require_choice("sigma0_unit", sigma0_unit, BACKSCATTER_UNITS)
    val = _require_finite_float("sigma0", sigma0)
    if sigma0_unit == "linear":
        if val <= 0.0:
            return (
                None,
                None,
                Missing(
                    reason="CONTROL_FAILED",
                    detail=f"linear sigma0 must be strictly positive, got {val}",
                ),
            )
        return val, linear_to_db(val), None
    try:
        lin = db_to_linear(val)
    except ValueError as exc:
        return None, None, Missing(reason="CONTROL_FAILED", detail=str(exc))
    return lin, val, None


def wcm_closed_form_moisture(
    sigma0: float,
    *,
    sigma0_unit: BackscatterUnit,
    vegetation: float,
    params: WcmParameters,
    incidence_angle_deg: float | None = None,
) -> float | Missing:
    """Exact closed-form WCM moisture inversion for monotonic verification against bisection."""
    if not isinstance(params, WcmParameters):
        raise TypeError(
            f"params: expected WcmParameters, got {type(params).__name__} (G5)"
        )
    veg_val = _require_finite_float("vegetation", vegetation)
    if veg_val < 0.0:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"vegetation descriptor must be >= 0 for WCM, got {veg_val}",
        )
    theta = _resolve_incidence_angle(params, incidence_angle_deg)
    sigma_lin, sigma_db, sigma_err = _normalize_sigma0(sigma0, sigma0_unit)
    if sigma_err is not None:
        return sigma_err
    assert sigma_lin is not None and sigma_db is not None

    if params.sigma0_min_db is not None and sigma_db < params.sigma0_min_db:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"sigma0 ({sigma_db} dB) is below sigma0_min_db ({params.sigma0_min_db} dB)"
            ),
        )
    if params.sigma0_max_db is not None and sigma_db > params.sigma0_max_db:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"sigma0 ({sigma_db} dB) exceeds sigma0_max_db ({params.sigma0_max_db} dB)"
            ),
        )

    tau2, sigma_veg = _canopy_components(veg_val, theta, params)
    if tau2 <= 0.0:
        return Missing(
            reason="CONTROL_FAILED",
            detail="canopy attenuation saturated (tau2 == 0); soil moisture unobservable",
        )
    sigma_soil_lin = (sigma_lin - sigma_veg) / tau2
    if sigma_soil_lin <= 0.0:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"observed linear sigma0 ({sigma_lin}) does not exceed canopy "
                f"backscatter ({sigma_veg}); outside invertible soil domain"
            ),
        )
    if params.soil_model == "db_linear":
        mv = (linear_to_db(sigma_soil_lin) - params.c_soil) / params.d_soil
    else:
        mv = (sigma_soil_lin - params.c_soil) / params.d_soil

    if not math.isfinite(mv):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="closed-form WCM inversion produced non-finite soil moisture",
        )
    mv_ulp = 10 * max(math.ulp(params.mv_min), math.ulp(params.mv_max))
    if mv < params.mv_min - mv_ulp or mv > params.mv_max + mv_ulp:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"inverted moisture {mv} m3 m-3 lies outside [{params.mv_min}, {params.mv_max}]"
            ),
        )
    if mv < params.mv_min:
        return params.mv_min
    if mv > params.mv_max:
        return params.mv_max
    return mv


def wcm_invert_moisture(
    sigma0: float,
    *,
    sigma0_unit: BackscatterUnit,
    vegetation: float,
    params: WcmParameters,
    incidence_angle_deg: float | None = None,
) -> float | Missing:
    """Invert 0–5 cm soil moisture ``m_v`` from ``sigma0`` via bounded bisection.

    Returns a finite ``float`` in ``[params.mv_min, params.mv_max]`` or typed
    ``Missing`` (``CONTROL_FAILED`` / ``NOT_COMPUTABLE``) when backscatter or
    vegetation falls outside the invertible domain.
    """
    if not isinstance(params, WcmParameters):
        raise TypeError(
            f"params: expected WcmParameters, got {type(params).__name__} (G5)"
        )
    veg_val = _require_finite_float("vegetation", vegetation)
    if veg_val < 0.0:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"vegetation descriptor must be >= 0 for WCM, got {veg_val}",
        )
    if params.veg_min is not None and veg_val < params.veg_min:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"vegetation descriptor ({veg_val}) below veg_min ({params.veg_min})",
        )
    if params.veg_max is not None and veg_val > params.veg_max:
        return Missing(
            reason="CONTROL_FAILED",
            detail=f"vegetation descriptor ({veg_val}) exceeds veg_max ({params.veg_max})",
        )

    theta = _resolve_incidence_angle(params, incidence_angle_deg)
    sigma_lin, sigma_db, sigma_err = _normalize_sigma0(sigma0, sigma0_unit)
    if sigma_err is not None:
        return sigma_err
    assert sigma_lin is not None and sigma_db is not None

    if params.sigma0_min_db is not None and sigma_db < params.sigma0_min_db:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"sigma0 ({sigma_db} dB) is below sigma0_min_db ({params.sigma0_min_db} dB)"
            ),
        )
    if params.sigma0_max_db is not None and sigma_db > params.sigma0_max_db:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"sigma0 ({sigma_db} dB) exceeds sigma0_max_db ({params.sigma0_max_db} dB)"
            ),
        )

    tau2, sigma_veg = _canopy_components(veg_val, theta, params)
    if tau2 <= 0.0:
        return Missing(
            reason="CONTROL_FAILED",
            detail="canopy attenuation saturated (tau2 == 0); soil moisture unobservable",
        )

    def _forward_lin(mv_candidate: float) -> float:
        return sigma_veg + tau2 * _soil_backscatter_linear(mv_candidate, params)

    f_lo = _forward_lin(params.mv_min)
    f_hi = _forward_lin(params.mv_max)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="forward WCM bracket is non-finite across [mv_min, mv_max]",
        )
    lo_ulp = 10 * math.ulp(f_lo)
    hi_ulp = 10 * math.ulp(f_hi)
    if sigma_lin < f_lo - lo_ulp or sigma_lin > f_hi + hi_ulp:
        return Missing(
            reason="CONTROL_FAILED",
            detail=(
                f"observed sigma0 ({sigma_db} dB / {sigma_lin} linear) lies outside "
                f"WCM bracket [{linear_to_db(f_lo)} dB, {linear_to_db(f_hi)} dB] "
                f"for mv in [{params.mv_min}, {params.mv_max}]"
            ),
        )
    if sigma_lin <= f_lo:
        return params.mv_min
    if sigma_lin >= f_hi:
        return params.mv_max

    lo = params.mv_min
    hi = params.mv_max
    iterations = 0
    while lo < hi:
        if params.bisection_tol is not None and (hi - lo) <= params.bisection_tol:
            break
        if (
            params.max_bisection_iters is not None
            and iterations >= params.max_bisection_iters
        ):
            break
        mid = lo + (hi - lo) / 2.0
        if mid <= lo or mid >= hi:
            break
        f_mid = _forward_lin(mid)
        if not math.isfinite(f_mid):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail="WCM forward evaluation became non-finite during bisection",
            )
        if f_mid == sigma_lin:
            return mid
        if f_mid < sigma_lin:
            lo = mid
        else:
            hi = mid
        iterations += 1

    return lo + (hi - lo) / 2.0


def aggregate_parcel_qa(
    pixels: Sequence[PixelWcmSample],
    *,
    pixel_spacing_m: float,
    polarization: Polarization,
    vegetation_descriptor: VegetationDescriptor,
    output_unit: BackscatterUnit = "dB",
) -> ParcelWcmObservation:
    """Aggregate pixel-level Sentinel-1/Sentinel-2 samples into a parcel QA observation.

    Valid pixels are averaged in linear backscatter power space and arithmetic
    vegetation space. ``effective_support_m`` is computed as
    ``pixel_spacing_m * sqrt(valid_pixel_count)``. Heterogeneous orbit
    directions among valid pixels mark ``qa_passed=False``.
    """
    if isinstance(pixels, (str, bytes, bytearray)) or not isinstance(pixels, Sequence):
        raise TypeError(
            f"pixels: expected Sequence of PixelWcmSample, got {type(pixels).__name__} (G5)"
        )
    spacing = _require_finite_float("pixel_spacing_m", pixel_spacing_m)
    if spacing <= 0.0:
        raise ValueError(f"pixel_spacing_m: expected > 0, got {spacing}")
    _require_choice("polarization", polarization, POLARIZATIONS)
    _require_choice(
        "vegetation_descriptor", vegetation_descriptor, VEGETATION_DESCRIPTORS
    )
    _require_choice("output_unit", output_unit, BACKSCATTER_UNITS)

    total_count = len(pixels)
    sigma_lin_values: list[float] = []
    veg_values: list[float] = []
    angle_values: list[float] = []
    delta_values: list[float] = []
    orbits: set[OrbitDirection] = set()

    for idx, sample in enumerate(pixels):
        if not isinstance(sample, PixelWcmSample):
            raise TypeError(
                f"pixels[{idx}]: expected PixelWcmSample, got {type(sample).__name__} (G5)"
            )
        if not isinstance(sample.qa_valid, bool):
            raise TypeError(
                f"pixels[{idx}].qa_valid: expected bool, "
                f"got {type(sample.qa_valid).__name__} (G5)"
            )
        if not sample.qa_valid:
            continue
        if sample.polarization != polarization:
            return ParcelWcmObservation(
                sigma0=None,
                sigma0_unit=output_unit,
                polarization=polarization,
                vegetation_value=None,
                vegetation_descriptor=vegetation_descriptor,
                valid_pixel_count=0,
                total_pixel_count=total_count,
                effective_support_m=None,
                orbit_direction=None,
                incidence_angle_deg=None,
                s1_s2_delta_days=None,
                qa_passed=False,
                qa_detail=(
                    f"pixel {idx} polarization {sample.polarization!r} does not "
                    f"match expected {polarization!r}"
                ),
            )
        if sample.vegetation_descriptor != vegetation_descriptor:
            return ParcelWcmObservation(
                sigma0=None,
                sigma0_unit=output_unit,
                polarization=polarization,
                vegetation_value=None,
                vegetation_descriptor=vegetation_descriptor,
                valid_pixel_count=0,
                total_pixel_count=total_count,
                effective_support_m=None,
                orbit_direction=None,
                incidence_angle_deg=None,
                s1_s2_delta_days=None,
                qa_passed=False,
                qa_detail=(
                    f"pixel {idx} vegetation_descriptor {sample.vegetation_descriptor!r} "
                    f"does not match expected {vegetation_descriptor!r}"
                ),
            )
        if (
            not _is_finite_number(sample.sigma0)
            or not _is_finite_number(sample.vegetation_value)
            or not _is_finite_number(sample.incidence_angle_deg)
            or not _is_finite_number(sample.s1_s2_delta_days)
            or sample.orbit_direction is None
        ):
            continue

        assert isinstance(sample.sigma0, (int, float))
        assert isinstance(sample.vegetation_value, (int, float))
        assert isinstance(sample.incidence_angle_deg, (int, float))
        assert isinstance(sample.s1_s2_delta_days, (int, float))

        _require_choice("sigma0_unit", sample.sigma0_unit, BACKSCATTER_UNITS)
        _require_choice("orbit_direction", sample.orbit_direction, ORBIT_DIRECTIONS)

        if sample.sigma0_unit == "linear":
            if float(sample.sigma0) <= 0.0:
                continue
            s_lin = float(sample.sigma0)
        else:
            try:
                s_lin = db_to_linear(float(sample.sigma0))
            except ValueError:
                continue

        sigma_lin_values.append(s_lin)
        veg_values.append(float(sample.vegetation_value))
        angle_values.append(float(sample.incidence_angle_deg))
        delta_values.append(float(sample.s1_s2_delta_days))
        orbits.add(sample.orbit_direction)

    valid_count = len(sigma_lin_values)
    if valid_count == 0:
        return ParcelWcmObservation(
            sigma0=None,
            sigma0_unit=output_unit,
            polarization=polarization,
            vegetation_value=None,
            vegetation_descriptor=vegetation_descriptor,
            valid_pixel_count=0,
            total_pixel_count=total_count,
            effective_support_m=None,
            orbit_direction=None,
            incidence_angle_deg=None,
            s1_s2_delta_days=None,
            qa_passed=True,
            qa_detail=None,
        )

    mean_sigma_lin = math.fsum(sigma_lin_values) / valid_count
    aggregated_sigma = (
        mean_sigma_lin if output_unit == "linear" else linear_to_db(mean_sigma_lin)
    )
    mean_veg = math.fsum(veg_values) / valid_count
    mean_angle = math.fsum(angle_values) / valid_count
    worst_delta = max(delta_values, key=abs)
    support_m = spacing * math.sqrt(valid_count)

    if len(orbits) > 1:
        return ParcelWcmObservation(
            sigma0=aggregated_sigma,
            sigma0_unit=output_unit,
            polarization=polarization,
            vegetation_value=mean_veg,
            vegetation_descriptor=vegetation_descriptor,
            valid_pixel_count=valid_count,
            total_pixel_count=total_count,
            effective_support_m=support_m,
            orbit_direction=None,
            incidence_angle_deg=mean_angle,
            s1_s2_delta_days=worst_delta,
            qa_passed=False,
            qa_detail="mixed Sentinel-1 orbit directions across parcel pixels",
        )

    orbit = next(iter(orbits))
    return ParcelWcmObservation(
        sigma0=aggregated_sigma,
        sigma0_unit=output_unit,
        polarization=polarization,
        vegetation_value=mean_veg,
        vegetation_descriptor=vegetation_descriptor,
        valid_pixel_count=valid_count,
        total_pixel_count=total_count,
        effective_support_m=support_m,
        orbit_direction=orbit,
        incidence_angle_deg=mean_angle,
        s1_s2_delta_days=worst_delta,
        qa_passed=True,
        qa_detail=None,
    )


def _missing_estimate(
    observation: ParcelWcmObservation,
    missing: Missing,
    *,
    local_transfer_validated: bool,
    incidence_angle_deg: float | None = None,
    s1_s2_delta_days: float | None = None,
    effective_support_m: float | None = None,
) -> SurfaceMoistureEstimate:
    """Build a ``SurfaceMoistureEstimate`` carrying a typed ``Missing`` outcome."""
    return SurfaceMoistureEstimate(
        soil_moisture_m3_m3=missing,
        local_transfer_validated=local_transfer_validated,
        provenance=None,
        polarization=observation.polarization,
        vegetation_descriptor=observation.vegetation_descriptor,
        orbit_direction=observation.orbit_direction,
        incidence_angle_deg=incidence_angle_deg,
        s1_s2_delta_days=s1_s2_delta_days,
        valid_pixel_count=observation.valid_pixel_count,
        total_pixel_count=observation.total_pixel_count,
        effective_support_m=effective_support_m,
        tau2=None,
        sigma_veg_lin=None,
        sigma0_obs_db=None,
    )


def estimate_surface_moisture(
    observation: ParcelWcmObservation,
    *,
    params: WcmParameters,
    local_transfer_validated: bool = False,
) -> SurfaceMoistureEstimate:
    """Estimate 0–5 cm volumetric soil moisture from a parcel WCM observation.

    Enforces Rev13 §3 depth, estimator-role, transfer-disclosure, and QA guards.
    Returns ``SurfaceMoistureEstimate`` with ``soil_moisture_m3_m3`` set to a
    finite ``float`` (``provenance="DERIVED"``) or typed ``Missing``
    (``NO_COVERAGE``, ``MISSING_INPUT``, ``CONTROL_FAILED``, or ``NOT_COMPUTABLE``).
    """
    if not isinstance(observation, ParcelWcmObservation):
        raise TypeError(
            f"observation: expected ParcelWcmObservation, "
            f"got {type(observation).__name__} (G5)"
        )
    if not isinstance(params, WcmParameters):
        raise TypeError(
            f"params: expected WcmParameters, got {type(params).__name__} (G5)"
        )
    if not isinstance(local_transfer_validated, bool):
        raise TypeError(
            f"local_transfer_validated: expected bool, "
            f"got {type(local_transfer_validated).__name__} (G5)"
        )

    if observation.total_pixel_count == 0:
        return _missing_estimate(
            observation,
            Missing(
                reason="NO_COVERAGE",
                detail="no Sentinel pixels cover the target parcel (total_pixel_count == 0)",
            ),
            local_transfer_validated=local_transfer_validated,
        )

    if not observation.qa_passed:
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=observation.qa_detail or "parcel QA control failed",
            ),
            local_transfer_validated=local_transfer_validated,
        )

    if observation.valid_pixel_count == 0:
        return _missing_estimate(
            observation,
            Missing(
                reason="NO_COVERAGE",
                detail="no valid Sentinel pixels remain after QA masking (valid_pixel_count == 0)",
            ),
            local_transfer_validated=local_transfer_validated,
        )

    if (
        params.min_valid_pixel_count is not None
        and observation.valid_pixel_count < params.min_valid_pixel_count
    ):
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"insufficient valid pixels: {observation.valid_pixel_count} < "
                    f"min_valid_pixel_count ({params.min_valid_pixel_count})"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
        )

    valid_fraction = observation.valid_pixel_count / observation.total_pixel_count
    if (
        params.min_valid_pixel_fraction is not None
        and valid_fraction < params.min_valid_pixel_fraction
    ):
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"insufficient valid pixel fraction: {valid_fraction} < "
                    f"min_valid_pixel_fraction ({params.min_valid_pixel_fraction})"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
        )

    sigma0_val, sigma0_missing = _missing_or_check_number("sigma0", observation.sigma0)
    if sigma0_missing is not None:
        return _missing_estimate(
            observation,
            sigma0_missing,
            local_transfer_validated=local_transfer_validated,
        )
    veg_val, veg_missing = _missing_or_check_number(
        "vegetation_value", observation.vegetation_value
    )
    if veg_missing is not None:
        return _missing_estimate(
            observation, veg_missing, local_transfer_validated=local_transfer_validated
        )
    delta_val, delta_missing = _missing_or_check_number(
        "s1_s2_delta_days", observation.s1_s2_delta_days
    )
    if delta_missing is not None:
        return _missing_estimate(
            observation,
            delta_missing,
            local_transfer_validated=local_transfer_validated,
        )
    angle_val, angle_missing = _missing_or_check_number(
        "incidence_angle_deg", observation.incidence_angle_deg
    )
    if angle_missing is not None:
        return _missing_estimate(
            observation,
            angle_missing,
            local_transfer_validated=local_transfer_validated,
            s1_s2_delta_days=delta_val,
        )
    support_val, support_missing = _missing_or_check_number(
        "effective_support_m", observation.effective_support_m
    )
    if support_missing is not None:
        return _missing_estimate(
            observation,
            support_missing,
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
        )
    if observation.orbit_direction is None:
        return _missing_estimate(
            observation,
            Missing(
                reason="MISSING_INPUT",
                detail="required observation input 'orbit_direction' is missing",
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    assert sigma0_val is not None
    assert veg_val is not None
    assert delta_val is not None
    assert angle_val is not None
    assert support_val is not None

    if support_val <= 0.0:
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=f"effective_support_m must be > 0, got {support_val}",
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    if observation.polarization != params.polarization:
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"observation polarization {observation.polarization!r} does not "
                    f"match WcmParameters polarization {params.polarization!r}"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    if observation.vegetation_descriptor != params.vegetation_descriptor:
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"observation vegetation_descriptor "
                    f"{observation.vegetation_descriptor!r} does not match "
                    f"WcmParameters {params.vegetation_descriptor!r}"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    if abs(delta_val) > params.max_s1_s2_gap_days:
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"|s1_s2_delta_days| ({abs(delta_val)}) exceeds "
                    f"max_s1_s2_gap_days ({params.max_s1_s2_gap_days})"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    if (
        angle_val <= 0.0
        or angle_val >= 90.0
        or math.cos(math.radians(angle_val)) <= 0.0
    ):
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=f"incidence_angle_deg ({angle_val}) outside (0, 90) degrees",
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    if (
        params.max_incidence_angle_delta_deg is not None
        and abs(angle_val - params.theta_deg) > params.max_incidence_angle_delta_deg
    ):
        return _missing_estimate(
            observation,
            Missing(
                reason="CONTROL_FAILED",
                detail=(
                    f"|incidence_angle_deg - theta_deg| "
                    f"({abs(angle_val - params.theta_deg)}) exceeds "
                    f"max_incidence_angle_delta_deg ({params.max_incidence_angle_delta_deg})"
                ),
            ),
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    inverted = wcm_invert_moisture(
        sigma0_val,
        sigma0_unit=observation.sigma0_unit,
        vegetation=veg_val,
        params=params,
        incidence_angle_deg=angle_val,
    )
    if isinstance(inverted, Missing):
        return _missing_estimate(
            observation,
            inverted,
            local_transfer_validated=local_transfer_validated,
            incidence_angle_deg=angle_val,
            s1_s2_delta_days=delta_val,
            effective_support_m=support_val,
        )

    tau2, sigma_veg = _canopy_components(veg_val, angle_val, params)
    _, sigma_db, _ = _normalize_sigma0(sigma0_val, observation.sigma0_unit)
    return SurfaceMoistureEstimate(
        soil_moisture_m3_m3=inverted,
        local_transfer_validated=local_transfer_validated,
        provenance="DERIVED",
        polarization=observation.polarization,
        vegetation_descriptor=observation.vegetation_descriptor,
        orbit_direction=observation.orbit_direction,
        incidence_angle_deg=angle_val,
        s1_s2_delta_days=delta_val,
        valid_pixel_count=observation.valid_pixel_count,
        total_pixel_count=observation.total_pixel_count,
        effective_support_m=support_val,
        tau2=tau2,
        sigma_veg_lin=sigma_veg,
        sigma0_obs_db=sigma_db,
    )


def validate_surface_moisture_benchmark(
    *,
    calibration_reference: str,
    validation_reference: str,
    claimed_level: ClaimedValidationLevel,
    in_situ_probe_count: int | None = None,
    depth: str = DEPTH_BAND_SURFACE,
) -> SurfaceMoistureBenchmarkReport:
    """Enforce Rev13 §3 anti-circularity guard on surface moisture benchmark claims.

    Refuses (``ValueError``) claiming ``"INDEPENDENT_FIELD_VALIDATION"`` when
    ``calibration_reference == "SMAP"`` and ``validation_reference == "SMAP"``
    (or when calibration and validation references name the same dataset), and
    enforces surface-only depth ``"0_to_5_cm"``.
    """
    if not isinstance(calibration_reference, str) or not calibration_reference.strip():
        raise ValueError("calibration_reference: expected non-empty str")
    if not isinstance(validation_reference, str) or not validation_reference.strip():
        raise ValueError("validation_reference: expected non-empty str")
    _require_choice("claimed_level", claimed_level, BENCHMARK_LEVELS)
    if not isinstance(depth, str):
        raise TypeError(f"depth: expected str, got {type(depth).__name__} (G5)")
    if depth != DEPTH_BAND_SURFACE:
        raise ValueError(
            f"Rev13 §3 guard: benchmark depth must be strictly '{DEPTH_BAND_SURFACE}', "
            f"got {depth!r}"
        )
    if in_situ_probe_count is not None:
        if not _is_strict_int(in_situ_probe_count):
            raise TypeError(
                f"in_situ_probe_count: expected int or None, "
                f"got {type(in_situ_probe_count).__name__} (G5)"
            )
        if in_situ_probe_count < 0:
            raise ValueError(
                f"in_situ_probe_count: expected >= 0, got {in_situ_probe_count}"
            )

    cal_norm = calibration_reference.strip().upper()
    val_norm = validation_reference.strip().upper()

    if claimed_level == "INDEPENDENT_FIELD_VALIDATION":
        if cal_norm == "SMAP" and val_norm == "SMAP":
            raise ValueError(
                "Rev13 §3 guard: cannot claim INDEPENDENT_FIELD_VALIDATION when "
                "calibration_reference == 'SMAP' and validation_reference == 'SMAP'"
            )
        if cal_norm == val_norm:
            raise ValueError(
                "Rev13 §3 guard: cannot claim INDEPENDENT_FIELD_VALIDATION when "
                f"calibration_reference and validation_reference are identical ({calibration_reference!r})"
            )
        if in_situ_probe_count is not None and in_situ_probe_count == 0:
            raise ValueError(
                "Rev13 §3 guard: INDEPENDENT_FIELD_VALIDATION requires positive in_situ_probe_count"
            )

    return SurfaceMoistureBenchmarkReport(
        calibration_reference=calibration_reference.strip(),
        validation_reference=validation_reference.strip(),
        claimed_level=claimed_level,
        local_transfer_validated=(claimed_level == "INDEPENDENT_FIELD_VALIDATION"),
        in_situ_probe_count=in_situ_probe_count,
    )
