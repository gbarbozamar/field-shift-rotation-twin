"""The rotation repeated over the agricultural years of the climate record.

Unit l1/calendar-repeat-d47 (issue #207). Decision D47 of issue #77: a result
lists every agricultural year of the climate record, cut by the start month
of the case, with the rotation repeated over them; a calendar whose own dates
lie outside the record still runs on the years of the record. Decision D29:
the record runs from 2001-01-01 to 2024-12-31. The record's first and last day
are arguments here, so this file holds neither date.

``repeat_over_record`` is a helper of the engines, not an entry point: EP2
(``build_rotation_calendar``) and its signature are unchanged (D56). EP1 uses
it; EP3 will use it in a later unit.

The form, PROPOSED (blueprint section 3.7). The questions each point leaves
are listed under OPEN at the end of this docstring and in OPEN 2 of
``engine/erosion/SOIL_LOSS.md``:

1. The agricultural years of the record are every agricultural year (C5.3)
   that has at least one day between the record's first and last day,
   identified by the calendar year in which it begins: the years EP1 lays out.
2. A date moves by whole calendar years: it keeps its month and its day. A 29
   February that falls in a year without one becomes 28 February, and the
   occurrence says so.
3. One cycle lasts the smallest whole number of years after which the
   calendar's ``start_date`` falls after its ``end_date``. So cycles never
   overlap, and the days between the end of one cycle and the start of the
   next are days of the rotation on which no component is placed.
4. The first cycle is the calendar moved so that its ``start_date`` falls in
   the first agricultural year of the record; the cycles follow one another
   every cycle length, each holding the calendar's components in the
   calendar's order, until a cycle would start after the last day of the
   record's years.
5. The last cycle is partial when it ends after that day. It is kept and
   marked, with the components that start after that day (those are not laid
   out). A component that starts on or before that day and ends after it
   keeps its dates and is marked.
6. Nothing is laid out before the first cycle: the days of the record before
   it are not described by the calendar.
7. A missing date stays missing in every cycle; nothing is filled in. A
   component without a start date can start no earlier than the cycle's
   start (the calendar's ``start_date`` in the cycle); a component without an
   end date can end no later than the day before the next cycle starts
   (``cycle_last_day``), since the rotation starts over then. The calendar's
   ``end_date`` is not used as that bound: it is the last date the calendar
   places, and a component without an end date may run past it.

OPEN, for the lead developer and the science reviewers (Q5 of
contracts/ENTRYPOINTS.md keeps "how the rotation is repeated" open):

- Point 4, where the first cycle starts, and the phases of D109 (issue #77,
  published after the brief of #207): "each phase of a rotation is a
  scenario", each phase starting in the first agricultural year of the
  record, cycles repeating, a cycle that does not fit whole cut at the end;
  the runner (L2a) makes one call per phase. This helper lays out the phase
  that starts with the calendar's first year only. Not built here: a start
  phase needs an explicit argument with no default, and EP1's signature
  cannot carry it (ENTRYPOINTS, D56), so how a phase reaches an engine (a
  field of the calendar, or a calendar the runner moves) is for the lead
  developer and the platform developer first. A candidate form: phase ``p``
  (0 to ``cycle_length - 1``) lays the calendar's year ``p`` on the first
  agricultural year of the record (shift reduced by ``p``); the components of
  the first cycle that end before the record are then not laid out, and one
  that starts before and ends inside it needs a rule.
- Point 6, the residue and the crop before the first cycle. Laying out one
  cycle before the record (a lead-in) would give the first year a last
  harvest; the residue ledger (Q12) is the other candidate. Not done: no
  decision asks for it.
- Point 3, the cycle length, and the days between two cycles as days with no
  component. The rotation definition's ``repeats`` does not reach the
  calendar (EP2 is unchanged, D56), so a rotation declared as not repeating is
  repeated all the same, as D47 says.
- Point 2, a 29 February in a year without one.
- Point 7, the bounds of a component with a missing date. A calendar whose
  last component has no end date (a pasture whose duration is not declared)
  gets a cycle length from its last placed date, so its next cycle may start
  while that component could still be on the field: the days in between are
  not known, never days with no crop.
- Which daily series marks the record for each engine (Q5): the caller passes
  the dates. EP1 passes those of its ``precipitation`` series.
- EP3 (``engine/water/``) does not call this helper yet: a later unit.

Pure function (G1 of contracts/ENTRYPOINTS.md): no file, no network, no clock,
and the calendar is not changed. The feasibility of the calendar is not read.
Like every module of this folder it imports neither ``datetime`` nor anything
else that can read a clock (``test_calendar.py``): every date is made from the
dates it is given, with ``replace`` and subtraction.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.inputs.common import IsoDate, Missing
from contracts.inputs.rotation_calendar import CalendarComponent, RotationCalendar

__all__ = [
    "Cycle",
    "RepeatedComponent",
    "RepeatedPeriod",
    "RepeatedRotation",
    "cycle_length_years",
    "repeat_over_record",
    "shifted_date",
]

_DAY_BEFORE_LEAP_DAY = 28
_FIRST = 1
_SECOND = 2

START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the agricultural years of the record cannot be laid out and the "
    "rotation cannot be repeated over them (decision D47 of issue #77)"
)


@dataclass(frozen=True)
class RepeatedPeriod:
    """One dated period of a component, in one cycle."""

    period_type: str
    start: IsoDate | None
    end: IsoDate | None  # inclusive


@dataclass(frozen=True)
class RepeatedComponent:
    """One component of the calendar, placed in one cycle.

    ``component_id`` and ``crop_id`` are the calendar's; a component appears
    once per cycle. ``start`` and ``end`` are ``None`` where the calendar's
    date is missing; ``calendar_start`` and ``calendar_end`` are the
    calendar's ``start_date`` and ``end_date`` in the same cycle, and
    ``cycle_last_day`` the day before the next cycle starts (point 7).
    """

    component_id: str
    crop_id: str
    cycle: int  # index of the cycle, the first is 0
    start: IsoDate | None
    end: IsoDate | None  # inclusive
    calendar_start: IsoDate
    calendar_end: IsoDate
    cycle_last_day: IsoDate
    periods: tuple[RepeatedPeriod, ...]
    leap_day_moved: bool  # a 29 February of the calendar became 28 February
    ends_after_record: bool  # ends after the last day of the record's years


@dataclass(frozen=True)
class Cycle:
    """One cycle of the rotation over the record."""

    index: int
    shift_years: int  # calendar years added to every date of the calendar
    start: IsoDate  # the calendar's start_date in this cycle
    end: IsoDate  # the calendar's end_date in this cycle
    last_day: IsoDate  # the day before the next cycle starts
    complete: bool  # the cycle ends on or before the last day of the record
    components_not_laid_out: tuple[str, ...]  # they start after that day


@dataclass(frozen=True)
class RepeatedRotation:
    """The rotation of one calendar repeated over the years of one record."""

    start_month: int
    record_start: IsoDate
    record_end: IsoDate
    cycle_length: int  # whole years of one cycle
    ag_years: tuple[int, ...]  # every agricultural year of the record
    first_day: IsoDate  # the first day of the first agricultural year
    last_day: IsoDate  # the last day of the last agricultural year
    cycles: tuple[Cycle, ...]
    components: tuple[RepeatedComponent, ...]  # cycle by cycle, calendar order

    @property
    def partial_cycle(self) -> Cycle | None:
        """The last cycle when it ends after the record's years, else ``None``."""
        last = self.cycles[-_FIRST]
        return None if last.complete else last

    @property
    def described_from(self) -> IsoDate:
        """The first day the repeated calendar describes: the first cycle's
        start. The days of the record's years before it are not described."""
        return self.cycles[0].start


