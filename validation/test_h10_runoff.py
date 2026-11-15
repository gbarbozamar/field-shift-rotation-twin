"""Tests of the H10 runoff comparison (entry H10 of ``docs/VALIDATION.md``;
unit l0/validation-h10-d230, issue #355, decisions D229 and D230 of issue
#77).

EXAMPLE DATA. Every table below is written by hand for this test. Its numbers
mean nothing: they are not the runoff of any plot, they are not the values of
Grahmann et al. (2022), Table 5, and they describe no real place, field or
producer. The values of the source enter the repository only through a fixture
that a person transcribes and signs (D34, D66). The years are the three years
D229 names, used as labels only.

The bound of the percent bias and the cap of a single event are the numbers
of D230 ("within ±25%"; "events up to 100 mm"), passed by each test as the
decision gives them; the module holds neither.

Run from the repository root: ``python -m pytest validation/test_h10_runoff.py``.
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
from fractions import Fraction
from pathlib import Path

import pytest

from contracts.results.models import Missing
from validation import h10_runoff
from validation.h10_runoff import compare_h10_runoff

BOUND_D230 = 25  # D230, condition (1): PBIAS within ±25%
CAP_D230 = 100  # D230: a modelled single event above 100 mm is reported

# Example measured yearly runoff, mm (hand-made; NOT the values of the source).
# Sum 600. Order, highest first: 2018, 2019, 2017.
MEASURED = {2017: 100.0, 2018: 300.0, 2019: 200.0}


def run(modelled, measured=MEASURED, daily=None):
    return compare_h10_runoff(
        measured,
        modelled,
        pbias_bound_percent=BOUND_D230,
        event_cap_mm=CAP_D230,
        modelled_daily=daily,
    )


# --- a pass ----------------------------------------------------------------------


def test_a_pass():
    # Modelled sum 560: PBIAS = 100 * (600 - 560) / 600 = 6.666...; same order.
    result = run({2017: 90.0, 2018: 280.0, 2019: 190.0})
    assert result.years == (2017, 2018, 2019)
    assert result.pbias_percent == pytest.approx(100 * 40 / 600)
    assert result.pbias_reason is None
    assert result.measured_order.order == (2018, 2019, 2017)
    assert result.modelled_order.order == (2018, 2019, 2017)
    assert result.orders_match is True
    assert result.pbias_condition.verdict == "pass"
    assert result.order_condition.verdict == "pass"
    assert result.h10.verdict == "pass"
    assert result.h10.reason is None


def test_each_year_has_its_relative_error_and_no_pass_mark():
    # 2017: 100 * (100 - 90) / 100 = 10; 2018: 100 * 20 / 300; 2019: 100 * 10 / 200.
    result = run({2017: 90.0, 2018: 280.0, 2019: 190.0})
    errors = {e.year: e.relative_error_percent for e in result.year_errors}
    assert errors == pytest.approx({2017: 10.0, 2018: 100 * 20 / 300, 2019: 5.0})
    assert all(e.reason is None for e in result.year_errors)
    assert {e.year: (e.measured, e.modelled) for e in result.year_errors} == {
        2017: (100.0, 90.0),
        2018: (300.0, 280.0),
        2019: (200.0, 190.0),
    }
    fields = {f for e in result.year_errors for f in vars(e)}
    assert not {f for f in fields if "verdict" in f or "pass" in f}


# --- a fail by one condition only --------------------------------------------------


def test_a_fail_by_the_percent_bias_only():
    # Modelled sum 350: PBIAS = 100 * 250 / 600 = 41.666...; same order.
    result = run({2017: 50.0, 2018: 200.0, 2019: 100.0})
    assert result.pbias_percent == pytest.approx(100 * 250 / 600)
    assert result.pbias_condition.verdict == "fail"
    assert result.order_condition.verdict == "pass"
    assert result.h10.verdict == "fail"
    assert "percent bias" in result.h10.reason
    assert "order of the years" not in result.h10.reason


def test_a_fail_by_the_order_only():
    # Modelled sum 600: PBIAS = 0; order 2018, 2017, 2019.
    result = run({2017: 200.0, 2018: 300.0, 2019: 100.0})
    assert result.pbias_percent == 0
    assert result.pbias_condition.verdict == "pass"
    assert result.modelled_order.order == (2018, 2017, 2019)
    assert result.orders_match is False
    assert result.order_condition.verdict == "fail"
    assert result.h10.verdict == "fail"
    assert "order of the years" in result.h10.reason
    assert "percent bias" not in result.h10.reason


# --- the edge of the bound ----------------------------------------------------------


@pytest.mark.parametrize(
    ("modelled", "pbias", "verdict"),
    [
        # Sum 450: PBIAS = 100 * 150 / 600 = 25 exactly.
        ({2017: 50.0, 2018: 250.0, 2019: 150.0}, 25, "pass"),
        # Sum 750: PBIAS = 100 * -150 / 600 = -25 exactly.
        ({2017: 150.0, 2018: 350.0, 2019: 250.0}, -25, "pass"),
        # Sum 449: PBIAS = 100 * 151 / 600, just above 25.
        ({2017: 49.0, 2018: 250.0, 2019: 150.0}, 100 * 151 / 600, "fail"),
        # Sum 751: PBIAS = 100 * -151 / 600, just below -25.
        ({2017: 151.0, 2018: 350.0, 2019: 250.0}, 100 * -151 / 600, "fail"),
    ],
)
def test_the_edge_of_the_bound_is_inside(modelled, pbias, verdict):
    result = run(modelled)
    assert result.pbias_percent == pytest.approx(pbias)
    assert result.pbias_condition.verdict == verdict
    assert result.order_condition.verdict == "pass"
    assert result.h10.verdict == verdict


def test_the_edge_is_computed_exactly_from_the_stored_values():
    # Measured 0.1, 0.2, 0.4 (sum 0.7 as written); modelled sum is 0.525 as
    # written, so PBIAS is 25 as written. Computed exactly from the stored
    # binary values the bias is not exactly 25; the test only asks that the
    # result is the exact one, whatever side of the edge it falls on.
    measured = {2017: 0.1, 2018: 0.2, 2019: 0.4}
    modelled = {2017: 0.075, 2018: 0.15, 2019: 0.3}
    result = run(modelled, measured=measured)
    total_m = sum(map(Fraction, measured.values()))
    total_s = sum(map(Fraction, modelled.values()))
    exact = 100 * (total_m - total_s) / total_m
    assert result.pbias_percent == float(exact)
    assert result.pbias_condition.verdict == ("pass" if abs(exact) <= 25 else "fail")


# --- the sign convention --------------------------------------------------------------


def test_the_sign_is_positive_when_ep3_underestimates():
    under = run({2017: 80.0, 2018: 270.0, 2019: 190.0})  # sum 540
    over = run({2017: 120.0, 2018: 330.0, 2019: 210.0})  # sum 660
    assert under.pbias_percent == pytest.approx(100 * 60 / 600)
    assert over.pbias_percent == pytest.approx(100 * -60 / 600)
    assert all(e.relative_error_percent > 0 for e in under.year_errors)
    assert all(e.relative_error_percent < 0 for e in over.year_errors)


# --- no verdict -----------------------------------------------------------------------


def _no_verdict(result):
    assert result.pbias_percent is None
    assert result.orders_match is None
    assert result.measured_order.order is None
    assert result.modelled_order.order is None
    for condition in (result.pbias_condition, result.order_condition, result.h10):
        assert condition.verdict is None
        assert condition.reason


def test_a_missing_year_gives_no_verdict_and_never_a_zero():
    result = run({2017: 90.0, 2018: 280.0})
    _no_verdict(result)
    assert "the modelled values have no year 2019" in result.h10.reason
    (missing,) = [e for e in result.year_errors if e.year == 2019]
    assert missing.modelled is None
    assert missing.relative_error_percent is None
    assert "not given" in missing.reason
    # The years that have both values keep their relative error.
    assert [e.year for e in result.year_errors if e.reason is None] == [2017, 2018]


def test_a_missing_value_gives_no_verdict_with_its_reason():
    missing = Missing(reason="NOT_COMPUTABLE", detail="example data: no run")
    result = run({2017: 90.0, 2018: missing, 2019: 190.0})
    _no_verdict(result)
    assert "the modelled value of 2018 is missing with the reason NOT_COMPUTABLE" in (
        result.h10.reason
    )
    measured_missing = dict(MEASURED)
    measured_missing[2017] = Missing(reason="MISSING_INPUT", detail="example data")
    result = run({2017: 90.0, 2018: 280.0, 2019: 190.0}, measured=measured_missing)
    _no_verdict(result)
    assert "the measured value of 2017 is missing" in result.h10.reason


def test_a_value_that_is_not_a_finite_number_gives_no_verdict():
    result = run({2017: float("nan"), 2018: 280.0, 2019: 190.0})
    _no_verdict(result)
    assert "the modelled value of 2017 is not a finite number" in result.h10.reason


def test_a_modelled_year_the_measured_values_do_not_hold_gives_no_verdict():
    result = run({2016: 10.0, 2017: 90.0, 2018: 280.0, 2019: 190.0})
    _no_verdict(result)
    assert "year 2016" in result.h10.reason


def test_no_measured_year_gives_no_verdict():
    result = run({}, measured={})
    _no_verdict(result)
    assert "no measured year" in result.h10.reason


# --- a tie ------------------------------------------------------------------------------


def test_a_tie_in_the_modelled_order_gives_no_order():
    # Modelled sum 500: PBIAS = 100 * 100 / 600, inside the bound; 2017 and 2019 tie.
    result = run({2017: 100.0, 2018: 300.0, 2019: 100.0})
    assert result.pbias_condition.verdict == "pass"
    assert result.modelled_order.order is None
    assert "2017 and 2019 are equal" in result.modelled_order.reason
    assert result.measured_order.order == (2018, 2019, 2017)
    assert result.orders_match is None
    assert result.order_condition.verdict is None
    assert result.h10.verdict is None
    assert "2017 and 2019" in result.h10.reason


def test_a_tie_in_the_measured_order_gives_no_order():
    measured = {2017: 200.0, 2018: 300.0, 2019: 200.0}  # sum 700
    result = run({2017: 190.0, 2018: 280.0, 2019: 180.0}, measured=measured)
    assert result.measured_order.order is None
    assert "measured values of 2017 and 2019 are equal" in result.measured_order.reason
    assert result.order_condition.verdict is None
    assert result.h10.verdict is None


def test_a_tie_with_a_failed_percent_bias_fails_h10():
    # Modelled sum 200: PBIAS = 100 * 400 / 600, outside the bound; 2017 and 2019 tie.
    result = run({2017: 50.0, 2018: 100.0, 2019: 50.0})
    assert result.pbias_condition.verdict == "fail"
    assert result.order_condition.verdict is None
    assert result.h10.verdict == "fail"


# --- a zero total -------------------------------------------------------------------------


def test_a_zero_measured_total_gives_no_percent_bias():
    measured = {2017: 0.0, 2018: 0.0, 2019: 0.0}
    result = run({2017: 10.0, 2018: 30.0, 2019: 20.0}, measured=measured)
    assert result.pbias_percent is None
    assert "not above zero" in result.pbias_reason
    assert result.pbias_condition.verdict is None
    assert result.h10.verdict is None
    assert all(e.relative_error_percent is None for e in result.year_errors)
    assert all("zero" in e.reason for e in result.year_errors)


# --- an event above the cap -----------------------------------------------------------------

MODELLED_PASS = {2017: 90.0, 2018: 280.0, 2019: 190.0}


def test_an_event_above_the_cap_is_reported_and_the_rule_does_not_change():
    daily = {
        dt.date(2018, 4, 1): 3.0,
        dt.date(2018, 4, 2): 120.0,
        dt.date(2018, 4, 3): 0.0,
    }
    with_events = run(MODELLED_PASS, daily=daily)
    without = run(MODELLED_PASS)
    assert with_events.large_events.flagged is True
    assert with_events.large_events.days_above_cap == ((dt.date(2018, 4, 2), 120.0),)
    assert with_events.h10 == without.h10
    assert with_events.pbias_condition == without.pbias_condition
    assert with_events.order_condition == without.order_condition


def test_an_event_at_the_cap_is_not_above_it():
    daily = {dt.date(2019, 1, 1): 100.0, dt.date(2019, 1, 2): 99.0}
    events = run(MODELLED_PASS, daily=daily).large_events
    assert events.flagged is False
    assert events.days_above_cap == ()
    assert events.reason is None


def test_a_day_without_a_value_leaves_the_flag_open():
    unknown = Missing(reason="NOT_COMPUTABLE", detail="example data")
    daily = {dt.date(2019, 1, 1): 10.0, dt.date(2019, 1, 2): unknown}
    events = run(MODELLED_PASS, daily=daily).large_events
    assert events.flagged is None
    assert events.days_without_value == (
        (dt.date(2019, 1, 2), "missing with the reason NOT_COMPUTABLE: example data"),
    )
    assert "cannot be ruled out" in events.reason
    # A day above the cap raises the flag whatever other days hold.
    daily[dt.date(2019, 1, 3)] = 101.0
    assert run(MODELLED_PASS, daily=daily).large_events.flagged is True


def test_no_daily_runoff_gives_no_flag_with_its_reason():
    events = run(MODELLED_PASS).large_events
    assert events.flagged is None
    assert "no daily modelled runoff" in events.reason


# --- the arguments and the module --------------------------------------------------------------


def test_the_bound_and_the_cap_have_no_default():
    parameters = inspect.signature(compare_h10_runoff).parameters
    for name in ("pbias_bound_percent", "event_cap_mm"):
        assert parameters[name].default is inspect.Parameter.empty
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        compare_h10_runoff(MEASURED, MODELLED_PASS, event_cap_mm=CAP_D230)
    with pytest.raises(TypeError):
        compare_h10_runoff(MEASURED, MODELLED_PASS, pbias_bound_percent=BOUND_D230)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_a_bound_or_a_cap_that_is_not_a_finite_number_is_refused(bad):
    with pytest.raises(ValueError):
        compare_h10_runoff(
            MEASURED, MODELLED_PASS, pbias_bound_percent=bad, event_cap_mm=CAP_D230
        )
    with pytest.raises(ValueError):
        compare_h10_runoff(
            MEASURED, MODELLED_PASS, pbias_bound_percent=BOUND_D230, event_cap_mm=bad
        )


def test_the_module_reads_no_file_clock_or_network_and_holds_no_number():
    tree = ast.parse(Path(h10_runoff.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "collections",
        "contracts",
        "dataclasses",
        "datetime",
        "fractions",
        "itertools",
        "math",
        "typing",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "input", "eval", "exec"}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not attributes & {"today", "now", "utcnow"}
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }
    # Zero, the pairs of a tie, and the 100 of the formula of D230; no bound, no cap.
    assert numbers <= {0, 2, 100}
