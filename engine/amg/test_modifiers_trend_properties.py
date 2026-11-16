"""Analytical and mutant-killing property tests for ``modifiers.py``, ``trend.py``, and ``entry.py``.

Every constant, unit string, and forcing in this file is a PLACEHOLDER (repeated
digits or small whole numbers); zero values of the science or publication
constants are written anywhere.
"""

from __future__ import annotations

import copy
import math
from types import MappingProxyType

import pytest

from contracts.carbon_balance import CarbonBalance
from contracts.results.models import (
    DIRECTION_OF,
    TREND_COMPUTATIONS,
    UNIT_SOIL_CARBON_TREND,
)
from engine.amg import (
    PoolState,
    StepInput,
    end_minus_start,
    fitted_slope,
    mean_over_cycles,
    run_amg,
    trend_measures,
)
from engine.amg.entry import FORCING_QUANTITIES, MODIFIERS, STOCK_UNIT
from engine.amg.test_amg import (
    DEGREE,
    DEPTH,
    TIME,
    a_run,
    assert_missing,
    carbonate,
    clay,
    cn,
    moisture,
    ph,
    rate,
    temperature,
)
from engine.amg.test_entry import (
    YEARS,
    annual,
    catalogue,
    catalogue_with,
    forcing,
    forcing_data,
    unmark,
)

# --- S8 temperature modifier: zero cut <= 0 and rise > 0 -----------------------


@pytest.mark.parametrize(
    "t",
    [0.0, -0.0, 0, -1e-12, -1e-6, -0.111, -11.1, -999.9],
)
@pytest.mark.parametrize("ref", [-22.2, 0.0, 22.2])
@pytest.mark.parametrize("shape", [0.5, 1.0, 3.33])
def test_s8_temperature_cut_is_exact_zero_at_or_below_zero(t, ref, shape):
    result = temperature(
        temperature=t,
        reference_temperature=ref,
        shape_coefficient=shape,
        sensitivity_coefficient=0.111,
    )
    assert result == 0.0
    assert isinstance(result, float)


@pytest.mark.parametrize("t", [1e-12, 1e-9, 1e-6, 0.111, 11.1, 22.2, 33.3, 99.9])
def test_s8_temperature_above_zero_is_strictly_positive_and_bounded_by_shape(t):
    shape = 3.33
    result = temperature(
        temperature=t,
        reference_temperature=22.2,
        shape_coefficient=shape,
        sensitivity_coefficient=0.111,
    )
    assert isinstance(result, float)
    assert 0.0 < result < shape


def test_s8_temperature_discontinuity_at_zero_kills_shifted_or_omitted_cut():
    # At T = 0, S8 cuts cleanly to 0.0; the continuous curve at T = 0 would be > 0.
    at_zero = temperature(temperature=0.0)
    just_above = temperature(temperature=1e-12)
    continuous_at_zero = 3.33 / (1.0 + (3.33 - 1.0) * math.exp(0.111 * 22.2))
    assert at_zero == 0.0
    assert continuous_at_zero > 0.0
    assert just_above == pytest.approx(continuous_at_zero, rel=1e-10)
    assert just_above > 0.0


def test_s8_temperature_strictly_rises_above_zero_and_crosses_one_at_reference():
    ref = 22.2
    shape = 3.33
    temps = [1e-9, 1.11, 11.1, ref, 33.3, 55.5, 99.9]
    values = [
        temperature(temperature=t, reference_temperature=ref, shape_coefficient=shape)
        for t in temps
    ]
    assert all(a < b for a, b in zip(values, values[1:]))
    # Below reference: strictly in (0, 1); at reference: 1.0; above reference: in (1, shape).
    ref_index = temps.index(ref)
    assert all(0.0 < v < 1.0 for v in values[:ref_index])
    assert values[ref_index] == pytest.approx(1.0, rel=1e-15)
    assert all(1.0 < v < shape for v in values[ref_index + 1 :])

    # Scaling sensitivity by factor c and (ref - T) by 1/c preserves f_T for T > 0.
    t_a, sens_a = 11.1, 0.111
    t_b = ref - (ref - t_a) / 2.0
    sens_b = 2.0 * sens_a
    assert temperature(
        temperature=t_a, reference_temperature=ref, sensitivity_coefficient=sens_a
    ) == pytest.approx(
        temperature(
            temperature=t_b, reference_temperature=ref, sensitivity_coefficient=sens_b
        ),
        rel=1e-14,
    )


