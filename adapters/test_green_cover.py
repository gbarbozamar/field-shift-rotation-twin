"""Acceptance tests for the green-cover strip adapter (Section 8 gated extra).

No network calls: the service is an ``httpx.MockTransport``, the cache lives in
``tmp_path``, endpoints use ``.invalid``, and all dates are in the year 1900.
Run with ``uv run pytest adapters/test_green_cover.py``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any, Protocol, runtime_checkable

import httpx
import pytest
from pydantic import ValidationError

from adapters.cache import FileCache
from adapters.green_cover import (
    CONTRACT,
    UNCONFIGURED_DETAIL,
    UNCONFIGURED_SOURCE_ID,
    GreenCoverObservation,
    GreenCoverRequest,
    GreenCoverResult,
    GreenCoverSettings,
    GreenCoverSource,
    GreenCoverStrip,
    HlsModisGreenCoverSource,
    UnconfiguredGreenCoverSource,
    UnusableResponse,
    to_green_cover_strip,
)
from adapters.ports import SourceInfo
from contracts.inputs.common import Missing

FIRST = dt.datetime(1900, 2, 1, 6, 0, tzinfo=dt.UTC)
LATER = dt.datetime(1900, 3, 1, 6, 0, tzinfo=dt.UTC)
PLACEHOLDER_FILL = -9999.0


class Clock:
    def __init__(self, *moments: dt.datetime) -> None:
        self._moments = list(moments)

    def __call__(self) -> dt.datetime:
        return self._moments.pop(0) if len(self._moments) > 1 else self._moments[0]


class FakeService:
    """Records HTTP requests and delegates responses to a test handler."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def settings_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "endpoint": "https://green-cover.invalid/v1/observations",
        "collection": "PLACEHOLDER_HLS_L30",
        "quantity": "placeholder_ndvi",
        "unit": "dimensionless",
        "provenance": "OBSERVED",
        "fill_value": PLACEHOLDER_FILL,
        "fill_reason": "MISSING_INPUT",
        "attribution": "PLACEHOLDER_attribution",
        "source_id": "placeholder_green_cover",
        "timeout_s": 2.0,
    }
    fields.update(overrides)
    return fields


def make_settings(**overrides: Any) -> GreenCoverSettings:
    return GreenCoverSettings(**settings_fields(**overrides))


def make_request(
    start: dt.date = dt.date(1900, 1, 1),
    end: dt.date = dt.date(1900, 1, 10),
    **overrides: Any,
) -> GreenCoverRequest:
    fields: dict[str, Any] = {
        "case_id": "placeholder_case",
        "field_id": "placeholder_field",
        "latitude": -34.33,
        "longitude": -57.68,
        "start_date": start,
        "end_date": end,
    }
    fields.update(overrides)
    return GreenCoverRequest(**fields)


def mock_document(
    observations: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "collection": "PLACEHOLDER_HLS_L30",
        "fill_value": PLACEHOLDER_FILL,
        "observations": observations
        if observations is not None
        else [
            {
                "date": "1900-01-05",
                "value": 0.72,
                "sensor": "PLACEHOLDER_HLS_S30",
                "cloud_masked": False,
                "cloud_fraction": 0.05,
            },
            {
                "date": "1900-01-01",
                "value": 0.61,
                "sensor": "PLACEHOLDER_HLS_L30",
                "cloud_masked": False,
                "cloud_fraction": 0.1,
            },
        ],
    }
    doc.update(overrides)
    return doc


def answer_with(document: dict[str, Any]) -> Any:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    return handler


def build(
    tmp_path: Any,
    handler: Any,
    *,
    clock: Any = None,
    settings: GreenCoverSettings | None = None,
) -> tuple[HlsModisGreenCoverSource, FakeService, Any]:
    service = FakeService(handler)
    client = httpx.Client(transport=httpx.MockTransport(service))
    cache_folder = tmp_path / "cache"
    source = HlsModisGreenCoverSource(
        settings or make_settings(),
        FileCache(cache_folder),
        client,
        now=clock or Clock(FIRST, LATER),
    )
    return source, service, cache_folder


