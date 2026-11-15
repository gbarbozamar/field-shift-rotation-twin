"""Multi-day mass conservation and boundary tests across water balance modules.

Exercises ``engine/water/runoff/curve_number.py``,
``engine/water/evaporation/surface_layer.py``, and
``engine/water/balance/bucket.py`` individually and wired together across
multi-day sequences.

EVERY NUMBER IN THIS FILE IS A PLACEHOLDER chosen to exercise the structure,
bounds, conservation laws, monotonicity, and missing-value latching of the
code. None is a real soil, crop, curve-number, or climate parameter, and none
comes from FAO-56, USDA-NRCS, or any field record.
"""

from __future__ import annotations

import dataclasses
import datetime
import random
import sys

import pytest

from contracts.results.models import Missing
from engine.water.balance.bucket import (
    RESULT_QUANTITIES as BALANCE_RESULT_QUANTITIES,
    CropDay,
    DayInput as BalanceDayInput,
    DayResult as BalanceDayResult,
    run_balance,
    step as balance_step,
    stress_coefficient,
)
from engine.water.evaporation.surface_layer import (
    RESULT_QUANTITIES as SURFACE_RESULT_QUANTITIES,
    DayInput as SurfaceDayInput,
    DayResult as SurfaceDayResult,
    run_surface_layer,
)
from engine.water.runoff.curve_number import (
    PRECIPITATION_UNIT,
    CurveNumberConstants,
    PrecipitationValue,
    RunoffDayInput,
    initial_abstraction,
    potential_retention,
    run_runoff,
    runoff_depth,
)

EPS = sys.float_info.epsilon
START = datetime.date(2001, 1, 1)  # PLACEHOLDER start date

# PLACEHOLDER column and surface-layer parameters (plainly synthetic).
CAPACITY = 64.0  # PLACEHOLDER
COLUMN_DEPTH = 4.0  # PLACEHOLDER
TEW = 32.0  # PLACEHOLDER total evaporable water
REW = 8.0  # PLACEHOLDER readily evaporable water
FW = 0.5  # PLACEHOLDER wetted fraction
MARGIN = 0.5  # PLACEHOLDER margin above basal coefficient
CLIMATE = 2.5  # PLACEHOLDER climate-adjusted upper limit

# PLACEHOLDER Curve Number constants: S = 4 * (20 / CN - 0.5), zero at CN = 40.
CN_CONSTANTS = CurveNumberConstants(
    initial_abstraction_ratio=0.25,  # PLACEHOLDER
    retention_numerator=20.0,  # PLACEHOLDER
    retention_offset=0.5,  # PLACEHOLDER
    retention_unit_factor=4.0,  # PLACEHOLDER
)
CN_TOP = 40.0  # PLACEHOLDER curve number where S == 0 under CN_CONSTANTS
UNIT_GUARD_REASON = "NOT_COMPUTABLE"  # PLACEHOLDER reason code

BALANCE_FLOWS = (
    "precipitation",
    "runoff",
    "evaporation",
    "transpiration",
    "drainage",
)


def _crop(
    root_depth: float = 2.0,  # PLACEHOLDER
    kcb: float = 1.25,  # PLACEHOLDER
    fraction: float = 0.5,  # PLACEHOLDER
) -> CropDay:
    return CropDay(
        transpiration_coefficient=kcb,
        root_depth=root_depth,
        readily_available_fraction=fraction,
    )


