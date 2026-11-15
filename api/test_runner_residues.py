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
from api.test_phases import THREE_YEARS, _post, _rotation
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
    result = run(
        engine_functions(residues, amg, calendar_fn, soil_fn, water_fn),
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
    assert "OPEN 3 of the residue ledger" in detail
    assert producer.STOCK_UNIT in detail
    # The fallback note on crops is not written for the ledger's series.
    assert "crop_id is not a quantity identifier" not in detail


def test_series_in_the_unit_amg_requires_carry_no_open_note():
    item = series("placeholder_input_a").model_copy(
        update={"unit": producer.STOCK_UNIT}
    )
    item = AnnualCarbonInputSeries.model_validate(item.model_dump())
    amg = Fake(balance())
    result = run(engine_functions(Fake(ledger(item)), amg))
    detail = modules(result)["amg"].detail
    assert LEFT_UNCHANGED in detail
    assert "OPEN 3" not in detail


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
    assert "PROPOSED" in detail


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
    expected = runner.ledger_status(calls[0])
    assert (states["residues"]["state"], states["residues"]["reason"]) == (
        expected.state,
        expected.reason,
    )
    assert LEFT_UNCHANGED in (states["amg"].get("detail") or "")
