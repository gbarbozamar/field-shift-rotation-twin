"""Acceptance test of EP6 ``run_rothc`` (unit l2/rothc-common-forcings, issue #176).

Every number here is a PLACEHOLDER: plainly unreal values with repeated
digits (rate constants of 0.22 and 0.44, stocks near 99, clay of 999.9),
chosen only so that the forms of the core give finite numbers. None is a
value of the method, and no expected value of the science is written: each
computed number is compared with the core functions called a second time on
the same inputs, or with the mass balance. The person-transcribed values of
the reference case live in ``test_reference_case.py``.

The word PLACEHOLDER marks every record and source string that would
otherwise look real. ``read_value`` refuses such a record and
``check_catalogue`` rejects it, so a test passes the in-memory copy in which
the word is replaced by ``UNMARKED_TEST_ONLY``, as ``engine/amg/test_entry.py``
does. Nothing without the word is written to a file.

Run from the repository root: ``python -m pytest engine/rothc/``.
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
from engine.rothc import entry
from engine.rothc.entry import (
    FORCING_QUANTITIES,
    INPUT_PARAMETERS,
    PARAMETERS,
    STOCK_UNIT,
    VARIANT,
    run_rothc,
)
from engine.rothc.modifiers import (
    advance_deficit,
    clay_partition,
    cover_modifier,
    maximum_tsmd,
    moisture_modifier,
    rate_modifying_factor,
    temperature_modifier,
)
from engine.rothc.pools import (
    InputSplit,
    MonthInput,
    initial_state,
    input_additions,
    plant_fractions,
    run,
)
from engine.rothc.trend import end_minus_start, fitted_slope
from params.catalogue import check_catalogue

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
FORCING_EXAMPLE = ROOT / "contracts" / "carbon_forcing" / "examples" / "PLACEHOLDER_carbon_forcing.json"  # fmt: skip
README = HERE / "README.md"
MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
YEARS = (2001, 2002)  # PLACEHOLDER calendar years of the horizon
ORIGINS = ("test_origin_a", "test_origin_b")  # scope words: no mark, so they pass
DEGREE = f"{MARK}_degree"

# PLACEHOLDER numbers, one per row of entry.PARAMETERS (and the input
# compositions below); the unit of each record follows entry.PARAMETERS.
VALUES: dict[str, tuple[float, str]] = {
    "dpm_rate_constant": (0.22, "yr-1"),
    "rpm_rate_constant": (0.044, "yr-1"),
    "bio_rate_constant": (0.066, "yr-1"),
    "hum_rate_constant": (0.022, "yr-1"),
    "temperature_maximum": (44.4, "dimensionless"),
    "temperature_exponent_scale": (99.9, DEGREE),
    "temperature_offset": (22.2, DEGREE),
    "tsmd_intercept": (66.6, "mm"),
    "tsmd_clay_coefficient": (1.33, "mm %-1"),
    "tsmd_clay_squared_coefficient": (0.011, "mm %-2"),
    "tsmd_reference_depth": (55.5, "cm"),
    "moisture_threshold": (0.44, "dimensionless"),
    "moisture_minimum": (0.22, "dimensionless"),
    "pan_factor": (0.77, "dimensionless"),
    "cover_vegetated": (0.66, "dimensionless"),
    "cover_bare": (1.0, "dimensionless"),
    "partition_scale": (1.11, "dimensionless"),
    "partition_intercept": (2.22, "dimensionless"),
    "partition_clay_coefficient": (3.33, "dimensionless"),
    "partition_clay_decay": (0.44, "%-1"),
    "bio_share": (0.44, "dimensionless"),
    "iom_coefficient": (0.044, "dimensionless"),
    "iom_exponent": (1.11, "dimensionless"),
}
# The composition of each origin: the first by its DPM:RPM ratio (plant
# material), the second by its three shares (an organic amendment).
RATIO = {ORIGINS[0]: 1.55}
AMENDMENT = {ORIGINS[1]: (0.44, 0.44, 0.12)}


def unmark(item: Any) -> Any:
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {unmark(key): unmark(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmark(value) for value in item]
    return item


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
    for origin, ratio in RATIO.items():
        records[f"records/ratio_{origin}.json"] = record(
            INPUT_PARAMETERS["input_dpm_rpm_ratio"], ratio, "dimensionless",
            {entry.ORIGIN_SCOPE_KEY: origin},
        )
    for origin, (dpm, rpm, hum) in AMENDMENT.items():
        for name, share in (
            ("input_dpm_fraction", dpm),
            ("input_rpm_fraction", rpm),
            ("input_hum_fraction", hum),
        ):
            records[f"records/{name}_{origin}.json"] = record(
                INPUT_PARAMETERS[name], share, "dimensionless",
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


def series_header(quantity: str, unit: str, **extra) -> dict:
    return {
        "quantity": quantity,
        "unit": unit,
        "provenance": "DERIVED",
        "source": f"{MARK}: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: no range"},
        **extra,
    }


def months_of(first_year: int, count: int, quantity: str, unit: str, values, **extra) -> dict:  # fmt: skip
    items = []
    index = 0
    for _ in range(count):
        year = first_year + index // 12
        month = index % 12 + 1
        value = values[index] if index < len(values) else values[-1]
        item: dict = {"year": year, "month": month}
        if isinstance(value, dict):  # a missing month with its reason
            item.update(value)
        else:
            item["value"] = value
        items.append(item)
        index += 1
    start, end = items[0], items[-1]
    return {
        **series_header(quantity, unit),
        **extra,
        "start": {"year": start["year"], "month": start["month"]},
        "end": {"year": end["year"], "month": end["month"]},
        "months": items,
    }


def soil(quantity: str, value, unit: str) -> dict:
    """One soil property or starting value: present with its header, or missing."""
    if isinstance(value, dict):  # a missing value with its reason
        return {"quantity": quantity, "unit": unit, "value": None, **value}
    return {**series_header(quantity, unit), "value": value}


def a_value(value: float, unit: str) -> dict:
    """One plain ``Value`` (the soil depth of the forcing)."""
    return {
        "value": value,
        "unit": unit,
        "provenance": "DECLARED",
        "source": f"{MARK}: example data, no real source",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: no range"},
    }


CLIMATE_MONTHS = 24  # two PLACEHOLDER calendar years


def forcing_data() -> dict:
    """The example forcing over two calendar years, with what run_rothc reads."""
    data = json.loads(FORCING_EXAMPLE.read_text(encoding="utf-8"))
    data["horizon"] = {
        "start": {"year": YEARS[0], "month": 1},
        "end": {"year": YEARS[1], "month": 12},
    }
    quantity = {name: q for name, (_, q) in FORCING_QUANTITIES.items()}
    data["climate"] = [
        months_of(YEARS[0], CLIMATE_MONTHS, quantity["rainfall"], "mm",
                  [22.2 + i // 2 for i in range(CLIMATE_MONTHS)]),
        months_of(YEARS[0], CLIMATE_MONTHS, quantity["pan_evaporation"], "mm",
                  [44.4 + i // 3 for i in range(CLIMATE_MONTHS)]),
        months_of(YEARS[0], CLIMATE_MONTHS, quantity["temperature"], unmark(DEGREE),
                  [11.1 + i // 4 for i in range(CLIMATE_MONTHS)]),
    ]
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []
    data["soil_cover"] = [
        months_of(YEARS[0], CLIMATE_MONTHS, quantity["soil_cover"], "dimensionless",
                  [float(i % 2) for i in range(CLIMATE_MONTHS)]),
    ]
    data["carbon_inputs"] = [
        months_of(YEARS[0], CLIMATE_MONTHS, "placeholder_input_a", STOCK_UNIT,
                  [float(i % 3) for i in range(CLIMATE_MONTHS)],
                  origin=ORIGINS[0]),
        months_of(YEARS[0], CLIMATE_MONTHS, "placeholder_input_b", STOCK_UNIT,
                  [0.0] * CLIMATE_MONTHS,
                  origin=ORIGINS[1]),
    ]
    data["soil_properties"] = [
        soil(quantity["clay_content"], 99.9, "%"),
    ]
    data["soil_depth"] = a_value(55.5, "cm")
    data["starting_state"] = [
        {**soil(quantity[name], 9.99 * (position + 1), STOCK_UNIT), "provenance": "DECLARED"}
        for position, name in enumerate(
            ("dpm_pool", "rpm_pool", "bio_pool", "hum_pool", "iom_pool")
        )
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


def composition_of(origin: str) -> InputSplit:
    if origin in RATIO:
        return plant_fractions(dpm_rpm_ratio=RATIO[origin])
    dpm, rpm, hum = AMENDMENT[origin]
    return InputSplit(dpm=dpm, rpm=rpm, bio=0.0, hum=hum)


def core_run(data: dict, parameters: dict[str, float]) -> dict:
    """The inputs the core needs, built a second time from the forcing data by hand."""
    q = {name: q for name, (_, q) in FORCING_QUANTITIES.items()}
    clay = next(p["value"] for p in data["soil_properties"] if p["quantity"] == q["clay_content"])  # fmt: skip
    partition = clay_partition(
        clay_content=clay,
        clay_content_unit="%",
        scale=parameters["partition_scale"],
        intercept=parameters["partition_intercept"],
        clay_coefficient=parameters["partition_clay_coefficient"],
        clay_decay=parameters["partition_clay_decay"],
        clay_decay_unit="%",
    )
    maximum = maximum_tsmd(
        clay_content=clay,
        clay_content_unit="%",
        depth=data["soil_depth"]["value"],
        depth_unit=data["soil_depth"]["unit"],
        intercept=parameters["tsmd_intercept"],
        intercept_unit="mm",
        clay_coefficient=parameters["tsmd_clay_coefficient"],
        clay_coefficient_unit="mm %-1",
        clay_squared_coefficient=parameters["tsmd_clay_squared_coefficient"],
        clay_squared_coefficient_unit="mm %-2",
        reference_depth=parameters["tsmd_reference_depth"],
        reference_depth_unit="cm",
    )
    series = {s["quantity"]: s for s in data["climate"] + data["soil_cover"]}
    cover = series[q["soil_cover"]]
    temperature = series[q["temperature"]]
    rainfall = series[q["rainfall"]]
    pan = series[q["pan_evaporation"]]
    inputs = {s["quantity"]: s for s in data["carbon_inputs"]}
    state = initial_state(
        **{
            pool: next(
                item["value"]
                for item in data["starting_state"]
                if item["quantity"] == q[f"{pool}_pool"]
            )
            for pool in ("dpm", "rpm", "bio", "hum", "iom")
        }
    )
    deficit: float | object = 0.0
    months = []
    for position in range(CLIMATE_MONTHS):
        a = temperature_modifier(
            temperature=temperature["months"][position]["value"],
            temperature_unit=unmark(DEGREE),
            maximum=parameters["temperature_maximum"],
            exponent_scale=parameters["temperature_exponent_scale"],
            exponent_scale_unit=unmark(DEGREE),
            offset=parameters["temperature_offset"],
            offset_unit=unmark(DEGREE),
        )
        deficit = advance_deficit(
            deficit=deficit,
            maximum=maximum,
            maximum_unit="mm",
            rainfall=rainfall["months"][position]["value"],
            rainfall_unit="mm",
            pan_evaporation=pan["months"][position]["value"],
            pan_evaporation_unit="mm",
            pan_factor=parameters["pan_factor"],
        )
        b = moisture_modifier(
            deficit=deficit,
            maximum=maximum,
            threshold_fraction=parameters["moisture_threshold"],
            minimum=parameters["moisture_minimum"],
        )
        c = cover_modifier(
            cover_state=cover["months"][position]["value"],
            vegetated_factor=parameters["cover_vegetated"],
            bare_factor=parameters["cover_bare"],
        )
        months.append(
            MonthInput(
                additions=input_additions(
                    carbon_inputs={
                        quantity: inputs[quantity]["months"][position]["value"]
                        for quantity in inputs
                    },
                    compositions={
                        quantity: composition_of(inputs[quantity]["origin"])
                        for quantity in inputs
                    },
                ),
                rate_modifying_factor=rate_modifying_factor(
                    temperature_factor=a,
                    moisture_factor=b,
                    cover_factor=c,
                ),
            )
        )
    return {"state": state, "months": months, "partition": partition}


PLACEHOLDER_NUMBERS = {name: value for name, (value, _) in VALUES.items()}


# --- the acceptance cases of the brief ------------------------------------------------


def test_example_forcing_and_empty_catalogue_give_every_value_missing_naming_parameters():
    balance = run_rothc(example_forcing(), parameters={})
    CarbonBalance.model_validate(balance.model_dump(mode="json"))
    values = every_value(balance)
    assert values
    for where, item in values:
        assert item.value is None, where
        assert item.missing.reason == "MISSING_INPUT", where
        # The example forcing carries none of the five pools, so the initial
        # state is what stops the run and every value names the quantities it
        # lacks; with pools given, the steps name the parameters instead (the
        # case below removes each parameter alone).
        assert "has no item in" in item.missing.detail, where


def test_placeholder_catalogue_passes_check_catalogue_and_stocks_are_computed_by_the_core():
    parameters = catalogue()
    assert check_catalogue(parameters) == []
    assert check_catalogue(marked_catalogue()) != []  # the marked records are refused
    data = forcing_data()
    balance = run_rothc(forcing(data), parameters=parameters)
    assert all(item.value is not None for _, item in every_value(balance)[:-1])
    expected = core_run(data, PLACEHOLDER_NUMBERS)
    the_run = run(
        initial_state=expected["state"],
        months=expected["months"],
        rate_constants={
            pool: PLACEHOLDER_NUMBERS[f"{pool}_rate_constant"]
            for pool in ("dpm", "rpm", "bio", "hum")
        },
        partition_ratio=expected["partition"],
        bio_share=PLACEHOLDER_NUMBERS["bio_share"],
    )
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    assert stocks == list(the_run.total_stocks())
    pools = {series.quantity: series for series in balance.pools}
    for pool, name in (
        ("dpm", "rothc_dpm_pool"),
        ("rpm", "rothc_rpm_pool"),
        ("bio", "rothc_bio_pool"),
        ("hum", "rothc_hum_pool"),
        ("iom", "rothc_iom_pool"),
    ):
        assert pools[name].initial.value == getattr(the_run.initial_state, pool)
        for position, item in enumerate(the_run.steps):
            assert pools[name].steps[position].value == getattr(item.end, pool)


def test_mass_balance_holds_at_every_month():
    balance = run_rothc(forcing(), parameters=catalogue())
    total = balance.total_stock
    pools = {series.quantity: series for series in balance.pools}
    carbon_input, co2 = balance.flows
    stocks = [total.initial.value] + [s.value for s in total.steps]
    tolerance = 1e-9 * max(abs(stock) for stock in stocks)
    for position in range(len(total.steps)):
        change = stocks[position + 1] - stocks[position]
        assert math.isclose(
            change,
            carbon_input.steps[position].value - co2.steps[position].value,
            rel_tol=1e-12,
            abs_tol=tolerance,
        )
        assert co2.steps[position].value >= 0
        assert carbon_input.steps[position].value >= 0
        assert math.isclose(
            total.steps[position].value,
            math.fsum(
                pools[name].steps[position].value
                for name in (
                    "rothc_dpm_pool",
                    "rothc_rpm_pool",
                    "rothc_bio_pool",
                    "rothc_hum_pool",
                    "rothc_iom_pool",
                )
            ),
            rel_tol=1e-12,
        )
    whole = stocks[-1] - stocks[0]
    assert math.isclose(
        whole,
        math.fsum(s.value for s in carbon_input.steps)
        - math.fsum(s.value for s in co2.steps),
        rel_tol=1e-12,
        abs_tol=tolerance,
    )


def test_pools_never_negative_over_a_long_horizon():
    balance = run_rothc(forcing(), parameters=catalogue())
    for series in [balance.total_stock, *balance.pools]:
        for item in [series.initial, *series.steps]:
            if item.value is not None:
                assert item.value >= 0


def test_trend_values_are_per_model_and_mean_over_cycles_waits_for_its_input():
    balance = run_rothc(forcing(), parameters=catalogue())
    stocks = [balance.total_stock.initial.value] + [
        s.value for s in balance.total_stock.steps
    ]
    times = [float(i) / 12 for i in range(len(stocks))]
    trend = {item.computation: item for item in balance.soil_carbon_trend}
    assert [item.computation for item in balance.soil_carbon_trend] == list(
        TREND_COMPUTATIONS
    )
    assert trend["end_minus_start"].value == pytest.approx(
        end_minus_start(stocks=stocks, times=times)
    )
    assert trend["fitted_slope"].value == pytest.approx(
        fitted_slope(stocks=stocks, times=times)
    )
    for name in ("end_minus_start", "fitted_slope"):
        assert trend[name].unit == UNIT_SOIL_CARBON_TREND
        assert trend[name].provenance == "SIMULATED"
        assert trend[name].carbon_model == "rothc"
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
            run_rothc(bad, parameters={})
    for bad in (None, [], "parameters", {"key": "not a record"}, {1: {}}):
        with pytest.raises(TypeError, match="parameters"):
            run_rothc(good, parameters=bad)


def test_the_runner_finds_run_rothc_by_its_module_path_and_name():
    """contracts/ENTRYPOINTS.md EP6: module ``engine.rothc``, function ``run_rothc``.

    The runner of api/engines.py imports each engine with
    ``importlib.import_module(module)`` and ``getattr(module, function)``; this
    is that lookup. Whether the runner lists EP6 among the entries it imports
    is the platform developer's (README.md, OPEN).
    """
    module = importlib.import_module("engine.rothc")
    assert getattr(module, "run_rothc") is run_rothc
    assert callable(run_rothc)


# --- what is missing, and why -------------------------------------------------------------


def test_a_month_without_cover_data_makes_that_month_and_every_later_month_missing():
    data = forcing_data()
    month = data["soil_cover"][0]["months"][13]
    data["soil_cover"][0]["months"][13] = {
        "year": month["year"],
        "month": month["month"],
        "value": None,
        "missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: no cover given"},
    }
    balance = run_rothc(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [s.value is None for s in steps] == [
        False,
    ] * 13 + [True] * (len(steps) - 13)
    assert steps[13].missing.reason == "MISSING_INPUT"
    assert "reason NOT_DECLARED" in steps[13].missing.detail
    assert "cover" in steps[13].missing.detail
    assert "month 13" in steps[14].missing.detail
    assert all(item.value is None for item in balance.soil_carbon_trend)


def test_a_soil_property_not_declared_is_named():
    data = forcing_data()
    quantity = FORCING_QUANTITIES["clay_content"][1]
    data["soil_properties"] = [
        item
        for item in data["soil_properties"]
        if item["quantity"] != quantity
    ]
    data["soil_properties"].append(
        soil(
            quantity,
            {"missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: nobody gave it"}},
            "%",
        )
    )
    balance = run_rothc(forcing(data), parameters=catalogue())
    step = balance.total_stock.steps[0]
    assert step.value is None
    assert step.missing.reason == "MISSING_INPUT"
    assert "reason NOT_DECLARED" in step.missing.detail
    assert "clay_content" in step.missing.detail


def test_carbon_inputs_not_available_are_named_with_their_reason():
    data = forcing_data()
    not_available = {"missing": {"reason": "NOT_AVAILABLE", "detail": f"{MARK}: EP4"}}
    for series in data["carbon_inputs"]:
        month = series["months"][10]
        month["value"] = None
        month.update(not_available)
    balance = run_rothc(forcing(data), parameters=catalogue())
    steps = balance.total_stock.steps
    assert [s.value is None for s in steps][:12] == [False] * 10 + [True, True]
    assert "reason NOT_AVAILABLE" in steps[10].missing.detail
    assert "month 10" in steps[11].missing.detail


def test_carbon_inputs_left_out_entirely_are_never_zero():
    data = forcing_data()
    data["carbon_inputs"] = []
    balance = run_rothc(forcing(data), parameters=catalogue())
    step = balance.total_stock.steps[0]
    assert step.value is None
    # The step is MISSING_INPUT naming its additions, whose own reason is
    # NOT_COMPUTABLE: no month is ever written as zero.
    assert step.missing.reason == "MISSING_INPUT"
    assert "carbon_inputs is empty" in step.missing.detail
    assert "reason NOT_COMPUTABLE" in step.missing.detail


def test_starting_state_feeds_the_pools_it_names():
    data = forcing_data()
    balance = run_rothc(forcing(data), parameters=catalogue())
    pools = {series.quantity: series for series in balance.pools}
    starting = {item["quantity"]: item["value"] for item in data["starting_state"]}
    for name, quantity in (
        ("dpm", "rothc_dpm_pool"),
        ("rpm", "rothc_rpm_pool"),
        ("bio", "rothc_bio_pool"),
        ("hum", "rothc_hum_pool"),
        ("iom", "rothc_iom_pool"),
    ):
        assert pools[quantity].initial.value == starting[quantity]
    assert balance.total_stock.initial.value == pytest.approx(
        math.fsum(starting.values())
    )
    # A pool the starting state does not name stays missing with its reason.
    data = forcing_data()
    named = FORCING_QUANTITIES["hum_pool"][1]
    data["starting_state"] = [
        item for item in data["starting_state"] if item["quantity"] != named
    ]
    balance = run_rothc(forcing(data), parameters=catalogue())
    pools = {series.quantity: series for series in balance.pools}
    assert pools[named].initial.value is None
    assert pools[named].initial.missing.reason == "MISSING_INPUT"
    assert named in pools[named].initial.missing.detail
    assert balance.total_stock.steps[0].value is None


def test_starting_iom_derived_from_the_total_when_not_given():
    data = forcing_data()
    named = FORCING_QUANTITIES["iom_pool"][1]
    total = FORCING_QUANTITIES["total_carbon"][1]
    data["starting_state"] = [
        item for item in data["starting_state"] if item["quantity"] != named
    ]
    data["starting_state"].append(
        {**soil(total, 99.9, STOCK_UNIT), "provenance": "DECLARED"}
    )
    balance = run_rothc(forcing(data), parameters=catalogue())
    pools = {series.quantity: series for series in balance.pools}
    assert pools[named].initial.value == pytest.approx(
        PLACEHOLDER_NUMBERS["iom_coefficient"]
        * 99.9 ** PLACEHOLDER_NUMBERS["iom_exponent"]
    )
    assert pools[named].initial.provenance == "DERIVED"
    # Without both, each is named.
    data["starting_state"] = [
        item for item in data["starting_state"] if item["quantity"] != total
    ]
    balance = run_rothc(forcing(data), parameters=catalogue())
    detail = balance.total_stock.initial.missing.detail
    assert "the inert pool in starting_state" in detail
    assert "soil_organic_carbon" in detail


@pytest.mark.parametrize("name", sorted(PARAMETERS))
def test_each_parameter_without_a_record_is_named(name):
    data = forcing_data()
    if name in ("iom_coefficient", "iom_exponent"):
        # These two are read only when the inert pool is derived from the total.
        data["starting_state"] = [
            item
            for item in data["starting_state"]
            if item["quantity"] != FORCING_QUANTITIES["iom_pool"][1]
        ]
        data["starting_state"].append(
            {
                **series_header(
                    FORCING_QUANTITIES["total_carbon"][1], STOCK_UNIT
                ),
                "value": 99.9,
                "provenance": "DECLARED",
            }
        )
    balance = run_rothc(forcing(data), parameters=catalogue_with(name, None))
    parameter_id = PARAMETERS[name][0]
    trend = {item.computation: item for item in balance.soil_carbon_trend}
    assert trend["end_minus_start"].value is None
    assert parameter_id in trend["end_minus_start"].missing.detail
    assert "no record in parameters (D56)" in trend["end_minus_start"].missing.detail
    assert balance.total_stock.steps[-1].value is None


def test_a_record_without_a_value_is_named_with_its_reason():
    parameters = catalogue_with(
        "bio_share",
        {"value": None, "value_missing_reason": f"{MARK}: nobody has given this value"},
    )
    balance = run_rothc(forcing(), parameters=parameters)
    detail = balance.total_stock.steps[0].missing.detail
    assert balance.total_stock.steps[0].missing.reason == "MISSING_INPUT"
    assert "rothc_bio_share_of_formed" in detail
    assert (
        f"the record holds no value: {UNMARKED}: nobody has given this value" in detail
    )
    assert balance.total_stock.initial.value is not None  # needs no bio share


def test_a_unit_of_a_record_that_is_not_accepted_is_not_computed():
    balance = run_rothc(
        forcing(),
        parameters=catalogue_with("bio_share", {"unit": "PLACEHOLDER_other"}),
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "reason NOT_COMPUTABLE" in detail
    assert "'dimensionless' (C1.1)" in detail
    balance = run_rothc(
        forcing(),
        parameters=catalogue_with(
            "dpm_rate_constant", {"unit": "PLACEHOLDER_other-1"}
        ),
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "reason NOT_COMPUTABLE" in detail and "must be per 'yr'" in detail
    balance = run_rothc(
        forcing(),
        parameters=catalogue_with("partition_clay_decay", {"unit": "PLACEHOLDER_other"}),  # fmt: skip
    )
    detail = balance.total_stock.steps[0].missing.detail
    assert "reason NOT_COMPUTABLE" in detail and "'X-1'" in detail


@pytest.mark.parametrize(
    "name", sorted(set(FORCING_QUANTITIES) - {"potential_evapotranspiration"})
)
def test_each_quantity_the_forcing_lacks_is_named(name):
    part, quantity = FORCING_QUANTITIES[name]
    data = forcing_data()
    data[part] = [item for item in data[part] if item["quantity"] != quantity]
    if name == "total_carbon":  # the inert pool is given: the total is not needed
        data["starting_state"] = [
            item for item in data["starting_state"]
            if item["quantity"] != FORCING_QUANTITIES["iom_pool"][1]
        ]
    balance = run_rothc(forcing(data), parameters=catalogue())
    detail = balance.soil_carbon_trend[0].missing.detail
    assert f"quantity '{quantity}' has no item in {part} of the forcing" in detail


def test_a_quantity_in_a_unit_the_engine_does_not_accept_is_not_computed():
    data = forcing_data()
    data["climate"][0]["unit"] = "PLACEHOLDER_other"  # rainfall
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "PLACEHOLDER_other" in balance.total_stock.steps[0].missing.detail
    data = forcing_data()
    data["soil_properties"][0]["unit"] = "PLACEHOLDER_other"  # clay content
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "clay_coefficient_unit" in balance.total_stock.steps[0].missing.detail
    data = forcing_data()
    data["soil_depth"]["unit"] = "PLACEHOLDER_other"
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "depth_unit" in balance.total_stock.steps[0].missing.detail
    data = forcing_data()
    data["soil_cover"][0]["unit"] = "PLACEHOLDER_other"
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "dimensionless" in balance.total_stock.steps[0].missing.detail
    data = forcing_data()
    data["starting_state"][0]["unit"] = "PLACEHOLDER_other"
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "converts nothing" in balance.total_stock.initial.missing.detail
    data = forcing_data()
    data["carbon_inputs"][0]["unit"] = "PLACEHOLDER_other"
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert "converts nothing" in balance.total_stock.steps[0].missing.detail


def test_pet_stands_in_for_pan_evaporation():
    data = forcing_data()
    quantity = FORCING_QUANTITIES["pan_evaporation"][1]
    pet = FORCING_QUANTITIES["potential_evapotranspiration"][1]
    data["climate"] = [
        series for series in data["climate"] if series["quantity"] != quantity
    ]
    data["climate"].append(
        months_of(
            YEARS[0],
            CLIMATE_MONTHS,
            pet,
            "mm",
            [33.3 for _ in range(CLIMATE_MONTHS)],
        )
    )
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert balance.total_stock.steps[0].value is not None
    # A missing PET month makes that month missing.
    data["climate"][-1]["months"][5]["value"] = None
    data["climate"][-1]["months"][5]["missing"] = {
        "reason": "NO_COVERAGE",
        "detail": f"{MARK}: no data",
    }
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert balance.total_stock.steps[5].value is None
    assert "potential evapotranspiration" in balance.total_stock.steps[5].missing.detail


def test_two_inputs_of_one_origin_take_the_composition_of_that_origin():
    data = forcing_data()
    data["carbon_inputs"].append(
        months_of(
            YEARS[0],
            CLIMATE_MONTHS,
            "placeholder_input_c",
            STOCK_UNIT,
            [0.0] * CLIMATE_MONTHS,
            origin=ORIGINS[0],
        )
    )
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert balance.flows[0].steps[0].value == pytest.approx(
        data["carbon_inputs"][0]["months"][0]["value"], rel=1e-12
    )
    # An origin without records is named with its scope.
    data["carbon_inputs"][0]["origin"] = "test_origin_c"
    balance = run_rothc(forcing(data), parameters=catalogue())
    detail = balance.total_stock.steps[0].missing.detail
    assert f'"{entry.ORIGIN_SCOPE_KEY}": "test_origin_c"' in detail
    assert "rothc_input_dpm_rpm_ratio" in detail


# --- the contract and the rules of every entry point -------------------------------------


def test_the_balance_names_the_forcing_and_the_variant():
    data = forcing_data()
    balance = run_rothc(forcing(data), parameters=catalogue())
    assert isinstance(balance, CarbonBalance)
    assert (balance.case_id, balance.field_id, balance.rotation_id) == (
        data["case_id"],
        data["field_id"],
        data["rotation_id"],
    )
    assert balance.carbon_model == "rothc" and balance.variant == VARIANT
    assert VARIANT == "rothc_26_3"
    assert balance.example_data is True
    assert balance.horizon == forcing(data).horizon
    assert balance.soil_depth == forcing(data).soil_depth
    assert balance.total_stock.unit == STOCK_UNIT
    assert f"{STOCK_UNIT} yr-1" == UNIT_SOIL_CARBON_TREND
    assert balance.total_stock.initial.provenance == "DERIVED"
    assert balance.total_stock.provenance == "SIMULATED"
    assert [s.quantity for s in balance.pools] == [
        "rothc_dpm_pool",
        "rothc_rpm_pool",
        "rothc_bio_pool",
        "rothc_hum_pool",
        "rothc_iom_pool",
    ]
    assert [s.quantity for s in balance.flows] == [
        "rothc_carbon_input",
        "rothc_co2_carbon",
    ]
    CarbonBalance.model_validate(balance.model_dump(mode="json"))


def test_run_rothc_is_pure():
    data = forcing_data()
    given = forcing(data)
    before = given.model_dump(mode="json")
    parameters = catalogue()
    kept = copy.deepcopy(parameters)
    first = run_rothc(given, parameters=parameters)
    second = run_rothc(given, parameters=parameters)
    assert first == second
    assert given.model_dump(mode="json") == before
    assert parameters == kept


def test_signature_of_the_entry_point():
    parameters = inspect.signature(run_rothc).parameters
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
    assert numbers <= {0, 1, 0.0, 1.0}, numbers


def section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("EP6 run_rothc: PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written, sorted(listed ^ written)
