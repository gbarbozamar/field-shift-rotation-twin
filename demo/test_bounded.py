"""Acceptance test of the bounded matrix through the decision (unit
l2/bounded-matrix-decision, issue #269).

The case under test is the one the producer approved on 15 November 2026:
the three rotation templates of D72 in the one admitted residue-cover
level of D115 and D171, every cell coming from the real-or-missing rule -
a real engine result where an engine runs, missing with its reason where
none does, and no hand-made value anywhere. What the rule gives today is
pinned as the truth it is: the six engines are built and the runner wires
them (EP1 to EP6, api/engines.py), the demonstration holds no climate
record of the point, so the runner calls none of them and every cell is
missing MISSING_INPUT with the runner's own answer, "input not
available: climate (site data: climate)". One test runs the real runner
to pin that this reason is its answer, not a text this unit invented.

The admitted set is the lower level of the block alone (D171): D115
leaves the upper level missing for R2 and R3, so it is not run (no row
of the table carries it), not admitted and not evaluated, and it is
listed with its reason; under D176, condition 2, it is never read as a
tipping point of the cover.

Every count, state, rank and coverage below is what the machinery of
``decision/functions.py`` gives on that table, derived from the decided
structure (D29 with D73 and D47 give the twenty-five agricultural years;
D157 gives one water value per agricultural year; D80 with C1.6 give the
six carbon cells; D94, D95, D60, D85, D87, D91 and D99 give the counts
and states over them). The state of each pair comes from ``pair_state``
and its coverage from ``dominance``; one test pins that on a hand-made
filled variant of the table (test data only, never shown by the demo):
with one soil cell filled on both sides the machinery gives "Not
separated: uncertainty missing", and the document carries exactly that.
The arithmetic of D92 has no work here - no difference holds a value, so
no range exists to widen by [b_low - a_high, b_high - a_low], and the
rule of D165 has no range to read - and the tests assert exactly that:
the honest state of the demo today, which the return path replaces with
real values when a climate record of the point is admitted.

Run from the repository root: ``python -m pytest demo/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from adapters.ports import (
    ClimateResult,
    SoilSlopeResult,
    SourceInfo,
)
from api.engines import (
    AMG,
    DEFAULT_CARBON_MODELS,
    EROSION,
    RESIDUES,
    ROTHC,
    WATER,
    EntryPointEngines,
    discover_engine_functions,
)
from contracts.decision_output import DecisionOutput
from contracts.inputs import SiteSoilSlope
from contracts.results.models import (
    Missing,
    ResultsTable,
    ResultsTableRow,
)
from decision.functions import (
    NOT_SEPARATED_UNCERTAINTY_MISSING,
    indicator_ranking,
    measurement_priority,
    never_preferred_less,
    pair_counts,
    pair_state,
    paired_differences,
)

from demo import bounded, run_bounded

ROOT = Path(__file__).parent.parent
TABLE = bounded.bounded_matrix()

# The cells of one rotation in one scenario: the twenty-five soil-loss
# years of the record, the twenty-five water years of D157 and the six
# carbon cells (two mandatory models of D80 under the three computations
# of C1.6).
SOIL_CELLS = len(bounded.AG_YEARS)  # 25
WATER_CELLS = len(bounded.AG_YEARS)  # 25, D157
CARBON_CELLS = len(bounded.CARBON_MODELS) * len(bounded.TREND_COMPUTATIONS)  # 6
CELLS_OF_A_ROTATION = SOIL_CELLS + WATER_CELLS + CARBON_CELLS  # 56
CELLS_OF_A_PAIR = CELLS_OF_A_ROTATION * len(bounded.SCENARIOS)  # 56


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
    # 3 rotations x 1 admitted level x 56 cells (D171 keeps the upper
    # level out: see test_the_upper_level_is_not_run_nor_admitted).
    assert len(TABLE.rows) == 168
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
                # D157: one water value per agricultural year, never one
                # value for the whole rotation.
                row = rows[("water_deficit_exposure", ag_year, None, None)]
                assert (row.unit, row.direction) == (
                    "dimensionless",
                    "higher_is_better",
                )
                assert row.time_basis == "ag_year"
                assert row.provenance is None
                assert row.source is None
                assert row.range is None and row.range_missing is None
            for carbon_model in bounded.CARBON_MODELS:
                for computation in bounded.TREND_COMPUTATIONS:
                    row = rows[("soil_carbon_trend", None, carbon_model, computation)]
                    assert (
                        row.unit,
                        row.direction,
                        row.computation,
                    ) == ("t C ha-1 yr-1", "higher_is_better", computation)
                    assert row.time_basis == "rotation"  # C1.5
                    assert row.provenance is None
                    assert row.source is None


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


# --- the real-or-missing rule: the runner's own reason, never zero ----------------


def test_every_cell_is_missing_with_the_runners_reason_and_never_zero() -> None:
    for row in TABLE.rows:
        assert row.value is None  # never zero
        assert row.missing is not None
        # The runner's own answer when the climate of the point is absent,
        # the same for EP1, EP3, EP4, EP5 and EP6 (api/engines.py).
        assert row.missing.reason == "MISSING_INPUT"
        assert bounded.CLIMATE_MISSING_DETAIL in row.missing.detail
        # The false claims this file once pinned are gone: no engine of
        # the six is "not built", and nothing is "not wired".
        assert "not built" not in row.missing.detail
        assert "not wired" not in row.missing.detail


def test_no_cell_of_any_rotation_differs_from_the_rule() -> None:
    # One reason for every cell, the same for every rotation, year, carbon
    # model and computation: the runner's answer is one, the climate of
    # the point, for every part alike.
    missing = {row.missing for row in TABLE.rows}
    assert missing == {bounded.MISSING_CLIMATE}


def test_the_engines_are_built_and_the_reason_is_the_runners_own() -> None:
    # The truth the reason pins, checked against the real registry and the
    # real runner, not against this unit's own text.
    functions = discover_engine_functions()
    for name in (
        "build_rotation_calendar",  # EP2
        "compute_soil_loss",  # EP1
        "compute_water_deficit_exposure",  # EP3
        "build_residue_ledger",  # EP4
        "run_amg",  # EP5
        "run_rothc",  # EP6
    ):
        assert getattr(functions, name) is not None, name
    # The real runner on the real inputs the demo has - the accepted soil
    # and slope of the point, no climate record of it - calls no engine
    # and answers MISSING_INPUT naming the climate for every part alike.
    soil = json.loads(
        (ROOT / "data/demo/la_estanzuela_soil_slope.json").read_text(encoding="utf-8")
    )
    unavailable = SourceInfo(
        id="demo-test",
        contract="site_data_climate",
        state="unavailable",
        missing_reason="SOURCE_UNAVAILABLE",
    )
    engines = EntryPointEngines(functions, carbon_models=DEFAULT_CARBON_MODELS)
    answer = engines.run(
        json.loads(
            (
                ROOT
                / "contracts/rotation_definition/examples/"
                "PLACEHOLDER_rotation_definition.json"
            ).read_text(encoding="utf-8")
        ),
        ClimateResult(data=None, source=unavailable),
        SoilSlopeResult(
            data=SiteSoilSlope.model_validate(soil), source=unavailable
        ),
    )
    by_id = {module.id: module for module in answer.modules}
    for point in (EROSION, WATER, RESIDUES, AMG, ROTHC):
        module = by_id[point.module_id]
        assert module.state == "not_available", point.module_id
        assert module.reason == "MISSING_INPUT", point.module_id
        assert module.detail == bounded.CLIMATE_MISSING_DETAIL, point.module_id
    # And the cells of the table carry exactly that reason.
    assert bounded.MISSING_CLIMATE.reason == "MISSING_INPUT"
    for row in TABLE.rows:
        assert row.missing.reason == "MISSING_INPUT"
        assert bounded.CLIMATE_MISSING_DETAIL in row.missing.detail


# --- the residue-cover block of D75: the admitted set of D171 ---------------------


def test_the_admitted_set_is_the_lower_level_alone() -> None:
    # The two levels of the block as D115 decides them...
    assert bounded.LEVELS == ("residue-cover-upper", "residue-cover-lower")
    # ...and the admitted set of the table (D171: "a level that a decision
    # leaves missing with its reason [...] is not run and is not
    # admitted"): the lower level alone, the one scenario of the table.
    assert bounded.SCENARIOS == ("residue-cover-lower",)
    assert {row.scenario_id for row in TABLE.rows} == {"residue-cover-lower"}


def test_the_upper_level_is_not_run_nor_admitted() -> None:
    # D171 with D115: the upper level is missing for R2 and R3 (no cap
    # before a winter cereal, no row after alfalfa), so it is not run -
    # no row of the table carries it - and it is listed with its reason.
    assert not any(
        row.scenario_id == bounded.UPPER for row in TABLE.rows
    )  # not run (D171)
    missing_upper = [
        cover
        for cover in bounded.COVER_AT_THE_UPPER_LEVEL
        if cover.upper_missing is not None
    ]
    assert sorted(cover.rotation_id for cover in missing_upper) == ["R2", "R3"]
    for cover in missing_upper:
        assert cover.upper_percent is None
        assert cover.upper_missing is not None
        assert cover.upper_missing.reason == "NO_COVERAGE"
    # No pair is evaluated at it and it is never read as a tipping point
    # of the cover (D176, condition 2): the document says so.
    document = run_bounded.build_decision_output(TABLE)
    listing = next(
        reason for reason in document.state.reasons if "D171" in reason
    )
    assert "not run and not admitted" in listing
    assert "R2, R3" in listing
    assert "NO_COVERAGE" in listing
    assert "D176" in listing
    assert "never read as a tipping point" in listing


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
    # (after alfalfa), the upper level is missing with its reason (D115)
    # and, with it, for the whole of that rotation (D171).
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
    # The lower level is 0%, bare soil, for every fallow (D115); it is the
    # one admitted level of the table (D171).
    assert bounded.LOWER_LEVEL_PERCENT == 0.0


# --- D1 with D60: the counts by year judge nothing --------------------------------


def test_the_counts_by_year() -> None:
    counts = run_bounded.counts_by_year(TABLE)
    # D94: one count per rotation, level and indicator; D95: D157 puts the
    # water cells on the agricultural year, so both indicators of the
    # ag_year basis are counted; only the soil carbon trend (one value per
    # rotation, C1.5) has no count of years.
    assert set(counts) == {
        (rotation, scenario, indicator, None, None)
        for rotation in bounded.ROTATIONS
        for scenario in bounded.SCENARIOS
        for indicator in ("soil_loss", "water_deficit_exposure")
    }
    for key, count in counts.items():
        # D60: no limit is declared, so no row is judged: nothing is
        # evaluated, the years within are null (never zero) and every row
        # is listed not evaluated with its reason.
        assert (count.evaluated, count.within, count.outside) == (0, None, None)
        assert len(count.not_evaluated) == len(bounded.AG_YEARS)
        assert all(
            row.missing.reason == "MISSING_INPUT" for row in count.not_evaluated
        )
        assert [row.ag_year for row in count.not_evaluated] == list(bounded.AG_YEARS)
        assert key[0] in bounded.ROTATIONS


def test_the_ranges_across_scenarios_are_missing() -> None:
    items = run_bounded.ranges_across_scenarios()
    # One per rotation and indicator counted (soil loss and water, D157),
    # each missing with its reason: no year is judged against a limit
    # (D60), so no range across scenarios is given (D96).
    assert {(item.rotation_id, item.indicator) for item in items} == {
        (rotation, indicator)
        for rotation in bounded.ROTATIONS
        for indicator in ("soil_loss", "water_deficit_exposure")
    }
    for item in items:
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
        # six carbon cells of the level are six counts of one cell each,
        # not one count of six (the keys below re-derive it).
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
            assert (count.cells_compared, count.cells_of_the_pair) == (
                0,
                SOIL_CELLS,
            )
            # D157: twenty-five water cells, one per agricultural year.
            count = counts[(scenario, "water_deficit_exposure", None, None)]
            assert count.by_point_sign.missing_side == WATER_CELLS
            assert (count.cells_compared, count.cells_of_the_pair) == (
                0,
                WATER_CELLS,
            )
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


# --- D7 with D85: the state of each pair, from the machinery ----------------------


def test_the_states_of_the_pairs() -> None:
    for first, second in run_bounded.PAIRS:
        state = pair_state(TABLE, first, second)
        # D85: no paired difference holds a value, so the pair is not
        # evaluated and has no state; nothing enters it (D6).
        assert state.state is None
        # The admitted set holds one scenario (D171), so the table is read
        # as one scenario and there is no member listing (D166 gives one
        # only over several); no computation choice of D173 changes
        # anything, every carbon difference being missing.
        assert state.by_scenario == ()
        assert state.identical_rows is False
        assert state.indicators_not_resolved == ()


def filled_variant(
    table: ResultsTable, first: str, second: str, ag_year: int
) -> ResultsTable:
    """The table with one soil-loss cell of the pair filled on both sides.

    Hand-made test data only (the demo itself shows no value): it exists
    to pin that the pair states of the document are the machinery's
    (``pair_state``), not a text this unit writes.
    """

    rows = []
    for row in table.rows:
        if (
            row.rotation_id in (first, second)
            and row.indicator == "soil_loss"
            and row.ag_year == ag_year
            and row.scenario_id in bounded.SCENARIOS
        ):
            rows.append(
                ResultsTableRow(
                    rotation_id=row.rotation_id,
                    scenario_id=row.scenario_id,
                    time_basis=row.time_basis,
                    ag_year=row.ag_year,
                    indicator=row.indicator,
                    direction=row.direction,
                    value=1.0 if row.rotation_id == first else 2.0,
                    unit=row.unit,
                    range_missing=Missing(
                        reason="NOT_DECLARED",
                        detail="hand-made test value: no range",
                    ),
                    provenance="DERIVED",  # C4.6
                    source="hand-made test table of demo/test_bounded.py",
                )
            )
        else:
            rows.append(row)
    return ResultsTable(case_id=table.case_id, field_id=table.field_id, rows=rows)


def test_the_pair_states_of_the_document_come_from_the_machinery() -> None:
    # On the honest table every pair is not evaluated (D85) and the
    # coverage counts no cell compared (D91)...
    items = {tuple(item.pair): item for item in run_bounded.pair_states_of_the_set(TABLE)}
    for pair, item in items.items():
        machinery = pair_state(TABLE, *pair)
        assert item.value == machinery.state is None
        assert item.missing is not None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert (item.coverage.cells_compared, item.coverage.cells_of_the_pair) == (
            0,
            CELLS_OF_A_PAIR,
        )
    # ...and on a filled variant the document carries exactly what the
    # machinery answers, not "not evaluated" regardless: one computed
    # difference without a range gives "Not separated: uncertainty
    # missing" (D92, D97).
    filled = filled_variant(TABLE, "R1", "R2", ag_year=2001)
    machinery = pair_state(filled, "R1", "R2")
    assert machinery.state == NOT_SEPARATED_UNCERTAINTY_MISSING
    item = {
        tuple(state.pair): state
        for state in run_bounded.pair_states_of_the_set(filled)
    }[("R1", "R2")]
    assert item.value == machinery.state == NOT_SEPARATED_UNCERTAINTY_MISSING
    assert item.reason == "a difference without its range"  # D86
    assert (item.coverage.cells_compared, item.coverage.cells_of_the_pair) == (
        1,
        CELLS_OF_A_PAIR,
    )


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
    assert len(soil.reasons) == 75  # 3 rotations x 1 level x 25 years
    assert {reason for _, reason in soil.reasons} == {soil.reasons[0][1]}
    assert soil.reasons[0][1].reason == "MISSING_INPUT"
    water = indicator_ranking(TABLE, "water_deficit_exposure")
    assert water.every_value_missing is True
    assert len(water.reasons) == 75  # 3 rotations x 1 level x 25 years (D157)
    carbon = indicator_ranking(TABLE, "soil_carbon_trend")
    assert carbon.every_value_missing is True
    assert len(carbon.reasons) == 18  # 3 rotations x 1 level x 6 cells


# --- D4 over no declared input -----------------------------------------------------


def test_the_measurement_priority_over_no_declared_input() -> None:
    # The residue-cover block drives no cell of this table and its upper
    # level is not admitted at all (D171), so no mapping is declared: the
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
    # D171: the admitted set is the lower level alone.
    assert document.scenarios == ["residue-cover-lower"]
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
    # D94 with D157: 3 rotations x 1 level x the two indicators of the
    # ag_year basis (soil loss and water); the carbon trend has no count
    # of years (D95, C1.5).
    assert set(counts) == {
        (rotation, scenario, indicator, None, None)
        for rotation in bounded.ROTATIONS
        for scenario in bounded.SCENARIOS
        for indicator in ("soil_loss", "water_deficit_exposure")
    }
    for (rotation, scenario, indicator, _, _), count in counts.items():
        assert (count.years_evaluated, count.years_within_limits) == (0, None)
        assert [row.ag_year for row in count.not_evaluated] == list(bounded.AG_YEARS)
    ranges = {(item.rotation_id, item.indicator) for item in document.range_across_scenarios}
    assert ranges == {
        (rotation, indicator)
        for rotation in bounded.ROTATIONS
        for indicator in ("soil_loss", "water_deficit_exposure")
    }
    for item in document.range_across_scenarios:
        assert item.missing is not None
        assert item.missing.reason == "NOT_DECLARED"


def test_the_document_carries_the_differences() -> None:
    document = run_bounded.build_decision_output(TABLE)
    assert len(document.paired_differences) == 168  # 3 pairs x 56 cells
    items = {
        (tuple(item.pair), item.cell()): item for item in document.paired_differences
    }
    assert len(items) == 168
    for item in items.values():
        assert item.difference.value is None  # never zero
        assert item.difference.missing is not None
        assert item.difference.missing.reason == "MISSING_INPUT"
        assert item.method == run_bounded.DIFFERENCE_METHOD
        if item.indicator == "water_deficit_exposure":
            # D157: the difference of a water cell is per agricultural
            # year, on the ag_year basis.
            assert item.time_basis == "ag_year"
            assert item.ag_year in bounded.AG_YEARS
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
    # D169: 3 pairs x 1 level x (soil, water and the six carbon cells of
    # two models under three computations, each a count of its own) - 24
    # counts, where the key of D87 alone gave 9.
    assert len(counts) == 24
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
    # evaluated, so no indicator is named (D6), and the reasons say so:
    # one per pair, one per indicator, one for the level not admitted.
    assert document.state.value is None
    assert document.state.missing is not None
    assert document.state.indicators_not_resolved == []
    assert len(document.state.reasons) == 7  # 3 pairs, 3 indicators, 1 level
    assert all(reason.strip() for reason in document.state.reasons)
    for first, second in run_bounded.PAIRS:
        reason = next(
            reason
            for reason in document.state.reasons
            if f"('{first}', '{second}')" in reason
        )
        assert "not evaluated" in reason
    for indicator in run_bounded.INDICATORS:
        reason = next(
            reason
            for reason in document.state.reasons
            if f"'{indicator}' is not evaluated" in reason
        )
        assert bounded.CLIMATE_MISSING_DETAIL in reason


def test_the_document_carries_no_measurement_priority() -> None:
    document = run_bounded.build_decision_output(TABLE)
    assert document.measure_first == []


def test_main_prints_the_document_the_block_and_the_gaps(capsys) -> None:
    run_bounded.main()
    printed = capsys.readouterr().out
    assert '"contract": "decision_output"' in printed
    assert "residue-cover-lower" in printed
    # The runner's own reason, not a "not built" or "not wired" story
    # about the engines (the phases of D117, condition 1 of D176, are a
    # gap the demo does report).
    assert bounded.CLIMATE_MISSING_DETAIL in printed
    assert "the six engines are built" in printed
    assert "not wired" not in printed
    # The false claims of the rejected first version are gone: no engine
    # of the six is called not built ("EP1 to EP6" does appear, stating
    # they are all registered), and D122 is not the reason anymore.
    assert "not built" not in printed.replace(
        "the phases of D117 are not built yet", ""
    )
    assert "D122" not in printed
    # The admitted set and the level not admitted (D171, D176 condition 2).
    assert "D115" in printed
    assert "0% residue cover, bare soil" in printed
    assert "not run, not admitted" in printed
    assert "D171" in printed
    # No tipping point, and the four conditions of D176 for the sweep of
    # #267 (the phases of D117 not built is condition 1, a gap the demo
    # reports rather than claims).
    assert "No tipping point of D3 is computed" in printed
    assert "D176" in printed
    assert "no tipping point" in printed
    assert "condition 4" in printed
    assert "not materialized" in printed