def _coupled_run(
    specs: list[dict],
    *,
    initial_depletion: float = 0.0,  # PLACEHOLDER
    initial_storage: float = 32.0,  # PLACEHOLDER
    capacity: float = CAPACITY,
    column_depth: float = COLUMN_DEPTH,
    tew: float = TEW,
    rew: float = REW,
    fw: float = FW,
    margin: float = MARGIN,
    cn_constants: CurveNumberConstants = CN_CONSTANTS,
):
    """Run CN runoff -> surface layer -> column water balance over ``specs``."""
    dates = [START + datetime.timedelta(days=i) for i in range(len(specs))]

    runoff_inputs = [
        RunoffDayInput(
            date=d,
            precipitation=PrecipitationValue(value=s["p"], unit=PRECIPITATION_UNIT),
            curve_number=s["cn"],
        )
        for d, s in zip(dates, specs)
    ]
    runoff_results = run_runoff(
        runoff_inputs,
        constants=cn_constants,
        unit_guard_reason=UNIT_GUARD_REASON,
    )

    surface_inputs = [
        SurfaceDayInput(
            date=d,
            precipitation=s["p"],
            runoff=q_res.runoff,
            reference_evapotranspiration=s["et0"],
            basal_crop_coefficient=s["kcb"],
            cover_fraction=s["fc"],
            climate_adjusted_upper_limit=s.get("climate", CLIMATE),
        )
        for d, s, q_res in zip(dates, specs, runoff_results)
    ]
    surface_results = run_surface_layer(
        surface_inputs,
        initial_depletion=initial_depletion,
        total_evaporable_water=tew,
        readily_evaporable_water=rew,
        wetted_fraction=fw,
        margin_above_basal=margin,
    )

    balance_inputs = [
        BalanceDayInput(
            date=d,
            precipitation=s["p"],
            runoff=q_res.runoff,
            reference_evapotranspiration=s["et0"],
            evaporation_coefficient=e_res.evaporation_coefficient,
            crop=s["crop"],
        )
        for d, s, q_res, e_res in zip(dates, specs, runoff_results, surface_results)
    ]
    balance_results = run_balance(
        balance_inputs,
        initial_storage=initial_storage,
        capacity=capacity,
        column_depth=column_depth,
    )
    return runoff_results, surface_results, balance_results


def _column_residual(r: BalanceDayResult) -> tuple[float, float]:
    change = r.storage_end - r.storage_start
    net = r.precipitation - r.runoff - r.evaporation - r.transpiration - r.drainage
    scale = (
        r.storage_start
        + r.storage_end
        + sum(getattr(r, name) for name in BALANCE_FLOWS)
    )
    return change - net, scale


def _surface_residual(r: SurfaceDayResult, tew: float = TEW) -> tuple[float, float]:
    change = r.depletion_end - r.depletion_start
    net = -r.infiltration + r.deep_percolation + r.evaporation_from_exposed_fraction
    scale = max(
        tew,
        abs(r.infiltration),
        r.deep_percolation,
        r.evaporation_from_exposed_fraction,
    )
    return change - net, scale


