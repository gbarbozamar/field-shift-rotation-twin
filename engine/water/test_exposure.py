"""Acceptance test of unit l1/water-entrypoint (issue #134).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``EXPOSURE.md`` under "PROPOSED cases"; a test checks that the two lists
agree. The identifier of a case is the name of its test function without
``test_``, with hyphens.

Every input is built from the PLACEHOLDER examples of
``contracts/inputs/examples/``, loaded and then changed in memory. A longer
daily series repeats the items of the example ``precipitation`` series in
order, under the quantity identifier it stands for; no number is written here.
Expected agricultural years are computed from the dates of the series, day by
day, independently of the module under test.

Run from the repository root: ``py -3.12 -m pytest engine/water/test_exposure.py``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import json
import re
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, get_args

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_WATER_DEFICIT_EXPOSURE,
    ReasonCode,
    ResultsPerRotation,
    WaterDeficitExposure,
)
from engine.water import exposure as module
from engine.water.balance import CropDay, run_balance
from engine.water.et0 import Et0Constants
from engine.water.et0.quantities import CLIMATE_QUANTITIES

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
INDICATOR = "water_deficit_exposure"
PRECIPITATION = "precipitation"  # decision D23 of issue #77
DAILY_INPUTS = (PRECIPITATION, *CLIMATE_QUANTITIES)
REASON_CODES = set(get_args(ReasonCode))
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


def daily_series(
    quantity: str, first: dt.date, last: dt.date, *, with_gaps: bool = False
) -> dict[str, Any]:
    """The example ``precipitation`` series stretched from ``first`` to ``last``.

    Each day takes, in turn, the item of an example day: only the days with a
    value, or, ``with_gaps``, every example day including those held missing.
    """
    series = copy.deepcopy(example_precipitation())
    items = [
        {k: v for k, v in item.items() if k != "date"}
        for item in series["days"]
        if with_gaps or item.get("missing") is None
    ]
    days = []
    day = first
    position = 0
    while day <= last:
        days.append({"date": day.isoformat(), **items[position % len(items)]})
        day += ONE_DAY
        position += 1
    series.update(
        quantity=quantity,
        start_date=first.isoformat(),
        end_date=last.isoformat(),
        days=days,
    )
    return series


def first_day_of(ag_year: int) -> dt.date:
    return dt.date(ag_year, start_month(), 1)


def last_day_of(ag_year: int) -> dt.date:
    return first_day_of(ag_year + 1) - ONE_DAY


def several_full_years() -> tuple[dt.date, dt.date]:
    """From the first day of the agricultural year that begins in the calendar
    year of the example's first day, to the last day of the one two later."""
    first_ag_year = example_start().year
    return first_day_of(first_ag_year), last_day_of(first_ag_year + 2)


def climate_with(series: list[dict[str, Any]]) -> SiteClimate:
    document = climate_document()
    others = [
        item
        for item in document["daily_series"]
        if item["quantity"] not in DAILY_INPUTS
    ]
    document["daily_series"] = others + series
    return SiteClimate.model_validate(document)


def climate(
    span: tuple[dt.date, dt.date] | None = None,
    *,
    quantities: tuple[str, ...] = DAILY_INPUTS,
    with_gaps: bool = False,
) -> SiteClimate:
    """The six daily series the water chain reads, over one span."""
    first, last = span or several_full_years()
    return climate_with(
        [daily_series(name, first, last, with_gaps=with_gaps) for name in quantities]
    )


def calendar() -> RotationCalendar:
    return RotationCalendar.model_validate(calendar_document())


def soil() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(soil_document())


def run(
    calendar_: RotationCalendar | None = None,
    climate_: SiteClimate | None = None,
    soil_: SiteSoilSlope | None = None,
) -> list[WaterDeficitExposure]:
    return module.compute_water_deficit_exposure(
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
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER"},
    }
    return RotationCalendar.model_validate(document)


def items_of(detail: str) -> list[str]:
    """The items of a ``MISSING_INPUT`` detail, after its opening sentence."""
    return detail.split(": ", 1)[1].split("; ")


