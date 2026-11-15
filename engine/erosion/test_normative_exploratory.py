"""Tests for Rev13 normative vs exploratory erosion separation.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13), testing
``engine/erosion/normative_exploratory.py`` against ``27_PLAN_DE_FRONTERA.md``
§5.1 and ``28_PLAN_INTEGRADO_REV13.md`` §2.

Every number, unit, source, profile, and threshold in this file is a synthetic
PLACEHOLDER chosen for exact hand-checkable arithmetic, never a real science
or regulatory parameter value.

Run from the repository root:
    python -m pytest engine/erosion/test_normative_exploratory.py -q
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing
from engine.erosion import normative_exploratory as ne
from engine.erosion.normative_exploratory import (
    CLIMATE_HORIZONS,
    EROSION_EXPLORATORIA,
    EROSION_NORMATIVA,
    FACTOR_NAMES,
    NORMATIVE_BASIS_LONG_TERM,
    NORMATIVE_UNIT,
    CalibrationStatus,
    DualErosionSummary,
    ExploratoryErosionView,
    ExploratoryPoint,
    HorizonSeries,
    MethodChangeVsNormative,
    NormativeErosionView,
    NormativeFactor,
    NormativeFactors,
    NormativeFactorUnits,
    NormativePeriod,
    ProfileTolerance,
    VoluntaryThresholdCount,
    build_normative_erosion_view,
    combine_erosion_views,
    compute_horizon_mean,
    compute_normative_a_norm,
    compute_t_margin,
    compute_t_ratio,
    count_voluntary_threshold_exceedances,
)

# Synthetic PLACEHOLDER values chosen so hand-checks are exact:
# 2.0 * 0.5 * 0.25 * 4.0 * 3.0 = 3.0 Mg ha-1 yr-1
PLACEHOLDER_CASE_ID = "PLACEHOLDER-case-01"
PLACEHOLDER_FIELD_ID = "PLACEHOLDER-field-01"

PLACEHOLDER_FACTOR_UNITS = NormativeFactorUnits(
    r="PLACEHOLDER-unit-r",
    k="PLACEHOLDER-unit-k",
    c_rps="PLACEHOLDER-unit-c-rps",
    ls="PLACEHOLDER-unit-ls",
    p="PLACEHOLDER-unit-p",
)
PLACEHOLDER_FACTOR_VALUES = {
    "r": 2.0,
    "k": 0.5,
    "c_rps": 0.25,
    "ls": 4.0,
    "p": 3.0,
}
PLACEHOLDER_A_NORM = 3.0  # 2.0 * 0.5 * 0.25 * 4.0 * 3.0
PLACEHOLDER_TOLERANCE_VALUE = 6.0  # PLACEHOLDER: t_ratio = 0.5, t_margin = 3.0

PLACEHOLDER_PERIODS = (
    NormativePeriod(period_id="PLACEHOLDER-cycle-1", start_year=2001, end_year=2010),
    NormativePeriod(period_id="PLACEHOLDER-cycle-2", start_year=2011, end_year=2020),
)


def _make_factors(**overrides: NormativeFactor) -> NormativeFactors:
    base = {
        name: NormativeFactor(
            value=PLACEHOLDER_FACTOR_VALUES[name],
            unit=getattr(PLACEHOLDER_FACTOR_UNITS, name),
        )
        for name in FACTOR_NAMES
    }
    base.update(overrides)
    return NormativeFactors(**base)


def _make_tolerance(
    *,
    value: float | Missing = PLACEHOLDER_TOLERANCE_VALUE,
    unit: str = NORMATIVE_UNIT,
    editable: bool = False,
) -> ProfileTolerance:
    return ProfileTolerance(
        value=value,
        unit=unit,
        profile_id="PLACEHOLDER-profile-A",
        source="PLACEHOLDER-official-soil-table",
        version="PLACEHOLDER-v1",
        editable=editable,
    )


def _make_normative(**overrides: object) -> NormativeErosionView:
    kwargs: dict[str, object] = {
        "case_id": PLACEHOLDER_CASE_ID,
        "field_id": PLACEHOLDER_FIELD_ID,
        "factors": _make_factors(),
        "factor_units": PLACEHOLDER_FACTOR_UNITS,
        "tolerance_t": _make_tolerance(),
        "official_method": "PLACEHOLDER-official-method",
        "official_version": "PLACEHOLDER-v2",
        "reference_erosivity_source": "PLACEHOLDER-reference-erosivity",
        "periods": PLACEHOLDER_PERIODS,
    }
    kwargs.update(overrides)
    return build_normative_erosion_view(**kwargs)


def _make_changes() -> tuple[MethodChangeVsNormative, ...]:
    return (
        MethodChangeVsNormative(
            aspect="erosivity_r",
            normative_basis="PLACEHOLDER multi-year reference erosivity",
            exploratory_basis="PLACEHOLDER annual dynamic erosivity",
            note="PLACEHOLDER difference note",
        ),
    )


def _make_calibration(
    *,
    status: str = "global_literature_exploratory",
    imerg_slope_source: str = "global_literature",
    is_uruguay_calibrated: bool = False,
    evidence_note: str = "PLACEHOLDER global literature slope, uncalibrated locally",
) -> CalibrationStatus:
    return CalibrationStatus(
        status=status,  # type: ignore[arg-type]
        imerg_slope_source=imerg_slope_source,  # type: ignore[arg-type]
        is_uruguay_calibrated=is_uruguay_calibrated,
        evidence_note=evidence_note,
    )


def _make_historical_series() -> HorizonSeries:
    return HorizonSeries(
        horizon="historical",
        points=(
            ExploratoryPoint(
                year=2018,
                scenario="PLACEHOLDER-s1",
                horizon="historical",
                value=2.0,
                unit=NORMATIVE_UNIT,
            ),
            ExploratoryPoint(
                year=2019,
                scenario="PLACEHOLDER-s1",
                horizon="historical",
                value=8.0,
                unit=NORMATIVE_UNIT,
            ),
            ExploratoryPoint(
                year=2020,
                scenario="PLACEHOLDER-s1",
                horizon="historical",
                value=5.0,
                unit=NORMATIVE_UNIT,
            ),
        ),
    )


def _make_exploratory(**overrides: object) -> ExploratoryErosionView:
    hist = _make_historical_series()
    kwargs: dict[str, object] = {
        "case_id": PLACEHOLDER_CASE_ID,
        "field_id": PLACEHOLDER_FIELD_ID,
        "changes_vs_normative": _make_changes(),
        "calibration_status": _make_calibration(),
        "historical": hist,
    }
    kwargs.update(overrides)
    return ExploratoryErosionView(**kwargs)


# --- NormativeErosionView ----------------------------------------------------


def test_normative_happy_path_and_frozen_invariants() -> None:
    view = _make_normative()
    assert view.track == EROSION_NORMATIVA
    assert view.unit == NORMATIVE_UNIT
    assert view.a_norm_basis == NORMATIVE_BASIS_LONG_TERM
    assert view.a_norm == PLACEHOLDER_A_NORM
    assert view.t_ratio == 0.5  # 3.0 / 6.0
    assert view.t_margin == 3.0  # 6.0 - 3.0
    assert view.pre_evaluation is True
    assert view.official_parity_proven is False
    assert view.tolerance_t.editable is False
    assert view.tolerance_t.profile_id == "PLACEHOLDER-profile-A"
    assert view.tolerance_t.source == "PLACEHOLDER-official-soil-table"
    assert view.tolerance_t.version == "PLACEHOLDER-v1"
    assert view.factor_units == PLACEHOLDER_FACTOR_UNITS
    assert view.periods == PLACEHOLDER_PERIODS

    with pytest.raises(dataclasses.FrozenInstanceError):
        view.a_norm = 99.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.tolerance_t.value = 99.0  # type: ignore[misc]


def test_profile_tolerance_is_non_editable() -> None:
    with pytest.raises(ValueError, match="non-editable"):
        _make_tolerance(editable=True)
    with pytest.raises(TypeError, match="bool"):
        _make_tolerance(editable="false")  # type: ignore[arg-type]


@pytest.mark.parametrize("t_val", [0.0, 0, -2.5])
def test_t_ratio_is_not_computable_when_t_non_positive(t_val: float) -> None:
    tol = _make_tolerance(value=t_val)
    view = _make_normative(tolerance_t=tol)
    assert isinstance(view.t_ratio, Missing)
    assert view.t_ratio.reason == "NOT_COMPUTABLE"
    assert view.t_margin == float(t_val) - PLACEHOLDER_A_NORM


def test_t_ratio_and_margin_unit_mismatch_return_missing() -> None:
    tol = _make_tolerance(unit="PLACEHOLDER-other-unit")
    ratio = compute_t_ratio(a_norm=PLACEHOLDER_A_NORM, tolerance_t=tol)
    margin = compute_t_margin(a_norm=PLACEHOLDER_A_NORM, tolerance_t=tol)
    assert isinstance(ratio, Missing) and ratio.reason == "NOT_COMPUTABLE"
    assert isinstance(margin, Missing) and margin.reason == "NOT_COMPUTABLE"


def test_pre_evaluation_mandatory_unless_official_parity_proven() -> None:
    with pytest.raises(ValueError, match="pre_evaluation"):
        _make_normative(pre_evaluation=False, official_parity_proven=False)

    parity_view = _make_normative(pre_evaluation=False, official_parity_proven=True)
    assert parity_view.pre_evaluation is False
    assert parity_view.official_parity_proven is True

    both_true = _make_normative(pre_evaluation=True, official_parity_proven=True)
    assert both_true.pre_evaluation is True
    assert both_true.official_parity_proven is True


@pytest.mark.parametrize(
    "bad_basis",
    [
        "single_meteorological_year",
        "single_year",
        "exploratory",
        "future",
        "future_climate",
        "storm",
        "storm_mean",
        "event",
    ],
)
def test_hard_guard_refuses_non_normative_a_norm_basis(bad_basis: str) -> None:
    with pytest.raises(ValueError, match="hard guard"):
        _make_normative(a_norm_basis=bad_basis)


def test_hard_guard_refuses_single_year_or_empty_periods() -> None:
    with pytest.raises(ValueError, match="at least one NormativePeriod"):
        _make_normative(periods=())

    single_year = (
        NormativePeriod(period_id="PLACEHOLDER-2024", start_year=2024, end_year=2024),
    )
    with pytest.raises(ValueError, match="single meteorological year"):
        _make_normative(periods=single_year)

    two_parts_same_year = (
        NormativePeriod(period_id="PLACEHOLDER-2024a", start_year=2024, end_year=2024),
        NormativePeriod(period_id="PLACEHOLDER-2024b", start_year=2024, end_year=2024),
    )
    with pytest.raises(ValueError, match="single meteorological year"):
        _make_normative(periods=two_parts_same_year)


@pytest.mark.parametrize("absent_name", FACTOR_NAMES)
def test_g4_missing_factor_propagates_never_zero(absent_name: str) -> None:
    # Even when another factor is 0.0, a Missing factor must propagate Missing (never 0).
    other_name = next(name for name in FACTOR_NAMES if name != absent_name)
    factors = _make_factors(
        **{
            absent_name: NormativeFactor(
                value=Missing(reason="NOT_DECLARED", detail="PLACEHOLDER missing"),
                unit=getattr(PLACEHOLDER_FACTOR_UNITS, absent_name),
            ),
            other_name: NormativeFactor(
                value=0.0,
                unit=getattr(PLACEHOLDER_FACTOR_UNITS, other_name),
            ),
        }
    )
    view = _make_normative(factors=factors)
    assert isinstance(view.a_norm, Missing)
    assert view.a_norm.reason == "MISSING_INPUT"
    assert absent_name in (view.a_norm.detail or "")
    assert isinstance(view.t_ratio, Missing)
    assert view.t_ratio.reason == "MISSING_INPUT"
    assert isinstance(view.t_margin, Missing)
    assert view.t_margin.reason == "MISSING_INPUT"


def test_normative_factor_unit_mismatch_and_non_finite_return_missing() -> None:
    mismatched = _make_factors(
        c_rps=NormativeFactor(value=0.5, unit="PLACEHOLDER-wrong-unit")
    )
    a_norm = compute_normative_a_norm(
        factors=mismatched, accepted_units=PLACEHOLDER_FACTOR_UNITS
    )
    assert isinstance(a_norm, Missing)
    assert a_norm.reason == "NOT_COMPUTABLE"
    assert "c_rps" in (a_norm.detail or "")

    for bad_num in (math.nan, math.inf, -math.inf):
        non_finite = _make_factors(
            r=NormativeFactor(value=bad_num, unit=PLACEHOLDER_FACTOR_UNITS.r)
        )
        res = compute_normative_a_norm(
            factors=non_finite, accepted_units=PLACEHOLDER_FACTOR_UNITS
        )
        assert isinstance(res, Missing)
        assert res.reason == "NOT_COMPUTABLE"


def test_direct_normative_view_rejects_missing_factor_with_numeric_a_norm() -> None:
    factors = _make_factors(
        p=NormativeFactor(
            value=Missing(reason="NO_COVERAGE", detail="PLACEHOLDER absent"),
            unit=PLACEHOLDER_FACTOR_UNITS.p,
        )
    )
    with pytest.raises(ValueError, match="G4 violation"):
        NormativeErosionView(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            a_norm=0.0,
            tolerance_t=_make_tolerance(),
            t_ratio=0.0,
            t_margin=PLACEHOLDER_TOLERANCE_VALUE,
            official_method="PLACEHOLDER-m",
            official_version="PLACEHOLDER-v",
            reference_erosivity_source="PLACEHOLDER-ref",
            periods=PLACEHOLDER_PERIODS,
            factor_units=PLACEHOLDER_FACTOR_UNITS,
            factors=factors,
        )


def test_normative_rejects_wrong_unit_and_wrong_track() -> None:
    with pytest.raises(ValueError, match=NORMATIVE_UNIT):
        NormativeErosionView(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            a_norm=PLACEHOLDER_A_NORM,
            tolerance_t=_make_tolerance(),
            t_ratio=0.5,
            t_margin=3.0,
            official_method="PLACEHOLDER-m",
            official_version="PLACEHOLDER-v",
            reference_erosivity_source="PLACEHOLDER-ref",
            periods=PLACEHOLDER_PERIODS,
            factor_units=PLACEHOLDER_FACTOR_UNITS,
            unit="t ha-1 yr-1",
        )

    with pytest.raises(ValueError, match=EROSION_NORMATIVA):
        NormativeErosionView(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            a_norm=PLACEHOLDER_A_NORM,
            tolerance_t=_make_tolerance(),
            t_ratio=0.5,
            t_margin=3.0,
            official_method="PLACEHOLDER-m",
            official_version="PLACEHOLDER-v",
            reference_erosivity_source="PLACEHOLDER-ref",
            periods=PLACEHOLDER_PERIODS,
            factor_units=PLACEHOLDER_FACTOR_UNITS,
            track=EROSION_EXPLORATORIA,  # type: ignore[arg-type]
        )


# --- ExploratoryErosionView --------------------------------------------------


def test_exploratory_horizons_separation_and_refusal_to_mix_or_average() -> None:
    hist = _make_historical_series()
    synth = HorizonSeries(
        horizon="synthetic",
        points=(
            ExploratoryPoint(
                year=2025,
                scenario="PLACEHOLDER-syn",
                horizon="synthetic",
                value=4.0,
                unit=NORMATIVE_UNIT,
            ),
        ),
    )
    fut = HorizonSeries(
        horizon="future",
        points=(
            ExploratoryPoint(
                year=2040,
                scenario="PLACEHOLDER-fut",
                horizon="future",
                value=10.0,
                unit=NORMATIVE_UNIT,
            ),
        ),
    )
    view = _make_exploratory(historical=hist, synthetic=synth, future=fut)
    assert view.track == EROSION_EXPLORATORIA
    assert view.counts_legal_noncompliance is False
    assert view.counts_voluntary_target is True
    assert view.represents_channel_sediment_export is False
    assert compute_horizon_mean(hist) == 5.0  # (2 + 8 + 5) / 3

    # Refusing to mix horizons inside HorizonSeries
    with pytest.raises(ValueError, match="mix climate horizons"):
        HorizonSeries(
            horizon="historical",
            points=(
                ExploratoryPoint(
                    year=2020,
                    scenario="PLACEHOLDER-s1",
                    horizon="future",
                    value=1.0,
                    unit=NORMATIVE_UNIT,
                ),
            ),
        )

    # Refusing to assign wrong HorizonSeries to a horizon slot
    with pytest.raises(ValueError, match="horizon mismatch"):
        _make_exploratory(historical=fut)

    # Refusing to mix or average distinct horizons
    with pytest.raises(ValueError, match="mix or average distinct climate horizons"):
        compute_horizon_mean([hist, fut])
    with pytest.raises(ValueError, match="mix or average distinct climate horizons"):
        compute_horizon_mean([hist.points[0], synth.points[0]])

    # Duplicate (y, s) or mixed units inside one horizon rejected
    with pytest.raises(ValueError, match="duplicate"):
        HorizonSeries(
            horizon="historical",
            points=(hist.points[0], hist.points[0]),
        )
    with pytest.raises(ValueError, match="mixed units"):
        HorizonSeries(
            horizon="historical",
            points=(
                hist.points[0],
                ExploratoryPoint(
                    year=2021,
                    scenario="PLACEHOLDER-s1",
                    horizon="historical",
                    value=3.0,
                    unit="PLACEHOLDER-other-unit",
                ),
            ),
        )


def test_exploratory_horizon_mean_propagates_missing_never_zero() -> None:
    series = HorizonSeries(
        horizon="future",
        points=(
            ExploratoryPoint(
                year=2035,
                scenario="PLACEHOLDER-f1",
                horizon="future",
                value=6.0,
                unit=NORMATIVE_UNIT,
            ),
            ExploratoryPoint(
                year=2036,
                scenario="PLACEHOLDER-f1",
                horizon="future",
                value=Missing(reason="NO_COVERAGE", detail="PLACEHOLDER gap"),
                unit=NORMATIVE_UNIT,
            ),
        ),
    )
    mean = compute_horizon_mean(series)
    assert isinstance(mean, Missing)
    assert mean.reason == "MISSING_INPUT"
    assert "2036" in (mean.detail or "")


def test_exploratory_requires_explicit_changes_and_at_least_one_horizon() -> None:
    with pytest.raises(ValueError, match="changes_vs_normative"):
        _make_exploratory(changes_vs_normative=())
    with pytest.raises(ValueError, match="at least one HorizonSeries"):
        _make_exploratory(historical=None, synthetic=None, future=None)


def test_calibration_guard_refuses_global_literature_imerg_as_uruguay_calibrated() -> (
    None
):
    with pytest.raises(ValueError, match="Uruguay-calibrated"):
        _make_calibration(
            status="uruguay_calibrated",
            imerg_slope_source="global_literature",
            is_uruguay_calibrated=True,
            evidence_note="PLACEHOLDER local note",
        )

    with pytest.raises(ValueError, match="Uruguay-calibrated"):
        _make_calibration(
            status="global_literature_exploratory",
            imerg_slope_source="global_literature",
            is_uruguay_calibrated=True,
            evidence_note="PLACEHOLDER local note",
        )

    with pytest.raises(ValueError, match="Uruguay-calibrated"):
        _make_calibration(
            status="uruguay_calibrated",
            imerg_slope_source="global_literature",
            is_uruguay_calibrated=False,
            evidence_note="PLACEHOLDER note",
        )

    with pytest.raises(ValueError, match="Uruguay-calibrated"):
        _make_calibration(
            status="uruguay_calibrated",
            imerg_slope_source="not_used",
            is_uruguay_calibrated=True,
            evidence_note="PLACEHOLDER global IMERG slope applied",
        )

    # Valid local calibration without global literature IMERG slope
    local_ok = _make_calibration(
        status="uruguay_calibrated",
        imerg_slope_source="local_uruguay_calibration",
        is_uruguay_calibrated=True,
        evidence_note="PLACEHOLDER local calibration study",
    )
    assert local_ok.is_uruguay_calibrated is True


def test_voluntary_threshold_year_count_and_strict_flags() -> None:
    hist = _make_historical_series()  # values 2.0, 8.0, 5.0
    count = count_voluntary_threshold_exceedances(
        series=hist,
        scenario="PLACEHOLDER-s1",
        threshold_value=4.0,
        threshold_unit=NORMATIVE_UNIT,
    )
    assert isinstance(count, VoluntaryThresholdCount)
    assert count.horizon == "historical"
    assert count.scenario == "PLACEHOLDER-s1"
    assert count.exceedance_years == 2  # 8.0 and 5.0 > 4.0
    assert count.total_years == 3
    assert count.counts_legal_noncompliance is False
    assert count.counts_voluntary_target is True
    assert count.represents_channel_sediment_export is False

    view = _make_exploratory(voluntary_threshold_counts=(count,))
    assert view.voluntary_threshold_counts == (count,)

    # Missing point in scenario propagates Missing (never counts missing as 0)
    with_gap = HorizonSeries(
        horizon="historical",
        points=(
            hist.points[0],
            ExploratoryPoint(
                year=2021,
                scenario="PLACEHOLDER-s1",
                horizon="historical",
                value=Missing(reason="MISSING_INPUT", detail="PLACEHOLDER missing yr"),
                unit=NORMATIVE_UNIT,
            ),
        ),
    )
    gap_count = count_voluntary_threshold_exceedances(
        series=with_gap,
        scenario="PLACEHOLDER-s1",
        threshold_value=4.0,
        threshold_unit=NORMATIVE_UNIT,
    )
    assert isinstance(gap_count, Missing)
    assert gap_count.reason == "MISSING_INPUT"

    # Unit mismatch -> NOT_COMPUTABLE; absent scenario -> NO_COVERAGE
    unit_mismatch = count_voluntary_threshold_exceedances(
        series=hist,
        scenario="PLACEHOLDER-s1",
        threshold_value=4.0,
        threshold_unit="PLACEHOLDER-wrong-unit",
    )
    assert isinstance(unit_mismatch, Missing)
    assert unit_mismatch.reason == "NOT_COMPUTABLE"

    absent_scen = count_voluntary_threshold_exceedances(
        series=hist,
        scenario="PLACEHOLDER-missing-scenario",
        threshold_value=4.0,
        threshold_unit=NORMATIVE_UNIT,
    )
    assert isinstance(absent_scen, Missing)
    assert absent_scen.reason == "NO_COVERAGE"

    # Strict flag enforcement on VoluntaryThresholdCount and ExploratoryErosionView
    with pytest.raises(ValueError, match="counts_legal_noncompliance"):
        VoluntaryThresholdCount(
            horizon="historical",
            scenario="PLACEHOLDER-s1",
            threshold_value=4.0,
            threshold_unit=NORMATIVE_UNIT,
            exceedance_years=1,
            total_years=3,
            counts_legal_noncompliance=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="counts_voluntary_target"):
        VoluntaryThresholdCount(
            horizon="historical",
            scenario="PLACEHOLDER-s1",
            threshold_value=4.0,
            threshold_unit=NORMATIVE_UNIT,
            exceedance_years=1,
            total_years=3,
            counts_voluntary_target=False,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="represents_channel_sediment_export"):
        VoluntaryThresholdCount(
            horizon="historical",
            scenario="PLACEHOLDER-s1",
            threshold_value=4.0,
            threshold_unit=NORMATIVE_UNIT,
            exceedance_years=1,
            total_years=3,
            represents_channel_sediment_export=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="counts_legal_noncompliance"):
        _make_exploratory(counts_legal_noncompliance=True)
    with pytest.raises(ValueError, match="counts_voluntary_target"):
        _make_exploratory(counts_voluntary_target=False)
    with pytest.raises(ValueError, match="represents_channel_sediment_export"):
        _make_exploratory(represents_channel_sediment_export=True)


# --- DualErosionSummary & G5 -------------------------------------------------


def test_dual_erosion_summary_side_by_side_and_g5_guards() -> None:
    norm = _make_normative()
    expl = _make_exploratory()
    summary = combine_erosion_views(
        case_id=PLACEHOLDER_CASE_ID,
        field_id=PLACEHOLDER_FIELD_ID,
        normative=norm,
        exploratory=expl,
    )
    assert summary.normative is norm
    assert summary.exploratory is expl
    assert summary.allows_cross_track_averaging is False
    assert summary.normative.track == EROSION_NORMATIVA
    assert summary.exploratory.track == EROSION_EXPLORATORIA

    # Accepts typed Missing on either track
    missing_norm_summary = combine_erosion_views(
        case_id=PLACEHOLDER_CASE_ID,
        field_id=PLACEHOLDER_FIELD_ID,
        normative=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER not run"),
        exploratory=expl,
    )
    assert isinstance(missing_norm_summary.normative, Missing)

    # Refuses swapped tracks (strict TypeError)
    with pytest.raises(TypeError, match="NormativeErosionView"):
        combine_erosion_views(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            normative=expl,  # type: ignore[arg-type]
            exploratory=expl,
        )
    with pytest.raises(TypeError, match="ExploratoryErosionView"):
        combine_erosion_views(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            normative=norm,
            exploratory=norm,  # type: ignore[arg-type]
        )

    # Refuses cross-track averaging flag
    with pytest.raises(ValueError, match="allows_cross_track_averaging"):
        DualErosionSummary(
            case_id=PLACEHOLDER_CASE_ID,
            field_id=PLACEHOLDER_FIELD_ID,
            normative=norm,
            exploratory=expl,
            allows_cross_track_averaging=True,  # type: ignore[arg-type]
        )

    # G5: case_id / field_id mismatch raises ValueError
    with pytest.raises(ValueError, match="G5 mismatch"):
        combine_erosion_views(
            case_id="PLACEHOLDER-other-case",
            field_id=PLACEHOLDER_FIELD_ID,
            normative=norm,
            exploratory=expl,
        )
    with pytest.raises(ValueError, match="G5 mismatch"):
        combine_erosion_views(
            case_id=PLACEHOLDER_CASE_ID,
            field_id="PLACEHOLDER-other-field",
            normative=norm,
            exploratory=expl,
        )


def test_g5_strict_type_and_value_errors() -> None:
    # Rejects bool as numeric or int, and rejects InputsMissing / None
    with pytest.raises(TypeError):
        NormativeFactor(value=True, unit=PLACEHOLDER_FACTOR_UNITS.r)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        NormativeFactor(
            value=InputsMissing(reason="NOT_DECLARED"),  # type: ignore[arg-type]
            unit=PLACEHOLDER_FACTOR_UNITS.r,
        )
    with pytest.raises(TypeError):
        NormativePeriod(period_id="PLACEHOLDER-p", start_year=True, end_year=2020)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        NormativePeriod(period_id="PLACEHOLDER-p", start_year=2020, end_year=2019)
    with pytest.raises(ValueError):
        NormativePeriod(period_id="   ", start_year=2001, end_year=2010)
    with pytest.raises(TypeError):
        ExploratoryPoint(
            year=2020,
            scenario="PLACEHOLDER-s",
            horizon="historical",
            value=False,  # type: ignore[arg-type]
            unit=NORMATIVE_UNIT,
        )
    with pytest.raises(ValueError):
        ExploratoryPoint(
            year=2020,
            scenario="PLACEHOLDER-s",
            horizon="historical",
            value=math.nan,
            unit=NORMATIVE_UNIT,
        )
    with pytest.raises(ValueError):
        VoluntaryThresholdCount(
            horizon="historical",
            scenario="PLACEHOLDER-s",
            threshold_value=5.0,
            threshold_unit=NORMATIVE_UNIT,
            exceedance_years=4,
            total_years=3,
        )
    with pytest.raises(TypeError):
        compute_normative_a_norm(
            factors="not-factors",  # type: ignore[arg-type]
            accepted_units=PLACEHOLDER_FACTOR_UNITS,
        )
    with pytest.raises(ValueError):
        compute_normative_a_norm(
            factors=_make_factors(),
            accepted_units=PLACEHOLDER_FACTOR_UNITS,
            unit_guard_reason="NOT_A_REASON",  # type: ignore[arg-type]
        )


# --- G1 purity & zero invented constants -------------------------------------


SOURCE = Path(ne.__file__).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def test_g1_module_imports_only_stdlib_and_contracts() -> None:
    allowed = {
        "__future__",
        "math",
        "collections.abc",
        "dataclasses",
        "typing",
        "contracts.results.models",
    }
    imported: set[str] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports disallowed"
            if node.module is not None:
                imported.add(node.module)
    assert imported <= allowed
    assert "contracts.results.models" in imported


def test_module_contains_no_invented_float_constants() -> None:
    floats = [
        node.value
        for node in ast.walk(TREE)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert floats == []


def test_g1_determinism_and_horizon_vocabulary() -> None:
    assert CLIMATE_HORIZONS == ("historical", "synthetic", "future")
    first = _make_normative()
    second = _make_normative()
    assert first == second
