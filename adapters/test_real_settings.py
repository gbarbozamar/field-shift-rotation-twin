"""The real settings of the NASA POWER adapter (``adapters/settings/nasa_power.json``).

Every value of that file is copied from a recorded decision of issue 77
(D20, D23 to D37, D55); none is chosen here. These tests keep the file in step
with the contract that names the quantities, and run it against the one
documented response of the service, committed as evidence. No test calls the
service.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

from adapters.cache import FileCache
from adapters.ports import ClimateRequest
from adapters.power import PowerClimateSource, PowerSettings, build_query
from adapters.power_mapping import to_site_climate
from contracts.inputs import SiteClimate

ROOT = Path(__file__).parent.parent
SETTINGS_FILE = Path(__file__).parent / "settings" / "nasa_power.json"
QUANTITIES_FILE = ROOT / "contracts" / "CLIMATE_QUANTITIES.md"
EVIDENCE = ROOT / "docs" / "evidence" / "nasa-power-2026-11-14"

DOCUMENT = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
SETTINGS = PowerSettings.from_mapping(DOCUMENT)

# The request of the evidence folder: a made-up ocean point, ten days.
EVIDENCE_REQUEST = ClimateRequest(
    case_id="PLACEHOLDER_case",
    field_id="PLACEHOLDER_field",
    latitude=-35.0,
    longitude=-50.0,
    start_date=dt.date(2024, 1, 1),
    end_date=dt.date(2024, 1, 10),
)


def evidence_response() -> dict:
    return json.loads((EVIDENCE / "response.json").read_text(encoding="utf-8"))


def test_the_settings_file_loads():
    assert isinstance(SETTINGS, PowerSettings)


def test_the_decided_values():
    # D28, D32, D31, D36, D55 of issue 77; the timeout is the platform developer's.
    assert SETTINGS.base_url == "https://power.larc.nasa.gov/api/temporal/daily/point"
    assert SETTINGS.community == "ag"
    assert SETTINGS.fill_value == -999.0
    assert SETTINGS.fill_reason == "NO_COVERAGE"
    assert SETTINGS.range_missing_reason == "NO_COVERAGE"
    assert SETTINGS.optional_arguments == {}
    assert SETTINGS.timeout_seconds == 60
    point = SETTINGS.point
    assert (point.latitude_unit, point.longitude_unit, point.elevation_unit) == (
        "degree",
        "degree",
        "m",
    )
    assert point.provenance == "OBSERVED"


def test_the_seven_series_of_d35():
    assert [spec.source_parameter for spec in SETTINGS.parameters] == [
        "IMERG_PRECTOT",
        "PRECTOTCORR",
        "T2M_MAX",
        "T2M_MIN",
        "T2MDEW",
        "WS2M",
        "ALLSKY_SFC_SW_DWN",
    ]
    assert all(spec.provenance == "OBSERVED" for spec in SETTINGS.parameters)


@pytest.mark.parametrize("spec", SETTINGS.parameters, ids=lambda spec: spec.quantity)
def test_each_series_is_written_as_the_contract_names_it(spec):
    """Identifier, unit string and source parameter on one row of the summary table.

    A change of ``contracts/CLIMATE_QUANTITIES.md`` then fails here instead of
    letting the settings drift.
    """
    rows = [
        line
        for line in QUANTITIES_FILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `CQ") and f"`{spec.quantity}`" in line
    ]
    assert len(rows) == 1, f"one row of the summary table names {spec.quantity}"
    row = rows[0]
    assert f"`{spec.unit}`" in row
    assert f"`{spec.source_parameter}`" in row
    assert f"`{spec.provenance}`" in row


def test_the_query_is_the_documented_request():
    request_text = (EVIDENCE / "request.txt").read_text(encoding="utf-8")
    url = next(
        line.split("URL:", 1)[1].strip()
        for line in request_text.splitlines()
        if line.startswith("URL:")
    )
    documented = httpx.URL(url)
    query = build_query(EVIDENCE_REQUEST, SETTINGS)
    assert str(documented.copy_with(query=None)) == SETTINGS.base_url
    recorded = dict(documented.params)
    assert sorted(recorded.pop("parameters").split(",")) == sorted(
        query["parameters"].split(",")
    )
    built = dict(query)
    built.pop("parameters")
    assert float(built.pop("latitude")) == float(recorded.pop("latitude"))
    assert float(built.pop("longitude")) == float(recorded.pop("longitude"))
    assert built == recorded


def test_the_documented_response_maps_into_the_contract():
    document = to_site_climate(evidence_response(), EVIDENCE_REQUEST, SETTINGS)
    model = SiteClimate.model_validate_json(json.dumps(document))
    assert [series.quantity for series in model.daily_series] == [
        spec.quantity for spec in SETTINGS.parameters
    ]
    for series in model.daily_series:
        assert len(series.days) == 10
        assert series.time_zone == "UTC"
        assert series.range_missing.reason == "NO_COVERAGE"
    # The point is what the response reports (D18), in GeoJSON order.
    assert model.point.longitude.value == -50.0
    assert model.point.latitude.value == -35.0
    assert model.point.elevation.value == 0.0
    assert model.point.latitude.unit == "degree"
    assert model.point.elevation.unit == "m"


def test_a_fill_value_in_the_documented_layout_is_missing_never_zero():
    raw = evidence_response()
    raw["properties"]["parameter"]["T2M_MAX"]["20240103"] = -999.0
    raw["properties"]["parameter"]["IMERG_PRECTOT"]["20240104"] = 0.0
    document = to_site_climate(raw, EVIDENCE_REQUEST, SETTINGS)
    series = {item["quantity"]: item for item in document["daily_series"]}
    day = series["air_temperature_max_2m"]["days"][2]
    assert day["value"] is None
    assert day["missing"]["reason"] == "NO_COVERAGE"
    assert series["precipitation"]["days"][3]["value"] == 0.0


def test_the_adapter_serves_the_documented_response_then_its_cache(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json=evidence_response())

    source = PowerClimateSource(
        SETTINGS,
        FileCache(tmp_path),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first = source.get_climate(EVIDENCE_REQUEST)
    second = source.get_climate(EVIDENCE_REQUEST)
    assert (first.source.state, second.source.state) == ("fresh", "cached")
    assert len(calls) == 1
    assert calls[0].host == "power.larc.nasa.gov"
    assert calls[0].params["community"] == "ag"
    assert calls[0].params["time-standard"] == "utc"
    assert first.source.id == "nasa_power"
    assert first.data == second.data
