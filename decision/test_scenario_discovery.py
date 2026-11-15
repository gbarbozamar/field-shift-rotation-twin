"""Tests for Frontier Unit F-21: Scenario Discovery (PRIM) and DAPP.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
All scenario inputs, thresholds, and signpost series below are plainly
synthetic placeholder data designed solely to verify algorithm invariants
and contract compliance (Blueprint §3.5).

Run from the repository root:
``python -m pytest decision/test_scenario_discovery.py -q``.
"""

from __future__ import annotations

import math

import pytest

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing
from decision.scenario_discovery import (
    AdaptivePathway,
    PathwayStep,
    SignpostTrigger,
    VulnerableBoxRule,
    discover_vulnerability_boxes,
    evaluate_adaptive_pathway,
)

# ---------------------------------------------------------------------------
# 1. Scenario Discovery (PRIM-style axis-aligned peeling)
# ---------------------------------------------------------------------------


def test_prim_discovers_single_1d_vulnerability_box_and_tracks_trajectory():
    scenarios = {
        f"s{i:02d}": {"rain": float(100 + i * 50), "temp": float(20 + i)}
        for i in range(20)
    }
    # Option fails iff rain <= 350.0 (s00..s05 -> 6 scenarios).
    outcomes = {sid: vals["rain"] <= 350.0 for sid, vals in scenarios.items()}

    result = discover_vulnerability_boxes(
        scenarios, outcomes, alpha=0.1, min_support_fraction=0.1
    )

    assert result.total_scenarios == 20
    assert result.modeled_scenarios == 20
    assert result.vulnerable_scenarios == 6
    assert result.unmodeled_scenarios == ()
    assert len(result.boxes) == 1

    box = result.boxes[0]
    assert box.density == pytest.approx(1.0)
    assert box.coverage == pytest.approx(1.0)
    assert result.total_coverage == pytest.approx(1.0)
    assert set(box.matched_ids) == {f"s{i:02d}" for i in range(6)}
    assert set(box.bounds.keys()) == {"rain"}
    assert box.bounds["rain"] == (100.0, 350.0)
    assert "rain <= 350" in box.description

    # Trajectory starts at baseline density 6/20 and climbs monotonically to 1.0.
    assert len(result.trajectory) >= 2
    assert result.trajectory[0].step == 0
    assert result.trajectory[0].density == pytest.approx(0.3)
    assert result.trajectory[-1].density == pytest.approx(1.0)
    densities = [step.density for step in result.trajectory]
    assert densities == sorted(densities)


def test_prim_discovers_2d_box_on_factorial_grid_without_splitting_ties():
    scenarios: dict[str, dict[str, float]] = {}
    outcomes: dict[str, bool] = {}
    for ix in range(1, 11):
        for iy in range(1, 11):
            sid = f"g_{ix}_{iy}"
            scenarios[sid] = {"x": float(ix), "y": float(iy)}
            outcomes[sid] = ix <= 4 and iy >= 7

    result = discover_vulnerability_boxes(
        scenarios, outcomes, alpha=0.05, min_support_fraction=0.1
    )

    assert len(result.boxes) == 1
    box = result.boxes[0]
    assert box.density == pytest.approx(1.0)
    assert box.coverage == pytest.approx(1.0)
    assert len(box.matched_ids) == 16
    assert box.bounds == {"x": (1.0, 4.0), "y": (7.0, 10.0)}


def test_prim_covering_discovers_multiple_disjoint_vulnerability_boxes():
    scenarios: dict[str, dict[str, float]] = {}
    outcomes: dict[str, bool] = {}
    for idx in range(40):
        if idx < 10:
            # Region 1: very low rainfall.
            rain = 100.0 + idx * 12.0
            temp = 20.0 + (idx % 5) * 1.5
            fail = True
        elif idx < 20:
            # Region 2: extreme heat at moderate rainfall.
            rain = 300.0 + (idx - 10) * 15.0
            temp = 36.0 + (idx - 10) * 0.6
            fail = True
        else:
            # Safe baseline region extending past Region 2 in rainfall.
            rain = 300.0 + (idx - 20) * 30.0
            temp = 20.0 + (idx - 20) * 0.4
            fail = False
        sid = f"sc_{idx:02d}"
        scenarios[sid] = {"rain": rain, "temp": temp}
        outcomes[sid] = fail

    result = discover_vulnerability_boxes(
        scenarios, outcomes, alpha=0.1, min_support_fraction=0.15
    )

    assert len(result.boxes) == 2
    assert result.total_coverage == pytest.approx(1.0)
    covered_union = {sid for box in result.boxes for sid in box.matched_ids}
    assert covered_union == {f"sc_{i:02d}" for i in range(20)}
    assert all(box.density == pytest.approx(1.0) for box in result.boxes)
    assert sum(box.coverage for box in result.boxes) == pytest.approx(1.0)


