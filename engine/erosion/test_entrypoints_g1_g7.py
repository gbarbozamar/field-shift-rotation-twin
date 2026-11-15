"""Property and invariant tests for EP1 (``compute_soil_loss``) under G1-G7.

Covers ``contracts/ENTRYPOINTS.md`` rules G1-G7 and RUSLE scaling properties:
- G1: purity (no file I/O, network, env vars, or clock reads), argument
  immutability, and determinism (including parameter key-order invariance);
- G2/G3/G5/G7: signature contract, strict ``TypeError`` on invalid model/dict
  types, strict ``ValueError`` on ``case_id``/``field_id`` mismatches, valid
  model outputs, and no threshold parameters;
- G4: typed ``Missing`` (never zero, blank, or omitted years/months) across
  missing parameters, null/malformed/mismatched-unit records, infeasible
  calendars, incomplete years/months, and D141 phase lead-in;
- RUSLE scaling monotonicity: exact strictly positive linearity in R, K, P, C,
  and LS (both slope regimes and both declared-C and computed-C routes), power
  scaling in slope length, joint multilinearity, and degree-0 homogeneity in the
  twelve monthly erosivity records.

Every fixture, date, unit string, and parameter value in this file is built
exclusively from ``contracts/inputs/examples/PLACEHOLDER_*.json`` and in-memory
``PLACEHOLDER`` records (unmarked in memory only so ``check_catalogue`` passes).

Run from the repository root:
    py -3.12 -m pytest engine/erosion/test_entrypoints_g1_g7.py -q
"""

from __future__ import annotations

import ast
import builtins
import copy
import datetime as dt
import inspect
import json
import math
import os
import random
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from contracts.inputs.rotation_calendar import RotationCalendar
from contracts.inputs.site_climate import SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope
from contracts.results.models import (
    DIRECTION_OF,
    PROVENANCE_OF_SOIL_LOSS,
    UNIT_SOIL_LOSS_ANNUAL,
    UNIT_SOIL_LOSS_MONTHLY,
    AnnualSoilLoss,
    Missing,
    MonthlySoilLoss,
    ReasonCode,
    SoilLossResults,
)
from engine.calendar.repeat import (
    components_crossing_phase,
    list_phases,
    phase_calendar,
    repeat_over_record,
)
from engine.erosion import compute_soil_loss, ls
from engine.erosion import soil_loss as module
from params.catalogue import check_catalogue

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"

WORD = "PLACEHOLDER"
UNMARKED = "UNMARKED_TEST_ONLY"
ONE_DAY = dt.timedelta(days=1)
VALID_REASONS = frozenset(get_args(ReasonCode))

CROP_A = f"{UNMARKED}-crop-a"
CROP_B = f"{UNMARKED}-crop-b"
LEN_UNIT = f"{UNMARKED}_length_unit"
HEIGHT_UNIT = f"{UNMARKED}_height_unit"
MASS_UNIT = f"{UNMARKED}_mass_unit"
YIELD_UNIT = f"{UNMARKED}_yield_unit"
MONTHLY_UNIT = f"{UNMARKED}_monthly_unit"
MM_PER_DAY = "mm day-1"
RAIN_PATTERN = (0.0, 4.44, 22.2, 0.0, 1.11, 33.3, 8.88)

# Distinct positive PLACEHOLDER numbers (never real method values).
# Kept moderate so products remain finite and S > 0 on both sides of s_break.
SITE_VALUES: dict[str, float] = {
    module.R_ID: 321.5,
    module.K_ID: 0.234,
    module.P_ID: 0.654,
    module.C_ID: 0.147,
    module.R_EXPONENT_ID: 1.11,
    module.R_THRESHOLD_ID: 2.22,
    module.FALL_HEIGHT_COEFFICIENT_ID: 0.333,
    module.SURFACE_COVER_B_PER_PERCENT_ID: 0.00666,
    module.MASS_COVER_COEFFICIENT_ID: 0.222,
    "rusle_s_below_break_sine_coefficient": 12.5,
    "rusle_s_below_break_constant": 0.45,
    "rusle_s_at_or_above_break_sine_coefficient": 18.5,
    "rusle_s_at_or_above_break_constant_subtracted": 0.05,
    module.S_BREAK_ID: 5.0,
    module.LAMBDA_UNIT_ID: 20.0,
    "rusle_l_beta_sine_divisor": 0.085,
    "rusle_l_beta_denominator_sine_coefficient": 2.5,
    "rusle_l_beta_denominator_sine_exponent": 1.1,
    "rusle_l_beta_denominator_constant": 0.65,
    **{
        pid: 10.0 + float(idx)
        for idx, pid in enumerate(module.MONTHLY_EROSIVITY_IDS, start=1)
    },
}

STAGE_DAYS: tuple[int, ...] = (11, 22, 44)
STAGE_COVER: dict[str, tuple[float, ...]] = {
    CROP_A: (0.111, 0.555, 0.333),
    CROP_B: (0.222, 0.666, 0.444),
}
STAGE_HEIGHT: dict[str, tuple[float, ...]] = {
    CROP_A: (0.444, 1.222, 2.111),
    CROP_B: (0.333, 0.888, 1.555),
}
RESIDUE_VALUES: dict[tuple[str, str], float] = {
    (module.RESIDUE_YIELD_RATIO_ID, CROP_A): 1.25,
    (module.RESIDUE_YIELD_RATIO_ID, CROP_B): 1.75,
    (module.CROP_YIELD_ID, CROP_A): 4.5,
    (module.CROP_YIELD_ID, CROP_B): 5.5,
    (module.DECAY_COEFFICIENT_ID, CROP_A): 0.033,
    (module.DECAY_COEFFICIENT_ID, CROP_B): 0.022,
    (module.MASS_COVER_COEFFICIENT_ID, CROP_A): 0.055,
    (module.MASS_COVER_COEFFICIENT_ID, CROP_B): 0.044,
}
CONVERSION_FACTOR = 0.777


def _unmark(item: Any) -> Any:
    if isinstance(item, str):
        return item.replace(WORD, UNMARKED)
    if isinstance(item, dict):
        return {_unmark(k): _unmark(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_unmark(v) for v in item]
    return item


def _load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"PLACEHOLDER_{name}.json").read_text("utf-8"))


def _days_between(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + idx * ONE_DAY for idx in range((last - first).days + 1)]


def _ag_year_of(day: dt.date, start_month: int) -> int:
    return day.year if day.month >= start_month else day.year - 1


def _first_day_of(ag_year: int, start_month: int) -> dt.date:
    return dt.date(ag_year, start_month, 1)


def _last_day_of(ag_year: int, start_month: int) -> dt.date:
    return _first_day_of(ag_year + 1, start_month) - ONE_DAY


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    return first, following - ONE_DAY


