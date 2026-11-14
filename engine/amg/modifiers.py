"""The rate coefficient of the active pool and its modifiers. PROPOSED.

The active pool of AMG mineralises at a rate coefficient. Here that
coefficient is a potential rate multiplied by modifiers of soil and climate,
each computed by its own function::

    rate coefficient     k     = potential_rate * product of the modifiers
    temperature          f_T   = shape / (1 + (shape - 1) * exp(sensitivity * (reference_temperature - temperature)))
    moisture             f_W   = 1 / (1 + shape * exp(-sensitivity * water_balance))
    clay                 f_A   = exp(-sensitivity * clay_content)
    carbonate            f_CaCO3 = 1 / (1 + sensitivity * carbonate_content)
    pH                   f_pH  = exp(-sensitivity * (ph - optimum_ph) * (ph - optimum_ph))

Every form is PROPOSED. **Its source is to be confirmed by a person**: the
session that wrote this module read no source of AMG, wrote the forms as
candidates only, and wrote no coefficient of the method here, in a default, a
test or a comment. Which modifiers the source has, and whether it has others
(for example one for the carbon to nitrogen ratio of the soil), is OPEN
(README.md of this folder).

Every constant is an argument with no default; the caller supplies it, read
from the parameter catalogue once its records exist (README.md, "Constants a
person has to transcribe"). Where a constant multiplies an input that has a
unit, the caller states both unit strings and they must be the same text: no
unit is converted here.

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_mapping,
    check_text,
    check_types,
    finite,
    is_not_negative,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
    units_differ,
)

__all__ = [
    "carbonate_modifier",
    "clay_modifier",
    "moisture_modifier",
    "ph_modifier",
    "rate_coefficient",
    "temperature_modifier",
]


def _modifier(
    function: str,
    numbers: Mapping[str, NumberOrMissing],
    not_negative: tuple[str, ...],
    units: Mapping[str, str] | None,
    form: Callable[[dict[str, float]], float],
) -> float | ResultMissing:
    """The checks every modifier makes, in the order of README.md, then its form.

    A modifier that the form makes negative is refused with ``NOT_COMPUTABLE``:
    it would make the rate coefficient negative and the active pool grow by
    mineralisation (PROPOSED, README.md OPEN).
    """
    check_types(numbers)
    for name, unit in (units or {}).items():
        check_text(name, unit)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, not_negative, is_not_negative, "is negative")
    if refused is not None:
        return refused
    if units:
        differ = units_differ(units, "multiplied together")
        if differ is not None:
            return differ
    try:
        result = real(form(values))
    except (ArithmeticError, ValueError):
        return no_finite_result(function, "the modifier")
    if result < 0:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{function}: the modifier is negative for these arguments",
        )
    return result


def temperature_modifier(
    *,
    temperature: NumberOrMissing,
    temperature_unit: str,
    reference_temperature: NumberOrMissing,
    reference_temperature_unit: str,
    shape_coefficient: NumberOrMissing,
    sensitivity_coefficient: NumberOrMissing,
    sensitivity_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The temperature modifier ``f_T`` of the rate coefficient. PROPOSED form.

    ``f_T = shape / (1 + (shape - 1) * exp(sensitivity * (reference_temperature - temperature)))``.
    At the reference temperature ``f_T`` is one, whatever the two coefficients.

    - ``temperature``: the temperature of the step (which one, air or soil,
      and over which period it is averaged, is OPEN).
    - ``reference_temperature``, ``shape_coefficient``,
      ``sensitivity_coefficient``: constants of the method.
    - The three unit strings must be the same text: the sensitivity is per
      degree of the temperature unit, and nothing is converted.

    Returns ``f_T``, or ``MISSING_INPUT`` (an argument is missing) or
    ``NOT_COMPUTABLE`` (an argument is not finite, the unit strings differ,
    or the form gives no finite real number or a negative one).
    """
    return _modifier(
        "temperature_modifier",
        {
            "temperature": temperature,
            "reference_temperature": reference_temperature,
            "shape_coefficient": shape_coefficient,
            "sensitivity_coefficient": sensitivity_coefficient,
        },
        (),
        {
            "temperature_unit": temperature_unit,
            "reference_temperature_unit": reference_temperature_unit,
            "sensitivity_coefficient_per_unit": sensitivity_coefficient_per_unit,
        },
        lambda v: (
            v["shape_coefficient"]
            / (
                1
                + (v["shape_coefficient"] - 1)
                * math.exp(
                    v["sensitivity_coefficient"]
                    * (v["reference_temperature"] - v["temperature"])
                )
            )
        ),
    )


