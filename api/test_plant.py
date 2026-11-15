"""Acceptance test of ``POST /api/plant/run`` (unit l2/plant-route, brief S-018).

Run with ``uv run pytest api/test_plant.py`` from the repository root.

Status: PROPOSED test cases. Fakes only: the climate, the soil and slope and
the engines are fakes of api/test_rotations.py or written here; no network and
no real service. The soil loss per agricultural year the fake engines give is
the example data of contracts/plant_answer/README.md ("the soil loss per kind
of year of each rotation (14.0, 11.0, 8.0; 6.5, 5.0, 4.0; 4.0, 3.0, 2.5 t
ha-1 yr-1), the one soil-loss year left missing (2022 of
example-rotation-soybean-cover-pasture, reason MISSING_INPUT)"), placed on the
kinds of year of the example answer. Every expected value of case 1 is read
from the example answer file, never typed here.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.config import PARAMETERS_FOLDER, load_parameters
from api.main import create_app
from api.plant import EXTRA_KEY_SEGMENT, NO_FACTORY, REDACTED_MESSAGE
from api.ports import EnginesResult, ErrorDetail, Missing, ModuleStatus, RunSettings
from api.rain_stress import R_ID, rain_stress, scale_erosivity
from api.test_rotations import FakeClimate, FakeSoilSlope
from contracts.inputs.common import Value
from contracts.plant_answer import (
    PlantAnswer,
    PlantRequest,
    check_answer_against_request,
)
from contracts.results.models import ResultsPerRotation
from economics.test_plant import load_record

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "contracts" / "plant_answer" / "examples"
ROUTE = "/api/plant/run"
ORIGIN = "http://localhost:5173"

REQUEST = json.loads(
    (EXAMPLES / "PLACEHOLDER_plant_request.json").read_text(encoding="utf-8")
)
ANSWER = json.loads(
    (EXAMPLES / "PLACEHOLDER_plant_answer.json").read_text(encoding="utf-8")
)
RESULT_TEMPLATE = json.loads(
    (
        ROOT / "contracts/results/examples/PLACEHOLDER_results_per_rotation.json"
    ).read_text(encoding="utf-8")
)

SOYBEAN, COVER, PASTURE = (r["rotation_id"] for r in REQUEST["rotations"])
START_MONTH = ANSWER["kinds_of_year"]["start_month"]
KIND_OF = {y["ag_year"]: y["kind"] for y in ANSWER["kinds_of_year"]["years"]}
FIRST_YEAR, LAST_YEAR = min(KIND_OF), max(KIND_OF)
# The whole agricultural years FIRST_YEAR..LAST_YEAR with START_MONTH.
PERIOD = RunSettings(
    start_date=dt.date(FIRST_YEAR, START_MONTH, 1),
    end_date=dt.date(LAST_YEAR + 1, START_MONTH, 1) - dt.timedelta(days=1),
)

# Example data of contracts/plant_answer/README.md (see the module docstring).
SOURCE = ANSWER["options"][0]["soil_loss"]["average"]["sources"][0]
LEVELS = {
    SOYBEAN: {"el_nino": 14.0, "neutral": 11.0, "la_nina": 8.0},
    COVER: {"el_nino": 6.5, "neutral": 5.0, "la_nina": 4.0},
    PASTURE: {"el_nino": 4.0, "neutral": 3.0, "la_nina": 2.5},
}
MISSING_YEAR = {PASTURE: 2022}
MISSING_DETAIL = "PLACEHOLDER: example of a soil loss the engine did not give"
MODULES = (ModuleStatus(id="PLACEHOLDER_MODULE", state="available"),)
NOT_BUILT_DETAIL = "PLACEHOLDER: the erosion engine is not built in this test"


# --- fakes ------------------------------------------------------------------------


def _annual(rotation_id: str, year: int) -> dict[str, Any]:
    item = {
        "ag_year": year,
        "indicator": "soil_loss",
        "direction": "lower_is_better",
        "unit": "t ha-1 yr-1",
    }
    if MISSING_YEAR.get(rotation_id) == year:
        return {
            **item,
            "value": None,
            "missing": {"reason": "MISSING_INPUT", "detail": MISSING_DETAIL},
        }
    return {
        **item,
        "value": LEVELS[rotation_id][KIND_OF[year]],
        "range_missing": {"reason": "NOT_AVAILABLE"},
        "provenance": "DERIVED",
        "source": SOURCE,
    }


def _monthly(year: int) -> list[dict[str, Any]]:
    months = []
    for step in range(12):
        month = (START_MONTH - 1 + step) % 12 + 1
        calendar_year = year + (START_MONTH - 1 + step) // 12
        months.append(
            {
                "year": calendar_year,
                "month": month,
                "ag_year": year,
                "indicator": "soil_loss",
                "direction": "lower_is_better",
                "value": None,
                "unit": "t ha-1 month-1",
                "missing": {
                    "reason": "NOT_AVAILABLE",
                    "detail": "PLACEHOLDER: no monthly value in this test",
                },
            }
        )
    return months


def _not_built(indicator: str, direction: str, units: list[str]) -> dict[str, Any]:
    return {
        "indicator": indicator,
        "direction": direction,
        "units": units,
        "missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
    }


def result_of(rotation_id: str, *, soil_loss_built: bool = True) -> EnginesResult:
    document = copy.deepcopy(RESULT_TEMPLATE)
    years = range(FIRST_YEAR, LAST_YEAR + 1)
    document.update(
        case_id=REQUEST["site"]["case_id"],
        field_id=REQUEST["site"]["field_id"],
        rotation_id=rotation_id,
        water_deficit_exposure=_not_built(
            "water_deficit_exposure", "higher_is_better", ["dimensionless"]
        ),
        soil_carbon_trend=_not_built(
            "soil_carbon_trend", "higher_is_better", ["t C ha-1 yr-1"]
        ),
    )
    if soil_loss_built:
        document["soil_loss"] = {
            "annual": [_annual(rotation_id, year) for year in years],
            "monthly": [m for year in years for m in _monthly(year)],
        }
    else:
        document["soil_loss"] = {
            **_not_built(
                "soil_loss", "lower_is_better", ["t ha-1 yr-1", "t ha-1 month-1"]
            ),
            "missing": {"reason": "NOT_AVAILABLE", "detail": NOT_BUILT_DETAIL},
        }
    return EnginesResult(
        calendar=None,
        result=ResultsPerRotation.model_validate(document),
        result_missing=None,
        modules=MODULES,
        values_present=1,
        values_missing=1,
    )


NO_RESULT = EnginesResult(
    calendar=None,
    result=None,
    result_missing=Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER: input not available: climate"
    ),
    modules=(
        ModuleStatus(
            id="PLACEHOLDER_MODULE", state="not_available", reason="MISSING_INPUT"
        ),
    ),
)


class FakeEngines:
    """Answers by the ``rotation_id`` of the rotation; records every call."""

    def __init__(self, answers: dict[str, EnginesResult] | None = None) -> None:
        self.answers = answers or {rid: result_of(rid) for rid in LEVELS}
        self.calls: list[tuple[Any, Any, Any]] = []

    def run(self, rotation, climate, soil_slope) -> EnginesResult:
        self.calls.append((rotation, climate, soil_slope))
        return self.answers[rotation["rotation_id"]]


class Factory:
    """An engines factory that records the catalogue it was given."""

    def __init__(self, engines: FakeEngines | None = None) -> None:
        self.engines = engines or FakeEngines()
        self.catalogues: list[dict[str, dict]] = []

    def __call__(self, catalogue: dict[str, dict]) -> FakeEngines:
        self.catalogues.append(catalogue)
        return self.engines


class Raises:
    def run(self, rotation, climate, soil_slope):
        raise RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT")


CATALOGUE = load_parameters(PARAMETERS_FOLDER)


def client(**kwargs: Any) -> TestClient:
    kwargs.setdefault("settings", PERIOD)
    kwargs.setdefault("kinds_of_year_record", load_record())
    kwargs.setdefault("climate", FakeClimate())
    kwargs.setdefault("soil_slope", FakeSoilSlope())
    if "engines" not in kwargs:
        kwargs.setdefault("parameters", CATALOGUE)
        kwargs.setdefault("engines_factory", Factory())
    return TestClient(create_app([ORIGIN], **kwargs), raise_server_exceptions=False)


def body(**questions: Any) -> dict[str, Any]:
    document = copy.deepcopy(REQUEST)
    document["questions"].update(questions)
    return document


def answered(response) -> dict[str, Any]:
    """A 200 that is a PlantAnswer and answers the request it was asked."""
    assert response.status_code == 200, response.text
    data = response.json()
    answer = PlantAnswer.model_validate_json(json.dumps(data))
    assert answer.model_dump(mode="json") == data
    return data


def checked(request: dict[str, Any], data: dict[str, Any]) -> None:
    check_answer_against_request(
        PlantRequest.model_validate_json(json.dumps(request)),
        PlantAnswer.model_validate_json(json.dumps(data)),
    )


def without_sources(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "sources"}


# --- case 1: the example request ---------------------------------------------------


def test_the_example_request_gives_the_example_answer():
    climate, soil, factory = FakeClimate(), FakeSoilSlope(), Factory()
    response = client(climate=climate, soil_slope=soil, engines_factory=factory).post(
        ROUTE, json=REQUEST
    )
    data = answered(response)
    checked(REQUEST, data)
    # Every field but the sources equals the example answer, which the pure
    # functions computed from the same example inputs. Compared as the
    # contract writes it: the route writes every member of a declared Value
    # (null and false included, never exclude_none), the example file leaves
    # out the members it does not set.
    example = PlantAnswer.model_validate(ANSWER).model_dump(mode="json")
    assert without_sources(data) == without_sources(example)
    for key in ("answer", "chosen", "limit_cost", "tipping_price"):
        assert data[key] == example[key]
    for ours, theirs in zip(data["options"], example["options"], strict=True):
        assert ours["state"] == theirs["state"]
        assert ours["margin"] == theirs["margin"]
    # The sources: the two fakes, then the ONI record as in the example.
    assert [s["id"] for s in data["sources"]] == [
        "PLACEHOLDER_CLIMATE",
        "PLACEHOLDER_SOIL",
        "oni_v6",
    ]
    # The record is the PLACEHOLDER record of economics/test_plant.py.
    for key in ("id", "contract", "state"):
        assert data["sources"][2][key] == ANSWER["sources"][1][key]
    assert data["sources"][2]["attribution"] == load_record()["reference"]
    # One climate request, one soil request, each rotation run once on them.
    assert len(climate.requests) == 1
    assert soil.calls == [(REQUEST["site"]["case_id"], REQUEST["site"]["field_id"])]
    calls = factory.engines.calls
    assert [call[0]["rotation_id"] for call in calls] == [SOYBEAN, COVER, PASTURE]
    assert all(call[1] is calls[0][1] and call[2] is calls[0][2] for call in calls)


# --- case 2: invalid requests ------------------------------------------------------


def _nothing_called(climate, soil, engines) -> None:
    assert climate.requests == []
    assert soil.calls == []
    assert engines.calls == []


def _keep(count: int) -> dict[str, Any]:
    document = copy.deepcopy(REQUEST)
    rotations = document["rotations"]
    document["rotations"] = [
        {**copy.deepcopy(rotations[i % len(rotations)]), "rotation_id": f"r-{i}"}
        for i in range(count)
    ]
    return document


def _error(response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    data = response.json()
    assert set(data) == {"error"}
    assert set(data["error"]) == {"code", "message", "details"}
    assert data["error"]["code"] == code
    return data["error"]


@pytest.mark.parametrize("count", [2, 6])
def test_two_or_six_rotations_are_invalid_and_nothing_is_called(count):
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=_keep(count)
    )
    error = _error(response, 422, "INVALID_REQUEST")
    assert [d["path"] for d in error["details"]] == ["rotations"]
    _nothing_called(climate, soil, engines)


def test_an_invalid_rotation_is_rotation_invalid_and_nothing_is_called():
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    request = copy.deepcopy(REQUEST)
    del request["rotations"][1]["components"]
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=request
    )
    error = _error(response, 422, "ROTATION_INVALID")
    assert error["details"]
    assert all(d["path"].startswith("rotations.1") for d in error["details"])
    _nothing_called(climate, soil, engines)


def test_a_problem_of_the_injected_validator_is_reported_under_its_index():
    class OneProblem:
        def validate(self, rotation):
            if rotation["rotation_id"] != PASTURE:
                return []
            return [ErrorDetail(path="components.0", code="PLACEHOLDER", message="m")]

    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    response = client(
        climate=climate,
        soil_slope=soil,
        engines=engines,
        rotation_validator=OneProblem(),
    ).post(ROUTE, json=REQUEST)
    error = _error(response, 422, "ROTATION_INVALID")
    assert error["details"] == [
        {"path": "rotations.2.components.0", "code": "PLACEHOLDER", "message": "m"}
    ]
    _nothing_called(climate, soil, engines)


def test_an_error_does_not_repeat_a_submitted_value():
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    request = copy.deepcopy(REQUEST)
    request["rotations"][2]["field_id"] = "PLACEHOLDER_other_field"
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=request
    )
    error = _error(response, 422, "INVALID_REQUEST")
    assert error["details"][0]["message"] == REDACTED_MESSAGE
    assert PASTURE not in response.text
    assert "PLACEHOLDER_other_field" not in response.text
    _nothing_called(climate, soil, engines)


@pytest.mark.parametrize(
    "where",
    [
        [],
        ["site"],
        ["economic_facts", "crops", 0],
        ["rotations", 0, "components", 0],
    ],
)
def test_an_error_path_never_repeats_a_submitted_key(where):
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    request = copy.deepcopy(REQUEST)
    target = request
    for step in where:
        target = target[step]
    target["PLACEHOLDER_submitted_key"] = 1
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=request
    )
    assert response.status_code == 422, response.text
    assert "PLACEHOLDER_submitted_key" not in response.text
    paths = [d["path"] for d in response.json()["error"]["details"]]
    assert paths and all(path.endswith(EXTRA_KEY_SEGMENT) for path in paths)
    _nothing_called(climate, soil, engines)


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ([1, 2, 3], 422, "INVALID_REQUEST"),
        ({**REQUEST, "site": {**REQUEST["site"], "latitude": 1000.0}}, 422, None),
    ],
)
def test_a_body_that_is_not_a_plant_request_is_422(payload, status, code):
    response = client(engines=FakeEngines()).post(ROUTE, json=payload)
    error = _error(response, status, code or "SITE_INVALID")
    assert error["message"]


def test_malformed_json_is_400():
    response = client(engines=FakeEngines()).post(
        ROUTE, content=b"{", headers={"Content-Type": "application/json"}
    )
    _error(response, 400, "MALFORMED_JSON")


# --- case 3: no climate period ------------------------------------------------------


def _numbers(data: Any, keys=("value", "price", "distance_percent", "limit")):
    if isinstance(data, dict):
        for key, item in data.items():
            if key in keys and isinstance(item, int | float):
                yield item
            yield from _numbers(item, keys)
    elif isinstance(data, list):
        for item in data:
            yield from _numbers(item, keys)


def test_without_a_period_soil_loss_is_missing_and_nothing_is_resolved():
    climate, engines = FakeClimate(), FakeEngines(dict.fromkeys(LEVELS, NO_RESULT))
    response = client(climate=climate, engines=engines, settings=RunSettings()).post(
        ROUTE, json=REQUEST
    )
    data = answered(response)
    checked(REQUEST, data)
    assert climate.requests == []
    assert data["sources"][0]["state"] == "unavailable"
    for option in data["options"]:
        for mean in option["soil_loss"].values():
            assert mean["value"] is None
            assert mean["reason"] == "MISSING_INPUT"
            assert "input not available: climate" in mean["detail"]
        limit = option["limit"]
        checks = [limit["on_average"], limit["every_kind"], *limit["by_kind"].values()]
        assert {c["verdict"] for c in checks} == {"not_resolved"}
        assert option["state"] == "not_resolved"
        # Not classified: the average margin is missing, never a weighted guess.
        assert option["margin"]["average"]["value"] is None
        assert option["margin"]["average"]["reason"] == "NOT_AVAILABLE"
    assert data["answer"] == "not_resolved"
    assert data["chosen"] is None
    # The kinds of year are missing with their reason; no count is known.
    years = data["kinds_of_year"]["years"]
    assert years and all(y["kind"] is None for y in years)
    assert {y["missing_reason"] for y in years} == {"NOT_AVAILABLE"}
    assert all("not configured" in y["detail"] for y in years)
    assert set(data["kinds_of_year"]["counts"].values()) == {None}
    # No zero stands for a missing value anywhere.
    assert 0 not in list(_numbers(data))


# --- case 4: the soil-loss engine not built -----------------------------------------


def test_a_soil_loss_engine_not_built_gives_its_reason_to_every_option():
    engines = FakeEngines(
        {rid: result_of(rid, soil_loss_built=False) for rid in LEVELS}
    )
    data = answered(
        client(engines=engines).post(ROUTE, json=body(rain_stress_factor=None))
    )
    checked(body(rain_stress_factor=None), data)
    for option in data["options"]:
        for mean in option["soil_loss"].values():
            assert mean["value"] is None
            assert mean["reason"] == "NOT_AVAILABLE"
            assert NOT_BUILT_DETAIL in mean["detail"]
        assert option["limit_check"]["verdict"] == "not_resolved"
        assert NOT_BUILT_DETAIL in option["limit_check"]["detail"]
        assert option["state"] == "not_resolved"
    assert data["answer"] == "not_resolved"
    # The kinds of year still come from the record and the margins are there.
    assert data["kinds_of_year"] == ANSWER["kinds_of_year"]
    example = PlantAnswer.model_validate(ANSWER).model_dump(mode="json")
    assert [o["margin"] for o in data["options"]] == [
        o["margin"] for o in example["options"]
    ]


# --- case 5: rain stress -------------------------------------------------------------


def test_no_rain_stress_factor_gives_no_echo_and_one_plain_run():
    engines = FakeEngines()
    request = body(rain_stress_factor=None)
    data = answered(client(engines=engines).post(ROUTE, json=request))
    checked(request, data)
    assert data["rain_stress"] is None
    assert len(engines.calls) == 3


def test_a_factor_with_a_factory_reaches_the_engines_on_the_scaled_catalogue():
    factory = Factory()
    data = answered(client(engines_factory=factory).post(ROUTE, json=REQUEST))
    (catalogue,) = factory.catalogues
    stress = rain_stress(
        Value.model_validate(REQUEST["questions"]["rain_stress_factor"])
    )
    assert catalogue == scale_erosivity(CATALOGUE, stress)
    scaled = [k for k, r in catalogue.items() if r.get("id") == R_ID]
    assert scaled and all(catalogue[k] != CATALOGUE[k] for k in scaled)
    assert len(factory.engines.calls) == 3
    assert data["rain_stress"]["applied"] is True
    example = PlantAnswer.model_validate(ANSWER).model_dump(mode="json")
    assert data["rain_stress"] == example["rain_stress"]


def test_a_factor_with_injected_engines_and_no_factory_is_not_applied():
    engines = FakeEngines()
    data = answered(client(engines=engines).post(ROUTE, json=REQUEST))
    checked(REQUEST, data)
    echo = data["rain_stress"]
    assert echo["applied"] is False
    assert NO_FACTORY in echo["detail"]
    assert Value.model_validate(echo["declared"]) == Value.model_validate(
        REQUEST["questions"]["rain_stress_factor"]
    )
    assert len(engines.calls) == 3


def test_a_missing_factor_is_echoed_missing():
    factor = {
        "value": None,
        "unit": "dimensionless",
        "missing": {"reason": "NOT_DECLARED"},
    }
    factory = Factory()
    request = body(rain_stress_factor=factor)
    data = answered(client(engines_factory=factory).post(ROUTE, json=request))
    checked(request, data)
    assert data["rain_stress"]["missing"] == {"reason": "NOT_DECLARED", "detail": None}
    assert factory.catalogues == []


# --- case 6: the questions change what is ranked ---------------------------------------


def test_strictness_every_kind_changes_the_answer():
    request = body(strictness="every_kind")
    data = answered(client().post(ROUTE, json=request))
    checked(request, data)
    assert (data["answer"], data["chosen"]) != (ANSWER["answer"], ANSWER["chosen"])
    assert data["answer"] == "not_resolved"
    assert [o["limit_check"] for o in data["options"]] == [
        o["limit"]["every_kind"] for o in ANSWER["options"]
    ]


def test_margin_of_a_kind_of_year_changes_the_answer():
    request = body(margin_of="la_nina")
    data = answered(client().post(ROUTE, json=request))
    checked(request, data)
    assert (data["answer"], data["chosen"]) != (ANSWER["answer"], ANSWER["chosen"])
    assert data["answer"] == "not_resolved"


def _pasture_sown_on(day: str) -> dict[str, Any]:
    request = copy.deepcopy(REQUEST)
    (pasture,) = [r for r in request["rotations"] if r["rotation_id"] == PASTURE]
    pasture["components"][-1]["sowing"]["date"] = day
    return request


def _a_year_later(day: str) -> str:
    date = dt.date.fromisoformat(day)
    return date.replace(year=date.year + 1).isoformat()


PASTURE_COMPONENTS = next(
    r["components"] for r in REQUEST["rotations"] if r["rotation_id"] == PASTURE
)


@pytest.mark.parametrize(
    "day",
    [
        # A year of the cycle with no crop sown: the pasture a year later.
        _a_year_later(PASTURE_COMPONENTS[-1]["sowing"]["date"]),
        # The declared-margin pasture sharing its year with the crop before it.
        PASTURE_COMPONENTS[-2]["sowing"]["date"],
    ],
)
def test_a_rotation_without_years_gives_its_own_reason_to_the_tipping_price(day):
    request = _pasture_sown_on(day)
    data = answered(client().post(ROUTE, json=request))
    checked(request, data)
    (option,) = [o for o in data["options"] if o["rotation_id"] == PASTURE]
    assert {m["reason"] for m in option["margin"].values()} == {"NOT_COMPUTABLE"}
    tipping = data["tipping_price"]
    assert tipping["reason"] == "NOT_COMPUTABLE"
    assert f"{PASTURE} (NOT_COMPUTABLE: " in tipping["detail"]
    for side in ("up", "down"):
        assert tipping[side]["price"] is None
        assert tipping[side]["reason"] == "NOT_COMPUTABLE"


# --- code review fixes (PROPOSED) --------------------------------------------------------


def test_a_rotation_with_every_date_missing_is_422_before_any_call():
    """Finding 1: D21 refuses it, so the years of classify_years are never empty."""
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    request = copy.deepcopy(REQUEST)
    for component in request["rotations"][0]["components"]:
        for key in ("sowing", "harvest"):
            component[key] = {"date": None, "missing": {"reason": "NOT_DECLARED"}}
    response = client(
        climate=climate, soil_slope=soil, engines=engines, settings=RunSettings()
    ).post(ROUTE, json=request)
    error = _error(response, 422, "ROTATION_INVALID")
    assert all(d["path"].startswith("rotations.0") for d in error["details"])
    _nothing_called(climate, soil, engines)


def test_problems_in_two_rotation_items_are_invalid_request():
    """Finding 7: ROTATION_INVALID only when every problem is in one item."""
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    request = copy.deepcopy(REQUEST)
    del request["rotations"][0]["components"]
    del request["rotations"][1]["components"]
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=request
    )
    error = _error(response, 422, "INVALID_REQUEST")
    heads = {".".join(d["path"].split(".")[:2]) for d in error["details"]}
    assert heads == {"rotations.0", "rotations.1"}
    _nothing_called(climate, soil, engines)


def test_injected_validator_problems_in_two_items_are_invalid_request():
    class TwoProblems:
        def validate(self, rotation):
            if rotation["rotation_id"] == SOYBEAN:
                return []
            return [ErrorDetail(path="components.0", code="PLACEHOLDER", message="m")]

    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    response = client(
        climate=climate,
        soil_slope=soil,
        engines=engines,
        rotation_validator=TwoProblems(),
    ).post(ROUTE, json=REQUEST)
    error = _error(response, 422, "INVALID_REQUEST")
    assert [d["path"] for d in error["details"]] == [
        "rotations.1.components.0",
        "rotations.2.components.0",
    ]
    _nothing_called(climate, soil, engines)


def _all_soil_means(data: dict[str, Any]):
    return [mean for o in data["options"] for mean in o["soil_loss"].values()]


def test_a_period_without_a_whole_year_reads_no_soil_loss_year():
    """Findings 2 and 4: the engines ran, but no year of the result is a whole
    agricultural year of the record, so every mean is NO_COVERAGE, never 0."""
    short = RunSettings(
        start_date=PERIOD.start_date,
        end_date=PERIOD.start_date + dt.timedelta(days=30),
    )
    data = answered(client(settings=short).post(ROUTE, json=REQUEST))
    checked(REQUEST, data)
    for mean in _all_soil_means(data):
        assert mean["value"] is None
        assert mean["reason"] == "NO_COVERAGE"
        assert "are ignored" in mean["detail"]
    assert 0 not in list(_numbers(data))


def test_years_of_the_result_outside_the_record_period_are_ignored_with_a_note():
    """Finding 4: a year of the result that is not classified is not averaged."""
    later = RunSettings(
        start_date=dt.date(FIRST_YEAR + 1, START_MONTH, 1), end_date=PERIOD.end_date
    )
    data = answered(client(settings=later).post(ROUTE, json=REQUEST))
    checked(REQUEST, data)
    note = f"agricultural year(s) {FIRST_YEAR} of the soil-loss result"
    for mean in _all_soil_means(data):
        assert FIRST_YEAR not in mean["ag_years"]
        assert note in mean["detail"]
    assert FIRST_YEAR not in {y["ag_year"] for y in data["kinds_of_year"]["years"]}


def test_an_empty_annual_list_gives_soil_loss_missing_not_a_500():
    """Finding 2: the contract refuses an empty list (min_length=1); built
    around it, the means are still missing with a reason."""
    from api.plant import Classified, soil_loss_means
    from contracts.results.models import SoilLossResults

    run = result_of(SOYBEAN)
    hollow = run.result.model_copy(
        update={"soil_loss": SoilLossResults.model_construct(annual=[], monthly=[])}
    )
    record, by_kind = soil_loss_means(
        dataclasses.replace(run, result=hollow), Classified({}, True)
    )
    for mean in (record, *by_kind.values()):
        assert mean.value is None
        assert mean.reason == "NO_COVERAGE"
        assert mean.detail


def test_a_pasture_kept_several_years_counts_in_each_year_until_its_harvest():
    """Finding 3: a declared-margin crop from its sowing through its harvest."""
    from api.plant import cycle_years
    from contracts.rotation_definition import RotationDefinition
    from economics.margin import compute_rotation_margin

    request = copy.deepcopy(REQUEST)
    (pasture,) = [r for r in request["rotations"] if r["rotation_id"] == PASTURE]
    last = pasture["components"][-1]
    sown = dt.date.fromisoformat(last["sowing"]["date"])
    last["harvest"] = {
        "date": sown.replace(year=sown.year + 2).isoformat(),
        "provenance": "DECLARED",
        "source": "user",
    }
    plant_request = PlantRequest.model_validate_json(json.dumps(request))
    crops = {c.crop_id: c for c in plant_request.economic_facts.crops}
    cycle = cycle_years(RotationDefinition.model_validate(pasture), crops)
    assert cycle.years is not None
    pasture_id = last["crop_id"]
    assert cycle.years[-3:] == [[pasture_id]] * 3
    data = answered(client().post(ROUTE, json=request))
    checked(request, data)
    (option,) = [o for o in data["options"] if o["rotation_id"] == PASTURE]
    expected = compute_rotation_margin(
        cycle.years,
        plant_request.economic_facts,
        {k: v for k, v in data["kinds_of_year"]["counts"].items()},
    )
    # The D249 labels (provenance, range, source) are added by the answer.
    labels = {"provenance", "range", "range_missing", "source"}
    average = {k: v for k, v in option["margin"]["average"].items() if k not in labels}
    assert average == json.loads(json.dumps(dataclasses.asdict(expected.average)))


def test_a_grain_crop_harvested_in_a_later_year_counts_only_once():
    from api.plant import cycle_years
    from contracts.rotation_definition import RotationDefinition

    request = copy.deepcopy(REQUEST)
    soybean = request["rotations"][0]
    first = soybean["components"][0]
    sown = dt.date.fromisoformat(first["sowing"]["date"])
    first["harvest"]["date"] = sown.replace(year=sown.year + 2).isoformat()
    plant_request = PlantRequest.model_validate_json(json.dumps(request))
    crops = {c.crop_id: c for c in plant_request.economic_facts.crops}
    cycle = cycle_years(RotationDefinition.model_validate(soybean), crops)
    assert cycle.years == [[first["crop_id"]]]


def test_a_factory_with_injected_engines_is_not_called_and_not_applied():
    """Finding 5: the catalogue of injected engines is not known."""
    from api.plant import NO_CATALOGUE

    engines, factory = FakeEngines(), Factory()
    data = answered(
        client(engines=engines, engines_factory=factory).post(ROUTE, json=REQUEST)
    )
    checked(REQUEST, data)
    assert factory.catalogues == []
    assert data["rain_stress"]["applied"] is False
    assert NO_CATALOGUE in data["rain_stress"]["detail"]
    assert len(engines.calls) == 3


# --- defects: 500 -----------------------------------------------------------------------


def _internal(response) -> None:
    error = _error(response, 500, "INTERNAL_ERROR")
    assert error["details"] == []
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_an_engine_that_raises_answers_500():
    response = client(engines=Raises()).post(
        ROUTE, json=REQUEST, headers={"Origin": ORIGIN}
    )
    _internal(response)


def test_engines_that_answer_for_another_rotation_answer_500():
    engines = FakeEngines({rid: result_of(SOYBEAN) for rid in LEVELS})
    response = client(engines=engines).post(
        ROUTE, json=REQUEST, headers={"Origin": ORIGIN}
    )
    _internal(response)


# --- the default app ---------------------------------------------------------------------


def test_the_default_app_answers_the_example_request():
    """The engines of the repository, the stand-in sources and no period: a
    200 with every soil-loss mean missing and the stress applied through the
    default factory on the catalogue."""
    app = create_app([], parameters=CATALOGUE)
    data = answered(TestClient(app).post(ROUTE, json=REQUEST))
    checked(REQUEST, data)
    assert data["rain_stress"]["applied"] is True
    assert all(
        mean["value"] is None
        for option in data["options"]
        for mean in option["soil_loss"].values()
    )
    assert 0 not in list(_numbers(data))


# --- the other routes ------------------------------------------------------------------


def test_the_rotation_route_is_unchanged_next_to_the_new_one():
    response = client(engines=FakeEngines()).post(
        "/api/rotations/run",
        json={"site": REQUEST["site"], "rotation": REQUEST["rotations"][0]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["rotation_id"] == SOYBEAN


# --- review of the whole 3 (brief S-029), PROPOSED test cases ---------------------------


def _day(ag_year: int, month: int, day: int) -> dt.date:
    """The day of agricultural year ``ag_year`` (START_MONTH) with this month
    and day: built from explicit numbers, never by ``date.replace(year=...)``."""
    assert (month, day) != (2, 29), "a day that every year has"
    return dt.date(ag_year if month >= START_MONTH else ag_year + 1, month, day)


def _declared(day: dt.date) -> dict[str, Any]:
    return {"date": day.isoformat(), "provenance": "DECLARED", "source": "user"}


def _date_of(item: dict[str, Any]) -> dt.date:
    return dt.date.fromisoformat(item["date"])


def _pasture_rotation(request: dict[str, Any]) -> dict[str, Any]:
    (pasture,) = [r for r in request["rotations"] if r["rotation_id"] == PASTURE]
    return pasture


def _ag(day: dt.date) -> int:
    from api.phases import ag_year_of

    return ag_year_of(day, START_MONTH)


def _example_years() -> tuple[int, list[str], str]:
    """The example pasture rotation read as agricultural years: the year the
    pasture is sown, the crop_ids of the year before it (every other
    component) and the pasture's crop_id."""
    *first_ones, pasture = _pasture_rotation(REQUEST)["components"]
    (first_year,) = {_ag(_date_of(c["sowing"])) for c in first_ones}
    pasture_year = _ag(_date_of(pasture["sowing"]))
    assert pasture_year == first_year + 1
    return pasture_year, [c["crop_id"] for c in first_ones], pasture["crop_id"]


