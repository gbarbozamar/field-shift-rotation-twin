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
import statistics
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


def test_every_value_but_the_decided_ones_is_missing_with_its_reason():
    # The decided values: the yearly mean temperature (D118), the soil depth
    # of D180, and the monthly rainfall and mean temperature of D220. The
    # monthly potential evapotranspiration and the yearly water balance of
    # D181 are missing here: no daily reference evapotranspiration is passed.
    forcing = chain_forcing()
    dumped = forcing.model_dump(mode="json")
    dumped["annual_climate"] = [
        s for s in dumped["annual_climate"] if s["quantity"] != "mean_temperature"
    ]
    dumped["climate"] = [
        s
        for s in dumped["climate"]
        if s["quantity"] not in ("rainfall", "mean_temperature")
    ]
    dumped.pop("soil_depth")
    assert values_in(dumped) == []  # no number at all, zero included
    assert (forcing.soil_depth.value, forcing.soil_depth.unit) == (20.0, "cm")
    climate = {series.quantity: series for series in forcing.annual_climate}
    assert set(climate) == {producer.MEAN_TEMPERATURE, producer.WATER_BALANCE}
    assert "D181" in climate["water_balance"].years[0].missing.detail
    assert "did not pass" in climate["water_balance"].years[0].missing.detail
    assert climate["water_balance"].unit == "m"  # the unit D181 writes
    assert "D122" in forcing.annual_carbon_inputs[0].years[0].missing.detail
    for series in [climate["water_balance"], *forcing.annual_carbon_inputs]:
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
    for item in forcing.soil_properties:
        assert item.value is None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert "D120" in item.missing.detail
    for item in forcing.starting_state:
        assert item.value is None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert "D121" in item.missing.detail
    assert [item.quantity for item in forcing.starting_state] == ["soil_organic_carbon"]
    assert forcing.starting_state[0].unit == STOCK_UNIT
    assert [item.quantity for item in forcing.soil_properties] == [
        "clay_content",
        "carbonate_content",
        "ph",
        "soil_cn_ratio",
    ]
    # Monthly parts: the climate of RothC (D220); the monthly carbon inputs
    # (D221) and the cover (D222) are not written by this producer yet.
    assert [series.quantity for series in forcing.climate] == [
        "rainfall",
        "potential_evapotranspiration",
        "mean_temperature",
    ]
    assert (forcing.carbon_inputs, forcing.soil_cover) == ([], [])


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
    assert set(by_quantity) == set(producer.SOIL_PROPERTIES)
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
        reads["cn_ratio"],
    ]
    # Every soil property run_amg reads is one the producer writes, and no other.
    assert {q for part, q in reads.values() if part == "soil_properties"} == set(
        producer.SOIL_PROPERTIES
    )
    assert reads["cn_ratio"] == ("soil_properties", producer.SOIL_CN_RATIO)
    assert STOCK_UNIT == entry.STOCK_UNIT


def test_d193_the_soil_cn_ratio_is_copied_unchanged_or_missing_naming_d193():
    # A site file without soil_cn_ratio: missing, NOT_AVAILABLE, naming D193.
    by_quantity = {item.quantity: item for item in chain_forcing().soil_properties}
    absent = by_quantity["soil_cn_ratio"]
    assert absent.value is None
    assert absent.unit == UNIT_OPEN
    assert absent.missing.reason == "NOT_AVAILABLE"
    assert "D193" in absent.missing.detail
    assert "soil_cn_ratio" in absent.missing.detail
    # The other three keep the text of D120, which does not name D193.
    for quantity in ("clay_content", "carbonate_content", "ph"):
        assert "D193" not in by_quantity[quantity].missing.detail
    # With the exact quantity it is copied unchanged, like the other three
    # (the number is the example's, a PLACEHOLDER); a near name is not read.
    present = {
        **SOIL_SLOPE["soil_properties"][0],
        "quantity": "soil_cn_ratio",
        "unit": "dimensionless",
    }
    near = {**SOIL_SLOPE["soil_properties"][0], "quantity": "cn_ratio"}
    soil = chain_soil_slope([near, present])
    by_quantity = {
        item.quantity: item for item in chain_forcing(soil_slope=soil).soil_properties
    }
    assert set(by_quantity) == set(producer.SOIL_PROPERTIES)
    assert by_quantity["soil_cn_ratio"] == soil.soil_properties[1]
    assert by_quantity["clay_content"].value is None


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


