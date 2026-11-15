"""Analytical property and mutant-killing tests for ``engine/erosion/c_factor/``.

Every number, unit, and label in this file is a PLACEHOLDER chosen for
analytical invariants and hand arithmetic. None is a value of any method or
source.
"""

from __future__ import annotations

import itertools
import math

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing
from engine.erosion.c_factor import (
    DECLARED_LIMIT,
    SET_TO_ONE,
    MonthOfRotation,
    RotationC,
    SoilLossRatio,
    canopy_subfactor,
    effective_canopy_cover,
    residue_cover_from_mass,
    residue_mass_after_decay,
    residue_mass_over_time,
    rotation_c,
    soil_loss_ratio,
    surface_cover_subfactor,
    surface_cover_subfactor_percent,
)

TOLERANCE = 1e-12

PLACEHOLDER_LENGTH_UNIT = "PLACEHOLDER_length_unit"
PLACEHOLDER_MASS_UNIT = "PLACEHOLDER_mass_unit"
PLACEHOLDER_TIME_UNIT = "PLACEHOLDER_time_unit"
PLACEHOLDER_RESIDUE_A = "PLACEHOLDER_residue_a"
PLACEHOLDER_RESIDUE_B = "PLACEHOLDER_residue_b"

# PLACEHOLDER grid of cover fractions on [0, 1].
COVER_GRID = (0.0, 0.05, 0.2, 0.5, 0.75, 0.95, 1.0)
PLACEHOLDER_COEFFICIENTS = (0.0, 0.25, 1.5, 4.0)
PLACEHOLDER_HEIGHTS = (0.0, 0.5, 2.0, 8.0)


def _missing(shape=ResultMissing, reason: str = "NOT_DECLARED", detail: str = "PLACEHOLDER"):
    return shape(reason=reason, detail=detail)


def _slr(value: float | InputMissing | ResultMissing) -> SoilLossRatio:
    return soil_loss_ratio(canopy=value, surface_cover=1.0)


# --- effective_canopy_cover -------------------------------------------------


def test_effective_canopy_cover_bounds_partition_and_monotonicity():
    """0 <= effective <= canopy_cover and <= 1 - ground_cover; monotone in both; exact partition."""
    for c in COVER_GRID:
        for g in COVER_GRID:
            eff = effective_canopy_cover(canopy_cover=c, ground_cover=g)
            assert isinstance(eff, float)
            assert 0.0 <= eff <= c + TOLERANCE
            assert eff <= (1.0 - g) + TOLERANCE
            # Exact partition of canopy over uncovered vs covered ground: eff + c * g == c.
            assert eff + c * g == pytest.approx(c, abs=TOLERANCE)

        # Boundary identities for fixed canopy_cover.
        assert effective_canopy_cover(canopy_cover=c, ground_cover=0.0) == pytest.approx(
            c, abs=TOLERANCE
        )
        assert effective_canopy_cover(canopy_cover=c, ground_cover=1.0) == 0.0

        # Non-increasing in ground_cover; strictly decreasing when canopy_cover > 0.
        by_ground = [
            effective_canopy_cover(canopy_cover=c, ground_cover=g) for g in COVER_GRID
        ]
        assert all(later <= earlier for earlier, later in zip(by_ground, by_ground[1:]))
        if c > 0.0:
            assert all(
                later < earlier for earlier, later in zip(by_ground, by_ground[1:])
            )

    for g in COVER_GRID:
        assert effective_canopy_cover(canopy_cover=0.0, ground_cover=g) == 0.0
        by_canopy = [
            effective_canopy_cover(canopy_cover=c, ground_cover=g) for c in COVER_GRID
        ]
        assert all(later >= earlier for earlier, later in zip(by_canopy, by_canopy[1:]))
        if g < 1.0:
            assert all(
                later > earlier for earlier, later in zip(by_canopy, by_canopy[1:])
            )


# --- canopy_subfactor -------------------------------------------------------


