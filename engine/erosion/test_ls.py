"""Acceptance test of unit l0/erosion-ls.

The cases are PROPOSED (blueprint section 3.7) and are listed in ``LS.md``
under "PROPOSED cases"; a test checks that the two lists agree.

**Every coefficient in this file is a PLACEHOLDER.** The numbers are plainly
not real: repeated digits, or the identity elements zero and one where the
arithmetic is done by hand. They are the coefficients of no method and no
case holds an expected value of the science. The test against published
values, [E3] of ``docs/VALIDATION.md``, is the skipped test at the end.

Run from the repository root: ``python -m pytest engine/erosion/test_ls.py``.
"""

from __future__ import annotations

import ast
import inspect
import math
import re
import sys
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import ls
from engine.erosion.ls import (
    REASON_UNIT_NOT_ACCEPTED,
    SlopeUnit,
    slope_length_factor,
    slope_steepness_factor,
)

HERE = Path(__file__).parent
LS_MD = HERE / "LS.md"

# Rounding of floating-point arithmetic only. Not a tolerance of the
# validation protocol.
FLOAT_NOISE = 1e-12

UNITS = list(SlopeUnit)

# PLACEHOLDER coefficients of the steepness forms. Not real values.
PLACEHOLDER_STEEPNESS = {
    "s_break": 55.0,
    "a1": 11.0,
    "a2": 22.0,
    "a3": 33.0,
    "a4": 44.0,
}

# PLACEHOLDER coefficients of the length forms. Not real values.
PLACEHOLDER_LENGTH = {
    "lambda_unit": 66.0,
    "b1": 0.11,
    "b2": 2.2,
    "b3": 3.3,
    "b4": 4.4,
}
PLACEHOLDER_LENGTH_UNIT = "PLACEHOLDER_length_unit"

# PLACEHOLDER slope and length of a field. Not a real field.
PLACEHOLDER_SLOPE = 7.0
PLACEHOLDER_LENGTH_OF_FIELD = 777.0

STEEPNESS_NUMBERS = ["slope_steepness", "s_break", "a1", "a2", "a3", "a4"]
LENGTH_NUMBERS = [
    "slope_length",
    "lambda_unit",
    "slope_steepness",
    "b1",
    "b2",
    "b3",
    "b4",
]
COEFFICIENTS = {
    "a1",
    "a2",
    "a3",
    "a4",
    "s_break",
    "lambda_unit",
    "b1",
    "b2",
    "b3",
    "b4",
}

NOT_FINITE = [math.nan, math.inf, -math.inf]
NOT_A_NUMBER_OR_MISSING = [None, "1.0", True, [1.0]]


def steepness(**changes):
    """``slope_steepness_factor`` with the PLACEHOLDER arguments, some replaced."""
    arguments = {
        "slope_steepness": PLACEHOLDER_SLOPE,
        "slope_unit": SlopeUnit.PERCENT,
        "s_break_unit": SlopeUnit.PERCENT,
        **PLACEHOLDER_STEEPNESS,
    }
    arguments.update(changes)
    return slope_steepness_factor(**arguments)


def length(**changes):
    """``slope_length_factor`` with the PLACEHOLDER arguments, some replaced."""
    arguments = {
        "slope_length": PLACEHOLDER_LENGTH_OF_FIELD,
        "slope_length_unit": PLACEHOLDER_LENGTH_UNIT,
        "lambda_unit_unit": PLACEHOLDER_LENGTH_UNIT,
        "slope_steepness": PLACEHOLDER_SLOPE,
        "slope_unit": SlopeUnit.PERCENT,
        **PLACEHOLDER_LENGTH,
    }
    arguments.update(changes)
    return slope_length_factor(**arguments)


def sine(slope: float, unit: SlopeUnit) -> float:
    """The sine of the slope angle, written a second time for the test.

    Percent and ratio are rise over horizontal distance, so the sine is the
    rise over the hypotenuse.
    """
    if unit is SlopeUnit.PERCENT:
        return slope / math.hypot(100.0, slope)
    if unit is SlopeUnit.RATIO:
        return slope / math.hypot(1.0, slope)
    if unit is SlopeUnit.ANGLE_DEGREES:
        return math.sin(math.radians(slope))
    return math.sin(slope)


def named(missing: ResultMissing) -> set[str]:
    """The arguments that the detail of a missing result names."""
    return {part.split()[0] for part in missing.detail.split("; ")}


