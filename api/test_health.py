"""Acceptance test of the backend skeleton.

Run with ``uv run pytest api/`` from the repository root.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_answers_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_get_only():
    assert client.post("/health").status_code == 405


def test_unknown_route_is_404():
    assert client.get("/does-not-exist").status_code == 404