def _mixed_specs(n_days: int, seed: int) -> list[dict]:
    """Generate a synthetic PLACEHOLDER sequence crossing every flow regime."""
    rng = random.Random(seed)
    specs = []
    root = 0.5  # PLACEHOLDER
    for i in range(n_days):
        in_crop = (i // 20) % 2 == 1  # PLACEHOLDER 20-day fallow / 20-day crop
        if in_crop:
            root = min(COLUMN_DEPTH, root + 0.1)  # PLACEHOLDER
            crop = _crop(
                root_depth=root,
                kcb=rng.uniform(0.2, 2.0),  # PLACEHOLDER
                fraction=rng.choice([0.0, 0.4, 1.0]),  # PLACEHOLDER
            )
            kcb = crop.transpiration_coefficient
            fc = rng.choice([0.0, 0.5, 1.0])  # PLACEHOLDER
        else:
            root = 0.5  # PLACEHOLDER
            crop = None
            kcb = 0.25  # PLACEHOLDER
            fc = 0.0  # PLACEHOLDER

        roll = rng.random()
        if roll < 0.55:
            p = 0.0
            cn = rng.uniform(2.0, CN_TOP)  # PLACEHOLDER
            et0 = rng.uniform(0.0, 35.0)  # PLACEHOLDER
        elif roll < 0.85:
            p = rng.uniform(0.5, 25.0)  # PLACEHOLDER moderate rain
            cn = rng.uniform(2.0, CN_TOP)  # PLACEHOLDER
            et0 = rng.uniform(0.0, 15.0)  # PLACEHOLDER
        else:
            p = rng.uniform(150.0, 300.0)  # PLACEHOLDER storm overfilling capacity
            cn = rng.uniform(0.5, 2.0)  # PLACEHOLDER low CN so storm infiltrates
            et0 = rng.uniform(0.0, 2.0)  # PLACEHOLDER

        specs.append(
            {
                "p": p,
                "cn": cn,
                "et0": et0,
                "kcb": kcb,
                "fc": fc,
                "climate": rng.uniform(1.0, 4.0),  # PLACEHOLDER
                "crop": crop,
            }
        )
    return specs


# ---------------------------------------------------------------------------
# 1. Exact daily column balance: ending_storage - starting_storage == P - Q - E - T - D


def test_exact_binary_daily_column_balance_across_multi_day_sequence():
    # Binary-exact PLACEHOLDER inputs so floating-point rounding is zero.
    days = [
        BalanceDayInput(
            date=START + datetime.timedelta(days=0),
            precipitation=10.0,
            runoff=2.0,
            reference_evapotranspiration=4.0,
            evaporation_coefficient=0.5,
            crop=_crop(root_depth=2.0, kcb=1.0, fraction=0.5),
        ),
        BalanceDayInput(
            date=START + datetime.timedelta(days=1),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=8.0,
            evaporation_coefficient=0.25,
            crop=_crop(root_depth=4.0, kcb=0.5, fraction=0.5),
        ),
        BalanceDayInput(
            date=START + datetime.timedelta(days=2),
            precipitation=50.0,
            runoff=10.0,
            reference_evapotranspiration=4.0,
            evaporation_coefficient=0.5,
            crop=None,
        ),
        BalanceDayInput(
            date=START + datetime.timedelta(days=3),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=200.0,
            evaporation_coefficient=0.5,
            crop=_crop(root_depth=2.0, kcb=1.0, fraction=0.5),
        ),
    ]
    results = run_balance(
        days,
        initial_storage=32.0,  # PLACEHOLDER
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )

    for r in results:
        assert r.storage_end - r.storage_start == (
            r.precipitation - r.runoff - r.evaporation - r.transpiration - r.drainage
        )
        assert 0.0 <= r.storage_start <= CAPACITY
        assert 0.0 <= r.storage_end <= CAPACITY

    for prev, nxt in zip(results, results[1:]):
        assert nxt.storage_start == prev.storage_end

    # Day 2 overflows and drains; Day 3 empties the column via evaporation.
    assert results[2].drainage > 0.0
    assert results[2].storage_end == CAPACITY
    assert results[3].storage_end == 0.0
    assert results[3].evaporation_shortfall > 0.0


@pytest.mark.parametrize("seed", [11, 23, 37])
def test_coupled_multi_day_daily_and_cumulative_column_balance(seed):
    specs = _mixed_specs(200, seed=seed)
    runoff_res, surface_res, balance_res = _coupled_run(
        specs, initial_depletion=4.0, initial_storage=24.0
    )

    assert len(balance_res) == len(specs)
    # Verify every regime was actually exercised.
    assert any(r.drainage > 0.0 for r in balance_res)
    assert any(r.storage_end == 0.0 for r in balance_res)
    assert any(
        not isinstance(r.stress_coefficient, Missing)
        and 0.0 < r.stress_coefficient < 1.0
        for r in balance_res
    )
    assert any(isinstance(r.stress_coefficient, Missing) for r in balance_res)

    for prev, nxt in zip(balance_res, balance_res[1:]):
        assert nxt.storage_start == prev.storage_end

    for r, q_r, e_r in zip(balance_res, runoff_res, surface_res):
        residual, scale = _column_residual(r)
        assert abs(residual) <= 16 * EPS * max(scale, 1.0), r.date
        assert 0.0 <= r.storage_start <= CAPACITY
        assert 0.0 <= r.storage_end <= CAPACITY
        for flow in BALANCE_FLOWS:
            assert getattr(r, flow) >= 0.0
        # Runoff from CN is in [0, P], so neither module records runoff shortfall.
        assert q_r.runoff == r.runoff
        assert r.runoff_shortfall == 0.0
        assert e_r.runoff_shortfall == 0.0

    net_cumulative = sum(
        r.precipitation - r.runoff - r.evaporation - r.transpiration - r.drainage
        for r in balance_res
    )
    cumulative_scale = sum(
        r.storage_start + r.storage_end + sum(getattr(r, f) for f in BALANCE_FLOWS)
        for r in balance_res
    )
    assert balance_res[-1].storage_end - balance_res[0].storage_start == pytest.approx(
        net_cumulative, abs=32 * EPS * max(cumulative_scale, 1.0), rel=0.0
    )


# ---------------------------------------------------------------------------
# 2. Zero drainage below capacity


def test_zero_drainage_below_and_at_capacity_across_multiple_days():
    # Days stay below capacity, hit capacity exactly, and stay below capacity
    # when outflows consume inflow above capacity before drainage runs.
    days = [
        # Start 20 + (10 - 0) - 2 = 28 < 64 -> D = 0
        BalanceDayInput(
            date=START + datetime.timedelta(days=0),
            precipitation=10.0,
            runoff=0.0,
            reference_evapotranspiration=4.0,
            evaporation_coefficient=0.5,
            crop=None,
        ),
        # Start 28 + (40 - 4) - 0 = 64 == capacity -> D = 0
        BalanceDayInput(
            date=START + datetime.timedelta(days=1),
            precipitation=40.0,
            runoff=4.0,
            reference_evapotranspiration=0.0,
            evaporation_coefficient=0.5,
            crop=None,
        ),
        # Start 64 + 8 = 72 > capacity before outflows, but E=4 + T=4 = 8
        # brings after_outflow back to 64 == capacity -> D = 0
        BalanceDayInput(
            date=START + datetime.timedelta(days=2),
            precipitation=8.0,
            runoff=0.0,
            reference_evapotranspiration=4.0,
            evaporation_coefficient=1.0,
            crop=_crop(root_depth=COLUMN_DEPTH, kcb=1.0, fraction=1.0),
        ),
        # Start 64 + 12 = 76 > capacity before outflows; E=6 + T=10 = 16
        # brings after_outflow to 60 < capacity -> D = 0
        BalanceDayInput(
            date=START + datetime.timedelta(days=3),
            precipitation=12.0,
            runoff=0.0,
            reference_evapotranspiration=10.0,
            evaporation_coefficient=0.6,
            crop=_crop(root_depth=COLUMN_DEPTH, kcb=1.0, fraction=1.0),
        ),
    ]
    results = run_balance(
        days,
        initial_storage=20.0,  # PLACEHOLDER
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )

    assert [r.drainage for r in results] == [0.0, 0.0, 0.0, 0.0]
    assert [r.storage_end for r in results] == [28.0, CAPACITY, CAPACITY, 60.0]

    # One additional day overflowing capacity after outflows drains exact excess.
    overflow = balance_step(
        results[-1].storage_end,
        BalanceDayInput(
            date=START + datetime.timedelta(days=4),
            precipitation=15.0,
            runoff=1.0,
            reference_evapotranspiration=2.0,
            evaporation_coefficient=0.5,
            crop=None,
        ),
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )
    assert overflow.storage_end == CAPACITY
    assert overflow.drainage == 9.0
    assert overflow.storage_end - overflow.storage_start == (
        overflow.precipitation
        - overflow.runoff
        - overflow.evaporation
        - overflow.transpiration
        - overflow.drainage
    )


# ---------------------------------------------------------------------------
# 3. Ks bounds [0, 1] and monotonicity


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.99, 1.0])
def test_stress_coefficient_bounds_and_monotonicity_across_depletion(fraction):
    taw = 40.0  # PLACEHOLDER
    raw = fraction * taw
    depletions = [taw * k / 200 for k in range(201)]
    values = [stress_coefficient(d, taw, fraction) for d in depletions]

    assert all(0.0 <= ks <= 1.0 for ks in values)
    assert all(b <= a for a, b in zip(values, values[1:]))

    for d, ks in zip(depletions, values):
        if d <= raw:
            assert ks == 1.0

    if fraction < 1.0:
        assert values[-1] == 0.0
        above_raw = [ks for d, ks in zip(depletions, values) if d > raw]
        assert all(b < a for a, b in zip(above_raw, above_raw[1:]))
    else:
        assert values[-1] == 1.0