def _months_of(ag_year: int, start_month: int) -> list[tuple[int, int]]:
    base = ag_year * 12 + start_month - 1
    return [((base + k) // 12, (base + k) % 12 + 1) for k in range(12)]


def _expected_ag_years(first: dt.date, last: dt.date, start_month: int) -> list[int]:
    return sorted({_ag_year_of(day, start_month) for day in _days_between(first, last)})


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
        "range_missing_reason": f"{UNMARKED}: no range",
        "citation": {
            "reference": f"{UNMARKED} reference",
            "locator": f"{UNMARKED} locator",
        },
        "transcribed_by": f"{UNMARKED}_person_1",
        "checked_by": f"{UNMARKED}_person_2",
    }
    if value is None:
        rec["value_missing_reason"] = missing_reason or f"{UNMARKED}: missing value"
    return rec


def _site_unit(pid: str) -> str:
    accepted = module.ACCEPTED_UNITS
    return {
        module.R_ID: accepted.r,
        module.K_ID: accepted.k,
        module.P_ID: accepted.p,
        module.C_ID: accepted.c,
        module.R_EXPONENT_ID: module.DIMENSIONLESS,
        module.R_THRESHOLD_ID: MM_PER_DAY,
        module.S_BREAK_ID: ls.SlopeUnit.PERCENT.value,
        module.LAMBDA_UNIT_ID: LEN_UNIT,
        module.FALL_HEIGHT_COEFFICIENT_ID: f"{HEIGHT_UNIT}-1",
        module.SURFACE_COVER_B_PER_PERCENT_ID: f"{module.PERCENT}-1",
        module.MASS_COVER_COEFFICIENT_ID: f"({MASS_UNIT})-1",
        **dict.fromkeys(module.MONTHLY_EROSIVITY_IDS, MONTHLY_UNIT),
    }.get(pid, f"{UNMARKED}_unit")


def _site_catalogue(
    *,
    leave_out: tuple[str, ...] = (),
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    records = {
        f"{pid}.json": _record(pid, SITE_VALUES[pid], _site_unit(pid))
        for pid in SITE_VALUES
        if pid not in leave_out
    }
    for key, patch in (overrides or {}).items():
        records[key].update(patch)
    return records


def _computed_c_catalogue(
    *,
    crops: tuple[str, ...] = (CROP_A, CROP_B),
    leave_out_keys: tuple[str, ...] = (),
    overrides: dict[str, dict[str, Any]] | None = None,
    validate: bool = True,
) -> dict[str, dict[str, Any]]:
    records = _site_catalogue()
    for crop in crops:
        for days, cover, height in zip(
            STAGE_DAYS, STAGE_COVER[crop], STAGE_HEIGHT[crop]
        ):
            stage = f"{module.STAGE_PREFIX}{days}"
            scope = {"crop": crop, "stage": stage}
            records[f"{module.CANOPY_COVER_ID}.{crop}.{stage}.json"] = _record(
                module.CANOPY_COVER_ID, cover, module.DIMENSIONLESS, scope
            )
            records[f"{module.FALL_HEIGHT_ID}.{crop}.{stage}.json"] = _record(
                module.FALL_HEIGHT_ID, height, HEIGHT_UNIT, scope
            )
        crop_scope = {"crop": crop}
        records[f"{module.RESIDUE_YIELD_RATIO_ID}.{crop}.json"] = _record(
            module.RESIDUE_YIELD_RATIO_ID,
            RESIDUE_VALUES[(module.RESIDUE_YIELD_RATIO_ID, crop)],
            module.DIMENSIONLESS,
            crop_scope,
        )
        records[f"{module.CROP_YIELD_ID}.{crop}.json"] = _record(
            module.CROP_YIELD_ID,
            RESIDUE_VALUES[(module.CROP_YIELD_ID, crop)],
            YIELD_UNIT if crop == CROP_A else MASS_UNIT,
            crop_scope,
        )
        records[f"{module.DECAY_COEFFICIENT_ID}.{crop}.json"] = _record(
            module.DECAY_COEFFICIENT_ID,
            RESIDUE_VALUES[(module.DECAY_COEFFICIENT_ID, crop)],
            f"{module.DAY}-1",
            crop_scope,
        )
        records[f"{module.MASS_COVER_COEFFICIENT_ID}.{crop}.json"] = _record(
            module.MASS_COVER_COEFFICIENT_ID,
            RESIDUE_VALUES[(module.MASS_COVER_COEFFICIENT_ID, crop)],
            f"({MASS_UNIT})-1",
            crop_scope,
        )
    records[f"{module.CANOPY_COVER_ID}.no_crop.json"] = _record(
        module.CANOPY_COVER_ID, 0.111, module.DIMENSIONLESS, module.NO_CROP_SCOPE
    )
    records[f"{module.FALL_HEIGHT_ID}.no_crop.json"] = _record(
        module.FALL_HEIGHT_ID, 0.222, HEIGHT_UNIT, module.NO_CROP_SCOPE
    )
    records[f"{module.YIELD_CONVERSION_ID}.json"] = _record(
        module.YIELD_CONVERSION_ID,
        CONVERSION_FACTOR,
        f"{MASS_UNIT}{module.CONVERSION_SEPARATOR}{YIELD_UNIT}",
    )
    for key in leave_out_keys:
        records.pop(key, None)
    for key, patch in (overrides or {}).items():
        records[key].update(patch)
    if validate:
        assert check_catalogue(records) == []
    return records


def _dated(day: dt.date) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "provenance": "DECLARED",
        "source": f"{WORD}: synthetic test date",
    }


def _comp(
    comp_id: str, crop_id: str, start: dt.date | None, end: dt.date | None
) -> dict[str, Any]:
    def edge(day: dt.date | None) -> dict[str, Any]:
        if day is not None:
            return _dated(day)
        return {
            "date": None,
            "missing": {"reason": "NOT_DECLARED", "detail": f"{WORD}: missing date"},
        }

    return {
        "component_id": comp_id,
        "crop_id": crop_id,
        "start": edge(start),
        "end": edge(end),
        "periods": [],
    }


def _make_calendar(
    start_date: dt.date,
    end_date: dt.date,
    components: list[dict[str, Any]],
    *,
    start_month: int | None = 7,
    feasible: bool = True,
    case_id: str | None = None,
    field_id: str | None = None,
) -> RotationCalendar:
    doc = _load_example("rotation_calendar")
    if case_id is not None:
        doc["case_id"] = case_id
    if field_id is not None:
        doc["field_id"] = field_id
    if start_month is None:
        doc["ag_year_start"] = {
            "month": None,
            "missing": {"reason": "NOT_DECLARED", "detail": f"{WORD}: no start month"},
        }
    else:
        doc["ag_year_start"]["month"] = start_month
    doc["start_date"] = start_date.isoformat()
    doc["end_date"] = end_date.isoformat()
    doc["feasibility"] = {
        "feasible": feasible,
        "violations": (
            []
            if feasible
            else [{"rule": f"{WORD}-rule", "component_ids": [c["component_id"] for c in components[:1]]}]
        ),
    }
    doc["components"] = components
    return RotationCalendar.model_validate(doc)


def _make_climate(
    start_date: dt.date,
    end_date: dt.date,
    *,
    with_precip: bool = True,
    missing_dates: set[dt.date] | None = None,
    case_id: str | None = None,
    field_id: str | None = None,
) -> SiteClimate:
    doc = _load_example("site_climate")
    if case_id is not None:
        doc["case_id"] = case_id
    if field_id is not None:
        doc["field_id"] = field_id
    (precip_template,) = [
        item for item in doc["daily_series"] if item["quantity"] == module.PRECIPITATION
    ]
    others = [
        item for item in doc["daily_series"] if item["quantity"] != module.PRECIPITATION
    ]
    if with_precip:
        missing_set = missing_dates or set()
        days = []
        for idx, day in enumerate(_days_between(start_date, end_date)):
            if day in missing_set:
                days.append(
                    {
                        "date": day.isoformat(),
                        "value": None,
                        "missing": {
                            "reason": "NO_COVERAGE",
                            "detail": f"{WORD}: gap on {day.isoformat()}",
                        },
                    }
                )
            else:
                days.append(
                    {
                        "date": day.isoformat(),
                        "value": RAIN_PATTERN[idx % len(RAIN_PATTERN)],
                    }
                )
        series = copy.deepcopy(precip_template)
        series.update(
            unit=MM_PER_DAY,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            days=days,
            source=f"{WORD}: synthetic daily series",
        )
        doc["daily_series"] = [*others, series]
    else:
        doc["daily_series"] = others
    return SiteClimate.model_validate(doc)


def _make_soil(
    *,
    slope_steepness: float | None = 2.0,
    slope_unit: str = ls.SlopeUnit.PERCENT.value,
    slope_length: float | None = 15.0,
    slope_length_unit: str = LEN_UNIT,
    case_id: str | None = None,
    field_id: str | None = None,
) -> SiteSoilSlope:
    doc = _load_example("site_soil_slope")
    if case_id is not None:
        doc["case_id"] = case_id
    if field_id is not None:
        doc["field_id"] = field_id
    if slope_steepness is None:
        doc["slope_steepness"] = {
            "value": None,
            "unit": slope_unit,
            "missing": {"reason": "NO_COVERAGE", "detail": f"{WORD}: missing slope"},
        }
    else:
        doc["slope_steepness"]["value"] = slope_steepness
        doc["slope_steepness"]["unit"] = slope_unit
        if "range" in doc["slope_steepness"]:
            doc["slope_steepness"]["range"]["low"] = slope_steepness - 0.5
            doc["slope_steepness"]["range"]["high"] = slope_steepness + 0.5
    if slope_length is None:
        doc["slope_length"] = {
            "value": None,
            "unit": slope_length_unit,
            "missing": {"reason": "NO_COVERAGE", "detail": f"{WORD}: missing length"},
        }
    else:
        doc["slope_length"]["value"] = slope_length
        doc["slope_length"]["unit"] = slope_length_unit
    return SiteSoilSlope.model_validate(doc)


def _two_year_calendar(*, crossing: bool = False) -> RotationCalendar:
    """Two-year rotation (ag_year 2001..2002, start_month=7) with CROP_A and CROP_B."""
    if crossing:
        # CROP_B starts in year 0 (2002-05-01) and crosses boundary 2002-07-01 into year 1 (2002-10-31).
        components = [
            _comp("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 28)),
            _comp("c2", CROP_B, dt.date(2002, 5, 1), dt.date(2002, 10, 31)),
            _comp("c3", CROP_A, dt.date(2002, 12, 1), dt.date(2003, 5, 15)),
        ]
    else:
        components = [
            _comp("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 28)),
            _comp("c2", CROP_B, dt.date(2002, 9, 1), dt.date(2003, 3, 31)),
        ]
    return _make_calendar(dt.date(2001, 7, 1), dt.date(2003, 6, 30), components)


def _assert_g4_invariants(
    result: SoilLossResults, expected_ag_years: list[int], start_month: int
) -> None:
    assert isinstance(result, SoilLossResults)
    assert [item.ag_year for item in result.annual] == expected_ag_years
    assert len(result.monthly) == 12 * len(expected_ag_years)

    for ag_year in expected_ag_years:
        months = [m for m in result.monthly if m.ag_year == ag_year]
        assert [(m.year, m.month) for m in months] == _months_of(ag_year, start_month)

    for item in [*result.annual, *result.monthly]:
        expected_unit = (
            UNIT_SOIL_LOSS_ANNUAL
            if isinstance(item, AnnualSoilLoss)
            else UNIT_SOIL_LOSS_MONTHLY
        )
        assert item.indicator == "soil_loss"
        assert item.direction == DIRECTION_OF["soil_loss"]
        assert item.unit == expected_unit
        if item.value is None:
            assert isinstance(item.missing, Missing)
            assert item.missing.reason in VALID_REASONS
            assert item.missing.detail and item.missing.detail.strip()
            assert item.provenance is None
            assert item.source is None
            assert item.range is None
            assert item.range_missing is None
        else:
            assert math.isfinite(item.value)
            assert item.missing is None
            assert item.provenance == PROVENANCE_OF_SOIL_LOSS
            assert item.source and item.source.strip()
            assert item.range is None
            assert item.range_missing == Missing(
                reason="NOT_AVAILABLE", detail=module.RANGE_NOT_BUILT
            )

    round_trip = SoilLossResults.model_validate_json(result.model_dump_json())
    assert round_trip == result


# =============================================================================
# G1: Purity, argument immutability, and determinism
# =============================================================================


def test_g1_purity_no_file_network_env_or_clock_access(monkeypatch):
    """EP1 performs no file I/O, network call, env lookup, or clock access."""
    import params.catalogue as catalogue_mod

    def _forbid(what: str):
        def _raiser(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"G1 purity violation: {what} called during EP1")

        return _raiser

    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    soil = _make_soil()
    regimes = [
        _site_catalogue(),
        _computed_c_catalogue(),
        {},
    ]
    for params in regimes:
        with monkeypatch.context() as mp:
            mp.setattr(builtins, "open", _forbid("builtins.open"))
            mp.setattr(Path, "open", _forbid("Path.open"))
            mp.setattr(Path, "read_text", _forbid("Path.read_text"))
            mp.setattr(catalogue_mod, "load_folder", _forbid("load_folder"))
            mp.setattr(catalogue_mod, "check_folder", _forbid("check_folder"))
            mp.setattr(socket, "socket", _forbid("socket.socket"))
            mp.setattr(os, "getenv", _forbid("os.getenv"))
            mp.setattr(time, "time", _forbid("time.time"))
            mp.setattr(time, "monotonic", _forbid("time.monotonic"))
            result = compute_soil_loss(
                calendar=cal, climate=cli, soil_slope=soil, parameters=params
            )
            assert isinstance(result, SoilLossResults)

    # Static check: soil_loss.py and _parameters.py never call today()/now()/environ.
    forbidden_attrs = {"today", "utcnow", "now", "environ", "getenv", "load_folder"}
    for filename in ("soil_loss.py", "_parameters.py"):
        tree = ast.parse((Path(module.__file__).parent / filename).read_text("utf-8"))
        names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if isinstance(node, (ast.Attribute, ast.Name))
        }
        assert names.isdisjoint(forbidden_attrs), filename


@pytest.mark.parametrize(
    "regime",
    [
        "declared_c",
        "computed_c",
        "empty_params",
        "infeasible",
        "partial_years",
        "missing_start_month",
        "missing_precip",
        "d141_lead_in",
    ],
)
def test_g1_immutability_across_all_regimes(regime: str):
    """compute_soil_loss never mutates calendar, climate, soil_slope, or parameters."""
    soil = _make_soil()
    if regime == "declared_c":
        cal = _two_year_calendar()
        cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
        params = _site_catalogue()
    elif regime == "computed_c":
        cal = _two_year_calendar()
        cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
        params = _computed_c_catalogue()
    elif regime == "empty_params":
        cal = _two_year_calendar()
        cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
        params = {}
    elif regime == "infeasible":
        cal = _make_calendar(
            dt.date(2001, 7, 1),
            dt.date(2003, 6, 30),
            [_comp("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 28))],
            feasible=False,
        )
        cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
        params = _computed_c_catalogue()
    elif regime == "partial_years":
        cal = _two_year_calendar()
        cli = _make_climate(dt.date(2001, 8, 15), dt.date(2003, 4, 10))
        params = _site_catalogue()
    elif regime == "missing_start_month":
        cal = _make_calendar(
            dt.date(2001, 7, 1), dt.date(2003, 6, 30), [], start_month=None
        )
        cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
        params = _site_catalogue()
    elif regime == "missing_precip":
        cal = _two_year_calendar()
        cli = _make_climate(
            dt.date(2001, 7, 1), dt.date(2003, 6, 30), with_precip=False
        )
        params = _site_catalogue()
    else:
        cal = phase_calendar(_two_year_calendar(crossing=True), 1)
        cli = _make_climate(dt.date(2001, 7, 1), dt.date(2004, 6, 30))
        params = _computed_c_catalogue()

    snapshot = (
        copy.deepcopy(cal),
        copy.deepcopy(cli),
        copy.deepcopy(soil),
        copy.deepcopy(params),
    )
    param_ids = {k: id(v) for k, v in params.items()}

    _ = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params
    )

    assert (cal, cli, soil, params) == snapshot
    assert {k: id(v) for k, v in params.items()} == param_ids


@pytest.mark.parametrize("use_computed_c", [False, True])
def test_g1_determinism_and_parameter_key_order_invariance(use_computed_c: bool):
    """Repeated calls and arbitrary parameter dict insertion orders match identically."""
    cal = _two_year_calendar(crossing=True)
    cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    soil = _make_soil()
    params = _computed_c_catalogue() if use_computed_c else _site_catalogue()

    baseline = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params
    )
    again = compute_soil_loss(
        calendar=copy.deepcopy(cal),
        climate=copy.deepcopy(cli),
        soil_slope=copy.deepcopy(soil),
        parameters=copy.deepcopy(params),
    )
    assert again == baseline
    assert again.model_dump(mode="json") == baseline.model_dump(mode="json")

    keys = list(params.keys())
    for seed in (1, 7, 42):
        shuffled_keys = list(keys)
        random.Random(seed).shuffle(shuffled_keys)
        permuted = {k: copy.deepcopy(params[k]) for k in shuffled_keys}
        res = compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=permuted
        )
        assert res == baseline


# =============================================================================
# G2 / G3 / G5 / G7: Signature, strict type checks, and same-field checks
# =============================================================================


def test_g3_g7_entrypoint_signature_and_no_thresholds():
    """EP1 is exported from engine.erosion, takes keyword-only parameters, and no threshold."""
    from engine.erosion import compute_soil_loss as pkg_fn

    assert pkg_fn is compute_soil_loss
    assert pkg_fn is module.compute_soil_loss
    sig = inspect.signature(compute_soil_loss)
    assert list(sig.parameters) == ["calendar", "climate", "soil_slope", "parameters"]
    assert sig.parameters["parameters"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["parameters"].default is inspect.Parameter.empty
    for name in sig.parameters:
        assert "threshold" not in name and "plan" not in name

    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    soil = _make_soil()

    with pytest.raises(TypeError, match="parameters"):
        compute_soil_loss(calendar=cal, climate=cli, soil_slope=soil)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        compute_soil_loss(cal, cli, soil, {})  # type: ignore[misc]
    with pytest.raises(TypeError):
        compute_soil_loss(
            calendar=cal,
            climate=cli,
            soil_slope=soil,
            parameters={},
            threshold=1.0,  # type: ignore[call-arg]
        )


@pytest.mark.parametrize("target", ["calendar", "climate", "soil_slope"])
def test_g5_strict_type_checks_on_model_arguments(target: str):
    """G3/G5: non-instance of expected model (dict, JSON, None, wrong model, duck-type) raises TypeError."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    soil = _make_soil()
    valid = {"calendar": cal, "climate": cli, "soil_slope": soil}
    other_model = {"calendar": cli, "climate": soil, "soil_slope": cal}[target]
    duck = SimpleNamespace(case_id=cal.case_id, field_id=cal.field_id)

    bad_values = [
        None,
        123,
        "invalid",
        [],
        valid[target].model_dump(mode="json"),
        valid[target].model_dump_json(),
        other_model,
        duck,
    ]
    for bad in bad_values:
        kwargs = {**valid, target: bad, "parameters": {}}
        with pytest.raises(TypeError, match=target):
            compute_soil_loss(**kwargs)


@pytest.mark.parametrize(
    "bad_params",
    [
        None,
        [],
        (),
        "PLACEHOLDER",
        42,
        {1: {}},
        {None: {}},
        {("a",): {}},
        {"a.json": None},
        {"a.json": "not-a-dict"},
        {"a.json": 123},
        {"a.json": [{}]},
        list(_site_catalogue().items()),
    ],
)
def test_g5_strict_type_checks_on_parameters(bad_params: Any):
    """G3/G5: parameters must be dict[str, dict]; any other container/key/value raises TypeError."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    soil = _make_soil()
    with pytest.raises(TypeError, match="parameters"):
        compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=bad_params
        )


@pytest.mark.parametrize(
    ("cli_override", "soil_override", "expected_fields"),
    [
        ({"case_id": f"{WORD}-other-case"}, {}, ("case_id",)),
        ({"field_id": f"{WORD}-other-field"}, {}, ("field_id",)),
        ({}, {"case_id": f"{WORD}-other-case"}, ("case_id",)),
        ({}, {"field_id": f"{WORD}-other-field"}, ("field_id",)),
        (
            {"case_id": f"{WORD}-other-case"},
            {"case_id": f"{WORD}-other-case"},
            ("case_id",),
        ),
        (
            {"case_id": f"{WORD}-case-x"},
            {"case_id": f"{WORD}-case-y"},
            ("case_id",),
        ),
        (
            {"case_id": f"{WORD}-other-case"},
            {"field_id": f"{WORD}-other-field"},
            ("case_id", "field_id"),
        ),
        (
            {"case_id": f"{WORD}-other-case", "field_id": f"{WORD}-other-field"},
            {},
            ("case_id", "field_id"),
        ),
    ],
)
def test_g5_same_field_case_id_and_field_id_checks(
    cli_override: dict[str, str],
    soil_override: dict[str, str],
    expected_fields: tuple[str, ...],
):
    """G5: differing case_id or field_id raises ValueError naming differing field(s), never values."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2002, 6, 30), **cli_override)
    soil = _make_soil(**soil_override)
    with pytest.raises(ValueError) as exc_info:
        compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=_site_catalogue()
        )
    message = str(exc_info.value)
    for field in expected_fields:
        assert field in message
    for field in {"case_id", "field_id"} - set(expected_fields):
        assert field not in message
    # Never leak actual ID values in the error message.
    for leaked in (*cli_override.values(), *soil_override.values()):
        assert leaked not in message


def test_g5_caller_defect_checks_precede_g4_missing_conditions():
    """TypeError and ValueError fire before G4 checks (missing start month / precip / infeasible)."""
    bad_cal = _make_calendar(
        dt.date(2001, 7, 1), dt.date(2002, 6, 30), [], start_month=None, feasible=False
    )
    cli_no_precip = _make_climate(
        dt.date(2001, 7, 1),
        dt.date(2002, 6, 30),
        with_precip=False,
        case_id=f"{WORD}-mismatch",
    )
    soil = _make_soil()
    with pytest.raises(ValueError, match="case_id"):
        compute_soil_loss(
            calendar=bad_cal, climate=cli_no_precip, soil_slope=soil, parameters={}
        )
    with pytest.raises(TypeError, match="parameters"):
        compute_soil_loss(
            calendar=bad_cal,
            climate=cli_no_precip,
            soil_slope=soil,
            parameters="bad",  # type: ignore[arg-type]
        )


# =============================================================================
# G4: Typed Missing across missing params, infeasible, incomplete years, D141
# =============================================================================


def test_g4_missing_start_month_or_precipitation_returns_top_level_missing():
    """Missing start_month or missing precipitation series returns typed Missing (MISSING_INPUT)."""
    cal_no_start = _make_calendar(
        dt.date(2001, 7, 1), dt.date(2002, 6, 30), [], start_month=None
    )
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2002, 6, 30))
    soil = _make_soil()

    res_start = compute_soil_loss(
        calendar=cal_no_start,
        climate=cli,
        soil_slope=soil,
        parameters=_site_catalogue(),
    )
    assert type(res_start) is Missing
    assert res_start.reason == "MISSING_INPUT"
    assert "start month" in (res_start.detail or "")

    cal = _two_year_calendar()
    cli_no_precip = _make_climate(
        dt.date(2001, 7, 1), dt.date(2002, 6, 30), with_precip=False
    )
    res_precip = compute_soil_loss(
        calendar=cal,
        climate=cli_no_precip,
        soil_slope=soil,
        parameters=_site_catalogue(),
    )
    assert type(res_precip) is Missing
    assert res_precip.reason == "MISSING_INPUT"
    assert module.PRECIPITATION in (res_precip.detail or "")


@pytest.mark.parametrize(
    ("span", "params"),
    [
        ((dt.date(2001, 7, 1), dt.date(2003, 6, 30)), {}),
        ((dt.date(2001, 7, 1), dt.date(2003, 6, 30)), _site_catalogue()),
        ((dt.date(2001, 7, 1), dt.date(2003, 6, 30)), _computed_c_catalogue()),
        ((dt.date(2001, 8, 15), dt.date(2003, 4, 10)), _site_catalogue()),
    ],
)
def test_g4_infeasible_calendar_every_value_is_not_computable(
    span: tuple[dt.date, dt.date], params: dict[str, dict[str, Any]]
):
    """Infeasible calendar makes every annual and monthly value NOT_COMPUTABLE, even on partial years."""
    cal = _make_calendar(
        dt.date(2001, 7, 1),
        dt.date(2003, 6, 30),
        [_comp("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 28))],
        feasible=False,
    )
    cli = _make_climate(*span)
    soil = _make_soil()

    res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params
    )
    expected_years = _expected_ag_years(*span, start_month=7)
    _assert_g4_invariants(res, expected_years, start_month=7)
    for item in [*res.annual, *res.monthly]:
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "NOT_COMPUTABLE"


def test_g4_incomplete_years_and_partial_months_no_coverage():
    """Uncovered years/months return NO_COVERAGE; covered months inside partial years still compute."""
    # Starts 1 day after 2001-07-01, ends 1 day before 2003-06-30 -> ag_years [2001, 2002].
    span = (dt.date(2001, 7, 2), dt.date(2003, 6, 29))
    cal = _two_year_calendar()
    cli = _make_climate(*span)
    soil = _make_soil()

    res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=_site_catalogue()
    )
    _assert_g4_invariants(res, [2001, 2002], start_month=7)
    for item in res.annual:
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "NO_COVERAGE"

    # First month (2001-07) and last month (2003-06) are incomplete -> NO_COVERAGE;
    # the 22 interior months are fully covered and compute numerically.
    assert res.monthly[0].missing is not None
    assert res.monthly[0].missing.reason == "NO_COVERAGE"
    assert res.monthly[-1].missing is not None
    assert res.monthly[-1].missing.reason == "NO_COVERAGE"
    for month_item in res.monthly[1:-1]:
        assert month_item.value is not None and month_item.value > 0.0

    # With a full interior year (2001-08-15 .. 2003-08-15 -> ag_years [2001, 2002, 2003]),
    # 2002 is full/numeric, while 2001 and 2003 are NO_COVERAGE.
    span3 = (dt.date(2001, 8, 15), dt.date(2003, 8, 15))
    res3 = compute_soil_loss(
        calendar=cal,
        climate=_make_climate(*span3),
        soil_slope=soil,
        parameters=_site_catalogue(),
    )
    _assert_g4_invariants(res3, [2001, 2002, 2003], start_month=7)
    by_year = {item.ag_year: item for item in res3.annual}
    assert by_year[2001].missing is not None and by_year[2001].missing.reason == "NO_COVERAGE"
    assert by_year[2002].value is not None and by_year[2002].value > 0.0
    assert by_year[2003].missing is not None and by_year[2003].missing.reason == "NO_COVERAGE"


@pytest.mark.parametrize(
    "missing_pid",
    [module.R_ID, module.K_ID, module.P_ID, module.C_ID, module.S_BREAK_ID, module.LAMBDA_UNIT_ID],
)
def test_g4_missing_required_site_parameter_returns_missing_input(missing_pid: str):
    """Omitting any required site parameter produces typed MISSING_INPUT naming that parameter."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _make_soil()
    params = _site_catalogue(leave_out=(missing_pid,))

    res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params
    )
    _assert_g4_invariants(res, [2001, 2002], start_month=7)
    for item in [*res.annual, *res.monthly]:
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "MISSING_INPUT"
        assert missing_pid in (item.missing.detail or "")


