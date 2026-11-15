"""Mutant-killing tests for ``params/catalogue.py``.

Every record built here is a placeholder: its values are synthetic
(PLACEHOLDER test inputs only) and mean nothing.
"""

from __future__ import annotations

import copy
import json

import pytest

from params import catalogue
from params.catalogue import (
    Missing,
    check_catalogue,
    check_folder,
    check_layout,
    check_record,
    find_duplicates,
    find_placeholders,
    identity,
    is_placeholder,
    load_folder,
    parse_record_text,
    read_range,
    read_value,
)

WORD = "PLACEHOLDER"


def placeholder_record(**changes):
    """Return a well-formed placeholder record with optional top-level overrides."""
    record = {
        "id": "PLACEHOLDER_parameter",
        "scope": {"crop": "PLACEHOLDER_crop"},
        "value": 2.0,
        "unit": "PLACEHOLDER_unit",
        "range": {"low": 1.0, "high": 3.0, "basis": "PLACEHOLDER basis"},
        "citation": {
            "reference": "PLACEHOLDER reference",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
    }
    record.update(copy.deepcopy(changes))
    return record


def unmarked(item):
    """Return an in-memory copy without the PLACEHOLDER marker word."""
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {unmarked(key): unmarked(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmarked(value) for value in item]
    return item


# --- range boundaries and propagation ----------------------------------------


@pytest.mark.parametrize(
    "value, low, high",
    [
        (2.0, 2.0, 2.0),  # low == high == value
        (1.0, 1.0, 3.0),  # value == low
        (3.0, 1.0, 3.0),  # value == high
    ],
    ids=["degenerate-point-range", "at-low-boundary", "at-high-boundary"],
)
def test_range_inclusive_boundaries_are_accepted(value, low, high):
    record = placeholder_record(
        value=value,
        range={"low": low, "high": high, "basis": "PLACEHOLDER basis"},
    )
    assert check_record(record) == []
    assert read_value(unmarked(record)) == value
    assert read_range(unmarked(record)) == (low, high)


@pytest.mark.parametrize("bound_key", ["low", "high"])
@pytest.mark.parametrize(
    "bad_bound",
    [True, False, float("nan"), float("inf"), float("-inf")],
    ids=["True", "False", "nan", "inf", "-inf"],
)
def test_range_bound_rejects_booleans_and_non_finite_floats(bound_key, bad_bound):
    record = placeholder_record()
    record["range"][bound_key] = bad_bound
    problems = check_record(record)
    assert any(f"'range.{bound_key}'" in p for p in problems), problems
    with pytest.raises(ValueError):
        read_range(unmarked(record))


@pytest.mark.parametrize("basis", ["", "   \t", None, 123])
def test_range_basis_must_be_non_empty_text(basis):
    record = placeholder_record()
    record["range"]["basis"] = basis
    problems = check_record(record)
    assert any("'range.basis'" in p for p in problems), problems


def test_missing_value_does_not_skip_range_ordering_check():
    record = placeholder_record(
        value=None,
        value_missing_reason="PLACEHOLDER reason",
        range={"low": 5.0, "high": 1.0, "basis": "PLACEHOLDER basis"},
    )
    problems = check_record(record)
    assert any("greater than" in p for p in problems), problems


def test_negative_unrepresentable_integer_is_rejected():
    record = placeholder_record(
        value=-(2**53) - 1,
        range={"low": -(2**53) - 3, "high": 0, "basis": "PLACEHOLDER basis"},
    )
    problems = check_record(record)
    assert any("'value' cannot be read back unchanged" in p for p in problems)
    assert any("'range.low' cannot be read back unchanged" in p for p in problems)


# --- id, unit, note -----------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["_PLACEHOLDER", "PLACEHOLDER\n", "PLACEHOLDER\t1", "1PLACEHOLDER"],
    ids=["leading-underscore", "trailing-newline", "tab", "leading-digit"],
)
def test_id_pattern_and_fullmatch_boundaries(bad_id):
    problems = check_record(placeholder_record(id=bad_id))
    assert any("'id'" in p for p in problems), problems


def test_single_letter_and_digit_underscore_ids_are_accepted():
    for valid_id in ("A", "PLACEHOLDER_1"):
        record = placeholder_record(id=valid_id)
        assert check_record(record) == []


@pytest.mark.parametrize("bad_note", ["   \t\n", None, 42, False])
def test_note_rejects_whitespace_and_non_strings(bad_note):
    problems = check_record(placeholder_record(note=bad_note))
    assert any("'note'" in p for p in problems), problems


@pytest.mark.parametrize("bad_unit", ["\t\n", True])
def test_unit_rejects_whitespace_and_bool(bad_unit):
    problems = check_record(placeholder_record(unit=bad_unit))
    assert any("'unit'" in p for p in problems), problems


# --- scope matching, scope keys, and identity ---------------------------------


def test_all_documented_scope_keys_are_accepted():
    expected_keys = ("crop", "stage", "management", "soil", "region")
    assert catalogue.SCOPE_KEYS == expected_keys
    for key in expected_keys:
        record = placeholder_record(scope={key: f"PLACEHOLDER_{key}"})
        assert check_record(record) == [], key
    all_keys = {key: f"PLACEHOLDER_{key}" for key in expected_keys}
    assert check_record(placeholder_record(scope=all_keys)) == []


@pytest.mark.parametrize(
    "bad_scope",
    [
        {"crop": "   \t"},
        {1: "PLACEHOLDER_crop"},
        {"unknown_key": "PLACEHOLDER_val"},
        True,
    ],
    ids=["whitespace-value", "non-str-key", "unknown-key", "bool"],
)
def test_malformed_scope_rejected_by_check_and_identity(bad_scope):
    record = placeholder_record(scope=bad_scope)
    assert check_record(record)
    with pytest.raises(ValueError):
        identity(record)


def test_identity_collapses_internal_whitespace_and_distinguishes_keys_and_subsets():
    base = placeholder_record(scope={"crop": "PLACEHOLDER  name"})
    tabbed = placeholder_record(scope={"crop": "placeholder\tname"})
    assert identity(base) == identity(tabbed)
    assert len(find_duplicates({"a.json": base, "b.json": tabbed})) == 1

    # Same value under a different scope key is a distinct identity.
    other_key = placeholder_record(scope={"soil": "PLACEHOLDER  name"})
    assert identity(base) != identity(other_key)
    assert find_duplicates({"a.json": base, "b.json": other_key}) == []

    # Subset vs superset scope is a distinct identity.
    superset = placeholder_record(
        scope={"crop": "PLACEHOLDER  name", "soil": "PLACEHOLDER_soil"}
    )
    assert identity(base) != identity(superset)
    assert find_duplicates({"a.json": base, "b.json": superset}) == []

    # Different id with identical scope is a distinct identity.
    other_id = placeholder_record(
        id="PLACEHOLDER_other_parameter", scope={"crop": "PLACEHOLDER  name"}
    )
    assert identity(base) != identity(other_id)
    assert find_duplicates({"a.json": base, "b.json": other_id}) == []


def test_identity_rejects_malformed_id_and_non_dict():
    for bad in (
        None,
        [],
        placeholder_record(id="_PLACEHOLDER"),
        placeholder_record(id="PLACEHOLDER\n"),
    ):
        with pytest.raises(ValueError):
            identity(bad)


def test_duplicates_reports_three_way_collision_and_non_mapping():
    records = {
        "a.json": placeholder_record(),
        "b.json": placeholder_record(value=1.5),
        "c.json": placeholder_record(value=2.5),
    }
    problems = find_duplicates(records)
    assert len(problems) == 1
    assert all(name in problems[0] for name in ("a.json", "b.json", "c.json"))

    for non_mapping in ([], None, "PLACEHOLDER"):
        assert find_duplicates(non_mapping) == [catalogue._NOT_A_MAPPING]
        assert find_placeholders(non_mapping) == [catalogue._NOT_A_MAPPING]
        assert check_catalogue(non_mapping) == [catalogue._NOT_A_MAPPING]


# --- unsigned rejection and persons -------------------------------------------


@pytest.mark.parametrize(
    "checked_by",
    ["", "   \t\n", None, 123, "PLACEHOLDER_person_one", "  placeholder_PERSON_one\n"],
    ids=["empty", "whitespace", "none", "int", "same-exact", "same-normalised"],
)
def test_unsigned_or_self_checked_record_is_rejected_and_refused(checked_by):
    record = placeholder_record(checked_by=checked_by)
    assert check_record(record)
    assert check_catalogue({"unsigned.json": unmarked(record)})
    with pytest.raises(ValueError):
        read_value(unmarked(record))
    with pytest.raises(ValueError):
        read_range(unmarked(record))


def test_absent_checked_by_is_rejected_and_refused():
    record = placeholder_record()
    del record["checked_by"]
    assert any("'checked_by'" in p for p in check_record(record))
    with pytest.raises(ValueError):
        read_value(unmarked(record))
    with pytest.raises(ValueError):
        read_range(unmarked(record))


def test_internal_whitespace_same_person_is_rejected():
    record = placeholder_record(
        transcribed_by="PLACEHOLDER\tperson\none",
        checked_by="placeholder  person one",
    )
    problems = check_record(record)
    assert any("same person" in p for p in problems), problems
    with pytest.raises(ValueError):
        read_value(unmarked(record))


# --- citation mutants ---------------------------------------------------------


def test_value_with_missing_range_still_requires_non_null_citation():
    record = placeholder_record(
        range=None,
        range_missing_reason="PLACEHOLDER no range",
        citation=None,
    )
    problems = check_record(record)
    assert problems == ["a record with a value needs a citation"]
    with pytest.raises(ValueError):
        read_value(unmarked(record))


@pytest.mark.parametrize("bad_locator", ["", "   \t", None, 99])
def test_citation_locator_must_be_non_empty_string(bad_locator):
    record = placeholder_record()
    record["citation"]["locator"] = bad_locator
    problems = check_record(record)
    assert any("'citation.locator'" in p for p in problems), problems


@pytest.mark.parametrize("bad_url", ["", "   \t", None, 99])
def test_citation_url_when_given_must_be_non_empty_string(bad_url):
    record = placeholder_record()
    record["citation"]["url"] = bad_url
    problems = check_record(record)
    assert any("'citation.url'" in p for p in problems), problems


@pytest.mark.parametrize("field", ["reference", "locator", "url"])
def test_citation_needed_rejected_in_any_citation_field(field):
    record = placeholder_record()
    record["citation"][field] = "PLACEHOLDER citation\n\tNEEDED"
    problems = check_record(record)
    assert any(
        f"'citation.{field}'" in p and "CITATION NEEDED" in p for p in problems
    ), problems
    with pytest.raises(ValueError):
        read_value(unmarked(record))


# --- placeholder, parser, and folder layout -----------------------------------


def test_is_placeholder_finds_word_in_tuples_and_mixed_case_keys():
    assert is_placeholder(("text", ("PlaceHolder",))) is True
    assert is_placeholder({"outer": (1, {"pLaCeHoLdEr_key": 2})}) is True
    assert is_placeholder(("text", (1, None))) is False


def test_parse_record_text_rejects_nested_repeated_key_nested_nan_and_non_str():
    with pytest.raises(ValueError, match="repeated key"):
        parse_record_text(
            '{"id": "PLACEHOLDER", "scope": {"crop": "PLACEHOLDER_a", "crop": "PLACEHOLDER_b"}}'
        )
    with pytest.raises(ValueError):
        parse_record_text('{"id": "PLACEHOLDER", "extra": [1, NaN]}')
    with pytest.raises(ValueError):
        parse_record_text('{"id": "PLACEHOLDER", "extra": [-Infinity]}')
    for non_str in (b"{}", None, 123):
        with pytest.raises(ValueError):
            parse_record_text(non_str)


def test_load_folder_reports_invalid_utf8_and_scalar_json(tmp_path):
    (tmp_path / "bad_bytes.json").write_bytes(b"\xff\xfe\x00\x00")
    (tmp_path / "scalar.json").write_text("123", encoding="utf-8")

    records, load_problems = load_folder(tmp_path)
    assert "scalar.json" in records
    assert len(load_problems) == 1
    assert load_problems[0].startswith("bad_bytes.json: not a readable record file")

    folder_problems = check_folder(tmp_path)
    assert any(
        p.startswith("scalar.json: the record is not a JSON object")
        for p in folder_problems
    )


def test_check_layout_allows_examples_and_rejects_root_json(tmp_path):
    (tmp_path / "records").mkdir()
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "PLACEHOLDER_ex.json").write_text(
        json.dumps(placeholder_record()), encoding="utf-8"
    )
    assert check_layout(tmp_path) == []

    (tmp_path / "stray.json").write_text(
        json.dumps(placeholder_record()), encoding="utf-8"
    )
    problems = check_layout(tmp_path)
    assert len(problems) == 1
    assert problems[0].startswith("stray.json: a record file outside")


def test_missing_value_record_read_returns_missing_not_number():
    record = unmarked(
        placeholder_record(
            value=None,
            value_missing_reason="PLACEHOLDER missing",
            range=None,
            range_missing_reason="PLACEHOLDER no range",
            citation=None,
        )
    )
    assert check_record(record) == []
    val = read_value(record)
    rng = read_range(record)
    assert isinstance(val, Missing)
    assert isinstance(rng, Missing)
    assert val.reason == "UNMARKED_TEST_ONLY missing"
    assert rng.reason == "UNMARKED_TEST_ONLY no range"
