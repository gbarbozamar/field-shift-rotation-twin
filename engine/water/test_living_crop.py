"""Tests of engine/water/living_crop.py (units l1/living-crop-days, issue #357,
and l1/live-crop-by-day, issue #399).

Every date, stage length and record here is PLACEHOLDER example data, plainly
not a value of the method: the dates are arbitrary and the lengths are
written with repeated digits. The equality test runs EP3 on the PLACEHOLDER
catalogue and climate of its own structural tests (``test_exposure.py``).
"""

from __future__ import annotations

import datetime as dt

import pytest

from contracts.results.models import Missing
from engine.calendar.repeat import repeat_over_record
from engine.water import exposure as ep3
from engine.water import living_crop as module
from engine.water import test_exposure as ep3_tests
from engine.water.stages import GROWTH_STAGES, STAGE_LENGTH_PARAMETERS

ONE_DAY = dt.timedelta(days=1)


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


# PLACEHOLDER stage lengths (days): initial, development, mid, late, 44 in all.
LENGTHS = {"initial": 11.0, "development": 11.0, "mid": 11.0, "late": 11.0}


def every_day(first: dt.date, last: dt.date) -> list[dt.date]:
    days, day = [], first
    while day <= last:
        days.append(day)
        day += ONE_DAY
    return days


def test_stages_shorter_than_the_period_leave_a_tail_with_no_live_crop():
    # PLACEHOLDER example: a period of 55 days and stages of 44 (D135, D136).
    sowing, harvest = d("2031-01-01"), d("2031-02-24")
    live = module.live_crop_days(sowing, harvest, LENGTHS, what="an example")
    assert isinstance(live, module.LiveCropDays)
    days = every_day(sowing, harvest)
    assert list(live.days) == days
    live_days = [day for day in days if live.is_live(day)]
    assert live_days == days[:44]
    assert list(live.stages.tail) == days[44:]
    assert all(not live.is_live(day) for day in days[44:])


def test_stages_longer_than_the_period_are_cut_at_the_harvest():
    # PLACEHOLDER example: a period of 33 days and stages of 44: every day of
    # the period up to the harvest has a live crop, and no tail (D135).
    sowing, harvest = d("2031-01-01"), d("2031-02-02")
    live = module.live_crop_days(sowing, harvest, LENGTHS, what="an example")
    assert isinstance(live, module.LiveCropDays)
    days = every_day(sowing, harvest)
    assert live.days == dict.fromkeys(days, True)
    assert live.stages.tail == ()
    assert live.stages[harvest].stage == "mid"


def test_a_period_that_crosses_the_start_of_an_agricultural_year():
    # PLACEHOLDER example: a period that runs through 1 July (the start month
    # of the agricultural year of the examples): the days are counted on
    # through it, with no break and no change of the rule.
    sowing, harvest = d("2031-06-01"), d("2031-07-31")
    live = module.live_crop_days(sowing, harvest, LENGTHS, what="an example")
    assert isinstance(live, module.LiveCropDays)
    days = every_day(sowing, harvest)
    assert list(live.days) == days
    assert live.is_live(d("2031-06-30")) and live.is_live(d("2031-07-01"))
    assert [day for day in days if live.days[day]] == days[:44]
    # 1 July is the 31st day of the period: the mid stage runs from the 23rd
    # day to the 33rd, with stages of 11 days each.
    assert live.stages[d("2031-07-01")].stage == "mid"
    assert live.stages[d("2031-07-01")].day_in_stage == 9


@pytest.mark.parametrize("stage", GROWTH_STAGES)
def test_a_missing_stage_length_leaves_the_days_missing_never_without_a_crop(stage):
    reason = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER: no record")
    lengths = {**LENGTHS, stage: reason}
    live = module.live_crop_days(
        d("2031-01-01"), d("2031-02-24"), lengths, what="an example"
    )
    assert isinstance(live, Missing)
    assert live.reason == "MISSING_INPUT"
    assert f"'{STAGE_LENGTH_PARAMETERS[stage]}'" in live.detail
    assert "PLACEHOLDER: no record" in live.detail
    assert "D79" in live.detail


