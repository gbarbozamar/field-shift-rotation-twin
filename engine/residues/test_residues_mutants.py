"""Mutant-killing tests for ``engine/residues/ledger.py`` and ``_parameters.py``.

Covers boundary conditions, D194 origin split, D221 monthly inputs, D188(2)
lead-in guards, and missing-input propagation paths not reached by
``test_ledger.py`` or ``test_ledger_lead_in_day.py``. All inputs are PLACEHOLDER.
"""

from __future__ import annotations

import datetime as dt

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import CARBON_FIELDS, MASS_FIELDS, NotGiven
from contracts.rotation_definition import RotationDefinition
from engine.calendar.repeat import RepeatedRotation
from engine.residues import build_residue_ledger
from engine.residues._parameters import KG_PER_TONNE
from engine.residues.ledger import PARTS
from engine.residues.test_ledger import (
    CROP_A,
    CROP_B,
    GROUP_PARTS,
    MARK,
    START_MONTH,
    YEARS,
    calendar_data,
    catalogue,
    climate_data,
    date_value,
    entries,
    month_of,
    monthly,
    record,
    rotation_data,
    run,
    series,
    unmark,
)

# --- 1. Boundary mutants (_whole_years, _ag_year, _record_period, bounds) ---


def test_single_whole_agricultural_year_is_covered():
    """Exactly one whole year kills ``last < first`` -> ``last <= first``."""
    ledger = run(climate=climate_data(dt.date(2001, 7, 1), dt.date(2002, 6, 30)))
    assert (ledger.first_ag_year, ledger.last_ag_year) == (2001, 2001)
    assert ledger.years_missing is None
    assert len(ledger.annual_carbon_inputs) == 6
    assert len(ledger.monthly_carbon_inputs) == 4
    for found in ledger.monthly_carbon_inputs:
        assert len(found.months) == 12


def test_one_day_short_of_whole_year_is_excluded():
    """Ending 1 day before ag-year end kills ``+ _ONE_DAY`` -> ``+ 2 days``."""
    short = run(climate=climate_data(dt.date(2001, 7, 1), dt.date(2002, 6, 29)))
    assert (short.first_ag_year, short.last_ag_year) == (None, None)
    assert short.years_missing is not None
    assert short.years_missing.reason == "NO_COVERAGE"

    partial_second = run(
        climate=climate_data(dt.date(2001, 7, 1), dt.date(2003, 6, 29))
    )
    assert (partial_second.first_ag_year, partial_second.last_ag_year) == (2001, 2001)


def test_start_one_day_after_or_before_ag_year_start():
    """Starting July 2 vs June 30 kills ``day=1`` -> ``day=2`` in ``_whole_years``."""
    after = run(climate=climate_data(dt.date(2001, 7, 2), dt.date(2004, 6, 30)))
    assert (after.first_ag_year, after.last_ag_year) == (2002, 2003)

    before = run(climate=climate_data(dt.date(2001, 6, 30), dt.date(2003, 6, 30)))
    assert (before.first_ag_year, before.last_ag_year) == (2001, 2002)


def test_harvest_on_start_month_boundary_assigns_exact_ag_year():
    """Harvest on July 1 vs June 30 kills ``month >= start_month`` -> ``>``."""
    calendar = calendar_data()
    calendar["components"][0]["start"] = date_value("2001-07-01")
    calendar["components"][0]["end"] = date_value("2001-07-01")
    calendar["components"][1]["start"] = date_value("2002-06-01")
    calendar["components"][1]["end"] = date_value("2002-06-30")
    rotation = rotation_data()
    rotation["components"][0]["sowing"] = date_value("2001-07-01")
    rotation["components"][0]["harvest"] = date_value("2001-07-01")
    rotation["components"][1]["sowing"] = date_value("2002-06-01")
    rotation["components"][1]["harvest"] = date_value("2002-06-30")

    ledger = run(rotation=rotation, calendar=calendar)
    for entry in entries(ledger, "c1"):
        assert entry.harvest.date.month == START_MONTH
        assert entry.ag_year == YEARS[0] + entry.cycle
    for entry in entries(ledger, "c2"):
        assert entry.harvest.date.month == START_MONTH - 1
        assert entry.ag_year == YEARS[0] + entry.cycle


