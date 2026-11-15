"""Mutant-resistance and edge tests for ``validation/h10_runoff.py``.

PLACEHOLDER TEST DATA ONLY. Every measured series, modelled series, daily
runoff series, PBIAS bound, and event cap in this file is a synthetic
PLACEHOLDER value created solely to exercise boundary, tie, error-handling,
and G1 immutability behaviour. None of the numbers here come from Grahmann
et al. (2022) Table 5 or from decision D230's real thresholds.
"""

from __future__ import annotations

import copy
import datetime as dt
from dataclasses import FrozenInstanceError, is_dataclass
from fractions import Fraction

import pytest

from contracts.results.models import Missing
from validation import h10_runoff
from validation.h10_runoff import (
    Condition,
    H10Result,
    LargeEvents,
    YearError,
    YearOrder,
    compare_h10_runoff,
)

# Synthetic PLACEHOLDER parameters (never real D230 bounds or Table 5 data).
PLACEHOLDER_BOUND_PERCENT = 10.0
PLACEHOLDER_BOUND_ALT_PERCENT = 12.5
PLACEHOLDER_EVENT_CAP_MM = 50.0
PLACEHOLDER_MEASURED = {2017: 120.0, 2018: 360.0, 2019: 240.0}  # sum 720.0


def _compare(
    measured,
    modelled,
    *,
    bound: float = PLACEHOLDER_BOUND_PERCENT,
    cap: float = PLACEHOLDER_EVENT_CAP_MM,
    daily=None,
) -> H10Result:
    return compare_h10_runoff(
        measured,
        modelled,
        pbias_bound_percent=bound,
        event_cap_mm=cap,
        modelled_daily=daily,
    )


# === 1. Exact Fraction boundary abs(PBIAS) == bound vs 1e-12 epsilon trap ===


@pytest.mark.parametrize(
    ("measured", "modelled", "bound", "expected_pbias"),
    [
        # Sum 720 -> +/-10% is 648 / 792; exact integer-valued floats.
        (
            PLACEHOLDER_MEASURED,
            {2017: 108.0, 2018: 324.0, 2019: 216.0},
            PLACEHOLDER_BOUND_PERCENT,
            10.0,
        ),
        (
            PLACEHOLDER_MEASURED,
            {2017: 132.0, 2018: 396.0, 2019: 264.0},
            PLACEHOLDER_BOUND_PERCENT,
            -10.0,
        ),
        # Sum 400 with non-integer binary-exact bound 12.5% -> 350 / 450.
        (
            {2017: 80.0, 2018: 200.0, 2019: 120.0},
            {2017: 70.0, 2018: 175.0, 2019: 105.0},
            PLACEHOLDER_BOUND_ALT_PERCENT,
            12.5,
        ),
        (
            {2017: 80.0, 2018: 200.0, 2019: 120.0},
            {2017: 90.0, 2018: 225.0, 2019: 135.0},
            PLACEHOLDER_BOUND_ALT_PERCENT,
            -12.5,
        ),
    ],
)
def test_exact_pbias_at_positive_and_negative_bound_passes(
    measured, modelled, bound, expected_pbias
):
    # Kills `abs(exact_pbias) <= bound` -> `< bound` and dropping `abs(...)`.
    result = _compare(measured, modelled, bound=bound)
    assert result.pbias_percent == expected_pbias
    assert result.pbias_condition == Condition("pass", None)
    assert result.order_condition == Condition("pass", None)
    assert result.h10 == Condition("pass", None)