def assert_missing(result, reason: str) -> None:
    """A result that is not computed: the ``Missing`` of the results contract, never a number."""
    assert type(result) is ResultMissing
    assert not isinstance(result, (int, float))
    assert result.reason == reason
    assert result.detail


def a_missing(shape, reason: str = "NOT_AVAILABLE"):
    return shape(reason=reason, detail="PLACEHOLDER: not transcribed")


# --- steepness: the branch --------------------------------------------------

BREAK = PLACEHOLDER_STEEPNESS["s_break"]
BELOW = {
    "far-below": BREAK - 44.0,
    "just-below": math.nextafter(BREAK, -math.inf),
}
AT_OR_ABOVE = {
    "exactly-at": BREAK,
    "just-above": math.nextafter(BREAK, math.inf),
    "far-above": BREAK + 22.0,
}


@pytest.mark.parametrize("unit", UNITS, ids=lambda unit: unit.value)
@pytest.mark.parametrize("where", list(BELOW))
def test_steepness_below_the_break_slope_uses_the_first_form(unit, where):
    slope = BELOW[where]
    result = steepness(slope_steepness=slope, slope_unit=unit, s_break_unit=unit)
    expected = (
        PLACEHOLDER_STEEPNESS["a1"] * sine(slope, unit) + PLACEHOLDER_STEEPNESS["a2"]
    )
    assert result == pytest.approx(expected, rel=FLOAT_NOISE)
    # With these placeholders the first form is positive and the second negative.
    assert result > 0


@pytest.mark.parametrize("unit", UNITS, ids=lambda unit: unit.value)
@pytest.mark.parametrize("where", list(AT_OR_ABOVE))
def test_steepness_at_or_above_the_break_slope_uses_the_second_form(unit, where):
    slope = AT_OR_ABOVE[where]
    result = steepness(slope_steepness=slope, slope_unit=unit, s_break_unit=unit)
    expected = (
        PLACEHOLDER_STEEPNESS["a3"] * sine(slope, unit) - PLACEHOLDER_STEEPNESS["a4"]
    )
    assert result == pytest.approx(expected, rel=FLOAT_NOISE)
    assert result < 0


def test_steepness_by_hand_on_a_three_four_five_slope():
    # Rise 3 over run 4: the sine is 3 / 5. Arithmetic on PLACEHOLDER
    # coefficients: 11 * 0.6 + 22 below the break, 33 * 0.6 - 44 at it.
    slope = 0.75
    below = steepness(
        slope_steepness=slope, slope_unit=SlopeUnit.RATIO, s_break_unit=SlopeUnit.RATIO
    )
    at = steepness(
        slope_steepness=slope,
        slope_unit=SlopeUnit.RATIO,
        s_break=slope,
        s_break_unit=SlopeUnit.RATIO,
    )
    assert below == pytest.approx(28.6, rel=FLOAT_NOISE)
    assert at == pytest.approx(-24.2, rel=FLOAT_NOISE)


@pytest.mark.parametrize(
    ("slope", "read", "not_read"),
    [(BELOW["far-below"], ("a1", "a2"), ("a3", "a4")),
     (AT_OR_ABOVE["far-above"], ("a3", "a4"), ("a1", "a2"))],
    ids=["below", "above"],
)  # fmt: skip
def test_steepness_each_form_reads_its_own_two_coefficients(slope, read, not_read):
    reference = steepness(slope_steepness=slope)
    for name in read:
        changed = steepness(
            slope_steepness=slope, **{name: PLACEHOLDER_STEEPNESS[name] + 5.0}
        )
        assert changed != reference
    for name in not_read:
        changed = steepness(
            slope_steepness=slope, **{name: PLACEHOLDER_STEEPNESS[name] + 5.0}
        )
        assert changed == reference


def test_the_four_slope_units_describe_the_same_slope():
    # One slope written four ways: 45 degrees is a rise equal to the run.
    same_slope = {
        SlopeUnit.ANGLE_DEGREES: 45.0,
        SlopeUnit.ANGLE_RADIANS: math.pi / 4,
        SlopeUnit.RATIO: 1.0,
        SlopeUnit.PERCENT: 100.0,
    }
    assert set(same_slope) == set(SlopeUnit)
    steepness_values = [
        steepness(
            slope_steepness=slope,
            slope_unit=unit,
            s_break=slope + 5.0,
            s_break_unit=unit,
        )
        for unit, slope in same_slope.items()
    ]
    length_values = [
        length(slope_steepness=slope, slope_unit=unit)
        for unit, slope in same_slope.items()
    ]
    for values in (steepness_values, length_values):
        assert all(isinstance(value, float) for value in values)
        assert values == pytest.approx([values[0]] * len(values), rel=FLOAT_NOISE)


