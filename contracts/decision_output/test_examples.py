"""Acceptance test of unit l0/contracts-decision-output.

The PLACEHOLDER example loads into ``DecisionOutput``, and each invalid
variant of it is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree. The example of issue #96 is held as the producer wrote
it, and a test checks that it differs from the contract only where
``README.md`` says ("Differences from the producer's example").

Run from the repository root: ``uv run pytest contracts/decision_output/``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.decision_output import DecisionOutput
from contracts.results.models import ResultsTable

HERE = Path(__file__).parent
EXAMPLE = HERE / "examples" / "PLACEHOLDER_decision_output.json"
RESULTS_TABLE_EXAMPLE = (
    HERE.parent / "results" / "examples" / "PLACEHOLDER_results_table.json"
)

Mutation = Callable[[dict[str, Any]], None]

SOIL_LOSS_LIMIT = ["limits", 0]
WATER_LIMIT = ["limits", 1]
SOIL_LOSS_COUNT = ["counts_by_year", 0]  # rotation a
WATER_COUNT = ["counts_by_year", 2]  # rotation a
SOIL_LOSS_DIFFERENCE = ["paired_differences", 0]  # 2001, a value
MISSING_DIFFERENCE = ["paired_differences", 1]  # 2002, missing
CARBON_DIFFERENCE = ["paired_differences", 3]  # amg, a value


# The example of issue #96 as the producer wrote it. It is kept unchanged:
# the landed contract differs from it in the places README.md lists under
# "Differences from the producer's example", and in no other.
PRODUCER_EXAMPLE = """
{
  "contract": "decision_output",
  "example_data": true,
  "case_id": "example-case",
  "field_id": "example-field-1",
  "rotations": ["current", "alternative-1"],
  "limits": [
    { "indicator": "soil_loss", "limit": { "value": 7.0, "unit": "t ha-1 yr-1" },
      "provenance": "DECLARED", "source": "user" }
  ],
  "counts_by_year": [
    { "rotation": "current", "indicator": "soil_loss", "years_evaluated": 27, "years_within_limits": 21 },
    { "rotation": "alternative-1", "indicator": "soil_loss", "years_evaluated": 27, "years_within_limits": 27 }
  ],
  "paired_differences": [
    {
      "pair": ["current", "alternative-1"],
      "indicator": "soil_loss",
      "difference": { "value": -2.3, "unit": "t ha-1 yr-1",
        "range_missing": { "reason": "NOT_AVAILABLE", "detail": "range of the difference not defined yet" },
        "provenance": "DERIVED", "source": "decision layer" },
      "method": "OPEN: paired-difference method and citation, person-supplied"
    }
  ],
  "state": {
    "value": "OPEN: exact wording by the science reviewers",
    "reasons": ["illustrative: alternative-1 within limits in every evaluated year; current exceeds in 6 of 27"]
  },
  "measure_first": [
    { "rank": 1, "what": "residue cover at sowing", "why": "illustrative: moves the soil-loss difference more than the evaluated inputs" }
  ]
}
"""


def load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def put(path: list[Any], value: Any) -> Mutation:
    """Set the item at ``path`` to ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def drop(path: list[Any]) -> Mutation:
    """Remove the key or the list item at ``path``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def _repeat(path: list[Any], index: int) -> Mutation:
    """Append a copy of item ``index`` of the list at ``path``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path:
            target = target[key]
        target.append(copy.deepcopy(target[index]))

    return mutate


def _limit_in_the_producer_shape(data: dict[str, Any]) -> None:
    limit = data["limits"][0]
    limit["limit"] = {"value": 7.0, "unit": "t ha-1 yr-1"}
    limit["provenance"] = "DECLARED"
    limit["source"] = "user"


def _difference_across_years(data: dict[str, Any]) -> None:
    item = data["paired_differences"][0]
    del item["time_basis"]
    del item["ag_year"]


def _swap_ranks(data: dict[str, Any]) -> None:
    data["measure_first"] = [
        {"rank": 2, "what": "PLACEHOLDER input two", "why": "PLACEHOLDER why"},
        {"rank": 1, "what": "PLACEHOLDER input one", "why": "PLACEHOLDER why"},
    ]


