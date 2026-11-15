"""End-to-end chain on the examples: unit l0/chain-examples (issue #168).

The rotation definition example, the chain examples of site climate and site
soil and slope (``contracts/inputs/examples/PLACEHOLDER_chain_*.json``) and
the real engine runner of ``api/engines.py``, in process and with no network:

    rotation definition -> EP2 calendar -> EP1 soil loss and EP3 water deficit
    exposure -> ResultsPerRotation

It shows that the chain is wired. It is not a result: every number in the
examples and in the test catalogue is PLACEHOLDER, plainly unreal.

The cases are PROPOSED (blueprint section 3.7) and are listed in
``validation/README.md`` under "PROPOSED cases", section "Chain of the
examples"; a test checks that the two lists agree. The code of a case is the
start of its test name.

Test catalogue: every record EP1 reads is built here in the record format of
``params/README.md`` and carries the word PLACEHOLDER in its citation, its
persons and its reasons. ``params.catalogue`` refuses a record with that word,
so, as ``params/test_layout.py`` and ``engine/erosion/test_soil_loss.py`` do,
the catalogue passed to the runner is an in-memory copy in which the word is
replaced by ``UNMARKED_TEST_ONLY``; that copy passes ``check_catalogue``.

Run from the repository root: ``python -m pytest validation/test_chain_examples.py``.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SoilSlopeResult, SourceInfo
from api.engines import (
    CALENDAR,
    DEFAULT_CARBON_MODELS,
    EROSION,
    OTHER_FIELD,
    WATER,
    EngineFunctions,
    EntryPointEngines,
    discover_engine_functions,
    takes_parameters,
)
from api.ports import EnginesResult, RunSettings
from contracts.inputs import SiteClimate, SiteSoilSlope
from contracts.results.models import (
    PROVENANCE_OF_SOIL_LOSS,
    Missing,
    PartNotBuilt,
    ResultsPerRotation,
    SoilLossResults,
)
from contracts.rotation_definition import RotationDefinition
from engine.erosion import equation, ls
from engine.erosion import soil_loss as ep1
from engine.water import exposure as ep3
from params.catalogue import check_catalogue

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INPUT_EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
ROTATION_EXAMPLE = (
    ROOT
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
CHAIN_CLIMATE = INPUT_EXAMPLES / "PLACEHOLDER_chain_site_climate.json"
CHAIN_SOIL_SLOPE = INPUT_EXAMPLES / "PLACEHOLDER_chain_site_soil_slope.json"

WORD = "PLACEHOLDER"
IDENTITY_FIELDS = ("case_id", "field_id")
ONE_DAY = dt.timedelta(days=1)
# The unit strings of the point, decision D55 of issue #77.
POINT_UNITS_D55 = {"latitude": "degree", "longitude": "degree", "elevation": "m"}


# --- the examples -------------------------------------------------------------


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rotation_document() -> dict[str, Any]:
    return read(ROTATION_EXAMPLE)


def climate() -> SiteClimate:
    return SiteClimate.model_validate_json(CHAIN_CLIMATE.read_text(encoding="utf-8"))


def soil_slope() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate_json(
        CHAIN_SOIL_SLOPE.read_text(encoding="utf-8")
    )


def start_month() -> int:
    """The start month of the agricultural year, as the rotation definition declares it."""
    month = RotationDefinition.model_validate(rotation_document()).ag_year_start.month
    assert month is not None
    return month


def precipitation() -> Any:
    (series,) = [s for s in climate().daily_series if s.quantity == ep1.PRECIPITATION]
    return series


# --- agricultural years, computed here, day by day (C5.3, D47) ----------------


def ag_year_of(day: dt.date, month: int) -> int:
    """The agricultural year a day belongs to, named by the year in which it begins."""
    return day.year if day.month >= month else day.year - 1


def bounds_of(ag_year: int, month: int) -> tuple[dt.date, dt.date]:
    """First and last day of an agricultural year."""
    return dt.date(ag_year, month, 1), dt.date(ag_year + 1, month, 1) - ONE_DAY


def ag_years_touched(first: dt.date, last: dt.date, month: int) -> list[int]:
    """Every agricultural year that holds at least one day from first to last."""
    years: list[int] = []
    day = first
    while day <= last:
        year = ag_year_of(day, month)
        if year not in years:
            years.append(year)
        day += ONE_DAY
    return years


def covered_ag_years(first: dt.date, last: dt.date, month: int) -> list[int]:
    """The agricultural years whose every day lies from first to last."""
    return [
        year
        for year in ag_years_touched(first, last, month)
        if first <= bounds_of(year, month)[0] and bounds_of(year, month)[1] <= last
    ]


def covered() -> list[int]:
    series = precipitation()
    return covered_ag_years(series.start_date, series.end_date, start_month())


# --- the test catalogue -------------------------------------------------------


def unmarked(item: Any) -> Any:
    """An in-memory copy with the word PLACEHOLDER replaced (params/test_layout.py)."""
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {unmarked(key): unmarked(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmarked(value) for value in item]
    return item


# PLACEHOLDER base of the test numbers: plainly unreal, not a value of the
# method. Each record gets the base plus its position in the list of the
# identifiers EP1 reads on its main route.
PLACEHOLDER_BASE = 98765.5

# The identifiers of the main route of EP1: those of the annual value, then
# the twelve monthly erosivity records of the climatology (D69, D84).
CATALOGUE_IDS: tuple[str, ...] = (*ep1.PARAMETER_IDS, *ep1.MONTHLY_EROSIVITY_IDS)

# One PLACEHOLDER unit string shared by the twelve monthly records: not a
# real unit (which unit the climatology prints is OPEN 11 of SOIL_LOSS.md).
MONTHLY_UNIT = "PLACEHOLDER_monthly_erosivity_unit"


def placeholder_numbers() -> dict[str, float]:
    return {
        pid: PLACEHOLDER_BASE + position for position, pid in enumerate(CATALOGUE_IDS)
    }


def unit_of(pid: str) -> str:
    """The unit string of a test record.

    The level of R, K, C and P: the unit EP1 accepts. The twelve monthly
    records: one PLACEHOLDER unit. The break slope: the slope unit of the
    soil-and-slope example. The unit length: the length unit of the
    soil-and-slope example (ls.py compares the two strings). Every other
    coefficient: a PLACEHOLDER unit.
    """
    accepted = ep1.ACCEPTED_UNITS
    example = soil_slope()
    return {
        ep1.R_ID: accepted.r,
        ep1.K_ID: accepted.k,
        ep1.C_ID: accepted.c,
        ep1.P_ID: accepted.p,
        **dict.fromkeys(ep1.MONTHLY_EROSIVITY_IDS, MONTHLY_UNIT),
        ep1.S_BREAK_ID: example.slope_steepness.unit,
        ep1.LAMBDA_UNIT_ID: example.slope_length.unit,
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


def marked_catalogue() -> dict[str, dict]:
    """Every record the main route of EP1 reads, keyed by a file path, still
    marked PLACEHOLDER."""
    return {
        f"{pid}.json": placeholder_record(pid, value)
        for pid, value in placeholder_numbers().items()
    }


def complete_catalogue() -> dict[str, dict]:
    """The unmarked copy of ``marked_catalogue``."""
    return unmarked(marked_catalogue())


def expected_ls(numbers: dict[str, float]) -> float:
    """LS through ls.py, from the soil-and-slope example and the catalogue."""
    example = soil_slope()
    slope_unit = ls.SlopeUnit(example.slope_steepness.unit)
    steepness = ls.slope_steepness_factor(
        slope_steepness=example.slope_steepness.value,
        slope_unit=slope_unit,
        s_break=numbers[ep1.S_BREAK_ID],
        s_break_unit=slope_unit,
        **{name: numbers[pid] for name, pid in ep1.S_COEFFICIENTS.items()},
    )
    length = ls.slope_length_factor(
        slope_length=example.slope_length.value,
        slope_length_unit=example.slope_length.unit,
        lambda_unit=numbers[ep1.LAMBDA_UNIT_ID],
        lambda_unit_unit=example.slope_length.unit,
        slope_steepness=example.slope_steepness.value,
        slope_unit=slope_unit,
        **{name: numbers[pid] for name, pid in ep1.L_COEFFICIENTS.items()},
    )
    assert isinstance(steepness, float) and isinstance(length, float)
    return length * steepness


def expected_soil_loss(numbers: dict[str, float]) -> float:
    """The annual value of the main route: ``equation.annual_soil_loss`` of the
    mean annual level of R, K, LS through ls.py, the declared C and P (D69,
    D84, USER-G)."""
    accepted = ep1.ACCEPTED_UNITS
    product = equation.annual_soil_loss(
        r=equation.Factor(numbers[ep1.R_ID], accepted.r),
        k=equation.Factor(numbers[ep1.K_ID], accepted.k),
        ls=equation.Factor(expected_ls(numbers), accepted.ls),
        c=equation.Factor(numbers[ep1.C_ID], accepted.c),
        p=equation.Factor(numbers[ep1.P_ID], accepted.p),
        accepted_units=accepted,
        unit_guard_reason=ep1.UNIT_NOT_ACCEPTED,
    )
    assert isinstance(product, float)
    return product


def expected_month(numbers: dict[str, float], month: int) -> float:
    """A monthly value of the main route, computed here: the level of R times
    the share of the calendar month in the twelve monthly records (January
    first), times K, LS, C and P."""
    monthly = [numbers[pid] for pid in ep1.MONTHLY_EROSIVITY_IDS]
    return (
        numbers[ep1.R_ID]
        * (monthly[month - 1] / sum(monthly))
        * numbers[ep1.K_ID]
        * expected_ls(numbers)
        * numbers[ep1.C_ID]
        * numbers[ep1.P_ID]
    )


# --- the chain through the real runner ----------------------------------------


def spy(function: Callable[..., Any], calls: list[tuple[str, dict]]) -> Callable:
    """The function, recording each call. ``functools.wraps`` keeps its
    signature visible to ``api.engines.takes_parameters``."""

    @functools.wraps(function)
    def recorded(*args: Any, **kwargs: Any) -> Any:
        calls.append((function.__name__, kwargs))
        return function(*args, **kwargs)

    return recorded


def example_source(contract: str) -> SourceInfo:
    return SourceInfo(
        id="PLACEHOLDER_chain_example", contract=contract, state="example"
    )


def run_chain(parameters: dict[str, dict]) -> tuple[EnginesResult, list]:
    """The rotation definition example through the runner the app builds."""
    found = discover_engine_functions()
    calls: list[tuple[str, dict]] = []
    functions = EngineFunctions(
        build_rotation_calendar=spy(found.build_rotation_calendar, calls),
        compute_soil_loss=spy(found.compute_soil_loss, calls),
        compute_water_deficit_exposure=spy(found.compute_water_deficit_exposure, calls),
    )
    engines = EntryPointEngines(
        functions, carbon_models=DEFAULT_CARBON_MODELS, parameters=parameters
    )
    outcome = engines.run(
        rotation_document(),
        ClimateResult(data=climate(), source=example_source("site_data_climate")),
        SoilSlopeResult(
            data=soil_slope(), source=example_source("site_data_soil_slope")
        ),
    )
    return outcome, calls


def module(outcome: EnginesResult, module_id: str) -> Any:
    (found,) = [m for m in outcome.modules if m.id == module_id]
    return found


def assert_not_an_identity_absence(missing: Missing | None) -> None:
    assert missing is not None
    assert OTHER_FIELD not in (missing.detail or "")


def assert_round_trip(result: ResultsPerRotation) -> None:
    dumped = json.dumps(result.model_dump(mode="json"))
    assert ResultsPerRotation.model_validate_json(dumped) == result


def assert_water_missing_for_every_covered_year(
    outcome: EnginesResult, parameters: dict[str, dict]
) -> None:
    """EP3 gives no number (C1.4, D61), so its reason is asserted instead.

    Every item is missing, none with an identity absence, none ``NO_COVERAGE``
    in a covered year, and the part is EP3's own output for the same
    arguments, passed on unchanged.

    With the point in the unit strings of D55, EP3 passes its unit guard, so
    a covered year is ``MISSING_INPUT`` for what the daily chain lacks, not for
    a unit (Q11): every site parameter of EP3 has no record (D56: neither test
    catalogue holds one), the crop of each day is not known (the calendar's
    dates lie outside the record and the repetition of the rotation over the
    years is not decided, Q5), and the definition of the indicator is
    incomplete (C1.4, D61). The texts are EP3's own constants.
    """
    result = outcome.result
    assert result is not None
    water = result.water_deficit_exposure
    assert not isinstance(water, PartNotBuilt)
    assert [item.ag_year for item in water] == ag_years_of_the_record()
    for item in water:
        assert item.time_basis == "ag_year"
        assert item.value is None
        assert_not_an_identity_absence(item.missing)
        if item.ag_year in covered():
            detail = item.missing.detail
            assert item.missing.reason == "MISSING_INPUT"
            assert "unit string the water engine does not accept" not in detail
            for pid in ep3.SITE_PARAMETERS:
                assert f"'{pid}'" in detail, pid
            assert "no record in parameters (D56)" in detail
            assert ep3.CROP_UNKNOWN in detail
            assert ep3.DEFINITION_INCOMPLETE in detail
    function = ep3.compute_water_deficit_exposure
    extra = {"parameters": parameters} if takes_parameters(function) else {}
    assert water == function(
        calendar=outcome.calendar, climate=climate(), soil_slope=soil_slope(), **extra
    )


def ag_years_of_the_record() -> list[int]:
    series = precipitation()
    return ag_years_touched(series.start_date, series.end_date, start_month())


# --- CH01 to CH03: the chain examples -----------------------------------------


@pytest.mark.parametrize(
    ("path", "model"),
    [(CHAIN_CLIMATE, SiteClimate), (CHAIN_SOIL_SLOPE, SiteSoilSlope)],
    ids=["climate", "soil-slope"],
)
def test_CH01_chain_examples_load_and_name_the_rotation_example(path, model):
    text = path.read_text(encoding="utf-8")
    loaded = model.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert path.name.startswith("PLACEHOLDER_chain_")
    assert loaded.example_data is True
    rotation = rotation_document()
    assert rotation["example_data"] is True
    for field in IDENTITY_FIELDS:
        assert getattr(loaded, field) == rotation[field]


def test_CH02_climate_example_covers_a_whole_agricultural_year_for_every_quantity_read():
    month = start_month()
    by_quantity = {series.quantity: series for series in climate().daily_series}
    read = sorted({ep1.PRECIPITATION, *ep3.DAILY_INPUTS})
    assert set(read) <= set(by_quantity)
    years = covered()
    assert len(years) >= 1
    for name in read:
        series = by_quantity[name]
        dates = [day.date for day in series.days]
        for year in years:
            first, last = bounds_of(year, month)
            needed = [first + k * ONE_DAY for k in range((last - first).days + 1)]
            assert set(needed) <= set(dates), (name, year)
        assert all(day.value is not None and day.missing is None for day in series.days)
    # One time zone for every series read (C6.3).
    assert len({by_quantity[name].time_zone for name in read}) == 1


def test_CH03_example_values_are_plainly_placeholder():
    example = climate()
    for series in example.daily_series:
        assert len({day.value for day in series.days}) == 1, series.quantity
        assert series.source is not None and series.source.startswith(WORD)
    # The unit strings of the point are those of D55 (issue #77), the ones
    # EP3 accepts; the numbers stay illustrative and the source says so.
    assert POINT_UNITS_D55["latitude"] == ep3.POINT_UNITS.latitude_decimal_degrees
    assert POINT_UNITS_D55["elevation"] == ep3.POINT_UNITS.elevation
    for name, unit in POINT_UNITS_D55.items():
        value = getattr(example.point, name)
        assert value.unit == unit
        assert value.source.startswith(WORD)
        assert "not a real place" in value.source
    soil = soil_slope()
    for value in (soil.slope_length, soil.slope_steepness):
        assert value.value is not None
        assert value.source is not None and value.source.startswith(WORD)


# --- CH04 to CH06: through the real runner ------------------------------------


def test_CH04_runner_discovers_and_calls_ep2_then_ep1_and_ep3_with_the_catalogue():
    found = discover_engine_functions()
    assert found.build_rotation_calendar is not None, CALENDAR
    assert found.compute_soil_loss is ep1.compute_soil_loss, EROSION
    assert found.compute_water_deficit_exposure is ep3.compute_water_deficit_exposure, (
        WATER
    )
    catalogue: dict[str, dict] = {}
    outcome, calls = run_chain(catalogue)
    assert [name for name, _ in calls] == [
        CALENDAR.function,
        EROSION.function,
        WATER.function,
    ]
    (soil_loss_call,) = [kwargs for name, kwargs in calls if name == EROSION.function]
    assert soil_loss_call["parameters"] is catalogue
    for _, kwargs in calls[1:]:
        assert kwargs["calendar"] is outcome.calendar
        assert kwargs["climate"] == climate()
        assert kwargs["soil_slope"] == soil_slope()
    assert outcome.calendar.feasibility.feasible
    for field in IDENTITY_FIELDS:
        assert getattr(outcome.calendar, field) == rotation_document()[field]


def test_CH05_empty_catalogue_every_value_missing_with_its_reason():
    outcome, _ = run_chain({})
    assert outcome.result_missing is None
    result = outcome.result
    assert isinstance(result, ResultsPerRotation)
    assert_round_trip(result)
    assert outcome.values_present == 0

    soil_loss = result.soil_loss
    assert isinstance(soil_loss, SoilLossResults)  # not the not-built form
    assert [item.ag_year for item in soil_loss.annual] == ag_years_of_the_record()
    for item in [*soil_loss.annual, *soil_loss.monthly]:
        assert item.value is None
        assert_not_an_identity_absence(item.missing)
        if item.ag_year in covered():
            assert item.missing.reason != "NO_COVERAGE"
    for item in soil_loss.annual:
        if item.ag_year in covered():
            for pid in ep1.PARAMETER_IDS:
                assert f"'{pid}'" in item.missing.detail
    # The runner passes EP1's output unchanged.
    assert soil_loss == ep1.compute_soil_loss(
        calendar=outcome.calendar,
        climate=climate(),
        soil_slope=soil_slope(),
        parameters={},
    )

    assert_water_missing_for_every_covered_year(outcome, {})
    for module_id in (EROSION.module_id, WATER.module_id):
        status = module(outcome, module_id)
        assert status.state == "not_available"
        assert OTHER_FIELD not in (status.detail or "")


def test_CH06_complete_placeholder_catalogue_gives_the_product_of_equation_py():
    assert check_catalogue(marked_catalogue()) != []
    catalogue = complete_catalogue()
    assert check_catalogue(catalogue) == []
    numbers = placeholder_numbers()

    outcome, _ = run_chain(catalogue)
    result = outcome.result
    assert isinstance(result, ResultsPerRotation)
    assert_round_trip(result)
    soil_loss = result.soil_loss
    assert isinstance(soil_loss, SoilLossResults)

    # The main route of EP1 (docs/METHODS.md M1.2; D69, D84, USER-G): the
    # annual value is equation.py of the level of R, K, LS, the declared C and
    # P, and each month is the level times the climatological fraction of the
    # month, times K, LS, C and P; all computed again here.
    expected = expected_soil_loss(numbers)
    years = covered()
    computed = 0
    for item in soil_loss.annual:
        if item.ag_year not in years:
            assert item.value is None and item.missing.reason == "NO_COVERAGE"
            continue
        computed += 1
        assert item.missing is None
        assert item.value == pytest.approx(expected, rel=1e-9)
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        assert item.source is not None
        assert "DECLARED" in item.source
        for pid in ep1.PARAMETER_IDS:
            assert f"'{pid}'" in item.source
    assert computed == len(years) >= 1
    months = 0
    for item in soil_loss.monthly:
        if item.ag_year not in years:
            assert_not_an_identity_absence(item.missing)
            continue
        months += 1
        assert item.missing is None
        assert item.value == pytest.approx(
            expected_month(numbers, item.month), rel=1e-9
        )
        assert item.provenance == PROVENANCE_OF_SOIL_LOSS
        for pid in ep1.MONTHLY_EROSIVITY_IDS:
            assert f"'{pid}'" in item.source
    assert months == 12 * len(years)
    # The months of a covered year add up to its value (C1.2).
    for year in years:
        total = sum(i.value for i in soil_loss.monthly if i.ag_year == year)
        assert total == pytest.approx(expected, rel=1e-9)
    assert outcome.values_present == computed + months
    # Every annual and monthly value is present, so the module is available.
    assert module(outcome, EROSION.module_id).state == "available"
    # The runner passes EP1's output unchanged.
    assert soil_loss == ep1.compute_soil_loss(
        calendar=outcome.calendar,
        climate=climate(),
        soil_slope=soil_slope(),
        parameters=catalogue,
    )

    assert_water_missing_for_every_covered_year(outcome, catalogue)


# --- CH07: through the route ---------------------------------------------------


class ChainClimate:
    """A climate source that serves the chain example, marked ``example``."""

    source_id = "PLACEHOLDER_chain_climate"
    contract = "site_data_climate"

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=climate(),
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


@pytest.mark.parametrize(
    "catalogue", [dict, complete_catalogue], ids=["empty", "complete-placeholder"]
)
def test_CH07_route_answers_with_the_runner_result(catalogue):
    from fastapi.testclient import TestClient

    from api.main import create_app

    parameters = catalogue()
    series = precipitation()
    point = climate().point
    rotation = rotation_document()
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": point.latitude.value,
            "longitude": point.longitude.value,
        },
        "rotation": rotation,
    }
    app = create_app(
        [],
        climate=ChainClimate(),
        soil_slope=ExampleSoilSlopeSource(CHAIN_SOIL_SLOPE),
        settings=RunSettings(start_date=series.start_date, end_date=series.end_date),
        parameters=parameters,
    )
    response = TestClient(app).post("/api/rotations/run", json=body)
    assert response.status_code == 200, response.text
    answer = response.json()
    result = ResultsPerRotation.model_validate(answer["result"])
    outcome, _ = run_chain(parameters)
    assert result == outcome.result
    states = {m["id"]: m for m in answer["modules"]}
    for module_id in (EROSION.module_id, WATER.module_id):
        assert OTHER_FIELD not in (states[module_id].get("detail") or "")


# --- the README lists every case -----------------------------------------------


def test_readme_lists_every_chain_case():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    section = readme.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    codes = re.findall(
        r"^def test_(CH\d\d)_", Path(__file__).read_text(encoding="utf-8"), re.M
    )
    assert len(codes) == len(set(codes)) >= 1
    missing = [code for code in codes if f"| {code} |" not in section]
    assert missing == []
