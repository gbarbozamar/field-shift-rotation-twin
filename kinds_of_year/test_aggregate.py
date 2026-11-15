"""Acceptance test of the unit l2/by-kind-of-year (brief S-013). PROPOSED.

Run with ``uv run pytest kinds_of_year/``. Every series below is invented test
data, made by hand for this test: it is not a result of any engine and not a
value of any real field. Every expected mean is written as arithmetic on those
invented values (PROPOSED), never as a number taken from anywhere else.
"""

import copy
import dataclasses
import math

import pytest

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.results.models import (
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_WATER_DEFICIT_EXPOSURE,
    AnnualSoilLoss,
    MonthlySoilLoss,
    WaterDeficitExposure,
)
from kinds_of_year import (
    KindMean,
    KindOfYear,
    MeansByKind,
    YearValue,
    mean_by_kind,
    series_from_results,
)

EL_NINO, NEUTRAL, LA_NINA = KINDS_OF_YEAR
INDICATOR = "soil_loss"
UNIT = UNIT_SOIL_LOSS_ANNUAL


def kind(name):
    return KindOfYear(
        kind=name, missing_reason=None, detail=None, season=None, season_year=None
    )


def no_kind():
    return KindOfYear(
        kind=None,
        missing_reason="NO_COVERAGE",
        detail="invented test case",
        season=None,
        season_year=None,
    )


def present(value):
    return YearValue(value=value, reason=None, detail=None)


def absent(reason, detail=None):
    return YearValue(value=None, reason=reason, detail=detail)


# Invented test data: six agricultural years, two of each kind.
SIX_KINDS = {
    2001: kind(EL_NINO),
    2002: kind(NEUTRAL),
    2003: kind(LA_NINA),
    2004: kind(EL_NINO),
    2005: kind(NEUTRAL),
    2006: kind(LA_NINA),
}
SIX_VALUES = {
    2001: present(1.0),
    2002: present(2.0),
    2003: present(4.0),
    2004: present(3.0),
    2005: present(6.0),
    2006: present(8.0),
}


# --- 1. six years, two of each kind -------------------------------------------


def test_six_years_two_of_each_kind():
    result = mean_by_kind(INDICATOR, UNIT, SIX_VALUES, SIX_KINDS)
    assert isinstance(result, MeansByKind)
    assert result.indicator == INDICATOR
    assert result.unit == UNIT
    assert tuple(result.by_kind) == KINDS_OF_YEAR
    # PROPOSED expected means, arithmetic on the invented values.
    expected = {
        EL_NINO: ((1.0 + 3.0) / 2, (2001, 2004)),
        NEUTRAL: ((2.0 + 6.0) / 2, (2002, 2005)),
        LA_NINA: ((4.0 + 8.0) / 2, (2003, 2006)),
    }
    for name, (value, years) in expected.items():
        item = result.by_kind[name]
        assert item.value == pytest.approx(value)
        assert item.unit == UNIT
        assert item.n_years == 2
        assert item.ag_years == years
        assert item.reason is None
        assert item.detail is None
    # PROPOSED expected record mean.
    assert result.record.value == pytest.approx((1.0 + 2.0 + 4.0 + 3.0 + 6.0 + 8.0) / 6)
    assert result.record.n_years == 6
    assert result.record.ag_years == (2001, 2002, 2003, 2004, 2005, 2006)
    assert result.record.reason is None
    assert result.unclassified_years == ()


# --- 2. a kind with no year ---------------------------------------------------


def test_kind_with_no_year_is_missing_no_coverage():
    kinds = {year: k for year, k in SIX_KINDS.items() if k.kind != LA_NINA}
    series = {year: SIX_VALUES[year] for year in kinds}
    result = mean_by_kind(INDICATOR, UNIT, series, kinds)
    la_nina = result.by_kind[LA_NINA]
    assert la_nina.value is None
    assert la_nina.value != 0
    assert la_nina.reason == "NO_COVERAGE"
    assert la_nina.detail == "no agricultural year of the record is la_nina"
    assert la_nina.n_years == 0
    assert la_nina.ag_years == ()
    # PROPOSED expected means of the two other kinds.
    assert result.by_kind[EL_NINO].value == pytest.approx((1.0 + 3.0) / 2)
    assert result.by_kind[NEUTRAL].value == pytest.approx((2.0 + 6.0) / 2)
    assert result.record.value == pytest.approx((1.0 + 2.0 + 3.0 + 6.0) / 4)


# --- 3. a year with a missing value -------------------------------------------


