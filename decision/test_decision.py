"""Acceptance test of the decision functions (units l2/decision-functions
#163 and l2/decision-separation #202).

The table below is the one supplied by a person and verified by the lead
developer on #96 (decisions D59 to D61 of #77); every expected value in
this file is that supplied one, or follows from the decisions D74 and
D85 to D99 of #77 as the person-approved expectations of #202 state
them, and none is invented here. The logic each group of tests follows
is the D entry of ``docs/VALIDATION.md`` named in its title, as decided
by the lead developer on 14 November 2026.

The table is labelled example data throughout; the results contract has
no field for that label (``ResultsTable`` holds only ``case_id``,
``field_id`` and ``rows``), so the label lives in this docstring, and
the sources of the numbers carry their PLACEHOLDER markers.

The supplied table carries no range on any value (``range_missing``
NOT_AVAILABLE everywhere), so under D92 no difference of any pair has a
range: the branches of D92, D93 and D98 that need a range (a computed
difference range, the classes of a ranged cell, the states "Robust
preference" and "Not separated: within uncertainty") are implemented in
``decision/functions.py`` and are not exercised numerically here,
because no person-supplied table carries ranges and this file invents
no value, threshold or range (CLAUDE.md, "Rules a session must follow").

Run from the repository root: ``python -m pytest decision/``.
"""

from __future__ import annotations

import pytest

from contracts.results import models
from contracts.results.models import Missing, ResultsTable, ResultsTableRow
from decision.functions import (
    IDENTICAL,
    NOT_SEPARATED_UNCERTAINTY_MISSING,
    DeclaredLimit,
    PairCounts,
    PointSignCounts,
    RangeClassCounts,
    indicator_ranking,
    limit_counts,
    never_preferred_less,
    paired_difference,
    paired_differences,
    pair_counts,
    pair_state,
)

# The numerical tolerance of the paired differences (D2) and of the
# "equal" cells of the counts of D87, supplied by the person who
# designed the case: absolute.
TOLERANCE = 1e-9

CASE_ID = "example-case"
FIELD_ID = "example-field-1"
SCENARIO_ID = "s1"
ROTATIONS = ("A", "B", "C")

SOIL_SOURCE = "PLACEHOLDER_source"
CARBON_SOURCE = "PLACEHOLDER_model_amg"
LIMIT_SOURCE = "PLACEHOLDER_user"
SOIL_RANGE_MISSING = Missing(
    reason="NOT_AVAILABLE", detail="range of the input values not defined yet"
)
CARBON_RANGE_MISSING = Missing(reason="NOT_AVAILABLE")
WATER_MISSING = Missing(
    reason="NOT_AVAILABLE", detail="the definition of C1.4 is incomplete"
)
NO_COVERAGE = Missing(reason="NO_COVERAGE")

# The soil-loss values of each rotation, by agricultural year; a year
# left out is the one missing with reason NO_COVERAGE.
SOIL_VALUES = {
    "A": {2020: 8.2, 2021: 7.0, 2022: 9.1},
    "B": {2020: 6.1, 2021: 6.5, 2022: 7.0, 2023: 6.8},
    "C": {2020: 6.1, 2021: 6.5, 2022: 7.0, 2023: 6.8},
}
CARBON_VALUES = {"A": -0.4, "B": 0.3, "C": 0.3}

# The declared limits (provenance DECLARED, source PLACEHOLDER_user):
# soil_loss <= 7.0 and soil_carbon_trend >= -0.1. No limit for water.
LIMITS = {
    "soil_loss": DeclaredLimit(
        indicator="soil_loss", limit=7.0, provenance="DECLARED", source=LIMIT_SOURCE
    ),
    "soil_carbon_trend": DeclaredLimit(
        indicator="soil_carbon_trend",
        limit=-0.1,
        provenance="DECLARED",
        source=LIMIT_SOURCE,
    ),
}