def test_s8_temperature_edge_shapes_and_zero_division():
    # shape == 1.0 yields constant 1.0 above zero while still 0.0 at or below zero.
    assert temperature(temperature=0.0, shape_coefficient=1.0) == 0.0
    for t in (1e-9, 11.1, 22.2, 44.4):
        assert temperature(temperature=t, shape_coefficient=1.0) == 1.0

    # shape == 0.0 at T == reference_temperature divides 0 by 0 -> NOT_COMPUTABLE.
    assert_missing(
        temperature(temperature=22.2, reference_temperature=22.2, shape_coefficient=0.0),
        "NOT_COMPUTABLE",
        "temperature_modifier",
    )


def test_s8_temperature_cut_through_run_amg_distinguishes_zero_from_positive_tiny():
    data_zero = forcing_data()
    data_zero["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [0.0, -11.1, 99.9, 88.8]
    )
    bal_zero = run_amg(forcing(data_zero), parameters=catalogue())
    assert bal_zero.flows[1].steps[0].value == 0.0
    assert bal_zero.flows[1].steps[1].value == 0.0
    assert bal_zero.flows[1].steps[2].value > 0.0

    data_pos = forcing_data()
    data_pos["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [1e-6, -1e-12, 99.9, 88.8]
    )
    bal_pos = run_amg(forcing(data_pos), parameters=catalogue())
    assert bal_pos.flows[1].steps[0].value > 0.0
    assert bal_pos.flows[1].steps[1].value == 0.0


# --- S7-S13 bounds [0, 1], monotonicity, and optimum symmetry (pH, C:N) --------


def test_s9_moisture_bounds_monotonicity_and_logistic_symmetry():
    shape = 0.555
    sens = 0.0222
    balances = [-222.0, -55.5, -11.1, 0.0, 11.1, 55.5, 222.0]
    values = [
        moisture(
            water_balance=w, shape_coefficient=shape, sensitivity_coefficient=sens
        )
        for w in balances
    ]
    assert all(0.0 < v < 1.0 for v in values)
    assert all(a < b for a, b in zip(values, values[1:]))
    assert moisture(
        water_balance=0.0, shape_coefficient=shape, sensitivity_coefficient=sens
    ) == pytest.approx(1.0 / (1.0 + shape), rel=1e-15)
    assert moisture(water_balance=-55.5, shape_coefficient=0.0) == 1.0

    # Decreasing in shape_coefficient.
    assert moisture(water_balance=11.1, shape_coefficient=0.222) > moisture(
        water_balance=11.1, shape_coefficient=0.888
    )

    # Logistic odds identity: (1/f_W(w) - 1) * (1/f_W(-w) - 1) == shape**2.
    f_pos = moisture(
        water_balance=33.3, shape_coefficient=shape, sensitivity_coefficient=sens
    )
    f_neg = moisture(
        water_balance=-33.3, shape_coefficient=shape, sensitivity_coefficient=sens
    )
    assert ((1.0 / f_pos) - 1.0) * ((1.0 / f_neg) - 1.0) == pytest.approx(
        shape**2, rel=1e-14
    )


def test_s10_clay_bounds_monotonicity_and_semigroup_property():
    sens = 0.00222
    contents = [0.0, 11.1, 55.5, 111.0, 222.0, 555.0]
    values = [
        clay(clay_content=c, sensitivity_coefficient=sens) for c in contents
    ]
    assert values[0] == 1.0
    assert all(0.0 < v <= 1.0 for v in values)
    assert all(a > b for a, b in zip(values, values[1:]))

    # Exponential semigroup: f_A(c1 + c2) == f_A(c1) * f_A(c2).
    assert clay(clay_content=33.3 + 44.4, sensitivity_coefficient=sens) == pytest.approx(
        clay(clay_content=33.3, sensitivity_coefficient=sens)
        * clay(clay_content=44.4, sensitivity_coefficient=sens),
        rel=1e-14,
    )


