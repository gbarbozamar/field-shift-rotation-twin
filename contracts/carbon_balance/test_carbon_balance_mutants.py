"""Targeted validator-boundary and mutant-killing tests for ``contracts/carbon_balance/models.py``.

Covers StockSeries initial/step checks, FlowSeries continuity across year
boundaries, variant identifier pattern, SoilCarbonTrend model/computation rules,
and injected validator mutants. Every identifier and number is PLACEHOLDER data.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.carbon_balance import models as cb_models
from contracts.carbon_balance.models import CarbonBalance, StepValue

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_carbon_balance.json"


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


# --- 1. Step continuity & single-month horizon bounds -------------------------


def test_single_month_step_and_december_to_january_rollover_accepted() -> None:
    step = StepValue(
        start={"year": 2001, "month": 12},
        end={"year": 2001, "month": 12},
        value=0.0,
    )
    assert step.start == step.end

    data = _load()
    for series in [data["total_stock"], *data["pools"], *data["flows"]]:
        series["steps"][0]["end"] = {"year": 2001, "month": 12}
        series["steps"][1]["start"] = {"year": 2002, "month": 1}
    loaded = CarbonBalance.model_validate(data)
    assert loaded.total_stock.steps[1].start.month == 1


def test_overlapping_steps_rejected() -> None:
    data = _load()
    for series in [data["total_stock"], *data["pools"], *data["flows"]]:
        series["steps"][0]["end"] = {"year": 2002, "month": 1}
        series["steps"][1]["start"] = {"year": 2002, "month": 1}
    with pytest.raises(ValidationError, match="no gap and no overlap"):
        CarbonBalance.model_validate(data)


def test_merged_steps_on_flow_covering_same_horizon_rejected() -> None:
    data = _load()
    flow = data["flows"][0]
    flow["steps"] = [
        {
            "start": copy.deepcopy(data["horizon"]["start"]),
            "end": copy.deepcopy(data["horizon"]["end"]),
            "value": 1.0,
        }
    ]
    with pytest.raises(ValidationError, match="same steps as total_stock"):
        CarbonBalance.model_validate(data)


def test_empty_pools_and_flows_accepted_and_total_stock_quantity_collision_rejected() -> (
    None
):
    data = _load()
    data["pools"] = []
    data["flows"] = []
    loaded = CarbonBalance.model_validate(data)
    assert loaded.pools == [] and loaded.flows == []

    data = _load()
    data["flows"][0]["quantity"] = data["total_stock"]["quantity"]
    with pytest.raises(ValidationError, match="appears more than once"):
        CarbonBalance.model_validate(data)


# --- 2. Stock initial provenance, range, and unit rules -----------------------


def test_initial_allows_independent_provenance_and_range_while_enforcing_unit() -> None:
    data = _load()
    data["total_stock"]["initial"] = {
        "value": 40.0,
        "unit": data["total_stock"]["unit"],
        "provenance": "DECLARED",
        "source": "PLACEHOLDER source",
        "range": {"low": 40.0, "high": 50.0, "kind": "PLACEHOLDER_kind"},
    }
    loaded = CarbonBalance.model_validate(data)
    assert loaded.total_stock.initial.provenance == "DECLARED"

    data["total_stock"]["initial"]["value"] = 39.999
    with pytest.raises(ValidationError, match="outside its bounds"):
        CarbonBalance.model_validate(data)


# --- 3. Variant & SoilCarbonTrend rules ---------------------------------------


@pytest.mark.parametrize(
    ("variant", "accepted"),
    [
        ("placeholder_a", True),
        ("a", True),
        ("placeholder_1", True),
        ("PLACEHOLDER", False),
        ("placeholder-a", False),
        ("1placeholder", False),
        ("", False),
    ],
)
def test_variant_quantity_id_boundaries(variant: str, *, accepted: bool) -> None:
    data = _load()
    data["variant"] = variant
    if accepted:
        assert CarbonBalance.model_validate(data).variant == variant
    else:
        with pytest.raises(ValidationError, match="variant"):
            CarbonBalance.model_validate(data)


def test_trend_reordered_accepted_and_wrong_direction_rejected() -> None:
    data = _load()
    data["soil_carbon_trend"].reverse()
    loaded = CarbonBalance.model_validate(data)
    assert len(loaded.soil_carbon_trend) == 3

    data["soil_carbon_trend"][0]["direction"] = "lower_is_better"
    with pytest.raises(ValidationError, match="higher_is_better"):
        CarbonBalance.model_validate(data)


# --- 4. Injected validator mutants --------------------------------------------


def test_mutant_weakened_check_steps_allows_overlapping_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    for series in [data["total_stock"], *data["pools"], *data["flows"]]:
        series["steps"][0]["end"] = {"year": 2002, "month": 1}
        series["steps"][1]["start"] = {"year": 2002, "month": 1}

    with pytest.raises(ValidationError, match="no gap and no overlap"):
        CarbonBalance.model_validate(data)

    monkeypatch.setattr(cb_models, "_check_steps", lambda steps, what: None)
    accepted = CarbonBalance.model_validate(data)
    assert accepted.total_stock.steps[0].end == accepted.total_stock.steps[1].start


def test_mutant_weakened_covers_horizon_allows_short_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["horizon"]["end"] = {"year": 2004, "month": 12}

    with pytest.raises(ValidationError, match="from the first month of the horizon"):
        CarbonBalance.model_validate(data)

    monkeypatch.setattr(cb_models, "_covers_horizon", lambda s, h, w: None)
    accepted = CarbonBalance.model_validate(data)
    assert accepted.horizon.end.year == 2004


def test_mutant_weakened_bounds_allows_mismatched_flow_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["flows"][0]["steps"] = [
        {
            "start": copy.deepcopy(data["horizon"]["start"]),
            "end": copy.deepcopy(data["horizon"]["end"]),
            "value": 1.0,
        }
    ]
    with pytest.raises(ValidationError, match="same steps as total_stock"):
        CarbonBalance.model_validate(data)

    monkeypatch.setattr(cb_models, "_bounds", lambda s: [(0, 0)])
    accepted = CarbonBalance.model_validate(data)
    assert len(accepted.flows[0].steps) == 1


def test_mutant_weakened_trend_computations_allows_duplicate_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["soil_carbon_trend"][2] = copy.deepcopy(data["soil_carbon_trend"][0])
    with pytest.raises(ValidationError, match="each of the three computations"):
        CarbonBalance.model_validate(data)

    monkeypatch.setattr(
        cb_models,
        "TREND_COMPUTATIONS",
        ("end_minus_start", "end_minus_start", "fitted_slope"),
    )
    accepted = CarbonBalance.model_validate(data)
    assert len(accepted.soil_carbon_trend) == 3
