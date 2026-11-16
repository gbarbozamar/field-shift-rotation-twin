"""Structural, provenance, and completeness invariants of the shipped catalogue.

Verifies the 205 signed records under ``params/records/`` directly against
``params/catalogue.py`` and the parameter lookup tables of EP1, EP3, EP4,
EP5 (AMG), and EP6 (RothC) for the two demonstration rotations of D128
(``web/src/data/demo_rotations_d128.json``).

Run from the repository root::

    py -3.12 -m pytest params/test_signed_catalogue_invariants.py -q
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from engine.amg import entry as ep5
from engine.erosion import soil_loss as ep1
from engine.residues import _parameters as ep4_params
from engine.rothc import entry as ep6
from engine.water import exposure as ep3
from params.catalogue import (
    CITATION_NEEDED,
    PLACEHOLDER_WORD,
    RECORDS_FOLDER,
    SCOPE_KEYS,
    WITHDRAWN_FOLDER,
    Missing,
    check_catalogue,
    check_layout,
    find_duplicates,
    find_placeholders,
    identity,
    is_placeholder,
    load_folder,
    parse_record_text,
    read_range,
    read_value,
)

PARAMS_DIR = Path(__file__).resolve().parent
RECORDS_DIR = PARAMS_DIR / RECORDS_FOLDER
WITHDRAWN_DIR = PARAMS_DIR / WITHDRAWN_FOLDER / "computed_c"
ROOT = PARAMS_DIR.parent
DEMO_ROTATIONS_PATH = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"

EXPECTED_TOTAL_RECORDS = 205
EXPECTED_TOP_EROSION_RECORDS = 27
EXPECTED_RESIDUE_RECORDS = 18
EXPECTED_EROSION_AND_RESIDUE_RECORDS = (
    EXPECTED_TOP_EROSION_RECORDS + EXPECTED_RESIDUE_RECORDS
)
EXPECTED_WATER_RECORDS = 110
EXPECTED_AMG_RECORDS = 20
EXPECTED_ROTHC_RECORDS = 30
EXPECTED_WITHDRAWN_RECORDS = 61

EXPECTED_SIGNED_EP4_IDS = frozenset(
    {
        "residue_carbon_fraction",
        "rhizodeposit_carbon",
        "root_carbon_fraction",
        "root_mass_at_harvest",
        "rusle2_crop_yield",
        "rusle2_residue_yield_ratio",
    }
)
EXPECTED_UNSIGNED_EP4_IDS = frozenset({"residue_removed_fraction"})

EXPECTED_ROTATION_B_MISSING_WATER_KEYS: frozenset[
    tuple[str, tuple[tuple[str, str], ...]]
] = frozenset()


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _catalogue_key(
    parameter_id: str, scope: tuple[tuple[str, str], ...] | dict[str, str]
) -> tuple[str, tuple[tuple[str, str], ...]]:
    return identity({"id": parameter_id, "scope": dict(scope)})


def _ep3_required_keys(
    crops: set[str],
) -> set[tuple[str, tuple[tuple[str, str], ...]]]:
    keys: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for pid in (*ep3.SITE_PARAMETERS, *ep3.FALLOW_SITE_PARAMETERS):
        keys.add((pid, ep3.SITE))
    for pid in (
        *ep3.FALLOW_PARAMETERS,
        *ep3.STAGE_PARAMETERS,
        *ep3.DAY_PARAMETERS,
    ):
        keys.add((pid, ep3.NO_CROP))
    for crop in sorted(crops):
        crop_scope = ((ep3.CROP_KEY, crop),)
        for pid in ep3.STAGE_PARAMETERS:
            for stage in ep3.STAGES:
                keys.add((pid, tuple(sorted((*crop_scope, (ep3.STAGE_KEY, stage))))))
        for pid in (*ep3.DAY_PARAMETERS, *ep3.CROP_PARAMETERS):
            keys.add((pid, crop_scope))
        for pid in ep3.FALLOW_COVER_PARAMETERS:
            keys.add((pid, tuple(sorted(ep3.fallow_scope(crop)))))
    return keys


@pytest.fixture(scope="module")
def shipped_records() -> dict[str, dict[str, Any]]:
    records, load_problems = load_folder(RECORDS_DIR)
    assert load_problems == []
    assert check_catalogue(records) == []
    return records


def test_catalogue_layout_and_domain_counts(
    shipped_records: dict[str, dict[str, Any]],
) -> None:
    assert check_layout(PARAMS_DIR) == []
    assert len(shipped_records) == EXPECTED_TOTAL_RECORDS

    subdirs = {path.name for path in RECORDS_DIR.iterdir() if path.is_dir()}
    assert subdirs == {"amg", "residues", "rothc", "water"}

    top_level = [name for name in shipped_records if "/" not in name]
    residues = [name for name in shipped_records if name.startswith("residues/")]
    water = [name for name in shipped_records if name.startswith("water/")]
    amg = [name for name in shipped_records if name.startswith("amg/")]
    rothc = [name for name in shipped_records if name.startswith("rothc/")]

    assert len(top_level) == EXPECTED_TOP_EROSION_RECORDS
    assert len(residues) == EXPECTED_RESIDUE_RECORDS
    assert len(top_level) + len(residues) == EXPECTED_EROSION_AND_RESIDUE_RECORDS
    assert len(water) == EXPECTED_WATER_RECORDS
    assert len(amg) == EXPECTED_AMG_RECORDS
    assert len(rothc) == EXPECTED_ROTHC_RECORDS
    assert (
        len(top_level) + len(residues) + len(water) + len(amg) + len(rothc)
        == len(shipped_records)
    )

    assert (RECORDS_DIR / "README.md").is_file()
    for rel_path, record in shipped_records.items():
        path = RECORDS_DIR / rel_path
        parsed = parse_record_text(path.read_text(encoding="utf-8"))
        assert parsed == record, rel_path
        param_id = record["id"]
        assert (
            path.name == f"{param_id}.json" or path.name.startswith(f"{param_id}.")
        ), rel_path


def test_catalogue_unique_identities_and_withdrawn_disjointness(
    shipped_records: dict[str, dict[str, Any]],
) -> None:
    assert find_duplicates(shipped_records) == []
    assert find_placeholders(shipped_records) == []

    identities = {identity(record) for record in shipped_records.values()}
    assert len(identities) == EXPECTED_TOTAL_RECORDS

    withdrawn, withdrawn_problems = load_folder(WITHDRAWN_DIR)
    assert withdrawn_problems == []
    assert check_catalogue(withdrawn) == []
    assert len(withdrawn) == EXPECTED_WITHDRAWN_RECORDS
    for name, record in withdrawn.items():
        assert identity(record) not in identities, name


def test_every_signed_record_provenance_citations_and_numeric_bounds(
    shipped_records: dict[str, dict[str, Any]],
) -> None:
    placeholder_cf = PLACEHOLDER_WORD.casefold()
    citation_needed_cf = _normalise(CITATION_NEEDED)

    for rel_path, record in shipped_records.items():
        assert not is_placeholder(record), rel_path

        checked_by = record["checked_by"]
        transcribed_by = record["transcribed_by"]
        for field_name, actor in (
            ("checked_by", checked_by),
            ("transcribed_by", transcribed_by),
        ):
            assert isinstance(actor, str) and actor.strip() != "", (rel_path, field_name)
            assert "@" not in actor, (rel_path, field_name)
            assert placeholder_cf not in actor.casefold(), (rel_path, field_name)
            assert citation_needed_cf not in _normalise(actor), (rel_path, field_name)
        assert _normalise(checked_by) != _normalise(transcribed_by), rel_path

        citation = record["citation"]
        assert isinstance(citation, dict), rel_path
        for cit_key in ("reference", "locator"):
            text = citation[cit_key]
            assert isinstance(text, str) and text.strip() != "", (rel_path, cit_key)
            assert placeholder_cf not in text.casefold(), (rel_path, cit_key)
            assert citation_needed_cf not in _normalise(text), (rel_path, cit_key)
        if "url" in citation:
            url = citation["url"]
            assert isinstance(url, str) and url.strip() != "", rel_path
            assert placeholder_cf not in url.casefold(), rel_path

        assert isinstance(record["unit"], str) and record["unit"].strip() != "", rel_path
        scope = record["scope"]
        assert isinstance(scope, dict), rel_path
        assert set(scope).issubset(SCOPE_KEYS), rel_path
        for scope_key, scope_val in scope.items():
            assert isinstance(scope_val, str) and scope_val.strip() != "", (
                rel_path,
                scope_key,
            )

        value = read_value(record)
        assert not isinstance(value, Missing), rel_path
        assert isinstance(value, float) and math.isfinite(value), rel_path

        rng = read_range(record)
        if isinstance(rng, Missing):
            assert rng.reason.strip() != "", rel_path
        else:
            low, high = rng
            assert math.isfinite(low) and math.isfinite(high), rel_path
            assert low <= value <= high, rel_path
            assert record["range"]["basis"].strip() != "", rel_path


def test_d128_rotations_ep1_ep3_ep4_key_completeness(
    shipped_records: dict[str, dict[str, Any]],
) -> None:
    identities = {identity(record) for record in shipped_records.values()}

    # EP1: main soil-loss route keys (empty scope) and soil-loss tolerance must be present.
    ep1_required = [
        _catalogue_key(pid, {})
        for pid in (*ep1.PARAMETER_IDS, *ep1.MONTHLY_EROSIVITY_IDS, "soil_loss_tolerance")
    ]
    assert [key for key in ep1_required if key not in identities] == []

    # Load D128 demo rotations from the canonical frontend data artifact.
    raw_rotations = json.loads(DEMO_ROTATIONS_PATH.read_text(encoding="utf-8"))
    crops_by_rotation = {
        entry["rotation_id"]: {comp["crop_id"] for comp in entry["components"]}
        for entry in raw_rotations
    }
    assert crops_by_rotation == {
        "soybean-winter-fallow": {"soybean"},
        "wheat-soybean-maize": {"wheat", "soybean", "maize"},
    }

    # EP3 Rotation A (soybean-winter-fallow): complete in shipped records.
    rot_a_ep3 = _ep3_required_keys(crops_by_rotation["soybean-winter-fallow"])
    rot_a_missing = {
        key for key in rot_a_ep3 if _catalogue_key(key[0], key[1]) not in identities
    }
    assert rot_a_missing == set()

    # EP3 Rotation B (wheat-soybean-maize): complete in shipped records.
    rot_b_ep3 = _ep3_required_keys(crops_by_rotation["wheat-soybean-maize"])
    rot_b_missing = {
        key for key in rot_b_ep3 if _catalogue_key(key[0], key[1]) not in identities
    }
    assert rot_b_missing == EXPECTED_ROTATION_B_MISSING_WATER_KEYS

    # EP4: 6 signed keys per D128 crop; only residue_removed_fraction remains unsigned.
    expected_unsigned_ep4 = set(ep4_params.RECORDS) - EXPECTED_SIGNED_EP4_IDS
    assert expected_unsigned_ep4 == EXPECTED_UNSIGNED_EP4_IDS
    for rotation_crops in crops_by_rotation.values():
        for crop in sorted(rotation_crops):
            present = {
                pid
                for pid in ep4_params.RECORDS
                if _catalogue_key(pid, {"crop": crop}) in identities
            }
            missing = set(ep4_params.RECORDS) - present
            assert present == EXPECTED_SIGNED_EP4_IDS, crop
            assert missing == expected_unsigned_ep4, crop


def test_amg_and_rothc_key_completeness(
    shipped_records: dict[str, dict[str, Any]],
) -> None:
    identities = {identity(record) for record in shipped_records.values()}
    raw_rotations = json.loads(DEMO_ROTATIONS_PATH.read_text(encoding="utf-8"))
    d128_crops = sorted(
        {
            comp["crop_id"]
            for entry in raw_rotations
            for comp in entry["components"]
        }
    )
    origins = [
        f"{crop}_{part}"
        for crop in d128_crops
        for part in ("aboveground", "belowground")
    ]

    # EP5 (AMG): 14 site/method constants (empty scope) + 6 origin humification coefficients.
    amg_humification_id = ep5.PARAMETERS["humification_coefficient"][0]
    amg_required = [
        _catalogue_key(pid, {})
        for name, (pid, _how) in ep5.PARAMETERS.items()
        if name != "humification_coefficient"
    ] + [
        _catalogue_key(amg_humification_id, {ep5.ORIGIN_SCOPE_KEY: origin})
        for origin in origins
    ]
    assert len(amg_required) == EXPECTED_AMG_RECORDS
    assert [key for key in amg_required if key not in identities] == []

    amg_records = {
        rel: rec for rel, rec in shipped_records.items() if rel.startswith("amg/")
    }
    assert len(amg_records) == EXPECTED_AMG_RECORDS
    assert {identity(rec) for rec in amg_records.values()} == set(amg_required)
    for rel, rec in amg_records.items():
        assert not is_placeholder(rec), rel
        assert rec["checked_by"].strip() != "", rel
        val = read_value(rec)
        assert isinstance(val, float) and math.isfinite(val), rel

    # EP6 (RothC): 24 site/method constants (empty scope) + 6 origin DPM:RPM ratios.
    rothc_ratio_id = ep6.INPUT_PARAMETERS["input_dpm_rpm_ratio"]
    rothc_required = [
        _catalogue_key(pid, {}) for pid, _how in ep6.PARAMETERS.values()
    ] + [
        _catalogue_key(rothc_ratio_id, {ep6.ORIGIN_SCOPE_KEY: origin})
        for origin in origins
    ]
    assert len(rothc_required) == EXPECTED_ROTHC_RECORDS
    assert [key for key in rothc_required if key not in identities] == []

    rothc_records = {
        rel: rec for rel, rec in shipped_records.items() if rel.startswith("rothc/")
    }
    assert len(rothc_records) == EXPECTED_ROTHC_RECORDS
    assert {identity(rec) for rec in rothc_records.values()} == set(rothc_required)
    for rel, rec in rothc_records.items():
        assert not is_placeholder(rec), rel
        assert rec["checked_by"].strip() != "", rel
        val = read_value(rec)
        assert isinstance(val, float) and math.isfinite(val), rel
