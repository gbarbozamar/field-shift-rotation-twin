"""Acceptance tests of EP4 in the runner (unit l2/runner-residues).

Run with ``uv run pytest api/test_runner_residues.py`` from the repository root.

``contracts/residue_ledger/`` may not be in the repository, so EP4 is a fake
that returns a ``FakeLedger``, and the runner's seam ``residue_ledger_type``
is replaced by that class. The series inside the fake ledger are real
``AnnualCarbonInputSeries`` built from the PLACEHOLDER example of
contracts/carbon_forcing/; no number and no unit is written here, the years
are those of the forcing horizon, computed. The tests that use the real EP4
run only when it can be imported.

Status: PROPOSED test cases (blueprint section 3.7).
"""

from __future__ import annotations

import copy
import importlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from api import carbon_forcing as producer
from api import engines as runner
from api.engines import EngineFunctions, EntryPointEngines, discover_engine_functions
from api.test_engines import (
    BODY,
    CALENDAR_DOCUMENT,
    CARBON_MODELS,
    ROTATION,
    ROUTE,
    ChainClimate,
    Fake,
    balance,
    calendar,
    chain_climate,
    client,
    climate_result,
    example,
    fakes,
    soil_result,
    write_package,
)
from api.test_phases import (
    THREE_YEARS,
    THREE_YEARS_PHASES,
    FakePhases,
    _post,
    _rotation,
)
from contracts.carbon_forcing import AnnualCarbonInputSeries, CarbonForcing
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Value
from contracts.rotation_definition import RotationDefinition

TEMPLATE = example("carbon_forcing", "PLACEHOLDER_carbon_forcing.json")[
    "annual_carbon_inputs"
][0]
# The placeholder unit of the example, which is not the unit AMG requires.
LEDGER_UNIT = TEMPLATE["unit"]
LEFT_UNCHANGED = "copied unchanged from engine.residues.build_residue_ledger"


@dataclass
class FakeLedger:
    """What the runner reads of a ``ResidueLedger``; nothing else."""

    case_id: str = CALENDAR_DOCUMENT["case_id"]
    field_id: str = CALENDAR_DOCUMENT["field_id"]
    rotation_id: str = CALENDAR_DOCUMENT["rotation_id"]
    years_missing: InputMissing | None = None
    components: list[Any] = field(default_factory=list)
    annual_carbon_inputs: list[AnnualCarbonInputSeries] = field(default_factory=list)


class FakeComponent(BaseModel):
    """A component entry: one identifier and two values, found by their type."""

    component_id: str
    first: Value
    second: Value


def component(*reasons: str | None) -> FakeComponent:
    """Each value present (the example's number) or missing with its reason."""
    value = TEMPLATE["years"][0]["value"]
    items = [
        Value(
            value=value,
            unit=LEDGER_UNIT,
            provenance=TEMPLATE["provenance"],
            source=TEMPLATE["source"],
            range_missing=InputMissing(**TEMPLATE["range_missing"]),
        )
        if reason is None
        else Value(
            value=None,
            unit=LEDGER_UNIT,
            missing=InputMissing(reason=reason, detail="PLACEHOLDER"),
        )
        for reason in reasons
    ]
    return FakeComponent(component_id="PLACEHOLDER", first=items[0], second=items[1])


@pytest.fixture(autouse=True)
def fake_ledger_type(monkeypatch):
    monkeypatch.setattr(runner, "residue_ledger_type", lambda: FakeLedger)


def horizon_years() -> tuple[int, int]:
    """The agricultural years of the forcing on the chain climate, computed."""
    start = calendar().ag_year_start.month
    years = producer.whole_ag_years(start, *producer.record_period(chain_climate()))
    assert years is not None
    return years