def test_missing_value_makes_its_group_and_the_record_missing():
    series = dict(SIX_VALUES)
    series[2005] = absent("NOT_COMPUTABLE", "invented test case")
    result = mean_by_kind(INDICATOR, UNIT, series, SIX_KINDS)

    neutral = result.by_kind[NEUTRAL]
    assert neutral.value is None
    assert neutral.reason == "MISSING_INPUT"
    assert "2005" in neutral.detail
    assert "NOT_COMPUTABLE" in neutral.detail
    assert neutral.n_years == 1
    assert neutral.ag_years == (2002,)

    record = result.record
    assert record.value is None
    assert record.reason == "MISSING_INPUT"
    assert "2005" in record.detail
    assert "NOT_COMPUTABLE" in record.detail
    assert record.n_years == 5
    assert record.ag_years == (2001, 2002, 2003, 2004, 2006)

    # PROPOSED expected means of the kinds whose years all have values.
    assert result.by_kind[EL_NINO].value == pytest.approx((1.0 + 3.0) / 2)
    assert result.by_kind[LA_NINA].value == pytest.approx((4.0 + 8.0) / 2)


def test_a_group_whose_years_all_miss_counts_zero_years_and_has_no_value():
    series = dict(SIX_VALUES)
    series[2002] = absent("NOT_COMPUTABLE")
    series[2005] = absent("SOURCE_UNAVAILABLE")
    neutral = mean_by_kind(INDICATOR, UNIT, series, SIX_KINDS).by_kind[NEUTRAL]
    assert neutral.value is None
    assert neutral.reason == "MISSING_INPUT"
    assert neutral.n_years == 0
    assert "2002" in neutral.detail and "2005" in neutral.detail
    assert "SOURCE_UNAVAILABLE" in neutral.detail


# --- 4. a year whose kind is missing ------------------------------------------


def test_unclassified_year_enters_the_record_only():
    kinds = dict(SIX_KINDS)
    kinds[2007] = no_kind()
    series = dict(SIX_VALUES)
    series[2007] = present(10.0)
    series[2008] = present(20.0)  # absent from kinds
    result = mean_by_kind(INDICATOR, UNIT, series, kinds)
    assert result.unclassified_years == (2007, 2008)
    for name in KINDS_OF_YEAR:
        assert 2007 not in result.by_kind[name].ag_years
        assert 2008 not in result.by_kind[name].ag_years
        assert result.by_kind[name].n_years == 2
    # PROPOSED expected means: kinds unchanged, record with both years.
    assert result.by_kind[EL_NINO].value == pytest.approx((1.0 + 3.0) / 2)
    assert result.record.value == pytest.approx(
        (1.0 + 2.0 + 4.0 + 3.0 + 6.0 + 8.0 + 10.0 + 20.0) / 8
    )
    assert result.record.n_years == 8
    assert 2007 in result.record.ag_years and 2008 in result.record.ag_years


def test_year_in_kinds_absent_from_series_is_ignored():
    kinds = dict(SIX_KINDS)
    kinds[1999] = kind(EL_NINO)
    result = mean_by_kind(INDICATOR, UNIT, SIX_VALUES, kinds)
    assert result.by_kind[EL_NINO].ag_years == (2001, 2004)
    assert 1999 not in result.record.ag_years


# --- 5. series_from_results ---------------------------------------------------


def annual(ag_year, value):
    if value is None:
        return AnnualSoilLoss(
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit=UNIT_SOIL_LOSS_ANNUAL,
            missing={"reason": "NOT_COMPUTABLE", "detail": "invented test case"},
            ag_year=ag_year,
        )
    return AnnualSoilLoss(
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        range_missing={"reason": "NOT_AVAILABLE"},
        provenance="DERIVED",
        assumption=True,
        ag_year=ag_year,
    )


def water(time_basis, ag_year, value=0.5):
    return WaterDeficitExposure(
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit=UNIT_WATER_DEFICIT_EXPOSURE,
        range_missing={"reason": "NOT_AVAILABLE"},
        provenance="SIMULATED",
        assumption=True,
        time_basis=time_basis,
        ag_year=ag_year,
    )


def test_series_from_annual_soil_loss():
    series = series_from_results([annual(2001, 1.5), annual(2002, None)])
    assert series == {
        2001: YearValue(value=1.5, reason=None, detail=None, assumption=True),
        2002: YearValue(
            value=None, reason="NOT_COMPUTABLE", detail="invented test case"
        ),
    }


