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
from typing import Any, get_args

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
    part_not_built,
    result_values,
    soil_loss_values,
)
from api.main import create_app
from api.ports import RotationEngines, RunSettings
from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    TREND_COMPUTATIONS,
    UNITS_OF,
    CarbonModel,
    Missing,
    PartNotBuilt,
    ResultsPerRotation,
    SoilCarbonTrend,
    SoilLossNotBuilt,
    SoilLossResults,
    WaterDeficitExposure,
    WaterDeficitExposureNotBuilt,
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
# The two carbon models of the contract (decision D1 of issue 77): the results
# models accept no other identifier.
CARBON_MODELS = ("amg", "rothc")
SOIL_SLOPE_FILE = CONTRACTS / "inputs" / "examples" / "PLACEHOLDER_site_soil_slope.json"
# The cycle of the PLACEHOLDER calendar lasts two years, so the runner makes
# two runs of EP1, EP3 and EP5, one per phase (D109; api/phases.py).
PHASES = 2


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


def write_package(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")


def test_without_an_engine_package_nothing_is_built(engines_hidden):
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
                "def compute_soil_loss(calendar, climate, soil_slope, *, parameters): ...\n"
            ),
            "engine/water/__init__.py": (
                "def compute_water_deficit_exposure(\n"
                "    calendar, climate, soil_slope, *, parameters\n"
                "): ...\n"
            ),
            "engine/amg/__init__.py": "def run_amg(forcing, *, parameters): ...\n",
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
    assert found.run_amg is sys.modules["engine.amg"].run_amg