def test_stress_coefficient_monotonic_in_readily_available_fraction():
    taw = 40.0  # PLACEHOLDER
    fractions = [0.0, 0.125, 0.25, 0.5, 0.75, 1.0]
    for k in range(41):
        depletion = taw * k / 40
        values = [stress_coefficient(depletion, taw, f) for f in fractions]
        assert all(0.0 <= ks <= 1.0 for ks in values)
        assert all(a <= b for a, b in zip(values, values[1:]))


def test_multi_day_drying_and_rewetting_stress_coefficient_monotonicity():
    crop = _crop(root_depth=2.0, kcb=1.0, fraction=0.25)
    # 15 dry days followed by a wet day and a fallow day.
    days = [
        BalanceDayInput(
            date=START + datetime.timedelta(days=i),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=6.0,
            evaporation_coefficient=0.5,
            crop=crop,
        )
        for i in range(15)
    ]
    days.append(
        BalanceDayInput(
            date=START + datetime.timedelta(days=15),
            precipitation=50.0,
            runoff=0.0,
            reference_evapotranspiration=2.0,
            evaporation_coefficient=0.5,
            crop=crop,
        )
    )
    days.append(
        BalanceDayInput(
            date=START + datetime.timedelta(days=16),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=2.0,
            evaporation_coefficient=0.5,
            crop=crop,
        )
    )
    days.append(
        BalanceDayInput(
            date=START + datetime.timedelta(days=17),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=2.0,
            evaporation_coefficient=0.5,
            crop=None,
        )
    )

    results = run_balance(
        days,
        initial_storage=CAPACITY,
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )

    dry_ks = [r.stress_coefficient for r in results[:15]]
    assert all(0.0 <= ks <= 1.0 for ks in dry_ks)
    assert dry_ks[0] == 1.0
    assert dry_ks[-1] < 1.0
    assert all(b <= a for a, b in zip(dry_ks, dry_ks[1:]))

    # Rewetting raises storage on day 15, so day 16's Ks increases back toward 1.
    assert results[15].storage_end > results[15].storage_start
    assert results[16].stress_coefficient >= results[15].stress_coefficient
    assert results[16].stress_coefficient == 1.0
    assert isinstance(results[17].stress_coefficient, Missing)
    assert results[17].stress_coefficient.reason == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# 4. Surface layer conservation


