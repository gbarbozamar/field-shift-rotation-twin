"""Acceptance test of the bounded matrix through the decision (unit
l2/bounded-matrix-decision, issue #269).

The case under test is the one the producer approved on 15 November 2026:
the three rotation templates of D72 at the two residue-cover levels of
D115, every cell coming from the real-or-missing rule — a real engine
result where an engine runs, missing with its reason where none does, and
no hand-made value anywhere. The check that decided the cells (the brief
asks for it) is part of what these tests pin: the repository holds no
climate record of the demonstration point, the one committed recorded
response is the ocean-point evidence of D17 and D32, and ``api/`` tests
work through placeholders, so no real EP1, EP3 or EP5 output is
obtainable in the demo and every cell is missing ``NOT_AVAILABLE``, "the
engine's real outputs are not wired to the demo yet".

Every count, state, rank and coverage below is what the machinery of
``decision/functions.py`` gives on that table, derived from the decided
structure (D29 with D73 and D47 give the twenty-five agricultural years;
D80 with C1.6 give the six carbon cells; D94, D95, D60, D85, D87, D91 and
D99 give the counts and states over them). The arithmetic of D92 has no
work here — no difference holds a value, so no range exists to widen by
[b_low − a_high, b_high − a_low], and the rule of D165 has no range to
read — and the tests assert exactly that: the honest state of the demo
today, which the return path replaces with real values when the runner's
outputs arrive. The decisions D165 to D176 of 15 November 2026 (unit
l2/decision-rule-d165-d176, #309) changed two of these expectations and
changed none of the missing values: D169 splits the carbon counts, one
per carbon model and computation where this file once read one count of
the six cells, and D166 with D175 reads each level of the block on its
own, the state of each member now asserted beside the state of the set.

Run from the repository root: ``python -m pytest demo/``.
"""

from __future__ import annotations

from contracts.decision_output import DecisionOutput
from contracts.results.models import ResultsTable
from decision.functions import (
    indicator_ranking,
    measurement_priority,
    never_preferred_less,
    pair_counts,
    pair_state,
    paired_differences,
)

from demo import bounded, run_bounded

TABLE = bounded.bounded_matrix()

# The cells of one rotation in one scenario: the twenty-five soil-loss
# years of the record, the one water value and the six carbon cells
# (two mandatory models of D80 under the three computations of C1.6).
SOIL_CELLS = len(bounded.AG_YEARS)  # 25
CARBON_CELLS = len(bounded.CARBON_MODELS) * len(bounded.TREND_COMPUTATIONS)  # 6
CELLS_OF_A_ROTATION = SOIL_CELLS + 1 + CARBON_CELLS  # 32
CELLS_OF_A_PAIR = CELLS_OF_A_ROTATION * len(bounded.SCENARIOS)  # 64


def rows_of(table: ResultsTable, rotation_id: str, scenario_id: str) -> dict:
    """The rows of one rotation and scenario, by (indicator, ag_year, model,
    computation)."""
    return {
        (row.indicator, row.ag_year, row.carbon_model, row.computation): row
        for row in table.rows
        if row.rotation_id == rotation_id and row.scenario_id == scenario_id
    }


# --- the table is the bounded skeleton of the demonstration ----------------------


def test_the_table_is_the_bounded_skeleton() -> None:
    assert (TABLE.case_id, TABLE.field_id) == (bounded.CASE_ID, bounded.FIELD_ID)
    assert len(TABLE.rows) == 192  # 3 rotations x 2 levels x 32 cells
    for scenario_id in bounded.SCENARIOS:
        for rotation_id in bounded.ROTATIONS:
            rows = rows_of(TABLE, rotation_id, scenario_id)
            assert len(rows) == CELLS_OF_A_ROTATION
            for ag_year in bounded.AG_YEARS:
                row = rows[("soil_loss", ag_year, None, None)]
                assert (row.unit, row.direction) == ("t ha-1 yr-1", "lower_is_better")
                assert row.time_basis == "ag_year"
                assert row.provenance is None  # C4.1: no label when missing
                assert row.source is None
                assert row.range is None and row.range_missing is None
            row = rows[("water_deficit_exposure", None, None, None)]
            assert (row.unit, row.direction) == ("dimensionless", "higher_is_better")
            assert row.time_basis == "rotation"
            for carbon_model in bounded.CARBON_MODELS:
                for computation in bounded.TREND_COMPUTATIONS:
                    row = rows[("soil_carbon_trend", None, carbon_model, computation)]
                    assert (
                        row.unit,
                        row.direction,
                        row.computation,
                    ) == ("t C ha-1 yr-1", "higher_is_better", computation)
                    assert row.time_basis == "rotation"


