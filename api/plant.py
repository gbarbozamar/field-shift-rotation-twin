"""Route ``POST /api/plant/run``: "What should I plant?" for one field. PROPOSED.

Unit ``l2/plant-route`` (brief S-018; R4, R10, R13, R15 of the loop
decisions). One field, three to five rotations. The body is a
``PlantRequest`` and the answer a ``PlantAnswer`` (contracts/plant_answer/).

What it does, in order:

1. The body is loaded into ``PlantRequest``. A body that fails it is ``422``
   with the one error shape of ``api/errors.py``: ``ROTATION_INVALID`` when
   every problem lies inside one rotation item, ``SITE_INVALID`` when every
   problem lies inside ``site``, ``INVALID_REQUEST`` otherwise. Then each
   rotation goes through the ``RotationValidator``, as on the other routes.
   A message that repeats a submitted value is replaced by a fixed text.
   Nothing is called before that.
2. The climate and the soil and slope are asked for once, for the site, as
   ``POST /api/decisions/run`` asks for them.
3. Each rotation runs once through the ``RotationEngines`` (PROPOSED: phase 1,
   the top-level answer of the run, is enough for the answer). With a
   rain-stress factor, the engines are rebuilt on the catalogue whose
   erosivity is scaled (``api/rain_stress.py``), when the app has a way to
   rebuild them.
4. The soil loss per agricultural year of the phase-1 result
   (``kinds_of_year.series_from_results``) is averaged by kind of year
   (``mean_by_kind``); the kinds of year are the whole agricultural years of
   the configured period classified on the ONI record.
5. The pure functions of ``economics/`` give the margins, the limit checks,
   the decision and the tipping price.
6. The answer is checked with ``check_answer_against_request``; a failure is a
   defect of the route (``500``).

The route computes no number itself: every number of the answer comes from a
function of ``economics/`` or ``kinds_of_year/``, or is copied from an engine
result or from the request. What an engine raises is a defect: ``500``
``INTERNAL_ERROR``, as on the other routes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
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
    EnginesResult,
    ErrorDetail,
    RotationEngines,
    RotationValidator,
    RunSettings,
    SoilSlopeSource,
)
from api.rain_stress import (
    RainStress,
    RainStressMissing,
    _not_applied_detail,
    applied_echo,
    rain_stress,
    scale_erosivity,
)
from api.rotation_validator import _field_names, _submitted_texts
from api.rotations import PERIOD_NOT_CONFIGURED, _get_climate, _source_out
from contracts.economic_facts import KINDS_OF_YEAR, DeclaredMarginCrop
from contracts.plant_answer import (
    PlantAnswer,
    PlantRequest,
    check_answer_against_request,
)
from contracts.results.models import (
    UNIT_SOIL_LOSS_ANNUAL,
    SoilLossNotBuilt,
    SoilLossResults,
)
from contracts.rotation_definition import RotationDefinition
from economics.decide import RotationOption, choose_rotation
from economics.limit import assess_limit
from economics.margin import MarginResult, compute_rotation_margin
from economics.tipping import PriceRange, TippingOption, find_tipping_price
from kinds_of_year import (
    KindMean,
    KindOfYear,
    classify_agricultural_years,
    count_kinds,
    mean_by_kind,
    series_from_results,
)

logger = logging.getLogger(__name__)

ROUTE = "/plant/run"

# Builds the engines for a stressed run from a parameter catalogue. PROPOSED.
EnginesFactory = Callable[[dict[str, dict]], RotationEngines]

# PROPOSED: which erosivity the soil-loss run used (S-026 may add "per_year").
EROSIVITY = "mean_annual"

INDICATOR = "soil_loss"

# PROPOSED: the source row of the ONI record (contract, state; OPEN 5 of
# contracts/plant_answer/README.md: SourceOut has no state for a record read
# from the repository).
RECORD_CONTRACT = "kinds_of_year_record"
RECORD_STATE = "cached"

# Shown in place of an error text that repeats a submitted value (as
# api/rotation_validator.py does for one rotation). PROPOSED.
REDACTED_MESSAGE = "The value breaks a rule of the plant request contract."

# PROPOSED texts of absences the route writes.
NO_FACTORY = (
    "the engines were given to the app without a way to rebuild them on a "
    "parameter catalogue with the erosivity scaled"
)
NO_WHOLE_YEAR = (
    "the climate record period holds no whole agricultural year for the start "
    "month of the rotations"
)
YEAR_NOT_OF_THE_RECORD = (
    "{why}, so the agricultural years of the record are not known; this is an "
    "agricultural year of the declared dates of the rotations, not a year of "
    "the record, and it is not classified"
)
NO_SOIL_LOSS = "the soil loss of this rotation is not available ({why})"


# --- the request --------------------------------------------------------------


def _owner(loc: Sequence[Any], error_type: str) -> str:
    """Which part of the request an error lies in. PROPOSED, as api/errors.py."""
    if not loc:
        return "envelope"
    if loc[0] == "site" and (len(loc) > 1 or error_type != "missing"):
        return "site"
    # Inside one rotation item; a wrong number of rotations is the envelope's.
    if loc[0] == "rotations" and len(loc) > 1 and isinstance(loc[1], int):
        return "rotations"
    return "envelope"


def _code_of(errors: Sequence[Mapping[str, Any]]) -> ErrorCode:
    owners = {_owner(tuple(e.get("loc", ())), str(e.get("type", ""))) for e in errors}
    if owners == {"site"}:
        return ErrorCode.SITE_INVALID
    if owners == {"rotations"}:
        return ErrorCode.ROTATION_INVALID
    return ErrorCode.INVALID_REQUEST


def request_problems(
    body: Mapping[str, Any],
) -> tuple[PlantRequest | None, ErrorCode | None, list[ErrorDetail]]:
    """The body loaded into ``PlantRequest``, or the code and details of its errors.

    A message that repeats a submitted value (text of three characters or
    more, as ``api/rotation_validator.py`` looks for) is replaced by
    ``REDACTED_MESSAGE``; the path and the code still say where and what.
    """
    try:
        request = PlantRequest.model_validate_json(json.dumps(body))
    except ValidationError as error:
        errors = error.errors(
            include_url=False, include_context=False, include_input=False
        )
        submitted = _submitted_texts(body) - _field_names(PlantRequest)
        details = []
        for item in errors:
            message = str(item["msg"])
            if any(text in message.casefold() for text in submitted):
                message = REDACTED_MESSAGE
            details.append(
                ErrorDetail(
                    path=join_path(item["loc"]),
                    code=str(item["type"]),
                    message=message,
                )
            )
        return None, _code_of(errors), details
    return request, None, []


def _under_rotation(index: int, problem: ErrorDetail) -> ErrorDetail:
    parts: list[Any] = ["rotations", index]
    if problem.path:
        parts.append(problem.path)
    return ErrorDetail(
        path=join_path(parts), code=problem.code, message=problem.message
    )


# --- years of the record and of the rotation ----------------------------------


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - 1


@dataclasses.dataclass(frozen=True)
class Classified:
    """The kinds of year the answer uses. PROPOSED.

    ``kinds`` holds one ``KindOfYear`` per agricultural year, in order;
    ``of_record`` is false when the years are not years of the record (no
    period, or no whole year in it): they are then written unclassified and
    no count of years is known.
    """

    kinds: dict[int, KindOfYear]
    of_record: bool


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
    """
    years = None
    why = PERIOD_NOT_CONFIGURED
    if settings.has_period:
        assert settings.start_date is not None and settings.end_date is not None
        years = whole_ag_years(start_month, settings.start_date, settings.end_date)
        why = NO_WHOLE_YEAR
    if years is not None:
        first, last = years
        return Classified(
            classify_agricultural_years(record, first, last, start_month), True
        )
    declared = sorted(
        {
            _ag_year_of(day, start_month)
            for rotation in rotations
            for component in rotation.components
            for day in (component.sowing.date, component.harvest.date)
            if day is not None
        }
    )
    detail = YEAR_NOT_OF_THE_RECORD.format(why=why)
    return Classified(
        {
            year: KindOfYear(
                kind=None,
                missing_reason="NOT_AVAILABLE",
                detail=detail,
                season=None,
                season_year=None,
            )
            for year in declared
        },
        False,
    )