def soil_row(rotation_id: str, ag_year: int, value: float | None) -> ResultsTableRow:
    """One agricultural year of soil loss of one rotation."""
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=SCENARIO_ID,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit=models.UNIT_SOIL_LOSS_ANNUAL,
            missing=NO_COVERAGE,
        )
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=SCENARIO_ID,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        range_missing=SOIL_RANGE_MISSING,
        provenance="DERIVED",
        source=SOIL_SOURCE,
    )


def carbon_row(rotation_id: str, value: float) -> ResultsTableRow:
    """The soil-carbon trend of one rotation, model amg, end minus start."""
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=SCENARIO_ID,
        time_basis="rotation",
        indicator="soil_carbon_trend",
        direction="higher_is_better",
        value=value,
        unit=models.UNIT_SOIL_CARBON_TREND,
        carbon_model="amg",
        computation="end_minus_start",
        range_missing=CARBON_RANGE_MISSING,
        provenance="SIMULATED",
        source=CARBON_SOURCE,
    )


def water_row(rotation_id: str) -> ResultsTableRow:
    """The water-deficit exposure of one rotation: missing, C1.4 incomplete."""
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=SCENARIO_ID,
        time_basis="rotation",
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=None,
        unit=models.UNIT_WATER_DEFICIT_EXPOSURE,
        missing=WATER_MISSING,
    )


def example_table() -> ResultsTable:
    """The supplied hand-made table, following ``contracts/results/`` exactly."""
    rows = []
    for rotation_id in ROTATIONS:
        for ag_year in (2020, 2021, 2022, 2023):
            soil = SOIL_VALUES[rotation_id].get(ag_year)
            rows.append(soil_row(rotation_id, ag_year, soil))
        rows.append(carbon_row(rotation_id, CARBON_VALUES[rotation_id]))
        rows.append(water_row(rotation_id))
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


def water_only_table() -> ResultsTable:
    """The water rows of the supplied table alone (a subset of it: no value
    is added, changed or invented)."""
    return ResultsTable(
        case_id=CASE_ID,
        field_id=FIELD_ID,
        rows=[water_row(rotation_id) for rotation_id in ROTATIONS],
    )


def by_cell(differences) -> dict[tuple, object]:
    """The paired differences of one pair, by indicator and agricultural year."""
    return {(item.indicator, item.ag_year): item for item in differences}


def by_cell_of_pair(
    table: ResultsTable, first_rotation: str, second_rotation: str
) -> dict[tuple, PairCounts]:
    """The counts of one pair, by scenario and indicator (the tolerance is
    the one the designer of the case set)."""
    return {
        (item.scenario_id, item.indicator): item
        for item in pair_counts(
            table, first_rotation, second_rotation, equal_tolerance=TOLERANCE
        )
    }


def soil_count_key(rotation_id: str) -> tuple[str, str, str, None, None]:
    """The key of the soil-loss counts: soil loss names no carbon model and
    no computation (D94 keys the counts by rotation, scenario, indicator,
    carbon model and computation)."""
    return (rotation_id, SCENARIO_ID, "soil_loss", None, None)


def row_of(
    table: ResultsTable, rotation_id: str, indicator: str, ag_year: int | None
) -> ResultsTableRow:
    return next(
        row
        for row in table.rows
        if row.rotation_id == rotation_id
        and row.indicator == indicator
        and row.ag_year == ag_year
    )


# --- the table is the one supplied ---------------------------------------------


