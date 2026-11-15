"""The phases of a rotation: one moved calendar per phase (D109, option b).

Decision D109 of issue #77: each phase of a rotation is a scenario with its
own ``scenario_id``; the rotation runs once per phase, each phase starting in
the first agricultural year of the record; cycles repeat; and the runner
(lane L2a) makes one call per phase. Decision D117: the phases are nested
inside each value of an uncertain input, which the decision layer reads; the
runner only gives one result per phase.

How a phase reaches an engine was left by ``engine/calendar/repeat.py`` to the
lead developer and the platform developer. This module builds option (b), "a
calendar the runner moves" (issue #18, 00:57 UTC): EP1, EP3 and EP5 keep their
signatures (D56) and get a calendar whose dates are moved, so that EP1, which
lays the calendar's first agricultural year on the first agricultural year of
the record (``repeat.py`` point 4), lays the phase's first year there.

The moving rule, PROPOSED (blueprint section 3.7); every point the decisions
leave open is listed under OPEN in api/README.md:

1. ``N``, the number of phases, is the cycle length of the calendar in whole
   years, by the rule of ``cycle_length_years`` in ``engine/calendar/repeat.py``
   (point 3 there): the smallest whole number of years after which the
   calendar's ``start_date`` falls after its ``end_date``. A rotation of one
   year has one phase.
2. The calendar's year ``p`` (0 to ``N - 1``) is the agricultural year (C5.3)
   ``p`` years after the one of the calendar's ``start_date``. Its first day,
   the cut of phase ``p``, is the first day of the start month in that year.
3. Phase ``p`` lays the calendar's year ``p`` first. A component that ends
   before the cut belongs to the years before ``p``: it moves forward by
   ``N`` years, to the end of the cycle. Then every date moves back by ``p``
   years. Each date moves once, by the net number of years (``N - p`` or
   ``-p``). The periods of a component move with it.
4. A component that starts before the cut and ends on or after it, or whose
   end date is missing (a crossing component), has no rule in this release
   (D133): moving it back would place it before the phase's first year,
   which ``RotationCalendar`` cannot hold, and anything else would guess it.
   ``phase_calendar`` raises ``ValueError`` for such a phase, as #221
   allows; the runner answers that phase refused (``NOT_COMPUTABLE``, the
   OPEN rule named) and calls no engine for it. A component with no date at
   all moves with no date.
5. A date moves by whole calendar years: it keeps its month and its day. A 29
   February that falls in a year without one becomes 28 February, exactly as
   ``shifted_date`` of ``repeat.py`` does (point 2 there); the calendar module
   of the phase counts those dates.
6. The moved calendar's ``start_date`` is the first day of the calendar's
   year 0 and its ``end_date`` the day before the first day of year ``N``:
   the ``N`` years starting at the cut of phase ``p``, moved back ``p`` years.
   Every day between them is a day of the rotation repeated over the record
   (cycle 0 or 1 of ``repeat.py``), so the moved calendar describes no day
   that the calendar does not. So ``cycle_length_years`` of every moved
   calendar is ``N``, and its first agricultural year is that of phase 0.

   Phase 0 keeps the ``start_date`` of EP2 (its first placed date): it is
   the calendar of EP2 unchanged, which the route and
   ``validation/test_chain_examples.py`` (CH07) compare. Phases 1 and above
   cannot take the first placed date: when the phase's first year has no
   component starting in it, that date falls in a later agricultural year,
   EP1 would lay that year on the record's first year, and the cycle would
   shrink. Starting on the first day of the start month keeps both. What
   changes with it, in ``repeat.py`` point 7: a component without an end
   date can end no later than the day before the next cycle, which here is
   the end of year ``N - 1`` rather than the day before the next first
   placed date. That only widens the days an engine leaves unknown for that
   component; it fills none. Days of year 0 before the first placed date
   are days of the rotation with no component (the days between two cycles
   of ``repeat.py`` point 3), not days before the first cycle.
7. The components keep the calendar's order: first those that do not move
   forward, then those that do (now at the end of the cycle). Nothing else
   changes: identifiers, crops, management, feasibility, the start month and
   every provenance label, source and assumption mark stay as the calendar
   gives them. Phase 0 is the calendar itself, unchanged (the same object).

Without the start month (``ag_year_start.month`` missing) the cut cannot be
laid out: only phase 0 is given, and its calendar module says so.

Lane L1 agreed on issue #221 to build the same rule in
``engine/calendar/repeat.py`` as ``phase_calendar(calendar, p)`` and
``list_phases(calendar)``. The runner finds those two by name
(``api.engines.discover_engine_functions``) and uses them when both exist;
otherwise it uses the copy below, a PROPOSED transition to drop once #221
merges (OPEN). Whichever is used, the runner itself finds the crossing
components of point 4 on the calendar EP2 built and records the OPEN rule in
the phase, whether the function refuses the phase (``ValueError``) or returns
a calendar.

Pure functions: no file, no network, no clock. This module imports nothing
from ``engine/`` (the route depends on interfaces only); ``api/test_phases.py``
checks that its two date rules give the dates ``repeat.py`` gives.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from contracts.inputs import RotationCalendar

__all__ = [
    "Phase",
    "PhaseFunctions",
    "crossing_components",
    "cycle_length_years",
    "first_phase",
    "list_phases",
    "phase_calendar",
    "phase_calendars",
    "scenario_id",
    "shifted_date",
]

_DAY_BEFORE_LEAP_DAY = 28
_FEBRUARY = 2
_LEAP_DAY = 29
_FIRST_DAY = 1
_ONE_DAY = dt.timedelta(days=1)

# PROPOSED: the identifier of phase p (0 to N - 1) is ``phase_{p + 1}``.
SCENARIO_PREFIX = "phase_"

# PROPOSED detail texts: English for developers, never shown to users. They
# give counts only, never an identifier or a date (submitted values).
START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the phases of decision D109 cannot be laid out: only {phase} "
    "(the calendar unchanged) is run, not the other {others} phase(s)"
)
CROSSING_OPEN = (
    "OPEN: {count} component(s) start before the first agricultural year of this "
    "phase and end inside it or on a missing date; the lead developer has not "
    "given the rule for them (issue #18)"
)
LEFT_AS_RETURNED = "the calendar {function} returned is used as it is"
CROSSING_REFUSED = (
    "a component starts before the first agricultural year of this phase and "
    "ends inside it or on a missing date (D133: no rule)"
)
NOT_LAID_OUT = (
    "{function} refused the phase (ValueError), so this phase is not run; "
    "no rule is guessed"
)
LEAP_DAYS_MOVED = (
    "{count} date(s) on 29 February became 28 February when the calendar was "
    "moved by whole years (point 2 of engine/calendar/repeat.py)"
)

# Where lane L1 puts the phase rule (issue #221): found by name, the way the
# runner finds the entry points, never imported here.
REPEAT_MODULE = "engine.calendar.repeat"


def scenario_id(index: int) -> str:
    """The ``scenario_id`` of phase ``index`` (0 to N - 1). PROPOSED."""
    return f"{SCENARIO_PREFIX}{index + 1}"


@dataclass(frozen=True)
class PhaseFunctions:
    """The two functions that lay out the phases, with the names and signatures
    agreed on issue #221: ``phase_calendar(calendar, p) -> RotationCalendar``
    and ``list_phases(calendar) -> list[int]``."""

    phase_calendar: Callable[[RotationCalendar, int], RotationCalendar]
    list_phases: Callable[[RotationCalendar], list[int]]
    name: str  # where they live, for the detail texts


@dataclass(frozen=True)
class Phase:
    """One phase of the rotation: the calendar it runs on, and its notes.

    ``first_ag_year`` is the agricultural year (C5.3) of the calendar EP2 built
    that comes first in this phase, ``None`` without the start month.
    ``notes`` are details for the calendar module of the phase. ``calendar``
    is ``None`` only when the phase function refused a phase with a crossing
    component (``not_laid_out`` then says why): that phase calls no engine.
    """

    index: int
    scenario_id: str
    first_ag_year: int | None
    calendar: RotationCalendar | None
    notes: tuple[str, ...] = ()
    not_laid_out: str | None = None


def shifted_date(day: dt.date, years: int) -> tuple[dt.date, bool]:
    """The date moved by whole calendar years, and whether a 29 February
    became 28 February. The rule of ``engine.calendar.repeat.shifted_date``."""
    year = day.year + years
    try:
        return day.replace(year=year), False
    except ValueError:  # only a 29 February, in a year without one
        return day.replace(year=year, day=_DAY_BEFORE_LEAP_DAY), True


def cycle_length_years(calendar: RotationCalendar) -> int:
    """The smallest whole number of years after which the calendar's
    ``start_date`` falls after its ``end_date``. The rule of
    ``engine.calendar.repeat.cycle_length_years``."""
    years = 1
    while shifted_date(calendar.start_date, years)[0] <= calendar.end_date:
        years += 1
    return years


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - 1


def _cut(calendar: RotationCalendar, p: int) -> dt.date:
    """The first day of the calendar's year ``p`` (point 2)."""
    month = calendar.ag_year_start.month
    if month is None:
        raise ValueError("the start month is missing: the phases cannot be laid out")
    return dt.date(_ag_year_of(calendar.start_date, month) + p, month, _FIRST_DAY)


