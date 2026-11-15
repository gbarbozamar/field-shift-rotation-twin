"""Acceptance test of EP4 ``build_residue_ledger`` (unit l1/residue-ledger-ep4, #220).

Every number here is a PLACEHOLDER: plainly unreal values with repeated
digits, chosen only so that the forms give finite numbers. None is a value of
the method, and no expected value of the science is written: each computed
number is recomputed in the test from the same records, a second time, or
checked against the closure of the ledger.

The word PLACEHOLDER marks every record. ``read_value`` refuses such a record,
so a test passes the in-memory copy in which the word is replaced by
``UNMARKED_TEST_ONLY``, as ``engine/amg/test_entry.py`` does. Nothing without
the word is written to a file.

Run from the repository root: ``python -m pytest engine/residues/``.
"""

from __future__ import annotations

import datetime as dt
import inspect
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.carbon_forcing import CarbonForcing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import CARBON_FIELDS, MASS_FIELDS, ResidueLedger
from contracts.rotation_definition import RotationDefinition
from engine.residues import build_residue_ledger
from engine.residues._parameters import (
    CARBON_INPUT_UNIT,
    CARBON_UNIT,
    KG_PER_TONNE,
    DIMENSIONLESS,
    MASS_UNIT,
    RECORDS,
)
from engine.amg.entry import STOCK_UNIT as AMG_INPUT_UNIT
from engine.residues.ledger import PARTS
from params.catalogue import check_catalogue

HERE = Path(__file__).parent
README = HERE / "README.md"
MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"

CROP_A = "test_crop_a"  # scope words without the mark, so they pass
CROP_B = "test_crop_b"
START_MONTH = 7  # PLACEHOLDER start month of the agricultural year
RECORD_START = dt.date(2001, 7, 1)  # PLACEHOLDER record: three whole years
RECORD_END = dt.date(2004, 6, 30)
YEARS = (2001, 2002, 2003)

# PLACEHOLDER numbers by record and crop; none is a value of the method.
NUMBERS: dict[str, dict[str, float]] = {
    "rusle2_residue_yield_ratio": {CROP_A: 0.777, CROP_B: 0.555},
    "rusle2_crop_yield": {CROP_A: 99.9, CROP_B: 88.8},
    "residue_carbon_fraction": {CROP_A: 0.111, CROP_B: 0.444},
    "residue_removed_fraction": {CROP_A: 0.333, CROP_B: 0.666},
    "root_mass_at_harvest": {CROP_A: 22.2, CROP_B: 11.1},
    "root_carbon_fraction": {CROP_A: 0.222, CROP_B: 0.888},
    "rhizodeposit_carbon": {CROP_A: 3.33, CROP_B: 6.66},
}


def unmark(item: Any) -> Any:
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {unmark(key): unmark(value) for key, value in item.items()}
    if isinstance(item, list):
        return [unmark(value) for value in item]
    return item


def record(
    name: str, crop: str, value: float | None, unit: str | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": RECORDS[name].parameter_id,
        "scope": {"crop": crop},
        "value": value,
        "unit": RECORDS[name].unit if unit is None else unit,
        "range": None,
        "range_missing_reason": f"{MARK}: no range in this test",
        "citation": {
            "reference": f"{MARK} reference. This is not a publication.",
            "locator": f"{MARK} locator",
        },
        "transcribed_by": f"{MARK}_person_one",
        "checked_by": f"{MARK}_person_two",
    }
    if value is None:
        data["value_missing_reason"] = f"{MARK}: nobody has given this value"
    return data


def marked_catalogue() -> dict[str, dict]:
    return {
        f"records/{name}.{crop}.json": record(name, crop, value)
        for name, by_crop in NUMBERS.items()
        for crop, value in by_crop.items()
    }


def catalogue(**changes: dict | None) -> dict[str, dict]:
    """The unmarked catalogue; ``changes`` replaces (or, with None, drops) a record."""
    records = marked_catalogue()
    for key, value in changes.items():
        path = f"records/{key}.json"
        if value is None:
            records.pop(path)
        else:
            records[path] = value
    return unmark(records)


# --- the inputs --------------------------------------------------------------------

IDS = {"case_id": "test-case", "field_id": "test-field"}
LABEL = {"provenance": "DECLARED", "source": f"{MARK}: test date"}


def date_value(day: str | None) -> dict[str, Any]:
    if day is None:
        return {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: no date"},
        }
    return {"date": day, **LABEL}


def calendar_data(**overrides: Any) -> dict[str, Any]:
    """One cycle of one agricultural year with one harvest of each crop."""
    data = {
        "contract": "rotation_calendar",
        "example_data": True,
        **IDS,
        "rotation_id": "test-rotation",
        "ag_year_start": {"month": START_MONTH, "provisional": True, **LABEL},
        "start_date": "2001-07-01",
        "end_date": "2002-06-30",
        "feasibility": {"feasible": True, "violations": []},
        "components": [
            {
                "component_id": "c1",
                "crop_id": CROP_A,
                "start": date_value("2001-07-15"),
                "end": date_value("2001-12-20"),
                "periods": [],
            },
            {
                "component_id": "c2",
                "crop_id": CROP_B,
                "start": date_value("2002-01-10"),
                "end": date_value("2002-05-30"),
                "periods": [],
            },
        ],
    }
    data.update(overrides)
    return data


