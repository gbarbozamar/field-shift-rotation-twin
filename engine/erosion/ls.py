"""Slope steepness factor and slope length factor (docs/METHODS.md M1.4). PROPOSED.

The two functions of this module compute the factors ``S`` and ``L`` in the
forms given in issue #73, which are themselves PROPOSED until a science
reviewer has checked them against sources S2 and S3 of ``docs/METHODS.md``::

    S = a1 * sin(theta) + a2        the slope is below the break slope s_break
    S = a3 * sin(theta) - a4        the slope is at the break slope or above it

    L    = (lambda / lambda_unit) ** m
    m    = beta / (1 + beta)
    beta = (sin(theta) / b1) / (b2 * sin(theta) ** b3 + b4)

``theta`` is the slope angle and ``lambda`` the slope length.

**This module holds no coefficient.** ``a1`` to ``a4``, ``s_break``,
``lambda_unit`` and ``b1`` to ``b4`` are arguments without a default: the
caller supplies each one, read from the parameter catalogue, where a person
transcribed it and a second person checked it. ``LS.md`` in this folder lists
them, together with every OPEN question of this unit.

Pure functions: no file, no network, no clock, and no argument is changed
(``contracts/ENTRYPOINTS.md`` G1). They are parts of the erosion engine, not
its entry point.

A factor that is not computed is returned as the ``Missing`` of
``contracts/results/models.py`` with its reason (G4 and section 3 of
``contracts/CONVENTIONS.md``): never zero, never a default, never "not a
number".
"""

from __future__ import annotations

import enum
import math

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

__all__ = [
    "REASON_UNIT_NOT_ACCEPTED",
    "SlopeUnit",
    "slope_length_factor",
    "slope_steepness_factor",
]


class SlopeUnit(enum.Enum):
    """How the number of a slope is to be read. PROPOSED.

    The input contract leaves the unit of slope steepness OPEN (question 18
    of ``contracts/inputs/README.md``), so the caller states it. These are
    names for the caller of this module, not unit strings of a contract.

    ``PERCENT`` and ``RATIO`` are read as rise over horizontal distance, that
    is the tangent of the slope angle. That reading is PROPOSED: see ``LS.md``.
    """

    PERCENT = "percent"
    RATIO = "ratio"
    ANGLE_DEGREES = "angle_degrees"
    ANGLE_RADIANS = "angle_radians"


# PROPOSED. Reason code of a factor that is not computed because two arguments
# that must share a unit do not. The code for "a unit the engine does not
# accept" is not decided: Q11 of contracts/ENTRYPOINTS.md.
REASON_UNIT_NOT_ACCEPTED = "NOT_COMPUTABLE"

# What the word "percent" means: parts per hundred. A unit conversion, not a
# coefficient of the method.
_PERCENT = 100.0

# The two existing ``Missing`` shapes of the contracts (question 24 of
# contracts/inputs/README.md asks for one). Either is accepted as an argument;
# a result is always the one of contracts/results/models.py.
_MISSING = (InputMissing, ResultMissing)


class _NotFiniteReal(ArithmeticError):
    """A step of a form gave a complex number, an infinity or "not a number"."""


def _check_types(numbers: dict[str, object]) -> None:
    """G5: an argument that is neither a number nor a ``Missing`` is a defect of the caller."""
    for name, item in numbers.items():
        if isinstance(item, _MISSING):
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(
                f"{name}: expected a number, or a Missing of the contract models "
                f"with its reason; got {type(item).__name__}. A missing value is "
                "never passed as None"
            )


def _check_slope_unit(name: str, unit: object) -> None:
    if not isinstance(unit, SlopeUnit):
        raise TypeError(f"{name}: expected a SlopeUnit, got {type(unit).__name__}")


def _check_unit_text(name: str, unit: object) -> None:
    if not isinstance(unit, str):
        raise TypeError(f"{name}: expected text, got {type(unit).__name__}")


def _finite(item: int | float) -> float | None:
    """The number as a float, or ``None`` when it is not a finite number."""
    try:
        number = float(item)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _numbers_or_missing(numbers: dict[str, object]) -> dict[str, float] | ResultMissing:
    """Every argument as a finite float, or the reason why nothing is computed.

    A missing argument comes first (C3.3): the result is ``MISSING_INPUT`` and
    its detail names every missing argument, each with its own reason. Then an
    argument that is not a finite number: ``NOT_COMPUTABLE``, named likewise.
    """
    absent = []
    for name, item in numbers.items():
        if isinstance(item, _MISSING):
            text = f"{name} is missing, reason {item.reason}"
            if item.detail is not None:
                text += f": {item.detail}"
            absent.append(text)
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))

    values = {name: _finite(item) for name, item in numbers.items()}
    not_finite = [name for name, value in values.items() if value is None]
    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    return values


def _real(number: object) -> float:
    """The result of one step of a form, when it is a finite real number."""
    if isinstance(number, complex) or not math.isfinite(number):
        raise _NotFiniteReal
    return number


def _sine_of_slope(slope: float, unit: SlopeUnit) -> float:
    """``sin(theta)``, with ``theta`` the slope angle."""
    if unit is SlopeUnit.ANGLE_RADIANS:
        theta = slope
    elif unit is SlopeUnit.ANGLE_DEGREES:
        theta = math.radians(slope)
    elif unit is SlopeUnit.RATIO:
        theta = math.atan(slope)
    else:
        theta = math.atan(slope / _PERCENT)
    return math.sin(theta)


def _no_finite_result(factor: str, step: str) -> ResultMissing:
    """G4: the inputs are present and the form does not cover the case."""
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail=f"{factor}: {step} is not a finite real number for these arguments",
    )


