"""Tests for ``engine/water/thermal_counts.py``.

Covers Need N3 agricultural-year aggregation, D73/C5.3 agricultural-year
mapping (cross-checked against ``api.carbon_forcing.whole_ag_years``),
C5.5 full 12-month coverage, G1 purity/non-mutation, G4 independent
``Missing`` propagation, G5 caller ``TypeError``/``ValueError`` checks,
blueprint section 3.5 AST hygiene (zero hardcoded thresholds or method
constants), and mutant-killing boundary cases.

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

from api.carbon_forcing import whole_ag_years
from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import (
    ClimatePoint,
    DailySeries,
    DailyValue,
    SiteClimate,
    YearMonth,
)
from contracts.results.models import Missing
from engine.water import thermal_counts
from engine.water.et0.quantities import TEMPERATURE_MAX, TEMPERATURE_MIN
from engine.water.frost_heat import MonthlyFrostHeatCount
from engine.water.thermal_counts import (
    AgYearThermalCount,
    ag_year_thermal_counts,
    summarize_climate_thermal_counts,
)

# PLACEHOLDER synthetic thresholds chosen solely for boundary/count tests.
PLACEHOLDER_FROST_THRESHOLD = 2.22  # PLACEHOLDER
PLACEHOLDER_HEAT_THRESHOLD = 8.88  # PLACEHOLDER
PLACEHOLDER_AG_START_JULY = YearMonth(year=2001, month=7)  # PLACEHOLDER


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
        time_zone="UTC",
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


def _ag_year_month_list(ag_year: int, start_month: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    for offset in range(12):
        month_index = start_month - 1 + offset
        months.append((ag_year + month_index // 12, month_index % 12 + 1))
    return months


def _build_ag_year_monthly_counts(
    ag_year: int,
    start_month: int,
    *,
    frost_by_index: list[int | Missing] | None = None,
    heat_by_index: list[int | Missing] | None = None,
) -> list[MonthlyFrostHeatCount]:
    frost_values = frost_by_index or [1] * 12
    heat_values = heat_by_index or [2] * 12
    return [
        MonthlyFrostHeatCount(
            year=year,
            month=month,
            frost_days=frost_values[idx],
            heat_days=heat_values[idx],
        )
        for idx, (year, month) in enumerate(_ag_year_month_list(ag_year, start_month))
    ]


# --- Blueprint §3.5: signature, AST hygiene, and frozen dataclass -----------


def test_signatures_require_keyword_only_arguments_with_no_defaults():
    sig_agg = inspect.signature(ag_year_thermal_counts)
    assert list(sig_agg.parameters) == ["monthly_counts", "ag_year_start"]
    assert sig_agg.parameters["monthly_counts"].default is inspect.Parameter.empty
    assert sig_agg.parameters["ag_year_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig_agg.parameters["ag_year_start"].default is inspect.Parameter.empty

    sig_sum = inspect.signature(summarize_climate_thermal_counts)
    assert list(sig_sum.parameters) == [
        "climate",
        "ag_year_start",
        "frost_threshold_deg_c",
        "heat_threshold_deg_c",
    ]
    assert sig_sum.parameters["climate"].default is inspect.Parameter.empty
    for name in ("ag_year_start", "frost_threshold_deg_c", "heat_threshold_deg_c"):
        assert sig_sum.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig_sum.parameters[name].default is inspect.Parameter.empty


def test_calling_without_keyword_only_args_raises_type_error():
    empty = _climate([])
    with pytest.raises(TypeError):
        ag_year_thermal_counts([])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ag_year_thermal_counts([], PLACEHOLDER_AG_START_JULY)  # type: ignore[misc]

    with pytest.raises(TypeError):
        summarize_climate_thermal_counts(empty)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        summarize_climate_thermal_counts(  # type: ignore[call-arg]
            empty,
            ag_year_start=PLACEHOLDER_AG_START_JULY,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        )
    with pytest.raises(TypeError):
        summarize_climate_thermal_counts(  # type: ignore[call-arg]
            empty,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
    with pytest.raises(TypeError):
        summarize_climate_thermal_counts(  # type: ignore[misc]
            empty,
            PLACEHOLDER_AG_START_JULY,
            PLACEHOLDER_FROST_THRESHOLD,
            PLACEHOLDER_HEAT_THRESHOLD,
        )


def test_module_contains_zero_hardcoded_numeric_constants_or_impure_imports():
    source_path = Path(thermal_counts.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numeric_constants <= {0, 1}

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


def test_ag_year_thermal_count_dataclass_is_frozen():
    item = AgYearThermalCount(ag_year=2001, frost_days=3, heat_days=5)
    with pytest.raises(FrozenInstanceError):
        item.frost_days = 4  # type: ignore[misc]


# --- G1: purity & non-mutation ----------------------------------------------


def test_pure_deterministic_and_does_not_mutate_inputs():
    monthly_list = _build_ag_year_monthly_counts(2001, 7)
    reversed_input = list(reversed(monthly_list))
    snapshot_list = copy.deepcopy(reversed_input)
    start_snapshot = PLACEHOLDER_AG_START_JULY.model_copy(deep=True)

    first = ag_year_thermal_counts(
        reversed_input, ag_year_start=PLACEHOLDER_AG_START_JULY
    )
    second = ag_year_thermal_counts(
        reversed_input, ag_year_start=PLACEHOLDER_AG_START_JULY
    )
    assert isinstance(first, tuple)
    assert first == second
    assert reversed_input == snapshot_list
    assert PLACEHOLDER_AG_START_JULY == start_snapshot

    climate = _climate(
        [
            _daily_series(
                TEMPERATURE_MIN,
                dt.date(2001, 7, 1),
                [PLACEHOLDER_FROST_THRESHOLD - 1.0] * 365,
            ),
            _daily_series(
                TEMPERATURE_MAX,
                dt.date(2001, 7, 1),
                [PLACEHOLDER_HEAT_THRESHOLD + 1.0] * 365,
            ),
        ]
    )
    climate_snapshot = copy.deepcopy(climate)
    sum_first = summarize_climate_thermal_counts(
        climate,
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    sum_second = summarize_climate_thermal_counts(
        climate,
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert sum_first == sum_second
    assert climate == climate_snapshot


# --- Agricultural-year mapping & happy paths --------------------------------


def test_empty_monthly_counts_returns_empty_tuple():
    assert ag_year_thermal_counts([], ag_year_start=PLACEHOLDER_AG_START_JULY) == ()
    assert ag_year_thermal_counts((), ag_year_start=YearMonth(year=2001, month=1)) == ()


def test_january_start_groups_calendar_year_and_preserves_zero_int():
    monthly = _build_ag_year_monthly_counts(
        2001,
        1,
        frost_by_index=[0] * 12,
        heat_by_index=list(range(1, 13)),
    )
    result = ag_year_thermal_counts(
        monthly, ag_year_start=YearMonth(year=2001, month=1)
    )
    assert result == (AgYearThermalCount(ag_year=2001, frost_days=0, heat_days=78),)
    assert type(result[0].frost_days) is int


def test_july_start_d73_boundary_month_assignment_and_year_span():
    # Kills `month > start_month` vs `month >= start_month` mutant:
    # 2001-06 belongs to ag_year 2000 (partial), 2001-07..2002-06 to ag_year 2001 (complete),
    # and 2002-07 belongs to ag_year 2002 (partial).
    entries = (
        [MonthlyFrostHeatCount(year=2001, month=6, frost_days=9, heat_days=9)]
        + _build_ag_year_monthly_counts(
            2001,
            7,
            frost_by_index=list(range(1, 13)),
            heat_by_index=[idx * 2 for idx in range(1, 13)],
        )
        + [MonthlyFrostHeatCount(year=2002, month=7, frost_days=4, heat_days=4)]
    )
    result = ag_year_thermal_counts(entries, ag_year_start=PLACEHOLDER_AG_START_JULY)
    assert [item.ag_year for item in result] == [2000, 2001, 2002]

    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"
    assert isinstance(result[0].heat_days, Missing)
    assert result[0].heat_days.reason == "NO_COVERAGE"

    assert result[1] == AgYearThermalCount(ag_year=2001, frost_days=78, heat_days=156)

    assert isinstance(result[2].frost_days, Missing)
    assert result[2].frost_days.reason == "NO_COVERAGE"
    assert isinstance(result[2].heat_days, Missing)
    assert result[2].heat_days.reason == "NO_COVERAGE"


@pytest.mark.parametrize("start_month", range(1, 13))
def test_ag_year_convention_matches_whole_ag_years_for_all_start_months(
    start_month: int,
):
    # Multi-year monthly span 2001-01 .. 2003-12 cross-checked against
    # api.carbon_forcing.whole_ag_years.
    first_day = dt.date(2001, 1, 1)
    last_day = dt.date(2003, 12, 31)
    monthly = [
        MonthlyFrostHeatCount(year=year, month=month, frost_days=1, heat_days=2)
        for year in (2001, 2002, 2003)
        for month in range(1, 13)
    ]
    result = ag_year_thermal_counts(
        monthly, ag_year_start=YearMonth(year=2001, month=start_month)
    )
    expected_whole = whole_ag_years(start_month, first_day, last_day)
    assert expected_whole is not None
    whole_range = set(range(expected_whole[0], expected_whole[1] + 1))

    for item in result:
        if item.ag_year in whole_range:
            assert item.frost_days == 12
            assert item.heat_days == 24
        else:
            assert isinstance(item.frost_days, Missing)
            assert item.frost_days.reason == "NO_COVERAGE"
            assert isinstance(item.heat_days, Missing)
            assert item.heat_days.reason == "NO_COVERAGE"


# --- C5.5: 12-month coverage enforcement & mutant killers -------------------


@pytest.mark.parametrize("drop_index", [0, 5, 6, 11])
def test_dropping_any_single_month_yields_no_coverage(drop_index: int):
    # Kills range/endpoint mutants when first, boundary, or last month is dropped.
    monthly = _build_ag_year_monthly_counts(2001, 7)
    dropped = monthly.pop(drop_index)
    result = ag_year_thermal_counts(monthly, ag_year_start=PLACEHOLDER_AG_START_JULY)
    assert len(result) == 1
    assert result[0].ag_year == 2001
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"
    assert f"{dropped.year:04d}-{dropped.month:02d}" in (
        result[0].frost_days.detail or ""
    )
    assert isinstance(result[0].heat_days, Missing)
    assert result[0].heat_days.reason == "NO_COVERAGE"


def test_incomplete_coverage_takes_precedence_over_monthly_missing_count():
    # Kills swapping 12-month coverage check with Missing propagation.
    monthly = _build_ag_year_monthly_counts(
        2001,
        7,
        frost_by_index=[
            Missing(reason="MISSING_INPUT", detail="PLACEHOLDER missing month")
            if i == 0
            else 1
            for i in range(12)
        ],
    )
    monthly.pop()  # drop 2002-06 -> incomplete 11-month agricultural year
    result = ag_year_thermal_counts(monthly, ag_year_start=PLACEHOLDER_AG_START_JULY)
    assert len(result) == 1
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "NO_COVERAGE"
    assert isinstance(result[0].heat_days, Missing)
    assert result[0].heat_days.reason == "NO_COVERAGE"


# --- G4: independent axis evaluation and strict Missing propagation ---------


def test_missing_propagates_independently_per_axis_and_picks_earliest_chronological():
    # Pass entries out of order so 2002-02 appears before 2001-11 in input;
    # chronological earliest missing month in ag_year 2001 (July start) is 2001-11.
    frost_list: list[int | Missing] = [1] * 12
    frost_list[4] = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER nov gap")
    frost_list[7] = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER feb nan")
    monthly = _build_ag_year_monthly_counts(
        2001, 7, frost_by_index=frost_list, heat_by_index=[3] * 12
    )
    result = ag_year_thermal_counts(
        list(reversed(monthly)), ag_year_start=PLACEHOLDER_AG_START_JULY
    )
    assert len(result) == 1
    assert result[0].ag_year == 2001
    assert isinstance(result[0].frost_days, Missing)
    assert result[0].frost_days.reason == "MISSING_INPUT"
    detail = result[0].frost_days.detail or ""
    assert "2001-11" in detail
    assert "2 of 12" in detail
    assert result[0].heat_days == 36


def test_missing_in_one_ag_year_does_not_poison_adjacent_ag_year():
    y1 = _build_ag_year_monthly_counts(
        2001,
        7,
        heat_by_index=[
            Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER nan") if i == 3 else 2
            for i in range(12)
        ],
    )
    y2 = _build_ag_year_monthly_counts(2002, 7)
    result = ag_year_thermal_counts(y1 + y2, ag_year_start=PLACEHOLDER_AG_START_JULY)
    assert len(result) == 2
    assert result[0].ag_year == 2001
    assert result[0].frost_days == 12
    assert isinstance(result[0].heat_days, Missing)
    assert result[0].heat_days.reason == "NOT_COMPUTABLE"

    assert result[1] == AgYearThermalCount(ag_year=2002, frost_days=12, heat_days=24)


# --- End-to-end: summarize_climate_thermal_counts ---------------------------


def test_summarize_climate_thermal_counts_empty_climate():
    monthly, yearly = summarize_climate_thermal_counts(
        _climate([]),
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert monthly == ()
    assert yearly == ()


def test_summarize_climate_thermal_counts_two_calendar_years_with_july_start():
    # Record 2001-01-01 .. 2002-12-31 (730 days). With July start (D73):
    # - ag_year 2000 (2001-01..2001-06): NO_COVERAGE
    # - ag_year 2001 (2001-07..2002-06): 1 frost day per month -> 12, 2 heat days per month -> 24
    # - ag_year 2002 (2002-07..2002-12): NO_COVERAGE
    tmin_days: list[float | InputsMissing] = []
    tmax_days: list[float | InputsMissing] = []
    for year in (2001, 2002):
        for month in range(1, 13):
            tmin_days.extend(
                _month_values(
                    year,
                    month,
                    PLACEHOLDER_FROST_THRESHOLD + 2.0,
                    {1: PLACEHOLDER_FROST_THRESHOLD},
                )
            )
            tmax_days.extend(
                _month_values(
                    year,
                    month,
                    PLACEHOLDER_HEAT_THRESHOLD - 2.0,
                    {
                        1: PLACEHOLDER_HEAT_THRESHOLD,
                        2: PLACEHOLDER_HEAT_THRESHOLD + 1.0,
                    },
                )
            )
    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 1, 1), tmin_days),
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 1, 1), tmax_days),
        ]
    )
    monthly, yearly = summarize_climate_thermal_counts(
        climate,
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(monthly) == 24
    assert [item.ag_year for item in yearly] == [2000, 2001, 2002]
    assert isinstance(yearly[0].frost_days, Missing)
    assert yearly[0].frost_days.reason == "NO_COVERAGE"
    assert isinstance(yearly[0].heat_days, Missing)
    assert yearly[0].heat_days.reason == "NO_COVERAGE"
    assert yearly[1] == AgYearThermalCount(ag_year=2001, frost_days=12, heat_days=24)
    assert isinstance(yearly[2].frost_days, Missing)
    assert yearly[2].frost_days.reason == "NO_COVERAGE"
    assert isinstance(yearly[2].heat_days, Missing)
    assert yearly[2].heat_days.reason == "NO_COVERAGE"


def test_summarize_propagates_missing_input_and_non_finite_independently():
    # Single full ag_year 2001 (2001-07..2002-06):
    # - tmin has one missing day in 2001-08 -> ag_year 2001 frost_days = MISSING_INPUT
    # - tmax has one NaN day in 2002-01 -> ag_year 2001 heat_days = NOT_COMPUTABLE
    tmin_days: list[float | InputsMissing] = []
    tmax_days: list[float | InputsMissing] = []
    for year, month in _ag_year_month_list(2001, 7):
        tmin_overrides: dict[int, float | InputsMissing] | None = (
            {10: InputsMissing(reason="NO_COVERAGE", detail="PLACEHOLDER gap")}
            if (year, month) == (2001, 8)
            else None
        )
        tmin_days.extend(
            _month_values(year, month, PLACEHOLDER_FROST_THRESHOLD, tmin_overrides)
        )
        tmax_days.extend(_month_values(year, month, PLACEHOLDER_HEAT_THRESHOLD))

    # Inject NaN into 2002-01 of tmax via model_construct.
    tmax_built = _daily_series(TEMPERATURE_MAX, dt.date(2001, 7, 1), tmax_days)
    nan_days = [
        DailyValue.model_construct(
            date=item.date,
            value=(math.nan if item.date == dt.date(2002, 1, 15) else item.value),
            missing=item.missing,
        )
        for item in tmax_built.days
    ]
    tmax_constructed = DailySeries.model_construct(
        quantity=tmax_built.quantity,
        unit=tmax_built.unit,
        time_zone=tmax_built.time_zone,
        start_date=tmax_built.start_date,
        end_date=tmax_built.end_date,
        provenance=tmax_built.provenance,
        source=tmax_built.source,
        range_missing=tmax_built.range_missing,
        days=nan_days,
    )
    tmin_built = _daily_series(TEMPERATURE_MIN, dt.date(2001, 7, 1), tmin_days)
    climate = SiteClimate.model_construct(
        contract="site_data_climate",
        example_data=True,
        case_id="placeholder-case",
        field_id="placeholder-field",
        point=_point(),
        daily_series=[tmin_built, tmax_constructed],
        monthly_series=[],
    )

    _, yearly = summarize_climate_thermal_counts(
        climate,
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
        heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
    )
    assert len(yearly) == 1
    assert yearly[0].ag_year == 2001
    assert isinstance(yearly[0].frost_days, Missing)
    assert yearly[0].frost_days.reason == "MISSING_INPUT"
    assert isinstance(yearly[0].heat_days, Missing)
    assert yearly[0].heat_days.reason == "NOT_COMPUTABLE"


def test_summarize_missing_and_non_finite_thresholds():
    tmin_days: list[float | InputsMissing] = []
    tmax_days: list[float | InputsMissing] = []
    for year, month in _ag_year_month_list(2001, 7):
        tmin_days.extend(_month_values(year, month, PLACEHOLDER_FROST_THRESHOLD))
        tmax_days.extend(_month_values(year, month, PLACEHOLDER_HEAT_THRESHOLD))
    climate = _climate(
        [
            _daily_series(TEMPERATURE_MIN, dt.date(2001, 7, 1), tmin_days),
            _daily_series(TEMPERATURE_MAX, dt.date(2001, 7, 1), tmax_days),
        ]
    )
    _, yearly = summarize_climate_thermal_counts(
        climate,
        ag_year_start=PLACEHOLDER_AG_START_JULY,
        frost_threshold_deg_c=Missing(reason="NOT_DECLARED", detail="PLACEHOLDER"),
        heat_threshold_deg_c=math.inf,
    )
    assert len(yearly) == 1
    assert isinstance(yearly[0].frost_days, Missing)
    assert yearly[0].frost_days.reason == "NOT_DECLARED"
    assert isinstance(yearly[0].heat_days, Missing)
    assert yearly[0].heat_days.reason == "NOT_COMPUTABLE"


# --- G5: caller TypeError & ValueError checks -------------------------------


@pytest.mark.parametrize(
    "bad_sequence",
    [None, 123, "2001-01", b"2001-01", {}, set(), (x for x in ())],
)
def test_wrong_monthly_counts_container_raises_type_error(bad_sequence):
    with pytest.raises(TypeError, match="monthly_counts"):
        ag_year_thermal_counts(
            bad_sequence,
            ag_year_start=PLACEHOLDER_AG_START_JULY,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("bad_elem", [None, 1, "item", {"year": 2001}])
def test_wrong_monthly_counts_element_raises_type_error(bad_elem):
    with pytest.raises(TypeError, match="MonthlyFrostHeatCount"):
        ag_year_thermal_counts(
            [bad_elem],
            ag_year_start=PLACEHOLDER_AG_START_JULY,  # type: ignore[list-item]
        )


@pytest.mark.parametrize("bad_val", [True, False, 1.5, "1", None])
def test_bad_field_types_in_monthly_count_raise_type_error(bad_val):
    with pytest.raises(TypeError):
        ag_year_thermal_counts(
            [
                MonthlyFrostHeatCount(
                    year=bad_val,
                    month=1,
                    frost_days=0,
                    heat_days=0,  # type: ignore[arg-type]
                )
            ],
            ag_year_start=PLACEHOLDER_AG_START_JULY,
        )
    with pytest.raises(TypeError):
        ag_year_thermal_counts(
            [
                MonthlyFrostHeatCount(
                    year=2001,
                    month=bad_val,
                    frost_days=0,
                    heat_days=0,  # type: ignore[arg-type]
                )
            ],
            ag_year_start=PLACEHOLDER_AG_START_JULY,
        )
    with pytest.raises(TypeError):
        ag_year_thermal_counts(
            [
                MonthlyFrostHeatCount(
                    year=2001,
                    month=1,
                    frost_days=bad_val,
                    heat_days=0,  # type: ignore[arg-type]
                )
            ],
            ag_year_start=PLACEHOLDER_AG_START_JULY,
        )
    with pytest.raises(TypeError):
        ag_year_thermal_counts(
            [
                MonthlyFrostHeatCount(
                    year=2001,
                    month=1,
                    frost_days=0,
                    heat_days=bad_val,  # type: ignore[arg-type]
                )
            ],
            ag_year_start=PLACEHOLDER_AG_START_JULY,
        )


def test_duplicate_month_or_invalid_domain_values_raise_value_error():
    dup = MonthlyFrostHeatCount(year=2001, month=7, frost_days=1, heat_days=2)
    with pytest.raises(ValueError, match="duplicate"):
        ag_year_thermal_counts([dup, dup], ag_year_start=PLACEHOLDER_AG_START_JULY)

    for bad_month in (0, 13):
        with pytest.raises(ValueError, match="month"):
            ag_year_thermal_counts(
                [
                    MonthlyFrostHeatCount(
                        year=2001, month=bad_month, frost_days=0, heat_days=0
                    )
                ],
                ag_year_start=PLACEHOLDER_AG_START_JULY,
            )

    with pytest.raises(ValueError, match="non-negative"):
        ag_year_thermal_counts(
            [MonthlyFrostHeatCount(year=2001, month=7, frost_days=-1, heat_days=0)],
            ag_year_start=PLACEHOLDER_AG_START_JULY,
        )


@pytest.mark.parametrize(
    "bad_start",
    [None, 7, "2001-07", (2001, 7), {"year": 2001, "month": 7}, True],
)
def test_wrong_ag_year_start_raises_type_error_even_on_empty_inputs(bad_start):
    with pytest.raises(TypeError, match="YearMonth"):
        ag_year_thermal_counts([], ag_year_start=bad_start)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="YearMonth"):
        summarize_climate_thermal_counts(
            _climate([]),
            ag_year_start=bad_start,  # type: ignore[arg-type]
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )


def test_constructed_year_month_with_bad_month_raises_type_or_value_error():
    bad_type = YearMonth.model_construct(year=2001, month=True)
    with pytest.raises(TypeError, match="ag_year_start.month"):
        ag_year_thermal_counts([], ag_year_start=bad_type)

    bad_range = YearMonth.model_construct(year=2001, month=13)
    with pytest.raises(ValueError, match="ag_year_start.month"):
        ag_year_thermal_counts([], ag_year_start=bad_range)


@pytest.mark.parametrize("bad_climate", [None, {}, "climate", 123, []])
def test_summarize_wrong_climate_raises_type_error(bad_climate):
    with pytest.raises(TypeError, match="SiteClimate"):
        summarize_climate_thermal_counts(
            bad_climate,  # type: ignore[arg-type]
            ag_year_start=PLACEHOLDER_AG_START_JULY,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )


@pytest.mark.parametrize(
    "bad_threshold",
    [True, False, "2.22", None, [], {}, InputsMissing(reason="NOT_DECLARED")],
)
def test_summarize_wrong_threshold_raises_type_error_even_on_empty_climate(
    bad_threshold,
):
    empty = _climate([])
    with pytest.raises(TypeError, match="frost_threshold_deg_c"):
        summarize_climate_thermal_counts(
            empty,
            ag_year_start=PLACEHOLDER_AG_START_JULY,
            frost_threshold_deg_c=bad_threshold,  # type: ignore[arg-type]
            heat_threshold_deg_c=PLACEHOLDER_HEAT_THRESHOLD,
        )
    with pytest.raises(TypeError, match="heat_threshold_deg_c"):
        summarize_climate_thermal_counts(
            empty,
            ag_year_start=PLACEHOLDER_AG_START_JULY,
            frost_threshold_deg_c=PLACEHOLDER_FROST_THRESHOLD,
            heat_threshold_deg_c=bad_threshold,  # type: ignore[arg-type]
        )
