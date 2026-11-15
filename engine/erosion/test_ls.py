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
import json
import math
import re
import sys
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion import ls
from params.catalogue import check_record, load_folder, read_value
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
#
# Decision D124 of issue #77 fixed the expected values and the tolerance of
# [E3] before any run (docs/VALIDATION.md, "Section 10"): the 91 cells of
# Table 4-2 of AH703, worked in feet with the unit length D124 names, and the
# 19 "Moderate" values of m of Table 4-5, each within plus or minus 0.005.
#
# No value of the source is in this file. The expected values and the unit
# length in feet are read from the signed fixture E3_FIXTURE (path PROPOSED,
# format in validation/fixtures/README.md); the coefficients a1 to a4,
# s_break and b1 to b4 from the parameter catalogue (params/records/), by the
# identifiers of the table in LS.md. The test skips, naming the file and what
# is not signed, while the fixture is absent or unsigned.
#
# LS of a cell is S times L, each computed by this module and nothing else.
# m is not returned by the module: it is read back from L at a length ten
# times the unit length, where L = 10 ** m, so m = log10(L). Arithmetic of the
# form of L, not a coefficient.

REPOSITORY = HERE.parents[1]
E3_FIXTURE = REPOSITORY / "validation" / "fixtures" / "e3_ah703_tables.json"
E3_FIXTURE_NAME = E3_FIXTURE.relative_to(REPOSITORY).as_posix()
PARAMETER_RECORDS = REPOSITORY / "params" / "records"

# D124: the cells of each table, and the tolerance of both.
E3_TABLE_4_2_CELLS = 91
E3_TABLE_4_5_CELLS = 19
E3_TOLERANCE = 0.005

# D124: Table 4-2 is worked in feet.
E3_LENGTH_UNIT = "ft"
E3_UNIT_LENGTH_ID = "rusle_l_unit_length"

# The identifiers of the table "Parameters a person has to transcribe" of LS.md.
E3_COEFFICIENT_IDS = {
    "a1": "rusle_s_below_break_sine_coefficient",
    "a2": "rusle_s_below_break_constant",
    "a3": "rusle_s_at_or_above_break_sine_coefficient",
    "a4": "rusle_s_at_or_above_break_constant_subtracted",
    "s_break": "rusle_s_break_slope",
    "b1": "rusle_l_beta_sine_divisor",
    "b2": "rusle_l_beta_denominator_sine_coefficient",
    "b3": "rusle_l_beta_denominator_sine_exponent",
    "b4": "rusle_l_beta_denominator_constant",
}
STEEPNESS_ARGUMENTS = ("s_break", "a1", "a2", "a3", "a4")
LENGTH_ARGUMENTS = ("b1", "b2", "b3", "b4")

E3_WAITS_FOR = (
    f"[E3] waits for the signed fixture {E3_FIXTURE_NAME}: the 91 cells of "
    "AH703 Table 4-2 and the 19 Moderate values of m of Table 4-5 with the "
    "unit length in feet, as decision D124 of issue #77 fixes them, "
    "transcribed and signed in checked_by by a person (D34 of issue #77)"
)

# A number as the table prints it: digits, a point and decimals.
E3_PRINTED = re.compile(r"\d+\.\d+")

# m = log10(L) at a length this many unit lengths long.
E3_LENGTHS_FOR_M = 10.0


def _e3_is_text(item: object) -> bool:
    return isinstance(item, str) and item.strip() != ""


def e3_read_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict), f"{path.name}: the fixture is one JSON object"
    return fixture


def e3_unsigned(fixture: dict) -> list[str]:
    """Every part of the fixture that has no ``checked_by``, by name.

    The ``checked_by`` of the file signs both tables and the tolerance; the
    unit length in feet is a parameter record with its own.
    """
    missing = []
    if not _e3_is_text(fixture.get("checked_by")):
        missing.append("checked_by of the file (tables 4-2 and 4-5, tolerance)")
    length_unit = fixture.get("length_unit")
    record = length_unit.get("record") if isinstance(length_unit, dict) else None
    if not isinstance(record, dict):
        missing.append("length_unit.record (absent)")
    elif not _e3_is_text(record.get("checked_by")):
        missing.append("checked_by of length_unit.record")
    return missing


