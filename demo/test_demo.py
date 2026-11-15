"""Acceptance test of the demo (unit l2/thin-matrix-decision, issue #240).

The table under test is the matrix approved by the designer of the case on 14 November
2026, written out again below straight from the brief, so the test reads
the brief and not the module it tests. Every count, state, rank and
coverage is compared exactly; the float values of the differences and of
their ranges are compared with ``pytest.approx`` at the default
tolerance, and where a bound is load-bearing (a range touching zero) it
is compared exactly against the arithmetic of D92 that produces it.

The designer-read expectations of the brief split in two on this matrix.
The ones the decided machinery reproduces are asserted as the brief
states them: A 1 of 3 years within the limit with 2021 at the limit
inclusive (D90); the point-sign count of A vs B at s1 (better 3, worse
0, equal 0, one missing side 2023) and the coverage 3 of 4 (D87, D91);
the 2022 range of A vs B at s3, [8.6 - 9.5, 9.4 - 8.7], crossing zero;
the carbon difference of A vs B, +0.7 [0.5, 0.9], wholly better for B;
the zero differences of B vs C at every shared soil year; water not
evaluated anywhere; no year counts for the carbon trend (D95).

The ones the machinery gives differently are asserted as the machinery
gives them, each marked DIVERGENCE with the decisions that force the
value (all four come from the worst-case interval arithmetic of D92 over
the approved ranges, read by D93 and D98):

1. A vs B, soil loss, 2021: the range [6.2 - 7.4, 6.8 - 6.6] =
   [-1.2, +0.2] crosses zero, so the cell blocks in EVERY scenario; the
   pair is "Not separated: within uncertainty" in each scenario, and the
   tipping point the brief reads between s2 and s3 does not appear (the
   state never changes). Over the set {s1, s2, s3} the pair is "Not
   robust across scenarios", as the brief reads it (D166, unit
   l2/decision-rule-d165-d176).
2. B vs C, carbon: the range [0.4 - 0.4, 0.6 - 0.2] = [0.0, +0.4]
   touches zero from the side that is not worse, so the cell is not a
   strict improvement and, under D165, does not block; the pair is still
   not the brief's "Robust preference (C)", because its soil-loss cells
   cross zero (3. below). The brief's range [0.1, 0.3] is not what D92
   gives on the approved ranges [0.2, 0.4] and [0.4, 0.6].
3. B vs C, soil loss: the differences are zero, but the ranges cross
   zero and the pair as a whole is never "Identical" (its carbon
   difference is +0.2); the brief's "Identical" is a per-indicator
   reading the machinery and the contract do not give.
4. The counts by year: B and C hold the valued 2023 row the matrix
   carries (6.8), so they count 4 of 4 at s1 and s2 and 3 of 4 at s3
   and the range across scenarios is 3 to 4 (minimum at s3); the brief
   reads 3 of 3, 2 of 3 and 2 to 3, the counts of a table without that
   2023 row.

Run from the repository root: ``python -m pytest demo/``.
"""

from __future__ import annotations

import pytest

from contracts.decision_output import DecisionOutput
from contracts.results.models import ResultsTable
from decision.functions import (
    NOT_ROBUST_ACROSS_SCENARIOS,
    NOT_SEPARATED_WITHIN_UNCERTAINTY,
    indicator_ranking,
    measurement_priority,
    never_preferred_less,
    pair_counts,
    pair_state,
    paired_differences,
    tipping_point,
)

from demo import matrix, run

# --- the approved matrix, straight from the brief (issue #240) -----------------
#
# Soil loss, (value, low, high) per rotation and agricultural year; the
# 2022 cell of B and C is the uncertain input u, per scenario; A holds
# no 2023 value.
APPROVED_SOIL: dict[str, dict[int, tuple[float, float, float]]] = {
    "A": {2020: (8.2, 7.8, 8.6), 2021: (7.0, 6.6, 7.4), 2022: (9.1, 8.7, 9.5)},
    "B": {2020: (6.1, 5.8, 6.4), 2021: (6.5, 6.2, 6.8), 2023: (6.8, 6.5, 7.1)},
    "C": {2020: (6.1, 5.8, 6.4), 2021: (6.5, 6.2, 6.8), 2023: (6.8, 6.5, 7.1)},
}
APPROVED_U_2022: dict[str, tuple[float, float, float]] = {
    "s1": (5.0, 4.7, 5.3),
    "s2": (7.0, 6.6, 7.4),
    "s3": (9.0, 8.6, 9.4),
}
APPROVED_CARBON: dict[str, tuple[float, float, float]] = {
    "A": (-0.4, -0.5, -0.3),
    "B": (0.3, 0.2, 0.4),
    "C": (0.5, 0.4, 0.6),
}
LIMIT_OF_SOIL_LOSS = 7.0


