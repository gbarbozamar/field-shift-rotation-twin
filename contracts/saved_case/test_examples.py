"""Acceptance test of unit l0/contracts-saved-case.

The PLACEHOLDER example loads into its model, each part it carries loads into
the model of its own contract, and the example written with
``model_dump(mode="json")`` loads back equal to itself. Each invalid variant
of the example is rejected for its stated reason, and each accepted variant
loads. The variants are PROPOSED (blueprint section 3.7) and are listed in
``README.md`` under "PROPOSED cases"; a test checks that the two lists agree.

Run from the repository root: ``python -m pytest contracts/saved_case/``.
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

from contracts.carbon_balance import CarbonBalance
from contracts.decision_output import DecisionOutput
from contracts.field_identity import FieldIdentity
from contracts.inputs.common import Missing, ReasonCode
from contracts.results.models import ResultsTable

from .saved_case import CarbonBalanceItem, SavedCase

HERE = Path(__file__).parent
CONTRACTS = HERE.parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_saved_case.json"
README = HERE / "README.md"

# The example of each folder that a part of the saved-case example comes from.
SOURCE_OF_FIELD_IDENTITY = "field_identity/examples/PLACEHOLDER_field_identity.json"
SOURCE_OF_RESULTS_TABLE = "results/examples/PLACEHOLDER_results_table.json"
SOURCE_OF_CARBON_BALANCE = "carbon_balance/examples/PLACEHOLDER_carbon_balance.json"
SOURCE_OF_DECISION_OUTPUT = "decision_output/examples/PLACEHOLDER_decision_output.json"

# Every identifier changed in the example, per part: aligned to the field
# identity example (README.md, "The example"). The results table mapping is
# the one the decision output test already uses for the same two examples.
IDENTIFIERS_CHANGED: dict[str, dict[str, str]] = {
    "results_table": {
        "PLACEHOLDER_case": "example-case",
        "PLACEHOLDER_field": "example-field-1",
        "PLACEHOLDER_rotation_a": "example-rotation-1",
        "PLACEHOLDER_rotation_b": "example-rotation-2",
    },
    "carbon_balance": {
        "PLACEHOLDER-case": "example-case",
        "PLACEHOLDER-field": "example-field-1",
        "PLACEHOLDER-rotation": "example-rotation-1",
    },
}
IDENTIFIER_KEYS = ("case_id", "field_id", "rotation_id")

Mutation = Callable[[dict[str, Any]], None]


def load() -> dict[str, Any]:
    return json.loads((EXAMPLES / EXAMPLE).read_text(encoding="utf-8"))


def load_source(relative: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))


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


def align(document: Any, mapping: dict[str, str]) -> Any:
    """The document with the identifiers of ``mapping`` changed, and nothing else."""
    if isinstance(document, dict):
        return {
            key: (
                mapping.get(value, value)
                if key in IDENTIFIER_KEYS and isinstance(value, str)
                else align(value, mapping)
            )
            for key, value in document.items()
        }
    if isinstance(document, list):
        return [align(item, mapping) for item in document]
    return document


FIELD_IDENTITY = ["field_identity"]
RESULTS_TABLE = ["results_table"]
DECISION_OUTPUT = ["decision_output"]
AMG_1 = ["carbon_balances", 0]  # example-rotation-1, amg: the one balance
ROTHC_1 = ["carbon_balances", 1]  # example-rotation-1, rothc: missing
AMG_2 = ["carbon_balances", 2]  # example-rotation-2, amg: missing
BALANCE = [*AMG_1, "carbon_balance"]
REASON = {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER detail"}


def missing(name: str, reason: dict[str, Any] | None = None) -> Mutation:
    """The top-level part ``name`` becomes null, with its missing part."""
    return both(
        put([name], None),
        put([f"{name}_missing"], reason or {"reason": "NOT_AVAILABLE"}),
    )


def missing_balance(index: int) -> Mutation:
    """The balance of the carbon item ``index`` becomes null, with its missing part."""
    return both(
        put(["carbon_balances", index, "carbon_balance"], None),
        put(["carbon_balances", index, "carbon_balance_missing"], REASON),
    )


def every_carbon_item_missing() -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for index in range(len(data["carbon_balances"])):
            missing_balance(index)(data)

    return mutate


def example_data_everywhere(value: bool) -> Mutation:
    """The document and every part that carries ``example_data`` say ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        data["example_data"] = value
        for name in ("field_identity", "decision_output"):
            if data[name] is not None:
                data[name]["example_data"] = value
        for item in data["carbon_balances"]:
            if item["carbon_balance"] is not None:
                item["carbon_balance"]["example_data"] = value

    return mutate