def management(residue: Any) -> dict[str, Any]:
    gone = {"missing": {"reason": "NOT_DECLARED"}}
    return {"residue": residue, "grazing": gone, "termination": gone}


def rotation_data(
    residue_a: Any = "removed", residue_b: Any = "left_on_surface", purpose_b="grain"
) -> dict[str, Any]:
    return {
        "contract": "rotation_definition",
        "example_data": True,
        **IDS,
        "rotation_id": "test-rotation",
        "label": f"{MARK} rotation",
        "ag_year_start": {"month": START_MONTH, "provisional": True, **LABEL},
        "repeats": True,
        "components": [
            {
                "component_id": "c1",
                "position": 1,
                "crop_id": CROP_A,
                "purpose": "grain",
                "sowing": date_value("2001-07-15"),
                "harvest": date_value("2001-12-20"),
                "management": management(residue_a),
            },
            {
                "component_id": "c2",
                "position": 2,
                "crop_id": CROP_B,
                "purpose": purpose_b,
                "sowing": date_value("2002-01-10"),
                "harvest": date_value("2002-05-30"),
                "management": management(residue_b),
            },
        ],
    }


def climate_data(start: dt.date = RECORD_START, end: dt.date = RECORD_END) -> dict:
    days = []
    day = start
    while day <= end:
        days.append({"date": day.isoformat(), "value": 1.0})
        day += dt.timedelta(days=1)
    gone = {
        "value": None,
        "unit": f"{MARK}_unit",
        "missing": {"reason": "NOT_DECLARED"},
    }
    return {
        "contract": "site_data_climate",
        "example_data": True,
        **IDS,
        "point": {"latitude": gone, "longitude": gone, "elevation": gone},
        "daily_series": [
            {
                "quantity": "test_quantity",
                "unit": f"{MARK}_unit",
                "provenance": "OBSERVED",
                "source": f"{MARK}: test series",
                "range_missing": {"reason": "NOT_AVAILABLE"},
                "time_zone": "UTC",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "days": days,
            }
        ],
        "monthly_series": [],
    }


def run(
    *,
    rotation: dict | None = None,
    calendar: dict | None = None,
    climate: dict | None = None,
    parameters: dict | None = None,
) -> ResidueLedger:
    return build_residue_ledger(
        RotationDefinition.model_validate(rotation or rotation_data()),
        RotationCalendar.model_validate(calendar or calendar_data()),
        SiteClimate.model_validate(climate or climate_data()),
        parameters=catalogue() if parameters is None else parameters,
    )


def entries(ledger: ResidueLedger, component_id: str) -> list:
    return [item for item in ledger.components if item.component_id == component_id]


def series(ledger: ResidueLedger, quantity: str):
    (found,) = [s for s in ledger.annual_carbon_inputs if s.quantity == quantity]
    return found


# --- the cases ------------------------------------------------------------------------


def test_placeholder_catalogue_is_well_formed_once_unmarked():
    assert check_catalogue(catalogue()) == []
    assert check_catalogue(marked_catalogue()) != []  # the mark is refused


def test_two_crop_calendar_gives_ledger_with_carbon_recomputed():
    ledger = run()
    assert (ledger.first_ag_year, ledger.last_ag_year) == (YEARS[0], YEARS[-1])
    assert (ledger.mass_unit, ledger.carbon_unit) == (MASS_UNIT, CARBON_UNIT)
    assert len(ledger.components) == 2 * len(YEARS)
    removed = {CROP_A: True, CROP_B: False}
    for entry in ledger.components:
        n = {name: by_crop[entry.crop_id] for name, by_crop in NUMBERS.items()}
        produced = n["rusle2_residue_yield_ratio"] * n["rusle2_crop_yield"]
        exported = (
            produced * n["residue_removed_fraction"] if removed[entry.crop_id] else 0.0
        )
        carbon_produced = produced * n["residue_carbon_fraction"]
        carbon_exported = exported * n["residue_carbon_fraction"]
        assert entry.aboveground_mass_produced.value == pytest.approx(produced)
        assert entry.aboveground_mass_exported.value == pytest.approx(exported)
        assert entry.aboveground_carbon_produced.value == pytest.approx(carbon_produced)
        assert entry.aboveground_carbon_exported.value == pytest.approx(carbon_exported)
        assert entry.aboveground_carbon_retained.value == pytest.approx(
            carbon_produced - carbon_exported
        )
        assert entry.root_mass.value == pytest.approx(n["root_mass_at_harvest"])
        assert entry.root_carbon.value == pytest.approx(
            n["root_mass_at_harvest"] * n["root_carbon_fraction"]
        )
        assert entry.rhizodeposit_carbon.value == pytest.approx(
            n["rhizodeposit_carbon"]
        )
        assert entry.aboveground_mass_produced.provenance == "DERIVED"
        assert entry.ag_year == entry.cycle + YEARS[0]
    # The annual series: one harvest of each crop per year, recomputed, then
    # from kg C ha-1 to t C ha-1 by the SI definition 1 t = 1000 kg (D147),
    # written here a second time and not taken from the engine.
    kg_per_tonne = 1000
    for crop in (CROP_A, CROP_B):
        n = {name: by_crop[crop] for name, by_crop in NUMBERS.items()}
        share = n["residue_removed_fraction"] if removed[crop] else 0.0
        retained = (
            n["rusle2_residue_yield_ratio"] * n["rusle2_crop_yield"] * (1 - share)
        )
        expected = {
            "aboveground_carbon_retained": retained * n["residue_carbon_fraction"],
            "root_carbon": n["root_mass_at_harvest"] * n["root_carbon_fraction"],
            "rhizodeposit_carbon": n["rhizodeposit_carbon"],
        }
        for part in PARTS:
            found = series(ledger, f"{crop}_grain_{part}")
            group = (
                "aboveground"
                if part == "aboveground_carbon_retained"
                else "belowground"
            )
            assert found.origin == f"{crop}_{group}"  # D194 of #77
            assert found.unit == CARBON_INPUT_UNIT
            assert [item.ag_year for item in found.years] == list(YEARS)
            for item in found.years:
                assert item.value == pytest.approx(expected[part] / kg_per_tonne)


