"""Acceptance tests of the phases of a rotation (unit l2/runner-phases, D109).

Run with ``uv run pytest api/test_phases.py`` from the repository root.

Every date here is a PLACEHOLDER date, written by hand to show the moving
rule of ``api/phases.py``; none is a real sowing or harvest. The engines are
fakes, except in the last test, which uses the engines of the repository only
when they can be imported. ``engine.calendar.repeat`` is imported by the tests
only, to check that the runner's copy of its two date rules agrees with it.

Status: PROPOSED test cases (blueprint section 3.7).
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api import phases
from api.engines import (
    EngineFunctions,
    EntryPointEngines,
    discover_engine_functions,
    phase_functions_of,
)
from api.main import create_app
from api.phases import (
    CROSSING_OPEN,
    RUNNER_COPY,
    PhaseFunctions,
    crossing_components,
    cycle_length_years,
    list_phases,
    phase_calendar,
    phase_calendars,
    scenario_id,
    shifted_date,
)
from api.ports import EnginesResult, Missing, RunSettings
from api.test_engines import (
    BODY,
    CARBON_MODELS,
    ROTATION,
    ROUTE,
    SOIL_SLOPE,
    Fake,
    balance,
    calendar,
    chain_climate,
    client,
    climate_result,
    fakes,
    soil_loss,
    soil_result,
    water,
)
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.results.models import ResultsPerRotation

ROOT = Path(__file__).parent.parent
SOURCE = "PLACEHOLDER: hand-written date of a test, not a declaration"


def date_value(day: str | None) -> dict[str, Any]:
    if day is None:
        return {"date": None, "missing": {"reason": "NOT_DECLARED"}}
    return {"date": day, "provenance": "DECLARED", "source": SOURCE}


def component(component_id: str, start: str | None, end: str | None) -> dict:
    return {
        "component_id": component_id,
        "crop_id": f"PLACEHOLDER-crop-{component_id}",
        "start": date_value(start),
        "end": date_value(end),
        "periods": [],
    }


def hand_calendar(
    start: str, end: str, components: list[dict], month: int | None = 7
) -> RotationCalendar:
    document = copy.deepcopy(calendar().model_dump(mode="json"))
    document["start_date"], document["end_date"] = start, end
    document["components"] = components
    if month is None:
        document["ag_year_start"] = {
            "month": None,
            "missing": {"reason": "NOT_DECLARED"},
        }
    else:
        document["ag_year_start"]["month"] = month
    return RotationCalendar.model_validate(document)


# A three-year PLACEHOLDER rotation, start month 7: one component in each
# agricultural year (2001, 2002, 2003); C ends on a 29 February.
THREE_YEARS = hand_calendar(
    "2001-09-01",
    "2004-02-29",
    [
        component("a", "2001-09-01", "2001-12-31"),
        component("b", "2002-09-01", "2003-02-28"),
        component("c", "2003-09-01", "2004-02-29"),
    ],
)
ONE_YEAR = hand_calendar(
    "2001-09-01", "2002-02-28", [component("a", "2001-09-01", "2002-02-28")]
)


def dates(moved: RotationCalendar) -> list[tuple[str, str | None, str | None]]:
    return [
        (
            c.component_id,
            c.start.date.isoformat() if c.start.date else None,
            c.end.date.isoformat() if c.end.date else None,
        )
        for c in moved.components
    ]


# --- 1. moving the calendar ---------------------------------------------------


def test_a_one_year_rotation_has_one_phase_the_calendar_unchanged():
    (only,) = phase_calendars(ONE_YEAR)
    assert only.calendar is ONE_YEAR
    assert (only.index, only.scenario_id, only.first_ag_year) == (0, "phase_1", 2001)
    assert only.notes == ()
    assert list_phases(ONE_YEAR) == [0]


def test_a_three_year_rotation_has_three_moved_calendars():
    first, second, third = phase_calendars(THREE_YEARS)
    assert first.calendar is THREE_YEARS  # phase 0 unchanged
    assert [p.scenario_id for p in (first, second, third)] == [
        "phase_1",
        "phase_2",
        "phase_3",
    ]
    assert [p.first_ag_year for p in (first, second, third)] == [2001, 2002, 2003]
    # Phase 1: year 2002 first; a moves to the end of the cycle.
    assert dates(second.calendar) == [
        ("b", "2001-09-01", "2002-02-28"),
        ("c", "2002-09-01", "2003-02-28"),  # 29 February in a year without one
        ("a", "2003-09-01", "2003-12-31"),
    ]
    assert (second.calendar.start_date, second.calendar.end_date) == (
        dt.date(2001, 7, 1),
        dt.date(2004, 6, 30),
    )
    # Phase 2: year 2003 first; a and b move to the end of the cycle.
    assert dates(third.calendar) == [
        ("c", "2001-09-01", "2002-02-28"),
        ("a", "2002-09-01", "2002-12-31"),
        ("b", "2003-09-01", "2004-02-28"),
    ]
    for phase in (second, third):
        moved = phase.calendar
        RotationCalendar.model_validate(moved.model_dump())  # loads into the contract
        assert cycle_length_years(moved) == 3
        assert any("29 February" in note for note in phase.notes)
        assert not any(note.startswith("OPEN") for note in phase.notes)
        # Nothing else changes.
        assert moved.ag_year_start == THREE_YEARS.ag_year_start
        assert moved.feasibility == THREE_YEARS.feasibility
        assert {c.component_id: c.crop_id for c in moved.components} == {
            c.component_id: c.crop_id for c in THREE_YEARS.components
        }
        assert [c.start.source for c in moved.components] == [SOURCE] * 3


def test_the_date_rules_are_those_of_engine_calendar_repeat():
    repeat = pytest.importorskip("engine.calendar.repeat")
    for day in (dt.date(2004, 2, 29), dt.date(2001, 9, 1), dt.date(2003, 2, 28)):
        for years in (-3, -2, -1, 1, 2, 3, 4):
            assert shifted_date(day, years) == repeat.shifted_date(day, years)
    for cal in (THREE_YEARS, ONE_YEAR, calendar()):
        assert cycle_length_years(cal) == repeat.cycle_length_years(cal)
    # Every moved date is the calendar's date moved by the net years, by
    # repeat.shifted_date.
    second = phase_calendar(THREE_YEARS, 1)
    original = {c.component_id: c for c in THREE_YEARS.components}
    for c in second.components:
        years = 2 if c.component_id == "a" else -1
        assert (
            c.end.date
            == repeat.shifted_date(original[c.component_id].end.date, years)[0]
        )


def test_a_phase_out_of_range_is_a_value_error():
    for bad in (-1, 3, True):
        with pytest.raises(ValueError):
            phase_calendar(THREE_YEARS, bad)


def test_phase_0_is_the_calendar_itself():
    assert phase_calendar(THREE_YEARS, 0) is THREE_YEARS


# --- 5. a component that starts before the phase -------------------------------


def test_a_crossing_component_refuses_the_phase_and_its_rule_is_open():
    # The PLACEHOLDER calendar: component 2 runs 2002-04-01 to 2002-10-31,
    # across the first day of the agricultural year 2002 (D133: no rule).
    example = calendar()
    assert crossing_components(example, 1) == 1
    with pytest.raises(ValueError):
        phase_calendar(example, 1)
    first, second = phase_calendars(example)
    assert first.calendar is example and first.notes == ()
    assert second.calendar is None  # nothing moved, nothing guessed
    assert (second.scenario_id, second.first_ag_year) == ("phase_2", 2002)
    (note,) = second.notes
    assert note == CROSSING_OPEN.format(count=1)
    assert "PLACEHOLDER-component-2" not in note  # counts only, no identifier
    assert "api.phases.phase_calendar" in second.not_laid_out


def test_a_component_without_an_end_date_before_the_cut_is_open_too():
    cal = hand_calendar(
        "2001-09-01",
        "2003-02-28",
        [
            component("a", "2001-09-01", None),
            component("b", "2002-09-01", "2003-02-28"),
        ],
    )
    assert crossing_components(cal, 1) == 1
    _, second = phase_calendars(cal)
    assert second.calendar is None
    assert any(n.startswith("OPEN") for n in second.notes)


def test_the_route_records_the_open_rule_in_the_phase():
    body = (
        client(EntryPointEngines(_functions(), carbon_models=CARBON_MODELS))
        .post(ROUTE, json=BODY)
        .json()
    )
    first, second = body["scenarios"]
    assert first["result"] is not None
    detail = {m["id"]: m["detail"] for m in second["modules"]}["calendar"]
    assert detail.startswith("OPEN")
    assert second["calendar"] is None and second["result"] is None
    assert second["result_missing"]["reason"] == "NOT_COMPUTABLE"
    assert second["result_missing"]["detail"].startswith("OPEN")
    assert second["outcome"] == "no_result"
    assert "OPEN" not in (
        {m["id"]: m["detail"] for m in first["modules"]}["calendar"] or ""
    )


def test_without_the_start_month_only_phase_1_runs_and_says_so():
    cal = hand_calendar(
        "2001-09-01",
        "2004-02-29",
        [c.model_dump() for c in THREE_YEARS.components],
        None,
    )
    (only,) = phase_calendars(cal)
    assert only.calendar is cal and only.first_ag_year is None
    (note,) = only.notes
    assert "start month" in note and "2 phase(s)" in note


# --- lane L1's functions (issue #221) and the runner's copy --------------------


class FakePhases:
    """``phase_calendar`` and ``list_phases`` as issue #221 names them."""

    def __init__(self, answer: Any = None, raises: bool = False) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.answer = answer
        self.raises = raises

    def phase_calendar(self, cal: RotationCalendar, p: int) -> RotationCalendar:
        self.calls.append(("phase_calendar", (cal, p)))
        if self.raises:
            raise ValueError("PLACEHOLDER: a component crosses the year boundary")
        return self.answer if self.answer is not None else phase_calendar(cal, p)

    def list_phases(self, cal: RotationCalendar) -> list[int]:
        self.calls.append(("list_phases", (cal,)))
        return list_phases(cal)