def test_a_length_that_is_not_whole_days_is_not_computable():
    lengths = {**LENGTHS, "mid": 1.5}  # PLACEHOLDER: not a whole number of days
    live = module.live_crop_days(
        d("2031-01-01"), d("2031-02-24"), lengths, what="an example"
    )
    assert isinstance(live, Missing)
    assert live.reason == "NOT_COMPUTABLE"


def test_a_stage_with_no_length_or_a_day_outside_the_period_raises():
    without_late = {stage: LENGTHS[stage] for stage in GROWTH_STAGES[:-1]}
    with pytest.raises(ValueError):
        module.live_crop_days(
            d("2031-01-01"), d("2031-02-24"), without_late, what="an example"
        )
    live = module.live_crop_days(
        d("2031-01-01"), d("2031-02-24"), LENGTHS, what="an example"
    )
    with pytest.raises(ValueError):
        live.is_live(d("2031-02-25"))


def stage_length_records(crop: str) -> dict[str, dict]:
    """A catalogue that holds the four PLACEHOLDER stage lengths of ``crop``
    and nothing else: no basal crop coefficient, no root depth."""
    records = {}
    for stage, parameter_id in STAGE_LENGTH_PARAMETERS.items():
        records[f"stage_length_{stage}"] = ep3_tests.unmarked(
            ep3_tests.placeholder_record(
                parameter_id, LENGTHS[stage], ep3_tests.scope_of(crop)
            )
        )
    return records


def test_the_catalogue_is_read_by_the_exact_scope_of_the_crop_and_kcb_does_not_matter():
    # Only the stage lengths decide the days: with no record of the basal
    # crop coefficient or of the root depth in the catalogue, the days are
    # the same (the crop is on the field, although EP3 does not compute
    # such a day).
    crop = ep3_tests.crop_word("crop-a")
    parameters = stage_length_records("crop-a")
    sowing, harvest = d("2031-01-01"), d("2031-02-24")
    live = module.live_crop_days_of_crop(
        sowing, harvest, ep3_tests.unmarked(crop), parameters=parameters
    )
    assert isinstance(live, module.LiveCropDays)
    expected = module.live_crop_days(sowing, harvest, LENGTHS, what="an example")
    assert live.days == expected.days
    # Another crop has no stage length in that catalogue: its days are not
    # known, never days with no crop.
    other = module.live_crop_days_of_crop(
        sowing,
        harvest,
        ep3_tests.unmarked(ep3_tests.crop_word("crop-b")),
        parameters=parameters,
    )
    assert isinstance(other, Missing) and other.reason == "MISSING_INPUT"


def expected_live_days(calendar, climate, parameters) -> dict[dt.date, bool | Missing]:
    """For every day of the record, whether a live crop stands, from this
    module and the repetition of the rotation over the record (D47), not
    from EP3: no component covers the day (a fallow day), or the days of
    the component's period from ``live_crop_days_of_crop``."""
    (precipitation,) = [
        series
        for series in climate.daily_series
        if series.quantity == ep3_tests.PRECIPITATION
    ]
    first, last = precipitation.start_date, precipitation.end_date
    repeated = repeat_over_record(calendar, first, last)
    flags: dict[dt.date, bool | Missing] = dict.fromkeys(every_day(first, last), False)
    for component in repeated.components:
        assert component.start is not None and component.end is not None
        live = module.live_crop_days_of_crop(
            component.start,
            component.end,
            component.crop_id,
            parameters=parameters,
            on=max(component.start, first),
        )
        for day in every_day(max(component.start, first), min(component.end, last)):
            flags[day] = live if isinstance(live, Missing) else live.is_live(day)
    return flags


