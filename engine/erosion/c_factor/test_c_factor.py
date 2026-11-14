"""Tests of engine/erosion/c_factor/: the PROPOSED cases listed in README.md.

Every constant in this file is a PLACEHOLDER: plainly not a real value of
any method. Repeated digits are used, or zero and one where the arithmetic
is done by hand. No case holds an expected value of the science. The tests
against the worked examples of source S1 of docs/METHODS.md are the skipped
tests at the end.

Run from the repository root: ``python -m pytest engine/erosion/c_factor/``.
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
from engine.erosion.c_factor import (
    DECLARED_LIMIT,
    SET_TO_ONE,
    MonthOfRotation,
    SoilLossRatio,
    canopy_subfactor,
    residue_cover_from_mass,
    residue_mass_after_decay,
    residue_mass_over_time,
    rotation_c,
    soil_loss_ratio,
    surface_cover_subfactor,
)

HERE = Path(__file__).parent
README = HERE / "README.md"
MODULES = sorted(
    path for path in HERE.glob("*.py") if not path.name.startswith("test_")
)

# Rounding of floating-point arithmetic only. Not a tolerance of the
# validation protocol.
FLOAT_NOISE = 1e-12

# --- PLACEHOLDER constants: not real values ---------------------------------

PLACEHOLDER_FALL_HEIGHT_COEFFICIENT = 0.777
PLACEHOLDER_SURFACE_COVER_COEFFICIENT = 4.44
PLACEHOLDER_MASS_COVER_COEFFICIENT = 0.888
PLACEHOLDER_RESIDUE_A = "PLACEHOLDER_residue_type_a"
PLACEHOLDER_RESIDUE_B = "PLACEHOLDER_residue_type_b"
PLACEHOLDER_DECAY = {PLACEHOLDER_RESIDUE_A: 0.111, PLACEHOLDER_RESIDUE_B: 0.222}
PLACEHOLDER_FRACTION_SUM_TOLERANCE = 0.0333

PLACEHOLDER_LENGTH_UNIT = "PLACEHOLDER_length_unit"
PLACEHOLDER_MASS_UNIT = "PLACEHOLDER_mass_per_area_unit"
PLACEHOLDER_TIME_UNIT = "PLACEHOLDER_time_unit"

# PLACEHOLDER inputs of a period. Not a real field or crop.
PLACEHOLDER_CANOPY_COVER = 0.55
PLACEHOLDER_FALL_HEIGHT = 2.22
PLACEHOLDER_RESIDUE_COVER = 0.66
PLACEHOLDER_RESIDUE_MASS = 3.33
PLACEHOLDER_ELAPSED_TIME = 5.55

GRID = [0.0, 0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88, 0.99, 1.0]


# --- calling helpers ---------------------------------------------------------


def canopy(**changes):
    arguments = {
        "canopy_cover": PLACEHOLDER_CANOPY_COVER,
        "fall_height": PLACEHOLDER_FALL_HEIGHT,
        "fall_height_unit": PLACEHOLDER_LENGTH_UNIT,
        "fall_height_coefficient": PLACEHOLDER_FALL_HEIGHT_COEFFICIENT,
        "fall_height_coefficient_per_unit": PLACEHOLDER_LENGTH_UNIT,
    }
    arguments.update(changes)
    return canopy_subfactor(**arguments)


def surface(**changes):
    arguments = {
        "surface_residue_cover": PLACEHOLDER_RESIDUE_COVER,
        "surface_cover_coefficient": PLACEHOLDER_SURFACE_COVER_COEFFICIENT,
    }
    arguments.update(changes)
    return surface_cover_subfactor(**arguments)


def ratio(**changes):
    arguments = {"canopy": canopy(), "surface_cover": surface()}
    arguments.update(changes)
    return soil_loss_ratio(**arguments)


def cover(**changes):
    arguments = {
        "residue_mass": PLACEHOLDER_RESIDUE_MASS,
        "residue_mass_unit": PLACEHOLDER_MASS_UNIT,
        "mass_cover_coefficient": PLACEHOLDER_MASS_COVER_COEFFICIENT,
        "mass_cover_coefficient_per_unit": PLACEHOLDER_MASS_UNIT,
    }
    arguments.update(changes)
    return residue_cover_from_mass(**arguments)


def decay(**changes):
    arguments = {
        "residue_mass": PLACEHOLDER_RESIDUE_MASS,
        "residue_type": PLACEHOLDER_RESIDUE_A,
        "decay_coefficients": dict(PLACEHOLDER_DECAY),
        "decay_coefficient_per_unit": PLACEHOLDER_TIME_UNIT,
        "elapsed_time": PLACEHOLDER_ELAPSED_TIME,
        "elapsed_time_unit": PLACEHOLDER_TIME_UNIT,
    }
    arguments.update(changes)
    return residue_mass_after_decay(**arguments)


def series(**changes):
    arguments = {
        "initial_residue_mass": PLACEHOLDER_RESIDUE_MASS,
        "residue_type": PLACEHOLDER_RESIDUE_A,
        "decay_coefficients": dict(PLACEHOLDER_DECAY),
        "decay_coefficient_per_unit": PLACEHOLDER_TIME_UNIT,
        "step_durations": [1.11, 2.22, 3.33],
        "elapsed_time_unit": PLACEHOLDER_TIME_UNIT,
    }
    arguments.update(changes)
    return residue_mass_over_time(**arguments)


def a_ratio(value):
    """A soil-loss ratio whose value is ``value``, built through the function."""
    return soil_loss_ratio(canopy=value, surface_cover=1.0)


def months_of(pairs):
    return [
        MonthOfRotation(label=f"PLACEHOLDER month {index}", erosivity_fraction=f, soil_loss_ratio=a_ratio(r))
        for index, (f, r) in enumerate(pairs)
    ]  # fmt: skip


def rotation(**changes):
    arguments = {
        "months": months_of([(0.25, 0.5), (0.75, 0.25)]),
        "number_of_years": 1,
        "fraction_sum_tolerance": PLACEHOLDER_FRACTION_SUM_TOLERANCE,
    }
    arguments.update(changes)
    return rotation_c(**arguments)


def a_missing(shape, reason="NOT_DECLARED"):
    return shape(reason=reason, detail="PLACEHOLDER detail")


def assert_missing(result, reason):
    assert isinstance(result, ResultMissing), result
    assert result.reason == reason, result


def assert_close(actual, expected):
    assert isinstance(actual, float), actual
    assert math.isclose(actual, expected, rel_tol=FLOAT_NOISE, abs_tol=FLOAT_NOISE)


# Every numeric argument of every function, with the call that changes it.
NUMERIC_ARGUMENTS = [
    (canopy, "canopy_cover", lambda r: r),
    (canopy, "fall_height", lambda r: r),
    (canopy, "fall_height_coefficient", lambda r: r),
    (surface, "surface_residue_cover", lambda r: r),
    (surface, "surface_cover_coefficient", lambda r: r),
    (ratio, "canopy", lambda r: r.value),
    (ratio, "surface_cover", lambda r: r.value),
    (cover, "residue_mass", lambda r: r),
    (cover, "mass_cover_coefficient", lambda r: r),
    (decay, "residue_mass", lambda r: r),
    (decay, "elapsed_time", lambda r: r),
    (series, "initial_residue_mass", lambda r: r),
    (rotation, "fraction_sum_tolerance", lambda r: r.fractions_add_up),
]
NUMERIC_IDS = [f"{call.__name__}-{name}" for call, name, _ in NUMERIC_ARGUMENTS]


# --- canopy sub-factor -------------------------------------------------------


def test_canopy_subfactor_follows_the_proposed_form():
    for canopy_cover in GRID:
        for height in [0.0, 1.11, 9.99]:
            expected = 1 - canopy_cover * math.exp(
                -PLACEHOLDER_FALL_HEIGHT_COEFFICIENT * height
            )
            assert_close(
                canopy(canopy_cover=canopy_cover, fall_height=height), expected
            )


def test_canopy_subfactor_is_one_without_canopy():
    for height in [0.0, 1.11, 9.99]:
        for coefficient in [0.0, 0.777, 7.77]:
            result = canopy(
                canopy_cover=0.0,
                fall_height=height,
                fall_height_coefficient=coefficient,
            )
            assert result == 1.0


def test_more_canopy_cover_never_raises_the_canopy_subfactor():
    for height in [0.0, 1.11, 9.99]:
        values = [canopy(canopy_cover=c, fall_height=height) for c in GRID]
        assert all(later <= earlier for earlier, later in zip(values, values[1:]))


# --- surface-cover sub-factor ------------------------------------------------


def test_surface_cover_subfactor_follows_the_proposed_form():
    for residue_cover in GRID:
        expected = math.exp(-PLACEHOLDER_SURFACE_COVER_COEFFICIENT * residue_cover)
        assert_close(surface(surface_residue_cover=residue_cover), expected)


def test_surface_cover_subfactor_is_one_without_residue():
    for coefficient in [0.0, 4.44, 44.4]:
        result = surface(
            surface_residue_cover=0.0, surface_cover_coefficient=coefficient
        )
        assert result == 1.0


def test_more_residue_cover_never_raises_the_surface_cover_subfactor():
    values = [surface(surface_residue_cover=c) for c in GRID]
    assert all(later <= earlier for earlier, later in zip(values, values[1:]))


# --- soil-loss ratio ---------------------------------------------------------


def test_soil_loss_ratio_is_the_product_of_its_subfactors():
    for canopy_value, surface_value in [(1.0, 1.0), (0.5, 0.25), (0.33, 0.66)]:
        result = soil_loss_ratio(canopy=canopy_value, surface_cover=surface_value)
        assert isinstance(result, SoilLossRatio)
        assert_close(result.value, canopy_value * surface_value)
        assert result.canopy == canopy_value
        assert result.surface_cover == surface_value


def test_soil_loss_ratio_records_the_subfactors_set_to_one():
    expected = (
        "surface_roughness",
        "soil_biomass",
        "soil_consolidation",
        "prior_land_use",
    )
    assert SET_TO_ONE == expected
    assert "D45" in DECLARED_LIMIT
    computed = ratio()
    missing = ratio(canopy=a_missing(ResultMissing))
    for result in (computed, missing):
        assert result.set_to_one == expected
        assert result.limit == DECLARED_LIMIT
    assert isinstance(missing.value, ResultMissing)


def test_more_canopy_or_residue_never_raises_the_soil_loss_ratio():
    def through(canopy_cover, residue_cover):
        return soil_loss_ratio(
            canopy=canopy(canopy_cover=canopy_cover),
            surface_cover=surface(surface_residue_cover=residue_cover),
        ).value

    for fixed in GRID:
        by_canopy = [through(c, fixed) for c in GRID]
        by_residue = [through(fixed, c) for c in GRID]
        for values in (by_canopy, by_residue):
            assert all(later <= earlier for earlier, later in zip(values, values[1:]))


# --- mass-cover relation -----------------------------------------------------


def test_residue_cover_follows_the_proposed_form():
    for mass in [0.0, 0.11, 1.11, 11.1]:
        expected = 1 - math.exp(-PLACEHOLDER_MASS_COVER_COEFFICIENT * mass)
        assert_close(cover(residue_mass=mass), expected)


def test_residue_cover_is_zero_without_residue_and_grows_with_mass():
    assert cover(residue_mass=0.0) == 0.0
    values = [cover(residue_mass=m) for m in [0.0, 0.11, 1.11, 11.1, 111.0]]
    assert all(later >= earlier for earlier, later in zip(values, values[1:]))
    assert all(0.0 <= value <= 1.0 for value in values)


# --- decay -------------------------------------------------------------------


def test_decay_step_follows_the_proposed_form():
    for mass in [0.0, 1.11, 33.3]:
        for elapsed in [0.0, 1.11, 55.5]:
            expected = mass * math.exp(
                -PLACEHOLDER_DECAY[PLACEHOLDER_RESIDUE_A] * elapsed
            )
            assert_close(decay(residue_mass=mass, elapsed_time=elapsed), expected)


def test_decay_never_adds_mass_and_never_makes_it_negative():
    for mass in [0.0, 0.11, 3.33, 333.0]:
        for elapsed in [0.0, 0.11, 5.55, 555.0, 5.55e5]:
            for coefficient in [0.0, 0.111, 11.1]:
                result = decay(
                    residue_mass=mass,
                    elapsed_time=elapsed,
                    decay_coefficients={PLACEHOLDER_RESIDUE_A: coefficient},
                )
                assert 0.0 <= result <= mass


def test_decay_chooses_the_coefficient_of_the_residue_type():
    a = decay(residue_type=PLACEHOLDER_RESIDUE_A)
    b = decay(residue_type=PLACEHOLDER_RESIDUE_B)
    assert a != b
    changed_other = dict(PLACEHOLDER_DECAY, **{PLACEHOLDER_RESIDUE_B: 9.99})
    assert (
        decay(residue_type=PLACEHOLDER_RESIDUE_A, decay_coefficients=changed_other) == a
    )


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
def test_residue_type_without_decay_coefficient_gives_missing_that_names_it(shape):
    absent = decay(residue_type="PLACEHOLDER_residue_type_without_coefficient")
    assert_missing(absent, "MISSING_INPUT")
    assert "PLACEHOLDER_residue_type_without_coefficient" in absent.detail

    held_missing = dict(PLACEHOLDER_DECAY, **{PLACEHOLDER_RESIDUE_A: a_missing(shape)})
    result = decay(decay_coefficients=held_missing)
    assert_missing(result, "MISSING_INPUT")
    assert PLACEHOLDER_RESIDUE_A in result.detail
    assert "NOT_DECLARED" in result.detail

    over_time = series(residue_type="PLACEHOLDER_residue_type_without_coefficient")
    assert_missing(over_time, "MISSING_INPUT")
    assert "PLACEHOLDER_residue_type_without_coefficient" in over_time.detail


def test_negative_decay_coefficient_or_elapsed_time_is_refused():
    negative_coefficient = decay(decay_coefficients={PLACEHOLDER_RESIDUE_A: -0.111})
    assert_missing(negative_coefficient, "NOT_COMPUTABLE")
    assert PLACEHOLDER_RESIDUE_A in negative_coefficient.detail
    negative_time = decay(elapsed_time=-1.11)
    assert_missing(negative_time, "NOT_COMPUTABLE")
    assert "elapsed_time" in negative_time.detail


def test_mass_over_time_equals_steps_applied_one_after_another():
    durations = [1.11, 2.22, 3.33]
    result = series(step_durations=durations)
    assert isinstance(result, tuple)
    assert len(result) == len(durations)
    mass = PLACEHOLDER_RESIDUE_MASS
    for value, duration in zip(result, durations):
        mass = decay(residue_mass=mass, elapsed_time=duration)
        assert_close(value, mass)
    assert all(later <= earlier for earlier, later in zip(result, result[1:]))


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
def test_mass_over_time_missing_step_makes_the_series_missing_and_names_the_step(shape):
    result = series(step_durations=[1.11, a_missing(shape), 3.33])
    assert_missing(result, "MISSING_INPUT")
    assert "step_durations[1]" in result.detail
    negative = series(step_durations=[1.11, 2.22, -3.33])
    assert_missing(negative, "NOT_COMPUTABLE")
    assert "step_durations[2]" in negative.detail


def test_mass_over_time_without_steps_checks_the_initial_mass():
    assert series(step_durations=[]) == ()
    assert_missing(
        series(step_durations=[], initial_residue_mass=a_missing(ResultMissing)),
        "MISSING_INPUT",
    )
    assert_missing(
        series(step_durations=[], initial_residue_mass=-1.11), "NOT_COMPUTABLE"
    )


# --- rotation C --------------------------------------------------------------


def test_rotation_c_weights_each_month_by_its_erosivity_fraction():
    result = rotation(months=months_of([(0.25, 0.5), (0.75, 0.25)]))
    assert_close(result.value, 0.25 * 0.5 + 0.75 * 0.25)
    moved = rotation(months=months_of([(0.75, 0.5), (0.25, 0.25)]))
    assert_close(moved.value, 0.75 * 0.5 + 0.25 * 0.25)
    assert moved.value > result.value
    no_erosivity = rotation(months=months_of([(0.0, 0.5), (1.0, 0.25)]))
    assert_close(no_erosivity.value, 0.25)


def test_rotation_c_divides_by_the_number_of_years():
    pairs = [(0.25, 0.5), (0.75, 0.25), (0.5, 1.0), (0.5, 0.0)]
    result = rotation(months=months_of(pairs), number_of_years=2)
    assert_close(result.value, (0.125 + 0.1875 + 0.5 + 0.0) / 2)
    assert result.fraction_sum == 2.0
    assert result.expected_fraction_sum == 2.0
    assert result.fractions_add_up is True


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize("part", ["erosivity_fraction", "soil_loss_ratio", "number_of_years"])  # fmt: skip
def test_rotation_c_missing_fraction_or_ratio_gives_missing_never_zero(part, shape):
    months = months_of([(0.25, 0.5), (0.75, 0.25)])
    number_of_years = 1
    if part == "erosivity_fraction":
        months[1] = MonthOfRotation(
            label=months[1].label,
            erosivity_fraction=a_missing(shape),
            soil_loss_ratio=months[1].soil_loss_ratio,
        )
    elif part == "soil_loss_ratio":
        months[1] = MonthOfRotation(
            label=months[1].label,
            erosivity_fraction=months[1].erosivity_fraction,
            soil_loss_ratio=soil_loss_ratio(canopy=a_missing(shape), surface_cover=1.0),
        )
    else:
        number_of_years = a_missing(shape)
    result = rotation(months=months, number_of_years=number_of_years)
    assert_missing(result.value, "MISSING_INPUT")
    assert part in result.value.detail
    if part != "number_of_years":
        assert months[1].label in result.value.detail
    assert result.set_to_one == SET_TO_ONE


def test_rotation_c_reports_fractions_that_do_not_add_up_without_normalising():
    pairs = [(0.25, 0.5), (0.5, 0.25)]  # the fractions add up to 0.75, not 1
    result = rotation(months=months_of(pairs), number_of_years=1)
    assert_close(result.value, 0.25 * 0.5 + 0.5 * 0.25)  # not divided by 0.75
    assert_close(result.fraction_sum, 0.75)
    assert result.expected_fraction_sum == 1.0
    assert result.fractions_add_up is False
    two_years = rotation(months=months_of([(0.5, 0.5), (0.5, 0.5)]), number_of_years=2)
    assert two_years.fractions_add_up is False
    assert_close(two_years.value, 0.25)


def test_rotation_c_fractions_that_add_up_within_the_tolerance_are_reported_as_such():
    inside = PLACEHOLDER_FRACTION_SUM_TOLERANCE / 3
    outside = PLACEHOLDER_FRACTION_SUM_TOLERANCE * 3
    assert rotation(months=months_of([(0.5, 0.5), (0.5 + inside, 0.5)])).fractions_add_up is True  # fmt: skip
    assert rotation(months=months_of([(0.5, 0.5), (0.5 - inside, 0.5)])).fractions_add_up is True  # fmt: skip
    assert rotation(months=months_of([(0.5, 0.5), (0.5 + outside, 0.5)])).fractions_add_up is False  # fmt: skip
    exact = rotation(
        months=months_of([(0.5, 0.5), (0.5, 0.5)]), fraction_sum_tolerance=0.0
    )
    assert exact.fractions_add_up is True


def test_rotation_c_records_the_subfactors_set_to_one():
    result = rotation()
    assert result.set_to_one == SET_TO_ONE
    assert result.limit == DECLARED_LIMIT


def test_rotation_c_without_months_or_with_no_years_is_not_computed():
    empty = rotation(months=[])
    assert_missing(empty.value, "NOT_COMPUTABLE")
    assert_missing(empty.fraction_sum, "NOT_COMPUTABLE")
    for years in [0, -1]:
        result = rotation(number_of_years=years)
        assert_missing(result.value, "NOT_COMPUTABLE")
        assert_missing(result.expected_fraction_sum, "NOT_COMPUTABLE")
        assert isinstance(result.fractions_add_up, ResultMissing)


def test_rotation_c_missing_tolerance_leaves_c_and_withholds_only_the_check():
    result = rotation(fraction_sum_tolerance=a_missing(ResultMissing))
    assert isinstance(result.value, float)
    assert_missing(result.fractions_add_up, "MISSING_INPUT")
    negative = rotation(fraction_sum_tolerance=-0.0333)
    assert isinstance(negative.value, float)
    assert_missing(negative.fractions_add_up, "NOT_COMPUTABLE")


# --- arguments outside what a quantity can be --------------------------------


@pytest.mark.parametrize("value", [-0.11, 1.11, -1e-9, 1 + 1e-9])
def test_cover_fraction_outside_zero_to_one_is_not_computed(value):
    canopy_result = canopy(canopy_cover=value)
    assert_missing(canopy_result, "NOT_COMPUTABLE")
    assert "canopy_cover" in canopy_result.detail
    surface_result = surface(surface_residue_cover=value)
    assert_missing(surface_result, "NOT_COMPUTABLE")
    assert "surface_residue_cover" in surface_result.detail
    for bound in [0.0, 1.0]:
        assert isinstance(canopy(canopy_cover=bound), float)
        assert isinstance(surface(surface_residue_cover=bound), float)


def test_negative_mass_or_height_is_not_computed():
    cases = [
        (canopy(fall_height=-1.11), "fall_height"),
        (cover(residue_mass=-1.11), "residue_mass"),
        (decay(residue_mass=-1.11), "residue_mass"),
        (series(initial_residue_mass=-1.11), "initial_residue_mass"),
    ]
    for result, name in cases:
        assert_missing(result, "NOT_COMPUTABLE")
        assert name in result.detail


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf, 10**400],
    ids=["nan", "inf", "-inf", "huge-int"],
)
@pytest.mark.parametrize(("call", "name", "read"), NUMERIC_ARGUMENTS, ids=NUMERIC_IDS)
def test_argument_that_is_not_finite_is_not_computed(call, name, read, value):
    result = read(call(**{name: value}))
    assert_missing(result, "NOT_COMPUTABLE")
    assert name in result.detail


def test_months_and_years_that_are_not_finite_are_not_computed():
    for value in [math.nan, math.inf]:
        fraction = rotation(months=months_of([(value, 0.5), (0.5, 0.5)]))
        assert_missing(fraction.value, "NOT_COMPUTABLE")
        assert_missing(fraction.fraction_sum, "NOT_COMPUTABLE")
        # Through soil_loss_ratio, a ratio that is not finite arrives missing.
        through = rotation(months=months_of([(0.5, value), (0.5, 0.5)]))
        assert_missing(through.value, "MISSING_INPUT")
        assert "PLACEHOLDER month 0" in through.value.detail
        assert through.fraction_sum == 1.0
        # A ratio built by hand with a value that is not finite.
        by_hand = SoilLossRatio(
            value=value,
            canopy=value,
            surface_cover=1.0,
            set_to_one=SET_TO_ONE,
            limit=DECLARED_LIMIT,
        )
        months = [
            MonthOfRotation(label="PLACEHOLDER month 0", erosivity_fraction=0.5, soil_loss_ratio=by_hand),
            MonthOfRotation(label="PLACEHOLDER month 1", erosivity_fraction=0.5, soil_loss_ratio=a_ratio(0.5)),
        ]  # fmt: skip
        assert_missing(rotation(months=months).value, "NOT_COMPUTABLE")
    huge = rotation(number_of_years=10**400)
    assert_missing(huge.value, "NOT_COMPUTABLE")
    decay_coefficient = decay(decay_coefficients={PLACEHOLDER_RESIDUE_A: math.nan})
    assert_missing(decay_coefficient, "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "shape", [InputMissing, ResultMissing], ids=["inputs", "results"]
)
@pytest.mark.parametrize(("call", "name", "read"), NUMERIC_ARGUMENTS, ids=NUMERIC_IDS)
def test_missing_argument_gives_missing_input_that_names_it(call, name, read, shape):
    result = read(call(**{name: a_missing(shape)}))
    assert_missing(result, "MISSING_INPUT")
    assert name in result.detail
    assert "NOT_DECLARED" in result.detail


def test_units_that_differ_are_not_computed():
    cases = [
        canopy(fall_height_unit="PLACEHOLDER_other_length_unit"),
        cover(residue_mass_unit="PLACEHOLDER_other_mass_unit"),
        decay(elapsed_time_unit="PLACEHOLDER_other_time_unit"),
        series(elapsed_time_unit="PLACEHOLDER_other_time_unit"),
    ]
    for result in cases:
        assert_missing(result, "NOT_COMPUTABLE")
        assert "PLACEHOLDER_other" in result.detail


def test_form_without_a_finite_result_is_not_computed():
    assert_missing(
        canopy(fall_height_coefficient=-1e300, fall_height=1e10), "NOT_COMPUTABLE"
    )
    assert_missing(surface(surface_cover_coefficient=-1e300, surface_residue_cover=1.0), "NOT_COMPUTABLE")  # fmt: skip
    assert_missing(
        cover(mass_cover_coefficient=-1e300, residue_mass=1e10), "NOT_COMPUTABLE"
    )
    assert_missing(
        soil_loss_ratio(canopy=1e300, surface_cover=1e300).value, "NOT_COMPUTABLE"
    )
    big = rotation(months=months_of([(1e300, 1e300), (0.5, 0.5)]))
    assert_missing(big.value, "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "bad", [None, "0.5", True, [0.5]], ids=["none", "text", "bool", "list"]
)
@pytest.mark.parametrize(("call", "name", "read"), NUMERIC_ARGUMENTS, ids=NUMERIC_IDS)
def test_argument_of_another_type_raises_type_error(call, name, read, bad):
    with pytest.raises(TypeError, match=re.escape(name)):
        call(**{name: bad})


def test_structured_argument_of_another_type_raises_type_error():
    with pytest.raises(TypeError, match="decay_coefficients"):
        decay(decay_coefficients=[0.111])
    with pytest.raises(TypeError, match="residue_type"):
        decay(residue_type=None)
    with pytest.raises(TypeError, match="step_durations"):
        series(step_durations=None)
    with pytest.raises(TypeError, match="months"):
        rotation(months=None)
    with pytest.raises(TypeError, match="soil_loss_ratio"):
        rotation(months=[MonthOfRotation(label="m", erosivity_fraction=1.0, soil_loss_ratio=0.5)])  # fmt: skip
    with pytest.raises(TypeError, match="number_of_years"):
        rotation(number_of_years=1.0)
    with pytest.raises(TypeError, match="fall_height_unit"):
        canopy(fall_height_unit=None)


# --- no constant of the method in the modules --------------------------------

PUBLIC_FUNCTIONS = [
    canopy_subfactor,
    surface_cover_subfactor,
    soil_loss_ratio,
    residue_cover_from_mass,
    residue_mass_after_decay,
    residue_mass_over_time,
    rotation_c,
]


def test_every_argument_is_passed_by_name_and_none_has_a_default():
    for function in PUBLIC_FUNCTIONS:
        for parameter in inspect.signature(function).parameters.values():
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
                function,
                parameter,
            )
            assert parameter.default is inspect.Parameter.empty, (function, parameter)


def test_the_modules_hold_no_number_but_zero_and_one():
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        numbers = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float, complex))
            and not isinstance(node.value, bool)
        }
        assert numbers <= {0, 1}, (path.name, numbers)


# --- README.md ---------------------------------------------------------------

CONSTANTS = {
    "fall_height_coefficient",
    "surface_cover_coefficient",
    "mass_cover_coefficient",
    "decay_coefficients",
}


def section(title):
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def table_rows(text):
    lines = [line for line in text.splitlines() if line.startswith("|")]
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines
    ]


def test_readme_lists_every_constant_with_an_empty_value():
    rows = table_rows(section("Constants a person has to transcribe"))
    header, body = rows[0], rows[2:]
    assert header[0] == "Constant"
    assert header[-1] == "Value"
    assert all(len(row) == len(header) for row in body)
    assert {row[0].strip("`") for row in body} == CONSTANTS
    identifiers = [row[1].strip("`") for row in body]
    assert len(set(identifiers)) == len(identifiers)
    for row in body:
        assert row[-1] == "", f"{row[0]}: a session writes no value"
        assert all(cell for cell in row[:-1]), f"{row[0]}: an empty cell"
    for identifier in identifiers:
        # params/README.md: starts with a letter; letters, digits and "_" only.
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", identifier), identifier


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written


# --- worked examples of source S1: waiting for a person ----------------------

WAITS_FOR = (
    "It waits for a person to transcribe from source S1 of docs/METHODS.md, and "
    "a second person to check (decision D34 of issue #77): {what}; the inputs of "
    "the worked example, its published result and the tolerance of the "
    "comparison, with their locators in S1. All of them are OPEN today."
)


@pytest.mark.skip(reason=WAITS_FOR.format(what="fall_height_coefficient as a record of the parameter catalogue"))  # fmt: skip
def test_s1_worked_example_of_the_canopy_subfactor():
    """The canopy sub-factor against a worked example of S1. No value written by a session."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="surface_cover_coefficient as a record of the parameter catalogue"))  # fmt: skip
def test_s1_worked_example_of_the_surface_cover_subfactor():
    """The surface-cover sub-factor against a worked example of S1."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="mass_cover_coefficient, and whether it depends on the residue type"))  # fmt: skip
def test_s1_worked_example_of_the_mass_cover_relation():
    """The mass-cover relation against a worked example of S1."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="the decay coefficient of each residue type of the example, and its time unit"))  # fmt: skip
def test_s1_worked_example_of_residue_decay():
    """Residue decay against a worked example of S1."""
    pytest.fail("not written: see the skip reason")


@pytest.mark.skip(reason=WAITS_FOR.format(what="the monthly erosivity fractions and soil-loss ratios of the example"))  # fmt: skip
def test_s1_worked_example_of_rotation_c():
    """``C`` of a rotation against a worked example of S1."""
    pytest.fail("not written: see the skip reason")
