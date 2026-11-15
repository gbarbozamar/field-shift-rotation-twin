"""Acceptance test of the decision functions (units l2/decision-functions
#163, l2/decision-separation #202 and l2/tipping-priority-input #223).

The first table below is the one supplied by a person and verified by the
lead developer on #96 (decisions D59 to D61 of #77); every expected value
on it is that supplied one, or follows from the decisions D74 and D85 to
D99 of #77 as the person-approved expectations of #202 state them. The
second case is the v2.1 tables of #223 (issue #177, comment of 14
November 2026), approved by the designer of the case as table designer and confirmed by
the lead developer in review (D103 confirmed the design readings, D97
and D98 re-derived the rows the case carries): every value, range,
bracket, rank, state and refusal on it is that approved one, and none is
invented here. The logic each group of tests follows is the D entry of
``docs/VALIDATION.md`` named in its title, as decided by the lead
developer on 14 November 2026.

Both tables are labelled example data throughout; the results contract
has no field for that label (``ResultsTable`` holds only ``case_id``,
``field_id`` and ``rows``), so the label lives in this docstring, and
the sources of the numbers carry their PLACEHOLDER markers.

The first table carries no range on any value (``range_missing``
NOT_AVAILABLE everywhere), so on it the branches of D92, D93 and D98
that need a range are not exercised numerically; the v2.1 table of #223
carries a range on every value (one kind, PLACEHOLDER_kind, so D92
applies), and the tests on it exercise those branches and the entries
D3, D4, D10 and D12 built on them.

Run from the repository root: ``python -m pytest decision/``.
"""

from __future__ import annotations

import pytest

from contracts.results import models
from contracts.results.models import (
    Missing,
    Range,
    ResultsTable,
    ResultsTableRow,
)
from decision.functions import (
    BY_POINT_VALUE,
    IDENTICAL,
    NOT_ROBUST_ACROSS_SCENARIOS,
    NOT_SEPARATED_UNCERTAINTY_MISSING,
    NOT_SEPARATED_WITHIN_UNCERTAINTY,
    ROBUST_PREFERENCE,
    DeclaredLimit,
    Measurement,
    PairCounts,
    PointSignCounts,
    RangeClassCounts,
    UncertainInput,
    dominance,
    indicator_ranking,
    limit_counts,
    measurement_consistency,
    measurement_priority,
    never_preferred_less,
    paired_difference,
    paired_differences,
    pair_counts,
    pair_state,
    recompute_with_measurement,
    tipping_point,
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


# --- the v2.1 case of #223: every value below is the person-approved one -------


# The kind label of every range of the case: one label on all, so the two
# ranges of a pair share their kind and D92 applies (the closed list of
# kinds is OPEN, C2.3).
V21_RANGE_KIND = "PLACEHOLDER_kind"

# The fixed cells of the case, as (value, low, high): A2020, A2021 at the
# reference of u2 and B2020 at the reference of u3.
A_2020 = (8.2, 7.8, 8.6)
A_2021 = (7.4, 7.0, 7.8)
B_2020 = (6.1, 5.8, 6.5)


def v21_soil_row(
    rotation_id: str, scenario_id: str, ag_year: int, entry: tuple[float, float, float]
) -> ResultsTableRow:
    """One soil-loss row of the v2.1 case: the value with its range, both
    person-approved, one kind on every value."""
    value, low, high = entry
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        range=Range(low=low, high=high, kind=V21_RANGE_KIND),
        provenance="DERIVED",
        source=SOIL_SOURCE,
    )


def sweep_table(
    u1_values: tuple[tuple[str, tuple[float, float, float]], ...],
) -> ResultsTable:
    """A one-input table of the case: one scenario per admitted value of u1
    (D103: each value of the uncertain input is one admitted scenario),
    holding the three fixed cells and B2021 at that scenario's value."""
    rows = []
    for scenario_id, u1 in u1_values:
        rows.append(v21_soil_row("A", scenario_id, 2020, A_2020))
        rows.append(v21_soil_row("A", scenario_id, 2021, A_2021))
        rows.append(v21_soil_row("B", scenario_id, 2020, B_2020))
        rows.append(v21_soil_row("B", scenario_id, 2021, u1))
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# T1: u1 = B2021, every value with the range the person derived for it.
T1_VALUES = (
    ("u1=4.0", (4.0, 3.8, 4.2)),
    ("u1=5.5", (5.5, 5.3, 5.7)),
    ("u1=6.9", (6.9, 6.7, 7.1)),
    ("u1=8.0", (8.0, 7.8, 8.2)),
    ("u1=9.0", (9.0, 8.8, 9.2)),
)
U1 = UncertainInput(
    name="u1",
    unit=models.UNIT_SOIL_LOSS_ANNUAL,
    cell=("B", "soil_loss", "ag_year", 2021, None, None),
    values=(
        (4.0, "u1=4.0"),
        (5.5, "u1=5.5"),
        (6.9, "u1=6.9"),
        (8.0, "u1=8.0"),
        (9.0, "u1=9.0"),
    ),
)