def codes_of(detail: str) -> list[str]:
    """The reason code of each item, ``OPEN`` for an item whose code is not decided."""
    codes = []
    for item in items_of(detail):
        code = item.split(" ", 2)[1].rstrip(":")
        codes.append("OPEN" if code == "(reason" else code)
    return codes


def assert_loads(result: list[WaterDeficitExposure]) -> None:
    for item in result:
        assert isinstance(item, WaterDeficitExposure)
        assert item.indicator == INDICATOR
        assert item.direction == DIRECTION_OF[INDICATOR]
        assert item.unit == UNIT_WATER_DEFICIT_EXPOSURE
        document = item.model_dump(mode="json")
        assert WaterDeficitExposure.model_validate(document) == item
        assert WaterDeficitExposure.model_validate_json(json.dumps(document)) == item


# --- the cases ---------------------------------------------------------------


def test_examples_as_they_are_load_and_every_item_is_missing():
    result = run(climate_=SiteClimate.model_validate(climate_document()))
    assert_loads(result)
    series = example_precipitation()
    span = (
        dt.date.fromisoformat(series["start_date"]),
        dt.date.fromisoformat(series["end_date"]),
    )
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    for item in result:
        assert item.time_basis == "ag_year"
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason in REASON_CODES


def test_several_agricultural_years_load_into_results_per_rotation():
    span = several_full_years()
    result = run(climate_=climate(span))
    assert_loads(result)
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    assert len(result) > 1
    assert {item.time_basis for item in result} == {"ag_year"}
    results = json.loads(
        (
            ROOT
            / "contracts"
            / "results"
            / "examples"
            / "PLACEHOLDER_results_per_rotation.json"
        ).read_text("utf-8")
    )
    results["water_deficit_exposure"] = [
        item.model_dump(mode="json") for item in result
    ]
    loaded = ResultsPerRotation.model_validate(results)
    assert list(loaded.water_deficit_exposure) == result


def test_every_covered_year_is_missing_input_naming_each_part():
    result = run()
    assert result
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        detail = item.missing.detail
        items = items_of(detail)
        parts = [entry.split(" ", 1)[0] for entry in items]
        assert parts == ["ET0"] * 3 + ["balance"] * 4 + ["indicator"]
        assert codes_of(detail) == [
            "MISSING_INPUT",
            "MISSING_INPUT",
            "MISSING_INPUT",
            "MISSING_INPUT",
            "MISSING_INPUT",
            "NOT_AVAILABLE",
            "NOT_AVAILABLE",
            "OPEN",
        ]
        for name in (field.name for field in fields(Et0Constants)):
            assert name in items[0]
        assert "D46" in items[0]
        assert "Q11" in items[1]
        assert "PointUnits" in items[2]
        for name, parameter in inspect.signature(run_balance).parameters.items():
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                assert name in items[3]
        for name in (field.name for field in fields(CropDay)):
            assert name in items[4]
        assert "Curve Number" in items[5]
        assert "surface-layer" in items[6]
        assert "question 4 of contracts/results/README.md" in items[7]
        assert "C1.4" in items[7]
        for code in codes_of(detail):
            assert code == "OPEN" or code in REASON_CODES


def test_infeasible_calendar_makes_every_item_not_computable():
    first, last = several_full_years()
    span = (first + ONE_DAY, last)  # the first year is not covered whole
    result = run(calendar_=infeasible_calendar(), climate_=climate(span))
    assert [item.ag_year for item in result] == expected_ag_years(*span)
    for item in result:
        assert item.missing.reason == "NOT_COMPUTABLE"
        assert "infeasible" in item.missing.detail


def test_year_not_covered_by_a_series_is_no_coverage():
    first, last = several_full_years()
    # The record starts and ends inside agricultural years.
    span = (first + ONE_DAY, last - ONE_DAY)
    result = run(climate_=climate(span))
    years = expected_ag_years(*span)
    assert [item.ag_year for item in result] == years
    for item in result:
        if item.ag_year in (years[0], years[-1]):
            assert item.missing.reason == "NO_COVERAGE"
            assert f"'{PRECIPITATION}'" in item.missing.detail
            assert "C5.5" in item.missing.detail
        else:
            assert item.missing.reason == "MISSING_INPUT"

    # One input of the reference evapotranspiration is shorter than the record.
    for short in CLIMATE_QUANTITIES:
        series = [
            daily_series(name, first, last - ONE_DAY if name == short else last)
            for name in DAILY_INPUTS
        ]
        result = run(climate_=climate_with(series))
        assert [item.ag_year for item in result] == expected_ag_years(first, last)
        assert result[-1].missing.reason == "NO_COVERAGE"
        assert f"'{short}'" in result[-1].missing.detail
        assert f"'{PRECIPITATION}'" not in result[-1].missing.detail
        for item in result[:-1]:
            assert item.missing.reason == "MISSING_INPUT"