def e3_skip_reason(path: Path) -> str | None:
    """Why the test cannot run on ``path``, or ``None`` when it can."""
    if not path.is_file():
        return (
            f"{E3_WAITS_FOR}. The file is absent, so nothing is signed (no checked_by)"
        )
    missing = e3_unsigned(e3_read_fixture(path))
    if missing:
        return f"{E3_WAITS_FOR}. Not signed yet: " + "; ".join(missing)
    return None


def e3_catalogue_coefficients() -> tuple[dict[str, float], SlopeUnit] | str:
    """The coefficients of the catalogue and the unit of ``s_break``, or why not."""
    records, problems = load_folder(PARAMETER_RECORDS)
    if problems:
        return "the parameter catalogue does not load: " + "; ".join(problems)
    by_id = {
        record.get("id"): record
        for record in records.values()
        if isinstance(record, dict) and record.get("scope") == {}
    }
    absent = [i for i in E3_COEFFICIENT_IDS.values() if i not in by_id]
    if absent:
        return "not in the parameter catalogue with the empty scope: " + ", ".join(
            absent
        )
    values = {name: read_value(by_id[i]) for name, i in E3_COEFFICIENT_IDS.items()}
    missing = [name for name, value in values.items() if not isinstance(value, float)]
    if missing:
        return "missing in the parameter catalogue: " + ", ".join(missing)
    return values, SlopeUnit(by_id[E3_COEFFICIENT_IDS["s_break"]]["unit"])


def _e3_number(cell: dict, field: str, where: str) -> float:
    value = cell.get(field)
    assert isinstance(value, (int, float)) and not isinstance(value, bool), (
        f"{where}: '{field}' must be a number"
    )
    assert math.isfinite(value), f"{where}: '{field}' must be finite"
    return float(value)


def _e3_expected(cell: dict, field: str, where: str) -> float:
    expected = _e3_number(cell, field, where)
    printed = cell.get("printed")
    assert isinstance(printed, str) and E3_PRINTED.fullmatch(printed), (
        f"{where}: 'printed' must be the number as the table prints it"
    )
    assert float(printed) == expected, (
        f"{where}: '{field}' is not the number of 'printed'"
    )
    return expected


def _e3_cells(fixture: dict, table: str, count: int) -> list[dict]:
    entry = fixture.get(table)
    assert isinstance(entry, dict), f"'{table}' must be an object"
    cells = entry.get("cells")
    assert isinstance(cells, list) and all(isinstance(c, dict) for c in cells), (
        f"{table}.cells must be a list of objects"
    )
    assert len(cells) == count, (
        f"{table}: D124 names {count} cells, the fixture has {len(cells)}"
    )
    return cells


def _e3_unit_length(fixture: dict) -> float:
    record = fixture["length_unit"]["record"]
    problems = check_record(record)
    assert not problems, "length_unit.record: " + "; ".join(problems)
    assert record["id"] == E3_UNIT_LENGTH_ID, (
        f"length_unit.record must be '{E3_UNIT_LENGTH_ID}'"
    )
    assert record["unit"] == E3_LENGTH_UNIT, (
        f"length_unit.record: D124 works in '{E3_LENGTH_UNIT}'"
    )
    assert record["value"] is not None, "length_unit.record has no value"
    return float(record["value"])