def v21_difference(
    table: ResultsTable, scenario_id: str, ag_year: int
) -> object:
    """The paired difference of one agricultural year of one scenario of the
    v2.1 case (second rotation minus first, D2)."""
    scenario = ResultsTable(
        case_id=table.case_id,
        field_id=table.field_id,
        rows=[row for row in table.rows if row.scenario_id == scenario_id],
    )
    return next(
        difference
        for difference in paired_differences(scenario, "A", "B")
        if difference.ag_year == ag_year
    )


# --- D3 (T1): the bracket where the robust preference ends ----------------------


def test_t1_the_state_of_the_pair_at_each_value_of_the_input():
    """Person-approved expectations of #223: at 4.0 and 5.5 both cells are
    strict improvements; at 6.9 the 2021 difference range crosses zero and
    at 8.0 it touches it, and a cell whose range touches or crosses zero
    blocks a robust preference (D98) under the name D97 gives it; at 9.0
    the range lies wholly on the worse side (deterioration)."""
    table = sweep_table(T1_VALUES)
    point = tipping_point(table, "A", "B", U1)
    assert point.states == (
        (4.0, ROBUST_PREFERENCE),
        (5.5, ROBUST_PREFERENCE),
        (6.9, NOT_SEPARATED_WITHIN_UNCERTAINTY),
        (8.0, NOT_SEPARATED_WITHIN_UNCERTAINTY),
        (9.0, NOT_ROBUST_ACROSS_SCENARIOS),
    )
    # The difference ranges the person derived (D92, worst case): 2020 is
    # [−2.8, −1.3] at every value of u1, and 2021 moves with it.
    fixed = v21_difference(table, "u1=4.0", 2020)
    assert fixed.range.low == pytest.approx(-2.8, abs=TOLERANCE)
    assert fixed.range.high == pytest.approx(-1.3, abs=TOLERANCE)
    for scenario_id, low, high in (
        ("u1=4.0", -4.0, -2.8),
        ("u1=5.5", -2.5, -1.3),
        ("u1=6.9", -1.1, 0.1),
        ("u1=8.0", 0.0, 1.2),
        ("u1=9.0", 1.0, 2.2),
    ):
        difference = v21_difference(table, scenario_id, 2021)
        assert difference.range.low == pytest.approx(low, abs=TOLERANCE)
        assert difference.range.high == pytest.approx(high, abs=TOLERANCE)
    # At 8.0 the range touches zero exactly (7.8 − 7.8): it is read as
    # touching, and it blocks.
    assert v21_difference(table, "u1=8.0", 2021).range.low == 0.0


def test_t1_the_tipping_point_is_the_bracket_between_two_adjacent_values():
    point = tipping_point(sweep_table(T1_VALUES), "A", "B", U1)
    assert point.bracket == (5.5, 6.9)
    assert point.input_name == "u1"
    assert point.unit == "t ha-1 yr-1"
    assert point.reason is None
    # No interpolation inside (D3): the bracket is the pair of adjacent
    # values, nothing between them. The change of reason at 9.0 ("Not
    # separated: within uncertainty" into "Not robust across scenarios")
    # is no change of the tipping point: the state is robust preference
    # against not.


# --- D3 (T0): no tipping point ---------------------------------------------------


