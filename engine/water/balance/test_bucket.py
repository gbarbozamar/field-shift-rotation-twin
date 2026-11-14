"""Acceptance test of engine/water/balance/ (PROPOSED cases, see README.md).

Every number in this file is a PLACEHOLDER chosen to exercise the code. None
is a real capacity, coefficient, root depth, fraction or climate value, and
none comes from FAO-56 or any other source. The checks are structural (mass
closure, bounds, invariants, missing values); the numeric criteria of H7 and
H8 and the reference case H1 are skipped until people supply them.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime
import math
import random
import sys
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water.balance import (
    RESULT_QUANTITIES,
    CropDay,
    DayInput,
    DayResult,
    run_balance,
    step,
    stress_coefficient,
)

# PLACEHOLDER values, plainly not real. Depths of water and lengths of soil
# carry no unit here.
CAPACITY = 50.0  # PLACEHOLDER
COLUMN_DEPTH = 4.0  # PLACEHOLDER
FRACTION = 0.25  # PLACEHOLDER
KCB = 2.0  # PLACEHOLDER
KE = 0.5  # PLACEHOLDER
START = datetime.date(2001, 1, 1)  # PLACEHOLDER first day
FLOWS = ("precipitation", "runoff", "evaporation", "transpiration", "drainage")
EPS = sys.float_info.epsilon


def crop(root_depth: float = 2.0, kcb: float = KCB, fraction: float = FRACTION):
    return CropDay(
        transpiration_coefficient=kcb,
        root_depth=root_depth,
        readily_available_fraction=fraction,
    )


def day(
    offset: int = 0,
    *,
    p: float | Missing = 0.0,
    q: float | Missing = 0.0,
    et0: float | Missing = 0.0,
    ke: float | Missing = KE,
    crop_day: CropDay | None | Missing = None,
) -> DayInput:
    return DayInput(
        date=START + datetime.timedelta(days=offset),
        precipitation=p,
        runoff=q,
        reference_evapotranspiration=et0,
        evaporation_coefficient=ke,
        crop=crop_day,
    )


def one(storage: float | Missing, d: DayInput, **kw) -> DayResult:
    return step(
        storage,
        d,
        capacity=kw.get("capacity", CAPACITY),
        column_depth=kw.get("column_depth", COLUMN_DEPTH),
    )


def run(days, initial: float | Missing = 20.0, **kw) -> list[DayResult]:
    return run_balance(
        days,
        initial_storage=initial,
        capacity=kw.get("capacity", CAPACITY),
        column_depth=kw.get("column_depth", COLUMN_DEPTH),
    )


def placeholder_series(n_days: int, seed: int) -> list[DayInput]:
    """A long PLACEHOLDER series: crops and fallow in turn, dry and wet days,
    storms that overfill the column, demands larger than the water there,
    runoff that sometimes asks for more than the precipitation."""
    rng = random.Random(seed)
    days = []
    season_length = 0
    root = 0.0
    in_crop = False
    for i in range(n_days):
        if season_length == 0:
            in_crop = not in_crop
            season_length = rng.randint(30, 200)
            root = rng.uniform(0.1, 1.0)
        season_length -= 1
        if in_crop:
            root = min(COLUMN_DEPTH, root + rng.uniform(0.0, 0.05))
            c = crop(
                root_depth=root,
                kcb=rng.uniform(0.0, 3.0),
                fraction=rng.choice([0.0, 1.0, rng.random()]),
            )
        else:
            c = None
        wet = rng.random()
        p = 0.0 if wet < 0.5 else rng.uniform(0.0, 3.0 * CAPACITY * wet**8)
        q = rng.choice([0.0, rng.uniform(0.0, p + 1.0)])
        days.append(
            day(
                i,
                p=p,
                q=q,
                et0=rng.uniform(0.0, 10.0),
                ke=rng.uniform(0.0, 1.5),
                crop_day=c,
            )
        )
    return days


def closure_residual(r: DayResult) -> tuple[float, float]:
    """Residual of the daily mass balance and the scale of its terms."""
    change = r.storage_end - r.storage_start
    net = r.precipitation - r.runoff - r.evaporation - r.transpiration - r.drainage
    scale = r.storage_start + r.storage_end + sum(getattr(r, f) for f in FLOWS)
    return change - net, scale


LONG = placeholder_series(20 * 366, seed=1)  # PLACEHOLDER series


# --- Mass closure (H7 structure) --------------------------------------------


def test_mass_closure_every_day_on_a_long_series():
    results = run(LONG)
    assert len(results) == len(LONG)
    for r in results:
        residual, scale = closure_residual(r)
        assert abs(residual) <= 16 * EPS * max(scale, 1.0), r.date


def test_the_long_series_reaches_every_branch_of_the_step():
    # So that closure and bounds are checked where they can break.
    results = run(LONG)
    assert any(r.drainage > 0.0 for r in results)
    assert any(r.storage_end == 0.0 for r in results)
    assert any(r.runoff_shortfall > 0.0 for r in results)
    assert any(r.evaporation_shortfall > 0.0 for r in results)
    stressed = [r for r in results if not isinstance(r.stress_coefficient, Missing)]
    assert any(0.0 < r.stress_coefficient < 1.0 for r in stressed)
    assert any(r.transpiration_shortfall > 0.0 for r in stressed)
    assert any(isinstance(r.stress_coefficient, Missing) for r in results)


@pytest.mark.parametrize("seed", [2, 3, 4])
@pytest.mark.parametrize("initial", [0.0, CAPACITY])
def test_mass_closure_from_other_initial_states_and_series(seed, initial):
    for r in run(placeholder_series(3 * 366, seed), initial=initial):
        residual, scale = closure_residual(r)
        assert abs(residual) <= 16 * EPS * max(scale, 1.0), r.date


def test_balance_is_never_reset_between_days_crops_or_years():
    results = run(LONG)
    for before, after in zip(results, results[1:]):
        assert after.storage_start == before.storage_end
    # Running the record in two parts, the second starting from the storage
    # the first ended with, gives the same days as one run.
    cut = 3 * 365 + 17
    first = run(LONG[:cut])
    second = run(LONG[cut:], initial=first[-1].storage_end)
    assert first + second == results


# --- Bounds and limited outflows (D44 mass rule) ----------------------------


def test_storage_never_below_zero_nor_above_capacity():
    for r in run(LONG):
        assert 0.0 <= r.storage_start <= CAPACITY
        assert 0.0 <= r.storage_end <= CAPACITY
        for f in FLOWS:
            assert getattr(r, f) >= 0.0


def test_evaporation_asking_more_than_there_is_is_limited_and_recorded():
    r = one(3.0, day(p=1.0, et0=40.0, ke=1.0))
    assert r.evaporation == 4.0
    assert r.evaporation_shortfall == 36.0
    assert r.storage_end == 0.0
    assert r.evaporation_demanded == r.evaporation + r.evaporation_shortfall


def test_transpiration_is_limited_to_the_water_of_the_root_zone():
    # Root zone is half the column; the column holds 10 after evaporation.
    c = crop(root_depth=COLUMN_DEPTH / 2, fraction=1.0)
    r = one(10.0, day(et0=100.0, ke=0.0, crop_day=c))
    assert r.stress_coefficient == 1.0
    assert r.transpiration == 5.0
    assert r.transpiration_shortfall == r.transpiration_demanded - 5.0
    assert r.storage_end == 5.0


def test_runoff_asking_more_than_the_precipitation_is_limited_and_recorded():
    r = one(10.0, day(p=2.0, q=5.0))
    assert r.runoff == 2.0
    assert r.runoff_shortfall == 3.0
    assert r.storage_end == 10.0


def test_flows_supplied_in_full_have_no_shortfall():
    r = one(30.0, day(p=2.0, q=1.0, et0=1.0, crop_day=crop()))
    assert r.runoff_shortfall == 0.0
    assert r.evaporation_shortfall == 0.0
    assert r.transpiration_shortfall == 0.0


def test_limited_flows_on_the_long_series_add_up():
    for r in run(LONG):
        assert r.runoff_shortfall >= 0.0 and r.evaporation_shortfall >= 0.0
        assert r.evaporation + r.evaporation_shortfall == pytest.approx(
            r.evaporation_demanded, rel=4 * EPS, abs=4 * EPS
        )
        if not isinstance(r.transpiration_shortfall, Missing):
            assert r.transpiration_shortfall >= 0.0


# --- Drainage ---------------------------------------------------------------


def test_water_above_capacity_leaves_as_drainage():
    r = one(45.0, day(p=20.0))
    assert r.drainage == 15.0
    assert r.storage_end == CAPACITY


def test_no_drainage_below_capacity():
    r = one(10.0, day(p=20.0))
    assert r.drainage == 0.0
    assert r.storage_end == 30.0


def test_drainage_comes_after_the_outflows_of_the_day():
    r = one(45.0, day(p=20.0, et0=4.0, ke=1.0))
    assert r.evaporation == 4.0
    assert r.drainage == 11.0
    assert r.storage_end == CAPACITY


# --- Days with no crop ------------------------------------------------------


def test_a_day_with_no_crop_has_no_transpiration_and_keeps_evaporation():
    r = one(20.0, day(et0=4.0, ke=KE, crop_day=None))
    assert r.transpiration == 0.0
    assert r.evaporation == KE * 4.0
    for name in (
        "transpiration_demanded",
        "root_zone_depletion",
        "stress_coefficient",
        "transpiration_shortfall",
    ):
        value = getattr(r, name)
        assert isinstance(value, Missing) and value.reason == "NOT_APPLICABLE"


# --- Root zone, sowing and harvest (H8 structure) ---------------------------


def test_growing_the_root_zone_adds_no_water():
    days = [day(i, crop_day=crop(root_depth=0.5 + i)) for i in range(4)]
    for r in run(days, initial=17.0):
        assert r.storage_start == r.storage_end == 17.0
        assert all(getattr(r, f) == 0.0 for f in FLOWS)


def test_growing_the_root_zone_gives_access_to_water_already_there():
    shallow = one(10.0, day(et0=100.0, ke=0.0, crop_day=crop(1.0, fraction=1.0)))
    deep = one(10.0, day(et0=100.0, ke=0.0, crop_day=crop(3.0, fraction=1.0)))
    assert shallow.storage_start == deep.storage_start
    assert shallow.transpiration == 10.0 * 1.0 / COLUMN_DEPTH
    assert deep.transpiration == 10.0 * 3.0 / COLUMN_DEPTH
    assert deep.transpiration > shallow.transpiration


def test_sowing_and_harvest_keep_the_stored_water():
    plan = [None, None, crop(0.5), crop(1.0), crop(1.5), None, None, crop(0.7)]
    days = [day(i, crop_day=c) for i, c in enumerate(plan)]
    results = run(days, initial=33.0)
    assert [r.storage_end for r in results] == [33.0] * len(plan)


# --- Stress coefficient (form PROPOSED, source CITATION NEEDED) ---------------


def test_actual_transpiration_is_demanded_times_stress_when_water_suffices():
    for start in (50.0, 40.0, 20.0, 5.0):
        r = one(start, day(et0=0.1, ke=0.0, crop_day=crop(2.0, fraction=0.5)))
        assert r.transpiration_shortfall == 0.0
        assert r.transpiration == r.stress_coefficient * r.transpiration_demanded


def test_actual_transpiration_is_demanded_times_stress_on_the_long_series():
    for r in run(LONG):
        if isinstance(r.stress_coefficient, Missing):
            continue
        asked = r.stress_coefficient * r.transpiration_demanded
        assert r.transpiration + r.transpiration_shortfall == pytest.approx(
            asked, rel=4 * EPS, abs=4 * EPS
        )
        if r.transpiration_shortfall == 0.0:
            assert r.transpiration == asked


def test_stress_coefficient_is_one_up_to_the_readily_available_water():
    assert stress_coefficient(0.0, 10.0, 0.25) == 1.0
    assert stress_coefficient(2.5, 10.0, 0.25) == 1.0


def test_stress_coefficient_falls_linearly_to_zero_beyond_it():
    taw, fraction = 10.0, 0.25
    raw = fraction * taw
    for dr in (3.0, 5.0, 7.5, 9.0, 10.0):
        assert stress_coefficient(dr, taw, fraction) == (taw - dr) / (taw - raw)
    assert stress_coefficient(taw, taw, fraction) == 0.0


def test_stress_coefficient_is_bounded_and_does_not_rise_with_depletion():
    for fraction in (0.0, 0.25, 0.5, 1.0):
        values = [
            stress_coefficient(10.0 * k / 100, 10.0, fraction) for k in range(101)
        ]
        assert all(0.0 <= v <= 1.0 for v in values)
        assert all(a >= b for a, b in zip(values, values[1:]))


def test_stress_follows_the_depletion_of_the_root_zone_at_the_start_of_the_day():
    c = crop(root_depth=2.0, fraction=0.5)
    r = one(10.0, day(p=30.0, et0=1.0, crop_day=c))
    share = 2.0 / COLUMN_DEPTH
    assert r.root_zone_depletion == (CAPACITY - 10.0) * share
    assert r.stress_coefficient == stress_coefficient(
        (CAPACITY - 10.0) * share, CAPACITY * share, 0.5
    )


def test_stress_coefficient_on_the_long_series_stays_within_bounds():
    for r in run(LONG):
        if not isinstance(r.stress_coefficient, Missing):
            assert 0.0 <= r.stress_coefficient <= 1.0


# --- Missing in, missing out (C3.1, C3.3) -----------------------------------


@pytest.mark.parametrize(
    "field", ["p", "q", "et0", "ke", "crop_day"], ids=lambda f: f"missing-{f}"
)
def test_a_missing_input_gives_missing_outputs_that_day_and_after(field):
    gap = Missing(reason="NO_COVERAGE", detail="PLACEHOLDER gap")
    days = [day(i, p=1.0, et0=2.0, crop_day=crop()) for i in range(6)]
    values = {"p": 1.0, "et0": 2.0, "crop_day": crop()}
    values[field] = gap
    days[3] = day(3, **values)
    results = run(days)
    for r in results[:3]:
        assert all(not isinstance(getattr(r, q), Missing) for q in RESULT_QUANTITIES)
    for r in results[3:]:
        for q in RESULT_QUANTITIES:
            value = getattr(r, q)
            assert isinstance(value, Missing), (r.date, q)
            assert value.reason == "MISSING_INPUT"
            assert "NO_COVERAGE" in value.detail
            assert days[3].date.isoformat() in value.detail
    assert [r.date for r in results] == [d.date for d in days]


def test_the_detail_names_the_missing_input():
    gap = Missing(reason="SOURCE_UNAVAILABLE")
    r = one(10.0, day(p=gap, et0=gap))
    assert r.storage_end.reason == "MISSING_INPUT"
    assert "precipitation (SOURCE_UNAVAILABLE)" in r.storage_end.detail
    assert "reference_evapotranspiration (SOURCE_UNAVAILABLE)" in r.storage_end.detail


def test_a_missing_initial_storage_gives_every_day_missing():
    results = run(LONG[:30], initial=Missing(reason="NOT_DECLARED"))
    for r in results:
        for q in RESULT_QUANTITIES:
            value = getattr(r, q)
            assert isinstance(value, Missing) and value.reason == "MISSING_INPUT"
            assert "initial storage (NOT_DECLARED)" in value.detail


def test_a_missing_storage_at_the_start_of_a_step_gives_a_missing_day():
    start = Missing(reason="MISSING_INPUT", detail="PLACEHOLDER cause")
    r = one(start, day(p=1.0))
    assert all(getattr(r, q).reason == "MISSING_INPUT" for q in RESULT_QUANTITIES)
    assert "PLACEHOLDER cause" in r.drainage.detail


def test_missing_is_never_zero():
    gap = Missing(reason="NO_COVERAGE")
    days = [day(i, p=gap if i == 0 else 0.0) for i in range(3)]
    for r in run(days):
        for q in RESULT_QUANTITIES:
            assert getattr(r, q) != 0.0


# --- Caller defects raise; nothing else does --------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capacity": 0.0},
        {"capacity": -1.0},
        {"capacity": math.inf},
        {"column_depth": 0.0},
        {"column_depth": math.nan},
    ],
)
def test_invalid_column_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        run([day()], **kwargs)


@pytest.mark.parametrize("initial", [-1.0, CAPACITY + 1.0, math.nan])
def test_initial_storage_outside_the_column_raises_value_error(initial):
    with pytest.raises(ValueError):
        run([day()], initial=initial)


@pytest.mark.parametrize(
    "bad",
    [
        day(p=-1.0),
        day(q=-1.0),
        day(et0=-1.0),
        day(ke=-1.0),
        day(crop_day=crop(root_depth=0.0)),
        day(crop_day=crop(root_depth=COLUMN_DEPTH + 1.0)),
        day(crop_day=crop(fraction=1.5)),
        day(crop_day=crop(kcb=-1.0)),
    ],
)
def test_invalid_day_raises_value_error(bad):
    with pytest.raises(ValueError):
        one(10.0, bad)


@pytest.mark.parametrize(
    "bad", [day(p="1"), day(p=True), day(crop_day="crop"), "a day"]
)
def test_wrong_types_raise_type_error(bad):
    with pytest.raises(TypeError):
        one(10.0, bad)


def test_days_that_are_not_consecutive_raise_value_error():
    with pytest.raises(ValueError):
        run([day(0), day(2)])
    with pytest.raises(ValueError):
        run([day(1), day(0)])
    with pytest.raises(ValueError):
        run([day(0), day(0)])


def test_an_empty_sequence_gives_no_days():
    assert run([]) == []


# --- Purity and no parameter values in the module ---------------------------


def test_same_arguments_give_the_same_result_and_are_not_changed():
    days = list(LONG[:500])
    copy = list(days)
    assert run(days) == run(days)
    assert days == copy
    assert all(dataclasses.is_dataclass(d) for d in days)


def test_the_module_holds_no_number_other_than_zero_and_one():
    source = Path(__file__).with_name("bucket.py").read_text(encoding="utf-8")
    numbers = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}


# --- Waiting for people -----------------------------------------------------


@pytest.mark.skip(
    reason="[H1] waits for docs/VALIDATION.md H1: the public reference case, its "
    "inputs, expected values and tolerance, its source (CITATION NEEDED), "
    "transcribed and checked by two people; and for the dual-coefficient and "
    "surface-layer units the case may need"
)
def test_h1_public_reference_case():
    raise AssertionError("not defined")


@pytest.mark.skip(
    reason="[H7] numeric criterion waits for docs/VALIDATION.md H7: the definition "
    "of the closure check and its tolerance, supplied and checked by people. "
    "The structure of H7 is tested above to floating-point precision"
)
def test_h7_mass_closure_numeric_criterion():
    raise AssertionError("not defined")


@pytest.mark.skip(
    reason="[H8] numeric criteria wait for docs/VALIDATION.md H8: the list of "
    "invariants, their expected values and tolerances, supplied and checked by "
    "people. The structure of H8 (root growth, sowing, harvest, bounds) is "
    "tested above"
)
def test_h8_invariants_numeric_criteria():
    raise AssertionError("not defined")
