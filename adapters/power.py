"""NASA POWER daily point adapter: implements ``adapters.ports.ClimateSource``.

Every decision that belongs to a person is a field of ``PowerSettings`` with no
default: endpoint, community, the parameter list with quantity, unit and
provenance of each, the fill value and the reason codes, the attribution, the
source identifier and the timeout. See README.md for who decides each one.

The facts about the service used here come from the scout report (issue 15):
the query arguments, ``time-standard=UTC`` to request UTC, ``format=JSON`` and
the JSON response layout. The time standard is not a setting: series from this
adapter are UTC (contracts/CONVENTIONS.md C6.2).

Network calls happen only through the injected ``httpx.Client``; tests pass a
client built on ``httpx.MockTransport``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.cache import ResponseCache, StoredResponse, cache_key
from adapters.ports import ClimateRequest, ClimateResult, SourceInfo, SourceState
from adapters.power_mapping import (
    CONTRACT,
    TIME_ZONE,
    UnusableResponse,
    to_site_climate,
)
from contracts.inputs import SiteClimate

# contracts/CONVENTIONS.md C4.1, copied so the adapter does not depend on an
# unmerged contract module.
PROVENANCE_LABELS = ("DECLARED", "OBSERVED", "DERIVED", "SIMULATED")
# contracts/CONVENTIONS.md C3.2, the closed list of reason codes.
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

# The reason a failed fetch becomes. PROPOSED for an error payload (README).
UNAVAILABLE_REASON = "SOURCE_UNAVAILABLE"

# Optional arguments of the daily point endpoint that a person may choose to
# send (scout report, section 1). ``user`` is not among them: the adapter never
# sends an identifier. The arguments the adapter builds itself cannot be set.
ALLOWED_OPTIONAL_ARGUMENTS = frozenset(
    {"units", "site-elevation", "wind-elevation", "wind-surface"}
)

_QUANTITY_ID = re.compile(r"[a-z][a-z0-9_]*")  # C1.1
_SOURCE_PARAMETER = re.compile(r"[^\s,]+")  # one code; the list is comma-separated


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


def _require_code(value: Any, name: str) -> str:
    if value not in REASON_CODES:
        raise ValueError(
            f"setting {name!r} is required and must be a reason code of C3.2: "
            + ", ".join(REASON_CODES)
        )
    return value


@dataclass(frozen=True, kw_only=True)
class ParameterSpec:
    """One requested variable: the source's code and how the contract names it."""

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
        if self.provenance not in PROVENANCE_LABELS:
            raise ValueError(
                "setting 'provenance' is required and must be one of "
                + ", ".join(PROVENANCE_LABELS)
                + " (C4.1)"
            )


@dataclass(frozen=True, kw_only=True)
class PowerSettings:
    """Everything a person decides for this adapter. No field has a default."""

    base_url: str
    community: str
    parameters: tuple[ParameterSpec, ...]
    optional_arguments: Mapping[str, str]  # may be empty: send none of them
    fill_value: float
    fill_reason: str
    range_missing_reason: str
    attribution: str
    source_id: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        _require_text(self.base_url, "base_url")
        url = httpx.URL(self.base_url)
        if url.scheme != "https" or not url.host or url.query or url.fragment:
            raise ValueError(
                "setting 'base_url' is an https URL without query or fragment"
            )
        _require_text(self.community, "community")

        if not isinstance(self.parameters, (tuple, list)) or not self.parameters:
            raise ValueError(
                "setting 'parameters' is required: at least one ParameterSpec"
            )
        if not all(isinstance(spec, ParameterSpec) for spec in self.parameters):
            raise ValueError("setting 'parameters' holds ParameterSpec items only")
        codes = [spec.source_parameter for spec in self.parameters]
        quantities = [spec.quantity for spec in self.parameters]
        if len(set(codes)) != len(codes):
            raise ValueError("setting 'parameters' names one source parameter twice")
        if len(set(quantities)) != len(quantities):
            raise ValueError("setting 'parameters' names one quantity twice")
        object.__setattr__(self, "parameters", tuple(self.parameters))

        if not isinstance(self.optional_arguments, Mapping):
            raise TypeError(
                "setting 'optional_arguments' is required: a mapping, empty to send none"
            )
        for name, value in self.optional_arguments.items():
            if name not in ALLOWED_OPTIONAL_ARGUMENTS:
                raise ValueError(
                    f"setting 'optional_arguments' cannot set {name!r}; allowed: "
                    + ", ".join(sorted(ALLOWED_OPTIONAL_ARGUMENTS))
                )
            _require_text(value, f"optional_arguments[{name!r}]")
        object.__setattr__(
            self,
            "optional_arguments",
            MappingProxyType(dict(sorted(self.optional_arguments.items()))),
        )

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
    def from_mapping(cls, document: Mapping[str, Any]) -> PowerSettings:
        """Build settings from configuration, for example a parsed JSON file.

        ``parameters`` is a list of mappings with the fields of ``ParameterSpec``.
        Unknown or missing keys are an error naming them.
        """
        if not isinstance(document, Mapping):
            raise TypeError("settings are a mapping")
        expected = {field.name for field in dataclasses.fields(cls)}
        _check_keys(document, expected, "settings")
        raw_parameters = document["parameters"]
        if not isinstance(raw_parameters, (list, tuple)):
            raise TypeError("setting 'parameters' is a list")
        spec_fields = {field.name for field in dataclasses.fields(ParameterSpec)}
        parameters = []
        for index, item in enumerate(raw_parameters):
            if not isinstance(item, Mapping):
                raise TypeError(f"setting 'parameters[{index}]' is a mapping")
            _check_keys(item, spec_fields, f"parameters[{index}]")
            parameters.append(ParameterSpec(**item))
        values = dict(document)
        values["parameters"] = tuple(parameters)
        return cls(**values)


