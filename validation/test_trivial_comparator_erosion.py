"""Acceptance test of the trivial comparator of the soil loss (entry E0 of
``docs/VALIDATION.md``; decision D211 of issue #77; unit
l0/trivial-comparator-e0-d211, issue #311).

EXAMPLE DATA. The sets of living months, the twelve monthly erosivity values
and the tables below are written by hand for this test. Their numbers mean nothing:
they describe no real place, field, crop, climate or producer, and every
source string says PLACEHOLDER. They are chosen only so that each order can be
counted by hand line by line.

Run from the repository root: ``python -m pytest validation/test_trivial_comparator_erosion.py``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import (
    AgYearStart,
    Feasibility,
    RuleViolation,
)
from contracts.results.models import Missing, ResultsTable, ResultsTableRow
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.water import living_crop as water_living_crop
from params.catalogue import check_catalogue, load_folder
from validation import trivial_comparator_erosion
from validation.trivial_comparator_erosion import (
    compare_with_soil_loss,
    erosion_orders,
    flags_by_rotation_from_calendars,
    living_crop_flags_from_calendar,
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

# The hand-made sets of living months, the same in both agricultural years: the
# months in which a living crop is on the field, whole months only. The daily
# flags are laid from them over a hand-made record of days (``flags``).
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
    """The daily flags of a living crop of one hand-made set of living months."""
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


def test_a_trivial_tie_counts_no_rotation_ordered():
    # A and B hold the same flags, so the trivial side ties: it has the means of
    # both rotations but no order. The full soil loss orders them (A 2.0, B 4.0,
    # lower is better). The count of the trivial side is that of its order, zero,
    # never the number of its means.
    months = {"A": LIVING_MONTHS["A"], "B": LIVING_MONTHS["A"]}
    (item,) = compare_with_soil_loss(
        living(("A", "B"), months=months),
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 4.0}),
        start_month=START_MONTH,
    )
    assert item.trivial.order is None and len(item.trivial.means) == 2
    assert item.full.order == ("A", "B")
    assert item.outcome == "no order from the trivial comparator"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (0, 2)


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


# --- the mean is the one of D211 -------------------------------------------------
#
# Three agricultural years (2020, 2021 and 2022, each of 365 days). The set of
# living months of P changes in the last year; that of Q does not. With the
# shares counted above (C 0.02, A 0.17, B 0.90):
#   P: 0.02, 0.02, 0.90   mean 0.94 / 3 = 0.313   median 0.02   first year 0.02
#   Q: 0.17, 0.17, 0.17   mean 0.17               median 0.17   first year 0.17
# By the mean, lower is better: Q, P. By the median or by the first year
# alone: P, Q. So an order taken by either of those would fail this case.
THREE_YEARS = (2020, 2021, 2022)
THREE_YEARS_LAST_DAY = dt.date(2023, 6, 30)
BY_YEAR = {
    "P": {2020: LIVING_MONTHS["C"], 2021: LIVING_MONTHS["C"], 2022: LIVING_MONTHS["B"]},
    "Q": {year: LIVING_MONTHS["A"] for year in THREE_YEARS},
}
BY_YEAR_SHARES = {"P": (0.02, 0.02, 0.90), "Q": (0.17, 0.17, 0.17)}
MEAN_ORDER = ("Q", "P")
MEDIAN_ORDER = FIRST_YEAR_ORDER = ("P", "Q")


def flags_by_year(months_of_year, first=FIRST_DAY, last=THREE_YEARS_LAST_DAY):
    """The daily flags of one rotation whose set of living months is chosen per
    agricultural year (the year starts in START_MONTH)."""
    days = {}
    day = first
    while day <= last:
        ag_year = day.year if day.month >= START_MONTH else day.year - 1
        days[day] = day.month in months_of_year[ag_year]
        day += dt.timedelta(days=1)
    return days


def test_the_order_is_by_the_mean_and_not_by_the_median_or_the_first_year():
    data = {
        (rotation_id, SCENARIO): flags_by_year(BY_YEAR[rotation_id])
        for rotation_id in BY_YEAR
    }
    shares = year_shares(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    for rotation_id, expected in BY_YEAR_SHARES.items():
        found = [item for item in shares if item.rotation_id == rotation_id]
        assert [item.ag_year for item in found] == list(THREE_YEARS)
        assert [item.share for item in found] == pytest.approx(list(expected))
    (order,) = erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert dict(order.means) == pytest.approx({"P": 0.94 / 3, "Q": 0.17})
    assert order.order == MEAN_ORDER
    assert order.order != MEDIAN_ORDER and order.order != FIRST_YEAR_ORDER


# --- what a flag can be ----------------------------------------------------------


@pytest.mark.parametrize(
    "flag", [None, 0, 1, 0.0, "yes"], ids=["None", "0", "1", "0.0", "text"]
)
def test_a_flag_that_is_neither_a_bool_nor_a_missing_raises_type_error(flag):
    data = living()
    data[("A", SCENARIO)][dt.date(2020, 9, 1)] = flag
    with pytest.raises(TypeError, match="True, False or a Missing"):
        year_shares(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    with pytest.raises(TypeError, match="True, False or a Missing"):
        erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    with pytest.raises(TypeError, match="True, False or a Missing"):
        compare_with_soil_loss(
            data,
            MONTHLY_EROSIVITY,
            soil_table({"A": 2.0, "B": 4.0, "C": 1.0}),
            start_month=START_MONTH,
        )


@pytest.mark.parametrize("shape", [Missing, InputMissing], ids=["results", "inputs"])
def test_the_missing_of_either_contract_is_a_missing_flag(shape):
    data = living()
    data[("B", SCENARIO)][dt.date(2020, 9, 1)] = shape(
        reason="NOT_DECLARED", detail="example data: not given"
    )
    shares = {
        (item.rotation_id, item.ag_year): item
        for item in year_shares(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    }
    assert shares[("B", 2020)].share is None
    assert shares[("B", 2020)].missing.reason == "NOT_DECLARED"
    assert shares[("B", 2021)].share == pytest.approx(HAND_SHARES["B"])
    (order,) = erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert order.order is None
    assert "'B' in 2020 (NOT_DECLARED)" in order.reason


def test_a_scenario_whose_rotations_all_have_empty_flags_gives_no_order():
    data = {("A", SCENARIO): {}, ("B", SCENARIO): {}}
    assert year_shares(data, MONTHLY_EROSIVITY, start_month=START_MONTH) == ()
    (order,) = erosion_orders(data, MONTHLY_EROSIVITY, start_month=START_MONTH)
    assert (order.scenario_id, order.order, order.means) == (SCENARIO, None, None)
    assert "'A', 'B'" in order.reason and "empty" in order.reason
    (alone,) = erosion_orders(
        {("A", SCENARIO): {}}, MONTHLY_EROSIVITY, start_month=START_MONTH
    )
    assert alone.order is None and "one rotation" in alone.reason


# --- the counts of the report --------------------------------------------------------


def test_the_trivial_count_is_zero_when_the_trivial_side_gives_no_order():
    # The trivial side has a missing year (a missing flag of B), so it gives no
    # order although it holds three rotations.
    data = living()
    data[("B", SCENARIO)][dt.date(2020, 9, 1)] = Missing(
        reason="MISSING_INPUT", detail="example data: the stage of the day is unknown"
    )
    (item,) = compare_with_soil_loss(
        data,
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 4.0, "C": 1.0}),
        start_month=START_MONTH,
    )
    assert item.trivial.order is None and item.full.order == HAND_ORDER
    assert item.outcome == "no order from the trivial comparator"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (0, 3)
    # Both sides without an order: the full method ties.
    (item,) = compare_with_soil_loss(
        data,
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 2.0, "C": 2.0}),
        start_month=START_MONTH,
    )
    assert item.outcome == "no order from either"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (0, 0)
    # The empty flags of every rotation: no order on the trivial side either.
    empty = {(rotation_id, SCENARIO): {} for rotation_id in "ABC"}
    (item,) = compare_with_soil_loss(
        empty,
        MONTHLY_EROSIVITY,
        soil_table({"A": 2.0, "B": 4.0, "C": 1.0}),
        start_month=START_MONTH,
    )
    assert item.outcome == "no order from the trivial comparator"
    assert (item.trivial_rotations_ordered, item.full_rotations_ordered) == (0, 3)


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


# --- bridge from RotationCalendar to live_crop_by_day (unit #399) ---------------

_ROOT = Path(__file__).resolve().parent.parent
_DEMO_ROTATIONS_PATH = _ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
_RECORDS_DIR = _ROOT / "params" / "records"

_BRIDGE_MARK = "PLACEHOLDER"
_BRIDGE_UNMARKED = "UNMARKED_TEST_ONLY"

# PLACEHOLDER stage lengths for synthetic tests and Rotation B's synthetic
# stage-length override (wheat, maize). Distinct repeated digits, plainly not real
# FAO-56 values, unmarked in memory only when fed into the catalogue lookup.
_PLACEHOLDER_ROTATION_B_STAGE_LENGTHS = {
    "wheat": {
        "fao56_stage_length_initial": 11,
        "fao56_stage_length_development": 22,
        "fao56_stage_length_mid": 33,
        "fao56_stage_length_late": 44,
    },
    "maize": {
        "fao56_stage_length_initial": 15,
        "fao56_stage_length_development": 25,
        "fao56_stage_length_mid": 35,
        "fao56_stage_length_late": 15,
    },
}


def _stage_length_record(
    *, param_id: str, crop: str, value: float | int
) -> dict[str, object]:
    raw = json.dumps(
        {
            "id": param_id,
            "scope": {"crop": crop},
            "value": value,
            "unit": "day",
            "range": None,
            "range_missing_reason": f"{_BRIDGE_MARK} test record without range.",
            "citation": {
                "reference": f"{_BRIDGE_MARK} test-only parameter record for {param_id}",
                "locator": f"{_BRIDGE_MARK} unit test",
            },
            "transcribed_by": f"{_BRIDGE_MARK} test author",
            "checked_by": f"{_BRIDGE_MARK} test reviewer",
            "note": f"{_BRIDGE_MARK} in-memory record for E0 bridge test.",
        }
    ).replace(_BRIDGE_MARK, _BRIDGE_UNMARKED)
    return json.loads(raw)


def _placeholder_stage_catalogue(
    lengths_by_crop: dict[str, dict[str, float | int]],
    *,
    replace_in: dict[str, dict] | None = None,
) -> dict[str, dict]:
    records: dict[str, dict] = {}
    overrides: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for crop, stages in lengths_by_crop.items():
        for param_id, value in stages.items():
            rec = _stage_length_record(param_id=param_id, crop=crop, value=value)
            records[f"placeholder.{param_id}.{crop}"] = rec
            overrides.add((rec["id"], tuple(sorted(rec["scope"].items()))))
    if replace_in is None:
        return records
    merged = {
        key: copy.deepcopy(rec)
        for key, rec in replace_in.items()
        if (rec.get("id"), tuple(sorted(rec.get("scope", {}).items()))) not in overrides
    }
    merged.update(records)
    return merged


def _placeholder_rotation_definition(
    rotation_id: str,
    crop_id: str,
    sowing: str,
    harvest: str,
    *,
    start_month: int = 7,
) -> RotationDefinition:
    return RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            "case_id": CASE_ID,
            "field_id": FIELD_ID,
            "rotation_id": rotation_id,
            "label": f"{SOURCE} {rotation_id}",
            "ag_year_start": {
                "month": start_month,
                "provisional": True,
                "provenance": "DECLARED",
                "source": SOURCE,
            },
            "repeats": True,
            "components": [
                {
                    "component_id": "c1",
                    "position": 1,
                    "crop_id": crop_id,
                    "purpose": "grain",
                    "sowing": {
                        "date": sowing,
                        "provenance": "DECLARED",
                        "source": SOURCE,
                    },
                    "harvest": {
                        "date": harvest,
                        "provenance": "DECLARED",
                        "source": SOURCE,
                    },
                    "management": {
                        "residue": "left_on_surface",
                        "grazing": {"missing": {"reason": "NOT_DECLARED"}},
                        "termination": {"missing": {"reason": "NOT_DECLARED"}},
                    },
                }
            ],
        }
    )


def test_living_crop_flags_from_calendar_delegates_to_live_crop_by_day(monkeypatch):
    cal = build_rotation_calendar(
        _placeholder_rotation_definition("rot-a", "crop-a", "2020-10-01", "2020-12-31")
    )
    params = _placeholder_stage_catalogue(
        {
            "crop-a": {
                "fao56_stage_length_initial": 11,
                "fao56_stage_length_development": 11,
                "fao56_stage_length_mid": 11,
                "fao56_stage_length_late": 11,
            }
        }
    )
    d1, d2, d3 = dt.date(2020, 7, 1), dt.date(2020, 7, 2), dt.date(2020, 7, 3)
    sentinel_missing = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER delegated")
    recorded_calls = []

    def fake_live_crop_by_day(calendar, record_start, record_end, *, parameters):
        recorded_calls.append((calendar, record_start, record_end, parameters))
        return {d1: True, d2: False, d3: sentinel_missing}

    monkeypatch.setattr(
        trivial_comparator_erosion, "live_crop_by_day", fake_live_crop_by_day
    )
    flags = living_crop_flags_from_calendar(
        cal, start_date=d1, end_date=d3, parameters=params
    )
    assert recorded_calls == [(cal, d1, d3, params)]
    assert flags == {d1: True, d2: False, d3: sentinel_missing}
    assert flags[d1] is True
    assert flags[d2] is False


def test_living_crop_flags_from_calendar_matches_live_crop_by_day_and_is_pure():
    cal = build_rotation_calendar(
        _placeholder_rotation_definition("rot-a", "crop-a", "2020-10-01", "2020-11-30")
    )
    params = _placeholder_stage_catalogue(
        {
            "crop-a": {
                "fao56_stage_length_initial": 11,
                "fao56_stage_length_development": 11,
                "fao56_stage_length_mid": 11,
                "fao56_stage_length_late": 11,
            }
        }
    )
    cal_before = cal.model_copy(deep=True)
    params_before = copy.deepcopy(params)
    start, end = dt.date(2020, 7, 1), dt.date(2021, 6, 30)

    flags = living_crop_flags_from_calendar(
        cal, start_date=start, end_date=end, parameters=params
    )
    direct = water_living_crop.live_crop_by_day(
        cal, start, end, parameters=params
    )
    assert flags == direct
    # 44 live days from Oct 1 -> Oct 1..Nov 13 are True; Nov 14..30 is tail (False).
    assert flags[dt.date(2020, 9, 30)] is False
    assert flags[dt.date(2020, 10, 1)] is True
    assert flags[dt.date(2020, 11, 13)] is True
    assert flags[dt.date(2020, 11, 14)] is False
    assert flags[dt.date(2020, 11, 30)] is False
    # G1 purity: arguments untouched, second call equal.
    assert cal == cal_before
    assert params == params_before
    assert (
        living_crop_flags_from_calendar(
            cal, start_date=start, end_date=end, parameters=params
        )
        == flags
    )

    # Single-day window is accepted.
    single = living_crop_flags_from_calendar(
        cal, start_date=dt.date(2020, 10, 1), end_date=dt.date(2020, 10, 1), parameters=params
    )
    assert single == {dt.date(2020, 10, 1): True}


def test_living_crop_flags_from_calendar_keeps_missing_for_infeasible_or_missing_start_month():
    cal_base = build_rotation_calendar(
        _placeholder_rotation_definition("bad", "crop-a", "2020-10-01", "2020-11-30")
    )
    cal_no_start = cal_base.model_copy(
        update={
            "ag_year_start": AgYearStart(
                month=None,
                missing=InputMissing(reason="NOT_DECLARED"),
            )
        }
    )
    cal_infeasible = cal_base.model_copy(
        update={
            "feasibility": Feasibility(
                feasible=False,
                violations=[
                    RuleViolation(
                        rule="overlap",
                        component_ids=["c1"],
                        detail="PLACEHOLDER infeasible calendar",
                    )
                ],
            )
        }
    )
    start, end = dt.date(2020, 7, 1), dt.date(2020, 7, 3)

    flags_no_start = living_crop_flags_from_calendar(
        cal_no_start, start_date=start, end_date=end, parameters={}
    )
    assert all(
        isinstance(flag, Missing) and flag.reason == "MISSING_INPUT"
        for flag in flags_no_start.values()
    )

    flags_infeasible = living_crop_flags_from_calendar(
        cal_infeasible, start_date=start, end_date=end, parameters={}
    )
    assert all(
        isinstance(flag, Missing) and flag.reason == "NOT_COMPUTABLE"
        for flag in flags_infeasible.values()
    )


def test_bridge_validates_arguments_per_g5():
    cal = build_rotation_calendar(
        _placeholder_rotation_definition("rot-a", "crop-a", "2020-10-01", "2020-11-30")
    )
    start, end = dt.date(2020, 7, 1), dt.date(2021, 6, 30)

    with pytest.raises(TypeError, match="RotationCalendar"):
        living_crop_flags_from_calendar(
            cal.model_dump(), start_date=start, end_date=end, parameters={}
        )
    for bad_date in ("2020-07-01", None, dt.datetime(2020, 7, 1, 0, 0)):
        with pytest.raises(TypeError, match="datetime.date"):
            living_crop_flags_from_calendar(
                cal, start_date=bad_date, end_date=end, parameters={}
            )
        with pytest.raises(TypeError, match="datetime.date"):
            living_crop_flags_from_calendar(
                cal, start_date=start, end_date=bad_date, parameters={}
            )
    with pytest.raises(ValueError, match="before start_date"):
        living_crop_flags_from_calendar(
            cal, start_date=end, end_date=start, parameters={}
        )
    for bad_params in (None, [], {1: {}}, {"k": "not-a-dict"}):
        with pytest.raises(TypeError, match="parameters"):
            living_crop_flags_from_calendar(
                cal, start_date=start, end_date=end, parameters=bad_params
            )

    # flags_by_rotation_from_calendars validation
    assert flags_by_rotation_from_calendars(
        {}, start_date=start, end_date=end, parameters={}
    ) == {}
    with pytest.raises(ValueError, match="before start_date"):
        flags_by_rotation_from_calendars(
            {}, start_date=end, end_date=start, parameters={}
        )
    with pytest.raises(TypeError, match="calendars"):
        flags_by_rotation_from_calendars(
            [("A", "p1", cal)], start_date=start, end_date=end, parameters={}
        )
    for bad_key in ("A", ("A",), ("A", "p1", "extra"), (1, "p1"), ("A", 2)):
        with pytest.raises(TypeError, match="calendars"):
            flags_by_rotation_from_calendars(
                {bad_key: cal}, start_date=start, end_date=end, parameters={}
            )
    for blank_key in (("", "p1"), ("A", "   ")):
        with pytest.raises(ValueError, match="non-empty"):
            flags_by_rotation_from_calendars(
                {blank_key: cal}, start_date=start, end_date=end, parameters={}
            )
    with pytest.raises(TypeError, match="RotationCalendar"):
        flags_by_rotation_from_calendars(
            {("A", "p1"): "not-a-calendar"},
            start_date=start,
            end_date=end,
            parameters={},
        )


def test_flags_by_rotation_from_calendars_feeds_comparator_end_to_end():
    cal_a = build_rotation_calendar(
        _placeholder_rotation_definition("A", "crop-a", "2020-12-01", "2021-03-31")
    )
    cal_b = build_rotation_calendar(
        _placeholder_rotation_definition("B", "crop-b", "2020-07-01", "2020-11-30")
    )
    # 44 live days for A (in high-erosivity Dec-Jan); 44 live days for B (in low-erosivity Jul-Aug).
    params = _placeholder_stage_catalogue(
        {
            crop: {
                "fao56_stage_length_initial": 11,
                "fao56_stage_length_development": 11,
                "fao56_stage_length_mid": 11,
                "fao56_stage_length_late": 11,
            }
            for crop in ("crop-a", "crop-b")
        }
    )
    living_map = flags_by_rotation_from_calendars(
        {("A", SCENARIO): cal_a, ("B", SCENARIO): cal_b},
        start_date=FIRST_DAY,
        end_date=LAST_DAY,
        parameters=params,
    )
    assert set(living_map) == {("A", SCENARIO), ("B", SCENARIO)}
    (order,) = erosion_orders(
        living_map, MONTHLY_EROSIVITY, start_month=START_MONTH
    )
    # A has live crop in Jan (erosivity 0.30) and Dec (0.03), so lower bare share than B.
    assert order.order == ("A", "B")
    assert order.reason is None


@pytest.fixture(scope="module")
def _d128_calendars_and_catalogue():
    records, load_errors = load_folder(_RECORDS_DIR)
    assert load_errors == []
    assert check_catalogue(records) == []
    raw_rotations = json.loads(_DEMO_ROTATIONS_PATH.read_text(encoding="utf-8"))
    calendars = {}
    for entry in raw_rotations:
        rotation = RotationDefinition.model_validate(entry)
        calendars[rotation.rotation_id] = build_rotation_calendar(rotation)
    return calendars, records


def test_d128_rotation_a_with_shipped_catalogue_computes_live_flags_and_year_shares(
    _d128_calendars_and_catalogue,
):
    calendars, shipped = _d128_calendars_and_catalogue
    cal_a = calendars["soybean-winter-fallow"]
    start, end = dt.date(2020, 7, 1), dt.date(2023, 6, 30)

    flags_a = living_crop_flags_from_calendar(
        cal_a, start_date=start, end_date=end, parameters=shipped
    )
    assert len(flags_a) == (end - start).days + 1
    assert all(isinstance(flag, bool) for flag in flags_a.values())
    assert any(flag is True for flag in flags_a.values())
    assert any(flag is False for flag in flags_a.values())
    assert flags_a == water_living_crop.live_crop_by_day(
        cal_a, start, end, parameters=shipped
    )

    shares = year_shares(
        {("soybean-winter-fallow", "phase_0"): flags_a},
        MONTHLY_EROSIVITY,
        start_month=cal_a.ag_year_start.month,
    )
    assert [item.ag_year for item in shares] == [2020, 2021, 2022]
    assert all(item.missing is None and 0.0 < item.share < 1.0 for item in shares)

    # Partial boundary years behave per E0 / NO_COVERAGE when the window starts mid-year.
    boundary_flags = living_crop_flags_from_calendar(
        cal_a,
        start_date=dt.date(2020, 1, 1),
        end_date=dt.date(2022, 12, 31),
        parameters=shipped,
    )
    boundary_shares = {
        item.ag_year: item
        for item in year_shares(
            {("soybean-winter-fallow", "phase_0"): boundary_flags},
            MONTHLY_EROSIVITY,
            start_month=cal_a.ag_year_start.month,
        )
    }
    assert boundary_shares[2019].missing.reason == "NO_COVERAGE"
    assert boundary_shares[2022].missing.reason == "NO_COVERAGE"
    assert boundary_shares[2020].missing is None and boundary_shares[2021].missing is None


def test_d128_rotation_b_shipped_catalogue_preserves_missing_input_without_filling(
    _d128_calendars_and_catalogue,
):
    calendars, shipped = _d128_calendars_and_catalogue
    cal_a = calendars["soybean-winter-fallow"]
    cal_b = calendars["wheat-soybean-maize"]
    start, end = dt.date(2020, 7, 1), dt.date(2023, 6, 30)

    # On the 205-record shipped catalogue, Rotation B resolves every daily flag as a bool.
    shipped_living_map = flags_by_rotation_from_calendars(
        {
            ("soybean-winter-fallow", "phase_0"): cal_a,
            ("wheat-soybean-maize", "phase_0"): cal_b,
        },
        start_date=start,
        end_date=end,
        parameters=shipped,
    )
    shipped_flags_b = shipped_living_map[("wheat-soybean-maize", "phase_0")]
    assert len(shipped_flags_b) == (end - start).days + 1
    assert all(isinstance(flag, bool) for flag in shipped_flags_b.values())
    assert any(flag is True for flag in shipped_flags_b.values())
    assert any(flag is False for flag in shipped_flags_b.values())
    assert shipped_flags_b == water_living_crop.live_crop_by_day(
        cal_b, start, end, parameters=shipped
    )
    (shipped_order,) = erosion_orders(
        shipped_living_map, MONTHLY_EROSIVITY, start_month=cal_a.ag_year_start.month
    )
    assert shipped_order.order is not None
    assert shipped_order.means is not None
    assert shipped_order.reason is None

    # Removing wheat/maize stage lengths still preserves Missing(MISSING_INPUT) without filling.
    stage_ids = frozenset(
        {
            "fao56_stage_length_initial",
            "fao56_stage_length_development",
            "fao56_stage_length_mid",
            "fao56_stage_length_late",
        }
    )
    without_wheat_maize = {
        key: rec
        for key, rec in shipped.items()
        if not (
            rec.get("id") in stage_ids
            and rec.get("scope", {}).get("crop") in {"wheat", "maize"}
        )
    }
    living_map = flags_by_rotation_from_calendars(
        {
            ("soybean-winter-fallow", "phase_0"): cal_a,
            ("wheat-soybean-maize", "phase_0"): cal_b,
        },
        start_date=start,
        end_date=end,
        parameters=without_wheat_maize,
    )
    flags_b = living_map[("wheat-soybean-maize", "phase_0")]
    assert any(
        isinstance(flag, Missing) and flag.reason == "MISSING_INPUT"
        for flag in flags_b.values()
    )
    # Soybean and fallow days remain resolved booleans even though wheat/maize are missing.
    assert any(flag is True for flag in flags_b.values())
    assert any(flag is False for flag in flags_b.values())

    (order,) = erosion_orders(
        living_map, MONTHLY_EROSIVITY, start_month=cal_a.ag_year_start.month
    )
    assert order.order is None
    assert order.means is None
    assert "'wheat-soybean-maize'" in order.reason
    assert "MISSING_INPUT" in order.reason


def test_d128_rotation_a_shipped_and_rotation_b_placeholder_compare_across_phases(
    _d128_calendars_and_catalogue,
):
    calendars, shipped = _d128_calendars_and_catalogue
    cal_a = calendars["soybean-winter-fallow"]
    cal_b = calendars["wheat-soybean-maize"]

    augmented = _placeholder_stage_catalogue(
        _PLACEHOLDER_ROTATION_B_STAGE_LENGTHS, replace_in=shipped
    )
    assert check_catalogue(augmented) == []

    start, end = dt.date(2020, 7, 1), dt.date(2023, 6, 30)
    phases_b = list_phases(cal_b)
    assert len(phases_b) >= 2

    calendar_map = {}
    for phase in phases_b[:2]:
        scenario_id = f"phase_{phase}"
        calendar_map[("soybean-winter-fallow", scenario_id)] = cal_a
        calendar_map[("wheat-soybean-maize", scenario_id)] = phase_calendar(cal_b, phase)

    living_map = flags_by_rotation_from_calendars(
        calendar_map, start_date=start, end_date=end, parameters=augmented
    )
    assert all(
        isinstance(flag, bool)
        for flags in living_map.values()
        for flag in flags.values()
    )

    orders = erosion_orders(
        living_map, MONTHLY_EROSIVITY, start_month=cal_a.ag_year_start.month
    )
    assert [item.scenario_id for item in orders] == ["phase_0", "phase_1"]
    assert all(item.order is not None and item.reason is None for item in orders)

    # Compare against a PLACEHOLDER ResultsTable with equal (D158-style) soil_loss.
    tied_rows = [
        ResultsTableRow(
            rotation_id=rot_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=2.0,
            unit="t ha-1 yr-1",
            range_missing=Missing(reason="NOT_AVAILABLE", detail=SOURCE),
            provenance="DERIVED",
            source=SOURCE,
        )
        for scenario_id in ("phase_0", "phase_1")
        for rot_id in ("soybean-winter-fallow", "wheat-soybean-maize")
        for ag_year in (2020, 2021, 2022)
    ]
    report = compare_with_soil_loss(
        living_map,
        MONTHLY_EROSIVITY,
        ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=tied_rows),
        start_month=cal_a.ag_year_start.month,
    )
    assert [item.outcome for item in report] == [
        "no order from the full method",
        "no order from the full method",
    ]
    assert all(
        (item.trivial_rotations_ordered, item.full_rotations_ordered) == (2, 0)
        for item in report
    )
