"""The surface layer on a fallow day of EP3 (decisions D110, D111, D115, D116 of #77).

Unit ``l1/water-fallow-residue`` (issue #217). A fallow day is a day of the
rotation, repeated over the years of the climate record (D47), on which no
component carries a crop. On such a day the water entry point
(``engine/water/exposure.py``):

- treats the fallow as weed-free (D111, declared as an assumption): no crop
  reaches the balance, so the balance transpires nothing;
- takes the cover fraction ``fc`` and the wetted fraction ``fw`` of the surface
  layer from two records for a day with no crop (D110 gives them as ``fc = 0``
  and ``fw = 1``; the values are records a person writes, never written here);
- reduces the total evaporable water by the surface residue cover of the
  fallow (D110), with the readily evaporable water not above it.

The cover is one value per fallow, constant over the fallow (D110, D115), read
from one record that both engines read (D116). The fallow is named by the crop
that follows it: the cover of D115 is the cover at the sowing of that crop.

Unit ``l1/water-ep3-repeat-d47`` (issue #253): ``following_crop`` takes the
sowings of the repeated rotation instead of a calendar, so the fallow after
the last component of a cycle is followed by the first sowing of the next
cycle. The repetition itself is ``engine.calendar.repeat_over_record``; this
module holds no rule of it and is given plain dates.

This module holds the three pure steps of that day; ``exposure.py`` reads the
records and chains them. Status: PROPOSED (blueprint section 3.7); see
engine/water/EXPOSURE.md, choices 18 to 21 and OPEN 30 to 35.

Pure functions: no file, no network, no clock, no global state; arguments are
not changed. The numbers are ``0`` and ``1``, the bounds of a fraction and the
whole of the total evaporable water; no value of the method is here.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Iterable

from contracts.results.models import Missing

__all__ = [
    "NO_FOLLOWING_CROP",
    "SOWING_NOT_KNOWN",
    "TWO_FOLLOWING_CROPS",
    "following_crop",
    "mulched_total_evaporable_water",
    "readily_evaporable_water_not_above",
]

Number = float | Missing

# --- detail texts: PROPOSED, English for developers -------------------------

NO_FOLLOWING_CROP = (
    "the fallow of the day has no crop that follows it in the rotation repeated "
    "over the years of the climate record (decision D47 of issue #77): no "
    "component of the calendar has a start date, so the record of its surface "
    "residue cover cannot be named: the cover of a fallow is read by the crop "
    "sown after it (decisions D110 and D115 of issue #77, scope PROPOSED, OPEN "
    "31 of engine/water/EXPOSURE.md)"
)
SOWING_NOT_KNOWN = (
    "the crop that follows the fallow of the day is not known: a component of "
    "the calendar has no start date and could be sown before the first dated "
    "sowing after the day, so the record of the surface residue cover of the "
    "fallow, read by the crop sown after it (decisions D110 and D115 of issue "
    "#77), cannot be named"
)
TWO_FOLLOWING_CROPS = (
    "two components with different crops start on the first sowing after the "
    "fallow of the day, so the crop that follows the fallow, which names the "
    "record of its surface residue cover, is not one (D110, D115)"
)


# --- the fallow and the crop that follows it -----------------------------------


def following_crop(
    sowings: Iterable[tuple[dt.date, str]],
    undated_sowings: Iterable[tuple[dt.date, dt.date, str]],
) -> Callable[[dt.date], str | Missing]:
    """The crop identifier of the component sown first after a fallow day, or why it is not known.

    PROPOSED (choice 19 of EXPOSURE.md). ``sowings`` holds the start date and
    the crop identifier of every component of the repeated rotation whose
    start date is known; ``undated_sowings`` holds, for every component whose
    start date is missing, the first and the last day it can be sown on and
    its component identifier. The entry point builds both from
    ``engine.calendar.repeat_over_record`` (unit #253); nothing of the
    repetition is computed here.

    The day is one on which no component carries a crop. The fallow it
    belongs to ends the day before the next sowing: the first start date
    after the day. Its crop names the fallow.

    - a component with no start date that can be sown after the day, and on
      or before that sowing (or when there is none): ``MISSING_INPUT`` with
      SOWING_NOT_KNOWN and the component identifiers;
    - no sowing after the day: ``MISSING_INPUT`` with NO_FOLLOWING_CROP;
    - components with different crops on that date: ``NOT_COMPUTABLE`` with
      TWO_FOLLOWING_CROPS.
    """
    dated = sorted(sowings)
    undated = list(undated_sowings)

    def crop(day: dt.date) -> str | Missing:
        later = [(start, crop_id) for start, crop_id in dated if start > day]
        sowing = min((start for start, _ in later), default=None)
        unknown = sorted(
            {
                component_id
                for first, last, component_id in undated
                if last > day and (sowing is None or first <= sowing)
            }
        )
        if unknown:
            names = ", ".join(repr(name) for name in unknown)
            return Missing(
                reason="MISSING_INPUT",
                detail=f"{SOWING_NOT_KNOWN}: component(s) {names}",
            )
        if sowing is None:
            return Missing(reason="MISSING_INPUT", detail=NO_FOLLOWING_CROP)
        crops = sorted({crop_id for start, crop_id in later if start == sowing})
        if len(crops) != 1:
            return Missing(reason="NOT_COMPUTABLE", detail=TWO_FOLLOWING_CROPS)
        (only,) = crops
        return only

    return crop


# --- the surface layer of a fallow day -----------------------------------------


def _missing(what: str, operands: dict[str, Number]) -> Missing | None:
    """A ``MISSING_INPUT`` naming every missing operand with its reason, or ``None``."""
    names = [
        f"{name} ({value.reason})"
        for name, value in operands.items()
        if isinstance(value, Missing)
    ]
    if not names:
        return None
    return Missing(reason="MISSING_INPUT", detail=f"{what}: " + ", ".join(names))


def _not_computable(detail: str) -> Missing:
    return Missing(reason="NOT_COMPUTABLE", detail=detail)


def mulched_total_evaporable_water(
    total_evaporable_water: Number,
    residue_cover: Number,
    *,
    reduction_per_increment: Number,
    cover_increment: Number,
) -> Number:
    """The total evaporable water of a fallow day, reduced by its residue cover.

    Decision D110 of #77, after FAO-56 chapter 11, "Surface covered with dead
    vegetation": the total evaporable water is "reduced by 5 % for each 10 %
    of soil surface effectively covered by an organic mulch". Form PROPOSED,
    the reduction taken in proportion to the cover (choice 20):

        TEW_fallow = TEW * (1 - reduction_per_increment * cover / cover_increment)

    with ``cover`` the fraction of the soil surface effectively covered by
    residue, ``reduction_per_increment`` the fraction of TEW removed per
    increment of cover (the 5 % of D110) and ``cover_increment`` the
    increment of cover, as a fraction of the surface (the 10 % of D110). Both
    constants are records a person transcribes; none is written here.

    Returns a number, or:

    - ``MISSING_INPUT`` naming each operand that is missing, with its reason;
    - ``NOT_COMPUTABLE`` for a cover outside zero to one, a cover increment
      not above zero, a reduction below zero, or a result that is not a
      finite number above zero (a reduction that removes all the evaporable
      water is outside what the surface layer computes).
    """
    missing = _missing(
        "the total evaporable water of a day with no crop",
        {
            "total_evaporable_water": total_evaporable_water,
            "surface_residue_cover": residue_cover,
            "reduction_per_increment": reduction_per_increment,
            "cover_increment": cover_increment,
        },
    )
    if missing is not None:
        return missing
    numbers = (
        total_evaporable_water,
        residue_cover,
        reduction_per_increment,
        cover_increment,
    )
    if not all(math.isfinite(value) for value in numbers):
        return _not_computable(
            "the total evaporable water of a day with no crop: an operand is not "
            "a finite number"
        )
    if not 0 <= residue_cover <= 1:
        return _not_computable(
            "the surface residue cover of the fallow lies outside zero to one: it "
            "is a fraction of the soil surface (D110)"
        )
    if not cover_increment > 0:
        return _not_computable(
            "the cover increment of the mulch reduction is not above zero (D110)"
        )
    if reduction_per_increment < 0:
        return _not_computable(
            "the reduction of the total evaporable water per increment of cover is "
            "below zero (D110)"
        )
    value = total_evaporable_water * (
        1 - reduction_per_increment * residue_cover / cover_increment
    )
    if not math.isfinite(value) or value <= 0:
        return _not_computable(
            "the residue cover of the fallow leaves no evaporable water in the "
            "surface layer (the reduction of D110 reaches or passes the whole of "
            "the total evaporable water)"
        )
    return value


def readily_evaporable_water_not_above(
    readily_evaporable_water: Number, total_evaporable_water: Number
) -> Number:
    """The readily evaporable water of a fallow day: not above its total evaporable water.

    D110: "with REW not above TEW" (FAO-56 chapter 11). The smaller of the two;
    a missing operand is ``MISSING_INPUT`` naming it, a ``NOT_COMPUTABLE``
    total is passed on as it is.
    """
    if (
        isinstance(total_evaporable_water, Missing)
        and total_evaporable_water.reason == "NOT_COMPUTABLE"
    ):
        return total_evaporable_water
    missing = _missing(
        "the readily evaporable water of a day with no crop",
        {
            "readily_evaporable_water": readily_evaporable_water,
            "total_evaporable_water": total_evaporable_water,
        },
    )
    if missing is not None:
        return missing
    return min(readily_evaporable_water, total_evaporable_water)