def e3_failures(
    fixture: dict, coefficients: dict[str, float], s_break_unit: SlopeUnit
) -> list[str]:
    """Every value of a signed fixture outside its tolerance; a malformed fixture fails."""
    unit_length = _e3_unit_length(fixture)
    assert fixture.get("table_4_5_moderate_optional", {}).get("included") is True, (
        "table_4_5_moderate_optional.included: D124 includes Table 4-5"
    )
    tolerance = fixture.get("tolerance")
    assert isinstance(tolerance, dict), "'tolerance' must be an object"
    failures = [
        f"tolerance.{key} is {tolerance.get(key)!r}; D124 gives {E3_TOLERANCE}"
        for key in ("ls", "m")
        if tolerance.get(key) != E3_TOLERANCE
    ]
    steepness = {k: coefficients[k] for k in STEEPNESS_ARGUMENTS}
    length = {k: coefficients[k] for k in LENGTH_ARGUMENTS}

    seen: set = set()
    for n, cell in enumerate(_e3_cells(fixture, "table_4_2", E3_TABLE_4_2_CELLS)):
        where = f"table_4_2.cells[{n}]"
        slope = _e3_number(cell, "slope_percent", where)
        horizontal = _e3_number(cell, "horizontal_length_ft", where)
        expected = _e3_expected(cell, "ls_expected", where)
        assert (slope, horizontal) not in seen, f"{where}: the cell is given twice"
        seen.add((slope, horizontal))
        s = slope_steepness_factor(
            slope_steepness=slope,
            slope_unit=SlopeUnit.PERCENT,
            s_break_unit=s_break_unit,
            **steepness,
        )
        lf = slope_length_factor(
            slope_length=horizontal,
            slope_length_unit=E3_LENGTH_UNIT,
            lambda_unit=unit_length,
            lambda_unit_unit=E3_LENGTH_UNIT,
            slope_steepness=slope,
            slope_unit=SlopeUnit.PERCENT,
            **length,
        )
        if isinstance(s, ResultMissing) or isinstance(lf, ResultMissing):
            failures.append(
                f"{where} ({slope} %, {horizontal} ft): not computed ({s}, {lf})"
            )
        elif s * lf != pytest.approx(expected, abs=tolerance["ls"], rel=0):
            failures.append(
                f"{where} ({slope} %, {horizontal} ft): LS {s * lf!r}, expected {expected!r}"
            )

    seen = set()
    table = "table_4_5_moderate_optional"
    for n, cell in enumerate(_e3_cells(fixture, table, E3_TABLE_4_5_CELLS)):
        where = f"{table}.cells[{n}]"
        slope = _e3_number(cell, "slope_percent", where)
        expected = _e3_expected(cell, "m_expected_moderate", where)
        assert slope not in seen, f"{where}: the cell is given twice"
        seen.add(slope)
        lf = slope_length_factor(
            slope_length=E3_LENGTHS_FOR_M,
            slope_length_unit=E3_LENGTH_UNIT,
            lambda_unit=1.0,
            lambda_unit_unit=E3_LENGTH_UNIT,
            slope_steepness=slope,
            slope_unit=SlopeUnit.PERCENT,
            **length,
        )
        if isinstance(lf, ResultMissing):
            failures.append(f"{where} ({slope} %): m not computed ({lf})")
            continue
        m = math.log(lf) / math.log(E3_LENGTHS_FOR_M)
        if m != pytest.approx(expected, abs=tolerance["m"], rel=0):
            failures.append(f"{where} ({slope} %): m {m!r}, expected {expected!r}")
    return failures


def test_e3_slope_length_and_steepness_against_published_values():
    """[E3]: ``LS`` and ``m`` against AH703 Tables 4-2 and 4-5 (D124)."""
    reason = e3_skip_reason(E3_FIXTURE)
    if reason is not None:
        pytest.skip(reason)
    coefficients = e3_catalogue_coefficients()
    assert not isinstance(coefficients, str), coefficients
    failures = e3_failures(e3_read_fixture(E3_FIXTURE), *coefficients)
    assert not failures, "\n".join(failures)


# --- [E3]: the loader and the comparison on a PLACEHOLDER fixture -----------

# The PLACEHOLDER coefficients of this file; the unit length travels in the
# fixture, as in the signed one.
E3_PLACEHOLDER_COEFFICIENTS = {
    k: v
    for k, v in {**PLACEHOLDER_STEEPNESS, **PLACEHOLDER_LENGTH}.items()
    if k != "lambda_unit"
}
E3_PLACEHOLDER_UNIT_LENGTH = PLACEHOLDER_LENGTH["lambda_unit"]

