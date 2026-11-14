"""Acceptance test of the validation layout. Run with: python -m pytest validation/

Every case here is PROPOSED by a builder session and is listed in
validation/README.md under "PROPOSED cases" for a person to approve.

Every record built here is a placeholder: its numbers, units, persons and
citations are not real and say so. No real expected value, tolerance or
citation appears in this file.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from validation import records

HERE = Path(__file__).resolve().parent
EXAMPLES_ROOT = HERE / "examples"

PERSON_A = "PLACEHOLDER person A"
PERSON_B = "PLACEHOLDER person B"


# --- well-formed placeholder records -------------------------------------------


def expected_number() -> dict:
    return {
        "format_version": 1,
        "kind": "expected_value",
        "id": "PLACEHOLDER-expected-number",
        "test_code": "E999",
        "quantity": "PLACEHOLDER quantity",
        "value": {"number": 123456789.0, "unit": "PLACEHOLDER unit"},
        "tolerance": {"absolute": 987654321.0},
        "citation": {
            "reference": "PLACEHOLDER citation, not a real source",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": PERSON_A,
        "checked_by": PERSON_B,
    }


def expected_text() -> dict:
    record = expected_number()
    record["id"] = "PLACEHOLDER-expected-text"
    record["test_code"] = "D999"
    record["value"] = {"text": "PLACEHOLDER expected wording"}
    del record["tolerance"]
    return record


def expected_missing() -> dict:
    record = expected_number()
    record["id"] = "PLACEHOLDER-expected-missing"
    record["test_code"] = "H999"
    record["value"] = {"missing_reason": "PLACEHOLDER reason: not transcribed yet"}
    del record["tolerance"]
    return record


def protocol_run() -> dict:
    return {
        "format_version": 1,
        "kind": "protocol_run",
        "id": "PLACEHOLDER-run",
        "protocol": "PLACEHOLDER protocol version",
        "code_version": "PLACEHOLDER commit",
        "run_at": "1900-01-01T00:00:00Z",
        "run_by": PERSON_A,
        "test_codes": ["E999", "H999", "D999"],
    }


def result_passed() -> dict:
    return {
        "format_version": 1,
        "kind": "result",
        "id": "PLACEHOLDER-result-passed",
        "run_id": "PLACEHOLDER-run",
        "test_code": "E999",
        "expected": {"id": "PLACEHOLDER-expected-number"},
        "outcome": "passed",
        "observed": {"number": 123456789.0, "unit": "PLACEHOLDER unit"},
    }


def result_failed() -> dict:
    record = result_passed()
    record["id"] = "PLACEHOLDER-result-failed"
    record["test_code"] = "D999"
    record["expected"] = {"id": "PLACEHOLDER-expected-text"}
    record["outcome"] = "failed"
    record["observed"] = {"text": "PLACEHOLDER observed wording"}
    return record


def result_not_evaluated() -> dict:
    record = result_passed()
    record["id"] = "PLACEHOLDER-result-not-evaluated"
    record["test_code"] = "H999"
    record["expected"] = {"id": "PLACEHOLDER-expected-missing"}
    record["outcome"] = "not_evaluated"
    record["observed"] = {"missing_reason": "PLACEHOLDER reason: nothing was computed"}
    record["reason"] = "PLACEHOLDER reason: the expected value is missing"
    return record


def changed(build, change) -> dict:
    record = copy.deepcopy(build())
    change(record)
    return record


def set_field(key, value):
    return lambda record: record.__setitem__(key, value)


def drop_field(key):
    return lambda record: record.__delitem__(key)


def set_in(outer, key, value):
    return lambda record: record[outer].__setitem__(key, value)


def drop_in(outer, key):
    return lambda record: record[outer].__delitem__(key)


def problems_of(record) -> list[str]:
    return records.check_record(record, allow_placeholders=True)


# --- A: well-formed records are accepted ---------------------------------------

ACCEPTED = {
    "A01-expected-number-absolute-tolerance": expected_number,
    "A02-expected-number-relative-tolerance": lambda: changed(
        expected_number, set_field("tolerance", {"relative": 987654321.0})
    ),
    "A03-expected-number-tolerance-missing-with-reason": lambda: changed(
        expected_number, set_field("tolerance", {"missing_reason": "PLACEHOLDER reason: not fixed yet"})
    ),
    "A04-expected-text": expected_text,
    "A05-expected-value-missing-with-reason": expected_missing,
    "A06-expected-with-citation-url-and-notes": lambda: changed(
        expected_number,
        lambda record: (
            record["citation"].__setitem__("url", "PLACEHOLDER url"),
            record.__setitem__("notes", "PLACEHOLDER note"),
        ),
    ),
    "A07-protocol-run": protocol_run,
    "A08-result-passed": result_passed,
    "A09-result-failed-with-observed-value": result_failed,
    "A10-result-failed-with-observed-missing": lambda: changed(
        result_failed, set_field("observed", {"missing_reason": "PLACEHOLDER reason: the engine stopped"})
    ),
    "A11-result-not-evaluated-with-reason": result_not_evaluated,
    "A12-result-without-expected-reference-with-reason": lambda: changed(
        result_passed,
        set_field("expected", {"missing_reason": "PLACEHOLDER reason: an invariant has no external value"}),
    ),
}


@pytest.mark.parametrize("case", ACCEPTED, ids=list(ACCEPTED))
def test_well_formed_record_is_accepted(case):
    assert problems_of(ACCEPTED[case]()) == []


# --- R: malformed records are rejected -----------------------------------------
# Each case: (well-formed record, change that breaks it, words the problem must contain).

REJECTED = {
    # expected value: citation
    "R01-expected-without-citation": (expected_number, drop_field("citation"), "missing field 'citation'"),
    "R02-expected-citation-null": (expected_number, set_field("citation", None), "citation: must be an object"),
    "R03-expected-citation-reference-empty": (
        expected_number,
        set_in("citation", "reference", "   "),
        "citation.reference: must be a non-empty string",
    ),
    "R04-expected-citation-marked-citation-needed": (
        expected_number,
        set_in("citation", "reference", "CITATION NEEDED (PLACEHOLDER)"),
        "CITATION NEEDED",
    ),
    "R05-expected-citation-without-locator": (
        expected_number,
        drop_in("citation", "locator"),
        "citation: missing field 'locator'",
    ),
    # expected value: two persons
    "R06-expected-transcriber-is-checker": (
        expected_number,
        set_field("checked_by", PERSON_A),
        "checked_by: must be a different person",
    ),
    "R07-expected-transcriber-is-checker-other-spelling": (
        expected_number,
        set_field("checked_by", "  placeholder   PERSON a "),
        "checked_by: must be a different person",
    ),
    "R08-expected-without-checker": (expected_number, drop_field("checked_by"), "missing field 'checked_by'"),
    "R09-expected-without-transcriber": (
        expected_number,
        drop_field("transcribed_by"),
        "missing field 'transcribed_by'",
    ),
    "R10-expected-checker-empty": (
        expected_number,
        set_field("checked_by", ""),
        "checked_by: must be a non-empty string",
    ),
    # expected value: value, unit, tolerance
    "R11-expected-number-without-unit": (
        expected_number,
        set_field("value", {"number": 123456789.0}),
        "value: must have exactly the fields",
    ),
    "R12-expected-number-written-as-text": (
        expected_number,
        set_in("value", "number", "123456789.0"),
        "value.number: must be a finite number",
    ),
    "R13-expected-number-is-boolean": (
        expected_number,
        set_in("value", "number", True),
        "value.number: must be a finite number",
    ),
    "R14-expected-number-not-finite": (
        expected_number,
        set_in("value", "number", float("nan")),
        "value.number: must be a finite number",
    ),
    "R15-expected-value-null": (expected_number, set_field("value", None), "value: must be an object"),
    "R16-expected-value-number-and-text": (
        expected_number,
        set_in("value", "text", "PLACEHOLDER wording"),
        "value: must have exactly the fields",
    ),
    "R17-expected-value-missing-without-reason": (
        expected_missing,
        set_field("value", {"missing_reason": ""}),
        "a missing value must state its reason",
    ),
    "R18-expected-number-without-tolerance": (
        expected_number,
        drop_field("tolerance"),
        "tolerance: a numeric expected value must carry its tolerance",
    ),
    "R19-expected-tolerance-negative": (
        expected_number,
        set_field("tolerance", {"absolute": -987654321.0}),
        "tolerance.absolute: must be a finite number, zero or greater",
    ),
    "R20-expected-tolerance-absolute-and-relative": (
        expected_number,
        set_field("tolerance", {"absolute": 987654321.0, "relative": 987654321.0}),
        "tolerance: must have exactly the fields",
    ),
    "R21-expected-text-with-tolerance": (
        expected_text,
        set_field("tolerance", {"absolute": 987654321.0}),
        "tolerance: only a numeric expected value carries a tolerance",
    ),
    # every kind: common fields
    "R22-test-code-outside-families": (expected_number, set_field("test_code", "X1"), "test_code: must be a test code"),
    "R23-test-code-lower-case-family": (expected_number, set_field("test_code", "e3"), "test_code: must be a test code"),
    "R24-unknown-field": (
        expected_number,
        set_field("citaton", "PLACEHOLDER misspelt field"),
        "unknown field 'citaton'",
    ),
    "R25-unknown-kind": (expected_number, set_field("kind", "expected"), "kind: must be one of"),
    "R26-wrong-format-version": (expected_number, set_field("format_version", 2), "format_version: must be the integer 1"),
    "R27-id-with-path-separator": (expected_number, set_field("id", "../PLACEHOLDER"), "id: must start with"),
    "R28-missing-quantity": (expected_number, drop_field("quantity"), "missing field 'quantity'"),
    # protocol run
    "R29-run-time-without-zone": (protocol_run, set_field("run_at", "1900-01-01T00:00:00"), "run_at: must be a UTC time"),
    "R30-run-time-with-offset": (
        protocol_run,
        set_field("run_at", "1900-01-01T00:00:00-03:00"),
        "run_at: must be a UTC time",
    ),
    "R31-run-time-impossible-date": (
        protocol_run,
        set_field("run_at", "1900-02-30T00:00:00Z"),
        "run_at: must be a UTC time",
    ),
    "R32-run-without-test-codes": (protocol_run, set_field("test_codes", []), "test_codes: must be a non-empty list"),
    "R33-run-test-code-listed-twice": (
        protocol_run,
        set_field("test_codes", ["E999", "E999"]),
        "test_codes: a test code is listed more than once",
    ),
    "R34-run-bad-test-code": (protocol_run, set_field("test_codes", ["E999", "Z1"]), "test_codes[1]: must be a test code"),
    "R35-run-without-code-version": (protocol_run, drop_field("code_version"), "missing field 'code_version'"),
    # result
    "R36-result-outcome-word-not-allowed": (result_passed, set_field("outcome", "ok"), "outcome: must be one of"),
    "R37-result-outcome-other-case": (result_failed, set_field("outcome", "FAILED"), "outcome: must be one of"),
    "R38-result-without-outcome": (result_passed, drop_field("outcome"), "missing field 'outcome'"),
    "R39-result-passed-without-observed-value": (
        result_passed,
        set_field("observed", {"missing_reason": "PLACEHOLDER reason: nothing was computed"}),
        "a result without an observed value cannot be 'passed'",
    ),
    "R40-result-without-observed": (result_failed, drop_field("observed"), "missing field 'observed'"),
    "R41-result-not-evaluated-without-reason": (
        result_not_evaluated,
        drop_field("reason"),
        "reason: a result that was not evaluated must state why",
    ),
    "R42-result-passed-with-reason": (
        result_passed,
        set_field("reason", "PLACEHOLDER reason"),
        "reason: only a 'not_evaluated' result carries a reason",
    ),
    "R43-result-expected-neither-id-nor-reason": (
        result_passed,
        set_field("expected", {}),
        "expected: must have exactly the fields",
    ),
    "R44-result-without-run-id": (result_passed, drop_field("run_id"), "missing field 'run_id'"),
}


@pytest.mark.parametrize("case", REJECTED, ids=list(REJECTED))
def test_malformed_record_is_rejected(case):
    build, change, words = REJECTED[case]
    assert problems_of(build()) == [], "the starting record must be well-formed"
    problems = problems_of(changed(build, change))
    assert any(words in problem for problem in problems), problems


def test_R45_record_that_is_not_an_object_is_rejected():
    assert records.check_record([expected_number()], allow_placeholders=True) == ["record: must be a JSON object"]


def test_R46_placeholder_is_rejected_unless_explicitly_allowed():
    record = expected_number()
    assert records.check_record(record, allow_placeholders=True) == []
    problems = records.check_record(record)
    assert len(problems) == 1 and "PLACEHOLDER" in problems[0]


def test_R47_a_broken_record_reports_every_problem_at_once():
    record = expected_number()
    del record["citation"]
    record["checked_by"] = PERSON_A
    problems = problems_of(record)
    assert any("citation" in problem for problem in problems)
    assert any("checked_by" in problem for problem in problems)


# --- S: a store on disk --------------------------------------------------------


def write_text(path: Path, text: str) -> Path:
    """The only place where a test writes a file: its content must carry the word PLACEHOLDER."""
    if "PLACEHOLDER" not in text:
        raise AssertionError(f"fixture without the word PLACEHOLDER: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def write(root: Path, record, *, folder: str | None = None, name: str | None = None) -> Path:
    folder = folder or records.FOLDER_BY_KIND[record["kind"]]
    path = root / folder / (name or f"{record['id']}.json")
    return write_text(path, json.dumps(record, indent=2))


def write_full_store(root: Path) -> None:
    for build in (
        expected_number,
        expected_text,
        expected_missing,
        protocol_run,
        result_passed,
        result_failed,
        result_not_evaluated,
    ):
        write(root, build())


def load(root: Path) -> records.Store:
    return records.load_store(root, allow_placeholders=True)


def messages(store: records.Store, path: str) -> list[str]:
    return [message for problem_path, message in store.problems if problem_path == path]


def test_S01_failed_result_is_stored_and_reported_as_failed(tmp_path):
    write_full_store(tmp_path)
    store = load(tmp_path)
    assert store.problems == ()
    assert store.results["PLACEHOLDER-result-failed"]["outcome"] == "failed"
    summary = records.summarise(store)
    assert summary["failed"] == ["PLACEHOLDER-result-failed"]
    assert summary["not_evaluated"] == ["PLACEHOLDER-result-not-evaluated"]
    assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}
    assert summary["results_total"] == 3 == sum(summary["counts"].values())
    assert summary["no_result"] == []
    assert summary["rejected"] == []


def test_S02_store_of_only_failed_results_reports_them_all(tmp_path):
    write(tmp_path, expected_text())
    write(tmp_path, protocol_run())
    write(tmp_path, result_failed())
    write(tmp_path, changed(result_failed, set_field("id", "PLACEHOLDER-result-failed-again")))
    summary = records.summarise(load(tmp_path))
    assert summary["failed"] == ["PLACEHOLDER-result-failed", "PLACEHOLDER-result-failed-again"]
    assert summary["counts"] == {"passed": 0, "failed": 2, "not_evaluated": 0}


def test_S03_examples_folder_holds_an_accepted_record_of_each_kind():
    store = load(EXAMPLES_ROOT)
    assert store.problems == ()
    assert store.expected and store.runs and store.results
    assert {result["outcome"] for result in store.results.values()} == set(records.OUTCOMES)
    summary = records.summarise(store)
    assert summary["failed"] == ["PLACEHOLDER-result-failed"]
    assert summary["results_total"] == len(store.results)


def test_S04_every_example_is_a_placeholder_and_the_real_store_refuses_it():
    store = records.load_store(EXAMPLES_ROOT)  # placeholders not allowed
    assert not store.expected and not store.runs and not store.results
    files = sorted(path for path in EXAMPLES_ROOT.rglob("*.json"))
    assert files, "the examples folder must hold records"
    for path in files:
        assert "PLACEHOLDER" in path.name
        assert records.is_placeholder(json.loads(path.read_text(encoding="utf-8")))
    assert len(records.summarise(store)["rejected"]) == len(files)


def test_S05_real_store_has_no_malformed_record():
    store = records.load_store(records.STORE_ROOT)
    assert store.problems == ()


def test_S06_missing_folders_mean_an_empty_store(tmp_path):
    store = load(tmp_path)
    assert (store.expected, store.runs, store.results, store.problems) == ({}, {}, {}, ())
    assert records.summarise(store)["results_total"] == 0


def test_S07_file_that_is_not_json_is_listed_and_the_rest_still_loads(tmp_path):
    write_full_store(tmp_path)
    write_text(tmp_path / "expected" / "PLACEHOLDER-broken.json", '{ "PLACEHOLDER": not json')
    store = load(tmp_path)
    assert any("is not valid JSON" in m for m in messages(store, "expected/PLACEHOLDER-broken.json"))
    assert len(store.expected) == 3 and len(store.results) == 3


def test_S08_field_written_twice_is_rejected(tmp_path):
    text = json.dumps(expected_number())
    text = text[:-1] + ', "checked_by": "PLACEHOLDER person C"}'
    path = tmp_path / "expected" / "PLACEHOLDER-expected-number.json"
    path.parent.mkdir(parents=True)
    write_text(path, text)
    store = load(tmp_path)
    assert any("written twice" in m for m in messages(store, "expected/PLACEHOLDER-expected-number.json"))
    assert store.expected == {}


def test_S09_nan_written_in_a_file_is_rejected(tmp_path):
    text = json.dumps(expected_number()).replace("123456789.0", "NaN")
    path = tmp_path / "expected" / "PLACEHOLDER-expected-number.json"
    path.parent.mkdir(parents=True)
    write_text(path, text)
    store = load(tmp_path)
    assert any("NaN is not a number" in m for m in messages(store, "expected/PLACEHOLDER-expected-number.json"))


def test_S10_record_in_the_folder_of_another_kind_is_rejected(tmp_path):
    write(tmp_path, protocol_run(), folder="results")
    store = load(tmp_path)
    assert any("belongs in 'runs/'" in m for m in messages(store, "results/PLACEHOLDER-run.json"))
    assert store.runs == {} and store.results == {}


def test_S11_file_name_that_differs_from_the_id_is_rejected(tmp_path):
    write(tmp_path, expected_number(), name="PLACEHOLDER-other-name.json")
    store = load(tmp_path)
    assert any("must be named" in m for m in messages(store, "expected/PLACEHOLDER-other-name.json"))


def test_S12_file_that_is_not_a_json_file_is_listed(tmp_path):
    write_full_store(tmp_path)
    write_text(tmp_path / "results" / "PLACEHOLDER-notes.txt", "PLACEHOLDER")
    store = load(tmp_path)
    assert any("is not a record" in m for m in messages(store, "results/PLACEHOLDER-notes.txt"))


def test_S13_result_of_an_unknown_run_is_rejected_and_listed(tmp_path):
    write_full_store(tmp_path)
    (tmp_path / "runs" / "PLACEHOLDER-run.json").unlink()
    store = load(tmp_path)
    summary = records.summarise(store)
    assert store.results == {}
    assert "results/PLACEHOLDER-result-failed.json" in summary["rejected"]
    assert any("no accepted protocol run" in m for m in messages(store, "results/PLACEHOLDER-result-failed.json"))


def test_S14_result_of_an_unknown_expected_value_is_rejected(tmp_path):
    write_full_store(tmp_path)
    (tmp_path / "expected" / "PLACEHOLDER-expected-text.json").unlink()
    store = load(tmp_path)
    assert "PLACEHOLDER-result-failed" not in store.results
    assert any(
        "no accepted expected value" in m for m in messages(store, "results/PLACEHOLDER-result-failed.json")
    )
    assert len(store.results) == 2


def test_S15_result_for_a_test_the_run_does_not_list_is_rejected(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(protocol_run, set_field("test_codes", ["E999", "H999"])))
    store = load(tmp_path)
    assert any("is not listed in the test_codes" in m for m in messages(store, "results/PLACEHOLDER-result-failed.json"))


def test_S16_result_pointing_to_the_expected_value_of_another_test_is_rejected(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(result_passed, set_field("expected", {"id": "PLACEHOLDER-expected-text"})))
    store = load(tmp_path)
    assert any("belongs to test 'D999'" in m for m in messages(store, "results/PLACEHOLDER-result-passed.json"))


def test_S17_result_cannot_pass_or_fail_against_a_missing_expected_value(tmp_path):
    write_full_store(tmp_path)
    for outcome in ("passed", "failed"):
        record = result_not_evaluated()
        record["outcome"] = outcome
        record["observed"] = {"number": 123456789.0, "unit": "PLACEHOLDER unit"}
        del record["reason"]
        write(tmp_path, record)
        store = load(tmp_path)
        assert any(
            "can only be 'not_evaluated'" in m
            for m in messages(store, "results/PLACEHOLDER-result-not-evaluated.json")
        ), outcome


def test_S18_test_listed_by_a_run_without_a_result_is_reported(tmp_path):
    write_full_store(tmp_path)
    (tmp_path / "results" / "PLACEHOLDER-result-failed.json").unlink()
    summary = records.summarise(load(tmp_path))
    assert summary["no_result"] == [{"run_id": "PLACEHOLDER-run", "test_code": "D999"}]


def test_S19_malformed_failed_result_is_rejected_and_still_reported_as_failed(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(result_failed, drop_field("observed")))
    store = load(tmp_path)
    summary = records.summarise(store)
    assert "PLACEHOLDER-result-failed" not in store.results
    assert summary["failed"] == []
    assert summary["failed_malformed"] == ["results/PLACEHOLDER-result-failed.json"]
    assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}
    assert summary["results_total"] == 3
    assert summary["rejected"] == ["results/PLACEHOLDER-result-failed.json"]
    assert summary["no_result"] == [{"run_id": "PLACEHOLDER-run", "test_code": "D999"}]


def test_S20_file_holding_a_list_is_rejected(tmp_path):
    path = tmp_path / "runs" / "PLACEHOLDER-run.json"
    path.parent.mkdir(parents=True)
    write_text(path, json.dumps([protocol_run()]))
    store = load(tmp_path)
    assert messages(store, "runs/PLACEHOLDER-run.json") == ["record: must be a JSON object"]


def test_S21_failed_result_of_a_rejected_run_is_still_reported_as_failed(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(protocol_run, set_field("run_at", "1900-01-01 00:00")))
    store = load(tmp_path)
    summary = records.summarise(store)
    assert store.runs == {} and store.results == {}
    assert summary["failed"] == ["PLACEHOLDER-result-failed"]
    assert summary["counts"] == {"passed": 0, "failed": 1, "not_evaluated": 0}
    assert summary["results_total"] == 1
    assert summary["broken_references"] == [
        {"id": "PLACEHOLDER-result-failed", "outcome": "failed"},
        {"id": "PLACEHOLDER-result-not-evaluated", "outcome": "not_evaluated"},
        {"id": "PLACEHOLDER-result-passed", "outcome": "passed"},
    ]
    assert "runs/PLACEHOLDER-run.json" in summary["rejected"]
    assert "results/PLACEHOLDER-result-failed.json" in summary["rejected"]


def test_S22_failed_result_of_a_rejected_expected_value_is_still_reported_as_failed(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(expected_text, set_field("checked_by", PERSON_A)))
    store = load(tmp_path)
    summary = records.summarise(store)
    assert "PLACEHOLDER-expected-text" not in store.expected
    assert "PLACEHOLDER-result-failed" not in store.results
    assert summary["failed"] == ["PLACEHOLDER-result-failed"]
    assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}
    assert summary["results_total"] == 3
    assert summary["broken_references"] == [{"id": "PLACEHOLDER-result-failed", "outcome": "failed"}]
    assert summary["no_result"] == []
    assert "results/PLACEHOLDER-result-failed.json" in summary["rejected"]


def test_S23_passed_result_with_a_broken_reference_is_listed_but_not_counted_as_passed(tmp_path):
    write_full_store(tmp_path)
    (tmp_path / "expected" / "PLACEHOLDER-expected-number.json").unlink()
    summary = records.summarise(load(tmp_path))
    assert summary["counts"] == {"passed": 0, "failed": 1, "not_evaluated": 1}
    assert summary["broken_references"] == [{"id": "PLACEHOLDER-result-passed", "outcome": "passed"}]
    assert summary["no_result"] == [{"run_id": "PLACEHOLDER-run", "test_code": "E999"}]
    assert "results/PLACEHOLDER-result-passed.json" in summary["rejected"]


def test_S24_record_in_a_misnamed_folder_is_listed(tmp_path):
    write_full_store(tmp_path)
    (tmp_path / "results" / "PLACEHOLDER-result-failed.json").unlink()
    write(tmp_path, result_failed(), folder="result")
    store = load(tmp_path)
    assert any("is outside" in m for m in messages(store, "result/PLACEHOLDER-result-failed.json"))
    summary = records.summarise(store)
    assert "result/PLACEHOLDER-result-failed.json" in summary["rejected"]
    assert summary["no_result"] == [{"run_id": "PLACEHOLDER-run", "test_code": "D999"}]


def test_S25_file_whose_name_starts_with_a_dot_is_listed(tmp_path):
    write_full_store(tmp_path)
    folder = tmp_path / "results"
    (folder / "PLACEHOLDER-result-failed.json").rename(folder / ".PLACEHOLDER-result-failed.json")
    write_text(folder / ".PLACEHOLDER-hidden", "PLACEHOLDER")
    store = load(tmp_path)
    assert any("must be named" in m for m in messages(store, "results/.PLACEHOLDER-result-failed.json"))
    assert any("is not a record" in m for m in messages(store, "results/.PLACEHOLDER-hidden"))
    assert "PLACEHOLDER-result-failed" not in store.results


def test_S26_json_file_outside_the_three_folders_is_listed_and_examples_are_not_read(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, protocol_run(), folder=".", name="PLACEHOLDER-stray.json")
    write(tmp_path, result_failed(), folder="old/results", name="PLACEHOLDER-deeper.JSON")
    write(tmp_path, result_failed(), folder="examples/results")
    write_text(tmp_path / "PLACEHOLDER-readme.md", "PLACEHOLDER")
    store = load(tmp_path)
    assert sorted({path for path, _ in store.problems}) == [
        "PLACEHOLDER-stray.json",
        "old/results/PLACEHOLDER-deeper.JSON",
    ]
    assert all("is outside" in message for _, message in store.problems)
    assert len(store.results) == 3


@pytest.mark.parametrize("depth", [500, 5000, 100000])
def test_S27_deeply_nested_file_is_listed_and_the_rest_still_loads(tmp_path, depth):
    write_full_store(tmp_path)
    nested = "[" * depth + '"PLACEHOLDER"' + "]" * depth
    write_text(tmp_path / "results" / "PLACEHOLDER-deep-list.json", nested)
    text = json.dumps(changed(result_failed, set_field("id", "PLACEHOLDER-deep-field")))
    text = text.replace('"PLACEHOLDER observed wording"', nested)
    write_text(tmp_path / "results" / "PLACEHOLDER-deep-field.json", text)
    for allow_placeholders in (True, False):
        store = records.load_store(tmp_path, allow_placeholders=allow_placeholders)
        assert messages(store, "results/PLACEHOLDER-deep-list.json")
        assert messages(store, "results/PLACEHOLDER-deep-field.json")
    store = load(tmp_path)
    assert len(store.expected) == 3 and len(store.runs) == 1 and len(store.results) == 3
    assert len(records.summarise(store)["rejected"]) == 2


def test_S28_every_rejected_file_that_says_failed_is_counted_as_failed(tmp_path):
    write_full_store(tmp_path)
    folder = tmp_path / "results"
    # an outcome word that is not allowed, but that plainly means failed
    write(tmp_path, changed(result_failed, set_field("outcome", " FAILED ")), name="PLACEHOLDER-a.json")
    # a well-formed failed result under a file name that is not its id
    write(tmp_path, result_failed(), name="PLACEHOLDER-b.json")
    # a failed result in the folder of another kind
    write(tmp_path, result_failed(), folder="runs", name="PLACEHOLDER-c.json")
    # a failed result with a deeply nested list where a wording is expected
    text = json.dumps(result_failed()).replace('"PLACEHOLDER observed wording"', "[" * 400 + '"PLACEHOLDER"' + "]" * 400)
    write_text(folder / "PLACEHOLDER-d.json", text)
    # rejected files that do not say failed, or that cannot be read at all
    write(tmp_path, changed(result_passed, drop_field("observed")), name="PLACEHOLDER-e.json")
    write_text(folder / "PLACEHOLDER-f.json", '{"id": "PLACEHOLDER-f", "outcome": "failed"')

    said_failed = [
        "results/PLACEHOLDER-a.json",
        "results/PLACEHOLDER-b.json",
        "results/PLACEHOLDER-d.json",
        "runs/PLACEHOLDER-c.json",
    ]
    for allow_placeholders in (True, False):
        store = records.load_store(tmp_path, allow_placeholders=allow_placeholders)
        summary = records.summarise(store)
        assert set(said_failed) <= set(summary["failed_malformed"])
        assert "results/PLACEHOLDER-e.json" not in summary["failed_malformed"]
        assert "results/PLACEHOLDER-f.json" not in summary["failed_malformed"]
        assert summary["counts"]["failed"] == len(summary["failed"]) + len(summary["failed_malformed"])
        assert set(summary["failed_malformed"]) <= set(summary["rejected"])

    summary = records.summarise(load(tmp_path))
    assert summary["failed"] == ["PLACEHOLDER-result-failed"]
    assert summary["failed_malformed"] == said_failed
    assert summary["counts"] == {"passed": 1, "failed": 5, "not_evaluated": 1}
    assert {"results/PLACEHOLDER-e.json", "results/PLACEHOLDER-f.json"} <= set(summary["rejected"])


def test_R48_check_references_reports_an_unchecked_record_and_does_not_raise():
    expected = {"PLACEHOLDER-expected-text": expected_text()}
    runs = {"PLACEHOLDER-run": protocol_run()}
    unchecked_results = {
        "without-run-id": changed(result_failed, drop_field("run_id")),
        "without-expected": changed(result_failed, drop_field("expected")),
        "without-outcome": changed(result_failed, drop_field("outcome")),
        "run-id-not-text": changed(result_failed, set_field("run_id", ["PLACEHOLDER-run"])),
        "not-an-object": "PLACEHOLDER",
        "another-kind": protocol_run(),
    }
    found = records.check_references(expected, runs, unchecked_results)
    assert set(found) == set(unchecked_results)
    assert all(problems for problems in found.values())

    sound = {"PLACEHOLDER-result-failed": result_failed()}
    assert records.check_references(expected, runs, sound) == {}
    unchecked_run = {"PLACEHOLDER-run": changed(protocol_run, drop_field("test_codes"))}
    found = records.check_references(expected, unchecked_run, sound)
    assert any("no accepted protocol run" in problem for problem in found["PLACEHOLDER-result-failed"])
    unchecked_expected = {"PLACEHOLDER-expected-text": changed(expected_text, drop_field("value"))}
    found = records.check_references(unchecked_expected, runs, sound)
    assert any("no accepted expected value" in problem for problem in found["PLACEHOLDER-result-failed"])
    wrong_kind = {"PLACEHOLDER-expected-text": protocol_run()}
    found = records.check_references(wrong_kind, runs, sound)
    assert any("no accepted expected value" in problem for problem in found["PLACEHOLDER-result-failed"])


# --- files as editors and operating systems write them ---------------------------


def test_S29_file_saved_with_a_byte_order_mark_is_read(tmp_path):
    write_full_store(tmp_path)
    for path in sorted(tmp_path.rglob("*.json")):
        write_text(path, "\ufeff" + path.read_text(encoding="utf-8"))
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    store = load(tmp_path)
    assert store.problems == ()
    assert len(store.expected) == 3 and len(store.runs) == 1 and len(store.results) == 3


def test_S30_extension_of_a_record_file_is_read_without_regard_to_case(tmp_path):
    write_full_store(tmp_path)
    for folder, name, extension in (
        ("expected", "PLACEHOLDER-expected-text", ".Json"),
        ("runs", "PLACEHOLDER-run", ".JSON"),
        ("results", "PLACEHOLDER-result-failed", ".jSoN"),
    ):
        (tmp_path / folder / f"{name}.json").rename(tmp_path / folder / f"{name}{extension}")
    store = load(tmp_path)
    assert store.problems == ()
    assert len(store.expected) == 3 and len(store.runs) == 1 and len(store.results) == 3
    assert records.summarise(store)["failed"] == ["PLACEHOLDER-result-failed"]

    # Only the extension: the name before it is still the id, letter for letter.
    (tmp_path / "runs" / "PLACEHOLDER-run.JSON").unlink()
    write(tmp_path, protocol_run(), name="placeholder-run.JSON")
    store = load(tmp_path)
    assert any("must be named" in m for m in messages(store, "runs/placeholder-run.JSON"))


@pytest.mark.parametrize("twin_listed", ["first", "last"])
def test_S31_two_files_that_carry_the_same_id_are_both_rejected(tmp_path, monkeypatch, twin_listed):
    # Two names that differ only in the case of the extension cannot both exist
    # on every file system, so the second file is added to the listing instead.
    root = tmp_path / "store"
    write_full_store(root)
    twin = write(tmp_path / "other", result_failed(), name="PLACEHOLDER-result-failed.JSON")
    listing = records._entries

    def with_twin(directory):
        found = listing(directory)
        if directory == root / "results":
            found = [twin] + found if twin_listed == "first" else found + [twin]
        return found

    monkeypatch.setattr(records, "_entries", with_twin)
    store = load(root)
    assert "PLACEHOLDER-result-failed" not in store.results
    assert "PLACEHOLDER-result-failed" not in store.unresolved
    assert any(
        "is also the id of 'results/PLACEHOLDER-result-failed.JSON'" in m
        for m in messages(store, "results/PLACEHOLDER-result-failed.json")
    )
    assert any(
        "is also the id of 'results/PLACEHOLDER-result-failed.json'" in m
        for m in messages(store, "results/PLACEHOLDER-result-failed.JSON")
    )
    assert len(store.results) == 2
    summary = records.summarise(store)
    assert summary["failed"] == []
    assert summary["failed_malformed"] == [
        "results/PLACEHOLDER-result-failed.JSON",
        "results/PLACEHOLDER-result-failed.json",
    ]


def test_S32_directory_named_like_a_record_file_is_listed(tmp_path):
    write_full_store(tmp_path)
    folders = ("expected", "runs", "results")
    for folder in folders:
        write(tmp_path, result_failed(), folder=f"{folder}/PLACEHOLDER-directory.json", name="PLACEHOLDER-inside.json")
    store = load(tmp_path)
    for folder in folders:
        assert any("is not a record" in m for m in messages(store, f"{folder}/PLACEHOLDER-directory.json"))
    assert len(store.expected) == 3 and len(store.runs) == 1 and len(store.results) == 3
    assert len(records.summarise(store)["rejected"]) == 3


# --- numbers that a float cannot hold --------------------------------------------

TOO_LARGE_FOR_A_FLOAT = 10**400
NOT_EXACT_AS_A_FLOAT = 2**53 + 1


def in_each_number_slot(number):
    """A well-formed placeholder record with the given number in each slot that takes one."""
    yield "value.number", changed(expected_number, set_in("value", "number", number))
    yield "tolerance.absolute", changed(expected_number, set_field("tolerance", {"absolute": number}))
    yield "tolerance.relative", changed(expected_number, set_field("tolerance", {"relative": number}))
    yield "observed.number", changed(result_passed, set_in("observed", "number", number))


@pytest.mark.parametrize("number", [TOO_LARGE_FOR_A_FLOAT, -TOO_LARGE_FOR_A_FLOAT])
def test_R49_integer_too_large_for_a_float_is_reported_and_does_not_raise(number):
    for slot, record in in_each_number_slot(number):
        if slot.startswith("tolerance") and number < 0:
            continue
        problems = problems_of(record)
        assert len(problems) == 1 and problems[0].startswith(f"{slot}:"), (slot, problems)


def test_R50_integer_that_a_float_cannot_hold_exactly_is_reported():
    for slot, record in in_each_number_slot(NOT_EXACT_AS_A_FLOAT):
        problems = problems_of(record)
        assert len(problems) == 1, (slot, problems)
        assert problems[0].startswith(f"{slot}:") and "cannot hold exactly" in problems[0]
    for exact in (2**53, 10**22, 123456789, 1e300):
        for slot, record in in_each_number_slot(exact):
            assert problems_of(record) == [], (slot, exact)


def test_S33_number_that_would_change_when_read_from_a_file_is_reported(tmp_path):
    def stored(case: str, literal: str) -> tuple[records.Store, list[str]]:
        root = tmp_path / case
        write_full_store(root)
        text = json.dumps(expected_number()).replace("123456789.0", literal)
        write_text(root / "expected" / "PLACEHOLDER-expected-number.json", text)
        store = load(root)
        return store, messages(store, "expected/PLACEHOLDER-expected-number.json")

    changed_when_read = [
        "9007199254740993",  # an integer one above the last that a float holds exactly
        "12345678901234567890123",
        "100000000000000000000000",
        "1" + "0" * 400,  # too large for a float
        "1" * 5000,  # more digits than Python converts
    ]
    for index, literal in enumerate(changed_when_read):
        store, found = stored(f"changed-{index}", literal)
        assert "PLACEHOLDER-expected-number" not in store.expected, literal
        assert found and all(message.startswith("value.number:") for message in found), (literal, found)

    # A number that a float reads as infinity is rejected as not finite, as before.
    store, found = stored("infinite", "1e400")
    assert found and "must be a finite number" in found[0]

    integers_read_as_written = ["9007199254740992", "100000000000000000000", "123456789", "-4503599627370496"]
    for index, literal in enumerate(integers_read_as_written):
        store, found = stored(f"same-{index}", literal)
        assert found == [], (literal, found)
        number = store.expected["PLACEHOLDER-expected-number"]["value"]["number"]
        assert type(number) is int and number == int(literal), literal

    # The rule is about integers only: a number written with a decimal point or
    # an exponent is accepted as the float it denotes.
    not_integer_literals = ["0.1", "0.10000000000000001", "0.12345678901234567890", "12345678901234567890.0", "1e22", "1e23", "1.0E+2"]
    for index, literal in enumerate(not_integer_literals):
        store, found = stored(f"float-{index}", literal)
        assert found == [], (literal, found)
        number = store.expected["PLACEHOLDER-expected-number"]["value"]["number"]
        assert type(number) is float and number == float(literal), literal

    # In a tolerance too, and a failed result that holds such a number is still counted as failed.
    root = tmp_path / "other-slots"
    write_full_store(root)
    text = json.dumps(expected_number()).replace("987654321.0", "9007199254740993")
    write_text(root / "expected" / "PLACEHOLDER-expected-number.json", text)
    failed = changed(result_passed, set_field("outcome", "failed"))
    text = json.dumps(failed).replace("123456789.0", "9007199254740993")
    write_text(root / "results" / "PLACEHOLDER-result-passed.json", text)
    store = load(root)
    found = messages(store, "expected/PLACEHOLDER-expected-number.json")
    assert found and found[0].startswith("tolerance.absolute:")
    found = messages(store, "results/PLACEHOLDER-result-passed.json")
    assert found and found[0].startswith("observed.number:")
    assert "results/PLACEHOLDER-result-passed.json" in records.summarise(store)["failed_malformed"]


def test_S35_result_whose_observed_number_has_more_digits_than_a_float_keeps_is_counted(tmp_path):
    for index, literal in enumerate(["0.10000000000000001", "1e23", "12345678901234567890.0"]):
        root = tmp_path / f"case-{index}"
        write_full_store(root)
        text = json.dumps(result_passed()).replace("123456789.0", literal)
        assert literal in text
        write_text(root / "results" / "PLACEHOLDER-result-passed.json", text)
        store = load(root)
        assert store.problems == (), literal
        assert store.results["PLACEHOLDER-result-passed"]["observed"]["number"] == float(literal)
        summary = records.summarise(store)
        assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}, literal
        assert summary["no_result"] == [] and summary["rejected"] == [], literal
    assert float("0.10000000000000001") == 0.1


# --- input that the functions were not written for -------------------------------

BUILDERS = (
    expected_number,
    expected_text,
    expected_missing,
    protocol_run,
    result_passed,
    result_failed,
    result_not_evaluated,
)


def nested_lists(depth: int, innermost) -> list:
    outer = inner = []
    for _ in range(depth):
        inner.append([])
        inner = inner[0]
    inner.append(innermost)
    return outer


def list_that_holds_itself() -> list:
    itself: list = []
    itself.append(itself)
    return itself


# Values that no field of a record is meant to hold. None of them is a record.
UNEXPECTED_VALUES = [
    None,
    True,
    0,
    -1,
    1.5,
    10**400,
    10**5000,
    float("nan"),
    float("inf"),
    "",
    " ",
    "PLACEHOLDER",
    [],
    [[]],
    [None],
    ["E999", 3],
    {},
    {"PLACEHOLDER": 1},
    {None: "PLACEHOLDER"},
    {10**5000: "PLACEHOLDER"},
    {("PLACEHOLDER",): 1},
    nested_lists(5000, "PLACEHOLDER"),
    list_that_holds_itself(),
    object(),
    set(),
    b"PLACEHOLDER",
    ("PLACEHOLDER", 2),
]


def unchecked_records():
    """Each well-formed record with every field dropped or replaced by every unexpected value."""
    for build in BUILDERS:
        base = build()
        for key in base:
            yield {name: value for name, value in base.items() if name != key}
            for value in UNEXPECTED_VALUES:
                yield {**base, key: value}
            if isinstance(base[key], dict):
                for inner in base[key]:
                    for value in UNEXPECTED_VALUES:
                        yield {**base, key: {**base[key], inner: value}}
        for value in UNEXPECTED_VALUES:
            try:
                yield {**base, value: "PLACEHOLDER"}
            except TypeError:  # not every value can be the name of a field
                continue


def test_R51_check_record_and_is_placeholder_accept_anything_without_raising():
    for record in [*unchecked_records(), *UNEXPECTED_VALUES]:
        for allow_placeholders in (True, False):
            problems = records.check_record(record, allow_placeholders=allow_placeholders)
            assert isinstance(problems, list) and all(isinstance(problem, str) for problem in problems)
        assert records.is_placeholder(record) in (True, False)
    for value in UNEXPECTED_VALUES:
        assert records.check_record(value, allow_placeholders=True) != []
        assert problems_of({**expected_number(), "kind": value}) != []
    assert records.is_placeholder(nested_lists(5000, "PLACEHOLDER")) is True
    assert records.is_placeholder(nested_lists(5000, None)) is False
    assert records.is_placeholder(list_that_holds_itself()) is False


def test_R52_check_references_reports_any_record_and_raises_only_value_error():
    for record in unchecked_records():
        found = records.check_references({"k": record}, {"k": record}, {"k": record})
        # One object cannot be a run, an expected value and a result at once.
        assert list(found) == ["k"] and found["k"]
        assert all(isinstance(problem, str) for problem in found["k"])
    for value in UNEXPECTED_VALUES:
        if isinstance(value, dict):
            continue
        for position in range(3):
            arguments = [{}, {}, {}]
            arguments[position] = value
            with pytest.raises(ValueError, match="check_references"):
                records.check_references(*arguments)


def test_S34_summarise_and_load_store_raise_only_their_documented_exception(tmp_path):
    def store_with(**fields) -> records.Store:
        return records.Store(**{"expected": {}, "runs": {}, "results": {}, "problems": (), **fields})

    for value in UNEXPECTED_VALUES:
        with pytest.raises(ValueError, match="summarise"):
            records.summarise(value)
    for record in unchecked_records():
        for group in ("runs", "results", "unresolved"):
            try:
                records.summarise(store_with(**{group: {"k": record}}))
            except ValueError:
                pass  # the one documented exception; anything else fails this test
    not_a_store_of_load_store = [
        store_with(results={"k": changed(result_failed, drop_field("outcome"))}),
        store_with(unresolved={"k": changed(result_failed, drop_field("run_id"))}),
        store_with(runs={"k": changed(protocol_run, drop_field("test_codes"))}),
        store_with(results={"k": protocol_run()}),
        store_with(results={1: result_failed()}),
        store_with(results=[result_failed()]),
        store_with(problems=("PLACEHOLDER",)),
        store_with(failed_malformed=(1,)),
        records.Store.__new__(records.Store),  # a store object that was never initialised
    ]
    for store in not_a_store_of_load_store:
        with pytest.raises(ValueError, match="summarise"):
            records.summarise(store)
    sound = store_with(
        runs={"PLACEHOLDER-run": protocol_run()},
        results={"PLACEHOLDER-result-failed": result_failed()},
    )
    assert records.summarise(sound)["failed"] == ["PLACEHOLDER-result-failed"]

    for value in UNEXPECTED_VALUES:
        if isinstance(value, str):
            continue
        with pytest.raises(TypeError, match="load_store"):
            records.load_store(value)
    for path in (tmp_path / "PLACEHOLDER-absent", str(tmp_path / "PLACEHOLDER\0absent")):
        store = records.load_store(path)
        assert (store.expected, store.runs, store.results, store.problems) == ({}, {}, {}, ())


# --- every fixture is a placeholder ------------------------------------------------


def test_R53_every_fixture_that_looks_like_a_record_carries_the_word_placeholder(tmp_path):
    fixtures = [build() for build in BUILDERS]
    fixtures += [build() for build in ACCEPTED.values()]
    fixtures += [changed(build, change) for build, change, _ in REJECTED.values()]
    fixtures += list(unchecked_records())
    fixtures += [record for _, record in in_each_number_slot(NOT_EXACT_AS_A_FLOAT)]
    for fixture in fixtures:
        assert records.is_placeholder(fixture), fixture
    for path in sorted(EXAMPLES_ROOT.rglob("*")):
        if path.is_file():
            assert "PLACEHOLDER" in path.name and "PLACEHOLDER" in path.read_text(encoding="utf-8")
    # Every file a test writes goes through write_text, which requires the word.
    source = Path(__file__).read_text(encoding="utf-8")
    assert source.count("." + "write_text(") == 0
    assert source.count("." + "write_bytes(") == 1
    never_written = tmp_path / "PLACEHOLDER-never-written.json"
    with pytest.raises(AssertionError, match="without the word"):
        write_text(never_written, '{"outcome": "failed"}')
    assert not never_written.exists()


# --- the README lists every case -----------------------------------------------


def test_readme_lists_every_proposed_case():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert "## PROPOSED cases" in readme
    listed = readme.split("## PROPOSED cases", 1)[1]
    cases = list(ACCEPTED) + list(REJECTED)
    cases += re.findall(r"^def test_((?:R|S)\d\d)_", Path(__file__).read_text(encoding="utf-8"), re.MULTILINE)
    codes = [case[:3] for case in cases]
    assert len(set(codes)) == len(codes), "case codes must be unique"
    missing = [code for code in codes if f"| {code} |" not in listed]
    assert missing == []
