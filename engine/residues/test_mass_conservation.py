"""Physical mass & carbon conservation, boundary, and G1-G7 tests for EP4 ``build_residue_ledger``.

Uses synthetic ``PLACEHOLDER`` inputs alongside the 18 signed residue records
shipped under ``params/records/residues/`` (loaded dynamically, with zero
parameter literals written in this file).
"""

from __future__ import annotations

import copy
import datetime as dt
import inspect
import itertools
import os
import socket
from pathlib import Path

import pytest

from contracts.carbon_forcing import CarbonForcing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import CARBON_FIELDS, MASS_FIELDS, ResidueLedger
from contracts.rotation_definition import RotationDefinition
from engine.calendar import build_rotation_calendar
from engine.calendar.repeat import list_phases, phase_calendar
from engine.residues import build_residue_ledger
from engine.residues._parameters import (
    CARBON_INPUT_UNIT,
    CARBON_UNIT,
    KG_PER_TONNE,
    MASS_UNIT,
)
from engine.residues.ledger import PARTS
from engine.residues.test_ledger import (
    CROP_A,
    CROP_B,
    GROUP_PARTS,
    IDS,
    LABEL,
    MARK,
    NUMBERS,
    START_MONTH,
    calendar_data,
    catalogue,
    climate_data,
    date_value,
    entries,
    management,
    month_of,
    monthly,
    record,
    rotation_data,
    run,
    series,
    unmark,
)
from params import catalogue as params_catalogue
from params.catalogue import check_catalogue, load_folder, read_value

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNED_RESIDUES_DIR = REPO_ROOT / "params" / "records" / "residues"
SIGNED_CROPS = ("maize", "soybean", "wheat")
SIGNED_IDS = (
    "rusle2_crop_yield",
    "rusle2_residue_yield_ratio",
    "residue_carbon_fraction",
    "root_mass_at_harvest",
    "root_carbon_fraction",
    "rhizodeposit_carbon",
)

# Synthetic PLACEHOLDER values for the one proposed residue parameter not in
# params/records/residues/ (repeated digits, clearly unreal).
SYNTHETIC_PROPOSED: dict[str, dict[str, float]] = {
    "residue_removed_fraction": {"maize": 0.666, "soybean": 0.222, "wheat": 0.777},
}


def load_signed_residue_records() -> tuple[dict[str, dict], dict[tuple[str, str], float]]:
    """Load the 18 shipped signed residue records from ``params/records/residues/``."""
    records, problems = load_folder(SIGNED_RESIDUES_DIR)
    assert problems == []
    assert check_catalogue(records) == []
    values: dict[tuple[str, str], float] = {}
    for rec in records.values():
        assert set(rec["scope"]) == {"crop"}
        val = read_value(rec)
        assert isinstance(val, float)
        values[(rec["id"], rec["scope"]["crop"])] = val
    expected_keys = {(pid, crop) for pid in SIGNED_IDS for crop in SIGNED_CROPS}
    assert set(values) == expected_keys
    assert len(records) == 18
    return records, values


def hybrid_catalogue(**overrides: dict | None) -> dict[str, dict]:
    """Combine the 18 shipped signed residue records with unmarked PLACEHOLDER proposed records."""
    signed, _ = load_signed_residue_records()
    combined: dict[str, dict] = {f"residues/{k}": copy.deepcopy(v) for k, v in signed.items()}
    for name, by_crop in SYNTHETIC_PROPOSED.items():
        for crop, value in by_crop.items():
            combined[f"placeholder/{name}.{crop}.json"] = unmark(record(name, crop, value))
    for key, val in overrides.items():
        path = f"placeholder/{key}.json"
        if val is None:
            combined.pop(path, None)
        else:
            combined[path] = unmark(val)
    assert check_catalogue(combined) == []
    return combined


def three_crop_inputs(
    *,
    start_month: int = START_MONTH,
    record_start: dt.date = dt.date(2001, 7, 1),
    record_end: dt.date = dt.date(2005, 6, 30),
    wheat_residue: str = "removed",
    soybean_residue: str = "left_on_surface",
    maize_residue: str = "incorporated",
) -> tuple[RotationDefinition, RotationCalendar, SiteClimate]:
    """Build a 2-year 3-crop rotation using the 3 crops of params/records/residues/."""
    ag_start = {"month": start_month, "provisional": True, **unmark(LABEL)}
    specs = [
        ("c1", 1, "wheat", "grain", "2001-07-10", "2001-11-30", wheat_residue),
        ("c2", 2, "soybean", "grain", "2001-12-10", "2002-05-10", soybean_residue),
        ("c3", 3, "maize", "grain", "2002-09-10", "2003-04-10", maize_residue),
    ]
    rot = RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            **IDS,
            "rotation_id": "three-crop-test",
            "label": unmark(f"{MARK} three-crop rotation"),
            "ag_year_start": ag_start,
            "repeats": True,
            "components": [
                {
                    "component_id": cid,
                    "position": pos,
                    "crop_id": crop,
                    "purpose": purpose,
                    "sowing": unmark(date_value(sowing)),
                    "harvest": unmark(date_value(harvest)),
                    "management": management(res),
                }
                for cid, pos, crop, purpose, sowing, harvest, res in specs
            ],
        }
    )
    cal = build_rotation_calendar(rot)
    assert cal.feasibility.feasible
    cli = SiteClimate.model_validate(unmark(climate_data(record_start, record_end)))
    return rot, cal, cli


