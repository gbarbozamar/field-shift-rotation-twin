"""Acceptance test of unit l2/plant-answer-contract (brief S-018a). PROPOSED.

Both PLACEHOLDER examples load into their models; the literals of the contract
equal those of ``economics/``, ``kinds_of_year/`` and ``api/rain_stress.py``;
the examples say they are example data; and each invalid variant is rejected.
The tests that read ``kinds_of_year/`` or ``api/rain_stress.py`` are skipped
while those modules are not on ``main`` (#387); the contract imports neither.
The variants are listed in ``README.md`` under "PROPOSED cases"; a test checks
that the two lists agree.

Run from the repository root: ``uv run pytest contracts/plant_answer/``.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from contracts.economic_facts import KINDS_OF_YEAR

from .plant_answer import (
    ANSWER_SCOPE,
    D148_SOIL_LOSS_LABEL,
    D249_LABELS,
    DIMENSIONLESS,
    MARGIN_SOURCE,
    MARGINS_OF,
    PHASE_ONE_ONLY,
    STRESS_TEST_LABEL,
    Answer,
    Direction,
    MarginOf,
    OptionState,
    PlantAnswer,
    PlantRequest,
    Strictness,
    Verdict,
    check_answer_against_request,
)

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
REQUEST = "PLACEHOLDER_plant_request.json"
ANSWER = "PLACEHOLDER_plant_answer.json"
README = HERE / "README.md"

Mutation = Callable[[dict[str, Any]], None]

# In the answer example: option 0 does not meet the limit, option 1 is
# chosen, option 2 is not resolved.
NOT_MET, CHOSEN, UNRESOLVED = (["options", i] for i in range(3))


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def at(data: dict[str, Any], path: list[Any]) -> Any:
    for key in path:
        data = data[key]
    return data


def put(path: list[Any], value: Any) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        at(data, path[:-1])[path[-1]] = copy.deepcopy(value)

    return mutate


def copy_from(target: list[Any], source: list[Any]) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        at(data, target[:-1])[target[-1]] = copy.deepcopy(at(data, source))

    return mutate


def both(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


def drop(path: list[Any], *keys: str) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        item = at(data, path)
        for key in keys:
            del item[key]

    return mutate


def label_real_soil_losses(data: dict[str, Any]) -> None:
    """D148: every present soil-loss value carries the label of D148."""
    for option in data["options"]:
        for item in option["soil_loss"].values():
            if item["value"] is not None:
                item["label"] = D148_SOIL_LOSS_LABEL


def range_around(path: list[Any], low: float, high: float) -> Mutation:
    """The item's range instead of its range_missing (C2.1, C2.2)."""

    def mutate(data: dict[str, Any]) -> None:
        item = at(data, path)
        item.pop("range_missing")
        item["range"] = {"low": low, "high": high, "kind": "PLACEHOLDER"}

    return mutate


def keep_rotations(count: int) -> Mutation:
    """``count`` rotations, made from the example's, each with its own id."""

    def mutate(data: dict[str, Any]) -> None:
        rotations = data["rotations"]
        made = []
        for i in range(count):
            rotation = copy.deepcopy(rotations[i % len(rotations)])
            rotation["rotation_id"] = f"example-rotation-{i}"
            made.append(rotation)
        data["rotations"] = made

    return mutate