def test_exact_fraction_epsilon_trap_1e_minus_12_where_naive_float_sum_passes():
    # Trap A (positive side): 1e-12 in 2017 is swallowed when summing floats
    # with 40000.0 + 60000.0 in IEEE-754 float64, so naive float arithmetic
    # computes PBIAS == 10.0 (pass), whereas exact Fraction exceeds 10 (fail).
    measured_pos = {2017: 1e-12, 2018: 40000.0, 2019: 60000.0}
    modelled_pos = {2017: 0.0, 2018: 30000.0, 2019: 60000.0}
    float_tm = sum(measured_pos.values())
    float_ts = sum(modelled_pos.values())
    assert 100.0 * (float_tm - float_ts) / float_tm <= PLACEHOLDER_BOUND_PERCENT

    res_pos = _compare(measured_pos, modelled_pos)
    assert res_pos.order_condition.verdict == "pass"
    assert res_pos.pbias_condition.verdict == "fail"
    assert res_pos.h10.verdict == "fail"
    assert "outside plus or minus" in res_pos.pbias_condition.reason

    # Trap B (negative side): 1e-12 in modelled 2017 is swallowed by float sum
    # 50000.0 + 60110.0, so naive float computes PBIAS == -10.0 (pass), while
    # exact Fraction is strictly below -10 (fail).
    measured_neg = {2017: 100.0, 2018: 40000.0, 2019: 60000.0}
    modelled_neg = {2017: 1e-12, 2018: 50000.0, 2019: 60110.0}
    float_tm_n = sum(measured_neg.values())
    float_ts_n = sum(modelled_neg.values())
    assert abs(100.0 * (float_tm_n - float_ts_n) / float_tm_n) <= PLACEHOLDER_BOUND_PERCENT

    res_neg = _compare(measured_neg, modelled_neg)
    assert res_neg.order_condition.verdict == "pass"
    assert res_neg.pbias_condition.verdict == "fail"
    assert res_neg.h10.verdict == "fail"

    # Trap C (returned float pbias_percent rounds to 10.0, yet Fraction > 10):
    # Kills comparing `abs(pbias) <= float(bound)` after float conversion.
    measured_ulp = {2017: 1e-13, 2018: 40000.0, 2019: 60000.0}
    res_ulp = _compare(measured_ulp, modelled_pos)
    assert res_ulp.pbias_percent == PLACEHOLDER_BOUND_PERCENT
    assert res_ulp.pbias_condition.verdict == "fail"
    assert res_ulp.h10.verdict == "fail"


def test_exact_pbias_1e_minus_12_above_and_below_bound_on_both_signs():
    # Exact measured sum 10.0; 10% bound -> exact edges at modelled sums 9.0 and 11.0.
    measured = {2017: 2.0, 2018: 5.0, 2019: 3.0}
    eps = 1e-12

    just_inside_pos = _compare(measured, {2017: 1.5 + eps, 2018: 4.5, 2019: 3.0})
    just_outside_pos = _compare(measured, {2017: 1.5 - eps, 2018: 4.5, 2019: 3.0})
    assert just_inside_pos.pbias_condition.verdict == "pass"
    assert just_outside_pos.pbias_condition.verdict == "fail"

    just_inside_neg = _compare(measured, {2017: 2.5 - eps, 2018: 5.5, 2019: 3.0})
    just_outside_neg = _compare(measured, {2017: 2.5 + eps, 2018: 5.5, 2019: 3.0})
    assert just_inside_neg.pbias_condition.verdict == "pass"
    assert just_outside_neg.pbias_condition.verdict == "fail"


def test_exact_pbias_non_dyadic_decimal_matches_fraction_arithmetic():
    measured = {2017: 0.1, 2018: 0.2, 2019: 0.4}
    modelled = {2017: 0.09, 2018: 0.18, 2019: 0.36}
    result = _compare(measured, modelled, bound=PLACEHOLDER_BOUND_PERCENT)
    total_m = sum(map(Fraction, measured.values()))
    total_s = sum(map(Fraction, modelled.values()))
    exact = h10_runoff.PERCENT * (total_m - total_s) / total_m
    expected_verdict = "pass" if abs(exact) <= Fraction(PLACEHOLDER_BOUND_PERCENT) else "fail"
    assert result.pbias_percent == float(exact)
    assert result.pbias_condition.verdict == expected_verdict


# === 2. Tank-cap strict inequality (== cap false, > cap true) ================


def test_tank_cap_strict_inequality_at_cap_is_false_and_epsilon_above_is_true():
    modelled_ok = {2017: 115.0, 2018: 350.0, 2019: 235.0}
    day_at_cap = dt.date(2018, 6, 1)
    day_below = dt.date(2018, 6, 2)
    day_just_above = dt.date(2018, 6, 3)

    # Exactly at cap and below cap -> flagged is False (kills `>` -> `>=`).
    at_cap = _compare(
        PLACEHOLDER_MEASURED,
        modelled_ok,
        daily={day_at_cap: PLACEHOLDER_EVENT_CAP_MM, day_below: PLACEHOLDER_EVENT_CAP_MM - 1e-12},
    )
    assert at_cap.large_events == LargeEvents(
        flagged=False, days_above_cap=(), days_without_value=(), reason=None
    )
    assert at_cap.h10 == Condition("pass", None)

    # Strictly above cap by 1e-12 -> flagged is True.
    above_val = PLACEHOLDER_EVENT_CAP_MM + 1e-12
    above_cap = _compare(
        PLACEHOLDER_MEASURED,
        modelled_ok,
        daily={day_at_cap: PLACEHOLDER_EVENT_CAP_MM, day_just_above: above_val},
    )
    assert above_cap.large_events.flagged is True
    assert above_cap.large_events.days_above_cap == ((day_just_above, above_val),)
    assert above_cap.large_events.days_without_value == ()
    assert above_cap.large_events.reason is None
    assert above_cap.h10 == at_cap.h10


