"""Phase-1 EP3 hydrological mass-closure and readiness tests (D128, closure_review).

Verifies deterministically in-memory against the repository's active signed
``params/records/`` catalogue, ``data/demo/la_estanzuela_soil_slope.json``,
``web/src/data/demo_rotations_d128.json``, and a synthetic deterministic
``PLACEHOLDER`` daily ``SiteClimate`` series spanning 8,766 days
(2001-01-01..2024-12-31):

1. ``soybean-winter-fallow`` phase 1 and ``wheat-soybean-maize`` phase 1 produce
   non-missing exposure outputs across all 23 full agricultural years
   (2001..2023) and close the daily soil-water mass balance across all 8,766
   days within tight floating-point tolerance against the active 205-record
   ``params/records/`` catalogue.
2. Filtering the 10 wheat/maize water parameter keys (#433) out of an
   in-memory copy of the catalogue isolates ``MISSING_INPUT`` on
   ``wheat-soybean-maize`` phase 1 to those exact 10 keys.

Every climate input in this module is synthetic ``PLACEHOLDER`` data; it does
not represent NASA POWER observations or claim physical field validation.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    UNIT_WATER_DEFICIT_EXPOSURE,
    Missing,
    WaterDeficitExposure,
)
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.water import (
    _parameters,
    compute_water_deficit_exposure,
    exposure,
)
from engine.water.exposure import ACCEPTED_DAILY_UNITS, DAILY_INPUTS
from engine.water.runoff import PRECIPITATION
from params.catalogue import check_catalogue, check_layout, load_folder

ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
SOIL_SLOPE_PATH = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"
PARAMS_DIR = ROOT / "params"
RECORDS_DIR = PARAMS_DIR / "records"

MARK = "PLACEHOLDER"
CLIMATE_START = dt.date(2001, 1, 1)
CLIMATE_END = dt.date(2024, 12, 31)
EXPECTED_DAY_COUNT = 8766
FULL_AG_YEARS = list(range(2001, 2024))
BOUNDARY_AG_YEARS = (2000, 2024)
EPS = sys.float_info.epsilon

EXPECTED_WHEAT_MAIZE_WATER_PARAMS: frozenset[
    tuple[str, tuple[tuple[str, str], ...]]
] = frozenset(
    {
        ("fao56_stage_length_initial", (("crop", "wheat"),)),
        ("fao56_stage_length_development", (("crop", "wheat"),)),
        ("fao56_stage_length_mid", (("crop", "wheat"),)),
        ("fao56_stage_length_late", (("crop", "wheat"),)),
        ("fao56_stage_length_initial", (("crop", "maize"),)),
        ("fao56_stage_length_development", (("crop", "maize"),)),
        ("fao56_stage_length_mid", (("crop", "maize"),)),
        ("fao56_stage_length_late", (("crop", "maize"),)),
        (
            "surface_residue_cover",
            (("crop", "wheat"), ("management", "no_crop")),
        ),
        (
            "surface_residue_cover",
            (("crop", "maize"), ("management", "no_crop")),
        ),
    }
)


def _load_active_catalogue() -> dict[str, dict[str, Any]]:
    layout_errors = check_layout(PARAMS_DIR)
    assert layout_errors == [], f"Unexpected params layout errors: {layout_errors}"
    records, load_errors = load_folder(RECORDS_DIR)
    assert load_errors == [], f"Unexpected parameter load errors: {load_errors}"
    catalogue_errors = check_catalogue(records)
    assert catalogue_errors == [], f"Catalogue check failed: {catalogue_errors}"
    return records


def _load_demo_rotations(
    case_id: str,
    field_id: str,
) -> dict[str, RotationDefinition]:
    raw = json.loads(DEMO_ROTATIONS_PATH.read_text(encoding="utf-8"))
    rotations: dict[str, RotationDefinition] = {}
    for entry in raw:
        rotation = RotationDefinition.model_validate(entry).model_copy(
            update={"case_id": case_id, "field_id": field_id}
        )
        rotations[rotation.rotation_id] = rotation
    return rotations


def _build_synthetic_placeholder_climate(
    case_id: str,
    field_id: str,
) -> SiteClimate:
    """Build a deterministic 8,766-day (2001-01-01..2024-12-31) PLACEHOLDER SiteClimate."""
    day_count = (CLIMATE_END - CLIMATE_START).days + 1
    assert day_count == EXPECTED_DAY_COUNT
    dates = [CLIMATE_START + dt.timedelta(days=offset) for offset in range(day_count)]

    patterns: dict[str, list[float]] = {
        "precipitation": [0.0, 0.0, 12.34, 0.0, 0.0, 4.56, 0.0, 45.0, 0.0, 0.0],
        "air_temperature_max_2m": [22.2, 24.4, 26.6, 25.5, 23.3],
        "air_temperature_min_2m": [11.1, 12.2, 13.3, 12.2],
        "dew_point_temperature_2m": [8.88, 9.99, 10.11],
        "wind_speed_2m": [1.55, 2.22, 3.11],
        "solar_radiation": [12.34, 15.67, 18.91, 14.56],
    }

    daily_series: list[DailySeries] = []
    for quantity, unit in ACCEPTED_DAILY_UNITS.items():
        seq = patterns[quantity]
        days = [
            DailyValue(date=day, value=seq[idx % len(seq)])
            for idx, day in enumerate(dates)
        ]
        daily_series.append(
            DailySeries(
                quantity=quantity,
                unit=unit,
                provenance="DECLARED",
                source=f"{MARK} deterministic synthetic daily climate series",
                range_missing={
                    "reason": "NOT_AVAILABLE",
                    "detail": f"{MARK} synthetic series carries no uncertainty range.",
                },
                time_zone="UTC",
                start_date=CLIMATE_START,
                end_date=CLIMATE_END,
                days=days,
            )
        )

    def _point_value(val: float, unit: str) -> dict[str, Any]:
        return {
            "value": val,
            "unit": unit,
            "provenance": "DECLARED",
            "source": f"{MARK} synthetic demonstration coordinates",
            "range_missing": {
                "reason": "NOT_AVAILABLE",
                "detail": f"{MARK} point value without range.",
            },
        }

    return SiteClimate.model_validate(
        {
            "contract": "site_data_climate",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "point": {
                "latitude": _point_value(-30.0, "degree"),
                "longitude": _point_value(-55.0, "degree"),
                "elevation": _point_value(50.0, "m"),
            },
            "daily_series": [s.model_dump(mode="python") for s in daily_series],
            "monthly_series": [],
        }
    )


def _run_daily_chain(
    calendar: RotationCalendar,
    climate: SiteClimate,
    records: dict[str, dict[str, Any]],
) -> list[exposure.ChainDay]:
    by_quantity = {
        series.quantity: series
        for series in climate.daily_series
        if series.quantity in DAILY_INPUTS
    }
    return exposure._run_chain(
        calendar,
        climate,
        _parameters.Catalogue(records),
        by_quantity,
        exposure._chain_days(by_quantity[PRECIPITATION], list(by_quantity), by_quantity),
        exposure._Notes(),
    )


def _extract_missing_parameters(
    detail: str,
) -> set[tuple[str, tuple[tuple[str, str], ...]]]:
    """Parse 'parameter MISSING_INPUT: ... scope <json>: <ids>' clauses from detail."""
    clause_pattern = re.compile(
        r"parameter MISSING_INPUT:[^;]*?scope\s+(\{[^}]*\}):\s*([^;]+)"
    )
    clauses = clause_pattern.findall(detail)
    assert len(clauses) == detail.count("parameter MISSING_INPUT:")
    found: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for scope_text, ids_text in clauses:
        scope_dict = json.loads(scope_text)
        scope_items = tuple(sorted((str(k), str(v)) for k, v in scope_dict.items()))
        for param_id in re.findall(r"'([a-z0-9_]+)'", ids_text):
            found.add((param_id, scope_items))
    return found


@pytest.fixture(scope="module")
def phase1_bundle() -> dict[str, Any]:
    records = _load_active_catalogue()
    soil_slope = SiteSoilSlope.model_validate_json(
        SOIL_SLOPE_PATH.read_text(encoding="utf-8")
    )
    rotations = _load_demo_rotations(soil_slope.case_id, soil_slope.field_id)
    climate = _build_synthetic_placeholder_climate(
        soil_slope.case_id, soil_slope.field_id
    )
    return {
        "records": records,
        "soil_slope": soil_slope,
        "rotations": rotations,
        "climate": climate,
    }


def _catalogue_without_keys(
    records: dict[str, dict[str, Any]],
    excluded: frozenset[tuple[str, tuple[tuple[str, str], ...]]],
) -> dict[str, dict[str, Any]]:
    """Return an in-memory copy of ``records`` without the excluded ``(id, scope)`` keys."""
    return {
        key: copy.deepcopy(record)
        for key, record in records.items()
        if (record["id"], tuple(sorted(record["scope"].items()))) not in excluded
    }


def _assert_phase1_exposure_and_mass_closure(
    phase1_calendar: RotationCalendar,
    climate: SiteClimate,
    records: dict[str, dict[str, Any]],
    soil_slope: SiteSoilSlope,
) -> None:
    results: list[WaterDeficitExposure] = compute_water_deficit_exposure(
        phase1_calendar,
        climate,
        soil_slope,
        parameters=records,
    )
    by_year = {item.ag_year: item for item in results}
    assert set(by_year) == set(range(2000, 2025))

    for year in BOUNDARY_AG_YEARS:
        item = by_year[year]
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "NO_COVERAGE"

    for year in FULL_AG_YEARS:
        item = by_year[year]
        assert item.missing is None
        assert item.value is not None
        assert math.isfinite(item.value)
        assert 0.0 <= item.value <= 1.0
        assert item.provenance == "SIMULATED"
        assert item.unit == UNIT_WATER_DEFICIT_EXPOSURE
        assert item.direction == DIRECTION_OF["water_deficit_exposure"]

    chain = _run_daily_chain(phase1_calendar, climate, records)
    assert len(chain) == EXPECTED_DAY_COUNT
    assert chain[0].date == CLIMATE_START
    assert chain[-1].date == CLIMATE_END

    capacity = float(records["water/column_capacity.json"]["value"])
    initial_storage = float(records["water/initial_storage.json"]["value"])
    assert chain[0].balance.storage_start == initial_storage

    for prev_day, curr_day in zip(chain, chain[1:]):
        assert curr_day.date == prev_day.date + dt.timedelta(days=1)
        assert curr_day.balance.storage_start == prev_day.balance.storage_end

    for day in chain:
        b = day.balance
        terms = (
            b.storage_start,
            b.storage_end,
            b.precipitation,
            b.runoff,
            b.evaporation,
            b.transpiration,
            b.drainage,
        )
        assert all(
            not isinstance(term, Missing) and math.isfinite(term) for term in terms
        ), day.date
        assert 0.0 <= b.storage_start <= capacity, day.date
        assert 0.0 <= b.storage_end <= capacity, day.date
        assert min(terms[2:]) >= 0.0, day.date

        storage_change = b.storage_end - b.storage_start
        net_flux = (
            b.precipitation
            - b.runoff
            - b.evaporation
            - b.transpiration
            - b.drainage
        )
        scale = math.fsum(terms)
        assert abs(storage_change - net_flux) <= 16.0 * EPS * max(scale, 1.0), day.date
        assert not isinstance(day.surface_layer.depletion_end, Missing), day.date
        assert not isinstance(day.surface_depletion_carried, Missing), day.date

    total_storage_change = chain[-1].balance.storage_end - chain[0].balance.storage_start
    total_precip = math.fsum(day.balance.precipitation for day in chain)
    total_runoff = math.fsum(day.balance.runoff for day in chain)
    total_evap = math.fsum(day.balance.evaporation for day in chain)
    total_transp = math.fsum(day.balance.transpiration for day in chain)
    total_drainage = math.fsum(day.balance.drainage for day in chain)
    cumulative_net = (
        total_precip - total_runoff - total_evap - total_transp - total_drainage
    )
    cumulative_scale = math.fsum(
        (
            chain[0].balance.storage_start,
            chain[-1].balance.storage_end,
            total_precip,
            total_runoff,
            total_evap,
            total_transp,
            total_drainage,
        )
    )
    assert abs(total_storage_change - cumulative_net) <= (
        64.0 * EPS * max(cumulative_scale, 1.0)
    )

    # Confirm non-trivial fluxes across the 24-year window so closure is not vacuously zero.
    assert total_precip > 0.0
    assert total_runoff > 0.0
    assert total_evap > 0.0
    assert total_transp > 0.0
    assert total_drainage > 0.0
    assert any(
        not isinstance(day.balance.transpiration_demanded, Missing) for day in chain
    )
    assert any(
        isinstance(day.balance.transpiration_demanded, Missing)
        and day.balance.transpiration_demanded.reason == "NOT_APPLICABLE"
        for day in chain
    )


def test_active_params_layout_and_signed_water_soybean_records(
    phase1_bundle: dict[str, Any],
) -> None:
    """Active params/records layout passes and carries signed water, soybean, wheat, and maize records."""
    records: dict[str, dict[str, Any]] = phase1_bundle["records"]
    assert len(records) == 205
    required_paths = (
        "water/column_capacity.json",
        "water/column_depth.json",
        "water/initial_storage.json",
        "water/fao56_stage_length_initial.soybean.json",
        "water/fao56_stage_length_development.soybean.json",
        "water/fao56_stage_length_mid.soybean.json",
        "water/fao56_stage_length_late.soybean.json",
        "water/surface_residue_cover.soybean.no_crop.json",
        "water/fao56_stage_length_initial.wheat.json",
        "water/fao56_stage_length_development.wheat.json",
        "water/fao56_stage_length_mid.wheat.json",
        "water/fao56_stage_length_late.wheat.json",
        "water/surface_residue_cover.wheat.no_crop.json",
        "water/fao56_stage_length_initial.maize.json",
        "water/fao56_stage_length_development.maize.json",
        "water/fao56_stage_length_mid.maize.json",
        "water/fao56_stage_length_late.maize.json",
        "water/surface_residue_cover.maize.no_crop.json",
    )
    for rel_path in required_paths:
        assert rel_path in records, f"Missing active record: {rel_path}"
        assert str(records[rel_path]["checked_by"]).strip() != ""


def test_soybean_winter_fallow_phase1_8766_day_exposure_and_mass_closure(
    phase1_bundle: dict[str, Any],
) -> None:
    """Soybean-winter-fallow phase 1 computes EP3 and closes daily mass across 8,766 days."""
    records = phase1_bundle["records"]
    soil_slope = phase1_bundle["soil_slope"]
    climate = phase1_bundle["climate"]
    rotation = phase1_bundle["rotations"]["soybean-winter-fallow"]

    calendar = build_rotation_calendar(rotation)
    assert list_phases(calendar) == [0]
    phase1_calendar = phase_calendar(calendar, 0)
    _assert_phase1_exposure_and_mass_closure(
        phase1_calendar, climate, records, soil_slope
    )


def test_wheat_soybean_maize_phase1_8766_day_exposure_and_mass_closure(
    phase1_bundle: dict[str, Any],
) -> None:
    """Wheat-soybean-maize phase 1 computes EP3 and closes daily mass across 8,766 days."""
    records = phase1_bundle["records"]
    soil_slope = phase1_bundle["soil_slope"]
    climate = phase1_bundle["climate"]
    rotation = phase1_bundle["rotations"]["wheat-soybean-maize"]

    calendar = build_rotation_calendar(rotation)
    assert 0 in list_phases(calendar)
    phase1_calendar = phase_calendar(calendar, 0)
    _assert_phase1_exposure_and_mass_closure(
        phase1_calendar, climate, records, soil_slope
    )


def test_wheat_soybean_maize_phase1_missing_10_params_isolated_in_memory(
    phase1_bundle: dict[str, Any],
) -> None:
    """Filtering the 10 wheat/maize water keys isolates MISSING_INPUT to those exact 10 keys."""
    records = _catalogue_without_keys(
        phase1_bundle["records"], EXPECTED_WHEAT_MAIZE_WATER_PARAMS
    )
    assert len(records) == len(phase1_bundle["records"]) - 10
    assert check_catalogue(records) == []

    soil_slope = phase1_bundle["soil_slope"]
    climate = phase1_bundle["climate"]
    rotation = phase1_bundle["rotations"]["wheat-soybean-maize"]

    calendar = build_rotation_calendar(rotation)
    assert 0 in list_phases(calendar)
    phase1_calendar = phase_calendar(calendar, 0)

    results: list[WaterDeficitExposure] = compute_water_deficit_exposure(
        phase1_calendar,
        climate,
        soil_slope,
        parameters=records,
    )
    by_year = {item.ag_year: item for item in results}
    assert set(by_year) == set(range(2000, 2025))

    for year in BOUNDARY_AG_YEARS:
        item = by_year[year]
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "NO_COVERAGE"

    for year in FULL_AG_YEARS:
        item = by_year[year]
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "MISSING_INPUT"
        missing_params = _extract_missing_parameters(item.missing.detail or "")
        assert len(missing_params) == 10
        assert missing_params == EXPECTED_WHEAT_MAIZE_WATER_PARAMS
