"""Targeted mutant-killing tests for ``engine/erosion/c_factor/``.

Every number in this file is a PLACEHOLDER chosen for hand arithmetic or
boundary checks. None is a value of any method or source.
"""

from __future__ import annotations

import math

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion.c_factor import (
    DECLARED_LIMIT,
    SET_TO_ONE,
    MonthOfRotation,
    SoilLossRatio,
    canopy_subfactor,
    effective_canopy_cover,
    residue_cover_from_mass,
    residue_mass_after_decay,
    residue_mass_over_time,
    rotation_c,
    soil_loss_ratio,
    surface_cover_subfactor_percent,
)

PLACEHOLDER_LENGTH_UNIT = "PLACEHOLDER_length_unit"
PLACEHOLDER_MASS_UNIT = "PLACEHOLDER_mass_unit"
PLACEHOLDER_TIME_UNIT = "PLACEHOLDER_time_unit"
PLACEHOLDER_RESIDUE = "PLACEHOLDER_residue"
PLACEHOLDER_DECAY = {PLACEHOLDER_RESIDUE: 0.1}


def _missing(shape=ResultMissing, reason="NOT_DECLARED"):
    return shape(reason=reason, detail="PLACEHOLDER detail")


def _ratio(value: float) -> SoilLossRatio:
    return soil_loss_ratio(canopy=value, surface_cover=1.0)


def _months(pairs: list[tuple[float, float]]) -> list[MonthOfRotation]:
    return [
        MonthOfRotation(
            label=f"PLACEHOLDER m{i}",
            erosivity_fraction=f,
            soil_loss_ratio=_ratio(r),
        )
        for i, (f, r) in enumerate(pairs)
    ]


# --- _numbers.py and subfactors.py ------------------------------------------


