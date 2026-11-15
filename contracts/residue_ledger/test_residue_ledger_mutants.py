"""Targeted validator-boundary and mutant-killing tests for ``contracts/residue_ledger/models.py``.

Covers D141/D160 lead-in bounds, D194 origin grouping, D221 monthly-origin ==
annual invariants, #361 harvest-in-ag-year start-month offset boundaries, and
injected validator mutants. Every identifier and number is PLACEHOLDER data.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.residue_ledger.models import (
    ResidueLedger,
    monthly_quantity,
    series_origin,
)

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_residue_ledger.json"
MISSING_INPUT = {"reason": "MISSING_INPUT", "detail": "PLACEHOLDER input"}


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _set_start_month(data: dict[str, Any], start_month: int) -> None:
    first = data["first_ag_year"] * 12 + (start_month - 1)
    for series in data["monthly_carbon_inputs"]:
        for idx, item in enumerate(series["months"]):
            yr, m0 = divmod(first + idx, 12)
            item["year"] = yr
            item["month"] = m0 + 1
        series["start"] = {"year": data["first_ag_year"], "month": start_month}
        last = series["months"][-1]
        series["end"] = {"year": last["year"], "month": last["month"]}


# --- 1. #361 Harvest-in-ag-year offset bounds [0, 12) -------------------------


@pytest.mark.parametrize(
    ("harvest_iso", "ag_year", "accepted"),
    [
        ("2001-07-01", 2001, True),  # offset == 0 (inclusive lower bound)
        ("2002-06-30", 2001, True),  # offset == 11 (inclusive upper bound)
        ("2001-06-30", 2001, False),  # offset == -1 (before ag_year)
        ("2002-07-01", 2001, False),  # offset == 12 (after ag_year)
    ],
    ids=[
        "offset-0-accepted",
        "offset-11-accepted",
        "offset-neg1-rejected",
        "offset-12-rejected",
    ],
)
def test_harvest_in_ag_year_offset_boundaries(
    harvest_iso: str, ag_year: int, *, accepted: bool
) -> None:
    data = _load()
    _set_start_month(data, 7)
    # Keep component 0 in ag_year 2001/2002 matching harvest_iso.
    comp0 = data["components"][0]
    comp0["harvest"]["date"] = harvest_iso
    comp0["ag_year"] = ag_year
    # Keep component 2 in a valid month for July start (2002-07-15 -> ag_year 2002).
    data["components"][2]["harvest"]["date"] = "2002-07-15"
    data["components"][2]["ag_year"] = 2002

    if accepted:
        ledger = ResidueLedger.model_validate(data)
        assert ledger.components[0].harvest.date == dt.date.fromisoformat(harvest_iso)
    else:
        with pytest.raises(ValidationError, match="does not hold that day"):
            ResidueLedger.model_validate(data)


def test_undated_harvests_bypass_start_month_bound_when_ag_year_null() -> None:
    data = _load()
    for comp in data["components"]:
        comp["harvest"] = {"date": None, "missing": dict(MISSING_INPUT)}
        comp["ag_year"] = None
    _set_start_month(data, 11)
    ledger = ResidueLedger.model_validate(data)
    assert all(c.harvest.date is None for c in ledger.components)


# --- 2. D194 & D221 monthly-origin == annual invariants -----------------------


def test_d221_rejects_extra_monthly_month_and_extra_monthly_origin() -> None:
    # 13 months for a 1-year slice (total 25 months for a 2-year ledger) is rejected.
    data = _load()
    s0 = data["monthly_carbon_inputs"][0]
    s0["end"] = {"year": 2003, "month": 1}
    s0["months"].append({"year": 2003, "month": 1, "value": 0.0})
    with pytest.raises(ValidationError, match="every month of the agricultural years"):
        ResidueLedger.model_validate(data)

    # Removing all belowground annual series for crop_a while keeping its monthly series is rejected.
    data = _load()
    data["annual_carbon_inputs"] = [
        s
        for s in data["annual_carbon_inputs"]
        if s["origin"] != "placeholder_crop_a_belowground"
    ]
    with pytest.raises(ValidationError, match="without an annual series"):
        ResidueLedger.model_validate(data)


def test_d194_helpers_and_same_unit_for_components_and_series() -> None:
    assert series_origin("placeholder_crop", "aboveground_carbon_retained") == (
        "placeholder_crop_aboveground"
    )
    assert series_origin("placeholder_crop", "root_carbon") == (
        "placeholder_crop_belowground"
    )
    assert series_origin("placeholder_crop", "rhizodeposit_carbon") == (
        "placeholder_crop_belowground"
    )
    assert monthly_quantity("placeholder_crop_aboveground") == (
        "placeholder_crop_aboveground_carbon_input"
    )

    # carbon_input_unit == carbon_unit is allowed when series match carbon_input_unit.
    data = _load()
    data["carbon_input_unit"] = data["carbon_unit"]
    for series in data["annual_carbon_inputs"] + data["monthly_carbon_inputs"]:
        series["unit"] = data["carbon_unit"]
    ledger = ResidueLedger.model_validate(data)
    assert ledger.carbon_input_unit == ledger.carbon_unit


# --- 3. Year range, lead-in cycle, NotGiven, and empty ledger bounds ----------


def test_single_year_ledger_and_same_component_in_lead_in_and_cycle_zero() -> None:
    data = _load()
    # Shrink to single ag_year 2001 with same component_id in cycle -1 and cycle 0.
    data["last_ag_year"] = 2001
    data["components"] = [
        data["components"][0],
        copy.deepcopy(data["components"][0]),
        data["components"][1],
    ]
    data["components"][0]["cycle"] = -1
    data["components"][1]["cycle"] = 0
    data["components"][2]["cycle"] = 0
    for series in data["annual_carbon_inputs"]:
        series["last_ag_year"] = 2001
        series["years"] = series["years"][:1]
    for series in data["monthly_carbon_inputs"]:
        series["end"] = {"year": 2001, "month": 12}
        series["months"] = series["months"][:12]

    ledger = ResidueLedger.model_validate(data)
    assert (ledger.first_ag_year, ledger.last_ag_year) == (2001, 2001)
    assert [c.cycle for c in ledger.components] == [-1, 0, 0]


def test_not_given_purpose_and_residue_management_accepted() -> None:
    data = _load()
    data["components"][0]["purpose"] = {"missing": {"reason": "NOT_DECLARED"}}
    data["components"][0]["residue_management"] = {
        "missing": {"reason": "NOT_DECLARED"}
    }
    ledger = ResidueLedger.model_validate(data)
    assert ledger.components[0].purpose.missing.reason == "NOT_DECLARED"


# --- 4. Injected validator mutants --------------------------------------------


def test_mutant_weakened_start_month_check_allows_harvest_outside_ag_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    _set_start_month(data, 7)
    data["components"][0]["harvest"]["date"] = "2002-07-01"
    data["components"][0]["ag_year"] = 2001

    with pytest.raises(ValidationError, match="does not hold that day"):
        ResidueLedger.model_validate(data)

    monkeypatch.setattr(ResidueLedger, "_check_start_month", lambda self, m: None)
    accepted = ResidueLedger.model_validate(data)
    assert accepted.components[0].ag_year == 2001


def test_mutant_weakened_monthly_check_allows_missing_monthly_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["monthly_carbon_inputs"] = []
    with pytest.raises(ValidationError, match="without a monthly series"):
        ResidueLedger.model_validate(data)

    monkeypatch.setattr(ResidueLedger, "_check_monthly_series", lambda self: None)
    accepted = ResidueLedger.model_validate(data)
    assert accepted.monthly_carbon_inputs == []


def test_mutant_weakened_series_check_allows_wrong_d194_origin_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    for s in data["annual_carbon_inputs"]:
        if s["quantity"].endswith("_root_carbon"):
            s["origin"] = "placeholder_crop_a_aboveground"
            break

    with pytest.raises(ValidationError, match="belowground"):
        ResidueLedger.model_validate(data)

    monkeypatch.setattr(ResidueLedger, "_check_series", lambda self: None)
    accepted = ResidueLedger.model_validate(data)
    assert any(
        s.quantity.endswith("_root_carbon") and s.origin.endswith("_aboveground")
        for s in accepted.annual_carbon_inputs
    )


def test_mutant_weakened_years_check_allows_inverted_years(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["first_ag_year"] = 2005
    data["last_ag_year"] = 2002
    data["annual_carbon_inputs"] = []
    data["monthly_carbon_inputs"] = []

    with pytest.raises(ValidationError, match="last_ag_year is before first_ag_year"):
        ResidueLedger.model_validate(data)

    monkeypatch.setattr(ResidueLedger, "_check_years", lambda self: None)
    accepted = ResidueLedger.model_validate(data)
    assert accepted.first_ag_year > accepted.last_ag_year
