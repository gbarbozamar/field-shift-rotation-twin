"""Tests for ``engine/water/frost_heat.py``.

Covers G1 (pure function), G3 (contract types), G4 (missing / non-computable
propagation), G5 (caller ``TypeError`` checks), blueprint section 3.5 (zero
default or hardcoded thresholds), and mutant-killing boundary/check-order cases.

Every threshold, date, and temperature series in this file is synthetic
PLACEHOLDER test data, plainly not real: nothing comes from a data source or
publication, and no real agronomic threshold is stated or implied.
"""

from __future__ import annotations

import ast
import calendar
import copy
import datetime as dt
import inspect
import math
from dataclasses import FrozenInstanceError
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
from engine.water import frost_heat
from engine.water.et0.quantities import TEMPERATURE_MAX, TEMPERATURE_MIN
from engine.water.frost_heat import (
    MonthlyFrostHeatCount,
    count_monthly_frost_and_heat_days,
)

# PLACEHOLDER synthetic thresholds chosen solely for boundary/count tests.
PLACEHOLDER_FROST_THRESHOLD = 2.22  # PLACEHOLDER
PLACEHOLDER_HEAT_THRESHOLD = 8.88  # PLACEHOLDER


def _point() -> ClimatePoint:
    range_missing = InputsMissing(
        reason="NOT_AVAILABLE",
        detail="PLACEHOLDER: synthetic test point has no range",
    )
    return ClimatePoint(
        latitude=Value(
            value=1.11,  # PLACEHOLDER
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        longitude=Value(
            value=2.22,  # PLACEHOLDER
            unit="degree",
            provenance="OBSERVED",
            source="PLACEHOLDER",
            range_missing=range_missing,
        ),
        elevation=Value(
            value=3.33,  # PLACEHOLDER
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
    for offset, item in enumerate(values):
        day_date = start + dt.timedelta(days=offset)
        if isinstance(item, InputsMissing):
            days.append(DailyValue(date=day_date, value=None, missing=item))
        else:
            days.append(DailyValue(date=day_date, value=item, missing=None))
    has_present = any(not isinstance(item, InputsMissing) for item in values)
    return DailySeries(
        quantity=quantity,
        unit=unit,
        time_zone=time_zone,
        start_date=start,
        end_date=end,
        provenance="OBSERVED" if has_present else None,
        source="PLACEHOLDER synthetic series" if has_present else None,
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


def _climate(series: list[DailySeries]) -> SiteClimate:
    return SiteClimate(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=series,
        monthly_series=[],
    )


def _month_values(
    year: int,
    month: int,
    default_value: float,
    overrides: dict[int, float | InputsMissing] | None = None,
) -> list[float | InputsMissing]:
    _, days_in_month = calendar.monthrange(year, month)
    overrides = overrides or {}
    return [
        overrides.get(day_num, default_value) for day_num in range(1, days_in_month + 1)
    ]


# --- Blueprint §3.5: strict zero-default / zero-hardcoded-threshold checks ----


def test_signature_requires_keyword_only_thresholds_with_no_defaults():
    sig = inspect.signature(count_monthly_frost_and_heat_days)
    params = sig.parameters
    assert list(params) == [
        "climate",
        "frost_threshold_deg_c",
        "heat_threshold_deg_c",
    ]
    assert params["climate"].default is inspect.Parameter.empty
    for name in ("frost_threshold_deg_c", "heat_threshold_deg_c"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default is inspect.Parameter.empty


def test_calling_without_keyword_thresholds_raises_type_error():
    empty = _climate([])
    with pytest.raises(TypeError):
        count_monthly_frost_and_heat_days(empty)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        count_monthly_frost_and_heat_days(  # type: ignore[call-arg]
            empty,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        )
    with pytest.raises(TypeError):
        count_monthly_frost_and_heat_days(  # type: ignore[call-arg]
            empty,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
    with pytest.raises(TypeError):
        count_monthly_frost_and_heat_days(  # type: ignore[misc]
            empty,
            PLACEHOLDER_FROST_THRESHOLD,
            PLACEHOLDER_HEAT_THRESHOLD,
        )


def test_module_contains_no_numeric_thresholds_or_impure_imports():
    source_path = Path(frost_heat.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    # Only the unit count `1` in `sum(1 for ...)` is permitted.
    assert numeric_constants == {1}

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    forbidden_impure = {
        "os",
        "pathlib",
        "datetime",
        "time",
        "random",
        "urllib",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "json",
    }
    assert imported_modules.isdisjoint(forbidden_impure)


def test_dataclass_is_frozen():
    item = MonthlyFrostHeatCount(year=2001, month=1, frost_days=1, heat_days=2)
    with pytest.raises(FrozenInstanceError):
        item.frost_days = 3  # type: ignore[misc]


# --- G1: purity & non-mutation ----------------------------------------------


def test_pure_deterministic_and_does_not_mutate_climate():
    # PLACEHOLDER synthetic values.
    tmin = _daily_series(
        TEMPERATURE_MIN,
        dt.date(2001, 1, 1),
        _month_values(2001, 1, 4.44, {1: 1.11, 2: PLACEHOLDER_FROST_THRESHOLD}),
    )
    tmax = _daily_series(
        TEMPERATURE_MAX,
        dt.date(2001, 1, 1),
        _month_values(2001, 1, 5.55, {10: 9.99, 11: PLACEHOLDER_HEAT_THRESHOLD}),
    )
    climate = _climate([tmin, tmax])
    snapshot = copy.deepcopy(climate)

    first = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    second = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert first == second
    assert climate == snapshot


# --- Happy paths & boundary (inclusive <= / >=) mutant killers --------------


def test_counts_inclusive_boundaries_and_ignores_unrelated_series():
    # Kills `<` vs `<=` for frost and `>` vs `>=` for heat, and verifies 0 counts
    # return `int` (not `bool`) and extra series do not affect months or counts.
    frost_t = PLACEHOLDER_FROST_THRESHOLD  # 2.22 PLACEHOLDER
    heat_t = PLACEHOLDER_HEAT_THRESHOLD  # 8.88 PLACEHOLDER

    # Jan 2001: 1 strictly below, 1 equal, 1 just above frost_t -> 2 frost days
    #           1 strictly above, 1 equal, 1 just below heat_t -> 2 heat days
    # Feb 2001: 0 frost days, all 28 days heat days
    jan_min = _month_values(
        2001,
        1,
        frost_t + 1.0,
        {5: frost_t - 0.01, 6: frost_t, 7: frost_t + 0.01},
    )
    feb_min = _month_values(2001, 2, frost_t + 3.0)
    jan_max = _month_values(
        2001,
        1,
        heat_t - 1.0,
        {10: heat_t + 0.01, 11: heat_t, 12: heat_t - 0.01},
    )
    feb_max = _month_values(2001, 2, heat_t)

    climate = _climate(
        [
            _daily_series(
                "precipitation",
                dt.date(2001, 1, 1),
                [5.55] * 90,  # PLACEHOLDER spanning Jan-Mar; Mar must NOT appear
                unit="mm day-1",
            ),
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 1, 1), jan_min + feb_min),
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 1, 1), jan_max + feb_max),
        ]
    )

    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=frost_t,
        heat_threshold_deg_c=heat_t,
    )
    assert result == [
        MonthlyFrostHeatCount(year=2001, month=1, frost_days=2, heat_days=2),
        MonthlyFrostHeatCount(year=2001, month=2, frost_days=0, heat_days=28),
    ]
    assert type(result[1].frost_days) is int


def test_negative_and_integer_thresholds_and_chronological_year_wrap():
    # PLACEHOLDER synthetic negative/int thresholds across Dec 2001 -> Feb 2002.
    frost_t = -3  # PLACEHOLDER int threshold
    heat_t = 7  # PLACEHOLDER int threshold

    dec_min = _month_values(2001, 12, 1.11, {1: -3.0, 2: -4.44, 3: -2.99})
    jan_min = _month_values(2002, 1, 1.11, {15: -5.55})
    dec_max = _month_values(2001, 12, 4.44, {20: 7.0, 21: 6.99})
    jan_max = _month_values(2002, 1, 8.88)

    climate = _climate(
        [
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 12, 1), dec_max + jan_max),
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 12, 1), dec_min + jan_min),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=frost_t,
        heat_threshold_deg_c=heat_t,
    )
    assert result == [
        MonthlyFrostHeatCount(year=2001, month=12, frost_days=2, heat_days=1),
        MonthlyFrostHeatCount(year=2002, month=1, frost_days=1, heat_days=31),
    ]


