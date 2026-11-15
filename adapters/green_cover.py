"""Green-cover strip adapter (Landsat/Sentinel-2 HLS or MODIS). PROPOSED (blueprint 3.7).

Platform adapter half for Blueprint Section 8 Gated Extra #2 ("Green-cover strip
from Landsat and Sentinel-2 (HLS) or MODIS"). Until the gate opens and settings
are supplied by the science reviewers and platform developer, the product uses
``UnconfiguredGreenCoverSource``, which makes no network calls and returns a
typed ``Missing(reason="NOT_AVAILABLE", ...)``.

Target ``contracts/green_cover`` schema alignment (developed concurrently in a
separate contracts unit; not imported here yet so this module passes standalone
on ``b107d7a``):
- ``GreenCoverObservation`` mirrors the planned ``contracts.green_cover``
  observation model using ``contracts.inputs.common.ContractModel``, ``IsoDate``,
  ``QuantityId``, ``NonEmptyStr``, ``Provenance``, ``Missing``, and
  ``check_source_or_assumption`` (C3.1, C4.1, C4.2, C5.2).
- ``GreenCoverStrip`` mirrors the planned ``contracts.green_cover`` strip model
  with ``contract == "green_cover_strip"``, ``case_id``, ``field_id``,
  ``example_data``, ``time_zone == "UTC"`` (C6.1), UTC date-ordered
  ``observations``, ``strip_missing``, and ``sources``.
Once ``contracts.green_cover`` lands on ``main``, wiring only requires swapping
the local DTO models for imports from ``contracts.green_cover``.

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
from typing import Any, Literal, Protocol, Self, get_args

import httpx
from pydantic import Field, FiniteFloat, ValidationError, model_validator

from adapters.cache import ResponseCache, StoredResponse, cache_key
from adapters.ports import SourceInfo, SourceState
from contracts.inputs.common import (
    ContractModel,
    IsoDate,
    Missing,
    NonEmptyStr,
    Provenance,
    QuantityId,
    ReasonCode,
    check_source_or_assumption,
)

CONTRACT = "green_cover_strip"
TIME_ZONE = "UTC"  # C6.1: UTC date-ordered observations

PROVENANCE_LABELS = get_args(Provenance)
REASON_CODES = get_args(ReasonCode)

UNAVAILABLE_REASON: ReasonCode = "SOURCE_UNAVAILABLE"
NOT_AVAILABLE_REASON: ReasonCode = "NOT_AVAILABLE"
CLOUD_MASKED_REASON: ReasonCode = "MISSING_INPUT"
NO_COVERAGE_REASON: ReasonCode = "NO_COVERAGE"

UNCONFIGURED_SOURCE_ID = "green_cover_unconfigured"
UNCONFIGURED_DETAIL = "green-cover strip adapter is not configured (Section 8 gate)"

DETAIL_FILL_VALUE = "the source gave its fill value for this green-cover observation"
DETAIL_VALUE_NULL = "the source reported null for this green-cover observation"
DETAIL_CLOUD_MASKED = "green-cover observation is cloud-masked"
DETAIL_CLOUD_FRACTION_FILL = (
    "the source gave its fill value for observation cloud fraction"
)
DETAIL_NO_OBSERVATIONS = (
    "the source returned no observations for the requested UTC date window"
)

_QUANTITY_ID = re.compile(r"[a-z][a-z0-9_]*")  # C1.1
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class UnusableResponse(ValueError):
    """The response does not have the expected layout. Never echoes the body."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"setting {name!r} is required and must be non-empty text")
    return value


def _require_finite(value: Any, name: str) -> float:
    if not _is_number(value):
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


def _check_keys(document: Mapping[str, Any], expected: set[str], what: str) -> None:
    missing = sorted(expected - set(document))
    unknown = sorted(set(document) - expected)
    if missing:
        raise ValueError(f"{what}: missing setting(s) {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{what}: unknown setting(s) {', '.join(unknown)}")


