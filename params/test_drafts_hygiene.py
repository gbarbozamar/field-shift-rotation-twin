"""Hygiene and layout checks across ``params/`` JSON files.

Dynamically audits ``params/examples/``, ``params/withdrawn/``, and
``params/records/`` without embedding raw parameter values or literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from params import catalogue

PARAMS_DIR = Path(__file__).parent
EXPECTED_FOLDERS = ("examples", "records", "withdrawn")

# Matches filesystem drive-letter paths (excluding URL schemes like https://)
# and common Windows/POSIX temporary or user-home directory markers.
TEMP_PATH_PATTERN = re.compile(
    r"(?:"
    r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]"
    r"|\\\\[A-Za-z0-9_.-]+\\"
    r"|/tmp/"
    r"|/var/folders/"
    r"|/Users/"
    r"|/home/"
    r"|[/\\]Users[/\\]"
    r"|AppData[/\\]Local[/\\]Temp"
    r")",
    re.IGNORECASE,
)


def _json_files(folder_name: str) -> list[Path]:
    folder = PARAMS_DIR / folder_name
    assert folder.is_dir(), f"missing expected params subfolder: {folder_name}"
    files = sorted(folder.rglob("*.json"))
    assert files, f"expected at least one .json file under params/{folder_name}/"
    return files


def _iter_strings(item: Any) -> list[str]:
    strings: list[str] = []
    pending = [item]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            strings.append(current)
        elif isinstance(current, dict):
            for key, value in current.items():
                if isinstance(key, str):
                    strings.append(key)
                pending.append(value)
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
    return strings


def _normalise_person(text: str) -> str:
    return " ".join(text.split()).casefold()


def test_no_drafts_folder_and_clean_params_layout() -> None:
    drafts = PARAMS_DIR / "drafts"
    assert not drafts.exists(), "params/drafts/ must not exist in the repository"
    subdirs = sorted(
        p.name for p in PARAMS_DIR.iterdir() if p.is_dir() and p.name != "__pycache__"
    )
    assert subdirs == sorted(EXPECTED_FOLDERS)
    assert catalogue.check_layout(PARAMS_DIR) == []


def test_all_params_json_files_are_valid_utf8_json_and_well_formed() -> None:
    for folder_name in EXPECTED_FOLDERS:
        for path in _json_files(folder_name):
            raw = path.read_text(encoding="utf-8")
            record = catalogue.parse_record_text(raw)
            assert isinstance(record, dict), path.relative_to(PARAMS_DIR).as_posix()
            problems = catalogue.check_record(record)
            assert problems == [], f"{path.relative_to(PARAMS_DIR).as_posix()}: {problems}"


def test_examples_retain_placeholder_markers() -> None:
    example_records: dict[str, Any] = {}
    for path in _json_files("examples"):
        raw = path.read_text(encoding="utf-8")
        assert catalogue.PLACEHOLDER_WORD in raw, path.name
        record = catalogue.parse_record_text(raw)
        assert catalogue.is_placeholder(record), path.name
        example_records[path.name] = record
    assert catalogue.check_catalogue(example_records) != []


def test_records_and_withdrawn_contain_no_placeholders() -> None:
    for folder_name in ("records", "withdrawn"):
        assert catalogue.check_folder(PARAMS_DIR / folder_name) == []
        for path in _json_files(folder_name):
            record = catalogue.parse_record_text(path.read_text(encoding="utf-8"))
            assert not catalogue.is_placeholder(record), (
                path.relative_to(PARAMS_DIR).as_posix()
            )


def test_no_email_addresses_in_params_json_files() -> None:
    for folder_name in EXPECTED_FOLDERS:
        for path in _json_files(folder_name):
            raw = path.read_text(encoding="utf-8")
            assert "@" not in raw, (
                f"unexpected '@' in {path.relative_to(PARAMS_DIR).as_posix()}"
            )


def test_no_temp_paths_in_examples_withdrawn_or_record_fields() -> None:
    for folder_name in ("examples", "withdrawn"):
        for path in _json_files(folder_name):
            record = catalogue.parse_record_text(path.read_text(encoding="utf-8"))
            for text in _iter_strings(record):
                match = TEMP_PATH_PATTERN.search(text)
                assert match is None, (
                    f"temp/local path marker {match.group(0)!r} in "
                    f"{path.relative_to(PARAMS_DIR).as_posix()}"
                )

    for path in _json_files("records"):
        record = catalogue.parse_record_text(path.read_text(encoding="utf-8"))
        # Provenance notes in records/ are audited separately from structured fields.
        non_note = {k: v for k, v in record.items() if k != "note"}
        for text in _iter_strings(non_note):
            match = TEMP_PATH_PATTERN.search(text)
            assert match is None, (
                f"temp/local path marker {match.group(0)!r} in "
                f"{path.relative_to(PARAMS_DIR).as_posix()}"
            )


def test_transcribed_by_and_checked_by_are_non_empty_and_distinct() -> None:
    for folder_name in EXPECTED_FOLDERS:
        for path in _json_files(folder_name):
            record = catalogue.parse_record_text(path.read_text(encoding="utf-8"))
            transcriber = record.get("transcribed_by")
            checker = record.get("checked_by")
            if transcriber is not None and checker is not None:
                assert isinstance(transcriber, str) and transcriber.strip()
                assert isinstance(checker, str) and checker.strip()
                assert _normalise_person(transcriber) != _normalise_person(checker), (
                    path.relative_to(PARAMS_DIR).as_posix()
                )


def test_withdrawn_is_completely_disjoint_from_records() -> None:
    records_dir = PARAMS_DIR / "records"
    withdrawn_dir = PARAMS_DIR / "withdrawn"

    record_paths = _json_files("records")
    withdrawn_paths = _json_files("withdrawn")

    record_rels = {p.relative_to(records_dir).as_posix() for p in record_paths}
    withdrawn_rels = {p.relative_to(withdrawn_dir).as_posix() for p in withdrawn_paths}
    assert record_rels.isdisjoint(withdrawn_rels)

    record_names = {p.name for p in record_paths}
    withdrawn_names = {p.name for p in withdrawn_paths}
    assert record_names.isdisjoint(withdrawn_names)

    record_identities = {
        catalogue.identity(catalogue.parse_record_text(p.read_text(encoding="utf-8")))
        for p in record_paths
    }
    withdrawn_identities = {
        catalogue.identity(catalogue.parse_record_text(p.read_text(encoding="utf-8")))
        for p in withdrawn_paths
    }
    assert record_identities.isdisjoint(withdrawn_identities)
