"""Targeted validator-boundary and mutant-killing tests for ``contracts/decision_output/models.py``.

Covers D60, D85-D88, D91, D94-D99, D169 boundaries (PairState reasons and
preferred_rotation_id, Coverage k-of-N, PairCellCount range vs point-sign
invariants, RangeAcrossScenarios, CountByYear, EqualToleranceItem) plus injected
validator mutants. Every identifier and number here is PLACEHOLDER data only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.decision_output import models as do_models
from contracts.decision_output.models import (
    Coverage,
    DecisionOutput,
    EqualToleranceItem,
    PairCellCount,
    PairState,
    RangeAcrossScenarios,
)
from contracts.inputs.common import Missing, Value

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_decision_output.json"


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


# --- 1. D85 / D86 / D88 / D91 / D97 PairState & Coverage boundaries -----------


def test_coverage_inclusive_boundaries_and_exceeding_rejection() -> None:
    zero = Coverage(cells_compared=0, cells_of_the_pair=0)
    full = Coverage(cells_compared=3, cells_of_the_pair=3)
    assert zero.cells_compared == 0 and full.cells_compared == 3

    with pytest.raises(ValidationError, match="D91"):
        Coverage(cells_compared=4, cells_of_the_pair=3)


def test_pair_state_d85_d86_d97_rules_and_preferred_rotation_in_pair() -> None:
    pair = ["PLACEHOLDER_rot_1", "PLACEHOLDER_rot_2"]
    cov_ok = Coverage(cells_compared=1, cells_of_the_pair=2)
    cov_zero = Coverage(cells_compared=0, cells_of_the_pair=2)

    # D85: non-null state with cells_compared == 0 is rejected.
    with pytest.raises(ValidationError, match="D85"):
        PairState(
            pair=pair,
            value="Identical",
            reason="identical rows",
            coverage=cov_zero,
        )

    # D85: null state carries missing and no reason or preferred_rotation_id.
    uneval = PairState(
        pair=pair,
        value=None,
        missing=Missing(reason="MISSING_INPUT", detail="PLACEHOLDER"),
        coverage=cov_zero,
    )
    assert uneval.value is None

    # D97 / K3: "Not separated: within uncertainty" rejects any concrete reason and
    # requires reason_missing.
    within = PairState(
        pair=pair,
        value="Not separated: within uncertainty",
        reason_missing=Missing(reason="NOT_AVAILABLE", detail="PLACEHOLDER K3"),
        coverage=cov_ok,
    )
    assert within.reason is None

    with pytest.raises(ValidationError, match="does not carry the reason"):
        PairState(
            pair=pair,
            value="Not separated: within uncertainty",
            reason="identical rows",
            coverage=cov_ok,
        )

    # D86: mismatched reason for "Identical" is rejected.
    with pytest.raises(ValidationError, match="does not carry the reason"):
        PairState(
            pair=pair,
            value="Identical",
            reason="a difference without its range",
            coverage=cov_ok,
        )

    # Robust preference must name one of the two rotations in the pair.
    with pytest.raises(ValidationError, match="D74"):
        PairState(
            pair=pair,
            value="Robust preference",
            preferred_rotation_id="PLACEHOLDER_rot_3",
            coverage=cov_ok,
        )


def test_duplicate_pair_states_in_reverse_order_rejected() -> None:
    data = _load()
    rev = copy.deepcopy(data["pair_states"][0])
    rev["pair"].reverse()
    data["pair_states"].append(rev)
    with pytest.raises(ValidationError, match="more than one state of the pair"):
        DecisionOutput.model_validate(data)


# --- 2. D87 / D99 / D169 PairCellCount & EqualToleranceItem boundaries --------


def test_d99_by_difference_range_equal_to_cells_with_a_value_accepted_and_over_rejected() -> (
    None
):
    # cells_with_a_value = 2 (better=1, worse=1, equal=0); missing_side = 5 does NOT count.
    exact = PairCellCount(
        pair=["PLACEHOLDER_rot_1", "PLACEHOLDER_rot_2"],
        scenario_id="PLACEHOLDER_scen",
        indicator="soil_loss",
        by_difference_range={
            "strict_improvement": 1,
            "deterioration": 1,
            "not_separated": 0,
        },
        by_sign_of_point_value={
            "better": 1,
            "worse": 1,
            "equal": 0,
            "missing_side": 5,
        },
    )
    assert exact.by_difference_range.cells() == 2

    with pytest.raises(ValidationError, match="D99"):
        PairCellCount(
            pair=["PLACEHOLDER_rot_1", "PLACEHOLDER_rot_2"],
            scenario_id="PLACEHOLDER_scen",
            indicator="soil_loss",
            by_difference_range={
                "strict_improvement": 1,
                "deterioration": 1,
                "not_separated": 1,
            },
            by_sign_of_point_value={
                "better": 1,
                "worse": 1,
                "equal": 0,
                "missing_side": 5,
            },
        )


def test_d169_partial_carbon_model_and_computation_rejected() -> None:
    with pytest.raises(ValidationError, match="D169"):
        PairCellCount(
            pair=["PLACEHOLDER_rot_1", "PLACEHOLDER_rot_2"],
            scenario_id="PLACEHOLDER_scen",
            indicator="soil_carbon_trend",
            carbon_model="amg",
            computation=None,
            by_difference_range={
                "strict_improvement": 0,
                "deterioration": 0,
                "not_separated": 0,
            },
            by_sign_of_point_value=None,
            by_sign_of_point_value_missing={"reason": "NOT_DECLARED"},
        )


def test_equal_tolerance_requires_declared_provenance() -> None:
    with pytest.raises(ValidationError, match="DECLARED"):
        EqualToleranceItem(
            indicator="soil_loss",
            tolerance=Value(
                value=0.1,
                unit="t ha-1 yr-1",
                provenance="DERIVED",
                source="PLACEHOLDER",
                range_missing=Missing(reason="NOT_DECLARED"),
            ),
        )


# --- 3. D96 RangeAcrossScenarios & D60 CountByYear boundaries -----------------


def test_d96_equal_min_max_accepted_and_count_equality_boundary() -> None:
    r = RangeAcrossScenarios(
        rotation_id="PLACEHOLDER_rot_1",
        indicator="soil_loss",
        minimum=3,
        maximum=3,
        scenario_of_the_minimum="PLACEHOLDER_scen",
    )
    assert r.minimum == r.maximum

    data = _load()
    c0 = data["counts_by_year"][0]
    c0["years_within_limits"] = c0["years_evaluated"]
    for item in data["range_across_scenarios"]:
        if (
            item["rotation_id"] == c0["rotation_id"]
            and item["indicator"] == c0["indicator"]
        ):
            item["minimum"] = c0["years_within_limits"]
            item["maximum"] = c0["years_within_limits"]
    loaded = DecisionOutput.model_validate(data)
    assert (
        loaded.counts_by_year[0].years_within_limits
        == loaded.counts_by_year[0].years_evaluated
    )


# --- 4. Injected validator mutants --------------------------------------------


def test_mutant_weakened_check_pair_allows_identical_pair_rotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    r0 = data["rotations"][0]
    data["pair_states"][0]["pair"] = [r0, r0]

    with pytest.raises(ValidationError, match="two different rotations"):
        DecisionOutput.model_validate(data)

    monkeypatch.setattr(do_models, "_check_pair", lambda pair, what: None)
    accepted = DecisionOutput.model_validate(data)
    assert accepted.pair_states[0].pair == [r0, r0]


def test_mutant_weakened_check_cell_allows_soil_loss_per_rotation_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    diff = data["paired_differences"][0]
    assert diff["indicator"] == "soil_loss"
    diff["time_basis"] = "rotation"
    diff["ag_year"] = None

    with pytest.raises(ValidationError, match="one value per agricultural year"):
        DecisionOutput.model_validate(data)

    monkeypatch.setattr(do_models, "_check_cell", lambda *a, **kw: None)
    accepted = DecisionOutput.model_validate(data)
    assert accepted.paired_differences[0].time_basis == "rotation"


def test_mutant_weakened_check_declared_allows_simulated_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _load()
    data["limits"][0]["limit"]["provenance"] = "SIMULATED"

    with pytest.raises(ValidationError, match="DECLARED"):
        DecisionOutput.model_validate(data)

    monkeypatch.setattr(do_models, "_check_declared", lambda v, i, w: None)
    accepted = DecisionOutput.model_validate(data)
    assert accepted.limits[0].limit.provenance == "SIMULATED"


def test_mutant_weakened_reason_map_allows_invented_k3_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_state = {
        "pair": ["PLACEHOLDER_rot_1", "PLACEHOLDER_rot_2"],
        "value": "Not separated: within uncertainty",
        "reason": "identical rows",
        "coverage": {"cells_compared": 1, "cells_of_the_pair": 1},
    }
    with pytest.raises(ValidationError, match="does not carry the reason"):
        PairState.model_validate(bad_state)

    monkeypatch.setattr(
        do_models,
        "REASON_OF_A_STATE",
        {
            **do_models.REASON_OF_A_STATE,
            "Not separated: within uncertainty": "identical rows",
        },
    )
    accepted = PairState.model_validate(bad_state)
    assert accepted.reason == "identical rows"