def crossing_components(calendar: RotationCalendar, p: int) -> int:
    """How many components start before the calendar's year ``p`` and end in
    or after it, or on a missing date (point 4). Zero for phase 0."""
    if p == 0:
        return 0
    cut = _cut(calendar, p)
    return sum(
        1
        for c in calendar.components
        if c.start.date is not None
        and c.start.date < cut
        and (c.end.date is None or c.end.date >= cut)
    )


# --- the runner's own copy of the phase rule ----------------------------------
# PROPOSED transition: lane L1 builds the same two functions in
# engine/calendar/repeat.py (issue #221). OPEN: drop this copy once #221
# merges; ``phase_functions`` then finds theirs and this copy is not used.


def list_phases(calendar: RotationCalendar) -> list[int]:
    """The phases of the calendar, 0 to N - 1 (point 1). Runner's copy."""
    return list(range(cycle_length_years(calendar)))


def phase_calendar(calendar: RotationCalendar, p: int) -> RotationCalendar:
    """The calendar moved so that its year ``p`` comes first (points 3 to 7).
    Runner's copy. Raises ``ValueError`` for ``p`` outside the phases or a
    missing start month, and for a phase with a crossing component (point 4,
    D133): nothing is guessed."""
    length = cycle_length_years(calendar)
    if isinstance(p, bool) or not isinstance(p, int) or not 0 <= p < length:
        raise ValueError("p is not a phase of this calendar")
    if p == 0:
        return calendar
    if crossing_components(calendar, p):
        raise ValueError(CROSSING_REFUSED)
    cut = _cut(calendar, p)
    document = calendar.model_dump()
    staying: list[dict[str, Any]] = []
    forward: list[dict[str, Any]] = []
    for component in document["components"]:
        end = component["end"]["date"]
        if end is not None and end < cut:
            years = length - p
            forward.append(component)
        else:
            years = -p
            staying.append(component)

        def edge(value: dict[str, Any], years: int = years) -> dict[str, Any]:
            if value["date"] is None:
                return value
            return {**value, "date": shifted_date(value["date"], years)[0]}

        component["start"] = edge(component["start"])
        component["end"] = edge(component["end"])
        component["periods"] = [
            {**period, "start": edge(period["start"]), "end": edge(period["end"])}
            for period in component["periods"]
        ]
    components = [*staying, *forward]
    first_day = shifted_date(cut, -p)[0]
    document["components"] = components
    document["start_date"] = first_day
    document["end_date"] = shifted_date(cut, length - p)[0] - _ONE_DAY
    return RotationCalendar.model_validate(document)


