"""Acceptance test of unit l0/contracts-rotation-definition.

The PLACEHOLDER example loads into its model, and each invalid variant of
the example is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree.

Run from the repository root: ``python -m pytest contracts/rotation_definition/``.
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

from .common import Provenance, ReasonCode
from .rotation_definition import Purpose, RotationDefinition

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_rotation_definition.json"
README = HERE / "README.md"
CONVENTIONS = HERE.parent / "CONVENTIONS.md"

# The example of issue #60, as the producer wrote it. It is kept here only to
# show that the landed example differs from it in one point and in no other.
PRODUCER_EXAMPLE = """
{
  "contract": "rotation_definition",
  "example_data": true,
  "case_id": "example-case",
  "field_id": "example-field-1",
  "rotation_id": "example-rotation-1",
  "label": "Illustrative rotation",
  "repeats": true,
  "components": [
    {
      "component_id": "c1",
      "position": 1,
      "crop_id": "PLACEHOLDER_crop",
      "purpose": "grain",
      "sowing": { "date": "2027-11-15", "provenance": "DECLARED", "source": "user" },
      "harvest": { "date": "2028-04-10", "provenance": "DECLARED", "source": "user" }
    },
    {
      "component_id": "c2",
      "position": 2,
      "crop_id": "PLACEHOLDER_cover_crop",
      "purpose": "cover",
      "sowing": { "date": "2028-04-20", "provenance": "DECLARED", "source": "user" },
      "harvest": null,
      "missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" }
    }
  ]
}
"""

Mutation = Callable[[dict[str, Any]], None]


def load() -> dict[str, Any]:
    return json.loads((EXAMPLES / EXAMPLE).read_text(encoding="utf-8"))


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


def both(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


FIRST = ["components", 0]  # the component with both dates
SECOND = ["components", 1]  # the component whose harvest is missing
SOWING = [*FIRST, "sowing"]  # a date that is present
HARVEST = [*SECOND, "harvest"]  # a date that is missing, with its reason

# (case identifier, mutation, fragment of the expected error).
# The fragment shows that the variant is rejected for the intended reason.
INVALID: list[tuple[str, Mutation, str]] = [
    # --- A date and its missing part ----------------------------------------
    (
        "date-without-provenance-label",
        drop([*SOWING, "provenance"]),
        "provenance label",
    ),
    (
        "provenance-label-in-lower-case",
        put([*SOWING, "provenance"], "declared"),
        "sowing.provenance",
    ),
    (
        "provenance-label-outside-the-four",
        put([*SOWING, "provenance"], "USER"),
        "sowing.provenance",
    ),
    (
        "date-without-source-or-assumption-mark",
        drop([*SOWING, "source"]),
        "source or the assumption mark",
    ),
    (
        "missing-date-without-reason",
        put(HARVEST, {"date": None}),
        "missing part with its reason",
    ),
    (
        "missing-part-without-reason-code",
        drop([*HARVEST, "missing", "reason"]),
        "harvest.missing.reason",
    ),
    (
        "missing-date-with-reason-code-not-in-the-sheet",
        put([*HARVEST, "missing", "reason"], "NOT_DECIDED"),
        "harvest.missing.reason",
    ),
    (
        "missing-input-without-detail",
        put([*HARVEST, "missing"], {"reason": "MISSING_INPUT"}),
        "names the input",
    ),
    (
        "missing-date-with-provenance-label",
        put([*HARVEST, "provenance"], "DECLARED"),
        "no provenance label",
    ),
    (
        "missing-date-marked-as-assumption",
        put([*HARVEST, "assumption"], True),
        "not an assumption",
    ),
    (
        "date-together-with-a-missing-part",
        put([*SOWING, "missing"], {"reason": "NOT_DECLARED"}),
        "never both",
    ),
    (
        "missing-part-beside-a-null-harvest",
        both(
            put([*SECOND, "missing"], {"reason": "NOT_APPLICABLE"}),
            put(HARVEST, None),
        ),
        "components.1.missing: Extra inputs",
    ),
    (
        "missing-date-left-out",
        drop(HARVEST),
        "components.1.harvest",
    ),
    (
        "date-not-written-as-year-month-day",
        put([*SOWING, "date"], "15/11/2027"),
        "YYYY-MM-DD",
    ),
    (
        "date-written-as-day-of-year",
        put([*SOWING, "date"], "2027-319"),
        "YYYY-MM-DD",
    ),
    (
        "date-with-a-time",
        put([*SOWING, "date"], "2027-11-15T00:00:00"),
        "YYYY-MM-DD",
    ),
    ("date-unknown-extra-field", put([*SOWING, "note"], "x"), "Extra inputs"),
    # --- A component --------------------------------------------------------
    (
        "harvest-before-its-sowing",
        put([*FIRST, "harvest", "date"], "2027-11-14"),
        "harvest is before sowing",
    ),
    (
        "purpose-outside-the-proposed-list",
        put([*FIRST, "purpose"], "PLACEHOLDER_purpose"),
        "components.0.purpose",
    ),
    (
        "component-without-crop-identifier",
        drop([*FIRST, "crop_id"]),
        "components.0.crop_id",
    ),
    (
        "crop-identifier-blank",
        put([*FIRST, "crop_id"], "   "),
        "components.0.crop_id",
    ),
    (
        "position-written-as-text",
        put([*FIRST, "position"], "1"),
        "valid integer",
    ),
    ("component-unknown-extra-field", put([*FIRST, "note"], "x"), "Extra inputs"),
    # --- The definition -----------------------------------------------------
    (
        "two-components-with-one-identifier",
        put([*SECOND, "component_id"], "c1"),
        "share one component_id",
    ),
    (
        "positions-repeat-a-number",
        put([*SECOND, "position"], 1),
        "none repeated and none skipped",
    ),
    (
        "positions-skip-a-number",
        put([*SECOND, "position"], 3),
        "none repeated and none skipped",
    ),
    (
        "positions-start-at-zero",
        both(put([*FIRST, "position"], 0), put([*SECOND, "position"], 1)),
        "positions number the components from 1",
    ),
    ("definition-unknown-extra-field", put(["note"], "x"), "Extra inputs"),
    (
        "definition-without-example-data-flag",
        drop(["example_data"]),
        "example_data",
    ),
    (
        "definition-without-repeats",
        drop(["repeats"]),
        "repeats",
    ),
    (
        "definition-with-another-contract-identifier",
        put(["contract"], "rotation_calendar"),
        "contract",
    ),
]

# Variants that stay valid. They show shapes the example does not contain.
# A case named "accepted-while-open-..." is accepted only because no person
# has decided the question yet (README.md, under OPEN). It is not a proposal
# to allow what the variant shows.
VALID: list[tuple[str, Mutation]] = [
    (
        "accepted-sowing-not-declared",
        put(SOWING, {"date": None, "missing": {"reason": "NOT_DECLARED"}}),
    ),
    (
        "accepted-date-with-assumption-mark-and-no-source",
        both(drop([*SOWING, "source"]), put([*SOWING, "assumption"], True)),
    ),
    ("accepted-rotation-that-does-not-repeat", put(["repeats"], False)),
    (
        "accepted-while-open-crop-identifier-as-any-text",
        put([*FIRST, "crop_id"], "PLACEHOLDER text, not taken from any list"),
    ),
    (
        "accepted-while-open-overlapping-components",
        put([*SECOND, "sowing", "date"], "2028-04-01"),
    ),
    (
        "accepted-while-open-components-not-listed-by-position",
        both(put([*FIRST, "position"], 2), put([*SECOND, "position"], 1)),
    ),
    (
        "accepted-while-open-harvest-on-the-day-of-sowing",
        put([*FIRST, "harvest", "date"], "2027-11-15"),
    ),
    ("accepted-while-open-definition-without-components", put(["components"], [])),
]


def test_example_loads_into_its_model() -> None:
    text = (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    loaded = RotationDefinition.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert RotationDefinition.model_validate(json.loads(text)) == loaded


def test_example_is_marked_as_example_data() -> None:
    assert EXAMPLE.startswith("PLACEHOLDER_")
    data = load()
    assert data["example_data"] is True
    # The identifiers are the producer's; the crops are the ones marked.
    for component in data["components"]:
        assert "PLACEHOLDER" in component["crop_id"]


def test_the_folder_holds_one_example() -> None:
    assert [path.name for path in EXAMPLES.iterdir()] == [EXAMPLE]


def test_example_differs_from_the_producer_example_only_in_the_missing_harvest() -> (
    None
):
    """README.md, "Differences from the producer's example"."""
    produced = json.loads(PRODUCER_EXAMPLE)

    # As the producer wrote it, the missing part sits next to a null harvest,
    # at the level of the component. The model rejects both halves of that.
    with pytest.raises(ValidationError) as rejected:
        RotationDefinition.model_validate(produced)
    assert sorted(
        ".".join(str(part) for part in item["loc"]) for item in rejected.value.errors()
    ) == ["components.1.harvest", "components.1.missing"]

    # C3.1: the missing part travels inside the item, with the null date.
    for component in produced["components"]:
        if component["harvest"] is None:
            component["harvest"] = {"date": None, "missing": component.pop("missing")}
    assert produced == load()


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(mutation, fragment, id=case) for case, mutation, fragment in INVALID],
)
def test_invalid_variant_is_rejected(mutation: Mutation, fragment: str) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    with pytest.raises(ValidationError) as rejected:
        RotationDefinition.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        RotationDefinition.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    RotationDefinition.model_validate(variant)
    RotationDefinition.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "path",
    [
        pytest.param([key], id=f"definition-{key}")
        for key in (
            "contract",
            "example_data",
            "case_id",
            "field_id",
            "rotation_id",
            "label",
            "repeats",
            "components",
        )
    ]
    + [
        pytest.param([*FIRST, key], id=f"component-{key}")
        for key in (
            "component_id",
            "position",
            "crop_id",
            "purpose",
            "sowing",
            "harvest",
        )
    ],
)
def test_no_field_of_the_producer_example_can_be_left_out(path: list[Any]) -> None:
    """No field of the definition or of a component has a default."""
    data = load()
    assert set(data) == {
        "contract",
        "example_data",
        "case_id",
        "field_id",
        "rotation_id",
        "label",
        "repeats",
        "components",
    }
    assert set(data["components"][0]) == {
        "component_id",
        "position",
        "crop_id",
        "purpose",
        "sowing",
        "harvest",
    }
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        RotationDefinition.model_validate(data)
    assert ".".join(str(part) for part in path) in _describe(rejected.value)


@pytest.mark.parametrize("reason", get_args(ReasonCode))
def test_a_missing_date_takes_any_reason_code_of_the_sheet(reason: str) -> None:
    """The model does not say which code fits which date."""
    variant = load()
    put([*HARVEST, "missing"], {"reason": reason, "detail": "PLACEHOLDER detail"})(
        variant
    )
    RotationDefinition.model_validate(variant)


def test_reason_codes_are_those_of_the_sheet() -> None:
    codes = re.findall(r"^\| `([A-Z_]+)` \|", _convention("C3.2"), re.MULTILINE)
    assert codes == list(get_args(ReasonCode))


def test_provenance_labels_are_those_of_the_sheet() -> None:
    labels = re.findall(r"^\| `([A-Z_]+)` \|", _convention("C4.1"), re.MULTILINE)
    assert labels == list(get_args(Provenance))


def test_purpose_list_is_the_one_the_producer_proposed() -> None:
    assert get_args(Purpose) == ("grain", "cover", "pasture")


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in (
        "## PROPOSED cases",
        "## Differences from the producer's example",
        "## OPEN",
    ):
        assert f"\n{heading}\n" in readme, f"README.md has no heading {heading!r}"
    listed = readme.split("\n## PROPOSED cases\n", 1)[1].split("\n## ", 1)[0]
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    for case in cases:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"
    # And the README lists no case that this file does not hold.
    in_readme = re.findall(r"^\| `([a-z0-9-]+)` \|", listed, re.MULTILINE)
    assert sorted(in_readme) == sorted(cases)


def _convention(identifier: str) -> str:
    """The text of one convention of the sheet, from its heading to the next."""
    text = CONVENTIONS.read_text(encoding="utf-8")
    start = text.index(f"### {identifier} ")
    end = text.find("\n#", start + 1)
    return text[start:] if end == -1 else text[start:end]


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