def series(
    quantity: str,
    *,
    missing_reason: str | None = None,
    years: tuple[int, int] | None = None,
) -> AnnualCarbonInputSeries:
    """One series over ``years``, every year the example's value, or missing."""
    first, last = years if years is not None else horizon_years()
    document = copy.deepcopy(TEMPLATE)
    document.update(quantity=quantity, first_ag_year=first, last_ag_year=last)
    if missing_reason is None:
        value = TEMPLATE["years"][0]["value"]
        document["years"] = [
            {"ag_year": y, "value": value} for y in range(first, last + 1)
        ]
    else:
        for key in ("provenance", "source", "range_missing", "assumption"):
            document.pop(key, None)
        document["years"] = [
            {
                "ag_year": y,
                "value": None,
                "missing": {"reason": missing_reason, "detail": "PLACEHOLDER"},
            }
            for y in range(first, last + 1)
        ]
    return AnnualCarbonInputSeries.model_validate(document)


def ledger(*items: AnnualCarbonInputSeries, **fields: Any) -> FakeLedger:
    return FakeLedger(annual_carbon_inputs=list(items), **fields)


def engine_functions(residues: Any, amg: Any = None, *parts: Any) -> EngineFunctions:
    calendar_fn, soil_fn, water_fn = parts or fakes()
    return EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_fn,
        compute_water_deficit_exposure=water_fn,
        build_residue_ledger=residues,
        run_amg=amg,
    )


def run(functions: EngineFunctions, *, parameters: dict | None = None, **inputs):
    engines = EntryPointEngines(
        functions, carbon_models=CARBON_MODELS, parameters=parameters
    )
    return engines.run(
        ROTATION,
        inputs.get("climate", climate_result(chain_climate())),
        inputs.get("soil", soil_result()),
    )


def modules(result) -> dict[str, Any]:
    return {m.id: m for m in result.modules}


def identifier_crops() -> Any:
    """The calendar example with crops that are quantity identifiers."""
    document = copy.deepcopy(CALENDAR_DOCUMENT)
    for index, item in enumerate(document["components"]):
        item["crop_id"] = f"placeholder_crop_{index % 2}"
    return type(calendar()).model_validate(document)


# --- 1. discovery and the guard of EP6 -----------------------------------------


def test_ep4_is_discovered_by_its_name(tmp_path, monkeypatch, no_engine_modules):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/residues/__init__.py": (
                "def build_residue_ledger(rotation, calendar, climate, *, parameters): ...\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found = discover_engine_functions()
    assert found.build_residue_ledger is (
        importlib.import_module("engine.residues").build_residue_ledger
    )
    assert runner.RESIDUES in runner.DISCOVERED


def test_ep4_absent_is_not_built(engines_hidden):
    assert discover_engine_functions().build_residue_ledger is None


def test_the_runner_does_not_import_the_ledger_contract_at_load():
    text = Path(runner.__file__).read_text(encoding="utf-8")
    assert "from contracts.residue_ledger" not in text
    assert "import contracts.residue_ledger" not in text


def test_the_seam_imports_the_contract_lazily(monkeypatch):
    monkeypatch.undo()  # the real seam, not the fake class
    try:
        importlib.import_module("contracts.residue_ledger")
    except ModuleNotFoundError:
        with pytest.raises(ModuleNotFoundError):
            runner.residue_ledger_type()
    else:
        assert runner.residue_ledger_type().__name__ == "ResidueLedger"


# --- 2. the call ---------------------------------------------------------------


def test_ep4_is_called_once_per_phase_with_its_calendar_by_keyword():
    calendar_fn, soil_fn, water_fn = fakes(calendar_answer=THREE_YEARS)
    residues = Fake(ledger())
    amg = Fake(balance())
    parameters: dict[str, dict] = {}
    climate = climate_result(chain_climate())
    phases = FakePhases(3, THREE_YEARS_PHASES)
    result = run(
        replace(
            engine_functions(residues, amg, calendar_fn, soil_fn, water_fn),
            phase_calendar=phases.phase_calendar,
            list_phases=phases.list_phases,
        ),
        parameters=parameters,
        climate=climate,
    )
    assert len(residues.calls) == len(result.phases) == 3
    ((definition,), _) = calendar_fn.calls[0]
    assert isinstance(definition, RotationDefinition)
    for (args, kwargs), phase, soil_call in zip(
        residues.calls, result.phases, soil_fn.calls, strict=True
    ):
        assert args == ()
        assert set(kwargs) == {"rotation", "calendar", "climate", "parameters"}
        assert kwargs["rotation"] is definition
        assert kwargs["calendar"] is phase.result.calendar
        assert kwargs["calendar"] is soil_call[1]["calendar"]  # as EP1 gets it
        assert kwargs["climate"] is climate.data
        assert kwargs["parameters"] is parameters


