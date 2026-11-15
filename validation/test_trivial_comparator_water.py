"""Acceptance test of the trivial comparator of the water-deficit exposure
(entry H0 of ``docs/VALIDATION.md``; unit l0/trivial-comparator-h0-d212,
issue #312, decision D212 of issue #77).

EXAMPLE DATA. Every daily series, calendar and table below is written by hand
for this test. Its numbers mean nothing: they describe no real place, field,
crop or producer, and every source string says PLACEHOLDER. Each agricultural
year is cut to a few days so that the sums can be read off line by line; the
module does not need a whole year to be given. A day of the calendar with no
living crop is written ``NA``: its demanded transpiration is missing with the
reason ``NOT_APPLICABLE``, as the daily balance of EP3 gives it on a day with
no crop.

Run from the repository root:
``python -m pytest validation/test_trivial_comparator_water.py``.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from contracts.results.models import Missing, Range, ResultsTable, ResultsTableRow
from engine.water.exposure import WINDOW_LABEL, _no_living_crop, _nothing_demanded
from validation import trivial_comparator_water
from validation.trivial_comparator_water import (
    WaterDay,
    compare_with_full_indicator,
    water_orders,
    year_ratio,
)

CASE_ID = "example-case-h0"
FIELD_ID = "example-field-h0"
SOURCE = "PLACEHOLDER_example_data_written_by_hand_for_entry_H0"
KIND = "PLACEHOLDER_kind"
NA = Missing(reason="NOT_APPLICABLE", detail="example data: no crop on the day")
LABEL = "whole cycle, not critical period"


def days(ag_year, entries):
    """The days of one hand-made agricultural year: (precipitation, demanded
    transpiration) per day, in mm; ``NA`` where the calendar has no living crop."""
    first = dt.date(ag_year, 5, 1)
    return tuple(
        WaterDay(first + dt.timedelta(days=i), precipitation, demanded)
        for i, (precipitation, demanded) in enumerate(entries)
    )


def water_row(rotation_id, scenario_id, ag_year, value):
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit="dimensionless",
        range=Range(low=value - 0.05, high=value + 0.05, kind=KIND),
        provenance="SIMULATED",
        source=SOURCE,
    )


def table(values):
    """``values`` maps (rotation_id, scenario_id) to the full values per year."""
    rows = [
        water_row(rotation_id, scenario_id, ag_year, value)
        for (rotation_id, scenario_id), by_year in values.items()
        for ag_year, value in by_year.items()
    ]
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# --- the hand-made case, scenario s1 ---------------------------------------------
#
# Days as (precipitation, demanded transpiration), mm:
#   A 2020: (9, NA) (2, 4) (2, 4)    the first day is a fallow before sowing
#   A 2021: (10, 4) (2, 4)
#   B 2020: (3, 4) (3, 4)
#   B 2021: (2, 4) (2, 4) (5, NA)    the last day is the tail after maturity
SERIES = {
    ("A", "s1", 2020): days(2020, [(9.0, NA), (2.0, 4.0), (2.0, 4.0)]),
    ("A", "s1", 2021): days(2021, [(10.0, 4.0), (2.0, 4.0)]),
    ("B", "s1", 2020): days(2020, [(3.0, 4.0), (3.0, 4.0)]),
    ("B", "s1", 2021): days(2021, [(2.0, 4.0), (2.0, 4.0), (5.0, NA)]),
}
# The ratio counted by hand, over the days with a living crop only:
#   A 2020: (2 + 2) / (4 + 4) = 4 / 8 = 0.5    (the 9 mm of the fallow day is left out)
#   A 2021: (10 + 2) / (4 + 4) = 12 / 8 = 1.5  (above one, and kept)
#   B 2020: (3 + 3) / (4 + 4) = 6 / 8 = 0.75
#   B 2021: (2 + 2) / (4 + 4) = 4 / 8 = 0.5    (the 5 mm of the tail day is left out)
# Means over the agricultural years: A (0.5 + 1.5) / 2 = 1.0; B (0.75 + 0.5) / 2
# = 0.625. Higher is better: A, B. The year 2020 alone would give B, A.
HAND_RATIOS = {("A", 2020): 0.5, ("A", 2021): 1.5, ("B", 2020): 0.75, ("B", 2021): 0.5}
HAND_CROP_DAYS = {("A", 2020): 2, ("A", 2021): 2, ("B", 2020): 2, ("B", 2021): 2}
HAND_MEANS = {"A": 1.0, "B": 0.625}
HAND_ORDER = ("A", "B")
# Full values of water_deficit_exposure, hand-made: A 0.6, 0.8 (mean 0.7); B 0.5,
# 0.7 (mean 0.6). By the reading of D0, higher is better: A, B, the same order.
FULL_EQUAL = {("A", "s1"): {2020: 0.6, 2021: 0.8}, ("B", "s1"): {2020: 0.5, 2021: 0.7}}


# --- (a) the order counted by hand -----------------------------------------------


def test_the_order_is_the_one_counted_by_hand():
    (order,) = water_orders(SERIES)
    assert order.scenario_id == "s1"
    ratios = {(year.rotation_id, year.ag_year): year.ratio for year in order.years}
    assert ratios == pytest.approx(HAND_RATIOS)
    assert {
        (y.rotation_id, y.ag_year): y.crop_days for y in order.years
    } == HAND_CROP_DAYS
    assert dict(order.means) == pytest.approx(HAND_MEANS)
    assert order.order == HAND_ORDER
    assert order.reason is None


def test_a_ratio_above_one_is_kept():
    ratio = year_ratio("A", "s1", 2021, SERIES[("A", "s1", 2021)])
    assert ratio.ratio == pytest.approx(1.5)
    assert ratio.missing is None


def test_days_without_a_living_crop_do_not_enter_the_sums():
    # The same year without the fallow day gives the same ratio.
    with_fallow = year_ratio("A", "s1", 2020, SERIES[("A", "s1", 2020)])
    without = year_ratio("A", "s1", 2020, days(2020, [(2.0, 4.0), (2.0, 4.0)]))
    assert with_fallow.ratio == without.ratio == pytest.approx(0.5)
    # A missing precipitation on a day with no crop does not touch the year.
    unknown_rain = Missing(reason="MISSING_INPUT", detail="example data: no rain value")
    fallow_unknown = days(2020, [(unknown_rain, NA), (2.0, 4.0), (2.0, 4.0)])
    assert year_ratio("A", "s1", 2020, fallow_unknown).ratio == pytest.approx(0.5)


# --- (b) the report against the full indicator, by the reading of D0 -------------


def test_the_report_says_equal_when_both_orders_agree():
    (item,) = compare_with_full_indicator(SERIES, table(FULL_EQUAL))
    assert item.trivial.order == HAND_ORDER
    assert item.full.order == HAND_ORDER
    assert dict(item.full.means) == pytest.approx({"A": 0.7, "B": 0.6})
    assert item.outcome == "equal"
    assert item.rotations_ordered == 2
    assert item.rotations_ordered_full == 2


def test_the_report_says_different_when_the_balance_changes_the_order():
    # A wet fallow before sowing: rain the full balance can carry into the crop
    # (storage carried between crops), which the comparator leaves out.
    #   A 2020 and 2021: (20, NA) (1, 4) (1, 4) -> 2 / 8 = 0.25 each, mean 0.25
    #   B 2020 and 2021: (2, 4) (2, 4)          -> 4 / 8 = 0.5 each, mean 0.5
    # Comparator: B, A. Full values, hand-made as if the stored fallow rain had
    # kept A unstressed: A 0.9, 0.9; B 0.6, 0.6 -> A, B.
    wet_fallow = [(20.0, NA), (1.0, 4.0), (1.0, 4.0)]
    series = {
        ("A", "s1", 2020): days(2020, wet_fallow),
        ("A", "s1", 2021): days(2021, wet_fallow),
        ("B", "s1", 2020): days(2020, [(2.0, 4.0), (2.0, 4.0)]),
        ("B", "s1", 2021): days(2021, [(2.0, 4.0), (2.0, 4.0)]),
    }
    full = {("A", "s1"): {2020: 0.9, 2021: 0.9}, ("B", "s1"): {2020: 0.6, 2021: 0.6}}
    (item,) = compare_with_full_indicator(series, table(full))
    assert dict(item.trivial.means) == pytest.approx({"A": 0.25, "B": 0.5})
    assert item.trivial.order == ("B", "A")
    assert item.full.order == ("A", "B")
    assert item.outcome == "different"
    assert item.rotations_ordered == 2


def test_every_result_carries_the_label_of_the_window():
    assert WINDOW_LABEL == LABEL
    (item,) = compare_with_full_indicator(SERIES, table(FULL_EQUAL))
    assert item.label == LABEL
    assert item.trivial.label == LABEL
    assert all(year.label == LABEL for year in item.trivial.years)


# --- the states of a year with no ratio, as EP3 gives the full indicator ---------


def test_a_year_with_no_living_crop_is_not_applicable_as_in_ep3():
    ratio = year_ratio("A", "s1", 2020, days(2020, [(9.0, NA), (4.0, NA)]))
    assert ratio.ratio is None
    assert ratio.missing.reason == _no_living_crop(2020).reason == "NOT_APPLICABLE"
    assert ratio.crop_days == 0

    series = dict(SERIES)
    series[("A", "s1", 2020)] = days(2020, [(9.0, NA), (4.0, NA)])
    (item,) = compare_with_full_indicator(series, table(FULL_EQUAL))
    assert item.trivial.order is None
    assert item.trivial.means is None
    assert "'A' in 2020 (NOT_APPLICABLE)" in item.trivial.reason
    assert item.outcome == "no order from the trivial comparator"
    assert item.rotations_ordered == 0


def test_a_zero_demand_is_not_computable_as_in_ep3():
    ratio = year_ratio("A", "s1", 2020, days(2020, [(3.0, 0.0), (2.0, 0.0)]))
    assert ratio.ratio is None
    assert ratio.missing.reason == _nothing_demanded(2020, 2).reason == "NOT_COMPUTABLE"
    assert ratio.crop_days == 2


def test_a_negative_demand_is_not_computable_as_in_ep3():
    # EP3 asks that the demanded sum be above zero (``not water_demanded >
    # _ZERO``), not only that it differ from zero. A negative sum gives no
    # ratio, never the negative number (here -5 / -3).
    for entries in ([(3.0, -4.0), (2.0, -4.0)], [(3.0, -4.0), (2.0, 1.0)]):
        ratio = year_ratio("A", "s1", 2020, days(2020, entries))
        assert ratio.ratio is None, entries
        assert ratio.missing.reason == _nothing_demanded(2020, 2).reason, entries
        assert ratio.crop_days == 2


def test_a_missing_day_makes_the_year_missing_and_never_a_zero():
    unknown = Missing(reason="MISSING_INPUT", detail="example data: no rain value")
    ratio = year_ratio("B", "s1", 2020, days(2020, [(3.0, 4.0), (unknown, 4.0)]))
    assert ratio.ratio is None
    assert ratio.missing.reason == "MISSING_INPUT"
    assert "2020-05-02" in ratio.missing.detail

    not_declared = Missing(reason="NOT_DECLARED", detail="example data: no coefficient")
    ratio = year_ratio("B", "s1", 2020, days(2020, [(3.0, 4.0), (3.0, not_declared)]))
    assert ratio.ratio is None
    assert ratio.missing.reason == "NOT_DECLARED"

    series = dict(SERIES)
    series[("B", "s1", 2020)] = days(2020, [(3.0, 4.0), (unknown, 4.0)])
    (order,) = water_orders(series)
    assert order.order is None and order.means is None
    assert "'B' in 2020 (MISSING_INPUT)" in order.reason
    assert "never filled or taken as zero" in order.reason


# --- what entry D0 does not say: no order, with the reason ----------------------


def test_a_tie_of_two_means_gives_no_order():
    # A: 4 / 8 = 0.5 both years; B: 2 / 4 = 0.5 both years.
    series = {
        ("A", "s1", 2020): days(2020, [(2.0, 4.0), (2.0, 4.0)]),
        ("A", "s1", 2021): days(2021, [(2.0, 4.0), (2.0, 4.0)]),
        ("B", "s1", 2020): days(2020, [(2.0, 4.0)]),
        ("B", "s1", 2021): days(2021, [(2.0, 4.0)]),
    }
    (item,) = compare_with_full_indicator(series, table(FULL_EQUAL))
    assert dict(item.trivial.means) == pytest.approx({"A": 0.5, "B": 0.5})
    assert item.trivial.order is None
    assert "equal" in item.trivial.reason and "tie" in item.trivial.reason
    assert item.outcome == "no order from the trivial comparator"


def test_a_single_rotation_gives_no_order():
    series = {key: value for key, value in SERIES.items() if key[0] == "A"}
    full = {("A", "s1"): FULL_EQUAL[("A", "s1")]}
    (item,) = compare_with_full_indicator(series, table(full))
    assert item.trivial.order is None and "one rotation" in item.trivial.reason
    assert item.full.order is None and "one rotation" in item.full.reason
    assert item.outcome == "no order from either"
    assert item.rotations_ordered == 0


def test_each_scenario_is_read_on_its_own():
    # s2 holds the series of s1 with A and B swapped: B, A.
    series = dict(SERIES)
    for (rotation_id, _, ag_year), value in SERIES.items():
        series[("B" if rotation_id == "A" else "A", "s2", ag_year)] = value
    full = dict(FULL_EQUAL)
    full[("A", "s2")] = FULL_EQUAL[("B", "s1")]
    full[("B", "s2")] = FULL_EQUAL[("A", "s1")]
    report = {
        item.scenario_id: item
        for item in compare_with_full_indicator(series, table(full))
    }
    assert report["s1"].trivial.order == ("A", "B")
    assert report["s2"].trivial.order == ("B", "A")
    assert report["s2"].full.order == ("B", "A")
    assert report["s2"].outcome == "equal"


def test_a_scenario_on_one_side_only_gives_no_order_with_the_reason():
    full = dict(FULL_EQUAL)
    full[("A", "s9")] = {2020: 0.6}
    full[("B", "s9")] = {2020: 0.5}
    report = {
        item.scenario_id: item
        for item in compare_with_full_indicator(SERIES, table(full))
    }
    assert report["s9"].trivial.order is None
    assert "no daily series" in report["s9"].trivial.reason
    assert report["s9"].outcome == "no order from the trivial comparator"


def test_the_means_are_compared_exactly_as_in_d0():
    # A: 1.0 and 1e-17; B: 1.0 and 0.0. In floating point both sums are 1.0, so
    # means taken in floating point tie; the stored values differ, so the exact
    # means do not: A is ahead (OPEN 7 of D0, which this module follows).
    series = {
        ("A", "s1", 2020): days(2020, [(1.0, 1.0)]),
        ("A", "s1", 2021): days(2021, [(1e-17, 1.0)]),
        ("B", "s1", 2020): days(2020, [(1.0, 1.0)]),
        ("B", "s1", 2021): days(2021, [(0.0, 1.0)]),
    }
    assert (1.0 + 1e-17) / 2 == (1.0 + 0.0) / 2  # the float means would tie
    (order,) = water_orders(series)
    assert order.order == ("A", "B")
    assert order.reason is None


def test_the_report_says_not_the_same_rotations_when_the_sides_differ():
    # The comparator orders A and B; the table orders A and C. Both orders
    # exist, over different rotations: neither "equal" nor "different".
    full = {("A", "s1"): {2020: 0.6, 2021: 0.8}, ("C", "s1"): {2020: 0.5, 2021: 0.7}}
    (item,) = compare_with_full_indicator(SERIES, table(full))
    assert item.trivial.order == HAND_ORDER
    assert item.full.order == ("A", "C")
    assert item.outcome == "not the same rotations"
    assert (item.rotations_ordered, item.rotations_ordered_full) == (2, 2)


def test_the_report_says_no_order_from_the_full_indicator_when_only_it_gives_none():
    # The comparator orders A, B; the full values tie (0.6 and 0.6 for both).
    full = {("A", "s1"): {2020: 0.6, 2021: 0.6}, ("B", "s1"): {2020: 0.6, 2021: 0.6}}
    (item,) = compare_with_full_indicator(SERIES, table(full))
    assert item.trivial.order == HAND_ORDER
    assert item.full.order is None and "equal" in item.full.reason
    assert item.outcome == "no order from the full indicator"
    assert (item.rotations_ordered, item.rotations_ordered_full) == (2, 0)


# --- the functions are pure and hold no value of the method -----------------------


def test_the_module_reads_no_file_clock_or_network_and_holds_no_number():
    tree = ast.parse(
        Path(trivial_comparator_water.__file__).read_text(encoding="utf-8")
    )
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "datetime",
        "itertools",
        "math",
        "collections",
        "dataclasses",
        "fractions",
        "typing",
        "contracts",
        "engine",
        "validation",
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
    assert numbers <= {0, 1, 2}  # counting only: no threshold, no tolerance
