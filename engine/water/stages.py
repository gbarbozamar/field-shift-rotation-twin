"""The four FAO-56 growth stages inside one crop period, and the value of a day by stage.

Unit ``l1/water-crop-stages`` (issue #206). Private to the water entry point
(``engine/water/exposure.py``); EP2 does not change (D56): the stages are
placed inside EP3, from the period of a calendar component.

Two pure functions:

- ``place_stages`` lays the four stages of FAO-56 chapter 6 (initial,
  development, mid, late) end to end from the first day of a crop period
  (its sowing), using the length of each stage in days. The lengths come
  from the parameter catalogue, by crop (D78, D79); none is written here.
- ``by_stage`` gives the value of one day from three values, one at the
  initial stage, one at the mid stage and one at the end of the late stage:
  constant in the initial and mid stages, and a straight line between them in
  the development and late stages (the construction of the crop coefficient
  curve of FAO-56 chapters 6 and 7, Eq. 66 as this module reads it). EP3
  uses it for the basal crop coefficient (``Kcb`` ini, mid, end; D78) and
  for the root depth (an initial depth, then the maximum root depth; D78,
  provisional curves).

Status: PROPOSED (blueprint section 3.7): the stage words, the identifiers
of the stage lengths, the day numbering, the straight line of ``by_stage``
for both uses, the answer when the lengths do not fill the period, and every
``detail``. See EXPOSURE.md in this folder, choices 6, 16 and 17 and OPEN 4
and 25 to 29.

Pure function (G1): no file, no network, no clock, no environment variable,
and the arguments are not changed. The only integer is the one of day
arithmetic (days counted from one, C5.2).
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass

from contracts.results.models import Missing

__all__ = [
    "GROWTH_STAGES",
    "STAGE_LENGTH_PARAMETERS",
    "StageDay",
    "by_stage",
    "place_stages",
]

# The four stages of FAO-56 chapter 6, in the order they follow one another.
GROWTH_STAGES: tuple[str, ...] = ("initial", "development", "mid", "late")
# The two stages over which the value of a day is a straight line.
SLOPED_STAGES: tuple[str, ...] = ("development", "late")

# The identifier of the length of each stage, in days, read by crop (scope
# {"crop": <crop>}). PROPOSED: issue #206 names this form; no record is
# drafted for them yet.
STAGE_LENGTH_PREFIX = "fao56_stage_length_"
STAGE_LENGTH_PARAMETERS: dict[str, str] = {
    stage: f"{STAGE_LENGTH_PREFIX}{stage}" for stage in GROWTH_STAGES
}

# Days counted from one (C5.2): the first day of the period is day one.
_FIRST = 1
_ONE_DAY = dt.timedelta(days=_FIRST)


@dataclass(frozen=True)
class StageDay:
    """Where one day of a crop period lies among the stages.

    ``stage`` is one of GROWTH_STAGES; ``day_in_stage`` counts the days of
    that stage from one, so that the last day of the stage has
    ``day_in_stage == stage_length``.
    """

    stage: str
    day_in_stage: int
    stage_length: int

    @property
    def fraction(self) -> float:
        """The share of the stage reached at the end of the day: from
        ``1 / stage_length`` on its first day to one on its last day."""
        return self.day_in_stage / self.stage_length


def _whole_days(value: float) -> int | None:
    """The length as a whole number of days, at least one; ``None`` otherwise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not float(value).is_integer() or value < _FIRST:
        return None
    return int(value)


def place_stages(
    first: dt.date,
    last: dt.date,
    lengths: Mapping[str, float],
    *,
    what: str,
) -> dict[dt.date, StageDay] | Missing:
    """The stage of every day from ``first`` to ``last`` (both inclusive).

    ``lengths`` holds the length in days of each stage of GROWTH_STAGES, as
    numbers; the caller answers a missing length before (D79). ``what``
    names the period and its crop in a ``detail``.

    The initial stage begins on ``first`` (the sowing) and each stage begins
    the day after the one before it ends. Returns ``NOT_COMPUTABLE`` (the
    method does not cover the case, G4), never a guess:

    - when a length is not a whole number of days of at least one;
    - when the lengths do not add up to the days of the period. FAO-56 does
      not say how to fit stage lengths to a period they do not fill, so the
      whole period is left missing (OPEN 25 of EXPOSURE.md).

    Raises ``ValueError`` when ``last`` comes before ``first`` (the calendar
    contract does not allow it) or a stage of GROWTH_STAGES has no length.
    """
    if last < first:
        raise ValueError(f"{what}: the period ends before it starts")
    absent = [stage for stage in GROWTH_STAGES if stage not in lengths]
    if absent:
        raise ValueError(f"{what}: no length given for the stage(s) {absent}")
    whole: dict[str, int] = {}
    not_whole: list[str] = []
    for stage in GROWTH_STAGES:
        days = _whole_days(lengths[stage])
        if days is None:
            not_whole.append(STAGE_LENGTH_PARAMETERS[stage])
        else:
            whole[stage] = days
    if not_whole:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"the growth stages of {what} cannot be placed: the stage length(s) "
                + ", ".join(f"'{name}'" for name in not_whole)
                + " are not a whole number of days of at least one (PROPOSED, "
                "issue #206)"
            ),
        )
    period = (last - first).days + _FIRST
    total = sum(whole.values())
    if total != period:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"the growth stages of {what} cannot be placed: the four stage "
                f"lengths add up to {total} day(s) and the period holds {period} "
                "day(s), and how FAO-56 stage lengths are fitted to a period they "
                "do not fill is not decided, so no stage is guessed (OPEN 25 of "
                "engine/water/EXPOSURE.md, issue #206)"
            ),
        )
    stages: dict[dt.date, StageDay] = {}
    day = first
    for stage in GROWTH_STAGES:
        for day_in_stage in range(_FIRST, whole[stage] + _FIRST):
            stages[day] = StageDay(
                stage=stage, day_in_stage=day_in_stage, stage_length=whole[stage]
            )
            day += _ONE_DAY
    return stages


def by_stage(
    stage_day: StageDay,
    initial: float | Missing,
    mid: float | Missing,
    end: float | Missing,
) -> float | Missing:
    """The value of one day from its stage and three values (PROPOSED form).

    - initial stage: ``initial``;
    - development stage: from ``initial`` to ``mid`` in a straight line,
      ``initial + fraction * (mid - initial)``, reaching ``mid`` on its last
      day;
    - mid stage: ``mid``;
    - late stage: from ``mid`` to ``end`` in a straight line,
      ``mid + fraction * (end - mid)``, reaching ``end`` on its last day.

    ``fraction`` is ``StageDay.fraction``. This is the construction of the
    crop coefficient curve of FAO-56 (chapter 6, Eq. 66, with ``i`` the day
    of the season counted from one), applied as written; the form is
    PROPOSED (issue #206). Only the values the stage of the day needs are
    read: a missing one makes the day missing with its reason
    (``MISSING_INPUT``, naming what is missing), the others are not looked
    at.
    """
    needed: tuple[float | Missing, ...] = {
        "initial": (initial,),
        "development": (initial, mid),
        "mid": (mid,),
        "late": (mid, end),
    }[stage_day.stage]
    absent = [item for item in needed if isinstance(item, Missing)]
    if absent:
        return Missing(
            reason="MISSING_INPUT",
            detail="; ".join(item.detail or item.reason for item in absent),
        )
    if stage_day.stage not in SLOPED_STAGES:
        (value,) = needed
        return value
    start, stop = needed
    return start + stage_day.fraction * (stop - start)