# --- length: the three forms ------------------------------------------------


@pytest.mark.parametrize("unit", UNITS, ids=lambda unit: unit.value)
@pytest.mark.parametrize("slope", [0.0, PLACEHOLDER_SLOPE, 77.0])
def test_length_factor_is_one_when_the_length_equals_the_unit_length(unit, slope):
    result = length(
        slope_length=PLACEHOLDER_LENGTH["lambda_unit"],
        slope_steepness=slope,
        slope_unit=unit,
    )
    assert isinstance(result, float)
    assert result == 1.0


@pytest.mark.parametrize("unit", UNITS, ids=lambda unit: unit.value)
@pytest.mark.parametrize("slope_length", [6.0, 66.0, PLACEHOLDER_LENGTH_OF_FIELD])
def test_length_factor_follows_the_three_forms(unit, slope_length):
    slope = PLACEHOLDER_SLOPE
    sin_theta = sine(slope, unit)
    beta = (sin_theta / PLACEHOLDER_LENGTH["b1"]) / (
        PLACEHOLDER_LENGTH["b2"] * sin_theta ** PLACEHOLDER_LENGTH["b3"]
        + PLACEHOLDER_LENGTH["b4"]
    )
    m = beta / (1 + beta)
    expected = (slope_length / PLACEHOLDER_LENGTH["lambda_unit"]) ** m

    result = length(slope_length=slope_length, slope_steepness=slope, slope_unit=unit)
    assert result == pytest.approx(expected, rel=FLOAT_NOISE)


def test_length_by_hand_on_a_three_four_five_slope():
    # Rise 3 over run 4: the sine is 0.6. PLACEHOLDER coefficients that are
    # identity elements: b2 = 0 and b4 = 1 leave beta = 0.6 / b1.
    by_hand = {
        "slope_steepness": 0.75,
        "slope_unit": SlopeUnit.RATIO,
        "lambda_unit": 1.0,
        "b2": 0.0,
        "b3": 7777.0,
        "b4": 1.0,
    }
    # beta = 1, so m = 1 / 2: the square root of 4.
    assert length(slope_length=4.0, b1=0.6, **by_hand) == pytest.approx(
        2.0, rel=FLOAT_NOISE
    )
    # beta = 3, so m = 3 / 4: 16 to the power 3 / 4.
    assert length(slope_length=16.0, b1=0.2, **by_hand) == pytest.approx(
        8.0, rel=FLOAT_NOISE
    )


@pytest.mark.parametrize("name", ["lambda_unit", "b1", "b2", "b3", "b4"])
def test_length_every_coefficient_changes_the_result(name):
    reference = length()
    changed = length(**{name: PLACEHOLDER_LENGTH[name] + 5.0})
    assert isinstance(reference, float)
    assert isinstance(changed, float)
    assert changed != reference


# --- missing arguments ------------------------------------------------------


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize(
    "slope", [BELOW["far-below"], AT_OR_ABOVE["far-above"]], ids=["below", "above"]
)
@pytest.mark.parametrize("name", STEEPNESS_NUMBERS)
def test_steepness_missing_argument_gives_missing_input_that_names_it(name, slope, shape):  # fmt: skip
    arguments = {"slope_steepness": slope, name: a_missing(shape)}
    result = steepness(**arguments)
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {name}


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("name", LENGTH_NUMBERS)
def test_length_missing_argument_gives_missing_input_that_names_it(name, shape):
    result = length(**{name: a_missing(shape)})
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {name}


def test_missing_length_stays_missing_also_when_the_factor_would_be_one():
    # A missing unit length is not read as the length of the field.
    result = length(lambda_unit=a_missing(InputMissing))
    assert_missing(result, "MISSING_INPUT")
    result = length(
        slope_length=a_missing(InputMissing), lambda_unit=a_missing(InputMissing)
    )
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {"slope_length", "lambda_unit"}