def test_the_table_is_the_one_supplied():
    table = example_table()
    assert (table.case_id, table.field_id) == (CASE_ID, FIELD_ID)
    assert len(table.rows) == 18  # per rotation: four years, one trend, one water row
    value_of = {
        (row.rotation_id, row.indicator, row.ag_year): row.value for row in table.rows
    }
    assert value_of[("A", "soil_loss", 2020)] == 8.2
    assert value_of[("A", "soil_loss", 2021)] == 7.0
    assert value_of[("A", "soil_loss", 2022)] == 9.1
    assert value_of[("A", "soil_loss", 2023)] is None
    for rotation_id in ("B", "C"):
        assert value_of[(rotation_id, "soil_loss", 2020)] == 6.1
        assert value_of[(rotation_id, "soil_loss", 2021)] == 6.5
        assert value_of[(rotation_id, "soil_loss", 2022)] == 7.0
        assert value_of[(rotation_id, "soil_loss", 2023)] == 6.8
    assert value_of[("A", "soil_carbon_trend", None)] == -0.4
    assert value_of[("B", "soil_carbon_trend", None)] == 0.3
    assert value_of[("C", "soil_carbon_trend", None)] == 0.3
    for rotation_id in ROTATIONS:
        assert value_of[(rotation_id, "water_deficit_exposure", None)] is None


# --- D1: counts by year against a declared limit --------------------------------


@pytest.mark.parametrize(
    "equal_is_within, a_soil_within, b_soil_within",
    [
        pytest.param(True, 1, 4, id="equal to the limit counts as within"),
        pytest.param(False, 0, 3, id="equal to the limit does not count as within"),
    ],
)
def test_d1_counts_by_year_against_the_declared_limit(
    equal_is_within, a_soil_within, b_soil_within
):
    table = example_table()
    counts = limit_counts(
        table, LIMITS, equal_to_limit_counts_as_within=equal_is_within
    )

    # One count per rotation, scenario, indicator, carbon model and
    # computation (D94); the scenario of this table is s1 only, and soil
    # loss names no carbon model and no computation.
    assert set(counts) == {soil_count_key(rotation_id) for rotation_id in ROTATIONS}

    # A soil loss: three years evaluated (2023 is missing), one within on
    # the inclusive setting (2021 = 7.0 exactly), none on the exclusive one.
    a_soil = counts[soil_count_key("A")]
    assert a_soil.evaluated == 3
    assert a_soil.within == a_soil_within
    assert a_soil.outside == a_soil.evaluated - a_soil.within
    # B soil loss: four years evaluated; 2022 = 7.0 exactly is the argument.
    b_soil = counts[soil_count_key("B")]
    assert b_soil.evaluated == 4
    assert b_soil.within == b_soil_within
    # C holds the same rows as B and gives the same counts.
    c_soil = counts[soil_count_key("C")]
    assert (c_soil.evaluated, c_soil.within) == (b_soil.evaluated, b_soil.within)


def test_d1_an_indicator_on_another_time_basis_gets_no_count_of_years():
    # D95: years are counted only over rows whose time basis is ag_year.
    # The soil-carbon trend is one value per rotation and the water ratio
    # here is per rotation: neither has a count of years, and the limit
    # declared for the carbon trend is not used in the counts.
    counts = limit_counts(
        example_table(), LIMITS, equal_to_limit_counts_as_within=True
    )
    assert all(key[2] != "soil_carbon_trend" for key in counts)
    assert all(key[2] != "water_deficit_exposure" for key in counts)


def test_d1_without_a_declared_limit_no_row_is_evaluated():
    # D60: without a declared limit nothing is judged. No row is
    # evaluated, the years within the limit are null, and a row without a
    # value keeps its reason in not_evaluated: a value never counts as
    # within or outside, and never as zero.
    counts = limit_counts(example_table(), {}, equal_to_limit_counts_as_within=True)
    for rotation_id in ROTATIONS:
        count = counts[soil_count_key(rotation_id)]
        assert count.limit is None
        assert count.evaluated == 0
        assert count.within is None
        assert count.outside is None
    a_not_evaluated = counts[soil_count_key("A")].not_evaluated
    assert [(entry.ag_year, entry.missing.reason) for entry in a_not_evaluated] == [
        (2023, "NO_COVERAGE")
    ]
    for rotation_id in ("B", "C"):
        assert counts[soil_count_key(rotation_id)].not_evaluated == ()


def test_d1_a_missing_year_is_not_evaluated_with_its_reason():
    counts = limit_counts(example_table(), LIMITS, equal_to_limit_counts_as_within=True)
    not_evaluated = counts[soil_count_key("A")].not_evaluated
    assert len(not_evaluated) == 1
    entry = not_evaluated[0]
    assert entry.ag_year == 2023
    assert entry.missing.reason == "NO_COVERAGE"