def test_multiple_daily_series_use_intersection_and_detect_disjoint():
    """Two daily series kill ``max``/``min`` swaps and ``end < start`` -> ``<=``."""
    wide = climate_data(dt.date(2001, 7, 1), dt.date(2004, 6, 30))
    narrow = climate_data(dt.date(2002, 7, 1), dt.date(2003, 6, 30))
    narrow["daily_series"][0]["quantity"] = "test_quantity_two"
    wide["daily_series"].append(narrow["daily_series"][0])
    ledger = run(climate=wide)
    assert (ledger.first_ag_year, ledger.last_ag_year) == (2002, 2002)

    # Disjoint series -> _record_period returns NO_COVERAGE ("share no day").
    s1 = climate_data(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    s2 = climate_data(dt.date(2002, 7, 1), dt.date(2003, 6, 30))
    s2["daily_series"][0]["quantity"] = "test_quantity_two"
    s1["daily_series"].append(s2["daily_series"][0])
    disjoint = run(climate=s1)
    assert disjoint.years_missing is not None
    assert disjoint.years_missing.reason == "NO_COVERAGE"
    assert "share no day" in disjoint.years_missing.detail

    # Touching on exactly 1 day -> _record_period succeeds, _whole_years gives NO_COVERAGE.
    t1 = climate_data(dt.date(2001, 7, 1), dt.date(2002, 7, 1))
    t2 = climate_data(dt.date(2002, 7, 1), dt.date(2003, 6, 30))
    t2["daily_series"][0]["quantity"] = "test_quantity_two"
    t1["daily_series"].append(t2["daily_series"][0])
    one_day = run(climate=t1)
    assert one_day.years_missing is not None
    assert one_day.years_missing.reason == "NO_COVERAGE"
    assert "whole agricultural year" in one_day.years_missing.detail


def test_parameter_bounds_zero_one_and_near_boundary_rejections():
    """0.0 and 1.0 are valid; -0.001 and 1.001 are rejected (kills <=0, >=1, <-1, >1.5)."""
    params = catalogue(
        **{
            f"rusle2_residue_yield_ratio.{CROP_A}": record(
                "rusle2_residue_yield_ratio", CROP_A, 0.0
            ),
            f"residue_carbon_fraction.{CROP_A}": record(
                "residue_carbon_fraction", CROP_A, 0.0
            ),
            f"residue_removed_fraction.{CROP_A}": record(
                "residue_removed_fraction", CROP_A, 1.0
            ),
            f"root_mass_at_harvest.{CROP_A}": record(
                "root_mass_at_harvest", CROP_A, 0.0
            ),
            f"root_carbon_fraction.{CROP_A}": record(
                "root_carbon_fraction", CROP_A, 1.0
            ),
            f"rhizodeposit_carbon.{CROP_A}": record("rhizodeposit_carbon", CROP_A, 0.0),
            f"residue_carbon_fraction.{CROP_B}": record(
                "residue_carbon_fraction", CROP_B, 1.0
            ),
        }
    )
    ledger = run(parameters=params)
    for entry in entries(ledger, "c1"):
        assert entry.aboveground_mass_produced.value == 0.0
        assert entry.aboveground_mass_exported.value == 0.0
        assert entry.aboveground_carbon_retained.value == 0.0
        assert entry.root_mass.value == 0.0
        assert entry.root_carbon.value == 0.0
        assert entry.rhizodeposit_carbon.value == 0.0
    for entry in entries(ledger, "c2"):
        assert entry.aboveground_carbon_produced.value == pytest.approx(
            entry.aboveground_mass_produced.value
        )

    # Slightly negative (< 0, > -1) and slightly above 1 (> 1, < 1.5) are NOT_COMPUTABLE.
    slightly_neg = run(
        parameters=catalogue(
            **{
                f"rhizodeposit_carbon.{CROP_A}": record(
                    "rhizodeposit_carbon", CROP_A, -0.001
                )
            }
        )
    )
    assert entries(slightly_neg, "c1")[0].rhizodeposit_carbon.missing.reason == (
        "NOT_COMPUTABLE"
    )
    slightly_over = run(
        parameters=catalogue(
            **{
                f"residue_removed_fraction.{CROP_A}": record(
                    "residue_removed_fraction", CROP_A, 1.001
                )
            }
        )
    )
    exported_missing = entries(slightly_over, "c1")[0].aboveground_mass_exported.missing
    assert exported_missing.reason == "MISSING_INPUT"
    assert "NOT_COMPUTABLE" in exported_missing.detail
    assert "a fraction from zero to one" in exported_missing.detail


def test_duplicate_parameter_record_and_empty_scope_fallback_are_missing_input():
    """Duplicate id+scope and missing crop scope (with empty scope present) return MISSING_INPUT."""
    dup = catalogue()
    dup["records/duplicate_yield.json"] = unmark(
        record("rusle2_crop_yield", CROP_A, 50.0)
    )
    ledger_dup = run(parameters=dup)
    gone_dup = entries(ledger_dup, "c1")[0].aboveground_mass_produced
    assert gone_dup.value is None
    assert gone_dup.missing.reason == "MISSING_INPUT"
    assert "two records share this id and scope" in gone_dup.missing.detail

    empty_scope = catalogue(**{f"rusle2_crop_yield.{CROP_A}": None})
    rec = unmark(record("rusle2_crop_yield", CROP_A, 50.0))
    rec["scope"] = {}
    empty_scope["records/empty_scope_yield.json"] = rec
    ledger_scope = run(parameters=empty_scope)
    gone_scope = entries(ledger_scope, "c1")[0].aboveground_mass_produced
    assert gone_scope.value is None
    assert gone_scope.missing.reason == "MISSING_INPUT"
    assert "no record in parameters" in gone_scope.missing.detail


def test_missing_start_month_and_invalid_arguments():
    """Missing ag_year_start.month gives empty ledger; case_id and parameters type checked."""
    cal_no_month = calendar_data()
    cal_no_month["ag_year_start"] = {
        "month": None,
        "provisional": None,
        "missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: no month"},
    }
    ledger = run(calendar=cal_no_month)
    assert (ledger.first_ag_year, ledger.last_ag_year) == (None, None)
    assert ledger.years_missing is not None
    assert ledger.years_missing.reason == "MISSING_INPUT"
    assert ledger.components == []
    assert ledger.annual_carbon_inputs == []
    assert ledger.monthly_carbon_inputs == []

    rot = RotationDefinition.model_validate(rotation_data())
    cal = RotationCalendar.model_validate(calendar_data())
    cli = SiteClimate.model_validate(climate_data())

    bad_case = climate_data()
    bad_case["case_id"] = "other-case"
    with pytest.raises(ValueError, match="case_id"):
        build_residue_ledger(
            rot, cal, SiteClimate.model_validate(bad_case), parameters={}
        )

    with pytest.raises(TypeError, match="parameters"):
        build_residue_ledger(rot, cal, cli, parameters={1: {}})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="parameters"):
        build_residue_ledger(rot, cal, cli, parameters={"k": []})  # type: ignore[dict-item]


