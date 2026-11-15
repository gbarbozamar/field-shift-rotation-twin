"""Read-only contract integrity tests for committed demo and evidence assets.

Verifies the three static JSON assets referenced across L0/L3 without making
any network calls or modifying any repository files:

- ``data/demo/la_estanzuela_soil_slope.json`` against ``SiteSoilSlope``
- ``web/src/data/demo_rotations_d128.json`` against ``RotationDefinition`` and
  the EP2 calendar builder ``build_rotation_calendar``
- ``docs/evidence/nasa-power-2026-11-14/response.json`` structure, Point
  geometry, and required NASA POWER parameter series.

Run from the repository root:
``py -3.12 -m pytest params/test_demo_assets_integrity.py -q``
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar.build import build_rotation_calendar

ROOT = Path(__file__).resolve().parent.parent
SOIL_SLOPE_PATH = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
NASA_POWER_RESPONSE_PATH = (
    ROOT / "docs" / "evidence" / "nasa-power-2026-11-14" / "response.json"
)

REQUIRED_NASA_CORE_PARAMETERS = frozenset(
    {
        "ALLSKY_SFC_SW_DWN",
        "T2M_MIN",
        "T2M_MAX",
        "PRECTOTCORR",
        "WS2M",
    }
)
NASA_HUMIDITY_PARAMETERS = frozenset({"RH2M", "T2MDEW"})
_YYYYMMDD = re.compile(r"^\d{8}$")


def _load_json(path: Path) -> object:
    assert path.is_file(), f"missing asset: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_la_estanzuela_soil_slope_validates_against_contract() -> None:
    raw = _load_json(SOIL_SLOPE_PATH)
    model = SiteSoilSlope.model_validate(raw)

    assert model.contract == "site_data_soil_slope"
    assert model.example_data is True
    assert model.case_id == "la-estanzuela-demo"
    assert model.field_id == "wischmeier-plots-1984"

    assert model.slope_length.value == pytest.approx(22.1)
    assert model.slope_length.unit == "m"
    assert model.slope_length.range is None
    assert model.slope_length.range_missing is not None
    assert model.slope_length.range_missing.reason == "NOT_AVAILABLE"

    assert model.slope_steepness.value == pytest.approx(4.5)
    assert model.slope_steepness.unit == "percent"
    assert model.slope_steepness.range is not None
    assert (
        model.slope_steepness.range.low
        <= model.slope_steepness.value
        <= model.slope_steepness.range.high
    )

    by_quantity = {prop.quantity: prop for prop in model.soil_properties}
    assert "rusle_k_factor" in by_quantity
    k_factor = by_quantity["rusle_k_factor"]
    assert k_factor.value == pytest.approx(0.03)
    assert k_factor.unit == "t ha h ha-1 MJ-1 mm-1"
    assert k_factor.range is not None
    assert k_factor.range.low <= k_factor.value <= k_factor.range.high


def test_demo_rotations_d128_validate_and_have_coherent_identity() -> None:
    raw = _load_json(DEMO_ROTATIONS_PATH)
    assert isinstance(raw, list)
    assert len(raw) >= 2

    rotations = [RotationDefinition.model_validate(entry) for entry in raw]

    rotation_ids = [rot.rotation_id for rot in rotations]
    assert len(rotation_ids) == len(set(rotation_ids))

    case_ids = {rot.case_id for rot in rotations}
    field_ids = {rot.field_id for rot in rotations}
    ag_year_months = {rot.ag_year_start.month for rot in rotations}

    assert case_ids == {"example-case"}
    assert field_ids == {"example-field-1"}
    assert len(ag_year_months) == 1

    for rot in rotations:
        assert rot.contract == "rotation_definition"
        assert rot.example_data is True
        assert rot.repeats is True
        assert rot.ag_year_start.provisional is True
        assert rot.ag_year_start.provenance == "DECLARED"
        assert rot.ag_year_start.source == "user"


def test_demo_rotations_d128_build_feasible_calendars_ep2() -> None:
    raw = _load_json(DEMO_ROTATIONS_PATH)
    assert isinstance(raw, list)

    for entry in raw:
        rotation = RotationDefinition.model_validate(entry)
        calendar = build_rotation_calendar(rotation)

        assert isinstance(calendar, RotationCalendar)
        assert calendar.contract == "rotation_calendar"
        assert calendar.example_data is rotation.example_data
        assert calendar.case_id == rotation.case_id
        assert calendar.field_id == rotation.field_id
        assert calendar.rotation_id == rotation.rotation_id
        assert calendar.ag_year_start.month == rotation.ag_year_start.month
        assert calendar.ag_year_start.provisional == rotation.ag_year_start.provisional
        assert calendar.ag_year_start.provenance == rotation.ag_year_start.provenance
        assert calendar.ag_year_start.source == rotation.ag_year_start.source

        assert calendar.feasibility.feasible is True
        assert calendar.feasibility.violations == []
        assert calendar.start_date <= calendar.end_date

        assert [c.component_id for c in calendar.components] == [
            c.component_id for c in rotation.components
        ]
        assert [c.crop_id for c in calendar.components] == [
            c.crop_id for c in rotation.components
        ]


def test_nasa_power_evidence_response_parses_with_expected_geometry_and_parameters() -> None:
    payload = _load_json(NASA_POWER_RESPONSE_PATH)
    assert isinstance(payload, dict)

    assert {"type", "geometry", "properties", "header", "parameters"} <= set(payload)
    assert payload["type"] == "Feature"

    geometry = payload["geometry"]
    assert isinstance(geometry, dict)
    assert geometry.get("type") == "Point"
    coords = geometry.get("coordinates")
    assert isinstance(coords, list)
    assert len(coords) == 3
    lon, lat, elev = coords
    for coord in (lon, lat, elev):
        assert isinstance(coord, (int, float))
        assert not isinstance(coord, bool)
        assert math.isfinite(coord)
    assert -180.0 <= lon <= 180.0
    assert -90.0 <= lat <= 90.0

    properties = payload["properties"]
    assert isinstance(properties, dict)
    param_series = properties.get("parameter")
    assert isinstance(param_series, dict)

    assert REQUIRED_NASA_CORE_PARAMETERS <= set(param_series)
    present_humidity = NASA_HUMIDITY_PARAMETERS & set(param_series)
    assert present_humidity, (
        f"expected at least one of {sorted(NASA_HUMIDITY_PARAMETERS)} in parameters"
    )

    checked_keys = sorted(REQUIRED_NASA_CORE_PARAMETERS | present_humidity)
    param_meta = payload["parameters"]
    assert isinstance(param_meta, dict)
    fill_value = payload["header"].get("fill_value")

    expected_dates: set[str] | None = None
    for key in checked_keys:
        assert key in param_meta
        assert isinstance(param_meta[key].get("units"), str) and param_meta[key]["units"]
        assert isinstance(param_meta[key].get("longname"), str) and param_meta[key]["longname"]

        series = param_series[key]
        assert isinstance(series, dict) and series
        for date_key, value in series.items():
            assert isinstance(date_key, str) and _YYYYMMDD.fullmatch(date_key)
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            assert math.isfinite(value)
            if fill_value is not None:
                assert value != fill_value

        if expected_dates is None:
            expected_dates = set(series)
        else:
            assert set(series) == expected_dates