@pytest.mark.parametrize(
    ("year", "expected_days"),
    [
        (2000, 29),  # Gregorian leap century
        (2001, 28),  # common year
        (2004, 29),  # leap year
        (1900, 28),  # non-leap century
    ],
)
def test_february_leap_year_coverage_and_counts(year: int, expected_days: int):
    # PLACEHOLDER synthetic values.
    feb_min = _month_values(year, 2, PLACEHOLDER_FROST_THRESHOLD)
    feb_max = _month_values(year, 2, PLACEHOLDER_HEAT_THRESHOLD)
    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(year, 2, 1), feb_min),
            _daily_series(TEMPERATURE_MAX, dt.date(year, 2, 1), feb_max),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert result == [
        MonthlyFrostHeatCount(
            year=year,
            month=2,
            frost_days=expected_days,
            heat_days=expected_days,
        )
    ]


def test_empty_or_non_temperature_climate_returns_empty_list():
    assert (
        count_monthly_frost_and_heat_days(
            _climate([]),
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
        == []
    )
    only_precip = _climate(
        [
            _daily_series(
                "precipitation",
                dt.date(2001, 1, 1),
                _month_values(2001, 1, 1.11),
                unit="mm day-1",
            )
        ]
    )
    assert (
        count_monthly_frost_and_heat_days(
            only_precip,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
        == []
    )


def test_independent_axes_allow_differing_series_time_zones():
    # PLACEHOLDER synthetic values.
    climate = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_FROST_THRESHOLD, {1: 9.99}),
                time_zone="UTC",
            ),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD, {2: 1.11}),
                time_zone="Etc/GMT+3",
            ),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert result == [
        MonthlyFrostHeatCount(year=2001, month=1, frost_days=30, heat_days=30)
    ]