# --- 2. D194 origin split & D221 monthly inputs mutants ---


def test_infeasible_calendar_makes_all_monthly_series_not_computable():
    """Kills deletion of ``if infeasible is not None:`` in ``_month_value``."""
    infeasible = calendar_data(
        feasibility={
            "feasible": False,
            "violations": [{"rule": "test_rule", "component_ids": ["c1"]}],
        }
    )
    ledger = run(calendar=infeasible)
    assert ledger.monthly_carbon_inputs
    for found in ledger.monthly_carbon_inputs:
        assert found.provenance is None
        for item in found.months:
            assert item.value is None
            assert item.missing is not None
            assert item.missing.reason == "NOT_COMPUTABLE"
            assert "test_rule" in item.missing.detail


def test_monthly_series_with_start_month_january_and_december():
    """Start month 1 and 12 exercise ``_months`` year/month rollover."""
    for start_m, first_day, end_day, last_m in (
        (1, dt.date(2001, 1, 1), dt.date(2002, 12, 31), 12),
        (12, dt.date(2001, 12, 1), dt.date(2003, 11, 30), 11),
    ):
        start_obj = {
            "month": start_m,
            "provisional": True,
            "provenance": "DECLARED",
            "source": f"{MARK}: test",
        }
        cal = calendar_data(
            ag_year_start=start_obj,
            start_date=first_day.isoformat(),
            end_date=(
                dt.date(first_day.year + (1 if start_m == 12 else 0), last_m, 28)
            ).isoformat(),
        )
        if start_m == 1:
            cal["components"][0]["start"] = date_value("2001-01-15")
            cal["components"][0]["end"] = date_value("2001-06-20")
            cal["components"][1]["start"] = date_value("2001-07-10")
            cal["components"][1]["end"] = date_value("2001-11-30")
        else:
            cal["components"][0]["start"] = date_value("2001-12-10")
            cal["components"][0]["end"] = date_value("2002-05-20")
            cal["components"][1]["start"] = date_value("2002-06-10")
            cal["components"][1]["end"] = date_value("2002-11-20")
        rot = rotation_data()
        rot["ag_year_start"] = start_obj
        for r_comp, c_comp in zip(rot["components"], cal["components"], strict=True):
            r_comp["sowing"], r_comp["harvest"] = c_comp["start"], c_comp["end"]

        ledger = run(
            rotation=rot,
            calendar=cal,
            climate=climate_data(first_day, end_day),
        )
        assert (ledger.first_ag_year, ledger.last_ag_year) == (2001, 2002)
        for found in ledger.monthly_carbon_inputs:
            assert (found.start.year, found.start.month) == (2001, start_m)
            expected_end_year = 2002 if start_m == 1 else 2003
            assert (found.end.year, found.end.month) == (expected_end_year, last_m)
            assert len(found.months) == 24


