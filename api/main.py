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

from adapters.ports import ClimateSource
from api.errors import install_error_handlers
from api.ports import RotationEngines, RotationValidator, RunSettings, SoilSlopeSource
from api.rotations import make_router
from api.standins import (
    AcceptAnyRotation,
    ClimateUnavailable,
    EnginesNotBuilt,
    SoilSlopeNotLoaded,
)


class Health(BaseModel):
    """Response of the liveness route."""

    status: Literal["ok"]


def parse_origins(value: str | None) -> list[str]:
    """Split a comma-separated origin list; blanks and trailing slashes dropped."""
    if not value:
        return []
    return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]


def create_app(
    cors_origins: list[str],
    *,
    climate: ClimateSource | None = None,
    soil_slope: SoilSlopeSource | None = None,
    engines: RotationEngines | None = None,
    rotation_validator: RotationValidator | None = None,
    settings: RunSettings | None = None,
) -> FastAPI:
    """Build the application. ``None`` for an implementation means its stand-in.

    The stand-ins are in ``api/standins.py``; ``settings=None`` means no climate
    record period is configured (OPEN for the science reviewers).
    """
    app = FastAPI(title="Field Shift Rotation Twin")
    install_error_handlers(app)
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

    app.include_router(
        make_router(
            climate=climate if climate is not None else ClimateUnavailable(),
            soil_slope=soil_slope if soil_slope is not None else SoilSlopeNotLoaded(),
            engines=engines if engines is not None else EnginesNotBuilt(),
            rotation_validator=(
                rotation_validator
                if rotation_validator is not None
                else AcceptAnyRotation()
            ),
            settings=settings if settings is not None else RunSettings(),
        )
    )

    return app


app = create_app(parse_origins(os.environ.get("CORS_ORIGINS")))