def test_mass_and_carbon_close_retained_plus_exported_equals_produced():
    for entry in run().components:
        for kind in ("mass", "carbon"):
            produced = getattr(entry, f"aboveground_{kind}_produced").value
            exported = getattr(entry, f"aboveground_{kind}_exported").value
            retained = getattr(entry, f"aboveground_{kind}_retained").value
            assert retained + exported == pytest.approx(produced, rel=1e-12)


def test_roots_and_aboveground_residue_stay_apart():
    without_roots = catalogue(
        **{f"root_mass_at_harvest.{crop}": None for crop in (CROP_A, CROP_B)}
    )
    whole, rootless = run(), run(parameters=without_roots)
    for a, b in zip(whole.components, rootless.components, strict=True):
        for name in MASS_FIELDS[:3] + CARBON_FIELDS[:3] + ("rhizodeposit_carbon",):
            assert getattr(a, name) == getattr(b, name)
        assert b.root_mass.value is None and b.root_carbon.value is None
        assert "root_mass_at_harvest" in b.root_mass.missing.detail
    quantities = [s.quantity for s in whole.annual_carbon_inputs]
    assert f"{CROP_A}_grain_root_carbon" in quantities
    assert f"{CROP_A}_grain_aboveground_carbon_retained" in quantities
    # Removing the root records leaves the aboveground series unchanged.
    name = f"{CROP_A}_grain_aboveground_carbon_retained"
    assert series(whole, name) == series(rootless, name)
    assert all(
        item.value is None
        for item in series(rootless, f"{CROP_A}_grain_root_carbon").years
    )


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("rusle2_residue_yield_ratio", "aboveground_mass_produced"),
        ("rusle2_crop_yield", "aboveground_mass_produced"),
        ("residue_carbon_fraction", "aboveground_carbon_produced"),
    ],
)
def test_missing_ratio_yield_or_carbon_fraction_names_itself(name, field):
    ledger = run(parameters=catalogue(**{f"{name}.{CROP_A}": None}))
    for entry in entries(ledger, "c1"):
        gone = getattr(entry, field)
        assert gone.value is None
        assert gone.missing.reason == "MISSING_INPUT"
        assert repr(name) in gone.missing.detail and repr(CROP_A) in gone.missing.detail
        assert entry.aboveground_carbon_retained.value is None  # it propagates (C3.3)
    for entry in entries(ledger, "c2"):  # the other crop is not touched
        assert getattr(entry, field).value is not None
    gone = series(ledger, f"{CROP_A}_grain_aboveground_carbon_retained").years[0]
    assert gone.missing.reason == "MISSING_INPUT" and name in gone.missing.detail


def test_null_record_repeats_its_reason():
    ledger = run(
        parameters=catalogue(
            **{
                "rusle2_crop_yield.test_crop_a": record(
                    "rusle2_crop_yield", CROP_A, None
                )
            }
        )
    )
    detail = entries(ledger, "c1")[0].aboveground_mass_produced.missing.detail
    assert "the record holds no value" in detail and "nobody has given" in detail


def test_infeasible_calendar_gives_not_computable():
    infeasible = calendar_data(
        feasibility={
            "feasible": False,
            "violations": [{"rule": "test_rule", "component_ids": ["c1"]}],
        }
    )
    ledger = run(calendar=infeasible)
    assert ledger.components
    for entry in ledger.components:
        for name in MASS_FIELDS + CARBON_FIELDS:
            item = getattr(entry, name)
            assert item.value is None and item.missing.reason == "NOT_COMPUTABLE"
            assert "test_rule" in item.missing.detail
    for found in ledger.annual_carbon_inputs:
        assert found.provenance is None
        assert all(i.missing.reason == "NOT_COMPUTABLE" for i in found.years)


def test_cover_component_is_kept_apart_and_not_computed():
    ledger = run(rotation=rotation_data(purpose_b="cover"))
    for entry in entries(ledger, "c2"):
        assert entry.purpose == "cover"
        for name in MASS_FIELDS + CARBON_FIELDS:
            assert getattr(entry, name).missing.reason == "NOT_COMPUTABLE"
    quantities = {s.quantity for s in ledger.annual_carbon_inputs}
    assert f"{CROP_B}_cover_root_carbon" in quantities
    assert f"{CROP_B}_grain_root_carbon" not in quantities
    for item in series(ledger, f"{CROP_A}_grain_root_carbon").years:
        assert item.value is not None  # the grain crop is not touched


