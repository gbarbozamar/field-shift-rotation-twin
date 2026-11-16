"""Tests for Frontier Unit F-11: multi-year sowing-window sweep.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
)
from contracts.results.models import Missing
from engine.calendar.sowing_window_sweep import (
    ACCEPTED_TEMPERATURE_UNIT,
    HORIZON_KINDS,
    TEMPERATURE_MAX_QUANTITY,
    TEMPERATURE_MIN_QUANTITY,
    CandidateSowingDate,
    ClimateHorizon,
    PhenologyEvaluator,
    PhenologyOutcome,
    RiskCount,
    RiskWindowConfig,
    SowingWindowSweepResult,
    horizon_from_site_climate,
    sweep_sowing_windows,
)

SWEEP_MODULE_PATH = Path(__file__).with_name("sowing_window_sweep.py")


def _build_daily_range(
    start: dt.date,
    end: dt.date,
    *,
    default_tmin: float = 12.0,
    default_tmax: float = 25.0,
    default_water_ratio: float = 0.85,
    tmin_overrides: dict[dt.date, float | Missing] | None = None,
    tmax_overrides: dict[dt.date, float | Missing] | None = None,
    water_overrides: dict[dt.date, float | Missing] | None = None,
) -> tuple[
    dict[dt.date, float | Missing],
    dict[dt.date, float | Missing],
    dict[dt.date, float | Missing],
]:
    tmin: dict[dt.date, float | Missing] = {}
    tmax: dict[dt.date, float | Missing] = {}
    water: dict[dt.date, float | Missing] = {}
    day = start
    one_day = dt.timedelta(days=1)
    while day <= end:
        tmin[day] = (
            tmin_overrides[day]
            if tmin_overrides and day in tmin_overrides
            else default_tmin
        )
        tmax[day] = (
            tmax_overrides[day]
            if tmax_overrides and day in tmax_overrides
            else default_tmax
        )
        water[day] = (
            water_overrides[day]
            if water_overrides and day in water_overrides
            else default_water_ratio
        )
        day += one_day
    return tmin, tmax, water


def _fixed_offset_phenology(
    *,
    days_to_flowering: int,
    days_to_maturity: int,
    harvest_lag: int | None = None,
) -> PhenologyEvaluator:
    def _eval(sowing_date: dt.date) -> PhenologyOutcome:
        flowering = sowing_date + dt.timedelta(days=days_to_flowering)
        maturity = sowing_date + dt.timedelta(days=days_to_maturity)
        harvest = (
            None if harvest_lag is None else maturity + dt.timedelta(days=harvest_lag)
        )
        return PhenologyOutcome(
            sowing_date=sowing_date,
            flowering_date=flowering,
            maturity_date=maturity,
            harvest_date=harvest,
        )

    return _eval


def _base_config(**overrides: object) -> RiskWindowConfig:
    params: dict[str, object] = {
        "pre_days": 5,
        "post_days": 5,
        "frost_threshold_c": 2.0,
        "heat_threshold_c": 34.0,
        "min_heat_consecutive_days": 3,
        "water_ratio_threshold": 0.70,
        "harvest_lag_days": 4,
        "successor_turnaround_days": 2,
        "successor_sowing_mm_dd": "05-15",
    }
    params.update(overrides)
    return RiskWindowConfig(**params)  # type: ignore[arg-type]


def _make_site_climate(
    *,
    start: dt.date,
    end: dt.date,
    tmin_unit: str = ACCEPTED_TEMPERATURE_UNIT,
    tmax_unit: str = ACCEPTED_TEMPERATURE_UNIT,
    tmin_tz: str = "UTC",
    tmax_tz: str = "UTC",
    include_tmin: bool = True,
    include_tmax: bool = True,
    missing_tmin_date: dt.date | None = None,
) -> SiteClimate:
    days: list[dt.date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += dt.timedelta(days=1)

    series_list: list[DailySeries] = []
    if include_tmin:
        series_list.append(
            DailySeries(
                quantity=TEMPERATURE_MIN_QUANTITY,
                unit=tmin_unit,
                provenance="OBSERVED",
                source="PLACEHOLDER_test",
                range_missing=InputsMissing(reason="NO_COVERAGE"),
                time_zone=tmin_tz,
                start_date=start,
                end_date=end,
                days=[
                    DailyValue(
                        date=d,
                        value=None if d == missing_tmin_date else 10.0,
                        missing=(
                            InputsMissing(reason="NO_COVERAGE", detail="fill value")
                            if d == missing_tmin_date
                            else None
                        ),
                    )
                    for d in days
                ],
            )
        )
    if include_tmax:
        series_list.append(
            DailySeries(
                quantity=TEMPERATURE_MAX_QUANTITY,
                unit=tmax_unit,
                provenance="OBSERVED",
                source="PLACEHOLDER_test",
                range_missing=InputsMissing(reason="NO_COVERAGE"),
                time_zone=tmax_tz,
                start_date=start,
                end_date=end,
                days=[DailyValue(date=d, value=25.0) for d in days],
            )
        )

    def _point_val(val: float, unit: str) -> dict[str, object]:
        return {
            "value": val,
            "unit": unit,
            "provenance": "OBSERVED",
            "source": "PLACEHOLDER_test",
            "range_missing": {"reason": "NO_COVERAGE"},
        }

    return SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id="case-f11",
        field_id="field-f11",
        point=ClimatePoint.model_validate(
            {
                "latitude": _point_val(-34.0, "degree"),
                "longitude": _point_val(-57.0, "degree"),
                "elevation": _point_val(50.0, "m"),
            }
        ),
        daily_series=series_list,
        monthly_series=[],
    )


# --- Decoupling, purity, and zero hardcoded thresholds ----------------------


def test_module_does_not_import_thermal_phenology_or_io_modules() -> None:
    tree = ast.parse(SWEEP_MODULE_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

    assert all("thermal_phenology" not in mod for mod in imported)
    forbidden_roots = {
        "os",
        "pathlib",
        "sys",
        "time",
        "urllib",
        "httpx",
        "json",
        "io",
        "random",
        "numpy",
    }
    for mod in imported:
        assert mod.split(".")[0] not in forbidden_roots


def test_risk_window_config_has_no_hardcoded_crop_threshold_defaults() -> None:
    sig = inspect.signature(RiskWindowConfig)
    for required_name in (
        "pre_days",
        "post_days",
        "frost_threshold_c",
        "heat_threshold_c",
        "min_heat_consecutive_days",
        "water_ratio_threshold",
    ):
        assert sig.parameters[required_name].default is inspect.Parameter.empty


def test_phenology_evaluator_protocol_accepts_plain_callable() -> None:
    fn = _fixed_offset_phenology(days_to_flowering=60, days_to_maturity=130)
    assert isinstance(fn, PhenologyEvaluator)


# --- Flowering window, boundaries, and k-of-n hazard counts -----------------


def test_flowering_window_boundaries_frost_heat_and_water_stress() -> None:
    # Candidate 10-15 across 2020..2023; flowering = +60d -> Dec 14 (2020 leap: Dec 14)
    # Window with pre_days=2, post_days=2 -> [flowering - 2, flowering + 2] (5 days)
    config = _base_config(
        pre_days=2,
        post_days=2,
        frost_threshold_c=2.0,
        heat_threshold_c=34.0,
        min_heat_consecutive_days=3,
        water_ratio_threshold=0.70,
    )
    pheno = _fixed_offset_phenology(days_to_flowering=60, days_to_maturity=120)

    fl_2020 = dt.date(2020, 10, 15) + dt.timedelta(days=60)  # 2020-12-14
    fl_2021 = dt.date(2021, 10, 15) + dt.timedelta(days=60)  # 2021-12-14
    fl_2022 = dt.date(2022, 10, 15) + dt.timedelta(days=60)  # 2022-12-14
    fl_2023 = dt.date(2023, 10, 15) + dt.timedelta(days=60)  # 2023-12-14

    tmin_over: dict[dt.date, float | Missing] = {
        # 2020: frost strictly inside window on left endpoint (1.9 < 2.0) -> FROST
        fl_2020 - dt.timedelta(days=2): 1.9,
        # 2021: equality on threshold (2.0 == 2.0) -> NOT frost; frost outside window -> ignored
        fl_2021: 2.0,
        fl_2021 - dt.timedelta(days=3): -1.0,
        fl_2021 + dt.timedelta(days=3): -1.0,
    }
    tmax_over: dict[dt.date, float | Missing] = {
        # 2020: 3 consecutive days > 34.0 -> HEAT
        fl_2020 - dt.timedelta(days=1): 34.1,
        fl_2020: 35.0,
        fl_2020 + dt.timedelta(days=1): 34.5,
        # 2021: 2 hot days, gap (34.0 == threshold, NOT >), 2 hot days -> NOT heat
        fl_2021 - dt.timedelta(days=2): 36.0,
        fl_2021 - dt.timedelta(days=1): 36.0,
        fl_2021: 34.0,
        fl_2021 + dt.timedelta(days=1): 36.0,
        fl_2021 + dt.timedelta(days=2): 36.0,
        # 2022: hot days outside window plus 2 inside -> only 2 inside -> NOT heat
        fl_2022 - dt.timedelta(days=3): 38.0,
        fl_2022 - dt.timedelta(days=2): 38.0,
        fl_2022 - dt.timedelta(days=1): 38.0,
    }
    water_over: dict[dt.date, float | Missing] = {
        # 2020: window mean = (0.50 + 4*0.75)/5 = 0.70 -> == 0.70 -> NOT stress (strict <)
        fl_2020: 0.50,
        fl_2020 - dt.timedelta(days=2): 0.75,
        fl_2020 - dt.timedelta(days=1): 0.75,
        fl_2020 + dt.timedelta(days=1): 0.75,
        fl_2020 + dt.timedelta(days=2): 0.75,
        # 2022: mean < 0.70 -> STRESS
        fl_2022 - dt.timedelta(days=1): 0.40,
        fl_2022: 0.40,
        fl_2022 + dt.timedelta(days=1): 0.40,
        # 2023: frost + heat + water stress simultaneously (mean = 0.69 < 0.70)
        fl_2023: 0.05,
    }
    tmin_over[fl_2023 + dt.timedelta(days=2)] = 0.5
    for offset in (0, 1, 2):
        tmax_over[fl_2023 + dt.timedelta(days=offset)] = 36.0

    tmin, tmax, water = _build_daily_range(
        dt.date(2020, 1, 1),
        dt.date(2024, 12, 31),
        tmin_overrides=tmin_over,
        tmax_overrides=tmax_over,
        water_overrides=water_over,
    )

    horizon = ClimateHorizon(
        horizon_id="hist_1",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2020, 2021, 2022, 2023],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )

    res = sweep_sowing_windows(["10-15"], [horizon], config)
    assert isinstance(res, SowingWindowSweepResult)
    assert res.orientation_only is True
    assert res.replaces_agronomist_recommendation is False
    assert res.horizons_pooled is False

    summary = res.get_horizon("hist_1").get_candidate("10-15")
    assert len(summary.evaluated_years) == 4
    assert summary.unevaluated_years == ()

    # Frost: 2020 and 2023 -> 2 of 4
    assert summary.flowering_frost_risk.events_count == 2
    assert summary.flowering_frost_risk.evaluated_years == 4
    assert summary.flowering_frost_risk.rate == pytest.approx(0.5)
    # Heat: 2020 and 2023 -> 2 of 4
    assert summary.flowering_heat_risk.events_count == 2
    assert summary.flowering_heat_risk.rate == pytest.approx(0.5)
    # Water stress: 2022 and 2023 -> 2 of 4
    assert summary.critical_water_stress_risk.events_count == 2
    assert summary.critical_water_stress_risk.rate == pytest.approx(0.5)


def test_critical_period_water_modes_transpiration_pair_and_evaluator() -> None:
    tmin, tmax, _ = _build_daily_range(
        dt.date(2021, 1, 1),
        dt.date(2022, 12, 31),
        default_tmin=10.0,
        default_tmax=26.0,
    )
    pheno = _fixed_offset_phenology(days_to_flowering=50, days_to_maturity=110)
    # Separate critical-period window [flowering - 1, flowering + 3]
    config = _base_config(
        pre_days=2,
        post_days=2,
        critical_pre_days=1,
        critical_post_days=3,
        water_ratio_threshold=0.65,
    )

    # Mode 1: transpiration_by_date + transpiration_demanded_by_date
    # Sum(T) / Sum(T_dem) = (2*1.0 + 3*4.0) / (5*4.0) = 14 / 20 = 0.70 (>= 0.65 -> no stress)
    fl_2021 = dt.date(2021, 10, 1) + dt.timedelta(days=50)
    t_actual: dict[dt.date, float | Missing] = {}
    t_demanded: dict[dt.date, float | Missing] = {}
    for offset in range(-1, 4):
        d = fl_2021 + dt.timedelta(days=offset)
        t_actual[d] = 1.0 if offset < 1 else 4.0
        t_demanded[d] = 4.0

    h_pair = ClimateHorizon(
        horizon_id="pair_mode",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_by_date=t_actual,
        transpiration_demanded_by_date=t_demanded,
    )

    # Mode 2: critical_water_evaluator returning 0.60 (< 0.65 -> stress)
    observed_windows: list[tuple[dt.date, dt.date]] = []

    def _water_eval(start: dt.date, end: dt.date) -> float:
        observed_windows.append((start, end))
        return 0.60

    h_eval = ClimateHorizon(
        horizon_id="eval_mode",
        horizon_kind="synthetic",
        source_tag="MARKOV_SYNTHETIC",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        critical_water_evaluator=_water_eval,
    )

    res = sweep_sowing_windows(["10-01"], [h_pair, h_eval], config)
    pair_cand = res.get_horizon("pair_mode").get_candidate("10-01")
    assert pair_cand.critical_water_stress_risk.events_count == 0
    assert pair_cand.evaluated_years[0].critical_transpiration_ratio == pytest.approx(
        0.70
    )

    eval_cand = res.get_horizon("eval_mode").get_candidate("10-01")
    assert eval_cand.critical_water_stress_risk.events_count == 1
    assert eval_cand.evaluated_years[0].critical_transpiration_ratio == pytest.approx(
        0.60
    )
    assert observed_windows == [
        (fl_2021 - dt.timedelta(days=1), fl_2021 + dt.timedelta(days=3))
    ]


# --- Separated climate horizons: never pooled or averaged -------------------


def test_separated_horizons_historical_synthetic_nex_isimip_never_average() -> None:
    # Overlapping future years 2040..2041 for NEX-GDDP-CMIP6 and ISIMIP3b must
    # remain strictly separated with their own phenology evaluators and tags.
    config = _base_config(
        pre_days=1,
        post_days=1,
        frost_threshold_c=1.0,
        heat_threshold_c=33.0,
        min_heat_consecutive_days=2,
        water_ratio_threshold=0.75,
    )

    tmin_hist, tmax_hist, water_hist = _build_daily_range(
        dt.date(2015, 1, 1), dt.date(2017, 12, 31), default_tmax=27.0
    )
    tmin_syn, tmax_syn, water_syn = _build_daily_range(
        dt.date(2015, 1, 1), dt.date(2017, 12, 31), default_tmax=28.0
    )
    # Future NEX: cool/wet (no heat); Future ISIMIP3b: hot (heat in both years)
    tmin_nex, tmax_nex, water_nex = _build_daily_range(
        dt.date(2040, 1, 1), dt.date(2042, 12, 31), default_tmax=29.0
    )
    tmin_isi, tmax_isi, water_isi = _build_daily_range(
        dt.date(2040, 1, 1), dt.date(2042, 12, 31), default_tmax=36.0
    )

    horizons = [
        ClimateHorizon(
            horizon_id="hist_power",
            horizon_kind="historical",
            source_tag="NASA_POWER",
            tmin_by_date=tmin_hist,
            tmax_by_date=tmax_hist,
            years=[2015, 2016],
            transpiration_ratio_by_date=water_hist,
        ),
        ClimateHorizon(
            horizon_id="syn_markov",
            horizon_kind="synthetic",
            source_tag="SYNTHETIC_MARKOV",
            tmin_by_date=tmin_syn,
            tmax_by_date=tmax_syn,
            years=[2015, 2016],
            transpiration_ratio_by_date=water_syn,
        ),
        ClimateHorizon(
            horizon_id="fut_nex_ssp245",
            horizon_kind="future",
            source_tag="NEX-GDDP-CMIP6",
            tmin_by_date=tmin_nex,
            tmax_by_date=tmax_nex,
            years=[2040, 2041],
            transpiration_ratio_by_date=water_nex,
        ),
        ClimateHorizon(
            horizon_id="fut_isimip3b_ssp585",
            horizon_kind="future",
            source_tag="ISIMIP3b",
            tmin_by_date=tmin_isi,
            tmax_by_date=tmax_isi,
            years=[2040, 2041],
            transpiration_ratio_by_date=water_isi,
        ),
    ]

    evaluators = {
        "hist_power": _fixed_offset_phenology(
            days_to_flowering=65, days_to_maturity=135
        ),
        "syn_markov": _fixed_offset_phenology(
            days_to_flowering=65, days_to_maturity=135
        ),
        "fut_nex_ssp245": _fixed_offset_phenology(
            days_to_flowering=58, days_to_maturity=125
        ),
        "fut_isimip3b_ssp585": _fixed_offset_phenology(
            days_to_flowering=52, days_to_maturity=115
        ),
    }

    res = sweep_sowing_windows(
        ["11-01"], horizons, config, phenology_evaluator=evaluators
    )
    assert res.horizons_pooled is False
    assert res.horizon_keys == (
        ("hist_power", "historical", "NASA_POWER"),
        ("syn_markov", "synthetic", "SYNTHETIC_MARKOV"),
        ("fut_nex_ssp245", "future", "NEX-GDDP-CMIP6"),
        ("fut_isimip3b_ssp585", "future", "ISIMIP3b"),
    )
    assert len(res.horizons_of_kind("historical")) == 1
    assert len(res.horizons_of_kind("synthetic")) == 1
    assert len(res.horizons_of_kind("future")) == 2

    nex_sum = res.get_horizon("fut_nex_ssp245").get_candidate("11-01")
    isi_sum = res.get_horizon("fut_isimip3b_ssp585").get_candidate("11-01")
    assert nex_sum.flowering_heat_risk.events_count == 0
    assert nex_sum.flowering_heat_risk.rate == pytest.approx(0.0)
    assert isi_sum.flowering_heat_risk.events_count == 2
    assert isi_sum.flowering_heat_risk.rate == pytest.approx(1.0)
    assert nex_sum.earliest_maturity_date != isi_sum.earliest_maturity_date


# --- Shifted maturity, successor entry, and bare-soil fallow duration -------


def test_shifted_maturity_successor_entry_and_bare_soil_fallow_tracking() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2020, 1, 1), dt.date(2023, 12, 31))
    # Sowing 10-15 matures in 150d -> Mar 14 (2020-21) / Mar 14; harvest +5d -> Mar 19;
    # turnaround +3d -> Mar 22 <= 05-15 successor (feasible, fallow = 56 days)
    # Sowing 12-20 matures in 150d -> May 19 -> harvest May 24 > 05-15 successor (conflict!)
    config = _base_config(
        pre_days=1,
        post_days=1,
        harvest_lag_days=5,
        successor_turnaround_days=3,
        successor_sowing_mm_dd="05-15",
    )
    pheno = _fixed_offset_phenology(days_to_flowering=60, days_to_maturity=150)
    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021, 2022],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )

    res = sweep_sowing_windows(["10-15", "12-20"], [horizon], config)
    early = res.get_horizon("hist").get_candidate("10-15")
    assert early.successor_conflict_years == ()
    y21 = early.evaluated_years[0]
    assert y21.maturity_date == dt.date(2022, 3, 14)
    assert y21.harvest_date == dt.date(2022, 3, 19)
    assert y21.successor_entry_earliest_date == dt.date(2022, 3, 22)
    assert y21.next_sowing_date == dt.date(2022, 5, 15)
    # Strictly between Mar 19 and May 15 -> (57 - 1) = 56 bare-soil days
    assert y21.bare_soil_fallow_days == 56
    assert y21.successor_window_feasible is True
    assert early.mean_bare_soil_fallow_days == pytest.approx(56.0)
    assert early.min_bare_soil_fallow_days == 56
    assert early.max_bare_soil_fallow_days == 56

    late = res.get_horizon("hist").get_candidate("12-20")
    assert late.successor_conflict_years == (2021, 2022)
    assert isinstance(late.evaluated_years[0].bare_soil_fallow_days, Missing)
    assert late.evaluated_years[0].bare_soil_fallow_days.reason == "NOT_COMPUTABLE"
    assert late.evaluated_years[0].successor_window_feasible is False
    assert isinstance(late.mean_bare_soil_fallow_days, Missing)
    assert late.mean_bare_soil_fallow_days.reason == "NOT_COMPUTABLE"


def test_turnaround_gap_conflict_with_non_negative_fallow_and_leap_day() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2020, 1, 1), dt.date(2022, 12, 31))
    # 2020-02-29 stays Feb 29; 2021-02-29 adjusts to 2021-02-28.
    # Maturity +80d, harvest_lag=0, turnaround=10, successor="05-20":
    # 2020-02-29 + 80d = 2020-05-19 (harvest May 19, successor May 20 -> fallow 0 days,
    # but earliest entry May 29 > May 20 -> successor_window_feasible=False).
    config = _base_config(
        pre_days=1,
        post_days=1,
        harvest_lag_days=0,
        successor_turnaround_days=10,
        successor_sowing_mm_dd="05-20",
    )
    pheno = _fixed_offset_phenology(days_to_flowering=40, days_to_maturity=80)
    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2020, 2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )

    res = sweep_sowing_windows(["02-29"], [horizon], config)
    summary = res.get_horizon("hist").get_candidate("02-29")
    assert summary.evaluated_years[0].sowing_date == dt.date(2020, 2, 29)
    assert summary.evaluated_years[0].leap_day_adjusted is False
    assert summary.evaluated_years[0].bare_soil_fallow_days == 0
    assert summary.evaluated_years[0].successor_window_feasible is False
    assert summary.evaluated_years[1].sowing_date == dt.date(2021, 2, 28)
    assert summary.evaluated_years[1].leap_day_adjusted is True
    assert summary.successor_conflict_years == (2020, 2021)


def test_annual_next_cycle_fallow_when_successor_sowing_not_declared() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2021, 1, 1), dt.date(2023, 12, 31))
    config = _base_config(
        pre_days=1,
        post_days=1,
        harvest_lag_days=0,
        successor_turnaround_days=0,
        successor_sowing_mm_dd=None,
    )
    pheno = _fixed_offset_phenology(days_to_flowering=60, days_to_maturity=150)
    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )
    res = sweep_sowing_windows(["10-01"], [horizon], config)
    y21 = res.get_horizon("hist").get_candidate("10-01").evaluated_years[0]
    assert y21.next_sowing_date == dt.date(2022, 10, 1)
    # 2021-10-01 + 150d = 2022-02-28; strictly between Feb 28 and Oct 1 = 215 - 1 = 214
    assert (
        y21.bare_soil_fallow_days == (dt.date(2022, 10, 1) - y21.harvest_date).days - 1
    )


# --- Missing data stays typed Missing in unevaluated_years (never zero!) -----


def test_missing_phenology_climate_and_water_keep_years_unevaluated_never_zero() -> (
    None
):
    config = _base_config(pre_days=1, post_days=1)

    def _pheno(sowing_date: dt.date) -> PhenologyOutcome | Missing:
        if sowing_date.year == 2020:
            return Missing(reason="MISSING_INPUT", detail="2020 phenology gap")
        if sowing_date.year == 2021:
            return PhenologyOutcome(
                sowing_date=sowing_date,
                flowering_date=Missing(
                    reason="NOT_COMPUTABLE", detail="thermal sum incomplete"
                ),
                maturity_date=sowing_date + dt.timedelta(days=120),
            )
        return PhenologyOutcome(
            sowing_date=sowing_date,
            flowering_date=sowing_date + dt.timedelta(days=50),
            maturity_date=sowing_date + dt.timedelta(days=120),
        )

    fl_2022 = dt.date(2022, 10, 1) + dt.timedelta(days=50)
    fl_2023 = dt.date(2023, 10, 1) + dt.timedelta(days=50)

    tmin, tmax, water = _build_daily_range(
        dt.date(2020, 1, 1),
        dt.date(2024, 12, 31),
        tmin_overrides={fl_2022: Missing(reason="NO_COVERAGE", detail="sensor gap")},
        tmax_overrides={fl_2023: float("nan")},
    )
    # 2024 water missing on flowering day
    fl_2024 = dt.date(2024, 10, 1) + dt.timedelta(days=50)
    water[fl_2024] = Missing(reason="MISSING_INPUT", detail="ET0 absent")

    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2020, 2021, 2022, 2023, 2024],
        phenology_evaluator=_pheno,
        transpiration_ratio_by_date=water,
    )

    res = sweep_sowing_windows(["10-01"], [horizon], config)
    summary = res.get_horizon("hist").get_candidate("10-01")
    assert summary.evaluated_years == ()
    assert [u.year for u in summary.unevaluated_years] == [2020, 2021, 2022, 2023, 2024]
    assert [u.missing.reason for u in summary.unevaluated_years] == [
        "MISSING_INPUT",
        "NOT_COMPUTABLE",
        "NO_COVERAGE",
        "NOT_COMPUTABLE",
        "MISSING_INPUT",
    ]

    # When n == 0, counts and rates and maturity/fallow summaries are Missing, NEVER 0!
    for risk in (
        summary.flowering_frost_risk,
        summary.flowering_heat_risk,
        summary.critical_water_stress_risk,
    ):
        assert risk.evaluated_years == 0
        assert isinstance(risk.events_count, Missing)
        assert isinstance(risk.rate, Missing)

    assert isinstance(summary.earliest_maturity_date, Missing)
    assert isinstance(summary.latest_maturity_date, Missing)
    assert isinstance(summary.earliest_successor_entry_date, Missing)
    assert isinstance(summary.latest_successor_entry_date, Missing)
    assert isinstance(summary.mean_bare_soil_fallow_days, Missing)
    assert isinstance(summary.min_bare_soil_fallow_days, Missing)
    assert isinstance(summary.max_bare_soil_fallow_days, Missing)


def test_missing_water_source_or_zero_demanded_keeps_years_unevaluated() -> None:
    tmin, tmax, _ = _build_daily_range(dt.date(2021, 1, 1), dt.date(2022, 12, 31))
    pheno = _fixed_offset_phenology(days_to_flowering=50, days_to_maturity=120)
    config = _base_config(pre_days=1, post_days=1)

    no_water = ClimateHorizon(
        horizon_id="no_water",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
    )
    res_no_water = sweep_sowing_windows(["10-01"], [no_water], config)
    s_no_water = res_no_water.get_horizon("no_water").get_candidate("10-01")
    assert len(s_no_water.unevaluated_years) == 1
    assert s_no_water.unevaluated_years[0].missing.reason == "MISSING_INPUT"
    assert isinstance(s_no_water.critical_water_stress_risk.events_count, Missing)

    fl_2021 = dt.date(2021, 10, 1) + dt.timedelta(days=50)
    zero_dem = {fl_2021 + dt.timedelta(days=o): 0.0 for o in (-1, 0, 1)}
    zero_act = {fl_2021 + dt.timedelta(days=o): 0.0 for o in (-1, 0, 1)}
    h_zero_dem = ClimateHorizon(
        horizon_id="zero_dem",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_by_date=zero_act,
        transpiration_demanded_by_date=zero_dem,
    )
    res_zero = sweep_sowing_windows(["10-01"], [h_zero_dem], config)
    s_zero = res_zero.get_horizon("zero_dem").get_candidate("10-01")
    assert len(s_zero.unevaluated_years) == 1
    assert s_zero.unevaluated_years[0].missing.reason == "NOT_COMPUTABLE"


def test_infeasible_phenology_date_order_is_unevaluated_not_computable() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2021, 1, 1), dt.date(2022, 12, 31))
    config = _base_config(pre_days=1, post_days=1)

    def _bad_pheno(sowing_date: dt.date) -> PhenologyOutcome:
        return PhenologyOutcome(
            sowing_date=sowing_date,
            flowering_date=sowing_date - dt.timedelta(days=1),
            maturity_date=sowing_date + dt.timedelta(days=100),
        )

    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=_bad_pheno,
        transpiration_ratio_by_date=water,
    )
    res = sweep_sowing_windows(["10-01"], [horizon], config)
    summary = res.get_horizon("hist").get_candidate("10-01")
    assert summary.evaluated_years == ()
    assert summary.unevaluated_years[0].missing.reason == "NOT_COMPUTABLE"


# --- SiteClimate adapter helper ---------------------------------------------


def test_horizon_from_site_climate_extracts_series_and_guards_units_and_tz() -> None:
    start = dt.date(2021, 1, 1)
    end = dt.date(2022, 12, 31)
    missing_day = dt.date(2021, 11, 20)
    climate = _make_site_climate(start=start, end=end, missing_tmin_date=missing_day)
    _, _, water = _build_daily_range(start, end)
    pheno = _fixed_offset_phenology(days_to_flowering=50, days_to_maturity=120)
    config = _base_config(pre_days=1, post_days=1)

    horizon = horizon_from_site_climate(
        climate,
        horizon_id="site_hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        years=[2021, 2022],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )
    res = sweep_sowing_windows(["10-01"], [horizon], config)
    summary = res.get_horizon("site_hist").get_candidate("10-01")
    # 2021-10-01 + 50d = 2021-11-20 -> missing_day inside window -> 2021 unevaluated!
    assert [u.year for u in summary.unevaluated_years] == [2021]
    assert summary.unevaluated_years[0].missing.reason == "NO_COVERAGE"
    assert [e.year for e in summary.evaluated_years] == [2022]

    # Wrong unit -> MISSING_INPUT across years (no unit conversion)
    wrong_unit = _make_site_climate(start=start, end=end, tmin_unit="K")
    h_unit = horizon_from_site_climate(
        wrong_unit,
        horizon_id="bad_unit",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )
    assert h_unit.series_missing is not None
    assert h_unit.series_missing.reason == "MISSING_INPUT"

    # Mixed time zones -> NOT_COMPUTABLE (C6.3)
    mixed_tz = _make_site_climate(
        start=start, end=end, tmin_tz="UTC", tmax_tz="America/Montevideo"
    )
    h_tz = horizon_from_site_climate(
        mixed_tz,
        horizon_id="bad_tz",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )
    assert h_tz.series_missing is not None
    assert h_tz.series_missing.reason == "NOT_COMPUTABLE"

    # Missing series -> MISSING_INPUT
    missing_series = _make_site_climate(start=start, end=end, include_tmin=False)
    h_miss = horizon_from_site_climate(
        missing_series,
        horizon_id="no_tmin",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )
    assert h_miss.series_missing is not None
    assert h_miss.series_missing.reason == "MISSING_INPUT"


# --- Orientation-only invariants, frozen dataclasses, G1 & G5 checks --------


def test_orientation_only_and_pooled_guards_cannot_be_bypassed() -> None:
    with pytest.raises(ValueError, match="orientation_only"):
        RiskCount(
            events_count=1,
            evaluated_years=2,
            rate=0.5,
            orientation_only=False,
        )
    with pytest.raises(ValueError, match="replaces_agronomist_recommendation"):
        RiskCount(
            events_count=1,
            evaluated_years=2,
            rate=0.5,
            replaces_agronomist_recommendation=True,
        )
    with pytest.raises(ValueError, match="horizons_pooled"):
        SowingWindowSweepResult(horizons=(), horizons_pooled=True)

    rc = RiskCount(events_count=1, evaluated_years=2, rate=0.5)
    with pytest.raises(FrozenInstanceError):
        rc.events_count = 0  # type: ignore[misc]


def test_g1_purity_and_determinism_and_caller_arguments_unmodified() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2020, 1, 1), dt.date(2022, 12, 31))
    tmin_snapshot = copy.deepcopy(tmin)
    tmax_snapshot = copy.deepcopy(tmax)
    water_snapshot = copy.deepcopy(water)
    candidates = ["10-15", "11-01"]
    candidates_snapshot = list(candidates)

    config = _base_config()
    pheno = _fixed_offset_phenology(days_to_flowering=60, days_to_maturity=130)
    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2020, 2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )

    first = sweep_sowing_windows(candidates, [horizon], config)
    second = sweep_sowing_windows(candidates, [horizon], config)
    assert first == second
    assert tmin == tmin_snapshot
    assert tmax == tmax_snapshot
    assert water == water_snapshot
    assert candidates == candidates_snapshot


def test_g5_type_and_value_error_validation() -> None:
    tmin, tmax, water = _build_daily_range(dt.date(2021, 1, 1), dt.date(2022, 12, 31))
    pheno = _fixed_offset_phenology(days_to_flowering=50, days_to_maturity=120)
    config = _base_config()
    horizon = ClimateHorizon(
        horizon_id="hist",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        transpiration_ratio_by_date=water,
    )

    with pytest.raises(TypeError):
        CandidateSowingDate.parse(1015)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CandidateSowingDate.parse("2021-10-15")
    with pytest.raises(ValueError):
        CandidateSowingDate.parse("02-30")
    with pytest.raises(TypeError):
        _base_config(pre_days=True)
    with pytest.raises(ValueError):
        _base_config(pre_days=-1)
    with pytest.raises(ValueError):
        _base_config(min_heat_consecutive_days=0)
    with pytest.raises(ValueError):
        _base_config(frost_threshold_c=float("nan"))
    with pytest.raises(ValueError):
        _base_config(water_ratio_threshold=-0.1)

    assert set(HORIZON_KINDS) == {"historical", "synthetic", "future"}
    with pytest.raises(ValueError):
        ClimateHorizon(
            horizon_id="bad_kind",
            horizon_kind="projected",  # type: ignore[arg-type]
            source_tag="NEX-GDDP-CMIP6",
            tmin_by_date=tmin,
            tmax_by_date=tmax,
        )
    with pytest.raises(ValueError):
        ClimateHorizon(
            horizon_id="bad_water_modes",
            horizon_kind="future",
            source_tag="ISIMIP3b",
            tmin_by_date=tmin,
            tmax_by_date=tmax,
            transpiration_ratio_by_date=water,
            critical_water_evaluator=lambda s, e: 0.8,
        )
    with pytest.raises(ValueError):
        ClimateHorizon(
            horizon_id="half_pair",
            horizon_kind="future",
            source_tag="ISIMIP3b",
            tmin_by_date=tmin,
            tmax_by_date=tmax,
            transpiration_by_date=water,
        )

    with pytest.raises(TypeError):
        sweep_sowing_windows("10-15", [horizon], config)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        sweep_sowing_windows(["10-15", "10-15"], [horizon], config)
    with pytest.raises(ValueError):
        sweep_sowing_windows(["10-15"], [horizon, horizon], config)
    with pytest.raises(TypeError):
        sweep_sowing_windows(["10-15"], [horizon], "not-config")  # type: ignore[arg-type]

    no_pheno_horizon = ClimateHorizon(
        horizon_id="no_pheno",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        transpiration_ratio_by_date=water,
    )
    with pytest.raises(ValueError):
        sweep_sowing_windows(["10-15"], [no_pheno_horizon], config)


def test_inferred_years_out_of_coverage_explicit_harvest_and_single_day_window() -> (
    None
):
    # Inferred years from 2021-01-01..2022-01-10: candidate 11-15 in 2021 flowers
    # +60d = 2022-01-14, which falls outside climate end 2022-01-10 -> NO_COVERAGE.
    tmin, tmax, water = _build_daily_range(dt.date(2021, 1, 1), dt.date(2022, 1, 10))
    config = _base_config(
        pre_days=0,
        post_days=0,
        harvest_lag_days=10,
        successor_turnaround_days=2,
        successor_sowing_mm_dd="05-15",
    )

    def _explicit_harvest_pheno(sowing_date: dt.date) -> PhenologyOutcome:
        return PhenologyOutcome(
            sowing_date=sowing_date,
            flowering_date=sowing_date + dt.timedelta(days=60),
            maturity_date=sowing_date + dt.timedelta(days=120),
            harvest_date=sowing_date + dt.timedelta(days=123),
        )

    horizon = ClimateHorizon(
        horizon_id="inferred",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=None,
        phenology_evaluator=_explicit_harvest_pheno,
        transpiration_ratio_by_date=water,
    )

    # Candidate 02-01 in 2021 flowers 2021-04-02 (single-day window covered)
    # Candidate 02-01 in 2022 flowers 2022-04-02 (not covered -> NO_COVERAGE)
    res = sweep_sowing_windows(["02-01", "11-15"], [horizon], config)
    h_res = res.get_horizon("inferred")

    feb_sum = h_res.get_candidate("02-01")
    assert [e.year for e in feb_sum.evaluated_years] == [2021]
    assert [u.year for u in feb_sum.unevaluated_years] == [2022]
    assert feb_sum.unevaluated_years[0].missing.reason == "NO_COVERAGE"
    e21 = feb_sum.evaluated_years[0]
    # Explicit harvest_date (+123d) overrides harvest_lag_days=10
    assert e21.harvest_date == dt.date(2021, 2, 1) + dt.timedelta(days=123)
    assert e21.flowering_window_start == e21.flowering_date
    assert e21.flowering_window_end == e21.flowering_date

    nov_sum = h_res.get_candidate("11-15")
    assert nov_sum.evaluated_years == ()
    assert [u.year for u in nov_sum.unevaluated_years] == [2021, 2022]
    assert all(u.missing.reason == "NO_COVERAGE" for u in nov_sum.unevaluated_years)

    # Empty candidates or empty horizons return empty tuples cleanly
    empty_cands = sweep_sowing_windows([], [horizon], config)
    assert empty_cands.get_horizon("inferred").candidates == ()
    empty_horizons = sweep_sowing_windows(["02-01"], [], config)
    assert empty_horizons.horizons == ()


def test_evaluator_edge_failures_and_bad_return_guards() -> None:
    tmin, tmax, _ = _build_daily_range(dt.date(2021, 1, 1), dt.date(2022, 12, 31))
    config = _base_config(pre_days=1, post_days=1)
    pheno = _fixed_offset_phenology(days_to_flowering=50, days_to_maturity=120)

    h_nan_water = ClimateHorizon(
        horizon_id="nan_water",
        horizon_kind="future",
        source_tag="ISIMIP3b",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=pheno,
        critical_water_evaluator=lambda s, e: float("nan"),
    )
    res_nan = sweep_sowing_windows(["10-01"], [h_nan_water], config)
    assert (
        res_nan.get_horizon("nan_water")
        .get_candidate("10-01")
        .unevaluated_years[0]
        .missing.reason
        == "NOT_COMPUTABLE"
    )

    h_wrong_sowing = ClimateHorizon(
        horizon_id="wrong_sowing",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=lambda d: PhenologyOutcome(
            sowing_date=d + dt.timedelta(days=1),
            flowering_date=d + dt.timedelta(days=50),
            maturity_date=d + dt.timedelta(days=120),
        ),
        critical_water_evaluator=lambda s, e: 0.9,
    )
    with pytest.raises(ValueError, match="expected 2021-10-01"):
        sweep_sowing_windows(["10-01"], [h_wrong_sowing], config)

    h_wrong_type = ClimateHorizon(
        horizon_id="wrong_type",
        horizon_kind="historical",
        source_tag="NASA_POWER",
        tmin_by_date=tmin,
        tmax_by_date=tmax,
        years=[2021],
        phenology_evaluator=lambda d: "bad",  # type: ignore[arg-type, return-value]
        critical_water_evaluator=lambda s, e: 0.9,
    )
    with pytest.raises(TypeError):
        sweep_sowing_windows(["10-01"], [h_wrong_type], config)