@pytest.mark.parametrize(
    "run",
    [
        "calendar with crops",
        "calendar with crops, long dry spells",
        "a tail of 33 days and a cut of 66",
        "a tail and a cut of one day",
        "the bare calendar",
    ],
)
def test_the_days_with_a_live_crop_are_the_crop_days_of_ep3(run):
    # On every day EP3 computes, the day has a live crop by this module
    # exactly when EP3 gives the balance a crop, so that its demanded
    # transpiration is a number; and it has none exactly when EP3 gives the
    # balance no crop, so that its demanded transpiration is NOT_APPLICABLE
    # (D106, D136, D157). PLACEHOLDER catalogue and climate of EP3's tests.
    climate = ep3_tests.climate()
    calendar = {
        "calendar with crops": ep3_tests.chain_calendar(),
        "calendar with crops, long dry spells": ep3_tests.chain_calendar(),
        "a tail of 33 days and a cut of 66": ep3_tests.calendar_with_tail_and_cut(
            33, 66
        ),
        "a tail and a cut of one day": ep3_tests.calendar_with_tail_and_cut(1, 1),
        "the bare calendar": ep3_tests.bare_calendar(),
    }[run]
    if run.endswith("long dry spells"):
        climate = ep3_tests.climate_with_dry_spells()
    parameters = ep3_tests.catalogue()
    days = ep3_tests.chain(calendar, climate, parameters)
    expected = expected_live_days(calendar, climate, parameters)
    counted = {True: 0, False: 0}
    for day in days:
        if not ep3_tests.is_number(day.balance.storage_end):
            continue
        demanded = day.balance.transpiration_demanded
        crop_day = not isinstance(demanded, Missing)
        if not crop_day:
            assert demanded.reason == ep3.NO_CROP_ON_THE_DAY, day.date
        assert expected[day.date] is crop_day, (run, day.date)
        counted[crop_day] += 1
    assert counted[False] > 0
    if run != "the bare calendar":
        assert counted[True] > 0


def test_ep3_and_this_module_name_a_missing_stage_length_the_same_way():
    # With the four stage lengths of every crop removed, EP3's crop days are
    # MISSING_INPUT naming D79, and this module leaves those days not known.
    parameters = ep3_tests.catalogue_with(
        {
            ep3_tests.stage_length_key(crop, stage): None
            for crop in ep3_tests.CROPS
            for stage in ("initial", "development", "mid", "late")
        }
    )
    calendar = ep3_tests.chain_calendar()
    climate = ep3_tests.climate()
    expected = expected_live_days(calendar, climate, parameters)
    unknown = [day for day, flag in expected.items() if isinstance(flag, Missing)]
    assert unknown
    assert all(expected[day].reason == "MISSING_INPUT" for day in unknown)
    assert not any(flag is True for flag in expected.values())


# --- live_crop_by_day: every day of the record (unit #399) ---------------------


def two_crop_lengths() -> dict[str, dict]:
    """The four PLACEHOLDER stage lengths (44 days in all) of crop-a and of
    crop-b, and nothing else."""
    return {
        f"{crop}_{name}": record
        for crop in ep3_tests.CROPS
        for name, record in stage_length_records(crop).items()
    }


def with_length(record: dict, value: float) -> dict:
    """A stage-length record with another PLACEHOLDER value and no range."""
    changed = {**record, "value": value, "range": None}
    changed["range_missing_reason"] = "an example with no range"
    return changed


def by_day(calendar, parameters=None, record=None) -> dict[dt.date, bool | Missing]:
    first, last = record or ep3_tests.literal_record()
    return module.live_crop_by_day(
        calendar,
        first,
        last,
        parameters=two_crop_lengths() if parameters is None else parameters,
    )


def test_every_day_of_the_record_is_given_in_order():
    first, last = ep3_tests.literal_record()
    flags = by_day(ep3_tests.two_year_calendar())
    assert list(flags) == every_day(first, last)


def test_the_rotation_repeats_over_the_record_with_a_tail_after_maturity_and_fallow():
    # The two-year PLACEHOLDER rotation laid on the record of 2001 to 2006
    # (D47, D109): w is sown on 10 August and harvested on 20 December; its
    # 44 days of stages end on 22 September, and the days after it up to the
    # harvest are its tail, with no live crop (D136). The days between
    # components are fallow. The rotation starts again two years later.
    flags = by_day(ep3_tests.two_year_calendar())
    assert flags[d("2001-07-01")] is False  # fallow before the first sowing
    assert flags[d("2001-08-09")] is False
    assert flags[d("2001-08-10")] is True  # sowing of w
    assert flags[d("2001-09-22")] is True  # its 44th day
    assert flags[d("2001-09-23")] is False  # the tail
    assert flags[d("2001-12-20")] is False  # its harvest, in the tail
    assert flags[d("2001-12-21")] is False  # fallow
    assert flags[d("2002-01-05")] is True  # sowing of x
    assert flags[d("2003-08-10")] is True  # w again, in the next cycle
    assert flags[d("2003-09-23")] is False
    assert all(isinstance(flag, bool) for flag in flags.values())


