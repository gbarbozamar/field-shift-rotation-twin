"""Monthly-conditioned two-state Markov synthetic weather generator (Frontier Unit F-08).

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Standalone module under ``engine/water/``; not wired into ``engine/water/__init__.py``,
EP3, or the API runner until approved.

Scientific & Rev13 Specification
--------------------------------
- **Zero hardcoded climate parameters (Blueprint §3.5):** every calibration and
  simulation parameter arrives via ``SyntheticWeatherConfig``
  (``wet_day_threshold_mm``, ``min_history_years``, ``n_synthetic_years``,
  ``seed``, ``ag_year_start_month``). No climate threshold, transition rate,
  or reference value is hardcoded in this module.
- **Monthly two-state Markov wet/dry chain:** for each calendar month ``1..12``,
  observed daily precipitation is classified as wet (``precip_mm >=
  wet_day_threshold_mm``) or dry (``precip_mm < wet_day_threshold_mm``).
  Consecutive valid observed day pairs ``(t - 1, t)`` within the same calendar
  month yield empirical transition probabilities ``P(W|W)`` and ``P(W|D)``,
  along with unconditional wet probability ``P(W)``.
- **Conditional empirical multi-variable resampling:** each simulated day
  preserves the joint multi-variable weather vector
  ``(precip_mm, tmax_c, tmin_c, radiation, wind, rh)`` by drawing uniformly with
  ``random.Random(seed)`` from the historical pool matching ``(month, state)``.
- **Rev13 Guard 1 (no zero-filling & clean coverage failure):** missing or
  non-finite historical days are NEVER filled as zero before fitting, never
  enter wet/dry resampling pools, and break consecutive transition pairs. Any
  calendar month with fewer than ``min_history_years`` complete valid
  historical calendar-month years fails cleanly with
  ``Missing(reason="MISSING_INPUT")`` or ``Missing(reason="NO_COVERAGE")``.
- **Rev13 Guard 2 (strict synthetic segregation):** every generated
  ``SyntheticWeatherSeries`` carries ``provenance="SIMULATED"``,
  ``horizon="synthetic"``, and ``can_replace_observed=False``. The normative
  guard helper ``require_observed_for_normative`` refuses mixing synthetic or
  non-``OBSERVED`` records into ``OBSERVED`` normative calculations
  (``ValueError``).

Pure Python 3.12 stdlib + ``contracts.*`` (zero numpy). Pure function (G1):
no file I/O, no network calls, no wall clock, no environment variables, no
global mutable state, and caller arguments are never mutated.
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.site_climate import DailySeries, MonthlySeries, SiteClimate
from contracts.results.models import Missing

__all__ = [
    "ACCEPTED_CLIMATE_UNITS",
    "PRECIPITATION",
    "RELATIVE_HUMIDITY_2M",
    "SOLAR_RADIATION",
    "SYNTHETIC_CAN_REPLACE_OBSERVED",
    "SYNTHETIC_HORIZON",
    "SYNTHETIC_PROVENANCE",
    "TEMPERATURE_MAX",
    "TEMPERATURE_MIN",
    "WIND_SPEED_2M",
    "AnnualPrecipDistribution",
    "DailyWeatherVector",
    "MonthlyMarkovParameters",
    "SyntheticWeatherConfig",
    "SyntheticWeatherDiagnostics",
    "SyntheticWeatherSeries",
    "daily_vectors_from_site_climate",
    "fit_monthly_markov_parameters",
    "generate_synthetic_weather",
    "require_observed_for_normative",
]

_MONTHS_IN_YEAR = len(calendar.month_name[1:])
_ZERO = 0
_ONE = 1
_ZERO_F = 0.0
_ONE_F = 1.0

OBSERVED_PROVENANCE = "OBSERVED"
SYNTHETIC_PROVENANCE: Literal["SIMULATED"] = "SIMULATED"
SYNTHETIC_HORIZON: Literal["synthetic"] = "synthetic"
SYNTHETIC_CAN_REPLACE_OBSERVED: Literal[False] = False

PRECIPITATION = "precipitation"
TEMPERATURE_MAX = "air_temperature_max_2m"
TEMPERATURE_MIN = "air_temperature_min_2m"
SOLAR_RADIATION = "solar_radiation"
WIND_SPEED_2M = "wind_speed_2m"
RELATIVE_HUMIDITY_2M = "relative_humidity_2m"

ACCEPTED_CLIMATE_UNITS: dict[str, str] = {
    PRECIPITATION: "mm day-1",
    TEMPERATURE_MAX: "degC",
    TEMPERATURE_MIN: "degC",
    SOLAR_RADIATION: "MJ m-2 day-1",
    WIND_SPEED_2M: "m s-1",
    RELATIVE_HUMIDITY_2M: "%",
}

_VECTOR_FIELD_TO_QUANTITY: tuple[tuple[str, str], ...] = (
    ("precip_mm", PRECIPITATION),
    ("tmax_c", TEMPERATURE_MAX),
    ("tmin_c", TEMPERATURE_MIN),
    ("radiation", SOLAR_RADIATION),
    ("wind", WIND_SPEED_2M),
    ("rh", RELATIVE_HUMIDITY_2M),
)


def _is_strict_int(value: object) -> bool:
    """True for an ``int`` excluding ``bool`` (G5)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    """True for ``int`` or ``float`` excluding ``bool`` (G5)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _to_results_missing(value: Missing | InputsMissing) -> Missing:
    """Normalize contract Missing variants to ``contracts.results.models.Missing``."""
    if isinstance(value, Missing):
        return value
    return Missing(reason=value.reason, detail=value.detail)


def _validate_vector_value(
    name: str, date_val: dt.date, value: object
) -> float | Missing:
    """Validate one daily weather variable (G5) without coercing missing to zero."""
    if isinstance(value, (Missing, InputsMissing)):
        return _to_results_missing(value)
    if not _is_number(value):
        raise TypeError(
            f"{name} on {date_val.isoformat()}: expected float, int, or Missing, "
            f"got {type(value).__name__} (G5)"
        )
    assert isinstance(value, (int, float))
    if not _is_finite(value):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{name} on {date_val.isoformat()} is not a finite number",
        )
    return float(value)


@dataclass(frozen=True)
class SyntheticWeatherConfig:
    """Caller-supplied calibration and simulation settings (zero hardcoded defaults).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    wet_day_threshold_mm: float
    min_history_years: int
    n_synthetic_years: int
    seed: int
    ag_year_start_month: int

    def __post_init__(self) -> None:
        if not _is_number(self.wet_day_threshold_mm):
            raise TypeError(
                "wet_day_threshold_mm: expected float or int, "
                f"got {type(self.wet_day_threshold_mm).__name__} (G5)"
            )
        if (
            not _is_finite(self.wet_day_threshold_mm)
            or self.wet_day_threshold_mm <= _ZERO_F
        ):
            raise ValueError(
                "wet_day_threshold_mm must be a finite positive number (> 0)"
            )
        object.__setattr__(
            self, "wet_day_threshold_mm", float(self.wet_day_threshold_mm)
        )

        for field_name in ("min_history_years", "n_synthetic_years", "seed"):
            val = getattr(self, field_name)
            if not _is_strict_int(val):
                raise TypeError(
                    f"{field_name}: expected int, got {type(val).__name__} (G5)"
                )
        if self.min_history_years < _ONE:
            raise ValueError("min_history_years must be >= 1")
        if self.n_synthetic_years < _ONE:
            raise ValueError("n_synthetic_years must be >= 1")

        if not _is_strict_int(self.ag_year_start_month):
            raise TypeError(
                "ag_year_start_month: expected int, "
                f"got {type(self.ag_year_start_month).__name__} (G5)"
            )
        if not (_ONE <= self.ag_year_start_month <= _MONTHS_IN_YEAR):
            raise ValueError(
                f"ag_year_start_month: expected 1..{_MONTHS_IN_YEAR}, "
                f"got {self.ag_year_start_month} (C5.1)"
            )


