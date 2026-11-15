"""Clean-room daily thermal-photoperiod-vernalization phenology simulator.

Frontier Unit F-10 (``l1/calendar-thermal-phenology``), implementing the
specification of ``27_PLAN_DE_FRONTERA.md`` section 15.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). This module is
standalone and is not wired into ``engine/calendar/__init__.py``, EP2, or the
API runner; nothing here takes effect until people approve it.

Design rules and guards
-----------------------
- **Zero hardcoded cultivar parameters:** ``CultivarPhenologyParams``,
  ``PhotoperiodParams``, and ``VernalizationParams`` carry no default values;
  all thermal, photoperiod, and vernalization parameters are supplied by the
  caller.
- **Clean-room astronomical daylength:** daylength is computed purely from
  ``latitude_deg`` and ``day_of_year`` via standard solar declination and
  sunset hour-angle geometry using pure-Python arithmetic only.
- **Calibration guard (§15.3 / §15.7):** when ``observed_flowering_dates`` or
  local calibration metadata is absent or uncalibrated, the simulation result
  MUST tag ``calibration_status="UNCALIBRATED"`` with ``local_error_days=None``
  and ``local_error_missing=Missing(reason="MISSING_INPUT", detail=...)``.
- **Missing-temperature guard (§15.3 / §15.7, G4, C3.1, C3.3):** any missing
  or non-finite daily temperature during active growth (from ``sowing_date``
  until physiological maturity) propagates typed
  ``Missing(reason="MISSING_INPUT", detail=...)`` to unreached phenological
  event dates and remaining active-growth ``dvs_series`` entries, never
  assuming ``0`` thermal units.

Pure function (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and caller arguments are never modified.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contracts.inputs.common import IsoDate
from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.results.models import Missing

__all__ = [
    "CALIBRATED_STATUS",
    "DEFAULT_TEMPERATURE_UNIT",
    "TEMPERATURE_MAX_QUANTITY",
    "TEMPERATURE_MIN_QUANTITY",
    "UNCALIBRATED_STATUS",
    "CalibrationMetadata",
    "CultivarPhenologyParams",
    "DailyThermalInput",
    "DvsPoint",
    "PhenologySimulationResult",
    "PhotoperiodMode",
    "PhotoperiodParams",
    "VernalizationParams",
    "astronomical_daylength_hours",
    "daily_thermal_inputs_from_site_climate",
    "daily_thermal_time",
    "day_of_year",
    "photoperiod_factor",
    "simulate_crop_phenology",
    "vernalization_effectiveness",
    "vernalization_factor",
]

PhotoperiodMode = str
CalibrationStatus = str

UNCALIBRATED_STATUS: CalibrationStatus = "UNCALIBRATED"
CALIBRATED_STATUS: CalibrationStatus = "CALIBRATED"

TEMPERATURE_MIN_QUANTITY = "air_temperature_min_2m"
TEMPERATURE_MAX_QUANTITY = "air_temperature_max_2m"
DEFAULT_TEMPERATURE_UNIT = "degC"

# Standard astronomical and calendar constants (not cultivar parameters).
_PI = 3.141592653589793
_HALF_PI = 1.5707963267948966
_QUARTER_PI = 0.7853981633974483
_TAU = 6.283185307179586
_DEG_TO_RAD = _PI / 180.0
_DAYS_PER_SOLAR_YEAR = 365.0
_SOLAR_DECLINATION_AMPLITUDE_RAD = 0.409
_SOLAR_DECLINATION_PHASE_RAD = 1.39
_HOURS_PER_HALF_DAY = 12.0
_HOURS_PER_DAY = 24.0
_MIN_LATITUDE_DEG = -90.0
_MAX_LATITUDE_DEG = 90.0
_MIN_DOY = 1
_MAX_DOY = 366
_DVS_EMERGENCE = 0.0
_DVS_FLOWERING = 1.0
_DVS_MATURITY = 2.0


def _sin_core(u: float) -> float:
    """Taylor series for ``sin(u)`` on ``|u| <= pi / 4`` to IEEE-754 precision."""
    u2 = u * u
    term = u
    total = term
    for k in range(1, 11):
        term *= -u2 / ((2 * k) * (2 * k + 1))
        total += term
    return total


def _cos_core(u: float) -> float:
    """Taylor series for ``cos(u)`` on ``|u| <= pi / 4`` to IEEE-754 precision."""
    u2 = u * u
    term = 1.0
    total = term
    for k in range(1, 11):
        term *= -u2 / ((2 * k - 1) * (2 * k))
        total += term
    return total


def _sin(x: float) -> float:
    """Pure-Python ``sin(x)`` via range reduction and core Taylor series."""
    reduced = ((x + _PI) % _TAU) - _PI
    if reduced > _HALF_PI:
        reduced = _PI - reduced
    elif reduced < -_HALF_PI:
        reduced = -_PI - reduced
    if abs(reduced) <= _QUARTER_PI:
        return _sin_core(reduced)
    sign = 1.0 if reduced >= 0.0 else -1.0
    return sign * _cos_core(_HALF_PI - abs(reduced))


def _cos(x: float) -> float:
    """Pure-Python ``cos(x)`` via range reduction and core Taylor series."""
    reduced = abs(((x + _PI) % _TAU) - _PI)
    if reduced > _HALF_PI:
        return -_cos(_PI - reduced)
    if reduced <= _QUARTER_PI:
        return _cos_core(reduced)
    return _sin_core(_HALF_PI - reduced)


def _asin_core(u: float) -> float:
    """Taylor series for ``asin(u)`` on ``|u| <= 0.5`` to IEEE-754 precision."""
    u2 = u * u
    central = 1.0
    power = u
    total = u
    for k in range(1, 28):
        central *= (2 * k - 1) / (2 * k)
        power *= u2
        total += central * power / (2 * k + 1)
    return total


def _acos(x: float) -> float:
    """Pure-Python ``acos(x)`` on ``[-1.0, 1.0]`` via half-angle reduction."""
    if x >= 1.0:
        return 0.0
    if x <= -1.0:
        return _PI
    if x > 0.5:
        return 2.0 * _asin_core(((1.0 - x) * 0.5) ** 0.5)
    if x < -0.5:
        return _PI - 2.0 * _asin_core(((1.0 + x) * 0.5) ** 0.5)
    return _HALF_PI - _asin_core(x)


def _is_strict_number(value: object) -> bool:
    """True for ``int`` or ``float``, excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_strict_int(value: object) -> bool:
    """True for ``int``, excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: object) -> bool:
    """True when ``value`` is a finite ``int`` or ``float`` (excluding ``bool``)."""
    if not _is_strict_number(value):
        return False
    assert isinstance(value, (int, float))
    try:
        x = float(value)
    except OverflowError:
        return False
    return abs(x) < float("inf")


def _is_date_object(value: object) -> bool:
    """True for a ``datetime.date`` instance, excluding ``datetime.datetime``."""
    cls = type(value)
    return (
        hasattr(value, "year")
        and hasattr(value, "month")
        and hasattr(value, "day")
        and hasattr(value, "toordinal")
        and hasattr(value, "timetuple")
        and hasattr(value, "isoformat")
        and not hasattr(value, "hour")
        and cls.__module__ == "datetime"
        and cls.__name__ == "date"
    )


def _require_finite_float(name: str, value: object) -> float:
    """Validate a strict, finite numeric argument (G5)."""
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected float or int, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite_number(value):
        raise ValueError(f"{name}: expected a finite number, got {value!r}")
    return float(value)


def _next_calendar_date(day: IsoDate) -> IsoDate:
    """Return the next Gregorian calendar date without importing ``datetime``."""
    return type(day).fromordinal(day.toordinal() + 1)


@dataclass(frozen=True)
class PhotoperiodParams:
    """Caller-supplied photoperiod bounds and response mode (zero defaults).

    Attributes:
        mode: ``"long_day"``, ``"short_day"``, or ``"neutral"``.
        dl_crit: Critical photoperiod in hours ``[0, 24]``. Below ``dl_crit``
            development halts (``0.0``) for ``"long_day"`` cultivars; above
            ``dl_crit`` development halts (``0.0``) for ``"short_day"``
            cultivars.
        dl_sat: Saturation photoperiod in hours ``[0, 24]``. At or above
            ``dl_sat`` photoperiod factor reaches ``1.0`` for ``"long_day"``;
            at or below ``dl_sat`` photoperiod factor reaches ``1.0`` for
            ``"short_day"``.
    """

    mode: PhotoperiodMode
    dl_crit: float
    dl_sat: float

    def __post_init__(self) -> None:
        if self.mode not in ("long_day", "short_day", "neutral"):
            raise ValueError(
                "photoperiod.mode: expected 'long_day', 'short_day', or "
                f"'neutral', got {self.mode!r}"
            )
        crit = _require_finite_float("photoperiod.dl_crit", self.dl_crit)
        sat = _require_finite_float("photoperiod.dl_sat", self.dl_sat)
        if not (0.0 <= crit <= _HOURS_PER_DAY):
            raise ValueError(f"photoperiod.dl_crit: expected in [0, 24], got {crit!r}")
        if not (0.0 <= sat <= _HOURS_PER_DAY):
            raise ValueError(f"photoperiod.dl_sat: expected in [0, 24], got {sat!r}")
        if self.mode == "long_day" and not (crit < sat):
            raise ValueError(
                "photoperiod: 'long_day' requires dl_crit < dl_sat, "
                f"got dl_crit={crit!r}, dl_sat={sat!r}"
            )
        if self.mode == "short_day" and not (sat < crit):
            raise ValueError(
                "photoperiod: 'short_day' requires dl_sat < dl_crit, "
                f"got dl_sat={sat!r}, dl_crit={crit!r}"
            )


@dataclass(frozen=True)
class VernalizationParams:
    """Caller-supplied vernalization cardinal temperatures and saturation (zero defaults).

    Attributes:
        v_base: Minimum temperature for vernalization accumulation (degC).
        v_opt_low: Lower bound of optimal vernalization temperature (degC).
        v_opt_high: Upper bound of optimal vernalization temperature (degC).
        v_max: Upper ceiling temperature for vernalization accumulation (degC).
        vsat_days: Effective vernalization days required for saturation (> 0).
        v_min_factor: Minimum pre-flowering rate factor in ``[0, 1]`` when
            accumulated vernalization is zero (``0.0`` = obligate).
    """

    v_base: float
    v_opt_low: float
    v_opt_high: float
    v_max: float
    vsat_days: float
    v_min_factor: float

    def __post_init__(self) -> None:
        vb = _require_finite_float("vernalization.v_base", self.v_base)
        vol = _require_finite_float("vernalization.v_opt_low", self.v_opt_low)
        voh = _require_finite_float("vernalization.v_opt_high", self.v_opt_high)
        vm = _require_finite_float("vernalization.v_max", self.v_max)
        vsat = _require_finite_float("vernalization.vsat_days", self.vsat_days)
        vmin = _require_finite_float("vernalization.v_min_factor", self.v_min_factor)
        if not (vb <= vol <= voh <= vm) or not (vb < vm):
            raise ValueError(
                "vernalization: expected v_base <= v_opt_low <= v_opt_high <= v_max "
                f"with v_base < v_max, got ({vb}, {vol}, {voh}, {vm})"
            )
        if vsat <= 0.0:
            raise ValueError(f"vernalization.vsat_days: expected > 0, got {vsat!r}")
        if not (0.0 <= vmin <= 1.0):
            raise ValueError(
                f"vernalization.v_min_factor: expected in [0, 1], got {vmin!r}"
            )


@dataclass(frozen=True)
class CultivarPhenologyParams:
    """Caller-supplied cultivar phenology parameters (zero hardcoded defaults).

    Every field is required from the caller; no cultivar constant is defaulted.
    """

    t_base: float
    t_opt: float
    t_max_ceiling: float
    tsum_emergence: float
    tsum1: float
    tsum2: float
    floral_initiation_dvs: float
    photoperiod: PhotoperiodParams | None
    vernalization: VernalizationParams | None

    def __post_init__(self) -> None:
        tb = _require_finite_float("t_base", self.t_base)
        to = _require_finite_float("t_opt", self.t_opt)
        tmax = _require_finite_float("t_max_ceiling", self.t_max_ceiling)
        tem = _require_finite_float("tsum_emergence", self.tsum_emergence)
        t1 = _require_finite_float("tsum1", self.tsum1)
        t2 = _require_finite_float("tsum2", self.tsum2)
        fi_dvs = _require_finite_float(
            "floral_initiation_dvs", self.floral_initiation_dvs
        )
        if not (tb < to <= tmax):
            raise ValueError(
                "cultivar cardinal temperatures must satisfy "
                f"t_base < t_opt <= t_max_ceiling, got ({tb}, {to}, {tmax})"
            )
        if tem < 0.0:
            raise ValueError(f"tsum_emergence: expected >= 0, got {tem!r}")
        if t1 <= 0.0:
            raise ValueError(f"tsum1: expected > 0, got {t1!r}")
        if t2 <= 0.0:
            raise ValueError(f"tsum2: expected > 0, got {t2!r}")
        if not (_DVS_EMERGENCE < fi_dvs < _DVS_FLOWERING):
            raise ValueError(
                "floral_initiation_dvs: expected strictly between 0 and 1, "
                f"got {fi_dvs!r}"
            )
        if self.photoperiod is not None and not isinstance(
            self.photoperiod, PhotoperiodParams
        ):
            raise TypeError(
                "photoperiod: expected PhotoperiodParams or None, "
                f"got {type(self.photoperiod).__name__} (G5)"
            )
        if self.vernalization is not None and not isinstance(
            self.vernalization, VernalizationParams
        ):
            raise TypeError(
                "vernalization: expected VernalizationParams or None, "
                f"got {type(self.vernalization).__name__} (G5)"
            )


@dataclass(frozen=True)
class DailyThermalInput:
    """One day of minimum and maximum air temperature (degC) for phenology."""

    date: IsoDate
    tmin_c: float | Missing | None
    tmax_c: float | Missing | None

    def __post_init__(self) -> None:
        if not _is_date_object(self.date):
            raise TypeError(
                f"DailyThermalInput.date: expected datetime.date, got {type(self.date).__name__} (G5)"
            )
        for name, val in (("tmin_c", self.tmin_c), ("tmax_c", self.tmax_c)):
            if (
                val is not None
                and not isinstance(val, Missing)
                and not _is_strict_number(val)
            ):
                raise TypeError(
                    f"DailyThermalInput.{name}: expected float, int, Missing, or None, "
                    f"got {type(val).__name__} (G5)"
                )


@dataclass(frozen=True)
class CalibrationMetadata:
    """Local phenology calibration declaration (§15.3 / §15.7 guard)."""

    calibrated: bool
    source: str
    local_error_days: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.calibrated, bool):
            raise TypeError(
                "CalibrationMetadata.calibrated: expected bool, "
                f"got {type(self.calibrated).__name__} (G5)"
            )
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("CalibrationMetadata.source: expected a non-empty string")
        if self.local_error_days is not None:
            err = _require_finite_float(
                "CalibrationMetadata.local_error_days", self.local_error_days
            )
            if err < 0.0:
                raise ValueError(
                    f"CalibrationMetadata.local_error_days: expected >= 0, got {err!r}"
                )


@dataclass(frozen=True)
class DvsPoint:
    """One daily entry of the simulated development stage (DVS) series."""

    date: IsoDate
    dvs: float | None
    daylength_hours: float | Missing
    daily_thermal_time: float | Missing
    vernalization_days: float | Missing
    missing: Missing | None = None


@dataclass(frozen=True)
class PhenologySimulationResult:
    """Predicted crop phenology events, daily DVS series, and calibration status.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    sowing_date: IsoDate
    emergence_date: IsoDate | Missing
    floral_initiation_date: IsoDate | Missing
    flowering_date: IsoDate | Missing
    maturity_date: IsoDate | Missing
    dvs_series: tuple[DvsPoint, ...]
    calibration_status: CalibrationStatus
    local_error_days: float | None
    local_error_missing: Missing | None
    provenance: str


