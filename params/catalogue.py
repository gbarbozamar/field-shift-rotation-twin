"""Record format of the parameter catalogue and the checks that enforce it.

The format is PROPOSED (blueprint section 3.7) and is described in
params/README.md. This module holds no parameter value.

Standard library only. Every check is a pure function over parsed JSON;
only ``load_folder``, ``check_folder`` and ``check_layout`` read files.

Unchecked input: every public function accepts any argument. A function
that returns problems reports a bad argument as a problem. The others
(``read_value``, ``read_range``, ``identity``, ``parse_record_text``)
raise ``ValueError`` and nothing else.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLACEHOLDER_WORD = "PLACEHOLDER"
CITATION_NEEDED = "CITATION NEEDED"

RECORDS_FOLDER = "records"
EXAMPLES_FOLDER = "examples"
RECORD_SUFFIX = ".json"
FOLDER_README = "README.md"

# PROPOSED: the keys a scope may use. Their vocabularies are OPEN.
SCOPE_KEYS = ("crop", "stage", "management", "soil", "region")

REQUIRED_FIELDS = (
    "id",
    "scope",
    "value",
    "unit",
    "range",
    "citation",
    "transcribed_by",
    "checked_by",
)
OPTIONAL_FIELDS = ("value_missing_reason", "range_missing_reason", "note")
RANGE_FIELDS = ("low", "high", "basis")
CITATION_REQUIRED_FIELDS = ("reference", "locator")
CITATION_OPTIONAL_FIELDS = ("url",)

_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_NOT_A_MAPPING = "the records are not a mapping from a name to a record"


@dataclass(frozen=True)
class Missing:
    """A value that is absent, with the reason why.

    It is not a number: it has no numeric conversion, it does not compare
    equal to zero and arithmetic on it raises ``TypeError``.
    """

    reason: str


# --- small predicates -------------------------------------------------------


def _is_text(item: Any) -> bool:
    return isinstance(item, str) and item.strip() != ""


def _is_number(item: Any) -> bool:
    if isinstance(item, bool):
        return False
    if isinstance(item, int):
        return True
    return isinstance(item, float) and math.isfinite(item)


def _reads_back_unchanged(number: int | float) -> bool:
    """False for an integer that a float cannot hold exactly."""
    try:
        return float(number) == number
    except OverflowError:
        return False


def _normalise(text: str) -> str:
    """Collapse whitespace and ignore case, for comparisons only."""
    return " ".join(text.split()).casefold()


# --- one record -------------------------------------------------------------


def check_record(record: Any) -> list[str]:
    """Return the problems of one record. An empty list means well-formed."""
    if not isinstance(record, dict):
        return ["the record is not a JSON object"]

    problems: list[str] = []
    allowed = REQUIRED_FIELDS + OPTIONAL_FIELDS
    for key in record:
        if key not in allowed:
            problems.append(f"unknown field '{key}'")
    for key in REQUIRED_FIELDS:
        if key not in record:
            problems.append(f"required field '{key}' is absent")

    if "id" in record:
        problems += _check_id(record["id"])
    if "scope" in record:
        problems += _check_scope(record["scope"])
    if "unit" in record and not _is_text(record["unit"]):
        problems.append("'unit' must be a non-empty string")
    if "note" in record and not _is_text(record["note"]):
        problems.append("'note', when given, must be a non-empty string")

    problems += _check_value(record)
    problems += _check_range(record)
    problems += _check_citation(record)
    problems += _check_persons(record)
    return problems


def _check_id(item: Any) -> list[str]:
    if not isinstance(item, str) or not _ID_PATTERN.fullmatch(item):
        return ["'id' must start with a letter and use only letters, digits and '_'"]
    return []


def _check_scope(scope: Any) -> list[str]:
    if not isinstance(scope, dict):
        return ["'scope' must be a JSON object (use {} when there is no restriction)"]
    problems = []
    for key, item in scope.items():
        if key not in SCOPE_KEYS:
            problems.append(f"unknown scope key '{key}'")
        elif not _is_text(item):
            problems.append(f"scope key '{key}' must hold a non-empty string")
    return problems


def _check_reason(record: dict, field: str, is_missing: bool) -> list[str]:
    """A reason is required when the thing is missing and forbidden otherwise.

    Forbidden means the reason field is not there at all, not even as null.
    """
    reason_field = f"{field}_missing_reason"
    if is_missing and not _is_text(record.get(reason_field)):
        return [f"'{field}' is missing without a reason: '{reason_field}' is required"]
    if not is_missing and reason_field in record:
        return [f"'{field}' is given together with '{reason_field}': keep only one"]
    return []


def _check_number(number: Any, name: str) -> list[str]:
    if not _is_number(number):
        return [f"'{name}' must be a finite number"]
    if not _reads_back_unchanged(number):
        return [f"'{name}' cannot be read back unchanged as a number"]
    return []


def _check_value(record: dict) -> list[str]:
    if "value" not in record:
        return []
    value = record["value"]
    problems = _check_reason(record, "value", is_missing=value is None)
    if value is None:
        return problems
    if not _is_number(value):
        return problems + ["'value' must be a finite number, or null with a reason"]
    return problems + _check_number(value, "value")


def _check_range(record: dict) -> list[str]:
    if "range" not in record:
        return []
    range_ = record["range"]
    problems = _check_reason(record, "range", is_missing=range_ is None)
    if range_ is None:
        return problems
    if not isinstance(range_, dict):
        return problems + ["'range' must be a JSON object, or null with a reason"]

    for key in range_:
        if key not in RANGE_FIELDS:
            problems.append(f"unknown field 'range.{key}'")
    for key in ("low", "high"):
        problems += _check_number(range_.get(key), f"range.{key}")
    if not _is_text(range_.get("basis")):
        problems.append("'range.basis' must say what the range represents")

    low, high = range_.get("low"), range_.get("high")
    if _is_number(low) and _is_number(high):
        if low > high:
            problems.append("'range.low' is greater than 'range.high'")
        elif _is_number(record.get("value")) and not low <= record["value"] <= high:
            problems.append("'value' lies outside its own range")
    return problems


def _check_citation(record: dict) -> list[str]:
    if "citation" not in record:
        return []
    citation = record["citation"]
    if citation is None:
        # PROPOSED: no citation only when there is no number to cite.
        if "value" not in record or record["value"] is not None:
            return ["a record with a value needs a citation"]
        # A range that is not an object is reported by the range check alone.
        if isinstance(record.get("range"), dict):
            return [
                "a range needs a citation: 'citation' may be null only when "
                "'value' and 'range' are both null"
            ]
        return []
    if not isinstance(citation, dict):
        return ["'citation' must be a JSON object"]

    problems = []
    for key in citation:
        if key not in CITATION_REQUIRED_FIELDS + CITATION_OPTIONAL_FIELDS:
            problems.append(f"unknown field 'citation.{key}'")
    for key in CITATION_REQUIRED_FIELDS:
        if not _is_text(citation.get(key)):
            problems.append(f"'citation.{key}' must be a non-empty string")
    for key in CITATION_OPTIONAL_FIELDS:
        if key in citation and not _is_text(citation[key]):
            problems.append(f"'citation.{key}', when given, must be a non-empty string")
    for key, item in citation.items():
        if isinstance(item, str) and _normalise(CITATION_NEEDED) in _normalise(item):
            problems.append(f"'citation.{key}' says {CITATION_NEEDED}: that is not a citation")
    return problems


def _check_persons(record: dict) -> list[str]:
    problems = []
    for key in ("transcribed_by", "checked_by"):
        if key in record and not _is_text(record[key]):
            problems.append(f"'{key}' must be a non-empty string")
    transcriber, checker = record.get("transcribed_by"), record.get("checked_by")
    if _is_text(transcriber) and _is_text(checker):
        if _normalise(transcriber) == _normalise(checker):
            problems.append("'transcribed_by' and 'checked_by' are the same person")
    return problems


# --- reading a checked record ----------------------------------------------


def _require_a_parameter(record: Any) -> None:
    problems = check_record(record)
    if problems:
        raise ValueError("malformed parameter record: " + "; ".join(problems))
    if is_placeholder(record):
        raise ValueError(
            f"the record contains the word {PLACEHOLDER_WORD}: "
            "it is an example, not a parameter, and is not read"
        )


def read_value(record: Any) -> float | Missing:
    """Return the value of a parameter record, or ``Missing`` with its reason.

    A missing value is never turned into a number. Raises ``ValueError``,
    and nothing else, when the record is malformed or is a placeholder.
    """
    _require_a_parameter(record)
    if record["value"] is None:
        return Missing(record["value_missing_reason"])
    return float(record["value"])


def read_range(record: Any) -> tuple[float, float] | Missing:
    """Return ``(low, high)`` of a parameter record, or ``Missing``.

    Raises ``ValueError``, and nothing else, when the record is malformed
    or is a placeholder.
    """
    _require_a_parameter(record)
    if record["range"] is None:
        return Missing(record["range_missing_reason"])
    return float(record["range"]["low"]), float(record["range"]["high"])


# --- a set of records -------------------------------------------------------


def is_placeholder(item: Any) -> bool:
    """True when the word PLACEHOLDER appears in any text of the item.

    Accepts anything. Looks inside objects, their keys and lists, however
    deep, and stops at an item that contains itself.
    """
    word = PLACEHOLDER_WORD.casefold()
    pending = [item]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if word in current.casefold():
                return True
        elif isinstance(current, (dict, list, tuple)):
            if id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, dict):
                pending.extend(current.keys())
                pending.extend(current.values())
            else:
                pending.extend(current)
    return False


def _has_identity(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    return not (_check_id(record.get("id")) or _check_scope(record.get("scope")))


def identity(record: Any) -> tuple[str, tuple[tuple[str, str], ...]]:
    """What makes a record unique: its identifier and its scope.

    Case and whitespace are ignored; the order of the scope keys does not
    matter. Raises ``ValueError``, and nothing else, when the record has no
    well-formed 'id' and 'scope'.
    """
    if not _has_identity(record):
        raise ValueError("the record has no well-formed 'id' and 'scope'")
    scope = tuple(sorted((key, _normalise(item)) for key, item in record["scope"].items()))
    return record["id"].casefold(), scope


def _named(records: Any) -> list[tuple[str, Any]] | None:
    """The records as (name, record) pairs in a stable order, or None."""
    if not isinstance(records, dict):
        return None
    return sorted(((str(name), record) for name, record in records.items()), key=lambda p: p[0])


def _duplicates(named: list[tuple[str, Any]]) -> tuple[list[str], list[str]]:
    """Problems of shared identity, and the names that could not be compared."""
    groups: dict[Any, list[str]] = {}
    not_compared = []
    for name, record in named:
        if _has_identity(record):
            groups.setdefault(identity(record), []).append(name)
        else:
            not_compared.append(name)
    problems = [
        f"same 'id' and 'scope' in: {', '.join(names)}"
        for names in groups.values()
        if len(names) > 1
    ]
    return problems, not_compared


def find_duplicates(records: Any) -> list[str]:
    """Report every group of records that share identifier and scope.

    A record without a well-formed 'id' and 'scope' cannot be compared:
    it is reported, not skipped.
    """
    named = _named(records)
    if named is None:
        return [_NOT_A_MAPPING]
    problems, not_compared = _duplicates(named)
    return problems + [
        f"{name}: cannot be compared with the others: its 'id' or 'scope' is malformed"
        for name in not_compared
    ]


def find_placeholders(records: Any) -> list[str]:
    """Report every record that carries the word PLACEHOLDER."""
    named = _named(records)
    if named is None:
        return [_NOT_A_MAPPING]
    return [
        f"{name}: contains the word {PLACEHOLDER_WORD}, so it is not a parameter"
        for name, record in named
        if is_placeholder(record)
    ]


def check_catalogue(records: Any) -> list[str]:
    """Return the problems of a set of records, keyed by a name such as a path.

    Each record must be well-formed, no two may share identifier and scope,
    and none may be a placeholder.
    """
    named = _named(records)
    if named is None:
        return [_NOT_A_MAPPING]
    problems = []
    for name, record in named:
        problems += [f"{name}: {problem}" for problem in check_record(record)]
    # A record that cannot be compared is malformed, so it is reported above.
    problems += _duplicates(named)[0]
    problems += find_placeholders(records)
    return problems


# --- files ------------------------------------------------------------------


def parse_record_text(text: Any) -> Any:
    """Parse the text of one record file.

    Stricter than plain JSON in two ways: a repeated key and the constants
    NaN and Infinity are errors, because each would let a value change
    silently. Numbers are read as JSON readers do: an integer exactly, a
    number with a fraction or an exponent as the nearest float.

    Raises ``ValueError``, and nothing else, when the text is unusable.
    """
    if not isinstance(text, str):
        raise ValueError("the content of a record file must be text")

    def reject_repeated_keys(pairs: list[tuple[str, Any]]) -> dict:
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"repeated key(s): {', '.join(repeated)}")
        return dict(pairs)

    def reject_constant(name: str) -> Any:
        raise ValueError(f"'{name}' is not a number that a record may hold")

    try:
        return json.loads(
            text, object_pairs_hook=reject_repeated_keys, parse_constant=reject_constant
        )
    except RecursionError:
        raise ValueError("the content is nested too deeply") from None


def _as_folder(folder: Any) -> tuple[Path | None, list[str]]:
    if not isinstance(folder, (str, os.PathLike)) or folder == "":
        return None, ["the folder is not given as a path"]
    try:
        path = Path(folder)
    except TypeError:
        return None, ["the folder is not given as a path"]
    if not path.is_dir():
        return None, [f"{path.name}: the folder does not exist"]
    return path, []


def _walk(folder: Path) -> tuple[list[Path], list[Path], list[str]]:
    """Every file and every subfolder under ``folder``, in a stable order."""
    files: list[Path] = []
    subfolders: list[Path] = []
    failures: list[OSError] = []
    for current, folder_names, file_names in os.walk(folder, onerror=failures.append):
        folder_names.sort()
        subfolders += [Path(current, name) for name in folder_names]
        files += [Path(current, name) for name in sorted(file_names)]
    problems = [
        f"{Path(failure.filename or folder).name}: the folder cannot be listed"
        for failure in failures
    ]
    return files, subfolders, problems


def load_folder(folder: Any) -> tuple[dict[str, Any], list[str]]:
    """Read every file under ``folder``, one record per ``.json`` file.

    Returns the records keyed by their path relative to ``folder``, and
    the problems found while reading. Nothing is skipped without a
    message, except the ``README.md`` at the top of ``folder``: a file
    that is not a ``.json`` file, a file that cannot be read as a record
    and a subfolder whose name ends in ``.json`` are each a problem, and
    the rest still loads.
    """
    folder, problems = _as_folder(folder)
    if folder is None:
        return {}, problems
    files, subfolders, problems = _walk(folder)
    for path in subfolders:
        if path.suffix == RECORD_SUFFIX:
            name = path.relative_to(folder).as_posix()
            problems.append(f"{name}: a folder, not a record file")

    records: dict[str, Any] = {}
    for path in files:
        name = path.relative_to(folder).as_posix()
        if name == FOLDER_README:
            continue
        if path.suffix != RECORD_SUFFIX:
            problems.append(f"{name}: not a {RECORD_SUFFIX} record file")
            continue
        try:
            records[name] = parse_record_text(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:  # ValueError covers JSON and encoding
            problems.append(f"{name}: not a readable record file ({error})")
    return records, problems


def check_folder(folder: Any) -> list[str]:
    """Return every problem of the catalogue stored under ``folder``."""
    records, problems = load_folder(folder)
    return problems + check_catalogue(records)


def check_layout(params_folder: Any) -> list[str]:
    """Return every problem of the whole ``params/`` folder.

    The catalogue under ``records/`` is checked with ``check_folder``, and
    its problems name each file relative to ``records/``. A ``.json`` file
    anywhere else, other than under ``examples/``, is reported with its
    path relative to ``params/``: it would never be checked or read.
    """
    root, problems = _as_folder(params_folder)
    if root is None:
        return problems
    files, _, problems = _walk(root)
    for path in files:
        relative = path.relative_to(root)
        if path.suffix.lower() != RECORD_SUFFIX:
            continue
        if relative.parts[0] in (RECORDS_FOLDER, EXAMPLES_FOLDER) and len(relative.parts) > 1:
            continue
        problems.append(
            f"{relative.as_posix()}: a record file outside {RECORDS_FOLDER}/ "
            f"and {EXAMPLES_FOLDER}/"
        )
    return problems + check_folder(root / RECORDS_FOLDER)