def test_residue_not_declared_leaves_export_and_retention_missing():
    gone = {"missing": {"reason": "NOT_DECLARED", "detail": f"{MARK}: not given"}}
    ledger = run(rotation=rotation_data(residue_a=gone))
    for entry in entries(ledger, "c1"):
        assert entry.residue_management.missing.reason == "NOT_DECLARED"
        assert entry.aboveground_mass_produced.value is not None
        for name in ("aboveground_mass_exported", "aboveground_mass_retained"):
            item = getattr(entry, name)
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                "management.residue" in item.missing.detail
                or "residue of" in item.missing.detail
            )


@pytest.mark.parametrize("word", ["left_on_surface", "incorporated"])
def test_residue_kept_on_the_field_exports_nothing(word):
    ledger = run(
        rotation=rotation_data(residue_a=word),
        parameters=catalogue(**{f"residue_removed_fraction.{CROP_A}": None}),
    )
    for entry in entries(ledger, "c1"):
        assert entry.aboveground_mass_exported.value == 0.0
        assert (
            entry.aboveground_mass_retained.value
            == entry.aboveground_mass_produced.value
        )


def test_record_in_another_unit_or_outside_its_bounds_is_not_computable():
    other_unit = record("rusle2_crop_yield", CROP_A, 1.0, unit=f"{MARK}_unit")
    ledger = run(parameters=catalogue(**{f"rusle2_crop_yield.{CROP_A}": other_unit}))
    detail = entries(ledger, "c1")[0].aboveground_mass_produced.missing.detail
    assert "NOT_COMPUTABLE" in detail and "is not accepted" in detail
    too_big = record("residue_carbon_fraction", CROP_A, 1.5)
    ledger = run(parameters=catalogue(**{f"residue_carbon_fraction.{CROP_A}": too_big}))
    detail = entries(ledger, "c1")[0].aboveground_carbon_produced.missing.detail
    assert "a fraction from zero to one" in detail
    negative = record("rhizodeposit_carbon", CROP_A, -1.0)
    ledger = run(parameters=catalogue(**{f"rhizodeposit_carbon.{CROP_A}": negative}))
    assert (
        entries(ledger, "c1")[0].rhizodeposit_carbon.missing.reason == "NOT_COMPUTABLE"
    )


def test_marked_or_malformed_record_is_missing_input_naming_why():
    ledger = run(parameters=marked_catalogue())
    item = entries(ledger, "c1")[0].root_mass
    assert item.missing.reason == "MISSING_INPUT" and MARK in item.missing.detail
    broken = catalogue()
    broken["records/broken.json"] = {"value": 1.0}
    item = entries(run(parameters=broken), "c2")[0].rhizodeposit_carbon
    assert "cannot be looked up" in item.missing.detail


def test_years_are_the_whole_agricultural_years_of_the_record():
    part_year = climate_data(dt.date(2001, 8, 1), dt.date(2004, 7, 31))
    ledger = run(climate=part_year)
    assert (ledger.first_ag_year, ledger.last_ag_year) == (2002, 2003)
    for found in ledger.annual_carbon_inputs:
        assert [i.ag_year for i in found.years] == [2002, 2003]


def test_first_year_before_the_first_cycle_is_missing():
    late = calendar_data(start_date="2001-07-10", end_date="2002-07-09")
    ledger = run(calendar=late)
    for found in ledger.annual_carbon_inputs:
        first, *rest = found.years
        assert first.missing.reason == "MISSING_INPUT"
        assert "before the first cycle" in first.missing.detail
        assert all(item.value is not None for item in rest)


def test_component_starting_before_the_start_month_gives_a_lead_in_entry():
    """The lead-in of D141 (point 13 of engine/calendar/repeat.py).

    The first component starts before the start month, so the calendar starts
    in the agricultural year before, and the cycle before the first ends
    inside the record. Its entries are written as cycle -1, which the ledger
    contract admits (D160). Their harvests fall in the first agricultural
    year, and that year is their value: it is not "before the first cycle".
    """
    early = calendar_data(start_date="2001-05-25", end_date="2002-05-20")
    early["components"][0]["start"] = date_value("2001-05-25")
    early["components"][1]["end"] = date_value("2002-05-20")
    ledger = run(calendar=early)
    assert ledger.first_ag_year == YEARS[0]
    lead_in = [entry for entry in ledger.components if entry.cycle == -1]
    assert [entry.component_id for entry in lead_in] == ["c1", "c2"]
    assert min(entry.cycle for entry in ledger.components) == -1
    for entry in lead_in:
        assert RECORD_START <= entry.harvest.date <= RECORD_END
        assert entry.ag_year == YEARS[0]
        for part in PARTS:
            # The only harvest of its crop in that year: the year is its
            # value, from kg to t (D147).
            first = series(ledger, f"{entry.crop_id}_grain_{part}").years[0]
            assert first.ag_year == YEARS[0]
            assert first.value == pytest.approx(
                getattr(entry, part).value / KG_PER_TONNE
            )
    for found in ledger.annual_carbon_inputs:
        assert all(item.value is not None for item in found.years)