def test_ep4_runs_after_ep3_and_before_ep5():
    order: list[str] = []

    def recording(name: str, answer: Any):
        def call(*args, **kwargs):
            order.append(name)
            return answer

        return call

    calendar_fn, soil_fn, water_fn = fakes()
    run(
        engine_functions(
            recording("EP4", ledger()),
            recording("EP5", balance()),
            recording("EP2", calendar_fn.answer),
            recording("EP1", soil_fn.answer),
            recording("EP3", water_fn.answer),
        )
    )
    assert order == ["EP2", "EP1", "EP3", "EP4", "EP5"]


def test_ep4_is_called_for_an_infeasible_calendar():
    residues = Fake(ledger())
    run(engine_functions(residues, None, *fakes(calendar_answer=calendar(False))))
    assert len(residues.calls) == 1


@pytest.mark.parametrize("absent", ["climate", "soil"])
def test_ep4_is_not_called_when_an_input_is_absent(absent):
    residues = Fake(ledger())
    inputs = {absent: (climate_result if absent == "climate" else soil_result)(None)}
    result = run(engine_functions(residues, Fake(balance())), **inputs)
    assert residues.calls == []
    assert (modules(result)["residues"].state, modules(result)["residues"].reason) == (
        "not_available",
        "MISSING_INPUT",
    )


def test_ep4_that_raises_is_500():
    engines = EntryPointEngines(
        engine_functions(Fake(raises=True), Fake(balance())),
        carbon_models=CARBON_MODELS,
    )
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 500
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text


@pytest.mark.parametrize(
    "wrong",
    [{"annual_carbon_inputs": []}, "other-rotation", "other-field"],
    ids=["dict", "other-rotation", "other-field"],
)
def test_ep4_returning_the_wrong_thing_is_500(wrong):
    if wrong == "other-rotation":
        wrong = ledger(rotation_id="PLACEHOLDER_OTHER_ROTATION")
    elif wrong == "other-field":
        wrong = ledger(field_id="PLACEHOLDER_OTHER_FIELD")
    functions = engine_functions(Fake(wrong), Fake(balance()))
    with pytest.raises(TypeError):
        run(functions)
    engines = EntryPointEngines(functions, carbon_models=CARBON_MODELS)
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


# --- 3. the forcing EP5 receives -----------------------------------------------


def test_the_series_reach_ep5_unchanged_in_their_unit():
    items = (
        series("placeholder_input_a"),
        series("placeholder_input_b", missing_reason="MISSING_INPUT"),
    )
    amg = Fake(balance())
    result = run(engine_functions(Fake(ledger(*items)), amg))
    ((forcing,), _) = amg.calls[0]
    assert isinstance(forcing, CarbonForcing)
    assert forcing.annual_carbon_inputs == list(items)
    assert all(a is b for a, b in zip(forcing.annual_carbon_inputs, items))
    assert {s.unit for s in forcing.annual_carbon_inputs} == {LEDGER_UNIT}
    detail = modules(result)["amg"].detail
    assert LEFT_UNCHANGED in detail
    assert "do not follow D147" in detail and "OPEN" not in detail
    assert "AMG refuses them" in detail
    assert producer.STOCK_UNIT in detail
    # The example's crops are not identifiers: the note is kept with a ledger.
    crops = {c["crop_id"] for c in CALENDAR_DOCUMENT["components"]}
    assert runner.crops_left_out_detail(len(crops)) in detail


def test_series_in_the_unit_amg_requires_carry_no_unit_note():
    item = series("placeholder_input_a").model_copy(
        update={"unit": producer.STOCK_UNIT}
    )
    item = AnnualCarbonInputSeries.model_validate(item.model_dump())
    amg = Fake(balance())
    result = run(engine_functions(Fake(ledger(item)), amg))
    detail = modules(result)["amg"].detail
    assert LEFT_UNCHANGED in detail
    assert "D147" not in detail