def stored_files(folder: Any) -> list[Any]:
    return sorted(folder.iterdir()) if folder.exists() else []


REQUEST = make_request()
DOCUMENT = mock_document()


@runtime_checkable
class CheckableGreenCoverSource(GreenCoverSource, Protocol):
    """Runtime-checkable copy of the green-cover adapter protocol."""


# --- Unconfigured (Section 8 gate) --------------------------------------------


def test_unconfigured_source_returns_not_available_without_network(monkeypatch):
    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network call must never occur when unconfigured")

    monkeypatch.setattr(httpx.Client, "send", fail_network)
    source = UnconfiguredGreenCoverSource()
    assert isinstance(source, CheckableGreenCoverSource)
    assert source.source_id == UNCONFIGURED_SOURCE_ID
    assert source.contract == CONTRACT

    result = source.get_green_cover(REQUEST)
    assert isinstance(result, GreenCoverResult)
    assert result.data is None
    assert result.missing == Missing(
        reason="NOT_AVAILABLE",
        detail=UNCONFIGURED_DETAIL,
    )
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NOT_AVAILABLE"
    assert result.source.detail == UNCONFIGURED_DETAIL
    assert result.source.retrieved_at is None
    assert result.source.time_zone == "UTC"


def test_unconfigured_source_rejects_blank_source_id():
    with pytest.raises(ValueError, match="source_id"):
        UnconfiguredGreenCoverSource(source_id="   ")


# --- GreenCoverSettings strict validation (G5) --------------------------------


def test_settings_have_no_defaults():
    for field in dataclasses.fields(GreenCoverSettings):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name


@pytest.mark.parametrize("name", sorted(settings_fields()))
def test_missing_setting_is_an_error_naming_it(name: str):
    fields = settings_fields()
    del fields[name]
    with pytest.raises(TypeError, match=name):
        GreenCoverSettings(**fields)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("endpoint", ""),
        ("endpoint", "   "),
        ("endpoint", "http://green-cover.invalid/v1/observations"),
        ("endpoint", "https://green-cover.invalid/v1/observations?q=1"),
        ("endpoint", "https://green-cover.invalid/v1/observations#frag"),
        ("endpoint", "not a url"),
        ("collection", ""),
        ("collection", "   "),
        ("quantity", ""),
        ("quantity", "NDVI"),
        ("quantity", "1bad"),
        ("unit", ""),
        ("unit", "   "),
        ("provenance", ""),
        ("provenance", "observed"),
        ("provenance", "ESTIMATED"),
        ("fill_value", float("nan")),
        ("fill_value", float("inf")),
        ("fill_value", float("-inf")),
        ("fill_reason", ""),
        ("fill_reason", "INVALID_REASON"),
        ("attribution", ""),
        ("attribution", "   "),
        ("source_id", ""),
        ("source_id", "   "),
        ("timeout_s", 0),
        ("timeout_s", -1.5),
        ("timeout_s", float("nan")),
        ("timeout_s", float("inf")),
    ],
)
def test_invalid_setting_raises_value_error_naming_it(name: str, value: Any):
    with pytest.raises(ValueError, match=name):
        make_settings(**{name: value})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("fill_value", None),
        ("fill_value", True),
        ("fill_value", "-9999"),
        ("timeout_s", None),
        ("timeout_s", True),
        ("timeout_s", "2.0"),
    ],
)
def test_wrong_type_setting_raises_type_error_naming_it(name: str, value: Any):
    with pytest.raises(TypeError, match=name):
        make_settings(**{name: value})


