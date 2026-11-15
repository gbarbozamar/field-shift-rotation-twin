"""Targeted mutant-killing and boundary tests for living crop, stages, and fallow.

Covers:
- D78 stage allocation (``initial`` / ``development`` / ``mid`` / ``late``) and
  ``by_stage`` (``initial`` / ``mid`` / ``end``) in ``engine/water/stages.py``;
- D135 / D136 cut-at-harvest and tail days with no living crop in
  ``engine/water/stages.py`` and ``engine/water/living_crop.py``;
- D79 missing stage lengths and D137 exact crop scope lookup in
  ``engine/water/living_crop.py``;
- D110 / D111 / D115 / D116 fallow residue reduction and REW clamping in
  ``engine/water/fallow.py``;
- ``live_crop_by_day`` (issue #423 / #399) overlap, undated component, and
  lead-in handling in ``engine/water/living_crop.py``.

Every number, date, crop name, and parameter record here is PLACEHOLDER test
data, plainly not real: zero invented FAO-56 numbers and nothing from a source.
"""

from __future__ import annotations

import copy
import datetime as dt
import math

import pytest

from contracts.inputs.common import DateValue
from contracts.inputs.rotation_calendar import CalendarComponent, RotationCalendar
from contracts.results.models import Missing
from engine.calendar.repeat import Cycle, RepeatedComponent, RepeatedRotation
from engine.water import fallow, living_crop, stages
from engine.water import test_exposure as ep3_tests

ONE_DAY = dt.timedelta(days=1)

# PLACEHOLDER stage lengths (days) and curve values, plainly not real.
PLACEHOLDER_LENGTHS = {"initial": 3.0, "development": 4.0, "mid": 2.0, "late": 5.0}
PLACEHOLDER_INI, PLACEHOLDER_MID, PLACEHOLDER_END = 0.222, 0.888, 0.444

# PLACEHOLDER fallow numbers, plainly not the values of D110 or any source.
PLACEHOLDER_TEW = 4.44
PLACEHOLDER_REW = 2.22
PLACEHOLDER_REDUCTION = 0.0333
PLACEHOLDER_INCREMENT = 0.111
PLACEHOLDER_COVER = 0.444


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def every_day(first: dt.date, last: dt.date) -> list[dt.date]:
    days, day = [], first
    while day <= last:
        days.append(day)
        day += ONE_DAY
    return days


