"""Targeted mutant-killing tests for EP3 and its water helpers.

Covers surviving boundary, missing-propagation, stage-tail, fallow,
parameter-lookup, and ``live_crop_by_day`` mutants across:
- ``engine/water/exposure.py``
- ``engine/water/living_crop.py``
- ``engine/water/stages.py``
- ``engine/water/fallow.py``
- ``engine/water/_parameters.py``

Every number, date, and parameter record here is PLACEHOLDER test data,
plainly not real: nothing comes from a source and no method value is
invented.
"""

from __future__ import annotations

import copy
import datetime as dt
import itertools
import json
import math

import pytest

from contracts.inputs.common import DateValue
from contracts.inputs.rotation_calendar import CalendarComponent, RotationCalendar
from contracts.results.models import Missing
from engine.calendar.repeat import Cycle, RepeatedComponent, RepeatedRotation
from engine.water import _parameters, fallow, living_crop, stages
from engine.water import exposure as ep3
from engine.water import test_exposure as ep3_tests

ONE_DAY = dt.timedelta(days=1)


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


# --- engine/water/exposure.py -------------------------------------------------


def test_late_non_precipitation_series_leaves_later_covered_years_computed():
    # Kills _chain_days using record.start_date instead of max(start_date)
    # across present daily series: when wind_speed_2m starts one day after
    # precipitation, year 0 is NO_COVERAGE, and years 1+ must still compute
    # without year 0's missing wind day poisoning storage/depletion.
    first, last = ep3_tests.several_full_years()
    series = [
        ep3_tests.daily_series(
            name,
            first + ONE_DAY if name == "wind_speed_2m" else first,
            last,
        )
        for name in ep3_tests.DAILY_INPUTS
    ]
    result = ep3_tests.run(
        calendar_=ep3_tests.chain_calendar(),
        climate_=ep3_tests.climate_with(series),
    )
    first_year, *later_years = result
    assert first_year.missing is not None
    assert first_year.missing.reason == "NO_COVERAGE"
    assert "'wind_speed_2m'" in first_year.missing.detail
    for item in later_years:
        ep3_tests.assert_computed(item)


def test_missing_point_value_with_unaccepted_unit_reports_point_missing_not_unit_error():
    # Kills removing `value.missing is None` in _unit_problems.
    first, last = ep3_tests.several_full_years()
    document = ep3_tests.climate_document()
    document["daily_series"] = [
        ep3_tests.daily_series(name, first, last) for name in ep3_tests.DAILY_INPUTS
    ]
    document["point"]["latitude"]["unit"] = ep3.POINT_UNITS.latitude_decimal_degrees
    document["point"]["elevation"] = {
        "value": None,
        "unit": "PLACEHOLDER_unaccepted_unit",
        "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER"},
    }
    climate = ep3_tests.SiteClimate.model_validate(document)
    result = ep3_tests.run(climate_=climate)
    for item in result:
        assert item.missing is not None
        assert item.missing.reason == "MISSING_INPUT"
        assert "the elevation of the point of the climate record is missing" in (
            item.missing.detail
        )
        assert "not in the accepted unit" not in item.missing.detail
        assert "Q11" not in item.missing.detail


def test_notes_keep_first_day_and_include_note_on_last_day_of_ag_year():
    # Kills _Notes.note overwriting first day (`self._first[text] = day`) and
    # _Notes.until using `day < last` instead of `day <= last`.
    notes = ep3._Notes()
    first_ag_end = ep3_tests.last_day_of(2001)
    note_a = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER note a")
    note_b = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER note b")
    notes.note(note_a, first_ag_end)
    notes.note(note_a, first_ag_end + ONE_DAY * 30)
    notes.note(note_b, first_ag_end + ONE_DAY)
    assert notes.until(first_ag_end) == ["NOT_COMPUTABLE: PLACEHOLDER note a"]
    assert notes.until(first_ag_end + ONE_DAY) == [
        "NOT_COMPUTABLE: PLACEHOLDER note a",
        "NOT_COMPUTABLE: PLACEHOLDER note b",
    ]

    # End-to-end: overlap occurring for the first time on 2002-06-30 (the last
    # day of agricultural year 2001) must be reported in year 2001.
    first, last = ep3_tests.several_full_years()
    overlap_day = ep3_tests.last_day_of(first.year)
    calendar = ep3_tests.rotation_calendar(
        first.isoformat(),
        last.isoformat(),
        [
            (
                "a",
                "crop-a",
                (overlap_day - ONE_DAY).isoformat(),
                (overlap_day + ONE_DAY).isoformat(),
            ),
            (
                "b",
                "crop-b",
                overlap_day.isoformat(),
                (overlap_day + ONE_DAY).isoformat(),
            ),
            ("c", "crop-a", last.isoformat(), last.isoformat()),
        ],
    )
    result = ep3_tests.run(
        calendar_=calendar, climate_=ep3_tests.climate((first, last))
    )
    year_2001 = result[0]
    assert year_2001.ag_year == first.year
    assert year_2001.missing is not None
    assert ep3.CROPS_OVERLAP in year_2001.missing.detail
    assert f"the first on {overlap_day.isoformat()}" in year_2001.missing.detail