def test_series_one_day_short_at_each_end_leaves_first_and_last_not_covered():
    first, last = several_full_years()
    exact = run(climate_=climate((first, last)))
    assert {item.missing.reason for item in exact} == {"MISSING_INPUT"}
    short = run(climate_=climate((first + ONE_DAY, last - ONE_DAY)))
    assert [item.ag_year for item in short] == [item.ag_year for item in exact]
    reasons = [item.missing.reason for item in short]
    assert reasons[0] == reasons[-1] == "NO_COVERAGE"
    assert set(reasons[1:-1]) == {"MISSING_INPUT"}


def test_absent_daily_series_is_missing_input_naming_it():
    for absent in CLIMATE_QUANTITIES:
        kept = tuple(name for name in DAILY_INPUTS if name != absent)
        result = run(climate_=climate(quantities=kept))
        assert [item.ag_year for item in result] == expected_ag_years(
            *several_full_years()
        )
        for item in result:
            assert item.missing.reason == "MISSING_INPUT"
            first_item = items_of(item.missing.detail)[0]
            assert first_item.startswith("input MISSING_INPUT")
            assert f"no daily series '{absent}'" in first_item
            for other in kept:
                assert f"no daily series '{other}'" not in item.missing.detail


def test_days_held_missing_are_missing_input_naming_the_series():
    result = run(climate_=climate(with_gaps=True))
    assert result
    for item in result:
        assert item.missing.reason == "MISSING_INPUT"
        inputs = [
            entry
            for entry in items_of(item.missing.detail)
            if entry.startswith("input")
        ]
        assert len(inputs) == len(DAILY_INPUTS)
        for name, entry in zip(DAILY_INPUTS, inputs, strict=True):
            assert entry.startswith("input MISSING_INPUT")
            assert f"'{name}'" in entry
            assert f"agricultural year {item.ag_year}" in entry
            first_held = dt.date.fromisoformat(
                entry.rsplit("the first on ", 1)[1].split(",", 1)[0]
            )
            assert first_day_of(item.ag_year) <= first_held <= last_day_of(item.ag_year)


@pytest.mark.parametrize(
    "names", [("latitude",), ("elevation",), ("latitude", "elevation"), ("longitude",)]
)
def test_missing_point_value_is_named_in_an_et0_item(names):
    document = climate_document()
    document["daily_series"] = [
        daily_series(name, *several_full_years()) for name in DAILY_INPUTS
    ]
    for name in names:
        unit = document["point"][name]["unit"]
        document["point"][name] = {
            "value": None,
            "unit": unit,
            "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
        }
    result = run(climate_=SiteClimate.model_validate(document))
    for item in result:
        point_items = [
            entry
            for entry in items_of(item.missing.detail)
            if "point of the climate record" in entry
        ]
        read = [name for name in names if name != "longitude"]
        assert len(point_items) == len(read)
        for name, entry in zip(read, point_items, strict=True):
            assert entry.startswith(f"ET0 NO_COVERAGE: {name} is missing")
            assert entry.endswith(": PLACEHOLDER")
        assert "longitude" not in item.missing.detail


def test_series_in_different_time_zones_make_every_item_not_computable():
    first, last = several_full_years()
    series = [daily_series(name, first, last) for name in DAILY_INPUTS]
    series[-1]["time_zone"] = "PLACEHOLDER_other_time_zone"
    result = run(climate_=climate_with(series))
    assert [item.ag_year for item in result] == expected_ag_years(first, last)
    for item in result:
        assert item.missing.reason == "NOT_COMPUTABLE"
        assert "C6.3" in item.missing.detail


