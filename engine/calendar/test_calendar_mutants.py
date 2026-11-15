"""Mutant-killing tests for ``engine/calendar/`` (unit l1/calendar-mutants).

Targets boundary, off-by-one, infeasibility, and ordering mutants in
``build.py``, ``rules.py``, and ``repeat.py``, including D188 part 2 lead-in
boundaries (#403).

All crop, component, case, field, and rotation identifiers and dates are
PLACEHOLDER test inputs.
"""

from __future__ import annotations

import calendar as gregorian
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.rotation_definition.common import DateValue as DeclaredDate
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar, repeat
from engine.calendar.repeat import (
    CROSSING_REASON,
    LEAD_IN,
    RepeatedRotation,
    components_crossing_phase,
    cycle_length_years,
    phase_calendar,
    repeat_over_record,
)
from engine.calendar.rules import (
    HARVEST_NOT_BEFORE_SOWING,
    POSITIONS_NUMBER_THE_COMPONENTS,
)

HERE = Path(__file__).parent
EXAMPLE_DEFINITION = (
    HERE.parents[1]
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
RECORD = (dt.date(2001, 1, 1), dt.date(2024, 12, 31))
RECORD_FROM_ITS_FIRST_DAY = (dt.date(2001, 7, 1), dt.date(2024, 6, 30))
JULY = 7
CROP_A = "PLACEHOLDER-crop-a"
CROP_B = "PLACEHOLDER-crop-b"
CROP_C = "PLACEHOLDER-crop-c"


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def load_example_definition() -> dict[str, Any]:
    return json.loads(EXAMPLE_DEFINITION.read_text(encoding="utf-8"))


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


def make_component(
    component_id: str,
    crop_id: str,
    start: str | None,
    end: str | None,
    periods: list[tuple[str, str | None, str | None]] | None = None,
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


def make_calendar(
    start: str,
    end: str,
    components: list[dict[str, Any]],
    month: int = JULY,
) -> RotationCalendar:
    return RotationCalendar.model_validate(
        {
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
    )


def run_repeat(
    calendar: RotationCalendar,
    record: tuple[dt.date, dt.date] = RECORD,
) -> RepeatedRotation:
    result = repeat_over_record(calendar, *record)
    assert isinstance(result, RepeatedRotation)
    return result


# --- rules.py & build.py mutants ----------------------------------------------


@pytest.mark.parametrize(
    "positions",
    [
        [1, 2, 4],
        [2, 3, 4],
        [0, 1, 2],
        [4, 2, 1],
    ],
    ids=["gap-1-2-4", "starts-at-two", "starts-at-zero", "reversed-with-gap"],
)
def test_unique_positions_not_numbered_one_to_n_are_infeasible(
    positions: list[int],
) -> None:
    rotation = RotationDefinition.model_validate(load_example_definition())
    for component, pos in zip(rotation.components, positions, strict=True):
        component.position = pos
    calendar = build_rotation_calendar(rotation)
    assert calendar.feasibility.feasible is False
    assert [v.rule for v in calendar.feasibility.violations] == [
        POSITIONS_NUMBER_THE_COMPONENTS
    ]
    assert calendar.feasibility.violations[0].component_ids == []


def test_single_component_with_position_not_one_is_infeasible() -> None:
    data = load_example_definition()
    data["components"] = data["components"][:1]
    rotation = RotationDefinition.model_validate(data)
    for bad_pos in (0, 2):
        rotation.components[0].position = bad_pos
        calendar = build_rotation_calendar(rotation)
        assert calendar.feasibility.feasible is False
        assert [v.rule for v in calendar.feasibility.violations] == [
            POSITIONS_NUMBER_THE_COMPONENTS
        ]


def test_multiple_harvest_before_sowing_violations_all_reported_in_order() -> None:
    rotation = RotationDefinition.model_validate(load_example_definition())
    first, middle, last = rotation.components
    first.harvest = DeclaredDate(
        date=first.sowing.date - dt.timedelta(days=1),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    last.sowing = DeclaredDate(
        date=d("2028-09-10"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    last.harvest = DeclaredDate(
        date=d("2028-09-01"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    calendar = build_rotation_calendar(rotation)
    assert calendar.feasibility.feasible is False
    assert [(v.rule, v.component_ids) for v in calendar.feasibility.violations] == [
        (HARVEST_NOT_BEFORE_SOWING, [first.component_id]),
        (HARVEST_NOT_BEFORE_SOWING, [last.component_id]),
    ]
    assert calendar.components[0].start.date is None
    assert calendar.components[0].end.date is None
    assert calendar.components[1].start.date == middle.sowing.date
    assert calendar.components[2].start.date is None
    assert calendar.components[2].end.date is None


def test_unplaced_harvest_before_sowing_dates_excluded_from_calendar_span() -> None:
    rotation = RotationDefinition.model_validate(load_example_definition())
    first, middle, last = rotation.components
    first.sowing = DeclaredDate(
        date=d("2027-01-10"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    first.harvest = DeclaredDate(
        date=d("2027-01-05"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    calendar = build_rotation_calendar(rotation)
    assert calendar.start_date == middle.sowing.date
    assert calendar.end_date == last.sowing.date

    rotation2 = RotationDefinition.model_validate(load_example_definition())
    c1, c2, c3 = rotation2.components
    c3.sowing = DeclaredDate(
        date=d("2030-02-10"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    c3.harvest = DeclaredDate(
        date=d("2030-02-01"),
        provenance="DECLARED",
        source="PLACEHOLDER: test",
    )
    calendar2 = build_rotation_calendar(rotation2)
    assert calendar2.start_date == c1.sowing.date
    assert calendar2.end_date == c2.sowing.date


def test_single_component_with_one_missing_date_sets_start_and_end() -> None:
    data = load_example_definition()
    data["components"] = data["components"][:1]
    data["components"][0]["sowing"] = {
        "date": None,
        "missing": {"reason": "NOT_DECLARED"},
    }
    calendar = build_rotation_calendar(RotationDefinition.model_validate(data))
    expected = d("2028-04-10")
    assert calendar.start_date == expected
    assert calendar.end_date == expected


# --- repeat.py: cycle length, record bounds, component bounds -----------------


def test_cycle_length_is_two_when_end_equals_one_year_anniversary_of_start() -> None:
    anniversary = make_calendar(
        "2027-07-01",
        "2028-07-01",
        [make_component("a", CROP_A, "2027-07-01", "2028-07-01")],
    )
    assert cycle_length_years(anniversary) == 2
    laid = run_repeat(anniversary)
    for before, after in zip(laid.cycles, laid.cycles[1:]):
        assert before.end < after.start

    leap_anniversary = make_calendar(
        "2028-02-29",
        "2029-02-28",
        [make_component("l", CROP_A, "2028-02-29", "2029-02-28")],
    )
    assert cycle_length_years(leap_anniversary) == 2


def test_one_day_record_succeeds_and_datetime_record_end_raises_type_error() -> None:
    calendar = make_calendar(
        "2027-11-15",
        "2028-05-05",
        [make_component("c1", CROP_A, "2027-11-15", "2028-05-05")],
    )
    july_day = run_repeat(calendar, (d("2010-07-01"), d("2010-07-01")))
    assert july_day.ag_years == (2010,)
    jan_day = run_repeat(calendar, (d("2010-01-15"), d("2010-01-15")))
    assert jan_day.ag_years == (2009,)

    with pytest.raises(TypeError):
        repeat_over_record(calendar, RECORD[0], dt.datetime(2024, 12, 31))


def test_cycle_and_component_starting_on_last_day_of_record_years_are_laid_out() -> (
    None
):
    calendar = make_calendar(
        "2027-06-30",
        "2027-12-01",
        [
            make_component("a", CROP_A, "2027-06-30", "2027-12-01"),
            make_component("u", CROP_B, None, None),
        ],
    )
    laid = run_repeat(calendar)
    last_cycle = laid.cycles[-1]
    assert last_cycle.start == laid.last_day == d("2025-06-30")
    assert last_cycle.components_not_laid_out == ()
    last_items = [c for c in laid.components if c.cycle == last_cycle.index]
    assert [c.component_id for c in last_items] == ["a", "u"]
    assert last_items[0].start == laid.last_day
    assert last_items[0].ends_after_record is True


def test_cycle_and_component_ending_on_last_day_are_complete_and_not_after_record() -> (
    None
):
    calendar = make_calendar(
        "2027-07-01",
        "2028-06-30",
        [make_component("a", CROP_A, "2027-09-01", "2028-06-30")],
    )
    laid = run_repeat(calendar)
    last_cycle = laid.cycles[-1]
    assert last_cycle.end == laid.last_day == d("2025-06-30")
    assert last_cycle.complete is True
    assert laid.partial_cycle is None
    assert laid.components[-1].end == laid.last_day
    assert laid.components[-1].ends_after_record is False


# --- repeat.py: D188 part 2 lead-in boundaries (#403) -------------------------


@pytest.mark.parametrize(
    "record",
    [RECORD, RECORD_FROM_ITS_FIRST_DAY],
    ids=["D29", "from-its-first-day"],
)
def test_lead_in_component_ending_on_first_day_is_laid_out(
    record: tuple[dt.date, dt.date],
) -> None:
    calendar = make_calendar(
        "2027-07-02",
        "2028-07-01",
        [
            make_component("before", CROP_A, "2027-08-01", "2028-06-30"),
            make_component("on_first", CROP_B, "2027-09-01", "2028-07-01"),
            make_component("missing_start_before", CROP_C, None, "2028-06-30"),
            make_component("missing_start_on_first", CROP_A, None, "2028-07-01"),
            make_component("open_ended", CROP_B, None, None),
        ],
    )
    laid = run_repeat(calendar, record)
    lead = laid.cycles[0]
    assert lead.index == LEAD_IN
    assert lead.last_day == laid.first_day
    assert lead.components_not_laid_out == ("before", "missing_start_before")
    lead_items = {c.component_id: c for c in laid.components if c.cycle == LEAD_IN}
    assert sorted(lead_items) == [
        "missing_start_on_first",
        "on_first",
        "open_ended",
    ]
    assert lead_items["on_first"].end == laid.first_day
    assert lead_items["missing_start_on_first"].end == laid.first_day
    assert lead_items["open_ended"].end is None
    assert lead_items["open_ended"].cycle_last_day == laid.first_day


# --- repeat.py: leap_day_moved flags ------------------------------------------


@pytest.mark.parametrize(
    ("case_id", "comp"),
    [
        (
            "start-only",
            make_component("c", CROP_A, "2028-02-29", "2028-05-01"),
        ),
        (
            "period-start-only",
            make_component(
                "c",
                CROP_A,
                "2028-01-15",
                "2028-05-01",
                periods=[("PLACEHOLDER-p", "2028-02-29", "2028-04-01")],
            ),
        ),
        (
            "period-end-only",
            make_component(
                "c",
                CROP_A,
                "2028-01-15",
                "2028-05-01",
                periods=[("PLACEHOLDER-p", "2028-02-01", "2028-02-29")],
            ),
        ),
    ],
    ids=lambda val: val if isinstance(val, str) else None,
)
def test_leap_day_moved_reflects_start_and_period_dates(
    case_id: str,
    comp: dict[str, Any],
) -> None:
    del case_id
    calendar = make_calendar("2027-07-01", "2028-06-30", [comp])
    laid = run_repeat(calendar)
    seen_flags = set()
    for item in laid.components:
        ref = item.start if item.start.day >= 28 else item.periods[0].start
        if ref.month != 2 or ref.day < 28:
            ref = item.periods[0].end
        is_leap = gregorian.isleap(ref.year)
        assert item.leap_day_moved is (not is_leap)
        seen_flags.add(item.leap_day_moved)
    assert seen_flags == {True, False}


# --- repeat.py: phase_calendar & components_crossing_phase --------------------


def test_crossing_on_exact_phase_boundary_vs_day_before_boundary() -> None:
    on_boundary = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("x", CROP_A, "2028-05-01", "2028-07-01"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    assert components_crossing_phase(on_boundary, 1) == ["x"]
    moved = phase_calendar(on_boundary, 1)
    assert moved.start_date == d("2028-07-02")
    x_moved = {c.component_id: c for c in moved.components}["x"]
    assert (x_moved.start.date, x_moved.end.date) == (d("2030-05-01"), d("2030-07-01"))

    before_boundary = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("x", CROP_A, "2028-05-01", "2028-06-30"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    assert components_crossing_phase(before_boundary, 1) == []
    moved_before = phase_calendar(before_boundary, 1)
    assert moved_before.start_date == d("2028-07-01")


def test_multiple_crossing_components_advance_floor_to_latest_date() -> None:
    calendar = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("x_later", CROP_A, "2028-05-01", "2028-09-30"),
            make_component("x_earlier", CROP_C, "2028-06-01", "2028-08-15"),
            make_component("b", CROP_B, "2028-11-01", "2029-04-30"),
        ],
    )
    assert components_crossing_phase(calendar, 1) == ["x_later", "x_earlier"]
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2028-10-01")
    by_id = {c.component_id: c for c in moved.components}
    assert (by_id["x_later"].start.date, by_id["x_later"].end.date) == (
        d("2030-05-01"),
        d("2030-09-30"),
    )
    assert (by_id["x_earlier"].start.date, by_id["x_earlier"].end.date) == (
        d("2030-06-01"),
        d("2030-08-15"),
    )


def test_crossing_ending_on_kept_component_start_cannot_be_placed() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("x", CROP_C, "2028-05-01", "2028-10-01"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2028-10-01")
    x = {c.component_id: c for c in moved.components}["x"]
    assert x.start.date is None
    assert x.end.date is None
    assert x.start.missing.reason == CROSSING_REASON
    assert x.end.missing.reason == CROSSING_REASON


def test_crossing_ending_day_before_last_day_of_year_p_keeps_dates() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("x", CROP_C, "2028-05-01", "2029-06-29"),
            make_component("b", CROP_B, "2029-06-30", "2029-06-30"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2029-06-30")
    x = {c.component_id: c for c in moved.components}["x"]
    assert (x.start.date, x.end.date) == (d("2030-05-01"), d("2031-06-29"))


def test_not_placed_crossing_component_masks_period_dates_on_or_after_boundary() -> (
    None
):
    calendar = make_calendar(
        "2030-07-01",
        "2033-06-30",
        [
            make_component(
                "long",
                CROP_A,
                "2030-09-01",
                "2032-07-31",
                periods=[
                    ("PLACEHOLDER-before", "2030-10-01", "2031-06-30"),
                    ("PLACEHOLDER-ends-on-boundary", "2031-06-01", "2031-07-01"),
                    ("PLACEHOLDER-starts-on-boundary", "2031-07-01", "2031-08-01"),
                ],
            ),
            make_component("c", CROP_C, "2032-10-01", "2033-05-31"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    long = {c.component_id: c for c in moved.components}["long"]
    assert long.start.date is None and long.end.date is None
    p0, p1, p2 = long.periods
    assert (p0.start.date, p0.end.date) == (d("2033-10-01"), d("2034-06-30"))
    assert p1.start.date == d("2034-06-01")
    assert p1.end.date is None and p1.end.missing.reason == CROSSING_REASON
    assert p2.start.date is None and p2.start.missing.reason == CROSSING_REASON
    assert p2.end.date is None and p2.end.missing.reason == CROSSING_REASON


def test_phase_bool_false_raises_value_error() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    with pytest.raises(ValueError):
        phase_calendar(calendar, False)
    with pytest.raises(ValueError):
        components_crossing_phase(calendar, False)


def test_phase_calendar_preserves_kept_then_moved_group_order() -> None:
    calendar = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("a1", CROP_A, "2027-09-01", "2027-11-30"),
            make_component("b1", CROP_B, "2028-09-01", "2028-11-30"),
            make_component("a2", CROP_C, "2028-01-01", "2028-03-31"),
            make_component("b2", CROP_A, "2029-01-01", "2029-03-31"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    assert [c.component_id for c in moved.components] == ["b1", "b2", "a1", "a2"]
    assert repeat.list_phases(moved) == [0, 1]