def test_s11_carbonate_bounds_monotonicity_and_reciprocal_linearity():
    sens = 0.0333
    contents = [0.0, 11.1, 33.3, 66.6, 222.0]
    values = [
        carbonate(carbonate_content=c, sensitivity_coefficient=sens) for c in contents
    ]
    assert values[0] == 1.0
    assert all(0.0 < v <= 1.0 for v in values)
    assert all(a > b for a, b in zip(values, values[1:]))

    # Reciprocal linearity: 1 / f_CaCO3(c) - 1 == sensitivity * c.
    for c, v in zip(contents, values, strict=True):
        assert (1.0 / v) - 1.0 == pytest.approx(sens * c, rel=1e-14, abs=1e-15)


def test_s12_ph_bounds_monotonicity_symmetry_and_quadratic_exponent():
    opt = 7.77
    sens = 0.111
    assert ph(ph=opt, optimum_ph=opt, sensitivity_coefficient=sens) == 1.0

    # Strictly increases toward optimum from below, strictly decreases above.
    below = [3.33, 5.55, 6.66, opt]
    above = [opt, 8.88, 9.99, 12.21]
    vals_below = [
        ph(ph=v, optimum_ph=opt, sensitivity_coefficient=sens) for v in below
    ]
    vals_above = [
        ph(ph=v, optimum_ph=opt, sensitivity_coefficient=sens) for v in above
    ]
    assert all(0.0 < v <= 1.0 for v in vals_below + vals_above)
    assert all(a < b for a, b in zip(vals_below, vals_below[1:]))
    assert all(a > b for a, b in zip(vals_above, vals_above[1:]))

    # Exact symmetry around optimum_ph.
    for delta in (0.111, 1.11, 3.33, 6.66):
        left = ph(ph=opt - delta, optimum_ph=opt, sensitivity_coefficient=sens)
        right = ph(ph=opt + delta, optimum_ph=opt, sensitivity_coefficient=sens)
        assert left == pytest.approx(right, rel=1e-15)
        assert 0.0 < left < 1.0

    # Quadratic exponent check: log(f_pH(opt + 2d)) == 4 * log(f_pH(opt + d)).
    # Kills abs(ph - opt) or missing-square mutants.
    d = 1.11
    f1 = ph(ph=opt + d, optimum_ph=opt, sensitivity_coefficient=sens)
    f2 = ph(ph=opt + 2.0 * d, optimum_ph=opt, sensitivity_coefficient=sens)
    assert math.log(f2) / math.log(f1) == pytest.approx(4.0, rel=1e-14)


