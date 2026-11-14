"""Annual soil-loss product of docs/METHODS.md M1.1, with a unit guard.

Status: PROPOSED (blueprint section 3.7). The behaviour is described in
engine/erosion/EQUATION.md and takes effect only when people approve it.

``annual_soil_loss`` multiplies the five factors of M1.1 and nothing else.
It does not compute a factor, it reads no parameter and it knows no unit:
the accepted unit string of each factor is supplied by the caller, and so
is the reason code of the unit guard (question Q11 of
contracts/ENTRYPOINTS.md is not decided). This module holds no number and
no unit string.

A pure function: no file, no network, no clock, no global state. It does
not change its arguments, and the same arguments give the same result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import get_args

from contracts.results.models import Missing, ReasonCode

# The five factors, in the order docs/METHODS.md M1.1 writes the product.
# The factors are multiplied in this order whatever the order of the
# arguments, and a result that names factors names them in this order.
FACTOR_NAMES: tuple[str, ...] = ("r", "k", "ls", "c", "p")


@dataclass(frozen=True)
class Factor:
    """One factor of the product: a number or a missing value, and its unit.

    ``value`` is a number, or the ``Missing`` of contracts/results/models.py
    with the reason the factor has no number (C3.1). ``unit`` is the unit
    string the factor arrives in; it is kept when the value is missing
    (C3.1).
    """

    value: float | Missing
    unit: str


@dataclass(frozen=True)
class AcceptedUnits:
    """The one unit string the product accepts for each factor.

    Every field is supplied by the caller and none has a default: the unit
    strings are written by a person (docs/METHODS.md M1.7).
    """

    r: str
    k: str
    ls: str
    c: str
    p: str


def _is_number(value: object) -> bool:
    """True for an ``int`` or a ``float``; a boolean is not a number here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large to be a float
        return False


def _check_arguments(
    factors: dict[str, Factor],
    accepted_units: AcceptedUnits,
    unit_guard_reason: str,
) -> None:
    """Raise for a defect of the caller; return nothing otherwise."""
    for name, factor in factors.items():
        if not isinstance(factor, Factor):
            raise TypeError(
                f"argument '{name}' must be a Factor, not {type(factor).__name__}"
            )
        if not isinstance(factor.value, Missing) and not _is_number(factor.value):
            raise TypeError(
                f"the value of factor '{name}' must be a number or the Missing of "
                f"contracts/results/models.py, not {type(factor.value).__qualname__} "
                f"of module {type(factor.value).__module__}"
            )
        if not isinstance(factor.unit, str):
            raise TypeError(
                f"the unit of factor '{name}' must be a string, "
                f"not {type(factor.unit).__name__}"
            )
    if not isinstance(accepted_units, AcceptedUnits):
        raise TypeError(
            "argument 'accepted_units' must be an AcceptedUnits, "
            f"not {type(accepted_units).__name__}"
        )
    for name in FACTOR_NAMES:
        accepted = getattr(accepted_units, name)
        if not isinstance(accepted, str):
            raise TypeError(
                f"the accepted unit of factor '{name}' must be a string, "
                f"not {type(accepted).__name__}"
            )
    if unit_guard_reason not in get_args(ReasonCode):
        raise ValueError(
            "argument 'unit_guard_reason' must be a reason code of convention C3.2"
        )


def _describe_missing(name: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"factor '{name}' is missing (reason {missing.reason})"
    return f"factor '{name}' is missing (reason {missing.reason}: {missing.detail})"


def annual_soil_loss(
    *,
    r: Factor,
    k: Factor,
    ls: Factor,
    c: Factor,
    p: Factor,
    accepted_units: AcceptedUnits,
    unit_guard_reason: ReasonCode,
) -> float | Missing:
    """The product of the five factors of docs/METHODS.md M1.1, or why there is none.

    Returns the product as a ``float`` only when every factor is a finite
    number in the unit string that ``accepted_units`` names for it. In
    every other case no factor is multiplied and the result is a ``Missing``
    (contracts/results/models.py), never zero:

    - a factor is missing: reason ``MISSING_INPUT``; ``detail`` names every
      missing factor (C3.3);
    - a factor is in another unit string than the accepted one: reason
      ``unit_guard_reason``; ``detail`` names every such factor (the unit
      guard; rule G4 and question Q11 of contracts/ENTRYPOINTS.md);
    - a factor, or the product, is not a finite number: reason
      ``NOT_COMPUTABLE``; ``detail`` names every such factor.

    The first of the three that applies, in that order, is the one returned.

    Unit strings are compared exactly as written. The function does not
    know what a unit string means and attaches no unit to the product: the
    product is in the unit of convention C1.2 only if the accepted unit
    strings, written by a person, make it so.

    Raises ``TypeError`` when an argument is not of the type the signature
    names, and ``ValueError`` when ``unit_guard_reason`` is not a reason
    code of convention C3.2. Both are defects of the caller.
    """
    factors = dict(zip(FACTOR_NAMES, (r, k, ls, c, p), strict=True))
    _check_arguments(factors, accepted_units, unit_guard_reason)

    missing = [
        _describe_missing(name, factor.value)
        for name, factor in factors.items()
        if isinstance(factor.value, Missing)
    ]
    if missing:
        return Missing(reason="MISSING_INPUT", detail="; ".join(missing))

    wrong_unit = [
        f"factor '{name}' is in the unit '{factor.unit}', "
        f"not in the accepted unit '{getattr(accepted_units, name)}'"
        for name, factor in factors.items()
        if factor.unit != getattr(accepted_units, name)
    ]
    if wrong_unit:
        return Missing(reason=unit_guard_reason, detail="; ".join(wrong_unit))

    not_finite = [
        f"factor '{name}' is not a finite number"
        for name, factor in factors.items()
        if not _is_finite(factor.value)
    ]
    if not_finite:
        return Missing(reason="NOT_COMPUTABLE", detail="; ".join(not_finite))

    product = math.prod(float(factor.value) for factor in factors.values())
    if not math.isfinite(product):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="the product of the five factors is not a finite number",
        )
    return product