def test_stages_longer_than_the_period_are_cut_at_the_harvest_and_the_day_after_is_fallow():
    # x runs from 5 January to 25 May; with stages of 9999 days every day of
    # it has a live crop up to the harvest (D135), and the next day is fallow.
    long = {
        name: with_length(record, 9999.0) for name, record in two_crop_lengths().items()
    }
    flags = by_day(ep3_tests.two_year_calendar(), parameters=long)
    assert all(
        flags[day] is True for day in every_day(d("2002-01-05"), d("2002-05-25"))
    )
    assert flags[d("2002-05-26")] is False


def test_a_day_before_the_described_period_is_not_known():
    # The calendar starts on its first sowing (10 August) and no component of
    # the cycle before it reaches the record: the days from 1 July to 9 August
    # 2001 are not described (D141; point 6 of engine/calendar/repeat.py).
    flags = by_day(ep3_tests.two_year_calendar(start="2031-08-10"))
    unknown = Missing(reason="MISSING_INPUT", detail=module.CROP_UNKNOWN)
    for day in every_day(d("2001-07-01"), d("2001-08-09")):
        assert flags[day] == unknown
    assert flags[d("2001-08-10")] is True


def test_a_component_of_the_lead_in_cycle_keeps_its_declared_dates():
    # Moved to its second year (D132), the crossing rotation has q on the
    # field on the first day of the record: the lead-in cycle (D141) lays it
    # from its declared sowing, before the record, so its stages are counted
    # from that sowing, not from the first day of the record.
    moved = ep3_tests.phase_calendar(ep3_tests.crossing_calendar(), 1)
    first, last = ep3_tests.literal_record()
    repeated = repeat_over_record(moved, first, last)
    (lead,) = [
        item
        for item in repeated.components
        if item.start is not None and item.start < first <= item.end
    ]
    flags = by_day(moved)
    live = module.live_crop_days(lead.start, lead.end, LENGTHS, what="the lead-in")
    for day in every_day(first, lead.end):
        assert flags[day] is live.is_live(day)
    assert any(flags[day] is False for day in every_day(first, lead.end))


def test_a_component_with_a_missing_date_leaves_the_days_it_could_cover_not_known():
    # The component "long" cannot lie whole in one cycle of the moved
    # calendar, so phase_calendar gives it missing dates with their reason;
    # the days it could cover are not known, naming it and that reason.
    calendar = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2033-08-15",
        [
            ("p", "crop-a", "2031-09-01", "2032-02-10"),
            ("long", "crop-b", "2032-03-01", "2033-08-15"),
        ],
    )
    moved = ep3_tests.phase_calendar(calendar, 1)
    flags = by_day(moved)
    unknown = [flag for flag in flags.values() if isinstance(flag, Missing)]
    named = [flag for flag in unknown if flag.detail != module.CROP_UNKNOWN]
    assert named
    for flag in named:
        assert flag.reason == "MISSING_INPUT"
        assert flag.detail.startswith(module.CROP_DATES_MISSING)
        assert "component 'PLACEHOLDER-component-long' (start and end date" in (
            flag.detail
        )
        assert "D141" in flag.detail
    assert any(flag is True for flag in flags.values())


def test_two_components_on_one_day_are_not_computable():
    calendar = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2032-06-30",
        [
            ("a", "crop-a", "2031-08-10", "2031-12-20"),
            ("b", "crop-b", "2031-12-01", "2032-03-01"),
        ],
    )
    flags = by_day(calendar)
    overlap = Missing(reason="NOT_COMPUTABLE", detail=module.CROPS_OVERLAP)
    for day in every_day(d("2001-12-01"), d("2001-12-20")):
        assert flags[day] == overlap
    assert flags[d("2001-11-30")] is False  # the tail of a
    assert flags[d("2001-12-21")] is True  # b alone, inside its 44 days


def test_a_stage_length_with_no_value_leaves_the_period_not_known_never_bare():
    # Only crop-a has stage lengths: every day of a component of crop-b is
    # not known, naming the length (D79), never a day with no crop.
    parameters = {
        name: record
        for name, record in two_crop_lengths().items()
        if name.startswith("crop-a")
    }
    flags = by_day(ep3_tests.two_year_calendar(), parameters=parameters)
    for day in every_day(d("2002-01-05"), d("2002-05-25")):  # x, crop-b
        flag = flags[day]
        assert isinstance(flag, Missing) and flag.reason == "MISSING_INPUT"
        assert STAGE_LENGTH_PARAMETERS["initial"] in flag.detail
        assert "D79" in flag.detail
    assert flags[d("2002-05-26")] is False  # the fallow after it is known
    assert flags[d("2001-08-10")] is True  # crop-a is known


