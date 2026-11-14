"""Acceptance test of unit l0/erosion-r-factor (issue #161).

The cases are PROPOSED (blueprint section 3.7) and are listed in ``README.md``
under "PROPOSED cases"; a test checks that the two lists agree.

**Every constant in this file is a PLACEHOLDER.** The exponent, the threshold,
the regression coefficients and the mean annual level below are plainly not
real: small whole numbers chosen so that the arithmetic can be done by hand.
They are the constants of no method and no case holds an expected value of
the science. The tests against a worked example of each source are the
skipped tests at the end (issue #77, D34).

Run from the repository root: ``python -m pytest engine/erosion/r_factor/``.
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
import math
import re
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import DailySeries
from contracts.results.models import Missing as ResultMissing
from engine.erosion.r_factor import (
    PRECIPITATION_UNIT,
    R_UNIT,
    REASON_UNIT_NOT_ACCEPTED,
    FractionComparison,
    annual_sums,
    checked_daily_precipitation,
    compare_monthly_fractions,
    control_monthly_erosivity,
    daily_erosivity_index,
    monthly_fractions,
    monthly_sums,
    r_by_year_and_month,
    r_factor_parts,
    yearly_ratios,
)
from engine.erosion.r_factor import _checks, control, erosivity

HERE = Path(__file__).parent
README = HERE / "README.md"

# Rounding of floating-point arithmetic only. Not a tolerance of the
# validation protocol.
ROUNDING = 1e-12

# PLACEHOLDER constants: not values of any method.
EXPONENT = 2.0  # PLACEHOLDER: squares, so the index is worked out by hand
THRESHOLD = 3.0  # PLACEHOLDER
COEFFICIENT = 2.0  # PLACEHOLDER
CONTROL_EXPONENT = 1.0  # PLACEHOLDER: makes the control proportional to the sum
LEVEL = 1000.0  # PLACEHOLDER mean annual level

PLACEHOLDER_SOURCE = "PLACEHOLDER: test series, not a real place, no real source"


def a_series(
    start: str, values: list[float | None], unit: str = PRECIPITATION_UNIT
) -> DailySeries:
    """A daily series from ``start``; ``None`` is a missing day (never zero rain)."""
    first = dt.date.fromisoformat(start)
    days = []
    for offset, value in enumerate(values):
        date = (first + dt.timedelta(days=offset)).isoformat()
        if value is None:
            days.append(
                {
                    "date": date,
                    "value": None,
                    "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER gap"},
                }
            )
        else:
            days.append({"date": date, "value": float(value)})
    body = {
        "quantity": "precipitation",
        "unit": unit,
        "time_zone": "UTC",
        "start_date": start,
        "end_date": (first + dt.timedelta(days=len(values) - 1)).isoformat(),
        "days": days,
    }
    if any(value is not None for value in values):
        body.update(
            provenance="OBSERVED",
            source=PLACEHOLDER_SOURCE,
            range_missing={"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
        )
    return DailySeries.model_validate(body)


def days_between(start: str, end: str) -> int:
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1


def rain_pattern(count: int, *, scale: float = 1.0) -> list[float]:
    """PLACEHOLDER rain: a repeating pattern of whole millimetres."""
    return [scale * (offset % 7) for offset in range(count)]


def years_series(first_year: int, last_year: int, **pattern) -> DailySeries:
    start = f"{first_year}-01-01"
    count = days_between(start, f"{last_year}-12-31")
    return a_series(start, rain_pattern(count, **pattern))


def index_of(series: DailySeries):
    return daily_erosivity_index(
        series=series,
        exponent=EXPONENT,
        threshold=THRESHOLD,
        threshold_unit=PRECIPITATION_UNIT,
    )


def is_missing(item: object, reason: str | None = None) -> bool:
    return isinstance(item, ResultMissing) and (reason is None or item.reason == reason)


# --- The daily index ------------------------------------------------------


def test_index_day_at_or_below_the_threshold_adds_nothing():
    series = a_series("2001-01-01", [0.0, 1.0, THRESHOLD - 1, THRESHOLD])
    index = index_of(series)
    assert list(index.values()) == [0.0, 0.0, 0.0, 0.0]
    # The nearest number above the threshold already adds something.
    (above,) = index_of(
        a_series("2001-01-01", [math.nextafter(THRESHOLD, math.inf)])
    ).values()
    assert above > 0


def test_index_grows_with_precipitation_above_the_threshold():
    amounts = [THRESHOLD + step for step in (1.0, 2.0, 5.0, 11.0)]
    index = index_of(a_series("2001-01-01", amounts))
    values = list(index.values())
    assert all(value > 0 for value in values)
    assert values == sorted(values) and len(set(values)) == len(values)


def test_index_by_hand_with_placeholder_constants():
    index = index_of(a_series("2001-01-01", [5.0, 4.0, 3.0]))
    # 5 ** 2 and 4 ** 2 above the PLACEHOLDER threshold of 3; 3 is at it.
    assert list(index.values()) == [25.0, 16.0, 0.0]


def test_index_missing_day_stays_missing_and_is_never_zero_rain():
    index = index_of(a_series("2001-01-01", [5.0, None, 0.0]))
    first, gap, dry = index.values()
    assert first == 25.0 and dry == 0.0
    assert is_missing(gap, "MISSING_INPUT")
    assert "2001-01-02" in gap.detail and "NO_COVERAGE" in gap.detail


def test_index_negative_or_non_finite_precipitation_is_not_clipped():
    series = a_series("2001-01-01", [5.0, 5.0, 5.0])
    # A DailySeries refuses a value that is not finite, so the items are
    # changed past its validation, as a defective caller could.
    series.days[1].value = -1.0
    series.days[2].value = math.inf
    precipitation = checked_daily_precipitation(series=series)
    index = index_of(series)
    for table in (precipitation, index):
        _, negative, infinite = table.values()
        assert is_missing(negative, "NOT_COMPUTABLE") and "negative" in negative.detail
        assert "not clipped" in negative.detail
        assert is_missing(infinite, "NOT_COMPUTABLE") and "finite" in infinite.detail


@pytest.mark.parametrize("shape", [InputMissing, ResultMissing])
def test_index_missing_or_non_finite_constant_gives_missing_naming_it(shape):
    series = a_series("2001-01-01", [5.0])
    gone = shape(reason="NOT_DECLARED", detail="PLACEHOLDER")
    for name in ("exponent", "threshold"):
        arguments = {"exponent": EXPONENT, "threshold": THRESHOLD, name: gone}
        result = daily_erosivity_index(
            series=series, threshold_unit=PRECIPITATION_UNIT, **arguments
        )
        assert is_missing(result, "MISSING_INPUT") and name in result.detail
        assert "NOT_DECLARED" in result.detail
    both = daily_erosivity_index(
        series=series, exponent=gone, threshold=gone, threshold_unit=PRECIPITATION_UNIT
    )
    assert "exponent" in both.detail and "threshold" in both.detail
    for bad in (math.nan, math.inf, 10**400):
        result = daily_erosivity_index(
            series=series,
            exponent=bad,
            threshold=THRESHOLD,
            threshold_unit=PRECIPITATION_UNIT,
        )
        assert is_missing(result, "NOT_COMPUTABLE") and "exponent" in result.detail


def test_index_unit_other_than_mm_per_day_is_not_converted():
    other = a_series("2001-01-01", [5.0], unit="PLACEHOLDER_unit")
    for table in (checked_daily_precipitation(series=other), index_of(other)):
        assert is_missing(table, REASON_UNIT_NOT_ACCEPTED)
        assert "PLACEHOLDER_unit" in table.detail and "not converted" in table.detail
    result = daily_erosivity_index(
        series=a_series("2001-01-01", [5.0]),
        exponent=EXPONENT,
        threshold=THRESHOLD,
        threshold_unit="PLACEHOLDER_unit",
    )
    assert is_missing(result, REASON_UNIT_NOT_ACCEPTED) and "threshold" in result.detail


def test_index_result_that_is_not_finite_is_not_computed():
    series = a_series("2001-01-01", [5.0])
    result = daily_erosivity_index(
        series=series,
        exponent=1e6,
        threshold=THRESHOLD,
        threshold_unit=PRECIPITATION_UNIT,
    )
    (day,) = result.values()
    assert is_missing(day, "NOT_COMPUTABLE")


# --- Monthly sums ---------------------------------------------------------


def test_monthly_sums_add_the_days_of_each_month():
    series = a_series("2001-01-01", rain_pattern(59))  # January and February 2001
    index = index_of(series)
    sums = monthly_sums(daily=index)
    assert list(sums) == [(2001, 1), (2001, 2)]
    january = math.fsum(v for d, v in index.items() if d.month == 1)
    february = math.fsum(v for d, v in index.items() if d.month == 2)
    assert sums[(2001, 1)] == january and sums[(2001, 2)] == february


def test_monthly_sum_with_a_missing_day_is_missing_input_naming_the_day():
    values: list[float | None] = rain_pattern(59)
    values[40] = None  # 2001-02-10
    sums = monthly_sums(daily=index_of(a_series("2001-01-01", values)))
    assert isinstance(sums[(2001, 1)], float)
    february = sums[(2001, 2)]
    assert is_missing(february, "MISSING_INPUT")
    assert "2001-02-10" in february.detail


def test_monthly_sum_of_a_partly_covered_month_is_no_coverage():
    # From 15 January to 10 March: January and March are cut by the extent.
    start, end = "2001-01-15", "2001-03-10"
    sums = monthly_sums(
        daily=index_of(a_series(start, rain_pattern(days_between(start, end))))
    )
    assert (
        is_missing(sums[(2001, 1)], "NO_COVERAGE")
        and "17 of the 31" in sums[(2001, 1)].detail
    )
    assert isinstance(sums[(2001, 2)], float)
    assert is_missing(sums[(2001, 3)], "NO_COVERAGE")


def test_a_missing_table_is_missing_input_that_names_it():
    gone = ResultMissing(reason="NOT_DECLARED", detail="PLACEHOLDER")
    for result, name in (
        (monthly_sums(daily=gone), "daily"),
        (annual_sums(monthly=gone, start_month=1), "monthly"),
        (monthly_fractions(monthly=gone, start_month=1), "monthly"),
        (yearly_ratios(annual=gone), "annual"),
        (
            r_by_year_and_month(
                mean_annual_r=LEVEL,
                mean_annual_r_unit=R_UNIT,
                monthly_fractions=gone,
                yearly_ratios={},
            ),
            "monthly_fractions",
        ),
        (
            r_by_year_and_month(
                mean_annual_r=LEVEL,
                mean_annual_r_unit=R_UNIT,
                monthly_fractions={},
                yearly_ratios=gone,
            ),
            "yearly_ratios",
        ),
        (
            compare_monthly_fractions(index_fractions=gone, control_fractions={}),
            "index_fractions",
        ),
        (
            compare_monthly_fractions(index_fractions={}, control_fractions=gone),
            "control_fractions",
        ),
    ):
        assert is_missing(result, "MISSING_INPUT") and result.detail.startswith(name)


# --- Annual sums ----------------------------------------------------------


def test_annual_sums_follow_the_start_month():
    sums = monthly_sums(daily=index_of(years_series(2001, 2003)))
    calendar_years = annual_sums(monthly=sums, start_month=1)
    assert list(calendar_years) == [2001, 2002, 2003]
    for year, total in calendar_years.items():
        assert total == pytest.approx(
            math.fsum(v for (y, _), v in sums.items() if y == year), abs=ROUNDING
        )
    # Start month 7 (a month of the case, not of the method): 2000 and 2003
    # are cut by the extent; 2001 runs from July 2001 to June 2002.
    ag_years = annual_sums(monthly=sums, start_month=7)
    assert list(ag_years) == [2000, 2001, 2002, 2003]
    assert is_missing(ag_years[2000], "NO_COVERAGE") and is_missing(
        ag_years[2003], "NO_COVERAGE"
    )
    expected = math.fsum(
        v
        for (y, m), v in sums.items()
        if (y == 2001 and m >= 7) or (y == 2002 and m < 7)
    )
    assert ag_years[2001] == pytest.approx(expected, abs=ROUNDING)


def test_annual_sum_of_an_incomplete_year_is_no_coverage():
    start, end = "2001-03-01", "2002-12-31"
    sums = monthly_sums(
        daily=index_of(a_series(start, rain_pattern(days_between(start, end))))
    )
    annual = annual_sums(monthly=sums, start_month=1)
    assert is_missing(annual[2001], "NO_COVERAGE")
    assert "2001-01" in annual[2001].detail and "2001-02" in annual[2001].detail
    assert isinstance(annual[2002], float)


def test_annual_sum_with_a_missing_month_is_missing_input():
    values: list[float | None] = rain_pattern(days_between("2001-01-01", "2002-12-31"))
    values[100] = None  # in April 2001
    annual = annual_sums(
        monthly=monthly_sums(daily=index_of(a_series("2001-01-01", values))),
        start_month=1,
    )
    assert (
        is_missing(annual[2001], "MISSING_INPUT") and "2001-04" in annual[2001].detail
    )
    assert isinstance(annual[2002], float)


# --- Monthly fractions ----------------------------------------------------


def test_monthly_fractions_of_a_year_add_up_to_one():
    sums = monthly_sums(daily=index_of(years_series(2001, 2003)))
    for start_month in (1, 7):
        fractions = monthly_fractions(monthly=sums, start_month=start_month)
        for months in fractions.values():
            assert len(months) == 12
            if all(isinstance(v, float) for v in months.values()):
                assert math.fsum(months.values()) == pytest.approx(1.0, abs=ROUNDING)
                assert all(v >= 0 for v in months.values())


def test_a_year_without_an_erosive_day_has_no_fraction():
    # 2001 never goes above the PLACEHOLDER threshold; 2002 does.
    dry = [THRESHOLD] * 365
    wet = rain_pattern(365, scale=2.0)
    fractions = monthly_fractions(
        monthly=monthly_sums(daily=index_of(a_series("2001-01-01", dry + wet))),
        start_month=1,
    )
    for value in fractions[2001].values():
        assert is_missing(value, "NOT_COMPUTABLE")
        assert "zero" in value.detail and "not split equally" in value.detail
    assert math.fsum(fractions[2002].values()) == pytest.approx(1.0, abs=ROUNDING)


def test_fractions_of_a_missing_year_carry_the_reason():
    start, end = "2001-03-01", "2002-12-31"
    values: list[float | None] = rain_pattern(days_between(start, end))
    values[-3] = None  # 2002-12-29
    fractions = monthly_fractions(
        monthly=monthly_sums(daily=index_of(a_series(start, values))), start_month=1
    )
    assert all(is_missing(v, "NO_COVERAGE") for v in fractions[2001].values())
    assert all(is_missing(v, "MISSING_INPUT") for v in fractions[2002].values())


def test_a_missing_day_makes_its_month_and_its_year_missing_and_no_other():
    values: list[float | None] = rain_pattern(days_between("2001-01-01", "2003-12-31"))
    values[400] = None  # 2002-02-05
    series = a_series("2001-01-01", values)
    parts = r_factor_parts(
        series=series,
        exponent=EXPONENT,
        threshold=THRESHOLD,
        threshold_unit=PRECIPITATION_UNIT,
        start_month=1,
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
    )
    missing_days = [d for d, v in parts.daily_index.items() if is_missing(v)]
    assert missing_days == [dt.date(2002, 2, 5)]
    missing_months = [m for m, v in parts.monthly_index_sums.items() if is_missing(v)]
    assert missing_months == [(2002, 2)]
    assert [y for y, v in parts.annual_index_sums.items() if is_missing(v)] == [2002]
    for year in (2001, 2003):
        assert all(isinstance(v, float) for v in parts.monthly_fractions[year].values())
        assert isinstance(parts.yearly_ratios[year], float)
        assert all(
            isinstance(v, float) for v in parts.r_by_year_and_month[year].values()
        )
    assert all(
        is_missing(v, "MISSING_INPUT") for v in parts.r_by_year_and_month[2002].values()
    )


# --- Yearly ratios --------------------------------------------------------


def test_yearly_ratios_average_to_one_over_the_years_where_they_are_defined():
    count = days_between("2001-01-01", "2004-12-31")
    values = [
        amount * (1 + offset // 400)
        for offset, amount in enumerate(rain_pattern(count))
    ]
    sums = monthly_sums(daily=index_of(a_series("2001-01-01", values)))
    ratios = yearly_ratios(annual=annual_sums(monthly=sums, start_month=1))
    assert list(ratios) == [2001, 2002, 2003, 2004]
    assert len(set(ratios.values())) == 4
    assert math.fsum(ratios.values()) / len(ratios) == pytest.approx(1.0, abs=ROUNDING)


def test_a_missing_year_has_a_missing_ratio_and_is_left_out_of_the_mean():
    annual = {
        2001: 10.0,
        2002: ResultMissing(reason="MISSING_INPUT", detail="PLACEHOLDER month"),
        2003: 30.0,
        2004: ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER extent"),
    }
    ratios = yearly_ratios(annual=annual)
    assert ratios[2001] == 0.5 and ratios[2003] == 1.5
    assert is_missing(ratios[2002], "MISSING_INPUT") and "2002" in ratios[2002].detail
    assert is_missing(ratios[2004], "NO_COVERAGE")


def test_yearly_ratios_with_a_zero_mean_are_not_computed():
    ratios = yearly_ratios(annual={2001: 0.0, 2002: 0.0})
    assert all(is_missing(v, "NOT_COMPUTABLE") for v in ratios.values())
    # A zero year next to an erosive one is a real ratio of zero.
    assert yearly_ratios(annual={2001: 0.0, 2002: 8.0}) == {2001: 0.0, 2002: 2.0}


# --- R by year and month --------------------------------------------------


def test_r_is_the_level_times_the_fraction_times_the_ratio():
    fractions = {2001: {(2001, m): (0.5 if m in (1, 2) else 0.0) for m in range(1, 13)}}
    result = r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions=fractions,
        yearly_ratios={2001: 2.0},
    )
    assert result[2001][(2001, 1)] == LEVEL * 0.5 * 2.0
    assert result[2001][(2001, 3)] == 0.0


def test_r_of_a_year_adds_up_to_level_times_ratio_and_averages_to_the_level():
    count = days_between("2001-01-01", "2004-12-31")
    values = [
        amount * (1 + offset // 500)
        for offset, amount in enumerate(rain_pattern(count))
    ]
    parts = r_factor_parts(
        series=a_series("2001-01-01", values),
        exponent=EXPONENT,
        threshold=THRESHOLD,
        threshold_unit=PRECIPITATION_UNIT,
        start_month=1,
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
    )
    totals = []
    for year, months in parts.r_by_year_and_month.items():
        total = math.fsum(months.values())
        assert total == pytest.approx(LEVEL * parts.yearly_ratios[year], rel=ROUNDING)
        totals.append(total)
    assert math.fsum(totals) / len(totals) == pytest.approx(LEVEL, rel=ROUNDING)


@pytest.mark.parametrize("shape", [InputMissing, ResultMissing])
def test_a_missing_level_makes_r_missing_and_keeps_fractions_and_ratios(shape):
    parts = r_factor_parts(
        series=years_series(2001, 2002),
        exponent=EXPONENT,
        threshold=THRESHOLD,
        threshold_unit=PRECIPITATION_UNIT,
        start_month=1,
        mean_annual_r=shape(reason="NOT_DECLARED", detail="PLACEHOLDER"),
        mean_annual_r_unit=R_UNIT,
    )
    assert is_missing(parts.r_by_year_and_month, "MISSING_INPUT")
    assert "mean_annual_r" in parts.r_by_year_and_month.detail
    assert all(isinstance(v, float) for v in parts.yearly_ratios.values())
    for months in parts.monthly_fractions.values():
        assert math.fsum(months.values()) == pytest.approx(1.0, abs=ROUNDING)
    not_finite = r_by_year_and_month(
        mean_annual_r=math.nan,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions=parts.monthly_fractions,
        yearly_ratios=parts.yearly_ratios,
    )
    assert (
        is_missing(not_finite, "NOT_COMPUTABLE")
        and "mean_annual_r" in not_finite.detail
    )


def test_a_level_in_another_unit_is_not_converted():
    result = r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit="PLACEHOLDER_unit",
        monthly_fractions={},
        yearly_ratios={},
    )
    assert is_missing(result, REASON_UNIT_NOT_ACCEPTED)
    assert "PLACEHOLDER_unit" in result.detail and "not converted" in result.detail


def test_r_of_a_month_with_a_missing_fraction_or_ratio_is_missing():
    gap = ResultMissing(reason="MISSING_INPUT", detail="PLACEHOLDER")
    extent = ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER")
    fractions = {
        2001: {(2001, 1): gap, (2001, 2): 1.0},
        2002: {(2002, 1): extent},
        2003: {(2003, 1): 1.0},
    }
    result = r_by_year_and_month(
        mean_annual_r=LEVEL,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions=fractions,
        yearly_ratios={2001: 1.0, 2002: extent},
    )
    assert is_missing(result[2001][(2001, 1)], "MISSING_INPUT")
    assert result[2001][(2001, 2)] == LEVEL
    assert is_missing(result[2002][(2002, 1)], "NO_COVERAGE")
    missing_ratio = result[2003][(2003, 1)]
    assert is_missing(missing_ratio, "MISSING_INPUT") and "2003" in missing_ratio.detail


# --- The control regression -----------------------------------------------


def test_control_is_the_coefficient_times_a_power_of_monthly_precipitation():
    series = a_series("2001-01-01", rain_pattern(59))
    control_values = control_monthly_erosivity(
        series=series, coefficient=3.0, exponent=2.0
    )
    january = math.fsum(rain_pattern(59)[:31])
    february = math.fsum(rain_pattern(59)[31:])
    assert control_values == {(2001, 1): 3.0 * january**2, (2001, 2): 3.0 * february**2}


@pytest.mark.parametrize("shape", [InputMissing, ResultMissing])
def test_control_missing_or_non_finite_coefficient_gives_missing_naming_it(shape):
    series = a_series("2001-01-01", rain_pattern(31))
    gone = shape(reason="NOT_DECLARED", detail="PLACEHOLDER")
    for name in ("coefficient", "exponent"):
        arguments = {
            "coefficient": COEFFICIENT,
            "exponent": CONTROL_EXPONENT,
            name: gone,
        }
        result = control_monthly_erosivity(series=series, **arguments)
        assert is_missing(result, "MISSING_INPUT") and name in result.detail
    result = control_monthly_erosivity(
        series=series, coefficient=math.inf, exponent=1.0
    )
    assert is_missing(result, "NOT_COMPUTABLE") and "coefficient" in result.detail
    other = a_series("2001-01-01", rain_pattern(31), unit="PLACEHOLDER_unit")
    result = control_monthly_erosivity(
        series=other, coefficient=COEFFICIENT, exponent=1.0
    )
    assert is_missing(result, REASON_UNIT_NOT_ACCEPTED)


def test_control_month_with_a_missing_day_or_cut_by_the_extent_is_missing():
    values: list[float | None] = rain_pattern(days_between("2001-01-10", "2001-03-31"))
    values[30] = None  # 2001-02-09
    control_values = control_monthly_erosivity(
        series=a_series("2001-01-10", values),
        coefficient=COEFFICIENT,
        exponent=CONTROL_EXPONENT,
    )
    assert is_missing(control_values[(2001, 1)], "NO_COVERAGE")
    assert is_missing(control_values[(2001, 2)], "MISSING_INPUT")
    assert "2001-02-09" in control_values[(2001, 2)].detail
    assert isinstance(control_values[(2001, 3)], float)


def test_the_comparison_reports_both_fractions_and_changes_neither():
    series = years_series(2001, 2002)
    index_fractions = monthly_fractions(
        monthly=monthly_sums(daily=index_of(series)), start_month=1
    )
    kept = {year: dict(months) for year, months in index_fractions.items()}
    control_fractions = monthly_fractions(
        monthly=control_monthly_erosivity(
            series=series, coefficient=COEFFICIENT, exponent=CONTROL_EXPONENT
        ),
        start_month=1,
    )
    for months in control_fractions.values():
        assert math.fsum(months.values()) == pytest.approx(1.0, abs=ROUNDING)
    report = compare_monthly_fractions(
        index_fractions=index_fractions, control_fractions=control_fractions
    )
    assert index_fractions == kept
    for year, months in report.items():
        assert len(months) == 12
        for year_month, row in months.items():
            assert isinstance(row, FractionComparison)
            assert row.index_fraction == index_fractions[year][year_month]
            assert row.control_fraction == control_fractions[year][year_month]
            assert row.difference == row.index_fraction - row.control_fraction


def test_a_month_missing_in_either_table_has_a_missing_difference():
    gap = ResultMissing(reason="MISSING_INPUT", detail="PLACEHOLDER")
    extent = ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER")
    report = compare_monthly_fractions(
        index_fractions={2001: {(2001, 1): 0.25, (2001, 2): gap, (2001, 3): extent}},
        control_fractions={
            2001: {(2001, 1): 0.5, (2001, 2): 0.5, (2001, 3): extent},
            2002: {},
        },
    )
    assert report[2001][(2001, 1)].difference == -0.25
    assert is_missing(report[2001][(2001, 2)].difference, "MISSING_INPUT")
    assert is_missing(report[2001][(2001, 3)].difference, "NO_COVERAGE")
    assert report[2002] == {}
    one_sided = compare_monthly_fractions(
        index_fractions={2001: {(2001, 1): 0.25}}, control_fractions={}
    )
    row = one_sided[2001][(2001, 1)]
    assert row.index_fraction == 0.25
    assert is_missing(row.control_fraction, "MISSING_INPUT")
    assert is_missing(row.difference, "MISSING_INPUT")


# --- Defects of the caller ------------------------------------------------

PUBLIC_FUNCTIONS = (
    checked_daily_precipitation,
    daily_erosivity_index,
    monthly_sums,
    annual_sums,
    monthly_fractions,
    yearly_ratios,
    r_by_year_and_month,
    r_factor_parts,
    control_monthly_erosivity,
    compare_monthly_fractions,
)


def test_every_argument_is_passed_by_name_and_none_has_a_default():
    for function in PUBLIC_FUNCTIONS:
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
                function,
                parameter,
            )
            assert parameter.default is inspect.Parameter.empty, (function, parameter)


def test_an_argument_of_another_type_raises_type_error():
    series = a_series("2001-01-01", [5.0])
    for bad in (None, "2.0", True, [2.0]):
        with pytest.raises(TypeError, match="exponent"):
            daily_erosivity_index(
                series=series,
                exponent=bad,
                threshold=THRESHOLD,
                threshold_unit=PRECIPITATION_UNIT,
            )
        with pytest.raises(TypeError, match="mean_annual_r"):
            r_by_year_and_month(
                mean_annual_r=bad,
                mean_annual_r_unit=R_UNIT,
                monthly_fractions={},
                yearly_ratios={},
            )
        with pytest.raises(TypeError, match="coefficient"):
            control_monthly_erosivity(series=series, coefficient=bad, exponent=1.0)
    with pytest.raises(TypeError, match="series"):
        checked_daily_precipitation(series={"days": []})
    with pytest.raises(TypeError, match="threshold_unit"):
        daily_erosivity_index(
            series=series, exponent=EXPONENT, threshold=THRESHOLD, threshold_unit=None
        )
    with pytest.raises(TypeError, match="daily"):
        monthly_sums(daily=[1.0])
    with pytest.raises(TypeError, match="daily"):
        monthly_sums(daily={dt.date(2001, 1, 1): None})
    with pytest.raises(TypeError, match="monthly"):
        annual_sums(monthly={"2001-01": 1.0}, start_month=1)
    with pytest.raises(TypeError, match="annual"):
        yearly_ratios(annual={2001: "1.0"})


def test_a_start_month_outside_one_to_twelve_is_refused():
    sums = monthly_sums(daily=index_of(years_series(2001, 2001)))
    for bad in (0, 13):
        with pytest.raises(ValueError, match="start_month"):
            annual_sums(monthly=sums, start_month=bad)
    for bad in (1.0, True, "1"):
        with pytest.raises(TypeError, match="start_month"):
            monthly_fractions(monthly=sums, start_month=bad)


# --- No coefficient in the modules ----------------------------------------


def test_the_modules_hold_no_number_but_calendar_ones():
    # Only the zero of "adds nothing" and of a zero sum, the one and twelve
    # of month arithmetic, and the two of a (year, month) pair.
    for module in (erosivity, control, _checks):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        numbers = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float, complex))
            and not isinstance(node.value, bool)
        }
        assert numbers <= {0, 1, 2, 12}, (module.__name__, numbers)


def section(title: str) -> str:
    """The text of one second-level section of README.md."""
    text = README.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S
    )
    assert match, f"README.md has no section '{title}'"
    return match.group(1)


def table_rows(text: str) -> list[list[str]]:
    lines = [line for line in text.splitlines() if line.startswith("|")]
    assert len(lines) > 2
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]


def test_readme_lists_every_constant_with_an_empty_value():
    header, _, *rows = table_rows(section("Constants a person has to transcribe"))
    assert header[-1] == "Value"
    assert {row[0] for row in rows} == {
        "`exponent` of `daily_erosivity_index`",
        "`threshold` of `daily_erosivity_index`",
        "`coefficient` of `control_monthly_erosivity`",
        "`exponent` of `control_monthly_erosivity`",
        "`mean_annual_r` of `r_by_year_and_month`",
    }
    identifiers = [row[1] for row in rows]
    assert len(set(identifiers)) == len(identifiers)
    for identifier, value in zip(identifiers, (row[-1] for row in rows), strict=True):
        assert re.fullmatch(r"`[a-z][a-z0-9_]*`", identifier)
        assert value == ""


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_[a-z0-9_]+)`", section("PROPOSED cases")))
    defined = {
        name
        for name, item in globals().items()
        if name.startswith("test_") and callable(item)
    }
    assert listed == defined


# --- Waiting for a person -------------------------------------------------


@pytest.mark.skip(
    reason=(
        "Waits for a worked example of the daily erosivity index of S5 (docs/METHODS.md): "
        "its exponent and threshold in the parameter catalogue, the daily precipitation of "
        "the example, its expected index values and the tolerance, each transcribed with its "
        "locator and checked by a person (issue #77, D34). Whether S5 has such an example is OPEN."
    )
)
def test_s5_daily_index_against_a_worked_example():
    raise AssertionError("not written until a person supplies the example")


@pytest.mark.skip(
    reason=(
        "Waits for a worked example of the daily erosivity index of S6 (docs/METHODS.md): "
        "inputs, expected values and tolerance, transcribed and checked by a person "
        "(issue #77, D34). Whether S6 has such an example is OPEN."
    )
)
def test_s6_daily_index_against_a_worked_example():
    raise AssertionError("not written until a person supplies the example")


@pytest.mark.skip(
    reason=(
        "Waits for a worked example of the regression on monthly precipitation of S7, as S4 "
        "gives it: its coefficients in the parameter catalogue, the monthly precipitation of "
        "the example, the expected values and the tolerance, transcribed and checked by a "
        "person (issue #77, D34)."
    )
)
def test_s7_control_regression_against_a_worked_example():
    raise AssertionError("not written until a person supplies the example")


@pytest.mark.skip(
    reason=(
        "Waits for a published mean annual level of R from S4 at one place, with the monthly "
        "distribution of R there if S4 gives one, the expected values and the tolerance, "
        "transcribed and checked by a person (issue #77, D34). Whether S4 publishes a monthly "
        "distribution is OPEN."
    )
)
def test_s4_r_by_month_against_published_values():
    raise AssertionError("not written until a person supplies the example")
