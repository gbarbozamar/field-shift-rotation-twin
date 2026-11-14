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
from adapters.soil_tables import SOIL_TABLES_ID
from api import config as config_module
from api.app import create_app
from api.config import (
    CLIMATE_CACHE_DIR,
    CLIMATE_END_DATE,
    CLIMATE_START_DATE,
    CORS_ORIGINS,
    POWER_SETTINGS_FILE,
    SOIL_GROUPS_FILE,
    SOIL_SLOPE_EXAMPLE_FILE,
    SOIL_TABLE_FILES,
    VARIABLES,
    AppConfig,
    ConfigError,
    SoilTablesConfig,
    build_app,
    load_config,
)
from api.engines import OTHER_FIELD
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


# --- the real settings file of the adapter -------------------------------------


def test_the_committed_settings_file_builds_the_app_with_the_period_of_d29(
    tmp_path, engines_hidden
):
    """The variables of the deployed service (api/README.md), on a fake service."""
    root = Path(__file__).parent.parent
    evidence = json.loads(
        (
            root / "docs" / "evidence" / "nasa-power-2026-11-14" / "response.json"
        ).read_text(encoding="utf-8")
    )
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        return httpx.Response(200, json=evidence)

    config = load_config(
        {
            "POWER_SETTINGS_FILE": str(
                root / "adapters" / "settings" / "nasa_power.json"
            ),
            "CLIMATE_CACHE_DIR": str(tmp_path / "cache"),
            "CLIMATE_START_DATE": "2001-01-01",
            "CLIMATE_END_DATE": "2024-12-31",
        }
    )
    client = TestClient(
        build_app(
            config,
            client_factory=lambda settings: httpx.Client(
                transport=httpx.MockTransport(handler)
            ),
        )
    )
    response = client.post(ROUTE, json=BODY)
    assert response.status_code == 200
    climate = sources(response)[0]
    assert (climate["id"], climate["state"]) == ("nasa_power", "fresh")
    assert len(requested) == 1
    assert requested[0].host == "power.larc.nasa.gov"
    assert requested[0].params["start"] == "20010101"
    assert requested[0].params["end"] == "20241231"
    assert requested[0].params["community"] == "ag"


# --- the parameter catalogue (Q3, D46, D56 of #77; PROPOSED) -------------------

PARAMS = ROOT / "params"
PARAMS_EXAMPLES = PARAMS / "examples"


def copy_example(folder: Path, name: str, target: str, **change: Any) -> dict:
    """Copy a record of params/examples/ into ``folder``, with fields removed or changed."""
    record = json.loads((PARAMS_EXAMPLES / name).read_text(encoding="utf-8"))
    for key, value in change.items():
        if value is None:
            del record[key]
        else:
            record[key] = value
    folder.mkdir(parents=True, exist_ok=True)
    (folder / target).write_text(json.dumps(record), encoding="utf-8")
    return record


def catalogue_error(folder: Path) -> str:
    with pytest.raises(ConfigError) as caught:
        load_config({}, parameters_folder=folder)
    message = str(caught.value)
    assert f"'{folder}'" in message  # the folder, written plainly
    return message


def test_the_catalogue_folder_is_params_records_of_the_repository():
    assert config_module.PARAMETERS_FOLDER == (PARAMS / "records").resolve()


def test_the_repository_catalogue_starts_the_app_with_an_empty_catalogue():
    config = load_config({})
    assert config.parameters == {}
    response = TestClient(build_app(config)).get("/health")
    assert response.status_code == 200


def test_an_empty_folder_is_an_empty_catalogue(tmp_path):
    assert load_config({}, parameters_folder=tmp_path).parameters == {}


def test_a_file_that_is_not_json_refuses_start_up(tmp_path):
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    message = catalogue_error(tmp_path)
    assert "broken.json: not a readable record file" in message


def test_a_file_that_is_not_a_record_file_refuses_start_up(tmp_path):
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    assert "notes.txt: not a .json record file" in catalogue_error(tmp_path)