# (case identifier, mutation, fragment of the expected error).
INVALID_REQUEST: list[tuple[str, Mutation, str]] = [
    ("request-with-two-rotations", keep_rotations(2), "at least 3"),
    ("request-with-six-rotations", keep_rotations(6), "at most 5"),
    (
        "request-with-a-duplicate-rotation-id",
        copy_from(["rotations", 1, "rotation_id"], ["rotations", 0, "rotation_id"]),
        "share the rotation_id",
    ),
    (
        "request-site-and-facts-of-different-fields",
        put(["economic_facts", "field_id"], "example-field-2"),
        "are those of the site",
    ),
    (
        "request-rotation-of-another-field",
        put(["rotations", 2, "field_id"], "example-field-2"),
        "another field than the site",
    ),
    (
        "request-price-range-low-not-below-high",
        put(["questions", "soybean_price_range", "low"], 600.0),
        "low is below high",
    ),
    (
        "request-price-range-in-another-unit",
        put(["questions", "soybean_price_range", "unit"], "USD kg-1"),
        "USD t-1",
    ),
    (
        "request-margin-of-not-in-margins-of",
        put(["questions", "margin_of"], "dry"),
        "margin_of",
    ),
    (
        "request-strictness-not-in-the-list",
        put(["questions", "strictness"], "most_years"),
        "strictness",
    ),
    (
        "request-soybean-crop-ids-empty",
        put(["questions", "soybean_crop_ids"], []),
        "soybean_crop_ids",
    ),
    (
        "request-soybean-crop-ids-repeated",
        put(
            ["questions", "soybean_crop_ids"],
            ["PLACEHOLDER_soybean", "PLACEHOLDER_soybean"],
        ),
        "repeated",
    ),
    (
        "request-soybean-crop-not-a-grain-crop",
        put(["questions", "soybean_crop_ids"], ["PLACEHOLDER_pasture"]),
        "grain crop",
    ),
    (
        "request-soybean-crop-sown-by-no-rotation",
        both(
            lambda d: d["economic_facts"]["crops"].append(
                {
                    **copy.deepcopy(d["economic_facts"]["crops"][0]),
                    "crop_id": "PLACEHOLDER_soybean_2",
                }
            ),
            put(["questions", "soybean_crop_ids"], ["PLACEHOLDER_soybean_2"]),
        ),
        "sown by at least one rotation",
    ),
    (
        "request-rotation-sows-an-undeclared-crop",
        put(["rotations", 2, "components", 2, "crop_id"], "PLACEHOLDER_other_crop"),
        "every crop sown is declared in economic_facts",
    ),
    (
        "request-soil-loss-limit-in-another-unit",
        put(["soil_loss_limit", "unit"], "t ha-1"),
        "t ha-1 yr-1",
    ),
    (
        "request-soil-loss-limit-not-declared",
        put(["soil_loss_limit", "provenance"], "OBSERVED"),
        "DECLARED",
    ),
    (
        "request-rain-stress-factor-zero",
        put(["questions", "rain_stress_factor", "value"], 0.0),
        "above zero",
    ),
    (
        "request-rain-stress-factor-with-a-unit",
        put(["questions", "rain_stress_factor", "unit"], "mm"),
        "dimensionless",
    ),
    (
        "request-soybean-crops-with-different-prices",
        both(
            lambda d: d["economic_facts"]["crops"].append(
                {
                    **copy.deepcopy(d["economic_facts"]["crops"][0]),
                    "crop_id": "PLACEHOLDER_soybean_2",
                }
            ),
            put(["economic_facts", "crops", 3, "price", "value"], 410.0),
            put(
                ["questions", "soybean_crop_ids"],
                ["PLACEHOLDER_soybean", "PLACEHOLDER_soybean_2"],
            ),
        ),
        "these carry different prices",
    ),
    (
        "request-rotations-with-different-start-months",
        put(["rotations", 2, "ag_year_start", "month"], 8),
        "the same ag_year_start month",
    ),
]

MISSING_COST = {
    "value": None,
    "against": None,
    "costs_nothing": False,
    "reason": "NOT_COMPUTABLE",
    "detail": "example detail: no rotation is chosen",
    "unit": "USD ha-1 yr-1",
}
MEETS = {"verdict": "meets", "reason": None, "detail": None}

# Nothing chosen: the answer is not resolved, the chosen option only meets.
NOTHING_CHOSEN = both(
    put(["answer"], "not_resolved"),
    put(["chosen"], None),
    put(["reason"], "NOT_COMPUTABLE"),
    put(["detail"], "example detail: the data cannot separate these"),
    put([*CHOSEN, "state"], "meets"),
    put(["limit_cost"], MISSING_COST),
)
# The option not resolved meets the limit on average instead, so it can tie.
UNRESOLVED_MEETS = both(
    put([*UNRESOLVED, "limit", "on_average"], MEETS),
    put([*UNRESOLVED, "limit_check"], MEETS),
    put([*UNRESOLVED, "state"], "meets"),
)
BOTH_THAT_MEET = [
    "example-rotation-soybean-cover",
    "example-rotation-soybean-cover-pasture",
]
TIPPING_UP_AT = {
    "direction": "up",
    "price": 300.0,
    "takes_over": None,
    "answer_after": "not_resolved",
    "distance_percent": 5.0,
    "reason": None,
    "detail": None,
    "unit": "USD t-1",
    "provenance": "DERIVED",
    "range_missing": {"reason": "NOT_AVAILABLE", "detail": "example detail"},
}
MARGIN = [*CHOSEN, "margin", "average"]
SOIL_LOSS = [*CHOSEN, "soil_loss", "average"]