@dataclasses.dataclass(frozen=True)
class CycleYears:
    """The crops sown in each agricultural year of one cycle, or why not."""

    years: list[list[str]] | None
    reason: str | None = None
    detail: str | None = None


def cycle_years(rotation: RotationDefinition) -> CycleYears:
    """PROPOSED: the crop_ids sown in each agricultural year of one cycle.

    Read from the ``RotationDefinition``: each component counts in the
    agricultural year of its sowing date (by ``ag_year_start.month``), in
    position order, from the first such year to the last. A missing sowing
    date (``MISSING_INPUT``), a year of the cycle with no crop sown, or a
    declared-margin crop sharing its year with another crop (both
    ``NOT_COMPUTABLE``: ``compute_rotation_margin`` takes neither) gives no
    years, with the reason.
    """
    month = rotation.ag_year_start.month
    by_year: dict[int, list[str]] = {}
    for component in sorted(rotation.components, key=lambda c: c.position):
        day = component.sowing.date
        if day is None:
            return CycleYears(
                None,
                "MISSING_INPUT",
                f"the sowing date of component {component.component_id!r} is "
                "missing, so the crops of each agricultural year are not known",
            )
        by_year.setdefault(_ag_year_of(day, month), []).append(component.crop_id)
    first, last = min(by_year), max(by_year)
    empty = [year for year in range(first, last + 1) if year not in by_year]
    if empty:
        return CycleYears(
            None,
            "NOT_COMPUTABLE",
            f"{len(empty)} agricultural year(s) of the cycle have no crop sown, "
            "and a year without a crop has no declared economic fact",
        )
    return CycleYears([by_year[year] for year in range(first, last + 1)])


