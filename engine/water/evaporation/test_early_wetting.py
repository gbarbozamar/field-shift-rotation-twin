"""Unit, boundary, missing-propagation, fixture-gate, and sensitivity tests for early wetting."""

from __future__ import annotations

import copy
import dataclasses
import datetime
import inspect
import json
import math
import random
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water.evaporation import (
    DayInput,
    EarlyWettingResult,
    UpperLimitClimateConstants,
    climate_adjusted_upper_limit,
    early_wetting_step,
    step,
    total_evaporable_water,
)
from engine.water.evaporation.test_surface_layer import (
    E35_COMPARED_COLUMNS,
    E35_FIXTURE,
    e35_comparison_failures,
    e35_load_case,
    e35_read_fixture,
    e35_skip_reason,
    run_e35,
)

START = datetime.date(2001, 1, 1)  # PLACEHOLDER
TEW = 18.0  # PLACEHOLDER
REW = 8.0  # PLACEHOLDER
FW = 0.8  # PLACEHOLDER
MARGIN = 0.05  # PLACEHOLDER
LEDGER_TOL = 1e-12


def _day(
    offset: int = 0,
    *,
    p: float | Missing = 0.0,
    q: float | Missing = 0.0,
    et0: float | Missing = 2.7,
    kcb: float | Missing = 0.36,
    fc: float | Missing = 0.11,
    climate: float | Missing = 1.21,
) -> DayInput:
    return DayInput(
        date=START + datetime.timedelta(days=offset),
        precipitation=p,
        runoff=q,
        reference_evapotranspiration=et0,
        basal_crop_coefficient=kcb,
        cover_fraction=fc,
        climate_adjusted_upper_limit=climate,
    )


def _constants(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "total_evaporable_water": TEW,
        "readily_evaporable_water": REW,
        "wetted_fraction": FW,
        "margin_above_basal": MARGIN,
    }
    base.update(overrides)
    return base


def _ledger_residual(res: EarlyWettingResult) -> float:
    sub = res.evaporation_substep
    assert not isinstance(res.depletion_carried, Missing)
    assert not isinstance(res.net_rain, Missing)
    assert not isinstance(res.irrigation_wetted, Missing)
    assert not isinstance(res.deep_percolation_early, Missing)
    assert not isinstance(sub.depletion_end, Missing)
    assert not isinstance(sub.deep_percolation, Missing)
    assert not isinstance(sub.evaporation_from_exposed_fraction, Missing)
    return (
        (sub.depletion_end - res.depletion_carried)
        + res.net_rain
        + res.irrigation_wetted
        - (res.deep_percolation_early + sub.deep_percolation)
        - sub.evaporation_from_exposed_fraction
    )


# ---------------------------------------------------------------------------
# Unit & boundary behaviour.


def test_early_rain_recomputes_kr_from_depletion_after_wetting():
    res = early_wetting_step(
        17.0,
        _day(),
        net_rain=6.0,
        irrigation_field=0.0,
        **_constants(wetted_fraction=1.0),
    )
    assert res.depletion_carried == 17.0
    assert res.depletion_after_wetting == 11.0
    assert res.deep_percolation_early == 0.0
    assert res.evaporation_substep.depletion_start == 11.0
    assert res.evaporation_substep.reduction_coefficient == pytest.approx(0.7)
    assert abs(_ledger_residual(res)) <= LEDGER_TOL

    pre_wetting = step(
        17.0,
        _day(p=6.0),
        **_constants(wetted_fraction=1.0),
    )
    assert pre_wetting.reduction_coefficient == pytest.approx(0.1)


def test_partial_wetting_converts_field_irrigation_to_wetted_fraction():
    res = early_wetting_step(
        18.0,
        _day(),
        net_rain=0.0,
        irrigation_field=40.0,
        **_constants(wetted_fraction=0.8),
    )
    assert res.irrigation_field == 40.0
    assert res.irrigation_wetted == pytest.approx(50.0)
    assert res.deep_percolation_early == pytest.approx(32.0)
    assert res.depletion_after_wetting == 0.0
    assert res.evaporation_substep.reduction_coefficient == 1.0
    assert abs(_ledger_residual(res)) <= LEDGER_TOL