INVALID_ANSWER: list[tuple[str, Mutation, str]] = [
    (
        "answer-tied-with-one-rotation",
        both(NOTHING_CHOSEN, put(["tied"], ["example-rotation-soybean-cover"])),
        "at least two rotations",
    ),
    (
        "answer-tied-rotation-not-in-state-meets",
        both(NOTHING_CHOSEN, put(["tied"], BOTH_THAT_MEET)),
        "every tied rotation is an option in state meets",
    ),
    (
        "answer-none-meets-with-an-option-that-meets",
        both(
            NOTHING_CHOSEN,
            put(["answer"], "none_meets"),
            put(["reason"], "NOT_APPLICABLE"),
        ),
        "every option is in state does_not_meet",
    ),
    (
        "answer-kind-of-year-present-with-a-detail",
        put(["kinds_of_year", "years", 0, "detail"], "example detail"),
        "a present kind carries no missing detail",
    ),
    (
        "answer-present-margin-with-a-detail",
        put([*CHOSEN, "margin", "average", "detail"], "example detail"),
        "a present margin carries no missing detail",
    ),
    (
        "answer-tipping-up-below-today",
        put(["tipping_price", "up"], TIPPING_UP_AT),
        "up.price is at or above today",
    ),
    (
        "answer-tipping-price-outside-the-range",
        both(
            put(["tipping_price", "down", "price"], 150.0),
            put(["tipping_price", "down", "distance_percent"], -62.5),
        ),
        "a tipping price is inside the range",
    ),
    (
        "answer-tipping-distance-sign-not-the-direction",
        put(["tipping_price", "down", "distance_percent"], 6.0),
        "not negative up and not positive down",
    ),
    (
        "answer-tipping-today-missing-without-a-reason",
        put(["tipping_price", "today"], None),
        "a missing today's price carries a reason and a detail",
    ),
    (
        "answer-tipping-shared-reason-not-on-both-points",
        both(
            put(["tipping_price", "reason"], "MISSING_INPUT"),
            put(["tipping_price", "detail"], "example detail"),
        ),
        "a shared reason is on both points",
    ),
    (
        "answer-limit-kinds-not-met-not-the-checks",
        put([*NOT_MET, "limit", "kinds_not_met"], ["el_nino", "neutral"]),
        "kinds_not_met are the kinds in the record",
    ),
    (
        "answer-limit-kind-not-in-the-record-and-not-met",
        put([*NOT_MET, "limit", "kinds_not_in_record"], ["la_nina"]),
        "kinds_not_met are the kinds in the record",
    ),
    (
        "answer-limit-kind-not-in-the-record-with-a-resolved-check",
        both(
            put([*NOT_MET, "limit", "kinds_not_in_record"], ["la_nina"]),
            put([*NOT_MET, "limit", "kinds_not_met"], ["el_nino", "neutral"]),
        ),
        "the check of a kind not in the record is not resolved",
    ),
    (
        "answer-limit-missing-with-a-resolved-check",
        put([*NOT_MET, "limit", "limit"], None),
        "with no limit, no check is resolved",
    ),
    (
        "answer-limit-every-kind-not-the-kinds",
        put([*CHOSEN, "limit", "every_kind"], MEETS),
        "every_kind is does_not_meet when a kind",
    ),
    (
        "answer-missing-margin-written-as-zero-with-a-reason",
        both(
            put([*UNRESOLVED, "margin", "la_nina", "value"], 0.0),
            put([*UNRESOLVED, "margin", "la_nina", "reason"], "MISSING_INPUT"),
            put([*UNRESOLVED, "margin", "la_nina", "detail"], "example detail"),
        ),
        "a value or a reason, never both",
    ),
    (
        "answer-value-with-a-reason",
        both(
            put([*CHOSEN, "soil_loss", "neutral", "reason"], "NOT_COMPUTABLE"),
            put([*CHOSEN, "soil_loss", "neutral", "detail"], "example detail"),
        ),
        "a value or a reason, never both",
    ),
    (
        "answer-missing-value-without-a-reason",
        put([*CHOSEN, "margin", "average", "value"], None),
        "carries its reason",
    ),
    (
        "answer-chosen-without-a-rotation",
        both(put(["chosen"], None), put([*CHOSEN, "state"], "meets")),
        "exactly when the answer is chosen",
    ),
    (
        "answer-reason-on-a-chosen-answer",
        both(put(["reason"], "NOT_COMPUTABLE"), put(["detail"], "example detail")),
        "exactly when nothing is chosen",
    ),
    (
        "answer-tied-on-a-chosen-answer",
        put(["tied"], ["example-rotation-soybean-cover", "example-rotation-soybean"]),
        "only when the answer is not resolved",
    ),
    (
        "answer-two-options-in-state-chosen",
        put([*NOT_MET, "state"], "chosen"),
        "on no other",
    ),
    (
        "answer-chosen-names-no-option",
        put(["chosen"], "example-rotation-unknown"),
        "the rotation_id of an option",
    ),
    (
        "answer-option-state-not-its-limit-check",
        put([*UNRESOLVED, "state"], "meets"),
        "the verdict of its limit check",
    ),
    (
        "answer-limit-check-not-of-the-strictness",
        put(["questions", "strictness"], "every_kind"),
        "the every_kind check of its limit",
    ),
    (
        "answer-with-two-options",
        lambda d: d.update(options=d["options"][:2]),
        "at least 3",
    ),
    (
        "answer-with-a-duplicate-option-id",
        put([*UNRESOLVED, "rotation_id"], "example-rotation-soybean"),
        "share the rotation_id",
    ),
    (
        "answer-limit-cost-value-without-against",
        put(["limit_cost", "against"], None),
        "exactly with the rotation it is against",
    ),
    (
        "answer-limit-cost-against-the-chosen-rotation",
        put(["limit_cost", "against"], "example-rotation-soybean-cover"),
        "another option than the chosen one",
    ),
    (
        "answer-tipping-point-missing-without-a-reason",
        put(["tipping_price", "up", "reason"], None),
        "a reason travels with its detail",
    ),
    (
        "answer-tipping-price-range-not-the-question",
        put(["tipping_price", "price_range", "high"], 700.0),
        "the soybean price range of the questions",
    ),
    (
        "answer-rain-stress-not-the-declared-factor",
        put(["rain_stress", "factor"], 1.5),
        "the factor is the declared value",
    ),
    (
        "answer-rain-stress-echo-without-a-factor",
        put(["questions", "rain_stress_factor"], None),
        "null when no factor was asked",
    ),
    (
        "answer-erosivity-not-in-the-list",
        put(["erosivity"], "per_year"),
        "erosivity",
    ),
    (
        "answer-kind-counts-not-the-years",
        put(["kinds_of_year", "counts", "neutral"], 3),
        "the counts are the years of each kind",
    ),
    (
        "answer-soil-loss-n-years-not-the-years",
        put([*CHOSEN, "soil_loss", "el_nino", "n_years"], 1),
        "n_years is the number of ag_years",
    ),
    (
        "answer-limit-kind-not-in-the-list",
        put([*NOT_MET, "limit", "kinds_not_met"], ["dry"]),
        "only kinds of KINDS_OF_YEAR",
    ),
    (
        "answer-margin-without-its-provenance",
        drop(MARGIN, "provenance"),
        "a present value carries its provenance",
    ),
    (
        "answer-margin-not-derived",
        put([*MARGIN, "provenance"], "DECLARED"),
        "the provenance is DERIVED",
    ),
    (
        "answer-margin-without-its-source",
        drop(MARGIN, "source"),
        f"the source is {MARGIN_SOURCE!r}",
    ),
    (
        "answer-margin-with-a-range-and-its-absence",
        put([*MARGIN, "range"], {"low": 0.0, "high": 900.0, "kind": "PLACEHOLDER"}),
        "never both",
    ),
    (
        "answer-margin-outside-its-range",
        lambda d: range_around(MARGIN, 0.0, at(d, MARGIN)["value"] - 1.0)(d),
        "the value is inside its range",
    ),
    (
        "answer-missing-margin-with-a-provenance",
        both(
            put([*MARGIN, "value"], None),
            put([*MARGIN, "reason"], "NOT_COMPUTABLE"),
        ),
        "a missing value carries no provenance and no range",
    ),
    (
        "answer-soil-loss-without-a-range-or-its-absence",
        drop(SOIL_LOSS, "range_missing"),
        "its range or range_missing",
    ),
    (
        "answer-soil-loss-not-of-c4-6",
        put([*SOIL_LOSS, "provenance"], "SIMULATED"),
        "the provenance is DERIVED",
    ),
    (
        "answer-soil-loss-label-not-the-one-of-d148",
        put([*SOIL_LOSS, "label"], "example label"),
        "the label is the one D148 words",
    ),
    (
        "answer-real-soil-loss-without-the-label-of-d148",
        put(["example_data"], False),
        "carries the label of D148",
    ),
    (
        "answer-limit-cost-without-its-provenance",
        drop(["limit_cost"], "provenance"),
        "limit cost: a present value carries its provenance",
    ),
    (
        "answer-tipping-point-not-derived",
        put(["tipping_price", "down", "provenance"], "OBSERVED"),
        "tipping point: the provenance is DERIVED",
    ),
    (
        "answer-tipping-today-without-its-provenance",
        drop(["tipping_price"], "provenance"),
        "tipping price: a present value carries its provenance",
    ),
    (
        "answer-scope-not-the-words-of-d245",
        put(["scope"], "Plant this rotation"),
        "the scope is",
    ),
    (
        "answer-without-the-limit-phase-one-only",
        put(["declared_limits"], []),
        "the declared limits include",
    ),
]