def test_several_missing_arguments_are_all_named_with_their_reasons():
    result = steepness(
        slope_steepness=InputMissing(reason="NOT_DECLARED"),
        a3=InputMissing(reason="NO_COVERAGE", detail="PLACEHOLDER upstream detail"),
        a1=math.nan,
    )
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {"slope_steepness", "a3"}
    assert "NOT_DECLARED" in result.detail
    assert "NO_COVERAGE" in result.detail
    assert "PLACEHOLDER upstream detail" in result.detail


# --- arguments that are not finite numbers ----------------------------------


@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "minus-inf"])
@pytest.mark.parametrize("name", STEEPNESS_NUMBERS)
def test_steepness_argument_that_is_not_finite_is_not_computed(name, number):
    result = steepness(**{name: number})
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {name}


@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "minus-inf"])
@pytest.mark.parametrize("name", LENGTH_NUMBERS)
def test_length_argument_that_is_not_finite_is_not_computed(name, number):
    result = length(**{name: number})
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {name}


def test_integer_too_large_for_a_float_is_not_computed():
    result = steepness(slope_steepness=10**400)
    assert_missing(result, "NOT_COMPUTABLE")
    assert named(result) == {"slope_steepness"}


# --- forms that give no finite real number ----------------------------------


def test_steepness_that_overflows_is_not_computed():
    largest = sys.float_info.max
    result = steepness(slope_steepness=BELOW["far-below"], a1=largest, a2=largest)
    assert_missing(result, "NOT_COMPUTABLE")
    assert "S" in result.detail.split()


SINE_OF_ONE_RADIAN = math.sin(1.0)


@pytest.mark.parametrize(
    ("changes", "step"),
    [
        ({"b1": 0.0}, "beta"),
        ({"b2": 0.0, "b4": 0.0}, "beta"),
        ({"slope_steepness": -PLACEHOLDER_SLOPE}, "beta"),
        (
            {
                "slope_steepness": 1.0,
                "slope_unit": SlopeUnit.ANGLE_RADIANS,
                "b1": -SINE_OF_ONE_RADIAN,
                "b2": 0.0,
                "b4": 1.0,
            },
            "m",
        ),
        ({"lambda_unit": 0.0}, "L"),
        ({"slope_length": -PLACEHOLDER_LENGTH_OF_FIELD}, "L"),
    ],
    ids=[
        "division-by-b1-zero",
        "denominator-of-beta-zero",
        "negative-sine-to-a-fractional-power",
        "one-plus-beta-zero",
        "unit-length-zero",
        "negative-length-to-a-fractional-power",
    ],
)
def test_length_form_without_a_finite_real_result_is_not_computed(changes, step):
    result = length(**changes)
    assert_missing(result, "NOT_COMPUTABLE")
    assert step in result.detail.split()


# --- units ------------------------------------------------------------------


def test_steepness_break_slope_in_another_unit_is_not_computed():
    result = steepness(slope_unit=SlopeUnit.PERCENT, s_break_unit=SlopeUnit.RATIO)
    assert_missing(result, REASON_UNIT_NOT_ACCEPTED)
    assert SlopeUnit.PERCENT.value in result.detail
    assert SlopeUnit.RATIO.value in result.detail


def test_length_and_unit_length_in_different_units_are_not_computed():
    result = length(lambda_unit_unit="PLACEHOLDER_another_length_unit")
    assert_missing(result, REASON_UNIT_NOT_ACCEPTED)
    assert PLACEHOLDER_LENGTH_UNIT in result.detail
    assert "PLACEHOLDER_another_length_unit" in result.detail


def test_a_missing_argument_is_reported_before_a_unit_that_differs():
    result = steepness(
        a2=a_missing(InputMissing),
        slope_unit=SlopeUnit.PERCENT,
        s_break_unit=SlopeUnit.RATIO,
    )
    assert_missing(result, "MISSING_INPUT")
    assert named(result) == {"a2"}


# --- defects of the caller (G5) ---------------------------------------------


@pytest.mark.parametrize(
    "item", NOT_A_NUMBER_OR_MISSING, ids=["none", "text", "boolean", "list"]
)
@pytest.mark.parametrize("name", STEEPNESS_NUMBERS)
def test_steepness_argument_of_another_type_raises_type_error(name, item):
    with pytest.raises(TypeError, match=name):
        steepness(**{name: item})


