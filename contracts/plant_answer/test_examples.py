"""Acceptance test of unit l2/plant-answer-contract (brief S-018a). PROPOSED.

Both PLACEHOLDER examples load into their models; the literals of the contract
equal those of ``economics/``, ``kinds_of_year/`` and ``api/rain_stress.py``;
the examples say they are example data; and each invalid variant is rejected.
The variants are listed in ``README.md`` under "PROPOSED cases"; a test checks
that the two lists agree.

Run from the repository root: ``uv run pytest contracts/plant_answer/``.
"""

from __future__ import annotations

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
    DIMENSIONLESS,
    MARGINS_OF,
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
]

INVALID_ANSWER: list[tuple[str, Mutation, str]] = [
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
]

VALID_ANSWER: list[tuple[str, Mutation]] = [
    (
        "accepted-answer-not-resolved-with-tied",
        both(
            put(["answer"], "not_resolved"),
            put(["chosen"], None),
            put(["reason"], "NOT_COMPUTABLE"),
            put(["detail"], "example detail: the data cannot separate these"),
            put(
                ["tied"],
                ["example-rotation-soybean-cover", "example-rotation-soybean"],
            ),
            put([*CHOSEN, "state"], "meets"),
            put(
                ["limit_cost"],
                {
                    "value": None,
                    "against": None,
                    "costs_nothing": False,
                    "reason": "NOT_COMPUTABLE",
                    "detail": "example detail: no rotation is chosen",
                    "unit": "USD ha-1 yr-1",
                },
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
        put(["example_data"], False),
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
    from api import rain_stress

    assert DIMENSIONLESS == rain_stress.DIMENSIONLESS
    assert STRESS_TEST_LABEL == rain_stress.STRESS_TEST_LABEL


def test_kinds_of_year_keys_follow_kinds_of_year() -> None:
    answer = load(ANSWER)
    option = answer["options"][0]
    assert list(option["margin"]) == ["average", *KINDS_OF_YEAR]
    assert list(option["soil_loss"]) == ["average", *KINDS_OF_YEAR]
    assert list(option["limit"]["by_kind"]) == list(KINDS_OF_YEAR)
    assert list(answer["kinds_of_year"]["counts"]) == list(KINDS_OF_YEAR)


def test_answer_fields_mirror_the_dataclasses() -> None:
    """Field for field where it can be (brief S-018a)."""
    import dataclasses

    from economics.decide import LimitCost
    from economics.limit import LimitAssessment, LimitCheck
    from economics.margin import MarginResult
    from economics.tipping import TippingPoint, TippingPrice
    from kinds_of_year.aggregate import KindMean
    from kinds_of_year.classify import KindOfYear

    from . import plant_answer as m

    def names(cls: type) -> set[str]:
        return {f.name for f in dataclasses.fields(cls)}

    assert set(m.MarginOut.model_fields) == names(MarginResult)
    assert set(m.SoilLossOut.model_fields) == names(KindMean)
    assert set(m.LimitCheckOut.model_fields) == names(LimitCheck)
    assert set(m.LimitAssessmentOut.model_fields) == names(LimitAssessment)
    assert set(m.LimitCostOut.model_fields) == names(LimitCost)
    assert set(m.TippingPointOut.model_fields) == names(TippingPoint)
    assert set(m.TippingPriceOut.model_fields) == names(TippingPrice) - {"decision"}
    assert set(m.YearKind.model_fields) == names(KindOfYear) | {"ag_year"}


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