def test_same_crop_mixed_purposes_stay_apart_in_annual_and_merge_in_monthly():
    """D194/D221: monthly origin names crop only; annual separates (crop, purpose)."""
    cal = calendar_data()
    rot = rotation_data(purpose_b="cover")
    cal["components"][1]["crop_id"] = CROP_A
    rot["components"][1]["crop_id"] = CROP_A
    ledger = run(rotation=rot, calendar=cal)

    annual_quantities = {s.quantity for s in ledger.annual_carbon_inputs}
    assert f"{CROP_A}_grain_aboveground_carbon_retained" in annual_quantities
    assert f"{CROP_A}_cover_aboveground_carbon_retained" in annual_quantities
    assert all(
        item.value is not None
        for item in series(ledger, f"{CROP_A}_grain_aboveground_carbon_retained").years
    )
    assert all(
        item.missing is not None and item.missing.reason == "MISSING_INPUT"
        for item in series(ledger, f"{CROP_A}_cover_aboveground_carbon_retained").years
    )

    # Monthly merges both purposes under CROP_A_<group>: Dec is finite, May is missing, others 0.
    assert {s.origin for s in ledger.monthly_carbon_inputs} == {
        f"{CROP_A}_aboveground",
        f"{CROP_A}_belowground",
    }
    for group in GROUP_PARTS:
        found = monthly(ledger, f"{CROP_A}_{group}")
        assert month_of(found, 2001, 12).value is not None
        assert month_of(found, 2001, 12).value > 0
        may = month_of(found, 2002, 5)
        assert may.value is None and may.missing.reason == "MISSING_INPUT"
        assert month_of(found, 2001, 8).value == 0.0


def test_same_crop_two_grain_harvests_in_different_months_sum_annually():
    """Two harvests of same crop/purpose in one ag year sum in annual, split in monthly."""
    cal = calendar_data()
    cal["components"][1]["crop_id"] = CROP_A
    rot = rotation_data()
    rot["components"][1]["crop_id"] = CROP_A
    ledger = run(rotation=rot, calendar=cal)

    dec_entry = entries(ledger, "c1")[0]
    may_entry = entries(ledger, "c2")[0]
    for group, parts in GROUP_PARTS.items():
        found = monthly(ledger, f"{CROP_A}_{group}")
        dec_expected = sum(getattr(dec_entry, p).value for p in parts) / KG_PER_TONNE
        may_expected = sum(getattr(may_entry, p).value for p in parts) / KG_PER_TONNE
        assert month_of(found, 2001, 12).value == pytest.approx(dec_expected)
        assert month_of(found, 2002, 5).value == pytest.approx(may_expected)
        assert month_of(found, 2001, 10).value == 0.0
    for part in PARTS:
        ann = series(ledger, f"{CROP_A}_grain_{part}")
        expected_year = (
            getattr(dec_entry, part).value + getattr(may_entry, part).value
        ) / KG_PER_TONNE
        assert ann.years[0].value == pytest.approx(expected_year)


