"""Targeted mutant-killing tests for the erosion core modules.

Covers boundary, relational, missing-reason, unit-guard, fallback, and
non-finite clamping/guard paths in ``engine/erosion/ls.py``,
``equation.py``, ``_parameters.py``, and ``soil_loss.py``.

Every coefficient, unit string, date, and value in this file is a
PLACEHOLDER: no value of the science is written or claimed.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import Missing as ResultMissing
from contracts.results.models import SoilLossResults
from engine.calendar.repeat import RepeatedComponent, RepeatedRotation
from engine.erosion import _parameters as params_mod
from engine.erosion import equation, ls
from engine.erosion import soil_loss as module
from params.catalogue import check_catalogue

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"

WORD = "PLACEHOLDER"
ONE_DAY = dt.timedelta(days=1)

# PLACEHOLDER equation fixtures
EQ_UNITS = equation.AcceptedUnits(
    r="PLACEHOLDER_unit_r",
    k="PLACEHOLDER_unit_k",
    ls="PLACEHOLDER_unit_ls",
    c="PLACEHOLDER_unit_c",
    p="PLACEHOLDER_unit_p",
)
EQ_NUMBERS = {"r": 2.0, "k": 3.0, "ls": 5.0, "c": 7.0, "p": 11.0}
EQ_GUARD = "NOT_APPLICABLE"

# PLACEHOLDER ls fixtures
LS_STEEPNESS = {
    "s_break": 55.0,
    "a1": 11.0,
    "a2": 22.0,
    "a3": 33.0,
    "a4": 44.0,
}
LS_LENGTH = {
    "lambda_unit": 66.0,
    "b1": 0.11,
    "b2": 2.2,
    "b3": 3.3,
    "b4": 4.4,
}
LS_UNIT = "PLACEHOLDER_len_unit"

# PLACEHOLDER soil_loss catalogue & fixtures
START_MONTH = 7
AG_YEAR_0 = 2001
CROP_SOY = "UNMARKED_TEST_ONLY_soy"
CROP_WHEAT = "UNMARKED_TEST_ONLY_wheat"
CROP_MAIZE = "UNMARKED_TEST_ONLY_maize"
LEN_UNIT = "UNMARKED_TEST_ONLY_len"
HEIGHT_UNIT = "UNMARKED_TEST_ONLY_height"
MASS_UNIT = "UNMARKED_TEST_ONLY_mass"
YIELD_UNIT = "UNMARKED_TEST_ONLY_yield"
MONTHLY_UNIT = "UNMARKED_TEST_ONLY_monthly"
MM_PER_DAY = "mm day-1"
RAIN_SEQ = (0.0, 5.55, 33.3, 0.0, 1.11, 22.2, 0.0, 44.4, 2.22)


def _unmarked(item: Any) -> Any:
    """Replace PLACEHOLDER markers in an in-memory test structure."""
    if isinstance(item, str):
        return item.replace(WORD, "UNMARKED_TEST_ONLY")
    if isinstance(item, dict):
        return {_unmarked(k): _unmarked(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_unmarked(v) for v in item]
    return item


def _load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"PLACEHOLDER_{name}.json").read_text("utf-8"))


def _record(
    pid: str,
    value: float | None,
    unit: str,
    scope: dict[str, str] | None = None,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": pid,
        "scope": dict(scope or {}),
        "value": value,
        "unit": unit,
        "range": None,
        "range_missing_reason": "UNMARKED_TEST_ONLY: no range",
        "citation": {
            "reference": "UNMARKED_TEST_ONLY reference",
            "locator": "UNMARKED_TEST_ONLY locator",
        },
        "transcribed_by": "UNMARKED_TEST_ONLY_p1",
        "checked_by": "UNMARKED_TEST_ONLY_p2",
    }
    if value is None:
        rec["value_missing_reason"] = missing_reason or "UNMARKED_TEST_ONLY: missing"
    return rec


def _site_values() -> dict[str, float]:
    chosen = {
        module.R_EXPONENT_ID: 1.11,
        module.R_THRESHOLD_ID: 2.22,
        module.FALL_HEIGHT_COEFFICIENT_ID: 0.333,
        module.SURFACE_COVER_B_PER_PERCENT_ID: 0.00666,
        module.MASS_COVER_COEFFICIENT_ID: 0.222,
    }
    ids = tuple(
        dict.fromkeys(
            (
                *module.PARAMETER_IDS,
                *module.MONTHLY_EROSIVITY_IDS,
                *module.DAILY_ROUTE_PARAMETER_IDS,
            )
        )
    )
    return {pid: chosen.get(pid, 12.5 + idx) for idx, pid in enumerate(ids)}


def _site_unit(pid: str) -> str:
    accepted = module.ACCEPTED_UNITS
    return {
        module.R_ID: accepted.r,
        module.C_ID: accepted.c,
        **dict.fromkeys(module.MONTHLY_EROSIVITY_IDS, MONTHLY_UNIT),
        module.R_EXPONENT_ID: module.DIMENSIONLESS,
        module.R_THRESHOLD_ID: MM_PER_DAY,
        module.K_ID: accepted.k,
        module.P_ID: accepted.p,
        module.S_BREAK_ID: ls.SlopeUnit.PERCENT.value,
        module.LAMBDA_UNIT_ID: LEN_UNIT,
        module.FALL_HEIGHT_COEFFICIENT_ID: f"{HEIGHT_UNIT}-1",
        module.SURFACE_COVER_B_PER_PERCENT_ID: f"{module.PERCENT}-1",
        module.MASS_COVER_COEFFICIENT_ID: f"({MASS_UNIT})-1",
    }.get(pid, "UNMARKED_TEST_ONLY_unit")


def _base_catalogue(*leave_out: str) -> dict[str, dict[str, Any]]:
    """Catalogue covering site records and daily-route crop records."""
    vals = _site_values()
    cat: dict[str, dict[str, Any]] = {
        f"{pid}.json": _record(pid, val, _site_unit(pid))
        for pid, val in vals.items()
        if pid not in leave_out
    }
    crop_defs = {
        CROP_SOY: {"crop": CROP_SOY},
        CROP_WHEAT: {"crop": CROP_WHEAT},
        CROP_MAIZE: {"crop": CROP_MAIZE},
        "no_crop": dict(module.NO_CROP_SCOPE),
    }
    for word, scope in crop_defs.items():
        cat[f"cc.{word}.json"] = _record(
            module.CANOPY_COVER_ID, 0.333, module.DIMENSIONLESS, scope
        )
        cat[f"fh.{word}.json"] = _record(
            module.FALL_HEIGHT_ID, 1.11, HEIGHT_UNIT, scope
        )
    for crop in (CROP_SOY, CROP_WHEAT, CROP_MAIZE):
        scope = {"crop": crop}
        cat[f"rm.{crop}.json"] = _record(module.RESIDUE_MASS_ID, 5.55, MASS_UNIT, scope)
        cat[f"dc.{crop}.json"] = _record(
            module.DECAY_COEFFICIENT_ID, 0.0222, f"{module.DAY}-1", scope
        )
    assert check_catalogue(cat) == []
    return cat


def _main_c_catalogue(
    *leave_out_keys: str, stage_days: tuple[int, ...] = (11, 22)
) -> dict[str, dict[str, Any]]:
    """Catalogue with computed-C records for CROP_SOY, CROP_WHEAT, CROP_MAIZE."""
    cat = _base_catalogue()
    for crop in (CROP_SOY, CROP_WHEAT, CROP_MAIZE):
        for idx, day_num in enumerate(stage_days):
            st_scope = {"crop": crop, "stage": f"day_{day_num}"}
            cat[f"cc.{crop}.d{day_num}.json"] = _record(
                module.CANOPY_COVER_ID,
                0.222 + 0.111 * idx,
                module.DIMENSIONLESS,
                st_scope,
            )
            cat[f"fh.{crop}.d{day_num}.json"] = _record(
                module.FALL_HEIGHT_ID, 1.11 + idx, HEIGHT_UNIT, st_scope
            )
        scope = {"crop": crop}
        cat[f"ryr.{crop}.json"] = _record(
            module.RESIDUE_YIELD_RATIO_ID, 1.11, module.DIMENSIONLESS, scope
        )
        yield_unit = MASS_UNIT if crop == CROP_MAIZE else YIELD_UNIT
        cat[f"cy.{crop}.json"] = _record(module.CROP_YIELD_ID, 4.44, yield_unit, scope)
        cat[f"mc.{crop}.json"] = _record(
            module.MASS_COVER_COEFFICIENT_ID, 0.0444, f"({MASS_UNIT})-1", scope
        )
    cat[f"{module.YIELD_CONVERSION_ID}.json"] = _record(
        module.YIELD_CONVERSION_ID, 0.777, f"{MASS_UNIT} per {YIELD_UNIT}"
    )
    for k in leave_out_keys:
        cat.pop(k, None)
    assert check_catalogue(cat) == []
    return cat


def _soil(
    slope_val: float | None = 2.0,
    slope_unit: str = ls.SlopeUnit.PERCENT.value,
    length_val: float | None = 77.0,
    length_unit: str = LEN_UNIT,
) -> SiteSoilSlope:
    doc = _load_example("site_soil_slope")
    doc["slope_steepness"]["unit"] = slope_unit
    doc["slope_length"]["unit"] = length_unit
    if slope_val is not None:
        doc["slope_steepness"]["value"] = slope_val
        doc["slope_steepness"]["range"] = {
            "low": min(1.0, slope_val),
            "high": max(3.0, slope_val),
            "kind": "PLACEHOLDER_range_kind",
        }
    if length_val is not None:
        doc["slope_length"]["value"] = length_val
    return SiteSoilSlope.model_validate(doc)


def _climate(first: dt.date, last: dt.date) -> SiteClimate:
    doc = _load_example("site_climate")
    series = copy.deepcopy(
        next(s for s in doc["daily_series"] if s["quantity"] == "precipitation")
    )
    days = []
    cur = first
    pos = 0
    while cur <= last:
        days.append({"date": cur.isoformat(), "value": RAIN_SEQ[pos % len(RAIN_SEQ)]})
        cur += ONE_DAY
        pos += 1
    series.update(
        unit=MM_PER_DAY,
        start_date=first.isoformat(),
        end_date=last.isoformat(),
        days=days,
        source="PLACEHOLDER: mutant test series",
    )
    doc["daily_series"] = [series]
    return SiteClimate.model_validate(doc)


def _component_dict(
    cid: str,
    crop_id: str,
    start: dt.date | None,
    end: dt.date | None,
) -> dict[str, Any]:
    template = copy.deepcopy(_load_example("rotation_calendar")["components"][0])
    template["component_id"] = cid
    template["crop_id"] = crop_id
    template["periods"] = []
    if start is None:
        template["start"] = {
            "date": None,
            "missing": {
                "reason": "NOT_DECLARED",
                "detail": "PLACEHOLDER: missing start",
            },
        }
    else:
        template["start"] = {
            "date": start.isoformat(),
            "provenance": "DECLARED",
            "source": "PLACEHOLDER: test start",
        }
    if end is None:
        template["end"] = {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER: missing end"},
        }
    else:
        template["end"] = {
            "date": end.isoformat(),
            "provenance": "DECLARED",
            "source": "PLACEHOLDER: test end",
        }
    return template


def _calendar(
    start: dt.date,
    end: dt.date,
    components: list[tuple[str, str, dt.date | None, dt.date | None]],
) -> RotationCalendar:
    doc = _load_example("rotation_calendar")
    doc["ag_year_start"]["month"] = START_MONTH
    doc["start_date"] = start.isoformat()
    doc["end_date"] = end.isoformat()
    doc["components"] = [
        _component_dict(cid, crop, s, e) for cid, crop, s, e in components
    ]
    return RotationCalendar.model_validate(doc)


def _eq_factors(**overrides: equation.Factor) -> dict[str, equation.Factor]:
    base = {
        name: equation.Factor(value=EQ_NUMBERS[name], unit=getattr(EQ_UNITS, name))
        for name in equation.FACTOR_NAMES
    }
    base.update(overrides)
    return base


def _ls_steepness(**overrides: Any) -> float | ResultMissing:
    args: dict[str, Any] = {
        "slope_steepness": 7.0,
        "slope_unit": ls.SlopeUnit.PERCENT,
        "s_break_unit": ls.SlopeUnit.PERCENT,
        **LS_STEEPNESS,
    }
    args.update(overrides)
    return ls.slope_steepness_factor(**args)


def _ls_length(**overrides: Any) -> float | ResultMissing:
    args: dict[str, Any] = {
        "slope_length": 77.0,
        "slope_length_unit": LS_UNIT,
        "lambda_unit_unit": LS_UNIT,
        "slope_steepness": 7.0,
        "slope_unit": ls.SlopeUnit.PERCENT,
        **LS_LENGTH,
    }
    args.update(overrides)
    return ls.slope_length_factor(**args)


# =============================================================================
# engine/erosion/ls.py mutants
# =============================================================================


def test_ls_missing_without_detail_omits_none_colon_text():
    """Missing arguments with detail=None must not append ': None' to detail."""
    res_s = _ls_steepness(
        slope_steepness=InputMissing(reason="NOT_DECLARED", detail=None),
        a2=ResultMissing(reason="NO_COVERAGE", detail="PLACEHOLDER reason"),
    )
    assert isinstance(res_s, ResultMissing)
    assert res_s.reason == "MISSING_INPUT"
    assert "None" not in res_s.detail
    assert "PLACEHOLDER reason" in res_s.detail

    res_l = _ls_length(
        lambda_unit=InputMissing(reason="NOT_DECLARED", detail=None),
    )
    assert isinstance(res_l, ResultMissing)
    assert res_l.reason == "MISSING_INPUT"
    assert "None" not in res_l.detail


def test_ls_missing_and_non_finite_precede_unit_mismatch():
    """In both steepness and length, MISSING_INPUT and NOT_COMPUTABLE precede unit check."""
    res_l_miss = _ls_length(
        slope_length=InputMissing(reason="NOT_DECLARED"),
        lambda_unit_unit="PLACEHOLDER_other_unit",
    )
    assert isinstance(res_l_miss, ResultMissing)
    assert res_l_miss.reason == "MISSING_INPUT"

    res_l_nan = _ls_length(
        slope_length=math.nan,
        lambda_unit_unit="PLACEHOLDER_other_unit",
    )
    assert isinstance(res_l_nan, ResultMissing)
    assert res_l_nan.reason == "NOT_COMPUTABLE"
    assert "slope_length" in res_l_nan.detail

    res_s_nan = _ls_steepness(
        slope_steepness=math.nan,
        s_break_unit=ls.SlopeUnit.RATIO,
    )
    assert isinstance(res_s_nan, ResultMissing)
    assert res_s_nan.reason == "NOT_COMPUTABLE"
    assert "slope_steepness" in res_s_nan.detail

    res_s_unit = _ls_steepness(s_break_unit=ls.SlopeUnit.RATIO)
    assert isinstance(res_s_unit, ResultMissing)
    assert res_s_unit.reason == ls.REASON_UNIT_NOT_ACCEPTED


def test_ls_steepness_at_or_above_branch_overflow_is_not_computable():
    """Overflow in the at-or-above break slope branch returns NOT_COMPUTABLE."""
    largest = sys.float_info.max
    res = _ls_steepness(
        slope_steepness=LS_STEEPNESS["s_break"],
        a3=largest,
        a4=-largest,
    )
    assert isinstance(res, ResultMissing)
    assert res.reason == "NOT_COMPUTABLE"
    assert "S" in res.detail.split()


def test_ls_boolean_false_raises_type_error_and_zero_slope_gives_one():
    """Boolean False is rejected as TypeError; zero slope gives L=1 even when length != lambda_unit."""
    with pytest.raises(TypeError, match="slope_steepness"):
        _ls_steepness(slope_steepness=False)
    with pytest.raises(TypeError, match="slope_length"):
        _ls_length(slope_length=False)

    res = _ls_length(slope_steepness=0.0, slope_length=123.0, lambda_unit=66.0)
    assert isinstance(res, float)
    assert res == 1.0


# =============================================================================
# engine/erosion/equation.py mutants
# =============================================================================


def test_equation_missing_precedes_non_finite_and_lists_multiple_non_finite():
    """MISSING_INPUT precedes NOT_COMPUTABLE; multiple non-finite factors are all named in order."""
    res_order = equation.annual_soil_loss(
        **_eq_factors(
            r=equation.Factor(
                value=ResultMissing(reason="NOT_DECLARED", detail=None),
                unit=EQ_UNITS.r,
            ),
            k=equation.Factor(value=math.nan, unit=EQ_UNITS.k),
        ),
        accepted_units=EQ_UNITS,
        unit_guard_reason=EQ_GUARD,
    )
    assert isinstance(res_order, ResultMissing)
    assert res_order.reason == "MISSING_INPUT"
    assert "'r'" in res_order.detail
    assert "'k'" not in res_order.detail
    assert "None" not in res_order.detail

    res_multi = equation.annual_soil_loss(
        **_eq_factors(
            p=equation.Factor(value=-math.inf, unit=EQ_UNITS.p),
            k=equation.Factor(value=math.nan, unit=EQ_UNITS.k),
        ),
        accepted_units=EQ_UNITS,
        unit_guard_reason=EQ_GUARD,
    )
    assert isinstance(res_multi, ResultMissing)
    assert res_multi.reason == "NOT_COMPUTABLE"
    assert "'k'" in res_multi.detail and "'p'" in res_multi.detail
    assert res_multi.detail.index("'k'") < res_multi.detail.index("'p'")
    assert "'r'" not in res_multi.detail


# =============================================================================
# engine/erosion/_parameters.py mutants
# =============================================================================


def test_parameters_scope_text_sorting_and_reader_fork_isolation():
    """scope_text sorts keys so ParameterReader caches identically regardless of key order,
    and fork() isolates subsequent reads from the parent reader."""
    cat = {
        "p.json": _record(
            "test_param", 4.5, "PLACEHOLDER_u", {"stage": "day_1", "crop": "soy"}
        ),
        "q.json": _record("other_param", 9.0, "PLACEHOLDER_u", {}),
    }
    assert (
        params_mod.scope_text({"stage": "day_1", "crop": "soy"})
        == '{"crop": "soy", "stage": "day_1"}'
    )
    reader = params_mod.ParameterReader(cat)
    first = reader.read("test_param", {"stage": "day_1", "crop": "soy"})
    second = reader.read("test_param", {"crop": "soy", "stage": "day_1"})
    assert first == second
    assert len(reader.records_read()) == 1

    forked = reader.fork()
    assert forked.records_read() == reader.records_read()
    forked.read("other_param", {})
    assert len(forked.records_read()) == 2
    assert len(reader.records_read()) == 1


def test_parameters_not_comparable_multiple_malformed_and_null_unit_preserved():
    """Multiple malformed records are all named sorted; null value preserves record unit."""
    cat = {
        "z_bad.json": {"id": None, "scope": {}},
        "a_bad.json": {"id": "valid_id", "scope": None},
    }
    res = params_mod.read_parameter(cat, "any_id", {})
    assert isinstance(res.value, ResultMissing)
    assert res.unit is None
    assert "'a_bad.json', 'z_bad.json'" in res.value.detail

    null_cat = {
        "null.json": _record(
            "null_id",
            None,
            "UNMARKED_TEST_ONLY_kept_unit",
            {},
            "UNMARKED_TEST_ONLY: omitted",
        )
    }
    null_res = params_mod.read_parameter(null_cat, "null_id", {})
    assert isinstance(null_res.value, ResultMissing)
    assert null_res.unit == "UNMARKED_TEST_ONLY_kept_unit"


def test_parameters_scope_words_filters_exact_scope_dedups_and_uses_shown_scope():
    """scope_words ignores other ids, extra scope keys, missing key, deduplicates normalized words,
    and names shown_scope when a malformed record exists."""
    cat = {
        "r1.json": _record("pid_a", 1.0, "u", {"crop": "soy", "stage": "day_2"}),
        "r2.json": _record("pid_a", 2.0, "u", {"crop": "soy", "stage": " Day_2 "}),
        "r3.json": _record("pid_a", 3.0, "u", {"crop": "soy", "stage": "day_11"}),
        "extra_key.json": _record(
            "pid_a", 4.0, "u", {"crop": "soy", "stage": "day_3", "management": "x"}
        ),
        "no_key.json": _record("pid_a", 5.0, "u", {"crop": "soy"}),
        "other_id.json": _record("pid_b", 6.0, "u", {"crop": "soy", "stage": "day_99"}),
    }
    words = params_mod.scope_words(
        cat, "pid_a", {"crop": "soy"}, "stage", {"crop": "soy", "stage": "day_<N>"}
    )
    assert words == ["day_11", "day_2"]

    bad_cat = dict(cat, **{"bad.json": {"id": 123, "scope": {}}})
    err = params_mod.scope_words(
        bad_cat, "pid_a", {"crop": "soy"}, "stage", {"crop": "soy", "stage": "day_<N>"}
    )
    assert isinstance(err, ResultMissing)
    assert err.reason == "MISSING_INPUT"
    assert "day_<N>" in err.detail
    assert "'bad.json'" in err.detail


# =============================================================================
# engine/erosion/soil_loss.py mutants
# =============================================================================


def test_soil_loss_ag_year_boundary_on_start_month_first_day():
    """A series ending on day 1 of start_month includes that agricultural year as NO_COVERAGE."""
    # Start month is 7; ending on 2003-07-01 must include ag_year 2003 (not stop at 2002).
    first = dt.date(2001, 7, 1)
    last = dt.date(2003, 7, 1)
    cal = _calendar(
        first,
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    res = module.compute_soil_loss(cal, _climate(first, last), _soil(), parameters={})
    assert isinstance(res, SoilLossResults)
    assert [item.ag_year for item in res.annual] == [2001, 2002, 2003]
    assert res.annual[-1].missing.reason == "NO_COVERAGE"


def test_soil_loss_combined_prioritizes_missing_input_over_not_computable():
    """_combined returns MISSING_INPUT even when NOT_COMPUTABLE appears first."""
    problems = [
        module._Problem("NOT_COMPUTABLE", "PLACEHOLDER first"),
        module._Problem("MISSING_INPUT", "PLACEHOLDER second"),
    ]
    combined = module._combined(problems, "prefix")
    assert combined.reason == "MISSING_INPUT"
    assert "PLACEHOLDER first; PLACEHOLDER second" in combined.detail

    unit_first = [
        module._Problem(module.UNIT_NOT_ACCEPTED, "PLACEHOLDER u"),
        module._Problem("NOT_COMPUTABLE", "PLACEHOLDER nc"),
    ]
    assert module._combined(unit_first, "prefix").reason == module.UNIT_NOT_ACCEPTED


def test_soil_loss_ls_both_slope_units_unrecognized_length_mismatch_and_overflow():
    """LS names both invalid slope units, rejects length unit mismatch, and catches L*S overflow."""
    first, last = dt.date(2001, 7, 1), dt.date(2003, 6, 30)
    cal = _calendar(
        first,
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)

    # Both slope_unit and s_break_unit unrecognized
    cat_bad_break = _base_catalogue()
    cat_bad_break[f"{module.S_BREAK_ID}.json"]["unit"] = "UNMARKED_TEST_ONLY_bad_sbreak"
    soil_bad_slope = _soil(slope_unit="PLACEHOLDER_bad_slope")
    res_both = module.compute_soil_loss(
        cal, cli, soil_bad_slope, parameters=cat_bad_break
    )
    assert isinstance(res_both, SoilLossResults)
    detail_both = res_both.annual[0].missing.detail
    assert "PLACEHOLDER_bad_slope" in detail_both
    assert "UNMARKED_TEST_ONLY_bad_sbreak" in detail_both

    # Length unit mismatch
    res_len = module.compute_soil_loss(
        cal,
        cli,
        _soil(length_unit="PLACEHOLDER_other_len"),
        parameters=_base_catalogue(),
    )
    assert res_len.annual[0].missing.reason == "MISSING_INPUT"
    assert (
        f"factor 'ls' is missing (reason {module.UNIT_NOT_ACCEPTED}"
        in res_len.annual[0].missing.detail
    )
    assert "PLACEHOLDER_other_len" in res_len.annual[0].missing.detail

    # L and S individually finite, L * S overflows to inf
    cat_overflow = _base_catalogue()
    cat_overflow["rusle_s_below_break_sine_coefficient.json"]["value"] = 1e300
    cat_overflow["rusle_s_below_break_constant.json"]["value"] = 1e300
    cat_overflow[f"{module.LAMBDA_UNIT_ID}.json"]["value"] = 1e-100
    cat_overflow["rusle_l_beta_denominator_constant.json"]["value"] = 1e-10
    cat_overflow["rusle_l_beta_denominator_sine_coefficient.json"]["value"] = 1e-10
    res_ov = module.compute_soil_loss(
        cal, cli, _soil(length_val=1e100), parameters=cat_overflow
    )
    assert res_ov.annual[0].missing.reason == "MISSING_INPUT"
    assert (
        "factor 'ls' is missing (reason NOT_COMPUTABLE"
        in res_ov.annual[0].missing.detail
    )
    assert (
        "product of L and S is not a finite number" in res_ov.annual[0].missing.detail
    )


def test_soil_loss_covering_and_last_harvest_exact_boundaries():
    """Exact day boundaries of _covering and _last_harvest including undated start/end."""
    from engine.calendar.repeat import Cycle

    first = dt.date(2001, 7, 1)
    last = dt.date(2003, 6, 30)
    c1_start, c1_end = dt.date(2001, 10, 1), dt.date(2001, 12, 31)
    c2_start, c2_end = dt.date(2002, 2, 1), dt.date(2002, 4, 30)

    repeated = RepeatedRotation(
        start_month=START_MONTH,
        record_start=first,
        record_end=last,
        cycle_length=1,
        ag_years=(2001, 2002),
        first_day=first,
        last_day=last,
        cycles=(
            Cycle(
                index=0,
                shift_years=0,
                start=dt.date(2001, 8, 1),
                end=dt.date(2002, 6, 30),
                last_day=dt.date(2002, 6, 30),
                complete=True,
                components_not_laid_out=(),
            ),
        ),
        components=(
            RepeatedComponent(
                component_id="c1",
                crop_id=CROP_SOY,
                cycle=0,
                calendar_start=first,
                calendar_end=dt.date(2002, 6, 30),
                cycle_last_day=dt.date(2002, 6, 30),
                start=c1_start,
                end=c1_end,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
            RepeatedComponent(
                component_id="c2",
                crop_id=CROP_WHEAT,
                cycle=0,
                calendar_start=first,
                calendar_end=dt.date(2002, 6, 30),
                cycle_last_day=dt.date(2002, 6, 30),
                start=c2_start,
                end=c2_end,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
        ),
    )

    # Outside record
    assert module._covering(repeated, first - ONE_DAY).text == module.OUTSIDE_RECORD
    assert module._covering(repeated, last + ONE_DAY).text == module.OUTSIDE_RECORD
    assert module._last_harvest(repeated, first - ONE_DAY).text == module.OUTSIDE_RECORD
    assert module._last_harvest(repeated, last + ONE_DAY).text == module.OUTSIDE_RECORD

    # Before first cycle (< described_from, NOT <=)
    assert (
        module._covering(repeated, dt.date(2001, 7, 31)).text
        == module.BEFORE_FIRST_CYCLE
    )
    assert module._covering(repeated, dt.date(2001, 8, 1)) is None

    # Exact component start and end bounds
    assert module._covering(repeated, c1_start - ONE_DAY) is None
    assert module._covering(repeated, c1_start).component_id == "c1"
    assert module._covering(repeated, c1_end).component_id == "c1"
    assert module._covering(repeated, c1_end + ONE_DAY) is None

    # _last_harvest requires end < day strictly (not <=)
    assert module._last_harvest(repeated, c1_end).text == module.NO_HARVEST_BEFORE
    assert module._last_harvest(repeated, c1_end + ONE_DAY).component_id == "c1"
    assert module._last_harvest(repeated, c2_end).component_id == "c1"
    assert module._last_harvest(repeated, c2_end + ONE_DAY).component_id == "c2"


def test_soil_loss_undated_start_only_and_cycle_last_day_boundary():
    """Undated start triggers _covering problem; undated end at cycle_last_day triggers _last_harvest."""
    from engine.calendar.repeat import Cycle

    first = dt.date(2001, 7, 1)
    last = dt.date(2002, 6, 30)
    c1_end = dt.date(2002, 6, 30)  # equals cycle_last_day!
    cycle_0 = Cycle(
        index=0,
        shift_years=0,
        start=first,
        end=last,
        last_day=last,
        complete=True,
        components_not_laid_out=(),
    )
    repeated = RepeatedRotation(
        start_month=START_MONTH,
        record_start=first,
        record_end=last,
        cycle_length=1,
        ag_years=(2001,),
        first_day=first,
        last_day=last,
        cycles=(cycle_0,),
        components=(
            RepeatedComponent(
                component_id="dated_end",
                crop_id=CROP_SOY,
                cycle=0,
                calendar_start=first,
                calendar_end=last,
                cycle_last_day=last,
                start=dt.date(2001, 8, 1),
                end=c1_end,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
            RepeatedComponent(
                component_id="missing_start",
                crop_id=CROP_WHEAT,
                cycle=0,
                calendar_start=first,
                calendar_end=last,
                cycle_last_day=last,
                start=None,
                end=dt.date(2002, 3, 1),
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
            RepeatedComponent(
                component_id="missing_end",
                crop_id=CROP_MAIZE,
                cycle=0,
                calendar_start=first,
                calendar_end=last,
                cycle_last_day=last,
                start=dt.date(2002, 4, 1),
                end=None,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
        ),
    )
    # _covering catches start is None inside [first_day, last_day] including exact first_day
    cov_first = module._covering(repeated, first)
    assert isinstance(cov_first, module._Problem)
    assert "missing_start" in cov_first.text
    cov_prob = module._covering(repeated, dt.date(2001, 7, 15))
    assert isinstance(cov_prob, module._Problem)
    assert "missing_start" in cov_prob.text
    assert "whether they cover the day is not known" in cov_prob.text

    # On missing_end.start (2002-04-01), _earliest < day is False so missing_end is not yet candidate
    harv_at_start = module._last_harvest(repeated, dt.date(2002, 4, 1))
    assert isinstance(harv_at_start, RepeatedComponent)
    assert harv_at_start.component_id == "missing_start"
    # On 2002-04-02, _earliest < day is True and cycle_last_day >= last (even if last == cycle_last_day)
    harv_prob = module._last_harvest(repeated, dt.date(2002, 4, 2))
    assert isinstance(harv_prob, module._Problem)
    assert "missing_end" in harv_prob.text

    # When last == cycle_last_day on a later day in cycle 1, cycle_last_day >= last must still hold
    rep_boundary = RepeatedRotation(
        start_month=START_MONTH,
        record_start=first,
        record_end=dt.date(2003, 6, 30),
        cycle_length=1,
        ag_years=(2001, 2002),
        first_day=first,
        last_day=dt.date(2003, 6, 30),
        cycles=(cycle_0,),
        components=(
            RepeatedComponent(
                component_id="ended_at_cycle_end",
                crop_id=CROP_SOY,
                cycle=0,
                calendar_start=first,
                calendar_end=last,
                cycle_last_day=last,
                start=dt.date(2001, 8, 1),
                end=last,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
            RepeatedComponent(
                component_id="missing_end_c0",
                crop_id=CROP_MAIZE,
                cycle=0,
                calendar_start=first,
                calendar_end=last,
                cycle_last_day=last,
                start=dt.date(2001, 9, 1),
                end=None,
                periods=(),
                leap_day_moved=False,
                ends_after_record=False,
            ),
        ),
    )
    harv_eq = module._last_harvest(rep_boundary, dt.date(2002, 8, 1))
    assert isinstance(harv_eq, module._Problem)
    assert "missing_end_c0" in harv_eq.text


def test_soil_loss_overlapping_and_same_end_day_components_are_not_computable():
    """Two components covering the same day or ending on the same day return NOT_COMPUTABLE."""
    first = dt.date(2001, 7, 1)
    last = dt.date(2003, 6, 30)
    cli = _climate(first, last)
    cat = _main_c_catalogue()

    # Touching/overlapping on 2001-12-01 (and both end on different days)
    cal_overlap = _calendar(
        first,
        dt.date(2002, 6, 30),
        [
            ("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2001, 12, 1)),
            ("c2", CROP_WHEAT, dt.date(2001, 12, 1), dt.date(2002, 3, 1)),
        ],
    )
    res_ov = module.compute_soil_loss(cal_overlap, cli, _soil(), parameters=cat)
    assert isinstance(res_ov, SoilLossResults)
    for item in res_ov.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        assert "cover the same day" in item.missing.detail
        assert module.NO_FALLBACK in item.missing.detail
    assert (
        "factor 'c' is missing (reason NOT_COMPUTABLE"
        in res_ov.annual[1].missing.detail
    )

    # Same end day
    cal_same_end2 = _calendar(
        first,
        dt.date(2002, 6, 30),
        [
            ("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2001, 12, 15)),
            ("c2", CROP_WHEAT, dt.date(2001, 10, 1), dt.date(2001, 12, 15)),
        ],
    )
    res_same_end = module.compute_soil_loss(cal_same_end2, cli, _soil(), parameters=cat)
    assert isinstance(res_same_end, SoilLossResults)
    for item in res_same_end.annual:
        assert item.value is None
        assert item.missing.reason == "MISSING_INPUT"
        assert "end on the same day" in item.missing.detail
    assert (
        "factor 'c' is missing (reason NOT_COMPUTABLE"
        in res_same_end.annual[1].missing.detail
    )


def test_soil_loss_daily_route_non_inverse_site_coefficients():
    """On the daily route, non-inverse fall_height_coefficient or mass_cover_coefficient fails unit guard."""
    first = dt.date(2001, 6, 1)
    last = dt.date(2003, 6, 30)
    cal = _calendar(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)
    for pid in (module.FALL_HEIGHT_COEFFICIENT_ID, module.MASS_COVER_COEFFICIENT_ID):
        cat = _base_catalogue()
        cat[f"{pid}.json"]["unit"] = "UNMARKED_TEST_ONLY_not_inverse"
        res = module.compute_soil_loss_daily_index(cal, cli, _soil(), parameters=cat)
        assert isinstance(res, SoilLossResults)
        covered = [a for a in res.annual if a.ag_year in (2001, 2002)]
        assert covered
        for item in covered:
            assert item.value is None
            assert item.missing.reason == "MISSING_INPUT"
            assert (
                f"factor 'c' is missing (reason {module.UNIT_NOT_ACCEPTED}"
                in item.missing.detail
            )
            assert "is not read as the inverse of a unit" in item.missing.detail
            assert pid in item.missing.detail


def test_soil_loss_main_c_unsorted_stage_days_and_duplicate_stage_day():
    """Lexicographically unsorted stage words ('day_11' before 'day_2') compute in numeric order;
    two stage words for the same day ('day_0' and 'day_00') fail with NOT_COMPUTABLE and NO_FALLBACK."""
    first = dt.date(2001, 6, 1)
    last = dt.date(2003, 6, 30)
    cal = _calendar(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)

    cat_unsorted = _main_c_catalogue(stage_days=(2, 11))
    res_ok = module.compute_soil_loss(cal, cli, _soil(), parameters=cat_unsorted)
    assert isinstance(res_ok, SoilLossResults)
    assert res_ok.annual[2].value is not None

    # Verify _on_series directly on unsorted points
    unsorted_series = module._Series(
        points=(module._Point(day=11, value=0.8), module._Point(day=2, value=0.2)),
        unit=module.DIMENSIONLESS,
    )
    assert module._on_series(unsorted_series, 0) == pytest.approx(0.2)
    assert module._on_series(unsorted_series, 2) == pytest.approx(0.2)
    assert module._on_series(unsorted_series, 5) == pytest.approx(0.4)
    assert module._on_series(unsorted_series, 11) == pytest.approx(0.8)
    assert module._on_series(unsorted_series, 30) == pytest.approx(0.8)

    # Duplicate day via 'day_0' and 'day_00'
    cat_dup = _main_c_catalogue()
    cat_dup["cc.soy.d0.json"] = _record(
        module.CANOPY_COVER_ID,
        0.1,
        module.DIMENSIONLESS,
        {"crop": CROP_SOY, "stage": "day_0"},
    )
    cat_dup["cc.soy.d00.json"] = _record(
        module.CANOPY_COVER_ID,
        0.2,
        module.DIMENSIONLESS,
        {"crop": CROP_SOY, "stage": "day_00"},
    )
    res_dup = module.compute_soil_loss(cal, cli, _soil(), parameters=cat_dup)
    assert res_dup.annual[2].value is None
    assert res_dup.annual[2].missing.reason == "MISSING_INPUT"
    assert (
        "factor 'c' is missing (reason NOT_COMPUTABLE"
        in res_dup.annual[2].missing.detail
    )
    assert "give one day after planting twice" in res_dup.annual[2].missing.detail
    assert module.NO_FALLBACK in res_dup.annual[2].missing.detail


def test_soil_loss_conversion_units_edge_cases_and_no_conversion_when_same_unit():
    """_conversion_units rejects double ' per ' and blank sides; main C skips YIELD_CONVERSION_ID
    when crop yield unit already equals alpha's base unit, and rejects swapped conversion units."""
    assert module._conversion_units("kg per lb per ac") is None
    assert module._conversion_units(" per lb") is None
    assert module._conversion_units("kg per ") is None
    assert module._conversion_units("   per   ") is None
    assert module._conversion_units("kg per lb") == ("kg", "lb")

    first = dt.date(2001, 6, 1)
    last = dt.date(2003, 6, 30)
    cal_maize = _calendar(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        [("c1", CROP_MAIZE, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)

    # CROP_MAIZE has yield in MASS_UNIT and alpha in (MASS_UNIT)-1 -> YIELD_CONVERSION_ID not needed
    cat_no_conv = _main_c_catalogue(f"{module.YIELD_CONVERSION_ID}.json")
    res_maize = module.compute_soil_loss(
        cal_maize, cli, _soil(), parameters=cat_no_conv
    )
    assert res_maize.annual[2].value is not None
    assert module.COMPUTED_C in res_maize.annual[2].source

    # Swapped conversion unit '<yield> per <mass>' must fail with UNIT_NOT_ACCEPTED, no fallback
    cal_soy = _calendar(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cat_swapped = _main_c_catalogue()
    cat_swapped[f"{module.YIELD_CONVERSION_ID}.json"]["unit"] = (
        f"{YIELD_UNIT} per {MASS_UNIT}"
    )
    res_swap = module.compute_soil_loss(cal_soy, cli, _soil(), parameters=cat_swapped)
    assert res_swap.annual[2].value is None
    assert res_swap.annual[2].missing.reason == "MISSING_INPUT"
    assert (
        f"factor 'c' is missing (reason {module.UNIT_NOT_ACCEPTED}"
        in res_swap.annual[2].missing.detail
    )
    assert module.NO_FALLBACK in res_swap.annual[2].missing.detail


def test_soil_loss_main_c_unit_checks_do_not_fall_back():
    """Unit errors on main-route C (no-crop cover, decay, site b, fall height coeff, monthly units,
    and negative monthly erosivity) fail C without falling back to declared rusle_c_factor."""
    first = dt.date(2001, 6, 1)
    last = dt.date(2003, 6, 30)
    cal = _calendar(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)

    unit_cases = [
        ("cc.no_crop.json", "UNMARKED_TEST_ONLY_percent", module.UNIT_NOT_ACCEPTED),
        (f"dc.{CROP_SOY}.json", module.DAY, module.UNIT_NOT_ACCEPTED),
        (
            f"{module.SURFACE_COVER_B_PER_PERCENT_ID}.json",
            f"{HEIGHT_UNIT}-1",
            module.UNIT_NOT_ACCEPTED,
        ),
        (
            f"{module.FALL_HEIGHT_COEFFICIENT_ID}.json",
            HEIGHT_UNIT,
            module.UNIT_NOT_ACCEPTED,
        ),
        (
            f"{module.MONTHLY_EROSIVITY_IDS[0]}.json",
            "UNMARKED_TEST_ONLY_other_monthly",
            module.UNIT_NOT_ACCEPTED,
        ),
    ]
    for key, bad_unit, expected_reason in unit_cases:
        cat = _main_c_catalogue()
        cat[key]["unit"] = bad_unit
        res = module.compute_soil_loss(cal, cli, _soil(), parameters=cat)
        item = res.annual[2]
        assert item.value is None, key
        assert item.missing.reason == "MISSING_INPUT", key
        assert (
            f"factor 'c' is missing (reason {expected_reason}" in item.missing.detail
        ), key
        assert module.NO_FALLBACK in item.missing.detail, key

    # Negative monthly erosivity on computed-C catalogue fails without fallback
    cat_neg = _main_c_catalogue()
    cat_neg[f"{module.MONTHLY_EROSIVITY_IDS[0]}.json"]["value"] = -1.0
    res_neg = module.compute_soil_loss(cal, cli, _soil(), parameters=cat_neg)
    assert res_neg.annual[2].value is None
    assert res_neg.annual[2].missing.reason == "MISSING_INPUT"
    assert module.NO_FALLBACK in res_neg.annual[2].missing.detail


def test_soil_loss_main_month_combines_annual_and_monthly_missing_and_catches_overflow():
    """Monthly result combines annual MISSING_INPUT/UNIT_NOT_ACCEPTED with monthly missing,
    and returns NOT_COMPUTABLE when monthly product overflows while annual product is finite."""
    first = dt.date(2001, 7, 1)
    last = dt.date(2002, 6, 30)
    cal = _calendar(
        first,
        last,
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)

    # Annual NOT_COMPUTABLE via ls b1=0.0 + monthly MISSING_INPUT -> MISSING_INPUT
    cat_comb = _main_c_catalogue(f"{module.MONTHLY_EROSIVITY_IDS[0]}.json")
    cat_comb[f"{module.L_COEFFICIENTS['b1']}.json"]["value"] = 0.0
    res_comb = module.compute_soil_loss(cal, cli, _soil(), parameters=cat_comb)
    assert res_comb.annual[0].missing.reason == "MISSING_INPUT"
    assert (
        "factor 'ls' is missing (reason NOT_COMPUTABLE"
        in res_comb.annual[0].missing.detail
    )
    m0 = res_comb.monthly[0]
    assert m0.value is None
    assert m0.missing.reason == "MISSING_INPUT"
    assert "annual product" in m0.missing.detail
    assert "R of the month" in m0.missing.detail

    # Annual product finite (tiny R * large K * large LS), monthly math.prod(K, LS, C, P) overflows
    cat_ov = _base_catalogue()
    cat_ov[f"{module.R_ID}.json"]["value"] = 1e-200
    cat_ov[f"{module.K_ID}.json"]["value"] = 1e200
    cat_ov["rusle_s_below_break_sine_coefficient.json"]["value"] = 1e200
    cat_ov["rusle_s_below_break_constant.json"]["value"] = 1e200
    cat_ov[f"{module.C_ID}.json"]["value"] = 1.0
    cat_ov[f"{module.P_ID}.json"]["value"] = 1.0
    # Make L = 1.0 by matching slope_length == lambda_unit
    res_ov = module.compute_soil_loss(
        cal,
        cli,
        _soil(length_val=cat_ov[f"{module.LAMBDA_UNIT_ID}.json"]["value"]),
        parameters=cat_ov,
    )
    assert isinstance(res_ov.annual[0].value, float)
    assert math.isfinite(res_ov.annual[0].value)
    assert res_ov.monthly[0].value is None
    assert res_ov.monthly[0].missing.reason == "NOT_COMPUTABLE"
    assert "not a finite number" in res_ov.monthly[0].missing.detail


def test_soil_loss_year_without_harvest_before_only_fails_that_year_no_fallback():
    """On main route, when ag_year 2001 has days before first harvest, only 2001 is missing
    (with NO_FALLBACK) while 2002 computes with COMPUTED_C."""
    first = dt.date(2001, 7, 1)
    last = dt.date(2003, 6, 30)
    cal = _calendar(
        first,
        dt.date(2002, 6, 30),
        [("c1", CROP_SOY, dt.date(2001, 9, 1), dt.date(2002, 2, 1))],
    )
    cli = _climate(first, last)
    res = module.compute_soil_loss(cal, cli, _soil(), parameters=_main_c_catalogue())
    by_year = {a.ag_year: a for a in res.annual}
    assert by_year[2001].value is None
    assert module.NO_HARVEST_BEFORE in by_year[2001].missing.detail
    assert module.NO_FALLBACK in by_year[2001].missing.detail
    assert by_year[2002].value is not None
    assert module.COMPUTED_C in by_year[2002].source