def test_a_stage_length_that_is_not_whole_days_makes_the_period_not_computable():
    parameters = {
        name: (
            with_length(record, 11.5)
            if name.startswith("crop-a") and name.endswith("initial")
            else record
        )
        for name, record in two_crop_lengths().items()
    }
    flags = by_day(ep3_tests.two_year_calendar(), parameters=parameters)
    flag = flags[d("2001-08-10")]
    assert isinstance(flag, Missing) and flag.reason == "NOT_COMPUTABLE"
    assert flags[d("2002-01-05")] is True  # crop-b is not affected


def test_no_start_month_or_an_infeasible_calendar_leaves_every_day_not_known():
    unknown = by_day(ep3_tests.calendar_without_start_month())
    assert set(unknown.values()) == {
        Missing(reason="MISSING_INPUT", detail=module.START_MONTH_UNKNOWN)
    }
    infeasible = by_day(ep3_tests.infeasible_calendar())
    assert set(infeasible.values()) == {
        Missing(reason="NOT_COMPUTABLE", detail=module.CALENDAR_INFEASIBLE)
    }


def test_a_record_that_ends_before_it_starts_is_refused():
    with pytest.raises(ValueError):
        module.live_crop_by_day(
            ep3_tests.two_year_calendar(),
            d("2002-01-01"),
            d("2001-12-31"),
            parameters=two_crop_lengths(),
        )


@pytest.mark.parametrize(
    "run",
    [
        "calendar with crops",
        "calendar with crops, long dry spells",
        "a tail of 33 days and a cut of 66",
        "a tail and a cut of one day",
        "the bare calendar",
    ],
)
def test_live_crop_by_day_is_true_exactly_where_ep3_asks_transpiration(run):
    # On every day EP3 computes, live_crop_by_day is True exactly when EP3
    # gives the balance a crop (its demanded transpiration is a number) and
    # False exactly when it gives none (NOT_APPLICABLE; D106, D136, D157).
    # The flags are also equal, on every day of the record, to flags built
    # without EP3 (``expected_live_days``). PLACEHOLDER catalogue and climate
    # of EP3's tests.
    climate = ep3_tests.climate()
    calendar = {
        "calendar with crops": ep3_tests.chain_calendar(),
        "calendar with crops, long dry spells": ep3_tests.chain_calendar(),
        "a tail of 33 days and a cut of 66": ep3_tests.calendar_with_tail_and_cut(
            33, 66
        ),
        "a tail and a cut of one day": ep3_tests.calendar_with_tail_and_cut(1, 1),
        "the bare calendar": ep3_tests.bare_calendar(),
    }[run]
    if run.endswith("long dry spells"):
        climate = ep3_tests.climate_with_dry_spells()
    parameters = ep3_tests.catalogue()
    (precipitation,) = [
        series
        for series in climate.daily_series
        if series.quantity == ep3_tests.PRECIPITATION
    ]
    flags = module.live_crop_by_day(
        calendar,
        precipitation.start_date,
        precipitation.end_date,
        parameters=parameters,
    )
    assert flags == expected_live_days(calendar, climate, parameters)
    computed = 0
    for day in ep3_tests.chain(calendar, climate, parameters):
        if not ep3_tests.is_number(day.balance.storage_end):
            continue
        demanded = day.balance.transpiration_demanded
        assert flags[day.date] is (not isinstance(demanded, Missing)), (run, day.date)
        computed += 1
    assert computed > 0


def test_ep3_reads_the_rule_of_this_module():
    # EP3 builds its chain on live_crop_over_record and no longer holds the
    # rule: its texts are this module's.
    assert ep3.CROP_UNKNOWN is module.CROP_UNKNOWN
    assert ep3.CROPS_OVERLAP is module.CROPS_OVERLAP
    assert ep3.CROP_DATES_MISSING is module.CROP_DATES_MISSING
    for name in ("_over_record", "_component_of_day", "_why_dates_are_missing"):
        assert not hasattr(ep3, name)