def _pasture_then_soybean(harvest_after_sowing_days: int | None = None):
    """The pasture rotation with the pasture kept until a harvest two
    agricultural years after its sowing and a soybean sown later in that same
    year (example data of this test, derived from the example request).

    With ``harvest_after_sowing_days``, the pasture is harvested that many
    days after the follower is sown instead (an overlap when above zero).
    Returns the request and the pasture's harvest year.
    """
    request = copy.deepcopy(REQUEST)
    pasture = _pasture_rotation(request)
    soybean, last = pasture["components"][0], pasture["components"][-1]
    pasture_year, _, _ = _example_years()
    soy_sown, soy_harvest = _date_of(soybean["sowing"]), _date_of(soybean["harvest"])
    end_year = pasture_year + 2
    follower_sown = _day(end_year, soy_sown.month, soy_sown.day)
    if harvest_after_sowing_days is None:
        # The first day of the agricultural year: before the follower's sowing.
        end = _day(end_year, START_MONTH, 1)
        assert end < follower_sown
    else:
        end = follower_sown + dt.timedelta(days=harvest_after_sowing_days)
    assert _ag(end) == end_year
    last["harvest"] = _declared(end)
    follower = copy.deepcopy(soybean)
    follower["component_id"] = soybean["component_id"] + "-after-pasture"
    follower["position"] = last["position"] + 1
    follower["sowing"] = _declared(follower_sown)
    harvest_year = end_year + _ag(soy_harvest) - _ag(soy_sown)
    follower["harvest"] = _declared(
        _day(harvest_year, soy_harvest.month, soy_harvest.day)
    )
    pasture["components"].append(follower)
    return request, end_year


