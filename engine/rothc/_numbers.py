"""Checks shared by the modules of ``engine/rothc/``. PROPOSED.

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

# The two existing ``Missing`` shapes of the contracts (question 24 of
# contracts/inputs/README.md). Either is accepted as an argument; a result is
# always the one of contracts/results/models.py.
MISSING_SHAPES = (InputMissing, ResultMissing)

# PROPOSED. Reason code of a result that is not computed because two unit
# strings that must be the same text are not. The code for "a unit the engine
# does not accept" is not decided: Q11 of contracts/ENTRYPOINTS.md. The same
# choice as engine/amg/, engine/erosion/ and engine/water/.
REASON_UNIT_NOT_ACCEPTED = "NOT_COMPUTABLE"

Number = int | float
NumberOrMissing = int | float | InputMissing | ResultMissing


def is_missing(item: object) -> bool:
    return isinstance(item, MISSING_SHAPES)


def is_number(item: object) -> bool:
    return isinstance(item, (int, float)) and not isinstance(item, bool)


def check_types(numbers: Mapping[str, object]) -> None:
    """An argument that is neither a number nor a ``Missing`` is a defect of the caller."""
    for name, item in numbers.items():
        if is_missing(item) or is_number(item):
            continue
        raise TypeError(
            f"{name}: expected a number, or a Missing of the contract models with "
            f"its reason; got {type(item).__name__}. A missing value is never "
            "passed as None"
        )


def check_text(name: str, item: object) -> None:
    if not isinstance(item, str):
        raise TypeError(f"{name}: expected text, got {type(item).__name__}")


def check_mapping(name: str, item: object) -> None:
    if not isinstance(item, Mapping):
        raise TypeError(f"{name}: expected a mapping, got {type(item).__name__}")
    for key in item:
        if not isinstance(key, str):
            raise TypeError(f"{name}: every key is text, got {type(key).__name__}")


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


def _absent_detail(missing_items: list[tuple[str, InputMissing | ResultMissing]]) -> str:
    """The detail of a missing-input refusal, per the lead coordinator's request.

    Every absent argument named with its reason while they differ; when they
    all carry one reason and one detail, the count with the first and the last
    name instead — a series of hundreds of missing points says how many it is
    missing, not each one by name. No reason and no value changes.
    """
    reasons = {item.reason for _, item in missing_items}
    details = {item.detail for _, item in missing_items}
    if len(reasons) == 1 and len(details) == 1 and len(missing_items) > 1:
        first = missing_items[0][0]
        last = missing_items[-1][0]
        summary = f"{len(missing_items)} arguments are missing (from {first} to {last}), reason {reasons.pop()}"
        detail = details.pop()
        if detail is not None:
            summary += f": {detail}"
        return summary
    return "; ".join(describe_missing(name, item) for name, item in missing_items)


def numbers_or_missing(
    numbers: Mapping[str, NumberOrMissing],
) -> dict[str, float] | ResultMissing:
    """Every argument as a finite float, or the reason why nothing is computed.

    A missing argument comes first (C3.3): ``MISSING_INPUT``, the detail names
    every missing argument with its own reason. Then an argument that is not
    a finite number: ``NOT_COMPUTABLE``, named likewise.
    """
    missing_items = [(name, item) for name, item in numbers.items() if is_missing(item)]
    if missing_items:
        return ResultMissing(reason="MISSING_INPUT", detail=_absent_detail(missing_items))
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


def is_positive(value: float) -> bool:
    return value > 0


def units_differ(names_and_units: Mapping[str, str], how: str) -> ResultMissing | None:
    """``REASON_UNIT_NOT_ACCEPTED`` when the unit strings given are not all the same text."""
    if len(set(names_and_units.values())) <= 1:
        return None
    listed = " and ".join(
        f"{name} is in '{unit}'" for name, unit in names_and_units.items()
    )
    return ResultMissing(
        reason=REASON_UNIT_NOT_ACCEPTED,
        detail=f"{listed}: the units are {how} as given and need one unit",
    )


def unit_is_not(
    name: str, unit: str, expected: str, how: str
) -> ResultMissing | None:
    """``REASON_UNIT_NOT_ACCEPTED`` when one unit string is not the expected text."""
    if unit == expected:
        return None
    return ResultMissing(
        reason=REASON_UNIT_NOT_ACCEPTED,
        detail=(
            f"{name} is in '{unit}'; expected '{expected}', {how}: "
            "nothing is converted"
        ),
    )


def no_finite_result(function: str, what: str) -> ResultMissing:
    """The inputs are present and the form gives no finite real number."""
    return ResultMissing(
        reason="NOT_COMPUTABLE",
        detail=f"{function}: {what} is not a finite real number for these arguments",
    )


def real(number: float) -> float:
    """The result of one step of a form, when it is a finite real number."""
    if isinstance(number, complex) or not math.isfinite(number):
        raise ArithmeticError
    return number