def test_every_rotation_holds_the_same_cells() -> None:
    # The contract enforces it (the table builds); asserted here in its own
    # words, because the phases of D109 make it the binding rule it is.
    cells = {
        rotation_id: {row.cell() for row in TABLE.rows if row.rotation_id == rotation_id}
        for rotation_id in bounded.ROTATIONS
    }
    assert cells["R1"] == cells["R2"] == cells["R3"]


def test_the_years_are_those_of_the_record() -> None:
    # D29: the record runs 2001-01-01 to 2024-12-31; D73: the agricultural
    # year starts in July; D47 with point 1 of engine/calendar/repeat.py:
    # every agricultural year with at least one day in the record, which
    # the start month cuts to 2000 (covered from 1 January 2001) through
    # 2024 (covered to 31 December 2024).
    assert (bounded.RECORD_START, bounded.RECORD_END) == ("2001-01-01", "2024-12-31")
    assert bounded.AG_YEAR_START_MONTH == 7
    assert bounded.AG_YEARS == tuple(range(2000, 2025))
    assert len(bounded.AG_YEARS) == 25


def test_the_rotations_are_the_three_templates_of_d72() -> None:
    assert bounded.ROTATIONS == ("R1", "R2", "R3")
    # The templates travel as documentation only (the brief of issue #269).
    for rotation_id in bounded.ROTATIONS:
        assert rotation_id in bounded.ROTATION_TEMPLATES
    assert "alfalfa" in bounded.ROTATION_TEMPLATES["R3"]


# --- the real-or-missing rule: no hand-made cell anywhere ------------------------


def test_every_cell_is_missing_with_its_reason_and_never_zero() -> None:
    for row in TABLE.rows:
        assert "not wired" in row.missing.detail
        if row.indicator == "soil_carbon_trend" and row.carbon_model == "amg":
            assert "D122" in row.missing.detail  # the annual carbon inputs
        if row.indicator == "soil_carbon_trend" and row.carbon_model == "rothc":
            assert "EP6" in row.missing.detail  # the engine is not built


def test_no_cell_of_any_rotation_differs_from_the_rule() -> None:
    # One reason per indicator part (and per carbon model), the same for
    # every rotation, level and year: the rule is the table's, not a cell's.
    soil = {
        row.missing
        for row in TABLE.rows
        if row.indicator == "soil_loss"
    }
    assert len(soil) == 1
    water = {row.missing for row in TABLE.rows if row.indicator == "water_deficit_exposure"}
    assert len(water) == 1
    carbon = {
        row.missing
        for row in TABLE.rows
        if row.indicator == "soil_carbon_trend"
    }
    assert len(carbon) == 2  # one for AMG (D122), one for RothC (EP6)


# --- the residue-cover block of D75 at its two levels of D115 --------------------


def test_the_two_levels_are_the_scenarios_of_the_table() -> None:
    assert bounded.SCENARIOS == ("residue-cover-upper", "residue-cover-lower")
    assert set(bounded.SCENARIOS) == {row.scenario_id for row in TABLE.rows}


