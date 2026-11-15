"""Tests of ``api/results_table.py``: the results table of two rotations from their runs.

Run with ``uv run pytest api/test_results_table.py`` from the repository root.

Status: PROPOSED test cases (unit ``l2/decision-route``). The results are the
PLACEHOLDER examples of ``contracts/results/``; no test asserts a scientific
value, only that values are copied unchanged and paired as the route decides.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from api.ports import EnginesResult, Missing, ModuleStatus, PhaseResult
from api.results_table import (
    SCENARIO_SEPARATOR,
    RotationRun,
    TableAnswer,
    build_results_table,
    scenario_id_of,
)
from contracts.results.models import ResultsPerRotation, ResultsTable

EXAMPLES = Path(__file__).parent.parent / "contracts" / "results" / "examples"
EXAMPLE = json.loads(
    (EXAMPLES / "PLACEHOLDER_results_per_rotation.json").read_text(encoding="utf-8")
)
NOT_BUILT = json.loads(
    (EXAMPLES / "PLACEHOLDER_results_per_rotation_not_built.json").read_text(
        encoding="utf-8"
    )
)
CASE, FIELD = EXAMPLE["case_id"], EXAMPLE["field_id"]
FIRST, SECOND = "PLACEHOLDER_rotation_a", "PLACEHOLDER_rotation_b"
MODULES = (ModuleStatus(id="PLACEHOLDER_MODULE", state="available"),)


def result(rotation_id: str, document: dict | None = None) -> ResultsPerRotation:
    document = copy.deepcopy(EXAMPLE if document is None else document)
    document["rotation_id"] = rotation_id
    return ResultsPerRotation.model_validate(document)


def run_of(*results: ResultsPerRotation | None, missing: Missing | None = None):
    """A run with one phase per result given (no phases when only one is given)."""

    def one(item: ResultsPerRotation | None) -> EnginesResult:
        if item is None:
            return EnginesResult(
                calendar=None,
                result=None,
                result_missing=missing
                or Missing(reason="MISSING_INPUT", detail="PLACEHOLDER_DETAIL"),
                modules=MODULES,
            )
        return EnginesResult(
            calendar=None,
            result=item,
            result_missing=None,
            modules=MODULES,
            values_present=1,
        )

    runs = [one(item) for item in results]
    if len(runs) == 1:
        return runs[0]
    phases = tuple(
        PhaseResult(scenario_id=f"phase_{index}", first_ag_year=None, result=run)
        for index, run in enumerate(runs, start=1)
    )
    first = runs[0]
    return EnginesResult(
        calendar=first.calendar,
        result=first.result,
        result_missing=first.result_missing,
        modules=first.modules,
        values_present=first.values_present,
        values_missing=first.values_missing,
        phases=phases,
    )


def build(first_run, second_run) -> TableAnswer:
    return build_results_table(
        CASE,
        FIELD,
        [RotationRun(FIRST, first_run), RotationRun(SECOND, second_run)],
    )


# --- pairing of the phases ---------------------------------------------------------


def test_one_phase_against_two_gives_every_combination():
    answer = build(run_of(result(FIRST)), run_of(result(SECOND), result(SECOND)))
    assert answer.missing is None
    ids = ["phase_1+phase_1", "phase_1+phase_2"]
    assert [s.scenario_id for s in answer.scenarios] == ids
    assert [[(p.rotation_id, p.phase) for p in s.phases] for s in answer.scenarios] == [
        [(FIRST, "phase_1"), (SECOND, "phase_1")],
        [(FIRST, "phase_1"), (SECOND, "phase_2")],
    ]
    table = answer.table
    assert isinstance(table, ResultsTable)
    assert sorted({row.scenario_id for row in table.rows}) == ids
    assert {row.rotation_id for row in table.rows} == {FIRST, SECOND}


def test_two_phases_against_two_give_four_scenarios_in_order():
    answer = build(
        run_of(result(FIRST), result(FIRST)), run_of(result(SECOND), result(SECOND))
    )
    assert [s.scenario_id for s in answer.scenarios] == [
        "phase_1+phase_1",
        "phase_1+phase_2",
        "phase_2+phase_1",
        "phase_2+phase_2",
    ]


def test_a_run_without_phases_is_phase_1():
    answer = build(run_of(result(FIRST)), run_of(result(SECOND)))
    assert [s.scenario_id for s in answer.scenarios] == ["phase_1+phase_1"]


def test_the_scenario_identifier_joins_the_phases_in_order():
    assert SCENARIO_SEPARATOR == "+"
    assert scenario_id_of(["phase_2", "phase_1"]) == "phase_2+phase_1"


# --- rows copied unchanged -----------------------------------------------------------


def test_every_value_is_copied_unchanged_and_nothing_is_left_out():
    first, second = result(FIRST), result(SECOND)
    table = build(run_of(first), run_of(second)).table
    rows = [row for row in table.rows if row.rotation_id == FIRST]
    annual = [row for row in rows if row.indicator == "soil_loss"]
    water = [row for row in rows if row.indicator == "water_deficit_exposure"]
    carbon = [row for row in rows if row.indicator == "soil_carbon_trend"]
    assert len(annual) == len(first.soil_loss.annual)
    assert len(water) == len(first.water_deficit_exposure)
    assert len(carbon) == len(first.soil_carbon_trend)
    fields = (
        "indicator",
        "direction",
        "value",
        "unit",
        "range",
        "range_missing",
        "missing",
        "provenance",
        "source",
        "assumption",
    )
    for row, item in zip(annual, first.soil_loss.annual, strict=True):
        assert (row.time_basis, row.ag_year) == ("ag_year", item.ag_year)
        assert all(getattr(row, name) == getattr(item, name) for name in fields)
    for row, item in zip(water, first.water_deficit_exposure, strict=True):
        assert (row.time_basis, row.ag_year) == (item.time_basis, item.ag_year)
        assert all(getattr(row, name) == getattr(item, name) for name in fields)
    for row, item in zip(carbon, first.soil_carbon_trend, strict=True):
        assert row.time_basis == "rotation" and row.ag_year is None
        assert (row.carbon_model, row.computation) == (
            item.carbon_model,
            item.computation,
        )
        assert all(getattr(row, name) == getattr(item, name) for name in fields)


def test_a_missing_value_stays_missing_with_its_reason():
    table = build(run_of(result(FIRST)), run_of(result(SECOND))).table
    missing = [row for row in table.rows if row.value is None]
    assert missing
    assert all(row.missing is not None and row.missing.reason for row in missing)


def test_the_table_writes_back_and_loads_unchanged():
    table = build(run_of(result(FIRST)), run_of(result(SECOND))).table
    again = ResultsTable.model_validate_json(json.dumps(table.model_dump(mode="json")))
    assert again == table


# --- no table, with its reason -------------------------------------------------------


def test_a_rotation_without_a_result_gives_no_table_with_its_reason():
    answer = build(
        run_of(result(FIRST)),
        run_of(None, missing=Missing(reason="MISSING_INPUT", detail="PLACEHOLDER")),
    )
    assert answer.table is None and answer.scenarios == ()
    assert answer.missing.reason == "MISSING_INPUT"
    assert "rotation 2 of the request" in answer.missing.detail
    assert "phase_1" in answer.missing.detail
    assert SECOND not in answer.missing.detail


def test_a_phase_without_a_result_gives_no_table():
    answer = build(run_of(result(FIRST)), run_of(result(SECOND), None))
    assert answer.table is None
    assert "phase_2" in answer.missing.detail


@pytest.mark.parametrize(
    "part", ["soil_loss", "water_deficit_exposure", "soil_carbon_trend"]
)
def test_a_part_whose_engine_is_not_built_gives_no_table(part):
    document = copy.deepcopy(EXAMPLE)
    document[part] = copy.deepcopy(NOT_BUILT[part])
    answer = build(run_of(result(FIRST, document)), run_of(result(SECOND, document)))
    assert answer.table is None
    assert answer.missing.reason == "NOT_AVAILABLE"
    assert f"'{part}'" in answer.missing.detail
    assert "rotation 1 of the request" in answer.missing.detail


def test_runs_that_do_not_hold_the_same_cells_give_no_table():
    # The example carries water by agricultural year (D157, D163); the other
    # run carries it as one value for the whole rotation, so the cells differ.
    other = copy.deepcopy(EXAMPLE)
    assert {i["time_basis"] for i in other["water_deficit_exposure"]} == {"ag_year"}
    template = {
        k: v for k, v in other["water_deficit_exposure"][0].items() if k != "ag_year"
    }
    other["water_deficit_exposure"] = [{**template, "time_basis": "rotation"}]
    answer = build(run_of(result(FIRST)), run_of(result(SECOND, other)))
    assert answer.table is None
    assert answer.missing.reason == "NOT_COMPUTABLE"
    assert "phase_1+phase_1" in answer.missing.detail
    assert FIRST not in answer.missing.detail and SECOND not in answer.missing.detail


# --- defects -------------------------------------------------------------------------


def test_a_result_of_another_rotation_is_a_defect():
    with pytest.raises(ValueError, match="identifiers"):
        build(run_of(result(FIRST)), run_of(result(FIRST)))


def test_a_result_of_another_case_is_a_defect():
    with pytest.raises(ValueError, match="identifiers"):
        build_results_table(
            "PLACEHOLDER_other_case",
            FIELD,
            [
                RotationRun(FIRST, run_of(result(FIRST))),
                RotationRun(SECOND, run_of(result(SECOND))),
            ],
        )


def test_one_rotation_is_not_enough():
    with pytest.raises(ValueError, match="two rotations"):
        build_results_table(CASE, FIELD, [RotationRun(FIRST, run_of(result(FIRST)))])


def test_a_run_without_result_and_without_reason_is_a_defect():
    no_reason = EnginesResult(calendar=None, result=None, result_missing=None)
    with pytest.raises(ValueError, match="reason"):
        build(run_of(result(FIRST)), no_reason)


def test_an_answer_holds_a_table_or_a_reason():
    with pytest.raises(ValueError):
        TableAnswer(table=None, missing=None)