def test_combined_rain_and_irrigation_refill_exactly_without_percolation():
    # carried=15.0, net_rain=5.0, irrigation_field=8.0, fw=0.8 => wetted=10.0 => inflow=15.0
    res = early_wetting_step(
        15.0,
        _day(),
        net_rain=5.0,
        irrigation_field=8.0,
        **_constants(wetted_fraction=0.8),
    )
    assert res.irrigation_wetted == pytest.approx(10.0)
    assert res.depletion_after_wetting == 0.0
    assert res.deep_percolation_early == 0.0
    assert res.evaporation_substep.reduction_coefficient == 1.0
    assert abs(_ledger_residual(res)) <= LEDGER_TOL


def test_zero_inflow_matches_plain_step_on_evaporation_substep():
    d = _day(et0=5.0)
    res = early_wetting_step(
        12.0,
        d,
        net_rain=0.0,
        irrigation_field=0.0,
        **_constants(),
    )
    plain = step(12.0, d, **_constants())
    assert res.depletion_after_wetting == 12.0
    assert res.deep_percolation_early == 0.0
    assert res.irrigation_wetted == 0.0
    assert res.evaporation_substep == plain


def test_stage_boundaries_and_full_depletion_and_full_cover():
    # Exactly at REW after wetting => Kr = 1.0
    at_rew = early_wetting_step(
        12.0,
        _day(),
        net_rain=4.0,
        irrigation_field=0.0,
        **_constants(wetted_fraction=1.0),
    )
    assert at_rew.depletion_after_wetting == REW
    assert at_rew.evaporation_substep.reduction_coefficient == 1.0

    # At TEW with zero inflow => Kr = 0.0, evaporation = 0.0
    at_tew = early_wetting_step(
        TEW,
        _day(),
        net_rain=0.0,
        irrigation_field=0.0,
        **_constants(wetted_fraction=1.0),
    )
    assert at_tew.evaporation_substep.reduction_coefficient == 0.0
    assert at_tew.evaporation_substep.evaporation == 0.0
    assert at_tew.evaporation_substep.depletion_end == TEW

    # Full cover => few = 0.0, Ke = 0.0
    full_cover = early_wetting_step(
        10.0,
        _day(fc=1.0),
        net_rain=2.0,
        irrigation_field=0.0,
        **_constants(wetted_fraction=1.0),
    )
    assert full_cover.evaporation_substep.exposed_and_wetted_fraction == 0.0
    assert full_cover.evaporation_substep.evaporation_coefficient == 0.0
    assert full_cover.evaporation_substep.evaporation == 0.0
    assert full_cover.evaporation_substep.depletion_end == 8.0


def test_early_wetting_has_no_defaults():
    for field in dataclasses.fields(EarlyWettingResult):
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING
    for param in inspect.signature(early_wetting_step).parameters.values():
        assert param.default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Missing propagation.


def _assert_all_missing(res: EarlyWettingResult, reason: str, expected_text: str):
    for field in dataclasses.fields(EarlyWettingResult):
        if field.name == "evaporation_substep":
            continue
        val = getattr(res, field.name)
        assert isinstance(val, Missing), field.name
        assert val.reason == reason
        assert val.detail is not None and expected_text in val.detail
    sub = res.evaporation_substep
    for field in dataclasses.fields(sub):
        if field.name == "date":
            continue
        val = getattr(sub, field.name)
        assert isinstance(val, Missing), field.name
        assert val.reason == reason
        assert val.detail is not None and expected_text in val.detail


def test_missing_depletion_carried_propagates_to_every_field():
    res = early_wetting_step(
        Missing(reason="NO_COVERAGE", detail="gap before start"),
        _day(),
        net_rain=0.0,
        irrigation_field=0.0,
        **_constants(),
    )
    _assert_all_missing(res, "MISSING_INPUT", "gap before start")