def test_tank_cap_strict_inequality_with_non_dyadic_cap_and_missing_days():
    # Binary float 0.1 + 0.2 is strictly greater than 0.3 as an exact Fraction.
    cap = 0.3
    modelled_ok = {2017: 115.0, 2018: 350.0, 2019: 235.0}
    d1 = dt.date(2019, 4, 1)
    d2 = dt.date(2019, 4, 2)
    d3 = dt.date(2019, 4, 3)

    at_exact = _compare(PLACEHOLDER_MEASURED, modelled_ok, cap=cap, daily={d1: 0.3})
    assert at_exact.large_events.flagged is False

    # Missing day with no day above cap (only == cap) -> flagged is None.
    missing = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER gauge gap")
    at_cap_with_missing = _compare(
        PLACEHOLDER_MEASURED,
        modelled_ok,
        cap=cap,
        daily={d2: missing, d1: 0.3},
    )
    assert at_cap_with_missing.large_events.flagged is None
    assert at_cap_with_missing.large_events.days_above_cap == ()
    assert at_cap_with_missing.large_events.days_without_value == (
        (d2, "missing with the reason MISSING_INPUT: PLACEHOLDER gauge gap"),
    )
    assert "cannot be ruled out" in at_cap_with_missing.large_events.reason
    assert str(cap) in at_cap_with_missing.large_events.reason

    # Day > cap alongside Missing and +inf -> flagged is True AND days_without_value preserved sorted.
    above_with_missing = _compare(
        PLACEHOLDER_MEASURED,
        modelled_ok,
        cap=cap,
        daily={d3: float("inf"), d2: missing, d1: 0.1 + 0.2},
    )
    assert above_with_missing.large_events.flagged is True
    assert above_with_missing.large_events.days_above_cap == ((d1, 0.1 + 0.2),)
    assert above_with_missing.large_events.days_without_value == (
        (d2, "missing with the reason MISSING_INPUT: PLACEHOLDER gauge gap"),
        (d3, "not a finite number"),
    )
    assert above_with_missing.large_events.reason is None
    # Large event flag never alters H10 pass or fail verdicts.
    assert above_with_missing.h10 == Condition("pass", None)
    failed = _compare(
        PLACEHOLDER_MEASURED,
        {2017: 50.0, 2018: 200.0, 2019: 100.0},
        cap=cap,
        daily={d1: 0.1 + 0.2},
    )
    assert failed.large_events.flagged is True
    assert failed.h10.verdict == "fail"


# === 3. Year-order ties and ordering precision ================================


def test_year_order_ties_both_sides_all_three_and_partial_ties():
    # Both sides tie the exact same years (2017 == 2019), PBIAS == 0:
    # must NOT pass; both sides give no order and orders_match is None.
    tied_both_m = {2017: 200.0, 2018: 320.0, 2019: 200.0}
    tied_both_s = {2017: 200.0, 2018: 320.0, 2019: 200.0}
    res_both = _compare(tied_both_m, tied_both_s)
    assert res_both.pbias_condition == Condition("pass", None)
    assert res_both.measured_order.order is None
    assert res_both.modelled_order.order is None
    assert res_both.orders_match is None
    assert res_both.order_condition.verdict is None
    assert "measured values of 2017 and 2019" in res_both.order_condition.reason
    assert "modelled values of 2017 and 2019" in res_both.order_condition.reason
    assert res_both.h10.verdict is None

    # All three years tied in modelled: all 3 pairs listed in order.
    res_three = _compare(PLACEHOLDER_MEASURED, {2017: 240.0, 2018: 240.0, 2019: 240.0})
    assert res_three.measured_order.order == (2018, 2019, 2017)
    assert res_three.modelled_order.order is None
    assert "2017 and 2018; 2017 and 2019; 2018 and 2019" in res_three.modelled_order.reason
    assert res_three.h10.verdict is None

    # Measured ties 2017 == 2018 while modelled has no tie -> modelled_order still reported.
    res_measured_only = _compare(
        {2017: 200.0, 2018: 200.0, 2019: 320.0},
        {2017: 190.0, 2018: 210.0, 2019: 320.0},
    )
    assert res_measured_only.measured_order.order is None
    assert res_measured_only.modelled_order.order == (2019, 2018, 2017)
    assert res_measured_only.order_condition.verdict is None
    assert res_measured_only.h10.verdict is None