def shifted_date(day: IsoDate, years: int) -> tuple[IsoDate, bool]:
    """The date moved by whole calendar years, and whether a 29 February
    became 28 February (point 2)."""
    year = day.year + years
    try:
        return day.replace(year=year), False
    except ValueError:  # only a 29 February, in a year without one
        return day.replace(year=year, day=_DAY_BEFORE_LEAP_DAY), True


def cycle_length_years(calendar: RotationCalendar) -> int:
    """The smallest whole number of years after which the calendar's
    ``start_date`` falls after its ``end_date`` (point 3)."""
    years = _FIRST
    while shifted_date(calendar.start_date, years)[0] <= calendar.end_date:
        years += _FIRST
    return years


def repeat_over_record(
    calendar: RotationCalendar, record_start: IsoDate, record_end: IsoDate
) -> RepeatedRotation | Missing:
    """The calendar's components repeated over every agricultural year of the
    record (D47, D29), cut by the calendar's start month. PROPOSED.

    Returns a ``Missing`` (reason ``MISSING_INPUT``) when the start month is
    missing: the agricultural years cannot be laid out.

    Raises ``TypeError`` for an argument that is not of its type and
    ``ValueError`` when the record ends before it starts.
    """
    if not isinstance(calendar, RotationCalendar):
        raise TypeError(
            f"calendar: expected a RotationCalendar, got {type(calendar).__name__}"
        )
    date_type = type(calendar.start_date)  # a date, never a date and time
    for name, value in (("record_start", record_start), ("record_end", record_end)):
        if type(value) is not date_type:
            raise TypeError(f"{name}: expected a date, got {type(value).__name__}")
    if record_end < record_start:
        raise ValueError("the record ends before it starts")

    start_month = calendar.ag_year_start.month
    if start_month is None:
        return Missing(reason="MISSING_INPUT", detail=START_MONTH_MISSING)

    first_ag_year = _ag_year_of(record_start, start_month)
    last_ag_year = _ag_year_of(record_end, start_month)
    first_day = record_start.replace(year=first_ag_year, month=start_month, day=_FIRST)
    one_day = first_day.replace(day=_SECOND) - first_day
    last_day = first_day.replace(year=last_ag_year + _FIRST) - one_day
    length = cycle_length_years(calendar)
    shift = first_ag_year - _ag_year_of(calendar.start_date, start_month)

    cycles: list[Cycle] = []
    components: list[RepeatedComponent] = []
    index = 0
    while True:
        cycle_start, _ = shifted_date(calendar.start_date, shift)
        if cycle_start > last_day:
            break
        cycle_end, _ = shifted_date(calendar.end_date, shift)
        cycle_last_day = shifted_date(calendar.start_date, shift + length)[0] - one_day
        bounds = (cycle_start, cycle_end, cycle_last_day)
        not_laid_out: list[str] = []
        for component in calendar.components:
            placed = _placed(component, index, shift, bounds, last_day)
            if placed is None:
                not_laid_out.append(component.component_id)
            else:
                components.append(placed)
        cycles.append(
            Cycle(
                index=index,
                shift_years=shift,
                start=cycle_start,
                end=cycle_end,
                last_day=cycle_last_day,
                complete=cycle_end <= last_day,
                components_not_laid_out=tuple(not_laid_out),
            )
        )
        index += _FIRST
        shift += length

    return RepeatedRotation(
        start_month=start_month,
        record_start=record_start,
        record_end=record_end,
        cycle_length=length,
        ag_years=tuple(range(first_ag_year, last_ag_year + _FIRST)),
        first_day=first_day,
        last_day=last_day,
        cycles=tuple(cycles),
        components=tuple(components),
    )