def day_of_year(day: IsoDate) -> int:
    """Ordinal day of the Gregorian calendar year (1..366)."""
    if not _is_date_object(day):
        raise TypeError(f"day: expected datetime.date, got {type(day).__name__} (G5)")
    return day.timetuple().tm_yday


def astronomical_daylength_hours(latitude_deg: float, doy: int) -> float:
    """Pure-geometry astronomical daylength (hours) from latitude and day of year.

    Uses standard solar declination and sunset hour-angle trigonometry via
    pure-Python arithmetic (zero external phenology code):

    - Solar declination: ``delta = 0.409 * sin(2 * pi * doy / 365 - 1.39)``
    - Hour-angle cosine: ``cos_ws = -tan(phi) * tan(delta)``
    - Polar day (``cos_ws <= -1``) returns ``24.0``; polar night
      (``cos_ws >= 1``) returns ``0.0``; otherwise ``(24 / pi) * acos(cos_ws)``.
    """
    lat = _require_finite_float("latitude_deg", latitude_deg)
    if not (_MIN_LATITUDE_DEG <= lat <= _MAX_LATITUDE_DEG):
        raise ValueError(f"latitude_deg: expected in [-90, 90], got {lat!r}")
    if not _is_strict_int(doy):
        raise TypeError(f"doy: expected int, got {type(doy).__name__} (G5)")
    if not (_MIN_DOY <= doy <= _MAX_DOY):
        raise ValueError(f"doy: expected in [1, 366], got {doy!r}")

    declination = _SOLAR_DECLINATION_AMPLITUDE_RAD * _sin(
        _TAU * doy / _DAYS_PER_SOLAR_YEAR - _SOLAR_DECLINATION_PHASE_RAD
    )
    lat_rad = lat * _DEG_TO_RAD
    # Express -tan(phi) * tan(delta) via sin/cos to handle +/-90 deg poles safely.
    cos_product = _cos(lat_rad) * _cos(declination)
    sin_product = _sin(lat_rad) * _sin(declination)
    if cos_product == 0.0:
        return _HOURS_PER_DAY if sin_product > 0.0 else 0.0
    cos_ws = -sin_product / cos_product
    if cos_ws <= -1.0:
        return _HOURS_PER_DAY
    if cos_ws >= 1.0:
        return 0.0
    hour_angle = _acos(cos_ws)
    return (_HOURS_PER_DAY / _PI) * hour_angle


