"""Acceptance test of ``economics/plant.py`` (unit l2/plant-rules-to-economics,
brief S-030). PROPOSED.

The route cases stay in api/test_plant.py; these call ``economics.plant``
directly. No number is typed here: the request, the answer's years and its
source rows are read from the contract examples (example data), and the runs
carry no soil loss (a missing result with a PLACEHOLDER detail). A test may
import ``api`` (to compare with it, or to build the rain-stress echo as the
route does); ``economics/plant.py`` may not.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
from pathlib import Path

from api.phases import ag_year_of
from api.plant import stressed_run
from contracts.economic_facts import KINDS_OF_YEAR, DeclaredMarginCrop
from contracts.plant_answer import PlantRequest, check_answer_against_request
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
    # The echo of the example's factor as the route writes it with no way to
    # rebuild the engines (api.plant.stressed_run), as JSON-ready data.
    echo = stressed_run(request, None, None, None).echo
    assert echo is not None
    answer = plant.assemble_answer(
        request,
        [NO_RESULT for _ in request.rotations],
        classified=classified,
        record=record,
        rain_stress=plant.plain(echo),
        sources=ANSWER["sources"],
        example_data=True,
    )
    check_answer_against_request(request, answer)
    assert answer.rain_stress.model_dump(mode="json") == plant.plain(echo)
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
        rain_stress=plant.plain(stressed_run(request, None, None, None).echo),
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
