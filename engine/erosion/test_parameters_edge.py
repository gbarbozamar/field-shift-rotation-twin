"""Unit & mutant-killing edge tests for ``engine/erosion/_parameters.py``
and the parameter-boundary behaviour of ``engine/erosion/soil_loss.py``.

Every record, unit string, crop name, date, and number in this file is a
PLACEHOLDER: no value of the science is written or claimed. Valid in-memory
catalogues replace ``PLACEHOLDER`` with ``UNMARKED_TEST_ONLY`` so
``params.catalogue.read_value`` accepts them while still verifying that raw
``PLACEHOLDER`` records are refused.

Run from the repository root:
``py -3.12 -m pytest engine/erosion/test_parameters_edge.py -q``
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing, SoilLossResults
from engine.erosion import _parameters as params_mod
from engine.erosion import soil_loss as ep1
from params.catalogue import check_catalogue

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
ONE_DAY = dt.timedelta(days=1)

START_MONTH = 7
CROP_A = "test_crop_alpha"
CROP_B = "test_crop_beta"
RAIN_PATTERN = (0.0, 4.44, 18.8, 0.0, 2.22, 11.1)

LEN_UNIT = f"{MARK}_len_unit"
HEIGHT_UNIT = f"{MARK}_height_unit"
MASS_UNIT = f"{MARK}_mass_unit"
YIELD_UNIT = f"{MARK}_yield_unit"
MONTHLY_UNIT = f"{MARK}_monthly_unit"
MM_PER_DAY = "mm day-1"


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
    pid: str,
    value: float | None,
    unit: str,
    scope: dict[str, str] | None = None,
    *,
    missing_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PLACEHOLDER catalogue record."""
    rec: dict[str, Any] = {
        "id": pid,
        "scope": dict(scope or {}),
        "value": value,
        "unit": unit,
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


def _load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"PLACEHOLDER_{name}.json").read_text("utf-8"))


def _climate(first: dt.date, last: dt.date) -> SiteClimate:
    doc = _load_example("site_climate")
    series = copy.deepcopy(
        next(s for s in doc["daily_series"] if s["quantity"] == "precipitation")
    )
    days = []
    cur = first
    idx = 0
    while cur <= last:
        days.append({"date": cur.isoformat(), "value": RAIN_PATTERN[idx % len(RAIN_PATTERN)]})
        cur += ONE_DAY
        idx += 1
    series.update(
        unit=MM_PER_DAY,
        start_date=first.isoformat(),
        end_date=last.isoformat(),
        days=days,
        source=f"{MARK}: edge test series",
    )
    doc["daily_series"] = [series]
    return SiteClimate.model_validate(doc)


def _soil(slope_percent: float = 2.0, length_val: float = 50.0) -> SiteSoilSlope:
    doc = _load_example("site_soil_slope")
    doc["slope_steepness"]["value"] = slope_percent
    doc["slope_steepness"]["unit"] = "percent"
    doc["slope_length"]["value"] = length_val
    doc["slope_length"]["unit"] = _unmark(LEN_UNIT)
    return SiteSoilSlope.model_validate(doc)