@dataclass(frozen=True, kw_only=True)
class GreenCoverSettings:
    """Strict configuration for the HLS/MODIS green-cover adapter. No defaults (G5)."""

    endpoint: str
    collection: str
    quantity: str
    unit: str
    provenance: str
    fill_value: float
    fill_reason: str
    attribution: str
    source_id: str
    timeout_s: float

    def __post_init__(self) -> None:
        _require_text(self.endpoint, "endpoint")
        try:
            url = httpx.URL(self.endpoint)
        except httpx.InvalidURL:
            raise ValueError(
                "setting 'endpoint' is an https URL without query or fragment"
            ) from None
        if url.scheme != "https" or not url.host or url.query or url.fragment:
            raise ValueError(
                "setting 'endpoint' is an https URL without query or fragment"
            )

        _require_text(self.collection, "collection")
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
        object.__setattr__(
            self, "fill_value", _require_finite(self.fill_value, "fill_value")
        )
        _require_code(self.fill_reason, "fill_reason")
        _require_text(self.attribution, "attribution")
        _require_text(self.source_id, "source_id")
        timeout = _require_finite(self.timeout_s, "timeout_s")
        if timeout <= 0:
            raise ValueError("setting 'timeout_s' must be greater than zero")
        object.__setattr__(self, "timeout_s", timeout)

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> GreenCoverSettings:
        """Build settings from configuration; missing or unknown keys raise ValueError."""
        if not isinstance(document, Mapping):
            raise TypeError("settings are a mapping")
        expected = {field.name for field in dataclasses.fields(cls)}
        _check_keys(document, expected, "settings")
        return cls(**dict(document))


@dataclass(frozen=True)
class GreenCoverRequest:
    """What a caller requests: one field of one case, one point, one UTC date window."""

    case_id: str
    field_id: str
    latitude: float
    longitude: float
    start_date: dt.date
    end_date: dt.date


class GreenCoverObservation(ContractModel):
    """One UTC-dated vegetation index or cover observation, or a typed Missing."""

    date: IsoDate
    quantity: QuantityId
    unit: NonEmptyStr
    value: FiniteFloat | None
    missing: Missing | None = None
    provenance: Provenance | None = None
    source: NonEmptyStr | None = None
    sensor_source: NonEmptyStr
    cloud_fraction: FiniteFloat | None = None
    cloud_fraction_missing: Missing | None = None

    @model_validator(mode="after")
    def _validate_observation(self) -> Self:
        present = self.value is not None
        if present and self.missing is not None:
            raise ValueError(
                "value: an observation holds a value or a missing part, never both (C3.1)"
            )
        if not present and self.missing is None:
            raise ValueError(
                "value: a missing observation carries a missing part with its reason (C3.1)"
            )
        check_source_or_assumption(
            present=present,
            provenance=self.provenance,
            source=self.source,
            assumption=False,
            what="observation",
        )
        if self.cloud_fraction is not None and self.cloud_fraction_missing is not None:
            raise ValueError(
                "cloud_fraction: holds a value or cloud_fraction_missing, never both"
            )
        if self.cloud_fraction is not None and not 0.0 <= self.cloud_fraction <= 1.0:
            raise ValueError("cloud_fraction must be between 0.0 and 1.0")
        return self


class GreenCoverStrip(ContractModel):
    """UTC date-ordered strip of green-cover observations for one field."""

    contract: Literal["green_cover_strip"] = "green_cover_strip"
    example_data: bool = False
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    time_zone: NonEmptyStr = TIME_ZONE
    observations: list[GreenCoverObservation]
    strip_missing: Missing | None = None
    sources: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_strip(self) -> Self:
        if self.strip_missing is not None and self.observations:
            raise ValueError(
                "green_cover_strip: a missing strip must not carry observations"
            )
        if self.strip_missing is None and not self.observations:
            raise ValueError(
                "green_cover_strip: an empty strip must carry strip_missing"
            )
        keys = [
            (obs.date, obs.sensor_source, obs.quantity) for obs in self.observations
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "green_cover_strip: duplicate observation for date, sensor_source, and quantity"
            )
        order_keys = [(obs.date, obs.sensor_source) for obs in self.observations]
        if order_keys != sorted(order_keys):
            raise ValueError(
                "green_cover_strip: observations must be ordered by UTC date and sensor_source"
            )
        return self


