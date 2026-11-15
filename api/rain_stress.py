"""Heavier rain as a stress test of the rainfall erosivity (unit l2/heavier-rain).

PROPOSED (blueprint section 3.7; brief S-017). The user declares a factor; the
rainfall erosivity level of the parameter catalogue, the record whose ``id`` is
``rusle_r_factor`` (``R_ID`` of ``engine/erosion/soil_loss.py``, read by EP1 on
its main route), is multiplied by it in a copy of the catalogue, and the answer
carries an echo labelled "stress test", never "forecast". The wiring into the
route and the request is S-018 (PROPOSED R10).

- ``rain_stress(factor)``: the declared factor checked, as ``RainStress``; a
  missing factor gives ``RainStressMissing`` (no stress, the run is as without
  the option) with its reason.
- ``scale_erosivity(parameters, stress)``: a deep copy of the catalogue in
  which only the records of ``R_ID`` are multiplied (value, and both bounds of
  a range that is not null), each with a note appended; every other record is
  unchanged and the input is not mutated. A ``RainStressMissing`` gives an
  unchanged copy. PROPOSED: the note is appended at every factor, also at 1;
  EP1 does not read the note, so at 1 every result field is unchanged.
- ``applied_echo(parameters, stress)``: the echo the answer carries, with
  ``applied`` false and a detail that says so when the catalogue holds no
  ``R_ID`` record with a number. PROPOSED.

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

__all__ = [
    "DIMENSIONLESS",
    "R_ID",
    "STRESS_TEST_LABEL",
    "RainStress",
    "RainStressMissing",
    "applied_echo",
    "rain_stress",
    "scale_erosivity",
]

# The record of the rainfall erosivity level that EP1 reads on its main route
# (engine/erosion/soil_loss.py, R_ID). Kept here, not imported, so that api/
# does not import an engine module; api/test_rain_stress.py checks that the two
# agree.
R_ID = "rusle_r_factor"

# The unit string of a value with no unit (contracts/CONVENTIONS.md C1.1).
DIMENSIONLESS = "dimensionless"

STRESS_TEST_LABEL = "stress test"

NOTE_SEPARATOR = "; "


def _factor_text(factor: float) -> str:
    return repr(factor)


def _applied_detail(factor: float) -> str:
    return (
        f"rain erosivity multiplied by {_factor_text(factor)} as a "
        f"{STRESS_TEST_LABEL} of heavier rain; not a forecast"
    )


def _not_applied_detail(factor: float) -> str:
    return (
        f"rain erosivity not multiplied by {_factor_text(factor)}: the parameter "
        f"catalogue holds no record '{R_ID}' with a value, so the {STRESS_TEST_LABEL} "
        "of heavier rain was not applied; not a forecast"
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
    """A declared rain-stress factor, and the echo the answer carries."""

    factor: float
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
        missing = factor.missing
        if missing is None:
            raise ValueError("factor: a missing value carries its reason (C3.1)")
        return RainStressMissing(missing=missing, detail=_missing_detail(missing))
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
    return RainStress(factor=number, detail=_applied_detail(number))


def _scaled_number(number: Any, factor: float) -> Any:
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return number  # null (missing with its reason) or malformed: unchanged
    product = number * factor
    if not math.isfinite(product):
        raise ValueError(f"the record '{R_ID}' times the factor is not a finite number")
    return product


def _scaled_record(record: dict, factor: float) -> dict:
    scaled = copy.deepcopy(record)
    scaled["value"] = _scaled_number(scaled.get("value"), factor)
    range_ = scaled.get("range")
    if isinstance(range_, dict):
        for bound in ("low", "high"):
            if bound in range_:
                range_[bound] = _scaled_number(range_[bound], factor)
    note = scaled.get("note")
    added = _note(factor)
    scaled["note"] = (
        f"{note}{NOTE_SEPARATOR}{added}" if isinstance(note, str) and note else added
    )
    return scaled


def _is_r_record(record: Any) -> bool:
    return isinstance(record, dict) and record.get("id") == R_ID


def scale_erosivity(
    parameters: dict[str, dict], stress: RainStress | RainStressMissing
) -> dict[str, dict]:
    """A deep copy of the catalogue with only the ``R_ID`` records multiplied.

    ``parameters`` is not changed. A ``RainStressMissing`` gives an unchanged
    copy. Raises ``ValueError`` when a product is not a finite number.
    """
    if not isinstance(parameters, dict):
        raise TypeError(
            f"parameters: expected dict[str, dict], got {type(parameters).__name__}"
        )
    if isinstance(stress, RainStressMissing):
        return copy.deepcopy(parameters)
    if not isinstance(stress, RainStress):
        raise TypeError(
            f"stress: expected RainStress or RainStressMissing, got "
            f"{type(stress).__name__}"
        )
    return {
        key: (
            _scaled_record(record, stress.factor)
            if _is_r_record(record)
            else copy.deepcopy(record)
        )
        for key, record in parameters.items()
    }


def applied_echo(
    parameters: dict[str, dict], stress: RainStress | RainStressMissing
) -> RainStress | RainStressMissing:
    """The echo the answer carries for this catalogue. PROPOSED.

    ``stress`` unchanged when it is missing or when the catalogue holds a
    record of ``R_ID`` with a number; otherwise the same factor with
    ``applied`` false and a detail that says the factor was not applied.
    """
    if isinstance(stress, RainStressMissing):
        return stress
    has_number = any(
        _is_r_record(record)
        and not isinstance(record.get("value"), bool)
        and isinstance(record.get("value"), (int, float))
        for record in parameters.values()
    )
    if has_number:
        return stress
    return replace(stress, applied=False, detail=_not_applied_detail(stress.factor))
