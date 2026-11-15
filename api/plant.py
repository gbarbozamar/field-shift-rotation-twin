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
from api.phases import ag_year_of
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
    applied_echo,
    not_applied_detail,
    rain_stress,
    scale_erosivity,
    scales_to_finite,
)
from api.rotation_validator import field_names, safe_message, submitted_texts
from api.rotations import PERIOD_NOT_CONFIGURED, get_climate, source_out
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
YEAR_NOT_OF_THE_RECORD = (
    "{why}, so the agricultural years of the record are not known; this is an "
    "agricultural year of the declared dates of the rotations, not a year of "
    "the record, and it is not classified"
)
NO_SOIL_LOSS = "the soil loss of this rotation is not available ({why})"
IGNORED_YEARS = (
    "agricultural year(s) {years} of the soil-loss result are not whole "
    "agricultural years of the record period and are ignored"
)
NO_YEAR_READ = (
    "the soil-loss result holds no whole agricultural year of the record period"
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


# --- years of the record and of the rotation ----------------------------------


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
            ag_year_of(day, start_month)
            for rotation in rotations
            for component in rotation.components
            for day in (component.sowing.date, component.harvest.date)
            if day is not None
        }
    )
    # Never empty: D21 of issue #77 (RotationDefinition) refuses a rotation
    # without any sowing or harvest date, so PlantRequest is 422 before this.
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


def cycle_years(rotation: RotationDefinition, crops: Mapping[str, Any]) -> CycleYears:
    """PROPOSED: the crop_ids of each agricultural year of one cycle.

    Read from the ``RotationDefinition``: each component counts in the
    agricultural year of its sowing date (by ``ag_year_start.month``), in
    position order, from the first such year to the last. PROPOSED (code
    review): a declared-margin crop of ``crops`` (its margin is per hectare
    and agricultural year, contracts/economic_facts) with a harvest date in a
    later agricultural year counts in each agricultural year from its sowing
    through its harvest, such as a pasture kept several years. A grain or
    cover crop counts only in the year of its sowing (its yield and cost are
    of one season; counting it twice would count them twice), and so does a
    declared-margin crop whose harvest date is missing (how long it is kept
    is not known). A missing sowing date (``MISSING_INPUT``), a year of the
    cycle with no crop, or a declared-margin crop sharing its year with
    another crop (both ``NOT_COMPUTABLE``: ``compute_rotation_margin`` takes
    neither) gives no years, with the reason.

    PROPOSED (S-029, review finding F1, and remark R2 of its review): a
    declared-margin crop kept past its sowing year counts from its sowing
    year up to its harvest year; the harvest year goes to the next component
    by position instead only when that component is sown in the harvest year
    on or after the harvest date. So a pasture that ends in year Y with the
    next crop sown later in Y gives Y to that crop. A next crop sown before
    the harvest date (in the harvest year or in an earlier year of the
    pasture) overlaps the pasture and is not moved: the two still share that
    year (``NOT_COMPUTABLE``), so the trimming never hides an overlap.

    OPEN (remark R1 of the S-029 review): the last component has no next
    component inside the definition, so it counts through its harvest year,
    even when the first component of the next cycle is sown in that year
    after the harvest date (the cycle is then one year longer than the
    calendar's cycle of point 3 of engine/calendar/repeat.py). Applying the
    rule above to the next cycle's first component changes the expected
    cycle of ``test_a_pasture_kept_several_years_counts_in_each_year_until_its_harvest``
    in api/test_plant.py, which a person decides;
    ``test_r1_the_last_pasture_gives_its_harvest_year_to_the_next_cycle``
    records the case (strict xfail).
    """
    month = rotation.ag_year_start.month
    ordered = sorted(rotation.components, key=lambda c: c.position)
    for component in ordered:
        if component.sowing.date is None:
            return CycleYears(
                None,
                "MISSING_INPUT",
                f"the sowing date of component {component.component_id!r} is "
                "missing, so the crops of each agricultural year are not known",
            )
    sowings = [c.sowing.date for c in ordered]
    followers: list[Any] = [*sowings[1:], None]
    by_year: dict[int, list[str]] = {}
    for component, sowing, follower in zip(ordered, sowings, followers, strict=True):
        first = last = ag_year_of(sowing, month)
        harvest = component.harvest.date
        if harvest is not None and isinstance(
            crops.get(component.crop_id), DeclaredMarginCrop
        ):
            last = ag_year_of(harvest, month)
            if (
                follower is not None
                and first < last == ag_year_of(follower, month)
                and follower >= harvest
            ):
                last -= 1
        for year in range(first, last + 1):
            by_year.setdefault(year, []).append(component.crop_id)
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


