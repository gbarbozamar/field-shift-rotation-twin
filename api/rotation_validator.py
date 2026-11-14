"""The real ``RotationValidator``: the request item ``rotation`` against its contract.

``RotationDefinitionValidator`` loads the item into
``contracts.rotation_definition.RotationDefinition`` (decision Q9, issue 18)
and returns one ``ErrorDetail`` per validation error:

- ``path``: the dotted location inside the rotation (``components.0.purpose``);
  empty for an error of the whole object. The route prefixes ``rotation``.
- ``code``: the validation error type.
- ``message``: the error text. The submitted input, the error context and the
  documentation link are never copied.

An empty list means the item loads. The route then answers ``422``
``ROTATION_INVALID`` for a non-empty list without calling a source or an
engine. Status: PROPOSED (blueprint section 3.7).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from api.errors import join_path
from api.ports import ErrorDetail
from contracts.rotation_definition import RotationDefinition


def load_rotation_definition(rotation: Mapping[str, Any]) -> RotationDefinition:
    """The argument of EP2: the request item loaded into its model, unchanged."""
    return RotationDefinition.model_validate(rotation)


class RotationDefinitionValidator:
    """Checks one rotation by loading it into ``RotationDefinition``."""

    def validate(self, rotation: Mapping[str, Any]) -> list[ErrorDetail]:
        try:
            load_rotation_definition(rotation)
        except ValidationError as error:
            return [
                ErrorDetail(
                    path=join_path(item["loc"]),
                    code=str(item["type"]),
                    message=str(item["msg"]),
                )
                for item in error.errors(
                    include_url=False, include_context=False, include_input=False
                )
            ]
        return []
