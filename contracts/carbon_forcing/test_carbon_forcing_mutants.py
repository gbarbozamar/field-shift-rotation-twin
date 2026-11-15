"""Targeted validator-boundary and mutant-killing tests for ``contracts/carbon_forcing/models.py``.

Covers ForcingHorizon bounds, whole-agricultural-year annual series checks,
D65 ``soil_cover`` and ``starting_state`` bounds and absence rules, and
injected validator mutants. Every identifier and number is PLACEHOLDER data.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.carbon_forcing import models as cf_models
from contracts.carbon_forcing.models import (
    CarbonForcing,
    ForcingHorizon,
    StartingStateValue,
)
from contracts.inputs.site_climate import YearMonth

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_carbon_forcing.json"
SOURCE = "PLACEHOLDER source"
UNIT = "PLACEHOLDER_unit"


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _rehorizon(data: dict[str, Any], start: tuple[int, int], months_count: int) -> None:
    sy, sm = start
    first = sy * 12 + (sm - 1)
    ey, em0 = divmod(first + months_count - 1, 12)
    data["horizon"] = {
        "start": {"year": sy, "month": sm},
        "end": {"year": ey, "month": em0 + 1},
    }
    for series in data["climate"] + data["carbon_inputs"] + data["soil_cover"]:
        series["start"] = copy.deepcopy(data["horizon"]["start"])
        series["end"] = copy.deepcopy(data["horizon"]["end"])
        series["months"] = [
            {
                "year": divmod(first + i, 12)[0],
                "month": divmod(first + i, 12)[1] + 1,
                "value": 1.0,
            }
            for i in range(months_count)
        ]


# --- 1. ForcingHorizon & _ag_years_of boundaries ------------------------------


def test_single_month_horizon_accepted_without_annual_series() -> None:
    horizon = ForcingHorizon(
        start=YearMonth(year=2001, month=1),
        end=YearMonth(year=2001, month=1),
    )
    assert horizon.start == horizon.end

    data = _load()
    _rehorizon(data, (2001, 1), 1)
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []
    loaded = CarbonForcing.model_validate(data)
    assert loaded.horizon.start == loaded.horizon.end


@pytest.mark.parametrize("months_count", [11, 13], ids=["11-months", "13-months"])
def test_non_multiple_of_12_horizon_rejected_with_annual_series(
    months_count: int,
) -> None:
    data = _load()
    _rehorizon(data, (2001, 1), months_count)
    with pytest.raises(ValidationError, match="whole number of agricultural years"):
        CarbonForcing.model_validate(data)


def test_non_january_multi_year_horizon_maps_exact_ag_years() -> None:
    data = _load()
    _rehorizon(data, (2001, 7), 24)  # 2001-07..2003-06 -> ag_years 2001..2002
    for series in data["annual_climate"] + data["annual_carbon_inputs"]:
        series["first_ag_year"] = 2001
        series["last_ag_year"] = 2002
        second = copy.deepcopy(series["years"][0])
        second["ag_year"] = 2002
        series["years"] = [series["years"][0], second]

    loaded = CarbonForcing.model_validate(data)
    assert loaded.annual_climate[0].first_ag_year == 2001
    assert loaded.annual_climate[0].last_ag_year == 2002

    # Off-by-one last_ag_year is rejected.
    data["annual_climate"][0]["last_ag_year"] = 2003
    data["annual_climate"][0]["years"].append({"ag_year": 2003, "value": 1.0})
    with pytest.raises(ValidationError, match="agricultural years of the horizon"):
        CarbonForcing.model_validate(data)


# --- 2. D65 soil_cover & starting_state bounds --------------------------------


def test_soil_cover_horizon_bounds_and_header_rules() -> None:
    # soil_cover running one month past horizon.end is rejected.
    data = _load()
    sc = data["soil_cover"][0]
    sc["end"] = {"year": 2002, "month": 1}
    sc["months"].append({"year": 2002, "month": 1, "value": 0.5})
    with pytest.raises(ValidationError, match="start and end are those of the horizon"):
        CarbonForcing.model_validate(data)

    # soil_cover starting one month before horizon.start is rejected.
    data = _load()
    sc = data["soil_cover"][0]
    sc["start"] = {"year": 2000, "month": 12}
    sc["months"].insert(0, {"year": 2000, "month": 12, "value": 0.5})
    with pytest.raises(ValidationError, match="start and end are those of the horizon"):
        CarbonForcing.model_validate(data)

    # All-missing soil_cover MUST omit provenance and range_missing.
    data = _load()
    sc = data["soil_cover"][0]
    sc["months"] = [
        {
            "year": m["year"],
            "month": m["month"],
            "value": None,
            "missing": {"reason": "NOT_DECLARED"},
        }
        for m in sc["months"]
    ]
    with pytest.raises(ValidationError, match="carries no provenance label"):
        CarbonForcing.model_validate(data)

    # Same quantity identifier is allowed across climate and soil_cover.
    data = _load()
    data["soil_cover"][0]["quantity"] = data["climate"][0]["quantity"]
    loaded = CarbonForcing.model_validate(data)
    assert loaded.soil_cover[0].quantity == loaded.climate[0].quantity


@pytest.mark.parametrize("val", [10.0, 20.0], ids=["at-low", "at-high"])
def test_starting_state_inclusive_range_bounds_and_outside_rejection(
    val: float,
) -> None:
    item = StartingStateValue(
        quantity="placeholder_pool",
        value=val,
        unit=UNIT,
        provenance="DECLARED",
        source=SOURCE,
        range={"low": 10.0, "high": 20.0, "kind": "PLACEHOLDER_kind"},
    )
    assert item.value == val

    with pytest.raises(ValidationError, match="outside its bounds"):
        StartingStateValue(
            quantity="placeholder_pool",
            value=9.999,
            unit=UNIT,
            provenance="DECLARED",
            source=SOURCE,
            range={"low": 10.0, "high": 20.0, "kind": "PLACEHOLDER_kind"},
        )

    # Missing starting_state rejects range_missing and provenance.
    with pytest.raises(ValidationError, match="missing value has no range"):
        StartingStateValue(
            quantity="placeholder_pool",
            value=None,
            unit=UNIT,
            missing={"reason": "NOT_DECLARED"},
            range_missing={"reason": "NOT_AVAILABLE"},
        )


def test_starting_state_allows_shared_quantity_with_soil_properties() -> None:
    data = _load()
    data["starting_state"][0]["quantity"] = data["soil_properties"][0]["quantity"]
    loaded = CarbonForcing.model_validate(data)
    assert loaded.starting_state[0].quantity == loaded.soil_properties[0].quantity


# --- 3. Injected validator mutants --------------------------------------------


def test_mutant_weakened_covers_horizon_allows_short_soil_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["soil_cover"][0]["months"].pop()
    data["soil_cover"][0]["end"] = {"year": 2001, "month": 11}
    with pytest.raises(ValidationError, match="start and end are those of the horizon"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(cf_models, "_covers_horizon", lambda s, h, w: None)
    accepted = CarbonForcing.model_validate(data)
    assert len(accepted.soil_cover[0].months) == 11


def test_mutant_weakened_unique_quantities_allows_duplicate_starting_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["starting_state"][1]["quantity"] = data["starting_state"][0]["quantity"]
    with pytest.raises(ValidationError, match="appears more than once"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(cf_models, "_unique_quantities", lambda items, what: None)
    accepted = CarbonForcing.model_validate(data)
    assert accepted.starting_state[0].quantity == accepted.starting_state[1].quantity


def test_mutant_weakened_ag_years_of_allows_11_month_horizon_with_annual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    _rehorizon(data, (2001, 1), 11)
    with pytest.raises(ValidationError, match="whole number of agricultural years"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(
        cf_models, "_ag_years_of", lambda h: (h.start.year, h.start.year)
    )
    accepted = CarbonForcing.model_validate(data)
    assert accepted.horizon.end.month == 11


def test_mutant_weakened_covers_ag_years_allows_shifted_annual_carbon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    s = data["annual_carbon_inputs"][0]
    s["first_ag_year"] = 2002
    s["last_ag_year"] = 2002
    s["years"][0]["ag_year"] = 2002
    with pytest.raises(ValidationError, match="agricultural years of the horizon"):
        CarbonForcing.model_validate(data)

    monkeypatch.setattr(cf_models, "_covers_ag_years", lambda s, y, w: None)
    accepted = CarbonForcing.model_validate(data)
    assert accepted.annual_carbon_inputs[0].first_ag_year == 2002
