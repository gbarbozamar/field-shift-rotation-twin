"""The real ``RotationValidator``: the request item ``rotation`` against its contract.

``RotationDefinitionValidator`` loads the item into
``contracts.rotation_definition.RotationDefinition`` (decision Q9, issue 18)
and returns one ``ErrorDetail`` per validation error:

- ``path``: the dotted location inside the rotation (``components.0.purpose``);
  empty for an error of the whole object. The route prefixes ``rotation``.
- ``code``: the validation error type.
- ``message``: the error text. The submitted input, the error context and the
  documentation link are never copied. A contract model may write a submitted
  value into its own message (for example an identifier); such a message is
  replaced by a fixed text, so no response echoes what was sent.

An empty list means the item loads. The route then answers ``422``
``ROTATION_INVALID`` for a non-empty list without calling a source or an
engine. Status: PROPOSED (blueprint section 3.7).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from api.errors import join_path
from api.ports import ErrorDetail
from contracts.rotation_definition import RotationDefinition

# Shown in place of an error text that repeats a submitted value. The path and
# the code of the detail still say where the problem is and of which kind.
REDACTED_MESSAGE = "The value breaks a rule of the rotation definition contract."

# A submitted value shorter than this, written as text, is not looked for: it
# is too short to tell apart from the words of a message. PROPOSED.
_SHORTEST_VALUE_LOOKED_FOR = 3


def submitted_texts(value: Any) -> set[str]:
    """Every value and key of the submitted item, as lower-case text."""
    texts: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            texts |= submitted_texts(key) | submitted_texts(item)
    elif isinstance(value, list | tuple):
        for item in value:
            texts |= submitted_texts(item)
    elif isinstance(value, str | int | float) and not isinstance(value, bool):
        text = str(value).strip().casefold()
        if len(text) >= _SHORTEST_VALUE_LOOKED_FOR:
            texts.add(text)
    return texts


def safe_message(
    message: str,
    submitted: set[str],
    known: set[str],
    redacted: str = REDACTED_MESSAGE,
) -> str:
    """The message, or the fixed text ``redacted`` when it repeats a submitted value.

    ``known`` holds the texts the contract itself defines (its field names):
    a message may name them even though the request also contains them.
    ``redacted`` lets another route write its own fixed text (PROPOSED, S-029).
    """
    lowered = message.casefold()
    if any(text in lowered for text in submitted - known):
        return redacted
    return message


def field_names(model: type[BaseModel], seen: set[type] | None = None) -> set[str]:
    """Field names of a model and of the models it nests, lower-case."""
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(name.casefold())
        for nested in _nested_models(field.annotation):
            names |= field_names(nested, seen)
    return names


# The old private names, kept so that nothing that imports them breaks (S-029).
_submitted_texts = submitted_texts
_safe_message = safe_message
_field_names = field_names


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in get_args(annotation):
        found.extend(_nested_models(argument))
    return found


def load_rotation_definition(rotation: Mapping[str, Any]) -> RotationDefinition:
    """The argument of EP2: the request item loaded into its model, unchanged."""
    return RotationDefinition.model_validate(rotation)


class RotationDefinitionValidator:
    """Checks one rotation by loading it into ``RotationDefinition``."""

    def validate(self, rotation: Mapping[str, Any]) -> list[ErrorDetail]:
        try:
            load_rotation_definition(rotation)
        except ValidationError as error:
            submitted = submitted_texts(rotation)
            known = field_names(RotationDefinition)
            return [
                ErrorDetail(
                    path=join_path(item["loc"]),
                    code=str(item["type"]),
                    message=safe_message(str(item["msg"]), submitted, known),
                )
                for item in error.errors(
                    include_url=False, include_context=False, include_input=False
                )
            ]
        return []
