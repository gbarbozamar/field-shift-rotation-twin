"""Targeted mutant-killing tests for ``engine/erosion/r_factor/``.

Every number in this file is a PLACEHOLDER chosen for hand arithmetic or
boundary checks. None is a value of any method or source.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import DailySeries
from contracts.results.models import Missing as ResultMissing
from engine.erosion.r_factor import (
    PRECIPITATION_UNIT,
    R_UNIT,
    REASON_UNIT_NOT_ACCEPTED,
    annual_sums,
    climatological_monthly_fractions,
    climatological_r_by_year_and_month,
    compare_monthly_fractions,
    control_monthly_erosivity,
    daily_erosivity_index,
    monthly_fractions,
    monthly_sums,
    r_by_year_and_month,
    yearly_ratios,
)

PLACEHOLDER_SOURCE = "PLACEHOLDER: test series, not a real place, no real source"


def _series(
    start: str, values: list[float | None], unit: str = PRECIPITATION_UNIT
) -> DailySeries:
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


def _placeholder_months() -> dict[int, float]:
    return {m: float(m) for m in range(1, 13)}


def _placeholder_fractions() -> dict[int, float]:
    fractions = climatological_monthly_fractions(
        monthly_erosivity=_placeholder_months()
    )
    assert not isinstance(fractions, ResultMissing)
    return fractions


# --- climatology.py ---------------------------------------------------------


def test_climatology_rejects_bool_keys_and_invalid_ag_years_or_fraction_items():
    """Bool month keys, str/bytes/bool ag_years, non-str units, and bad fraction items raise TypeError."""
    bool_key_months = {True: 1.0, **{m: float(m) for m in range(2, 13)}}
    with pytest.raises(TypeError, match="monthly_erosivity"):
        climatological_monthly_fractions(monthly_erosivity=bool_key_months)

    fractions = _placeholder_fractions()
    for bad_years in ("", b"", [True]):
        with pytest.raises(TypeError, match="ag_years"):
            climatological_r_by_year_and_month(
                mean_annual_r=1.0,
                mean_annual_r_unit=R_UNIT,
                fractions=fractions,
                ag_years=bad_years,
                start_month=1,
            )

    with pytest.raises(TypeError, match="mean_annual_r_unit"):
        climatological_r_by_year_and_month(
            mean_annual_r=1.0,
            mean_annual_r_unit=None,
            fractions=fractions,
            ag_years=[2001],
            start_month=1,
        )

    for bad_item in (True, "0.1", None, InputMissing(reason="NOT_DECLARED")):
        bad_fractions = dict(fractions)
        bad_fractions[1] = bad_item
        with pytest.raises(TypeError, match="fractions"):
            climatological_r_by_year_and_month(
                mean_annual_r=1.0,
                mean_annual_r_unit=R_UNIT,
                fractions=bad_fractions,
                ag_years=[2001],
                start_month=1,
            )


def test_climatology_allows_single_zero_month_and_names_all_negative_months():
    """A zero month with positive total gives fraction 0.0; multiple negatives are all named."""
    with_zero = _placeholder_months()
    with_zero[1] = 0.0
    fractions = climatological_monthly_fractions(monthly_erosivity=with_zero)
    assert not isinstance(fractions, ResultMissing)
    assert fractions[1] == 0.0
    assert math.fsum(fractions.values()) == pytest.approx(1.0, abs=1e-12)

    two_neg = _placeholder_months()
    two_neg[2] = -1.0
    two_neg[5] = -2.0
    result = climatological_monthly_fractions(monthly_erosivity=two_neg)
    assert isinstance(result, ResultMissing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "month 02" in result.detail and "month 05" in result.detail


def test_climatology_r_precedence_empty_dedup_missing_fraction_and_overflow():
    """Missing/non-finite level precedes unit error; empty/dup ag_years and overflow behave cleanly."""
    fractions = _placeholder_fractions()
    gone = InputMissing(reason="NOT_DECLARED", detail="PLACEHOLDER")

    missing_first = climatological_r_by_year_and_month(
        mean_annual_r=gone,
        mean_annual_r_unit="PLACEHOLDER_unit",
        fractions=ResultMissing(reason="NOT_AVAILABLE"),
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(missing_first, ResultMissing)
    assert missing_first.reason == "MISSING_INPUT"
    assert "mean_annual_r" in missing_first.detail

    nan_before_unit = climatological_r_by_year_and_month(
        mean_annual_r=math.nan,
        mean_annual_r_unit="PLACEHOLDER_unit",
        fractions=fractions,
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(nan_before_unit, ResultMissing)
    assert nan_before_unit.reason == "NOT_COMPUTABLE"
    assert "mean_annual_r" in nan_before_unit.detail
    assert "not converted" not in nan_before_unit.detail

    unit_before_fractions = climatological_r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit="PLACEHOLDER_unit",
        fractions=ResultMissing(reason="NOT_AVAILABLE"),
        ag_years=[2001],
        start_month=1,
    )
    assert isinstance(unit_before_fractions, ResultMissing)
    assert unit_before_fractions.reason == REASON_UNIT_NOT_ACCEPTED
    assert "not converted" in unit_before_fractions.detail

    assert (
        climatological_r_by_year_and_month(
            mean_annual_r=1.0,
            mean_annual_r_unit=R_UNIT,
            fractions=fractions,
            ag_years=[],
            start_month=1,
        )
        == {}
    )

    dedup = climatological_r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit=R_UNIT,
        fractions=fractions,
        ag_years=[2002, 2001, 2002],
        start_month=1,
    )
    assert not isinstance(dedup, ResultMissing)
    assert list(dedup) == [2001, 2002]

    no_cov_frac = dict(fractions)
    no_cov_frac[4] = ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER")
    with_no_cov = climatological_r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit=R_UNIT,
        fractions=no_cov_frac,
        ag_years=[2001],
        start_month=1,
    )
    assert not isinstance(with_no_cov, ResultMissing)
    cell = with_no_cov[2001][(2001, 4)]
    assert isinstance(cell, ResultMissing) and cell.reason == "MISSING_INPUT"

    overflow = climatological_r_by_year_and_month(
        mean_annual_r=1e308,
        mean_annual_r_unit=R_UNIT,
        fractions={m: 10.0 for m in range(1, 13)},
        ag_years=[2001],
        start_month=1,
    )
    assert not isinstance(overflow, ResultMissing)
    assert all(
        isinstance(c, ResultMissing) and c.reason == "NOT_COMPUTABLE"
        for c in overflow[2001].values()
    )


# --- _checks.py and erosivity.py --------------------------------------------


def test_daily_index_precedence_and_zero_threshold_boundary():
    """Missing constant precedes non-finite; non-finite precedes unit; threshold==0 uses <=."""
    series = _series("2001-01-01", [0.0, 1.0])
    gone = InputMissing(reason="NOT_DECLARED", detail="PLACEHOLDER")

    missing_wins = daily_erosivity_index(
        series=series,
        exponent=gone,
        threshold=math.nan,
        threshold_unit="PLACEHOLDER_unit",
    )
    assert isinstance(missing_wins, ResultMissing)
    assert missing_wins.reason == "MISSING_INPUT"
    assert "exponent" in missing_wins.detail

    nan_wins = daily_erosivity_index(
        series=series,
        exponent=math.inf,
        threshold=0.0,
        threshold_unit="PLACEHOLDER_unit",
    )
    assert isinstance(nan_wins, ResultMissing)
    assert nan_wins.reason == "NOT_COMPUTABLE"
    assert "exponent" in nan_wins.detail
    assert "not converted" not in nan_wins.detail

    other_series = _series("2001-01-01", [1.0], unit="PLACEHOLDER_series_unit")
    thresh_unit_first = daily_erosivity_index(
        series=other_series,
        exponent=2.0,
        threshold=0.0,
        threshold_unit="PLACEHOLDER_threshold_unit",
    )
    assert isinstance(thresh_unit_first, ResultMissing)
    assert thresh_unit_first.reason == REASON_UNIT_NOT_ACCEPTED
    assert "threshold" in thresh_unit_first.detail

    with pytest.raises(TypeError, match="threshold_unit"):
        daily_erosivity_index(
            series=series, exponent=2.0, threshold=0.0, threshold_unit=123
        )

    # With negative exponent, amount == threshold == 0.0 must take the <= branch (0.0), not 0 ** -1.
    boundary = daily_erosivity_index(
        series=series,
        exponent=-1.0,
        threshold=0.0,
        threshold_unit=PRECIPITATION_UNIT,
    )
    assert not isinstance(boundary, ResultMissing)
    assert boundary[dt.date(2001, 1, 1)] == 0.0
    assert boundary[dt.date(2001, 1, 2)] == 1.0


def test_mapping_and_key_type_guards_reject_datetime_bool_and_bad_year_months():
    """dt.datetime, bool values/keys, invalid (year, month) pairs, and ResultMissing year rows raise."""
    with pytest.raises(TypeError, match="daily"):
        monthly_sums(daily={dt.datetime(2001, 1, 1, 0, 0): 1.0})
    with pytest.raises(TypeError, match="daily"):
        monthly_sums(daily={dt.date(2001, 1, 1): True})

    for bad_key in ((2001, 0), (2001, 13), (2001, True), (True, 1), (2001, 1, 1)):
        with pytest.raises(TypeError, match="monthly"):
            annual_sums(monthly={bad_key: 1.0}, start_month=1)

    with pytest.raises(TypeError, match="annual"):
        yearly_ratios(annual={True: 1.0})

    with pytest.raises(TypeError, match="monthly_fractions"):
        r_by_year_and_month(
            mean_annual_r=1.0,
            mean_annual_r_unit=R_UNIT,
            monthly_fractions={2001: ResultMissing(reason="NO_COVERAGE")},
            yearly_ratios={2001: 1.0},
        )
    with pytest.raises(TypeError, match="monthly_fractions"):
        r_by_year_and_month(
            mean_annual_r=1.0,
            mean_annual_r_unit=R_UNIT,
            monthly_fractions={True: {(2001, 1): 1.0}},
            yearly_ratios={2001: 1.0},
        )


def test_monthly_and_annual_sums_leap_year_precedence_start_12_and_overflow():
    """Leap Feb coverage, empty mappings, NO_COVERAGE > MISSING_INPUT, start_month=12, and overflow."""
    assert monthly_sums(daily={}) == {}
    assert annual_sums(monthly={}, start_month=1) == {}

    feb_28 = {dt.date(2004, 2, day): 1.0 for day in range(1, 29)}
    partial_leap = monthly_sums(daily=feb_28)
    assert isinstance(partial_leap[(2004, 2)], ResultMissing)
    assert partial_leap[(2004, 2)].reason == "NO_COVERAGE"
    assert "28 of the 29" in partial_leap[(2004, 2)].detail

    feb_29 = dict(feb_28)
    feb_29[dt.date(2004, 2, 29)] = 1.0
    full_leap = monthly_sums(daily=feb_29)
    assert full_leap[(2004, 2)] == 29.0

    # Partial month containing a missing day reports NO_COVERAGE before MISSING_INPUT.
    partial_with_missing = {
        dt.date(2001, 1, 1): ResultMissing(
            reason="MISSING_INPUT", detail="PLACEHOLDER"
        ),
        dt.date(2001, 1, 2): 1.0,
    }
    res_partial = monthly_sums(daily=partial_with_missing)
    assert isinstance(res_partial[(2001, 1)], ResultMissing)
    assert res_partial[(2001, 1)].reason == "NO_COVERAGE"

    # Full month with two missing days names both dates.
    two_gaps = {dt.date(2001, 2, day): 1.0 for day in range(1, 29)}
    two_gaps[dt.date(2001, 2, 3)] = ResultMissing(reason="MISSING_INPUT", detail="gap1")
    two_gaps[dt.date(2001, 2, 9)] = ResultMissing(reason="MISSING_INPUT", detail="gap2")
    res_two_gaps = monthly_sums(daily=two_gaps)
    assert isinstance(res_two_gaps[(2001, 2)], ResultMissing)
    assert res_two_gaps[(2001, 2)].reason == "MISSING_INPUT"
    assert (
        "2001-02-03" in res_two_gaps[(2001, 2)].detail
        and "2001-02-09" in res_two_gaps[(2001, 2)].detail
    )

    overflow_month = {dt.date(2001, 1, day): 1e308 for day in range(1, 32)}
    res_overflow_month = monthly_sums(daily=overflow_month)
    assert isinstance(res_overflow_month[(2001, 1)], ResultMissing)
    assert res_overflow_month[(2001, 1)].reason == "NOT_COMPUTABLE"

    # start_month=12 boundary (kills <= 12 -> < 12).
    ag_months = {(2001, 12): 1.0, **{(2002, m): 1.0 for m in range(1, 12)}}
    res_start_12 = annual_sums(monthly=ag_months, start_month=12)
    assert res_start_12 == {2001: 12.0}

    # Annual NO_COVERAGE precedes MISSING_INPUT; multiple MISSING_INPUT months are all named.
    mixed_year = dict(ag_months)
    del mixed_year[(2002, 5)]
    mixed_year[(2002, 6)] = ResultMissing(reason="MISSING_INPUT", detail="gap")
    res_mixed_year = annual_sums(monthly=mixed_year, start_month=12)
    assert isinstance(res_mixed_year[2001], ResultMissing)
    assert res_mixed_year[2001].reason == "NO_COVERAGE"

    two_missing_months = {(2001, m): 1.0 for m in range(1, 13)}
    two_missing_months[(2001, 2)] = ResultMissing(reason="MISSING_INPUT", detail="a")
    two_missing_months[(2001, 8)] = ResultMissing(reason="MISSING_INPUT", detail="b")
    res_two_months = annual_sums(monthly=two_missing_months, start_month=1)
    assert isinstance(res_two_months[2001], ResultMissing)
    assert res_two_months[2001].reason == "MISSING_INPUT"
    assert (
        "2001-02" in res_two_months[2001].detail
        and "2001-08" in res_two_months[2001].detail
    )

    overflow_year = {(2001, m): 1e308 for m in range(1, 13)}
    res_overflow_year = annual_sums(monthly=overflow_year, start_month=1)
    assert isinstance(res_overflow_year[2001], ResultMissing)
    assert res_overflow_year[2001].reason == "NOT_COMPUTABLE"


def test_monthly_fractions_negative_total_and_division_overflow():
    """Non-zero negative annual sum gives fractions adding to 1; division overflow is NOT_COMPUTABLE."""
    neg_monthly = {(2001, m): -1.0 for m in range(1, 13)}
    neg_fracs = monthly_fractions(monthly=neg_monthly, start_month=1)
    assert not isinstance(neg_fracs, ResultMissing)
    assert math.fsum(neg_fracs[2001].values()) == pytest.approx(1.0, abs=1e-12)

    tiny_total = {
        (2001, 1): 1e10,
        (2001, 2): -1e10,
        (2001, 3): 1e-308,
        **{(2001, m): 0.0 for m in range(4, 13)},
    }
    frac_overflow = monthly_fractions(monthly=tiny_total, start_month=1)
    assert not isinstance(frac_overflow, ResultMissing)
    m1 = frac_overflow[2001][(2001, 1)]
    assert isinstance(m1, ResultMissing) and m1.reason == "NOT_COMPUTABLE"
    assert frac_overflow[2001][(2001, 3)] == pytest.approx(1.0, abs=1e-12)


def test_yearly_ratios_empty_all_missing_and_overflow():
    """Empty annual dict, all-missing annual dict, and division overflow are handled."""
    assert yearly_ratios(annual={}) == {}

    all_missing = yearly_ratios(
        annual={
            2001: ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER"),
            2002: ResultMissing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER"),
        }
    )
    assert not isinstance(all_missing, ResultMissing)
    assert isinstance(all_missing[2001], ResultMissing)
    assert all_missing[2001].reason == "NO_COVERAGE"
    assert isinstance(all_missing[2002], ResultMissing)
    assert all_missing[2002].reason == "MISSING_INPUT"

    overflow_ratios = yearly_ratios(annual={2001: 1e308, 2002: -1e308 + 1.0})
    assert not isinstance(overflow_ratios, ResultMissing)
    assert isinstance(overflow_ratios[2001], ResultMissing)
    assert overflow_ratios[2001].reason == "NOT_COMPUTABLE"


def test_r_by_year_and_month_mixed_missing_precedence_sorting_and_overflow():
    """Mixed NO_COVERAGE + MISSING_INPUT produces MISSING_INPUT; precedence, sorting, and overflow hold."""
    gap = ResultMissing(reason="MISSING_INPUT", detail="PLACEHOLDER")
    extent = ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER")

    # Mixed reasons must yield MISSING_INPUT, never NO_COVERAGE (kills all -> any in combine_missing).
    mixed = r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions={
            2003: {(2003, 1): extent},
            2002: {(2002, 1): extent},
            2001: {(2001, 1): gap, (2001, 2): extent},
        },
        yearly_ratios={2001: extent, 2003: gap},
    )
    assert not isinstance(mixed, ResultMissing)
    assert list(mixed) == [2001, 2002, 2003]
    assert isinstance(mixed[2001][(2001, 1)], ResultMissing)
    assert mixed[2001][(2001, 1)].reason == "MISSING_INPUT"
    assert isinstance(mixed[2001][(2001, 2)], ResultMissing)
    assert mixed[2001][(2001, 2)].reason == "NO_COVERAGE"
    assert isinstance(mixed[2002][(2002, 1)], ResultMissing)
    assert mixed[2002][(2002, 1)].reason == "MISSING_INPUT"
    assert isinstance(mixed[2003][(2003, 1)], ResultMissing)
    assert mixed[2003][(2003, 1)].reason == "MISSING_INPUT"

    # Precedence checks.
    assert (
        r_by_year_and_month(
            mean_annual_r=InputMissing(reason="NOT_DECLARED"),
            mean_annual_r_unit="PLACEHOLDER_unit",
            monthly_fractions=gap,
            yearly_ratios=gap,
        ).reason
        == "MISSING_INPUT"
    )
    nan_res = r_by_year_and_month(
        mean_annual_r=math.nan,
        mean_annual_r_unit="PLACEHOLDER_unit",
        monthly_fractions=gap,
        yearly_ratios=gap,
    )
    assert isinstance(nan_res, ResultMissing) and nan_res.reason == "NOT_COMPUTABLE"
    assert "not converted" not in nan_res.detail

    unit_res = r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit="PLACEHOLDER_unit",
        monthly_fractions=gap,
        yearly_ratios=gap,
    )
    assert isinstance(unit_res, ResultMissing)
    assert unit_res.reason == REASON_UNIT_NOT_ACCEPTED

    table_res = r_by_year_and_month(
        mean_annual_r=1.0,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions=gap,
        yearly_ratios=extent,
    )
    assert isinstance(table_res, ResultMissing)
    assert table_res.reason == "MISSING_INPUT"
    assert "monthly_fractions" in table_res.detail

    overflow_r = r_by_year_and_month(
        mean_annual_r=1e308,
        mean_annual_r_unit=R_UNIT,
        monthly_fractions={2001: {(2001, 1): 1.0}},
        yearly_ratios={2001: 2.0},
    )
    assert not isinstance(overflow_r, ResultMissing)
    assert isinstance(overflow_r[2001][(2001, 1)], ResultMissing)
    assert overflow_r[2001][(2001, 1)].reason == "NOT_COMPUTABLE"


# --- control.py -------------------------------------------------------------


def test_control_precedence_non_finite_exponent_and_arithmetic_errors():
    """Missing/non-finite coefficients precede unit check; 0**-1 and overflow give NOT_COMPUTABLE."""
    bad_unit_series = _series("2001-01-01", [1.0], unit="PLACEHOLDER_unit")

    missing_first = control_monthly_erosivity(
        series=bad_unit_series,
        coefficient=InputMissing(reason="NOT_DECLARED"),
        exponent=math.nan,
    )
    assert (
        isinstance(missing_first, ResultMissing)
        and missing_first.reason == "MISSING_INPUT"
    )
    assert "coefficient" in missing_first.detail

    nan_exp = control_monthly_erosivity(
        series=bad_unit_series,
        coefficient=1.0,
        exponent=math.nan,
    )
    assert isinstance(nan_exp, ResultMissing) and nan_exp.reason == "NOT_COMPUTABLE"
    assert "exponent" in nan_exp.detail

    # Jan 2001 is dry (sum 0.0 -> 0**-1 raises ZeroDivisionError); Feb 2001 is wet (sum 56.0).
    jan_dry = [0.0] * 31
    feb_wet = [2.0] * 28
    dry_and_wet = _series("2001-01-01", jan_dry + feb_wet)
    zero_div = control_monthly_erosivity(
        series=dry_and_wet, coefficient=1.0, exponent=-1.0
    )
    assert not isinstance(zero_div, ResultMissing)
    assert isinstance(zero_div[(2001, 1)], ResultMissing)
    assert zero_div[(2001, 1)].reason == "NOT_COMPUTABLE"
    assert zero_div[(2001, 2)] == pytest.approx(1.0 / 56.0, abs=1e-12)

    huge_month = _series("2001-01-01", [1e100] * 31)
    overflow = control_monthly_erosivity(
        series=huge_month, coefficient=1.0, exponent=10.0
    )
    assert not isinstance(overflow, ResultMissing)
    assert isinstance(overflow[(2001, 1)], ResultMissing)
    assert overflow[(2001, 1)].reason == "NOT_COMPUTABLE"


def test_compare_monthly_fractions_guards_mixed_missing_sorting_and_overflow():
    """Table type guards, missing index-only month, mixed NO_COVERAGE+MISSING_INPUT, sort, overflow."""
    with pytest.raises(TypeError, match="index_fractions"):
        compare_monthly_fractions(
            index_fractions={2001: ResultMissing(reason="NO_COVERAGE")},
            control_fractions={},
        )
    with pytest.raises(TypeError, match="control_fractions"):
        compare_monthly_fractions(
            index_fractions={},
            control_fractions={True: {(2001, 1): 0.5}},
        )

    gap = ResultMissing(reason="MISSING_INPUT", detail="PLACEHOLDER")
    extent = ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER")

    report = compare_monthly_fractions(
        index_fractions={
            2002: {(2002, 2): extent},
            2001: {(2001, 3): gap, (2001, 1): extent},
        },
        control_fractions={
            2002: {},
            2001: {(2001, 2): 0.5, (2001, 3): extent, (2001, 1): gap},
        },
    )
    assert not isinstance(report, ResultMissing)
    assert list(report) == [2001, 2002]
    assert list(report[2001]) == [(2001, 1), (2001, 2), (2001, 3)]

    # Month present only in control_fractions has MISSING_INPUT index_fraction & difference.
    only_ctrl = report[2001][(2001, 2)]
    assert (
        isinstance(only_ctrl.index_fraction, ResultMissing)
        and only_ctrl.index_fraction.reason == "MISSING_INPUT"
    )
    assert only_ctrl.control_fraction == 0.5
    assert (
        isinstance(only_ctrl.difference, ResultMissing)
        and only_ctrl.difference.reason == "MISSING_INPUT"
    )

    # Mixed NO_COVERAGE + MISSING_INPUT (or absent) must yield MISSING_INPUT, never NO_COVERAGE.
    for row in (
        report[2001][(2001, 1)],
        report[2001][(2001, 3)],
        report[2002][(2002, 2)],
    ):
        assert (
            isinstance(row.difference, ResultMissing)
            and row.difference.reason == "MISSING_INPUT"
        )

    overflow = compare_monthly_fractions(
        index_fractions={2001: {(2001, 1): 1e308}},
        control_fractions={2001: {(2001, 1): -1e308}},
    )
    assert not isinstance(overflow, ResultMissing)
    diff = overflow[2001][(2001, 1)].difference
    assert isinstance(diff, ResultMissing) and diff.reason == "NOT_COMPUTABLE"
