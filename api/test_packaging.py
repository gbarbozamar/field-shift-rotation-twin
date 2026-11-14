"""One import path for the contract models (decision Q1 of contracts/ENTRYPOINTS.md).

Under pytest, a contract folder without ``contracts/__init__.py`` above it is
also loaded under its own name (``inputs``, ``results``), so the same class
exists twice. This test fails if that double identity returns once
``contracts/__init__.py`` exists. Lane L0 lands that file (issue #71); until
then the test is skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_FILE = Path(__file__).parent.parent / "contracts" / "__init__.py"


@pytest.mark.skipif(
    not PACKAGE_FILE.exists(),
    reason="contracts/__init__.py is not on this branch yet (lane L0, issue #71)",
)
def test_contract_models_load_under_one_name_only():
    import contracts.inputs
    import contracts.results
    import contracts.rotation_definition  # noqa: F401

    for short in ("inputs", "results", "rotation_definition"):
        assert short not in sys.modules, f"{short!r} is loaded under a second name"