def test_a_folder_that_does_not_exist_refuses_start_up(tmp_path):
    folder = tmp_path / "absent"
    assert "absent: the folder does not exist" in catalogue_error(folder)


def test_a_malformed_record_refuses_start_up(tmp_path):
    copy_example(tmp_path, "PLACEHOLDER_with_value.json", "record.json", unit=None)
    message = catalogue_error(tmp_path)
    assert "record.json: required field 'unit' is absent" in message


def test_two_records_with_the_same_identity_refuse_start_up(tmp_path):
    for target in ("one.json", "two.json"):
        copy_example(tmp_path, "PLACEHOLDER_with_value.json", target)
    message = catalogue_error(tmp_path)
    assert "same 'id' and 'scope' in: one.json, two.json" in message


@pytest.mark.parametrize(
    "name", ["PLACEHOLDER_with_value.json", "PLACEHOLDER_missing_value.json"]
)
def test_a_placeholder_record_refuses_start_up(tmp_path, name):
    copy_example(tmp_path, name, "record.json")
    message = catalogue_error(tmp_path)
    assert "record.json: contains the word PLACEHOLDER, so it is not a parameter" in (
        message
    )


def test_each_problem_is_on_its_own_line(tmp_path):
    for target in ("one.json", "two.json"):
        copy_example(tmp_path, "PLACEHOLDER_with_value.json", target)
    records, problems = config_module.load_folder(tmp_path)
    expected = config_module.check_catalogue(records)
    assert problems == [] and len(expected) > 1
    lines = catalogue_error(tmp_path).splitlines()
    assert lines[1:] == expected


def test_a_problem_while_loading_is_reported_before_the_check(tmp_path):
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    copy_example(tmp_path, "PLACEHOLDER_with_value.json", "record.json")
    _records, problems = config_module.load_folder(tmp_path)
    lines = catalogue_error(tmp_path).splitlines()
    assert problems and lines[1:] == problems


def recorded_engines(monkeypatch) -> list[Any]:
    """Record every ``EntryPointEngines`` that ``create_app`` builds."""
    from api import app as app_module

    built: list[Any] = []
    real = app_module.EntryPointEngines

    def recording(*args: Any, **kwargs: Any) -> Any:
        built.append(real(*args, **kwargs))
        return built[-1]

    monkeypatch.setattr(app_module, "EntryPointEngines", recording)
    return built


def test_build_app_gives_the_loaded_catalogue_to_the_engines(monkeypatch):
    loaded: dict[str, dict] = {}
    built = recorded_engines(monkeypatch)
    build_app(AppConfig(parameters=loaded))
    (engines,) = built
    assert engines.parameters is loaded


def test_load_config_and_build_app_pass_the_same_catalogue(monkeypatch, tmp_path):
    config = load_config({}, parameters_folder=tmp_path)
    built = recorded_engines(monkeypatch)
    build_app(config)
    (engines,) = built
    assert engines.parameters is config.parameters


# --- the soil-table source (unit l2/soil-tables) -------------------------------

ADAPTER_EXAMPLES = ROOT / "adapters" / "examples"
SOIL_TABLE_TEMPLATE = ADAPTER_EXAMPLES / "PLACEHOLDER_soil_table.json"
SOIL_GROUPS_TEMPLATE = ADAPTER_EXAMPLES / "PLACEHOLDER_soil_groups.json"
SOIL_TABLES_ENVIRON = {
    SOIL_TABLE_FILES: str(SOIL_TABLE_TEMPLATE),
    SOIL_GROUPS_FILE: str(SOIL_GROUPS_TEMPLATE),
}