@pytest.mark.parametrize("initial_depletion", [0.0, REW, TEW])
def test_surface_layer_multi_day_conservation_and_bounds(initial_depletion):
    rng = random.Random(42)
    days = []
    for i in range(90):
        wet = rng.random() < 0.25
        p = rng.uniform(0.0, 80.0) if wet else 0.0  # PLACEHOLDER
        # Include runoff > p on some days to verify surface layer limits runoff to p.
        q = rng.choice([0.0, 0.3 * p, p + 5.0])  # PLACEHOLDER
        days.append(
            SurfaceDayInput(
                date=START + datetime.timedelta(days=i),
                precipitation=p,
                runoff=q,
                reference_evapotranspiration=rng.uniform(0.0, 15.0),  # PLACEHOLDER
                basal_crop_coefficient=rng.uniform(0.0, 2.0),  # PLACEHOLDER
                cover_fraction=rng.choice([0.0, 0.4, 1.0]),  # PLACEHOLDER
                climate_adjusted_upper_limit=rng.uniform(1.0, 3.5),  # PLACEHOLDER
            )
        )

    results = run_surface_layer(
        days,
        initial_depletion=initial_depletion,
        total_evaporable_water=TEW,
        readily_evaporable_water=REW,
        wetted_fraction=FW,
        margin_above_basal=MARGIN,
    )

    # Confirm stage 1, stage 2, deep percolation, evaporation shortfall, and full cover all occur.
    assert any(r.reduction_coefficient == 1.0 for r in results)
    assert any(0.0 <= r.reduction_coefficient < 1.0 for r in results)
    assert any(r.deep_percolation > 0.0 for r in results)
    assert any(r.evaporation_shortfall > 0.0 for r in results)
    assert any(r.exposed_and_wetted_fraction == 0.0 for r in results)

    for prev, nxt in zip(results, results[1:]):
        assert nxt.depletion_start == prev.depletion_end

    for r in results:
        residual, scale = _surface_residual(r)
        assert abs(residual) <= 16 * EPS * max(scale, 1.0), r.date
        assert 0.0 <= r.depletion_start <= TEW
        assert 0.0 <= r.depletion_end <= TEW
        assert 0.0 <= r.reduction_coefficient <= 1.0
        assert 0.0 <= r.evaporation_coefficient <= r.upper_limit
        assert r.infiltration == r.precipitation - r.runoff
        assert r.runoff <= r.precipitation
        assert r.deep_percolation >= 0.0
        if r.infiltration <= r.depletion_start:
            assert r.deep_percolation == 0.0
        else:
            assert r.deep_percolation == pytest.approx(
                r.infiltration - r.depletion_start, abs=8 * EPS * max(scale, 1.0)
            )
        assert r.evaporation + r.evaporation_shortfall == pytest.approx(
            r.evaporation_demanded, abs=8 * EPS * max(scale, 1.0)
        )
        if r.exposed_and_wetted_fraction == 0.0:
            assert r.evaporation_coefficient == 0.0
            assert r.evaporation == 0.0
            assert r.evaporation_from_exposed_fraction == 0.0

    cumulative_change = results[-1].depletion_end - results[0].depletion_start
    cumulative_net = sum(
        -r.infiltration + r.deep_percolation + r.evaporation_from_exposed_fraction
        for r in results
    )
    cumulative_scale = sum(
        TEW + abs(r.infiltration) + r.deep_percolation + r.evaporation_from_exposed_fraction
        for r in results
    )
    assert cumulative_change == pytest.approx(
        cumulative_net, abs=32 * EPS * max(cumulative_scale, 1.0), rel=0.0
    )


