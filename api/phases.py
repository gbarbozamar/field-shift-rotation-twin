"""The phases of a rotation: one calendar per phase (D109, D141).

Decision D109 of issue #77: each phase of a rotation is a scenario with its
own ``scenario_id``; the rotation runs once per phase, each phase starting in
the first agricultural year of the record; cycles repeat; and the runner
(lane L2a) makes one call per phase. Decision D117: the phases are nested
inside each value of an uncertain input, which the decision layer reads; the
runner only gives one result per phase.

How a phase reaches an engine is option (b), "a calendar the runner moves"
(D132; issue #18, 00:57 UTC): EP1, EP3 and EP5 keep their signatures (D56)
and get the calendar of the phase. Lane L1 lays the phases out in
``engine/calendar/repeat.py`` as ``phase_calendar(calendar, p)`` and
``list_phases(calendar)`` (issue #221). The runner finds both by name
(``api.engines.discover_engine_functions``) and holds no copy of their rule:

- both found: phase 0 is the calendar of EP2 itself, unchanged; every other
  phase ``p`` is what ``phase_calendar(calendar, p)`` returns, checked
  (``phase_calendars``) and used as returned. A ``ValueError`` from it is a
  defect and propagates (``500``): D141 gives a rule for every phase, so no
  phase is refused;
- either one not found (an older engine tree): phase 0 alone, and its
  calendar module says so (PROPOSED);
- the start month missing: phase 0 alone, and its calendar module says how
  many phases were not run (``list_phases`` counts them).

D141 (issue #77, amends D133): each phase is laid out as the first one is. A
component that spans the start of the phase's first year keeps its declared
dates; the part before the record falls outside the record, inside it the
component is present from the first day of the record, and whatever would
need the part before the record stays missing with its reason. The runner
counts those components on the calendar of EP2 (``crossing_components``) and
writes the count in the calendar module of the phase, never an identifier.

Pure functions: no file, no network, no clock. This module imports nothing
from ``engine/`` (the route depends on interfaces only).
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
    "first_phase",
    "phase_calendars",
    "scenario_id",
]

_DAY_BEFORE_LEAP_DAY = 28
_FEBRUARY = 2
_LEAP_DAY = 29
_FIRST_DAY = 1

# PROPOSED: the identifier of phase p (0 to N - 1) is ``phase_{p + 1}``.
SCENARIO_PREFIX = "phase_"

# Where lane L1 puts the phase rule (issue #221): found by name, the way the
# runner finds the entry points, never imported here.
REPEAT_MODULE = "engine.calendar.repeat"

# PROPOSED detail texts: English for developers, never shown to users. They
# give counts only, never an identifier or a date (submitted values).
START_MONTH_MISSING = (
    "the start month of the agricultural year (calendar.ag_year_start.month) is "
    "missing, so the phases of decision D109 cannot be laid out: only {phase} "
    "(the calendar unchanged) is run, not the other {others} phase(s)"
)
PHASE_FUNCTIONS_NOT_FOUND = (
    "phase_calendar and list_phases of "
    + REPEAT_MODULE
    + " were not found, so the phases of decision D109 are not laid out: only "
    "{phase} (the calendar unchanged) is run"
)
CROSSING_D141 = (
    "{count} component(s) start before the first agricultural year of this "
    "phase and end inside it or on a missing date; laid out as the first phase "
    "is (D141, issue #77): what would need the part before the record is "
    "missing with its reason"
)
LEAP_DAYS_MOVED = (
    "{count} date(s) on 29 February became 28 February when the calendar was "
    "moved by whole years (point 2 of engine/calendar/repeat.py)"
)


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
    ``notes`` are details for the calendar module of the phase.
    """

    index: int
    scenario_id: str
    first_ag_year: int | None
    calendar: RotationCalendar
    notes: tuple[str, ...] = ()


def _ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - 1


def crossing_components(calendar: RotationCalendar, p: int) -> int:
    """How many components of the calendar start before the first day of its
    agricultural year ``p`` and end on or after it, or on a missing date: the
    components that span the start of phase ``p``'s first year (D141). Zero
    for phase 0 and without the start month. Only counted, for the note."""
    month = calendar.ag_year_start.month
    if p == 0 or month is None:
        return 0
    cut = dt.date(_ag_year_of(calendar.start_date, month) + p, month, _FIRST_DAY)
    return sum(
        1
        for c in calendar.components
        if c.start.date is not None
        and c.start.date < cut
        and (c.end.date is None or c.end.date >= cut)
    )


def first_phase(calendar: RotationCalendar, notes: tuple[str, ...] = ()) -> Phase:
    """Phase 0 alone: the calendar itself, unchanged.

    The runner uses it when it runs one phase only (an infeasible calendar,
    phase functions not found), or calls no engine after EP2.
    """
    start_month = calendar.ag_year_start.month
    first_ag_year = (
        None if start_month is None else _ag_year_of(calendar.start_date, start_month)
    )
    return Phase(0, scenario_id(0), first_ag_year, calendar, notes)


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
    """Everything of a calendar but its dates: contract, example mark,
    identifiers, start month, feasibility, and the components as a multiset
    of (identifier, crop, period types). A phase calendar changes none of
    them. Which dates are present may change: the phase rule may leave a
    date missing with its reason."""

    def kept(c: Any) -> tuple:
        return (c.component_id, c.crop_id, tuple(q.period_type for q in c.periods))

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
    calendar: RotationCalendar, functions: PhaseFunctions | None
) -> tuple[Phase, ...]:
    """Every phase of the calendar, in order; phase 0 is the calendar itself.

    ``functions`` lay out the phases (lane L1's, found by name); ``None``
    when they were not found: phase 0 alone, with a note. Phase 0 is never
    asked of them. Whatever they raise propagates (``500``), a
    ``ValueError`` included. What they return is checked: a list of phases
    starting at 0, and a calendar that loads into the contract and keeps
    everything of the calendar but its dates; anything else is a
    ``TypeError``.
    """
    if not isinstance(calendar, RotationCalendar):
        raise TypeError(
            f"calendar: expected a RotationCalendar, got {type(calendar).__name__}"
        )
    if functions is None:
        note = PHASE_FUNCTIONS_NOT_FOUND.format(phase=scenario_id(0))
        return (first_phase(calendar, (note,)),)
    returned = functions.list_phases(calendar)
    if isinstance(returned, str | bytes) or not isinstance(returned, Sequence):
        raise TypeError(f"{functions.name}.list_phases returned no sequence")
    indices = list(returned)
    if not indices or indices != list(range(len(indices))):
        raise TypeError(f"{functions.name}.list_phases returned no phases 0 to N - 1")
    first = first_phase(calendar)
    if first.first_ag_year is None:
        notes: tuple[str, ...] = ()
        if len(indices) > 1:
            others = len(indices) - 1
            notes = (
                START_MONTH_MISSING.format(phase=first.scenario_id, others=others),
            )
        return (first_phase(calendar, notes),)
    phases = [first]
    for p in indices[1:]:
        moved = functions.phase_calendar(calendar, p)
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
        notes_of_phase = []
        crossing = crossing_components(calendar, p)
        if crossing:
            notes_of_phase.append(CROSSING_D141.format(count=crossing))
        leap_days = _leap_days_moved(calendar, moved)
        if leap_days:
            notes_of_phase.append(LEAP_DAYS_MOVED.format(count=leap_days))
        year = first.first_ag_year + p
        phases.append(Phase(p, scenario_id(p), year, moved, tuple(notes_of_phase)))
    return tuple(phases)
