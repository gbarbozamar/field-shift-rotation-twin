"""Acceptance and invariant tests for experimental AMG-M ``run_amg_monthly`` (D80).

Every number here is a PLACEHOLDER (plainly unreal values with repeated digits,
or simple test fractions), chosen only so that the forms of the core give finite
numbers. None is a value of AMG, and no expected value of the science is
written: computed values are verified against the core functions called directly,
against ``run_amg`` under uniform forcing (D80 / blueprint section 8), and
against exact step-by-step mass balance.

Run from the repository root:
``py -3.12 -m pytest engine/amg/test_monthly_entry.py``.
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import math
from pathlib import Path
from typing import Any

import pytest

from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.results.models import TREND_COMPUTATIONS, UNIT_SOIL_CARBON_TREND
from engine.amg import entry, monthly_entry
from engine.amg.entry import (
    MODIFIERS,
    MONTHS,
    ORIGIN_SCOPE_KEY,
    PARAMETERS,
    POOL_QUANTITIES,
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
from engine.amg.monthly_entry import (
    FORCING_QUANTITIES,
    METHOD_LABEL,
    VARIANT,
    run_amg_monthly,
)
from engine.amg.pools import StepInput, humified_input, initial_state, run
from engine.amg.test_entry import (
    CONTENT,
    DEGREE,
    DEPTH,
    FORCING_EXAMPLE,
    HUMIFICATION,
    MARK,
    ORIGINS,
    PLACEHOLDER_NUMBERS,
    UNMARKED,
    YEARS,
    carriers,
    catalogue,
    catalogue_with,
    every_value,
    example_forcing,
    marked_catalogue,
    record,
    series_header,
    unmark,
)
from engine.amg.test_entry import forcing_data as annual_forcing_data
from engine.amg.trend import end_minus_start, fitted_slope
from params.catalogue import check_catalogue

HERE = Path(__file__).parent


# --- monthly PLACEHOLDER forcing helpers -------------------------------------


def _horizon_months(
    start: tuple[int, int] = (YEARS[0], 1),
    end: tuple[int, int] = (YEARS[-1], 12),
) -> list[tuple[int, int]]:
    months = []
    year, month = start
    while (year, month) <= end:
        months.append((year, month))
        year, month = (year, month + 1) if month < MONTHS else (year + 1, 1)
    return months


def monthly_series(
    quantity: str,
    unit: str,
    values: list[float | None],
    *,
    start: tuple[int, int] = (YEARS[0], 1),
    end: tuple[int, int] = (YEARS[-1], 12),
    **extra: Any,
) -> dict:
    horizon = _horizon_months(start, end)
    items = []
    for (year, month), value in zip(horizon, values, strict=True):
        item: dict[str, Any] = {"year": year, "month": month, "value": value}
        if value is None:
            item["missing"] = {"reason": "NO_COVERAGE", "detail": f"{MARK}: no data"}
        items.append(item)
    return {
        **series_header(quantity, unit),
        **extra,
        "start": {"year": start[0], "month": start[1]},
        "end": {"year": end[0], "month": end[1]},
        "months": items,
    }


def _uniform_monthly_from_annual(annual_data: dict) -> dict:
    """Turn an annual-forcing dict into a uniform monthly-forcing dict."""
    data = copy.deepcopy(annual_data)
    q = {name: qty for name, (_, qty) in FORCING_QUANTITIES.items()}
    annual_temp = {
        y["ag_year"]: y["value"] for y in annual_data["annual_climate"][0]["years"]
    }
    annual_wb = {
        y["ag_year"]: y["value"] for y in annual_data["annual_climate"][1]["years"]
    }
    months = _horizon_months()
    data["climate"] = [
        monthly_series(
            q["temperature"],
            unmark(DEGREE),
            [annual_temp[year] for year, _ in months],
        ),
        monthly_series(
            q["water_balance"],
            unmark(DEPTH),
            [annual_wb[year] for year, _ in months],
        ),
    ]
    monthly_inputs = []
    for series in annual_data["annual_carbon_inputs"]:
        by_year = {y["ag_year"]: y["value"] for y in series["years"]}
        monthly_inputs.append(
            monthly_series(
                series["quantity"],
                series["unit"],
                [by_year[year] / MONTHS for year, _ in months],
                origin=series["origin"],
            )
        )
    data["carbon_inputs"] = monthly_inputs
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []
    return data


def forcing_data(*, non_uniform: bool = False) -> dict:
    """Monthly PLACEHOLDER forcing over four years (48 calendar months)."""
    data = _uniform_monthly_from_annual(annual_forcing_data())
    if not non_uniform:
        return data
    months = _horizon_months()
    # Seasonal PLACEHOLDER variation around the base values.
    q = {name: qty for name, (_, qty) in FORCING_QUANTITIES.items()}
    temps = [
        88.8 + (month - 6) * 2.5 for _, month in months
    ]
    wbs = [
        -22.2 + (month - 6) * 5.5 for _, month in months
    ]
    data["climate"] = [
        monthly_series(q["temperature"], unmark(DEGREE), temps),
        monthly_series(q["water_balance"], unmark(DEPTH), wbs),
    ]
    # Put residue inputs at harvest month 4 and zero in other months.
    data["carbon_inputs"] = [
        monthly_series(
            "placeholder_input_a",
            STOCK_UNIT,
            [3.3 if month == 4 else 0.0 for _, month in months],
            origin=ORIGINS[0],
        ),
        monthly_series(
            "placeholder_input_b",
            STOCK_UNIT,
            [1.5 if month == 10 else 0.0 for _, month in months],
            origin=ORIGINS[1],
        ),
    ]
    return data


def forcing(data: dict | None = None) -> CarbonForcing:
    return CarbonForcing.model_validate(forcing_data() if data is None else data)


def core_run_monthly(data: dict, parameters: dict[str, float]):
    """Rebuild the monthly run directly from the core functions."""
    temp_series = {
        (m["year"], m["month"]): m["value"] for m in data["climate"][0]["months"]
    }
    wb_series = {
        (m["year"], m["month"]): m["value"] for m in data["climate"][1]["months"]
    }
    soil_values = {p["quantity"]: p["value"] for p in data["soil_properties"]}
    q = {name: qty for name, (_, qty) in FORCING_QUANTITIES.items()}
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
    start_ym = data["horizon"]["start"]
    end_ym = data["horizon"]["end"]
    months = _horizon_months(
        (start_ym["year"], start_ym["month"]),
        (end_ym["year"], end_ym["month"]),
    )
    steps = []
    for ym in months:
        modifiers = {
            "temperature": temperature_modifier(
                temperature=temp_series[ym],
                temperature_unit=deg,
                reference_temperature=parameters["temperature_reference"],
                reference_temperature_unit=deg,
                shape_coefficient=parameters["temperature_shape"],
                sensitivity_coefficient=parameters["temperature_sensitivity"],
                sensitivity_coefficient_per_unit=deg,
            ),
            "moisture": moisture_modifier(
                water_balance=wb_series[ym],
                water_balance_unit=depth,
                shape_coefficient=parameters["moisture_shape"],
                sensitivity_coefficient=parameters["moisture_sensitivity"],
                sensitivity_coefficient_per_unit=depth,
            ),
            **soil_modifiers,
        }
        inputs = {
            s["quantity"]: next(
                m["value"]
                for m in s["months"]
                if (m["year"], m["month"]) == ym
            )
            for s in data["carbon_inputs"]
        }
        coefficients = {
            s["quantity"]: HUMIFICATION[s["origin"]]
            for s in data["carbon_inputs"]
        }
        steps.append(
            StepInput(
                humified_input=humified_input(
                    carbon_inputs=inputs, humification_coefficients=coefficients
                ),
                rate_coefficient=rate_coefficient(
                    potential_rate=parameters["potential_rate"],
                    modifiers={name: modifiers[name] for name in MODIFIERS},
                ),
                duration=1 / MONTHS,
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
        scheme=SCHEME,
    )


# --- core correspondence and D80 uniform-forcing check -----------------------


def test_example_forcing_and_empty_catalogue_give_every_value_missing_naming_parameters():
    balance = run_amg_monthly(example_forcing(), parameters={})
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
    assert check_catalogue(marked_catalogue()) != []
    data = forcing_data(non_uniform=True)
    balance = run_amg_monthly(forcing(data), parameters=parameters)
    assert all(item.value is not None for _, item in every_value(balance)[:-1])
    expected = core_run_monthly(data, PLACEHOLDER_NUMBERS)
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


def test_uniform_forcing_matches_run_amg_annual_reference():
    """D80 / blueprint section 8: under uniform forcing within each agricultural
    year, 12 monthly exponential steps match one annual step of ``run_amg``."""
    parameters = catalogue()
    annual_data = annual_forcing_data()
    monthly_data = _uniform_monthly_from_annual(annual_data)

    annual_bal = run_amg(forcing(annual_data), parameters=parameters)
    monthly_bal = run_amg_monthly(forcing(monthly_data), parameters=parameters)

    assert len(monthly_bal.total_stock.steps) == len(YEARS) * MONTHS
    assert monthly_bal.total_stock.initial.value == annual_bal.total_stock.initial.value
    assert monthly_bal.pools[0].initial.value == annual_bal.pools[0].initial.value
    assert monthly_bal.pools[1].initial.value == annual_bal.pools[1].initial.value

    m_humified, m_mineralised = monthly_bal.flows
    a_humified, a_mineralised = annual_bal.flows
    for year_idx in range(len(YEARS)):
        end_month = (year_idx + 1) * MONTHS - 1
        start_month = year_idx * MONTHS
        assert monthly_bal.total_stock.steps[end_month].value == pytest.approx(
            annual_bal.total_stock.steps[year_idx].value, rel=1e-12
        )
        assert monthly_bal.pools[0].steps[end_month].value == pytest.approx(
            annual_bal.pools[0].steps[year_idx].value, rel=1e-12
        )
        assert monthly_bal.pools[1].steps[end_month].value == (
            annual_bal.pools[1].steps[year_idx].value
        )
        assert math.fsum(
            s.value for s in m_humified.steps[start_month : end_month + 1]
        ) == pytest.approx(a_humified.steps[year_idx].value, rel=1e-12)
        assert math.fsum(
            s.value for s in m_mineralised.steps[start_month : end_month + 1]
        ) == pytest.approx(a_mineralised.steps[year_idx].value, rel=1e-12)

    m_trend = {t.computation: t for t in monthly_bal.soil_carbon_trend}
    a_trend = {t.computation: t for t in annual_bal.soil_carbon_trend}
    assert m_trend["end_minus_start"].value == pytest.approx(
        a_trend["end_minus_start"].value, rel=1e-12
    )


def test_mass_balance_holds_at_every_month_for_non_uniform_forcing():
    parameters = catalogue()
    uniform_bal = run_amg_monthly(forcing(forcing_data()), parameters=parameters)
    balance = run_amg_monthly(
        forcing(forcing_data(non_uniform=True)), parameters=parameters
    )
    assert (
        balance.total_stock.steps[-1].value
        != uniform_bal.total_stock.steps[-1].value
    )
    total = balance.total_stock
    active, stable = balance.pools
    humified, mineralised = balance.flows
    stocks = [total.initial.value] + [s.value for s in total.steps]
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


def test_a_month_at_or_below_zero_temperature_mineralises_nothing():
    data = forcing_data()
    months = _horizon_months()
    temps = [88.8] * len(months)
    temps[1] = 0.0
    temps[2] = -11.1
    data["climate"][0] = monthly_series(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), temps
    )
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    active = balance.pools[0]
    humified, mineralised = balance.flows
    assert [s.value == 0 for s in mineralised.steps[:4]] == [False, True, True, False]
    assert all(s.value is not None for s in balance.total_stock.steps)
    before = [active.initial.value] + [s.value for s in active.steps]
    for position in (1, 2):
        assert active.steps[position].value == (
            before[position] + humified.steps[position].value
        )


def test_non_whole_year_and_single_month_horizons_step_month_by_month():
    parameters = catalogue()
    for start, end in (
        ((YEARS[0], 1), (YEARS[0], 1)),
        ((YEARS[0], 1), (YEARS[0], 5)),
        ((YEARS[0], 7), (YEARS[0] + 1, 7)),
    ):
        months = _horizon_months(start, end)
        data = forcing_data()
        data["horizon"] = {
            "start": {"year": start[0], "month": start[1]},
            "end": {"year": end[0], "month": end[1]},
        }
        q = {name: qty for name, (_, qty) in FORCING_QUANTITIES.items()}
        data["climate"] = [
            monthly_series(
                q["temperature"], unmark(DEGREE), [99.9] * len(months), start=start, end=end
            ),
            monthly_series(
                q["water_balance"], unmark(DEPTH), [11.1] * len(months), start=start, end=end
            ),
        ]
        data["carbon_inputs"] = [
            monthly_series(
                "placeholder_input_a",
                STOCK_UNIT,
                [0.2] * len(months),
                start=start,
                end=end,
                origin=ORIGINS[0],
            )
        ]
        balance = run_amg_monthly(forcing(data), parameters=parameters)
        steps = balance.total_stock.steps
        assert len(steps) == len(months)
        for step, (year, month) in zip(steps, months, strict=True):
            assert (step.start.year, step.start.month) == (year, month)
            assert (step.end.year, step.end.month) == (year, month)
            assert step.value is not None
        trend = {item.computation: item for item in balance.soil_carbon_trend}
        assert trend["end_minus_start"].value is not None
        assert trend["fitted_slope"].value is not None


def test_trend_values_are_those_of_the_core_and_mean_over_cycles_waits_for_its_input():
    balance = run_amg_monthly(forcing(), parameters=catalogue())
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    times = [math.fsum([1 / MONTHS] * i) for i in range(len(stocks))]
    trend = {item.computation: item for item in balance.soil_carbon_trend}
    assert [item.computation for item in balance.soil_carbon_trend] == list(
        TREND_COMPUTATIONS
    )
    assert trend["end_minus_start"].value == pytest.approx(
        end_minus_start(stocks=stocks, times=times), rel=1e-12
    )
    assert trend["fitted_slope"].value == pytest.approx(
        fitted_slope(stocks=stocks, times=times), rel=1e-12
    )
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


# --- G1 / G3 / G4 / G5 & monthly requirement checks --------------------------


def test_wrong_types_raise_type_error():
    good = forcing()
    for bad in (None, {}, forcing_data(), good.model_dump(mode="json"), "forcing"):
        with pytest.raises(TypeError, match="forcing"):
            run_amg_monthly(bad, parameters={})
    for bad in (None, [], "parameters", {"key": "not a record"}, {1: {}}):
        with pytest.raises(TypeError, match="parameters"):
            run_amg_monthly(good, parameters=bad)


def test_requires_monthly_climate_and_carbon_inputs_ignoring_annual_series():
    parameters = catalogue()
    # Annual series present, but monthly climate absent -> must not fall back to annual.
    data = annual_forcing_data()
    balance = run_amg_monthly(forcing(data), parameters=parameters)
    step0 = balance.total_stock.steps[0]
    assert step0.value is None
    assert step0.missing.reason == "MISSING_INPUT"
    assert "carbon_inputs is empty" in step0.missing.detail
    assert "reason NOT_COMPUTABLE" in step0.missing.detail
    assert "quantity 'mean_temperature' has no item in climate" in step0.missing.detail
    assert "quantity 'water_balance' has no item in climate" in step0.missing.detail

    # Monthly climate present, monthly carbon_inputs empty (annual_carbon_inputs populated).
    monthly_with_annual_inputs = forcing_data()
    monthly_with_annual_inputs["carbon_inputs"] = []
    monthly_with_annual_inputs["annual_carbon_inputs"] = annual_forcing_data()[
        "annual_carbon_inputs"
    ]
    bal_no_inputs = run_amg_monthly(
        forcing(monthly_with_annual_inputs), parameters=parameters
    )
    assert bal_no_inputs.total_stock.initial.value is not None
    step0_ni = bal_no_inputs.total_stock.steps[0]
    assert step0_ni.value is None
    assert step0_ni.missing.reason == "MISSING_INPUT"
    assert "carbon_inputs is empty" in step0_ni.missing.detail
    assert "reason NOT_COMPUTABLE" in step0_ni.missing.detail


@pytest.mark.parametrize("name", sorted(PARAMETERS))
def test_each_parameter_without_a_record_is_named(name):
    balance = run_amg_monthly(forcing(), parameters=catalogue_with(name, None))
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
    balance = run_amg_monthly(forcing(), parameters=parameters)
    detail = balance.total_stock.steps[0].missing.detail
    assert balance.total_stock.steps[0].missing.reason == "MISSING_INPUT"
    assert "amg_potential_mineralisation_rate" in detail
    assert (
        f"the record holds no value: {UNMARKED}: nobody has given this value" in detail
    )
    assert balance.total_stock.initial.value is not None


def test_a_placeholder_record_is_not_read():
    records = catalogue()
    key = "records/stable_fraction.json"
    records[key] = marked_catalogue()[key]
    balance = run_amg_monthly(forcing(), parameters=records)
    assert "amg_stable_fraction" in balance.total_stock.initial.missing.detail
    assert "the record is not read" in balance.total_stock.initial.missing.detail


def test_malformed_and_duplicate_records_are_named():
    malformed = catalogue()
    malformed["records/bad.json"] = {"value": 1.0}
    bal = run_amg_monthly(forcing(), parameters=malformed)
    assert bal.total_stock.initial.value is None
    assert bal.total_stock.initial.missing.reason == "MISSING_INPUT"
    assert "'records/bad.json'" in bal.total_stock.initial.missing.detail
    assert "F3c" in bal.total_stock.initial.missing.detail

    dup = catalogue()
    dup["records/stable_fraction_dup.json"] = copy.deepcopy(
        dup["records/stable_fraction.json"]
    )
    bal_dup = run_amg_monthly(forcing(), parameters=dup)
    assert bal_dup.total_stock.initial.value is None
    assert (
        "two records share this id and scope"
        in bal_dup.total_stock.initial.missing.detail
    )


def test_a_unit_of_a_record_that_is_not_accepted_is_not_computed():
    balance = run_amg_monthly(
        forcing(),
        parameters=catalogue_with("stable_fraction", {"unit": unmark(CONTENT)}),
    )
    detail = balance.total_stock.initial.missing.detail
    assert "reason NOT_COMPUTABLE" in detail
    assert "'dimensionless' (C1.1)" in detail

    balance = run_amg_monthly(
        forcing(),
        parameters=catalogue_with("clay_sensitivity", {"unit": unmark(CONTENT)}),
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "amg_clay_sensitivity" in detail and "written 'X-1'" in detail

    balance = run_amg_monthly(
        forcing(),
        parameters=catalogue_with("clay_sensitivity", {"unit": "-1"}),
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "reason NOT_COMPUTABLE" in detail and "written 'X-1'" in detail

    balance = run_amg_monthly(
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
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    detail = balance.soil_carbon_trend[0].missing.detail
    assert f"quantity '{quantity}' has no item in {part} of the forcing" in detail


def test_a_missing_climate_month_makes_that_step_and_every_later_step_missing():
    data = forcing_data()
    months = _horizon_months()
    temps = [99.9] * len(months)
    temps[5] = None
    data["climate"][0] = monthly_series(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), temps
    )
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [s.value is None for s in steps[:7]] == [
        False,
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    assert steps[5].missing.reason == "MISSING_INPUT"
    assert "reason NO_COVERAGE" in steps[5].missing.detail
    assert "step 5 is missing" in steps[6].missing.detail
    assert all(s.value is None for s in steps[5:])
    assert all(item.value is None for item in balance.soil_carbon_trend)
    assert all(item.source is None for item in balance.soil_carbon_trend)
    assert balance.total_stock.provenance == "SIMULATED"


def test_a_missing_carbon_input_month_makes_that_step_and_every_later_step_missing():
    data = forcing_data()
    months = _horizon_months()
    vals = [0.1] * len(months)
    vals[3] = None
    data["carbon_inputs"][0] = monthly_series(
        "placeholder_input_a", STOCK_UNIT, vals, origin=ORIGINS[0]
    )
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [s.value is None for s in steps[:5]] == [False, False, False, True, True]
    assert steps[3].missing.reason == "MISSING_INPUT"
    assert "reason NO_COVERAGE" in steps[3].missing.detail
    assert "step 3 is missing" in steps[4].missing.detail


def test_unit_checks_and_missing_unit_preservation():
    parameters = catalogue()
    # Wrong unit on starting_state
    data = forcing_data()
    data["starting_state"][0]["unit"] = unmark(CONTENT)
    bal = run_amg_monthly(forcing(data), parameters=parameters)
    assert "reason NOT_COMPUTABLE" in bal.total_stock.initial.missing.detail
    assert "converts nothing" in bal.total_stock.initial.missing.detail

    # Wrong unit on carbon_inputs
    data = forcing_data()
    data["carbon_inputs"][1]["unit"] = unmark(CONTENT)
    bal = run_amg_monthly(forcing(data), parameters=parameters)
    detail = bal.flows[0].steps[0].missing.detail
    assert "placeholder_input_b" in detail and "converts nothing" in detail

    # Wrong unit on ph and soil_cn_ratio
    for idx, qty in ((2, "ph"), (3, "soil_cn_ratio")):
        data = forcing_data()
        data["soil_properties"][idx]["unit"] = unmark(CONTENT)
        bal = run_amg_monthly(forcing(data), parameters=parameters)
        step0 = bal.total_stock.steps[0]
        assert step0.value is None
        assert f"soil property '{qty}' is in" in step0.missing.detail
        assert "reason NOT_COMPUTABLE" in step0.missing.detail

    # Missing ph / soil_cn_ratio with non-dimensionless unit preserves MISSING_INPUT reason
    for idx, qty in ((2, "ph"), (3, "soil_cn_ratio")):
        data = forcing_data()
        data["soil_properties"][idx] = {
            "quantity": qty,
            "value": None,
            "unit": "OPEN",
            "missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: missing"},
        }
        bal = run_amg_monthly(forcing(data), parameters=parameters)
        step0 = bal.total_stock.steps[0]
        assert step0.value is None
        assert "reason NOT_AVAILABLE" in step0.missing.detail
        assert "dimensionless" not in step0.missing.detail


def test_two_inputs_of_one_origin_take_the_coefficient_of_that_origin():
    data = forcing_data()
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    expected = math.fsum(
        series["months"][0]["value"] * HUMIFICATION[series["origin"]]
        for series in data["carbon_inputs"]
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
                    {ORIGIN_SCOPE_KEY: ORIGINS[1]},
                )
            }
        )
    )
    detail = (
        run_amg_monthly(forcing(data), parameters=parameters)
        .flows[0]
        .steps[0]
        .missing.detail
    )
    assert f'"{ORIGIN_SCOPE_KEY}": "{ORIGINS[0]}"' in detail


def test_the_balance_names_the_forcing_and_the_variant():
    data = forcing_data()
    balance = run_amg_monthly(forcing(data), parameters=catalogue())
    assert isinstance(balance, CarbonBalance)
    assert (balance.case_id, balance.field_id, balance.rotation_id) == (
        data["case_id"],
        data["field_id"],
        data["rotation_id"],
    )
    assert balance.carbon_model == "amg" and balance.variant == VARIANT == "amg_m"
    assert balance.example_data is True
    assert balance.horizon == forcing(data).horizon
    assert balance.soil_depth == forcing(data).soil_depth
    assert balance.total_stock.unit == STOCK_UNIT
    assert balance.total_stock.initial.provenance == "DERIVED"
    assert balance.total_stock.provenance == "SIMULATED"
    assert [s.quantity for s in balance.pools] == ["amg_active_pool", "amg_stable_pool"]
    assert [s.quantity for s in balance.flows] == [
        "amg_humified_input",
        "amg_mineralised_carbon",
    ]
    for step in balance.total_stock.steps:
        assert step.start == step.end
    reloaded = CarbonBalance.model_validate(balance.model_dump(mode="json"))
    assert reloaded == balance


def test_run_amg_monthly_is_pure_and_signature():
    parameters_sig = inspect.signature(run_amg_monthly).parameters
    assert list(parameters_sig) == ["forcing", "parameters"]
    assert parameters_sig["forcing"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters_sig["parameters"].kind is inspect.Parameter.KEYWORD_ONLY
    assert all(p.default is inspect.Parameter.empty for p in parameters_sig.values())

    data = forcing_data()
    given = forcing(data)
    before = given.model_dump(mode="json")
    parameters = catalogue()
    kept = copy.deepcopy(parameters)
    first = run_amg_monthly(given, parameters=parameters)
    second = run_amg_monthly(given, parameters=parameters)
    assert first == second
    assert given.model_dump(mode="json") == before
    assert parameters == kept


def test_monthly_entry_holds_no_value_of_the_method():
    """No number but zero and one in monthly_entry.py, matching test_amg.py."""
    tree = ast.parse((HERE / "monthly_entry.py").read_text(encoding="utf-8"))
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, numbers


def test_every_number_carries_the_method_label_first_and_missing_carries_no_source():
    parameters = catalogue()
    assert check_catalogue(parameters) == []
    balance = run_amg_monthly(forcing(forcing_data()), parameters=parameters)
    parts = carriers(balance)
    assert len(parts) == len(POOL_QUANTITIES) * 2 + 2 + len(TREND_COMPUTATIONS)
    assert [where for where, _, holds in parts if not holds] == [
        "trend mean_over_cycles"
    ]
    opening = f"{METHOD_LABEL}; "
    rest = {}
    for where, part, holds in parts:
        if holds:
            assert part.source.startswith(opening), where
            assert part.source.count(METHOD_LABEL) == 1, where
            rest[where] = part.source[len(opening) :]
    total = POOL_QUANTITIES["total"]
    assert rest[f"{total}.initial"].startswith(
        "derived by engine.amg.monthly_entry.run_amg_monthly "
    )
    assert rest[total].startswith(
        "simulated by engine.amg.monthly_entry.run_amg_monthly, variant 'amg_m'"
    )
    for name in ("end_minus_start", "fitted_slope"):
        assert rest[f"trend {name}"] == (
            f"{rest[total]}; computation '{name}' of engine/amg/trend.py"
        )
    for word in ("transferred", "La Estanzuela", "Uruguay", "clay", "C:N"):
        assert word.lower() not in METHOD_LABEL.lower(), word

    # Missing values carry no source and no label.
    missing_balance = run_amg_monthly(example_forcing(), parameters={})
    for where, part, holds in carriers(missing_balance):
        assert not holds, where
        assert part.source is None, where
    dumped = json.dumps(missing_balance.model_dump(mode="json"), ensure_ascii=False)
    assert METHOD_LABEL not in dumped
    assert entry.METHOD_LABEL not in dumped

    # Example forcing file was not modified.
    assert json.loads(FORCING_EXAMPLE.read_text(encoding="utf-8"))["contract"] == (
        "carbon_forcing"
    )
    assert monthly_entry.VARIANT == "amg_m"
