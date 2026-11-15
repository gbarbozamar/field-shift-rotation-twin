"""Acceptance test of ``POST /api/decisions/run``.

Run with ``uv run pytest api/test_decisions.py`` from the repository root.

Status: PROPOSED test cases (unit ``l2/decision-route``). Every number is an
obvious placeholder and every identifier is ``PLACEHOLDER_...`` or one of the
contract examples. The decision layer is a fake that writes the smallest
document the contract accepts; no test asserts a value of the science.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from importlib.abc import MetaPathFinder
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api.decision_layer import NamedDecisionLayer
from api.engines import discover_engine_functions
from api.main import create_app
from api.ports import (
    EnginesResult,
    ErrorDetail,
    Missing,
    ModuleStatus,
    PhaseResult,
    RunSettings,
)
from api.test_decision_layer import smallest_document
from api.test_rotations import PERIOD, FakeClimate, FakeSoilSlope
from contracts.decision_output import DecisionOutput
from contracts.inputs import SiteClimate
from contracts.results.models import ResultsPerRotation, ResultsTable

ROOT = Path(__file__).parent.parent
ROUTE = "/api/decisions/run"
ORIGIN = "http://localhost:5173"

RESULT = json.loads(
    (
        ROOT / "contracts/results/examples/PLACEHOLDER_results_per_rotation.json"
    ).read_text(encoding="utf-8")
)
ROTATION = json.loads(
    (
        ROOT
        / "contracts/rotation_definition/examples/PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)
CASE, FIELD = RESULT["case_id"], RESULT["field_id"]
FIRST, SECOND = "PLACEHOLDER_rotation_a", "PLACEHOLDER_rotation_b"
SITE = {"case_id": CASE, "field_id": FIELD, "latitude": 1.0, "longitude": 2.0}
MODULES = (ModuleStatus(id="PLACEHOLDER_MODULE", state="available"),)


def rotation(rotation_id: str, **changes: Any) -> dict[str, Any]:
    document = copy.deepcopy(ROTATION)
    document.update({"case_id": CASE, "field_id": FIELD, "rotation_id": rotation_id})
    document.update(changes)
    return document


BODY = {"site": SITE, "rotations": [rotation(FIRST), rotation(SECOND)]}


def result_of(rotation_id: str) -> ResultsPerRotation:
    return ResultsPerRotation.model_validate({**RESULT, "rotation_id": rotation_id})


def with_result(rotation_id: str, phases: int = 1) -> EnginesResult:
    one = EnginesResult(
        calendar=None,
        result=result_of(rotation_id),
        result_missing=None,
        modules=MODULES,
        values_present=1,
        values_missing=1,
    )
    if phases == 1:
        return one
    return EnginesResult(
        calendar=None,
        result=one.result,
        result_missing=None,
        modules=MODULES,
        values_present=1,
        values_missing=1,
        phases=tuple(
            PhaseResult(scenario_id=f"phase_{index}", first_ag_year=None, result=one)
            for index in range(1, phases + 1)
        ),
    )


WITHOUT_RESULT = EnginesResult(
    calendar=None,
    result=None,
    result_missing=Missing(reason="MISSING_INPUT", detail="PLACEHOLDER_DETAIL"),
    modules=(
        ModuleStatus(
            id="PLACEHOLDER_MODULE", state="not_available", reason="MISSING_INPUT"
        ),
    ),
)


class FakeEngines:
    """Answers by the ``rotation_id`` of the rotation it is given."""

    def __init__(self, answers: dict[str, EnginesResult] | None = None, raises=False):
        self.answers = answers or {
            FIRST: with_result(FIRST),
            SECOND: with_result(SECOND, 2),
        }
        self.raises = raises
        self.calls: list[tuple[Any, ClimateResult, Any]] = []

    def run(self, rotation, climate, soil_slope) -> EnginesResult:
        self.calls.append((rotation, climate, soil_slope))
        if self.raises:
            raise RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT")
        return self.answers[rotation["rotation_id"]]


class FakeDecisionLayer:
    def __init__(self, answer: Missing | None = None, raises: bool = False) -> None:
        self.answer = answer
        self.raises = raises
        self.calls: list[tuple[ResultsTable, bool]] = []

    def decide(self, table: ResultsTable, *, example_data: bool):
        self.calls.append((table, example_data))
        if self.raises:
            raise RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT")
        if self.answer is not None:
            return self.answer
        return smallest_document(table, example_data=example_data)


class AcceptAll:
    def validate(self, rotation) -> list[ErrorDetail]:
        return []


def client(**kwargs: Any) -> TestClient:
    kwargs.setdefault("settings", PERIOD)
    kwargs.setdefault("climate", FakeClimate())
    kwargs.setdefault("soil_slope", FakeSoilSlope())
    kwargs.setdefault("engines", FakeEngines())
    kwargs.setdefault("decision_layer", FakeDecisionLayer())
    return TestClient(create_app([ORIGIN], **kwargs), raise_server_exceptions=False)


# --- a valid request --------------------------------------------------------------------


def test_two_rotations_answer_200_with_the_decision_document():
    climate, soil, engines, layer = (
        FakeClimate(),
        FakeSoilSlope(),
        FakeEngines(),
        FakeDecisionLayer(),
    )
    response = client(
        climate=climate, soil_slope=soil, engines=engines, decision_layer=layer
    ).post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision_missing"] is None
    # The document loads into the contract from the JSON of the response and
    # writes back unchanged.
    document = DecisionOutput.model_validate_json(json.dumps(body["decision"]))
    assert document.model_dump(mode="json") == body["decision"]
    assert sorted(document.rotations) == [FIRST, SECOND]
    # One climate request and one soil request; each rotation runs once on them.
    assert len(climate.requests) == 1
    assert soil.calls == [(CASE, FIELD)]
    assert [call[0]["rotation_id"] for call in engines.calls] == [FIRST, SECOND]
    assert engines.calls[0][1] is engines.calls[1][1]
    assert engines.calls[0][2] is engines.calls[1][2]
    # The decision layer got one table.
    ((table, example_data),) = layer.calls
    # The rotation example and the two site examples all say example_data: true.
    assert example_data is True
    assert sorted({row.scenario_id for row in table.rows}) == [
        "phase_1+phase_1",
        "phase_1+phase_2",
    ]


def test_the_legend_of_the_scenarios_names_the_phase_of_each_rotation():
    body = client().post(ROUTE, json=BODY).json()
    assert body["scenarios"] == [
        {
            "scenario_id": "phase_1+phase_1",
            "phases": [
                {"rotation_id": FIRST, "phase": "phase_1"},
                {"rotation_id": SECOND, "phase": "phase_1"},
            ],
        },
        {
            "scenario_id": "phase_1+phase_2",
            "phases": [
                {"rotation_id": FIRST, "phase": "phase_1"},
                {"rotation_id": SECOND, "phase": "phase_2"},
            ],
        },
    ]
    assert sorted(body["decision"]["scenarios"]) == [
        s["scenario_id"] for s in body["scenarios"]
    ]


def test_each_rotation_is_summarised_without_its_result_or_calendar():
    body = client().post(ROUTE, json=BODY).json()
    first, second = body["rotations"]
    assert first["rotation_id"] == FIRST and second["rotation_id"] == SECOND
    assert set(first) == {
        "rotation_id",
        "outcome",
        "result_missing",
        "modules",
        "phases",
    }
    assert first["outcome"] == "partial"
    assert first["modules"] == [
        {
            "id": "PLACEHOLDER_MODULE",
            "state": "available",
            "reason": None,
            "detail": None,
        }
    ]
    assert [p["scenario_id"] for p in first["phases"]] == ["phase_1"]
    assert [p["scenario_id"] for p in second["phases"]] == ["phase_1", "phase_2"]
    assert [s["id"] for s in body["sources"]] == [
        "PLACEHOLDER_CLIMATE",
        "PLACEHOLDER_SOIL",
    ]


def test_the_document_keeps_every_null():
    response = client().post(ROUTE, json=BODY)
    assert '"value":null' in response.text.replace(" ", "")
    state = response.json()["decision"]["state"]
    assert "value" in state and state["value"] is None
    assert state["missing"]["reason"] == "NOT_AVAILABLE"


class MarkedClimate(FakeClimate):
    """The climate example with its own ``example_data`` mark set, state "fresh"."""

    def __init__(self, mark: bool) -> None:
        super().__init__("fresh")
        self.mark = mark

    def get_climate(self, request):
        answer = super().get_climate(request)
        return ClimateResult(
            data=answer.data.model_copy(update={"example_data": self.mark}),
            source=answer.source,
        )


class MarkedSoil(FakeSoilSlope):
    """The soil-and-slope example with its own mark set, and state "fresh"."""

    def __init__(self, mark: bool) -> None:
        super().__init__()
        self.mark = mark

    def get_soil_slope(self, case_id, field_id):
        answer = super().get_soil_slope(case_id, field_id)
        return type(answer)(
            data=answer.data.model_copy(update={"example_data": self.mark}),
            source=SourceInfo(
                id="PLACEHOLDER_SOIL", contract="site_data_soil_slope", state="fresh"
            ),
        )


@pytest.mark.parametrize(
    ("rotation_mark", "climate_mark", "soil_mark", "expected"),
    [
        (False, False, False, False),
        (True, False, False, True),
        (False, True, False, True),
        (False, False, True, True),
    ],
)
def test_the_example_mark_is_read_from_each_input(
    rotation_mark, climate_mark, soil_mark, expected
):
    """The mark the rotations, the climate and the soil carry themselves, not
    the state of the sources (both sources here are "fresh")."""
    layer = FakeDecisionLayer()
    body = {
        "site": SITE,
        "rotations": [
            rotation(FIRST, example_data=rotation_mark),
            rotation(SECOND, example_data=False),
        ],
    }
    response = client(
        climate=MarkedClimate(climate_mark),
        soil_slope=MarkedSoil(soil_mark),
        decision_layer=layer,
    ).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    assert layer.calls[0][1] is expected
    assert response.json()["decision"]["example_data"] is expected


# --- a valid request without a decision --------------------------------------------------


def test_the_decision_layer_not_built_answers_200_with_its_reason():
    response = client(decision_layer=NamedDecisionLayer(None)).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] is None
    assert body["decision_missing"]["reason"] == "NOT_AVAILABLE"
    assert (
        "decision.output.assemble_decision_output" in body["decision_missing"]["detail"]
    )
    # The table was built: its legend is there.
    assert [s["scenario_id"] for s in body["scenarios"]] == [
        "phase_1+phase_1",
        "phase_1+phase_2",
    ]


def test_a_rotation_without_a_result_answers_200_and_no_decision():
    layer = FakeDecisionLayer()
    engines = FakeEngines({FIRST: with_result(FIRST), SECOND: WITHOUT_RESULT})
    response = client(engines=engines, decision_layer=layer).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] is None
    assert body["decision_missing"]["reason"] == "MISSING_INPUT"
    assert "rotation 2 of the request" in body["decision_missing"]["detail"]
    assert SECOND not in body["decision_missing"]["detail"]
    assert body["scenarios"] == []
    assert layer.calls == []
    assert body["rotations"][1]["outcome"] == "no_result"


def test_the_decision_layer_may_answer_a_typed_absence():
    layer = FakeDecisionLayer(Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER"))
    body = client(decision_layer=layer).post(ROUTE, json=BODY).json()
    assert body["decision"] is None
    assert body["decision_missing"] == {
        "reason": "NOT_COMPUTABLE",
        "detail": "PLACEHOLDER",
    }


# --- invalid requests: 422, nothing is called ---------------------------------------------


def _nothing_called(climate: FakeClimate, engines: FakeEngines) -> None:
    assert climate.requests == []
    assert engines.calls == []


@pytest.mark.parametrize("count", [0, 1, 3])
def test_a_request_without_exactly_two_rotations_is_invalid(count):
    climate, engines = FakeClimate(), FakeEngines()
    rotations = [rotation(f"PLACEHOLDER_rotation_{i}") for i in range(count)]
    response = client(climate=climate, engines=engines).post(
        ROUTE, json={"site": SITE, "rotations": rotations}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    _nothing_called(climate, engines)


def test_problems_of_a_rotation_are_reported_under_its_index():
    class OneProblem:
        def validate(self, rotation):
            if rotation["rotation_id"] != SECOND:
                return []
            return [
                ErrorDetail(path="components.0", code="PLACEHOLDER_CODE", message="m")
            ]

    climate, engines = FakeClimate(), FakeEngines()
    response = client(
        climate=climate, engines=engines, rotation_validator=OneProblem()
    ).post(ROUTE, json=BODY)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert error["details"] == [
        {"path": "rotations.1.components.0", "code": "PLACEHOLDER_CODE", "message": "m"}
    ]
    _nothing_called(climate, engines)


def test_the_default_validator_checks_each_rotation():
    broken = rotation(SECOND)
    del broken["components"]
    response = client(rotation_validator=None).post(
        ROUTE, json={"site": SITE, "rotations": [rotation(FIRST), broken]}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert all(d["path"].startswith("rotations.1") for d in error["details"])


def test_one_rotation_id_twice_is_invalid_and_its_value_is_not_repeated():
    climate, engines = FakeClimate(), FakeEngines()
    response = client(climate=climate, engines=engines).post(
        ROUTE, json={"site": SITE, "rotations": [rotation(FIRST), rotation(FIRST)]}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert error["details"] == [
        {
            "path": "rotations.1.rotation_id",
            "code": "repeated",
            "message": "this rotation_id is the rotation_id of an earlier rotation",
        }
    ]
    assert FIRST not in response.text
    _nothing_called(climate, engines)


@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_a_rotation_of_another_case_or_field_than_the_site_is_invalid(field):
    climate, engines = FakeClimate(), FakeEngines()
    other = rotation(SECOND, **{field: "PLACEHOLDER_OTHER"})
    response = client(
        climate=climate, engines=engines, rotation_validator=AcceptAll()
    ).post(ROUTE, json={"site": SITE, "rotations": [rotation(FIRST), other]})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert error["details"] == [
        {
            "path": f"rotations.1.{field}",
            "code": "not_the_site",
            "message": f"the {field} of this rotation is not the {field} of site",
        }
    ]
    assert "PLACEHOLDER_OTHER" not in response.text
    _nothing_called(climate, engines)


def test_an_invalid_site_is_site_invalid():
    response = client().post(ROUTE, json={**BODY, "site": {**SITE, "latitude": 1000.0}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SITE_INVALID"


def test_an_unknown_field_is_invalid():
    response = client().post(ROUTE, json={**BODY, "PLACEHOLDER_extra": 1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


# --- defects of the engines: 500 ---------------------------------------------------------


def _is_internal_error(response) -> None:
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_an_engine_that_raises_answers_500_with_cors_and_no_exception_text():
    response = client(engines=FakeEngines(raises=True)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _is_internal_error(response)


# --- a decision layer that fails: a typed absence, never a 500 ----------------------------


def _layer_failed(response, kind: str) -> None:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] is None
    assert body["decision_missing"]["reason"] == "NOT_AVAILABLE"
    assert f"failed ({kind})" in body["decision_missing"]["detail"]
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text
    assert "PLACEHOLDER_other" not in response.text
    # The table was built: the legend and the rotations are still there.
    assert len(body["scenarios"]) == 2
    assert len(body["rotations"]) == 2


def test_a_decision_layer_that_raises_answers_200_with_its_absence():
    response = client(decision_layer=FakeDecisionLayer(raises=True)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _layer_failed(response, "RuntimeError")


def test_any_injected_layer_is_checked_by_the_route():
    """A layer that is not the default one and returns a document whose
    scenarios are not those of the table: the route's own check answers it."""

    class Mismatched(FakeDecisionLayer):
        def decide(self, table, *, example_data):
            return smallest_document(
                table, example_data=example_data, scenarios=["phase_1+phase_1"]
            )

    response = client(decision_layer=Mismatched()).post(ROUTE, json=BODY)
    _layer_failed(response, "TypeError")


