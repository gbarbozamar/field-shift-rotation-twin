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


def write(root: Path, record, *, folder: str | None = None, name: str | None = None) -> Path:
    folder = folder or records.FOLDER_BY_KIND[record["kind"]]
    path = root / folder / (name or f"{record['id']}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


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
    (tmp_path / "expected" / "PLACEHOLDER-broken.json").write_text("{ not json", encoding="utf-8")
    store = load(tmp_path)
    assert any("is not valid JSON" in m for m in messages(store, "expected/PLACEHOLDER-broken.json"))
    assert len(store.expected) == 3 and len(store.results) == 3


def test_S08_field_written_twice_is_rejected(tmp_path):
    text = json.dumps(expected_number())
    text = text[:-1] + ', "checked_by": "PLACEHOLDER person C"}'
    path = tmp_path / "expected" / "PLACEHOLDER-expected-number.json"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    store = load(tmp_path)
    assert any("written twice" in m for m in messages(store, "expected/PLACEHOLDER-expected-number.json"))
    assert store.expected == {}


def test_S09_nan_written_in_a_file_is_rejected(tmp_path):
    text = json.dumps(expected_number()).replace("123456789.0", "NaN")
    path = tmp_path / "expected" / "PLACEHOLDER-expected-number.json"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
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
    (tmp_path / "results" / "PLACEHOLDER-notes.txt").write_text("PLACEHOLDER", encoding="utf-8")
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


def test_S19_malformed_failed_result_is_listed_as_rejected_not_lost(tmp_path):
    write_full_store(tmp_path)
    write(tmp_path, changed(result_failed, drop_field("observed")))
    summary = records.summarise(load(tmp_path))
    assert summary["failed"] == []
    assert summary["rejected"] == ["results/PLACEHOLDER-result-failed.json"]
    assert summary["no_result"] == [{"run_id": "PLACEHOLDER-run", "test_code": "D999"}]


def test_S20_file_holding_a_list_is_rejected(tmp_path):
    path = tmp_path / "runs" / "PLACEHOLDER-run.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([protocol_run()]), encoding="utf-8")
    store = load(tmp_path)
    assert messages(store, "runs/PLACEHOLDER-run.json") == ["record: must be a JSON object"]


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