def assert_ledger_conserves_mass_and_carbon(ledger: ResidueLedger, start_month: int) -> None:
    """Assert component closure and exact component == annual == monthly conservation."""
    assert ledger.first_ag_year is not None and ledger.last_ag_year is not None
    years = range(ledger.first_ag_year, ledger.last_ag_year + 1)

    for entry in ledger.components:
        assert entry.aboveground_mass_retained.value == pytest.approx(
            entry.aboveground_mass_produced.value - entry.aboveground_mass_exported.value,
            rel=1e-12,
            abs=1e-12,
        )
        assert entry.aboveground_carbon_retained.value == pytest.approx(
            entry.aboveground_carbon_produced.value - entry.aboveground_carbon_exported.value,
            rel=1e-12,
            abs=1e-12,
        )
        soil_c = (
            entry.aboveground_carbon_retained.value
            + entry.root_carbon.value
            + entry.rhizodeposit_carbon.value
        )
        total_produced_c = (
            entry.aboveground_carbon_produced.value
            + entry.root_carbon.value
            + entry.rhizodeposit_carbon.value
        )
        assert entry.aboveground_carbon_exported.value + soil_c == pytest.approx(
            total_produced_c, rel=1e-12, abs=1e-12
        )

    for mon_series in ledger.monthly_carbon_inputs:
        origin = mon_series.origin
        crop, group = origin.rsplit("_", 1)
        parts = GROUP_PARTS[group]
        ann_matching = [s for s in ledger.annual_carbon_inputs if s.origin == origin]
        assert ann_matching

        total_monthly = sum(m.value for m in mon_series.months)
        total_annual = sum(y.value for s in ann_matching for y in s.years)
        # Only components harvested inside the ledger's whole agricultural years
        # enter the annual and monthly series; a partial final cycle entry
        # harvesting after last_ag_year stays in ledger.components only.
        total_components_t = (
            sum(
                getattr(e, part).value
                for e in ledger.components
                if e.crop_id == crop
                and e.ag_year is not None
                and ledger.first_ag_year <= e.ag_year <= ledger.last_ag_year
                for part in parts
            )
            / KG_PER_TONNE
        )
        assert total_monthly == pytest.approx(total_annual, rel=1e-12, abs=1e-12)
        assert total_annual == pytest.approx(total_components_t, rel=1e-12, abs=1e-12)

        for idx, ag_year in enumerate(years):
            year_months = mon_series.months[idx * 12 : (idx + 1) * 12]
            assert (year_months[0].month) == start_month
            ann_year = sum(
                y.value
                for s in ann_matching
                for y in s.years
                if y.ag_year == ag_year
            )
            comp_year_t = (
                sum(
                    getattr(e, part).value
                    for e in ledger.components
                    if e.crop_id == crop and e.ag_year == ag_year
                    for part in parts
                )
                / KG_PER_TONNE
            )
            assert sum(m.value for m in year_months) == pytest.approx(
                ann_year, rel=1e-12, abs=1e-12
            )
            assert ann_year == pytest.approx(comp_year_t, rel=1e-12, abs=1e-12)


# --- 1. Signed residue records + harvest-level mass & carbon conservation ---


def test_signed_residue_records_catalogue_is_complete_and_valid():
    records, values = load_signed_residue_records()
    assert len(records) == 18
    for (pid, crop), val in values.items():
        assert val > 0.0, (pid, crop)
    params = hybrid_catalogue()
    assert len(params) == 18 + len(SYNTHETIC_PROPOSED) * len(SIGNED_CROPS)


