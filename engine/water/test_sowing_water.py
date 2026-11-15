"""Unit and D128 chain invariant tests for ``engine.water.sowing_water`` (D50, D106).

Every synthetic parameter record, calendar, and climate series in this module is
a PLACEHOLDER, plainly not real, constructed solely to verify structural,
coverage, missingness, continuity, and physical-bound invariants of
``compute_sowing_available_water``.

Run from the repository root:
    py -3.12 -m pytest engine/water/test_sowing_water.py -q
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.water import exposure
from engine.water._parameters import Catalogue
from engine.water.et0.quantities import WIND_SPEED_2M
from engine.water.sowing_water import (
    UNIT_SOWING_AVAILABLE_WATER,
    SowingAvailableWater,
    compute_sowing_available_water,
)
from engine.water.stages import GROWTH_STAGES, STAGE_LENGTH_PARAMETERS
from params.catalogue import check_catalogue, load_folder

ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
SOIL_SLOPE_PATH = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"
RECORDS_DIR = ROOT / "params" / "records"

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"

# --- PLACEHOLDER unit-test catalogue & inputs --------------------------------

_SITE_VALUES: dict[str, float] = {
    "net_shortwave_albedo": 0.0,
    "net_longwave_stefan_boltzmann": 0.0,
    "inverse_relative_distance_amplitude": 0.0,
    "solar_declination_amplitude": 0.0,
    "atmospheric_pressure_lapse_rate": 0.0,
    "net_longwave_relative_shortwave_maximum": 7.77,
    "penman_monteith_minimum_wind_speed": 0.111,
    "soil_heat_flux_daily_value": 1.11,
    "initial_abstraction_ratio": 0.555,
    "retention_numerator": 2.22,
    "retention_unit_factor": 4.44,
    "initial_depletion": 1.11,
    "field_capacity_water_content": 5.55,
    "wilting_point_water_content": 1.11,
    "readily_evaporable_water": 2.22,
    "wetted_fraction": 0.777,
    "margin_above_basal": 0.555,
    "minimum_crop_coefficient": 0.222,
    "minimum_relative_humidity": 3.33,
    "column_capacity": 50.0,
    "column_depth": 2.22,
    "initial_storage": 11.1,
    "mulch_total_evaporable_water_reduction": 0.0333,
    "mulch_cover_increment": 0.111,
}
_CROPS = ("crop-a", "crop-b")
_STAGE_COEFFS = {"initial": 0.444, "mid": 0.555, "end": 0.666}
_STAGE_LENGTHS = {
    "crop-a": {"initial": 1.0, "development": 1.0, "mid": 1.0, "late": 1.0},
    "crop-b": {"initial": 1.0, "development": 1.0, "mid": 1.0, "late": 1.0},
}


def _unmark(obj: Any) -> Any:
    return json.loads(json.dumps(obj).replace(MARK, UNMARKED))


def _placeholder_record(
    param_id: str,
    scope: dict[str, str],
    value: float | int | None,
    unit: str = f"{MARK}_unit",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": param_id,
        "scope": scope,
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": f"{MARK} synthetic test record without uncertainty range.",
        "citation": {
            "reference": f"{MARK} synthetic reference for {param_id}",
            "locator": f"{MARK} synthetic unit test",
        },
        "transcribed_by": f"{MARK} automated test author",
        "checked_by": f"{MARK} automated test reviewer",
    }
    if value is None:
        record["missing_reason"] = f"{MARK} intentionally omitted value"
    return record


def _build_unit_catalogue(
    overrides: dict[tuple[str, tuple[tuple[str, str], ...]], float | None] | None = None,
) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for param_id in (*exposure.SITE_PARAMETERS, *exposure.FALLOW_SITE_PARAMETERS):
        records.append(
            _placeholder_record(param_id, {}, _SITE_VALUES.get(param_id, 1.0))
        )
    no_crop_scope = {"management": "no_crop"}
    for param_id, val in (
        ("basal_crop_coefficient", 0.333),
        ("crop_height", 0.111),
        ("curve_number", 1.11),
        ("cover_fraction", 0.111),
        ("wetted_fraction", 0.888),
    ):
        records.append(_placeholder_record(param_id, no_crop_scope, val))
    for crop in _CROPS:
        crop_scope = {"crop": crop}
        records.append(
            _placeholder_record(
                exposure.SURFACE_RESIDUE_COVER,
                {"crop": crop, "management": "no_crop"},
                0.222,
            )
        )
        for param_id, val in (
            ("crop_height", 1.11),
            ("curve_number", 1.11),
            ("cover_fraction_exponent", 1.11),
            ("maximum_root_depth", 1.11),
            ("initial_root_depth", 0.111),
            ("readily_available_fraction", 0.444),
        ):
            records.append(_placeholder_record(param_id, crop_scope, val))
        for stage in exposure.STAGES:
            records.append(
                _placeholder_record(
                    exposure.BASAL_CROP_COEFFICIENT,
                    {"crop": crop, "stage": stage},
                    _STAGE_COEFFS[stage],
                )
            )
        for stage in GROWTH_STAGES:
            records.append(
                _placeholder_record(
                    STAGE_LENGTH_PARAMETERS[stage],
                    crop_scope,
                    _STAGE_LENGTHS[crop][stage],
                )
            )
    if overrides:
        for rec in records:
            key = (rec["id"], tuple(sorted(rec["scope"].items())))
            if key in overrides:
                val = overrides[key]
                rec["value"] = val
                if val is None:
                    rec["missing_reason"] = f"{MARK} intentionally omitted value"
                else:
                    rec.pop("missing_reason", None)
    return _unmark({f"{MARK}_{idx}.json": rec for idx, rec in enumerate(records)})


def _point_value(val: float, unit: str) -> dict[str, Any]:
    return {
        "value": val,
        "unit": unit,
        "provenance": "DECLARED",
        "source": f"{MARK} synthetic coordinates",
        "range_missing": {
            "reason": "NOT_AVAILABLE",
            "detail": f"{MARK} point value without range.",
        },
    }


def _build_climate(
    start: dt.date,
    end: dt.date,
    *,
    case_id: str = "case-1",
    field_id: str = "field-1",
    precip_by_day: dict[dt.date, float | None] | None = None,
    series_starts: dict[str, dt.date] | None = None,
    time_zones: dict[str, str] | None = None,
    units: dict[str, str] | None = None,
    omit_series: set[str] | None = None,
) -> SiteClimate:
    patterns: dict[str, list[float]] = {
        "precipitation": [0.0, 0.0, 6.66, 0.0, 4.44],
        "air_temperature_max_2m": [22.2, 24.4, 25.5],
        "air_temperature_min_2m": [11.1, 12.2],
        "dew_point_temperature_2m": [8.88, 9.99],
        "wind_speed_2m": [1.55, 2.22],
        "solar_radiation": [12.34, 15.67, 14.56],
    }
    daily_series: list[dict[str, Any]] = []
    for quantity, default_unit in exposure.ACCEPTED_DAILY_UNITS.items():
        if omit_series and quantity in omit_series:
            continue
        s_start = series_starts.get(quantity, start) if series_starts else start
        days: list[dict[str, Any]] = []
        seq = patterns[quantity]
        cur = s_start
        idx = 0
        while cur <= end:
            if quantity == "precipitation" and precip_by_day and cur in precip_by_day:
                val = precip_by_day[cur]
            else:
                val = seq[idx % len(seq)]
            if val is None:
                days.append(
                    {
                        "date": cur,
                        "value": None,
                        "missing": {
                            "reason": "MISSING_INPUT",
                            "detail": f"{MARK} missing value on {cur.isoformat()}",
                        },
                    }
                )
            else:
                days.append({"date": cur, "value": val})
            cur += dt.timedelta(days=1)
            idx += 1
        daily_series.append(
            {
                "quantity": quantity,
                "unit": units.get(quantity, default_unit) if units else default_unit,
                "provenance": "DECLARED",
                "source": f"{MARK} deterministic synthetic daily series",
                "range_missing": {
                    "reason": "NOT_AVAILABLE",
                    "detail": f"{MARK} synthetic series without uncertainty range.",
                },
                "time_zone": time_zones.get(quantity, "UTC") if time_zones else "UTC",
                "start_date": s_start,
                "end_date": end,
                "days": days,
            }
        )

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
            "daily_series": daily_series,
            "monthly_series": [],
        }
    )


def _date_value(day: dt.date | None) -> dict[str, Any]:
    if day is None:
        return {
            "date": None,
            "missing": {
                "reason": "NOT_DECLARED",
                "detail": f"{MARK} intentionally omitted date",
            },
        }
    return {
        "date": day,
        "provenance": "DECLARED",
        "source": f"{MARK} synthetic calendar date",
    }


def _build_calendar(
    *,
    case_id: str = "case-1",
    field_id: str = "field-1",
    ag_year_start_month: int | None = 7,
    start_date: dt.date = dt.date(2001, 7, 1),
    end_date: dt.date = dt.date(2002, 6, 30),
    feasible: bool = True,
    components: list[tuple[str, str, dt.date | None, dt.date | None]] | None = None,
) -> RotationCalendar:
    if components is None:
        components = [
            ("comp-1", "crop-a", dt.date(2001, 7, 5), dt.date(2001, 7, 8)),
            ("comp-2", "crop-b", dt.date(2001, 7, 12), dt.date(2001, 7, 15)),
        ]
    ag_year_start: dict[str, Any] = (
        {
            "month": None,
            "missing": {
                "reason": "NOT_DECLARED",
                "detail": f"{MARK} intentionally missing ag_year_start.month",
            },
        }
        if ag_year_start_month is None
        else {
            "month": ag_year_start_month,
            "provisional": True,
            "provenance": "DECLARED",
            "source": f"{MARK} synthetic start month",
        }
    )
    violations = (
        []
        if feasible
        else [
            {
                "rule": f"{MARK}_rule",
                "component_ids": [components[0][0]],
                "detail": f"{MARK} synthetic infeasibility",
            }
        ]
    )
    return RotationCalendar.model_validate(
        {
            "contract": "rotation_calendar",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "rotation_id": f"{MARK}-rotation",
            "ag_year_start": ag_year_start,
            "start_date": start_date,
            "end_date": end_date,
            "feasibility": {"feasible": feasible, "violations": violations},
            "components": [
                {
                    "component_id": cid,
                    "crop_id": crop,
                    "start": _date_value(s),
                    "end": _date_value(e),
                    "periods": [],
                }
                for cid, crop, s, e in components
            ],
        }
    )


def _build_soil_slope(
    *, case_id: str = "case-1", field_id: str = "field-1"
) -> SiteSoilSlope:
    return SiteSoilSlope.model_validate(
        {
            "contract": "site_data_soil_slope",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "slope_length": _point_value(20.0, "m"),
            "slope_steepness": _point_value(3.0, "percent"),
            "soil_properties": [],
        }
    )


# --- Unit tests ---------------------------------------------------------------


def test_caller_validation_matches_ep3() -> None:
    cal = _build_calendar()
    clim = _build_climate(dt.date(2001, 7, 1), dt.date(2001, 7, 20))
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    with pytest.raises(TypeError):
        compute_sowing_available_water("bad", clim, soil, parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_sowing_available_water(cal, "bad", soil, parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_sowing_available_water(cal, clim, "bad", parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compute_sowing_available_water(cal, clim, soil, parameters="bad")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="case_id"):
        compute_sowing_available_water(
            cal,
            _build_climate(
                dt.date(2001, 7, 1), dt.date(2001, 7, 20), case_id="other-case"
            ),
            soil,
            parameters=params,
        )
    with pytest.raises(ValueError, match="field_id"):
        compute_sowing_available_water(
            cal,
            clim,
            _build_soil_slope(field_id="other-field"),
            parameters=params,
        )


def test_missing_start_month_and_missing_precipitation_return_sentinel() -> None:
    clim = _build_climate(dt.date(2001, 7, 1), dt.date(2001, 7, 20))
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    cal_no_month = _build_calendar(ag_year_start_month=None)
    res_no_month = compute_sowing_available_water(
        cal_no_month, clim, soil, parameters=params
    )
    assert len(res_no_month) == 1
    assert res_no_month[0].sowing_date is None
    assert res_no_month[0].unit == UNIT_SOWING_AVAILABLE_WATER
    assert isinstance(res_no_month[0].value, Missing)
    assert res_no_month[0].value.reason == "MISSING_INPUT"

    cal = _build_calendar()
    clim_no_precip = _build_climate(
        dt.date(2001, 7, 1), dt.date(2001, 7, 20), omit_series={"precipitation"}
    )
    res_no_precip = compute_sowing_available_water(
        cal, clim_no_precip, soil, parameters=params
    )
    assert len(res_no_precip) == 1
    assert res_no_precip[0].sowing_date is None
    assert res_no_precip[0].unit == UNIT_SOWING_AVAILABLE_WATER
    assert isinstance(res_no_precip[0].value, Missing)
    assert res_no_precip[0].value.reason == "MISSING_INPUT"


def test_infeasible_mixed_tz_and_unaccepted_units() -> None:
    clim = _build_climate(dt.date(2001, 7, 1), dt.date(2001, 7, 20))
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    infeasible = _build_calendar(feasible=False)
    res_inf = compute_sowing_available_water(infeasible, clim, soil, parameters=params)
    assert len(res_inf) == 2
    for item in res_inf:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "NOT_COMPUTABLE"

    cal = _build_calendar()
    mixed_tz_clim = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 20),
        time_zones={WIND_SPEED_2M: "America/Montevideo"},
    )
    res_tz = compute_sowing_available_water(cal, mixed_tz_clim, soil, parameters=params)
    assert len(res_tz) == 2
    for item in res_tz:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "NOT_COMPUTABLE"

    # Bad unit: in-record sowing gets MISSING_INPUT, out-of-record gets NO_COVERAGE.
    cal_with_oob = _build_calendar(
        components=[
            ("comp-1", "crop-a", dt.date(2001, 7, 5), dt.date(2001, 7, 8)),
            ("comp-2", "crop-b", dt.date(2001, 7, 25), dt.date(2001, 7, 28)),
        ]
    )
    bad_unit_clim = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 20),
        units={"precipitation": "cm day-1"},
    )
    res_units = compute_sowing_available_water(
        cal_with_oob, bad_unit_clim, soil, parameters=params
    )
    assert len(res_units) == 2
    assert res_units[0].sowing_date == dt.date(2001, 7, 5)
    assert isinstance(res_units[0].value, Missing)
    assert res_units[0].value.reason == "MISSING_INPUT"
    assert res_units[1].sowing_date == dt.date(2001, 7, 25)
    assert isinstance(res_units[1].value, Missing)
    assert res_units[1].value.reason == "NO_COVERAGE"


def test_sowing_on_day_one_uses_initial_storage_and_validates_bounds() -> None:
    cal = _build_calendar(
        components=[
            ("comp-1", "crop-a", dt.date(2001, 7, 1), dt.date(2001, 7, 4)),
            ("comp-2", "crop-b", dt.date(2001, 7, 6), dt.date(2001, 7, 9)),
        ]
    )
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    # Normal day-1 sowing reports initial_storage.
    clim = _build_climate(dt.date(2001, 7, 1), dt.date(2001, 7, 10))
    res = compute_sowing_available_water(cal, clim, soil, parameters=params)
    assert len(res) == 2
    assert res[0] == SowingAvailableWater(
        component_id="comp-1",
        crop_id="crop-a",
        cycle_index=0,
        sowing_date=dt.date(2001, 7, 1),
        value=pytest.approx(_SITE_VALUES["initial_storage"]),
        unit="mm",
    )
    assert isinstance(res[1].value, float)

    # Day 1 weather missing: day-1 entering storage is STILL initial_storage,
    # while day-6 sowing becomes MISSING_INPUT from the broken chain.
    clim_day1_missing = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 10),
        precip_by_day={dt.date(2001, 7, 1): None},
    )
    res_day1_gap = compute_sowing_available_water(
        cal, clim_day1_missing, soil, parameters=params
    )
    assert res_day1_gap[0].value == pytest.approx(_SITE_VALUES["initial_storage"])
    assert isinstance(res_day1_gap[1].value, Missing)
    assert res_day1_gap[1].value.reason == "MISSING_INPUT"

    # Missing initial_storage -> MISSING_INPUT on day 1.
    params_no_init = _build_unit_catalogue({("initial_storage", ()): None})
    res_no_init = compute_sowing_available_water(
        cal, clim, soil, parameters=params_no_init
    )
    assert isinstance(res_no_init[0].value, Missing)
    assert res_no_init[0].value.reason == "MISSING_INPUT"

    # initial_storage > column_capacity -> NOT_COMPUTABLE on day 1.
    params_bad_init = _build_unit_catalogue({("initial_storage", ()): 999.0})
    res_bad_init = compute_sowing_available_water(
        cal, clim, soil, parameters=params_bad_init
    )
    assert isinstance(res_bad_init[0].value, Missing)
    assert res_bad_init[0].value.reason == "NOT_COMPUTABLE"


def test_entering_day_storage_matches_previous_day_storage_end() -> None:
    sowing_day = dt.date(2001, 7, 5)
    prev_day = dt.date(2001, 7, 4)
    cal = _build_calendar(
        components=[
            ("comp-1", "crop-a", sowing_day, dt.date(2001, 7, 8)),
        ]
    )
    clim = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 10),
        precip_by_day={prev_day: 0.0, sowing_day: 25.0},
    )
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    res = compute_sowing_available_water(cal, clim, soil, parameters=params)
    assert len(res) == 1
    assert isinstance(res[0].value, float)

    # Cross-check directly against exposure._run_chain: entering storage equals
    # prev_day.balance.storage_end, NOT sowing_day.balance.storage_end.
    by_q = {s.quantity: s for s in clim.daily_series}
    present = [q for q in exposure.DAILY_INPUTS if q in by_q]
    chain = exposure._run_chain(
        cal,
        clim,
        Catalogue(params),
        by_q,
        exposure._chain_days(by_q["precipitation"], present, by_q),
        exposure._Notes(),
    )
    chain_by_day = {item.date: item for item in chain}
    expected_entering = chain_by_day[prev_day].balance.storage_end
    sowing_day_end = chain_by_day[sowing_day].balance.storage_end
    assert isinstance(expected_entering, float)
    assert isinstance(sowing_day_end, float)
    assert expected_entering != pytest.approx(sowing_day_end)
    assert res[0].value == pytest.approx(expected_entering)


def test_sowing_day_missing_weather_keeps_carried_storage_and_breaks_later() -> None:
    cal = _build_calendar(
        components=[
            ("comp-1", "crop-a", dt.date(2001, 7, 5), dt.date(2001, 7, 8)),
            ("comp-2", "crop-b", dt.date(2001, 7, 12), dt.date(2001, 7, 15)),
        ]
    )
    clim = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 18),
        precip_by_day={dt.date(2001, 7, 5): None},
    )
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    res = compute_sowing_available_water(cal, clim, soil, parameters=params)
    assert len(res) == 2
    assert isinstance(res[0].value, float)
    assert 0.0 <= res[0].value <= _SITE_VALUES["column_capacity"]
    assert isinstance(res[1].value, Missing)
    assert res[1].value.reason == "MISSING_INPUT"


def test_out_of_record_undated_and_uncovered_previous_day() -> None:
    # Lead-in (cycle -1) and cycle 0 start before record_start (2002-01-01);
    # cycle 1 starts inside record.
    cal = _build_calendar(
        ag_year_start_month=7,
        start_date=dt.date(2001, 9, 1),
        end_date=dt.date(2002, 8, 15),
        components=[
            ("comp-1", "crop-a", dt.date(2001, 10, 1), dt.date(2002, 8, 1)),
        ],
    )
    clim = _build_climate(dt.date(2002, 1, 1), dt.date(2002, 10, 15))
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    res = compute_sowing_available_water(cal, clim, soil, parameters=params)
    assert [(r.cycle_index, r.component_id, r.sowing_date) for r in res] == [
        (-1, "comp-1", dt.date(2000, 10, 1)),
        (0, "comp-1", dt.date(2001, 10, 1)),
        (1, "comp-1", dt.date(2002, 10, 1)),
    ]
    assert isinstance(res[0].value, Missing)
    assert res[0].value.reason == "NO_COVERAGE"
    assert isinstance(res[1].value, Missing)
    assert res[1].value.reason == "NO_COVERAGE"
    assert isinstance(res[2].value, float)

    # Undated-start component is omitted from sowing occurrences (and leaves
    # subsequent carried storage MISSING_INPUT when it could cover fallow days).
    cal_undated = _build_calendar(
        ag_year_start_month=7,
        start_date=dt.date(2001, 9, 1),
        end_date=dt.date(2002, 8, 15),
        components=[
            ("comp-1", "crop-a", dt.date(2001, 10, 1), dt.date(2002, 8, 1)),
            ("comp-undated", "crop-b", None, dt.date(2002, 8, 10)),
        ],
    )
    res_undated = compute_sowing_available_water(
        cal_undated, clim, soil, parameters=params
    )
    assert [r.component_id for r in res_undated] == ["comp-1", "comp-1", "comp-1"]
    assert isinstance(res_undated[2].value, Missing)
    assert res_undated[2].value.reason == "MISSING_INPUT"

    # Record ends before cycle 1 sowing (2002-10-01) -> NO_COVERAGE.
    clim_short = _build_climate(dt.date(2002, 1, 1), dt.date(2002, 9, 1))
    res_short = compute_sowing_available_water(cal, clim_short, soil, parameters=params)
    assert len(res_short) == 3
    for item in res_short:
        assert isinstance(item.value, Missing)
        assert item.value.reason == "NO_COVERAGE"

    # Non-precipitation series starts after prev_day -> NO_COVERAGE.
    cal_early = _build_calendar(
        components=[
            ("comp-1", "crop-a", dt.date(2001, 7, 4), dt.date(2001, 7, 8)),
        ]
    )
    clim_late_tmax = _build_climate(
        dt.date(2001, 7, 1),
        dt.date(2001, 7, 15),
        series_starts={"air_temperature_max_2m": dt.date(2001, 7, 5)},
    )
    res_late = compute_sowing_available_water(
        cal_early, clim_late_tmax, soil, parameters=params
    )
    assert len(res_late) == 1
    assert isinstance(res_late[0].value, Missing)
    assert res_late[0].value.reason == "NO_COVERAGE"


def test_inputs_not_mutated_g1() -> None:
    cal = _build_calendar()
    clim = _build_climate(dt.date(2001, 7, 1), dt.date(2001, 7, 20))
    soil = _build_soil_slope()
    params = _build_unit_catalogue()

    cal_snap = copy.deepcopy(cal.model_dump())
    clim_snap = copy.deepcopy(clim.model_dump())
    soil_snap = copy.deepcopy(soil.model_dump())
    params_snap = copy.deepcopy(params)

    compute_sowing_available_water(cal, clim, soil, parameters=params)

    assert cal.model_dump() == cal_snap
    assert clim.model_dump() == clim_snap
    assert soil.model_dump() == soil_snap
    assert params == params_snap


# --- D128 chain tests (with PLACEHOLDER climate & 10 PLACEHOLDER records) -----

_D128_CLIMATE_START = dt.date(2001, 1, 1)
_D128_CLIMATE_END = dt.date(2024, 12, 31)

_PLACEHOLDER_STAGE_LENGTHS: dict[str, dict[str, int]] = {
    "wheat": {
        "fao56_stage_length_initial": 11,
        "fao56_stage_length_development": 22,
        "fao56_stage_length_mid": 33,
        "fao56_stage_length_late": 44,
    },
    "maize": {
        "fao56_stage_length_initial": 15,
        "fao56_stage_length_development": 25,
        "fao56_stage_length_mid": 35,
        "fao56_stage_length_late": 15,
    },
}
_PLACEHOLDER_RESIDUE_COVER: dict[str, float] = {
    "wheat": 0.111,
    "maize": 0.222,
}


def _d128_placeholder_10() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for crop, stages in _PLACEHOLDER_STAGE_LENGTHS.items():
        for param_id, value in stages.items():
            key = f"{MARK.lower()}.{param_id}.{crop}"
            records[key] = _unmark(
                _placeholder_record(param_id, {"crop": crop}, value, unit="day")
            )
    for crop, cover in _PLACEHOLDER_RESIDUE_COVER.items():
        key = f"{MARK.lower()}.surface_residue_cover.{crop}.no_crop"
        records[key] = _unmark(
            _placeholder_record(
                "surface_residue_cover",
                {"crop": crop, "management": "no_crop"},
                cover,
                unit="fraction of the soil surface (the table prints percent)",
            )
        )
    return records


@pytest.fixture(scope="module")
def d128_sowing_bundle() -> dict[str, Any]:
    soil_slope = SiteSoilSlope.model_validate_json(
        SOIL_SLOPE_PATH.read_text(encoding="utf-8")
    )
    raw_rotations = json.loads(DEMO_ROTATIONS_PATH.read_text(encoding="utf-8"))
    rotations = {
        entry["rotation_id"]: RotationDefinition.model_validate(entry).model_copy(
            update={"case_id": soil_slope.case_id, "field_id": soil_slope.field_id}
        )
        for entry in raw_rotations
    }
    climate = _build_climate(
        _D128_CLIMATE_START,
        _D128_CLIMATE_END,
        case_id=soil_slope.case_id,
        field_id=soil_slope.field_id,
    )
    records, load_errors = load_folder(RECORDS_DIR)
    assert load_errors == []
    assert check_catalogue(records) == []
    capacity = Catalogue(records).value("column_capacity", (), _D128_CLIMATE_START)
    assert isinstance(capacity, float) and capacity > 0.0
    return {
        "soil_slope": soil_slope,
        "rotations": rotations,
        "climate": climate,
        "catalogue": records,
        "capacity": capacity,
    }


def test_d128_rotation_a_sowing_water_invariants(
    d128_sowing_bundle: dict[str, Any],
) -> None:
    cal_a = build_rotation_calendar(
        d128_sowing_bundle["rotations"]["soybean-winter-fallow"]
    )
    results = compute_sowing_available_water(
        cal_a,
        d128_sowing_bundle["climate"],
        d128_sowing_bundle["soil_slope"],
        parameters=d128_sowing_bundle["catalogue"],
    )
    assert len(results) == 25  # 2000-11-15 .. 2024-11-15
    capacity = d128_sowing_bundle["capacity"]
    for item in results:
        assert item.crop_id == "soybean"
        assert item.unit == UNIT_SOWING_AVAILABLE_WATER
        assert item.sowing_date is not None
        if item.sowing_date < _D128_CLIMATE_START or item.sowing_date > _D128_CLIMATE_END:
            assert isinstance(item.value, Missing)
            assert item.value.reason == "NO_COVERAGE"
        else:
            assert isinstance(item.value, float)
            assert math.isfinite(item.value)
            assert 0.0 <= item.value <= capacity


def test_d128_rotation_b_shipped_catalogue_reports_missing_input(
    d128_sowing_bundle: dict[str, Any],
) -> None:
    cal_b = build_rotation_calendar(
        d128_sowing_bundle["rotations"]["wheat-soybean-maize"]
    )
    results = compute_sowing_available_water(
        cal_b,
        d128_sowing_bundle["climate"],
        d128_sowing_bundle["soil_slope"],
        parameters=d128_sowing_bundle["catalogue"],
    )
    assert len(results) > 0
    for item in results:
        assert item.unit == UNIT_SOWING_AVAILABLE_WATER
        assert item.sowing_date is not None
        assert isinstance(item.value, Missing)
        if item.sowing_date < _D128_CLIMATE_START or item.sowing_date > _D128_CLIMATE_END:
            assert item.value.reason == "NO_COVERAGE"
        else:
            assert item.value.reason == "MISSING_INPUT"


def test_d128_rotation_b_with_10_placeholder_records_computes_all_phases(
    d128_sowing_bundle: dict[str, Any],
) -> None:
    cal_b = build_rotation_calendar(
        d128_sowing_bundle["rotations"]["wheat-soybean-maize"]
    )
    augmented = copy.deepcopy(d128_sowing_bundle["catalogue"])
    augmented.update(_d128_placeholder_10())
    assert check_catalogue(augmented) == []
    capacity = d128_sowing_bundle["capacity"]

    for phase in list_phases(cal_b):
        phased = phase_calendar(cal_b, phase)
        results = compute_sowing_available_water(
            phased,
            d128_sowing_bundle["climate"],
            d128_sowing_bundle["soil_slope"],
            parameters=augmented,
        )
        assert len(results) > 0
        for item in results:
            assert item.unit == UNIT_SOWING_AVAILABLE_WATER
            assert item.sowing_date is not None
            if (
                item.sowing_date < _D128_CLIMATE_START
                or item.sowing_date > _D128_CLIMATE_END
            ):
                assert isinstance(item.value, Missing)
                assert item.value.reason == "NO_COVERAGE"
            else:
                assert isinstance(item.value, float)
                assert math.isfinite(item.value)
                assert 0.0 <= item.value <= capacity
