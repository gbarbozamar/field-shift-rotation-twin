"""Multi-year candidate sowing-date risk sweep across separated climate horizons.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13), Frontier Unit F-11
(``27_PLAN_DE_FRONTERA.md`` §§15.2, 15.3, 15.7).

Decoupling rule: this module does NOT import
``engine.calendar.thermal_phenology``. Phenology is injected strictly through
the ``PhenologyEvaluator`` Protocol (``Callable[[date], PhenologyOutcome |
Missing]``).

Climate horizon separation: ``historical``, ``synthetic``, and ``future``
horizons — and distinct future datasets/ensembles such as ``NEX-GDDP-CMIP6``
and ``ISIMIP3b`` — stay keyed and tagged separately and are never pooled or
averaged together.

Orientation-only guard (§15.7): every output is tagged
``orientation_only=True`` and ``replaces_agronomist_recommendation=False``.
Missing climate, water, or phenology inputs keep the affected candidate
date-year in ``unevaluated_years`` with typed ``Missing`` (never ``0`` or
``0.0``).

Pure function (G1): no file access, no network call, no clock, no environment
variables, no global mutable state, and caller arguments are never mutated.
Zero hardcoded crop thresholds or calibration constants.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.results.models import Missing

__all__ = [
    "ACCEPTED_TEMPERATURE_UNIT",
    "HORIZON_KINDS",
    "TEMPERATURE_MAX_QUANTITY",
    "TEMPERATURE_MIN_QUANTITY",
    "CandidateSowingDate",
    "CandidateSowingSummary",
    "ClimateHorizon",
    "CriticalWaterEvaluator",
    "EvaluatedCandidateYear",
    "HorizonKind",
    "HorizonSweepResult",
    "PhenologyEvaluator",
    "PhenologyOutcome",
    "RiskCount",
    "RiskWindowConfig",
    "SowingWindowSweepResult",
    "UnevaluatedCandidateYear",
    "horizon_from_site_climate",
    "sweep_sowing_windows",
]

HorizonKind = Literal["historical", "synthetic", "future"]
HORIZON_KINDS: tuple[HorizonKind, ...] = ("historical", "synthetic", "future")

# Decided temperature quantities and unit from contracts/CLIMATE_QUANTITIES.md (CQ2, CQ3).
TEMPERATURE_MIN_QUANTITY = "air_temperature_min_2m"
TEMPERATURE_MAX_QUANTITY = "air_temperature_max_2m"
ACCEPTED_TEMPERATURE_UNIT = "degC"

_LEAP_REFERENCE_YEAR = 2000
_MONTHS_IN_YEAR = 12
_MM_DD_PARTS = 2
_MM_DD_PART_LEN = 2


def _is_strict_int(value: object) -> bool:
    """Return True for ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_number(value: object) -> bool:
    """Return True for ``int`` or ``float`` excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: float) -> bool:
    """Return True when ``value`` is finite, guarding large-int overflow."""
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _require_non_empty_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__} (G5)")
    if not value.strip():
        raise ValueError(f"{name}: must be a non-empty, non-blank string")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if not _is_strict_int(value):
        raise TypeError(f"{name}: expected int, got {type(value).__name__} (G5)")
    assert isinstance(value, int)
    if value < 0:
        raise ValueError(f"{name}: must be >= 0, got {value}")
    return value


def _require_finite_number(name: str, value: object) -> float:
    if not _is_strict_number(value):
        raise TypeError(
            f"{name}: expected float or int, got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite_number(value):
        raise ValueError(f"{name}: must be a finite number, got {value!r}")
    return float(value)


def _require_orientation_tags(
    orientation_only: object,
    replaces_agronomist_recommendation: object,
    what: str,
) -> None:
    if orientation_only is not True:
        raise ValueError(f"{what}: orientation_only must always be True (§15.7)")
    if replaces_agronomist_recommendation is not False:
        raise ValueError(
            f"{what}: replaces_agronomist_recommendation must always be False (§15.7)"
        )


def _check_date_mapping(name: str, mapping: Mapping[dt.date, float | Missing]) -> None:
    if not isinstance(mapping, Mapping):
        raise TypeError(f"{name}: expected Mapping, got {type(mapping).__name__} (G5)")
    for key, val in mapping.items():
        if not isinstance(key, dt.date) or isinstance(key, dt.datetime):
            raise TypeError(
                f"{name}: keys must be datetime.date, got {type(key).__name__} (G5)"
            )
        if not isinstance(val, Missing) and not _is_strict_number(val):
            raise TypeError(
                f"{name}[{key.isoformat()}]: expected float, int, or Missing, "
                f"got {type(val).__name__} (G5)"
            )


@dataclass(frozen=True)
class CandidateSowingDate:
    """Caller-supplied candidate sowing date as month and day (``MM-DD``).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    month: int
    day: int

    def __post_init__(self) -> None:
        if not _is_strict_int(self.month) or not _is_strict_int(self.day):
            raise TypeError("CandidateSowingDate: month and day must be int (G5)")
        if not (1 <= self.month <= _MONTHS_IN_YEAR):
            raise ValueError(
                f"CandidateSowingDate: month must be in 1..12, got {self.month}"
            )
        try:
            dt.date(_LEAP_REFERENCE_YEAR, self.month, self.day)
        except ValueError as exc:
            raise ValueError(
                f"CandidateSowingDate: invalid MM-DD {self.month:02d}-{self.day:02d}: {exc}"
            ) from exc

    @property
    def mm_dd(self) -> str:
        """Canonical ``MM-DD`` string."""
        return f"{self.month:02d}-{self.day:02d}"

    @classmethod
    def parse(cls, value: CandidateSowingDate | str) -> CandidateSowingDate:
        """Normalize a ``CandidateSowingDate`` or strict ``MM-DD`` string."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(
                "candidate sowing date: expected CandidateSowingDate or 'MM-DD' str, "
                f"got {type(value).__name__} (G5)"
            )
        parts = value.split("-")
        if (
            len(parts) != _MM_DD_PARTS
            or len(parts[0]) != _MM_DD_PART_LEN
            or len(parts[1]) != _MM_DD_PART_LEN
            or not (parts[0].isdigit() and parts[1].isdigit())
        ):
            raise ValueError(
                f"candidate sowing date: expected format 'MM-DD', got {value!r}"
            )
        return cls(month=int(parts[0]), day=int(parts[1]))

    def resolve_for_year(self, year: int) -> tuple[dt.date, bool]:
        """Resolve ``MM-DD`` in calendar ``year`` (Feb 29 -> Feb 28 in non-leap years)."""
        if not _is_strict_int(year):
            raise TypeError(f"year: expected int, got {type(year).__name__} (G5)")
        try:
            return dt.date(year, self.month, self.day), False
        except ValueError:
            return dt.date(year, 2, 28), True


@dataclass(frozen=True)
class PhenologyOutcome:
    """Phenology outcome returned by a ``PhenologyEvaluator`` for one sowing date.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    sowing_date: dt.date
    flowering_date: dt.date | Missing
    maturity_date: dt.date | Missing
    harvest_date: dt.date | Missing | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sowing_date, dt.date) or isinstance(
            self.sowing_date, dt.datetime
        ):
            raise TypeError("PhenologyOutcome.sowing_date must be datetime.date (G5)")
        for field_name, val in (
            ("flowering_date", self.flowering_date),
            ("maturity_date", self.maturity_date),
        ):
            if not isinstance(val, (dt.date, Missing)) or isinstance(val, dt.datetime):
                raise TypeError(
                    f"PhenologyOutcome.{field_name} must be datetime.date or Missing (G5)"
                )
        if self.harvest_date is not None and (
            not isinstance(self.harvest_date, (dt.date, Missing))
            or isinstance(self.harvest_date, dt.datetime)
        ):
            raise TypeError(
                "PhenologyOutcome.harvest_date must be datetime.date, Missing, or None (G5)"
            )


