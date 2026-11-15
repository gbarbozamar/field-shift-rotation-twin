"""Mutant-killing and boundary tests for ``contracts/saved_case/``.

Covers ``saved_on`` UTC minute format, complete carbon items, unknown rotation
rejection, variant key uniqueness, and carried document invariants using
PLACEHOLDER test inputs only.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.saved_case import saved_case
from contracts.saved_case.saved_case import SavedCase

EXAMPLE_PATH = Path(__file__).parent / "examples" / "PLACEHOLDER_saved_case.json"
PLACEHOLDER_IDS = {
    "example-case": "PLACEHOLDER-case",
    "example-field-1": "PLACEHOLDER-field-1",
    "example-field-2": "PLACEHOLDER-field-2",
    "example-field-3": "PLACEHOLDER-field-3",
    "example-rotation-1": "PLACEHOLDER-rotation-1",
    "example-rotation-2": "PLACEHOLDER-rotation-2",
}


def _rewrite_ids(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, str):
        return mapping.get(node, node)
    if isinstance(node, list):
        return [_rewrite_ids(item, mapping) for item in node]
    if isinstance(node, dict):
        return {key: _rewrite_ids(value, mapping) for key, value in node.items()}
    return node


def _base_case() -> dict[str, Any]:
    raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    return _rewrite_ids(raw, PLACEHOLDER_IDS)


def _set_field_everywhere(doc: dict[str, Any], field_id: str) -> None:
    doc["field_id"] = field_id
    for key in ("results_table", "decision_output"):
        if doc[key] is not None:
            doc[key]["field_id"] = field_id
    for item in doc["carbon_balances"]:
        if item["carbon_balance"] is not None:
            item["carbon_balance"]["field_id"] = field_id


def _set_example_data_everywhere(doc: dict[str, Any], flag: bool) -> None:
    doc["example_data"] = flag
    for key in ("field_identity", "decision_output"):
        if doc[key] is not None:
            doc[key]["example_data"] = flag
    for item in doc["carbon_balances"]:
        if item["carbon_balance"] is not None:
            item["carbon_balance"]["example_data"] = flag


@contextmanager
def _weaken_model_validator(
    cls: type[BaseModel], name: str, replacement: Any
) -> Iterator[None]:
    """Temporarily replace a Pydantic model_validator and rebuild the schema."""
    decorator = cls.__pydantic_decorators__.model_validators[name]
    with patch.object(decorator, "func", replacement):
        cls.model_rebuild(force=True)
        try:
            yield
        finally:
            pass
    cls.model_rebuild(force=True)


# --- saved_on UTC minute format & timezone boundaries (#297 / #384) ----------


@pytest.mark.parametrize(
    "valid_stamp",
    [
        "2026-01-01T00:00Z",
        "2026-12-31T23:59Z",
        "2024-02-29T12:00Z",
    ],
    ids=["year-start-midnight", "year-end-2359", "leap-day"],
)
def test_saved_on_valid_utc_minute_boundaries(valid_stamp: str) -> None:
    doc = _base_case()
    doc["saved_on"] = valid_stamp
    loaded = SavedCase.model_validate(doc)
    assert loaded.model_dump(mode="json")["saved_on"] == valid_stamp


@pytest.mark.parametrize(
    "bad_stamp",
    [
        "2026-11-15T24:00Z",
        "2026-11-15T23:60Z",
        "2025-02-29T12:00Z",
        "2026-04-31T12:00Z",
        "2026-11-15T11:56z",
        "2026-11-15 11:56Z",
        "2026-11-15T11:56+00:00",
        "2026-11-15T11:56-00:00",
        "2026-11-15T11:56:00Z",
        "2026-11-15T11:56:00.000Z",
        "2026-11-15T08:56-03:00",
        "2026-11-15T11:56",
        "2026-11-15",
    ],
    ids=[
        "hour-24",
        "minute-60",
        "non-leap-feb-29",
        "apr-31",
        "lowercase-z",
        "space-separator",
        "plus-00-offset",
        "minus-00-offset",
        "with-seconds",
        "with-millis",
        "non-utc-offset",
        "missing-tz",
        "date-only",
    ],
)
def test_saved_on_rejects_off_by_one_and_non_utc_minute_formats(
    bad_stamp: str,
) -> None:
    doc = _base_case()
    doc["saved_on"] = bad_stamp
    with pytest.raises(ValidationError, match="YYYY-MM-DDTHH:MMZ"):
        SavedCase.model_validate(doc)


@pytest.mark.parametrize(
    "bad_dt",
    [
        dt.datetime(2026, 11, 15, 0, 0),
        dt.datetime(2026, 11, 15, 0, 0, 1, tzinfo=dt.UTC),
        dt.datetime(2026, 11, 15, 0, 0, 0, 1, tzinfo=dt.UTC),
        dt.datetime(2026, 11, 15, 0, 0, tzinfo=dt.timezone(dt.timedelta(minutes=1))),
        dt.date(2026, 11, 15),
    ],
    ids=["naive", "one-second", "one-microsecond", "one-minute-offset", "date-only"],
)
def test_saved_on_python_datetime_rejects_subminute_and_non_utc(bad_dt: Any) -> None:
    doc = _base_case()
    doc["saved_on"] = bad_dt
    with pytest.raises(ValidationError, match="YYYY-MM-DDTHH:MMZ"):
        SavedCase.model_validate(doc)


def test_saved_on_python_utc_minute_datetime_round_trips() -> None:
    doc = _base_case()
    doc["saved_on"] = dt.datetime(2026, 11, 15, 0, 0, tzinfo=dt.UTC)
    loaded = SavedCase.model_validate(doc)
    assert loaded.model_dump(mode="json")["saved_on"] == "2026-11-15T00:00Z"


# --- complete carbon items, unknown rotation rejection (#384), variant keys ---


def test_unknown_rotation_in_carbon_balances_is_rejected() -> None:
    doc = _base_case()
    doc["carbon_balances"].append(
        {
            "rotation_id": "PLACEHOLDER-rotation-unknown",
            "carbon_model": "amg",
            "variant": "placeholder_variant",
            "carbon_balance": None,
            "carbon_balance_missing": {
                "reason": "NOT_AVAILABLE",
                "detail": "PLACEHOLDER detail",
            },
        }
    )
    with pytest.raises(ValidationError, match="results table does not name"):
        SavedCase.model_validate(doc)


def test_missing_any_rotation_model_pair_is_rejected() -> None:
    for idx in range(len(_base_case()["carbon_balances"])):
        doc = _base_case()
        del doc["carbon_balances"][idx]
        with pytest.raises(ValidationError, match="no carbon item for rotation"):
            SavedCase.model_validate(doc)


def test_duplicate_missing_carbon_item_key_rejected_and_distinct_variant_accepted() -> (
    None
):
    # Duplicate (rotation_id, carbon_model, variant) even when both balances are None
    dup_doc = _base_case()
    dup_doc["carbon_balances"].append(copy.deepcopy(dup_doc["carbon_balances"][1]))
    with pytest.raises(ValidationError, match="two carbon items"):
        SavedCase.model_validate(dup_doc)

    # Distinct variant on same (rotation_id, carbon_model) is accepted
    var_doc = _base_case()
    extra = copy.deepcopy(var_doc["carbon_balances"][1])
    extra["variant"] = "placeholder_variant_alt"
    var_doc["carbon_balances"].append(extra)
    SavedCase.model_validate(var_doc)


@pytest.mark.parametrize("bad_variant", ["", "1a", "_a", "A", "a-b", "a b"])
def test_carbon_item_variant_rejects_invalid_quantity_ids(bad_variant: str) -> None:
    doc = _base_case()
    doc["carbon_balances"][1]["variant"] = bad_variant
    with pytest.raises(ValidationError):
        SavedCase.model_validate(doc)


# --- carried document cross-checks & example_data propagation ----------------


def test_secondary_field_in_field_identity_accepted_and_unknown_rejected() -> None:
    doc = _base_case()
    _set_field_everywhere(doc, "PLACEHOLDER-field-3")
    SavedCase.model_validate(doc)

    bad = _base_case()
    _set_field_everywhere(bad, "PLACEHOLDER-field-missing")
    with pytest.raises(ValidationError, match="not a field of the case"):
        SavedCase.model_validate(bad)


def test_example_data_true_when_all_parts_false_is_accepted_but_converse_rejected() -> (
    None
):
    doc = _base_case()
    _set_example_data_everywhere(doc, False)
    doc["example_data"] = True
    SavedCase.model_validate(doc)

    bad = _base_case()
    _set_example_data_everywhere(bad, False)
    bad["carbon_balances"][0]["carbon_balance"]["example_data"] = True
    with pytest.raises(ValidationError, match="is example data"):
        SavedCase.model_validate(bad)


# --- injected mutants proving guards fail when weakened ----------------------


def test_mutant_weakened_saved_on_regex_and_format_is_detected() -> None:
    doc = _base_case()
    doc["saved_on"] = "2026-11-15T11:56:00Z"
    with pytest.raises(ValidationError, match="YYYY-MM-DDTHH:MMZ"):
        SavedCase.model_validate(doc)
    with (
        patch.object(
            saved_case,
            "_SAVED_ON",
            re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
        ),
        patch.object(saved_case, "_SAVED_ON_FORMAT", "%Y-%m-%dT%H:%M:%SZ"),
    ):
        loaded = SavedCase.model_validate(doc)
        assert loaded.saved_on.second == 0


def test_mutant_weakened_check_part_or_missing_is_detected() -> None:
    doc = _base_case()
    doc["results_table"] = None
    with pytest.raises(ValidationError, match="results_table_missing"):
        SavedCase.model_validate(doc)
    with patch.object(saved_case, "_check_part_or_missing", lambda *args: None):
        SavedCase.model_validate(doc)


def test_mutant_weakened_carbon_models_tuple_is_detected() -> None:
    doc = _base_case()
    doc["carbon_balances"] = [
        item for item in doc["carbon_balances"] if item["carbon_model"] == "amg"
    ]
    with pytest.raises(ValidationError, match="carbon model 'rothc'"):
        SavedCase.model_validate(doc)
    with patch.object(saved_case, "CARBON_MODELS", ("amg",)):
        SavedCase.model_validate(doc)


def test_mutant_weakened_unknown_rotation_and_duplicate_guards_are_detected() -> None:
    unknown_rot = _base_case()
    unknown_rot["carbon_balances"].append(
        {
            "rotation_id": "PLACEHOLDER-rotation-unknown",
            "carbon_model": "amg",
            "variant": "placeholder_variant",
            "carbon_balance": None,
            "carbon_balance_missing": {"reason": "NOT_AVAILABLE"},
        }
    )
    with pytest.raises(ValidationError, match="results table does not name"):
        SavedCase.model_validate(unknown_rot)
    with _weaken_model_validator(
        SavedCase, "_carbon_items_complete", lambda self: self
    ):
        SavedCase.model_validate(unknown_rot)

    dup_item = _base_case()
    dup_item["carbon_balances"].append(copy.deepcopy(dup_item["carbon_balances"][1]))
    with pytest.raises(ValidationError, match="two carbon items"):
        SavedCase.model_validate(dup_item)
    with _weaken_model_validator(
        SavedCase, "_one_carbon_item_per_rotation_model_and_variant", lambda self: self
    ):
        SavedCase.model_validate(dup_item)


def test_mutant_weakened_carried_doc_and_example_data_guards_are_detected() -> None:
    bad_field = _base_case()
    _set_field_everywhere(bad_field, "PLACEHOLDER-field-missing")
    with pytest.raises(ValidationError, match="not a field of the case"):
        SavedCase.model_validate(bad_field)
    with _weaken_model_validator(
        SavedCase,
        "_carried_documents_belong_to_the_case_and_field",
        lambda self: self,
    ):
        SavedCase.model_validate(bad_field)

    bad_example = _base_case()
    _set_example_data_everywhere(bad_example, False)
    bad_example["decision_output"]["example_data"] = True
    with pytest.raises(ValidationError, match="is example data"):
        SavedCase.model_validate(bad_example)
    with _weaken_model_validator(
        SavedCase, "_example_data_when_a_part_is", lambda self: self
    ):
        SavedCase.model_validate(bad_example)
