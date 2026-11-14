"""Record format of the validation store and the check that rejects a malformed record.

Three kinds of record, one JSON file each (see validation/README.md):

- ``expected_value``: a value with its citation and the two persons who
  transcribed and checked it;
- ``protocol_run``: one execution of the validation protocol;
- ``result``: the outcome of one test in one run, including a failed one.

The format is PROPOSED until a person approves it. This module holds no
expected value, no tolerance and no citation: people supply those.

``check_record``, ``check_references`` and ``summarise`` are pure functions.
``load_store`` only reads files below the folder it is given.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1

KIND_EXPECTED = "expected_value"
KIND_RUN = "protocol_run"
KIND_RESULT = "result"

# Folder of each kind, relative to the root of a store.
FOLDER_BY_KIND = {
    KIND_EXPECTED: "expected",
    KIND_RUN: "runs",
    KIND_RESULT: "results",
}

# PROPOSED: the allowed words for the outcome of a result.
OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_NOT_EVALUATED = "not_evaluated"
OUTCOMES = (OUTCOME_PASSED, OUTCOME_FAILED, OUTCOME_NOT_EVALUATED)

# The real store is this folder; validation/examples/ is a second, separate store.
STORE_ROOT = Path(__file__).resolve().parent

# PROPOSED: a test code is a family letter (E, H or D), a number and an optional
# lower-case letter, as the codes appear in section 8 of the blueprint.
_TEST_CODE_RE = re.compile(r"[EHD][0-9]+[a-z]?")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# A folder with this name directly below the root of a store is a separate
# store, holding placeholder records only. It is not read with its parent.
EXAMPLES_FOLDER = "examples"

_TOO_DEEP = "is nested too deeply to be a record"
_OUTSIDE = "is outside 'expected/', 'runs/' and 'results/': a record lives in one of these three folders"

_PLACEHOLDER_WORD = "placeholder"
_CITATION_NEEDED = "CITATION NEEDED"

_COMMON_FIELDS = frozenset({"format_version", "kind", "id"})
_OPTIONAL_COMMON_FIELDS = frozenset({"notes"})

_EXPECTED_REQUIRED = _COMMON_FIELDS | {
    "test_code",
    "quantity",
    "value",
    "citation",
    "transcribed_by",
    "checked_by",
}
_EXPECTED_OPTIONAL = _OPTIONAL_COMMON_FIELDS | {"tolerance"}

_RUN_REQUIRED = _COMMON_FIELDS | {
    "protocol",
    "code_version",
    "run_at",
    "run_by",
    "test_codes",
}
_RUN_OPTIONAL = _OPTIONAL_COMMON_FIELDS

_RESULT_REQUIRED = _COMMON_FIELDS | {
    "run_id",
    "test_code",
    "expected",
    "outcome",
    "observed",
}
_RESULT_OPTIONAL = _OPTIONAL_COMMON_FIELDS | {"reason"}

# A slot that can be missing has exactly one of these forms. A missing value
# is always written {"missing_reason": "..."}: it is never zero, null or absent.
_VALUE_FORMS = {
    "number": frozenset({"number", "unit"}),
    "text": frozenset({"text"}),
    "missing": frozenset({"missing_reason"}),
}
_TOLERANCE_FORMS = {
    "absolute": frozenset({"absolute"}),
    "relative": frozenset({"relative"}),
    "missing": frozenset({"missing_reason"}),
}
_EXPECTED_REFERENCE_FORMS = {
    "id": frozenset({"id"}),
    "missing": frozenset({"missing_reason"}),
}


# --- small predicates ---------------------------------------------------------


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _person_key(name: str) -> str:
    """Two spellings that differ only in case or spacing are the same person."""
    return " ".join(name.split()).casefold()


def is_placeholder(record: Any) -> bool:
    """True when any key or any text anywhere in the record contains PLACEHOLDER."""
    if isinstance(record, str):
        return _PLACEHOLDER_WORD in record.casefold()
    if isinstance(record, dict):
        return any(is_placeholder(key) or is_placeholder(value) for key, value in record.items())
    if isinstance(record, list):
        return any(is_placeholder(item) for item in record)
    return False


# --- checks of one record -----------------------------------------------------


def _check_keys(obj: dict, required: frozenset, optional: frozenset, where: str, problems: list[str]) -> None:
    for key in sorted(required - obj.keys(), key=str):
        problems.append(f"{where}: missing field '{key}'")
    for key in sorted(obj.keys() - required - optional, key=str):
        problems.append(f"{where}: unknown field '{key}'")


def _check_text(obj: dict, key: str, where: str, problems: list[str]) -> None:
    if key in obj and not _is_text(obj[key]):
        problems.append(f"{where}{key}: must be a non-empty string")


def _match_form(obj: Any, forms: dict[str, frozenset], where: str, problems: list[str]) -> str | None:
    listed = " or ".join("{" + ", ".join(sorted(keys)) + "}" for keys in forms.values())
    if not isinstance(obj, dict):
        problems.append(f"{where}: must be an object with exactly the fields {listed}")
        return None
    keys = frozenset(obj)
    for name, form_keys in forms.items():
        if keys == form_keys:
            return name
    problems.append(f"{where}: must have exactly the fields {listed}")
    return None


def _check_missing_reason(obj: dict, where: str, problems: list[str]) -> None:
    if not _is_text(obj["missing_reason"]):
        problems.append(f"{where}.missing_reason: a missing value must state its reason")


def _check_value(obj: Any, where: str, problems: list[str]) -> str | None:
    """Check a value slot. Returns its form: 'number', 'text' or 'missing'."""
    form = _match_form(obj, _VALUE_FORMS, where, problems)
    if form == "number":
        if not _is_number(obj["number"]):
            problems.append(f"{where}.number: must be a finite number, not a string or a boolean")
        if not _is_text(obj["unit"]):
            problems.append(f"{where}.unit: a number must state its unit as a non-empty string")
    elif form == "text":
        if not _is_text(obj["text"]):
            problems.append(f"{where}.text: must be a non-empty string")
    elif form == "missing":
        _check_missing_reason(obj, where, problems)
    return form


def _check_test_code(code: Any, where: str, problems: list[str]) -> None:
    if not isinstance(code, str) or not _TEST_CODE_RE.fullmatch(code):
        problems.append(
            f"{where}: must be a test code of family E, H or D, such as 'E3' or 'E1b'; got {code!r}"
        )


def _check_common(record: dict, problems: list[str]) -> None:
    if "format_version" in record:
        version = record["format_version"]
        if type(version) is not int or version != FORMAT_VERSION:
            problems.append(f"format_version: must be the integer {FORMAT_VERSION}; got {version!r}")
    if "id" in record:
        identifier = record["id"]
        if not isinstance(identifier, str) or not _ID_RE.fullmatch(identifier):
            problems.append(
                "id: must start with a letter or a digit and contain only letters, digits, '.', '_' and '-'"
            )
    _check_text(record, "notes", "", problems)


def _check_citation(record: dict, problems: list[str]) -> None:
    if "citation" not in record:
        return  # already reported as a missing field
    citation = record["citation"]
    if not isinstance(citation, dict):
        problems.append("citation: must be an object with the fields 'reference' and 'locator'")
        return
    _check_keys(citation, frozenset({"reference", "locator"}), frozenset({"url"}), "citation", problems)
    for key in ("reference", "locator", "url"):
        if key not in citation:
            continue
        text = citation[key]
        if not _is_text(text):
            problems.append(f"citation.{key}: must be a non-empty string")
        elif _CITATION_NEEDED in " ".join(text.split()).upper():
            problems.append(f"citation.{key}: is marked CITATION NEEDED; a person supplies the citation")


def _check_expected(record: dict, problems: list[str]) -> None:
    _check_keys(record, _EXPECTED_REQUIRED, _EXPECTED_OPTIONAL, "record", problems)
    if "test_code" in record:
        _check_test_code(record["test_code"], "test_code", problems)
    _check_text(record, "quantity", "", problems)

    value_form = _check_value(record["value"], "value", problems) if "value" in record else None
    if value_form == "number":
        if "tolerance" not in record:
            problems.append(
                "tolerance: a numeric expected value must carry its tolerance, "
                "or {'missing_reason': ...}; it is never assumed"
            )
        else:
            tolerance = record["tolerance"]
            form = _match_form(tolerance, _TOLERANCE_FORMS, "tolerance", problems)
            if form == "missing":
                _check_missing_reason(tolerance, "tolerance", problems)
            elif form is not None and (not _is_number(tolerance[form]) or tolerance[form] < 0):
                problems.append(f"tolerance.{form}: must be a finite number, zero or greater")
    elif value_form is not None and "tolerance" in record:
        problems.append("tolerance: only a numeric expected value carries a tolerance")

    _check_citation(record, problems)

    for key in ("transcribed_by", "checked_by"):
        _check_text(record, key, "", problems)
    transcriber, checker = record.get("transcribed_by"), record.get("checked_by")
    if _is_text(transcriber) and _is_text(checker) and _person_key(transcriber) == _person_key(checker):
        problems.append("checked_by: must be a different person from transcribed_by")


def _check_run(record: dict, problems: list[str]) -> None:
    _check_keys(record, _RUN_REQUIRED, _RUN_OPTIONAL, "record", problems)
    for key in ("protocol", "code_version", "run_by"):
        _check_text(record, key, "", problems)
    if "run_at" in record:
        run_at = record["run_at"]
        valid = isinstance(run_at, str) and _UTC_TIMESTAMP_RE.fullmatch(run_at) is not None
        if valid:
            try:
                datetime.strptime(run_at, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                valid = False
        if not valid:
            problems.append("run_at: must be a UTC time written as YYYY-MM-DDTHH:MM:SSZ")
    if "test_codes" in record:
        codes = record["test_codes"]
        if not isinstance(codes, list) or not codes:
            problems.append("test_codes: must be a non-empty list of test codes")
        else:
            for index, code in enumerate(codes):
                _check_test_code(code, f"test_codes[{index}]", problems)
            texts = [code for code in codes if isinstance(code, str)]
            if len(set(texts)) != len(texts):
                problems.append("test_codes: a test code is listed more than once")


def _check_result(record: dict, problems: list[str]) -> None:
    _check_keys(record, _RESULT_REQUIRED, _RESULT_OPTIONAL, "record", problems)
    _check_text(record, "run_id", "", problems)
    if "test_code" in record:
        _check_test_code(record["test_code"], "test_code", problems)

    if "expected" in record:
        reference = record["expected"]
        form = _match_form(reference, _EXPECTED_REFERENCE_FORMS, "expected", problems)
        if form == "id" and not _is_text(reference["id"]):
            problems.append("expected.id: must be the id of an expected-value record")
        elif form == "missing":
            _check_missing_reason(reference, "expected", problems)

    outcome = record.get("outcome")
    outcome_known = isinstance(outcome, str) and outcome in OUTCOMES
    if "outcome" in record and not outcome_known:
        problems.append(f"outcome: must be one of {', '.join(OUTCOMES)}; got {outcome!r}")

    observed_form = _check_value(record["observed"], "observed", problems) if "observed" in record else None
    if outcome_known:
        if outcome == OUTCOME_PASSED and observed_form == "missing":
            problems.append("outcome: a result without an observed value cannot be 'passed'")
        if outcome == OUTCOME_NOT_EVALUATED:
            if not _is_text(record.get("reason")):
                problems.append("reason: a result that was not evaluated must state why")
        elif "reason" in record:
            problems.append("reason: only a 'not_evaluated' result carries a reason; use 'notes' for remarks")


_CHECK_BY_KIND = {
    KIND_EXPECTED: _check_expected,
    KIND_RUN: _check_run,
    KIND_RESULT: _check_result,
}


def check_record(record: Any, *, allow_placeholders: bool = False) -> list[str]:
    """Return every problem found in one record. An empty list means it is accepted.

    A record that contains the word PLACEHOLDER anywhere is rejected unless
    ``allow_placeholders`` is true, so a placeholder can never stand in the
    real store as if it were a value with a source.
    """
    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    kind = record.get("kind")
    if not isinstance(kind, str) or kind not in _CHECK_BY_KIND:
        return [f"kind: must be one of {', '.join(_CHECK_BY_KIND)}; got {kind!r}"]
    problems: list[str] = []
    _check_common(record, problems)
    _CHECK_BY_KIND[kind](record, problems)
    if not allow_placeholders and is_placeholder(record):
        problems.append("record: contains the word PLACEHOLDER; a placeholder is not a record of the store")
    return problems


# --- checks across records ----------------------------------------------------


def _problems_as(record: Any, kind: str) -> list[str]:
    """Problems of a record that is meant to be of the given kind."""
    problems = check_record(record, allow_placeholders=True)
    if not problems and record["kind"] != kind:
        problems = [f"kind: must be '{kind}' here; got '{record['kind']}'"]
    return problems


def check_references(
    expected: dict[str, dict], runs: dict[str, dict], results: dict[str, dict]
) -> dict[str, list[str]]:
    """Check what each result points to. Returns problems by result id.

    Never raises on a record that was not checked before: a malformed result
    gets its own problems, and a malformed run or expected value counts as
    not accepted.
    """
    runs = {key: run for key, run in runs.items() if not _problems_as(run, KIND_RUN)}
    expected = {key: value for key, value in expected.items() if not _problems_as(value, KIND_EXPECTED)}
    found: dict[str, list[str]] = {}
    for result_id, result in results.items():
        problems = _problems_as(result, KIND_RESULT)
        if problems:
            found[result_id] = problems
            continue
        run = runs.get(result["run_id"])
        if run is None:
            problems.append(f"run_id: no accepted protocol run has the id '{result['run_id']}'")
        elif result["test_code"] not in run["test_codes"]:
            problems.append(
                f"test_code: '{result['test_code']}' is not listed in the test_codes of run '{result['run_id']}'"
            )
        reference = result["expected"]
        if "id" in reference:
            target = expected.get(reference["id"])
            if target is None:
                problems.append(f"expected.id: no accepted expected value has the id '{reference['id']}'")
            else:
                if target["test_code"] != result["test_code"]:
                    problems.append(
                        f"expected.id: '{reference['id']}' belongs to test "
                        f"'{target['test_code']}', not to '{result['test_code']}'"
                    )
                if "missing_reason" in target["value"] and result["outcome"] != OUTCOME_NOT_EVALUATED:
                    problems.append(
                        "outcome: the referenced expected value is missing, "
                        f"so the outcome can only be '{OUTCOME_NOT_EVALUATED}'"
                    )
        if problems:
            found[result_id] = problems
    return found


# --- reading a store ----------------------------------------------------------


@dataclass(frozen=True)
class Store:
    """The accepted records of a store, by id, and every problem found while reading it.

    ``unresolved`` holds the results that are well-formed on their own but
    point to a run or to an expected value that is not accepted. They are not
    among the accepted ``results``, and their problems are in ``problems``.
    """

    expected: dict[str, dict]
    runs: dict[str, dict]
    results: dict[str, dict]
    problems: tuple[tuple[str, str], ...]  # (file path relative to the store root, message)
    unresolved: dict[str, dict] = field(default_factory=dict)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"the field '{key}' is written twice")
        obj[key] = value
    return obj


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a number; a missing value is written with 'missing_reason'")


def _read_json(path: Path) -> tuple[Any, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot be read as UTF-8 text: {exc}"
    try:
        record = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ValueError as exc:
        return None, f"is not valid JSON: {exc}"
    except RecursionError:
        return None, _TOO_DEEP
    return record, None


def load_store(root: Path | str, *, allow_placeholders: bool = False) -> Store:
    """Read every record below ``root`` and check it.

    A malformed record is not returned among the accepted ones, and it is not
    dropped either: it is listed in ``Store.problems`` with its file path.
    One file that cannot be read never stops the rest from loading.
    A folder that does not exist yet holds no record.

    Everything inside the three record folders is read or reported. Outside
    them, every ``.json`` file below ``root`` is reported, so a record in a
    misnamed folder is not lost. Only two things are not looked at: the
    folder ``examples/`` directly below ``root``, and files outside the three
    folders that are not ``.json`` files.
    """
    root = Path(root)
    accepted: dict[str, dict[str, dict]] = {kind: {} for kind in FOLDER_BY_KIND}
    paths: dict[tuple[str, str], str] = {}
    problems: list[tuple[str, str]] = []

    if root.is_dir():
        read_elsewhere = set(FOLDER_BY_KIND.values()) | {EXAMPLES_FOLDER}
        for path in sorted(root.rglob("*")):
            parts = path.relative_to(root).parts
            if parts[0] in read_elsewhere and len(parts) > 1:
                continue
            if path.is_file() and path.suffix.lower() == ".json":
                problems.append(("/".join(parts), _OUTSIDE))

    for kind, folder in FOLDER_BY_KIND.items():
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            relative = f"{folder}/{path.name}"
            if path.is_dir() or path.suffix != ".json":
                problems.append((relative, "is not a record: this folder holds only files named <id>.json"))
                continue
            record, error = _read_json(path)
            if error is not None:
                problems.append((relative, error))
                continue
            try:
                found = check_record(record, allow_placeholders=allow_placeholders)
            except RecursionError:
                problems.append((relative, _TOO_DEEP))
                continue
            if isinstance(record, dict):
                record_kind = record.get("kind")
                if isinstance(record_kind, str) and record_kind in FOLDER_BY_KIND and record_kind != kind:
                    found.append(
                        f"kind: a '{record_kind}' record belongs in "
                        f"'{FOLDER_BY_KIND[record_kind]}/', not in '{folder}/'"
                    )
                record_id = record.get("id")
                if isinstance(record_id, str) and path.name != f"{record_id}.json":
                    found.append(f"id: the file must be named '{record_id}.json'")
            if found:
                problems.extend((relative, message) for message in found)
                continue
            accepted[kind][record["id"]] = record
            paths[(kind, record["id"])] = relative

    results = accepted[KIND_RESULT]
    unresolved: dict[str, dict] = {}
    broken = check_references(accepted[KIND_EXPECTED], accepted[KIND_RUN], results)
    for result_id, messages in broken.items():
        unresolved[result_id] = results.pop(result_id)
        problems.extend((paths[(KIND_RESULT, result_id)], message) for message in messages)

    return Store(
        expected=accepted[KIND_EXPECTED],
        runs=accepted[KIND_RUN],
        results=results,
        problems=tuple(sorted(problems)),
        unresolved=unresolved,
    )


# --- reporting ----------------------------------------------------------------


def summarise(store: Store) -> dict:
    """Report the results of a store without dropping anything.

    Every accepted result is counted under its outcome; failed and
    not-evaluated results are listed by id; a test code that a run lists
    without any counted result is listed under ``no_result``; every file that
    was rejected is listed under ``rejected``.

    A well-formed result whose references are broken (``Store.unresolved``) is
    listed under ``broken_references`` with its outcome. When that outcome is
    ``failed`` it is also counted and listed as failed: a failure is never
    hidden by a broken reference. With any other outcome it is not counted: a
    pass that cannot be traced to its run and expected value is not a pass.

    ``results_total`` is the number of results counted under an outcome.
    """
    counts = {outcome: 0 for outcome in OUTCOMES}
    by_outcome: dict[str, list[str]] = {outcome: [] for outcome in OUTCOMES}
    reported: set[tuple[str, str]] = set()
    counted = list(store.results.items())
    counted += [item for item in store.unresolved.items() if item[1]["outcome"] == OUTCOME_FAILED]
    for result_id, result in counted:
        counts[result["outcome"]] += 1
        by_outcome[result["outcome"]].append(result_id)
        reported.add((result["run_id"], result["test_code"]))
    no_result = [
        {"run_id": run_id, "test_code": code}
        for run_id, run in sorted(store.runs.items())
        for code in run["test_codes"]
        if (run_id, code) not in reported
    ]
    return {
        "results_total": sum(counts.values()),
        "counts": counts,
        OUTCOME_FAILED: sorted(by_outcome[OUTCOME_FAILED]),
        OUTCOME_NOT_EVALUATED: sorted(by_outcome[OUTCOME_NOT_EVALUATED]),
        "broken_references": [
            {"id": result_id, "outcome": result["outcome"]}
            for result_id, result in sorted(store.unresolved.items())
        ],
        "no_result": no_result,
        "rejected": sorted({path for path, _ in store.problems}),
    }
