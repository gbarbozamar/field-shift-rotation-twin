"""Acceptance test of the annual soil-loss product (engine/erosion/equation.py).

Run with ``python -m pytest engine/erosion/test_equation.py`` from the
repository root.

The cases are PROPOSED (blueprint section 3.7) and are listed with the same
codes in engine/erosion/EQUATION.md under "PROPOSED cases".

Every number and every unit string in this file is a PLACEHOLDER: it means
nothing, it is not a value or a unit of the method, and no case holds an
expected value of the science. The numbers are chosen so that every product
is exact and can be checked by hand.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
import math
import sys
from pathlib import Path
from typing import get_args

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.results import models as results_models
from contracts.results.models import Missing, ReasonCode
from engine.erosion import equation
from engine.erosion.equation import (
    FACTOR_NAMES,
    AcceptedUnits,
    Factor,
    annual_soil_loss,
)

WORD = "PLACEHOLDER"

# PLACEHOLDER unit strings, one per factor, all different from each other.
UNITS = AcceptedUnits(
    r="PLACEHOLDER unit of r",
    k="PLACEHOLDER unit of k",
    ls="PLACEHOLDER unit of ls",
    c="PLACEHOLDER unit of c",
    p="PLACEHOLDER unit of p",
)
OTHER_UNIT = "PLACEHOLDER another unit"

# PLACEHOLDER numbers: five different primes, so that a factor left out or
# multiplied twice changes the product. By hand: 2 x 3 = 6; 6 x 5 = 30;
# 30 x 7 = 210; 210 x 11 = 2310.
NUMBERS = {"r": 2.0, "k": 3.0, "ls": 5.0, "c": 7.0, "p": 11.0}  # PLACEHOLDER
PRODUCT = 2310.0  # PLACEHOLDER

# PLACEHOLDER numbers with fractions. By hand: 0.5 x 4 = 2; 2 x 0.25 = 0.5;
# 0.5 x 8 = 4; 4 x 1 = 4.
FRACTIONS = {"r": 0.5, "k": 4.0, "ls": 0.25, "c": 8.0, "p": 1.0}  # PLACEHOLDER
FRACTIONS_PRODUCT = 4.0  # PLACEHOLDER

SCALES = (2.0, 0.5, 3.0)  # PLACEHOLDER

REASON_CODES = get_args(ReasonCode)  # the closed list of convention C3.2

# Question Q11 of contracts/ENTRYPOINTS.md is not decided, so no case says
# which reason code the unit guard uses. The cases that do not look at the
# reason pass this one; case EQ6a passes every code of C3.2 in turn.
GUARD_REASON = "NOT_APPLICABLE"  # PLACEHOLDER choice, not a decision

A_FACTOR_REASON = "NOT_DECLARED"  # PLACEHOLDER choice
A_DETAIL = "PLACEHOLDER detail"

NOT_FINITE = (math.nan, math.inf, -math.inf)

PAIRS = list(itertools.combinations(FACTOR_NAMES, 2))


def factors(numbers=None, **changed):
    """The five factors in their accepted units, with some of them replaced."""
    numbers = NUMBERS if numbers is None else numbers
    given = {
        name: Factor(value=numbers[name], unit=getattr(UNITS, name))
        for name in FACTOR_NAMES
    }
    given.update(changed)
    return given


def compute(given, *, accepted_units=UNITS, unit_guard_reason=GUARD_REASON):
    return annual_soil_loss(
        **given, accepted_units=accepted_units, unit_guard_reason=unit_guard_reason
    )


def missing(reason=A_FACTOR_REASON, detail=None):
    """A factor that has no number, in its accepted unit."""
    return lambda name: Factor(
        value=Missing(reason=reason, detail=detail), unit=getattr(UNITS, name)
    )


def with_missing(*names, numbers=None, reason=A_FACTOR_REASON, detail=None):
    make = missing(reason, detail)
    return factors(numbers, **{name: make(name) for name in names})


def with_unit(*names, unit=OTHER_UNIT, numbers=None):
    numbers = NUMBERS if numbers is None else numbers
    return factors(
        numbers, **{name: Factor(value=numbers[name], unit=unit) for name in names}
    )


def with_number(name, number):
    return factors(**{name: Factor(value=number, unit=getattr(UNITS, name))})


def assert_missing(result, reason):
    """The result is the ``Missing`` of the results contract, with this reason."""
    assert isinstance(result, Missing), f"expected a Missing, got {result!r}"
    assert result.reason == reason
    assert result.detail is not None
    return result.detail


def assert_names_only(detail, *names):
    """The detail names these factors, in the order of M1.1, and no other."""
    named = [name for name in FACTOR_NAMES if f"'{name}'" in detail]
    assert named == [name for name in FACTOR_NAMES if name in names], detail
    positions = [detail.index(f"'{name}'") for name in named]
    assert positions == sorted(positions), detail


# --- EQ1: the product of five factors ----------------------------------------


def test_eq1a_product_of_five_factors():
    result = compute(factors())
    assert type(result) is float
    assert result == PRODUCT


def test_eq1b_product_of_five_factors_with_fractions():
    assert compute(factors(FRACTIONS)) == FRACTIONS_PRODUCT


def test_eq1c_whole_numbers_give_the_same_product_as_floats():
    whole = {name: int(number) for name, number in NUMBERS.items()}
    result = compute(factors(whole))
    assert type(result) is float
    assert result == PRODUCT


@pytest.mark.parametrize("left_out", FACTOR_NAMES)
def test_eq1d_every_factor_takes_part_in_the_product(left_out):
    """Setting one factor to one divides the product by that factor."""
    result = compute(with_number(left_out, 1.0))
    assert result == PRODUCT / NUMBERS[left_out]


# --- EQ2: any factor equal to zero gives zero --------------------------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize("zero", [0.0, 0])
def test_eq2a_a_factor_equal_to_zero_gives_zero(name, zero):
    result = compute(with_number(name, zero))
    assert type(result) is float
    assert result == 0.0


def test_eq2b_every_factor_equal_to_zero_gives_zero():
    result = compute(factors(dict.fromkeys(FACTOR_NAMES, 0.0)))
    assert type(result) is float
    assert result == 0.0


# --- EQ3: multiplying one factor multiplies the result ------------------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("numbers", [NUMBERS, FRACTIONS])
def test_eq3_multiplying_one_factor_multiplies_the_result(name, scale, numbers):
    base = compute(factors(numbers))
    scaled = factors(
        numbers,
        **{name: Factor(value=numbers[name] * scale, unit=getattr(UNITS, name))},
    )
    assert compute(scaled) == base * scale


# --- EQ4: the order in which the factors are given ---------------------------


def in_every_order(given):
    """The same named factors, as keyword arguments in each possible order."""
    for order in itertools.permutations(FACTOR_NAMES):
        yield {name: given[name] for name in order}


def test_eq4a_the_order_of_the_factors_does_not_change_the_product():
    results = {compute(given) for given in in_every_order(factors())}
    assert results == {PRODUCT}


def test_eq4b_the_order_of_the_factors_does_not_change_a_missing_result():
    cases = [
        with_missing("c", "k"),
        with_unit("p", "r"),
        factors(
            ls=Factor(value=math.inf, unit=UNITS.ls),
            r=Factor(value=math.inf, unit=UNITS.r),
        ),
    ]
    for given in cases:
        results = {compute(ordered) for ordered in in_every_order(given)}
        assert len(results) == 1
        assert isinstance(results.pop(), Missing)


def test_eq4c_the_order_of_the_fields_of_accepted_units_does_not_matter():
    reordered = AcceptedUnits(p=UNITS.p, c=UNITS.c, ls=UNITS.ls, k=UNITS.k, r=UNITS.r)
    assert compute(factors(), accepted_units=reordered) == PRODUCT


# --- EQ5: a missing factor gives a missing result that names it ---------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize("reason", REASON_CODES)
def test_eq5a_a_missing_factor_gives_a_missing_result_that_names_it(name, reason):
    result = compute(with_missing(name, reason=reason, detail=A_DETAIL))
    detail = assert_missing(result, "MISSING_INPUT")
    assert_names_only(detail, name)
    # The factor keeps its own reason: it travels in the detail.
    assert reason in detail
    assert A_DETAIL in detail


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq5b_a_missing_factor_without_detail_is_named_too(name):
    detail = assert_missing(compute(with_missing(name)), "MISSING_INPUT")
    assert_names_only(detail, name)
    assert A_FACTOR_REASON in detail


@pytest.mark.parametrize("pair", PAIRS)
def test_eq5c_every_missing_factor_is_named(pair):
    detail = assert_missing(compute(with_missing(*pair)), "MISSING_INPUT")
    assert_names_only(detail, *pair)


def test_eq5d_all_factors_missing():
    detail = assert_missing(compute(with_missing(*FACTOR_NAMES)), "MISSING_INPUT")
    assert_names_only(detail, *FACTOR_NAMES)


@pytest.mark.parametrize("pair", itertools.permutations(FACTOR_NAMES, 2))
def test_eq5e_a_zero_factor_does_not_turn_a_missing_factor_into_zero(pair):
    zero, absent = pair
    given = with_missing(absent)
    given[zero] = Factor(value=0.0, unit=getattr(UNITS, zero))
    detail = assert_missing(compute(given), "MISSING_INPUT")
    assert_names_only(detail, absent)


# --- EQ6: the unit guard -----------------------------------------------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize("reason", REASON_CODES)
def test_eq6a_a_factor_in_another_unit_is_not_multiplied(name, reason):
    result = compute(with_unit(name), unit_guard_reason=reason)
    detail = assert_missing(result, reason)
    assert_names_only(detail, name)
    assert OTHER_UNIT in detail
    assert getattr(UNITS, name) in detail


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize(
    "change",
    [str.lower, str.upper, lambda unit: unit + " ", lambda unit: " " + unit],
    ids=["lower case", "upper case", "space after", "space before"],
)
def test_eq6b_unit_strings_are_compared_exactly_as_written(name, change):
    unit = change(getattr(UNITS, name))
    detail = assert_missing(compute(with_unit(name, unit=unit)), GUARD_REASON)
    assert_names_only(detail, name)


@pytest.mark.parametrize("pair", PAIRS)
def test_eq6c_the_accepted_unit_of_another_factor_is_not_accepted(pair):
    first, second = pair
    given = factors(
        **{
            first: Factor(value=NUMBERS[first], unit=getattr(UNITS, second)),
            second: Factor(value=NUMBERS[second], unit=getattr(UNITS, first)),
        }
    )
    detail = assert_missing(compute(given), GUARD_REASON)
    assert_names_only(detail, first, second)


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq6d_the_accepted_unit_is_the_one_the_caller_supplies(name):
    """The same factors pass or not according to ``accepted_units`` alone."""
    given = with_unit(name)
    accepting = dataclasses.replace(UNITS, **{name: OTHER_UNIT})
    assert compute(given, accepted_units=accepting) == PRODUCT
    assert_missing(compute(given, accepted_units=UNITS), GUARD_REASON)
    assert_missing(compute(factors(), accepted_units=accepting), GUARD_REASON)


@pytest.mark.parametrize("pair", itertools.permutations(FACTOR_NAMES, 2))
def test_eq6e_a_zero_factor_does_not_turn_a_unit_mismatch_into_zero(pair):
    zero, other_unit = pair
    given = with_unit(other_unit)
    given[zero] = Factor(value=0.0, unit=getattr(UNITS, zero))
    detail = assert_missing(compute(given), GUARD_REASON)
    assert_names_only(detail, other_unit)


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq6f_a_zero_factor_in_another_unit_is_not_multiplied(name):
    given = factors(**{name: Factor(value=0.0, unit=OTHER_UNIT)})
    detail = assert_missing(compute(given), GUARD_REASON)
    assert_names_only(detail, name)


# --- EQ7: a factor that is not a finite number --------------------------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "-inf"])
def test_eq7a_a_factor_that_is_not_finite_is_not_multiplied(name, number):
    detail = assert_missing(compute(with_number(name, number)), "NOT_COMPUTABLE")
    assert_names_only(detail, name)


@pytest.mark.parametrize("pair", itertools.permutations(FACTOR_NAMES, 2))
@pytest.mark.parametrize("number", NOT_FINITE, ids=["nan", "inf", "-inf"])
def test_eq7b_a_zero_factor_does_not_turn_a_non_finite_factor_into_zero(pair, number):
    zero, not_finite = pair
    given = with_number(not_finite, number)
    given[zero] = Factor(value=0.0, unit=getattr(UNITS, zero))
    detail = assert_missing(compute(given), "NOT_COMPUTABLE")
    assert_names_only(detail, not_finite)


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq7c_a_whole_number_too_large_to_be_a_float_is_not_multiplied(name):
    too_large = int(sys.float_info.max) * int(sys.float_info.max)
    detail = assert_missing(compute(with_number(name, too_large)), "NOT_COMPUTABLE")
    assert_names_only(detail, name)


@pytest.mark.parametrize("pair", PAIRS)
def test_eq7d_a_product_that_is_not_finite_is_missing(pair):
    """Two finite factors whose product is beyond the largest float."""
    given = factors(dict.fromkeys(FACTOR_NAMES, 1.0))
    for name in pair:
        given[name] = Factor(value=sys.float_info.max, unit=getattr(UNITS, name))
    detail = assert_missing(compute(given), "NOT_COMPUTABLE")
    assert_names_only(detail)


# --- EQ8: more than one reason at once ---------------------------------------


@pytest.mark.parametrize("pair", itertools.permutations(FACTOR_NAMES, 2))
def test_eq8a_a_missing_factor_is_reported_before_a_unit_mismatch(pair):
    absent, other_unit = pair
    given = with_unit(other_unit)
    given[absent] = missing()(absent)
    detail = assert_missing(compute(given), "MISSING_INPUT")
    assert_names_only(detail, absent)


@pytest.mark.parametrize("pair", itertools.permutations(FACTOR_NAMES, 2))
def test_eq8b_a_unit_mismatch_is_reported_before_a_non_finite_factor(pair):
    other_unit, not_finite = pair
    given = with_unit(other_unit)
    given[not_finite] = Factor(value=math.nan, unit=getattr(UNITS, not_finite))
    detail = assert_missing(compute(given), GUARD_REASON)
    assert_names_only(detail, other_unit)


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq8c_a_missing_factor_in_another_unit_is_reported_as_missing(name):
    given = factors(
        **{name: Factor(value=Missing(reason=A_FACTOR_REASON), unit=OTHER_UNIT)}
    )
    detail = assert_missing(compute(given), "MISSING_INPUT")
    assert_names_only(detail, name)


# --- EQ9: defects of the caller ----------------------------------------------


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize(
    "not_a_factor",
    [NUMBERS["r"], None, (NUMBERS["r"], UNITS.r), Missing(reason=A_FACTOR_REASON)],
    ids=["a bare number", "None", "a tuple", "a bare Missing"],
)
def test_eq9a_an_argument_that_is_not_a_factor_is_a_type_error(name, not_a_factor):
    with pytest.raises(TypeError, match=f"'{name}'"):
        compute(factors(**{name: not_a_factor}))


@pytest.mark.parametrize("name", FACTOR_NAMES)
@pytest.mark.parametrize(
    "value",
    [None, "PLACEHOLDER text", True, False, InputsMissing(reason=A_FACTOR_REASON)],
    ids=["None", "text", "True", "False", "the Missing of the input contracts"],
)
def test_eq9b_a_value_that_is_no_number_and_no_missing_is_a_type_error(name, value):
    given = factors(**{name: Factor(value=value, unit=getattr(UNITS, name))})
    with pytest.raises(TypeError, match=f"'{name}'"):
        compute(given)


@pytest.mark.parametrize("name", FACTOR_NAMES)
def test_eq9c_a_unit_that_is_not_a_string_is_a_type_error(name):
    with pytest.raises(TypeError, match=f"'{name}'"):
        compute(factors(**{name: Factor(value=NUMBERS[name], unit=None)}))
    with pytest.raises(TypeError, match=f"'{name}'"):
        compute(factors(), accepted_units=dataclasses.replace(UNITS, **{name: None}))


def test_eq9d_accepted_units_of_another_type_is_a_type_error():
    as_mapping = dataclasses.asdict(UNITS)
    with pytest.raises(TypeError, match="accepted_units"):
        compute(factors(), accepted_units=as_mapping)


@pytest.mark.parametrize("reason", ["PLACEHOLDER_CODE", "not_computable", "", None])
def test_eq9e_a_guard_reason_outside_the_closed_list_is_a_value_error(reason):
    """Also when no unit is wrong: the defect does not wait for a mismatch."""
    with pytest.raises(ValueError, match="unit_guard_reason"):
        compute(factors(), unit_guard_reason=reason)


# --- EQ10: nothing has a default ---------------------------------------------


def test_eq10a_every_argument_is_keyword_only_and_has_no_default():
    parameters = inspect.signature(annual_soil_loss).parameters
    assert list(parameters) == [*FACTOR_NAMES, "accepted_units", "unit_guard_reason"]
    for parameter in parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize(
    "left_out", [*FACTOR_NAMES, "accepted_units", "unit_guard_reason"]
)
def test_eq10b_leaving_an_argument_out_is_a_type_error(left_out):
    arguments = {
        **factors(),
        "accepted_units": UNITS,
        "unit_guard_reason": GUARD_REASON,
    }
    del arguments[left_out]
    with pytest.raises(TypeError, match=left_out):
        annual_soil_loss(**arguments)


def test_eq10c_no_accepted_unit_and_no_part_of_a_factor_has_a_default():
    assert [field.name for field in dataclasses.fields(AcceptedUnits)] == list(
        FACTOR_NAMES
    )
    for field in (*dataclasses.fields(AcceptedUnits), *dataclasses.fields(Factor)):
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING


# --- EQ11: a pure function without numbers or units of its own -----------------

SOURCE = Path(equation.__file__).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def test_eq11a_the_arguments_are_not_changed_and_the_result_repeats():
    given = with_missing("k")
    before = dict(given)
    units_before = dataclasses.replace(UNITS)
    first = compute(given)
    assert compute(given) == first
    assert given == before
    assert units_before == UNITS

    product = compute(factors())
    assert compute(factors()) == product


def test_eq11b_the_module_holds_no_number():
    numbers = [
        node.value
        for node in ast.walk(TREE)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float, complex))
        and not isinstance(node.value, bool)
    ]
    assert numbers == []


def test_eq11c_the_module_holds_no_unit_string_of_the_conventions_sheet():
    units = [
        value
        for name, value in vars(results_models).items()
        if name.startswith("UNIT_") and isinstance(value, str)
    ]
    assert units, "the results models no longer name their units as UNIT_ constants"
    for unit in units:
        assert unit not in SOURCE


def test_eq11d_the_module_imports_nothing_that_reads_the_outside():
    allowed = {
        "__future__",
        "math",
        "dataclasses",
        "typing",
        "contracts.results.models",
    }
    imported = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            imported.add(node.module)
    assert imported <= allowed
    assert "contracts.results.models" in imported


def test_eq11e_every_unit_string_of_this_test_is_a_placeholder():
    for unit in (*dataclasses.astuple(UNITS), OTHER_UNIT):
        assert WORD in unit
    assert len(set(dataclasses.astuple(UNITS))) == len(FACTOR_NAMES)