VALID_ANSWER: list[tuple[str, Mutation]] = [
    (
        "accepted-answer-not-resolved-with-tied",
        both(NOTHING_CHOSEN, UNRESOLVED_MEETS, put(["tied"], BOTH_THAT_MEET)),
    ),
    (
        "accepted-answer-none-meets",
        both(
            NOTHING_CHOSEN,
            put(["answer"], "none_meets"),
            put(["reason"], "NOT_APPLICABLE"),
            put([*CHOSEN, "limit", "on_average", "verdict"], "does_not_meet"),
            put([*CHOSEN, "limit_check", "verdict"], "does_not_meet"),
            put([*CHOSEN, "state"], "does_not_meet"),
            put([*UNRESOLVED, "limit", "on_average"], MEETS),
            put([*UNRESOLVED, "limit", "on_average", "verdict"], "does_not_meet"),
            put([*UNRESOLVED, "limit_check"], MEETS),
            put([*UNRESOLVED, "limit_check", "verdict"], "does_not_meet"),
            put([*UNRESOLVED, "state"], "does_not_meet"),
        ),
    ),
    (
        "accepted-answer-margin-missing-without-a-detail",
        both(
            put([*UNRESOLVED, "margin", "la_nina", "value"], None),
            put([*UNRESOLVED, "margin", "la_nina", "reason"], "MISSING_INPUT"),
            drop(
                [*UNRESOLVED, "margin", "la_nina"],
                "provenance",
                "range_missing",
                "source",
            ),
        ),
    ),
    (
        "accepted-answer-kind-of-year-missing-without-a-detail",
        both(
            put(["kinds_of_year", "years", -1, "kind"], None),
            put(["kinds_of_year", "years", -1, "missing_reason"], "NO_COVERAGE"),
            put(
                ["kinds_of_year", "counts"],
                {"el_nino": None, "neutral": None, "la_nina": None},
            ),
        ),
    ),
    (
        "accepted-answer-without-a-rain-stress-test",
        both(
            put(["questions", "rain_stress_factor"], None), put(["rain_stress"], None)
        ),
    ),
    (
        "accepted-answer-rain-stress-factor-missing",
        both(
            put(
                ["questions", "rain_stress_factor"],
                {
                    "value": None,
                    "unit": "dimensionless",
                    "missing": {"reason": "NOT_DECLARED"},
                },
            ),
            put(
                ["rain_stress"],
                {
                    "missing": {"reason": "NOT_DECLARED"},
                    "detail": "example detail: no stress test, the factor is missing",
                    "label": "stress test",
                },
            ),
        ),
    ),
    (
        "accepted-answer-not-example-data",
        both(put(["example_data"], False), label_real_soil_losses),
    ),
    (
        "accepted-answer-margin-with-a-range",
        lambda d: range_around(
            MARGIN, at(d, MARGIN)["value"] - 1.0, at(d, MARGIN)["value"] + 1.0
        )(d),
    ),
    (
        "accepted-answer-example-soil-loss-with-the-label-of-d148",
        label_real_soil_losses,
    ),
    (
        "accepted-answer-with-a-second-declared-limit",
        put(["declared_limits"], [PHASE_ONE_ONLY, "example limit"]),
    ),
]

