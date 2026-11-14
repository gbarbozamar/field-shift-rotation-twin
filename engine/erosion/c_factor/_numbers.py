"""Checks shared by the modules of ``engine/erosion/c_factor/``. PROPOSED.

How an argument is read: a number, or a ``Missing`` of the contract models
with its reason (``contracts/CONVENTIONS.md`` C3). A missing argument makes
the result ``MISSING_INPUT`` and the detail names it (C3.3); an argument
that is not a finite number, or that lies outside what a quantity can be,
makes it ``NOT_COMPUTABLE``. Nothing is clipped, filled or defaulted.

This module holds no number of the method. The only numbers in it are the
bounds zero and one of a fraction, which are what the word "fraction" means.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

# The two existing ``Missing`` shapes of the contracts. Either is accepted as
# an argument; a result is always the one of contracts/results/models.py.
MISSING_SHAPES = (InputMissing, ResultMissing)

# PROPOSED. Reason code of a result that is not computed because two
# arguments that must share a unit do not. The code for "a unit the engine
# does not accept" is not decided: Q11 of contracts/ENTRYPOINTS.md. The same
# choice as engine/erosion/ls.py.
REASON_UNIT_NOT_ACCEPTED = "NOT_COMPUTABLE"

Number = int | float
NumberOrMissing = int | float | InputMissing | ResultMissing


def is_missing(item: object) -> bool:
    return isinstance(item, MISSING_SHAPES)


def check_types(numbers: Mapping[str, object]) -> None:
    """An argument that is neither a number nor a ``Missing`` is a defect of the caller."""
    for name, item in numbers.items():
        if is_missing(item):
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(
                f"{name}: expected a number, or a Missing of the contract models "
                f"with its reason; got {type(item).__name__}. A missing value is "
                "never passed as None"
            )


def check_text(name: str, item: object) -> None:
    if not isinstance(item, str):
        raise TypeError(f"{name}: expected text, got {type(item).__name__}")


def describe_missing(name: str, missing: InputMissing | ResultMissing) -> str:
    text = f"{name} is missing, reason {missing.reason}"
    if missing.detail is not None:
        text += f": {missing.detail}"
    return text


def finite(item: Number) -> float | None:
    """The number as a float, or ``None`` when it is not a finite number."""
    try:
        number = float(item)
    except OverflowError:  # an integer too large to be a float
        return None
    return number if math.isfinite(number) else None


def numbers_or_missing(
    numbers: Mapping[str, NumberOrMissing],
) -> dict[str, float] | ResultMissing:
    """Every argument as a finite float, or the reason why nothing is computed.

    A missing argument comes first (C3.3): ``MISSING_INPUT``, the detail names
    every missing argument with its own reason. Then an argument that is not
    a finite number: ``NOT_COMPUTABLE``, named likewise.
    """
    absent = [
        describe_missing(name, item)
        for name, item in numbers.items()
        if is_missing(item)
    ]
    if absent:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(absent))
    values = {name: finite(item) for name, item in numbers.items()}
    not_finite = [name for name, value in values.items() if value is None]
    if not_finite:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="; ".join(f"{name} is not a finite number" for name in not_finite),
        )
    return values


def outside(
    values: Mapping[str, float],
    names: Iterable[str],
    holds: Callable[[float], bool],
    what: str,
) -> ResultMissing | None:
    """``NOT_COMPUTABLE`` naming every argument of ``names`` for which ``holds`` fails."""
    failing = [name for name in names if not holds(values[name])]
    if not failing:
        return None
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail="; ".join(f"{name} {what}" for name in failing),
    )


def is_fraction(value: float) -> bool:
    """Zero to one, both included: what a fraction can be."""
    return 0 <= value <= 1


def is_not_negative(value: float) -> bool:
    return value >= 0


def units_differ(
    first: str, first_unit: str, second: str, second_unit: str, how: str
) -> ResultMissing | None:
    """``REASON_UNIT_NOT_ACCEPTED`` when two unit strings are not the same text."""
    if first_unit == second_unit:
        return None
    return ResultMissing(
        reason=REASON_UNIT_NOT_ACCEPTED,
        detail=(
            f"{first} is in '{first_unit}' and {second} in '{second_unit}': "
            f"the two are {how} as given and need one unit"
        ),
    )


def no_finite_result(function: str, step: str) -> ResultMissing:
    """The inputs are present and the form gives no finite real number."""
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail=f"{function}: {step} is not a finite real number for these arguments",
    )


def real(number: float) -> float:
    """The result of one step of a form, when it is a finite real number."""
    if isinstance(number, complex) or not math.isfinite(number):
        raise ArithmeticError
    return number