def test_t0_no_tipping_point_when_the_state_never_changes():
    """Person-approved expectation of #223: u1 in {4.0, 5.0, 6.0} keeps both
    cells strict improvements (6.0 gives [−2.0, −0.8]), so no tipping point
    is reported, with that reason."""
    values = (
        ("u1=4.0", (4.0, 3.8, 4.2)),
        ("u1=5.0", (5.0, 4.8, 5.2)),
        ("u1=6.0", (6.0, 5.8, 6.2)),
    )
    u1 = UncertainInput(
        name="u1",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=((4.0, "u1=4.0"), (5.0, "u1=5.0"), (6.0, "u1=6.0")),
    )
    point = tipping_point(sweep_table(values), "A", "B", u1)
    assert point.states == (
        (4.0, ROBUST_PREFERENCE),
        (5.0, ROBUST_PREFERENCE),
        (6.0, ROBUST_PREFERENCE),
    )
    assert point.bracket is None
    assert point.reason is not None
    assert "Robust preference" in point.reason
    assert "u1" in point.reason


# --- D4 (T2): what to measure first ----------------------------------------------


def t2_scenario(u1: float, u2: float, u3: float) -> str:
    return f"u1={u1},u2={u2},u3={u3}"


# The admitted values of the three inputs, each with the person-derived
# range: u1 drives B2021 (width ±0.2), u2 drives A2021 (its reference 7.4
# carries the fixed cell's range), u3 drives B2020 (same at 6.1).
T2_U1 = ((5.5, 5.3, 5.7), (9.0, 8.8, 9.2))
T2_U2 = ((7.4, 7.0, 7.8), (5.0, 4.8, 5.2))
T2_U3 = ((6.1, 5.8, 6.5), (5.0, 4.8, 5.2))


def t2_table() -> ResultsTable:
    """The whole admitted set of T2: one scenario per combination of the
    values of the three uncertain inputs."""
    rows = []
    for u1 in T2_U1:
        for u2 in T2_U2:
            for u3 in T2_U3:
                scenario_id = t2_scenario(u1[0], u2[0], u3[0])
                rows.append(v21_soil_row("A", scenario_id, 2020, A_2020))
                rows.append(v21_soil_row("A", scenario_id, 2021, u2))
                rows.append(v21_soil_row("B", scenario_id, 2020, u3))
                rows.append(v21_soil_row("B", scenario_id, 2021, u1))
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


T2_INPUTS = (
    UncertainInput(
        name="u1",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=(
            (5.5, t2_scenario(5.5, 7.4, 6.1)),
            (9.0, t2_scenario(9.0, 7.4, 6.1)),
        ),
    ),
    UncertainInput(
        name="u2",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("A", "soil_loss", "ag_year", 2021, None, None),
        values=(
            (7.4, t2_scenario(5.5, 7.4, 6.1)),
            (5.0, t2_scenario(5.5, 5.0, 6.1)),
        ),
    ),
    UncertainInput(
        name="u3",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("B", "soil_loss", "ag_year", 2020, None, None),
        values=(
            (6.1, t2_scenario(5.5, 7.4, 6.1)),
            (5.0, t2_scenario(5.5, 7.4, 5.0)),
        ),
    ),
)


def test_t2_the_base_state_over_the_whole_admitted_set_is_not_robust():
    # The set contains u1 = 9.0 (a deterioration), so the pair over the
    # whole set is "Not robust across scenarios" (D103: the set-level
    # state) and the priority list exists.
    priority = measurement_priority(t2_table(), "A", "B", T2_INPUTS)
    assert priority.base_state == NOT_ROBUST_ACROSS_SCENARIOS
    assert priority.items != ()


def test_t2_rank_one_is_shared_by_the_inputs_that_change_the_state():
    priority = measurement_priority(t2_table(), "A", "B", T2_INPUTS)
    u1, u2, u3 = priority.items
    # The ordering measure among state-changers is OPEN (D4): u1 and u2
    # tie at rank 1; u3, whose values never change the state, ranks below.
    assert (u1.rank, u1.input_name) == (1, "u1")
    assert (u2.rank, u2.input_name) == (1, "u2")
    assert (u3.rank, u3.input_name) == (2, "u3")
    assert u1.unit == u2.unit == u3.unit == "t ha-1 yr-1"
    assert u1.cell == ("B", "soil_loss", "ag_year", 2021, None, None)
    assert u2.cell == ("A", "soil_loss", "ag_year", 2021, None, None)
    assert u3.cell == ("B", "soil_loss", "ag_year", 2020, None, None)
    # u1 at 9.0 deteriorates; u2 at 5.0, with u1 at its reference, gives
    # [5.3−5.2, 5.7−4.8] wholly worse; u3 never (at 5.0 the 2020 range is
    # [−3.8, −2.6] and 2021 still strictly improves: robust either way).
    assert u1.states == ((5.5, ROBUST_PREFERENCE), (9.0, NOT_ROBUST_ACROSS_SCENARIOS))
    assert u2.states == ((7.4, ROBUST_PREFERENCE), (5.0, NOT_ROBUST_ACROSS_SCENARIOS))
    assert u3.states == ((6.1, ROBUST_PREFERENCE), (5.0, ROBUST_PREFERENCE))
    # Each item is qualitative (D4): rank, what to measure, why.
    for item in (u1, u2, u3):
        assert item.input_name in item.why