@dataclass(frozen=True)
class DailyWeatherVector:
    """Multi-variable daily weather vector for historical input or synthetic output.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    date: dt.date
    precip_mm: float | Missing
    tmax_c: float | Missing
    tmin_c: float | Missing
    radiation: float | Missing
    wind: float | Missing
    rh: float | Missing

    def __post_init__(self) -> None:
        if isinstance(self.date, dt.datetime) or not isinstance(self.date, dt.date):
            raise TypeError(
                f"date: expected datetime.date, got {type(self.date).__name__} (G5)"
            )
        for field_name, _ in _VECTOR_FIELD_TO_QUANTITY:
            validated = _validate_vector_value(
                field_name, self.date, getattr(self, field_name)
            )
            object.__setattr__(self, field_name, validated)


@dataclass(frozen=True)
class MonthlyMarkovParameters:
    """Fitted two-state wet/dry Markov parameters for one calendar month.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    month: int
    p_wet_given_wet: float | Missing
    p_wet_given_dry: float | Missing
    p_wet_unconditional: float | Missing
    wet_pool_size: int
    dry_pool_size: int
    valid_years_observed: int
    valid_day_count: int
    ww_transitions: int
    wd_transitions: int
    dw_transitions: int
    dd_transitions: int
    coverage_missing: Missing | None = None