def lengths_catalogue(
    by_crop: dict[str, dict[str, float | None]],
    *,
    extra_records: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Build an unmarked PLACEHOLDER catalogue holding stage-length records."""
    records: dict[str, dict] = {}
    for crop, stage_map in by_crop.items():
        for stage, value in stage_map.items():
            parameter_id = stages.STAGE_LENGTH_PARAMETERS[stage]
            if value is None:
                record = ep3_tests.placeholder_record(
                    parameter_id, 1.0, ep3_tests.scope_of(crop)
                )
                record["value"] = None
                record["missing_reason"] = "PLACEHOLDER missing stage length"
                record["range"] = None
                record["range_missing_reason"] = "PLACEHOLDER"
            else:
                record = ep3_tests.placeholder_record(
                    parameter_id, value, ep3_tests.scope_of(crop)
                )
            records[f"{crop}_{stage}"] = ep3_tests.unmarked(record)
    if extra_records:
        records.update(ep3_tests.unmarked(extra_records))
    return records


def undated_calendar(
    start: str,
    end: str,
    specs: list[dict],
) -> RotationCalendar:
    """Build a RotationCalendar from a PLACEHOLDER template with custom components."""
    document = ep3_tests.calendar_document()
    template = document["components"][0]
    document["start_date"] = start
    document["end_date"] = end
    built = []
    for spec in specs:
        comp = copy.deepcopy(template)
        comp["component_id"] = f"PLACEHOLDER-component-{spec['name']}"
        comp["crop_id"] = ep3_tests.unmarked(ep3_tests.crop_word(spec["crop"]))
        if spec["start"].get("date") is not None:
            comp["start"]["date"] = spec["start"]["date"]
        else:
            comp["start"] = spec["start"]
        if spec["end"].get("date") is not None:
            comp["end"]["date"] = spec["end"]["date"]
        else:
            comp["end"] = spec["end"]
        comp["periods"] = []
        built.append(comp)
    document["components"] = built
    return RotationCalendar.model_validate(document)


# --- engine/water/stages.py: D78, D135, D136 ---------------------------------


def test_place_stages_exact_transitions_one_day_sloped_and_mapping_api():
    first = d("2001-09-01")
    # int lengths, including 1-day development and 1-day late (kills int vs float
    # and division-by-(stage_length - 1) mutants).
    lengths = {"initial": 2, "development": 1, "mid": 3, "late": 1}
    last = first + ONE_DAY * 6
    placed = stages.place_stages(first, last, lengths, what="PLACEHOLDER")
    assert isinstance(placed, stages.PlacedStages)
    assert placed.tail == ()
    assert len(placed) == 7
    assert list(placed.keys()) == every_day(first, last)
    assert [item.stage for item in placed.values()] == [
        "initial",
        "initial",
        "development",
        "mid",
        "mid",
        "mid",
        "late",
    ]
    assert list(placed.items()) == [(day, placed[day]) for day in every_day(first, last)]
    assert (first - ONE_DAY) not in placed
    assert (last + ONE_DAY) not in placed
    assert placed.get(last + ONE_DAY) is None

    # 1-day sloped stages reach the target endpoint immediately on their sole day.
    dev_day = placed[first + ONE_DAY * 2]
    assert dev_day == stages.StageDay(stage="development", day_in_stage=1, stage_length=1)
    assert dev_day.fraction == 1.0
    assert (
        stages.by_stage(dev_day, PLACEHOLDER_INI, PLACEHOLDER_MID, PLACEHOLDER_END)
        == pytest.approx(PLACEHOLDER_MID)
    )

    late_day = placed[last]
    assert late_day == stages.StageDay(stage="late", day_in_stage=1, stage_length=1)
    assert late_day.fraction == 1.0
    assert (
        stages.by_stage(late_day, PLACEHOLDER_INI, PLACEHOLDER_MID, PLACEHOLDER_END)
        == pytest.approx(PLACEHOLDER_END)
    )


@pytest.mark.parametrize(
    ("offset", "expected_stage", "expected_day_in_stage", "expected_length"),
    [
        (0, "initial", 1, 3),  # 1-day period: first == last
        (2, "initial", 3, 3),  # cut on exact end of initial
        (3, "development", 1, 4),  # cut on day 1 of development
        (6, "development", 4, 4),  # cut on exact end of development
        (7, "mid", 1, 2),  # cut on day 1 of mid
        (8, "mid", 2, 2),  # cut on exact end of mid
        (9, "late", 1, 5),  # cut on day 1 of late
        (12, "late", 4, 5),  # cut one day before late completes
    ],
)
def test_place_stages_d135_cut_at_harvest_on_all_stage_boundaries(
    offset, expected_stage, expected_day_in_stage, expected_length
):
    first = d("2001-09-01")
    last = first + ONE_DAY * offset
    placed = stages.place_stages(first, last, PLACEHOLDER_LENGTHS, what="PLACEHOLDER")
    assert isinstance(placed, stages.PlacedStages)
    assert placed.tail == ()
    assert len(placed) == offset + 1
    assert max(placed) == last
    cut_day = placed[last]
    assert cut_day == stages.StageDay(
        stage=expected_stage,
        day_in_stage=expected_day_in_stage,
        stage_length=expected_length,
    )
    val = stages.by_stage(cut_day, PLACEHOLDER_INI, PLACEHOLDER_MID, PLACEHOLDER_END)
    if expected_stage == "development" and expected_day_in_stage == 1:
        assert val == pytest.approx(
            PLACEHOLDER_INI + 0.25 * (PLACEHOLDER_MID - PLACEHOLDER_INI)
        )
        assert val != pytest.approx(PLACEHOLDER_INI)
        assert val != pytest.approx(PLACEHOLDER_MID)
    elif expected_stage == "late" and expected_day_in_stage == 1:
        assert val == pytest.approx(
            PLACEHOLDER_MID + 0.2 * (PLACEHOLDER_END - PLACEHOLDER_MID)
        )
        assert val != pytest.approx(PLACEHOLDER_MID)
        assert val != pytest.approx(PLACEHOLDER_END)


def test_place_stages_d136_single_and_multi_day_tail_excluded_from_mapping():
    first = d("2001-09-01")
    total = int(sum(PLACEHOLDER_LENGTHS.values()))
    for extra in (1, 3):
        last = first + ONE_DAY * (total - 1 + extra)
        placed = stages.place_stages(
            first, last, PLACEHOLDER_LENGTHS, what="PLACEHOLDER"
        )
        assert isinstance(placed, stages.PlacedStages)
        assert len(placed) == total
        assert len(placed.tail) == extra
        assert placed.tail[0] == first + ONE_DAY * total
        assert placed.tail[-1] == last
        for tail_day in placed.tail:
            assert tail_day not in placed
            assert placed.get(tail_day) is None
        assert sorted([*placed, *placed.tail]) == every_day(first, last)


@pytest.mark.parametrize(
    "bad",
    [0.0, -1.0, 0.5, 1.5, False, True, math.nan, math.inf, -math.inf, None, "3"],
)
def test_place_stages_rejects_invalid_stage_lengths(bad):
    lengths = dict(PLACEHOLDER_LENGTHS, initial=bad)
    result = stages.place_stages(
        d("2001-09-01"), d("2001-09-14"), lengths, what="PLACEHOLDER"
    )
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    assert "'fao56_stage_length_initial'" in result.detail


def test_place_stages_reports_multiple_invalid_stage_lengths_in_stage_order():
    lengths = dict(PLACEHOLDER_LENGTHS, initial=0.0, late=2.5)
    result = stages.place_stages(
        d("2001-09-01"), d("2001-09-14"), lengths, what="PLACEHOLDER"
    )
    assert isinstance(result, Missing)
    assert result.reason == "NOT_COMPUTABLE"
    pos_ini = result.detail.index("'fao56_stage_length_initial'")
    pos_late = result.detail.index("'fao56_stage_length_late'")
    assert pos_ini < pos_late
    assert "'fao56_stage_length_development'" not in result.detail
    assert "'fao56_stage_length_mid'" not in result.detail


@pytest.mark.parametrize("omitted", stages.GROWTH_STAGES)
def test_place_stages_raises_when_any_stage_key_is_absent_even_with_extra_key(omitted):
    lengths = {k: v for k, v in PLACEHOLDER_LENGTHS.items() if k != omitted}
    with pytest.raises(ValueError, match=omitted):
        stages.place_stages(
            d("2001-09-01"), d("2001-09-14"), lengths, what="PLACEHOLDER"
        )
    # Replacing the omitted stage with an unrelated extra key keeps len == 4.
    lengths_with_extra = {**lengths, "extra_stage": 2.0}
    with pytest.raises(ValueError, match=omitted):
        stages.place_stages(
            d("2001-09-01"), d("2001-09-14"), lengths_with_extra, what="PLACEHOLDER"
        )


def test_by_stage_d78_decreasing_constant_and_missing_order():
    # Decreasing and constant curves
    ini_hi, mid_eq, end_lo = 0.888, 0.555, 0.222
    placed = stages.place_stages(
        d("2001-09-01"), d("2001-09-14"), PLACEHOLDER_LENGTHS, what="PLACEHOLDER"
    )
    assert isinstance(placed, stages.PlacedStages)
    dev_values = [
        stages.by_stage(placed[day], ini_hi, mid_eq, end_lo)
        for day in sorted(placed)
        if placed[day].stage == "development"
    ]
    assert dev_values == pytest.approx(
        [ini_hi + n / 4 * (mid_eq - ini_hi) for n in (1, 2, 3, 4)]
    )
    assert all(
        stages.by_stage(item, 0.555, 0.555, 0.555) == pytest.approx(0.555)
        for item in placed.values()
    )

    # Development with both initial and mid missing preserves order & falls back to reason
    dev1 = placed[d("2001-09-04")]
    assert dev1.stage == "development"
    m_ini = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER ini")
    m_mid = Missing(reason="NOT_AVAILABLE", detail=None)
    got = stages.by_stage(dev1, m_ini, m_mid, PLACEHOLDER_END)
    assert got == Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER ini; NOT_AVAILABLE"
    )

    # Unused missing values never taint a stage that does not read them
    m_unused = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER unused")
    assert stages.by_stage(placed[d("2001-09-01")], ini_hi, m_unused, m_unused) == ini_hi
    assert stages.by_stage(dev1, ini_hi, mid_eq, m_unused) == pytest.approx(
        ini_hi + 0.25 * (mid_eq - ini_hi)
    )
    assert stages.by_stage(placed[d("2001-09-08")], m_unused, mid_eq, m_unused) == mid_eq
    assert stages.by_stage(placed[d("2001-09-10")], m_unused, mid_eq, end_lo) == pytest.approx(
        mid_eq + 0.2 * (end_lo - mid_eq)
    )


# --- engine/water/living_crop.py: D79, D135, D136, D137 ----------------------


def test_live_crop_days_d79_missing_lengths_precedence_and_single_day_period():
    sowing = d("2031-01-01")
    harvest = d("2031-02-24")

    # All four stages missing -> all four named in detail in order
    all_missing = {
        stage: Missing(reason="NOT_DECLARED", detail=f"PLACEHOLDER {stage}")
        for stage in stages.GROWTH_STAGES
    }
    res_all = living_crop.live_crop_days(
        sowing, harvest, all_missing, what="PLACEHOLDER period"
    )
    assert isinstance(res_all, Missing)
    assert res_all.reason == "MISSING_INPUT"
    assert "PLACEHOLDER period" in res_all.detail
    assert "D79" in res_all.detail
    for stage in stages.GROWTH_STAGES:
        assert stages.STAGE_LENGTH_PARAMETERS[stage] in res_all.detail
        assert f"NOT_DECLARED: PLACEHOLDER {stage}" in res_all.detail

    # Missing takes precedence over non-whole stage length (kills swapping checks)
    mixed = dict(
        PLACEHOLDER_LENGTHS,
        initial=Missing(reason="NOT_DECLARED", detail="PLACEHOLDER"),
        mid=2.5,
    )
    res_mixed = living_crop.live_crop_days(
        sowing, harvest, mixed, what="PLACEHOLDER period"
    )
    assert isinstance(res_mixed, Missing)
    assert res_mixed.reason == "MISSING_INPUT"
    assert "D79" in res_mixed.detail

    # Absent stage key raises ValueError even when extra key gives len == 4
    for omitted in stages.GROWTH_STAGES:
        absent = {k: v for k, v in PLACEHOLDER_LENGTHS.items() if k != omitted}
        absent["extra"] = 2.0
        with pytest.raises(ValueError, match=omitted):
            living_crop.live_crop_days(sowing, harvest, absent, what="PLACEHOLDER")

    # Single-day period (sowing == harvest) succeeds with 1 live day and empty tail
    one_day = living_crop.live_crop_days(
        sowing, sowing, PLACEHOLDER_LENGTHS, what="PLACEHOLDER"
    )
    assert isinstance(one_day, living_crop.LiveCropDays)
    assert one_day.days == {sowing: True}
    assert one_day.is_live(sowing) is True
    assert one_day.stages.tail == ()
    with pytest.raises(ValueError):
        one_day.is_live(sowing - ONE_DAY)
    with pytest.raises(ValueError):
        one_day.is_live(sowing + ONE_DAY)


def test_live_crop_days_of_crop_d137_exact_scope_d79_and_unrelated_kcb_missing():
    crop = ep3_tests.unmarked(ep3_tests.crop_word("crop-a"))
    sowing, harvest = d("2031-01-01"), d("2031-01-20")

    # Empty scope {} or stage-scoped {"crop": crop, "stage": "initial"} must NOT match
    wrong_scope_records = {}
    for stage, parameter_id in stages.STAGE_LENGTH_PARAMETERS.items():
        wrong_scope_records[f"empty_{stage}"] = ep3_tests.placeholder_record(
            parameter_id, PLACEHOLDER_LENGTHS[stage], {}
        )
        wrong_scope_records[f"staged_{stage}"] = ep3_tests.placeholder_record(
            parameter_id, PLACEHOLDER_LENGTHS[stage], {"crop": crop, "stage": stage}
        )
    res_wrong = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=ep3_tests.unmarked(wrong_scope_records)
    )
    assert isinstance(res_wrong, Missing)
    assert res_wrong.reason == "MISSING_INPUT"
    assert "D79" in res_wrong.detail

    # Partial missing (late record has value=None) leaves period MISSING_INPUT naming D79
    partial = lengths_catalogue(
        {"crop-a": {"initial": 3.0, "development": 4.0, "mid": 2.0, "late": None}}
    )
    res_partial = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=partial
    )
    assert isinstance(res_partial, Missing)
    assert res_partial.reason == "MISSING_INPUT"
    assert stages.STAGE_LENGTH_PARAMETERS["late"] in res_partial.detail
    assert stages.STAGE_LENGTH_PARAMETERS["initial"] not in res_partial.detail

    # Non-whole length in catalogue -> NOT_COMPUTABLE
    non_whole = lengths_catalogue(
        {"crop-a": {"initial": 3.0, "development": 4.0, "mid": 2.5, "late": 5.0}}
    )
    res_bad = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=non_whole
    )
    assert isinstance(res_bad, Missing)
    assert res_bad.reason == "NOT_COMPUTABLE"

    # Unrelated missing basal_crop_coefficient / maximum_root_depth does NOT stop live days
    kcb_missing = ep3_tests.placeholder_record(
        "basal_crop_coefficient", 0.555, ep3_tests.scope_of("crop-a:initial")
    )
    kcb_missing["value"] = None
    kcb_missing["missing_reason"] = "PLACEHOLDER missing kcb"
    kcb_missing["range"] = None
    kcb_missing["range_missing_reason"] = "PLACEHOLDER"
    root_missing = ep3_tests.placeholder_record(
        "maximum_root_depth", 1.11, ep3_tests.scope_of("crop-a")
    )
    root_missing["value"] = None
    root_missing["missing_reason"] = "PLACEHOLDER missing root"
    root_missing["range"] = None
    root_missing["range_missing_reason"] = "PLACEHOLDER"
    valid_with_kcb_missing = lengths_catalogue(
        {"crop-a": PLACEHOLDER_LENGTHS},
        extra_records={"kcb": kcb_missing, "root": root_missing},
    )
    res_ok = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=valid_with_kcb_missing
    )
    res_ok_on = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=valid_with_kcb_missing, on=harvest
    )
    assert isinstance(res_ok, living_crop.LiveCropDays)
    assert res_ok == res_ok_on
    assert len(res_ok.stages) == 14
    assert len(res_ok.stages.tail) == 6

    # Duplicate stage-length records for the same (id, scope) -> MISSING_INPUT (D79)
    dup_records = lengths_catalogue(
        {"crop-a": PLACEHOLDER_LENGTHS},
        extra_records={
            "dup_initial": ep3_tests.placeholder_record(
                stages.STAGE_LENGTH_PARAMETERS["initial"],
                3.0,
                ep3_tests.scope_of("crop-a"),
            )
        },
    )
    res_dup = living_crop.live_crop_days_of_crop(
        sowing, harvest, crop, parameters=dup_records
    )
    assert isinstance(res_dup, Missing)
    assert res_dup.reason == "MISSING_INPUT"
    assert "D79" in res_dup.detail


# --- engine/water/fallow.py: D110, D111, D115, D116 --------------------------


def test_mulched_tew_d110_d186_boundaries_and_over_reduction_not_clamped():
    # Exact bounds residue_cover=0.0 and residue_cover=1.0
    assert (
        fallow.mulched_total_evaporable_water(
            PLACEHOLDER_TEW,
            0.0,
            reduction_per_increment=PLACEHOLDER_REDUCTION,
            cover_increment=PLACEHOLDER_INCREMENT,
        )
        == PLACEHOLDER_TEW
    )
    at_one = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        1.0,
        reduction_per_increment=PLACEHOLDER_REDUCTION,
        cover_increment=PLACEHOLDER_INCREMENT,
    )
    assert at_one == pytest.approx(
        PLACEHOLDER_TEW * (1 - PLACEHOLDER_REDUCTION / PLACEHOLDER_INCREMENT)
    )

    # Just outside [0, 1] and <= 0 / < 0 boundaries
    for bad_cover in (-1e-6, 1.0 + 1e-6):
        res = fallow.mulched_total_evaporable_water(
            PLACEHOLDER_TEW,
            bad_cover,
            reduction_per_increment=PLACEHOLDER_REDUCTION,
            cover_increment=PLACEHOLDER_INCREMENT,
        )
        assert isinstance(res, Missing) and res.reason == "NOT_COMPUTABLE"

    for bad_inc in (0.0, -1e-6):
        res = fallow.mulched_total_evaporable_water(
            PLACEHOLDER_TEW,
            PLACEHOLDER_COVER,
            reduction_per_increment=PLACEHOLDER_REDUCTION,
            cover_increment=bad_inc,
        )
        assert isinstance(res, Missing) and res.reason == "NOT_COMPUTABLE"

    bad_red = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        PLACEHOLDER_COVER,
        reduction_per_increment=-1e-6,
        cover_increment=PLACEHOLDER_INCREMENT,
    )
    assert isinstance(bad_red, Missing) and bad_red.reason == "NOT_COMPUTABLE"

    # Non-positive TEW (0.0 or negative) -> NOT_COMPUTABLE
    for non_pos_tew in (0.0, -1.11):
        res = fallow.mulched_total_evaporable_water(
            non_pos_tew,
            PLACEHOLDER_COVER,
            reduction_per_increment=PLACEHOLDER_REDUCTION,
            cover_increment=PLACEHOLDER_INCREMENT,
        )
        assert isinstance(res, Missing) and res.reason == "NOT_COMPUTABLE"

    # Over-reduction (< 0) is NOT_COMPUTABLE, never clamped to 0
    over = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        0.888,
        reduction_per_increment=0.222,
        cover_increment=0.111,
    )
    assert isinstance(over, Missing)
    assert over.reason == "NOT_COMPUTABLE"
    assert "leaves no evaporable water" in over.detail

    # Non-finite values across all 4 operands
    for kwargs in (
        {"total_evaporable_water": math.nan},
        {"total_evaporable_water": -math.inf},
        {"residue_cover": math.inf},
        {"reduction_per_increment": math.nan},
        {"cover_increment": math.inf},
    ):
        params = {
            "total_evaporable_water": PLACEHOLDER_TEW,
            "residue_cover": PLACEHOLDER_COVER,
            "reduction_per_increment": PLACEHOLDER_REDUCTION,
            "cover_increment": PLACEHOLDER_INCREMENT,
            **kwargs,
        }
        res = fallow.mulched_total_evaporable_water(
            params["total_evaporable_water"],
            params["residue_cover"],
            reduction_per_increment=params["reduction_per_increment"],
            cover_increment=params["cover_increment"],
        )
        assert isinstance(res, Missing) and res.reason == "NOT_COMPUTABLE"

    # Multiple Missing operands -> all named; Missing takes precedence over NaN
    m = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER")
    both = fallow.mulched_total_evaporable_water(
        m,
        math.nan,
        reduction_per_increment=m,
        cover_increment=PLACEHOLDER_INCREMENT,
    )
    assert isinstance(both, Missing) and both.reason == "MISSING_INPUT"
    assert "total_evaporable_water (NOT_DECLARED)" in both.detail
    assert "reduction_per_increment (NOT_DECLARED)" in both.detail


def test_rew_not_above_tew_clamping_composition_and_precedence():
    # Exact equality boundary, above, and below
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, PLACEHOLDER_REW)
        == PLACEHOLDER_REW
    )
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_TEW, PLACEHOLDER_REW)
        == PLACEHOLDER_REW
    )
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, PLACEHOLDER_TEW)
        == PLACEHOLDER_REW
    )

    # Composition: mulch lowers TEW below REW -> REW clamped to reduced TEW
    tew_reduced = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        0.666,
        reduction_per_increment=0.111,
        cover_increment=0.111,
    )
    assert isinstance(tew_reduced, float) and tew_reduced < PLACEHOLDER_REW
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, tew_reduced)
        == tew_reduced
    )

    # Composition: over-mulched TEW (NOT_COMPUTABLE) passes through unchanged
    tew_over = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        1.0,
        reduction_per_increment=0.222,
        cover_increment=0.111,
    )
    assert isinstance(tew_over, Missing) and tew_over.reason == "NOT_COMPUTABLE"
    assert fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, tew_over) == tew_over

    # Precedence: NOT_COMPUTABLE TEW beats MISSING_INPUT REW
    rew_missing = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER rew")
    assert (
        fallow.readily_evaporable_water_not_above(rew_missing, tew_over) == tew_over
    )

    # NOT_COMPUTABLE on REW is NOT passed through: becomes MISSING_INPUT naming it
    rew_nc = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER rew nc")
    got_rew_nc = fallow.readily_evaporable_water_not_above(rew_nc, PLACEHOLDER_TEW)
    assert isinstance(got_rew_nc, Missing)
    assert got_rew_nc.reason == "MISSING_INPUT"
    assert "readily_evaporable_water (NOT_COMPUTABLE)" in got_rew_nc.detail

    # Both Missing -> both named
    tew_missing = Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER tew")
    got_both = fallow.readily_evaporable_water_not_above(rew_missing, tew_missing)
    assert isinstance(got_both, Missing)
    assert got_both.reason == "MISSING_INPUT"
    assert "readily_evaporable_water (NOT_DECLARED)" in got_both.detail
    assert "total_evaporable_water (NOT_AVAILABLE)" in got_both.detail


def test_following_crop_generator_reuse_and_undated_boundaries():
    s1 = d("2001-08-10")
    s2 = d("2002-01-05")
    day = d("2001-08-01")
    # Generator inputs must be materialized so multiple lookups work (kills dropping list/sorted)
    sow_gen = (item for item in ((s1, "crop-a"), (s2, "crop-b")))
    undated_gen = (
        item for item in ((s2 + ONE_DAY, s2 + ONE_DAY * 10, "PLACEHOLDER-later-undated"),)
    )
    following = fallow.following_crop(sow_gen, undated_gen)
    assert following(day) == "crop-a"
    assert following(day) == "crop-a"
    assert following(s1) == "crop-b"

    # Undated with last == day and no dated sowings -> NO_FOLLOWING_CROP (kills last >= day)
    no_later = fallow.following_crop([], [(day - ONE_DAY, day, "PLACEHOLDER-ended")])
    res_no_later = no_later(day)
    assert isinstance(res_no_later, Missing)
    assert res_no_later.detail == fallow.NO_FOLLOWING_CROP

    # Multiple undated components sorted and deduplicated in SOWING_NOT_KNOWN
    multi_undated = fallow.following_crop(
        [(s1, "crop-a")],
        [
            (day + ONE_DAY, s1, "PLACEHOLDER-z"),
            (day, s1, "PLACEHOLDER-a"),
            (day, s1, "PLACEHOLDER-a"),
        ],
    )
    res_multi = multi_undated(day)
    assert isinstance(res_multi, Missing)
    assert res_multi.reason == "MISSING_INPUT"
    assert res_multi.detail == (
        f"{fallow.SOWING_NOT_KNOWN}: component(s) 'PLACEHOLDER-a', 'PLACEHOLDER-z'"
    )

    # Three sowings on the same date (2 same crop, 1 different) + non-blocking undated
    three = fallow.following_crop(
        [(s1, "crop-a"), (s1, "crop-a"), (s1, "crop-b")],
        [(s1 + ONE_DAY, s2, "PLACEHOLDER-after")],
    )
    res_three = three(day)
    assert isinstance(res_three, Missing)
    assert res_three.reason == "NOT_COMPUTABLE"
    assert res_three.detail == fallow.TWO_FOLLOWING_CROPS


# --- engine/water/living_crop.py: live_crop_by_day (#423), overlap/undated/lead-in


def test_repeat_calendar_over_record_ag_year_month_boundaries():
    # Start month is July (7): June 30 belongs to previous ag year, July 1 to current.
    assert living_crop._ag_year_of(d("2001-06-30"), 7) == 2000
    assert living_crop._ag_year_of(d("2001-07-01"), 7) == 2001
    assert living_crop._ag_year_of(d("2002-06-30"), 7) == 2001

    repeated = living_crop.repeat_calendar_over_record(
        ep3_tests.two_year_calendar(), d("2001-06-30"), d("2002-07-01")
    )
    assert repeated.ag_years == (2000, 2001, 2002)

    with pytest.raises(ValueError, match="did not repeat"):
        living_crop.repeat_calendar_over_record(
            ep3_tests.calendar_without_start_month(), d("2001-07-01"), d("2002-06-30")
        )


def test_component_of_day_single_day_edges_described_from_and_missing_date_texts():
    base_cal = ep3_tests.calendar()
    one_day = d("2001-09-15")

    comp_single = CalendarComponent.model_construct(
        component_id="PLACEHOLDER-single",
        crop_id="crop-a",
        start=DateValue.model_construct(date=one_day),
        end=DateValue.model_construct(date=one_day),
        periods=(),
    )
    # Same missing on start & end vs different missing (detail=None vs missing=None)
    shared_missing = ep3_tests.calendar_without_start_month().ag_year_start.missing
    comp_same_missing = CalendarComponent.model_construct(
        component_id="PLACEHOLDER-same-missing",
        crop_id="crop-b",
        start=DateValue.model_construct(date=None, missing=shared_missing),
        end=DateValue.model_construct(date=None, missing=shared_missing),
        periods=(),
    )
    comp_diff_missing = CalendarComponent.model_construct(
        component_id="PLACEHOLDER-diff-missing",
        crop_id="crop-b",
        start=DateValue.model_construct(
            date=None, missing=Missing(reason="NOT_DECLARED", detail=None)
        ),
        end=DateValue.model_construct(date=None, missing=None),
        periods=(),
    )
    calendar = RotationCalendar.model_construct(
        case_id=base_cal.case_id,
        field_id=base_cal.field_id,
        ag_year_start=base_cal.ag_year_start,
        start_date=base_cal.start_date,
        end_date=base_cal.end_date,
        components=[comp_single, comp_same_missing, comp_diff_missing],
        feasibility=base_cal.feasibility,
    )

    rc_single = RepeatedComponent(
        component_id="PLACEHOLDER-single",
        crop_id="crop-a",
        cycle=0,
        start=one_day,
        end=one_day,
        calendar_start=d("2001-07-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_same_c0 = RepeatedComponent(
        component_id="PLACEHOLDER-same-missing",
        crop_id="crop-b",
        cycle=0,
        start=None,
        end=None,
        calendar_start=d("2001-11-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2001-11-10"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    # Duplicate component_id in cycle 1 overlapping window -> deduplicated once
    rc_same_c1 = RepeatedComponent(
        component_id="PLACEHOLDER-same-missing",
        crop_id="crop-b",
        cycle=1,
        start=None,
        end=None,
        calendar_start=d("2001-11-05"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2001-11-15"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_diff = RepeatedComponent(
        component_id="PLACEHOLDER-diff-missing",
        crop_id="crop-b",
        cycle=0,
        start=None,
        end=None,
        calendar_start=d("2001-11-08"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2001-11-20"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_pre = RepeatedComponent(
        component_id="PLACEHOLDER-single",
        crop_id="crop-a",
        cycle=0,
        start=d("2001-06-25"),
        end=d("2001-07-02"),
        calendar_start=d("2001-06-25"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_overlap_undated = RepeatedComponent(
        component_id="PLACEHOLDER-single",
        crop_id="crop-a",
        cycle=0,
        start=d("2001-11-04"),
        end=d("2001-11-05"),
        calendar_start=d("2001-07-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_overlap_undated_2 = RepeatedComponent(
        component_id="PLACEHOLDER-single",
        crop_id="crop-a",
        cycle=0,
        start=d("2001-11-07"),
        end=d("2001-11-07"),
        calendar_start=d("2001-07-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
    rc_overlap_undated_3 = RepeatedComponent(
        component_id="PLACEHOLDER-single-2",
        crop_id="crop-b",
        cycle=0,
        start=d("2001-11-07"),
        end=d("2001-11-07"),
        calendar_start=d("2001-07-01"),
        calendar_end=d("2002-06-30"),
        cycle_last_day=d("2002-06-30"),
        periods=(),
        leap_day_moved=False,
        ends_after_record=False,
    )
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
        components=(
            rc_pre,
            rc_single,
            rc_overlap_undated,
            rc_overlap_undated_2,
            rc_overlap_undated_3,
            rc_same_c0,
            rc_same_c1,
            rc_diff,
        ),
    )
    comp_of = living_crop.component_of_day(calendar, repeated)

    # described_from boundary: 2001-07-01 is described (covered by rc_pre), while
    # 2001-06-30 is CROP_UNKNOWN even though rc_pre spans it (kills swapping checks).
    assert comp_of(d("2001-07-01")) == rc_pre
    before = comp_of(d("2001-06-30"))
    assert isinstance(before, Missing) and before.detail == living_crop.CROP_UNKNOWN

    # Single-day component exact boundaries
    assert comp_of(one_day - ONE_DAY) is None
    assert comp_of(one_day) == rc_single
    assert comp_of(one_day + ONE_DAY) is None

    # Dated component(s) take precedence over undated components on the same day
    assert comp_of(d("2001-11-05")) == rc_overlap_undated
    assert comp_of(d("2001-11-07")) == Missing(
        reason="NOT_COMPUTABLE", detail=living_crop.CROPS_OVERLAP
    )

    # Same missing grouped as "start and end date ..." and deduplicated across cycles
    m_same = comp_of(d("2001-11-06"))
    assert isinstance(m_same, Missing)
    assert m_same.detail == (
        f"{living_crop.CROP_DATES_MISSING}: component 'PLACEHOLDER-same-missing' "
        "(start and end date NOT_DECLARED: PLACEHOLDER)"
    )

    # Both undated components covering 2001-11-09 -> both named, different reasons formatted
    m_both = comp_of(d("2001-11-09"))
    assert isinstance(m_both, Missing)
    assert "component 'PLACEHOLDER-same-missing' (start and end date" in m_both.detail
    assert (
        "component 'PLACEHOLDER-diff-missing' (start date NOT_DECLARED; end date no reason given)"
        in m_both.detail
    )


def test_live_crop_by_day_overlap_single_boundary_repeated_cycles_and_three_crops():
    # Two components touching on a single day (2001-12-01) and a third component
    # overlapping on 2001-12-01..2001-12-03, repeated across a 2-year record.
    calendar = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2032-06-30",
        [
            ("a", "crop-a", "2031-11-01", "2031-12-01"),
            ("b", "crop-b", "2031-12-01", "2031-12-20"),
            ("c", "crop-a", "2031-12-01", "2031-12-03"),
        ],
    )
    params = lengths_catalogue(
        {
            "crop-a": {"initial": 2.0, "development": 2.0, "mid": 2.0, "late": 2.0},
            "crop-b": {"initial": 2.0, "development": 2.0, "mid": 2.0, "late": 2.0},
        }
    )
    flags = living_crop.live_crop_by_day(
        calendar, d("2001-07-01"), d("2003-06-30"), parameters=params
    )
    overlap = Missing(reason="NOT_COMPUTABLE", detail=living_crop.CROPS_OVERLAP)
    # Cycle 0: a runs 2001-11-01..2001-12-01 (8 live days, tail Nov 9..Dec 1)
    assert flags[d("2001-11-01")] is True
    assert flags[d("2001-11-08")] is True
    assert flags[d("2001-11-09")] is False
    assert flags[d("2001-11-30")] is False  # day before overlap
    assert flags[d("2001-12-01")] == overlap  # 3 crops overlap on boundary day
    assert flags[d("2001-12-03")] == overlap  # 2 crops overlap (b and c)
    assert flags[d("2001-12-04")] is True  # b alone, 4th day of 8 live days
    assert flags[d("2001-12-08")] is True  # b's 8th day
    assert flags[d("2001-12-09")] is False  # b's tail
    # Cycle 1: repeats in 2002-2003
    assert flags[d("2002-11-30")] is False
    assert flags[d("2002-12-01")] == overlap
    assert flags[d("2002-12-04")] is True


def test_live_crop_by_day_undated_window_and_dated_precedence():
    missing_date = ep3_tests.calendar_without_start_month().ag_year_start.missing.model_dump()
    # Dated component covering 2001-11-01..2001-11-20, plus undated component missing end
    # starting 2001-11-15 (so its window is 2001-11-15..2002-06-30).
    calendar = undated_calendar(
        "2031-07-01",
        "2032-06-30",
        [
            {
                "name": "dated",
                "crop": "crop-a",
                "start": {"date": "2031-11-01"},
                "end": {"date": "2031-11-20"},
            },
            {
                "name": "open-end",
                "crop": "crop-b",
                "start": {"date": "2031-11-15"},
                "end": {"date": None, "missing": missing_date},
            },
        ],
    )
    params = lengths_catalogue(
        {
            "crop-a": {"initial": 2.0, "development": 2.0, "mid": 2.0, "late": 2.0},
            "crop-b": {"initial": 2.0, "development": 2.0, "mid": 2.0, "late": 2.0},
        }
    )
    flags = living_crop.live_crop_by_day(
        calendar, d("2001-07-01"), d("2002-06-30"), parameters=params
    )
    # Before dated and undated -> fallow
    assert flags[d("2001-10-31")] is False
    # Dated component wins over undated on 2001-11-15..2001-11-20 (dated tail)
    assert flags[d("2001-11-01")] is True
    assert flags[d("2001-11-08")] is True
    assert flags[d("2001-11-09")] is False
    assert flags[d("2001-11-15")] is False
    assert flags[d("2001-11-20")] is False
    # After dated ends, undated component makes 2001-11-21..2002-06-30 MISSING_INPUT
    for day in (d("2001-11-21"), d("2002-06-30")):
        flag = flags[day]
        assert isinstance(flag, Missing)
        assert flag.reason == "MISSING_INPUT"
        assert flag.detail.startswith(living_crop.CROP_DATES_MISSING)
        assert "PLACEHOLDER-component-open-end" in flag.detail
        assert "end date NOT_DECLARED" in flag.detail

    # Missing start date: window is [calendar_start, end]
    cal_open_start = undated_calendar(
        "2031-07-01",
        "2032-06-30",
        [
            {
                "name": "open-start",
                "crop": "crop-b",
                "start": {"date": None, "missing": missing_date},
                "end": {"date": "2031-09-10"},
            }
        ],
    )
    flags_open_start = living_crop.live_crop_by_day(
        cal_open_start, d("2001-07-01"), d("2002-06-30"), parameters=params
    )
    for day in (d("2001-07-01"), d("2001-09-10")):
        flag = flags_open_start[day]
        assert isinstance(flag, Missing) and flag.reason == "MISSING_INPUT"
        assert "PLACEHOLDER-component-open-start" in flag.detail
        assert "start date NOT_DECLARED" in flag.detail
    assert flags_open_start[d("2001-09-11")] is False


def test_live_crop_by_day_lead_in_tail_split_cut_missing_and_overlap():
    # Crossing calendar phased by 1: q (crop-b) is sown 2001-05-20 (before record_start
    # 2001-07-01, 42 pre-record days: May 20..June 30) and harvested 2001-11-25.
    moved = ep3_tests.phase_calendar(ep3_tests.crossing_calendar(), 1)
    first, last = d("2001-07-01"), d("2002-06-30")

    # Case A: 40 live days -> maturity ends 2001-06-28 (before record_start); every day
    # of lead-in q inside record (July 1..Nov 25) is False (tail), NOT counted from July 1.
    short_q = lengths_catalogue(
        {
            "crop-a": PLACEHOLDER_LENGTHS,
            "crop-b": {"initial": 10.0, "development": 10.0, "mid": 10.0, "late": 10.0},
        }
    )
    flags_tail = living_crop.live_crop_by_day(moved, first, last, parameters=short_q)
    assert all(flags_tail[day] is False for day in every_day(first, d("2001-11-25")))

    # Case B: 45 live days -> May 20 + 44 days = July 3 (first 3 days of record are True,
    # July 4..Nov 25 are False).
    split_q = lengths_catalogue(
        {
            "crop-a": PLACEHOLDER_LENGTHS,
            "crop-b": {"initial": 10.0, "development": 10.0, "mid": 10.0, "late": 15.0},
        }
    )
    flags_split = living_crop.live_crop_by_day(moved, first, last, parameters=split_q)
    assert flags_split[d("2001-07-01")] is True
    assert flags_split[d("2001-07-03")] is True
    assert flags_split[d("2001-07-04")] is False
    assert flags_split[d("2001-11-25")] is False

    # Case C: 9999 live days -> cut at harvest: every day July 1..Nov 25 is True,
    # Nov 26 (fallow) is False.
    long_q = lengths_catalogue(
        {
            "crop-a": PLACEHOLDER_LENGTHS,
            "crop-b": {
                "initial": 9999.0,
                "development": 9999.0,
                "mid": 9999.0,
                "late": 9999.0,
            },
        }
    )
    flags_cut = living_crop.live_crop_by_day(moved, first, last, parameters=long_q)
    assert all(flags_cut[day] is True for day in every_day(first, d("2001-11-25")))
    assert flags_cut[d("2001-11-26")] is False

    # Case D: missing stage length for crop-b (D79) -> lead-in days are MISSING_INPUT,
    # Nov 26 fallow is False, and r (crop-a, Jan 10) is True.
    missing_q = lengths_catalogue({"crop-a": PLACEHOLDER_LENGTHS})
    flags_miss = living_crop.live_crop_by_day(moved, first, last, parameters=missing_q)
    for day in (first, d("2001-11-25")):
        flag = flags_miss[day]
        assert isinstance(flag, Missing) and flag.reason == "MISSING_INPUT"
        assert "D79" in flag.detail
    assert flags_miss[d("2001-11-26")] is False
    assert flags_miss[d("2002-01-10")] is True

    # Case E: two lead-in components overlapping inside the record -> CROPS_OVERLAP on
    # the overlap days, then single lead-in component until its harvest.
    overlap_cal = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2033-05-31",
        [
            ("lead-a", "crop-b", "2032-05-20", "2032-11-25"),
            ("lead-b", "crop-a", "2032-06-20", "2032-08-01"),
            ("later", "crop-a", "2033-01-10", "2033-05-31"),
        ],
    )
    moved_overlap = ep3_tests.phase_calendar(overlap_cal, 1)
    flags_overlap = living_crop.live_crop_by_day(
        moved_overlap, first, last, parameters=long_q
    )
    overlap = Missing(reason="NOT_COMPUTABLE", detail=living_crop.CROPS_OVERLAP)
    for day in every_day(d("2001-07-01"), d("2001-08-01")):
        assert flags_overlap[day] == overlap
    assert flags_overlap[d("2001-08-02")] is True
    assert flags_overlap[d("2001-11-25")] is True
    assert flags_overlap[d("2001-11-26")] is False


def test_live_crop_by_day_single_day_record_and_post_record_component():
    # Single-day record (kills record_end <= record_start and off-by-one range)
    day = d("2001-08-10")
    params = lengths_catalogue({"crop-a": PLACEHOLDER_LENGTHS, "crop-b": PLACEHOLDER_LENGTHS})
    assert living_crop.live_crop_by_day(
        ep3_tests.two_year_calendar(), day, day, parameters=params
    ) == {day: True}
    assert living_crop.live_crop_by_day(
        ep3_tests.calendar_without_start_month(), day, day, parameters=params
    ) == {day: Missing(reason="MISSING_INPUT", detail=living_crop.START_MONTH_UNKNOWN)}
    assert living_crop.live_crop_by_day(
        ep3_tests.infeasible_calendar(), day, day, parameters=params
    ) == {day: Missing(reason="NOT_COMPUTABLE", detail=living_crop.CALENDAR_INFEASIBLE)}

    # Component starting inside record and ending after record_end: days up to record_end
    # follow its full [sowing, harvest] stage placement and dict ends at record_end.
    cal = ep3_tests.rotation_calendar(
        "2031-07-01",
        "2032-07-20",
        [("tail-end", "crop-a", "2032-06-20", "2032-07-20")],
    )
    rec_start, rec_end = d("2001-07-01"), d("2002-06-30")
    flags = living_crop.live_crop_by_day(cal, rec_start, rec_end, parameters=params)
    assert max(flags) == rec_end
    assert flags[d("2002-06-19")] is False
    assert flags[d("2002-06-20")] is True
    assert flags[d("2002-06-30")] is True  # 11th day of 14 live days


def test_live_crop_over_record_keys_periods_by_cycle_and_component_id():
    # Two components in cycle 0 plus the first component in cycle 1 keep distinct periods.
    cal = ep3_tests.two_year_calendar()
    params = lengths_catalogue({"crop-a": PLACEHOLDER_LENGTHS, "crop-b": PLACEHOLDER_LENGTHS})
    over = living_crop.live_crop_over_record(
        cal, d("2001-07-01"), d("2005-06-30"), parameters=params
    )
    c0_w = over.component(d("2001-08-10"))
    c0_x = over.component(d("2002-01-05"))
    c1_w = over.component(d("2003-08-10"))
    assert isinstance(c0_w, RepeatedComponent)
    assert isinstance(c0_x, RepeatedComponent)
    assert isinstance(c1_w, RepeatedComponent)
    d_c0_w = over.live_days(c0_w, d("2001-08-10"))
    d_c0_x = over.live_days(c0_x, d("2002-01-05"))
    d_c1_w = over.live_days(c1_w, d("2003-08-10"))
    assert isinstance(d_c0_w, living_crop.LiveCropDays)
    assert isinstance(d_c0_x, living_crop.LiveCropDays)
    assert isinstance(d_c1_w, living_crop.LiveCropDays)
    assert d_c0_w.sowing == d("2001-08-10")
    assert d_c0_x.sowing == d("2002-01-05")
    assert d_c1_w.sowing == d("2003-08-10")
    assert over.is_live(d("2001-08-23")) is True
    assert over.is_live(d("2001-08-24")) is False
    assert over.is_live(d("2002-01-18")) is True
    assert over.is_live(d("2002-01-19")) is False
    assert over.is_live(d("2003-08-23")) is True
    assert over.is_live(d("2003-08-24")) is False