def _cycle_of(request: dict[str, Any]):
    from api.plant import cycle_years
    from contracts.rotation_definition import RotationDefinition

    plant_request = PlantRequest.model_validate_json(json.dumps(request))
    crops = {c.crop_id: c for c in plant_request.economic_facts.crops}
    definition = RotationDefinition.model_validate(_pasture_rotation(request))
    return plant_request, cycle_years(definition, crops)


def _pasture_option(request: dict[str, Any]) -> tuple[dict, dict]:
    data = answered(client().post(ROUTE, json=request))
    checked(request, data)
    (option,) = [o for o in data["options"] if o["rotation_id"] == PASTURE]
    return data, option


def _margin_reasons(option: dict[str, Any]) -> set[str | None]:
    return {m["reason"] for m in option["margin"].values()}


def _assert_margin_as_computed(request: dict[str, Any]) -> None:
    from economics.margin import compute_rotation_margin

    plant_request, cycle = _cycle_of(request)
    data, option = _pasture_option(request)
    assert "NOT_COMPUTABLE" not in _margin_reasons(option)
    expected = compute_rotation_margin(
        cycle.years, plant_request.economic_facts, data["kinds_of_year"]["counts"]
    )
    labels = {"provenance", "range", "range_missing", "source"}  # D249
    average = {k: v for k, v in option["margin"]["average"].items() if k not in labels}
    assert average == json.loads(json.dumps(dataclasses.asdict(expected.average)))