def test_prim_quarantines_missing_factors_and_never_fills_with_zero():
    scenarios: dict[str, dict[str, float | Missing | InputsMissing]] = {
        f"m{i:02d}": {"rain": float(100 + i * 50), "temp": float(20 + i)}
        for i in range(10)
    }
    outcomes: dict[str, bool | Missing] = {
        sid: vals["rain"] <= 200.0
        for sid, vals in scenarios.items()  # type: ignore[operator]
    }
    # Quarantined scenarios: one Missing factor (would fall in rain<=200 if filled with 0!),
    # one InputsMissing factor, one absent key, and one Missing outcome.
    scenarios["q_results_missing"] = {
        "rain": Missing(reason="NO_COVERAGE", detail="station gap"),
        "temp": 25.0,
    }
    outcomes["q_results_missing"] = False

    scenarios["q_inputs_missing"] = {
        "rain": 500.0,
        "temp": InputsMissing(
            reason="MISSING_INPUT", detail="temperature sensor offline"
        ),
    }
    outcomes["q_inputs_missing"] = True

    scenarios["q_absent_key"] = {"rain": 150.0}
    outcomes["q_absent_key"] = True

    scenarios["q_missing_outcome"] = {"rain": 120.0, "temp": 21.0}
    outcomes["q_missing_outcome"] = Missing(
        reason="NOT_COMPUTABLE", detail="engine diverged"
    )

    snapshot = {k: dict(v) for k, v in scenarios.items()}

    result = discover_vulnerability_boxes(
        scenarios, outcomes, alpha=0.1, min_support_fraction=0.2
    )

    # Original input mappings were not mutated (G1).
    assert scenarios == snapshot

    assert result.total_scenarios == 14
    assert result.modeled_scenarios == 10
    assert result.vulnerable_scenarios == 3
    assert result.unmodeled_ids == (
        "q_results_missing",
        "q_inputs_missing",
        "q_absent_key",
        "q_missing_outcome",
    )
    by_id = {u.scenario_id: u for u in result.unmodeled_scenarios}
    assert by_id["q_results_missing"].missing_factors == ("rain",)
    assert by_id["q_results_missing"].reasons["rain"].reason == "NO_COVERAGE"
    assert by_id["q_inputs_missing"].reasons["temp"].reason == "MISSING_INPUT"
    assert by_id["q_absent_key"].reasons["temp"].reason == "MISSING_INPUT"
    assert by_id["q_missing_outcome"].missing_factors == ("outcome",)
    assert by_id["q_missing_outcome"].reasons["outcome"].reason == "NOT_COMPUTABLE"

    assert len(result.boxes) == 1
    assert set(result.boxes[0].matched_ids) == {"m00", "m01", "m02"}
    assert result.boxes[0].density == pytest.approx(1.0)


def test_prim_respects_min_support_fraction_floor():
    scenarios = {f"s{i:02d}": {"rain": float(100 + i * 20)} for i in range(10)}
    # Only 1 vulnerable scenario (support 0.1), while min_support_fraction=0.3 (3 scenarios).
    outcomes = {f"s{i:02d}": (i == 0) for i in range(10)}

    result = discover_vulnerability_boxes(
        scenarios, outcomes, alpha=0.2, min_support_fraction=0.3
    )

    assert len(result.boxes) == 1
    box = result.boxes[0]
    assert len(box.matched_ids) >= 3
    assert box.support >= 0.3
    assert box.density == pytest.approx(1.0 / len(box.matched_ids))


