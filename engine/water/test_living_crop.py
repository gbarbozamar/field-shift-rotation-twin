"""Tests of engine/water/living_crop.py (unit l1/living-crop-days, issue #357).

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
