"""Mutant-killing and boundary tests for ``engine/calendar/repeat.py``.

Covers ``repeat_over_record``, ``list_phases``, ``phase_calendar`` (and
``components_crossing_phase``, ``shifted_date``, ``cycle_length_years``):
- D132 cyclic phase shifts (length-1, multi-year, wrap-around invariance);
- D141 and D188(2) lead-in boundaries crossing record and ag-year start;
- leap-year 29 February boundaries across shifting, cycles, phases, lead-in;
- undated components in repetition, lead-in, and phase shifts;
- infeasible calendar preservation and unplaceable/missing-month refusal;
- G1 purity and G5 caller-defect invariants.

All case, field, rotation, crop, component, and period identifiers and dates
are PLACEHOLDER test values.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from contracts.inputs.common import Missing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.rotation_definition.common import DateValue as DeclaredDate
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import (
    CROSSING_REASON,
    LEAD_IN,
    START_MONTH_MISSING,
    RepeatedRotation,
    components_crossing_phase,
    cycle_length_years,
    list_phases,
    phase_calendar,
    repeat_over_record,
    shifted_date,
)
from engine.calendar.rules import (
    HARVEST_NOT_BEFORE_SOWING,
    POSITIONS_NUMBER_THE_COMPONENTS,
)
from engine.calendar.test_repeat import EXAMPLE_DEFINITION

RECORD = (dt.date(2001, 1, 1), dt.date(2024, 12, 31))
ONE_DAY = dt.timedelta(days=1)
JANUARY = 1
FEBRUARY = 2
MARCH = 3
JULY = 7
DECEMBER = 12

CROP_A = "PLACEHOLDER-crop-a"
CROP_B = "PLACEHOLDER-crop-b"
CROP_C = "PLACEHOLDER-crop-c"
CROP_D = "PLACEHOLDER-crop-d"


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def dated(
    text: str | None,
    *,
    reason: str = "NOT_DECLARED",
    provenance: str = "DECLARED",
    source: str | None = "PLACEHOLDER: test calendar date",
    assumption: bool = False,
) -> dict[str, Any]:
    if text is None:
        return {
            "date": None,
            "missing": {"reason": reason, "detail": "PLACEHOLDER: missing date"},
        }
    return {
        "date": text,
        "provenance": provenance,
        "source": source,
        "assumption": assumption,
    }


def make_component(
    component_id: str,
    crop_id: str,
    start: str | None,
    end: str | None,
    periods: list[tuple[str, str | None, str | None]] | None = None,
    *,
    start_meta: dict[str, Any] | None = None,
    end_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "crop_id": crop_id,
        "start": start_meta if start_meta is not None else dated(start),
        "end": end_meta if end_meta is not None else dated(end),
        "periods": [
            {"period_type": kind, "start": dated(first), "end": dated(last)}
            for kind, first, last in periods or []
        ],
    }


def calendar_document(
    start: str,
    end: str,
    components: list[dict[str, Any]],
    *,
    month: int | None = JULY,
    feasibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ag_year_start: dict[str, Any]
    if month is None:
        ag_year_start = {
            "month": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: no month"},
        }
    else:
        ag_year_start = {
            "month": month,
            "provisional": True,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER: test start month",
            "assumption": True,
        }
    return {
        "contract": "rotation_calendar",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "ag_year_start": ag_year_start,
        "start_date": start,
        "end_date": end,
        "feasibility": feasibility or {"feasible": True, "violations": []},
        "components": components,
    }


def make_calendar(
    start: str,
    end: str,
    components: list[dict[str, Any]],
    *,
    month: int | None = JULY,
    feasibility: dict[str, Any] | None = None,
) -> RotationCalendar:
    return RotationCalendar.model_validate(
        calendar_document(start, end, components, month=month, feasibility=feasibility)
    )


def run_repeat(
    calendar: RotationCalendar,
    record: tuple[dt.date, dt.date] = RECORD,
) -> RepeatedRotation:
    result = repeat_over_record(calendar, *record)
    assert isinstance(result, RepeatedRotation)
    return result


def cycle_of(result: RepeatedRotation, index: int):
    (found,) = [c for c in result.cycles if c.index == index]
    return found


def four_year_calendar() -> RotationCalendar:
    return make_calendar(
        "2027-09-01",
        "2031-05-31",
        [
            make_component("c0", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("c1", CROP_B, "2028-10-01", "2029-04-30"),
            make_component("c2", CROP_C, "2029-09-15", "2030-03-15"),
            make_component("c3", CROP_D, "2030-11-01", "2031-05-31"),
        ],
    )


# ---------------------------------------------------------------------------
# 1. D132 cyclic phase shifts: length-1, multi-year, wrap-around invariance
# ---------------------------------------------------------------------------


def test_length_one_rotations_have_single_phase_zero_and_reject_phase_one() -> None:
    single_day = make_calendar(
        "2027-11-15",
        "2027-11-15",
        [make_component("d1", CROP_A, "2027-11-15", "2027-11-15")],
    )
    day_before_anniversary = make_calendar(
        "2027-07-01",
        "2028-06-30",
        [make_component("y1", CROP_A, "2027-09-01", "2028-05-01")],
    )
    for cal in (single_day, day_before_anniversary):
        assert cycle_length_years(cal) == 1
        assert list_phases(cal) == [0]
        assert components_crossing_phase(cal, 0) == []
        moved0 = phase_calendar(cal, 0)
        assert moved0 == cal and moved0 is not cal
        assert repeat_over_record(moved0, *RECORD) == repeat_over_record(cal, *RECORD)
        for bad in (-1, 1):
            with pytest.raises(ValueError):
                phase_calendar(cal, bad)
            with pytest.raises(ValueError):
                components_crossing_phase(cal, bad)


def test_four_year_rotation_phases_and_metadata_preservation() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2031-05-31",
        [
            make_component(
                "c0",
                CROP_A,
                "2027-09-01",
                "2028-03-31",
                start_meta=dated(
                    "2027-09-01",
                    provenance="DERIVED",
                    source="PLACEHOLDER: derived sowing",
                    assumption=True,
                ),
            ),
            make_component("c1", CROP_B, "2028-10-01", "2029-04-30"),
            make_component("c2", CROP_C, "2029-08-15", "2030-03-15"),
            make_component("c3", CROP_D, "2030-11-01", "2031-05-31"),
        ],
    )
    assert list_phases(calendar) == [0, 1, 2, 3]
    expected_starts = {
        0: d("2027-09-01"),
        1: d("2028-09-01"),
        2: d("2029-08-15"),  # kept c2 starts earlier than 2029-09-01 floor
        3: d("2030-09-01"),
    }
    for phase in range(4):
        moved = phase_calendar(calendar, phase)
        assert cycle_length_years(moved) == 4
        assert list_phases(moved) == [0, 1, 2, 3]
        expected_ids = [f"c{i}" for i in range(phase, 4)] + [
            f"c{i}" for i in range(phase)
        ]
        assert [c.component_id for c in moved.components] == expected_ids
        assert moved.start_date == expected_starts[phase]
        laid = run_repeat(moved)
        first_cycle_items = [c for c in laid.components if c.cycle == 0]
        assert [c.component_id for c in first_cycle_items] == expected_ids
        assert first_cycle_items[0].start.year == 2000
        assert laid.ag_years[0] == 2000
        # Moved component keeps provenance, source, and assumption mark (OPEN point 10).
        c0 = {c.component_id: c for c in moved.components}["c0"]
        assert c0.start.provenance == "DERIVED"
        assert c0.start.source == "PLACEHOLDER: derived sowing"
        assert c0.start.assumption is True


def test_phase_calendar_with_fallow_middle_year_keeps_cycle_length_and_start() -> None:
    # 3-year rotation where year 1 has no components; year 2 has c2.
    calendar = make_calendar(
        "2027-07-01",
        "2030-06-30",
        [
            make_component("c0", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("c2", CROP_C, "2029-09-01", "2030-03-31"),
        ],
    )
    assert list_phases(calendar) == [0, 1, 2]
    p1 = phase_calendar(calendar, 1)
    assert [c.component_id for c in p1.components] == ["c2", "c0"]
    assert p1.start_date == d("2028-07-01")
    assert p1.end_date == d("2031-03-31")
    assert cycle_length_years(p1) == 3

    p2 = phase_calendar(calendar, 2)
    assert [c.component_id for c in p2.components] == ["c2", "c0"]
    assert p2.start_date == d("2029-07-01")
    # Placed dates end at 2031-03-31, earlier than start + 2 years (2031-07-01),
    # so end_date is set to 2031-07-01 to preserve the 3-year cycle (point 12).
    assert p2.end_date == d("2031-07-01")
    assert cycle_length_years(p2) == 3


def test_phase_start_uses_min_of_floor_and_kept_component_start() -> None:
    # Calendar starts 2027-11-15, so floor for phase 1 is 2028-11-15.
    # Kept component b starts 2028-08-01 (< floor), so moved.start_date must drop to 2028-08-01.
    calendar = make_calendar(
        "2027-11-15",
        "2029-05-31",
        [
            make_component("a", CROP_A, "2027-11-15", "2028-04-01"),
            make_component("b", CROP_B, "2028-08-01", "2029-03-01"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2028-08-01")
    assert cycle_length_years(moved) == 2


def test_crossing_ending_before_floor_does_not_pull_start_date_backward() -> None:
    # Calendar starts 2027-11-15, so floor for phase 1 is 2028-11-15.
    # Crossing x ends 2028-09-30: max(crossing)+1 = 2028-10-01 < floor, so
    # start_date stays at 2028-11-15 (kills dropping max(floor, ...)).
    calendar = make_calendar(
        "2027-11-15",
        "2029-05-31",
        [
            make_component("a", CROP_A, "2027-11-15", "2028-03-31"),
            make_component("x", CROP_C, "2028-05-01", "2028-09-30"),
            make_component("b", CROP_B, "2028-12-01", "2029-05-31"),
        ],
    )
    assert components_crossing_phase(calendar, 1) == ["x"]
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2028-11-15")
    x = {c.component_id: c for c in moved.components}["x"]
    assert (x.start.date, x.end.date) == (d("2030-05-01"), d("2030-09-30"))


def test_crossing_order_independence_and_period_boundary_vs_kept_start() -> None:
    # Two crossing components listed earlier-then-later still advance floor to latest.
    cal = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("x1", CROP_A, "2028-06-01", "2028-08-15"),
            make_component("x2", CROP_C, "2028-05-01", "2028-09-30"),
            make_component("b", CROP_B, "2028-11-01", "2029-04-30"),
        ],
    )
    moved = phase_calendar(cal, 1)
    assert moved.start_date == d("2028-10-01")

    # Component whose period ends on kept component's start cannot lie whole in one cycle;
    # ending one day earlier keeps its dates.
    period_on_kept = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component(
                "x",
                CROP_C,
                "2028-05-01",
                None,
                periods=[("PLACEHOLDER-p", "2028-06-15", "2028-10-01")],
            ),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    moved_bad = phase_calendar(period_on_kept, 1)
    x_bad = {c.component_id: c for c in moved_bad.components}["x"]
    assert x_bad.start.date is None and x_bad.end.date is None
    assert x_bad.start.missing.reason == CROSSING_REASON
    assert x_bad.periods[0].start.date == d("2030-06-15")
    assert x_bad.periods[0].end.date is None
    assert x_bad.periods[0].end.missing.reason == CROSSING_REASON

    period_before_kept = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component(
                "x",
                CROP_C,
                "2028-05-01",
                None,
                periods=[("PLACEHOLDER-p", "2028-06-15", "2028-09-30")],
            ),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    moved_ok = phase_calendar(period_before_kept, 1)
    x_ok = {c.component_id: c for c in moved_ok.components}["x"]
    assert x_ok.start.date == d("2030-05-01")
    assert x_ok.end.date is None and x_ok.end.missing.reason == "NOT_DECLARED"
    assert (x_ok.periods[0].start.date, x_ok.periods[0].end.date) == (
        d("2030-06-15"),
        d("2030-09-30"),
    )


def _strip_shift_years(
    repeated: RepeatedRotation,
    *,
    include_calendar_end: bool = True,
) -> tuple[Any, ...]:
    """Everything in ``RepeatedRotation`` except cycle ``shift_years`` (and
    optionally ``calendar_end`` when a calendar's declared ``end_date`` padded
    past its last component)."""
    return (
        repeated.start_month,
        repeated.record_start,
        repeated.record_end,
        repeated.cycle_length,
        repeated.ag_years,
        repeated.first_day,
        repeated.last_day,
        repeated.described_from,
        tuple(
            (
                c.index,
                c.start,
                c.end if include_calendar_end else None,
                c.last_day,
                c.complete,
                c.components_not_laid_out,
            )
            for c in repeated.cycles
        ),
        tuple(
            (
                item.component_id,
                item.crop_id,
                item.cycle,
                item.start,
                item.end,
                item.calendar_start,
                item.calendar_end if include_calendar_end else None,
                item.cycle_last_day,
                item.periods,
                item.leap_day_moved,
                item.ends_after_record,
            )
            for item in repeated.components
        ),
    )


def test_wrap_around_invariance_across_single_steps_and_compositions() -> None:
    one_year_cal = make_calendar(
        "2027-09-01",
        "2028-05-31",
        [make_component("c0", CROP_A, "2027-09-01", "2028-05-31")],
    )
    assert phase_calendar(one_year_cal, 0) == one_year_cal
    assert run_repeat(phase_calendar(one_year_cal, 0)) == run_repeat(one_year_cal)

    tight_two_year = make_calendar(
        "2027-09-01",
        "2029-04-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("x", CROP_C, "2028-05-01", "2028-09-30"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    padded_two_year = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("x", CROP_C, "2028-05-01", "2028-09-30"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )

    for calendar, tight in (
        (tight_two_year, True),
        (padded_two_year, False),
        (four_year_calendar(), True),
    ):
        length = cycle_length_years(calendar)
        stepped = calendar
        for _ in range(length):
            stepped = phase_calendar(stepped, 1)
        assert [c.component_id for c in stepped.components] == [
            c.component_id for c in calendar.components
        ]
        assert stepped.start_date == shifted_date(calendar.start_date, length)[0]
        assert _strip_shift_years(
            run_repeat(stepped), include_calendar_end=tight
        ) == _strip_shift_years(run_repeat(calendar), include_calendar_end=tight)

    # Composition: phase_calendar(phase_calendar(cal, 1), 1) == phase_calendar(cal, 2)
    cal4 = four_year_calendar()
    assert phase_calendar(phase_calendar(cal4, 1), 1) == phase_calendar(cal4, 2)
    assert phase_calendar(phase_calendar(cal4, 1), 2) == phase_calendar(cal4, 3)
    # Wrapping past N: phase 3 followed by phase 2 matches phase 1 shifted by +4 years.
    wrapped = phase_calendar(phase_calendar(cal4, 3), 2)
    direct = phase_calendar(cal4, 1)
    assert [c.component_id for c in wrapped.components] == [
        c.component_id for c in direct.components
    ]
    assert wrapped.start_date == shifted_date(direct.start_date, 4)[0]
    assert _strip_shift_years(run_repeat(wrapped)) == _strip_shift_years(
        run_repeat(direct)
    )


def test_calendar_dated_before_record_gives_identical_schedule_to_after_record() -> (
    None
):
    future = four_year_calendar()
    past_shift = -40
    past = make_calendar(
        shifted_date(future.start_date, past_shift)[0].isoformat(),
        shifted_date(future.end_date, past_shift)[0].isoformat(),
        [
            make_component(
                c.component_id,
                c.crop_id,
                shifted_date(c.start.date, past_shift)[0].isoformat(),
                shifted_date(c.end.date, past_shift)[0].isoformat(),
            )
            for c in future.components
        ],
    )
    for phase in list_phases(future):
        assert _strip_shift_years(
            run_repeat(phase_calendar(past, phase))
        ) == _strip_shift_years(run_repeat(phase_calendar(future, phase)))


# ---------------------------------------------------------------------------
# 2. D141 & D188(2) lead-in crossing record start and ag-year boundaries
# ---------------------------------------------------------------------------


def test_lead_in_exact_first_day_boundaries_with_crossing_and_non_crossing() -> None:
    record = (d("2001-01-01"), d("2003-12-31"))  # July start -> first_day = 2000-07-01
    # Calendar starts 2027-07-03 and ends 2028-07-02 (cycle_length = 1).
    calendar = make_calendar(
        "2027-07-03",
        "2028-07-02",
        [
            make_component("day_before", CROP_A, "2027-09-01", "2028-06-30"),
            make_component("on_first_day", CROP_B, "2028-05-01", "2028-07-01"),
            make_component("after_first_day", CROP_C, "2028-05-15", "2028-07-02"),
        ],
    )
    laid = run_repeat(calendar, record)
    assert laid.first_day == d("2000-07-01")
    lead = cycle_of(laid, LEAD_IN)
    assert lead.last_day == d("2000-07-02")
    assert lead.components_not_laid_out == ("day_before",)
    lead_items = [c for c in laid.components if c.cycle == LEAD_IN]
    assert [(c.component_id, c.start, c.end) for c in lead_items] == [
        ("on_first_day", d("2000-05-01"), d("2000-07-01")),
        ("after_first_day", d("2000-05-15"), d("2000-07-02")),
    ]
    assert laid.described_from == lead.start < laid.first_day

    # Exact boundary: lead.last_day == laid.first_day when cycle 0 starts on 2 July.
    exact_boundary = make_calendar(
        "2027-07-02",
        "2028-07-01",
        [
            make_component("day_before", CROP_A, "2027-09-01", "2028-06-30"),
            make_component("on_first_day", CROP_B, "2028-05-01", "2028-07-01"),
        ],
    )
    laid_exact = run_repeat(exact_boundary, record)
    lead_exact = cycle_of(laid_exact, LEAD_IN)
    assert lead_exact.last_day == laid_exact.first_day
    assert lead_exact.components_not_laid_out == ("day_before",)
    assert [
        (c.component_id, c.start, c.end)
        for c in laid_exact.components
        if c.cycle == LEAD_IN
    ] == [("on_first_day", d("2000-05-01"), d("2000-07-01"))]


def test_lead_in_absent_when_first_cycle_starts_on_first_day_and_present_one_day_later() -> (
    None
):
    record = (d("2001-03-15"), d("2003-10-10"))
    on_first = make_calendar(
        "2027-07-01",
        "2028-06-30",
        [make_component("a", CROP_A, "2027-09-01", "2028-03-31")],
    )
    laid_on = run_repeat(on_first, record)
    assert laid_on.cycles[0].index == 0
    assert laid_on.described_from == laid_on.first_day == d("2000-07-01")

    on_second = make_calendar(
        "2027-07-02",
        "2028-06-30",
        [make_component("a", CROP_A, "2027-09-01", "2028-03-31")],
    )
    laid_second = run_repeat(on_second, record)
    assert laid_second.cycles[0].index == LEAD_IN
    assert laid_second.cycles[0].last_day == laid_second.first_day
    assert laid_second.described_from == laid_second.cycles[0].start < laid_second.first_day


def test_lead_in_crosses_record_start_when_start_month_is_january_and_december() -> (
    None
):
    # January start: first_day == record_start == 2001-01-01.
    jan_cal = make_calendar(
        "2027-11-15",
        "2029-06-01",
        [
            make_component("winter", CROP_A, "2027-11-15", "2028-05-05"),
            make_component("summer", CROP_B, "2028-11-15", "2029-05-05"),
        ],
        month=JANUARY,
    )
    p1_jan = phase_calendar(jan_cal, 1)
    laid_jan = run_repeat(p1_jan, (d("2001-01-01"), d("2004-12-31")))
    (lead_jan,) = [c for c in laid_jan.components if c.cycle == LEAD_IN]
    assert (lead_jan.component_id, lead_jan.start, lead_jan.end) == (
        "winter",
        d("2000-11-15"),
        d("2001-05-05"),
    )
    assert lead_jan.start < laid_jan.record_start <= lead_jan.end

    # December start with record starting in January -> first_ag_year = 2000, first_day = 2000-12-01.
    dec_cal = make_calendar(
        "2027-12-10",
        "2028-11-30",
        [make_component("w", CROP_A, "2027-12-10", "2028-04-15")],
        month=DECEMBER,
    )
    laid_dec = run_repeat(dec_cal, (d("2001-01-15"), d("2002-11-30")))
    assert laid_dec.ag_years == (2000, 2001)
    assert laid_dec.first_day == d("2000-12-01")
    assert laid_dec.last_day == d("2002-11-30")
    assert laid_dec.cycles[0].index == LEAD_IN


def test_short_record_lead_in_complete_flag_and_ends_after_record() -> None:
    # A 1-year record (2010-07-01..2011-06-30) with a 3-year calendar:
    # lead-in always ends before cycle 0 starts (<= last_day), so lead.complete is True
    # and lead-in components never end after last_day, while cycle 0 is partial.
    record = (d("2010-07-01"), d("2011-06-30"))
    long_lead = make_calendar(
        "2027-08-01",
        "2030-07-15",
        [
            make_component("a", CROP_A, "2027-08-01", "2028-03-31"),
            make_component("b", CROP_B, "2028-10-01", "2029-06-30"),
            make_component("c", CROP_C, "2029-10-01", "2030-07-15"),
        ],
    )
    laid = run_repeat(long_lead, record)
    lead, cycle0 = laid.cycles
    assert lead.index == LEAD_IN
    assert lead.end == d("2010-07-15") < cycle0.start <= laid.last_day
    assert lead.complete is True
    assert cycle0.index == 0 and cycle0.complete is False
    assert cycle0.components_not_laid_out == ("b", "c")
    assert laid.partial_cycle is cycle0
    (lead_c,) = [c for c in laid.components if c.cycle == LEAD_IN]
    assert lead_c.component_id == "c"
    assert lead_c.end == d("2010-07-15")
    assert lead_c.ends_after_record is False


def test_ag_year_month_cut_with_february_start_and_month_boundary_dates() -> None:
    calendar = make_calendar(
        "2027-03-01",
        "2028-01-31",
        [make_component("c", CROP_A, "2027-03-01", "2028-01-31")],
        month=FEBRUARY,
    )
    # record_start on leap day 2020-02-29, record_end 2021-01-31 -> both in ag year 2020.
    laid = run_repeat(calendar, (d("2020-02-29"), d("2021-01-31")))
    assert laid.ag_years == (2020,)
    assert laid.first_day == d("2020-02-01")
    assert laid.last_day == d("2021-01-31")

    # One day later on record_end enters ag year 2021; record_start on Jan 31 enters ag year 2020.
    laid2 = run_repeat(calendar, (d("2021-01-31"), d("2021-02-01")))
    assert laid2.ag_years == (2020, 2021)
    assert laid2.first_day == d("2020-02-01")
    assert laid2.last_day == d("2022-01-31")


def test_cycle_and_component_exact_last_day_boundaries() -> None:
    # Cycle ending on last_day vs last_day + 1 day.
    exact = make_calendar(
        "2027-07-01",
        "2028-06-30",
        [make_component("a", CROP_A, "2027-09-01", "2028-06-30")],
    )
    laid_exact = run_repeat(exact, (d("2001-07-01"), d("2002-06-30")))
    assert laid_exact.cycles[-1].complete is True
    assert laid_exact.partial_cycle is None
    assert laid_exact.components[-1].ends_after_record is False

    one_over = make_calendar(
        "2027-07-01",
        "2028-07-01",
        [make_component("a", CROP_A, "2027-09-01", "2028-07-01")],
    )
    laid_over = run_repeat(one_over, (d("2001-07-01"), d("2002-06-30")))
    # Cycle 0 runs 2001-07-01..2002-07-01 (> last_day=2002-06-30); cycle 1 would start 2003-07-01 > last_day.
    assert len(laid_over.cycles) == 1
    assert laid_over.cycles[0].complete is False
    assert laid_over.partial_cycle is laid_over.cycles[0]
    assert laid_over.components[0].ends_after_record is True


# ---------------------------------------------------------------------------
# 3. Leap-year Feb-29 boundaries
# ---------------------------------------------------------------------------


def test_shifted_date_leap_century_negative_and_non_leap_boundaries() -> None:
    assert shifted_date(d("2028-02-29"), 0) == (d("2028-02-29"), False)
    assert shifted_date(d("2028-02-29"), 1) == (d("2029-02-28"), True)
    assert shifted_date(d("2028-02-29"), 4) == (d("2032-02-29"), False)
    assert shifted_date(d("2028-02-29"), -1) == (d("2027-02-28"), True)
    assert shifted_date(d("2028-02-29"), -4) == (d("2024-02-29"), False)
    assert shifted_date(d("2028-02-29"), 72) == (d("2100-02-28"), True)  # non-leap century
    assert shifted_date(d("2028-02-29"), -28) == (d("2000-02-29"), False)  # leap century
    assert shifted_date(d("2027-02-28"), 1) == (d("2028-02-28"), False)


def test_cycle_length_years_feb_29_boundaries() -> None:
    assert (
        cycle_length_years(
            make_calendar(
                "2028-02-29",
                "2029-02-27",
                [make_component("a", CROP_A, "2028-02-29", "2029-02-27")],
            )
        )
        == 1
    )
    assert (
        cycle_length_years(
            make_calendar(
                "2028-02-29",
                "2029-02-28",
                [make_component("a", CROP_A, "2028-02-29", "2029-02-28")],
            )
        )
        == 2
    )
    assert (
        cycle_length_years(
            make_calendar(
                "2028-02-29",
                "2032-02-28",
                [make_component("a", CROP_A, "2028-02-29", "2032-02-28")],
            )
        )
        == 4
    )
    assert (
        cycle_length_years(
            make_calendar(
                "2028-02-29",
                "2032-02-29",
                [make_component("a", CROP_A, "2028-02-29", "2032-02-29")],
            )
        )
        == 5
    )


def test_calendar_starting_on_feb_29_repeats_with_lead_in_and_leap_cycle_starts() -> (
    None
):
    calendar = make_calendar(
        "2028-02-29",
        "2028-11-30",
        [make_component("c", CROP_A, "2028-02-29", "2028-11-30")],
        month=FEBRUARY,
    )
    laid = run_repeat(calendar, (d("2000-02-01"), d("2005-01-31")))
    # Lead-in shifts 2028 -> 1999 (non-leap: 1999-02-28..1999-11-30, ends < 2000-02-01).
    lead = laid.cycles[0]
    assert lead.index == LEAD_IN
    assert lead.start == d("1999-02-28")
    assert lead.last_day == d("2000-02-28")
    assert lead.components_not_laid_out == ("c",)

    cycles = laid.cycles[1:]
    assert [c.start for c in cycles] == [
        d("2000-02-29"),
        d("2001-02-28"),
        d("2002-02-28"),
        d("2003-02-28"),
        d("2004-02-29"),
    ]
    assert [c.last_day for c in cycles] == [
        d("2001-02-27"),
        d("2002-02-27"),
        d("2003-02-27"),
        d("2004-02-28"),
        d("2005-02-27"),
    ]


@pytest.mark.parametrize(
    ("case_id", "comp"),
    [
        ("end-only", make_component("c", CROP_A, "2028-01-15", "2028-02-29")),
        ("start-only-open-end", make_component("c", CROP_A, "2028-02-29", None)),
        ("open-start-leap-end", make_component("c", CROP_A, None, "2028-02-29")),
        (
            "second-period-only",
            make_component(
                "c",
                CROP_A,
                "2028-01-10",
                "2028-05-01",
                periods=[
                    ("PLACEHOLDER-p1", "2028-01-15", "2028-02-15"),
                    ("PLACEHOLDER-p2", "2028-02-20", "2028-02-29"),
                ],
            ),
        ),
        (
            "undated-with-leap-period",
            make_component(
                "c",
                CROP_A,
                None,
                None,
                periods=[("PLACEHOLDER-p", "2028-02-29", "2028-03-15")],
            ),
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_leap_day_moved_flag_across_all_date_positions(
    case_id: str, comp: dict[str, Any]
) -> None:
    del case_id
    calendar = make_calendar("2027-07-01", "2028-06-30", [comp])
    laid = run_repeat(calendar, (d("2003-07-01"), d("2005-06-30")))
    # ag years 2003 (Feb 2004 leap) and 2004 (Feb 2005 non-leap)
    by_year = {cycle_of(laid, item.cycle).start.year: item for item in laid.components}
    assert by_year[2003].leap_day_moved is False
    assert by_year[2004].leap_day_moved is True


def test_phase_calendar_with_feb_29_start_and_moved_dates() -> None:
    calendar = make_calendar(
        "2028-02-29",
        "2029-06-30",
        [
            make_component(
                "a",
                CROP_A,
                "2028-02-29",
                "2028-06-15",
                periods=[("PLACEHOLDER-p", "2028-02-29", "2028-04-01")],
            ),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    assert list_phases(calendar) == [0, 1]
    moved = phase_calendar(calendar, 1)
    assert moved.start_date == d("2028-10-01")
    a = {c.component_id: c for c in moved.components}["a"]
    assert a.start.date == d("2030-02-28")
    assert a.periods[0].start.date == d("2030-02-28")
    assert a.start.provenance == "DECLARED"
    assert a.start.source == "PLACEHOLDER: test calendar date"
    # Per OPEN point 10, repeat_over_record on the moved calendar keeps Feb 28 even in leap years.
    laid = run_repeat(moved, (d("2003-07-01"), d("2005-06-30")))
    a_items = [c for c in laid.components if c.component_id == "a"]
    assert all(item.start.day == 28 and item.leap_day_moved is False for item in a_items)

    # When kept component starts after shifted_date(2028-02-29, 1) = 2029-02-28,
    # moved.start_date is 2029-02-28 (Feb 29 start_date shifted into non-leap year).
    no_early_kept = make_calendar(
        "2028-02-29",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2028-02-29", "2028-06-15"),
            make_component("b", CROP_B, "2029-03-15", "2029-06-30"),
        ],
    )
    moved2 = phase_calendar(no_early_kept, 1)
    assert moved2.start_date == d("2029-02-28")
    assert cycle_length_years(moved2) == 2


# ---------------------------------------------------------------------------
# 4. Undated components in repetition, lead-in, and phase_calendar
# ---------------------------------------------------------------------------


def test_undated_and_half_dated_components_across_lead_in_and_partial_cycle() -> None:
    calendar = make_calendar(
        "2027-07-02",
        "2029-07-01",
        [
            make_component("both_none", CROP_A, None, None),
            make_component("open_end_y0", CROP_B, "2027-09-01", None),
            make_component("open_end_y1", CROP_C, "2028-10-01", None),
            make_component("open_start_before_first", CROP_A, None, "2029-06-30"),
            make_component("open_start_on_first", CROP_B, None, "2029-07-01"),
        ],
    )
    # Record 2001-07-01..2004-06-30 (3 ag years: 2001, 2002, 2003).
    # Cycle 0 spans ag years 2001-2002 (2001-07-02..2003-07-01); lead-in shift is -28.
    # Cycle 1 starts 2003-07-02 (partial, ag year 2003 only; open_end_y1 starts 2004-10-01 > last_day).
    laid = run_repeat(calendar, (d("2001-07-01"), d("2004-06-30")))
    lead = cycle_of(laid, LEAD_IN)
    assert lead.components_not_laid_out == ("open_start_before_first",)
    lead_ids = [c.component_id for c in laid.components if c.cycle == LEAD_IN]
    assert lead_ids == [
        "both_none",
        "open_end_y0",
        "open_end_y1",
        "open_start_on_first",
    ]
    for item in laid.components:
        if item.component_id in {"both_none", "open_end_y0", "open_end_y1"}:
            assert item.end is None
            assert item.ends_after_record is False
    partial = laid.partial_cycle
    assert partial is not None and partial.index == 1
    assert partial.components_not_laid_out == ("open_end_y1",)
    partial_ids = [c.component_id for c in laid.components if c.cycle == partial.index]
    assert partial_ids == [
        "both_none",
        "open_end_y0",
        "open_start_before_first",
        "open_start_on_first",
    ]
    open_start_in_partial = [
        c
        for c in laid.components
        if c.cycle == partial.index and c.component_id == "open_start_on_first"
    ][0]
    assert open_start_in_partial.end == d("2005-07-01")
    assert open_start_in_partial.ends_after_record is True


def test_phase_calendar_undated_start_assigns_year_by_end_date() -> None:
    calendar = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component("u_none", CROP_C, None, None),
            make_component("y0_open_start", CROP_A, None, "2028-03-31"),
            make_component("y1_open_start", CROP_B, None, "2028-08-15"),
            make_component("y1_kept", CROP_A, "2028-10-01", "2029-04-30"),
        ],
    )
    assert components_crossing_phase(calendar, 1) == []
    moved = phase_calendar(calendar, 1)
    # Kept group (u_none, y1_open_start, y1_kept) comes before moved group (y0_open_start).
    assert [c.component_id for c in moved.components] == [
        "u_none",
        "y1_open_start",
        "y1_kept",
        "y0_open_start",
    ]
    by_id = {c.component_id: c for c in moved.components}
    assert by_id["u_none"].start.date is None and by_id["u_none"].end.date is None
    assert by_id["y0_open_start"].start.date is None
    assert by_id["y0_open_start"].end.date == d("2030-03-31")
    assert by_id["y1_open_start"].start.date is None
    assert by_id["y1_open_start"].end.date == d("2028-08-15")


def test_not_placed_crossing_preserves_missing_period_reason_and_masks_both_ends() -> (
    None
):
    calendar = make_calendar(
        "2027-07-01",
        "2029-06-30",
        [
            make_component(
                "x",
                CROP_A,
                "2028-05-01",
                None,
                periods=[
                    ("PLACEHOLDER-before-with-gap", "2028-05-10", None),
                    ("PLACEHOLDER-crosses", "2028-06-15", "2028-11-01"),
                ],
            ),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
    )
    moved = phase_calendar(calendar, 1)
    x = {c.component_id: c for c in moved.components}["x"]
    for edge in (x.start, x.end):
        assert edge.date is None
        assert edge.missing.reason == CROSSING_REASON
        assert "D141" in edge.missing.detail
        assert "phase 1" in edge.missing.detail
        assert "'x'" in edge.missing.detail
        assert edge.provenance is None
        assert edge.source is None
        assert edge.assumption is False
    p0, p1 = x.periods
    assert p0.start.date == d("2030-05-10")
    assert p0.end.date is None and p0.end.missing.reason == "NOT_DECLARED"
    assert p1.start.date == d("2030-06-15")
    assert p1.end.date is None and p1.end.missing.reason == CROSSING_REASON


# ---------------------------------------------------------------------------
# 5. Infeasible calendar handling & refusal / missing-month paths
# ---------------------------------------------------------------------------


def test_infeasible_calendar_is_preserved_through_phases_and_repeated_without_refusal() -> (
    None
):
    # Built through EP2 (build_rotation_calendar) so feasibility is False with both rules.
    definition = RotationDefinition.model_validate(
        json.loads(EXAMPLE_DEFINITION.read_text(encoding="utf-8"))
    )
    first = definition.components[0]
    first.harvest = DeclaredDate(
        date=first.sowing.date - ONE_DAY,
        provenance="DECLARED",
        source="PLACEHOLDER: bad harvest",
    )
    definition.components[1].position = first.position
    infeasible = build_rotation_calendar(definition)
    assert infeasible.feasibility.feasible is False
    assert [v.rule for v in infeasible.feasibility.violations] == [
        HARVEST_NOT_BEFORE_SOWING,
        POSITIONS_NUMBER_THE_COMPONENTS,
    ]

    # repeat.py does not read feasibility; list_phases, phase_calendar, repeat_over_record run.
    phases = list_phases(infeasible)
    assert len(phases) >= 1
    laid = run_repeat(infeasible)
    # First component has both dates missing (NOT_COMPUTABLE) so it is laid out in every cycle.
    c0_laid = [
        c for c in laid.components if c.component_id == first.component_id
    ]
    assert len(c0_laid) == len(laid.cycles)
    assert all(c.start is None and c.end is None for c in c0_laid)

    # Also test a multi-year infeasible calendar through phase_calendar(cal, 1).
    multi_infeasible = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
        feasibility={
            "feasible": False,
            "violations": [
                {
                    "rule": "PLACEHOLDER_RULE",
                    "component_ids": ["a"],
                    "detail": "PLACEHOLDER violation",
                }
            ],
        },
    )
    assert list_phases(multi_infeasible) == [0, 1]
    moved = phase_calendar(multi_infeasible, 1)
    assert moved.feasibility == multi_infeasible.feasibility
    assert moved.feasibility.feasible is False
    assert [v.component_ids for v in moved.feasibility.violations] == [["a"]]


def test_missing_start_month_behaviour_across_repeat_list_and_phase() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2029-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("b", CROP_B, "2028-10-01", "2029-04-30"),
        ],
        month=None,
    )
    res = repeat_over_record(calendar, *RECORD)
    assert isinstance(res, Missing)
    assert res.reason == "MISSING_INPUT"
    assert res.detail == START_MONTH_MISSING

    assert list_phases(calendar) == [0, 1]
    assert phase_calendar(calendar, 0) == calendar
    assert components_crossing_phase(calendar, 0) == []
    with pytest.raises(ValueError, match="D132"):
        phase_calendar(calendar, 1)
    with pytest.raises(ValueError, match="D132"):
        components_crossing_phase(calendar, 1)


# ---------------------------------------------------------------------------
# 6. G1 purity and G5 caller-defect invariants
# ---------------------------------------------------------------------------


def test_g1_purity_immutability_and_isolation() -> None:
    calendar = make_calendar(
        "2027-09-01",
        "2030-06-30",
        [
            make_component("a", CROP_A, "2027-09-01", "2028-03-31"),
            make_component("long", CROP_B, "2028-05-01", "2029-08-01"),
            make_component("c", CROP_C, "2029-10-01", "2030-06-30"),
        ],
    )
    snapshot = calendar.model_dump_json()

    assert list_phases(calendar) == [0, 1, 2]
    assert calendar.model_dump_json() == snapshot

    for phase in (0, 1, 2):
        components_crossing_phase(calendar, phase)
        moved = phase_calendar(calendar, phase)
        assert calendar.model_dump_json() == snapshot
        assert moved == phase_calendar(copy.deepcopy(calendar), phase)
        assert moved is not calendar
        moved.components[0].start.source = "mutated by test"
        moved.ag_year_start.source = "mutated by test"
        moved.components.clear()
        assert calendar.model_dump_json() == snapshot

    repeated = run_repeat(calendar)
    assert calendar.model_dump_json() == snapshot
    assert repeated == run_repeat(copy.deepcopy(calendar))
    with pytest.raises(FrozenInstanceError):
        repeated.cycle_length = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        repeated.cycles[0].complete = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        repeated.components[0].leap_day_moved = True  # type: ignore[misc]


def test_g5_caller_defects_raise_type_error_or_value_error() -> None:
    calendar = four_year_calendar()
    raw_doc = calendar_document(
        "2027-09-01",
        "2028-05-31",
        [make_component("a", CROP_A, "2027-09-01", "2028-05-31")],
    )

    class DateSubclass(dt.date):
        pass

    for bad_cal in (
        raw_doc,
        None,
        "2027-09-01",
        RotationCalendar,
        calendar.components[0],
    ):
        with pytest.raises(TypeError):
            list_phases(bad_cal)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            phase_calendar(bad_cal, 0)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            components_crossing_phase(bad_cal, 0)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            repeat_over_record(bad_cal, *RECORD)  # type: ignore[arg-type]

    for bad_date in (
        "2001-01-01",
        None,
        20010101,
        dt.datetime(2001, 1, 1),
        DateSubclass(2001, 1, 1),
    ):
        with pytest.raises(TypeError):
            repeat_over_record(calendar, bad_date, RECORD[1])  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            repeat_over_record(calendar, RECORD[0], bad_date)  # type: ignore[arg-type]

    # Reversed by 1 day raises ValueError; 1-day record succeeds.
    with pytest.raises(ValueError):
        repeat_over_record(calendar, d("2010-07-02"), d("2010-07-01"))
    one_day = run_repeat(calendar, (d("2010-07-01"), d("2010-07-01")))
    assert one_day.ag_years == (2010,)

    for bad_p in (-1, 4, 5, True, False, 0.0, 1.0, "0", None):
        with pytest.raises(ValueError):
            phase_calendar(calendar, bad_p)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            components_crossing_phase(calendar, bad_p)  # type: ignore[arg-type]