def test_d1_a_limit_for_an_indicator_the_table_does_not_hold_is_refused():
    limits = {"PLACEHOLDER_indicator": LIMITS["soil_loss"]}
    with pytest.raises(ValueError, match="does not hold"):
        limit_counts(
            example_table(), limits, equal_to_limit_counts_as_within=True
        )


# --- D2: paired differences between two rotations -------------------------------


def test_d2_paired_differences_second_minus_first():
    differences = by_cell(paired_differences(example_table(), "A", "B"))
    assert abs(differences[("soil_loss", 2020)].value - (-2.1)) <= TOLERANCE
    assert abs(differences[("soil_loss", 2021)].value - (-0.5)) <= TOLERANCE
    assert abs(differences[("soil_loss", 2022)].value - (-2.1)) <= TOLERANCE
    assert abs(differences[("soil_carbon_trend", None)].value - 0.7) <= TOLERANCE
    # 2023: side A holds no value, so the difference is missing with reason
    # MISSING_INPUT, naming side A; it is never 6.8 - 0.0.
    difference_2023 = differences[("soil_loss", 2023)]
    assert difference_2023.value is None
    assert difference_2023.missing.reason == "MISSING_INPUT"
    assert "A" in difference_2023.missing.detail


def test_d2_swapping_the_rotations_changes_only_the_sign():
    table = example_table()
    forward = by_cell(paired_differences(table, "A", "B"))
    backward = by_cell(paired_differences(table, "B", "A"))
    assert abs(backward[("soil_loss", 2020)].value - 2.1) <= TOLERANCE
    assert set(forward) == set(backward)
    for key, difference in forward.items():
        swapped = backward[key]
        if difference.value is None:
            assert swapped.value is None
        else:
            assert abs(swapped.value + difference.value) <= TOLERANCE


def test_d2_identical_rows_of_two_rotations_give_zero():
    differences = by_cell(paired_differences(example_table(), "B", "C"))
    assert abs(differences[("soil_loss", 2020)].value - 0.0) <= TOLERANCE
    assert abs(differences[("soil_carbon_trend", None)].value - 0.0) <= TOLERANCE


def test_d2_a_difference_is_never_taken_across_cells():
    table = example_table()
    a_2020 = row_of(table, "A", "soil_loss", 2020)
    b_2021 = row_of(table, "B", "soil_loss", 2021)
    with pytest.raises(ValueError, match="never across cells"):
        paired_difference(a_2020, b_2021)


def test_d2_rows_of_a_pair_with_different_units_are_refused():
    """A valid results table cannot hold such a pair: the contract fixes the
    unit of each indicator (C1.1). The second row is built by hand, past
    the validation of the contract, so that the refusal itself is checked."""
    annual = soil_row("A", 2020, 8.2)
    monthly = ResultsTableRow.model_construct(
        **{
            **soil_row("B", 2020, 6.1).model_dump(),
            "unit": models.UNIT_SOIL_LOSS_MONTHLY,
        }
    )
    assert annual.unit != monthly.unit
    with pytest.raises(ValueError, match="refused, with no conversion"):
        paired_difference(annual, monthly)


def test_d92_no_difference_of_this_table_has_a_range():
    """The supplied table carries no range on any value, so under D92 the
    range of every computed difference is missing with its reason (and the
    pairs take the state "Not separated: uncertainty missing", entry D7)."""
    table = example_table()
    for first, second in (("A", "B"), ("A", "C"), ("B", "C")):
        for difference in paired_differences(table, first, second):
            if difference.value is not None:
                assert difference.range is None
                assert difference.range_missing.reason == "NOT_AVAILABLE"


# --- D5: direction of each indicator and dominance between rotations ------------