def test_prim_edge_cases_empty_no_vulnerable_and_all_vulnerable():
    empty = discover_vulnerability_boxes({}, {}, alpha=0.1, min_support_fraction=0.2)
    assert empty.boxes == ()
    assert empty.total_scenarios == 0
    assert empty.total_coverage == 0.0

    safe_scenarios = {f"s{i}": {"x": float(i)} for i in range(5)}
    safe_outcomes = {f"s{i}": False for i in range(5)}
    no_vuln = discover_vulnerability_boxes(
        safe_scenarios, safe_outcomes, alpha=0.2, min_support_fraction=0.2
    )
    assert no_vuln.boxes == ()
    assert no_vuln.vulnerable_scenarios == 0
    assert no_vuln.total_coverage == 0.0

    all_vuln = discover_vulnerability_boxes(
        safe_scenarios,
        {f"s{i}": True for i in range(5)},
        alpha=0.2,
        min_support_fraction=0.2,
    )
    assert len(all_vuln.boxes) == 1
    assert all_vuln.boxes[0].bounds == {}
    assert all_vuln.boxes[0].coverage == pytest.approx(1.0)
    assert all_vuln.boxes[0].density == pytest.approx(1.0)


def test_prim_validation_rejects_invalid_inputs_and_positional_rule():
    rule = VulnerableBoxRule({"x": (0.0, 1.0)}, 0.5, 0.8, ("s1",))
    assert rule.bounds["x"] == (0.0, 1.0)
    with pytest.raises(TypeError):
        rule.bounds["x"] = (0.0, 2.0)  # type: ignore[index]

    with pytest.raises(ValueError, match="alpha"):
        discover_vulnerability_boxes({}, {}, alpha=0.0, min_support_fraction=0.2)
    with pytest.raises(ValueError, match="alpha"):
        discover_vulnerability_boxes({}, {}, alpha=1.0, min_support_fraction=0.2)
    with pytest.raises(ValueError, match="min_support_fraction"):
        discover_vulnerability_boxes({}, {}, alpha=0.1, min_support_fraction=0.0)
    with pytest.raises(ValueError, match="keys"):
        discover_vulnerability_boxes(
            {"s1": {"x": 1.0}}, {}, alpha=0.1, min_support_fraction=0.5
        )
    with pytest.raises(ValueError, match="finite"):
        discover_vulnerability_boxes(
            {"s1": {"x": math.nan}},
            {"s1": True},
            alpha=0.1,
            min_support_fraction=0.5,
        )
    with pytest.raises(TypeError, match="finite real number"):
        discover_vulnerability_boxes(
            {"s1": {"x": True}},  # type: ignore[dict-item]
            {"s1": True},
            alpha=0.1,
            min_support_fraction=0.5,
        )


# ---------------------------------------------------------------------------
# 2. Dynamic Adaptive Policy Pathways (DAPP)
# ---------------------------------------------------------------------------


def _sample_pathway(*, horizon_end: int | None = None) -> AdaptivePathway:
    return AdaptivePathway(
        pathway_id="rotation-adaptation",
        initial_step_id="current_rotation",
        horizon_end=horizon_end,
        steps=(
            PathwayStep(
                step_id="current_rotation",
                action="Continue baseline rotation",
                trigger=SignpostTrigger(
                    signpost_id="water_deficit",
                    threshold=0.30,
                    direction="below",
                    unit="dimensionless",
                ),
                lead_time=0,
                transfer_to=("slow_transition", "fast_transition"),
            ),
            PathwayStep(
                step_id="slow_transition",
                action="Establish deep-rooted perennial buffer",
                trigger=None,
                lead_time=3,
            ),
            PathwayStep(
                step_id="fast_transition",
                action="Shift to drought-tolerant cover crop",
                trigger=SignpostTrigger(
                    signpost_id="water_deficit",
                    threshold=0.15,
                    direction="below",
                    unit="dimensionless",
                ),
                lead_time=1,
                transfer_to=("terminal_fallow",),
            ),
            PathwayStep(
                step_id="terminal_fallow",
                action="Convert to permanent pasture",
                trigger=None,
                lead_time=1,
            ),
        ),
    )


def test_dapp_no_trigger_stays_on_initial_step():
    plan = _sample_pathway()
    series = {
        2020: {"water_deficit": 0.45},
        2021: {"water_deficit": 0.35},
        2022: {"water_deficit": 0.30},  # 'below' 0.30 is strict <, so no trigger.
    }
    res = evaluate_adaptive_pathway(plan, series)

    assert res.status == "NO_TRIGGER"
    assert res.active_step_id == "current_rotation"
    assert res.transitions == ()
    assert res.tipping_events == ()
    assert res.rejected_transfers == ()
    assert res.missing is None
    assert res.evaluated_times == (2020, 2021, 2022)


