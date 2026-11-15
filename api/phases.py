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
``list_phases(calendar)`` (issue #221), and names the components that cross
into a phase's first year with ``components_crossing_phase(calendar, p)``.
The runner finds them by name (``api.engines.discover_engine_functions``)
and holds no copy of their rules, the crossing rule included:

- ``phase_calendar`` and ``list_phases`` found: phase 0 is the calendar of EP2
  itself, unchanged; every other phase ``p`` is what
  ``phase_calendar(calendar, p)`` returns, checked (``phase_calendars``) and
  used as returned. Whatever it raises, a ``ValueError`` included, is a
  defect and propagates (``500``): under D141 no phase is refused;
- either one not found (an older engine tree): phase 0 alone, and its
  calendar module says so (PROPOSED);
- the start month missing: phase 0 alone, and its calendar module says how
  many phases were not run (``list_phases`` counts them);
- ``components_crossing_phase`` found: the calendar module of phase ``p``
  gives how many components it names (a count, never an identifier);
  not found: no count is written.

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
    "first_phase",
    "phase_calendars",
    "scenario_id",
]

_DAY_BEFORE_LEAP_DAY = 28
_FEBRUARY = 2
_LEAP_DAY = 29

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
CROSSING_COUNTED = (
    "{count} component(s) of the calendar cross into the first agricultural "
    "year of this phase, as {name}.components_crossing_phase names them; this "
    "phase runs on the calendar {name}.phase_calendar returned, used as "
    "returned (D141 of issue #77: no phase is refused)"
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
    """The functions that lay out the phases, with the names and signatures
    agreed on issue #221: ``phase_calendar(calendar, p) -> RotationCalendar``
    and ``list_phases(calendar) -> list[int]``; and, when lane L1 has it,
    ``components_crossing_phase(calendar, p) -> list[str]``."""

    phase_calendar: Callable[[RotationCalendar, int], RotationCalendar]
    list_phases: Callable[[RotationCalendar], list[int]]
    name: str  # where they live, for the detail texts
    components_crossing_phase: Callable[[RotationCalendar, int], list[str]] | None = (
        None
    )


@dataclass(frozen=True)
class Phase:
    """One phase of the rotation: the calendar it runs on, and its notes.

    ``first_ag_year`` is the agricultural year (C5.3) in which the calendar of
    the phase starts, ``None`` without the start month. ``notes`` are details
    for the calendar module of the phase.
    """

    index: int
    scenario_id: str
    first_ag_year: int | None
    calendar: RotationCalendar
    notes: tuple[str, ...] = ()


def ag_year_of(day: dt.date, start_month: int) -> int:
    """The agricultural year a day belongs to, by the year in which it begins."""
    return day.year if day.month >= start_month else day.year - 1


def first_phase(calendar: RotationCalendar, notes: tuple[str, ...] = ()) -> Phase:
    """Phase 0 alone: the calendar itself, unchanged.

    The runner uses it when it runs one phase only (an infeasible calendar,
    phase functions not found), or calls no engine after EP2.
    """
    start_month = calendar.ag_year_start.month
    first_ag_year = (
        None if start_month is None else ag_year_of(calendar.start_date, start_month)
    )
    return Phase(0, scenario_id(0), first_ag_year, calendar, notes)


def _edges(component: Any) -> list[dt.date | None]:
    """The dates of a component in a fixed order: start, end, then each
    period's start and end."""
    dates = [component.start.date, component.end.date]
    for period in component.periods:
        dates += [period.start.date, period.end.date]
    return dates


def _leap_days_moved(calendar: RotationCalendar, moved: RotationCalendar) -> int:
    """Dates on 29 February in the calendar that are 28 February in the moved
    one, matched by component identifier (and period position)."""
    after = {c.component_id: _edges(c) for c in moved.components}
    count = 0
    for component in calendar.components:
        for old, new in zip(_edges(component), after.get(component.component_id, [])):
            if (
                old is not None
                and new is not None
                and (old.month, old.day) == (_FEBRUARY, _LEAP_DAY)
                and (new.month, new.day) == (_FEBRUARY, _DAY_BEFORE_LEAP_DAY)
            ):
                count += 1
    return count


def _fills_a_missing_date(calendar: RotationCalendar, moved: RotationCalendar) -> bool:
    """Whether the moved calendar has a date where the calendar's is missing,
    matched by component identifier (and period position). A date present in
    the calendar may become missing (the phase rule may leave it missing with
    its reason); a missing one never becomes present."""
    after = {c.component_id: _edges(c) for c in moved.components}
    return any(
        old is None and new is not None
        for component in calendar.components
        for old, new in zip(_edges(component), after.get(component.component_id, []))
    )


def _what_moving_keeps(calendar: RotationCalendar) -> tuple:
    """Everything of a calendar but its dates: contract, example mark,
    identifiers, start month, feasibility, and the components as a multiset
    of (identifier, crop, period types). A phase calendar changes none of
    them."""

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


def _checked_phase(
    calendar: RotationCalendar,
    moved: object,
    p: int,
    first_ag_year: int,
    start_month: int,
    name: str,
) -> tuple[RotationCalendar, int]:
    """What ``phase_calendar(calendar, p)`` returned, checked; with the
    agricultural year in which it starts. Any failed check is a defect of
    the phase function: ``TypeError`` (``500``)."""
    function = f"{name}.phase_calendar"
    if not isinstance(moved, RotationCalendar):
        raise TypeError(
            f"{function} returned {type(moved).__name__}, not RotationCalendar"
        )
    moved = RotationCalendar.model_validate(moved.model_dump())
    if _what_moving_keeps(moved) != _what_moving_keeps(calendar):
        raise TypeError(f"{function} changed more than the dates of the calendar")
    if _fills_a_missing_date(calendar, moved):
        raise TypeError(f"{function} gave a date the calendar has missing")
    year = ag_year_of(moved.start_date, start_month)
    if year != first_ag_year + p:
        raise TypeError(
            f"{function} returned a calendar for phase {p} that does not start "
            f"in agricultural year {p} of the calendar"
        )
    return moved, year


def _crossing_count(functions: PhaseFunctions, calendar: RotationCalendar, p: int):
    """How many components lane L1 names as crossing into year ``p``, or
    ``None`` when it has no such function."""
    if functions.components_crossing_phase is None:
        return None
    named = functions.components_crossing_phase(calendar, p)
    if isinstance(named, str | bytes) or not isinstance(named, Sequence):
        raise TypeError(
            f"{functions.name}.components_crossing_phase returned no sequence"
        )
    return len(named)


def phase_calendars(
    calendar: RotationCalendar, functions: PhaseFunctions | None
) -> tuple[Phase, ...]:
    """Every phase of the calendar, in order; phase 0 is the calendar itself.

    ``functions`` lay out the phases (lane L1's, found by name); ``None``
    when they were not found: phase 0 alone, with a note. Phase 0 is never
    asked of them. Whatever they raise propagates (``500``), a
    ``ValueError`` included. What they return is checked: a list of phases
    0 to N - 1; for phase ``p``, a calendar that loads into the contract,
    keeps everything of the calendar but its dates, gives no date the
    calendar has missing, and starts in the calendar's agricultural year
    ``p`` (so no phase is misaligned or repeated). Anything else is a
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
    start_month = calendar.ag_year_start.month
    if first.first_ag_year is None or start_month is None:
        notes: tuple[str, ...] = ()
        if len(indices) > 1:
            others = len(indices) - 1
            notes = (
                START_MONTH_MISSING.format(phase=first.scenario_id, others=others),
            )
        return (first_phase(calendar, notes),)
    phases = [first]
    for p in indices[1:]:
        moved, year = _checked_phase(
            calendar,
            functions.phase_calendar(calendar, p),
            p,
            first.first_ag_year,
            start_month,
            functions.name,
        )
        notes_of_phase = []
        crossing = _crossing_count(functions, calendar, p)
        if crossing:
            notes_of_phase.append(
                CROSSING_COUNTED.format(count=crossing, name=functions.name)
            )
        leap_days = _leap_days_moved(calendar, moved)
        if leap_days:
            notes_of_phase.append(LEAP_DAYS_MOVED.format(count=leap_days))
        phases.append(Phase(p, scenario_id(p), year, moved, tuple(notes_of_phase)))
    return tuple(phases)
