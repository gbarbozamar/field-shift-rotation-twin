"""Unit & mutant-killing edge tests for ``engine/residues/_parameters.py``
and the parameter-boundary behaviour of ``engine/residues/ledger.py``.

Every record, unit string, crop name, date, and number in this file is a
PLACEHOLDER: no value of the science is written or claimed. Valid in-memory
catalogues replace ``PLACEHOLDER`` with ``UNMARKED_TEST_ONLY`` so
``params.catalogue.read_value`` accepts them while still verifying that raw
``PLACEHOLDER`` records are refused.

Run from the repository root:
``py -3.12 -m pytest engine/residues/test_parameters_edge.py -q``
"""

from __future__ import annotations

import copy
import datetime as dt
import math
from types import MappingProxyType
from typing import Any

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.residue_ledger import ResidueLedger
from contracts.rotation_definition import RotationDefinition
from engine.residues import build_residue_ledger
from engine.residues._parameters import (
    CARBON_INPUT_UNIT,
    CARBON_UNIT,
    CROP_SCOPE_KEY,
    DIMENSIONLESS,
    FRACTION,
    KG_PER_TONNE,
    MASS_UNIT,
    NOT_NEGATIVE,
    RECORDS,
    Catalogue,
    named,
)
from params.catalogue import check_catalogue

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
ONE_DAY = dt.timedelta(days=1)

CROP_A = "test_crop_alpha"
CROP_B = "test_crop_beta"
START_MONTH = 7
RECORD_START = dt.date(2001, 7, 1)
RECORD_END = dt.date(2003, 6, 30)

PLACEHOLDER_NUMBERS: dict[str, dict[str, float]] = {
    "rusle2_residue_yield_ratio": {CROP_A: 0.777, CROP_B: 0.555},
    "rusle2_crop_yield": {CROP_A: 88.8, CROP_B: 44.4},
    "residue_carbon_fraction": {CROP_A: 0.222, CROP_B: 0.333},
    "residue_removed_fraction": {CROP_A: 0.111, CROP_B: 0.666},
    "root_mass_at_harvest": {CROP_A: 12.3, CROP_B: 23.4},
    "root_carbon_fraction": {CROP_A: 0.444, CROP_B: 0.555},
    "rhizodeposit_carbon": {CROP_A: 3.21, CROP_B: 6.54},
}