def test_f1_a_crop_sown_in_the_year_a_pasture_ends_gets_computed_margins():
    """F1: a declared-margin crop counts up to the year before the next crop's
    sowing year; its harvest year only when no crop follows it in that year."""
    request, end_year = _pasture_then_soybean()
    pasture_year, first_crops, pasture_id = _example_years()
    _, cycle = _cycle_of(request)
    soybean_id = _pasture_rotation(request)["components"][-1]["crop_id"]
    kept = end_year - pasture_year  # from its sowing year to its harvest year - 1
    assert cycle.years == [first_crops, *[[pasture_id]] * kept, [soybean_id]]
    _assert_margin_as_computed(request)


def test_f1_a_crop_sown_while_the_pasture_is_kept_still_shares_its_year():
    """F1: only a crop sown in the pasture's harvest year ends it early; one
    sown in an earlier year of the pasture still shares that year."""
    request, _ = _pasture_then_soybean()
    follower = _pasture_rotation(request)["components"][-1]
    for key in ("sowing", "harvest"):
        day = _date_of(follower[key])
        follower[key] = _declared(_day(_ag(day) - 1, day.month, day.day))
    _, option = _pasture_option(request)
    assert _margin_reasons(option) == {"NOT_COMPUTABLE"}


def test_r2_a_crop_sown_before_the_pasture_harvest_date_shares_the_year():
    """R2: the harvest year goes to the follower only when it is sown on or
    after the harvest date; sown one day before it, the two overlap and keep
    sharing the year (NOT_COMPUTABLE): the trimming never hides an overlap."""
    request, end_year = _pasture_then_soybean(harvest_after_sowing_days=1)
    pasture_year, first_crops, pasture_id = _example_years()
    _, cycle = _cycle_of(request)
    soybean_id = _pasture_rotation(request)["components"][-1]["crop_id"]
    kept = end_year - pasture_year
    assert cycle.years == [
        first_crops,
        *[[pasture_id]] * kept,
        [pasture_id, soybean_id],
    ]
    _, option = _pasture_option(request)
    assert _margin_reasons(option) == {"NOT_COMPUTABLE"}