@runtime_checkable
class PhenologyEvaluator(Protocol):
    """Protocol decoupling the sowing-window sweep from thermal phenology (F-11).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    def __call__(self, sowing_date: dt.date, /) -> PhenologyOutcome | Missing: ...


@runtime_checkable
class CriticalWaterEvaluator(Protocol):
    """Protocol returning critical-period mean transpiration ratio over ``[start, end]``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    def __call__(
        self, window_start: dt.date, window_end: dt.date, /
    ) -> float | Missing: ...


@dataclass(frozen=True)
class RiskWindowConfig:
    """Caller-supplied flowering window offsets and stress event thresholds.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    All crop-specific offsets and thresholds are required from the caller;
    this module holds zero hardcoded crop thresholds.
    """

    pre_days: int
    post_days: int
    frost_threshold_c: float
    heat_threshold_c: float
    min_heat_consecutive_days: int
    water_ratio_threshold: float
    critical_pre_days: int | None = None
    critical_post_days: int | None = None
    harvest_lag_days: int = 0
    successor_turnaround_days: int = 0
    successor_sowing_mm_dd: CandidateSowingDate | str | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int("pre_days", self.pre_days)
        _require_non_negative_int("post_days", self.post_days)
        if self.critical_pre_days is not None:
            _require_non_negative_int("critical_pre_days", self.critical_pre_days)
        if self.critical_post_days is not None:
            _require_non_negative_int("critical_post_days", self.critical_post_days)

        object.__setattr__(
            self,
            "frost_threshold_c",
            _require_finite_number("frost_threshold_c", self.frost_threshold_c),
        )
        object.__setattr__(
            self,
            "heat_threshold_c",
            _require_finite_number("heat_threshold_c", self.heat_threshold_c),
        )
        if not _is_strict_int(self.min_heat_consecutive_days):
            raise TypeError(
                "min_heat_consecutive_days: expected int, "
                f"got {type(self.min_heat_consecutive_days).__name__} (G5)"
            )
        if self.min_heat_consecutive_days < 1:
            raise ValueError(
                "min_heat_consecutive_days: must be >= 1, "
                f"got {self.min_heat_consecutive_days}"
            )
        water_thr = _require_finite_number(
            "water_ratio_threshold", self.water_ratio_threshold
        )
        if water_thr < 0.0:
            raise ValueError(f"water_ratio_threshold: must be >= 0.0, got {water_thr}")
        object.__setattr__(self, "water_ratio_threshold", water_thr)
        _require_non_negative_int("harvest_lag_days", self.harvest_lag_days)
        _require_non_negative_int(
            "successor_turnaround_days", self.successor_turnaround_days
        )
        if self.successor_sowing_mm_dd is not None:
            object.__setattr__(
                self,
                "successor_sowing_mm_dd",
                CandidateSowingDate.parse(self.successor_sowing_mm_dd),
            )

    @property
    def effective_critical_pre_days(self) -> int:
        """Days before flowering used for critical-period water stress."""
        return (
            self.pre_days if self.critical_pre_days is None else self.critical_pre_days
        )

    @property
    def effective_critical_post_days(self) -> int:
        """Days after flowering used for critical-period water stress."""
        return (
            self.post_days
            if self.critical_post_days is None
            else self.critical_post_days
        )


