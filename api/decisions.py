"""Route ``POST /api/decisions/run``: two rotations of one field, and their decision.

The route that issue #268 waits for ("the route that serves a decision
output"). Shape PROPOSED by unit ``l2/decision-route``, from option 1 of the
proposal the lead developer chose (two rotations of one site, the decision
output of their pair, no limit, no tolerance, no sweep). The interface
developer accepts or corrects it as consumer.

What it does, in order:

1. Each rotation goes through the ``RotationValidator``; a problem is
   ``422`` ``ROTATION_INVALID`` with its path under ``rotations.<index>``.
   Two rotations with one ``rotation_id``, or a rotation of another
   ``case_id`` or ``field_id`` than ``site``, are ``422`` too. Nothing is
   called before that.
2. The climate and the soil and slope are asked for once, for the site, as
   ``POST /api/rotations/run`` asks for them.
3. Each rotation runs through the same ``RotationEngines`` as that route,
   with the same inputs.
4. The results table is built from the runs (``api/results_table.py``).
5. The decision layer turns the table into the decision output document
   (``api/decision_layer.py``).

A valid request always answers ``200``. ``decision`` is the
``DecisionOutput`` of contracts/decision_output/, serialised with every null
kept (``model_dump(mode="json")``, never ``exclude_none``), or ``null`` with
``decision_missing`` and its reason: a rotation without a result, a part
whose engine is not built, runs that do not hold the same cells, or a
decision layer that is not built or fails (``_decide``). What an engine
raises is a defect: ``500`` ``INTERNAL_ERROR``, as on the existing route.

The route depends only on interfaces. It never imports ``engine/`` or
``decision/``, never builds a number, and changes nothing it copies.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Self

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adapters.ports import ClimateResult, ClimateSource, SoilSlopeResult
from api.decision_layer import check_document
from api.errors import ErrorCode, error_response, join_path
from api.ports import (
    DecisionLayer,
    ErrorDetail,
    Missing,
    RotationEngines,
    RotationValidator,
    RunSettings,
    SoilSlopeSource,
)
from api.results_table import RotationRun, build_results_table
from api.rotations import (
    MissingOut,
    ModuleOut,
    Outcome,
    SiteReference,
    SourceOut,
    build_envelope,
    get_climate,
)

logger = logging.getLogger(__name__)

ROUTE = "/decisions/run"

# PROPOSED: the number of rotations the route takes (option 1: one pair).
ROTATIONS_PER_REQUEST = 2

# PROPOSED error-detail codes and texts. A text names a field, never a value
# the request carried.
NOT_THE_SITE = "not_the_site"
REPEATED = "repeated"
NOT_THE_SITE_MESSAGE = "the {field} of this rotation is not the {field} of site"
REPEATED_MESSAGE = "this rotation_id is the rotation_id of an earlier rotation"
# PROPOSED: the detail of a decision layer that failed (it names the kind of
# error only; the error itself goes to the server log, never to the answer).
LAYER_FAILED = (
    "the decision layer failed ({kind}), so no decision is given; the failure is "
    "in the server log"
)

# --- request ------------------------------------------------------------------


class RunDecisionRequest(BaseModel):
    """Body of ``POST /api/decisions/run``. PROPOSED.

    ``site`` is the ``SiteReference`` of ``POST /api/rotations/run``.
    ``rotations`` holds exactly two items of the "Rotation definition"
    contract, unchanged; here each only has to be a JSON object, and its
    contents are checked by the ``RotationValidator``.
    """

    model_config = ConfigDict(extra="forbid")

    site: SiteReference
    rotations: list[dict[str, Any]] = Field(
        min_length=ROTATIONS_PER_REQUEST, max_length=ROTATIONS_PER_REQUEST
    )


# --- response -----------------------------------------------------------------


class PhaseSummary(BaseModel):
    """One phase of one rotation: how its run ended (the full result is not here)."""

    scenario_id: str
    first_ag_year: int | None
    outcome: Outcome
    result_missing: MissingOut | None


class RotationSummary(BaseModel):
    """One rotation of the request: the top-level answer of its run (phase 1),
    as ``POST /api/rotations/run`` gives it, and how each phase ended. The
    calendar and the result are not repeated here: that route serves them."""

    rotation_id: str
    outcome: Outcome
    result_missing: MissingOut | None
    modules: list[ModuleOut]
    phases: list[PhaseSummary]


class PhaseOfRotationOut(BaseModel):
    rotation_id: str
    phase: str


class PairedScenarioOut(BaseModel):
    """One scenario of the decision: the phase of each rotation it holds."""

    scenario_id: str
    phases: list[PhaseOfRotationOut]


class RunDecisionResponse(BaseModel):
    """The success envelope. ``decision_missing`` is non-null exactly when
    ``decision`` is null. ``scenarios`` is the legend of the scenarios of the
    results table (and so of the decision), empty when there is no table.
    ``sources`` is written once: both rotations ran on the same inputs.
    PROPOSED."""

    decision: dict[str, Any] | None
    decision_missing: MissingOut | None
    scenarios: list[PairedScenarioOut]
    rotations: list[RotationSummary]
    sources: list[SourceOut]

    @model_validator(mode="after")
    def _missing_iff_no_decision(self) -> Self:
        if (self.decision is None) != (self.decision_missing is not None):
            raise ValueError(
                "decision_missing must be set exactly when decision is null"
            )
        if self.decision is not None and sorted(self.decision["scenarios"]) != sorted(
            s.scenario_id for s in self.scenarios
        ):
            raise ValueError("the legend names the scenarios of the decision")
        return self


def example_data_of(
    rotations: Sequence[Mapping[str, Any]],
    climate: ClimateResult,
    soil_slope: SoilSlopeResult,
) -> bool:
    """The example mark of the document: true when a rotation definition, the
    climate or the soil and slope says ``example_data: true``. It reads the
    mark each input carries itself, as ``api/carbon_forcing.py`` marks the
    forcing from the calendar (which copies the rotation's mark), the climate
    and the soil and slope. An input that is absent carries no mark. PROPOSED."""
    return any(rotation.get("example_data") is True for rotation in rotations) or any(
        data.example_data
        for data in (climate.data, soil_slope.data)
        if data is not None
    )


def _missing_out(missing: Missing) -> MissingOut:
    return MissingOut(reason=missing.reason, detail=missing.detail)


def _decide(layer: DecisionLayer, table: Any, *, example_data: bool) -> Any:
    """The decision layer's answer, or a typed absence when it fails. PROPOSED.

    A decision layer that fails to load, raises, or returns a document that
    does not match its table answers ``200`` with ``decision_missing``
    ``NOT_AVAILABLE`` (C3.2: the module is not enabled), the kind of error in
    the detail and the error in the log. The document is checked here
    (``check_document``) whatever the implementation of ``DecisionLayer``,
    not only by the default one. The engines are not covered: what they raise
    is still ``500``, as on the existing route.
    """
    try:
        answer = layer.decide(table, example_data=example_data)
        if isinstance(answer, Missing):
            return answer
        return check_document(answer, table, example_data=example_data)
    except Exception as error:
        logger.exception("POST /api/decisions/run: the decision layer failed")
        return Missing(
            reason="NOT_AVAILABLE",
            detail=LAYER_FAILED.format(kind=type(error).__name__),
        )


def _under_rotation(index: int, problem: ErrorDetail) -> ErrorDetail:
    path = (
        join_path(["rotations", index, problem.path])
        if problem.path
        else join_path(["rotations", index])
    )
    return ErrorDetail(path=path, code=problem.code, message=problem.message)


def identity_problems(
    site: SiteReference, rotations: Sequence[Mapping[str, Any]]
) -> list[ErrorDetail]:
    """Rotations of another case or field than ``site``, and a ``rotation_id``
    given twice. The details name the field, never its value. PROPOSED."""
    problems: list[ErrorDetail] = []
    seen: list[Any] = []
    for index, rotation in enumerate(rotations):
        for field in ("case_id", "field_id"):
            if rotation.get(field) != getattr(site, field):
                problems.append(
                    ErrorDetail(
                        path=join_path(["rotations", index, field]),
                        code=NOT_THE_SITE,
                        message=NOT_THE_SITE_MESSAGE.format(field=field),
                    )
                )
        rotation_id = rotation.get("rotation_id")
        if rotation_id in seen:
            problems.append(
                ErrorDetail(
                    path=join_path(["rotations", index, "rotation_id"]),
                    code=REPEATED,
                    message=REPEATED_MESSAGE,
                )
            )
        seen.append(rotation_id)
    return problems


# --- route --------------------------------------------------------------------


def make_decision_router(
    *,
    climate: ClimateSource,
    soil_slope: SoilSlopeSource,
    engines: RotationEngines,
    rotation_validator: RotationValidator,
    settings: RunSettings,
    decision_layer: DecisionLayer,
) -> APIRouter:
    """The decision route, bound to the given implementations."""
    router = APIRouter(prefix="/api")

    @router.post(
        ROUTE,
        response_model=RunDecisionResponse,
        responses={400: {}, 422: {}, 500: {}},
    )
    def run_decision(body: RunDecisionRequest):
        """Run two rotations of one field and return the decision output of the pair."""
        try:
            problems = [
                _under_rotation(index, problem)
                for index, rotation in enumerate(body.rotations)
                for problem in rotation_validator.validate(rotation)
            ]
            if not problems:
                problems = identity_problems(body.site, body.rotations)
            if problems:
                return error_response(ErrorCode.ROTATION_INVALID, problems)

            climate_result = get_climate(climate, body.site, settings)
            soil_result = soil_slope.get_soil_slope(
                body.site.case_id, body.site.field_id
            )
            sources = [climate_result.source, soil_result.source]
            runs = [
                engines.run(rotation, climate_result, soil_result)
                for rotation in body.rotations
            ]
            # The envelope of the existing route: same outcome rule, same checks.
            envelopes = [build_envelope(run, sources) for run in runs]
            rotation_ids = [rotation["rotation_id"] for rotation in body.rotations]

            answer = build_results_table(
                body.site.case_id,
                body.site.field_id,
                [
                    RotationRun(rotation_id=rotation_id, run=run)
                    for rotation_id, run in zip(rotation_ids, runs, strict=True)
                ],
            )
            decision: dict[str, Any] | None = None
            decision_missing: MissingOut | None = None
            if answer.table is None:
                assert answer.missing is not None
                decision_missing = _missing_out(answer.missing)
            else:
                outcome = _decide(
                    decision_layer,
                    answer.table,
                    example_data=example_data_of(
                        body.rotations, climate_result, soil_result
                    ),
                )
                if isinstance(outcome, Missing):
                    decision_missing = _missing_out(outcome)
                else:
                    # Never ``exclude_none``: a document written that way does
                    # not load back.
                    decision = outcome.model_dump(mode="json")

            response = RunDecisionResponse(
                decision=decision,
                decision_missing=decision_missing,
                scenarios=[
                    PairedScenarioOut(
                        scenario_id=scenario.scenario_id,
                        phases=[
                            PhaseOfRotationOut(
                                rotation_id=phase.rotation_id, phase=phase.phase
                            )
                            for phase in scenario.phases
                        ],
                    )
                    for scenario in answer.scenarios
                ],
                rotations=[
                    RotationSummary(
                        rotation_id=rotation_id,
                        outcome=envelope.outcome,
                        result_missing=envelope.result_missing,
                        modules=envelope.modules,
                        phases=[
                            PhaseSummary(
                                scenario_id=phase.scenario_id,
                                first_ag_year=phase.first_ag_year,
                                outcome=phase.outcome,
                                result_missing=phase.result_missing,
                            )
                            for phase in envelope.scenarios
                        ],
                    )
                    for rotation_id, envelope in zip(
                        rotation_ids, envelopes, strict=True
                    )
                ],
                sources=envelopes[0].sources,
            )
            return JSONResponse(content=response.model_dump(mode="json"))
        except Exception:
            logger.exception("POST /api/decisions/run failed")
            return error_response(ErrorCode.INTERNAL_ERROR)

    return router