def _functions(found: FakePhases | None = None, **kwargs: Any) -> EngineFunctions:
    calendar_fn, soil_fn, water_fn = fakes(**kwargs)
    extra = {}
    if found is not None:
        extra = {
            "phase_calendar": found.phase_calendar,
            "list_phases": found.list_phases,
        }
    return EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_fn,
        compute_water_deficit_exposure=water_fn,
        **extra,
    )


def test_lane_l1_functions_are_used_when_both_exist():
    found = FakePhases()
    chosen = phase_functions_of(_functions(found))
    assert chosen.name == "engine.calendar.repeat"
    result = EntryPointEngines(_functions(found), carbon_models=CARBON_MODELS).run(
        ROTATION, climate_result(), soil_result()
    )
    assert [name for name, _ in found.calls] == ["list_phases", "phase_calendar"]
    assert found.calls[1][1][1] == 1  # phase 0 is never asked
    assert [p.scenario_id for p in result.phases] == ["phase_1", "phase_2"]


def test_with_one_of_the_two_missing_the_runner_uses_its_copy():
    found = FakePhases()
    only_one = EngineFunctions(phase_calendar=found.phase_calendar)
    assert phase_functions_of(only_one) is RUNNER_COPY
    assert phase_functions_of(EngineFunctions()) is RUNNER_COPY