def test_d4_a_set_that_is_robust_in_every_scenario_gives_no_priority_list():
    """The empty-list case of the approved unit: a set whose only uncertain
    input is u3 (values 6.1 and 5.0) is robust in every scenario, so the
    base state is a robust preference and the priority list is empty."""
    rows = []
    for scenario_id, b2020 in (("u3=6.1", T2_U3[0]), ("u3=5.0", T2_U3[1])):
        rows.append(v21_soil_row("A", scenario_id, 2020, A_2020))
        rows.append(v21_soil_row("A", scenario_id, 2021, A_2021))
        rows.append(v21_soil_row("B", scenario_id, 2020, b2020))
        rows.append(v21_soil_row("B", scenario_id, 2021, T2_U1[0]))
    only_u3 = UncertainInput(
        name="u3",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("B", "soil_loss", "ag_year", 2020, None, None),
        values=((6.1, "u3=6.1"), (5.0, "u3=5.0")),
    )
    only_u3_table = ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)
    priority = measurement_priority(only_u3_table, "A", "B", (only_u3,))
    assert priority.base_state == ROBUST_PREFERENCE
    assert priority.items == ()


# --- D10 (T3): a measured value for one input of the list ------------------------


def measured_u1(
    value: float | None,
    low: float,
    high: float,
    unit: str = models.UNIT_SOIL_LOSS_ANNUAL,
) -> Measurement:
    return Measurement(
        input_name="u1",
        value=value,
        unit=unit,
        provenance="OBSERVED",
        range=Range(low=low, high=high, kind=V21_RANGE_KIND),
    )


def test_t3_a_measured_value_recomputes_the_decision_to_robust():
    table = sweep_table(T1_VALUES)
    measurement = measured_u1(5.5, 5.3, 5.7)
    assert measurement.provenance == "OBSERVED"  # it enters with the label (C4.1)
    recomputed = recompute_with_measurement(table, U1, measurement)
    # 2021 becomes [5.3−7.8, 5.7−7.0] = [−2.5, −1.3], wholly better; 2020
    # is unchanged: the recomputed pair is a robust preference.
    assert pair_state(recomputed, "A", "B").state == ROBUST_PREFERENCE
    # The scenario's cells the input drives change, nothing else: every
    # other row is carried into the new table unchanged, and each driven
    # row holds the measured value and range, keeping its identifier, its
    # unit and the label the contract fixes for its indicator (C4.6).
    assert len(recomputed.rows) == len(table.rows)
    for before, after in zip(table.rows, recomputed.rows):
        if before.rotation_id == "B" and before.ag_year == 2021:
            assert after.value == 5.5
            assert (after.range.low, after.range.high, after.range.kind) == (
                5.3,
                5.7,
                V21_RANGE_KIND,
            )
            assert after.range_missing is None
            assert after.missing is None
            assert after.provenance == "DERIVED"
            assert (after.rotation_id, after.scenario_id, after.ag_year) == (
                before.rotation_id,
                before.scenario_id,
                before.ag_year,
            )
        else:
            assert after == before


def test_t3_a_blank_value_is_refused_and_never_taken_as_zero():
    blank = measured_u1(None, 5.3, 5.7)
    with pytest.raises(ValueError, match="never taken as zero"):
        recompute_with_measurement(sweep_table(T1_VALUES), U1, blank)


def test_t3_a_value_in_another_unit_is_refused():
    wrong_unit = measured_u1(5.5, 5.3, 5.7, unit="t/ha")
    with pytest.raises(ValueError, match="refused"):
        recompute_with_measurement(sweep_table(T1_VALUES), U1, wrong_unit)