def test_state_carry_preserves_first_cause_across_multiple_missing_days():
    # Kills removing `if self.cause is None:` in _State.carry.
    first, _ = ep3_tests.several_full_years()
    day1 = first + ONE_DAY * 2
    day2 = day1 + ONE_DAY
    days = ep3_tests.chain(climate_=ep3_tests.climate(held_missing=(day1, day2)))
    by_date = {day.date: day for day in days}

    cause_storage = by_date[day1].balance.storage_end.detail
    assert "storage after" not in cause_storage
    assert by_date[day2].balance.storage_start.detail.endswith(cause_storage)
    assert by_date[day2 + ONE_DAY].balance.storage_start.detail.endswith(cause_storage)
    assert (
        "storage after"
        not in by_date[day2 + ONE_DAY].balance.storage_start.detail.split(
            "missing since: ", 1
        )[1]
    )

    cause_depletion = by_date[day1].surface_layer.depletion_end.detail
    assert "depletion after" not in cause_depletion
    assert by_date[day2 + ONE_DAY].surface_depletion_carried.detail.endswith(
        cause_depletion
    )


def test_layer_start_accepts_depletion_equal_to_layer_total():
    # Kills `depletion > layer_total` mutated to `depletion >= layer_total` in _layer_start.
    start = ep3_tests.PLACEHOLDER_TEW
    parameters = ep3_tests.catalogue_with(
        {("initial_depletion", None): ep3_tests.site_record("initial_depletion", start)}
    )
    days = ep3_tests.chain(parameters=parameters)
    reduced = ep3_tests.mulched(ep3_tests.PLACEHOLDER_RESIDUE_COVER["crop-a"])
    assert reduced < start
    first = days[0]
    assert first.precipitation == 0
    assert first.surface_layer.depletion_start == pytest.approx(reduced)
    assert first.surface_depletion_carried == pytest.approx(start)
    for item in ep3_tests.run(parameters=parameters):
        ep3_tests.assert_computed(item)


def test_layer_start_handles_missing_precipitation_or_runoff_when_above_total():
    # Kills removing the `isinstance(precipitation, Missing) or isinstance(runoff, Missing)`
    # guard in _layer_start.
    missing_p = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER p")
    missing_r = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER r")
    res_p = ep3._layer_start(4.22, 2.22, 4.44, missing_p, 0.555)
    assert res_p.depletion == 2.22
    assert res_p.precipitation == missing_p
    assert res_p.above == pytest.approx(2.0)

    res_r = ep3._layer_start(4.22, 2.22, 4.44, 1.11, missing_r)
    assert res_r.depletion == 2.22
    assert res_r.precipitation == 1.11
    assert res_r.above == pytest.approx(2.0)

    first, _ = ep3_tests.several_full_years()
    parameters = ep3_tests.catalogue_with(
        {("initial_depletion", None): ep3_tests.site_record("initial_depletion", 4.22)}
    )
    days = ep3_tests.chain(
        climate_=ep3_tests.climate(held_missing=(first,)),
        parameters=parameters,
    )
    assert isinstance(days[0].balance.storage_end, Missing)


