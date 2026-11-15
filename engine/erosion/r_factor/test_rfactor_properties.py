"""Analytical property and mutant-killing tests for ``engine/erosion/r_factor/``.

Every number, unit, and series in this file is a PLACEHOLDER chosen for
analytical invariants and hand arithmetic. None is a value of any method or
source.
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
    _checks,
    annual_sums,
    climatological_monthly_fractions,
    climatological_r_by_year_and_month,
    compare_monthly_fractions,
    control_monthly_erosivity,
    monthly_fractions,
    r_factor_parts,
    yearly_ratios,
)

TOLERANCE = 1e-12
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


def _days_between(start: str, end: str) -> int:
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1


# --- climatological_monthly_fractions: simplex & positive scale invariance ---


@pytest.mark.parametrize(
    "base",
    [
        {m: float(m) for m in range(1, 13)},
        {m: (100.0 if m == 7 else 0.0) for m in range(1, 13)},
        {m: (0.0 if m % 2 == 0 else float(m * m)) for m in range(1, 13)},
        {m: 5.0 for m in range(1, 13)},
    ],
    ids=["ramp", "single-month-spike", "alternating-zeros", "uniform"],
)
def test_climatological_monthly_fractions_simplex_and_positive_scale_invariance(base):
    """Fractions lie in the unit simplex (f in [0, 1], sum == 1) and are invariant under k * x (k > 0)."""
    fractions = climatological_monthly_fractions(monthly_erosivity=base)
    assert not isinstance(fractions, ResultMissing)
    assert set(fractions) == set(range(1, 13))
    for month, frac in fractions.items():
        assert isinstance(frac, float)
        assert 0.0 <= frac <= 1.0
        assert (frac == 0.0) == (base[month] == 0.0)
    assert math.fsum(fractions.values()) == pytest.approx(1.0, abs=TOLERANCE)

    # Positive scale invariance across orders of magnitude.
    for scale in (1e-6, 0.25, 3.7, 1e6):
        scaled = {m: scale * v for m, v in base.items()}
        scaled_fractions = climatological_monthly_fractions(monthly_erosivity=scaled)
        assert not isinstance(scaled_fractions, ResultMissing)
        for month in range(1, 13):
            assert scaled_fractions[month] == pytest.approx(
                fractions[month], abs=TOLERANCE
            )

    # Key insertion order permutation invariance.
    reversed_order = {m: base[m] for m in range(12, 0, -1)}
    permuted = climatological_monthly_fractions(monthly_erosivity=reversed_order)
    assert not isinstance(permuted, ResultMissing)
    for month in range(1, 13):
        assert permuted[month] == pytest.approx(fractions[month], abs=TOLERANCE)


def test_climatological_monthly_fractions_boundaries_and_r_linearity():
    """All-zero -> NOT_COMPUTABLE; negative -> NOT_COMPUTABLE; -0.0 valid; R scales linearly with level."""
    zeros = {m: 0.0 for m in range(1, 13)}
    zero_res = climatological_monthly_fractions(monthly_erosivity=zeros)
    assert isinstance(zero_res, ResultMissing) and zero_res.reason == "NOT_COMPUTABLE"

    # Negative zero is non-negative and yields 0.0 fraction when total > 0.
    neg_zero = {m: (1.0 if m == 12 else -0.0) for m in range(1, 13)}
    nz_res = climatological_monthly_fractions(monthly_erosivity=neg_zero)
    assert not isinstance(nz_res, ResultMissing)
    assert nz_res[12] == 1.0
    assert all(nz_res[m] == 0.0 for m in range(1, 12))

    # Even a tiny negative month with large positive total is refused without clipping.
    tiny_neg = {m: (-1e-12 if m == 4 else 10.0) for m in range(1, 13)}
    neg_res = climatological_monthly_fractions(monthly_erosivity=tiny_neg)
    assert isinstance(neg_res, ResultMissing) and neg_res.reason == "NOT_COMPUTABLE"
    assert "month 04" in neg_res.detail

    # Linear scaling of climatological_r_by_year_and_month with mean_annual_r.
    base = {m: float(m) for m in range(1, 13)}
    fracs = climatological_monthly_fractions(monthly_erosivity=base)
    assert not isinstance(fracs, ResultMissing)
    r1 = climatological_r_by_year_and_month(
        mean_annual_r=100.0,
        mean_annual_r_unit=R_UNIT,
        fractions=fracs,
        ag_years=[2001, 2002],
        start_month=5,
    )
    r2 = climatological_r_by_year_and_month(
        mean_annual_r=350.0,
        mean_annual_r_unit=R_UNIT,
        fractions=fracs,
        ag_years=[2001, 2002],
        start_month=5,
    )
    assert not isinstance(r1, ResultMissing) and not isinstance(r2, ResultMissing)
    for ag_year in (2001, 2002):
        assert math.fsum(r1[ag_year].values()) == pytest.approx(100.0, abs=TOLERANCE)
        assert math.fsum(r2[ag_year].values()) == pytest.approx(350.0, abs=TOLERANCE)
        for ym in r1[ag_year]:
            assert r2[ag_year][ym] == pytest.approx(3.5 * r1[ag_year][ym], abs=TOLERANCE)


def test_erosivity_fractions_and_ratios_positive_scale_invariance():
    """monthly_fractions and yearly_ratios are homogeneous of degree 0 under positive scaling."""
    monthly = {
        (year, month): float(year - 2000) * float(month)
        for year in (2001, 2002, 2003)
        for month in range(1, 13)
    }
    base_fracs = monthly_fractions(monthly=monthly, start_month=4)
    base_annual = annual_sums(monthly=monthly, start_month=4)
    assert not isinstance(base_annual, ResultMissing)
    base_ratios = yearly_ratios(annual=base_annual)
    assert not isinstance(base_fracs, ResultMissing)
    assert not isinstance(base_ratios, ResultMissing)

    for scale in (0.01, 7.5, 1e4):
        scaled_monthly = {ym: scale * val for ym, val in monthly.items()}
        scaled_fracs = monthly_fractions(monthly=scaled_monthly, start_month=4)
        scaled_annual = annual_sums(monthly=scaled_monthly, start_month=4)
        assert not isinstance(scaled_annual, ResultMissing)
        scaled_ratios = yearly_ratios(annual=scaled_annual)
        assert not isinstance(scaled_fracs, ResultMissing)
        assert not isinstance(scaled_ratios, ResultMissing)
        for ag_year in base_fracs:
            if isinstance(base_ratios[ag_year], float):
                assert scaled_ratios[ag_year] == pytest.approx(
                    base_ratios[ag_year], abs=TOLERANCE
                )
            for ym in base_fracs[ag_year]:
                if isinstance(base_fracs[ag_year][ym], float):
                    assert scaled_fracs[ag_year][ym] == pytest.approx(
                        base_fracs[ag_year][ym], abs=TOLERANCE
                    )


# --- ag_year_of & months_of_ag_year: 12-month partition & bijection ----------


@pytest.mark.parametrize("start_month", range(1, 13))
def test_ag_year_partition_and_bijection_across_all_start_months(start_month):
    """months_of_ag_year and ag_year_of form an exact 12-month partition and bijection for 1..12."""
    # 1. Forward -> inverse on every ag_year and month.
    all_assigned: list[tuple[int, int]] = []
    for ag_year in (1999, 2000, 2001, 2002):
        months = _checks.months_of_ag_year(ag_year, start_month)
        assert len(months) == 12
        assert months[0] == (ag_year, start_month)
        assert all(_checks.is_year_month(ym) for ym in months)
        # Calendar months {1..12} appear once each, strictly consecutive month-by-month.
        assert {m for _, m in months} == set(range(1, 13))
        serials = [y * 12 + (m - 1) for y, m in months]
        assert serials == list(range(serials[0], serials[0] + 12))

        for ym in months:
            assert _checks.ag_year_of(ym, start_month) == ag_year
        all_assigned.extend(months)

    # No two distinct agricultural years overlap.
    assert len(all_assigned) == len(set(all_assigned))

    # 2. Reverse -> forward on every calendar (year, month) across 2000..2002.
    calendar_range = [(y, m) for y in (2000, 2001, 2002) for m in range(1, 13)]
    grouped: dict[int, list[tuple[int, int]]] = {}
    for ym in calendar_range:
        ag = _checks.ag_year_of(ym, start_month)
        assert ym in _checks.months_of_ag_year(ag, start_month)
        grouped.setdefault(ag, []).append(ym)

    # Boundary check at start_month - 1 vs start_month (kills >= -> > and year - 1 -> year).
    if start_month > 1:
        assert _checks.ag_year_of((2001, start_month - 1), start_month) == 2000
    assert _checks.ag_year_of((2001, start_month), start_month) == 2001

    # Exact partition of interior agricultural years.
    interior_years = [2000, 2001, 2002] if start_month == 1 else [2000, 2001]
    for ag in interior_years:
        assert grouped[ag] == _checks.months_of_ag_year(ag, start_month)

    # 3. Verify annual_sums produces exact numeric sums for interior years and NO_COVERAGE on cut years.
    unit_monthly = {ym: 1.0 for ym in calendar_range}
    sums = annual_sums(monthly=unit_monthly, start_month=start_month)
    assert not isinstance(sums, ResultMissing)
    assert set(sums) == set(grouped)
    for ag in interior_years:
        assert sums[ag] == 12.0
    for ag in set(grouped) - set(interior_years):
        assert isinstance(sums[ag], ResultMissing) and sums[ag].reason == "NO_COVERAGE"


# --- Missing propagation across r_factor ------------------------------------


@pytest.mark.parametrize("shape", [InputMissing, ResultMissing], ids=["input", "result"])
def test_climatology_missing_propagation_and_multi_missing_names(shape):
    """Missing months name every missing month and precede negative/non-finite checks."""
    gap_a = shape(reason="NOT_AVAILABLE", detail="PLACEHOLDER a")
    gap_b = shape(reason="NO_COVERAGE", detail="PLACEHOLDER b")
    months = {m: float(m) for m in range(1, 13)}
    months[2] = gap_a
    months[9] = gap_b
    months[5] = -10.0  # MISSING_INPUT must precede negative check (C3.3)
    res = climatological_monthly_fractions(monthly_erosivity=months)
    assert isinstance(res, ResultMissing) and res.reason == "MISSING_INPUT"
    assert "month 02" in res.detail and "month 09" in res.detail
    assert "month 05" not in res.detail

    # Missing fraction cell affects only its calendar month across every ag_year.
    fracs = climatological_monthly_fractions(
        monthly_erosivity={m: float(m) for m in range(1, 13)}
    )
    assert not isinstance(fracs, ResultMissing)
    partial_fracs = dict(fracs)
    partial_fracs[6] = ResultMissing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER")
    table = climatological_r_by_year_and_month(
        mean_annual_r=78.0,
        mean_annual_r_unit=R_UNIT,
        fractions=partial_fracs,
        ag_years=[2001, 2002],
        start_month=3,
    )
    assert not isinstance(table, ResultMissing)
    for ag_year in (2001, 2002):
        # Month 6 of each ag_year is in calendar year ag_year (since start_month=3 <= 6).
        bad_cell = table[ag_year][(ag_year, 6)]
        assert (
            isinstance(bad_cell, ResultMissing) and bad_cell.reason == "MISSING_INPUT"
        )
        assert "month 06" in bad_cell.detail
        for ym, val in table[ag_year].items():
            if ym[1] != 6:
                assert isinstance(val, float)


def test_r_factor_missing_propagation_end_to_end_and_combine_missing_rules():
    """End-to-end Missing propagation from daily gaps, partial extent, and combine_missing lattice."""
    # Three calendar years 2001..2003:
    # - 2001 is complete and wet
    # - 2002 has one missing day on 2002-05-15 (rest wet)
    # - 2003 is complete and wet, except truncated on 2003-12-20 -> Dec 2003 is NO_COVERAGE
    start = "2001-01-01"
    end = "2003-12-20"
    total_days = _days_between(start, end)
    values: list[float | None] = [5.0 + (i % 4) for i in range(total_days)]
    missing_offset = _days_between(start, "2002-05-15") - 1
    values[missing_offset] = None

    series = _series(start, values)
    parts = r_factor_parts(
        series=series,
        exponent=2.0,
        threshold=1.0,
        threshold_unit=PRECIPITATION_UNIT,
        start_month=1,
        mean_annual_r=500.0,
        mean_annual_r_unit=R_UNIT,
    )

    assert not isinstance(parts.daily_index, ResultMissing)
    assert not isinstance(parts.monthly_index_sums, ResultMissing)
    assert not isinstance(parts.annual_index_sums, ResultMissing)
    assert not isinstance(parts.monthly_fractions, ResultMissing)
    assert not isinstance(parts.yearly_ratios, ResultMissing)
    assert not isinstance(parts.r_by_year_and_month, ResultMissing)

    # Day level: only 2002-05-15 is MISSING_INPUT.
    bad_day = parts.daily_index[dt.date(2002, 5, 15)]
    assert isinstance(bad_day, ResultMissing) and bad_day.reason == "MISSING_INPUT"

    # Month level: 2002-05 is MISSING_INPUT; 2003-12 is NO_COVERAGE; all others float.
    assert (
        isinstance(parts.monthly_index_sums[(2002, 5)], ResultMissing)
        and parts.monthly_index_sums[(2002, 5)].reason == "MISSING_INPUT"
    )
    assert (
        isinstance(parts.monthly_index_sums[(2003, 12)], ResultMissing)
        and parts.monthly_index_sums[(2003, 12)].reason == "NO_COVERAGE"
    )

    # Annual level: 2001 float, 2002 MISSING_INPUT, 2003 NO_COVERAGE.
    assert isinstance(parts.annual_index_sums[2001], float)
    assert (
        isinstance(parts.annual_index_sums[2002], ResultMissing)
        and parts.annual_index_sums[2002].reason == "MISSING_INPUT"
    )
    assert (
        isinstance(parts.annual_index_sums[2003], ResultMissing)
        and parts.annual_index_sums[2003].reason == "NO_COVERAGE"
    )

    # Yearly ratios: only 2001 is defined -> ratio[2001] == 1.0; 2002 MISSING_INPUT; 2003 NO_COVERAGE.
    assert parts.yearly_ratios[2001] == 1.0
    assert (
        isinstance(parts.yearly_ratios[2002], ResultMissing)
        and parts.yearly_ratios[2002].reason == "MISSING_INPUT"
    )
    assert (
        isinstance(parts.yearly_ratios[2003], ResultMissing)
        and parts.yearly_ratios[2003].reason == "NO_COVERAGE"
    )

    # Monthly fractions and final R propagate exact reasons per year.
    assert all(
        isinstance(v, float) for v in parts.r_by_year_and_month[2001].values()
    )
    assert math.fsum(parts.r_by_year_and_month[2001].values()) == pytest.approx(
        500.0, abs=TOLERANCE
    )
    assert all(
        isinstance(v, ResultMissing) and v.reason == "MISSING_INPUT"
        for v in parts.r_by_year_and_month[2002].values()
    )
    assert all(
        isinstance(v, ResultMissing) and v.reason == "NO_COVERAGE"
        for v in parts.r_by_year_and_month[2003].values()
    )

    # Control regression and comparison preserve NO_COVERAGE vs MISSING_INPUT distinction.
    ctrl = control_monthly_erosivity(series=series, coefficient=2.0, exponent=1.0)
    assert not isinstance(ctrl, ResultMissing)
    assert (
        isinstance(ctrl[(2002, 5)], ResultMissing)
        and ctrl[(2002, 5)].reason == "MISSING_INPUT"
    )
    assert (
        isinstance(ctrl[(2003, 12)], ResultMissing)
        and ctrl[(2003, 12)].reason == "NO_COVERAGE"
    )
    ctrl_fracs = monthly_fractions(monthly=ctrl, start_month=1)
    report = compare_monthly_fractions(
        index_fractions=parts.monthly_fractions, control_fractions=ctrl_fracs
    )
    assert not isinstance(report, ResultMissing)
    assert all(
        isinstance(row.difference, ResultMissing)
        and row.difference.reason == "MISSING_INPUT"
        for row in report[2002].values()
    )
    assert all(
        isinstance(row.difference, ResultMissing)
        and row.difference.reason == "NO_COVERAGE"
        for row in report[2003].values()
    )


def test_r_factor_parts_missing_mean_annual_r_only_withholds_r_table():
    """Missing mean_annual_r leaves daily index, sums, fractions, and ratios intact."""
    series = _series("2001-01-01", [4.0] * 365)
    parts = r_factor_parts(
        series=series,
        exponent=2.0,
        threshold=1.0,
        threshold_unit=PRECIPITATION_UNIT,
        start_month=1,
        mean_annual_r=InputMissing(reason="NOT_DECLARED", detail="PLACEHOLDER"),
        mean_annual_r_unit=R_UNIT,
    )
    assert not isinstance(parts.daily_index, ResultMissing)
    assert not isinstance(parts.monthly_index_sums, ResultMissing)
    assert not isinstance(parts.annual_index_sums, ResultMissing)
    assert not isinstance(parts.monthly_fractions, ResultMissing)
    assert parts.yearly_ratios == {2001: 1.0}
    assert (
        isinstance(parts.r_by_year_and_month, ResultMissing)
        and parts.r_by_year_and_month.reason == "MISSING_INPUT"
    )
    assert "mean_annual_r" in parts.r_by_year_and_month.detail