def soil_of(
    rotation_id: str, scenario_id: str, ag_year: int
) -> tuple[float, float, float] | None:
    """The approved soil loss of one cell, or None where the matrix has none."""
    if rotation_id in ("B", "C") and ag_year == 2022:
        return APPROVED_U_2022[scenario_id]
    return APPROVED_SOIL[rotation_id].get(ag_year)


def rows_of(table: ResultsTable, rotation_id: str, scenario_id: str) -> dict:
    """The rows of one rotation and scenario, by (indicator, ag_year, model)."""
    return {
        (row.indicator, row.ag_year, row.carbon_model): row
        for row in table.rows
        if row.rotation_id == rotation_id and row.scenario_id == scenario_id
    }


def scenario_table(table: ResultsTable, scenario_id: str) -> ResultsTable:
    """The rows of one scenario, as a table of their own."""
    return ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[row for row in table.rows if row.scenario_id == scenario_id],
    )


def differences_of(table: ResultsTable, first: str, second: str) -> dict:
    """The paired differences of one pair, by (scenario, indicator, year)."""
    return {
        (d.scenario_id, d.indicator, d.ag_year): d
        for d in paired_differences(table, first, second)
    }


def counts_of(table: ResultsTable, first: str, second: str) -> dict:
    """The cell counts of one pair, by (scenario, indicator)."""
    return {
        (c.scenario_id, c.indicator): c
        for c in pair_counts(
            table, first, second, equal_tolerance=matrix.EQUAL_TOLERANCE
        )
    }


TABLE = matrix.thin_matrix()


# --- the table is the approved matrix ------------------------------------------


def test_the_table_is_the_approved_matrix() -> None:
    assert (TABLE.case_id, TABLE.field_id) == ("example-case", "example-field-1")
    assert len(TABLE.rows) == 54  # 3 rotations x 3 scenarios x 6 cells
    for scenario_id in matrix.SCENARIOS:
        for rotation_id in matrix.ROTATIONS:
            rows = rows_of(TABLE, rotation_id, scenario_id)
            for ag_year in matrix.AG_YEARS:
                row = rows[("soil_loss", ag_year, None)]
                approved = soil_of(rotation_id, scenario_id, ag_year)
                assert (row.unit, row.direction) == ("t ha-1 yr-1", "lower_is_better")
                if approved is None:  # A, 2023: missing, never zero
                    assert row.value is None
                    assert row.missing is not None
                    assert row.missing.reason == "NO_COVERAGE"
                    assert row.provenance is None  # C4.1: no label when missing
                else:
                    assert row.provenance == "DERIVED"  # C4.6
                    value, low, high = approved
                    assert row.value == pytest.approx(value)
                    assert row.range is not None
                    assert (row.range.low, row.range.high) == (
                        pytest.approx(low),
                        pytest.approx(high),
                    )
            row = rows[("soil_carbon_trend", None, "amg")]
            value, low, high = APPROVED_CARBON[rotation_id]
            assert (row.unit, row.direction, row.provenance) == (
                "t C ha-1 yr-1",
                "higher_is_better",
                "SIMULATED",
            )
            assert (row.computation, row.time_basis) == ("end_minus_start", "rotation")
            assert row.value == pytest.approx(value)
            assert row.range is not None
            assert (row.range.low, row.range.high) == (
                pytest.approx(low),
                pytest.approx(high),
            )
            row = rows[("water_deficit_exposure", None, None)]
            assert row.value is None  # D61: missing, never zero
            assert row.missing is not None
            assert row.missing.reason == "NOT_AVAILABLE"
            assert (row.unit, row.direction) == ("dimensionless", "higher_is_better")


def test_the_limit_and_the_uncertain_input_are_the_approved_ones() -> None:
    assert matrix.SOIL_LOSS_LIMIT.limit == LIMIT_OF_SOIL_LOSS
    assert matrix.SOIL_LOSS_LIMIT.provenance == "DECLARED"
    assert set(matrix.LIMITS) == {"soil_loss"}  # no other limit is declared
    assert matrix.UNCERTAIN_INPUT.name == "u"
    assert matrix.UNCERTAIN_INPUT.unit == "t ha-1 yr-1"
    assert matrix.UNCERTAIN_INPUT.values == (
        (5.0, "s1"),
        (7.0, "s2"),
        (9.0, "s3"),
    )
    assert matrix.UNCERTAIN_INPUT.cell == (
        "B",
        "soil_loss",
        "ag_year",
        2022,
        None,
        None,
    )


