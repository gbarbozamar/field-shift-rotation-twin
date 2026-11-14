"""Backend application.

Run locally with ``uv run uvicorn api.main:app --reload`` from the
repository root.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Field Shift Rotation Twin")


class Health(BaseModel):
    """Response of the liveness route."""

    status: Literal["ok"]


@app.get("/health", response_model=Health)
def health() -> Health:
    """Liveness: the process is up and answering. Checks nothing else."""
    return Health(status="ok")