def test_start_month_missing_returns_one_item_for_the_rotation():
    result = run(calendar_=calendar_without_start_month())
    assert_loads(result)
    (item,) = result
    assert item.time_basis == "rotation"
    assert item.ag_year is None
    assert item.missing.reason == "MISSING_INPUT"
    assert "ag_year_start.month" in item.missing.detail


def test_no_precipitation_series_returns_one_item_for_the_rotation():
    result = run(climate_=climate(quantities=CLIMATE_QUANTITIES))
    assert_loads(result)
    (item,) = result
    assert item.time_basis == "rotation"
    assert item.missing.reason == "MISSING_INPUT"
    assert f"'{PRECIPITATION}'" in item.missing.detail


def test_calendar_dates_outside_the_record_keep_the_years_of_the_record():
    span = several_full_years()
    reference = run(climate_=climate(span))
    document = calendar_document()
    start = dt.date.fromisoformat(document["start_date"])
    end = dt.date.fromisoformat(document["end_date"])
    shift = span[1] - start + ONE_DAY
    document["start_date"] = (start + shift).isoformat()
    document["end_date"] = (end + shift).isoformat()
    for component in document["components"]:
        for edge in [component, *component["periods"]]:
            for key in ("start", "end"):
                if edge[key]["date"] is not None:
                    moved = dt.date.fromisoformat(edge[key]["date"]) + shift
                    edge[key]["date"] = moved.isoformat()
    moved_calendar = RotationCalendar.model_validate(document)
    assert moved_calendar.start_date > span[1]
    assert run(calendar_=moved_calendar, climate_=climate(span)) == reference


def every_kind_of_result() -> list[list[WaterDeficitExposure]]:
    """One result of each situation of the cases above."""
    first, last = several_full_years()
    mixed = [daily_series(name, first, last) for name in DAILY_INPUTS]
    mixed[-1]["time_zone"] = "PLACEHOLDER_other_time_zone"
    return [
        run(climate_=SiteClimate.model_validate(climate_document())),
        run(),
        run(climate_=climate(with_gaps=True)),
        run(climate_=climate((first + ONE_DAY, last - ONE_DAY))),
        run(climate_=climate(quantities=DAILY_INPUTS[:-1])),
        run(calendar_=infeasible_calendar()),
        run(climate_=climate_with(mixed)),
        run(calendar_=calendar_without_start_month()),
        run(climate_=climate(quantities=CLIMATE_QUANTITIES)),
    ]


def test_the_list_is_never_empty_and_no_item_is_a_number():
    for result in every_kind_of_result():
        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert item.value is None
            assert item.value != 0
            assert item.missing is not None
            assert item.missing.reason in REASON_CODES
            assert item.provenance is None
            assert item.range is None and item.range_missing is None
        assert len({item.time_basis for item in result}) == 1
        ag_years = [item.ag_year for item in result]
        assert len(set(ag_years)) == len(ag_years)


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_arguments_of_another_case_or_field_raise_value_error(argument, field):
    loader = {"climate": climate_document, "soil_slope": soil_document}[argument]
    model = {"climate": SiteClimate, "soil_slope": SiteSoilSlope}[argument]
    document = loader()
    document[field] = f"{document[field]}-other"
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    arguments[argument] = model.model_validate(document)
    with pytest.raises(ValueError, match=field):
        module.compute_water_deficit_exposure(**arguments)


@pytest.mark.parametrize("argument", ["calendar", "climate", "soil_slope"])
def test_argument_that_is_not_its_model_raises_type_error(argument):
    arguments = {"calendar": calendar(), "climate": climate(), "soil_slope": soil()}
    other_model = soil() if argument != "soil_slope" else calendar()
    for wrong in (arguments[argument].model_dump(mode="json"), other_model):
        given = dict(arguments)
        given[argument] = wrong
        with pytest.raises(TypeError, match=argument):
            module.compute_water_deficit_exposure(**given)


def test_arguments_unchanged_and_second_call_equal():
    arguments = {
        "calendar": calendar(),
        "climate": climate(with_gaps=True),
        "soil_slope": soil(),
    }
    before = copy.deepcopy(arguments)
    first = module.compute_water_deficit_exposure(**arguments)
    assert arguments == before
    assert module.compute_water_deficit_exposure(**arguments) == first


