"""Acceptance test of the configuration: the running app assembled from variables.

Run with ``uv run pytest api/`` from the repository root.

Status: PROPOSED test cases (blueprint section 3.7). No network: the climate
service is an ``httpx.MockTransport``. Nothing is written outside ``tmp_path``.
Every setting comes from the placeholder builders of ``adapters/_fakes.py``,
every date is in year 1900 and every identifier is ``PLACEHOLDER_...``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import importlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from adapters._fakes import full_document, settings_fields
from adapters.example_soil_slope import EXAMPLE_SOIL_SLOPE_ID
from api import config as config_module
from api.app import create_app
from api.config import (
    CLIMATE_CACHE_DIR,
    CLIMATE_END_DATE,
    CLIMATE_START_DATE,
    CORS_ORIGINS,
    POWER_SETTINGS_FILE,
    SOIL_SLOPE_EXAMPLE_FILE,
    VARIABLES,
    AppConfig,
    ConfigError,
    build_app,
    load_config,
)
from api.ports import RunSettings
from api.standins import CLIMATE_STANDIN_ID, SOIL_SLOPE_STANDIN_ID

ROOT = Path(__file__).parent.parent
SOIL_SLOPE_FILE = (
    ROOT / "contracts" / "inputs" / "examples" / ("PLACEHOLDER_site_soil_slope.json")
)
ROTATION = json.loads(
    (
        ROOT
        / "contracts"
        / "rotation_definition"
        / "examples"
        / "PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)
BODY = {
    "site": {
        "case_id": "PLACEHOLDER_CASE",
        "field_id": "PLACEHOLDER_FIELD",
        "latitude": 1.5,
        "longitude": -2.5,
    },
    "rotation": ROTATION,
}
ROUTE = "/api/rotations/run"
ORIGIN = "http://localhost:5173"
START, END = "1900-01-01", "1900-01-03"
# A marker written into files: a ConfigError must never repeat file content.
SECRET = "PLACEHOLDER_FILE_CONTENT_MARKER"


# --- helpers ------------------------------------------------------------------


def settings_document(**overrides: Any) -> dict[str, Any]:
    fields = settings_fields(**overrides)
    fields["parameters"] = [dataclasses.asdict(p) for p in fields["parameters"]]
    fields["point"] = dataclasses.asdict(fields["point"])
    return fields


def write_settings(tmp_path: Path, document: Any = None) -> Path:
    path = tmp_path / "power_settings.json"
    path.write_text(
        json.dumps(document if document is not None else settings_document()),
        encoding="utf-8",
    )
    return path


def climate_environ(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {
        POWER_SETTINGS_FILE: str(write_settings(tmp_path)),
        CLIMATE_CACHE_DIR: str(tmp_path / "cache"),
        CLIMATE_START_DATE: START,
        CLIMATE_END_DATE: END,
        **extra,
    }


class Service:
    """A fake climate service: counts the calls, answers with a handler."""

    def __init__(self, handler=None) -> None:
        self.calls = 0
        self.handler = handler or self.data

    @staticmethod
    def data(_request: httpx.Request) -> httpx.Response:
        start, end = dt.date.fromisoformat(START), dt.date.fromisoformat(END)
        return httpx.Response(200, json=full_document(start, end))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.handler(request)


class RecordingClient(httpx.Client):
    """An ``httpx.Client`` on a mock transport that records ``close``."""

    def __init__(self, service: Service) -> None:
        super().__init__(transport=httpx.MockTransport(service))
        self.closed = 0

    def close(self) -> None:
        self.closed += 1
        super().close()


def factory_for(service: Service, made: list[RecordingClient] | None = None):
    def factory(_settings) -> httpx.Client:
        client = RecordingClient(service)
        if made is not None:
            made.append(client)
        return client

    return factory


def sources(response) -> list[dict[str, Any]]:
    assert response.status_code == 200
    return response.json()["sources"]


def config_error(environ: dict[str, str]) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        load_config(environ)
    return caught.value


# --- 1, 2, 12: nothing configured ---------------------------------------------


def test_nothing_set_is_todays_app():
    config = load_config({})
    assert config == AppConfig()
    assert config.climate is None
    assert config.soil_slope_example_file is None
    assert config.run_settings == RunSettings()
    assert not config.run_settings.has_period
    assert config.cors_origins == ()
    built = TestClient(build_app(config)).post(ROUTE, json=BODY)
    today = TestClient(create_app([])).post(ROUTE, json=BODY)
    assert today.status_code == 200
    assert built.status_code == today.status_code
    assert built.json() == today.json()


def test_nothing_set_uses_the_stand_ins(engines_hidden):
    response = TestClient(build_app(load_config({}))).post(ROUTE, json=BODY)
    assert [(s["id"], s["state"], s["missing_reason"]) for s in sources(response)] == [
        (CLIMATE_STANDIN_ID, "unavailable", "NOT_AVAILABLE"),
        (SOIL_SLOPE_STANDIN_ID, "unavailable", "NOT_AVAILABLE"),
    ]


def test_the_module_app_with_no_variable_is_todays_app(monkeypatch):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    import api.main

    module = importlib.reload(api.main)
    built = TestClient(module.app).post(ROUTE, json=BODY)
    today = TestClient(create_app([])).post(ROUTE, json=BODY)
    assert built.json() == today.json()


@pytest.mark.parametrize("blank", ["", " ", "\t\n"])
def test_blank_values_count_as_unset(blank):
    assert load_config({name: blank for name in VARIABLES}) == AppConfig()


def test_load_config_reads_only_the_mapping_it_is_given(monkeypatch, tmp_path):
    monkeypatch.setenv(POWER_SETTINGS_FILE, str(tmp_path / "absent.json"))
    monkeypatch.setenv(CLIMATE_START_DATE, "not a date")
    monkeypatch.setenv(SOIL_SLOPE_EXAMPLE_FILE, str(tmp_path / "absent.json"))
    monkeypatch.setenv(CORS_ORIGINS, ORIGIN)
    assert load_config({}) == AppConfig()


def test_cors_origins_from_the_mapping():
    config = load_config({CORS_ORIGINS: f"{ORIGIN}/, https://placeholder.invalid"})
    assert config.cors_origins == (ORIGIN, "https://placeholder.invalid")
    response = TestClient(build_app(config)).get("/health", headers={"Origin": ORIGIN})
    assert response.headers.get("access-control-allow-origin") == ORIGIN


# --- 3, 4: misconfiguration fails at start-up ---------------------------------


def test_settings_file_absent(tmp_path):
    error = config_error(
        {
            POWER_SETTINGS_FILE: str(tmp_path / "absent.json"),
            CLIMATE_CACHE_DIR: str(tmp_path / "cache"),
        }
    )
    assert POWER_SETTINGS_FILE in str(error)
    assert "does not exist" in str(error)


def test_settings_file_not_json(tmp_path):
    path = tmp_path / "power_settings.json"
    path.write_text(f"{{ {SECRET} ", encoding="utf-8")
    error = config_error(
        {POWER_SETTINGS_FILE: str(path), CLIMATE_CACHE_DIR: str(tmp_path / "cache")}
    )
    assert POWER_SETTINGS_FILE in str(error)
    assert "not valid JSON" in str(error)
    assert str(path) in str(error)
    assert SECRET not in str(error)


# A path written with backslashes, as on Windows (issue #18). It is never
# created; on any system it names a file that does not exist.
BACKSLASH_PATH = r"C:\made\up\settings.json"


@pytest.mark.parametrize("variable", [POWER_SETTINGS_FILE, SOIL_SLOPE_EXAMPLE_FILE])
def test_a_path_is_written_plainly_in_the_message(tmp_path, variable):
    """Single backslashes, between single quotes: never the doubled ``repr``."""
    error = config_error(
        {variable: BACKSLASH_PATH, CLIMATE_CACHE_DIR: str(tmp_path / "cache")}
    )
    assert f"'{BACKSLASH_PATH}'" in str(error)
    assert "\\\\" not in str(error)


@pytest.mark.parametrize(
    "document, reason",
    [
        (settings_document(base_url=f"http://{SECRET}.invalid/"), "base_url"),
        (
            {k: v for k, v in settings_document().items() if k != "community"},
            "community",
        ),
        (settings_document(community=""), "community"),
        ([SECRET], "mapping"),
    ],
)
def test_settings_rejected_by_the_adapter(tmp_path, document, reason):
    path = write_settings(tmp_path, document)
    error = config_error(
        {POWER_SETTINGS_FILE: str(path), CLIMATE_CACHE_DIR: str(tmp_path / "cache")}
    )
    assert POWER_SETTINGS_FILE in str(error)
    assert reason in str(error)  # the adapter's own message is passed on
    assert SECRET not in str(error)


def test_settings_file_without_cache_dir(tmp_path):
    error = config_error({POWER_SETTINGS_FILE: str(write_settings(tmp_path))})
    assert CLIMATE_CACHE_DIR in str(error)
    assert POWER_SETTINGS_FILE in str(error)


def test_cache_dir_alone_is_ignored(tmp_path):
    assert load_config({CLIMATE_CACHE_DIR: str(tmp_path / "cache")}) == AppConfig()
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize(
    "environ, named",
    [
        ({CLIMATE_START_DATE: START}, CLIMATE_START_DATE),
        ({CLIMATE_END_DATE: END}, CLIMATE_END_DATE),
        ({CLIMATE_START_DATE: "1900/01/01", CLIMATE_END_DATE: END}, CLIMATE_START_DATE),
        ({CLIMATE_START_DATE: START, CLIMATE_END_DATE: "19000103"}, CLIMATE_END_DATE),
        ({CLIMATE_START_DATE: START, CLIMATE_END_DATE: "1900-02-30"}, CLIMATE_END_DATE),
        ({CLIMATE_START_DATE: END, CLIMATE_END_DATE: START}, CLIMATE_START_DATE),
    ],
)
def test_wrong_period(environ, named):
    assert named in str(config_error(environ))


def test_a_one_day_period_is_accepted():
    config = load_config({CLIMATE_START_DATE: START, CLIMATE_END_DATE: START})
    assert config.run_settings.has_period


def test_soil_slope_file_absent(tmp_path):
    error = config_error({SOIL_SLOPE_EXAMPLE_FILE: str(tmp_path / "absent.json")})
    assert SOIL_SLOPE_EXAMPLE_FILE in str(error)
    assert "does not exist" in str(error)


def test_soil_slope_file_does_not_load(tmp_path):
    path = tmp_path / "soil.json"
    path.write_text(json.dumps({"contract": SECRET}), encoding="utf-8")
    error = config_error({SOIL_SLOPE_EXAMPLE_FILE: str(path)})
    assert SOIL_SLOPE_EXAMPLE_FILE in str(error)
    assert "SiteSoilSlope" in str(error)
    assert SECRET not in str(error)


def test_soil_slope_file_not_marked_as_example(tmp_path):
    document = json.loads(SOIL_SLOPE_FILE.read_text(encoding="utf-8"))
    document["example_data"] = False
    document["case_id"] = SECRET
    path = tmp_path / "soil.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    error = config_error({SOIL_SLOPE_EXAMPLE_FILE: str(path)})
    assert SOIL_SLOPE_EXAMPLE_FILE in str(error)
    assert "example_data" in str(error)
    assert SECRET not in str(error)


def test_the_example_source_itself_still_answers_unavailable(tmp_path):
    """The start-up check is an extra guard; the source keeps its own behaviour."""
    from adapters.example_soil_slope import ExampleSoilSlopeSource

    result = ExampleSoilSlopeSource(tmp_path / "absent.json").get_soil_slope(
        "PLACEHOLDER_CASE", "PLACEHOLDER_FIELD"
    )
    assert result.data is None
    assert result.source.state == "unavailable"


# --- 5 to 9: the assembled sources --------------------------------------------


def test_full_climate_configuration_fetches_once_then_cached(tmp_path, engines_hidden):
    service = Service()
    config = load_config(climate_environ(tmp_path))
    client = TestClient(build_app(config, client_factory=factory_for(service)))
    first = sources(client.post(ROUTE, json=BODY))[0]
    second = sources(client.post(ROUTE, json=BODY))[0]
    assert (first["id"], first["state"]) == ("placeholder_source", "fresh")
    assert (second["id"], second["state"]) == ("placeholder_source", "cached")
    assert service.calls == 1
    stored = list((tmp_path / "cache").iterdir())
    assert len(stored) == 1
    assert stored[0].suffix == ".json"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "cache",
        "power_settings.json",
    ]


def test_source_down_with_an_empty_cache(tmp_path, engines_hidden):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PLACEHOLDER", request=request)

    service = Service(down)
    config = load_config(climate_environ(tmp_path))
    client = TestClient(build_app(config, client_factory=factory_for(service)))
    response = client.post(ROUTE, json=BODY)
    climate = sources(response)[0]
    assert (climate["state"], climate["missing_reason"]) == (
        "unavailable",
        "SOURCE_UNAVAILABLE",
    )
    assert service.calls == 1
    assert not (tmp_path / "cache").exists()


def test_settings_without_a_period_do_not_call_the_source(tmp_path, engines_hidden):
    service = Service()
    environ = climate_environ(tmp_path)
    del environ[CLIMATE_START_DATE], environ[CLIMATE_END_DATE]
    client = TestClient(
        build_app(load_config(environ), client_factory=factory_for(service))
    )
    climate = sources(client.post(ROUTE, json=BODY))[0]
    assert (climate["id"], climate["state"], climate["missing_reason"]) == (
        "placeholder_source",
        "unavailable",
        "NOT_AVAILABLE",
    )
    assert service.calls == 0


def test_soil_slope_example_file_is_served_as_example(engines_hidden):
    config = load_config({SOIL_SLOPE_EXAMPLE_FILE: str(SOIL_SLOPE_FILE)})
    assert config.soil_slope_example_file == SOIL_SLOPE_FILE
    soil = sources(TestClient(build_app(config)).post(ROUTE, json=BODY))[1]
    assert (soil["id"], soil["contract"], soil["state"]) == (
        EXAMPLE_SOIL_SLOPE_ID,
        "site_data_soil_slope",
        "example",
    )


def test_the_client_is_closed_on_shutdown(tmp_path, engines_hidden):
    made: list[RecordingClient] = []
    config = load_config(climate_environ(tmp_path))
    app = build_app(config, client_factory=factory_for(Service(), made))
    assert len(made) == 1
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert made[0].closed == 0
    assert made[0].closed == 1


def test_the_default_client_has_the_configured_timeout(tmp_path):
    config = load_config(climate_environ(tmp_path))
    client = config_module.default_client(config.climate.settings)
    try:
        assert isinstance(client, httpx.Client)
        assert client.timeout == httpx.Timeout(config.climate.settings.timeout_seconds)
    finally:
        client.close()


def test_build_app_needs_an_app_config():
    with pytest.raises(TypeError):
        build_app({})  # type: ignore[arg-type]