def test_an_absent_module_or_function_is_not_built(
    tmp_path, monkeypatch, no_engine_modules
):
    write_package(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/calendar/__init__.py": "def placeholder_other_function(): ...\n",
            "engine/erosion/__init__.py": (
                "def compute_soil_loss(calendar, climate, soil_slope, *, parameters): ...\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found = discover_engine_functions()
    assert found.build_rotation_calendar is None  # module there, function absent
    assert found.compute_soil_loss is not None
    assert found.compute_water_deficit_exposure is None  # module absent
    assert found.run_amg is None  # module absent


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
    assert order == ["EP2", *["EP1", "EP3"] * PHASES]
    assert calendar_fn.calls == [((loaded,), {})]
    for fake in (soil_fn, water_fn):
        assert len(fake.calls) == PHASES
        for args, kwargs in fake.calls:
            assert args == ()  # by keyword only (G3)
            assert set(kwargs) == {"calendar", "climate", "soil_slope", "parameters"}
            assert kwargs["climate"] is climate.data
            assert kwargs["soil_slope"] is soil.data
        # Phase 1 is the calendar of EP2 itself (api/phases.py).
        assert fake.calls[0][1]["calendar"] is calendar_answer


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
    """D12: the part of the engine that is not built takes the not-built form."""
    calendar_fn, soil_fn, water_fn = fakes()
    if absent == "erosion":
        soil_fn = None
    else:
        water_fn = None
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assembled = result.result
    assert isinstance(assembled, ResultsPerRotation)
    assert result.result_missing is None
    assert result.calendar is calendar_fn.answer
    assert states(result)[absent] == ("not_available", "NOT_AVAILABLE")
    # The engine that is built still runs; its part is its output, unchanged.
    if absent == "erosion":
        assert isinstance(assembled.soil_loss, SoilLossNotBuilt)
        assert "engine.erosion.compute_soil_loss" in assembled.soil_loss.missing.detail
        assert len(water_fn.calls) == PHASES
        assert all(
            a is b for a, b in zip(assembled.water_deficit_exposure, water_fn.answer)
        )
        assert len(assembled.water_deficit_exposure) == len(water_fn.answer)
        other, values = "water", water_fn.answer
    else:
        assert isinstance(
            assembled.water_deficit_exposure, WaterDeficitExposureNotBuilt
        )
        assert (
            "engine.water.compute_water_deficit_exposure"
            in assembled.water_deficit_exposure.missing.detail
        )
        assert len(soil_fn.calls) == PHASES
        assert assembled.soil_loss is soil_fn.answer
        other, values = "erosion", [*soil_fn.answer.annual, *soil_fn.answer.monthly]
    expected = module_status_of(other, count_values(values))
    assert states(result)[other] == (expected.state, expected.reason)
    assert states(result)["calendar"] == ("available", None)
    count = count_values(result_values(assembled))
    assert (result.values_present, result.values_missing) == (
        count.present,
        count.missing,
    )


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


def test_default_engines_are_the_runner_and_say_nothing_is_built(engines_hidden):
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
        ("EP5", "engine.amg", "run_amg"),
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


        def compute_soil_loss(calendar, climate, soil_slope, *, parameters):
            return soil_loss()
    """,
    "engine/water/__init__.py": """
        from engine._examples import water


        def compute_water_deficit_exposure(calendar, climate, soil_slope, *, parameters):
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


# --- 11. site data of another field (PROPOSED) --------------------------------

OTHER_CASE = "PLACEHOLDER_OTHER_CASE_SUBMITTED"
OTHER_FIELD = "PLACEHOLDER_OTHER_FIELD_SUBMITTED"


class SameFieldOrRaise(Fake):
    """An EP1 or EP3 that raises, as G5 says, when its arguments name other fields."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        identities = {
            (kwargs[name].case_id, kwargs[name].field_id)
            for name in ("calendar", "climate", "soil_slope")
        }
        if len(identities) != 1:
            raise ValueError("PLACEHOLDER: the arguments name different fields")
        return super().__call__(*args, **kwargs)


def checking_fakes() -> tuple[Fake, SameFieldOrRaise, SameFieldOrRaise]:
    return Fake(calendar()), SameFieldOrRaise(soil_loss()), SameFieldOrRaise(water())


def soil_of_another_field(**update: str) -> SiteSoilSlope:
    return SOIL_SLOPE.model_copy(update=update)


def climate_of_another_field(**update: str) -> SiteClimate:
    return CLIMATE.model_copy(update=update)


@pytest.mark.parametrize(
    "climate_data, soil_data, named, fields",
    [
        (
            CLIMATE,
            soil_of_another_field(field_id=OTHER_FIELD),
            ["soil_slope"],
            "field_id",
        ),
        (
            climate_of_another_field(case_id=OTHER_CASE),
            SOIL_SLOPE,
            ["climate"],
            "case_id",
        ),
        (
            climate_of_another_field(case_id=OTHER_CASE, field_id=OTHER_FIELD),
            soil_of_another_field(field_id=OTHER_FIELD),
            ["climate", "soil_slope"],
            "case_id and field_id",
        ),
    ],
)
def test_site_data_of_another_field_is_missing_input(
    climate_data, soil_data, named, fields
):
    calendar_fn, soil_fn, water_fn = checking_fakes()
    result = run(
        functions(calendar_fn, soil_fn, water_fn),
        climate=climate_result(climate_data),
        soil=soil_result(soil_data),
    )
    assert soil_fn.calls == [] and water_fn.calls == []
    assert result.result is None
    assert result.calendar == calendar_fn.answer
    assert result.result_missing.reason == "MISSING_INPUT"
    detail = result.result_missing.detail
    assert detail.startswith(runner.OTHER_FIELD)
    for name in named:
        assert name in detail
    assert fields in detail
    assert states(result) == {
        "calendar": ("available", None),
        "erosion": ("not_available", "MISSING_INPUT"),
        "water": ("not_available", "MISSING_INPUT"),
        **CARBON_STATES,
    }
    calendar_ids = (calendar_fn.answer.case_id, calendar_fn.answer.field_id)
    for text in [detail, *(m.detail or "" for m in result.modules)]:
        for identifier in (OTHER_CASE, OTHER_FIELD, *calendar_ids):
            assert identifier not in text


def test_another_field_with_an_engine_not_built_keeps_the_precedence_rule():
    calendar_fn, soil_fn, _ = checking_fakes()
    result = run(
        functions(calendar_fn, soil_fn, None),
        soil=soil_result(soil_of_another_field(field_id=OTHER_FIELD)),
    )
    assert soil_fn.calls == []
    assert result.result_missing.reason == "MISSING_INPUT"
    assert states(result)["erosion"] == ("not_available", "MISSING_INPUT")
    assert states(result)["water"] == ("not_available", "NOT_AVAILABLE")


def test_site_data_of_the_same_field_calls_the_engines():
    calendar_fn, soil_fn, water_fn = checking_fakes()
    result = run(functions(calendar_fn, soil_fn, water_fn))
    assert len(soil_fn.calls) == len(water_fn.calls) == PHASES
    assert result.result is not None
    assert result.result_missing is None


def test_site_data_of_another_field_is_answered_200_not_500():
    calendar_fn, soil_fn, water_fn = checking_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn), carbon_models=CARBON_MODELS
    )

    class OtherFieldSoil:
        source_id = "PLACEHOLDER_SOIL"
        contract = "site_data_soil_slope"

        def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
            return soil_result(soil_of_another_field(field_id=OTHER_FIELD))

    submitted = {
        **BODY,
        "site": {**BODY["site"], "field_id": "PLACEHOLDER_SUBMITTED_FIELD_ID"},
    }
    response = client(engines, soil_slope=OtherFieldSoil()).post(ROUTE, json=submitted)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_result"
    assert body["result"] is None
    assert body["result_missing"]["reason"] == "MISSING_INPUT"
    detail = body["result_missing"]["detail"]
    for identifier in (
        "PLACEHOLDER_SUBMITTED_FIELD_ID",
        BODY["site"]["case_id"],
        OTHER_FIELD,
    ):
        assert identifier not in detail
    assert soil_fn.calls == [] and water_fn.calls == []


def test_other_field_inputs_names_only_the_fields_that_differ():
    cal = calendar()
    assert runner.other_field_inputs(cal, climate=CLIMATE, soil_slope=SOIL_SLOPE) == []
    assert runner.other_field_inputs(
        cal, soil_slope=soil_of_another_field(case_id=OTHER_CASE)
    ) == [("soil_slope", ("case_id",))]


# --- 12. partial results: a part whose engine is not built (D12) ---------------

NOT_BUILT_DOCUMENT = example(
    "results", "PLACEHOLDER_results_per_rotation_not_built.json"
)
EP1_PATH = "engine.erosion.compute_soil_loss"
EP3_PATH = "engine.water.compute_water_deficit_exposure"


def calendar_only(**kwargs: Any):
    calendar_fn = Fake(calendar())
    return calendar_fn, run(functions(calendar_fn, None, None), **kwargs)


def without_detail(part: dict[str, Any]) -> dict[str, Any]:
    return {**part, "missing": {"reason": part["missing"]["reason"]}}


def test_only_the_calendar_built_gives_two_not_built_parts_and_six_carbon_rows():
    calendar_fn, result = calendar_only(carbon_models=DEFAULT_CARBON_MODELS)
    assembled = result.result
    assert isinstance(assembled, ResultsPerRotation)
    assert result.result_missing is None
    assert result.calendar is calendar_fn.answer
    assert isinstance(assembled.soil_loss, SoilLossNotBuilt)
    assert isinstance(assembled.water_deficit_exposure, WaterDeficitExposureNotBuilt)
    assert EP1_PATH in assembled.soil_loss.missing.detail
    assert EP3_PATH in assembled.water_deficit_exposure.missing.detail
    rows = assembled.soil_carbon_trend
    assert isinstance(rows, list)  # the six rows, not the not-built form
    assert sorted((row.carbon_model, row.computation) for row in rows) == sorted(
        (model, computation)
        for model in ("amg", "rothc")
        for computation in TREND_COMPUTATIONS
    )
    assert all(row.value is None for row in rows)
    assert all(row.missing.reason == "NOT_AVAILABLE" for row in rows)
    assert states(result) == {
        "calendar": ("available", None),
        "erosion": ("not_available", "NOT_AVAILABLE"),
        "water": ("not_available", "NOT_AVAILABLE"),
        **CARBON_STATES,
    }
    # Each not-built part counts as one missing value (PROPOSED).
    assert (result.values_present, result.values_missing) == (0, 2 + len(rows))


def test_the_not_built_parts_carry_the_constants_of_the_contract():
    _, result = calendar_only()
    soil = result.result.soil_loss
    water_part = result.result.water_deficit_exposure
    for part, indicator in (
        (soil, "soil_loss"),
        (water_part, "water_deficit_exposure"),
    ):
        assert part.indicator == indicator
        assert part.direction == DIRECTION_OF[indicator]
        assert tuple(part.units) == UNITS_OF[indicator]
        assert part.missing.reason == "NOT_AVAILABLE"
    # The same as the accepted example, except the detail text.
    for name, part in (("soil_loss", soil), ("water_deficit_exposure", water_part)):
        assert without_detail(part.model_dump(mode="json")) == without_detail(
            NOT_BUILT_DOCUMENT[name]
        )
    assert part_not_built(SoilLossNotBuilt, runner.EROSION) == soil


@pytest.mark.parametrize(
    "built, outcome",
    [
        ("none", "no_result"),
        ("erosion", "partial"),
        # The PLACEHOLDER water output holds no present value, and no example
        # holds one, so no value is present and the rule of the route gives
        # ``no_result``. No number is written here to make it ``partial``.
        ("water", "no_result"),
    ],
)
def test_the_route_answers_a_result_that_loads_back(built, outcome):
    calendar_fn, soil_fn, water_fn = fakes()
    engines = EntryPointEngines(
        functions(
            calendar_fn,
            soil_fn if built == "erosion" else None,
            water_fn if built == "water" else None,
        ),
        carbon_models=DEFAULT_CARBON_MODELS,
    )
    response = client(engines).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == outcome
    assert body["result_missing"] is None
    loaded = ResultsPerRotation.model_validate_json(json.dumps(body["result"]))
    parts = {
        "soil_loss": loaded.soil_loss,
        "water_deficit_exposure": loaded.water_deficit_exposure,
    }
    not_built = [name for name, part in parts.items() if isinstance(part, PartNotBuilt)]
    assert not_built == [
        name
        for name, engine in (
            ("soil_loss", "erosion"),
            ("water_deficit_exposure", "water"),
        )
        if engine != built
    ]
    for name in not_built:
        assert numbers_in(body["result"][name]) == []
    if built == "erosion":
        assert loaded.soil_loss == soil_fn.answer
    if built == "water":
        assert loaded.water_deficit_exposure == water_fn.answer


def test_count_values_on_a_result_with_not_built_parts():
    _, nothing = calendar_only()
    values = result_values(nothing.result)
    count = count_values(values)
    assert count.present == 0
    assert count.missing == 2 + 3 * len(CARBON_MODELS)
    assert count.first_missing == nothing.result.soil_loss.missing
    assert soil_loss_values(nothing.result.soil_loss) == [nothing.result.soil_loss]

    _, with_soil, _ = fakes()
    partial = run(functions(Fake(calendar()), with_soil, None)).result
    count = count_values(result_values(partial))
    loss = count_values(soil_loss_values(with_soil.answer))
    assert count.present == loss.present > 0
    assert count.missing == loss.missing + 1 + 3 * len(CARBON_MODELS)


# What keeps its present answer (D12 allows the not-built form only for an
# engine that is not built): one test per row.


def test_still_no_result_when_the_calendar_engine_is_not_built():
    result = run(EngineFunctions(), carbon_models=DEFAULT_CARBON_MODELS)
    assert result.calendar is None
    assert result.result is None
    assert result.result_missing.reason == "NOT_AVAILABLE"
    assert "engine.calendar.build_rotation_calendar" in result.result_missing.detail


@pytest.mark.parametrize(
    "climate_data, soil_data", [(None, SOIL_SLOPE), (CLIMATE, None), (None, None)]
)
def test_still_no_result_when_an_input_is_absent(climate_data, soil_data):
    """PROPOSED: inputs absent and engines not built is still MISSING_INPUT."""
    _, result = calendar_only(
        climate=climate_result(climate_data), soil=soil_result(soil_data)
    )
    assert result.result is None
    assert result.calendar is not None
    assert result.result_missing.reason == "MISSING_INPUT"
    assert states(result)["erosion"] == ("not_available", "NOT_AVAILABLE")
    assert states(result)["water"] == ("not_available", "NOT_AVAILABLE")


def test_still_no_result_for_site_data_of_another_field():
    _, result = calendar_only(
        soil=soil_result(soil_of_another_field(field_id=OTHER_FIELD))
    )
    assert result.result is None
    assert result.result_missing.reason == "MISSING_INPUT"
    assert result.result_missing.detail.startswith(runner.OTHER_FIELD)


def test_still_no_result_when_ep1_returns_a_bare_missing():
    bare = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER start month")
    result = run(functions(Fake(calendar()), Fake(bare), None))
    assert result.result is None
    assert (result.result_missing.reason, result.result_missing.detail) == (
        "MISSING_INPUT",
        "PLACEHOLDER start month",
    )


def test_still_no_result_without_carbon_model_identifiers():
    _, result = calendar_only(carbon_models=())
    assert result.result is None
    assert result.result_missing.reason == "NOT_AVAILABLE"
    assert "carbon models" in result.result_missing.detail


@pytest.mark.parametrize("which", [1, 2])
def test_a_built_engine_that_returns_the_not_built_form_is_a_defect(which):
    parts = list(fakes())
    parts[which] = Fake(
        part_not_built(SoilLossNotBuilt, runner.EROSION)
        if which == 1
        else part_not_built(WaterDeficitExposureNotBuilt, runner.WATER)
    )
    engines = EntryPointEngines(functions(*parts), carbon_models=CARBON_MODELS)
    with pytest.raises(TypeError):
        engines.run(ROTATION, climate_result(), soil_result())
    response = client(engines).post(ROUTE, json=BODY, headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


# --- 13. the example soil and slope stands in for any field (D38) --------------


def test_the_example_with_its_own_identifiers_no_longer_answers_another_field(
    tmp_path, monkeypatch, no_engine_modules
):
    """Default engines (a fake package), the example file under other identifiers."""
    write_package(tmp_path / "package", FAKE_ENGINE_PACKAGE)
    monkeypatch.syspath_prepend(str(tmp_path / "package"))
    document = example("inputs", "PLACEHOLDER_site_soil_slope.json")
    document["case_id"] = "PLACEHOLDER_FILE_CASE"
    document["field_id"] = "PLACEHOLDER_FILE_FIELD"
    soil_file = tmp_path / "soil.json"
    soil_file.write_text(json.dumps(document), encoding="utf-8")
    app_client = TestClient(
        create_app(
            [ORIGIN],
            climate=FakeClimate(),
            soil_slope=ExampleSoilSlopeSource(soil_file),
            settings=PERIOD,
        )
    )
    body = app_client.post(ROUTE, json=BODY).json()
    assert body["result_missing"] is None
    assert body["result"] is not None
    assert body["sources"][1]["state"] == "example"
    assert "PLACEHOLDER_FILE" not in json.dumps(body)


# --- 14. the parameter catalogue as `parameters` (Q3, D46, D56 of #77) ---------
#
# EP1 and EP3 always get ``parameters=`` by keyword (contracts/ENTRYPOINTS.md);
# EP2 never does. The catalogue here is given directly at the level of the
# runner: the PLACEHOLDER example record of params/examples/, which
# ``check_catalogue`` would refuse as a placeholder; the runner passes what it
# is given and checks nothing (api/config.py checks at start-up).

PARAMS_EXAMPLE = Path(__file__).parent.parent / "params" / "examples"


def catalogue() -> dict[str, dict]:
    name = "PLACEHOLDER_with_value.json"
    record = json.loads((PARAMS_EXAMPLE / name).read_text(encoding="utf-8"))
    return {name: record}


class TakesParameters(Fake):
    """A fake EP1 or EP3 on the signature of the contract: ``parameters`` required."""

    def __call__(self, *, calendar, climate, soil_slope, parameters):  # type: ignore[override]
        return super().__call__(
            calendar=calendar,
            climate=climate,
            soil_slope=soil_slope,
            parameters=parameters,
        )


class WithoutParameters(Fake):
    """A fake EP1 or EP3 that does not follow the contract: no ``parameters``."""

    def __call__(self, *, calendar, climate, soil_slope):  # type: ignore[override]
        return super().__call__(
            calendar=calendar, climate=climate, soil_slope=soil_slope
        )


def engine_fakes() -> tuple[Fake, Fake, Fake]:
    calendar_fn, soil_fn, water_fn = fakes()
    return (
        calendar_fn,
        TakesParameters(soil_fn.answer),
        TakesParameters(water_fn.answer),
    )


def test_ep1_and_ep3_get_the_catalogue_by_keyword_and_ep2_never():
    loaded = catalogue()
    calendar_fn, soil_fn, water_fn = engine_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn),
        carbon_models=CARBON_MODELS,
        parameters=loaded,
    )
    result = engines.run(ROTATION, climate_result(), soil_result())
    assert result.result is not None
    for fake in (soil_fn, water_fn):
        assert len(fake.calls) == PHASES
        for args, kwargs in fake.calls:
            assert args == ()
            assert set(kwargs) == {"calendar", "climate", "soil_slope", "parameters"}
            assert kwargs["parameters"] is loaded  # the same object, not a copy
    # EP2 is never given the catalogue.
    assert calendar_fn.calls == [((RotationDefinition.model_validate(ROTATION),), {})]


@pytest.mark.parametrize("which", [1, 2])
def test_an_engine_without_a_parameters_argument_is_500(which):
    """The runner no longer adapts to a signature: such an engine is a defect."""
    parts = list(engine_fakes())
    parts[which] = WithoutParameters(parts[which].answer)
    engines = EntryPointEngines(
        functions(*parts), carbon_models=CARBON_MODELS, parameters=catalogue()
    )
    with pytest.raises(TypeError):
        engines.run(ROTATION, climate_result(), soil_result())
    response = client(engines).post(ROUTE, json=BODY, headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert parts[which].calls == []


def test_the_catalogue_passes_unchanged_and_is_the_same_object_every_call():
    loaded = catalogue()
    before = json.loads(json.dumps(loaded))
    calendar_fn, soil_fn, water_fn = engine_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn),
        carbon_models=CARBON_MODELS,
        parameters=loaded,
    )
    assert engines.parameters is loaded
    for _ in range(2):
        engines.run(ROTATION, climate_result(), soil_result())
    passed = [
        kwargs["parameters"] for fake in (soil_fn, water_fn) for _, kwargs in fake.calls
    ]
    assert len(passed) == 2 * 2 * PHASES  # two runs, two engines, every phase
    assert all(item is loaded for item in passed)
    assert loaded == before


def test_engines_that_require_parameters_answer_200_through_the_route():
    loaded = catalogue()
    calendar_fn, soil_fn, water_fn = engine_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn),
        carbon_models=CARBON_MODELS,
        parameters=loaded,
    )
    response = client(engines).post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text
    assert response.json()["result"] is not None
    for fake in (soil_fn, water_fn):
        assert len(fake.calls) == PHASES
        for _, kwargs in fake.calls:
            assert kwargs["parameters"] is loaded


def test_without_a_catalogue_the_runner_passes_the_empty_one():
    calendar_fn, soil_fn, water_fn = engine_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn), carbon_models=CARBON_MODELS
    )
    engines.run(ROTATION, climate_result(), soil_result())
    for fake in (soil_fn, water_fn):
        assert len(fake.calls) == PHASES
        for _, kwargs in fake.calls:
            assert kwargs["parameters"] == {}
            assert kwargs["parameters"] is engines.parameters


def test_the_empty_catalogue_given_is_passed_as_given():
    empty: dict[str, dict] = {}
    calendar_fn, soil_fn, water_fn = engine_fakes()
    engines = EntryPointEngines(
        functions(calendar_fn, soil_fn, water_fn),
        carbon_models=CARBON_MODELS,
        parameters=empty,
    )
    engines.run(ROTATION, climate_result(), soil_result())
    assert len(soil_fn.calls) == PHASES
    for _, kwargs in soil_fn.calls:
        assert kwargs["parameters"] is empty


@pytest.mark.parametrize("bad", [[], "PLACEHOLDER", ({},)])
def test_the_catalogue_must_be_a_dict(bad):
    with pytest.raises(TypeError):
        EntryPointEngines(EngineFunctions(), parameters=bad)


def test_create_app_gives_its_catalogue_to_the_default_engines(monkeypatch):
    loaded = catalogue()
    calendar_fn, soil_fn, water_fn = engine_fakes()
    monkeypatch.setattr(
        "api.app.discover_engine_functions",
        lambda: functions(calendar_fn, soil_fn, water_fn),
    )
    app_client = TestClient(
        create_app(
            [ORIGIN],
            climate=FakeClimate(),
            soil_slope=ExampleSoilSlopeSource(SOIL_SLOPE_FILE),
            settings=PERIOD,
            parameters=loaded,
        )
    )
    response = app_client.post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text
    for fake in (soil_fn, water_fn):
        assert len(fake.calls) == PHASES
        for _, kwargs in fake.calls:
            assert kwargs["parameters"] is loaded


def test_create_app_refuses_a_catalogue_beside_engines_passed_in():
    engines = EntryPointEngines(EngineFunctions(), carbon_models=CARBON_MODELS)
    with pytest.raises(TypeError):
        create_app([ORIGIN], engines=engines, parameters={})


def test_the_default_app_with_the_engines_of_the_repository_answers_200():
    """The engines on this branch, each given ``parameters``, give no ``TypeError``.

    The empty catalogue is today's state of params/records/.
    """
    app_client = TestClient(
        create_app(
            [ORIGIN],
            climate=FakeClimate(),
            soil_slope=ExampleSoilSlopeSource(SOIL_SLOPE_FILE),
            settings=PERIOD,
            parameters={},
        )
    )
    response = app_client.post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text


def test_takes_parameters_helper_kept_for_the_chain_test():
    """``takes_parameters`` is kept only for ``validation/test_chain_examples.py``."""

    def keyword_only(*, parameters):
        return parameters

    def positional_or_keyword(parameters):
        return parameters

    def positional_only(parameters, /):
        return parameters

    def without(calendar):
        return calendar

    assert runner.takes_parameters(keyword_only)
    assert runner.takes_parameters(positional_or_keyword)
    assert not runner.takes_parameters(positional_only)
    assert not runner.takes_parameters(without)


# --- 15. EP5 run_amg on the CarbonForcing of the runner (unit l2/runner-amg) ----
#
# The climate is the chain example under the identifiers of the calendar
# example, so its record holds a whole agricultural year from the calendar's
# start month and the forcing can be laid out. The fake EP5 returns the
# PLACEHOLDER CarbonBalance example under the identifiers of the forcing.

CHAIN_CLIMATE_DOCUMENT = example("inputs", "PLACEHOLDER_chain_site_climate.json")
BALANCE_DOCUMENT = example("carbon_balance", "PLACEHOLDER_carbon_balance.json")


def chain_climate() -> SiteClimate:
    document = json.loads(json.dumps(CHAIN_CLIMATE_DOCUMENT))
    document["case_id"] = CALENDAR_DOCUMENT["case_id"]
    document["field_id"] = CALENDAR_DOCUMENT["field_id"]
    return SiteClimate.model_validate(document)


def balance(**update: Any) -> CarbonBalance:
    document = json.loads(json.dumps(BALANCE_DOCUMENT))
    for field in ("case_id", "field_id", "rotation_id"):
        document[field] = CALENDAR_DOCUMENT[field]
    carbon_model = update.pop("carbon_model", None)
    if carbon_model is not None:
        document["carbon_model"] = carbon_model
        for row in document["soil_carbon_trend"]:
            row["carbon_model"] = carbon_model
    document.update(update)
    return CarbonBalance.model_validate(document)


class ChainClimate(FakeClimate):
    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return climate_result(chain_climate())


def with_amg(amg: Any, *parts: Fake | None) -> EngineFunctions:
    calendar_fn, soil_fn, water_fn = parts or fakes()
    return EngineFunctions(
        build_rotation_calendar=calendar_fn,
        compute_soil_loss=soil_fn,
        compute_water_deficit_exposure=water_fn,
        run_amg=amg,
    )


def carbon_rows(result, carbon_model: str) -> list[SoilCarbonTrend]:
    return [
        r for r in result.result.soil_carbon_trend if r.carbon_model == carbon_model
    ]


def test_ep5_rows_reach_the_result_unchanged_and_rothc_stays_missing():
    amg = Fake(balance())
    result = run(with_amg(amg), climate=climate_result(chain_climate()))
    assert len(amg.calls) == PHASES
    assert carbon_rows(result, "amg") == amg.answer.soil_carbon_trend
    assert all(
        a is b for a, b in zip(carbon_rows(result, "amg"), amg.answer.soil_carbon_trend)
    )
    rothc = carbon_rows(result, "rothc")
    assert sorted(r.computation for r in rothc) == sorted(TREND_COMPUTATIONS)
    assert all(r.value is None for r in rothc)
    assert all(r.missing.reason == "NOT_AVAILABLE" for r in rothc)
    assert all("engine.rothc.run_rothc" in r.missing.detail for r in rothc)
    # The order of the configured models, three rows each.
    assert [r.carbon_model for r in result.result.soil_carbon_trend] == [
        model for model in CARBON_MODELS for _ in TREND_COMPUTATIONS
    ]
    text = json.dumps(result.result.model_dump(mode="json"))
    assert ResultsPerRotation.model_validate_json(text) == result.result


def test_ep5_module_states_and_counts():
    amg = Fake(balance())
    result = run(with_amg(amg), climate=climate_result(chain_climate()))
    count = count_values(amg.answer.soil_carbon_trend)
    assert states(result)["amg"] == (
        module_status_of("amg", count).state,
        module_status_of("amg", count).reason,
    )
    assert count.present and count.missing  # the example: degraded
    assert states(result)["amg"][0] == "degraded"
    assert states(result)["residues"] == ("not_available", "NOT_AVAILABLE")
    assert states(result)["rothc"] == ("not_available", "NOT_AVAILABLE")
    whole = count_values(result_values(result.result))
    assert (result.values_present, result.values_missing) == (
        whole.present,
        whole.missing,
    )


def test_ep5_gets_the_forcing_and_the_same_catalogue_by_keyword():
    parameters = catalogue()
    calendar_fn, soil_fn, water_fn = engine_fakes()
    amg = Fake(balance())
    engines = EntryPointEngines(
        with_amg(amg, calendar_fn, soil_fn, water_fn),
        carbon_models=CARBON_MODELS,
        parameters=parameters,
    )
    for _ in range(2):
        engines.run(ROTATION, climate_result(chain_climate()), soil_result())
    for args, kwargs in amg.calls:
        (forcing,) = args
        assert isinstance(forcing, CarbonForcing)
        assert set(kwargs) == {"parameters"}
        assert kwargs["parameters"] is parameters
        assert kwargs["parameters"] is soil_fn.calls[0][1]["parameters"]
        assert kwargs["parameters"] is water_fn.calls[0][1]["parameters"]
        assert (forcing.case_id, forcing.field_id, forcing.rotation_id) == (
            CALENDAR_DOCUMENT["case_id"],
            CALENDAR_DOCUMENT["field_id"],
            CALENDAR_DOCUMENT["rotation_id"],
        )


def test_ep5_is_called_after_ep2_ep1_and_ep3():
    order: list[str] = []

    def recording(name: str, answer: Any):
        def call(*args, **kwargs):
            order.append(name)
            return answer

        return call

    calendar_fn, soil_fn, water_fn = fakes()
    run(
        with_amg(
            recording("EP5", balance()),
            recording("EP2", calendar_fn.answer),
            recording("EP1", soil_fn.answer),
            recording("EP3", water_fn.answer),
        ),
        climate=climate_result(chain_climate()),
    )
    assert order == ["EP2", *["EP1", "EP3", "EP5"] * PHASES]


def test_ep5_not_built_is_the_answer_before_ep5_existed():
    climate = climate_result(chain_climate())
    without = run(functions(*fakes()), climate=climate)
    explicit = run(with_amg(None), climate=climate)
    assert explicit == without
    for row in explicit.result.soil_carbon_trend:
        assert row.missing == Missing(
            reason="NOT_AVAILABLE", detail=runner.CARBON_NOT_BUILT
        )
    carbon = [m for m in explicit.modules if m.id in CARBON_STATES]
    assert [(m.state, m.reason, m.detail) for m in carbon] == [
        ("not_available", "NOT_AVAILABLE", runner.CARBON_NOT_BUILT)
    ] * 3


@pytest.mark.parametrize(
    "climate_data, soil_data",
    [(None, SOIL_SLOPE), (CLIMATE, None)],
    ids=["no-climate", "no-soil"],
)
def test_ep5_not_called_when_an_input_is_absent(climate_data, soil_data):
    amg = Fake(balance())
    result = run(
        with_amg(amg),
        climate=climate_result(climate_data),
        soil=soil_result(soil_data),
    )
    assert amg.calls == []
    assert result.result is None
    assert result.result_missing.reason == "MISSING_INPUT"
    assert states(result)["amg"] == ("not_available", "MISSING_INPUT")
    assert states(result)["rothc"] == ("not_available", "NOT_AVAILABLE")


def test_ep5_not_called_for_site_data_of_another_field():
    amg = Fake(balance())
    other = chain_climate().model_copy(update={"field_id": OTHER_FIELD})
    result = run(with_amg(amg), climate=climate_result(other))
    assert amg.calls == []
    assert states(result)["amg"] == ("not_available", "MISSING_INPUT")
    assert OTHER_FIELD not in (dict_of_modules(result)["amg"].detail or "")


def dict_of_modules(result) -> dict[str, Any]:
    return {m.id: m for m in result.modules}


def test_ep5_with_the_calendar_engine_not_built_is_missing_input():
    amg = Fake(balance())
    result = run(with_amg(amg, None, *fakes()[1:]))
    assert amg.calls == []
    assert states(result)["amg"] == ("not_available", "MISSING_INPUT")
    assert "calendar" in dict_of_modules(result)["amg"].detail


def test_ep5_not_called_when_the_forcing_cannot_be_laid_out():
    # The PLACEHOLDER climate holds a few days: no whole agricultural year.
    amg = Fake(balance())
    result = run(with_amg(amg), climate=climate_result(CLIMATE))
    assert amg.calls == []
    rows = carbon_rows(result, "amg")
    assert sorted(r.computation for r in rows) == sorted(TREND_COMPUTATIONS)
    assert all(r.value is None for r in rows)
    assert all(r.missing.reason == "NO_COVERAGE" for r in rows)
    assert states(result)["amg"] == ("not_available", "NO_COVERAGE")
    assert result.result_missing is None  # the result is still assembled


@pytest.mark.parametrize(
    "wrong",
    [
        BALANCE_DOCUMENT,  # a dictionary, not the model
        "balance-of-another-rotation",
        "balance-of-another-carbon-model",
    ],
    ids=["dict", "other-rotation", "other-carbon-model"],
)
def test_ep5_returning_the_wrong_thing_is_500(wrong):
    if wrong == "balance-of-another-rotation":
        wrong = balance(rotation_id="PLACEHOLDER_OTHER_ROTATION")
    elif wrong == "balance-of-another-carbon-model":
        wrong = balance(carbon_model="rothc")
    engines = EntryPointEngines(with_amg(Fake(wrong)), carbon_models=CARBON_MODELS)
    with pytest.raises(TypeError):
        engines.run(ROTATION, climate_result(chain_climate()), soil_result())
    response = client(engines, climate=ChainClimate()).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_ep5_that_raises_is_500():
    engines = EntryPointEngines(
        with_amg(Fake(raises=True)), carbon_models=CARBON_MODELS
    )
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 500
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text


def test_ep5_through_the_route_loads_back():
    amg = Fake(balance())
    engines = EntryPointEngines(with_amg(amg), carbon_models=CARBON_MODELS)
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    result = ResultsPerRotation.model_validate_json(json.dumps(body["result"]))
    assert [r for r in result.soil_carbon_trend if r.carbon_model == "amg"] == (
        amg.answer.soil_carbon_trend
    )
    assert "carbon_balance" not in json.dumps(body)  # the balance is not exposed
    modules = {m["id"]: m for m in body["modules"]}
    assert modules["amg"]["state"] == "degraded"


def test_the_real_run_amg_with_an_empty_catalogue_answers_200_and_writes_no_number():
    amg_package = pytest.importorskip("engine.amg")
    run_amg = getattr(amg_package, "run_amg", None)
    if run_amg is None:
        pytest.skip("engine.amg.run_amg is not built")
    engines = EntryPointEngines(
        with_amg(run_amg), carbon_models=CARBON_MODELS, parameters={}
    )
    response = client(engines, climate=ChainClimate()).post(ROUTE, json=BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    result = ResultsPerRotation.model_validate_json(json.dumps(body["result"]))
    rows = [r for r in result.soil_carbon_trend if r.carbon_model == "amg"]
    assert sorted(r.computation for r in rows) == sorted(TREND_COMPUTATIONS)
    assert all(r.value is None for r in rows)
    assert all(r.missing.reason and r.missing.detail for r in rows)
    assert numbers_in([r.model_dump(mode="json") for r in rows]) == []
    modules = {m["id"]: m for m in body["modules"]}
    assert modules["amg"]["state"] == "not_available"
    assert modules["amg"]["reason"] == rows[0].missing.reason


# --- 16. remarks of the review of l2/runner-amg ---------------------------------


def test_an_unknown_carbon_model_is_a_value_error_at_construction():
    with pytest.raises(ValueError, match="carbon models"):
        EntryPointEngines(EngineFunctions(), carbon_models=("amg", "PLACEHOLDER"))
    # The closed list comes from the results contract, not from a literal here.
    assert set(runner.CARBON_MODEL_IDS) == set(get_args(CarbonModel))


def run_with_models(amg: Fake, carbon_models: tuple[str, ...]):
    engines = EntryPointEngines(with_amg(amg), carbon_models=carbon_models)
    return engines.run(ROTATION, climate_result(chain_climate()), soil_result())


def test_ep5_not_called_when_amg_is_not_a_configured_model():
    amg = Fake(balance())
    result = run_with_models(amg, ("rothc",))
    assert amg.calls == []
    assert {r.carbon_model for r in result.result.soil_carbon_trend} == {"rothc"}
    modules = dict_of_modules(result)
    assert (modules["amg"].state, modules["amg"].reason) == (
        "not_available",
        "NOT_AVAILABLE",
    )
    assert modules["amg"].detail == runner.AMG_NOT_CONFIGURED


def test_ep5_not_called_when_amg_is_not_configured_and_an_input_is_absent():
    amg = Fake(balance())
    engines = EntryPointEngines(with_amg(amg), carbon_models=("rothc",))
    result = engines.run(ROTATION, climate_result(None), soil_result())
    assert amg.calls == []
    assert dict_of_modules(result)["amg"].detail == runner.AMG_NOT_CONFIGURED


def test_the_rows_are_those_of_ep5_then_ep6_whatever_the_configured_order():
    # contracts/ENTRYPOINTS.md, "From the entry points to one response".
    amg = Fake(balance())
    result = run_with_models(amg, ("rothc", "amg"))
    assert len(amg.calls) == PHASES
    rows = result.result.soil_carbon_trend
    assert [r.carbon_model for r in rows] == ["amg"] * 3 + ["rothc"] * 3
    assert rows[:3] == amg.answer.soil_carbon_trend


@pytest.mark.parametrize(
    "point", [runner.RESIDUES, runner.ROTHC], ids=lambda p: p.entry
)
def test_the_carbon_engines_written_not_built_do_not_exist_yet(point):
    # The runner names these not built without looking. When one lands, this
    # fails: the runner must then discover and call it (a unit of lane L2a).
    assert runner._import_function(point) is None, (
        f"{runner._name(point)} now exists: add it to DISCOVERED"
    )


def test_crops_that_are_not_identifiers_are_counted_in_the_amg_detail():
    amg = Fake(balance())
    result = run(with_amg(amg), climate=climate_result(chain_climate()))
    (forcing,) = amg.calls[0][0]
    assert forcing.annual_carbon_inputs == []  # the example's crops are not ids
    crops = {c["crop_id"] for c in CALENDAR_DOCUMENT["components"]}
    detail = dict_of_modules(result)["amg"].detail
    assert runner.crops_left_out_detail(len(crops)) in detail
    assert not any(crop in detail for crop in crops)  # counted, never repeated


def test_a_soil_property_of_the_site_data_reaches_ep5_unchanged():
    soil_document = example("inputs", "PLACEHOLDER_site_soil_slope.json")
    soil_document["soil_properties"][0]["quantity"] = "clay_content"
    soil = SiteSoilSlope.model_validate(soil_document)
    amg = Fake(balance())
    run(with_amg(amg), climate=climate_result(chain_climate()), soil=soil_result(soil))
    (forcing,) = amg.calls[0][0]
    (clay,) = [p for p in forcing.soil_properties if p.quantity == "clay_content"]
    assert clay == soil.soil_properties[0]
