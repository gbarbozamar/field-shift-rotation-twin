"""Acceptance test of units l0/contracts-decision-output and l0/decision-output-d85-d99.

The PLACEHOLDER example loads into ``DecisionOutput``, and each invalid
variant of it is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree. The example of issue #96 is held as the producer wrote
it, and a test checks that it differs from the contract only where
``README.md`` says ("Differences from the producer's example"), once the
fields that decisions D85 to D99 of issue #77 add are added.

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

from contracts.decision_output import STATE_NAMES, DecisionOutput
from contracts.results.models import CARBON_MODELS, TREND_COMPUTATIONS, ResultsTable

HERE = Path(__file__).parent
EXAMPLE = HERE / "examples" / "PLACEHOLDER_decision_output.json"
RESULTS_TABLE_EXAMPLE = (
    HERE.parent / "results" / "examples" / "PLACEHOLDER_results_table.json"
)

Mutation = Callable[[dict[str, Any]], None]

SOIL_LOSS_LIMIT = ["limits", 0]
WATER_LIMIT = ["limits", 1]
SOIL_LOSS_COUNT = ["counts_by_year", 0]  # rotation a
SOIL_LOSS_RANGE = ["range_across_scenarios", 0]  # rotation a
SOIL_LOSS_DIFFERENCE = ["paired_differences", 0]  # 2001, a value with a range
MISSING_DIFFERENCE = ["paired_differences", 1]  # 2002, missing
SOIL_LOSS_TOLERANCE = ["equal_tolerances", 0]  # a number
SOIL_LOSS_PAIR_COUNT = ["pair_cell_counts", 0]  # counted by the sign
CARBON_PAIR_COUNT = ["pair_cell_counts", 2]  # no tolerance, not counted by the sign
PAIR_STATE = ["pair_states", 0]
CARBON_DIFFERENCE = ["paired_differences", 4]  # amg, a value


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
    # The water rows are per agricultural year (D163) and none holds a value,
    # so no year is evaluated and none is within the limit (D1, D95).
    for count in data["counts_by_year"]:
        if count["indicator"] == "water_deficit_exposure":
            count["years_within_limits"] = 0
    for item in data["range_across_scenarios"]:
        if item["indicator"] == "water_deficit_exposure":
            item.pop("missing")
            item.update(
                minimum=0, maximum=0, scenario_of_the_minimum="PLACEHOLDER_scenario_one"
            )


def _drop_soil_loss_limit(data: dict[str, Any]) -> None:
    del data["limits"][0]


NO_SOIL_LOSS_LIMIT = {
    "value": None,
    "unit": "t ha-1 yr-1",
    "missing": {"reason": "NOT_DECLARED"},
}


def _without_soil_loss_limit(then: Mutation | None = None) -> Mutation:
    """The soil-loss limit is not declared; ``then`` changes the result further."""

    def mutate(data: dict[str, Any]) -> None:
        data["limits"][0]["limit"] = copy.deepcopy(NO_SOIL_LOSS_LIMIT)
        if then is not None:
            then(data)

    return mutate


def _soil_loss_limit_not_declared(data: dict[str, Any]) -> None:
    """D60: no row is evaluated; the year that held a value is not evaluated either."""
    data["limits"][0]["limit"] = copy.deepcopy(NO_SOIL_LOSS_LIMIT)
    for count in data["counts_by_year"]:
        if count["indicator"] != "soil_loss":
            continue
        count["years_evaluated"] = 0
        count["years_within_limits"] = None
        count["not_evaluated"].insert(
            0,
            {
                "time_basis": "ag_year",
                "ag_year": 2001,
                "missing": {
                    "reason": "NOT_DECLARED",
                    "detail": "PLACEHOLDER detail: no limit is declared (OPEN 6)",
                },
            },
        )
    for item in data["range_across_scenarios"]:
        if item["indicator"] != "soil_loss":
            continue
        item.update(
            minimum=None,
            maximum=None,
            scenario_of_the_minimum=None,
            missing={"reason": "NOT_DECLARED"},
        )


def _water_count_per_rotation(data: dict[str, Any]) -> None:
    for rotation_id in data["rotations"]:
        data["counts_by_year"].append(
            {
                "rotation_id": rotation_id,
                "scenario_id": "PLACEHOLDER_scenario_one",
                "indicator": "water_deficit_exposure",
                "years_evaluated": 0,
                "years_within_limits": None,
                "not_evaluated": [
                    {"time_basis": "rotation", "missing": {"reason": "NOT_AVAILABLE"}}
                ],
            }
        )


def _count_of_soil_carbon_trend(data: dict[str, Any]) -> None:
    data["limits"].append(
        {
            "indicator": "soil_carbon_trend",
            "limit": {
                "value": None,
                "unit": "t C ha-1 yr-1",
                "missing": {"reason": "NOT_DECLARED"},
            },
        }
    )
    for rotation_id in data["rotations"]:
        data["counts_by_year"].append(
            {
                "rotation_id": rotation_id,
                "scenario_id": "PLACEHOLDER_scenario_one",
                "indicator": "soil_carbon_trend",
                "carbon_model": "amg",
                "computation": "end_minus_start",
                "years_evaluated": 0,
                "years_within_limits": None,
                "not_evaluated": [],
            }
        )


def _add_scenario_two(data: dict[str, Any]) -> None:
    """A second scenario: one soil-loss count per rotation with 1 year within the
    limit, and the water counts of scenario one copied (no limit is declared)."""
    data["scenarios"].append("PLACEHOLDER_scenario_two")
    water = [
        count
        for count in data["counts_by_year"]
        if count["indicator"] == "water_deficit_exposure"
    ]
    for rotation_id in data["rotations"]:
        count = copy.deepcopy(data["counts_by_year"][0])
        count.update(
            rotation_id=rotation_id,
            scenario_id="PLACEHOLDER_scenario_two",
            years_within_limits=1,
        )
        data["counts_by_year"].append(count)
    for count in water:
        data["counts_by_year"].append(
            {**copy.deepcopy(count), "scenario_id": "PLACEHOLDER_scenario_two"}
        )


def _range_with_another_scenario_as_minimum(data: dict[str, Any]) -> None:
    _add_scenario_two(data)
    data["range_across_scenarios"][0]["scenario_of_the_minimum"] = (
        "PLACEHOLDER_scenario_two"
    )


def _range_over_two_scenarios(data: dict[str, Any]) -> None:
    """Two scenarios: the minimum is 0 in scenario one, the maximum 1 in scenario two."""
    _add_scenario_two(data)
    for item in data["range_across_scenarios"]:
        if item["indicator"] == "soil_loss":
            item["maximum"] = 1


def _state(**fields: Any) -> Mutation:
    """Replace the state of the example pair, keeping its pair and coverage."""

    def mutate(data: dict[str, Any]) -> None:
        state = data["pair_states"][0]
        for name in ("value", "missing", "reason", "reason_missing"):
            state.pop(name, None)
        state.update(fields)

    return mutate


def _not_evaluated_pair(data: dict[str, Any]) -> None:
    _state(
        value=None,
        missing={
            "reason": "MISSING_INPUT",
            "detail": "PLACEHOLDER detail: every paired difference of the pair is missing",
        },
    )(data)
    data["pair_states"][0]["coverage"]["cells_compared"] = 0


def _robust_preference(data: dict[str, Any]) -> None:
    _state(value="Robust preference")(data)
    data["pair_states"][0]["preferred_rotation_id"] = "example-rotation-2"


def _pair_count_not_given_by_sign(data: dict[str, Any]) -> None:
    item = data["pair_cell_counts"][0]
    item["by_sign_of_point_value"] = None
    item["by_sign_of_point_value_missing"] = {"reason": "NOT_DECLARED"}


# D169: "One count per pair, scenario, indicator, carbon model and
# computation" for the soil carbon trend.
WATER_PAIR_COUNT = ["pair_cell_counts", 1]


def _carbon_counts_split(
    carbon_models: tuple[str, ...], computations: tuple[str, ...]
) -> Mutation:
    """The example's one count of the soil carbon trend becomes one count per
    carbon model and computation, each with the counts of the example's (D169)."""

    def mutate(data: dict[str, Any]) -> None:
        unsplit = data["pair_cell_counts"].pop(CARBON_PAIR_COUNT[1])
        for carbon_model in carbon_models:
            for computation in computations:
                data["pair_cell_counts"].append(
                    {
                        **copy.deepcopy(unsplit),
                        "carbon_model": carbon_model,
                        "computation": computation,
                    }
                )

    return mutate