def _rename_scenario_list(data: dict[str, Any]) -> None:
    data["scenarios"] = ["PLACEHOLDER_scenario_two"]


def _declare_a_water_limit(data: dict[str, Any]) -> None:
    data["limits"][1]["limit"] = {
        "value": 0.5,
        "unit": "dimensionless",
        "range_missing": {"reason": "NOT_DECLARED"},
        "provenance": "DECLARED",
        "source": "user",
    }
    for count in data["counts_by_year"][2:]:
        count["years_within_limits"] = 0


def _drop_water_limit(data: dict[str, Any]) -> None:
    del data["limits"][1]


def _three_rotations_one_uncounted(data: dict[str, Any]) -> None:
    data["rotations"].append("PLACEHOLDER_rotation_c")


def _tied_ranks(data: dict[str, Any]) -> None:
    data["measure_first"] = [
        {"rank": 1, "what": "PLACEHOLDER input one", "why": "PLACEHOLDER why"},
        {"rank": 1, "what": "PLACEHOLDER input two", "why": "PLACEHOLDER why"},
        {"rank": 3, "what": "PLACEHOLDER input three", "why": "PLACEHOLDER why"},
    ]


def _resolved(data: dict[str, Any]) -> None:
    data["state"]["indicators_not_resolved"] = []
    data["measure_first"] = []


def _no_counts_no_differences(data: dict[str, Any]) -> None:
    data["limits"] = []
    data["counts_by_year"] = []
    data["paired_differences"] = []


def _swapped_pair(data: dict[str, Any]) -> None:
    item = copy.deepcopy(data["paired_differences"][0])
    item["pair"].reverse()
    item["difference"]["value"] = 4.0
    data["paired_differences"].append(item)