def _check_keys(document: Mapping[str, Any], expected: set[str], what: str) -> None:
    missing = sorted(expected - set(document))
    unknown = sorted(set(document) - expected)
    if missing:
        raise ValueError(f"{what}: missing setting(s) {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{what}: unknown setting(s) {', '.join(unknown)}")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _format_coordinate(value: float) -> str:
    return repr(float(value))


def _check_request(request: ClimateRequest) -> None:
    """A request that cannot be valid is a programming error of the caller."""
    if not isinstance(request, ClimateRequest):
        raise TypeError("get_climate takes a ClimateRequest")
    for name in ("case_id", "field_id"):
        _require_text(getattr(request, name), name)
    for name, limit in (("latitude", 90.0), ("longitude", 180.0)):
        value = getattr(request, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"request {name} is a number of decimal degrees")
        if not math.isfinite(value) or not -limit <= value <= limit:
            raise ValueError(f"request {name} is outside -{limit} to {limit}")
    for name in ("start_date", "end_date"):
        value = getattr(request, name)
        if isinstance(value, dt.datetime) or not isinstance(value, dt.date):
            raise TypeError(f"request {name} is a date without a time")
    if request.end_date < request.start_date:
        raise ValueError("request end_date is before start_date")


def build_query(request: ClimateRequest, settings: PowerSettings) -> dict[str, str]:
    """The query sent to the service. Same inputs, same query, in a fixed order.

    The parameter codes are sorted, so the order in which they are configured
    does not change the query or the cache key.
    """
    _check_request(request)
    query = {
        "parameters": ",".join(
            sorted(spec.source_parameter for spec in settings.parameters)
        ),
        "community": settings.community,
        "latitude": _format_coordinate(request.latitude),
        "longitude": _format_coordinate(request.longitude),
        "start": request.start_date.strftime("%Y%m%d"),
        "end": request.end_date.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    query.update(settings.optional_arguments)
    return query


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _parse_json(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant)


class PowerClimateSource:
    """Daily climate of one point from NASA POWER, cached on its first response."""

    def __init__(
        self,
        settings: PowerSettings,
        cache: ResponseCache,
        client: httpx.Client,
        *,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not isinstance(settings, PowerSettings):
            raise TypeError("PowerClimateSource needs PowerSettings")
        if cache is None or not callable(getattr(cache, "get", None)):
            raise TypeError("PowerClimateSource needs a ResponseCache")
        if not isinstance(client, httpx.Client):
            raise TypeError("PowerClimateSource needs an httpx.Client")
        self._settings = settings
        self._cache = cache
        self._client = client
        self._now = now

    @property
    def source_id(self) -> str:
        """The ``SourceInfo.id`` this source writes: the ``source_id`` setting."""
        return self._settings.source_id

    @property
    def contract(self) -> str:
        """The ``SourceInfo.contract`` this source writes."""
        return CONTRACT

    def _load(self, raw: Any, request: ClimateRequest) -> SiteClimate:
        """Map a parsed response and load it into the contract model.

        Raises ``UnusableResponse`` when the response cannot be mapped or the
        mapped document does not load. The text never echoes the response.
        """
        document = to_site_climate(raw, request, self._settings)
        try:
            return SiteClimate.model_validate(document)
        except ValidationError:
            raise UnusableResponse(
                "the mapped document does not load into the contract model SiteClimate"
            ) from None

    def _info(
        self,
        query: Mapping[str, str],
        state: SourceState,
        *,
        retrieved_at: dt.datetime | None = None,
        missing_reason: str | None = None,
        detail: str | None = None,
    ) -> SourceInfo:
        return SourceInfo(
            id=self._settings.source_id,
            contract=CONTRACT,
            state=state,
            retrieved_at=retrieved_at,
            time_zone=TIME_ZONE,
            request=MappingProxyType(dict(query)),
            attribution=self._settings.attribution,
            missing_reason=missing_reason,
            detail=detail,
        )

    def _unavailable(self, query: Mapping[str, str], detail: str) -> ClimateResult:
        return ClimateResult(
            data=None,
            source=self._info(
                query,
                "unavailable",
                missing_reason=UNAVAILABLE_REASON,
                detail=detail,
            ),
        )

    def _retrieved_now(self) -> dt.datetime:
        moment = self._now()
        if not isinstance(moment, dt.datetime) or moment.utcoffset() is None:
            raise ValueError("the clock returns a timezone-aware datetime")
        return moment.astimezone(dt.UTC)

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        settings = self._settings
        query = build_query(request, settings)
        key = cache_key(settings.source_id, settings.base_url, query)

        stored = self._cache.get(key)
        if stored is not None:
            try:
                data = self._load(_parse_json(stored.body), request)
            except ValueError:
                return self._unavailable(
                    query,
                    "the stored first response of this request cannot be read as "
                    "climate data; it is kept and the source is not asked again",
                )
            return ClimateResult(
                data=data,
                source=self._info(query, "cached", retrieved_at=stored.retrieved_at),
            )

        try:
            response = self._client.get(
                settings.base_url,
                params=list(query.items()),
                timeout=settings.timeout_seconds,
            )
        except httpx.TimeoutException:
            return self._unavailable(query, "the source did not answer in time")
        except httpx.TransportError:
            return self._unavailable(query, "the source could not be reached")
        except httpx.HTTPError:
            return self._unavailable(query, "the request to the source failed")
        retrieved_at = self._retrieved_now()

        if not response.is_success:
            return self._unavailable(
                query, f"the source answered with HTTP status {response.status_code}"
            )
        try:
            body = response.text
            raw = _parse_json(body)
        except ValueError:
            return self._unavailable(query, "the response body is not JSON")
        try:
            data = self._load(raw, request)
        except UnusableResponse as error:
            if _is_error_payload(raw):
                return self._unavailable(
                    query, "the source answered with an error message instead of data"
                )
            return self._unavailable(
                query, f"the response does not have the expected layout: {error}"
            )

        entry = StoredResponse(body=body, query=query, retrieved_at=retrieved_at)
        try:
            kept = self._cache.put(key, entry)
        except OSError:
            return ClimateResult(
                data=data,
                source=self._info(
                    query,
                    "fresh",
                    retrieved_at=retrieved_at,
                    detail="the response could not be stored; the next call asks the source again",
                ),
            )
        if kept is not entry:
            # Another writer stored a first response meanwhile: that one wins.
            try:
                kept_data = self._load(_parse_json(kept.body), request)
            except ValueError:
                kept_data = None
            if kept_data is not None:
                return ClimateResult(
                    data=kept_data,
                    source=self._info(query, "cached", retrieved_at=kept.retrieved_at),
                )
        return ClimateResult(
            data=data,
            source=self._info(query, "fresh", retrieved_at=kept.retrieved_at),
        )


def _is_error_payload(raw: Any) -> bool:
    """A JSON object with no data and a non-empty ``messages`` list. PROPOSED."""
    return (
        isinstance(raw, dict)
        and "properties" not in raw
        and isinstance(raw.get("messages"), list)
        and len(raw["messages"]) > 0
    )