def run_of_field(field_id: str) -> Mutation:
    """The document, and every part that names a field, name ``field_id``."""

    def mutate(data: dict[str, Any]) -> None:
        data["field_id"] = field_id
        for name in ("results_table", "decision_output"):
            data[name]["field_id"] = field_id
        for item in data["carbon_balances"]:
            if item["carbon_balance"] is not None:
                item["carbon_balance"]["field_id"] = field_id

    return mutate


def leave_out_the_missing_members_of_present_parts() -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for name in ("field_identity", "results_table", "decision_output"):
            if data[f"{name}_missing"] is None:
                del data[f"{name}_missing"]
        for item in data["carbon_balances"]:
            if item["carbon_balance_missing"] is None:
                del item["carbon_balance_missing"]

    return mutate


def add_carbon_item(rotation_id: str, carbon_model: str) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        data["carbon_balances"].append(
            {
                "rotation_id": rotation_id,
                "carbon_model": carbon_model,
                "carbon_balance": None,
                "carbon_balance_missing": copy.deepcopy(REASON),
            }
        )

    return mutate


# (case identifier, mutation, fragment of the expected error).
# The fragment shows that the variant is rejected for the intended reason.
INVALID: list[tuple[str, Mutation, str]] = [
    # --- The header -----------------------------------------------------------
    (
        "unknown-member-of-the-document",
        put(["tipping_point"], {"value": None}),
        "tipping_point",
    ),
    (
        "unknown-member-of-a-carbon-item",
        put([*ROTHC_1, "variant"], "placeholder_variant"),
        "carbon_balances.1.variant",
    ),
    ("contract-of-another-name", put(["contract"], "field_identity"), "contract"),
    ("example-data-as-text", put(["example_data"], "true"), "example_data"),
    ("case-id-blank", put(["case_id"], "   "), "case_id"),
    ("field-id-blank", put(["field_id"], ""), "field_id"),
    ("saved-on-not-a-date", put(["saved_on"], "15 November 2026"), "saved_on"),
    ("saved-on-with-a-time", put(["saved_on"], "2026-11-15T05:35:00"), "saved_on"),
    ("saved-on-null", put(["saved_on"], None), "saved_on"),
    # --- A part and its missing part ------------------------------------------
    (
        "field-identity-null-without-missing-part",
        put(FIELD_IDENTITY, None),
        "field_identity: a part that is null carries field_identity_missing",
    ),
    (
        "results-table-null-without-missing-part",
        put(RESULTS_TABLE, None),
        "results_table: a part that is null carries results_table_missing",
    ),
    (
        "decision-output-null-without-missing-part",
        put(DECISION_OUTPUT, None),
        "decision_output: a part that is null carries decision_output_missing",
    ),
    (
        "carbon-balance-null-without-missing-part",
        put(BALANCE, None),
        "carbon_balance: a part that is null carries carbon_balance_missing",
    ),
    (
        "field-identity-and-missing-part-both",
        put(["field_identity_missing"], REASON),
        "field_identity: a part holds its document or field_identity_missing, never both",
    ),
    (
        "results-table-and-missing-part-both",
        put(["results_table_missing"], REASON),
        "results_table: a part holds its document or results_table_missing, never both",
    ),
    (
        "decision-output-and-missing-part-both",
        put(["decision_output_missing"], REASON),
        "decision_output: a part holds its document or decision_output_missing, never both",
    ),
    (
        "carbon-balance-and-missing-part-both",
        put([*AMG_1, "carbon_balance_missing"], REASON),
        "carbon_balance: a part holds its document or carbon_balance_missing, never both",
    ),
    (
        "missing-part-with-reason-not-in-the-sheet",
        missing("field_identity", {"reason": "NOT_SAVED"}),
        "field_identity_missing.reason",
    ),
    (
        "missing-part-with-reason-in-lower-case",
        put([*ROTHC_1, "carbon_balance_missing", "reason"], "not_available"),
        "carbon_balances.1.carbon_balance_missing.reason",
    ),
    (
        "missing-part-without-reason",
        missing("results_table", {"detail": "PLACEHOLDER detail"}),
        "results_table_missing.reason",
    ),
    (
        "missing-input-without-detail",
        missing("decision_output", {"reason": "MISSING_INPUT"}),
        "needs a detail that names the input",
    ),
    # --- The carbon items -----------------------------------------------------
    (
        "two-carbon-items-for-one-rotation-and-model",
        put([*ROTHC_1, "carbon_model"], "amg"),
        "two carbon items for rotation 'example-rotation-1' and carbon model 'amg'",
    ),
    (
        "carbon-item-of-another-rotation-than-its-balance",
        put([*BALANCE, "rotation_id"], "example-rotation-2"),
        "the rotation_id of the item is the rotation_id of the balance",
    ),
    (
        "carbon-item-of-another-model-than-its-balance",
        both(drop(ROTHC_1), put([*AMG_1, "carbon_model"], "rothc")),
        "the carbon_model of the item is the carbon_model of the balance",
    ),
    (
        "carbon-model-not-decided",
        put([*ROTHC_1, "carbon_model"], "RothC"),
        "carbon_balances.1.carbon_model",
    ),
    # --- A carried document of another case or field ---------------------------
    (
        "field-identity-of-another-case",
        put([*FIELD_IDENTITY, "case_id"], "example-case-2"),
        "field_identity: its case_id is not the case_id of the saved case",
    ),
    (
        "field-identity-without-the-field",
        put([*FIELD_IDENTITY, "fields", 0, "field_id"], "example-field-9"),
        "field_identity: the field_id of the saved case is not a field of the case",
    ),
    (
        "results-table-of-another-case",
        put([*RESULTS_TABLE, "case_id"], "example-case-2"),
        "results_table: its case_id is not the case_id of the saved case",
    ),
    (
        "results-table-of-another-field",
        put([*RESULTS_TABLE, "field_id"], "example-field-2"),
        "results_table: its field_id is not the field_id of the saved case",
    ),
    (
        "carbon-balance-of-another-case",
        put([*BALANCE, "case_id"], "example-case-2"),
        "carbon_balances.0.carbon_balance: its case_id is not the case_id",
    ),
    (
        "carbon-balance-of-another-field",
        put([*BALANCE, "field_id"], "example-field-2"),
        "carbon_balances.0.carbon_balance: its field_id is not the field_id",
    ),
    (
        "decision-output-of-another-case",
        put([*DECISION_OUTPUT, "case_id"], "example-case-2"),
        "decision_output: its case_id is not the case_id of the saved case",
    ),
    (
        "decision-output-of-another-field",
        put([*DECISION_OUTPUT, "field_id"], "example-field-2"),
        "decision_output: its field_id is not the field_id of the saved case",
    ),
    # --- example_data -----------------------------------------------------------
    (
        "example-data-false-while-the-field-identity-says-true",
        both(
            example_data_everywhere(False), put([*FIELD_IDENTITY, "example_data"], True)
        ),
        "example_data: field_identity is example data",
    ),
    (
        "example-data-false-while-a-carbon-balance-says-true",
        both(example_data_everywhere(False), put([*BALANCE, "example_data"], True)),
        "example_data: carbon_balances.0.carbon_balance is example data",
    ),
    (
        "example-data-false-while-the-decision-output-says-true",
        both(
            example_data_everywhere(False),
            put([*DECISION_OUTPUT, "example_data"], True),
        ),
        "example_data: decision_output is example data",
    ),
]