def test_d5_dominance_reads_the_direction_of_each_row():
    table = example_table()
    # B is no worse than A in every shared cell (soil loss 2020, 2021 and
    # 2022, where lower is better, and the carbon trend, where higher is
    # better) and better in at least one: B is never preferred less than A.
    # The cell where A holds no value (soil loss 2023) counts neither for
    # nor against B.
    assert never_preferred_less(table, "A", "B") is True
    # A is worse than B in every shared cell.
    assert never_preferred_less(table, "B", "A") is False
    # B and C hold identical rows: neither is better in any cell, and
    # "better in at least one" fails in both directions.
    assert never_preferred_less(table, "B", "C") is False
    assert never_preferred_less(table, "C", "B") is False


def test_d5_reordering_the_rows_or_the_rotations_changes_nothing():
    table = example_table()
    # Reversing the rows also reorders the rotations of the table (the
    # rows of C now come before those of B and A).
    reordered = ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=list(reversed(table.rows)),
    )
    for first, second in (("A", "B"), ("B", "A"), ("B", "C"), ("C", "B")):
        assert never_preferred_less(
            reordered, first, second
        ) == never_preferred_less(table, first, second)


# --- D6: missing values and modules not built in the decision -------------------


def test_d6_water_gives_no_ranking_and_carries_its_reasons():
    ranking = indicator_ranking(example_table(), "water_deficit_exposure")
    assert ranking.every_value_missing is True
    assert ranking.rotations_with_a_value == frozenset()
    assert [rotation_id for rotation_id, _ in ranking.reasons] == list(ROTATIONS)
    for _, missing in ranking.reasons:
        assert missing.reason == "NOT_AVAILABLE"
        assert missing.detail == "the definition of C1.4 is incomplete"


def test_d6_a_missing_value_never_counts_as_zero_within_best_or_worst():
    table = example_table()
    # Soil loss 2023 of A is missing and never counts as zero: three years
    # are evaluated, not four, and the paired difference of 2023 is
    # missing, never 6.8 - 0.0.
    counts = limit_counts(table, LIMITS, equal_to_limit_counts_as_within=True)
    assert counts[soil_count_key("A")].evaluated == 3
    differences = by_cell(paired_differences(table, "A", "B"))
    assert differences[("soil_loss", 2023)].value is None
    # A keeps its place among the rotations that hold a value, through its
    # other years; the missing year stays a reason, never a rank.
    soil = indicator_ranking(table, "soil_loss")
    assert soil.every_value_missing is False
    assert soil.rotations_with_a_value == frozenset(ROTATIONS)
    assert [(rotation_id, missing.reason) for rotation_id, missing in soil.reasons] == [
        ("A", "NO_COVERAGE")
    ]


# --- D7: the state of a pair (D74, with the names of D88 and D97) ---------------


def test_d74_a_pair_with_a_computed_difference_and_no_range_is_not_separated():
    """Person-approved expectation of #202: every rotation pair on soil_loss
    and soil_carbon_trend of this table is "Not separated: uncertainty
    missing" (a computed difference exists; its range is missing, D92)."""
    for first, second in (("A", "B"), ("A", "C")):
        state = pair_state(example_table(), first, second)
        assert state.state == NOT_SEPARATED_UNCERTAINTY_MISSING
        assert state.identical_rows is False
        assert state.indicators_not_resolved == ("soil_carbon_trend", "soil_loss")
        # Water was never evaluated for this pair: it does not enter the
        # state (D6, D85).
        assert "water_deficit_exposure" not in state.indicators_not_resolved


def test_d85_two_rotations_with_identical_rows_are_identical():
    """Person-approved expectation of #202: B and C are "Identical" (D85: at
    least one difference holds a value and every difference of an indicator
    the pair evaluated is zero; the all-missing water difference does not
    enter the state, D6). The ranges of those differences are missing as
    well (this table carries no ranges): "Identical" is the state the
    person approved for this pair; which state comes first in general is
    OPEN as K2 of entry D7."""
    state = pair_state(example_table(), "B", "C")
    assert state.state == IDENTICAL
    assert state.identical_rows is True
    assert state.indicators_not_resolved == ("soil_carbon_trend", "soil_loss")


