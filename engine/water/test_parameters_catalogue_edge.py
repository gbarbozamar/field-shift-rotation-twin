"""Edge and mutant-killing tests for ``engine/water/_parameters.py``.

Covers:
- ``check_parameters`` caller defects (container types, key/value types,
  non-dict mappings, error-message privacy);
- ``Scope`` exact matching / no-fallback precedence, key-order sorting,
  ``identity`` case/whitespace normalization, and duplicate collisions;
- null-value and missing-reason preservation (``MISSING_INPUT`` naming
  ``id`` and ``scope`` per D56);
- ``provisional`` and ``source`` propagation (catalogue isolation and
  EP3 / ``daily_reference_evapotranspiration`` behavior);
- repeated lookups (caching, first-day retention, ``problems_until``
  boundaries, grouping, and ordering);
- malformed record shapes (uncomparable ``id``/``scope`` vs ``read_value``
  refusals without poisoning unrelated parameters).

Every record built here uses synthetic ``PLACEHOLDER`` test data only (passed
in memory as an unmarked copy where ``read_value`` is expected to read it).
"""

from __future__ import annotations

import copy
import datetime as dt
import math
from collections import OrderedDict
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from contracts.results.models import Missing
from engine.water import _parameters
from engine.water import exposure as ep3
from engine.water import reference_et0
from engine.water import test_exposure as ep3_tests
from engine.water._parameters import (
    CANNOT_LOOK_UP,
    NO_RECORD,
    NO_VALUE,
    NOT_READ,
    Catalogue,
    check_parameters,
    describe,
    scope_text,
)

MARK = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
ONE_DAY = dt.timedelta(days=1)
_UNSET = object()