def test_column_evaporation_coefficient_when_demanded_is_zero_and_on_crop_day():
    # Kills `surface.evaporation >= surface.evaporation_demanded` mutated to `>`
    # (ZeroDivisionError when evaporation_demanded == 0) and removing `not no_crop`.
    surface_zero = ep3.evaporation.DayResult(
        date=d("2001-07-01"),
        depletion_start=2.22,
        depletion_end=2.22,
        precipitation=0.0,
        runoff=0.0,
        infiltration=0.0,
        deep_percolation=0.0,
        reduction_coefficient=1.0,
        upper_limit=1.11,
        exposed_and_wetted_fraction=0.0,
        evaporation_coefficient=0.0,
        evaporation_demanded=0.0,
        evaporation=0.0,
        evaporation_from_exposed_fraction=0.0,
        evaporation_shortfall=0.0,
        runoff_shortfall=0.0,
    )
    start_at = ep3.LayerStart(depletion=2.22, precipitation=0.0, above=None)
    assert (
        ep3._column_evaporation_coefficient(surface_zero, start_at, 2.22, True) == 0.0
    )

    # End-to-end with cover_fraction = 1.0 (structurally full cover, so
    # exposed_and_wetted_fraction = 0 and evaporation_demanded = 0) and
    # initial_depletion == reduced TEW == REW.
    full = 1.0
    reduction = 0.0555  # PLACEHOLDER: leaves reduced TEW == REW (2.22)
    reduced = ep3_tests.mulched(full, reduction)
    assert reduced == pytest.approx(
        ep3_tests.PLACEHOLDER_SITE["readily_evaporable_water"]
    )
    parameters = ep3_tests.catalogue_with(
        {
            ("cover_fraction", "no_crop"): ep3_tests.unmarked(
                ep3_tests.placeholder_record(
                    ep3.COVER_FRACTION, full, ep3_tests.scope_of("no_crop")
                )
            ),
            ("surface_residue_cover", "fallow:crop-a"): ep3_tests.fallow_record(
                "crop-a", full
            ),
            ("mulch_total_evaporable_water_reduction", None): ep3_tests.site_record(
                "mulch_total_evaporable_water_reduction", reduction
            ),
            ("initial_depletion", None): ep3_tests.site_record(
                "initial_depletion", reduced
            ),
        }
    )
    days = ep3_tests.chain(parameters=parameters)
    assert days[0].surface_layer.evaporation_demanded == 0.0
    assert days[0].balance.evaporation == 0.0

    # On a crop day (`no_crop=False`), coefficient is never scaled down even when
    # depletion == total and evaporation < evaporation_demanded.
    surface_crop = ep3.evaporation.DayResult(
        date=d("2001-07-01"),
        depletion_start=4.44,
        depletion_end=4.44,
        precipitation=0.0,
        runoff=0.0,
        infiltration=0.0,
        deep_percolation=0.0,
        reduction_coefficient=1.0,
        upper_limit=1.11,
        exposed_and_wetted_fraction=0.555,
        evaporation_coefficient=0.444,
        evaporation_demanded=0.888,
        evaporation=0.111,
        evaporation_from_exposed_fraction=0.2,
        evaporation_shortfall=0.777,
        runoff_shortfall=0.0,
    )
    assert (
        ep3._column_evaporation_coefficient(
            surface_crop,
            ep3.LayerStart(depletion=4.44, precipitation=0.0, above=None),
            4.44,
            False,
        )
        == 0.444
    )


def test_missing_covering_propagates_to_runoff_and_surface_layer_after_crop_day():
    # Kills missing-propagation mutants when `isinstance(covering, Missing)`
    # omits setting kcb, height, exponent, or curve_number to `covering`
    # (which would silently reuse the previous day's numbers).
    calendar = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2033-08-15",
        [
            ("p", "crop-a", "2032-07-01", "2032-07-10"),
            ("long", "crop-b", "2031-07-11", "2033-08-15"),
        ],
    )
    moved = ep3_tests.phase_calendar(calendar, 1)
    first, last = ep3_tests.literal_record()
    days = ep3_tests.chain(moved, ep3_tests.climate((first, last)))
    # Transition from the last valid crop day ('p') to the first missing day
    # covered by 'long' (where covering is Missing).
    prev_day, missing_day = next(
        (prev, curr)
        for prev, curr in itertools.pairwise(days)
        if ep3_tests.is_number(prev.balance.storage_end)
        and isinstance(curr.balance.storage_end, Missing)
    )
    assert ep3_tests.is_number(prev_day.runoff.runoff)
    assert ep3_tests.is_number(prev_day.surface_layer.evaporation_coefficient)
    assert isinstance(missing_day.runoff.runoff, Missing)
    assert missing_day.runoff.runoff.reason == "MISSING_INPUT"
    assert ep3.CROP_DATES_MISSING in missing_day.runoff.runoff.detail
    assert isinstance(missing_day.surface_layer.evaporation_coefficient, Missing)
    assert (
        "basal_crop_coefficient (MISSING_INPUT)"
        in missing_day.surface_layer.evaporation_coefficient.detail
    )
    assert (
        "cover_fraction (MISSING_INPUT)"
        in missing_day.surface_layer.evaporation_coefficient.detail
    )
    assert (
        "climate_adjusted_upper_limit (MISSING_INPUT)"
        in missing_day.surface_layer.evaporation_coefficient.detail
    )
    assert isinstance(missing_day.surface_layer.upper_limit, Missing)
    assert isinstance(missing_day.balance.storage_end, Missing)
    assert "crop (MISSING_INPUT)" in missing_day.balance.storage_end.detail


