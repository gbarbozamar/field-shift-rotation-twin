"""Frontend dependency licence check.

Reads ``web/package-lock.json``, which records the licence of every npm
package, and fails when a package carries no licence or one that is not in
``ci/allowed_frontend_licences.txt``. Licence expressions are read by
``ci.licences.is_allowed``. Standard library only: no new dependency.

Without a lockfile (a checkout without ``web/``) the check is skipped with a
notice.

Run from the repository root::

    uv run python -m ci.frontend_licences [path/to/package-lock.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ci.licences import is_allowed, read_allowed

ALLOWED_FILE = Path(__file__).parent / "allowed_frontend_licences.txt"
LOCKFILE = Path("web") / "package-lock.json"


def find_problems(lock: dict, allowed: set[str]) -> tuple[list[str], int]:
    """One line per package whose licence is absent or not acceptable, and
    the number of packages checked. The root entry (``""``) is the project
    itself and is not checked."""
    problems = []
    checked = 0
    for path, package in lock.get("packages", {}).items():
        if path == "":
            continue
        checked += 1
        version = package.get("version", "?")
        licence = package.get("license")
        if not isinstance(licence, str) or not licence.strip():
            problems.append(f"{path} {version}: no licence recorded")
        elif not is_allowed(licence, allowed):
            problems.append(f"{path} {version}: licence '{licence}' is not allowed")
    return sorted(problems), checked


def main(lockfile: Path = LOCKFILE, allowed_file: Path = ALLOWED_FILE) -> int:
    if not lockfile.is_file():
        print(f"::notice::Frontend licence check skipped: {lockfile} does not exist")
        return 0
    lock = json.loads(lockfile.read_text(encoding="utf-8"))
    problems, checked = find_problems(lock, read_allowed(allowed_file))
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} package(s) with a licence outside {allowed_file.name}")
        return 1
    print(f"{checked} packages checked: every licence is allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else LOCKFILE))