def test_discovery_finds_them_by_name_in_engine_calendar_repeat():
    repeat = pytest.importorskip("engine.calendar.repeat")
    found = discover_engine_functions()
    assert found.phase_calendar is getattr(repeat, "phase_calendar", None)
    assert found.list_phases is getattr(repeat, "list_phases", None)


def test_discovery_without_an_engine_package_gives_none(engines_hidden):
    found = discover_engine_functions()
    assert found.phase_calendar is None and found.list_phases is None


def test_a_refused_phase_with_a_crossing_component_is_recorded_not_guessed():
    found = FakePhases(raises=True)
    calendar_fn, soil_fn, water_fn = fakes()
    functions = EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_fn,
        compute_water_deficit_exposure=water_fn,
        phase_calendar=found.phase_calendar,
        list_phases=found.list_phases,
    )
    result = EntryPointEngines(functions, carbon_models=CARBON_MODELS).run(
        ROTATION, climate_result(), soil_result()
    )
    assert len(soil_fn.calls) == len(water_fn.calls) == 1  # phase 2 calls none
    refused = result.phases[1].result
    assert refused.calendar is None and refused.result is None
    assert refused.result_missing.reason == "NOT_COMPUTABLE"
    assert refused.result_missing.detail.startswith("OPEN")
    assert "PLACEHOLDER: a component" not in refused.result_missing.detail
    body = client(EntryPointEngines(functions, carbon_models=CARBON_MODELS)).post(
        ROUTE, json=BODY
    )
    assert body.status_code == 200
    second = body.json()["scenarios"][1]
    assert second["result"] is None and second["outcome"] == "no_result"