def moisture_modifier(
    *,
    water_balance: NumberOrMissing,
    water_balance_unit: str,
    shape_coefficient: NumberOrMissing,
    sensitivity_coefficient: NumberOrMissing,
    sensitivity_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The moisture modifier ``f_W`` of the rate coefficient. PROPOSED form.

    ``f_W = 1 / (1 + shape * exp(-sensitivity * water_balance))``.

    - ``water_balance``: a depth of water over the step that may be negative.
      What it is (for example precipitation and irrigation less potential
      evapotranspiration) and over which period, is OPEN.
    - ``shape_coefficient``, ``sensitivity_coefficient``: constants of the
      method.
    - ``water_balance_unit`` and ``sensitivity_coefficient_per_unit`` must be
      the same text.

    Returns ``f_W``, or ``MISSING_INPUT`` or ``NOT_COMPUTABLE`` as
    ``temperature_modifier``.
    """
    return _modifier(
        "moisture_modifier",
        {
            "water_balance": water_balance,
            "shape_coefficient": shape_coefficient,
            "sensitivity_coefficient": sensitivity_coefficient,
        },
        (),
        {
            "water_balance_unit": water_balance_unit,
            "sensitivity_coefficient_per_unit": sensitivity_coefficient_per_unit,
        },
        lambda v: (
            1
            / (
                1
                + v["shape_coefficient"]
                * math.exp(-v["sensitivity_coefficient"] * v["water_balance"])
            )
        ),
    )


def clay_modifier(
    *,
    clay_content: NumberOrMissing,
    clay_content_unit: str,
    sensitivity_coefficient: NumberOrMissing,
    sensitivity_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The clay modifier ``f_A`` of the rate coefficient. PROPOSED form.

    ``f_A = exp(-sensitivity * clay_content)``.

    - ``clay_content``: the clay content of the soil, zero or more; a negative
      content is ``NOT_COMPUTABLE``, named.
    - ``clay_content_unit`` and ``sensitivity_coefficient_per_unit`` must be
      the same text.

    Returns ``f_A``, or ``MISSING_INPUT`` or ``NOT_COMPUTABLE``.
    """
    return _modifier(
        "clay_modifier",
        {
            "clay_content": clay_content,
            "sensitivity_coefficient": sensitivity_coefficient,
        },
        ("clay_content",),
        {
            "clay_content_unit": clay_content_unit,
            "sensitivity_coefficient_per_unit": sensitivity_coefficient_per_unit,
        },
        lambda v: math.exp(-v["sensitivity_coefficient"] * v["clay_content"]),
    )


def carbonate_modifier(
    *,
    carbonate_content: NumberOrMissing,
    carbonate_content_unit: str,
    sensitivity_coefficient: NumberOrMissing,
    sensitivity_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The carbonate modifier ``f_CaCO3`` of the rate coefficient. PROPOSED form.

    ``f_CaCO3 = 1 / (1 + sensitivity * carbonate_content)``.

    - ``carbonate_content``: the calcium carbonate content of the soil, zero
      or more; a negative content is ``NOT_COMPUTABLE``, named.
    - ``carbonate_content_unit`` and ``sensitivity_coefficient_per_unit`` must
      be the same text.

    Returns ``f_CaCO3``, or ``MISSING_INPUT`` or ``NOT_COMPUTABLE``.
    """
    return _modifier(
        "carbonate_modifier",
        {
            "carbonate_content": carbonate_content,
            "sensitivity_coefficient": sensitivity_coefficient,
        },
        ("carbonate_content",),
        {
            "carbonate_content_unit": carbonate_content_unit,
            "sensitivity_coefficient_per_unit": sensitivity_coefficient_per_unit,
        },
        lambda v: 1 / (1 + v["sensitivity_coefficient"] * v["carbonate_content"]),
    )


def ph_modifier(
    *,
    ph: NumberOrMissing,
    optimum_ph: NumberOrMissing,
    sensitivity_coefficient: NumberOrMissing,
) -> float | ResultMissing:
    """The pH modifier ``f_pH`` of the rate coefficient. PROPOSED form.

    ``f_pH = exp(-sensitivity * (ph - optimum_ph) * (ph - optimum_ph))``. At
    the optimum pH ``f_pH`` is one. pH has no unit, so no unit string is
    compared.

    Returns ``f_pH``, or ``MISSING_INPUT`` or ``NOT_COMPUTABLE``.
    """
    return _modifier(
        "ph_modifier",
        {
            "ph": ph,
            "optimum_ph": optimum_ph,
            "sensitivity_coefficient": sensitivity_coefficient,
        },
        (),
        None,
        lambda v: math.exp(
            -v["sensitivity_coefficient"]
            * (v["ph"] - v["optimum_ph"])
            * (v["ph"] - v["optimum_ph"])
        ),
    )


def rate_coefficient(
    *,
    potential_rate: NumberOrMissing,
    modifiers: Mapping[str, NumberOrMissing],
) -> float | ResultMissing:
    """The rate coefficient ``k`` of the active pool. PROPOSED form.

    ``k = potential_rate * product of the values of modifiers``.

    - ``potential_rate``: the rate coefficient before any modifier, a constant
      of the method, zero or more. Its time unit is the caller's: it is
      carried to the step as ``rate_coefficient_per_unit``.
    - ``modifiers``: each modifier by name (the name is used only in a
      detail), each zero or more. An empty mapping is accepted and gives the
      potential rate unchanged; which modifiers apply is OPEN.

    Returns ``k``, or:

    - ``MISSING_INPUT`` when the potential rate or a modifier is missing; the
      detail names each one with its reason.
    - ``NOT_COMPUTABLE`` when one is not a finite number, when one is negative
      (named; nothing is clipped), or when the product is not finite.

    Raises ``TypeError`` for an argument of another type.
    """
    check_mapping("modifiers", modifiers)
    numbers = {"potential_rate": potential_rate}
    numbers.update({f"modifier '{name}'": item for name, item in modifiers.items()})
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(values, values.keys(), is_not_negative, "is negative")
    if refused is not None:
        return refused
    product = values["potential_rate"]
    for name in modifiers:
        product *= values[f"modifier '{name}'"]
    if finite(product) is None:
        return no_finite_result("rate_coefficient", "the product")
    return product
