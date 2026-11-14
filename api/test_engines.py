"""Acceptance tests of the engine runner ``api/engines.py`` (unit l2/engine-runner).

Run with ``uv run pytest api/`` from the repository root.

The fake engine functions are written here and build their returns only
through the contract models, from the PLACEHOLDER examples of contracts/. No
number is written here; carbon model identifiers are placeholders, or the decided
``amg`` and ``rothc`` (issue #18) where the default app is tested. A fake
``engine`` package exists only under ``tmp_path``.

Status: PROPOSED test cases (blueprint section 3.7).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SoilSlopeResult, SourceInfo
from api import engines as runner
from api.engines import (
    DEFAULT_CARBON_MODELS,
    MODULE_IDS,
    EngineFunctions,
    EntryPointEngines,
    ValueCount,
    calendar_status,
    count_values,
    discover_engine_functions,
    module_status_of,
    result_values,
)
from api.main import create_app
from api.ports import RotationEngines, RunSettings
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.results.models import (
    TREND_COMPUTATIONS,
    Missing,
    ResultsPerRotation,
    SoilLossResults,
    WaterDeficitExposure,
)
from contracts.rotation_definition import RotationDefinition

CONTRACTS = Path(__file__).parent.parent / "contracts"
ROUTE = "/api/rotations/run"
ORIGIN = "http://localhost:5173"
# Dates in the year the examples use.
PERIOD = RunSettings(start_date=dt.date(2001, 1, 1), end_date=dt.date(2001, 1, 5))
RETRIEVED = dt.datetime(2001, 1, 6, tzinfo=dt.UTC)
# A valid rotation: the PLACEHOLDER example of the rotation definition.
ROTATION = json.loads(
    (
        Path(__file__).parent.parent
        / "contracts"
        / "rotation_definition"
        / "examples"
        / "PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)
BODY = {
    "site": {
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "latitude": 1.0,
        "longitude": 2.0,
    },
    "rotation": ROTATION,
}
CARBON_MODELS = ("PLACEHOLDER_carbon_model_one", "PLACEHOLDER_carbon_model_two")
SOIL_SLOPE_FILE = CONTRACTS / "inputs" / "examples" / "PLACEHOLDER_site_soil_slope.json"


def example(folder: str, name: str) -> dict[str, Any]:
    path = CONTRACTS / folder / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


CALENDAR_DOCUMENT = example("inputs", "PLACEHOLDER_rotation_calendar.json")
RESULT_DOCUMENT = example("results", "PLACEHOLDER_results_per_rotation.json")
CLIMATE = SiteClimate.model_validate(example("inputs", "PLACEHOLDER_site_climate.json"))
SOIL_SLOPE = SiteSoilSlope.model_validate(
    example("inputs", "PLACEHOLDER_site_soil_slope.json")
)


def calendar(feasible: bool = True) -> RotationCalendar:
    document = json.loads(json.dumps(CALENDAR_DOCUMENT))
    if not feasible:
        document["feasibility"] = {
            "feasible": False,
            "violations": [
                {
                    "rule": "PLACEHOLDER-rule",
                    "component_ids": [],
                    "detail": "PLACEHOLDER",
                }
            ],
        }
    return RotationCalendar.model_validate(document)


def as_missing(item: dict[str, Any], reason: str) -> dict[str, Any]:
    """The same value written as missing: identifier, direction and unit kept (C3.1)."""
    kept = {
        key: value
        for key, value in item.items()
        if key
        not in ("value", "range", "range_missing", "provenance", "source", "assumption")
    }
    return {
        **kept,
        "value": None,
        "missing": {"reason": reason, "detail": "PLACEHOLDER"},
    }


def soil_loss(missing_reason: str | None = None) -> SoilLossResults:
    document = RESULT_DOCUMENT["soil_loss"]
    if missing_reason is not None:
        document = {
            part: [as_missing(item, missing_reason) for item in document[part]]
            for part in ("annual", "monthly")
        }
    return SoilLossResults.model_validate(document)


def water(missing_reason: str | None = None) -> list[WaterDeficitExposure]:
    items = RESULT_DOCUMENT["water_deficit_exposure"]
    if missing_reason is not None:
        items = [as_missing(item, missing_reason) for item in items]
    return [WaterDeficitExposure.model_validate(item) for item in items]


class Fake:
    """An engine function that records its calls and returns a fixed answer."""

    def __init__(self, answer: Any = None, *, raises: bool = False) -> None:
        self.answer = answer
        self.raises = raises
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.raises:
            raise RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT")
        return self.answer


def fakes(
    *,
    calendar_answer: Any = None,
    soil_loss_answer: Any = None,
    water_answer: Any = None,
) -> tuple[Fake, Fake, Fake]:
    return (
        Fake(calendar_answer if calendar_answer is not None else calendar()),
        Fake(soil_loss_answer if soil_loss_answer is not None else soil_loss()),
        Fake(water_answer if water_answer is not None else water()),
    )


def functions(
    calendar_fn: Fake | None, soil_loss_fn: Fake | None, water_fn: Fake | None
) -> EngineFunctions:
    return EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_loss_fn,
        compute_water_deficit_exposure=water_fn,
    )


def climate_result(data: SiteClimate | None = CLIMATE) -> ClimateResult:
    if data is None:
        return ClimateResult(
            data=None,
            source=SourceInfo(
                id="PLACEHOLDER_CLIMATE",
                contract="site_data_climate",
                state="unavailable",
                missing_reason="SOURCE_UNAVAILABLE",
            ),
        )
    return ClimateResult(
        data=data,
        source=SourceInfo(
            id="PLACEHOLDER_CLIMATE",
            contract="site_data_climate",
            state="fresh",
            retrieved_at=RETRIEVED,
        ),
    )


def soil_result(data: SiteSoilSlope | None = SOIL_SLOPE) -> SoilSlopeResult:
    if data is None:
        return SoilSlopeResult(
            data=None,
            source=SourceInfo(
                id="PLACEHOLDER_SOIL",
                contract="site_data_soil_slope",
                state="unavailable",
                missing_reason="NOT_AVAILABLE",
            ),
        )
    return SoilSlopeResult(
        data=data,
        source=SourceInfo(
            id="PLACEHOLDER_SOIL", contract="site_data_soil_slope", state="example"
        ),
    )


def run(
    engine_functions: EngineFunctions,
    *,
    carbon_models: tuple[str, ...] = CARBON_MODELS,
    climate: ClimateResult | None = None,
    soil: SoilSlopeResult | None = None,
    load_rotation: Any = None,
):
    kwargs: dict[str, Any] = {"carbon_models": carbon_models}
    if load_rotation is not None:
        kwargs["load_rotation"] = load_rotation
    engines: RotationEngines = EntryPointEngines(engine_functions, **kwargs)
    return engines.run(
        ROTATION,
        climate if climate is not None else climate_result(),
        soil if soil is not None else soil_result(),
    )


def states(result) -> dict[str, tuple[str, str | None]]:
    return {m.id: (m.state, m.reason) for m in result.modules}


CARBON_STATES = {
    "residues": ("not_available", "NOT_AVAILABLE"),
    "amg": ("not_available", "NOT_AVAILABLE"),
    "rothc": ("not_available", "NOT_AVAILABLE"),
}


class FakeClimate:
    source_id = "PLACEHOLDER_CLIMATE"
    contract = "site_data_climate"

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return climate_result()


def client(engines: RotationEngines, **kwargs: Any) -> TestClient:
    kwargs.setdefault("climate", FakeClimate())
    kwargs.setdefault("soil_slope", ExampleSoilSlopeSource(SOIL_SLOPE_FILE))
    kwargs.setdefault("settings", PERIOD)
    return TestClient(create_app([ORIGIN], engines=engines, **kwargs))


def numbers_in(value: Any) -> list[Any]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, int | float):
        return [value]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    return []


# --- 1. discovery -------------------------------------------------------------


@pytest.fixture
def no_engine_modules():
    def clear() -> None:
        for name in [
            n for n in sys.modules if n == "engine" or n.startswith("engine.")
        ]:
            del sys.modules[name]

    clear()
    yield
    clear()


def write_package(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")


def test_without_an_engine_package_nothing_is_built(no_engine_modules):
    assert discover_engine_functions() == EngineFunctions()


def test_functions_are_found_by_the_names_of_entrypoints(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/calendar/__init__.py": "def build_rotation_calendar(rotation): ...\n",
            "engine/erosion/__init__.py": (
                "def compute_soil_loss(calendar, climate, soil_slope): ...\n"
            ),
            "engine/water/__init__.py": (
                "def compute_water_deficit_exposure(calendar, climate, soil_slope): ...\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found = discover_engine_functions()
    assert found.build_rotation_calendar is (
        sys.modules["engine.calendar"].build_rotation_calendar
    )
    assert found.compute_soil_loss is sys.modules["engine.erosion"].compute_soil_loss
    assert found.compute_water_deficit_exposure is (
        sys.modules["engine.water"].compute_water_deficit_exposure
    )


def test_an_absent_module_or_function_is_not_built(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/calendar/__init__.py": "def placeholder_other_function(): ...\n",
            "engine/erosion/__init__.py": (
                "def compute_soil_loss(calendar, climate, soil_slope): ...\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found = discover_engine_functions()
    assert found.build_rotation_calendar is None  # module there, function absent
    assert found.compute_soil_loss is not None
    assert found.compute_water_deficit_exposure is None  # module absent


def test_a_module_that_raises_on_import_propagates(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/water/__init__.py": "raise RuntimeError('PLACEHOLDER')\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(RuntimeError, match="PLACEHOLDER"):
        discover_engine_functions()


def test_a_module_that_imports_something_absent_propagates(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/erosion/__init__.py": "import placeholder_absent_dependency\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError, match="placeholder_absent_dependency"):
        discover_engine_functions()


def test_a_name_that_is_not_a_function_is_a_defect(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/calendar/__init__.py": "build_rotation_calendar = 'PLACEHOLDER'\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(TypeError, match="not a function"):
        discover_engine_functions()


# --- 2. call order and arguments ----------------------------------------------


def test_call_order_and_arguments():
    order: list[str] = []
    loaded = {"PLACEHOLDER_LOADED": "PLACEHOLDER"}
    calendar_fn, soil_fn, water_fn = fakes()
    calendar_answer = calendar_fn.answer

    def recording(name: str, fake: Fake) -> Fake:
        def call(*args, **kwargs):
            order.append(name)
            return fake(*args, **kwargs)

        return call  # type: ignore[return-value]

    climate, soil = climate_result(), soil_result()
    run(
        functions(
            recording("EP2", calendar_fn),
            recording("EP1", soil_fn),
            recording("EP3", water_fn),
        ),
        climate=climate,
        soil=soil,
        load_rotation=lambda rotation: loaded if rotation == ROTATION else None,
    )
    assert order == ["EP2", "EP1", "EP3"]
    assert calendar_fn.calls == [((loaded,), {})]
    for fake in (soil_fn, water_fn):
        ((args, kwargs),) = fake.calls
        assert args == ()  # by keyword only (G3)
        assert set(kwargs) == {"calendar", "climate", "soil_slope"}
        assert kwargs["calendar"] is calendar_answer
        assert kwargs["climate"] is climate.data
        assert kwargs["soil_slope"] is soil.data


def test_default_load_rotation_gives_ep2_a_rotation_definition():
    calendar_fn, soil_fn, water_fn = fakes()
    run(functions(calendar_fn, soil_fn, water_fn))
    ((args, kwargs),) = calendar_fn.calls
    assert kwargs == {}
    assert isinstance(args[0], RotationDefinition)
    assert args[0] == RotationDefinition.model_validate(ROTATION)


# --- 3. infeasible calendar ---------------------------------------------------


def test_infeasible_calendar_still_calls_the_engines_and_is_no_result():
    infeasible = calendar(feasible=False)
    missing_soil, missing_water = soil_loss("NOT_COMPUTABLE"), water("NOT_COMPUTABLE")
    calendar_fn, soil_fn, water_fn = fakes(
        calendar_answer=infeasible,
        soil_loss_answer=missing_soil,
        water_answer=missing_water,
    )
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assert len(soil_fn.calls) == len(water_fn.calls) == 1
    assert result.result is not None
    assert result.result.soil_loss is missing_soil  # passed through unchanged
    assert result.result.water_deficit_exposure == missing_water
    assert result.values_present == 0
    assert states(result)["calendar"] == ("degraded", "NOT_COMPUTABLE")
    assert states(result)["erosion"] == ("not_available", "NOT_COMPUTABLE")
    assert states(result)["water"] == ("not_available", "NOT_COMPUTABLE")

    body = (
        client(
            EntryPointEngines(
                functions(
                    *fakes(
                        calendar_answer=infeasible,
                        soil_loss_answer=missing_soil,
                        water_answer=missing_water,
                    )
                ),
                carbon_models=CARBON_MODELS,
            )
        )
        .post(ROUTE, json=BODY)
        .json()
    )
    assert body["outcome"] == "no_result"
    assert body["calendar"]["feasibility"]["feasible"] is False


# --- 4. the table of what the runner writes when something is absent ----------


def test_calendar_engine_not_built():
    _, soil_fn, water_fn = fakes()
    result = run(functions(None, soil_fn, water_fn))
    assert result.calendar is None
    assert result.result is None
    assert result.result_missing.reason == "NOT_AVAILABLE"
    assert "engine.calendar.build_rotation_calendar" in result.result_missing.detail
    assert soil_fn.calls == water_fn.calls == []
    assert states(result) == {
        "calendar": ("not_available", "NOT_AVAILABLE"),
        "erosion": ("not_available", "MISSING_INPUT"),
        "water": ("not_available", "MISSING_INPUT"),
        **CARBON_STATES,
    }
    erosion = next(m for m in result.modules if m.id == "erosion")
    assert "calendar" in erosion.detail


def test_nothing_built_every_module_says_not_built():
    result = run(EngineFunctions())
    assert result.result is None
    assert result.result_missing.reason == "NOT_AVAILABLE"
    assert {module_id: state for module_id, state in states(result).items()} == {
        module_id: ("not_available", "NOT_AVAILABLE") for module_id in MODULE_IDS
    }


@pytest.mark.parametrize(
    ("climate_data", "soil_data", "named"),
    [
        (None, SOIL_SLOPE, ["climate"]),
        (CLIMATE, None, ["soil_slope"]),
        (None, None, ["climate", "soil_slope"]),
    ],
)
def test_site_data_absent(climate_data, soil_data, named):
    calendar_fn, soil_fn, water_fn = fakes()
    result = run(
        functions(calendar_fn, soil_fn, water_fn),
        climate=climate_result(climate_data),
        soil=soil_result(soil_data),
    )
    assert soil_fn.calls == water_fn.calls == []  # no instance to pass (G3)
    assert result.result is None
    assert result.calendar is calendar_fn.answer  # still returned
    assert result.result_missing.reason == "MISSING_INPUT"
    for name in named:
        assert name in result.result_missing.detail
    assert states(result) == {
        "calendar": ("available", None),
        "erosion": ("not_available", "MISSING_INPUT"),
        "water": ("not_available", "MISSING_INPUT"),
        **CARBON_STATES,
    }


@pytest.mark.parametrize("absent", ["erosion", "water"])
def test_one_of_ep1_and_ep3_not_built(absent):
    calendar_fn, soil_fn, water_fn = fakes()
    if absent == "erosion":
        soil_fn = None
    else:
        water_fn = None
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assert result.result is None
    assert result.calendar is calendar_fn.answer
    assert result.result_missing.reason == "NOT_AVAILABLE"
    path = {"erosion": "engine.erosion", "water": "engine.water"}[absent]
    assert path in result.result_missing.detail
    assert states(result)[absent] == ("not_available", "NOT_AVAILABLE")
    # The engine that is built still runs and reports its own state.
    if absent == "erosion":
        other, values = "water", water_fn.answer
        assert len(water_fn.calls) == 1
    else:
        other, values = "erosion", [*soil_fn.answer.annual, *soil_fn.answer.monthly]
        assert len(soil_fn.calls) == 1
    expected = module_status_of(other, count_values(values))
    assert states(result)[other] == (expected.state, expected.reason)
    assert states(result)["calendar"] == ("available", None)


def test_ep1_returns_a_bare_missing():
    bare = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER start month")
    calendar_fn, soil_fn, water_fn = fakes(soil_loss_answer=bare)
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assert result.result is None
    assert result.calendar is calendar_fn.answer
    assert result.result_missing.reason == "MISSING_INPUT"
    assert result.result_missing.detail == "PLACEHOLDER start month"
    erosion = next(m for m in result.modules if m.id == "erosion")
    assert (erosion.state, erosion.reason, erosion.detail) == (
        "not_available",
        "MISSING_INPUT",
        "PLACEHOLDER start month",
    )


def test_no_carbon_model_identifiers_means_no_result():
    # An explicit configuration: the app's default is DEFAULT_CARBON_MODELS.
    result = run(functions(*fakes()), carbon_models=())
    assert result.result is None
    assert result.calendar is not None
    assert result.result_missing.reason == "NOT_AVAILABLE"
    assert "carbon models" in result.result_missing.detail
    assert {k: v for k, v in states(result).items() if k in CARBON_STATES} == (
        CARBON_STATES
    )


# --- 5. everything built ------------------------------------------------------


def test_everything_built_assembles_results_per_rotation():
    calendar_fn, soil_fn, water_fn = fakes()
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assembled = result.result
    assert isinstance(assembled, ResultsPerRotation)
    assert result.result_missing is None
    built_calendar = calendar_fn.answer
    assert (assembled.case_id, assembled.field_id, assembled.rotation_id) == (
        built_calendar.case_id,
        built_calendar.field_id,
        built_calendar.rotation_id,
    )
    assert assembled.soil_loss is soil_fn.answer
    assert assembled.water_deficit_exposure == water_fn.answer
    assert all(
        a is b for a, b in zip(assembled.water_deficit_exposure, water_fn.answer)
    )
    rows = assembled.soil_carbon_trend
    assert len(rows) == 3 * len(CARBON_MODELS)
    for carbon_model in CARBON_MODELS:
        mine = [row for row in rows if row.carbon_model == carbon_model]
        assert sorted(row.computation for row in mine) == sorted(TREND_COMPUTATIONS)
    assert all(row.value is None for row in rows)
    assert all(row.missing.reason == "NOT_AVAILABLE" for row in rows)
    # Serialises without dropping anything and loads back.
    text = json.dumps(assembled.model_dump(mode="json"))
    assert ResultsPerRotation.model_validate_json(text) == assembled
    count = count_values(result_values(assembled))
    assert (result.values_present, result.values_missing) == (
        count.present,
        count.missing,
    )


def test_the_runner_writes_no_number():
    result = run(functions(*fakes()))
    carbon = [row.model_dump(mode="json") for row in result.result.soil_carbon_trend]
    assert numbers_in(carbon) == []


def test_carbon_model_identifiers_have_no_default():
    engines = EntryPointEngines(EngineFunctions())
    assert engines._carbon_models == ()


@pytest.mark.parametrize("bad", ["PLACEHOLDER", ("",), ("PLACEHOLDER", "PLACEHOLDER")])
def test_carbon_model_identifiers_are_checked(bad):
    with pytest.raises((TypeError, ValueError)):
        EntryPointEngines(EngineFunctions(), carbon_models=bad)


# --- 6. module states and the counting function -------------------------------


def test_count_values():
    assert count_values([]) == ValueCount(present=0, missing=0, first_missing=None)
    loss = soil_loss()
    count = count_values([*loss.annual, *loss.monthly])
    annual = RESULT_DOCUMENT["soil_loss"]["annual"]
    monthly = RESULT_DOCUMENT["soil_loss"]["monthly"]
    expected_missing = [i for i in [*annual, *monthly] if i["value"] is None]
    assert count.missing == len(expected_missing)
    assert count.present == len(annual) + len(monthly) - len(expected_missing)
    assert count.first_missing == Missing.model_validate(expected_missing[0]["missing"])


def test_count_values_counts_indicator_values_only():
    with pytest.raises(TypeError):
        count_values([object()])  # type: ignore[list-item]


def test_module_status_of_each_case():
    reason = Missing(reason="NO_COVERAGE")
    assert module_status_of("PLACEHOLDER", ValueCount(2, 0, None)).state == "available"
    degraded = module_status_of("PLACEHOLDER", ValueCount(2, 1, reason))
    assert (degraded.state, degraded.reason) == ("degraded", "NO_COVERAGE")
    assert "1 of 3" in degraded.detail
    gone = module_status_of("PLACEHOLDER", ValueCount(0, 3, reason))
    assert (gone.state, gone.reason) == ("not_available", "NO_COVERAGE")


def test_module_states_from_the_engine_outputs():
    result = run(functions(*fakes(water_answer=water("NOT_AVAILABLE"))))
    # The example soil loss has present and missing values; its water is missing.
    first_missing = count_values(
        [*soil_loss().annual, *soil_loss().monthly]
    ).first_missing
    assert states(result)["erosion"] == ("degraded", first_missing.reason)
    assert states(result)["water"] == ("not_available", "NOT_AVAILABLE")
    assert states(result)["calendar"] == ("available", None)
    assert [m.id for m in result.modules] == list(MODULE_IDS)


def test_calendar_status():
    assert calendar_status(calendar()).state == "available"
    infeasible = calendar_status(calendar(feasible=False))
    assert (infeasible.state, infeasible.reason) == ("degraded", "NOT_COMPUTABLE")


# --- 7. outcome through the route ---------------------------------------------


def test_outcome_partial_and_complete_not_reachable_with_carbon_missing():
    engines = EntryPointEngines(functions(*fakes()), carbon_models=CARBON_MODELS)
    body = client(engines).post(ROUTE, json=BODY).json()
    assert body["outcome"] == "partial"


def test_outcome_no_result_without_a_result():
    engines = EntryPointEngines(functions(*fakes()), carbon_models=())
    body = client(engines).post(ROUTE, json=BODY).json()
    assert body["outcome"] == "no_result"
    assert body["result"] is None
    assert body["calendar"] is not None  # the calendar that was built


# --- 8. engine exceptions and wrong return types ------------------------------


@pytest.mark.parametrize("which", [0, 1, 2])
def test_an_engine_that_raises_is_500_with_cors_and_no_text(which):
    parts = list(fakes())
    parts[which] = Fake(raises=True)
    engines = EntryPointEngines(functions(*parts), carbon_models=CARBON_MODELS)
    response = client(engines).post(ROUTE, json=BODY, headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text


@pytest.mark.parametrize(
    "which, wrong",
    [
        (0, CALENDAR_DOCUMENT),  # a dictionary, not the model
        (1, RESULT_DOCUMENT["soil_loss"]),
        (2, water()[0]),  # one item, not a list
        (2, [RESULT_DOCUMENT["water_deficit_exposure"][0]]),
    ],
)
def test_an_engine_that_returns_the_wrong_type_is_500(which, wrong):
    parts = list(fakes())
    parts[which] = Fake(wrong)
    engines = EntryPointEngines(functions(*parts), carbon_models=CARBON_MODELS)
    with pytest.raises(TypeError):
        engines.run(ROTATION, climate_result(), soil_result())
    response = client(engines).post(ROUTE, json=BODY, headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers.get("access-control-allow-origin") == ORIGIN


# --- 9. the route end to end with fakes ---------------------------------------


def test_route_end_to_end():
    calendar_fn, soil_fn, water_fn = fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn), carbon_models=CARBON_MODELS
    )
    response = client(engines).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    loaded = ResultsPerRotation.model_validate_json(json.dumps(body["result"]))
    assert loaded.soil_loss == soil_fn.answer
    assert RotationCalendar.model_validate_json(json.dumps(body["calendar"])) == (
        calendar_fn.answer
    )
    assert [(s["contract"], s["state"]) for s in body["sources"]] == [
        ("site_data_climate", "fresh"),
        ("site_data_soil_slope", "example"),
    ]
    assert body["result_missing"] is None
    assert [m["id"] for m in body["modules"]] == list(MODULE_IDS)
    # EP1 and EP3 received the example soil and slope as an instance.
    assert isinstance(soil_fn.calls[0][1]["soil_slope"], SiteSoilSlope)


# --- 10. the default app ------------------------------------------------------


def test_default_engines_are_the_runner_and_say_nothing_is_built(no_engine_modules):
    app_client = TestClient(create_app([ORIGIN]))
    response = app_client.post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_result"
    assert body["calendar"] is None
    assert body["result"] is None
    assert body["result_missing"]["reason"] == "NOT_AVAILABLE"
    assert [(m["id"], m["state"], m["reason"]) for m in body["modules"]] == [
        (module_id, "not_available", "NOT_AVAILABLE") for module_id in MODULE_IDS
    ]
    assert numbers_in(body) == []


def test_module_identifiers_follow_entrypoints():
    assert MODULE_IDS == ("calendar", "erosion", "water", "residues", "amg", "rothc")
    assert [(p.entry, p.module, p.function) for p in runner.DISCOVERED] == [
        ("EP2", "engine.calendar", "build_rotation_calendar"),
        ("EP1", "engine.erosion", "compute_soil_loss"),
        ("EP3", "engine.water", "compute_water_deficit_exposure"),
    ]


# --- the default carbon model identifiers (issue #18, decision D1 of #77) -----

FAKE_ENGINE_PACKAGE = {
    "engine/__init__.py": "",
    "engine/_examples.py": f"""
        import json
        from pathlib import Path

        from contracts.inputs import RotationCalendar
        from contracts.results.models import SoilLossResults, WaterDeficitExposure

        CONTRACTS = Path({str(CONTRACTS)!r})


        def load(folder, name):
            path = CONTRACTS / folder / "examples" / name
            return json.loads(path.read_text(encoding="utf-8"))


        def calendar():
            document = load("inputs", "PLACEHOLDER_rotation_calendar.json")
            return RotationCalendar.model_validate(document)


        def soil_loss():
            document = load("results", "PLACEHOLDER_results_per_rotation.json")
            return SoilLossResults.model_validate(document["soil_loss"])


        def water():
            document = load("results", "PLACEHOLDER_results_per_rotation.json")
            return [
                WaterDeficitExposure.model_validate(item)
                for item in document["water_deficit_exposure"]
            ]
    """,
    "engine/calendar/__init__.py": """
        from engine._examples import calendar


        def build_rotation_calendar(rotation):
            return calendar()
    """,
    "engine/erosion/__init__.py": """
        from engine._examples import soil_loss


        def compute_soil_loss(calendar, climate, soil_slope):
            return soil_loss()
    """,
    "engine/water/__init__.py": """
        from engine._examples import water


        def compute_water_deficit_exposure(calendar, climate, soil_slope):
            return water()
    """,
}


def test_default_carbon_models_are_the_decided_identifiers():
    assert DEFAULT_CARBON_MODELS == ("amg", "rothc")


def test_default_app_assembles_a_result_once_the_three_engines_exist(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(tmp_path, FAKE_ENGINE_PACKAGE)
    monkeypatch.syspath_prepend(str(tmp_path))
    app_client = TestClient(
        create_app(
            [ORIGIN],
            climate=FakeClimate(),
            soil_slope=ExampleSoilSlopeSource(SOIL_SLOPE_FILE),
            settings=PERIOD,
        )
    )
    response = app_client.post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["result_missing"] is None
    result = ResultsPerRotation.model_validate_json(json.dumps(body["result"]))
    assert result.soil_loss == soil_loss()
    assert result.water_deficit_exposure == water()
    rows = result.soil_carbon_trend
    assert sorted((row.carbon_model, row.computation) for row in rows) == sorted(
        (model, computation)
        for model in ("amg", "rothc")
        for computation in TREND_COMPUTATIONS
    )
    assert all(row.value is None for row in rows)
    assert all(row.missing.reason == "NOT_AVAILABLE" for row in rows)
    assert all(row.missing.detail for row in rows)
    assert body["outcome"] == "partial"  # carbon is missing: never complete yet
    assert [(s["contract"], s["state"]) for s in body["sources"]] == [
        ("site_data_climate", "fresh"),
        ("site_data_soil_slope", "example"),
    ]