def test_undated_harvest_leaves_the_years_it_may_fall_in_missing():
    data = calendar_data()
    data["components"][0]["end"] = date_value(None)
    ledger = run(calendar=data)
    for entry in entries(ledger, "c1"):
        assert entry.ag_year is None and entry.harvest.missing.reason == "NOT_DECLARED"
        assert entry.aboveground_mass_produced.value is not None
    for item in series(ledger, f"{CROP_A}_grain_root_carbon").years:
        assert item.missing.reason == "MISSING_INPUT"
        assert "harvest date of component 'c1'" in item.missing.detail
    for item in series(ledger, f"{CROP_B}_grain_root_carbon").years:
        assert item.value is not None


def test_year_without_a_harvest_of_a_crop_is_zero():
    two_years = calendar_data(start_date="2001-07-01", end_date="2003-06-30")
    two_years["components"][1]["start"] = date_value("2003-01-10")
    two_years["components"][1]["end"] = date_value("2003-05-30")
    ledger = run(calendar=two_years)
    values = [
        i.value for i in series(ledger, f"{CROP_B}_grain_rhizodeposit_carbon").years
    ]
    assert values[0] == 0.0 and values[1] == pytest.approx(
        NUMBERS["rhizodeposit_carbon"][CROP_B] / 1000  # kg to t (D147)
    )


def test_ledger_without_years_says_why():
    no_series = climate_data()
    no_series["daily_series"] = []
    ledger = run(climate=no_series)
    assert ledger.years_missing.reason == "MISSING_INPUT"
    assert ledger.components == [] and ledger.annual_carbon_inputs == []
    short = run(climate=climate_data(dt.date(2001, 8, 1), dt.date(2002, 6, 30)))
    assert short.years_missing.reason == "NO_COVERAGE"


def test_series_load_into_carbon_forcing_unchanged():
    ledger = run()
    gone = {
        "value": None,
        "unit": f"{MARK}_unit",
        "missing": {"reason": "NOT_DECLARED"},
    }
    forcing = CarbonForcing.model_validate(
        {
            "contract": "carbon_forcing",
            "example_data": True,
            **IDS,
            "rotation_id": "test-rotation",
            "horizon": {
                "start": {"year": YEARS[0], "month": START_MONTH},
                "end": {"year": YEARS[-1] + 1, "month": START_MONTH - 1},
            },
            "soil_depth": gone,
            "climate": [],
            "carbon_inputs": [],
            "annual_climate": [],
            "annual_carbon_inputs": [
                s.model_dump(mode="json") for s in ledger.annual_carbon_inputs
            ],
            "soil_properties": [],
            "soil_cover": [],
            "starting_state": [],
        }
    )
    assert len(forcing.annual_carbon_inputs) == len(ledger.annual_carbon_inputs)
    # D147: the series are in the unit AMG requires, so nothing is converted
    # after EP4; the entries of the ledger stay in kg.
    assert {s.unit for s in forcing.annual_carbon_inputs} == {AMG_INPUT_UNIT}
    assert ledger.carbon_input_unit == AMG_INPUT_UNIT
    assert ledger.carbon_unit == CARBON_UNIT != AMG_INPUT_UNIT


def previous_origins(ledger: ResidueLedger) -> list[dict[str, Any]]:
    """The series of the ledger with the origin of the rule before D194 (the
    crop), written here and not taken from the engine: every other field as
    the engine wrote it."""
    result = []
    for item in ledger.annual_carbon_inputs:
        dumped = item.model_dump(mode="json")
        crop = item.quantity.split("_grain_")[0]
        dumped["origin"] = crop
        result.append(dumped)
    return result


def test_series_origin_is_the_part_group():
    """D194 of #77: per crop and purpose, three series whose origins are
    <crop>_aboveground (retained aboveground carbon) and <crop>_belowground
    (root carbon, rhizodeposit carbon); everything else is as before."""
    ledger = run()
    origins = {s.quantity: s.origin for s in ledger.annual_carbon_inputs}
    assert origins == {
        f"{crop}_grain_{part}": f"{crop}_{group}"
        for crop in (CROP_A, CROP_B)
        for part, group in (
            ("aboveground_carbon_retained", "aboveground"),
            ("root_carbon", "belowground"),
            ("rhizodeposit_carbon", "belowground"),
        )
    }
    # Every value, year, unit, label and source is the one of the previous
    # rule: only the origin differs.
    for before, after in zip(
        previous_origins(ledger), ledger.annual_carbon_inputs, strict=True
    ):
        now = after.model_dump(mode="json")
        assert now.pop("origin") != before.pop("origin")
        assert now == before
    # The components, which carry no origin, are untouched.
    assert ResidueLedger.model_validate(ledger.model_dump(mode="json")) == ledger


# --- through EP5: one humification coefficient for each origin group (D194) -------------


