"""Route ``POST /api/plant/run``: "What should I plant?" for one field. PROPOSED.

Unit ``l2/plant-route`` (brief S-018; R4, R10, R13, R15 of the loop
decisions). One field, three to five rotations. The body is a
``PlantRequest`` and the answer a ``PlantAnswer`` (contracts/plant_answer/).

What it does, in order:

1. The body is loaded into ``PlantRequest``. A body that fails it is ``422``
   with the one error shape of ``api/errors.py``: ``ROTATION_INVALID`` when
   every problem lies inside one rotation item, ``SITE_INVALID`` when every
   problem lies inside ``site``, ``INVALID_REQUEST`` otherwise (problems in
   several rotation items included). Then each rotation goes through the
   ``RotationValidator``, as on the other routes, with the same rule.
   A message that repeats a submitted value is replaced by a fixed text.
   Nothing is called before that.
2. The climate and the soil and slope are asked for once, for the site, as
   ``POST /api/decisions/run`` asks for them.
3. Each rotation runs once through the ``RotationEngines`` (PROPOSED: phase 1,
   the top-level answer of the run, is enough for the answer). With a
   rain-stress factor, the engines are rebuilt on the catalogue whose
   erosivity is scaled (``api/rain_stress.py``), when the app has a way to
   rebuild them.
4. The kinds of year are the whole agricultural years of the configured
   period (``api.carbon_forcing.whole_ag_years``, read here from the
   settings) classified on the ONI record by ``economics.plant.classify_years``.
   The soil loss per agricultural year of the phase-1 result is averaged by
   kind of year in ``economics.plant`` (``soil_loss_means``).
5. ``economics.plant.assemble_answer`` gives the margins, the limit checks,
   the decision and the tipping price from the runs and the request, through
   the pure functions of ``economics/``.
6. The answer is checked with ``check_answer_against_request`` (inside
   ``assemble_answer``); a failure is a defect of the route (``500``).

The route computes no number itself and decides no rule of which crops and
years count (S-030, point 2 of the platform review of PR 310): every number of
the answer comes from a function of ``economics/`` or ``kinds_of_year/``, or
is copied from an engine result or from the request. The names that moved to
``economics.plant`` are imported back here, so ``from api.plant import ...``
keeps working. What an engine raises is a defect: ``500`` ``INTERNAL_ERROR``,
as on the other routes.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.ports import ClimateSource
from api.carbon_forcing import whole_ag_years
from api.decisions import example_data_of
from api.errors import ErrorCode, error_response, join_path
from api.ports import (
    ErrorDetail,
    RotationEngines,
    RotationValidator,
    RunSettings,
    SoilSlopeSource,
)
from api.rain_stress import (
    RainStress,
    RainStressMissing,
    applied_echo,
    not_applied_detail,
    rain_stress,
    scale_erosivity,
    scales_to_finite,
)
from api.rotation_validator import field_names, safe_message, submitted_texts
from api.rotations import PERIOD_NOT_CONFIGURED, get_climate, source_out
from contracts.plant_answer import PlantRequest
from contracts.rotation_definition import RotationDefinition

# Moved to economics.plant (S-030): the names the route uses, and the names
# imported back so that ``from api.plant import ...`` keeps working.
from economics.plant import (  # noqa: F401
    EROSIVITY,
    IGNORED_YEARS,
    INDICATOR,
    NO_SOIL_LOSS,
    NO_YEAR_READ,
    YEAR_NOT_OF_THE_RECORD,
    Classified,
    CycleYears,
    _todays_price,
    assemble_answer,
    cycle_years,
    plain,
    soil_loss_means,
)

# The same style; ruff's import sorting keeps an aliased name in its own
# statement. The alias frees ``classify_years`` for the wrapper below.
from economics.plant import (
    classify_years as classify_record_years,
)

logger = logging.getLogger(__name__)

ROUTE = "/plant/run"

# Builds the engines for a stressed run from a parameter catalogue. PROPOSED.
EnginesFactory = Callable[[dict[str, dict]], RotationEngines]

# PROPOSED: the source row of the ONI record (contract, state; OPEN 5 of
# contracts/plant_answer/README.md: SourceOut has no state for a record read
# from the repository).
RECORD_CONTRACT = "kinds_of_year_record"
RECORD_STATE = "cached"

# Shown in place of an error text that repeats a submitted value (as
# api/rotation_validator.py does for one rotation). PROPOSED.
REDACTED_MESSAGE = "The value breaks a rule of the plant request contract."

# Written in an error path in place of a key the contract does not define
# (a submitted key is never repeated). PROPOSED.
EXTRA_KEY_SEGMENT = "<extra>"
EXTRA_FORBIDDEN = "extra_forbidden"

# PROPOSED texts of absences the route writes.
NO_FACTORY = (
    "the engines were given to the app without a way to rebuild them on a "
    "parameter catalogue with the erosivity scaled"
)
NO_CATALOGUE = (
    "the engines were given to the app without the parameter catalogue they "
    "use, so there is no erosivity to scale"
)
NOT_FINITE = (
    "the rainfall erosivity of the parameter catalogue times the factor is not "
    "a finite number"
)
NO_WHOLE_YEAR = (
    "the climate record period holds no whole agricultural year for the start "
    "month of the rotations"
)


# --- the request --------------------------------------------------------------


def _owner(loc: Sequence[Any], error_type: str) -> str:
    """Which part of the request an error lies in. PROPOSED, as api/errors.py.

    A rotation item is owned by its index (``rotations.<i>``), so errors in two
    items have two owners.
    """
    if not loc:
        return "envelope"
    if loc[0] == "site" and (len(loc) > 1 or error_type != "missing"):
        return "site"
    # Inside one rotation item; a wrong number of rotations is the envelope's.
    if loc[0] == "rotations" and len(loc) > 1 and isinstance(loc[1], int):
        return f"rotations.{loc[1]}"
    return "envelope"


def _code_of(errors: Sequence[Mapping[str, Any]]) -> ErrorCode:
    """PROPOSED: ``ROTATION_INVALID`` only when every error lies inside one and
    the same rotation item; errors in several items are ``INVALID_REQUEST``."""
    owners = {_owner(tuple(e.get("loc", ())), str(e.get("type", ""))) for e in errors}
    if owners == {"site"}:
        return ErrorCode.SITE_INVALID
    if len(owners) == 1 and next(iter(owners)).startswith("rotations."):
        return ErrorCode.ROTATION_INVALID
    return ErrorCode.INVALID_REQUEST


def _safe_loc(loc: Sequence[Any], error_type: str) -> tuple[Any, ...]:
    """The location of an error with no key the client made up. PROPOSED.

    A key that is not a field name of the model at that point reaches a
    location only as the last segment of an ``extra_forbidden`` error (no
    model of ``PlantRequest`` has a mapping of free keys); it is written as
    ``EXTRA_KEY_SEGMENT``. Every other segment is a field name, an index or a
    tag of the contract.
    """
    if error_type == EXTRA_FORBIDDEN and loc:
        return (*loc[:-1], EXTRA_KEY_SEGMENT)
    return tuple(loc)


def request_problems(
    body: Mapping[str, Any],
) -> tuple[PlantRequest | None, ErrorCode | None, list[ErrorDetail]]:
    """The body loaded into ``PlantRequest``, or the code and details of its errors.

    A message that repeats a submitted value (text of three characters or
    more, as ``api/rotation_validator.py`` looks for) is replaced by
    ``REDACTED_MESSAGE``; the path and the code still say where and what. A
    key that is not a field name of the model at that point is never written
    in the path (``_safe_loc``).
    """
    try:
        request = PlantRequest.model_validate_json(json.dumps(body))
    except ValidationError as error:
        errors = error.errors(
            include_url=False, include_context=False, include_input=False
        )
        submitted = submitted_texts(body)
        known = field_names(PlantRequest)
        details = [
            ErrorDetail(
                path=join_path(_safe_loc(item["loc"], str(item["type"]))),
                code=str(item["type"]),
                message=safe_message(
                    str(item["msg"]), submitted, known, REDACTED_MESSAGE
                ),
            )
            for item in errors
        ]
        return None, _code_of(errors), details
    return request, None, []


def _under_rotation(index: int, problem: ErrorDetail) -> ErrorDetail:
    parts: list[Any] = ["rotations", index]
    if problem.path:
        parts.append(problem.path)
    return ErrorDetail(
        path=join_path(parts), code=problem.code, message=problem.message
    )


# --- years of the record -----------------------------------------------------


def classify_years(
    record: Mapping[str, Any],
    settings: RunSettings,
    start_month: int,
    rotations: Sequence[RotationDefinition],
) -> Classified:
    """PROPOSED: the whole agricultural years of the settings period
    (``api.carbon_forcing.whole_ag_years``), classified on the ONI record.

    Without a period, or with a period that holds no whole agricultural year,
    the record's years are not known; the answer still lists years (the
    contract asks for at least one), the agricultural years of every declared
    date of the rotations, each missing ``NOT_AVAILABLE`` with a detail that
    says they are not years of the record.

    PROPOSED (S-030): this reads the period of the settings and picks the
    text of why the years are not known; the classification itself is
    ``economics.plant.classify_years``.
    """
    years = None
    why = PERIOD_NOT_CONFIGURED
    if settings.has_period:
        assert settings.start_date is not None and settings.end_date is not None
        years = whole_ag_years(start_month, settings.start_date, settings.end_date)
        why = NO_WHOLE_YEAR
    return classify_record_years(record, years, why, start_month, rotations)


# --- the sources and the rain stress ------------------------------------------


def _record_source(record: Mapping[str, Any]) -> dict[str, Any]:
    record_id = record["id"]
    return {
        "id": record_id,
        "contract": RECORD_CONTRACT,
        "state": RECORD_STATE,
        "retrieved_at": None,
        "time_zone": None,
        "request": None,
        "attribution": record.get("reference"),
        "missing_reason": None,
        "detail": (
            f"transcribed record kinds_of_year/records/{record_id}.json, read on "
            f"{record.get('date_read')}"
        ),
    }


@dataclasses.dataclass(frozen=True)
class StressedRun:
    engines: RotationEngines
    echo: RainStress | RainStressMissing | None


def stressed_run(
    request: PlantRequest,
    engines: RotationEngines,
    factory: EnginesFactory | None,
    catalogue: dict[str, dict] | None,
) -> StressedRun:
    """The engines for this request and the rain-stress echo. PROPOSED (R10).

    No factor: the engines unchanged, no echo. A missing factor: the engines
    unchanged, the missing echo. A factor and a factory: the engines rebuilt on
    ``scale_erosivity(catalogue, stress)``, the echo of ``applied_echo``. A
    factor and no factory, or a factory but no catalogue (``None``: the
    engines were injected, so the catalogue they use is not known): the
    engines unchanged and the echo ``applied`` false, with the sentence that
    says why in its detail; never a silent run.

    PROPOSED (S-029, review findings F2 and F3, remark R3): the echo is
    computed first. When it says the factor is not applied (EP1 would not
    read the erosivity of the catalogue as a number), the factory is not
    called and the engines are unchanged: a run on a copy EP1 reads as
    unscaled would only repeat the plain run. When the scaled erosivity is
    not a finite number (``scales_to_finite``, checked before scaling), the
    factor is not applied either, with ``NOT_FINITE`` in the detail, never a
    ``500``. Any ``ValueError`` of ``scale_erosivity`` still surfaces (the
    route's ``500``): it is a defect, not a reason of the echo.
    """
    factor = request.questions.rain_stress_factor
    if factor is None:
        return StressedRun(engines, None)
    stress = rain_stress(factor)
    if isinstance(stress, RainStressMissing):
        return StressedRun(engines, stress)
    if factory is None or catalogue is None:
        why = NO_FACTORY if factory is None else NO_CATALOGUE
        return StressedRun(engines, _not_applied(stress, why))
    echo = applied_echo(catalogue, stress)
    # ``applied_echo`` is typed to return either kind; for a ``RainStress`` it
    # returns one, so this check narrows the type, it is not redundant.
    if isinstance(echo, RainStress) and not echo.applied:
        return StressedRun(engines, echo)
    if not scales_to_finite(catalogue, stress):
        return StressedRun(engines, _not_applied(stress, NOT_FINITE))
    return StressedRun(factory(scale_erosivity(catalogue, stress)), echo)


def _not_applied(stress: RainStress, why: str) -> RainStress:
    return dataclasses.replace(
        stress, applied=False, detail=not_applied_detail(stress.factor, why)
    )


# --- route --------------------------------------------------------------------


def make_plant_router(
    *,
    climate: ClimateSource,
    soil_slope: SoilSlopeSource,
    engines: RotationEngines,
    rotation_validator: RotationValidator,
    settings: RunSettings,
    kinds_of_year_record: Mapping[str, Any],
    engines_factory: EnginesFactory | None,
    parameters: dict[str, dict] | None,
) -> APIRouter:
    """The plant route, bound to the given implementations."""
    router = APIRouter(prefix="/api")

    @router.post(ROUTE, responses={400: {}, 422: {}, 500: {}})
    def run_plant(body: dict[str, Any] = Body(...)):  # noqa: B008
        """Answer "What should I plant?" for one field and three to five rotations."""
        try:
            request, code, problems = request_problems(body)
            if request is None:
                assert code is not None
                return error_response(code, problems)
            rotations = body["rotations"]
            problems = []
            items = set()
            for index, rotation in enumerate(rotations):
                for problem in rotation_validator.validate(rotation):
                    problems.append(_under_rotation(index, problem))
                    items.add(index)
            if problems:
                # PROPOSED: one item is ROTATION_INVALID, several are
                # INVALID_REQUEST, as for the errors of PlantRequest (_code_of).
                return error_response(
                    ErrorCode.ROTATION_INVALID
                    if len(items) == 1
                    else ErrorCode.INVALID_REQUEST,
                    problems,
                )

            climate_result = get_climate(climate, request.site, settings)
            soil_result = soil_slope.get_soil_slope(
                request.site.case_id, request.site.field_id
            )
            run = stressed_run(request, engines, engines_factory, parameters)
            runs = [
                run.engines.run(rotation, climate_result, soil_result)
                for rotation in rotations
            ]
            infos = [climate_result.source, soil_result.source]
            sources = [
                *(source_out(info).model_dump(mode="json") for info in infos),
                _record_source(kinds_of_year_record),
            ]
            example_data = (
                request.example_data
                or example_data_of(rotations, climate_result, soil_result)
                or any(info.state == "example" for info in infos)
            )
            classified = classify_years(
                kinds_of_year_record,
                settings,
                request.rotations[0].ag_year_start.month,
                request.rotations,
            )
            answer = assemble_answer(
                request,
                runs,
                classified=classified,
                record=kinds_of_year_record,
                rain_stress=None if run.echo is None else plain(run.echo),
                sources=sources,
                example_data=example_data,
            )
            # Never ``exclude_none``: a document written that way does not load back.
            return JSONResponse(content=answer.model_dump(mode="json"))
        except Exception:
            logger.exception("POST /api/plant/run failed")
            return error_response(ErrorCode.INTERNAL_ERROR)

    return router