def test_s13_cn_ratio_bounds_monotonicity_symmetry_and_d192_d199_distinction():
    opt = 66.6
    sens = 0.00444
    for minimum in (0.0, 0.222, 0.555, 0.888, 1.0):
        assert cn(
            cn_ratio=opt,
            optimum_cn_ratio=opt,
            sensitivity_coefficient=sens,
            minimum=minimum,
        ) == pytest.approx(1.0, rel=1e-15)

        grid = [0.0, 11.1, 33.3, 55.5, opt, 77.7, 99.9, 111.0]
        vals = [
            cn(
                cn_ratio=r,
                optimum_cn_ratio=opt,
                sensitivity_coefficient=sens,
                minimum=minimum,
            )
            for r in grid
        ]
        assert all(minimum <= v <= 1.0 for v in vals)

        if minimum < 1.0:
            peak_idx = grid.index(opt)
            assert all(a < b for a, b in zip(vals[: peak_idx + 1], vals[1 : peak_idx + 1]))
            assert all(a > b for a, b in zip(vals[peak_idx:], vals[peak_idx + 1 :]))
            assert all(v > minimum for v in vals)

            # Optimum symmetry for all deltas keeping ratio >= 0.
            for delta in (1.11, 11.1, 33.3, 66.6):
                left = cn(
                    cn_ratio=opt - delta,
                    optimum_cn_ratio=opt,
                    sensitivity_coefficient=sens,
                    minimum=minimum,
                )
                right = cn(
                    cn_ratio=opt + delta,
                    optimum_cn_ratio=opt,
                    sensitivity_coefficient=sens,
                    minimum=minimum,
                )
                assert left == pytest.approx(right, rel=1e-15)
                assert minimum < left < 1.0

            # Gaussian quadratic decay of normalized excess (f_CN - min) / (1 - min).
            d = 11.1
            e1 = (
                cn(
                    cn_ratio=opt + d,
                    optimum_cn_ratio=opt,
                    sensitivity_coefficient=sens,
                    minimum=minimum,
                )
                - minimum
            ) / (1.0 - minimum)
            e2 = (
                cn(
                    cn_ratio=opt + 2.0 * d,
                    optimum_cn_ratio=opt,
                    sensitivity_coefficient=sens,
                    minimum=minimum,
                )
                - minimum
            ) / (1.0 - minimum)
            assert e2 == pytest.approx(e1**4, rel=1e-14)
        else:
            assert all(v == 1.0 for v in vals)

    # Distinguish S13 (D192/D199) from max(minimum, exp(...)) in the tail where exp < minimum.
    minimum = 0.555
    far_r = 111.0
    exp_only = math.exp(-sens * (far_r - opt) ** 2)
    assert exp_only < minimum
    s13_val = cn(
        cn_ratio=far_r,
        optimum_cn_ratio=opt,
        sensitivity_coefficient=sens,
        minimum=minimum,
    )
    assert s13_val > minimum
    assert s13_val != pytest.approx(max(minimum, exp_only), rel=1e-6)


def test_s7_rate_coefficient_bounds_linearity_and_permutation_invariance():
    pot = 0.444
    mods = {
        "temperature": temperature(temperature=11.1, reference_temperature=22.2),
        "moisture": moisture(water_balance=-11.1),
        "clay": clay(clay_content=55.5),
        "carbonate": carbonate(carbonate_content=22.2),
        "ph": ph(ph=6.66, optimum_ph=7.77),
        "cn_ratio": cn(cn_ratio=55.5, optimum_cn_ratio=66.6),
    }
    assert tuple(mods) == MODIFIERS
    assert all(0.0 <= v <= 1.0 for v in mods.values())

    k = rate(potential_rate=pot, modifiers=mods)
    assert 0.0 <= k <= pot

    # Permutation invariance over modifier ordering.
    reversed_mods = dict(reversed(list(mods.items())))
    assert rate(potential_rate=pot, modifiers=reversed_mods) == pytest.approx(
        k, rel=1e-15
    )

    # Linearity in potential_rate.
    scale = 3.33
    assert rate(potential_rate=scale * pot, modifiers=mods) == pytest.approx(
        scale * k, rel=1e-15
    )

    # Zeroing any single modifier zeroes rate_coefficient; setting all to 1.0 recovers pot.
    for key in mods:
        zeroed = {**mods, key: 0.0}
        assert rate(potential_rate=pot, modifiers=zeroed) == 0.0
    ones = {key: 1.0 for key in mods}
    assert rate(potential_rate=pot, modifiers=ones) == pytest.approx(pot, rel=1e-15)


# --- trend_measures: linearity, invariances, signs, and CarbonBalance ----------