# --- D1: the counts by year (D90, D94, D95) -------------------------------------


def test_the_counts_by_year() -> None:
    counts = run.counts_by_year(TABLE)
    # D94: one count per rotation, scenario, indicator; D95: the two
    # indicators on another time basis have no count of years at all.
    assert set(counts) == {
        (rotation, scenario, "soil_loss", None, None)
        for rotation in "ABC"
        for scenario in matrix.SCENARIOS
    }
    for scenario_id in matrix.SCENARIOS:
        # A: 1 of 3, the 2021 value sitting at the limit, inclusive (D90).
        a = counts[("A", scenario_id, "soil_loss", None, None)]
        assert (a.evaluated, a.within, a.outside) == (3, 1, 2)
        assert [(row.ag_year, row.missing.reason) for row in a.not_evaluated] == [
            (2023, "NO_COVERAGE")
        ]
        rows = rows_of(TABLE, "A", scenario_id)
        within = [
            (row.ag_year, row.value)
            for row in rows.values()
            if row.indicator == "soil_loss"
            and row.value is not None
            and row.value <= LIMIT_OF_SOIL_LOSS
        ]
        assert within == [(2021, 7.0)]  # at the limit, inclusive
        for rotation_id in ("B", "C"):
            # DIVERGENCE 4: the matrix carries the 2023 value of B and C
            # (6.8), so the machinery counts 4 of 4 at s1 and s2 and 3 of
            # 4 at s3; the brief reads 3 of 3 and 2 of 3.
            count = counts[(rotation_id, scenario_id, "soil_loss", None, None)]
            expected = (4, 4, 0) if scenario_id in ("s1", "s2") else (4, 3, 1)
            assert (count.evaluated, count.within, count.outside) == expected
            assert count.not_evaluated == ()
    # D90 at work: at s2 the 2022 value of B and C is 7.0, equal to the
    # limit, and counts within.
    b2022 = rows_of(TABLE, "B", "s2")[("soil_loss", 2022, None)].value
    assert b2022 == LIMIT_OF_SOIL_LOSS
    assert counts[("B", "s2", "soil_loss", None, None)].within == 4


# --- D96: the range across scenarios ---------------------------------------------


def test_the_ranges_across_scenarios() -> None:
    items = {item.rotation_id: item for item in run.ranges_across_scenarios()}
    assert set(items) == {"A", "B", "C"}
    # A: 1 to 1. The minimum ties at every scenario; the demo names the
    # first in the person's order — which one to name is OPEN (OPEN 11).
    assert (items["A"].minimum, items["A"].maximum) == (1, 1)
    assert items["A"].scenario_of_the_minimum == "s1"
    # DIVERGENCE 4: the brief reads 2 to 3; the machinery counts the 2023
    # value the matrix carries, so 3 to 4 — the minimum at s3, as the
    # brief also says.
    for rotation_id in ("B", "C"):
        item = items[rotation_id]
        assert (item.minimum, item.maximum) == (3, 4)
        assert item.scenario_of_the_minimum == "s3"
        assert item.missing is None


# --- D2 with D92: the paired differences -----------------------------------------


def test_the_differences_of_a_and_b_soil_loss() -> None:
    differences = differences_of(TABLE, "A", "B")
    for scenario_id in matrix.SCENARIOS:
        # 2020: wholly better for B.
        difference = differences[(scenario_id, "soil_loss", 2020)]
        assert difference.value == pytest.approx(6.1 - 8.2)
        assert difference.range is not None
        assert (difference.range.low, difference.range.high) == (
            pytest.approx(5.8 - 8.6),
            pytest.approx(6.4 - 7.8),
        )
        assert difference.range.high < 0.0
        # DIVERGENCE 1: 2021 crosses zero ([6.2 - 7.4, 6.8 - 6.6] =
        # [-1.2, +0.2]), so it is NOT wholly better for B at any scenario.
        difference = differences[(scenario_id, "soil_loss", 2021)]
        assert difference.value == pytest.approx(6.5 - 7.0)
        assert (difference.range.low, difference.range.high) == (
            pytest.approx(6.2 - 7.4),
            pytest.approx(6.8 - 6.6),
        )
        assert difference.range.low < 0.0 < difference.range.high
        # 2022: as the brief reads it — wholly better at s1 and s2, the
        # range [8.6 - 9.5, 9.4 - 8.7] crossing zero at s3.
        u, u_low, u_high = APPROVED_U_2022[scenario_id]
        difference = differences[(scenario_id, "soil_loss", 2022)]
        assert difference.value == pytest.approx(u - 9.1)
        assert (difference.range.low, difference.range.high) == (
            pytest.approx(u_low - 9.5),
            pytest.approx(u_high - 8.7),
        )
        if scenario_id == "s3":
            assert difference.range.low < 0.0 < difference.range.high
        else:
            assert difference.range.high < 0.0
        # 2023: the side of A holds no value; the difference is missing,
        # naming that side, and never zero.
        difference = differences[(scenario_id, "soil_loss", 2023)]
        assert difference.value is None
        assert difference.missing is not None
        assert difference.missing.reason == "MISSING_INPUT"
        assert "'A'" in difference.missing.detail


