"""Acceptance test of unit l1/calendar-repeat-d47 (issue #207): the rotation
repeated over the agricultural years of the climate record (D47, D29), and of
unit l1/calendar-phases-d109 (issue #221): the phases of a rotation (D109,
D132, D133).

The cases are PROPOSED (blueprint section 3.7). Every calendar is built here
from PLACEHOLDER crops and dates that are test values, not a declaration; the
record is the D29 record (2001-01-01 to 2024-12-31) unless a case says
otherwise. Expected dates are computed here from the PROPOSED form in the
docstring of ``repeat.py``, without calling the module.

Run from the repository root: ``py -3.12 -m pytest engine/calendar/test_repeat.py``.
"""

from __future__ import annotations

import ast
import calendar as gregorian
import copy
import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.common import Missing
from contracts.inputs.rotation_calendar import RotationCalendar
from engine.calendar import repeat
from engine.calendar.repeat import repeat_over_record

HERE = Path(__file__).parent
RECORD = (dt.date(2001, 1, 1), dt.date(2024, 12, 31))  # D29
JULY = 7
JANUARY = 1
CROP_A = "PLACEHOLDER-crop-a"
CROP_B = "PLACEHOLDER-crop-b"
CROP_C = "PLACEHOLDER-crop-c"


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def dated(text: str | None) -> dict[str, Any]:
    if text is None:
        return {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: no date"},
        }
    return {
        "date": text,
        "provenance": "DECLARED",
        "source": "PLACEHOLDER: test calendar, not a real declaration",
    }


def component(
    component_id: str,
    crop_id: str,
    start: str | None,
    end: str | None,
    periods: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "crop_id": crop_id,
        "start": dated(start),
        "end": dated(end),
        "periods": [
            {"period_type": kind, "start": dated(first), "end": dated(last)}
            for kind, first, last in periods or []
        ],
    }


def calendar_document(
    start: str, end: str, components: list[dict[str, Any]], month: int = JULY
) -> dict[str, Any]:
    return {
        "contract": "rotation_calendar",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "ag_year_start": {
            "month": month,
            "provisional": True,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER: test start month",
            "assumption": True,
        },
        "start_date": start,
        "end_date": end,
        "feasibility": {"feasible": True, "violations": []},
        "components": components,
    }


def build(
    start: str, end: str, components: list[dict[str, Any]], month: int = JULY
) -> RotationCalendar:
    return RotationCalendar.model_validate(
        calendar_document(start, end, components, month)
    )


def one_year(month: int = JULY) -> RotationCalendar:
    """One crop a year, dated after the record (as real calendars are)."""
    return build(
        "2027-11-15",
        "2028-05-05",
        [component("c1", CROP_A, "2027-11-15", "2028-05-05")],
        month,
    )


def three_years() -> RotationCalendar:
    """One crop in each of three agricultural years, dated after the record."""
    return build(
        "2027-09-01",
        "2030-06-30",
        [
            component("a", CROP_A, "2027-09-01", "2028-03-31"),
            component("b", CROP_B, "2028-10-01", "2029-04-30"),
            component("c", CROP_C, "2029-08-01", "2030-06-30"),
        ],
    )


def run(calendar: RotationCalendar, record=RECORD) -> repeat.RepeatedRotation:
    result = repeat_over_record(calendar, *record)
    assert isinstance(result, repeat.RepeatedRotation)
    return result


def cycle_of(result: repeat.RepeatedRotation, index: int) -> repeat.Cycle:
    """The cycle of an index (the lead-in is ``LEAD_IN``, point 13)."""
    (cycle,) = [c for c in result.cycles if c.index == index]
    return cycle


def ag_year_of(day: dt.date, month: int) -> int:
    return day.year if day.month >= month else day.year - 1


def ag_years(record, month: int) -> list[int]:
    return list(range(ag_year_of(record[0], month), ag_year_of(record[1], month) + 1))


def last_day_of_record_years(record, month: int) -> dt.date:
    return dt.date(ag_years(record, month)[-1] + 1, month, 1) - dt.timedelta(days=1)


def moved(day: dt.date, years: int) -> dt.date:
    """Point 2, computed again: same month and day, 29 February to 28."""
    year = day.year + years
    if (day.month, day.day) == (2, 29) and not gregorian.isleap(year):
        return dt.date(year, 2, 28)
    return day.replace(year=year)


def test_one_year_rotation_repeats_once_per_agricultural_year():
    result = run(one_year())
    years = ag_years(RECORD, JULY)
    assert result.ag_years == tuple(years)
    assert result.cycle_length == 1
    # D188 (2): the first sowing comes after the first day of the record's
    # years, so the cycle before the first is laid out; its crop ends before
    # that day and is listed, not laid out (points 6 and 13).
    lead, *cycles = result.cycles
    assert lead.index == repeat.LEAD_IN and lead.components_not_laid_out == ("c1",)
    assert lead.last_day == cycles[0].start - dt.timedelta(days=1)
    assert len(cycles) == len(years) == len(result.components)
    for year, item, cycle in zip(years, result.components, cycles):
        assert item.component_id == "c1" and item.crop_id == CROP_A
        assert item.start == dt.date(year, 11, 15)
        assert item.end == dt.date(year + 1, 5, 5)
        assert ag_year_of(item.start, JULY) == year
        assert item.cycle == cycle.index
        assert cycle.complete and cycle.components_not_laid_out == ()
    assert result.partial_cycle is None


