"""Acceptance test of ``economics/plant.py`` (unit l2/plant-rules-to-economics,
brief S-030). PROPOSED.

The route cases stay in api/test_plant.py; these call ``economics.plant``
directly. No number is typed here: the request, the answer's years and its
source rows are read from the contract examples (example data), and the runs
carry no soil loss (a missing result with a PLACEHOLDER detail), or are the
contract results example; the rain-stress echo is the example answer's.
The tests import nothing of ``api`` but ``api.phases.ag_year_of``, the rule
``_ag_year_of`` is checked against; ``economics/plant.py`` may not import
``api`` at all.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from api.phases import ag_year_of
from contracts.economic_facts import KINDS_OF_YEAR, DeclaredMarginCrop
from contracts.plant_answer import (
    PlantAnswer,
    PlantRequest,
    check_answer_against_request,
)
from contracts.results.models import ResultsPerRotation
from economics import plant
from kinds_of_year import load_record

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "contracts" / "plant_answer" / "examples"
REQUEST = json.loads(
    (EXAMPLES / "PLACEHOLDER_plant_request.json").read_text(encoding="utf-8")
)
ANSWER = json.loads(
    (EXAMPLES / "PLACEHOLDER_plant_answer.json").read_text(encoding="utf-8")
)
WHY = "PLACEHOLDER: why the years of the record are not known in this test"
MISSING_DETAIL = "PLACEHOLDER: input not available: climate"
RESULTS_EXAMPLE = json.loads(
    (
        ROOT
        / "contracts"
        / "results"
        / "examples"
        / "PLACEHOLDER_results_per_rotation.json"
    ).read_text(encoding="utf-8")
)


@dataclasses.dataclass(frozen=True)
class _Missing:
    reason: str
    detail: str | None


@dataclasses.dataclass(frozen=True)
class _Run:
    """The smallest run: no result, with the reason (as NO_RESULT of
    api/test_plant.py)."""

    result: ResultsPerRotation | None
    result_missing: _Missing | None


NO_RESULT = _Run(None, _Missing("MISSING_INPUT", MISSING_DETAIL))


def _request() -> PlantRequest:
    return PlantRequest.model_validate_json(json.dumps(REQUEST))


def _record_years() -> tuple[int, int]:
    years = [item["ag_year"] for item in ANSWER["kinds_of_year"]["years"]]
    return min(years), max(years)


# --- a. no import of api, adapters or engine ------------------------------------


def test_the_module_imports_nothing_from_api_adapters_or_engine():
    tree = ast.parse((Path(__file__).parent / "plant.py").read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import is not checked by this scan"
            imported.append(node.module or "")
    assert imported
    forbidden = [
        name for name in imported if name.split(".")[0] in {"api", "adapters", "engine"}
    ]
    assert forbidden == []


# --- b. the agricultural year of a day ------------------------------------------


def test_ag_year_of_agrees_with_api_phases_on_every_day_of_two_years():
    """Every day of two calendar years covers both sides of each month
    boundary, and of the turn of the year, for every start month. The first
    year is the first agricultural year of the example answer."""
    first = dt.date(_record_years()[0], 1, 1)
    days = [first + dt.timedelta(days=n) for n in range(2 * 366)]
    assert days[-1].year > first.year + 1  # past the end of the second year
    for start_month in range(1, 13):
        for day in days:
            assert plant._ag_year_of(day, start_month) == ag_year_of(
                day, start_month
            ), (day, start_month)


# --- c. the answer on the contract example --------------------------------------


def test_assemble_answer_on_the_contract_example_passes_the_contract_check():
    request = _request()
    record = load_record()
    start_month = request.rotations[0].ag_year_start.month
    classified = plant.classify_years(
        record, _record_years(), WHY, start_month, request.rotations
    )
    assert classified.of_record
    # The echo of the example answer, unchanged (JSON-ready data).
    echo = ANSWER["rain_stress"]
    answer = plant.assemble_answer(
        request,
        [NO_RESULT for _ in request.rotations],
        classified=classified,
        record=record,
        rain_stress=echo,
        sources=ANSWER["sources"],
        example_data=True,
    )
    check_answer_against_request(request, answer)
    # Copied as given: it reads back as the example answer's echo does.
    example = PlantAnswer.model_validate_json(json.dumps(ANSWER))
    assert answer.rain_stress == example.rain_stress
    assert answer.kinds_of_year.source == record["id"]
    for option in answer.options:
        assert option.soil_loss.average.value is None
        assert MISSING_DETAIL in option.soil_loss.average.detail


def test_assemble_answer_averages_the_soil_loss_of_a_contract_results_example():
    """The averaging branch through ``assemble_answer``: every rotation's run
    is the contract results example, loaded unchanged except for its
    ``rotation_id`` (an identifier, set to the rotation it answers for), and
    the record years are the agricultural years of that example."""
    request = _request()
    record = load_record()
    start_month = request.rotations[0].ag_year_start.month
    example = ResultsPerRotation.model_validate(RESULTS_EXAMPLE)
    annual_years = [item.ag_year for item in example.soil_loss.annual]
    classified = plant.classify_years(
        record,
        (min(annual_years), max(annual_years)),
        WHY,
        start_month,
        request.rotations,
    )
    runs = [
        _Run(example.model_copy(update={"rotation_id": r.rotation_id}), None)
        for r in request.rotations
    ]
    answer = plant.assemble_answer(
        request,
        runs,
        classified=classified,
        record=record,
        rain_stress=ANSWER["rain_stress"],
        sources=ANSWER["sources"],
        example_data=True,
    )
    check_answer_against_request(request, answer)
    means = plant.soil_loss_means(runs[0], classified)
    for option in answer.options:
        assert option.soil_loss.average.model_dump(mode="json") == plant.plain(means[0])
    # mean_by_kind read at least one year of the example (the averaging
    # branch), not the missing-mean branch, whose ag_years are empty.
    assert means[0].ag_years


# --- d. years that are not years of the record ----------------------------------


def test_without_record_years_the_declared_years_are_listed_missing():
    request = _request()
    start_month = request.rotations[0].ag_year_start.month
    classified = plant.classify_years(
        load_record(), None, WHY, start_month, request.rotations
    )
    declared = {
        ag_year_of(day, start_month)
        for rotation in request.rotations
        for component in rotation.components
        for day in (component.sowing.date, component.harvest.date)
        if day is not None
    }
    assert classified.of_record is False
    assert list(classified.kinds) == sorted(declared)
    for kind in classified.kinds.values():
        assert kind.kind is None
        assert kind.missing_reason == "NOT_AVAILABLE"
        assert WHY in kind.detail


# --- e. cycle_years and soil_loss_means -----------------------------------------


def test_cycle_years_of_the_first_example_rotation():
    request = _request()
    rotation = request.rotations[0]
    crops = {crop.crop_id: crop for crop in request.economic_facts.crops}
    cycle = plant.cycle_years(rotation, crops)
    assert cycle.years is not None and cycle.reason is None
    # No declared-margin crop: each component counts in the agricultural year
    # of its sowing only, in position order, from the first year to the last.
    assert not any(
        isinstance(crops[c.crop_id], DeclaredMarginCrop) for c in rotation.components
    )
    month = rotation.ag_year_start.month
    ordered = sorted(rotation.components, key=lambda c: c.position)
    sown = [ag_year_of(c.sowing.date, month) for c in ordered]
    expected = [
        [c.crop_id for c, year in zip(ordered, sown, strict=True) if year == ag_year]
        for ag_year in range(min(sown), max(sown) + 1)
    ]
    assert cycle.years == expected


def test_soil_loss_means_of_a_run_without_result_are_missing_with_its_reason():
    record, by_kind = plant.soil_loss_means(NO_RESULT, plant.Classified({}, True))
    assert set(by_kind) == set(KINDS_OF_YEAR)
    for mean in (record, *by_kind.values()):
        assert mean.value is None
        assert mean.reason == "MISSING_INPUT"
        assert MISSING_DETAIL in mean.detail


# --- the seam refuses misuse (code review of S-030) ------------------------------


def test_a_run_with_neither_result_nor_result_missing_is_a_value_error():
    with pytest.raises(ValueError, match="neither a result nor result_missing"):
        plant.soil_loss_means(_Run(None, None), plant.Classified({}, True))


def test_classify_years_refuses_record_years_in_the_wrong_order():
    request = _request()
    first, last = _record_years()
    assert first < last
    with pytest.raises(ValueError, match="first agricultural year is after"):
        plant.classify_years(
            load_record(),
            (last, first),
            WHY,
            request.rotations[0].ag_year_start.month,
            request.rotations,
        )


def test_classify_years_records_its_start_month_and_positional_build_works():
    request = _request()
    month = request.rotations[0].ag_year_start.month
    classified = plant.classify_years(
        load_record(), _record_years(), WHY, month, request.rotations
    )
    assert classified.start_month == month
    assert plant.Classified({}, True).start_month is None


def test_assemble_answer_refuses_years_classified_with_another_start_month():
    request = _request()
    month = request.rotations[0].ag_year_start.month
    classified = plant.classify_years(
        load_record(), _record_years(), WHY, month, request.rotations
    )
    other = dataclasses.replace(classified, start_month=month % 12 + 1)
    with pytest.raises(ValueError, match="another start month"):
        plant.assemble_answer(
            request,
            [NO_RESULT for _ in request.rotations],
            classified=other,
            record=load_record(),
            rain_stress=ANSWER["rain_stress"],
            sources=ANSWER["sources"],
            example_data=True,
        )


# --- review of the whole 4 (brief S-034), PROPOSED test cases --------------------


def _example_run(annual_items: int | None = None) -> _Run:
    """The contract results example, its annual list cut to the first items."""
    example = ResultsPerRotation.model_validate(RESULTS_EXAMPLE)
    if annual_items is not None:
        soil = example.soil_loss.model_copy(
            update={"annual": example.soil_loss.annual[:annual_items]}
        )
        example = example.model_copy(update={"soil_loss": soil})
    return _Run(example, None)


def test_f1_a_record_year_the_annual_list_lacks_is_missing_not_dropped():
    """F1 (fix round 1): the record years are those of the example; the run
    lists only the first. The year it lacks enters the series as a missing
    value NO_COVERAGE, so the record mean and the mean of its kind are missing
    as for a listed year without a value; every other kind is unaffected."""
    from kinds_of_year import mean_by_kind, series_from_results

    request = _request()
    full = _example_run().result
    years = [item.ag_year for item in full.soil_loss.annual]
    classified = plant.classify_years(
        load_record(),
        (min(years), max(years)),
        WHY,
        request.rotations[0].ag_year_start.month,
        request.rotations,
    )
    run = _example_run(1)
    kept = run.result.soil_loss.annual
    absent = sorted(set(years) - {item.ag_year for item in kept})
    assert absent
    absent_kinds = {classified.kinds[year].kind for year in absent} - {None}
    # The case reaches a kind whose only year is absent.
    assert absent_kinds
    record, by_kind = plant.soil_loss_means(run, classified)
    # Missing as the same year listed without a value (the example lists the
    # absent year with no value): same value, reason and years.
    listed_record, listed_by_kind = plant.soil_loss_means(_example_run(), classified)
    named = f"{absent[0]} (NO_COVERAGE: {plant.ABSENT_YEAR})"
    for mean, listed in [
        (record, listed_record),
        *((by_kind[kind], listed_by_kind[kind]) for kind in absent_kinds),
    ]:
        assert mean.value is None
        assert (mean.reason, mean.ag_years) == (listed.reason, listed.ag_years)
        assert named in mean.detail
        assert "no agricultural year of the record is" not in mean.detail
    # A kind with no absent year is unaffected: as mean_by_kind over the
    # years present.
    present_only = mean_by_kind(
        plant.INDICATOR, record.unit, series_from_results(kept), classified.kinds
    )
    for kind in set(KINDS_OF_YEAR) - absent_kinds:
        assert by_kind[kind] == present_only.by_kind[kind]


def test_f8_classify_years_refuses_a_reason_with_record_years():
    request = _request()
    with pytest.raises(ValueError, match="a reason is given for record years"):
        plant.classify_years(
            load_record(),
            _record_years(),
            WHY,
            request.rotations[0].ag_year_start.month,
            request.rotations,
            reason="NOT_AVAILABLE",
        )


def test_f3_without_a_period_the_soil_loss_carries_the_reason_of_the_caller():
    """F3: years that are not years of the record for a named reason (as an
    absent period) give the soil-loss means that reason, not NO_COVERAGE."""
    request = _request()
    reason = "NOT_AVAILABLE"
    classified = plant.classify_years(
        load_record(),
        None,
        WHY,
        request.rotations[0].ag_year_start.month,
        request.rotations,
        reason=reason,
    )
    run = _example_run()
    record, by_kind = plant.soil_loss_means(run, classified)
    # Fix round 1: the note of the years of the result set aside is kept.
    set_aside = ", ".join(str(item.ag_year) for item in run.result.soil_loss.annual)
    for mean in (record, *by_kind.values()):
        assert mean.value is None
        assert mean.reason == reason
        assert WHY in mean.detail
        assert f"agricultural year(s) {set_aside} of the soil-loss result" in (
            mean.detail
        )


def test_f3_without_a_reason_the_years_off_the_record_stay_no_coverage():
    """F3: without a reason of the caller (a period without a whole year),
    the behaviour is the one before."""
    request = _request()
    classified = plant.classify_years(
        load_record(),
        None,
        WHY,
        request.rotations[0].ag_year_start.month,
        request.rotations,
    )
    assert classified.reason is None and classified.why is None
    record, _ = plant.soil_loss_means(_example_run(), classified)
    assert record.reason == "NO_COVERAGE"