def test_canopy_subfactor_bounds_endpoints_and_monotonicity():
    """1 - c <= CC <= 1; non-increasing in cover, non-decreasing in height and coefficient."""
    for k in PLACEHOLDER_COEFFICIENTS:
        for h in PLACEHOLDER_HEIGHTS:
            assert (
                canopy_subfactor(
                    canopy_cover=0.0,
                    fall_height=h,
                    fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                    fall_height_coefficient=k,
                    fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
                )
                == 1.0
            )
            by_cover = [
                canopy_subfactor(
                    canopy_cover=c,
                    fall_height=h,
                    fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                    fall_height_coefficient=k,
                    fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
                )
                for c in COVER_GRID
            ]
            for c, val in zip(COVER_GRID, by_cover, strict=True):
                assert isinstance(val, float)
                assert (1.0 - c) - TOLERANCE <= val <= 1.0 + TOLERANCE
                assert 0.0 <= val <= 1.0
            # Strictly decreasing in canopy_cover (for finite k * h).
            assert all(
                later < earlier for earlier, later in zip(by_cover, by_cover[1:])
            )

    for c in COVER_GRID:
        for k in PLACEHOLDER_COEFFICIENTS:
            at_zero_h = canopy_subfactor(
                canopy_cover=c,
                fall_height=0.0,
                fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                fall_height_coefficient=k,
                fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
            )
            assert at_zero_h == pytest.approx(1.0 - c, abs=TOLERANCE)

            by_height = [
                canopy_subfactor(
                    canopy_cover=c,
                    fall_height=h,
                    fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                    fall_height_coefficient=k,
                    fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
                )
                for h in PLACEHOLDER_HEIGHTS
            ]
            assert all(
                later >= earlier for earlier, later in zip(by_height, by_height[1:])
            )
            if c > 0.0 and k > 0.0:
                assert all(
                    later > earlier for earlier, later in zip(by_height, by_height[1:])
                )

        for h in PLACEHOLDER_HEIGHTS:
            at_zero_k = canopy_subfactor(
                canopy_cover=c,
                fall_height=h,
                fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                fall_height_coefficient=0.0,
                fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
            )
            assert at_zero_k == pytest.approx(1.0 - c, abs=TOLERANCE)

            by_coeff = [
                canopy_subfactor(
                    canopy_cover=c,
                    fall_height=h,
                    fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
                    fall_height_coefficient=coeff,
                    fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
                )
                for coeff in PLACEHOLDER_COEFFICIENTS
            ]
            assert all(
                later >= earlier for earlier, later in zip(by_coeff, by_coeff[1:])
            )
            if c > 0.0 and h > 0.0:
                assert all(
                    later > earlier for earlier, later in zip(by_coeff, by_coeff[1:])
                )