def test_series_from_ag_year_water():
    series = series_from_results([water("ag_year", 2001)])
    assert series == {
        2001: YearValue(value=0.5, reason=None, detail=None, assumption=True)
    }


def test_series_from_results_copies_the_source():
    item = AnnualSoilLoss(
        indicator="soil_loss",
        direction="lower_is_better",
        value=1.5,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        range_missing={"reason": "NOT_AVAILABLE"},
        provenance="DERIVED",
        source="invented test source",
        ag_year=2001,
    )
    assert series_from_results([item]) == {
        2001: YearValue(
            value=1.5,
            reason=None,
            detail=None,
            source="invented test source",
            assumption=False,
        )
    }


# --- fix round 1 ---------------------------------------------------------------


def test_kind_without_classified_year_names_the_unclassified_years():
    kinds = {year: k for year, k in SIX_KINDS.items() if k.kind != LA_NINA}
    kinds[2003] = no_kind()
    series = {year: SIX_VALUES[year] for year in (*kinds, 2006)}
    result = mean_by_kind(INDICATOR, UNIT, series, kinds)
    la_nina = result.by_kind[LA_NINA]
    assert la_nina.value is None
    assert la_nina.reason == "NO_COVERAGE"
    assert la_nina.n_years == 0
    assert la_nina.detail == (
        "no agricultural year of the record is classified la_nina; "
        "agricultural year(s) 2003, 2006 have no kind of year"
    )
    assert result.unclassified_years == (2003, 2006)


def test_keys_of_kinds_must_be_int_years():
    for key in (True, "2001", 2001.0):
        with pytest.raises(ValueError):
            mean_by_kind(INDICATOR, UNIT, SIX_VALUES, {key: kind(EL_NINO)})


def test_missing_input_detail_keeps_each_years_own_detail():
    series = dict(SIX_VALUES)
    series[2003] = absent("MISSING_INPUT", "precipitation of June missing")
    series[2006] = absent("NOT_COMPUTABLE")
    la_nina = mean_by_kind(INDICATOR, UNIT, series, SIX_KINDS).by_kind[LA_NINA]
    assert "2003 (MISSING_INPUT: precipitation of June missing)" in la_nina.detail
    assert "2006 (NOT_COMPUTABLE)" in la_nina.detail


def test_present_year_value_carries_no_detail_and_missing_no_provenance():
    with pytest.raises(ValueError):
        YearValue(value=1.0, reason=None, detail="a detail")
    with pytest.raises(ValueError):
        YearValue(value=None, reason="NOT_COMPUTABLE", detail=None, source="s")
    with pytest.raises(ValueError):
        YearValue(value=None, reason="NOT_COMPUTABLE", detail=None, assumption=True)


def test_kind_mean_carries_sources_and_assumption():
    series = {
        2001: YearValue(1.0, None, None, source="invented source b"),
        2002: YearValue(2.0, None, None, source="invented source a"),
        2004: YearValue(3.0, None, None, source="invented source b"),
        2005: YearValue(6.0, None, None, assumption=True),
    }
    result = mean_by_kind(INDICATOR, UNIT, series, SIX_KINDS)
    assert result.by_kind[EL_NINO].sources == ("invented source b",)
    assert result.by_kind[EL_NINO].assumption is False
    assert result.by_kind[NEUTRAL].sources == ("invented source a",)
    assert result.by_kind[NEUTRAL].assumption is True
    assert result.record.sources == ("invented source a", "invented source b")
    assert result.record.assumption is True
    assert result.by_kind[LA_NINA].sources == ()
    assert not hasattr(result.record, "range")


def a_mean(**changes):
    fields = {
        "value": 1.0,
        "unit": UNIT,
        "n_years": 1,
        "ag_years": (2001,),
        "reason": None,
        "detail": None,
    }
    fields.update(changes)
    return KindMean(**fields)


def test_means_by_kind_checks_its_parts():
    good = {name: a_mean() for name in KINDS_OF_YEAR}
    MeansByKind(INDICATOR, UNIT, good, a_mean(), ())
    with pytest.raises(ValueError):
        MeansByKind(INDICATOR, UNIT, {**good, EL_NINO: 1.0}, a_mean(), ())
    with pytest.raises(ValueError):
        MeansByKind(INDICATOR, UNIT, {**good, EL_NINO: a_mean(unit="x")}, a_mean(), ())
    with pytest.raises(ValueError):
        MeansByKind(INDICATOR, UNIT, good, a_mean(unit="x"), ())
    for years in ((2002, 2001), (2001, 2001), (True,), [2001]):
        with pytest.raises(ValueError):
            MeansByKind(INDICATOR, UNIT, good, a_mean(), years)


