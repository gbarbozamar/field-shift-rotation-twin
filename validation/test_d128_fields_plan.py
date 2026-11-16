"""Structural and physical invariant tests for the D128 two-fields test plan.

No invented numeric output magnitudes are asserted here; every check tests
monotonicity, invariance, completeness/missingness contracts, and clean
evaluation of [D0] and [W0] across the two PLACEHOLDER demonstration fields.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from contracts.results.models import Missing
from params.catalogue import check_catalogue
from validation.d128_fields_plan import (
    BOUNDARY_AG_YEARS,
    CLIMATE_END,
    CLIMATE_START,
    EXPECTED_ROTATION_B_MISSING_PARAMS,
    FIELD_DEMO_GENTLE,
    FIELD_DEMO_STEEP,
    FULL_AG_YEARS,
    TwoFieldsPlanResult,
    build_demo_fields,
    build_placeholder_climate,
    run_shipped_d128_fields_plan,
)

ROTATION_A_ID = "soybean-winter-fallow"
ROTATION_B_ID = "wheat-soybean-maize"
EXPECTED_SCENARIOS = frozenset({"phase_1+phase_1", "phase_1+phase_2"})


@pytest.fixture(scope="module")
def plan() -> TwoFieldsPlanResult:
    return run_shipped_d128_fields_plan()


def test_shipped_inputs_and_placeholder_fields(plan: TwoFieldsPlanResult) -> None:
    assert len(plan.parameters) == 205
    assert check_catalogue(plan.parameters) == []

    gentle = plan.gentle.soil_slope
    steep = plan.steep.soil_slope
    assert gentle.field_id == FIELD_DEMO_GENTLE
    assert steep.field_id == FIELD_DEMO_STEEP
    assert gentle.example_data is True
    assert steep.example_data is True
    assert gentle.case_id == steep.case_id

    for field in (gentle, steep):
        assert "PLACEHOLDER" in (field.slope_length.source or "")
        assert "PLACEHOLDER" in (field.slope_steepness.source or "")
        assert field.slope_length.range_missing is not None
        assert "PLACEHOLDER" in field.slope_length.range_missing.detail
        assert field.slope_steepness.range_missing is not None
        assert "PLACEHOLDER" in field.slope_steepness.range_missing.detail
        assert len(field.soil_properties) >= 1
        for prop in field.soil_properties:
            assert "PLACEHOLDER" in (prop.source or "")

    assert steep.slope_length.value is not None and gentle.slope_length.value is not None
    assert steep.slope_steepness.value is not None and gentle.slope_steepness.value is not None
    assert steep.slope_length.value > gentle.slope_length.value
    assert steep.slope_steepness.value > gentle.slope_steepness.value

    gentle_props = [
        (p.quantity, p.value, p.unit) for p in gentle.soil_properties
    ]
    steep_props = [
        (p.quantity, p.value, p.unit) for p in steep.soil_properties
    ]
    assert gentle_props == steep_props

    for field_plan in (plan.gentle, plan.steep):
        assert field_plan.climate.example_data is True
        for series in field_plan.climate.daily_series:
            assert "PLACEHOLDER" in (series.source or "")

    assert [r.rotation_id for r in plan.rotations] == [ROTATION_A_ID, ROTATION_B_ID]
    assert len(plan.gentle.phases_by_rotation[ROTATION_A_ID]) == 1
    assert len(plan.gentle.phases_by_rotation[ROTATION_B_ID]) == 2
    assert len(plan.steep.phases_by_rotation[ROTATION_A_ID]) == 1
    assert len(plan.steep.phases_by_rotation[ROTATION_B_ID]) == 2


def test_et0_complete_and_field_invariant(plan: TwoFieldsPlanResult) -> None:
    expected_days = (CLIMATE_END - CLIMATE_START).days + 1
    for field_plan in (plan.gentle, plan.steep):
        assert len(field_plan.et0) == expected_days
        for offset in range(expected_days):
            day = CLIMATE_START + dt.timedelta(days=offset)
            val = field_plan.et0[day]
            assert not isinstance(val, Missing)
            assert isinstance(val, float)
            assert math.isfinite(val) and val >= 0.0

    assert dict(plan.gentle.et0) == dict(plan.steep.et0)


def test_ep1_steep_strictly_exceeds_gentle_across_full_years(
    plan: TwoFieldsPlanResult,
) -> None:
    for rotation_id in (ROTATION_A_ID, ROTATION_B_ID):
        gentle_phases = plan.gentle.phases_by_rotation[rotation_id]
        steep_phases = plan.steep.phases_by_rotation[rotation_id]
        for g_phase, s_phase in zip(gentle_phases, steep_phases, strict=True):
            g_annual = {item.ag_year: item for item in g_phase.soil_loss.annual}
            s_annual = {item.ag_year: item for item in s_phase.soil_loss.annual}
            assert set(g_annual) == set(s_annual)

            for boundary_yr in BOUNDARY_AG_YEARS:
                assert g_annual[boundary_yr].value is None
                assert g_annual[boundary_yr].missing is not None
                assert g_annual[boundary_yr].missing.reason == "NO_COVERAGE"
                assert s_annual[boundary_yr].value is None
                assert s_annual[boundary_yr].missing is not None
                assert s_annual[boundary_yr].missing.reason == "NO_COVERAGE"

            g_months_by_year: dict[int, list[float]] = {}
            s_months_by_year: dict[int, list[float]] = {}
            for m in g_phase.soil_loss.monthly:
                if m.ag_year in FULL_AG_YEARS:
                    assert m.missing is None and m.value is not None
                    g_months_by_year.setdefault(m.ag_year, []).append(m.value)
            for m in s_phase.soil_loss.monthly:
                if m.ag_year in FULL_AG_YEARS:
                    assert m.missing is None and m.value is not None
                    s_months_by_year.setdefault(m.ag_year, []).append(m.value)

            for ag_year in FULL_AG_YEARS:
                g_val = g_annual[ag_year].value
                s_val = s_annual[ag_year].value
                assert g_annual[ag_year].missing is None and g_val is not None
                assert s_annual[ag_year].missing is None and s_val is not None
                assert math.isfinite(g_val) and g_val > 0.0
                assert math.isfinite(s_val) and s_val > g_val

                g_months = g_months_by_year[ag_year]
                s_months = s_months_by_year[ag_year]
                assert len(g_months) == 12
                assert len(s_months) == 12
                assert math.isclose(sum(g_months), g_val, rel_tol=1e-9, abs_tol=1e-9)
                assert math.isclose(sum(s_months), s_val, rel_tol=1e-9, abs_tol=1e-9)
                for gm, sm in zip(g_months, s_months, strict=True):
                    if gm > 0.0:
                        assert sm > gm
                    else:
                        assert sm >= gm


def test_ep3_and_ep4_invariant_between_gentle_and_steep(
    plan: TwoFieldsPlanResult,
) -> None:
    for rotation_id in (ROTATION_A_ID, ROTATION_B_ID):
        gentle_phases = plan.gentle.phases_by_rotation[rotation_id]
        steep_phases = plan.steep.phases_by_rotation[rotation_id]
        for g_phase, s_phase in zip(gentle_phases, steep_phases, strict=True):
            assert len(g_phase.water_deficit_exposure) == len(
                s_phase.water_deficit_exposure
            )
            for gw, sw in zip(
                g_phase.water_deficit_exposure,
                s_phase.water_deficit_exposure,
                strict=True,
            ):
                assert gw.ag_year == sw.ag_year
                assert gw.time_basis == sw.time_basis
                assert gw.unit == sw.unit
                assert gw.missing == sw.missing
                if gw.value is None:
                    assert sw.value is None
                else:
                    assert sw.value is not None
                    assert math.isclose(gw.value, sw.value, rel_tol=1e-12, abs_tol=1e-12)

            assert g_phase.residue_ledger.model_dump(
                exclude={"field_id"}
            ) == s_phase.residue_ledger.model_dump(exclude={"field_id"})


def test_rotation_a_numeric_ep1_ep3_ep4_all_full_years(
    plan: TwoFieldsPlanResult,
) -> None:
    for field_plan in (plan.gentle, plan.steep):
        phase = field_plan.phases_by_rotation[ROTATION_A_ID][0]
        annual_sl = {item.ag_year: item for item in phase.soil_loss.annual}
        water_by_yr = {item.ag_year: item for item in phase.water_deficit_exposure}
        ledger = phase.residue_ledger
        comps_by_yr: dict[int, list] = {}
        for comp in ledger.components:
            comps_by_yr.setdefault(comp.ag_year, []).append(comp)

        assert ledger.years_missing is None
        assert ledger.first_ag_year == FULL_AG_YEARS[0]
        assert ledger.last_ag_year == FULL_AG_YEARS[-1]
        for series in ledger.annual_carbon_inputs:
            assert [item.ag_year for item in series.years] == list(FULL_AG_YEARS)

        for ag_year in FULL_AG_YEARS:
            sl_item = annual_sl[ag_year]
            assert sl_item.missing is None and sl_item.value is not None
            assert math.isfinite(sl_item.value) and sl_item.value > 0.0

            w_item = water_by_yr[ag_year]
            assert w_item.missing is None and w_item.value is not None
            assert math.isfinite(w_item.value) and 0.0 <= w_item.value <= 1.0

            yr_comps = comps_by_yr[ag_year]
            assert len(yr_comps) >= 1
            for comp in yr_comps:
                prod = comp.aboveground_mass_produced
                exp = comp.aboveground_mass_exported
                ret = comp.aboveground_mass_retained
                assert prod.missing is None and prod.value is not None
                assert exp.missing is None and exp.value is not None
                assert ret.missing is None and ret.value is not None
                assert math.isfinite(prod.value) and prod.value > 0.0
                assert math.isfinite(exp.value) and exp.value >= 0.0
                assert math.isfinite(ret.value) and ret.value >= 0.0
                assert math.isclose(
                    ret.value, prod.value - exp.value, rel_tol=1e-9, abs_tol=1e-9
                )

        for boundary_yr in BOUNDARY_AG_YEARS:
            assert water_by_yr[boundary_yr].value is None
            assert water_by_yr[boundary_yr].missing is not None
            assert water_by_yr[boundary_yr].missing.reason == "NO_COVERAGE"


def test_rotation_b_numeric_ep1_ep3_ep4_all_full_years(
    plan: TwoFieldsPlanResult,
) -> None:
    """Rotation B computes numeric EP1, EP3 (23/23 years), and EP4 on the 205-record catalogue."""
    assert EXPECTED_ROTATION_B_MISSING_PARAMS == frozenset()
    for field_plan in (plan.gentle, plan.steep):
        phases = field_plan.phases_by_rotation[ROTATION_B_ID]
        assert len(phases) == 2
        for phase in phases:
            annual_sl = {item.ag_year: item for item in phase.soil_loss.annual}
            water_by_yr = {item.ag_year: item for item in phase.water_deficit_exposure}
            ledger = phase.residue_ledger
            full_comps = [
                comp for comp in ledger.components if comp.ag_year in FULL_AG_YEARS
            ]

            assert ledger.years_missing is None
            assert ledger.first_ag_year == FULL_AG_YEARS[0]
            assert ledger.last_ag_year == FULL_AG_YEARS[-1]
            assert {comp.crop_id for comp in full_comps} == {
                "wheat",
                "soybean",
                "maize",
            }
            for comp in full_comps:
                prod = comp.aboveground_mass_produced
                exp = comp.aboveground_mass_exported
                ret = comp.aboveground_mass_retained
                assert prod.missing is None and prod.value is not None
                assert exp.missing is None and exp.value is not None
                assert ret.missing is None and ret.value is not None
                assert math.isfinite(prod.value) and prod.value > 0.0
                assert math.isfinite(exp.value) and exp.value >= 0.0
                assert math.isfinite(ret.value) and ret.value >= 0.0
                assert math.isclose(
                    ret.value, prod.value - exp.value, rel_tol=1e-9, abs_tol=1e-9
                )

            for ag_year in FULL_AG_YEARS:
                sl_item = annual_sl[ag_year]
                assert sl_item.missing is None and sl_item.value is not None
                assert math.isfinite(sl_item.value) and sl_item.value > 0.0

                w_item = water_by_yr[ag_year]
                assert w_item.missing is None and w_item.value is not None
                assert math.isfinite(w_item.value) and 0.0 <= w_item.value <= 1.0

            for boundary_yr in BOUNDARY_AG_YEARS:
                assert water_by_yr[boundary_yr].value is None
                assert water_by_yr[boundary_yr].missing is not None
                assert water_by_yr[boundary_yr].missing.reason == "NO_COVERAGE"


def test_d0_and_w0_comparators_evaluate_cleanly_on_both_fields(
    plan: TwoFieldsPlanResult,
) -> None:
    for field_plan in (plan.gentle, plan.steep):
        table = field_plan.results_table
        assert table.field_id == field_plan.field_id
        assert {row.scenario_id for row in table.rows} == EXPECTED_SCENARIOS
        assert {row.ag_year for row in table.rows} == set(FULL_AG_YEARS)
        assert {row.rotation_id for row in table.rows} == {
            ROTATION_A_ID,
            ROTATION_B_ID,
        }

        d0_items = field_plan.decision_comparison
        assert {item.scenario_id for item in d0_items} == EXPECTED_SCENARIOS
        assert {item.indicator for item in d0_items} == {
            "soil_loss",
            "water_deficit_exposure",
        }
        assert len(d0_items) == 4

        w0_items = field_plan.water_comparison
        assert {item.scenario_id for item in w0_items} == EXPECTED_SCENARIOS
        assert len(w0_items) == 2
        for w_item in w0_items:
            assert "whole cycle, not critical period" in w_item.label


def test_pure_builders_are_deterministic() -> None:
    g1, s1 = build_demo_fields()
    g2, s2 = build_demo_fields()
    assert g1.model_dump() == g2.model_dump()
    assert s1.model_dump() == s2.model_dump()

    c1 = build_placeholder_climate(field_id=FIELD_DEMO_GENTLE)
    c2 = build_placeholder_climate(field_id=FIELD_DEMO_GENTLE)
    assert c1.model_dump() == c2.model_dump()