# ---------------------------------------------------------------------------
# 5. CN runoff bounded [0, P]


@pytest.mark.parametrize("ia_ratio", [0.0, 0.25, 0.5, 2.0])
def test_cn_runoff_bounded_zero_to_precipitation_across_regimes(ia_ratio):
    constants = dataclasses.replace(CN_CONSTANTS, initial_abstraction_ratio=ia_ratio)
    curves = [CN_TOP * k / 40 for k in range(1, 41)]
    precipitations = [0.0, 1e-9, 0.5, 2.0, 10.0, 50.0, 500.0, 1e6]

    for cn in curves:
        s = potential_retention(cn, constants=constants)
        ia = initial_abstraction(s, constants=constants)
        assert isinstance(s, float) and s >= 0.0
        assert isinstance(ia, float) and ia >= 0.0

        day_inputs = [
            RunoffDayInput(
                date=START + datetime.timedelta(days=i),
                precipitation=PrecipitationValue(value=p, unit=PRECIPITATION_UNIT),
                curve_number=cn,
            )
            for i, p in enumerate(precipitations)
        ]
        results = run_runoff(
            day_inputs, constants=constants, unit_guard_reason=UNIT_GUARD_REASON
        )
        for p, res in zip(precipitations, results):
            q = res.runoff
            assert isinstance(q, float)
            assert 0.0 <= q <= p
            if p <= ia:
                assert q == 0.0
            if s == 0.0:
                assert q == pytest.approx(p) and q <= p
            assert q == runoff_depth(p, cn, constants=constants)


def test_cn_runoff_monotonic_in_precipitation_and_curve_number():
    precipitations = [0.0, 1.0, 5.0, 15.0, 40.0, 120.0]
    curves = [5.0, 10.0, 20.0, 30.0, CN_TOP]

    for cn in curves:
        by_p = [runoff_depth(p, cn, constants=CN_CONSTANTS) for p in precipitations]
        assert all(0.0 <= q <= p for q, p in zip(by_p, precipitations))
        assert all(a <= b for a, b in zip(by_p, by_p[1:]))

    for p in precipitations:
        by_cn = [runoff_depth(p, cn, constants=CN_CONSTANTS) for cn in curves]
        assert all(0.0 <= q <= p for q in by_cn)
        assert all(a <= b for a, b in zip(by_cn, by_cn[1:]))


# ---------------------------------------------------------------------------
# 6. One-day missing input latching cleanly across subsequent days


@pytest.mark.parametrize(
    "field",
    [
        "precipitation",
        "runoff",
        "reference_evapotranspiration",
        "evaporation_coefficient",
        "crop",
    ],
)
def test_one_day_missing_input_latches_across_subsequent_balance_days(field):
    base_days = [
        BalanceDayInput(
            date=START + datetime.timedelta(days=i),
            precipitation=6.0,
            runoff=1.0,
            reference_evapotranspiration=4.0,
            evaporation_coefficient=0.5,
            crop=_crop(),
        )
        for i in range(8)
    ]
    baseline = run_balance(
        base_days,
        initial_storage=30.0,  # PLACEHOLDER
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )

    gap_index = 3
    gap_reason = "NO_COVERAGE"
    perturbed = list(base_days)
    perturbed[gap_index] = dataclasses.replace(
        perturbed[gap_index],
        **{field: Missing(reason=gap_reason, detail="PLACEHOLDER gap")},
    )
    results = run_balance(
        perturbed,
        initial_storage=30.0,  # PLACEHOLDER
        capacity=CAPACITY,
        column_depth=COLUMN_DEPTH,
    )

    assert len(results) == len(base_days)
    assert results[:gap_index] == baseline[:gap_index]
    gap_date_str = perturbed[gap_index].date.isoformat()

    for r in results[gap_index:]:
        for qty_name in BALANCE_RESULT_QUANTITIES:
            val = getattr(r, qty_name)
            assert isinstance(val, Missing), (r.date, qty_name)
            assert val.reason == "MISSING_INPUT"
            assert val != 0.0
            assert gap_reason in val.detail
            assert gap_date_str in val.detail
            assert field in val.detail