def test_dapp_selects_shortest_valid_transfer_and_checks_lead_time():
    plan = _sample_pathway(horizon_end=2025)
    # Tipping point crossed at 2021 (0.25 < 0.30): both slow (lead=3) and fast (lead=1)
    # fit within 2025-2021=4, so shortest valid transfer ('fast_transition', lead=1) wins.
    series = {
        2020: {"water_deficit": 0.40},
        2021: {"water_deficit": 0.25},
        2022: {"water_deficit": 0.22},
        2023: {"water_deficit": 0.20},
    }
    res = evaluate_adaptive_pathway(plan, series)

    assert res.status == "TRANSFERRED"
    assert res.active_step_id == "fast_transition"
    assert res.missing is None
    assert len(res.transitions) == 1
    tr = res.transitions[0]
    assert tr.time == 2021
    assert tr.from_step_id == "current_rotation"
    assert tr.to_step_id == "fast_transition"
    assert tr.lead_time == 1
    assert tr.effective_time == 2022
    assert res.rejected_transfers == ()


def test_dapp_rejects_transfer_exceeding_remaining_lead_time():
    # Without explicit horizon_end, last_observed_time is 2023 -> remaining at 2021 is 2.
    # slow_transition (lead=3) exceeds remaining=2 and must be rejected; fast_transition (lead=1) succeeds.
    plan = AdaptivePathway(
        pathway_id="lead-check",
        initial_step_id="base",
        steps=(
            PathwayStep(
                step_id="base",
                action="Baseline",
                trigger=SignpostTrigger("soil_loss", 10.0, direction="at_or_above"),
                transfer_to=("long_fix", "short_fix"),
            ),
            PathwayStep(step_id="long_fix", action="Terracing", lead_time=3),
            PathwayStep(step_id="short_fix", action="Contour strip", lead_time=1),
        ),
    )
    series = {
        2020: {"soil_loss": 8.0},
        2021: {"soil_loss": 10.0},  # at_or_above triggers on exact equality
        2022: {"soil_loss": 11.0},
        2023: {"soil_loss": 11.5},
    }
    res = evaluate_adaptive_pathway(plan, series)

    assert res.status == "TRANSFERRED"
    assert res.active_step_id == "short_fix"
    assert len(res.rejected_transfers) == 1
    rej = res.rejected_transfers[0]
    assert rej.to_step_id == "long_fix"
    assert rej.reason == "lead_time_exceeded"

    # When tipping occurs at the final observed year (remaining=0), lead_time=1 also fails.
    late_res = evaluate_adaptive_pathway(
        plan, {2020: {"soil_loss": 8.0}, 2021: {"soil_loss": 10.5}}
    )
    assert late_res.status == "NO_VALID_TRANSFER"
    assert late_res.active_step_id is None
    assert {r.to_step_id for r in late_res.rejected_transfers} == {
        "long_fix",
        "short_fix",
    }


def test_dapp_rejects_already_exceeded_target_and_chains_multistep_transfers():
    plan = AdaptivePathway(
        pathway_id="multistep",
        initial_step_id="s0",
        horizon_end=2030,
        steps=(
            PathwayStep(
                step_id="s0",
                action="Initial",
                trigger=SignpostTrigger("heat_days", 10.0, direction="above"),
                transfer_to=("s1_already_bad", "s1_valid"),
            ),
            PathwayStep(
                step_id="s1_already_bad",
                action="Mild adjustment",
                trigger=SignpostTrigger("heat_days", 15.0, direction="above"),
                lead_time=1,
            ),
            PathwayStep(
                step_id="s1_valid",
                action="Moderate adjustment",
                trigger=SignpostTrigger("heat_days", 20.0, direction="above"),
                lead_time=2,
                transfer_to=("s2_final",),
            ),
            PathwayStep(
                step_id="s2_final",
                action="Full shift",
                trigger=None,
                lead_time=1,
            ),
        ),
    )
    series = {
        2020: {"heat_days": 8.0},
        2021: {"heat_days": 12.0},  # s0 triggers; s1_already_bad effective at 2022
        2022: {"heat_days": 16.0},  # > 15.0, so s1_already_bad is already exceeded!
        2023: {"heat_days": 18.0},  # s1_valid becomes effective at 2023 (<= 20.0)
        2024: {"heat_days": 22.0},  # s1_valid triggers -> s2_final (effective 2025)
    }

    res = evaluate_adaptive_pathway(plan, series)

    assert res.status == "TRANSFERRED"
    assert res.active_step_id == "s2_final"
    assert [(t.from_step_id, t.to_step_id, t.time) for t in res.transitions] == [
        ("s0", "s1_valid", 2021),
        ("s1_valid", "s2_final", 2024),
    ]
    assert len(res.rejected_transfers) == 1
    assert res.rejected_transfers[0].to_step_id == "s1_already_bad"
    assert res.rejected_transfers[0].reason == "target_already_exceeded"


