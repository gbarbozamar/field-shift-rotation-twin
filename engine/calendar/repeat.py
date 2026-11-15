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

The phases of a rotation (unit l1/calendar-phases-d109, issue #221).
Decision D109 of issue #77: each phase of a rotation is a scenario, each
phase starting in the first agricultural year of the record, cycles
repeating, a cycle that does not fit whole cut at the end; a one-year
rotation has one phase. Decision D132: a phase reaches the engines as a
calendar the runner moves with ``phase_calendar`` and ``list_phases``; EP1,
EP3 and EP5 take the moved ``RotationCalendar`` unchanged (D56), and
``repeat_over_record`` then lays the calendar's year ``p`` on the first
agricultural year of the record. Decision D133: a component that starts
before the first agricultural year of the record and ends inside it gets no
rule in this release; its days in the record are missing with their reason,
never guessed. (D117, how the phases nest in the one-input sweep, and the
``scenario_id`` of each phase are the runner's.) The form, PROPOSED (blueprint
section 3.7):

8. The phases of a calendar are 0 to ``cycle_length_years - 1`` (point 3),
   so a one-year rotation has one phase (D109).
9. The years of the calendar are its agricultural years (C5.3), counted from
   the one that holds its ``start_date`` (year 0). A component belongs to the
   year of its start date, or of its end date when the start is missing; a
   component with neither date stays where it is.
10. ``phase_calendar(calendar, p)`` keeps the components of years ``p`` and
    later and moves those of earlier years one cycle later (point 3 length),
    each date keeping its month and day as ``shifted_date`` moves it
    (point 2). The kept components come first, then the moved ones, each
    group in the calendar's order. Phase 0 returns the calendar unchanged.
11. A component of a year before ``p`` with a date on or after the first day
    of year ``p`` crosses the boundary between years ``p - 1`` and ``p``.
    Moved, that date would fall in the next cycle. It is not moved and not
    guessed (D133): it becomes missing with reason ``NOT_COMPUTABLE`` and a
    detail naming D133, the component's other dates are moved, and
    ``components_crossing_phase`` names the component. No error is raised:
    the phase runs, and the days that depend on that date are missing.
12. The moved calendar's ``start_date`` is the calendar's ``start_date`` moved
    ``p`` years, or the day after the last date of a crossing component in
    year ``p`` if that is later (so those days lie before the first cycle in
    the record and between cycles inside the bound of point 7, never on days
    with no component), or the earliest date it places if that is earlier.
    Its ``end_date`` is the latest date it places, or its ``start_date`` moved
    ``cycle length - 1`` years if that is later, so its cycle length is the
    calendar's (point 3). ``feasibility``, the identifiers and the start month
    are copied unchanged, and the result is a valid ``RotationCalendar``.

OPEN, for the lead developer and the science reviewers (Q5 of
contracts/ENTRYPOINTS.md keeps "how the rotation is repeated" open):

- Point 4, where the first cycle starts: decided for the phases by D109 and
  D132 and built in ``phase_calendar`` (points 8 to 12). EP1 keeps calling
  ``repeat_over_record``; the runner (L2a) passes it the moved calendar.
- Point 11, the rule for a component that crosses into year ``p``: none in
  this release (D133). Which date to cut, or a lead-in, stays for a later
  release (asked on #18).
- Point 11, a component of a year before ``p`` whose end date is missing and
  that has no dated period on or after year ``p``: it may cross the boundary
  but cannot be shown to, so it is moved with its end still missing (point
  7). A component of year ``p`` or later whose start date is missing may have
  started before the boundary: it is kept, its start still missing.
- Point 12, an ``end_date`` later than every date the moved calendar places
  (only when a year holds nothing near its end), set so the cycle length of
  point 3 holds.
- Point 10, a 29 February moved twice (one cycle here, then the shift of
  point 4) can become 28 February in a leap year of the record, and the moved
  calendar cannot say a date was moved (``leap_day_moved`` stays false).
- Point 10, a moved date keeps the provenance and source of the calendar's
  date.
- Point 9, a calendar whose start month is missing: ``phase_calendar``
  raises ``ValueError`` for a phase above 0, as its years are not known.
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
    "components_crossing_phase",
    "cycle_length_years",
    "list_phases",
    "phase_calendar",
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

# Point 11: the reason (C3.2) of a date that crosses into the phase's year.
CROSSING_REASON = "NOT_COMPUTABLE"
_CROSSING_DETAIL = (
    "phase {phase}: component {component_id!r} starts before year {phase} of "
    "the calendar and this date falls in that year or later; with the calendar "
    "moved (decision D132 of issue #77) the date would fall in the next cycle, "
    "and a component that crosses into the first year of a phase gets no rule "
    "in this release (decision D133), so the date is missing, never guessed"
)
_PHASE_START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the years of the calendar are not known and phase {phase} "
    "cannot be laid out (decisions D109 and D132 of issue #77)"
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


def list_phases(calendar: RotationCalendar) -> list[int]:
    """The phases of the calendar's rotation, 0 to ``cycle_length_years - 1``
    (point 8). A one-year rotation has one phase (D109). PROPOSED.

    Raises ``TypeError`` when ``calendar`` is not a ``RotationCalendar``.
    """
    _check_calendar(calendar)
    return list(range(cycle_length_years(calendar)))


def phase_calendar(calendar: RotationCalendar, p: int) -> RotationCalendar:
    """The calendar moved so that its year ``p`` comes first (points 9 to 12;
    D109, D132, D133). A valid ``RotationCalendar``: EP1, EP3 and EP5 take it
    unchanged, and ``repeat_over_record`` lays its year ``p`` on the first
    agricultural year of the record. PROPOSED.

    A component that crosses into year ``p`` does not raise: the crossing
    date is missing with its reason (point 11) and
    ``components_crossing_phase`` names it.

    Raises ``TypeError`` when ``calendar`` is not a ``RotationCalendar``;
    ``ValueError`` when ``p`` is not one of ``list_phases(calendar)``, and for
    a phase above 0 when the start month is missing.
    """
    length, boundary = _phase_bounds(calendar, p)
    if p == 0:
        return calendar.model_copy(deep=True)
    first_year = _ag_year_of(calendar.start_date, calendar.ag_year_start.month)
    one_day = boundary.replace(day=_SECOND) - boundary

    kept: list[dict] = []
    moved: list[dict] = []
    floor = shifted_date(calendar.start_date, p)[0]
    for component in calendar.components:
        year = _year_of_component(component, calendar.ag_year_start.month)
        if year is None or year - first_year >= p:
            kept.append(component.model_dump())
            continue
        crossing = [day for day in _known_dates(component) if day >= boundary]
        if crossing:
            floor = max(floor, max(crossing) + one_day)
        detail = _CROSSING_DETAIL.format(phase=p, component_id=component.component_id)
        moved.append(_moved(component, length, boundary, detail))

    components = kept + moved
    placed = [day for item in components for day in _known_dates_of_dump(item)]
    start = min([floor, *placed])
    end = max([shifted_date(start, length - _FIRST)[0], *placed])
    document = calendar.model_dump()
    document.update(start_date=start, end_date=end, components=components)
    return RotationCalendar.model_validate(document)


def components_crossing_phase(calendar: RotationCalendar, p: int) -> list[str]:
    """The components of years before ``p`` with a date in year ``p`` or later
    (point 11): the ones ``phase_calendar(calendar, p)`` leaves with a missing
    date. Empty for phase 0. PROPOSED.

    Raises as ``phase_calendar`` does.
    """
    _, boundary = _phase_bounds(calendar, p)
    if p == 0:
        return []
    month = calendar.ag_year_start.month
    first_year = _ag_year_of(calendar.start_date, month)
    found = []
    for component in calendar.components:
        year = _year_of_component(component, month)
        if year is None or year - first_year >= p:
            continue
        if any(day >= boundary for day in _known_dates(component)):
            found.append(component.component_id)
    return found


def _check_calendar(calendar: object) -> None:
    if not isinstance(calendar, RotationCalendar):
        raise TypeError(
            f"calendar: expected a RotationCalendar, got {type(calendar).__name__}"
        )


def _phase_bounds(calendar: RotationCalendar, p: object) -> tuple[int, IsoDate]:
    """The cycle length and the first day of year ``p`` (the start date for
    phase 0), after checking the arguments."""
    phases = list_phases(calendar)
    if type(p) is not int or p not in phases:
        raise ValueError(
            f"p: expected a whole number from 0 to {phases[-_FIRST]} "
            "(the cycle length of the calendar less one)"
        )
    if p == 0:
        return len(phases), calendar.start_date
    month = calendar.ag_year_start.month
    if month is None:
        raise ValueError(_PHASE_START_MONTH_MISSING.format(phase=p))
    first_year = _ag_year_of(calendar.start_date, month)
    boundary = calendar.start_date.replace(year=first_year + p, month=month, day=_FIRST)
    return len(phases), boundary


def _year_of_component(component: CalendarComponent, start_month: int) -> int | None:
    """Point 9: the agricultural year of the start date, else of the end date."""
    for day in (component.start.date, component.end.date):
        if day is not None:
            return _ag_year_of(day, start_month)
    return None


def _known_dates(component: CalendarComponent) -> list[IsoDate]:
    days = [component.start.date, component.end.date]
    for period in component.periods:
        days += [period.start.date, period.end.date]
    return [day for day in days if day is not None]


def _known_dates_of_dump(component: dict) -> list[IsoDate]:
    days = [component["start"]["date"], component["end"]["date"]]
    for period in component["periods"]:
        days += [period["start"]["date"], period["end"]["date"]]
    return [day for day in days if day is not None]


def _moved(
    component: CalendarComponent, years: int, boundary: IsoDate, detail: str
) -> dict:
    """The component one cycle later (point 10); a date on or after the
    boundary becomes missing (point 11)."""

    def move(value: dict) -> dict:
        day = value["date"]
        if day is None:
            return value
        if day >= boundary:
            return {
                "date": None,
                "missing": {"reason": CROSSING_REASON, "detail": detail},
                "provenance": None,
                "source": None,
                "assumption": False,
            }
        return {**value, "date": shifted_date(day, years)[0]}

    item = component.model_dump()
    item["start"] = move(item["start"])
    item["end"] = move(item["end"])
    for period in item["periods"]:
        period["start"] = move(period["start"])
        period["end"] = move(period["end"])
    return item


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