def test_r2_a_crop_sown_on_the_pasture_harvest_date_takes_the_year():
    """R2: sown on the harvest date itself ("on or after"), the follower
    takes the harvest year."""
    request, end_year = _pasture_then_soybean(harvest_after_sowing_days=0)
    pasture_year, first_crops, pasture_id = _example_years()
    _, cycle = _cycle_of(request)
    soybean_id = _pasture_rotation(request)["components"][-1]["crop_id"]
    kept = end_year - pasture_year
    assert cycle.years == [first_crops, *[[pasture_id]] * kept, [soybean_id]]
    _assert_margin_as_computed(request)


def _pasture_last_until(end: dt.date, repeats: bool = True) -> dict[str, Any]:
    """The example pasture rotation with its pasture, the last component,
    harvested on ``end`` (example data of this test)."""
    request = copy.deepcopy(REQUEST)
    pasture = _pasture_rotation(request)
    pasture["components"][-1]["harvest"] = _declared(end)
    pasture["repeats"] = repeats
    return request


def _next_cycle_sowing() -> tuple[int, dt.date]:
    """The year after the pasture's sowing year and the day of that year on
    which the first component is sown (by its month and day)."""
    pasture_year, _, _ = _example_years()
    sown = _date_of(_pasture_rotation(REQUEST)["components"][0]["sowing"])
    return pasture_year + 1, _day(pasture_year + 1, sown.month, sown.day)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN (S-029 remark R1): fixing it changes the expected cycle of "
        "test_a_pasture_kept_several_years_counts_in_each_year_until_its_harvest, "
        "which a person decides"
    ),
)
def test_r1_the_last_pasture_gives_its_harvest_year_to_the_next_cycle():
    """R1: a declared-margin crop that is the last component, harvested in
    the year the first component of the next cycle is sown and before that
    sowing date, does not count that year: the cycle is not one year longer
    than the one the calendar repeats (point 3 of engine/calendar/repeat.py)."""
    next_year, next_sown = _next_cycle_sowing()
    _, first_crops, pasture_id = _example_years()
    end = _day(next_year, START_MONTH, 1)
    assert end < next_sown
    request = _pasture_last_until(end)
    _, cycle = _cycle_of(request)
    assert cycle.years == [first_crops, [pasture_id]]
    _assert_margin_as_computed(request)