def test_g4_missing_monthly_erosivity_leaves_annual_numeric_and_months_missing():
    """Omitting a monthly erosivity record keeps declared-C annual numeric, months MISSING_INPUT."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _make_soil()
    omitted = module.MONTHLY_EROSIVITY_IDS[3]
    params = _site_catalogue(leave_out=(omitted,))

    res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params
    )
    _assert_g4_invariants(res, [2001, 2002], start_month=7)
    for ann in res.annual:
        assert ann.value is not None and ann.value > 0.0
    for mon in res.monthly:
        assert mon.value is None
        assert mon.missing is not None
        assert mon.missing.reason == "MISSING_INPUT"
        assert omitted in (mon.missing.detail or "")


def test_g4_null_parameter_and_unit_mismatch_return_typed_missing():
    """Null parameter repeats its reason (MISSING_INPUT); bad units return NOT_COMPUTABLE."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _make_soil()

    # Null parameter value on R_ID
    reason_text = f"{UNMARKED}: no measurement for R"
    params_null = _site_catalogue(
        overrides={
            f"{module.R_ID}.json": {
                "value": None,
                "value_missing_reason": reason_text,
            }
        }
    )
    res_null = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params_null
    )
    _assert_g4_invariants(res_null, [2001, 2002], start_month=7)
    for item in res_null.annual:
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == "MISSING_INPUT"
        assert reason_text in (item.missing.detail or "")

    # Unit mismatch on K_ID (declared-C path)
    params_bad_unit = _site_catalogue(
        overrides={f"{module.K_ID}.json": {"unit": f"{UNMARKED}_wrong_unit"}}
    )
    res_unit = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params_bad_unit
    )
    _assert_g4_invariants(res_unit, [2001, 2002], start_month=7)
    for item in [*res_unit.annual, *res_unit.monthly]:
        assert item.value is None
        assert item.missing is not None
        assert item.missing.reason == module.UNIT_NOT_ACCEPTED

    # Unit mismatch on computed-C record gives NOT_COMPUTABLE without fallback
    cli_lead = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    params_bad_c_unit = _computed_c_catalogue(
        overrides={
            f"{module.RESIDUE_YIELD_RATIO_ID}.{CROP_A}.json": {
                "unit": f"{UNMARKED}_bad_ratio_unit"
            }
        }
    )
    res_c_unit = compute_soil_loss(
        calendar=cal, climate=cli_lead, soil_slope=soil, parameters=params_bad_c_unit
    )
    _assert_g4_invariants(res_c_unit, [2000, 2001, 2002, 2003], start_month=7)
    for ann in res_c_unit.annual:
        if ann.ag_year in (2001, 2002, 2003):
            assert ann.value is None
            assert ann.missing is not None
            assert ann.missing.reason == "MISSING_INPUT"
            detail = ann.missing.detail or ""
            assert f"factor 'c' is missing (reason {module.UNIT_NOT_ACCEPTED}" in detail
            assert module.NO_FALLBACK in detail