def test_full_aboveground_export_gives_zero_aboveground_only():
    """100% removed residue yields 0.0 aboveground carbon while belowground stays positive."""
    params = catalogue(
        **{
            f"residue_removed_fraction.{CROP_A}": record(
                "residue_removed_fraction", CROP_A, 1.0
            )
        }
    )
    ledger = run(parameters=params)
    for part in PARTS:
        ann = series(ledger, f"{CROP_A}_grain_{part}")
        if part == "aboveground_carbon_retained":
            assert all(item.value == 0.0 for item in ann.years)
        else:
            assert all(item.value > 0.0 for item in ann.years)
    assert all(m.value == 0.0 for m in monthly(ledger, f"{CROP_A}_aboveground").months)
    below = monthly(ledger, f"{CROP_A}_belowground")
    assert month_of(below, 2001, 12).value > 0.0


# --- 3. Undated harvest bounds & D188(2) lead-in mutants ---


def test_undated_harvest_possible_years_and_month_boundaries():
    """2-year cycle kills ``if True:`` and ``<=`` -> ``<`` and dropped ``cycle_last_day``."""
    # Case A: c1 starts in year 2 of a 2-year cycle (2002-09-15 .. 2003-06-30), undated end.
    # Cycle 0 spans 2001-07-01 .. 2003-06-30, climate covers 2001..2004 (4 ag years: 2001..2004).
    cal = calendar_data(start_date="2001-07-01", end_date="2003-06-30")
    cal["components"] = [
        {
            "component_id": "c1",
            "crop_id": CROP_A,
            "start": date_value("2002-09-15"),
            "end": date_value(None),
            "periods": [],
        }
    ]
    rot = rotation_data()
    rot["components"] = [
        {
            "component_id": "c1",
            "position": 1,
            "crop_id": CROP_A,
            "purpose": "grain",
            "sowing": date_value("2002-09-15"),
            "harvest": date_value(None),
            "management": rot["components"][0]["management"],
        }
    ]
    ledger = run(
        rotation=rot,
        calendar=cal,
        climate=climate_data(dt.date(2001, 7, 1), dt.date(2005, 6, 30)),
    )
    ann = series(ledger, f"{CROP_A}_grain_aboveground_carbon_retained")
    by_year = {item.ag_year: item for item in ann.years}
    # Years 2001 and 2003 are before c1's earliest start in cycles 0 and 1 -> must be 0.0!
    assert by_year[2001].value == 0.0
    assert by_year[2002].value is None
    assert by_year[2002].missing.reason == "MISSING_INPUT"
    assert by_year[2003].value == 0.0
    assert by_year[2004].value is None

    above = monthly(ledger, f"{CROP_A}_aboveground")
    # Months before 2002-09 are 0.0; boundary months 2002-09 and 2003-06 are missing;
    # 2003-07 (before cycle 1's 2004-09 start) is 0.0 again.
    assert month_of(above, 2002, 8).value == 0.0
    assert month_of(above, 2002, 9).value is None
    assert month_of(above, 2003, 6).value is None
    assert month_of(above, 2003, 7).value == 0.0

    # Case B: c1 starts in year 1 (2001-09-15) of a 2-year cycle (cycle_last_day 2003-06-30),
    # undated end -> BOTH ag_years 2001 and 2002 must be missing (kills dropping cycle_last_day).
    cal["components"][0]["start"] = date_value("2001-09-15")
    rot["components"][0]["sowing"] = date_value("2001-09-15")
    ledger_span = run(
        rotation=rot,
        calendar=cal,
        climate=climate_data(dt.date(2001, 7, 1), dt.date(2003, 6, 30)),
    )
    ann_span = series(ledger_span, f"{CROP_A}_grain_aboveground_carbon_retained")
    assert all(
        item.value is None and item.missing.reason == "MISSING_INPUT"
        for item in ann_span.years
    )

    # Case C: undated start AND undated end falls back to calendar_start.
    cal_no_start = calendar_data()
    cal_no_start["components"][0]["start"] = date_value(None)
    cal_no_start["components"][0]["end"] = date_value(None)
    ledger_no_start = run(calendar=cal_no_start)
    for item in series(ledger_no_start, f"{CROP_A}_grain_root_carbon").years:
        assert item.value is None and item.missing.reason == "MISSING_INPUT"