def test_settings_from_mapping_round_trip_and_rejects_missing_or_unknown():
    raw = settings_fields()
    assert GreenCoverSettings.from_mapping(raw) == make_settings()

    missing = dict(raw)
    del missing["collection"]
    with pytest.raises(ValueError, match="collection"):
        GreenCoverSettings.from_mapping(missing)

    unknown = dict(raw, extra_field="unexpected")
    with pytest.raises(ValueError, match="extra_field"):
        GreenCoverSettings.from_mapping(unknown)

    with pytest.raises(TypeError):
        GreenCoverSettings.from_mapping(["not", "a", "mapping"])  # type: ignore[arg-type]


# --- Valid fetch, UTC date ordering, and caching ------------------------------


def test_valid_fetch_orders_observations_by_utc_date_and_stores_cache(tmp_path):
    doc = mock_document(
        [
            {
                "date": "1900-01-05T14:00:00Z",
                "value": 0.72,
                "sensor": "PLACEHOLDER_HLS_S30",
                "cloud_masked": False,
                "cloud_fraction": 0.05,
            },
            {
                # -03:00 at 22:30 converts to 1900-01-03T01:30:00Z in UTC!
                "date": "1900-01-02T22:30:00-03:00",
                "value": 0.0,
                "sensor": "PLACEHOLDER_MODIS",
                "cloud_masked": False,
            },
            {
                "date": "1900-01-01",
                "value": 0.55,
                "sensor": "PLACEHOLDER_HLS_L30",
            },
            {
                # Outside requested window [1900-01-01, 1900-01-10] -> filtered out
                "date": "1900-01-12",
                "value": 0.88,
                "sensor": "PLACEHOLDER_HLS_L30",
            },
        ]
    )
    source, service, folder = build(tmp_path, answer_with(doc))
    assert isinstance(source, CheckableGreenCoverSource)
    assert source.source_id == "placeholder_green_cover"
    assert source.contract == CONTRACT
    assert service.requests == []

    result = source.get_green_cover(REQUEST)
    assert len(service.requests) == 1
    assert result.missing is None
    assert result.source.state == "fresh"
    assert result.source.retrieved_at == FIRST
    assert result.source.time_zone == "UTC"
    assert result.source.missing_reason is None
    assert len(stored_files(folder)) == 1

    assert isinstance(result.data, GreenCoverStrip)
    assert result.data.contract == "green_cover_strip"
    assert result.data.time_zone == "UTC"
    assert result.data.strip_missing is None
    assert [obs.date for obs in result.data.observations] == [
        dt.date(1900, 1, 1),
        dt.date(1900, 1, 3),
        dt.date(1900, 1, 5),
    ]
    # Real zero stays 0.0, never converted to Missing
    assert result.data.observations[1].value == 0.0
    assert result.data.observations[1].missing is None
    assert result.data.observations[1].provenance == "OBSERVED"
    assert result.data.observations[1].source == "placeholder_green_cover"