# --- G4: Missing & non-computable propagation + independence -----------------


def test_missing_thresholds_propagate_independently():
    climate = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_FROST_THRESHOLD),
            ),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD),
            ),
        ]
    )
    missing_frost = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER frost missing")
    res_frost_missing = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=missing_frost,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert res_frost_missing == [
        MonthlyFrostHeatCount(
            year=2001,
            month=1,
            frost_days=missing_frost,
            heat_days=31,
        )
    ]

    missing_heat = Missing(reason="NOT_AVAILABLE")
    res_heat_missing = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=missing_heat,
    )
    assert res_heat_missing == [
        MonthlyFrostHeatCount(
            year=2001,
            month=1,
            frost_days=31,
            heat_days=missing_heat,
        )
    ]


@pytest.mark.parametrize(
    "bad_threshold",
    [math.nan, math.inf, -math.inf, 10**400],
)
def test_non_finite_threshold_returns_not_computable_independently(bad_threshold):
    climate = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_FROST_THRESHOLD),
            ),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD),
            ),
        ]
    )
    res_bad_frost = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=bad_threshold,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(res_bad_frost) == 1
    assert isinstance(res_bad_frost[0].frost_days, Missing)
    assert res_bad_frost[0].frost_days.reason == "NOT_COMPUTABLE"
    assert "frost_threshold_deg_c" in (res_bad_frost[0].frost_days.detail or "")
    assert res_bad_frost[0].heat_days == 31

    res_bad_heat = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=bad_threshold,
    )
    assert len(res_bad_heat) == 1
    assert res_bad_heat[0].frost_days == 31
    assert isinstance(res_bad_heat[0].heat_days, Missing)
    assert res_bad_heat[0].heat_days.reason == "NOT_COMPUTABLE"
    assert "heat_threshold_deg_c" in (res_bad_heat[0].heat_days.detail or "")


def test_missing_one_temperature_series_computes_the_other():
    only_min = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_FROST_THRESHOLD),
            )
        ]
    )
    res_min = count_monthly_frost_and_heat_days(
        only_min,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(res_min) == 1
    assert res_min[0].frost_days == 31
    assert isinstance(res_min[0].heat_days, Missing)
    assert res_min[0].heat_days.reason == "MISSING_INPUT"
    assert TEMPERATURE_MAX in (res_min[0].heat_days.detail or "")

    only_max = _climate(
        [
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD),
            )
        ]
    )
    res_max = count_monthly_frost_and_heat_days(
        only_max,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(res_max) == 1
    assert isinstance(res_max[0].frost_days, Missing)
    assert res_max[0].frost_days.reason == "MISSING_INPUT"
    assert TEMPERATURE_MIN in (res_max[0].frost_days.detail or "")
    assert res_max[0].heat_days == 31


@pytest.mark.parametrize("bad_unit", ["K", "degF", "C", "degc"])
def test_wrong_unit_returns_missing_input_even_on_partial_month(bad_unit: str):
    # Checks unit guard runs before month coverage (kills unit/coverage swap).
    climate = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 1, 1),
                [273.15, 274.15, 275.15],  # PLACEHOLDER partial month, wrong unit
                unit=bad_unit,
            ),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 1, 1),
                _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD),
                unit="degC",
            ),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(result) == 1
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "MISSING_INPUT"
    assert bad_unit in (result[0].frost_days.detail or "")
    assert "degC" in (result[0].frost_days.detail or "")
    assert result[0].heat_days == 31


