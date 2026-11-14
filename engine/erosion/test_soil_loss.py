"""Acceptance test of unit l0/erosion-entrypoint (issue #115).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``SOIL_LOSS.md`` under "PROPOSED cases"; a test checks that the two lists
agree. The identifier of a case is the name of its test function without
``test_``, with hyphens.

Every input is built from the PLACEHOLDER examples of
``contracts/inputs/examples/``, loaded and then changed in memory. The daily
values of a longer "precipitation" series repeat the items of the example
series in order; no number is written here. Expected agricultural years are
computed from the dates of the series, day by day, independently of the
module under test.

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
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    ReasonCode,
    SoilLossResults,
)
from engine.erosion import soil_loss as module

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
INDICATOR = "soil_loss"
PRECIPITATION = "precipitation"  # decision D23 of issue #77
FACTORS = ("R", "K", "LS", "C", "P")
ONE_DAY = dt.timedelta(days=1)


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
    """From the first day of the agricultural year after the example's first
    day, to the last day of the agricultural year two later."""
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
) -> SoilLossResults | Missing:
    return module.compute_soil_loss(
        calendar=calendar_ if calendar_ is not None else calendar(),
        climate=climate_ if climate_ is not None else climate(),
        soil_slope=soil_ if soil_ is not None else soil(),
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


def soil_with_missing(*names: str) -> SiteSoilSlope:
    document = soil_document()
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


def factor_items(detail: str) -> list[tuple[str, str, str]]:
    """(factor, code, why) of each item of the PROPOSED detail format."""
    _, _, body = detail.partition(": ")
    items = []
    for part in body.split("; "):
        match = re.match(r"(R|K|LS|C|P) ([A-Z_]+): (.+)", part)
        if match:
            items.append(match.groups())
    return items


# --- cases -------------------------------------------------------------------


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
    result = run(infeasible_calendar(), climate(partial_years()))
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
        expected = "MISSING_INPUT" if covered else "NO_COVERAGE"
        assert item.missing.reason == expected, (item.year, item.month)
        month_reasons.add(expected)
        if not covered:
            assert PRECIPITATION in item.missing.detail
    assert month_reasons == {"MISSING_INPUT", "NO_COVERAGE"}
    # A year that is not covered whole still has months that are covered.
    first_year = result.annual[0].ag_year
    assert {
        item.missing.reason for item in result.monthly if item.ag_year == first_year
    } == {"MISSING_INPUT", "NO_COVERAGE"}


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


def test_every_other_value_is_missing_input_naming_each_factor():
    result = run()
    assert isinstance(result, SoilLossResults)
    assert {item.missing.reason for item in values(result)} == {"MISSING_INPUT"}
    detail = result.annual[0].missing.detail
    assert {item.missing.detail for item in values(result)} == {detail}

    items = factor_items(detail)
    assert [factor for factor, _, _ in items] == [
        "R",
        "R",
        "K",
        "LS",
        "LS",
        "C",
        "C",
        "P",
    ]
    codes = {(factor, code) for factor, code, _ in items}
    assert codes == {
        ("R", "MISSING_INPUT"),
        ("R", "NOT_AVAILABLE"),
        ("K", "MISSING_INPUT"),
        ("LS", "MISSING_INPUT"),
        ("C", "MISSING_INPUT"),
        ("C", "NOT_AVAILABLE"),
        ("P", "MISSING_INPUT"),
    }
    whys = {(factor, code): [] for factor, code in codes}
    for factor, code, why in items:
        whys[(factor, code)].append(why)
    assert any("question 10" in why for why in whys[("R", "MISSING_INPUT")])
    assert any("not built" in why for why in whys[("R", "NOT_AVAILABLE")])
    assert any("question 16" in why for why in whys[("K", "MISSING_INPUT")])
    assert any("D46" in why for why in whys[("LS", "MISSING_INPUT")])
    assert any("SlopeUnit" in why for why in whys[("LS", "MISSING_INPUT")])
    assert any("P7" in why for why in whys[("C", "MISSING_INPUT")])
    assert any("not built" in why for why in whys[("C", "NOT_AVAILABLE")])
    assert any("M1.6" in why for why in whys[("P", "MISSING_INPUT")])
    # NOT_AVAILABLE only for a part that is not built (D12, D31).
    for factor, code, why in items:
        if code == "NOT_AVAILABLE":
            assert "not built" in why


@pytest.mark.parametrize(
    "names",
    [("slope_steepness",), ("slope_length",), ("slope_steepness", "slope_length")],
)
def test_missing_slope_input_is_named_in_the_ls_item(names):
    result = run(soil_=soil_with_missing(*names))
    assert isinstance(result, SoilLossResults)
    detail = result.annual[0].missing.detail
    ls_items = [
        (code, why) for factor, code, why in factor_items(detail) if factor == "LS"
    ]
    for name in names:
        assert any(
            code == "NO_COVERAGE" and why.startswith(f"{name} is missing")
            for code, why in ls_items
        ), name
    for name in {"slope_steepness", "slope_length"} - set(names):
        assert not any(why.startswith(f"{name} is missing") for _, why in ls_items)


def every_case() -> list[SoilLossResults | Missing]:
    return [
        run(),
        run(climate_=climate(partial_years())),
        run(infeasible_calendar()),
        run(calendar_outside_the_record()),
        run(calendar_without_start_month()),
        run(climate_=climate_with(None)),
        run(soil_=soil_with_missing("slope_steepness", "slope_length")),
    ]


def test_no_value_is_a_number_and_none_is_zero():
    codes = set(get_args(ReasonCode))
    for result in every_case():
        if isinstance(result, Missing):
            assert result.reason in codes
            continue
        for item in values(result):
            assert item.value is None
            assert item.value != 0
            assert item.missing is not None and item.missing.reason in codes
            assert item.range is None and item.range_missing is None
            for _, code, _ in factor_items(item.missing.detail):
                assert code in codes


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_arguments_of_another_case_or_field_raise_value_error(argument, field):
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
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
            module.compute_soil_loss(**changed)


def test_arguments_unchanged_and_second_call_equal():
    arguments = {
        "calendar": calendar(),
        "climate": climate(partial_years()),
        "soil_slope": soil_with_missing("slope_length"),
    }
    before = {name: copy.deepcopy(value) for name, value in arguments.items()}
    first = module.compute_soil_loss(**arguments)
    assert arguments == before
    assert module.compute_soil_loss(**arguments) == first


def test_module_imports_only_allowed_modules_and_holds_only_month_integers():
    tree = ast.parse((HERE / "soil_loss.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            allowed = (
                top in sys.stdlib_module_names
                or name.startswith("contracts.inputs.")
                or name == "contracts.results.models"
            )
            assert allowed, name
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers == {12, 1}


def test_package_exposes_compute_soil_loss_with_exactly_three_parameters():
    from engine.erosion import compute_soil_loss

    assert compute_soil_loss is module.compute_soil_loss
    assert list(inspect.signature(compute_soil_loss).parameters) == [
        "calendar",
        "climate",
        "soil_slope",
    ]


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