def test_not_computable_series_are_copied_and_named():
    items = (
        series("placeholder_input_a"),
        series("placeholder_cover_input", missing_reason="NOT_COMPUTABLE"),
    )
    amg = Fake(balance())
    result = run(engine_functions(Fake(ledger(*items)), amg))
    ((forcing,), _) = amg.calls[0]
    assert forcing.annual_carbon_inputs == list(items)
    detail = modules(result)["amg"].detail
    assert "1 series carry NOT_COMPUTABLE years" in detail
    assert "the reason the series itself gives" in detail
    assert "cover" not in detail and "PROPOSED" in detail


def test_a_series_over_other_years_is_500():
    first, last = horizon_years()
    wrong = series("placeholder_input_a", years=(first + 1, last + 1))
    functions = engine_functions(Fake(ledger(wrong)), Fake(balance()))
    with pytest.raises(TypeError):
        run(functions)
    engines = EntryPointEngines(functions, carbon_models=CARBON_MODELS)
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 500


def test_a_ledger_without_years_gives_the_per_crop_series_with_its_reason():
    reason = InputMissing(reason="NO_COVERAGE", detail="PLACEHOLDER: no whole year")
    amg = Fake(balance())
    result = run(
        engine_functions(
            Fake(FakeLedger(years_missing=reason)),
            amg,
            *fakes(calendar_answer=identifier_crops()),
        )
    )
    ((forcing,), _) = amg.calls[0]
    crops = producer.crop_origins(identifier_crops())
    assert [s.origin for s in forcing.annual_carbon_inputs] == crops
    assert [s.quantity for s in forcing.annual_carbon_inputs] == crops
    for item in forcing.annual_carbon_inputs:
        assert item.unit == producer.STOCK_UNIT
        assert all(year.missing == reason for year in item.years)
    residues = modules(result)["residues"]
    assert (residues.state, residues.reason, residues.detail) == (
        "not_available",
        reason.reason,
        reason.detail,
    )
    assert LEFT_UNCHANGED not in (modules(result)["amg"].detail or "")


def test_the_producer_without_a_ledger_keeps_the_d122_text():
    forcing = producer.build_carbon_forcing(
        identifier_crops(), chain_climate(), soil_result().data
    )
    assert isinstance(forcing, CarbonForcing)
    for item in forcing.annual_carbon_inputs:
        assert all(
            year.missing.detail == producer.CARBON_INPUTS_OPEN for year in item.years
        )


def test_the_ledger_is_not_in_the_response():
    engines = EntryPointEngines(
        engine_functions(Fake(ledger(series("placeholder_input_a"))), Fake(balance())),
        carbon_models=CARBON_MODELS,
    )
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text
    text = json.dumps(response.json())
    assert "placeholder_input_a" not in text
    assert "annual_carbon_inputs" not in text


# --- 4. the state of the residues module ----------------------------------------


@pytest.mark.parametrize(
    "reasons, state",
    [
        ((None,), "available"),
        ((None, "MISSING_INPUT"), "degraded"),
        (("MISSING_INPUT", "NOT_COMPUTABLE"), "not_available"),
    ],
)
def test_the_residues_state_comes_from_the_ledger_values(reasons, state):
    items = [
        series(f"placeholder_input_{i}", missing_reason=reason)
        for i, reason in enumerate(reasons)
    ]
    result = run(engine_functions(Fake(ledger(*items)), Fake(balance())))
    residues = modules(result)["residues"]
    assert residues.state == state
    first = next((r for r in reasons if r is not None), None)
    assert residues.reason == first


def test_the_values_of_the_components_are_counted_too():
    item = series("placeholder_input_a")
    result = run(
        engine_functions(
            Fake(
                FakeLedger(
                    components=[component(None, "MISSING_INPUT")],
                    annual_carbon_inputs=[item],
                )
            ),
            Fake(balance()),
        )
    )
    residues = modules(result)["residues"]
    assert (residues.state, residues.reason) == ("degraded", "MISSING_INPUT")
    assert residues.detail == f"1 of {2 + len(item.years)} values are missing"


