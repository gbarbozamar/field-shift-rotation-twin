"""The days with a live crop in one crop period (decisions D135 and D136 of #77).

Unit ``l1/living-crop-days`` (issue #357). Three readers need the days on
which a live crop stands, under the rules of D135 and D136: the trivial
comparators of soil loss and water (D211, D212) and the monthly soil cover
of RothC (D222). Until this unit the rule lived only inside EP3
(``engine/water/exposure.py``, where the balance is given no crop on a
fallow day and on a day of the tail after maturity). This module holds it
once; EP3 reads it, and so can the other readers.

The rule, for one crop period from its sowing to its harvest (both
inclusive), with the four stage lengths of its crop:

- The four FAO-56 stages are laid end to end from the sowing, each with its
  length, never stretched to the period (D135); this is
  ``engine.water.stages.place_stages``.
- Stages that run past the harvest are cut there (D135): every day of the
  period up to the harvest is then a day with a live crop.
- Stages that end before the harvest leave a tail, from the day after the
  end of the late stage to the harvest: days with no live crop (D136).

The stage lengths are those of the crop, read from the parameter catalogue
by the exact scope ``{"crop": <crop>}`` (D137; ``live_crop_days_of_crop``),
as EP3 reads them. Only the stage lengths decide the days: a missing record
of the basal crop coefficient, or of the root depth, does not change which
days have a live crop (the crop is on the field), although EP3 does not
compute such a day. A stage length with no value leaves every day of the
period not known, missing with its reason, never a day with no crop (D79).
A length that is not a whole number of days of at least one leaves the
period ``NOT_COMPUTABLE``, as ``place_stages`` says why.

Unit ``l1/live-crop-by-day`` (issue #399) moves here, from EP3, the rule
that maps a day of the climate record to its crop period: the calendar
repeated over the agricultural years of the record (D47, D109), the lead-in
(D141), undated components, overlaps, and the stage lengths read per
component and cycle (D137). ``live_crop_by_day`` gives, for every day of the
record, whether a live crop stands, or why it is not known; EP3 builds its
daily chain on ``live_crop_over_record``, the same rule, so the monthly soil
cover of RothC (D222) and the water chain read one rule.

Pure functions (G1): no file, no network, no clock; the arguments are not
changed. No value of the method is here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from contracts.inputs.rotation_calendar import CalendarComponent, RotationCalendar
from contracts.results.models import Missing
from engine.calendar.repeat import (
    RepeatedComponent,
    RepeatedRotation,
    repeat_over_record,
)
from engine.water._parameters import Catalogue, Scope
from engine.water.stages import (
    GROWTH_STAGES,
    STAGE_LENGTH_PARAMETERS,
    PlacedStages,
    place_stages,
)

__all__ = [
    "CALENDAR_INFEASIBLE",
    "CROPS_OVERLAP",
    "CROP_DATES_MISSING",
    "CROP_UNKNOWN",
    "REPETITION_NOT_LAID_OUT",
    "REPETITION_OTHER_YEARS",
    "START_MONTH_UNKNOWN",
    "LiveCropDays",
    "LiveCropOverRecord",
    "component_of_day",
    "earliest_day",
    "latest_day",
    "live_crop_by_day",
    "live_crop_days",
    "live_crop_days_of_crop",
    "live_crop_over_record",
    "repeat_calendar_over_record",
]

# The scope key of a parameter read by crop (EP3's ``CROP_KEY``).
_CROP_KEY = "crop"


@dataclass(frozen=True)
class LiveCropDays:
    """The days of one crop period, each with or without a live crop.

    ``stages`` holds the growth stage of every day with a live crop and, in
    ``stages.tail``, the days after the end of the late stage up to the
    harvest, with no live crop (D136).
    """

    sowing: dt.date
    harvest: dt.date
    stages: PlacedStages

    def is_live(self, day: dt.date) -> bool:
        """Whether a live crop stands on a day of the period.

        Raises ``ValueError`` for a day outside the period.
        """
        if day in self.stages:
            return True
        if day in self.stages.tail:
            return False
        raise ValueError(
            f"{day.isoformat()} lies outside the crop period from "
            f"{self.sowing.isoformat()} to {self.harvest.isoformat()}"
        )

    @property
    def days(self) -> dict[dt.date, bool]:
        """Every day of the period, from the sowing to the harvest, in order,
        with whether a live crop stands on it."""
        live = dict.fromkeys(self.stages, True)
        live.update(dict.fromkeys(self.stages.tail, False))
        return dict(sorted(live.items()))


def live_crop_days(
    sowing: dt.date,
    harvest: dt.date,
    lengths: Mapping[str, float | Missing],
    *,
    what: str,
) -> LiveCropDays | Missing:
    """The days with a live crop of one crop period (D135, D136).

    ``lengths`` holds the length in days of each stage of ``GROWTH_STAGES``,
    a number or the ``Missing`` the catalogue gave. ``what`` names the period
    and its crop in a ``detail``.

    Returns:

    - ``Missing`` with reason ``MISSING_INPUT`` when a stage length has no
      value: every day of the period is not known, never a day with no crop
      (D79); the detail names each missing length and repeats its reason;
    - ``Missing`` with reason ``NOT_COMPUTABLE`` when a length is not a whole
      number of days of at least one, as ``place_stages`` says;
    - otherwise the ``LiveCropDays`` of the period.

    Raises ``ValueError`` when ``harvest`` comes before ``sowing`` or a stage
    of ``GROWTH_STAGES`` is not in ``lengths`` (a defect of the caller).
    """
    absent = [stage for stage in GROWTH_STAGES if stage not in lengths]
    if absent:
        raise ValueError(f"{what}: no length given for the stage(s) {absent}")
    missing = {
        stage: value for stage, value in lengths.items() if isinstance(value, Missing)
    }
    if missing:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the days with a live crop of {what} are not known: "
                + "; ".join(
                    f"the stage length '{STAGE_LENGTH_PARAMETERS[stage]}' has no "
                    f"value ({value.reason}: {value.detail})"
                    for stage, value in missing.items()
                )
                + "; missing stages stay missing (decision D79 of issue #77)"
            ),
        )
    placed = place_stages(sowing, harvest, dict(lengths), what=what)
    if isinstance(placed, Missing):
        return placed
    return LiveCropDays(sowing=sowing, harvest=harvest, stages=placed)


def live_crop_days_of_crop(
    sowing: dt.date,
    harvest: dt.date,
    crop: str,
    *,
    parameters: Mapping[str, dict],
    on: dt.date | None = None,
) -> LiveCropDays | Missing:
    """The days with a live crop of a period of ``crop``, from ``parameters``.

    The four stage lengths are read from the catalogue ``parameters`` (as
    ``params.catalogue.load_folder`` returns it) with the exact scope
    ``{"crop": crop}`` (D137), as EP3 reads them, on the day ``on`` (the
    sowing when it is not given); then ``live_crop_days``. No record but
    the four stage lengths is read: the basal crop coefficient and the root
    depth do not change the days.
    """
    catalogue = Catalogue(parameters)
    scope: Scope = ((_CROP_KEY, crop),)
    when = sowing if on is None else on
    lengths = {
        stage: catalogue.value(parameter_id, scope, when)
        for stage, parameter_id in STAGE_LENGTH_PARAMETERS.items()
    }
    return live_crop_days(sowing, harvest, lengths, what=f"a period of crop '{crop}'")


# --- the record: which component covers a day, and whether a live crop stands ---
#
# Unit l1/live-crop-by-day (issue #399, for D222). EP3's rule for the crop of a
# day of the record lived in engine/water/exposure.py as private functions; it
# is here so that EP3 and the monthly soil cover of RothC read one rule. The
# texts are EP3's, unchanged (EP3 imports them from here).

# Day arithmetic (C5.1, C5.3): months and days counted from one.
_FIRST = 1

CROP_UNKNOWN = (
    "the crop of the day is not known: the day lies before the described "
    "period, the first day the rotation repeated over the agricultural years "
    "of the climate record describes (decisions D47 and D109 of issue #77, "
    "engine/calendar/repeat.py), which is the start of the cycle laid out "
    "ahead of the first when the first cycle starts late (points 6 and 13 of "
    "engine/calendar/repeat.py, decision D188 of issue #77, part (2), #403), "
    "so the calendar does not describe the day; since D188 (2) no day of the "
    "record's years lies there (OPEN 5 of engine/water/EXPOSURE.md)"
)
CROP_DATES_MISSING = (
    "the crop of the day is not known: a component of the calendar has a "
    "missing date, so the days it covers are not known, within its cycle of "
    "the rotation repeated over the record (point 7 of "
    "engine/calendar/repeat.py)"
)
REPETITION_NOT_LAID_OUT = (
    "engine/calendar/repeat.py did not repeat the calendar over the years of "
    "the record although its start month is known (D47)"
)
REPETITION_OTHER_YEARS = (
    "engine/calendar/repeat.py laid out other agricultural years than EP3 did "
    "from the same record and start month (D47)"
)
CROPS_OVERLAP = (
    "two components of the calendar cover the day, and the water chain takes "
    "one crop per day"
)
START_MONTH_UNKNOWN = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the rotation cannot be repeated over the agricultural years of "
    "the record and no day of it is known (D47; EP3 lays out no year then)"
)
CALENDAR_INFEASIBLE = (
    "the calendar is infeasible (feasibility.feasible is false), so no day of it "
    "is laid out; EP3 computes no day of such a calendar"
)


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - _FIRST


def repeat_calendar_over_record(
    calendar: RotationCalendar, record_start: dt.date, record_end: dt.date
) -> RepeatedRotation:
    """The calendar repeated over the agricultural years of the record (D47, D109).

    The repetition is ``engine.calendar.repeat_over_record``, called once with
    the record as it is; EP3 passes the dates of its ``precipitation`` series,
    the series that marks the record for EP1 too. No rule of the repetition is
    written here. A calendar moved by ``phase_calendar`` (D132) is repeated
    like any other. Nothing is laid out past the record: a cycle that does not
    fit whole is cut at its end (D109).

    Raises ``ValueError`` when the start month is missing or the helper does
    not repeat the calendar (``REPETITION_NOT_LAID_OUT``), or lays out other
    agricultural years than the record and the start month give
    (``REPETITION_OTHER_YEARS``), as EP1 and EP3 do.
    """
    start_month = calendar.ag_year_start.month
    repeated = repeat_over_record(calendar, record_start, record_end)
    if start_month is None or not isinstance(repeated, RepeatedRotation):
        raise ValueError(REPETITION_NOT_LAID_OUT)
    years = range(
        _ag_year_of(record_start, start_month),
        _ag_year_of(record_end, start_month) + _FIRST,
    )
    if repeated.ag_years != tuple(years):
        raise ValueError(REPETITION_OTHER_YEARS)
    return repeated


def earliest_day(component: RepeatedComponent) -> dt.date:
    """The first day a component can cover: its start, else its cycle's start
    (point 7 of engine/calendar/repeat.py)."""
    return component.start if component.start is not None else component.calendar_start


def latest_day(component: RepeatedComponent) -> dt.date:
    """The last day a component can cover: its end, else the day before the
    next cycle starts (point 7 of engine/calendar/repeat.py)."""
    return component.end if component.end is not None else component.cycle_last_day


def _why_dates_are_missing(components: list[CalendarComponent]) -> dict[str, str]:
    """For each component with a missing date, which date and the reason the
    calendar gives for it (C3.2), as one text."""
    texts: dict[str, str] = {}
    for component in components:
        reasons: dict[str, list[str]] = {}
        for edge, value in (("start", component.start), ("end", component.end)):
            if value.date is not None:
                continue
            why = "no reason given"
            if value.missing is not None:
                why = value.missing.reason
                if value.missing.detail is not None:
                    why = f"{why}: {value.missing.detail}"
            reasons.setdefault(why, []).append(edge)
        if reasons:
            texts[component.component_id] = "; ".join(
                f"{' and '.join(edges)} date {why}" for why, edges in reasons.items()
            )
    return texts


def component_of_day(
    calendar: RotationCalendar, repeated: RepeatedRotation
) -> Callable[[dt.date], RepeatedComponent | None | Missing]:
    """The component on the field on a day, ``None`` for a day with no crop, or why it is not known.

    PROPOSED, as EP1 reads it (``_covering`` of engine/erosion/soil_loss.py).
    The day is a day of the record, so it lies inside the agricultural years
    the rotation is repeated over (D47). It takes the one component of the
    repeated rotation whose dates cover it, in whichever cycle; a component
    that starts before the record and ends inside it is one of them, with its
    declared dates (the lead-in of ``repeat_over_record``, D141), so it is
    present from the first day of the record. No component when none can
    cover the day. Not known (``MISSING_INPUT``) for a day before the
    described period (``described_from``: the lead-in is laid out whenever
    the first cycle starts late, D188 part (2), #403, so no day of the
    record's years lies there), and for a day a component with
    a missing date could cover, within its cycle (the detail names the
    component and repeats the reason the calendar gives for the date, so a
    crossing component ``phase_calendar`` could not place names D141). Two
    components on one day are not computed (``NOT_COMPUTABLE``).
    """
    dated = [
        component
        for component in repeated.components
        if component.start is not None and component.end is not None
    ]
    undated = [
        component
        for component in repeated.components
        if component.start is None or component.end is None
    ]
    why = _why_dates_are_missing(calendar.components)

    def component_of(day: dt.date) -> RepeatedComponent | None | Missing:
        if day < repeated.described_from:
            return Missing(reason="MISSING_INPUT", detail=CROP_UNKNOWN)
        covering = [item for item in dated if item.start <= day <= item.end]
        if len(covering) == _FIRST:
            (only,) = covering
            return only
        if covering:
            return Missing(reason="NOT_COMPUTABLE", detail=CROPS_OVERLAP)
        possible = dict.fromkeys(
            item.component_id
            for item in undated
            if earliest_day(item) <= day <= latest_day(item)
        )
        if possible:
            names = ", ".join(
                f"component {name!r} ({why.get(name, 'a date is missing')})"
                for name in possible
            )
            return Missing(
                reason="MISSING_INPUT", detail=f"{CROP_DATES_MISSING}: {names}"
            )
        return None

    return component_of


class LiveCropOverRecord:
    """The rotation over a record, with the live days of each crop period.

    Built by ``live_crop_over_record``, or by EP3 with its own catalogue.
    ``repeated`` is the calendar repeated over the record
    (``repeat_calendar_over_record``); ``component(day)`` is
    ``component_of_day``; and ``live_days(component, day)`` gives the
    ``LiveCropDays`` of one period (one component in one cycle), its four
    stage lengths read from ``catalogue`` by crop (D137) once, on the first
    day of the period it is asked for, and kept.
    """

    def __init__(
        self,
        calendar: RotationCalendar,
        repeated: RepeatedRotation,
        catalogue: Catalogue,
    ) -> None:
        self.repeated = repeated
        self.component = component_of_day(calendar, repeated)
        self._catalogue = catalogue
        self._periods: dict[tuple[int, str], LiveCropDays | Missing] = {}

    def live_days(
        self, component: RepeatedComponent, day: dt.date
    ) -> LiveCropDays | Missing:
        """The live days of the period of ``component`` (D135, D136), read on ``day``."""
        key = (component.cycle, component.component_id)
        if key not in self._periods:
            scope: Scope = ((_CROP_KEY, component.crop_id),)
            lengths = {
                stage: self._catalogue.value(parameter_id, scope, day)
                for stage, parameter_id in STAGE_LENGTH_PARAMETERS.items()
            }
            self._periods[key] = live_crop_days(
                component.start,
                component.end,
                lengths,
                what=f"component '{component.component_id}'",
            )
        return self._periods[key]

    def is_live(self, day: dt.date) -> bool | Missing:
        """Whether a live crop stands on a day of the record, or why it is not known."""
        covering = self.component(day)
        if covering is None or isinstance(covering, Missing):
            return False if covering is None else covering
        live = self.live_days(covering, day)
        if isinstance(live, Missing):
            return live
        return live.is_live(day)


def live_crop_over_record(
    calendar: RotationCalendar,
    record_start: dt.date,
    record_end: dt.date,
    *,
    parameters: Mapping[str, dict],
) -> LiveCropOverRecord:
    """The rotation repeated over the record, with the live days of each period.

    ``repeat_calendar_over_record``, then ``component_of_day``, with the stage
    lengths read from ``parameters`` (the catalogue as
    ``params.catalogue.load_folder`` returns it). EP3 builds its chain on it,
    so EP3 and ``live_crop_by_day`` read one rule. Raises ``ValueError`` as
    ``repeat_calendar_over_record`` does.
    """
    repeated = repeat_calendar_over_record(calendar, record_start, record_end)
    return LiveCropOverRecord(calendar, repeated, Catalogue(parameters))


def live_crop_by_day(
    calendar: RotationCalendar,
    record_start: dt.date,
    record_end: dt.date,
    *,
    parameters: Mapping[str, dict],
) -> dict[dt.date, bool | Missing]:
    """For each day of the record, whether a live crop stands, under EP3's rules.

    The days run from ``record_start`` to ``record_end``, both inclusive, in
    order. Each is:

    - ``True``: a live crop stands (a day of a growth stage, D135);
    - ``False``: no live crop, a fallow day or a day of the tail after
      maturity up to the harvest (D136);
    - a ``Missing`` with its reason when the day is not known: before the
      described period (``MISSING_INPUT``, ``CROP_UNKNOWN``, D141, D188); a day
      an undated component could cover (``MISSING_INPUT``, naming the
      component and the calendar's reason); two components on one day
      (``NOT_COMPUTABLE``); a stage length of the crop with no value
      (``MISSING_INPUT`` naming it, D79, never a day with no crop) or not a
      whole number of days (``NOT_COMPUTABLE``); a missing start month or an
      infeasible calendar (every day, ``START_MONTH_UNKNOWN`` or
      ``CALENDAR_INFEASIBLE``: EP3 computes no day then).

    The repetition over the record (D47, D109) and the lead-in (D141) are
    ``repeat_calendar_over_record``; the stage lengths are read per component
    and cycle on the first day of it in the record (D137), as EP3 reads them
    on the first day of it its chain meets. EP3 passes the dates of its
    ``precipitation`` series. No climate value is read.

    Raises ``ValueError`` when ``record_end`` is before ``record_start``, or
    as ``repeat_calendar_over_record`` does for a calendar with a start month.
    """
    if record_end < record_start:
        raise ValueError("the record ends before it starts")
    days = [
        record_start + dt.timedelta(days=offset)
        for offset in range((record_end - record_start).days + _FIRST)
    ]
    if calendar.ag_year_start.month is None:
        unknown = Missing(reason="MISSING_INPUT", detail=START_MONTH_UNKNOWN)
        return dict.fromkeys(days, unknown)
    if not calendar.feasibility.feasible:
        infeasible = Missing(reason="NOT_COMPUTABLE", detail=CALENDAR_INFEASIBLE)
        return dict.fromkeys(days, infeasible)
    over = live_crop_over_record(
        calendar, record_start, record_end, parameters=parameters
    )
    return {day: over.is_live(day) for day in days}
