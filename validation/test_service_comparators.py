"""Acceptance and isolation tests for the service-connected trivial comparators
runner (unit W4-04, ``validation/service_comparators.py``).

EXAMPLE DATA. All calendars, monthly erosivity tables, daily precipitation,
daily ET0, parameters, and results tables here are synthetic PLACEHOLDER data
constructed by hand so every [D0, E0, H0] expectation is verified by arithmetic.

Run from the repository root:
``python -m pytest validation/test_service_comparators.py``.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import (
    AgYearStart,
    Feasibility,
    RotationCalendar,
    RuleViolation,
)
from contracts.results.models import Missing, Range, ResultsTable, ResultsTableRow
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from validation import service_comparators
from validation.service_comparators import (
    ServiceComparatorsReport,
    run_service_comparators,
)

CASE_ID = "placeholder-case-w4-04"
FIELD_ID = "placeholder-field-w4-04"
SOURCE = "PLACEHOLDER_service_comparators_test"
KIND = "PLACEHOLDER_kind"
_CATALOGUE_MARK = "PLACEHOLDER"
_IN_MEMORY_MARK = "UNMARKED_TEST_ONLY"

START_MONTH = 7
FIRST_DAY = dt.date(2020, 7, 1)
LAST_DAY = dt.date(2022, 6, 30)  # agricultural years 2020 and 2021

# Monthly erosivity summing to 100.0; Dec/Jan/Feb/Mar carry 0.83 of total erosivity.
MONTHLY_EROSIVITY: dict[int, float] = {
    1: 30.0,
    2: 30.0,
    3: 20.0,
    4: 5.0,
    5: 2.0,
    6: 1.0,
    7: 1.0,
    8: 1.0,
    9: 2.0,
    10: 3.0,
    11: 2.0,
    12: 3.0,
}


def _catalogue_record(
    *,
    param_id: str,
    scope: dict[str, str],
    value: float,
    unit: str,
) -> dict[str, object]:
    raw = json.dumps(
        {
            "id": param_id,
            "scope": scope,
            "value": value,
            "unit": unit,
            "range": None,
            "range_missing_reason": f"{_CATALOGUE_MARK} test record without range.",
            "citation": {
                "reference": f"{_CATALOGUE_MARK} synthetic test record for {param_id}",
                "locator": f"{_CATALOGUE_MARK} unit test",
            },
            "transcribed_by": f"{_CATALOGUE_MARK} test author",
            "checked_by": f"{_CATALOGUE_MARK} test reviewer",
            "note": f"{_CATALOGUE_MARK} in-memory record for W4-04 tests.",
        }
    ).replace(_CATALOGUE_MARK, _IN_MEMORY_MARK)
    return json.loads(raw)


def _placeholder_parameters(
    *,
    include_stage_lengths: bool = True,
    include_kcb: bool = True,
    crops: tuple[str, ...] = ("crop-a", "crop-b"),
) -> dict[str, dict]:
    records: dict[str, dict] = {}
    stage_values = {
        "fao56_stage_length_initial": 15,
        "fao56_stage_length_development": 15,
        "fao56_stage_length_mid": 15,
        "fao56_stage_length_late": 15,
    }
    kcb_values = {
        "initial": 0.5,
        "mid": 1.0,
        "end": 0.5,
    }
    for crop in crops:
        if include_stage_lengths:
            for param_id, value in stage_values.items():
                records[f"placeholder.{param_id}.{crop}"] = _catalogue_record(
                    param_id=param_id,
                    scope={"crop": crop},
                    value=value,
                    unit="day",
                )
        if include_kcb:
            for stage, value in kcb_values.items():
                records[f"placeholder.kcb.{crop}.{stage}"] = _catalogue_record(
                    param_id="basal_crop_coefficient",
                    scope={"crop": crop, "stage": stage},
                    value=value,
                    unit="dimensionless",
                )
    return records


def _placeholder_calendar(
    rotation_id: str,
    crop_id: str,
    sowing: str,
    harvest: str,
    *,
    start_month: int = START_MONTH,
    case_id: str = CASE_ID,
    field_id: str = FIELD_ID,
) -> RotationCalendar:
    definition = RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            "case_id": case_id,
            "field_id": field_id,
            "rotation_id": rotation_id,
            "label": f"{SOURCE} {rotation_id}",
            "ag_year_start": {
                "month": start_month,
                "provisional": True,
                "provenance": "DECLARED",
                "source": SOURCE,
            },
            "repeats": True,
            "components": [
                {
                    "component_id": "c1",
                    "position": 1,
                    "crop_id": crop_id,
                    "purpose": "grain",
                    "sowing": {
                        "date": sowing,
                        "provenance": "DECLARED",
                        "source": SOURCE,
                    },
                    "harvest": {
                        "date": harvest,
                        "provenance": "DECLARED",
                        "source": SOURCE,
                    },
                    "management": {
                        "residue": "left_on_surface",
                        "grazing": {"missing": {"reason": "NOT_DECLARED"}},
                        "termination": {"missing": {"reason": "NOT_DECLARED"}},
                    },
                }
            ],
        }
    )
    return build_rotation_calendar(definition)


def _daily_series(
    first: dt.date,
    last: dt.date,
    fn,
) -> dict[dt.date, float | Missing]:
    out: dict[dt.date, float | Missing] = {}
    day = first
    while day <= last:
        out[day] = fn(day)
        day += dt.timedelta(days=1)
    return out


def _soil_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int,
    value: float | None,
    *,
    half_width: float = 0.2,
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="soil_loss",
            direction="lower_is_better",
            value=None,
            unit="t ha-1 yr-1",
            missing=Missing(reason="NO_COVERAGE", detail="PLACEHOLDER missing soil"),
        )
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range=Range(low=value - half_width, high=value + half_width, kind=KIND),
        provenance="DERIVED",
        source=SOURCE,
    )


def _water_row(
    rotation_id: str,
    scenario_id: str,
    ag_year: int,
    value: float | None,
    *,
    half_width: float = 0.05,
) -> ResultsTableRow:
    if value is None:
        return ResultsTableRow(
            rotation_id=rotation_id,
            scenario_id=scenario_id,
            time_basis="ag_year",
            ag_year=ag_year,
            indicator="water_deficit_exposure",
            direction="higher_is_better",
            value=None,
            unit="dimensionless",
            missing=Missing(reason="NO_COVERAGE", detail="PLACEHOLDER missing water"),
        )
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=value,
        unit="dimensionless",
        range=Range(low=value - half_width, high=value + half_width, kind=KIND),
        provenance="SIMULATED",
        source=SOURCE,
    )


def _base_calendars(scenario: str = "s1") -> dict[tuple[str, str], RotationCalendar]:
    # Crop A covers Dec 1 .. Jan 29 (60 live days across high-erosivity Dec-Jan).
    # Crop B covers Jul 1 .. Aug 29 (60 live days across low-erosivity Jul-Aug).
    return {
        ("A", scenario): _placeholder_calendar(
            "A", "crop-a", "2020-12-01", "2021-01-29"
        ),
        ("B", scenario): _placeholder_calendar(
            "B", "crop-b", "2020-07-01", "2020-08-29"
        ),
    }


def _base_climate() -> tuple[
    dict[dt.date, float | Missing], dict[dt.date, float | Missing]
]:
    # On Dec-Jan (crop-a live), precip = 4.0 mm/d, et0 = 2.0 mm/d -> higher ratio.
    # On Jul-Aug (crop-b live), precip = 1.0 mm/d, et0 = 2.0 mm/d -> lower ratio.
    precip = _daily_series(
        FIRST_DAY,
        LAST_DAY,
        lambda d: 4.0 if d.month in (12, 1) else 1.0,
    )
    et0 = _daily_series(FIRST_DAY, LAST_DAY, lambda _d: 2.0)
    return precip, et0


def _agreeing_table(scenario: str = "s1") -> ResultsTable:
    # Soil loss: lower is better -> A (2.0, 2.0) ahead of B (8.0, 8.0) -> ("A", "B")
    # Water deficit exposure: higher is better -> A (0.9, 0.9) ahead of B (0.4, 0.4) -> ("A", "B")
    rows = [
        _soil_row("A", scenario, 2020, 2.0),
        _soil_row("A", scenario, 2021, 2.0),
        _soil_row("B", scenario, 2020, 8.0),
        _soil_row("B", scenario, 2021, 8.0),
        _water_row("A", scenario, 2020, 0.9),
        _water_row("A", scenario, 2021, 0.9),
        _water_row("B", scenario, 2020, 0.4),
        _water_row("B", scenario, 2021, 0.4),
    ]
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)


# --- 1. Full [D0, E0, H0] agreement and disagreement -----------------------------


def test_full_d0_e0_h0_agreement_and_immutability():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert isinstance(report, ServiceComparatorsReport)
    assert report.case_id == CASE_ID
    assert report.field_id == FIELD_ID

    with pytest.raises(FrozenInstanceError):
        report.case_id = "mutated"  # type: ignore[misc]

    d0_by_ind = {item.indicator: item for item in report.d0}
    assert d0_by_ind["soil_loss"].outcome == "equal"
    assert d0_by_ind["soil_loss"].trivial.order == ("A", "B")
    assert d0_by_ind["soil_loss"].decision.order == ("A", "B")
    assert d0_by_ind["water_deficit_exposure"].outcome == "equal"
    assert d0_by_ind["water_deficit_exposure"].trivial.order == ("A", "B")
    assert d0_by_ind["water_deficit_exposure"].decision.order == ("A", "B")

    assert not isinstance(report.e0, Missing)
    (e0_item,) = report.e0
    assert e0_item.scenario_id == "s1"
    assert e0_item.trivial.order == ("A", "B")
    assert e0_item.full is not None and e0_item.full.order == ("A", "B")
    assert e0_item.outcome == "equal"
    # Hand-counted E0 bare shares:
    # A has 0 bare days in Dec and 29/31 covered in Jan (Jan 30-31 bare -> 2/31 * 0.30).
    # B has 0 bare days in Jul and 29/31 covered in Aug (Aug 30-31 bare -> 2/31 * 0.01).
    # Bare share A = 1 - 0.03 - (29/31)*0.30 = 1 - 0.03 - 0.280645... = 0.68935...
    # Bare share B = 1 - 0.01 - (29/31)*0.01 = 0.980645...
    e0_means = dict(e0_item.trivial.means)
    assert e0_means["A"] == pytest.approx(1.0 - 0.03 - (29 / 31) * 0.30)
    assert e0_means["B"] == pytest.approx(1.0 - 0.01 - (29 / 31) * 0.01)

    assert not isinstance(report.h0, Missing)
    (h0_item,) = report.h0
    assert h0_item.scenario_id == "s1"
    assert h0_item.trivial.order == ("A", "B")
    assert h0_item.full.order == ("A", "B")
    assert h0_item.outcome == "equal"
    assert all(yr.crop_days == 60 for yr in h0_item.trivial.years)
    # Daily Kcb averages over (15*0.5 + 15*mean(0.5..1.0) + 15*1.0 + 15*mean(1.0..0.5)) / 60:
    # With precip=4.0 vs 1.0 and constant et0=2.0, ratio(A) == 4 * ratio(B) > ratio(B).
    h0_means = dict(h0_item.trivial.means)
    assert h0_means["A"] == pytest.approx(4.0 * h0_means["B"])

    assert not isinstance(report.e0_year_shares, Missing)
    assert len(report.e0_year_shares) == 4
    assert all(ys.missing is None for ys in report.e0_year_shares)
    assert report.e0_missing_by_scenario == ()
    assert report.h0_missing_by_scenario == ()


def test_disagreement_across_d0_e0_and_h0_in_multi_scenario_table():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = {**_base_calendars("s1"), **_base_calendars("s2")}

    # s1 agrees across D0, E0, H0.
    # s2 reverses full soil_loss (B ahead of A -> E0 "different"),
    # reverses full water_deficit_exposure (B ahead of A -> H0 "different"),
    # and crosses zero on water ranges across years (D0 "no order from the full decision").
    rows = list(_agreeing_table("s1").rows) + [
        _soil_row("A", "s2", 2020, 9.0),
        _soil_row("A", "s2", 2021, 9.0),
        _soil_row("B", "s2", 2020, 2.0),
        _soil_row("B", "s2", 2021, 2.0),
        _water_row("A", "s2", 2020, 0.2, half_width=0.05),
        _water_row("A", "s2", 2021, 0.6, half_width=0.05),  # mean 0.4
        _water_row("B", "s2", 2020, 0.7, half_width=0.05),
        _water_row("B", "s2", 2021, 0.3, half_width=0.05),  # mean 0.5 -> B ahead of A
    ]
    table = ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    d0 = {(item.scenario_id, item.indicator): item for item in report.d0}
    assert d0[("s1", "soil_loss")].outcome == "equal"
    assert d0[("s1", "water_deficit_exposure")].outcome == "equal"
    assert d0[("s2", "soil_loss")].outcome == "equal"
    assert (
        d0[("s2", "water_deficit_exposure")].outcome
        == "no order from the full decision"
    )
    assert d0[("s2", "water_deficit_exposure")].trivial.order == ("B", "A")

    assert not isinstance(report.e0, Missing)
    e0 = {item.scenario_id: item for item in report.e0}
    assert e0["s1"].outcome == "equal"
    assert e0["s2"].trivial.order == ("A", "B")
    assert e0["s2"].full.order == ("B", "A")
    assert e0["s2"].outcome == "different"

    assert not isinstance(report.h0, Missing)
    h0 = {item.scenario_id: item for item in report.h0}
    assert h0["s1"].outcome == "equal"
    assert h0["s2"].trivial.order == ("A", "B")
    assert h0["s2"].full.order == ("B", "A")
    assert h0["s2"].outcome == "different"


# --- 2. Missing-input isolation & typed Missing preservation --------------------


def test_empty_calendars_isolates_d0_and_preserves_missing_on_e0_and_h0():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    table = _agreeing_table("s1")

    report = run_service_comparators(table, {}, MONTHLY_EROSIVITY, precip, et0, params)
    assert all(item.outcome == "equal" for item in report.d0)
    assert isinstance(report.e0, Missing)
    assert report.e0.reason == "MISSING_INPUT"
    assert isinstance(report.e0_year_shares, Missing)
    assert isinstance(report.h0, Missing)
    assert report.h0.reason == "MISSING_INPUT"


def test_missing_erosivity_isolates_e0_while_d0_and_h0_succeed():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    # Wholly Missing (InputMissing normalized cleanly to results Missing).
    whole_missing = InputMissing(reason="SOURCE_UNAVAILABLE", detail="PLACEHOLDER no R")
    report_whole = run_service_comparators(
        table, calendars, whole_missing, precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report_whole.d0)
    assert isinstance(report_whole.e0, Missing)
    assert report_whole.e0.reason == "SOURCE_UNAVAILABLE"
    assert report_whole.e0_year_shares == report_whole.e0
    assert not isinstance(report_whole.h0, Missing)
    assert report_whole.h0[0].outcome == "equal"

    # Single month Missing inside monthly_erosivity.
    partial_erosivity: dict[int, float | Missing] = dict(MONTHLY_EROSIVITY)
    partial_erosivity[3] = Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER March missing"
    )
    report_partial = run_service_comparators(
        table, calendars, partial_erosivity, precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report_partial.d0)
    assert not isinstance(report_partial.h0, Missing)
    assert report_partial.h0[0].outcome == "equal"
    assert not isinstance(report_partial.e0, Missing)
    (e0_item,) = report_partial.e0
    assert e0_item.outcome == "no order from the trivial comparator"
    assert e0_item.trivial.order is None
    assert "MISSING_INPUT" in e0_item.trivial.reason
    assert dict(report_partial.e0_missing_by_scenario)["s1"].reason == "MISSING_INPUT"


def test_missing_precipitation_or_et0_isolates_h0_while_d0_and_e0_succeed():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    # 1) Wholly Missing precipitation -> E0 falls back to ET0 window and succeeds.
    report_no_precip = run_service_comparators(
        table,
        calendars,
        MONTHLY_EROSIVITY,
        Missing(reason="SOURCE_UNAVAILABLE", detail="PLACEHOLDER no precip"),
        et0,
        params,
    )
    assert all(item.outcome == "equal" for item in report_no_precip.d0)
    assert not isinstance(report_no_precip.e0, Missing)
    assert report_no_precip.e0[0].outcome == "equal"
    assert isinstance(report_no_precip.h0, Missing)
    assert report_no_precip.h0.reason == "SOURCE_UNAVAILABLE"

    # 2) Empty ET0 -> E0 uses precip window and succeeds, H0 is NO_COVERAGE.
    report_empty_et0 = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, {}, params
    )
    assert all(item.outcome == "equal" for item in report_empty_et0.d0)
    assert not isinstance(report_empty_et0.e0, Missing)
    assert report_empty_et0.e0[0].outcome == "equal"
    assert isinstance(report_empty_et0.h0, Missing)
    assert report_empty_et0.h0.reason == "NO_COVERAGE"

    # 3) Single missing living-crop day in precip (absent key) -> never filled as 0!
    precip_gap = dict(precip)
    del precip_gap[dt.date(2020, 12, 10)]  # living crop day for A in ag_year 2020
    report_gap = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip_gap, et0, params
    )
    assert not isinstance(report_gap.e0, Missing)
    assert report_gap.e0[0].outcome == "equal"
    assert not isinstance(report_gap.h0, Missing)
    (h0_item,) = report_gap.h0
    assert h0_item.outcome == "no order from the trivial comparator"
    by_year = {(yr.rotation_id, yr.ag_year): yr for yr in h0_item.trivial.years}
    assert by_year[("A", 2020)].ratio is None
    assert by_year[("A", 2020)].missing is not None
    assert by_year[("A", 2020)].missing.reason == "NO_COVERAGE"
    assert by_year[("A", 2021)].ratio is not None
    assert by_year[("B", 2020)].ratio is not None
    assert dict(report_gap.h0_missing_by_scenario)["s1"].reason == "NO_COVERAGE"


def test_missing_fallow_day_in_climate_does_not_invalidate_h0():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    # 2020-10-15 is fallow for both A (Dec-Jan) and B (Jul-Aug).
    precip[dt.date(2020, 10, 15)] = Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER fallow rain gap"
    )
    et0[dt.date(2020, 10, 15)] = Missing(
        reason="MISSING_INPUT", detail="PLACEHOLDER fallow et0 gap"
    )
    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert not isinstance(report.h0, Missing)
    assert report.h0[0].outcome == "equal"
    assert report.h0_missing_by_scenario == ()


def test_missing_kcb_isolates_h0_while_e0_and_d0_succeed():
    precip, et0 = _base_climate()
    params_no_kcb = _placeholder_parameters(
        include_stage_lengths=True, include_kcb=False
    )
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params_no_kcb
    )
    assert all(item.outcome == "equal" for item in report.d0)
    assert not isinstance(report.e0, Missing)
    assert report.e0[0].outcome == "equal"
    assert not isinstance(report.h0, Missing)
    (h0_item,) = report.h0
    assert h0_item.outcome == "no order from the trivial comparator"
    assert dict(report.h0_missing_by_scenario)["s1"].reason == "MISSING_INPUT"


def test_missing_stage_lengths_preserves_missing_in_e0_and_h0_while_d0_succeeds():
    precip, et0 = _base_climate()
    params_no_stages = _placeholder_parameters(
        include_stage_lengths=False, include_kcb=True
    )
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params_no_stages
    )
    assert all(item.outcome == "equal" for item in report.d0)
    assert not isinstance(report.e0, Missing)
    assert report.e0[0].outcome == "no order from the trivial comparator"
    assert dict(report.e0_missing_by_scenario)["s1"].reason == "MISSING_INPUT"
    assert not isinstance(report.h0, Missing)
    assert report.h0[0].outcome == "no order from the trivial comparator"
    assert dict(report.h0_missing_by_scenario)["s1"].reason == "MISSING_INPUT"


def test_infeasible_and_missing_start_month_calendars_are_isolated_per_scenario():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()

    cal_s1 = _base_calendars("s1")
    cal_s2_infeasible = {
        "A": _placeholder_calendar(
            "A", "crop-a", "2020-12-01", "2021-01-29"
        ).model_copy(
            update={
                "feasibility": Feasibility(
                    feasible=False,
                    violations=[
                        RuleViolation(
                            rule="overlap",
                            component_ids=["c1"],
                            detail="PLACEHOLDER infeasible",
                        )
                    ],
                )
            }
        ),
        "B": _placeholder_calendar("B", "crop-b", "2020-07-01", "2020-08-29"),
    }
    cal_s3_no_month = {
        "A": _placeholder_calendar(
            "A", "crop-a", "2020-12-01", "2021-01-29"
        ).model_copy(
            update={
                "ag_year_start": AgYearStart(
                    month=None, missing=InputMissing(reason="NOT_DECLARED")
                )
            }
        ),
        "B": _placeholder_calendar("B", "crop-b", "2020-07-01", "2020-08-29"),
    }
    calendars = {
        **cal_s1,
        ("A", "s2"): cal_s2_infeasible["A"],
        ("B", "s2"): cal_s2_infeasible["B"],
        ("A", "s3"): cal_s3_no_month["A"],
        ("B", "s3"): cal_s3_no_month["B"],
    }
    rows = (
        list(_agreeing_table("s1").rows)
        + list(_agreeing_table("s2").rows)
        + list(_agreeing_table("s3").rows)
    )
    table = ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report.d0)

    assert not isinstance(report.e0, Missing)
    e0 = {item.scenario_id: item for item in report.e0}
    assert e0["s1"].outcome == "equal"
    assert e0["s2"].outcome == "no order from the trivial comparator"
    assert e0["s3"].outcome == "no order from the trivial comparator"
    e0_miss = dict(report.e0_missing_by_scenario)
    assert e0_miss["s2"].reason == "NOT_COMPUTABLE"
    assert e0_miss["s3"].reason == "MISSING_INPUT"

    assert not isinstance(report.h0, Missing)
    h0 = {item.scenario_id: item for item in report.h0}
    assert h0["s1"].outcome == "equal"
    assert h0["s2"].outcome == "no order from the trivial comparator"
    assert h0["s3"].outcome == "no order from the trivial comparator"
    h0_miss = dict(report.h0_missing_by_scenario)
    assert h0_miss["s2"].reason == "NOT_COMPUTABLE"
    assert h0_miss["s3"].reason == "MISSING_INPUT"


def test_delegates_to_flags_by_rotation_from_calendars(monkeypatch):
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    recorded = []
    real_fn = service_comparators.flags_by_rotation_from_calendars

    def spy_flags_by_rotation_from_calendars(cals, *, start_date, end_date, parameters):
        recorded.append((dict(cals), start_date, end_date, parameters))
        return real_fn(
            cals, start_date=start_date, end_date=end_date, parameters=parameters
        )

    monkeypatch.setattr(
        service_comparators,
        "flags_by_rotation_from_calendars",
        spy_flags_by_rotation_from_calendars,
    )
    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert len(recorded) == 1
    assert recorded[0][1] == FIRST_DAY
    assert recorded[0][2] == LAST_DAY
    assert not isinstance(report.e0, Missing)
    assert report.e0[0].outcome == "equal"


# --- 3. G1 purity and G5 TypeError/ValueError checks ----------------------------


def test_g1_purity_does_not_mutate_inputs_and_is_deterministic():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")
    erosivity = dict(MONTHLY_EROSIVITY)

    table_before = table.model_copy(deep=True)
    cals_before = {k: v.model_copy(deep=True) for k, v in calendars.items()}
    erosivity_before = copy.deepcopy(erosivity)
    precip_before = copy.deepcopy(precip)
    et0_before = copy.deepcopy(et0)
    params_before = copy.deepcopy(params)

    first = run_service_comparators(table, calendars, erosivity, precip, et0, params)
    second = run_service_comparators(table, calendars, erosivity, precip, et0, params)
    assert first == second
    assert table == table_before
    assert calendars == cals_before
    assert erosivity == erosivity_before
    assert precip == precip_before
    assert et0 == et0_before
    assert params == params_before


def test_g1_module_reads_no_file_clock_or_network_and_holds_no_thresholds():
    tree = ast.parse(Path(service_comparators.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "datetime",
        "math",
        "collections",
        "dataclasses",
        "typing",
        "contracts",
        "engine",
        "validation",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "input", "eval", "exec"}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not attributes & {"today", "now", "utcnow"}
    numbers = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }
    assert numbers <= {0, 1}


def test_g5_type_and_value_errors():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    with pytest.raises(TypeError, match="ResultsTable"):
        run_service_comparators(
            table.model_dump(),
            calendars,
            MONTHLY_EROSIVITY,
            precip,
            et0,
            params,  # type: ignore[arg-type]
        )

    for bad_cals in (
        None,
        [],
        {("A",): calendars[("A", "s1")]},
        {(1, "s1"): calendars[("A", "s1")]},
        {("A", "s1"): "bad"},
    ):
        with pytest.raises(TypeError, match="calendars"):
            run_service_comparators(
                table,
                bad_cals,
                MONTHLY_EROSIVITY,
                precip,
                et0,
                params,  # type: ignore[arg-type]
            )

    with pytest.raises(ValueError, match="non-empty"):
        run_service_comparators(
            table,
            {("", "s1"): calendars[("A", "s1")]},
            MONTHLY_EROSIVITY,
            precip,
            et0,
            params,
        )

    wrong_field_cal = _placeholder_calendar(
        "A", "crop-a", "2020-12-01", "2021-01-29", field_id="other-field"
    )
    with pytest.raises(ValueError, match="case_id/field_id"):
        run_service_comparators(
            table,
            {("A", "s1"): wrong_field_cal},
            MONTHLY_EROSIVITY,
            precip,
            et0,
            params,
        )

    with pytest.raises(ValueError, match="rotation_id"):
        run_service_comparators(
            table,
            {("B", "s1"): calendars[("A", "s1")]},
            MONTHLY_EROSIVITY,
            precip,
            et0,
            params,
        )

    for bad_erosivity in (
        None,
        [],
        {True: 1.0},
        {1: None, **{m: 1.0 for m in range(2, 13)}},
    ):
        with pytest.raises(TypeError, match="monthly_erosivity"):
            run_service_comparators(
                table,
                calendars,
                bad_erosivity,
                precip,
                et0,
                params,  # type: ignore[arg-type]
            )
    with pytest.raises(ValueError, match="monthly_erosivity"):
        run_service_comparators(
            table, calendars, {m: 1.0 for m in range(1, 12)}, precip, et0, params
        )

    for bad_series in (
        None,
        [],
        {dt.datetime(2020, 7, 1): 1.0},
        {"2020-07-01": 1.0},
        {FIRST_DAY: None},
        {FIRST_DAY: True},
    ):
        with pytest.raises(TypeError, match="daily_precipitation"):
            run_service_comparators(
                table,
                calendars,
                MONTHLY_EROSIVITY,
                bad_series,
                et0,
                params,  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="daily_et0"):
            run_service_comparators(
                table,
                calendars,
                MONTHLY_EROSIVITY,
                precip,
                bad_series,
                params,  # type: ignore[arg-type]
            )

    for bad_params in (None, [], {1: {}}, {"k": "not-a-dict"}):
        with pytest.raises(TypeError, match="parameters"):
            run_service_comparators(
                table,
                calendars,
                MONTHLY_EROSIVITY,
                precip,
                et0,
                bad_params,  # type: ignore[arg-type]
            )

    # Mismatched rotations between calendars and table soil_loss raises ValueError per E0.
    with pytest.raises(ValueError, match="rotations"):
        run_service_comparators(
            table,
            {("A", "s1"): calendars[("A", "s1")]},
            MONTHLY_EROSIVITY,
            precip,
            et0,
            params,
        )


def test_non_finite_climate_values_and_conflicting_start_months_preserve_missing():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    table = _agreeing_table("s1")

    # Non-finite precip on living day of A -> NOT_COMPUTABLE in H0, E0/D0 still equal.
    nan_precip = dict(precip)
    nan_precip[dt.date(2020, 12, 10)] = float("nan")
    report_nan = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, nan_precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report_nan.d0)
    assert not isinstance(report_nan.e0, Missing)
    assert report_nan.e0[0].outcome == "equal"
    assert dict(report_nan.h0_missing_by_scenario)["s1"].reason == "NOT_COMPUTABLE"

    # Conflicting start months within one scenario -> typed NOT_COMPUTABLE on E0 and H0, D0 still equal.
    conflicting = {
        ("A", "s1"): _placeholder_calendar(
            "A", "crop-a", "2020-12-01", "2021-01-29", start_month=7
        ),
        ("B", "s1"): _placeholder_calendar(
            "B", "crop-b", "2020-07-01", "2020-08-29", start_month=1
        ),
    }
    report_conflict = run_service_comparators(
        table, conflicting, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report_conflict.d0)
    assert isinstance(report_conflict.e0, Missing)
    assert report_conflict.e0.reason == "NOT_COMPUTABLE"
    assert isinstance(report_conflict.h0, Missing)
    assert report_conflict.h0.reason == "NOT_COMPUTABLE"


def test_scenario_only_in_table_is_isolated_while_present_scenario_evaluates():
    precip, et0 = _base_climate()
    params = _placeholder_parameters()
    calendars = _base_calendars("s1")
    rows = list(_agreeing_table("s1").rows) + list(_agreeing_table("s_table_only").rows)
    table = ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)

    report = run_service_comparators(
        table, calendars, MONTHLY_EROSIVITY, precip, et0, params
    )
    assert all(item.outcome == "equal" for item in report.d0)
    assert not isinstance(report.e0, Missing)
    e0 = {item.scenario_id: item for item in report.e0}
    assert e0["s1"].outcome == "equal"
    assert e0["s_table_only"].outcome == "no order from the trivial comparator"
    assert dict(report.e0_missing_by_scenario)["s_table_only"].reason == "MISSING_INPUT"

    assert not isinstance(report.h0, Missing)
    h0 = {item.scenario_id: item for item in report.h0}
    assert h0["s1"].outcome == "equal"
    assert h0["s_table_only"].outcome == "no order from the trivial comparator"
    assert dict(report.h0_missing_by_scenario)["s_table_only"].reason == "MISSING_INPUT"
