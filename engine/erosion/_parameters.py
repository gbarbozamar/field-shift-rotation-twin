"""Look up one parameter of the catalogue by its id and scope. PROPOSED.

Private to the erosion engine (unit l0/erosion-ep1-parameters, issue #154).
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

__all__ = ["Parameter", "read_parameter", "scope_text"]


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

    A record with another scope is not read, also not one with a wider or a
    narrower scope (question 5 of params/README.md is OPEN).
    """
    sought = identity({"id": parameter_id, "scope": scope})
    matches = [
        record
        for _, record in sorted(parameters.items())
        if _identity_or_none(record) == sought
    ]
    named = _named(parameter_id, scope)
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
