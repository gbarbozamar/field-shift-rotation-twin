"""Acceptance test of ``engine.water.daily_reference_evapotranspiration`` (D256).

The public function gives exactly the daily reference evapotranspiration EP3
uses. EP3's own series is read where EP3 calls the function of
``engine/water/et0/`` (``exposure.et0_days``), and compared day by day: the same days, the same numbers, the same reasons.

EXAMPLE DATA. The climate, the soil and the calendars are the PLACEHOLDER
chain examples of ``contracts/inputs/examples/``; the two calendars carry the
crops and the month and day of the two rotations of the demonstration (D128,
row USER-AP of D72), on PLACEHOLDER years. The catalogue is the one of the
repository (``params/records/``). No number is asserted.

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