VALID: list[tuple[str, Mutation]] = [
    ("accepted-every-carbon-item-missing", every_carbon_item_missing()),
    ("accepted-not-example-data", example_data_everywhere(False)),
    (
        "accepted-field-identity-with-one-field",
        put([*FIELD_IDENTITY, "fields"], load()["field_identity"]["fields"][:1]),
    ),
    ("accepted-run-of-another-field-of-the-case", run_of_field("example-field-2")),
    ("accepted-field-identity-missing", missing("field_identity", REASON)),
    ("accepted-results-table-missing", missing("results_table", REASON)),
    ("accepted-decision-output-missing", missing("decision_output", REASON)),
    (
        "accepted-every-part-missing",
        both(
            missing("field_identity", REASON),
            missing("results_table", REASON),
            missing("decision_output", REASON),
            every_carbon_item_missing(),
        ),
    ),
    (
        "accepted-missing-part-without-detail",
        missing("results_table", {"reason": "NOT_AVAILABLE"}),
    ),
    (
        "accepted-missing-input-with-detail",
        missing(
            "decision_output",
            {"reason": "MISSING_INPUT", "detail": "PLACEHOLDER detail: results_table"},
        ),
    ),
    (
        "accepted-missing-members-left-out",
        leave_out_the_missing_members_of_present_parts(),
    ),
    # --- Accepted only while a question is open -------------------------------
    (
        "accepted-while-open-example-data-true-while-no-part-says-so",
        both(example_data_everywhere(False), put(["example_data"], True)),
    ),
    ("accepted-while-open-no-carbon-item", put(["carbon_balances"], [])),
    (
        "accepted-while-open-carbon-item-of-a-rotation-not-in-the-results",
        add_carbon_item("example-rotation-3", "amg"),
    ),
    (
        "accepted-while-open-rotation-of-the-results-without-a-carbon-item",
        both(drop(AMG_2), drop(AMG_2)),  # both items of example-rotation-2
    ),
]


