"""Backend application.

Run locally with ``uv run uvicorn api.main:app --reload`` from the
repository root, or in a container with ``docker compose watch``
(edits reload the server; http://localhost:8000/health).

Settings (environment variables):

- ``CORS_ORIGINS``: comma-separated origins allowed to call the API from a
  browser, e.g. ``http://localhost:5173,https://gbarbozamar.github.io``.
  Empty or unset: no cross-origin access.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class Health(BaseModel):
    """Response of the liveness route."""

    status: Literal["ok"]


def parse_origins(value: str | None) -> list[str]:
    """Split a comma-separated origin list; blanks and trailing slashes dropped."""
    if not value:
        return []
    return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]


def create_app(cors_origins: list[str]) -> FastAPI:
    app = FastAPI(title="Field Shift Rotation Twin")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        """Liveness: the process is up and answering. Checks nothing else."""
        return Health(status="ok")

    return app


app = create_app(parse_origins(os.environ.get("CORS_ORIGINS")))