def slope_steepness_factor(
    *,
    slope_steepness: float | InputMissing | ResultMissing,
    slope_unit: SlopeUnit,
    s_break: float | InputMissing | ResultMissing,
    s_break_unit: SlopeUnit,
    a1: float | InputMissing | ResultMissing,
    a2: float | InputMissing | ResultMissing,
    a3: float | InputMissing | ResultMissing,
    a4: float | InputMissing | ResultMissing,
) -> float | ResultMissing:
    """The slope steepness factor ``S`` of ``docs/METHODS.md`` M1.4.

    ``S = a1 * sin(theta) + a2`` when ``slope_steepness`` is below ``s_break``,
    and ``S = a3 * sin(theta) - a4`` when it is at ``s_break`` or above it.
    The two numbers are compared as given, so they must be in the same unit.

    Arguments, all by name and none with a default:

    - ``slope_steepness``: the slope of the field, or its ``Missing`` part.
    - ``slope_unit``: how the number of ``slope_steepness`` is to be read.
    - ``s_break``: the break slope, from the parameter catalogue.
    - ``s_break_unit``: how the number of ``s_break`` is to be read.
    - ``a1`` to ``a4``: the coefficients, from the parameter catalogue. ``a4``
      is the number that the form subtracts.

    Returns ``S`` as a float, or a ``Missing``:

    - ``MISSING_INPUT`` when the slope or any coefficient is missing; the
      detail names each one. Every coefficient is needed, also those of the
      branch that the slope does not take (PROPOSED).
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, or when the
      form gives no finite real number.
    - ``REASON_UNIT_NOT_ACCEPTED`` when ``s_break_unit`` is not ``slope_unit``.

    Raises ``TypeError`` for an argument of another type (G5).
    """
    numbers = {
        "slope_steepness": slope_steepness,
        "s_break": s_break,
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "a4": a4,
    }
    _check_types(numbers)
    _check_slope_unit("slope_unit", slope_unit)
    _check_slope_unit("s_break_unit", s_break_unit)

    values = _numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    if s_break_unit is not slope_unit:
        return ResultMissing(
            reason=REASON_UNIT_NOT_ACCEPTED,
            detail=(
                f"s_break is in {s_break_unit.value} and slope_steepness in "
                f"{slope_unit.value}: the two are compared as given and need one unit"
            ),
        )

    slope = values["slope_steepness"]
    sine = _sine_of_slope(slope, slope_unit)
    try:
        if slope < values["s_break"]:
            return _real(values["a1"] * sine + values["a2"])
        return _real(values["a3"] * sine - values["a4"])
    except ArithmeticError:
        return _no_finite_result("slope_steepness_factor", "S")


def slope_length_factor(
    *,
    slope_length: float | InputMissing | ResultMissing,
    slope_length_unit: str,
    lambda_unit: float | InputMissing | ResultMissing,
    lambda_unit_unit: str,
    slope_steepness: float | InputMissing | ResultMissing,
    slope_unit: SlopeUnit,
    b1: float | InputMissing | ResultMissing,
    b2: float | InputMissing | ResultMissing,
    b3: float | InputMissing | ResultMissing,
    b4: float | InputMissing | ResultMissing,
) -> float | ResultMissing:
    """The slope length factor ``L`` of ``docs/METHODS.md`` M1.4.

    ``L = (slope_length / lambda_unit) ** m``, with ``m = beta / (1 + beta)``
    and ``beta = (sin(theta) / b1) / (b2 * sin(theta) ** b3 + b4)``.

    Arguments, all by name and none with a default:

    - ``slope_length``: the slope length of the field, or its ``Missing`` part.
    - ``slope_length_unit``: the unit string that ``slope_length`` carries.
    - ``lambda_unit``: the unit length, from the parameter catalogue.
    - ``lambda_unit_unit``: the unit string that ``lambda_unit`` carries.
    - ``slope_steepness``: the slope of the field, or its ``Missing`` part.
    - ``slope_unit``: how the number of ``slope_steepness`` is to be read.
    - ``b1`` to ``b4``: the coefficients, from the parameter catalogue.

    The length is divided by the unit length as given, so the two unit
    strings must be the same text. No length is converted here.

    Returns ``L`` as a float, or a ``Missing``:

    - ``MISSING_INPUT`` when the length, the slope or any coefficient is
      missing; the detail names each one.
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, or when a
      step of the form gives no finite real number.
    - ``REASON_UNIT_NOT_ACCEPTED`` when the two unit strings differ.

    Raises ``TypeError`` for an argument of another type (G5).
    """
    numbers = {
        "slope_length": slope_length,
        "lambda_unit": lambda_unit,
        "slope_steepness": slope_steepness,
        "b1": b1,
        "b2": b2,
        "b3": b3,
        "b4": b4,
    }
    _check_types(numbers)
    _check_unit_text("slope_length_unit", slope_length_unit)
    _check_unit_text("lambda_unit_unit", lambda_unit_unit)
    _check_slope_unit("slope_unit", slope_unit)

    values = _numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    if lambda_unit_unit != slope_length_unit:
        return ResultMissing(
            reason=REASON_UNIT_NOT_ACCEPTED,
            detail=(
                f"lambda_unit is in '{lambda_unit_unit}' and slope_length in "
                f"'{slope_length_unit}': the two are divided as given and need one unit"
            ),
        )

    sine = _sine_of_slope(values["slope_steepness"], slope_unit)
    step = "beta"
    try:
        beta = _real(
            (sine / values["b1"]) / (values["b2"] * sine ** values["b3"] + values["b4"])
        )
        step = "m"
        m = _real(beta / (1 + beta))
        step = "L"
        return _real((values["slope_length"] / values["lambda_unit"]) ** m)
    except ArithmeticError:
        return _no_finite_result("slope_length_factor", step)