def test_the_differences_of_carbon() -> None:
    # (first value / range), then (second value / range), of each pair.
    pairs = {
        ("A", "B"): ((-0.4, -0.5, -0.3), (0.3, 0.2, 0.4)),
        ("A", "C"): ((-0.4, -0.5, -0.3), (0.5, 0.4, 0.6)),
    }
    for (first, second), ((a_value, a_low, a_high), (b_value, b_low, b_high)) in (
        pairs.items()
    ):
        # The brief reads A vs B, carbon: +0.7 [0.5, 0.9], wholly better
        # for B — and D92 agrees: [b_low - a_high, b_high - a_low] =
        # [0.2 - (-0.3), 0.4 - (-0.5)] = [0.5, 0.9].
        for scenario_id in matrix.SCENARIOS:
            difference = differences_of(TABLE, first, second)[
                (scenario_id, "soil_carbon_trend", None)
            ]
            assert difference.value == pytest.approx(b_value - a_value)
            assert difference.range is not None
            assert (difference.range.low, difference.range.high) == (
                pytest.approx(b_low - a_high),
                pytest.approx(b_high - a_low),
            )
            assert difference.range.low > 0.0  # wholly better, higher is better
    # DIVERGENCE 2: the brief reads B vs C, carbon: +0.2 [0.1, 0.3];
    # D92 on the approved ranges [0.2, 0.4] and [0.4, 0.6] gives
    # [0.4 - 0.4, 0.6 - 0.2] = [0.0, +0.4], which touches zero.
    for scenario_id in matrix.SCENARIOS:
        difference = differences_of(TABLE, "B", "C")[
            (scenario_id, "soil_carbon_trend", None)
        ]
        assert difference.value == pytest.approx(0.5 - 0.3)
        assert difference.range is not None
        assert difference.range.low == 0.4 - 0.4  # exactly zero: it touches
        assert difference.range.high == pytest.approx(0.6 - 0.2)
        assert difference.range.low == 0.0


def test_the_differences_of_b_and_c_soil_loss() -> None:
    # Zero at every shared cell, 2022 included (both sides are u) — as
    # the brief reads it. DIVERGENCE 3: the ranges of those zero
    # differences cross zero, so the cells are not separated, and the
    # pair as a whole is never "Identical" (see the states below).
    for scenario_id in matrix.SCENARIOS:
        differences = differences_of(TABLE, "B", "C")
        for ag_year in matrix.AG_YEARS:
            difference = differences[(scenario_id, "soil_loss", ag_year)]
            assert difference.value == 0.0
            assert difference.missing is None
            assert difference.range is not None
            assert difference.range.low < 0.0 < difference.range.high


def test_the_differences_of_water_are_missing_on_both_sides() -> None:
    for first, second in run.PAIRS:
        for scenario_id in matrix.SCENARIOS:
            difference = differences_of(TABLE, first, second)[
                (scenario_id, "water_deficit_exposure", None)
            ]
            assert difference.value is None  # never zero
            assert difference.missing is not None
            assert difference.missing.reason == "MISSING_INPUT"
            assert f"'{first}'" in difference.missing.detail
            assert f"'{second}'" in difference.missing.detail


def test_every_computed_difference_carries_its_range() -> None:
    # Every value of the matrix has a range of one kind, so D92 gives
    # every computed difference its range; nothing is range-missing.
    for first, second in run.PAIRS:
        for difference in paired_differences(TABLE, first, second):
            if difference.value is None:
                assert difference.range is None
                assert difference.range_missing is None
            else:
                assert difference.range is not None
                assert difference.range_missing is None


# --- D87 with D99 and D91: the counts of the cells of a pair ----------------------