def test_three_year_rotation_cycles_and_marks_the_partial_last_cycle():
    result = run(three_years())
    years = ag_years(RECORD, JULY)  # 2000 to 2024: 25 years
    assert result.cycle_length == 3
    starts = list(range(years[0], years[-1] + 1, 3))
    # D188 (2): the cycle before the first is laid out (the first sowing
    # comes after the first day of the record's years); every one of its
    # components ends before that day, so none is laid out.
    lead, *cycles = result.cycles
    assert lead.index == repeat.LEAD_IN and lead.shift_years == starts[0] - 2030
    assert lead.components_not_laid_out == ("a", "b", "c")
    assert [c.shift_years for c in cycles] == [y - 2027 for y in starts]
    ids = [item.component_id for item in result.components]
    assert ids[:6] == ["a", "b", "c", "a", "b", "c"]
    # The last cycle starts in the last agricultural year of the record:
    # only its first component is laid out, and the cycle is marked partial.
    partial = result.partial_cycle
    assert partial is result.cycles[-1]
    assert partial.start == dt.date(years[-1], 9, 1)
    assert partial.end > last_day_of_record_years(RECORD, JULY)
    assert partial.components_not_laid_out == ("b", "c")
    assert ids[-1] == "a" and result.components[-1].cycle == partial.index
    assert all(c.complete for c in result.cycles[:-1])
    for item in result.components:
        cycle = cycle_of(result, item.cycle)
        original = {c.component_id: c for c in three_years().components}[
            item.component_id
        ]
        assert item.start == moved(original.start.date, cycle.shift_years)
        assert item.end == moved(original.end.date, cycle.shift_years)


def test_cycle_is_the_smallest_whole_number_of_years_and_leaves_a_gap():
    # A rotation that straddles the start month at both ends (as a crop sown
    # in May with a July start does) is two years long, not three.
    straddling = build(
        "2028-05-25",
        "2030-04-20",
        [
            component("w", CROP_A, "2028-05-25", "2028-12-05"),
            component("s", CROP_B, "2028-12-10", "2029-05-10"),
            component("m", CROP_C, "2029-09-20", "2030-04-20"),
        ],
    )
    assert repeat.cycle_length_years(straddling) == 2
    result = run(straddling)
    for before, after in zip(result.cycles, result.cycles[1:]):
        assert after.start == moved(before.start, 2)
        assert before.end < after.start  # cycles never overlap
    # A calendar of one and a half years: a two-year cycle, and the days
    # between its end and the next start hold no component.
    gap = build(
        "2027-08-01",
        "2029-01-31",
        [component("g", CROP_A, "2027-08-01", "2029-01-31")],
    )
    result = run(gap)
    assert result.cycle_length == 2
    first, second = result.components[:2]
    assert second.start == moved(first.start, 2)
    assert (second.start - first.end).days > 1


def test_start_month_cuts_the_years_and_the_first_cycle():
    for month, first_year in ((JULY, 2000), (JANUARY, 2001)):
        result = run(one_year(month))
        assert result.ag_years == tuple(ag_years(RECORD, month))
        assert result.ag_years[0] == first_year
        assert result.first_day == dt.date(first_year, month, 1)
        assert result.last_day == last_day_of_record_years(RECORD, month)
        # The calendar's start_date falls in the first agricultural year,
        # with its month and day kept.
        first = [c for c in result.components if c.cycle == 0][0]
        assert ag_year_of(first.start, month) == first_year
        assert (first.start.month, first.start.day) == (11, 15)
        assert result.described_from == result.cycles[0].start
    # With a January start, 2027-11-15 is in agricultural year 2027 and the
    # harvest in 2028; with July both are in 2027.
    january = run(one_year(JANUARY))
    first = [c for c in january.components if c.cycle == 0][0]
    assert (first.start, first.end) == (d("2001-11-15"), d("2002-05-05"))
    # D141 (point 13): with a January start the crop of the cycle before runs
    # into the record (2000-11-15 to 2001-05-05), so it is laid out with its
    # dates and is present from the record's first day.
    (lead,) = [c for c in january.components if c.cycle == repeat.LEAD_IN]
    assert (lead.start, lead.end) == (d("2000-11-15"), d("2001-05-05"))
    assert january.cycles[0].index == repeat.LEAD_IN
    assert january.described_from == d("2000-11-15") < january.first_day
    # With a July start that crop ends before the record's years. D188 (2):
    # the cycle before the first is laid out all the same, with no component,
    # so the days from the first day to the first sowing are days with no
    # crop, not days the calendar does not describe.
    july = run(one_year(JULY))
    assert july.cycles[0].index == repeat.LEAD_IN
    assert july.cycles[0].components_not_laid_out == ("c1",)
    assert not [c for c in july.components if c.cycle == repeat.LEAD_IN]
    assert july.described_from == d("1999-11-15") < july.first_day


def test_leap_years_keep_month_and_day_and_29_february_becomes_28():
    calendar = build(
        "2027-07-01",
        "2028-06-30",
        [
            component(
                "c1",
                CROP_A,
                "2027-09-01",
                "2028-02-29",
                periods=[("PLACEHOLDER-period", "2028-01-01", "2028-02-29")],
            ),
            component("c2", CROP_B, "2028-03-01", "2028-05-31"),
        ],
    )
    result = run(calendar)
    first = [c for c in result.components if c.component_id == "c1"]
    for item in first:
        leap = gregorian.isleap(item.end.year)
        assert item.end == dt.date(item.end.year, 2, 29 if leap else 28)
        assert item.periods[0].end == item.end
        assert item.leap_day_moved is (not leap)
    assert {c.leap_day_moved for c in first} == {True, False}
    for item in result.components:
        if item.component_id == "c2":
            assert (item.start.month, item.start.day) == (3, 1)
            assert not item.leap_day_moved
    # A 28 February of a year without 29 February stays 28 February.
    plain = build(
        "2026-07-01",
        "2027-06-30",
        [component("p", CROP_A, "2026-09-01", "2027-02-28")],
    )
    for item in run(plain).components:
        assert (item.end.month, item.end.day) == (2, 28)
        assert not item.leap_day_moved