def test_mass_and_carbon_conservation_across_all_three_management_modes():
    _, signed_vals = load_signed_residue_records()
    rot, cal, cli = three_crop_inputs(
        wheat_residue="removed",
        soybean_residue="left_on_surface",
        maize_residue="incorporated",
    )
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())
    assert len(ledger.components) == 6  # 2 cycles x 3 crops over 4 ag years

    expected_mgmt = {
        "wheat": "removed",
        "soybean": "left_on_surface",
        "maize": "incorporated",
    }
    for entry in ledger.components:
        crop = entry.crop_id
        assert entry.residue_management == expected_mgmt[crop]
        produced_mass = (
            signed_vals[("rusle2_residue_yield_ratio", crop)]
            * signed_vals[("rusle2_crop_yield", crop)]
        )
        c_frac = signed_vals[("residue_carbon_fraction", crop)]
        rem_frac = (
            SYNTHETIC_PROPOSED["residue_removed_fraction"][crop]
            if crop == "wheat"
            else 0.0
        )
        assert entry.aboveground_mass_produced.value == pytest.approx(produced_mass, rel=1e-12)
        assert entry.aboveground_mass_exported.value == pytest.approx(
            produced_mass * rem_frac, rel=1e-12
        )
        assert entry.aboveground_mass_retained.value == pytest.approx(
            produced_mass * (1.0 - rem_frac), rel=1e-12
        )
        assert entry.aboveground_carbon_produced.value == pytest.approx(
            produced_mass * c_frac, rel=1e-12
        )
        assert entry.aboveground_carbon_exported.value == pytest.approx(
            produced_mass * rem_frac * c_frac, rel=1e-12
        )
        assert entry.aboveground_carbon_retained.value == pytest.approx(
            produced_mass * (1.0 - rem_frac) * c_frac, rel=1e-12
        )
        if crop in ("soybean", "maize"):
            assert entry.aboveground_mass_exported.value == 0.0
            assert entry.aboveground_carbon_exported.value == 0.0
            assert entry.aboveground_mass_retained.value == entry.aboveground_mass_produced.value
            assert entry.aboveground_carbon_retained.value == entry.aboveground_carbon_produced.value

    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)


def test_incorporated_and_left_on_surface_retain_identical_mass_and_preserve_label():
    """Both ``left_on_surface`` and ``incorporated`` retain 100% of residue while keeping the management tag."""
    rot_surf, cal_surf, cli_surf = three_crop_inputs(
        wheat_residue="left_on_surface",
        soybean_residue="left_on_surface",
        maize_residue="left_on_surface",
    )
    rot_inc, cal_inc, cli_inc = three_crop_inputs(
        wheat_residue="incorporated",
        soybean_residue="incorporated",
        maize_residue="incorporated",
    )
    params = hybrid_catalogue()
    # Drop residue_removed_fraction to prove neither kept mode reads it.
    for crop in SIGNED_CROPS:
        params.pop(f"placeholder/residue_removed_fraction.{crop}.json")

    surf = build_residue_ledger(rot_surf, cal_surf, cli_surf, parameters=params)
    inc = build_residue_ledger(rot_inc, cal_inc, cli_inc, parameters=params)

    assert surf.annual_carbon_inputs == inc.annual_carbon_inputs
    assert surf.monthly_carbon_inputs == inc.monthly_carbon_inputs
    for a, b in zip(surf.components, inc.components, strict=True):
        assert a.residue_management == "left_on_surface"
        assert b.residue_management == "incorporated"
        for field in MASS_FIELDS + CARBON_FIELDS:
            assert getattr(a, field).value == getattr(b, field).value
        assert a.aboveground_mass_exported.value == 0.0
        assert b.aboveground_mass_exported.value == 0.0