def test_a_refused_phase_without_a_crossing_component_is_a_defect():
    found = FakePhases(raises=True)
    functions = PhaseFunctions(found.phase_calendar, found.list_phases, "PLACEHOLDER")
    with pytest.raises(ValueError):
        phase_calendars(THREE_YEARS, functions)


def test_a_flagged_calendar_with_a_crossing_component_records_the_open_rule():
    # Whatever flag lane L1's function sets, the runner finds the crossing
    # component on the calendar EP2 built.
    # A fake that returns a calendar instead of raising (the "flagged" form).
    example = calendar()
    found = FakePhases(answer=example)
    functions = PhaseFunctions(found.phase_calendar, found.list_phases, "PLACEHOLDER")
    _, second = phase_calendars(example, functions)
    assert second.calendar == example
    (note,) = [n for n in second.notes if n.startswith("OPEN")]
    assert note.startswith(CROSSING_OPEN.format(count=1))
    assert "PLACEHOLDER.phase_calendar returned is used as it is" in note


def _changed(**update: Any) -> RotationCalendar:
    """The runner's own phase 2 of THREE_YEARS with one thing changed."""
    document = phase_calendar(THREE_YEARS, 1).model_dump()
    for key, value in update.items():
        if key == "crop":
            document["components"][0]["crop_id"] = value
        elif key == "month":
            document["ag_year_start"]["month"] = value
        else:
            document[key] = value
    return RotationCalendar.model_validate(document)


@pytest.mark.parametrize(
    "answer",
    [
        _changed(rotation_id="PLACEHOLDER-another-rotation"),
        _changed(field_id="PLACEHOLDER-another-field"),
        _changed(crop="PLACEHOLDER-another-crop"),
        _changed(month=8),
        "PLACEHOLDER-not-a-calendar",
    ],
    ids=["rotation", "field", "crop", "start-month", "type"],
)
def test_a_moved_calendar_that_changes_more_than_dates_is_a_defect(answer):
    found = FakePhases(answer=answer)
    functions = PhaseFunctions(found.phase_calendar, found.list_phases, "PLACEHOLDER")
    with pytest.raises(TypeError):
        phase_calendars(THREE_YEARS, functions)


@pytest.mark.parametrize("returned", [[1, 2], [], "012", 3, [0, 2]])
def test_phases_that_are_not_0_to_n_minus_1_are_a_defect(returned):
    found = FakePhases()
    functions = PhaseFunctions(
        found.phase_calendar, lambda cal: returned, "PLACEHOLDER"
    )
    with pytest.raises(TypeError):
        phase_calendars(THREE_YEARS, functions)


