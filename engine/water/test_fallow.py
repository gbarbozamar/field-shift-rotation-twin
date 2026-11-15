"""Acceptance test of ``fallow.py``, unit l1/water-fallow-residue (issue #217).
Unit l1/water-ep3-repeat-d47 (issue #253) gives ``following_crop`` the sowings
of the repeated rotation as plain dates, in place of a calendar.

The cases are PROPOSED (blueprint section 3.7) and are listed in
``EXPOSURE.md`` under "PROPOSED cases of the fallow"; a test checks that the
two lists agree. Every number written here is a PLACEHOLDER, plainly not real:
none is a value of the method (not the "5 % for each 10 %" of D110, not a
cover of D115), none comes from a source. The fallow day inside EP3 is checked
in ``test_exposure.py``.

Run from the repository root: ``py -3.12 -m pytest engine/water/test_fallow.py``.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water import fallow

HERE = Path(__file__).parent
EXAMPLE = (
    HERE.parent.parent
    / "contracts"
    / "inputs"
    / "examples"
    / "PLACEHOLDER_rotation_calendar.json"
)

PLACEHOLDER_TEW = 4.44
PLACEHOLDER_REDUCTION = 0.0333
PLACEHOLDER_INCREMENT = 0.111
PLACEHOLDER_COVER = 0.444
PLACEHOLDER_REW = 2.22
GRID = [step / 20 for step in range(21)]  # covers from zero to one


def mulched(cover, *, tew=PLACEHOLDER_TEW, reduction=PLACEHOLDER_REDUCTION):
    return fallow.mulched_total_evaporable_water(
        tew,
        cover,
        reduction_per_increment=reduction,
        cover_increment=PLACEHOLDER_INCREMENT,
    )


def components(document: dict) -> list[tuple[dt.date, dt.date, str]]:
    return [
        (
            dt.date.fromisoformat(c["start"]["date"]),
            dt.date.fromisoformat(c["end"]["date"]),
            c["crop_id"],
        )
        for c in document["components"]
    ]


def sowings(document: dict) -> list[tuple[dt.date, str]]:
    """The start date and the crop of every component: what the entry point
    gives ``following_crop`` for the components with a start date."""
    return [(start, crop) for start, _, crop in components(document)]


ONE_DAY = dt.timedelta(days=1)


# --- the crop that follows a fallow day -----------------------------------------


def test_following_crop_is_the_crop_of_the_next_sowing():
    document = json.loads(EXAMPLE.read_text("utf-8"))
    following = fallow.following_crop(sowings(document), [])
    dated = sorted(components(document))
    calendar_start = dt.date.fromisoformat(document["start_date"])
    # Every day before each sowing, back to the end of the component before
    # it (or the start of the calendar), is followed by that sowing's crop.
    previous_end = calendar_start - dt.timedelta(days=1)
    checked = 0
    for start, end, crop in dated:
        day = previous_end + dt.timedelta(days=1)
        while day < start:
            assert following(day) == crop
            day += dt.timedelta(days=1)
            checked += 1
        previous_end = end
    assert checked > 0


def test_no_sowing_after_the_day_is_missing_input_naming_open_31():
    document = json.loads(EXAMPLE.read_text("utf-8"))
    last_end = max(end for _, end, _ in components(document))
    found = fallow.following_crop(sowings(document), [])(last_end + ONE_DAY)
    assert isinstance(found, Missing)
    assert found.reason == "MISSING_INPUT"
    assert found.detail == fallow.NO_FOLLOWING_CROP
    assert "OPEN 31" in found.detail
    assert "D110" in found.detail and "D115" in found.detail
    # With no sowing at all, every day is such a day.
    assert fallow.following_crop([], [])(last_end).detail == fallow.NO_FOLLOWING_CROP


def test_a_sowing_of_the_next_cycle_follows_the_last_fallow_of_a_cycle():
    # What the repeated rotation gives (unit #253): the sowings of one cycle
    # and of the next. The day after the last component of the first cycle
    # is followed by the first sowing of the next cycle.
    document = json.loads(EXAMPLE.read_text("utf-8"))
    one_cycle = sorted(sowings(document))
    last_end = max(end for _, end, _ in components(document))
    PLACEHOLDER_CYCLE = dt.timedelta(days=3333)
    next_cycle = [(start + PLACEHOLDER_CYCLE, crop) for start, crop in one_cycle]
    following = fallow.following_crop([*next_cycle, *one_cycle], [])
    first_start, first_crop = one_cycle[0]
    assert first_start + PLACEHOLDER_CYCLE > last_end
    day = last_end + ONE_DAY
    while day < first_start + PLACEHOLDER_CYCLE:
        assert following(day) == first_crop
        day += dt.timedelta(days=111)
    # The order in which the sowings are given does not matter.
    assert fallow.following_crop([*one_cycle, *next_cycle], [])(
        last_end + ONE_DAY
    ) == following(last_end + ONE_DAY)


def test_a_component_without_a_start_date_that_could_be_sown_first_leaves_the_crop_unknown():
    document = json.loads(EXAMPLE.read_text("utf-8"))
    (first_start, first_crop), (second_start, second_crop), *_ = sorted(
        sowings(document)
    )
    day = first_start - ONE_DAY
    name = "PLACEHOLDER-component-undated"

    def found(first_possible: dt.date, last_possible: dt.date):
        return fallow.following_crop(
            sowings(document), [(first_possible, last_possible, name)]
        )(day)

    # It can be sown after the day and on or before the next dated sowing:
    # the crop that follows the fallow is not known.
    for first_possible, last_possible in (
        (day - ONE_DAY, day + ONE_DAY),
        (day + ONE_DAY, second_start),
        (first_start, first_start),
    ):
        unknown = found(first_possible, last_possible)
        assert isinstance(unknown, Missing)
        assert unknown.reason == "MISSING_INPUT"
        assert unknown.detail.startswith(fallow.SOWING_NOT_KNOWN)
        assert repr(name) in unknown.detail
        assert "D110" in unknown.detail and "D115" in unknown.detail
    # Its last possible day is the day or before it: it was sown before.
    assert found(day - ONE_DAY, day) == first_crop
    # Its first possible day comes after the next dated sowing.
    assert found(first_start + ONE_DAY, second_start) == first_crop
    # With no dated sowing after the day, it alone leaves the crop unknown.
    alone = fallow.following_crop([], [(day + ONE_DAY, second_start, name)])(day)
    assert alone.detail.startswith(fallow.SOWING_NOT_KNOWN)
    assert second_crop  # the example has a second sowing


def test_two_crops_on_the_next_sowing_are_not_computable():
    document = json.loads(EXAMPLE.read_text("utf-8"))
    first = document["components"][0]
    twin = copy.deepcopy(first)
    twin["component_id"] = "PLACEHOLDER-component-twin"
    twin["crop_id"] = "PLACEHOLDER-crop-other"
    document["components"].append(twin)
    sowing = dt.date.fromisoformat(first["start"]["date"])
    following = fallow.following_crop(sowings(document), [])
    found = following(sowing - dt.timedelta(days=1))
    assert isinstance(found, Missing)
    assert found.reason == "NOT_COMPUTABLE"
    assert found.detail == fallow.TWO_FOLLOWING_CROPS
    # The same crop sown twice on one date is one crop.
    twin["crop_id"] = first["crop_id"]
    same = fallow.following_crop(sowings(document), [])
    assert same(sowing - dt.timedelta(days=1)) == first["crop_id"]


# --- the total and readily evaporable water of a fallow day ---------------------


def test_mulched_total_follows_the_proposed_form():
    for cover in GRID:
        expected = PLACEHOLDER_TEW * (
            1 - PLACEHOLDER_REDUCTION * cover / PLACEHOLDER_INCREMENT
        )
        assert mulched(cover) == pytest.approx(expected)


def test_no_cover_leaves_the_total_unchanged_and_more_cover_never_gives_more():
    assert mulched(0.0) == PLACEHOLDER_TEW
    values = [mulched(cover) for cover in GRID]
    assert all(later <= earlier for earlier, later in zip(values, values[1:]))
    assert values[-1] < values[0]
    # One increment of cover removes one reduction of the total.
    assert mulched(PLACEHOLDER_INCREMENT) == pytest.approx(
        PLACEHOLDER_TEW * (1 - PLACEHOLDER_REDUCTION)
    )


@pytest.mark.parametrize(
    "name",
    [
        "total_evaporable_water",
        "surface_residue_cover",
        "reduction_per_increment",
        "cover_increment",
    ],
)
def test_missing_operand_is_missing_input_naming_it(name):
    operands = {
        "total_evaporable_water": PLACEHOLDER_TEW,
        "surface_residue_cover": PLACEHOLDER_COVER,
        "reduction_per_increment": PLACEHOLDER_REDUCTION,
        "cover_increment": PLACEHOLDER_INCREMENT,
    }
    operands[name] = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER")
    found = fallow.mulched_total_evaporable_water(
        operands["total_evaporable_water"],
        operands["surface_residue_cover"],
        reduction_per_increment=operands["reduction_per_increment"],
        cover_increment=operands["cover_increment"],
    )
    assert isinstance(found, Missing)
    assert found.reason == "MISSING_INPUT"
    assert f"{name} (NOT_DECLARED)" in found.detail
    others = [other for other in operands if other != name]
    assert not any(f"{other} (" in found.detail for other in others)


@pytest.mark.parametrize(
    ("cover", "reduction", "increment", "why"),
    [
        (1.11, PLACEHOLDER_REDUCTION, PLACEHOLDER_INCREMENT, "outside zero to one"),
        (-0.111, PLACEHOLDER_REDUCTION, PLACEHOLDER_INCREMENT, "outside zero to one"),
        (PLACEHOLDER_COVER, PLACEHOLDER_REDUCTION, 0.0, "not above zero"),
        (PLACEHOLDER_COVER, PLACEHOLDER_REDUCTION, -0.111, "not above zero"),
        (PLACEHOLDER_COVER, -0.0333, PLACEHOLDER_INCREMENT, "below zero"),
        (PLACEHOLDER_COVER, 0.444, PLACEHOLDER_INCREMENT, "leaves no evaporable"),
        (PLACEHOLDER_COVER, 0.111, 0.0333, "leaves no evaporable"),
        (math.nan, PLACEHOLDER_REDUCTION, PLACEHOLDER_INCREMENT, "not a finite"),
        (PLACEHOLDER_COVER, math.inf, PLACEHOLDER_INCREMENT, "not a finite"),
    ],
)
def test_values_outside_what_the_method_computes_are_not_computable(
    cover, reduction, increment, why
):
    found = fallow.mulched_total_evaporable_water(
        PLACEHOLDER_TEW,
        cover,
        reduction_per_increment=reduction,
        cover_increment=increment,
    )
    assert isinstance(found, Missing)
    assert found.reason == "NOT_COMPUTABLE"
    assert why in found.detail
    for value in (cover, reduction, increment):
        assert repr(value) not in found.detail  # no value is repeated


def test_readily_evaporable_water_is_not_above_the_total():
    small = 1.11
    assert fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, small) == small
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, PLACEHOLDER_TEW)
        == PLACEHOLDER_REW
    )
    not_declared = Missing(reason="NOT_DECLARED", detail="PLACEHOLDER")
    for rew, tew, name in (
        (not_declared, PLACEHOLDER_TEW, "readily_evaporable_water"),
        (PLACEHOLDER_REW, not_declared, "total_evaporable_water"),
    ):
        found = fallow.readily_evaporable_water_not_above(rew, tew)
        assert found.reason == "MISSING_INPUT"
        assert f"{name} (NOT_DECLARED)" in found.detail
    refused = Missing(reason="NOT_COMPUTABLE", detail="PLACEHOLDER")
    assert (
        fallow.readily_evaporable_water_not_above(PLACEHOLDER_REW, refused) == refused
    )


def test_proposed_cases_match_exposure_md():
    text = (HERE / "EXPOSURE.md").read_text("utf-8")
    section = text.split("## PROPOSED cases of the fallow", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, flags=re.MULTILINE)
    tests = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert sorted(listed) == sorted(tests)
