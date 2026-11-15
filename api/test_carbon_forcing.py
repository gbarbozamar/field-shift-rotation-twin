"""Acceptance tests of the ``CarbonForcing`` producer ``api/carbon_forcing.py`` (unit l2/runner-amg).

Run with ``uv run pytest api/test_carbon_forcing.py`` from the repository root.

The inputs are the PLACEHOLDER examples of contracts/inputs/, with the
identifiers rewritten so that they name one field. No number is written
here: the only number the producer may carry is a soil property copied from
the soil-and-slope example. Crop identifiers written here are test data.

Status: PROPOSED test cases (blueprint section 3.7).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from api import carbon_forcing as producer
from api.carbon_forcing import (
    STOCK_UNIT,
    UNIT_OPEN,
    build_carbon_forcing,
    horizon_of,
    record_period,
    whole_ag_years,
)
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import Missing

EXAMPLES = Path(__file__).parent.parent / "contracts" / "inputs" / "examples"
ROTATION_EXAMPLE = (
    Path(__file__).parent.parent
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
# Test data: two crop identifiers that are quantity identifiers.
CROPS = ("placeholder_crop_a", "placeholder_crop_b")


def document(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


CHAIN_CLIMATE = document("PLACEHOLDER_chain_site_climate.json")
CHAIN_SOIL_SLOPE = document("PLACEHOLDER_chain_site_soil_slope.json")
SOIL_SLOPE = document("PLACEHOLDER_site_soil_slope.json")
ROTATION = json.loads(ROTATION_EXAMPLE.read_text(encoding="utf-8"))


def chain_calendar(
    *, crops: bool = True, start_month: Any = "keep"
) -> RotationCalendar:
    """The calendar example under the identifiers of the chain rotation."""
    calendar = document("PLACEHOLDER_rotation_calendar.json")
    for field in ("case_id", "field_id", "rotation_id"):
        calendar[field] = ROTATION[field]
    if crops:
        # The example's three components: two crops, the first one twice.
        for component, crop in zip(
            calendar["components"], (CROPS[0], CROPS[1], CROPS[0]), strict=True
        ):
            component["crop_id"] = crop
    if start_month is None:
        calendar["ag_year_start"] = {
            "month": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER"},
        }
    elif start_month != "keep":
        calendar["ag_year_start"]["month"] = start_month
    return RotationCalendar.model_validate(calendar)


def chain_climate(**update: Any) -> SiteClimate:
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    climate.update(update)
    return SiteClimate.model_validate(climate)


def chain_soil_slope(properties: list[dict[str, Any]] | None = None) -> SiteSoilSlope:
    soil = json.loads(json.dumps(CHAIN_SOIL_SLOPE))
    if properties is not None:
        soil["soil_properties"] = properties
    return SiteSoilSlope.model_validate(soil)


def chain_forcing(**kwargs: Any) -> CarbonForcing:
    forcing = build_carbon_forcing(
        kwargs.get("calendar", chain_calendar()),
        kwargs.get("climate", chain_climate()),
        kwargs.get("soil_slope", chain_soil_slope()),
    )
    assert isinstance(forcing, CarbonForcing), forcing
    return forcing


def values_in(value: Any) -> list[Any]:
    """Every ``value`` field of a dumped document that holds something."""
    if isinstance(value, dict):
        found = [value["value"]] if value.get("value") is not None else []
        return found + [n for v in value.values() for n in values_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in values_in(v)]
    return []


def the_period() -> tuple[dt.date, dt.date]:
    series = CHAIN_CLIMATE["daily_series"][0]
    return (
        dt.date.fromisoformat(series["start_date"]),
        dt.date.fromisoformat(series["end_date"]),
    )


# --- 1. the producer on the chain examples --------------------------------------


def test_the_forcing_loads_into_the_contract_and_round_trips():
    forcing = chain_forcing()
    text = json.dumps(forcing.model_dump(mode="json"))
    assert CarbonForcing.model_validate_json(text) == forcing
    assert forcing.contract == "carbon_forcing"
    assert forcing.example_data is True


def test_identifiers_come_from_the_calendar():
    calendar = chain_calendar()
    forcing = chain_forcing(calendar=calendar)
    assert (forcing.case_id, forcing.field_id, forcing.rotation_id) == (
        calendar.case_id,
        calendar.field_id,
        calendar.rotation_id,
    )


def test_the_horizon_is_the_whole_agricultural_years_of_the_record():
    calendar = chain_calendar()
    month = calendar.ag_year_start.month
    first_day, last_day = the_period()
    forcing = chain_forcing(calendar=calendar)
    years = whole_ag_years(month, first_day, last_day)
    assert years is not None
    assert forcing.horizon.start == YearMonth(year=years[0], month=month)
    # The chain record runs from the start month to the month before it.
    assert forcing.horizon.start == YearMonth(
        year=first_day.year, month=first_day.month
    )
    assert forcing.horizon.end == YearMonth(year=last_day.year, month=last_day.month)
    for series in [*forcing.annual_climate, *forcing.annual_carbon_inputs]:
        assert (series.first_ag_year, series.last_ag_year) == years


def test_every_value_is_missing_with_its_reason_and_nothing_is_zero():
    forcing = chain_forcing()
    dumped = forcing.model_dump(mode="json")
    assert values_in(dumped) == []  # no number at all, zero included
    assert forcing.soil_depth.value is None
    assert forcing.soil_depth.missing.reason == "NOT_AVAILABLE"
    assert "C1.6" in forcing.soil_depth.missing.detail
    assert forcing.soil_depth.unit == UNIT_OPEN
    climate = {series.quantity: series for series in forcing.annual_climate}
    assert set(climate) == {producer.MEAN_TEMPERATURE, producer.WATER_BALANCE}
    assert "D30" in climate["mean_temperature"].years[0].missing.detail
    assert "not defined" in climate["water_balance"].years[0].missing.detail
    for series in [*forcing.annual_climate, *forcing.annual_carbon_inputs]:
        assert series.years
        assert all(item.value is None for item in series.years)
        assert all(item.missing.reason == "NOT_AVAILABLE" for item in series.years)
        assert all(item.missing.detail for item in series.years)
        # All-missing series carry no provenance, source or range reason.
        assert (series.provenance, series.source, series.range_missing) == (
            None,
            None,
            None,
        )
        assert series.assumption is False
    for item in [*forcing.soil_properties, *forcing.starting_state]:
        assert item.value is None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert item.missing.detail
    assert [item.quantity for item in forcing.starting_state] == ["soil_organic_carbon"]
    assert forcing.starting_state[0].unit == STOCK_UNIT
    assert [item.quantity for item in forcing.soil_properties] == [
        "clay_content",
        "carbonate_content",
        "ph",
    ]
    # Monthly parts: run_amg reads annual series only.
    assert (forcing.climate, forcing.carbon_inputs, forcing.soil_cover) == ([], [], [])


def test_one_carbon_input_series_per_crop_with_the_crop_as_origin():
    forcing = chain_forcing()
    assert [(s.origin, s.quantity) for s in forcing.annual_carbon_inputs] == [
        (crop, crop) for crop in CROPS
    ]
    assert all(s.unit == STOCK_UNIT for s in forcing.annual_carbon_inputs)
    detail = forcing.annual_carbon_inputs[0].years[0].missing.detail
    assert "residue ledger" in detail


def test_a_crop_that_is_not_an_identifier_is_left_out_never_renamed():
    calendar = chain_calendar(crops=False)  # the example's own crop identifiers
    assert all(not c.crop_id.islower() for c in calendar.components)
    forcing = chain_forcing(calendar=calendar)
    assert forcing.annual_carbon_inputs == []


def test_a_soil_property_with_the_exact_quantity_is_copied_unchanged():
    present = {**SOIL_SLOPE["soil_properties"][0], "quantity": "clay_content"}
    near = {**SOIL_SLOPE["soil_properties"][0], "quantity": "clay"}
    soil = chain_soil_slope([present, near])
    forcing = chain_forcing(soil_slope=soil)
    by_quantity = {item.quantity: item for item in forcing.soil_properties}
    assert set(by_quantity) == {"clay_content", "carbonate_content", "ph"}
    assert by_quantity["clay_content"] == soil.soil_properties[0]
    assert by_quantity["carbonate_content"].value is None
    assert by_quantity["ph"].missing.reason == "NOT_AVAILABLE"


def test_the_producer_changes_no_argument():
    calendar, climate, soil = chain_calendar(), chain_climate(), chain_soil_slope()
    before = [m.model_dump(mode="json") for m in (calendar, climate, soil)]
    build_carbon_forcing(calendar, climate, soil)
    assert [m.model_dump(mode="json") for m in (calendar, climate, soil)] == before


@pytest.mark.parametrize("which", [0, 1, 2])
def test_an_argument_of_another_type_is_a_type_error(which):
    arguments: list[Any] = [chain_calendar(), chain_climate(), chain_soil_slope()]
    arguments[which] = arguments[which].model_dump(mode="json")
    with pytest.raises(TypeError):
        build_carbon_forcing(*arguments)


def test_the_identifiers_and_units_are_those_run_amg_reads():
    entry = pytest.importorskip("engine.amg.entry")
    reads = entry.FORCING_QUANTITIES
    assert (
        "annual_climate",
        producer.MEAN_TEMPERATURE,
    ) == reads["temperature"]
    assert ("annual_climate", producer.WATER_BALANCE) == reads["water_balance"]
    assert ("starting_state", producer.STARTING_CARBON) == reads["starting_carbon"]
    assert [("soil_properties", q) for q in producer.SOIL_PROPERTIES] == [
        reads["clay_content"],
        reads["carbonate_content"],
        reads["ph"],
    ]
    assert STOCK_UNIT == entry.STOCK_UNIT


# --- 2. the horizon: edge cases ---------------------------------------------------


def test_a_record_shorter_than_one_agricultural_year_gives_no_forcing():
    climate = chain_climate(
        daily_series=document("PLACEHOLDER_site_climate.json")["daily_series"]
    )
    answer = build_carbon_forcing(chain_calendar(), climate, chain_soil_slope())
    assert isinstance(answer, Missing)
    assert answer.reason == "NO_COVERAGE"
    assert "C5.5" in answer.detail


def test_a_record_that_starts_after_the_start_month_loses_that_year():
    # The chain record, start month one month later: no whole year is left.
    month = chain_calendar().ag_year_start.month
    answer = build_carbon_forcing(
        chain_calendar(start_month=month + 1), chain_climate(), chain_soil_slope()
    )
    assert isinstance(answer, Missing)
    assert answer.reason == "NO_COVERAGE"


def test_start_month_in_january():
    first_day, _ = the_period()
    # The chain days relabelled to begin on the first of January.
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    start = dt.date(first_day.year, 1, 1)
    for series in climate["daily_series"]:
        for offset, day in enumerate(series["days"]):
            day["date"] = (start + dt.timedelta(days=offset)).isoformat()
        series["start_date"] = series["days"][0]["date"]
        series["end_date"] = series["days"][-1]["date"]
    forcing = chain_forcing(
        calendar=chain_calendar(start_month=1),
        climate=SiteClimate.model_validate(climate),
    )
    assert forcing.horizon.start == YearMonth(year=start.year, month=1)
    assert forcing.horizon.end == YearMonth(year=start.year, month=12)
    assert forcing.annual_climate[0].first_ag_year == start.year


def test_whole_ag_years_and_horizon_of_the_record_of_d29():
    # D29: 2001-01-01 to 2024-12-31; with the chain start month and with January.
    first_day, last_day = dt.date(2001, 1, 1), dt.date(2024, 12, 31)
    month = chain_calendar().ag_year_start.month
    years = whole_ag_years(month, first_day, last_day)
    assert years == (first_day.year, last_day.year - 1)
    assert horizon_of(month, years).end == YearMonth(
        year=last_day.year, month=month - 1
    )
    assert whole_ag_years(1, first_day, last_day) == (first_day.year, last_day.year)
    assert horizon_of(1, (first_day.year, last_day.year)).end == YearMonth(
        year=last_day.year, month=12
    )


def test_an_absent_start_month_gives_no_forcing_with_its_reason():
    answer = build_carbon_forcing(
        chain_calendar(start_month=None), chain_climate(), chain_soil_slope()
    )
    assert isinstance(answer, Missing)
    assert answer.reason == "MISSING_INPUT"
    assert "ag_year_start" in answer.detail
    assert "NOT_DECLARED" in answer.detail


def test_a_record_without_daily_series_gives_no_forcing():
    answer = build_carbon_forcing(
        chain_calendar(), chain_climate(daily_series=[]), chain_soil_slope()
    )
    assert isinstance(answer, Missing)
    assert answer.reason == "MISSING_INPUT"
    assert "daily series" in answer.detail


def test_the_record_period_is_the_days_every_daily_series_covers():
    climate = SiteClimate.model_validate(document("PLACEHOLDER_site_climate.json"))
    series = climate.daily_series
    assert record_period(climate) == (
        max(s.start_date for s in series),
        min(s.end_date for s in series),
    )
    assert record_period(chain_climate()) == the_period()
    assert record_period(chain_climate(daily_series=[])) is None


@pytest.mark.parametrize("marked", [(), (0,), (1,), (2,), (0, 1, 2)])
def test_example_data_is_true_when_any_input_says_so(marked):
    documents = [
        chain_calendar().model_dump(mode="json"),
        chain_climate().model_dump(mode="json"),
        chain_soil_slope().model_dump(mode="json"),
    ]
    for index, item in enumerate(documents):
        item["example_data"] = index in marked
    forcing = chain_forcing(
        calendar=RotationCalendar.model_validate_json(json.dumps(documents[0])),
        climate=SiteClimate.model_validate_json(json.dumps(documents[1])),
        soil_slope=SiteSoilSlope.model_validate_json(json.dumps(documents[2])),
    )
    assert forcing.example_data is bool(marked)


def test_crops_left_out_are_the_crops_that_are_not_identifiers():
    assert producer.crops_left_out(chain_calendar()) == []
    calendar = chain_calendar(crops=False)
    expected = list(dict.fromkeys(c.crop_id for c in calendar.components))
    assert producer.crops_left_out(calendar) == expected