VALID_REQUEST: list[tuple[str, Mutation]] = [
    ("accepted-request-with-five-rotations", keep_rotations(5)),
    (
        "accepted-request-soil-loss-limit-missing",
        put(
            ["soil_loss_limit"],
            {
                "value": None,
                "unit": "t ha-1 yr-1",
                "missing": {"reason": "NOT_DECLARED"},
            },
        ),
    ),
    (
        "accepted-request-soybean-price-missing",
        put(
            ["economic_facts", "crops", 0, "price"],
            {"value": None, "unit": "USD t-1", "missing": {"reason": "NOT_DECLARED"}},
        ),
    ),
]


def _describe(error: ValidationError) -> str:
    return "\n".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )


# --- The examples ------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "model"), [(REQUEST, PlantRequest), (ANSWER, PlantAnswer)]
)
def test_example_loads_into_its_model(name: str, model: type) -> None:
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    loaded = model.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert model.model_validate(json.loads(text)) == loaded
    dumped = loaded.model_dump(mode="json")
    assert model.model_validate(dumped) == loaded


def test_the_answer_example_answers_the_request_example() -> None:
    request = PlantRequest.model_validate(load(REQUEST))
    answer = PlantAnswer.model_validate(load(ANSWER))
    check_answer_against_request(request, answer)