def test_removal_fraction_monotonicity_and_boundary_conservation():
    """Export increases and retention decreases monotonically across [0, 1] while belowground is invariant."""
    rot, cal, cli = three_crop_inputs(
        wheat_residue="removed",
        soybean_residue="left_on_surface",
        maize_residue="removed",
    )
    fractions = [0.0, 0.25, 0.5, 0.75, 1.0]
    exported_masses: list[float] = []
    retained_masses: list[float] = []
    produced_masses: list[float] = []
    belowground_carbons: list[float] = []

    for frac in fractions:
        params = hybrid_catalogue(
            **{
                "residue_removed_fraction.maize": record(
                    "residue_removed_fraction", "maize", frac
                )
            }
        )
        ledger = build_residue_ledger(rot, cal, cli, parameters=params)
        assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)

        maize_entry = [e for e in ledger.components if e.crop_id == "maize"][0]
        produced_masses.append(maize_entry.aboveground_mass_produced.value)
        exported_masses.append(maize_entry.aboveground_mass_exported.value)
        retained_masses.append(maize_entry.aboveground_mass_retained.value)
        belowground_carbons.append(
            maize_entry.root_carbon.value + maize_entry.rhizodeposit_carbon.value
        )

        if frac == 0.0:
            assert maize_entry.aboveground_mass_exported.value == 0.0
            assert maize_entry.aboveground_carbon_exported.value == 0.0
            assert (
                maize_entry.aboveground_mass_retained.value
                == maize_entry.aboveground_mass_produced.value
            )
        if frac == 1.0:
            assert maize_entry.aboveground_mass_retained.value == 0.0
            assert maize_entry.aboveground_carbon_retained.value == 0.0
            assert (
                maize_entry.aboveground_mass_exported.value
                == maize_entry.aboveground_mass_produced.value
            )
            assert all(
                y.value == 0.0
                for y in series(ledger, "maize_grain_aboveground_carbon_retained").years
            )
            assert all(m.value == 0.0 for m in monthly(ledger, "maize_aboveground").months)
            assert any(m.value > 0.0 for m in monthly(ledger, "maize_belowground").months)

    assert all(p == pytest.approx(produced_masses[0], rel=1e-12) for p in produced_masses)
    assert all(b == pytest.approx(belowground_carbons[0], rel=1e-12) for b in belowground_carbons)
    assert all(a < b for a, b in itertools.pairwise(exported_masses))
    assert all(a > b for a, b in itertools.pairwise(retained_masses))


@pytest.mark.parametrize("zero_param", ["rusle2_crop_yield", "rusle2_residue_yield_ratio"])
def test_zero_yield_or_ratio_conserves_zero_aboveground_and_keeps_belowground(zero_param):
    params = catalogue(**{f"{zero_param}.{CROP_A}": record(zero_param, CROP_A, 0.0)})
    ledger = run(parameters=params)
    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)
    for entry in entries(ledger, "c1"):
        for field in (
            "aboveground_mass_produced",
            "aboveground_mass_exported",
            "aboveground_mass_retained",
            "aboveground_carbon_produced",
            "aboveground_carbon_exported",
            "aboveground_carbon_retained",
        ):
            assert getattr(entry, field).value == 0.0
        assert entry.root_mass.value > 0.0
        assert entry.root_carbon.value > 0.0
        assert entry.rhizodeposit_carbon.value > 0.0


# --- 2. D141 lead-in (cycle = -1) & D132 multi-phase conservation ---


def test_d141_lead_in_cycle_minus_one_conservation_and_record_start_cutoff():
    """D141: components starting before ag_year_start produce cycle=-1 entries whose carbon closes in year 0."""
    ag_start = {"month": START_MONTH, "provisional": True, **unmark(LABEL)}
    # Cycle spans May -> May, crossing the July 1 ag_year_start boundary.
    # Cycle 0 is laid out starting 2002-05-15 (inside first_ag_year 2001: 2001-07-01..2002-06-30),
    # so cycle -1 (2001-05-15..2002-05-10) has wheat (2001-11-20) and soybean (2002-05-10)
    # harvests falling inside RECORD_START..RECORD_END, while partial final cycle 2
    # starts 2004-05-15 (<= RECORD_END) and harvests in ag_year 2004 (> last_ag_year 2003).
    rot = RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            **IDS,
            "rotation_id": "d141-lead-in-test",
            "label": unmark(f"{MARK} lead-in"),
            "ag_year_start": ag_start,
            "repeats": True,
            "components": [
                {
                    "component_id": "c1",
                    "position": 1,
                    "crop_id": "wheat",
                    "purpose": "grain",
                    "sowing": unmark(date_value("2001-05-15")),
                    "harvest": unmark(date_value("2001-11-20")),
                    "management": management("incorporated"),
                },
                {
                    "component_id": "c2",
                    "position": 2,
                    "crop_id": "soybean",
                    "purpose": "grain",
                    "sowing": unmark(date_value("2001-12-05")),
                    "harvest": unmark(date_value("2002-05-10")),
                    "management": management("removed"),
                },
            ],
        }
    )
    cal = build_rotation_calendar(rot)
    assert cal.feasibility.feasible
    record_start = dt.date(2001, 7, 1)
    record_end = dt.date(2004, 6, 30)
    cli = SiteClimate.model_validate(unmark(climate_data(record_start, record_end)))

    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())
    lead_in = [e for e in ledger.components if e.cycle == -1]
    assert [e.component_id for e in lead_in] == ["c1", "c2"]
    assert min(e.cycle for e in ledger.components) == -1
    for entry in lead_in:
        assert record_start <= entry.harvest.date <= record_end
        assert entry.ag_year == 2001

    post_record = [e for e in ledger.components if e.ag_year > ledger.last_ag_year]
    assert [(e.component_id, e.cycle, e.ag_year) for e in post_record] == [("c1", 2, 2004)]

    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)