def test_d10_a_measurement_carries_its_range_or_its_range_missing():
    without_either = Measurement(
        input_name="u1",
        value=5.5,
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        provenance="OBSERVED",
    )
    with pytest.raises(ValueError, match="C2.2"):
        recompute_with_measurement(sweep_table(T1_VALUES), U1, without_either)


# --- D12 (T4): a measured value on one side of the bracket -----------------------


def test_t4_a_value_below_the_bracket_gives_the_state_of_that_side():
    # Measured 5.0 [4.8, 5.2] lies below the bracket (5.5, 6.9): 2021
    # becomes [−3.0, −1.8], wholly better — the robust side — and a state
    # that has become a robust preference empties the priority list (D12).
    consistency = measurement_consistency(
        sweep_table(T1_VALUES),
        "A",
        "B",
        U1,
        measured_u1(5.0, 4.8, 5.2),
        (5.5, 6.9),
        (U1,),
    )
    assert consistency.measured_value == 5.0
    assert consistency.side == "below the bracket"
    assert consistency.state_after_measurement == ROBUST_PREFERENCE
    assert consistency.priority.items == ()


def test_t4_a_value_above_the_bracket_gives_the_state_of_that_side():
    # Measured 8.5 [8.3, 8.7] lies above the bracket: 2021 becomes
    # [+0.5, +1.7], wholly worse — not robust — and the priority list
    # follows D4 over the recomputed set.
    consistency = measurement_consistency(
        sweep_table(T1_VALUES),
        "A",
        "B",
        U1,
        measured_u1(8.5, 8.3, 8.7),
        (5.5, 6.9),
        (U1,),
    )
    assert consistency.side == "above the bracket"
    assert consistency.state_after_measurement == NOT_ROBUST_ACROSS_SCENARIOS
    assert consistency.priority.base_state == NOT_ROBUST_ACROSS_SCENARIOS
    assert consistency.priority.items != ()
    # The list is the one D4 builds over the same recomputed set.
    recomputed = recompute_with_measurement(
        sweep_table(T1_VALUES), U1, measured_u1(8.5, 8.3, 8.7)
    )
    assert consistency.priority == measurement_priority(recomputed, "A", "B", (U1,))


# --- D165 to D176 of #77 (unit l2/decision-rule-d165-d176) ------------------------
#
# EXAMPLE DATA written by hand for these tests. The numbers mean nothing and
# describe no real place, field, crop or producer; each range is chosen only
# so that the range of a difference (D92: [b_low - a_high, b_high - a_low],
# second minus first) lands where the decision under test reads it. The
# fixed cells are those of the v2.1 case above: A2020 8.2 [7.8, 8.6], A2021
# 7.4 [7.0, 7.8], B2020 6.1 [5.8, 6.5], so B2020 - A2020 = [-2.8, -1.3], a
# strict improvement for B.

PLACEHOLDER_LEVEL = "PLACEHOLDER_level"


def two_cells(scenario_id, b_2021):
    """A2020, A2021, B2020 fixed, and B2021 as given, in one scenario."""
    return [
        v21_soil_row("A", scenario_id, 2020, A_2020),
        v21_soil_row("A", scenario_id, 2021, A_2021),
        v21_soil_row("B", scenario_id, 2020, B_2020),
        v21_soil_row("B", scenario_id, 2021, b_2021),
    ]


def ranged_carbon(
    rotation_id, scenario_id, entry, *, model="amg", computation="end_minus_start"
):
    value, low, high = entry
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="rotation",
        indicator="soil_carbon_trend",
        direction="higher_is_better",
        value=value,
        unit=models.UNIT_SOIL_CARBON_TREND,
        carbon_model=model,
        computation=computation,
        range=Range(low=low, high=high, kind=V21_RANGE_KIND),
        provenance="SIMULATED",
        source=CARBON_SOURCE,
    )


def soil_missing(rotation_id, scenario_id, ag_year):
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=None,
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        missing=NO_COVERAGE,
    )


def hand_table(rows):
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# D165: "No. It is non-deteriorating and it is not a strict improvement."