@dataclass(frozen=True)
class GreenCoverResult:
    """Answer of a green-cover source: data or typed Missing, plus SourceInfo."""

    data: GreenCoverStrip | None
    source: SourceInfo
    missing: Missing | None = None

    def __post_init__(self) -> None:
        if self.data is None:
            if self.missing is None:
                raise ValueError(
                    "GreenCoverResult: data is None so missing must be provided"
                )
            if self.source.state != "unavailable":
                raise ValueError(
                    "GreenCoverResult: data is None so source.state must be 'unavailable'"
                )
            if self.missing.reason != self.source.missing_reason:
                raise ValueError(
                    "GreenCoverResult: missing.reason must match source.missing_reason"
                )
        else:
            if self.missing is not None:
                raise ValueError(
                    "GreenCoverResult: missing must be None when data is present"
                )
            if self.source.state == "unavailable":
                raise ValueError(
                    "GreenCoverResult: source.state cannot be 'unavailable' when data is present"
                )


class GreenCoverSource(Protocol):
    """Anything that can supply a field's green-cover strip."""

    @property
    def source_id(self) -> str: ...

    @property
    def contract(self) -> str: ...

    def get_green_cover(self, request: GreenCoverRequest) -> GreenCoverResult: ...


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _format_coordinate(value: float) -> str:
    return repr(float(value))


def _check_request(request: GreenCoverRequest) -> None:
    """A request that cannot be valid is a programming error of the caller."""
    if not isinstance(request, GreenCoverRequest):
        raise TypeError("get_green_cover takes a GreenCoverRequest")
    for name in ("case_id", "field_id"):
        _require_text(getattr(request, name), name)
    for name, limit in (("latitude", 90.0), ("longitude", 180.0)):
        value = getattr(request, name)
        if not _is_number(value):
            raise TypeError(f"request {name} is a number of decimal degrees")
        if not math.isfinite(value) or not -limit <= value <= limit:
            raise ValueError(f"request {name} is outside -{limit} to {limit}")
    for name in ("start_date", "end_date"):
        value = getattr(request, name)
        if isinstance(value, dt.datetime) or not isinstance(value, dt.date):
            raise TypeError(f"request {name} is a date without a time")
    if request.end_date < request.start_date:
        raise ValueError("request end_date is before start_date")


def build_query(
    request: GreenCoverRequest, settings: GreenCoverSettings
) -> dict[str, str]:
    """Build deterministic query parameters for the HLS/MODIS point request."""
    _check_request(request)
    return {
        "collection": settings.collection,
        "latitude": _format_coordinate(request.latitude),
        "longitude": _format_coordinate(request.longitude),
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "quantity": settings.quantity,
    }


def _parse_utc_date(value: Any) -> dt.date:
    """Parse strict ``YYYY-MM-DD`` or timezone-aware ISO datetime into a UTC date."""
    if not isinstance(value, str) or not value.strip():
        raise UnusableResponse("an observation date is not a non-empty string")
    if _ISO_DATE.fullmatch(value):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            raise UnusableResponse(
                "an observation date is not a calendar date"
            ) from None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        raise UnusableResponse(
            "an observation date is neither YYYY-MM-DD nor an ISO-8601 timestamp"
        ) from None
    if parsed.utcoffset() is None:
        raise UnusableResponse("an observation timestamp has no time zone")
    return parsed.astimezone(dt.UTC).date()