def amg_ledger() -> ResidueLedger:
    """The two-crop ledger over the agricultural years of the AMG test forcing
    (calendar years, start month 1), so its series fit that horizon."""
    from engine.amg import test_entry as amg_test

    first, last = amg_test.YEARS[0], amg_test.YEARS[-1]
    start = {"month": 1, "provisional": True, **LABEL}
    calendar = calendar_data(
        ag_year_start=start, start_date=f"{first}-01-01", end_date=f"{first}-12-31"
    )
    rotation = rotation_data()
    rotation["ag_year_start"] = start
    for item, (sowing, harvest) in zip(
        calendar["components"],
        ((f"{first}-01-15", f"{first}-06-20"), (f"{first}-07-10", f"{first}-11-30")),
        strict=True,
    ):
        item["start"], item["end"] = date_value(sowing), date_value(harvest)
    for item, part in zip(rotation["components"], calendar["components"], strict=True):
        item["sowing"], item["harvest"] = part["start"], part["end"]
    ledger = run(
        rotation=rotation,
        calendar=calendar,
        climate=climate_data(dt.date(first, 1, 1), dt.date(last, 12, 31)),
    )
    assert (ledger.first_ag_year, ledger.last_ag_year) == (first, last)
    return ledger


# PLACEHOLDER humification coefficients, one per origin group of each crop, and
# one under the plain crop word that must never be read (D194).
HUMIFICATION = {
    f"{CROP_A}_aboveground": 0.123,
    f"{CROP_A}_belowground": 0.456,
    f"{CROP_B}_aboveground": 0.234,
    f"{CROP_B}_belowground": 0.567,
}
PLAIN_CROP = {CROP_A: 0.999, CROP_B: 0.888}


def amg_parameters(coefficients: dict[str, float]) -> dict[str, dict]:
    """The PLACEHOLDER catalogue of engine/amg/test_entry.py without its
    humification records, with ``coefficients`` under the scope key of EP5."""
    from engine.amg import entry
    from engine.amg import test_entry as amg_test

    records = amg_test.catalogue_with("humification_coefficient", None)
    for origin, value in coefficients.items():
        records[f"records/humification_{origin}.json"] = amg_test.unmark(
            amg_test.record(
                entry.PARAMETERS["humification_coefficient"][0],
                value,
                "dimensionless",
                {entry.ORIGIN_SCOPE_KEY: origin},
            )
        )
    return records


def amg_forcing(ledger: ResidueLedger) -> CarbonForcing:
    from engine.amg import test_entry as amg_test

    data = amg_test.forcing_data()
    data["annual_carbon_inputs"] = [
        s.model_dump(mode="json") for s in ledger.annual_carbon_inputs
    ]
    return CarbonForcing.model_validate(data)


def test_amg_reads_one_coefficient_per_origin_group():
    """Through EP5 (``run_amg``): the humified input of each year is the sum of
    each series times the coefficient of its origin group, recomputed here;
    the records under the plain crop word are in the catalogue and not read."""
    from engine.amg import entry, run_amg

    ledger = amg_ledger()
    forcing = amg_forcing(ledger)
    balance = run_amg(
        forcing, parameters=amg_parameters({**HUMIFICATION, **PLAIN_CROP})
    )
    (humified,) = [f for f in balance.flows if f.quantity.endswith("humified_input")]
    assert len(humified.steps) == len(ledger.annual_carbon_inputs[0].years)

    def value_of(series, year: int) -> float:
        (found,) = [item.value for item in series.years if item.ag_year == year]
        return found

    # Start month 1: the agricultural year of a step is the year of its start.
    for step in humified.steps:
        year = step.start.year
        expected = sum(
            value_of(s, year) * HUMIFICATION[s.origin]
            for s in forcing.annual_carbon_inputs
        )
        plain = sum(
            value_of(s, year) * PLAIN_CROP[s.origin.rsplit("_", 1)[0]]
            for s in forcing.annual_carbon_inputs
        )
        assert step.value == pytest.approx(expected, rel=1e-12)
        assert step.value != pytest.approx(plain)  # the plain crop record unread
    # The source of the flow names the humification record it read.
    assert f"'{entry.PARAMETERS['humification_coefficient'][0]}'" in humified.source


def test_amg_without_the_group_records_names_them_and_not_the_crop():
    """With only records under the plain crop word, EP5 finds none for the
    origins EP4 writes: the humified input is missing and names each
    <crop>_aboveground and <crop>_belowground scope it looked for."""
    from engine.amg import entry, run_amg

    forcing = amg_forcing(amg_ledger())
    balance = run_amg(forcing, parameters=amg_parameters(PLAIN_CROP))
    (humified,) = [f for f in balance.flows if f.quantity.endswith("humified_input")]
    detail = humified.steps[0].missing.detail
    assert humified.steps[0].missing.reason == "MISSING_INPUT"
    named = {s.origin for s in forcing.annual_carbon_inputs}
    assert named == set(HUMIFICATION)
    assert any(f'"{entry.ORIGIN_SCOPE_KEY}": "{origin}"' in detail for origin in named)
    for crop in PLAIN_CROP:
        assert f'"{entry.ORIGIN_SCOPE_KEY}": "{crop}"' not in detail


# --- the monthly carbon inputs of D221 ------------------------------------------------


GROUP_PARTS = {
    "aboveground": ("aboveground_carbon_retained",),
    "belowground": ("root_carbon", "rhizodeposit_carbon"),
}


def monthly(ledger: ResidueLedger, origin: str):
    (found,) = [s for s in ledger.monthly_carbon_inputs if s.origin == origin]
    return found


