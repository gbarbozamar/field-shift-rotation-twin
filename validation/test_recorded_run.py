"""The recorded runs of the validation protocol load and add up.

Unit l0/validation-run-record (issue #289). A recorded run is one
``protocol_run`` record in ``validation/runs/`` with its ``result`` records in
``validation/results/``. This file reads the real store and checks it with the
functions of ``validation/records.py``. It does not run the protocol again.

It holds no expected value of the science, no tolerance and no citation. The
counts below are outcomes: what pytest reported, in the run that was recorded,
for the tests that stand under a code of ``docs/VALIDATION.md``.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest

from validation import records

REPOSITORY = Path(__file__).resolve().parents[1]
PROTOCOL_FILE = REPOSITORY / "docs" / "VALIDATION.md"

# One entry per recorded run, by the id of its ``protocol_run`` record.
#   outcomes: the counts of the JUnit report of that run over the tests that
#     have a result record, in the outcome words of the store (a test that
#     pytest skipped is ``not_evaluated``);
#   skipped_in_the_whole_suite: the number of tests pytest skipped in the whole
#     suite of that run. Each of them is in the store with the reason pytest
#     printed: as a ``not_evaluated`` result when it stands under a code, and
#     otherwise as a line of the notes of the run that starts with
#     ``- SKIPPED``.
RECORDED_RUNS = {
    "run-20261115T061340Z-3ced36f": {
        "outcomes": {"passed": 37, "failed": 0, "not_evaluated": 3},
        "skipped_in_the_whole_suite": 17,
    },
    "run-20261115T100532Z-b831602": {
        "outcomes": {"passed": 73, "failed": 0, "not_evaluated": 3},
        "skipped_in_the_whole_suite": 17,
    },
    "run-20261115T122846Z-9410a92": {
        "outcomes": {"passed": 496, "failed": 0, "not_evaluated": 2},
        "skipped_in_the_whole_suite": 16,
    },
    "run-20261115T170110Z-df43899": {
        "outcomes": {"passed": 497, "failed": 0, "not_evaluated": 1},
        "skipped_in_the_whole_suite": 16,
    },
}

_ENTRY_HEADING_RE = re.compile(r"^### ([EHD][0-9]+[a-z]?)\s*$")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_RESULT_TEST_RE = re.compile(r"Test (\S+\.py)::(test_\w+)(\[.*\])?\. Placed under ")
_SKIPPED_LINE_RE = re.compile(r"- SKIPPED (\S+\.py)::(test_\w+): \S")
_ENTRY_TEST_RE = re.compile(r"- Test: `(\S+\.py)::(test_\w+)`")


@pytest.fixture(scope="module")
def store() -> records.Store:
    return records.load_store(records.STORE_ROOT)


def results_of(store: records.Store, run_id: str) -> dict[str, dict]:
    return {key: result for key, result in store.results.items() if result["run_id"] == run_id}


def codes_not_defined() -> set[str]:
    """The codes whose entry of docs/VALIDATION.md has the status 'not defined'."""
    found: set[str] = set()
    code = None
    for line in PROTOCOL_FILE.read_text(encoding="utf-8").splitlines():
        heading = _ENTRY_HEADING_RE.match(line)
        if heading:
            code = heading.group(1)
        elif line.startswith("#"):
            code = None
        elif code is not None and line.strip() == "- Status: not defined":
            found.add(code)
    return found


def top_level_tests_of(path: str) -> dict[str, ast.FunctionDef]:
    """The test functions written at the top level of a file of the repository."""
    file = REPOSITORY / path
    assert file.is_file(), f"{path} is not a file of the repository"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def named_by_the_entries() -> dict[str, tuple[str, str]]:
    """By code, the file and the function that the entry of docs/VALIDATION.md names on its 'Test:' line."""
    found: dict[str, tuple[str, str]] = {}
    code = None
    for line in PROTOCOL_FILE.read_text(encoding="utf-8").splitlines():
        heading = _ENTRY_HEADING_RE.match(line)
        if heading:
            code = heading.group(1)
        elif line.startswith("#"):
            code = None
        elif code is not None and _ENTRY_TEST_RE.match(line):
            found[code] = _ENTRY_TEST_RE.match(line).groups()
    return found


def latest_run_id(store: records.Store) -> str:
    # The time format of a run is fixed, so the texts sort as the times do.
    return max(store.runs, key=lambda run_id: store.runs[run_id]["run_at"])


def test_the_real_store_is_accepted_by_every_check_of_records(store):
    assert store.problems == ()
    assert store.unresolved == {}
    assert store.failed_malformed == ()
    for group in (store.expected, store.runs, store.results):
        for record in group.values():
            assert records.check_record(record) == []
    assert records.check_references(store.expected, store.runs, store.results) == {}


def test_every_recorded_run_is_in_the_store_and_no_other(store):
    assert set(store.runs) == set(RECORDED_RUNS)


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_a_run_names_its_commit_its_protocol_and_the_session_that_ran_it(store, run_id):
    run = store.runs[run_id]
    assert _COMMIT_RE.fullmatch(run["code_version"])
    assert run["code_version"] in run["protocol"]
    assert run_id.endswith(run["code_version"][:7])
    # A run made by a session says so; no person is named as having run it.
    assert run["run_by"].startswith("AI session")
    assert "pytest" in run["notes"]


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_the_results_of_a_run_give_the_counts_pytest_reported(store, run_id):
    outcomes = Counter(result["outcome"] for result in results_of(store, run_id).values())
    assert {word: outcomes[word] for word in records.OUTCOMES} == RECORDED_RUNS[run_id]["outcomes"]


def test_summarise_gives_the_counts_pytest_reported(store):
    summary = records.summarise(store)
    expected = Counter()
    for run in RECORDED_RUNS.values():
        expected.update(run["outcomes"])
    assert summary["counts"] == {word: expected[word] for word in records.OUTCOMES}
    assert summary["results_total"] == sum(expected.values()) == len(store.results)
    assert len(summary["failed"]) == expected["failed"]
    assert len(summary["not_evaluated"]) == expected["not_evaluated"]
    assert summary["failed_malformed"] == []
    assert summary["broken_references"] == []
    assert summary["rejected"] == []


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_a_code_without_a_result_is_listed_and_never_counted(store, run_id):
    run = store.runs[run_id]
    with_a_result = {result["test_code"] for result in results_of(store, run_id).values()}
    listed = [item["test_code"] for item in records.summarise(store)["no_result"] if item["run_id"] == run_id]
    assert listed == [code for code in run["test_codes"] if code not in with_a_result]
    assert listed, "this run has codes with no test; they must stay visible"


def test_no_code_whose_entry_is_not_defined_holds_a_passed_result(store):
    # Since D252 to D254 no entry of docs/VALIDATION.md has the status
    # "not defined"; the check stays for any entry that returns to it.
    not_defined = codes_not_defined()
    passed = {result["test_code"] for result in store.results.values() if result["outcome"] == "passed"}
    assert passed & not_defined == set()


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_every_result_names_the_test_it_is_the_outcome_of(store, run_id):
    short = store.runs[run_id]["code_version"][:7]
    names = []
    for result_id, result in results_of(store, run_id).items():
        assert result_id.startswith(f"{short}-{result['test_code']}-test_")
        name = _RESULT_TEST_RE.match(result["notes"])
        assert name, result_id
        path, function, case = name.groups()
        node = f"{path}::{function}{case or ''}"
        names.append(node)
        # The id is built from the commit, the code and the test function.
        assert re.fullmatch(re.escape(f"{short}-{result['test_code']}-{function}-") + r"\d{3}", result_id)
        slot = result["observed"]
        assert node in (slot.get("text") or slot.get("missing_reason"))
        # No expected-value record is pointed to: the store holds none.
        assert set(result["expected"]) == {"missing_reason"}
    assert len(set(names)) == len(names), "a test has one outcome in a run"


def test_the_latest_run_names_test_files_and_functions_that_exist(store):
    """A record cannot name a test that is not there.

    Only the latest run is held to this: an earlier run names the tests of its
    own commit, which a later unit may rename. What this does not show: that
    the named test is the check of its code, or that its outcome was the one
    recorded. Only running the suite again shows that.
    """
    run_id = latest_run_id(store)
    named_by_entry = named_by_the_entries()
    functions: dict[str, dict[str, ast.FunctionDef]] = {}
    checked = 0
    for result_id, result in results_of(store, run_id).items():
        path, function, case = _RESULT_TEST_RE.match(result["notes"]).groups()
        found = functions.setdefault(path, top_level_tests_of(path))
        assert function in found, f"{result_id} names {path}::{function}, which is not a test of that file"
        if case:
            assert found[function].decorator_list, f"{result_id} names a case of a test that has no cases"
        if result["test_code"] in named_by_entry:
            # Where the entry names its test, the result is the outcome of that test.
            assert (path, function) == named_by_entry[result["test_code"]], result_id
        checked += 1
    assert checked == sum(RECORDED_RUNS[run_id]["outcomes"].values())
    for line in store.runs[run_id]["notes"].splitlines():
        if line.startswith("- SKIPPED "):
            path, function = _SKIPPED_LINE_RE.match(line).groups()
            found = functions.setdefault(path, top_level_tests_of(path))
            assert function in found, f"the notes name {path}::{function}, which is not a test of that file"


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_every_skipped_test_is_in_the_store_with_its_reason(store, run_id):
    not_evaluated = [r for r in results_of(store, run_id).values() if r["outcome"] == "not_evaluated"]
    for result in not_evaluated:
        # The three tests skipped under a code name that code in their reason.
        assert result["reason"].startswith(f"[{result['test_code']}] ")
        assert "pytest skipped" in result["observed"]["missing_reason"]
    lines = [line for line in store.runs[run_id]["notes"].splitlines() if line.startswith("- SKIPPED ")]
    assert all(re.match(r"- SKIPPED \S+\.py::test_\w+: \S", line) for line in lines)
    assert len(not_evaluated) + len(lines) == RECORDED_RUNS[run_id]["skipped_in_the_whole_suite"]


@pytest.mark.parametrize("run_id", sorted(RECORDED_RUNS))
def test_the_notes_of_a_run_hold_what_no_result_can(store, run_id):
    notes = store.runs[run_id]["notes"]
    # The plot check has no code, so it has no result. Its entry gives it two
    # statuses, one for each way of obtaining C, and the notes keep them apart.
    assert "PLOT CHECK WITHOUT A CODE: NOT PASSED FOR THE COMPUTED C; A KNOWN OVERESTIMATE FOR THE DECLARED C" in notes
    # The tests of the machinery of E3 and H2 ran and are not results.
    assert re.search(r"TESTS OF THE MACHINERY OF E3 AND H2, NOT RECORDED AS RESULTS \(\d+ items\)", notes)
    # The structural cases under entries that are not defined are not results.
    assert "passing them does not make either entry pass" in notes
    for code in ("E8", "E9", "H7", "H8"):
        assert re.search(rf"{code}: \d+ items of \d+ test functions ran, \d+ passed, \d+ did not pass", notes)
    # The decision tests ran on the functions as they are.
    assert "do not say that the decided rule is built" in notes