def _ag_year_of(day: IsoDate, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - _FIRST


def _maybe_shifted(day: IsoDate | None, years: int) -> tuple[IsoDate | None, bool]:
    if day is None:
        return None, False
    return shifted_date(day, years)


def _placed(
    component: CalendarComponent,
    index: int,
    shift: int,
    bounds: tuple[IsoDate, IsoDate, IsoDate],
    last_day: IsoDate,
) -> RepeatedComponent | None:
    """One component in one cycle, or ``None`` when it starts after the last
    day of the record's years. Without a start date, the earliest day it can
    start is the cycle's start (point 7)."""
    cycle_start, cycle_end, cycle_last_day = bounds
    start, start_moved = _maybe_shifted(component.start.date, shift)
    end, end_moved = _maybe_shifted(component.end.date, shift)
    earliest = start if start is not None else cycle_start
    if earliest > last_day:
        return None
    moved = start_moved or end_moved
    periods = []
    for period in component.periods:
        period_start, start_of_period_moved = _maybe_shifted(period.start.date, shift)
        period_end, end_of_period_moved = _maybe_shifted(period.end.date, shift)
        moved = moved or start_of_period_moved or end_of_period_moved
        periods.append(
            RepeatedPeriod(
                period_type=period.period_type, start=period_start, end=period_end
            )
        )
    return RepeatedComponent(
        component_id=component.component_id,
        crop_id=component.crop_id,
        cycle=index,
        start=start,
        end=end,
        calendar_start=cycle_start,
        calendar_end=cycle_end,
        cycle_last_day=cycle_last_day,
        periods=tuple(periods),
        leap_day_moved=moved,
        ends_after_record=end is not None and end > last_day,
    )
