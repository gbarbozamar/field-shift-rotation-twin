"""Acceptance test of the parameter catalogue layout.

Run with ``python -m pytest params/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7) and are listed with the
same codes in params/README.md under "PROPOSED cases". Every record built
here is a placeholder: its numbers mean nothing.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from params.catalogue import (
    Missing,
    check_catalogue,
    check_folder,
    check_record,
    find_duplicates,
    find_placeholders,
    is_placeholder,
    load_folder,
    parse_record_text,
    read_range,
    read_value,
)

HERE = Path(__file__).parent
RECORDS = HERE / "records"
EXAMPLES = HERE / "examples"


def placeholder_record(**changes):
    """A well-formed placeholder record, with top-level fields replaced."""
    record = {
        "id": "PLACEHOLDER_parameter",
        "scope": {"crop": "PLACEHOLDER_crop"},
        "value": 2.0,
        "unit": "PLACEHOLDER_unit",
        "range": {"low": 1.0, "high": 3.0, "basis": "PLACEHOLDER basis"},
        "citation": {
            "reference": "PLACEHOLDER reference. This is not a publication.",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER_person_one",
        "checked_by": "PLACEHOLDER_person_two",
    }
    record.update(copy.deepcopy(changes))
    return record


def without(record, *path):
    """A copy of the record with the field at ``path`` removed."""
    record = copy.deepcopy(record)
    holder = record
    for key in path[:-1]:
        holder = holder[key]
    del holder[path[-1]]
    return record


def missing_value_record(**changes):
    fields = {
        "value": None,
        "value_missing_reason": "PLACEHOLDER reason for the missing value",
    }
    fields.update(changes)
    return placeholder_record(**fields)


def assert_rejected(record, *expected_words):
    problems = check_record(record)
    assert problems, "the record was accepted"
    text = " | ".join(problems)
    for word in expected_words:
        assert word in text, f"expected '{word}' in: {text}"


# --- A: accepted ------------------------------------------------------------


def test_a1_well_formed_record_is_accepted():
    record = placeholder_record()
    assert check_record(record) == []
    assert read_value(record) == 2.0
    assert read_range(record) == (1.0, 3.0)


def test_a2_missing_value_with_reason_is_accepted_and_stays_missing():
    record = missing_value_record()
    assert check_record(record) == []

    value = read_value(record)
    assert isinstance(value, Missing)
    assert value.reason == "PLACEHOLDER reason for the missing value"
    # It is never read as zero, nor as any other number.
    assert not isinstance(value, (int, float))
    assert value != 0
    with pytest.raises(TypeError):
        float(value)
    with pytest.raises(TypeError):
        value + 1.0
    with pytest.raises(TypeError):
        value * 2.0


def test_a3_missing_range_with_reason_is_accepted_and_stays_missing():
    record = placeholder_record(
        range=None, range_missing_reason="PLACEHOLDER reason for the missing range"
    )
    assert check_record(record) == []
    assert read_value(record) == 2.0
    range_ = read_range(record)
    assert isinstance(range_, Missing)
    assert range_.reason == "PLACEHOLDER reason for the missing range"


def test_a4_a_value_of_zero_is_a_value_and_not_a_missing_mark():
    record = placeholder_record(
        value=0, range={"low": -1.0, "high": 1.0, "basis": "PLACEHOLDER basis"}
    )
    assert check_record(record) == []
    value = read_value(record)
    assert value == 0.0
    assert not isinstance(value, Missing)


def test_a5_missing_value_may_have_no_citation():
    assert check_record(missing_value_record(citation=None)) == []


def test_a6_same_identifier_with_another_scope_is_another_record():
    records = {
        "one.json": placeholder_record(scope={"crop": "PLACEHOLDER_crop"}),
        "two.json": placeholder_record(scope={"crop": "PLACEHOLDER_other_crop"}),
        "three.json": placeholder_record(scope={}),
    }
    assert find_duplicates(records) == []


def test_a7_optional_fields_are_accepted():
    record = placeholder_record(note="PLACEHOLDER note")
    record["citation"]["url"] = "PLACEHOLDER_url"
    assert check_record(record) == []


def test_a8_example_files_are_well_formed_placeholders():
    records, file_problems = load_folder(EXAMPLES)
    assert file_problems == []
    assert len(records) >= 2
    for name, record in records.items():
        assert check_record(record) == [], name
        assert is_placeholder(record), name
    assert find_duplicates(records) == []
    # An example can never pass as a parameter.
    assert len(find_placeholders(records)) == len(records)
    assert check_catalogue(records) != []


def test_a9_the_catalogue_in_this_repository_passes():
    """Checks every record under params/records/. Today there is none."""
    assert check_folder(RECORDS) == []


# --- R1: citation -----------------------------------------------------------


@pytest.mark.parametrize(
    "record",
    [
        without(placeholder_record(), "citation"),
        placeholder_record(citation=None),
        placeholder_record(citation={}),
        placeholder_record(citation="PLACEHOLDER reference as plain text"),
        without(placeholder_record(), "citation", "reference"),
        without(placeholder_record(), "citation", "locator"),
        placeholder_record(citation={"reference": "  ", "locator": "PLACEHOLDER locator"}),
        without(missing_value_record(), "citation"),
    ],
    ids=[
        "field absent",
        "null with a value",
        "empty object",
        "plain text",
        "no reference",
        "no locator",
        "blank reference",
        "field absent on a missing value",
    ],
)
def test_r1_record_without_citation_is_rejected(record):
    assert_rejected(record, "citation")


@pytest.mark.parametrize("marker", ["CITATION NEEDED", "citation  needed: PLACEHOLDER"])
def test_r1_citation_needed_marker_is_not_a_citation(marker):
    record = placeholder_record()
    record["citation"]["reference"] = marker
    assert_rejected(record, "CITATION NEEDED")


# --- R2: two persons --------------------------------------------------------


@pytest.mark.parametrize(
    "transcriber, checker",
    [
        ("PLACEHOLDER_person_one", "PLACEHOLDER_person_one"),
        ("PLACEHOLDER_person_one", "placeholder_person_one"),
        ("PLACEHOLDER person one", "  PLACEHOLDER   person one "),
    ],
    ids=["identical", "case differs", "whitespace differs"],
)
def test_r2_same_transcriber_and_checker_is_rejected(transcriber, checker):
    record = placeholder_record(transcribed_by=transcriber, checked_by=checker)
    assert_rejected(record, "same person")


@pytest.mark.parametrize("field", ["transcribed_by", "checked_by"])
@pytest.mark.parametrize("content", ["absent", None, "", "   ", 7])
def test_r2_each_person_must_be_named(field, content):
    record = placeholder_record()
    if content == "absent":
        del record[field]
    else:
        record[field] = content
    assert_rejected(record, field)


# --- R3: missing value ------------------------------------------------------


@pytest.mark.parametrize("reason", ["absent", None, "", "   ", 0])
def test_r3_missing_value_without_reason_is_rejected(reason):
    record = placeholder_record(value=None)
    if reason != "absent":
        record["value_missing_reason"] = reason
    assert_rejected(record, "missing without a reason")
    with pytest.raises(ValueError):
        read_value(record)


def test_r3_absent_value_field_is_rejected_and_not_read_as_missing():
    record = without(placeholder_record(), "value")
    assert_rejected(record, "'value' is absent")
    with pytest.raises(ValueError):
        read_value(record)


@pytest.mark.parametrize("value", [0, 2.0])
def test_r3_value_together_with_a_missing_reason_is_rejected(value):
    record = placeholder_record(
        value=value,
        value_missing_reason="PLACEHOLDER reason",
        range={"low": -5.0, "high": 5.0, "basis": "PLACEHOLDER basis"},
    )
    assert_rejected(record, "keep only one")


@pytest.mark.parametrize(
    "value",
    ["2.0", "", "NA", True, False, float("nan"), float("inf"), [2.0], {"v": 2.0}],
    ids=repr,
)
def test_r3_value_that_is_not_a_finite_number_is_rejected(value):
    assert_rejected(placeholder_record(value=value), "finite number")


# --- R4: identifier and scope ----------------------------------------------


def test_r4_same_identifier_and_scope_twice_is_rejected():
    records = {
        "first.json": placeholder_record(),
        "second.json": placeholder_record(value=3.0),
    }
    problems = find_duplicates(records)
    assert len(problems) == 1
    assert "first.json" in problems[0] and "second.json" in problems[0]
    assert any("same 'id' and 'scope'" in problem for problem in check_catalogue(records))


@pytest.mark.parametrize(
    "first, second",
    [
        (
            {"id": "PLACEHOLDER_parameter"},
            {"id": "placeholder_PARAMETER"},
        ),
        (
            {"scope": {"crop": "PLACEHOLDER_crop"}},
            {"scope": {"crop": " placeholder_CROP "}},
        ),
        (
            {"scope": {"crop": "PLACEHOLDER_crop", "soil": "PLACEHOLDER_soil"}},
            {"scope": {"soil": "PLACEHOLDER_soil", "crop": "PLACEHOLDER_crop"}},
        ),
        ({"scope": {}}, {"scope": {}}),
    ],
    ids=["id case", "scope case and whitespace", "scope key order", "empty scope"],
)
def test_r4_duplicates_are_found_whatever_the_spelling(first, second):
    records = {
        "first.json": placeholder_record(**first),
        "second.json": placeholder_record(**second),
    }
    assert len(find_duplicates(records)) == 1


@pytest.mark.parametrize(
    "identifier", ["absent", None, "", "9_PLACEHOLDER", "PLACEHOLDER parameter", "PLACEHOLDER-x", 3]
)
def test_r4_malformed_identifier_is_rejected(identifier):
    record = placeholder_record()
    if identifier == "absent":
        del record["id"]
    else:
        record["id"] = identifier
    assert_rejected(record, "'id'")


@pytest.mark.parametrize(
    "scope, expected",
    [
        ("absent", "'scope' is absent"),
        (None, "'scope' must be a JSON object"),
        ("PLACEHOLDER_crop", "'scope' must be a JSON object"),
        ({"PLACEHOLDER_key": "PLACEHOLDER_item"}, "unknown scope key"),
        ({"crop": ""}, "non-empty string"),
        ({"crop": None}, "non-empty string"),
        ({"crop": ["PLACEHOLDER_crop"]}, "non-empty string"),
    ],
)
def test_r4_malformed_scope_is_rejected(scope, expected):
    record = placeholder_record()
    if scope == "absent":
        del record["scope"]
    else:
        record["scope"] = scope
    assert_rejected(record, expected)


# --- R5: unit, range and other fields --------------------------------------


@pytest.mark.parametrize("unit", ["absent", None, "", "  ", 1])
def test_r5_record_without_unit_is_rejected(unit):
    record = placeholder_record()
    if unit == "absent":
        del record["unit"]
    else:
        record["unit"] = unit
    assert_rejected(record, "'unit'")


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"range": None}, "missing without a reason"),
        ({"range": None, "range_missing_reason": " "}, "missing without a reason"),
        ({"range_missing_reason": "PLACEHOLDER reason"}, "keep only one"),
        ({"range": [1.0, 3.0]}, "'range' must be a JSON object"),
        ({"range": {"low": 3.0, "high": 1.0, "basis": "PLACEHOLDER basis"}}, "greater than"),
        ({"range": {"low": 2.5, "high": 3.0, "basis": "PLACEHOLDER basis"}}, "outside its own range"),
        ({"range": {"low": 1.0, "high": 1.5, "basis": "PLACEHOLDER basis"}}, "outside its own range"),
        ({"range": {"low": 1.0, "high": 3.0}}, "'range.basis'"),
        ({"range": {"low": "1.0", "high": 3.0, "basis": "PLACEHOLDER basis"}}, "'range.low'"),
        ({"range": {"low": 1.0, "basis": "PLACEHOLDER basis"}}, "'range.high'"),
        (
            {"range": {"low": 1.0, "high": 3.0, "basis": "PLACEHOLDER basis", "mid": 2.0}},
            "unknown field 'range.mid'",
        ),
    ],
    ids=[
        "null without reason",
        "null with blank reason",
        "range and reason together",
        "not an object",
        "low above high",
        "value below low",
        "value above high",
        "no basis",
        "low is text",
        "no high",
        "unknown field",
    ],
)
def test_r5_malformed_range_is_rejected(changes, expected):
    assert_rejected(placeholder_record(**changes), expected)


def test_r5_absent_range_field_is_rejected():
    assert_rejected(without(placeholder_record(), "range"), "'range' is absent")


def test_r5_unknown_fields_are_rejected():
    assert_rejected(placeholder_record(citaton="PLACEHOLDER"), "unknown field 'citaton'")
    record = placeholder_record()
    record["citation"]["page"] = "PLACEHOLDER"
    assert_rejected(record, "unknown field 'citation.page'")


@pytest.mark.parametrize("record", [None, [], "PLACEHOLDER", 2.0])
def test_r5_record_that_is_not_an_object_is_rejected(record):
    assert_rejected(record, "not a JSON object")


def test_r5_empty_note_is_rejected():
    assert_rejected(placeholder_record(note=""), "'note'")


# --- R6: placeholders -------------------------------------------------------


def test_r6_placeholder_record_is_rejected_from_the_catalogue():
    record = placeholder_record()
    assert check_record(record) == []  # well-formed, and still not a parameter
    problems = check_catalogue({"record.json": record})
    assert len(problems) == 1
    assert "PLACEHOLDER" in problems[0]


@pytest.mark.parametrize(
    "item, expected",
    [
        ({"id": "x", "note": "a placeholder here"}, True),
        ({"citation": {"reference": "PLACEHOLDER reference"}}, True),
        ({"scope": {"PLACEHOLDER_key": "x"}}, True),
        ({"id": "x", "value": 2.0, "list": ["y", 3]}, False),
    ],
)
def test_r6_placeholder_word_is_found_anywhere(item, expected):
    assert is_placeholder(item) is expected


# --- R7: files --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        '{"value": 2.0, "value": 3.0}',
        '{"value": NaN}',
        '{"range": {"low": -Infinity, "high": Infinity}}',
    ],
    ids=["empty", "truncated", "repeated key", "NaN", "Infinity"],
)
def test_r7_unusable_file_text_is_rejected(text):
    with pytest.raises(ValueError):
        parse_record_text(text)


def test_r7_folder_check_reports_bad_files_and_bad_records(tmp_path):
    (tmp_path / "group").mkdir()
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    (tmp_path / "group" / "no_citation.json").write_text(
        '{"id": "x", "scope": {}, "value": 2.0, "unit": "u", "range": null,'
        ' "range_missing_reason": "r", "transcribed_by": "a", "checked_by": "b"}',
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("not a record", encoding="utf-8")

    problems = check_folder(tmp_path)
    assert len(problems) == 3
    assert any(p.startswith("broken.json: not a readable record file") for p in problems)
    assert any(p.startswith("list.json: the record is not a JSON object") for p in problems)
    assert any(
        p.startswith("group/no_citation.json:") and "'citation' is absent" in p
        for p in problems
    )


def test_r7_folder_that_does_not_exist_is_a_problem(tmp_path):
    problems = check_folder(tmp_path / "nowhere")
    assert len(problems) == 1
    assert "does not exist" in problems[0]