def daily_thermal_time(
    tmin_c: float,
    tmax_c: float,
    params: CultivarPhenologyParams,
) -> float:
    """Effective daily thermal units (degC-days) from ``tmin_c``, ``tmax_c``, and cardinal temperatures.

    Uses the daily arithmetic mean ``(tmin_c + tmax_c) / 2`` with a bilinear
    cardinal response: ``0`` at or below ``t_base``, linear rise ``T - t_base``
    up to ``t_opt``, linear decline from ``t_opt - t_base`` down to ``0`` at
    ``t_max_ceiling`` (when ``t_opt < t_max_ceiling``), and ``0`` above
    ``t_max_ceiling``.
    """
    if not isinstance(params, CultivarPhenologyParams):
        raise TypeError(
            f"params: expected CultivarPhenologyParams, got {type(params).__name__} (G5)"
        )
    tmin = _require_finite_float("tmin_c", tmin_c)
    tmax = _require_finite_float("tmax_c", tmax_c)
    if tmax < tmin:
        raise ValueError(f"tmax_c ({tmax!r}) must be >= tmin_c ({tmin!r})")

    tmean = 0.5 * (tmin + tmax)
    if tmean <= params.t_base:
        return 0.0
    if tmean <= params.t_opt:
        return tmean - params.t_base
    if params.t_opt == params.t_max_ceiling or tmean >= params.t_max_ceiling:
        return 0.0
    max_rate = params.t_opt - params.t_base
    return (
        max_rate
        * (params.t_max_ceiling - tmean)
        / (params.t_max_ceiling - params.t_opt)
    )