def test_second_identical_call_uses_cache_and_shares_across_instances(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    first = source.get_green_cover(REQUEST)
    second = source.get_green_cover(REQUEST)
    assert len(service.requests) == 1
    assert second.source.state == "cached"
    assert second.source.retrieved_at == first.source.retrieved_at == FIRST
    assert second.data == first.data

    other, other_service, _ = build(tmp_path, answer_with(DOCUMENT))
    third = other.get_green_cover(REQUEST)
    assert other_service.requests == []
    assert third.source.state == "cached"
    assert third.data == first.data


def test_distinct_request_misses_cache(tmp_path):
    source, service, folder = build(tmp_path, answer_with(DOCUMENT))
    source.get_green_cover(REQUEST)
    source.get_green_cover(make_request(latitude=-34.5))
    assert len(service.requests) == 2
    assert len(stored_files(folder)) == 2


def test_source_down_with_cache_serves_cached_entry(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    first = source.get_green_cover(REQUEST)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    service.handler = down
    second = source.get_green_cover(REQUEST)
    assert second.source.state == "cached"
    assert second.data == first.data
    assert second.source.retrieved_at == FIRST


# --- Fill values and cloud masking -> MISSING_INPUT (never 0) -----------------


def test_fill_value_and_cloud_masked_map_to_missing_input_never_zero(tmp_path):
    doc = mock_document(
        [
            {
                "date": "1900-01-01",
                "value": PLACEHOLDER_FILL,
                "sensor": "PLACEHOLDER_HLS_L30",
                "cloud_masked": False,
                "cloud_fraction": PLACEHOLDER_FILL,
            },
            {
                "date": "1900-01-02",
                "value": -9999,
                "sensor": "PLACEHOLDER_HLS_L30",
                "cloud_masked": False,
            },
            {
                "date": "1900-01-03",
                "value": 0.48,  # contaminated pixel behind cloud mask must NOT leak
                "sensor": "PLACEHOLDER_HLS_S30",
                "cloud_masked": True,
                "cloud_fraction": 0.92,
            },
            {
                "date": "1900-01-04",
                "value": None,
                "sensor": "PLACEHOLDER_MODIS",
                "cloud_masked": False,
            },
            {
                "date": "1900-01-05",
                "value": 0.0,  # real zero stays 0.0
                "sensor": "PLACEHOLDER_MODIS",
                "cloud_masked": False,
            },
        ]
    )
    source, _, _ = build(tmp_path, answer_with(doc))
    result = source.get_green_cover(REQUEST)
    assert result.data is not None
    obs = result.data.observations
    assert len(obs) == 5

    for idx in (0, 1, 2, 3):
        assert obs[idx].value is None
        assert obs[idx].value != 0
        assert obs[idx].missing is not None
        assert obs[idx].missing.reason == "MISSING_INPUT"
        assert obs[idx].missing.detail
        assert obs[idx].provenance is None
        assert obs[idx].source is None

    assert obs[0].cloud_fraction is None
    assert obs[0].cloud_fraction_missing is not None
    assert obs[0].cloud_fraction_missing.reason == "MISSING_INPUT"
    assert "cloud-masked" in (obs[2].missing.detail or "")
    assert obs[4].value == 0.0
    assert obs[4].missing is None
    assert obs[4].provenance == "OBSERVED"


def test_empty_observations_yields_strip_missing_no_coverage(tmp_path):
    source, _, _ = build(tmp_path, answer_with(mock_document([])))
    result = source.get_green_cover(REQUEST)
    assert result.source.state == "fresh"
    assert result.data is not None
    assert result.data.observations == []
    assert result.data.strip_missing is not None
    assert result.data.strip_missing.reason == "NO_COVERAGE"


# --- HTTP / Timeout / Malformed errors -> SOURCE_UNAVAILABLE (no body echo) ---


def _raise(exception_type: type[Exception]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if issubclass(exception_type, httpx.RequestError):
            raise exception_type("PLACEHOLDER_SECRET_BODY", request=request)
        raise exception_type("PLACEHOLDER_SECRET_BODY")

    return handler


def _status(code: int, **kwargs: Any) -> Any:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, **kwargs)

    return handler


FAILURES = {
    "read-timeout": _raise(httpx.ReadTimeout),
    "connect-timeout": _raise(httpx.ConnectTimeout),
    "connection-error": _raise(httpx.ConnectError),
    "http-error": _raise(httpx.HTTPError),
    "status-500": _status(500, json={"error": "PLACEHOLDER_SECRET_BODY"}),
    "status-404": _status(404, text="PLACEHOLDER_SECRET_BODY"),
    "status-422": _status(422, json={"detail": ["PLACEHOLDER_SECRET_BODY"]}),
    "status-429": _status(429, text="PLACEHOLDER_SECRET_BODY"),
    "status-503": _status(503, text="PLACEHOLDER_SECRET_BODY"),
    "status-302": _status(302, text="PLACEHOLDER_SECRET_BODY"),
    "body-not-json": _status(200, text="<html>PLACEHOLDER_SECRET_BODY</html>"),
    "body-json-nan": _status(200, text='{"observations": NaN}'),
    "body-json-infinity": _status(200, text='{"observations": Infinity}'),
    "json-not-object": _status(200, json=["PLACEHOLDER_SECRET_BODY"]),
    "missing-observations": _status(200, json={"PLACEHOLDER_SECRET_BODY": 1}),
    "observations-not-list": _status(
        200, json={"observations": "PLACEHOLDER_SECRET_BODY"}
    ),
    "collection-mismatch": _status(
        200, json=mock_document([], collection="PLACEHOLDER_SECRET_BODY")
    ),
    "fill-value-mismatch": _status(200, json=mock_document([], fill_value=-1.0)),
    "observation-not-object": _status(
        200, json=mock_document(["PLACEHOLDER_SECRET_BODY"])
    ),
    "observation-missing-date": _status(
        200, json=mock_document([{"value": 0.5, "sensor": "PLACEHOLDER_SECRET_BODY"}])
    ),
    "observation-naive-timestamp": _status(
        200, json=mock_document([{"date": "1900-01-01T12:00:00", "value": 0.5}])
    ),
    "observation-bad-date": _status(
        200, json=mock_document([{"date": "PLACEHOLDER_SECRET_BODY", "value": 0.5}])
    ),
    "observation-bad-value-type": _status(
        200,
        json=mock_document(
            [{"date": "1900-01-01", "value": "PLACEHOLDER_SECRET_BODY"}]
        ),
    ),
    "observation-bool-value": _status(
        200, json=mock_document([{"date": "1900-01-01", "value": True}])
    ),
    "observation-bad-cloud-masked": _status(
        200,
        json=mock_document(
            [{"date": "1900-01-01", "value": 0.5, "cloud_masked": "yes"}]
        ),
    ),
    "observation-cloud-fraction-out-of-range": _status(
        200,
        json=mock_document(
            [{"date": "1900-01-01", "value": 0.5, "cloud_fraction": 1.2}]
        ),
    ),
    "observation-duplicate-date-sensor": _status(
        200,
        json=mock_document(
            [
                {"date": "1900-01-01", "value": 0.5, "sensor": "PLACEHOLDER_HLS_L30"},
                {"date": "1900-01-01", "value": 0.6, "sensor": "PLACEHOLDER_HLS_L30"},
            ]
        ),
    ),
}


@pytest.mark.parametrize("kind", sorted(FAILURES))
def test_each_failure_returns_source_unavailable_without_body_echo(tmp_path, kind: str):
    source, service, folder = build(tmp_path, FAILURES[kind])
    result = source.get_green_cover(REQUEST)
    assert len(service.requests) == 1
    assert result.data is None
    assert result.missing is not None
    assert result.missing.reason == "SOURCE_UNAVAILABLE"
    assert result.missing.detail
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "SOURCE_UNAVAILABLE"
    assert result.source.retrieved_at is None
    assert result.source.detail == result.missing.detail
    assert "PLACEHOLDER_SECRET_BODY" not in result.source.detail
    assert stored_files(folder) == []


def test_after_failure_next_call_retries_and_succeeds(tmp_path):
    source, service, folder = build(tmp_path, FAILURES["status-500"])
    assert source.get_green_cover(REQUEST).source.state == "unavailable"
    service.handler = answer_with(DOCUMENT)
    result = source.get_green_cover(REQUEST)
    assert len(service.requests) == 2
    assert result.source.state == "fresh"
    assert result.data is not None
    assert len(stored_files(folder)) == 1


# --- Query hygiene, cache edge cases, request/model invariants ----------------


def test_query_carries_no_user_identifying_params_or_headers(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    source.get_green_cover(REQUEST)
    (sent,) = service.requests
    assert sent.method == "GET"
    assert str(sent.url).startswith("https://green-cover.invalid/v1/observations?")
    params = dict(sent.url.params.multi_items())
    assert params == {
        "collection": "PLACEHOLDER_HLS_L30",
        "latitude": "-34.33",
        "longitude": "-57.68",
        "start_date": "1900-01-01",
        "end_date": "1900-01-10",
        "quantity": "placeholder_ndvi",
    }
    assert "user" not in params
    assert "cookie" not in {name.lower() for name in sent.headers}
    assert "authorization" not in {name.lower() for name in sent.headers}


def test_readonly_cache_still_returns_fresh_data(tmp_path):
    class ReadOnlyCache:
        def get(self, key: str) -> None:
            return None

        def put(self, key: str, entry: Any) -> Any:
            raise OSError("read-only")

    client = httpx.Client(transport=httpx.MockTransport(answer_with(DOCUMENT)))
    source = HlsModisGreenCoverSource(
        make_settings(), ReadOnlyCache(), client, now=Clock(FIRST)
    )
    result = source.get_green_cover(REQUEST)
    assert result.source.state == "fresh"
    assert result.data is not None
    assert "not be stored" in (result.source.detail or "")


def test_corrupted_cached_entry_returns_source_unavailable_without_network(tmp_path):
    source, _service, folder = build(tmp_path, answer_with(DOCUMENT))
    source.get_green_cover(REQUEST)
    (cache_file,) = stored_files(folder)
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["body"] = "PLACEHOLDER_SECRET_CORRUPT"
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    again, service2, _ = build(tmp_path, answer_with(DOCUMENT))
    result = again.get_green_cover(REQUEST)
    assert service2.requests == []
    assert result.data is None
    assert result.missing is not None
    assert result.missing.reason == "SOURCE_UNAVAILABLE"
    assert "PLACEHOLDER_SECRET_CORRUPT" not in (result.missing.detail or "")


def test_constructor_type_checks(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(answer_with(DOCUMENT)))
    cache = FileCache(tmp_path)
    with pytest.raises(TypeError):
        HlsModisGreenCoverSource(None, cache, client)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        HlsModisGreenCoverSource(make_settings(), None, client)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        HlsModisGreenCoverSource(make_settings(), cache, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"case_id": ""},
        {"field_id": "  "},
        {"latitude": 90.5},
        {"longitude": -181.0},
        {"longitude": float("nan")},
        {"start_date": dt.date(1900, 1, 5), "end_date": dt.date(1900, 1, 4)},
    ],
)
def test_impossible_request_is_programming_error_before_network(tmp_path, overrides):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    with pytest.raises(ValueError):
        source.get_green_cover(make_request(**overrides))
    assert service.requests == []


def test_pure_mapper_rejects_non_finite_float_in_python_dict():
    with pytest.raises(UnusableResponse):
        to_green_cover_strip(
            mock_document([{"date": "1900-01-01", "value": float("nan")}]),
            REQUEST,
            make_settings(),
        )


def test_dto_model_invariants():
    with pytest.raises(ValidationError):
        GreenCoverObservation(
            date=dt.date(1900, 1, 1),
            quantity="ndvi",
            unit="dimensionless",
            value=0.5,
            missing=Missing(reason="MISSING_INPUT", detail="both set"),
            provenance="OBSERVED",
            source="placeholder_source",
            sensor_source="PLACEHOLDER_HLS_L30",
        )
    with pytest.raises(ValidationError):
        GreenCoverObservation(
            date=dt.date(1900, 1, 1),
            quantity="ndvi",
            unit="dimensionless",
            value=None,
            missing=None,
            sensor_source="PLACEHOLDER_HLS_L30",
        )
    with pytest.raises(ValidationError):
        GreenCoverStrip(
            case_id="placeholder_case",
            field_id="placeholder_field",
            observations=[],
            strip_missing=None,
        )
    with pytest.raises(ValueError, match="missing"):
        GreenCoverResult(
            data=None,
            missing=None,
            source=SourceInfo(
                id="s",
                contract=CONTRACT,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
            ),
        )