def _parse_observation(
    item: Any, settings: GreenCoverSettings
) -> tuple[dt.date, dict[str, Any]]:
    if not isinstance(item, dict):
        raise UnusableResponse("an observation item is not a JSON object")
    if "date" not in item:
        raise UnusableResponse("an observation item has no 'date'")
    obs_date = _parse_utc_date(item["date"])

    sensor = item.get("sensor", settings.collection)
    if not isinstance(sensor, str) or not sensor.strip():
        raise UnusableResponse("an observation 'sensor' is not non-empty text")

    cloud_masked = item.get("cloud_masked", False)
    if not isinstance(cloud_masked, bool):
        raise UnusableResponse("an observation 'cloud_masked' flag is not a boolean")

    cloud_fraction_raw = item.get("cloud_fraction")
    cloud_fraction: float | None = None
    cloud_fraction_missing: dict[str, Any] | None = None
    if cloud_fraction_raw is not None:
        if not _is_number(cloud_fraction_raw) or not math.isfinite(cloud_fraction_raw):
            raise UnusableResponse(
                "an observation 'cloud_fraction' is not a finite number"
            )
        if float(cloud_fraction_raw) == settings.fill_value:
            cloud_fraction_missing = {
                "reason": settings.fill_reason,
                "detail": DETAIL_CLOUD_FRACTION_FILL,
            }
        else:
            cloud_fraction = float(cloud_fraction_raw)
            if not 0.0 <= cloud_fraction <= 1.0:
                raise UnusableResponse(
                    "an observation 'cloud_fraction' is outside 0.0 to 1.0"
                )

    if "value" not in item:
        raise UnusableResponse("an observation item has no 'value'")
    raw_value = item["value"]
    if raw_value is not None and (
        not _is_number(raw_value) or not math.isfinite(raw_value)
    ):
        raise UnusableResponse("an observation 'value' is not a finite number or null")

    entry: dict[str, Any] = {
        "date": obs_date.isoformat(),
        "quantity": settings.quantity,
        "unit": settings.unit,
        "sensor_source": sensor,
        "cloud_fraction": cloud_fraction,
        "cloud_fraction_missing": cloud_fraction_missing,
    }
    if cloud_masked:
        entry["value"] = None
        entry["missing"] = {
            "reason": CLOUD_MASKED_REASON,
            "detail": DETAIL_CLOUD_MASKED,
        }
    elif raw_value is None:
        entry["value"] = None
        entry["missing"] = {
            "reason": settings.fill_reason,
            "detail": DETAIL_VALUE_NULL,
        }
    elif float(raw_value) == settings.fill_value:
        entry["value"] = None
        entry["missing"] = {
            "reason": settings.fill_reason,
            "detail": DETAIL_FILL_VALUE,
        }
    else:
        entry["value"] = float(raw_value)
        entry["provenance"] = settings.provenance
        entry["source"] = settings.source_id
    return obs_date, entry


def to_green_cover_strip(
    raw: Any, request: GreenCoverRequest, settings: GreenCoverSettings
) -> dict[str, Any]:
    """Pure mapper: parsed HLS/MODIS JSON -> ``GreenCoverStrip`` document.

    Raises ``UnusableResponse`` on structural or value-type errors without
    echoing response contents. Observations are filtered to
    ``[request.start_date, request.end_date]`` and sorted in UTC date order.
    Fill values and cloud-masked observations map to typed ``Missing`` entries
    (never ``0``), while real ``0.0`` values remain ``0.0``.
    """
    _check_request(request)
    if not isinstance(raw, dict):
        raise UnusableResponse("the response is not a JSON object")

    if "collection" in raw:
        collection = raw["collection"]
        if not isinstance(collection, str) or collection != settings.collection:
            raise UnusableResponse(
                "the response collection does not match the configured collection"
            )

    if "fill_value" in raw and raw["fill_value"] is not None:
        declared_fill = raw["fill_value"]
        if not _is_number(declared_fill) or float(declared_fill) != settings.fill_value:
            raise UnusableResponse(
                "the response declares a fill value other than the configured one"
            )

    raw_observations = raw.get("observations")
    if not isinstance(raw_observations, list):
        raise UnusableResponse("the response has no 'observations' list")

    parsed: list[tuple[dt.date, str, dict[str, Any]]] = []
    seen_keys: set[tuple[dt.date, str]] = set()
    for item in raw_observations:
        obs_date, entry = _parse_observation(item, settings)
        if not request.start_date <= obs_date <= request.end_date:
            continue
        key = (obs_date, entry["sensor_source"])
        if key in seen_keys:
            raise UnusableResponse(
                "the response contains duplicate observations for the same UTC date and sensor"
            )
        seen_keys.add(key)
        parsed.append((obs_date, entry["sensor_source"], entry))

    parsed.sort(key=lambda row: (row[0], row[1]))
    observations = [row[2] for row in parsed]

    if observations:
        strip_missing = None
        sources = [settings.source_id]
    else:
        strip_missing = {
            "reason": NO_COVERAGE_REASON,
            "detail": DETAIL_NO_OBSERVATIONS,
        }
        sources = []

    return {
        "contract": CONTRACT,
        "example_data": False,
        "case_id": request.case_id,
        "field_id": request.field_id,
        "time_zone": TIME_ZONE,
        "observations": observations,
        "strip_missing": strip_missing,
        "sources": sources,
    }


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _parse_json(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant)


