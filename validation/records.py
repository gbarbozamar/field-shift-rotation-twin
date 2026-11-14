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

What each public function does with an input it was not written for:

- ``check_record`` and ``is_placeholder`` accept any object and never raise;
- ``check_references`` reports a problem for any record, and raises
  ``ValueError`` when one of its three arguments is not a dict;
- ``summarise`` raises ``ValueError`` when it is not given a store whose
  records are well-formed, as ``load_store`` returns it;
- ``load_store`` raises ``TypeError`` when ``root`` is not a path.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
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

_INEXACT_INTEGER = "is an integer that a float cannot hold exactly, so it would change when read"

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


class _ChangedNumber(float):
    """A number written in a file with digits that are lost when it is read.

    ``_read_json`` puts it in place of the number, so that the record can
    still be checked and the field is reported. No slot accepts it.
    """

    literal: str

    def __new__(cls, value: float, literal: str = "") -> "_ChangedNumber":
        number = super().__new__(cls, value)
        number.literal = literal
        return number


def _exactness_problem(value: Any) -> str | None:
    """Why a number would not be read back as it is written, or None.

    Engines and other readers of a JSON file hold a number as a float, so a
    number that a float cannot hold exactly is reported, never rounded.
    """
    if isinstance(value, _ChangedNumber):
        literal = value.literal if len(value.literal) <= 40 else value.literal[:40] + "..."
        return f"is written as {literal}, which would change when read as a number"
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            exact = float(value) == value
        except OverflowError:
            exact = False
        if not exact:
            return _INEXACT_INTEGER
    return None


def _shown(value: Any) -> str:
    """A short description of any value for a problem message. Never raises."""
    if isinstance(value, str):
        return repr(value if len(value) <= 60 else value[:60] + "...")
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, (int, float)):
        try:
            return repr(value)
        except ValueError:
            return "an integer too long to print"
    return f"a value of type {type(value).__name__}"


def _key_text(key: Any) -> str:
    return key if isinstance(key, str) else _shown(key)


def _person_key(name: str) -> str:
    """Two spellings that differ only in case or spacing are the same person."""
    return " ".join(name.split()).casefold()


def is_placeholder(record: Any) -> bool:
    """True when any key or any text anywhere in the record contains PLACEHOLDER.

    Accepts any object and never raises, however deeply it is nested.
    """
    pending = [record]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if _PLACEHOLDER_WORD in item.casefold():
                return True
        elif isinstance(item, (dict, list)) and id(item) not in seen:
            seen.add(id(item))
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
    return False


# --- checks of one record -----------------------------------------------------


def _check_keys(obj: dict, required: frozenset, optional: frozenset, where: str, problems: list[str]) -> None:
    for key in sorted(required - obj.keys()):
        problems.append(f"{where}: missing field '{key}'")
    for text in sorted(_key_text(key) for key in obj.keys() - required - optional):
        problems.append(f"{where}: unknown field '{text}'")


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
        exactness = _exactness_problem(obj["number"])
        if exactness is not None:
            problems.append(f"{where}.number: {exactness}")
        elif not _is_number(obj["number"]):
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
            f"{where}: must be a test code of family E, H or D, such as 'E3' or 'E1b'; got {_shown(code)}"
        )