def _d(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def _unmarked(item: Any) -> Any:
    """Return an in-memory copy replacing PLACEHOLDER with UNMARKED_TEST_ONLY."""
    if isinstance(item, str):
        return item.replace(MARK, UNMARKED)
    if isinstance(item, dict):
        return {_unmarked(k): _unmarked(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_unmarked(v) for v in item]
    return item


def _placeholder_record(
    parameter_id: Any = "PLACEHOLDER_param",
    value: Any = 1.11,
    scope: Any = _UNSET,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a well-formed PLACEHOLDER record in params/README.md format."""
    copied_scope = {} if scope is _UNSET else copy.deepcopy(scope)
    if value is None:
        record: dict[str, Any] = {
            "id": parameter_id,
            "scope": copied_scope,
            "value": None,
            "value_missing_reason": "PLACEHOLDER reason: value absent",
            "unit": "PLACEHOLDER_unit",
            "range": None,
            "range_missing_reason": "PLACEHOLDER reason: range absent",
            "citation": None,
            "transcribed_by": "PLACEHOLDER_person_one",
            "checked_by": "PLACEHOLDER_person_two",
        }
    else:
        num = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
        low = num if isinstance(num, float) and math.isfinite(num) else 0.0
        record = {
            "id": parameter_id,
            "scope": copied_scope,
            "value": value,
            "unit": "PLACEHOLDER_unit",
            "range": {
                "low": low,
                "high": low,
                "basis": "PLACEHOLDER: synthetic test range",
            },
            "citation": {
                "reference": "PLACEHOLDER reference",
                "locator": "PLACEHOLDER locator",
            },
            "transcribed_by": "PLACEHOLDER_person_one",
            "checked_by": "PLACEHOLDER_person_two",
        }
    record.update(copy.deepcopy(overrides))
    return record


def _null_record(
    parameter_id: str = "PLACEHOLDER_param",
    scope: Any = _UNSET,
    reason: str = "PLACEHOLDER reason: no value",
    **overrides: Any,
) -> dict[str, Any]:
    return _placeholder_record(
        parameter_id=parameter_id,
        value=None,
        scope=scope,
        value_missing_reason=reason,
        **overrides,
    )


# --- 1. check_parameters caller defects --------------------------------------


class _DictSubclass(dict):
    """A dict subclass accepted by isinstance(..., dict)."""


def test_check_parameters_accepts_empty_valid_dict_subclasses_and_unvalidated_dicts():
    valid = _unmarked(_placeholder_record())
    assert check_parameters({}) is None
    assert check_parameters({"a.json": valid}) is None
    assert check_parameters(OrderedDict([("a.json", valid)])) is None
    assert check_parameters(_DictSubclass({"a.json": valid})) is None
    # check_parameters validates container shape dict[str, dict], not record schema.
    assert check_parameters({"broken.json": {"arbitrary": 1}}) is None


@pytest.mark.parametrize(
    ("bad", "expected_type_name"),
    [
        (None, "NoneType"),
        ([], "list"),
        ((), "tuple"),
        (set(), "set"),
        ("PLACEHOLDER", "str"),
        (123, "int"),
        (True, "bool"),
        (MappingProxyType({"a.json": {"id": "PLACEHOLDER"}}), "mappingproxy"),
    ],
    ids=["None", "list", "tuple", "set", "str", "int", "bool", "mappingproxy"],
)
def test_check_parameters_rejects_non_dict_containers_with_type_name_and_g5(
    bad: object, expected_type_name: str
):
    with pytest.raises(TypeError) as exc_info:
        check_parameters(bad)
    msg = str(exc_info.value)
    assert "parameters" in msg
    assert f"got {expected_type_name} (G5)" in msg


@pytest.mark.parametrize(
    "bad_key",
    [1, None, ("a.json",), Path("a.json"), True],
    ids=["int", "None", "tuple", "Path", "bool"],
)
def test_check_parameters_rejects_non_str_keys_alone_and_after_valid_entry(bad_key):
    valid = _unmarked(_placeholder_record())
    # Kills `not isinstance(key, str) and ...` and first-item-only mutants.
    for container in ({bad_key: valid}, {"ok.json": valid, bad_key: valid}):
        with pytest.raises(TypeError) as exc_info:
            check_parameters(container)
        msg = str(exc_info.value)
        assert "parameters" in msg
        assert "every key is the path of a record file and every value a record (G5)" in msg


@pytest.mark.parametrize(
    "bad_value",
    [None, [], (), "PLACEHOLDER", 123, True, MappingProxyType({"id": "PLACEHOLDER"})],
    ids=["None", "list", "tuple", "str", "int", "bool", "mappingproxy"],
)
def test_check_parameters_rejects_non_dict_values_alone_and_after_valid_entry(bad_value):
    valid = _unmarked(_placeholder_record())
    for container in (
        {"bad.json": bad_value},
        {"ok.json": valid, "bad.json": bad_value},
    ):
        with pytest.raises(TypeError) as exc_info:
            check_parameters(container)
        msg = str(exc_info.value)
        assert "parameters" in msg
        assert "every key is the path of a record file and every value a record (G5)" in msg


def test_check_parameters_error_message_never_repeats_key_or_record_contents():
    sentinel_key = "PLACEHOLDER_SECRET_PATH_TOKEN"
    sentinel_val = "PLACEHOLDER_SECRET_RECORD_TOKEN"
    with pytest.raises(TypeError) as exc_str:
        check_parameters(sentinel_val)
    assert sentinel_val not in str(exc_str.value)
    assert "parameters" in str(exc_str.value)

    with pytest.raises(TypeError) as exc_bad_val:
        check_parameters({sentinel_key: sentinel_val})
    assert sentinel_key not in str(exc_bad_val.value)
    assert sentinel_val not in str(exc_bad_val.value)
    assert "(G5)" in str(exc_bad_val.value)

    with pytest.raises(TypeError) as exc_bad_key:
        check_parameters({999: {"id": sentinel_val}})
    assert sentinel_val not in str(exc_bad_key.value)
    assert "999" not in str(exc_bad_key.value)


def test_water_entrypoints_reject_check_parameters_defects():
    valid = _unmarked(_placeholder_record())
    climate = ep3_tests.climate()
    calendar = ep3_tests.bare_calendar()
    soil = ep3_tests.soil()
    for bad in (MappingProxyType({"a.json": valid}), {1: valid}, {"a.json": []}):
        with pytest.raises(TypeError, match="parameters"):
            ep3.compute_water_deficit_exposure(
                calendar, climate, soil, parameters=bad  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="parameters"):
            reference_et0.daily_reference_evapotranspiration(
                climate, parameters=bad  # type: ignore[arg-type]
            )


# --- 2. Scope precedence, exact matching, normalization, and formatting ------


def test_scope_matching_is_exact_with_no_empty_subset_or_superset_fallback():
    day = _d("2001-09-15")
    crop = f"{UNMARKED}_crop"
    # Empty scope does NOT satisfy a crop scope.
    cat_empty = Catalogue(
        {"site.json": _unmarked(_placeholder_record("PLACEHOLDER_p", 2.22, {}))}
    )
    miss_crop = cat_empty.value(f"{UNMARKED}_p", (("crop", crop),), day)
    assert miss_crop == Missing(
        reason="MISSING_INPUT",
        detail=f'parameter \'{UNMARKED}_p\' with scope {{"crop": "{crop}"}}: {NO_RECORD}',
    )

    # Crop scope does NOT satisfy empty scope or narrower (crop + stage) scope.
    cat_crop = Catalogue(
        {"crop.json": _unmarked(_placeholder_record("PLACEHOLDER_p", 2.22, {"crop": crop}))}
    )
    miss_empty = cat_crop.value(f"{UNMARKED}_p", (), day)
    assert miss_empty == Missing(
        reason="MISSING_INPUT",
        detail=f"parameter '{UNMARKED}_p' with scope {{}}: {NO_RECORD}",
    )
    miss_narrower = cat_crop.value(
        f"{UNMARKED}_p", (("crop", crop), ("stage", "mid")), day
    )
    assert miss_narrower == Missing(
        reason="MISSING_INPUT",
        detail=(
            f'parameter \'{UNMARKED}_p\' with scope {{"crop": "{crop}", "stage": "mid"}}: '
            f"{NO_RECORD}"
        ),
    )

    # Narrower (crop + stage) scope does NOT satisfy wider (crop) scope.
    cat_stage = Catalogue(
        {
            "stage.json": _unmarked(
                _placeholder_record(
                    "PLACEHOLDER_p", 3.33, {"crop": crop, "stage": "mid"}
                )
            )
        }
    )
    miss_wider = cat_stage.value(f"{UNMARKED}_p", (("crop", crop),), day)
    assert miss_wider == Missing(
        reason="MISSING_INPUT",
        detail=f'parameter \'{UNMARKED}_p\' with scope {{"crop": "{crop}"}}: {NO_RECORD}',
    )

    # Different scope key with identical word never matches.
    cat_soil = Catalogue(
        {"soil.json": _unmarked(_placeholder_record("PLACEHOLDER_p", 4.44, {"soil": crop}))}
    )
    assert isinstance(cat_soil.value(f"{UNMARKED}_p", (("crop", crop),), day), Missing)
    assert cat_soil.value(f"{UNMARKED}_p", (("soil", crop),), day) == 4.44


def test_multiple_scopes_for_same_parameter_id_resolve_independently():
    day = _d("2001-09-15")
    crop = f"{UNMARKED}_crop"
    records = {
        "r0.json": _unmarked(_placeholder_record("PLACEHOLDER_p", 1.11, {})),
        "r1.json": _unmarked(_placeholder_record("PLACEHOLDER_p", 2.22, {"crop": crop})),
        "r2.json": _unmarked(
            _placeholder_record("PLACEHOLDER_p", 3.33, {"crop": crop, "stage": "mid"})
        ),
        "r3.json": _unmarked(
            _placeholder_record("PLACEHOLDER_p", 4.44, {"management": "no_crop"})
        ),
        "r4.json": _unmarked(
            _placeholder_record(
                "PLACEHOLDER_p", 5.55, {"crop": crop, "management": "no_crop"}
            )
        ),
    }
    cat = Catalogue(records)
    pid = f"{UNMARKED}_p"
    assert cat.value(pid, (), day) == 1.11
    assert cat.value(pid, (("crop", crop),), day) == 2.22
    assert cat.value(pid, (("crop", crop), ("stage", "mid")), day) == 3.33
    assert cat.value(pid, (("management", "no_crop"),), day) == 4.44
    assert cat.value(pid, (("crop", crop), ("management", "no_crop")), day) == 5.55
    assert cat.problems_until(day) == []


def test_scope_key_order_is_normalized_for_lookup_and_sorted_in_detail():
    day = _d("2001-09-15")
    crop = f"{UNMARKED}_crop"
    reversed_scope: _parameters.Scope = (("stage", "mid"), ("crop", crop))
    # Kills removing `sort_keys=True` in scope_text.
    assert scope_text(reversed_scope) == f'{{"crop": "{crop}", "stage": "mid"}}'
    assert (
        describe(f"{UNMARKED}_p", reversed_scope)
        == f'parameter \'{UNMARKED}_p\' with scope {{"crop": "{crop}", "stage": "mid"}}'
    )

    cat = Catalogue(
        {
            "rec.json": _unmarked(
                _placeholder_record(
                    "PLACEHOLDER_p", 6.66, {"stage": "mid", "crop": crop}
                )
            )
        }
    )
    assert cat.value(f"{UNMARKED}_p", (("crop", crop), ("stage", "mid")), day) == 6.66
    assert cat.value(f"{UNMARKED}_p", reversed_scope, day) == 6.66

    # Missing lookup with unsorted Scope still writes sorted JSON keys in detail.
    miss = cat.value(f"{UNMARKED}_missing", reversed_scope, day)
    assert isinstance(miss, Missing)
    assert miss.detail == (
        f'parameter \'{UNMARKED}_missing\' with scope {{"crop": "{crop}", "stage": "mid"}}: '
        f"{NO_RECORD}"
    )


def test_identity_normalizes_case_and_whitespace_and_detects_normalized_duplicates():
    day = _d("2001-09-15")
    cat = Catalogue(
        {
            "norm.json": _unmarked(
                _placeholder_record(
                    "PLACEHOLDER_Param",
                    7.77,
                    {"crop": "PLACEHOLDER  crop\tname"},
                )
            )
        }
    )
    looked_up_scope: _parameters.Scope = (("crop", f"  {UNMARKED.lower()} crop name "),)
    assert cat.value(f"{UNMARKED.lower()}_param", looked_up_scope, day) == 7.77

    # Missing lookup preserves caller's parameter_id and scope spelling in detail.
    absent = cat.value("Other_Param", looked_up_scope, day)
    assert isinstance(absent, Missing)
    assert "parameter 'Other_Param'" in absent.detail
    assert f"  {UNMARKED.lower()} crop name " in absent.detail

    # Two records colliding only after case/whitespace/key-order normalization -> NOT_READ.
    dup_cat = Catalogue(
        {
            "a.json": _unmarked(
                _placeholder_record(
                    "PLACEHOLDER_Param",
                    1.11,
                    {"stage": "Initial", "crop": "PLACEHOLDER  c1"},
                )
            ),
            "b.json": _unmarked(
                _placeholder_record(
                    f"{UNMARKED.lower()}_param",
                    2.22,
                    {"crop": f"{UNMARKED.lower()} c1 ", "stage": "\tinitial"},
                )
            ),
        }
    )
    dup = dup_cat.value(
        f"{UNMARKED}_param", (("crop", f"{UNMARKED.lower()} c1"), ("stage", "initial")), day
    )
    assert isinstance(dup, Missing)
    assert dup.reason == "MISSING_INPUT"
    assert NOT_READ in dup.detail
    assert "two records share this id and scope" in dup.detail


def test_invalid_lookup_id_or_scope_raises_value_error_when_catalogue_clean():
    day = _d("2001-09-15")
    cat = Catalogue({})
    for bad_id, bad_scope in (
        ("_leading", ()),
        ("1digit", ()),
        ("has-hyphen", ()),
        ("valid_id", (("unknown_key", "val"),)),
        ("valid_id", (("crop", "   \t"),)),
    ):
        with pytest.raises(ValueError):
            cat.value(bad_id, bad_scope, day)


# --- 3. Null-value / missing-reason preservation (MISSING_INPUT, D56) --------


def test_null_value_preserves_exact_reason_and_names_id_and_scope():
    day = _d("2001-09-15")
    exact_reason = f"  {UNMARKED}: verbatim (C3.2) reason;\tline  "
    crop = f"{UNMARKED}_crop"
    scope_dict = {"crop": crop, "stage": "late"}
    scope_tuple: _parameters.Scope = (("stage", "late"), ("crop", crop))
    cat = Catalogue(
        {
            "null.json": _unmarked(
                _null_record("PLACEHOLDER_null_param", scope_dict, reason=exact_reason)
            )
        }
    )
    got = cat.value(f"{UNMARKED}_null_param", scope_tuple, day)
    assert isinstance(got, Missing)
    assert got != 0
    assert got.reason == "MISSING_INPUT"
    expected_detail = (
        f'parameter \'{UNMARKED}_null_param\' with scope {{"crop": "{crop}", "stage": "late"}}: '
        f"{NO_VALUE}: {exact_reason}"
    )
    assert got.detail == expected_detail
    assert cat.problems_until(day) == [expected_detail]


def test_null_value_with_valid_range_and_citation_still_preserves_reason():
    day = _d("2001-09-15")
    reason = f"{UNMARKED}: value withheld despite range"
    rec = _unmarked(
        _null_record(
            "PLACEHOLDER_ranged_null",
            {},
            reason=reason,
            range={"low": 1.11, "high": 3.33, "basis": f"{UNMARKED} basis"},
            range_missing_reason=None,  # removed below
            citation={"reference": f"{UNMARKED} ref", "locator": f"{UNMARKED} loc"},
        )
    )
    del rec["range_missing_reason"]
    cat = Catalogue({"ranged_null.json": rec})
    got = cat.value(f"{UNMARKED}_ranged_null", (), day)
    assert got == Missing(
        reason="MISSING_INPUT",
        detail=f"parameter '{UNMARKED}_ranged_null' with scope {{}}: {NO_VALUE}: {reason}",
    )


@pytest.mark.parametrize(
    "bad_reason",
    [None, "", "   \t\n"],
    ids=["none", "empty", "whitespace"],
)
def test_null_value_without_nonempty_reason_is_not_read_not_no_value(bad_reason):
    day = _d("2001-09-15")
    rec = _unmarked(_null_record("PLACEHOLDER_bad_null", {}))
    if bad_reason is None:
        del rec["value_missing_reason"]
    else:
        rec["value_missing_reason"] = bad_reason
    cat = Catalogue({"bad_null.json": rec})
    got = cat.value(f"{UNMARKED}_bad_null", (), day)
    assert isinstance(got, Missing)
    assert got.reason == "MISSING_INPUT"
    assert NOT_READ in got.detail
    assert NO_VALUE not in got.detail


def test_null_value_with_placeholder_in_reason_is_not_read_not_no_value():
    day = _d("2001-09-15")
    rec = _unmarked(_null_record("PLACEHOLDER_marked_null", {}))
    # Restore PLACEHOLDER inside value_missing_reason only.
    rec["value_missing_reason"] = "PLACEHOLDER reason not unmarked"
    cat = Catalogue({"marked_null.json": rec})
    got = cat.value(f"{UNMARKED}_marked_null", (), day)
    assert isinstance(got, Missing)
    assert got.reason == "MISSING_INPUT"
    assert NOT_READ in got.detail
    assert NO_VALUE not in got.detail
    assert "PLACEHOLDER" in got.detail


@pytest.mark.parametrize(
    "raw_value",
    [0, 0.0, -0.0, -2, -3.33],
    ids=["int-zero", "float-zero", "neg-zero", "neg-int", "neg-float"],
)
def test_zero_and_negative_numeric_values_return_float_never_missing(raw_value):
    day = _d("2001-09-15")
    low = min(float(raw_value), 0.0)
    high = max(float(raw_value), 0.0)
    rec = _unmarked(
        _placeholder_record(
            "PLACEHOLDER_num",
            raw_value,
            {},
            range={"low": low, "high": high, "basis": f"{UNMARKED} basis"},
        )
    )
    cat = Catalogue({"num.json": rec})
    got = cat.value(f"{UNMARKED}_num", (), day)
    assert type(got) is float
    assert got == float(raw_value)
    assert cat.problems_until(day) == []


# --- 4. provisional & source propagation -------------------------------------


def test_catalogue_isolates_citation_and_provisional_note_from_value_and_missing():
    day = _d("2001-09-15")
    rec_num = _unmarked(
        _placeholder_record(
            "PLACEHOLDER_with_note",
            2,  # int in JSON -> float returned
            {},
            note="PLACEHOLDER provisional note",
            citation={
                "reference": "PLACEHOLDER reference",
                "locator": "PLACEHOLDER locator",
                "url": "https://example.invalid/PLACEHOLDER",
            },
        )
    )
    rec_null = _unmarked(
        _null_record(
            "PLACEHOLDER_null_with_note",
            {},
            reason="PLACEHOLDER missing reason",
            note="PLACEHOLDER provisional note that must not appear in detail",
            range_missing_reason="PLACEHOLDER range reason that must not appear",
        )
    )
    rec_cit_needed = _unmarked(
        _placeholder_record(
            "PLACEHOLDER_cit_needed",
            1.11,
            {},
            citation={"reference": "citation\tNEEDED", "locator": "PLACEHOLDER loc"},
        )
    )
    cat = Catalogue(
        {
            "num.json": rec_num,
            "null.json": rec_null,
            "cit_needed.json": rec_cit_needed,
        }
    )

    val = cat.value(f"{UNMARKED}_with_note", (), day)
    assert type(val) is float
    assert val == 2.0

    null_got = cat.value(f"{UNMARKED}_null_with_note", (), day)
    assert isinstance(null_got, Missing)
    assert "provisional note" not in null_got.detail
    assert "range reason" not in null_got.detail
    assert f"{UNMARKED} missing reason" in null_got.detail

    cit_got = cat.value(f"{UNMARKED}_cit_needed", (), day)
    assert isinstance(cit_got, Missing)
    assert cit_got.reason == "MISSING_INPUT"
    assert NOT_READ in cit_got.detail
    assert "CITATION NEEDED" in cit_got.detail


@pytest.mark.parametrize("provisional", [True, False], ids=["provisional-true", "provisional-false"])
def test_ep3_propagates_provisional_start_month_and_source_on_computed_years(provisional):
    cal_doc = ep3_tests.chain_calendar_document()
    cal_doc["ag_year_start"]["provisional"] = provisional
    calendar = ep3_tests.RotationCalendar.model_validate(cal_doc)

    result = ep3_tests.run(calendar_=calendar, parameters=ep3_tests.catalogue())
    assert result
    for item in result:
        assert item.missing is None
        assert isinstance(item.value, float)
        assert item.provenance == ep3.PROVENANCE
        assert item.source is not None
        assert item.source.startswith(ep3.WINDOW_LABEL)
        assert item.source.endswith(f"; {ep3.METHOD_FACTS}")
        assert item.range_missing == Missing(
            reason="NOT_AVAILABLE", detail=ep3.RANGE_NOT_BUILT
        )


def test_ep3_clears_provenance_and_source_and_propagates_null_reason_from_first_needed_year():
    calendar = ep3_tests.chain_calendar()
    second_comp = calendar.components[1]
    lengths = ep3_tests.placeholder_stage_lengths("crop-b")
    first_late_day = second_comp.start.date + ONE_DAY * int(
        sum(lengths[s] for s in ep3_tests.GROWTH_STAGES[:3])
    )

    custom_reason = f"PLACEHOLDER: late Kcb withheld for {second_comp.crop_id}"
    null_kcb = _placeholder_record(
        "basal_crop_coefficient",
        None,
        ep3_tests.scope_of("crop-b:end"),
        value_missing_reason=custom_reason,
    )
    parameters = ep3_tests.catalogue_with(
        {("basal_crop_coefficient", "crop-b:end"): null_kcb}
    )
    result = ep3_tests.run(calendar_=calendar, parameters=parameters)
    assert result

    computed = [item for item in result if item.missing is None]
    missing = [item for item in result if item.missing is not None]
    assert computed and missing
    for item in computed:
        assert ep3_tests.last_day_of(item.ag_year) < first_late_day
        assert item.provenance == ep3.PROVENANCE
        assert item.source is not None and item.source.startswith(ep3.WINDOW_LABEL)
    for item in missing:
        assert ep3_tests.last_day_of(item.ag_year) >= first_late_day
        assert item.value is None
        assert item.provenance is None
        assert item.source is None
        assert item.range is None
        assert item.range_missing is None
        assert item.missing.reason == "MISSING_INPUT"
        assert "parameter 'basal_crop_coefficient'" in item.missing.detail
        assert f"{NO_VALUE}: {custom_reason.replace(MARK, UNMARKED)}" in item.missing.detail


def test_ep3_clears_provenance_and_source_when_catalogue_has_malformed_record():
    broken = _unmarked(_placeholder_record("column_depth", 2.22, {}))
    del broken["scope"]
    parameters = ep3_tests.catalogue() | {"z_broken.json": broken}
    result = ep3_tests.run(parameters=parameters)
    assert result
    for item in result:
        assert item.value is None
        assert item.provenance is None
        assert item.source is None
        assert item.missing is not None
        assert item.missing.reason == "MISSING_INPUT"
        assert "'z_broken.json'" in item.missing.detail


def test_daily_reference_evapotranspiration_propagates_null_value_missing_reason():
    reason = "PLACEHOLDER: albedo not measured"
    null_albedo = _placeholder_record(
        "net_shortwave_albedo", None, {}, value_missing_reason=reason
    )
    parameters = ep3_tests.catalogue_with({("net_shortwave_albedo", None): null_albedo})
    days = reference_et0.daily_reference_evapotranspiration(
        ep3_tests.climate(), parameters=parameters
    )
    assert days
    for value in days.values():
        assert isinstance(value, Missing)
        assert value.reason == "MISSING_INPUT"
        assert "parameter 'net_shortwave_albedo' with scope {}" in value.detail
        assert f"{NO_VALUE}: {reason.replace(MARK, UNMARKED)}" in value.detail


# --- 5. Repeated lookups, caching, first-day retention, problems_until -------


def test_repeated_lookups_cache_answers_and_keep_first_day_needed(monkeypatch):
    calls: list[tuple[str, _parameters.Scope, dt.date]] = []
    real_read = Catalogue._read

    def spy_read(self, parameter_id, scope, day):
        calls.append((parameter_id, scope, day))
        return real_read(self, parameter_id, scope, day)

    monkeypatch.setattr(Catalogue, "_read", spy_read)

    cat = Catalogue(
        {
            "ok.json": _unmarked(_placeholder_record("PLACEHOLDER_ok", 1.11, {})),
            "null.json": _unmarked(_null_record("PLACEHOLDER_null", {})),
            "dup1.json": _unmarked(_placeholder_record("PLACEHOLDER_dup", 2.22, {})),
            "dup2.json": _unmarked(_placeholder_record("PLACEHOLDER_dup", 3.33, {})),
        }
    )

    d1 = _d("2001-07-01")
    d2 = _d("2001-08-15")
    d3 = _d("2002-06-30")

    v1 = cat.value(f"{UNMARKED}_ok", (), d1)
    v2 = cat.value(f"{UNMARKED}_ok", (), d3)
    assert v1 == 1.11 and v2 == 1.11

    m_absent_1 = cat.value(f"{UNMARKED}_absent", (), d1)
    m_absent_2 = cat.value(f"{UNMARKED}_absent", (), d3)
    assert m_absent_1 is m_absent_2

    m_null_1 = cat.value(f"{UNMARKED}_null", (), d2)
    m_null_2 = cat.value(f"{UNMARKED}_null", (), d3)
    assert m_null_1 is m_null_2

    m_dup_1 = cat.value(f"{UNMARKED}_dup", (), d2)
    m_dup_2 = cat.value(f"{UNMARKED}_dup", (), d3)
    assert m_dup_1 is m_dup_2

    # Same id under a different scope is a distinct cache key.
    m_scoped = cat.value(f"{UNMARKED}_ok", (("crop", f"{UNMARKED}_c"),), d3)
    assert isinstance(m_scoped, Missing)

    # _read was invoked exactly once per distinct (parameter_id, scope) key.
    assert len(calls) == 5

    # First-day retention: d1 problems appear on d1 and NOT on d1 - 1 day;
    # d2 problems appear on d2 and NOT on d1 (even though re-queried on d3).
    assert cat.problems_until(d1 - ONE_DAY) == []
    until_d1 = cat.problems_until(d1)
    assert any(f"'{UNMARKED}_absent'" in item for item in until_d1)
    assert not any(f"'{UNMARKED}_null'" in item for item in until_d1)
    assert not any(f"'{UNMARKED}_dup'" in item for item in until_d1)

    until_d2 = cat.problems_until(d2)
    assert any(f"'{UNMARKED}_absent'" in item for item in until_d2)
    assert any(f"'{UNMARKED}_null'" in item for item in until_d2)
    assert any(f"'{UNMARKED}_dup'" in item for item in until_d2)
    assert not any(f'"{UNMARKED}_c"' in item for item in until_d2)

    until_d3 = cat.problems_until(d3)
    assert any(f'"{UNMARKED}_c"' in item for item in until_d3)


def test_problems_until_boundary_grouping_and_ordering():
    day_before = _d("2002-06-29")
    last = _d("2002-06-30")
    day_after = _d("2002-07-01")
    crop = f"{UNMARKED}_crop"

    cat = Catalogue(
        {
            "null_b.json": _unmarked(
                _null_record("PLACEHOLDER_null_b", {}, reason="PLACEHOLDER b")
            ),
            "null_a.json": _unmarked(
                _null_record("PLACEHOLDER_null_a", {}, reason="PLACEHOLDER a")
            ),
            "bad_read.json": _placeholder_record("PLACEHOLDER_marked", 1.11, {}),
            "after_null.json": _unmarked(
                _null_record("PLACEHOLDER_after_null", {}, reason="PLACEHOLDER late")
            ),
        }
    )

    cat.value("z_missing", (("crop", crop),), day_before)
    cat.value("a_missing", (), last)
    cat.value("b_missing", (), last)
    cat.value("c_missing_after", (), day_after)
    cat.value(f"{UNMARKED}_null_b", (), last)
    cat.value(f"{UNMARKED}_null_a", (), day_before)
    cat.value("PLACEHOLDER_marked", (), last)
    cat.value(f"{UNMARKED}_after_null", (), day_after)

    items = cat.problems_until(last)
    # 2 NO_RECORD scope groups (sorted by scope tuple: () < (('crop', ...),)),
    # followed by 3 sorted `others` (PLACEHOLDER_marked, UNMARKED_null_a, UNMARKED_null_b).
    assert len(items) == 5
    assert items[0] == (
        "parameters with no record in parameters (D56), scope {}: "
        "'a_missing', 'b_missing'"
    )
    assert items[1] == (
        f'parameters with no record in parameters (D56), scope {{"crop": "{crop}"}}: '
        "'z_missing'"
    )
    assert items[2].startswith("parameter 'PLACEHOLDER_marked' with scope {}: ")
    assert items[3].startswith(f"parameter '{UNMARKED}_null_a' with scope {{}}: ")
    assert items[4].startswith(f"parameter '{UNMARKED}_null_b' with scope {{}}: ")
    assert not any("after" in item for item in items)


def test_problems_until_omits_cannot_look_up_header_when_only_after_last():
    last = _d("2002-06-30")
    day_after = _d("2002-07-01")
    broken = _unmarked(_placeholder_record("PLACEHOLDER_ok", 1.11, {}))
    del broken["id"]
    cat = Catalogue({"broken.json": broken})

    cat.value("later_param", (), day_after)
    # No lookup occurred on or before `last`, so summary header must NOT appear.
    assert cat.problems_until(last) == []

    until_after = cat.problems_until(day_after)
    assert len(until_after) == 2
    assert until_after[0].startswith("parameters that cannot be looked up: ")
    assert "'broken.json'" in until_after[0]
    assert until_after[1] == (
        "parameters that cannot be looked up, scope {}: 'later_param'"
    )


def test_catalogue_accepts_readonly_mapping_and_does_not_mutate_inputs():
    day = _d("2001-09-15")
    raw = {
        "a.json": _unmarked(_placeholder_record("PLACEHOLDER_a", 1.11, {})),
        "b.json": _unmarked(_null_record("PLACEHOLDER_b", {})),
    }
    snapshot = copy.deepcopy(raw)
    cat = Catalogue(MappingProxyType(raw))

    # Mutating raw after Catalogue creation does not affect indexed records.
    raw["c.json"] = _unmarked(_placeholder_record("PLACEHOLDER_c", 9.99, {}))
    assert cat.value(f"{UNMARKED}_a", (), day) == 1.11
    assert isinstance(cat.value(f"{UNMARKED}_b", (), day), Missing)
    assert isinstance(cat.value(f"{UNMARKED}_c", (), day), Missing)
    del raw["c.json"]
    assert raw == snapshot


# --- 6. Malformed record shapes ----------------------------------------------


@pytest.mark.parametrize(
    "bad_record",
    [
        None,
        [],
        "PLACEHOLDER",
        42,
        {k: v for k, v in _unmarked(_placeholder_record()).items() if k != "id"},
        _unmarked(_placeholder_record(id="")),
        _unmarked(_placeholder_record(id="   ")),
        _unmarked(_placeholder_record(id=123)),
        _unmarked(_placeholder_record(id=True)),
        _unmarked(_placeholder_record(id="_leading")),
        _unmarked(_placeholder_record(id="1digit")),
        _unmarked(_placeholder_record(id="has-hyphen")),
        _unmarked(_placeholder_record(id="has.dot")),
        _unmarked(_placeholder_record(id="trailing\n")),
        {k: v for k, v in _unmarked(_placeholder_record()).items() if k != "scope"},
        _unmarked(_placeholder_record(scope=None)),
        _unmarked(_placeholder_record(scope=[])),
        _unmarked(_placeholder_record(scope="crop")),
        _unmarked(_placeholder_record(scope=True)),
        _unmarked(_placeholder_record(scope={"unknown_key": f"{UNMARKED}_v"})),
        _unmarked(_placeholder_record(scope={1: f"{UNMARKED}_v"})),
        _unmarked(_placeholder_record(scope={"crop": ""})),
        _unmarked(_placeholder_record(scope={"crop": "   \t\n"})),
        _unmarked(_placeholder_record(scope={"crop": None})),
        _unmarked(_placeholder_record(scope={"crop": 123})),
        _unmarked(_placeholder_record(scope={"crop": True})),
    ],
    ids=[
        "record-none",
        "record-list",
        "record-str",
        "record-int",
        "missing-id",
        "empty-id",
        "blank-id",
        "int-id",
        "bool-id",
        "leading-underscore-id",
        "leading-digit-id",
        "hyphen-id",
        "dot-id",
        "newline-id",
        "missing-scope",
        "none-scope",
        "list-scope",
        "str-scope",
        "bool-scope",
        "unknown-scope-key",
        "non-str-scope-key",
        "empty-scope-val",
        "blank-scope-val",
        "none-scope-val",
        "int-scope-val",
        "bool-scope-val",
    ],
)
def test_malformed_id_or_scope_poisons_unrelated_valid_lookups(bad_record):
    day = _d("2001-09-15")
    cat = Catalogue(
        {
            "valid.json": _unmarked(_placeholder_record("PLACEHOLDER_good", 5.55, {})),
            "bad.json": bad_record,  # type: ignore[dict-item]
        }
    )
    got = cat.value(f"{UNMARKED}_good", (), day)
    assert isinstance(got, Missing)
    assert got.reason == "MISSING_INPUT"
    assert CANNOT_LOOK_UP in got.detail
    assert "'bad.json'" in got.detail
    assert "F3c" in got.detail
    assert "check_catalogue" in got.detail


def test_multiple_malformed_records_are_listed_in_sorted_key_order():
    day = _d("2001-09-15")
    cat = Catalogue(
        {
            "z_bad.json": {"scope": {}},
            "a_bad.json": {"id": "PLACEHOLDER_x"},
            "m_bad.json": None,  # type: ignore[dict-item]
        }
    )
    # Kills removing sorted(...) in Catalogue.__init__.
    text = cat.malformed_text()
    assert "'a_bad.json', 'm_bad.json', 'z_bad.json'" in text
    got = cat.value("any_param", (), day)
    assert isinstance(got, Missing)
    assert "'a_bad.json', 'm_bad.json', 'z_bad.json'" in got.detail


def _unreadable_variants() -> list[tuple[str, dict[str, Any]]]:
    base = _unmarked(_placeholder_record("PLACEHOLDER_bad", 2.22, {}))

    def without(field: str) -> dict[str, Any]:
        rec = copy.deepcopy(base)
        del rec[field]
        return rec

    def with_update(**changes: Any) -> dict[str, Any]:
        rec = copy.deepcopy(base)
        rec.update(changes)
        return rec

    variants: list[tuple[str, dict[str, Any]]] = [
        ("placeholder-unit", with_update(unit="PLACEHOLDER_unit")),
        ("placeholder-mixed-case-note", with_update(note="nested pLaCeHoLdEr")),
        (
            "placeholder-nested-unknown",
            with_update(extra=[1, {"k": "PLACEHOLDER_nested"}]),
        ),
        ("unknown-field", with_update(extra=f"{UNMARKED}_extra")),
        ("bool-true-value", with_update(value=True)),
        ("bool-false-value", with_update(value=False)),
        ("str-value", with_update(value="2.22")),
        ("nan-value", with_update(value=math.nan)),
        ("inf-value", with_update(value=math.inf)),
        ("neg-inf-value", with_update(value=-math.inf)),
        ("unrepresentable-pos-int", with_update(value=2**53 + 1)),
        ("unrepresentable-neg-int", with_update(value=-(2**53) - 1)),
        (
            "value-with-missing-reason",
            with_update(value_missing_reason=f"{UNMARKED} extra"),
        ),
        ("value-with-null-missing-reason", with_update(value_missing_reason=None)),
        (
            "range-low-gt-high",
            with_update(range={"low": 5.0, "high": 1.0, "basis": f"{UNMARKED}"}),
        ),
        (
            "value-outside-range",
            with_update(
                value=9.99,
                range={"low": 1.0, "high": 3.0, "basis": f"{UNMARKED}"},
            ),
        ),
        ("range-null-without-reason", with_update(range=None)),
        (
            "range-object-with-missing-reason",
            with_update(range_missing_reason=f"{UNMARKED} extra"),
        ),
        ("citation-null-with-value", with_update(citation=None)),
        (
            "citation-needed",
            with_update(
                citation={"reference": "citation\tneeded", "locator": f"{UNMARKED}"}
            ),
        ),
        (
            "same-person-normalized",
            with_update(
                transcribed_by=f"{UNMARKED}\tPerson",
                checked_by=f"{UNMARKED.lower()}  person ",
            ),
        ),
    ]
    for missing_field in ("unit", "value", "range", "citation", "transcribed_by", "checked_by"):
        variants.append((f"missing-{missing_field}", without(missing_field)))
    return variants


@pytest.mark.parametrize(
    ("label", "bad_record"),
    _unreadable_variants(),
    ids=[label for label, _ in _unreadable_variants()],
)
def test_well_formed_identity_but_unreadable_record_returns_not_read_only_for_itself(
    label: str, bad_record: dict[str, Any]
):
    day = _d("2001-09-15")
    cat = Catalogue(
        {
            "bad.json": bad_record,
            "sibling.json": _unmarked(
                _placeholder_record("PLACEHOLDER_sibling", 8.88, {})
            ),
        }
    )
    got_bad = cat.value(f"{UNMARKED}_bad", (), day)
    assert isinstance(got_bad, Missing), label
    assert got_bad.reason == "MISSING_INPUT"
    assert f"parameter '{UNMARKED}_bad' with scope {{}}: {NOT_READ}: " in got_bad.detail

    # Unrelated valid parameter in the same catalogue is unaffected.
    assert cat.value(f"{UNMARKED}_sibling", (), day) == 8.88