# PLACEHOLDER: the expected m is computed at this many unit lengths, another
# length than e3_failures uses, so the two readings of m check each other.
E3_PLACEHOLDER_LENGTHS_FOR_M = 3.0


def _e3_placeholder_l(slope: float, length: float) -> float:
    return slope_length_factor(
        slope_length=length,
        slope_length_unit=E3_LENGTH_UNIT,
        lambda_unit=E3_PLACEHOLDER_UNIT_LENGTH,
        lambda_unit_unit=E3_LENGTH_UNIT,
        slope_steepness=slope,
        slope_unit=SlopeUnit.PERCENT,
        **{k: E3_PLACEHOLDER_COEFFICIENTS[k] for k in LENGTH_ARGUMENTS},
    )


def _e3_placeholder_ls(slope: float, horizontal: float) -> str:
    s = slope_steepness_factor(
        slope_steepness=slope,
        slope_unit=SlopeUnit.PERCENT,
        s_break_unit=SlopeUnit.PERCENT,
        **{k: E3_PLACEHOLDER_COEFFICIENTS[k] for k in STEEPNESS_ARGUMENTS},
    )
    return f"{s * _e3_placeholder_l(slope, horizontal):.2f}"


def _e3_placeholder_m(slope: float) -> str:
    length = E3_PLACEHOLDER_UNIT_LENGTH * E3_PLACEHOLDER_LENGTHS_FOR_M
    m = math.log(_e3_placeholder_l(slope, length)) / math.log(
        E3_PLACEHOLDER_LENGTHS_FOR_M
    )
    return f"{m:.2f}"


def e3_placeholder_fixture(*, checked: bool = True) -> dict:
    """A fixture in the documented format, with PLACEHOLDER numbers only.

    The slopes and lengths are made up (13 slopes and 7 lengths make the 91
    cells); the expected values are what this module computes on them with
    the PLACEHOLDER coefficients of this file, printed with two decimals, so
    the comparison passes by construction: it exercises the reading and the
    comparison, not the science.
    """
    slopes = [1.0 + n for n in range(13)]
    lengths = [11.0 * (n + 1) for n in range(7)]
    cells = []
    for slope in slopes:
        for horizontal in lengths:
            printed = _e3_placeholder_ls(slope, horizontal)
            cells.append(
                {
                    "slope_percent": slope,
                    "horizontal_length_ft": horizontal,
                    "ls_expected": float(printed),
                    "printed": printed,
                    "check_sheet_row": 0,
                }
            )
    m_cells = []
    for n in range(E3_TABLE_4_5_CELLS):
        slope = 0.5 + n
        printed = _e3_placeholder_m(slope)
        m_cells.append(
            {
                "slope_percent": slope,
                "m_expected_moderate": float(printed),
                "printed": printed,
                "check_sheet_row": 0,
            }
        )
    signature = "PLACEHOLDER person two" if checked else ""
    return {
        "test": "PLACEHOLDER fixture of the E3 machinery",
        "source": {
            "reference": "PLACEHOLDER, not a publication",
            "read": "PLACEHOLDER",
        },
        "transcribed_by": "PLACEHOLDER person one",
        "checked_by": signature,
        "table_4_2": {"locator": "PLACEHOLDER", "cells": cells},
        "table_4_5_moderate_optional": {
            "locator": "PLACEHOLDER",
            "included": True,
            "cells": m_cells,
        },
        "tolerance": {"ls": E3_TOLERANCE, "m": E3_TOLERANCE},
        "tolerance_rule": "PLACEHOLDER: D124",
        "length_unit": {
            "choice": "PLACEHOLDER",
            "record": {
                "id": E3_UNIT_LENGTH_ID,
                "scope": {},
                "value": E3_PLACEHOLDER_UNIT_LENGTH,
                "unit": E3_LENGTH_UNIT,
                "range": None,
                "range_missing_reason": "PLACEHOLDER: no range",
                "citation": {
                    "reference": "PLACEHOLDER reference, not a publication",
                    "locator": "PLACEHOLDER locator",
                },
                "transcribed_by": "PLACEHOLDER person one",
                "checked_by": signature,
            },
        },
    }