def _check_common(record: dict, problems: list[str]) -> None:
    if "format_version" in record:
        version = record["format_version"]
        if type(version) is not int or version != FORMAT_VERSION:
            problems.append(f"format_version: must be the integer {FORMAT_VERSION}; got {_shown(version)}")
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
            elif form is not None:
                exactness = _exactness_problem(tolerance[form])
                if exactness is not None:
                    problems.append(f"tolerance.{form}: {exactness}")
                elif not _is_number(tolerance[form]) or tolerance[form] < 0:
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
        problems.append(f"outcome: must be one of {', '.join(OUTCOMES)}; got {_shown(outcome)}")

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

    Accepts any object and never raises: whatever is wrong is a problem in
    the list.
    """
    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    kind = record.get("kind")
    if not isinstance(kind, str) or kind not in _CHECK_BY_KIND:
        return [f"kind: must be one of {', '.join(_CHECK_BY_KIND)}; got {_shown(kind)}"]
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

    Raises ``ValueError``, and nothing else, when ``expected``, ``runs`` or
    ``results`` is not a dict of records by id.
    """
    for name, group in (("expected", expected), ("runs", runs), ("results", results)):
        if not isinstance(group, dict):
            raise ValueError(f"check_references: '{name}' must be a dict of records by id")
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

    ``failed_malformed`` holds the paths of the rejected files, in any of the
    three folders, whose record says that its outcome is failed. Nothing else
    of such a record is trusted.
    """

    expected: dict[str, dict]
    runs: dict[str, dict]
    results: dict[str, dict]
    problems: tuple[tuple[str, str], ...]  # (file path relative to the store root, message)
    unresolved: dict[str, dict] = field(default_factory=dict)
    failed_malformed: tuple[str, ...] = ()


def _says_failed(record: Any) -> bool:
    """True when a record, however malformed, says that its outcome is failed.

    Upper or lower case and surrounding spaces do not matter here: 'FAILED' is
    not an allowed outcome word, but it must not hide a failure.
    """
    if not isinstance(record, dict):
        return False
    outcome = record.get("outcome")
    return isinstance(outcome, str) and outcome.strip().casefold() == OUTCOME_FAILED


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"the field '{key}' is written twice")
        obj[key] = value
    return obj


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a number; a missing value is written with 'missing_reason'")


def _parse_float(literal: str) -> float:
    value = float(literal)
    if not math.isfinite(value):
        return value  # reported by the check as not finite
    try:
        unchanged = Decimal(literal) == Decimal(repr(value))
    except (InvalidOperation, ValueError):
        unchanged = False
    return value if unchanged else _ChangedNumber(value, literal)


def _parse_int(literal: str) -> int | float:
    try:
        return int(literal)
    except ValueError:  # more digits than Python converts
        return _ChangedNumber(float(literal), literal)


def _entries(directory: Path) -> list[Path]:
    return sorted(directory.iterdir())


def _read_json(path: Path) -> tuple[Any, str | None]:
    try:
        # utf-8-sig also reads a file that starts with a byte-order mark,
        # which editors on Windows write by default.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot be read as UTF-8 text: {exc}"
    try:
        record = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
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

    The extension of a record file is read without regard to case, so
    ``<id>.JSON`` is a record file too. Two files of one folder that carry
    the same id are both rejected.

    Raises ``TypeError``, and nothing else, when ``root`` is not a path.
    """
    try:
        root = Path(root)
    except TypeError:
        raise TypeError("load_store: 'root' must be a path, given as text or as a path object") from None
    accepted: dict[str, dict[str, dict]] = {kind: {} for kind in FOLDER_BY_KIND}
    paths: dict[tuple[str, str], str] = {}
    problems: list[tuple[str, str]] = []
    failed_malformed: list[str] = []

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
        for path in _entries(directory):
            relative = f"{folder}/{path.name}"
            if path.is_dir() or path.suffix.lower() != ".json":
                problems.append((relative, "is not a record: this folder holds only files named <id>.json"))
                continue
            record, error = _read_json(path)
            if error is not None:
                problems.append((relative, error))
                continue
            try:
                found = check_record(record, allow_placeholders=allow_placeholders)
            except RecursionError:
                found = [_TOO_DEEP]
            if isinstance(record, dict):
                record_kind = record.get("kind")
                if isinstance(record_kind, str) and record_kind in FOLDER_BY_KIND and record_kind != kind:
                    found.append(
                        f"kind: a '{record_kind}' record belongs in "
                        f"'{FOLDER_BY_KIND[record_kind]}/', not in '{folder}/'"
                    )
                record_id = record.get("id")
                if isinstance(record_id, str) and path.stem != record_id:
                    found.append(f"id: the file must be named '{record_id}.json'")
            if found:
                problems.extend((relative, message) for message in found)
                if _says_failed(record):
                    failed_malformed.append(relative)
                continue
            first = paths.get((kind, record["id"]))
            if first is not None:
                # Possible only where two file names differ in the case of
                # the extension. Neither file replaces the other.
                problems.append((relative, f"id: '{record['id']}' is also the id of '{first}'"))
                if _says_failed(record):
                    failed_malformed.append(relative)
                earlier = accepted[kind].pop(record["id"], None)
                if earlier is not None:
                    problems.append((first, f"id: '{record['id']}' is also the id of '{relative}'"))
                    if _says_failed(earlier):
                        failed_malformed.append(first)
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
        failed_malformed=tuple(sorted(failed_malformed)),
    )


# --- reporting ----------------------------------------------------------------


def _require_sound_store(store: Any) -> None:
    if not isinstance(store, Store):
        raise ValueError("summarise: needs a Store, as load_store returns it")
    for name, kind in (("runs", KIND_RUN), ("results", KIND_RESULT), ("unresolved", KIND_RESULT)):
        group = getattr(store, name)
        if not isinstance(group, dict):
            raise ValueError(f"summarise: store.{name} must be a dict of records by id")
        for key, record in group.items():
            if not isinstance(key, str) or _problems_as(record, kind):
                raise ValueError(
                    f"summarise: store.{name} holds, under the key {_shown(key)}, "
                    f"something that is not a well-formed '{kind}' record"
                )
    problems = store.problems
    if not isinstance(problems, (tuple, list)) or not all(
        isinstance(item, (tuple, list)) and len(item) == 2 and all(isinstance(part, str) for part in item)
        for item in problems
    ):
        raise ValueError("summarise: store.problems must be a sequence of (path, message) pairs of text")
    paths = store.failed_malformed
    if not isinstance(paths, (tuple, list)) or not all(isinstance(path, str) for path in paths):
        raise ValueError("summarise: store.failed_malformed must be a sequence of paths as text")


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

    A rejected file whose record says that its outcome is failed
    (``Store.failed_malformed``) is listed by path under ``failed_malformed``
    and is counted as failed too, so ``counts['failed']`` is the length of
    ``failed`` plus the length of ``failed_malformed``. Its run and its test
    are not trusted, so it does not remove a test from ``no_result``.

    ``results_total`` is the number of results counted under an outcome.

    Raises ``ValueError``, and nothing else, when ``store`` is not a store
    whose records are well-formed, as ``load_store`` returns it.
    """
    _require_sound_store(store)
    counts = {outcome: 0 for outcome in OUTCOMES}
    by_outcome: dict[str, list[str]] = {outcome: [] for outcome in OUTCOMES}
    reported: set[tuple[str, str]] = set()
    counted = list(store.results.items())
    counted += [item for item in store.unresolved.items() if item[1]["outcome"] == OUTCOME_FAILED]
    for result_id, result in counted:
        counts[result["outcome"]] += 1
        by_outcome[result["outcome"]].append(result_id)
        reported.add((result["run_id"], result["test_code"]))
    counts[OUTCOME_FAILED] += len(store.failed_malformed)
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
        "failed_malformed": sorted(store.failed_malformed),
        OUTCOME_NOT_EVALUATED: sorted(by_outcome[OUTCOME_NOT_EVALUATED]),
        "broken_references": [
            {"id": result_id, "outcome": result["outcome"]}
            for result_id, result in sorted(store.unresolved.items())
        ],
        "no_result": no_result,
        "rejected": sorted({path for path, _ in store.problems}),
    }