def test_both_soil_variables_wire_the_soil_table_source(engines_hidden):
    config = load_config(SOIL_TABLES_ENVIRON)
    assert config.soil_tables == SoilTablesConfig(
        table_files=(SOIL_TABLE_TEMPLATE,), groups_file=SOIL_GROUPS_TEMPLATE
    )
    assert config.soil_slope_example_file is None
    response = TestClient(build_app(config)).post(ROUTE, json=BODY)
    soil = sources(response)[1]
    assert (soil["id"], soil["contract"], soil["state"]) == (
        SOIL_TABLES_ID,
        "site_data_soil_slope",
        "example",
    )
    assert soil["missing_reason"] is None
    assert soil["request"] == {
        "case_id": BODY["site"]["case_id"],
        "field_id": BODY["site"]["field_id"],
        "soil_group": "PLACEHOLDER_GROUP_A",
    }


def test_an_undeclared_field_is_reported_in_sources(engines_hidden):
    body = {**BODY, "site": {**BODY["site"], "field_id": "PLACEHOLDER_UNDECLARED"}}
    response = TestClient(build_app(load_config(SOIL_TABLES_ENVIRON))).post(
        ROUTE, json=body
    )
    soil = sources(response)[1]
    assert (soil["id"], soil["state"], soil["missing_reason"]) == (
        SOIL_TABLES_ID,
        "unavailable",
        "NOT_DECLARED",
    )


@pytest.mark.parametrize(
    "given, absent",
    [(SOIL_TABLE_FILES, SOIL_GROUPS_FILE), (SOIL_GROUPS_FILE, SOIL_TABLE_FILES)],
)
def test_one_soil_variable_without_the_other(given, absent):
    error = config_error({given: SOIL_TABLES_ENVIRON[given]})
    assert f"{given} is set without {absent}" in str(error)


@pytest.mark.parametrize("blank", ["", " ", "\t"])
@pytest.mark.parametrize(
    "given, absent",
    [(SOIL_TABLE_FILES, SOIL_GROUPS_FILE), (SOIL_GROUPS_FILE, SOIL_TABLE_FILES)],
)
def test_a_blank_soil_variable_counts_as_unset(given, absent, blank):
    error = config_error({given: SOIL_TABLES_ENVIRON[given], absent: blank})
    assert f"{given} is set without {absent}" in str(error)


def test_the_missing_slope_reaches_the_runner_without_error(monkeypatch):
    """With no engine assumed, the source's document reaches the runner whole."""
    from api import app as app_module

    received: list[Any] = []
    real = app_module.EntryPointEngines

    class Recording:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._inner = real(*args, **kwargs)

        def run(self, rotation, climate, soil_slope):
            received.append(soil_slope)
            return self._inner.run(rotation, climate, soil_slope)

    monkeypatch.setattr(app_module, "EntryPointEngines", Recording)
    response = TestClient(build_app(load_config(SOIL_TABLES_ENVIRON))).post(
        ROUTE, json=BODY
    )
    assert response.status_code == 200
    (soil_result,) = received
    for value in (soil_result.data.slope_length, soil_result.data.slope_steepness):
        assert value.value is None
        assert value.missing.reason == "NOT_AVAILABLE"
    for module in response.json()["modules"]:
        assert module["state"] in ("available", "degraded", "not_available")