def test_the_upper_level_is_the_cap_of_the_table_per_sequence() -> None:
    covers = {
        (cover.rotation_id, cover.fallow): cover
        for cover in bounded.COVER_AT_THE_UPPER_LEVEL
    }
    # The caps of D115, as the fallows of the three templates read them.
    r1 = covers[("R1", "after soybean, before soybean (continuous annual soybean)")]
    assert r1.upper_percent == 40.0 and r1.upper_missing is None
    for rotation_id in ("R2", "R3"):
        cover = covers[(rotation_id, "after second-crop soybean, before maize")]
        assert cover.upper_percent == 80.0 and cover.upper_missing is None
    # Where the table gives no cap (before a winter cereal) or has no row
    # (after alfalfa), the upper level is missing with its reason (D115).
    r2_wheat = covers[("R2", "after maize, before wheat")]
    assert r2_wheat.upper_percent is None
    assert r2_wheat.upper_missing is not None
    assert r2_wheat.upper_missing.reason == "NO_COVERAGE"
    assert "no cap before a winter cereal" in r2_wheat.upper_missing.detail
    r3_wheat = covers[("R3", "after alfalfa, before wheat")]
    assert r3_wheat.upper_percent is None
    assert r3_wheat.upper_missing is not None
    assert r3_wheat.upper_missing.reason == "NO_COVERAGE"
    assert "no row after alfalfa" in r3_wheat.upper_missing.detail


def test_the_row_no_rotation_reads_and_the_lower_level() -> None:
    # The 70% row of the table is read by no rotation of D72; it stays as
    # data so the block shows the whole row of D115 it comes from.
    assert bounded.CAP_READ_BY_NO_ROTATION.upper_percent == 70.0
    assert bounded.CAP_READ_BY_NO_ROTATION.rotation_id == ""
    # The lower level is 0%, bare soil, for every fallow (D115).
    assert bounded.LOWER_LEVEL_PERCENT == 0.0


# --- D1 with D60: the counts by year judge nothing --------------------------------


def test_the_counts_by_year() -> None:
    counts = run_bounded.counts_by_year(TABLE)
    # D94: one count per rotation, level and indicator; D95: the two
    # indicators on the rotation basis have no count of years at all.
    assert set(counts) == {
        (rotation, scenario, "soil_loss", None, None)
        for rotation in bounded.ROTATIONS
        for scenario in bounded.SCENARIOS
    }
    for key, count in counts.items():
        # D60: no limit is declared, so no row is judged: nothing is
        # evaluated, the years within are null (never zero) and every row
        # is listed not evaluated with its reason.
        assert (count.evaluated, count.within, count.outside) == (0, None, None)
        assert len(count.not_evaluated) == SOIL_CELLS
        assert all(row.missing.reason == "NOT_AVAILABLE" for row in count.not_evaluated)
        assert [row.ag_year for row in count.not_evaluated] == list(bounded.AG_YEARS)
        assert key[0] in bounded.ROTATIONS


def test_the_ranges_across_scenarios_are_missing() -> None:
    items = {item.rotation_id: item for item in run_bounded.ranges_across_scenarios()}
    assert set(items) == set(bounded.ROTATIONS)
    for item in items.values():
        assert (item.minimum, item.maximum, item.scenario_of_the_minimum) == (
            None,
            None,
            None,
        )
        assert item.missing is not None
        assert item.missing.reason == "NOT_DECLARED"  # D60, D96


# --- D2 with D92: every paired difference is missing ------------------------------


def test_every_paired_difference_is_missing_on_both_sides() -> None:
    for first, second in run_bounded.PAIRS:
        differences = paired_differences(TABLE, first, second)
        assert len(differences) == CELLS_OF_A_PAIR
        for difference in differences:
            assert difference.value is None  # never zero
            assert difference.missing is not None
            assert difference.missing.reason == "MISSING_INPUT"
            assert f"'{first}'" in difference.missing.detail
            assert f"'{second}'" in difference.missing.detail
            # No value, so no range exists for D92 to compute.
            assert difference.range is None
            assert difference.range_missing is None


# --- D87 with D99 and D91: the counts of the cells of a pair -----------------------