def _with_note(mean: KindMean, note: str) -> KindMean:
    detail = note if mean.detail is None else f"{mean.detail}; {note}"
    return dataclasses.replace(mean, detail=detail)


def soil_loss_means(
    run: EnginesResult, classified: Classified
) -> tuple[KindMean, dict[str, KindMean]]:
    """The soil loss on the record and in each kind of year, or missing.

    From the annual values of the phase-1 result. No result, or the soil-loss
    part not built, gives every mean missing with the engine's reason.

    PROPOSED (code review): only the agricultural years of the classified
    list are read, and only when they are years of the record. A year of the
    result outside them is ignored, and a note naming the ignored years is
    added to the detail of every mean. No year left (an empty annual list, or
    no year of the result in the list, as when the period holds no whole
    agricultural year) gives every mean missing ``NO_COVERAGE`` (C3.2: no data
    for this period), never a zero.
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
        annual = run.result.soil_loss.annual
        read = set(classified.kinds) if classified.of_record else set()
        kept = [item for item in annual if item.ag_year in read]
        ignored = sorted({item.ag_year for item in annual} - read)
        note = (
            None
            if not ignored
            else IGNORED_YEARS.format(years=", ".join(str(y) for y in ignored))
        )
        if kept:
            means = mean_by_kind(
                INDICATOR,
                UNIT_SOIL_LOSS_ANNUAL,
                series_from_results(kept),
                classified.kinds,
            )
            if note is None:
                return means.record, dict(means.by_kind)
            return _with_note(means.record, note), {
                kind: _with_note(mean, note) for kind, mean in means.by_kind.items()
            }
        reason = "NO_COVERAGE"
        detail = NO_YEAR_READ if note is None else f"{NO_YEAR_READ}; {note}"
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
    """As ``check_answer_against_request`` reads it: null when one is missing.

    Mirrors the rule "tipping_price.today is the declared soybean price, or
    null when it is missing" of ``check_answer_against_request``
    (contracts/plant_answer/plant_answer.py, PROPOSED fix round 2), which
    exposes no public helper for it. That rule also keeps only ``GrainCrop``
    items; ``PlantRequest`` already refuses a soybean crop_id that is not a
    grain crop, so the two read the same prices. Keep them in step: it also
    mirrors the private ``economics.tipping._todays_price``, and
    ``test_f6_todays_price_reads_as_economics_tipping_does`` in
    api/test_plant.py compares the two on the contract example (S-029, F6:
    neither economics/ nor the contract exposes a public helper).
    """
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
    years_missing: list[tuple[str, str]] = []  # (reason, rotation and detail)
    soil: list[tuple[KindMean, dict[str, KindMean]]] = []
    for definition, run in zip(request.rotations, runs, strict=True):
        if run.result is not None and run.result.rotation_id != definition.rotation_id:
            raise ValueError("the engines answered for another rotation")
        record_mean, by_kind = soil_loss_means(run, classified)
        soil.append((record_mean, by_kind))
        limits.append(
            assess_limit(
                request.soil_loss_limit,
                record_mean,
                by_kind,
                kinds_in_record=kinds_in_record,
            )
        )
        cycle = cycle_years(definition, crops)
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
            years_missing.append(
                (
                    cycle.reason,
                    f"{definition.rotation_id} ({cycle.reason}: {cycle.detail})",
                )
            )
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
        # PROPOSED: the reason of the first rotation without years, in the
        # order of the request; the detail names each such rotation with its
        # own reason.
        tipping = _shared_tipping(
            today,
            price_range,
            years_missing[0][0],
            "the margin of each agricultural year of a rotation is not known, so "
            "its margin at another soybean price is not computed: "
            + "; ".join(detail for _, detail in years_missing),
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
