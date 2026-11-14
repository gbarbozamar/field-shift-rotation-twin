"""Acceptance test of engine/water/runoff/ (unit l1/water-runoff-cn, issue #148).

Run with ``python -m pytest engine/water/runoff/`` from the repository root.

The cases are PROPOSED (blueprint section 3.7). Each is listed in
engine/water/runoff/README.md under "PROPOSED cases", by the name of its test
function without ``test_``, written with hyphens.

EVERY NUMBER IN THIS FILE IS A PLACEHOLDER. None is a constant, a curve
number or an expected value of the Curve Number method, and none comes from
any source. The constants below are chosen to be plainly not real; they
test the structure of the code, not the method.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import datetime
import inspect
import math
import re
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing
from engine.water.balance import DayInput, run_balance, step
from engine.water.runoff import curve_number as module
from engine.water.runoff import (
    PRECIPITATION,
    PRECIPITATION_UNIT,
    CurveNumberConstants,
    PrecipitationValue,
    RunoffDayInput,
    RunoffDayResult,
    initial_abstraction,
    potential_retention,
    run_runoff,
    runoff_day,
    runoff_depth,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
README = (HERE / "README.md").read_text(encoding="utf-8")
MODULES = sorted(p for p in HERE.glob("*.py") if not p.name.startswith("test_"))

# PLACEHOLDER constants, plainly not real. With them the retention is
# S = 3 * (6 / CN - 0.2), which is zero at CN = 30 and below zero above it.
CONSTANTS = CurveNumberConstants(
    initial_abstraction_ratio=0.5,  # PLACEHOLDER
    retention_numerator=6.0,  # PLACEHOLDER
    retention_offset=0.2,  # PLACEHOLDER
    retention_unit_factor=3.0,  # PLACEHOLDER
)
TOP_CURVE_NUMBER = 30.0  # PLACEHOLDER: where S is zero with CONSTANTS
GUARD = "NOT_COMPUTABLE"  # PLACEHOLDER reason code of the unit guard (Q11 is OPEN)
DAY = datetime.date(2001, 3, 5)  # PLACEHOLDER date
CONSTANT_NAMES = [f.name for f in dataclasses.fields(CurveNumberConstants)]
NON_FINITE = [math.inf, -math.inf, math.nan]


def _by_hand(precipitation: float, curve: float, c: CurveNumberConstants) -> float:
    """The PROPOSED forms of the README, written out again for the test."""
    s = c.retention_unit_factor * (c.retention_numerator / curve - c.retention_offset)
    ia = c.initial_abstraction_ratio * s
    if precipitation <= ia:
        return 0.0
    return (precipitation - ia) ** 2 / (precipitation - ia + s)


def _day(precipitation=12.0, curve=10.0, unit=PRECIPITATION_UNIT, date=DAY):
    return RunoffDayInput(
        date=date,
        precipitation=PrecipitationValue(value=precipitation, unit=unit),
        curve_number=curve,
    )


def _with(**changes) -> CurveNumberConstants:
    return dataclasses.replace(CONSTANTS, **changes)


# ---------------------------------------------------------------------------
# The forms, with PLACEHOLDER values.


def test_runoff_follows_the_proposed_forms():
    for precipitation in (0.0, 1.0, 4.0, 12.0, 40.0, 300.0):
        for curve in (2.0, 5.0, 10.0, 20.0, 29.0):
            got = runoff_depth(precipitation, curve, constants=CONSTANTS)
            assert got == pytest.approx(_by_hand(precipitation, curve, CONSTANTS))
    s = potential_retention(10.0, constants=CONSTANTS)
    assert s == pytest.approx(3.0 * (6.0 / 10.0 - 0.2))
    assert initial_abstraction(s, constants=CONSTANTS) == pytest.approx(0.5 * s)


def test_runoff_is_zero_when_precipitation_does_not_exceed_the_initial_abstraction():
    for curve in (2.0, 10.0, 25.0):
        ia = initial_abstraction(
            potential_retention(curve, constants=CONSTANTS), constants=CONSTANTS
        )
        assert ia > 0
        for precipitation in (0.0, ia / 3, ia):
            assert runoff_depth(precipitation, curve, constants=CONSTANTS) == 0.0
        assert runoff_depth(ia * 1.01, curve, constants=CONSTANTS) > 0.0


def test_runoff_is_never_above_the_precipitation_of_the_day():
    curves = [TOP_CURVE_NUMBER * k / 40 for k in range(1, 41)]
    precipitations = [0.0, 1e-9, 0.3, 1.0, 7.7, 25.0, 120.0, 1e6]
    for ratio in (0.0, 0.5, 2.0):
        constants = _with(initial_abstraction_ratio=ratio)
        for curve in curves:
            for precipitation in precipitations:
                q = runoff_depth(precipitation, curve, constants=constants)
                assert isinstance(q, float)
                assert 0.0 <= q <= precipitation


def test_at_zero_retention_runoff_is_the_whole_precipitation_and_not_more():
    assert potential_retention(TOP_CURVE_NUMBER, constants=CONSTANTS) == 0.0
    for precipitation in (1e-300, 0.1, 0.7, 3.3, 1e300):
        q = runoff_depth(precipitation, TOP_CURVE_NUMBER, constants=CONSTANTS)
        assert q <= precipitation
        assert q == pytest.approx(precipitation)


def test_runoff_grows_with_precipitation():
    for curve in (3.0, 10.0, 28.0):
        values = [
            runoff_depth(p, curve, constants=CONSTANTS)
            for p in [k * 0.5 for k in range(200)]
        ]
        assert all(b >= a for a, b in zip(values, values[1:]))
        positive = [v for v in values if v > 0]
        assert all(b > a for a, b in zip(positive, positive[1:]))


def test_runoff_grows_with_the_curve_number():
    for precipitation in (2.0, 12.0, 60.0):
        curves = [TOP_CURVE_NUMBER * k / 50 for k in range(1, 51)]
        values = [runoff_depth(precipitation, c, constants=CONSTANTS) for c in curves]
        assert all(b >= a for a, b in zip(values, values[1:]))
        assert values[-1] > values[0]


# ---------------------------------------------------------------------------
# Rejected, never clipped.


@pytest.mark.parametrize("curve", [0.0, -1.0, -TOP_CURVE_NUMBER])
def test_a_curve_number_not_above_zero_is_not_computable(curve):
    s = potential_retention(curve, constants=CONSTANTS)
    assert isinstance(s, Missing) and s.reason == "NOT_COMPUTABLE"
    assert "curve_number" in s.detail and "admissible range" in s.detail
    q = runoff_depth(12.0, curve, constants=CONSTANTS)
    assert isinstance(q, Missing) and q.reason == "MISSING_INPUT"
    assert "curve_number" in q.detail and "NOT_COMPUTABLE" in q.detail


@pytest.mark.parametrize("curve", [TOP_CURVE_NUMBER * 1.001, 31.0, 1e9])
def test_a_curve_number_whose_retention_is_below_zero_is_not_clipped(curve):
    s = potential_retention(curve, constants=CONSTANTS)
    assert isinstance(s, Missing) and s.reason == "NOT_COMPUTABLE"
    assert "curve_number" in s.detail and "below zero" in s.detail
    q = runoff_depth(12.0, curve, constants=CONSTANTS)
    assert isinstance(q, Missing)
    # Not silently taken at the top of the range.
    assert q != runoff_depth(12.0, TOP_CURVE_NUMBER, constants=CONSTANTS)


@pytest.mark.parametrize("precipitation", [-1e-9, -0.5, -40.0])
def test_a_negative_precipitation_is_not_computable(precipitation):
    q = runoff_depth(precipitation, 10.0, constants=CONSTANTS)
    assert isinstance(q, Missing) and q.reason == "NOT_COMPUTABLE"
    assert f"'{PRECIPITATION}'" in q.detail and "below zero" in q.detail
    result = runoff_day(
        _day(precipitation), constants=CONSTANTS, unit_guard_reason=GUARD
    )
    assert isinstance(result.runoff, Missing)
    assert result.runoff.reason == "NOT_COMPUTABLE"


def test_a_negative_initial_abstraction_ratio_is_not_computable():
    constants = _with(initial_abstraction_ratio=-0.5)
    ia = initial_abstraction(5.0, constants=constants)
    assert isinstance(ia, Missing) and ia.reason == "NOT_COMPUTABLE"
    assert "initial_abstraction_ratio" in ia.detail
    q = runoff_depth(12.0, 10.0, constants=constants)
    assert isinstance(q, Missing) and "initial_abstraction_ratio" in q.detail


def test_a_negative_retention_given_to_the_initial_abstraction_is_not_computable():
    ia = initial_abstraction(-1.0, constants=CONSTANTS)
    assert isinstance(ia, Missing) and ia.reason == "NOT_COMPUTABLE"


@pytest.mark.parametrize("bad", NON_FINITE, ids=["inf", "minus-inf", "nan"])
def test_a_non_finite_input_or_constant_is_not_computable(bad):
    q = runoff_depth(bad, 10.0, constants=CONSTANTS)
    assert isinstance(q, Missing) and q.reason == "NOT_COMPUTABLE"
    assert f"'{PRECIPITATION}'" in q.detail
    s = potential_retention(bad, constants=CONSTANTS)
    assert isinstance(s, Missing) and s.reason == "NOT_COMPUTABLE"
    assert "curve_number" in s.detail
    for name in CONSTANT_NAMES:
        q = runoff_depth(12.0, 10.0, constants=_with(**{name: bad}))
        assert isinstance(q, Missing), name
        assert name in q.detail, name
        assert "NOT_COMPUTABLE" in (q.reason + q.detail), name


def test_an_overflow_is_not_computable():
    s = potential_retention(1e-308, constants=_with(retention_numerator=1e300))
    assert isinstance(s, Missing) and s.reason == "NOT_COMPUTABLE"
    q = runoff_depth(1.0, 1.0, constants=_with(retention_unit_factor=1e308))
    assert isinstance(q, Missing) and "NOT_COMPUTABLE" in q.detail
    # P - Ia + S overflows although each term is finite.
    q = runoff_depth(1.7e308, 1.0, constants=_with(retention_unit_factor=1e307))
    assert isinstance(q, Missing) and q.reason == "NOT_COMPUTABLE"


# ---------------------------------------------------------------------------
# Missing in, missing out (C3.1, C3.3).


def test_a_missing_precipitation_gives_a_missing_runoff_that_names_it():
    gone = Missing(reason="NO_COVERAGE")
    q = runoff_depth(gone, 10.0, constants=CONSTANTS)
    assert q == Missing(
        reason="MISSING_INPUT", detail=f"input '{PRECIPITATION}' (NO_COVERAGE)"
    )
    result = runoff_day(_day(gone), constants=CONSTANTS, unit_guard_reason=GUARD)
    assert result.runoff.reason == "MISSING_INPUT"
    assert (
        result.runoff.detail
        == f"{DAY.isoformat()}: input '{PRECIPITATION}' (NO_COVERAGE)"
    )
    # The precipitation is needed by the runoff only.
    assert isinstance(result.potential_retention, float)
    assert isinstance(result.initial_abstraction, float)


def test_a_missing_curve_number_gives_a_missing_runoff_that_names_it():
    q = runoff_depth(12.0, Missing(reason="NOT_DECLARED"), constants=CONSTANTS)
    assert isinstance(q, Missing) and q.reason == "MISSING_INPUT"
    assert "input 'curve_number' (NOT_DECLARED)" in q.detail


@pytest.mark.parametrize("name", CONSTANT_NAMES)
def test_a_missing_constant_gives_a_missing_runoff_that_names_it(name):
    constants = _with(**{name: Missing(reason="NOT_AVAILABLE")})
    q = runoff_depth(12.0, 10.0, constants=constants)
    assert isinstance(q, Missing) and q.reason == "MISSING_INPUT"
    assert f"constant '{name}' (NOT_AVAILABLE)" in q.detail
    # Also when the day would give no runoff at all.
    q = runoff_depth(0.0, 10.0, constants=constants)
    assert isinstance(q, Missing)


def test_every_missing_operand_is_named():
    q = runoff_depth(
        Missing(reason="NO_COVERAGE"),
        10.0,
        constants=_with(
            retention_offset=Missing(reason="NOT_AVAILABLE"),
            retention_unit_factor=Missing(reason="NOT_DECLARED"),
        ),
    )
    assert f"input '{PRECIPITATION}' (NO_COVERAGE)" in q.detail
    assert "constant 'retention_offset' (NOT_AVAILABLE)" in q.detail
    assert "constant 'retention_unit_factor' (NOT_DECLARED)" in q.detail


def test_a_missing_operand_is_reported_before_a_non_finite_one():
    s = potential_retention(
        math.inf, constants=_with(retention_offset=Missing(reason="NOT_AVAILABLE"))
    )
    assert s.reason == "MISSING_INPUT" and "retention_offset" in s.detail


def test_missing_is_never_zero():
    cases = [
        runoff_depth(Missing(reason="NO_COVERAGE"), 10.0, constants=CONSTANTS),
        runoff_depth(0.0, Missing(reason="NOT_DECLARED"), constants=CONSTANTS),
        runoff_depth(
            0.0,
            10.0,
            constants=_with(initial_abstraction_ratio=Missing(reason="NOT_AVAILABLE")),
        ),
        runoff_depth(-1.0, 10.0, constants=CONSTANTS),
        runoff_depth(0.0, 0.0, constants=CONSTANTS),
    ]
    for q in cases:
        assert isinstance(q, Missing)
        assert q != 0


# ---------------------------------------------------------------------------
# Unit of the precipitation.


def test_the_precipitation_unit_is_that_of_climate_quantities():
    text = (ROOT / "contracts" / "CLIMATE_QUANTITIES.md").read_text(encoding="utf-8")
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.startswith("| `CQ1` |")
    ]
    assert len(rows) == 1
    assert rows[0][1] == f"`{PRECIPITATION}`"
    assert rows[0][3] == f"`{PRECIPITATION_UNIT}`"


@pytest.mark.parametrize(
    "unit", ["mm", "in day-1", "MM DAY-1", " mm day-1", "mm/day", "kg m-2 s-1", ""]
)
def test_a_precipitation_in_another_unit_is_not_converted(unit):
    result = runoff_day(
        _day(12.0, unit=unit), constants=CONSTANTS, unit_guard_reason="CONTROL_FAILED"
    )
    assert isinstance(result.runoff, Missing)
    assert result.runoff.reason == "CONTROL_FAILED"
    assert f"'{unit}'" in result.runoff.detail
    assert f"'{PRECIPITATION_UNIT}'" in result.runoff.detail
    # Even a day that would give no runoff is not computed.
    result = runoff_day(
        _day(0.0, unit=unit), constants=CONSTANTS, unit_guard_reason=GUARD
    )
    assert isinstance(result.runoff, Missing)


def test_the_unit_guard_order_missing_then_unit_then_non_finite():
    missing_curve = runoff_day(
        _day(12.0, curve=Missing(reason="NOT_DECLARED"), unit="mm"),
        constants=CONSTANTS,
        unit_guard_reason="CONTROL_FAILED",
    )
    assert missing_curve.runoff.reason == "MISSING_INPUT"
    missing_rain = runoff_day(
        _day(Missing(reason="NO_COVERAGE"), unit="mm"),
        constants=CONSTANTS,
        unit_guard_reason="CONTROL_FAILED",
    )
    assert missing_rain.runoff.reason == "MISSING_INPUT"
    for value in (math.inf, math.nan, -3.0):
        result = runoff_day(
            _day(value, unit="mm"),
            constants=CONSTANTS,
            unit_guard_reason="CONTROL_FAILED",
        )
        assert result.runoff.reason == "CONTROL_FAILED"


# ---------------------------------------------------------------------------
# One day and a sequence of days.


def test_one_day_gives_its_runoff_retention_and_initial_abstraction():
    result = runoff_day(_day(12.0, 10.0), constants=CONSTANTS, unit_guard_reason=GUARD)
    assert result == RunoffDayResult(
        date=DAY,
        runoff=runoff_depth(12.0, 10.0, constants=CONSTANTS),
        potential_retention=potential_retention(10.0, constants=CONSTANTS),
        initial_abstraction=initial_abstraction(
            potential_retention(10.0, constants=CONSTANTS), constants=CONSTANTS
        ),
    )


def test_a_run_returns_one_result_per_day_in_order():
    dates = [DAY + datetime.timedelta(days=k) for k in range(30)]
    days = [_day(float(k % 7) * 4.0, 2.0 + k % 25, date=d) for k, d in enumerate(dates)]
    results = run_runoff(days, constants=CONSTANTS, unit_guard_reason=GUARD)
    assert [r.date for r in results] == dates
    for day, result in zip(days, results):
        assert result == runoff_day(day, constants=CONSTANTS, unit_guard_reason=GUARD)
    # The order given is kept, not sorted.
    reversed_results = run_runoff(
        days[::-1], constants=CONSTANTS, unit_guard_reason=GUARD
    )
    assert reversed_results == results[::-1]


def test_a_missing_day_does_not_stop_the_days_after_it():
    dates = [DAY + datetime.timedelta(days=k) for k in range(5)]
    days = [_day(12.0, 10.0, date=d) for d in dates]
    days[1] = _day(Missing(reason="NO_COVERAGE"), 10.0, date=dates[1])
    days[3] = _day(12.0, Missing(reason="NOT_DECLARED"), date=dates[3])
    results = run_runoff(days, constants=CONSTANTS, unit_guard_reason=GUARD)
    assert len(results) == 5
    assert isinstance(results[1].runoff, Missing)
    assert results[1].runoff.detail.startswith(dates[1].isoformat())
    assert isinstance(results[3].runoff, Missing)
    assert results[3].runoff.detail.startswith(dates[3].isoformat())
    for k in (0, 2, 4):
        assert results[k].runoff == runoff_depth(12.0, 10.0, constants=CONSTANTS)


def test_an_empty_sequence_gives_no_days():
    assert run_runoff([], constants=CONSTANTS, unit_guard_reason=GUARD) == []


# ---------------------------------------------------------------------------
# Integration with engine/water/balance (read only).


def test_the_runoff_of_a_day_is_the_runoff_of_a_balance_day():
    result = runoff_day(_day(12.0, 10.0), constants=CONSTANTS, unit_guard_reason=GUARD)
    balance_day = DayInput(
        date=result.date,
        precipitation=12.0,
        runoff=result.runoff,
        reference_evapotranspiration=2.0,  # PLACEHOLDER
        evaporation_coefficient=0.25,  # PLACEHOLDER
        crop=None,
    )
    out = step(40.0, balance_day, capacity=100.0, column_depth=1.0)  # PLACEHOLDER
    assert out.runoff == result.runoff
    assert out.runoff_shortfall == 0.0
    closure = (
        out.precipitation
        - out.runoff
        - out.evaporation
        - out.transpiration
        - out.drainage
    )
    assert out.storage_end - out.storage_start == pytest.approx(closure)


def test_a_missing_runoff_makes_the_balance_day_missing_and_named():
    result = runoff_day(
        _day(Missing(reason="NO_COVERAGE"), 10.0),
        constants=CONSTANTS,
        unit_guard_reason=GUARD,
    )
    balance_day = DayInput(
        date=result.date,
        precipitation=Missing(reason="NO_COVERAGE"),
        runoff=result.runoff,
        reference_evapotranspiration=2.0,  # PLACEHOLDER
        evaporation_coefficient=0.25,  # PLACEHOLDER
        crop=None,
    )
    out = step(40.0, balance_day, capacity=100.0, column_depth=1.0)  # PLACEHOLDER
    assert isinstance(out.storage_end, Missing)
    assert "runoff (MISSING_INPUT)" in out.storage_end.detail


def test_a_run_of_runoff_feeds_a_run_of_the_balance():
    dates = [DAY + datetime.timedelta(days=k) for k in range(60)]
    rain = [float((k * 7) % 23) for k in range(60)]  # PLACEHOLDER
    runoff = run_runoff(
        [_day(p, 5.0 + k % 24, date=d) for k, (p, d) in enumerate(zip(rain, dates))],
        constants=CONSTANTS,
        unit_guard_reason=GUARD,
    )
    balance = run_balance(
        [
            DayInput(
                date=d,
                precipitation=p,
                runoff=r.runoff,
                reference_evapotranspiration=3.0,  # PLACEHOLDER
                evaporation_coefficient=0.5,  # PLACEHOLDER
                crop=None,
            )
            for d, p, r in zip(dates, rain, runoff)
        ],
        initial_storage=10.0,  # PLACEHOLDER
        capacity=50.0,  # PLACEHOLDER
        column_depth=1.0,  # PLACEHOLDER
    )
    assert len(balance) == 60
    for day in balance:
        assert day.runoff_shortfall == 0.0
    assert any(day.runoff > 0 for day in balance)


# ---------------------------------------------------------------------------
# Caller defects, purity.


def test_wrong_types_raise_type_error():
    for bad in (True, "12", None, InputsMissing(reason="NOT_DECLARED")):
        with pytest.raises(TypeError):
            runoff_depth(bad, 10.0, constants=CONSTANTS)
        with pytest.raises(TypeError):
            runoff_depth(12.0, bad, constants=CONSTANTS)
        with pytest.raises(TypeError):
            runoff_depth(12.0, 10.0, constants=_with(retention_offset=bad))
        with pytest.raises(TypeError):
            runoff_day(_day(bad), constants=CONSTANTS, unit_guard_reason=GUARD)
    with pytest.raises(TypeError):
        runoff_depth(12.0, 10.0, constants={"initial_abstraction_ratio": 0.5})
    with pytest.raises(TypeError):
        runoff_day(_day(12.0, unit=None), constants=CONSTANTS, unit_guard_reason=GUARD)
    with pytest.raises(TypeError):
        runoff_day(
            RunoffDayInput(date=DAY, precipitation=12.0, curve_number=10.0),
            constants=CONSTANTS,
            unit_guard_reason=GUARD,
        )
    with pytest.raises(TypeError):
        runoff_day(
            _day(date=datetime.datetime(2001, 3, 5)),
            constants=CONSTANTS,
            unit_guard_reason=GUARD,
        )
    with pytest.raises(TypeError):
        run_runoff("days", constants=CONSTANTS, unit_guard_reason=GUARD)
    with pytest.raises(TypeError):
        run_runoff([_day(), "day"], constants=CONSTANTS, unit_guard_reason=GUARD)


@pytest.mark.parametrize("reason", ["UNIT_MISMATCH", "", None, "not_computable"])
def test_a_reason_code_outside_c32_raises_value_error(reason):
    with pytest.raises(ValueError):
        runoff_day(_day(), constants=CONSTANTS, unit_guard_reason=reason)
    with pytest.raises(ValueError):
        run_runoff([], constants=CONSTANTS, unit_guard_reason=reason)


def test_same_arguments_give_the_same_result_and_are_not_changed():
    days = [_day(12.0, 10.0), _day(Missing(reason="NO_COVERAGE"), 10.0)]
    before = copy.deepcopy((days, CONSTANTS))
    first = run_runoff(days, constants=CONSTANTS, unit_guard_reason=GUARD)
    second = run_runoff(days, constants=CONSTANTS, unit_guard_reason=GUARD)
    assert first == second
    assert (days, CONSTANTS) == before


# ---------------------------------------------------------------------------
# Rules of the brief.


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.M | re.S)
    assert match, f"README has no section '{title}'"
    return match.group(1)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_module_holds_no_number_other_than_zero(path):
    numbers = [
        node.value
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    ]
    assert all(n == 0 for n in numbers), numbers


def test_no_constant_and_no_public_argument_has_a_default():
    for item in dataclasses.fields(CurveNumberConstants):
        assert item.default is dataclasses.MISSING
        assert item.default_factory is dataclasses.MISSING
    for cls in (PrecipitationValue, RunoffDayInput, RunoffDayResult):
        for item in dataclasses.fields(cls):
            assert item.default is dataclasses.MISSING, f"{cls.__name__}.{item.name}"
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_") or function.__module__ != module.__name__:
            continue
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.default is inspect.Parameter.empty, (
                f"{name}({parameter.name})"
            )


ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "datetime",
    "math",
    "typing",
    "contracts.results.models",
}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_module_imports_nothing_that_reads_the_outside(path):
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names = {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            names = {node.module}
        else:
            continue
        assert names <= ALLOWED_IMPORTS, names - ALLOWED_IMPORTS


@pytest.mark.parametrize("path", sorted(HERE.glob("*.py")), ids=lambda p: p.name)
def test_contract_models_are_imported_as_contracts_folder_module_and_no_missing_is_defined(
    path,
):
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            top = node.module.split(".")[0]
            assert top not in {"inputs", "results"}, node.module
            if top == "contracts":
                assert len(node.module.split(".")) >= 3, node.module
        if isinstance(node, ast.ClassDef):
            assert "missing" not in node.name.lower(), node.name


def _constants_table() -> list[list[str]]:
    rows = []
    for line in _section("Constants a person has to transcribe").splitlines():
        if line.startswith("| `"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def test_the_readme_lists_every_constant_once_with_an_empty_value():
    rows = _constants_table()
    identifiers = [row[0].strip("`") for row in rows]
    assert sorted(identifiers) == sorted(CONSTANT_NAMES)
    for row in rows:
        assert len(row) == 5, row[0]
        assert row[-1] == "", row[0]


def test_every_case_is_listed_in_the_readme_and_the_readme_says_no_state_is_carried():
    section = _section("PROPOSED cases")
    tree = _tree(Path(__file__))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            case = node.name.removeprefix("test_").replace("_", "-")
            assert f"`{case}`" in section, case
    assert "No state is carried from one day to the next" in README


# ---------------------------------------------------------------------------
# Skipped, waiting for people.

# Filled by a person from a public worked example of the Curve Number method,
# with the record D34 asks for (full reference, locator, verbatim text, date
# read) and checked by a person. Keys: "precipitation" (depth of the day, in
# PRECIPITATION_UNIT once converted by the person), "curve_number",
# "constants" (a CurveNumberConstants), "runoff" (the printed result) and
# "tolerance" (absolute, set by the science reviewers). Nothing is filled here.
WORKED_EXAMPLE: dict | None = None

WAITS_FOR = (
    "waits for a public worked example of the Curve Number method, transcribed "
    "and checked by a person under D34 of issue #77: its inputs (precipitation "
    "of the day and curve number), the constants of the README table, the "
    "printed runoff and the tolerance set by the science reviewers; the source "
    "is CITATION NEEDED"
)


@pytest.mark.skipif(WORKED_EXAMPLE is None, reason=WAITS_FOR)
def test_public_worked_example():
    example = WORKED_EXAMPLE
    got = runoff_depth(
        example["precipitation"],
        example["curve_number"],
        constants=example["constants"],
    )
    assert got == pytest.approx(example["runoff"], abs=example["tolerance"])


def test_the_worked_example_says_what_it_waits_for():
    for words in (
        "inputs",
        "constants",
        "runoff",
        "tolerance",
        "D34",
        "CITATION NEEDED",
    ):
        assert words in WAITS_FOR