def _then(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


def _split_count_beside_the_unsplit_one(data: dict[str, Any]) -> None:
    split = copy.deepcopy(data["pair_cell_counts"][CARBON_PAIR_COUNT[1]])
    split.update(carbon_model="amg", computation="end_minus_start")
    data["pair_cell_counts"].append(split)


def _three_rotations_one_uncounted(data: dict[str, Any]) -> None:
    data["rotations"].append("example-rotation-3")


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
    for name in (
        "limits",
        "counts_by_year",
        "range_across_scenarios",
        "paired_differences",
        "equal_tolerances",
        "pair_cell_counts",
        "pair_states",
    ):
        data[name] = []


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
    ("one-rotation", put(["rotations"], ["example-rotation-1"]), "rotations"),
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
    (
        "counted-indicator-without-limit-item",
        _drop_soil_loss_limit,
        "no item in 'limits'",
    ),
    (
        "count-names-rotation-not-listed",
        put(SOIL_LOSS_COUNT + ["rotation_id"], "current"),
        "not in 'rotations'",
    ),
    ("count-names-scenario-not-listed", _rename_scenario_list, "not in 'scenarios'"),
    (
        "count-with-producer-key-rotation",
        put(SOIL_LOSS_COUNT + ["rotation"], "example-rotation-1"),
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
        _without_soil_loss_limit(),
        "D60",
    ),
    (
        "evaluated-without-a-limit",
        _without_soil_loss_limit(put(SOIL_LOSS_COUNT + ["years_within_limits"], None)),
        "D60",
    ),
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
            ["example-rotation-1", "example-rotation-1"],
        ),
        "twice",
    ),
    (
        "difference-pair-of-three",
        put(
            SOIL_LOSS_DIFFERENCE + ["pair"],
            [
                "example-rotation-1",
                "example-rotation-2",
                "example-rotation-1",
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
        drop(SOIL_LOSS_DIFFERENCE + ["difference", "range"]),
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
    # D94, D95: the key of a count, and counts of years over 'ag_year' rows only.
    ("count-of-water-per-rotation", _water_count_per_rotation, "D95"),
    ("count-of-soil-carbon-trend", _count_of_soil_carbon_trend, "D95"),
    (
        "count-names-carbon-model-on-soil-loss",
        put(SOIL_LOSS_COUNT + ["carbon_model"], "amg"),
        "belong to 'soil_carbon_trend'",
    ),
    # D96: the range across scenarios.
    (
        "range-minimum-greater-than-maximum",
        put(SOIL_LOSS_RANGE + ["minimum"], 1),
        "greater than 'maximum'",
    ),
    (
        "range-without-minimum",
        put(SOIL_LOSS_RANGE + ["minimum"], None),
        "together",
    ),
    (
        "range-without-value-or-reason",
        lambda data: data["range_across_scenarios"][0].update(
            minimum=None, maximum=None, scenario_of_the_minimum=None
        ),
        "missing",
    ),
    (
        "range-with-value-and-reason",
        put(SOIL_LOSS_RANGE + ["missing"], {"reason": "NOT_DECLARED"}),
        "never both",
    ),
    (
        "range-scenario-of-minimum-not-listed",
        put(SOIL_LOSS_RANGE + ["scenario_of_the_minimum"], "PLACEHOLDER_scenario_two"),
        "not in 'scenarios'",
    ),
    (
        "range-minimum-not-that-of-its-scenario",
        _range_with_another_scenario_as_minimum,
        "is not the minimum",
    ),
    (
        "range-of-an-uncounted-indicator",
        put(SOIL_LOSS_RANGE + ["indicator"], "soil_carbon_trend"),
        "summarises no count",
    ),
    (
        "range-names-rotation-not-listed",
        put(SOIL_LOSS_RANGE + ["rotation_id"], "current"),
        "not in 'rotations'",
    ),
    ("range-repeated", _repeat(["range_across_scenarios"], 0), "repeats"),
    ("range-with-a-mean", put(SOIL_LOSS_RANGE + ["mean"], 0.0), "mean"),
    (
        "range-with-a-share-of-scenarios",
        put(SOIL_LOSS_RANGE + ["share_of_scenarios"], 1.0),
        "share_of_scenarios",
    ),
    # D87: the tolerance of "equal".
    (
        "tolerance-not-declared",
        put(SOIL_LOSS_TOLERANCE + ["tolerance", "provenance"], "OBSERVED"),
        "DECLARED",
    ),
    (
        "tolerance-in-another-unit",
        put(SOIL_LOSS_TOLERANCE + ["tolerance", "unit"], "t ha-1 month-1"),
        "is in 't ha-1 yr-1'",
    ),
    (
        "two-tolerances-of-one-indicator",
        _repeat(["equal_tolerances"], 0),
        "more than one tolerance",
    ),
    # D87, D99: the counts of a pair's cells.
    (
        "pair-count-without-tolerance-item",
        drop(SOIL_LOSS_TOLERANCE),
        "no item in 'equal_tolerances'",
    ),
    (
        "pair-count-by-sign-without-a-tolerance",
        lambda data: data["pair_cell_counts"][2].update(
            by_sign_of_point_value={
                "better": 0,
                "worse": 1,
                "equal": 0,
                "missing_side": 1,
            },
            by_sign_of_point_value_missing=None,
        ),
        "no tolerance",
    ),
    (
        "pair-count-by-sign-without-value-or-reason",
        put(SOIL_LOSS_PAIR_COUNT + ["by_sign_of_point_value"], None),
        "by_sign_of_point_value_missing",
    ),
    (
        "pair-count-by-sign-with-value-and-reason",
        put(
            SOIL_LOSS_PAIR_COUNT + ["by_sign_of_point_value_missing"],
            {"reason": "NOT_DECLARED"},
        ),
        "never both",
    ),
    (
        "pair-count-without-range-count",
        drop(SOIL_LOSS_PAIR_COUNT + ["by_difference_range"]),
        "by_difference_range",
    ),
    (
        "pair-count-range-count-negative",
        put(SOIL_LOSS_PAIR_COUNT + ["by_difference_range", "not_separated"], -1),
        "not_separated",
    ),
    (
        "pair-count-more-ranges-than-values",
        put(SOIL_LOSS_PAIR_COUNT + ["by_difference_range", "strict_improvement"], 1),
        "D99",
    ),
    (
        "pair-count-with-a-total",
        put(SOIL_LOSS_PAIR_COUNT + ["total"], 2),
        "total",
    ),
    (
        "pair-count-with-a-p-value",
        put(SOIL_LOSS_PAIR_COUNT + ["p_value"], 0.5),
        "p_value",
    ),
    (
        "pair-count-of-one-rotation",
        put(
            SOIL_LOSS_PAIR_COUNT + ["pair"],
            ["example-rotation-1", "example-rotation-1"],
        ),
        "twice",
    ),
    (
        "pair-count-names-rotation-not-listed",
        put(SOIL_LOSS_PAIR_COUNT + ["pair", 0], "current"),
        "not in 'rotations'",
    ),
    (
        "pair-count-without-scenario",
        drop(SOIL_LOSS_PAIR_COUNT + ["scenario_id"]),
        "scenario_id",
    ),
    ("pair-count-repeated", _repeat(["pair_cell_counts"], 0), "repeats"),
    # D169: the counts of a pair's cells by carbon model and computation.
    (
        "pair-count-carbon-key-repeated",
        _then(
            _carbon_counts_split(CARBON_MODELS, TREND_COMPUTATIONS),
            _repeat(["pair_cell_counts"], 3),
        ),
        "repeats pair, scenario, indicator, carbon model and computation",
    ),
    (
        "pair-count-carbon-model-on-soil-loss",
        put(SOIL_LOSS_PAIR_COUNT + ["carbon_model"], "amg"),
        "belong to 'soil_carbon_trend' only, not to 'soil_loss' (D169)",
    ),
    (
        "pair-count-computation-on-soil-loss",
        put(SOIL_LOSS_PAIR_COUNT + ["computation"], "end_minus_start"),
        "belong to 'soil_carbon_trend' only, not to 'soil_loss' (D169)",
    ),
    (
        "pair-count-carbon-model-on-water",
        lambda data: data["pair_cell_counts"][WATER_PAIR_COUNT[1]].update(
            carbon_model="amg", computation="end_minus_start"
        ),
        "belong to 'soil_carbon_trend' only, not to 'water_deficit_exposure' (D169)",
    ),
    (
        "pair-count-carbon-model-without-computation",
        put(CARBON_PAIR_COUNT + ["carbon_model"], "amg"),
        "names its carbon model and its computation together (D169)",
    ),
    (
        "pair-count-computation-without-carbon-model",
        put(CARBON_PAIR_COUNT + ["computation"], "fitted_slope"),
        "names its carbon model and its computation together (D169)",
    ),
    (
        "pair-count-carbon-model-not-decided",
        lambda data: data["pair_cell_counts"][CARBON_PAIR_COUNT[1]].update(
            carbon_model="AMG", computation="end_minus_start"
        ),
        "Input should be 'amg' or 'rothc'",
    ),
    (
        "pair-count-computation-not-in-the-list",
        lambda data: data["pair_cell_counts"][CARBON_PAIR_COUNT[1]].update(
            carbon_model="amg", computation="slope"
        ),
        "Input should be 'end_minus_start', 'fitted_slope' or 'mean_over_cycles'",
    ),
    (
        "pair-count-carbon-split-beside-unsplit",
        _split_count_beside_the_unsplit_one,
        "a cell would be counted twice (D169)",
    ),
    # D85, D86, D88, D91, D97: the state of a pair and its coverage.
    (
        "pair-state-unknown-name",
        put(PAIR_STATE + ["value"], "not resolved"),
        "Input should be",
    ),
    (
        "pair-state-not-evaluated-as-a-name",
        _state(value="Not evaluated"),
        "Input should be",
    ),
    (
        "pair-state-without-value-or-reason",
        _state(value=None),
        "missing",
    ),
    (
        "pair-state-with-value-and-missing",
        put(PAIR_STATE + ["missing"], {"reason": "MISSING_INPUT", "detail": "x"}),
        "never both",
    ),
    (
        "pair-state-with-nothing-compared",
        put(PAIR_STATE + ["coverage", "cells_compared"], 0),
        "D85",
    ),
    (
        "not-evaluated-pair-with-a-reason",
        lambda data: (
            _not_evaluated_pair(data),
            data["pair_states"][0].update(reason="a difference without its range"),
        ),
        "D85",
    ),
    (
        "pair-state-without-its-reason",
        _state(value="Not separated: uncertainty missing"),
        "D86",
    ),
    (
        "pair-state-with-reason-of-another-state",
        put(PAIR_STATE + ["reason"], "identical rows"),
        "D86",
    ),
    (
        "pair-state-with-reason-and-reason-missing",
        put(PAIR_STATE + ["reason_missing"], {"reason": "NOT_AVAILABLE"}),
        "never both",
    ),
    (
        "within-uncertainty-with-a-reason-of-d86",
        _state(
            value="Not separated: within uncertainty",
            reason="a difference without its range",
        ),
        "D86",
    ),
    (
        "robust-preference-with-a-reason",
        lambda data: (
            _robust_preference(data),
            data["pair_states"][0].update(reason="identical rows"),
        ),
        "no reason",
    ),
    (
        "robust-preference-without-preferred-rotation",
        _state(value="Robust preference"),
        "preferred_rotation_id",
    ),
    (
        "preferred-rotation-outside-the-pair",
        lambda data: (
            _robust_preference(data),
            data["pair_states"][0].update(preferred_rotation_id="current"),
        ),
        "preferred_rotation_id",
    ),
    (
        "preferred-rotation-without-robust-preference",
        put(PAIR_STATE + ["preferred_rotation_id"], "example-rotation-2"),
        "robust preference only",
    ),
    (
        "coverage-compared-greater-than-cells",
        put(PAIR_STATE + ["coverage", "cells_compared"], 7),
        "D91",
    ),
    (
        "coverage-left-out",
        drop(PAIR_STATE + ["coverage"]),
        "coverage",
    ),
    (
        "coverage-as-a-share",
        put(PAIR_STATE + ["coverage"], 0.4),
        "coverage",
    ),
    (
        "pair-state-names-rotation-not-listed",
        put(PAIR_STATE + ["pair", 0], "current"),
        "not in 'rotations'",
    ),
    (
        "pair-state-of-one-rotation",
        put(PAIR_STATE + ["pair"], ["example-rotation-1", "example-rotation-1"]),
        "twice",
    ),
    (
        "pair-state-repeated-swapped",
        lambda data: (
            data["pair_states"].append(copy.deepcopy(data["pair_states"][0])),
            data["pair_states"][1]["pair"].reverse(),
        ),
        "more than one state",
    ),
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
    ("soil-loss-limit-not-declared", _soil_loss_limit_not_declared),
    ("range-over-two-scenarios", _range_over_two_scenarios),
    ("no-range-across-scenarios", put(["range_across_scenarios"], [])),
    ("pair-count-not-given-by-sign", _pair_count_not_given_by_sign),
    (
        "pair-count-per-carbon-model-and-computation",
        _carbon_counts_split(CARBON_MODELS, TREND_COMPUTATIONS),
    ),
    (
        "pair-count-per-carbon-model-of-the-example",
        _carbon_counts_split(CARBON_MODELS, ("end_minus_start",)),
    ),
    ("not-evaluated-pair", _not_evaluated_pair),
    (
        "identical-with-its-reason",
        _state(value="Identical", reason="identical rows"),
    ),
    (
        "not-robust-with-its-reason",
        _state(
            value="Not robust across scenarios",
            reason="not robust across the admitted scenarios",
        ),
    ),
    (
        "within-uncertainty-with-reason-missing",
        _state(
            value="Not separated: within uncertainty",
            reason_missing={
                "reason": "NOT_AVAILABLE",
                "detail": "PLACEHOLDER detail: D86 writes no reason for this state (OPEN, K3)",
            },
        ),
    ),
    (
        "uncertainty-missing-with-reason-missing",
        _state(
            value="Not separated: uncertainty missing",
            reason_missing={"reason": "NOT_AVAILABLE"},
        ),
    ),
    ("robust-preference", _robust_preference),
    ("no-pair-state", put(["pair_states"], [])),
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
    # Not a difference: the fields that D85 to D99 of issue #77 add after #96
    # (README.md, "Fields added by D85 to D99"), here left empty.
    _add_the_fields_of_d85_to_d99(data)


def _add_the_fields_of_d85_to_d99(data: dict[str, Any]) -> None:
    for name in (
        "range_across_scenarios",
        "equal_tolerances",
        "pair_cell_counts",
        "pair_states",
    ):
        data[name] = []


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


# The example uses the identifiers that chain the examples of the repository
# (the rotation definition example and the web example case); the results
# table example uses its own. This is the one place they are matched.
IDS_IN_THE_RESULTS_TABLE_EXAMPLE = {
    "example-case": "PLACEHOLDER_case",
    "example-field-1": "PLACEHOLDER_field",
    "example-rotation-1": "PLACEHOLDER_rotation_a",
    "example-rotation-2": "PLACEHOLDER_rotation_b",
}


def _table_id(identifier: str) -> str:
    return IDS_IN_THE_RESULTS_TABLE_EXAMPLE[identifier]


def _table() -> ResultsTable:
    return ResultsTable.model_validate_json(
        RESULTS_TABLE_EXAMPLE.read_text(encoding="utf-8")
    )


def test_example_names_the_rotations_and_scenarios_of_the_results_table_example() -> (
    None
):
    document = DecisionOutput.model_validate(load())
    table = _table()
    assert (_table_id(document.case_id), _table_id(document.field_id)) == (
        table.case_id,
        table.field_id,
    )
    assert {_table_id(rotation_id) for rotation_id in document.rotations} == {
        row.rotation_id for row in table.rows
    }
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
            if row.rotation_id == _table_id(count.rotation_id)
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
        first, second = (
            rows[(_table_id(rotation_id), item.cell())] for rotation_id in item.pair
        )
        if first.value is None or second.value is None:
            assert item.difference.value is None
            assert item.difference.missing.reason == "MISSING_INPUT"
        else:
            assert item.difference.value == second.value - first.value


def test_example_difference_ranges_follow_d92() -> None:
    """D92: the range of B - A is [b_low - a_high, b_high - a_low], same kind, else missing."""
    document = DecisionOutput.model_validate(load())
    rows = {(row.rotation_id, row.cell()): row for row in _table().rows}
    for item in document.paired_differences:
        if item.difference.value is None:
            continue
        first, second = (
            rows[(_table_id(rotation_id), item.cell())] for rotation_id in item.pair
        )
        if (
            first.range is None
            or second.range is None
            or first.range.kind != second.range.kind
        ):
            assert item.difference.range is None
            assert item.difference.range_missing is not None
        else:
            assert item.difference.range is not None
            assert item.difference.range.low == second.range.low - first.range.high
            assert item.difference.range.high == second.range.high - first.range.low
            assert item.difference.range.kind == first.range.kind


def test_example_pair_counts_and_coverage_agree_with_the_differences() -> None:
    """D87, D91, D99: what the model cannot see, checked for the example alone.

    The example's differences are all the cells of its one pair. Every cell
    is in the count by the sign of the point value; only a cell whose
    difference has a range is in the count by range; "k of N" counts the
    cells with a value on both sides.
    """
    document = DecisionOutput.model_validate(load())
    differences = document.paired_differences
    (state,) = document.pair_states
    assert state.coverage.cells_of_the_pair == len(differences)
    assert state.coverage.cells_compared == sum(
        item.difference.value is not None for item in differences
    )
    _check_the_counts_agree_with_the_differences(document)


def test_counts_split_by_carbon_model_agree_with_the_differences() -> None:
    """D169: the example's carbon cells, counted apart per carbon model."""
    data = load()
    _carbon_counts_split(CARBON_MODELS, ("end_minus_start",))(data)
    document = DecisionOutput.model_validate(data)
    carbon = [
        (count.carbon_model, count.computation)
        for count in document.pair_cell_counts
        if count.indicator == "soil_carbon_trend"
    ]
    assert carbon == [("amg", "end_minus_start"), ("rothc", "end_minus_start")]
    _check_the_counts_agree_with_the_differences(document)


def _check_the_counts_agree_with_the_differences(document: DecisionOutput) -> None:
    """Each count holds the differences of its key; a count without a carbon
    model holds every carbon model and computation of its indicator."""
    differences = document.paired_differences
    for count in document.pair_cell_counts:
        cells = [
            item
            for item in differences
            if item.pair == count.pair
            and item.scenario_id == count.scenario_id
            and item.indicator == count.indicator
            and count.carbon_model in (None, item.carbon_model)
            and count.computation in (None, item.computation)
        ]
        assert count.by_difference_range.cells() == sum(
            item.difference.range is not None for item in cells
        )
        if count.by_sign_of_point_value is not None:
            by_sign = count.by_sign_of_point_value
            assert by_sign.cells_with_a_value() + by_sign.missing_side == len(cells)
            assert by_sign.missing_side == sum(
                item.difference.value is None for item in cells
            )


def test_example_range_across_scenarios_is_that_of_its_counts() -> None:
    document = DecisionOutput.model_validate(load())
    for item in document.range_across_scenarios:
        within = [
            count.years_within_limits
            for count in document.counts_by_year
            if (
                count.rotation_id,
                count.indicator,
                count.carbon_model,
                count.computation,
            )
            == item.key()
        ]
        assert (item.minimum, item.maximum) == (min(within), max(within))


def test_state_names_are_those_of_d88_and_d97() -> None:
    """D88 lists five names, the first being "Not evaluated" (D85: no state); D97 adds one."""
    assert set(STATE_NAMES) == {
        "Identical",
        "Not separated: uncertainty missing",
        "Not robust across scenarios",
        "Robust preference",
        "Not separated: within uncertainty",
    }