def test_any_sequence_0_to_n_minus_1_is_accepted():
    found = FakePhases()
    functions = PhaseFunctions(
        found.phase_calendar, lambda cal: (0, 1, 2), "PLACEHOLDER"
    )
    assert [p.calendar for p in phase_calendars(THREE_YEARS, functions)] == [
        p.calendar for p in phase_calendars(THREE_YEARS)
    ]


# --- 2. each phase calls EP1, EP3 and EP5 on its calendar ---------------------


def test_each_phase_calls_ep1_ep3_and_ep5_once_with_its_calendar():
    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=THREE_YEARS)
    amg = Fake(balance())
    parameters: dict[str, dict] = {}
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
            run_amg=amg,
        ),
        carbon_models=CARBON_MODELS,
        parameters=parameters,
    )
    climate, soil = climate_result(chain_climate()), soil_result()
    result = engines.run(ROTATION, climate, soil)
    expected = [p.calendar for p in phase_calendars(THREE_YEARS)]
    assert len(calendar_fn.calls) == 1
    for fake in (soil_fn, water_fn):
        assert [kwargs["calendar"] for _, kwargs in fake.calls] == expected
        assert all(kwargs["climate"] is climate.data for _, kwargs in fake.calls)
        assert all(kwargs["soil_slope"] is soil.data for _, kwargs in fake.calls)
        assert all(kwargs["parameters"] is parameters for _, kwargs in fake.calls)
    assert len(amg.calls) == 3
    assert all(kwargs["parameters"] is parameters for _, kwargs in amg.calls)
    assert [p.result.calendar for p in result.phases] == expected


# --- 3. the response -----------------------------------------------------------


def test_scenarios_one_per_phase_and_the_first_is_the_top_level():
    engines = EntryPointEngines(
        _functions(calendar_answer=THREE_YEARS), carbon_models=CARBON_MODELS
    )
    body = client(engines).post(ROUTE, json=BODY).json()
    scenarios = body["scenarios"]
    assert [s["scenario_id"] for s in scenarios] == [
        "phase_1",
        "phase_2",
        "phase_3",
    ]
    assert [s["first_ag_year"] for s in scenarios] == [2001, 2002, 2003]
    first = scenarios[0]
    for key in ("outcome", "calendar", "result", "result_missing", "modules"):
        assert first[key] == body[key]
    for item in scenarios:
        ResultsPerRotation.model_validate(item["result"])
        RotationCalendar.model_validate(item["calendar"])
    assert "sources" not in first  # once, at the top


def _single(body: dict) -> None:
    (only,) = body["scenarios"]
    assert only["scenario_id"] == "phase_1"
    for key in ("outcome", "calendar", "result", "result_missing", "modules"):
        assert only[key] == body[key]


def test_ep2_not_built_answers_one_scenario():
    _, soil_fn, _ = fakes()
    engines = EntryPointEngines(
        EngineFunctions(compute_soil_loss=soil_fn), carbon_models=CARBON_MODELS
    )
    body = client(engines).post(ROUTE, json=BODY).json()
    _single(body)
    assert body["scenarios"][0]["first_ag_year"] is None


class NoClimate:
    source_id = "PLACEHOLDER_CLIMATE"
    contract = "site_data_climate"

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return climate_result(None)


def test_absent_input_answers_one_scenario():
    engines = EntryPointEngines(_functions(), carbon_models=CARBON_MODELS)
    body = client(engines, climate=NoClimate()).post(ROUTE, json=BODY).json()
    _single(body)
    assert body["scenarios"][0]["first_ag_year"] == 2001


def test_another_field_answers_one_scenario():
    other = SiteSoilSlope.model_validate(
        {**SOIL_SLOPE.model_dump(mode="json"), "field_id": "PLACEHOLDER-other"}
    )
    result = EntryPointEngines(_functions(), carbon_models=CARBON_MODELS).run(
        ROTATION, climate_result(), soil_result(other)
    )
    assert len(result.phases) == 1 and result.result is None