@dataclass(frozen=True)
class ClimateHorizon:
    """One separated climate horizon stream for sowing-window risk evaluation.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Each horizon carries an explicit ``horizon_id``, ``horizon_kind``
    (``"historical"``, ``"synthetic"``, or ``"future"``), and ``source_tag``
    (e.g. ``"NASA_POWER"``, ``"NEX-GDDP-CMIP6"``, ``"ISIMIP3b"``) so distinct
    horizons and datasets are never pooled or averaged together.
    """

    horizon_id: str
    horizon_kind: HorizonKind
    source_tag: str
    tmin_by_date: Mapping[dt.date, float | Missing]
    tmax_by_date: Mapping[dt.date, float | Missing]
    years: Sequence[int] | None = None
    phenology_evaluator: PhenologyEvaluator | None = None
    transpiration_ratio_by_date: Mapping[dt.date, float | Missing] | None = None
    transpiration_by_date: Mapping[dt.date, float | Missing] | None = None
    transpiration_demanded_by_date: Mapping[dt.date, float | Missing] | None = None
    critical_water_evaluator: CriticalWaterEvaluator | None = None
    series_missing: Missing | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str("horizon_id", self.horizon_id)
        if not isinstance(self.horizon_kind, str):
            raise TypeError(
                f"horizon_kind: expected str, got {type(self.horizon_kind).__name__} (G5)"
            )
        if self.horizon_kind not in HORIZON_KINDS:
            raise ValueError(
                f"horizon_kind: expected one of {HORIZON_KINDS}, got {self.horizon_kind!r}"
            )
        _require_non_empty_str("source_tag", self.source_tag)
        _check_date_mapping("tmin_by_date", self.tmin_by_date)
        _check_date_mapping("tmax_by_date", self.tmax_by_date)

        if self.years is not None:
            if isinstance(self.years, (str, bytes, bytearray)) or not isinstance(
                self.years, Sequence
            ):
                raise TypeError(
                    f"years: expected a Sequence of int, got {type(self.years).__name__} (G5)"
                )
            seen_years: set[int] = set()
            for year in self.years:
                if not _is_strict_int(year):
                    raise TypeError(
                        f"years elements must be int, got {type(year).__name__} (G5)"
                    )
                if year in seen_years:
                    raise ValueError(f"years contains duplicate year {year}")
                seen_years.add(year)

        if self.phenology_evaluator is not None and not callable(
            self.phenology_evaluator
        ):
            raise TypeError("phenology_evaluator must be callable (G5)")

        has_t = self.transpiration_by_date is not None
        has_td = self.transpiration_demanded_by_date is not None
        if has_t != has_td:
            raise ValueError(
                "transpiration_by_date and transpiration_demanded_by_date must be "
                "provided together"
            )
        modes = sum(
            (
                self.critical_water_evaluator is not None,
                self.transpiration_ratio_by_date is not None,
                has_t and has_td,
            )
        )
        if modes > 1:
            raise ValueError(
                "provide at most one water-stress input mode per ClimateHorizon: "
                "critical_water_evaluator, transpiration_ratio_by_date, or "
                "(transpiration_by_date + transpiration_demanded_by_date)"
            )
        if self.critical_water_evaluator is not None and not callable(
            self.critical_water_evaluator
        ):
            raise TypeError("critical_water_evaluator must be callable (G5)")
        if self.transpiration_ratio_by_date is not None:
            _check_date_mapping(
                "transpiration_ratio_by_date", self.transpiration_ratio_by_date
            )
        if self.transpiration_by_date is not None:
            _check_date_mapping("transpiration_by_date", self.transpiration_by_date)
        if self.transpiration_demanded_by_date is not None:
            _check_date_mapping(
                "transpiration_demanded_by_date", self.transpiration_demanded_by_date
            )
        if self.series_missing is not None and not isinstance(
            self.series_missing, Missing
        ):
            raise TypeError(
                "series_missing: expected contracts.results.models.Missing or None (G5)"
            )

    def candidate_years(self) -> tuple[int, ...]:
        """Sorted years to evaluate for this horizon."""
        if self.years is not None:
            return tuple(sorted(self.years))
        inferred = {day.year for day in self.tmin_by_date} | {
            day.year for day in self.tmax_by_date
        }
        return tuple(sorted(inferred))


@dataclass(frozen=True)
class RiskCount:
    """Count ``k of n`` evaluated years experiencing a given hazard.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    When ``evaluated_years == 0``, ``events_count`` and ``rate`` are typed
    ``Missing`` (never ``0`` or ``0.0``).
    """

    events_count: int | Missing
    evaluated_years: int
    rate: float | Missing
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "RiskCount",
        )


