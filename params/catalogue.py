"""Record format of the parameter catalogue and the checks that enforce it.

The format is PROPOSED (blueprint section 3.7) and is described in
params/README.md. This module holds no parameter value.

Standard library only. Every check is a pure function over parsed JSON;
only ``load_folder`` and ``check_folder`` read files.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLACEHOLDER_WORD = "PLACEHOLDER"
CITATION_NEEDED = "CITATION NEEDED"

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
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        return False
    return math.isfinite(item)


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
    """A reason is required when the thing is missing and forbidden otherwise."""
    reason_field = f"{field}_missing_reason"
    reason = record.get(reason_field)
    if is_missing and not _is_text(reason):
        return [f"'{field}' is missing without a reason: '{reason_field}' is required"]
    if not is_missing and reason is not None:
        return [f"'{field}' is given together with '{reason_field}': keep only one"]
    return []


def _check_value(record: dict) -> list[str]:
    if "value" not in record:
        return []
    value = record["value"]
    problems = _check_reason(record, "value", is_missing=value is None)
    if value is not None and not _is_number(value):
        problems.append("'value' must be a finite number, or null with a reason")
    return problems


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
        if not _is_number(range_.get(key)):
            problems.append(f"'range.{key}' must be a finite number")
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
        # PROPOSED: only a record whose value is missing may have no citation.
        if record.get("value") is None and "value" in record:
            return []
        return ["a record with a value needs a citation"]
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


def _require_well_formed(record: Any) -> None:
    problems = check_record(record)
    if problems:
        raise ValueError("malformed parameter record: " + "; ".join(problems))


def read_value(record: Any) -> float | Missing:
    """Return the value of a well-formed record, or ``Missing`` with its reason.

    A missing value is never turned into a number. A malformed record
    raises ``ValueError``.
    """
    _require_well_formed(record)
    if record["value"] is None:
        return Missing(record["value_missing_reason"])
    return float(record["value"])


def read_range(record: Any) -> tuple[float, float] | Missing:
    """Return ``(low, high)`` of a well-formed record, or ``Missing``."""
    _require_well_formed(record)
    if record["range"] is None:
        return Missing(record["range_missing_reason"])
    return float(record["range"]["low"]), float(record["range"]["high"])


# --- a set of records -------------------------------------------------------


def is_placeholder(item: Any) -> bool:
    """True when the word PLACEHOLDER appears anywhere in the item."""
    if isinstance(item, str):
        return PLACEHOLDER_WORD.casefold() in item.casefold()
    if isinstance(item, dict):
        return any(is_placeholder(k) or is_placeholder(v) for k, v in item.items())
    if isinstance(item, list):
        return any(is_placeholder(v) for v in item)
    return False


def identity(record: dict) -> tuple[str, tuple[tuple[str, str], ...]]:
    """What makes a record unique: its identifier and its scope.

    Case and whitespace are ignored; the order of the scope keys does not
    matter. Call it only on a record whose 'id' and 'scope' are well-formed.
    """
    scope = tuple(sorted((key, _normalise(item)) for key, item in record["scope"].items()))
    return record["id"].casefold(), scope


def find_duplicates(records: dict[str, Any]) -> list[str]:
    """Report every group of records that share identifier and scope."""
    groups: dict[Any, list[str]] = {}
    for name in sorted(records):
        record = records[name]
        if not isinstance(record, dict):
            continue
        if _check_id(record.get("id")) or _check_scope(record.get("scope")):
            continue
        groups.setdefault(identity(record), []).append(name)
    return [
        f"same 'id' and 'scope' in: {', '.join(names)}"
        for names in groups.values()
        if len(names) > 1
    ]


def find_placeholders(records: dict[str, Any]) -> list[str]:
    """Report every record that carries the word PLACEHOLDER."""
    return [
        f"{name}: contains the word {PLACEHOLDER_WORD}, so it is not a parameter"
        for name in sorted(records)
        if is_placeholder(records[name])
    ]


def check_catalogue(records: dict[str, Any]) -> list[str]:
    """Return the problems of a set of records, keyed by a name such as a path.

    Each record must be well-formed, no two may share identifier and scope,
    and none may be a placeholder.
    """
    problems = []
    for name in sorted(records):
        problems += [f"{name}: {problem}" for problem in check_record(records[name])]
    problems += find_duplicates(records)
    problems += find_placeholders(records)
    return problems


# --- files ------------------------------------------------------------------


def parse_record_text(text: str) -> Any:
    """Parse the text of one record file. Raises ``ValueError`` when unusable.

    Stricter than plain JSON: a repeated key and the constants NaN and
    Infinity are errors, because each would let a value change silently.
    """

    def reject_repeated_keys(pairs: list[tuple[str, Any]]) -> dict:
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"repeated key(s): {', '.join(repeated)}")
        return dict(pairs)

    def reject_constant(name: str) -> Any:
        raise ValueError(f"'{name}' is not a number that a record may hold")

    return json.loads(
        text, object_pairs_hook=reject_repeated_keys, parse_constant=reject_constant
    )


def load_folder(folder: Path) -> tuple[dict[str, Any], list[str]]:
    """Read every ``*.json`` file under ``folder``, one record per file.

    Returns the records keyed by their path relative to ``folder``, and
    the problems of the files that could not be read as a record.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return {}, [f"{folder.name}: the folder does not exist"]
    records: dict[str, Any] = {}
    problems: list[str] = []
    for path in sorted(folder.rglob("*.json")):
        name = path.relative_to(folder).as_posix()
        try:
            records[name] = parse_record_text(path.read_text(encoding="utf-8"))
        except ValueError as error:  # includes JSON and encoding errors
            problems.append(f"{name}: not a readable record file ({error})")
    return records, problems


def check_folder(folder: Path) -> list[str]:
    """Return every problem of the catalogue stored under ``folder``."""
    records, problems = load_folder(folder)
    return problems + check_catalogue(records)