def test_subfactors_missing_precedes_nonfinite_and_out_of_range():
    """C3.3: MISSING_INPUT takes precedence over NOT_COMPUTABLE, range, and unit checks."""
    cc_missing = canopy_subfactor(
        canopy_cover=_missing(InputMissing),
        fall_height=math.nan,
        fall_height_unit="PLACEHOLDER_other",
        fall_height_coefficient=-1.0,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    assert isinstance(cc_missing, ResultMissing)
    assert cc_missing.reason == "MISSING_INPUT"
    assert "canopy_cover" in cc_missing.detail

    slr_missing = soil_loss_ratio(
        canopy=math.nan, surface_cover=_missing(ResultMissing)
    )
    assert isinstance(slr_missing.value, ResultMissing)
    assert slr_missing.value.reason == "MISSING_INPUT"
    assert "surface_cover" in slr_missing.value.detail

    eff_missing = effective_canopy_cover(
        canopy_cover=-0.5, ground_cover=_missing(InputMissing)
    )
    assert isinstance(eff_missing, ResultMissing)
    assert eff_missing.reason == "MISSING_INPUT"
    assert "ground_cover" in eff_missing.detail


def test_subfactors_multiple_failures_name_every_failing_argument():
    """Multiple missing, non-finite, or out-of-range arguments are all named in detail."""
    both_missing = canopy_subfactor(
        canopy_cover=_missing(InputMissing),
        fall_height=_missing(ResultMissing),
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
        fall_height_coefficient=0.5,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    assert isinstance(both_missing, ResultMissing)
    assert both_missing.reason == "MISSING_INPUT"
    assert "canopy_cover" in both_missing.detail
    assert "fall_height" in both_missing.detail

    both_nonfinite = surface_cover_subfactor_percent(
        surface_residue_cover=math.nan,
        surface_cover_coefficient_per_percent=math.inf,
    )
    assert isinstance(both_nonfinite, ResultMissing)
    assert both_nonfinite.reason == "NOT_COMPUTABLE"
    assert "surface_residue_cover" in both_nonfinite.detail
    assert "surface_cover_coefficient_per_percent" in both_nonfinite.detail

    both_outside = effective_canopy_cover(canopy_cover=-0.1, ground_cover=1.1)
    assert isinstance(both_outside, ResultMissing)
    assert both_outside.reason == "NOT_COMPUTABLE"
    assert "canopy_cover" in both_outside.detail
    assert "ground_cover" in both_outside.detail

    both_negative = canopy_subfactor(
        canopy_cover=0.5,
        fall_height=-1.0,
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
        fall_height_coefficient=-1.0,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    assert isinstance(both_negative, ResultMissing)
    assert both_negative.reason == "NOT_COMPUTABLE"
    assert "fall_height" in both_negative.detail
    assert "fall_height_coefficient" in both_negative.detail

    both_slr_missing = soil_loss_ratio(canopy=_missing(), surface_cover=_missing())
    assert isinstance(both_slr_missing.value, ResultMissing)
    assert (
        "canopy" in both_slr_missing.value.detail
        and "surface_cover" in both_slr_missing.value.detail
    )


@pytest.mark.parametrize("bad", [None, "0.5", True, [0.5]])
def test_effective_canopy_and_surface_percent_type_guards(bad):
    """check_types guards effective_canopy_cover and surface_cover_subfactor_percent against bad types."""
    with pytest.raises(TypeError, match="canopy_cover"):
        effective_canopy_cover(canopy_cover=bad, ground_cover=0.5)
    with pytest.raises(TypeError, match="ground_cover"):
        effective_canopy_cover(canopy_cover=0.5, ground_cover=bad)
    with pytest.raises(TypeError, match="surface_residue_cover"):
        surface_cover_subfactor_percent(
            surface_residue_cover=bad, surface_cover_coefficient_per_percent=0.1
        )
    with pytest.raises(TypeError, match="surface_cover_coefficient_per_percent"):
        surface_cover_subfactor_percent(
            surface_residue_cover=0.5, surface_cover_coefficient_per_percent=bad
        )


def test_effective_canopy_and_surface_percent_boundaries_missing_and_nonfinite():
    """Exact 0/1 bounds, hair-outside bounds, zero coeff, Missing, and non-finite inputs."""
    assert effective_canopy_cover(canopy_cover=1.0, ground_cover=0.0) == 1.0
    assert effective_canopy_cover(canopy_cover=0.0, ground_cover=0.0) == 0.0
    for c, g in ((-1e-9, 0.5), (0.5, -1e-9), (1 + 1e-9, 0.5), (0.5, 1 + 1e-9)):
        res = effective_canopy_cover(canopy_cover=c, ground_cover=g)
        assert isinstance(res, ResultMissing) and res.reason == "NOT_COMPUTABLE"

    for bad_num in (math.nan, math.inf, -math.inf, 10**400):
        res_eff = effective_canopy_cover(canopy_cover=bad_num, ground_cover=0.5)
        assert isinstance(res_eff, ResultMissing) and res_eff.reason == "NOT_COMPUTABLE"
        res_pct = surface_cover_subfactor_percent(
            surface_residue_cover=0.5, surface_cover_coefficient_per_percent=bad_num
        )
        assert isinstance(res_pct, ResultMissing) and res_pct.reason == "NOT_COMPUTABLE"

    for shape in (InputMissing, ResultMissing):
        res_m = surface_cover_subfactor_percent(
            surface_residue_cover=_missing(shape),
            surface_cover_coefficient_per_percent=0.1,
        )
        assert isinstance(res_m, ResultMissing) and res_m.reason == "MISSING_INPUT"
        assert "surface_residue_cover" in res_m.detail

    # Zero coefficient is valid (>= 0); -1e-9 is refused; cover outside [0, 1] is refused.
    assert (
        surface_cover_subfactor_percent(
            surface_residue_cover=0.5, surface_cover_coefficient_per_percent=0.0
        )
        == 1.0
    )
    for bad_cov in (-1e-9, 1 + 1e-9):
        res = surface_cover_subfactor_percent(
            surface_residue_cover=bad_cov, surface_cover_coefficient_per_percent=0.1
        )
        assert isinstance(res, ResultMissing) and res.reason == "NOT_COMPUTABLE"
    neg_b = surface_cover_subfactor_percent(
        surface_residue_cover=0.5, surface_cover_coefficient_per_percent=-1e-9
    )
    assert isinstance(neg_b, ResultMissing) and neg_b.reason == "NOT_COMPUTABLE"


def test_canopy_unit_and_negative_precedence_and_text_guard():
    """Negative fall_height precedes unit mismatch; unit text is compared strictly without stripping."""
    neg_before_unit = canopy_subfactor(
        canopy_cover=0.5,
        fall_height=-1e-9,
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
        fall_height_coefficient=0.5,
        fall_height_coefficient_per_unit="PLACEHOLDER_other",
    )
    assert isinstance(neg_before_unit, ResultMissing)
    assert neg_before_unit.reason == "NOT_COMPUTABLE"
    assert "fall_height" in neg_before_unit.detail

    ws_unit = canopy_subfactor(
        canopy_cover=0.5,
        fall_height=1.0,
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT + " ",
        fall_height_coefficient=0.5,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    assert isinstance(ws_unit, ResultMissing) and ws_unit.reason == "NOT_COMPUTABLE"

    with pytest.raises(TypeError, match="fall_height_coefficient_per_unit"):
        canopy_subfactor(
            canopy_cover=0.5,
            fall_height=1.0,
            fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
            fall_height_coefficient=0.5,
            fall_height_coefficient_per_unit=None,
        )


# --- residue.py -------------------------------------------------------------


def test_residue_text_mapping_and_str_bytes_step_durations_guards():
    """Non-str units/keys, non-numeric decay values, and str/bytes step_durations raise TypeError."""
    with pytest.raises(TypeError, match="residue_mass_unit"):
        residue_cover_from_mass(
            residue_mass=1.0,
            residue_mass_unit=None,
            mass_cover_coefficient=0.5,
            mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
        )
    with pytest.raises(TypeError, match="mass_cover_coefficient_per_unit"):
        residue_cover_from_mass(
            residue_mass=1.0,
            residue_mass_unit=PLACEHOLDER_MASS_UNIT,
            mass_cover_coefficient=0.5,
            mass_cover_coefficient_per_unit=123,
        )

    with pytest.raises(TypeError, match="decay_coefficients"):
        residue_mass_after_decay(
            residue_mass=1.0,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients={1: 0.1},
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=1.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
    with pytest.raises(TypeError, match=PLACEHOLDER_RESIDUE):
        residue_mass_after_decay(
            residue_mass=1.0,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients={PLACEHOLDER_RESIDUE: True},
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=1.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
    with pytest.raises(TypeError, match="elapsed_time_unit"):
        residue_mass_after_decay(
            residue_mass=1.0,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients=PLACEHOLDER_DECAY,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=1.0,
            elapsed_time_unit=None,
        )
    with pytest.raises(TypeError, match="decay_coefficient_per_unit"):
        residue_mass_after_decay(
            residue_mass=1.0,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients=PLACEHOLDER_DECAY,
            decay_coefficient_per_unit=None,
            elapsed_time=1.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )

    # Empty str and bytes are Sequences in Python and must be rejected as step_durations.
    for bad_seq in ("", b"", "1"):
        with pytest.raises(TypeError, match="step_durations"):
            residue_mass_over_time(
                initial_residue_mass=1.0,
                residue_type=PLACEHOLDER_RESIDUE,
                decay_coefficients=PLACEHOLDER_DECAY,
                decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
                step_durations=bad_seq,
                elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
            )

    for bad_item in (True, None):
        with pytest.raises(TypeError, match="step_durations\\[1\\]"):
            residue_mass_over_time(
                initial_residue_mass=1.0,
                residue_type=PLACEHOLDER_RESIDUE,
                decay_coefficients=PLACEHOLDER_DECAY,
                decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
                step_durations=[1.0, bad_item],
                elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
            )


def test_residue_boundaries_empty_steps_zero_duration_and_step_error_names():
    """Empty steps at 0.0/-1e-9/nan, zero-duration steps, and step index naming."""
    neg_mass = residue_cover_from_mass(
        residue_mass=-1e-9,
        residue_mass_unit=PLACEHOLDER_MASS_UNIT,
        mass_cover_coefficient=0.5,
        mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
    )
    assert isinstance(neg_mass, ResultMissing) and neg_mass.reason == "NOT_COMPUTABLE"

    both_neg = residue_cover_from_mass(
        residue_mass=-1.0,
        residue_mass_unit=PLACEHOLDER_MASS_UNIT,
        mass_cover_coefficient=-1.0,
        mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
    )
    assert isinstance(both_neg, ResultMissing) and both_neg.reason == "NOT_COMPUTABLE"
    assert (
        "residue_mass" in both_neg.detail
        and "mass_cover_coefficient" in both_neg.detail
    )

    assert (
        residue_mass_over_time(
            initial_residue_mass=0.0,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients=PLACEHOLDER_DECAY,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            step_durations=[],
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        == ()
    )

    for bad_init in (-1e-9, math.nan):
        res = residue_mass_over_time(
            initial_residue_mass=bad_init,
            residue_type=PLACEHOLDER_RESIDUE,
            decay_coefficients=PLACEHOLDER_DECAY,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            step_durations=[],
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        assert isinstance(res, ResultMissing) and res.reason == "NOT_COMPUTABLE"

    step_zero = residue_mass_over_time(
        initial_residue_mass=2.0,
        residue_type=PLACEHOLDER_RESIDUE,
        decay_coefficients=PLACEHOLDER_DECAY,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        step_durations=[0.0, 1.0],
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(step_zero, tuple)
    assert step_zero[0] == 2.0
    assert math.isclose(step_zero[1], 2.0 * math.exp(-0.1), rel_tol=1e-12)

    step1_neg = residue_mass_over_time(
        initial_residue_mass=2.0,
        residue_type=PLACEHOLDER_RESIDUE,
        decay_coefficients=PLACEHOLDER_DECAY,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        step_durations=[1.0, -1e-9],
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(step1_neg, ResultMissing) and step1_neg.reason == "NOT_COMPUTABLE"
    assert "step 1" in step1_neg.detail and "step_durations[1]" in step1_neg.detail

    step0_missing_coeff = residue_mass_over_time(
        initial_residue_mass=2.0,
        residue_type=PLACEHOLDER_RESIDUE,
        decay_coefficients={PLACEHOLDER_RESIDUE: _missing(InputMissing)},
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        step_durations=[1.0],
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(step0_missing_coeff, ResultMissing)
    assert step0_missing_coeff.reason == "MISSING_INPUT"
    assert "step 0" in step0_missing_coeff.detail


# --- rotation.py ------------------------------------------------------------


def test_rotation_c_guards_for_str_bytes_bool_years_and_month_fields():
    """str/bytes months, bool number_of_years, and malformed MonthOfRotation fields raise TypeError."""
    for bad_months in ("", b""):
        with pytest.raises(TypeError, match="months"):
            rotation_c(
                months=bad_months,
                number_of_years=1,
                fraction_sum_tolerance=0.0,
            )

    with pytest.raises(TypeError, match=r"months\[0\]"):
        rotation_c(months=[object()], number_of_years=1, fraction_sum_tolerance=0.0)

    bad_label = MonthOfRotation(
        label=123, erosivity_fraction=1.0, soil_loss_ratio=_ratio(0.5)
    )
    with pytest.raises(TypeError, match=r"months\[0\]\.label"):
        rotation_c(months=[bad_label], number_of_years=1, fraction_sum_tolerance=0.0)

    bad_frac = MonthOfRotation(
        label="m0", erosivity_fraction=True, soil_loss_ratio=_ratio(0.5)
    )
    with pytest.raises(TypeError, match=r"months\[0\]\.erosivity_fraction"):
        rotation_c(months=[bad_frac], number_of_years=1, fraction_sum_tolerance=0.0)

    bad_slr_val = SoilLossRatio(
        value=True,
        canopy=1.0,
        surface_cover=1.0,
        set_to_one=SET_TO_ONE,
        limit=DECLARED_LIMIT,
    )
    bad_slr_month = MonthOfRotation(
        label="m0", erosivity_fraction=1.0, soil_loss_ratio=bad_slr_val
    )
    with pytest.raises(TypeError, match=r"months\[0\]\.soil_loss_ratio\.value"):
        rotation_c(
            months=[bad_slr_month], number_of_years=1, fraction_sum_tolerance=0.0
        )

    for bad_years in (True, False):
        with pytest.raises(TypeError, match="number_of_years"):
            rotation_c(
                months=_months([(1.0, 0.5)]),
                number_of_years=bad_years,
                fraction_sum_tolerance=0.0,
            )


def test_rotation_c_tolerance_nonzero_exact_boundary_and_hair_negative():
    """Exact non-zero tolerance boundary passes (<=); nextafter below fails; -1e-9 tolerance is refused."""
    # Exact binary floats: 0.5 + 0.75 = 1.25; expected = 1.0; difference = 0.25.
    months = _months([(0.5, 0.5), (0.75, 0.5)])
    at_boundary = rotation_c(
        months=months, number_of_years=1, fraction_sum_tolerance=0.25
    )
    assert at_boundary.fractions_add_up is True

    just_below = rotation_c(
        months=months,
        number_of_years=1,
        fraction_sum_tolerance=math.nextafter(0.25, -math.inf),
    )
    assert just_below.fractions_add_up is False

    neg_tol = rotation_c(
        months=_months([(1.0, 0.5)]),
        number_of_years=1,
        fraction_sum_tolerance=-1e-9,
    )
    assert isinstance(neg_tol.value, float)
    assert isinstance(neg_tol.fractions_add_up, ResultMissing)
    assert neg_tol.fractions_add_up.reason == "NOT_COMPUTABLE"


def test_rotation_c_precedence_and_multiple_missing_parts():
    """Missing fraction + missing years names both; outside fraction precedes number_of_years<=0."""
    bad_slr = SoilLossRatio(
        value=math.nan,
        canopy=math.nan,
        surface_cover=1.0,
        set_to_one=SET_TO_ONE,
        limit=DECLARED_LIMIT,
    )
    both_missing = rotation_c(
        months=[
            MonthOfRotation(
                label="PLACEHOLDER m0",
                erosivity_fraction=_missing(InputMissing),
                soil_loss_ratio=bad_slr,
            )
        ],
        number_of_years=_missing(ResultMissing),
        fraction_sum_tolerance=0.0,
    )
    assert isinstance(both_missing.value, ResultMissing)
    assert both_missing.value.reason == "MISSING_INPUT"
    assert "PLACEHOLDER m0" in both_missing.value.detail
    assert "number_of_years" in both_missing.value.detail

    outside_before_years = rotation_c(
        months=_months([(-0.25, 0.5)]),
        number_of_years=0,
        fraction_sum_tolerance=0.0,
    )
    assert isinstance(outside_before_years.value, ResultMissing)
    assert outside_before_years.value.reason == "NOT_COMPUTABLE"
    assert "PLACEHOLDER m0" in outside_before_years.value.detail
