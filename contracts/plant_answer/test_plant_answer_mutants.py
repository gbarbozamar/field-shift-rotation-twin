"""Targeted validator-boundary and mutant-killing tests for ``contracts/plant_answer/plant_answer.py``.

Covers D148 soil-loss labels, D245 scope & forbidden phrase checks, D249 & D259
provenance/range labels, D250 phase-1 limit, PlantRequest/PlantAnswer rotation
bounds, PriceRange strict inequality, RainStressFactor > 0, SourceOut UTC
timezone checks, check_answer_against_request, and injected validator mutants.
Every identifier and number introduced here is PLACEHOLDER test data only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.plant_answer import plant_answer as pa_module
from contracts.plant_answer.plant_answer import (
    ANSWER_SCOPE,
    D148_SOIL_LOSS_LABEL,
    PHASE_ONE_ONLY,
    PlantAnswer,
    PlantRequest,
    PriceRange,
    RainStressApplied,
    SoilLossOut,
    SourceOut,
    check_answer_against_request,
)

EXAMPLES = Path(__file__).parent / "examples"


def _load_request() -> dict[str, Any]:
    return json.loads(
        (EXAMPLES / "PLACEHOLDER_plant_request.json").read_text(encoding="utf-8")
    )


def _load_answer() -> dict[str, Any]:
    return json.loads(
        (EXAMPLES / "PLACEHOLDER_plant_answer.json").read_text(encoding="utf-8")
    )


def _label_all_soil_losses(answer: dict[str, Any]) -> None:
    for option in answer["options"]:
        for item in option["soil_loss"].values():
            if item["value"] is not None:
                item["label"] = D148_SOIL_LOSS_LABEL


# --- 1. D245 forbidden phrases, D250 phase-1 limit, D148 soil-loss labels -----


@pytest.mark.parametrize(
    "bad_scope",
    [
        "Plant this rotation",
        f"{ANSWER_SCOPE}.",
        "the most margin within the limit you declared",
    ],
)
def test_d245_scope_rejects_forbidden_or_altered_phrases(bad_scope: str) -> None:
    data = _load_answer()
    data["scope"] = bad_scope
    with pytest.raises(ValidationError, match="D245"):
        PlantAnswer.model_validate(data)


def test_d250_declared_limits_requires_exact_phase_one_only_phrase() -> None:
    data = _load_answer()
    data["declared_limits"] = ["phase 1 only"]
    with pytest.raises(ValidationError, match="declared limits include"):
        PlantAnswer.model_validate(data)


def test_d148_real_answer_requires_label_on_every_present_soil_loss_and_forbids_on_missing() -> (
    None
):
    data = _load_answer()
    data["example_data"] = False
    _label_all_soil_losses(data)
    # Valid when every present soil-loss item carries D148_SOIL_LOSS_LABEL.
    loaded = PlantAnswer.model_validate(data)
    assert loaded.example_data is False

    # Removing the label from a single kind (la_nina) on one option is rejected.
    missing_one = copy.deepcopy(data)
    for opt in missing_one["options"]:
        if opt["soil_loss"]["la_nina"]["value"] is not None:
            opt["soil_loss"]["la_nina"]["label"] = None
            break
    with pytest.raises(ValidationError, match="label of D148"):
        PlantAnswer.model_validate(missing_one)

    # Setting D148 label on a missing SoilLossOut (value=None) is rejected.
    with pytest.raises(ValidationError, match="missing value carries no label"):
        SoilLossOut(
            value=None,
            unit="t ha-1 yr-1",
            n_years=0,
            ag_years=[],
            reason="NO_COVERAGE",
            detail="PLACEHOLDER missing",
            sources=[],
            assumption=False,
            label=D148_SOIL_LOSS_LABEL,
        )


# --- 2. D249 / D259 labels & numeric boundaries -------------------------------


def test_price_range_strict_low_below_high_and_zero_boundary() -> None:
    valid = PriceRange(low=0.0, high=0.01, unit="USD t-1", provenance="DECLARED")
    assert valid.low == 0.0

    # low == high is rejected (kills `<` -> `<=`).
    with pytest.raises(ValidationError, match="low is below high"):
        PriceRange(low=400.0, high=400.0, unit="USD t-1", provenance="DECLARED")

    with pytest.raises(ValidationError, match="not negative"):
        PriceRange(low=-0.01, high=400.0, unit="USD t-1", provenance="DECLARED")


def test_rain_stress_factor_above_zero_boundary_and_timezone_check() -> None:
    with pytest.raises(ValidationError, match="above zero"):
        RainStressApplied(
            factor=0.0,
            declared={
                "value": 0.0,
                "unit": "dimensionless",
                "provenance": "DECLARED",
                "source": "PLACEHOLDER",
                "range_missing": {"reason": "NOT_DECLARED"},
            },
            detail="PLACEHOLDER",
            label="stress test",
            applied=True,
        )

    applied = RainStressApplied(
        factor=1e-6,
        declared={
            "value": 1e-6,
            "unit": "dimensionless",
            "provenance": "DECLARED",
            "source": "PLACEHOLDER",
            "range_missing": {"reason": "NOT_DECLARED"},
        },
        detail="PLACEHOLDER",
        label="stress test",
        applied=True,
    )
    assert applied.factor == 1e-6

    # SourceOut naive datetime is rejected; aware datetime serializes to UTC Z.
    with pytest.raises(ValidationError, match="no time zone"):
        SourceOut(
            id="PLACEHOLDER_src",
            contract="results",
            state="cached",
            retrieved_at="2026-11-15T10:30:00",
            time_zone=None,
            request=None,
            attribution=None,
            missing_reason=None,
            detail=None,
        )


def test_tipping_point_boundary_at_today_and_range_endpoints_accepted() -> None:
    data = _load_answer()
    today = data["tipping_price"]["today"]
    low = data["tipping_price"]["price_range"]["low"]
    # up.price == today with distance_percent == 0.0 is accepted (kills < vs <=).
    data["tipping_price"]["up"] = {
        "direction": "up",
        "price": today,
        "takes_over": None,
        "answer_after": "not_resolved",
        "distance_percent": 0.0,
        "reason": None,
        "detail": None,
        "unit": "USD t-1",
        "provenance": "DERIVED",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
        "distance_provenance": "DERIVED",
        "distance_range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
    }
    # down.price == price_range.low is accepted (kills <= vs <).
    data["tipping_price"]["down"] = {
        "direction": "down",
        "price": low,
        "takes_over": None,
        "answer_after": "not_resolved",
        "distance_percent": -((today - low) / today) * 100.0,
        "reason": None,
        "detail": None,
        "unit": "USD t-1",
        "provenance": "DERIVED",
        "range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
        "distance_provenance": "DERIVED",
        "distance_range_missing": {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER"},
    }
    loaded = PlantAnswer.model_validate(data)
    assert loaded.tipping_price.up.price == today
    assert loaded.tipping_price.down.price == low


def test_request_and_answer_rotation_count_bounds_3_and_5() -> None:
    req = _load_request()
    assert len(req["rotations"]) == 3
    PlantRequest.model_validate(req)

    # Extend to 5 rotations (upper bound).
    for idx in range(3, 5):
        extra = copy.deepcopy(req["rotations"][0])
        extra["rotation_id"] = f"PLACEHOLDER_rot_{idx}"
        req["rotations"].append(extra)
    assert len(PlantRequest.model_validate(req).rotations) == 5

    # 6th rotation rejected.
    extra6 = copy.deepcopy(req["rotations"][0])
    extra6["rotation_id"] = "PLACEHOLDER_rot_5"
    req["rotations"].append(extra6)
    with pytest.raises(ValidationError, match="at most 5"):
        PlantRequest.model_validate(req)


def test_check_answer_against_request_missing_soybean_price_propagates_to_today() -> (
    None
):
    req = _load_request()
    req["economic_facts"]["crops"][0]["price"] = {
        "value": None,
        "unit": "USD t-1",
        "missing": {"reason": "NOT_DECLARED"},
    }
    request = PlantRequest.model_validate(req)
    # Answer still has numeric today -> refused by check_answer_against_request.
    answer = PlantAnswer.model_validate(_load_answer())
    with pytest.raises(ValueError, match="declared soybean price"):
        check_answer_against_request(request, answer)


# --- 3. Injected validator mutants --------------------------------------------


def test_mutant_weakened_answer_scope_allows_forbidden_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_answer()
    data["scope"] = "Plant this rotation"
    with pytest.raises(ValidationError, match="D245"):
        PlantAnswer.model_validate(data)

    monkeypatch.setattr(pa_module, "ANSWER_SCOPE", "Plant this rotation")
    accepted = PlantAnswer.model_validate(data)
    assert accepted.scope == "Plant this rotation"


def test_mutant_weakened_phase_one_only_allows_missing_release_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_answer()
    data["declared_limits"] = ["PLACEHOLDER_other_limit"]
    assert PHASE_ONE_ONLY not in data["declared_limits"]
    with pytest.raises(ValidationError, match="declared limits include"):
        PlantAnswer.model_validate(data)

    monkeypatch.setattr(pa_module, "PHASE_ONE_ONLY", "PLACEHOLDER_other_limit")
    accepted = PlantAnswer.model_validate(data)
    assert "PLACEHOLDER_other_limit" in accepted.declared_limits


def test_mutant_weakened_d148_label_allows_unlabeled_real_soil_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_answer()
    data["example_data"] = False
    for option in data["options"]:
        for item in option["soil_loss"].values():
            if item["value"] is not None:
                item["label"] = "PLACEHOLDER_weakened_label"
    with pytest.raises(ValidationError, match="D148"):
        PlantAnswer.model_validate(data)

    monkeypatch.setattr(pa_module, "D148_SOIL_LOSS_LABEL", "PLACEHOLDER_weakened_label")
    accepted = PlantAnswer.model_validate(data)
    assert accepted.example_data is False


def test_mutant_weakened_d249_labels_helper_allows_unprovenanced_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_answer()
    margin = data["options"][1]["margin"]["average"]
    margin.pop("provenance")
    margin.pop("range_missing")

    with pytest.raises(ValidationError, match="D249"):
        PlantAnswer.model_validate(data)

    monkeypatch.setattr(pa_module, "_labels", lambda *a, **kw: None)
    accepted = PlantAnswer.model_validate(data)
    assert accepted.options[1].margin.average.provenance is None


def test_mutant_weakened_one_of_allows_zero_with_missing_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load_answer()
    margin = data["options"][2]["margin"]["la_nina"]
    margin["value"] = 0.0
    margin["reason"] = "MISSING_INPUT"
    margin["detail"] = "PLACEHOLDER"
    margin["provenance"] = "DERIVED"
    margin["source"] = pa_module.MARGIN_SOURCE
    margin["range_missing"] = {"reason": "NOT_AVAILABLE"}

    with pytest.raises(ValidationError, match="never both"):
        PlantAnswer.model_validate(data)

    monkeypatch.setattr(pa_module, "_one_of", lambda *a, **kw: None)
    accepted = PlantAnswer.model_validate(data)
    assert accepted.options[2].margin.la_nina.value == 0.0
    assert accepted.options[2].margin.la_nina.reason == "MISSING_INPUT"