def test_the_counts_of_the_cells_of_each_pair() -> None:
    # The tolerance argument satisfies the machinery's signature; no cell
    # holds a value on both sides, so it decides nothing here (D87 leaves
    # it to the designer of the case, who set none for this case).
    for first, second in run_bounded.PAIRS:
        counts = {
            (
                count.scenario_id,
                count.indicator,
                count.carbon_model,
                count.computation,
            ): count
            for count in pair_counts(TABLE, first, second, equal_tolerance=0.0)
        }
        # D169 ("One count per pair, scenario, indicator, carbon model and
        # computation, so that the cells of AMG and of RothC, which D155
        # never reads together, are never added in one count") resolves K10
        # the other way round from the comment this test once carried: the
        # six carbon cells of a level are six counts of one cell each, not
        # one count of six (the keys below re-derive it).
        assert set(counts) == {
            (scenario, "soil_loss", None, None)
            for scenario in bounded.SCENARIOS
        } | {
            (scenario, "water_deficit_exposure", None, None)
            for scenario in bounded.SCENARIOS
        } | {
            (scenario, "soil_carbon_trend", carbon_model, computation)
            for scenario in bounded.SCENARIOS
            for carbon_model in bounded.CARBON_MODELS
            for computation in bounded.TREND_COMPUTATIONS
        }
        for scenario in bounded.SCENARIOS:
            count = counts[(scenario, "soil_loss", None, None)]
            assert count.by_point_sign.missing_side == SOIL_CELLS
            assert (count.cells_compared, count.cells_of_the_pair) == (0, SOIL_CELLS)
            count = counts[(scenario, "water_deficit_exposure", None, None)]
            assert count.by_point_sign.missing_side == 1
            assert (count.cells_compared, count.cells_of_the_pair) == (0, 1)
            # D169: each carbon model and computation is a count of its
            # own, over its one cell.
            for carbon_model in bounded.CARBON_MODELS:
                for computation in bounded.TREND_COMPUTATIONS:
                    count = counts[
                        (scenario, "soil_carbon_trend", carbon_model, computation)
                    ]
                    assert count.by_point_sign.missing_side == 1
                    assert (count.cells_compared, count.cells_of_the_pair) == (0, 1)
            for count in counts.values():
                assert (
                    count.by_point_sign.better,
                    count.by_point_sign.worse,
                    count.by_point_sign.equal,
                ) == (0, 0, 0)
                assert (
                    count.by_range.strict_improvement,
                    count.by_range.deterioration,
                    count.by_range.not_separated,
                ) == (0, 0, 0)


# --- D7 with D85: the state of each pair ------------------------------------------


def test_the_states_of_the_pairs() -> None:
    for first, second in run_bounded.PAIRS:
        state = pair_state(TABLE, first, second)
        # D85: no paired difference holds a value, so the pair is not
        # evaluated and has no state; nothing enters it (D6).
        assert state.state is None
        # D166 with D175: the two levels of the block are read each on its
        # own — the cells of different scenarios are never merged — and the
        # state of each member is shown beside the state of the set. Every
        # member is not evaluated, so the set is not evaluated either (a
        # member without a state is never a robust preference, D175); no
        # range exists for D165 to unblock and no computation choice of
        # D173 changes anything, every carbon difference being missing.
        assert state.by_scenario == tuple(
            (scenario, None) for scenario in sorted(bounded.SCENARIOS)
        )
        assert state.identical_rows is False
        assert state.indicators_not_resolved == ()


def test_dominance_between_the_rotations() -> None:
    # D5 with D6: no cell of any pair holds a value on both sides, so no
    # rotation is better anywhere and no dominance holds, either way.
    for first, second in run_bounded.PAIRS:
        assert never_preferred_less(TABLE, first, second) is False
        assert never_preferred_less(TABLE, second, first) is False


# --- D6: what the missing values give ---------------------------------------------


