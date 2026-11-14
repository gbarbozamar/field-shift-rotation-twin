"""Dependency licence check.

Reads the JSON report of ``pip-licenses`` and fails when an installed package
carries a licence that is not in ``ci/allowed_licences.txt``.

Run from the repository root::

    uv run pip-licenses --with-system --format=json | uv run python -m ci.licences
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED_FILE = Path(__file__).parent / "allowed_licences.txt"


def read_allowed(path: Path = ALLOWED_FILE) -> set[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def is_allowed(licence: str, allowed: set[str]) -> bool:
    """Whether a licence string as reported by package metadata is acceptable.

    ``A OR B`` is acceptable when one side is. ``A AND B`` and ``A; B``
    (several licences declared together) need every part. An empty or
    unknown licence is never acceptable.
    """
    text = licence.strip()
    if text in allowed:
        return True
    if text.startswith("(") and text.endswith(")"):
        return is_allowed(text[1:-1], allowed)
    for separator, combine in ((";", all), (r"\s+AND\s+", all), (r"\s+OR\s+", any)):
        parts = [part for part in re.split(separator, text) if part.strip()]
        if len(parts) > 1:
            return combine(is_allowed(part, allowed) for part in parts)
    return False


def find_problems(packages: list[dict], allowed: set[str]) -> list[str]:
    """One line per package whose licence is not acceptable."""
    problems = []
    for package in packages:
        licence = str(package.get("License", ""))
        if not is_allowed(licence, allowed):
            name, version = package.get("Name", "?"), package.get("Version", "?")
            problems.append(f"{name} {version}: licence '{licence}' is not allowed")
    return sorted(problems)


def main() -> int:
    packages = json.load(sys.stdin)
    problems = find_problems(packages, read_allowed())
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} package(s) with a licence outside {ALLOWED_FILE.name}")
        return 1
    print(f"{len(packages)} packages checked: every licence is allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
