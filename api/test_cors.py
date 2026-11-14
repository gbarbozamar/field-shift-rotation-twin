"""Acceptance test of the CORS settings.

Run with ``uv run pytest api/`` from the repository root.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app, parse_origins

DEV = "http://localhost:5173"
OTHER = "https://not-allowed.example"

client = TestClient(create_app([DEV]))


def test_allowed_origin_gets_header():
    response = client.get("/health", headers={"Origin": DEV})
    assert response.headers.get("access-control-allow-origin") == DEV


def test_other_origin_gets_no_header():
    response = client.get("/health", headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_allowed_origin():
    response = client.options(
        "/health",
        headers={"Origin": DEV, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == DEV


def test_no_origins_means_no_cross_origin_access():
    closed = TestClient(create_app([]))
    response = closed.get("/health", headers={"Origin": DEV})
    assert "access-control-allow-origin" not in response.headers


def test_parse_origins():
    assert parse_origins(None) == []
    assert parse_origins("") == []
    assert parse_origins(f" {DEV}/ , https://a.example,, ") == [
        DEV,
        "https://a.example",
    ]