def test_components_without_series_are_counted():
    result = run(
        engine_functions(
            Fake(FakeLedger(components=[component("MISSING_INPUT", "MISSING_INPUT")])),
            Fake(balance()),
        )
    )
    residues = modules(result)["residues"]
    assert (residues.state, residues.reason) == ("not_available", "MISSING_INPUT")


def test_a_ledger_with_no_value_is_not_available():
    result = run(engine_functions(Fake(ledger()), Fake(balance())))
    residues = modules(result)["residues"]
    assert (residues.state, residues.reason, residues.detail) == (
        "not_available",
        "NOT_AVAILABLE",
        runner.LEDGER_EMPTY,
    )


def test_ep4_built_and_ep5_not_built_name_each_engine():
    result = run(engine_functions(Fake(ledger(series("placeholder_input_a"))), None))
    states = modules(result)
    assert states["residues"].state == "available"
    assert states["amg"].detail == f"{runner.NOT_BUILT}: engine.amg.run_amg"
    rows = [r for r in result.result.soil_carbon_trend if r.carbon_model == "amg"]
    assert rows and all("engine.amg.run_amg" in r.missing.detail for r in rows)


def test_ep4_not_built_is_the_answer_before_this_unit():
    amg = Fake(balance())
    without = run(engine_functions(None, amg))
    states = modules(without)
    assert states["residues"].detail == (
        f"{runner.NOT_BUILT}: engine.residues.build_residue_ledger"
    )
    nothing = run(engine_functions(None, None))
    assert all(
        modules(nothing)[m].detail == runner.CARBON_NOT_BUILT
        for m in runner.CARBON_MODULE_IDS
    )


# --- 5. the engines of the repository, when they exist --------------------------


def test_the_real_ep4_and_ep5_answer_200(monkeypatch):
    found = discover_engine_functions()
    if found.build_residue_ledger is None or found.run_amg is None:
        pytest.skip("engine.residues or engine.amg is not built")
    monkeypatch.undo()  # the real ResidueLedger
    real = found.build_residue_ledger
    calls: list[Any] = []

    def recording(**kwargs: Any) -> Any:
        answer = real(**kwargs)
        calls.append(answer)
        return answer

    monkeypatch.setattr(
        "api.app.discover_engine_functions",
        lambda: replace(found, build_residue_ledger=recording),
    )
    answer = _post(_rotation("two_crops"))  # the chain example, the same field
    assert calls and len(calls) == len(answer["scenarios"])
    states = {m["id"]: m for m in answer["modules"]}
    # With the empty catalogue no record is there: some values missing, the
    # reason MISSING_INPUT, never a not-built or another-field answer.
    assert states["residues"]["state"] in ("degraded", "not_available")
    assert states["residues"]["reason"] == "MISSING_INPUT"
    assert runner.NOT_BUILT not in (states["residues"].get("detail") or "")
    assert runner.OTHER_FIELD not in (states["residues"].get("detail") or "")
    assert states["amg"]["state"] == "not_available"
    assert "engine.residues.build_residue_ledger" in (states["amg"].get("detail") or "")


# --- 6. remarks of the review ----------------------------------------------------


def mixed_crops() -> Any:
    """The calendar example with one crop an identifier and one not."""
    document = copy.deepcopy(CALENDAR_DOCUMENT)
    first = document["components"][0]["crop_id"]
    for item in document["components"]:
        if item["crop_id"] == first:
            item["crop_id"] = "placeholder_crop_a"
    return type(calendar()).model_validate(document)


def test_with_a_ledger_and_no_identifier_crop_the_note_is_kept():
    amg = Fake(balance())
    result = run(engine_functions(Fake(ledger()), amg))
    ((forcing,), _) = amg.calls[0]
    assert forcing.annual_carbon_inputs == []
    detail = modules(result)["amg"].detail
    crops = producer.crops_left_out(calendar())
    assert crops
    assert runner.crops_left_out_detail(len(crops)) in detail
    assert "wrote no carbon-input series" in detail