# --- 3. D118: mean_temperature from the daily mean of D30 -------------------------

# Plainly unreal placeholder temperatures, for the synthetic record only.
HIGH, LOW = 1234.5, 1000.25


def temperature_climate(
    *, years: int = 2, gap: tuple[str, int] | None = None, low_unit: str | None = None
) -> SiteClimate:
    """The chain climate with two temperature series of ``years`` agricultural years."""
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    first_day, _ = the_period()
    after = dt.date(first_day.year + years, first_day.month, first_day.day)
    count = (after - first_day).days
    kept = []
    for series in climate["daily_series"]:
        if series["quantity"] not in (
            producer.TEMPERATURE_MAX,
            producer.TEMPERATURE_MIN,
        ):
            continue
        value = HIGH if series["quantity"] == producer.TEMPERATURE_MAX else LOW
        series["days"] = [
            {"date": (first_day + dt.timedelta(days=i)).isoformat(), "value": value}
            for i in range(count)
        ]
        series["start_date"] = series["days"][0]["date"]
        series["end_date"] = series["days"][-1]["date"]
        if gap is not None and gap[0] == series["quantity"]:
            series["days"][gap[1]] = {
                "date": series["days"][gap[1]]["date"],
                "value": None,
                "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
            }
        if low_unit is not None and series["quantity"] == producer.TEMPERATURE_MIN:
            series["unit"] = low_unit
        kept.append(series)
    climate["daily_series"] = list(reversed(kept))  # read by quantity, not position
    return SiteClimate.model_validate(climate)


def mean_temperature(forcing: CarbonForcing):
    (series,) = [s for s in forcing.annual_climate if s.quantity == "mean_temperature"]
    return series


def test_d118_is_the_yearly_mean_of_the_daily_mean_of_d30():
    climate = temperature_climate()
    series = mean_temperature(chain_forcing(climate=climate))
    expected = statistics.fmean([(HIGH + LOW) / 2])  # every day the same
    assert [item.value for item in series.years] == [expected, expected]
    assert series.unit == climate.daily_series[0].unit
    assert series.provenance == "DERIVED"
    assert "D118" in series.source and "D30" in series.source
    assert climate.daily_series[0].source in series.source
    assert series.range_missing is not None


def test_d118_on_the_chain_example_uses_every_day_of_the_year():
    climate = chain_climate()
    series = {s.quantity: s for s in climate.daily_series}
    high = [d.value for d in series[producer.TEMPERATURE_MAX].days]
    low = [d.value for d in series[producer.TEMPERATURE_MIN].days]
    expected = statistics.fmean([(h + lo) / 2 for h, lo in zip(high, low, strict=True)])
    (item,) = mean_temperature(chain_forcing()).years
    assert item.value == pytest.approx(expected)


@pytest.mark.parametrize("which", ["air_temperature_max_2m", "air_temperature_min_2m"])
def test_d118_a_year_with_one_missing_day_is_missing_and_not_filled(which):
    climate = temperature_climate(gap=(which, 3))
    first, second = mean_temperature(chain_forcing(climate=climate)).years
    assert first.value is None
    assert first.missing.reason == "MISSING_INPUT"
    assert which in first.missing.detail
    assert second.value is not None  # the other year is whole


def test_d118_inputs_in_different_units_give_every_year_missing():
    climate = temperature_climate(low_unit="PLACEHOLDER_other_unit")
    series = mean_temperature(chain_forcing(climate=climate))
    assert all(item.value is None for item in series.years)
    assert all(item.missing.reason == "NOT_COMPUTABLE" for item in series.years)
    assert series.provenance is None


def test_d118_an_absent_input_series_gives_every_year_missing():
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    climate["daily_series"] = [
        s for s in climate["daily_series"] if s["quantity"] != producer.TEMPERATURE_MIN
    ]
    series = mean_temperature(
        chain_forcing(climate=SiteClimate.model_validate(climate))
    )
    assert all(item.missing.reason == "MISSING_INPUT" for item in series.years)
    assert producer.TEMPERATURE_MIN in series.years[0].missing.detail