@pytest.mark.parametrize("field_name", ["net_rain", "irrigation_field"])
def test_missing_wetting_input_propagates(field_name: str):
    kwargs = {"net_rain": 0.0, "irrigation_field": 0.0}
    kwargs[field_name] = Missing(reason="SOURCE_UNAVAILABLE")
    res = early_wetting_step(10.0, _day(), **kwargs, **_constants())
    _assert_all_missing(
        res, "MISSING_INPUT", f"input '{field_name}' (SOURCE_UNAVAILABLE)"
    )


@pytest.mark.parametrize(
    "const_name",
    [
        "total_evaporable_water",
        "readily_evaporable_water",
        "wetted_fraction",
        "margin_above_basal",
    ],
)
def test_missing_constant_propagates(const_name: str):
    res = early_wetting_step(
        10.0,
        _day(),
        net_rain=0.0,
        irrigation_field=0.0,
        **_constants(**{const_name: Missing(reason="NOT_DECLARED")}),
    )
    _assert_all_missing(res, "MISSING_INPUT", f"constant '{const_name}' (NOT_DECLARED)")


@pytest.mark.parametrize(
    "day_kw, field_name",
    [
        ("p", "precipitation"),
        ("q", "runoff"),
        ("et0", "reference_evapotranspiration"),
        ("kcb", "basal_crop_coefficient"),
        ("fc", "cover_fraction"),
        ("climate", "climate_adjusted_upper_limit"),
    ],
)
def test_missing_day_input_propagates(day_kw: str, field_name: str):
    res = early_wetting_step(
        10.0,
        _day(**{day_kw: Missing(reason="NO_COVERAGE")}),
        net_rain=0.0,
        irrigation_field=0.0,
        **_constants(),
    )
    _assert_all_missing(res, "MISSING_INPUT", f"{field_name} (NO_COVERAGE)")


# ---------------------------------------------------------------------------
# D185 out-of-range depletion_carried, fw bounds, and caller defects.


@pytest.mark.parametrize("carried", [-0.1, TEW + 0.01, TEW + 10.0, math.nan, math.inf])
def test_out_of_range_or_d185_depletion_carried_raises_value_error(carried: float):
    with pytest.raises(ValueError):
        early_wetting_step(
            carried,
            _day(),
            net_rain=0.0,
            irrigation_field=0.0,
            **_constants(),
        )


@pytest.mark.parametrize("fw", [0.0, -0.01, -1.0, 1.0001, 1.5, math.nan, math.inf])
def test_wetted_fraction_outside_open_closed_unit_interval_raises(fw: float):
    with pytest.raises(ValueError):
        early_wetting_step(
            10.0,
            _day(),
            net_rain=0.0,
            irrigation_field=0.0,
            **_constants(wetted_fraction=fw),
        )


def test_zero_wetted_fraction_still_raises_when_inputs_are_missing():
    with pytest.raises(ValueError, match="wetted_fraction"):
        early_wetting_step(
            Missing(reason="NO_COVERAGE"),
            _day(),
            net_rain=Missing(reason="NO_COVERAGE"),
            irrigation_field=0.0,
            **_constants(wetted_fraction=0.0),
        )


def test_nonzero_day_precipitation_or_runoff_raises_value_error():
    with pytest.raises(ValueError, match="evaporation-only substep"):
        early_wetting_step(
            10.0,
            _day(p=1.0),
            net_rain=0.0,
            irrigation_field=0.0,
            **_constants(),
        )
    with pytest.raises(ValueError, match="evaporation-only substep"):
        early_wetting_step(
            10.0,
            _day(q=0.5),
            net_rain=0.0,
            irrigation_field=0.0,
            **_constants(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"net_rain": -0.1, "irrigation_field": 0.0},
        {"net_rain": 0.0, "irrigation_field": -0.1},
        {"net_rain": math.nan, "irrigation_field": 0.0},
        {"net_rain": 0.0, "irrigation_field": math.inf},
    ],
)
def test_invalid_wetting_numbers_raise_value_error(kwargs: dict):
    with pytest.raises(ValueError):
        early_wetting_step(10.0, _day(), **kwargs, **_constants())