def _calendar(
    first: dt.date,
    last: dt.date,
    *,
    provisional: bool = True,
) -> RotationCalendar:
    doc = _load_example("rotation_calendar")
    template = copy.deepcopy(doc["components"][0])
    doc["ag_year_start"] = {
        "month": START_MONTH,
        "provisional": provisional,
        "provenance": "DECLARED",
        "source": f"{MARK}: edge test start month",
    }
    doc["start_date"] = first.isoformat()
    doc["end_date"] = last.isoformat()
    doc["feasibility"] = {"feasible": True, "violations": []}
    components = []
    for cid, crop, s_day, e_day in (
        ("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 1)),
        ("c2", CROP_B, dt.date(2002, 3, 1), dt.date(2002, 5, 20)),
    ):
        comp = copy.deepcopy(template)
        comp["component_id"] = cid
        comp["crop_id"] = crop
        comp["periods"] = []
        comp["start"] = {
            "date": s_day.isoformat(),
            "provenance": "DECLARED",
            "source": f"{MARK}: start",
        }
        comp["end"] = {
            "date": e_day.isoformat(),
            "provenance": "DECLARED",
            "source": f"{MARK}: end",
        }
        components.append(comp)
    doc["components"] = components
    return RotationCalendar.model_validate(doc)


def _site_unit(pid: str) -> str:
    accepted = ep1.ACCEPTED_UNITS
    return {
        ep1.R_ID: accepted.r,
        ep1.K_ID: accepted.k,
        ep1.C_ID: accepted.c,
        ep1.P_ID: accepted.p,
        ep1.R_EXPONENT_ID: "dimensionless",
        ep1.R_THRESHOLD_ID: MM_PER_DAY,
        ep1.S_BREAK_ID: "percent",
        ep1.LAMBDA_UNIT_ID: LEN_UNIT,
        ep1.FALL_HEIGHT_COEFFICIENT_ID: f"{HEIGHT_UNIT}-1",
        ep1.SURFACE_COVER_B_PER_PERCENT_ID: "percent-1",
        ep1.MASS_COVER_COEFFICIENT_ID: f"{MASS_UNIT}-1",
    }.get(pid, "dimensionless")


def _full_catalogue(*, unmarked: bool = True) -> dict[str, dict[str, Any]]:
    """Complete PLACEHOLDER catalogue covering main, computed-C, monthly, and daily routes."""
    cat: dict[str, dict[str, Any]] = {}
    all_site = tuple(
        dict.fromkeys(
            (*ep1.PARAMETER_IDS, *ep1.MONTHLY_EROSIVITY_IDS, *ep1.DAILY_ROUTE_PARAMETER_IDS)
        )
    )
    for idx, pid in enumerate(all_site, start=1):
        unit = MONTHLY_UNIT if pid in ep1.MONTHLY_EROSIVITY_IDS else _site_unit(pid)
        val = 1.11 if pid == ep1.R_EXPONENT_ID else (2.22 if pid == ep1.R_THRESHOLD_ID else 0.123 * idx)
        if pid == ep1.FALL_HEIGHT_COEFFICIENT_ID:
            val = 0.25
        elif pid == ep1.SURFACE_COVER_B_PER_PERCENT_ID:
            val = 0.03
        elif pid == ep1.MASS_COVER_COEFFICIENT_ID:
            val = 0.05
        cat[f"site/{pid}.json"] = _record(pid, val, unit, {})

    for crop in (CROP_A, CROP_B):
        cat[f"crops/{crop}.yield_ratio.json"] = _record(
            ep1.RESIDUE_YIELD_RATIO_ID, 0.5, "dimensionless", {"crop": crop}
        )
        cat[f"crops/{crop}.yield.json"] = _record(
            ep1.CROP_YIELD_ID, 100.0, MASS_UNIT, {"crop": crop}
        )
        cat[f"crops/{crop}.decay.json"] = _record(
            ep1.DECAY_COEFFICIENT_ID, 0.01, "day-1", {"crop": crop}
        )
        cat[f"crops/{crop}.alpha.json"] = _record(
            ep1.MASS_COVER_COEFFICIENT_ID, 0.05, f"{MASS_UNIT}-1", {"crop": crop}
        )
        cat[f"crops/{crop}.residue_mass.json"] = _record(
            ep1.RESIDUE_MASS_ID, 50.0, MASS_UNIT, {"crop": crop}
        )
        cat[f"crops/{crop}.canopy_legacy.json"] = _record(
            ep1.CANOPY_COVER_ID, 0.4, "dimensionless", {"crop": crop}
        )
        cat[f"crops/{crop}.height_legacy.json"] = _record(
            ep1.FALL_HEIGHT_ID, 0.4, HEIGHT_UNIT, {"crop": crop}
        )
        for day_n, cov, ht in ((0, 0.1, 0.1), (30, 0.75, 0.6)):
            stage = f"day_{day_n}"
            cat[f"crops/{crop}.{stage}.cover.json"] = _record(
                ep1.CANOPY_COVER_ID, cov, "dimensionless", {"crop": crop, "stage": stage}
            )
            cat[f"crops/{crop}.{stage}.height.json"] = _record(
                ep1.FALL_HEIGHT_ID, ht, HEIGHT_UNIT, {"crop": crop, "stage": stage}
            )

    cat["no_crop/cover.json"] = _record(
        ep1.CANOPY_COVER_ID, 0.0, "dimensionless", ep1.NO_CROP_SCOPE
    )
    cat["no_crop/height.json"] = _record(
        ep1.FALL_HEIGHT_ID, 0.0, HEIGHT_UNIT, ep1.NO_CROP_SCOPE
    )
    return _unmark(cat) if unmarked else cat


# =============================================================================
# 1. check_parameters / G5 checks
# =============================================================================


def test_g5_parameters_must_be_keyword_dict_of_str_to_dict():
    cal = _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()
    valid_rec = _unmark(_record("test_id", 1.0, "u"))

    for fn in (ep1.compute_soil_loss, ep1.compute_soil_loss_daily_index):
        with pytest.raises(TypeError, match="parameters"):
            fn(cal, cli, soil)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            fn(cal, cli, soil, {})  # type: ignore[misc]

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
            with pytest.raises(TypeError, match=r"parameters.*\(G5\)"):
                fn(cal, cli, soil, parameters=bad_container)  # type: ignore[arg-type]

        for bad_key in (1, None, b"a.json", ("a",), True):
            with pytest.raises(TypeError, match=r"parameters.*\(G5\)"):
                fn(cal, cli, soil, parameters={bad_key: valid_rec})  # type: ignore[dict-item]

        for bad_val in (None, [], (), MARK, 3.14, MappingProxyType(valid_rec)):
            with pytest.raises(TypeError, match=r"parameters.*\(G5\)"):
                fn(cal, cli, soil, parameters={"a.json": bad_val})  # type: ignore[dict-item]


def test_g5_wrong_model_types_and_mismatched_field_identifiers_raise():
    cal = _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()

    for bad_cal in (cal.model_dump(), cli, None):
        with pytest.raises(TypeError, match=r"calendar.*\(G5\)"):
            ep1.compute_soil_loss(bad_cal, cli, soil, parameters={})  # type: ignore[arg-type]
    for bad_cli in (cli.model_dump(), soil, None):
        with pytest.raises(TypeError, match=r"climate.*\(G5\)"):
            ep1.compute_soil_loss(cal, bad_cli, soil, parameters={})  # type: ignore[arg-type]
    for bad_soil in (soil.model_dump(), cal, None):
        with pytest.raises(TypeError, match=r"soil_slope.*\(G5\)"):
            ep1.compute_soil_loss(cal, cli, bad_soil, parameters={})  # type: ignore[arg-type]

    other_cli = cli.model_copy(update={"case_id": "other-case"})
    with pytest.raises(ValueError, match=r"case_id.*\(G5\)") as exc_case:
        ep1.compute_soil_loss(cal, other_cli, soil, parameters={})
    assert "other-case" not in str(exc_case.value)

    other_soil = soil.model_copy(update={"field_id": "other-field"})
    with pytest.raises(ValueError, match=r"field_id.*\(G5\)") as exc_field:
        ep1.compute_soil_loss(cal, cli, other_soil, parameters={})
    assert "other-field" not in str(exc_field.value)

    both = soil.model_copy(update={"case_id": "other-case", "field_id": "other-field"})
    with pytest.raises(ValueError, match=r"case_id.*field_id.*\(G5\)"):
        ep1.compute_soil_loss(cal, cli, both, parameters={})


def test_g5_catalogue_defects_never_raise_in_reader_or_entry_point():
    cal = _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()

    for defect_cat in (
        _full_catalogue(unmarked=False),  # raw PLACEHOLDER records
        {"bad_shape.json": {"id": None, "scope": {}}},
        {"bad_val.json": _unmark(_record(ep1.R_ID, "not_a_number", "u"))},  # type: ignore[arg-type]
    ):
        res = ep1.compute_soil_loss(cal, cli, soil, parameters=defect_cat)
        assert isinstance(res, SoilLossResults)
        assert all(item.missing is not None for item in res.annual)


# =============================================================================
# 2. Exact (id, scope) lookup, normalisation, duplicates, scope_words
# =============================================================================


def test_exact_id_and_scope_lookup_ignores_path_and_normalises_case_and_whitespace():
    cat = _unmark(
        {
            "unrelated/folder/any_name.json": _record(
                "RUSLE_K_FACTOR",
                2.5,
                "u_k",
                {"stage": "  Day_1  ", "crop": " Test_Crop "},
            )
        }
    )
    assert check_catalogue(cat) == []

    found = params_mod.read_parameter(
        cat, "rusle_k_factor", {"crop": "test_crop", "stage": "day_1"}
    )
    assert found == params_mod.Parameter(2.5, "u_k")


def test_exact_scope_does_not_fall_back_to_empty_narrower_or_wider_scope():
    cat = _unmark(
        {
            "empty.json": _record("test_p", 1.0, "u", {}),
            "crop_only.json": _record("test_p", 2.0, "u", {"crop": CROP_A}),
            "wider.json": _record(
                "test_p", 3.0, "u", {"crop": CROP_A, "region": "test_region"}
            ),
        }
    )
    assert check_catalogue(cat) == []

    # Exact matches find their own record only
    assert params_mod.read_parameter(cat, "test_p", {}).value == 1.0
    assert params_mod.read_parameter(cat, "test_p", {"crop": CROP_A}).value == 2.0
    assert (
        params_mod.read_parameter(
            cat, "test_p", {"crop": CROP_A, "region": "test_region"}
        ).value
        == 3.0
    )

    # Other crop or other scope key does NOT fall back to empty or narrower/wider
    for missing_scope in (
        {"crop": CROP_B},
        {"management": "no_crop"},
        {"crop": CROP_A, "stage": "day_0"},
        {"region": "test_region"},
    ):
        res = params_mod.read_parameter(cat, "test_p", missing_scope)
        assert isinstance(res.value, Missing)
        assert res.value.reason == "MISSING_INPUT"
        assert "has no record in parameters (D56)" in res.value.detail
        assert res.unit is None


def test_duplicate_id_and_scope_including_normalised_collision_is_missing_input():
    cat = _unmark(
        {
            "a.json": _record(
                "test_dup", 1.0, "u", {"crop": CROP_A, "stage": "day_1"}
            ),
            "b.json": _record(
                "TEST_DUP", 2.0, "u", {"stage": " Day_1 ", "crop": f" {CROP_A.upper()} "}
            ),
        }
    )
    res = params_mod.read_parameter(cat, "test_dup", {"crop": CROP_A, "stage": "day_1"})
    assert isinstance(res.value, Missing)
    assert res.value.reason == "MISSING_INPUT"
    assert "more than one record" in res.value.detail
    assert "(G3)" in res.value.detail
    assert res.unit is None


def test_scope_words_exact_rest_dedup_sorting_and_empty_catalogue():
    assert params_mod.scope_words({}, "pid", {"crop": CROP_A}, "stage", {"crop": CROP_A}) == []

    cat = _unmark(
        {
            "a.json": _record("pid", 1.0, "u", {"crop": CROP_A, "stage": "day_2"}),
            "b.json": _record("PID", 2.0, "u", {"stage": " Day_2 ", "crop": CROP_A}),
            "c.json": _record("pid", 3.0, "u", {"crop": CROP_A, "stage": "day_10"}),
            "d.json": _record("pid", 4.0, "u", {"crop": CROP_A, "stage": "day_0"}),
            "extra.json": _record(
                "pid", 5.0, "u", {"crop": CROP_A, "stage": "day_3", "region": "r"}
            ),
            "fewer.json": _record("pid", 6.0, "u", {"stage": "day_4"}),
            "other_id.json": _record("other", 7.0, "u", {"crop": CROP_A, "stage": "day_5"}),
            "other_crop.json": _record("pid", 8.0, "u", {"crop": CROP_B, "stage": "day_6"}),
        }
    )
    assert params_mod.scope_words(
        cat,
        "pid",
        {"crop": CROP_A},
        "stage",
        {"crop": CROP_A, "stage": "day_<N>"},
    ) == ["day_0", "day_10", "day_2"]

    with pytest.raises(ValueError):
        params_mod.scope_words(cat, "1bad_id", {"crop": CROP_A}, "stage", {})


# =============================================================================
# 3. Missing / null / malformed / PLACEHOLDER reason propagation (D56, F3c)
# =============================================================================


def test_d56_missing_null_placeholder_and_malformed_record_reasons():
    # 1. Missing record
    missing = params_mod.read_parameter({}, "test_missing", {"crop": CROP_A})
    assert isinstance(missing.value, Missing)
    assert missing.value.reason == "MISSING_INPUT"
    assert missing.value.detail == (
        f"parameter 'test_missing' with scope {params_mod.scope_text({'crop': CROP_A})} "
        "has no record in parameters (D56)"
    )
    assert missing.unit is None

    # 2. Null value preserves record["unit"] and repeats value_missing_reason
    null_cat = _unmark(
        {
            "n.json": _record(
                "test_null",
                None,
                "test_kept_unit",
                {"crop": CROP_A},
                missing_reason=f"{MARK}: deferred pending measurement",
            )
        }
    )
    null_res = params_mod.read_parameter(null_cat, "test_null", {"crop": CROP_A})
    assert isinstance(null_res.value, Missing)
    assert null_res.value.reason == "MISSING_INPUT"
    assert "has no value: UNMARKED_TEST_ONLY: deferred pending measurement" in null_res.value.detail
    assert null_res.unit == "test_kept_unit"

    # 3. Raw PLACEHOLDER record is refused by read_value -> MISSING_INPUT, unit=None
    ph_cat = {"ph.json": _record("test_ph", 4.2, "u", {})}
    ph_res = params_mod.read_parameter(ph_cat, "test_ph", {})
    assert isinstance(ph_res.value, Missing)
    assert ph_res.value.reason == "MISSING_INPUT"
    assert "read_value" in ph_res.value.detail
    assert "PLACEHOLDER" in ph_res.value.detail
    assert ph_res.unit is None

    # 4. Other read_value refusals (same transcriber/checker, out-of-range value, bool value)
    same_person = _unmark(
        {
            "sp.json": _record(
                "test_sp",
                1.0,
                "u",
                {},
                extra={"transcribed_by": "person_x", "checked_by": "PERSON_X"},
            )
        }
    )
    sp_res = params_mod.read_parameter(same_person, "test_sp", {})
    assert isinstance(sp_res.value, Missing)
    assert sp_res.value.reason == "MISSING_INPUT"
    assert "transcribed_by" in sp_res.value.detail
    assert sp_res.unit is None

    out_of_range = _unmark(
        {
            "oor.json": _record(
                "test_oor",
                9.9,
                "u",
                {},
                extra={
                    "range": {"low": 1.0, "high": 5.0, "basis": f"{MARK} range"},
                    "range_missing_reason": None,
                },
            )
        }
    )
    # Remove range_missing_reason so range is the only defect
    del out_of_range["oor.json"]["range_missing_reason"]
    oor_res = params_mod.read_parameter(out_of_range, "test_oor", {})
    assert isinstance(oor_res.value, Missing)
    assert oor_res.value.reason == "MISSING_INPUT"
    assert "outside its own range" in oor_res.value.detail
    assert oor_res.unit is None

    bool_cat = _unmark({"b.json": _record("test_bool", True, "u", {})})  # type: ignore[arg-type]
    bool_res = params_mod.read_parameter(bool_cat, "test_bool", {})
    assert isinstance(bool_res.value, Missing)
    assert bool_res.value.reason == "MISSING_INPUT"
    assert bool_res.unit is None


def test_f3c_any_malformed_id_or_scope_blocks_all_lookups_and_scope_words():
    valid_rec = _unmark(_record("valid_param", 5.0, "u", {"crop": CROP_A}))
    cat = {
        "valid.json": valid_rec,
        "z_bad_id.json": {"id": "123_invalid", "scope": {}},
        "a_bad_scope_key.json": {"id": "ok_id", "scope": {"unknown_key": "v"}},
        "m_not_dict.json": [],  # type: ignore[dict-item]
    }
    res = params_mod.read_parameter(cat, "valid_param", {"crop": CROP_A})
    assert isinstance(res.value, Missing)
    assert res.value.reason == "MISSING_INPUT"
    assert res.unit is None
    assert "'a_bad_scope_key.json', 'm_not_dict.json', 'z_bad_id.json'" in res.value.detail
    assert "F3c" in res.value.detail

    sw = params_mod.scope_words(
        cat, "valid_param", {"crop": CROP_A}, "stage", {"crop": CROP_A, "stage": "day_<N>"}
    )
    assert isinstance(sw, Missing)
    assert sw.reason == "MISSING_INPUT"
    assert "day_<N>" in sw.detail
    assert "'a_bad_scope_key.json', 'm_not_dict.json', 'z_bad_id.json'" in sw.detail


def test_d56_null_record_propagates_through_compute_soil_loss_and_fallback():
    cat = _full_catalogue()
    # 1. Null K record propagates its missing reason to annual and monthly results
    k_null_cat = dict(cat)
    k_null_cat[f"site/{ep1.K_ID}.json"] = _unmark(
        _record(
            ep1.K_ID,
            None,
            ep1.ACCEPTED_UNITS.k,
            {},
            missing_reason=f"{MARK}: K unavailable in test",
        )
    )
    cal = _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()

    res_k = ep1.compute_soil_loss(cal, cli, soil, parameters=k_null_cat)
    assert isinstance(res_k, SoilLossResults)
    assert res_k.annual[0].missing is not None
    assert res_k.annual[0].missing.reason == "MISSING_INPUT"
    assert "UNMARKED_TEST_ONLY: K unavailable in test" in res_k.annual[0].missing.detail
    assert res_k.monthly[0].missing is not None
    assert res_k.monthly[0].missing.reason == "MISSING_INPUT"
    assert "UNMARKED_TEST_ONLY: K unavailable in test" in res_k.monthly[0].missing.detail

    # 2. Null computed-C record triggers D125 declared-C fallback and names reason in source
    c_null_cat = dict(cat)
    c_null_cat[f"crops/{CROP_A}.yield.json"] = _unmark(
        _record(
            ep1.CROP_YIELD_ID,
            None,
            MASS_UNIT,
            {"crop": CROP_A},
            missing_reason=f"{MARK}: crop yield withheld",
        )
    )
    res_c = ep1.compute_soil_loss(cal, cli, soil, parameters=c_null_cat)
    assert isinstance(res_c, SoilLossResults)
    covered = [item for item in res_c.annual if item.value is not None]
    assert covered
    for item in covered:
        assert item.provenance == "DERIVED"
        assert item.assumption is False
        assert item.source is not None
        assert "PROPOSED fallback of brief #218" in item.source
        assert "DECLARED" in item.source and "D125" in item.source
        assert "UNMARKED_TEST_ONLY: crop yield withheld" in item.source
        assert f"'{ep1.C_ID}' with scope {{}}" in item.source


# =============================================================================
# 4. provisional / source attribution & ParameterReader tracking
# =============================================================================


def test_parameter_reader_caches_orders_and_forks_independently():
    cat = _full_catalogue()
    reader = params_mod.ParameterReader(cat)

    first = reader.read(ep1.K_ID, {})
    # Mutate backing dict after first read: cached result must still be returned
    cat[f"site/{ep1.K_ID}.json"] = _unmark(_record(ep1.K_ID, 999.0, ep1.ACCEPTED_UNITS.k))
    cached = reader.read(ep1.K_ID, {})
    assert cached == first
    assert reader.records_read() == [(ep1.K_ID, "{}")]

    # Reordered scope keys hit the same cache entry and do not duplicate records_read
    s1 = reader.read(ep1.CANOPY_COVER_ID, {"stage": "day_0", "crop": CROP_A})
    s2 = reader.read(ep1.CANOPY_COVER_ID, {"crop": CROP_A, "stage": "day_0"})
    assert s1 == s2
    assert reader.records_read() == [
        (ep1.K_ID, "{}"),
        (ep1.CANOPY_COVER_ID, f'{{"crop": "{CROP_A}", "stage": "day_0"}}'),
    ]

    # Missing lookups are still recorded in order
    reader.read("missing_param", {"crop": CROP_B})
    assert len(reader.records_read()) == 3

    # Fork isolation in both directions
    forked = reader.fork()
    assert forked.records_read() == reader.records_read()
    forked.read(ep1.P_ID, {})
    reader.read(ep1.R_ID, {})
    assert forked.records_read()[-1][0] == ep1.P_ID
    assert reader.records_read()[-1][0] == ep1.R_ID
    assert len(forked.records_read()) == 4
    assert len(reader.records_read()) == 4


def test_source_attribution_and_ag_year_provisional_invariance():
    cat = _full_catalogue()
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()

    res_true = ep1.compute_soil_loss(
        _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30), provisional=True),
        cli,
        soil,
        parameters=cat,
    )
    res_false = ep1.compute_soil_loss(
        _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30), provisional=False),
        cli,
        soil,
        parameters=cat,
    )
    assert res_true == res_false
    assert isinstance(res_true, SoilLossResults)

    annual_ok = [item for item in res_true.annual if item.value is not None]
    assert annual_ok
    for item in annual_ok:
        assert item.provenance == "DERIVED"
        assert item.assumption is False
        assert item.source is not None
        assert "engine.erosion.compute_soil_loss" in item.source
        assert "PROPOSED fallback of brief #218" not in item.source
        assert "records read for C:" in item.source
        assert f"'{ep1.R_ID}' with scope {{}}" in item.source
        assert f"'{ep1.CROP_YIELD_ID}' with scope {{\"crop\": \"{CROP_A}\"}}" in item.source

    monthly_ok = [item for item in res_true.monthly if item.value is not None]
    assert monthly_ok
    for item in monthly_ok:
        assert item.provenance == "DERIVED"
        assert item.assumption is False
        assert item.source is not None
        assert "records read for the month:" in item.source
        assert f"'{ep1.MONTHLY_EROSIVITY_IDS[0]}' with scope {{}}" in item.source

    daily_res = ep1.compute_soil_loss_daily_index(
        _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30), provisional=True),
        cli,
        soil,
        parameters=cat,
    )
    assert isinstance(daily_res, SoilLossResults)
    daily_ok = [item for item in daily_res.annual if item.value is not None]
    assert daily_ok
    assert daily_ok[0].source is not None
    assert "compute_soil_loss_daily_index" in daily_ok[0].source
    assert "parameter records read:" in daily_ok[0].source