def test_daily_mean_temperature_is_the_mean_of_maximum_and_minimum():
    assert producer.daily_mean_temperature(HIGH, LOW) == (HIGH + LOW) / 2


# --- 4. D121: the starting soil organic carbon ----------------------------------


def soil_item(quantity: str, unit: str) -> dict[str, Any]:
    return {**SOIL_SLOPE["soil_properties"][0], "quantity": quantity, "unit": unit}


def test_d121_copied_unchanged_in_the_stock_unit():
    soil = chain_soil_slope([soil_item("soil_organic_carbon", STOCK_UNIT)])
    (state,) = chain_forcing(soil_slope=soil).starting_state
    assert state.model_dump() == soil.soil_properties[0].model_dump()


def test_d121_another_unit_is_never_converted():
    soil = chain_soil_slope([soil_item("soil_organic_carbon", "PLACEHOLDER_percent")])
    (state,) = chain_forcing(soil_slope=soil).starting_state
    assert state.value is None
    assert state.unit == STOCK_UNIT
    assert state.missing.reason == "NOT_COMPUTABLE"
    assert "D121" in state.missing.detail


def test_d121_absent_is_missing_naming_d121():
    (state,) = chain_forcing().starting_state
    assert state.missing.reason == "NOT_AVAILABLE"
    assert "D121" in state.missing.detail


# --- D220: the monthly climate of RothC; D180: the soil depth ----------------------
#
# The chain climate example holds one agricultural year, 2001-07-01 to
# 2002-06-30, every value 1234.5 (PLACEHOLDER). The hand counts below use
# that, or a copy of it with some days changed; the numbers mean nothing.


def with_days(quantity: str, changes: dict[str, dict[str, Any]]) -> SiteClimate:
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    for series in climate["daily_series"]:
        if series["quantity"] == quantity:
            series["days"] = [
                {"date": day["date"], **changes[day["date"]]}
                if day["date"] in changes
                else day
                for day in series["days"]
            ]
    return SiteClimate.model_validate(climate)


def monthly(forcing: CarbonForcing, quantity: str):
    (series,) = [item for item in forcing.climate if item.quantity == quantity]
    return series, {(item.year, item.month): item for item in series.months}


def forcing_with(climate: SiteClimate | None = None, **kwargs: Any) -> CarbonForcing:
    built = build_carbon_forcing(
        chain_calendar(), climate or chain_climate(), chain_soil_slope(), **kwargs
    )
    assert isinstance(built, CarbonForcing), built
    return built


def every_day_of_the_record() -> list[dt.date]:
    first, last = the_period()
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


def test_d180_the_soil_depth_is_20_cm_with_its_source():
    depth = chain_forcing().soil_depth
    assert (depth.value, depth.unit, depth.provenance) == (20.0, "cm", "DECLARED")
    assert "D180" in depth.source
    assert depth.missing is None
    assert depth.range_missing.reason == "NOT_AVAILABLE"


def test_d220_the_months_follow_the_horizon_and_no_pan_series_is_written():
    forcing = chain_forcing()
    assert [series.quantity for series in forcing.climate] == [
        "rainfall",
        "potential_evapotranspiration",
        "mean_temperature",
    ]
    for series in forcing.climate:
        assert (series.start, series.end) == (
            forcing.horizon.start,
            forcing.horizon.end,
        )
        assert len(series.months) == 12
    assert "open_pan_evaporation" not in {s.quantity for s in forcing.climate}


def test_d220_rainfall_is_the_sum_of_the_days_of_each_month_in_mm():
    # July 2001: 31 days of 1234.5 = 38269.5. February 2002: 28 days, of which
    # 2002-02-10 is changed to 0.5: 27 x 1234.5 + 0.5 = 33331.5 + 0.5 = 33332.0.
    climate = with_days("precipitation", {"2002-02-10": {"value": 0.5}})
    series, by_month = monthly(forcing_with(climate), "rainfall")
    assert series.unit == "mm"
    assert by_month[(2001, 7)].value == 38269.5
    assert by_month[(2002, 2)].value == 33332.0
    assert series.provenance == "DERIVED"
    assert "D220" in series.source and "precipitation" in series.source


