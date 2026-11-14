"""Surface residue: the mass-cover relation and decay by residue type. PROPOSED.

Decision D45 of issue #77 keeps surface residue cover, with residue decay by
residue type, among the sub-factors of the soil-loss ratio (docs/METHODS.md
M1.5). This module turns a residue mass into the fraction of the soil it
covers, and carries a residue mass through time by decay.

The forms below are PROPOSED. Their source is to be confirmed by a person
against S1; the session that wrote them did not read S1, and it writes no
coefficient of S1 here, in a default, a test or a comment::

    mass-cover relation   cover = 1 - exp(-mass_cover_coefficient * residue_mass)
    decay of one step     mass_after = mass_before * exp(-decay_coefficient[residue_type] * elapsed_time)

Every constant is an argument without a default, supplied by the caller from
the parameter catalogue (README.md of this folder, "Constants a person has to
transcribe"). The decay coefficient is chosen by residue type from a mapping
the caller passes; a residue type that the mapping does not hold gives a
missing result that names it.

Decay never adds mass and never makes it negative: a negative mass, a
negative elapsed time or a negative decay coefficient is refused, since each
would break one of the two.

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_text,
    check_types,
    is_not_negative,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
    units_differ,
)

__all__ = [
    "residue_cover_from_mass",
    "residue_mass_after_decay",
    "residue_mass_over_time",
]


def residue_cover_from_mass(
    *,
    residue_mass: NumberOrMissing,
    residue_mass_unit: str,
    mass_cover_coefficient: NumberOrMissing,
    mass_cover_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The fraction of the soil covered by residue, from the residue mass. PROPOSED form.

    ``cover = 1 - exp(-mass_cover_coefficient * residue_mass)``.

    Arguments, all by name and none with a default:

    - ``residue_mass``: the residue mass on the surface per unit area, zero or more.
    - ``residue_mass_unit``: the unit string of ``residue_mass``.
    - ``mass_cover_coefficient``: the constant of the relation, from the
      parameter catalogue. Its unit is one over a mass per area.
    - ``mass_cover_coefficient_per_unit``: the mass-per-area unit whose
      inverse is the unit of the coefficient. It must be the same text as
      ``residue_mass_unit``: no unit is converted here.

    Returns the cover as a fraction (a float), or a ``Missing``:

    - ``MISSING_INPUT`` when an argument is missing; the detail names each one.
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, when the
      mass is negative (named; nothing is clipped), when the two unit strings
      differ, or when the form gives no finite real number.

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {
        "residue_mass": residue_mass,
        "mass_cover_coefficient": mass_cover_coefficient,
    }
    check_types(numbers)
    check_text("residue_mass_unit", residue_mass_unit)
    check_text("mass_cover_coefficient_per_unit", mass_cover_coefficient_per_unit)

    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, ["residue_mass"], is_not_negative, "is negative")
    if refused is not None:
        return refused
    refused = units_differ(
        "mass_cover_coefficient (per unit)",
        mass_cover_coefficient_per_unit,
        "residue_mass",
        residue_mass_unit,
        "multiplied",
    )
    if refused is not None:
        return refused
    try:
        exponential = real(
            math.exp(-values["mass_cover_coefficient"] * values["residue_mass"])
        )
        return real(1 - exponential)
    except (ArithmeticError, OverflowError):
        return no_finite_result("residue_cover_from_mass", "cover")


def _decay_coefficient(
    residue_type: str,
    decay_coefficients: Mapping[str, NumberOrMissing],
) -> NumberOrMissing:
    """The coefficient of the residue type as given, or a ``Missing`` when it has none."""
    if residue_type not in decay_coefficients:
        return ResultMissing(
            reason="MISSING_INPUT",
            detail="decay_coefficients holds no entry for this residue type",
        )
    return decay_coefficients[residue_type]


def _check_decay_arguments(
    residue_type: object,
    decay_coefficients: object,
    elapsed_time_unit: object,
    decay_coefficient_per_unit: object,
) -> None:
    check_text("residue_type", residue_type)
    if not isinstance(decay_coefficients, Mapping):
        raise TypeError(
            "decay_coefficients: expected a mapping from residue type to a number "
            f"or a Missing, got {type(decay_coefficients).__name__}"
        )
    for key, item in decay_coefficients.items():
        check_text("a residue type of decay_coefficients", key)
        check_types({f"the decay coefficient of residue type '{key}'": item})
    check_text("elapsed_time_unit", elapsed_time_unit)
    check_text("decay_coefficient_per_unit", decay_coefficient_per_unit)


def _decay(
    numbers: dict[str, NumberOrMissing],
    elapsed_time_unit: str,
    decay_coefficient_per_unit: str,
    function: str,
) -> float | ResultMissing:
    """One decay step, once the coefficient of the residue type is chosen."""
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, list(values), is_not_negative, "is negative")
    if refused is not None:
        return refused
    refused = units_differ(
        "the decay coefficient (per unit)",
        decay_coefficient_per_unit,
        "elapsed_time",
        elapsed_time_unit,
        "multiplied",
    )
    if refused is not None:
        return refused
    # ``numbers`` holds, in this order: the mass, the coefficient, the time.
    mass, coefficient, elapsed = values.values()
    try:
        return real(mass * real(math.exp(-coefficient * elapsed)))
    except (ArithmeticError, OverflowError):
        return no_finite_result(function, "the residue mass")


def residue_mass_after_decay(
    *,
    residue_mass: NumberOrMissing,
    residue_type: str,
    decay_coefficients: Mapping[str, NumberOrMissing],
    decay_coefficient_per_unit: str,
    elapsed_time: NumberOrMissing,
    elapsed_time_unit: str,
) -> float | ResultMissing:
    """The residue mass after one decay step. PROPOSED form.

    ``mass_after = residue_mass * exp(-decay_coefficients[residue_type] * elapsed_time)``.

    Arguments, all by name and none with a default:

    - ``residue_mass``: the residue mass at the start of the step, zero or more.
      The result is in the same unit.
    - ``residue_type``: the residue type whose coefficient applies.
    - ``decay_coefficients``: residue type to decay coefficient, from the
      parameter catalogue; each value a number or a ``Missing``. Every
      coefficient is zero or more, in one over a time.
    - ``decay_coefficient_per_unit``: the time unit whose inverse is the unit
      of every coefficient of the mapping. It must be the same text as
      ``elapsed_time_unit``: no time is converted here.
    - ``elapsed_time``: the length of the step, zero or more.
    - ``elapsed_time_unit``: the unit string of ``elapsed_time``.

    Returns the mass as a float, never more than ``residue_mass`` and never
    negative, or a ``Missing``:

    - ``MISSING_INPUT`` when the mass or the time is missing, when the
      mapping holds no coefficient for ``residue_type``, or when that
      coefficient is missing; the detail names each, and the residue type.
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, when the
      mass, the time or the coefficient is negative (named; nothing is
      clipped), when the two unit strings differ, or when the form gives no
      finite real number.

    Raises ``TypeError`` for an argument of another type.
    """
    check_types({"residue_mass": residue_mass, "elapsed_time": elapsed_time})
    _check_decay_arguments(
        residue_type, decay_coefficients, elapsed_time_unit, decay_coefficient_per_unit
    )
    numbers = {
        "residue_mass": residue_mass,
        f"the decay coefficient of residue type '{residue_type}'": _decay_coefficient(
            residue_type, decay_coefficients
        ),
        "elapsed_time": elapsed_time,
    }
    return _decay(
        numbers,
        elapsed_time_unit,
        decay_coefficient_per_unit,
        "residue_mass_after_decay",
    )


def residue_mass_over_time(
    *,
    initial_residue_mass: NumberOrMissing,
    residue_type: str,
    decay_coefficients: Mapping[str, NumberOrMissing],
    decay_coefficient_per_unit: str,
    step_durations: Sequence[NumberOrMissing],
    elapsed_time_unit: str,
) -> tuple[float, ...] | ResultMissing:
    """The residue mass at the end of each of consecutive decay steps. PROPOSED.

    Applies ``residue_mass_after_decay`` step after step, from
    ``initial_residue_mass``, one step per item of ``step_durations``. The
    result holds one mass per step, in order; it does not repeat the initial
    mass. The initial mass is checked also when there is no step. No mass is added between steps: a new residue input is the
    residue ledger, out of scope here (EP4 is OPEN).

    Arguments as for ``residue_mass_after_decay``; ``step_durations`` is a
    sequence of step lengths in ``elapsed_time_unit``, each a number or a
    ``Missing``.

    Returns the tuple of masses, or one ``Missing`` for the whole series: a
    step that cannot be computed makes the series missing, with the step
    named (0-based) and its own reason. An empty ``step_durations`` gives an
    empty tuple.

    Raises ``TypeError`` for an argument of another type.
    """
    check_types({"initial_residue_mass": initial_residue_mass})
    _check_decay_arguments(
        residue_type, decay_coefficients, elapsed_time_unit, decay_coefficient_per_unit
    )
    if isinstance(step_durations, (str, bytes)) or not isinstance(
        step_durations, Sequence
    ):
        raise TypeError(
            "step_durations: expected a sequence of numbers or Missing, "
            f"got {type(step_durations).__name__}"
        )
    check_types(
        {f"step_durations[{index}]": item for index, item in enumerate(step_durations)}
    )
    if not step_durations:
        values = numbers_or_missing({"initial_residue_mass": initial_residue_mass})
        if isinstance(values, ResultMissing):
            return values
        refused = outside(values, list(values), is_not_negative, "is negative")
        return () if refused is None else refused
    masses: list[float] = []
    mass: NumberOrMissing = initial_residue_mass
    for index, duration in enumerate(step_durations):
        name = "initial_residue_mass" if index == 0 else f"mass after step {index - 1}"
        numbers = {
            name: mass,
            f"the decay coefficient of residue type '{residue_type}'": _decay_coefficient(
                residue_type, decay_coefficients
            ),
            f"step_durations[{index}]": duration,
        }
        result = _decay(
            numbers,
            elapsed_time_unit,
            decay_coefficient_per_unit,
            "residue_mass_over_time",
        )
        if isinstance(result, ResultMissing):
            return ResultMissing(
                reason=result.reason,
                detail=f"step {index}: {result.detail}",
            )
        masses.append(result)
        mass = result
    return tuple(masses)
