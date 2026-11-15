"""Acceptance test of the trivial comparator of the soil loss (entry E0 of
``docs/VALIDATION.md``; decision D211 of issue #77; unit
l0/trivial-comparator-e0-d211, issue #311).

EXAMPLE DATA. The calendars, the twelve monthly erosivity values and the
tables below are written by hand for this test. Their numbers mean nothing:
they describe no real place, field, crop, climate or producer, and every
source string says PLACEHOLDER. They are chosen only so that each order can be
counted by hand line by line.

Run from the repository root: ``python -m pytest validation/test_trivial_comparator_erosion.py``.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from contracts.results.models import Missing, ResultsTable, ResultsTableRow
from validation import trivial_comparator_erosion
from validation.trivial_comparator_erosion import (
    compare_with_soil_loss,
    erosion_orders,
    year_shares,
)

CASE_ID = "example-case-e0"
FIELD_ID = "example-field-e0"
SOURCE = "PLACEHOLDER_example_data_written_by_hand_for_entry_E0"
SCENARIO = "phase_1"
START_MONTH = 7  # the agricultural year starts in July (as D73 has it)
FIRST_DAY = dt.date(2020, 7, 1)
LAST_DAY = dt.date(2022, 6, 30)  # agricultural years 2020 and 2021, both of 365 days
AG_YEARS = (2020, 2021)

# Twelve monthly erosivity values, by calendar month (example data). They add
# up to 100, so the fraction of each month is its value over 100:
#   Jan 0.30  Feb 0.30  Mar 0.20  Apr 0.05  May 0.02  Jun 0.01
#   Jul 0.01  Aug 0.01  Sep 0.02  Oct 0.03  Nov 0.02  Dec 0.03
MONTHLY_EROSIVITY = {
    1: 30.0,
    2: 30.0,
    3: 20.0,
    4: 5.0,
    5: 2.0,
    6: 1.0,
    7: 1.0,
    8: 1.0,
    9: 2.0,
    10: 3.0,
    11: 2.0,
    12: 3.0,
}
# The same total spread evenly: every month 1/12.
UNIFORM_EROSIVITY = {month: 1.0 for month in range(1, 13)}

# The hand-made calendars, the same in both agricultural years: the months in
# which a living crop is on the field, whole months only.
LIVING_MONTHS = {
    "A": {12, 1, 2, 3},  # bare April to November
    "B": {6, 7, 8, 9, 10, 11},  # bare December to May
    "C": {9, 10, 11, 12, 1, 2, 3, 4, 5, 6},  # bare July and August
}

# --- the order counted by hand -----------------------------------------------------
#
# A whole month without a crop counts 1 and a whole month with a crop counts 0,
# so the share of a year is the sum of the fractions of the bare months:
#   A: Apr + May + Jun + Jul + Aug + Sep + Oct + Nov
#      = 0.05 + 0.02 + 0.01 + 0.01 + 0.01 + 0.02 + 0.03 + 0.02 = 0.17
#   B: Dec + Jan + Feb + Mar + Apr + May = 0.03 + 0.30 + 0.30 + 0.20 + 0.05 + 0.02 = 0.90
#   C: Jul + Aug = 0.01 + 0.01 = 0.02
# Both years are the same, so each mean is that share. Lower is better:
# 0.02 < 0.17 < 0.90, so the order, best first, is C, A, B.
HAND_SHARES = {"A": 0.17, "B": 0.90, "C": 0.02}
HAND_ORDER = ("C", "A", "B")
# Without the weighting, the share of the days without a crop, per year of
# 365 days: A 244 / 365 = 0.668 (Apr 30, May 31, Jun 30, Jul 31, Aug 31, Sep
# 30, Oct 31, Nov 30); B 182 / 365 = 0.499 (Dec 31, Jan 31, Feb 28, Mar 31,
# Apr 30, May 31); C 62 / 365 = 0.170 (Jul 31, Aug 31). Order C, B, A: not the
# weighted order, so the test reads the weighting. With the erosivity spread
# evenly the weighted share is the number of bare months over 12 (A 8/12, B
# 6/12, C 2/12): also C, B, A.
UNWEIGHTED_ORDER = ("C", "B", "A")


def flags(living_months, first=FIRST_DAY, last=LAST_DAY):
    """The daily flags of a living crop of one hand-made calendar."""
    days = {}
    day = first
    while day <= last:
        days[day] = day.month in living_months
        day += dt.timedelta(days=1)
    return days


def living(rotations=("A", "B", "C"), scenario=SCENARIO, months=LIVING_MONTHS):
    return {
        (rotation_id, scenario): flags(months[rotation_id]) for rotation_id in rotations
    }


def soil_table(values, scenario=SCENARIO):
    """A hand-made results table of soil loss: one value per rotation, the
    same in both agricultural years."""
    rows = []
    for rotation_id, value in values.items():
        for ag_year in AG_YEARS:
            rows.append(
                ResultsTableRow(
                    rotation_id=rotation_id,
                    scenario_id=scenario,
                    time_basis="ag_year",
                    ag_year=ag_year,
                    indicator="soil_loss",
                    direction="lower_is_better",
                    value=value,
                    unit="t ha-1 yr-1",
                    range_missing=Missing(
                        reason="NOT_AVAILABLE", detail="example data"
                    ),
                    provenance="DERIVED",
                    source=SOURCE,
                )
            )
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# --- (a) the order counted by hand -------------------------------------------------


def test_the_shares_and_the_order_are_the_ones_counted_by_hand():
    shares = year_shares(living(), MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert {(item.rotation_id, item.ag_year) for item in shares} == {
        (rotation_id, ag_year) for rotation_id in "ABC" for ag_year in AG_YEARS
    }
    for item in shares:
        assert item.missing is None
        assert item.share == pytest.approx(HAND_SHARES[item.rotation_id])
    (order,) = erosion_orders(living(), MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert order.scenario_id == SCENARIO
    assert dict(order.means) == pytest.approx(HAND_SHARES)
    assert order.order == HAND_ORDER
    assert order.reason is None


def test_the_weighting_by_erosivity_changes_the_order():
    (weighted,) = erosion_orders(living(), MONTHLY_EROSIVITY, start_month=START_MONTH)
    (even,) = erosion_orders(living(), UNIFORM_EROSIVITY, start_month=START_MONTH)
    assert weighted.order == HAND_ORDER
    assert even.order == UNWEIGHTED_ORDER
    assert weighted.order != even.order


def test_a_part_of_a_month_counts_by_its_days():
    # A crop on the field from 16 April: April counts 15 / 30 without a crop.
    months = dict(LIVING_MONTHS)
    days = flags(months["A"])
    for year in (2021, 2022):
        for day in range(16, 31):
            days[dt.date(year, 4, day)] = True
    shares = year_shares(
        {("A", SCENARIO): days}, MONTHLY_EROSIVITY, start_month=START_MONTH
    )
    # 0.17 - 0.05 + 0.05 * 15 / 30 = 0.145
    assert [item.share for item in shares] == pytest.approx([0.145, 0.145])


# --- (b) the report against the full soil loss ------------------------------------


def test_the_report_says_equal_when_the_full_soil_loss_gives_the_same_order():
    # Full soil loss, lower is better: C 1.0, A 2.0, B 4.0 -> C, A, B.
    (item,) = compare_with_soil_loss(
        living(),
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 4.0, "C": 1.0}),
        start_month=START_MONTH,
    )
    assert item.full.order == HAND_ORDER
    assert item.outcome == "equal"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (3, 3)


def test_the_report_says_different_when_the_orders_differ():
    # Full soil loss: A 1.0, C 2.0, B 4.0 -> A, C, B.
    (item,) = compare_with_soil_loss(
        living(),
        MONTHLY_EROSIVITY,
        soil_table({"A": 1.0, "B": 4.0, "C": 2.0}),
        start_month=START_MONTH,
    )
    assert item.full.order == ("A", "C", "B")
    assert item.trivial.order == HAND_ORDER
    assert item.outcome == "different"


def test_the_full_method_ties_when_every_rotation_has_the_same_soil_loss():
    # As D158 makes it today with the single declared C: every rotation the
    # same soil loss. The reading of D0 gives no order (a tie), and the report
    # says that the full method gives no order.
    (item,) = compare_with_soil_loss(
        living(),
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 2.0, "C": 2.0}),
        start_month=START_MONTH,
    )
    assert item.full.order is None
    assert "equal" in item.full_reason
    assert item.trivial.order == HAND_ORDER
    assert item.outcome == "no order from the full method"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (3, 0)


def test_the_rotations_must_be_the_same_on_both_sides():
    with pytest.raises(ValueError, match="same rotations"):
        compare_with_soil_loss(
            living(),
            MONTHLY_EROSIVITY,
            soil_table({"A": 1.0, "B": 2.0}),
            start_month=START_MONTH,
        )


# --- no order, with the reason -----------------------------------------------------


def test_a_day_without_a_flag_is_a_missing_year_and_never_a_zero():
    data = living()
    del data[("A", SCENARIO)][dt.date(2022, 3, 15)]  # agricultural year 2021
    shares = {
        (item.rotation_id, item.ag_year): item
        for item in year_shares(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    }
    assert shares[("A", 2021)].share is None
    assert shares[("A", 2021)].missing.reason == "NO_COVERAGE"
    assert shares[("A", 2020)].share == pytest.approx(0.17)
    (order,) = erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert order.order is None and order.means is None
    assert "'A' in 2021 (NO_COVERAGE)" in order.reason
    assert "never filled or taken as zero" in order.reason


def test_a_missing_flag_keeps_its_reason():
    data = living()
    data[("B", SCENARIO)][dt.date(2020, 9, 1)] = Missing(
        reason="MISSING_INPUT", detail="example data: the stage of the day is unknown"
    )
    (order,) = erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert order.order is None
    assert "'B' in 2020 (MISSING_INPUT)" in order.reason


def test_a_tie_of_two_mean_shares_gives_no_order():
    months = {"A": LIVING_MONTHS["A"], "B": LIVING_MONTHS["A"]}
    (order,) = erosion_orders(
        living(("A", "B"), months=months), MONTHLY_EROSIVITY, start_month=START_MONTH
    )
    assert order.order is None
    assert "equal" in order.reason and "tie" in order.reason


def test_a_single_rotation_gives_no_order():
    (order,) = erosion_orders(
        living(("A",)), MONTHLY_EROSIVITY, start_month=START_MONTH
    )
    assert order.order is None and "one rotation" in order.reason


def test_a_missing_monthly_erosivity_gives_no_share():
    erosivity = dict(MONTHLY_EROSIVITY)
    erosivity[2] = Missing(
        reason="MISSING_INPUT", detail="example data: February not given"
    )
    shares = year_shares(living(), erosivity, start_month=START_MONTH)
    assert all(item.share is None for item in shares)
    assert {item.missing.reason for item in shares} == {"MISSING_INPUT"}
    (order,) = erosion_orders(living(), erosivity, start_month=START_MONTH)
    assert order.order is None


def test_each_scenario_is_read_on_its_own():
    # Phase 2 lays the calendars of A and B the other way round.
    data = living()
    data.update(
        {
            ("A", "phase_2"): flags(LIVING_MONTHS["B"]),
            ("B", "phase_2"): flags(LIVING_MONTHS["A"]),
            ("C", "phase_2"): flags(LIVING_MONTHS["C"]),
        }
    )
    orders = {
        item.scenario_id: item.order
        for item in erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    }
    assert orders == {"phase_1": ("C", "A", "B"), "phase_2": ("C", "B", "A")}


# --- the functions are pure and hold no value of the method -----------------------


def test_the_module_reads_no_file_clock_or_network_and_holds_no_number():
    tree = ast.parse(
        Path(trivial_comparator_erosion.__file__).read_text(encoding="utf-8")
    )
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "calendar",
        "datetime",
        "itertools",
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
    assert not attributes & {"today", "now", "utcnow"}  # no clock
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }
    assert numbers <= {0, 1, 2}  # counting only: no threshold, no value of the method