def test_dapp_emits_typed_missing_input_when_required_signpost_missing():
    plan = _sample_pathway(horizon_end=2025)

    # Case A: required signpost absent from observation at a step.
    res_absent = evaluate_adaptive_pathway(
        plan, {2020: {"water_deficit": 0.45}, 2021: {"other_metric": 1.0}}
    )
    assert res_absent.status == "MISSING_INPUT"
    assert res_absent.active_step_id is None
    assert isinstance(res_absent.missing, Missing)
    assert res_absent.missing.reason == "MISSING_INPUT"
    assert "water_deficit" in (res_absent.missing.detail or "")

    # Case B: required signpost explicitly carries a Missing object.
    res_typed = evaluate_adaptive_pathway(
        plan,
        {
            2020: {"water_deficit": 0.45},
            2021: {
                "water_deficit": InputsMissing(
                    reason="SOURCE_UNAVAILABLE", detail="NASA POWER timeout"
                )
            },
        },
    )
    assert res_typed.status == "MISSING_INPUT"
    assert res_typed.missing is not None
    assert res_typed.missing.reason == "MISSING_INPUT"
    assert "SOURCE_UNAVAILABLE" in (res_typed.missing.detail or "")

    # Case C: empty signpost series when active step requires a signpost.
    res_empty = evaluate_adaptive_pathway(plan, {})
    assert res_empty.status == "MISSING_INPUT"
    assert res_empty.missing is not None
    assert res_empty.missing.reason == "MISSING_INPUT"


def test_dapp_supports_signpost_keyed_series_and_consecutive_periods():
    plan = AdaptivePathway(
        pathway_id="persistent-trigger",
        initial_step_id="base",
        horizon_end=2026,
        steps=(
            PathwayStep(
                step_id="base",
                action="Baseline",
                trigger=SignpostTrigger(
                    signpost_id="frost_days",
                    threshold=5.0,
                    direction="at_or_below",
                    consecutive_periods=2,
                ),
                transfer_to=("protected",),
            ),
            PathwayStep(step_id="protected", action="Frost cover", lead_time=1),
        ),
    )
    # Signpost-keyed mapping; single low year in 2020 does not trigger, 2022+2023 triggers at 2023.
    series = {
        "frost_days": {2020: 4.0, 2021: 8.0, 2022: 5.0, 2023: 3.0},
    }
    res = evaluate_adaptive_pathway(plan, series)

    assert res.status == "TRANSFERRED"
    assert res.active_step_id == "protected"
    assert len(res.transitions) == 1
    assert res.transitions[0].time == 2023


def test_dapp_validation_errors():
    with pytest.raises(ValueError, match="direction"):
        SignpostTrigger("s", 1.0, direction="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="consecutive_periods"):
        SignpostTrigger("s", 1.0, consecutive_periods=0)
    with pytest.raises(ValueError, match="lead_time"):
        PathwayStep("a", "Act", lead_time=-1)
    with pytest.raises(ValueError, match="unknown transfer target"):
        AdaptivePathway(
            "p",
            "a",
            (PathwayStep("a", "Act", transfer_to=("missing_step",)),),
        )
    with pytest.raises(ValueError, match="itself"):
        AdaptivePathway(
            "p",
            "a",
            (PathwayStep("a", "Act", transfer_to=("a",)),),
        )
    plan = _sample_pathway()
    with pytest.raises(ValueError, match="finite"):
        evaluate_adaptive_pathway(plan, {2020: {"water_deficit": math.inf}})
