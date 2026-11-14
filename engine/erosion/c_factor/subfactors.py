"""Sub-factors of the soil-loss ratio of a period (docs/METHODS.md M1.5, D45). PROPOSED.

Decision D45 of issue #77 keeps two sub-factors of source S1: canopy cover,
and surface residue cover. The other sub-factors (surface roughness, soil
biomass, soil consolidation, prior land use) are set to one as a declared
limit of the method. The soil-loss ratio of a period is the product of the
sub-factors; this module multiplies the two that are kept, and records the
four that are set to one in every result, so the limit is never silent.

The forms below are PROPOSED. Their source is to be confirmed by a person
against S1; the session that wrote them did not read S1, and it writes no
coefficient of S1 here, in a default, a test or a comment::

    canopy sub-factor          CC = 1 - canopy_cover * exp(-fall_height_coefficient * fall_height)
    surface-cover sub-factor   SC = exp(-surface_cover_coefficient * surface_residue_cover)
    soil-loss ratio            SLR = CC * SC

``canopy_cover`` and ``surface_residue_cover`` are fractions of the soil, from
zero to one. ``fall_height`` is the height from which drops fall from the
canopy. ``fall_height_coefficient`` and ``surface_cover_coefficient`` are
arguments without a default: the caller supplies each one, read from the
parameter catalogue (README.md of this folder, "Constants a person has to
transcribe").

Pure functions: no file, no network, no clock, no argument is changed. A
result that is not computed is the ``Missing`` of contracts/results/models.py
with its reason: never zero, never a default, never "not a number".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from contracts.results.models import Missing as ResultMissing

from ._numbers import (
    NumberOrMissing,
    check_text,
    check_types,
    is_fraction,
    is_not_negative,
    no_finite_result,
    numbers_or_missing,
    outside,
    real,
    units_differ,
)

__all__ = [
    "DECLARED_LIMIT",
    "SET_TO_ONE",
    "SoilLossRatio",
    "canopy_subfactor",
    "soil_loss_ratio",
    "surface_cover_subfactor",
]

# D45 of issue #77: the sub-factors of S1 that are not computed and stand at
# one. Their names are PROPOSED identifiers, in the order D45 lists them.
SET_TO_ONE: tuple[str, ...] = (
    "surface_roughness",
    "soil_biomass",
    "soil_consolidation",
    "prior_land_use",
)

# Where the limit is declared. A pointer for the reader of a result, not the
# text on the limits of the method (that is a separate unit, M1.1).
DECLARED_LIMIT = (
    "sub-factors set to one as a declared limit of the method: "
    "decision D45 of issue #77, docs/METHODS.md M1.5"
)


@dataclass(frozen=True)
class SoilLossRatio:
    """The soil-loss ratio of one period, and what it is made of.

    - ``value``: the product of the two sub-factors that are computed, or the
      ``Missing`` of the results contract with its reason.
    - ``canopy`` and ``surface_cover``: the two sub-factors as they were
      passed in, number or ``Missing``.
    - ``set_to_one``: the sub-factors of S1 that stand at one (D45). Always
      ``SET_TO_ONE``, also when ``value`` is missing.
    - ``limit``: where that limit is declared, ``DECLARED_LIMIT``.
    """

    value: float | ResultMissing
    canopy: NumberOrMissing
    surface_cover: NumberOrMissing
    set_to_one: tuple[str, ...]
    limit: str


def canopy_subfactor(
    *,
    canopy_cover: NumberOrMissing,
    fall_height: NumberOrMissing,
    fall_height_unit: str,
    fall_height_coefficient: NumberOrMissing,
    fall_height_coefficient_per_unit: str,
) -> float | ResultMissing:
    """The canopy sub-factor ``CC`` of the soil-loss ratio. PROPOSED form.

    ``CC = 1 - canopy_cover * exp(-fall_height_coefficient * fall_height)``.

    Arguments, all by name and none with a default:

    - ``canopy_cover``: the fraction of the soil under the canopy, zero to one.
    - ``fall_height``: the fall height of drops from the canopy, zero or more.
    - ``fall_height_unit``: the unit string of ``fall_height``.
    - ``fall_height_coefficient``: the constant of the form, from the
      parameter catalogue. Its unit is one over a length.
    - ``fall_height_coefficient_per_unit``: the length whose inverse is the
      unit of the coefficient. It must be the same text as
      ``fall_height_unit``: no length is converted here.

    Returns ``CC`` as a float, or a ``Missing``:

    - ``MISSING_INPUT`` when an argument is missing; the detail names each one.
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, when
      ``canopy_cover`` is outside zero to one, when ``fall_height`` or
      ``fall_height_coefficient`` is negative (each named; nothing is
      clipped; the refusal of a negative coefficient is PROPOSED), when
      the two unit strings differ, or when the form gives no finite real number.

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {
        "canopy_cover": canopy_cover,
        "fall_height": fall_height,
        "fall_height_coefficient": fall_height_coefficient,
    }
    check_types(numbers)
    check_text("fall_height_unit", fall_height_unit)
    check_text("fall_height_coefficient_per_unit", fall_height_coefficient_per_unit)

    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values, ["canopy_cover"], is_fraction, "is outside zero to one"
    ) or outside(
        values,
        ["fall_height", "fall_height_coefficient"],
        is_not_negative,
        "is negative",
    )
    if refused is not None:
        return refused
    refused = units_differ(
        "fall_height_coefficient (per unit)",
        fall_height_coefficient_per_unit,
        "fall_height",
        fall_height_unit,
        "multiplied",
    )
    if refused is not None:
        return refused
    try:
        exponential = real(
            math.exp(-values["fall_height_coefficient"] * values["fall_height"])
        )
        return real(1 - values["canopy_cover"] * exponential)
    except (ArithmeticError, OverflowError):
        return no_finite_result("canopy_subfactor", "CC")