def test_d165_a_range_touching_zero_on_the_side_not_worse_does_not_block():
    # B2021 6.9 [6.8, 7.0]: B2021 - A2021 = [6.8 - 7.8, 7.0 - 7.0] = [-1.0, 0.0].
    table = hand_table(two_cells("s1", (6.9, 6.8, 7.0)))
    touching = v21_difference(table, "s1", 2021)
    assert touching.range.high == 0.0
    state = pair_state(table, "A", "B")
    assert state.state == ROBUST_PREFERENCE
    assert state.indicators_not_resolved == ()
    # The count by range keeps the three classes of D99 (D167): the cell is
    # "not separated" in the sense of D93 although it does not block.
    (counts,) = pair_counts(table, "A", "B", equal_tolerance=TOLERANCE)
    assert counts.by_range == RangeClassCounts(
        strict_improvement=1, deterioration=0, not_separated=1
    )


def test_d165_a_range_touching_zero_on_the_worse_side_blocks():
    # B2021 8.0 [7.8, 8.2]: [7.8 - 7.8, 8.2 - 7.0] = [0.0, 1.2]: it is not
    # non-deteriorating (D98), so it blocks (D165).
    state = pair_state(hand_table(two_cells("s1", (8.0, 7.8, 8.2))), "A", "B")
    assert state.state == NOT_SEPARATED_WITHIN_UNCERTAINTY
    assert state.indicators_not_resolved == ("soil_loss",)


def test_d165_a_touching_cell_alone_gives_no_strict_improvement():
    # Only the cell [-1.0, 0.0]: nothing blocks, but no cell is a strict
    # improvement (D93, D153), so the pair is not a robust preference; it
    # takes the name of D97 ("touches or crosses zero"). No indicator has a
    # blocking cell, so none is named (D165, follow-up).
    rows = [
        v21_soil_row("A", "s1", 2021, A_2021),
        v21_soil_row("B", "s1", 2021, (6.9, 6.8, 7.0)),
    ]
    state = pair_state(hand_table(rows), "A", "B")
    assert state.state == NOT_SEPARATED_WITHIN_UNCERTAINTY
    assert state.indicators_not_resolved == ()


def test_d165_a_carbon_range_touching_zero_from_the_better_side_does_not_block():
    # Carbon, higher is better: A 0.3 [0.2, 0.4], B 0.5 [0.4, 0.6] give
    # [0.4 - 0.4, 0.6 - 0.2] = [0.0, 0.4]; soil loss B2020 - A2020 strict.
    rows = [
        v21_soil_row("A", "s1", 2020, A_2020),
        v21_soil_row("B", "s1", 2020, B_2020),
        ranged_carbon("A", "s1", (0.3, 0.2, 0.4)),
        ranged_carbon("B", "s1", (0.5, 0.4, 0.6)),
    ]
    assert pair_state(hand_table(rows), "A", "B").state == ROBUST_PREFERENCE


# D166: "The state is read in each single scenario, in the order of D152.
# Over a set, the pair is a robust preference only if it is one in every
# member; otherwise it is "Not robust across scenarios" ... The cells of
# different scenarios are never read as one scenario."


def test_d166_a_set_with_one_robust_scenario_and_one_crossing_zero_is_not_robust():
    # s1: B2021 5.5 [5.3, 5.7] -> [-2.5, -1.3], strict. s2: B2021 7.3
    # [7.1, 7.5] -> [-0.7, 0.5], crossing zero.
    table = hand_table(
        two_cells("s1", (5.5, 5.3, 5.7)) + two_cells("s2", (7.3, 7.1, 7.5))
    )
    state = pair_state(table, "A", "B")
    assert state.state == NOT_ROBUST_ACROSS_SCENARIOS
    assert state.by_scenario == (
        ("s1", ROBUST_PREFERENCE),
        ("s2", NOT_SEPARATED_WITHIN_UNCERTAINTY),
    )
    assert state.indicators_not_resolved == ("soil_loss",)
    # D103 (2): the base state of D4 is the state over the whole set.
    u1 = UncertainInput(
        name="u1",
        unit=models.UNIT_SOIL_LOSS_ANNUAL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=((5.5, "s1"), (7.3, "s2")),
    )
    priority = measurement_priority(table, "A", "B", (u1,))
    assert priority.base_state == NOT_ROBUST_ACROSS_SCENARIOS
    assert [item.rank for item in priority.items] == [1]