def _shares_a_declared_margin_year(years: list[list[str]], crops: Mapping) -> bool:
    return any(
        len(entry) > 1
        and any(isinstance(crops.get(crop_id), DeclaredMarginCrop) for crop_id in entry)
        for entry in years
    )


# --- soil loss by kind of year ------------------------------------------------


def _missing_mean(reason: str, detail: str) -> KindMean:
    # ``n_years`` is a count of years with a value (none), not a soil loss.
    return KindMean(
        value=None,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        n_years=0,
        ag_years=(),
        reason=reason,
        detail=detail,
    )


def _why(reason: str, detail: str | None) -> str:
    return reason if detail is None else f"{reason}: {detail}"


def soil_loss_means(
    run: EnginesResult, kinds: Mapping[int, KindOfYear]
) -> tuple[KindMean, dict[str, KindMean]]:
    """The soil loss on the record and in each kind of year, or missing.

    From the annual values of the phase-1 result. No result, or the soil-loss
    part not built, gives every mean missing with the engine's reason.
    """
    if run.result is None:
        missing = run.result_missing
        assert missing is not None
        reason, detail = missing.reason, missing.detail
    elif isinstance(run.result.soil_loss, SoilLossNotBuilt):
        reason = run.result.soil_loss.missing.reason
        detail = run.result.soil_loss.missing.detail
    else:
        assert isinstance(run.result.soil_loss, SoilLossResults)
        means = mean_by_kind(
            INDICATOR,
            UNIT_SOIL_LOSS_ANNUAL,
            series_from_results(run.result.soil_loss.annual),
            kinds,
        )
        return means.record, dict(means.by_kind)
    mean = _missing_mean(reason, NO_SOIL_LOSS.format(why=_why(reason, detail)))
    return mean, {kind: mean for kind in KINDS_OF_YEAR}


# --- the answer ---------------------------------------------------------------


