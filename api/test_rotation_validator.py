"""Tests of ``RotationDefinitionValidator`` and of the route with it (unit l2/engine-runner).

Valid rotations are the PLACEHOLDER example of
contracts/rotation_definition/examples/; invalid ones remove or break one field
of that example.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.ports import RotationValidator
from api.rotation_validator import (
    RotationDefinitionValidator,
    load_rotation_definition,
)
from contracts.rotation_definition import RotationDefinition

EXAMPLE = json.loads(
    (
        Path(__file__).parent.parent
        / "contracts"
        / "rotation_definition"
        / "examples"
        / "PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)
ROUTE = "/api/rotations/run"
SITE = {
    "case_id": "PLACEHOLDER_CASE",
    "field_id": "PLACEHOLDER_FIELD",
    "latitude": 1.0,
    "longitude": 2.0,
}
MARKER = "PLACEHOLDER_MARKER_STRING"


def broken(change) -> dict:
    document = copy.deepcopy(EXAMPLE)
    change(document)
    return document


def test_the_example_is_valid():
    validator: RotationValidator = RotationDefinitionValidator()
    assert validator.validate(EXAMPLE) == []
    assert isinstance(load_rotation_definition(EXAMPLE), RotationDefinition)


@pytest.mark.parametrize(
    ("change", "path", "code"),
    [
        (lambda d: d.pop("rotation_id"), "rotation_id", "missing"),
        (lambda d: d.update(repeats="PLACEHOLDER"), "repeats", "bool_type"),
        (
            lambda d: d["components"][0].update(purpose=MARKER),
            "components.0.purpose",
            "literal_error",
        ),
        (
            lambda d: d.update(PLACEHOLDER_EXTRA=MARKER),
            "PLACEHOLDER_EXTRA",
            "extra_forbidden",
        ),
        (
            lambda d: d["components"][1].update(position=1),
            "",
            "value_error",
        ),
    ],
)
def test_each_problem_is_one_detail_with_its_path(change, path, code):
    details = RotationDefinitionValidator().validate(broken(change))
    assert [(d.path, d.code) for d in details] == [(path, code)]
    assert all(d.message for d in details)
    assert all(MARKER not in d.message for d in details)


def test_two_problems_give_two_details():
    def change(document):
        document.pop("label")
        document["components"][0].pop("crop_id")

    details = RotationDefinitionValidator().validate(broken(change))
    assert sorted(d.path for d in details) == ["components.0.crop_id", "label"]


def test_the_default_app_answers_422_for_an_invalid_rotation_without_echo():
    rotation = broken(lambda d: d["components"][0].update(purpose=MARKER))
    response = TestClient(create_app([])).post(
        ROUTE, json={"site": SITE, "rotation": rotation}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert [d["path"] for d in error["details"]] == ["rotation.components.0.purpose"]
    assert MARKER not in response.text


def test_an_error_of_the_whole_rotation_is_reported_at_rotation():
    rotation = broken(lambda d: d["components"][1].update(position=1))
    response = TestClient(create_app([])).post(
        ROUTE, json={"site": SITE, "rotation": rotation}
    )
    assert response.status_code == 422
    assert [d["path"] for d in response.json()["error"]["details"]] == ["rotation"]


def test_the_default_app_accepts_the_example():
    response = TestClient(create_app([])).post(
        ROUTE, json={"site": SITE, "rotation": EXAMPLE}
    )
    assert response.status_code == 200


def test_an_invalid_rotation_reaches_no_source_and_no_engine():
    class Counting:
        source_id = "PLACEHOLDER"
        contract = "PLACEHOLDER"

        def __init__(self) -> None:
            self.calls = 0

        def get_climate(self, request):
            self.calls += 1
            raise AssertionError("not called")

        def get_soil_slope(self, case_id, field_id):
            self.calls += 1
            raise AssertionError("not called")

        def run(self, rotation, climate, soil_slope):
            self.calls += 1
            raise AssertionError("not called")

    counting = Counting()
    app = create_app([], climate=counting, soil_slope=counting, engines=counting)
    rotation = broken(lambda d: d.pop("components"))
    response = TestClient(app).post(ROUTE, json={"site": SITE, "rotation": rotation})
    assert response.status_code == 422
    assert counting.calls == 0