def month_of(series_, year: int, month: int):
    (found,) = [m for m in series_.months if (m.year, m.month) == (year, month)]
    return found


def test_monthly_series_use_the_origins_of_d194():
    """D221 of #77: one monthly series per origin of D194, over every month of
    the agricultural years of the ledger, from the start month, in t C ha-1."""
    ledger = run()
    origins = [s.origin for s in ledger.monthly_carbon_inputs]
    assert origins == [
        f"{crop}_{group}" for crop in (CROP_A, CROP_B) for group in GROUP_PARTS
    ]
    for item in ledger.monthly_carbon_inputs:
        assert item.quantity == f"{item.origin}_carbon_input"
        assert item.unit == CARBON_INPUT_UNIT == AMG_INPUT_UNIT
        assert (item.start.year, item.start.month) == (YEARS[0], START_MONTH)
        assert (item.end.year, item.end.month) == (YEARS[-1] + 1, START_MONTH - 1)
        assert len(item.months) == 12 * len(YEARS)
        assert "D221" in item.source
    # The annual series keep their own origins (D194): the same set.
    assert {s.origin for s in ledger.annual_carbon_inputs} == set(origins)


def test_harvest_month_carries_the_whole_component_and_other_months_are_zero():
    """All the carbon of a component enters in the calendar month of its
    harvest; every other month is an explicit zero (D221). Recomputed here
    from the entries of the ledger, converted by 1 t = 1000 kg (D147)."""
    ledger = run()
    kg_per_tonne = 1000
    for crop in (CROP_A, CROP_B):
        for group, parts in GROUP_PARTS.items():
            found = monthly(ledger, f"{crop}_{group}")
            expected: dict[tuple[int, int], float] = {}
            for entry in ledger.components:
                if entry.crop_id != crop:
                    continue
                key = (entry.harvest.date.year, entry.harvest.date.month)
                carbon = sum(getattr(entry, part).value for part in parts)
                expected[key] = expected.get(key, 0.0) + carbon / kg_per_tonne
            assert expected  # one harvest a year
            for item in found.months:
                value = expected.get((item.year, item.month), 0.0)
                assert item.missing is None
                assert item.value == pytest.approx(value, rel=1e-12)
            zeros = [m for m in found.months if (m.year, m.month) not in expected]
            assert zeros and all(m.value == 0.0 for m in zeros)  # explicit zeros


def test_two_harvests_in_one_month_add_up():
    """Two components of one crop harvested in the same calendar month: the
    month holds the sum of both (D221)."""
    calendar = calendar_data()
    second = calendar["components"][1]
    second.update(
        crop_id=CROP_A, start=date_value("2001-12-21"), end=date_value("2001-12-30")
    )
    rotation = rotation_data()
    item = rotation["components"][1]
    item.update(
        crop_id=CROP_A,
        sowing=date_value("2001-12-21"),
        harvest=date_value("2001-12-30"),
    )
    ledger = run(rotation=rotation, calendar=calendar)
    for group, parts in GROUP_PARTS.items():
        found = monthly(ledger, f"{CROP_A}_{group}")
        december = [
            entry
            for entry in ledger.components
            if (entry.harvest.date.year, entry.harvest.date.month) == (2001, 12)
        ]
        assert {entry.component_id for entry in december} == {"c1", "c2"}
        total = sum(getattr(e, part).value for e in december for part in parts)
        assert month_of(found, 2001, 12).value == pytest.approx(
            total / KG_PER_TONNE, rel=1e-12
        )
    assert not [s for s in ledger.monthly_carbon_inputs if s.origin.startswith(CROP_B)]


def test_missing_component_gives_missing_months_never_zero():
    """A component whose carbon is missing makes its harvest month missing;
    an undated harvest makes every month it may fall in missing. Never zero."""
    rootless = run(parameters=catalogue(**{f"root_mass_at_harvest.{CROP_A}": None}))
    below = monthly(rootless, f"{CROP_A}_belowground")
    for entry in entries(rootless, "c1"):
        item = month_of(below, entry.harvest.date.year, entry.harvest.date.month)
        assert item.value is None and item.missing.reason == "MISSING_INPUT"
        assert "root_carbon of component 'c1'" in item.missing.detail
    # The aboveground series of the same crop does not need the roots.
    above = monthly(rootless, f"{CROP_A}_aboveground")
    assert all(item.value is not None for item in above.months)

    undated = calendar_data()
    undated["components"][0]["end"] = date_value(None)
    ledger = run(calendar=undated)
    found = monthly(ledger, f"{CROP_A}_aboveground")
    missing = [m for m in found.months if m.value is None]
    assert missing
    for item in missing:
        assert item.missing.reason == "MISSING_INPUT"
        assert "harvest date of component 'c1'" in item.missing.detail
    assert not [m for m in missing if m.value == 0.0]
    # Crop B, harvested on its dates, is computed in every month.
    assert all(
        m.value is not None for m in monthly(ledger, f"{CROP_B}_aboveground").months
    )


