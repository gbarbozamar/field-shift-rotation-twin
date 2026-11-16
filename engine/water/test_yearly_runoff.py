"""Tests for ``engine.water.yearly_runoff`` (H10 D229/D230 bridge).

Every synthetic climate series, measured runoff table, bound, cap, and test
parameter record defined in this file is a PLACEHOLDER, plainly not real and
not taken from Grahmann et al. (2022). Shipped records come exclusively from
``params/records`` via ``params.catalogue.load_folder``.

Run from the repository root:
    py -3.12 -m pytest engine/water/test_yearly_runoff.py -q
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import DailySeries, DailyValue, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.water import compute_water_deficit_exposure
from engine.water import exposure as ep3
from engine.water import yearly_runoff as module
from engine.water.yearly_runoff import (
    CalendarYearRunoffSummary,
    compute_calendar_year_runoff,
)
from params.catalogue import check_catalogue, load_folder
from validation.h10_runoff import compare_h10_runoff

ROOT = Path(__file__).resolve().parents[2]
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
SOIL_SLOPE_PATH = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"
RECORDS_DIR = ROOT / "params" / "records"

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"


def _unmark(obj: Any) -> Any:
    return json.loads(json.dumps(obj).replace(MARK, UNMARKED))


def _placeholder_record(
    *,
    param_id: str,
    scope: dict[str, str],
    value: float | int,
    unit: str,
) -> dict[str, Any]:
    return _unmark(
        {
            "id": param_id,
            "scope": scope,
            "value": value,
            "unit": unit,
            "range": None,
            "range_missing_reason": f"{MARK} test record without range.",
            "citation": {
                "reference": f"{MARK} test-only parameter record for {param_id}",
                "locator": f"{MARK} test",
            },
            "transcribed_by": f"{MARK} automated test author",
            "checked_by": f"{MARK} automated test reviewer",
            "note": f"{MARK} in-memory test record.",
        }
    )


def _shipped_catalogue() -> dict[str, dict[str, Any]]:
    records, errors = load_folder(RECORDS_DIR)
    assert errors == []
    assert len(records) == 205
    assert check_catalogue(records) == []
    return records


def _soil_slope() -> SiteSoilSlope:
    return SiteSoilSlope.model_validate_json(SOIL_SLOPE_PATH.read_text("utf-8"))


def _d128_calendars(case_id: str, field_id: str) -> dict[str, RotationCalendar]:
    raw = json.loads(DEMO_ROTATIONS_PATH.read_text("utf-8"))
    calendars: dict[str, RotationCalendar] = {}
    for entry in raw:
        rotation = RotationDefinition.model_validate(entry).model_copy(
            update={"case_id": case_id, "field_id": field_id}
        )
        calendars[rotation.rotation_id] = build_rotation_calendar(rotation)
    return calendars


def _build_placeholder_climate(
    case_id: str,
    field_id: str,
    start: dt.date,
    end: dt.date,
    *,
    precip_by_day: dict[dt.date, float | InputsMissing] | None = None,
    precip_unit: str = "mm day-1",
    include_precip: bool = True,
    wind_time_zone: str = "UTC",
) -> SiteClimate:
    dates: list[dt.date] = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += dt.timedelta(days=1)

    patterns: dict[str, list[float]] = {
        # Includes 0.0, small, and large PLACEHOLDER daily values so both zero
        # and positive Curve Number runoff occur.
        "precipitation": [0.0, 0.0, 12.34, 0.0, 55.55, 0.0, 111.11, 0.0],
        "air_temperature_max_2m": [22.2, 24.4, 26.6, 25.5, 23.3],
        "air_temperature_min_2m": [11.1, 12.2, 13.3, 12.2],
        "dew_point_temperature_2m": [8.88, 9.99, 10.11],
        "wind_speed_2m": [1.55, 2.22, 3.11],
        "solar_radiation": [12.34, 15.67, 18.91, 14.56],
    }

    daily_series: list[DailySeries] = []
    for quantity, default_unit in ep3.ACCEPTED_DAILY_UNITS.items():
        if quantity == ep3.PRECIPITATION and not include_precip:
            continue
        seq = patterns[quantity]
        days: list[DailyValue] = []
        for idx, day in enumerate(dates):
            if (
                quantity == ep3.PRECIPITATION
                and precip_by_day is not None
                and day in precip_by_day
            ):
                val = precip_by_day[day]
                if isinstance(val, InputsMissing):
                    days.append(DailyValue(date=day, value=None, missing=val))
                else:
                    days.append(DailyValue(date=day, value=val))
            else:
                days.append(DailyValue(date=day, value=seq[idx % len(seq)]))
        unit = precip_unit if quantity == ep3.PRECIPITATION else default_unit
        tz = wind_time_zone if quantity == "wind_speed_2m" else "UTC"
        daily_series.append(
            DailySeries(
                quantity=quantity,
                unit=unit,
                provenance="DECLARED",
                source=f"{MARK} synthetic daily series",
                range_missing={
                    "reason": "NOT_AVAILABLE",
                    "detail": f"{MARK} synthetic series without range.",
                },
                time_zone=tz,
                start_date=start,
                end_date=end,
                days=days,
            )
        )

    def _point_val(val: float, unit: str) -> dict[str, Any]:
        return {
            "value": val,
            "unit": unit,
            "provenance": "DECLARED",
            "source": f"{MARK} synthetic point coordinate",
            "range_missing": {
                "reason": "NOT_AVAILABLE",
                "detail": f"{MARK} synthetic point without range.",
            },
        }

    return SiteClimate.model_validate(
        {
            "contract": "site_data_climate",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "point": {
                "latitude": _point_val(-30.0, "degree"),
                "longitude": _point_val(-55.0, "degree"),
                "elevation": _point_val(50.0, "m"),
            },
            "daily_series": [s.model_dump(mode="python") for s in daily_series],
            "monthly_series": [],
        }
    )


@pytest.fixture(scope="module")
def bundle() -> dict[str, Any]:
    soil = _soil_slope()
    calendars = _d128_calendars(soil.case_id, soil.field_id)
    catalogue = _shipped_catalogue()
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2017, 1, 1),
        dt.date(2020, 12, 31),
    )
    return {
        "soil": soil,
        "calendars": calendars,
        "catalogue": catalogue,
        "climate": climate,
    }


# --- Delegation to EP3 chain internals & yearly summation --------------------


@pytest.mark.parametrize(
    "rotation_id", ["soybean-winter-fallow", "wheat-soybean-maize"]
)
def test_daily_runoff_matches_ep3_run_chain_day_by_day(
    monkeypatch, bundle: dict[str, Any], rotation_id: str
) -> None:
    calendar = bundle["calendars"][rotation_id]
    climate = bundle["climate"]
    soil = bundle["soil"]
    catalogue = bundle["catalogue"]

    captured: list[list[ep3.ChainDay]] = []
    real_run_chain = ep3._run_chain

    def recording(*args: Any, **kwargs: Any) -> list[ep3.ChainDay]:
        chain = real_run_chain(*args, **kwargs)
        captured.append(chain)
        return chain

    monkeypatch.setattr(ep3, "_run_chain", recording)
    compute_water_deficit_exposure(calendar, climate, soil, parameters=catalogue)
    monkeypatch.undo()
    assert len(captured) == 1
    ep3_daily = {item.date: item.runoff.runoff for item in captured[0]}

    summary = compute_calendar_year_runoff(
        calendar, climate, soil, parameters=catalogue
    )
    assert isinstance(summary, CalendarYearRunoffSummary)
    assert list(summary.daily_runoff) == list(ep3_daily)
    for day, expected in ep3_daily.items():
        assert summary.daily_runoff[day] == expected

    # Physical bounds and exact yearly sum for all complete years (2017..2020).
    precip_series = next(
        s for s in climate.daily_series if s.quantity == ep3.PRECIPITATION
    )
    precip_by_day = {d.date: d.value for d in precip_series.days}
    for day, q in summary.daily_runoff.items():
        assert isinstance(q, float) and math.isfinite(q)
        assert 0.0 <= q <= precip_by_day[day]

    assert any(q > 0.0 for q in summary.daily_runoff.values())
    assert list(summary.yearly_runoff) == [2017, 2018, 2019, 2020]
    for year, total in summary.yearly_runoff.items():
        expected_sum = math.fsum(
            q for d, q in summary.daily_runoff.items() if d.year == year
        )
        assert total == expected_sum


# --- Incomplete calendar years & leap years ----------------------------------


def test_incomplete_calendar_years_stay_no_coverage(bundle: dict[str, Any]) -> None:
    soil = bundle["soil"]
    calendar = bundle["calendars"]["soybean-winter-fallow"]
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2017, 7, 1),
        dt.date(2019, 6, 30),
    )

    summary = compute_calendar_year_runoff(
        calendar, climate, soil, parameters=bundle["catalogue"]
    )
    expected_days = (dt.date(2019, 6, 30) - dt.date(2017, 7, 1)).days + 1
    assert len(summary.daily_runoff) == expected_days
    assert list(summary.yearly_runoff) == [2017, 2018, 2019]

    for incomplete_year in (2017, 2019):
        val = summary.yearly_runoff[incomplete_year]
        assert isinstance(val, Missing)
        assert val.reason == "NO_COVERAGE"

    val_2018 = summary.yearly_runoff[2018]
    assert isinstance(val_2018, float) and math.isfinite(val_2018)
    assert val_2018 == math.fsum(
        q for d, q in summary.daily_runoff.items() if d.year == 2018
    )


def test_leap_year_includes_feb_29_and_missing_feb_29_invalidates_year(
    bundle: dict[str, Any],
) -> None:
    soil = bundle["soil"]
    calendar = bundle["calendars"]["soybean-winter-fallow"]
    leap_day = dt.date(2020, 2, 29)

    # Full leap year (2020: 366 days) + non-leap year (2021: 365 days), with a
    # large PLACEHOLDER rain on Feb 29 so Feb 29 runoff is strictly positive.
    climate_full = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2020, 1, 1),
        dt.date(2021, 12, 31),
        precip_by_day={leap_day: 222.22},
    )
    summary_full = compute_calendar_year_runoff(
        calendar, climate_full, soil, parameters=bundle["catalogue"]
    )
    days_2020 = [d for d in summary_full.daily_runoff if d.year == 2020]
    days_2021 = [d for d in summary_full.daily_runoff if d.year == 2021]
    assert len(days_2020) == 366
    assert len(days_2021) == 365

    feb29_runoff = summary_full.daily_runoff[leap_day]
    assert isinstance(feb29_runoff, float) and feb29_runoff > 0.0
    without_feb29 = math.fsum(
        summary_full.daily_runoff[d] for d in days_2020 if d != leap_day
    )
    assert summary_full.yearly_runoff[2020] == pytest.approx(
        without_feb29 + feb29_runoff, rel=0.0, abs=1e-12
    )
    assert summary_full.yearly_runoff[2020] > without_feb29

    # Leap year with missing Feb 29 -> 2020 must be Missing, 2021 intact.
    climate_gap = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2020, 1, 1),
        dt.date(2021, 12, 31),
        precip_by_day={
            leap_day: InputsMissing(
                reason="MISSING_INPUT", detail=f"{MARK} missing leap day"
            )
        },
    )
    summary_gap = compute_calendar_year_runoff(
        calendar, climate_gap, soil, parameters=bundle["catalogue"]
    )
    assert isinstance(summary_gap.daily_runoff[leap_day], Missing)
    assert summary_gap.daily_runoff[leap_day].reason == "MISSING_INPUT"
    missing_2020 = summary_gap.yearly_runoff[2020]
    assert isinstance(missing_2020, Missing)
    assert missing_2020.reason == "MISSING_INPUT"
    assert "2020-02-29" in (missing_2020.detail or "")
    assert isinstance(summary_gap.yearly_runoff[2021], float)


# --- G4: missingness and failure propagation --------------------------------


def test_g4_missing_precipitation_series_returns_empty_summary(
    bundle: dict[str, Any],
) -> None:
    soil = bundle["soil"]
    calendar = bundle["calendars"]["soybean-winter-fallow"]
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2018, 1, 1),
        dt.date(2019, 12, 31),
        include_precip=False,
    )
    summary = compute_calendar_year_runoff(
        calendar, climate, soil, parameters=bundle["catalogue"]
    )
    assert summary.daily_runoff == {}
    assert summary.yearly_runoff == {}


def test_g4_missing_daily_precipitation_invalidates_only_that_year(
    bundle: dict[str, Any],
) -> None:
    soil = bundle["soil"]
    calendar = bundle["calendars"]["soybean-winter-fallow"]
    gap_day = dt.date(2018, 8, 15)
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2017, 1, 1),
        dt.date(2019, 12, 31),
        precip_by_day={
            gap_day: InputsMissing(
                reason="MISSING_INPUT", detail=f"{MARK} sensor gap"
            )
        },
    )
    summary = compute_calendar_year_runoff(
        calendar, climate, soil, parameters=bundle["catalogue"]
    )
    assert isinstance(summary.yearly_runoff[2017], float)
    assert isinstance(summary.yearly_runoff[2019], float)
    assert isinstance(summary.daily_runoff[gap_day], Missing)
    assert summary.daily_runoff[gap_day].reason == "MISSING_INPUT"
    y2018 = summary.yearly_runoff[2018]
    assert isinstance(y2018, Missing)
    assert y2018.reason == "MISSING_INPUT"
    assert "2018-08-15" in (y2018.detail or "")


@pytest.mark.parametrize(
    "parameter_id",
    [*ep3.RUNOFF_PARAMETERS, ep3.CURVE_NUMBER],
)
def test_g4_missing_runoff_parameter_makes_affected_days_and_years_missing(
    bundle: dict[str, Any], parameter_id: str
) -> None:
    parameters = {
        key: record
        for key, record in bundle["catalogue"].items()
        if record.get("id") != parameter_id
    }
    summary = compute_calendar_year_runoff(
        bundle["calendars"]["soybean-winter-fallow"],
        bundle["climate"],
        bundle["soil"],
        parameters=parameters,
    )
    for day_val in summary.daily_runoff.values():
        assert isinstance(day_val, Missing)
        assert day_val.reason == "MISSING_INPUT"
        assert parameter_id in (day_val.detail or "")
    for year_val in summary.yearly_runoff.values():
        assert isinstance(year_val, Missing)
        assert year_val.reason == "MISSING_INPUT"
        assert parameter_id in (year_val.detail or "")


def test_g4_missing_ag_year_start_month_returns_missing_input(
    bundle: dict[str, Any],
) -> None:
    cal = bundle["calendars"]["soybean-winter-fallow"]
    no_month = cal.model_copy(
        update={
            "ag_year_start": cal.ag_year_start.model_copy(
                update={
                    "month": None,
                    "missing": InputsMissing(
                        reason="MISSING_INPUT", detail=f"{MARK} no start month"
                    ),
                }
            )
        }
    )
    summary = compute_calendar_year_runoff(
        no_month, bundle["climate"], bundle["soil"], parameters=bundle["catalogue"]
    )
    assert all(
        isinstance(v, Missing) and v.reason == "MISSING_INPUT"
        for v in summary.daily_runoff.values()
    )
    assert all(
        isinstance(v, Missing) and v.reason == "MISSING_INPUT"
        for v in summary.yearly_runoff.values()
    )


def test_g4_infeasible_calendar_returns_not_computable(
    bundle: dict[str, Any],
) -> None:
    cal = bundle["calendars"]["soybean-winter-fallow"]
    infeasible = cal.model_copy(
        update={
            "feasibility": cal.feasibility.model_copy(
                update={"feasible": False, "reasons": [f"{MARK} infeasible"]}
            )
        }
    )
    summary = compute_calendar_year_runoff(
        infeasible, bundle["climate"], bundle["soil"], parameters=bundle["catalogue"]
    )
    assert all(
        isinstance(v, Missing) and v.reason == "NOT_COMPUTABLE"
        for v in summary.daily_runoff.values()
    )
    assert all(
        isinstance(v, Missing) and v.reason == "NOT_COMPUTABLE"
        for v in summary.yearly_runoff.values()
    )


def test_g4_mixed_time_zones_returns_not_computable(bundle: dict[str, Any]) -> None:
    soil = bundle["soil"]
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2018, 1, 1),
        dt.date(2018, 12, 31),
        wind_time_zone="America/Montevideo",
    )
    summary = compute_calendar_year_runoff(
        bundle["calendars"]["soybean-winter-fallow"],
        climate,
        soil,
        parameters=bundle["catalogue"],
    )
    assert all(
        isinstance(v, Missing) and v.reason == "NOT_COMPUTABLE"
        for v in summary.daily_runoff.values()
    )
    assert isinstance(summary.yearly_runoff[2018], Missing)
    assert summary.yearly_runoff[2018].reason == "NOT_COMPUTABLE"


def test_g4_wrong_precipitation_unit_returns_missing_input_and_preserves_no_coverage(
    bundle: dict[str, Any],
) -> None:
    soil = bundle["soil"]
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2017, 7, 1),
        dt.date(2018, 12, 31),
        precip_unit="m day-1",
    )
    summary = compute_calendar_year_runoff(
        bundle["calendars"]["soybean-winter-fallow"],
        climate,
        soil,
        parameters=bundle["catalogue"],
    )
    assert all(
        isinstance(v, Missing) and v.reason == "MISSING_INPUT"
        for v in summary.daily_runoff.values()
    )
    assert isinstance(summary.yearly_runoff[2017], Missing)
    assert summary.yearly_runoff[2017].reason == "NO_COVERAGE"
    assert isinstance(summary.yearly_runoff[2018], Missing)
    assert summary.yearly_runoff[2018].reason == "MISSING_INPUT"


def test_g4_non_computable_curve_number_returns_not_computable(
    bundle: dict[str, Any],
) -> None:
    catalogue = copy.deepcopy(bundle["catalogue"])
    replaced = False
    for key, rec in list(catalogue.items()):
        if rec.get("id") == ep3.CURVE_NUMBER and rec.get("scope") == {
            "management": "no_crop"
        }:
            catalogue[key] = _placeholder_record(
                param_id=ep3.CURVE_NUMBER,
                scope={"management": "no_crop"},
                value=0.0,
                unit="dimensionless",
            )
            replaced = True
    assert replaced
    summary = compute_calendar_year_runoff(
        bundle["calendars"]["soybean-winter-fallow"],
        bundle["climate"],
        bundle["soil"],
        parameters=catalogue,
    )
    assert any(
        isinstance(v, Missing)
        and "NOT_COMPUTABLE" in (v.detail or "")
        and "curve_number" in (v.detail or "")
        for v in summary.daily_runoff.values()
    )
    for yval in summary.yearly_runoff.values():
        assert isinstance(yval, Missing)
        assert "NOT_COMPUTABLE" in (yval.detail or "")
        assert "curve_number" in (yval.detail or "")


# --- G3 & G5: caller validation ---------------------------------------------


def test_g3_g5_signature_and_wrong_types_raise_type_error(
    bundle: dict[str, Any],
) -> None:
    sig = inspect.signature(compute_calendar_year_runoff).parameters
    assert list(sig) == ["calendar", "climate", "soil_slope", "parameters"]
    assert all(p.default is inspect.Parameter.empty for p in sig.values())
    assert sig["parameters"].kind is inspect.Parameter.KEYWORD_ONLY

    cal = bundle["calendars"]["soybean-winter-fallow"]
    cli = bundle["climate"]
    soil = bundle["soil"]
    params = bundle["catalogue"]

    with pytest.raises(TypeError, match="parameters"):
        compute_calendar_year_runoff(cal, cli, soil)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        compute_calendar_year_runoff(cal, cli, soil, params)  # type: ignore[misc]

    for arg_name, wrong in (
        ("calendar", cal.model_dump(mode="json")),
        ("calendar", soil),
        ("climate", cli.model_dump(mode="json")),
        ("climate", cal),
        ("soil_slope", soil.model_dump(mode="json")),
        ("soil_slope", cal),
    ):
        kwargs: dict[str, Any] = {
            "calendar": cal,
            "climate": cli,
            "soil_slope": soil,
            "parameters": params,
        }
        kwargs[arg_name] = wrong
        with pytest.raises(TypeError, match=arg_name):
            compute_calendar_year_runoff(**kwargs)

    for bad_params in (
        list(params.values()),
        None,
        {0: {}},
        {"rec.json": "not-a-dict"},
    ):
        with pytest.raises(TypeError, match="parameters"):
            compute_calendar_year_runoff(
                cal, cli, soil, parameters=bad_params  # type: ignore[arg-type]
            )


@pytest.mark.parametrize("argument", ["climate", "soil_slope"])
@pytest.mark.parametrize("field", ["case_id", "field_id"])
def test_g5_different_case_or_field_raises_value_error(
    bundle: dict[str, Any], argument: str, field: str
) -> None:
    kwargs: dict[str, Any] = {
        "calendar": bundle["calendars"]["soybean-winter-fallow"],
        "climate": bundle["climate"],
        "soil_slope": bundle["soil"],
        "parameters": bundle["catalogue"],
    }
    target = kwargs[argument]
    kwargs[argument] = target.model_copy(
        update={field: f"{getattr(target, field)}-other"}
    )
    with pytest.raises(ValueError, match=field):
        compute_calendar_year_runoff(**kwargs)


# --- G1: purity & module hygiene --------------------------------------------


def test_g1_purity_arguments_unchanged_and_deterministic(
    bundle: dict[str, Any],
) -> None:
    for params in (bundle["catalogue"], {}):
        kwargs = {
            "calendar": bundle["calendars"]["soybean-winter-fallow"],
            "climate": bundle["climate"],
            "soil_slope": bundle["soil"],
            "parameters": params,
        }
        snapshot = copy.deepcopy(kwargs)
        first = compute_calendar_year_runoff(**kwargs)
        assert kwargs == snapshot
        assert compute_calendar_year_runoff(**kwargs) == first


def test_g1_module_is_pure_and_holds_no_invented_constants() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            assert top in sys.stdlib_module_names or name.startswith(
                ("contracts.", "engine.")
            ), name
            assert top not in ("os", "io", "pathlib", "socket", "time", "random")
    assert "load_folder" not in source
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers == set()


# --- Direct compatibility with validation.h10_runoff ------------------------


def test_direct_compatibility_with_validation_h10_compare_h10_runoff(
    bundle: dict[str, Any],
) -> None:
    soil = bundle["soil"]
    calendar = bundle["calendars"]["soybean-winter-fallow"]
    # 3 complete PLACEHOLDER years (2017, 2018, 2019) with different daily
    # precipitation magnitudes so each year produces a distinct modelled runoff.
    precip_by_day: dict[dt.date, float] = {
        dt.date(2017, 3, 10): 44.44,
        dt.date(2018, 4, 15): 133.33,
        dt.date(2018, 9, 20): 88.88,
        dt.date(2019, 6, 5): 77.77,
    }
    climate = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2017, 1, 1),
        dt.date(2019, 12, 31),
        precip_by_day=precip_by_day,
    )
    summary = compute_calendar_year_runoff(
        calendar, climate, soil, parameters=bundle["catalogue"]
    )
    assert set(summary.yearly_runoff) == {2017, 2018, 2019}
    assert all(isinstance(v, float) for v in summary.yearly_runoff.values())
    assert len({v for v in summary.yearly_runoff.values()}) == 3

    # Construct PLACEHOLDER measured values matching the exact modelled values
    # (PBIAS = 0%, identical ranking) and PLACEHOLDER bound/cap values.
    placeholder_measured = {
        year: float(val) for year, val in summary.yearly_runoff.items()
    }
    max_daily = max(
        q for q in summary.daily_runoff.values() if isinstance(q, float)
    )
    assert max_daily > 0.0

    flagged_res = compare_h10_runoff(
        placeholder_measured,
        summary.yearly_runoff,
        pbias_bound_percent=10.0,
        event_cap_mm=max_daily / 2.0,
        modelled_daily=summary.daily_runoff,
    )
    assert flagged_res.h10.verdict == "pass"
    assert flagged_res.pbias_percent == 0.0
    assert flagged_res.orders_match is True
    assert flagged_res.large_events.flagged is True
    assert len(flagged_res.large_events.days_above_cap) >= 1
    assert flagged_res.large_events.days_without_value == ()

    clean_res = compare_h10_runoff(
        placeholder_measured,
        summary.yearly_runoff,
        pbias_bound_percent=10.0,
        event_cap_mm=max_daily + 10.0,
        modelled_daily=summary.daily_runoff,
    )
    assert clean_res.h10.verdict == "pass"
    assert clean_res.large_events.flagged is False
    assert clean_res.large_events.days_above_cap == ()

    # Incomplete year (2016) stays Missing("NO_COVERAGE") and passes cleanly into
    # compare_h10_runoff (producing no verdict when included, or passing when
    # comparing only the 3 complete years).
    climate_with_partial = _build_placeholder_climate(
        soil.case_id,
        soil.field_id,
        dt.date(2016, 7, 1),
        dt.date(2019, 12, 31),
        precip_by_day=precip_by_day,
    )
    partial_summary = compute_calendar_year_runoff(
        calendar, climate_with_partial, soil, parameters=bundle["catalogue"]
    )
    assert isinstance(partial_summary.yearly_runoff[2016], Missing)
    assert partial_summary.yearly_runoff[2016].reason == "NO_COVERAGE"

    no_verdict_res = compare_h10_runoff(
        placeholder_measured,
        partial_summary.yearly_runoff,
        pbias_bound_percent=10.0,
        event_cap_mm=max_daily + 10.0,
        modelled_daily=partial_summary.daily_runoff,
    )
    assert no_verdict_res.h10.verdict is None
    assert "2016" in (no_verdict_res.h10.reason or "")