def _plain(value: Any) -> Any:
    """A dataclass or model as JSON-ready data: tuples as lists, mappings as dicts."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _margin_out(margin: MarginResult) -> dict[str, Any]:
    return _plain(margin)


def _missing_margin(reason: str, detail: str) -> MarginResult:
    return MarginResult(value=None, reason=reason, detail=detail)


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


def _year_kind(ag_year: int, kind: KindOfYear) -> dict[str, Any]:
    return {"ag_year": ag_year, **_plain(kind)}


def _shared_tipping(
    today: float | None, price_range: Mapping[str, Any], reason: str, detail: str
) -> dict[str, Any]:
    point = {
        "price": None,
        "takes_over": None,
        "answer_after": None,
        "distance_percent": None,
        "reason": reason,
        "detail": detail,
        "unit": price_range["unit"],
    }
    return {
        "today": today,
        "unit": price_range["unit"],
        "price_range": dict(price_range),
        "up": {"direction": "up", **point},
        "down": {"direction": "down", **point},
        "reason": reason,
        "detail": detail,
    }


def _todays_price(request: PlantRequest) -> float | None:
    """As ``check_answer_against_request`` reads it: null when one is missing."""
    prices = [
        crop.price.value
        for crop in request.economic_facts.crops
        if crop.crop_id in request.questions.soybean_crop_ids
    ]
    return None if None in prices else prices[0]


@dataclasses.dataclass(frozen=True)
class StressedRun:
    engines: RotationEngines
    echo: RainStress | RainStressMissing | None


def stressed_run(
    request: PlantRequest,
    engines: RotationEngines,
    factory: EnginesFactory | None,
    catalogue: dict[str, dict],
) -> StressedRun:
    """The engines for this request and the rain-stress echo. PROPOSED (R10).

    No factor: the engines unchanged, no echo. A missing factor: the engines
    unchanged, the missing echo. A factor and a factory: the engines rebuilt on
    ``scale_erosivity(catalogue, stress)``, the echo of ``applied_echo``. A
    factor and no factory: the engines unchanged and the echo ``applied``
    false, with the reason in its detail; never a silent run.
    """
    factor = request.questions.rain_stress_factor
    if factor is None:
        return StressedRun(engines, None)
    stress = rain_stress(factor)
    if isinstance(stress, RainStressMissing):
        return StressedRun(engines, stress)
    if factory is None:
        return StressedRun(
            engines,
            dataclasses.replace(
                stress,
                applied=False,
                detail=_not_applied_detail(stress.factor, NO_FACTORY),
            ),
        )
    return StressedRun(
        factory(scale_erosivity(catalogue, stress)), applied_echo(catalogue, stress)
    )


def build_answer(
    request: PlantRequest,
    runs: Sequence[EnginesResult],
    classified: Classified,
    record: Mapping[str, Any],
    echo: RainStress | RainStressMissing | None,
    sources: list[dict[str, Any]],
    example_data: bool,
) -> PlantAnswer:
    """The answer, from the runs and the pure functions. Raises on a defect."""
    questions = request.questions
    facts = request.economic_facts
    crops = {crop.crop_id: crop for crop in facts.crops}
    start_month = request.rotations[0].ag_year_start.month
    kinds = classified.kinds

    # The counts of years of each kind, and the kinds with a year (R7, R13).
    if classified.of_record:
        counts = count_kinds(kinds)
        year_counts: Mapping[str, int | None] | None = counts
        if all(counts[kind] is not None for kind in KINDS_OF_YEAR):
            kinds_in_record: tuple[str, ...] | None = tuple(
                kind for kind in KINDS_OF_YEAR if counts[kind]
            )
        else:
            # A year without a kind: whether a kind is in the record is not
            # known, so every kind stays in the check (assess_limit's default).
            kinds_in_record = None
    else:
        counts = {kind: None for kind in KINDS_OF_YEAR}
        year_counts = None  # not classified: the average is NOT_AVAILABLE
        kinds_in_record = None

    margins: list[dict[str, MarginResult]] = []
    limits = []
    tipping_years: list[list[list[str]]] = []
    years_missing: list[str] = []
    soil: list[tuple[KindMean, dict[str, KindMean]]] = []
    for definition, run in zip(request.rotations, runs, strict=True):
        if run.result is not None and run.result.rotation_id != definition.rotation_id:
            raise ValueError("the engines answered for another rotation")
        record_mean, by_kind = soil_loss_means(run, kinds)
        soil.append((record_mean, by_kind))
        limits.append(
            assess_limit(
                request.soil_loss_limit,
                record_mean,
                by_kind,
                kinds_in_record=kinds_in_record,
            )
        )
        cycle = cycle_years(definition)
        if cycle.years is not None and _shares_a_declared_margin_year(
            cycle.years, crops
        ):
            cycle = CycleYears(
                None,
                "NOT_COMPUTABLE",
                "a declared-margin crop shares its agricultural year with another "
                "crop, and a declared margin covers the whole year",
            )
        if cycle.years is None:
            assert cycle.reason is not None and cycle.detail is not None
            missing = _missing_margin(cycle.reason, cycle.detail)
            margins.append(
                {"average": missing, **dict.fromkeys(KINDS_OF_YEAR, missing)}
            )
            years_missing.append(f"{definition.rotation_id} ({cycle.detail})")
            continue
        tipping_years.append(cycle.years)
        margin = compute_rotation_margin(cycle.years, facts, year_counts)
        margins.append({"average": margin.average, **dict(margin.by_kind)})

    margin_of = questions.margin_of
    decision = choose_rotation(
        (
            RotationOption(
                rotation_id=definition.rotation_id,
                margin=margin[margin_of],
                limit=limit,
            )
            for definition, margin, limit in zip(
                request.rotations, margins, limits, strict=True
            )
        ),
        questions.strictness,
    )

    price_range = questions.soybean_price_range.model_dump(mode="json")
    today = _todays_price(request)
    if years_missing:
        tipping = _shared_tipping(
            today,
            price_range,
            "MISSING_INPUT",
            "the crops of each agricultural year of a rotation are not known, so "
            "its margin at another soybean price is not computed: "
            + "; ".join(years_missing),
        )
    else:
        found = find_tipping_price(
            [
                TippingOption(
                    rotation_id=definition.rotation_id, years=years, limit=limit
                )
                for definition, years, limit in zip(
                    request.rotations, tipping_years, limits, strict=True
                )
            ],
            facts,
            year_counts,
            questions.soybean_crop_ids,
            PriceRange(low=price_range["low"], high=price_range["high"]),
            questions.strictness,
            margin_of,
        )
        # The decision at today's price is the answer itself (contract).
        tipping = {
            key: value for key, value in _plain(found).items() if key != "decision"
        }
        tipping["price_range"] = price_range

    states = {option.rotation_id: option for option in decision.options}
    options = []
    for definition, margin, limit, (record_mean, by_kind) in zip(
        request.rotations, margins, limits, soil, strict=True
    ):
        verdict = states[definition.rotation_id]
        options.append(
            {
                "rotation_id": definition.rotation_id,
                "state": verdict.state,
                "margin": {key: _margin_out(margin[key]) for key in margin},
                "soil_loss": {
                    "average": _plain(record_mean),
                    **{kind: _plain(by_kind[kind]) for kind in KINDS_OF_YEAR},
                },
                "limit": _plain(limit),
                "limit_check": _plain(verdict.limit_check),
            }
        )

    document = {
        "contract": "plant_answer",
        "example_data": example_data,
        "case_id": request.site.case_id,
        "field_id": request.site.field_id,
        "questions": questions.model_dump(mode="json"),
        "answer": decision.answer,
        "chosen": decision.chosen,
        "reason": decision.reason,
        "detail": decision.detail,
        "tied": list(decision.tied),
        "options": options,
        "limit_cost": _plain(decision.limit_cost),
        "tipping_price": tipping,
        "rain_stress": None if echo is None else _plain(echo),
        "erosivity": EROSIVITY,
        "kinds_of_year": {
            "source": record["id"],
            "start_month": start_month,
            "years": [_year_kind(year, kinds[year]) for year in sorted(kinds)],
            "counts": counts,
        },
        "sources": sources,
    }
    answer = PlantAnswer.model_validate_json(json.dumps(document))
    check_answer_against_request(request, answer)
    return answer


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
    parameters: dict[str, dict],
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
            problems = [
                _under_rotation(index, problem)
                for index, rotation in enumerate(rotations)
                for problem in rotation_validator.validate(rotation)
            ]
            if problems:
                return error_response(ErrorCode.ROTATION_INVALID, problems)

            climate_result = _get_climate(climate, request.site, settings)
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
                *(_source_out(info).model_dump(mode="json") for info in infos),
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
            answer = build_answer(
                request,
                runs,
                classified,
                kinds_of_year_record,
                run.echo,
                sources,
                example_data,
            )
            # Never ``exclude_none``: a document written that way does not load back.
            return JSONResponse(content=answer.model_dump(mode="json"))
        except Exception:
            logger.exception("POST /api/plant/run failed")
            return error_response(ErrorCode.INTERNAL_ERROR)

    return router