def photoperiod_factor(
    daylength_hours: float,
    photoperiod: PhotoperiodParams | None,
) -> float:
    """Dimensionless photoperiod multiplier in ``[0.0, 1.0]``."""
    dl = _require_finite_float("daylength_hours", daylength_hours)
    if not (0.0 <= dl <= _HOURS_PER_DAY):
        raise ValueError(f"daylength_hours: expected in [0, 24], got {dl!r}")
    if photoperiod is None:
        return 1.0
    if not isinstance(photoperiod, PhotoperiodParams):
        raise TypeError(
            "photoperiod: expected PhotoperiodParams or None, "
            f"got {type(photoperiod).__name__} (G5)"
        )
    if photoperiod.mode == "neutral":
        return 1.0
    if photoperiod.mode == "long_day":
        if dl <= photoperiod.dl_crit:
            return 0.0
        if dl >= photoperiod.dl_sat:
            return 1.0
        return (dl - photoperiod.dl_crit) / (photoperiod.dl_sat - photoperiod.dl_crit)
    # short_day: dl_sat < dl_crit
    if dl <= photoperiod.dl_sat:
        return 1.0
    if dl >= photoperiod.dl_crit:
        return 0.0
    return (photoperiod.dl_crit - dl) / (photoperiod.dl_crit - photoperiod.dl_sat)