def test_tail_day_uses_no_crop_height_curve_number_and_basal_coefficient(monkeypatch):
    # Kills omitting `height = ...`, `curve_number = ...`, or `kcb = ...`
    # reset to NO_CROP on a stage-tail day (crop-b has distinct height=2.22,
    # curve_number=0.555, kcb=0.444..0.666 vs no_crop 0.111, 1.11, 0.333).
    first, last = ep3_tests.several_full_years()
    crop_b_days = ep3_tests.period_days("crop-b")
    sowing_b = first + ONE_DAY * 10
    harvest_b = sowing_b + ONE_DAY * (crop_b_days + 9)  # 10 tail days
    calendar = ep3_tests.rotation_calendar(
        first.isoformat(),
        (last + ONE_DAY * (ep3_tests.period_days("crop-a") - 1)).isoformat(),
        [
            ("b", "crop-b", sowing_b.isoformat(), harvest_b.isoformat()),
            (
                "closing",
                "crop-a",
                last.isoformat(),
                (last + ONE_DAY * (ep3_tests.period_days("crop-a") - 1)).isoformat(),
            ),
        ],
    )
    # Give every day enough precipitation to produce runoff differences between
    # curve_number=0.555 (crop-b) and curve_number=1.11 (no_crop).
    climate = ep3_tests.climate((first, last))
    rainy = copy.deepcopy(climate.model_dump(mode="json"))
    for series in rainy["daily_series"]:
        if series["quantity"] == ep3_tests.PRECIPITATION:
            for item in series["days"]:
                item["value"] = 6.66  # PLACEHOLDER wet day
    rainy_climate = ep3_tests.SiteClimate.model_validate(rainy)

    given = ep3_tests.spy_surface_layer(monkeypatch)
    days = ep3_tests.chain(calendar, rainy_climate)
    by_date = {day.date: day for day in days}
    tail_first = sowing_b + ONE_DAY * crop_b_days
    tail_day = by_date[tail_first]
    _, tail_input, _ = given[tail_first]
    _, crop_input, _ = given[sowing_b]
    _, fallow_input, _ = given[first]

    assert tail_input.basal_crop_coefficient == pytest.approx(
        ep3_tests.PLACEHOLDER_DAY["basal_crop_coefficient"]["no_crop"]
    )
    # Confirm climate_adjusted_upper_limit matches no_crop height (0.111), not
    # crop-b height (2.22).
    assert tail_input.climate_adjusted_upper_limit != pytest.approx(
        crop_input.climate_adjusted_upper_limit
    )
    assert tail_input.climate_adjusted_upper_limit == pytest.approx(
        fallow_input.climate_adjusted_upper_limit
    )
    # Confirm runoff uses no_crop curve_number (1.11), not crop-b (0.555).
    assert tail_day.runoff.runoff == pytest.approx(by_date[first].runoff.runoff)
    assert tail_day.runoff.runoff != pytest.approx(by_date[sowing_b].runoff.runoff)


def test_missing_kcb_or_root_depth_is_not_duplicated_as_chain_note():
    # Kills mutating `if growth.detail == STAGE_UNKNOWN or growth.reason != "MISSING_INPUT":`
    # to `if True:` in _run_chain.
    for key in (
        ("basal_crop_coefficient", "crop-a:initial"),
        ("maximum_root_depth", "crop-a"),
    ):
        result = ep3_tests.run(
            calendar_=ep3_tests.chain_calendar(),
            parameters=ep3_tests.catalogue_with({key: None}),
        )
        missing = [item for item in result if not ep3_tests.is_computed(item)]
        assert missing
        for item in missing:
            assert item.missing.reason == "MISSING_INPUT"
            assert "chain MISSING_INPUT:" not in item.missing.detail