def test_g4_computed_c_fallback_uniformity_and_c_id_not_required():
    """Missing any computed-C record triggers uniform fallback; complete computed-C needs no C_ID."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    soil = _make_soil()

    # Complete computed-C works even without rusle_c_factor (C_ID).
    params_no_c = _computed_c_catalogue(leave_out_keys=(f"{module.C_ID}.json",))
    res_computed = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params_no_c
    )
    _assert_g4_invariants(res_computed, [2000, 2001, 2002, 2003], start_month=7)
    for ann in res_computed.annual:
        if ann.ag_year in (2001, 2002, 2003):
            assert ann.value is not None and ann.value > 0.0
            assert module.COMPUTED_C in (ann.source or "")

    # Leaving out one computed-C record falls back uniformly across ALL covered years.
    params_fallback = _computed_c_catalogue(
        leave_out_keys=(f"{module.DECAY_COEFFICIENT_ID}.{CROP_B}.json",)
    )
    res_fallback = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=params_fallback
    )
    _assert_g4_invariants(res_fallback, [2000, 2001, 2002, 2003], start_month=7)
    covered_vals = {
        ann.value for ann in res_fallback.annual if ann.ag_year in (2001, 2002, 2003)
    }
    assert len(covered_vals) == 1 and next(iter(covered_vals)) is not None
    for ann in res_fallback.annual:
        if ann.ag_year in (2001, 2002, 2003):
            assert "PROPOSED fallback" in (ann.source or "")


def test_g4_d141_lead_in_crossing_fit_and_unfit_and_pre_record_harvest():
    """D141 lead-in: missing harvest before record on year 0, normal computation after,
    and typed MISSING_INPUT when a crossing component cannot lie whole in one cycle."""
    soil = _make_soil()
    computed_params = _computed_c_catalogue()
    declared_params = _site_catalogue()

    # 1) Crossing component that fits whole in one cycle (phase 1).
    cal_fit = _two_year_calendar(crossing=True)
    assert list_phases(cal_fit) == [0, 1]
    assert components_crossing_phase(cal_fit, 1) == ["c2"]

    # Record starts on the exact first day of ag_year 2001 (2001-07-01) -> no pre-record harvest.
    cli_exact = _make_climate(dt.date(2001, 7, 1), dt.date(2004, 6, 30))
    for phase in list_phases(cal_fit):
        moved = phase_calendar(cal_fit, phase)
        repeated = repeat_over_record(moved, dt.date(2001, 7, 1), dt.date(2004, 6, 30))
        if phase == 1:
            assert repeated.cycles[0].index == -1  # D141/D188 lead-in cycle laid out
            assert "c1" in repeated.cycles[0].components_not_laid_out
            assert any(c.cycle == -1 and c.component_id == "c2" for c in repeated.components)
        else:
            assert repeated.cycles[0].index == 0

        res_c = compute_soil_loss(
            calendar=moved,
            climate=cli_exact,
            soil_slope=soil,
            parameters=computed_params,
        )
        _assert_g4_invariants(res_c, [2001, 2002, 2003], start_month=7)
        by_year = {a.ag_year: a for a in res_c.annual}
        # First year lacks a harvest before the record -> typed MISSING_INPUT, no fallback.
        assert by_year[2001].value is None
        assert by_year[2001].missing is not None
        assert by_year[2001].missing.reason == "MISSING_INPUT"
        assert module.NO_HARVEST_BEFORE in (by_year[2001].missing.detail or "")
        assert module.NO_FALLBACK in (by_year[2001].missing.detail or "")
        for mon in [m for m in res_c.monthly if m.ag_year == 2001]:
            assert mon.value is None and mon.missing is not None
            assert mon.missing.reason == "MISSING_INPUT"
        # Subsequent years compute numerically via computed C.
        for yr in (2002, 2003):
            assert by_year[yr].value is not None and by_year[yr].value > 0.0
            assert module.COMPUTED_C in (by_year[yr].source or "")

        # Declared-C fallback computes every covered year across every phase.
        res_d = compute_soil_loss(
            calendar=moved,
            climate=cli_exact,
            soil_slope=soil,
            parameters=declared_params,
        )
        _assert_g4_invariants(res_d, [2001, 2002, 2003], start_month=7)
        assert all(a.value is not None and a.value > 0.0 for a in res_d.annual)

    # 2) Record starts 1 month before first full ag_year (2001-06-01): ag_year 2000 holds
    #    the first cycle's harvest, so ALL full covered years (2001..2003) compute in every phase.
    cli_lead = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    for phase in list_phases(cal_fit):
        moved = phase_calendar(cal_fit, phase)
        res_lead = compute_soil_loss(
            calendar=moved,
            climate=cli_lead,
            soil_slope=soil,
            parameters=computed_params,
        )
        _assert_g4_invariants(res_lead, [2000, 2001, 2002, 2003], start_month=7)
        by_year = {a.ag_year: a for a in res_lead.annual}
        assert by_year[2000].missing is not None and by_year[2000].missing.reason == "NO_COVERAGE"
        for yr in (2001, 2002, 2003):
            assert by_year[yr].value is not None and by_year[yr].value > 0.0

    # 3) Crossing component that CANNOT lie whole in one cycle (overlaps year 1 component):
    #    phase_calendar(cal, 1) marks its dates missing (NOT_COMPUTABLE, D141); EP1 stays typed
    #    Missing (MISSING_INPUT) on computed-C without raising or falling back, while declared-C
    #    still produces numeric values.
    cal_unfit = _make_calendar(
        dt.date(2001, 7, 1),
        dt.date(2003, 6, 30),
        [
            _comp("c1", CROP_A, dt.date(2001, 9, 1), dt.date(2002, 2, 28)),
            _comp("c2", CROP_B, dt.date(2002, 5, 1), dt.date(2002, 11, 30)),
            _comp("c3", CROP_A, dt.date(2002, 10, 1), dt.date(2003, 5, 15)),
        ],
    )
    moved_unfit = phase_calendar(cal_unfit, 1)
    assert any(c.start.date is None and c.end.date is None for c in moved_unfit.components)
    res_unfit_c = compute_soil_loss(
        calendar=moved_unfit,
        climate=cli_lead,
        soil_slope=soil,
        parameters=computed_params,
    )
    _assert_g4_invariants(res_unfit_c, [2000, 2001, 2002, 2003], start_month=7)
    for ann in res_unfit_c.annual:
        if ann.ag_year in (2001, 2002, 2003):
            assert ann.value is None
            assert ann.missing is not None
            assert ann.missing.reason == "MISSING_INPUT"
            assert module.NO_FALLBACK in (ann.missing.detail or "")
    # When no day has a known crop/harvest because of 'c2' missing dates, site-only
    # records of computed-C (e.g. SURFACE_COVER_B_PER_PERCENT_ID) are still checked;
    # omitting one triggers the declared-C fallback and computes every covered year.
    declared_no_computed_c_site = _site_catalogue(
        leave_out=(module.SURFACE_COVER_B_PER_PERCENT_ID,)
    )
    res_unfit_d = compute_soil_loss(
        calendar=moved_unfit,
        climate=cli_lead,
        soil_slope=soil,
        parameters=declared_no_computed_c_site,
    )
    _assert_g4_invariants(res_unfit_d, [2000, 2001, 2002, 2003], start_month=7)
    for ann in res_unfit_d.annual:
        if ann.ag_year in (2001, 2002, 2003):
            assert ann.value is not None and ann.value > 0.0


# =============================================================================
# RUSLE scaling monotonicity (strictly positive linearity in K, P, C, LS, and R)
# =============================================================================


SCALES: tuple[float, ...] = (0.125, 0.5, 1.0, 2.5, 7.25)


@pytest.mark.parametrize("factor_pid", [module.R_ID, module.K_ID, module.P_ID, module.C_ID])
def test_rusle_exact_positive_linearity_and_monotonicity_r_k_p_c(factor_pid: str):
    """Declared-C route: annual and monthly soil loss are strictly positive linear in R, K, P, C."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _make_soil()
    base_params = _site_catalogue()
    base_res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=base_params
    )
    assert isinstance(base_res, SoilLossResults)
    base_annual = [a.value for a in base_res.annual]
    base_monthly = [m.value for m in base_res.monthly]
    assert all(v is not None and v > 0.0 for v in base_annual)
    assert all(v is not None and v > 0.0 for v in base_monthly)

    prev_annual: list[float] | None = None
    prev_monthly: list[float] | None = None
    for scale in SCALES:
        scaled_params = _site_catalogue(
            overrides={f"{factor_pid}.json": {"value": SITE_VALUES[factor_pid] * scale}}
        )
        res = compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=scaled_params
        )
        _assert_g4_invariants(res, [2001, 2002], start_month=7)
        ann_vals = [a.value for a in res.annual]
        mon_vals = [m.value for m in res.monthly]
        assert all(v is not None and v > 0.0 for v in ann_vals)
        assert all(v is not None and v > 0.0 for v in mon_vals)
        for cur, base in zip(ann_vals, base_annual, strict=True):
            assert cur == pytest.approx(scale * base, rel=1e-12)
        for cur, base in zip(mon_vals, base_monthly, strict=True):
            assert cur == pytest.approx(scale * base, rel=1e-12)
        for ag_year in (2001, 2002):
            ann = next(a.value for a in res.annual if a.ag_year == ag_year)
            mon_sum = sum(m.value for m in res.monthly if m.ag_year == ag_year)
            assert mon_sum == pytest.approx(ann, rel=1e-12)
        if prev_annual is not None and prev_monthly is not None:
            assert all(cur > prev for cur, prev in zip(ann_vals, prev_annual, strict=True))
            assert all(cur > prev for cur, prev in zip(mon_vals, prev_monthly, strict=True))
        prev_annual = ann_vals
        prev_monthly = mon_vals