@dataclass(frozen=True)
class UnevaluatedCandidateYear:
    """A candidate sowing date-year withheld due to missing or invalid inputs.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    year: int
    sowing_date: dt.date
    missing: Missing
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "UnevaluatedCandidateYear",
        )


@dataclass(frozen=True)
class EvaluatedCandidateYear:
    """Complete risk and calendar outcome for one evaluated candidate date-year.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    ``bare_soil_fallow_days`` counts calendar days strictly between
    ``harvest_date`` and ``next_sowing_date`` (both crop days are inclusive, so
    a next-day or same-day sowing gives ``0`` and an overlap gives
    ``Missing(reason="NOT_COMPUTABLE")``).
    """

    year: int
    sowing_date: dt.date
    leap_day_adjusted: bool
    flowering_date: dt.date
    flowering_window_start: dt.date
    flowering_window_end: dt.date
    maturity_date: dt.date
    harvest_date: dt.date
    successor_entry_earliest_date: dt.date
    next_sowing_date: dt.date
    bare_soil_fallow_days: int | Missing
    successor_window_feasible: bool
    flowering_frost: bool
    flowering_heat: bool
    critical_water_stress: bool
    window_min_tmin_c: float
    window_max_tmax_c: float
    max_consecutive_heat_days: int
    critical_transpiration_ratio: float
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "EvaluatedCandidateYear",
        )


@dataclass(frozen=True)
class CandidateSowingSummary:
    """Multi-year risk summary for one ``MM-DD`` candidate within one horizon.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    candidate_mm_dd: str
    horizon_id: str
    horizon_kind: HorizonKind
    source_tag: str
    evaluated_years: tuple[EvaluatedCandidateYear, ...]
    unevaluated_years: tuple[UnevaluatedCandidateYear, ...]
    flowering_frost_risk: RiskCount
    flowering_heat_risk: RiskCount
    critical_water_stress_risk: RiskCount
    earliest_maturity_date: dt.date | Missing
    latest_maturity_date: dt.date | Missing
    earliest_successor_entry_date: dt.date | Missing
    latest_successor_entry_date: dt.date | Missing
    mean_bare_soil_fallow_days: float | Missing
    min_bare_soil_fallow_days: int | Missing
    max_bare_soil_fallow_days: int | Missing
    successor_conflict_years: tuple[int, ...]
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "CandidateSowingSummary",
        )


@dataclass(frozen=True)
class HorizonSweepResult:
    """Risk sweep results for one climate horizon (never pooled across horizons).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    horizon_id: str
    horizon_kind: HorizonKind
    source_tag: str
    candidates: tuple[CandidateSowingSummary, ...]
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "HorizonSweepResult",
        )

    def get_candidate(self, candidate_mm_dd: str) -> CandidateSowingSummary:
        """Return the summary for ``candidate_mm_dd`` or raise ``KeyError``."""
        for item in self.candidates:
            if item.candidate_mm_dd == candidate_mm_dd:
                return item
        raise KeyError(
            f"candidate {candidate_mm_dd!r} not found in horizon {self.horizon_id!r}"
        )


@dataclass(frozen=True)
class SowingWindowSweepResult:
    """Top-level multi-horizon sowing-window sweep output.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    horizons: tuple[HorizonSweepResult, ...]
    horizons_pooled: bool = False
    orientation_only: bool = True
    replaces_agronomist_recommendation: bool = False

    def __post_init__(self) -> None:
        if self.horizons_pooled is not False:
            raise ValueError(
                "SowingWindowSweepResult: horizons_pooled must always be False "
                "(historical, synthetic, and future datasets never average together)"
            )
        _require_orientation_tags(
            self.orientation_only,
            self.replaces_agronomist_recommendation,
            "SowingWindowSweepResult",
        )

    @property
    def horizon_keys(self) -> tuple[tuple[str, HorizonKind, str], ...]:
        """Tuple of ``(horizon_id, horizon_kind, source_tag)`` across separated horizons."""
        return tuple(
            (h.horizon_id, h.horizon_kind, h.source_tag) for h in self.horizons
        )

    def get_horizon(self, horizon_id: str) -> HorizonSweepResult:
        """Return the separated result for ``horizon_id`` or raise ``KeyError``."""
        for item in self.horizons:
            if item.horizon_id == horizon_id:
                return item
        raise KeyError(f"horizon {horizon_id!r} not found")

    def horizons_of_kind(
        self, horizon_kind: HorizonKind
    ) -> tuple[HorizonSweepResult, ...]:
        """Return separated horizons matching ``horizon_kind`` without pooling."""
        if horizon_kind not in HORIZON_KINDS:
            raise ValueError(
                f"horizon_kind: expected one of {HORIZON_KINDS}, got {horizon_kind!r}"
            )
        return tuple(h for h in self.horizons if h.horizon_kind == horizon_kind)


def _extract_temperature_series(
    by_quantity: dict[str, DailySeries],
    quantity: str,
) -> tuple[dict[dt.date, float | Missing], DailySeries | None, Missing | None]:
    series = by_quantity.get(quantity)
    if series is None:
        return (
            {},
            None,
            Missing(
                reason="MISSING_INPUT",
                detail=f"the climate record has no daily series '{quantity}'",
            ),
        )
    if series.unit != ACCEPTED_TEMPERATURE_UNIT:
        return (
            {},
            series,
            Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"the daily series '{quantity}' is in unit '{series.unit}', "
                    f"not in accepted unit '{ACCEPTED_TEMPERATURE_UNIT}' (C1.1)"
                ),
            ),
        )
    values: dict[dt.date, float | Missing] = {}
    for day in series.days:
        if day.missing is not None:
            values[day.date] = Missing(
                reason=day.missing.reason,
                detail=day.missing.detail,
            )
        else:
            assert day.value is not None
            values[day.date] = float(day.value)
    return values, series, None