@dataclass(frozen=True)
class AnnualPrecipDistribution:
    """Distribution summary of synthetic annual precipitation totals (mm yr-1).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    annual_totals_mm: tuple[float, ...]
    mean_mm: float
    std_mm: float
    min_mm: float
    median_mm: float
    max_mm: float


@dataclass(frozen=True)
class SyntheticWeatherDiagnostics:
    """Summary diagnostics of a generated synthetic daily weather series.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    wet_spell_count: int
    wet_day_count: int
    dry_day_count: int
    annual_precip_distribution: AnnualPrecipDistribution


@dataclass(frozen=True)
class SyntheticWeatherSeries:
    """Output of the synthetic weather generator with strict Rev13 provenance guards.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    config: SyntheticWeatherConfig
    monthly_parameters: tuple[MonthlyMarkovParameters, ...]
    days: tuple[DailyWeatherVector, ...] | Missing
    diagnostics: SyntheticWeatherDiagnostics | Missing
    provenance: Literal["SIMULATED"] = SYNTHETIC_PROVENANCE
    horizon: Literal["synthetic"] = SYNTHETIC_HORIZON
    can_replace_observed: Literal[False] = SYNTHETIC_CAN_REPLACE_OBSERVED

    def __post_init__(self) -> None:
        if self.provenance != SYNTHETIC_PROVENANCE:
            raise ValueError(
                f"SyntheticWeatherSeries requires provenance={SYNTHETIC_PROVENANCE!r}"
            )
        if self.horizon != SYNTHETIC_HORIZON:
            raise ValueError(
                f"SyntheticWeatherSeries requires horizon={SYNTHETIC_HORIZON!r}"
            )
        if self.can_replace_observed is not False:
            raise ValueError(
                "SyntheticWeatherSeries requires can_replace_observed=False"
            )


def _check_series_for_synthetic(series: DailySeries | MonthlySeries) -> None:
    if series.provenance == SYNTHETIC_PROVENANCE:
        raise ValueError(
            f"series {series.quantity!r} carries provenance='SIMULATED' "
            "and cannot be mixed into OBSERVED normative calculations"
        )
    if series.provenance is not None and series.provenance != OBSERVED_PROVENANCE:
        raise ValueError(
            f"series {series.quantity!r} carries provenance={series.provenance!r}, "
            f"expected {OBSERVED_PROVENANCE!r} for normative calculations"
        )


def _reject_synthetic_series() -> None:
    raise ValueError(
        "cannot mix SyntheticWeatherSeries (provenance='SIMULATED', "
        "horizon='synthetic', can_replace_observed=False) into OBSERVED "
        "normative calculations"
    )


def require_observed_for_normative(*records: object) -> None:
    """Refuse mixing synthetic or non-``OBSERVED`` records into normative calculations.

    Raises ``ValueError`` if any record is a ``SyntheticWeatherSeries``, carries
    ``provenance='SIMULATED'``, ``horizon='synthetic'``,
    ``can_replace_observed=False``, or is a ``SiteClimate`` / ``DailySeries`` /
    ``MonthlySeries`` with non-``OBSERVED`` provenance.
    Raises ``TypeError`` for unsupported argument types (G5).
    """
    for record in records:
        if isinstance(record, SyntheticWeatherSeries):
            _reject_synthetic_series()
            continue
        if isinstance(record, SiteClimate):
            for daily in record.daily_series:
                _check_series_for_synthetic(daily)
            for monthly in record.monthly_series:
                _check_series_for_synthetic(monthly)
            for point_val in (
                record.point.latitude,
                record.point.longitude,
                record.point.elevation,
            ):
                if point_val.provenance == SYNTHETIC_PROVENANCE:
                    raise ValueError(
                        "SiteClimate point carries provenance='SIMULATED' and "
                        "cannot be mixed into OBSERVED normative calculations"
                    )
            continue
        if isinstance(record, (DailySeries, MonthlySeries)):
            _check_series_for_synthetic(record)
            continue
        if isinstance(record, (list, tuple)):
            require_observed_for_normative(*record)
            continue
        if (
            hasattr(record, "provenance")
            or hasattr(record, "horizon")
            or hasattr(record, "can_replace_observed")
        ):
            prov = getattr(record, "provenance", None)
            horizon = getattr(record, "horizon", None)
            can_replace = getattr(record, "can_replace_observed", None)
            if (
                prov == SYNTHETIC_PROVENANCE
                or horizon == SYNTHETIC_HORIZON
                or can_replace is False
            ):
                raise ValueError(
                    "cannot mix synthetic record into OBSERVED normative calculations"
                )
            if prov is not None and prov != OBSERVED_PROVENANCE:
                raise ValueError(
                    f"record provenance {prov!r} is not {OBSERVED_PROVENANCE!r}"
                )
            continue
        raise TypeError(
            f"unsupported record type for normative provenance check: "
            f"{type(record).__name__} (G5)"
        )


def daily_vectors_from_site_climate(
    climate: SiteClimate,
) -> tuple[DailyWeatherVector, ...]:
    """Extract aligned daily weather vectors from a ``SiteClimate`` contract object.

    Raises ``TypeError`` if ``climate`` is not a ``SiteClimate`` (G5), and
    ``ValueError`` if any series in ``climate`` has ``provenance='SIMULATED'``
    (Rev13 Guard 2). Missing series, wrong units, out-of-coverage dates, or
    mixed time zones stay explicit ``Missing`` values and are never filled as
    zero (Rev13 Guard 1).
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    require_observed_for_normative(climate)

    target_quantities = {quantity for _, quantity in _VECTOR_FIELD_TO_QUANTITY}
    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in target_quantities
    }
    if not by_quantity:
        return ()

    time_zones = {series.time_zone for series in by_quantity.values()}
    mixed_tz_missing: Missing | None = None
    if len(time_zones) > _ONE:
        mixed_tz_missing = Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                "climate daily series use mixed time zones: "
                + ", ".join(sorted(time_zones))
            ),
        )

    day_maps: dict[str, dict[dt.date, float | Missing]] = {}
    all_dates: set[dt.date] = set()
    for quantity, series in by_quantity.items():
        accepted_unit = ACCEPTED_CLIMATE_UNITS[quantity]
        per_day: dict[dt.date, float | Missing] = {}
        for day in series.days:
            all_dates.add(day.date)
            if mixed_tz_missing is not None:
                per_day[day.date] = mixed_tz_missing
            elif series.unit != accepted_unit:
                per_day[day.date] = Missing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"daily series '{quantity}' is in unit '{series.unit}', "
                        f"not accepted unit '{accepted_unit}' (C1.1)"
                    ),
                )
            elif day.missing is not None:
                per_day[day.date] = _to_results_missing(day.missing)
            else:
                assert day.value is not None
                if not _is_finite(day.value):
                    per_day[day.date] = Missing(
                        reason="NOT_COMPUTABLE",
                        detail=f"non-finite value in '{quantity}' on {day.date.isoformat()}",
                    )
                else:
                    per_day[day.date] = float(day.value)
        day_maps[quantity] = per_day

    vectors: list[DailyWeatherVector] = []
    for day_date in sorted(all_dates):
        kwargs: dict[str, float | Missing] = {}
        for field_name, quantity in _VECTOR_FIELD_TO_QUANTITY:
            if mixed_tz_missing is not None:
                kwargs[field_name] = mixed_tz_missing
            elif quantity not in by_quantity:
                kwargs[field_name] = Missing(
                    reason="MISSING_INPUT",
                    detail=f"the climate record has no daily series '{quantity}'",
                )
            elif day_date not in day_maps[quantity]:
                kwargs[field_name] = Missing(
                    reason="NO_COVERAGE",
                    detail=(
                        f"daily series '{quantity}' does not cover "
                        f"{day_date.isoformat()} (C5.5)"
                    ),
                )
            else:
                kwargs[field_name] = day_maps[quantity][day_date]
        vectors.append(DailyWeatherVector(date=day_date, **kwargs))
    return tuple(vectors)


