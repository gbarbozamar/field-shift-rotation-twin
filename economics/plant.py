"""The answer of "What should I plant?" from the engine runs. PROPOSED.

Unit ``l2/plant-rules-to-economics`` (brief S-030; point 2 of the platform
review of PR 310): the rules that decide which crops and years count in each
margin and mean live here, not in ``api/``. The route ``api/plant.py`` gathers
the request and the engine runs and hands them to ``answer_plant``, the one
entry function of this module, which the platform finds by name on each
request (S-031, ``api/plant_layer.py``): it calls ``classify_years`` and then
``assemble_answer``.

Steps 4 to 6 of ``api/plant.py`` happen here. ``classify_years`` classifies
the whole agricultural years of the record (computed by the caller) on the
ONI record, or lists the declared years unclassified when they are not known
(step 4). Then ``assemble_answer``, in order:

1. averages the soil loss per agricultural year of the phase-1 result
   (``kinds_of_year.series_from_results``) by kind of year (``mean_by_kind``),
   on the kinds of year of ``classify_years`` (step 4);
2. gives the margins, the limit checks, the decision and the tipping price
   through the pure functions of ``economics/`` (step 5);
3. checks the answer with ``check_answer_against_request``; a failure raises
   (a defect of the caller's inputs or of this module) (step 6).

No number is computed here that does not come from a function of
``economics/`` or ``kinds_of_year/``, or is copied from an engine result or
from the request. This module imports contracts, ``economics/`` and
``kinds_of_year/`` only, never ``api/``, ``adapters/`` or ``engine/``: a run is
any object with ``result`` and ``result_missing`` (``EngineRun``), which
``api.ports.EnginesResult`` satisfies without conversion.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from contracts.economic_facts import KINDS_OF_YEAR, DeclaredMarginCrop
from contracts.plant_answer import (
    PlantAnswer,
    PlantRequest,
    check_answer_against_request,
)
from contracts.results.models import (
    UNIT_SOIL_LOSS_ANNUAL,
    ResultsPerRotation,
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
    YearValue,
    classify_agricultural_years,
    count_kinds,
    mean_by_kind,
    series_from_results,
)

# PROPOSED: which erosivity the soil-loss run used (S-026 may add "per_year").
EROSIVITY = "mean_annual"

INDICATOR = "soil_loss"

# PROPOSED texts of absences this module writes.
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
# PROPOSED (S-034, F1): the detail of a year of the record that the soil-loss
# result does not list (its reason is NO_COVERAGE, C3.2: no data for this
# period). mean_by_kind writes the year itself before it.
ABSENT_YEAR = "the soil-loss result lists no value for this year of the record"


# --- what a run is ------------------------------------------------------------


class RunMissing(Protocol):
    """Why a run has no result: a reason code (C3.2) and its detail."""

    @property
    def reason(self) -> str: ...

    @property
    def detail(self) -> str | None: ...


class EngineRun(Protocol):
    """One rotation run through the engines, as this module reads it. PROPOSED.

    ``result`` is the phase-1 ``ResultsPerRotation``, or ``None`` with
    ``result_missing`` saying why. ``api.ports.EnginesResult`` is one.
    """

    @property
    def result(self) -> ResultsPerRotation | None: ...

    @property
    def result_missing(self) -> RunMissing | None: ...


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to. PROPOSED (S-030).

    contracts/CONVENTIONS.md, C5.3: "An agricultural year is twelve
    consecutive calendar months beginning at the start month of the case
    (C5.4)." and "An agricultural year is identified by the calendar year in
    which it begins, in a field named `ag_year`." So a day in or after the
    start month belongs to the agricultural year of its own calendar year, and
    a day before it to the one of the calendar year before. The same rule as
    ``api.phases.ag_year_of``, which this module may not import;
    economics/test_plant.py checks that the two agree.
    """
    return day.year if day.month >= start_month else day.year - 1


# --- years of the record and of the rotation ----------------------------------


