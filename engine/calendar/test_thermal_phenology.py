"""Tests for ``engine/calendar/thermal_phenology.py`` (Frontier Unit F-10).

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Every temperature, latitude, date, and cultivar parameter in this file is
synthetic PLACEHOLDER test data, plainly not real: nothing comes from a data
source or publication, and no real agronomic cultivar parameter is stated or
implied.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import math
from dataclasses import MISSING as DC_MISSING
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
)
from contracts.results.models import Missing
from engine.calendar import thermal_phenology
from engine.calendar.thermal_phenology import (
    CALIBRATED_STATUS,
    UNCALIBRATED_STATUS,
    CalibrationMetadata,
    CultivarPhenologyParams,
    DailyThermalInput,
    DvsPoint,
    PhenologySimulationResult,
    PhotoperiodParams,
    VernalizationParams,
    astronomical_daylength_hours,
    daily_thermal_inputs_from_site_climate,
    daily_thermal_time,
    day_of_year,
    photoperiod_factor,
    simulate_crop_phenology,
    vernalization_effectiveness,
    vernalization_factor,
)

# PLACEHOLDER synthetic cultivar parameters for deterministic unit tests only.
PLACEHOLDER_LATITUDE_SOUTH = -34.0  # PLACEHOLDER
PLACEHOLDER_LATITUDE_NORTH = 45.0  # PLACEHOLDER


def _neutral_params(
    *,
    t_base: float = 5.0,
    t_opt: float = 25.0,
    t_max_ceiling: float = 35.0,
    tsum_emergence: float = 50.0,
    tsum1: float = 500.0,
    tsum2: float = 400.0,
    floral_initiation_dvs: float = 0.4,
    photoperiod: PhotoperiodParams | None = None,
    vernalization: VernalizationParams | None = None,
) -> CultivarPhenologyParams:
    return CultivarPhenologyParams(
        t_base=t_base,
        t_opt=t_opt,
        t_max_ceiling=t_max_ceiling,
        tsum_emergence=tsum_emergence,
        tsum1=tsum1,
        tsum2=tsum2,
        floral_initiation_dvs=floral_initiation_dvs,
        photoperiod=photoperiod,
        vernalization=vernalization,
    )


def _constant_weather(
    start: dt.date,
    num_days: int,
    tmin_c: float,
    tmax_c: float,
) -> list[DailyThermalInput]:
    return [
        DailyThermalInput(
            date=start + dt.timedelta(days=offset),
            tmin_c=tmin_c,
            tmax_c=tmax_c,
        )
        for offset in range(num_days)
    ]


def _placeholder_point() -> ClimatePoint:
    range_missing = InputsMissing(
        reason="NOT_AVAILABLE",
        detail="PLACEHOLDER: synthetic point has no range",
    )
    return ClimatePoint(
        latitude=Value(
            value=-34.0,
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        longitude=Value(
            value=-56.0,
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        elevation=Value(
            value=50.0,
            unit="m",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
    )


def _daily_series(
    quantity: str,
    start: dt.date,
    values: list[float | InputsMissing],
    *,
    unit: str = "degC",
    time_zone: str = "UTC",
) -> DailySeries:
    end = start + dt.timedelta(days=len(values) - 1)
    days = []
    for offset, val in enumerate(values):
        d = start + dt.timedelta(days=offset)
        if isinstance(val, InputsMissing):
            days.append(DailyValue(date=d, value=None, missing=val))
        else:
            days.append(DailyValue(date=d, value=val, missing=None))
    has_present = any(not isinstance(v, InputsMissing) for v in values)
    return DailySeries(
        quantity=quantity,
        unit=unit,
        time_zone=time_zone,
        start_date=start,
        end_date=end,
        provenance="OBSERVED" if has_present else None,
        source="PLACEHOLDER synthetic climate" if has_present else None,
        range_missing=(
            InputsMissing(
                reason="NOT_AVAILABLE",
                detail="PLACEHOLDER synthetic series has no range",
            )
            if has_present
            else None
        ),
        days=days,
    )


# --- Zero hardcoded cultivar defaults & frozen dataclasses ------------------


def test_cultivar_parameter_dataclasses_have_zero_defaults():
    for cls in (CultivarPhenologyParams, PhotoperiodParams, VernalizationParams):
        for f in fields(cls):
            assert f.default is DC_MISSING, f"{cls.__name__}.{f.name} has a default"
            assert f.default_factory is DC_MISSING, (
                f"{cls.__name__}.{f.name} has a default_factory"
            )


def test_dataclasses_are_frozen():
    params = _neutral_params()
    with pytest.raises(FrozenInstanceError):
        params.t_base = 0.0  # type: ignore[misc]
    weather = _constant_weather(dt.date(2027, 5, 1), 120, 10.0, 20.0)
    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=dt.date(2027, 5, 1),
        params=params,
    )
    with pytest.raises(FrozenInstanceError):
        res.calibration_status = "CALIBRATED"  # type: ignore[misc]


# --- Clean-room astronomical daylength geometry -----------------------------


def test_daylength_equator_is_twelve_hours_year_round():
    for doy in (1, 80, 172, 264, 355):
        assert math.isclose(astronomical_daylength_hours(0.0, doy), 12.0, abs_tol=1e-12)


def test_daylength_hemisphere_seasonality_and_symmetry():
    # June solstice (doy 172) vs December solstice (doy 355)
    north_jun = astronomical_daylength_hours(PLACEHOLDER_LATITUDE_NORTH, 172)
    north_dec = astronomical_daylength_hours(PLACEHOLDER_LATITUDE_NORTH, 355)
    south_jun = astronomical_daylength_hours(PLACEHOLDER_LATITUDE_SOUTH, 172)
    south_dec = astronomical_daylength_hours(PLACEHOLDER_LATITUDE_SOUTH, 355)

    assert north_jun > 12.0 > north_dec
    assert south_jun < 12.0 < south_dec
    # Symmetric opposite latitudes sum to 24 hours on the same day of year
    assert math.isclose(
        astronomical_daylength_hours(40.0, 172)
        + astronomical_daylength_hours(-40.0, 172),
        24.0,
        abs_tol=1e-12,
    )


def test_daylength_polar_day_and_polar_night():
    assert astronomical_daylength_hours(89.0, 172) == 24.0
    assert astronomical_daylength_hours(89.0, 355) == 0.0
    assert astronomical_daylength_hours(90.0, 172) == 24.0
    assert astronomical_daylength_hours(-90.0, 172) == 0.0


def test_daylength_matches_math_reference_across_latitudes_and_days():
    for lat in (-89.5, -66.5, -45.0, -34.0, -10.0, 0.0, 10.0, 34.0, 45.0, 66.5, 89.5):
        for doy in range(1, 367, 15):
            decl = 0.409 * math.sin(math.tau * doy / 365.0 - 1.39)
            cos_ws = -math.tan(math.radians(lat)) * math.tan(decl)
            if cos_ws <= -1.0:
                expected = 24.0
            elif cos_ws >= 1.0:
                expected = 0.0
            else:
                expected = (24.0 / math.pi) * math.acos(cos_ws)
            actual = astronomical_daylength_hours(lat, doy)
            assert math.isclose(actual, expected, abs_tol=1e-12)


def test_daylength_rejects_invalid_inputs():
    with pytest.raises(TypeError):
        astronomical_daylength_hours(True, 100)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        astronomical_daylength_hours(10.0, True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        astronomical_daylength_hours(91.0, 100)
    with pytest.raises(ValueError):
        astronomical_daylength_hours(-90.1, 100)
    with pytest.raises(ValueError):
        astronomical_daylength_hours(math.nan, 100)
    with pytest.raises(ValueError):
        astronomical_daylength_hours(10.0, 0)
    with pytest.raises(ValueError):
        astronomical_daylength_hours(10.0, 367)


def test_day_of_year_leap_and_non_leap():
    assert day_of_year(dt.date(2024, 12, 31)) == 366
    assert day_of_year(dt.date(2025, 12, 31)) == 365
    with pytest.raises(TypeError):
        day_of_year(dt.datetime(2025, 1, 1))  # type: ignore[arg-type]


# --- Thermal time, photoperiod, and vernalization submodels -----------------


def test_daily_thermal_time_cardinal_shape():
    params = _neutral_params(t_base=5.0, t_opt=25.0, t_max_ceiling=35.0)
    assert daily_thermal_time(0.0, 6.0, params) == 0.0  # tmean=3 <= 5
    assert daily_thermal_time(5.0, 5.0, params) == 0.0  # tmean=5
    assert math.isclose(daily_thermal_time(10.0, 20.0, params), 10.0)  # tmean=15
    assert math.isclose(daily_thermal_time(20.0, 30.0, params), 20.0)  # tmean=25 (opt)
    assert math.isclose(
        daily_thermal_time(25.0, 35.0, params), 10.0
    )  # tmean=30 (declining)
    assert daily_thermal_time(30.0, 40.0, params) == 0.0  # tmean=35 (ceiling)
    assert daily_thermal_time(35.0, 45.0, params) == 0.0  # tmean=40 > ceiling


def test_photoperiod_factor_all_modes():
    assert photoperiod_factor(12.0, None) == 1.0
    neutral = PhotoperiodParams(mode="neutral", dl_crit=10.0, dl_sat=16.0)
    assert photoperiod_factor(8.0, neutral) == 1.0
    assert photoperiod_factor(18.0, neutral) == 1.0

    long_day = PhotoperiodParams(mode="long_day", dl_crit=10.0, dl_sat=14.0)
    assert photoperiod_factor(9.0, long_day) == 0.0
    assert photoperiod_factor(10.0, long_day) == 0.0
    assert math.isclose(photoperiod_factor(12.0, long_day), 0.5)
    assert photoperiod_factor(14.0, long_day) == 1.0
    assert photoperiod_factor(16.0, long_day) == 1.0

    short_day = PhotoperiodParams(mode="short_day", dl_crit=15.0, dl_sat=11.0)
    assert photoperiod_factor(10.0, short_day) == 1.0
    assert photoperiod_factor(11.0, short_day) == 1.0
    assert math.isclose(photoperiod_factor(13.0, short_day), 0.5)
    assert photoperiod_factor(15.0, short_day) == 0.0
    assert photoperiod_factor(17.0, short_day) == 0.0


def test_vernalization_effectiveness_and_factor():
    vern = VernalizationParams(
        v_base=0.0,
        v_opt_low=4.0,
        v_opt_high=8.0,
        v_max=14.0,
        vsat_days=10.0,
        v_min_factor=0.2,
    )
    assert vernalization_effectiveness(-1.0, vern) == 0.0
    assert math.isclose(vernalization_effectiveness(2.0, vern), 0.5)
    assert vernalization_effectiveness(6.0, vern) == 1.0
    assert math.isclose(vernalization_effectiveness(11.0, vern), 0.5)
    assert vernalization_effectiveness(14.0, vern) == 0.0

    assert math.isclose(vernalization_factor(0.0, vern), 0.2)
    assert math.isclose(vernalization_factor(5.0, vern), 0.6)
    assert math.isclose(vernalization_factor(10.0, vern), 1.0)
    assert math.isclose(vernalization_factor(25.0, vern), 1.0)
    assert vernalization_factor(0.0, None) == 1.0


# --- Exact analytical phenology trajectory ----------------------------------


def test_exact_thermal_simulation_chronology_and_dvs_series():
    # tmean = 15.0, t_base = 5.0 -> 10.0 degC-days/day
    # tsum_emergence=50 -> 5 days (sowing day 0 .. day 4 -> emergence on day 4)
    # tsum1=500 -> 50 days after emergence (day 5 .. day 54 -> flowering on day 54)
    # floral_initiation_dvs=0.4 -> 20 days after emergence (day 24)
    # tsum2=400 -> 40 days after flowering (day 55 .. day 94 -> maturity on day 94)
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    params = _neutral_params()

    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
    )

    assert isinstance(res, PhenologySimulationResult)
    assert res.provenance == "SIMULATED"
    assert res.emergence_date == sowing + dt.timedelta(days=4)
    assert res.floral_initiation_date == sowing + dt.timedelta(days=24)
    assert res.flowering_date == sowing + dt.timedelta(days=54)
    assert res.maturity_date == sowing + dt.timedelta(days=94)
    assert (
        res.emergence_date
        < res.floral_initiation_date
        < res.flowering_date
        < res.maturity_date
    )
    assert len(res.dvs_series) == 95
    assert isinstance(res.dvs_series[0], DvsPoint)
    assert res.dvs_series[0].date == sowing
    assert res.dvs_series[4].dvs == 0.0
    assert res.dvs_series[54].dvs == 1.0
    assert res.dvs_series[-1].date == res.maturity_date
    assert res.dvs_series[-1].dvs == 2.0


def test_long_day_and_short_day_photoperiod_shift_flowering():
    sowing = dt.date(
        2027, 6, 1
    )  # Northern summer (~15.4h at 45N) vs Southern winter (~10h at -34S)
    weather = _constant_weather(sowing, 210, tmin_c=10.0, tmax_c=20.0)

    ld_params = _neutral_params(
        photoperiod=PhotoperiodParams(mode="long_day", dl_crit=11.0, dl_sat=14.0)
    )
    res_north = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_NORTH,
        sowing_date=sowing,
        params=ld_params,
    )
    res_south = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=ld_params,
    )
    # Under long days in Northern June, flowering occurs earlier than Southern winter
    assert isinstance(res_north.flowering_date, dt.date)
    assert isinstance(res_south.flowering_date, dt.date)
    assert res_north.flowering_date < res_south.flowering_date

    # Short-day cultivar under Northern summer (>15h > dl_crit=14h) stays vegetative
    sd_params = _neutral_params(
        photoperiod=PhotoperiodParams(mode="short_day", dl_crit=14.0, dl_sat=11.0)
    )
    res_sd_north = simulate_crop_phenology(
        weather[:60],
        latitude_deg=PLACEHOLDER_LATITUDE_NORTH,
        sowing_date=sowing,
        params=sd_params,
    )
    assert isinstance(res_sd_north.emergence_date, dt.date)
    assert isinstance(res_sd_north.flowering_date, Missing)
    assert res_sd_north.flowering_date.reason == "NO_COVERAGE"


def test_vernalization_delays_flowering_when_chilling_is_insufficient():
    sowing = dt.date(2027, 5, 1)
    weather_warm = _constant_weather(
        sowing, 120, tmin_c=15.0, tmax_c=25.0
    )  # tmean=20 > v_max=12
    vern = VernalizationParams(
        v_base=0.0,
        v_opt_low=2.0,
        v_opt_high=6.0,
        v_max=12.0,
        vsat_days=15.0,
        v_min_factor=0.0,
    )
    obligate_params = _neutral_params(vernalization=vern)
    res_warm = simulate_crop_phenology(
        weather_warm,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=obligate_params,
    )
    # Without chilling, obligate winter cultivar cannot flower (DVS remains 0.0)
    assert isinstance(res_warm.emergence_date, dt.date)
    assert isinstance(res_warm.flowering_date, Missing)
    assert res_warm.dvs_series[-1].dvs == 0.0

    # Provide 20 cool days (tmean=5 in [v_opt_low, v_opt_high]) followed by warm days
    cool_days = _constant_weather(
        sowing, 25, tmin_c=2.0, tmax_c=8.0
    )  # 0 tt/day if t_base=5? t_base=2
    warm_days = _constant_weather(
        sowing + dt.timedelta(days=25), 140, tmin_c=12.0, tmax_c=22.0
    )
    chilled_params = _neutral_params(
        t_base=2.0, tsum_emergence=30.0, vernalization=vern
    )
    res_chilled = simulate_crop_phenology(
        cool_days + warm_days,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=chilled_params,
    )
    assert isinstance(res_chilled.flowering_date, dt.date)
    assert isinstance(res_chilled.maturity_date, dt.date)


# --- §15.3 / §15.7 Guards: Calibration & Missing Temperature Propagation -----


def test_guard_uncalibrated_when_observed_dates_or_metadata_absent():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    params = _neutral_params()

    # Case 1: both absent
    res1 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
    )
    assert res1.calibration_status == UNCALIBRATED_STATUS
    assert res1.local_error_days is None
    assert isinstance(res1.local_error_missing, Missing)
    assert res1.local_error_missing.reason == "MISSING_INPUT"

    # Case 2: observed dates given, metadata absent
    res2 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
        observed_flowering_dates=[dt.date(2027, 6, 20)],
        calibration_metadata=None,
    )
    assert res2.calibration_status == UNCALIBRATED_STATUS
    assert res2.local_error_days is None
    assert isinstance(res2.local_error_missing, Missing)
    assert res2.local_error_missing.reason == "MISSING_INPUT"

    # Case 3: metadata explicitly uncalibrated
    res3 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
        observed_flowering_dates=[dt.date(2027, 6, 20)],
        calibration_metadata=CalibrationMetadata(
            calibrated=False, source="PLACEHOLDER", local_error_days=None
        ),
    )
    assert res3.calibration_status == UNCALIBRATED_STATUS
    assert res3.local_error_days is None
    assert isinstance(res3.local_error_missing, Missing)
    assert res3.local_error_missing.reason == "MISSING_INPUT"

    # Case 4: metadata says calibrated=True, but observed_flowering_dates is empty
    res4 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
        observed_flowering_dates=[],
        calibration_metadata=CalibrationMetadata(
            calibrated=True, source="PLACEHOLDER", local_error_days=2.0
        ),
    )
    assert res4.calibration_status == UNCALIBRATED_STATUS
    assert res4.local_error_days is None
    assert isinstance(res4.local_error_missing, Missing)
    assert res4.local_error_missing.reason == "MISSING_INPUT"


def test_calibrated_status_when_both_observed_and_metadata_calibrated():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    params = _neutral_params()
    observed = dt.date(2027, 6, 21)  # predicted flowering is 2027-06-24 (3 days diff)

    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
        observed_flowering_dates=[observed],
        calibration_metadata=CalibrationMetadata(
            calibrated=True,
            source="PLACEHOLDER local field trial",
            local_error_days=None,
        ),
    )
    assert res.calibration_status == CALIBRATED_STATUS
    assert res.local_error_days == 3.0
    assert res.local_error_missing is None


@pytest.mark.parametrize(
    "bad_tmin,bad_tmax",
    [
        (None, 20.0),
        (10.0, None),
        (Missing(reason="SOURCE_UNAVAILABLE", detail="sensor offline"), 20.0),
        (10.0, Missing(reason="MISSING_INPUT", detail="tmax missing")),
        (math.nan, 20.0),
        (10.0, math.inf),
        (-math.inf, 20.0),
    ],
)
def test_guard_missing_or_non_finite_temp_during_active_growth_propagates_missing(
    bad_tmin: float | Missing | None,
    bad_tmax: float | Missing | None,
):
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    # Inject bad temperature on day 30 (after emergence & floral initiation, before flowering)
    bad_day = sowing + dt.timedelta(days=30)
    weather[30] = DailyThermalInput(date=bad_day, tmin_c=bad_tmin, tmax_c=bad_tmax)

    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=_neutral_params(),
    )

    # Events reached before day 30 remain valid dates
    assert res.emergence_date == sowing + dt.timedelta(days=4)
    assert res.floral_initiation_date == sowing + dt.timedelta(days=24)

    # Unreached events MUST be Missing(reason="MISSING_INPUT")
    assert isinstance(res.flowering_date, Missing)
    assert res.flowering_date.reason == "MISSING_INPUT"
    assert bad_day.isoformat() in (res.flowering_date.detail or "")

    assert isinstance(res.maturity_date, Missing)
    assert res.maturity_date.reason == "MISSING_INPUT"

    # DVS points from day 30 onward MUST have dvs=None and Missing(reason="MISSING_INPUT")
    assert all(pt.dvs is not None and pt.missing is None for pt in res.dvs_series[:30])
    for pt in res.dvs_series[30:]:
        assert pt.dvs is None
        assert isinstance(pt.daily_thermal_time, Missing)
        assert pt.daily_thermal_time.reason == "MISSING_INPUT"
        assert isinstance(pt.missing, Missing)
        assert pt.missing.reason == "MISSING_INPUT"


def test_missing_temp_before_sowing_or_after_maturity_does_not_taint_result():
    pre_sowing = dt.date(2027, 4, 25)
    sowing = dt.date(2027, 5, 1)
    pre_weather = _constant_weather(pre_sowing, 6, tmin_c=10.0, tmax_c=20.0)
    pre_weather[2] = DailyThermalInput(
        date=pre_sowing + dt.timedelta(days=2),
        tmin_c=math.nan,
        tmax_c=20.0,
    )
    active_and_post = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    # Maturity is reached at day 94; day 110 is after active growth
    active_and_post[110] = DailyThermalInput(
        date=sowing + dt.timedelta(days=110),
        tmin_c=None,
        tmax_c=None,
    )

    res = simulate_crop_phenology(
        pre_weather + active_and_post,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=_neutral_params(),
    )
    assert res.maturity_date == sowing + dt.timedelta(days=94)
    assert all(pt.dvs is not None and pt.missing is None for pt in res.dvs_series)


def test_date_gap_during_active_growth_propagates_missing_input():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 80, tmin_c=10.0, tmax_c=20.0)
    missing_date = weather[10].date
    del weather[10]

    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=_neutral_params(),
    )
    assert isinstance(res.flowering_date, Missing)
    assert res.flowering_date.reason == "MISSING_INPUT"
    assert missing_date.isoformat() in (res.flowering_date.detail or "")


def test_uncovered_sowing_date_returns_no_coverage():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(dt.date(2027, 5, 10), 30, tmin_c=10.0, tmax_c=20.0)
    res = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=_neutral_params(),
    )
    for field_val in (
        res.emergence_date,
        res.floral_initiation_date,
        res.flowering_date,
        res.maturity_date,
    ):
        assert isinstance(field_val, Missing)
        assert field_val.reason == "NO_COVERAGE"
    assert res.dvs_series == ()


def test_missing_latitude_propagates_missing_input():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 30, tmin_c=10.0, tmax_c=20.0)
    res = simulate_crop_phenology(
        weather,
        latitude_deg=Missing(reason="NOT_DECLARED", detail="site latitude missing"),
        sowing_date=sowing,
        params=_neutral_params(),
    )
    assert isinstance(res.emergence_date, Missing)
    assert res.emergence_date.reason == "MISSING_INPUT"
    assert isinstance(res.maturity_date, Missing)
    assert res.maturity_date.reason == "MISSING_INPUT"


# --- SiteClimate integration & G1 / G5 checks -------------------------------


def test_extract_from_site_climate_and_simulate():
    start = dt.date(2027, 5, 1)
    climate = SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_placeholder_point(),
        daily_series=[
            _daily_series("air_temperature_min_2m", start, [10.0] * 120),
            _daily_series("air_temperature_max_2m", start, [20.0] * 120),
        ],
        monthly_series=[],
    )
    records = daily_thermal_inputs_from_site_climate(climate)
    res = simulate_crop_phenology(
        records,
        latitude_deg=climate.point.latitude.value,  # type: ignore[arg-type]
        sowing_date=start,
        params=_neutral_params(),
    )
    assert res.maturity_date == start + dt.timedelta(days=94)


def test_purity_non_mutation_and_determinism():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 120, tmin_c=10.0, tmax_c=20.0)
    snapshot = copy.deepcopy(weather)
    params = _neutral_params()

    res1 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
    )
    res2 = simulate_crop_phenology(
        weather,
        latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
        sowing_date=sowing,
        params=params,
    )
    assert weather == snapshot
    assert res1 == res2


def test_g5_caller_defects_raise_type_or_value_error():
    sowing = dt.date(2027, 5, 1)
    weather = _constant_weather(sowing, 10, tmin_c=10.0, tmax_c=20.0)
    params = _neutral_params()

    with pytest.raises(TypeError):
        simulate_crop_phenology(
            "not-a-sequence",  # type: ignore[arg-type]
            latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
            sowing_date=sowing,
            params=params,
        )
    with pytest.raises(TypeError):
        simulate_crop_phenology(
            weather,
            latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
            sowing_date="2027-05-01",  # type: ignore[arg-type]
            params=params,
        )
    with pytest.raises(TypeError):
        simulate_crop_phenology(
            weather,
            latitude_deg=PLACEHOLDER_LATITUDE_SOUTH,
            sowing_date=sowing,
            params={"t_base": 5.0},  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        _neutral_params(t_base=20.0, t_opt=15.0, t_max_ceiling=30.0)
    with pytest.raises(ValueError):
        PhotoperiodParams(mode="long_day", dl_crit=14.0, dl_sat=11.0)
    with pytest.raises(ValueError):
        PhotoperiodParams(mode="short_day", dl_crit=11.0, dl_sat=14.0)


def test_ast_hygiene_pure_stdlib_and_contracts_only():
    path = Path(thermal_phenology.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed_prefixes = ("__future__", "collections.abc", "dataclasses", "contracts.")
    forbidden_calls = {"open", "print", "eval", "exec", "input"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.startswith(allowed_prefixes), (
                    f"disallowed import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "unexpected relative import"
            assert node.module is not None and node.module.startswith(
                allowed_prefixes
            ), f"disallowed import from: {node.module}"
        elif isinstance(node, ast.Name):
            assert node.id not in forbidden_calls, f"forbidden builtin: {node.id}"