def _normalize_history(
    history: Sequence[DailyWeatherVector] | SiteClimate,
) -> tuple[DailyWeatherVector, ...]:
    """Validate and sort historical daily vectors without mutating caller inputs."""
    if isinstance(history, SiteClimate):
        return daily_vectors_from_site_climate(history)
    if isinstance(history, (str, bytes, bytearray)) or not isinstance(
        history, Sequence
    ):
        raise TypeError(
            "history: expected Sequence[DailyWeatherVector] or SiteClimate, "
            f"got {type(history).__name__} (G5)"
        )
    by_date: dict[dt.date, DailyWeatherVector] = {}
    for item in history:
        if not isinstance(item, DailyWeatherVector):
            raise TypeError(
                "history: expected DailyWeatherVector elements, "
                f"got {type(item).__name__} (G5)"
            )
        if item.date in by_date:
            raise ValueError(
                f"history contains duplicate entry for date {item.date.isoformat()}"
            )
        by_date[item.date] = item
    return tuple(by_date[d] for d in sorted(by_date))


def _is_valid_day_vector(vector: DailyWeatherVector) -> bool:
    """True iff all six variables are finite numbers and ``precip_mm >= 0``."""
    for field_name, _ in _VECTOR_FIELD_TO_QUANTITY:
        val = getattr(vector, field_name)
        if isinstance(val, Missing):
            return False
        if not _is_finite(val):
            return False
    assert not isinstance(vector.precip_mm, Missing)
    return vector.precip_mm >= _ZERO_F