def test_trend_measures_linearity_shift_and_time_scaling_on_series():
    times = [1.0, 2.0, 4.0, 7.0, 11.0]
    s1 = [10.0, 12.0, 11.0, 15.0, 18.0]
    s2 = [20.0, 18.0, 22.0, 19.0, 16.0]
    boundaries = [0, 2, 4]
    a, b, c = 2.22, -1.11, 99.9
    combo = [a * x + b * y + c for x, y in zip(s1, s2, strict=True)]

    for fn, kwargs in [
        (end_minus_start, {}),
        (fitted_slope, {}),
        (mean_over_cycles, {"cycle_boundaries": boundaries}),
    ]:
        m1 = fn(stocks=s1, times=times, **kwargs)
        m2 = fn(stocks=s2, times=times, **kwargs)
        mc = fn(stocks=combo, times=times, **kwargs)
        assert mc == pytest.approx(a * m1 + b * m2, rel=1e-12, abs=1e-12)

        # Time-shift invariance.
        assert fn(stocks=s1, times=[t + 55.5 for t in times], **kwargs) == pytest.approx(
            m1, rel=1e-13
        )
        # Time-scaling: scaling times by alpha divides the rate by alpha.
        alpha = 2.5
        assert fn(
            stocks=s1, times=[alpha * t for t in times], **kwargs
        ) == pytest.approx(m1 / alpha, rel=1e-13)


def test_trend_measures_affine_exactness_signs_and_unequal_cycle_distinction():
    times = [0.0, 1.0, 3.0, 7.0]
    boundaries = [0, 2, 3]
    for slope in (-3.33, 0.0, 2.22):
        affine = [44.4 + slope * t for t in times]
        assert end_minus_start(stocks=affine, times=times) == pytest.approx(
            slope, rel=1e-14, abs=1e-15
        )
        assert fitted_slope(stocks=affine, times=times) == pytest.approx(
            slope, rel=1e-14, abs=1e-15
        )
        assert mean_over_cycles(
            stocks=affine, times=times, cycle_boundaries=boundaries
        ) == pytest.approx(slope, rel=1e-14, abs=1e-15)

    # Strictly increasing / decreasing / constant series -> positive / negative / zero signs.
    inc = [10.0, 11.1, 13.3, 18.8]
    dec = [18.8, 13.3, 11.1, 10.0]
    const = [44.4, 44.4, 44.4, 44.4]
    for fn, kwargs in [
        (end_minus_start, {}),
        (fitted_slope, {}),
        (mean_over_cycles, {"cycle_boundaries": boundaries}),
    ]:
        assert fn(stocks=inc, times=times, **kwargs) > 0.0
        assert fn(stocks=dec, times=times, **kwargs) < 0.0
        assert fn(stocks=const, times=times, **kwargs) == 0.0

    # Mutant killer: unequal cycle durations distinguish mean_over_cycles from end_minus_start.
    # Cycle 1: dt=1.0, dS=4.0 -> rate=4.0; Cycle 2: dt=3.0, dS=0.0 -> rate=0.0.
    # Mean of per-cycle rates is (4.0 + 0.0)/2 = 2.0, while end_minus_start is 4.0/4.0 = 1.0.
    unequal_stocks = [10.0, 14.0, 14.0]
    unequal_times = [0.0, 1.0, 4.0]
    assert mean_over_cycles(
        stocks=unequal_stocks, times=unequal_times, cycle_boundaries=[0, 1, 2]
    ) == pytest.approx(2.0, rel=1e-15)
    assert end_minus_start(stocks=unequal_stocks, times=unequal_times) == pytest.approx(
        1.0, rel=1e-15
    )