def test_r1_a_pasture_harvested_after_the_next_sowing_day_keeps_its_year():
    """R1: harvested after the next cycle's first sowing day of that year, the
    calendar's cycle is one year longer too, so the pasture keeps its harvest
    year and the next cycle starts a year later (true now and under the rule
    R1 asks for)."""
    _, next_sown = _next_cycle_sowing()
    _, first_crops, pasture_id = _example_years()
    request = _pasture_last_until(next_sown + dt.timedelta(days=1))
    _, cycle = _cycle_of(request)
    assert cycle.years == [first_crops, [pasture_id], [pasture_id]]


def test_r1_a_rotation_that_does_not_repeat_keeps_the_harvest_year():
    """R1: with ``repeats`` false no cycle follows, so the last pasture counts
    through its harvest year (true now and under the rule R1 asks for)."""
    next_year, _ = _next_cycle_sowing()
    _, first_crops, pasture_id = _example_years()
    request = _pasture_last_until(_day(next_year, START_MONTH, 1), repeats=False)
    _, cycle = _cycle_of(request)
    assert cycle.years == [first_crops, [pasture_id], [pasture_id]]


# PROPOSED example factor of this test: large enough that the erosivity of
# the repository catalogue times it is not a finite number.
HUGE_FACTOR = 1e308