def test_annual_series_lead_in_guard_on_first_and_second_day(monkeypatch):
    """Kills deleting ``if first_day < described_from:`` or ``<`` -> ``<=`` in ``_year_value``."""
    # On the 2nd day of the first ag year, year 2001 is missing in BOTH annual and monthly.
    second_day = dt.date(2001, 7, 2)
    monkeypatch.setattr(
        RepeatedRotation, "described_from", property(lambda self: second_day)
    )
    ledger_2nd = run()
    for found in ledger_2nd.annual_carbon_inputs:
        y0, y1, y2 = found.years
        assert y0.value is None and y0.missing.reason == "MISSING_INPUT"
        assert f"before {second_day.isoformat()}" in y0.missing.detail
        assert y1.value is not None and y2.value is not None
    for found in ledger_2nd.monthly_carbon_inputs:
        assert month_of(found, 2001, 7).value is None
        assert month_of(found, 2001, 8).value is not None

    # On the 1st day of the first ag year, year 2001 is computed in BOTH annual and monthly.
    first_day = dt.date(2001, 7, 1)
    monkeypatch.setattr(
        RepeatedRotation, "described_from", property(lambda self: first_day)
    )
    ledger_1st = run()
    for found in ledger_1st.annual_carbon_inputs:
        assert all(y.value is not None for y in found.years)
    for found in ledger_1st.monthly_carbon_inputs:
        assert all(m.value is not None for m in found.months)


def test_lead_in_entry_feeds_monthly_series_and_closes_with_annual():
    """D141 lead-in cycle -1 entries appear in monthly_carbon_inputs and sum to annual."""
    early = calendar_data(start_date="2001-05-25", end_date="2002-05-20")
    early["components"][0]["start"] = date_value("2001-05-25")
    early["components"][1]["end"] = date_value("2002-05-20")
    ledger = run(calendar=early)
    assert min(e.cycle for e in ledger.components) == -1
    for found in ledger.monthly_carbon_inputs:
        assert all(m.value is not None for m in found.months)
        annual_for_origin = [
            s for s in ledger.annual_carbon_inputs if s.origin == found.origin
        ]
        for year in YEARS:
            months = found.months[(year - YEARS[0]) * 12 : (year - YEARS[0] + 1) * 12]
            ann_sum = sum(
                item.value
                for s in annual_for_origin
                for item in s.years
                if item.ag_year == year
            )
            assert sum(m.value for m in months) == pytest.approx(ann_sum, rel=1e-12)


# --- 4. Missing-propagation mutants ---


def test_missing_removed_fraction_propagates_only_to_export_retention_and_aboveground():
    """When residue is 'removed', missing residue_removed_fraction spares produced & belowground."""
    ledger = run(parameters=catalogue(**{f"residue_removed_fraction.{CROP_A}": None}))
    for entry in entries(ledger, "c1"):
        assert entry.aboveground_mass_produced.value is not None
        assert entry.aboveground_carbon_produced.value is not None
        assert entry.root_mass.value is not None
        assert entry.root_carbon.value is not None
        assert entry.rhizodeposit_carbon.value is not None
        for name in (
            "aboveground_mass_exported",
            "aboveground_mass_retained",
            "aboveground_carbon_exported",
            "aboveground_carbon_retained",
        ):
            gone = getattr(entry, name)
            assert gone.value is None and gone.missing.reason == "MISSING_INPUT"
            assert "residue_removed_fraction" in gone.missing.detail

    assert all(
        y.value is None and y.missing.reason == "MISSING_INPUT"
        for y in series(ledger, f"{CROP_A}_grain_aboveground_carbon_retained").years
    )
    assert all(
        y.value is not None for y in series(ledger, f"{CROP_A}_grain_root_carbon").years
    )
    above = monthly(ledger, f"{CROP_A}_aboveground")
    for entry in entries(ledger, "c1"):
        m = month_of(above, entry.harvest.date.year, entry.harvest.date.month)
        assert m.value is None and m.missing.reason == "MISSING_INPUT"
    assert all(
        m.value is not None for m in monthly(ledger, f"{CROP_A}_belowground").months
    )