def test_d166_a_set_whose_members_are_all_identical_is_not_robust():
    # D166: "This holds even when every member has the same state that is
    # not a robust preference." A and B hold the same values and ranges.
    rows = []
    for scenario_id in ("s1", "s2"):
        rows.append(v21_soil_row("A", scenario_id, 2020, B_2020))
        rows.append(v21_soil_row("B", scenario_id, 2020, B_2020))
    state = pair_state(hand_table(rows), "A", "B")
    assert state.state == NOT_ROBUST_ACROSS_SCENARIOS
    assert state.by_scenario == (("s1", IDENTICAL), ("s2", IDENTICAL))
    assert state.identical_rows is True


def test_d166_a_set_robust_in_every_scenario_is_a_robust_preference():
    table = hand_table(
        two_cells("s1", (5.5, 5.3, 5.7)) + two_cells("s2", (5.0, 4.8, 5.2))
    )
    state = pair_state(table, "A", "B")
    assert state.state == ROBUST_PREFERENCE
    assert state.by_scenario == (
        ("s1", ROBUST_PREFERENCE),
        ("s2", ROBUST_PREFERENCE),
    )


# D175: "A member without a state is not a robust preference and holds no
# strictly improving cell, so the set is "Not robust across scenarios"."


def test_d175_a_set_with_one_scenario_not_evaluated_is_not_robust():
    rows = [
        v21_soil_row("A", "s1", 2020, A_2020),
        v21_soil_row("B", "s1", 2020, B_2020),
        v21_soil_row("A", "s2", 2020, A_2020),
        soil_missing("B", "s2", 2020),
    ]
    state = pair_state(hand_table(rows), "A", "B")
    assert state.state == NOT_ROBUST_ACROSS_SCENARIOS
    assert state.by_scenario == (("s1", ROBUST_PREFERENCE), ("s2", None))


def test_d175_a_set_with_no_value_in_any_scenario_has_no_state():
    rows = []
    for scenario_id in ("s1", "s2"):
        rows.append(v21_soil_row("A", scenario_id, 2020, A_2020))
        rows.append(soil_missing("B", scenario_id, 2020))
    state = pair_state(hand_table(rows), "A", "B")
    assert state.state is None  # D85: not evaluated, with no state
    assert state.by_scenario == (("s1", None), ("s2", None))


# D117: "The state at a value of the input is the state over all the phases
# at that value, read as D74 reads a set of scenarios".


def test_d117_the_phases_nested_in_a_value_give_the_state_at_that_value():
    # Value 1: phase p1 strict (B2021 5.5), phase p2 crossing (B2021 7.3);
    # value 2: both phases strict (B2021 5.0 and 5.5).
    spec = {
        ("v1", "p1"): (5.5, 5.3, 5.7),
        ("v1", "p2"): (7.3, 7.1, 7.5),
        ("v2", "p1"): (5.0, 4.8, 5.2),
        ("v2", "p2"): (5.5, 5.3, 5.7),
    }
    rows = []
    for (value, phase), b_2021 in spec.items():
        rows += two_cells(f"{value}|{phase}", b_2021)
    table = hand_table(rows)
    nested = UncertainInput(
        name="u",
        unit=PLACEHOLDER_LEVEL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=((1.0, ("v1|p1", "v1|p2")), (2.0, ("v2|p1", "v2|p2"))),
    )
    point = tipping_point(table, "A", "B", nested)
    assert point.states == (
        (1.0, NOT_ROBUST_ACROSS_SCENARIOS),
        (2.0, ROBUST_PREFERENCE),
    )
    assert point.bracket == (1.0, 2.0)
    # Naming one phase per value reads that phase only: no tipping point.
    one_phase = UncertainInput(
        name="u",
        unit=PLACEHOLDER_LEVEL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=((1.0, "v1|p1"), (2.0, "v2|p1")),
    )
    assert tipping_point(table, "A", "B", one_phase).bracket is None
    # D117: a phase is not an uncertain input; the priority list ranks the
    # input by its state at each value, over its phases.
    priority = measurement_priority(table, "A", "B", (nested,))
    assert priority.base_state == NOT_ROBUST_ACROSS_SCENARIOS
    assert [(item.input_name, item.rank) for item in priority.items] == [("u", 1)]