def test_module_imports_only_allowed_modules_and_holds_only_the_integer_one():
    tree = ast.parse((HERE / "exposure.py").read_text("utf-8"))
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
                or name in ("engine.water.et0", "engine.water.et0.quantities")
                or name == "engine.water.balance"
            )
            assert allowed, name
            assert top not in ("os", "io", "pathlib", "socket", "time", "random")
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers == {1}
    format_specs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None
    ]
    assert format_specs == [], "a format specification can hide a number"


def test_package_exposes_compute_water_deficit_exposure_with_exactly_three_parameters():
    from engine.water import compute_water_deficit_exposure

    assert compute_water_deficit_exposure is module.compute_water_deficit_exposure
    parameters = inspect.signature(compute_water_deficit_exposure).parameters
    assert list(parameters) == ["calendar", "climate", "soil_slope"]
    assert all(p.default is inspect.Parameter.empty for p in parameters.values())


def test_runner_discovers_the_entry_point():
    from api.engines import discover_engine_functions

    found = discover_engine_functions()
    assert found.compute_water_deficit_exposure is module.compute_water_deficit_exposure


def test_route_answers_with_a_water_part_that_loads_into_results_per_rotation():
    """In process, with the examples, no network.

    EP2 is replaced by the example calendar, which carries a start month: the
    calendar engine on ``main`` writes the start month as missing until the
    rotation definition carries it (#129), and then EP1 returns one ``Missing``
    and the route has no ``ResultsPerRotation`` at all. EP1 and EP3 are the
    functions the runner discovers.
    """
    from fastapi.testclient import TestClient

    from adapters.example_soil_slope import ExampleSoilSlopeSource
    from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
    from api.engines import (
        DEFAULT_CARBON_MODELS,
        EngineFunctions,
        EntryPointEngines,
        discover_engine_functions,
    )
    from api.main import create_app
    from api.ports import RunSettings

    example_climate = SiteClimate.model_validate(climate_document())
    series = example_precipitation()

    class ExampleClimate:
        source_id = "PLACEHOLDER_CLIMATE"
        contract = "site_data_climate"

        def get_climate(self, request: ClimateRequest) -> ClimateResult:
            return ClimateResult(
                data=example_climate,
                source=SourceInfo(
                    id=self.source_id, contract=self.contract, state="example"
                ),
            )

    found = discover_engine_functions()
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=lambda rotation: calendar(),
            compute_soil_loss=found.compute_soil_loss,
            compute_water_deficit_exposure=found.compute_water_deficit_exposure,
        ),
        carbon_models=DEFAULT_CARBON_MODELS,
    )
    rotation = json.loads(
        (
            ROOT
            / "contracts"
            / "rotation_definition"
            / "examples"
            / "PLACEHOLDER_rotation_definition.json"
        ).read_text("utf-8")
    )
    example_calendar = calendar_document()
    body = {
        "site": {
            "case_id": example_calendar["case_id"],
            "field_id": example_calendar["field_id"],
            "latitude": example_climate.point.latitude.value,
            "longitude": example_climate.point.longitude.value,
        },
        "rotation": rotation,
    }
    app = create_app(
        [],
        climate=ExampleClimate(),
        soil_slope=ExampleSoilSlopeSource(
            EXAMPLES / "PLACEHOLDER_site_soil_slope.json"
        ),
        engines=engines,
        settings=RunSettings(
            start_date=dt.date.fromisoformat(series["start_date"]),
            end_date=dt.date.fromisoformat(series["end_date"]),
        ),
    )
    response = TestClient(app).post("/api/rotations/run", json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    result = ResultsPerRotation.model_validate(answer["result"])
    water = result.water_deficit_exposure
    assert isinstance(water, list)
    assert water == module.compute_water_deficit_exposure(
        calendar=calendar(), climate=example_climate, soil_slope=soil()
    )
    (water_module,) = [m for m in answer["modules"] if m["id"] == "water"]
    assert water_module["state"] == "not_available"
    assert water_module["reason"] == water[0].missing.reason


def test_proposed_cases_match_exposure_md():
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    section = text.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
