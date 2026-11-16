"""Blueprint Block 4 L0+L1 demonstration-field chain invariant tests (D128).

Exercises EP2 -> EP1, EP3, EP4, and ``daily_reference_evapotranspiration`` on:
- ``web/src/data/demo_rotations_d128.json`` (both D128 rotations),
- ``data/demo/la_estanzuela_soil_slope.json``,
- the shipped ``params/records`` catalogue, and
- a synthetic deterministic PLACEHOLDER daily ``SiteClimate`` (2001-01-01..2024-12-31).

Every synthetic record and climate number defined in this module is a
PLACEHOLDER, plainly not real, constructed solely to assert structural,
provenance, missingness, and physical/mass-bound invariants (never specific
hardcoded simulated water or carbon outputs).

Run from the repository root:
    py -3.12 -m pytest engine/water/test_d128_chain_invariants.py -q
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.residue_ledger import ResidueLedger
from contracts.results.models import (
    DIRECTION_OF,
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_WATER_DEFICIT_EXPOSURE,
    Missing,
    SoilLossResults,
    WaterDeficitExposure,
)
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.erosion import compute_soil_loss
from engine.residues import build_residue_ledger
from engine.water import (
    compute_water_deficit_exposure,
    daily_reference_evapotranspiration,
)
from engine.water.exposure import ACCEPTED_DAILY_UNITS
from params.catalogue import check_catalogue, load_folder

ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
SOIL_SLOPE_PATH = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"
RECORDS_DIR = ROOT / "params" / "records"

MARK = "PLACEHOLDER"

CLIMATE_START = dt.date(2001, 1, 1)
CLIMATE_END = dt.date(2024, 12, 31)
FULL_AG_YEARS = list(range(2001, 2024))
BOUNDARY_AG_YEARS = (2000, 2024)

EXPECTED_ROTATION_B_MISSING_PARAMS: frozenset[
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


def _load_shipped_catalogue() -> dict[str, dict[str, Any]]:
    records, load_errors = load_folder(RECORDS_DIR)
    assert load_errors == [], f"Unexpected parameter load errors: {load_errors}"
    assert len(records) == 205
    catalogue_errors = check_catalogue(records)
    assert catalogue_errors == [], f"Catalogue check failed: {catalogue_errors}"
    return records


def _load_soil_slope() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate_json(
        SOIL_SLOPE_PATH.read_text(encoding="utf-8")
    )


def _load_d128_rotations(
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


def _build_placeholder_climate(
    case_id: str,
    field_id: str,
) -> SiteClimate:
    """Build a deterministic 2001-01-01..2024-12-31 PLACEHOLDER SiteClimate."""
    dates: list[dt.date] = []
    current = CLIMATE_START
    while current <= CLIMATE_END:
        dates.append(current)
        current += dt.timedelta(days=1)

    patterns: dict[str, list[float]] = {
        "precipitation": [0.0, 0.0, 12.34, 0.0, 0.0, 4.56, 0.0],
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


def _assert_valid_exposure_series(results: list[WaterDeficitExposure]) -> None:
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
        assert item.range is not None or item.range_missing is not None
        if item.range_missing is not None:
            assert item.range_missing.reason == "NOT_AVAILABLE"


@pytest.fixture(scope="module")
def d128_bundle() -> dict[str, Any]:
    soil_slope = _load_soil_slope()
    rotations = _load_d128_rotations(soil_slope.case_id, soil_slope.field_id)
    climate = _build_placeholder_climate(soil_slope.case_id, soil_slope.field_id)
    catalogue = _load_shipped_catalogue()
    return {
        "soil_slope": soil_slope,
        "rotations": rotations,
        "climate": climate,
        "catalogue": catalogue,
    }


def test_rotation_a_ep3_water_deficit_exposure_invariants(
    d128_bundle: dict[str, Any],
) -> None:
    """Invariant (a): Rotation A computes bounded [0, 1] exposure for 2001..2023."""
    rot_a = d128_bundle["rotations"]["soybean-winter-fallow"]
    cal_a = build_rotation_calendar(rot_a)
    results = compute_water_deficit_exposure(
        cal_a,
        d128_bundle["climate"],
        d128_bundle["soil_slope"],
        parameters=d128_bundle["catalogue"],
    )
    assert isinstance(results, list)
    _assert_valid_exposure_series(results)


def test_rotation_b_shipped_catalogue_computes_all_phases(
    d128_bundle: dict[str, Any],
) -> None:
    """Invariant (b1): on shipped 205 records, Rotation B evaluates 23/23 ag years across all phases."""
    rot_b = d128_bundle["rotations"]["wheat-soybean-maize"]
    cal_b = build_rotation_calendar(rot_b)
    phases = list_phases(cal_b)
    assert len(phases) >= 2
    assert {c.crop_id for c in cal_b.components} == {"wheat", "soybean", "maize"}

    direct_results = compute_water_deficit_exposure(
        cal_b,
        d128_bundle["climate"],
        d128_bundle["soil_slope"],
        parameters=d128_bundle["catalogue"],
    )
    assert isinstance(direct_results, list)
    _assert_valid_exposure_series(direct_results)

    for phase in phases:
        phased_cal = phase_calendar(cal_b, phase)
        results = compute_water_deficit_exposure(
            phased_cal,
            d128_bundle["climate"],
            d128_bundle["soil_slope"],
            parameters=d128_bundle["catalogue"],
        )
        assert isinstance(results, list)
        _assert_valid_exposure_series(results)


def test_rotation_b_missing_10_water_params_isolated_in_memory(
    d128_bundle: dict[str, Any],
) -> None:
    """Invariant (b2): filtering the 10 wheat/maize water keys isolates MISSING_INPUT to those 10."""
    rot_b = d128_bundle["rotations"]["wheat-soybean-maize"]
    cal_b = build_rotation_calendar(rot_b)
    stripped = _catalogue_without_keys(
        d128_bundle["catalogue"], EXPECTED_ROTATION_B_MISSING_PARAMS
    )
    assert len(stripped) == len(d128_bundle["catalogue"]) - 10
    assert check_catalogue(stripped) == []

    results = compute_water_deficit_exposure(
        cal_b,
        d128_bundle["climate"],
        d128_bundle["soil_slope"],
        parameters=stripped,
    )
    assert isinstance(results, list)
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
        detail = item.missing.detail or ""
        parsed = _extract_missing_parameters(detail)
        assert parsed == EXPECTED_ROTATION_B_MISSING_PARAMS


@pytest.mark.parametrize(
    "rotation_id", ["soybean-winter-fallow", "wheat-soybean-maize"]
)
def test_ep2_ep1_ep4_and_et0_chain_invariants(
    d128_bundle: dict[str, Any],
    rotation_id: str,
) -> None:
    """Invariant (c): EP2, EP1, EP4, and ET0 execute cleanly and satisfy structural & mass bounds."""
    rotation: RotationDefinition = d128_bundle["rotations"][rotation_id]
    climate: SiteClimate = d128_bundle["climate"]
    soil_slope: SiteSoilSlope = d128_bundle["soil_slope"]
    catalogue: dict[str, dict[str, Any]] = d128_bundle["catalogue"]

    # EP2: RotationCalendar structure and ordering
    calendar: RotationCalendar = build_rotation_calendar(rotation)
    assert calendar.ag_year_start.month == 7
    assert calendar.feasibility.feasible is True
    assert len(calendar.components) == len(rotation.components)
    for comp in calendar.components:
        assert comp.start.date is not None
        assert comp.end.date is not None
        assert comp.start.date <= comp.end.date

    # EP1: SoilLossResults invariants and monthly-to-annual conservation
    soil_loss = compute_soil_loss(
        calendar,
        climate,
        soil_slope,
        parameters=catalogue,
    )
    assert isinstance(soil_loss, SoilLossResults), (
        f"Expected SoilLossResults, got {soil_loss}"
    )
    annual_by_year = {entry.ag_year: entry for entry in soil_loss.annual}
    assert set(annual_by_year) == set(range(2000, 2025))
    for year in BOUNDARY_AG_YEARS:
        entry = annual_by_year[year]
        assert entry.value is None
        assert entry.missing is not None
        assert entry.missing.reason == "NO_COVERAGE"

    monthly_by_year: dict[int, list[float]] = {y: [] for y in FULL_AG_YEARS}
    for m_entry in soil_loss.monthly:
        if m_entry.ag_year in monthly_by_year:
            assert m_entry.missing is None
            assert m_entry.value is not None
            assert math.isfinite(m_entry.value)
            assert m_entry.value >= 0.0
            assert m_entry.provenance == PROVENANCE_OF_SOIL_LOSS
            monthly_by_year[m_entry.ag_year].append(m_entry.value)

    for year in FULL_AG_YEARS:
        entry = annual_by_year[year]
        assert entry.missing is None
        assert entry.value is not None
        assert math.isfinite(entry.value)
        assert entry.value >= 0.0
        assert entry.provenance == PROVENANCE_OF_SOIL_LOSS
        assert entry.range is not None or entry.range_missing is not None
        assert len(monthly_by_year[year]) == 12
        assert sum(monthly_by_year[year]) == pytest.approx(
            entry.value, rel=1e-9, abs=1e-9
        )

    # EP4: ResidueLedger invariants and biomass/carbon closure
    ledger = build_residue_ledger(
        rotation,
        calendar,
        climate,
        parameters=catalogue,
    )
    assert isinstance(ledger, ResidueLedger)
    assert ledger.first_ag_year == 2001
    assert ledger.last_ag_year == 2023
    assert ledger.years_missing is None
    assert len(ledger.components) > 0

    for comp in ledger.components:
        if comp.aboveground_mass_produced.value is not None:
            produced = comp.aboveground_mass_produced.value
            exported = comp.aboveground_mass_exported.value
            retained = comp.aboveground_mass_retained.value
            assert math.isfinite(produced) and produced >= 0.0
            assert exported is not None and math.isfinite(exported) and exported == 0.0
            assert retained is not None and math.isfinite(retained)
            assert retained == pytest.approx(produced - exported, rel=1e-9, abs=1e-9)
        if comp.aboveground_carbon_produced.value is not None:
            c_produced = comp.aboveground_carbon_produced.value
            c_exported = comp.aboveground_carbon_exported.value
            c_retained = comp.aboveground_carbon_retained.value
            assert math.isfinite(c_produced) and c_produced >= 0.0
            assert (
                c_exported is not None
                and math.isfinite(c_exported)
                and c_exported == 0.0
            )
            assert c_retained is not None and math.isfinite(c_retained)
            assert c_retained == pytest.approx(
                c_produced - c_exported, rel=1e-9, abs=1e-9
            )
        for c_field in (comp.root_mass, comp.root_carbon, comp.rhizodeposit_carbon):
            if c_field.value is not None:
                assert math.isfinite(c_field.value)
                assert c_field.value >= 0.0

    for annual_series in ledger.annual_carbon_inputs:
        assert len(annual_series.years) == len(FULL_AG_YEARS)
        assert annual_series.origin.endswith(("_aboveground", "_belowground"))
        for item in annual_series.years:
            if item.value is not None:
                assert math.isfinite(item.value) and item.value >= 0.0
            else:
                assert item.missing is not None
                assert item.missing.reason == "MISSING_INPUT"

    for monthly_series in ledger.monthly_carbon_inputs:
        assert len(monthly_series.months) == len(FULL_AG_YEARS) * 12
        for item in monthly_series.months:
            if item.value is not None:
                assert math.isfinite(item.value) and item.value >= 0.0
            else:
                assert item.missing is not None
                assert item.missing.reason == "MISSING_INPUT"

    # Reference ET0 over the entire climate record
    et0_by_day = daily_reference_evapotranspiration(climate, parameters=catalogue)
    expected_day_count = (CLIMATE_END - CLIMATE_START).days + 1
    assert len(et0_by_day) == expected_day_count
    for day_val in et0_by_day.values():
        assert not isinstance(day_val, Missing)
        assert math.isfinite(day_val)
        assert day_val >= 0.0
