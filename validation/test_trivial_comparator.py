"""Acceptance test of the trivial comparator of the decision (entry D0 of
``docs/VALIDATION.md``; unit l0/trivial-comparator-d0, issue #291).

EXAMPLE DATA. Every table below is written by hand for this test. Its
numbers mean nothing: they describe no real place, field, crop or producer,
and every source string says PLACEHOLDER. They are chosen only so that the
order counted by hand, and the order of the full decision, can be read off
them line by line.

Run from the repository root: ``python -m pytest validation/test_trivial_comparator.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from contracts.results.models import Missing, Range, ResultsTable, ResultsTableRow
from validation import trivial_comparator
from validation.trivial_comparator import (
    compare_with_decision,
    decision_order,
    trivial_orders,
)

CASE_ID = "example-case-d0"
FIELD_ID = "example-field-d0"
SOURCE = "PLACEHOLDER_example_data_written_by_hand_for_entry_D0"
KIND = "PLACEHOLDER_kind"
YEARS = (2020, 2021, 2022)

# --- the hand-made table, scenario s1 --------------------------------------------
#
# Soil loss (t ha-1 yr-1, lower is better), value [low, high] per year:
#   A: 9.0 [8.8, 9.2]   8.0 [7.8, 8.2]   10.0 [9.8, 10.2]
#   B: 5.0 [4.8, 5.2]   4.0 [3.8, 4.2]    6.0 [5.8, 6.2]
#   C: 7.0 [6.8, 7.2]   6.0 [5.8, 6.2]    8.0 [7.8, 8.2]
SOIL = {
    "A": ((9.0, 8.8, 9.2), (8.0, 7.8, 8.2), (10.0, 9.8, 10.2)),
    "B": ((5.0, 4.8, 5.2), (4.0, 3.8, 4.2), (6.0, 5.8, 6.2)),
    "C": ((7.0, 6.8, 7.2), (6.0, 5.8, 6.2), (8.0, 7.8, 8.2)),
}
# Water deficit exposure (dimensionless, higher is better), one value per
# agricultural year:
#   A: 0.60 [0.50, 0.70]   0.70 [0.60, 0.80]   0.80 [0.70, 0.90]
#   B: 0.65 [0.55, 0.75]   0.75 [0.65, 0.85]   0.85 [0.75, 0.95]
#   C: 0.30 [0.25, 0.35]   0.40 [0.35, 0.45]   0.50 [0.45, 0.55]
WATER = {
    "A": ((0.60, 0.50, 0.70), (0.70, 0.60, 0.80), (0.80, 0.70, 0.90)),
    "B": ((0.65, 0.55, 0.75), (0.75, 0.65, 0.85), (0.85, 0.75, 0.95)),
    "C": ((0.30, 0.25, 0.35), (0.40, 0.35, 0.45), (0.50, 0.45, 0.55)),
}
# Soil carbon trend (t C ha-1 yr-1, higher is better), one value per
# rotation, model amg, end minus start:
#   A: -0.4 [-0.5, -0.3]   B: 0.3 [0.2, 0.4]   C: 0.5 [0.45, 0.55]
CARBON = {"A": (-0.4, -0.5, -0.3), "B": (0.3, 0.2, 0.4), "C": (0.5, 0.45, 0.55)}

# --- the order counted by hand -----------------------------------------------------
#
# Soil loss, mean over the three agricultural years, ranges ignored:
#   A: (9.0 + 8.0 + 10.0) / 3 = 27.0 / 3 = 9.0
#   B: (5.0 + 4.0 + 6.0) / 3  = 15.0 / 3 = 5.0
#   C: (7.0 + 6.0 + 8.0) / 3  = 21.0 / 3 = 7.0
#   Lower is better: 5.0 < 7.0 < 9.0, so the order, best first, is B, C, A.
HAND_SOIL_MEANS = {"A": 9.0, "B": 5.0, "C": 7.0}
HAND_SOIL_ORDER = ("B", "C", "A")
# Water, mean over the three agricultural years, ranges ignored:
#   A: (0.60 + 0.70 + 0.80) / 3 = 2.10 / 3 = 0.70
#   B: (0.65 + 0.75 + 0.85) / 3 = 2.25 / 3 = 0.75
#   C: (0.30 + 0.40 + 0.50) / 3 = 1.20 / 3 = 0.40
#   Higher is better: 0.75 > 0.70 > 0.40, so the order, best first, is B, A, C.
HAND_WATER_MEANS = {"A": 0.70, "B": 0.75, "C": 0.40}
HAND_WATER_ORDER = ("B", "A", "C")
# Soil carbon trend: one value per rotation, on the time basis 'rotation',
# not 'ag_year'. There is no mean over agricultural years, and entry D0
# gives no rule for it: no order (OPEN).
#
# The order of the full decision, read from the ranges of the differences
# (D92: [b_low - a_high, b_high - a_low], second minus first):
#   Soil loss. B - A: 2020 [4.8 - 9.2, 5.2 - 8.8] = [-4.4, -3.6]; 2021
#   [-4.4, -3.6]; 2022 [-4.4, -3.6]: wholly better for B in every year.
#   C - A: [-2.4, -1.6] in every year: wholly better for C. C - B: [1.6, 2.4]
#   in every year: wholly worse for C, so B is ahead of C. Every pair is
#   separated: B, C, A, the same as the trivial order.
#   Water. B - A: 2020 [0.55 - 0.70, 0.75 - 0.50] = [-0.15, 0.25], which
#   crosses zero: A and B are not separated, so the full decision gives no
#   order for water, while the trivial comparator gives B, A, C.
#   Carbon. B - A [0.2 + 0.3, 0.4 + 0.5] = [0.5, 0.9]; C - B [0.45 - 0.4,
#   0.55 - 0.2] = [0.05, 0.35]; C - A [0.75, 1.05]: every pair separated,
#   C, B, A. The trivial comparator gives none (time basis).
HAND_DECISION_CARBON_ORDER = ("C", "B", "A")


def soil_row(rotation_id, scenario_id, ag_year, entry):
    if entry is None:
        return ResultsTableRow(
            rotation_id=rotation_id, scenario_id=scenario_id, time_basis="ag_year",
            ag_year=ag_year, indicator="soil_loss", direction="lower_is_better",
            value=None, unit="t ha-1 yr-1",
            missing=Missing(reason="NO_COVERAGE", detail="example data: year left out"),
        )
    value, low, high = entry
    return ResultsTableRow(
        rotation_id=rotation_id, scenario_id=scenario_id, time_basis="ag_year",
        ag_year=ag_year, indicator="soil_loss", direction="lower_is_better",
        value=value, unit="t ha-1 yr-1", range=Range(low=low, high=high, kind=KIND),
        provenance="DERIVED", source=SOURCE,
    )


def water_row(rotation_id, scenario_id, ag_year, entry):
    value, low, high = entry
    return ResultsTableRow(
        rotation_id=rotation_id, scenario_id=scenario_id, time_basis="ag_year",
        ag_year=ag_year, indicator="water_deficit_exposure", direction="higher_is_better",
        value=value, unit="dimensionless", range=Range(low=low, high=high, kind=KIND),
        provenance="SIMULATED", source=SOURCE,
    )


def carbon_row(rotation_id, scenario_id, entry):
    value, low, high = entry
    return ResultsTableRow(
        rotation_id=rotation_id, scenario_id=scenario_id, time_basis="rotation",
        indicator="soil_carbon_trend", direction="higher_is_better", value=value,
        unit="t C ha-1 yr-1", carbon_model="amg", computation="end_minus_start",
        range=Range(low=low, high=high, kind=KIND), provenance="SIMULATED", source=SOURCE,
    )


def scenario_rows(scenario_id, soil=SOIL, water=WATER, carbon=CARBON):
    rows = []
    for rotation_id in sorted(soil):
        for ag_year, entry in zip(YEARS, soil[rotation_id]):
            rows.append(soil_row(rotation_id, scenario_id, ag_year, entry))
        if water is not None:
            for ag_year, entry in zip(YEARS, water[rotation_id]):
                rows.append(water_row(rotation_id, scenario_id, ag_year, entry))
        if carbon is not None:
            rows.append(carbon_row(rotation_id, scenario_id, carbon[rotation_id]))
    return rows


def table(rows):
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


def by_indicator(items):
    return {item.indicator: item for item in items}


# --- (a) the order counted by hand -------------------------------------------------


def test_the_trivial_order_is_the_one_counted_by_hand():
    orders = by_indicator(trivial_orders(table(scenario_rows("s1"))))
    assert set(orders) == {"soil_loss", "water_deficit_exposure", "soil_carbon_trend"}

    soil = orders["soil_loss"]
    assert soil.scenario_id == "s1"
    assert soil.direction == "lower_is_better"
    assert dict(soil.means) == pytest.approx(HAND_SOIL_MEANS)
    assert soil.order == HAND_SOIL_ORDER
    assert soil.reason is None

    water = orders["water_deficit_exposure"]
    assert water.direction == "higher_is_better"
    assert dict(water.means) == pytest.approx(HAND_WATER_MEANS)
    assert water.order == HAND_WATER_ORDER
    assert water.reason is None


def test_the_order_ignores_ranges():
    # The same values with every range widened tenfold give the same order.
    wide = {
        rotation_id: tuple((v, v - 10 * (v - lo), v + 10 * (hi - v)) for v, lo, hi in entries)
        for rotation_id, entries in SOIL.items()
    }
    orders = by_indicator(trivial_orders(table(scenario_rows("s1", soil=wide))))
    assert orders["soil_loss"].order == HAND_SOIL_ORDER


def test_an_indicator_not_on_the_agricultural_year_gets_no_order():
    carbon = by_indicator(trivial_orders(table(scenario_rows("s1"))))["soil_carbon_trend"]
    assert carbon.order is None
    assert carbon.means is None
    assert "time basis" in carbon.reason and "OPEN" in carbon.reason


# --- (b) the report against the full decision -----------------------------------


def test_the_report_states_per_indicator_whether_the_orders_are_equal():
    report = by_indicator(compare_with_decision(table(scenario_rows("s1"))))

    soil = report["soil_loss"]
    assert soil.decision.order == HAND_SOIL_ORDER
    assert soil.outcome == "equal"

    # A and B are not separated on water: the full decision gives no order,
    # and the report says so instead of "equal" or "different".
    water = report["water_deficit_exposure"]
    assert water.trivial.order == HAND_WATER_ORDER
    assert water.decision.order is None
    assert "'A' and 'B'" in water.decision.reason
    assert water.outcome == "no order from the full decision"

    carbon = report["soil_carbon_trend"]
    assert carbon.decision.order == HAND_DECISION_CARBON_ORDER
    assert carbon.trivial.order is None
    assert carbon.outcome == "no order from the trivial comparator"

    assert all(item.outcome != "different" for item in report.values())


# --- (d) what entry D0 does not say: no order, with the reason --------------------


def test_a_missing_year_gives_no_order_and_never_a_zero():
    soil = {rotation_id: list(entries) for rotation_id, entries in SOIL.items()}
    soil["B"][1] = None  # B has no soil-loss value in 2021 (NO_COVERAGE)
    report = by_indicator(compare_with_decision(table(scenario_rows("s1", soil=soil))))
    item = report["soil_loss"]
    assert item.trivial.order is None
    assert item.trivial.means is None  # no mean is taken over a filled or zeroed year
    assert "'B' in 2021 (NO_COVERAGE)" in item.trivial.reason
    assert "never filled or taken as zero" in item.trivial.reason
    # The full decision judges only the cells with a value on both sides
    # (D59, D6): the two years left still separate every pair, B, C, A.
    assert item.decision.order == HAND_SOIL_ORDER
    assert item.outcome == "no order from the trivial comparator"


def test_a_tie_of_two_means_gives_no_order():
    # A: 5.0 and 7.0, mean 6.0; B: 6.0 and 6.0, mean 6.0. The full decision:
    # B - A 2020 [5.8 - 5.2, 6.2 - 4.8] = [0.6, 1.4] (worse for B), 2021
    # [5.8 - 7.2, 6.2 - 6.8] = [-1.4, -0.6] (better for B): not separated.
    rows = []
    for rotation_id, entries in {
        "A": ((5.0, 4.8, 5.2), (7.0, 6.8, 7.2)),
        "B": ((6.0, 5.8, 6.2), (6.0, 5.8, 6.2)),
    }.items():
        for ag_year, entry in zip(YEARS, entries):
            rows.append(soil_row(rotation_id, "s1", ag_year, entry))
    item = compare_with_decision(table(rows))[0]
    assert dict(item.trivial.means) == {"A": 6.0, "B": 6.0}
    assert item.trivial.order is None
    assert "equal" in item.trivial.reason and "tie" in item.trivial.reason
    assert item.decision.order is None
    assert item.outcome == "no order from either"


def test_a_single_rotation_gives_no_order():
    rows = [soil_row("A", "s1", ag_year, entry) for ag_year, entry in zip(YEARS, SOIL["A"])]
    item = compare_with_decision(table(rows))[0]
    assert item.trivial.order is None and "one rotation" in item.trivial.reason
    assert item.decision.order is None and "one rotation" in item.decision.reason
    assert item.outcome == "no order from either"


def test_each_scenario_is_read_on_its_own():
    # s2 swaps the soil loss of B and C, so its order is C, B, A; nothing is
    # ordered across s1 and s2 (D166).
    swapped = {"A": SOIL["A"], "B": SOIL["C"], "C": SOIL["B"]}
    two = table(scenario_rows("s1") + scenario_rows("s2", soil=swapped))
    orders = {(item.scenario_id, item.indicator): item for item in trivial_orders(two)}
    assert {scenario for scenario, _ in orders} == {"s1", "s2"}
    assert orders[("s1", "soil_loss")].order == ("B", "C", "A")
    assert orders[("s2", "soil_loss")].order == ("C", "B", "A")
    s2_alone = table(scenario_rows("s2", soil=swapped))
    assert decision_order(s2_alone, "s2", "soil_loss").order == ("C", "B", "A")
    report = {(item.scenario_id, item.indicator): item for item in compare_with_decision(two)}
    assert report[("s2", "soil_loss")].outcome == "equal"


# --- the functions are pure and hold no value of the method -----------------------


def test_the_module_reads_no_file_clock_or_network_and_holds_no_number():
    tree = ast.parse(Path(trivial_comparator.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "itertools", "dataclasses", "fractions", "typing",
                        "contracts", "decision"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "input", "eval", "exec"}
    numbers = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }
    assert numbers <= {0, 1, 2}  # counting only: no threshold, no tolerance
