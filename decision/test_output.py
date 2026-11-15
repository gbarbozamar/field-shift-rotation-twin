"""Tests of ``decision/output.py``: the decision output document of a results table.

Run with ``python -m pytest decision/test_output.py`` from the repository root.

Status: PROPOSED test cases (proposal for sub-lane L2b). The tables are the
approved thin matrix of ``demo/matrix.py`` (#240) and small hand-made tables
of plainly unreal PLACEHOLDER values. No test asserts a value of the science
beyond the logic the D entries of docs/VALIDATION.md decide.
"""

from __future__ import annotations

import json

import pytest

from contracts.decision_output import DecisionOutput
from contracts.results.models import Range, ResultsTable, ResultsTableRow
from decision.output import assemble_decision_output
from demo import matrix

KIND = "PLACEHOLDER_kind"
SOURCE = "PLACEHOLDER source: a hand-made table of this test"


def soil(rotation, scenario, year, value, low=None, high=None, missing=None):
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation,
            scenario_id=scenario,
            time_basis="ag_year",
            ag_year=year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit="t ha-1 yr-1",
            missing=missing,
        )
    return ResultsTableRow(
        rotation_id=rotation,
        scenario_id=scenario,
        time_basis="ag_year",
        ag_year=year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range=Range(low=low, high=high, kind=KIND),
        provenance="DERIVED",
        source=SOURCE,
    )


def table(rows) -> ResultsTable:
    return ResultsTable(
        case_id="PLACEHOLDER_case", field_id="PLACEHOLDER_field", rows=rows
    )


def roundtrip(document: DecisionOutput) -> dict:
    dumped = document.model_dump(mode="json")
    assert DecisionOutput.model_validate_json(json.dumps(dumped)) == document
    return dumped


# --- the thin matrix ---------------------------------------------------------------


def test_the_thin_matrix_gives_a_valid_document_of_its_rotations_and_scenarios():
    document = assemble_decision_output(matrix.thin_matrix(), example_data=True)
    roundtrip(document)
    assert document.rotations == list(matrix.ROTATIONS)
    assert document.scenarios == list(matrix.SCENARIOS)
    assert document.example_data is True
    assert [state.pair for state in document.pair_states] == [
        ["A", "B"],
        ["A", "C"],
        ["B", "C"],
    ]


def test_over_several_scenarios_a_pair_not_robust_in_one_is_not_robust_across_them():
    """D103, D117: over a set of scenarios, a robust preference only if it is
    one in every member, otherwise "Not robust across scenarios". In the thin
    matrix every pair is "Not separated: within uncertainty" in each scenario
    (the divergences of #259)."""
    document = assemble_decision_output(matrix.thin_matrix(), example_data=True)
    for state in document.pair_states:
        assert state.value == "Not robust across scenarios"
        assert state.reason == "not robust across the admitted scenarios"
        assert state.preferred_rotation_id is None
    texts = "\n".join(document.state.reasons)
    for scenario in matrix.SCENARIOS:
        assert (
            f"in scenario '{scenario}' the pair ('A', 'B') is 'Not separated: within uncertainty'"
            in texts
        )


def test_no_limit_judges_no_year_and_lists_every_row_not_evaluated():
    document = assemble_decision_output(matrix.thin_matrix(), example_data=True)
    assert all(item.limit.value is None for item in document.limits)
    assert {item.indicator for item in document.limits} == {
        "soil_loss",
        "soil_carbon_trend",
        "water_deficit_exposure",
    }
    for count in document.counts_by_year:
        assert count.years_evaluated == 0 and count.years_within_limits is None
        assert len(count.not_evaluated) == len(matrix.AG_YEARS)
        reasons = {item.missing.reason for item in count.not_evaluated}
        assert reasons <= {"NOT_DECLARED", "NO_COVERAGE"}
    assert all(
        item.minimum is None and item.missing
        for item in document.range_across_scenarios
    )