def test_an_infeasible_calendar_runs_once_unmoved():
    calendar_fn, soil_fn, water_fn = fakes(
        calendar_answer=calendar(feasible=False),
        soil_loss_answer=soil_loss("NOT_COMPUTABLE"),
        water_answer=water("NOT_COMPUTABLE"),
    )
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
        ),
        carbon_models=CARBON_MODELS,
    )
    body = client(engines).post(ROUTE, json=BODY).json()
    _single(body)
    assert len(soil_fn.calls) == 1


class OnePhaseEngines:
    """A ``RotationEngines`` that gives no phases: the route writes one."""

    def run(self, rotation, climate, soil_slope):
        return EnginesResult(
            calendar=None,
            result=None,
            result_missing=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER"),
        )


def test_an_implementation_without_phases_gets_phase_1_from_the_route():
    body = client(OnePhaseEngines()).post(ROUTE, json=BODY).json()
    _single(body)
    assert body["scenarios"][0]["first_ag_year"] is None


# --- 6. the engines of the repository -------------------------------------------


class ChainClimate:
    source_id = "PLACEHOLDER_chain_climate"
    contract = "site_data_climate"

    def __init__(self, data: SiteClimate) -> None:
        self.data = data

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=self.data,
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


def _example_rotation() -> dict[str, Any]:
    return json.loads(
        (
            ROOT
            / "contracts"
            / "rotation_definition"
            / "examples"
            / "PLACEHOLDER_rotation_definition.json"
        ).read_text(encoding="utf-8")
    )


def _rotation(kind: str) -> dict[str, Any]:
    """The rotation definition example, or a two-year variant of it.

    ``crossing``: its first component repeated one year later (c4), so the
    cycle lasts two years; c2 starts in April, before the agricultural year
    that starts in July, and has no end date: phase 2 has a crossing
    component. ``two_crops``: only c1, and c1 again one year later with the
    crop of c2 (PLACEHOLDER dates): two years, no crossing component.
    """
    rotation = _example_rotation()
    if kind == "example":
        return rotation
    first = rotation["components"][0]
    again = copy.deepcopy(first)
    again["position"] = len(rotation["components"]) + 1
    again["sowing"]["date"] = "2028-11-15"
    again["harvest"]["date"] = "2029-04-10"
    if kind == "crossing":
        again["component_id"] = "c4"
        rotation["components"].append(again)
    else:
        again["component_id"] = "c2"
        again["position"] = 2
        again["crop_id"] = rotation["components"][1]["crop_id"]
        rotation["components"] = [first, again]
    return rotation


def _chain_app() -> tuple[Any, SiteClimate]:
    examples = ROOT / "contracts" / "inputs" / "examples"
    climate = SiteClimate.model_validate_json(
        (examples / "PLACEHOLDER_chain_site_climate.json").read_text(encoding="utf-8")
    )
    series = climate.daily_series[0]
    app = create_app(
        [],
        climate=ChainClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            examples / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=series.start_date, end_date=series.end_date),
    )
    return app, climate