def _fit_one_month(
    month: int,
    month_vectors: list[DailyWeatherVector],
    config: SyntheticWeatherConfig,
) -> tuple[
    MonthlyMarkovParameters,
    tuple[DailyWeatherVector, ...],
    tuple[DailyWeatherVector, ...],
]:
    """Fit Markov transitions and empirical pools for one calendar month."""
    by_year: dict[int, list[DailyWeatherVector]] = {}
    for vec in month_vectors:
        by_year.setdefault(vec.date.year, []).append(vec)

    complete_present_years: list[int] = []
    complete_valid_years: list[int] = []
    has_missing_or_invalid_in_complete_dates = False
    has_missing_or_invalid_anywhere = False

    for year, year_days in sorted(by_year.items()):
        _, days_in_month = calendar.monthrange(year, month)
        all_valid = all(_is_valid_day_vector(v) for v in year_days)
        if not all_valid:
            has_missing_or_invalid_anywhere = True
        if len(year_days) == days_in_month:
            complete_present_years.append(year)
            if all_valid:
                complete_valid_years.append(year)
            else:
                has_missing_or_invalid_in_complete_dates = True

    valid_days = [v for v in month_vectors if _is_valid_day_vector(v)]
    wet_pool = tuple(
        v
        for v in valid_days
        if not isinstance(v.precip_mm, Missing)
        and v.precip_mm >= config.wet_day_threshold_mm
    )
    dry_pool = tuple(
        v
        for v in valid_days
        if not isinstance(v.precip_mm, Missing)
        and v.precip_mm < config.wet_day_threshold_mm
    )

    ww = _ZERO
    wd = _ZERO
    dw = _ZERO
    dd = _ZERO
    valid_by_date: dict[dt.date, bool] = {}
    for v in valid_days:
        assert not isinstance(v.precip_mm, Missing)
        valid_by_date[v.date] = v.precip_mm >= config.wet_day_threshold_mm

    one_day = dt.timedelta(days=_ONE)
    for cur_date in sorted(valid_by_date):
        prev_date = cur_date - one_day
        if prev_date.month != month or prev_date not in valid_by_date:
            continue
        prev_wet = valid_by_date[prev_date]
        cur_wet = valid_by_date[cur_date]
        if prev_wet and cur_wet:
            ww += _ONE
        elif prev_wet and not cur_wet:
            wd += _ONE
        elif not prev_wet and cur_wet:
            dw += _ONE
        else:
            dd += _ONE

    valid_year_count = len(complete_valid_years)
    if valid_year_count < config.min_history_years:
        if len(complete_present_years) >= config.min_history_years or (
            has_missing_or_invalid_in_complete_dates
            or (
                len(by_year) >= config.min_history_years
                and has_missing_or_invalid_anywhere
            )
        ):
            failure = Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"calendar month {month:02d} has {valid_year_count} complete "
                    f"valid historical year(s), fewer than required "
                    f"min_history_years={config.min_history_years}; "
                    "missing days are never filled as zero"
                ),
            )
        else:
            failure = Missing(
                reason="NO_COVERAGE",
                detail=(
                    f"calendar month {month:02d} has {len(complete_present_years)} "
                    f"covered historical year(s), fewer than required "
                    f"min_history_years={config.min_history_years}"
                ),
            )
        return (
            MonthlyMarkovParameters(
                month=month,
                p_wet_given_wet=failure,
                p_wet_given_dry=failure,
                p_wet_unconditional=failure,
                wet_pool_size=len(wet_pool),
                dry_pool_size=len(dry_pool),
                valid_years_observed=valid_year_count,
                valid_day_count=len(valid_days),
                ww_transitions=ww,
                wd_transitions=wd,
                dw_transitions=dw,
                dd_transitions=dd,
                coverage_missing=failure,
            ),
            (),
            (),
        )

    total_valid = len(valid_days)
    p_wet_unconditional = len(wet_pool) / total_valid

    w_denom = ww + wd
    if w_denom > _ZERO:
        p_ww: float | Missing = ww / w_denom
    else:
        p_ww = Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"calendar month {month:02d} has no wet predecessor transitions "
                "(ww + wd == 0)"
            ),
        )

    d_denom = dw + dd
    if d_denom > _ZERO:
        p_wd: float | Missing = dw / d_denom
    else:
        p_wd = Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"calendar month {month:02d} has no dry predecessor transitions "
                "(dw + dd == 0)"
            ),
        )

    return (
        MonthlyMarkovParameters(
            month=month,
            p_wet_given_wet=p_ww,
            p_wet_given_dry=p_wd,
            p_wet_unconditional=p_wet_unconditional,
            wet_pool_size=len(wet_pool),
            dry_pool_size=len(dry_pool),
            valid_years_observed=valid_year_count,
            valid_day_count=total_valid,
            ww_transitions=ww,
            wd_transitions=wd,
            dw_transitions=dw,
            dd_transitions=dd,
            coverage_missing=None,
        ),
        wet_pool,
        dry_pool,
    )