def test_d117_a_value_that_names_no_scenario_is_refused():
    table = hand_table(two_cells("s1", (5.5, 5.3, 5.7)))
    empty = UncertainInput(
        name="u",
        unit=PLACEHOLDER_LEVEL,
        cell=("B", "soil_loss", "ag_year", 2021, None, None),
        values=((1.0, ()),),
    )
    with pytest.raises(ValueError, match="names no scenario"):
        tipping_point(table, "A", "B", empty)


# D173: "The one used to compare rotations: the one the user chose, and
# end_minus_start when the user has not chosen ... The other two are shown
# and counted (D99, by computation, D169) and do not enter the state."


def three_computations_table():
    # Soil loss strict; AMG end_minus_start [0.1, 0.5] strict, fitted_slope
    # [-0.1, 0.2] crossing zero, mean_over_cycles [0.1, 0.5] strict.
    rows = [
        v21_soil_row("A", "s1", 2020, A_2020),
        v21_soil_row("B", "s1", 2020, B_2020),
    ]
    for computation, a, b in (
        ("end_minus_start", (0.0, -0.1, 0.1), (0.3, 0.2, 0.4)),
        ("fitted_slope", (0.1, 0.0, 0.2), (0.15, 0.1, 0.2)),
        ("mean_over_cycles", (0.1, 0.0, 0.2), (0.4, 0.3, 0.5)),
    ):
        rows.append(ranged_carbon("A", "s1", a, computation=computation))
        rows.append(ranged_carbon("B", "s1", b, computation=computation))
    return hand_table(rows)


def test_d173_only_the_computation_used_to_compare_enters_the_state():
    table = three_computations_table()
    # The user has not chosen: end_minus_start (C1.6).
    assert pair_state(table, "A", "B").state == ROBUST_PREFERENCE
    chosen = pair_state(table, "A", "B", trend_computation="fitted_slope")
    assert chosen.state == NOT_SEPARATED_WITHIN_UNCERTAINTY
    assert chosen.indicators_not_resolved == ("soil_carbon_trend",)
    with pytest.raises(ValueError, match="not a computation"):
        pair_state(table, "A", "B", trend_computation="PLACEHOLDER_computation")


# D169: "One count per pair, scenario, indicator, carbon model and
# computation".


def test_d169_the_counts_are_split_by_carbon_model_and_computation():
    counts = {
        (item.indicator, item.carbon_model, item.computation): item
        for item in pair_counts(
            three_computations_table(), "A", "B", equal_tolerance=TOLERANCE
        )
    }
    assert set(counts) == {
        ("soil_loss", None, None),
        ("soil_carbon_trend", "amg", "end_minus_start"),
        ("soil_carbon_trend", "amg", "fitted_slope"),
        ("soil_carbon_trend", "amg", "mean_over_cycles"),
    }
    assert counts[
        ("soil_carbon_trend", "amg", "fitted_slope")
    ].by_range == RangeClassCounts(strict_improvement=0, deterioration=0, not_separated=1)
    rows = [
        v21_soil_row("A", "s1", 2020, A_2020),
        v21_soil_row("B", "s1", 2020, B_2020),
    ]
    for model in ("amg", "rothc"):
        rows.append(ranged_carbon("A", "s1", (0.0, -0.1, 0.1), model=model))
        rows.append(ranged_carbon("B", "s1", (0.3, 0.2, 0.4), model=model))
    by_model = [
        (item.carbon_model, item.cells_of_the_pair)
        for item in pair_counts(hand_table(rows), "A", "B", equal_tolerance=TOLERANCE)
        if item.indicator == "soil_carbon_trend"
    ]
    assert by_model == [("amg", 1), ("rothc", 1)]


# D174: dominance "returns its basis ("by point value") with the coverage
# "k of N" of D91".


def test_d174_dominance_carries_its_basis_and_its_coverage():
    table = example_table()
    record = dominance(table, "A", "B")
    assert record.basis == BY_POINT_VALUE == "by point value"
    assert record.never_preferred_less is never_preferred_less(table, "A", "B")
    counts = pair_counts(table, "A", "B", equal_tolerance=TOLERANCE)
    assert record.cells_compared == sum(item.cells_compared for item in counts)
    assert record.cells_of_the_pair == sum(item.cells_of_the_pair for item in counts)