RUNNER_COPY = PhaseFunctions(phase_calendar, list_phases, "api.phases")

# --- the phases of one calendar -----------------------------------------------


def first_phase(calendar: RotationCalendar) -> Phase:
    """Phase 0 alone: the calendar itself, unchanged, with no note.

    The runner uses it when it runs one phase only (an infeasible calendar),
    or calls no engine after EP2.
    """
    start_month = calendar.ag_year_start.month
    first_ag_year = (
        None if start_month is None else _ag_year_of(calendar.start_date, start_month)
    )
    return Phase(0, scenario_id(0), first_ag_year, calendar)


def _leap_days_moved(calendar: RotationCalendar, moved: RotationCalendar) -> int:
    """Dates on 29 February in the calendar that are 28 February in the moved
    one, matched by component identifier (and period position)."""

    def edges(c: Any) -> list[dt.date | None]:
        dates = [c.start.date, c.end.date]
        for period in c.periods:
            dates += [period.start.date, period.end.date]
        return dates

    after = {c.component_id: edges(c) for c in moved.components}
    count = 0
    for component in calendar.components:
        for old, new in zip(edges(component), after.get(component.component_id, [])):
            if (
                old is not None
                and new is not None
                and (old.month, old.day) == (_FEBRUARY, _LEAP_DAY)
                and (new.month, new.day) == (_FEBRUARY, _DAY_BEFORE_LEAP_DAY)
            ):
                count += 1
    return count