def test_f2_a_factor_whose_scaled_erosivity_is_not_finite_is_not_applied():
    """F2: a typed absence (the echo applied false, with why), never a 500."""
    from api.plant import NOT_FINITE

    factor = dict(REQUEST["questions"]["rain_stress_factor"], value=HUGE_FACTOR)
    factory = Factory()
    request = body(rain_stress_factor=factor)
    data = answered(client(engines_factory=factory).post(ROUTE, json=request))
    checked(request, data)
    assert factory.catalogues == []
    echo = data["rain_stress"]
    assert echo["applied"] is False
    assert NOT_FINITE in echo["detail"]


def _counting_factory():
    calls: list[dict[str, dict]] = []

    def factory(catalogue: dict[str, dict]) -> FakeEngines:
        calls.append(catalogue)
        return FakeEngines()

    return factory, calls


WITHOUT_R = {k: r for k, r in CATALOGUE.items() if r.get("id") != R_ID}


def test_f3_a_catalogue_without_the_r_record_never_calls_the_factory():
    """F3: when EP1 would not read the level, the factory is not called."""
    from api.plant import stressed_run

    factory, calls = _counting_factory()
    engines = FakeEngines()
    request = PlantRequest.model_validate_json(json.dumps(REQUEST))
    run = stressed_run(request, engines, factory, WITHOUT_R)
    assert calls == []
    assert run.engines is engines
    assert run.echo.applied is False
    assert R_ID in run.echo.detail


def test_f3_through_the_route_the_factory_is_not_called():
    factory, calls = _counting_factory()
    response = client(
        parameters=WITHOUT_R, engines_factory=factory, settings=RunSettings()
    ).post(ROUTE, json=REQUEST)
    data = answered(response)
    checked(REQUEST, data)
    assert calls == []
    assert data["rain_stress"]["applied"] is False


def test_r3_another_value_error_of_scale_erosivity_is_not_called_not_finite(
    monkeypatch,
):
    """R3: only a scaled erosivity that is not finite is the NOT_FINITE
    absence; any other ValueError of scale_erosivity surfaces as before (the
    route's 500, a defect), never relabelled."""
    import api.plant

    def raises(parameters, stress):
        raise ValueError("another defect")

    monkeypatch.setattr(api.plant, "scale_erosivity", raises)
    factory = Factory()
    response = client(engines_factory=factory).post(ROUTE, json=REQUEST)
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert factory.catalogues == []


def test_r3_scales_to_finite_reads_the_products():
    from api.rain_stress import scales_to_finite

    stress = rain_stress(
        Value.model_validate(REQUEST["questions"]["rain_stress_factor"])
    )
    huge = rain_stress(
        Value.model_validate(
            dict(REQUEST["questions"]["rain_stress_factor"], value=HUGE_FACTOR)
        )
    )
    assert scales_to_finite(CATALOGUE, stress) is True
    assert scales_to_finite(CATALOGUE, huge) is False


def _with_soybean_price(price: dict[str, Any]) -> PlantRequest:
    request = copy.deepcopy(REQUEST)
    soy = REQUEST["questions"]["soybean_crop_ids"][0]
    (crop,) = [c for c in request["economic_facts"]["crops"] if c["crop_id"] == soy]
    if price:
        crop["price"] = price
    return PlantRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize(
    "price",
    [
        {},
        {"value": None, "unit": "USD t-1", "missing": {"reason": "NOT_DECLARED"}},
    ],
)
def test_f6_todays_price_reads_as_economics_tipping_does(price):
    """F6: the route's copy of the rule and the private rule of
    economics.tipping read the same price on the contract example (keep them
    in step)."""
    from api.plant import _todays_price
    from contracts.economic_facts import GrainCrop
    from economics.tipping import _todays_price as tipping_today

    request = _with_soybean_price(price)
    soybeans = {
        c.crop_id: c
        for c in request.economic_facts.crops
        if c.crop_id in request.questions.soybean_crop_ids and isinstance(c, GrainCrop)
    }
    assert _todays_price(request) == tipping_today(soybeans)[0]


def _two_soybeans_at(prices: tuple[float, float]) -> dict[str, Any]:
    """The example request with a second soybean crop (example data of this
    test): the first at ``prices[0]``, the copy at ``prices[1]``."""
    request = copy.deepcopy(REQUEST)
    soy = REQUEST["questions"]["soybean_crop_ids"][0]
    (crop,) = [c for c in request["economic_facts"]["crops"] if c["crop_id"] == soy]
    other = copy.deepcopy(crop)
    other["crop_id"] = soy + "_second"
    crop["price"]["value"], other["price"]["value"] = prices
    request["economic_facts"]["crops"].append(other)
    request["questions"]["soybean_crop_ids"] = [soy, other["crop_id"]]
    # Every named soybean crop is sown by a rotation (PlantRequest).
    (first,) = [r for r in request["rotations"] if r["rotation_id"] == SOYBEAN]
    first["components"][0]["crop_id"] = other["crop_id"]
    return request


def _named_soybeans(facts: Any, ids: Any) -> dict[str, Any]:
    from contracts.economic_facts import GrainCrop

    return {
        c.crop_id: c
        for c in facts.crops
        if c.crop_id in ids and isinstance(c, GrainCrop)
    }


def test_r7_soybean_crops_with_different_prices_are_refused_as_economics_does():
    """R7: economics.tipping refuses named soybean crops with different
    prices (ValueError); PlantRequest refuses them too, so the route answers
    422 with the one error shape and never reaches its reading of today's
    price (no 500)."""
    from contracts.economic_facts import EconomicFacts
    from economics.tipping import _todays_price as tipping_today

    price = _example_soybean_price()
    request = _two_soybeans_at((price, price + price))
    facts = EconomicFacts.model_validate(request["economic_facts"])
    soybeans = _named_soybeans(facts, request["questions"]["soybean_crop_ids"])
    with pytest.raises(ValueError, match="different prices"):
        tipping_today(soybeans)
    with pytest.raises(ValueError, match="different prices"):
        PlantRequest.model_validate_json(json.dumps(request))
    response = client().post(ROUTE, json=request)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "INVALID_REQUEST"


def test_r7_two_soybean_crops_at_one_price_read_as_economics_does():
    """R7: named soybean crops at one and the same price: the route's
    today's price is the one economics.tipping reads."""
    from api.plant import _todays_price
    from economics.tipping import _todays_price as tipping_today

    price = _example_soybean_price()
    request = PlantRequest.model_validate_json(
        json.dumps(_two_soybeans_at((price, price)))
    )
    soybeans = _named_soybeans(
        request.economic_facts, request.questions.soybean_crop_ids
    )
    assert _todays_price(request) == tipping_today(soybeans)[0] == price