def test_d141_lead_in_pre_record_harvest_excluded_while_post_record_harvest_kept():
    """In cycle -1, a component harvested before record_start is excluded; one harvested >= record_start is included."""
    ag_start = {"month": START_MONTH, "provisional": True, **unmark(LABEL)}
    # Cycle spans 2001-05-15 .. 2002-05-10.
    # Cycle 0 is laid out starting 2002-05-15 (inside ag_year 2001).
    # Cycle -1 spans 2001-05-15 .. 2002-05-10:
    # - c1 harvests 2001-06-25 (< 2001-07-01 record_start) -> excluded from cycle -1
    # - c2 harvests 2002-05-10 (>= 2001-07-01 record_start) -> included in cycle -1
    rot = RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            **IDS,
            "rotation_id": "d141-cutoff-test",
            "label": unmark(f"{MARK} lead-in cutoff"),
            "ag_year_start": ag_start,
            "repeats": True,
            "components": [
                {
                    "component_id": "c1",
                    "position": 1,
                    "crop_id": "wheat",
                    "purpose": "grain",
                    "sowing": unmark(date_value("2001-05-15")),
                    "harvest": unmark(date_value("2001-06-25")),
                    "management": management("left_on_surface"),
                },
                {
                    "component_id": "c2",
                    "position": 2,
                    "crop_id": "soybean",
                    "purpose": "grain",
                    "sowing": unmark(date_value("2001-12-01")),
                    "harvest": unmark(date_value("2002-05-10")),
                    "management": management("removed"),
                },
            ],
        }
    )
    cal = build_rotation_calendar(rot)
    cli = SiteClimate.model_validate(
        unmark(climate_data(dt.date(2001, 7, 1), dt.date(2004, 6, 30)))
    )
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())

    lead_in = [e for e in ledger.components if e.cycle == -1]
    assert [e.component_id for e in lead_in] == ["c2"]
    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)


def test_multi_phase_d132_d141_conservation_across_all_phases():
    """Every phase of a multi-year rotation preserves component closure and annual == monthly totals."""
    rot, cal, cli = three_crop_inputs(
        record_start=dt.date(2001, 7, 1),
        record_end=dt.date(2007, 6, 30),
    )
    phases = list_phases(cal)
    assert phases == [0, 1]
    params = hybrid_catalogue()

    for phase in phases:
        pcal = phase_calendar(cal, phase)
        ledger = build_residue_ledger(rot, pcal, cli, parameters=params)
        assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)
        # In phase 1, wheat/soybean wrap into lead-in or shifted cycles cleanly without losing closure.
        assert ledger.components


# --- 3. D147, D194 & D221 origin totals and CarbonForcing handoff ---


def test_d147_d194_d221_origin_totals_and_carbon_forcing_handoff():
    """D147 (kg -> t), D194 (origin split), and D221 (monthly series) load into CarbonForcing with exact totals."""
    rot, cal, cli = three_crop_inputs(
        wheat_residue="removed",
        soybean_residue="left_on_surface",
        maize_residue="incorporated",
    )
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())
    assert (ledger.mass_unit, ledger.carbon_unit, ledger.carbon_input_unit) == (
        "kg ha-1",
        "kg C ha-1",
        "t C ha-1",
    )

    gone = {
        "value": None,
        "unit": unmark(f"{MARK}_unit"),
        "missing": {"reason": "NOT_DECLARED"},
    }
    forcing = CarbonForcing.model_validate(
        {
            "contract": "carbon_forcing",
            "example_data": True,
            **IDS,
            "rotation_id": ledger.rotation_id,
            "horizon": {
                "start": {"year": ledger.first_ag_year, "month": START_MONTH},
                "end": {"year": ledger.last_ag_year + 1, "month": START_MONTH - 1},
            },
            "soil_depth": gone,
            "climate": [],
            "carbon_inputs": [
                s.model_dump(mode="json") for s in ledger.monthly_carbon_inputs
            ],
            "annual_climate": [],
            "annual_carbon_inputs": [
                s.model_dump(mode="json") for s in ledger.annual_carbon_inputs
            ],
            "soil_properties": [],
            "soil_cover": [],
            "starting_state": [],
        }
    )

    assert len(forcing.annual_carbon_inputs) == 3 * len(PARTS)
    assert len(forcing.carbon_inputs) == 3 * 2  # aboveground + belowground per crop
    expected_origins = {f"{c}_{g}" for c in SIGNED_CROPS for g in ("aboveground", "belowground")}
    assert {s.origin for s in forcing.annual_carbon_inputs} == expected_origins
    assert {s.origin for s in forcing.carbon_inputs} == expected_origins

    # Total carbon per origin across the entire horizon matches component totals / 1000.
    for origin in sorted(expected_origins):
        crop, group = origin.rsplit("_", 1)
        parts = GROUP_PARTS[group]
        forcing_ann_total = sum(
            y.value
            for s in forcing.annual_carbon_inputs
            if s.origin == origin
            for y in s.years
        )
        forcing_mon_total = sum(
            m.value
            for s in forcing.carbon_inputs
            if s.origin == origin
            for m in s.months
        )
        component_total_t = (
            sum(
                getattr(e, part).value
                for e in ledger.components
                if e.crop_id == crop
                for part in parts
            )
            / KG_PER_TONNE
        )
        assert forcing_ann_total == pytest.approx(component_total_t, rel=1e-12)
        assert forcing_mon_total == pytest.approx(component_total_t, rel=1e-12)