# =============================================================================
# 5. Determinism & purity (G1)
# =============================================================================


def test_determinism_under_catalogue_key_reordering_and_purity():
    cat = _full_catalogue()
    reversed_cat = {k: copy.deepcopy(cat[k]) for k in reversed(list(cat))}
    snapshot = copy.deepcopy(cat)

    cal = _calendar(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    cli = _climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _soil()

    r1 = ep1.compute_soil_loss(cal, cli, soil, parameters=cat)
    r2 = ep1.compute_soil_loss(cal, cli, soil, parameters=cat)
    r3 = ep1.compute_soil_loss(cal, cli, soil, parameters=reversed_cat)
    assert r1 == r2 == r3
    assert cat == snapshot

    d1 = ep1.compute_soil_loss_daily_index(cal, cli, soil, parameters=cat)
    d2 = ep1.compute_soil_loss_daily_index(cal, cli, soil, parameters=reversed_cat)
    assert d1 == d2
    assert cat == snapshot

    # Deterministic error detail ordering when multiple records are malformed
    bad_forward = {"z.json": {"id": None, "scope": {}}, "a.json": {"id": 1, "scope": {}}}
    bad_reverse = {"a.json": {"id": 1, "scope": {}}, "z.json": {"id": None, "scope": {}}}
    assert params_mod.read_parameter(bad_forward, "x", {}) == params_mod.read_parameter(
        bad_reverse, "x", {}
    )