@dataclasses.dataclass(frozen=True)
class Classified:
    """The kinds of year the answer uses. PROPOSED.

    ``kinds`` holds one ``KindOfYear`` per agricultural year, in order;
    ``of_record`` is false when the years are not years of the record (no
    period, or no whole year in it): they are then written unclassified and
    no count of years is known.

    PROPOSED (S-030, code review): ``start_month`` is the start month the
    years were classified with, or ``None`` when not known (a ``Classified``
    built by hand, positionally, with two fields). ``assemble_answer``
    refuses one that differs from the start month of the request.

    PROPOSED (S-034, F3): ``reason`` and ``why`` are, when the caller gave a
    reason code (C3.2) for why the years are not years of the record, that
    code and its text. ``soil_loss_means`` then gives every soil-loss mean
    missing with them, in place of ``NO_COVERAGE``. ``None``: no such reason
    (years of the record, or a period without a whole agricultural year).
    """

    kinds: dict[int, KindOfYear]
    of_record: bool
    start_month: int | None = None
    reason: str | None = None
    why: str | None = None


def classify_years(
    record: Mapping[str, Any],
    record_years: tuple[int, int] | None,
    why: str,
    start_month: int,
    rotations: Sequence[RotationDefinition],
    *,
    reason: str | None = None,
) -> Classified:
    """PROPOSED: the whole agricultural years of the record, ``record_years``
    (first and last, as the caller computed them), classified on the ONI
    record.

    ``record_years`` ``None`` means the record's years are not known, and
    ``why`` is the text that says why (the caller's, such as "no period" or
    "no whole agricultural year in the period"). PROPOSED (S-030): the caller
    computes the years from its settings; this module reads no settings.

    Without a period, or with a period that holds no whole agricultural year,
    the record's years are not known; the answer still lists years (the
    contract asks for at least one), the agricultural years of every declared
    date of the rotations, each missing ``NOT_AVAILABLE`` with a detail that
    says they are not years of the record.

    PROPOSED (S-030, code review): ``record_years`` whose first year is after
    its last is a ``ValueError``, a defect of the caller, not an absence.

    PROPOSED (S-034, F3): ``reason`` is the reason code (C3.2) of ``why``,
    when the caller has one (the route gives the one of an absent period);
    with ``record_years`` ``None`` it is kept in the ``Classified`` with
    ``why``, so the soil-loss means carry it. Given with ``record_years`` it
    is a ``ValueError`` (years of the record have no reason to be missing).
    """
    if record_years is not None:
        if reason is not None:
            raise ValueError(
                "classify_years: a reason is given for record years that are known"
            )
        first, last = record_years
        if first > last:
            raise ValueError(
                "record_years: the first agricultural year is after the last"
            )
        return Classified(
            classify_agricultural_years(record, first, last, start_month),
            True,
            start_month,
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
        start_month,
        reason,
        None if reason is None else why,
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
        first = last = _ag_year_of(sowing, month)
        harvest = component.harvest.date
        if harvest is not None and isinstance(
            crops.get(component.crop_id), DeclaredMarginCrop
        ):
            last = _ag_year_of(harvest, month)
            if (
                follower is not None
                and first < last == _ag_year_of(follower, month)
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


def _series_of_the_record(kept: Sequence[Any], read: set[int]) -> dict[int, YearValue]:
    """PROPOSED (S-034, F1): the series of the years of the result that are
    years of the record, plus every year of the record the result does not
    list, as a missing value ``NO_COVERAGE`` (C3.2: no data for this period)
    with ``ABSENT_YEAR`` as its detail. ``mean_by_kind`` then treats such a
    year as it treats a listed year without a value: the record mean, and
    the mean of the kind of that year, are missing and name it."""
    series = series_from_results(kept)
    for year in sorted(read - set(series)):
        series[year] = YearValue(None, "NO_COVERAGE", ABSENT_YEAR)
    return series


def soil_loss_means(
    run: EngineRun, classified: Classified
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

    PROPOSED (S-034, F1): a year of the record the annual list lacks enters
    the series as a missing value ``NO_COVERAGE`` (``_series_of_the_record``),
    so the record mean and the mean of its kind are missing and name it, as
    for a listed year without a value; a kind without such a year is
    unaffected. PROPOSED (S-034, F3): years that are not years of the record
    for a reason of the caller (``Classified.reason``, as for an absent
    period) give every mean missing with that reason and its text, plus the
    note naming the years of the result set aside.

    PROPOSED (S-030, code review): a run with neither a result nor
    ``result_missing``, or a soil loss of another type, is a ``ValueError``
    naming the problem (the route answers ``500``, as before).
    """
    if run.result is None:
        missing = run.result_missing
        if missing is None:
            raise ValueError("a run has neither a result nor result_missing")
        reason, detail = missing.reason, missing.detail
    elif isinstance(run.result.soil_loss, SoilLossNotBuilt):
        reason = run.result.soil_loss.missing.reason
        detail = run.result.soil_loss.missing.detail
    elif not isinstance(run.result.soil_loss, SoilLossResults):
        raise ValueError(
            "the soil_loss of a result is neither SoilLossResults nor SoilLossNotBuilt"
        )
    else:
        annual = run.result.soil_loss.annual
        read = set(classified.kinds) if classified.of_record else set()
        kept = [item for item in annual if item.ag_year in read]
        ignored = sorted({item.ag_year for item in annual} - read)
        note = (
            None
            if not ignored
            else IGNORED_YEARS.format(years=", ".join(str(y) for y in ignored))
        )
        if not classified.of_record and classified.reason is not None:
            # PROPOSED (S-034, F3): the years are not years of the record for
            # a reason the caller named (no period): that reason, not
            # NO_COVERAGE, with the note of the years set aside.
            reason = classified.reason
            parts = [text for text in (classified.why, note) if text is not None]
            detail = "; ".join(parts) if parts else None
        elif kept:
            means = mean_by_kind(
                INDICATOR,
                UNIT_SOIL_LOSS_ANNUAL,
                _series_of_the_record(kept, read),
                classified.kinds,
            )
            if note is None:
                return means.record, dict(means.by_kind)
            return _with_note(means.record, note), {
                kind: _with_note(mean, note) for kind, mean in means.by_kind.items()
            }
        else:
            reason = "NO_COVERAGE"
            detail = NO_YEAR_READ if note is None else f"{NO_YEAR_READ}; {note}"
    mean = _missing_mean(reason, NO_SOIL_LOSS.format(why=_why(reason, detail)))
    return mean, {kind: mean for kind in KINDS_OF_YEAR}


# --- the answer ---------------------------------------------------------------


def plain(value: Any) -> Any:
    """A dataclass or model as JSON-ready data: tuples as lists, mappings as dicts."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def _missing_margin(reason: str, detail: str) -> MarginResult:
    return MarginResult(value=None, reason=reason, detail=detail)


def _year_kind(ag_year: int, kind: KindOfYear) -> dict[str, Any]:
    return {"ag_year": ag_year, **plain(kind)}


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


def assemble_answer(
    request: PlantRequest,
    runs: Sequence[EngineRun],
    *,
    classified: Classified,
    record: Mapping[str, Any] | None,
    rain_stress: Mapping[str, Any] | None,
    sources: list[dict[str, Any]],
    example_data: bool,
) -> PlantAnswer:
    """The answer, from the runs and the pure functions. Raises on a defect.

    ``runs`` holds one run per rotation of the request, in its order.
    ``record`` is the ONI record ``classified`` was read on (its ``id`` names
    the source of the kinds of year). PROPOSED (S-031): ``None`` when no
    record is configured; the source of the kinds of year is then null, which
    the contract allows only when every year is missing. ``rain_stress`` is the rain-stress echo
    already as JSON-ready data, or ``None`` when no factor was asked; it is
    copied into the answer unchanged. ``sources`` are the source rows of the
    answer, as JSON-ready data, copied unchanged. A ``classified`` whose
    ``start_month`` is set and differs from the request's is a ``ValueError``.
    """
    questions = request.questions
    facts = request.economic_facts
    crops = {crop.crop_id: crop for crop in facts.crops}
    start_month = request.rotations[0].ag_year_start.month
    if classified.start_month is not None and classified.start_month != start_month:
        raise ValueError(
            "classified: the years were classified with another start month "
            "than the one of the request"
        )
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
            if cycle.reason is None or cycle.detail is None:
                raise ValueError("a cycle without years carries no reason")
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
            key: value for key, value in plain(found).items() if key != "decision"
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
                "margin": {key: plain(margin[key]) for key in margin},
                "soil_loss": {
                    "average": plain(record_mean),
                    **{kind: plain(by_kind[kind]) for kind in KINDS_OF_YEAR},
                },
                "limit": plain(limit),
                "limit_check": plain(verdict.limit_check),
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
        "limit_cost": plain(decision.limit_cost),
        "tipping_price": tipping,
        "rain_stress": rain_stress,
        "erosivity": EROSIVITY,
        "kinds_of_year": {
            "source": None if record is None else record["id"],
            "start_month": start_month,
            "years": [_year_kind(year, kinds[year]) for year in sorted(kinds)],
            "counts": counts,
        },
        "sources": sources,
    }
    answer = PlantAnswer.model_validate_json(json.dumps(document))
    check_answer_against_request(request, answer)
    return answer


# --- the entry function -------------------------------------------------------


def _missing_kind(detail: str) -> KindOfYear:
    return KindOfYear(
        kind=None,
        missing_reason="NOT_AVAILABLE",
        detail=detail,
        season=None,
        season_year=None,
    )


def _without_record(
    record_years: tuple[int, int] | None,
    why: str,
    reason: str | None,
    start_month: int,
    rotations: Sequence[RotationDefinition],
    record_missing: str,
) -> Classified:
    """The kinds of year when no record is configured. PROPOSED (S-031).

    Known years (the whole agricultural years of the record period) are still
    years of the record period (``of_record`` true), each missing
    ``NOT_AVAILABLE`` with ``record_missing``: the soil-loss mean of the
    period is kept and each kind of year is missing, through
    ``mean_by_kind`` and ``count_kinds`` as for any year without a kind.
    Unknown years are the declared years of ``classify_years`` (which reads
    no record on that path), with ``record_missing`` first in each detail.
    """
    if record_years is not None:
        if reason is not None:
            raise ValueError(
                "answer_plant: a reason is given for record years that are known"
            )
        first, last = record_years
        if first > last:
            raise ValueError(
                "record_years: the first agricultural year is after the last"
            )
        kinds = {year: _missing_kind(record_missing) for year in range(first, last + 1)}
        return Classified(kinds, True, start_month)
    declared = classify_years({}, None, why, start_month, rotations, reason=reason)
    kinds = {
        year: _missing_kind(
            record_missing
            if kind.detail is None
            else f"{record_missing}; {kind.detail}"
        )
        for year, kind in declared.kinds.items()
    }
    return dataclasses.replace(declared, kinds=kinds)


def answer_plant(
    request: PlantRequest,
    runs: Sequence[EngineRun],
    *,
    record_years: tuple[int, int] | None,
    why: str,
    reason: str | None,
    record: Mapping[str, Any] | None,
    record_missing: str | None,
    rain_stress: Any,
    sources: list[dict[str, Any]],
    example_data: bool,
) -> PlantAnswer:
    """The answer to "What should I plant?". PROPOSED (S-031, decision R24).

    The one entry function the platform finds by name
    (``api/plant_layer.py``). It does what the route did after the engines
    ran: ``classify_years`` on the given years, then ``assemble_answer``.

    ``record_years``, ``why`` and ``reason`` are what ``classify_years``
    takes: the whole agricultural years of the record period (first and
    last), or ``None`` with the text of why they are not known and its reason
    code (or ``None``). ``record`` is the ONI record, or ``None`` when no
    record is configured; ``record_missing`` is then the sentence that says
    so (given exactly when there is no record, ``ValueError`` otherwise), and
    the kinds of year are those of ``_without_record``. ``rain_stress`` is the
    rain-stress echo (a dataclass, a mapping or ``None``), written into the
    answer through ``plain``; ``sources`` and ``example_data`` are copied.
    """
    if (record is None) != (record_missing is not None):
        raise ValueError(
            "answer_plant: record_missing is given exactly when there is no record"
        )
    start_month = request.rotations[0].ag_year_start.month
    if record is not None:
        classified = classify_years(
            record, record_years, why, start_month, request.rotations, reason=reason
        )
    else:
        assert record_missing is not None
        classified = _without_record(
            record_years, why, reason, start_month, request.rotations, record_missing
        )
    return assemble_answer(
        request,
        runs,
        classified=classified,
        record=record,
        rain_stress=plain(rain_stress),
        sources=sources,
        example_data=example_data,
    )
