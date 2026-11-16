"""Strict separation of normative and exploratory soil erosion views.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13), implementing
``27_PLAN_DE_FRONTERA.md`` §5.1 and ``28_PLAN_INTEGRADO_REV13.md`` §2.

Rev13 enforces a strict boundary between two non-interchangeable tracks:

- ``EROSION_NORMATIVA`` (``NormativeErosionView``): regulatory long-term
  multi-year mean soil loss ``a_norm`` (``Mg ha-1 yr-1``), compared against a
  non-editable soil-profile tolerance ``tolerance_t`` via ``t_ratio`` and
  ``t_margin``. Refuses any single meteorological year, exploratory series,
  future climate mean, or storm/event mean as ``a_norm``.
- ``EROSION_EXPLORATORIA`` (``ExploratoryErosionView``): exploratory series
  ``a_expl(y, s)`` separated cleanly by climate horizon (``"historical"``,
  ``"synthetic"``, ``"future"``) without mixing or averaging horizons, carrying
  explicit ``changes_vs_normative``, ``calibration_status`` (guarding against
  claiming a global literature IMERG slope as Uruguay-calibrated), and
  voluntary threshold year-counts ``k of n`` explicitly marked as non-legal and
  non-channel-sediment-export.
- ``DualErosionSummary``: side-by-side container holding both tracks for the
  same ``case_id`` and ``field_id`` without blending or cross-track averaging.

Pure Python 3.12 stdlib + ``contracts.*`` (G1 pure, frozen dataclasses, G4
typed ``Missing`` propagation never defaulting to zero, G5 strict ``TypeError``
and ``ValueError``, zero invented constants, thresholds, or parameter values).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from contracts.results.models import Missing, ReasonCode

__all__ = [
    "CALIBRATION_LEVELS",
    "CLIMATE_HORIZONS",
    "EROSION_EXPLORATORIA",
    "EROSION_NORMATIVA",
    "EROSION_TRACKS",
    "FACTOR_NAMES",
    "IMERG_SLOPE_SOURCES",
    "NORMATIVE_BASIS_LONG_TERM",
    "NORMATIVE_UNIT",
    "CalibrationLevel",
    "CalibrationStatus",
    "ClimateHorizon",
    "DualErosionSummary",
    "ExploratoryErosionView",
    "ExploratoryPoint",
    "HorizonSeries",
    "ImergSlopeSource",
    "MethodChangeVsNormative",
    "NormativeErosionView",
    "NormativeFactor",
    "NormativeFactorUnits",
    "NormativeFactors",
    "NormativePeriod",
    "ProfileTolerance",
    "VoluntaryThresholdCount",
    "build_normative_erosion_view",
    "combine_erosion_views",
    "compute_horizon_mean",
    "compute_normative_a_norm",
    "compute_t_margin",
    "compute_t_ratio",
    "count_voluntary_threshold_exceedances",
]

# --- Track & vocabulary identifiers ------------------------------------------

EROSION_NORMATIVA: Literal["EROSION_NORMATIVA"] = "EROSION_NORMATIVA"
EROSION_EXPLORATORIA: Literal["EROSION_EXPLORATORIA"] = "EROSION_EXPLORATORIA"
EROSION_TRACKS: tuple[str, ...] = (EROSION_NORMATIVA, EROSION_EXPLORATORIA)

NORMATIVE_UNIT = "Mg ha-1 yr-1"
NORMATIVE_BASIS_LONG_TERM = "long_term_multi_year"

# Factor order matching (R, K, C/RPS, LS, P).
FACTOR_NAMES: tuple[str, ...] = ("r", "k", "c_rps", "ls", "p")

ClimateHorizon = Literal["historical", "synthetic", "future"]
CLIMATE_HORIZONS: tuple[str, ...] = get_args(ClimateHorizon)

CalibrationLevel = Literal[
    "uncalibrated",
    "global_literature_exploratory",
    "uruguay_calibrated",
]
CALIBRATION_LEVELS: tuple[str, ...] = get_args(CalibrationLevel)

ImergSlopeSource = Literal[
    "not_used",
    "global_literature",
    "local_uruguay_calibration",
]
IMERG_SLOPE_SOURCES: tuple[str, ...] = get_args(ImergSlopeSource)

_VALID_REASON_CODES: frozenset[str] = frozenset(get_args(ReasonCode))


# --- Shared validation helpers (G1 / G5) -------------------------------------


def _require_non_blank_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: expected str, got {type(value).__name__}")
    if value.strip() == "":
        raise ValueError(f"{name}: must not be empty or blank")
    return value


def _require_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name}: expected bool, got {type(value).__name__}")
    return value


def _require_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}: expected int, got {type(value).__name__}")
    return value


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_float_or_none(value: float) -> float | None:
    try:
        num = float(value)
    except OverflowError:
        return None
    return num if math.isfinite(num) else None


def _require_finite_number_or_missing(name: str, value: object) -> float | Missing:
    if isinstance(value, Missing):
        return value
    if not _is_number(value):
        raise TypeError(
            f"{name}: expected a number or contracts.results.models.Missing, "
            f"got {type(value).__qualname__}"
        )
    num = _finite_float_or_none(value)
    if num is None:
        raise ValueError(
            f"{name}: must be a finite number; represent non-computable values as Missing"
        )
    return num


def _require_finite_number(name: str, value: object) -> float:
    if not _is_number(value):
        raise TypeError(f"{name}: expected a number, got {type(value).__qualname__}")
    num = _finite_float_or_none(value)
    if num is None:
        raise ValueError(f"{name}: must be a finite number")
    return num


def _describe_missing(name: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"{name} is missing (reason {missing.reason})"
    return f"{name} is missing (reason {missing.reason}: {missing.detail})"


# --- Normative dataclasses ---------------------------------------------------


@dataclass(frozen=True)
class NormativeFactor:
    """One factor of the normative product, or a typed ``Missing`` (C3.1, G4).

    ``value`` may be an ``int``, ``float``, or ``Missing``; non-finite numbers
    are caught by ``compute_normative_a_norm`` as ``Missing(reason="NOT_COMPUTABLE")``.
    """

    value: float | Missing
    unit: str

    def __post_init__(self) -> None:
        _require_non_blank_str("unit", self.unit)
        if isinstance(self.value, Missing):
            return
        if not _is_number(self.value):
            raise TypeError(
                f"value: expected a number or contracts.results.models.Missing, "
                f"got {type(self.value).__qualname__}"
            )


@dataclass(frozen=True)
class NormativeFactorUnits:
    """Accepted unit strings for the five normative factors ``(R, K, C/RPS, LS, P)``."""

    r: str
    k: str
    c_rps: str
    ls: str
    p: str

    def __post_init__(self) -> None:
        for name in FACTOR_NAMES:
            _require_non_blank_str(f"factor_units.{name}", getattr(self, name))


@dataclass(frozen=True)
class NormativeFactors:
    """The five normative factors ``(R, K, C/RPS, LS, P)``."""

    r: NormativeFactor
    k: NormativeFactor
    c_rps: NormativeFactor
    ls: NormativeFactor
    p: NormativeFactor

    def __post_init__(self) -> None:
        for name in FACTOR_NAMES:
            item = getattr(self, name)
            if not isinstance(item, NormativeFactor):
                raise TypeError(
                    f"factors.{name}: expected NormativeFactor, got {type(item).__name__}"
                )

    def as_dict(self) -> dict[str, NormativeFactor]:
        return {name: getattr(self, name) for name in FACTOR_NAMES}


@dataclass(frozen=True)
class NormativePeriod:
    """One multi-year or rotational period covered by the normative mean ``a_norm``."""

    period_id: str
    start_year: int
    end_year: int

    def __post_init__(self) -> None:
        _require_non_blank_str("period_id", self.period_id)
        start = _require_int("start_year", self.start_year)
        end = _require_int("end_year", self.end_year)
        if end < start:
            raise ValueError(
                f"period '{self.period_id}': end_year ({end}) is before start_year ({start})"
            )


@dataclass(frozen=True)
class ProfileTolerance:
    """Non-editable normative soil-profile tolerance ``T`` with provenance."""

    value: float | Missing
    unit: str
    profile_id: str
    source: str
    version: str
    editable: Literal[False] = False

    def __post_init__(self) -> None:
        val = _require_finite_number_or_missing("tolerance_t.value", self.value)
        if not isinstance(val, Missing):
            object.__setattr__(self, "value", val)
        _require_non_blank_str("tolerance_t.unit", self.unit)
        _require_non_blank_str("tolerance_t.profile_id", self.profile_id)
        _require_non_blank_str("tolerance_t.source", self.source)
        _require_non_blank_str("tolerance_t.version", self.version)
        editable = _require_bool("tolerance_t.editable", self.editable)
        if editable is not False:
            raise ValueError(
                "tolerance_t is non-editable in normative view (editable must be False)"
            )


def _validate_normative_periods(periods: object) -> tuple[NormativePeriod, ...]:
    if not isinstance(periods, tuple):
        raise TypeError(
            f"periods: expected tuple of NormativePeriod, got {type(periods).__name__}"
        )
    if not periods:
        raise ValueError("periods: at least one NormativePeriod is required for a_norm")
    for idx, period in enumerate(periods):
        if not isinstance(period, NormativePeriod):
            raise TypeError(
                f"periods[{idx}]: expected NormativePeriod, got {type(period).__name__}"
            )
    min_start = min(p.start_year for p in periods)
    max_end = max(p.end_year for p in periods)
    span_years = max_end - min_start + 1
    if span_years < 2:
        raise ValueError(
            "hard guard: a_norm cannot represent a single meteorological year "
            f"(covered span is {span_years} year, requires multi-year span >= 2)"
        )
    return periods


def _validate_a_norm_basis(a_norm_basis: object) -> str:
    basis = _require_non_blank_str("a_norm_basis", a_norm_basis)
    if basis != NORMATIVE_BASIS_LONG_TERM:
        raise ValueError(
            f"hard guard: a_norm_basis='{basis}' is refused as normative a_norm; "
            f"single meteorological year, exploratory, future, and storm means are "
            f"prohibited (expected '{NORMATIVE_BASIS_LONG_TERM}')"
        )
    return basis


@dataclass(frozen=True)
class NormativeErosionView:
    """``EROSION_NORMATIVA``: long-term multi-year normative soil-loss view."""

    case_id: str
    field_id: str
    a_norm: float | Missing
    tolerance_t: ProfileTolerance
    t_ratio: float | Missing
    t_margin: float | Missing
    official_method: str
    official_version: str
    reference_erosivity_source: str
    periods: tuple[NormativePeriod, ...]
    factor_units: NormativeFactorUnits
    unit: str = NORMATIVE_UNIT
    a_norm_basis: str = NORMATIVE_BASIS_LONG_TERM
    pre_evaluation: bool = True
    official_parity_proven: bool = False
    factors: NormativeFactors | None = None
    track: Literal["EROSION_NORMATIVA"] = EROSION_NORMATIVA

    def __post_init__(self) -> None:
        _require_non_blank_str("case_id", self.case_id)
        _require_non_blank_str("field_id", self.field_id)
        if self.track != EROSION_NORMATIVA:
            raise ValueError(
                f"track: NormativeErosionView requires '{EROSION_NORMATIVA}', got {self.track!r}"
            )
        unit = _require_non_blank_str("unit", self.unit)
        if unit != NORMATIVE_UNIT:
            raise ValueError(
                f"unit: normative a_norm requires '{NORMATIVE_UNIT}', got '{unit}'"
            )
        _validate_a_norm_basis(self.a_norm_basis)
        _validate_normative_periods(self.periods)

        _require_non_blank_str("official_method", self.official_method)
        _require_non_blank_str("official_version", self.official_version)
        _require_non_blank_str(
            "reference_erosivity_source", self.reference_erosivity_source
        )

        if not isinstance(self.tolerance_t, ProfileTolerance):
            raise TypeError(
                f"tolerance_t: expected ProfileTolerance, got {type(self.tolerance_t).__name__}"
            )
        if not isinstance(self.factor_units, NormativeFactorUnits):
            raise TypeError(
                f"factor_units: expected NormativeFactorUnits, got {type(self.factor_units).__name__}"
            )

        pre_eval = _require_bool("pre_evaluation", self.pre_evaluation)
        parity = _require_bool("official_parity_proven", self.official_parity_proven)
        if not parity and not pre_eval:
            raise ValueError(
                "pre_evaluation must be True unless official_parity_proven is True"
            )

        a_norm_val = _require_finite_number_or_missing("a_norm", self.a_norm)
        if not isinstance(a_norm_val, Missing):
            object.__setattr__(self, "a_norm", a_norm_val)

        t_ratio_val = _require_finite_number_or_missing("t_ratio", self.t_ratio)
        if not isinstance(t_ratio_val, Missing):
            object.__setattr__(self, "t_ratio", t_ratio_val)

        t_margin_val = _require_finite_number_or_missing("t_margin", self.t_margin)
        if not isinstance(t_margin_val, Missing):
            object.__setattr__(self, "t_margin", t_margin_val)

        if self.factors is not None:
            if not isinstance(self.factors, NormativeFactors):
                raise TypeError(
                    f"factors: expected NormativeFactors or None, got {type(self.factors).__name__}"
                )
            factor_map = self.factors.as_dict()
            absent = [
                name
                for name, factor in factor_map.items()
                if isinstance(factor.value, Missing)
            ]
            if absent and not isinstance(a_norm_val, Missing):
                raise ValueError(
                    f"G4 violation: factors {absent} are Missing so a_norm must be Missing, not numeric"
                )
            wrong_units = [
                name
                for name, factor in factor_map.items()
                if factor.unit != getattr(self.factor_units, name)
            ]
            if wrong_units and not isinstance(a_norm_val, Missing):
                raise ValueError(
                    f"unit guard violation: factors {wrong_units} do not match factor_units "
                    "so a_norm must be Missing"
                )
            non_finite = [
                name
                for name, factor in factor_map.items()
                if not isinstance(factor.value, Missing)
                and _finite_float_or_none(factor.value) is None
            ]
            if non_finite and not isinstance(a_norm_val, Missing):
                raise ValueError(
                    f"G4 violation: factors {non_finite} are not finite so a_norm must be Missing"
                )

        # G4 / T<=0 consistency checks on t_ratio and t_margin
        t_val = self.tolerance_t.value
        has_missing_input = isinstance(t_val, Missing) or isinstance(
            a_norm_val, Missing
        )
        if has_missing_input and not isinstance(t_ratio_val, Missing):
            raise ValueError(
                "G4 violation: t_ratio must be Missing when a_norm or tolerance_t is Missing"
            )
        if has_missing_input and not isinstance(t_margin_val, Missing):
            raise ValueError(
                "G4 violation: t_margin must be Missing when a_norm or tolerance_t is Missing"
            )
        if (
            not has_missing_input
            and self.tolerance_t.unit != NORMATIVE_UNIT
            and (
                not isinstance(t_ratio_val, Missing)
                or not isinstance(t_margin_val, Missing)
            )
        ):
            raise ValueError(
                "unit guard violation: t_ratio and t_margin must be Missing when "
                f"tolerance_t.unit != '{NORMATIVE_UNIT}'"
            )
        if (
            not has_missing_input
            and self.tolerance_t.unit == NORMATIVE_UNIT
            and t_val <= 0
            and (
                not isinstance(t_ratio_val, Missing)
                or t_ratio_val.reason != "NOT_COMPUTABLE"
            )
        ):
            raise ValueError(
                "tolerance_t <= 0 requires t_ratio to be Missing(reason='NOT_COMPUTABLE')"
            )


# --- Normative pure functions ------------------------------------------------


def compute_normative_a_norm(
    *,
    factors: NormativeFactors,
    accepted_units: NormativeFactorUnits,
    unit_guard_reason: ReasonCode = "NOT_COMPUTABLE",
) -> float | Missing:
    """Multiply the five normative factors ``(R, K, C/RPS, LS, P)`` with G4 checks.

    Returns ``Missing`` (never ``0``) if any factor is ``Missing``, if any
    factor unit differs from ``accepted_units``, or if any factor or the
    product is not finite.
    """
    if not isinstance(factors, NormativeFactors):
        raise TypeError(
            f"factors: expected NormativeFactors, got {type(factors).__name__}"
        )
    if not isinstance(accepted_units, NormativeFactorUnits):
        raise TypeError(
            f"accepted_units: expected NormativeFactorUnits, got {type(accepted_units).__name__}"
        )
    if not isinstance(unit_guard_reason, str) or (
        unit_guard_reason not in _VALID_REASON_CODES
    ):
        raise ValueError(
            "unit_guard_reason: must be a valid ReasonCode of contracts.results.models"
        )

    factor_map = factors.as_dict()
    missing = [
        _describe_missing(f"factor '{name}'", factor.value)
        for name, factor in factor_map.items()
        if isinstance(factor.value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing))

    wrong_unit = [
        f"factor '{name}' has unit '{factor.unit}', expected '{getattr(accepted_units, name)}'"
        for name, factor in factor_map.items()
        if factor.unit != getattr(accepted_units, name)
    ]
    if wrong_unit:
        return Missing(reason=unit_guard_reason, detail="; ".join(wrong_unit))

    finite_values: dict[str, float] = {}
    non_finite: list[str] = []
    for name, factor in factor_map.items():
        num = _finite_float_or_none(factor.value)
        if num is None:
            non_finite.append(f"factor '{name}' is not a finite number")
        else:
            finite_values[name] = num
    if non_finite:
        return Missing(reason="NOT_COMPUTABLE", detail="; ".join(non_finite))

    product = math.prod(finite_values.values())
    if not math.isfinite(product):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="product of normative factors is not a finite number",
        )
    return product


def compute_t_ratio(
    *,
    a_norm: float | Missing,
    tolerance_t: ProfileTolerance,
) -> float | Missing:
    """Compute ``a_norm / t``, returning ``Missing(reason="NOT_COMPUTABLE")`` if ``t <= 0``."""
    a_val = _require_finite_number_or_missing("a_norm", a_norm)
    if not isinstance(tolerance_t, ProfileTolerance):
        raise TypeError(
            f"tolerance_t: expected ProfileTolerance, got {type(tolerance_t).__name__}"
        )
    t_val = tolerance_t.value

    if not isinstance(t_val, Missing):
        if tolerance_t.unit != NORMATIVE_UNIT:
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"tolerance_t unit '{tolerance_t.unit}' does not match "
                    f"normative unit '{NORMATIVE_UNIT}'"
                ),
            )
        if t_val <= 0:
            return Missing(
                reason="NOT_COMPUTABLE",
                detail="tolerance_t must be strictly positive (> 0) to compute t_ratio",
            )

    missing_parts: list[str] = []
    if isinstance(a_val, Missing):
        missing_parts.append(_describe_missing("a_norm", a_val))
    if isinstance(t_val, Missing):
        missing_parts.append(_describe_missing("tolerance_t", t_val))
    if missing_parts:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing_parts))

    ratio = a_val / t_val
    if not math.isfinite(ratio):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="t_ratio is not a finite number",
        )
    return ratio


def compute_t_margin(
    *,
    a_norm: float | Missing,
    tolerance_t: ProfileTolerance,
) -> float | Missing:
    """Compute ``t - a_norm`` with G4 ``Missing`` propagation."""
    a_val = _require_finite_number_or_missing("a_norm", a_norm)
    if not isinstance(tolerance_t, ProfileTolerance):
        raise TypeError(
            f"tolerance_t: expected ProfileTolerance, got {type(tolerance_t).__name__}"
        )
    t_val = tolerance_t.value

    missing_parts: list[str] = []
    if isinstance(t_val, Missing):
        missing_parts.append(_describe_missing("tolerance_t", t_val))
    if isinstance(a_val, Missing):
        missing_parts.append(_describe_missing("a_norm", a_val))
    if missing_parts:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing_parts))

    if tolerance_t.unit != NORMATIVE_UNIT:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"tolerance_t unit '{tolerance_t.unit}' does not match "
                f"normative unit '{NORMATIVE_UNIT}'"
            ),
        )

    margin = t_val - a_val
    if not math.isfinite(margin):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="t_margin is not a finite number",
        )
    return margin


def build_normative_erosion_view(
    *,
    case_id: str,
    field_id: str,
    factors: NormativeFactors,
    factor_units: NormativeFactorUnits,
    tolerance_t: ProfileTolerance,
    official_method: str,
    official_version: str,
    reference_erosivity_source: str,
    periods: tuple[NormativePeriod, ...],
    a_norm_basis: str = NORMATIVE_BASIS_LONG_TERM,
    pre_evaluation: bool = True,
    official_parity_proven: bool = False,
    unit_guard_reason: ReasonCode = "NOT_COMPUTABLE",
) -> NormativeErosionView:
    """Construct ``NormativeErosionView`` from factors, units, tolerance, and provenance."""
    _validate_a_norm_basis(a_norm_basis)
    _validate_normative_periods(periods)

    a_norm = compute_normative_a_norm(
        factors=factors,
        accepted_units=factor_units,
        unit_guard_reason=unit_guard_reason,
    )
    t_ratio = compute_t_ratio(a_norm=a_norm, tolerance_t=tolerance_t)
    t_margin = compute_t_margin(a_norm=a_norm, tolerance_t=tolerance_t)

    return NormativeErosionView(
        case_id=case_id,
        field_id=field_id,
        a_norm=a_norm,
        tolerance_t=tolerance_t,
        t_ratio=t_ratio,
        t_margin=t_margin,
        official_method=official_method,
        official_version=official_version,
        reference_erosivity_source=reference_erosivity_source,
        periods=periods,
        factor_units=factor_units,
        unit=NORMATIVE_UNIT,
        a_norm_basis=a_norm_basis,
        pre_evaluation=pre_evaluation,
        official_parity_proven=official_parity_proven,
        factors=factors,
    )


# --- Exploratory dataclasses -------------------------------------------------


@dataclass(frozen=True)
class ExploratoryPoint:
    """One exploratory soil-loss point ``a_expl(y, s)`` within a single climate horizon."""

    year: int
    scenario: str
    horizon: ClimateHorizon
    value: float | Missing
    unit: str

    def __post_init__(self) -> None:
        _require_int("year", self.year)
        _require_non_blank_str("scenario", self.scenario)
        horizon = _require_non_blank_str("horizon", self.horizon)
        if horizon not in CLIMATE_HORIZONS:
            raise ValueError(
                f"horizon: expected one of {CLIMATE_HORIZONS}, got '{horizon}'"
            )
        val = _require_finite_number_or_missing("value", self.value)
        if not isinstance(val, Missing):
            object.__setattr__(self, "value", val)
        _require_non_blank_str("unit", self.unit)


@dataclass(frozen=True)
class HorizonSeries:
    """Time series ``a_expl(y, s)`` strictly belonging to one climate horizon."""

    horizon: ClimateHorizon
    points: tuple[ExploratoryPoint, ...]

    def __post_init__(self) -> None:
        horizon = _require_non_blank_str("horizon", self.horizon)
        if horizon not in CLIMATE_HORIZONS:
            raise ValueError(
                f"horizon: expected one of {CLIMATE_HORIZONS}, got '{horizon}'"
            )
        if not isinstance(self.points, tuple):
            raise TypeError(
                f"points: expected tuple of ExploratoryPoint, got {type(self.points).__name__}"
            )
        seen_keys: set[tuple[int, str]] = set()
        units: set[str] = set()
        for idx, pt in enumerate(self.points):
            if not isinstance(pt, ExploratoryPoint):
                raise TypeError(
                    f"points[{idx}]: expected ExploratoryPoint, got {type(pt).__name__}"
                )
            if pt.horizon != horizon:
                raise ValueError(
                    f"refusing to mix climate horizons: HorizonSeries is '{horizon}' "
                    f"but points[{idx}] has horizon '{pt.horizon}'"
                )
            key = (pt.year, pt.scenario)
            if key in seen_keys:
                raise ValueError(
                    f"duplicate (year, scenario) entry {key!r} in horizon '{horizon}'"
                )
            seen_keys.add(key)
            units.add(pt.unit)
        if len(units) > 1:
            raise ValueError(
                f"mixed units {sorted(units)!r} within horizon '{horizon}'"
            )

    @property
    def unit(self) -> str | None:
        if not self.points:
            return None
        return self.points[0].unit


@dataclass(frozen=True)
class MethodChangeVsNormative:
    """Explicit documentation of one methodological difference vs ``EROSION_NORMATIVA``."""

    aspect: str
    normative_basis: str
    exploratory_basis: str
    note: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank_str("aspect", self.aspect)
        _require_non_blank_str("normative_basis", self.normative_basis)
        _require_non_blank_str("exploratory_basis", self.exploratory_basis)
        if self.note is not None:
            _require_non_blank_str("note", self.note)


@dataclass(frozen=True)
class CalibrationStatus:
    """Calibration status of the exploratory model, guarding against false local claims.

    Specifically prevents claiming a global literature IMERG erosivity slope
    as locally calibrated for Uruguay.
    """

    status: CalibrationLevel
    imerg_slope_source: ImergSlopeSource
    is_uruguay_calibrated: bool
    evidence_note: str

    def __post_init__(self) -> None:
        status = _require_non_blank_str("status", self.status)
        if status not in CALIBRATION_LEVELS:
            raise ValueError(
                f"status: expected one of {CALIBRATION_LEVELS}, got '{status}'"
            )
        slope_src = _require_non_blank_str(
            "imerg_slope_source", self.imerg_slope_source
        )
        if slope_src not in IMERG_SLOPE_SOURCES:
            raise ValueError(
                f"imerg_slope_source: expected one of {IMERG_SLOPE_SOURCES}, got '{slope_src}'"
            )
        uruguay_cal = _require_bool("is_uruguay_calibrated", self.is_uruguay_calibrated)
        note = _require_non_blank_str("evidence_note", self.evidence_note)

        if slope_src == "global_literature" and (
            uruguay_cal or status == "uruguay_calibrated"
        ):
            raise ValueError(
                "calibration guard: global literature IMERG slope cannot be claimed "
                "as Uruguay-calibrated"
            )
        if status == "uruguay_calibrated" and not uruguay_cal:
            raise ValueError(
                "calibration guard: status='uruguay_calibrated' requires is_uruguay_calibrated=True"
            )
        if uruguay_cal and status != "uruguay_calibrated":
            raise ValueError(
                "calibration guard: is_uruguay_calibrated=True requires status='uruguay_calibrated'"
            )
        if slope_src == "local_uruguay_calibration" and not uruguay_cal:
            raise ValueError(
                "calibration guard: imerg_slope_source='local_uruguay_calibration' "
                "requires is_uruguay_calibrated=True"
            )
        lower_note = note.casefold()
        if uruguay_cal and (
            ("global" in lower_note and "imerg" in lower_note)
            or "global literature" in lower_note
        ):
            raise ValueError(
                "calibration guard: evidence_note referencing global literature or global IMERG "
                "cannot be marked Uruguay-calibrated"
            )


@dataclass(frozen=True)
class VoluntaryThresholdCount:
    """Voluntary exceedance year-count ``k of n`` on an exploratory horizon/scenario.

    Strictly non-legal, voluntary-target only, and never channel sediment export.
    """

    horizon: ClimateHorizon
    scenario: str
    threshold_value: float
    threshold_unit: str
    exceedance_years: int
    total_years: int
    counts_legal_noncompliance: Literal[False] = False
    counts_voluntary_target: Literal[True] = True
    represents_channel_sediment_export: Literal[False] = False

    def __post_init__(self) -> None:
        horizon = _require_non_blank_str("horizon", self.horizon)
        if horizon not in CLIMATE_HORIZONS:
            raise ValueError(
                f"horizon: expected one of {CLIMATE_HORIZONS}, got '{horizon}'"
            )
        _require_non_blank_str("scenario", self.scenario)
        thresh = _require_finite_number("threshold_value", self.threshold_value)
        object.__setattr__(self, "threshold_value", thresh)
        _require_non_blank_str("threshold_unit", self.threshold_unit)

        k = _require_int("exceedance_years", self.exceedance_years)
        n = _require_int("total_years", self.total_years)
        if n < 1:
            raise ValueError(f"total_years (n) must be >= 1, got {n}")
        if k < 0 or k > n:
            raise ValueError(
                f"exceedance_years (k={k}) must satisfy 0 <= k <= total_years (n={n})"
            )

        legal = _require_bool(
            "counts_legal_noncompliance", self.counts_legal_noncompliance
        )
        voluntary = _require_bool(
            "counts_voluntary_target", self.counts_voluntary_target
        )
        channel = _require_bool(
            "represents_channel_sediment_export",
            self.represents_channel_sediment_export,
        )
        if legal is not False:
            raise ValueError(
                "voluntary threshold guard: counts_legal_noncompliance must be False"
            )
        if voluntary is not True:
            raise ValueError(
                "voluntary threshold guard: counts_voluntary_target must be True"
            )
        if channel is not False:
            raise ValueError(
                "voluntary threshold guard: represents_channel_sediment_export must be False"
            )


@dataclass(frozen=True)
class ExploratoryErosionView:
    """``EROSION_EXPLORATORIA``: horizon-separated exploratory soil-loss view."""

    case_id: str
    field_id: str
    changes_vs_normative: tuple[MethodChangeVsNormative, ...]
    calibration_status: CalibrationStatus
    historical: HorizonSeries | None = None
    synthetic: HorizonSeries | None = None
    future: HorizonSeries | None = None
    voluntary_threshold_counts: tuple[VoluntaryThresholdCount, ...] = ()
    counts_legal_noncompliance: Literal[False] = False
    counts_voluntary_target: Literal[True] = True
    represents_channel_sediment_export: Literal[False] = False
    track: Literal["EROSION_EXPLORATORIA"] = EROSION_EXPLORATORIA

    def __post_init__(self) -> None:
        _require_non_blank_str("case_id", self.case_id)
        _require_non_blank_str("field_id", self.field_id)
        if self.track != EROSION_EXPLORATORIA:
            raise ValueError(
                f"track: ExploratoryErosionView requires '{EROSION_EXPLORATORIA}', "
                f"got {self.track!r}"
            )

        if not isinstance(self.changes_vs_normative, tuple):
            raise TypeError(
                "changes_vs_normative: expected tuple of MethodChangeVsNormative, "
                f"got {type(self.changes_vs_normative).__name__}"
            )
        if not self.changes_vs_normative:
            raise ValueError(
                "changes_vs_normative: must explicitly declare at least one change vs normative"
            )
        for idx, item in enumerate(self.changes_vs_normative):
            if not isinstance(item, MethodChangeVsNormative):
                raise TypeError(
                    f"changes_vs_normative[{idx}]: expected MethodChangeVsNormative, "
                    f"got {type(item).__name__}"
                )

        if not isinstance(self.calibration_status, CalibrationStatus):
            raise TypeError(
                "calibration_status: expected CalibrationStatus, "
                f"got {type(self.calibration_status).__name__}"
            )

        horizons_present = 0
        for expected_horizon in CLIMATE_HORIZONS:
            series = getattr(self, expected_horizon)
            if series is None:
                continue
            if not isinstance(series, HorizonSeries):
                raise TypeError(
                    f"{expected_horizon}: expected HorizonSeries or None, "
                    f"got {type(series).__name__}"
                )
            if series.horizon != expected_horizon:
                raise ValueError(
                    f"horizon mismatch: field '{expected_horizon}' received "
                    f"HorizonSeries(horizon='{series.horizon}')"
                )
            horizons_present += 1
        if horizons_present == 0:
            raise ValueError(
                "ExploratoryErosionView requires at least one HorizonSeries "
                "('historical', 'synthetic', or 'future')"
            )

        if not isinstance(self.voluntary_threshold_counts, tuple):
            raise TypeError(
                "voluntary_threshold_counts: expected tuple of VoluntaryThresholdCount, "
                f"got {type(self.voluntary_threshold_counts).__name__}"
            )
        for idx, count in enumerate(self.voluntary_threshold_counts):
            if not isinstance(count, VoluntaryThresholdCount):
                raise TypeError(
                    f"voluntary_threshold_counts[{idx}]: expected VoluntaryThresholdCount, "
                    f"got {type(count).__name__}"
                )
            if getattr(self, count.horizon) is None:
                raise ValueError(
                    f"voluntary_threshold_counts[{idx}]: references horizon '{count.horizon}' "
                    "which is not present on this ExploratoryErosionView"
                )

        legal = _require_bool(
            "counts_legal_noncompliance", self.counts_legal_noncompliance
        )
        voluntary = _require_bool(
            "counts_voluntary_target", self.counts_voluntary_target
        )
        channel = _require_bool(
            "represents_channel_sediment_export",
            self.represents_channel_sediment_export,
        )
        if legal is not False:
            raise ValueError(
                "exploratory guard: counts_legal_noncompliance must be False"
            )
        if voluntary is not True:
            raise ValueError("exploratory guard: counts_voluntary_target must be True")
        if channel is not False:
            raise ValueError(
                "exploratory guard: represents_channel_sediment_export must be False"
            )


# --- Exploratory pure functions ----------------------------------------------


def compute_horizon_mean(
    series: HorizonSeries | Sequence[HorizonSeries | ExploratoryPoint],
    *,
    scenario: str | None = None,
) -> float | Missing:
    """Compute the mean of ``a_expl(y, s)`` within ONE climate horizon.

    Refuses with ``ValueError`` if asked to mix or average across distinct
    climate horizons. Propagates G4 ``Missing`` if any point in scope is
    ``Missing`` (never treats missing as zero).
    """
    if scenario is not None:
        _require_non_blank_str("scenario", scenario)

    if isinstance(series, HorizonSeries):
        points = series.points
    elif isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
        if not series:
            return Missing(
                reason="NO_COVERAGE",
                detail="no exploratory points or horizon series supplied",
            )
        if all(isinstance(item, HorizonSeries) for item in series):
            horizons = {item.horizon for item in series}
            if len(horizons) > 1:
                raise ValueError(
                    f"refusing to mix or average distinct climate horizons: {sorted(horizons)!r}"
                )
            units = {item.unit for item in series if item.unit is not None}
            if len(units) > 1:
                raise ValueError(
                    f"refusing to mix distinct units {sorted(units)!r} within horizon"
                )
            points = tuple(pt for item in series for pt in item.points)
        elif all(isinstance(item, ExploratoryPoint) for item in series):
            horizons = {item.horizon for item in series}
            if len(horizons) > 1:
                raise ValueError(
                    f"refusing to mix or average distinct climate horizons: {sorted(horizons)!r}"
                )
            units = {item.unit for item in series}
            if len(units) > 1:
                raise ValueError(
                    f"refusing to mix distinct units {sorted(units)!r} within horizon"
                )
            points = tuple(series)
        else:
            raise TypeError(
                "series: expected HorizonSeries or sequence of HorizonSeries/ExploratoryPoint"
            )
    else:
        raise TypeError(
            "series: expected HorizonSeries or sequence of HorizonSeries/ExploratoryPoint, "
            f"got {type(series).__name__}"
        )

    selected = (
        points
        if scenario is None
        else tuple(pt for pt in points if pt.scenario == scenario)
    )
    if not selected:
        scope = f"scenario '{scenario}'" if scenario is not None else "horizon"
        return Missing(
            reason="NO_COVERAGE",
            detail=f"no exploratory points available for {scope}",
        )

    missing_parts = [
        _describe_missing(f"(year={pt.year}, scenario='{pt.scenario}')", pt.value)
        for pt in selected
        if isinstance(pt.value, Missing)
    ]
    if missing_parts:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing_parts))

    total = math.fsum(float(pt.value) for pt in selected)
    mean = total / len(selected)
    if not math.isfinite(mean):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="mean of exploratory points is not a finite number",
        )
    return mean


def count_voluntary_threshold_exceedances(
    *,
    series: HorizonSeries,
    scenario: str,
    threshold_value: float | Missing,
    threshold_unit: str,
) -> VoluntaryThresholdCount | Missing:
    """Count years ``k of n`` exceeding ``threshold_value`` for one horizon and scenario.

    Returns ``Missing`` (never ``0``) when ``threshold_value`` or any point in
    the scenario is ``Missing``, when the scenario has no points, or when units
    mismatch. Never flags legal noncompliance or channel sediment export.
    """
    if not isinstance(series, HorizonSeries):
        raise TypeError(f"series: expected HorizonSeries, got {type(series).__name__}")
    _require_non_blank_str("scenario", scenario)
    _require_non_blank_str("threshold_unit", threshold_unit)
    thresh = _require_finite_number_or_missing("threshold_value", threshold_value)
    if isinstance(thresh, Missing):
        return Missing(
            reason="MISSING_INPUT",
            detail=_describe_missing("threshold_value", thresh),
        )

    selected = tuple(pt for pt in series.points if pt.scenario == scenario)
    if not selected:
        return Missing(
            reason="NO_COVERAGE",
            detail=(
                f"no exploratory points for scenario '{scenario}' "
                f"in horizon '{series.horizon}'"
            ),
        )

    series_unit = selected[0].unit
    if series_unit != threshold_unit:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"series unit '{series_unit}' does not match "
                f"threshold_unit '{threshold_unit}'"
            ),
        )

    missing_parts = [
        _describe_missing(f"(year={pt.year}, scenario='{pt.scenario}')", pt.value)
        for pt in selected
        if isinstance(pt.value, Missing)
    ]
    if missing_parts:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing_parts))

    exceedances = sum(1 for pt in selected if float(pt.value) > thresh)
    return VoluntaryThresholdCount(
        horizon=series.horizon,
        scenario=scenario,
        threshold_value=thresh,
        threshold_unit=threshold_unit,
        exceedance_years=exceedances,
        total_years=len(selected),
        counts_legal_noncompliance=False,
        counts_voluntary_target=True,
        represents_channel_sediment_export=False,
    )


# --- Side-by-side DualErosionSummary -----------------------------------------


@dataclass(frozen=True)
class DualErosionSummary:
    """Side-by-side container holding ``EROSION_NORMATIVA`` and ``EROSION_EXPLORATORIA``.

    The two tracks remain strictly separated and are never blended or averaged.
    """

    case_id: str
    field_id: str
    normative: NormativeErosionView | Missing
    exploratory: ExploratoryErosionView | Missing
    allows_cross_track_averaging: Literal[False] = False

    def __post_init__(self) -> None:
        case_id = _require_non_blank_str("case_id", self.case_id)
        field_id = _require_non_blank_str("field_id", self.field_id)

        if not isinstance(self.normative, (NormativeErosionView, Missing)):
            raise TypeError(
                "normative: expected NormativeErosionView or Missing, "
                f"got {type(self.normative).__name__}"
            )
        if not isinstance(self.exploratory, (ExploratoryErosionView, Missing)):
            raise TypeError(
                "exploratory: expected ExploratoryErosionView or Missing, "
                f"got {type(self.exploratory).__name__}"
            )

        if isinstance(self.normative, NormativeErosionView) and (
            self.normative.case_id != case_id or self.normative.field_id != field_id
        ):
            raise ValueError(
                "G5 mismatch: normative view case_id/field_id differs from summary"
            )
        if isinstance(self.exploratory, ExploratoryErosionView) and (
            self.exploratory.case_id != case_id or self.exploratory.field_id != field_id
        ):
            raise ValueError(
                "G5 mismatch: exploratory view case_id/field_id differs from summary"
            )

        allow_avg = _require_bool(
            "allows_cross_track_averaging", self.allows_cross_track_averaging
        )
        if allow_avg is not False:
            raise ValueError(
                "DualErosionSummary forbids cross-track averaging "
                "(allows_cross_track_averaging must be False)"
            )


def combine_erosion_views(
    *,
    case_id: str,
    field_id: str,
    normative: NormativeErosionView | Missing,
    exploratory: ExploratoryErosionView | Missing,
) -> DualErosionSummary:
    """Combine normative and exploratory views side by side without mixing tracks."""
    return DualErosionSummary(
        case_id=case_id,
        field_id=field_id,
        normative=normative,
        exploratory=exploratory,
        allows_cross_track_averaging=False,
    )