def _e3_write(tmp_path: Path, fixture: dict) -> Path:
    path = tmp_path / E3_FIXTURE.name
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def _e3_run(fixture: dict) -> list[str]:
    return e3_failures(fixture, E3_PLACEHOLDER_COEFFICIENTS, SlopeUnit.PERCENT)


def test_e3_absent_fixture_skips_naming_the_file_and_the_signature(tmp_path):
    reason = e3_skip_reason(tmp_path / E3_FIXTURE.name)
    assert reason is not None
    assert E3_FIXTURE_NAME in reason
    assert "absent" in reason
    assert "checked_by" in reason


def test_e3_unsigned_fixture_skips_naming_what_is_not_signed(tmp_path):
    reason = e3_skip_reason(_e3_write(tmp_path, e3_placeholder_fixture(checked=False)))
    assert reason is not None
    assert E3_FIXTURE_NAME in reason
    assert "checked_by of the file" in reason
    assert "checked_by of length_unit.record" in reason


def test_e3_unsigned_unit_length_alone_is_enough_to_skip(tmp_path):
    fixture = e3_placeholder_fixture()
    fixture["length_unit"]["record"]["checked_by"] = ""
    reason = e3_skip_reason(_e3_write(tmp_path, fixture))
    assert reason is not None
    assert "checked_by of length_unit.record" in reason
    assert "checked_by of the file" not in reason


def test_e3_signed_placeholder_fixture_runs_and_passes(tmp_path):
    path = _e3_write(tmp_path, e3_placeholder_fixture())
    assert e3_skip_reason(path) is None
    assert _e3_run(e3_read_fixture(path)) == []


def test_e3_value_outside_its_tolerance_fails():
    fixture = e3_placeholder_fixture()
    for table, field, n in (
        ("table_4_2", "ls_expected", 40),
        ("table_4_5_moderate_optional", "m_expected_moderate", 7),
    ):
        cell = fixture[table]["cells"][n]
        moved = f"{cell[field] + 0.01:.2f}"
        cell[field], cell["printed"] = float(moved), moved
    failures = _e3_run(fixture)
    assert len(failures) == 2
    assert failures[0].startswith("table_4_2.cells[40]")
    assert failures[1].startswith("table_4_5_moderate_optional.cells[7]")


def test_e3_a_tolerance_other_than_d124_fails():
    fixture = e3_placeholder_fixture()
    fixture["tolerance"]["ls"] = E3_TOLERANCE * 2
    assert _e3_run(fixture) == [
        f"tolerance.ls is {E3_TOLERANCE * 2!r}; D124 gives {E3_TOLERANCE}"
    ]


def test_e3_a_cell_count_other_than_d124_fails():
    fixture = e3_placeholder_fixture()
    fixture["table_4_2"]["cells"].pop()
    with pytest.raises(AssertionError, match="D124 names 91 cells"):
        _e3_run(fixture)


def test_e3_unit_length_in_another_unit_fails():
    fixture = e3_placeholder_fixture()
    fixture["length_unit"]["record"]["unit"] = "PLACEHOLDER other unit"
    with pytest.raises(AssertionError, match="D124 works in 'ft'"):
        _e3_run(fixture)


def test_e3_coefficients_are_read_by_the_identifiers_of_ls_md():
    rows = table_rows(section("Parameters a person has to transcribe"))
    listed = {row[1].strip("`") for row in rows}
    assert set(E3_COEFFICIENT_IDS.values()) | {E3_UNIT_LENGTH_ID} == listed
    found = e3_catalogue_coefficients()
    assert not isinstance(found, str), found
    assert set(found[0]) == set(E3_COEFFICIENT_IDS)