def _unmark(item: Any) -> Any:
    """Return an in-memory copy with the PLACEHOLDER word replaced."""
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {_unmark(k): _unmark(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_unmark(v) for v in item]
    return item


def _record(
    name: str,
    crop: str,
    value: float | None,
    unit: str | None = None,
    *,
    scope: dict[str, str] | None = None,
    missing_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PLACEHOLDER catalogue record for ``RECORDS[name]``."""
    spec = RECORDS[name]
    rec: dict[str, Any] = {
        "id": spec.parameter_id,
        "scope": {CROP_SCOPE_KEY: crop} if scope is None else dict(scope),
        "value": value,
        "unit": spec.unit if unit is None else unit,
        "range": None,
        "range_missing_reason": f"{MARK}: no range in edge test",
        "citation": {
            "reference": f"{MARK} reference",
            "locator": f"{MARK} locator",
        },
        "transcribed_by": f"{MARK}_person_one",
        "checked_by": f"{MARK}_person_two",
    }
    if value is None:
        rec["value_missing_reason"] = missing_reason or f"{MARK}: no value given"
    if extra:
        rec.update(extra)
    return rec


def _catalogue(
    *, unmarked: bool = True, **overrides: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    cat: dict[str, dict[str, Any]] = {
        f"records/{name}.{crop}.json": _record(name, crop, val)
        for name, by_crop in PLACEHOLDER_NUMBERS.items()
        for crop, val in by_crop.items()
    }
    for key, val in overrides.items():
        path = f"records/{key}.json"
        if val is None:
            cat.pop(path, None)
        else:
            cat[path] = val
    return _unmark(cat) if unmarked else cat


IDS = {"case_id": "test-case", "field_id": "test-field"}
LABEL = {"provenance": "DECLARED", "source": f"{MARK}: test date"}


def _date_value(day: str, *, end_source: str | None = "default", assumption: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "date": day,
        "provenance": "DECLARED",
        "assumption": assumption,
    }
    if end_source == "default":
        out["source"] = f"{MARK}: test date"
    elif end_source is not None:
        out["source"] = end_source
    return out


def _calendar(
    *,
    provisional: bool = True,
    end_source: str | None = "default",
    assumption: bool = False,
) -> RotationCalendar:
    return RotationCalendar.model_validate(
        {
            "contract": "rotation_calendar",
            "example_data": True,
            **IDS,
            "rotation_id": "test-rotation",
            "ag_year_start": {"month": START_MONTH, "provisional": provisional, **LABEL},
            "start_date": "2001-07-01",
            "end_date": "2002-06-30",
            "feasibility": {"feasible": True, "violations": []},
            "components": [
                {
                    "component_id": "c1",
                    "crop_id": CROP_A,
                    "start": _date_value("2001-07-15"),
                    "end": _date_value(
                        "2001-12-20", end_source=end_source, assumption=assumption
                    ),
                    "periods": [],
                },
                {
                    "component_id": "c2",
                    "crop_id": CROP_B,
                    "start": _date_value("2002-01-10"),
                    "end": _date_value("2002-05-30"),
                    "periods": [],
                },
            ],
        }
    )


def _rotation(residue_a: str = "removed", residue_b: str = "left_on_surface") -> RotationDefinition:
    gone = {"missing": {"reason": "NOT_DECLARED"}}
    return RotationDefinition.model_validate(
        {
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
                    "sowing": _date_value("2001-07-15"),
                    "harvest": _date_value("2001-12-20"),
                    "management": {"residue": residue_a, "grazing": gone, "termination": gone},
                },
                {
                    "component_id": "c2",
                    "position": 2,
                    "crop_id": CROP_B,
                    "purpose": "grain",
                    "sowing": _date_value("2002-01-10"),
                    "harvest": _date_value("2002-05-30"),
                    "management": {"residue": residue_b, "grazing": gone, "termination": gone},
                },
            ],
        }
    )


def _climate(first: dt.date = RECORD_START, last: dt.date = RECORD_END) -> SiteClimate:
    days = []
    cur = first
    while cur <= last:
        days.append({"date": cur.isoformat(), "value": 1.0})
        cur += ONE_DAY
    gone = {"value": None, "unit": f"{MARK}_unit", "missing": {"reason": "NOT_DECLARED"}}
    return SiteClimate.model_validate(
        {
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
                    "start_date": first.isoformat(),
                    "end_date": last.isoformat(),
                    "days": days,
                }
            ],
            "monthly_series": [],
        }
    )


# =============================================================================
# 1. check_parameters / G5 checks
# =============================================================================


def test_g5_parameters_must_be_keyword_dict_of_str_to_dict():
    rot = _rotation()
    cal = _calendar()
    cli = _climate()
    valid_rec = _unmark(_record("rusle2_crop_yield", CROP_A, 10.0))

    with pytest.raises(TypeError, match="parameters"):
        build_residue_ledger(rot, cal, cli)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        build_residue_ledger(rot, cal, cli, {})  # type: ignore[misc]

    for bad_container in (
        None,
        [],
        (),
        MARK,
        42,
        set(),
        MappingProxyType({}),
        [("a.json", valid_rec)],
    ):
        with pytest.raises(TypeError, match="parameters"):
            build_residue_ledger(rot, cal, cli, parameters=bad_container)  # type: ignore[arg-type]

    for bad_key in (1, None, b"a.json", ("a",), True):
        with pytest.raises(TypeError, match="parameters"):
            build_residue_ledger(rot, cal, cli, parameters={bad_key: valid_rec})  # type: ignore[dict-item]

    for bad_val in (None, [], (), MARK, 3.14, MappingProxyType(valid_rec)):
        with pytest.raises(TypeError, match="parameters"):
            build_residue_ledger(rot, cal, cli, parameters={"a.json": bad_val})  # type: ignore[dict-item]


def test_g5_wrong_model_types_and_mismatched_field_identifiers_raise():
    rot = _rotation()
    cal = _calendar()
    cli = _climate()

    for bad_rot in (rot.model_dump(), cal, None):
        with pytest.raises(TypeError, match="rotation"):
            build_residue_ledger(bad_rot, cal, cli, parameters={})  # type: ignore[arg-type]
    for bad_cal in (cal.model_dump(), cli, None):
        with pytest.raises(TypeError, match="calendar"):
            build_residue_ledger(rot, bad_cal, cli, parameters={})  # type: ignore[arg-type]
    for bad_cli in (cli.model_dump(), rot, None):
        with pytest.raises(TypeError, match="climate"):
            build_residue_ledger(rot, cal, bad_cli, parameters={})  # type: ignore[arg-type]

    for bad_field in ("case_id", "field_id"):
        altered = cli.model_copy(update={bad_field: "other-value"})
        with pytest.raises(ValueError, match=rf"{bad_field}.*\(G5\)") as exc:
            build_residue_ledger(rot, cal, altered, parameters={})
        assert "other-value" not in str(exc.value)


def test_g5_catalogue_defects_never_raise_in_catalogue_or_entry_point():
    rot = _rotation()
    cal = _calendar()
    cli = _climate()

    for defect_cat in (
        _catalogue(unmarked=False),  # raw PLACEHOLDER records
        {"bad_shape.json": {"id": None, "scope": {}}},
        {
            "bad_unit.json": _unmark(
                _record("rusle2_crop_yield", CROP_A, 10.0, unit="t ha-1")
            ),
            "bad_bound.json": _unmark(
                _record("residue_carbon_fraction", CROP_A, 1.5)
            ),
        },
    ):
        ledger = build_residue_ledger(rot, cal, cli, parameters=defect_cat)
        assert isinstance(ledger, ResidueLedger)
        assert ledger.components


# =============================================================================
# 2. Exact (id, scope) lookup, units, bounds, and check precedence
# =============================================================================


def test_exact_id_and_scope_lookup_ignores_path_and_normalises_case_and_whitespace():
    rec = _unmark(_record("rusle2_crop_yield", CROP_A, 55.5))
    rec["id"] = "RUSLE2_CROP_YIELD"
    rec["scope"] = {"crop": f"  {CROP_A.upper()}  "}
    cat = {"nested/unrelated/path.json": rec}
    assert check_catalogue(cat) == []

    reader = Catalogue(cat)
    assert reader.value("rusle2_crop_yield", CROP_A) == 55.5


def test_exact_scope_does_not_fall_back_to_empty_wider_or_other_crop_scope():
    cat = _unmark(
        {
            "empty.json": _record("rusle2_crop_yield", CROP_A, 10.0, scope={}),
            "wider.json": _record(
                "rusle2_crop_yield",
                CROP_A,
                20.0,
                scope={"crop": CROP_A, "region": "test_region"},
            ),
            "other_crop.json": _record("rusle2_crop_yield", CROP_B, 30.0),
        }
    )
    assert check_catalogue(cat) == []

    reader = Catalogue(cat)
    miss = reader.value("rusle2_crop_yield", CROP_A)
    assert isinstance(miss, InputMissing)
    assert miss.reason == "MISSING_INPUT"
    assert miss.detail == f"{named('rusle2_crop_yield', CROP_A)}: no record in parameters (D56)"


def test_duplicate_id_and_scope_including_normalised_collision_is_missing_input():
    r1 = _record("root_mass_at_harvest", CROP_A, 10.0)
    r2 = _record("root_mass_at_harvest", CROP_A, 20.0)
    r2["id"] = "ROOT_MASS_AT_HARVEST"
    r2["scope"] = {"crop": f" {CROP_A.upper()} "}
    cat = _unmark({"a.json": r1, "b.json": r2})

    reader = Catalogue(cat)
    miss = reader.value("root_mass_at_harvest", CROP_A)
    assert isinstance(miss, InputMissing)
    assert miss.reason == "MISSING_INPUT"
    assert "two records share this id and scope" in miss.detail
    assert named("root_mass_at_harvest", CROP_A) in miss.detail


def test_unit_guard_rejects_unaccepted_units_without_conversion():
    bad_units = {
        "rusle2_residue_yield_ratio": "percent",
        "rusle2_crop_yield": "t ha-1",
        "residue_carbon_fraction": "g kg-1",
        "residue_removed_fraction": "percent",
        "root_mass_at_harvest": "t ha-1",
        "root_carbon_fraction": "g kg-1",
        "rhizodeposit_carbon": "t C ha-1",
    }
    for name, bad_unit in bad_units.items():
        cat = _unmark({"u.json": _record(name, CROP_A, 0.5, unit=bad_unit)})
        res = Catalogue(cat).value(name, CROP_A)
        assert isinstance(res, InputMissing)
        assert res.reason == "NOT_COMPUTABLE"
        assert "nothing is converted" in res.detail
        assert repr(bad_unit) in res.detail
        assert repr(RECORDS[name].unit) in res.detail


def test_bounds_guard_boundaries_for_not_negative_and_fraction():
    for name, spec in RECORDS.items():
        # Lower bound 0.0 accepted; -1e-9 rejected
        ok_zero = Catalogue(_unmark({"z.json": _record(name, CROP_A, 0.0)})).value(
            name, CROP_A
        )
        assert ok_zero == 0.0

        bad_neg = Catalogue(_unmark({"n.json": _record(name, CROP_A, -1e-9)})).value(
            name, CROP_A
        )
        assert isinstance(bad_neg, InputMissing)
        assert bad_neg.reason == "NOT_COMPUTABLE"

        if spec.bounds == FRACTION:
            assert "a fraction from zero to one" in bad_neg.detail
            ok_one = Catalogue(_unmark({"o.json": _record(name, CROP_A, 1.0)})).value(
                name, CROP_A
            )
            assert ok_one == 1.0
            bad_high = Catalogue(
                _unmark({"h.json": _record(name, CROP_A, 1.0 + 1e-9)})
            ).value(name, CROP_A)
            assert isinstance(bad_high, InputMissing)
            assert bad_high.reason == "NOT_COMPUTABLE"
            assert "a fraction from zero to one" in bad_high.detail
        else:
            assert spec.bounds == NOT_NEGATIVE
            assert "a number that is not negative" in bad_neg.detail
            ok_gt_one = Catalogue(
                _unmark({"g.json": _record(name, CROP_A, 2.5)})
            ).value(name, CROP_A)
            assert ok_gt_one == 2.5


def test_catalogue_value_check_precedence_order():
    # 1. Raw PLACEHOLDER + wrong unit + negative value -> read_value refusal (MISSING_INPUT) first
    ph_bad = {"p.json": _record("residue_carbon_fraction", CROP_A, -5.0, unit="wrong_unit")}
    res_ph = Catalogue(ph_bad).value("residue_carbon_fraction", CROP_A)
    assert isinstance(res_ph, InputMissing)
    assert res_ph.reason == "MISSING_INPUT"
    assert "the record is not read" in res_ph.detail

    # 2. Null value + wrong unit -> "holds no value" (MISSING_INPUT) before unit check
    null_bad = _unmark(
        {
            "n.json": _record(
                "residue_carbon_fraction",
                CROP_A,
                None,
                unit="wrong_unit",
                missing_reason=f"{MARK}: missing before unit",
            )
        }
    )
    res_null = Catalogue(null_bad).value("residue_carbon_fraction", CROP_A)
    assert isinstance(res_null, InputMissing)
    assert res_null.reason == "MISSING_INPUT"
    assert "the record holds no value: UNMARKED_TEST_ONLY: missing before unit" in res_null.detail

    # 3. Wrong unit + out-of-bounds value -> unit guard (NOT_COMPUTABLE) before bounds guard
    unit_and_bound = _unmark(
        {"ub.json": _record("residue_carbon_fraction", CROP_A, -5.0, unit="wrong_unit")}
    )
    res_ub = Catalogue(unit_and_bound).value("residue_carbon_fraction", CROP_A)
    assert isinstance(res_ub, InputMissing)
    assert res_ub.reason == "NOT_COMPUTABLE"
    assert "nothing is converted" in res_ub.detail


# =============================================================================
# 3. Missing / null / malformed / PLACEHOLDER reason propagation (D56, F3c, C3.3)
# =============================================================================


def test_d56_null_placeholder_and_malformed_record_reasons_and_f3c_blocking():
    # Raw PLACEHOLDER record refused
    ph = Catalogue({"ph.json": _record("rhizodeposit_carbon", CROP_A, 1.0)}).value(
        "rhizodeposit_carbon", CROP_A
    )
    assert isinstance(ph, InputMissing)
    assert ph.reason == "MISSING_INPUT"
    assert "PLACEHOLDER" in ph.detail

    # Same transcriber & checker refused by read_value
    same_person = _unmark(
        {
            "sp.json": _record(
                "rhizodeposit_carbon",
                CROP_A,
                1.0,
                extra={"transcribed_by": "person_x", "checked_by": "PERSON_X"},
            )
        }
    )
    sp_res = Catalogue(same_person).value("rhizodeposit_carbon", CROP_A)
    assert isinstance(sp_res, InputMissing)
    assert sp_res.reason == "MISSING_INPUT"
    assert "transcribed_by" in sp_res.detail

    # Non-finite NaN refused by read_value
    nan_cat = _unmark({"nan.json": _record("rhizodeposit_carbon", CROP_A, math.nan)})
    nan_res = Catalogue(nan_cat).value("rhizodeposit_carbon", CROP_A)
    assert isinstance(nan_res, InputMissing)
    assert nan_res.reason == "MISSING_INPUT"

    # F3c: any malformed id/scope anywhere blocks lookup, names sorted keys, and logs read_ids
    cat = _catalogue()
    cat["z_bad.json"] = {"id": "1bad", "scope": {}}
    cat["a_bad.json"] = {"id": "ok_id", "scope": {"unknown": "v"}}
    cat["m_bad.json"] = "not_a_dict"  # type: ignore[assignment]
    reader = Catalogue(cat)
    blocked = reader.value("rusle2_crop_yield", CROP_A)
    assert isinstance(blocked, InputMissing)
    assert blocked.reason == "MISSING_INPUT"
    assert "'a_bad.json', 'm_bad.json', 'z_bad.json'" in blocked.detail
    assert "F3c" in blocked.detail
    assert reader.read_ids == ["rusle2_crop_yield"]


def test_missing_null_and_not_computable_propagate_through_build_residue_ledger():
    # Null rhizodeposit_carbon and wrong-unit root_mass_at_harvest for CROP_A
    cat = _catalogue(
        **{
            f"rhizodeposit_carbon.{CROP_A}": _record(
                "rhizodeposit_carbon",
                CROP_A,
                None,
                missing_reason=f"{MARK}: rhizodeposit omitted",
            ),
            f"root_mass_at_harvest.{CROP_A}": _record(
                "root_mass_at_harvest", CROP_A, 12.0, unit="t ha-1"
            ),
        }
    )
    ledger = build_residue_ledger(_rotation(), _calendar(), _climate(), parameters=cat)
    c1_entries = [item for item in ledger.components if item.component_id == "c1"]
    assert c1_entries

    for entry in c1_entries:
        # Direct fields keep their exact Missing reason and detail
        assert entry.rhizodeposit_carbon.value is None
        assert entry.rhizodeposit_carbon.missing is not None
        assert entry.rhizodeposit_carbon.missing.reason == "MISSING_INPUT"
        assert "UNMARKED_TEST_ONLY: rhizodeposit omitted" in entry.rhizodeposit_carbon.missing.detail

        assert entry.root_mass.value is None
        assert entry.root_mass.missing is not None
        assert entry.root_mass.missing.reason == "NOT_COMPUTABLE"
        assert "nothing is converted" in entry.root_mass.missing.detail

        # Derived root_carbon wraps operand Missing into MISSING_INPUT naming operand (C3.3)
        assert entry.root_carbon.value is None
        assert entry.root_carbon.missing is not None
        assert entry.root_carbon.missing.reason == "MISSING_INPUT"
        assert "NOT_COMPUTABLE" in entry.root_carbon.missing.detail
        assert "root_mass_at_harvest" in entry.root_carbon.missing.detail

        # Independent aboveground fields for CROP_A stay computed
        assert entry.aboveground_carbon_retained.value is not None

    # Affected annual/monthly series have provenance=None when every year is missing
    rhizo_series = next(
        s for s in ledger.annual_carbon_inputs if s.quantity == f"{CROP_A}_grain_rhizodeposit_carbon"
    )
    assert rhizo_series.provenance is None
    assert rhizo_series.source is None
    assert rhizo_series.range_missing is None
    assert all(y.missing is not None and y.missing.reason == "MISSING_INPUT" for y in rhizo_series.years)

    # Unaffected annual series remain DERIVED with D147 source
    ag_series = next(
        s for s in ledger.annual_carbon_inputs if s.quantity == f"{CROP_A}_grain_aboveground_carbon_retained"
    )
    assert ag_series.provenance == "DERIVED"
    assert ag_series.source is not None and "D147" in ag_series.source


# =============================================================================
# 4. provisional / source attribution & Catalogue.read_ids
# =============================================================================


def test_catalogue_read_ids_and_ledger_source_provisional_and_assumption_attribution():
    cat = _catalogue()
    reader = Catalogue(cat)
    reader.value("rusle2_crop_yield", CROP_A)
    reader.value("rusle2_crop_yield", CROP_B)
    reader.value("root_mass_at_harvest", CROP_A)
    reader.value("rusle2_crop_yield", CROP_A)
    assert reader.read_ids == ["rusle2_crop_yield", "root_mass_at_harvest"]

    # ag_year_start.provisional True vs False must not alter values or attribution
    rot = _rotation(residue_a="removed", residue_b="incorporated")
    cli = _climate()
    ledger_prov = build_residue_ledger(
        rot, _calendar(provisional=True, end_source=None, assumption=True), cli, parameters=cat
    )
    ledger_final = build_residue_ledger(
        rot, _calendar(provisional=False, end_source=None, assumption=True), cli, parameters=cat
    )
    assert ledger_prov == ledger_final

    c1 = next(item for item in ledger_prov.components if item.component_id == "c1")
    c2 = next(item for item in ledger_prov.components if item.component_id == "c2")

    # Direct record attribution (C4.5) and derived formula attribution (D129 (c))
    assert c1.root_mass.provenance == "DERIVED"
    assert c1.root_mass.source is not None
    assert f"record root_mass_at_harvest of crop {CROP_A!r} (DECLARED, C4.5)" in c1.root_mass.source
    assert c1.root_mass.range_missing is not None
    assert c1.root_mass.range_missing.reason == "NOT_AVAILABLE"

    assert c1.aboveground_mass_produced.source is not None
    assert "aboveground_mass_produced = rusle2_residue_yield_ratio x rusle2_crop_yield" in c1.aboveground_mass_produced.source

    assert c2.aboveground_mass_exported.value == 0.0
    assert c2.aboveground_mass_exported.source is not None
    assert "declares its residue 'incorporated'" in c2.aboveground_mass_exported.source

    # Harvest date assumption mark and fallback source when calendar end.source is None
    assert c1.harvest.assumption is True
    assert c1.harvest.source is not None
    assert "the calendar (assumption mark)" in c1.harvest.source
    assert "D47" in c1.harvest.source

    # Monthly series source attribution (D221, D147, KG_PER_TONNE)
    monthly = ledger_prov.monthly_carbon_inputs[0]
    assert monthly.provenance == "DERIVED"
    assert monthly.unit == CARBON_INPUT_UNIT
    assert monthly.source is not None
    assert "D221" in monthly.source
    assert f"1 t = {KG_PER_TONNE} kg (D147)" in monthly.source


# =============================================================================
# 5. Determinism & purity (G1)
# =============================================================================


def test_determinism_under_catalogue_key_reordering_and_purity():
    cat = _catalogue()
    reversed_cat = {k: copy.deepcopy(cat[k]) for k in reversed(list(cat))}
    snapshot = copy.deepcopy(cat)

    rot = _rotation()
    cal = _calendar()
    cli = _climate()

    l1 = build_residue_ledger(rot, cal, cli, parameters=cat)
    l2 = build_residue_ledger(rot, cal, cli, parameters=cat)
    l3 = build_residue_ledger(rot, cal, cli, parameters=reversed_cat)
    assert l1 == l2 == l3
    assert cat == snapshot

    # Deterministic error detail ordering when multiple records are malformed
    bad_fwd = {"z.json": {"id": None, "scope": {}}, "a.json": {"id": 1, "scope": {}}}
    bad_rev = {"a.json": {"id": 1, "scope": {}}, "z.json": {"id": None, "scope": {}}}
    assert Catalogue(bad_fwd).value("rusle2_crop_yield", CROP_A) == Catalogue(bad_rev).value(
        "rusle2_crop_yield", CROP_A
    )
    assert sorted(RECORDS) == sorted(PLACEHOLDER_NUMBERS)
    assert CARBON_UNIT == "kg C ha-1"
    assert MASS_UNIT == "kg ha-1"
    assert DIMENSIONLESS == "dimensionless"
