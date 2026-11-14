"""Acceptance test of the decision functions (unit l2/decision-functions).

The table below is the one supplied by a person and verified by the lead
developer on #96 (decisions D59 to D61 of #77); every expected value in
this file is that supplied one, and none is invented here. The logic
each group of tests follows is the D entry of ``docs/VALIDATION.md``
named in its title, as decided by the lead developer on 14 November
2026.

The table is labelled example data throughout; the results contract has
no field for that label (``ResultsTable`` holds only ``case_id``,
``field_id`` and ``rows``), so the label lives in this docstring, and
the sources of the numbers carry their PLACEHOLDER markers.

Run from the repository root: ``python -m pytest decision/``.
"""

from __future__ import annotations

import pytest

from contracts.results import models
from contracts.results.models import Missing, ResultsTable, ResultsTableRow
from decision.functions import (
    NOT_RESOLVED,
    DeclaredLimit,
    indicator_ranking,
    limit_counts,
    never_preferred_less,
    paired_difference,
    paired_differences,
    pair_state,
)

# The numerical tolerance of the paired differences (D2), supplied by
# the person who designed the case: absolute.
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
            rows.append(soil_row(rotation_id, ag_year, SOIL_VALUES[rotation_id].get(ag_year)))
        rows.append(carbon_row(rotation_id, CARBON_VALUES[rotation_id]))
        rows.append(water_row(rotation_id))
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


def by_cell(differences) -> dict[tuple, object]:
    """The paired differences of one pair, by indicator and agricultural year."""
    return {(item.indicator, item.ag_year): item for item in differences}


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

    # A soil loss: three years evaluated (2023 is missing), one within on
    # the inclusive setting (2021 = 7.0 exactly), none on the exclusive one.
    a_soil = counts[("A", "soil_loss")]
    assert a_soil.evaluated == 3
    assert a_soil.within == a_soil_within
    # B soil loss: four years evaluated; 2022 = 7.0 exactly is the argument.
    b_soil = counts[("B", "soil_loss")]
    assert b_soil.evaluated == 4
    assert b_soil.within == b_soil_within
    # C holds the same rows as B and gives the same counts.
    c_soil = counts[("C", "soil_loss")]
    assert (c_soil.evaluated, c_soil.within) == (b_soil.evaluated, b_soil.within)

    # The carbon trend: one value per rotation, against >= -0.1, where no
    # value equals the limit, so both settings agree.
    for rotation_id in ROTATIONS:
        carbon = counts[(rotation_id, "soil_carbon_trend")]
        assert carbon.evaluated == 1
        assert carbon.within == (0 if rotation_id == "A" else 1)

    # Water has no declared limit and no value at all: nothing is judged,
    # nothing counts as within or outside (D60 of #77).
    for rotation_id in ROTATIONS:
        water = counts[(rotation_id, "water_deficit_exposure")]
        assert water.limit is None
        assert water.evaluated == 0
        assert water.within == 0
        assert water.outside == 0
        assert [entry.missing.reason for entry in water.not_evaluated] == [
            "NOT_AVAILABLE"
        ]


def test_d1_a_missing_year_is_not_evaluated_with_its_reason():
    counts = limit_counts(example_table(), LIMITS, equal_to_limit_counts_as_within=True)
    not_evaluated = counts[("A", "soil_loss")].not_evaluated
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
    assert counts[("A", "soil_loss")].evaluated == 3
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


# --- D7: the state "not resolved" -----------------------------------------------


def test_d7_every_difference_of_this_table_is_missing_its_range():
    table = example_table()
    for first, second in (("A", "B"), ("B", "C")):
        for difference in paired_differences(table, first, second):
            if difference.value is not None:
                assert difference.range is None
                assert difference.range_missing.reason == "NOT_AVAILABLE"


def test_d7_a_pair_whose_differences_have_no_range_is_not_resolved():
    state = pair_state(example_table(), "A", "B")
    assert state.state == NOT_RESOLVED
    assert state.identical_rows is False
    assert state.indicators_not_resolved == ("soil_carbon_trend", "soil_loss")
    # Water was never evaluated for this pair: it does not enter the state (D6).
    assert "water_deficit_exposure" not in state.indicators_not_resolved


def test_d7_two_rotations_with_identical_rows_are_never_resolved():
    state = pair_state(example_table(), "B", "C")
    assert state.state == NOT_RESOLVED
    assert state.identical_rows is True
    assert state.indicators_not_resolved == ("soil_carbon_trend", "soil_loss")
