"""Route ``POST /api/plant/run``: "What should I plant?" for one field. PROPOSED.

Unit ``l2/plant-route`` (brief S-018; R4, R10, R13, R15 of the loop
decisions). One field, three to five rotations. The body is a
``PlantRequest`` and the answer a ``PlantAnswer`` (contracts/plant_answer/).

What it does, in order:

0. PROPOSED (unit ``l2/plant-layer-by-name``, S-031, decision R24): the plant
   layer is found by name (``api/plant_layer.py``, ``DiscoveredPlantLayer``
   unless ``create_app`` was given another ``PlantLayer``). Not built: ``200``
   with exactly ``{"answer": null, "answer_missing": {"reason":
   "NOT_AVAILABLE", "detail": ...}}`` (R27, the form of #427), and nothing
   is called. A
   plant layer that fails to import is ``500`` ``INTERNAL_ERROR`` here only.
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
4. The whole agricultural years of the configured period
   (``api.carbon_forcing.whole_ag_years``, read here from the settings,
   ``record_years_of``) and the ONI record go to the entry function
   ``economics.plant.answer_plant`` (S-031), which classifies them
   (``classify_years``) and averages the soil loss per agricultural year of
   the phase-1 result by kind of year (``soil_loss_means``). The record is
   the one ``KINDS_OF_YEAR_RECORD_FILE`` names, read once at start-up
   (``api/config.py``); without it every kind of year is missing
   ``NOT_AVAILABLE`` (``economics.plant.RECORD_NOT_CONFIGURED``) and its
   source row is ``unavailable`` with ``NO_RECORD``, which names the
   variable.
5. ``answer_plant`` (through ``assemble_answer``) gives the margins, the
   limit checks, the decision and the tipping price from the runs and the
   request, through the pure functions of ``economics/``.
6. The answer is checked with ``check_answer_against_request`` (inside
   ``assemble_answer``), and here to be a ``PlantAnswer``; a failure is a
   defect (``500``).

The route computes no number itself and decides no rule of which crops and
years count (S-030, point 2 of the platform review of PR 310): every number of
the answer comes from a function of ``economics/`` or ``kinds_of_year/``, or
is copied from an engine result or from the request. The names that moved to
``economics.plant`` are imported back here on first use (module
``__getattr__``), so ``from api.plant import ...`` keeps working while this
module imports nothing of ``economics/``, ``kinds_of_year/`` or
``contracts.plant_answer`` when it is imported (S-031). What an engine raises is a defect: ``500`` ``INTERNAL_ERROR``,
as on the other routes.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.ports import ClimateSource
from api.carbon_forcing import whole_ag_years
from api.decisions import example_data_of
from api.errors import ErrorCode, error_response, join_path
from api.plant_layer import DiscoveredPlantLayer, not_built_body
from api.ports import (
    ErrorDetail,
    Missing,
    PlantLayer,
    PlantParts,
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
from api.rotations import (
    PERIOD_NOT_CONFIGURED,
    get_climate,
    source_out,
)

# PROPOSED (S-034, F3): the reason code (C3.2) of an absent period, the one
# ``api.rotations.get_climate`` writes on the climate source row.
from api.rotations import (
    PERIOD_NOT_CONFIGURED_REASON as PERIOD_REASON,
)

if TYPE_CHECKING:
    from contracts.plant_answer import PlantRequest

# Moved to economics.plant (S-030). PROPOSED (S-031): imported back lazily,
# on first use, by ``__getattr__`` below, so ``from api.plant import ...``
# keeps working while this module imports nothing of economics/ when the app
# starts (decision R24).
_FROM_ECONOMICS = frozenset(
    {
        "Classified",
        "_todays_price",
        "assemble_answer",
        "cycle_years",
        "plain",
        "soil_loss_means",
    }
)


def __getattr__(name: str) -> Any:
    if name in _FROM_ECONOMICS:
        import economics.plant

        return getattr(economics.plant, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


logger = logging.getLogger(__name__)

ROUTE = "/plant/run"

# Builds the engines for a stressed run from a parameter catalogue. PROPOSED.
EnginesFactory = Callable[[dict[str, dict]], RotationEngines]

# PROPOSED: the source row of the ONI record (contract, state). The state is
# "cached", as main's contract lists the record (OPEN 5 of
# contracts/plant_answer/README.md, #424): SourceOut has no state for a record
# read from a file. S-031 had proposed a state "transcribed"; main's contract
# does not have it (decision R27 of the loop, PROPOSED).
RECORD_CONTRACT = "kinds_of_year_record"
RECORD_STATE = "cached"
# PROPOSED (S-031): the id of the record's source row when there is no record
# id to name (no record configured, or an injected record without ``id``).
# Fix round 1 (F2): the same text and rule as ``economics.plant.NO_RECORD_ID``
# and ``economics.plant.record_id`` (the answer's kinds_of_year.source), which
# this module may not import when it is loaded; api/test_plant_layer.py
# checks that the two agree.
NO_RECORD_ID = RECORD_CONTRACT
# PROPOSED (S-031): why there is no record. It names the variable a person
# sets to switch the record on (api/config.py), never a submitted value.
NO_RECORD = (
    "the kinds-of-year record is not configured (KINDS_OF_YEAR_RECORD_FILE is "
    "not set), so no agricultural year is classified as a kind of year"
)

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
# PROPOSED (S-032, decision R25, fix round 1): the heavier-rain stress test is
# a modelling choice inside api/ until the erosion lane takes it as an option
# of EP1, so a person switches it on with RAIN_STRESS_TEST=on (api/config.py).
# The sentence is shown to public users: it names no server variable.
NOT_SWITCHED_ON = "heavier rain is not switched on in this service"
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
    model: Any = None,
) -> tuple[PlantRequest | None, ErrorCode | None, list[ErrorDetail]]:
    """The body loaded into ``PlantRequest``, or the code and details of its errors.

    A message that repeats a submitted value (text of three characters or
    more, as ``api/rotation_validator.py`` looks for) is replaced by
    ``REDACTED_MESSAGE``; the path and the code still say where and what. A
    key that is not a field name of the model at that point is never written
    in the path (``_safe_loc``).

    PROPOSED (S-031): ``model`` is the request model the plant layer gave
    (``PlantParts.request_model``); ``None`` imports
    ``contracts.plant_answer.PlantRequest`` here, on the call, never when
    this module is imported.
    """
    if model is None:
        from contracts.plant_answer import PlantRequest as model
    try:
        request = model.model_validate_json(json.dumps(body))
    except ValidationError as error:
        errors = error.errors(
            include_url=False, include_context=False, include_input=False
        )
        submitted = submitted_texts(body)
        known = field_names(model)
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


RecordYears = tuple[tuple[int, int] | None, str, str | None]


def record_years_of(settings: RunSettings, start_month: int) -> RecordYears:
    """PROPOSED: the whole agricultural years of the settings period
    (``api.carbon_forcing.whole_ag_years``), or ``None``, with the text of
    why they are not known and its reason code (C3.2) when there is one.

    Without a period, or with a period that holds no whole agricultural year,
    the record's years are not known; ``economics.plant.classify_years`` then
    lists the agricultural years of every declared date of the rotations,
    each missing ``NOT_AVAILABLE``.

    PROPOSED (S-030): this reads the period of the settings and picks the
    text of why the years are not known; the classification itself is in
    ``economics.plant`` (S-031: called by ``answer_plant``).

    PROPOSED (S-034, F3): without a period the reason is the one
    ``api.rotations.get_climate`` gives an absent period (``PERIOD_REASON``),
    so the soil-loss means carry it, not ``NO_COVERAGE``.
    """
    if settings.has_period:
        assert settings.start_date is not None and settings.end_date is not None
        years = whole_ag_years(start_month, settings.start_date, settings.end_date)
        return years, NO_WHOLE_YEAR, None
    return None, PERIOD_NOT_CONFIGURED, PERIOD_REASON


# --- the sources and the rain stress ------------------------------------------


def _record_source(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """The source row of the ONI record. PROPOSED.

    No record (``None``: ``KINDS_OF_YEAR_RECORD_FILE`` not set): state
    ``unavailable``, ``NOT_AVAILABLE``, with ``NO_RECORD`` as its detail
    (S-031, point 7). A record: state ``RECORD_STATE`` (point 8).
    PROPOSED (S-031, F5): ``api/config.py`` refuses a record without ``id``
    or ``date_read`` at start-up; a record injected without them (tests)
    gives a row whose id is ``NO_RECORD_ID`` and whose detail leaves out the
    date, never "None" and never a ``KeyError``.
    PROPOSED (fix round 1, F7): the detail is ``transcribed record {id}``,
    then ``, read on {date_read}`` when the record has it; no path, since any
    path can be configured.
    """
    row: dict[str, Any] = {
        "id": NO_RECORD_ID,
        "contract": RECORD_CONTRACT,
        "state": "unavailable",
        "retrieved_at": None,
        "time_zone": None,
        "request": None,
        "attribution": None,
        "missing_reason": "NOT_AVAILABLE",
        "detail": NO_RECORD,
    }
    if record is None:
        return row
    value = record.get("id")
    record_id = NO_RECORD_ID if value is None else str(value)
    date_read = record.get("date_read")
    detail = f"transcribed record {record_id}"
    if date_read is not None:
        detail = f"{detail}, read on {date_read}"
    return {
        **row,
        "id": record_id,
        "state": RECORD_STATE,
        "attribution": record.get("reference"),
        "missing_reason": None,
        "detail": detail,
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
    *,
    rain_stress_switched_on: bool,
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

    PROPOSED (S-032, decision R25): ``rain_stress_switched_on`` is required
    (no default, so a forgotten pass fails loudly). False: a declared factor is not applied: the engines unchanged,
    the echo ``applied`` false with ``NOT_SWITCHED_ON`` in its detail, and
    the factory never called. No factor and a missing factor are unchanged.
    """
    factor = request.questions.rain_stress_factor
    if factor is None:
        return StressedRun(engines, None)
    stress = rain_stress(factor)
    if isinstance(stress, RainStressMissing):
        return StressedRun(engines, stress)
    if not rain_stress_switched_on:
        return StressedRun(engines, _not_applied(stress, NOT_SWITCHED_ON))
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
    kinds_of_year_record: Mapping[str, Any] | None,
    engines_factory: EnginesFactory | None,
    parameters: dict[str, dict] | None,
    rain_stress_switched_on: bool,
    plant_layer: PlantLayer | None = None,
) -> APIRouter:
    """The plant route, bound to the given implementations.

    PROPOSED (S-032, decision R25): ``rain_stress_switched_on`` is required
    (no default; ``create_app`` holds the default, off). False means a declared rain-stress factor is echoed not applied with
    ``NOT_SWITCHED_ON``, and ``engines_factory`` is never called; true means
    the factor is applied as ``stressed_run`` describes.

    PROPOSED (S-031): ``kinds_of_year_record`` ``None`` means no record is
    configured (never "the committed one"). ``plant_layer`` ``None`` means
    ``DiscoveredPlantLayer``, which finds the plant layer by name on each
    request. A plant layer that is not built answers ``200`` with the
    not-built body (``api.plant_layer.not_built_body``) before the body is
    read and before any source or engine is called; one that fails to import
    or raises is ``500`` ``INTERNAL_ERROR``, on this route only.
    """
    router = APIRouter(prefix="/api")
    layer: PlantLayer = (
        plant_layer if plant_layer is not None else DiscoveredPlantLayer()
    )

    @router.post(ROUTE, responses={400: {}, 422: {}, 500: {}})
    def run_plant(body: dict[str, Any] = Body(...)):  # noqa: B008
        """Answer "What should I plant?" for one field and three to five rotations."""
        try:
            parts = layer.parts()
            if isinstance(parts, Missing):
                return JSONResponse(content=not_built_body(parts))
            if not isinstance(parts, PlantParts):
                raise TypeError("the plant layer gave neither PlantParts nor Missing")
            request, code, problems = request_problems(body, parts.request_model)
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
            run = stressed_run(
                request,
                engines,
                engines_factory,
                parameters,
                rain_stress_switched_on=rain_stress_switched_on,
            )
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
            record_years, why, reason = record_years_of(
                settings, request.rotations[0].ag_year_start.month
            )
            answer = parts.answer_plant(
                request,
                runs,
                record_years=record_years,
                why=why,
                reason=reason,
                record=kinds_of_year_record,
                rain_stress=run.echo,
                sources=sources,
                example_data=example_data,
            )
            if not isinstance(answer, parts.answer_model):
                raise TypeError(
                    "the plant layer returned another type than PlantAnswer"
                )
            # Never ``exclude_none``: a document written that way does not load back.
            return JSONResponse(content=answer.model_dump(mode="json"))
        except Exception:
            logger.exception("POST /api/plant/run failed")
            return error_response(ErrorCode.INTERNAL_ERROR)

    return router