def test_calendar_outside_the_record_yields_periods_inside_it():
    for calendar in (one_year(), three_years()):
        assert calendar.start_date > RECORD[1]
        result = run(calendar)
        for item in result.components:
            assert result.first_day <= item.start <= result.last_day
            for period in item.periods:
                assert result.first_day <= period.start <= result.last_day
            assert item.ends_after_record is (item.end > result.last_day)
    # A crop sown in the last agricultural year and harvested after it keeps
    # its harvest date and is marked.
    late = build(
        "2027-05-01",
        "2027-08-31",
        [component("x", CROP_A, "2027-05-01", "2027-08-31")],
    )
    result = run(late)
    last = result.components[-1]
    assert last.start <= result.last_day < last.end and last.ends_after_record
    assert result.partial_cycle is result.cycles[-1]


def test_calendar_on_the_record_from_its_first_year_is_laid_out_unchanged():
    calendar = build(
        "2000-07-01",
        "2003-06-30",
        [
            component("a", CROP_A, "2000-09-01", "2001-02-28"),
            component("b", CROP_B, "2002-04-01", "2002-10-31"),
        ],
    )
    result = run(calendar)
    assert result.cycles[0].shift_years == 0
    first = [c for c in result.components if c.cycle == 0]
    assert [(c.start, c.end) for c in first] == [
        (c.start.date, c.end.date) for c in calendar.components
    ]


def test_missing_date_stays_missing_in_every_cycle_and_is_bounded_by_the_cycle():
    calendar = build(
        "2027-07-01",
        "2028-06-30",
        [
            component("a", CROP_A, "2027-09-01", "2027-12-31"),
            component("b", CROP_B, "2028-02-01", None),
            component("u", CROP_C, None, None),
        ],
    )
    result = run(calendar)
    for item in result.components:
        cycle = result.cycles[item.cycle]
        assert (item.calendar_start, item.calendar_end) == (cycle.start, cycle.end)
        assert item.cycle_last_day == cycle.last_day
        assert cycle.last_day == moved(cycle.start, 1) - dt.timedelta(days=1)
        if item.component_id == "b":
            assert item.start is not None and item.end is None
        if item.component_id == "u":
            assert item.start is None and item.end is None
    assert len([c for c in result.components if c.component_id == "u"]) == len(
        result.cycles
    )


def test_component_without_end_date_is_bounded_by_the_next_cycle_not_the_calendar():
    # As the rotation definition example: the last component (a pasture) has a
    # sowing date and no end, so the calendar ends on its sowing date.
    calendar = build(
        "2027-11-15",
        "2028-08-20",
        [
            component("c1", CROP_A, "2027-11-15", "2028-04-10"),
            component("c3", CROP_C, "2028-08-20", None),
        ],
    )
    result = run(calendar)
    assert result.cycle_length == 1
    for item in result.components:
        if item.component_id == "c3":
            cycle = cycle_of(result, item.cycle)
            assert item.end is None and item.calendar_end == item.start
            assert item.cycle_last_day == moved(cycle.start, 1) - dt.timedelta(days=1)
            assert item.cycle_last_day > item.calendar_end
    # D188 (2) lays out the cycle before the first: c1 ends before the first
    # day of the record's years and is listed; c3 can reach that day by the
    # bound of point 7, so it is laid out with its end still missing (its
    # days are not known, never days with no crop).
    lead = cycle_of(result, repeat.LEAD_IN)
    assert lead.components_not_laid_out == ("c1",)
    (c3,) = [c for c in result.components if c.cycle == repeat.LEAD_IN]
    assert c3.component_id == "c3" and c3.end is None
    assert result.first_day < c3.start < c3.cycle_last_day
    assert c3.cycle_last_day == cycle_of(result, 0).start - dt.timedelta(days=1)


def test_start_month_missing_returns_missing_input():
    document = calendar_document(
        "2027-11-15", "2028-05-05", [component("c1", CROP_A, "2027-11-15", None)]
    )
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: none"},
    }
    result = repeat_over_record(RotationCalendar.model_validate(document), *RECORD)
    assert isinstance(result, Missing)
    assert result.reason == "MISSING_INPUT" and "D47" in result.detail


def test_arguments_of_another_type_or_a_reversed_record_raise():
    with pytest.raises(TypeError):
        repeat_over_record(calendar_document("2027-11-15", "2028-05-05", []), *RECORD)
    with pytest.raises(TypeError):
        repeat_over_record(one_year(), "2001-01-01", RECORD[1])
    with pytest.raises(TypeError):
        repeat_over_record(one_year(), dt.datetime(2001, 1, 1), RECORD[1])
    with pytest.raises(ValueError):
        repeat_over_record(one_year(), RECORD[1], RECORD[0])


def test_calendar_unchanged_and_second_call_equal():
    calendar = three_years()
    before = copy.deepcopy(calendar)
    first = repeat_over_record(calendar, *RECORD)
    assert calendar == before
    assert repeat_over_record(calendar, *RECORD) == first


def test_short_record_inside_one_cycle():
    record = (d("2010-03-01"), d("2010-09-30"))
    result = run(three_years(), record)
    assert result.ag_years == (2009, 2010)
    # D188 (2): the first cycle starts on 2009-09-01, after the first day of
    # the record's years, so the cycle before it is laid out; its components
    # all end before that day.
    lead, cycle = result.cycles
    assert lead.index == repeat.LEAD_IN
    assert lead.components_not_laid_out == ("a", "b", "c")
    assert result.partial_cycle is cycle and cycle.index == 0
    assert cycle.components_not_laid_out == ("c",)