def _post(document: dict[str, Any]) -> dict[str, Any]:
    app, climate = _chain_app()
    body = {
        "site": {
            "case_id": document["case_id"],
            "field_id": document["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotation": document,
    }
    response = TestClient(app).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _repository_engines() -> None:
    found = discover_engine_functions()
    if found.build_rotation_calendar is None or found.compute_soil_loss is None:
        pytest.skip("the calendar or the soil-loss engine is not built")


# For each rotation: per phase, whether it has a result, else its reason.
EXPECTED_PHASES = {
    "example": [None],
    "crossing": [None, "NOT_COMPUTABLE"],
    "two_crops": [None, None],
}


@pytest.mark.parametrize("kind", list(EXPECTED_PHASES))
def test_the_engines_of_the_repository_answer_one_scenario_per_phase(kind):
    _repository_engines()
    answer = _post(_rotation(kind))
    expected = EXPECTED_PHASES[kind]
    scenarios = answer["scenarios"]
    assert [s["scenario_id"] for s in scenarios] == [
        scenario_id(i) for i in range(len(expected))
    ]
    for item, refused in zip(scenarios, expected, strict=True):
        if refused is None:
            assert item["result_missing"] is None, item["result_missing"]
            ResultsPerRotation.model_validate(item["result"])
            RotationCalendar.model_validate(item["calendar"])
        else:
            assert item["result"] is None and item["calendar"] is None
            assert item["result_missing"]["reason"] == refused
            assert item["result_missing"]["detail"].startswith("OPEN")


# --- the moved calendar repeated over the record (engine/calendar/repeat.py) --


def _laid_out(repeated: Any, ag_year: int) -> list[tuple[str, str]]:
    """(crop, month-day of start) of the components that start in one
    agricultural year of a repeated rotation."""
    start_month = repeated.start_month
    first = dt.date(ag_year, start_month, 1)
    last = dt.date(ag_year + 1, start_month, 1) - dt.timedelta(days=1)
    return sorted(
        (c.crop_id, c.start.strftime("%m-%d"))
        for c in repeated.components
        if c.start is not None and first <= c.start <= last
    )


NO_CROSSING = (
    THREE_YEARS,
    hand_calendar(
        "2001-11-15",
        "2003-04-10",
        [
            component("a", "2001-11-15", "2002-04-10"),
            component("b", "2002-11-15", "2003-04-10"),
        ],
    ),
)


@pytest.mark.parametrize("cal", NO_CROSSING, ids=["three-years", "two-years"])
def test_every_phase_lays_year_p_on_the_first_year_of_the_record(cal):
    repeat = pytest.importorskip("engine.calendar.repeat")
    length = repeat.cycle_length_years(cal)
    record = (dt.date(2001, 1, 1), dt.date(2012, 12, 31))  # PLACEHOLDER record
    original = repeat.repeat_over_record(cal, *record)
    first_year = original.ag_years[0]
    for phase in phase_calendars(cal):
        assert phase.calendar is not None
        assert repeat.cycle_length_years(phase.calendar) == length
        moved = repeat.repeat_over_record(phase.calendar, *record)
        assert moved.cycle_length == length
        assert moved.ag_years == original.ag_years
        # Agricultural year k of the phase holds what year k + p of the
        # calendar repeated over the record holds (dates keep month and day,
        # a 29 February aside).
        for k in range(len(original.ag_years) - length):
            expected = [
                (crop, "02-28" if day == "02-29" else day)
                for crop, day in _laid_out(original, first_year + k + phase.index)
            ]
            got = [
                (crop, "02-28" if day == "02-29" else day)
                for crop, day in _laid_out(moved, first_year + k)
            ]
            assert got == expected, (phase.scenario_id, k)


def test_the_real_ep1_lays_year_p_crops_on_the_first_year_of_the_record(monkeypatch):
    _repository_engines()
    soil_loss_module = pytest.importorskip("engine.erosion.soil_loss")
    seen: list[Any] = []
    real = soil_loss_module.repeat_over_record

    def spy(calendar_, start, end):
        repeated = real(calendar_, start, end)
        seen.append(repeated)
        return repeated

    monkeypatch.setattr(soil_loss_module, "repeat_over_record", spy)
    rotation = _rotation("two_crops")
    year_0_crop = rotation["components"][0]["crop_id"]
    year_1_crop = rotation["components"][1]["crop_id"]
    answer = _post(rotation)
    assert [s["scenario_id"] for s in answer["scenarios"]] == ["phase_1", "phase_2"]
    assert len(seen) == 2, "EP1 laid out the rotation once per phase"
    for repeated, crop in zip(seen, (year_0_crop, year_1_crop), strict=True):
        first_year = repeated.ag_years[0]
        assert [c for c, _ in _laid_out(repeated, first_year)] == [crop]


def test_module_has_no_engine_import():
    text = Path(phases.__file__).read_text(encoding="utf-8")
    assert "import engine" not in text and "from engine" not in text
