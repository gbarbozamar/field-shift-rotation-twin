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
from api import decisions
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
from api.rotations import SiteReference
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


# --- a decision layer that fails: a defect, 500 like an engine ---------------------------


def test_a_decision_layer_that_raises_answers_500():
    response = client(decision_layer=FakeDecisionLayer(raises=True)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _is_internal_error(response)


def test_any_injected_layer_is_checked_by_the_route():
    """A layer that is not the default one and returns a document whose
    scenarios are not those of the table: the route's own check refuses it."""

    class Mismatched(FakeDecisionLayer):
        def decide(self, table, *, example_data):
            return smallest_document(
                table, example_data=example_data, scenarios=["phase_1+phase_1"]
            )

    response = client(decision_layer=Mismatched()).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _is_internal_error(response)


def test_a_decision_function_that_returns_another_document_answers_500():
    def another(table, *, example_data):
        return smallest_document(
            table, example_data=example_data, case_id="PLACEHOLDER_other"
        )

    response = client(decision_layer=NamedDecisionLayer(another)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    _is_internal_error(response)
    assert "PLACEHOLDER_other" not in response.text


class _BrokenDecisionModule(MetaPathFinder):
    """``decision.output`` exists and raises when imported."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "decision.output":
            raise self.error


@pytest.fixture(
    params=[
        ModuleNotFoundError(
            "No module named 'PLACEHOLDER_absent_dependency'",
            name="PLACEHOLDER_absent_dependency",
        ),
        RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT"),
    ],
    ids=["imports-something-absent", "raises"],
)
def broken_decision_module(request):
    saved = sys.modules.pop("decision.output", None)
    finder = _BrokenDecisionModule(request.param)
    sys.meta_path.insert(0, finder)
    yield
    sys.meta_path.remove(finder)
    sys.modules.pop("decision.output", None)
    if saved is not None:
        sys.modules["decision.output"] = saved


def test_a_decision_module_that_fails_to_import_is_a_defect(broken_decision_module):
    """Not "not built": the decision route answers 500. The default app still
    starts and its other routes answer as before."""
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
    _is_internal_error(web.post(ROUTE, json=BODY, headers={"Origin": ORIGIN}))


def test_a_decision_module_that_is_absent_is_not_built(monkeypatch):
    """Only the absence of the module answers 200 ``NOT_AVAILABLE``."""
    monkeypatch.setattr(
        "api.decision_layer.DECISION_MODULE", "placeholder_absent_package.output"
    )
    app = create_app(
        [ORIGIN],
        climate=FakeClimate(),
        soil_slope=FakeSoilSlope(),
        engines=FakeEngines(),
        settings=PERIOD,
    )
    body = TestClient(app).post(ROUTE, json=BODY).json()
    assert body["decision"] is None
    assert body["decision_missing"]["reason"] == "NOT_AVAILABLE"


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


# --- phases: N x M scenarios, each rotation run once per phase --------------------------


class PhasesByRotation:
    """The phase functions of issue #221 as fakes, answering by the
    ``rotation_id`` of the calendar: hand-written phase calendars, never a
    computed rule (``api/test_phases.py``)."""

    def __init__(self, answers: dict[str, dict[int, Any]], counts: dict[str, int]):
        self.answers = answers
        self.counts = counts
        self.asked: list[tuple[str, int]] = []

    def phase_calendar(self, cal, p: int):
        self.asked.append((cal.rotation_id, p))
        return self.answers[cal.rotation_id][p]

    def list_phases(self, cal) -> list[int]:
        return list(range(self.counts[cal.rotation_id]))


def _as_rotation(cal, rotation_id: str):
    from contracts.inputs import RotationCalendar

    return RotationCalendar.model_validate(
        {**cal.model_dump(mode="json"), "rotation_id": rotation_id}
    )


def test_two_rotations_of_n_and_m_phases_give_n_times_m_scenarios():
    """N = 2 and M = 3: six scenarios ``phase_a+phase_b``; the engines of each
    rotation run once per phase of that rotation (2 + 3 runs), never once per
    scenario (6 x 2). Fakes only, with hand-written PLACEHOLDER calendars."""
    from api.engines import EngineFunctions, EntryPointEngines
    from api.test_engines import (
        CARBON_MODELS,
        SOIL_SLOPE_FILE,
        Fake,
        calendar,
        soil_loss,
        water,
    )
    from api.test_engines import PERIOD as ENGINES_PERIOD
    from api.test_engines import FakeClimate as EnginesClimate
    from api.test_phases import EXAMPLE_PHASES, THREE_YEARS, THREE_YEARS_PHASES

    two, three = "PLACEHOLDER-rotation-two-phases", "PLACEHOLDER-rotation-three-phases"
    calendars = {
        two: _as_rotation(calendar(), two),
        three: _as_rotation(THREE_YEARS, three),
    }
    phases = PhasesByRotation(
        answers={
            two: {p: _as_rotation(c, two) for p, c in EXAMPLE_PHASES.items()},
            three: {p: _as_rotation(c, three) for p, c in THREE_YEARS_PHASES.items()},
        },
        counts={two: 2, three: 3},
    )

    class CalendarByRotation(Fake):
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            (rotation,) = args
            return calendars[rotation.rotation_id]

    calendar_fn, soil_fn, water_fn = (
        CalendarByRotation(),
        Fake(soil_loss()),
        Fake(water()),
    )
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
            phase_calendar=phases.phase_calendar,
            list_phases=phases.list_phases,
        ),
        carbon_models=CARBON_MODELS,
    )
    site = {**SITE, "case_id": "PLACEHOLDER-case", "field_id": "PLACEHOLDER-field"}
    body = {
        "site": site,
        "rotations": [
            rotation(rotation_id, case_id=site["case_id"], field_id=site["field_id"])
            for rotation_id in (two, three)
        ],
    }
    layer = FakeDecisionLayer()
    response = client(
        engines=engines,
        climate=EnginesClimate(),
        soil_slope=ExampleSoilSlopeSource(SOIL_SLOPE_FILE),
        settings=ENGINES_PERIOD,
        decision_layer=layer,
    ).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["decision_missing"] is None, answer["decision_missing"]
    assert [s["scenario_id"] for s in answer["scenarios"]] == [
        f"phase_{a}+phase_{b}" for a in (1, 2) for b in (1, 2, 3)
    ]
    for item in answer["scenarios"]:
        a, b = item["scenario_id"].split("+")
        assert item["phases"] == [
            {"rotation_id": two, "phase": a},
            {"rotation_id": three, "phase": b},
        ]
    assert [len(r["phases"]) for r in answer["rotations"]] == [2, 3]
    assert sorted(answer["decision"]["scenarios"]) == sorted(
        s["scenario_id"] for s in answer["scenarios"]
    )
    # EP2 once per rotation; the phase function once per phase after the
    # first; EP1 and EP3 once per phase of each rotation.
    assert [args[0].rotation_id for args, _ in calendar_fn.calls] == [two, three]
    assert phases.asked == [(two, 1), (three, 1), (three, 2)]
    ran = [kwargs["calendar"].rotation_id for _, kwargs in soil_fn.calls]
    assert ran == [two] * 2 + [three] * 3
    assert [kwargs["calendar"].rotation_id for _, kwargs in water_fn.calls] == ran
    ((table, _),) = layer.calls
    assert len({row.scenario_id for row in table.rows}) == 6


def test_two_rotations_of_different_start_months_are_an_invalid_request():
    """D255 of #77: the rotations of a pair share one start month of the
    agricultural year; a pair whose months differ is ``422`` ``ROTATION_INVALID``
    naming ``ag_year_start.month`` of the second rotation, never its value, and
    no source, engine or decision layer is called."""
    first = rotation(FIRST)
    second = rotation(SECOND)
    month = first["ag_year_start"]["month"]
    other = month % 12 + 1
    second["ag_year_start"] = {**second["ag_year_start"], "month": other}
    engines = FakeEngines({FIRST: with_result(FIRST), SECOND: with_result(SECOND)})
    layer = FakeDecisionLayer()
    response = client(engines=engines, decision_layer=layer).post(
        ROUTE, json={"site": SITE, "rotations": [first, second]}
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert [(d["path"], d["code"]) for d in error["details"]] == [
        ("rotations.1.ag_year_start.month", "not_the_start_month")
    ]
    assert str(other) not in error["details"][0]["message"]
    assert engines.calls == []
    assert layer.calls == []


def test_two_rotations_of_the_same_start_month_pass_the_check():
    """The check of D255 refuses nothing when the months agree."""
    assert (
        decisions.identity_problems(
            SiteReference(**SITE), [rotation(FIRST), rotation(SECOND)]
        )
        == []
    )


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


def test_the_default_decision_layer_serves_a_document_through_the_route():
    """With nothing injected, the route finds ``decision.output`` by name and
    answers 200 with a document that validates as ``DecisionOutput``, marked
    example data since its inputs are (the engines of the repository on the
    PLACEHOLDER chain examples). No value of the science is asserted."""
    from contracts.decision_output.models import STATE_NAMES

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
    app = create_app(
        [],
        climate=ChainClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            examples / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=series.start_date, end_date=series.end_date),
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
    document = DecisionOutput.model_validate_json(json.dumps(body["decision"]))
    assert document.example_data is True
    assert document.rotations == [first["rotation_id"], second["rotation_id"]]
    assert sorted(document.scenarios) == [s["scenario_id"] for s in body["scenarios"]]
    (state,) = document.pair_states
    assert state.value in STATE_NAMES or (
        state.value is None and state.missing is not None
    )


# --- uncertain_inputs (D4 measure_first) ------------------------------------------------


def _soil_loss_result(
    rotation_id: str,
    value: float,
    low: float,
    high: float,
    carbon: tuple[float, float, float],
) -> ResultsPerRotation:
    payload = copy.deepcopy(RESULT)
    payload["rotation_id"] = rotation_id
    first_annual = payload["soil_loss"]["annual"][0]
    first_annual["value"] = value
    first_annual["range"]["low"] = low
    first_annual["range"]["high"] = high
    c_val, c_low, c_high = carbon
    first_carbon = payload["soil_carbon_trend"][0]
    first_carbon["value"] = c_val
    first_carbon["range"]["low"] = c_low
    first_carbon["range"]["high"] = c_high
    return ResultsPerRotation.model_validate(payload)


def _multi_phase_engines_for_sweep() -> FakeEngines:
    """Two rotations: FIRST has one phase, SECOND has two phases where phase_1
    is strictly better than FIRST and phase_2 crosses zero against FIRST."""
    first_res = _soil_loss_result(FIRST, 10.0, 9.5, 10.5, (0.5, 0.4, 0.6))
    second_p1 = _soil_loss_result(SECOND, 4.0, 3.5, 4.5, (1.0, 0.9, 1.1))
    second_p2 = _soil_loss_result(SECOND, 9.8, 9.3, 10.3, (1.0, 0.9, 1.1))

    def make_run(res: ResultsPerRotation) -> EnginesResult:
        return EnginesResult(
            calendar=None,
            result=res,
            result_missing=None,
            modules=MODULES,
            values_present=1,
            values_missing=1,
        )

    first_run = make_run(first_res)
    p1_run = make_run(second_p1)
    p2_run = make_run(second_p2)
    second_run = EnginesResult(
        calendar=None,
        result=second_p1,
        result_missing=None,
        modules=MODULES,
        values_present=1,
        values_missing=1,
        phases=(
            PhaseResult(scenario_id="phase_1", first_ag_year=None, result=p1_run),
            PhaseResult(scenario_id="phase_2", first_ag_year=None, result=p2_run),
        ),
    )
    return FakeEngines({FIRST: first_run, SECOND: second_run})


def test_omitted_or_null_uncertain_inputs_works_with_legacy_and_default_layers():
    """Backwards compatibility: a legacy DecisionLayer without ``uncertain_inputs``
    and the default DiscoveredDecisionLayer both return 200 with empty
    ``measure_first`` when ``uncertain_inputs`` is omitted or null."""
    for payload in (BODY, {**BODY, "uncertain_inputs": None}):
        legacy_response = client(decision_layer=FakeDecisionLayer()).post(
            ROUTE, json=payload
        )
        assert legacy_response.status_code == 200, legacy_response.text
        assert legacy_response.json()["decision"]["measure_first"] == []

        default_app = create_app(
            [ORIGIN],
            climate=FakeClimate(),
            soil_slope=FakeSoilSlope(),
            engines=FakeEngines(),
            settings=PERIOD,
        )
        default_response = TestClient(default_app).post(ROUTE, json=payload)
        assert default_response.status_code == 200, default_response.text
        assert default_response.json()["decision"]["measure_first"] == []


def test_valid_uncertain_inputs_populates_measure_first_through_default_layer():
    """Valid ``uncertain_inputs`` (single-scenario and nested-scenario entries)
    passes through ``DiscoveredDecisionLayer`` to ``assemble_decision_output``
    and populates ``measure_first`` in rank order."""
    app = create_app(
        [ORIGIN],
        climate=FakeClimate(),
        soil_slope=FakeSoilSlope(),
        engines=_multi_phase_engines_for_sweep(),
        settings=PERIOD,
    )
    payload = {
        **BODY,
        "uncertain_inputs": [
            {
                "name": "PLACEHOLDER_constant",
                "unit": "t ha-1 yr-1",
                "cell": [SECOND, "soil_loss", "ag_year", 2001, None, None],
                "values": [[4.0, ["phase_1+phase_1"]]],
            },
            {
                "name": "PLACEHOLDER_changer",
                "unit": "t ha-1 yr-1",
                "cell": [SECOND, "soil_loss", "ag_year", 2001, None, None],
                "values": [
                    [4.0, "phase_1+phase_1"],
                    [9.8, ["phase_1+phase_2"]],
                ],
            },
        ],
    }
    response = TestClient(app).post(ROUTE, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision_missing"] is None
    document = DecisionOutput.model_validate_json(json.dumps(body["decision"]))
    assert [item.rank for item in document.measure_first] == [1, 2]
    assert "PLACEHOLDER_changer" in document.measure_first[0].what
    assert "PLACEHOLDER_constant" in document.measure_first[1].what


def test_valid_empty_uncertain_inputs_is_accepted_and_forwarded():
    received: list[Any] = []

    class RecordingLayer:
        def decide(
            self, table: ResultsTable, *, example_data: bool, uncertain_inputs=None
        ):
            received.append(uncertain_inputs)
            return smallest_document(table, example_data=example_data)

    response = client(decision_layer=RecordingLayer()).post(
        ROUTE, json={**BODY, "uncertain_inputs": []}
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["measure_first"] == []
    assert received == [()]


def test_uncertain_inputs_with_legacy_layer_without_param_answers_500():
    """When ``uncertain_inputs`` is supplied, a layer or function that does not
    accept ``uncertain_inputs`` raises a clear defect -> 500 INTERNAL_ERROR."""
    payload = {
        **BODY,
        "uncertain_inputs": [
            {
                "name": "PLACEHOLDER_input",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [[1.0, "phase_1+phase_1"]],
            }
        ],
    }
    legacy_resp = client(decision_layer=FakeDecisionLayer()).post(
        ROUTE, json=payload, headers={"Origin": ORIGIN}
    )
    _is_internal_error(legacy_resp)

    def legacy_fn(table, *, example_data):
        return smallest_document(table, example_data=example_data)

    named_resp = client(decision_layer=NamedDecisionLayer(legacy_fn)).post(
        ROUTE, json=payload, headers={"Origin": ORIGIN}
    )
    _is_internal_error(named_resp)
    # The same NamedDecisionLayer still works when uncertain_inputs is omitted.
    ok_resp = client(decision_layer=NamedDecisionLayer(legacy_fn)).post(
        ROUTE, json=BODY
    )
    assert ok_resp.status_code == 200


@pytest.mark.parametrize(
    "bad_uncertain_inputs",
    [
        "PLACEHOLDER_not_a_list",
        {"name": "PLACEHOLDER_dict"},
        [{"name": "PLACEHOLDER_missing_fields"}],
        [
            {
                "name": "PLACEHOLDER_extra",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [],
                "PLACEHOLDER_unknown_field": 1,
            }
        ],
        [
            {
                "name": "   ",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [],
            }
        ],
        [
            {
                "name": "PLACEHOLDER_bad_cell",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss"],
                "values": [],
            }
        ],
        [
            {
                "name": "PLACEHOLDER_bool_year",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", True, None, None],
                "values": [],
            }
        ],
        [
            {
                "name": "PLACEHOLDER_bool_value",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [[True, "phase_1+phase_1"]],
            }
        ],
        [
            {
                "name": "PLACEHOLDER_empty_scenarios",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [[1.0, []]],
            }
        ],
        [
            {
                "name": "PLACEHOLDER_blank_scenario",
                "unit": "t ha-1 yr-1",
                "cell": [FIRST, "soil_loss", "ag_year", 2001, None, None],
                "values": [[1.0, "  "]],
            }
        ],
    ],
)
def test_invalid_uncertain_inputs_returns_422_and_calls_nothing(bad_uncertain_inputs):
    climate, engines, layer = FakeClimate(), FakeEngines(), FakeDecisionLayer()
    response = client(climate=climate, engines=engines, decision_layer=layer).post(
        ROUTE, json={**BODY, "uncertain_inputs": bad_uncertain_inputs}
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert any(d["path"].startswith("uncertain_inputs") for d in error["details"])
    _nothing_called(climate, engines)
    assert layer.calls == []
