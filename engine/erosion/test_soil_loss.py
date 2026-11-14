"""Acceptance test of units l0/erosion-entrypoint (issue #115) and
l0/erosion-ep1-parameters (issue #154).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``SOIL_LOSS.md`` under "PROPOSED cases"; a test checks that the two lists
agree. The identifier of a case is the name of its test function without
``test_``, with hyphens.

Every input is built from the PLACEHOLDER examples of
``contracts/inputs/examples/``, loaded and then changed in memory. The daily
values of a longer "precipitation" series repeat the items of the example
series in order. Expected agricultural years are computed from the dates of
the series, day by day, independently of the module under test.

Test catalogues: every record is built here in the record format of
``params/README.md`` and carries the word PLACEHOLDER in its citation, its
persons and its reasons. ``params.catalogue`` refuses a record with that word,
so, as ``params/test_layout.py`` does, the catalogue passed to the entry point
is an in-memory copy in which the word is replaced by ``UNMARKED_TEST_ONLY``;
that copy passes ``check_catalogue``. Its numbers are positions in a list, not
values of the method: ``placeholder_values`` says how they are made.

Run from the repository root: ``py -3.12 -m pytest engine/erosion/test_soil_loss.py``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    ReasonCode,
    SoilLossResults,
)
from engine.erosion import equation, ls
from engine.erosion import soil_loss as module
from params.catalogue import check_catalogue

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
INDICATOR = "soil_loss"
PRECIPITATION = "precipitation"  # decision D23 of issue #77
ONE_DAY = dt.timedelta(days=1)
WORD = "PLACEHOLDER"
EMPTY_SCOPE = "scope {}"


# --- inputs built from the examples ------------------------------------------


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"PLACEHOLDER_{name}.json").read_text("utf-8"))


def calendar_document() -> dict[str, Any]:
    return load("rotation_calendar")


def climate_document() -> dict[str, Any]:
    return load("site_climate")


def soil_document() -> dict[str, Any]:
    return load("site_soil_slope")


def start_month() -> int:
    return calendar_document()["ag_year_start"]["month"]


def example_precipitation() -> dict[str, Any]:
    (series,) = [
        item
        for item in climate_document()["daily_series"]
        if item["quantity"] == PRECIPITATION
    ]
    return series


def example_start() -> dt.date:
    return dt.date.fromisoformat(example_precipitation()["start_date"])


def precipitation_series(first: dt.date, last: dt.date) -> dict[str, Any]:
    """The example series stretched from ``first`` to ``last``.

    Each day takes, in turn, the value or missing part of the example days.
    """
    series = copy.deepcopy(example_precipitation())
    items = series["days"]
    days = []
    day = first
    position = 0
    while day <= last:
        item = {k: v for k, v in items[position % len(items)].items() if k != "date"}
        days.append({"date": day.isoformat(), **item})
        day += ONE_DAY
        position += 1
    series.update(start_date=first.isoformat(), end_date=last.isoformat(), days=days)
    return series


def climate_with(series: dict[str, Any] | None) -> SiteClimate:
    document = climate_document()
    others = [
        item for item in document["daily_series"] if item["quantity"] != PRECIPITATION
    ]
    document["daily_series"] = others + ([series] if series is not None else [])
    return SiteClimate.model_validate(document)


def first_day_of(ag_year: int) -> dt.date:
    return dt.date(ag_year, start_month(), 1)


def last_day_of(ag_year: int) -> dt.date:
    return first_day_of(ag_year + 1) - ONE_DAY


# Three spans of the record, all from the dates of the example series.
def several_full_years() -> tuple[dt.date, dt.date]:
    """From the first day of the agricultural year that begins in the calendar
    year of the example's first day, to the last day of the agricultural year
    two later."""
    first_ag_year = example_start().year
    return first_day_of(first_ag_year), last_day_of(first_ag_year + 2)


def partial_years() -> tuple[dt.date, dt.date]:
    """From the first day of the example series to the last day of the first
    month of the agricultural year after ``several_full_years``: the first and
    the last years are not covered whole."""
    _, last = several_full_years()
    following = last + ONE_DAY
    return example_start(), month_bounds(following.year, following.month)[1]


def calendar() -> RotationCalendar:
    return RotationCalendar.model_validate(calendar_document())


def soil() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(soil_document())


def climate(span: tuple[dt.date, dt.date] | None = None) -> SiteClimate:
    return climate_with(precipitation_series(*(span or several_full_years())))


def run(
    calendar_: RotationCalendar | None = None,
    climate_: SiteClimate | None = None,
    soil_: SiteSoilSlope | None = None,
    parameters: dict[str, dict] | None = None,
) -> SoilLossResults | Missing:
    return module.compute_soil_loss(
        calendar=calendar_ if calendar_ is not None else calendar(),
        climate=climate_ if climate_ is not None else climate(),
        soil_slope=soil_ if soil_ is not None else soil(),
        parameters=parameters if parameters is not None else {},
    )


def expected_ag_years(first: dt.date, last: dt.date) -> list[int]:
    """Every agricultural year with at least one day in the span, day by day."""
    month = start_month()
    years = set()
    day = first
    while day <= last:
        years.add(day.year if day.month >= month else day.year - 1)
        day += ONE_DAY
    return sorted(years)


def is_covered(first: dt.date, last: dt.date, span: tuple[dt.date, dt.date]) -> bool:
    return span[0] <= first and last <= span[1]


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    return first, following - ONE_DAY


def infeasible_calendar() -> RotationCalendar:
    document = calendar_document()
    document["feasibility"] = {
        "feasible": False,
        "violations": [{"rule": "PLACEHOLDER-rule", "component_ids": []}],
    }
    return RotationCalendar.model_validate(document)


def calendar_without_start_month() -> RotationCalendar:
    document = calendar_document()
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: not declared"},
    }
    return RotationCalendar.model_validate(document)


def shift_years(text: str, years: int) -> str:
    day = dt.date.fromisoformat(text)
    return day.replace(year=day.year + years).isoformat()


def calendar_outside_the_record() -> RotationCalendar:
    """The example calendar moved past the last day of the record."""
    document = calendar_document()
    _, last = several_full_years()
    years = last.year - dt.date.fromisoformat(document["start_date"]).year + 1
    document["start_date"] = shift_years(document["start_date"], years)
    document["end_date"] = shift_years(document["end_date"], years)
    for component in document["components"]:
        for edge in ("start", "end"):
            component[edge]["date"] = shift_years(component[edge]["date"], years)
        for period in component["periods"]:
            for edge in ("start", "end"):
                period[edge]["date"] = shift_years(period[edge]["date"], years)
    built = RotationCalendar.model_validate(document)
    assert built.start_date > last
    return built


def soil_with_missing(*names: str, document: dict | None = None) -> SiteSoilSlope:
    document = copy.deepcopy(document) if document is not None else soil_document()
    for name in names:
        document[name] = {
            "value": None,
            "unit": document[name]["unit"],
            "missing": {
                "reason": "NO_COVERAGE",
                "detail": f"PLACEHOLDER: {name} not available for this place",
            },
        }
    return SiteSoilSlope.model_validate(document)


def values(result: SoilLossResults) -> list[AnnualSoilLoss | MonthlySoilLoss]:
    return [*result.annual, *result.monthly]


# --- test catalogues ----------------------------------------------------------


def unmarked(item: Any) -> Any:
    """An in-memory copy with the word PLACEHOLDER replaced (params/test_layout.py)."""
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {unmarked(key): unmarked(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmarked(value) for value in item]
    return item


PERCENT = ls.SlopeUnit.PERCENT
LENGTH_UNIT = "PLACEHOLDER_length_unit"


def placeholder_values() -> dict[str, float]:
    """One PLACEHOLDER number per parameter: its position in the list of
    identifiers, plus two, so that none is zero or one. Not values of the
    method."""
    return {
        pid: float(position + 2) for position, pid in enumerate(module.PARAMETER_IDS)
    }


def unit_of(pid: str) -> str:
    """The unit string a test record carries: the accepted one for R, K, C and
    P; a slope unit for the break slope; the length unit of the slope length
    for the unit length; a PLACEHOLDER unit for every other coefficient."""
    accepted = module.ACCEPTED_UNITS
    return {
        module.R_ID: accepted.r,
        module.K_ID: accepted.k,
        module.C_ID: accepted.c,
        module.P_ID: accepted.p,
        module.S_BREAK_ID: PERCENT.value,
        module.LAMBDA_UNIT_ID: LENGTH_UNIT,
    }.get(pid, "PLACEHOLDER_unit")


def placeholder_record(pid: str, value: float) -> dict[str, Any]:
    return {
        "id": pid,
        "scope": {},
        "value": value,
        "unit": unit_of(pid),
        "range": None,
        "range_missing_reason": "PLACEHOLDER: this test record has no range",
        "citation": {
            "reference": "PLACEHOLDER reference. This is not a publication.",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
    }


def marked_catalogue(*leave_out: str) -> dict[str, dict]:
    """Every record EP1 reads, keyed by a file path, still marked PLACEHOLDER."""
    return {
        f"{pid}.json": placeholder_record(pid, value)
        for pid, value in placeholder_values().items()
        if pid not in leave_out
    }


def catalogue(*leave_out: str) -> dict[str, dict]:
    """The unmarked copy, which passes ``check_catalogue``."""
    built = unmarked(marked_catalogue(*leave_out))
    assert check_catalogue(built) == []
    return built


def computable_soil_document() -> dict[str, Any]:
    """The example soil data with a slope in percent and a slope length in
    the unit of the unit-length record."""
    document = soil_document()
    document["slope_steepness"]["unit"] = PERCENT.value
    document["slope_length"]["unit"] = unmarked(LENGTH_UNIT)
    return document


def computable_soil() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(computable_soil_document())


def expected_ls(numbers: dict[str, float]) -> float:
    slope = computable_soil()
    steepness = ls.slope_steepness_factor(
        slope_steepness=slope.slope_steepness.value,
        slope_unit=PERCENT,
        s_break=numbers[module.S_BREAK_ID],
        s_break_unit=PERCENT,
        **{name: numbers[pid] for name, pid in module.S_COEFFICIENTS.items()},
    )
    length = ls.slope_length_factor(
        slope_length=slope.slope_length.value,
        slope_length_unit=slope.slope_length.unit,
        lambda_unit=numbers[module.LAMBDA_UNIT_ID],
        lambda_unit_unit=unmarked(LENGTH_UNIT),
        slope_steepness=slope.slope_steepness.value,
        slope_unit=PERCENT,
        **{name: numbers[pid] for name, pid in module.L_COEFFICIENTS.items()},
    )
    assert isinstance(steepness, float) and isinstance(length, float)
    return length * steepness


def expected_product(numbers: dict[str, float] | None = None) -> float:
    numbers = placeholder_values() if numbers is None else numbers
    accepted = module.ACCEPTED_UNITS
    product = equation.annual_soil_loss(
        r=equation.Factor(numbers[module.R_ID], accepted.r),
        k=equation.Factor(numbers[module.K_ID], accepted.k),
        ls=equation.Factor(expected_ls(numbers), accepted.ls),
        c=equation.Factor(numbers[module.C_ID], accepted.c),
        p=equation.Factor(numbers[module.P_ID], accepted.p),
        accepted_units=accepted,
        unit_guard_reason=module.UNIT_NOT_ACCEPTED,
    )
    assert isinstance(product, float)
    return product


def run_computable(
    parameters: dict[str, dict] | None = None, **arguments: Any
) -> SoilLossResults:
    arguments.setdefault("soil_", computable_soil())
    result = run(
        parameters=catalogue() if parameters is None else parameters, **arguments
    )
    assert isinstance(result, SoilLossResults)
    return result


def named(pid: str) -> str:
    return f"parameter '{pid}' with {EMPTY_SCOPE}"


# --- cases of #125, kept ------------------------------------------------------


def test_examples_with_several_agricultural_years_load_into_soil_loss_results():
    span = several_full_years()
    cal = calendar()
    result = run(cal, climate(span))
    assert isinstance(result, SoilLossResults)

    ag_years = expected_ag_years(*span)
    assert len(ag_years) > 1
    assert [item.ag_year for item in result.annual] == ag_years
    for ag_year in ag_years:
        months = [item for item in result.monthly if item.ag_year == ag_year]
        assert len(months) == 12
        first = months[0]
        assert (first.year, first.month) == (ag_year, cal.ag_year_start.month)
        positions = [item.year * 12 + item.month for item in months]
        assert positions == list(range(positions[0], positions[0] + 12))

    for item in values(result):
        assert item.indicator == INDICATOR
        assert item.direction == DIRECTION_OF[INDICATOR]
    assert {item.unit for item in result.annual} == {UNIT_SOIL_LOSS_ANNUAL}
    assert {item.unit for item in result.monthly} == {UNIT_SOIL_LOSS_MONTHLY}

    dumped = result.model_dump(mode="json")
    assert SoilLossResults.model_validate_json(json.dumps(dumped)) == result


def test_start_month_missing_returns_one_missing_input():
    result = run(calendar_without_start_month())
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert "start month" in result.detail


def test_infeasible_calendar_makes_every_value_not_computable():
    for parameters, soil_ in (({}, soil()), (catalogue(), computable_soil())):
        result = run(infeasible_calendar(), climate(partial_years()), soil_, parameters)
        assert isinstance(result, SoilLossResults)
        assert {item.missing.reason for item in values(result)} == {"NOT_COMPUTABLE"}
        assert all("infeasible" in item.missing.detail for item in values(result))


def test_year_or_month_not_covered_by_precipitation_is_no_coverage():
    span = partial_years()
    result = run(climate_=climate(span))
    assert isinstance(result, SoilLossResults)
    assert [item.ag_year for item in result.annual] == expected_ag_years(*span)

    reasons = set()
    for item in result.annual:
        covered = is_covered(
            first_day_of(item.ag_year), last_day_of(item.ag_year), span
        )
        expected = "MISSING_INPUT" if covered else "NO_COVERAGE"
        assert item.missing.reason == expected, item.ag_year
        reasons.add(expected)
    assert reasons == {"MISSING_INPUT", "NO_COVERAGE"}

    month_reasons = set()
    for item in result.monthly:
        covered = is_covered(*month_bounds(item.year, item.month), span)
        expected = "NOT_AVAILABLE" if covered else "NO_COVERAGE"
        assert item.missing.reason == expected, (item.year, item.month)
        month_reasons.add(expected)
        if not covered:
            assert PRECIPITATION in item.missing.detail
    assert month_reasons == {"NOT_AVAILABLE", "NO_COVERAGE"}
    # A year that is not covered whole still has months that are covered.
    first_year = result.annual[0].ag_year
    assert {
        item.missing.reason for item in result.monthly if item.ag_year == first_year
    } == {"NOT_AVAILABLE", "NO_COVERAGE"}


def test_series_one_day_short_at_each_end_leaves_first_and_last_not_covered():
    full_first, full_last = several_full_years()
    span = (full_first + ONE_DAY, full_last - ONE_DAY)
    result = run(climate_=climate(span))
    assert isinstance(result, SoilLossResults)
    ag_years = expected_ag_years(*span)
    assert [item.ag_year for item in result.annual] == ag_years

    reasons = {item.ag_year: item.missing.reason for item in result.annual}
    assert reasons[ag_years[0]] == "NO_COVERAGE"
    assert reasons[ag_years[-1]] == "NO_COVERAGE"
    for ag_year in ag_years[1:-1]:
        assert reasons[ag_year] == "MISSING_INPUT", ag_year

    months = result.monthly
    assert months[0].missing.reason == "NO_COVERAGE"
    assert months[-1].missing.reason == "NO_COVERAGE"
    for item in months[1:-1]:
        assert item.missing.reason == "NOT_AVAILABLE", (item.year, item.month)


def test_calendar_dates_outside_the_record_keep_the_years_of_the_record():
    span = several_full_years()
    moved = run(calendar_outside_the_record(), climate(span))
    assert isinstance(moved, SoilLossResults)
    assert [item.ag_year for item in moved.annual] == expected_ag_years(*span)
    assert moved == run(calendar(), climate(span))


def test_no_precipitation_series_returns_one_missing_input():
    result = run(climate_=climate_with(None))
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT"
    assert PRECIPITATION in result.detail


@pytest.mark.parametrize(
    "names",
    [("slope_steepness",), ("slope_length",), ("slope_steepness", "slope_length")],
)
def test_missing_slope_input_is_named_in_the_ls_factor(names):
    soil_ = soil_with_missing(*names, document=computable_soil_document())
    result = run_computable(soil_=soil_)
    for item in result.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert "factor 'ls' is missing" in detail
        for name in names:
            assert (
                f"{name} is missing in the soil-and-slope data, reason NO_COVERAGE"
                in (detail)
            )
        for name in {"slope_steepness", "slope_length"} - set(names):
            assert f"{name} is missing" not in detail
        for factor in ("r", "k", "c", "p"):
            assert f"factor '{factor}'" not in detail


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_arguments_of_another_case_or_field_raise_value_error(argument, field):
    arguments = {
        "calendar": calendar(),
        "climate": climate(),
        "soil_slope": soil(),
        "parameters": {},
    }
    arguments[argument] = arguments[argument].model_copy(
        update={field: "PLACEHOLDER-other"}
    )
    with pytest.raises(ValueError, match=field):
        module.compute_soil_loss(**arguments)


@pytest.mark.parametrize("argument", ["calendar", "climate", "soil_slope"])
def test_argument_that_is_not_its_model_raises_type_error(argument):
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    wrong = {"calendar": soil(), "climate": calendar(), "soil_slope": climate()}
    for replacement in (arguments[argument].model_dump(mode="json"), wrong[argument]):
        changed = dict(arguments, **{argument: replacement})
        with pytest.raises(TypeError, match=argument):
            module.compute_soil_loss(**changed, parameters={})


# --- the argument parameters (D46, D56) ---------------------------------------


def test_parameters_missing_positional_or_not_a_dict_raises_type_error():
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    with pytest.raises(TypeError, match="parameters"):
        module.compute_soil_loss(**arguments)
    with pytest.raises(TypeError):
        module.compute_soil_loss(*arguments.values(), {})
    for wrong in (None, [], (), "PLACEHOLDER", list(catalogue().items())):
        with pytest.raises(TypeError, match="parameters"):
            module.compute_soil_loss(**arguments, parameters=wrong)
    record = next(iter(catalogue().values()))
    for wrong in ({"a.json": "PLACEHOLDER"}, {"a.json": [record]}, {object(): record}):
        with pytest.raises(TypeError, match="parameters"):
            module.compute_soil_loss(**arguments, parameters=wrong)


def test_empty_catalogue_names_every_parameter_and_keeps_every_year():
    span = several_full_years()
    result = run(climate_=climate(span), soil_=computable_soil(), parameters={})
    assert isinstance(result, SoilLossResults)
    assert [item.ag_year for item in result.annual] == expected_ag_years(*span)
    assert {item.missing.reason for item in result.annual} == {"MISSING_INPUT"}
    detail = result.annual[0].missing.detail
    assert {item.missing.detail for item in result.annual} == {detail}
    for factor in equation.FACTOR_NAMES:
        assert f"factor '{factor}' is missing" in detail
    for pid in module.PARAMETER_IDS:
        assert f"{named(pid)} has no record in parameters (D56)" in detail
    assert "M1.5" in detail and "D45" in detail
    assert {item.missing.reason for item in result.monthly} == {"NOT_AVAILABLE"}
    assert all("M1.2" in item.missing.detail for item in result.monthly)


def test_full_catalogue_gives_the_product_of_equation_py():
    span = partial_years()
    result = run_computable(climate_=climate(span))
    product = expected_product()
    numbers = 0
    for item in result.annual:
        covered = is_covered(
            first_day_of(item.ag_year), last_day_of(item.ag_year), span
        )
        if not covered:
            assert item.value is None and item.missing.reason == "NO_COVERAGE"
            continue
        numbers += 1
        assert item.missing is None
        assert item.value == product
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        assert item.source is not None and not item.assumption
        for pid in module.PARAMETER_IDS:
            assert f"'{pid}'" in item.source
        assert item.range is None
        assert item.range_missing.reason == "NOT_AVAILABLE"
    assert numbers > 0
    for item in result.monthly:
        assert item.value is None
        assert item.missing.reason in {"NOT_AVAILABLE", "NO_COVERAGE"}
    dumped = result.model_dump(mode="json")
    assert SoilLossResults.model_validate_json(json.dumps(dumped)) == result


def test_ls_is_computed_through_ls_py_from_the_catalogue():
    """Every LS record, changed, gives the product of ls.py with the change, on
    both sides of the break slope."""
    slope = computable_soil().slope_steepness.value
    for s_break in (placeholder_values()[module.S_BREAK_ID], slope):
        for pid in (None, *module.LS_IDS):
            numbers = dict(placeholder_values(), **{module.S_BREAK_ID: s_break})
            if pid is not None:
                numbers[pid] += 1
            marked = marked_catalogue()
            for key, number in numbers.items():
                marked[f"{key}.json"]["value"] = number
            result = run_computable(unmarked(marked))
            assert {item.value for item in result.annual} == {
                expected_product(numbers)
            }, pid


@pytest.mark.parametrize("pid", module.PARAMETER_IDS)
def test_removing_any_one_record_makes_the_year_missing_and_names_it(pid):
    result = run_computable(catalogue(pid))
    for item in result.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(pid)} has no record in parameters (D56)" in item.missing.detail
        for other in module.PARAMETER_IDS:
            if other != pid:
                assert f"'{other}'" not in item.missing.detail


@pytest.mark.parametrize("pid", [module.R_ID, module.S_BREAK_ID, module.C_ID])
def test_record_with_null_value_repeats_its_reason(pid):
    marked = marked_catalogue()
    record = marked[f"{pid}.json"]
    record["value"] = None
    record["value_missing_reason"] = "PLACEHOLDER: the source gives no value here"
    parameters = unmarked(marked)
    assert check_catalogue(parameters) == []
    for item in run_computable(parameters).annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        assert f"the record of {named(pid)} has no value" in detail
        assert unmarked("PLACEHOLDER: the source gives no value here") in detail


def test_record_that_read_value_refuses_is_missing_input():
    marked = marked_catalogue()
    malformed = unmarked(marked)
    del malformed[f"{module.K_ID}.json"]["unit"]
    cases = {
        module.R_ID: dict(
            unmarked(marked), **{f"{module.R_ID}.json": marked[f"{module.R_ID}.json"]}
        ),
        module.K_ID: malformed,
    }
    for pid, parameters in cases.items():
        assert check_catalogue(parameters) != []
        for item in run_computable(parameters).annual:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                f"the record of {named(pid)} is refused by params.catalogue.read_value"
                in item.missing.detail
            )


def test_only_a_record_with_the_empty_scope_is_read():
    parameters = catalogue()
    record = parameters.pop(f"{module.P_ID}.json")
    parameters["scoped.json"] = dict(record, scope={"management": "UNMARKED_TEST_ONLY"})
    assert check_catalogue(parameters) == []
    for item in run_computable(parameters).annual:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(module.P_ID)} has no record" in item.missing.detail


def test_two_records_with_one_identity_are_missing_input():
    parameters = catalogue()
    parameters["copy.json"] = copy.deepcopy(parameters[f"{module.C_ID}.json"])
    assert check_catalogue(parameters) != []
    for item in run_computable(parameters).annual:
        assert item.missing.reason == "MISSING_INPUT"
        assert f"{named(module.C_ID)} has more than one record" in item.missing.detail


def test_slope_unit_that_ls_py_cannot_read_is_not_computed():
    soil_ = soil()  # the example slope unit is a PLACEHOLDER unit
    document = computable_soil_document()
    document["slope_steepness"]["unit"] = soil_.slope_steepness.unit
    marked = marked_catalogue()
    marked[f"{module.S_BREAK_ID}.json"]["unit"] = "PLACEHOLDER_unit"
    cases = (
        (SiteSoilSlope.model_validate(document), catalogue(), "slope_steepness"),
        (computable_soil(), unmarked(marked), f"parameter '{module.S_BREAK_ID}'"),
    )
    for soil_slope, parameters, what in cases:
        for item in run_computable(parameters, soil_=soil_slope).annual:
            assert item.value is None
            detail = item.missing.detail
            assert (
                f"factor 'ls' is missing (reason {module.UNIT_NOT_ACCEPTED}" in detail
            )
            assert f"of {what} is not one that engine/erosion/ls.py reads" in detail


def test_factor_in_another_unit_is_stopped_by_the_unit_guard():
    marked = marked_catalogue()
    marked[f"{module.R_ID}.json"]["unit"] = "PLACEHOLDER_unit"
    for item in run_computable(unmarked(marked)).annual:
        assert item.value is None
        assert item.missing.reason == module.UNIT_NOT_ACCEPTED
        assert "factor 'r' is in the unit" in item.missing.detail


def test_no_value_is_a_number_unless_every_factor_is_present():
    codes = set(get_args(ReasonCode))
    cases = [
        run(),
        run(climate_=climate(partial_years())),
        run(infeasible_calendar()),
        run(calendar_outside_the_record()),
        run(calendar_without_start_month()),
        run(climate_=climate_with(None)),
        run(soil_=soil_with_missing("slope_steepness", "slope_length")),
        run(soil_=computable_soil(), parameters=catalogue(module.P_ID)),
        run(soil_=soil(), parameters=catalogue()),
    ]
    for result in cases:
        if isinstance(result, Missing):
            assert result.reason in codes
            continue
        for item in values(result):
            assert item.value is None
            assert item.value != 0
            assert item.missing is not None and item.missing.reason in codes
            assert item.range is None and item.range_missing is None
            assert item.source is None and item.provenance is None


def test_arguments_unchanged_and_second_call_equal():
    for parameters, soil_ in (
        ({}, soil_with_missing("slope_length")),
        (catalogue(), computable_soil()),
    ):
        arguments = {
            "calendar": calendar(),
            "climate": climate(partial_years()),
            "soil_slope": soil_,
            "parameters": parameters,
        }
        before = {name: copy.deepcopy(value) for name, value in arguments.items()}
        first = module.compute_soil_loss(**arguments)
        assert arguments == before
        assert module.compute_soil_loss(**arguments) == first


# --- the modules --------------------------------------------------------------


def imported_names(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            names.append(node.module)
    return names


def numbers_in(path: Path) -> set[object]:
    return {
        node.value
        for node in ast.walk(ast.parse(path.read_text("utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }


def test_modules_import_only_allowed_modules_and_hold_only_counting_integers():
    allowed_engine = {
        "engine.erosion",
        "engine.erosion._parameters",
        "engine.erosion.equation",
    }
    for name in imported_names(HERE / "soil_loss.py"):
        assert (
            name.split(".")[0] in sys.stdlib_module_names
            or name.startswith("contracts.inputs.")
            or name == "contracts.results.models"
            or name in allowed_engine
        ), name
    for name in imported_names(HERE / "_parameters.py"):
        assert name.split(".")[0] in sys.stdlib_module_names or name in {
            "contracts.results.models",
            "params.catalogue",
        }, name
    # Never load_folder or anything else that reads a file (G1).
    reads_files = {"load_folder", "check_folder", "check_layout", "open", "read_text"}
    for path in (HERE / "soil_loss.py", HERE / "_parameters.py"):
        used = set()
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.alias):
                used.add(node.name)
        assert used.isdisjoint(reads_files), path.name
    assert numbers_in(HERE / "soil_loss.py") == {12, 1}
    assert numbers_in(HERE / "_parameters.py") == {1}
    tree = ast.parse((HERE / "soil_loss.py").read_text("utf-8"))
    format_specs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None
    ]
    assert format_specs == [], "a format specification can hide a number"


def test_package_exposes_compute_soil_loss_with_parameters_by_keyword_and_no_default():
    from engine.erosion import compute_soil_loss

    assert compute_soil_loss is module.compute_soil_loss
    signature = inspect.signature(compute_soil_loss)
    assert list(signature.parameters) == [
        "calendar",
        "climate",
        "soil_slope",
        "parameters",
    ]
    parameter = signature.parameters["parameters"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_soil_loss_md_lists_every_parameter_identifier():
    text = (HERE / "SOIL_LOSS.md").read_text("utf-8")
    section = text.split("## Parameters EP1 reads", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(
        r"^\| `[A-Za-z0-9_]+` \| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE
    )
    assert sorted(listed) == sorted(module.PARAMETER_IDS)


def test_proposed_cases_match_soil_loss_md():
    text = (HERE / "SOIL_LOSS.md").read_text("utf-8")
    section = text.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