def check_example_mark(name: str, data: dict[str, Any]) -> None:
    """An example says it is example data, in its name and in its data."""
    if not name.startswith("PLACEHOLDER_"):
        raise AssertionError(f"{name}: an example's file name starts PLACEHOLDER_")
    if data.get("example_data") is not True:
        raise AssertionError(f"{name}: an example says example_data true")


@pytest.mark.parametrize("name", [REQUEST, ANSWER])
def test_examples_say_they_are_example_data(name: str) -> None:
    check_example_mark(name, load(name))


@pytest.mark.parametrize("name", [REQUEST, ANSWER])
def test_an_example_with_example_data_false_is_refused(name: str) -> None:
    data = load(name)
    data["example_data"] = False
    with pytest.raises(AssertionError, match="example_data true"):
        check_example_mark(name, data)


def test_the_folder_holds_the_two_examples() -> None:
    assert sorted(path.name for path in EXAMPLES.iterdir()) == sorted([ANSWER, REQUEST])


def test_the_answer_example_shows_what_the_brief_asks() -> None:
    answer = load(ANSWER)
    states = [option["state"] for option in answer["options"]]
    assert answer["answer"] == "chosen"
    assert states.count("chosen") == 1
    assert "does_not_meet" in states
    assert any(
        point["price"] is not None
        for point in (answer["tipping_price"]["up"], answer["tipping_price"]["down"])
    )
    text = json.dumps(answer)
    assert '"value": null' in text or '"price": null' in text


# --- The literals agree with the pure functions ------------------------------


def test_literals_equal_those_of_economics() -> None:
    from economics import decide, limit, tipping

    assert get_args(Strictness) == get_args(decide.Strictness)
    assert get_args(Answer) == get_args(decide.Answer)
    assert get_args(OptionState) == get_args(decide.OptionState)
    assert get_args(Verdict) == get_args(limit.Verdict)
    assert get_args(Direction) == get_args(tipping.Direction)
    assert MARGINS_OF == tipping.MARGINS_OF
    assert get_args(MarginOf) == tipping.MARGINS_OF


def test_constants_equal_those_of_rain_stress() -> None:
    rain_stress = pytest.importorskip("api.rain_stress")

    assert DIMENSIONLESS == rain_stress.DIMENSIONLESS
    assert STRESS_TEST_LABEL == rain_stress.STRESS_TEST_LABEL


def test_kinds_of_year_keys_follow_kinds_of_year() -> None:
    answer = load(ANSWER)
    option = answer["options"][0]
    assert list(option["margin"]) == ["average", *KINDS_OF_YEAR]
    assert list(option["soil_loss"]) == ["average", *KINDS_OF_YEAR]
    assert list(option["limit"]["by_kind"]) == list(KINDS_OF_YEAR)
    assert list(answer["kinds_of_year"]["counts"]) == list(KINDS_OF_YEAR)


def _names(cls: type) -> set[str]:
    import dataclasses

    return {f.name for f in dataclasses.fields(cls)}


def test_answer_fields_mirror_the_dataclasses() -> None:
    """Field for field where it can be (brief S-018a), plus the labels D249 adds."""
    from economics.decide import LimitCost
    from economics.limit import LimitAssessment, LimitCheck
    from economics.margin import MarginResult
    from economics.tipping import TippingPoint, TippingPrice

    from . import plant_answer as m

    margin = set(m.MarginOut.model_fields)
    assert margin == _names(MarginResult) | D249_LABELS | {"source"}
    assert set(m.LimitCheckOut.model_fields) == _names(LimitCheck)
    assert set(m.LimitAssessmentOut.model_fields) == _names(LimitAssessment)
    assert set(m.LimitCostOut.model_fields) == _names(LimitCost) | D249_LABELS
    assert set(m.TippingPointOut.model_fields) == _names(TippingPoint) | D249_LABELS
    assert (
        set(m.TippingPriceOut.model_fields)
        == (_names(TippingPrice) - {"decision"}) | D249_LABELS
    )

    from api.rotations import SiteReference, SourceOut

    assert set(m.SourceOut.model_fields) == set(SourceOut.model_fields)
    assert set(m.SiteReference.model_fields) == set(SiteReference.model_fields)


def test_answer_fields_mirror_kinds_of_year() -> None:
    pytest.importorskip("kinds_of_year")
    from kinds_of_year.aggregate import KindMean
    from kinds_of_year.classify import KindOfYear

    from . import plant_answer as m

    soil_loss = set(m.SoilLossOut.model_fields)
    assert soil_loss == _names(KindMean) | D249_LABELS | {"label"}
    assert set(m.YearKind.model_fields) == _names(KindOfYear) | {"ag_year"}


