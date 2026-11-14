"""Each CI check is shown to fail on a planted case.

Run with ``uv run pytest ci/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7): the platform developer
approves them. Every planted item is made up at run time in a temporary
folder; nothing planted is stored in the repository.

Checks without a planted case yet, both OPEN:

- frontend build: needs ``web/``;
- contract validation: needs ``contracts/`` and the agreed command.
"""

from __future__ import annotations

import os
import random
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

from ci import licences, names_scan

ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITLEAKS_IMAGE = "ghcr.io/gitleaks/gitleaks:v8.21.2"

# A made-up word that stands for a forbidden name. It is not a real name.
PLANTED_NAME = "Zorvexia"


# --- check 1: tests -------------------------------------------------------


def test_tests_check_fails_on_a_failing_test(tmp_path):
    planted = tmp_path / "test_planted.py"
    planted.write_text("def test_planted():\n    assert 1 == 2\n")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(planted)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 1


# --- check 4: secret scan -------------------------------------------------


def planted_secret() -> str:
    """A string with the shape of a cloud access key, built at run time."""
    rng = random.Random(7)
    body = "".join(rng.choice(string.ascii_uppercase + "234567") for _ in range(16))
    return "AK" + "IA" + body


def gitleaks(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{folder}:/scan:ro",
            GITLEAKS_IMAGE, "dir", "/scan", "--redact", "--no-banner",
        ],
        capture_output=True,
        check=False,
    )  # fmt: skip


@pytest.fixture
def scan_folder(tmp_path):
    if shutil.which("docker") is None:
        if os.environ.get("CI"):
            pytest.fail("docker is required in CI for the secret scan")
        pytest.skip("docker is not available on this machine")
    tmp_path.chmod(0o755)
    return tmp_path


def test_secret_scan_fails_on_a_planted_key(scan_folder):
    (scan_folder / "settings.py").write_text(
        f'aws_access_key_id = "{planted_secret()}"\n'
    )
    assert gitleaks(scan_folder).returncode == 1


def test_secret_scan_passes_on_a_clean_folder(scan_folder):
    (scan_folder / "settings.py").write_text('region = "PLACEHOLDER"\n')
    assert gitleaks(scan_folder).returncode == 0


def test_workflow_uses_the_scanner_tested_here():
    assert GITLEAKS_IMAGE in WORKFLOW.read_text(encoding="utf-8")


# --- check 5: names scan --------------------------------------------------


def make_repo(folder: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(folder), "add", "-A"], check=True)
    return folder


def run_scan(repo: Path, names: str | None, monkeypatch, capsys) -> tuple[int, str]:
    if names is None:
        monkeypatch.delenv(names_scan.ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(names_scan.ENV_VAR, names)
    code = names_scan.main(repo)
    return code, capsys.readouterr().out


def test_names_scan_fails_on_a_planted_name(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"notes.md": f"line one\nbuilt for {PLANTED_NAME}\n"})
    code, out = run_scan(repo, PLANTED_NAME, monkeypatch, capsys)
    assert code == 1
    assert "notes.md:2" in out


def test_names_scan_never_prints_the_name(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"notes.md": f"built for {PLANTED_NAME}\n"})
    _, out = run_scan(repo, PLANTED_NAME, monkeypatch, capsys)
    assert PLANTED_NAME.casefold() not in out.casefold()


def test_names_scan_ignores_case(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"a.txt": f"{PLANTED_NAME.upper()} inside\n"})
    code, _ = run_scan(repo, PLANTED_NAME.lower(), monkeypatch, capsys)
    assert code == 1


def test_names_scan_reads_file_names(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {f"docs/{PLANTED_NAME.lower()}-plan.md": "clean\n"})
    code, out = run_scan(repo, PLANTED_NAME, monkeypatch, capsys)
    assert code == 1
    assert "in the file name" in out


def test_names_scan_matches_whole_words_only(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"a.txt": f"pre{PLANTED_NAME}post is another word\n"})
    code, _ = run_scan(repo, PLANTED_NAME, monkeypatch, capsys)
    assert code == 0


def test_names_scan_reads_only_tracked_files(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"a.txt": "clean\n"})
    (repo / "untracked.txt").write_text(f"{PLANTED_NAME}\n")
    code, _ = run_scan(repo, PLANTED_NAME, monkeypatch, capsys)
    assert code == 0


def test_names_scan_passes_on_a_clean_repository(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path, {"a.txt": "nothing to see\n"})
    code, out = run_scan(
        repo, f"{PLANTED_NAME}\nAnother Planted Name", monkeypatch, capsys
    )
    assert code == 0
    assert "2 name(s) checked" in out


@pytest.mark.parametrize("value", [None, "", "  \n\n "])
def test_names_scan_without_a_list_is_skipped_with_a_notice(
    value, tmp_path, monkeypatch, capsys
):
    repo = make_repo(tmp_path, {"a.txt": f"{PLANTED_NAME}\n"})
    code, out = run_scan(repo, value, monkeypatch, capsys)
    assert code == 0
    assert "::notice::Names scan skipped" in out


def test_parse_names_drops_blanks_and_duplicates():
    assert names_scan.parse_names(" A b \n\na B\nc\n") == ["a b", "c"]


# --- check 6: dependency licences -----------------------------------------

ALLOWED = {"MIT", "BSD-3-Clause", "Mozilla Public License 2.0 (MPL 2.0)"}


def package(licence: str) -> dict:
    return {"Name": "placeholder-package", "Version": "0.0.0", "License": licence}


@pytest.mark.parametrize(
    "licence",
    [
        "PLACEHOLDER licence that is not on the list",
        "UNKNOWN",
        "",
        "MIT AND PLACEHOLDER licence that is not on the list",
        "MIT; PLACEHOLDER licence that is not on the list",
    ],
)
def test_licence_check_fails_on_a_planted_licence(licence):
    problems = licences.find_problems([package("MIT"), package(licence)], ALLOWED)
    assert len(problems) == 1
    assert "placeholder-package 0.0.0" in problems[0]


@pytest.mark.parametrize(
    "licence",
    [
        "MIT",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "MIT OR PLACEHOLDER licence that is not on the list",
        "(MIT OR BSD-3-Clause)",
        "MIT AND BSD-3-Clause",
        "MIT; BSD-3-Clause",
    ],
)
def test_licence_check_accepts_an_allowed_licence(licence):
    assert licences.find_problems([package(licence)], ALLOWED) == []


def test_allowed_list_is_read_without_comments():
    allowed = licences.read_allowed()
    assert allowed
    assert not any(entry.startswith("#") for entry in allowed)
