"""Route ``POST /api/rotations/run``: one rotation, end to end.

The route depends only on interfaces (``adapters.ports.ClimateSource``,
``adapters.ports.SoilSlopeSource`` and the protocols of ``api/ports.py``). It never imports a concrete adapter or engine,
never knows whether data came from a cache, and never builds a number: it
copies what the interfaces return into one envelope.

A valid request always answers ``200``, also when nothing could be computed:
values then travel as missing with a reason code (contracts/CONVENTIONS.md
C3.2), never as zero.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from adapters.ports import ClimateRequest, ClimateResult, ClimateSource, SourceInfo
from api.errors import ErrorCode, error_response, join_path
from api.ports import (
    EnginesResult,
    ErrorDetail,
    ModuleState,
    ReasonCode,
    RotationEngines,
    RotationValidator,
    RunSettings,
    SoilSlopeSource,
)

logger = logging.getLogger(__name__)

PERIOD_NOT_CONFIGURED = "the climate record period is not configured"

NonEmpty = Annotated[str, Field(min_length=1)]

# --- request ------------------------------------------------------------------


class SiteReference(BaseModel):
    """Which field of which case, and the point that stands for it.

    PROPOSED (blueprint section 3.7). Which contract carries field identity is
    OPEN; this model is the only place that knows the shape of ``site``, so it
    is replaced in one spot. How the point is chosen for a field is OPEN
    (adapters/ports.py).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: NonEmpty
    field_id: NonEmpty
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class RunRotationRequest(BaseModel):
    """Body of ``POST /api/rotations/run``.

    ``rotation`` is one item of the "Rotation definition" contract, unchanged.
    Here it only has to be a JSON object; its contents are checked by the
    ``RotationValidator``.
    """

    model_config = ConfigDict(extra="forbid")

    site: SiteReference
    rotation: dict[str, Any]


# --- response -----------------------------------------------------------------

Outcome = Literal["complete", "partial", "no_result"]


class MissingOut(BaseModel):
    reason: ReasonCode
    detail: str | None = None


class ModuleOut(BaseModel):
    id: str
    state: ModuleState
    reason: ReasonCode | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def _reason_unless_available(self) -> Self:
        if self.state != "available" and self.reason is None:
            raise ValueError(f"module {self.id!r}: reason required when {self.state}")
        return self