def test_incomplete_calendar_month_returns_no_coverage_per_axis():
    # tmin covers Jan 2..Feb 28 (Jan incomplete); tmax covers Feb 1..Mar 15 (Mar incomplete).
    jan_partial = _month_values(2001, 1, PLACEHOLDER_FROST_THRESHOLD)[1:]  # 30 days
    feb_min = _month_values(2001, 2, PLACEHOLDER_FROST_THRESHOLD)
    feb_max = _month_values(2001, 2, PLACEHOLDER_HEAT_THRESHOLD)
    mar_partial = _month_values(2001, 3, PLACEHOLDER_HEAT_THRESHOLD)[:15]

    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 1, 2), jan_partial + feb_min),
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 2, 1), feb_max + mar_partial),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert [(item.year, item.month) for item in result] == [
        (2001, 1),
        (2001, 2),
        (2001, 3),
    ]
    # 2001-01: tmin partial -> NO_COVERAGE; tmax has no days -> NO_COVERAGE
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"
    assert isinstance(result[0].heat_days, Missing)
    assert result[0].heat_days.reason == "NO_COVERAGE"
    # 2001-02: both full -> computed
    assert result[1] == MonthlyFrostHeatCount(
        year=2001, month=2, frost_days=28, heat_days=28
    )
    # 2001-03: tmin has no days -> NO_COVERAGE; tmax partial -> NO_COVERAGE
    assert isinstance(result[2].frost_days, Missing)
    assert result[2].frost_days.reason == "NO_COVERAGE"
    assert isinstance(result[2].heat_days, Missing)
    assert result[2].heat_days.reason == "NO_COVERAGE"


def test_leap_february_missing_29th_returns_no_coverage():
    # 2004 is a leap year; 28 days is incomplete.
    feb_28_days = _month_values(2004, 2, PLACEHOLDER_FROST_THRESHOLD)[:28]
    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(2004, 2, 1), feb_28_days),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2004, 2, 1),
                _month_values(2004, 2, PLACEHOLDER_HEAT_THRESHOLD),
            ),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(result) == 1
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"
    assert result[0].heat_days == 29


def test_duplicate_date_in_constructed_series_returns_no_coverage():
    # Kills removing `len(month_days) != days_in_month` check when unique dates == 28.
    feb_days = [
        DailyValue(date=dt.date(2001, 2, day), value=PLACEHOLDER_FROST_THRESHOLD)
        for day in range(1, 29)
    ]
    feb_days.append(
        DailyValue(date=dt.date(2001, 2, 1), value=PLACEHOLDER_FROST_THRESHOLD)
    )
    bad_series = DailySeries.model_construct(
        quantity=TEMPERATURE_MIN,
        unit="degC",
        time_zone="UTC",
        start_date=dt.date(2001, 2, 1),
        end_date=dt.date(2001, 2, 28),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
        days=feb_days,
    )
    climate = SiteClimate.model_construct(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=[bad_series],
        monthly_series=[],
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"


def test_missing_day_value_returns_missing_input_without_poisoning_other_months():
    # Even when the daily fill_reason is NO_COVERAGE, aggregating over a gap
    # returns MISSING_INPUT (C3.3, C3.4, G4), naming the earliest missing date.
    jan_min = _month_values(
        2001,
        1,
        PLACEHOLDER_FROST_THRESHOLD,
        {
            20: InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER gap 2"),
            10: InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER gap 1"),
        },
    )
    feb_min = _month_values(2001, 2, PLACEHOLDER_FROST_THRESHOLD)
    jan_max = _month_values(2001, 1, PLACEHOLDER_HEAT_THRESHOLD)
    feb_max = _month_values(2001, 2, PLACEHOLDER_HEAT_THRESHOLD)

    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 1, 1), jan_min + feb_min),
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 1, 1), jan_max + feb_max),
        ]
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(result) == 2
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "MISSING_INPUT"
    assert "2001-01-10" in (result[0].frost_days.detail or "")
    assert "2 day(s)" in (result[0].frost_days.detail or "")
    assert result[0].heat_days == 31
    assert result[1] == MonthlyFrostHeatCount(
        year=2001, month=2, frost_days=28, heat_days=28
    )