INVALID: list[tuple[str, Mutation, str]] = [
    ("unknown-field", put(["extra"], 1), "extra"),
    ("contract-left-out", drop(["contract"]), "contract"),
    ("contract-of-another-document", put(["contract"], "results_table"), "contract"),
    ("example-data-left-out", drop(["example_data"]), "example_data"),
    ("case-id-blank", put(["case_id"], " "), "case_id"),
    ("one-rotation", put(["rotations"], ["PLACEHOLDER_rotation_a"]), "rotations"),
    ("rotation-listed-twice", _repeat(["rotations"], 0), "more than once"),
    ("scenarios-left-out", drop(["scenarios"]), "scenarios"),
    ("no-scenario", put(["scenarios"], []), "scenarios"),
    ("limit-in-the-producer-shape", _limit_in_the_producer_shape, "Extra inputs"),
    (
        "limit-without-range-or-reason",
        drop(SOIL_LOSS_LIMIT + ["limit", "range_missing"]),
        "range",
    ),
    ("limit-without-source", drop(SOIL_LOSS_LIMIT + ["limit", "source"]), "source"),
    (
        "limit-not-declared",
        put(SOIL_LOSS_LIMIT + ["limit", "provenance"], "OBSERVED"),
        "DECLARED",
    ),
    (
        "limit-in-another-unit",
        put(SOIL_LOSS_LIMIT + ["limit", "unit"], "t ha-1 month-1"),
        "is in 't ha-1 yr-1'",
    ),
    (
        "limit-written-as-text",
        put(SOIL_LOSS_LIMIT + ["limit", "value"], "7.0"),
        "value",
    ),
    (
        "missing-limit-written-as-zero",
        put(WATER_LIMIT + ["limit", "value"], 0.0),
        "missing",
    ),
    (
        "missing-limit-without-reason",
        drop(WATER_LIMIT + ["limit", "missing"]),
        "missing",
    ),
    ("two-limits-of-one-indicator", _repeat(["limits"], 0), "more than one limit"),
    ("counted-indicator-without-limit-item", _drop_water_limit, "no item in 'limits'"),
    (
        "count-names-rotation-not-listed",
        put(SOIL_LOSS_COUNT + ["rotation_id"], "current"),
        "not in 'rotations'",
    ),
    ("count-names-scenario-not-listed", _rename_scenario_list, "not in 'scenarios'"),
    (
        "count-with-producer-key-rotation",
        put(SOIL_LOSS_COUNT + ["rotation"], "PLACEHOLDER_rotation_a"),
        "rotation",
    ),
    ("count-without-scenario", drop(SOIL_LOSS_COUNT + ["scenario_id"]), "scenario_id"),
    (
        "count-without-not-evaluated",
        drop(SOIL_LOSS_COUNT + ["not_evaluated"]),
        "not_evaluated",
    ),
    (
        "within-greater-than-evaluated",
        put(SOIL_LOSS_COUNT + ["years_within_limits"], 2),
        "greater",
    ),
    (
        "negative-count",
        put(SOIL_LOSS_COUNT + ["years_evaluated"], -1),
        "years_evaluated",
    ),
    (
        "count-written-as-text",
        put(SOIL_LOSS_COUNT + ["years_evaluated"], "1"),
        "years_evaluated",
    ),
    (
        "within-null-with-a-declared-limit",
        put(SOIL_LOSS_COUNT + ["years_within_limits"], None),
        "declared limit",
    ),
    (
        "within-counted-without-a-limit",
        put(WATER_COUNT + ["years_within_limits"], 0),
        "D60",
    ),
    ("evaluated-without-a-limit", put(WATER_COUNT + ["years_evaluated"], 1), "D60"),
    ("count-repeated", _repeat(["counts_by_year"], 0), "repeats"),
    ("rotation-left-out-of-counts", drop(["counts_by_year", 1]), "leaves out"),
    (
        "not-evaluated-without-reason",
        drop(SOIL_LOSS_COUNT + ["not_evaluated", 0, "missing"]),
        "missing",
    ),
    (
        "not-evaluated-soil-loss-per-rotation",
        put(
            SOIL_LOSS_COUNT + ["not_evaluated", 0],
            {"time_basis": "rotation", "missing": {"reason": "NO_COVERAGE"}},
        ),
        "agricultural year",
    ),
    (
        "not-evaluated-row-twice",
        _repeat(SOIL_LOSS_COUNT + ["not_evaluated"], 0),
        "same row twice",
    ),
    (
        "difference-pair-of-one-rotation",
        put(
            SOIL_LOSS_DIFFERENCE + ["pair"],
            ["PLACEHOLDER_rotation_a", "PLACEHOLDER_rotation_a"],
        ),
        "twice",
    ),
    (
        "difference-pair-of-three",
        put(
            SOIL_LOSS_DIFFERENCE + ["pair"],
            [
                "PLACEHOLDER_rotation_a",
                "PLACEHOLDER_rotation_b",
                "PLACEHOLDER_rotation_a",
            ],
        ),
        "pair",
    ),
    (
        "difference-names-rotation-not-listed",
        put(SOIL_LOSS_DIFFERENCE + ["pair", 0], "current"),
        "not in 'rotations'",
    ),
    (
        "difference-without-scenario",
        drop(SOIL_LOSS_DIFFERENCE + ["scenario_id"]),
        "scenario_id",
    ),
    ("difference-across-years", _difference_across_years, "time_basis"),
    (
        "difference-soil-loss-without-year",
        drop(SOIL_LOSS_DIFFERENCE + ["ag_year"]),
        "ag_year",
    ),
    (
        "difference-carbon-without-model",
        drop(CARBON_DIFFERENCE + ["carbon_model"]),
        "carbon model",
    ),
    (
        "difference-carbon-model-not-decided",
        put(CARBON_DIFFERENCE + ["carbon_model"], "century"),
        "carbon_model",
    ),
    (
        "difference-model-on-soil-loss",
        put(SOIL_LOSS_DIFFERENCE + ["carbon_model"], "amg"),
        "belong to 'soil_carbon_trend'",
    ),
    (
        "difference-in-another-unit",
        put(SOIL_LOSS_DIFFERENCE + ["difference", "unit"], "t ha-1 month-1"),
        "is in 't ha-1 yr-1'",
    ),
    (
        "difference-without-range-or-reason",
        drop(SOIL_LOSS_DIFFERENCE + ["difference", "range_missing"]),
        "range",
    ),
    (
        "difference-without-provenance",
        drop(SOIL_LOSS_DIFFERENCE + ["difference", "provenance"]),
        "provenance",
    ),
    (
        "missing-difference-written-as-zero",
        put(MISSING_DIFFERENCE + ["difference", "value"], 0.0),
        "missing",
    ),
    (
        "missing-difference-without-reason",
        drop(MISSING_DIFFERENCE + ["difference", "missing"]),
        "missing",
    ),
    (
        "difference-repeated",
        _repeat(["paired_differences"], 0),
        "same pair and cell twice",
    ),
    ("difference-without-method", drop(SOIL_LOSS_DIFFERENCE + ["method"]), "method"),
    ("state-without-value-or-reason", put(["state", "value"], None), "missing"),
    (
        "state-with-value-and-reason",
        put(["state", "missing"], {"reason": "NOT_AVAILABLE"}),
        "never both",
    ),
    (
        "state-without-indicators-not-resolved",
        drop(["state", "indicators_not_resolved"]),
        "indicators_not_resolved",
    ),
    (
        "state-names-unknown-indicator",
        put(["state", "indicators_not_resolved"], ["runoff"]),
        "indicators_not_resolved",
    ),
    (
        "state-names-indicator-twice",
        put(["state", "indicators_not_resolved"], ["soil_loss", "soil_loss"]),
        "twice",
    ),
    ("measure-first-rank-zero", put(["measure_first", 0, "rank"], 0), "rank"),
    ("measure-first-out-of-rank-order", _swap_ranks, "rank order"),
    (
        "measure-first-with-monetary-value",
        put(["measure_first", 0, "value_of_information"], 1.0),
        "value_of_information",
    ),
    ("measure-first-blank-why", put(["measure_first", 0, "why"], ""), "why"),
    ("uncounted-rotation", _three_rotations_one_uncounted, "leaves out"),
]