def test_no_tolerance_gives_no_count_by_sign():
    document = assemble_decision_output(matrix.thin_matrix(), example_data=False)
    assert document.example_data is False
    assert all(item.tolerance.value is None for item in document.equal_tolerances)
    assert all(
        item.by_sign_of_point_value is None and item.by_sign_of_point_value_missing
        for item in document.pair_cell_counts
    )


def test_every_computed_difference_is_derived_with_its_range_or_reason():
    document = assemble_decision_output(matrix.thin_matrix(), example_data=True)
    computed = [
        d for d in document.paired_differences if d.difference.value is not None
    ]
    assert computed
    for item in computed:
        assert item.difference.provenance == "DERIVED"
        assert (item.difference.range is None) != (
            item.difference.range_missing is None
        )
    soil_loss = [d for d in document.paired_differences if d.indicator == "soil_loss"]
    assert all(d.time_basis == "ag_year" for d in soil_loss)


# --- hand-made tables ---------------------------------------------------------------


def test_one_scenario_keeps_the_state_of_that_scenario():
    rows = [
        soil("A", "s", 2001, 2.0, 1.0, 3.0),
        soil("B", "s", 2001, 2.5, 1.5, 3.5),
    ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value == "Not separated: within uncertainty"
    assert state.reason is None and state.reason_missing is not None


@pytest.mark.parametrize(
    ("first_value", "second_value", "preferred"), [(9.0, 2.0, "B"), (2.0, 9.0, "A")]
)
def test_a_robust_preference_names_the_rotation_preferred_in_either_order(
    first_value, second_value, preferred
):
    rows = [
        soil("A", "s", 2001, first_value, first_value - 0.5, first_value + 0.5),
        soil("B", "s", 2001, second_value, second_value - 0.5, second_value + 0.5),
    ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value == "Robust preference"
    assert state.preferred_rotation_id == preferred
    assert state.reason is None


def test_robust_in_every_scenario_for_the_same_rotation_is_robust():
    rows = []
    for scenario in ("s1", "s2"):
        rows += [
            soil("A", scenario, 2001, 9.0, 8.5, 9.5),
            soil("B", scenario, 2001, 2.0, 1.5, 2.5),
        ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value == "Robust preference" and state.preferred_rotation_id == "B"


def test_robust_for_different_rotations_in_two_scenarios_is_not_robust():
    rows = [
        soil("A", "s1", 2001, 9.0, 8.5, 9.5),
        soil("B", "s1", 2001, 2.0, 1.5, 2.5),
        soil("A", "s2", 2001, 2.0, 1.5, 2.5),
        soil("B", "s2", 2001, 9.0, 8.5, 9.5),
    ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value == "Not robust across scenarios"


def test_a_pair_with_no_computed_difference_has_no_state():
    from contracts.results.models import Missing

    gone = Missing(reason="NO_COVERAGE", detail="PLACEHOLDER")
    rows = [
        soil("A", "s", 2001, None, missing=gone),
        soil("B", "s", 2001, 2.0, 1.0, 3.0),
    ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value is None and state.missing.reason == "NOT_AVAILABLE"
    assert state.coverage.cells_compared == 0


def test_differences_without_ranges_are_not_separated_uncertainty_missing():
    rows = [
        ResultsTableRow(
            **{
                **soil("A", "s", 2001, 2.0, 1.0, 3.0).model_dump(),
                "range": None,
                "range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
            }
        ),
        ResultsTableRow(
            **{
                **soil("B", "s", 2001, 2.5, 1.0, 3.0).model_dump(),
                "range": None,
                "range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
            }
        ),
        soil("A", "s", 2002, 3.0, 2.0, 4.0),
        soil("B", "s", 2002, 3.0, 2.0, 4.0),
    ]
    (state,) = assemble_decision_output(table(rows), example_data=True).pair_states
    assert state.value == "Not separated: uncertainty missing"
    assert state.reason == "a difference without its range"