@pytest.mark.parametrize(
    "field",
    [
        "precipitation",
        "runoff",
        "reference_evapotranspiration",
        "basal_crop_coefficient",
        "cover_fraction",
        "climate_adjusted_upper_limit",
    ],
)
def test_one_day_missing_input_latches_across_subsequent_surface_layer_days(field):
    base_days = [
        SurfaceDayInput(
            date=START + datetime.timedelta(days=i),
            precipitation=4.0 if i % 2 == 0 else 0.0,
            runoff=0.5 if i % 2 == 0 else 0.0,
            reference_evapotranspiration=4.0,
            basal_crop_coefficient=1.25,
            cover_fraction=0.25,
            climate_adjusted_upper_limit=CLIMATE,
        )
        for i in range(8)
    ]
    baseline = run_surface_layer(
        base_days,
        initial_depletion=4.0,  # PLACEHOLDER
        total_evaporable_water=TEW,
        readily_evaporable_water=REW,
        wetted_fraction=FW,
        margin_above_basal=MARGIN,
    )

    gap_index = 2
    gap_reason = "SOURCE_UNAVAILABLE"
    perturbed = list(base_days)
    perturbed[gap_index] = dataclasses.replace(
        perturbed[gap_index],
        **{field: Missing(reason=gap_reason)},
    )
    results = run_surface_layer(
        perturbed,
        initial_depletion=4.0,  # PLACEHOLDER
        total_evaporable_water=TEW,
        readily_evaporable_water=REW,
        wetted_fraction=FW,
        margin_above_basal=MARGIN,
    )

    assert len(results) == len(base_days)
    assert results[:gap_index] == baseline[:gap_index]
    gap_date_str = perturbed[gap_index].date.isoformat()

    for r in results[gap_index:]:
        for qty_name in SURFACE_RESULT_QUANTITIES:
            val = getattr(r, qty_name)
            assert isinstance(val, Missing), (r.date, qty_name)
            assert val.reason == "MISSING_INPUT"
            assert val != 0.0
            assert gap_reason in val.detail
            assert gap_date_str in val.detail
            assert field in val.detail


@pytest.mark.parametrize("missing_key", ["cn", "p"])
def test_coupled_pipeline_latches_one_day_missing_input_cleanly(missing_key):
    base_specs = _mixed_specs(10, seed=7)
    # Ensure day 0..3 have numeric values so pre-gap days compute cleanly.
    for s in base_specs:
        s["p"] = 10.0  # PLACEHOLDER
        s["cn"] = 25.0  # PLACEHOLDER
        s["et0"] = 4.0  # PLACEHOLDER

    base_q, base_e, base_b = _coupled_run(base_specs)

    gap_index = 4
    gap_reason = "NO_COVERAGE"
    perturbed_specs = [dict(s) for s in base_specs]
    perturbed_specs[gap_index][missing_key] = Missing(reason=gap_reason)

    q_res, e_res, b_res = _coupled_run(perturbed_specs)

    # Stateless CN runoff is missing only on the gap day and computes afterwards.
    assert q_res[:gap_index] == base_q[:gap_index]
    assert isinstance(q_res[gap_index].runoff, Missing)
    assert q_res[gap_index].runoff.reason == "MISSING_INPUT"
    assert q_res[gap_index + 1 :] == base_q[gap_index + 1 :]

    # Stateful surface layer and column balance match before gap, then latch
    # MISSING_INPUT across every subsequent day even after CN runoff resumes.
    assert e_res[:gap_index] == base_e[:gap_index]
    assert b_res[:gap_index] == base_b[:gap_index]

    gap_date_str = (START + datetime.timedelta(days=gap_index)).isoformat()
    for er, br in zip(e_res[gap_index:], b_res[gap_index:]):
        for qty_name in SURFACE_RESULT_QUANTITIES:
            val = getattr(er, qty_name)
            assert isinstance(val, Missing)
            assert val.reason == "MISSING_INPUT"
            assert gap_date_str in val.detail
        for qty_name in BALANCE_RESULT_QUANTITIES:
            val = getattr(br, qty_name)
            assert isinstance(val, Missing)
            assert val.reason == "MISSING_INPUT"
            assert gap_date_str in val.detail