@pytest.mark.parametrize("scheme", ["explicit", "exponential"])
def test_trend_measures_homogeneity_and_constant_shift_on_run(scheme):
    scale = 2.5
    delta = 77.7
    steps_base = [
        StepInput(humified_input=1.11, rate_coefficient=0.111, duration=1.0),
        StepInput(humified_input=2.22, rate_coefficient=0.222, duration=0.5),
        StepInput(humified_input=0.555, rate_coefficient=0.111, duration=1.5),
        StepInput(humified_input=3.33, rate_coefficient=0.0555, duration=1.0),
    ]
    steps_scaled = [
        StepInput(
            humified_input=scale * s.humified_input,
            rate_coefficient=s.rate_coefficient,
            duration=s.duration,
        )
        for s in steps_base
    ]
    base_init = PoolState(active=44.4, stable=22.2)
    base_run = a_run(steps_base, scheme=scheme, initial_state=base_init)
    scaled_run = a_run(
        steps_scaled,
        scheme=scheme,
        initial_state=PoolState(
            active=scale * base_init.active, stable=scale * base_init.stable
        ),
    )
    shifted_run = a_run(
        steps_base,
        scheme=scheme,
        initial_state=PoolState(active=base_init.active, stable=base_init.stable + delta),
    )
    m_base = trend_measures(run=base_run, cycle_boundaries=[0, 2, 4])
    m_scaled = trend_measures(run=scaled_run, cycle_boundaries=[0, 2, 4])
    m_shifted = trend_measures(run=shifted_run, cycle_boundaries=[0, 2, 4])

    assert tuple(m_base.values) == TREND_COMPUTATIONS
    assert m_base.time_unit == TIME
    for key in TREND_COMPUTATIONS:
        assert m_scaled.values[key] == pytest.approx(
            scale * m_base.values[key], rel=1e-12
        )
        assert m_shifted.values[key] == pytest.approx(
            m_base.values[key], rel=1e-12, abs=1e-12
        )


def test_carbon_balance_trend_linearity_constant_shift_and_signs():
    # Homogeneity and constant-stable-shift invariance through run_amg -> CarbonBalance.
    base_data = forcing_data()
    params = catalogue()
    base_bal = run_amg(forcing(base_data), parameters=params)
    base_trends = {
        t.computation: t.value for t in base_bal.soil_carbon_trend if t.value is not None
    }
    assert set(base_trends) == {"end_minus_start", "fitted_slope"}

    # Scale starting_carbon and every annual carbon input by `scale`.
    scale = 3.0
    scaled_data = copy.deepcopy(base_data)
    scaled_data["starting_state"][0]["value"] *= scale
    for series in scaled_data["annual_carbon_inputs"]:
        for item in series["years"]:
            if item["value"] is not None:
                item["value"] *= scale
    scaled_bal = run_amg(forcing(scaled_data), parameters=params)
    for item in scaled_bal.soil_carbon_trend:
        if item.computation in base_trends:
            assert item.value == pytest.approx(
                scale * base_trends[item.computation], rel=1e-10, abs=1e-10
            )
            assert item.direction == DIRECTION_OF["soil_carbon_trend"]
            assert item.unit == UNIT_SOIL_CARBON_TREND

    # Shift stable pool by +delta while preserving initial active pool.
    c0 = base_data["starting_state"][0]["value"]
    f0 = params["records/stable_fraction.json"]["value"]
    delta = 11111.1
    new_f = (f0 * c0 + delta) / (c0 + delta)
    shifted_data = copy.deepcopy(base_data)
    shifted_data["starting_state"][0]["value"] = c0 + delta
    shifted_params = catalogue_with("stable_fraction", {"value": new_f})
    shifted_bal = run_amg(forcing(shifted_data), parameters=shifted_params)
    for item in shifted_bal.soil_carbon_trend:
        if item.computation in base_trends:
            assert item.value == pytest.approx(
                base_trends[item.computation], rel=1e-12, abs=1e-10
            )

    # Sign check 1: zero carbon inputs with positive rate -> strictly negative trends.
    zero_in_data = copy.deepcopy(base_data)
    for series in zero_in_data["annual_carbon_inputs"]:
        for item in series["years"]:
            item["value"] = 0.0
    neg_bal = run_amg(forcing(zero_in_data), parameters=params)
    for item in neg_bal.soil_carbon_trend:
        if item.computation in ("end_minus_start", "fitted_slope"):
            assert item.value < 0.0

    # Sign check 2: temperature <= 0 (zero mineralisation) with positive inputs -> positive trends.
    frozen_data = copy.deepcopy(base_data)
    frozen_data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [0.0, -5.5, -11.1, 0.0]
    )
    pos_bal = run_amg(forcing(frozen_data), parameters=params)
    for item in pos_bal.soil_carbon_trend:
        if item.computation in ("end_minus_start", "fitted_slope"):
            assert item.value > 0.0

    # Sign check 3: steady-state constant input I = A0 * k (under uniform climate) -> zero trends.
    steady_data = copy.deepcopy(base_data)
    steady_data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [99.9, 99.9, 99.9, 99.9]
    )
    steady_data["annual_climate"][1] = annual(
        FORCING_QUANTITIES["water_balance"][1], unmark(DEPTH), [0.0, 0.0, 0.0, 0.0]
    )
    for series in steady_data["annual_carbon_inputs"]:
        for item in series["years"]:
            item["value"] = 0.0
    probe = run_amg(forcing(steady_data), parameters=params)
    a0 = probe.pools[0].initial.value
    a1 = probe.pools[0].steps[0].value
    # Under zero input, a1 = a0 * exp(-k), so k = -log(a1 / a0); steady inflow = a0 * k.
    k = -math.log(a1 / a0)
    h_coeff = params["records/humification_test_origin_a.json"]["value"]
    steady_raw_input = (a0 * k) / h_coeff
    steady_data["annual_carbon_inputs"] = [
        annual(
            "placeholder_input_a",
            STOCK_UNIT,
            [steady_raw_input] * len(YEARS),
            origin="test_origin_a",
        )
    ]
    steady_bal = run_amg(forcing(steady_data), parameters=params)
    for item in steady_bal.soil_carbon_trend:
        if item.computation in ("end_minus_start", "fitted_slope"):
            assert item.value == pytest.approx(0.0, abs=1e-10)