def surface_cover_subfactor(
    *,
    surface_residue_cover: NumberOrMissing,
    surface_cover_coefficient: NumberOrMissing,
) -> float | ResultMissing:
    """The surface-cover sub-factor ``SC`` of the soil-loss ratio. PROPOSED form.

    ``SC = exp(-surface_cover_coefficient * surface_residue_cover)``.

    Arguments, all by name and none with a default:

    - ``surface_residue_cover``: the fraction of the soil covered by residue,
      zero to one (not percent: README.md, OPEN).
    - ``surface_cover_coefficient``: the constant of the form, from the
      parameter catalogue.

    Returns ``SC`` as a float, or a ``Missing``:

    - ``MISSING_INPUT`` when an argument is missing; the detail names each one.
    - ``NOT_COMPUTABLE`` when an argument is not a finite number, when the
      cover is outside zero to one or the coefficient is negative (named;
      nothing is clipped; the refusal of a negative coefficient is
      PROPOSED: it would give a sub-factor above one), or when the
      form gives no finite real number.

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {
        "surface_residue_cover": surface_residue_cover,
        "surface_cover_coefficient": surface_cover_coefficient,
    }
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        return values
    refused = outside(
        values, ["surface_residue_cover"], is_fraction, "is outside zero to one"
    ) or outside(values, ["surface_cover_coefficient"], is_not_negative, "is negative")
    if refused is not None:
        return refused
    try:
        return real(
            math.exp(
                -values["surface_cover_coefficient"] * values["surface_residue_cover"]
            )
        )
    except (ArithmeticError, OverflowError):
        return no_finite_result("surface_cover_subfactor", "SC")


def soil_loss_ratio(
    *,
    canopy: NumberOrMissing,
    surface_cover: NumberOrMissing,
) -> SoilLossRatio:
    """The soil-loss ratio of one period: the product of its sub-factors (D45).

    ``canopy`` is the result of ``canopy_subfactor`` and ``surface_cover`` the
    result of ``surface_cover_subfactor``, each a number or a ``Missing``.
    The four other sub-factors of S1 are not multiplied: they stand at one
    by D45 and are named in ``set_to_one`` of the result.

    ``value`` of the result is the product, or a ``Missing``:

    - ``MISSING_INPUT`` when a sub-factor is missing; the detail names it
      with its own reason.
    - ``NOT_COMPUTABLE`` when a sub-factor, or the product, is not a finite
      number.

    Raises ``TypeError`` for an argument of another type.
    """
    numbers = {"canopy": canopy, "surface_cover": surface_cover}
    check_types(numbers)
    values = numbers_or_missing(numbers)
    if isinstance(values, ResultMissing):
        value: float | ResultMissing = values
    else:
        try:
            value = real(values["canopy"] * values["surface_cover"])
        except ArithmeticError:
            value = no_finite_result("soil_loss_ratio", "the product")
    return SoilLossRatio(
        value=value,
        canopy=canopy,
        surface_cover=surface_cover,
        set_to_one=SET_TO_ONE,
        limit=DECLARED_LIMIT,
    )