def test_months_before_a_late_first_cycle_are_missing_never_zero():
    """The lead-in rule of the months (``_month_value``): the first cycle is
    laid out from a day after the start of the first agricultural year, so a
    harvest in the months before that day, or in its own month before it, is
    not known. Those months are missing, never zero; the months after are
    computed. Without the rule they would read as months without a harvest."""
    for first_day, unknown in (
        ("2001-09-20", [(2001, 7), (2001, 8), (2001, 9)]),
        ("2001-09-01", [(2001, 7), (2001, 8)]),  # the month of a first day is known
    ):
        late = calendar_data(start_date=first_day, end_date="2002-09-19")
        late["components"][0]["start"] = date_value("2001-09-25")
        ledger = run(calendar=late)
        assert ledger.first_ag_year == YEARS[0]
        for found in ledger.monthly_carbon_inputs:
            for item in found.months:
                if (item.year, item.month) in unknown:
                    assert item.value is None, (found.origin, item)
                    assert item.missing.reason == "MISSING_INPUT"
                    assert f"before {first_day}" in item.missing.detail
                    assert "before the first cycle" in item.missing.detail
                else:
                    assert item.value is not None, (found.origin, item)


def test_monthly_sum_equals_the_annual_series():
    """For each origin and agricultural year, the sum of the twelve months
    equals the sum of the annual series of that origin in that year (D221)."""
    for ledger in (
        run(),
        run(parameters=catalogue(**{f"root_mass_at_harvest.{CROP_A}": None})),
    ):
        checked = 0
        for found in ledger.monthly_carbon_inputs:
            annual = [
                s for s in ledger.annual_carbon_inputs if s.origin == found.origin
            ]
            assert annual
            for year in YEARS:
                months = found.months[
                    (year - YEARS[0]) * 12 : (year - YEARS[0] + 1) * 12
                ]
                assert (months[0].year, months[0].month) == (year, START_MONTH)
                values = [
                    item.value
                    for series_ in annual
                    for item in series_.years
                    if item.ag_year == year
                ]
                if any(v is None for v in values):
                    # A missing annual value has at least one missing month.
                    assert any(m.value is None for m in months)
                    continue
                assert all(m.value is not None for m in months)
                assert sum(m.value for m in months) == pytest.approx(
                    sum(values), rel=1e-12
                )
                checked += 1
        assert checked


def test_series_are_in_tonnes_hand_checked():
    """D147, checked by hand on one PLACEHOLDER number.

    The rhizodeposit carbon of crop A is the record, 3.33 kg C ha-1, one
    harvest a year, so each year of its series is 3.33 / 1000 = 0.00333 t C ha-1.
    """
    assert (CARBON_UNIT, CARBON_INPUT_UNIT) == ("kg C ha-1", "t C ha-1")
    assert KG_PER_TONNE == 1000
    assert NUMBERS["rhizodeposit_carbon"][CROP_A] == 3.33
    ledger = run()
    for entry in entries(ledger, "c1"):
        assert entry.rhizodeposit_carbon.value == 3.33  # the ledger stays in kg
        assert entry.rhizodeposit_carbon.unit == "kg C ha-1"
    found = series(ledger, f"{CROP_A}_grain_rhizodeposit_carbon")
    assert found.unit == "t C ha-1"
    assert [item.value for item in found.years] == pytest.approx([0.00333] * 3)
    assert "D147" in found.source


def test_ledger_round_trips_and_arguments_are_not_changed():
    rotation = RotationDefinition.model_validate(rotation_data())
    calendar = RotationCalendar.model_validate(calendar_data())
    climate = SiteClimate.model_validate(climate_data())
    parameters = catalogue()
    before = (
        rotation.model_dump(),
        calendar.model_dump(),
        climate.model_dump(),
        repr(parameters),
    )
    ledger = build_residue_ledger(rotation, calendar, climate, parameters=parameters)
    again = build_residue_ledger(rotation, calendar, climate, parameters=parameters)
    assert ledger == again
    assert ResidueLedger.model_validate(ledger.model_dump(mode="json")) == ledger
    assert before == (
        rotation.model_dump(),
        calendar.model_dump(),
        climate.model_dump(),
        repr(parameters),
    )


def test_wrong_argument_types_and_other_field_raise():
    rotation = RotationDefinition.model_validate(rotation_data())
    calendar = RotationCalendar.model_validate(calendar_data())
    climate = SiteClimate.model_validate(climate_data())
    with pytest.raises(TypeError):
        build_residue_ledger(rotation_data(), calendar, climate, parameters={})
    with pytest.raises(TypeError):
        build_residue_ledger(rotation, calendar, climate, parameters=[])
    other = climate_data()
    other["field_id"] = "test-other-field"
    with pytest.raises(ValueError, match="field_id"):
        build_residue_ledger(
            rotation, calendar, SiteClimate.model_validate(other), parameters={}
        )


def test_signature_is_the_one_of_entrypoints():
    signature = inspect.signature(build_residue_ledger)
    assert list(signature.parameters) == [
        "rotation",
        "calendar",
        "climate",
        "parameters",
    ]
    assert signature.parameters["parameters"].kind is inspect.Parameter.KEYWORD_ONLY


def test_records_have_the_units_of_the_readme():
    units = {spec.unit for spec in RECORDS.values()}
    assert units == {DIMENSIONLESS, MASS_UNIT, CARBON_UNIT}
    text = README.read_text(encoding="utf-8")
    for spec in RECORDS.values():
        assert f"`{spec.parameter_id}`" in text


def section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written
