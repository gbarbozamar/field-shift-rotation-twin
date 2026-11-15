"""Future climate ensemble & seasonal forecast adapters.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements no-default settings and ``httpx.Client`` adapters (tested with
``httpx.MockTransport``, never live network calls in tests) for:

1. ``NexGddpCmip6Source`` — NEX-GDDP-CMIP6 downscaled daily scenarios
   (``tasmax``, ``tasmin``, ``pr``, etc.).
2. ``Isimip3bSource`` — ISIMIP3b 5-model CMIP6 bias-adjusted contrast scenarios
   (``SSP1-2.6``, ``SSP3-7.0``, ``SSP5-8.5``).
3. ``SeasonalForecastSubsetSource`` — ``GEOS-S2S-3`` / ``NMME`` seasonal
   tercile and member subsets.

Also implements ``compare_climate_ensembles(nex_runs, isimip_runs, criterion)``
enforcing Rev13 rules:

- Reports ``NEX-GDDP-CMIP6`` and ``ISIMIP3b`` strictly separately with per-ensemble
  ``(agreeing_models, total_models, min_val, max_val)``, never averaging across
  ensembles (``cross_ensemble_averaged=False``).
- Any future scenario or seasonal forecast output sets
  ``valid_for_normative_erosion=False``.
- Missing or malformed HTTP payloads return typed ``SOURCE_UNAVAILABLE``,
  ``NO_COVERAGE``, or ``MISSING_INPUT`` without echoing raw response bodies.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

import httpx
from pydantic import Field, FiniteFloat, ValidationError, model_validator

from adapters.cache import ResponseCache, StoredResponse, cache_key
from adapters.ports import ClimateRequest, SourceInfo, SourceState
from contracts.inputs.common import (
    ContractModel,
    IsoDate,
    Missing,
    NonEmptyStr,
    QuantityId,
    ReasonCode,
)
from contracts.inputs.site_climate import DailyValue

# C4.1: future projections and seasonal forecasts are SIMULATED or DERIVED.
FUTURE_PROVENANCE_LABELS = ("SIMULATED", "DERIVED")
FutureProvenance = Literal["SIMULATED", "DERIVED"]

# C3.2: closed list of reason codes.
REASON_CODES = (
    "NOT_DECLARED",
    "SOURCE_UNAVAILABLE",
    "NO_COVERAGE",
    "MISSING_INPUT",
    "NOT_COMPUTABLE",
    "CONTROL_FAILED",
    "NOT_AVAILABLE",
    "NOT_APPLICABLE",
)

NEX_GDDP_ENSEMBLE_NAME = "NEX-GDDP-CMIP6"
ISIMIP3B_ENSEMBLE_NAME = "ISIMIP3b"
ISIMIP3B_CONTRAST_SCENARIOS = ("SSP1-2.6", "SSP3-7.0", "SSP5-8.5")
ISIMIP3B_MODEL_COUNT = 5
SEASONAL_FORECAST_SYSTEMS = ("GEOS-S2S-3", "NMME")

FUTURE_ENSEMBLE_CONTRACT = "future_climate_ensemble"
SEASONAL_FORECAST_CONTRACT = "seasonal_forecast_subset"
TIME_ZONE = "UTC"

EnsembleName = Literal["NEX-GDDP-CMIP6", "ISIMIP3b"]

DETAIL_FILL_VALUE = "the source gave its fill value for this entry"
DETAIL_NOT_IN_RESPONSE = "the response holds no value for this day"
DETAIL_NO_RANGE = "the source gives no uncertainty range for this series"

_QUANTITY_ID = re.compile(r"[a-z][a-z0-9_]*")
_SOURCE_PARAMETER = re.compile(r"[^\s,]+")
_SOURCE_DATE = re.compile(r"\d{8}")


# --- shared validation helpers ------------------------------------------------


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"setting {name!r} is required and must be non-empty text")
    return value


def _require_finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"setting {name!r} is required and must be a number")
    if not math.isfinite(value):
        raise ValueError(f"setting {name!r} must be a finite number")
    return float(value)


def _require_positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"setting {name!r} is required and must be an integer")
    if value <= 0:
        raise ValueError(f"setting {name!r} must be greater than zero")
    return value


def _require_https_url(value: Any, name: str) -> str:
    _require_text(value, name)
    url = httpx.URL(value)
    if url.scheme != "https" or not url.host or url.query or url.fragment:
        raise ValueError(
            f"setting {name!r} must be an https URL without query or fragment"
        )
    return value


def _require_code(value: Any, name: str) -> str:
    if value not in REASON_CODES:
        raise ValueError(
            f"setting {name!r} is required and must be a reason code of C3.2: "
            + ", ".join(REASON_CODES)
        )
    return value


def _require_future_provenance(value: Any, name: str) -> str:
    if value not in FUTURE_PROVENANCE_LABELS:
        raise ValueError(
            f"setting {name!r} is required and must be one of "
            + ", ".join(FUTURE_PROVENANCE_LABELS)
            + " (C4.1)"
        )
    return value


def _require_distinct_texts(
    values: Any, name: str, *, exact_count: int | None = None
) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError(f"setting {name!r} is required: at least one text entry")
    cleaned: list[str] = []
    for index, item in enumerate(values):
        cleaned.append(_require_text(item, f"{name}[{index}]"))
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"setting {name!r} contains duplicate entries")
    if exact_count is not None and len(cleaned) != exact_count:
        raise ValueError(f"setting {name!r} must contain exactly {exact_count} entries")
    return tuple(cleaned)


def _check_keys(document: Mapping[str, Any], expected: set[str], what: str) -> None:
    missing = sorted(expected - set(document))
    unknown = sorted(set(document) - expected)
    if missing:
        raise ValueError(f"{what}: missing setting(s) {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{what}: unknown setting(s) {', '.join(unknown)}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _parse_json(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- no-default settings (PROPOSED) -------------------------------------------


@dataclass(frozen=True, kw_only=True)
class FutureParameterSpec:
    """One requested future climate or seasonal forecast variable (PROPOSED)."""

    source_parameter: str
    quantity: str
    unit: str
    provenance: str

    def __post_init__(self) -> None:
        _require_text(self.source_parameter, "source_parameter")
        if not _SOURCE_PARAMETER.fullmatch(self.source_parameter):
            raise ValueError(
                "setting 'source_parameter' is one code, without spaces or commas"
            )
        if not isinstance(self.quantity, str) or not _QUANTITY_ID.fullmatch(
            self.quantity
        ):
            raise ValueError(
                "setting 'quantity' is required: lower case with underscores (C1.1)"
            )
        _require_text(self.unit, "unit")
        _require_future_provenance(self.provenance, "provenance")


def _validate_parameters(raw_parameters: Any) -> tuple[FutureParameterSpec, ...]:
    if not isinstance(raw_parameters, (tuple, list)) or not raw_parameters:
        raise ValueError(
            "setting 'parameters' is required: at least one FutureParameterSpec"
        )
    if not all(isinstance(spec, FutureParameterSpec) for spec in raw_parameters):
        raise ValueError("setting 'parameters' holds FutureParameterSpec items only")
    codes = [spec.source_parameter for spec in raw_parameters]
    quantities = [spec.quantity for spec in raw_parameters]
    if len(set(codes)) != len(codes):
        raise ValueError("setting 'parameters' names one source_parameter twice")
    if len(set(quantities)) != len(quantities):
        raise ValueError("setting 'parameters' names one quantity twice")
    return tuple(raw_parameters)


def _parse_parameter_specs(raw_parameters: Any) -> tuple[FutureParameterSpec, ...]:
    if not isinstance(raw_parameters, (list, tuple)):
        raise TypeError("setting 'parameters' is a list")
    spec_fields = {field.name for field in dataclasses.fields(FutureParameterSpec)}
    specs: list[FutureParameterSpec] = []
    for index, item in enumerate(raw_parameters):
        if not isinstance(item, Mapping):
            raise TypeError(f"setting 'parameters[{index}]' is a mapping")
        _check_keys(item, spec_fields, f"parameters[{index}]")
        specs.append(FutureParameterSpec(**item))
    return tuple(specs)


@dataclass(frozen=True, kw_only=True)
class FutureEnsembleSettings:
    """No-default settings for CMIP6/ISIMIP3b ensemble adapters (PROPOSED)."""

    base_url: str
    ensemble_name: str
    models: tuple[str, ...]
    scenarios: tuple[str, ...]
    parameters: tuple[FutureParameterSpec, ...]
    fill_value: float
    fill_reason: str
    range_missing_reason: str
    attribution: str
    source_id: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        _require_https_url(self.base_url, "base_url")
        _require_text(self.ensemble_name, "ensemble_name")
        object.__setattr__(
            self, "models", _require_distinct_texts(self.models, "models")
        )
        object.__setattr__(
            self, "scenarios", _require_distinct_texts(self.scenarios, "scenarios")
        )
        object.__setattr__(self, "parameters", _validate_parameters(self.parameters))
        object.__setattr__(
            self, "fill_value", _require_finite(self.fill_value, "fill_value")
        )
        _require_code(self.fill_reason, "fill_reason")
        _require_code(self.range_missing_reason, "range_missing_reason")
        _require_text(self.attribution, "attribution")
        _require_text(self.source_id, "source_id")
        timeout = _require_finite(self.timeout_seconds, "timeout_seconds")
        if timeout <= 0:
            raise ValueError("setting 'timeout_seconds' must be greater than zero")
        object.__setattr__(self, "timeout_seconds", timeout)

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> FutureEnsembleSettings:
        """Build settings from a mapping with exact key validation."""
        if not isinstance(document, Mapping):
            raise TypeError("settings are a mapping")
        expected = {field.name for field in dataclasses.fields(cls)}
        _check_keys(document, expected, "settings")
        values = dict(document)
        values["parameters"] = _parse_parameter_specs(document["parameters"])
        return cls(**values)


@dataclass(frozen=True, kw_only=True)
class SeasonalForecastSettings:
    """No-default settings for seasonal forecast subset adapters (PROPOSED)."""

    base_url: str
    forecast_system: str
    member_count: int
    lead_months: tuple[int, ...]
    tercile_labels: tuple[str, ...]
    parameters: tuple[FutureParameterSpec, ...]
    fill_value: float
    fill_reason: str
    range_missing_reason: str
    attribution: str
    source_id: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        _require_https_url(self.base_url, "base_url")
        _require_text(self.forecast_system, "forecast_system")
        object.__setattr__(
            self,
            "member_count",
            _require_positive_int(self.member_count, "member_count"),
        )
        if not isinstance(self.lead_months, (tuple, list)) or not self.lead_months:
            raise ValueError("setting 'lead_months' is required: at least one month")
        leads = [
            _require_positive_int(m, f"lead_months[{i}]")
            for i, m in enumerate(self.lead_months)
        ]
        if any(m > 12 for m in leads):
            raise ValueError("setting 'lead_months' entries must be between 1 and 12")
        if len(set(leads)) != len(leads):
            raise ValueError("setting 'lead_months' contains duplicate entries")
        object.__setattr__(self, "lead_months", tuple(leads))
        object.__setattr__(
            self,
            "tercile_labels",
            _require_distinct_texts(
                self.tercile_labels, "tercile_labels", exact_count=3
            ),
        )
        object.__setattr__(self, "parameters", _validate_parameters(self.parameters))
        object.__setattr__(
            self, "fill_value", _require_finite(self.fill_value, "fill_value")
        )
        _require_code(self.fill_reason, "fill_reason")
        _require_code(self.range_missing_reason, "range_missing_reason")
        _require_text(self.attribution, "attribution")
        _require_text(self.source_id, "source_id")
        timeout = _require_finite(self.timeout_seconds, "timeout_seconds")
        if timeout <= 0:
            raise ValueError("setting 'timeout_seconds' must be greater than zero")
        object.__setattr__(self, "timeout_seconds", timeout)

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> SeasonalForecastSettings:
        """Build settings from a mapping with exact key validation."""
        if not isinstance(document, Mapping):
            raise TypeError("settings are a mapping")
        expected = {field.name for field in dataclasses.fields(cls)}
        _check_keys(document, expected, "settings")
        values = dict(document)
        values["parameters"] = _parse_parameter_specs(document["parameters"])
        return cls(**values)


# --- requests -----------------------------------------------------------------


@dataclass(frozen=True)
class FutureClimateRequest:
    """Request for a future climate ensemble projection subset."""

    case_id: str
    field_id: str
    latitude: float
    longitude: float
    start_date: dt.date
    end_date: dt.date
    scenarios: tuple[str, ...] | None = None
    models: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SeasonalForecastRequest:
    """Request for a seasonal forecast tercile and member subset."""

    case_id: str
    field_id: str
    latitude: float
    longitude: float
    init_date: dt.date
    lead_months: tuple[int, ...] | None = None


def _check_common_location(
    case_id: Any, field_id: Any, latitude: Any, longitude: Any
) -> None:
    _require_text(case_id, "case_id")
    _require_text(field_id, "field_id")
    for name, limit in (("latitude", 90.0), ("longitude", 180.0)):
        value = latitude if name == "latitude" else longitude
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"request {name} is a number of decimal degrees")
        if not math.isfinite(value) or not -limit <= value <= limit:
            raise ValueError(f"request {name} is outside -{limit} to {limit}")


def _check_date(value: Any, name: str) -> None:
    if isinstance(value, dt.datetime) or not isinstance(value, dt.date):
        raise TypeError(f"request {name} is a date without a time")


def _resolve_subset(
    requested: tuple[str, ...] | None, configured: tuple[str, ...], name: str
) -> tuple[str, ...]:
    if requested is None:
        return configured
    if not isinstance(requested, (tuple, list)) or not requested:
        raise ValueError(f"request {name} must be non-empty when supplied")
    cleaned = tuple(
        _require_text(item, f"{name}[{i}]") for i, item in enumerate(requested)
    )
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"request {name} contains duplicates")
    unknown = sorted(set(cleaned) - set(configured))
    if unknown:
        raise ValueError(
            f"request {name} contains unconfigured entries: {', '.join(unknown)}"
        )
    return cleaned


def _check_ensemble_request(
    request: FutureClimateRequest | ClimateRequest, settings: FutureEnsembleSettings
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(request, (FutureClimateRequest, ClimateRequest)):
        raise TypeError(
            "get_projections takes a FutureClimateRequest or ClimateRequest"
        )
    _check_common_location(
        request.case_id, request.field_id, request.latitude, request.longitude
    )
    _check_date(request.start_date, "start_date")
    _check_date(request.end_date, "end_date")
    if request.end_date < request.start_date:
        raise ValueError("request end_date is before start_date")
    if isinstance(request, FutureClimateRequest):
        models = _resolve_subset(request.models, settings.models, "models")
        scenarios = _resolve_subset(request.scenarios, settings.scenarios, "scenarios")
    else:
        models = settings.models
        scenarios = settings.scenarios
    return models, scenarios


def _check_seasonal_request(
    request: SeasonalForecastRequest, settings: SeasonalForecastSettings
) -> tuple[int, ...]:
    if not isinstance(request, SeasonalForecastRequest):
        raise TypeError("get_forecast_subset takes a SeasonalForecastRequest")
    _check_common_location(
        request.case_id, request.field_id, request.latitude, request.longitude
    )
    _check_date(request.init_date, "init_date")
    if request.lead_months is None:
        return settings.lead_months
    if not isinstance(request.lead_months, (tuple, list)) or not request.lead_months:
        raise ValueError("request lead_months must be non-empty when supplied")
    leads = tuple(
        _require_positive_int(m, f"lead_months[{i}]")
        for i, m in enumerate(request.lead_months)
    )
    if len(set(leads)) != len(leads):
        raise ValueError("request lead_months contains duplicates")
    unknown = sorted(set(leads) - set(settings.lead_months))
    if unknown:
        raise ValueError(
            "request lead_months contains unconfigured months: "
            + ", ".join(str(m) for m in unknown)
        )
    return leads


# --- contract output models (PROPOSED) ----------------------------------------


class EnsembleModelRun(ContractModel):
    """One model-scenario-quantity daily series from a future ensemble (PROPOSED)."""

    ensemble_name: NonEmptyStr
    model_id: NonEmptyStr
    scenario: NonEmptyStr
    quantity: QuantityId
    unit: NonEmptyStr
    provenance: FutureProvenance
    source: NonEmptyStr
    range_missing: Missing
    time_zone: NonEmptyStr
    start_date: IsoDate
    end_date: IsoDate
    days: list[DailyValue]
    valid_for_normative_erosion: Literal[False] = False

    @model_validator(mode="after")
    def _consistent_days(self) -> EnsembleModelRun:
        if self.end_date < self.start_date:
            raise ValueError("run ends before it starts")
        expected = self.start_date
        for day in self.days:
            if day.date != expected:
                raise ValueError(
                    "every day from start_date to end_date must appear once in order"
                )
            expected += dt.timedelta(days=1)
        if expected != self.end_date + dt.timedelta(days=1):
            raise ValueError("run days stop before end_date")
        return self


class FutureEnsemblePayload(ContractModel):
    """Multi-model, multi-scenario ensemble payload (PROPOSED)."""

    contract: Literal["future_climate_ensemble"] = FUTURE_ENSEMBLE_CONTRACT
    example_data: bool = False
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    ensemble_name: NonEmptyStr
    valid_for_normative_erosion: Literal[False] = False
    runs: list[EnsembleModelRun]


@dataclass(frozen=True)
class FutureEnsembleResult:
    """Answer of a future climate ensemble source."""

    data: FutureEnsemblePayload | None
    source: SourceInfo


class TercileProbability(ContractModel):
    """Probability for one seasonal forecast tercile, or missing with reason."""

    label: NonEmptyStr
    probability: FiniteFloat | None
    missing: Missing | None = None

    @model_validator(mode="after")
    def _value_or_missing(self) -> TercileProbability:
        if self.probability is not None and self.missing is not None:
            raise ValueError("tercile holds a probability or a missing part, not both")
        if self.probability is None and self.missing is None:
            raise ValueError("missing tercile probability needs a missing reason")
        if self.probability is not None and not (0.0 <= self.probability <= 1.0):
            raise ValueError("tercile probability must be between 0.0 and 1.0")
        return self


class SeasonalMemberValue(ContractModel):
    """One ensemble member value of a seasonal forecast subset."""

    member_index: int = Field(ge=0)
    value: FiniteFloat | None
    missing: Missing | None = None

    @model_validator(mode="after")
    def _value_or_missing(self) -> SeasonalMemberValue:
        if self.value is not None and self.missing is not None:
            raise ValueError("member holds a value or a missing part, not both")
        if self.value is None and self.missing is None:
            raise ValueError("missing member value needs a missing reason")
        return self


class SeasonalLeadSubset(ContractModel):
    """One (quantity, lead_month) tercile and member subset (PROPOSED)."""

    forecast_system: NonEmptyStr
    init_date: IsoDate
    lead_month: int = Field(ge=1, le=12)
    quantity: QuantityId
    unit: NonEmptyStr
    provenance: FutureProvenance
    source: NonEmptyStr
    range_missing: Missing
    tercile_probabilities: list[TercileProbability]
    member_values: list[SeasonalMemberValue]
    valid_for_normative_erosion: Literal[False] = False


class SeasonalForecastPayload(ContractModel):
    """Seasonal forecast subset payload for GEOS-S2S-3 / NMME (PROPOSED)."""

    contract: Literal["seasonal_forecast_subset"] = SEASONAL_FORECAST_CONTRACT
    example_data: bool = False
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    forecast_system: NonEmptyStr
    init_date: IsoDate
    valid_for_normative_erosion: Literal[False] = False
    subsets: list[SeasonalLeadSubset]


@dataclass(frozen=True)
class SeasonalForecastResult:
    """Answer of a seasonal forecast subset source."""

    data: SeasonalForecastPayload | None
    source: SourceInfo


# --- comparison models & Rev13 ensemble comparison ----------------------------


class EnsembleCriterion(ContractModel):
    """Criterion evaluated per model within each ensemble separately (PROPOSED)."""

    name: NonEmptyStr
    quantity: QuantityId
    unit: NonEmptyStr
    scenario: NonEmptyStr | None = None
    statistic: Literal["mean", "max", "min", "sum"] = "mean"
    comparator: Literal[">", ">=", "<", "<="]
    threshold: FiniteFloat


class EnsembleModelOutcome(ContractModel):
    """Per-model metric value and criterion outcome inside one ensemble."""

    model_id: NonEmptyStr
    scenario: NonEmptyStr
    value: FiniteFloat | None
    agrees: bool | None = None
    missing: Missing | None = None

    @model_validator(mode="after")
    def _consistent(self) -> EnsembleModelOutcome:
        if self.value is None:
            if self.agrees is not None or self.missing is None:
                raise ValueError(
                    "missing model outcome requires missing and forbids agrees"
                )
        else:
            if self.agrees is None or self.missing is not None:
                raise ValueError(
                    "present model outcome requires agrees and forbids missing"
                )
        return self


class EnsembleSummary(ContractModel):
    """Strict per-ensemble summary: (agreeing_models, total_models, min_val, max_val)."""

    ensemble_name: EnsembleName
    scenario: NonEmptyStr | None
    quantity: QuantityId
    unit: NonEmptyStr
    agreeing_models: int = Field(ge=0)
    total_models: int = Field(ge=0)
    evaluated_models: int = Field(ge=0)
    min_val: FiniteFloat | None
    max_val: FiniteFloat | None
    missing: Missing | None = None
    model_outcomes: list[EnsembleModelOutcome]
    valid_for_normative_erosion: Literal[False] = False

    @model_validator(mode="after")
    def _consistent(self) -> EnsembleSummary:
        if self.evaluated_models > self.total_models:
            raise ValueError("evaluated_models cannot exceed total_models")
        if self.agreeing_models > self.evaluated_models:
            raise ValueError("agreeing_models cannot exceed evaluated_models")
        if self.evaluated_models == 0:
            if (
                self.min_val is not None
                or self.max_val is not None
                or self.missing is None
            ):
                raise ValueError(
                    "summary with zero evaluated models requires missing and null bounds"
                )
        else:
            if self.min_val is None or self.max_val is None or self.missing is not None:
                raise ValueError(
                    "summary with evaluated models requires min_val/max_val and null missing"
                )
            if self.min_val > self.max_val:
                raise ValueError("min_val cannot exceed max_val")
        return self


class EnsembleComparison(ContractModel):
    """Side-by-side ensemble comparison; never averaged across ensembles (Rev13)."""

    criterion_name: NonEmptyStr
    quantity: QuantityId
    unit: NonEmptyStr
    provenance: FutureProvenance
    nex_gddp_cmip6: EnsembleSummary
    isimip3b: EnsembleSummary
    cross_ensemble_averaged: Literal[False] = False
    valid_for_normative_erosion: Literal[False] = False


# --- mapping & typed error handling -------------------------------------------


class _TypedResponseFailure(ValueError):
    """Typed response failure; detail never echoes the raw response body."""

    def __init__(self, reason: ReasonCode, detail: str) -> None:
        super().__init__(detail)
        self.reason: ReasonCode = reason
        self.detail = detail


def _parse_source_date(text: Any) -> dt.date:
    if not isinstance(text, str) or not _SOURCE_DATE.fullmatch(text):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "a date key is not written YYYYMMDD"
        )
    try:
        return dt.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "a date key is not a calendar date"
        ) from None


def _is_error_payload(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and "runs" not in raw
        and "subsets" not in raw
        and isinstance(raw.get("messages"), list)
        and len(raw["messages"]) > 0
    )


def _check_response_envelope(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "the response is not a JSON object"
        )
    if _is_error_payload(raw):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            "the source answered with an error message instead of data",
        )
    if raw.get("coverage") is False or raw.get("status") == "no_coverage":
        raise _TypedResponseFailure(
            "NO_COVERAGE",
            "the source reports no coverage for the requested location or period",
        )


def _days_between(start: dt.date, end: dt.date) -> list[dt.date]:
    count = (end - start).days + 1
    return [start + dt.timedelta(days=offset) for offset in range(count)]


def _parse_daily_series(
    raw_series: Any,
    spec: FutureParameterSpec,
    days: list[dt.date],
    settings: FutureEnsembleSettings,
) -> list[dict[str, Any]]:
    if not isinstance(raw_series, dict):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            f"series for parameter {spec.source_parameter!r} is not an object",
        )
    parsed: dict[dt.date, float] = {}
    for key, val in raw_series.items():
        day = _parse_source_date(key)
        if not _is_number(val) or not math.isfinite(val):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                f"a value for parameter {spec.source_parameter!r} is not a finite number",
            )
        parsed[day] = float(val)

    items: list[dict[str, Any]] = []
    for day in days:
        val = parsed.get(day)
        if val is None:
            items.append(
                {
                    "date": day.isoformat(),
                    "value": None,
                    "missing": {
                        "reason": settings.fill_reason,
                        "detail": DETAIL_NOT_IN_RESPONSE,
                    },
                }
            )
        elif val == settings.fill_value:
            items.append(
                {
                    "date": day.isoformat(),
                    "value": None,
                    "missing": {
                        "reason": settings.fill_reason,
                        "detail": DETAIL_FILL_VALUE,
                    },
                }
            )
        else:
            items.append({"date": day.isoformat(), "value": val})
    return items


def _to_ensemble_payload(
    raw: Any,
    request: FutureClimateRequest | ClimateRequest,
    models: tuple[str, ...],
    scenarios: tuple[str, ...],
    settings: FutureEnsembleSettings,
) -> dict[str, Any]:
    _check_response_envelope(raw)
    response_ensemble = raw.get("ensemble")
    if response_ensemble is not None and response_ensemble != settings.ensemble_name:
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            "the response ensemble identifier does not match the configured ensemble",
        )
    raw_runs = raw.get("runs")
    if not isinstance(raw_runs, list):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "the response has no 'runs' list"
        )
    if not raw_runs:
        raise _TypedResponseFailure(
            "NO_COVERAGE",
            "the source returned no projection runs for the requested domain",
        )

    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in raw_runs:
        if not isinstance(entry, dict):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE", "a run entry in 'runs' is not an object"
            )
        model_id = entry.get("model")
        scenario = entry.get("scenario")
        params = entry.get("parameters")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or not isinstance(scenario, str)
            or not scenario.strip()
            or not isinstance(params, dict)
        ):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                "a run entry is missing valid model, scenario, or parameters",
            )
        key = (model_id, scenario)
        if key in indexed:
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                "the response contains duplicate model-scenario entries",
            )
        indexed[key] = params

    requested_pairs = [(m, s) for s in scenarios for m in models]
    if not any(pair in indexed for pair in requested_pairs):
        raise _TypedResponseFailure(
            "NO_COVERAGE",
            "the response covers none of the requested model-scenario pairs",
        )

    days = _days_between(request.start_date, request.end_date)
    run_docs: list[dict[str, Any]] = []
    for model_id, scenario in requested_pairs:
        if (model_id, scenario) not in indexed:
            raise _TypedResponseFailure(
                "MISSING_INPUT",
                f"missing required projection run for model {model_id!r} and scenario {scenario!r}",
            )
        params = indexed[(model_id, scenario)]
        for spec in settings.parameters:
            if (
                spec.source_parameter not in params
                or params[spec.source_parameter] is None
            ):
                raise _TypedResponseFailure(
                    "MISSING_INPUT",
                    f"missing required input parameter {spec.source_parameter!r} "
                    f"(quantity {spec.quantity!r}) for model {model_id!r}",
                )
            day_docs = _parse_daily_series(
                params[spec.source_parameter], spec, days, settings
            )
            run_docs.append(
                {
                    "ensemble_name": settings.ensemble_name,
                    "model_id": model_id,
                    "scenario": scenario,
                    "quantity": spec.quantity,
                    "unit": spec.unit,
                    "provenance": spec.provenance,
                    "source": settings.source_id,
                    "range_missing": {
                        "reason": settings.range_missing_reason,
                        "detail": DETAIL_NO_RANGE,
                    },
                    "time_zone": TIME_ZONE,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "days": day_docs,
                    "valid_for_normative_erosion": False,
                }
            )

    return {
        "contract": FUTURE_ENSEMBLE_CONTRACT,
        "example_data": False,
        "case_id": request.case_id,
        "field_id": request.field_id,
        "ensemble_name": settings.ensemble_name,
        "valid_for_normative_erosion": False,
        "runs": run_docs,
    }


def _to_seasonal_payload(
    raw: Any,
    request: SeasonalForecastRequest,
    lead_months: tuple[int, ...],
    settings: SeasonalForecastSettings,
) -> dict[str, Any]:
    _check_response_envelope(raw)
    system = raw.get("forecast_system")
    if system is not None and system != settings.forecast_system:
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            "the response forecast_system does not match the configured system",
        )
    init_str = raw.get("init_date")
    if init_str is not None and init_str != request.init_date.isoformat():
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            "the response init_date does not match the requested init_date",
        )
    raw_subsets = raw.get("subsets")
    if not isinstance(raw_subsets, list):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "the response has no 'subsets' list"
        )
    if not raw_subsets:
        raise _TypedResponseFailure(
            "NO_COVERAGE",
            "the source returned no seasonal subsets for the requested location or init_date",
        )

    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for entry in raw_subsets:
        if not isinstance(entry, dict):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE", "a subset entry in 'subsets' is not an object"
            )
        param = entry.get("parameter")
        lead = entry.get("lead_month")
        if (
            not isinstance(param, str)
            or not param.strip()
            or isinstance(lead, bool)
            or not isinstance(lead, int)
        ):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                "a subset entry is missing valid parameter or lead_month",
            )
        key = (param, lead)
        if key in indexed:
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                "the response contains duplicate parameter-lead_month subsets",
            )
        indexed[key] = entry

    requested_keys = [
        (spec.source_parameter, lead)
        for spec in settings.parameters
        for lead in lead_months
    ]
    if not any(key in indexed for key in requested_keys):
        raise _TypedResponseFailure(
            "NO_COVERAGE",
            "the response covers none of the requested seasonal parameter-lead subsets",
        )

    subset_docs: list[dict[str, Any]] = []
    for spec in settings.parameters:
        for lead in lead_months:
            key = (spec.source_parameter, lead)
            if key not in indexed:
                raise _TypedResponseFailure(
                    "MISSING_INPUT",
                    f"missing required seasonal subset for parameter "
                    f"{spec.source_parameter!r} at lead month {lead}",
                )
            entry = indexed[key]
            terciles = _parse_terciles(entry.get("tercile_probabilities"), settings)
            members = _parse_members(entry.get("member_values"), settings)
            subset_docs.append(
                {
                    "forecast_system": settings.forecast_system,
                    "init_date": request.init_date.isoformat(),
                    "lead_month": lead,
                    "quantity": spec.quantity,
                    "unit": spec.unit,
                    "provenance": spec.provenance,
                    "source": settings.source_id,
                    "range_missing": {
                        "reason": settings.range_missing_reason,
                        "detail": DETAIL_NO_RANGE,
                    },
                    "tercile_probabilities": terciles,
                    "member_values": members,
                    "valid_for_normative_erosion": False,
                }
            )

    return {
        "contract": SEASONAL_FORECAST_CONTRACT,
        "example_data": False,
        "case_id": request.case_id,
        "field_id": request.field_id,
        "forecast_system": settings.forecast_system,
        "init_date": request.init_date.isoformat(),
        "valid_for_normative_erosion": False,
        "subsets": subset_docs,
    }


def _parse_terciles(
    raw_terciles: Any, settings: SeasonalForecastSettings
) -> list[dict[str, Any]]:
    if not isinstance(raw_terciles, dict):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "tercile_probabilities is missing or not an object"
        )
    docs: list[dict[str, Any]] = []
    present_probs: list[float] = []
    for label in settings.tercile_labels:
        if label not in raw_terciles or raw_terciles[label] is None:
            raise _TypedResponseFailure(
                "MISSING_INPUT",
                f"missing required seasonal tercile probability {label!r}",
            )
        val = raw_terciles[label]
        if not _is_number(val) or not math.isfinite(val):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                f"tercile probability for {label!r} is not a finite number",
            )
        num = float(val)
        if num == settings.fill_value:
            docs.append(
                {
                    "label": label,
                    "probability": None,
                    "missing": {
                        "reason": settings.fill_reason,
                        "detail": DETAIL_FILL_VALUE,
                    },
                }
            )
        elif not 0.0 <= num <= 1.0:
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                f"tercile probability for {label!r} is outside [0.0, 1.0]",
            )
        else:
            present_probs.append(num)
            docs.append({"label": label, "probability": num})

    if len(present_probs) == len(settings.tercile_labels) and not math.isclose(
        sum(present_probs), 1.0, abs_tol=1e-4
    ):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "tercile probabilities do not sum to 1.0"
        )
    return docs


def _parse_members(
    raw_members: Any, settings: SeasonalForecastSettings
) -> list[dict[str, Any]]:
    if not isinstance(raw_members, list):
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE", "member_values is missing or not a list"
        )
    if len(raw_members) < settings.member_count:
        raise _TypedResponseFailure(
            "MISSING_INPUT",
            f"missing seasonal member_values: expected {settings.member_count} members",
        )
    if len(raw_members) > settings.member_count:
        raise _TypedResponseFailure(
            "SOURCE_UNAVAILABLE",
            "member_values length exceeds configured member_count",
        )
    docs: list[dict[str, Any]] = []
    for idx, val in enumerate(raw_members):
        if val is None:
            docs.append(
                {
                    "member_index": idx,
                    "value": None,
                    "missing": {
                        "reason": settings.fill_reason,
                        "detail": DETAIL_NOT_IN_RESPONSE,
                    },
                }
            )
            continue
        if not _is_number(val) or not math.isfinite(val):
            raise _TypedResponseFailure(
                "SOURCE_UNAVAILABLE",
                f"seasonal member value at index {idx} is not a finite number",
            )
        num = float(val)
        if num == settings.fill_value:
            docs.append(
                {
                    "member_index": idx,
                    "value": None,
                    "missing": {
                        "reason": settings.fill_reason,
                        "detail": DETAIL_FILL_VALUE,
                    },
                }
            )
        else:
            docs.append({"member_index": idx, "value": num})
    return docs


# --- HTTP + Cache adapter base ------------------------------------------------


class _CachedHttpSource:
    """Shared HTTP + first-response-wins cache mechanics for frontier adapters."""

    def __init__(
        self,
        *,
        source_id: str,
        contract: str,
        base_url: str,
        attribution: str,
        timeout_seconds: float,
        cache: ResponseCache,
        client: httpx.Client,
        now: Callable[[], dt.datetime],
    ) -> None:
        if cache is None or not callable(getattr(cache, "get", None)):
            raise TypeError(f"{type(self).__name__} needs a ResponseCache")
        if not isinstance(client, httpx.Client):
            raise TypeError(f"{type(self).__name__} needs an httpx.Client")
        self._source_id = source_id
        self._contract = contract
        self._base_url = base_url
        self._attribution = attribution
        self._timeout_seconds = timeout_seconds
        self._cache = cache
        self._client = client
        self._now = now

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def contract(self) -> str:
        return self._contract

    def _info(
        self,
        query: Mapping[str, str],
        state: SourceState,
        *,
        retrieved_at: dt.datetime | None = None,
        missing_reason: ReasonCode | None = None,
        detail: str | None = None,
    ) -> SourceInfo:
        return SourceInfo(
            id=self._source_id,
            contract=self._contract,
            state=state,
            retrieved_at=retrieved_at,
            time_zone=TIME_ZONE,
            request=MappingProxyType(dict(query)),
            attribution=self._attribution,
            missing_reason=missing_reason,
            detail=detail,
        )

    def _retrieved_now(self) -> dt.datetime:
        moment = self._now()
        if not isinstance(moment, dt.datetime) or moment.utcoffset() is None:
            raise ValueError("the clock returns a timezone-aware datetime")
        return moment.astimezone(dt.UTC)

    def _fetch_and_validate(
        self,
        query: Mapping[str, str],
        loader: Callable[[Any], Any],
    ) -> tuple[Any | None, SourceInfo]:
        key = cache_key(self._source_id, self._base_url, query)
        stored = self._cache.get(key)
        if stored is not None:
            try:
                data = loader(_parse_json(stored.body))
            except _TypedResponseFailure as err:
                return None, self._info(
                    query,
                    "unavailable",
                    missing_reason=err.reason,
                    detail=err.detail,
                )
            except ValueError:
                return None, self._info(
                    query,
                    "unavailable",
                    missing_reason="SOURCE_UNAVAILABLE",
                    detail="the stored first response cannot be read; it is kept and the source is not asked again",
                )
            return data, self._info(query, "cached", retrieved_at=stored.retrieved_at)

        try:
            response = self._client.get(
                self._base_url,
                params=list(query.items()),
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            return None, self._info(
                query,
                "unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
                detail="the source did not answer in time",
            )
        except httpx.TransportError:
            return None, self._info(
                query,
                "unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
                detail="the source could not be reached",
            )
        except httpx.HTTPError:
            return None, self._info(
                query,
                "unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
                detail="the request to the source failed",
            )
        retrieved_at = self._retrieved_now()

        if not response.is_success:
            return None, self._info(
                query,
                "unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
                detail=f"the source answered with HTTP status {response.status_code}",
            )
        try:
            body = response.text
            raw = _parse_json(body)
        except ValueError:
            return None, self._info(
                query,
                "unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
                detail="the response body is not JSON",
            )
        try:
            data = loader(raw)
        except _TypedResponseFailure as err:
            return None, self._info(
                query,
                "unavailable",
                missing_reason=err.reason,
                detail=err.detail,
            )

        entry = StoredResponse(body=body, query=query, retrieved_at=retrieved_at)
        try:
            kept = self._cache.put(key, entry)
        except OSError:
            return data, self._info(
                query,
                "fresh",
                retrieved_at=retrieved_at,
                detail="the response could not be stored; the next call asks the source again",
            )
        if kept is not entry:
            try:
                kept_data = loader(_parse_json(kept.body))
            except ValueError:
                kept_data = None
            if kept_data is not None:
                return kept_data, self._info(
                    query, "cached", retrieved_at=kept.retrieved_at
                )
        return data, self._info(query, "fresh", retrieved_at=kept.retrieved_at)


class _BaseFutureEnsembleSource(_CachedHttpSource):
    """Shared implementation for NEX-GDDP-CMIP6 and ISIMIP3b adapters."""

    _expected_ensemble: str

    def __init__(
        self,
        settings: FutureEnsembleSettings,
        cache: ResponseCache,
        client: httpx.Client,
        *,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not isinstance(settings, FutureEnsembleSettings):
            raise TypeError(f"{type(self).__name__} needs FutureEnsembleSettings")
        if settings.ensemble_name != self._expected_ensemble:
            raise ValueError(
                f"{type(self).__name__} requires ensemble_name={self._expected_ensemble!r}"
            )
        super().__init__(
            source_id=settings.source_id,
            contract=FUTURE_ENSEMBLE_CONTRACT,
            base_url=settings.base_url,
            attribution=settings.attribution,
            timeout_seconds=settings.timeout_seconds,
            cache=cache,
            client=client,
            now=now,
        )
        self._settings = settings

    @property
    def ensemble_name(self) -> str:
        return self._settings.ensemble_name

    def _build_query(
        self,
        request: FutureClimateRequest | ClimateRequest,
        models: tuple[str, ...],
        scenarios: tuple[str, ...],
    ) -> dict[str, str]:
        return {
            "ensemble": self._settings.ensemble_name,
            "models": ",".join(sorted(models)),
            "scenarios": ",".join(sorted(scenarios)),
            "parameters": ",".join(
                sorted(spec.source_parameter for spec in self._settings.parameters)
            ),
            "latitude": repr(float(request.latitude)),
            "longitude": repr(float(request.longitude)),
            "start": request.start_date.strftime("%Y%m%d"),
            "end": request.end_date.strftime("%Y%m%d"),
            "format": "JSON",
            "time_standard": TIME_ZONE,
        }

    def get_projections(
        self, request: FutureClimateRequest | ClimateRequest
    ) -> FutureEnsembleResult:
        models, scenarios = _check_ensemble_request(request, self._settings)
        query = self._build_query(request, models, scenarios)

        def _load(raw: Any) -> FutureEnsemblePayload:
            document = _to_ensemble_payload(
                raw, request, models, scenarios, self._settings
            )
            try:
                return FutureEnsemblePayload.model_validate(document)
            except ValidationError:
                raise _TypedResponseFailure(
                    "SOURCE_UNAVAILABLE",
                    "the mapped document does not load into FutureEnsemblePayload",
                ) from None

        data, source = self._fetch_and_validate(query, _load)
        return FutureEnsembleResult(data=data, source=source)


class NexGddpCmip6Source(_BaseFutureEnsembleSource):
    """NEX-GDDP-CMIP6 downscaled daily climate scenarios adapter (PROPOSED)."""

    _expected_ensemble = NEX_GDDP_ENSEMBLE_NAME


class Isimip3bSource(_BaseFutureEnsembleSource):
    """ISIMIP3b 5-model CMIP6 bias-adjusted contrast scenarios adapter (PROPOSED)."""

    _expected_ensemble = ISIMIP3B_ENSEMBLE_NAME


class SeasonalForecastSubsetSource(_CachedHttpSource):
    """GEOS-S2S-3 / NMME seasonal tercile & member subset adapter (PROPOSED)."""

    def __init__(
        self,
        settings: SeasonalForecastSettings,
        cache: ResponseCache,
        client: httpx.Client,
        *,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not isinstance(settings, SeasonalForecastSettings):
            raise TypeError(
                "SeasonalForecastSubsetSource needs SeasonalForecastSettings"
            )
        super().__init__(
            source_id=settings.source_id,
            contract=SEASONAL_FORECAST_CONTRACT,
            base_url=settings.base_url,
            attribution=settings.attribution,
            timeout_seconds=settings.timeout_seconds,
            cache=cache,
            client=client,
            now=now,
        )
        self._settings = settings

    @property
    def forecast_system(self) -> str:
        return self._settings.forecast_system

    def _build_query(
        self, request: SeasonalForecastRequest, lead_months: tuple[int, ...]
    ) -> dict[str, str]:
        return {
            "system": self._settings.forecast_system,
            "init_date": request.init_date.strftime("%Y%m%d"),
            "lead_months": ",".join(str(m) for m in sorted(lead_months)),
            "member_count": str(self._settings.member_count),
            "parameters": ",".join(
                sorted(spec.source_parameter for spec in self._settings.parameters)
            ),
            "latitude": repr(float(request.latitude)),
            "longitude": repr(float(request.longitude)),
            "format": "JSON",
            "time_standard": TIME_ZONE,
        }

    def get_forecast_subset(
        self, request: SeasonalForecastRequest
    ) -> SeasonalForecastResult:
        lead_months = _check_seasonal_request(request, self._settings)
        query = self._build_query(request, lead_months)

        def _load(raw: Any) -> SeasonalForecastPayload:
            document = _to_seasonal_payload(raw, request, lead_months, self._settings)
            try:
                return SeasonalForecastPayload.model_validate(document)
            except ValidationError:
                raise _TypedResponseFailure(
                    "SOURCE_UNAVAILABLE",
                    "the mapped document does not load into SeasonalForecastPayload",
                ) from None

        data, source = self._fetch_and_validate(query, _load)
        return SeasonalForecastResult(data=data, source=source)


# --- Rev13 strict ensemble comparison -----------------------------------------


def _aggregate_run(
    run: EnsembleModelRun, statistic: Literal["mean", "max", "min", "sum"]
) -> tuple[float | None, Missing | None]:
    if not run.days:
        return None, Missing(
            reason="NO_COVERAGE",
            detail=f"model {run.model_id!r} has no days in series",
        )
    values: list[float] = []
    for day in run.days:
        if day.value is None:
            return None, Missing(
                reason="MISSING_INPUT",
                detail=f"missing day {day.date.isoformat()} in model {run.model_id!r}",
            )
        values.append(float(day.value))
    if statistic == "mean":
        return sum(values) / len(values), None
    if statistic == "max":
        return max(values), None
    if statistic == "min":
        return min(values), None
    return sum(values), None


def _matches_criterion(
    value: float, comparator: Literal[">", ">=", "<", "<="], threshold: float
) -> bool:
    if comparator == ">":
        return value > threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == "<":
        return value < threshold
    return value <= threshold


def _summarize_ensemble(
    runs: Sequence[EnsembleModelRun],
    expected_ensemble: EnsembleName,
    criterion: EnsembleCriterion,
) -> EnsembleSummary:
    matching: list[EnsembleModelRun] = []
    for run in runs:
        if not isinstance(run, EnsembleModelRun):
            raise TypeError("ensemble runs must be EnsembleModelRun instances")
        if run.ensemble_name != expected_ensemble:
            raise ValueError(
                f"expected runs for {expected_ensemble!r}, got {run.ensemble_name!r}"
            )
        if run.quantity != criterion.quantity:
            continue
        if criterion.scenario is not None and run.scenario != criterion.scenario:
            continue
        if run.unit != criterion.unit:
            raise ValueError(
                f"unit mismatch for {expected_ensemble!r} model {run.model_id!r}: "
                f"expected {criterion.unit!r}, got {run.unit!r}"
            )
        matching.append(run)

    seen_keys: set[tuple[str, str]] = set()
    for run in matching:
        key = (run.model_id, run.scenario)
        if key in seen_keys:
            raise ValueError(f"duplicate model run in {expected_ensemble!r}: {key!r}")
        seen_keys.add(key)

    scenarios = {run.scenario for run in matching}
    if criterion.scenario is None and len(scenarios) > 1:
        raise ValueError(
            f"{expected_ensemble!r} mixes multiple scenarios without criterion.scenario filter"
        )
    resolved_scenario = (
        criterion.scenario
        if criterion.scenario is not None
        else (next(iter(scenarios)) if scenarios else None)
    )

    if not matching:
        return EnsembleSummary(
            ensemble_name=expected_ensemble,
            scenario=resolved_scenario,
            quantity=criterion.quantity,
            unit=criterion.unit,
            agreeing_models=0,
            total_models=0,
            evaluated_models=0,
            min_val=None,
            max_val=None,
            missing=Missing(
                reason="NO_COVERAGE",
                detail=f"no runs available in {expected_ensemble!r} for quantity {criterion.quantity!r}",
            ),
            model_outcomes=[],
            valid_for_normative_erosion=False,
        )

    outcomes: list[EnsembleModelOutcome] = []
    valid_vals: list[float] = []
    agreeing = 0
    for run in matching:
        val, missing = _aggregate_run(run, criterion.statistic)
        if val is None:
            outcomes.append(
                EnsembleModelOutcome(
                    model_id=run.model_id,
                    scenario=run.scenario,
                    value=None,
                    agrees=None,
                    missing=missing,
                )
            )
        else:
            agrees = _matches_criterion(val, criterion.comparator, criterion.threshold)
            if agrees:
                agreeing += 1
            valid_vals.append(val)
            outcomes.append(
                EnsembleModelOutcome(
                    model_id=run.model_id,
                    scenario=run.scenario,
                    value=val,
                    agrees=agrees,
                    missing=None,
                )
            )

    if not valid_vals:
        return EnsembleSummary(
            ensemble_name=expected_ensemble,
            scenario=resolved_scenario,
            quantity=criterion.quantity,
            unit=criterion.unit,
            agreeing_models=0,
            total_models=len(matching),
            evaluated_models=0,
            min_val=None,
            max_val=None,
            missing=Missing(
                reason="MISSING_INPUT",
                detail=f"all {len(matching)} model(s) in {expected_ensemble!r} had missing values",
            ),
            model_outcomes=outcomes,
            valid_for_normative_erosion=False,
        )

    return EnsembleSummary(
        ensemble_name=expected_ensemble,
        scenario=resolved_scenario,
        quantity=criterion.quantity,
        unit=criterion.unit,
        agreeing_models=agreeing,
        total_models=len(matching),
        evaluated_models=len(valid_vals),
        min_val=min(valid_vals),
        max_val=max(valid_vals),
        missing=None,
        model_outcomes=outcomes,
        valid_for_normative_erosion=False,
    )


def compare_climate_ensembles(
    nex_runs: Iterable[EnsembleModelRun],
    isimip_runs: Iterable[EnsembleModelRun],
    criterion: EnsembleCriterion,
) -> EnsembleComparison:
    """Compare NEX-GDDP-CMIP6 and ISIMIP3b ensembles strictly separately (Rev13).

    Reports ``(agreeing_models, total_models, min_val, max_val)`` per ensemble
    without ever averaging across ensembles (``cross_ensemble_averaged=False``),
    and enforces ``valid_for_normative_erosion=False`` on the output.
    """
    if not isinstance(criterion, EnsembleCriterion):
        raise TypeError("compare_climate_ensembles requires an EnsembleCriterion")
    nex_list = list(nex_runs)
    isimip_list = list(isimip_runs)
    nex_summary = _summarize_ensemble(nex_list, NEX_GDDP_ENSEMBLE_NAME, criterion)
    isimip_summary = _summarize_ensemble(isimip_list, ISIMIP3B_ENSEMBLE_NAME, criterion)

    all_matching = [
        r
        for r in (*nex_list, *isimip_list)
        if r.quantity == criterion.quantity
        and (criterion.scenario is None or r.scenario == criterion.scenario)
    ]
    provenance: FutureProvenance = (
        "SIMULATED"
        if any(r.provenance == "SIMULATED" for r in all_matching) or not all_matching
        else "DERIVED"
    )

    return EnsembleComparison(
        criterion_name=criterion.name,
        quantity=criterion.quantity,
        unit=criterion.unit,
        provenance=provenance,
        nex_gddp_cmip6=nex_summary,
        isimip3b=isimip_summary,
        cross_ensemble_averaged=False,
        valid_for_normative_erosion=False,
    )