class UnconfiguredGreenCoverSource:
    """Default Section 8 gated source: makes no network calls and returns NOT_AVAILABLE."""

    def __init__(self, *, source_id: str = UNCONFIGURED_SOURCE_ID) -> None:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must be non-empty text")
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def contract(self) -> str:
        return CONTRACT

    def get_green_cover(self, request: GreenCoverRequest) -> GreenCoverResult:
        _check_request(request)
        missing = Missing(reason=NOT_AVAILABLE_REASON, detail=UNCONFIGURED_DETAIL)
        return GreenCoverResult(
            data=None,
            missing=missing,
            source=SourceInfo(
                id=self._source_id,
                contract=CONTRACT,
                state="unavailable",
                time_zone=TIME_ZONE,
                missing_reason=NOT_AVAILABLE_REASON,
                detail=UNCONFIGURED_DETAIL,
            ),
        )


class HlsModisGreenCoverSource:
    """HLS/MODIS green-cover strip adapter, cached on its first usable response."""

    def __init__(
        self,
        settings: GreenCoverSettings,
        cache: ResponseCache,
        client: httpx.Client,
        *,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not isinstance(settings, GreenCoverSettings):
            raise TypeError("HlsModisGreenCoverSource needs GreenCoverSettings")
        if cache is None or not callable(getattr(cache, "get", None)):
            raise TypeError("HlsModisGreenCoverSource needs a ResponseCache")
        if not isinstance(client, httpx.Client):
            raise TypeError("HlsModisGreenCoverSource needs an httpx.Client")
        self._settings = settings
        self._cache = cache
        self._client = client
        self._now = now

    @property
    def source_id(self) -> str:
        return self._settings.source_id

    @property
    def contract(self) -> str:
        return CONTRACT

    def _load(self, raw: Any, request: GreenCoverRequest) -> GreenCoverStrip:
        document = to_green_cover_strip(raw, request, self._settings)
        try:
            return GreenCoverStrip.model_validate(document)
        except ValidationError:
            raise UnusableResponse(
                "the mapped document does not load into GreenCoverStrip"
            ) from None

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

    def _unavailable(
        self,
        query: Mapping[str, str],
        detail: str,
        *,
        reason: ReasonCode = UNAVAILABLE_REASON,
    ) -> GreenCoverResult:
        return GreenCoverResult(
            data=None,
            missing=Missing(reason=reason, detail=detail),
            source=self._info(
                query,
                "unavailable",
                missing_reason=reason,
                detail=detail,
            ),
        )

    def _retrieved_now(self) -> dt.datetime:
        moment = self._now()
        if not isinstance(moment, dt.datetime) or moment.utcoffset() is None:
            raise ValueError("the clock returns a timezone-aware datetime")
        return moment.astimezone(dt.UTC)

    def get_green_cover(self, request: GreenCoverRequest) -> GreenCoverResult:
        settings = self._settings
        query = build_query(request, settings)
        key = cache_key(settings.source_id, settings.endpoint, query)

        stored = self._cache.get(key)
        if stored is not None:
            try:
                data = self._load(_parse_json(stored.body), request)
            except ValueError:
                return self._unavailable(
                    query,
                    "the stored first response of this request cannot be read as "
                    "green-cover data; it is kept and the source is not asked again",
                )
            return GreenCoverResult(
                data=data,
                source=self._info(query, "cached", retrieved_at=stored.retrieved_at),
            )

        try:
            response = self._client.get(
                settings.endpoint,
                params=list(query.items()),
                timeout=settings.timeout_s,
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
            return self._unavailable(
                query, f"the response does not have the expected layout: {error}"
            )

        entry = StoredResponse(body=body, query=query, retrieved_at=retrieved_at)
        try:
            kept = self._cache.put(key, entry)
        except OSError:
            return GreenCoverResult(
                data=data,
                source=self._info(
                    query,
                    "fresh",
                    retrieved_at=retrieved_at,
                    detail=(
                        "the response could not be stored; the next call asks the "
                        "source again"
                    ),
                ),
            )
        if kept is not entry:
            try:
                kept_data = self._load(_parse_json(kept.body), request)
            except ValueError:
                kept_data = None
            if kept_data is not None:
                return GreenCoverResult(
                    data=kept_data,
                    source=self._info(query, "cached", retrieved_at=kept.retrieved_at),
                )
        return GreenCoverResult(
            data=data,
            source=self._info(query, "fresh", retrieved_at=kept.retrieved_at),
        )
