"""Acceptance test of unit l1/calendar-engine.

The cases are PROPOSED (blueprint section 3.7) and are listed in
``README.md`` under "PROPOSED cases"; a test checks that the two lists agree.
The identifier of a case is the name of its test function without ``test_``,
with hyphens.

Every date and identifier used here comes from the PLACEHOLDER example of
``contracts/rotation_definition/`` or is computed from it. Nothing here
describes a real field.

Run from the repository root: ``python -m pytest engine/calendar/``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, get_args

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.rotation_definition.common import DateValue as DeclaredDate
from contracts.rotation_definition.common import ReasonCode
from contracts.rotation_definition.rotation_definition import RotationDefinition
from engine.calendar import NoValidCalendarForm, build_rotation_calendar
from engine.calendar import build as build_module
from engine.calendar.rules import (
    HARVEST_NOT_BEFORE_SOWING,
    POSITIONS_NUMBER_THE_COMPONENTS,
    RULES,
    CalendarRule,
    Finding,
)

HERE = Path(__file__).parent
README = HERE / "README.md"
EXAMPLE = (
    HERE.parents[1]
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)

NOT_DECLARED = {"date": None, "missing": {"reason": "NOT_DECLARED"}}


def example() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def definition(data: dict[str, Any] | None = None) -> RotationDefinition:
    return RotationDefinition.model_validate(example() if data is None else data)


def reloaded(calendar: RotationCalendar) -> RotationCalendar:
    """The calendar written as JSON and loaded into its model again."""
    return RotationCalendar.model_validate_json(calendar.model_dump_json())


def declared_dates(rotation: RotationDefinition) -> set[dt.date]:
    return {
        value.date
        for component in rotation.components
        for value in (component.sowing, component.harvest)
        if value.date is not None
    }


def calendar_dates(calendar: RotationCalendar) -> set[dt.date]:
    dates = {calendar.start_date, calendar.end_date}
    for component in calendar.components:
        for value in (component.start, component.end):
            if value.date is not None:
                dates.add(value.date)
        for period in component.periods:
            for value in (period.start, period.end):
                if value.date is not None:
                    dates.add(value.date)
    return dates


# --- The accepted example ---------------------------------------------------


def test_example_definition_gives_a_calendar_that_loads_into_its_model():
    rotation = definition()
    calendar = build_rotation_calendar(rotation)
    assert isinstance(calendar, RotationCalendar)
    assert reloaded(calendar) == calendar
    assert calendar.contract == "rotation_calendar"
    assert calendar.example_data is rotation.example_data
    assert calendar.case_id == rotation.case_id
    assert calendar.field_id == rotation.field_id
    assert calendar.rotation_id == rotation.rotation_id
    assert [(c.component_id, c.crop_id) for c in calendar.components] == [
        (c.component_id, c.crop_id) for c in rotation.components
    ]


def test_example_data_flag_is_carried():
    data = example()
    data["example_data"] = False
    assert build_rotation_calendar(definition(data)).example_data is False


# --- Dates: carried, never invented ------------------------------------------


def test_declared_dates_are_carried_unchanged():
    rotation = definition()
    calendar = build_rotation_calendar(rotation)
    for declared, placed in zip(rotation.components, calendar.components, strict=True):
        for given, carried in (
            (declared.sowing, placed.start),
            (declared.harvest, placed.end),
        ):
            assert carried.model_dump() == given.model_dump()


def test_no_date_is_invented():
    rotation = definition()
    calendar = build_rotation_calendar(rotation)
    assert calendar_dates(calendar) <= declared_dates(rotation)


def test_missing_harvest_stays_missing_with_its_reason():
    rotation = definition()
    harvest = rotation.components[1].harvest
    assert harvest.date is None  # the example: a component that is not harvested
    end = build_rotation_calendar(rotation).components[1].end
    assert end.date is None
    assert end.missing is not None
    assert end.missing.reason == harvest.missing.reason
    assert end.missing.detail == harvest.missing.detail
    assert end.provenance is None


@pytest.mark.parametrize("field", ["sowing", "harvest"])
@pytest.mark.parametrize("reason", get_args(ReasonCode))
def test_missing_date_keeps_its_reason_code(field: str, reason: str):
    data = example()
    missing = {"reason": reason}
    if reason == "MISSING_INPUT":
        missing["detail"] = "PLACEHOLDER input"
    data["components"][0][field] = {"date": None, "missing": missing}
    rotation = definition(data)
    placed = build_rotation_calendar(rotation).components[0]
    carried = placed.start if field == "sowing" else placed.end
    assert carried.date is None
    assert (
        carried.missing.model_dump()
        == getattr(rotation.components[0], field).missing.model_dump()
    )
    assert calendar_dates(build_rotation_calendar(rotation)) <= declared_dates(rotation)


def test_date_with_assumption_mark_keeps_it():
    data = example()
    sowing = data["components"][0]["sowing"]
    del sowing["source"]
    sowing["assumption"] = True
    start = build_rotation_calendar(definition(data)).components[0].start
    assert start.assumption is True
    assert start.source is None
    assert start.provenance == "DECLARED"


def test_calendar_runs_from_the_earliest_to_the_latest_declared_date():
    rotation = definition()
    calendar = build_rotation_calendar(rotation)
    assert calendar.start_date == min(declared_dates(rotation))
    assert calendar.end_date == max(declared_dates(rotation))


# --- What the definition does not carry ---------------------------------------


def test_start_month_of_the_agricultural_year_is_missing_not_declared():
    start = build_rotation_calendar(definition()).ag_year_start
    assert start.month is None
    assert start.provisional is None
    assert start.provenance is None
    assert start.missing.reason == "NOT_DECLARED"


def test_periods_are_empty():
    calendar = build_rotation_calendar(definition())
    assert [component.periods for component in calendar.components] == [[], []]


def test_repeats_changes_nothing():
    data = example()
    calendars = []
    for repeats in (True, False):
        data["repeats"] = repeats
        calendars.append(build_rotation_calendar(definition(data)))
    assert calendars[0] == calendars[1]
    assert len(calendars[0].components) == len(data["components"])


def test_components_keep_the_order_of_the_definition_list():
    data = example()
    data["components"].reverse()  # positions stay 1 and 2: now listed 2, 1
    calendar = build_rotation_calendar(definition(data))
    assert [c.component_id for c in calendar.components] == [
        c["component_id"] for c in data["components"]
    ]


# --- Feasibility ----------------------------------------------------------------


def test_rotation_that_breaks_no_rule_is_feasible_with_no_violation():
    feasibility = build_rotation_calendar(definition()).feasibility
    assert feasibility.feasible is True
    assert feasibility.violations == []


def test_harvest_before_sowing_gives_an_infeasible_calendar_not_an_exception():
    # The model rejects this when a definition is loaded, so the instance is
    # changed after loading: assignment is not validated.
    rotation = definition()
    first = rotation.components[0]
    first.harvest = DeclaredDate(
        date=first.sowing.date - dt.timedelta(days=1),
        provenance="DECLARED",
        source="test",
    )
    calendar = build_rotation_calendar(rotation)
    assert reloaded(calendar) == calendar
    assert calendar.feasibility.feasible is False
    [violation] = calendar.feasibility.violations
    assert violation.rule == HARVEST_NOT_BEFORE_SOWING
    assert violation.component_ids == [first.component_id]
    placed = calendar.components[0]
    for edge in (placed.start, placed.end):
        assert edge.date is None
        assert edge.missing.reason == "NOT_COMPUTABLE"
    # The other component is placed as declared.
    assert calendar.components[1].start.date == rotation.components[1].sowing.date
    assert calendar_dates(calendar) <= declared_dates(rotation)


def test_positions_not_numbered_from_one_give_an_infeasible_calendar_not_an_exception():
    rotation = definition()
    rotation.components[1].position = rotation.components[0].position
    calendar = build_rotation_calendar(rotation)
    assert reloaded(calendar) == calendar
    assert calendar.feasibility.feasible is False
    [violation] = calendar.feasibility.violations
    assert violation.rule == POSITIONS_NUMBER_THE_COMPONENTS
    assert violation.component_ids == []


def test_two_rules_broken_are_both_named():
    rotation = definition()
    first = rotation.components[0]
    first.harvest = DeclaredDate(
        date=first.sowing.date - dt.timedelta(days=1),
        provenance="DECLARED",
        source="test",
    )
    rotation.components[1].position = first.position
    calendar = build_rotation_calendar(rotation)
    assert calendar.feasibility.feasible is False
    assert [violation.rule for violation in calendar.feasibility.violations] == [
        rule.rule_id for rule in RULES
    ]


def test_rule_planted_by_the_test_names_the_rule_and_the_component():
    # Shows the mechanism on a definition that loads: any rule added later
    # gives a valid, infeasible calendar. The rule below is not a calendar
    # rule; it exists only in this test.
    rotation = definition()
    target = rotation.components[1].component_id
    planted = (
        CalendarRule(
            "TEST_ONLY_component",
            lambda r: [Finding((target,), "planted by the test")],
        ),
        CalendarRule("TEST_ONLY_whole_rotation", lambda r: [Finding(())]),
        CalendarRule("TEST_ONLY_never_broken", lambda r: []),
    )
    calendar = build_module._build(rotation, planted)
    assert reloaded(calendar) == calendar
    assert calendar.feasibility.feasible is False
    assert [
        (v.rule, v.component_ids, v.detail) for v in calendar.feasibility.violations
    ] == [
        ("TEST_ONLY_component", [target], "planted by the test"),
        ("TEST_ONLY_whole_rotation", [], None),
    ]
    # A violation changes nothing else in the calendar.
    assert calendar.components == build_rotation_calendar(rotation).components


def _overlapping(data: dict[str, Any]) -> None:
    data["components"][1]["sowing"]["date"] = data["components"][0]["sowing"]["date"]


def _harvest_on_the_day_of_sowing(data: dict[str, Any]) -> None:
    data["components"][0]["harvest"]["date"] = data["components"][0]["sowing"]["date"]


def _dates_against_the_positions(data: dict[str, Any]) -> None:
    data["components"][0]["position"] = 2
    data["components"][1]["position"] = 1


def _one_date_missing(data: dict[str, Any]) -> None:
    data["components"][0]["sowing"] = copy.deepcopy(NOT_DECLARED)


@pytest.mark.parametrize(
    "change",
    [
        _overlapping,
        _harvest_on_the_day_of_sowing,
        _dates_against_the_positions,
        _one_date_missing,
    ],
    ids=lambda change: change.__name__.strip("_").replace("_", "-"),
)
def test_no_rule_while_the_question_is_open(change):
    # Not a proposal to allow what these variants show. No person has decided
    # a rule for them, so the engine has none and they break nothing today.
    data = example()
    change(data)
    calendar = build_rotation_calendar(definition(data))
    assert calendar.feasibility.feasible is True
    assert calendar.feasibility.violations == []


# --- Caller defects (rule G5) ---------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(example(), id="a-dictionary"),
        pytest.param(json.dumps(example()), id="json-text"),
        pytest.param(None, id="nothing"),
        pytest.param(RotationDefinition, id="the-model-class"),
        pytest.param(build_rotation_calendar(definition()), id="a-rotation-calendar"),
        pytest.param(definition().components[0], id="one-component"),
    ],
)
def test_value_that_is_not_a_rotation_definition_raises_type_error(value):
    with pytest.raises(TypeError):
        build_rotation_calendar(value)


# --- Pure function (rule G1) ----------------------------------------------------


def test_argument_is_not_changed():
    rotation = definition()
    before = rotation.model_dump_json()
    twin = rotation.model_copy(deep=True)
    build_rotation_calendar(rotation)
    assert rotation.model_dump_json() == before
    assert rotation == twin


def test_argument_is_not_changed_when_a_rule_is_broken():
    rotation = definition()
    rotation.components[1].position = rotation.components[0].position
    before = rotation.model_dump_json()
    build_rotation_calendar(rotation)
    assert rotation.model_dump_json() == before


def test_same_argument_gives_the_same_result():
    rotation = definition()
    first = build_rotation_calendar(rotation)
    second = build_rotation_calendar(rotation)
    third = build_rotation_calendar(definition())
    assert first == second == third
    assert (
        first.model_dump_json() == second.model_dump_json() == third.model_dump_json()
    )
    assert first is not second


def test_changing_the_result_does_not_change_the_argument():
    rotation = definition()
    before = rotation.model_dump_json()
    calendar = build_rotation_calendar(rotation)
    calendar.components[0].start.source = "changed by the test"
    calendar.components.clear()
    assert rotation.model_dump_json() == before


def test_engine_modules_import_nothing_that_reads_a_file_the_network_or_the_clock():
    allowed = ("__future__", "collections.abc", "dataclasses", "contracts.")
    modules = sorted(p for p in HERE.glob("*.py") if not p.name.startswith("test_"))
    assert modules
    for path in modules:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative: a module of this folder
                    continue
                names = [node.module]
            else:
                continue
            for name in names:
                assert name.startswith(allowed), f"{path.name} imports {name}"


def test_contract_models_are_imported_through_the_contracts_path():
    assert RotationDefinition.__module__ == (
        "contracts.rotation_definition.rotation_definition"
    )
    assert RotationCalendar.__module__ == "contracts.inputs.rotation_calendar"
    calendar = build_rotation_calendar(definition())
    assert type(calendar) is RotationCalendar
    assert type(calendar.components[0].start).__module__ == "contracts.inputs.common"
    assert (
        type(calendar.components[1].end.missing).__module__ == "contracts.inputs.common"
    )


# --- No valid form ----------------------------------------------------------------


def test_definition_with_no_date_has_no_valid_calendar():
    data = example()
    for component in data["components"]:
        component["sowing"] = copy.deepcopy(NOT_DECLARED)
        component["harvest"] = copy.deepcopy(NOT_DECLARED)
    with pytest.raises(NoValidCalendarForm):
        build_rotation_calendar(definition(data))


def test_definition_with_no_component_has_no_valid_calendar():
    data = example()
    data["components"] = []
    with pytest.raises(NoValidCalendarForm):
        build_rotation_calendar(definition(data))


def test_two_components_with_one_identifier_have_no_valid_calendar():
    # Rejected when a definition is loaded; the instance is changed afterwards.
    rotation = definition()
    rotation.components[1].component_id = rotation.components[0].component_id
    with pytest.raises(NoValidCalendarForm):
        build_rotation_calendar(rotation)


def test_only_dates_that_cannot_be_placed_have_no_valid_calendar():
    # One component, changed after loading so that its harvest is before its
    # sowing: neither date is placed, so the calendar has no date at all.
    data = example()
    del data["components"][1]
    rotation = definition(data)
    only = rotation.components[0]
    only.harvest = DeclaredDate(
        date=only.sowing.date - dt.timedelta(days=1),
        provenance="DECLARED",
        source="test",
    )
    with pytest.raises(NoValidCalendarForm):
        build_rotation_calendar(rotation)


def test_no_valid_form_is_not_one_of_the_caller_defects():
    assert not issubclass(NoValidCalendarForm, (TypeError, ValueError))


# --- README and tests agree -------------------------------------------------------


def _section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"README has no section {title!r}"
    return match.group(1)


def test_readme_lists_the_cases():
    listed = re.findall(r"^\| `([a-z0-9-]+)` \|", _section("PROPOSED cases"), re.M)
    here = [
        name.removeprefix("test_").replace("_", "-")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    assert len(listed) == len(set(listed))
    assert sorted(listed) == sorted(here)


def test_readme_lists_the_rules():
    listed = re.findall(r"^\| `([a-z_]+)` \|", _section("PROPOSED rules"), re.M)
    assert listed == [rule.rule_id for rule in RULES]
