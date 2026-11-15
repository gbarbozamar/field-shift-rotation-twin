"""Acceptance tests of the phases of a rotation (D109, D141).

Run with ``uv run pytest api/test_phases.py`` from the repository root.

Every date here is a PLACEHOLDER date, written by hand; none is a real sowing
or harvest. The phase functions are fakes that return hand-written calendars:
the runner holds no copy of the phase rule, so no test here computes one. The
engines are fakes, except in the tests of section 6, which use the engines of
the repository only when they can be imported.

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
    CROSSING_D141,
    PHASE_FUNCTIONS_NOT_FOUND,
    PhaseFunctions,
    crossing_components,
    phase_calendars,
    scenario_id,
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
# agricultural year (2001, 2002, 2003); c ends on a 29 February.
THREE_YEARS = hand_calendar(
    "2001-09-01",
    "2004-02-29",
    [
        component("a", "2001-09-01", "2001-12-31"),
        component("b", "2002-09-01", "2003-02-28"),
        component("c", "2003-09-01", "2004-02-29"),
    ],
)
# Hand-written answers of a fake phase function for THREE_YEARS (PLACEHOLDER
# dates, not computed): phase 1 and phase 2 with c on 28 February.
THREE_YEARS_PHASES = {
    1: hand_calendar(
        "2001-07-01",
        "2004-06-30",
        [
            component("b", "2001-09-01", "2002-02-28"),
            component("c", "2002-09-01", "2003-02-28"),
            component("a", "2003-09-01", "2003-12-31"),
        ],
    ),
    2: hand_calendar(
        "2001-07-01",
        "2004-06-30",
        [
            component("c", "2001-09-01", "2002-02-28"),
            component("a", "2002-09-01", "2002-12-31"),
            component("b", "2003-09-01", "2004-02-28"),
        ],
    ),
}
ONE_YEAR = hand_calendar(
    "2001-09-01", "2002-02-28", [component("a", "2001-09-01", "2002-02-28")]
)


class FakePhases:
    """``phase_calendar`` and ``list_phases`` as issue #221 names them.

    ``count`` phases; phase ``p`` answers ``answers[p]``, else a copy of the
    calendar it was given (hand-written answers, never a computed rule).
    """

    def __init__(
        self,
        count: int,
        answers: dict[int, Any] | None = None,
        raises: bool = False,
    ) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.count = count
        self.answers = answers or {}
        self.raises = raises

    def phase_calendar(self, cal: RotationCalendar, p: int) -> RotationCalendar:
        self.calls.append(("phase_calendar", (cal, p)))
        if self.raises:
            raise ValueError("PLACEHOLDER: a defect of the phase function")
        if p in self.answers:
            return self.answers[p]
        return cal.model_copy(deep=True)

    def list_phases(self, cal: RotationCalendar) -> list[int]:
        self.calls.append(("list_phases", (cal,)))
        return list(range(self.count))

    def functions(self) -> PhaseFunctions:
        return PhaseFunctions(self.phase_calendar, self.list_phases, "PLACEHOLDER")


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


def dates(cal: RotationCalendar) -> list[tuple[str, str | None, str | None]]:
    return [
        (
            c.component_id,
            c.start.date.isoformat() if c.start.date else None,
            c.end.date.isoformat() if c.end.date else None,
        )
        for c in cal.components
    ]


def calendar_detail(modules: list[dict]) -> str:
    return {m["id"]: m["detail"] for m in modules}["calendar"] or ""


# --- 1. the phases come from the phase functions ------------------------------


def test_a_one_year_rotation_has_one_phase_the_calendar_unchanged():
    found = FakePhases(1)
    (only,) = phase_calendars(ONE_YEAR, found.functions())
    assert only.calendar is ONE_YEAR
    assert (only.index, only.scenario_id, only.first_ag_year) == (0, "phase_1", 2001)
    assert only.notes == ()
    assert [name for name, _ in found.calls] == ["list_phases"]


def test_each_phase_is_what_phase_calendar_returns():
    found = FakePhases(3, THREE_YEARS_PHASES)
    first, second, third = phase_calendars(THREE_YEARS, found.functions())
    assert first.calendar is THREE_YEARS  # phase 0 unchanged, never asked
    assert [args[1] for name, args in found.calls if name == "phase_calendar"] == [
        1,
        2,
    ]
    assert [p.scenario_id for p in (first, second, third)] == [
        "phase_1",
        "phase_2",
        "phase_3",
    ]
    assert [p.first_ag_year for p in (first, second, third)] == [2001, 2002, 2003]
    assert second.calendar == THREE_YEARS_PHASES[1]
    assert third.calendar == THREE_YEARS_PHASES[2]
    assert dates(third.calendar)[2] == ("b", "2003-09-01", "2004-02-28")
    for phase in (second, third):
        assert any("29 February" in note for note in phase.notes)
        assert not any("D141" in note for note in phase.notes)


def test_without_the_start_month_only_phase_1_runs_and_says_so():
    cal = hand_calendar(
        "2001-09-01",
        "2004-02-29",
        [c.model_dump() for c in THREE_YEARS.components],
        None,
    )
    found = FakePhases(3)
    (only,) = phase_calendars(cal, found.functions())
    assert only.calendar is cal and only.first_ag_year is None
    (note,) = only.notes
    assert "start month" in note and "2 phase(s)" in note
    assert "phase_calendar" not in [name for name, _ in found.calls]


# --- 2. without the phase functions: phase 1 only ------------------------------


def test_without_the_phase_functions_only_phase_1_runs_and_says_so():
    (only,) = phase_calendars(THREE_YEARS, None)
    assert only.calendar is THREE_YEARS and only.first_ag_year == 2001
    assert only.notes == (PHASE_FUNCTIONS_NOT_FOUND.format(phase="phase_1"),)


def test_the_route_without_the_phase_functions_answers_phase_1_with_its_note():
    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=THREE_YEARS)
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
    assert body["result"] is not None
    assert len(soil_fn.calls) == len(water_fn.calls) == 1
    detail = calendar_detail(body["modules"])
    assert PHASE_FUNCTIONS_NOT_FOUND.format(phase="phase_1") in detail


def test_with_one_of_the_two_missing_there_are_no_phase_functions():
    found = FakePhases(2)
    assert (
        phase_functions_of(EngineFunctions(phase_calendar=found.phase_calendar)) is None
    )
    assert phase_functions_of(EngineFunctions(list_phases=found.list_phases)) is None
    assert phase_functions_of(EngineFunctions()) is None


def test_lane_l1_functions_are_used_when_both_exist():
    found = FakePhases(2)
    chosen = phase_functions_of(_functions(found))
    assert chosen is not None and chosen.name == "engine.calendar.repeat"
    result = EntryPointEngines(_functions(found), carbon_models=CARBON_MODELS).run(
        ROTATION, climate_result(), soil_result()
    )
    assert [name for name, _ in found.calls] == ["list_phases", "phase_calendar"]
    assert found.calls[1][1][1] == 1  # phase 0 is never asked
    assert [p.scenario_id for p in result.phases] == ["phase_1", "phase_2"]


def test_discovery_finds_them_by_name_in_engine_calendar_repeat():
    repeat = pytest.importorskip("engine.calendar.repeat")
    found = discover_engine_functions()
    assert found.phase_calendar is getattr(repeat, "phase_calendar", None)
    assert found.list_phases is getattr(repeat, "list_phases", None)


def test_discovery_without_an_engine_package_gives_none(engines_hidden):
    found = discover_engine_functions()
    assert found.phase_calendar is None and found.list_phases is None
    assert phase_functions_of(found) is None


# --- 3. a component that spans the start of a phase (D141) ---------------------


def test_a_crossing_component_is_counted_on_the_calendar_of_ep2():
    # The PLACEHOLDER calendar: component 2 runs 2002-04-01 to 2002-10-31,
    # across the first day of the agricultural year 2002.
    example = calendar()
    assert crossing_components(example, 0) == 0
    assert crossing_components(example, 1) == 1
    cal = hand_calendar(
        "2001-09-01",
        "2003-02-28",
        [
            component("a", "2001-09-01", None),  # an end date missing
            component("b", "2002-09-01", "2003-02-28"),
        ],
    )
    assert crossing_components(cal, 1) == 1
    assert (
        crossing_components(THREE_YEARS, 1) == crossing_components(THREE_YEARS, 2) == 0
    )


def test_a_phase_with_a_crossing_component_is_computed_with_the_d141_note():
    # The fake returns the calendar unchanged (a form with no date missing):
    # whatever lane L1 returns is used, nothing is refused.
    example = calendar()
    _, second = phase_calendars(example, FakePhases(2).functions())
    assert second.calendar == example
    (note,) = second.notes
    assert note == CROSSING_D141.format(count=1)
    assert "D141" in note and "OPEN" not in note
    assert "PLACEHOLDER-component-2" not in note  # counts only, no identifier


def _d141_form() -> RotationCalendar:
    """A hand-written phase 2 of the PLACEHOLDER calendar in the form of D141:
    component 2 keeps its declared dates, starting before the first day of
    the phase's first year (2002-07-01); component 1 one cycle later; a date
    of component 3 missing with its reason. PLACEHOLDER dates, not computed."""
    document = calendar().model_dump(mode="json")
    first, second, third = document["components"]
    document["start_date"], document["end_date"] = "2002-04-01", "2004-06-30"
    first["start"]["date"], first["end"]["date"] = "2003-09-01", "2004-02-29"
    first["periods"][0]["start"]["date"] = "2003-09-01"
    first["periods"][0]["end"]["date"] = "2003-11-30"
    first["periods"][1]["start"]["date"] = "2003-12-01"
    first["periods"][1]["end"]["date"] = "2004-02-29"
    third["end"] = {
        "date": None,
        "missing": {"reason": "NOT_COMPUTABLE", "detail": "PLACEHOLDER"},
    }
    document["components"] = [second, third, first]
    return RotationCalendar.model_validate(document)


def test_a_calendar_in_the_d141_form_is_used_as_returned_and_computed():
    returned = _d141_form()
    found = FakePhases(2, {1: returned})
    calendar_fn, soil_fn, water_fn = fakes()
    functions = _functions(found)
    functions = EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_fn,
        compute_water_deficit_exposure=water_fn,
        phase_calendar=found.phase_calendar,
        list_phases=found.list_phases,
    )
    engines = EntryPointEngines(functions, carbon_models=CARBON_MODELS)
    response = client(engines).post(ROUTE, json=BODY)
    assert response.status_code == 200
    first, second = response.json()["scenarios"]
    assert [kwargs["calendar"] for _, kwargs in soil_fn.calls][1] == returned
    assert [kwargs["calendar"] for _, kwargs in water_fn.calls][1] == returned
    assert RotationCalendar.model_validate(second["calendar"]) == returned
    for item in (first, second):
        assert item["result_missing"] is None
        ResultsPerRotation.model_validate(item["result"])
    assert CROSSING_D141.format(count=1) in calendar_detail(second["modules"])
    assert "D141" not in calendar_detail(first["modules"])


def test_a_value_error_of_phase_calendar_is_a_defect_500():
    found = FakePhases(2, raises=True)
    engines = EntryPointEngines(_functions(found), carbon_models=CARBON_MODELS)
    response = client(engines).post(ROUTE, json=BODY)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "PLACEHOLDER: a defect" not in response.text
    with pytest.raises(ValueError):
        phase_calendars(calendar(), found.functions())


# --- 4. what the phase functions return is checked ------------------------------


def _changed(**update: Any) -> RotationCalendar:
    """The hand-written phase 2 of THREE_YEARS with one thing changed."""
    document = THREE_YEARS_PHASES[1].model_dump()
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
def test_a_phase_calendar_that_changes_more_than_dates_is_a_defect(answer):
    found = FakePhases(3, {1: answer, 2: answer})
    with pytest.raises(TypeError):
        phase_calendars(THREE_YEARS, found.functions())


@pytest.mark.parametrize("returned", [[1, 2], [], "012", 3, [0, 2]])
def test_phases_that_are_not_0_to_n_minus_1_are_a_defect(returned):
    found = FakePhases(3)
    functions = PhaseFunctions(
        found.phase_calendar, lambda cal: returned, "PLACEHOLDER"
    )
    with pytest.raises(TypeError):
        phase_calendars(THREE_YEARS, functions)


def test_any_sequence_0_to_n_minus_1_is_accepted():
    found = FakePhases(3, THREE_YEARS_PHASES)
    functions = PhaseFunctions(
        found.phase_calendar, lambda cal: (0, 1, 2), "PLACEHOLDER"
    )
    assert [p.calendar for p in phase_calendars(THREE_YEARS, functions)] == [
        THREE_YEARS,
        THREE_YEARS_PHASES[1],
        THREE_YEARS_PHASES[2],
    ]


# --- 5. each phase calls EP1, EP3 and EP5 on its calendar ---------------------


def test_each_phase_calls_ep1_ep3_and_ep5_once_with_its_calendar():
    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=THREE_YEARS)
    found = FakePhases(3, THREE_YEARS_PHASES)
    amg = Fake(balance())
    parameters: dict[str, dict] = {}
    engines = EntryPointEngines(
        EngineFunctions(
            build_rotation_calendar=calendar_fn,
            compute_soil_loss=soil_fn,
            compute_water_deficit_exposure=water_fn,
            run_amg=amg,
            phase_calendar=found.phase_calendar,
            list_phases=found.list_phases,
        ),
        carbon_models=CARBON_MODELS,
        parameters=parameters,
    )
    climate, soil = climate_result(chain_climate()), soil_result()
    result = engines.run(ROTATION, climate, soil)
    expected = [THREE_YEARS, THREE_YEARS_PHASES[1], THREE_YEARS_PHASES[2]]
    assert len(calendar_fn.calls) == 1
    for fake in (soil_fn, water_fn):
        assert [kwargs["calendar"] for _, kwargs in fake.calls] == expected
        assert all(kwargs["climate"] is climate.data for _, kwargs in fake.calls)
        assert all(kwargs["soil_slope"] is soil.data for _, kwargs in fake.calls)
        assert all(kwargs["parameters"] is parameters for _, kwargs in fake.calls)
    assert len(amg.calls) == 3
    assert all(kwargs["parameters"] is parameters for _, kwargs in amg.calls)
    assert [p.result.calendar for p in result.phases] == expected


# --- the response -----------------------------------------------------------------


def test_scenarios_one_per_phase_and_the_first_is_the_top_level():
    engines = EntryPointEngines(
        _functions(FakePhases(3, THREE_YEARS_PHASES), calendar_answer=THREE_YEARS),
        carbon_models=CARBON_MODELS,
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
    engines = EntryPointEngines(_functions(FakePhases(2)), carbon_models=CARBON_MODELS)
    body = client(engines, climate=NoClimate()).post(ROUTE, json=BODY).json()
    _single(body)
    assert body["scenarios"][0]["first_ag_year"] == 2001


def test_another_field_answers_one_scenario():
    other = SiteSoilSlope.model_validate(
        {**SOIL_SLOPE.model_dump(mode="json"), "field_id": "PLACEHOLDER-other"}
    )
    result = EntryPointEngines(
        _functions(FakePhases(2)), carbon_models=CARBON_MODELS
    ).run(ROTATION, climate_result(), soil_result(other))
    assert len(result.phases) == 1 and result.result is None


def test_an_infeasible_calendar_runs_once_unmoved():
    found = FakePhases(2)
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
            phase_calendar=found.phase_calendar,
            list_phases=found.list_phases,
        ),
        carbon_models=CARBON_MODELS,
    )
    body = client(engines).post(ROUTE, json=BODY).json()
    _single(body)
    assert len(soil_fn.calls) == 1
    assert found.calls == []
    assert PHASE_FUNCTIONS_NOT_FOUND.format(phase="phase_1") not in calendar_detail(
        body["modules"]
    )


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
    if found.phase_calendar is None or found.list_phases is None:
        pytest.skip("the phase functions of engine.calendar.repeat are not built")


# For each rotation: the number of phases, and the phases (0-based) whose
# first year a component spans (the D141 note). Every phase has a result.
EXPECTED_PHASES = {
    "example": (1, ()),
    "crossing": (2, (1,)),
    "two_crops": (2, ()),
}


@pytest.mark.parametrize("kind", list(EXPECTED_PHASES))
def test_the_engines_of_the_repository_answer_one_scenario_per_phase(kind):
    _repository_engines()
    answer = _post(_rotation(kind))
    count, crossing = EXPECTED_PHASES[kind]
    scenarios = answer["scenarios"]
    assert [s["scenario_id"] for s in scenarios] == [
        scenario_id(i) for i in range(count)
    ]
    for index, item in enumerate(scenarios):
        # D141: no phase is refused; each is computed on its calendar.
        assert item["result_missing"] is None, item["result_missing"]
        ResultsPerRotation.model_validate(item["result"])
        RotationCalendar.model_validate(item["calendar"])
        calendar_module = next(m for m in item["modules"] if m["id"] == "calendar")
        detail = calendar_module.get("detail") or ""
        assert ("D141" in detail) == (index in crossing), detail
        assert "OPEN" not in detail


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
