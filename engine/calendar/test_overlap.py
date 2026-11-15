"""Tests for component overlap detection (D72 / USER-Z) in ``engine/calendar/overlap.py``."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import Feasibility, RotationCalendar
from contracts.rotation_definition.common import DateValue as DeclaredDate
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar import build as build_module
from engine.calendar import build_rotation_calendar
from engine.calendar.overlap import (
    NO_OVERLAPPING_COMPONENTS,
    OVERLAP_RULE,
    RULES_WITH_OVERLAP,
    check_feasibility_with_overlap,
    find_overlapping_components,
    make_overlap_rule,
)
from engine.calendar.rules import (
    HARVEST_NOT_BEFORE_SOWING,
    POSITIONS_NUMBER_THE_COMPONENTS,
    RULES,
    CalendarRule,
    Finding,
    check_feasibility,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = (
    REPO_ROOT
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
D128_PATH = REPO_ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"

NOT_DECLARED = {"date": None, "missing": {"reason": "NOT_DECLARED"}}


def _date_payload(iso: str) -> dict[str, Any]:
    return {"date": iso, "provenance": "DECLARED", "source": "PLACEHOLDER_test"}


def _component_payload(
    component_id: str,
    position: int,
    crop_id: str,
    sowing: str | None,
    harvest: str | None,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "position": position,
        "crop_id": crop_id,
        "purpose": "grain",
        "sowing": _date_payload(sowing)
        if sowing is not None
        else copy.deepcopy(NOT_DECLARED),
        "harvest": _date_payload(harvest)
        if harvest is not None
        else copy.deepcopy(NOT_DECLARED),
        "management": {
            "residue": "left_on_surface",
            "grazing": {"missing": {"reason": "NOT_DECLARED"}},
            "termination": {"missing": {"reason": "NOT_DECLARED"}},
        },
    }


def _rotation_from_spans(
    spans: list[tuple[str, str | None, str | None]],
    *,
    positions: list[int] | None = None,
) -> RotationDefinition:
    base = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    pos_list = positions if positions is not None else list(range(1, len(spans) + 1))
    base["components"] = [
        _component_payload(cid, pos, f"PLACEHOLDER_crop_{idx}", sowing, harvest)
        for idx, ((cid, sowing, harvest), pos) in enumerate(
            zip(spans, pos_list, strict=True), start=1
        )
    ]
    return RotationDefinition.model_validate(base)


# --- Non-overlapping D128 and example rotations -----------------------------


def test_d128_rotations_have_no_overlapping_components():
    raw_list = json.loads(D128_PATH.read_text(encoding="utf-8"))
    assert len(raw_list) == 2
    for raw in raw_list:
        rotation = RotationDefinition.model_validate(raw)
        assert find_overlapping_components(rotation) == []
        assert find_overlapping_components(rotation, allow_same_day_handoff=True) == []
        feasibility = check_feasibility_with_overlap(rotation)
        assert feasibility == Feasibility(feasible=True, violations=[])


def test_placeholder_example_rotation_has_no_overlapping_components():
    rotation = RotationDefinition.model_validate_json(
        EXAMPLE_PATH.read_text(encoding="utf-8")
    )
    assert find_overlapping_components(rotation) == []
    assert check_feasibility_with_overlap(rotation).feasible is True


def test_disjoint_components_with_one_day_gap_do_not_overlap():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-25", "2027-12-05"),
            ("c2", "2027-12-06", "2028-05-10"),
            ("c3", "2028-05-11", "2028-10-01"),
        ]
    )
    assert find_overlapping_components(rotation) == []
    assert check_feasibility_with_overlap(rotation).feasible is True


def test_disjoint_components_listed_out_of_chronological_order_do_not_overlap():
    rotation = _rotation_from_spans(
        [
            ("c2", "2027-12-10", "2028-05-10"),
            ("c1", "2027-05-25", "2027-12-05"),
        ]
    )
    assert find_overlapping_components(rotation) == []


# --- Overlap detection: partial, nested, same-day sowing/harvest ------------


def test_partial_overlap_detected_with_component_ids_and_dates():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-25", "2027-12-05"),
            ("c2", "2027-11-15", "2028-05-05"),
        ]
    )
    for allow in (False, True):
        findings = find_overlapping_components(rotation, allow_same_day_handoff=allow)
        assert len(findings) == 1
        [finding] = findings
        assert isinstance(finding, Finding)
        assert finding.component_ids == ("c1", "c2")
        assert finding.detail is not None
        assert "c1" in finding.detail
        assert "c2" in finding.detail
        assert "2027-05-25" in finding.detail
        assert "2028-05-05" in finding.detail


def test_partial_overlap_preserves_component_list_order_in_finding():
    rotation = _rotation_from_spans(
        [
            ("c_later", "2027-11-15", "2028-05-05"),
            ("c_earlier", "2027-05-25", "2027-12-05"),
        ]
    )
    [finding] = find_overlapping_components(rotation)
    assert finding.component_ids == ("c_later", "c_earlier")


def test_multiple_overlapping_pairs_reported_in_pair_order():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-01", "2027-12-01"),
            ("c2", "2027-11-01", "2028-04-01"),
            ("c3", "2028-03-01", "2028-09-01"),
        ]
    )
    findings = find_overlapping_components(rotation)
    assert [f.component_ids for f in findings] == [("c1", "c2"), ("c2", "c3")]


@pytest.mark.parametrize(
    "spans",
    [
        pytest.param(
            [
                ("outer", "2027-05-01", "2028-05-01"),
                ("inner", "2027-11-15", "2028-02-15"),
            ],
            id="strictly-nested",
        ),
        pytest.param(
            [
                ("inner", "2027-11-15", "2028-02-15"),
                ("outer", "2027-05-01", "2028-05-01"),
            ],
            id="strictly-nested-reversed",
        ),
        pytest.param(
            [
                ("outer", "2027-05-01", "2028-05-01"),
                ("single", "2027-11-15", "2027-11-15"),
            ],
            id="single-day-nested-inside",
        ),
        pytest.param(
            [("a", "2027-11-15", "2028-04-10"), ("b", "2027-11-15", "2028-05-05")],
            id="same-day-sowing",
        ),
        pytest.param(
            [("a", "2027-10-01", "2028-05-05"), ("b", "2027-11-15", "2028-05-05")],
            id="same-day-harvest",
        ),
        pytest.param(
            [("a", "2027-11-15", "2028-05-05"), ("b", "2027-11-15", "2028-05-05")],
            id="identical-multi-day-spans",
        ),
        pytest.param(
            [("a", "2027-11-15", "2027-11-15"), ("b", "2027-11-15", "2027-11-15")],
            id="identical-single-day-spans",
        ),
    ],
)
def test_nested_and_coincident_overlaps_always_detected(spans):
    rotation = _rotation_from_spans(spans)
    for allow in (False, True):
        findings = find_overlapping_components(rotation, allow_same_day_handoff=allow)
        assert len(findings) == 1
        assert findings[0].component_ids == (spans[0][0], spans[1][0])


# --- Same-day harvest-to-sowing handoff toggle ------------------------------


@pytest.mark.parametrize(
    "spans",
    [
        pytest.param(
            [("c1", "2027-05-25", "2027-12-05"), ("c2", "2027-12-05", "2028-05-10")],
            id="chronological-order",
        ),
        pytest.param(
            [("c2", "2027-12-05", "2028-05-10"), ("c1", "2027-05-25", "2027-12-05")],
            id="reverse-list-order",
        ),
        pytest.param(
            [("c1", "2027-05-25", "2027-12-05"), ("c2", "2027-12-05", "2027-12-05")],
            id="single-day-second-component-on-harvest",
        ),
    ],
)
def test_same_day_handoff_toggle(spans):
    rotation = _rotation_from_spans(spans)
    strict = find_overlapping_components(rotation, allow_same_day_handoff=False)
    assert len(strict) == 1
    assert strict[0].component_ids == (spans[0][0], spans[1][0])
    assert find_overlapping_components(rotation) == strict

    permissive = find_overlapping_components(rotation, allow_same_day_handoff=True)
    assert permissive == []

    assert check_feasibility_with_overlap(rotation).feasible is False
    assert (
        check_feasibility_with_overlap(rotation, allow_same_day_handoff=True).feasible
        is True
    )


# --- Undated and inverted components skipped cleanly ------------------------


def test_undated_components_are_skipped_cleanly():
    rotation = _rotation_from_spans(
        [
            ("c_dated", "2027-11-15", "2028-04-10"),
            ("c_no_harvest", "2027-12-01", None),
            ("c_no_sowing", None, "2028-01-15"),
            ("c_neither", None, None),
        ]
    )
    assert find_overlapping_components(rotation) == []
    assert check_feasibility_with_overlap(rotation).feasible is True


def test_undated_component_does_not_mask_overlap_between_dated_components():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-11-15", "2028-04-10"),
            ("c_undated", "2027-12-01", None),
            ("c2", "2028-03-01", "2028-08-01"),
        ]
    )
    findings = find_overlapping_components(rotation)
    assert [f.component_ids for f in findings] == [("c1", "c2")]


def test_harvest_before_sowing_component_is_skipped_by_overlap_check():
    rotation = _rotation_from_spans(
        [
            ("c_valid", "2027-11-15", "2028-04-10"),
            ("c_inverted", "2028-01-01", "2028-02-01"),
        ]
    )
    inverted = rotation.components[1]
    inverted.harvest = DeclaredDate(
        date=inverted.sowing.date - dt.timedelta(days=10),
        provenance="DECLARED",
        source="PLACEHOLDER_test",
    )
    assert find_overlapping_components(rotation) == []
    feasibility = check_feasibility_with_overlap(rotation)
    assert feasibility.feasible is False
    assert [v.rule for v in feasibility.violations] == [HARVEST_NOT_BEFORE_SOWING]


# --- Rules, check_feasibility_with_overlap, and calendar integration --------


def test_rule_constants_and_make_overlap_rule():
    assert NO_OVERLAPPING_COMPONENTS == "no_overlapping_components"
    assert isinstance(OVERLAP_RULE, CalendarRule)
    assert OVERLAP_RULE.rule_id == NO_OVERLAPPING_COMPONENTS
    assert RULES_WITH_OVERLAP == (*RULES, OVERLAP_RULE)

    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-25", "2027-12-05"),
            ("c2", "2027-12-05", "2028-05-10"),
        ]
    )
    permissive_rule = make_overlap_rule(allow_same_day_handoff=True)
    assert permissive_rule.rule_id == NO_OVERLAPPING_COMPONENTS
    assert check_feasibility(rotation, (OVERLAP_RULE,)).feasible is False
    assert check_feasibility(rotation, (permissive_rule,)).feasible is True


def test_check_feasibility_with_overlap_combines_rules_in_order():
    rotation = _rotation_from_spans(
        [
            ("c_bad_dates", "2027-11-15", "2028-04-10"),
            ("c_overlap_a", "2027-05-25", "2027-12-05"),
            ("c_overlap_b", "2027-11-15", "2028-05-05"),
        ]
    )
    rotation.components[0].harvest = DeclaredDate(
        date=rotation.components[0].sowing.date - dt.timedelta(days=1),
        provenance="DECLARED",
        source="PLACEHOLDER_test",
    )
    rotation.components[1].position = rotation.components[0].position

    feasibility = check_feasibility_with_overlap(rotation)
    assert feasibility.feasible is False
    assert [v.rule for v in feasibility.violations] == [
        HARVEST_NOT_BEFORE_SOWING,
        POSITIONS_NUMBER_THE_COMPONENTS,
        NO_OVERLAPPING_COMPONENTS,
    ]
    assert feasibility.violations[2].component_ids == ["c_overlap_a", "c_overlap_b"]


def test_rules_with_overlap_produces_valid_rotation_calendar():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-25", "2027-12-05"),
            ("c2", "2027-11-15", "2028-05-05"),
        ]
    )
    # Standard EP2 remains unchanged while opted-in RULES_WITH_OVERLAP rejects overlap.
    assert build_rotation_calendar(rotation).feasibility.feasible is True

    calendar = build_module._build(rotation, RULES_WITH_OVERLAP)
    assert RotationCalendar.model_validate_json(calendar.model_dump_json()) == calendar
    assert calendar.feasibility.feasible is False
    [violation] = calendar.feasibility.violations
    assert violation.rule == NO_OVERLAPPING_COMPONENTS
    assert violation.component_ids == ["c1", "c2"]


# --- Caller defects (G5) and pure function (G1) -----------------------------


@pytest.mark.parametrize("bad_input", [None, {}, "json", 42])
def test_non_rotation_definition_raises_type_error(bad_input):
    with pytest.raises(TypeError):
        find_overlapping_components(bad_input)
    with pytest.raises(TypeError):
        check_feasibility_with_overlap(bad_input)


def test_pure_function_does_not_mutate_argument_and_is_deterministic():
    rotation = _rotation_from_spans(
        [
            ("c1", "2027-05-25", "2027-12-05"),
            ("c2", "2027-11-15", "2028-05-05"),
        ]
    )
    before = rotation.model_dump_json()
    twin = rotation.model_copy(deep=True)

    f1 = find_overlapping_components(rotation)
    f2 = find_overlapping_components(twin)
    c1 = check_feasibility_with_overlap(rotation)
    c2 = check_feasibility_with_overlap(twin)

    assert f1 == f2
    assert c1 == c2
    assert rotation.model_dump_json() == before
    assert rotation == twin

    # Mutating returned containers does not affect later calls or the input.
    f1.clear()
    c1.violations.clear()
    assert len(find_overlapping_components(rotation)) == 1
    assert len(check_feasibility_with_overlap(rotation).violations) == 1
    assert rotation.model_dump_json() == before
