"""Looking up a parameter of the catalogue by its identifier and scope (D46, D56).

Private to the water entry point (``engine/water/exposure.py``). Status:
PROPOSED (blueprint section 3.7); see engine/water/EXPOSURE.md.

The catalogue reaches the entry point as the argument ``parameters``: the
records exactly as ``params.catalogue.load_folder`` returns them, keyed by the
path of their file (contracts/ENTRYPOINTS.md, type row of ``parameters``). A
record is found by its ``id`` and its ``scope`` through
``params.catalogue.identity``, never by its path, and its value is read with
``params.catalogue.read_value``. Nothing here reads a file (G1).

What a lookup returns, the rows of G4 of contracts/ENTRYPOINTS.md:

- the number of the record;
- no record with that ``id`` and ``scope``: ``MISSING_INPUT``, naming the
  parameter by its ``id`` and the scope looked for (D56);
- a record whose value is ``null``: ``MISSING_INPUT``, naming the parameter
  and repeating the reason of the record;
- a record that ``read_value`` refuses (malformed, or a placeholder), or two
  records with the same ``id`` and ``scope``: ``MISSING_INPUT``, naming the
  parameter and why it is not read (PROPOSED: the value the computation
  needs is not available to it);
- a record anywhere in ``parameters`` without a well-formed ``id`` and
  ``scope``: every parameter is ``MISSING_INPUT``, naming it and every such
  record by its key. It cannot be compared, so it could be a record of any
  parameter; it is reported, not skipped (F3c of params/README.md), as EP1
  does in engine/erosion/_parameters.py (PROPOSED).

The lookup is exact: a record with the empty scope is not read in place of
one that names a crop, nor the other way round (question 5 of
params/README.md stays OPEN).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping

from contracts.results.models import Missing
from params.catalogue import Missing as CatalogueMissing
from params.catalogue import identity, read_value

__all__ = [
    "Catalogue",
    "check_parameters",
    "describe",
]

# A scope as the entry point looks it up: (key, word) pairs, in a fixed order.
Scope = tuple[tuple[str, str], ...]

# The kinds of problem a lookup reports; the first is named by D56.
NO_RECORD = "no record in parameters (D56)"
NO_VALUE = "the record holds no value"
NOT_READ = "the record is not read"
CANNOT_LOOK_UP = "it cannot be looked up"


def check_parameters(parameters: object) -> None:
    """``TypeError`` unless ``parameters`` is a ``dict[str, dict]`` (G3, G5).

    The message names the argument and never repeats a key or a record.
    """
    if not isinstance(parameters, dict):
        raise TypeError(
            "parameters: expected dict[str, dict] (the catalogue as loaded), "
            f"got {type(parameters).__name__} (G5)"
        )
    for key, record in parameters.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise TypeError(
                "parameters: expected dict[str, dict] (the catalogue as loaded): "
                "every key is the path of a record file and every value a record (G5)"
            )


def scope_text(scope: Scope) -> str:
    """The scope as JSON text with sorted keys, for a ``detail``."""
    return json.dumps(dict(scope), sort_keys=True)


def describe(parameter_id: str, scope: Scope) -> str:
    """How a ``detail`` names a parameter: its ``id`` and the scope looked for."""
    return f"parameter '{parameter_id}' with scope {scope_text(scope)}"


class Catalogue:
    """The records of ``parameters``, found by ``id`` and ``scope``.

    Each lookup is answered once and kept. A lookup that does not give a
    number is remembered with the first day it was needed, so that a yearly
    item names only what was needed up to the end of its year.
    """

    def __init__(self, parameters: Mapping[str, dict]) -> None:
        self._index: dict[object, list[dict]] = {}
        # The keys of the records without a well-formed id and scope. Such a
        # record cannot be compared, so it could be a record of any parameter:
        # it is reported, not skipped (F3c of params/README.md), as EP1 does.
        self._malformed: list[str] = []
        for name in sorted(parameters):
            record = parameters[name]
            try:
                key = identity(record)
            except ValueError:
                self._malformed.append(name)
                continue
            self._index.setdefault(key, []).append(record)
        self._answers: dict[tuple[str, Scope], float | Missing] = {}
        # (parameter id, scope) -> (kind, reason of the record or None, first day)
        self._problems: dict[tuple[str, Scope], tuple[str, str | None, dt.date]] = {}

    def value(self, parameter_id: str, scope: Scope, day: dt.date) -> float | Missing:
        """The value of one parameter, or why there is none; ``day`` is when it is needed."""
        key = (parameter_id, scope)
        if key not in self._answers:
            self._answers[key] = self._read(parameter_id, scope, day)
        return self._answers[key]

    def _read(self, parameter_id: str, scope: Scope, day: dt.date) -> float | Missing:
        if self._malformed:
            return self._problem(
                parameter_id, scope, day, CANNOT_LOOK_UP, self.malformed_text()
            )
        found = self._index.get(
            identity({"id": parameter_id, "scope": dict(scope)}), []
        )
        if not found:
            return self._problem(parameter_id, scope, day, NO_RECORD, None)
        if len(found) != 1:
            return self._problem(
                parameter_id,
                scope,
                day,
                NOT_READ,
                "two records share this id and scope",
            )
        (record,) = found
        try:
            value = read_value(record)
        except ValueError as error:
            return self._problem(parameter_id, scope, day, NOT_READ, str(error))
        if isinstance(value, CatalogueMissing):
            return self._problem(parameter_id, scope, day, NO_VALUE, value.reason)
        return value

    def _problem(
        self,
        parameter_id: str,
        scope: Scope,
        day: dt.date,
        kind: str,
        reason: str | None,
    ) -> Missing:
        self._problems[(parameter_id, scope)] = (kind, reason, day)
        why = kind if reason is None else f"{kind}: {reason}"
        return Missing(
            reason="MISSING_INPUT", detail=f"{describe(parameter_id, scope)}: {why}"
        )

    def malformed_text(self) -> str:
        """Why no parameter can be looked up while a record is malformed."""
        return (
            "the record(s) "
            + ", ".join(repr(name) for name in self._malformed)
            + " have no well-formed 'id' and 'scope', so they cannot be compared "
            "and could be records of this parameter (F3c of params/README.md); "
            "params.catalogue.check_catalogue rejects such a catalogue (G3)"
        )

    def problems_until(self, last: dt.date) -> list[str]:
        """The items naming every parameter without a value needed on or before ``last``.

        The parameters with no record, and those that cannot be looked up
        because a record is malformed, are grouped by scope, so that each scope
        (and the malformed records) is written once; the others are one item
        each, with their reason.
        """
        grouped: dict[str, dict[Scope, list[str]]] = {NO_RECORD: {}, CANNOT_LOOK_UP: {}}
        others: list[str] = []
        for (parameter_id, scope), (kind, reason, day) in self._problems.items():
            if day > last:
                continue
            if kind in grouped:
                grouped[kind].setdefault(scope, []).append(parameter_id)
            else:
                others.append(f"{describe(parameter_id, scope)}: {kind}: {reason}")
        items = [
            f"parameters with no record in parameters (D56), scope "
            f"{scope_text(scope)}: " + ", ".join(f"'{name}'" for name in names)
            for scope, names in sorted(grouped[NO_RECORD].items())
        ]
        if grouped[CANNOT_LOOK_UP]:
            items.append(
                "parameters that cannot be looked up: " + self.malformed_text()
            )
            items += [
                f"parameters that cannot be looked up, scope {scope_text(scope)}: "
                + ", ".join(f"'{name}'" for name in names)
                for scope, names in sorted(grouped[CANNOT_LOOK_UP].items())
            ]
        return items + sorted(others)
