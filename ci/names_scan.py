"""Scan for forbidden names.

The list of forbidden names (companies, products, persons) is **not** in the
repository: in plain text it would itself be the leak. It arrives in the
environment variable ``FORBIDDEN_NAMES``, one name per line, filled from the
CI host's secret storage.

The scan reads every file tracked by git and fails when a name appears as a
whole word, ignoring case. The report gives the file and the line, never the
name that was found.

Run from the repository root::

    FORBIDDEN_NAMES="$(cat list.txt)" uv run python -m ci.names_scan

Exit codes: 0 clean, 1 a name was found, 0 with a notice when no list was
supplied (for example on a pull request from a fork, where secrets are not
available).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ENV_VAR = "FORBIDDEN_NAMES"


def parse_names(value: str | None) -> list[str]:
    """Names from the secret: one per line, blanks and duplicates dropped."""
    if not value:
        return []
    seen: dict[str, None] = {}
    for line in value.splitlines():
        name = line.strip()
        if name:
            seen.setdefault(name.casefold(), None)
    return list(seen)


def build_pattern(names: list[str]) -> re.Pattern[str]:
    """Match any name as a whole word, ignoring case."""
    alternatives = "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True)
    )
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def scan_text(text: str, pattern: re.Pattern[str]) -> list[int]:
    """Line numbers (from 1) where a forbidden name appears."""
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def tracked_files(root: Path) -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode()
    return [root / name for name in listing.split("\0") if name]


def scan_files(files: list[Path], root: Path, names: list[str]) -> list[str]:
    """``path:line`` for every hit, in file names and in file contents."""
    pattern = build_pattern(names)
    hits = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if pattern.search(relative):
            hits.append(f"{relative}: in the file name")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing to read as text
        hits.extend(f"{relative}:{number}" for number in scan_text(text, pattern))
    return hits


def main(root: Path | None = None) -> int:
    root = root or Path.cwd()
    names = parse_names(os.environ.get(ENV_VAR))
    if not names:
        print(f"::notice::Names scan skipped: {ENV_VAR} is empty or not available here")
        return 0
    hits = scan_files(tracked_files(root), root, names)
    for hit in hits:
        print(f"::error::Forbidden name at {hit}")
    if hits:
        print(f"{len(hits)} place(s) with a forbidden name. The name is not printed.")
        return 1
    print(f"Names scan clean: {len(names)} name(s) checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