def test_negative_total_evaporable_water_is_noted_as_not_computable():
    # Kills removing `if isinstance(value, Missing) and value.reason == "NOT_COMPUTABLE":`
    # in _total_evaporable_water.
    parameters = ep3_tests.catalogue_with(
        {
            ("field_capacity_water_content", None): ep3_tests.site_record(
                "field_capacity_water_content", 1.11
            ),
            ("wilting_point_water_content", None): ep3_tests.site_record(
                "wilting_point_water_content", 2.22
            ),
        }
    )
    result = ep3_tests.run(parameters=parameters)
    for item in result:
        assert item.missing is not None
        assert item.missing.reason != "NOT_AVAILABLE"
        assert any(
            entry.startswith("chain NOT_COMPUTABLE: the total evaporable water:")
            for entry in ep3_tests.items_of(item.missing.detail)
        )


# --- engine/water/living_crop.py ----------------------------------------------


def test_live_crop_by_day_accepts_single_day_record():
    # Kills `if record_end < record_start:` mutated to `<=` in live_crop_by_day.
    calendar = ep3_tests.two_year_calendar()
    from engine.water import test_living_crop as lc_tests

    params = lc_tests.two_crop_lengths()
    for day, expected in (
        (d("2001-08-10"), True),  # sowing day of w
        (d("2001-09-23"), False),  # tail day of w
        (d("2001-07-01"), False),  # fallow day
    ):
        flags = living_crop.live_crop_by_day(calendar, day, day, parameters=params)
        assert flags == {day: expected}


def test_live_crop_by_day_missing_start_month_takes_precedence_over_infeasible():
    # Kills swapping start_month vs feasibility check order in live_crop_by_day.
    document = ep3_tests.chain_calendar_document()
    document["ag_year_start"] = {
        "month": None,
        "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER"},
    }
    document["feasibility"] = {
        "feasible": False,
        "violations": [{"rule": "PLACEHOLDER-rule", "component_ids": []}],
    }
    both = RotationCalendar.model_validate(document)
    first, last = ep3_tests.literal_record()
    flags = living_crop.live_crop_by_day(both, first, last, parameters={})
    assert set(flags.values()) == {
        Missing(reason="MISSING_INPUT", detail=living_crop.START_MONTH_UNKNOWN)
    }


