"""Acceptance test of api/rain_stress.py (unit l2/heavier-rain, brief S-017).

PROPOSED (blueprint section 3.7). Heavier rain as a stress test: the rainfall
erosivity level of the catalogue (record id ``rusle_r_factor``, read by EP1 on
its main route) is multiplied by a factor the user declares. Expected results
are relations, never numbers: the run with the factor at 1 equals the run
without the option, and with a factor ``f`` every soil-loss value is ``f``
times the value without it. Soil loss is linear in R on EP1's main route:
``engine/erosion/soil_loss.py`` forms the annual value as the product
``annual_soil_loss(R, K, LS, C, P)`` with R the level of ``rusle_r_factor``,
and a monthly value as the level times the climatological fraction of the
month times K, LS, C and P (the fractions come from the twelve monthly
records, not from the level).

The EP1 case: the PLACEHOLDER rotation calendar and the PLACEHOLDER chain
climate of ``contracts/inputs/examples/`` and the demonstration soil file
``data/demo/la_estanzuela_soil_slope.json``, all under the identity of the
chain climate. Catalogue: ``params/records/`` as api/config.py loads it. No
network.
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import math
from pathlib import Path

import pytest

import api.rain_stress as rain_stress_module
from api.config import PARAMETERS_FOLDER, load_parameters
from api.rain_stress import (
    DIMENSIONLESS,
    EP1_SCOPE,
    R_ID,
    STRESS_TEST_LABEL,
    RainStress,
    RainStressMissing,
    applied_echo,
    rain_stress,
    scale_erosivity,
)
from contracts.inputs.common import Missing, Value
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from engine.erosion import compute_soil_loss
from engine.erosion import soil_loss as erosion
from engine.erosion._parameters import read_parameter
from params.catalogue import check_catalogue

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
DEMO_SOIL = ROOT / "data" / "demo" / "la_estanzuela_soil_slope.json"

# Test data, not a value of the product: a heavier-rain factor chosen by the
# test only.
TEST_FACTOR = 1.5
# Test data: the tolerance of a floating-point product.
REL_TOLERANCE = 1e-12


def declared(number: float, unit: str = DIMENSIONLESS) -> Value:
    return Value(
        value=number,
        unit=unit,
        provenance="DECLARED",
        source="test data: a factor declared by the test",
        range_missing=Missing(reason="NOT_AVAILABLE", detail="test data"),
    )


def unchecked(number: object) -> Value:
    """A Value built without validation, to reach the checks of rain_stress."""
    return Value.model_construct(
        value=number,
        unit=DIMENSIONLESS,
        provenance="DECLARED",
        source="test data",
        assumption=False,
        missing=None,
        range=None,
        range_missing=Missing(reason="NOT_AVAILABLE", detail="test data"),
    )


def catalogue() -> dict[str, dict]:
    return load_parameters(PARAMETERS_FOLDER)


def ep1_case() -> tuple[RotationCalendar, SiteClimate, SiteSoilSlope]:
    climate = SiteClimate.model_validate_json(
        (EXAMPLES / "PLACEHOLDER_chain_site_climate.json").read_text("utf-8")
    )
    identity = {"case_id": climate.case_id, "field_id": climate.field_id}
    calendar = json.loads(
        (EXAMPLES / "PLACEHOLDER_rotation_calendar.json").read_text("utf-8")
    )
    calendar.update(identity)
    soil = json.loads(DEMO_SOIL.read_text("utf-8"))
    soil.update(identity)
    return (
        RotationCalendar.model_validate(calendar),
        climate,
        SiteSoilSlope.model_validate(soil),
    )


def run(parameters: dict[str, dict]):
    calendar, climate, soil = ep1_case()
    return compute_soil_loss(calendar, climate, soil, parameters=parameters)


def r_keys(parameters: dict[str, dict]) -> list[str]:
    return [key for key, record in parameters.items() if record.get("id") == R_ID]


# --- the identifiers agree with EP1 and the conventions --------------------------


def test_identifiers_are_those_of_ep1():
    assert R_ID == erosion.R_ID
    assert EP1_SCOPE == erosion.SCOPE
    assert DIMENSIONLESS == erosion.DIMENSIONLESS
    assert STRESS_TEST_LABEL == "stress test"
    assert r_keys(catalogue()), "the catalogue holds the R record"


# --- 1. factor 1 ---------------------------------------------------------------


def test_factor_one_gives_the_same_result():
    parameters = catalogue()
    stress = rain_stress(declared(1.0))
    assert isinstance(stress, RainStress)
    base = run(parameters).model_dump(mode="json")
    stressed = run(scale_erosivity(parameters, stress)).model_dump(mode="json")
    assert stressed == base  # the note is not read by EP1: every field equal


# --- 2. factor f > 1 -------------------------------------------------------------


def test_factor_multiplies_every_soil_loss_value():
    parameters = catalogue()
    stress = rain_stress(declared(TEST_FACTOR))
    assert isinstance(stress, RainStress)
    base = run(parameters)
    stressed = run(scale_erosivity(parameters, stress))
    pairs = list(zip(base.annual, stressed.annual, strict=True)) + list(
        zip(base.monthly, stressed.monthly, strict=True)
    )
    numbers = [(a, b) for a, b in pairs if a.value is not None]
    assert numbers, "the EP1 case gives soil-loss numbers"
    for before, after in pairs:
        if before.value is None:
            assert after.value is None and after.missing == before.missing
            continue
        assert after.value is not None
        assert math.isclose(
            after.value, before.value * TEST_FACTOR, rel_tol=REL_TOLERANCE
        )
        assert after.value > before.value


# --- 3. only the R record changes ------------------------------------------------


def test_only_the_r_record_changes_and_the_input_is_unchanged():
    parameters = catalogue()
    kept = copy.deepcopy(parameters)
    stress = rain_stress(declared(TEST_FACTOR))
    scaled = scale_erosivity(parameters, stress)
    assert parameters == kept
    assert scaled is not parameters
    assert set(scaled) == set(parameters)
    changed = r_keys(parameters)
    for key, record in parameters.items():
        if key not in changed:
            assert scaled[key] == record
            continue
        after = scaled[key]
        assert after is not record
        assert math.isclose(
            after["value"], record["value"] * TEST_FACTOR, rel_tol=REL_TOLERANCE
        )
        assert "stress test: multiplied by" in after["note"]
        assert after["note"].startswith(record["note"])
        others = {k: v for k, v in after.items() if k not in ("value", "note")}
        assert others == {k: v for k, v in record.items() if k not in ("value", "note")}
    assert check_catalogue(scaled) == []


def test_a_range_is_multiplied_at_both_bounds():
    parameters = catalogue()
    (key,) = r_keys(parameters)
    record = copy.deepcopy(parameters[key])
    record.pop("range_missing_reason")
    # Test data: a range around the value, not a range of the source.
    record["range"] = {
        "low": record["value"] / 2,
        "high": record["value"] * 2,
        "basis": "test data",
    }
    parameters[key] = record
    assert check_catalogue(parameters) == []
    scaled = scale_erosivity(parameters, rain_stress(declared(TEST_FACTOR)))
    after = scaled[key]["range"]
    assert math.isclose(after["low"], record["range"]["low"] * TEST_FACTOR)
    assert math.isclose(after["high"], record["range"]["high"] * TEST_FACTOR)
    assert after["basis"] == record["range"]["basis"]
    assert check_catalogue(scaled) == []


def test_no_r_record_returns_an_unchanged_copy_not_applied():
    parameters = {
        key: record for key, record in catalogue().items() if record.get("id") != R_ID
    }
    stress = rain_stress(declared(TEST_FACTOR))
    scaled = scale_erosivity(parameters, stress)
    assert scaled == parameters and scaled is not parameters
    echo = applied_echo(parameters, stress)
    assert isinstance(echo, RainStress) and echo.applied is False
    assert "not applied" in echo.detail
    applied = applied_echo(catalogue(), stress)
    assert applied == stress and applied.applied is True


# --- 4. refused factors ------------------------------------------------------------


@pytest.mark.parametrize(
    "factor",
    [
        declared(0.0),
        declared(-TEST_FACTOR),
        declared(TEST_FACTOR, unit="percent"),
        unchecked(float("nan")),
        unchecked(float("inf")),
        unchecked(True),
    ],
    ids=["zero", "negative", "wrong_unit", "nan", "inf", "bool"],
)
def test_refused_factor_raises_value_error(factor):
    with pytest.raises(ValueError):
        rain_stress(factor)


def test_a_factor_below_one_is_allowed():
    # Test data: lighter rain.
    stress = rain_stress(declared(1 / TEST_FACTOR))
    assert isinstance(stress, RainStress)


def test_not_a_value_is_a_type_error():
    with pytest.raises(TypeError):
        rain_stress(TEST_FACTOR)  # type: ignore[arg-type]


# --- 5. a missing factor -----------------------------------------------------------


def test_missing_factor_gives_no_scaling_and_is_echoed_with_its_reason():
    missing = Missing(reason="NOT_DECLARED", detail="test data: no factor declared")
    stress = rain_stress(Value(value=None, unit=DIMENSIONLESS, missing=missing))
    assert isinstance(stress, RainStressMissing)
    assert stress.missing == missing
    assert "NOT_DECLARED" in stress.detail
    parameters = catalogue()
    scaled = scale_erosivity(parameters, stress)
    assert scaled == parameters and scaled is not parameters
    assert applied_echo(parameters, stress) == stress
    assert run(scaled).model_dump(mode="json") == run(parameters).model_dump(
        mode="json"
    )


# --- 6. the echo text ---------------------------------------------------------------


def no_forecast(text: str) -> bool:
    return "forecast" not in text.replace("not a forecast", "")


def test_the_echo_says_stress_test_never_forecast():
    parameters = catalogue()
    echoes = [
        rain_stress(declared(TEST_FACTOR)),
        rain_stress(
            Value(
                value=None,
                unit=DIMENSIONLESS,
                missing=Missing(reason="NOT_DECLARED", detail="test data"),
            )
        ),
        applied_echo({}, rain_stress(declared(TEST_FACTOR))),
    ]
    for echo in echoes:
        assert echo.label == STRESS_TEST_LABEL
        assert "stress test" in echo.detail
        assert no_forecast(echo.detail) and no_forecast(echo.label)
    (key,) = r_keys(parameters)
    note = scale_erosivity(parameters, echoes[0])[key]["note"]
    assert no_forecast(note.removeprefix(parameters[key]["note"]))
    assert "not a forecast" in echoes[0].detail


# --- 7. no factor constant in the module ---------------------------------------------


def test_the_module_holds_no_factor_number():
    tree = ast.parse(inspect.getsource(rain_stress_module))
    floats = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert floats == []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
            node.value, ast.Constant
        ):
            value = node.value.value
            assert isinstance(value, str), ast.dump(node)


# --- fix round 1: the record EP1 reads, EP1's semantics, provenance, text ------------


def r_key_and_record(parameters: dict[str, dict]) -> tuple[str, dict]:
    (key,) = r_keys(parameters)
    return key, parameters[key]


def test_a_record_of_r_with_another_scope_is_unchanged_and_not_noted():
    parameters = catalogue()
    key, record = r_key_and_record(parameters)
    other = copy.deepcopy(record)
    # Test data: a scope word EP1 does not read.
    other["scope"] = {"region": "test_data_region"}
    parameters["test_data_other_scope.json"] = other
    assert check_catalogue(parameters) == []
    scaled = scale_erosivity(parameters, rain_stress(declared(TEST_FACTOR)))
    assert scaled["test_data_other_scope.json"] == other
    assert scaled[key]["value"] != record["value"]


def test_a_null_r_value_is_not_scaled_nor_noted():
    parameters = catalogue()
    key, record = r_key_and_record(parameters)
    null = copy.deepcopy(record)
    null["value"] = None
    null["value_missing_reason"] = "test data: no value"
    parameters[key] = null
    assert check_catalogue(parameters) == []
    stress = rain_stress(declared(TEST_FACTOR))
    assert scale_erosivity(parameters, stress)[key] == null
    echo = applied_echo(parameters, stress)
    assert echo.applied is False and "has no value" in echo.detail


def test_a_numeric_value_with_a_bound_that_is_not_a_number_is_a_value_error():
    parameters = catalogue()
    key, record = r_key_and_record(parameters)
    broken = copy.deepcopy(record)
    broken.pop("range_missing_reason")
    broken["range"] = {"low": "test data", "high": record["value"], "basis": "test"}
    parameters[key] = broken
    with pytest.raises(ValueError):
        scale_erosivity(parameters, rain_stress(declared(TEST_FACTOR)))


def duplicate(parameters: dict[str, dict]) -> None:
    _, record = r_key_and_record(parameters)
    parameters["test_data_duplicate.json"] = copy.deepcopy(record)


def placeholder(parameters: dict[str, dict]) -> None:
    key, record = r_key_and_record(parameters)
    parameters[key] = {**record, "note": f"{record['note']} PLACEHOLDER"}


def null_value(parameters: dict[str, dict]) -> None:
    key, record = r_key_and_record(parameters)
    parameters[key] = {**record, "value": None, "value_missing_reason": "test data"}


def malformed_elsewhere(parameters: dict[str, dict]) -> None:
    parameters["test_data_malformed.json"] = {"id": "_not_an_id", "scope": {}}


def no_record(parameters: dict[str, dict]) -> None:
    key, _ = r_key_and_record(parameters)
    del parameters[key]


@pytest.mark.parametrize(
    "change",
    [duplicate, placeholder, null_value, malformed_elsewhere, no_record],
    ids=["duplicate", "placeholder", "null_value", "malformed", "no_record"],
)
def test_applied_echo_follows_ep1_reader(change):
    parameters = catalogue()
    stress = rain_stress(declared(TEST_FACTOR))
    assert isinstance(read_parameter(parameters, R_ID, EP1_SCOPE).value, float)
    assert applied_echo(parameters, stress) == stress
    change(parameters)
    read = read_parameter(parameters, R_ID, EP1_SCOPE)
    assert not isinstance(read.value, float)
    echo = applied_echo(parameters, stress)
    assert isinstance(echo, RainStress) and echo.applied is False
    assert echo.factor == stress.factor and echo.declared == stress.declared
    assert "not applied" in echo.detail and "not a forecast" in echo.detail


def test_a_placeholder_r_record_is_not_scaled():
    parameters = catalogue()
    placeholder(parameters)
    key, record = r_key_and_record(parameters)
    scaled = scale_erosivity(parameters, rain_stress(declared(TEST_FACTOR)))
    assert scaled[key] == record


def test_the_declared_factor_travels_with_the_stress():
    factor = declared(TEST_FACTOR)
    stress = rain_stress(factor)
    assert isinstance(stress, RainStress)
    assert stress.declared == factor
    assert stress.declared.provenance == "DECLARED"
    assert stress.declared.source == factor.source


def test_the_scaled_record_keeps_its_citation_and_signatures():
    parameters = catalogue()
    key, record = r_key_and_record(parameters)
    after = scale_erosivity(parameters, rain_stress(declared(TEST_FACTOR)))[key]
    for name in ("citation", "transcribed_by", "checked_by"):
        assert after[name] == record[name]


def test_applied_echo_checks_its_arguments():
    stress = rain_stress(declared(TEST_FACTOR))
    with pytest.raises(TypeError, match="parameters"):
        applied_echo([], stress)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="stress"):
        applied_echo(catalogue(), TEST_FACTOR)  # type: ignore[arg-type]


def test_the_factor_is_written_without_float_artefacts():
    # Test data: a product whose float repr carries an artefact.
    number = 1.1 * 1.1
    assert repr(number) != "1.21"
    stress = rain_stress(declared(number))
    parameters = catalogue()
    key, _ = r_key_and_record(parameters)
    note = scale_erosivity(parameters, stress)[key]["note"]
    for text in (stress.detail, note):
        assert "multiplied by 1.21 " in f"{text} "
        assert repr(number) not in text


def test_a_missing_factor_without_its_missing_part_is_refused():
    # A Value built without validation (model_construct) may break C3.1; the
    # guard is an explicit check, so it holds also under python -O.
    broken = Value.model_construct(value=None, unit=DIMENSIONLESS, missing=None)
    with pytest.raises(ValueError, match="C3.1"):
        rain_stress(broken)


@pytest.mark.parametrize("number", [1.2345678, 1.0000001])
def test_a_factor_with_many_digits_is_written_exactly(number):
    # Test data: factors with more than 6 significant digits (invented).
    stress = rain_stress(declared(number))
    parameters = catalogue()
    key, _ = r_key_and_record(parameters)
    note = scale_erosivity(parameters, stress)[key]["note"]
    for text in (stress.detail, note):
        assert f"multiplied by {number!r} " in f"{text} "


# --- review of the whole 4 (brief S-034), PROPOSED test cases ----------------------

# Test data: an int factor too large for a float. A RainStress built by hand
# (rain_stress() turns every factor into a float); the product overflows.
OVERFLOWING_INT_FACTOR = 10**400


def test_f4_a_product_that_overflows_is_not_finite_never_an_exception():
    """F4: number * factor raising OverflowError is "not finite", not a raise."""
    from dataclasses import replace

    from api.rain_stress import scales_to_finite

    parameters = catalogue()
    stress = replace(rain_stress(declared(TEST_FACTOR)), factor=OVERFLOWING_INT_FACTOR)
    assert scales_to_finite(parameters, stress) is False
    # scale_erosivity raises the ValueError its docstring names, not OverflowError.
    with pytest.raises(ValueError, match="not a finite number"):
        scale_erosivity(parameters, stress)