def test_answer_fields_mirror_rain_stress() -> None:
    rain_stress = pytest.importorskip("api.rain_stress")

    from . import plant_answer as m

    assert set(m.RainStressApplied.model_fields) == _names(rain_stress.RainStress)
    assert set(m.RainStressMissingOut.model_fields) == _names(
        rain_stress.RainStressMissing
    )


def test_the_contract_imports_neither_kinds_of_year_nor_rain_stress() -> None:
    """#387: the contract imports neither ``kinds_of_year`` nor ``api``."""
    tree = ast.parse((HERE / "plant_answer.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    roots = {name.split(".")[0] for name in imported}
    assert "kinds_of_year" not in roots
    assert "api" not in roots


def test_the_answer_says_what_it_is_and_its_limit() -> None:
    """D245 and the declared limit, in the example as the screen reads them."""
    answer = load(ANSWER)
    assert answer["scope"] == ANSWER_SCOPE
    assert PHASE_ONE_ONLY in answer["declared_limits"]
    assert "Plant this rotation" not in json.dumps(answer)


def test_every_number_of_the_example_carries_its_labels() -> None:
    """D249: provenance and range or range_missing on every present number; a
    margin's source."""
    answer = load(ANSWER)
    numbers = [answer["limit_cost"], answer["tipping_price"]]
    numbers += [answer["tipping_price"]["up"], answer["tipping_price"]["down"]]
    for option in answer["options"]:
        numbers += option["margin"].values()
        numbers += option["soil_loss"].values()
    for item in numbers:
        value = item.get("value", item.get("price", item.get("today")))
        if value is None:
            assert "provenance" not in item
            continue
        assert item["provenance"] in ("DECLARED", "DERIVED")
        assert ("range" in item) != ("range_missing" in item)
    for option in answer["options"]:
        for margin in option["margin"].values():
            if margin["value"] is not None:
                assert margin["source"] == MARGIN_SOURCE


def test_retrieved_at_is_written_in_utc_as_api_writes_it() -> None:
    from api.rotations import SourceOut as ApiSourceOut

    from .plant_answer import SourceOut

    row = {
        "id": "example_source",
        "contract": "results",
        "state": "cached",
        "retrieved_at": "2026-11-15T10:30:00+02:00",
        "time_zone": None,
        "request": None,
        "attribution": None,
        "missing_reason": None,
        "detail": None,
    }
    ours = SourceOut.model_validate(row).model_dump(mode="json")
    assert ours["retrieved_at"] == "2026-11-15T08:30:00Z"
    assert ours == ApiSourceOut.model_validate(row).model_dump(mode="json")
    # What it writes reads back into an equal row.
    assert SourceOut.model_validate(ours) == SourceOut.model_validate(row)


# --- Invalid and valid variants ----------------------------------------------


def _variant(name: str, mutation: Mutation) -> dict[str, Any]:
    data = load(name)
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    return variant


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(m, f, id=case) for case, m, f in INVALID_REQUEST],
)
def test_invalid_request_is_rejected(mutation: Mutation, fragment: str) -> None:
    variant = _variant(REQUEST, mutation)
    with pytest.raises(ValidationError) as rejected:
        PlantRequest.model_validate(variant)
    assert fragment in _describe(rejected.value)
    with pytest.raises(ValidationError):
        PlantRequest.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(m, f, id=case) for case, m, f in INVALID_ANSWER],
)
def test_invalid_answer_is_rejected(mutation: Mutation, fragment: str) -> None:
    variant = _variant(ANSWER, mutation)
    with pytest.raises(ValidationError) as rejected:
        PlantAnswer.model_validate(variant)
    assert fragment in _describe(rejected.value)
    with pytest.raises(ValidationError):
        PlantAnswer.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation", [pytest.param(m, id=case) for case, m in VALID_REQUEST]
)
def test_valid_request_is_accepted(mutation: Mutation) -> None:
    variant = _variant(REQUEST, mutation)
    PlantRequest.model_validate(variant)
    PlantRequest.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation", [pytest.param(m, id=case) for case, m in VALID_ANSWER]
)
def test_valid_answer_is_accepted(mutation: Mutation) -> None:
    variant = _variant(ANSWER, mutation)
    PlantAnswer.model_validate(variant)
    PlantAnswer.model_validate_json(json.dumps(variant))


