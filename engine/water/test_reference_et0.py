"""Acceptance test of ``engine.water.daily_reference_evapotranspiration`` (D256).

The public function gives exactly the daily reference evapotranspiration EP3
uses. EP3's own series is read where EP3 calls the function of
``engine/water/et0/`` (``exposure.et0_days``), and compared day by day: the same days, the same numbers, the same reasons.

EXAMPLE DATA. The climate, the soil and the calendars are the PLACEHOLDER
chain examples of ``contracts/inputs/examples/``; the two calendars carry the
crops and the month and day of the two rotations of the demonstration (D128,
row USER-AP of D72), on PLACEHOLDER years. The catalogue is the one of the
repository (``params/records/``). No number is asserted.

The test of the wind bound of D82 (PC-4) uses a PLACEHOLDER test catalogue:
the repository's, with the record of ``penman_monteith_minimum_wind_speed``
replaced by a test record marked PLACEHOLDER whose value is not the one of
FAO-56. The readers of ``params.catalogue`` refuse a record with that word,
so the test passes the in-memory copy in which it is replaced by
``UNMARKED_TEST_ONLY``, as ``engine/water/test_exposure.py`` does (question
12 of ``params/README.md``). No constant of the method is written here.

Run from the repository root: ``python -m pytest engine/water/test_reference_et0.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing
from engine import water
from engine.water import (
    compute_water_deficit_exposure,
    daily_reference_evapotranspiration,
)
from engine.water import exposure as ep3
from engine.water import reference_et0 as public_module
from engine.water.et0.daily import WIND_SPEED_BOUND
from params.catalogue import load_folder

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
DOCS = ROOT / "contracts" / "ENTRYPOINTS.md"

# The two rotations of the demonstration (D128), on PLACEHOLDER years inside
# the calendar span below: (crop, start, end) per component.
DEMO_ROTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "soybean-winter-fallow": [("soybean", "2001-11-15", "2002-05-05")],
    "wheat-soybean-maize": [
        ("wheat", "2002-05-25", "2002-12-05"),
        ("soybean", "2002-12-10", "2003-05-10"),
        ("maize", "2003-09-20", "2004-04-20"),
    ],
}


def document(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def climate() -> SiteClimate:
    return SiteClimate.model_validate(document("PLACEHOLDER_chain_site_climate.json"))


def soil(of: SiteClimate) -> SiteSoilSlope:
    data = document("PLACEHOLDER_chain_site_soil_slope.json")
    data["case_id"], data["field_id"] = of.case_id, of.field_id
    return SiteSoilSlope.model_validate(data)


def calendar(name: str, of: SiteClimate) -> RotationCalendar:
    data = document("PLACEHOLDER_rotation_calendar.json")
    data["case_id"], data["field_id"] = of.case_id, of.field_id
    data["rotation_id"] = f"example-{name}"
    data["end_date"] = "2004-06-30"
    template = data["components"][0]
    components = []
    for position, (crop, start, end) in enumerate(DEMO_ROTATIONS[name], start=1):
        item = copy.deepcopy(template)
        item["component_id"] = f"example-component-{position}"
        item["crop_id"] = crop
        item["start"]["date"], item["end"]["date"] = start, end
        period = copy.deepcopy(template["periods"][0])
        period["start"]["date"], period["end"]["date"] = start, end
        item["periods"] = [period]
        components.append(item)
    data["components"] = components
    return RotationCalendar.model_validate(data)


def repository_catalogue() -> dict[str, dict]:
    records, problems = load_folder(ROOT / "params" / "records")
    assert problems == [], problems
    return records


def ep3_series(monkeypatch, calendar_, climate_, parameters) -> dict:
    """The daily ET0 EP3 runs its chain on, read where EP3 calls it."""
    seen: list[Any] = []
    real = ep3.et0_days

    def recording(*args: Any, **kwargs: Any) -> Any:
        days = real(*args, **kwargs)
        seen.append(days)
        return days

    monkeypatch.setattr(ep3, "et0_days", recording)
    compute_water_deficit_exposure(
        calendar_, climate_, soil(climate_), parameters=parameters
    )
    monkeypatch.undo()
    assert len(seen) == 1, "EP3 computes its daily ET0 once per call"
    return {item.date: item.value for item in seen[0]}


def assert_same(public: dict, of_ep3: dict) -> None:
    assert list(public) == list(of_ep3)
    for day, value in of_ep3.items():
        given = public[day]
        if isinstance(value, Missing):
            assert isinstance(given, Missing), day
            assert (given.reason, given.detail) == (value.reason, value.detail), day
        else:
            assert given == value, day


@pytest.mark.parametrize("rotation", sorted(DEMO_ROTATIONS))
def test_the_series_is_the_one_ep3_uses_day_by_day(monkeypatch, rotation):
    climate_ = climate()
    parameters = repository_catalogue()
    of_ep3 = ep3_series(monkeypatch, calendar(rotation, climate_), climate_, parameters)
    public = daily_reference_evapotranspiration(climate_, parameters=parameters)
    assert any(isinstance(value, float) for value in public.values()), (
        "the comparison needs days with a number"
    )
    assert_same(public, of_ep3)


@pytest.mark.parametrize(
    "parameter_id",
    [
        next(
            f"{group}_{name}"
            for group, names in ep3.ET0_PARAMETERS.items()
            for name in names
        ),
        *(
            parameter_id
            for names in ep3.ET0_BOUND_PARAMETERS.values()
            for parameter_id in names.values()
        ),
    ],
)
def test_a_missing_constant_or_bound_gives_the_reason_ep3_gives(
    monkeypatch, parameter_id
):
    climate_ = climate()
    parameters = {
        key: record
        for key, record in repository_catalogue().items()
        if record.get("id") != parameter_id
    }
    assert len(parameters) == len(repository_catalogue()) - 1, parameter_id
    of_ep3 = ep3_series(
        monkeypatch, calendar("soybean-winter-fallow", climate_), climate_, parameters
    )
    public = daily_reference_evapotranspiration(climate_, parameters=parameters)
    assert_same(public, of_ep3)
    missing = [value for value in public.values() if isinstance(value, Missing)]
    assert len(missing) == len(public), "every day misses the record"
    assert all(value.reason == "MISSING_INPUT" for value in missing)
    assert all(parameter_id in value.detail for value in missing)


def test_an_empty_catalogue_names_the_records_as_ep3_does(monkeypatch):
    climate_ = climate()
    of_ep3 = ep3_series(
        monkeypatch, calendar("wheat-soybean-maize", climate_), climate_, {}
    )
    assert_same(daily_reference_evapotranspiration(climate_, parameters={}), of_ep3)


# --- the wind bound of D82 (PC-4), on a PLACEHOLDER test catalogue ----------

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
WIND_BOUND_RECORD = ep3.ET0_BOUND_PARAMETERS["wind_speed_bound"]["lower_bound"]


def example_winds(climate_: SiteClimate) -> list[float]:
    """The numbers of the wind series of the example climate."""
    (series,) = [s for s in climate_.daily_series if s.quantity == "wind_speed_2m"]
    return [day.value for day in series.days if day.missing is None]


def unmarked(item: Any) -> Any:
    """The in-memory copy in which the word PLACEHOLDER is replaced."""
    return json.loads(json.dumps(item).replace(MARK, UNMARKED))


def catalogue_with_wind_bound(value: float) -> dict[str, dict]:
    """The repository's catalogue, its wind-bound record replaced by a test record.

    ``value`` is a test placeholder, never the value of FAO-56; the record
    says so with the word PLACEHOLDER, and the unmarked copy is returned.
    """
    records = {
        key: record
        for key, record in repository_catalogue().items()
        if record.get("id") != WIND_BOUND_RECORD
    }
    assert len(records) == len(repository_catalogue()) - 1
    test_record = {
        "id": WIND_BOUND_RECORD,
        "scope": {},
        "value": value,
        "unit": "m s-1",
        "range": None,
        "range_missing_reason": "PLACEHOLDER: a test record has no range",
        "citation": {
            "reference": "PLACEHOLDER reference. This is not a publication.",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
        "note": "PLACEHOLDER test value of the wind bound, not the value of FAO-56",
    }
    records[f"{MARK}/{WIND_BOUND_RECORD}.json"] = test_record
    return unmarked(records)


def public_days(monkeypatch, climate_: SiteClimate, parameters: dict) -> dict:
    """The public series, with the steps of each day, read where it calls et0/."""
    seen: list[Any] = []
    real = public_module.reference_evapotranspiration_from_climate_with_bounds

    def recording(*args: Any, **kwargs: Any) -> Any:
        days = real(*args, **kwargs)
        seen.append(days)
        return days

    monkeypatch.setattr(
        public_module,
        "reference_evapotranspiration_from_climate_with_bounds",
        recording,
    )
    public = daily_reference_evapotranspiration(climate_, parameters=parameters)
    monkeypatch.undo()
    assert len(seen) == 1
    steps = {item.date: item.steps for item in seen[0]}
    assert list(public) == list(steps)
    for day, value in public.items():
        assert value == steps[day].reference_evapotranspiration, day
    return {day: (public[day], steps[day]) for day in public}


def test_a_wind_bound_above_the_example_wind_changes_the_wind_and_the_et0(
    monkeypatch,
):
    """D82 (PC-4): a lower bound above the day's wind replaces it in Eq. 6.

    With the test bound above every wind of the example, every day whose wind
    is a number reports that the bound changed it (``bounds_changed``), and
    its ET0 differs from the one with the bound at 0.0, which changes no wind
    of the example. EP3 gives the same series with the same test catalogue.
    The mutant "bound set to 0.0" fails it.
    """
    climate_ = climate()
    winds = example_winds(climate_)
    assert winds and min(winds) >= 0.0, "the example has winds, none below zero"
    # PLACEHOLDER test values, not values of the method: twice the largest
    # wind of the example, so the bound lies above every day's wind; and
    # 0.0, the lower bound that leaves a wind of zero or more unchanged.
    above = 2 * max(winds)
    assert above > max(winds)
    at_zero = 0.0
    bounded = public_days(monkeypatch, climate_, catalogue_with_wind_bound(above))
    unbounded = public_days(monkeypatch, climate_, catalogue_with_wind_bound(at_zero))
    assert list(bounded) == list(unbounded)
    compared = 0
    for day, (value, steps) in bounded.items():
        value_at_zero, steps_at_zero = unbounded[day]
        assert WIND_SPEED_BOUND not in steps_at_zero.bounds_changed, day
        if isinstance(steps_at_zero.wind_speed_2m, Missing):
            continue
        assert WIND_SPEED_BOUND in steps.bounds_changed, day
        assert steps.wind_speed_2m == above, day
        assert steps_at_zero.wind_speed_2m < above, day
        if isinstance(value, float) and isinstance(value_at_zero, float):
            assert value != value_at_zero, day
            compared += 1
    assert compared > 0, "the comparison needs days with an ET0"
    assert_same(
        {day: value for day, (value, _) in bounded.items()},
        ep3_series(
            monkeypatch,
            calendar("soybean-winter-fallow", climate_),
            climate_,
            catalogue_with_wind_bound(above),
        ),
    )


def test_wrong_types_raise_type_error():
    with pytest.raises(TypeError, match="climate"):
        daily_reference_evapotranspiration(object(), parameters={})
    with pytest.raises(TypeError, match="parameters"):
        daily_reference_evapotranspiration(climate(), parameters=[])


def test_it_is_found_by_name_beside_ep3_and_listed_in_entrypoints():
    assert (
        water.daily_reference_evapotranspiration is daily_reference_evapotranspiration
    )
    assert "daily_reference_evapotranspiration" in water.__all__
    text = DOCS.read_text(encoding="utf-8")
    assert "engine.water.daily_reference_evapotranspiration" in text
    assert "D256" in text