def test_d220_a_month_with_a_missing_day_is_missing_and_never_filled():
    climate = with_days(
        "precipitation",
        {
            "2001-09-15": {
                "value": None,
                "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
            }
        },
    )
    _, by_month = monthly(forcing_with(climate), "rainfall")
    september = by_month[(2001, 9)]
    assert september.value is None
    assert september.missing.reason == "NO_COVERAGE"
    assert "2001-09-15" in september.missing.detail
    assert by_month[(2001, 8)].value == 31 * 1234.5  # the other months stay
    assert by_month[(2001, 10)].value == 31 * 1234.5


def test_d220_rainfall_in_another_unit_is_not_computable():
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    for series in climate["daily_series"]:
        if series["quantity"] == "precipitation":
            series["unit"] = "PLACEHOLDER_unit"
    _, by_month = monthly(forcing_with(SiteClimate.model_validate(climate)), "rainfall")
    assert all(item.value is None for item in by_month.values())
    assert {item.missing.reason for item in by_month.values()} == {"NOT_COMPUTABLE"}


def test_d220_potential_evapotranspiration_is_the_sum_of_the_daily_et0():
    # 2.0 every day, except 2001-11-03 at 0.25: November 30 x 2.0 - 2.0 + 0.25
    # = 58.25; December 31 x 2.0 = 62.0.
    et0 = {day: 2.0 for day in every_day_of_the_record()}
    et0[dt.date(2001, 11, 3)] = 0.25
    series, by_month = monthly(
        forcing_with(reference_evapotranspiration=et0), "potential_evapotranspiration"
    )
    assert series.unit == "mm"
    assert by_month[(2001, 11)].value == 58.25
    assert by_month[(2001, 12)].value == 62.0
    assert series.provenance == "DERIVED"
    # FAO-56 ET0 stands in for the PET of RothC (D80, D220).
    assert "D80" in series.source and "D220" in series.source
    assert "stands in" in series.source and "D44" in series.source


def test_d220_a_day_of_et0_missing_or_absent_makes_its_month_missing():
    et0 = {day: 2.0 for day in every_day_of_the_record()}
    et0[dt.date(2002, 1, 5)] = Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER: a record"
    )
    del et0[dt.date(2002, 3, 9)]
    _, by_month = monthly(
        forcing_with(reference_evapotranspiration=et0), "potential_evapotranspiration"
    )
    assert by_month[(2002, 1)].value is None
    assert by_month[(2002, 1)].missing.reason == "MISSING_INPUT"
    assert "2002-01-05" in by_month[(2002, 1)].missing.detail
    assert by_month[(2002, 3)].missing.reason == "NO_COVERAGE"
    assert by_month[(2002, 2)].value == 28 * 2.0


def test_d220_without_et0_every_month_is_missing_with_its_reason():
    series, by_month = monthly(chain_forcing(), "potential_evapotranspiration")
    assert series.unit == "mm"
    assert {item.missing.reason for item in by_month.values()} == {"NOT_AVAILABLE"}
    assert "did not pass" in by_month[(2001, 7)].missing.detail
    assert (series.provenance, series.source, series.range_missing) == (
        None,
        None,
        None,
    )
    not_computed = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER: no record")
    _, by_month = monthly(
        forcing_with(reference_evapotranspiration=not_computed),
        "potential_evapotranspiration",
    )
    assert {item.missing.reason for item in by_month.values()} == {"MISSING_INPUT"}
    assert "PLACEHOLDER: no record" in by_month[(2001, 7)].missing.detail


def test_d220_mean_temperature_is_the_mean_of_the_daily_means_in_their_unit():
    # Maximum 1234.5 and minimum 1234.5 every day, except 2001-07-10 with a
    # maximum of 1240.5: that day's mean is 1237.5, so July is
    # (30 x 1234.5 + 1237.5) / 31 = 1234.5 + 3 / 31.
    climate = with_days("air_temperature_max_2m", {"2001-07-10": {"value": 1240.5}})
    series, by_month = monthly(forcing_with(climate), "mean_temperature")
    assert series.unit == "degC"
    assert by_month[(2001, 7)].value == pytest.approx(1234.5 + 3 / 31)
    assert by_month[(2001, 8)].value == 1234.5
    assert "D30" in series.source and "D220" in series.source


# --- D221: the monthly carbon inputs, copied unchanged ------------------------------