def test_d85_a_pair_without_a_computed_difference_is_not_evaluated():
    """Person-approved expectation of #202: the all-missing
    water_deficit_exposure is "Not evaluated", with no state (D85). The
    table here is the water rows of the supplied table alone."""
    for first, second in (("A", "B"), ("A", "C"), ("B", "C")):
        state = pair_state(water_only_table(), first, second)
        assert state.state is None  # "Not evaluated" (D85, D88): no state at all
        assert state.identical_rows is False  # a missing difference is never identical
        assert state.indicators_not_resolved == ()


# --- D87 with D99: the counts of the cells of a pair; D91: the coverage ----------


def test_d87_the_cells_of_each_pair_by_the_sign_of_the_point_value():
    table = example_table()
    # Pair (A, B): B, the second rotation, is better in the three years
    # where both hold a soil-loss value (lower is better) and in the
    # carbon trend (higher is better, 0.3 against -0.4); 2023 holds a
    # missing side, and water holds one in its only cell.
    counts = by_cell_of_pair(table, "A", "B")
    assert counts[("s1", "soil_loss")].by_point_sign == PointSignCounts(
        better=3, worse=0, equal=0, missing_side=1
    )
    assert counts[("s1", "soil_carbon_trend")].by_point_sign == PointSignCounts(
        better=1, worse=0, equal=0, missing_side=0
    )
    assert counts[("s1", "water_deficit_exposure")].by_point_sign == PointSignCounts(
        better=0, worse=0, equal=0, missing_side=1
    )
    # C holds the same rows as B, so the pair (A, C) gives the same counts.
    counts_of_a_c = by_cell_of_pair(table, "A", "C")
    for key, count in counts.items():
        assert counts_of_a_c[key].by_point_sign == count.by_point_sign


def test_d87_identical_rows_are_equal_within_the_tolerance_of_the_designer():
    counts = by_cell_of_pair(example_table(), "B", "C")
    assert counts[("s1", "soil_loss")].by_point_sign == PointSignCounts(
        better=0, worse=0, equal=4, missing_side=0
    )
    assert counts[("s1", "soil_carbon_trend")].by_point_sign == PointSignCounts(
        better=0, worse=0, equal=1, missing_side=0
    )


def test_d99_the_two_counts_are_shown_apart_and_never_added():
    """The supplied table carries no range on any value, so no cell enters
    the count by range; a cell without a range appears only in the count
    of the point signs, and nothing of one count is added to the other
    (D99)."""
    table = example_table()
    for first, second in (("A", "B"), ("A", "C"), ("B", "C")):
        for count in pair_counts(table, first, second, equal_tolerance=TOLERANCE):
            assert count.by_range == RangeClassCounts(
                strict_improvement=0, deterioration=0, not_separated=0
            )


def test_d91_the_coverage_names_the_cells_compared_out_of_the_cells_of_the_pair():
    counts = by_cell_of_pair(example_table(), "A", "B")
    soil = counts[("s1", "soil_loss")]
    # 2023 holds no value on side A: three cells compared of the four of the pair.
    assert (soil.cells_compared, soil.cells_of_the_pair) == (3, 4)
    carbon = counts[("s1", "soil_carbon_trend")]
    assert (carbon.cells_compared, carbon.cells_of_the_pair) == (1, 1)
    water = counts[("s1", "water_deficit_exposure")]
    assert (water.cells_compared, water.cells_of_the_pair) == (0, 1)
    # B and C hold a value in every soil-loss cell: all four are compared.
    counts_of_b_c = by_cell_of_pair(example_table(), "B", "C")
    assert counts_of_b_c[("s1", "soil_loss")].cells_compared == 4
    assert counts_of_b_c[("s1", "soil_loss")].cells_of_the_pair == 4
    # No minimum coverage is set (D91): a missing side lowers the coverage
    # and blocks nothing.