def _what_moving_keeps(calendar: RotationCalendar) -> tuple:
    """Everything of a calendar but its dates: identifiers, start month,
    feasibility, and the components as a multiset of (identifier, crop,
    period types, which dates are present). Moving a calendar changes none."""

    def kept(c: Any) -> tuple:
        return (
            c.component_id,
            c.crop_id,
            c.start.date is None,
            c.end.date is None,
            tuple(
                (q.period_type, q.start.date is None, q.end.date is None)
                for q in c.periods
            ),
        )

    return (
        calendar.contract,
        calendar.example_data,
        calendar.case_id,
        calendar.field_id,
        calendar.rotation_id,
        calendar.ag_year_start,
        calendar.feasibility,
        sorted(kept(c) for c in calendar.components),
    )


def phase_calendars(
    calendar: RotationCalendar, functions: PhaseFunctions = RUNNER_COPY
) -> tuple[Phase, ...]:
    """Every phase of the calendar, in order; phase 0 is the calendar itself.

    ``functions`` lay out the phases: lane L1's when found, else the runner's
    copy. Phase 0 is never asked of them. A ``ValueError`` from
    ``phase_calendar`` for a phase with a crossing component (point 4) is the
    OPEN rule, recorded in that phase; any other exception, or a ``ValueError``
    for a phase without one, is a defect and propagates (``500``). What they
    return is checked: a list of phases starting at 0, and a calendar that
    loads into the contract with the identifiers of the calendar.
    """
    if not isinstance(calendar, RotationCalendar):
        raise TypeError(
            f"calendar: expected a RotationCalendar, got {type(calendar).__name__}"
        )
    start_month = calendar.ag_year_start.month
    if start_month is None:
        length = cycle_length_years(calendar)
        notes = ()
        if length > 1:
            notes = (
                START_MONTH_MISSING.format(phase=scenario_id(0), others=length - 1),
            )
        return (Phase(0, scenario_id(0), None, calendar, notes),)
    returned = functions.list_phases(calendar)
    if isinstance(returned, str | bytes) or not isinstance(returned, Sequence):
        raise TypeError(f"{functions.name}.list_phases returned no sequence")
    indices = list(returned)
    if not indices or indices != list(range(len(indices))):
        raise TypeError(f"{functions.name}.list_phases returned no phases 0 to N - 1")
    first = first_phase(calendar)
    assert first.first_ag_year is not None
    phases = [first]
    for p in indices[1:]:
        crossing = crossing_components(calendar, p)
        year = first.first_ag_year + p
        try:
            moved = functions.phase_calendar(calendar, p)
        except ValueError:
            if not crossing:
                raise
            phases.append(
                Phase(
                    p,
                    scenario_id(p),
                    year,
                    None,
                    (CROSSING_OPEN.format(count=crossing),),
                    NOT_LAID_OUT.format(function=f"{functions.name}.phase_calendar"),
                )
            )
            continue
        if not isinstance(moved, RotationCalendar):
            raise TypeError(
                f"{functions.name}.phase_calendar returned {type(moved).__name__}, "
                "not RotationCalendar"
            )
        moved = RotationCalendar.model_validate(moved.model_dump())
        if _what_moving_keeps(moved) != _what_moving_keeps(calendar):
            raise TypeError(
                f"{functions.name}.phase_calendar changed more than the dates of "
                "the calendar"
            )
        notes = []
        if crossing:
            used = LEFT_AS_RETURNED.format(function=f"{functions.name}.phase_calendar")
            notes.append(f"{CROSSING_OPEN.format(count=crossing)}; {used}")
        leap_days = _leap_days_moved(calendar, moved)
        if leap_days:
            notes.append(LEAP_DAYS_MOVED.format(count=leap_days))
        phases.append(Phase(p, scenario_id(p), year, moved, tuple(notes)))
    return tuple(phases)