def test_component_of_day_undated_exact_boundaries_and_partial_missing_dates():
    # Kills `<` vs `<=` on earliest_day/latest_day in component_of_day, and
    # earliest_day/latest_day always falling back to calendar_start/cycle_last_day.
    base_cal = ep3_tests.calendar()
    comp_end_missing = CalendarComponent.model_construct(
        component_id="PLACEHOLDER-end-missing",
        crop_id="crop-a",
        start=DateValue.model_construct(date=d("2001-09-10")),
        end=DateValue.model_construct(date=None, missing=None),
        periods=(),
    )
    comp_start_missing = CalendarComponent.model_construct(
        component_id="PLACEHOLDER-start-missing",
        crop_id="crop-b",
        start=DateValue.model_construct(
            date=None,
            missing=ep3_tests.calendar_without_start_month().ag_year_start.missing,
        ),
        end=DateValue.model_construct(date=d("2002-04-20")),
        periods=(),
    )
    calendar = RotationCalendar.model_construct(
        case_id=base_cal.case_id,
        field_id=base_cal.field_id,
        ag_year_start=base_cal.ag_year_start,
        start_date=base_cal.start_date,
        end_date=base_cal.end_date,
        components=[comp_end_missing, comp_start_missing],
        feasibility=base_cal.feasibility,
    )

    rc_end_missing = RepeatedComponent(
        component_id="PLACEHOLDER-end-missing",
        crop_id="crop-a",
        cycle=0,
        start=d("2001-09-10"),
        end=None,
        calendar_start=d("2001-07-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-01-15"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_start_missing = RepeatedComponent(
        component_id="PLACEHOLDER-start-missing",
        crop_id="crop-b",
        cycle=0,
        start=None,
        end=d("2002-04-20"),
        calendar_start=d("2002-02-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    assert living_crop.earliest_day(rc_end_missing) == d("2001-09-10")
    assert living_crop.latest_day(rc_end_missing) == d("2002-01-15")
    assert living_crop.earliest_day(rc_start_missing) == d("2002-02-01")
    assert living_crop.latest_day(rc_start_missing) == d("2002-04-20")

    repeated = RepeatedRotation(
        start_month=7,
        record_start=d("2001-07-01"),
        record_end=d("2002-06-30"),
        cycle_length=1,
        ag_years=(2001,),
        first_day=d("2001-07-01"),
        last_day=d("2002-06-30"),
        cycles=(
            Cycle(
                index=0,
                shift_years=0,
                start=d("2001-07-01"),
                end=d("2002-06-30"),
                last_day=d("2002-06-30"),
                complete=True,
                components_not_laid_out=(),
            ),
        ),
        components=(rc_end_missing, rc_start_missing),
    )
    comp_of = living_crop.component_of_day(calendar, repeated)

    # Exact boundaries for rc_end_missing: [2001-09-10, 2002-01-15]
    assert comp_of(d("2001-09-09")) is None
    m_start = comp_of(d("2001-09-10"))
    m_end = comp_of(d("2002-01-15"))
    assert isinstance(m_start, Missing) and m_start.reason == "MISSING_INPUT"
    assert "end date no reason given" in m_start.detail
    assert "start date" not in m_start.detail
    assert m_end == m_start
    assert comp_of(d("2002-01-16")) is None

    # Exact boundaries for rc_start_missing: [2002-02-01, 2002-04-20]
    assert comp_of(d("2002-01-31")) is None
    m2_start = comp_of(d("2002-02-01"))
    m2_end = comp_of(d("2002-04-20"))
    assert isinstance(m2_start, Missing)
    assert "start date NOT_DECLARED" in m2_start.detail
    assert "end date" not in m2_start.detail
    assert m2_end == m2_start
    assert comp_of(d("2002-04-21")) is None


def test_repeat_calendar_over_record_errors_and_live_crop_days_errors(monkeypatch):
    calendar = ep3_tests.two_year_calendar()
    first, last = ep3_tests.literal_record()

    monkeypatch.setattr(living_crop, "repeat_over_record", lambda c, s, e: None)
    with pytest.raises(ValueError, match="did not repeat"):
        living_crop.repeat_calendar_over_record(calendar, first, last)

    wrong_years = RepeatedRotation(
        start_month=7,
        record_start=first,
        record_end=last,
        cycle_length=2,
        ag_years=(1999,),
        first_day=first,
        last_day=last,
        cycles=(),
        components=(),
    )
    monkeypatch.setattr(living_crop, "repeat_over_record", lambda c, s, e: wrong_years)
    with pytest.raises(ValueError, match="other agricultural years"):
        living_crop.repeat_calendar_over_record(calendar, first, last)

    # live_crop_days: harvest < sowing, multiple missing lengths, and is_live before sowing
    lengths = {"initial": 11.0, "development": 11.0, "mid": 11.0, "late": 11.0}
    with pytest.raises(ValueError):
        living_crop.live_crop_days(d("2031-02-01"), d("2031-01-01"), lengths, what="ex")

    two_missing = {
        **lengths,
        "initial": Missing(reason="NOT_DECLARED", detail="p1"),
        "late": Missing(reason="NOT_DECLARED", detail="p2"),
    }
    res = living_crop.live_crop_days(
        d("2031-01-01"), d("2031-02-24"), two_missing, what="ex"
    )
    assert isinstance(res, Missing)
    assert stages.STAGE_LENGTH_PARAMETERS["initial"] in res.detail
    assert stages.STAGE_LENGTH_PARAMETERS["late"] in res.detail

    live = living_crop.live_crop_days(
        d("2031-01-01"), d("2031-02-24"), lengths, what="ex"
    )
    assert isinstance(live, living_crop.LiveCropDays)
    with pytest.raises(ValueError):
        live.is_live(d("2030-12-31"))


# --- engine/water/stages.py ---------------------------------------------------


def test_placed_stages_len_and_by_stage_missing_without_detail():
    # Kills PlacedStages.__len__ returning wrong length and by_stage failing when
    # Missing.detail is None.
    lengths = {"initial": 3.0, "development": 4.0, "mid": 2.0, "late": 5.0}
    exact = stages.place_stages(d("2001-09-01"), d("2001-09-14"), lengths, what="ex")
    assert len(exact) == 14
    assert len(exact.tail) == 0

    with_tail = stages.place_stages(
        d("2001-09-01"), d("2001-09-17"), lengths, what="ex"
    )
    assert len(with_tail) == 14
    assert len(with_tail.tail) == 3

    cut = stages.place_stages(d("2001-09-01"), d("2001-09-06"), lengths, what="ex")
    assert len(cut) == 6
    assert len(cut.tail) == 0

    missing_no_detail = Missing(reason="NOT_DECLARED", detail=None)
    got = stages.by_stage(exact[d("2001-09-01")], missing_no_detail, 0.555, 0.222)
    assert got == Missing(reason="MISSING_INPUT", detail="NOT_DECLARED")


# --- engine/water/fallow.py ---------------------------------------------------


def test_following_crop_on_sowing_day_returns_next_sowing_or_missing():
    # Kills `start > day` mutated to `start >= day` in fallow.following_crop.
    s1 = d("2001-08-10")
    s2 = d("2002-01-05")
    following = fallow.following_crop([(s1, "crop-a"), (s2, "crop-b")], [])
    assert following(s1) == "crop-b"
    no_next = following(s2)
    assert isinstance(no_next, Missing)
    assert no_next.reason == "MISSING_INPUT"
    assert no_next.detail == fallow.NO_FOLLOWING_CROP


def test_mulched_tew_allows_zero_reduction_and_rejects_zero_remaining_tew():
    # Kills `reduction_per_increment < 0` -> `<= 0` and `value <= 0` -> `value < 0`
    # and missing math.isfinite checks on total_evaporable_water / cover_increment.
    tew = 4.44
    unchanged = fallow.mulched_total_evaporable_water(
        tew, 0.444, reduction_per_increment=0.0, cover_increment=0.111
    )
    assert unchanged == tew

    zero_left = fallow.mulched_total_evaporable_water(
        tew, 1.0, reduction_per_increment=0.111, cover_increment=0.111
    )
    assert isinstance(zero_left, Missing)
    assert zero_left.reason == "NOT_COMPUTABLE"
    assert "leaves no evaporable water" in zero_left.detail

    for bad_tew, bad_inc in ((math.inf, 0.111), (tew, math.nan)):
        bad = fallow.mulched_total_evaporable_water(
            bad_tew, 0.444, reduction_per_increment=0.0333, cover_increment=bad_inc
        )
        assert isinstance(bad, Missing)
        assert bad.reason == "NOT_COMPUTABLE"


# --- engine/water/_parameters.py ----------------------------------------------


def test_catalogue_problems_until_includes_last_day_and_excludes_next_day():
    # Kills `if day > last:` mutated to `if day >= last:` in Catalogue.problems_until.
    catalogue = _parameters.Catalogue({})
    last = d("2002-06-30")
    catalogue.value("column_depth", (), last)
    catalogue.value("column_capacity", (), last + ONE_DAY)
    items = catalogue.problems_until(last)
    assert any("'column_depth'" in item for item in items)
    assert not any("'column_capacity'" in item for item in items)

    # End-to-end: a crop sown for the first time on the last day of ag_year 2001
    # whose basal_crop_coefficient (initial) is missing must be named in ag_year 2001.
    first, span_end = ep3_tests.several_full_years()
    sow_on_last = ep3_tests.last_day_of(first.year)
    harvest_later = sow_on_last + ONE_DAY * (ep3_tests.period_days("crop-b") - 1)
    calendar = ep3_tests.rotation_calendar(
        first.isoformat(),
        (span_end + ONE_DAY * (ep3_tests.period_days("crop-a") - 1)).isoformat(),
        [
            ("b", "crop-b", sow_on_last.isoformat(), harvest_later.isoformat()),
            (
                "closing",
                "crop-a",
                span_end.isoformat(),
                (
                    span_end + ONE_DAY * (ep3_tests.period_days("crop-a") - 1)
                ).isoformat(),
            ),
        ],
    )
    parameters = ep3_tests.catalogue_with(
        {("basal_crop_coefficient", "crop-b:initial"): None}
    )
    result = ep3_tests.run(
        calendar_=calendar,
        climate_=ep3_tests.climate((first, span_end)),
        parameters=parameters,
    )
    year_2001 = result[0]
    assert year_2001.ag_year == first.year
    assert year_2001.missing is not None
    assert year_2001.missing.reason == "MISSING_INPUT"
    scope = json.dumps(ep3_tests.unmarked(ep3_tests.scope_of("crop-b:initial")))
    assert ep3_tests.no_record_item(year_2001.missing.detail, scope).endswith(
        ": 'basal_crop_coefficient'"
    )