def test_the_counts_of_the_cells_of_a_and_b() -> None:
    counts = counts_of(TABLE, "A", "B")
    # The brief's own reading: A vs B, soil loss, s1 — better 3, worse 0,
    # equal 0, one missing side (2023); coverage 3 of 4 (D91). The point
    # signs are the same at every scenario; the not-separated cells grow
    # from one (2021) to two (2021 and 2022) at s3.
    for scenario_id in matrix.SCENARIOS:
        count = counts[(scenario_id, "soil_loss")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (3, 0, 0, 1)
        assert (count.cells_compared, count.cells_of_the_pair) == (3, 4)
        # The carbon cell: wholly better for B at every scenario.
        count = counts[(scenario_id, "soil_carbon_trend")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (1, 0, 0, 0)
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == (1, 0, 0)
        assert (count.cells_compared, count.cells_of_the_pair) == (1, 1)
        # The water cell: a missing side, no cell compared.
        count = counts[(scenario_id, "water_deficit_exposure")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (0, 0, 0, 1)
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == (0, 0, 0)
        assert (count.cells_compared, count.cells_of_the_pair) == (0, 1)


def test_the_counts_of_the_cells_of_a_and_c() -> None:
    # C carries the soil values of B, so the counts of A vs C are those
    # of A vs B, cell for cell.
    counts = counts_of(TABLE, "A", "C")
    for scenario_id in matrix.SCENARIOS:
        count = counts[(scenario_id, "soil_loss")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (3, 0, 0, 1)
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == ((2, 0, 1) if scenario_id in ("s1", "s2") else (1, 0, 2))
        assert (count.cells_compared, count.cells_of_the_pair) == (3, 4)
        count = counts[(scenario_id, "soil_carbon_trend")]
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == (1, 0, 0)


def test_the_counts_of_the_cells_of_b_and_c() -> None:
    counts = counts_of(TABLE, "B", "C")
    for scenario_id in matrix.SCENARIOS:
        # Soil loss: four equal cells (the tolerance of "equal" is 0.0),
        # every one not separated by its crossing range (D99: the two
        # counts are shown apart — equal by sign, not separated by range).
        count = counts[(scenario_id, "soil_loss")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (0, 0, 4, 0)
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == (0, 0, 4)
        assert (count.cells_compared, count.cells_of_the_pair) == (4, 4)
        # DIVERGENCE 2: the carbon cell is better by the point value and
        # not separated by its touching range.
        count = counts[(scenario_id, "soil_carbon_trend")]
        assert (
            count.by_point_sign.better,
            count.by_point_sign.worse,
            count.by_point_sign.equal,
            count.by_point_sign.missing_side,
        ) == (1, 0, 0, 0)
        assert (
            count.by_range.strict_improvement,
            count.by_range.deterioration,
            count.by_range.not_separated,
        ) == (0, 0, 1)
        # Water: one cell, one missing side, nothing compared.
        count = counts[(scenario_id, "water_deficit_exposure")]
        assert count.by_point_sign.missing_side == 1
        assert count.cells_compared == 0


# --- D7: the states of the pairs (D74, D85, D93, D97, D98) ------------------------


def test_the_states_of_the_pairs_over_the_whole_set() -> None:
    states = {}
    for first, second in run.PAIRS:
        state = pair_state(TABLE, first, second)
        states[(first, second)] = state
        # D166: each scenario is read on its own and the set is "Not robust
        # across scenarios" unless every member is a robust preference. In
        # every scenario each pair is "Not separated: within uncertainty"
        # (DIVERGENCE 1: the 2021 cell of A vs B crosses zero; B vs C: its
        # soil-loss cells cross zero), so over {s1, s2, s3} the pair is "Not
        # robust across scenarios", as the brief reads it for A vs B. The
        # brief's "Robust preference (C)" stays a divergence (2.).
        assert state.state == NOT_ROBUST_ACROSS_SCENARIOS
        assert state.by_scenario == tuple(
            (scenario_id, NOT_SEPARATED_WITHIN_UNCERTAINTY)
            for scenario_id in matrix.SCENARIOS
        )
        # DIVERGENCE 3: B vs C is never "Identical" (D85): its carbon
        # difference (+0.2) is not zero.
        assert state.identical_rows is False
    assert states[("A", "B")].indicators_not_resolved == ("soil_loss",)
    assert states[("A", "C")].indicators_not_resolved == ("soil_loss",)
    # D165: the carbon cell of B vs C, [0.0, +0.4], touches zero from the
    # side that is not worse, so it does not block and its indicator is not
    # named; "indicators_not_resolved names only indicators with a blocking
    # cell".
    assert states[("B", "C")].indicators_not_resolved == ("soil_loss",)
    # Water never enters a state (D6): it is not named anywhere.
    assert all(
        "water_deficit_exposure" not in state.indicators_not_resolved
        for state in states.values()
    )


def test_the_states_of_the_pairs_at_each_scenario() -> None:
    # The state the tipping point reads (D3, D103): the state of the pair
    # in the one scenario that holds u at that value. DIVERGENCE 1: the
    # brief reads a robust preference at s1 and s2 that fails only at s3;
    # under D92 the 2021 cell blocks at every value, so the state is the
    # same at all three.
    for first, second in run.PAIRS:
        for scenario_id in matrix.SCENARIOS:
            state = pair_state(scenario_table(TABLE, scenario_id), first, second)
            assert state.state == NOT_SEPARATED_WITHIN_UNCERTAINTY


# --- D5: dominance --------------------------------------------------------------


def test_dominance_between_the_rotations() -> None:
    # Read on the point values (D156): B and C are never preferred
    # less than A (better at 2020, 2021, 2022 of every scenario and on
    # carbon), C is never preferred less than B (carbon), and no pair is
    # preferred the other way.
    expected = {
        (("A", "B"), True),
        (("B", "A"), False),
        (("A", "C"), True),
        (("C", "A"), False),
        (("B", "C"), True),
        (("C", "B"), False),
    }
    for (first, second), value in expected:
        assert never_preferred_less(TABLE, first, second) is value


# --- D6: what missing values give ------------------------------------------------


def test_water_is_not_evaluated_at_all() -> None:
    # The brief: "Water, every pair: Not evaluated, no state." The
    # machinery's reading is this one (D6): every value of the indicator
    # is missing, so no rotation enters the ranking; and the water
    # differences of every pair hold no value (asserted above), so water
    # enters no state. GAP: the contract has no per-indicator state of a
    # pair, and "Not evaluated" is not one of its state names (K1), so
    # this reading cannot travel as a PairState.
    water = indicator_ranking(TABLE, "water_deficit_exposure")
    assert water.every_value_missing is True
    assert water.rotations_with_a_value == frozenset()
    assert len(water.reasons) == 9  # 3 rotations x 3 scenarios, none zero
    assert {reason for _, reason in water.reasons} == {water.reasons[0][1]}
    soil = indicator_ranking(TABLE, "soil_loss")
    assert soil.every_value_missing is False
    assert soil.rotations_with_a_value == frozenset({"A", "B", "C"})
    assert len(soil.reasons) == 3  # A, 2023, one per scenario
    carbon = indicator_ranking(TABLE, "soil_carbon_trend")
    assert carbon.every_value_missing is False
    assert carbon.reasons == ()


# --- D3: the tipping point -------------------------------------------------------


def test_the_tipping_points() -> None:
    # DIVERGENCE 1: the brief reads the state of A vs B changing between
    # s2 and s3 (a bracket [7.0, 9.0]); under D92 the pair is "Not
    # separated: within uncertainty" at every admitted value, so no
    # bracket is reported, with the reason of D3. The pairs the brief
    # reads as unchanging (B vs C, robust at every value) give no bracket
    # as well — for the machinery's own reason.
    for first, second, point in run.tipping_points(TABLE):
        assert (first, second) in run.PAIRS
        assert point.input_name == "u"
        assert point.unit == "t ha-1 yr-1"
        assert point.states == (
            (5.0, NOT_SEPARATED_WITHIN_UNCERTAINTY),
            (7.0, NOT_SEPARATED_WITHIN_UNCERTAINTY),
            (9.0, NOT_SEPARATED_WITHIN_UNCERTAINTY),
        )
        assert point.bracket is None
        assert point.reason is not None
        assert "at every admitted value" in point.reason
        assert tipping_point(TABLE, first, second, matrix.UNCERTAIN_INPUT) == point


# --- D4: the measurement priority -------------------------------------------------


def test_the_measurement_priority() -> None:
    for first, second in run.PAIRS:
        priority = measurement_priority(
            TABLE, first, second, matrix.UNCERTAIN_INPUTS
        )
        # D103 and D166: the base state is the state over the whole admitted
        # set, each scenario read on its own.
        assert priority.base_state == NOT_ROBUST_ACROSS_SCENARIOS
        assert len(priority.items) == 1
        item = priority.items[0]
        # The values of u never change the state of any pair, so u holds
        # rank 2 on every pair (D4: an input whose values never change
        # the state ranks below one whose values do; here there is only
        # the one input, and it ties with itself).
        assert item.rank == 2
        assert item.input_name == "u"
        assert item.cell == ("B", "soil_loss", "ag_year", 2022, None, None)
        assert "never change the state" in item.why


# --- the decision output document -------------------------------------------------


def test_the_document_validates_and_roundtrips() -> None:
    document = run.build_decision_output(TABLE)
    assert isinstance(document, DecisionOutput)
    again = DecisionOutput.model_validate(document.model_dump())
    assert again == document
    assert (document.case_id, document.field_id) == ("example-case", "example-field-1")
    assert document.rotations == ["A", "B", "C"]
    assert document.scenarios == ["s1", "s2", "s3"]
    assert document.example_data is True


def test_the_document_carries_the_limits_and_tolerances() -> None:
    document = run.build_decision_output(TABLE)
    limits = {item.indicator: item.limit for item in document.limits}
    assert limits["soil_loss"].value == 7.0
    assert limits["soil_loss"].provenance == "DECLARED"
    assert limits["soil_loss"].range_missing is not None
    # D60: the limits not declared stay in the list, missing with their
    # reason and never zero.
    for indicator in ("water_deficit_exposure", "soil_carbon_trend"):
        assert limits[indicator].value is None
        assert limits[indicator].missing is not None
        assert limits[indicator].missing.reason == "NOT_DECLARED"
    tolerances = {item.indicator: item.tolerance for item in document.equal_tolerances}
    assert tolerances["soil_loss"].value == matrix.EQUAL_TOLERANCE
    assert tolerances["soil_loss"].provenance == "DECLARED"
    for indicator in ("water_deficit_exposure", "soil_carbon_trend"):
        assert tolerances[indicator].value is None
        assert tolerances[indicator].missing.reason == "NOT_DECLARED"


def test_the_document_carries_the_counts_and_their_ranges() -> None:
    document = run.build_decision_output(TABLE)
    counts = {count.key(): count for count in document.counts_by_year}
    assert len(counts) == 9  # D94: nothing across scenarios or models
    for scenario_id in matrix.SCENARIOS:
        assert (
            counts[("A", scenario_id, "soil_loss", None, None)].years_evaluated,
            counts[("A", scenario_id, "soil_loss", None, None)].years_within_limits,
        ) == (3, 1)
        for rotation_id in ("B", "C"):
            expected = (4, 4) if scenario_id in ("s1", "s2") else (4, 3)
            count = counts[(rotation_id, scenario_id, "soil_loss", None, None)]
            assert (count.years_evaluated, count.years_within_limits) == expected
    not_evaluated = counts[("A", "s1", "soil_loss", None, None)].not_evaluated
    assert [(row.ag_year, row.missing.reason) for row in not_evaluated] == [
        (2023, "NO_COVERAGE")
    ]
    ranges = {item.rotation_id: item for item in document.range_across_scenarios}
    range_a = ranges["A"]
    assert (
        range_a.minimum,
        range_a.maximum,
        range_a.scenario_of_the_minimum,
    ) == (1, 1, "s1")
    for rotation_id in ("B", "C"):
        item = ranges[rotation_id]
        assert (
            item.minimum,
            item.maximum,
            item.scenario_of_the_minimum,
        ) == (3, 4, "s3")


def test_the_document_carries_the_differences() -> None:
    document = run.build_decision_output(TABLE)
    assert len(document.paired_differences) == 54  # 3 pairs x 3 scenarios x 6 cells
    items = {
        (tuple(item.pair), item.cell()): item for item in document.paired_differences
    }
    carbon = items[
        (
            ("A", "B"),
            ("s1", "soil_carbon_trend", "rotation", None, "amg", "end_minus_start"),
        )
    ]
    assert carbon.difference.value == pytest.approx(0.7)
    assert carbon.difference.range is not None
    assert (carbon.difference.range.low, carbon.difference.range.high) == (
        pytest.approx(0.5),
        pytest.approx(0.9),
    )
    assert carbon.method == run.DIFFERENCE_METHOD
    carbon = items[
        (
            ("B", "C"),
            ("s3", "soil_carbon_trend", "rotation", None, "amg", "end_minus_start"),
        )
    ]
    assert carbon.difference.value == pytest.approx(0.2)
    assert carbon.difference.range is not None
    assert carbon.difference.range.low == 0.0
    assert carbon.difference.range.high == pytest.approx(0.4)
    water = items[
        (("B", "C"), ("s2", "water_deficit_exposure", "rotation", None, None, None))
    ]
    assert water.difference.value is None
    assert water.difference.missing.reason == "MISSING_INPUT"
    missing_2023 = items[(("A", "C"), ("s3", "soil_loss", "ag_year", 2023, None, None))]
    assert missing_2023.difference.value is None
    assert missing_2023.difference.missing.reason == "MISSING_INPUT"


def test_the_document_carries_the_counts_of_the_pairs_cells() -> None:
    document = run.build_decision_output(TABLE)
    counts = {item.key(): item for item in document.pair_cell_counts}
    assert len(counts) == 27  # 3 pairs x 3 scenarios x 3 indicators
    count = counts[(("A", "B"), "s1", "soil_loss")]
    assert count.by_sign_of_point_value is not None
    assert (
        count.by_sign_of_point_value.better,
        count.by_sign_of_point_value.worse,
        count.by_sign_of_point_value.equal,
        count.by_sign_of_point_value.missing_side,
    ) == (3, 0, 0, 1)
    assert (
        count.by_difference_range.strict_improvement,
        count.by_difference_range.deterioration,
        count.by_difference_range.not_separated,
    ) == (2, 0, 1)
    # Without a declared tolerance of "equal", the count by the sign of
    # the point value stays missing (D87, C3.1) — a GAP to report: the
    # machinery computes those counts too, the contract refuses them.
    for indicator in ("water_deficit_exposure", "soil_carbon_trend"):
        count = counts[(("B", "C"), "s1", indicator)]
        assert count.by_sign_of_point_value is None
        assert count.by_sign_of_point_value_missing is not None
        assert count.by_sign_of_point_value_missing.reason == "NOT_DECLARED"


def test_the_counts_of_the_carbon_cells_name_their_model_and_computation() -> None:
    """D169: one count per pair, scenario, indicator, carbon model and computation."""
    document = run.build_decision_output(TABLE)
    keys = [item.key_with_the_carbon_model() for item in document.pair_cell_counts]
    assert len(set(keys)) == len(keys) == 27
    for item in document.pair_cell_counts:
        if item.indicator == "soil_carbon_trend":
            # The matrix holds one carbon model and one computation (#240).
            assert (item.carbon_model, item.computation) == ("amg", "end_minus_start")
        else:
            assert (item.carbon_model, item.computation) == (None, None)


def test_the_document_carries_the_states_and_their_coverage() -> None:
    document = run.build_decision_output(TABLE)
    states = {tuple(item.pair): item for item in document.pair_states}
    assert set(states) == {("A", "B"), ("A", "C"), ("B", "C")}
    expected_coverage = {
        ("A", "B"): (12, 18),
        ("A", "C"): (12, 18),
        ("B", "C"): (15, 18),
    }
    for pair, item in states.items():
        # D166: over the set {s1, s2, s3}, "Not robust across scenarios",
        # with the reason of D86 "not robust across the admitted scenarios".
        assert item.value == "Not robust across scenarios"
        assert item.reason == "not robust across the admitted scenarios"
        assert item.reason_missing is None
        assert item.preferred_rotation_id is None
        assert (item.coverage.cells_compared, item.coverage.cells_of_the_pair) == (
            expected_coverage[pair]
        )
    # The document's one state: null with its reason (OPEN 5), naming
    # the indicators the pairs do not resolve; water is not among them
    # (D6: what was not evaluated does not enter the state).
    assert document.state.value is None
    assert document.state.missing is not None
    # D165: no pair has a blocking carbon cell (B vs C touches zero from the
    # side that is not worse), so only soil loss is named.
    assert document.state.indicators_not_resolved == ["soil_loss"]
    assert len(document.state.reasons) == 4  # one per pair, one for water
    assert all(reason.strip() for reason in document.state.reasons)


def test_the_document_carries_the_measurement_priority() -> None:
    # GAP: the contract's list is not keyed by a pair, so each item names
    # its pair in `what` (three items, one per pair, all rank 2).
    document = run.build_decision_output(TABLE)
    assert [item.rank for item in document.measure_first] == [2, 2, 2]
    for item, (first, second) in zip(document.measure_first, run.PAIRS):
        assert f"('{first}', '{second}')" in item.what
        assert "'u'" in item.what
        assert "never change the state" in item.why


def test_main_prints_the_document_and_the_tipping_points(capsys) -> None:
    run.main()
    printed = capsys.readouterr().out
    assert '"contract": "decision_output"' in printed
    assert "Tipping points" in printed
    assert "'Not separated: within uncertainty'" in printed
    assert "bracket None" in printed