def test_example_loads_into_its_model() -> None:
    text = (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    loaded = SavedCase.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert SavedCase.model_validate(json.loads(text)) == loaded


def test_each_part_loads_into_the_model_of_its_own_contract() -> None:
    """The parts are the documents of the contracts that exist, imported, not copied."""
    data = load()
    loaded = SavedCase.model_validate(data)
    assert type(loaded.field_identity) is FieldIdentity
    assert FieldIdentity.model_validate(data["field_identity"]) == loaded.field_identity
    assert type(loaded.results_table) is ResultsTable
    assert ResultsTable.model_validate(data["results_table"]) == loaded.results_table
    assert type(loaded.decision_output) is DecisionOutput
    assert (
        DecisionOutput.model_validate(data["decision_output"]) == loaded.decision_output
    )
    present = [i for i in loaded.carbon_balances if i.carbon_balance is not None]
    absent = [i for i in loaded.carbon_balances if i.carbon_balance is None]
    assert len(present) == 1 and len(absent) == 3
    for item, written in zip(
        loaded.carbon_balances, data["carbon_balances"], strict=True
    ):
        assert type(item) is CarbonBalanceItem
        if item.carbon_balance is None:
            assert type(item.carbon_balance_missing) is Missing
            continue
        assert type(item.carbon_balance) is CarbonBalance
        assert (
            CarbonBalance.model_validate(written["carbon_balance"])
            == item.carbon_balance
        )


def test_example_written_with_model_dump_loads_back_equal_to_itself() -> None:
    loaded = SavedCase.model_validate_json(
        (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    )
    written = loaded.model_dump(mode="json")
    assert SavedCase.model_validate(written) == loaded
    assert SavedCase.model_validate_json(json.dumps(written)) == loaded
    assert SavedCase.model_validate(written).model_dump(mode="json") == written
    # D177: the document is written with every null kept.
    assert written["field_identity_missing"] is None
    assert written["carbon_balances"][1]["carbon_balance"] is None


def test_a_document_written_without_its_nulls_does_not_load() -> None:
    """Why D177 keeps every null: ``exclude_none=True`` drops required keys."""
    loaded = SavedCase.model_validate(load())
    with pytest.raises(ValidationError):
        SavedCase.model_validate(loaded.model_dump(mode="json", exclude_none=True))


def test_example_is_marked_as_example_data() -> None:
    assert EXAMPLE.startswith("PLACEHOLDER_")
    data = load()
    assert data["example_data"] is True
    assert data["field_identity"]["example_data"] is True
    assert data["decision_output"]["example_data"] is True
    assert data["carbon_balances"][0]["carbon_balance"]["example_data"] is True


def test_the_folder_holds_one_example() -> None:
    assert [path.name for path in EXAMPLES.iterdir()] == [EXAMPLE]


def test_example_shows_a_field_identity_with_several_fields() -> None:
    data = load()
    fields = [field["field_id"] for field in data["field_identity"]["fields"]]
    assert len(fields) > 1
    assert data["field_id"] in fields


def test_the_parts_of_the_example_are_the_examples_of_their_folders() -> None:
    """README.md, "The example": each part, and the identifiers changed in it."""
    data = load()
    assert data["field_identity"] == load_source(SOURCE_OF_FIELD_IDENTITY)
    assert data["decision_output"] == load_source(SOURCE_OF_DECISION_OUTPUT)
    assert data["results_table"] == align(
        load_source(SOURCE_OF_RESULTS_TABLE), IDENTIFIERS_CHANGED["results_table"]
    )
    assert data["carbon_balances"][0]["carbon_balance"] == align(
        load_source(SOURCE_OF_CARBON_BALANCE), IDENTIFIERS_CHANGED["carbon_balance"]
    )
    # The changed identifiers are those of the field identity example and of
    # the decision output example, which shares them.
    identity = load_source(SOURCE_OF_FIELD_IDENTITY)
    decision = load_source(SOURCE_OF_DECISION_OUTPUT)
    aligned_to = {identity["case_id"], *(f["field_id"] for f in identity["fields"])}
    aligned_to |= set(decision["rotations"])
    for mapping in IDENTIFIERS_CHANGED.values():
        assert set(mapping.values()) <= aligned_to


def test_readme_lists_every_identifier_changed() -> None:
    readme = README.read_text(encoding="utf-8")
    for mapping in IDENTIFIERS_CHANGED.values():
        for old, new in mapping.items():
            assert f"`{old}` → `{new}`" in readme, f"README.md does not list {old}"


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
        SavedCase.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        SavedCase.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    loaded = SavedCase.model_validate(variant)
    assert SavedCase.model_validate_json(json.dumps(variant)) == loaded
    # Every accepted variant also survives being written and read back.
    assert SavedCase.model_validate(loaded.model_dump(mode="json")) == loaded


DOCUMENT_KEYS = (
    "contract",
    "example_data",
    "case_id",
    "field_id",
    "saved_on",
    "field_identity",
    "results_table",
    "carbon_balances",
    "decision_output",
)
CARBON_ITEM_KEYS = ("rotation_id", "carbon_model", "carbon_balance")


@pytest.mark.parametrize(
    "path",
    [pytest.param([key], id=f"document-{key}") for key in DOCUMENT_KEYS]
    + [
        pytest.param([*ROTHC_1, key], id=f"carbon-item-{key}")
        for key in CARBON_ITEM_KEYS
    ],
)
def test_no_member_can_be_left_out(path: list[Any]) -> None:
    """A part is never left out: it is its document or null with its missing part."""
    data = load()
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        SavedCase.model_validate(data)
    location = ".".join(str(part) for part in path)
    assert f"{location}: " in _describe(rejected.value)


@pytest.mark.parametrize("reason", get_args(ReasonCode))
def test_a_missing_part_takes_every_code_of_the_sheet(reason: str) -> None:
    """C3.2: the reason of a missing part is any of its eight codes."""
    variant = load()
    detail = {"detail": "PLACEHOLDER detail"} if reason == "MISSING_INPUT" else {}
    missing("results_table", {"reason": reason, **detail})(variant)
    put([*ROTHC_1, "carbon_balance_missing"], {"reason": reason, **detail})(variant)
    SavedCase.model_validate(variant)


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in (
        "## PROPOSED cases",
        "## Differences from #251",
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


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