@pytest.mark.parametrize(
    "item", NOT_A_NUMBER_OR_MISSING, ids=["none", "text", "boolean", "list"]
)
@pytest.mark.parametrize("name", LENGTH_NUMBERS)
def test_length_argument_of_another_type_raises_type_error(name, item):
    with pytest.raises(TypeError, match=name):
        length(**{name: item})


@pytest.mark.parametrize("item", [None, "percent", 1.0], ids=["none", "text", "number"])
def test_unit_argument_of_another_type_raises_type_error(item):
    with pytest.raises(TypeError, match="slope_unit"):
        steepness(slope_unit=item)
    with pytest.raises(TypeError, match="s_break_unit"):
        steepness(s_break_unit=item)
    with pytest.raises(TypeError, match="slope_unit"):
        length(slope_unit=item)
    if not isinstance(item, str):
        with pytest.raises(TypeError, match="slope_length_unit"):
            length(slope_length_unit=item)
        with pytest.raises(TypeError, match="lambda_unit_unit"):
            length(lambda_unit_unit=item)


# --- no coefficient in the module -------------------------------------------


@pytest.mark.parametrize("function", [slope_steepness_factor, slope_length_factor])
def test_every_argument_is_passed_by_name_and_none_has_a_default(function):
    parameters = inspect.signature(function).parameters.values()
    assert parameters
    for parameter in parameters:
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, parameter.name
        assert parameter.default is inspect.Parameter.empty, parameter.name


def test_every_coefficient_of_the_issue_is_an_argument():
    arguments = set(inspect.signature(slope_steepness_factor).parameters) | set(
        inspect.signature(slope_length_factor).parameters
    )
    assert COEFFICIENTS <= arguments


def test_the_module_holds_no_number_but_those_of_the_forms():
    # The only numbers written in ls.py: the 1 of "1 + beta", which is part
    # of the form given in the issue, and the 100 that "percent" means.
    tree = ast.parse(Path(ls.__file__).read_text(encoding="utf-8"))
    numbers = sorted(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    )
    assert numbers == [1, 100.0]


# --- LS.md ------------------------------------------------------------------


def section(title: str) -> str:
    """The text of one second-level section of LS.md."""
    text = LS_MD.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S
    )
    assert match, f"LS.md has no section '{title}'"
    return match.group(1)


def table_rows(text: str) -> list[list[str]]:
    """The cells of the body rows of the first table in ``text``."""
    lines = [line for line in text.splitlines() if line.startswith("|")]
    assert len(lines) > 2
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[2:]]


def test_ls_md_lists_every_coefficient_with_an_empty_value():
    text = section("Parameters a person has to transcribe")
    header = [
        cell.strip()
        for cell in next(line for line in text.splitlines() if line.startswith("|"))
        .strip("|")
        .split("|")
    ]
    assert header[0] == "Coefficient"
    assert header[-1] == "Value"
    rows = table_rows(text)
    assert all(len(row) == len(header) for row in rows)
    assert sorted(row[0].strip("`") for row in rows) == sorted(COEFFICIENTS)
    for row in rows:
        assert row[-1] == "", f"{row[0]}: a session writes no value"
        assert all(cell for cell in row[:-1]), f"{row[0]}: an empty cell"
    identifiers = [row[1].strip("`") for row in rows]
    assert len(set(identifiers)) == len(identifiers)
    for identifier in identifiers:
        # params/README.md: starts with a letter; letters, digits and "_" only.
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", identifier), identifier


def test_ls_md_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written


# --- [E3] -------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "[E3] of docs/VALIDATION.md waits for two things, both transcribed by a "
        "person and checked by a second person: (1) the coefficients a1, a2, a3, "
        "a4, s_break, lambda_unit, b1, b2, b3 and b4 as records of the parameter "
        "catalogue, from source S2 or S3 of docs/METHODS.md (the table of "
        "engine/erosion/LS.md); (2) entry E3 of docs/VALIDATION.md: its "
        "definition, its expected values, its tolerance and its source. All of "
        "them are OPEN today."
    )
)
def test_e3_slope_length_and_steepness_against_published_values():
    """[E3]: ``S`` and ``L`` against the values published in the source.

    To write when both parts of the skip reason exist: read the coefficients
    from the parameter catalogue, compute ``S`` and ``L`` for the slopes and
    lengths that entry E3 names, and compare with its expected values within
    its tolerance. No value of this test is written by a session.
    """
    pytest.fail("[E3] is not written: see the skip reason")