VALID: list[tuple[str, Mutation]] = [
    ("declared-water-limit", _declare_a_water_limit),
    ("tied-ranks", _tied_ranks),
    ("resolved-without-priority", _resolved),
    (
        "state-not-given",
        lambda data: data["state"].update(
            value=None, missing={"reason": "NOT_COMPUTABLE"}
        ),
    ),
    ("no-counts-no-differences", _no_counts_no_differences),
    ("swapped-pair", _swapped_pair),
    ("example-data-false", put(["example_data"], False)),
]


def test_example_loads() -> None:
    document = DecisionOutput.model_validate(load())
    assert document.example_data is True
    # Round trip: what the model writes, it reads back unchanged.
    dumped = document.model_dump(mode="json")
    assert DecisionOutput.model_validate(dumped) == document


@pytest.mark.parametrize(
    ("case", "mutation", "hint"), INVALID, ids=[case for case, *_ in INVALID]
)
def test_invalid_variant_is_rejected(case: str, mutation: Mutation, hint: str) -> None:
    data = load()
    mutation(data)
    with pytest.raises(ValidationError) as caught:
        DecisionOutput.model_validate(data)
    assert hint in str(caught.value), f"{case}: {caught.value}"


@pytest.mark.parametrize(("case", "mutation"), VALID, ids=[case for case, _ in VALID])
def test_valid_variant_is_accepted(case: str, mutation: Mutation) -> None:
    data = load()
    mutation(data)
    DecisionOutput.model_validate(data)


def test_readme_lists_every_proposed_case() -> None:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert "## PROPOSED cases" in readme
    assert "## OPEN" in readme
    listed = readme.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    for case in [case for case, *_ in INVALID] + [case for case, _ in VALID]:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"


# --- the producer's example -------------------------------------------------------


def _apply_the_listed_differences(data: dict[str, Any]) -> None:
    """Turn the example of #96 into the contract, one listed difference at a time.

    The numbers in the comments are those of README.md, "Differences from
    the producer's example".
    """
    # 1. Rotations are referenced by ``rotation_id``; the key of a count is
    # ``rotation_id``. The free labels themselves are text, so the model
    # cannot tell them from identifiers: that part is a rule for the producer.
    for count in data["counts_by_year"]:
        count["rotation_id"] = count.pop("rotation")
    # 2. Scenarios: a list, and a ``scenario_id`` on every count and difference.
    data["scenarios"] = ["example-scenario"]
    for item in data["counts_by_year"] + data["paired_differences"]:
        item["scenario_id"] = "example-scenario"
    # 3. ``limit`` is one value of C2.1: provenance and source inside it, with
    # its range or the reason it has none.
    for item in data["limits"]:
        item["limit"]["provenance"] = item.pop("provenance")
        item["limit"]["source"] = item.pop("source")
        item["limit"]["range_missing"] = {"reason": "NOT_DECLARED"}
    # 4. A count lists its rows not evaluated, with their reasons.
    for count in data["counts_by_year"]:
        count["not_evaluated"] = []
    # 5. A difference names its cell; soil loss is one value per agricultural year.
    for item in data["paired_differences"]:
        item["time_basis"] = "ag_year"
        item["ag_year"] = 2001
    # 6. The state names the indicators not resolved.
    data["state"]["indicators_not_resolved"] = []