def _fit_all_months(
    vectors: tuple[DailyWeatherVector, ...],
    config: SyntheticWeatherConfig,
) -> tuple[
    tuple[MonthlyMarkovParameters, ...],
    dict[int, tuple[DailyWeatherVector, ...]],
    dict[int, tuple[DailyWeatherVector, ...]],
]:
    by_month: dict[int, list[DailyWeatherVector]] = {
        m: [] for m in range(_ONE, _MONTHS_IN_YEAR + _ONE)
    }
    for vec in vectors:
        by_month[vec.date.month].append(vec)

    params_list: list[MonthlyMarkovParameters] = []
    wet_pools: dict[int, tuple[DailyWeatherVector, ...]] = {}
    dry_pools: dict[int, tuple[DailyWeatherVector, ...]] = {}
    for month in range(_ONE, _MONTHS_IN_YEAR + _ONE):
        params, wet_pool, dry_pool = _fit_one_month(month, by_month[month], config)
        params_list.append(params)
        wet_pools[month] = wet_pool
        dry_pools[month] = dry_pool
    return tuple(params_list), wet_pools, dry_pools


def fit_monthly_markov_parameters(
    history: Sequence[DailyWeatherVector] | SiteClimate,
    *,
    config: SyntheticWeatherConfig,
) -> tuple[MonthlyMarkovParameters, ...]:
    """Fit monthly-conditioned two-state Markov parameters from historical weather.

    Raises ``TypeError`` for invalid argument types (G5) and ``ValueError`` for
    duplicate dates or synthetic/non-observed ``SiteClimate`` series.
    """
    if not isinstance(config, SyntheticWeatherConfig):
        raise TypeError(
            f"config: expected SyntheticWeatherConfig, got {type(config).__name__} (G5)"
        )
    vectors = _normalize_history(history)
    params, _, _ = _fit_all_months(vectors, config)
    return params