def test_no_indicator_is_evaluated_at_all() -> None:
    soil = indicator_ranking(TABLE, "soil_loss")
    assert soil.every_value_missing is True
    assert soil.rotations_with_a_value == frozenset()
    assert len(soil.reasons) == 150  # 3 rotations x 2 levels x 25 years
    assert {reason for _, reason in soil.reasons} == {soil.reasons[0][1]}
    assert soil.reasons[0][1].reason == "NOT_AVAILABLE"
    water = indicator_ranking(TABLE, "water_deficit_exposure")
    assert water.every_value_missing is True
    assert len(water.reasons) == 6  # 3 rotations x 2 levels
    carbon = indicator_ranking(TABLE, "soil_carbon_trend")
    assert carbon.every_value_missing is True
    assert len(carbon.reasons) == 36  # 3 rotations x 2 levels x 6 cells


# --- D4 over no declared input -----------------------------------------------------


def test_the_measurement_priority_over_no_declared_input() -> None:
    # The residue-cover block drives no cell of this table and its upper
    # level holds no single admitted value, so no mapping is declared: the
    # machinery's answer over no inputs is an empty list per pair (the
    # base state being that of a pair not evaluated).
    for pair, priority in run_bounded.measurement_priorities(TABLE).items():
        assert pair in run_bounded.PAIRS
        assert priority.base_state is None
        assert priority.items == ()
        assert measurement_priority(TABLE, *pair, run_bounded.UNCERTAIN_INPUTS) == (
            priority
        )


# --- the decision output document --------------------------------------------------


def test_the_document_validates_and_roundtrips() -> None:
    document = run_bounded.build_decision_output(TABLE)
    assert isinstance(document, DecisionOutput)
    again = DecisionOutput.model_validate(document.model_dump())
    assert again == document
    assert (document.case_id, document.field_id) == (bounded.CASE_ID, bounded.FIELD_ID)
    assert document.rotations == ["R1", "R2", "R3"]
    assert document.scenarios == ["residue-cover-upper", "residue-cover-lower"]
    assert document.example_data is True


def test_the_document_carries_the_limits_and_tolerances() -> None:
    document = run_bounded.build_decision_output(TABLE)
    limits = {item.indicator: item.limit for item in document.limits}
    assert set(limits) == set(run_bounded.INDICATORS)
    for indicator, limit in limits.items():
        assert limit.value is None  # never zero
        assert limit.missing is not None
        assert limit.missing.reason == "NOT_DECLARED"  # D60, D89
    tolerances = {
        item.indicator: item.tolerance for item in document.equal_tolerances
    }
    for indicator, tolerance in tolerances.items():
        assert tolerance.value is None
        assert tolerance.missing is not None
        assert tolerance.missing.reason == "NOT_DECLARED"  # D87, C3.1


def test_the_document_carries_the_counts_and_their_ranges() -> None:
    document = run_bounded.build_decision_output(TABLE)
    counts = {count.key(): count for count in document.counts_by_year}
    assert len(counts) == 6  # D94: 3 rotations x 2 levels, soil loss only
    for (rotation, scenario, indicator, _, _), count in counts.items():
        assert (rotation, scenario, indicator) in {
            (r, s, "soil_loss")
            for r in bounded.ROTATIONS
            for s in bounded.SCENARIOS
        }
        assert (count.years_evaluated, count.years_within_limits) == (0, None)
        assert [row.ag_year for row in count.not_evaluated] == list(bounded.AG_YEARS)
    ranges = {item.rotation_id: item for item in document.range_across_scenarios}
    assert set(ranges) == set(bounded.ROTATIONS)
    for item in ranges.values():
        assert item.missing is not None
        assert item.missing.reason == "NOT_DECLARED"


def test_the_document_carries_the_differences() -> None:
    document = run_bounded.build_decision_output(TABLE)
    assert len(document.paired_differences) == 192  # 3 pairs x 64 cells
    items = {
        (tuple(item.pair), item.cell()): item for item in document.paired_differences
    }
    assert len(items) == 192
    for item in items.values():
        assert item.difference.value is None  # never zero
        assert item.difference.missing is not None
        assert item.difference.missing.reason == "MISSING_INPUT"
        assert item.method == run_bounded.DIFFERENCE_METHOD
    carbon = items[
        (
            ("R2", "R3"),
            (
                "residue-cover-lower",
                "soil_carbon_trend",
                "rotation",
                None,
                "rothc",
                "fitted_slope",
            ),
        )
    ]
    assert "'R2'" in carbon.difference.missing.detail
    assert "'R3'" in carbon.difference.missing.detail


