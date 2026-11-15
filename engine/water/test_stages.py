"""Tests of ``engine/water/stages.py`` (unit l1/water-crop-stages, issue #206;
unit l1/water-stage-tail-d135, issue #224: the cut and the tail of D135, D136).

The cases are PROPOSED (blueprint section 3.7) and are listed in
``EXPOSURE.md`` under "PROPOSED cases of the stages"; a test checks that the
two lists agree. Every number written here is a PLACEHOLDER, plainly not real:
none is a stage length, a crop coefficient or a root depth of any crop, and
none comes from a source.

Run from the repository root: ``py -3.12 -m pytest engine/water/test_stages.py``.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water import stages as module

HERE = Path(__file__).parent
ONE_DAY = dt.timedelta(days=1)
FIRST = dt.date(2001, 9, 1)  # PLACEHOLDER sowing date
WHAT = "PLACEHOLDER period"

# PLACEHOLDER lengths in days, plainly not those of any crop.
LENGTHS = {"initial": 3.0, "development": 4.0, "mid": 2.0, "late": 5.0}
TOTAL = 14  # their sum
LAST = FIRST + ONE_DAY * (TOTAL - 1)

# PLACEHOLDER values at the three points of the curve.
INITIAL, MID, END = 0.222, 0.888, 0.444


def placed(last: dt.date = LAST, first: dt.date = FIRST) -> module.PlacedStages:
    result = module.place_stages(first, last, LENGTHS, what=WHAT)
    assert isinstance(result, module.PlacedStages)
    return result


def stage_list(result: module.PlacedStages) -> list[str]:
    return [result[day].stage for day in sorted(result)]


FILLED = ["initial"] * 3 + ["development"] * 4 + ["mid"] * 2 + ["late"] * 5


# --- the stage boundaries --------------------------------------------------------


def test_stages_follow_one_another_from_the_first_day_and_fill_the_period():
    result = placed()
    assert list(result) == [FIRST + ONE_DAY * n for n in range(TOTAL)]
    stages = [result[day].stage for day in sorted(result)]
    assert stages == (
        ["initial"] * 3 + ["development"] * 4 + ["mid"] * 2 + ["late"] * 5
    )
    assert module.GROWTH_STAGES == ("initial", "development", "mid", "late")


def test_each_stage_counts_its_days_from_one_to_its_length():
    result = placed()
    for stage in module.GROWTH_STAGES:
        days = [result[day] for day in sorted(result) if result[day].stage == stage]
        assert [item.day_in_stage for item in days] == list(
            range(1, int(LENGTHS[stage]) + 1)
        )
        assert {item.stage_length for item in days} == {int(LENGTHS[stage])}
        assert days[-1].fraction == 1.0
        assert days[0].fraction == pytest.approx(1 / LENGTHS[stage])


def test_boundary_days_belong_to_the_stage_that_ends_or_begins_on_them():
    result = placed()
    # The last day of each stage, and the first day of the next.
    edges = {
        FIRST: "initial",
        FIRST + ONE_DAY * 2: "initial",
        FIRST + ONE_DAY * 3: "development",
        FIRST + ONE_DAY * 6: "development",
        FIRST + ONE_DAY * 7: "mid",
        FIRST + ONE_DAY * 8: "mid",
        FIRST + ONE_DAY * 9: "late",
        LAST: "late",
    }
    for day, stage in edges.items():
        assert result[day].stage == stage, day


def test_a_stage_of_one_day_and_a_period_of_four_days():
    lengths = dict.fromkeys(module.GROWTH_STAGES, 1.0)
    result = module.place_stages(FIRST, FIRST + ONE_DAY * 3, lengths, what=WHAT)
    assert stage_list(result) == list(module.GROWTH_STAGES)
    assert result.tail == ()
    assert all(item.fraction == 1.0 for item in result.values())


def test_lengths_that_fill_the_period_exactly_leave_no_tail_and_cut_nothing():
    result = placed()
    assert result.tail == ()
    assert stage_list(result) == FILLED
    assert result.stages == dict(result)
    assert result[LAST] == module.StageDay(stage="late", day_in_stage=5, stage_length=5)


@pytest.mark.parametrize(
    ("short", "kept"),
    [
        (1, FILLED[:-1]),  # the harvest falls inside the late stage
        (5, FILLED[:9]),  # on the last day of the mid stage: no late day
        (9, FILLED[:5]),  # inside the development stage: no mid nor late day
        (TOTAL - 1, ["initial"]),  # the period holds only its sowing day
    ],
)
def test_lengths_longer_than_the_period_are_cut_at_the_harvest(short, kept):
    last = LAST - ONE_DAY * short
    result = placed(last)
    assert result.tail == ()
    assert sorted(result) == [FIRST + ONE_DAY * n for n in range(TOTAL - short)]
    assert max(result) == last
    assert stage_list(result) == kept
    # The stages are not shrunk: every placed day keeps its catalogue length
    # and its place in its stage, as in the period the lengths fill.
    whole = placed()
    for day, item in result.items():
        assert item == whole[day]


def test_a_stage_cut_at_the_harvest_keeps_its_whole_line_and_never_reaches_the_next_value():
    last = LAST - ONE_DAY * 2  # three of the five late days are placed
    result = placed(last)
    item = result[last]
    assert (item.stage, item.day_in_stage, item.stage_length) == ("late", 3, 5)
    assert item.fraction == pytest.approx(3 / 5)
    value = module.by_stage(item, INITIAL, MID, END)
    assert value == pytest.approx(MID + 3 / 5 * (END - MID))
    assert value != pytest.approx(END)


@pytest.mark.parametrize("extra", [1, 2, 9])
def test_lengths_shorter_than_the_period_leave_a_tail_of_exactly_the_days_to_the_harvest(
    extra,
):
    last = LAST + ONE_DAY * extra
    result = placed(last)
    # The four stages are placed whole, as in the period they fill.
    assert result.stages == placed().stages
    assert stage_list(result) == FILLED
    # The tail runs from the day after the late stage to the harvest.
    assert result.tail == tuple(LAST + ONE_DAY * n for n in range(1, extra + 1))
    assert result.tail[-1] == last
    # Every day of the period is a stage day or a tail day, never both.
    period = [FIRST + ONE_DAY * n for n in range((last - FIRST).days + 1)]
    assert sorted([*result, *result.tail]) == period
    assert not set(result) & set(result.tail)
    for day in result.tail:
        assert day not in result
        with pytest.raises(KeyError):
            result[day]


def test_a_period_crossing_29_february_has_one_more_tail_day_or_one_day_less_cut():
    # The same calendar dates, in a year without and a year with 29 February.
    plain_first, leap_first = dt.date(2002, 2, 20), dt.date(2004, 2, 20)
    plain_last, leap_last = dt.date(2002, 3, 10), dt.date(2004, 3, 10)
    plain = placed(plain_last, plain_first)
    leap = placed(leap_last, leap_first)
    assert dt.date(2004, 2, 29) in leap.stages
    assert len(leap.tail) == len(plain.tail) + 1
    assert stage_list(leap) == stage_list(plain) == FILLED
    # Cut: the period holds one day fewer than the lengths without the leap
    # day, and exactly their days with it.
    plain_cut = placed(dt.date(2002, 3, 4), plain_first)
    leap_cut = placed(dt.date(2004, 3, 4), leap_first)
    assert stage_list(plain_cut) == FILLED[:-1]
    assert stage_list(leap_cut) == FILLED
    assert plain_cut.tail == leap_cut.tail == ()


@pytest.mark.parametrize("bad", [0.0, -2.0, 2.5, float("nan"), float("inf"), True])
def test_a_length_that_is_not_whole_days_of_at_least_one_is_not_computable(bad):
    lengths = dict(LENGTHS, mid=bad)
    result = module.place_stages(FIRST, LAST, lengths, what=WHAT)
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "'fao56_stage_length_mid'" in result.detail
    assert "'fao56_stage_length_late'" not in result.detail
    assert "not a whole number of days" in result.detail


def test_a_period_that_ends_before_it_starts_or_a_stage_without_length_raises():
    # A stage without length: the caller answers it before, MISSING_INPUT with
    # the stage unknown (D79); reaching place_stages without it is a bug.
    with pytest.raises(ValueError, match="ends before it starts"):
        module.place_stages(FIRST, FIRST - ONE_DAY, LENGTHS, what=WHAT)
    lengths = {stage: LENGTHS[stage] for stage in module.GROWTH_STAGES[:-1]}
    with pytest.raises(ValueError, match="no length"):
        module.place_stages(FIRST, LAST, lengths, what=WHAT)


def test_stage_length_identifiers_are_one_per_stage_with_the_proposed_prefix():
    assert module.STAGE_LENGTH_PARAMETERS == {
        stage: f"fao56_stage_length_{stage}" for stage in module.GROWTH_STAGES
    }


def test_arguments_unchanged_and_second_call_equal():
    lengths = dict(LENGTHS)
    first = module.place_stages(FIRST, LAST, lengths, what=WHAT)
    assert lengths == LENGTHS
    assert module.place_stages(FIRST, LAST, lengths, what=WHAT) == first


# --- the interpolation ------------------------------------------------------------


def test_initial_and_mid_stages_take_their_value_on_every_day():
    for day, item in placed().items():
        value = module.by_stage(item, INITIAL, MID, END)
        if item.stage == "initial":
            assert value == INITIAL, day
        elif item.stage == "mid":
            assert value == MID, day


def test_development_and_late_stages_follow_a_straight_line_to_the_next_value():
    result = placed()
    for item in result.values():
        value = module.by_stage(item, INITIAL, MID, END)
        share = item.day_in_stage / item.stage_length
        if item.stage == "development":
            assert value == pytest.approx(INITIAL + share * (MID - INITIAL))
        elif item.stage == "late":
            assert value == pytest.approx(MID + share * (END - MID))
    # The line reaches the next value on the last day of its stage.
    by_day = [module.by_stage(result[day], INITIAL, MID, END) for day in sorted(result)]
    assert by_day[6] == pytest.approx(MID)
    assert by_day[-1] == pytest.approx(END)
    # The steps of each line are equal.
    development = by_day[2:7]
    steps = [after - before for before, after in zip(development, development[1:])]
    assert steps == pytest.approx([(MID - INITIAL) / 4] * 4)


def test_the_curve_written_out_day_by_day():
    # The same PLACEHOLDER curve, written out by hand: day n of the period.
    expected = (
        [INITIAL] * 3
        + [INITIAL + n / 4 * (MID - INITIAL) for n in (1, 2, 3, 4)]
        + [MID] * 2
        + [MID + n / 5 * (END - MID) for n in (1, 2, 3, 4, 5)]
    )
    result = placed()
    got = [module.by_stage(result[day], INITIAL, MID, END) for day in sorted(result)]
    assert got == pytest.approx(expected)


def test_only_the_values_the_stage_needs_are_read():
    missing = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER value missing")
    needs = {
        "initial": ("initial",),
        "development": ("initial", "mid"),
        "mid": ("mid",),
        "late": ("mid", "end"),
    }
    for item in placed().values():
        for absent in ("initial", "mid", "end"):
            values = {"initial": INITIAL, "mid": MID, "end": END, absent: missing}
            value = module.by_stage(
                item, values["initial"], values["mid"], values["end"]
            )
            if absent in needs[item.stage]:
                assert isinstance(value, Missing)
                assert value.reason == "MISSING_INPUT"
                assert value.detail == "PLACEHOLDER value missing"
            else:
                assert isinstance(value, float)


def test_both_values_missing_are_both_named():
    one = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER one")
    two = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER two")
    late = next(item for item in placed().values() if item.stage == "late")
    value = module.by_stage(late, INITIAL, one, two)
    assert value.detail == "PLACEHOLDER one; PLACEHOLDER two"


def test_proposed_cases_match_exposure_md():
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    section = text.split("## PROPOSED cases of the stages", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