def test_module_imports_no_clock_and_only_the_input_contracts():
    """As the rule of this folder (test_calendar.py), and tighter: only
    ``__future__``, ``dataclasses`` and ``contracts.inputs``."""
    tree = ast.parse((HERE / "repeat.py").read_text("utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.append(node.module)
        elif isinstance(node, ast.Name):
            assert node.id not in {"open", "print"}
    for name in imported:
        assert name in {"__future__", "dataclasses"} or name.startswith(
            "contracts.inputs."
        ), name


# ---------------------------------------------------------------------------
# Unit l1/calendar-phases-d109 (issue #221, with its amendment): the phases of
# a rotation as a moved calendar (D109, D132, D133). The cases are PROPOSED;
# calendars are PLACEHOLDER test values. Expected dates are computed here
# from points 8 to 12 of ``repeat.py``.
# ---------------------------------------------------------------------------

EXAMPLES = HERE.parent.parent / "contracts"
EXAMPLE_CALENDAR = (
    EXAMPLES / "inputs" / "examples" / "PLACEHOLDER_rotation_calendar.json"
)
EXAMPLE_DEFINITION = (
    EXAMPLES
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)


def two_years(*extra: dict[str, Any]) -> RotationCalendar:
    """One crop in each of two agricultural years, dated after the record."""
    return build(
        "2027-09-01",
        "2029-06-30",
        [
            component("a", CROP_A, "2027-09-01", "2028-03-31"),
            *extra,
            component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )


def dates_of(calendar: RotationCalendar) -> list[tuple[str, Any, Any]]:
    return [(c.component_id, c.start.date, c.end.date) for c in calendar.components]


def assert_valid_with_cycle(moved_calendar: RotationCalendar, length: int) -> None:
    """Valid as a calendar of the contract, and the cycle of point 3 kept."""
    again = RotationCalendar.model_validate_json(moved_calendar.model_dump_json())
    assert again == moved_calendar
    assert repeat.cycle_length_years(moved_calendar) == length
    assert repeat.list_phases(moved_calendar) == list(range(length))


def test_list_phases_one_per_year_of_the_cycle():
    assert repeat.list_phases(one_year()) == [0]
    assert repeat.list_phases(one_year(JANUARY)) == [0]
    assert repeat.list_phases(two_years()) == [0, 1]
    assert repeat.list_phases(three_years()) == [0, 1, 2]
    with pytest.raises(TypeError):
        repeat.list_phases(calendar_document("2027-11-15", "2028-05-05", []))


def test_phase_0_is_the_calendar_unchanged():
    for calendar in (one_year(), two_years(), three_years()):
        moved_calendar = repeat.phase_calendar(calendar, 0)
        assert moved_calendar == calendar and moved_calendar is not calendar
        assert repeat_over_record(moved_calendar, *RECORD) == repeat_over_record(
            calendar, *RECORD
        )
        assert repeat.components_crossing_phase(calendar, 0) == []


def test_two_year_rotation_phase_1_starts_with_its_second_year():
    calendar = two_years()
    moved_calendar = repeat.phase_calendar(calendar, 1)
    # Year 1 (crop b) kept and first; year 0 (crop a) one cycle later.
    assert dates_of(moved_calendar) == [
        ("b", d("2028-10-01"), d("2029-04-30")),
        ("a", d("2029-09-01"), d("2030-03-31")),
    ]
    assert moved_calendar.start_date == d("2028-09-01")  # start_date moved 1 year
    assert moved_calendar.end_date == d("2030-03-31")
    assert_valid_with_cycle(moved_calendar, 2)
    assert moved_calendar.feasibility == calendar.feasibility
    assert moved_calendar.ag_year_start == calendar.ag_year_start
    assert repeat.components_crossing_phase(calendar, 1) == []
    # Laid out over the record, crop b falls on the first agricultural year.
    laid = run(moved_calendar)
    first = laid.components[0]
    assert (first.component_id, first.start, first.end) == (
        "b",
        d("2000-10-01"),
        d("2001-04-30"),
    )
    assert ag_year_of(first.start, JULY) == laid.ag_years[0]
    assert [c.component_id for c in laid.components[:4]] == ["b", "a", "b", "a"]
    assert laid.components[1].start == d("2001-09-01")


def test_every_phase_lays_its_year_on_the_first_record_year():
    calendar = three_years()
    originals = {c.component_id: c for c in calendar.components}
    year_of = {"a": 0, "b": 1, "c": 2}
    first_year = ag_years(RECORD, JULY)[0]
    for phase in (0, 1, 2):
        moved_calendar = repeat.phase_calendar(calendar, phase)
        assert_valid_with_cycle(moved_calendar, 3)
        expected_order = [k for k in "abc" if year_of[k] >= phase] + [
            k for k in "abc" if year_of[k] < phase
        ]
        assert [c.component_id for c in moved_calendar.components] == expected_order
        laid = run(moved_calendar)
        assert laid.components[0].component_id == "abc"[phase]
        shift = first_year - (2027 + phase)
        for item in laid.components:
            original = originals[item.component_id]
            years = (
                shift
                + 3 * item.cycle
                + (3 if year_of[item.component_id] < phase else 0)
            )
            assert item.start == moved(original.start.date, years)
            assert item.end == moved(original.end.date, years)
            assert laid.first_day <= item.start <= laid.last_day


def test_component_crossing_into_year_p_keeps_its_dates():
    # D141: x starts in year 0 (May, before the July start month) and ends in
    # year 1. It keeps its declared dates, moved one cycle as year 0 is.
    crossing = component("x", CROP_C, "2028-05-01", "2028-09-30")
    calendar = two_years(crossing)
    assert repeat.components_crossing_phase(calendar, 1) == ["x"]
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    x = {c.component_id: c for c in moved_calendar.components}["x"]
    assert (x.start.date, x.end.date) == (d("2030-05-01"), d("2030-09-30"))
    assert x.start.missing is None and x.end.missing is None
    # The start comes after x's last date, so x lies whole in one cycle.
    assert moved_calendar.start_date == d("2028-10-01")
    laid = run(moved_calendar)
    # In the record, the x of the cycle before runs from 2000-05-01: the part
    # before the record's first day falls outside it, and x is present from
    # that day (point 13).
    (lead,) = [c for c in laid.components if c.cycle == repeat.LEAD_IN]
    assert (lead.component_id, lead.start, lead.end) == (
        "x",
        d("2000-05-01"),
        d("2000-09-30"),
    )
    assert lead.start < laid.first_day <= lead.end
    assert all(c.end is not None for c in laid.components if c.component_id == "x")


def test_crossing_shown_by_a_period_or_left_unknown_by_a_missing_date():
    calendar = two_years(
        component(
            "e",
            CROP_C,
            "2028-05-01",
            None,
            periods=[("PLACEHOLDER-period", "2028-05-01", "2028-08-15")],
        ),
        component("u", CROP_C, "2028-04-01", None),
        component("s", CROP_C, None, "2028-09-30"),
        component("n", CROP_C, None, None),
    )
    assert repeat.components_crossing_phase(calendar, 1) == ["e"]
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    by_id = {c.component_id: c for c in moved_calendar.components}
    # e crosses by its period; its known dates end before the start, so it
    # keeps them (D141), its end still missing for its own reason.
    period = by_id["e"].periods[0]
    assert (period.start.date, period.end.date) == (d("2030-05-01"), d("2030-08-15"))
    assert by_id["e"].start.date == d("2030-05-01")
    assert by_id["e"].end.missing.reason == "NOT_DECLARED"
    # No date shows u crossing: moved with its end still missing.
    assert by_id["u"].start.date == d("2030-04-01")
    assert by_id["u"].end.missing.reason == "NOT_DECLARED"
    # s belongs to year 1 by its end, n to no year: both kept as they are.
    assert by_id["s"].start.date is None and by_id["s"].end.date == d("2028-09-30")
    assert by_id["n"].start.date is None and by_id["n"].end.date is None


def test_phase_moves_29_february_with_shifted_date():
    calendar = build(
        "2027-07-01",
        "2029-06-30",
        [
            component(
                "l",
                CROP_A,
                "2027-09-01",
                "2028-02-29",
                periods=[("PLACEHOLDER-period", "2028-01-01", "2028-02-29")],
            ),
            component("m", CROP_B, "2028-09-01", "2029-03-31"),
        ],
    )
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    leap = {c.component_id: c for c in moved_calendar.components}["l"]
    assert leap.end.date == repeat.shifted_date(d("2028-02-29"), 2)[0]
    assert leap.end.date == d("2030-02-28")
    assert leap.periods[0].end.date == d("2030-02-28")


def test_phase_out_of_range_or_not_a_whole_number_raises_value_error():
    calendar = two_years()
    for phase in (-1, 2, 3, True, 1.0, None, "1"):
        with pytest.raises(ValueError):
            repeat.phase_calendar(calendar, phase)
        with pytest.raises(ValueError):
            repeat.components_crossing_phase(calendar, phase)
    with pytest.raises(ValueError):
        repeat.phase_calendar(one_year(), 1)
    with pytest.raises(TypeError):  # p has no default
        repeat.phase_calendar(calendar)
    with pytest.raises(TypeError):
        repeat.phase_calendar(calendar_document("2027-11-15", "2028-05-05", []), 0)


def test_phase_above_0_with_start_month_missing_raises():
    document = calendar_document(
        "2027-09-01",
        "2029-06-30",
        [component("a", CROP_A, "2027-09-01", "2029-04-30")],
    )
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: none"},
    }
    calendar = RotationCalendar.model_validate(document)
    assert repeat.list_phases(calendar) == [0, 1]
    assert repeat.phase_calendar(calendar, 0) == calendar
    with pytest.raises(ValueError, match="D132"):
        repeat.phase_calendar(calendar, 1)


def test_end_date_keeps_the_cycle_when_a_year_ends_early():
    # Year 1 holds a crop that ends before the calendar's start day comes
    # round again: in phase 2 the dates placed span less than two years from
    # the moved start, so the end date is set to keep the three-year cycle
    # (point 12).
    calendar = build(
        "2027-11-15",
        "2030-01-10",
        [
            component("a", CROP_A, "2027-11-15", "2028-03-01"),
            component("b", CROP_B, "2028-08-01", "2028-10-01"),
            component("c", CROP_C, "2029-11-20", "2030-01-10"),
        ],
    )
    assert repeat.list_phases(calendar) == [0, 1, 2]
    moved_calendar = repeat.phase_calendar(calendar, 2)
    assert dates_of(moved_calendar)[-1] == ("b", d("2031-08-01"), d("2031-10-01"))
    assert moved_calendar.start_date == d("2029-11-15")
    assert moved_calendar.end_date == d("2031-11-15")  # start moved 2 years
    assert_valid_with_cycle(moved_calendar, 3)
    laid = run(moved_calendar)
    for before, after in zip(laid.cycles, laid.cycles[1:]):
        assert after.shift_years == before.shift_years + 3


def test_phase_calendar_leaves_the_calendar_unchanged_and_is_repeatable():
    calendar = two_years(component("x", CROP_C, "2028-05-01", "2028-09-30"))
    before = copy.deepcopy(calendar)
    first = repeat.phase_calendar(calendar, 1)
    assert calendar == before
    assert repeat.phase_calendar(calendar, 1) == first


def test_example_calendars_of_the_contracts():
    from contracts.rotation_definition import RotationDefinition
    from engine.calendar import build_rotation_calendar

    definition = RotationDefinition.model_validate_json(
        EXAMPLE_DEFINITION.read_text("utf-8")
    )
    from_ep2 = build_rotation_calendar(definition)
    assert repeat.list_phases(from_ep2) == [0]  # a one-year rotation
    assert repeat.phase_calendar(from_ep2, 0) == from_ep2

    calendar = RotationCalendar.model_validate_json(EXAMPLE_CALENDAR.read_text("utf-8"))
    assert repeat.list_phases(calendar) == [0, 1]
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    # Component 2 runs from April into October, across the July start month.
    assert repeat.components_crossing_phase(calendar, 1) == ["PLACEHOLDER-component-2"]


def test_start_of_a_phase_stays_in_year_p_when_a_crossing_runs_past_it():
    # Verifier's case on PR #228 (B1): "long" starts in year 0 and ends in
    # year 2; the start of phase 1 stays in year 1, so phase 1 must not
    # turn into phase 2.
    calendar = build(
        "2030-07-01",
        "2033-06-30",
        [
            component("long", CROP_A, "2030-09-01", "2032-07-31"),
            component("c", CROP_C, "2032-10-01", "2033-05-31"),
        ],
    )
    assert repeat.list_phases(calendar) == [0, 1, 2]
    starts = {}
    for phase in (1, 2):
        assert repeat.components_crossing_phase(calendar, phase) == ["long"]
        moved_calendar = repeat.phase_calendar(calendar, phase)
        assert_valid_with_cycle(moved_calendar, 3)
        assert ag_year_of(moved_calendar.start_date, JULY) == 2030 + phase
        starts[phase] = moved_calendar.start_date
    # The start is capped at the last day of year 1 in phase 1 (point 12).
    assert starts == {1: d("2032-06-30"), 2: d("2032-08-01")}
    assert repeat.phase_calendar(calendar, 1) != repeat.phase_calendar(calendar, 2)


def test_start_of_a_phase_is_capped_at_the_last_day_of_year_p():
    # x crosses into year 1 and ends on its last day: the day after would be
    # year 2, so the start is the last day of year 1 (point 12).
    calendar = build(
        "2027-09-01",
        "2029-06-30",
        [
            component("a", CROP_A, "2027-09-01", "2028-03-31"),
            component("x", CROP_C, "2028-05-01", "2029-06-30"),
        ],
    )
    assert repeat.list_phases(calendar) == [0, 1]
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    assert moved_calendar.start_date == d("2029-06-30")
    assert ag_year_of(moved_calendar.start_date, JULY) == 2028
    laid = run(moved_calendar)
    assert ag_year_of(cycle_of(laid, 0).start, JULY) == laid.ag_years[0]
    # The first cycle starts after the first day of the record's years, so
    # the cycle before it is laid out (D188 (2)).
    assert laid.cycles[0].index == repeat.LEAD_IN


def e1() -> RotationCalendar:
    """The verifier's calendar on PR #228: "long" runs from year 0 to year 2."""
    return build(
        "2030-07-01",
        "2033-06-30",
        [
            component("long", CROP_A, "2030-09-01", "2032-07-31"),
            component("c", CROP_C, "2032-10-01", "2033-05-31"),
        ],
    )


def test_crossing_past_year_p_cannot_be_placed_and_no_day_reads_no_crop():
    # E1 phase 1: "long" runs past the last day of year 1, so no start in
    # year 1 lets it lie whole in one cycle (OPEN, D141 quoted in repeat.py).
    # Its dates are missing; EP1 bounds it by the whole cycle: no day of the
    # record reads {"management": "no_crop"}, and crop c keeps its days. A
    # cross-lane check of the reading of engine/erosion/soil_loss.py.
    from engine.erosion.soil_loss import NO_CROP_SCOPE, _crop_scope

    moved_calendar = repeat.phase_calendar(e1(), 1)
    long = {c.component_id: c for c in moved_calendar.components}["long"]
    for value in (long.start, long.end):
        assert value.date is None
        assert value.missing.reason == repeat.CROSSING_REASON == "NOT_COMPUTABLE"
        assert "D141" in value.missing.detail
    laid = run(moved_calendar)
    c_days = {
        day
        for item in laid.components
        if item.component_id == "c"
        for day in (
            item.start + dt.timedelta(days=n)
            for n in range((min(item.end, laid.last_day) - item.start).days + 1)
        )
    }
    counts = {"no_crop": 0, "missing": 0, "c": 0}
    day = laid.first_day
    while day <= laid.last_day:
        scope = _crop_scope(laid, day)
        if scope == NO_CROP_SCOPE:
            counts["no_crop"] += 1
        elif isinstance(scope, dict):
            assert scope == {"crop": CROP_C} and day in c_days, day
            counts["c"] += 1
        else:
            assert scope.reason == "MISSING_INPUT", day
            assert day not in c_days, day
            counts["missing"] += 1
        day += dt.timedelta(days=1)
    assert counts["no_crop"] == 0
    assert counts["c"] == len(c_days) > 0
    # The verifier's cycle 2004-06-30 to 2007-06-29: 852 missing, 243 of c.
    cycle = [d("2004-06-30") + dt.timedelta(days=n) for n in range(1095)]
    scopes = [_crop_scope(laid, day) for day in cycle]
    assert sum(1 for s in scopes if s == {"crop": CROP_C}) == 243
    assert sum(1 for s in scopes if not isinstance(s, dict)) == 852


def test_crossing_that_ends_inside_year_p_keeps_all_its_dates():
    # D141: a crossing component that ends inside year p keeps its declared
    # dates, moved one cycle; none is missing.
    calendar = two_years(component("x", CROP_C, "2028-05-01", "2028-09-30"))
    x = {c.component_id: c for c in repeat.phase_calendar(calendar, 1).components}["x"]
    assert (x.start.date, x.end.date) == (d("2030-05-01"), d("2030-09-30"))
    # The same for the phase of E1 whose year holds the end of "long".
    moved_calendar = repeat.phase_calendar(e1(), 2)
    assert_valid_with_cycle(moved_calendar, 3)
    long = {c.component_id: c for c in moved_calendar.components}["long"]
    assert (long.start.date, long.end.date) == (d("2033-09-01"), d("2035-07-31"))


def soy_wheat_maize() -> RotationCalendar:
    """A PLACEHOLDER two-year rotation like the demonstration's (D72, D73):
    wheat from late May to early December spans the July start month, then a
    summer crop and maize. Dates are test values, not the demonstration's."""
    return build(
        "2027-05-25",
        "2029-03-31",
        [
            component("wheat", CROP_A, "2027-05-25", "2027-12-05"),
            component("soy", CROP_B, "2027-12-10", "2028-04-20"),
            component("maize", CROP_C, "2028-09-15", "2029-03-31"),
        ],
    )


def true_crop(
    calendar: RotationCalendar, phase: int, day: dt.date, record=RECORD
) -> str | None:
    """The crop on a day of the record by D109 and D141, computed again from
    the calendar's own dates: every component in every cycle (before the
    record too), the calendar's year ``phase`` on the record's first year."""
    length = repeat.cycle_length_years(calendar)
    shift = phase_shift(calendar, phase, record)
    found = None
    for k in range(-2, 30):
        for item in calendar.components:
            start = moved(item.start.date, shift + k * length)
            end = moved(item.end.date, shift + k * length)
            if start <= day <= end:
                assert found is None, day
                found = item.crop_id
    return found


def phase_shift(calendar: RotationCalendar, phase: int, record=RECORD) -> int:
    """Point 9 computed again: years added to the calendar so that its year
    ``phase`` falls on the record's first agricultural year."""
    month = calendar.ag_year_start.month
    first = ag_years(record, month)[0]
    return first - ag_year_of(calendar.start_date, month) - phase


def test_soy_wheat_maize_phases_lay_out_every_crop_from_the_first_day():
    # D141 with a wheat that spans 1 July: in each phase EP1's crop of every
    # day of the record is the crop the rotation has on it (D109, D141): no
    # day with a crop reads no_crop, none reads missing, and in phase 1 the
    # crossing wheat is the crop from the record's first day. A cross-lane
    # check of the reading of engine/erosion/soil_loss.py.
    from engine.erosion.soil_loss import NO_CROP_SCOPE, _crop_scope

    calendar = soy_wheat_maize()
    assert repeat.list_phases(calendar) == [0, 1]
    assert repeat.components_crossing_phase(calendar, 1) == ["wheat"]
    moved_calendar = repeat.phase_calendar(calendar, 1)
    assert_valid_with_cycle(moved_calendar, 2)
    assert dates_of(moved_calendar) == [
        ("soy", d("2027-12-10"), d("2028-04-20")),
        ("maize", d("2028-09-15"), d("2029-03-31")),
        ("wheat", d("2029-05-25"), d("2029-12-05")),
    ]
    for phase in (0, 1):
        laid = run(repeat.phase_calendar(calendar, phase))
        day = laid.first_day
        while day <= laid.last_day:
            expected = true_crop(calendar, phase, day)
            scope = _crop_scope(laid, day)
            if expected is None:
                assert scope == NO_CROP_SCOPE, (phase, day)
            else:
                assert scope == {"crop": expected}, (phase, day)
            day += dt.timedelta(days=1)
    phase_1 = run(moved_calendar)
    for offset in range(158):  # 2000-07-01 to 2000-12-05
        day = phase_1.first_day + dt.timedelta(days=offset)
        assert _crop_scope(phase_1, day) == {"crop": CROP_A}, day
    assert _crop_scope(phase_1, d("2000-12-06")) == NO_CROP_SCOPE


def test_e1_phase_2_lays_out_long_from_the_first_day():
    # D141: in phase 2 of E1, "long" ends inside year 2 and keeps its dates;
    # its occurrence before the record runs to 2000-07-31 and is EP1's crop
    # from the record's first day. A cross-lane check of EP1's reading.
    from engine.erosion.soil_loss import NO_CROP_SCOPE, _crop_scope

    laid = run(repeat.phase_calendar(e1(), 2))
    (lead,) = [c for c in laid.components if c.cycle == repeat.LEAD_IN]
    assert (lead.component_id, lead.start, lead.end) == (
        "long",
        d("1998-09-01"),
        d("2000-07-31"),
    )
    day = laid.first_day
    while day <= laid.last_day:
        expected = true_crop(e1(), 2, day)
        scope = _crop_scope(laid, day)
        assert scope == (NO_CROP_SCOPE if expected is None else {"crop": expected})
        day += dt.timedelta(days=1)


# ---------------------------------------------------------------------------
# Unit l1/calendar-lead-in-d188-part2 (issue #372): the cycle before the
# first is laid out whenever the first cycle starts after the first day of
# the record's years, in every phase (decision D188 of issue #77, part (2);
# points 6 and 13 of ``repeat.py``). Calendars and records are PLACEHOLDER
# test values. The crop of each day is computed again with ``true_crop``
# from the calendar's own dates, and read through EP1 as above.
# ---------------------------------------------------------------------------

# A PLACEHOLDER record whose first day is the first day of its years (July).
RECORD_FROM_ITS_FIRST_DAY = (d("2001-07-01"), d("2024-06-30"))
BOTH_RECORDS = pytest.mark.parametrize(
    "record",
    [RECORD, RECORD_FROM_ITS_FIRST_DAY],
    ids=["D29", "from-its-first-day"],
)


def described_to_the_end_of_the_first_cycle(
    calendar: RotationCalendar, phase: int, record
) -> repeat.RepeatedRotation:
    """The phase laid out over the record, after checking that every day from
    the first day of the record's years to the last day of the first cycle
    reads, through EP1, the crop the rotation has on it or no crop, and none
    reads missing. A cross-lane check of engine/erosion/soil_loss.py."""
    from engine.erosion.soil_loss import NO_CROP_SCOPE, _crop_scope

    laid = run(repeat.phase_calendar(calendar, phase), record)
    assert laid.described_from <= laid.first_day
    day = laid.first_day
    while day <= cycle_of(laid, 0).last_day:
        expected = true_crop(calendar, phase, day, record)
        scope = _crop_scope(laid, day)
        crop = NO_CROP_SCOPE if expected is None else {"crop": expected}
        assert scope == crop, (phase, day)
        day += dt.timedelta(days=1)
    return laid


@BOTH_RECORDS
def test_first_sowing_after_the_first_day_lays_out_the_cycle_before(record):
    # D188 (2), with no component crossing the start month: in every phase
    # the first sowing comes after the first day of the record's years and
    # every component of the cycle before ends before that day. That cycle is
    # laid out all the same, with none of them, so the days from the first
    # day to the first sowing are days with no crop, not days the calendar
    # does not describe.
    calendar = three_years()
    for phase in repeat.list_phases(calendar):
        assert repeat.components_crossing_phase(calendar, phase) == []
        laid = described_to_the_end_of_the_first_cycle(calendar, phase, record)
        lead, first = laid.cycles[:2]
        assert (lead.index, first.index) == (repeat.LEAD_IN, 0)
        assert lead.start < laid.first_day < first.start
        assert lead.last_day == first.start - dt.timedelta(days=1)
        assert sorted(lead.components_not_laid_out) == ["a", "b", "c"]
        assert not [c for c in laid.components if c.cycle == repeat.LEAD_IN]
        assert laid.described_from == lead.start


@BOTH_RECORDS
def test_first_sowing_after_the_first_day_with_a_crossing_component(record):
    # D188 (2), with x crossing the July start month: in phase 0 the x of the
    # cycle before ends before the first day of the record's years, so that
    # cycle is laid out with no component (part (2)); in phase 1 it ends
    # inside the record's years and is laid out with its dates (part (1),
    # D141). In both phases every day is described.
    calendar = two_years(component("x", CROP_C, "2028-05-01", "2028-09-30"))
    assert repeat.components_crossing_phase(calendar, 1) == ["x"]
    for phase, laid_in_the_lead_in in ((0, []), (1, ["x"])):
        laid = described_to_the_end_of_the_first_cycle(calendar, phase, record)
        assert laid.cycles[0].index == repeat.LEAD_IN
        assert laid.first_day < cycle_of(laid, 0).start
        assert [
            c.component_id for c in laid.components if c.cycle == repeat.LEAD_IN
        ] == laid_in_the_lead_in


@BOTH_RECORDS
def test_first_cycle_that_starts_on_the_first_day_is_unchanged(record):
    # The calendar starts on 1 July, the first day of its agricultural year,
    # in both phases: its first cycle starts on the first day of the record's
    # years, so nothing is laid out before it (point 6) and every day lies in
    # a cycle already; the days before its first sowing are days with no
    # crop of the first cycle.
    calendar = build(
        "2027-07-01",
        "2029-06-30",
        [
            component("a", CROP_A, "2027-09-01", "2028-03-31"),
            component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    for phase in repeat.list_phases(calendar):
        laid = described_to_the_end_of_the_first_cycle(calendar, phase, record)
        assert cycle_of(laid, 0).start == laid.first_day == laid.described_from
        assert [c.index for c in laid.cycles] == list(range(len(laid.cycles)))
        assert all(c.cycle >= 0 for c in laid.components)


def soybean_winter_fallow() -> RotationCalendar:
    """A PLACEHOLDER one-year rotation shaped as the D128 rotation soybean -
    winter fallow: a soybean sown after the July start month and harvested
    before it, and a winter fallow, the days no component holds. Dates and
    years are test values, not the demonstration's."""
    return build(
        "2027-11-15",
        "2028-05-05",
        [component("soybean", CROP_A, "2027-11-15", "2028-05-05")],
    )


@BOTH_RECORDS
def test_soybean_winter_fallow_describes_its_first_agricultural_year(record):
    # D188 (2) on the D128 rotation soybean - winter fallow: the first
    # agricultural year of the record is fully described. The cycle before
    # holds no component (its soybean is harvested before the first day of
    # the record's years), so the days to the first sowing are days with no
    # crop; then the soybean; then the winter fallow, days with no crop.
    from engine.erosion.soil_loss import NO_CROP_SCOPE, _crop_scope

    calendar = soybean_winter_fallow()
    assert repeat.list_phases(calendar) == [0]
    laid = described_to_the_end_of_the_first_cycle(calendar, 0, record)
    lead = laid.cycles[0]
    assert lead.index == repeat.LEAD_IN
    assert lead.components_not_laid_out == ("soybean",)
    first_year = laid.ag_years[0]
    sowing = dt.date(first_year, 11, 15)
    harvest = dt.date(first_year + 1, 5, 5)
    day = laid.first_day
    while day < dt.date(first_year + 1, JULY, 1):
        crop = {"crop": CROP_A} if sowing <= day <= harvest else NO_CROP_SCOPE
        assert _crop_scope(laid, day) == crop, day
        day += dt.timedelta(days=1)
