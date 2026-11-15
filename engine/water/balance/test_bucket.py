"""Acceptance test of engine/water/balance/ (PROPOSED cases, see README.md).

Every number in this file is a PLACEHOLDER chosen to exercise the code. None
is a real capacity, coefficient, root depth, fraction or climate value, and
none comes from FAO-56 or any other source. The checks are structural (mass
closure, bounds, invariants, missing values). The criterion of H7 decided by
D227 of issue #77 runs below (docs/VALIDATION.md H7); H8 is the list of
invariants checked by the tests docs/VALIDATION.md H8 names.

The reference case H1 is FAO-56 chapter 8, Example 37 (D228 of issue #77,
docs/VALIDATION.md H1). Its numbers are not in this file: they are read from
the signed fixture H1_FIXTURE, and the test skips while that file is absent or
unsigned, as the test of H2 does.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime
import json
import math
import random
import re
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


def h7_series():
    """The PLACEHOLDER series of the two closure tests above, each with the
    initial storage it is run from (the long one from the default of run)."""
    yield LONG, {}
    for seed in (2, 3, 4):
        for initial in (0.0, CAPACITY):
            yield placeholder_series(3 * 366, seed), {"initial": initial}


def test_h7_mass_closure_numeric_criterion():
    """[H7] as D227 of issue #77 decides it (docs/VALIDATION.md H7): the daily
    closure within 16 x machine epsilon x the scale of the day's terms, on
    every day with values, on the PLACEHOLDER series of the structural tests.
    The bound is the one those tests already use, not a value of the science.
    A day with a missing quantity (R9) is not checked and never read as zero.
    """
    for series, kwargs in h7_series():
        checked = 0
        for r in run(series, **kwargs):
            terms = (r.storage_start, r.storage_end, *(getattr(r, f) for f in FLOWS))
            if any(isinstance(t, Missing) for t in terms):
                continue
            residual, scale = closure_residual(r)
            assert abs(residual) <= 16 * EPS * max(scale, 1.0), r.date
            checked += 1
        assert checked > 0


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


# --- [H1]: FAO-56 chapter 8, Example 37 (D228) -------------------------------
#
# D228 of issue #77 (docs/VALIDATION.md H1) runs Example 37 on this one-layer
# balance with three readings, each a modelling choice the source does not
# state: Kc is read as the basal coefficient with Ke = 0; the column depth
# equals Zr, so the capacity of the column is the printed TAW; the initial
# state is the printed depletion. The stress coefficient uses the depletion at
# the start of the day (note (5) of the example; rule R7). No precipitation or
# runoff: the example has neither. The tolerance is the rule of D124: half a
# unit of the last printed digit of each value.
# https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893079768

ROOT = Path(__file__).resolve().parents[3]

# PROPOSED path of the signed fixture (amendment to brief #347).
H1_FIXTURE = ROOT / "validation" / "fixtures" / "h1_fao56_example37.json"
H1_FIXTURE_NAME = H1_FIXTURE.relative_to(ROOT).as_posix()

H1_WAITS_FOR = (
    f"[H1] waits for the signed fixture {H1_FIXTURE_NAME}: the inputs and the ten "
    "printed rows of FAO-56 chapter 8, EXAMPLE 37 (Ks, adjusted ETc and the "
    "depletion at the end of each day), with the tolerance of D228 of issue #77 "
    "(the rule of D124), transcribed and signed in checked_by by a person "
    "(D34 of issue #77)"
)

# The printed inputs the run needs, by name in the fixture.
H1_INPUTS = (
    "reference_evapotranspiration",
    "crop_coefficient",
    "root_depth",
    "depletion_fraction",
    "total_available_water",
    "initial_depletion",
)
# The printed daily values compared with the run, by name in the fixture.
H1_COLUMNS = (
    "stress_coefficient",
    "adjusted_crop_evapotranspiration",
    "depletion_end",
)

# A number as the example prints it: digits, an optional point and decimals.
PRINTED = re.compile(r"-?\d+(\.\d+)?")

# Rounding of floating-point arithmetic only, used to compare a tolerance with
# the one D124 gives. Not a tolerance of the validation protocol.
FLOAT_NOISE = 1e-12


@dataclasses.dataclass(frozen=True)
class H1Case:
    """What the H1 check needs, read from a signed fixture."""

    inputs: dict[str, float]
    rows: list[dict[str, float]]
    printed: list[dict[str, str]]
    tolerance: dict[str, float]


def h1_read_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict), f"{path.name}: the fixture is one JSON object"
    return fixture


def h1_skip_reason(path: Path) -> str | None:
    """Why the H1 check cannot run on ``path``, or ``None`` when it can."""
    if not path.is_file():
        return (
            f"{H1_WAITS_FOR}. The file is absent, so nothing is signed (no checked_by)"
        )
    signature = h1_read_fixture(path).get("checked_by")
    if not (isinstance(signature, str) and signature.strip()):
        return f"{H1_WAITS_FOR}. Not signed yet: checked_by of the file"
    return None


def h1_half_unit(printed: str) -> float:
    """D124: half a unit of the last digit the example prints."""
    assert PRINTED.fullmatch(printed), f"'{printed}' is not a printed number"
    return 0.5 * 10.0 ** -len(printed.partition(".")[2])


def _h1_number(entry: object, where: str) -> tuple[float, str | None]:
    assert isinstance(entry, dict), f"{where}: expected an object with 'value'"
    value = entry.get("value")
    assert isinstance(value, (int, float)) and not isinstance(value, bool), (
        f"{where}: 'value' must be a number"
    )
    assert math.isfinite(value), f"{where}: 'value' must be finite"
    printed = entry.get("printed")
    if printed is not None:
        assert isinstance(printed, str), f"{where}: 'printed' is text"
        assert float(printed) == value, (
            f"{where}: 'value' is not the number of 'printed'"
        )
    return float(value), printed


def h1_load_case(fixture: dict) -> H1Case:
    """The case of a signed fixture; a malformed fixture fails, it is not skipped."""
    inputs_entry = fixture.get("inputs")
    assert isinstance(inputs_entry, dict), "'inputs' must be an object"
    assert set(inputs_entry) == set(H1_INPUTS), (
        f"'inputs' must hold exactly {H1_INPUTS}"
    )
    inputs = {
        name: _h1_number(inputs_entry[name], f"inputs.{name}")[0] for name in H1_INPUTS
    }
    rows_entry = fixture.get("rows")
    assert isinstance(rows_entry, list) and rows_entry, "'rows' must be a list of days"
    rows, printed = [], []
    for index, row in enumerate(rows_entry, start=1):
        assert isinstance(row, dict), f"rows[{index}]: every row is an object"
        assert row.get("day") == index, f"rows[{index}]: days are 1, 2, 3 ... in order"
        assert set(row) == {"day", *H1_COLUMNS}, (
            f"rows[{index}]: must hold {H1_COLUMNS}"
        )
        values, texts = {}, {}
        for name in H1_COLUMNS:
            values[name], texts[name] = _h1_number(row[name], f"rows[{index}].{name}")
            assert texts[name] is not None, (
                f"rows[{index}].{name}: 'printed' is required"
            )
        rows.append(values)
        printed.append(texts)
    tolerance = fixture.get("tolerance")
    assert isinstance(tolerance, dict), "'tolerance' must be an object"
    assert set(tolerance) == set(H1_COLUMNS), (
        f"'tolerance' needs one entry per {H1_COLUMNS}"
    )
    return H1Case(inputs=inputs, rows=rows, printed=printed, tolerance=tolerance)


def h1_tolerance_problems(case: H1Case) -> list[str]:
    """Each tolerance of the fixture that is not the rule of D124 for a value."""
    problems = []
    for name, given in case.tolerance.items():
        for day, texts in enumerate(case.printed, start=1):
            rule = h1_half_unit(texts[name])
            if not isinstance(given, (int, float)) or abs(given - rule) > FLOAT_NOISE:
                problems.append(
                    f"tolerance.{name} is {given!r}; D124 gives {rule!r} for the "
                    f"printed '{texts[name]}' of day {day}"
                )
    return problems


def h1_run(case: H1Case) -> tuple[list[DayResult], float]:
    """Example 37 on this balance, read as D228 says; also the capacity."""
    capacity = case.inputs["total_available_water"]
    root_depth = case.inputs["root_depth"]
    crop_day = CropDay(
        transpiration_coefficient=case.inputs["crop_coefficient"],
        root_depth=root_depth,
        readily_available_fraction=case.inputs["depletion_fraction"],
    )
    days = [
        DayInput(
            date=START + datetime.timedelta(days=offset),
            precipitation=0.0,
            runoff=0.0,
            reference_evapotranspiration=case.inputs["reference_evapotranspiration"],
            evaporation_coefficient=0.0,
            crop=crop_day,
        )
        for offset in range(len(case.rows))
    ]
    results = run_balance(
        days,
        initial_storage=capacity - case.inputs["initial_depletion"],
        capacity=capacity,
        column_depth=root_depth,
    )
    return results, capacity


def h1_computed(r: DayResult, capacity: float) -> dict[str, float | Missing]:
    """The three printed columns of a day, as this balance gives them.

    Adjusted ETc is the actual evapotranspiration of R3, transpiration plus
    evaporation (zero with Ke = 0); the depletion at the end of the day is the
    capacity less the storage at its end. A missing quantity stays missing.
    """
    if isinstance(r.transpiration, Missing):
        adjusted = r.transpiration
    elif isinstance(r.evaporation, Missing):
        adjusted = r.evaporation
    else:
        adjusted = r.transpiration + r.evaporation
    depletion = r.storage_end
    if not isinstance(depletion, Missing):
        depletion = capacity - depletion
    return {
        "stress_coefficient": r.stress_coefficient,
        "adjusted_crop_evapotranspiration": adjusted,
        "depletion_end": depletion,
    }


def h1_comparison_failures(case: H1Case) -> list[str]:
    """Each printed value the run misses by more than its tolerance."""
    results, capacity = h1_run(case)
    failures = []
    for day, (r, expected, texts) in enumerate(
        zip(results, case.rows, case.printed), start=1
    ):
        computed = h1_computed(r, capacity)
        for name in H1_COLUMNS:
            value = computed[name]
            if isinstance(value, Missing):
                failures.append(f"day {day}, {name}: not computed ({value.reason})")
                continue
            tolerance = h1_half_unit(texts[name])
            if value != pytest.approx(expected[name], abs=tolerance, rel=0):
                failures.append(
                    f"day {day}, {name}: computed {value!r}, expected "
                    f"{expected[name]!r} within {tolerance!r}"
                )
    return failures


def run_h1(path: Path) -> list[str]:
    """Every problem of the H1 check on the signed fixture at ``path``."""
    case = h1_load_case(h1_read_fixture(path))
    return h1_tolerance_problems(case) + h1_comparison_failures(case)


def test_h1_public_reference_case():
    reason = h1_skip_reason(H1_FIXTURE)
    if reason is not None:
        pytest.skip(reason)
    problems = run_h1(H1_FIXTURE)
    assert not problems, "\n".join(problems)


def test_h1_the_skip_says_what_it_waits_for():
    assert "EXAMPLE 37" in H1_WAITS_FOR
    assert "D228" in H1_WAITS_FOR
    assert "D124" in H1_WAITS_FOR
    assert "D34" in H1_WAITS_FOR
    assert H1_FIXTURE_NAME in H1_WAITS_FOR


# The loader and the comparison of H1 on a PLACEHOLDER fixture. Its inputs are
# PLACEHOLDER numbers; its rows are what this balance computes on them, printed
# with the decimals of the example, so the comparison passes by construction.

H1_PLACEHOLDER_INPUTS = {
    "reference_evapotranspiration": 7.0,  # PLACEHOLDER
    "crop_coefficient": KCB,
    "root_depth": COLUMN_DEPTH,
    "depletion_fraction": FRACTION,
    "total_available_water": CAPACITY,
    "initial_depletion": 3.0,  # PLACEHOLDER
}
H1_PLACEHOLDER_DECIMALS = {
    "stress_coefficient": 2,
    "adjusted_crop_evapotranspiration": 1,
    "depletion_end": 1,
}


def h1_placeholder_fixture(*, checked: bool = True, days: int = 6) -> dict:
    inputs = {
        name: {"value": value, "unit": "PLACEHOLDER"}
        for name, value in H1_PLACEHOLDER_INPUTS.items()
    }
    case = H1Case(
        inputs=dict(H1_PLACEHOLDER_INPUTS),
        rows=[{} for _ in range(days)],
        printed=[],
        tolerance={},
    )
    results, capacity = h1_run(case)
    rows = []
    for day, r in enumerate(results, start=1):
        computed = h1_computed(r, capacity)
        row = {"day": day}
        for name, decimals in H1_PLACEHOLDER_DECIMALS.items():
            printed = f"{computed[name]:.{decimals}f}"
            row[name] = {"value": float(printed), "printed": printed}
        rows.append(row)
    return {
        "test": "PLACEHOLDER fixture of the H1 machinery",
        "source": {
            "reference": "PLACEHOLDER, not a publication",
            "locator": "PLACEHOLDER",
        },
        "transcribed_by": "PLACEHOLDER person one",
        "checked_by": "PLACEHOLDER person two" if checked else "",
        "inputs": inputs,
        "rows": rows,
        "tolerance": {
            name: 0.5 * 10.0**-decimals
            for name, decimals in H1_PLACEHOLDER_DECIMALS.items()
        },
    }


def h1_write(tmp_path: Path, fixture: dict) -> Path:
    path = tmp_path / H1_FIXTURE.name
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def test_h1_placeholder_series_reaches_the_stressed_days():
    # So that the machinery is exercised where Ks falls below one.
    rows = h1_placeholder_fixture()["rows"]
    assert rows[0]["stress_coefficient"]["value"] == 1.0
    assert rows[-1]["stress_coefficient"]["value"] < 1.0


def test_h1_absent_fixture_skips_naming_the_file_and_the_signature(tmp_path):
    reason = h1_skip_reason(tmp_path / H1_FIXTURE.name)
    assert reason is not None
    assert H1_FIXTURE_NAME in reason
    assert "absent" in reason
    assert "checked_by" in reason


def test_h1_unsigned_fixture_skips(tmp_path):
    reason = h1_skip_reason(h1_write(tmp_path, h1_placeholder_fixture(checked=False)))
    assert reason is not None
    assert "Not signed yet: checked_by of the file" in reason


def test_h1_signed_placeholder_fixture_runs_and_passes(tmp_path):
    path = h1_write(tmp_path, h1_placeholder_fixture())
    assert h1_skip_reason(path) is None
    assert run_h1(path) == []


@pytest.mark.parametrize("name", H1_COLUMNS)
def test_h1_value_outside_its_tolerance_fails(tmp_path, name):
    fixture = h1_placeholder_fixture()
    entry = fixture["rows"][-1][name]
    decimals = H1_PLACEHOLDER_DECIMALS[name]
    # Two units of the last printed digit: beyond the half unit of D124 for sure.
    moved = f"{entry['value'] + 2 * 10.0**-decimals:.{decimals}f}"
    entry["value"], entry["printed"] = float(moved), moved
    problems = run_h1(h1_write(tmp_path, fixture))
    assert len(problems) == 1
    assert problems[0].startswith(f"day {len(fixture['rows'])}, {name}:")


def test_h1_the_comparison_uses_half_a_unit_of_the_last_printed_digit():
    case = h1_load_case(h1_placeholder_fixture())
    results, capacity = h1_run(case)
    exact = capacity - results[-1].storage_end
    tolerance = case.tolerance["depletion_end"]
    inside = [dict(row) for row in case.rows]
    outside = [dict(row) for row in case.rows]
    inside[-1]["depletion_end"] = exact + 0.9 * tolerance
    outside[-1]["depletion_end"] = exact + 1.1 * tolerance
    assert h1_comparison_failures(dataclasses.replace(case, rows=inside)) == []
    failures = h1_comparison_failures(dataclasses.replace(case, rows=outside))
    assert len(failures) == 1
    assert "depletion_end" in failures[0]


def test_h1_a_tolerance_other_than_the_rule_of_d124_fails(tmp_path):
    fixture = h1_placeholder_fixture()
    fixture["tolerance"]["stress_coefficient"] *= 2
    problems = h1_tolerance_problems(h1_load_case(fixture))
    assert problems
    assert all(p.startswith("tolerance.stress_coefficient") for p in problems)


def test_h1_value_that_is_not_its_printed_number_fails():
    fixture = h1_placeholder_fixture()
    fixture["rows"][0]["depletion_end"]["value"] += 1.0
    with pytest.raises(AssertionError, match=r"rows\[1\]\.depletion_end"):
        h1_load_case(fixture)


def test_h1_days_out_of_order_fail():
    fixture = h1_placeholder_fixture()
    fixture["rows"][0], fixture["rows"][1] = fixture["rows"][1], fixture["rows"][0]
    with pytest.raises(AssertionError, match="in order"):
        h1_load_case(fixture)


def test_h1_an_input_too_many_or_too_few_fails():
    fixture = h1_placeholder_fixture()
    fixture["inputs"]["precipitation"] = {"value": 0.0}
    with pytest.raises(AssertionError, match="'inputs'"):
        h1_load_case(fixture)
    fixture = h1_placeholder_fixture()
    del fixture["inputs"]["initial_depletion"]
    with pytest.raises(AssertionError, match="'inputs'"):
        h1_load_case(fixture)


# --- Waiting for people -----------------------------------------------------


@pytest.mark.skip(
    reason="[H8] is defined by D227 of issue #77 (docs/VALIDATION.md H8) as a "
    "list of invariants that the tests named in that entry check one by one. "
    "This test has no criterion of its own: asserting the list again here would "
    "need series and cases D227 does not give. Whether to remove it is for the "
    "lead developer"
)
def test_h8_invariants_numeric_criteria():
    raise AssertionError("not defined")