@pytest.mark.parametrize("slope_steepness", [2.0, 5.0, 8.0])
@pytest.mark.parametrize("use_computed_c", [False, True])
def test_rusle_exact_positive_linearity_in_ls_both_slope_regimes(
    slope_steepness: float, use_computed_c: bool
):
    """LS scaling via S coefficients (below and at/above s_break) is strictly positive linear
    on both declared-C and computed-C routes; L scales as (lambda_gamma)**m."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    soil = _make_soil(slope_steepness=slope_steepness)
    covered_years = [2001, 2002, 2003]

    def _make_params(s_scale: float) -> dict[str, dict[str, Any]]:
        overrides = {
            f"{pid}.json": {"value": SITE_VALUES[pid] * s_scale}
            for pid in module.S_COEFFICIENTS.values()
        }
        return (
            _computed_c_catalogue(overrides=overrides)
            if use_computed_c
            else _site_catalogue(overrides=overrides)
        )

    base_res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=_make_params(1.0)
    )
    assert isinstance(base_res, SoilLossResults)
    base_ann = {a.ag_year: a.value for a in base_res.annual if a.ag_year in covered_years}
    base_mon = {
        (m.year, m.month): m.value
        for m in base_res.monthly
        if m.ag_year in covered_years
    }
    assert all(v is not None and v > 0.0 for v in base_ann.values())
    assert all(v is not None and v > 0.0 for v in base_mon.values())

    prev_ann: dict[int, float] | None = None
    for scale in SCALES:
        res = compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=_make_params(scale)
        )
        _assert_g4_invariants(res, [2000, 2001, 2002, 2003], start_month=7)
        cur_ann = {a.ag_year: a.value for a in res.annual if a.ag_year in covered_years}
        cur_mon = {
            (m.year, m.month): m.value for m in res.monthly if m.ag_year in covered_years
        }
        for yr in covered_years:
            assert cur_ann[yr] == pytest.approx(scale * base_ann[yr], rel=1e-12)
        for ym in base_mon:
            assert cur_mon[ym] == pytest.approx(scale * base_mon[ym], rel=1e-12)
        if prev_ann is not None:
            assert all(cur_ann[yr] > prev_ann[yr] for yr in covered_years)
        prev_ann = cur_ann

    # Power-law scaling in slope_length: L(gamma * lambda) = gamma**m * L(lambda).
    theta = math.atan(slope_steepness / 100.0)
    sine = math.sin(theta)
    beta = (sine / SITE_VALUES["rusle_l_beta_sine_divisor"]) / (
        SITE_VALUES["rusle_l_beta_denominator_sine_coefficient"]
        * (sine ** SITE_VALUES["rusle_l_beta_denominator_sine_exponent"])
        + SITE_VALUES["rusle_l_beta_denominator_constant"]
    )
    m_exp = beta / (1.0 + beta)
    assert 0.0 < m_exp < 1.0

    prev_len_ann: dict[int, float] | None = None
    for gamma in (0.25, 0.5, 1.0, 2.0, 4.0):
        res_len = compute_soil_loss(
            calendar=cal,
            climate=cli,
            soil_slope=_make_soil(
                slope_steepness=slope_steepness, slope_length=15.0 * gamma
            ),
            parameters=_make_params(1.0),
        )
        cur_len_ann = {
            a.ag_year: a.value for a in res_len.annual if a.ag_year in covered_years
        }
        for yr in covered_years:
            assert cur_len_ann[yr] == pytest.approx(
                (gamma**m_exp) * base_ann[yr], rel=1e-12
            )
        if prev_len_ann is not None:
            assert all(cur_len_ann[yr] > prev_len_ann[yr] for yr in covered_years)
        prev_len_ann = cur_len_ann


@pytest.mark.parametrize("factor_pid", [module.R_ID, module.K_ID, module.P_ID])
def test_rusle_exact_positive_linearity_in_r_k_p_on_computed_c_route(factor_pid: str):
    """Computed-C route: scaling R, K, or P by alpha > 0 scales all covered annual/monthly
    values by exact alpha while keeping the implied C_year invariant."""
    cal = _two_year_calendar(crossing=True)
    cli = _make_climate(dt.date(2001, 6, 1), dt.date(2004, 6, 30))
    soil = _make_soil()
    covered_years = [2001, 2002, 2003]

    base_res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=_computed_c_catalogue()
    )
    assert isinstance(base_res, SoilLossResults)
    base_ann = {a.ag_year: a.value for a in base_res.annual if a.ag_year in covered_years}
    base_mon = {
        (m.year, m.month): m.value
        for m in base_res.monthly
        if m.ag_year in covered_years
    }
    # Computed C distinguishes years with different crop/residue trajectories.
    assert len({round(v, 9) for v in base_ann.values()}) > 1

    prev_ann: dict[int, float] | None = None
    for scale in SCALES:
        params = _computed_c_catalogue(
            overrides={f"{factor_pid}.json": {"value": SITE_VALUES[factor_pid] * scale}}
        )
        res = compute_soil_loss(
            calendar=cal, climate=cli, soil_slope=soil, parameters=params
        )
        cur_ann = {a.ag_year: a.value for a in res.annual if a.ag_year in covered_years}
        cur_mon = {
            (m.year, m.month): m.value for m in res.monthly if m.ag_year in covered_years
        }
        for yr in covered_years:
            assert cur_ann[yr] == pytest.approx(scale * base_ann[yr], rel=1e-12)
        for ym in base_mon:
            assert cur_mon[ym] == pytest.approx(scale * base_mon[ym], rel=1e-12)
        if prev_ann is not None:
            assert all(cur_ann[yr] > prev_ann[yr] for yr in covered_years)
        prev_ann = cur_ann


def test_rusle_joint_multilinearity_and_monthly_erosivity_homogeneity():
    """Joint scaling in (R, K, LS, C, P) multiplies soil loss by the product of scales;
    scaling all twelve monthly erosivity records together is degree-0 homogeneous."""
    cal = _two_year_calendar()
    cli = _make_climate(dt.date(2001, 7, 1), dt.date(2003, 6, 30))
    soil = _make_soil(slope_steepness=3.0)

    base_res = compute_soil_loss(
        calendar=cal, climate=cli, soil_slope=soil, parameters=_site_catalogue()
    )
    assert isinstance(base_res, SoilLossResults)

    scales = {"r": 1.75, "k": 2.25, "ls": 0.6, "c": 3.5, "p": 0.4}
    joint_scale = math.prod(scales.values())
    overrides: dict[str, dict[str, Any]] = {
        f"{module.R_ID}.json": {"value": SITE_VALUES[module.R_ID] * scales["r"]},
        f"{module.K_ID}.json": {"value": SITE_VALUES[module.K_ID] * scales["k"]},
        f"{module.C_ID}.json": {"value": SITE_VALUES[module.C_ID] * scales["c"]},
        f"{module.P_ID}.json": {"value": SITE_VALUES[module.P_ID] * scales["p"]},
        **{
            f"{pid}.json": {"value": SITE_VALUES[pid] * scales["ls"]}
            for pid in module.S_COEFFICIENTS.values()
        },
    }
    joint_res = compute_soil_loss(
        calendar=cal,
        climate=cli,
        soil_slope=soil,
        parameters=_site_catalogue(overrides=overrides),
    )
    assert isinstance(joint_res, SoilLossResults)
    for cur, base in zip(joint_res.annual, base_res.annual, strict=True):
        assert cur.value == pytest.approx(joint_scale * base.value, rel=1e-11)
    for cur, base in zip(joint_res.monthly, base_res.monthly, strict=True):
        assert cur.value == pytest.approx(joint_scale * base.value, rel=1e-11)

    # Common scaling of all 12 monthly erosivity records leaves every value invariant.
    for common_scale in (0.1, 3.7, 100.0):
        monthly_overrides = {
            f"{pid}.json": {"value": SITE_VALUES[pid] * common_scale}
            for pid in module.MONTHLY_EROSIVITY_IDS
        }
        homog_res = compute_soil_loss(
            calendar=cal,
            climate=cli,
            soil_slope=soil,
            parameters=_site_catalogue(overrides=monthly_overrides),
        )
        assert isinstance(homog_res, SoilLossResults)
        for cur, base in zip(homog_res.annual, base_res.annual, strict=True):
            assert cur.value == pytest.approx(base.value, rel=1e-12)
        for cur, base in zip(homog_res.monthly, base_res.monthly, strict=True):
            assert cur.value == pytest.approx(base.value, rel=1e-12)