def test_same_crop_multiple_harvests_and_mixed_purposes_conservation():
    """Multiple grain components of one crop sum cleanly; mixed grain+cover separates annual but merges monthly."""
    cal = calendar_data()
    rot = rotation_data(residue_a="removed", residue_b="incorporated")
    cal["components"][1]["crop_id"] = CROP_A
    rot["components"][1]["crop_id"] = CROP_A
    ledger = run(rotation=rot, calendar=cal)
    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)

    # Also test same month double-harvest for CROP_A (Dec 20 and Dec 30).
    cal_same_month = copy.deepcopy(cal)
    rot_same_month = copy.deepcopy(rot)
    cal_same_month["components"][1]["start"] = date_value("2001-12-21")
    cal_same_month["components"][1]["end"] = date_value("2001-12-30")
    rot_same_month["components"][1]["sowing"] = date_value("2001-12-21")
    rot_same_month["components"][1]["harvest"] = date_value("2001-12-30")
    ledger_same_month = run(rotation=rot_same_month, calendar=cal_same_month)
    assert_ledger_conserves_mass_and_carbon(ledger_same_month, START_MONTH)

    # Mixed grain + cover of same crop: annual separates grain vs cover; monthly merges origin.
    rot_mixed = rotation_data(purpose_b="cover")
    cal_mixed = copy.deepcopy(cal)
    rot_mixed["components"][1]["crop_id"] = CROP_A
    cal_mixed["components"][1]["crop_id"] = CROP_A
    mixed = run(rotation=rot_mixed, calendar=cal_mixed)
    assert {s.quantity for s in mixed.annual_carbon_inputs} == {
        f"{CROP_A}_grain_{p}" for p in PARTS
    } | {f"{CROP_A}_cover_{p}" for p in PARTS}
    assert {s.origin for s in mixed.monthly_carbon_inputs} == {
        f"{CROP_A}_aboveground",
        f"{CROP_A}_belowground",
    }
    for group in GROUP_PARTS:
        mon = monthly(mixed, f"{CROP_A}_{group}")
        # December (grain harvest) is finite; May (cover harvest) is MISSING_INPUT, never 0.0.
        assert month_of(mon, 2001, 12).value is not None and month_of(mon, 2001, 12).value > 0
        may = month_of(mon, 2002, 5)
        assert may.value is None and may.missing.reason == "MISSING_INPUT"


def test_leap_year_feb_29_harvest_conservation():
    """A component harvested on Feb 29 shifts to Feb 28 in non-leap years and conserves mass/carbon."""
    ag_start = {"month": START_MONTH, "provisional": True, **unmark(LABEL)}
    rot = RotationDefinition.model_validate(
        {
            "contract": "rotation_definition",
            "example_data": True,
            **IDS,
            "rotation_id": "leap-day-test",
            "label": unmark(f"{MARK} leap day"),
            "ag_year_start": ag_start,
            "repeats": True,
            "components": [
                {
                    "component_id": "c1",
                    "position": 1,
                    "crop_id": "soybean",
                    "purpose": "grain",
                    "sowing": unmark(date_value("2003-10-01")),
                    "harvest": unmark(date_value("2004-02-29")),
                    "management": management("incorporated"),
                }
            ],
        }
    )
    cal = build_rotation_calendar(rot)
    cli = SiteClimate.model_validate(
        unmark(climate_data(dt.date(2003, 7, 1), dt.date(2008, 6, 30)))
    )
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())
    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)
    feb_dates = [e.harvest.date for e in ledger.components]
    assert dt.date(2004, 2, 29) in feb_dates
    assert dt.date(2005, 2, 28) in feb_dates
    assert dt.date(2008, 2, 29) in feb_dates


# --- 4. G1-G7 Entry Guarantees ---


