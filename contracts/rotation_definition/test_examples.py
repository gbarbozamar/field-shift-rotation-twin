"""Acceptance test of units l0/contracts-rotation-definition and l0/rotation-definition-v2.

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
from .rotation_definition import (
    Purpose,
    Residue,
    RotationDefinition,
    TerminationMethod,
)

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_rotation_definition.json"
README = HERE / "README.md"
CONVENTIONS = HERE.parent / "CONVENTIONS.md"

# The example of issue #95 (version 2), as the producer wrote it. It is kept
# here only to show that the landed example differs from it in the points of
# README.md, "Differences from the producer's example", and in no other.
PRODUCER_EXAMPLE = """
{
  "contract": "rotation_definition",
  "example_data": true,
  "case_id": "example-case",
  "field_id": "example-field-1",
  "rotation_id": "example-rotation-1",
  "label": "Illustrative rotation",
  "ag_year_start": { "month": 7, "provisional": true, "provenance": "DECLARED", "source": "user" },
  "repeats": true,
  "components": [
    {
      "component_id": "c1",
      "position": 1,
      "crop_id": "PLACEHOLDER_crop",
      "purpose": "grain",
      "sowing": { "date": "2027-11-15", "provenance": "DECLARED", "source": "user" },
      "harvest": { "date": "2028-04-10", "provenance": "DECLARED", "source": "user" },
      "management": { "residue": "left_on_surface", "grazing": null, "termination": null }
    },
    {
      "component_id": "c2",
      "position": 2,
      "crop_id": "PLACEHOLDER_cover_crop",
      "purpose": "cover",
      "sowing": { "date": "2028-04-20", "provenance": "DECLARED", "source": "user" },
      "harvest": null,
      "missing": { "reason": "NOT_APPLICABLE", "detail": "cover crop is terminated, not harvested" },
      "management": { "residue": "left_on_surface", "grazing": null,
        "termination": { "date": "2028-08-15", "method": "chemical" } }
    },
    {
      "component_id": "c3",
      "position": 3,
      "crop_id": "PLACEHOLDER_pasture",
      "purpose": "pasture",
      "sowing": { "date": "2028-08-20", "provenance": "DECLARED", "source": "user" },
      "harvest": null,
      "missing": { "reason": "NOT_APPLICABLE", "detail": "a pasture is grazed, not harvested" },
      "management": { "residue": "left_on_surface", "grazing": { "intensity": "PLACEHOLDER_light" }, "termination": null }
    }
  ]
}
"""

# What the landing writes in place of a management field the producer wrote
# as null, "not declared for this component" (issue #95): an explicit
# missing part with its reason (D39 of issue #77).
NOT_DECLARED = {"missing": {"reason": "NOT_DECLARED"}}

Mutation = Callable[[dict[str, Any]], None]


def load() -> dict[str, Any]:
    return json.loads((EXAMPLES / EXAMPLE).read_text(encoding="utf-8"))


def put(path: list[Any], value: Any) -> Mutation:
    """Set the item at ``path`` to ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = copy.deepcopy(value)

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


def every_date_missing() -> Mutation:
    """Every sowing and harvest date of every component missing with its reason."""

    def mutate(data: dict[str, Any]) -> None:
        for component in data["components"]:
            for key in ("sowing", "harvest"):
                if component[key]["date"] is not None:
                    component[key] = {
                        "date": None,
                        "missing": {"reason": "NOT_DECLARED"},
                    }

    return mutate