class ExampleClimate:
    """A fake climate source: the PLACEHOLDER contract example, for the request's field."""

    source_id = "PLACEHOLDER_climate"
    contract = "site_data_climate"

    def get_climate(self, request):
        from adapters.ports import ClimateResult, SourceInfo
        from contracts.inputs import SiteClimate

        path = (
            ROOT / "contracts" / "inputs" / "examples" / "PLACEHOLDER_site_climate.json"
        )
        document = json.loads(path.read_text(encoding="utf-8"))
        document.update(case_id=request.case_id, field_id=request.field_id)
        return ClimateResult(
            data=SiteClimate.model_validate(document),
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


def test_the_missing_slope_reaches_the_engines_and_the_route_answers(tmp_path):
    """Climate present and the field of the rotation declared, so every engine
    that exists is called with the missing slope; none is assumed to exist."""
    from adapters.soil_tables import SoilTableSource
    from contracts.results.models import ResultsPerRotation

    case_id, field_id = ROTATION["case_id"], ROTATION["field_id"]
    groups = tmp_path / "groups.json"
    groups.write_text(
        json.dumps(
            {
                "example_data": True,
                "declarations": [
                    {
                        "case_id": case_id,
                        "field_id": field_id,
                        "soil_group": "PLACEHOLDER_GROUP_A",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    body = {**BODY, "site": {**BODY["site"], "case_id": case_id, "field_id": field_id}}
    app = create_app(
        [],
        climate=ExampleClimate(),
        soil_slope=SoilTableSource([SOIL_TABLE_TEMPLATE], groups),
        settings=RunSettings(
            start_date=dt.date(1900, 1, 1), end_date=dt.date(1900, 1, 3)
        ),
    )
    response = TestClient(app).post(ROUTE, json=body)
    assert response.status_code == 200
    answer = response.json()
    assert [s["state"] for s in answer["sources"]] == ["example", "example"]
    if answer["result"] is not None:
        ResultsPerRotation.model_validate(answer["result"])
    else:
        assert OTHER_FIELD not in (answer["result_missing"]["detail"] or "")


def test_the_soil_tables_and_the_example_together_are_refused():
    error = config_error(
        {**SOIL_TABLES_ENVIRON, SOIL_SLOPE_EXAMPLE_FILE: str(SOIL_SLOPE_FILE)}
    )
    for name in (SOIL_SLOPE_EXAMPLE_FILE, SOIL_TABLE_FILES, SOIL_GROUPS_FILE):
        assert name in str(error)


def test_build_app_refuses_two_soil_sources():
    config = AppConfig(
        soil_slope_example_file=SOIL_SLOPE_FILE,
        soil_tables=SoilTablesConfig(
            table_files=(SOIL_TABLE_TEMPLATE,), groups_file=SOIL_GROUPS_TEMPLATE
        ),
    )
    with pytest.raises(ConfigError):
        build_app(config)


@pytest.mark.parametrize("variable", [SOIL_TABLE_FILES, SOIL_GROUPS_FILE])
def test_a_soil_file_absent_names_the_variable_and_the_path_plainly(variable):
    environ = {**SOIL_TABLES_ENVIRON, variable: BACKSLASH_PATH}
    error = config_error(environ)
    assert variable in str(error)
    assert f"'{BACKSLASH_PATH}'" in str(error)
    assert "\\\\" not in str(error)
    assert "does not exist" in str(error)


@pytest.mark.parametrize("variable", [SOIL_TABLE_FILES, SOIL_GROUPS_FILE])
def test_a_malformed_soil_file_refuses_start_up(tmp_path, variable):
    path = tmp_path / "soil.json"
    path.write_text(json.dumps({SECRET: SECRET}), encoding="utf-8")
    error = config_error({**SOIL_TABLES_ENVIRON, variable: str(path)})
    assert variable in str(error)
    assert f"'{path}'" in str(error)
    assert SECRET not in str(error)


def test_one_table_file_named_twice_refuses_start_up():
    twice = f"{SOIL_TABLE_TEMPLATE},{SOIL_TABLE_TEMPLATE}"
    error = config_error({**SOIL_TABLES_ENVIRON, SOIL_TABLE_FILES: twice})
    assert SOIL_TABLE_FILES in str(error)
    assert "twice" in str(error)


def test_two_table_files_with_the_same_quantity_refuse_start_up(tmp_path):
    copy_path = tmp_path / "copy.json"
    copy_path.write_text(SOIL_TABLE_TEMPLATE.read_text(encoding="utf-8"), "utf-8")
    environ = {
        **SOIL_TABLES_ENVIRON,
        SOIL_TABLE_FILES: f"{SOIL_TABLE_TEMPLATE}, {copy_path}",
    }
    error = config_error(environ)
    assert SOIL_TABLE_FILES in str(error)
    assert "same quantity" in str(error)


def test_an_empty_item_in_the_table_list_refuses_start_up():
    environ = {**SOIL_TABLES_ENVIRON, SOIL_TABLE_FILES: f"{SOIL_TABLE_TEMPLATE},"}
    assert SOIL_TABLE_FILES in str(config_error(environ))