def horizon_from_site_climate(
    climate: SiteClimate,
    *,
    horizon_id: str,
    horizon_kind: HorizonKind,
    source_tag: str,
    years: Sequence[int] | None = None,
    phenology_evaluator: PhenologyEvaluator | None = None,
    transpiration_ratio_by_date: Mapping[dt.date, float | Missing] | None = None,
    transpiration_by_date: Mapping[dt.date, float | Missing] | None = None,
    transpiration_demanded_by_date: Mapping[dt.date, float | Missing] | None = None,
    critical_water_evaluator: CriticalWaterEvaluator | None = None,
) -> ClimateHorizon:
    """Build a ``ClimateHorizon`` from a ``SiteClimate`` contract model.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Checks exact unit strings (``"degC"``, C1.1) and matching ``time_zone``
    (C6.3) for ``air_temperature_min_2m`` and ``air_temperature_max_2m``.
    Any missing/wrong-unit series or mixed time zone is preserved on
    ``series_missing`` rather than guessed or converted.
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in (TEMPERATURE_MIN_QUANTITY, TEMPERATURE_MAX_QUANTITY)
    }
    tmin_map, min_series, min_missing = _extract_temperature_series(
        by_quantity, TEMPERATURE_MIN_QUANTITY
    )
    tmax_map, max_series, max_missing = _extract_temperature_series(
        by_quantity, TEMPERATURE_MAX_QUANTITY
    )

    series_missing: Missing | None = min_missing or max_missing
    if (
        series_missing is None
        and min_series is not None
        and max_series is not None
        and min_series.time_zone != max_series.time_zone
    ):
        series_missing = Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"daily series '{TEMPERATURE_MIN_QUANTITY}' ({min_series.time_zone}) "
                f"and '{TEMPERATURE_MAX_QUANTITY}' ({max_series.time_zone}) "
                "have different time zones (C6.3)"
            ),
        )

    return ClimateHorizon(
        horizon_id=horizon_id,
        horizon_kind=horizon_kind,
        source_tag=source_tag,
        tmin_by_date=tmin_map,
        tmax_by_date=tmax_map,
        years=years,
        phenology_evaluator=phenology_evaluator,
        transpiration_ratio_by_date=transpiration_ratio_by_date,
        transpiration_by_date=transpiration_by_date,
        transpiration_demanded_by_date=transpiration_demanded_by_date,
        critical_water_evaluator=critical_water_evaluator,
        series_missing=series_missing,
    )


def _date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    span_days = (end - start).days + 1
    return [start + dt.timedelta(days=offset) for offset in range(span_days)]


def _read_daily_series_window(
    series_name: str,
    mapping: Mapping[dt.date, float | Missing],
    days: Sequence[dt.date],
) -> list[float] | Missing:
    values: list[float] = []
    for day in days:
        if day not in mapping:
            return Missing(
                reason="NO_COVERAGE",
                detail=(
                    f"'{series_name}' has no entry on {day.isoformat()} "
                    f"within window {days[0].isoformat()}..{days[-1].isoformat()} (C5.5)"
                ),
            )
        raw = mapping[day]
        if isinstance(raw, Missing):
            detail = raw.detail if raw.detail is not None else raw.reason
            return Missing(
                reason=raw.reason,
                detail=f"'{series_name}' missing on {day.isoformat()}: {detail}",
            )
        if not _is_strict_number(raw):
            raise TypeError(
                f"'{series_name}' on {day.isoformat()}: expected number or Missing, "
                f"got {type(raw).__name__} (G5)"
            )
        if not _is_finite_number(raw):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"'{series_name}' has non-finite value on {day.isoformat()}",
            )
        values.append(float(raw))
    return values


def _evaluate_critical_water_ratio(
    horizon: ClimateHorizon,
    crit_start: dt.date,
    crit_end: dt.date,
) -> float | Missing:
    if horizon.critical_water_evaluator is not None:
        ratio = horizon.critical_water_evaluator(crit_start, crit_end)
        if isinstance(ratio, Missing):
            return ratio
        if not _is_strict_number(ratio):
            raise TypeError(
                "critical_water_evaluator must return float, int, or Missing, "
                f"got {type(ratio).__name__} (G5)"
            )
        if not _is_finite_number(ratio):
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"critical_water_evaluator returned non-finite ratio for "
                    f"{crit_start.isoformat()}..{crit_end.isoformat()}"
                ),
            )
        return float(ratio)

    crit_days = _date_range(crit_start, crit_end)

    if horizon.transpiration_ratio_by_date is not None:
        ratios = _read_daily_series_window(
            "transpiration_ratio",
            horizon.transpiration_ratio_by_date,
            crit_days,
        )
        if isinstance(ratios, Missing):
            return ratios
        return sum(ratios) / len(ratios)

    if (
        horizon.transpiration_by_date is not None
        and horizon.transpiration_demanded_by_date is not None
    ):
        transp = _read_daily_series_window(
            "transpiration",
            horizon.transpiration_by_date,
            crit_days,
        )
        if isinstance(transp, Missing):
            return transp
        demanded = _read_daily_series_window(
            "transpiration_demanded",
            horizon.transpiration_demanded_by_date,
            crit_days,
        )
        if isinstance(demanded, Missing):
            return demanded
        total_demanded = sum(demanded)
        if total_demanded <= 0.0:
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    "critical-period transpiration_demanded sum is not above zero "
                    f"for {crit_start.isoformat()}..{crit_end.isoformat()}"
                ),
            )
        return sum(transp) / total_demanded

    return Missing(
        reason="MISSING_INPUT",
        detail=(
            f"horizon '{horizon.horizon_id}' has no critical-period water data "
            "or evaluator (C3.3)"
        ),
    )


def _max_consecutive_exceedance(
    values: Sequence[float],
    threshold: float,
) -> int:
    streak = 0
    best = 0
    for val in values:
        if val > threshold:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _next_sowing_target(
    sowing_date: dt.date,
    candidate: CandidateSowingDate,
    config: RiskWindowConfig,
) -> dt.date:
    successor = config.successor_sowing_mm_dd
    if successor is None:
        next_date, _ = candidate.resolve_for_year(sowing_date.year + 1)
        return next_date
    assert isinstance(successor, CandidateSowingDate)
    same_year_target, _ = successor.resolve_for_year(sowing_date.year)
    if same_year_target > sowing_date:
        return same_year_target
    next_year_target, _ = successor.resolve_for_year(sowing_date.year + 1)
    return next_year_target


def _evaluate_candidate_year(
    *,
    year: int,
    candidate: CandidateSowingDate,
    horizon: ClimateHorizon,
    config: RiskWindowConfig,
    evaluator: PhenologyEvaluator,
) -> EvaluatedCandidateYear | UnevaluatedCandidateYear:
    sowing_date, leap_adjusted = candidate.resolve_for_year(year)

    if horizon.series_missing is not None:
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=horizon.series_missing,
        )

    outcome = evaluator(sowing_date)
    if isinstance(outcome, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=outcome,
        )
    if not isinstance(outcome, PhenologyOutcome):
        raise TypeError(
            "phenology_evaluator must return PhenologyOutcome or Missing, "
            f"got {type(outcome).__name__} (G5)"
        )
    if outcome.sowing_date != sowing_date:
        raise ValueError(
            f"phenology_evaluator returned outcome for {outcome.sowing_date.isoformat()}, "
            f"expected {sowing_date.isoformat()}"
        )

    if isinstance(outcome.flowering_date, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=outcome.flowering_date,
        )
    if isinstance(outcome.maturity_date, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=outcome.maturity_date,
        )
    if isinstance(outcome.harvest_date, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=outcome.harvest_date,
        )

    flowering_date = outcome.flowering_date
    maturity_date = outcome.maturity_date
    harvest_date = (
        outcome.harvest_date
        if outcome.harvest_date is not None
        else maturity_date + dt.timedelta(days=config.harvest_lag_days)
    )

    if flowering_date < sowing_date:
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"flowering_date {flowering_date.isoformat()} precedes "
                    f"sowing_date {sowing_date.isoformat()}"
                ),
            ),
        )
    if maturity_date < flowering_date:
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"maturity_date {maturity_date.isoformat()} precedes "
                    f"flowering_date {flowering_date.isoformat()}"
                ),
            ),
        )
    if harvest_date < maturity_date:
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"harvest_date {harvest_date.isoformat()} precedes "
                    f"maturity_date {maturity_date.isoformat()}"
                ),
            ),
        )

    win_start = flowering_date - dt.timedelta(days=config.pre_days)
    win_end = flowering_date + dt.timedelta(days=config.post_days)
    win_days = _date_range(win_start, win_end)

    tmin_values = _read_daily_series_window(
        TEMPERATURE_MIN_QUANTITY, horizon.tmin_by_date, win_days
    )
    if isinstance(tmin_values, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=tmin_values,
        )

    tmax_values = _read_daily_series_window(
        TEMPERATURE_MAX_QUANTITY, horizon.tmax_by_date, win_days
    )
    if isinstance(tmax_values, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=tmax_values,
        )

    crit_start = flowering_date - dt.timedelta(days=config.effective_critical_pre_days)
    crit_end = flowering_date + dt.timedelta(days=config.effective_critical_post_days)
    crit_ratio = _evaluate_critical_water_ratio(horizon, crit_start, crit_end)
    if isinstance(crit_ratio, Missing):
        return UnevaluatedCandidateYear(
            year=year,
            sowing_date=sowing_date,
            missing=crit_ratio,
        )

    min_tmin = min(tmin_values)
    max_tmax = max(tmax_values)
    max_heat_streak = _max_consecutive_exceedance(tmax_values, config.heat_threshold_c)

    frost_event = min_tmin < config.frost_threshold_c
    heat_event = max_heat_streak >= config.min_heat_consecutive_days
    water_event = crit_ratio < config.water_ratio_threshold

    successor_earliest = harvest_date + dt.timedelta(
        days=config.successor_turnaround_days
    )
    next_sowing = _next_sowing_target(sowing_date, candidate, config)
    if next_sowing < harvest_date:
        fallow_days: int | Missing = Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"next sowing {next_sowing.isoformat()} precedes harvest "
                f"{harvest_date.isoformat()}"
            ),
        )
        successor_feasible = False
    else:
        # Both harvest_date and next_sowing_date are inclusive crop days; bare-soil
        # fallow consists of the calendar days strictly between them.
        fallow_days = max(0, (next_sowing - harvest_date).days - 1)
        successor_feasible = next_sowing >= successor_earliest

    return EvaluatedCandidateYear(
        year=year,
        sowing_date=sowing_date,
        leap_day_adjusted=leap_adjusted,
        flowering_date=flowering_date,
        flowering_window_start=win_start,
        flowering_window_end=win_end,
        maturity_date=maturity_date,
        harvest_date=harvest_date,
        successor_entry_earliest_date=successor_earliest,
        next_sowing_date=next_sowing,
        bare_soil_fallow_days=fallow_days,
        successor_window_feasible=successor_feasible,
        flowering_frost=frost_event,
        flowering_heat=heat_event,
        critical_water_stress=water_event,
        window_min_tmin_c=min_tmin,
        window_max_tmax_c=max_tmax,
        max_consecutive_heat_days=max_heat_streak,
        critical_transpiration_ratio=crit_ratio,
    )


def _no_evaluated_years_missing(
    horizon: ClimateHorizon,
    unevaluated: Sequence[UnevaluatedCandidateYear],
) -> Missing:
    if horizon.series_missing is not None:
        return horizon.series_missing
    if unevaluated:
        first = unevaluated[0].missing
        first_detail = f": {first.detail}" if first.detail else ""
        return Missing(
            reason=first.reason,
            detail=(
                f"no evaluated years for horizon '{horizon.horizon_id}': "
                f"all {len(unevaluated)} year(s) unevaluated, first in {unevaluated[0].year} "
                f"({first.reason}{first_detail})"
            ),
        )
    return Missing(
        reason="NO_COVERAGE",
        detail=f"horizon '{horizon.horizon_id}' contains no years to evaluate (C5.5)",
    )


def _build_risk_count(
    events: int,
    evaluated_count: int,
    empty_missing: Missing | None,
) -> RiskCount:
    if evaluated_count == 0:
        assert empty_missing is not None
        return RiskCount(
            events_count=empty_missing,
            evaluated_years=0,
            rate=empty_missing,
        )
    return RiskCount(
        events_count=events,
        evaluated_years=evaluated_count,
        rate=events / evaluated_count,
    )


def _summarize_candidate_in_horizon(
    *,
    candidate: CandidateSowingDate,
    horizon: ClimateHorizon,
    config: RiskWindowConfig,
    evaluator: PhenologyEvaluator,
) -> CandidateSowingSummary:
    evaluated: list[EvaluatedCandidateYear] = []
    unevaluated: list[UnevaluatedCandidateYear] = []

    for year in horizon.candidate_years():
        outcome = _evaluate_candidate_year(
            year=year,
            candidate=candidate,
            horizon=horizon,
            config=config,
            evaluator=evaluator,
        )
        if isinstance(outcome, UnevaluatedCandidateYear):
            unevaluated.append(outcome)
        else:
            evaluated.append(outcome)

    n = len(evaluated)
    empty_missing = (
        _no_evaluated_years_missing(horizon, unevaluated) if n == 0 else None
    )

    frost_risk = _build_risk_count(
        sum(1 for item in evaluated if item.flowering_frost),
        n,
        empty_missing,
    )
    heat_risk = _build_risk_count(
        sum(1 for item in evaluated if item.flowering_heat),
        n,
        empty_missing,
    )
    water_risk = _build_risk_count(
        sum(1 for item in evaluated if item.critical_water_stress),
        n,
        empty_missing,
    )

    if n == 0:
        assert empty_missing is not None
        earliest_mat: dt.date | Missing = empty_missing
        latest_mat: dt.date | Missing = empty_missing
        earliest_succ: dt.date | Missing = empty_missing
        latest_succ: dt.date | Missing = empty_missing
        mean_fallow: float | Missing = empty_missing
        min_fallow: int | Missing = empty_missing
        max_fallow: int | Missing = empty_missing
    else:
        earliest_mat = min(item.maturity_date for item in evaluated)
        latest_mat = max(item.maturity_date for item in evaluated)
        earliest_succ = min(item.successor_entry_earliest_date for item in evaluated)
        latest_succ = max(item.successor_entry_earliest_date for item in evaluated)

        missing_fallow = next(
            (
                item.bare_soil_fallow_days
                for item in evaluated
                if isinstance(item.bare_soil_fallow_days, Missing)
            ),
            None,
        )
        if missing_fallow is not None:
            mean_fallow = missing_fallow
            min_fallow = missing_fallow
            max_fallow = missing_fallow
        else:
            fallow_vals = [
                item.bare_soil_fallow_days
                for item in evaluated
                if isinstance(item.bare_soil_fallow_days, int)
            ]
            mean_fallow = sum(fallow_vals) / len(fallow_vals)
            min_fallow = min(fallow_vals)
            max_fallow = max(fallow_vals)

    conflicts = tuple(
        item.year for item in evaluated if not item.successor_window_feasible
    )

    return CandidateSowingSummary(
        candidate_mm_dd=candidate.mm_dd,
        horizon_id=horizon.horizon_id,
        horizon_kind=horizon.horizon_kind,
        source_tag=horizon.source_tag,
        evaluated_years=tuple(evaluated),
        unevaluated_years=tuple(unevaluated),
        flowering_frost_risk=frost_risk,
        flowering_heat_risk=heat_risk,
        critical_water_stress_risk=water_risk,
        earliest_maturity_date=earliest_mat,
        latest_maturity_date=latest_mat,
        earliest_successor_entry_date=earliest_succ,
        latest_successor_entry_date=latest_succ,
        mean_bare_soil_fallow_days=mean_fallow,
        min_bare_soil_fallow_days=min_fallow,
        max_bare_soil_fallow_days=max_fallow,
        successor_conflict_years=conflicts,
    )


def _resolve_phenology_evaluator(
    horizon: ClimateHorizon,
    phenology_evaluator: PhenologyEvaluator | Mapping[str, PhenologyEvaluator] | None,
) -> PhenologyEvaluator:
    if horizon.phenology_evaluator is not None:
        return horizon.phenology_evaluator
    if isinstance(phenology_evaluator, Mapping):
        found = phenology_evaluator.get(horizon.horizon_id)
        if found is None:
            raise ValueError(
                f"no phenology_evaluator provided for horizon {horizon.horizon_id!r}"
            )
        if not callable(found):
            raise TypeError(
                f"phenology_evaluator[{horizon.horizon_id!r}] must be callable (G5)"
            )
        return found
    if phenology_evaluator is not None:
        if not callable(phenology_evaluator):
            raise TypeError(
                "phenology_evaluator: expected PhenologyEvaluator callable or Mapping, "
                f"got {type(phenology_evaluator).__name__} (G5)"
            )
        return phenology_evaluator
    raise ValueError(
        f"no phenology_evaluator provided for horizon {horizon.horizon_id!r}"
    )


def sweep_sowing_windows(
    candidate_sowing_dates: Sequence[CandidateSowingDate | str],
    horizons: Sequence[ClimateHorizon],
    config: RiskWindowConfig,
    *,
    phenology_evaluator: PhenologyEvaluator
    | Mapping[str, PhenologyEvaluator]
    | None = None,
) -> SowingWindowSweepResult:
    """Run multi-year candidate sowing-date risk sweep across separated horizons.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Raises ``TypeError`` for wrong argument types (G5) and ``ValueError`` for
    invalid ``MM-DD`` strings, duplicate candidate sowing dates, duplicate
    ``horizon_id`` values, or missing ``phenology_evaluator``.
    """
    if isinstance(candidate_sowing_dates, (str, bytes, bytearray)) or not isinstance(
        candidate_sowing_dates, Sequence
    ):
        raise TypeError(
            "candidate_sowing_dates: expected Sequence of CandidateSowingDate or str, "
            f"got {type(candidate_sowing_dates).__name__} (G5)"
        )
    if isinstance(horizons, (str, bytes, bytearray)) or not isinstance(
        horizons, Sequence
    ):
        raise TypeError(
            "horizons: expected Sequence of ClimateHorizon, "
            f"got {type(horizons).__name__} (G5)"
        )
    if not isinstance(config, RiskWindowConfig):
        raise TypeError(
            f"config: expected RiskWindowConfig, got {type(config).__name__} (G5)"
        )
    if (
        phenology_evaluator is not None
        and not isinstance(phenology_evaluator, Mapping)
        and not callable(phenology_evaluator)
    ):
        raise TypeError(
            "phenology_evaluator: expected PhenologyEvaluator callable, Mapping, or None, "
            f"got {type(phenology_evaluator).__name__} (G5)"
        )

    parsed_candidates: list[CandidateSowingDate] = []
    seen_mm_dd: set[str] = set()
    for raw_candidate in candidate_sowing_dates:
        cand = CandidateSowingDate.parse(raw_candidate)
        if cand.mm_dd in seen_mm_dd:
            raise ValueError(
                f"candidate_sowing_dates contains duplicate date {cand.mm_dd!r}"
            )
        seen_mm_dd.add(cand.mm_dd)
        parsed_candidates.append(cand)

    seen_horizon_ids: set[str] = set()
    resolved_horizons: list[tuple[ClimateHorizon, PhenologyEvaluator]] = []
    for horizon in horizons:
        if not isinstance(horizon, ClimateHorizon):
            raise TypeError(
                f"horizons elements must be ClimateHorizon, got {type(horizon).__name__} (G5)"
            )
        if horizon.horizon_id in seen_horizon_ids:
            raise ValueError(
                f"horizons contains duplicate horizon_id {horizon.horizon_id!r}"
            )
        seen_horizon_ids.add(horizon.horizon_id)
        evaluator = _resolve_phenology_evaluator(horizon, phenology_evaluator)
        resolved_horizons.append((horizon, evaluator))

    horizon_results: list[HorizonSweepResult] = []
    for horizon, evaluator in resolved_horizons:
        summaries = tuple(
            _summarize_candidate_in_horizon(
                candidate=cand,
                horizon=horizon,
                config=config,
                evaluator=evaluator,
            )
            for cand in parsed_candidates
        )
        horizon_results.append(
            HorizonSweepResult(
                horizon_id=horizon.horizon_id,
                horizon_kind=horizon.horizon_kind,
                source_tag=horizon.source_tag,
                candidates=summaries,
            )
        )

    return SowingWindowSweepResult(horizons=tuple(horizon_results))
