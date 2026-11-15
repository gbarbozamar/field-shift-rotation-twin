"""Acceptance test of unit ``l2/plant-layer-by-name`` (brief S-031).

Run with ``uv run pytest api/test_plant_layer.py -q`` from the repository root.

Status: PROPOSED test cases, written before the code. The plant layer
(``economics.plant.answer_plant`` and ``contracts.plant_answer``) is found by
name on each request (``api/plant_layer.py``), as the decision layer is; a
broken or absent plant layer never stops the service from starting nor
breaks another route. The ONI record is read only when
``KINDS_OF_YEAR_RECORD_FILE`` is set, once, at start-up (``api/config.py``).

Fakes only: the climate, the soil and slope and the engines are the fakes of
api/test_rotations.py and api/test_plant.py; no network and no real service.
No expected number is typed here: every value compared is read from the
PLACEHOLDER record of economics/test_plant.py or from the contract examples.
No ONI record is in the repository (D240 (5) of #77, #422): a test that needs
a record file writes that PLACEHOLDER record to a temporary folder.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.test_plant as plant_tests
import api.test_rotations as rotation_tests
from api.config import (
    KINDS_OF_YEAR_RECORD_FILE,
    ConfigError,
    load_config,
)
from api.main import create_app
from api.plant import NO_RECORD, RECORD_CONTRACT, RECORD_STATE, _record_source
from api.plant import NO_RECORD_ID as API_NO_RECORD_ID
from api.plant_layer import DiscoveredPlantLayer, not_built_body
from api.ports import Missing, PlantParts
from contracts.plant_answer import PlantAnswer
from economics.plant import NO_RECORD_ID as ECONOMICS_NO_RECORD_ID
from economics.plant import RECORD_NOT_CONFIGURED, answer_plant
from kinds_of_year import load_record as read_record_file

ROOT = Path(__file__).parent.parent
PLANT_ROUTE = "/api/plant/run"
ABSENT_MODULE = "PLACEHOLDER_absent_plant_module"
# PLACEHOLDER: example data, not a date a record was read on. api/config.py
# asks the record for a non-blank date_read; the record of
# economics/test_plant.py has none.
PLACEHOLDER_DATE_READ = "PLACEHOLDER date read"


def load_record() -> dict[str, Any]:
    """The PLACEHOLDER record of economics/test_plant.py, with a date_read.

    D240 (5) of #77 (#422): no ONI record is shipped, so the tests that read
    the committed record read this one instead; none of its values is ONI.
    """
    record = plant_tests.load_record()
    record["date_read"] = PLACEHOLDER_DATE_READ
    return record


@pytest.fixture
def record_file(tmp_path: Path) -> Path:
    """The PLACEHOLDER record written to a file, as a person would configure one."""
    path = tmp_path / "PLACEHOLDER_record.json"
    path.write_text(json.dumps(load_record()), encoding="utf-8")
    return path


def _app(**kwargs: Any) -> TestClient:
    """An app on the fakes of api/test_rotations.py, as the other api tests."""
    kwargs.setdefault("settings", rotation_tests.PERIOD)
    kwargs.setdefault("climate", rotation_tests.FakeClimate())
    kwargs.setdefault("soil_slope", rotation_tests.FakeSoilSlope())
    kwargs.setdefault("engines", rotation_tests.FakeEngines())
    return TestClient(create_app([], **kwargs), raise_server_exceptions=False)


def _other_routes_answer(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    response = client.post(rotation_tests.ROUTE, json=rotation_tests.BODY)
    assert response.status_code == 200, response.text


def _record_row(data: dict[str, Any]) -> dict[str, Any]:
    rows = [s for s in data["sources"] if s["contract"] == RECORD_CONTRACT]
    assert len(rows) == 1
    return rows[0]


# --- a1: a plant layer whose function is absent -------------------------------------


@pytest.mark.parametrize(
    "layer",
    [
        DiscoveredPlantLayer(plant_module=ABSENT_MODULE),
        DiscoveredPlantLayer(plant_function="PLACEHOLDER_absent_function"),
        DiscoveredPlantLayer(contract_module=ABSENT_MODULE),
    ],
    ids=["module-absent", "function-absent", "contract-absent"],
)
def test_a1_an_absent_plant_layer_is_not_built_and_the_other_routes_answer(layer):
    client = _app(plant_layer=layer)
    _other_routes_answer(client)
    response = client.post(PLANT_ROUTE, json=plant_tests.REQUEST)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"answer", "answer_missing"}
    assert data["answer"] is None
    assert set(data["answer_missing"]) == {"reason", "detail"}
    assert data["answer_missing"]["reason"] == "NOT_AVAILABLE"
    assert data["answer_missing"]["detail"]
    # The detail never repeats a submitted value.
    for text in (
        plant_tests.REQUEST["site"]["case_id"],
        plant_tests.REQUEST["site"]["field_id"],
    ):
        assert text not in data["answer_missing"]["detail"]
    # R27: the body is exactly the one not_built_body writes for its Missing.
    missing = Missing(reason="NOT_AVAILABLE", detail=data["answer_missing"]["detail"])
    assert data == not_built_body(missing)


def test_a1_not_built_calls_no_source_and_no_engine():
    climate, soil = plant_tests.FakeClimate(), plant_tests.FakeSoilSlope()
    engines = plant_tests.FakeEngines()
    client = _app(
        climate=climate,
        soil_slope=soil,
        engines=engines,
        plant_layer=DiscoveredPlantLayer(plant_module=ABSENT_MODULE),
    )
    response = client.post(PLANT_ROUTE, json=plant_tests.REQUEST)
    assert response.json()["answer"] is None
    assert response.json()["answer_missing"]["reason"] == "NOT_AVAILABLE"
    assert (climate.requests, soil.calls, engines.calls) == ([], [], [])


# --- a2: a plant layer module that raises at import ---------------------------------


@pytest.fixture
def broken_module(tmp_path, monkeypatch):
    """A module on sys.path that raises at import (not a missing module)."""
    name = "PLACEHOLDER_broken_plant_module"
    (tmp_path / f"{name}.py").write_text(
        'raise RuntimeError("PLACEHOLDER_SECRET_IMPORT_TEXT")\n', encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


@pytest.fixture
def module_importing_an_absent_one(tmp_path, monkeypatch):
    """A module that exists and imports another that does not: a defect."""
    name = "PLACEHOLDER_plant_module_with_absent_import"
    (tmp_path / f"{name}.py").write_text(
        "import PLACEHOLDER_absent_dependency  # noqa: F401\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


@pytest.mark.parametrize("which", ["plant_module", "contract_module"])
def test_a2_a_module_that_raises_at_import_is_500_on_the_plant_route_only(
    broken_module, which
):
    client = _app(plant_layer=DiscoveredPlantLayer(**{which: broken_module}))
    response = client.post(PLANT_ROUTE, json=plant_tests.REQUEST)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "PLACEHOLDER_SECRET_IMPORT_TEXT" not in response.text
    _other_routes_answer(client)


def test_a2_a_module_importing_an_absent_module_is_a_defect(
    module_importing_an_absent_one,
):
    client = _app(
        plant_layer=DiscoveredPlantLayer(plant_module=module_importing_an_absent_one)
    )
    response = client.post(PLANT_ROUTE, json=plant_tests.REQUEST)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    _other_routes_answer(client)


# --- a3: importing api.app imports none of the plant layer --------------------------


def test_a3_importing_the_app_leaves_the_plant_layer_unimported():
    code = (
        "import sys, json\n"
        "import api.app, api.main\n"
        "names = ('economics', 'kinds_of_year', 'contracts.plant_answer')\n"
        "print(json.dumps([n for n in names if n in sys.modules]))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "", "PYTHONPATH": str(ROOT)},
    )
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []


# --- a4: KINDS_OF_YEAR_RECORD_FILE unset or blank -----------------------------------


@pytest.mark.parametrize("environ", [{}, {KINDS_OF_YEAR_RECORD_FILE: "   "}])
def test_a4_unset_or_blank_means_no_record_and_no_import(environ):
    code = (
        "import sys, json\n"
        "from api.config import load_config\n"
        f"config = load_config({environ!r})\n"
        "print(json.dumps([config.kinds_of_year_record is None,\n"
        "                  'kinds_of_year' in sys.modules]))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "", "PYTHONPATH": str(ROOT)},
    )
    assert json.loads(done.stdout.strip().splitlines()[-1]) == [True, False]


@pytest.mark.parametrize("with_period", [True, False])
def test_a4_without_a_record_a_plant_request_answers_with_every_kind_missing(
    with_period,
):
    config = load_config({})
    assert config.kinds_of_year_record is None
    kwargs: dict[str, Any] = {"kinds_of_year_record": config.kinds_of_year_record}
    if not with_period:
        kwargs["settings"] = config.run_settings
    data = plant_tests.answered(
        plant_tests.client(**kwargs).post(PLANT_ROUTE, json=plant_tests.REQUEST)
    )
    plant_tests.checked(plant_tests.REQUEST, data)
    years = data["kinds_of_year"]["years"]
    assert years
    for year in years:
        assert year["kind"] is None
        assert year["missing_reason"] == "NOT_AVAILABLE"
        # Fix round 1 (F6): the kind of year carries the sentence of
        # economics/, which never names the variable; the record's source
        # row (below) still names it.
        assert year["detail"].startswith(RECORD_NOT_CONFIGURED)
        assert KINDS_OF_YEAR_RECORD_FILE not in year["detail"]
    # Main's contract requires a source text (#424): the id of the record's
    # source row, the same rule as for a record without id (F2).
    assert data["kinds_of_year"]["source"] == API_NO_RECORD_ID
    assert set(data["kinds_of_year"]["counts"].values()) == {None}
    row = _record_row(data)
    assert row["id"] == data["kinds_of_year"]["source"]
    assert row["state"] == "unavailable"
    assert row["missing_reason"] == "NOT_AVAILABLE"
    assert row["detail"] == NO_RECORD
    assert KINDS_OF_YEAR_RECORD_FILE in NO_RECORD
    # Every soil-loss mean by kind of year is missing with a reason, never 0
    # (the margins follow through economics/ as for any missing kind).
    for option in data["options"]:
        for kind in ("el_nino", "neutral", "la_nina"):
            item = option["soil_loss"][kind]
            assert item["value"] is None
            assert item["reason"] is not None


# --- a5: KINDS_OF_YEAR_RECORD_FILE set to a file that is refused ---------------------


def _refused(environ: dict[str, str]) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        load_config(environ)
    assert KINDS_OF_YEAR_RECORD_FILE in str(caught.value)
    return caught.value


def test_a5_a_file_that_does_not_exist_is_refused(tmp_path):
    _refused({KINDS_OF_YEAR_RECORD_FILE: str(tmp_path / "absent.json")})


def test_a5_a_file_that_is_not_json_is_refused(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("PLACEHOLDER: not JSON", encoding="utf-8")
    error = _refused({KINDS_OF_YEAR_RECORD_FILE: str(path)})
    assert "PLACEHOLDER: not JSON" not in str(error)


@pytest.mark.parametrize(
    "drop", ["id", "date_read", "reference", "seasons", "threshold"]
)
def test_a5_a_record_without_a_field_the_plant_layer_reads_is_refused(tmp_path, drop):
    record = load_record()
    del record[drop]
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    error = _refused({KINDS_OF_YEAR_RECORD_FILE: str(path)})
    assert drop in str(error)


def test_a5_a_json_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("[]", encoding="utf-8")
    _refused({KINDS_OF_YEAR_RECORD_FILE: str(path)})


# --- a6: set to the committed record ------------------------------------------------


def test_a6_the_configured_record_is_passed_through(record_file):
    config = load_config({KINDS_OF_YEAR_RECORD_FILE: str(record_file)})
    committed = read_record_file(record_file)
    assert config.kinds_of_year_record == committed
    data = plant_tests.answered(
        plant_tests.client(kinds_of_year_record=config.kinds_of_year_record).post(
            PLANT_ROUTE, json=plant_tests.REQUEST
        )
    )
    plant_tests.checked(plant_tests.REQUEST, data)
    row = _record_row(data)
    assert row["state"] == RECORD_STATE == "cached"
    assert row["id"] == committed["id"]
    assert row["missing_reason"] is None
    assert committed["date_read"] in row["detail"]
    assert data["kinds_of_year"]["source"] == committed["id"]


def test_a6_an_injected_record_without_date_read_gives_a_row_without_a_date():
    record = load_record()
    del record["date_read"]
    row = _record_source(record)
    assert row["state"] == "cached"
    assert "None" not in row["detail"]
    assert "read on" not in row["detail"]
    record = load_record()
    del record["id"]
    row = _record_source(record)  # never a KeyError
    assert row["id"]
    assert "None" not in row["detail"]


# --- a7: an injected plant layer is the one called ----------------------------------


class FakePlantLayer:
    """Gives the real request model and a fake answer function; records calls."""

    def __init__(self) -> None:
        from contracts.plant_answer import PlantRequest

        self.calls: list[dict[str, Any]] = []
        self.request_model = PlantRequest

    def parts(self) -> PlantParts | Missing:
        def answer_plant(request, runs, **kwargs):
            self.calls.append({"request": request, "runs": runs, **kwargs})
            return PlantAnswer.model_validate(plant_tests.ANSWER)

        return PlantParts(
            request_model=self.request_model,
            answer_model=PlantAnswer,
            answer_plant=answer_plant,
        )


def test_a7_an_injected_plant_layer_is_the_one_called():
    layer = FakePlantLayer()
    client = plant_tests.client(plant_layer=layer)
    response = client.post(PLANT_ROUTE, json=plant_tests.REQUEST)
    assert response.status_code == 200, response.text
    assert response.json() == PlantAnswer.model_validate(plant_tests.ANSWER).model_dump(
        mode="json"
    )
    assert len(layer.calls) == 1
    call = layer.calls[0]
    assert call["request"].site.case_id == plant_tests.REQUEST["site"]["case_id"]
    assert len(call["runs"]) == len(plant_tests.REQUEST["rotations"])


def test_a7_a_layer_that_returns_another_type_is_500():
    class Wrong(FakePlantLayer):
        def parts(self):
            return PlantParts(
                request_model=self.request_model,
                answer_model=PlantAnswer,
                answer_plant=lambda request, runs, **kwargs: {"contract": "x"},
            )

    response = plant_tests.client(plant_layer=Wrong()).post(
        PLANT_ROUTE, json=plant_tests.REQUEST
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


# --- fix round 1 of the review (PROPOSED) -------------------------------------------


def _write_record(tmp_path: Path, record: Any) -> dict[str, str]:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return {KINDS_OF_YEAR_RECORD_FILE: str(path)}


def test_f2_an_injected_record_without_id_gives_an_answer_not_a_500():
    record = load_record()
    del record["id"]
    data = plant_tests.answered(
        plant_tests.client(kinds_of_year_record=record).post(
            PLANT_ROUTE, json=plant_tests.REQUEST
        )
    )
    plant_tests.checked(plant_tests.REQUEST, data)
    # One rule for the id in economics/ and in api/: the answer's source and
    # the record's source row name the record the same way.
    assert ECONOMICS_NO_RECORD_ID == API_NO_RECORD_ID
    assert data["kinds_of_year"]["source"] == API_NO_RECORD_ID
    assert _record_row(data)["id"] == API_NO_RECORD_ID


def test_f3_a_threshold_that_is_text_is_refused_at_start_up(tmp_path):
    record = load_record()
    record["threshold"] = str(record["threshold"])
    error = _refused(_write_record(tmp_path, record))
    assert "threshold" in str(error)


def test_f3_season_rows_that_are_not_rows_are_refused_at_start_up(tmp_path):
    record = load_record()
    record["seasons"] = [1, 2]
    _refused(_write_record(tmp_path, record))


def test_f3_a_season_row_the_classification_refuses_is_refused_at_start_up(tmp_path):
    record = load_record()
    record["seasons"] = [*record["seasons"], dict(record["seasons"][0])]
    error = _refused(_write_record(tmp_path, record))
    assert "duplicated" in str(error)


@pytest.mark.parametrize("broken", ["absent", "raises"])
def test_f4_a_kinds_of_year_that_cannot_be_imported_is_a_config_error(
    monkeypatch, broken, record_file
):
    for name in list(sys.modules):
        if name == "kinds_of_year" or name.startswith("kinds_of_year."):
            monkeypatch.delitem(sys.modules, name)
    if broken == "absent":
        # None in sys.modules: the import raises ImportError.
        monkeypatch.setitem(sys.modules, "kinds_of_year", None)
    else:
        import builtins

        real_import = builtins.__import__

        def failing(name, *args, **kwargs):
            if name == "kinds_of_year" or name.startswith("kinds_of_year."):
                raise ImportError("PLACEHOLDER broken kinds_of_year")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", failing)
    with pytest.raises(ConfigError) as caught:
        load_config({KINDS_OF_YEAR_RECORD_FILE: str(record_file)})
    assert KINDS_OF_YEAR_RECORD_FILE in str(caught.value)
    assert isinstance(caught.value.__cause__, ImportError)


def test_f5_the_file_is_read_once_and_not_through_load_record(monkeypatch, record_file):
    import kinds_of_year

    def never(*args, **kwargs):
        raise AssertionError("load_record is not called by load_config")

    monkeypatch.setattr(kinds_of_year, "load_record", never)
    config = load_config({KINDS_OF_YEAR_RECORD_FILE: str(record_file)})
    assert config.kinds_of_year_record == read_record_file(record_file)


def test_f5_a_file_that_is_not_utf8_is_refused(tmp_path):
    path = tmp_path / "record.json"
    path.write_bytes(b"\xff\xfe\x00")
    _refused({KINDS_OF_YEAR_RECORD_FILE: str(path)})


def test_f6_answer_plant_takes_no_record_missing():
    import inspect

    assert "record_missing" not in inspect.signature(answer_plant).parameters
    assert KINDS_OF_YEAR_RECORD_FILE not in RECORD_NOT_CONFIGURED


def test_f7_the_record_row_names_the_record_and_its_date_never_a_path():
    record = load_record()
    row = _record_source(record)
    expected = "transcribed record " + record["id"] + ", read on "
    assert row["detail"] == expected + record["date_read"]
    assert "/" not in row["detail"]
    assert ".json" not in row["detail"]
    del record["date_read"]
    assert _record_source(record)["detail"] == "transcribed record " + record["id"]
