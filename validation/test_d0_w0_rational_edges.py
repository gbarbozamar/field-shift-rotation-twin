"""Edge and mutant-killing tests for D0, W0/H0, and E2 rational comparators:
- ``validation/trivial_comparator.py`` (D0)
- ``validation/trivial_comparator_water.py`` (H0 / W0)
- ``validation/order_between_systems.py`` (E2)

Every table, daily series, and identifier here uses PLACEHOLDER test inputs
only and carries no real scientific or domain data.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from contracts.results.models import Missing, Range, ResultsTable, ResultsTableRow
from validation.order_between_systems import compare_with_expected_order
from validation.trivial_comparator import (
    _order_one,
    compare_with_decision,
    decision_order,
    trivial_orders,
)
from validation.trivial_comparator_water import (
    WaterDay,
    compare_with_full_indicator,
    water_orders,
    year_ratio,
)

CASE_ID = "PLACEHOLDER-d0-w0-case"
FIELD_ID = "PLACEHOLDER-d0-w0-field"
SOURCE = "PLACEHOLDER_d0_w0_rational_edges"
KIND = "PLACEHOLDER_kind"
NA = Missing(reason="NOT_APPLICABLE", detail="PLACEHOLDER: no crop on the day")


def _soil_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int,
    value: float | None,
    *,
    low: float | None = None,
    high: float | None = None,
    with_range: bool = True,
    reason: str = "NO_COVERAGE",
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit="t ha-1 yr-1",
            missing=Missing(reason=reason, detail=f"PLACEHOLDER missing {reason}"),
        )
    if not with_range:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=value,
            unit="t ha-1 yr-1",
            range_missing=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER no range"),
            provenance="DERIVED",
            source=SOURCE,
        )
    lo = value - 0.01 if low is None else low
    hi = value + 0.01 if high is None else high
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range=Range(low=lo, high=hi, kind=KIND),
        provenance="DERIVED",
        source=SOURCE,
    )


def _water_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int,
    value: float | None,
    *,
    low: float | None = None,
    high: float | None = None,
    with_range: bool = True,
    reason: str = "NO_COVERAGE",
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=None,
            unit="dimensionless",
            missing=Missing(reason=reason, detail=f"PLACEHOLDER missing {reason}"),
        )
    if not with_range:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=value,
            unit="dimensionless",
            range_missing=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER no range"),
            provenance="SIMULATED",
            source=SOURCE,
        )
    lo = value - 0.01 if low is None else low
    hi = value + 0.01 if high is None else high
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit="dimensionless",
        range=Range(low=lo, high=hi, kind=KIND),
        provenance="SIMULATED",
        source=SOURCE,
    )


def _table(rows: list[ResultsTableRow]) -> ResultsTable:
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


def _wdays(
    entries: list[tuple[float | Missing, float | Missing]], ag_year: int = 2020
) -> tuple[WaterDay, ...]:
    start = dt.date(ag_year, 5, 1)
    return tuple(
        WaterDay(start + dt.timedelta(days=i), precip, demand)
        for i, (precip, demand) in enumerate(entries)
    )


# === 1. IEEE-754 float trap (0.1 + 0.2 == 0.3) & exact rational mean ties ===


def test_ieee754_01_plus_02_vs_03_across_d0_e2_and_w0():
    # Precondition: 0.1 + 0.2 != 0.3 in binary64 (0.1 + 0.2 > 0.3).
    assert (0.1 + 0.2) > 0.3

    rows = [
        _soil_row("A", "s1", 2020, 0.1),
        _soil_row("A", "s1", 2021, 0.2),
        _soil_row("B", "s1", 2020, 0.3),
        _soil_row("B", "s1", 2021, 0.0),
        _water_row("A", "s1", 2020, 0.1),
        _water_row("A", "s1", 2021, 0.2),
        _water_row("B", "s1", 2020, 0.3),
        _water_row("B", "s1", 2021, 0.0),
    ]
    tbl = _table(rows)
    by_ind = {item.indicator: item for item in trivial_orders(tbl)}
    # A's stored mean is strictly larger than B's stored mean.
    assert by_ind["soil_loss"].order == ("B", "A")
    assert by_ind["soil_loss"].reason is None
    assert by_ind["water_deficit_exposure"].order == ("A", "B")
    assert by_ind["water_deficit_exposure"].reason is None

    # E2 delegates to D0, so it observes the same exact binary64 ordering.
    (e2_eq,) = compare_with_expected_order(tbl, ("B", "A"))
    assert e2_eq.outcome == "equal"
    assert e2_eq.full.order == ("B", "A")
    (e2_diff,) = compare_with_expected_order(tbl, ("A", "B"))
    assert e2_diff.outcome == "different"

    # W0 / H0 across two years and within a single multi-day year.
    series_two_years = {
        ("A", "s1", 2020): _wdays([(0.1, 1.0)], 2020),
        ("A", "s1", 2021): _wdays([(0.2, 1.0)], 2021),
        ("B", "s1", 2020): _wdays([(0.3, 1.0)], 2020),
        ("B", "s1", 2021): _wdays([(0.0, 1.0)], 2021),
    }
    (w_two,) = water_orders(series_two_years)
    assert w_two.order == ("A", "B")
    assert w_two.reason is None

    series_one_year = {
        ("A", "s1", 2020): _wdays([(0.1, 1.0), (0.2, 1.0)], 2020),
        ("B", "s1", 2020): _wdays([(0.3, 1.0), (0.0, 1.0)], 2020),
    }
    (w_one,) = water_orders(series_one_year)
    assert w_one.order == ("A", "B")


def test_ieee754_float_mean_tie_broken_by_exact_fraction_in_d0_e2_w0():
    # Both float sum/2 and float(exact) tie at 0.15000000000000002, yet
    # Fraction(0.1) + Fraction(0.2) < Fraction(0.1 + 0.2).
    summed = 0.1 + 0.2
    assert (0.1 + 0.2) / 2.0 == (summed + 0.0) / 2.0

    rows = [
        _soil_row("A", "s1", 2020, 0.1),
        _soil_row("A", "s1", 2021, 0.2),
        _soil_row("B", "s1", 2020, summed),
        _soil_row("B", "s1", 2021, 0.0),
        _water_row("A", "s1", 2020, 0.1),
        _water_row("A", "s1", 2021, 0.2),
        _water_row("B", "s1", 2020, summed),
        _water_row("B", "s1", 2021, 0.0),
    ]
    tbl = _table(rows)
    by_ind = {item.indicator: item for item in trivial_orders(tbl)}
    assert dict(by_ind["soil_loss"].means)["A"] == dict(by_ind["soil_loss"].means)["B"]
    assert by_ind["soil_loss"].order == ("A", "B")
    assert by_ind["water_deficit_exposure"].order == ("B", "A")

    (e2_item,) = compare_with_expected_order(tbl, ("A", "B"))
    assert e2_item.outcome == "equal"

    series = {
        ("A", "s1", 2020): _wdays([(0.1, 1.0)], 2020),
        ("A", "s1", 2021): _wdays([(0.2, 1.0)], 2021),
        ("B", "s1", 2020): _wdays([(summed, 1.0)], 2020),
        ("B", "s1", 2021): _wdays([(0.0, 1.0)], 2021),
    }
    (w_order,) = water_orders(series)
    assert dict(w_order.means)["A"] == dict(w_order.means)["B"]
    assert w_order.order == ("B", "A")

    # Second float-tie pair: (1/3 + 2/3) / 2 == 0.5 == (1.0 + 0.0) / 2 in float,
    # yet Fraction(1/3) + Fraction(2/3) < Fraction(1.0).
    one_third = 1.0 / 3.0
    two_thirds = 2.0 / 3.0
    assert (one_third + two_thirds) / 2.0 == (1.0 + 0.0) / 2.0
    third_rows = [
        _soil_row("A", "s1", 2020, one_third),
        _soil_row("A", "s1", 2021, two_thirds),
        _soil_row("B", "s1", 2020, 1.0),
        _soil_row("B", "s1", 2021, 0.0),
    ]
    (third_order,) = trivial_orders(_table(third_rows))
    assert dict(third_order.means) == {"A": 0.5, "B": 0.5}
    assert third_order.order == ("A", "B")


def test_exact_rational_tie_immune_to_float_addition_order_across_d0_e2_w0():
    # Naive left-to-right float addition gives (0.1 + 0.2) + 0.3 != (0.3 + 0.2) + 0.1.
    assert ((0.1 + 0.2) + 0.3) / 3.0 != ((0.3 + 0.2) + 0.1) / 3.0

    rows = [
        _soil_row("A", "s1", 2020, 0.1),
        _soil_row("A", "s1", 2021, 0.2),
        _soil_row("A", "s1", 2022, 0.3),
        _soil_row("B", "s1", 2020, 0.3),
        _soil_row("B", "s1", 2021, 0.2),
        _soil_row("B", "s1", 2022, 0.1),
        _water_row("A", "s1", 2020, 0.1),
        _water_row("A", "s1", 2021, 0.2),
        _water_row("A", "s1", 2022, 0.3),
        _water_row("B", "s1", 2020, 0.3),
        _water_row("B", "s1", 2021, 0.2),
        _water_row("B", "s1", 2022, 0.1),
    ]
    tbl = _table(rows)
    for item in trivial_orders(tbl):
        assert item.order is None
        assert item.means is not None
        assert "'A' and 'B'" in item.reason
        assert "tie" in item.reason

    (e2_item,) = compare_with_expected_order(tbl, ("A", "B"))
    assert e2_item.outcome == "no order from the full method"
    assert e2_item.rotations_ordered == 0

    series = {
        ("A", "s1", 2020): _wdays([(0.1, 1.0)], 2020),
        ("A", "s1", 2021): _wdays([(0.2, 1.0)], 2021),
        ("A", "s1", 2022): _wdays([(0.3, 1.0)], 2022),
        ("B", "s1", 2020): _wdays([(0.3, 1.0)], 2020),
        ("B", "s1", 2021): _wdays([(0.2, 1.0)], 2021),
        ("B", "s1", 2022): _wdays([(0.1, 1.0)], 2022),
    }
    (w_order,) = water_orders(series)
    assert w_order.order is None
    assert w_order.means is not None
    assert "'A' and 'B'" in w_order.reason

    # Exact dyadic rational tie across distinct values: (0.125 + 0.375) / 2 == 0.25.
    dyadic_rows = [
        _soil_row("A", "s1", 2020, 0.125),
        _soil_row("A", "s1", 2021, 0.375),
        _soil_row("B", "s1", 2020, 0.25),
        _soil_row("B", "s1", 2021, 0.25),
        _soil_row("C", "s1", 2020, 0.1),
        _soil_row("C", "s1", 2021, 0.1),
    ]
    (dyadic_order,) = trivial_orders(_table(dyadic_rows))
    assert dyadic_order.order is None
    assert dict(dyadic_order.means)["A"] == 0.25
    assert dict(dyadic_order.means)["B"] == 0.25
    assert "'A' and 'B'" in dyadic_order.reason


def test_w0_fsum_preserves_01_plus_02_vs_03_under_large_cancellation():
    # Naive float summation loses 0.1, 0.2, 0.3 when added after 1e16.
    series = {
        ("A", "s1", 2020): _wdays([(1e16, 1.0), (0.1, 1.0), (0.2, 1.0), (-1e16, 1.0)]),
        ("B", "s1", 2020): _wdays([(1e16, 1.0), (0.3, 1.0), (0.0, 1.0), (-1e16, 1.0)]),
    }
    (w_order,) = water_orders(series)
    assert w_order.order == ("A", "B")
    assert w_order.reason is None


# === 2. D166 multi-scenario independence =====================================


def test_d166_missing_year_in_scenario_1_does_not_break_scenario_2_d0_and_decision():
    # Insert s2 before s1 and water before soil to verify deterministic D166 sorting.
    rows = [
        # s2: complete years; soil_loss separates cleanly, water ranges overlap.
        _water_row("B", "s2", 2020, 0.7, low=0.1, high=0.8),
        _water_row("B", "s2", 2021, 0.8, low=0.1, high=0.85),
        _water_row("A", "s2", 2020, 0.3, low=0.0, high=0.9),
        _water_row("A", "s2", 2021, 0.4, low=0.0, high=0.9),
        _soil_row("B", "s2", 2020, 1.0, low=0.9, high=1.1),
        _soil_row("B", "s2", 2021, 2.0, low=1.9, high=2.1),
        _soil_row("A", "s2", 2020, 4.0, low=3.9, high=4.1),
        _soil_row("A", "s2", 2021, 5.0, low=4.9, high=5.1),
        # s1: A misses 2021 on soil_loss; B misses 2020 on water_deficit_exposure.
        _soil_row("A", "s1", 2020, 1.0, low=0.9, high=1.1),
        _soil_row("A", "s1", 2021, None, reason="NO_COVERAGE"),
        _soil_row("B", "s1", 2020, 5.0, low=4.9, high=5.1),
        _soil_row("B", "s1", 2021, 6.0, low=5.9, high=6.1),
        _water_row("A", "s1", 2020, 0.8, low=0.79, high=0.81),
        _water_row("A", "s1", 2021, 0.9, low=0.89, high=0.91),
        _water_row("B", "s1", 2020, None, reason="MISSING_INPUT"),
        _water_row("B", "s1", 2021, 0.4, low=0.39, high=0.41),
    ]
    items = compare_with_decision(_table(rows))
    assert [(item.scenario_id, item.indicator) for item in items] == [
        ("s1", "soil_loss"),
        ("s1", "water_deficit_exposure"),
        ("s2", "soil_loss"),
        ("s2", "water_deficit_exposure"),
    ]
    report = {(item.scenario_id, item.indicator): item for item in items}

    assert report[("s1", "soil_loss")].trivial.order is None
    assert report[("s1", "soil_loss")].trivial.means is None
    assert "'A' in 2021 (NO_COVERAGE)" in report[("s1", "soil_loss")].trivial.reason
    assert report[("s1", "soil_loss")].decision.order == ("A", "B")
    assert report[("s1", "soil_loss")].outcome == "no order from the trivial comparator"

    assert report[("s1", "water_deficit_exposure")].trivial.order is None
    assert "'B' in 2020 (MISSING_INPUT)" in report[("s1", "water_deficit_exposure")].trivial.reason
    assert report[("s1", "water_deficit_exposure")].outcome == "no order from the trivial comparator"

    # s2 is completely unaffected by s1's missing years.
    assert report[("s2", "soil_loss")].trivial.order == ("B", "A")
    assert report[("s2", "soil_loss")].decision.order == ("B", "A")
    assert report[("s2", "soil_loss")].outcome == "equal"

    assert report[("s2", "water_deficit_exposure")].trivial.order == ("B", "A")
    assert report[("s2", "water_deficit_exposure")].decision.order is None
    assert report[("s2", "water_deficit_exposure")].outcome == "no order from the full decision"


def test_d166_overlapping_uncertainty_in_s1_does_not_leak_into_s2_decision_order():
    # Kills a mutant that passes the whole multi-scenario table to decision_order.
    rows = [
        # s1: overlapping ranges -> pair_state cannot separate A and B.
        _soil_row("A", "s1", 2020, 1.0, low=0.0, high=10.0),
        _soil_row("B", "s1", 2020, 5.0, low=0.0, high=10.0),
        # s2: disjoint ranges -> pair_state cleanly separates A and B.
        _soil_row("A", "s2", 2020, 1.0, low=0.9, high=1.1),
        _soil_row("B", "s2", 2020, 5.0, low=4.9, high=5.1),
    ]
    report = {
        item.scenario_id: item for item in compare_with_decision(_table(rows))
    }
    assert report["s1"].trivial.order == ("A", "B")
    assert report["s1"].decision.order is None
    assert report["s1"].outcome == "no order from the full decision"

    assert report["s2"].trivial.order == ("A", "B")
    assert report["s2"].decision.order == ("A", "B")
    assert report["s2"].outcome == "equal"


def test_d166_missing_year_in_s1_does_not_break_s2_in_w0_and_e2():
    # W0 / H0: s1 has a MISSING_INPUT year in series & NO_COVERAGE in table; s2 is valid.
    bad_rain = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER missing rain")
    series = {
        ("A", "s1", 2020): _wdays([(2.0, 4.0)], 2020),
        ("A", "s1", 2021): _wdays([(bad_rain, 4.0)], 2021),
        ("B", "s1", 2020): _wdays([(3.0, 4.0)], 2020),
        ("B", "s1", 2021): _wdays([(3.0, 4.0)], 2021),
        ("A", "s2", 2020): _wdays([(1.0, 4.0)], 2020),
        ("A", "s2", 2021): _wdays([(1.0, 4.0)], 2021),
        ("B", "s2", 2020): _wdays([(3.0, 4.0)], 2020),
        ("B", "s2", 2021): _wdays([(3.0, 4.0)], 2021),
    }
    w_tbl = _table(
        [
            _water_row("A", "s1", 2020, 0.5),
            _water_row("A", "s1", 2021, None, reason="NO_COVERAGE"),
            _water_row("B", "s1", 2020, 0.8),
            _water_row("B", "s1", 2021, 0.9),
            _water_row("A", "s2", 2020, 0.2),
            _water_row("A", "s2", 2021, 0.4),
            _water_row("B", "s2", 2020, 0.8),
            _water_row("B", "s2", 2021, 0.9),
        ]
    )
    w_report = {item.scenario_id: item for item in compare_with_full_indicator(series, w_tbl)}
    assert w_report["s1"].outcome == "no order from either"
    assert w_report["s1"].trivial.means is None
    assert w_report["s1"].full.means is None
    assert w_report["s2"].outcome == "equal"
    assert w_report["s2"].trivial.order == ("B", "A")
    assert w_report["s2"].full.order == ("B", "A")
    assert (w_report["s2"].rotations_ordered, w_report["s2"].rotations_ordered_full) == (2, 2)

    # E2: s1 missing year, s2 equal, s3 different, s4 no soil_loss row.
    e2_tbl = _table(
        [
            _soil_row("A", "s1", 2020, None, reason="NOT_AVAILABLE"),
            _soil_row("B", "s1", 2020, 2.0),
            _soil_row("A", "s2", 2020, 1.0),
            _soil_row("B", "s2", 2020, 3.0),
            _soil_row("A", "s3", 2020, 4.0),
            _soil_row("B", "s3", 2020, 1.0),
            _water_row("A", "s4", 2020, 0.6),
            _water_row("B", "s4", 2020, 0.4),
        ]
    )
    e2_report = {
        item.scenario_id: item for item in compare_with_expected_order(e2_tbl, ("A", "B"))
    }
    assert e2_report["s1"].outcome == "no order from the full method"
    assert "'A' in 2020 (NOT_AVAILABLE)" in e2_report["s1"].reason
    assert e2_report["s2"].outcome == "equal"
    assert e2_report["s3"].outcome == "different"
    assert e2_report["s4"].outcome == "no order from the full method"
    assert "holds no 'soil_loss'" in e2_report["s4"].reason


# === 3. higher_is_better vs lower_is_better directionality flip ==============


def test_directionality_flip_lower_vs_higher_is_better_reverses_order():
    # Identical values across soil_loss (lower_is_better) and
    # water_deficit_exposure (higher_is_better) must produce exact reversed orders
    # in both trivial_orders and decision_order.
    vals = {
        "A": (0.3, 0.5, 0.7),  # mean 0.5
        "B": (0.1, 0.6, 0.2),  # mean 0.3
        "C": (0.8, 0.4, 0.9),  # mean 0.7
    }
    # Ranges tight enough that every year separates pairs cleanly? Note: B vs A
    # crosses in 2021 (0.6 vs 0.5), so use strictly separated values for decision_order
    # and keep the crossing values in a second check for trivial_orders alone.
    rows_crossing = []
    for rot, series in vals.items():
        for yr, val in zip((2020, 2021, 2022), series, strict=True):
            rows_crossing.append(_soil_row(rot, "s1", yr, val))
            rows_crossing.append(_water_row(rot, "s1", yr, val))
    by_ind = {item.indicator: item for item in trivial_orders(_table(rows_crossing))}
    assert by_ind["soil_loss"].direction == "lower_is_better"
    assert by_ind["soil_loss"].order == ("B", "A", "C")
    assert by_ind["water_deficit_exposure"].direction == "higher_is_better"
    assert by_ind["water_deficit_exposure"].order == ("C", "A", "B")

    # Monotone year-by-year values so compare_with_decision checks both trivial & decision.
    mono = {
        "A": (0.4, 0.5, 0.6),  # mean 0.5
        "B": (0.1, 0.2, 0.3),  # mean 0.2
        "C": (0.7, 0.8, 0.9),  # mean 0.8
    }
    rows_mono = []
    for rot, series in mono.items():
        for yr, val in zip((2020, 2021, 2022), series, strict=True):
            rows_mono.append(_soil_row(rot, "s1", yr, val, low=val - 0.02, high=val + 0.02))
            rows_mono.append(_water_row(rot, "s1", yr, val, low=val - 0.02, high=val + 0.02))
    rep = {
        item.indicator: item for item in compare_with_decision(_table(rows_mono))
    }
    assert rep["soil_loss"].trivial.order == ("B", "A", "C")
    assert rep["soil_loss"].decision.order == ("B", "A", "C")
    assert rep["soil_loss"].outcome == "equal"
    assert rep["water_deficit_exposure"].trivial.order == ("C", "A", "B")
    assert rep["water_deficit_exposure"].decision.order == ("C", "A", "B")
    assert rep["water_deficit_exposure"].outcome == "equal"


def test_order_one_direct_direction_flip_on_float_trap():
    def _ns_rows(direction: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                rotation_id="A",
                direction=direction,
                time_basis="ag_year",
                ag_year=2020,
                value=0.1,
                missing=None,
            ),
            SimpleNamespace(
                rotation_id="A",
                direction=direction,
                time_basis="ag_year",
                ag_year=2021,
                value=0.2,
                missing=None,
            ),
            SimpleNamespace(
                rotation_id="B",
                direction=direction,
                time_basis="ag_year",
                ag_year=2020,
                value=0.3,
                missing=None,
            ),
            SimpleNamespace(
                rotation_id="B",
                direction=direction,
                time_basis="ag_year",
                ag_year=2021,
                value=0.0,
                missing=None,
            ),
        ]

    low = _order_one("s1", "PLACEHOLDER_ind", _ns_rows("lower_is_better"))
    high = _order_one("s1", "PLACEHOLDER_ind", _ns_rows("higher_is_better"))
    assert low.order == ("B", "A")
    assert high.order == ("A", "B")


# === 4. Range rows ignored per D0 ============================================


def test_ranges_ignored_per_d0_even_when_skewed_overlapping_or_missing():
    # Point values give soil_loss order ("A", "B", "C") and water order ("C", "B", "A").
    # Skewed ranges invert the range midpoints: A midpoint = 50.0, B = 4.0, C = 6.0.
    tight = _table(
        [
            _soil_row("A", "s1", 2020, 2.0, low=1.9, high=2.1),
            _soil_row("B", "s1", 2020, 4.0, low=3.9, high=4.1),
            _soil_row("C", "s1", 2020, 6.0, low=5.9, high=6.1),
            _water_row("A", "s1", 2020, 0.2, low=0.19, high=0.21),
            _water_row("B", "s1", 2020, 0.5, low=0.49, high=0.51),
            _water_row("C", "s1", 2020, 0.8, low=0.79, high=0.81),
        ]
    )
    skewed = _table(
        [
            _soil_row("A", "s1", 2020, 2.0, low=0.0, high=100.0),
            _soil_row("B", "s1", 2020, 4.0, low=3.9, high=4.1),
            _soil_row("C", "s1", 2020, 6.0, low=5.9, high=6.1),
            _water_row("A", "s1", 2020, 0.2, low=0.0, high=10.0),
            _water_row("B", "s1", 2020, 0.5, low=0.49, high=0.51),
            _water_row("C", "s1", 2020, 0.8, low=0.79, high=0.81),
        ]
    )
    no_range = _table(
        [
            _soil_row("A", "s1", 2020, 2.0, with_range=False),
            _soil_row("B", "s1", 2020, 4.0, with_range=False),
            _soil_row("C", "s1", 2020, 6.0, with_range=False),
            _water_row("A", "s1", 2020, 0.2, with_range=False),
            _water_row("B", "s1", 2020, 0.5, with_range=False),
            _water_row("C", "s1", 2020, 0.8, with_range=False),
        ]
    )

    assert trivial_orders(tight) == trivial_orders(skewed) == trivial_orders(no_range)

    rep_tight = {i.indicator: i for i in compare_with_decision(tight)}
    rep_skewed = {i.indicator: i for i in compare_with_decision(skewed)}
    rep_no_range = {i.indicator: i for i in compare_with_decision(no_range)}

    assert rep_tight["soil_loss"].outcome == "equal"
    assert rep_skewed["soil_loss"].trivial.order == ("A", "B", "C")
    assert rep_skewed["soil_loss"].decision.order is None
    assert rep_skewed["soil_loss"].outcome == "no order from the full decision"

    assert rep_no_range["water_deficit_exposure"].trivial.order == ("C", "B", "A")
    assert rep_no_range["water_deficit_exposure"].decision.order is None
    assert rep_no_range["water_deficit_exposure"].outcome == "no order from the full decision"

    # E2 and H0 (full side) also ignore skewed/missing ranges via D0.
    assert compare_with_expected_order(tight, ("A", "B", "C")) == compare_with_expected_order(
        skewed, ("A", "B", "C")
    )
    assert compare_with_expected_order(tight, ("A", "B", "C")) == compare_with_expected_order(
        no_range, ("A", "B", "C")
    )

    series = {
        ("A", "s1", 2020): _wdays([(1.0, 4.0)], 2020),
        ("B", "s1", 2020): _wdays([(2.0, 4.0)], 2020),
        ("C", "s1", 2020): _wdays([(3.0, 4.0)], 2020),
    }
    (w_skewed,) = compare_with_full_indicator(series, skewed)
    (w_no_range,) = compare_with_full_indicator(series, no_range)
    assert w_skewed.outcome == "equal"
    assert w_no_range.outcome == "equal"


# === 5. Missing-year veto vs incomplete sets =================================


@pytest.mark.parametrize(
    "reason",
    [
        "NOT_DECLARED",
        "SOURCE_UNAVAILABLE",
        "NO_COVERAGE",
        "MISSING_INPUT",
        "NOT_COMPUTABLE",
        "CONTROL_FAILED",
        "NOT_AVAILABLE",
        "NOT_APPLICABLE",
    ],
)
def test_any_reason_code_missing_year_vetoes_d0_and_e2_while_decision_still_orders(reason):
    # 8 of 9 cells present with clear separation; 1 missing year vetoes D0 & E2.
    rows = [
        _soil_row("A", "s1", 2020, 1.0, low=0.9, high=1.1),
        _soil_row("A", "s1", 2021, 1.0, low=0.9, high=1.1),
        _soil_row("A", "s1", 2022, 1.0, low=0.9, high=1.1),
        _soil_row("B", "s1", 2020, 5.0, low=4.9, high=5.1),
        _soil_row("B", "s1", 2021, None, reason=reason),
        _soil_row("B", "s1", 2022, 5.0, low=4.9, high=5.1),
        _soil_row("C", "s1", 2020, 9.0, low=8.9, high=9.1),
        _soil_row("C", "s1", 2021, 9.0, low=8.9, high=9.1),
        _soil_row("C", "s1", 2022, 9.0, low=8.9, high=9.1),
    ]
    tbl = _table(rows)
    (d0_item,) = compare_with_decision(tbl)
    assert d0_item.trivial.order is None
    assert d0_item.trivial.means is None
    assert f"'B' in 2021 ({reason})" in d0_item.trivial.reason
    assert d0_item.decision.order == ("A", "B", "C")
    assert d0_item.outcome == "no order from the trivial comparator"

    (e2_item,) = compare_with_expected_order(tbl, ("A", "B", "C"))
    assert e2_item.outcome == "no order from the full method"
    assert e2_item.rotations_ordered == 0


def test_w0_missing_year_veto_vs_fallow_day_missing_precip():
    # A missing precipitation on a NOT_APPLICABLE (no-crop) day does NOT veto;
    # a missing precipitation on a living-crop day vetoes the year and order.
    missing_rain = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER rain")
    ok_series = {
        ("A", "s1", 2020): _wdays([(missing_rain, NA), (1.0, 4.0)], 2020),
        ("A", "s1", 2021): _wdays([(1.0, 4.0)], 2021),
        ("B", "s1", 2020): _wdays([(3.0, 4.0)], 2020),
        ("B", "s1", 2021): _wdays([(3.0, 4.0)], 2021),
    }
    (ok_order,) = water_orders(ok_series)
    assert ok_order.order == ("B", "A")
    assert ok_order.reason is None

    veto_series = dict(ok_series)
    veto_series[("A", "s1", 2020)] = _wdays([(missing_rain, 4.0)], 2020)
    (veto_order,) = water_orders(veto_series)
    assert veto_order.order is None
    assert veto_order.means is None
    assert "'A' in 2020 (MISSING_INPUT)" in veto_order.reason

    # Zero demanded transpiration on living-crop day -> NOT_COMPUTABLE veto.
    zero_demand = dict(ok_series)
    zero_demand[("B", "s1", 2021)] = _wdays([(3.0, 0.0)], 2021)
    (zero_order,) = water_orders(zero_demand)
    assert zero_order.order is None
    assert "'B' in 2021 (NOT_COMPUTABLE)" in zero_order.reason

    # Year with no living-crop day -> NOT_APPLICABLE veto.
    no_crop_year = year_ratio("A", "s1", 2020, _wdays([(5.0, NA)], 2020))
    assert no_crop_year.ratio is None
    assert no_crop_year.missing.reason == "NOT_APPLICABLE"


def test_incomplete_sets_in_results_table_w0_and_e2():
    # 1. ResultsTable contract forbids omitting a cell on one rotation.
    with pytest.raises(ValidationError, match="same cells"):
        _table(
            [
                _soil_row("A", "s1", 2020, 1.0),
                _soil_row("A", "s1", 2021, 2.0),
                _soil_row("B", "s1", 2020, 3.0),
            ]
        )

    # 2. Disjoint coverage across rotations in ResultsTable: D0 vetoes and D7 cannot
    # evaluate the pair -> "no order from either".
    disjoint_tbl = _table(
        [
            _soil_row("A", "s1", 2020, 1.0),
            _soil_row("A", "s1", 2021, None),
            _soil_row("B", "s1", 2020, None),
            _soil_row("B", "s1", 2021, 2.0),
        ]
    )
    (disjoint_d0,) = compare_with_decision(disjoint_tbl)
    assert disjoint_d0.outcome == "no order from either"
    assert decision_order(disjoint_tbl, "s1", "soil_loss").order is None

    # 3. W0: incomplete rotation set vs missing-year veto precedence.
    series_ab = {
        ("A", "s1", 2020): _wdays([(3.0, 4.0)], 2020),
        ("B", "s1", 2020): _wdays([(1.0, 4.0)], 2020),
    }
    table_abc = _table(
        [
            _water_row("A", "s1", 2020, 0.8),
            _water_row("B", "s1", 2020, 0.6),
            _water_row("C", "s1", 2020, 0.4),
        ]
    )
    (w_subset,) = compare_with_full_indicator(series_ab, table_abc)
    assert w_subset.outcome == "not the same rotations"
    assert (w_subset.rotations_ordered, w_subset.rotations_ordered_full) == (2, 3)

    # When trivial has a missing-year veto, outcome stays "no order from the trivial
    # comparator" even though full holds an extra rotation C.
    bad_rain = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER rain")
    series_ab_missing = {
        ("A", "s1", 2020): _wdays([(bad_rain, 4.0)], 2020),
        ("B", "s1", 2020): _wdays([(1.0, 4.0)], 2020),
    }
    (w_veto_wins,) = compare_with_full_indicator(series_ab_missing, table_abc)
    assert w_veto_wins.outcome == "no order from the trivial comparator"
    assert (w_veto_wins.rotations_ordered, w_veto_wins.rotations_ordered_full) == (0, 3)

    # W0 series with an omitted year for B (not a None YearRatio): water_orders
    # divides by each rotation's own year count (mean, not sum): A has (0.6, 0.6)
    # -> sum 1.2, mean 0.6; B has (0.8,) -> sum 0.8, mean 0.8 -> ("B", "A").
    uneven_series = {
        ("A", "s1", 2020): _wdays([(2.4, 4.0)], 2020),
        ("A", "s1", 2021): _wdays([(2.4, 4.0)], 2021),
        ("B", "s1", 2020): _wdays([(3.2, 4.0)], 2020),
    }
    (uneven_order,) = water_orders(uneven_series)
    assert dict(uneven_order.means) == pytest.approx({"A": 0.6, "B": 0.8})
    assert uneven_order.order == ("B", "A")

    # Same sum-vs-mean check directly on _order_one: A has [1.0, 1.0] (sum 2.0,
    # mean 1.0); B has [1.5] (sum 1.5, mean 1.5).
    ns_uneven = [
        SimpleNamespace(
            rotation_id="A",
            direction="lower_is_better",
            time_basis="ag_year",
            ag_year=2020,
            value=1.0,
            missing=None,
        ),
        SimpleNamespace(
            rotation_id="A",
            direction="lower_is_better",
            time_basis="ag_year",
            ag_year=2021,
            value=1.0,
            missing=None,
        ),
        SimpleNamespace(
            rotation_id="B",
            direction="lower_is_better",
            time_basis="ag_year",
            ag_year=2020,
            value=1.5,
            missing=None,
        ),
    ]
    ns_order = _order_one("s1", "PLACEHOLDER_ind", ns_uneven)
    assert dict(ns_order.means) == {"A": 1.0, "B": 1.5}
    assert ns_order.order == ("A", "B")

    # 4. E2: incomplete expected set vs superset vs missing-year veto precedence.
    soil_abc = _table(
        [
            _soil_row("A", "s1", 2020, 1.0),
            _soil_row("B", "s1", 2020, 2.0),
            _soil_row("C", "s1", 2020, 3.0),
        ]
    )
    (e2_sub,) = compare_with_expected_order(soil_abc, ("A", "B"))
    assert e2_sub.outcome == "not compared"
    assert e2_sub.rotations_ordered == 3
    assert e2_sub.full.order == ("A", "B", "C")

    (e2_sup,) = compare_with_expected_order(soil_abc, ("A", "B", "C", "D"))
    assert e2_sup.outcome == "not compared"
    assert e2_sup.rotations_ordered == 3

    soil_abc_missing = _table(
        [
            _soil_row("A", "s1", 2020, 1.0),
            _soil_row("B", "s1", 2020, None),
            _soil_row("C", "s1", 2020, 3.0),
        ]
    )
    (e2_veto_mismatch,) = compare_with_expected_order(soil_abc_missing, ("A", "B"))
    assert e2_veto_mismatch.outcome == "not compared"
    assert e2_veto_mismatch.rotations_ordered == 0
