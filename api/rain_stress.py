"""Heavier rain as a stress test of the rainfall erosivity (unit l2/heavier-rain).

PROPOSED (blueprint section 3.7; brief S-017). The user declares a factor; the
rainfall erosivity level of the parameter catalogue that EP1 reads on its main
route, the record whose ``id`` is ``rusle_r_factor`` with the empty scope
(``R_ID`` and ``SCOPE`` of ``engine/erosion/soil_loss.py``), is multiplied by it
in a copy of the catalogue, and the answer carries an echo labelled "stress
test", never "forecast". The wiring into the route and the request is S-018
(PROPOSED R10).

- ``rain_stress(factor)``: the declared factor checked, as ``RainStress``,
  which keeps the declared ``Value`` (its provenance, source, range or the
  reason it has none, assumption mark) so the echo shows where the factor came
  from; a missing factor gives ``RainStressMissing`` (no stress, the run is as
  without the option) with its reason.
- ``scale_erosivity(parameters, stress)``: a deep copy of the catalogue in
  which only the records with ``R_ID`` and ``EP1_SCOPE`` whose value is a
  number are multiplied (the value, and both bounds of a range that is not
  null), each with a note appended. A record of ``R_ID`` with another scope, a
  null value or the word PLACEHOLDER is copied unchanged, with no note. Every
  other record is unchanged and the input is not mutated. A
  ``RainStressMissing`` gives an unchanged copy. PROPOSED: the note is
  appended at every factor, also at 1; EP1 does not read the note, so at 1
  every result field is unchanged.
- ``applied_echo(parameters, stress)``: the echo the answer carries, with
  ``applied`` false and a detail that says why when EP1 would not read the
  level as a number: no record, more than one, a record ``read_value``
  refuses (malformed or a placeholder), a null value, or a record anywhere
  without a well-formed ``id`` and ``scope``. These are the cases of
  ``read_parameter`` of ``engine/erosion/_parameters.py``, which EP1 uses;
  api/test_rain_stress.py checks that the two agree. PROPOSED.

The scaled record keeps its ``citation``, ``transcribed_by`` and
``checked_by`` unchanged: a signature is never changed, and the note says the
value was multiplied. EP1's source text names the records it read by id and
scope only, so it does not say the value was scaled: the echo must always
travel with any result computed on a stressed catalogue (S-018).

The factor's own range is not carried into R: R's range is multiplied by the
factor's number only. How the uncertainty of the factor combines with the
uncertainty of R is a science choice, OPEN.

The factor is written in the detail and the note with 15 significant digits
(``_factor_text``, PROPOSED, S-028): exactly as declared up to 15 digits,
without binary float artefacts.

This module holds no factor: "as today, heavier, much heavier" are screen
choices whose numbers the user declares (or example data in ``demo/``,
labelled as such). Pure functions: no file, no network, no clock.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from typing import Any

from contracts.inputs.common import Missing, Value
from params.catalogue import Missing as CatalogueMissing
from params.catalogue import identity, is_placeholder, read_value

__all__ = [
    "DIMENSIONLESS",
    "EP1_SCOPE",
    "R_ID",
    "STRESS_TEST_LABEL",
    "RainStress",
    "RainStressMissing",
    "applied_echo",
    "not_applied_detail",
    "rain_stress",
    "scale_erosivity",
]

# The record of the rainfall erosivity level that EP1 reads on its main route
# (engine/erosion/soil_loss.py, R_ID and SCOPE). Kept here, not imported, so
# that api/ does not import an engine module; api/test_rain_stress.py checks
# that they agree.
R_ID = "rusle_r_factor"
EP1_SCOPE: dict[str, str] = {}

# The unit string of a value with no unit (contracts/CONVENTIONS.md C1.1).
DIMENSIONLESS = "dimensionless"

STRESS_TEST_LABEL = "stress test"

NOTE_SEPARATOR = "; "


def _factor_text(factor: float) -> str:
    """The factor as a person reads it, without floating-point artefacts.

    PROPOSED (S-028): 15 significant digits, the most a binary float (double)
    always carries without an artefact of its binary form, so a factor
    declared with up to 15 significant digits is written exactly as declared
    (1.2345678 stays 1.2345678) and a product such as 1.1 * 1.1 is written
    1.21. The ``g`` default of 6 digits rounded longer factors.
    """
    return f"{factor:.15g}"


def _applied_detail(factor: float) -> str:
    return (
        f"rain erosivity multiplied by {_factor_text(factor)} as a "
        f"{STRESS_TEST_LABEL} of heavier rain; not a forecast"
    )


def not_applied_detail(factor: float, why: str) -> str:
    return (
        f"rain erosivity not multiplied by {_factor_text(factor)}: {why}, so the "
        f"{STRESS_TEST_LABEL} of heavier rain was not applied; not a forecast"
    )


def _missing_detail(missing: Missing) -> str:
    why = f"reason {missing.reason}"
    if missing.detail is not None:
        why = f"{why}: {missing.detail}"
    return (
        f"no {STRESS_TEST_LABEL} of heavier rain: the factor is missing ({why}), "
        "so rain erosivity is as in the record; not a forecast"
    )


def _note(factor: float) -> str:
    return f"{STRESS_TEST_LABEL}: multiplied by {_factor_text(factor)}"


@dataclass(frozen=True)
class RainStress:
    """A declared rain-stress factor, and the echo the answer carries.

    ``declared`` is the ``Value`` the user declared, unchanged: its
    provenance, source, range or range_missing and assumption mark.
    """

    factor: float
    declared: Value
    detail: str
    label: str = STRESS_TEST_LABEL
    applied: bool = True


@dataclass(frozen=True)
class RainStressMissing:
    """No rain stress: the factor is missing, echoed with its reason."""

    missing: Missing
    detail: str
    label: str = STRESS_TEST_LABEL


def rain_stress(factor: Value) -> RainStress | RainStressMissing:
    """The declared factor, checked.

    A missing factor gives ``RainStressMissing`` with its reason. Raises
    ``TypeError`` when ``factor`` is not a ``Value``, and ``ValueError`` when
    its unit is not ``DIMENSIONLESS`` or its number is a bool, not finite, or
    not above zero. A factor below one (lighter rain) is allowed. PROPOSED.
    """
    if not isinstance(factor, Value):
        raise TypeError(f"factor: expected Value, got {type(factor).__name__}")
    if factor.unit != DIMENSIONLESS:
        raise ValueError(
            f"factor: the unit is not '{DIMENSIONLESS}' (contracts/CONVENTIONS.md C1.1)"
        )
    number: Any = factor.value
    if number is None:
        # The Value contract gives a missing value its missing part (C3.1).
        if factor.missing is None:
            raise ValueError(
                "factor: a missing value carries a missing part with its reason (C3.1)"
            )
        return RainStressMissing(
            missing=factor.missing, detail=_missing_detail(factor.missing)
        )
    # A bool or another non-number is a refused value (brief S-017): ValueError,
    # as for a number that is not finite or not above zero.
    is_number = not isinstance(number, bool) and isinstance(number, (int, float))
    if not is_number:
        raise ValueError("factor: the value is not a number")
    if not math.isfinite(number):
        raise ValueError("factor: the value is not a finite number")
    if number <= 0:
        raise ValueError("factor: the value is not above zero")
    number = float(number)
    return RainStress(factor=number, declared=factor, detail=_applied_detail(number))


# --- the record EP1 reads ---------------------------------------------------------


def _identity_or_none(record: Any) -> Any:
    try:
        return identity(record)
    except ValueError:
        return None


_SOUGHT = identity({"id": R_ID, "scope": EP1_SCOPE})


def _is_ep1_record(record: Any) -> bool:
    return _identity_or_none(record) == _SOUGHT


def _why_not_read(parameters: dict[str, dict]) -> str | None:
    """Why EP1 would not read the level as a number, or ``None`` when it would.

    The cases of ``read_parameter`` of engine/erosion/_parameters.py.
    """
    named = f"the record '{R_ID}' with the scope EP1 reads ({{}})"
    malformed = [
        key for key, rec in parameters.items() if _identity_or_none(rec) is None
    ]
    if malformed:
        return (
            "the parameter catalogue holds records without a well-formed 'id' and "
            f"'scope', so {named} cannot be looked up"
        )
    matches = [record for record in parameters.values() if _is_ep1_record(record)]
    if not matches:
        return f"the parameter catalogue holds no {named}"
    if len(matches) > 1:
        return f"the parameter catalogue holds more than one {named}"
    (record,) = matches
    try:
        value = read_value(record)
    except ValueError as error:
        return f"{named} is refused by params.catalogue.read_value ({error})"
    if isinstance(value, CatalogueMissing):
        return f"{named} has no value ({value.reason})"
    return None


# --- scaling ---------------------------------------------------------------------


def _finite(product: float) -> float:
    if not math.isfinite(product):
        raise ValueError(f"the record '{R_ID}' times the factor is not a finite number")
    return product


def _scaled_record(record: dict, factor: float) -> dict:
    """The record multiplied, or an unchanged copy when EP1 reads no number in it.

    A placeholder record or a null value: unchanged, no note. A value that is
    a number with a range that is not an object or has a bound that is not a
    number: ``ValueError`` (``read_value`` refuses the record), never a half
    scaled record.
    """
    scaled = copy.deepcopy(record)
    if is_placeholder(record):
        return scaled
    # read_value checks the whole record (check_record): a bound that is not a
    # number raises ValueError here, before anything is multiplied.
    if isinstance(read_value(record), CatalogueMissing):
        return scaled
    scaled["value"] = _finite(record["value"] * factor)
    range_ = scaled["range"]
    if range_ is not None:
        range_["low"] = _finite(range_["low"] * factor)
        range_["high"] = _finite(range_["high"] * factor)
    note = scaled.get("note")
    added = _note(factor)
    scaled["note"] = f"{note}{NOTE_SEPARATOR}{added}" if note else added
    return scaled


def _check_parameters(parameters: Any) -> None:
    if not isinstance(parameters, dict):
        raise TypeError(
            f"parameters: expected dict[str, dict], got {type(parameters).__name__}"
        )


def _check_stress(stress: Any) -> None:
    if not isinstance(stress, (RainStress, RainStressMissing)):
        raise TypeError(
            f"stress: expected RainStress or RainStressMissing, got "
            f"{type(stress).__name__}"
        )


def scale_erosivity(
    parameters: dict[str, dict], stress: RainStress | RainStressMissing
) -> dict[str, dict]:
    """A deep copy of the catalogue with only EP1's ``R_ID`` record multiplied.

    ``parameters`` is not changed. A ``RainStressMissing`` gives an unchanged
    copy. Raises ``TypeError`` for an argument of another type and
    ``ValueError`` when a record to scale is malformed or a product is not a
    finite number.
    """
    _check_parameters(parameters)
    _check_stress(stress)
    if isinstance(stress, RainStressMissing):
        return copy.deepcopy(parameters)
    return {
        key: (
            _scaled_record(record, stress.factor)
            if _is_ep1_record(record)
            else copy.deepcopy(record)
        )
        for key, record in parameters.items()
    }


def scales_to_finite(
    parameters: dict[str, dict], stress: RainStress | RainStressMissing
) -> bool:
    """Whether every number ``scale_erosivity`` multiplies stays finite.

    PROPOSED (S-029, remark R3): the same records as ``_scaled_record`` scales
    (EP1's ``R_ID`` records that are not placeholders and whose value
    ``read_value`` reads as a number), and the same products (the value and
    both bounds of a range that is not null), each checked with
    ``math.isfinite``. A ``RainStressMissing`` multiplies nothing: true.
    Raises ``TypeError`` for an argument of another type and ``ValueError``
    where ``read_value`` refuses a record, as ``scale_erosivity`` does.
    """
    _check_parameters(parameters)
    _check_stress(stress)
    if isinstance(stress, RainStressMissing):
        return True
    for record in parameters.values():
        if not _is_ep1_record(record) or is_placeholder(record):
            continue
        if isinstance(read_value(record), CatalogueMissing):
            continue
        numbers = [record["value"]]
        if record["range"] is not None:
            numbers += [record["range"]["low"], record["range"]["high"]]
        if not all(math.isfinite(number * stress.factor) for number in numbers):
            return False
    return True


def applied_echo(
    parameters: dict[str, dict], stress: RainStress | RainStressMissing
) -> RainStress | RainStressMissing:
    """The echo the answer carries for this catalogue. PROPOSED.

    ``stress`` unchanged when it is missing or when EP1 reads its ``R_ID``
    record as a number; otherwise the same factor with ``applied`` false and a
    detail that says why the factor was not applied. Raises ``TypeError`` for
    an argument of another type.
    """
    _check_parameters(parameters)
    _check_stress(stress)
    if isinstance(stress, RainStressMissing):
        return stress
    why = _why_not_read(parameters)
    if why is None:
        return stress
    return replace(stress, applied=False, detail=not_applied_detail(stress.factor, why))