def test_with_a_ledger_and_mixed_crops_the_note_counts_the_others():
    item = series("placeholder_crop_a_input").model_copy(
        update={"origin": "placeholder_crop_a"}
    )
    item = AnnualCarbonInputSeries.model_validate(item.model_dump())
    amg = Fake(balance())
    result = run(
        engine_functions(Fake(ledger(item)), amg, *fakes(calendar_answer=mixed_crops()))
    )
    ((forcing,), _) = amg.calls[0]
    assert forcing.annual_carbon_inputs == [item]
    detail = modules(result)["amg"].detail
    left_out = producer.crops_left_out(mixed_crops())
    assert len(left_out) == 1
    assert runner.crops_left_out_detail(1) in detail
    assert LEFT_UNCHANGED in detail


def test_ep4_is_not_called_for_site_data_of_another_field():
    residues = Fake(ledger())
    other = chain_climate().model_copy(update={"field_id": "PLACEHOLDER_OTHER_FIELD"})
    result = run(
        engine_functions(residues, Fake(balance())), climate=climate_result(other)
    )
    assert residues.calls == []
    state = modules(result)["residues"]
    assert (state.state, state.reason) == ("not_available", "MISSING_INPUT")
    assert state.detail.startswith(runner.OTHER_FIELD)


def test_ep4_is_not_called_when_phase_calendar_raises():
    # D141: no phase is refused; a ValueError of the phase function is a
    # defect, raised before any engine after EP2 is called.
    phases = FakePhases(2, raises=True)
    calendar_fn, soil_fn, water_fn = fakes()
    residues = Fake(ledger())
    functions = replace(
        engine_functions(residues, Fake(balance()), calendar_fn, soil_fn, water_fn),
        phase_calendar=phases.phase_calendar,
        list_phases=phases.list_phases,
    )
    with pytest.raises(ValueError):
        run(functions)
    assert residues.calls == soil_fn.calls == []


# --- 7. a rotation with a lead-in cycle (D141), through the real engines ----------