def vernalization_effectiveness(
    tmean_c: float,
    vernalization: VernalizationParams,
) -> float:
    """Daily effective vernalization increment in ``[0.0, 1.0]``."""
    if not isinstance(vernalization, VernalizationParams):
        raise TypeError(
            "vernalization: expected VernalizationParams, "
            f"got {type(vernalization).__name__} (G5)"
        )
    tmean = _require_finite_float("tmean_c", tmean_c)
    if tmean <= vernalization.v_base or tmean >= vernalization.v_max:
        return 0.0
    if vernalization.v_opt_low <= tmean <= vernalization.v_opt_high:
        return 1.0
    if tmean < vernalization.v_opt_low:
        return (tmean - vernalization.v_base) / (
            vernalization.v_opt_low - vernalization.v_base
        )
    return (vernalization.v_max - tmean) / (
        vernalization.v_max - vernalization.v_opt_high
    )


def vernalization_factor(
    accumulated_vern_days: float,
    vernalization: VernalizationParams | None,
) -> float:
    """Dimensionless vernalization multiplier in ``[v_min_factor, 1.0]``."""
    if vernalization is None:
        return 1.0
    if not isinstance(vernalization, VernalizationParams):
        raise TypeError(
            "vernalization: expected VernalizationParams or None, "
            f"got {type(vernalization).__name__} (G5)"
        )
    acc = _require_finite_float("accumulated_vern_days", accumulated_vern_days)
    if acc < 0.0:
        raise ValueError(f"accumulated_vern_days: expected >= 0, got {acc!r}")
    frac = min(1.0, acc / vernalization.vsat_days)
    return vernalization.v_min_factor + (1.0 - vernalization.v_min_factor) * frac


def _series_map_by_date(
    series: DailySeries, expected_unit: str
) -> dict[IsoDate, DailyValue]:
    if series.unit != expected_unit:
        raise ValueError(
            f"series {series.quantity!r}: expected unit {expected_unit!r}, "
            f"got {series.unit!r}"
        )
    return {item.date: item for item in series.days}


