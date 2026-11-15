"""Acceptance test of the order between systems (entry E2 of
``docs/VALIDATION.md``; decision D225 of issue #77; unit
l0/validation-e2-d225, issue #346).

EXAMPLE DATA. The tables and the expected orders below are written by hand
for this test. Their numbers mean nothing: they describe no real place,
field, crop, climate or producer, and every source string says PLACEHOLDER.
They are chosen only so that each order can be counted by hand line by line.
No expected order here is an order of the science: each is an input chosen
so that the report has something to state.

Run from the repository root: ``python -m pytest validation/test_order_between_systems.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from contracts.results.models import Missing, ResultsTable, ResultsTableRow
from validation import order_between_systems
from validation.order_between_systems import compare_with_expected_order
from validation.trivial_comparator import trivial_orders

CASE_ID = "example-case-e2"
FIELD_ID = "example-field-e2"
SOURCE = "PLACEHOLDER_example_data_written_by_hand_for_entry_E2"
YEARS = (2020, 2021, 2022)

# Soil loss by rotation and agricultural year (example data), lower is better.
SOIL = {
    "A": (3.0, 1.0, 2.0),
    "B": (5.0, 3.0, 4.0),
    "C": (1.0, 2.0, 0.0),
}
# --- the order counted by hand -----------------------------------------------------
#
# Means over the three agricultural years: A (3 + 1 + 2) / 3 = 2.0,
# B (5 + 3 + 4) / 3 = 4.0, C (1 + 2 + 0) / 3 = 1.0. Lower is better, so the
# order, best first, is C, A, B.
HAND_MEANS = {"A": 2.0, "B": 4.0, "C": 1.0}
HAND_ORDER = ("C", "A", "B")
# Another order of the same three rotations, given as the expected one.
OTHER_ORDER = ("A", "C", "B")


def soil_row(rotation_id, scenario_id, ag_year, value):
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
            missing=Missing(reason="NO_COVERAGE", detail="example data: year left out"),
        )
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range_missing=Missing(reason="NOT_AVAILABLE", detail="example data"),
        provenance="DERIVED",
        source=SOURCE,
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
        range_missing=Missing(reason="NOT_AVAILABLE", detail="example data"),
        provenance="SIMULATED",
        source=SOURCE,
    )


def soil_rows(soil=SOIL, scenario_id="phase_1"):
    return [
        soil_row(rotation_id, scenario_id, ag_year, value)
        for rotation_id, values in soil.items()
        for ag_year, value in zip(YEARS, values, strict=True)
    ]


def table(rows):
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# --- (a) the order counted by hand, and (b) the report against the expected order ---


def test_the_order_is_the_one_of_d0_counted_by_hand_and_the_report_says_equal():
    given = table(soil_rows())
    (item,) = compare_with_expected_order(given, HAND_ORDER)
    assert item.scenario_id == "phase_1"
    # The order is the one of the reading of entry D0, not a second one.
    (of_d0,) = [o for o in trivial_orders(given) if o.indicator == "soil_loss"]
    assert item.full == of_d0
    assert item.full.order == HAND_ORDER
    assert dict(item.full.means) == pytest.approx(HAND_MEANS)
    assert (item.outcome, item.reason) == ("equal", None)
    assert item.expected == HAND_ORDER
    assert item.rotations_ordered == 3


def test_a_different_expected_order_is_reported_different():
    (item,) = compare_with_expected_order(table(soil_rows()), OTHER_ORDER)
    assert item.full.order == HAND_ORDER
    assert (item.outcome, item.reason) == ("different", None)
    assert item.rotations_ordered == 3


def test_each_scenario_and_phase_is_compared_on_its_own():
    # Phase 2 gives A the soil loss of C and C that of A: order A, C, B.
    swapped = {"A": SOIL["C"], "B": SOIL["B"], "C": SOIL["A"]}
    rows = soil_rows() + soil_rows(swapped, scenario_id="phase_2")
    items = compare_with_expected_order(table(rows), HAND_ORDER)
    assert [(i.scenario_id, i.full.order, i.outcome) for i in items] == [
        ("phase_1", HAND_ORDER, "equal"),
        ("phase_2", ("A", "C", "B"), "different"),
    ]


# --- no order, with the reason -----------------------------------------------------


def test_the_d158_tie_gives_no_order():
    # As D158 makes it today with the single declared C: every rotation the
    # same soil loss in every year.
    tied = {rotation_id: (2.0, 2.0, 2.0) for rotation_id in SOIL}
    (item,) = compare_with_expected_order(table(soil_rows(tied)), HAND_ORDER)
    assert item.full.order is None
    assert item.outcome == "no order from the full method"
    assert "equal" in item.reason and item.reason == item.full.reason
    assert item.rotations_ordered == 0


def test_a_missing_year_gives_no_order_and_never_a_zero():
    gap = dict(SOIL)
    gap["A"] = (3.0, None, 2.0)
    (item,) = compare_with_expected_order(table(soil_rows(gap)), HAND_ORDER)
    assert item.full.order is None and item.full.means is None
    assert item.outcome == "no order from the full method"
    assert "'A' in 2021 (NO_COVERAGE)" in item.reason
    assert "never filled or taken as zero" in item.reason
    assert item.rotations_ordered == 0


def test_a_single_rotation_gives_no_order():
    (item,) = compare_with_expected_order(table(soil_rows({"A": SOIL["A"]})), ("A",))
    assert item.full.order is None
    assert item.outcome == "no order from the full method"
    assert "one rotation" in item.reason
    assert item.rotations_ordered == 0


def test_a_scenario_without_soil_loss_gives_no_order():
    # Phase 2 holds water values only (the table needs the same cells for
    # every rotation, so every rotation has them).
    rows = soil_rows() + [
        water_row(rotation_id, "phase_2", ag_year, 0.5)
        for rotation_id in SOIL
        for ag_year in YEARS
    ]
    items = compare_with_expected_order(table(rows), HAND_ORDER)
    assert [i.scenario_id for i in items] == ["phase_1", "phase_2"]
    without = items[1]
    assert without.full is None
    assert without.outcome == "no order from the full method"
    assert "holds no 'soil_loss' of scenario 'phase_2'" in without.reason
    assert without.rotations_ordered == 0


def test_other_indicators_are_not_read():
    # Water values ordering the rotations B, A, C (higher is better) change
    # nothing: only soil_loss is read.
    water = {"A": 0.5, "B": 0.9, "C": 0.1}
    rows = soil_rows() + [
        water_row(rotation_id, "phase_1", ag_year, value)
        for rotation_id, value in water.items()
        for ag_year in YEARS
    ]
    assert compare_with_expected_order(
        table(rows), HAND_ORDER
    ) == compare_with_expected_order(table(soil_rows()), HAND_ORDER)


# --- the expected order and the table do not name the same rotations (OPEN 1) ----


def test_an_expected_order_naming_a_rotation_the_table_lacks_is_not_compared():
    (item,) = compare_with_expected_order(table(soil_rows()), ("C", "A", "D"))
    assert item.outcome == "not compared"
    assert "['A', 'C', 'D']" in item.reason and "['A', 'B', 'C']" in item.reason
    assert "OPEN 1" in item.reason
    # The order of the full soil loss is still reported, with its count.
    assert item.full.order == HAND_ORDER and item.rotations_ordered == 3
    # The reverse: the table holds a rotation the expected order lacks.
    (item,) = compare_with_expected_order(table(soil_rows()), ("C", "A"))
    assert item.outcome == "not compared"
    assert "['A', 'C']" in item.reason


# --- what the inputs may be ----------------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "error"),
    [
        ("CAB", TypeError),
        (None, TypeError),
        (("C", 1, "B"), TypeError),
        (("C", "", "B"), TypeError),
        ((), ValueError),
        (("C", "A", "C"), ValueError),
    ],
    ids=["text", "None", "integer", "empty text", "empty order", "twice"],
)
def test_a_malformed_expected_order_raises(expected, error):
    with pytest.raises(error, match="expected"):
        compare_with_expected_order(table(soil_rows()), expected)


def test_a_table_that_is_not_a_results_table_raises():
    with pytest.raises(TypeError, match="ResultsTable"):
        compare_with_expected_order(table(soil_rows()).model_dump(), HAND_ORDER)


# --- the functions are pure and hold no value of the method -----------------------


def test_the_module_reads_no_file_clock_or_network_and_holds_no_number():
    tree = ast.parse(Path(order_between_systems.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "collections",
        "dataclasses",
        "typing",
        "contracts",
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
    assert numbers <= {0, 1}  # counting only: no threshold, no value of the method