@pytest.mark.parametrize("bad_temp", [math.nan, math.inf, -math.inf, 10**400])
def test_non_finite_daily_temperature_returns_not_computable(bad_temp):
    days = [
        DailyValue.model_construct(
            date=dt.date(2001, 2, day),
            value=(bad_temp if day == 14 else PLACEHOLDER_FROST_THRESHOLD),
            missing=None,
        )
        for day in range(1, 29)
    ]
    bad_series = DailySeries.model_construct(
        quantity=TEMPERATURE_MIN,
        unit="degC",
        time_zone="UTC",
        start_date=dt.date(2001, 2, 1),
        end_date=dt.date(2001, 2, 28),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
        days=days,
    )
    good_max = _daily_series(
        TEMPERATURE_MAX,
        dt.date(2001, 2, 1),
        _month_values(2001, 2, PLACEHOLDER_HEAT_THRESHOLD),
    )
    climate = SiteClimate.model_construct(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=[bad_series, good_max],
        monthly_series=[],
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(result) == 1
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NOT_COMPUTABLE"
    assert "2001-02-14" in (result[0].frost_days.detail or "")
    assert result[0].heat_days == 28


def test_missing_day_takes_precedence_over_non_finite_day_in_same_month():
    days = [
        DailyValue.model_construct(
            date=dt.date(2001, 2, day),
            value=(
                None
                if day == 5
                else (math.nan if day == 10 else PLACEHOLDER_FROST_THRESHOLD)
            ),
            missing=(InputsMissing(reason="SOURCE_UNAVAILABLE") if day == 5 else None),
        )
        for day in range(1, 29)
    ]
    series = DailySeries.model_construct(
        quantity=TEMPERATURE_MIN,
        unit="degC",
        time_zone="UTC",
        start_date=dt.date(2001, 2, 1),
        end_date=dt.date(2001, 2, 28),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
        days=days,
    )
    climate = SiteClimate.model_construct(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=[series],
        monthly_series=[],
    )
    result = count_monthly_frost_and_heat_days(
        climate,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "MISSING_INPUT"


# --- G5: caller type checks --------------------------------------------------


@pytest.mark.parametrize("bad_climate", [None, {}, "climate", 123, []])
def test_wrong_climate_type_raises_type_error(bad_climate):
    with pytest.raises(TypeError, match="SiteClimate"):
        count_monthly_frost_and_heat_days(
            bad_climate,  # type: ignore[arg-type]
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )


@pytest.mark.parametrize(
    "bad_threshold",
    [
        True,
        False,
        "2.22",
        None,
        [],
        {},
        complex(1.0, 2.0),
        InputsMissing(reason="NOT_DECLARED"),
    ],
)
def test_wrong_threshold_type_raises_type_error_even_on_empty_climate(bad_threshold):
    empty = _climate([])
    with pytest.raises(TypeError, match="frost_threshold_deg_c"):
        count_monthly_frost_and_heat_days(
            empty,
            frost_threshold_deg_c=bad_threshold,  # type: ignore[arg-type]
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
    with pytest.raises(TypeError, match="heat_threshold_deg_c"):
        count_monthly_frost_and_heat_days(
            empty,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=bad_threshold,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("bad_day_value", [True, False, None, "1.11"])
def test_non_numeric_daily_value_raises_type_error(bad_day_value):
    days = [
        DailyValue.model_construct(
            date=dt.date(2001, 2, day),
            value=(bad_day_value if day == 3 else PLACEHOLDER_FROST_THRESHOLD),
            missing=None,
        )
        for day in range(1, 29)
    ]
    series = DailySeries.model_construct(
        quantity=TEMPERATURE_MIN,
        unit="degC",
        time_zone="UTC",
        start_date=dt.date(2001, 2, 1),
        end_date=dt.date(2001, 2, 28),
        provenance="OBSERVED",
        source="PLACEHOLDER",
        range_missing=InputsMissing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
        days=days,
    )
    climate = SiteClimate.model_construct(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=[series],
        monthly_series=[],
    )
    with pytest.raises(TypeError, match="number"):
        count_monthly_frost_and_heat_days(
            climate,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
