"""Acceptance test of the parameter catalogue layout.

Run with ``python -m pytest params/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7) and are listed with the
same codes in params/README.md under "PROPOSED cases". Every record built
here is a placeholder: its numbers mean nothing.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from params import catalogue
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
EXAMPLES = HERE / "examples"

WORD = "PLACEHOLDER"


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


def nothing_recorded(**changes):
    """A placeholder record with no value and no range, each with its reason."""
    fields = {
        "range": None,
        "range_missing_reason": "PLACEHOLDER reason for the missing range",
    }
    fields.update(changes)
    return missing_value_record(**fields)


def unmarked(item):
    """A copy with the marker word replaced, in memory only.

    The reading functions refuse a placeholder (case F5b), so the accepting
    path of a reader can only be reached by a record without the word. No
    fixture is written without it: this copy exists only while a test runs,
    and every text in it says UNMARKED_TEST_ONLY.
    """
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {unmarked(key): unmarked(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmarked(value) for value in item]
    return item


def assert_rejected(record, *expected_words):
    problems = check_record(record)
    assert problems, "the record was accepted"
    text = " | ".join(problems)
    for word in expected_words:
        assert word in text, f"expected '{word}' in: {text}"


def write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


# --- A: accepted ------------------------------------------------------------


def test_a1_well_formed_record_is_accepted():
    record = placeholder_record()
    assert check_record(record) == []
    assert read_value(unmarked(record)) == 2.0
    assert read_range(unmarked(record)) == (1.0, 3.0)


def test_a2_missing_value_with_reason_is_accepted_and_stays_missing():
    record = missing_value_record()
    assert check_record(record) == []

    value = read_value(unmarked(record))
    assert isinstance(value, Missing)
    assert value.reason == unmarked("PLACEHOLDER reason for the missing value")
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
    assert read_value(unmarked(record)) == 2.0
    range_ = read_range(unmarked(record))
    assert isinstance(range_, Missing)
    assert range_.reason == unmarked("PLACEHOLDER reason for the missing range")


def test_a4_a_value_of_zero_is_a_value_and_not_a_missing_mark():
    record = placeholder_record(
        value=0, range={"low": -1.0, "high": 1.0, "basis": "PLACEHOLDER basis"}
    )
    assert check_record(record) == []
    value = read_value(unmarked(record))
    assert value == 0.0
    assert not isinstance(value, Missing)


def test_a5_record_with_no_value_and_no_range_may_have_no_citation():
    assert check_record(nothing_recorded(citation=None)) == []


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
    """Checks the whole params/ folder: the records of records/ and, apart
    from them, the records of withdrawn/."""
    assert catalogue.check_layout(HERE) == []


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
        read_value(unmarked(record))


def test_r3_absent_value_field_is_rejected_and_not_read_as_missing():
    record = without(placeholder_record(), "value")
    assert_rejected(record, "'value' is absent")
    with pytest.raises(ValueError):
        read_value(unmarked(record))


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
            placeholder_record(),
            placeholder_record(id="PLACEHOLDER_parameter".swapcase()),
        ),
        (
            placeholder_record(),
            placeholder_record(scope={"crop": " PLACEHOLDER_crop ".swapcase()}),
        ),
        (
            placeholder_record(scope={"crop": "PLACEHOLDER_crop", "soil": "PLACEHOLDER_soil"}),
            placeholder_record(scope={"soil": "PLACEHOLDER_soil", "crop": "PLACEHOLDER_crop"}),
        ),
        (placeholder_record(scope={}), placeholder_record(scope={})),
    ],
    ids=["id case", "scope case and whitespace", "scope key order", "empty scope"],
)
def test_r4_duplicates_are_found_whatever_the_spelling(first, second):
    records = {"first.json": first, "second.json": second}
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
        ({"crop": "", "soil": "PLACEHOLDER_soil"}, "non-empty string"),
        ({"crop": None, "soil": "PLACEHOLDER_soil"}, "non-empty string"),
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
    "record, expected",
    [
        (placeholder_record(range=None), "missing without a reason"),
        (placeholder_record(range=None, range_missing_reason=" "), "missing without a reason"),
        (placeholder_record(range_missing_reason="PLACEHOLDER reason"), "keep only one"),
        (placeholder_record(range=[1.0, 3.0]), "'range' must be a JSON object"),
        (
            placeholder_record(range={"low": 3.0, "high": 1.0, "basis": "PLACEHOLDER basis"}),
            "greater than",
        ),
        (
            placeholder_record(range={"low": 2.5, "high": 3.0, "basis": "PLACEHOLDER basis"}),
            "outside its own range",
        ),
        (
            placeholder_record(range={"low": 1.0, "high": 1.5, "basis": "PLACEHOLDER basis"}),
            "outside its own range",
        ),
        (without(placeholder_record(), "range", "basis"), "'range.basis'"),
        (
            placeholder_record(range={"low": "1.0", "high": 3.0, "basis": "PLACEHOLDER basis"}),
            "'range.low'",
        ),
        (without(placeholder_record(), "range", "high"), "'range.high'"),
        (
            placeholder_record(
                range={"low": 1.0, "high": 3.0, "basis": "PLACEHOLDER basis", "mid": 2.0}
            ),
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
def test_r5_malformed_range_is_rejected(record, expected):
    assert_rejected(record, expected)


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
        ("a placeholder here", True),
        ({"key": ["text", {"inner": "PLACEHOLDER text"}]}, True),
        ({"PLACEHOLDER_key": "text"}, True),
        ({"key": ["text", 3, None]}, False),
        ("text", False),
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
        '{"id": "PLACEHOLDER_parameter", "value": 2.0, "value": 3.0}',
        '{"id": "PLACEHOLDER_parameter", "value": NaN}',
        '{"id": "PLACEHOLDER_parameter", "range": {"low": -Infinity, "high": Infinity}}',
    ],
    ids=["empty", "truncated", "repeated key", "NaN", "Infinity"],
)
def test_r7_unusable_file_text_is_rejected(text):
    with pytest.raises(ValueError):
        parse_record_text(text)


def test_r7_folder_check_reports_bad_files_and_bad_records(tmp_path):
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    write_record(
        tmp_path / "group" / "no_citation.json", without(placeholder_record(), "citation")
    )

    problems = check_folder(tmp_path)
    assert len(problems) == 4
    assert any(p.startswith("broken.json: not a readable record file") for p in problems)
    assert any(p.startswith("list.json: the record is not a JSON object") for p in problems)
    assert any(
        p.startswith("group/no_citation.json:") and "'citation' is absent" in p
        for p in problems
    )
    assert any(p.startswith("group/no_citation.json:") and WORD in p for p in problems)


def test_r7_folder_that_does_not_exist_is_a_problem(tmp_path):
    problems = check_folder(tmp_path / "nowhere")
    assert len(problems) == 1
    assert "does not exist" in problems[0]


# --- F: fixes of issue 21 ---------------------------------------------------

DEPTH = 100_000


def nested(depth, bottom):
    item = bottom
    for _ in range(depth):
        item = [item]
    return item


def test_f1a_deeply_nested_file_is_reported_and_the_rest_still_loads(tmp_path):
    (tmp_path / "deep.json").write_text("[" * DEPTH + "]" * DEPTH, encoding="utf-8")
    write_record(tmp_path / "good.json", placeholder_record())

    records, problems = load_folder(tmp_path)
    assert list(records) == ["good.json"]
    assert len(problems) == 1
    assert problems[0].startswith("deep.json: not a readable record file")
    with pytest.raises(ValueError):
        parse_record_text("[" * DEPTH + "]" * DEPTH)


def test_f1a_placeholder_check_survives_deep_and_circular_items():
    assert is_placeholder(nested(DEPTH, "PLACEHOLDER text")) is True
    assert is_placeholder(nested(DEPTH, "text")) is False
    circular = {"key": "text"}
    circular["again"] = circular
    assert is_placeholder(circular) is False

    record = placeholder_record()
    record["note"] = nested(DEPTH, "text")
    problems = check_catalogue({"deep.json": record})
    assert any(p.startswith("deep.json: 'note'") for p in problems)
    assert len(find_placeholders({"deep.json": record})) == 1


def test_f1b_folder_named_like_a_record_is_reported_and_the_rest_still_loads(tmp_path):
    (tmp_path / "folder.json").mkdir()
    write_record(tmp_path / "folder.json" / "inside.json", placeholder_record())
    write_record(tmp_path / "good.json", placeholder_record(scope={}))

    records, problems = load_folder(tmp_path)
    assert sorted(records) == ["folder.json/inside.json", "good.json"]
    assert len(problems) == 1
    assert problems[0].startswith("folder.json: a folder")


@pytest.mark.parametrize(
    "record",
    [
        placeholder_record(value=10**400),
        placeholder_record(
            range={"low": -(10**400), "high": 3.0, "basis": "PLACEHOLDER basis"}
        ),
        placeholder_record(range={"low": 1.0, "high": 10**400, "basis": "PLACEHOLDER basis"}),
    ],
    ids=["value", "range.low", "range.high"],
)
def test_f1c_integer_too_large_for_a_float_is_reported(record):
    assert_rejected(record, "read back unchanged")
    assert any("read back unchanged" in p for p in check_catalogue({"big.json": record}))
    with pytest.raises(ValueError):
        read_value(unmarked(record))
    with pytest.raises(ValueError):
        read_range(unmarked(record))


@pytest.mark.parametrize(
    "record, field",
    [
        (
            placeholder_record(
                value=2**53 + 1, range=None, range_missing_reason="PLACEHOLDER reason"
            ),
            "'value'",
        ),
        (
            placeholder_record(
                range={"low": -(2**53) - 1, "high": 3.0, "basis": "PLACEHOLDER basis"}
            ),
            "'range.low'",
        ),
        (
            placeholder_record(
                range={"low": 1.0, "high": 2**53 + 1, "basis": "PLACEHOLDER basis"}
            ),
            "'range.high'",
        ),
    ],
    ids=["value", "range.low", "range.high"],
)
def test_f2_number_that_cannot_be_read_back_unchanged_is_reported(record, field):
    problems = check_record(record)
    assert problems == [f"{field} cannot be read back unchanged as a number"]


def test_f2_integer_that_reads_back_unchanged_is_accepted():
    record = placeholder_record(value=2**53)
    record["range"]["high"] = 2**53
    assert check_record(record) == []
    assert read_value(unmarked(record)) == 2**53


@pytest.mark.parametrize(
    "written, nearest",
    [
        ("2.00000000000000000001", 2.0),
        ("0.33333333333333333", 0.3333333333333333),
        ("9007199254740993.0", 9007199254740992.0),
    ],
)
def test_f2b_decimal_with_many_digits_is_read_as_the_nearest_float(written, nearest):
    text = '{"id": "PLACEHOLDER_parameter", "value": %s}' % written
    assert parse_record_text(text)["value"] == nearest


def test_f2b_record_file_with_a_long_decimal_is_accepted_and_read(tmp_path):
    written = "2.00000000000000000001"
    text = json.dumps(placeholder_record(value="@")).replace('"@"', written)
    assert written in text
    (tmp_path / "long.json").write_text(text, encoding="utf-8")

    records, problems = load_folder(tmp_path)
    assert problems == []
    assert check_record(records["long.json"]) == []
    assert read_value(unmarked(records["long.json"])) == 2.0


@pytest.mark.parametrize("number", ["2.0", "2.50", "0.1", "-0.0", "1e-5", "1E5", "2"])
def test_f2_ordinary_number_text_is_read(number):
    text = '{"id": "PLACEHOLDER_parameter", "value": %s}' % number
    assert parse_record_text(text)["value"] == float(number)


@pytest.mark.parametrize(
    "path",
    ["stray.json", "other/stray.json", "other/deeper/stray.JSON"],
    ids=["directly in params", "sibling folder", "nested, upper-case extension"],
)
def test_f3a_record_file_outside_records_and_examples_is_reported(tmp_path, path):
    (tmp_path / "records").mkdir()
    write_record(tmp_path / "examples" / "example.json", placeholder_record())
    assert catalogue.check_layout(tmp_path) == []

    write_record(tmp_path / path, placeholder_record())
    problems = catalogue.check_layout(tmp_path)
    assert len(problems) == 1
    assert problems[0].startswith(f"{path}: a record file outside")


def test_f3b_file_in_records_that_is_not_a_record_is_reported(tmp_path):
    (tmp_path / "README.md").write_text("PLACEHOLDER", encoding="utf-8")
    assert load_folder(tmp_path) == ({}, [])

    for path in ["notes.md", "table.csv", "UPPER.JSON", "group/README.md", "no_extension"]:
        (tmp_path / path).parent.mkdir(exist_ok=True)
        (tmp_path / path).write_text("PLACEHOLDER", encoding="utf-8")

    records, problems = load_folder(tmp_path)
    assert records == {}
    assert len(problems) == 5
    for path in ["notes.md", "table.csv", "UPPER.JSON", "group/README.md", "no_extension"]:
        assert f"{path}: not a .json record file" in problems
    assert check_folder(tmp_path) == problems


def test_f3c_duplicate_check_reports_a_record_it_cannot_compare():
    records = {
        "bad_id.json": placeholder_record(id=3),
        "bad_scope.json": placeholder_record(scope="PLACEHOLDER_crop"),
        "list.json": [],
        "ok.json": placeholder_record(),
    }
    problems = find_duplicates(records)
    assert len(problems) == 3
    for name in ["bad_id.json", "bad_scope.json", "list.json"]:
        assert any(p.startswith(f"{name}: cannot be compared") for p in problems)
    # The catalogue check says why, once per record.
    catalogue_problems = check_catalogue(records)
    for name in ["bad_id.json", "bad_scope.json", "list.json"]:
        assert any(p.startswith(f"{name}: ") for p in catalogue_problems)
        assert not any("cannot be compared" in p for p in catalogue_problems)


def test_f4_numeric_range_needs_a_citation():
    record = missing_value_record(citation=None)
    assert check_record(record) == [
        "a range needs a citation: 'citation' may be null only when "
        "'value' and 'range' are both null"
    ]
    with pytest.raises(ValueError):
        read_range(unmarked(record))
    assert check_record(missing_value_record()) == []  # same range, with a citation


def test_f4_malformed_range_without_citation_reports_only_the_real_problem():
    record = missing_value_record(citation=None, range=[1.0, 3.0])
    assert check_record(record) == ["'range' must be a JSON object, or null with a reason"]


@pytest.mark.parametrize(
    "record",
    [
        placeholder_record(value_missing_reason=None),
        placeholder_record(range_missing_reason=None),
        placeholder_record(value=0, value_missing_reason=None),
    ],
    ids=["value", "range", "value of zero"],
)
def test_f5a_reason_field_next_to_what_it_explains_is_rejected_even_as_null(record):
    record["range"] = {"low": -5.0, "high": 5.0, "basis": "PLACEHOLDER basis"}
    assert_rejected(record, "keep only one")


def test_f5b_reading_functions_refuse_a_placeholder():
    for record in [placeholder_record(), missing_value_record(), nothing_recorded()]:
        assert check_record(record) == []
        with pytest.raises(ValueError, match=WORD):
            read_value(record)
        with pytest.raises(ValueError, match=WORD):
            read_range(record)
    # One mention of the word anywhere is enough.
    record = unmarked(placeholder_record())
    assert read_value(record) == 2.0
    record["note"] = "a placeholder note"
    with pytest.raises(ValueError, match=WORD):
        read_value(record)


def test_f5b_no_example_file_can_be_read_as_a_parameter():
    records, _ = load_folder(EXAMPLES)
    assert records
    for name, record in records.items():
        with pytest.raises(ValueError, match=WORD):
            read_value(record)
        with pytest.raises(ValueError, match=WORD):
            read_range(record)


def test_f5c_acceptance_check_reads_every_file_under_records(tmp_path):
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "README.md").write_text("PLACEHOLDER", encoding="utf-8")
    assert catalogue.check_layout(tmp_path) == []

    (tmp_path / "records" / "values.txt").write_text("PLACEHOLDER", encoding="utf-8")
    assert catalogue.check_layout(tmp_path) == ["values.txt: not a .json record file"]


def test_f5c_params_folder_without_records_is_a_problem(tmp_path):
    problems = catalogue.check_layout(tmp_path)
    assert len(problems) == 1
    assert "does not exist" in problems[0]


# --- W: withdrawn records (PROPOSED) ----------------------------------------


def test_w1_withdrawn_record_is_checked_and_is_not_in_the_catalogue(tmp_path):
    (tmp_path / "records").mkdir()
    assert catalogue.check_layout(tmp_path) == []  # withdrawn/ may be absent

    write_record(tmp_path / "withdrawn" / "group" / "kept.json", placeholder_record())
    (tmp_path / "withdrawn" / "README.md").write_text("PLACEHOLDER", encoding="utf-8")
    # Not part of the catalogue: the folder a service loads does not hold it.
    assert load_folder(tmp_path / "records") == ({}, [])
    # Not a stray file, and still checked as a record: the one problem is the
    # one any record with the word has, named from params/.
    assert catalogue.check_layout(tmp_path) == [
        f"withdrawn/group/kept.json: contains the word {WORD}, so it is not a parameter"
    ]


def test_w2_withdrawn_folder_is_checked_like_a_catalogue_of_its_own(tmp_path):
    (tmp_path / "records").mkdir()
    withdrawn = tmp_path / "withdrawn"
    withdrawn.mkdir()
    (withdrawn / "broken.json").write_text("{", encoding="utf-8")
    (withdrawn / "notes.txt").write_text("PLACEHOLDER", encoding="utf-8")
    (withdrawn / "group").mkdir()
    (withdrawn / "group" / "README.md").write_text("PLACEHOLDER", encoding="utf-8")
    write_record(
        withdrawn / "group" / "no_citation.json", without(placeholder_record(), "citation")
    )
    write_record(withdrawn / "first.json", placeholder_record(scope={}))
    write_record(withdrawn / "second.json", placeholder_record(scope={}, value=3.0))

    problems = catalogue.check_layout(tmp_path)
    assert problems and all("withdrawn/" in p for p in problems)
    assert not any("a record file outside" in p for p in problems)
    assert any(
        p.startswith("withdrawn/broken.json: not a readable record file") for p in problems
    )
    assert "withdrawn/notes.txt: not a .json record file" in problems
    assert "withdrawn/group/README.md: not a .json record file" in problems
    assert any(
        p.startswith("withdrawn/group/no_citation.json:") and "'citation' is absent" in p
        for p in problems
    )
    assert "same 'id' and 'scope' in: withdrawn/first.json, withdrawn/second.json" in problems


def test_w2_withdrawn_and_loaded_records_are_two_sets(tmp_path):
    """The same identifier and scope in records/ and in withdrawn/ is not a
    duplicate: the withdrawn record is not in the catalogue."""
    write_record(tmp_path / "records" / "one.json", placeholder_record())
    write_record(tmp_path / "withdrawn" / "one.json", placeholder_record(value=3.0))

    assert list(load_folder(tmp_path / "records")[0]) == ["one.json"]
    problems = catalogue.check_layout(tmp_path)
    assert len(problems) == 2  # the word, once per folder
    assert not any("same 'id' and 'scope'" in p for p in problems)


def test_w3_withdrawn_records_of_this_repository_are_checked_and_not_loaded():
    loaded, problems = load_folder(HERE / catalogue.RECORDS_FOLDER)
    assert problems == [] and check_catalogue(loaded) == []
    withdrawn, problems = load_folder(HERE / catalogue.WITHDRAWN_FOLDER)
    assert problems == [] and check_catalogue(withdrawn) == []
    assert withdrawn
    loaded_identities = {catalogue.identity(record) for record in loaded.values()}
    for name, record in withdrawn.items():
        assert catalogue.identity(record) not in loaded_identities, name


PUBLIC_FUNCTIONS = [
    "check_record",
    "read_value",
    "read_range",
    "is_placeholder",
    "identity",
    "find_duplicates",
    "find_placeholders",
    "check_catalogue",
    "parse_record_text",
    "load_folder",
    "check_folder",
    "check_layout",
]


def unchecked_inputs():
    circular = placeholder_record()
    circular["note"] = circular
    return [
        None,
        3,
        2.5,
        float("nan"),
        10**400,
        "PLACEHOLDER text",
        "PLACEHOLDER\0text",
        "",
        b"PLACEHOLDER bytes",
        [],
        [None, 3],
        (),
        set(),
        object(),
        {},
        {3: 4},
        {None: None, ("PLACEHOLDER", 2): [3]},
        {"one.json": placeholder_record(), 3: placeholder_record(), None: []},
        placeholder_record(),
        placeholder_record(id=3),
        placeholder_record(id=["PLACEHOLDER"]),
        placeholder_record(scope=[]),
        placeholder_record(scope={3: "PLACEHOLDER", "crop": 4}),
        placeholder_record(value=10**400),
        placeholder_record(value=[]),
        placeholder_record(range=3),
        placeholder_record(range={"low": [], "high": {"PLACEHOLDER": 3}, "basis": 3}),
        placeholder_record(citation=[]),
        placeholder_record(citation={3: 4}),
        placeholder_record(transcribed_by={}, checked_by=[]),
        unmarked(placeholder_record(value=10**400)),
        unmarked(without(placeholder_record(), "range")),
        circular,
        nested(DEPTH, "PLACEHOLDER text"),
    ]


def test_f6_public_function_list_is_complete():
    public = {
        name
        for name, item in vars(catalogue).items()
        if callable(item)
        and not name.startswith("_")
        and getattr(item, "__module__", None) == catalogue.__name__
        and not isinstance(item, type)
    }
    assert public == set(PUBLIC_FUNCTIONS)


@pytest.mark.parametrize("name", PUBLIC_FUNCTIONS)
def test_f6_public_functions_report_or_raise_value_error_only(name):
    function = getattr(catalogue, name)
    for position, item in enumerate(unchecked_inputs()):
        try:
            function(item)
        except ValueError:
            pass  # the one documented exception type
        except Exception as error:  # any other type is the defect
            pytest.fail(f"{name}, input {position}: raised {type(error).__name__}")


# F7: every fixture that looks like a record carries the word.

FIELD_NAMES = (
    catalogue.REQUIRED_FIELDS
    + catalogue.OPTIONAL_FIELDS
    + catalogue.RANGE_FIELDS
    + catalogue.CITATION_REQUIRED_FIELDS
    + catalogue.CITATION_OPTIONAL_FIELDS
    + catalogue.SCOPE_KEYS
)
FIELD_IN_TEXT = re.compile('"(?:%s)"' % "|".join(FIELD_NAMES))
RECORD_BUILDERS = ("placeholder_record", "missing_value_record", "nothing_recorded")


def fixtures_without_the_word(source):
    """Lines of ``source`` that hold something like a record without the word.

    Something looks like a record when it is an object literal with a key
    that is a field name of the format, a text that holds such a key in
    quotes, or a call that passes a field name to anything other than the
    builders of placeholder records.
    """
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
            looks_like_a_record = any(key in FIELD_NAMES for key in keys)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            looks_like_a_record = bool(FIELD_IN_TEXT.search(node.value))
        elif isinstance(node, ast.Call):
            called = getattr(node.func, "id", getattr(node.func, "attr", ""))
            looks_like_a_record = called not in RECORD_BUILDERS and any(
                keyword.arg in FIELD_NAMES for keyword in node.keywords
            )
            if looks_like_a_record:
                lines.append(node.lineno)
            continue
        else:
            continue
        if looks_like_a_record and WORD not in ast.get_source_segment(source, node):
            lines.append(node.lineno)
    return sorted(set(lines))


def test_f7_every_fixture_that_looks_like_a_record_carries_the_word():
    source = Path(__file__).read_text(encoding="utf-8")
    assert fixtures_without_the_word(source) == []
    # The detector is not blind: without the word, the same file is full of them.
    assert len(fixtures_without_the_word(source.replace(WORD, "A_REAL_NAME"))) > 20
    for path in sorted(EXAMPLES.rglob("*.json")):
        assert WORD in path.read_text(encoding="utf-8"), path.name