def test_producer_example_as_written_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate(json.loads(PRODUCER_EXAMPLE))


def test_example_differs_from_the_producer_example_only_where_the_readme_says() -> None:
    """README.md, "Differences from the producer's example"."""
    data = json.loads(PRODUCER_EXAMPLE)
    _apply_the_listed_differences(data)
    DecisionOutput.model_validate(data)
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Differences from the producer's example", 1)[1]
    section = section.split("\n## ", 1)[0]
    for number in range(1, 7):
        assert f"### {number}. " in section, (
            f"README.md does not list difference {number}"
        )
    assert "### 7. " not in section


# Undoing one of the differences 2 to 6 after applying all of them.
UNDO_ONE_DIFFERENCE: dict[int, Callable[[dict[str, Any]], Any]] = {
    2: lambda d: [
        i.pop("scenario_id") for i in d["counts_by_year"] + d["paired_differences"]
    ],
    3: lambda d: [i["limit"].pop("range_missing") for i in d["limits"]],
    4: lambda d: [c.pop("not_evaluated") for c in d["counts_by_year"]],
    5: lambda d: [i.pop("time_basis") for i in d["paired_differences"]],
    6: lambda d: d["state"].pop("indicators_not_resolved"),
}


@pytest.mark.parametrize("number", sorted(UNDO_ONE_DIFFERENCE))
def test_each_listed_difference_is_needed(number: int) -> None:
    """Leaving out any one of the differences 2 to 6 leaves the example invalid.

    Difference 1 is partly a rule the model cannot check (free labels are
    text); its renamed key is checked by ``count-with-producer-key-rotation``.
    """
    data = json.loads(PRODUCER_EXAMPLE)
    _apply_the_listed_differences(data)
    UNDO_ONE_DIFFERENCE[number](data)
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate(data)


# --- the example is read off the results table example ------------------------------


def _table() -> ResultsTable:
    return ResultsTable.model_validate_json(
        RESULTS_TABLE_EXAMPLE.read_text(encoding="utf-8")
    )


def test_example_names_the_rotations_and_scenarios_of_the_results_table_example() -> (
    None
):
    document = DecisionOutput.model_validate(load())
    table = _table()
    assert (document.case_id, document.field_id) == (table.case_id, table.field_id)
    assert set(document.rotations) == {row.rotation_id for row in table.rows}
    assert set(document.scenarios) == {row.scenario_id for row in table.rows}


def test_example_rows_not_evaluated_are_the_missing_rows_of_the_table() -> None:
    document = DecisionOutput.model_validate(load())
    table = _table()
    for count in document.counts_by_year:
        expected = {
            (
                row.time_basis,
                row.ag_year,
                row.carbon_model,
                row.computation,
                row.missing.reason,
                row.missing.detail,
            )
            for row in table.rows
            if row.rotation_id == count.rotation_id
            and row.scenario_id == count.scenario_id
            and row.indicator == count.indicator
            and row.value is None
        }
        given = {
            (
                item.time_basis,
                item.ag_year,
                item.carbon_model,
                item.computation,
                item.missing.reason,
                item.missing.detail,
            )
            for item in count.not_evaluated
        }
        assert given == expected


def test_example_differences_are_second_minus_first_of_the_table() -> None:
    document = DecisionOutput.model_validate(load())
    rows = {(row.rotation_id, row.cell()): row for row in _table().rows}
    for item in document.paired_differences:
        first, second = (rows[(rotation_id, item.cell())] for rotation_id in item.pair)
        if first.value is None or second.value is None:
            assert item.difference.value is None
            assert item.difference.missing.reason == "MISSING_INPUT"
        else:
            assert item.difference.value == second.value - first.value