def _ag_year_month_pairs(ag_year: int, start_month: int) -> list[tuple[int, int]]:
    return [
        (
            ag_year + (start_month - _ONE + offset) // _MONTHS_IN_YEAR,
            (start_month - _ONE + offset) % _MONTHS_IN_YEAR + _ONE,
        )
        for offset in range(_MONTHS_IN_YEAR)
    ]


def _ag_year_dates(
    start_year: int, start_month: int, n_years: int
) -> list[tuple[int, dt.date]]:
    """Build ``(ag_year_index, calendar_date)`` pairs for ``n_years`` ag years."""
    schedule: list[tuple[int, dt.date]] = []
    for ag_offset in range(n_years):
        ag_year = start_year + ag_offset
        for year, month in _ag_year_month_pairs(ag_year, start_month):
            _, days_in_month = calendar.monthrange(year, month)
            for day_num in range(_ONE, days_in_month + _ONE):
                schedule.append((ag_year, dt.date(year, month, day_num)))
    return schedule


def _compute_diagnostics(
    days: tuple[DailyWeatherVector, ...],
    ag_year_by_date: dict[dt.date, int],
    ag_years_order: list[int],
    wet_threshold_mm: float,
) -> SyntheticWeatherDiagnostics:
    wet_spell_count = _ZERO
    wet_day_count = _ZERO
    dry_day_count = _ZERO
    in_wet_spell = False

    precip_by_ag_year: dict[int, list[float]] = {y: [] for y in ag_years_order}
    for vec in days:
        assert not isinstance(vec.precip_mm, Missing)
        is_wet = vec.precip_mm >= wet_threshold_mm
        if is_wet:
            wet_day_count += _ONE
            if not in_wet_spell:
                wet_spell_count += _ONE
                in_wet_spell = True
        else:
            dry_day_count += _ONE
            in_wet_spell = False
        precip_by_ag_year[ag_year_by_date[vec.date]].append(vec.precip_mm)

    totals = tuple(math.fsum(precip_by_ag_year[y]) for y in ag_years_order)
    dist = AnnualPrecipDistribution(
        annual_totals_mm=totals,
        mean_mm=statistics.fmean(totals),
        std_mm=statistics.pstdev(totals),
        min_mm=min(totals),
        median_mm=statistics.median(totals),
        max_mm=max(totals),
    )
    return SyntheticWeatherDiagnostics(
        wet_spell_count=wet_spell_count,
        wet_day_count=wet_day_count,
        dry_day_count=dry_day_count,
        annual_precip_distribution=dist,
    )