def test_a_decision_function_that_returns_another_document_answers_its_absence():
    def another(table, *, example_data):
        return smallest_document(
            table, example_data=example_data, case_id="PLACEHOLDER_other"
        )

    response = client(decision_layer=NamedDecisionLayer(another)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _layer_failed(response, "TypeError")


class _BrokenDecisionModule(MetaPathFinder):
    """``decision.output`` exists and imports something absent."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "decision.output":
            raise ModuleNotFoundError(
                "No module named 'PLACEHOLDER_absent_dependency'",
                name="PLACEHOLDER_absent_dependency",
            )


@pytest.fixture
def broken_decision_module():
    saved = sys.modules.pop("decision.output", None)
    finder = _BrokenDecisionModule()
    sys.meta_path.insert(0, finder)
    yield
    sys.meta_path.remove(finder)
    sys.modules.pop("decision.output", None)
    if saved is not None:
        sys.modules["decision.output"] = saved


def test_a_decision_module_that_fails_to_import_breaks_nothing(broken_decision_module):
    """The default app starts, its other routes answer as before, and the
    decision route answers 200 with its absence."""
    app = create_app(
        [ORIGIN],
        climate=FakeClimate(),
        soil_slope=FakeSoilSlope(),
        engines=FakeEngines(),
        settings=PERIOD,
    )
    web = TestClient(app, raise_server_exceptions=False)
    assert web.get("/health").json() == {"status": "ok"}
    assert (
        web.post(
            "/api/rotations/run", json={"site": SITE, "rotation": rotation(FIRST)}
        ).status_code
        == 200
    )
    _layer_failed(web.post(ROUTE, json=BODY), "ModuleNotFoundError")


def test_the_default_app_imports_nothing_of_the_decision_layer_at_start_up():
    """Building the default app imports neither ``decision`` nor
    ``contracts.decision_output`` (checked in a fresh interpreter)."""
    code = (
        "import sys\n"
        "from api.main import create_app\n"
        "create_app([])\n"
        "names = [n for n in sys.modules if n == 'decision' or n.startswith('decision.')"
        " or n.startswith('contracts.decision_output')]\n"
        "print(names)\n"
    )
    answer = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert answer.stdout.strip() == "[]", answer.stdout + answer.stderr


def test_the_existing_route_is_unchanged_next_to_the_new_one():
    response = client().post(
        "/api/rotations/run", json={"site": SITE, "rotation": rotation(FIRST)}
    )
    assert response.status_code == 200
    assert response.json()["result"]["rotation_id"] == FIRST


# --- the engines of the repository ------------------------------------------------------


class ChainClimate:
    source_id = "PLACEHOLDER_chain_climate"
    contract = "site_data_climate"

    def __init__(self, data: SiteClimate) -> None:
        self.data = data

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=self.data,
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


def _two_years(document: dict[str, Any]) -> dict[str, Any]:
    """The rotation definition example with only c1, and c1 again one year later
    with the crop of c2 (PLACEHOLDER dates): two years, no component crossing
    the start of the agricultural year (as ``two_crops`` of api/test_phases.py)."""
    first = document["components"][0]
    again = copy.deepcopy(first)
    again.update(
        component_id="c2", position=2, crop_id=document["components"][1]["crop_id"]
    )
    again["sowing"]["date"] = "2028-11-15"
    again["harvest"]["date"] = "2029-04-10"
    document["components"] = [first, again]
    return document


def test_the_engines_of_the_repository_through_the_route():
    found = discover_engine_functions()
    if found.build_rotation_calendar is None or found.compute_soil_loss is None:
        pytest.skip("the calendar or the soil-loss engine is not built")
    if found.phase_calendar is None or found.list_phases is None:
        pytest.skip("the phase functions of engine.calendar.repeat are not built")
    examples = ROOT / "contracts" / "inputs" / "examples"
    climate = SiteClimate.model_validate_json(
        (examples / "PLACEHOLDER_chain_site_climate.json").read_text(encoding="utf-8")
    )
    series = climate.daily_series[0]
    first = copy.deepcopy(ROTATION)
    second = _two_years(copy.deepcopy(ROTATION))
    second["rotation_id"] = "PLACEHOLDER_rotation_two_years"
    layer = FakeDecisionLayer()
    app = create_app(
        [],
        climate=ChainClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            examples / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=series.start_date, end_date=series.end_date),
        decision_layer=layer,
    )
    site = {
        "case_id": first["case_id"],
        "field_id": first["field_id"],
        "latitude": climate.point.latitude.value,
        "longitude": climate.point.longitude.value,
    }
    response = TestClient(app).post(
        ROUTE, json={"site": site, "rotations": [first, second]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision_missing"] is None, body["decision_missing"]
    DecisionOutput.model_validate_json(json.dumps(body["decision"]))
    assert [s["scenario_id"] for s in body["scenarios"]] == [
        "phase_1+phase_1",
        "phase_1+phase_2",
    ]
    ((table, example_data),) = layer.calls
    assert example_data is True
    ResultsTable.model_validate_json(json.dumps(table.model_dump(mode="json")))
    assert {row.rotation_id for row in table.rows} == {
        first["rotation_id"],
        second["rotation_id"],
    }