def a_monthly_series(horizon, origin: str = "placeholder_crop_aboveground"):
    from contracts.carbon_forcing import CarbonInputSeries

    months = []
    year, month = horizon.start.year, horizon.start.month
    while (year, month) <= (horizon.end.year, horizon.end.month):
        months.append({"year": year, "month": month, "value": 1234.5})
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return CarbonInputSeries.model_validate(
        {
            "origin": origin,
            "quantity": f"{origin}_carbon_input",
            "unit": STOCK_UNIT,
            "provenance": "SIMULATED",
            "source": "PLACEHOLDER",
            "range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
            "start": horizon.start.model_dump(),
            "end": horizon.end.model_dump(),
            "months": months,
        }
    )


def test_d221_the_monthly_carbon_inputs_are_copied_unchanged():
    horizon = chain_forcing().horizon
    monthly = [
        a_monthly_series(horizon),
        a_monthly_series(horizon, "placeholder_crop_belowground"),
    ]
    forcing = forcing_with(monthly_carbon_inputs=monthly)
    assert forcing.carbon_inputs == monthly
    assert all(a is b for a, b in zip(forcing.carbon_inputs, monthly))


def test_d221_a_monthly_series_over_other_months_is_a_defect():
    horizon = chain_forcing().horizon
    other = horizon.model_copy(
        update={
            "start": YearMonth(year=horizon.start.year - 1, month=horizon.start.month)
        }
    )
    with pytest.raises(TypeError, match="months of the forcing horizon"):
        forcing_with(monthly_carbon_inputs=[a_monthly_series(other)])


# --- 7. D181: the yearly water balance of AMG -----------------------------------
#
# A synthetic record of two agricultural years from 2001-07-01 (the chain start
# month), precipitation only: 3.0 mm a day in the first year and 1.0 in the
# second, except 3.5 on 2002-06-30 (the last day of the first year) and 0.25
# on 2002-07-01 (the first day of the second). The daily ET0 is 2.0 every day.
# Both years have 365 days. Hand counts, in mm then m (D181: mm / 1000):
#   2001: 364 x 3.0 + 3.5 = 1095.5; minus 365 x 2.0 = 730.0: 365.5 mm, 0.3655 m.
#   2002: 0.25 + 364 x 1.0 = 364.25; minus 730.0: -365.75 mm, -0.36575 m,
#         below -290 mm, the low end of the range of D181: kept, and named.
# The numbers mean nothing; they are chosen so that a sum, a sign, the unit
# and the boundary of the agricultural year each change the answer.

WATER_DAYS = [dt.date(2001, 7, 1) + dt.timedelta(days=n) for n in range(730)]


def water_climate(changes: dict[str, dict[str, Any]] | None = None) -> SiteClimate:
    climate = json.loads(json.dumps(CHAIN_CLIMATE))
    (series,) = [s for s in climate["daily_series"] if s["quantity"] == "precipitation"]
    values = {day: 3.0 if day < dt.date(2002, 7, 1) else 1.0 for day in WATER_DAYS}
    values[dt.date(2002, 6, 30)] = 3.5
    values[dt.date(2002, 7, 1)] = 0.25
    series["days"] = [
        {"date": day.isoformat(), "value": values[day]} for day in WATER_DAYS
    ]
    # SiteClimate keeps every day of a daily series (a day without data stays
    # in it as missing), so a day absent inside the record can only be a day
    # of the runner's ET0 mapping; that case is the second one below.
    for day, change in (changes or {}).items():
        index = WATER_DAYS.index(dt.date.fromisoformat(day))
        series["days"][index] = {"date": day, **change}
    series["start_date"] = WATER_DAYS[0].isoformat()
    series["end_date"] = WATER_DAYS[-1].isoformat()
    climate["daily_series"] = [series]
    return SiteClimate.model_validate(climate)


def water_et0() -> dict[dt.date, Any]:
    return {day: 2.0 for day in WATER_DAYS}


def water_balance(forcing: CarbonForcing):
    (series,) = [s for s in forcing.annual_climate if s.quantity == "water_balance"]
    return series, {item.ag_year: item for item in series.years}