# --- run_amg G1-G5 checks -----------------------------------------------------


def test_run_amg_g1_purity_determinism_no_file_or_env_reads(monkeypatch):
    import os

    import params.catalogue as cat_mod

    def fail(*args, **kwargs):
        raise AssertionError("G1 violated: run_amg must not read files or env")

    monkeypatch.setattr(cat_mod, "load_folder", fail)
    monkeypatch.setattr(os, "getenv", fail)

    given = forcing()
    before_forcing = given.model_dump(mode="json")
    params = catalogue()
    before_params = copy.deepcopy(params)

    first = run_amg(given, parameters=params)
    second = run_amg(given, parameters=params)

    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert given.model_dump(mode="json") == before_forcing
    assert params == before_params


def test_run_amg_g2_one_call_per_rotation_and_no_cross_call_leakage():
    d1 = forcing_data()
    d2 = forcing_data()
    d2["case_id"] = "placeholder_case_two"
    d2["field_id"] = "placeholder_field_two"
    d2["rotation_id"] = "placeholder_rotation_two"
    d2["starting_state"][0]["value"] = 22222.2

    params = catalogue()
    b1_before = run_amg(forcing(d1), parameters=params)
    b2 = run_amg(forcing(d2), parameters=params)
    b1_after = run_amg(forcing(d1), parameters=params)

    assert b1_before == b1_after
    assert (b2.case_id, b2.field_id, b2.rotation_id) == (
        "placeholder_case_two",
        "placeholder_field_two",
        "placeholder_rotation_two",
    )
    assert b2.total_stock.initial.value != b1_before.total_stock.initial.value


def test_run_amg_g3_strict_model_types_and_valid_carbon_balance_outputs():
    params = catalogue()
    # MappingProxyType is a Mapping but not a dict -> G3/G5 TypeError.
    with pytest.raises(TypeError, match="parameters"):
        run_amg(forcing(), parameters=MappingProxyType(params))  # type: ignore[arg-type]

    # Every variant of output (computed, partial missing, empty params, non-whole horizon)
    # returns a valid CarbonBalance that survives model_validate round-trip.
    partial_data = forcing_data()
    partial_data["annual_climate"][0] = annual(
        FORCING_QUANTITIES["temperature"][1], unmark(DEGREE), [88.8, None, 99.9, 77.7]
    )
    short_horizon = forcing_data()
    short_horizon["annual_climate"] = []
    short_horizon["annual_carbon_inputs"] = []
    short_horizon["horizon"]["end"] = {"year": YEARS[0], "month": 6}

    for bal in (
        run_amg(forcing(), parameters=params),
        run_amg(forcing(partial_data), parameters=params),
        run_amg(forcing(), parameters={}),
        run_amg(forcing(short_horizon), parameters=params),
    ):
        assert isinstance(bal, CarbonBalance)
        revalidated = CarbonBalance.model_validate(bal.model_dump(mode="json"))
        assert revalidated == bal