def test_result_supports_asdict_and_deepcopy():
    result = mean_by_kind(INDICATOR, UNIT, SIX_VALUES, SIX_KINDS)
    as_dict = dataclasses.asdict(result)
    assert set(as_dict["by_kind"]) == set(KINDS_OF_YEAR)
    assert copy.deepcopy(result) == result


def test_kind_mean_checks_its_years():
    for years in ((2001, 2001), (True,), (2002, 2001)):
        with pytest.raises(ValueError):
            a_mean(n_years=len(years), ag_years=years)
    with pytest.raises(ValueError):
        a_mean(n_years=0, ag_years=())


def test_series_from_results_refuses_rotation_basis_and_mixtures():
    with pytest.raises(ValueError):
        series_from_results([water("rotation", None)])
    with pytest.raises(ValueError):
        series_from_results([annual(2001, 1.0), water("ag_year", 2002)])
    with pytest.raises(ValueError):
        series_from_results([annual(2001, 1.0), annual(2001, 2.0)])
    with pytest.raises(ValueError):
        series_from_results([])
    monthly = MonthlySoilLoss(
        indicator="soil_loss",
        direction="lower_is_better",
        value=None,
        unit="t ha-1 month-1",
        missing={"reason": "NOT_COMPUTABLE"},
        year=2001,
        month=7,
        ag_year=2001,
    )
    with pytest.raises(ValueError):
        series_from_results([monthly])


# --- 6. refused inputs --------------------------------------------------------


def test_empty_series_is_refused():
    with pytest.raises(ValueError):
        mean_by_kind(INDICATOR, UNIT, {}, SIX_KINDS)


@pytest.mark.parametrize(
    ("value", "reason"),
    [(1.0, "NOT_COMPUTABLE"), (None, None)],
)
def test_year_value_needs_exactly_one_of_value_and_reason(value, reason):
    with pytest.raises(ValueError):
        YearValue(value=value, reason=reason, detail=None)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1.0"])
def test_year_value_refuses_non_finite_bool_and_text(value):
    with pytest.raises(ValueError):
        YearValue(value=value, reason=None, detail=None)


def test_year_value_refuses_an_unknown_reason():
    with pytest.raises(ValueError):
        YearValue(value=None, reason="ZERO", detail=None)


def test_kind_mean_needs_exactly_one_of_value_and_reason():
    with pytest.raises(ValueError):
        KindMean(
            value=1.0,
            unit=UNIT,
            n_years=1,
            ag_years=(2001,),
            reason="NO_COVERAGE",
            detail=None,
        )
    with pytest.raises(ValueError):
        KindMean(
            value=None, unit=UNIT, n_years=0, ag_years=(), reason=None, detail=None
        )


def test_mean_by_kind_refuses_wrong_entries():
    with pytest.raises(ValueError):
        mean_by_kind(INDICATOR, UNIT, {2001: 1.0}, SIX_KINDS)
    with pytest.raises(ValueError):
        mean_by_kind(INDICATOR, UNIT, {True: present(1.0)}, SIX_KINDS)
    with pytest.raises(ValueError):
        mean_by_kind(INDICATOR, UNIT, SIX_VALUES, {2001: EL_NINO})
    with pytest.raises(ValueError):
        mean_by_kind("", UNIT, SIX_VALUES, SIX_KINDS)
    with pytest.raises(ValueError):
        mean_by_kind(INDICATOR, " ", SIX_VALUES, SIX_KINDS)


# --- 7. no mutation, frozen results -------------------------------------------


def test_inputs_are_not_mutated_and_results_are_frozen():
    series = dict(SIX_VALUES)
    series[2005] = absent("NOT_COMPUTABLE", "invented test case")
    kinds = dict(SIX_KINDS)
    kinds[2007] = no_kind()
    series[2007] = present(10.0)
    series_before = copy.deepcopy(series)
    kinds_before = copy.deepcopy(kinds)

    result = mean_by_kind(INDICATOR, UNIT, series, kinds)

    assert series == series_before
    assert kinds == kinds_before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.unit = "other"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.record.value = 0.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        present(1.0).value = 2.0


def test_series_from_results_does_not_mutate_its_items():
    items = [annual(2001, 1.5), annual(2002, None)]
    before = [item.model_dump(mode="json") for item in items]
    series_from_results(items)
    assert [item.model_dump(mode="json") for item in items] == before