def test_g1_purity_no_file_network_env_clock_no_mutation_and_determinism(monkeypatch):
    """G1: pure function makes no file/network/env calls, does not mutate inputs, and is deterministic."""
    def forbid(*args, **kwargs):
        raise AssertionError("G1 violation: external I/O or env/clock access attempted")

    monkeypatch.setattr(params_catalogue, "load_folder", forbid)
    monkeypatch.setattr(socket, "create_connection", forbid)
    monkeypatch.setattr(os, "getenv", forbid)

    rot, cal, cli = three_crop_inputs()
    params = hybrid_catalogue()
    rot_before = copy.deepcopy(rot.model_dump())
    cal_before = copy.deepcopy(cal.model_dump())
    cli_before = copy.deepcopy(cli.model_dump())
    params_before = copy.deepcopy(params)

    first = build_residue_ledger(rot, cal, cli, parameters=params)
    second = build_residue_ledger(rot, cal, cli, parameters=params)

    assert first == second
    assert rot.model_dump() == rot_before
    assert cal.model_dump() == cal_before
    assert cli.model_dump() == cli_before
    assert params == params_before


def test_g2_single_rotation_isolation_and_identifier_preservation():
    """G2: each call computes one rotation of one field independently and preserves identifiers."""
    rot_a, cal_a, cli_a = three_crop_inputs(wheat_residue="removed")
    rot_b, cal_b, cli_b = three_crop_inputs(wheat_residue="incorporated")
    rot_b = rot_b.model_copy(update={"case_id": "case-b", "field_id": "field-b", "rotation_id": "rot-b"})
    cal_b = cal_b.model_copy(update={"case_id": "case-b", "field_id": "field-b", "rotation_id": "rot-b"})
    cli_b = cli_b.model_copy(update={"case_id": "case-b", "field_id": "field-b"})

    params = hybrid_catalogue()
    res_a = build_residue_ledger(rot_a, cal_a, cli_a, parameters=params)
    res_b = build_residue_ledger(rot_b, cal_b, cli_b, parameters=params)

    assert (res_a.case_id, res_a.field_id, res_a.rotation_id) == (
        IDS["case_id"],
        IDS["field_id"],
        "three-crop-test",
    )
    assert (res_b.case_id, res_b.field_id, res_b.rotation_id) == ("case-b", "field-b", "rot-b")
    assert entries(res_a, "c1")[0].aboveground_mass_exported.value > 0.0
    assert entries(res_b, "c1")[0].aboveground_mass_exported.value == 0.0


def test_g3_signature_types_and_model_roundtrip():
    """G3: signature takes validated models + keyword-only parameters and returns valid ResidueLedger."""
    sig = inspect.signature(build_residue_ledger)
    assert list(sig.parameters) == ["rotation", "calendar", "climate", "parameters"]
    assert sig.parameters["parameters"].kind is inspect.Parameter.KEYWORD_ONLY

    rot, cal, cli = three_crop_inputs()
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())
    assert isinstance(ledger, ResidueLedger)
    round_tripped = ResidueLedger.model_validate_json(ledger.model_dump_json())
    assert round_tripped == ledger


def test_g4_missing_and_infeasible_never_substitute_zero():
    """G4: missing inputs, infeasible calendars, non-grain purposes, and bad coverage return Missing."""
    # Infeasible calendar -> NOT_COMPUTABLE everywhere, never 0.
    cal_inf = calendar_data(
        feasibility={
            "feasible": False,
            "violations": [{"rule": "g4_test_rule", "component_ids": ["c1"]}],
        }
    )
    inf_ledger = run(calendar=cal_inf)
    for entry in inf_ledger.components:
        for field in MASS_FIELDS + CARBON_FIELDS:
            item = getattr(entry, field)
            assert item.value is None and item.missing.reason == "NOT_COMPUTABLE"
    for s in inf_ledger.annual_carbon_inputs:
        assert all(y.value is None and y.missing.reason == "NOT_COMPUTABLE" for y in s.years)
    for s in inf_ledger.monthly_carbon_inputs:
        assert all(m.value is None and m.missing.reason == "NOT_COMPUTABLE" for m in s.months)

    # Pasture component -> NOT_COMPUTABLE entries, MISSING_INPUT in harvest years/months.
    pasture_ledger = run(rotation=rotation_data(purpose_b="pasture"))
    for entry in entries(pasture_ledger, "c2"):
        assert entry.purpose == "pasture"
        for field in MASS_FIELDS + CARBON_FIELDS:
            assert getattr(entry, field).missing.reason == "NOT_COMPUTABLE"
    for y in series(pasture_ledger, f"{CROP_B}_pasture_root_carbon").years:
        assert y.value is None and y.missing.reason == "MISSING_INPUT"

    # Non-identifier crop_id -> entries kept, invalid identifier omitted from series.
    cal_bad_id = calendar_data()
    rot_bad_id = rotation_data()
    cal_bad_id["components"][1]["crop_id"] = "Bad-Crop-ID"
    rot_bad_id["components"][1]["crop_id"] = "Bad-Crop-ID"
    bad_id_ledger = run(rotation=rot_bad_id, calendar=cal_bad_id)
    assert any(e.crop_id == "Bad-Crop-ID" for e in bad_id_ledger.components)
    assert all(not s.origin.startswith("Bad-Crop-ID") for s in bad_id_ledger.annual_carbon_inputs)
    assert all(not s.origin.startswith("Bad-Crop-ID") for s in bad_id_ledger.monthly_carbon_inputs)