def _example_soybean_price() -> float:
    """The declared soybean price of the example request."""
    soy = REQUEST["questions"]["soybean_crop_ids"][0]
    (crop,) = [c for c in REQUEST["economic_facts"]["crops"] if c["crop_id"] == soy]
    return crop["price"]["value"]


# --- review of the whole 4 (brief S-034), PROPOSED test cases ---------------------------

# Test data: identifiers shorter than the three characters the redaction of
# api/rotation_validator.py looks for, so only the message itself can keep
# them out of an error.
SHORT_ID = "q7"


def _short_rotation_ids(request: dict[str, Any]) -> None:
    request["rotations"][0]["rotation_id"] = SHORT_ID
    request["rotations"][1]["rotation_id"] = SHORT_ID


def _short_rotation_of_another_field(request: dict[str, Any]) -> None:
    request["rotations"][2]["rotation_id"] = SHORT_ID
    request["rotations"][2]["field_id"] = "example-field-2"


def _short_undeclared_crop(request: dict[str, Any]) -> None:
    request["rotations"][2]["components"][0]["crop_id"] = SHORT_ID


def _short_repeated_soybean(request: dict[str, Any]) -> None:
    request["questions"]["soybean_crop_ids"] = [SHORT_ID, SHORT_ID]


def _short_soybean_not_sown(request: dict[str, Any]) -> None:
    soy = request["questions"]["soybean_crop_ids"][0]
    (crop,) = [c for c in request["economic_facts"]["crops"] if c["crop_id"] == soy]
    request["economic_facts"]["crops"].append(dict(crop, crop_id=SHORT_ID))
    request["questions"]["soybean_crop_ids"] = [SHORT_ID]


@pytest.mark.parametrize(
    "mutate",
    [
        _short_rotation_ids,
        pytest.param(
            _short_rotation_of_another_field,
            # OPEN (S-034): this message still quotes the rotation_id; see the
            # comment at the message in contracts/plant_answer/plant_answer.py.
            marks=pytest.mark.xfail(strict=True, reason="OPEN: S-034 F2"),
        ),
        _short_undeclared_crop,
        _short_repeated_soybean,
        _short_soybean_not_sown,
    ],
)
def test_f2_an_error_never_repeats_a_short_submitted_id(mutate):
    """F2: the messages of PlantRequest name positions, never a submitted id,
    so redaction by length is not the only guard."""
    request = copy.deepcopy(REQUEST)
    mutate(request)
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=request
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["details"]
    for detail in error["details"]:
        assert SHORT_ID not in detail["message"].casefold()
    _nothing_called(climate, soil, engines)


def test_f3_without_a_period_the_soil_loss_is_missing_with_the_period_reason():
    """F3: no period, engines that answer with a soil loss: every mean is
    missing with the reason of the absent period, not NO_COVERAGE."""
    from api.plant import PERIOD_REASON

    data = answered(client(settings=RunSettings()).post(ROUTE, json=REQUEST))
    checked(REQUEST, data)
    for mean in _all_soil_means(data):
        assert mean["value"] is None
        assert mean["reason"] == PERIOD_REASON
        assert "not configured" in mean["detail"]
    assert 0 not in list(_numbers(data))


def test_f3_the_period_reason_is_the_one_of_the_climate_source_row():
    """F3: the route's reason of an absent period is the one get_climate
    writes on the climate source row (api/rotations.py)."""
    from api.plant import PERIOD_REASON
    from api.rotations import SiteReference, get_climate

    site = SiteReference.model_validate(REQUEST["site"])
    result = get_climate(FakeClimate(), site, RunSettings())
    assert result.source.missing_reason == PERIOD_REASON


# --- review of #310: no record, plant layer by name, nothing at start-up ----------


def test_without_a_record_every_kind_of_year_is_missing_with_its_reason():
    """No ONI record configured: the route answers, and no kind is made up."""
    response = client(kinds_of_year_record=None).post(ROUTE, json=REQUEST)
    assert response.status_code == 200
    data = response.json()
    years = data["kinds_of_year"]["years"]
    assert years
    assert all(y["kind"] is None for y in years)
    assert {y["missing_reason"] for y in years} == {"NOT_AVAILABLE"}
    assert all("KINDS_OF_YEAR_RECORD_FILE" in y["detail"] for y in years)
    assert set(data["kinds_of_year"]["counts"].values()) == {None}
    record_row = data["sources"][-1]
    assert record_row["state"] == "unavailable"
    assert record_row["missing_reason"] == "NOT_AVAILABLE"
    PlantAnswer.model_validate(data)


def test_the_plant_layer_is_looked_up_by_name_on_each_request(monkeypatch):
    """Not there: 200 with the answer null and NOT_AVAILABLE; other routes unaffected."""
    import api.app as app_module

    monkeypatch.setattr(app_module, "PLANT_MODULE", "api.plant_layer_not_built")
    test_client = client()
    response = test_client.post(ROUTE, json=REQUEST)
    assert response.status_code == 200
    assert response.json() == {
        "answer": None,
        "answer_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": app_module.PLANT_NOT_BUILT,
        },
    }
    assert test_client.get("/health").status_code == 200


def test_an_injected_plant_layer_answers_the_route():
    calls = []

    def layer(body, **kwargs):
        calls.append((body, kwargs))
        return {"answer": "PLACEHOLDER"}

    response = client(plant_layer=layer).post(ROUTE, json=REQUEST)
    assert response.json() == {"answer": "PLACEHOLDER"}
    assert calls[0][0] == REQUEST
    assert calls[0][1]["kinds_of_year_record"] == load_record()


def test_building_the_app_imports_no_plant_layer_and_reads_no_record():
    import subprocess
    import sys

    code = (
        "import sys; from api.main import create_app; create_app([]); "
        "assert 'api.plant' not in sys.modules, 'api.plant'; "
        "assert 'economics.plant' not in sys.modules, 'economics.plant'; "
        "assert 'kinds_of_year' not in sys.modules, 'kinds_of_year'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_the_record_is_read_only_from_the_variable_that_names_it(tmp_path):
    from api.config import KINDS_OF_YEAR_RECORD_FILE, ConfigError, load_config

    assert load_config({}).kinds_of_year_record is None
    path = tmp_path / "PLACEHOLDER_record.json"
    path.write_text(json.dumps(load_record()), encoding="utf-8")
    config = load_config({KINDS_OF_YEAR_RECORD_FILE: str(path)})
    assert config.kinds_of_year_record == load_record()
    wrong = tmp_path / "PLACEHOLDER_not_a_record.json"
    wrong.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match=KINDS_OF_YEAR_RECORD_FILE):
        load_config({KINDS_OF_YEAR_RECORD_FILE: str(wrong)})
    with pytest.raises(ConfigError, match=KINDS_OF_YEAR_RECORD_FILE):
        load_config({KINDS_OF_YEAR_RECORD_FILE: str(tmp_path / "absent.json")})