def test_wheat_soybean_maize_with_a_lead_in_answers_200(monkeypatch):
    """Wheat / second-crop soybean, then maize, answers 200 in both phases.

    The rotation definition example with three ``grain`` components, start
    month 7 as in the example. Every date is a PLACEHOLDER: the years mean
    nothing, and the month and day are those of the row USER-AP (D72) of
    docs/SCIENCE_DECISIONS.md. The wheat is sown before the start month, so
    each phase has a cycle before the first that ends inside the record: the
    lead-in of D141 (point 13 of engine/calendar/repeat.py). EP4 writes its
    component as cycle -1, which the ledger contract admits (D160).

    Site data: the PLACEHOLDER chain examples, posted as ``_post`` of
    api/test_phases.py posts them. Catalogue: ``params/records/``, as the
    service loads it. No number is asserted.
    """
    from fastapi.testclient import TestClient

    from adapters.example_soil_slope import ExampleSoilSlopeSource
    from api.config import PARAMETERS_FOLDER, load_parameters
    from api.main import create_app
    from api.ports import RunSettings
    from api.test_phases import ROOT
    from api.test_phases import ChainClimate as ChainExampleClimate
    from contracts.inputs import SiteClimate

    found = discover_engine_functions()
    if found.build_residue_ledger is None:
        pytest.skip("engine.residues is not built")
    if found.phase_calendar is None or found.list_phases is None:
        pytest.skip("the phase functions of engine.calendar.repeat are not built")
    monkeypatch.undo()  # the real ResidueLedger
    real = found.build_residue_ledger
    ledgers: list[Any] = []

    def recording(**kwargs: Any) -> Any:
        answer = real(**kwargs)
        ledgers.append(answer)
        return answer

    monkeypatch.setattr(
        "api.app.discover_engine_functions",
        lambda: replace(found, build_residue_ledger=recording),
    )

    # PLACEHOLDER years; month and day of USER-AP (D72). Crop words of the
    # catalogue.
    placeholder_dates = [
        ("wheat", "2027-05-25", "2027-12-05"),
        ("soybean", "2027-12-10", "2028-05-10"),
        ("maize", "2028-09-20", "2029-04-20"),
    ]
    rotation = copy.deepcopy(ROTATION)
    template = rotation["components"][0]
    rotation["components"] = []
    for position, (crop, sowing, harvest) in enumerate(placeholder_dates, start=1):
        item = copy.deepcopy(template)
        item.update(
            component_id=f"c{position}",
            position=position,
            crop_id=crop,
            purpose="grain",
        )
        item["sowing"]["date"], item["harvest"]["date"] = sowing, harvest
        rotation["components"].append(item)

    examples = ROOT / "contracts" / "inputs" / "examples"
    climate = SiteClimate.model_validate_json(
        (examples / "PLACEHOLDER_chain_site_climate.json").read_text(encoding="utf-8")
    )
    record = climate.daily_series[0]
    app = create_app(
        [],
        climate=ChainExampleClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            examples / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=record.start_date, end_date=record.end_date),
        parameters=load_parameters(PARAMETERS_FOLDER),
    )
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotation": rotation,
    }
    response = TestClient(app, raise_server_exceptions=False).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    scenarios = response.json()["scenarios"]
    assert [item["scenario_id"] for item in scenarios] == ["phase_1", "phase_2"]
    assert len(ledgers) == len(scenarios)  # EP4 once per phase

    lead_in_crops = []
    for scenario, ledger in zip(scenarios, ledgers, strict=True):
        states = {m["id"]: m for m in scenario["modules"]}
        assert runner.NOT_BUILT not in (states["residues"].get("detail") or "")
        (lead_in,) = [item for item in ledger.components if item.cycle == -1]
        lead_in_crops.append(lead_in.crop_id)
        assert record.start_date <= lead_in.harvest.date <= record.end_date
        assert lead_in.ag_year == ledger.first_ag_year
        # Its harvest enters the first year of its crop's series: a number, or
        # missing because a record is, never a zero and never "not laid out".
        of_its_crop = [
            series
            for series in ledger.annual_carbon_inputs
            # D194: <crop>_aboveground and <crop>_belowground
            if series.origin.rsplit("_", 1)[0] == lead_in.crop_id
        ]
        assert of_its_crop
        for series in of_its_crop:
            first = series.years[0]
            assert first.ag_year == ledger.first_ag_year
            if first.value is not None:
                assert first.value != 0
                continue
            assert first.missing.reason == "MISSING_INPUT"
            assert "before the first cycle" not in first.missing.detail
            assert "parameter" in first.missing.detail  # it names a record
            assert repr(lead_in.crop_id) in first.missing.detail
    # Phase 1 starts with the wheat, so the cycle before it ends with the maize;
    # phase 2 starts after the wheat, which then crosses into its first year.
    assert lead_in_crops == ["maize", "wheat"]


# --- 8. D194: the origin of each series, through the runner ---------------------


# The two rotations of the demonstration (D128) on PLACEHOLDER years, with the
# month and day of the row USER-AP (D72) of docs/SCIENCE_DECISIONS.md, as in
# section 7. No number is asserted.
DEMO_ROTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "soybean-winter-fallow": [("soybean", "2027-11-15", "2028-05-05")],
    "wheat-soybean-maize": [
        ("wheat", "2027-05-25", "2027-12-05"),
        ("soybean", "2027-12-10", "2028-05-10"),
        ("maize", "2028-09-20", "2029-04-20"),
    ],
}