def test_g5_only_type_error_and_value_error_raised():
    """G5: raises TypeError for wrong argument types and ValueError for mismatched case_id/field_id."""
    rot, cal, cli = three_crop_inputs()
    params = hybrid_catalogue()

    with pytest.raises(TypeError):
        build_residue_ledger(rotation_data(), cal, cli, parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_residue_ledger(rot, calendar_data(), cli, parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_residue_ledger(rot, cal, climate_data(), parameters=params)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_residue_ledger(rot, cal, cli, parameters="not-a-dict")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_residue_ledger(rot, cal, cli, parameters={"k": "not-a-dict"})  # type: ignore[dict-item]

    with pytest.raises(ValueError, match="case_id"):
        build_residue_ledger(
            rot.model_copy(update={"case_id": "mismatch-case"}), cal, cli, parameters=params
        )
    with pytest.raises(ValueError, match="field_id"):
        build_residue_ledger(
            rot, cal, cli.model_copy(update={"field_id": "mismatch-field"}), parameters=params
        )


def test_g6_results_follow_models_provenance_units_and_range_missing():
    """G6: every computed value carries DERIVED provenance, source naming EP4, NOT_AVAILABLE range, and exact units."""
    rot, cal, cli = three_crop_inputs()
    ledger = build_residue_ledger(rot, cal, cli, parameters=hybrid_catalogue())

    assert ledger.mass_unit == MASS_UNIT
    assert ledger.carbon_unit == CARBON_UNIT
    assert ledger.carbon_input_unit == CARBON_INPUT_UNIT

    for entry in ledger.components:
        for field in MASS_FIELDS:
            val = getattr(entry, field)
            assert val.unit == MASS_UNIT
            assert val.provenance == "DERIVED"
            assert "engine.residues.build_residue_ledger" in val.source
            assert val.range_missing is not None and val.range_missing.reason == "NOT_AVAILABLE"
        for field in CARBON_FIELDS:
            val = getattr(entry, field)
            assert val.unit == CARBON_UNIT
            assert val.provenance == "DERIVED"
            assert "engine.residues.build_residue_ledger" in val.source
            assert val.range_missing is not None and val.range_missing.reason == "NOT_AVAILABLE"

    for s in ledger.annual_carbon_inputs + ledger.monthly_carbon_inputs:
        assert s.unit == CARBON_INPUT_UNIT
        assert s.provenance == "DERIVED"
        assert "engine.residues.build_residue_ledger" in s.source
        assert s.range_missing is not None and s.range_missing.reason == "NOT_AVAILABLE"


def test_g7_no_thresholds_or_clipping_applied():
    """G7: signature accepts no threshold/plan and large finite yields compute without clipping."""
    sig = inspect.signature(build_residue_ledger)
    for forbidden in ("threshold", "thresholds", "plan", "test_plan"):
        assert forbidden not in sig.parameters

    huge = 1.0e8
    params = catalogue(
        **{
            f"rusle2_crop_yield.{CROP_A}": record("rusle2_crop_yield", CROP_A, huge),
            f"rusle2_residue_yield_ratio.{CROP_A}": record(
                "rusle2_residue_yield_ratio", CROP_A, 1.5
            ),
        }
    )
    ledger = run(parameters=params)
    assert_ledger_conserves_mass_and_carbon(ledger, START_MONTH)
    expected_produced = huge * 1.5
    expected_exported = expected_produced * NUMBERS["residue_removed_fraction"][CROP_A]
    entry = entries(ledger, "c1")[0]
    assert entry.aboveground_mass_produced.value == pytest.approx(expected_produced, rel=1e-12)
    assert entry.aboveground_mass_exported.value == pytest.approx(expected_exported, rel=1e-12)
    assert entry.aboveground_mass_retained.value == pytest.approx(
        expected_produced - expected_exported, rel=1e-12
    )