class SourceOut(BaseModel):
    id: str
    contract: str
    state: Literal["fresh", "cached", "unavailable", "example"]
    retrieved_at: dt.datetime | None = None
    time_zone: str | None = None
    request: dict[str, Any] | None = None
    attribution: str | None = None
    missing_reason: ReasonCode | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def _reason_when_unavailable(self) -> Self:
        if self.state == "unavailable" and self.missing_reason is None:
            raise ValueError(f"source {self.id!r}: missing_reason required")
        if self.retrieved_at is not None and self.retrieved_at.utcoffset() is None:
            raise ValueError(f"source {self.id!r}: retrieved_at has no time zone")
        return self

    @field_serializer("retrieved_at")
    def _utc(self, value: dt.datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunRotationResponse(BaseModel):
    """The success envelope. ``result_missing`` is non-null exactly when ``result`` is null."""

    outcome: Outcome
    calendar: dict[str, Any] | None
    result: dict[str, Any] | None
    result_missing: MissingOut | None
    modules: list[ModuleOut]
    sources: list[SourceOut]

    @model_validator(mode="after")
    def _missing_iff_no_result(self) -> Self:
        if (self.result is None) != (self.result_missing is not None):
            raise ValueError("result_missing must be set exactly when result is null")
        return self


def derive_outcome(
    result_present: bool,
    values_present: int,
    values_missing: int,
    module_states: Sequence[ModuleState],
    source_states: Sequence[str],
) -> Outcome:
    """Outcome of a run. PROPOSED.

    - ``no_result`` when there is no result, or no value in it is present
      (an infeasible calendar ends here, issue 18);
    - ``complete`` when no value is missing, every module is ``available`` and
      no source is ``unavailable``;
    - ``partial`` otherwise.
    """
    if not result_present or values_present == 0:
        return "no_result"
    if (
        values_missing == 0
        and all(s == "available" for s in module_states)
        and all(s != "unavailable" for s in source_states)
    ):
        return "complete"
    return "partial"


def _source_out(info: SourceInfo) -> SourceOut:
    return SourceOut(
        id=info.id,
        contract=info.contract,
        state=info.state,
        retrieved_at=info.retrieved_at,
        time_zone=info.time_zone,
        request=dict(info.request) if info.request is not None else None,
        attribution=info.attribution,
        missing_reason=info.missing_reason,
        detail=info.detail,
    )


def build_envelope(
    engines: EnginesResult, sources: Sequence[SourceInfo]
) -> RunRotationResponse:
    """Copy what the interfaces returned into the envelope. Raises on a defect."""
    modules = [
        ModuleOut(id=m.id, state=m.state, reason=m.reason, detail=m.detail)
        for m in engines.modules
    ]
    return RunRotationResponse(
        outcome=derive_outcome(
            engines.result is not None,
            engines.values_present,
            engines.values_missing,
            [m.state for m in modules],
            [s.state for s in sources],
        ),
        # Never ``exclude_none``: a document written that way does not load back.
        calendar=(
            engines.calendar.model_dump(mode="json")
            if engines.calendar is not None
            else None
        ),
        result=(
            engines.result.model_dump(mode="json")
            if engines.result is not None
            else None
        ),
        result_missing=(
            MissingOut(
                reason=engines.result_missing.reason,
                detail=engines.result_missing.detail,
            )
            if engines.result_missing is not None
            else None
        ),
        modules=modules,
        sources=[_source_out(s) for s in sources],
    )


# --- route --------------------------------------------------------------------


def make_router(
    *,
    climate: ClimateSource,
    soil_slope: SoilSlopeSource,
    engines: RotationEngines,
    rotation_validator: RotationValidator,
    settings: RunSettings,
) -> APIRouter:
    """The rotation routes, bound to the given implementations."""
    router = APIRouter(prefix="/api")

    @router.post(
        "/rotations/run",
        response_model=RunRotationResponse,
        responses={400: {}, 422: {}, 500: {}},
    )
    def run_rotation(body: RunRotationRequest):
        """Run one rotation for one field against the configured record period."""
        try:
            problems = rotation_validator.validate(body.rotation)
            if problems:
                return error_response(
                    ErrorCode.ROTATION_INVALID,
                    [_under_rotation(p) for p in problems],
                )
            climate_result = _get_climate(climate, body.site, settings)
            soil_result = soil_slope.get_soil_slope(
                body.site.case_id, body.site.field_id
            )
            engines_result = engines.run(body.rotation, climate_result, soil_result)
            envelope = build_envelope(
                engines_result, [climate_result.source, soil_result.source]
            )
            return JSONResponse(content=envelope.model_dump(mode="json"))
        except Exception:
            logger.exception("POST /api/rotations/run failed")
            return error_response(ErrorCode.INTERNAL_ERROR)

    return router


def _get_climate(
    climate: ClimateSource, site: SiteReference, settings: RunSettings
) -> ClimateResult:
    if not settings.has_period:
        return ClimateResult(
            data=None,
            source=SourceInfo(
                id=climate.source_id,
                contract=climate.contract,
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
                detail=PERIOD_NOT_CONFIGURED,
            ),
        )
    assert settings.start_date is not None and settings.end_date is not None
    return climate.get_climate(
        ClimateRequest(
            case_id=site.case_id,
            field_id=site.field_id,
            latitude=site.latitude,
            longitude=site.longitude,
            start_date=settings.start_date,
            end_date=settings.end_date,
        )
    )


def _under_rotation(problem: ErrorDetail) -> ErrorDetail:
    path = join_path(["rotation", problem.path]) if problem.path else "rotation"
    return ErrorDetail(path=path, code=problem.code, message=problem.message)
