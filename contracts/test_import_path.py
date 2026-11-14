"""Acceptance test of unit l0/contracts-package.

One import path for the contract models: ``contracts.<folder>.<module>``,
imported from the repository root. This is the answer to question Q1 of
``contracts/ENTRYPOINTS.md`` (issue #18). A file loaded under two names
gives two classes, and an instance of one is not an instance of the other.

Run from the repository root: ``python -m pytest contracts/test_import_path.py``,
or as part of ``python -m pytest`` over the whole repository, where the
checks also see the modules that the tests of each contract folder loaded.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent
ROOT = CONTRACTS.parent

# The contract folders named in the brief of this unit. A folder added later
# is found by ``contract_folders`` and checked without a change here.
KNOWN_FOLDERS = ("inputs", "results", "rotation_definition")


def contract_folders() -> list[str]:
    """Every folder under ``contracts/`` that is a Python package."""
    return sorted(p.name for p in CONTRACTS.iterdir() if (p / "__init__.py").is_file())


def import_contract_packages() -> None:
    for folder in contract_folders():
        importlib.import_module(f"contracts.{folder}")


def name_from_root(file: Path) -> str:
    """The one name a file under ``contracts/`` may load under."""
    parts = file.relative_to(ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def loaded_contract_modules() -> dict[Path, list[str]]:
    """Names in ``sys.modules`` per source file under ``contracts/``."""
    names: dict[Path, list[str]] = {}
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if file is None:
            continue
        path = Path(file).resolve()
        if path.is_relative_to(CONTRACTS):
            names.setdefault(path, []).append(name)
    return names


def test_the_known_contract_folders_are_checked():
    assert set(KNOWN_FOLDERS) <= set(contract_folders())


def test_contracts_is_a_regular_package():
    import contracts

    assert contracts.__file__ is not None, "contracts/ has no __init__.py"
    assert Path(contracts.__file__).resolve() == CONTRACTS / "__init__.py"


def test_no_contract_folder_is_loaded_as_a_top_level_module():
    import_contract_packages()
    folders = set(contract_folders())
    wrong = sorted(name for name in sys.modules if name.split(".")[0] in folders)
    assert wrong == []


def test_no_contract_folder_can_be_imported_by_its_bare_name():
    """``import inputs`` must not find ``contracts/inputs/``."""
    import_contract_packages()
    found = {}
    for folder in contract_folders():
        spec = importlib.util.find_spec(folder)
        if spec is None or spec.origin is None:
            continue
        if Path(spec.origin).resolve().is_relative_to(CONTRACTS):
            found[folder] = spec.origin
    assert found == {}


def test_every_contract_file_is_loaded_under_its_name_from_the_root():
    import_contract_packages()
    loaded = loaded_contract_modules()
    assert len(loaded) > len(contract_folders())
    wrong = {
        str(file.relative_to(ROOT)): sorted(names)
        for file, names in loaded.items()
        if names != [name_from_root(file)]
    }
    assert wrong == {}


def test_a_class_reached_through_two_import_routes_is_the_same_object():
    """Every route to a contract class ends at one object.

    The routes are every loaded module that holds the class: the module that
    defines it, the package that exports it and the test module that imports
    it. A class is identified by the file that defines it and its name.
    """
    import_contract_packages()
    module_names = loaded_contract_modules()
    file_of = {name: file for file, names in module_names.items() for name in names}

    objects: dict[tuple[str, str], dict[int, list[str]]] = {}
    for file, names in module_names.items():
        for name in names:
            for attribute, value in list(vars(sys.modules[name]).items()):
                defined_in = file_of.get(getattr(value, "__module__", None))
                if not isinstance(value, type) or defined_in is None:
                    continue
                key = (str(defined_in.relative_to(ROOT)), value.__qualname__)
                routes = objects.setdefault(key, {}).setdefault(id(value), [])
                routes.append(f"{name}.{attribute}")

    assert objects, "no contract class was found"
    split = {
        key: sorted(routes.values())
        for key, routes in objects.items()
        if len(routes) > 1
    }
    assert split == {}

    # The pair named in the answer to Q1, written out.
    from contracts.inputs import SiteClimate
    from contracts.inputs.site_climate import SiteClimate as SiteClimateOfModule

    assert SiteClimate is SiteClimateOfModule