@pytest.mark.parametrize(
    "bad_arg",
    [
        {"depletion_carried": True},
        {"net_rain": "5"},
        {"irrigation_field": False},
        {"wetted_fraction": True},
    ],
)
def test_non_number_or_bool_raises_type_error(bad_arg: dict):
    depletion_carried = bad_arg.get("depletion_carried", 10.0)
    net_rain = bad_arg.get("net_rain", 0.0)
    irrigation_field = bad_arg.get("irrigation_field", 0.0)
    fw = bad_arg.get("wetted_fraction", FW)
    with pytest.raises(TypeError):
        early_wetting_step(
            depletion_carried,
            _day(),
            net_rain=net_rain,
            irrigation_field=irrigation_field,
            **_constants(wetted_fraction=fw),
        )


# ---------------------------------------------------------------------------
# Multi-day ledger closure and bounds.


def test_multi_day_ledger_closure_and_bounds():
    rng = random.Random(20261115)
    carried = TEW
    for offset in range(180):
        fw = rng.choice([0.25, 0.5, 0.8, 1.0])
        rain = 0.0 if rng.random() < 0.6 else rng.uniform(0.0, 25.0)
        irrig = 0.0 if rng.random() < 0.8 else rng.uniform(0.0, 35.0)
        res = early_wetting_step(
            carried,
            _day(
                offset,
                et0=rng.uniform(0.0, 8.0),
                kcb=rng.uniform(0.15, 1.15),
                fc=rng.uniform(0.0, 1.0),
                climate=rng.uniform(1.0, 1.4),
            ),
            net_rain=rain,
            irrigation_field=irrig,
            **_constants(wetted_fraction=fw),
        )
        sub = res.evaporation_substep
        assert 0.0 <= res.depletion_after_wetting <= TEW
        assert 0.0 <= sub.depletion_end <= TEW
        assert res.deep_percolation_early >= 0.0
        assert abs(_ledger_residual(res)) <= LEDGER_TOL
        carried = sub.depletion_end


# ---------------------------------------------------------------------------
# Fixture gate (tmp_path unsigned / unaccepted / tampered).


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / E35_FIXTURE.name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_fixture_gate_absent_file_skips(tmp_path: Path):
    reason = e35_skip_reason(tmp_path / E35_FIXTURE.name)
    assert reason is not None
    assert E35_FIXTURE.name in reason
    assert "absent" in reason
    assert "checked_by" in reason


def test_fixture_gate_unsigned_checked_by_skips(tmp_path: Path):
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    data["checked_by"] = ""
    reason = e35_skip_reason(_write_fixture(tmp_path, data))
    assert reason is not None
    assert "checked_by" in reason


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d.pop("method_acceptance"),
        lambda d: d.__setitem__("method_acceptance", "invalid"),
        lambda d: d["method_acceptance"].__setitem__("accepted_by", "   "),
        lambda d: d["method_acceptance"].__setitem__("early_wetting_option", "PENDING"),
    ],
)
def test_fixture_gate_unaccepted_method_skips(tmp_path: Path, mutator):
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    mutator(data)
    reason = e35_skip_reason(_write_fixture(tmp_path, data))
    assert reason is not None
    assert "method_acceptance" in reason


def test_fixture_gate_signed_and_accepted_copy_passes(tmp_path: Path):
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    path = _write_fixture(tmp_path, data)
    assert e35_skip_reason(path) is None
    assert run_e35(path) == []


@pytest.mark.parametrize("col", E35_COMPARED_COLUMNS)
def test_fixture_tampered_cell_outside_half_last_digit_fails(tmp_path: Path, col: str):
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    entry = data["rows"][-1][col]
    decimals = len(entry["printed"].partition(".")[2])
    moved = f"{entry['value'] + 2.0 * 10.0**-decimals:.{decimals}f}"
    entry["value"] = float(moved)
    entry["printed"] = moved
    problems = run_e35(_write_fixture(tmp_path, data))
    assert any(f"day 10, {col}:" in p for p in problems)


