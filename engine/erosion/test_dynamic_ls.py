"""Tests for ``engine.erosion.dynamic_ls``. PROPOSED (blueprint section 3.7).

Every coefficient in this file is a PLACEHOLDER: plainly not real numbers
(repeated digits, or zero and one where arithmetic is done by hand). No case
holds an expected value of the science.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
import sys
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import dynamic_ls
from engine.erosion.dynamic_ls import (
    DynamicLsStep,
    SlopeSegment,
    dynamic_ls_by_period,
    dynamic_segmented_ls,
    dynamic_segmented_ls_steps,
)
from engine.erosion.ls import (
    SlopeUnit,
    slope_length_factor,
    slope_steepness_factor,
)

FLOAT_NOISE = 1e-12
UNITS = list(SlopeUnit)

# PLACEHOLDER coefficients (repeated digits, never real method values).
PLACEHOLDER_PARAMS = {
    "a1": 11.0,
    "a2": 22.0,
    "a3": 33.0,
    "a4": 44.0,
    "s_break": 55.0,
    "lambda_unit": 22.0,
    "b1": 0.11,
    "b2": 2.2,
    "b3": 3.3,
    "b4": 4.4,
}

# PLACEHOLDER coefficients guaranteeing positive, strictly increasing S on both sides.
MONOTONIC_PARAMS = {
    "a1": 11.0,
    "a2": 2.2,
    "a3": 22.0,
    "a4": 1.1,
    "s_break": 55.0,
    "lambda_unit": 22.0,
    "b1": 0.11,
    "b2": 2.2,
    "b3": 1.1,
    "b4": 4.4,
}

PARAM_NAMES = list(PLACEHOLDER_PARAMS)
NOT_FINITE = [math.nan, math.inf, -math.inf]
INVALID_NUMBERS = [None, "5.0", True, False, [5.0]]


def call_segmented(segments, *, slope_unit=SlopeUnit.PERCENT, **changes):
    params = dict(PLACEHOLDER_PARAMS)
    params.update(changes)
    return dynamic_segmented_ls(segments, slope_unit=slope_unit, **params)


def call_steps(segments, *, slope_unit=SlopeUnit.PERCENT, **changes):
    params = dict(PLACEHOLDER_PARAMS)
    params.update(changes)
    return dynamic_segmented_ls_steps(segments, slope_unit=slope_unit, **params)


def call_periods(periods, *, slope_unit=SlopeUnit.PERCENT, **changes):
    params = dict(PLACEHOLDER_PARAMS)
    params.update(changes)
    return dynamic_ls_by_period(periods, slope_unit=slope_unit, **params)


def single_ls_from_ls_py(
    length_m, steepness, *, slope_unit=SlopeUnit.PERCENT, **changes
):
    params = dict(PLACEHOLDER_PARAMS)
    params.update(changes)
    s = slope_steepness_factor(
        slope_steepness=steepness,
        slope_unit=slope_unit,
        s_break=params["s_break"],
        s_break_unit=slope_unit,
        a1=params["a1"],
        a2=params["a2"],
        a3=params["a3"],
        a4=params["a4"],
    )
    lf = slope_length_factor(
        slope_length=length_m,
        slope_length_unit="m",
        lambda_unit=params["lambda_unit"],
        lambda_unit_unit="m",
        slope_steepness=steepness,
        slope_unit=slope_unit,
        b1=params["b1"],
        b2=params["b2"],
        b3=params["b3"],
        b4=params["b4"],
    )
    return s * lf


def assert_missing(result: object, reason: str) -> None:
    assert type(result) is ResultMissing
    assert not isinstance(result, (int, float))
    assert result.reason == reason
    assert result.detail


def named(missing: ResultMissing) -> set[str]:
    return {part.split()[0] for part in missing.detail.split("; ")}


def a_missing(shape, reason: str = "NOT_AVAILABLE"):
    return shape(reason=reason, detail="PLACEHOLDER: missing input")


# --- 1-segment equivalence to ls.py ------------------------------------------


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u.value)
@pytest.mark.parametrize("branch", ["zero", "below", "at", "above"])
@pytest.mark.parametrize("length_m", [11.0, 22.0, 88.0])
def test_single_segment_reproduces_ls_py_exactly(unit, branch, length_m):
    s_break = 0.5 if unit is SlopeUnit.ANGLE_RADIANS else PLACEHOLDER_PARAMS["s_break"]
    steepness = {
        "zero": 0.0,
        "below": 0.2 if unit is SlopeUnit.ANGLE_RADIANS else 7.0,
        "at": s_break,
        "above": 1.0 if unit is SlopeUnit.ANGLE_RADIANS else 66.0,
    }[branch]
    expected = single_ls_from_ls_py(
        length_m, steepness, slope_unit=unit, s_break=s_break
    )
    actual = call_segmented(
        [SlopeSegment(length_m=length_m, steepness=steepness)],
        slope_unit=unit,
        s_break=s_break,
    )
    assert isinstance(actual, float)
    assert actual == pytest.approx(expected, rel=FLOAT_NOISE, abs=FLOAT_NOISE)


def test_single_segment_works_with_integer_inputs():
    expected = single_ls_from_ls_py(44, 7, slope_unit=SlopeUnit.PERCENT)
    actual = call_segmented([SlopeSegment(length_m=44, steepness=7)])
    assert isinstance(actual, float)
    assert actual == pytest.approx(expected, rel=FLOAT_NOISE)


# --- Multi-segment analytical & physical checks ------------------------------


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u.value)
def test_uniform_multisegment_reproduces_unsegmented_ls(unit):
    steepness = 7.0 if unit is not SlopeUnit.ANGLE_RADIANS else 0.25
    lengths = [11.0, 22.0, 33.0, 14.0]
    total_length = sum(lengths)
    segments = [
        SlopeSegment(length_m=length, steepness=steepness) for length in lengths
    ]

    expected = single_ls_from_ls_py(total_length, steepness, slope_unit=unit)
    actual = call_segmented(segments, slope_unit=unit)
    assert isinstance(actual, float)
    assert actual == pytest.approx(expected, rel=FLOAT_NOISE)


def test_multisegment_by_hand_analytical_check():
    # Three-four-five slope (ratio 0.75 => sin = 0.6) followed by flat segment (0.0).
    # With PLACEHOLDER coefficients: a1=10, a2=1, s_break=1, lambda_unit=1,
    # b1=0.6, b2=0, b3=7, b4=1:
    # - Segment 0 (0 -> 4 m, slope 0.75): beta=1, m=0.5, L(4)=2, S=10*0.6+1=7 => LS_0 = 14.
    # - Segment 1 (4 -> 12 m, slope 0.0): beta=0, m=0, L(12)=L(4)=1, S=1 => LS_1 = 1.
    # - Weighted LS = (4/12)*14 + (8/12)*1 = 16/3.
    params = {
        "a1": 10.0,
        "a2": 1.0,
        "a3": 20.0,
        "a4": 2.0,
        "s_break": 1.0,
        "lambda_unit": 1.0,
        "b1": 0.6,
        "b2": 0.0,
        "b3": 7.0,
        "b4": 1.0,
    }
    segments = [
        SlopeSegment(length_m=4.0, steepness=0.75),
        SlopeSegment(length_m=8.0, steepness=0.0),
    ]
    result = dynamic_segmented_ls(segments, slope_unit=SlopeUnit.RATIO, **params)
    assert result == pytest.approx(16.0 / 3.0, rel=FLOAT_NOISE)

    steps = dynamic_segmented_ls_steps(segments, slope_unit=SlopeUnit.RATIO, **params)
    assert isinstance(steps, tuple)
    assert len(steps) == 2
    assert steps[0] == DynamicLsStep(
        start_m=0.0,
        end_m=4.0,
        length_m=4.0,
        steepness=0.75,
        s_factor=pytest.approx(7.0, rel=FLOAT_NOISE),
        segment_ls=pytest.approx(14.0, rel=FLOAT_NOISE),
        weight=pytest.approx(4.0 / 12.0, rel=FLOAT_NOISE),
    )
    assert steps[1] == DynamicLsStep(
        start_m=4.0,
        end_m=12.0,
        length_m=8.0,
        steepness=0.0,
        s_factor=pytest.approx(1.0, rel=FLOAT_NOISE),
        segment_ls=pytest.approx(1.0, rel=FLOAT_NOISE),
        weight=pytest.approx(8.0 / 12.0, rel=FLOAT_NOISE),
    )


def test_multisegment_matches_direct_foster_wischmeier_formula():
    segments = [
        SlopeSegment(length_m=15.0, steepness=3.0),
        SlopeSegment(length_m=25.0, steepness=8.0),
        SlopeSegment(length_m=20.0, steepness=15.0),
    ]
    params = MONOTONIC_PARAMS
    actual = call_segmented(segments, slope_unit=SlopeUnit.PERCENT, **params)

    # Recompute directly from ls.py factors per segment break.
    breaks = [(0.0, 15.0, 3.0), (15.0, 40.0, 8.0), (40.0, 60.0, 15.0)]
    weighted_sum = 0.0
    total_len = 60.0
    for start, end, slope in breaks:
        s_i = slope_steepness_factor(
            slope_steepness=slope,
            slope_unit=SlopeUnit.PERCENT,
            s_break=params["s_break"],
            s_break_unit=SlopeUnit.PERCENT,
            a1=params["a1"],
            a2=params["a2"],
            a3=params["a3"],
            a4=params["a4"],
        )
        l_end = slope_length_factor(
            slope_length=end,
            slope_length_unit="m",
            lambda_unit=params["lambda_unit"],
            lambda_unit_unit="m",
            slope_steepness=slope,
            slope_unit=SlopeUnit.PERCENT,
            b1=params["b1"],
            b2=params["b2"],
            b3=params["b3"],
            b4=params["b4"],
        )
        if start == 0.0:
            term = end * l_end
        else:
            l_start = slope_length_factor(
                slope_length=start,
                slope_length_unit="m",
                lambda_unit=params["lambda_unit"],
                lambda_unit_unit="m",
                slope_steepness=slope,
                slope_unit=SlopeUnit.PERCENT,
                b1=params["b1"],
                b2=params["b2"],
                b3=params["b3"],
                b4=params["b4"],
            )
            term = end * l_end - start * l_start
        weighted_sum += s_i * term
    expected = weighted_sum / total_len
    assert actual == pytest.approx(expected, rel=FLOAT_NOISE)


def test_convex_slope_has_higher_ls_than_concave_slope_with_same_segments():
    gentle = SlopeSegment(length_m=30.0, steepness=3.0)
    steep = SlopeSegment(length_m=30.0, steepness=12.0)
    convex_ls = call_segmented([gentle, steep], **MONOTONIC_PARAMS)
    concave_ls = call_segmented([steep, gentle], **MONOTONIC_PARAMS)
    assert isinstance(convex_ls, float) and isinstance(concave_ls, float)
    assert convex_ls > concave_ls


# --- Monotonicity ------------------------------------------------------------


def test_monotonic_increase_with_steepness():
    # Single segment and multi-segment (total length >= lambda_unit).
    slopes = [2.0, 5.0, 10.0, 20.0]
    single_vals = [
        call_segmented([SlopeSegment(length_m=44.0, steepness=s)], **MONOTONIC_PARAMS)
        for s in slopes
    ]
    assert all(a < b for a, b in zip(single_vals, single_vals[1:]))

    multi_vals = [
        call_segmented(
            [
                SlopeSegment(length_m=22.0, steepness=3.0),
                SlopeSegment(length_m=33.0, steepness=s),
            ],
            **MONOTONIC_PARAMS,
        )
        for s in slopes
    ]
    assert all(a < b for a, b in zip(multi_vals, multi_vals[1:]))


def test_monotonic_increase_with_length():
    lengths = [11.0, 22.0, 44.0, 88.0]
    single_vals = [
        call_segmented(
            [SlopeSegment(length_m=length, steepness=8.0)], **MONOTONIC_PARAMS
        )
        for length in lengths
    ]
    assert all(a < b for a, b in zip(single_vals, single_vals[1:]))

    multi_vals = [
        call_segmented(
            [
                SlopeSegment(length_m=22.0, steepness=5.0),
                SlopeSegment(length_m=length, steepness=10.0),
            ],
            **MONOTONIC_PARAMS,
        )
        for length in lengths
    ]
    assert all(a < b for a, b in zip(multi_vals, multi_vals[1:]))


# --- Time-varying periods: dynamic_ls_by_period ------------------------------


def test_dynamic_ls_by_period_evaluates_each_period_cleanly():
    periods = [
        ("year_1", 22.0, 4.5),
        ("year_2", 44.0, 8.0),
        (3, 66.0, 12.0),
    ]
    result = call_periods(periods)
    assert isinstance(result, tuple)
    assert [pid for pid, _ in result] == ["year_1", "year_2", 3]
    for (pid, length_m, steepness), (out_pid, out_val) in zip(periods, result):
        assert out_pid == pid
        assert out_val == pytest.approx(
            single_ls_from_ls_py(length_m, steepness), rel=FLOAT_NOISE
        )


def test_dynamic_ls_by_period_empty_returns_empty_tuple():
    assert call_periods([]) == ()


def test_dynamic_ls_by_period_isolates_missing_and_invalid_periods():
    periods = [
        ("ok_1", 22.0, 5.0),
        ("missing_len", a_missing(InputMissing), 5.0),
        ("neg_len", -5.0, 5.0),
        ("zero_len", 0.0, 5.0),
        ("ok_2", 44.0, 9.0),
    ]
    result = dict(call_periods(periods))
    assert isinstance(result["ok_1"], float)
    assert isinstance(result["ok_2"], float)
    assert_missing(result["missing_len"], "MISSING_INPUT")
    assert_missing(result["neg_len"], "NOT_COMPUTABLE")
    assert_missing(result["zero_len"], "NOT_COMPUTABLE")


# --- G4: Missing propagation & NOT_COMPUTABLE domain checks ------------------


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("param", PARAM_NAMES)
def test_missing_scalar_parameter_propagates_both_shapes(shape, param):
    result = call_segmented(
        [SlopeSegment(length_m=22.0, steepness=7.0)],
        **{param: a_missing(shape)},
    )
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {param}


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("field", ["length_m", "steepness"])
def test_missing_segment_field_propagates_both_shapes(shape, field):
    seg0 = SlopeSegment(length_m=22.0, steepness=5.0)
    seg1 = SlopeSegment(
        length_m=a_missing(shape) if field == "length_m" else 33.0,
        steepness=a_missing(shape) if field == "steepness" else 7.0,
    )
    result = call_segmented([seg0, seg1])
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {f"segments[1].{field}"}


def test_multiple_missing_arguments_are_all_reported_before_not_computable():
    result = call_segmented(
        [
            SlopeSegment(length_m=-10.0, steepness=InputMissing(reason="NOT_DECLARED")),
        ],
        a1=ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER detail"),
        b1=math.nan,
    )
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {"a1", "segments[0].steepness"}
    assert "NOT_DECLARED" in result.detail
    assert "NO_COVERAGE" in result.detail
    assert "PLACEHOLDER detail" in result.detail


def test_empty_segments_is_not_computable():
    result = call_segmented([])
    assert_missing(result, "NOT_COMPUTABLE")


@pytest.mark.parametrize("bad_length", [0.0, -0.0, -10.0])
def test_zero_or_negative_segment_length_is_not_computable(bad_length):
    result = call_segmented(
        [
            SlopeSegment(length_m=20.0, steepness=5.0),
            SlopeSegment(length_m=bad_length, steepness=7.0),
        ]
    )
    assert_missing(result, "NOT_COMPUTABLE")
    assert "segments[1].length_m" in result.detail


def test_non_monotonic_cumulative_break_from_absorption_is_not_computable():
    # In IEEE-754 float64, 1e18 + 1.0 == 1e18 so cumulative break fails to advance.
    result = call_segmented(
        [
            SlopeSegment(length_m=1e18, steepness=5.0),
            SlopeSegment(length_m=1.0, steepness=7.0),
        ]
    )
    assert_missing(result, "NOT_COMPUTABLE")
    assert "monotonic" in result.detail


def test_cumulative_break_overflow_is_not_computable():
    largest = sys.float_info.max
    result = call_segmented(
        [
            SlopeSegment(length_m=largest, steepness=5.0),
            SlopeSegment(length_m=largest, steepness=7.0),
        ]
    )
    assert_missing(result, "NOT_COMPUTABLE")


@pytest.mark.parametrize("bad_lambda_unit", [0.0, -22.0])
def test_non_positive_lambda_unit_is_not_computable(bad_lambda_unit):
    result = call_segmented(
        [SlopeSegment(length_m=22.0, steepness=5.0)],
        lambda_unit=bad_lambda_unit,
    )
    assert_missing(result, "NOT_COMPUTABLE")


@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "minus-inf"])
@pytest.mark.parametrize("param", PARAM_NAMES)
def test_non_finite_scalar_parameter_is_not_computable(number, param):
    result = call_segmented(
        [SlopeSegment(length_m=22.0, steepness=5.0)],
        **{param: number},
    )
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {param}


@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "minus-inf"])
@pytest.mark.parametrize("field", ["length_m", "steepness"])
def test_non_finite_segment_field_is_not_computable(number, field):
    seg = SlopeSegment(
        length_m=number if field == "length_m" else 22.0,
        steepness=number if field == "steepness" else 5.0,
    )
    result = call_segmented([seg])
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {f"segments[0].{field}"}


def test_huge_integer_overflowing_float_is_not_computable():
    result = call_segmented([SlopeSegment(length_m=10**400, steepness=5.0)])
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {"segments[0].length_m"}


def test_ls_py_domain_errors_propagate_as_not_computable():
    # b1=0 causes division by zero inside slope_length_factor
    result = call_segmented([SlopeSegment(length_m=22.0, steepness=5.0)], b1=0.0)
    assert_missing(result, "NOT_COMPUTABLE")

    # Negative slope with fractional b3 raises _NotFiniteReal inside ls.py
    result_neg = call_segmented([SlopeSegment(length_m=22.0, steepness=-5.0)])
    assert_missing(result_neg, "NOT_COMPUTABLE")


# --- G5: TypeError checks ----------------------------------------------------


@pytest.mark.parametrize("bad_segments", [None, "segment", b"segment", 123, {"a": 1}])
def test_invalid_segments_container_raises_type_error(bad_segments):
    with pytest.raises(TypeError):
        call_segmented(bad_segments)


def test_non_segment_element_raises_type_error():
    with pytest.raises(TypeError, match="SlopeSegment"):
        call_segmented([(22.0, 5.0)])


@pytest.mark.parametrize("bad_val", INVALID_NUMBERS, ids=lambda x: repr(x))
@pytest.mark.parametrize("field", ["length_m", "steepness"])
def test_invalid_segment_field_type_raises_type_error(bad_val, field):
    seg = SlopeSegment(
        length_m=bad_val if field == "length_m" else 22.0,
        steepness=bad_val if field == "steepness" else 5.0,
    )
    with pytest.raises(TypeError, match=field):
        call_segmented([seg])


@pytest.mark.parametrize("bad_val", INVALID_NUMBERS, ids=lambda x: repr(x))
@pytest.mark.parametrize("param", PARAM_NAMES)
def test_invalid_scalar_parameter_type_raises_type_error(bad_val, param):
    with pytest.raises(TypeError, match=param):
        call_segmented(
            [SlopeSegment(length_m=22.0, steepness=5.0)],
            **{param: bad_val},
        )


@pytest.mark.parametrize("bad_unit", [None, "percent", 1, True])
def test_invalid_slope_unit_raises_type_error(bad_unit):
    with pytest.raises(TypeError, match="slope_unit"):
        call_segmented(
            [SlopeSegment(length_m=22.0, steepness=5.0)], slope_unit=bad_unit
        )
    with pytest.raises(TypeError, match="slope_unit"):
        call_periods([("p1", 22.0, 5.0)], slope_unit=bad_unit)


@pytest.mark.parametrize(
    "bad_periods",
    [
        None,
        "p1",
        b"p1",
        [["p1", 22.0, 5.0]],
        [("p1", 22.0)],
        [("p1", 22.0, 5.0, 1.0)],
        [(["unhashable"], 22.0, 5.0)],
        [("p1", True, 5.0)],
        [("p1", 22.0, None)],
    ],
)
def test_invalid_periods_raises_type_error(bad_periods):
    with pytest.raises(TypeError):
        call_periods(bad_periods)


# --- G1 purity, zero defaults, and AST constant checks -----------------------


def test_frozen_dataclasses_have_no_defaults_and_are_immutable():
    for cls in (SlopeSegment, DynamicLsStep):
        assert dataclasses.is_dataclass(cls)
        for f in dataclasses.fields(cls):
            assert f.default is dataclasses.MISSING
            assert f.default_factory is dataclasses.MISSING

    seg = SlopeSegment(length_m=22.0, steepness=5.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        seg.length_m = 33.0  # type: ignore[misc]

    step = DynamicLsStep(
        start_m=0.0,
        end_m=22.0,
        length_m=22.0,
        steepness=5.0,
        s_factor=1.0,
        segment_ls=1.0,
        weight=1.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.weight = 2.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "func",
    [dynamic_segmented_ls, dynamic_segmented_ls_steps, dynamic_ls_by_period],
)
def test_zero_default_parameter_values_and_keyword_only_coefficients(func):
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    assert params
    for param in params:
        assert param.default is inspect.Parameter.empty, param.name
    for param in params[1:]:
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, param.name
    assert set(PARAM_NAMES) | {"slope_unit"} <= set(sig.parameters)


def test_ast_holds_zero_method_constants_and_reuses_ls_py():
    source = Path(dynamic_ls.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1}, (
        f"unexpected numeric constants in dynamic_ls.py: {numbers}"
    )

    # Verify zero default values in AST as well.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.args.defaults == []
            assert all(d is None for d in node.args.kw_defaults)

    # Verify G1 purity (no I/O, network, clock, or env reads) and no S/L reimplementation.
    forbidden_names = {
        "open",
        "read_text",
        "write_text",
        "load_folder",
        "os",
        "socket",
        "time",
        "datetime",
        "random",
        "sin",
        "atan",
        "radians",
    }
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            used_names.add(node.attr)
        elif isinstance(node, ast.alias):
            used_names.add(node.name)
    assert used_names.isdisjoint(forbidden_names), used_names & forbidden_names

    # Verify allowed imports only (stdlib + contracts + engine.erosion.ls).
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            top = node.module.split(".")[0]
            assert (
                top in sys.stdlib_module_names
                or node.module.startswith("contracts.")
                or node.module == "engine.erosion.ls"
            ), node.module


def test_g1_input_immutability_and_determinism():
    segments = [
        SlopeSegment(length_m=15.0, steepness=4.0),
        SlopeSegment(length_m=25.0, steepness=9.0),
    ]
    snapshot = list(segments)
    first = call_segmented(segments)
    second = call_segmented(segments)
    assert segments == snapshot
    assert first == second
