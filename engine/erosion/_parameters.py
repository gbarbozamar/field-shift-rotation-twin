"""Look up one parameter of the catalogue by its id and scope. PROPOSED.

Private to the erosion engine (unit l0/erosion-ep1-parameters, issue #154;
``ParameterReader`` added by unit l0/erosion-ep1-c-r, issue #173).
The catalogue reaches the entry point as the argument ``parameters``, the
dictionary that ``params.catalogue.load_folder`` returns (contracts/ENTRYPOINTS.md,
Q3, D46, D56). A record is found by its ``id`` and its ``scope`` through
``params.catalogue.identity``, never by the path of its file, and its value is
read with ``params.catalogue.read_value``.

Every absence is the ``Missing`` of ``contracts/results/models.py`` with reason
``MISSING_INPUT`` and a ``detail`` that names the parameter by id and scope
(G4, the two rows for a parameter). The ``Missing`` of ``params/catalogue.py``
is rewritten as that one; it is never turned into a number.

Pure (G1): no file is read and no argument is changed. ``load_folder`` is
never called. The one number of this module is the 1 of "more than one record".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from contracts.results.models import Missing
from params.catalogue import Missing as CatalogueMissing
from params.catalogue import identity, read_value

__all__ = ["Parameter", "ParameterReader", "read_parameter", "scope_text"]


@dataclass(frozen=True)
class Parameter:
    """The value of one parameter, or why it has none, and the unit it carries.

    ``unit`` is the ``unit`` of the record when one record was read, and
    ``None`` when no record could be read.
    """

    value: float | Missing
    unit: str | None


def scope_text(scope: dict[str, str]) -> str:
    """The scope as it is written in a ``detail``: JSON with sorted keys."""
    return json.dumps(scope, sort_keys=True)


def _named(parameter_id: str, scope: dict[str, str]) -> str:
    return f"parameter '{parameter_id}' with scope {scope_text(scope)}"


def _identity_or_none(record: Any) -> Any:
    try:
        return identity(record)
    except ValueError:
        return None


def read_parameter(
    parameters: dict[str, dict], parameter_id: str, scope: dict[str, str]
) -> Parameter:
    """The value of the one record with this ``id`` and exactly this ``scope``.

    - No record: ``MISSING_INPUT``, the parameter named by id and scope (D56).
    - More than one record: ``MISSING_INPUT``, saying so. ``check_catalogue``
      rejects such a catalogue, and the runner passes only a checked one (G3).
    - A record that ``read_value`` refuses (malformed, or a placeholder):
      ``MISSING_INPUT``, the parameter named and the refusal repeated.
    - A record whose value is ``null``: ``MISSING_INPUT``, the parameter named
      and the reason of the record repeated (G4).
    - A record without a well-formed ``id`` and ``scope`` anywhere in
      ``parameters``: ``MISSING_INPUT``, the parameter named and every such
      record named by its key. It cannot be compared, so it could be a record of
      this parameter; it is reported, not skipped (F3c of params/README.md).
      PROPOSED; ``check_catalogue`` rejects such a catalogue (G3).

    A record with another scope is not read, also not one with a wider or a
    narrower scope (question 5 of params/README.md is OPEN).
    """
    sought = identity({"id": parameter_id, "scope": scope})
    named = _named(parameter_id, scope)
    identities = {
        key: _identity_or_none(record) for key, record in sorted(parameters.items())
    }
    malformed = [key for key, found in identities.items() if found is None]
    if malformed:
        return Parameter(
            Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"{named} cannot be looked up: the record(s) "
                    f"{', '.join(repr(key) for key in malformed)} have no well-formed "
                    "'id' and 'scope', so they cannot be compared and could be records "
                    "of this parameter (F3c of params/README.md); "
                    "params.catalogue.check_catalogue rejects such a catalogue (G3)"
                ),
            ),
            None,
        )
    matches = [parameters[key] for key, found in identities.items() if found == sought]
    if not matches:
        return Parameter(
            Missing(
                reason="MISSING_INPUT",
                detail=f"{named} has no record in parameters (D56)",
            ),
            None,
        )
    if len(matches) > 1:
        return Parameter(
            Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"{named} has more than one record in parameters, which "
                    "params.catalogue.check_catalogue rejects (G3)"
                ),
            ),
            None,
        )
    (record,) = matches
    try:
        value = read_value(record)
    except ValueError as error:
        return Parameter(
            Missing(
                reason="MISSING_INPUT",
                detail=f"the record of {named} is refused by params.catalogue.read_value: {error}",
            ),
            None,
        )
    if isinstance(value, CatalogueMissing):
        return Parameter(
            Missing(
                reason="MISSING_INPUT",
                detail=f"the record of {named} has no value: {value.reason}",
            ),
            record["unit"],
        )
    return Parameter(value, record["unit"])


class ParameterReader:
    """``read_parameter`` on one catalogue, each id and scope looked up once.

    It remembers every id and scope it was asked for, in the order first
    asked, so that the source of a computed value can name each record read.
    PROPOSED (unit l0/erosion-ep1-c-r). It changes nothing in ``parameters``.
    """

    def __init__(self, parameters: dict[str, dict]) -> None:
        self._parameters = parameters
        self._read: dict[tuple[str, str], Parameter] = {}

    def read(self, parameter_id: str, scope: dict[str, str]) -> Parameter:
        """The value of one parameter, as ``read_parameter`` returns it."""
        key = (parameter_id, scope_text(scope))
        if key not in self._read:
            self._read[key] = read_parameter(self._parameters, parameter_id, scope)
        return self._read[key]

    def records_read(self) -> list[tuple[str, str]]:
        """Every id and scope (as ``scope_text`` writes it) asked for, in order."""
        return list(self._read)

    def fork(self) -> ParameterReader:
        """A reader of the same catalogue that starts with what this one read."""
        other = ParameterReader(self._parameters)
        other._read = dict(self._read)
        return other