def _post_demo(name: str) -> dict[str, Any]:
    """POST one demo rotation through the app with the catalogue the service
    loads (``params/records/``); EP4 is what ``discover_engine_functions``
    gives, which the caller patches."""
    from fastapi.testclient import TestClient

    from adapters.example_soil_slope import ExampleSoilSlopeSource
    from api.config import PARAMETERS_FOLDER, load_parameters
    from api.main import create_app
    from api.ports import RunSettings
    from api.test_phases import ROOT
    from api.test_phases import ChainClimate as ChainExampleClimate
    from contracts.inputs import SiteClimate

    rotation = copy.deepcopy(ROTATION)
    template = rotation["components"][0]
    rotation["components"] = []
    for position, (crop, sowing, harvest) in enumerate(DEMO_ROTATIONS[name], start=1):
        item = copy.deepcopy(template)
        item.update(
            component_id=f"c{position}",
            position=position,
            crop_id=crop,
            purpose="grain",
        )
        item["sowing"]["date"], item["harvest"]["date"] = sowing, harvest
        rotation["components"].append(item)
    examples = ROOT / "contracts" / "inputs" / "examples"
    climate = SiteClimate.model_validate_json(
        (examples / "PLACEHOLDER_chain_site_climate.json").read_text(encoding="utf-8")
    )
    record = climate.daily_series[0]
    app = create_app(
        [],
        climate=ChainExampleClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            examples / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=record.start_date, end_date=record.end_date),
        parameters=load_parameters(PARAMETERS_FOLDER),
    )
    body = {
        "site": {
            "case_id": rotation["case_id"],
            "field_id": rotation["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotation": rotation,
    }
    response = TestClient(app, raise_server_exceptions=False).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_rotations_answer_as_before_the_origin_split(monkeypatch):
    """D194, unit l1/residues-origin-split-d194. For both demo rotations, and
    both phases of the wheat rotation, through the real EP4 and EP5 with the
    catalogue the service loads:

    - every series EP4 writes has the origin <crop>_aboveground (retained
      aboveground carbon) or <crop>_belowground (root and rhizodeposit carbon);
    - the response is the same, field for field, as the one given by the same
      ledgers with the origin of the rule before D194 (the crop), written here.

    The response does not change because the catalogue holds no humification
    record yet (the records of D194 wait for a person's signature): AMG's
    values are missing before any coefficient is used.
    """
    found = discover_engine_functions()
    if found.build_residue_ledger is None or found.run_amg is None:
        pytest.skip("engine.residues or engine.amg is not built")
    real = found.build_residue_ledger
    for name, phases in (
        ("soybean-winter-fallow", ["phase_1"]),
        ("wheat-soybean-maize", ["phase_1", "phase_2"]),
    ):
        # The rule of D194, with the real ResidueLedger.
        monkeypatch.undo()
        ledgers: list[Any] = []

        def recording(**kwargs: Any) -> Any:
            answer = real(**kwargs)
            ledgers.append(answer)
            return answer

        monkeypatch.setattr(
            "api.app.discover_engine_functions",
            lambda: replace(found, build_residue_ledger=recording),
        )
        split = _post_demo(name)
        assert [s["scenario_id"] for s in split["scenarios"]] == phases
        assert len(ledgers) == len(phases)
        for ledger in ledgers:
            assert ledger.annual_carbon_inputs
            for item in ledger.annual_carbon_inputs:
                crop = item.quantity.split("_grain_")[0]
                group = (
                    "aboveground"
                    if item.quantity.endswith("_aboveground_carbon_retained")
                    else "belowground"
                )
                assert item.origin == f"{crop}_{group}"

        # The previous rule: the same ledgers, origin = crop. The real ledger
        # contract rejects that origin now, so the runner reads a FakeLedger.
        monkeypatch.undo()
        monkeypatch.setattr(runner, "residue_ledger_type", lambda: FakeLedger)

        previous_calls: list[Any] = []

        def previous(**kwargs: Any) -> Any:
            answer = real(**kwargs)
            previous_calls.append(answer)
            return FakeLedger(
                case_id=answer.case_id,
                field_id=answer.field_id,
                rotation_id=answer.rotation_id,
                years_missing=answer.years_missing,
                components=list(answer.components),
                annual_carbon_inputs=[
                    item.model_copy(
                        update={"origin": item.quantity.split("_grain_")[0]}
                    )
                    for item in answer.annual_carbon_inputs
                ],
            )

        monkeypatch.setattr(
            "api.app.discover_engine_functions",
            lambda: replace(found, build_residue_ledger=previous),
        )
        assert _post_demo(name) == split
        assert len(previous_calls) == len(phases)  # the previous rule did run
