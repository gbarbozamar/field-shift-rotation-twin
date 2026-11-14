"""Acceptance test of the rules of the unit brief (issue #113) for engine/water/et0/.

Run with ``python -m pytest engine/water/et0/`` from the repository root.
The cases are PROPOSED (blueprint section 3.7) and are listed with the same
codes in engine/water/et0/README.md under "PROPOSED cases".
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from pathlib import Path

import pytest

from engine.water.et0 import constants as constants_module
from engine.water.et0 import daily, equations, quantities
from engine.water.et0.constants import Et0Constants

HERE = Path(__file__).resolve().parent
MODULES = sorted(p for p in HERE.glob("*.py") if not p.name.startswith("test_"))
TESTS = sorted(HERE.glob("test_*.py"))
README = (HERE / "README.md").read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.M | re.S)
    assert match, f"README has no section '{title}'"
    return match.group(1)


def _constant_identifiers() -> set[str]:
    # The module uses postponed annotations: a field type is the class name.
    return {
        f"{group.name}.{item.name}"
        for group in dataclasses.fields(Et0Constants)
        for item in dataclasses.fields(getattr(constants_module, group.type))
    }


# --- R1: no number in the modules ---


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_r1_a_module_holds_no_number(path):
    numbers = [
        node.value
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    ]
    assert numbers == []


# --- R2: no default for any constant or argument ---


def test_r2_no_constant_has_a_default():
    classes = [
        value
        for value in vars(constants_module).values()
        if dataclasses.is_dataclass(value) and isinstance(value, type)
    ]
    assert len(classes) == len(dataclasses.fields(Et0Constants)) + 1
    for cls in classes:
        for item in dataclasses.fields(cls):
            assert item.default is dataclasses.MISSING, f"{cls.__name__}.{item.name}"
            assert item.default_factory is dataclasses.MISSING


@pytest.mark.parametrize(
    "module", [equations, quantities, daily], ids=lambda m: m.__name__
)
def test_r2_no_public_function_has_a_default_argument(module):
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_") or function.__module__ != module.__name__:
            continue
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.default is inspect.Parameter.empty, (
                f"{name}({parameter.name})"
            )


def test_r2_the_classes_of_the_inputs_have_no_default():
    for cls in (quantities.InputValue, quantities.PointUnits):
        for item in dataclasses.fields(cls):
            assert item.default is dataclasses.MISSING


# --- R3: pure, and contract models only through contracts.<folder>.<module> ---

ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "datetime",
    "math",
    "statistics",
    "typing",
    "contracts.inputs.common",
    "contracts.inputs.site_climate",
    "contracts.results.models",
}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_r3_a_module_imports_nothing_that_reads_the_outside(path):
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names = {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import of this package
                continue
            names = {node.module}
        else:
            continue
        assert names <= ALLOWED_IMPORTS, names - ALLOWED_IMPORTS


@pytest.mark.parametrize("path", MODULES + TESTS, ids=lambda p: p.name)
def test_r3_contract_models_are_imported_as_contracts_folder_module(path):
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            top = node.module.split(".")[0]
            assert top not in {"inputs", "results"}, node.module
            if top == "contracts":
                # contracts.<folder>.<module>: three parts at least
                assert len(node.module.split(".")) >= 3, node.module


# --- R4: no new Missing shape ---


@pytest.mark.parametrize("path", MODULES + TESTS, ids=lambda p: p.name)
def test_r4_no_module_defines_its_own_missing(path):
    classes = {n.name for n in ast.walk(_tree(path)) if isinstance(n, ast.ClassDef)}
    assert not {name for name in classes if "missing" in name.lower()}


# --- R5: the README lists every constant with an empty value ---


def _constants_table() -> list[list[str]]:
    section = _section("Constants a person has to transcribe")
    rows = []
    for line in section.splitlines():
        if line.startswith("| `"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def test_r5_the_readme_table_has_one_row_per_constant():
    rows = _constants_table()
    identifiers = [row[0].strip("`") for row in rows]
    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == _constant_identifiers()


def test_r5_every_value_of_the_readme_table_is_empty():
    for row in _constants_table():
        assert row[-1] == "", row[0]


# --- R6: every case code of the tests is listed in the README ---


def test_r6_every_case_code_is_listed_under_proposed_cases():
    section = _section("PROPOSED cases")
    codes = set()
    for path in TESTS:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                codes.add(node.name.split("_")[1].upper())
    for code in codes:
        assert f"`{code}`" in section, code


def test_r6_the_readme_has_an_open_list_with_the_dew_point_route():
    section = _section("OPEN")
    assert "D25" in section
    assert "dew point" in section