def test_year_order_fraction_distinguishes_1e_minus_12_and_sorts_highest_first():
    # 1e-12 difference is NOT a tie and orders strictly highest-first.
    measured = {2017: 200.0, 2018: 200.0 + 2e-12, 2019: 200.0 + 1e-12}
    modelled = {2017: 200.0, 2018: 200.0 + 2e-12, 2019: 200.0 + 1e-12}
    res_pass = _compare(measured, modelled)
    assert res_pass.measured_order.order == (2018, 2019, 2017)
    assert res_pass.modelled_order.order == (2018, 2019, 2017)
    assert res_pass.orders_match is True
    assert res_pass.h10.verdict == "pass"

    # Reversed modelled order fails condition (2) even when PBIAS == 0.
    res_rev = _compare(measured, {2017: 200.0 + 2e-12, 2018: 200.0, 2019: 200.0 + 1e-12})
    assert res_rev.modelled_order.order == (2017, 2019, 2018)
    assert res_rev.orders_match is False
    assert res_rev.order_condition.verdict == "fail"
    assert res_rev.h10.verdict == "fail"


# === 4. Zero and negative measured sums ======================================


def test_zero_and_negative_measured_sums_with_nonzero_values():
    # Non-zero cancelling measured values whose sum is exactly 0.
    measured_zero = {2017: -40.0, 2018: 120.0, 2019: -80.0}
    res_zero_same_order = _compare(measured_zero, {2017: -30.0, 2018: 110.0, 2019: -70.0})
    assert res_zero_same_order.pbias_percent is None
    assert "not above zero" in res_zero_same_order.pbias_reason
    assert res_zero_same_order.pbias_condition.verdict is None
    assert res_zero_same_order.measured_order.order == (2018, 2017, 2019)
    assert res_zero_same_order.order_condition.verdict == "pass"
    assert res_zero_same_order.h10.verdict is None
    assert "condition (1)" in res_zero_same_order.h10.reason
    # Relative errors are still computed for all non-zero years.
    assert {e.year: e.relative_error_percent for e in res_zero_same_order.year_errors} == pytest.approx(
        {
            2017: 100 * (-40.0 - (-30.0)) / -40.0,
            2018: 100 * (120.0 - 110.0) / 120.0,
            2019: 100 * (-80.0 - (-70.0)) / -80.0,
        }
    )

    # Order failure still makes H10 fail even when PBIAS has no verdict (sum <= 0).
    res_zero_bad_order = _compare(measured_zero, {2017: -80.0, 2018: 120.0, 2019: -40.0})
    assert res_zero_bad_order.pbias_condition.verdict is None
    assert res_zero_bad_order.order_condition.verdict == "fail"
    assert res_zero_bad_order.h10.verdict == "fail"
    assert "condition (2)" in res_zero_bad_order.h10.reason

    # Negative measured sum (-60.0) with mismatched order vs matched order.
    measured_neg = {2017: -30.0, 2018: 20.0, 2019: -50.0}
    res_neg_match = _compare(measured_neg, dict(measured_neg))
    assert res_neg_match.pbias_percent is None
    assert res_neg_match.pbias_condition.verdict is None
    assert res_neg_match.order_condition.verdict == "pass"
    assert res_neg_match.h10.verdict is None

    res_neg_mismatch = _compare(measured_neg, {2017: -50.0, 2018: 20.0, 2019: -30.0})
    assert res_neg_mismatch.pbias_condition.verdict is None
    assert res_neg_mismatch.order_condition.verdict == "fail"
    assert res_neg_mismatch.h10.verdict == "fail"

    # Tiny positive cancelling sum (1e-12 > 0) DOES compute PBIAS.
    measured_tiny_pos = {2017: -50.0, 2018: 50.0, 2019: 1e-12}
    res_tiny_pos = _compare(measured_tiny_pos, dict(measured_tiny_pos))
    assert res_tiny_pos.pbias_percent == 0.0
    assert res_tiny_pos.pbias_condition.verdict == "pass"
    assert res_tiny_pos.h10.verdict == "pass"


# === 5. Missing year mismatches and non-numeric values =======================


