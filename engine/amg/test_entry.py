"""Acceptance test of EP5 ``run_amg`` (unit l1/amg-ep5, issue #192; the
sixth modifier, the cut of the temperature modifier and the exponential step
by unit l1/amg-v2-complete-d192, issue #299, decisions D192, D193 and D199
of issue #77).

Every number here is a PLACEHOLDER: plainly unreal values with repeated
digits (a stable fraction of 0.999, a starting stock of 99999.9, a clay
content of 999.9, temperatures near 100, a soil C:N ratio of 44.4), chosen
only so that the forms of the core give finite numbers. None is a value of
AMG, and no expected value of the science is written: each computed number is
compared with the core functions called a second time on the same inputs, or
with the mass balance.

The word PLACEHOLDER marks every record. ``read_value`` refuses such a record
and ``check_catalogue`` rejects it, so a test passes the in-memory copy in
which the word is replaced by ``UNMARKED_TEST_ONLY``, as
``engine/water/test_exposure.py`` and ``params/test_layout.py`` do. Nothing
without the word is written to a file.

Run from the repository root: ``python -m pytest engine/amg/test_entry.py``.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.results.models import TREND_COMPUTATIONS, UNIT_SOIL_CARBON_TREND
from engine.amg import entry
from engine.amg.entry import (
    FORCING_QUANTITIES,
    MODIFIERS,
    PARAMETERS,
    SCHEME,
    STEP_UNIT,
    STOCK_UNIT,
    run_amg,
)
from engine.amg.modifiers import (
    carbonate_modifier,
    clay_modifier,
    cn_ratio_modifier,
    moisture_modifier,
    ph_modifier,
    rate_coefficient,
    temperature_modifier,
)
from engine.amg.pools import StepInput, humified_input, initial_state, run
from engine.amg.trend import end_minus_start, fitted_slope
from params.catalogue import check_catalogue

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
FORCING_EXAMPLE = ROOT / "contracts" / "carbon_forcing" / "examples" / "PLACEHOLDER_carbon_forcing.json"  # fmt: skip
README = HERE / "README.md"
MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
YEARS = (2001, 2002, 2003, 2004)  # PLACEHOLDER agricultural years of the horizon
ORIGINS = ("test_origin_a", "test_origin_b")  # scope words: no mark, so they pass


def unmark(item: Any) -> Any:
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {unmark(key): unmark(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmark(value) for value in item]
    return item


# --- the PLACEHOLDER catalogue ------------------------------------------------------

DEGREE = f"{MARK}_degree"
DEPTH = f"{MARK}_depth"
CONTENT = f"{MARK}_content"

# PLACEHOLDER numbers; the unit of each record follows the rule of entry.PARAMETERS.
VALUES: dict[str, tuple[float, str]] = {
    "stable_fraction": (0.999, "dimensionless"),
    "potential_rate": (0.22, f"{STEP_UNIT}-1"),
    "temperature_reference": (99.9, DEGREE),
    "temperature_shape": (2.2, "dimensionless"),
    "temperature_sensitivity": (0.11, f"{DEGREE}-1"),
    "moisture_shape": (0.33, "dimensionless"),
    "moisture_sensitivity": (0.011, f"{DEPTH}-1"),
    "clay_sensitivity": (0.0011, f"{CONTENT}-1"),
    "carbonate_sensitivity": (0.0022, f"{CONTENT}-1"),
    "ph_optimum": (1.11, "dimensionless"),
    "ph_sensitivity": (0.044, "dimensionless"),
    "cn_ratio_sensitivity": (0.0077, "dimensionless"),
    "cn_ratio_optimum": (55.5, "dimensionless"),
    "cn_ratio_minimum": (0.333, "dimensionless"),
}
HUMIFICATION = {ORIGINS[0]: 0.33, ORIGINS[1]: 0.44}


def record(parameter_id: str, value: float | None, unit: str, scope: dict) -> dict:
    data = {
        "id": parameter_id,
        "scope": scope,
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": f"{MARK}: no range in this test",
        "citation": {
            "reference": f"{MARK} reference. This is not a publication.",
            "locator": f"{MARK} locator",
        },
        "transcribed_by": f"{MARK}_person_one",
        "checked_by": f"{MARK}_person_two",
    }
    if value is None:
        data["value_missing_reason"] = f"{MARK}: nobody has given this value"
    return data


def marked_catalogue() -> dict[str, dict]:
    records = {
        f"records/{name}.json": record(PARAMETERS[name][0], value, unit, {})
        for name, (value, unit) in VALUES.items()
    }
    for origin, value in HUMIFICATION.items():
        records[f"records/humification_{origin}.json"] = record(
            PARAMETERS["humification_coefficient"][0],
            value,
            "dimensionless",
            {entry.ORIGIN_SCOPE_KEY: origin},
        )
    return records


def catalogue() -> dict[str, dict]:
    return unmark(marked_catalogue())


def catalogue_with(name: str, change: dict | None) -> dict[str, dict]:
    """The catalogue with the record(s) of one parameter changed, or removed (``None``)."""
    records = marked_catalogue()
    parameter_id = PARAMETERS[name][0]
    for key in [k for k, r in records.items() if r["id"] == parameter_id]:
        if change is None:
            del records[key]
        else:
            records[key] = {**records[key], **change}
    return unmark(records)


# --- the forcing ------------------------------------------------------------------------


def series_header(quantity: str, unit: str) -> dict:
    return {
        "quantity": quantity,
        "unit": unit,
        "provenance": "DERIVED",
        "source": f"{MARK}: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: no range"},
    }


def annual(quantity: str, unit: str, values: list[float | None], **extra) -> dict:
    years = []
    for year, value in zip(YEARS, values, strict=True):
        item: dict = {"ag_year": year, "value": value}
        if value is None:
            item["missing"] = {"reason": "NO_COVERAGE", "detail": f"{MARK}: no data"}
        years.append(item)
    return {
        **series_header(quantity, unit),
        **extra,
        "first_ag_year": YEARS[0],
        "last_ag_year": YEARS[-1],
        "years": years,
    }


def soil(quantity: str, value: float, unit: str) -> dict:
    return {**series_header(quantity, unit), "value": value}


def forcing_data() -> dict:
    """The example forcing over four agricultural years, with what run_amg reads."""
    data = json.loads(FORCING_EXAMPLE.read_text(encoding="utf-8"))
    data["horizon"] = {
        "start": {"year": YEARS[0], "month": 1},
        "end": {"year": YEARS[-1], "month": 12},
    }
    data["climate"] = []
    data["carbon_inputs"] = []
    data["soil_cover"] = []
    quantity = {name: q for name, (_, q) in FORCING_QUANTITIES.items()}
    data["annual_climate"] = [
        annual(quantity["temperature"], unmark(DEGREE), [88.8, 99.9, 111.1, 77.7]),
        annual(quantity["water_balance"], unmark(DEPTH), [-22.2, 33.3, 0.0, 11.1]),
    ]
    data["annual_carbon_inputs"] = [
        annual(
            "placeholder_input_a", STOCK_UNIT, [1.1, 2.2, 0.0, 3.3], origin=ORIGINS[0]
        ),
        annual(
            "placeholder_input_b", STOCK_UNIT, [0.5, 0.0, 1.5, 2.5], origin=ORIGINS[1]
        ),
        annual(
            "placeholder_input_c", STOCK_UNIT, [0.2, 0.2, 0.2, 0.2], origin=ORIGINS[0]
        ),
    ]
    data["soil_properties"] = [
        soil(quantity["clay_content"], 999.9, unmark(CONTENT)),
        soil(quantity["carbonate_content"], 99.9, unmark(CONTENT)),
        soil(quantity["ph"], 9.99, "dimensionless"),
        soil(quantity["cn_ratio"], 44.4, "dimensionless"),
    ]
    data["starting_state"] = [
        {
            **soil(quantity["starting_carbon"], 99999.9, STOCK_UNIT),
            "provenance": "DECLARED",
        }
    ]
    return data


def forcing(data: dict | None = None) -> CarbonForcing:
    return CarbonForcing.model_validate(forcing_data() if data is None else data)


def example_forcing() -> CarbonForcing:
    return CarbonForcing.model_validate(
        json.loads(FORCING_EXAMPLE.read_text(encoding="utf-8"))
    )


# --- helpers -----------------------------------------------------------------------------


def every_value(balance: CarbonBalance) -> list[tuple[str, Any]]:
    """Every value of the balance with where it is: initial stocks, steps, trend values."""
    values = []
    for series in [balance.total_stock, *balance.pools, *balance.flows]:
        if hasattr(series, "initial"):
            values.append((f"{series.quantity}.initial", series.initial))
        values += [(f"{series.quantity}[{i}]", s) for i, s in enumerate(series.steps)]
    values += [(f"trend {t.computation}", t) for t in balance.soil_carbon_trend]
    return values


def details(balance: CarbonBalance) -> list[str]:
    return [
        item.missing.detail for _, item in every_value(balance) if item.value is None
    ]


def core_run(
    data: dict,
    parameters: dict[str, float],
    *,
    scheme: str = SCHEME,
    names: tuple[str, ...] = MODIFIERS,
):
    """The same run built a second time from the core functions, by hand.

    ``names``: the modifiers the rate coefficient multiplies, in this order.
    """
    years = data["annual_climate"]
    temperature = {y["ag_year"]: y["value"] for y in years[0]["years"]}
    balance = {y["ag_year"]: y["value"] for y in years[1]["years"]}
    soil_values = {p["quantity"]: p["value"] for p in data["soil_properties"]}
    q = {name: q for name, (_, q) in FORCING_QUANTITIES.items()}
    deg, depth, content = unmark(DEGREE), unmark(DEPTH), unmark(CONTENT)
    soil_modifiers = {
        "clay": clay_modifier(
            clay_content=soil_values[q["clay_content"]],
            clay_content_unit=content,
            sensitivity_coefficient=parameters["clay_sensitivity"],
            sensitivity_coefficient_per_unit=content,
        ),
        "carbonate": carbonate_modifier(
            carbonate_content=soil_values[q["carbonate_content"]],
            carbonate_content_unit=content,
            sensitivity_coefficient=parameters["carbonate_sensitivity"],
            sensitivity_coefficient_per_unit=content,
        ),
        "ph": ph_modifier(
            ph=soil_values[q["ph"]],
            optimum_ph=parameters["ph_optimum"],
            sensitivity_coefficient=parameters["ph_sensitivity"],
        ),
        "cn_ratio": cn_ratio_modifier(
            cn_ratio=soil_values[q["cn_ratio"]],
            optimum_cn_ratio=parameters["cn_ratio_optimum"],
            sensitivity_coefficient=parameters["cn_ratio_sensitivity"],
            minimum=parameters["cn_ratio_minimum"],
        ),
    }
    steps = []
    for year in YEARS:
        modifiers = {
            "temperature": temperature_modifier(
                temperature=temperature[year],
                temperature_unit=deg,
                reference_temperature=parameters["temperature_reference"],
                reference_temperature_unit=deg,
                shape_coefficient=parameters["temperature_shape"],
                sensitivity_coefficient=parameters["temperature_sensitivity"],
                sensitivity_coefficient_per_unit=deg,
            ),
            "moisture": moisture_modifier(
                water_balance=balance[year],
                water_balance_unit=depth,
                shape_coefficient=parameters["moisture_shape"],
                sensitivity_coefficient=parameters["moisture_sensitivity"],
                sensitivity_coefficient_per_unit=depth,
            ),
            **soil_modifiers,
        }
        inputs = {
            s["quantity"]: next(y["value"] for y in s["years"] if y["ag_year"] == year)
            for s in data["annual_carbon_inputs"]
        }
        coefficients = {
            s["quantity"]: HUMIFICATION[s["origin"]]
            for s in data["annual_carbon_inputs"]
        }
        steps.append(
            StepInput(
                humified_input=humified_input(
                    carbon_inputs=inputs, humification_coefficients=coefficients
                ),
                rate_coefficient=rate_coefficient(
                    potential_rate=parameters["potential_rate"],
                    modifiers={name: modifiers[name] for name in names},
                ),
                duration=1,
            )
        )
    start = initial_state(
        total_carbon=data["starting_state"][0]["value"],
        stable_fraction=parameters["stable_fraction"],
    )
    return run(
        initial_state=start,
        steps=steps,
        rate_coefficient_per_unit=STEP_UNIT,
        duration_unit=STEP_UNIT,
        scheme=scheme,
    )


PLACEHOLDER_NUMBERS = {name: value for name, (value, _) in VALUES.items()}


# --- the acceptance cases of the brief ------------------------------------------------


def test_example_forcing_and_empty_catalogue_give_every_value_missing_naming_parameters():
    balance = run_amg(example_forcing(), parameters={})
    CarbonBalance.model_validate(balance.model_dump(mode="json"))
    values = every_value(balance)
    assert values
    for where, item in values:
        assert item.value is None, where
        assert item.missing.reason == "MISSING_INPUT", where
        assert "parameter 'amg_" in item.missing.detail, where
        assert "no record in parameters (D56)" in item.missing.detail, where


def test_placeholder_catalogue_passes_check_catalogue_and_stocks_are_computed_by_the_core():
    parameters = catalogue()
    assert check_catalogue(parameters) == []
    assert check_catalogue(marked_catalogue()) != []  # the marked records are refused
    data = forcing_data()
    balance = run_amg(forcing(data), parameters=parameters)
    assert all(item.value is not None for _, item in every_value(balance)[:-1])
    expected = core_run(data, PLACEHOLDER_NUMBERS)
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    assert stocks == list(expected.total_stocks())
    active, stable = balance.pools
    assert active.initial.value == expected.initial_state.active
    assert stable.initial.value == expected.initial_state.stable
    for position, step in enumerate(expected.steps):
        assert active.steps[position].value == step.end.active
        assert stable.steps[position].value == step.end.stable
        assert balance.flows[0].steps[position].value == step.humified_input
        assert balance.flows[1].steps[position].value == step.mineralised


def test_mass_balance_holds_at_every_step():
    balance = run_amg(forcing(), parameters=catalogue())
    total = balance.total_stock
    active, stable = balance.pools
    humified, mineralised = balance.flows
    stocks = [total.initial.value] + [s.value for s in total.steps]
    # A difference of two stocks is exact only to the precision of the stocks.
    tolerance = 1e-12 * max(abs(stock) for stock in stocks)
    for position in range(len(total.steps)):
        change = stocks[position + 1] - stocks[position]
        assert math.isclose(
            change,
            humified.steps[position].value - mineralised.steps[position].value,
            rel_tol=1e-12,
            abs_tol=tolerance,
        )
        assert mineralised.steps[position].value >= 0
        assert math.isclose(
            total.steps[position].value,
            active.steps[position].value + stable.steps[position].value,
            rel_tol=1e-12,
        )
        assert stable.steps[position].value == stable.initial.value
    whole = stocks[-1] - stocks[0]
    assert math.isclose(
        whole,
        math.fsum(s.value for s in humified.steps)
        - math.fsum(s.value for s in mineralised.steps),
        rel_tol=1e-12,
        abs_tol=tolerance,
    )


def test_rate_coefficient_multiplies_six_modifiers():
    """D192: the rate coefficient is the potential rate times six modifiers,
    the C:N modifier among them, and the yearly step is the exponential one.
    Every stock equals the core's run built a second time by hand with the
    six and the scheme written here; the mass balance holds."""
    six = ("temperature", "moisture", "clay", "carbonate", "ph", "cn_ratio")
    assert MODIFIERS == six
    assert SCHEME == "exponential"
    parameters = catalogue()
    assert check_catalogue(parameters) == []
    for name in ("cn_ratio_sensitivity", "cn_ratio_optimum", "cn_ratio_minimum"):
        (found,) = [r for r in parameters.values() if r["id"] == PARAMETERS[name][0]]
        assert found["scope"] == {} and found["unit"] == "dimensionless"
    data = forcing_data()
    assert FORCING_QUANTITIES["cn_ratio"] == ("soil_properties", "soil_cn_ratio")
    assert "soil_cn_ratio" in [p["quantity"] for p in data["soil_properties"]]
    balance = run_amg(forcing(data), parameters=parameters)
    expected = core_run(data, PLACEHOLDER_NUMBERS, scheme="exponential", names=six)
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    assert all(stock is not None for stock in stocks)
    assert stocks == list(expected.total_stocks())
    active, stable = balance.pools
    humified, mineralised = balance.flows
    for position, step in enumerate(expected.steps):
        assert active.steps[position].value == step.end.active
        assert stable.steps[position].value == step.end.stable
        assert humified.steps[position].value == step.humified_input
        assert mineralised.steps[position].value == step.mineralised
    # The mass balance, to the precision of the stocks.
    tolerance = 1e-12 * max(abs(stock) for stock in stocks)
    for position in range(len(stocks) - 1):
        assert math.isclose(
            stocks[position + 1] - stocks[position],
            humified.steps[position].value - mineralised.steps[position].value,
            rel_tol=1e-12,
            abs_tol=tolerance,
        )
    # The sixth modifier and the scheme are both used: without the C:N
    # modifier, or with the explicit step, the stocks are other numbers.
    five = core_run(data, PLACEHOLDER_NUMBERS, scheme="exponential", names=six[:-1])
    explicit = core_run(data, PLACEHOLDER_NUMBERS, scheme="explicit", names=six)
    assert list(five.total_stocks()) != stocks
    assert list(explicit.total_stocks()) != stocks
    # The source text of a value names the scheme, the quantity and the records.
    source = balance.total_stock.source
    assert "scheme 'exponential'" in source
    assert "soil_properties 'soil_cn_ratio'" in source
    for name in ("cn_ratio_sensitivity", "cn_ratio_optimum", "cn_ratio_minimum"):
        assert f"'{PARAMETERS[name][0]}'" in source
    # A C:N ratio in a unit other than "dimensionless" is not computed (C1.1).
    data["soil_properties"][-1]["unit"] = unmark(CONTENT)
    detail = run_amg(forcing(data), parameters=parameters).total_stock.steps[0]
    assert detail.value is None
    assert "soil property 'soil_cn_ratio' is in" in detail.missing.detail
    assert "reason NOT_COMPUTABLE" in detail.missing.detail


def test_a_year_at_or_below_zero_temperature_mineralises_nothing():
    """The cut of S8 (D192) through the entry point: in a year whose mean
    temperature is zero or below, the rate coefficient is zero, so the
    mineralised carbon of that year is zero, a value and not a missing, and
    the active pool gains the whole humified input."""
    data = forcing_data()
    data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [88.8, 0.0, -11.1, 77.7]
    )
    balance = run_amg(forcing(data), parameters=catalogue())
    active = balance.pools[0]
    humified, mineralised = balance.flows
    assert [s.value == 0 for s in mineralised.steps] == [False, True, True, False]
    assert all(s.value is not None for s in balance.total_stock.steps)
    before = [active.initial.value] + [s.value for s in active.steps]
    for position in (1, 2):
        assert active.steps[position].value == (
            before[position] + humified.steps[position].value
        )


def test_trend_values_are_those_of_the_core_and_mean_over_cycles_waits_for_its_input():
    balance = run_amg(forcing(), parameters=catalogue())
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    times = [float(i) for i in range(len(stocks))]
    trend = {item.computation: item for item in balance.soil_carbon_trend}
    assert [item.computation for item in balance.soil_carbon_trend] == list(
        TREND_COMPUTATIONS
    )
    assert trend["end_minus_start"].value == end_minus_start(stocks=stocks, times=times)
    assert trend["fitted_slope"].value == fitted_slope(stocks=stocks, times=times)
    for name in ("end_minus_start", "fitted_slope"):
        assert trend[name].unit == UNIT_SOIL_CARBON_TREND
        assert trend[name].provenance == "SIMULATED"
        assert trend[name].carbon_model == "amg"
        assert trend[name].range_missing.reason == "NOT_AVAILABLE"
    cycles = trend["mean_over_cycles"]
    assert cycles.value is None
    assert cycles.missing.reason == "MISSING_INPUT"
    assert cycles.missing.detail.startswith("cycle_boundaries is missing")
    assert "CarbonForcing carries no rotation cycle" in cycles.missing.detail


def test_wrong_types_raise_type_error():
    good = forcing()
    for bad in (None, {}, forcing_data(), good.model_dump(mode="json"), "forcing"):
        with pytest.raises(TypeError, match="forcing"):
            run_amg(bad, parameters={})
    for bad in (None, [], "parameters", {"key": "not a record"}, {1: {}}):
        with pytest.raises(TypeError, match="parameters"):
            run_amg(good, parameters=bad)


def test_the_runner_finds_run_amg_by_its_module_path_and_name():
    """contracts/ENTRYPOINTS.md EP5: module ``engine.amg``, function ``run_amg``.

    The runner of api/engines.py imports each engine with
    ``importlib.import_module(module)`` and ``getattr(module, function)``; this
    is that lookup. Whether the runner lists EP5 among the entries it imports
    is the platform developer's (README.md, OPEN).
    """
    module = importlib.import_module("engine.amg")
    assert getattr(module, "run_amg") is run_amg
    assert callable(run_amg)


# --- what is missing, and why -------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PARAMETERS))
def test_each_parameter_without_a_record_is_named(name):
    balance = run_amg(forcing(), parameters=catalogue_with(name, None))
    parameter_id = PARAMETERS[name][0]
    trend = {item.computation: item for item in balance.soil_carbon_trend}
    assert trend["end_minus_start"].value is None
    assert parameter_id in trend["end_minus_start"].missing.detail
    assert "no record in parameters (D56)" in trend["end_minus_start"].missing.detail
    assert balance.total_stock.steps[-1].value is None


def test_a_record_without_a_value_is_named_with_its_reason():
    parameters = catalogue_with(
        "potential_rate",
        {"value": None, "value_missing_reason": f"{MARK}: nobody has given this value"},
    )
    balance = run_amg(forcing(), parameters=parameters)
    detail = balance.total_stock.steps[0].missing.detail
    assert balance.total_stock.steps[0].missing.reason == "MISSING_INPUT"
    assert "amg_potential_mineralisation_rate" in detail
    assert (
        f"the record holds no value: {UNMARKED}: nobody has given this value" in detail
    )
    assert balance.total_stock.initial.value is not None  # needs no rate


def test_a_placeholder_record_is_not_read():
    records = catalogue()
    key = "records/stable_fraction.json"
    records[key] = marked_catalogue()[key]
    balance = run_amg(forcing(), parameters=records)
    assert "amg_stable_fraction" in balance.total_stock.initial.missing.detail
    assert "the record is not read" in balance.total_stock.initial.missing.detail


def test_a_unit_of_a_record_that_is_not_accepted_is_not_computed():
    balance = run_amg(
        forcing(),
        parameters=catalogue_with("stable_fraction", {"unit": unmark(CONTENT)}),
    )
    detail = balance.total_stock.initial.missing.detail
    assert "reason NOT_COMPUTABLE" in detail
    assert "'dimensionless' (C1.1)" in detail
    balance = run_amg(
        forcing(),
        parameters=catalogue_with("clay_sensitivity", {"unit": unmark(CONTENT)}),
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "amg_clay_sensitivity" in detail and "written 'X-1'" in detail
    balance = run_amg(
        forcing(),
        parameters=catalogue_with("potential_rate", {"unit": unmark(DEPTH) + "-1"}),
    )
    step = balance.total_stock.steps[0].missing
    assert step.reason == "NOT_COMPUTABLE"
    assert "rate_coefficient_per_unit" in step.detail and "duration_unit" in step.detail


@pytest.mark.parametrize("name", sorted(FORCING_QUANTITIES))
def test_each_quantity_the_forcing_lacks_is_named(name):
    part, quantity = FORCING_QUANTITIES[name]
    data = forcing_data()
    data[part] = [item for item in data[part] if item["quantity"] != quantity]
    balance = run_amg(forcing(data), parameters=catalogue())
    detail = balance.soil_carbon_trend[0].missing.detail
    assert f"quantity '{quantity}' has no item in {part} of the forcing" in detail


def test_a_missing_climate_year_makes_that_step_and_every_later_step_missing():
    data = forcing_data()
    data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [88.8, 99.9, None, 77.7]
    )
    balance = run_amg(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [s.value is None for s in steps] == [False, False, True, True]
    assert steps[2].missing.reason == "MISSING_INPUT"
    assert "reason NO_COVERAGE" in steps[2].missing.detail
    assert "step 2 is missing" in steps[3].missing.detail
    assert all(item.value is None for item in balance.soil_carbon_trend)
    assert balance.total_stock.provenance == "SIMULATED"


def test_starting_carbon_or_input_in_another_unit_is_not_computed():
    data = forcing_data()
    data["starting_state"][0]["unit"] = unmark(CONTENT)
    balance = run_amg(forcing(data), parameters=catalogue())
    detail = balance.total_stock.initial.missing.detail
    assert "reason NOT_COMPUTABLE" in detail and "converts nothing" in detail
    data = forcing_data()
    data["annual_carbon_inputs"][1]["unit"] = unmark(CONTENT)
    balance = run_amg(forcing(data), parameters=catalogue())
    detail = balance.flows[0].steps[0].missing.detail
    assert "placeholder_input_b" in detail and "converts nothing" in detail


def test_months_after_the_last_whole_agricultural_year_are_one_step_not_computed():
    data = forcing_data()
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []
    data["horizon"]["end"] = {"year": YEARS[0] + 1, "month": 5}
    balance = run_amg(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [(s.start.year, s.start.month, s.end.year, s.end.month) for s in steps] == [
        (YEARS[0], 1, YEARS[0], 12),
        (YEARS[0] + 1, 1, YEARS[0] + 1, 5),
    ]
    # Without annual series the first step is missing too, so the second names it.
    assert "step 0 is missing" in steps[1].missing.detail
    data["horizon"]["end"] = {"year": YEARS[0], "month": 5}
    balance = run_amg(forcing(data), parameters=catalogue())
    (step,) = balance.total_stock.steps
    assert balance.total_stock.initial.value is not None
    assert step.missing.reason == "MISSING_INPUT"
    assert "reason NOT_COMPUTABLE" in step.missing.detail
    assert "not a whole agricultural year" in step.missing.detail


def test_two_inputs_of_one_origin_take_the_coefficient_of_that_origin():
    data = forcing_data()
    balance = run_amg(forcing(data), parameters=catalogue())
    expected = math.fsum(
        series["years"][0]["value"] * HUMIFICATION[series["origin"]]
        for series in data["annual_carbon_inputs"]
    )
    assert balance.flows[0].steps[0].value == pytest.approx(expected, rel=1e-12)
    parameters = catalogue_with("humification_coefficient", None)
    parameters.update(
        unmark(
            {
                "records/only_b.json": record(
                    PARAMETERS["humification_coefficient"][0],
                    HUMIFICATION[ORIGINS[1]],
                    "dimensionless",
                    {entry.ORIGIN_SCOPE_KEY: ORIGINS[1]},
                )
            }
        )
    )
    detail = (
        run_amg(forcing(data), parameters=parameters).flows[0].steps[0].missing.detail
    )
    assert f'"{entry.ORIGIN_SCOPE_KEY}": "{ORIGINS[0]}"' in detail


# --- the contract and the rules of every entry point -------------------------------------


def test_the_balance_names_the_forcing_and_the_variant():
    data = forcing_data()
    balance = run_amg(forcing(data), parameters=catalogue())
    assert isinstance(balance, CarbonBalance)
    assert (balance.case_id, balance.field_id, balance.rotation_id) == (
        data["case_id"],
        data["field_id"],
        data["rotation_id"],
    )
    assert balance.carbon_model == "amg" and balance.variant == "amg_a"
    assert balance.example_data is True
    assert balance.horizon == forcing(data).horizon
    assert balance.soil_depth == forcing(data).soil_depth
    assert balance.total_stock.unit == STOCK_UNIT
    assert f"{STOCK_UNIT} {STEP_UNIT}-1" == UNIT_SOIL_CARBON_TREND
    assert balance.total_stock.initial.provenance == "DERIVED"
    assert balance.total_stock.provenance == "SIMULATED"
    assert [s.quantity for s in balance.pools] == ["amg_active_pool", "amg_stable_pool"]
    assert [s.quantity for s in balance.flows] == [
        "amg_humified_input",
        "amg_mineralised_carbon",
    ]
    CarbonBalance.model_validate(balance.model_dump(mode="json"))


def test_run_amg_is_pure():
    data = forcing_data()
    given = forcing(data)
    before = given.model_dump(mode="json")
    parameters = catalogue()
    kept = copy.deepcopy(parameters)
    first = run_amg(given, parameters=parameters)
    second = run_amg(given, parameters=parameters)
    assert first == second
    assert given.model_dump(mode="json") == before
    assert parameters == kept


def test_signature_of_the_entry_point():
    parameters = inspect.signature(run_amg).parameters
    assert list(parameters) == ["forcing", "parameters"]
    assert parameters["forcing"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["parameters"].kind is inspect.Parameter.KEYWORD_ONLY
    assert all(p.default is inspect.Parameter.empty for p in parameters.values())


def test_entry_holds_no_value_of_the_method():
    """No number but zero and one in entry.py, as in every module of this folder."""
    import ast

    tree = ast.parse((HERE / "entry.py").read_text(encoding="utf-8"))
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, numbers


def section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("EP5 run_amg: PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written