def test_canopy_subfactor_height_coefficient_scale_invariance_and_ground_cover_composition():
    """CC(c, alpha*h, k/alpha) == CC(c, h, k), and higher ground_cover never lowers CC."""
    c, h, k = 0.6, 2.5, 0.8
    baseline = canopy_subfactor(
        canopy_cover=c,
        fall_height=h,
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
        fall_height_coefficient=k,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    for alpha in (0.1, 0.5, 3.0, 100.0):
        scaled = canopy_subfactor(
            canopy_cover=c,
            fall_height=alpha * h,
            fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
            fall_height_coefficient=k / alpha,
            fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
        )
        assert scaled == pytest.approx(baseline, abs=TOLERANCE)

    # Composing effective_canopy_cover with canopy_subfactor is non-decreasing in ground_cover.
    composed = [
        canopy_subfactor(
            canopy_cover=effective_canopy_cover(canopy_cover=0.75, ground_cover=g),
            fall_height=1.5,
            fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
            fall_height_coefficient=0.5,
            fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
        )
        for g in COVER_GRID
    ]
    assert all(later > earlier for earlier, later in zip(composed, composed[1:]))
    assert composed[-1] == 1.0


# --- surface_cover_subfactor & surface_cover_subfactor_percent --------------


def test_surface_cover_subfactor_bounds_monotonicity_and_semigroup():
    """exp(-b) <= SC <= 1; strictly decreasing for b > 0; SC(c1 + c2) == SC(c1) * SC(c2)."""
    for b in PLACEHOLDER_COEFFICIENTS:
        assert (
            surface_cover_subfactor(
                surface_residue_cover=0.0, surface_cover_coefficient=b
            )
            == 1.0
        )
        by_cover = [
            surface_cover_subfactor(
                surface_residue_cover=c, surface_cover_coefficient=b
            )
            for c in COVER_GRID
        ]
        lower_bound = math.exp(-b)
        for val in by_cover:
            assert isinstance(val, float)
            assert lower_bound - TOLERANCE <= val <= 1.0
            assert 0.0 < val <= 1.0
        if b > 0.0:
            assert all(
                later < earlier for earlier, later in zip(by_cover, by_cover[1:])
            )
        else:
            assert all(val == 1.0 for val in by_cover)

        # Semigroup property on the cover domain: SC(c1 + c2, b) == SC(c1, b) * SC(c2, b).
        for c1, c2 in ((0.15, 0.35), (0.0, 0.6), (0.4, 0.6)):
            lhs = surface_cover_subfactor(
                surface_residue_cover=c1 + c2, surface_cover_coefficient=b
            )
            rhs = surface_cover_subfactor(
                surface_residue_cover=c1, surface_cover_coefficient=b
            ) * surface_cover_subfactor(
                surface_residue_cover=c2, surface_cover_coefficient=b
            )
            assert lhs == pytest.approx(rhs, abs=TOLERANCE)

    # Monotonicity in surface_cover_coefficient for cover > 0.
    for c in (0.2, 0.75, 1.0):
        by_coeff = [
            surface_cover_subfactor(
                surface_residue_cover=c, surface_cover_coefficient=b
            )
            for b in PLACEHOLDER_COEFFICIENTS
        ]
        assert all(later < earlier for earlier, later in zip(by_coeff, by_coeff[1:]))


def test_surface_cover_subfactor_percent_matches_100x_unit_scaling():
    """surface_cover_subfactor_percent(c, b_pct) == surface_cover_subfactor(c, 100 * b_pct)."""
    for b_pct in (0.0, 0.005, 0.025, 0.08):
        by_cover = [
            surface_cover_subfactor_percent(
                surface_residue_cover=c,
                surface_cover_coefficient_per_percent=b_pct,
            )
            for c in COVER_GRID
        ]
        for c, val in zip(COVER_GRID, by_cover, strict=True):
            expected = surface_cover_subfactor(
                surface_residue_cover=c,
                surface_cover_coefficient=100.0 * b_pct,
            )
            assert val == pytest.approx(expected, abs=TOLERANCE)
            assert math.exp(-100.0 * b_pct) - TOLERANCE <= val <= 1.0
        if b_pct > 0.0:
            assert all(
                later < earlier for earlier, later in zip(by_cover, by_cover[1:])
            )


# --- soil_loss_ratio --------------------------------------------------------


def test_soil_loss_ratio_bounds_monotonicity_and_declared_limit():
    """0 <= SLR <= min(CC, SC) <= 1; monotone in covers/height; limit metadata always kept."""
    cc_vals = [
        canopy_subfactor(
            canopy_cover=c,
            fall_height=1.5,
            fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
            fall_height_coefficient=0.4,
            fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
        )
        for c in COVER_GRID
    ]
    sc_vals = [
        surface_cover_subfactor(
            surface_residue_cover=r, surface_cover_coefficient=2.5
        )
        for r in COVER_GRID
    ]
    for cc in cc_vals:
        for sc in sc_vals:
            slr = soil_loss_ratio(canopy=cc, surface_cover=sc)
            assert isinstance(slr.value, float)
            assert 0.0 <= slr.value <= min(cc, sc) + TOLERANCE <= 1.0 + TOLERANCE
            assert slr.value == pytest.approx(cc * sc, abs=TOLERANCE)
            assert slr.set_to_one == SET_TO_ONE
            assert slr.limit == DECLARED_LIMIT
            # Symmetry of the product.
            swapped = soil_loss_ratio(canopy=sc, surface_cover=cc)
            assert slr.value == pytest.approx(swapped.value, abs=TOLERANCE)

    # Identity and zero absorption.
    assert soil_loss_ratio(canopy=0.42, surface_cover=1.0).value == 0.42
    assert soil_loss_ratio(canopy=1.0, surface_cover=0.42).value == 0.42
    assert soil_loss_ratio(canopy=0.42, surface_cover=0.0).value == 0.0
    assert soil_loss_ratio(canopy=0.0, surface_cover=0.42).value == 0.0

    # Monotonicity: strictly decreasing as canopy_cover or surface_residue_cover increases.
    by_canopy = [soil_loss_ratio(canopy=cc, surface_cover=0.6).value for cc in cc_vals]
    by_surface = [soil_loss_ratio(canopy=0.6, surface_cover=sc).value for sc in sc_vals]
    assert all(later < earlier for earlier, later in zip(by_canopy, by_canopy[1:]))
    assert all(later < earlier for earlier, later in zip(by_surface, by_surface[1:]))


# --- residue.py -------------------------------------------------------------


def test_residue_cover_from_mass_bounds_monotonicity_and_complement_semigroup():
    """0 <= cover < 1; monotone in mass and coeff; (1 - cover(m1))*(1 - cover(m2)) == 1 - cover(m1+m2)."""
    masses = (0.0, 0.25, 1.0, 3.5, 10.0)
    for k in PLACEHOLDER_COEFFICIENTS:
        assert (
            residue_cover_from_mass(
                residue_mass=0.0,
                residue_mass_unit=PLACEHOLDER_MASS_UNIT,
                mass_cover_coefficient=k,
                mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
            )
            == 0.0
        )
        by_mass = [
            residue_cover_from_mass(
                residue_mass=m,
                residue_mass_unit=PLACEHOLDER_MASS_UNIT,
                mass_cover_coefficient=k,
                mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
            )
            for m in masses
        ]
        assert all(0.0 <= val <= 1.0 for val in by_mass)
        if k > 0.0:
            assert all(
                later > earlier for earlier, later in zip(by_mass, by_mass[1:])
            )
            # Complementary exponential identity.
            c1 = residue_cover_from_mass(
                residue_mass=1.25,
                residue_mass_unit=PLACEHOLDER_MASS_UNIT,
                mass_cover_coefficient=k,
                mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
            )
            c2 = residue_cover_from_mass(
                residue_mass=2.75,
                residue_mass_unit=PLACEHOLDER_MASS_UNIT,
                mass_cover_coefficient=k,
                mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
            )
            c_sum = residue_cover_from_mass(
                residue_mass=4.0,
                residue_mass_unit=PLACEHOLDER_MASS_UNIT,
                mass_cover_coefficient=k,
                mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
            )
            assert (1.0 - c1) * (1.0 - c2) == pytest.approx(1.0 - c_sum, abs=TOLERANCE)

    # Scale invariance in (k, mass): cover(alpha * m, k / alpha) == cover(m, k).
    base_cover = residue_cover_from_mass(
        residue_mass=2.0,
        residue_mass_unit=PLACEHOLDER_MASS_UNIT,
        mass_cover_coefficient=0.75,
        mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
    )
    for alpha in (0.25, 4.0, 100.0):
        scaled = residue_cover_from_mass(
            residue_mass=alpha * 2.0,
            residue_mass_unit=PLACEHOLDER_MASS_UNIT,
            mass_cover_coefficient=0.75 / alpha,
            mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
        )
        assert scaled == pytest.approx(base_cover, abs=TOLERANCE)


def test_residue_decay_bounds_linearity_monotonicity_and_semigroup():
    """0 <= m_after <= m; homogeneous of degree 1 in mass; Chapman-Kolmogorov time splitting."""
    coeffs = {PLACEHOLDER_RESIDUE_A: 0.2, PLACEHOLDER_RESIDUE_B: 0.5}
    times = (0.0, 0.5, 2.0, 7.0)

    # Zero mass stays zero; zero time or zero decay coefficient preserves mass.
    assert (
        residue_mass_after_decay(
            residue_mass=0.0,
            residue_type=PLACEHOLDER_RESIDUE_A,
            decay_coefficients=coeffs,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=5.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        == 0.0
    )
    assert (
        residue_mass_after_decay(
            residue_mass=4.5,
            residue_type=PLACEHOLDER_RESIDUE_A,
            decay_coefficients={PLACEHOLDER_RESIDUE_A: 0.0},
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=5.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        == 4.5
    )

    # Monotone decreasing in elapsed_time and in decay_coefficient.
    m0 = 10.0
    by_time = [
        residue_mass_after_decay(
            residue_mass=m0,
            residue_type=PLACEHOLDER_RESIDUE_A,
            decay_coefficients=coeffs,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=t,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        for t in times
    ]
    assert by_time[0] == m0
    assert all(0.0 <= val <= m0 for val in by_time)
    assert all(later < earlier for earlier, later in zip(by_time, by_time[1:]))

    fast = residue_mass_after_decay(
        residue_mass=m0,
        residue_type=PLACEHOLDER_RESIDUE_B,
        decay_coefficients=coeffs,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        elapsed_time=2.0,
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    slow = residue_mass_after_decay(
        residue_mass=m0,
        residue_type=PLACEHOLDER_RESIDUE_A,
        decay_coefficients=coeffs,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        elapsed_time=2.0,
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert fast < slow

    # Linear homogeneity in residue_mass: decay(alpha * m, t) == alpha * decay(m, t).
    for alpha in (0.5, 3.0, 10.0):
        scaled = residue_mass_after_decay(
            residue_mass=alpha * m0,
            residue_type=PLACEHOLDER_RESIDUE_A,
            decay_coefficients=coeffs,
            decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
            elapsed_time=2.0,
            elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
        )
        assert scaled == pytest.approx(alpha * slow, abs=TOLERANCE)

    # Semigroup / Chapman-Kolmogorov: multi-step decay over [t1, t2, t3] matches single step t1+t2+t3.
    durations = (1.25, 0.0, 2.75, 4.0)
    series = residue_mass_over_time(
        initial_residue_mass=m0,
        residue_type=PLACEHOLDER_RESIDUE_A,
        decay_coefficients=coeffs,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        step_durations=durations,
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(series, tuple) and len(series) == len(durations)
    assert all(later <= earlier for earlier, later in zip((m0, *series), series))
    assert series[1] == series[0]  # zero-duration step leaves mass unchanged
    direct = residue_mass_after_decay(
        residue_mass=m0,
        residue_type=PLACEHOLDER_RESIDUE_A,
        decay_coefficients=coeffs,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        elapsed_time=sum(durations),
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert series[-1] == pytest.approx(direct, abs=TOLERANCE)


# --- rotation.py ------------------------------------------------------------


def test_rotation_c_convex_bounds_linearity_permutation_and_non_normalisation():
    """Convex bounds on normalized fractions, SLR linearity, month-order invariance, and year scaling."""
    # Exact convex combination when fractions sum to number_of_years.
    fractions = (0.1, 0.3, 0.6, 0.25, 0.75)
    slrs = (0.2, 0.8, 0.4, 0.1, 0.9)
    months = [
        MonthOfRotation(
            label=f"PLACEHOLDER m{i}",
            erosivity_fraction=f,
            soil_loss_ratio=_slr(r),
        )
        for i, (f, r) in enumerate(zip(fractions, slrs, strict=True))
    ]
    res = rotation_c(
        months=months, number_of_years=2, fraction_sum_tolerance=1e-9
    )
    assert isinstance(res, RotationC)
    assert isinstance(res.value, float)
    assert res.fractions_add_up is True
    assert min(slrs) <= res.value <= max(slrs)
    assert res.set_to_one == SET_TO_ONE
    assert res.limit == DECLARED_LIMIT

    # Constant SLR = c across normalized fractions gives C == c.
    const_months = [
        MonthOfRotation(
            label=f"PLACEHOLDER m{i}",
            erosivity_fraction=f,
            soil_loss_ratio=_slr(0.45),
        )
        for i, f in enumerate(fractions)
    ]
    const_res = rotation_c(
        months=const_months, number_of_years=2, fraction_sum_tolerance=1e-9
    )
    assert const_res.value == pytest.approx(0.45, abs=TOLERANCE)

    # Positive scaling of SLR scales C by the same factor.
    scale = 0.5
    scaled_months = [
        MonthOfRotation(
            label=f"PLACEHOLDER m{i}",
            erosivity_fraction=f,
            soil_loss_ratio=_slr(scale * r),
        )
        for i, (f, r) in enumerate(zip(fractions, slrs, strict=True))
    ]
    scaled_res = rotation_c(
        months=scaled_months, number_of_years=2, fraction_sum_tolerance=1e-9
    )
    assert scaled_res.value == pytest.approx(scale * res.value, abs=TOLERANCE)

    # Order permutation invariance (all rotations of months give the same C).
    for perm in itertools.islice(itertools.permutations(months), 12):
        perm_res = rotation_c(
            months=list(perm), number_of_years=2, fraction_sum_tolerance=1e-9
        )
        assert perm_res.value == pytest.approx(res.value, abs=TOLERANCE)
        assert perm_res.fraction_sum == pytest.approx(res.fraction_sum, abs=TOLERANCE)
        assert perm_res.fractions_add_up is True

    # Monotonicity: raising one month's SLR with positive erosivity fraction raises C.
    raised = list(months)
    raised[2] = MonthOfRotation(
        label="PLACEHOLDER m2", erosivity_fraction=0.6, soil_loss_ratio=_slr(0.5)
    )
    raised_res = rotation_c(
        months=raised, number_of_years=2, fraction_sum_tolerance=1e-9
    )
    assert raised_res.value > res.value

    # Non-normalisation: changing number_of_years divides C without normalising fractions.
    four_years = rotation_c(
        months=months, number_of_years=4, fraction_sum_tolerance=1e-9
    )
    assert four_years.value == pytest.approx(res.value / 2.0, abs=TOLERANCE)
    assert four_years.fraction_sum == pytest.approx(2.0, abs=TOLERANCE)
    assert four_years.expected_fraction_sum == 4.0
    assert four_years.fractions_add_up is False


# --- Missing propagation across c_factor ------------------------------------


@pytest.mark.parametrize("shape", [InputMissing, ResultMissing], ids=["input", "result"])
def test_c_factor_missing_propagation_across_all_modules(shape):
    """Missing values propagate as ResultMissing(MISSING_INPUT) and preserve independent fields."""
    gap = _missing(shape, reason="NO_COVERAGE", detail="PLACEHOLDER gap")

    # 1. Subfactors: missing input -> MISSING_INPUT naming the missing argument.
    eff = effective_canopy_cover(canopy_cover=gap, ground_cover=0.5)
    assert isinstance(eff, ResultMissing) and eff.reason == "MISSING_INPUT"
    assert "canopy_cover" in eff.detail

    cc = canopy_subfactor(
        canopy_cover=eff,
        fall_height=1.0,
        fall_height_unit=PLACEHOLDER_LENGTH_UNIT,
        fall_height_coefficient=0.5,
        fall_height_coefficient_per_unit=PLACEHOLDER_LENGTH_UNIT,
    )
    assert isinstance(cc, ResultMissing) and cc.reason == "MISSING_INPUT"
    assert "canopy_cover" in cc.detail

    sc_pct = surface_cover_subfactor_percent(
        surface_residue_cover=0.5,
        surface_cover_coefficient_per_percent=gap,
    )
    assert isinstance(sc_pct, ResultMissing) and sc_pct.reason == "MISSING_INPUT"
    assert "surface_cover_coefficient_per_percent" in sc_pct.detail

    # SoilLossRatio preserves canopy, surface_cover, set_to_one, limit even when missing.
    slr = soil_loss_ratio(canopy=cc, surface_cover=0.8)
    assert isinstance(slr.value, ResultMissing) and slr.value.reason == "MISSING_INPUT"
    assert "canopy" in slr.value.detail
    assert slr.canopy is cc
    assert slr.surface_cover == 0.8
    assert slr.set_to_one == SET_TO_ONE
    assert slr.limit == DECLARED_LIMIT

    # 2. Residue: missing mass/coeff/step propagates; unselected missing coeff does NOT fail.
    cov = residue_cover_from_mass(
        residue_mass=gap,
        residue_mass_unit=PLACEHOLDER_MASS_UNIT,
        mass_cover_coefficient=0.5,
        mass_cover_coefficient_per_unit=PLACEHOLDER_MASS_UNIT,
    )
    assert isinstance(cov, ResultMissing) and cov.reason == "MISSING_INPUT"
    assert "residue_mass" in cov.detail

    coeffs_with_unselected_missing = {
        PLACEHOLDER_RESIDUE_A: 0.2,
        PLACEHOLDER_RESIDUE_B: gap,
    }
    ok_decay = residue_mass_after_decay(
        residue_mass=4.0,
        residue_type=PLACEHOLDER_RESIDUE_A,
        decay_coefficients=coeffs_with_unselected_missing,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        elapsed_time=1.0,
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(ok_decay, float)

    bad_decay = residue_mass_after_decay(
        residue_mass=4.0,
        residue_type=PLACEHOLDER_RESIDUE_B,
        decay_coefficients=coeffs_with_unselected_missing,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        elapsed_time=1.0,
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(bad_decay, ResultMissing) and bad_decay.reason == "MISSING_INPUT"
    assert PLACEHOLDER_RESIDUE_B in bad_decay.detail

    series = residue_mass_over_time(
        initial_residue_mass=4.0,
        residue_type=PLACEHOLDER_RESIDUE_A,
        decay_coefficients=coeffs_with_unselected_missing,
        decay_coefficient_per_unit=PLACEHOLDER_TIME_UNIT,
        step_durations=[1.0, gap, 1.0],
        elapsed_time_unit=PLACEHOLDER_TIME_UNIT,
    )
    assert isinstance(series, ResultMissing) and series.reason == "MISSING_INPUT"
    assert "step 1" in series.detail and "step_durations[1]" in series.detail

    # 3. Rotation: partial missingness isolates only the fields that depend on the missing part.
    # Missing SLR leaves fraction_sum, expected_fraction_sum, fractions_add_up intact.
    rot_missing_slr = rotation_c(
        months=[
            MonthOfRotation(
                label="PLACEHOLDER m0", erosivity_fraction=0.5, soil_loss_ratio=slr
            ),
            MonthOfRotation(
                label="PLACEHOLDER m1",
                erosivity_fraction=0.5,
                soil_loss_ratio=_slr(0.4),
            ),
        ],
        number_of_years=1,
        fraction_sum_tolerance=0.0,
    )
    assert (
        isinstance(rot_missing_slr.value, ResultMissing)
        and rot_missing_slr.value.reason == "MISSING_INPUT"
    )
    assert "PLACEHOLDER m0" in rot_missing_slr.value.detail
    assert rot_missing_slr.fraction_sum == 1.0
    assert rot_missing_slr.expected_fraction_sum == 1.0
    assert rot_missing_slr.fractions_add_up is True

    # Missing erosivity_fraction leaves expected_fraction_sum intact.
    rot_missing_frac = rotation_c(
        months=[
            MonthOfRotation(
                label="PLACEHOLDER m0",
                erosivity_fraction=gap,
                soil_loss_ratio=_slr(0.4),
            ),
        ],
        number_of_years=1,
        fraction_sum_tolerance=0.0,
    )
    assert isinstance(rot_missing_frac.value, ResultMissing)
    assert rot_missing_frac.value.reason == "MISSING_INPUT"
    assert isinstance(rot_missing_frac.fraction_sum, ResultMissing)
    assert isinstance(rot_missing_frac.fractions_add_up, ResultMissing)
    assert rot_missing_frac.expected_fraction_sum == 1.0

    # Missing number_of_years leaves fraction_sum intact.
    rot_missing_years = rotation_c(
        months=[
            MonthOfRotation(
                label="PLACEHOLDER m0",
                erosivity_fraction=1.0,
                soil_loss_ratio=_slr(0.4),
            ),
        ],
        number_of_years=gap,
        fraction_sum_tolerance=0.0,
    )
    assert isinstance(rot_missing_years.value, ResultMissing)
    assert rot_missing_years.value.reason == "MISSING_INPUT"
    assert rot_missing_years.fraction_sum == 1.0
    assert isinstance(rot_missing_years.expected_fraction_sum, ResultMissing)
    assert isinstance(rot_missing_years.fractions_add_up, ResultMissing)

    # Missing tolerance leaves value, fraction_sum, expected_fraction_sum intact.
    rot_missing_tol = rotation_c(
        months=[
            MonthOfRotation(
                label="PLACEHOLDER m0",
                erosivity_fraction=1.0,
                soil_loss_ratio=_slr(0.4),
            ),
        ],
        number_of_years=1,
        fraction_sum_tolerance=gap,
    )
    assert rot_missing_tol.value == pytest.approx(0.4, abs=TOLERANCE)
    assert rot_missing_tol.fraction_sum == 1.0
    assert rot_missing_tol.expected_fraction_sum == 1.0
    assert isinstance(rot_missing_tol.fractions_add_up, ResultMissing)
    assert rot_missing_tol.fractions_add_up.reason == "MISSING_INPUT"