def test_missing_root_fraction_or_rhizodeposit_propagates_to_belowground_monthly():
    """Missing one belowground part makes belowground monthly missing, never partial sum."""
    for missing_param, missing_part, present_part in (
        ("root_carbon_fraction", "root_carbon", "rhizodeposit_carbon"),
        ("rhizodeposit_carbon", "rhizodeposit_carbon", "root_carbon"),
    ):
        ledger = run(parameters=catalogue(**{f"{missing_param}.{CROP_A}": None}))
        assert all(
            y.value is None and y.missing.reason == "MISSING_INPUT"
            for y in series(ledger, f"{CROP_A}_grain_{missing_part}").years
        )
        assert all(
            y.value is not None
            for y in series(ledger, f"{CROP_A}_grain_{present_part}").years
        )
        below = monthly(ledger, f"{CROP_A}_belowground")
        for entry in entries(ledger, "c1"):
            m = month_of(below, entry.harvest.date.year, entry.harvest.date.month)
            assert m.value is None and m.missing.reason == "MISSING_INPUT"
            assert missing_part in m.missing.detail
        assert all(
            m.value is not None for m in monthly(ledger, f"{CROP_A}_aboveground").months
        )


def test_missing_residue_management_propagates_to_carbon_and_series():
    """Missing management.residue propagates to carbon fields, annual, and monthly series."""
    gone = {"missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: not given"}}
    ledger = run(rotation=rotation_data(residue_a=gone))
    for entry in entries(ledger, "c1"):
        for name in ("aboveground_carbon_exported", "aboveground_carbon_retained"):
            item = getattr(entry, name)
            assert item.value is None and item.missing.reason == "MISSING_INPUT"
    assert all(
        y.value is None and y.missing.reason == "MISSING_INPUT"
        for y in series(ledger, f"{CROP_A}_grain_aboveground_carbon_retained").years
    )
    above = monthly(ledger, f"{CROP_A}_aboveground")
    for entry in entries(ledger, "c1"):
        m = month_of(above, entry.harvest.date.year, entry.harvest.date.month)
        assert m.value is None and m.missing.reason == "MISSING_INPUT"
    assert all(
        m.value is not None for m in monthly(ledger, f"{CROP_A}_belowground").months
    )


def test_calendar_component_missing_from_rotation_blocks_all_series():
    """Kills deleting ``blockers`` in ``_series`` and ``_monthly_series``."""
    rot = rotation_data()
    rot["components"] = [rot["components"][0]]  # drop c2 from rotation_definition
    ledger = run(rotation=rot)

    c2_entries = entries(ledger, "c2")
    assert c2_entries
    for entry in c2_entries:
        assert isinstance(entry.purpose, NotGiven)
        assert isinstance(entry.residue_management, NotGiven)
        for name in MASS_FIELDS + CARBON_FIELDS:
            item = getattr(entry, name)
            assert item.value is None and item.missing.reason == "MISSING_INPUT"
            assert "no component in the rotation definition" in item.missing.detail

    # Blocker propagates to every year of annual and every month of monthly series.
    assert ledger.annual_carbon_inputs
    for ann in ledger.annual_carbon_inputs:
        assert ann.provenance is None
        for y in ann.years:
            assert y.value is None and y.missing.reason == "MISSING_INPUT"
            assert "component 'c2'" in y.missing.detail
    assert ledger.monthly_carbon_inputs
    for mon in ledger.monthly_carbon_inputs:
        assert mon.provenance is None
        for m in mon.months:
            assert m.value is None and m.missing.reason == "MISSING_INPUT"
            assert "component 'c2'" in m.missing.detail