def daily_thermal_inputs_from_site_climate(
    climate: SiteClimate,
) -> tuple[DailyThermalInput, ...]:
    """Extract aligned ``DailyThermalInput`` records from a ``SiteClimate`` contract.

    Checks that both ``air_temperature_min_2m`` and ``air_temperature_max_2m``
    exist, carry unit ``"degC"``, and share the same ``time_zone`` (C6.3).
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    by_qty = {series.quantity: series for series in climate.daily_series}
    tmin_series = by_qty.get(TEMPERATURE_MIN_QUANTITY)
    tmax_series = by_qty.get(TEMPERATURE_MAX_QUANTITY)
    if tmin_series is None:
        raise ValueError(
            f"climate.daily_series is missing {TEMPERATURE_MIN_QUANTITY!r}"
        )
    if tmax_series is None:
        raise ValueError(
            f"climate.daily_series is missing {TEMPERATURE_MAX_QUANTITY!r}"
        )
    if tmin_series.time_zone != tmax_series.time_zone:
        raise ValueError(
            "daily series time_zone mismatch between "
            f"{TEMPERATURE_MIN_QUANTITY!r} ({tmin_series.time_zone!r}) and "
            f"{TEMPERATURE_MAX_QUANTITY!r} ({tmax_series.time_zone!r}) (C6.3)"
        )
    tmin_by_date = _series_map_by_date(tmin_series, DEFAULT_TEMPERATURE_UNIT)
    tmax_by_date = _series_map_by_date(tmax_series, DEFAULT_TEMPERATURE_UNIT)

    all_dates = sorted(set(tmin_by_date) | set(tmax_by_date))
    records: list[DailyThermalInput] = []
    for day in all_dates:
        tmin_item = tmin_by_date.get(day)
        tmax_item = tmax_by_date.get(day)
        tmin_val: float | Missing | None = (
            None
            if tmin_item is None
            else (
                Missing(
                    reason=tmin_item.missing.reason,
                    detail=tmin_item.missing.detail,
                )
                if tmin_item.missing is not None
                else tmin_item.value
            )
        )
        tmax_val: float | Missing | None = (
            None
            if tmax_item is None
            else (
                Missing(
                    reason=tmax_item.missing.reason,
                    detail=tmax_item.missing.detail,
                )
                if tmax_item.missing is not None
                else tmax_item.value
            )
        )
        records.append(DailyThermalInput(date=day, tmin_c=tmin_val, tmax_c=tmax_val))
    return tuple(records)


def _check_daily_temperatures(day: DailyThermalInput) -> Missing | None:
    """Return ``Missing(reason='MISSING_INPUT', ...)`` if daily temps are unusable."""
    day_iso = day.date.isoformat()
    for label, val in (("tmin_c", day.tmin_c), ("tmax_c", day.tmax_c)):
        if val is None:
            return Missing(
                reason="MISSING_INPUT",
                detail=f"{label} is None on {day_iso} during active growth",
            )
        if isinstance(val, Missing):
            detail = (
                f"{label} is missing on {day_iso} during active growth "
                f"({val.reason}: {val.detail})"
                if val.detail is not None
                else f"{label} is missing on {day_iso} during active growth ({val.reason})"
            )
            return Missing(reason="MISSING_INPUT", detail=detail)
        if not _is_finite_number(val):
            return Missing(
                reason="MISSING_INPUT",
                detail=f"{label} is non-finite ({val!r}) on {day_iso} during active growth",
            )
    assert _is_strict_number(day.tmin_c) and _is_strict_number(day.tmax_c)
    if day.tmax_c < day.tmin_c:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"tmax_c ({day.tmax_c}) < tmin_c ({day.tmin_c}) on {day_iso} "
                "during active growth"
            ),
        )
    return None


def _evaluate_calibration(
    *,
    flowering_date: IsoDate | Missing,
    observed_flowering_dates: Sequence[IsoDate] | None,
    calibration_metadata: CalibrationMetadata | None,
) -> tuple[CalibrationStatus, float | None, Missing | None]:
    """Enforce §15.3 / §15.7 local-calibration provenance guard."""
    if observed_flowering_dates is None or len(observed_flowering_dates) == 0:
        return (
            UNCALIBRATED_STATUS,
            None,
            Missing(
                reason="MISSING_INPUT",
                detail="observed_flowering_dates absent: cultivar phenology is UNCALIBRATED (§15.3/§15.7)",
            ),
        )
    if calibration_metadata is None or not calibration_metadata.calibrated:
        return (
            UNCALIBRATED_STATUS,
            None,
            Missing(
                reason="MISSING_INPUT",
                detail="local calibration_metadata is absent or uncalibrated (§15.3/§15.7)",
            ),
        )
    if calibration_metadata.local_error_days is not None:
        return (
            CALIBRATED_STATUS,
            float(calibration_metadata.local_error_days),
            None,
        )
    if not isinstance(flowering_date, Missing) and len(observed_flowering_dates) == 1:
        err = float(abs((flowering_date - observed_flowering_dates[0]).days))
        return (CALIBRATED_STATUS, err, None)
    return (
        UNCALIBRATED_STATUS,
        None,
        Missing(
            reason="MISSING_INPUT",
            detail=(
                "local_error_days could not be established from calibration_metadata "
                "and observed_flowering_dates (§15.3/§15.7)"
            ),
        ),
    )


def _validate_simulation_inputs(
    daily_weather: object,
    latitude_deg: object,
    sowing_date: object,
    params: object,
    observed_flowering_dates: object,
    calibration_metadata: object,
) -> tuple[tuple[DailyThermalInput, ...], float | Missing]:
    """Validate caller arguments (G5) and return normalized weather + latitude."""
    if isinstance(daily_weather, (str, bytes, bytearray)) or not isinstance(
        daily_weather, Sequence
    ):
        raise TypeError(
            "daily_weather: expected a Sequence of DailyThermalInput, "
            f"got {type(daily_weather).__name__} (G5)"
        )
    weather_items: list[DailyThermalInput] = []
    prev_date: IsoDate | None = None
    for item in daily_weather:
        if not isinstance(item, DailyThermalInput):
            raise TypeError(
                "daily_weather: expected DailyThermalInput elements, "
                f"got {type(item).__name__} (G5)"
            )
        if prev_date is not None and item.date <= prev_date:
            raise ValueError(
                "daily_weather dates must be strictly increasing; "
                f"got {item.date.isoformat()} after {prev_date.isoformat()}"
            )
        prev_date = item.date
        weather_items.append(item)

    if not _is_date_object(sowing_date):
        raise TypeError(
            f"sowing_date: expected datetime.date, got {type(sowing_date).__name__} (G5)"
        )
    if not isinstance(params, CultivarPhenologyParams):
        raise TypeError(
            "params: expected CultivarPhenologyParams, "
            f"got {type(params).__name__} (G5)"
        )

    lat_val: float | Missing
    if isinstance(latitude_deg, Missing):
        lat_val = latitude_deg
    elif _is_strict_number(latitude_deg):
        assert isinstance(latitude_deg, (int, float))
        if not _is_finite_number(latitude_deg):
            lat_val = Missing(
                reason="MISSING_INPUT",
                detail=f"latitude_deg is non-finite ({latitude_deg!r})",
            )
        else:
            lat_float = float(latitude_deg)
            if not (_MIN_LATITUDE_DEG <= lat_float <= _MAX_LATITUDE_DEG):
                raise ValueError(
                    f"latitude_deg: expected in [-90, 90], got {lat_float!r}"
                )
            lat_val = lat_float
    else:
        raise TypeError(
            "latitude_deg: expected float, int, or Missing, "
            f"got {type(latitude_deg).__name__} (G5)"
        )

    if observed_flowering_dates is not None:
        if isinstance(
            observed_flowering_dates, (str, bytes, bytearray)
        ) or not isinstance(observed_flowering_dates, Sequence):
            raise TypeError(
                "observed_flowering_dates: expected a Sequence of datetime.date or None, "
                f"got {type(observed_flowering_dates).__name__} (G5)"
            )
        for obs in observed_flowering_dates:
            if not _is_date_object(obs):
                raise TypeError(
                    "observed_flowering_dates: expected datetime.date elements, "
                    f"got {type(obs).__name__} (G5)"
                )

    if calibration_metadata is not None and not isinstance(
        calibration_metadata, CalibrationMetadata
    ):
        raise TypeError(
            "calibration_metadata: expected CalibrationMetadata or None, "
            f"got {type(calibration_metadata).__name__} (G5)"
        )

    return tuple(weather_items), lat_val


def simulate_crop_phenology(
    daily_weather: Sequence[DailyThermalInput],
    *,
    latitude_deg: float | Missing,
    sowing_date: IsoDate,
    params: CultivarPhenologyParams,
    observed_flowering_dates: Sequence[IsoDate] | None = None,
    calibration_metadata: CalibrationMetadata | None = None,
) -> PhenologySimulationResult:
    """Simulate daily thermal-photoperiod-vernalization phenology from sowing to maturity.

    Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Predicts ``(emergence_date, floral_initiation_date, flowering_date,
    maturity_date, dvs_series)`` with strict G4/C3.3 missing-value propagation
    and §15.3/§15.7 local-calibration tagging.
    """
    weather, lat_or_missing = _validate_simulation_inputs(
        daily_weather,
        latitude_deg,
        sowing_date,
        params,
        observed_flowering_dates,
        calibration_metadata,
    )

    if isinstance(lat_or_missing, Missing):
        lat_missing = Missing(
            reason="MISSING_INPUT",
            detail=(
                f"latitude_deg is missing ({lat_or_missing.reason}: {lat_or_missing.detail})"
                if lat_or_missing.detail is not None
                else f"latitude_deg is missing ({lat_or_missing.reason})"
            ),
        )
        cal_status, cal_err, cal_err_missing = _evaluate_calibration(
            flowering_date=lat_missing,
            observed_flowering_dates=observed_flowering_dates,
            calibration_metadata=calibration_metadata,
        )
        return PhenologySimulationResult(
            sowing_date=sowing_date,
            emergence_date=lat_missing,
            floral_initiation_date=lat_missing,
            flowering_date=lat_missing,
            maturity_date=lat_missing,
            dvs_series=(),
            calibration_status=cal_status,
            local_error_days=cal_err,
            local_error_missing=cal_err_missing,
            provenance="SIMULATED",
        )

    start_idx: int | None = None
    for idx, entry in enumerate(weather):
        if entry.date == sowing_date:
            start_idx = idx
            break
        if entry.date > sowing_date:
            break

    if start_idx is None:
        no_cov = Missing(
            reason="NO_COVERAGE",
            detail=f"daily_weather does not cover sowing_date {sowing_date.isoformat()}",
        )
        cal_status, cal_err, cal_err_missing = _evaluate_calibration(
            flowering_date=no_cov,
            observed_flowering_dates=observed_flowering_dates,
            calibration_metadata=calibration_metadata,
        )
        return PhenologySimulationResult(
            sowing_date=sowing_date,
            emergence_date=no_cov,
            floral_initiation_date=no_cov,
            flowering_date=no_cov,
            maturity_date=no_cov,
            dvs_series=(),
            calibration_status=cal_status,
            local_error_days=cal_err,
            local_error_missing=cal_err_missing,
            provenance="SIMULATED",
        )

    emerged = False
    em_tt_acc = 0.0
    pre_tt_acc = 0.0
    post_tt_acc = 0.0
    dvs = _DVS_EMERGENCE
    vern_days_acc = 0.0

    emergence_date: IsoDate | None = None
    floral_initiation_date: IsoDate | None = None
    flowering_date: IsoDate | None = None
    maturity_date: IsoDate | None = None

    dvs_points: list[DvsPoint] = []
    halted_missing: Missing | None = None
    expected_date = sowing_date

    for entry in weather[start_idx:]:
        if maturity_date is not None:
            break

        if entry.date != expected_date and halted_missing is None:
            halted_missing = Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"missing daily_weather record on {expected_date.isoformat()} "
                    "during active growth"
                ),
            )

        if halted_missing is not None:
            dl = astronomical_daylength_hours(lat_or_missing, day_of_year(entry.date))
            dvs_points.append(
                DvsPoint(
                    date=entry.date,
                    dvs=None,
                    daylength_hours=dl,
                    daily_thermal_time=halted_missing,
                    vernalization_days=halted_missing,
                    missing=halted_missing,
                )
            )
            expected_date = _next_calendar_date(entry.date)
            continue

        temp_missing = _check_daily_temperatures(entry)
        dl = astronomical_daylength_hours(lat_or_missing, day_of_year(entry.date))
        if temp_missing is not None:
            halted_missing = temp_missing
            dvs_points.append(
                DvsPoint(
                    date=entry.date,
                    dvs=None,
                    daylength_hours=dl,
                    daily_thermal_time=halted_missing,
                    vernalization_days=halted_missing,
                    missing=halted_missing,
                )
            )
            expected_date = _next_calendar_date(entry.date)
            continue

        assert _is_strict_number(entry.tmin_c) and _is_strict_number(entry.tmax_c)
        tmin = float(entry.tmin_c)
        tmax = float(entry.tmax_c)
        tmean = 0.5 * (tmin + tmax)
        tt = daily_thermal_time(tmin, tmax, params)

        if not emerged:
            em_tt_acc += tt
            if em_tt_acc >= params.tsum_emergence:
                emerged = True
                emergence_date = entry.date
                dvs = _DVS_EMERGENCE
        elif flowering_date is None:
            if params.vernalization is not None:
                vern_days_acc = min(
                    params.vernalization.vsat_days,
                    vern_days_acc
                    + vernalization_effectiveness(tmean, params.vernalization),
                )
            f_vern = vernalization_factor(vern_days_acc, params.vernalization)
            f_photo = photoperiod_factor(dl, params.photoperiod)
            pre_tt_acc += tt * f_photo * f_vern
            dvs = min(_DVS_FLOWERING, pre_tt_acc / params.tsum1)
            if floral_initiation_date is None and dvs >= params.floral_initiation_dvs:
                floral_initiation_date = entry.date
            if pre_tt_acc >= params.tsum1:
                dvs = _DVS_FLOWERING
                flowering_date = entry.date
        else:
            post_tt_acc += tt
            if post_tt_acc >= params.tsum2:
                dvs = _DVS_MATURITY
                maturity_date = entry.date
            else:
                dvs = _DVS_FLOWERING + (post_tt_acc / params.tsum2)

        dvs_points.append(
            DvsPoint(
                date=entry.date,
                dvs=dvs,
                daylength_hours=dl,
                daily_thermal_time=tt,
                vernalization_days=vern_days_acc,
                missing=None,
            )
        )
        expected_date = _next_calendar_date(entry.date)

    last_seen = weather[-1].date.isoformat()

    def _unresolved(stage_name: str) -> Missing:
        if halted_missing is not None:
            return halted_missing
        return Missing(
            reason="NO_COVERAGE",
            detail=(
                f"daily_weather ended on {last_seen} before {stage_name} was reached"
            ),
        )

    final_em: IsoDate | Missing = (
        emergence_date if emergence_date is not None else _unresolved("emergence_date")
    )
    final_fi: IsoDate | Missing = (
        floral_initiation_date
        if floral_initiation_date is not None
        else _unresolved("floral_initiation_date")
    )
    final_fl: IsoDate | Missing = (
        flowering_date if flowering_date is not None else _unresolved("flowering_date")
    )
    final_mat: IsoDate | Missing = (
        maturity_date if maturity_date is not None else _unresolved("maturity_date")
    )

    cal_status, cal_err, cal_err_missing = _evaluate_calibration(
        flowering_date=final_fl,
        observed_flowering_dates=observed_flowering_dates,
        calibration_metadata=calibration_metadata,
    )

    return PhenologySimulationResult(
        sowing_date=sowing_date,
        emergence_date=final_em,
        floral_initiation_date=final_fi,
        flowering_date=final_fl,
        maturity_date=final_mat,
        dvs_series=tuple(dvs_points),
        calibration_status=cal_status,
        local_error_days=cal_err,
        local_error_missing=cal_err_missing,
        provenance="SIMULATED",
    )
