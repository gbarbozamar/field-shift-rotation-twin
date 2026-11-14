"""Fixtures shared by the tests of api/."""

from __future__ import annotations

import sys
from importlib.abc import MetaPathFinder

import pytest


def _is_engine(name: str) -> bool:
    return name == "engine" or name.startswith("engine.")


class _NoEnginePackage(MetaPathFinder):
    """Makes ``import engine`` fail as if the package did not exist."""

    def find_spec(self, fullname, path=None, target=None):
        if _is_engine(fullname):
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)


@pytest.fixture
def no_engine_modules():
    """Forget every loaded ``engine`` module for one test, then put them back.

    A test that writes its own ``engine`` package and puts it first on
    ``sys.path`` then imports that one, not the engines of the repository.
    """
    saved = {name: module for name, module in sys.modules.items() if _is_engine(name)}
    for name in saved:
        del sys.modules[name]
    yield
    for name in [name for name in sys.modules if _is_engine(name)]:
        del sys.modules[name]
    sys.modules.update(saved)


@pytest.fixture
def engines_hidden(no_engine_modules):
    """No engine is built, whatever the repository holds.

    The engines of the repository land one by one; a test of "nothing is
    built" must not change its answer when one of them lands.
    """
    finder = _NoEnginePackage()
    sys.meta_path.insert(0, finder)
    yield
    sys.meta_path.remove(finder)
