"""Acceptance tests of the NASA POWER adapter (PROPOSED cases 7 to 15 of the plan).

No network: the service is an ``httpx.MockTransport``, the cache lives in
``tmp_path`` and the clock is fixed. Run with ``uv run pytest adapters/``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Protocol, runtime_checkable

import httpx
import pytest

from adapters._fakes import (
    full_document,
    make_request,
    make_settings,
    power_document,
    settings_fields,
)
from adapters.cache import FileCache
from adapters.ports import ClimateSource
from adapters.power import ParameterSpec, PowerClimateSource, PowerSettings
from contracts.inputs import SiteClimate

FIRST = dt.datetime(1900, 2, 1, 6, 0, tzinfo=dt.UTC)
LATER = dt.datetime(1900, 3, 1, 6, 0, tzinfo=dt.UTC)


class Clock:
    def __init__(self, *moments: dt.datetime) -> None:
        self._moments = list(moments)

    def __call__(self) -> dt.datetime:
        return self._moments.pop(0) if len(self._moments) > 1 else self._moments[0]


class FakeService:
    """Counts calls and answers with a handler chosen by the test."""

    def __init__(self, handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def answer_with(document):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    return handler


def build(tmp_path, handler, clock=None, settings=None):
    service = FakeService(handler)
    client = httpx.Client(transport=httpx.MockTransport(service))
    cache_folder = tmp_path / "cache"
    source = PowerClimateSource(
        settings or make_settings(),
        FileCache(cache_folder),
        client,
        now=clock or Clock(FIRST, LATER),
    )
    return source, service, cache_folder


def stored_files(folder):
    return sorted(folder.iterdir()) if folder.exists() else []


REQUEST = make_request()
DOCUMENT = full_document(REQUEST.start_date, REQUEST.end_date)


# 7
def test_first_call_fetches_and_stores(tmp_path):
    source, service, folder = build(tmp_path, answer_with(DOCUMENT))
    result = source.get_climate(REQUEST)
    assert len(service.requests) == 1
    assert result.source.state == "fresh"
    assert result.source.retrieved_at == FIRST
    assert result.source.missing_reason is None
    assert result.data is not None
    assert len(stored_files(folder)) == 1


# 8
def test_second_identical_call_uses_the_cache(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    first = source.get_climate(REQUEST)
    second = source.get_climate(REQUEST)
    assert len(service.requests) == 1
    assert second.source.state == "cached"
    assert second.source.retrieved_at == first.source.retrieved_at == FIRST
    assert second.data == first.data


def test_cache_is_shared_by_two_adapter_instances(tmp_path):
    source, _, _ = build(tmp_path, answer_with(DOCUMENT))
    first = source.get_climate(REQUEST)
    again, service, _ = build(tmp_path, answer_with(DOCUMENT))
    second = again.get_climate(REQUEST)
    assert service.requests == []
    assert second.source.state == "cached"
    assert second.data == first.data


def test_another_request_is_not_served_from_the_cache(tmp_path):
    source, service, folder = build(tmp_path, answer_with(DOCUMENT))
    source.get_climate(REQUEST)
    source.get_climate(make_request(latitude=1.6))
    assert len(service.requests) == 2
    assert len(stored_files(folder)) == 2


# 9
def test_source_down_with_a_cache_entry_serves_the_entry(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    first = source.get_climate(REQUEST)

    def down(request):
        raise httpx.ConnectError("placeholder: down", request=request)

    service.handler = down
    second = source.get_climate(REQUEST)
    assert second.source.state == "cached"
    assert second.data == first.data
    assert second.source.retrieved_at == FIRST


def _raise(exception_type):
    def handler(request):
        raise exception_type("placeholder failure", request=request)

    return handler


def _status(code, **kwargs):
    def handler(_request):
        return httpx.Response(code, **kwargs)

    return handler


FAILURES = {
    "timeout": _raise(httpx.ReadTimeout),
    "connect-timeout": _raise(httpx.ConnectTimeout),
    "connection-error": _raise(httpx.ConnectError),
    "status-500": _status(500, json={"placeholder": "server error"}),
    "status-404": _status(404, text="PLACEHOLDER not found"),
    "status-422-error-payload": _status(422, json={"detail": ["PLACEHOLDER"]}),
    "status-429": _status(429, text="PLACEHOLDER"),
    "status-503": _status(503, text="PLACEHOLDER"),
    "body-not-json": _status(200, text="<html>PLACEHOLDER_SECRET_BODY</html>"),
    "body-json-nan": _status(200, text='{"properties": NaN}'),
    "json-without-layout": _status(200, json={"PLACEHOLDER_SECRET_BODY": 1.0}),
    "json-not-an-object": _status(200, json=[1.0, 2.0]),
    "json-without-a-configured-parameter": _status(
        200,
        json=power_document({"PLACEHOLDER_PARAMETER_A": {"19000101": 1.0}}),
    ),
    "service-error-payload": _status(
        200,
        json={"header": {}, "messages": ["PLACEHOLDER_SECRET_BODY"]},
    ),
    "unparseable-date": _status(
        200,
        json=power_document(
            {
                "PLACEHOLDER_PARAMETER_A": {"1900-01-01": 1.0},
                "PLACEHOLDER_PARAMETER_B": {"19000101": 1.0},
            }
        ),
    ),
    "other-fill-value-declared": _status(
        200, json=dict(DOCUMENT, header={"fill_value": 1.0})
    ),
}


# 10
@pytest.mark.parametrize("kind", sorted(FAILURES))
def test_each_failure_is_a_typed_absence(tmp_path, kind):
    source, service, folder = build(tmp_path, FAILURES[kind])
    result = source.get_climate(REQUEST)
    assert len(service.requests) == 1
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "SOURCE_UNAVAILABLE"
    assert result.source.retrieved_at is None
    assert result.source.detail
    assert "PLACEHOLDER_SECRET_BODY" not in result.source.detail
    assert stored_files(folder) == []


def test_failure_details_name_the_kind(tmp_path):
    details = {}
    for kind in ("timeout", "connection-error", "status-500", "body-not-json"):
        source, _, _ = build(tmp_path / kind, FAILURES[kind])
        details[kind] = source.get_climate(REQUEST).source.detail
    assert "in time" in details["timeout"]
    assert "reached" in details["connection-error"]
    assert "500" in details["status-500"]
    assert "not JSON" in details["body-not-json"]


# 11
def test_after_a_failure_the_next_call_tries_again(tmp_path):
    source, service, folder = build(tmp_path, FAILURES["status-500"])
    assert source.get_climate(REQUEST).source.state == "unavailable"
    service.handler = answer_with(DOCUMENT)
    result = source.get_climate(REQUEST)
    assert len(service.requests) == 2
    assert result.source.state == "fresh"
    assert len(stored_files(folder)) == 1


# 12
def test_query_carries_what_is_needed_and_nothing_that_identifies_a_user(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    source.get_climate(REQUEST)
    (sent,) = service.requests
    assert sent.method == "GET"
    assert str(sent.url).startswith("https://power.invalid/daily/point?")
    params = dict(sent.url.params.multi_items())
    assert len(sent.url.params.multi_items()) == len(params)  # nothing twice
    assert params == {
        "parameters": "PLACEHOLDER_PARAMETER_A,PLACEHOLDER_PARAMETER_B",
        "community": "PLACEHOLDER_community",
        "latitude": "1.5",
        "longitude": "-2.5",
        "start": "19000101",
        "end": "19000103",
        "format": "JSON",
        "time-standard": "UTC",
    }
    assert "user" not in params
    assert "cookie" not in {name.lower() for name in sent.headers}
    assert "authorization" not in {name.lower() for name in sent.headers}


def test_same_inputs_give_the_same_query_whatever_the_configured_order(tmp_path):
    fields = settings_fields()
    reversed_settings = PowerSettings(
        **dict(fields, parameters=tuple(reversed(fields["parameters"])))
    )
    source, _, _ = build(tmp_path, answer_with(DOCUMENT))
    source.get_climate(REQUEST)
    other, other_service, _ = build(
        tmp_path, answer_with(DOCUMENT), settings=reversed_settings
    )
    result = other.get_climate(REQUEST)
    assert other_service.requests == []  # same query, same key: a cache hit
    assert result.source.state == "cached"
    assert [s.quantity for s in result.data.daily_series] == [
        "placeholder_quantity_b",
        "placeholder_quantity_a",
    ]


def test_optional_arguments_are_sent_when_configured(tmp_path):
    settings = make_settings(optional_arguments={"units": "PLACEHOLDER_units"})
    source, service, _ = build(tmp_path, answer_with(DOCUMENT), settings=settings)
    source.get_climate(REQUEST)
    (sent,) = service.requests
    assert sent.url.params["units"] == "PLACEHOLDER_units"
    assert source.get_climate(REQUEST).source.request["units"] == "PLACEHOLDER_units"


@pytest.mark.parametrize(
    "name", ["user", "parameters", "time-standard", "format", "latitude", "header"]
)
def test_optional_arguments_cannot_identify_a_user_or_override_the_query(name):
    with pytest.raises(ValueError, match="optional_arguments"):
        make_settings(optional_arguments={name: "PLACEHOLDER"})


# 13
@pytest.mark.parametrize("handler", [answer_with(DOCUMENT), FAILURES["status-500"]])
def test_source_info(tmp_path, handler):
    source, service, _ = build(tmp_path, handler)
    info = source.get_climate(REQUEST).source
    assert info.id == "placeholder_source" == source.source_id
    assert info.contract == "site_data_climate" == source.contract
    assert info.time_zone == "UTC"
    assert info.attribution == "PLACEHOLDER_attribution"
    assert dict(info.request) == dict(service.requests[0].url.params.multi_items())


def test_retrieved_at_comes_from_the_clock_in_utc(tmp_path):
    offset = dt.timezone(dt.timedelta(hours=3))
    clock = Clock(dt.datetime(1900, 2, 1, 9, 0, tzinfo=offset))
    source, _, _ = build(tmp_path, answer_with(DOCUMENT), clock=clock)
    assert source.get_climate(REQUEST).source.retrieved_at == FIRST


# 14
@runtime_checkable
class CheckableClimateSource(ClimateSource, Protocol):
    """A runtime-checkable copy of the seam; the seam itself is not edited."""


def test_satisfies_the_climate_source_protocol(tmp_path):
    source, _, _ = build(tmp_path, answer_with(DOCUMENT))
    typed: ClimateSource = source
    assert isinstance(typed, CheckableClimateSource)


# 15
@pytest.mark.parametrize("name", sorted(settings_fields()))
def test_a_missing_setting_is_an_error_naming_it(name):
    fields = settings_fields()
    del fields[name]
    with pytest.raises(TypeError, match=name):
        PowerSettings(**fields)


def test_no_setting_has_a_default():
    for field in dataclasses.fields(PowerSettings):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name
    for field in dataclasses.fields(ParameterSpec):
        assert field.default is dataclasses.MISSING, field.name


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("base_url", ""),
        ("base_url", "http://power.invalid/daily/point"),
        ("base_url", "https://power.invalid/daily/point?format=JSON"),
        ("community", ""),
        ("community", "   "),
        ("parameters", ()),
        ("fill_value", float("nan")),
        ("fill_reason", ""),
        ("fill_reason", "PLACEHOLDER_REASON"),
        ("range_missing_reason", ""),
        ("attribution", ""),
        ("source_id", ""),
        ("timeout_seconds", 0),
        ("timeout_seconds", -1.0),
    ],
)
def test_an_empty_or_invalid_setting_is_an_error_naming_it(name, value):
    with pytest.raises(ValueError, match=name):
        make_settings(**{name: value})


@pytest.mark.parametrize(
    ("name", "value"),
    [("fill_value", None), ("fill_value", True), ("optional_arguments", None)],
)
def test_a_setting_of_the_wrong_type_is_an_error_naming_it(name, value):
    with pytest.raises(TypeError, match=name):
        make_settings(**{name: value})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("source_parameter", ""),
        ("source_parameter", "PLACEHOLDER_A,PLACEHOLDER_B"),
        ("quantity", "Placeholder_quantity"),
        ("quantity", ""),
        ("unit", ""),
        ("provenance", "observed"),
        ("provenance", ""),
    ],
)
def test_an_invalid_parameter_spec_is_an_error_naming_it(name, value):
    fields = {
        "source_parameter": "PLACEHOLDER_PARAMETER_A",
        "quantity": "placeholder_quantity_a",
        "unit": "PLACEHOLDER_unit",
        "provenance": "OBSERVED",
        name: value,
    }
    with pytest.raises(ValueError, match=name):
        ParameterSpec(**fields)


def test_two_specs_for_one_source_parameter_or_quantity_are_an_error():
    spec = make_settings().parameters[0]
    with pytest.raises(ValueError, match="twice"):
        make_settings(parameters=(spec, spec))
    other = dataclasses.replace(spec, source_parameter="PLACEHOLDER_PARAMETER_C")
    with pytest.raises(ValueError, match="twice"):
        make_settings(parameters=(spec, other))


def test_settings_from_configuration():
    document = json.loads(
        json.dumps(
            dict(
                settings_fields(),
                parameters=[
                    dataclasses.asdict(spec) for spec in make_settings().parameters
                ],
            )
        )
    )
    assert PowerSettings.from_mapping(document) == make_settings()
    del document["community"]
    with pytest.raises(ValueError, match="community"):
        PowerSettings.from_mapping(document)
    document["community"] = "PLACEHOLDER_community"
    document["placeholder_unknown"] = 1
    with pytest.raises(ValueError, match="placeholder_unknown"):
        PowerSettings.from_mapping(document)


def test_construction_needs_its_three_parts(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(answer_with(DOCUMENT)))
    cache = FileCache(tmp_path)
    with pytest.raises(TypeError):
        PowerClimateSource(None, cache, client)
    with pytest.raises(TypeError):
        PowerClimateSource(make_settings(), None, client)
    with pytest.raises(TypeError):
        PowerClimateSource(make_settings(), cache, None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": dt.date(1900, 1, 2), "end_date": dt.date(1900, 1, 1)},
        {"latitude": 90.5},
        {"longitude": float("nan")},
    ],
)
def test_an_impossible_request_is_a_programming_error(tmp_path, overrides):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    with pytest.raises(ValueError):
        source.get_climate(make_request(**overrides))
    assert service.requests == []


def test_a_cache_that_cannot_write_still_returns_the_data(tmp_path):
    class ReadOnlyCache:
        def get(self, key):
            return None

        def put(self, key, entry):
            raise OSError("placeholder: read-only")

    client = httpx.Client(transport=httpx.MockTransport(answer_with(DOCUMENT)))
    source = PowerClimateSource(
        make_settings(), ReadOnlyCache(), client, now=Clock(FIRST)
    )
    result = source.get_climate(REQUEST)
    assert result.source.state == "fresh"
    assert result.data is not None
    assert "not be stored" in result.source.detail


# Seam fixes of unit l2/engine-runner


def test_data_is_a_site_climate_instance(tmp_path):
    source, _, _ = build(tmp_path, answer_with(DOCUMENT))
    fresh = source.get_climate(REQUEST)
    cached = source.get_climate(REQUEST)
    assert isinstance(fresh.data, SiteClimate)
    assert isinstance(cached.data, SiteClimate)
    assert cached.source.state == "cached"


def test_source_says_who_it_is_without_a_call(tmp_path):
    source, service, _ = build(tmp_path, answer_with(DOCUMENT))
    assert source.source_id == "placeholder_source"
    assert source.contract == "site_data_climate"
    assert service.requests == []


def test_a_document_that_does_not_load_is_unavailable_and_not_stored(
    tmp_path, monkeypatch
):
    import adapters.power

    def not_loadable(raw, request, settings):
        return {"contract": "site_data_climate", "PLACEHOLDER_KEY": "PLACEHOLDER"}

    monkeypatch.setattr(adapters.power, "to_site_climate", not_loadable)
    source, _, folder = build(tmp_path, answer_with(DOCUMENT))
    result = source.get_climate(REQUEST)
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "SOURCE_UNAVAILABLE"
    assert "SiteClimate" in result.source.detail
    assert "PLACEHOLDER_KEY" not in result.source.detail
    assert stored_files(folder) == []