def test_missing_and_extra_year_mismatches_and_combined_problems():
    measured = {2017: 120.0, 2018: 360.0, 2019: 240.0}
    modelled = {2017: 108.0, 2018: 324.0, 2020: 15.0}
    daily = {dt.date(2018, 5, 1): 60.0}
    result = _compare(measured, modelled, daily=daily)

    assert result.years == (2017, 2018, 2019)
    assert result.pbias_percent is None
    assert result.orders_match is None
    assert result.pbias_condition.verdict is None
    assert result.order_condition.verdict is None
    assert result.h10.verdict is None
    assert "the modelled values have no year 2019" in result.h10.reason
    assert "the modelled values hold the year 2020" in result.h10.reason

    # year_errors covers the union of years, keeping valid relative errors.
    by_year = {e.year: e for e in result.year_errors}
    assert tuple(by_year) == (2017, 2018, 2019, 2020)
    assert by_year[2017].relative_error_percent == pytest.approx(10.0)
    assert by_year[2018].relative_error_percent == pytest.approx(10.0)
    assert by_year[2019] == YearError(2019, 240.0, None, None, "the modelled value is not given")
    assert by_year[2020] == YearError(2020, None, 15.0, None, "the measured value is not given")

    # Daily event check still runs despite yearly mismatch.
    assert result.large_events.flagged is True
    assert result.large_events.days_above_cap == ((dt.date(2018, 5, 1), 60.0),)

    # Empty measured with non-empty modelled reports both problems.
    empty_m = _compare({}, {2017: 10.0})
    assert empty_m.years == ()
    assert empty_m.h10.verdict is None
    assert "no measured year is given" in empty_m.h10.reason
    assert "hold the year 2017" in empty_m.h10.reason

    # Both sides non-numeric on the same year combines both reasons.
    m_bad = {
        2017: 120.0,
        2018: Missing(reason="MISSING_INPUT", detail="PLACEHOLDER no gauge"),
        2019: 240.0,
    }
    s_bad = {2017: 108.0, 2018: float("-inf"), 2019: "216.0"}  # type: ignore[dict-item]
    res_bad = _compare(m_bad, s_bad)
    assert res_bad.h10.verdict is None
    err_2018 = {e.year: e for e in res_bad.year_errors}[2018]
    assert "measured value is missing with the reason MISSING_INPUT: PLACEHOLDER no gauge" in err_2018.reason
    assert "modelled value is not a finite number" in err_2018.reason
    err_2019 = {e.year: e for e in res_bad.year_errors}[2019]
    assert err_2019.relative_error_percent is None
    assert "not a finite number" in err_2019.reason


# === 6. G1 immutability (pure function, frozen results, no input mutation) ===


@pytest.mark.parametrize(
    ("measured", "modelled", "daily"),
    [
        (
            PLACEHOLDER_MEASURED,
            {2017: 115.0, 2018: 350.0, 2019: 235.0},
            {dt.date(2018, 2, 1): 55.0, dt.date(2018, 2, 2): 10.0},
        ),
        (
            PLACEHOLDER_MEASURED,
            {2017: 10.0, 2018: 20.0},
            {dt.date(2019, 3, 1): Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER")},
        ),
    ],
)
def test_g1_immutability_inputs_unchanged_outputs_frozen_and_deterministic(
    measured, modelled, daily
):
    measured_copy = dict(measured)
    modelled_copy = dict(modelled)
    daily_copy = dict(daily)
    snapshot = copy.deepcopy((measured_copy, modelled_copy, daily_copy))

    first = _compare(measured_copy, modelled_copy, daily=daily_copy)
    second = _compare(measured_copy, modelled_copy, daily=daily_copy)

    # Inputs are never mutated and repeated calls return identical results (G1).
    assert (measured_copy, modelled_copy, daily_copy) == snapshot
    assert first == second

    # Mutating caller dicts after the call does not affect the returned result.
    measured_copy[2017] = -999.0
    modelled_copy[2025] = 999.0
    daily_copy[dt.date(2025, 1, 1)] = 999.0
    assert first == second

    # Returned dataclasses and sequences are immutable.
    for obj in (
        first,
        first.year_errors[0],
        first.measured_order,
        first.modelled_order,
        first.pbias_condition,
        first.order_condition,
        first.h10,
        first.large_events,
    ):
        assert is_dataclass(obj)
        assert obj.__dataclass_params__.frozen is True  # type: ignore[attr-defined]

    assert isinstance(first.measured_order, YearOrder)
    assert isinstance(first.years, tuple)
    assert isinstance(first.year_errors, tuple)
    assert isinstance(first.large_events.days_above_cap, tuple)
    assert isinstance(first.large_events.days_without_value, tuple)
    if first.measured_order.order is not None:
        assert isinstance(first.measured_order.order, tuple)

    with pytest.raises(FrozenInstanceError):
        first.h10 = Condition("fail", "PLACEHOLDER")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.pbias_condition.verdict = "fail"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.year_errors[0].reason = "PLACEHOLDER"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.measured_order.reason = "PLACEHOLDER"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.large_events.flagged = False  # type: ignore[misc]