def test_d181_the_water_balance_is_the_yearly_sum_of_p_minus_et0_in_m():
    forcing = forcing_with(water_climate(), reference_evapotranspiration=water_et0())
    series, by_year = water_balance(forcing)
    assert (series.first_ag_year, series.last_ag_year) == (2001, 2002)
    assert series.unit == "m"
    assert by_year[2001].value == 365.5 / 1000  # a sum, in m, positive
    assert by_year[2002].value == -365.75 / 1000  # negative: ET0 above rain
    assert series.provenance == "DERIVED"
    assert "D181" in series.source and "D44" in series.source
    assert "Penman (1948)" in series.source and "declared adaptation" in series.source
    assert "IW = 0" in series.source
    assert series.range_missing.reason == "NOT_AVAILABLE"


def test_d181_the_agricultural_year_boundary_splits_the_days():
    # 2002-06-30 belongs to 2001, 2002-07-01 to 2002: moving either day's
    # change across the boundary would change both years by hand count.
    _, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=water_et0())
    )
    assert by_year[2001].value * 1000 == pytest.approx(364 * 3.0 + 3.5 - 730.0)
    assert by_year[2002].value * 1000 == pytest.approx(0.25 + 364 * 1.0 - 730.0)


def test_d181_a_year_outside_the_calibrated_range_keeps_its_number_and_is_named():
    series, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=water_et0())
    )
    assert by_year[2002].value is not None and by_year[2002].missing is None
    assert "-290 to 595 mm yr-1" in series.source
    assert "Clivot et al. 2019, p. 107" in series.source
    outside = series.source.split("Outside the calibrated range", 1)[1]
    assert "2002" in outside and "2001" not in outside


def test_d181_every_year_inside_the_range_says_so():
    et0 = water_et0()
    for day in WATER_DAYS[365:]:
        et0[day] = 1.0  # 2002: 364.25 - 365.0 = -0.75 mm, inside the range
    series, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=et0)
    )
    assert by_year[2002].value == pytest.approx(-0.75 / 1000)
    assert "Every year with a value lies inside that range" in series.source
    assert "Outside the calibrated range" not in series.source


def test_d181_a_missing_or_absent_day_makes_its_year_missing_never_zero():
    held = {
        "value": None,
        "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
    }
    _, by_year = water_balance(
        forcing_with(
            water_climate({"2001-10-02": held}),
            reference_evapotranspiration=water_et0(),
        )
    )
    assert by_year[2001].value is None
    assert by_year[2001].missing.reason == "NO_COVERAGE"
    assert "2001-10-02" in by_year[2001].missing.detail
    assert "precipitation" in by_year[2001].missing.detail
    assert by_year[2002].value == -365.75 / 1000  # the other year stays

    et0 = water_et0()
    del et0[dt.date(2003, 1, 15)]
    _, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=et0)
    )
    assert by_year[2002].value is None
    assert by_year[2002].missing.reason == "NO_COVERAGE"
    assert "2003-01-15" in by_year[2002].missing.detail
    assert by_year[2001].value == 365.5 / 1000

    et0 = water_et0()
    et0[dt.date(2001, 8, 8)] = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER")
    _, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=et0)
    )
    assert by_year[2001].value is None
    assert by_year[2001].missing.reason == "MISSING_INPUT"
    assert "2001-08-08" in by_year[2001].missing.detail


def test_d181_without_et0_or_precipitation_every_year_is_missing_with_its_reason():
    series, by_year = water_balance(forcing_with(water_climate()))
    assert {item.missing.reason for item in by_year.values()} == {"NOT_AVAILABLE"}
    assert "did not pass" in by_year[2001].missing.detail
    assert (series.provenance, series.source) == (None, None)

    not_computed = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER: no record")
    _, by_year = water_balance(
        forcing_with(water_climate(), reference_evapotranspiration=not_computed)
    )
    assert {item.missing.reason for item in by_year.values()} == {"MISSING_INPUT"}
    assert "PLACEHOLDER: no record" in by_year[2001].missing.detail

    other_unit = json.loads(water_climate().model_dump_json())
    other_unit["daily_series"][0]["unit"] = "PLACEHOLDER_unit"
    _, by_year = water_balance(
        forcing_with(
            SiteClimate.model_validate(other_unit),
            reference_evapotranspiration=water_et0(),
        )
    )
    assert {item.missing.reason for item in by_year.values()} == {"NOT_COMPUTABLE"}