def test_run_amg_g4_missing_or_uncomputable_never_raises_and_never_clips():
    params = catalogue()

    # Negative soil properties, negative starting carbon, negative carbon input -> Missing, never clipped.
    for idx, name in ((0, "clay_content"), (1, "carbonate_content"), (3, "cn_ratio")):
        data = forcing_data()
        data["soil_properties"][idx]["value"] = -1.11
        step0 = run_amg(forcing(data), parameters=params).total_stock.steps[0]
        assert step0.value is None and step0.missing is not None
        assert step0.missing.reason == "MISSING_INPUT"
        assert "NOT_COMPUTABLE" in step0.missing.detail
        assert name in step0.missing.detail

    neg_start = forcing_data()
    neg_start["starting_state"][0]["value"] = -10.0
    bal_neg_start = run_amg(forcing(neg_start), parameters=params)
    assert bal_neg_start.total_stock.initial.value is None
    assert bal_neg_start.total_stock.initial.source is None
    assert bal_neg_start.total_stock.initial.provenance is None
    assert bal_neg_start.total_stock.initial.missing.reason == "NOT_COMPUTABLE"

    neg_in = forcing_data()
    neg_in["annual_carbon_inputs"][0] = annual(
        "placeholder_input_a", STOCK_UNIT, [1.1, -0.5, 0.0, 3.3], origin="test_origin_a"
    )
    bal_neg_in = run_amg(forcing(neg_in), parameters=params)
    assert bal_neg_in.flows[0].steps[0].value is not None
    assert bal_neg_in.flows[0].steps[1].value is None
    assert "NOT_COMPUTABLE" in bal_neg_in.flows[0].steps[1].missing.detail
    assert bal_neg_in.total_stock.steps[2].value is None
    assert "step 1 is missing" in bal_neg_in.total_stock.steps[2].missing.detail

    # Modifier overflow (exp overflow) through run_amg -> Missing, never OverflowError.
    overflow_data = forcing_data()
    overflow_data["annual_climate"][1] = annual(
        FORCING_QUANTITIES["water_balance"][1],
        unmark(DEPTH),
        [-1e300, 0.0, 0.0, 0.0],
    )
    bal_ov = run_amg(forcing(overflow_data), parameters=params)
    assert bal_ov.total_stock.steps[0].value is None
    assert "NOT_COMPUTABLE" in bal_ov.total_stock.steps[0].missing.detail

    # Missing value always has source=None, and never uses 0.0 as a stand-in.
    empty_bal = run_amg(forcing(), parameters={})
    assert empty_bal.total_stock.initial.value is None
    assert empty_bal.total_stock.initial.source is None
    assert empty_bal.total_stock.source is None
    assert all(s.value is None for s in empty_bal.total_stock.steps)
    assert all(t.value is None and t.source is None for t in empty_bal.soil_carbon_trend)


def test_run_amg_g5_only_caller_type_defects_raise_type_error():
    good_forcing = forcing()
    good_params = catalogue()
    for bad_forcing in (None, 123, "forcing", {}, forcing_data()):
        with pytest.raises(TypeError, match="forcing"):
            run_amg(bad_forcing, parameters=good_params)  # type: ignore[arg-type]
    for bad_params in (
        None,
        [],
        "params",
        {"bad": None},
        {123: {}},
        MappingProxyType(good_params),
    ):
        with pytest.raises(TypeError, match="parameters"):
            run_amg(good_forcing, parameters=bad_params)  # type: ignore[arg-type]