def test_the_document_carries_the_counts_of_the_pairs_cells() -> None:
    document = run_bounded.build_decision_output(TABLE)
    counts = {
        item.key_with_the_carbon_model(): item for item in document.pair_cell_counts
    }
    # D169: 3 pairs x 2 levels x (soil, water and the six carbon cells of
    # two models under three computations, each a count of its own) — 48
    # counts, where the key of D87 alone gave 18.
    assert len(counts) == 48
    carbon_keys = {
        (carbon_model, computation)
        for carbon_model in bounded.CARBON_MODELS
        for computation in bounded.TREND_COMPUTATIONS
    }
    for key, count in counts.items():
        pair, scenario, indicator, carbon_model, computation = key
        assert tuple(pair) in run_bounded.PAIRS
        assert scenario in bounded.SCENARIOS
        if indicator == "soil_carbon_trend":
            # D169: a carbon count names its carbon model and computation.
            assert (carbon_model, computation) in carbon_keys
        else:
            assert indicator in ("soil_loss", "water_deficit_exposure")
            assert (carbon_model, computation) == (None, None)
        # Without a declared tolerance of "equal" the count by the sign of
        # the point value stays missing (D87, C3.1).
        assert count.by_sign_of_point_value is None
        assert count.by_sign_of_point_value_missing is not None
        assert count.by_sign_of_point_value_missing.reason == "NOT_DECLARED"
        assert (
            count.by_difference_range.strict_improvement,
            count.by_difference_range.deterioration,
            count.by_difference_range.not_separated,
        ) == (0, 0, 0)


def test_the_document_carries_the_states_and_their_coverage() -> None:
    document = run_bounded.build_decision_output(TABLE)
    states = {tuple(item.pair): item for item in document.pair_states}
    assert set(states) == set(run_bounded.PAIRS)
    for item in states.values():
        assert item.value is None  # D85: not evaluated, no state
        assert item.missing is not None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert item.reason is None  # D86 writes no reason for it
        assert item.preferred_rotation_id is None
        assert (item.coverage.cells_compared, item.coverage.cells_of_the_pair) == (
            0,
            CELLS_OF_A_PAIR,
        )
    # The document's one state: null with its reason (OPEN 5); nothing was
    # evaluated, so no indicator is named (D6), and the reasons say so.
    assert document.state.value is None
    assert document.state.missing is not None
    assert document.state.indicators_not_resolved == []
    assert len(document.state.reasons) == 7  # 3 pairs, 3 indicators, 1 block
    assert all(reason.strip() for reason in document.state.reasons)
    # D166 with D152: the reason of a pair shows the state of each member
    # beside the state of the set, and a member without a state is written
    # with the label D151 gives that absence.
    for first, second in run_bounded.PAIRS:
        reason = next(
            reason
            for reason in document.state.reasons
            if f"('{first}', '{second}')" in reason
        )
        assert "; in each scenario:" in reason
        for scenario in bounded.SCENARIOS:
            assert f"'{scenario}' 'Not evaluated'" in reason


def test_the_document_carries_no_measurement_priority() -> None:
    document = run_bounded.build_decision_output(TABLE)
    assert document.measure_first == []


def test_main_prints_the_document_the_block_and_the_gaps(capsys) -> None:
    run_bounded.main()
    printed = capsys.readouterr().out
    assert '"contract": "decision_output"' in printed
    assert "residue-cover-upper" in printed
    assert "the engine's real outputs are not wired to the demo yet" in printed
    assert "D115" in printed
    assert "0% residue cover, bare soil" in printed
    assert "No tipping point of D3 is computed" in printed
    # D176: the printed gap carries its conditions for the sweep of #267.
    assert "D176 confirms the block" in printed
    assert "no tipping point" in printed
