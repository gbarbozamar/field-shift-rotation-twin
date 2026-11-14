"""Acceptance test of the one error shape on every route.

Run with ``uv run pytest api/`` from the repository root.

Status: PROPOSED test cases (blueprint section 3.7). Every number is an
obvious placeholder and every identifier is ``PLACEHOLDER_...``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.errors import ErrorCode, classify_validation_errors
from api.main import create_app

ROUTE = "/api/rotations/run"
SITE = {
    "case_id": "PLACEHOLDER_CASE",
    "field_id": "PLACEHOLDER_FIELD",
    "latitude": 1.0,
    "longitude": 2.0,
}
# A valid rotation: the PLACEHOLDER example of the rotation definition.
ROTATION = json.loads(
    (
        Path(__file__).parent.parent
        / "contracts"
        / "rotation_definition"
        / "examples"
        / "PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)

client = TestClient(create_app([]))


def error_of(response) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    for detail in body["error"]["details"]:
        assert set(detail) == {"path", "code", "message"}
    return body["error"]


def test_get_on_run_route_is_405_with_allow_header():
    response = client.get(ROUTE)
    assert response.status_code == 405
    assert error_of(response)["code"] == "METHOD_NOT_ALLOWED"
    assert "POST" in response.headers.get("allow", "")


def test_malformed_json_is_400():
    response = client.post(
        ROUTE, content=b"{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert error_of(response)["code"] == "MALFORMED_JSON"


def test_missing_rotation_is_invalid_request():
    response = client.post(ROUTE, json={"site": SITE})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_REQUEST"
    assert "rotation" in [d["path"] for d in error["details"]]


def test_unknown_top_level_field_is_invalid_request():
    response = client.post(
        ROUTE, json={"site": SITE, "rotation": ROTATION, "PLACEHOLDER_EXTRA": "x"}
    )
    assert response.status_code == 422
    assert error_of(response)["code"] == "INVALID_REQUEST"


def test_wrong_content_type_is_invalid_request():
    response = client.post(
        ROUTE, content=b"PLACEHOLDER_TEXT", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 422
    assert error_of(response)["code"] == "INVALID_REQUEST"


def test_rotation_not_an_object_is_rotation_invalid():
    response = client.post(ROUTE, json={"site": SITE, "rotation": "PLACEHOLDER"})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "ROTATION_INVALID"
    assert all(d["path"].startswith("rotation") for d in error["details"])


def test_latitude_out_of_range_is_site_invalid():
    site = {**SITE, "latitude": 1000.0}
    response = client.post(ROUTE, json={"site": site, "rotation": ROTATION})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "SITE_INVALID"
    assert [d["path"] for d in error["details"]] == ["site.latitude"]


def test_unknown_field_in_site_is_site_invalid():
    site = {**SITE, "PLACEHOLDER_EXTRA": "x"}
    response = client.post(ROUTE, json={"site": site, "rotation": ROTATION})
    assert response.status_code == 422
    assert error_of(response)["code"] == "SITE_INVALID"


def test_submitted_input_is_never_echoed():
    marker = "PLACEHOLDER_MARKER_STRING"
    site = {**SITE, "latitude": marker}
    response = client.post(ROUTE, json={"site": site, "rotation": ROTATION})
    assert response.status_code == 422
    assert marker not in response.text
    for detail in error_of(response)["details"]:
        assert set(detail) == {"path", "code", "message"}


def test_unknown_route_is_404_in_error_shape():
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    error = error_of(response)
    assert error["code"] == "NOT_FOUND"
    assert error["details"] == []


@pytest.mark.parametrize(
    ("errors", "expected"),
    [
        ([{"type": "json_invalid", "loc": ("body", 1)}], ErrorCode.MALFORMED_JSON),
        ([], ErrorCode.INVALID_REQUEST),
        ([{"type": "missing", "loc": ("body", "site")}], ErrorCode.INVALID_REQUEST),
        (
            [{"type": "missing", "loc": ("body", "rotation")}],
            ErrorCode.INVALID_REQUEST,
        ),
        (
            [{"type": "missing", "loc": ("body", "site", "case_id")}],
            ErrorCode.SITE_INVALID,
        ),
        (
            [{"type": "dict_type", "loc": ("body", "rotation")}],
            ErrorCode.ROTATION_INVALID,
        ),
        (
            [
                {"type": "less_than_equal", "loc": ("body", "site", "latitude")},
                {"type": "dict_type", "loc": ("body", "rotation")},
            ],
            ErrorCode.INVALID_REQUEST,
        ),
        (
            [{"type": "extra_forbidden", "loc": ("body", "PLACEHOLDER_EXTRA")}],
            ErrorCode.INVALID_REQUEST,
        ),
        (
            [{"type": "model_attributes_type", "loc": ("body",)}],
            ErrorCode.INVALID_REQUEST,
        ),
    ],
)
def test_classify_validation_errors(errors, expected):
    assert classify_validation_errors(errors) is expected