def test_fixture_tampered_tolerance_fails(tmp_path: Path):
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    data["tolerance"]["ke"] *= 2.0
    problems = run_e35(_write_fixture(tmp_path, data))
    assert problems
    assert all(p.startswith("tolerance.ke") for p in problems)


def test_fixture_value_mismatch_against_printed_fails():
    data = copy.deepcopy(e35_read_fixture(E35_FIXTURE))
    data["rows"][0]["kr"]["value"] += 0.5
    with pytest.raises(AssertionError, match=r"rows\[1\]\.kr"):
        e35_load_case(data)


# ---------------------------------------------------------------------------
# Sensitivity: pre-wetting step vs accepted early_wetting_step on Example 35.


def test_pre_wetting_step_diverges_from_example35_on_wet_days():
    case = e35_load_case(e35_read_fixture(E35_FIXTURE))
    assert e35_comparison_failures(case) == []

    c = case.constants
    interp = case.interpolation
    climate = climate_adjusted_upper_limit(
        c["u2_m_s"],
        c["rhmin_percent"],
        c["h_m"],
        constants=UpperLimitClimateConstants(
            base=c["base"],
            wind_coefficient=c["wind_coefficient"],
            reference_wind_speed=c["reference_wind_speed"],
            humidity_coefficient=c["humidity_coefficient"],
            reference_minimum_relative_humidity=c[
                "reference_minimum_relative_humidity"
            ],
            reference_crop_height=c["reference_crop_height"],
            height_exponent=c["height_exponent"],
        ),
    )
    tew = total_evaporable_water(
        c["theta_fc"],
        c["theta_wp"],
        c["ze_m"],
        wilting_point_weight=c["wilting_point_weight"],
        unit_factor=c["unit_factor"],
    )

    # Run the same 10-day forcing through pre-wetting `step` (Kr before inflow).
    carried = c["initial_de_mm"]
    span = interp["days"] - 1.0
    pre_wetting_results = []
    for day_index, row in enumerate(case.rows):
        ratio = day_index / span
        uncovered = interp["uncovered_start"] + ratio * (
            interp["uncovered_end"] - interp["uncovered_start"]
        )
        kcb = interp["kcb_start"] + ratio * (interp["kcb_end"] - interp["kcb_start"])
        fw = row["fw"]
        inflow_wetted = row["rain_minus_runoff"] + row["irrigation_div_fw"]
        res = step(
            carried,
            DayInput(
                date=START + datetime.timedelta(days=day_index),
                precipitation=inflow_wetted,
                runoff=0.0,
                reference_evapotranspiration=row["eto"],
                basal_crop_coefficient=kcb,
                cover_fraction=1.0 - uncovered,
                climate_adjusted_upper_limit=climate,
            ),
            total_evaporable_water=tew,
            readily_evaporable_water=c["rew_mm"],
            wetted_fraction=fw,
            margin_above_basal=c["margin_above_basal"],
        )
        pre_wetting_results.append(res)
        carried = res.depletion_end

    # Wet day 1 (irrigation_div_fw = 50 from carried = TEW = 18):
    # pre-wetting step evaluates Kr on De = 18 -> Kr = 0.0, Ke = 0.0 (printed: 1.00, 0.91).
    day1_pre = pre_wetting_results[0]
    assert day1_pre.reduction_coefficient == 0.0
    assert (
        abs(day1_pre.reduction_coefficient - case.rows[0]["kr"]) > case.tolerance["kr"]
    )
    assert (
        abs(day1_pre.evaporation_coefficient - case.rows[0]["ke"])
        > case.tolerance["ke"]
    )

    # Wet day 6 (rain_minus_runoff = 6):
    # pre-wetting step evaluates Kr on pre-rain depletion -> diverges from printed Kr = 0.71.
    day6_pre = pre_wetting_results[5]
    assert (
        abs(day6_pre.reduction_coefficient - case.rows[5]["kr"]) > case.tolerance["kr"]
    )
    assert (
        abs(day6_pre.evaporation_coefficient - case.rows[5]["ke"])
        > case.tolerance["ke"]
    )