AGAINST_REQUEST: list[tuple[str, Mutation, str]] = [
    (
        "answer-options-not-in-request-order",
        lambda d: d["options"].reverse(),
        "in request order",
    ),
    (
        "answer-of-another-field",
        put(["field_id"], "example-field-2"),
        "case_id and field_id",
    ),
    (
        "answer-questions-not-those-of-the-request",
        put(["questions", "margin_of"], "la_nina"),
        "the questions of the request",
    ),
    (
        "answer-not-example-data-to-an-example-request",
        both(put(["example_data"], False), label_real_soil_losses),
        "example_data is true when the request's is",
    ),
    (
        "answer-tipping-today-not-the-declared-price",
        put(["tipping_price", "today"], 390.0),
        "the declared soybean price",
    ),
    (
        "answer-start-month-not-the-rotations",
        put(["kinds_of_year", "start_month"], 8),
        "the rotations' ag_year_start month",
    ),
    (
        "answer-tipping-today-labels-not-the-declared-price",
        put(["tipping_price", "provenance"], "OBSERVED"),
        "the provenance and range of the declared soybean price",
    ),
]


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(m, f, id=case) for case, m, f in AGAINST_REQUEST],
)
def test_answer_not_to_this_request_is_refused(
    mutation: Mutation, fragment: str
) -> None:
    request = PlantRequest.model_validate(load(REQUEST))
    answer = PlantAnswer.model_validate(_variant(ANSWER, mutation))
    with pytest.raises(ValueError, match=fragment):
        check_answer_against_request(request, answer)


# --- The README lists the cases ----------------------------------------------


def _all_cases() -> list[str]:
    return (
        [case for case, *_ in INVALID_REQUEST]
        + [case for case, *_ in INVALID_ANSWER]
        + [case for case, *_ in VALID_REQUEST]
        + [case for case, *_ in VALID_ANSWER]
        + [case for case, *_ in AGAINST_REQUEST]
    )


def test_case_identifiers_are_unique() -> None:
    cases = _all_cases()
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in ("## PROPOSED cases", "## OPEN"):
        assert f"\n{heading}\n" in readme, f"README.md has no heading {heading!r}"
    listed = readme.split("\n## PROPOSED cases\n", 1)[1].split("\n## ", 1)[0]
    cases = _all_cases()
    in_readme = re.findall(r"^\| `([a-z0-9-]+)` \|", listed, re.MULTILINE)
    assert sorted(in_readme) == sorted(cases)


# --- Review of the whole 4 (brief S-034, F2), PROPOSED ---------------------------
# Not cases of the README lists: a check of the wording of the messages only.

# Test data: an identifier shorter than the three characters the route's
# redaction looks for (api/rotation_validator.py).
SHORT_ID = "q7"


def _soybean_not_sown(data: dict[str, Any]) -> None:
    soy = data["questions"]["soybean_crop_ids"][0]
    (crop,) = [c for c in data["economic_facts"]["crops"] if c["crop_id"] == soy]
    data["economic_facts"]["crops"].append(dict(crop, crop_id=SHORT_ID))
    data["questions"]["soybean_crop_ids"] = [SHORT_ID]


SHORT_ID_CASES: list[tuple[str, Mutation, str]] = [
    (
        "duplicate-rotation-id",
        both(
            put(["rotations", 0, "rotation_id"], SHORT_ID),
            put(["rotations", 1, "rotation_id"], SHORT_ID),
        ),
        "share the rotation_id",
    ),
    (
        "undeclared-crop",
        put(["rotations", 2, "components", 0, "crop_id"], SHORT_ID),
        "every crop sown is declared in economic_facts",
    ),
    (
        "repeated-soybean-crop-id",
        put(["questions", "soybean_crop_ids"], [SHORT_ID, SHORT_ID]),
        "repeated",
    ),
    ("soybean-crop-not-sown", _soybean_not_sown, "sown by at least one rotation"),
]


# OPEN (S-034): this message still quotes the rotation_id (see the comment at
# the message in plant_answer.py); strict, so it reports when it is fixed.
SHORT_ID_OPEN = pytest.param(
    both(
        put(["rotations", 2, "rotation_id"], SHORT_ID),
        put(["rotations", 2, "field_id"], "example-field-2"),
    ),
    "another field than the site",
    id="rotation-of-another-field",
    marks=pytest.mark.xfail(strict=True, reason="OPEN: S-034 F2, see plant_answer.py"),
)


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(m, f, id=case) for case, m, f in SHORT_ID_CASES] + [SHORT_ID_OPEN],
)
def test_f2_a_request_message_never_quotes_a_submitted_id(
    mutation: Mutation, fragment: str
) -> None:
    """F2: the message says what and where (a position), never the id."""
    with pytest.raises(ValidationError) as caught:
        PlantRequest.model_validate(_variant(REQUEST, mutation))
    messages = [e["msg"] for e in caught.value.errors(include_input=False)]
    assert any(fragment in message for message in messages)
    for message in messages:
        assert SHORT_ID not in message
    # Fix round 1: a list index (0-based), not the component's position field.
    assert any("list ind" in message for message in messages)
    assert not any("position" in message for message in messages)