def generate_synthetic_weather(
    history: Sequence[DailyWeatherVector] | SiteClimate,
    *,
    config: SyntheticWeatherConfig,
    start_year: int = _ONE,
) -> SyntheticWeatherSeries:
    """Calibrate and simulate a deterministic seeded synthetic daily weather series.

    Every generated series carries ``provenance="SIMULATED"``,
    ``horizon="synthetic"``, and ``can_replace_observed=False``. When any calendar
    month lacks ``config.min_history_years`` valid complete historical years,
    ``days`` and ``diagnostics`` return the first failing month's ``Missing``
    object cleanly without zero-filling missing historical days.
    """
    if not isinstance(config, SyntheticWeatherConfig):
        raise TypeError(
            f"config: expected SyntheticWeatherConfig, got {type(config).__name__} (G5)"
        )
    if not _is_strict_int(start_year):
        raise TypeError(
            f"start_year: expected int, got {type(start_year).__name__} (G5)"
        )
    if start_year < dt.MINYEAR or start_year + config.n_synthetic_years > dt.MAXYEAR:
        raise ValueError(
            f"start_year + n_synthetic_years must stay within {dt.MINYEAR}..{dt.MAXYEAR}"
        )

    vectors = _normalize_history(history)
    monthly_params, wet_pools, dry_pools = _fit_all_months(vectors, config)

    failing = [
        p.coverage_missing for p in monthly_params if p.coverage_missing is not None
    ]
    if failing:
        first_failure = failing[_ZERO]
        return SyntheticWeatherSeries(
            config=config,
            monthly_parameters=monthly_params,
            days=first_failure,
            diagnostics=first_failure,
        )

    params_by_month = {p.month: p for p in monthly_params}
    schedule = _ag_year_dates(
        start_year, config.ag_year_start_month, config.n_synthetic_years
    )
    ag_year_by_date = {cal_date: ag_year for ag_year, cal_date in schedule}
    ag_years_order = [start_year + offset for offset in range(config.n_synthetic_years)]

    rng = random.Random(config.seed)
    generated: list[DailyWeatherVector] = []
    prev_is_wet: bool | None = None

    for _, syn_date in schedule:
        month = syn_date.month
        m_params = params_by_month[month]
        assert not isinstance(m_params.p_wet_unconditional, Missing)

        if prev_is_wet is None:
            p_wet = m_params.p_wet_unconditional
        elif prev_is_wet:
            p_wet = (
                m_params.p_wet_given_wet
                if not isinstance(m_params.p_wet_given_wet, Missing)
                else m_params.p_wet_unconditional
            )
        else:
            p_wet = (
                m_params.p_wet_given_dry
                if not isinstance(m_params.p_wet_given_dry, Missing)
                else m_params.p_wet_unconditional
            )

        is_wet = rng.random() < p_wet
        pool = wet_pools[month] if is_wet else dry_pools[month]
        template = rng.choice(pool)
        generated.append(
            DailyWeatherVector(
                date=syn_date,
                precip_mm=template.precip_mm,
                tmax_c=template.tmax_c,
                tmin_c=template.tmin_c,
                radiation=template.radiation,
                wind=template.wind,
                rh=template.rh,
            )
        )
        prev_is_wet = is_wet

    days_tuple = tuple(generated)
    diagnostics = _compute_diagnostics(
        days_tuple,
        ag_year_by_date,
        ag_years_order,
        config.wet_day_threshold_mm,
    )
    return SyntheticWeatherSeries(
        config=config,
        monthly_parameters=monthly_params,
        days=days_tuple,
        diagnostics=diagnostics,
    )