FIRST = ["components", 0]  # grain, with both dates
SECOND = ["components", 1]  # cover, harvest missing, termination declared
THIRD = ["components", 2]  # pasture, harvest missing, grazing declared
SOWING = [*FIRST, "sowing"]  # a date that is present
HARVEST = [*SECOND, "harvest"]  # a date that is missing, with its reason
START = ["ag_year_start"]  # the start month of the agricultural year
RESIDUE = [*FIRST, "management", "residue"]  # declared
GRAZING = [*FIRST, "management", "grazing"]  # not declared: a missing part
TERMINATION = [*SECOND, "management", "termination"]  # declared
GRAZING_DECLARED = [*THIRD, "management", "grazing"]  # declared
PRESENT_HARVEST = {"date": "2028-04-10", "provenance": "DECLARED", "source": "user"}
PRESENT_SOWING = {"date": "2028-08-20", "provenance": "DECLARED", "source": "user"}

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
        put([*THIRD, "position"], 4),
        "none repeated and none skipped",
    ),
    (
        "positions-start-at-zero",
        both(
            put([*FIRST, "position"], 0),
            put([*SECOND, "position"], 1),
            put([*THIRD, "position"], 2),
        ),
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
    # --- At least one present date (D21) ------------------------------------
    (
        "no-present-sowing-or-harvest-date",
        every_date_missing(),
        "at least one sowing or harvest date is present (D21)",
    ),
    (
        "definition-without-components",
        put(["components"], []),
        "at least one sowing or harvest date is present (D21)",
    ),
    # --- The start month of the agricultural year (D7, D8) ------------------
    (
        "definition-without-start-month",
        drop(START),
        "ag_year_start: Field required",
    ),
    (
        "start-month-null",
        put(START, None),
        "ag_year_start: Input should be",
    ),
    (
        "start-month-missing-with-its-reason",
        put(START, {"month": None, "missing": {"reason": "NOT_DECLARED"}}),
        "ag_year_start.missing: Extra inputs",
    ),
    (
        "start-month-zero",
        put([*START, "month"], 0),
        "ag_year_start.month: Input should be greater than or equal to 1",
    ),
    (
        "start-month-thirteen",
        put([*START, "month"], 13),
        "ag_year_start.month: Input should be less than or equal to 12",
    ),
    (
        "start-month-written-as-text",
        put([*START, "month"], "7"),
        "ag_year_start.month: Input should be a valid integer",
    ),
    (
        "start-month-without-provisional-mark",
        drop([*START, "provisional"]),
        "ag_year_start.provisional: Field required",
    ),
    (
        "start-month-provisional-mark-written-as-text",
        put([*START, "provisional"], "true"),
        "ag_year_start.provisional",
    ),
    (
        "start-month-without-provenance-label",
        drop([*START, "provenance"]),
        "ag_year_start.provenance: Field required",
    ),
    (
        "start-month-provenance-label-outside-the-four",
        put([*START, "provenance"], "USER"),
        "ag_year_start.provenance",
    ),
    (
        "start-month-without-source-or-assumption-mark",
        drop([*START, "source"]),
        "source or the assumption mark",
    ),
    (
        "start-month-unknown-extra-field",
        put([*START, "note"], "x"),
        "ag_year_start.note: Extra inputs",
    ),
    # --- Management fields (D4, D39) ----------------------------------------
    (
        "component-without-management",
        drop([*FIRST, "management"]),
        "components.0.management: Field required",
    ),
    (
        "management-null",
        put([*FIRST, "management"], None),
        "components.0.management",
    ),
    (
        "management-unknown-extra-field",
        put([*FIRST, "management", "note"], "x"),
        "management.note: Extra inputs",
    ),
    (
        "residue-outside-the-closed-list",
        put(RESIDUE, "PLACEHOLDER_residue"),
        "management.residue.declared",
    ),
    (
        "residue-in-upper-case",
        put(RESIDUE, "LEFT_ON_SURFACE"),
        "management.residue.declared",
    ),
    (
        "residue-not-declared-written-as-null",
        put(RESIDUE, None),
        "never as null (D39)",
    ),
    (
        "residue-not-declared-left-out",
        drop(RESIDUE),
        "management.residue: Field required",
    ),
    (
        "grazing-not-declared-written-as-null",
        put(GRAZING, None),
        "never as null (D39)",
    ),
    (
        "termination-not-declared-written-as-null",
        put([*FIRST, "management", "termination"], None),
        "never as null (D39)",
    ),
    (
        "termination-not-declared-left-out",
        drop([*FIRST, "management", "termination"]),
        "management.termination: Field required",
    ),
    (
        "not-declared-field-without-reason-code",
        put(GRAZING, {"missing": {}}),
        "grazing.missing.missing.reason",
    ),
    (
        "not-declared-field-with-reason-code-not-in-the-sheet",
        put(GRAZING, {"missing": {"reason": "NOT_DECIDED"}}),
        "grazing.missing.missing.reason",
    ),
    (
        "not-declared-field-missing-input-without-detail",
        put(GRAZING, {"missing": {"reason": "MISSING_INPUT"}}),
        "names the input",
    ),
    (
        "not-declared-field-with-its-missing-part-null",
        put(GRAZING, {"missing": None}),
        "grazing.missing.missing",
    ),
    (
        "termination-declared-together-with-a-missing-part",
        put([*TERMINATION, "missing"], {"reason": "NOT_DECLARED"}),
        "termination.missing.date: Extra inputs",
    ),
    (
        "termination-method-outside-the-closed-list",
        put([*TERMINATION, "method"], "PLACEHOLDER_method"),
        "termination.declared.method",
    ),
    (
        "termination-without-method",
        drop([*TERMINATION, "method"]),
        "termination.declared.method: Field required",
    ),
    (
        "termination-without-date",
        drop([*TERMINATION, "date"]),
        "termination.declared.date: Field required",
    ),
    (
        "termination-date-not-a-valid-date",
        put([*TERMINATION, "date"], "2028-02-30"),
        "termination.declared.date",
    ),
    (
        "termination-date-not-written-as-year-month-day",
        put([*TERMINATION, "date"], "15/08/2028"),
        "termination.declared.date: Value error, a date is written YYYY-MM-DD",
    ),
    (
        "termination-date-null",
        put([*TERMINATION, "date"], None),
        "termination.declared.date",
    ),
    (
        "termination-unknown-extra-field",
        put([*TERMINATION, "note"], "x"),
        "termination.declared.note: Extra inputs",
    ),
    (
        "grazing-without-intensity",
        put(GRAZING_DECLARED, {}),
        "grazing.declared.intensity: Field required",
    ),
    (
        "grazing-intensity-blank",
        put([*GRAZING_DECLARED, "intensity"], "   "),
        "grazing.declared.intensity",
    ),
    (
        "grazing-intensity-written-as-a-number",
        put([*GRAZING_DECLARED, "intensity"], 2),
        "grazing.declared.intensity",
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
        "accepted-one-present-date-and-every-other-missing",
        both(every_date_missing(), put([*FIRST, "harvest"], PRESENT_HARVEST)),
    ),
    (
        "accepted-only-one-sowing-date-present",
        both(every_date_missing(), put([*THIRD, "sowing"], PRESENT_SOWING)),
    ),
    (
        "accepted-start-month-with-assumption-mark-and-no-source",
        both(drop([*START, "source"]), put([*START, "assumption"], True)),
    ),
    (
        "accepted-every-management-field-not-declared",
        both(
            put(RESIDUE, NOT_DECLARED),
            put(TERMINATION, NOT_DECLARED),
            put(GRAZING_DECLARED, NOT_DECLARED),
        ),
    ),
    (
        "accepted-not-declared-field-with-a-detail",
        put(
            GRAZING,
            {"missing": {"reason": "NOT_APPLICABLE", "detail": "PLACEHOLDER detail"}},
        ),
    ),
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
    (
        "accepted-while-open-start-month-not-provisional",
        put([*START, "provisional"], False),
    ),
    (
        "accepted-while-open-start-month-with-another-provenance-label",
        put([*START, "provenance"], "OBSERVED"),
    ),
    (
        "accepted-while-open-termination-on-a-grain-component",
        put(
            [*FIRST, "management", "termination"],
            {"date": "2028-04-10", "method": "mechanical"},
        ),
    ),
    (
        "accepted-while-open-grazing-on-a-cover-component",
        put([*SECOND, "management", "grazing"], {"intensity": "PLACEHOLDER_light"}),
    ),
    (
        "accepted-while-open-pasture-without-grazing",
        put(GRAZING_DECLARED, NOT_DECLARED),
    ),
    (
        "accepted-while-open-cover-without-termination",
        put(TERMINATION, NOT_DECLARED),
    ),
    (
        "accepted-while-open-termination-before-its-sowing",
        put([*TERMINATION, "date"], "2028-04-19"),
    ),
    (
        "accepted-while-open-cover-with-a-harvest-and-a-termination",
        put(
            HARVEST, {"date": "2028-08-15", "provenance": "DECLARED", "source": "user"}
        ),
    ),
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


def test_example_differs_from_the_producer_example_only_where_the_readme_says() -> None:
    """README.md, "Differences from the producer's example"."""
    produced = json.loads(PRODUCER_EXAMPLE)

    # As the producer wrote it, the model rejects the missing part beside a
    # null harvest (difference 1) and a null in place of a management field
    # that is not declared (difference 2), and nothing else.
    with pytest.raises(ValidationError) as rejected:
        RotationDefinition.model_validate(produced)
    assert sorted(
        ".".join(str(part) for part in item["loc"]) for item in rejected.value.errors()
    ) == [
        "components.0.management",
        "components.1.harvest",
        "components.1.management",
        "components.1.missing",
        "components.2.harvest",
        "components.2.management",
        "components.2.missing",
    ]

    for component in produced["components"]:
        # Difference 1, C3.1: the missing part travels inside the item.
        if component["harvest"] is None:
            component["harvest"] = {"date": None, "missing": component.pop("missing")}
        # Difference 2, D39: not declared is an explicit missing part.
        management = component["management"]
        for key, value in management.items():
            if value is None:
                management[key] = copy.deepcopy(NOT_DECLARED)
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


DEFINITION_KEYS = (
    "contract",
    "example_data",
    "case_id",
    "field_id",
    "rotation_id",
    "label",
    "ag_year_start",
    "repeats",
    "components",
)
COMPONENT_KEYS = (
    "component_id",
    "position",
    "crop_id",
    "purpose",
    "sowing",
    "harvest",
    "management",
)
# `source` may give way to the assumption mark (C4.2): it has a case of its own.
START_KEYS = ("month", "provisional", "provenance")
MANAGEMENT_KEYS = ("residue", "grazing", "termination")


@pytest.mark.parametrize(
    "path",
    [pytest.param([key], id=f"definition-{key}") for key in DEFINITION_KEYS]
    + [pytest.param([*FIRST, key], id=f"component-{key}") for key in COMPONENT_KEYS]
    + [pytest.param([*START, key], id=f"start-month-{key}") for key in START_KEYS]
    + [
        pytest.param([*FIRST, "management", key], id=f"management-{key}")
        for key in MANAGEMENT_KEYS
    ]
    + [
        pytest.param([*TERMINATION, "date"], id="termination-date"),
        pytest.param([*TERMINATION, "method"], id="termination-method"),
        pytest.param([*GRAZING_DECLARED, "intensity"], id="grazing-intensity"),
    ],
)
def test_no_field_of_the_producer_example_can_be_left_out(path: list[Any]) -> None:
    """No field of the definition, of a component or of its management has a default."""
    data = load()
    assert set(data) == set(DEFINITION_KEYS)
    assert set(data["ag_year_start"]) == {*START_KEYS, "source"}
    for component in data["components"]:
        assert set(component) == set(COMPONENT_KEYS)
        assert set(component["management"]) == set(MANAGEMENT_KEYS)
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        RotationDefinition.model_validate(data)
    described = _describe(rejected.value)
    # A management field is reported inside the form it was read as.
    location = ".".join(str(part) for part in path)
    in_form = ".".join(str(part) for part in [*path[:-1], "declared", path[-1]])
    assert f"{location}: " in described or f"{in_form}: " in described


@pytest.mark.parametrize("reason", get_args(ReasonCode))
def test_a_missing_date_takes_any_reason_code_of_the_sheet(reason: str) -> None:
    """The model does not say which code fits which date."""
    variant = load()
    put([*HARVEST, "missing"], {"reason": reason, "detail": "PLACEHOLDER detail"})(
        variant
    )
    RotationDefinition.model_validate(variant)


@pytest.mark.parametrize("reason", get_args(ReasonCode))
@pytest.mark.parametrize(
    "path", [RESIDUE, GRAZING, TERMINATION], ids=list(MANAGEMENT_KEYS)
)
def test_a_management_field_not_declared_takes_any_reason_code_of_the_sheet(
    path: list[Any], reason: str
) -> None:
    """The model does not say which code fits which field (README, OPEN)."""
    variant = load()
    put(path, {"missing": {"reason": reason, "detail": "PLACEHOLDER detail"}})(variant)
    RotationDefinition.model_validate(variant)


@pytest.mark.parametrize("month", range(1, 13))
def test_start_month_takes_every_month_of_the_year(month: int) -> None:
    """C5.1: January is month 1 and December is month 12."""
    variant = load()
    put([*START, "month"], month)(variant)
    RotationDefinition.model_validate(variant)


def test_reason_codes_are_those_of_the_sheet() -> None:
    codes = re.findall(r"^\| `([A-Z_]+)` \|", _convention("C3.2"), re.MULTILINE)
    assert codes == list(get_args(ReasonCode))


def test_provenance_labels_are_those_of_the_sheet() -> None:
    labels = re.findall(r"^\| `([A-Z_]+)` \|", _convention("C4.1"), re.MULTILINE)
    assert labels == list(get_args(Provenance))


def test_purpose_list_is_the_one_the_producer_proposed() -> None:
    assert get_args(Purpose) == ("grain", "cover", "pasture")


def test_management_closed_lists_are_those_of_issue_95() -> None:
    assert get_args(Residue) == ("left_on_surface", "incorporated", "removed")
    assert get_args(TerminationMethod) == ("chemical", "mechanical", "frost")


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
