"""Tests for Frontier research inventory, ablation gate, and national grid governance."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from contracts.results.models import Missing
from validation.frontier_governance import (
    EXPECTED_INVENTORY_SIZE,
    FRONTIER_DOMAINS,
    FRONTIER_INVENTORY,
    STATUS_PROPOSED,
    AblationTestCase,
    ControlFailedError,
    FrontierLineEntry,
    NationalGridCellInput,
    assert_maturity_validation_independence,
    evaluate_layer_ablation,
    get_inventory_by_unit,
    report_uniform_robust_if_all_robust,
    run_national_grid_cells,
    summarize_inventory_by_domain,
    validate_frontier_inventory,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. 46-line Frontier Research Inventory Registry
# ---------------------------------------------------------------------------


def test_frontier_inventory_has_46_entries_and_all_10_domains() -> None:
    assert len(FRONTIER_INVENTORY) == EXPECTED_INVENTORY_SIZE == 46
    validate_frontier_inventory(FRONTIER_INVENTORY)
    counts = summarize_inventory_by_domain(FRONTIER_INVENTORY)
    assert tuple(counts.keys()) == FRONTIER_DOMAINS
    assert sum(counts.values()) == 46
    assert all(count > 0 for count in counts.values())


def test_frontier_inventory_covers_all_units_f01_through_f25() -> None:
    for index in range(1, 26):
        unit_id = f"F-{index:02d}"
        entries = get_inventory_by_unit(unit_id)
        assert entries, f"{unit_id} must be mapped in FRONTIER_INVENTORY"


def test_all_46_inventory_lines_are_implemented_without_auto_validation() -> None:
    impl_counts = Counter(entry.implementation_status for entry in FRONTIER_INVENTORY)
    assert impl_counts == {
        "FRONTIER_IMPLEMENTED": 40,
        "CORE_IMPLEMENTED": 6,
    }
    assert impl_counts.get("NOT_IMPLEMENTED", 0) == 0

    by_id = {entry.line_id: entry for entry in FRONTIER_INVENTORY}
    for line_id in ("L06", "L16"):
        assert by_id[line_id].implementation_status == "FRONTIER_IMPLEMENTED"
        assert by_id[line_id].data_availability == "LOCAL_MEASUREMENT_REQUIRED"
        assert by_id[line_id].local_validation_status == "UNVALIDATED"

    assert all(
        entry.local_validation_status != "VALIDATED" for entry in FRONTIER_INVENTORY
    )


def test_established_maturity_never_auto_grants_local_validation() -> None:
    established = [
        entry for entry in FRONTIER_INVENTORY if entry.method_maturity == "ESTABLISHED"
    ]
    assert len(established) >= 10
    for entry in established:
        assert entry.local_validation_status != "VALIDATED"
        assert entry.auto_validated_by_maturity is False

    with pytest.raises(ValueError, match="local_evidence_verified=True"):
        FrontierLineEntry(
            line_id="L99",
            domain="Erosion",
            title="Unverified established entry",
            unit_ids=("F-01",),
            method_maturity="ESTABLISHED",
            implementation_status="FRONTIER_IMPLEMENTED",
            data_availability="AVAILABLE_PUBLIC",
            local_validation_status="VALIDATED",
        )

    with pytest.raises(ValueError, match="auto-grant"):
        FrontierLineEntry(
            line_id="L99",
            domain="Erosion",
            title="Auto validated claim",
            unit_ids=("F-01",),
            method_maturity="ESTABLISHED",
            implementation_status="FRONTIER_IMPLEMENTED",
            data_availability="AVAILABLE_PUBLIC",
            local_validation_status="UNVALIDATED",
            auto_validated_by_maturity=True,
        )

    verified = FrontierLineEntry(
        line_id="L99",
        domain="Erosion",
        title="Independently verified entry",
        unit_ids=("F-01",),
        method_maturity="ESTABLISHED",
        implementation_status="FRONTIER_IMPLEMENTED",
        data_availability="AVAILABLE_PUBLIC",
        local_validation_status="VALIDATED",
        local_evidence_verified=True,
        validation_evidence_ref="validation/fixtures/PLACEHOLDER_signed.json",
    )
    assert_maturity_validation_independence(verified)


def test_validate_frontier_inventory_rejects_broken_registries() -> None:
    with pytest.raises(ValueError, match="exactly 46"):
        validate_frontier_inventory(FRONTIER_INVENTORY[:45])

    duplicate_id_list = [*FRONTIER_INVENTORY[:-1], FRONTIER_INVENTORY[0]]
    with pytest.raises(ValueError, match="unique"):
        validate_frontier_inventory(duplicate_id_list)

    swapped = [FRONTIER_INVENTORY[1], FRONTIER_INVENTORY[0], *FRONTIER_INVENTORY[2:]]
    with pytest.raises(ValueError, match="sequential"):
        validate_frontier_inventory(swapped)

    missing_domain = [
        FrontierLineEntry(
            line_id=entry.line_id,
            domain="Erosion" if entry.domain == "Economics" else entry.domain,
            title=entry.title,
            unit_ids=entry.unit_ids,
            method_maturity=entry.method_maturity,
            implementation_status=entry.implementation_status,
            data_availability=entry.data_availability,
            local_validation_status=entry.local_validation_status,
            notes=entry.notes,
        )
        for entry in FRONTIER_INVENTORY
    ]
    with pytest.raises(ValueError, match="missing required domains"):
        validate_frontier_inventory(missing_domain)


# ---------------------------------------------------------------------------
# 2. Layer-Ablation Decision Gate (§7 rule)
# ---------------------------------------------------------------------------


def test_ablation_recommends_prune_when_state_and_uncertainty_do_not_improve() -> None:
    cases = (
        AblationTestCase(
            case_id="case-1",
            core_decision_state="Not separated: within uncertainty",
            frontier_decision_state="Not separated: within uncertainty",
            core_interval=(1.0, 3.0),  # width 2.0
            frontier_interval=(1.02, 2.98),  # width 1.96 -> reduction 0.04 <= 0.05
        ),
        AblationTestCase(
            case_id="case-2",
            core_decision_state="Robust preference",
            frontier_decision_state="Robust preference",
            core_interval=(0.5, 1.5),  # width 1.0
            frontier_interval=(0.5, 1.45),  # exact boundary 0.05 -> not beyond
        ),
        AblationTestCase(
            case_id="case-3-widened",
            core_decision_state="Identical",
            frontier_decision_state="Identical",
            core_interval=(2.0, 3.0),  # width 1.0
            frontier_interval=(1.8, 3.2),  # width 1.4 -> negative reduction
        ),
    )
    result = evaluate_layer_ablation("F-05-wcm", cases, min_delta=0.05)
    assert result.status == STATUS_PROPOSED
    assert result.prune_recommended is True
    assert result.any_state_changed is False
    assert result.any_uncertainty_narrowed is False
    assert result.state_changed_cases == ()
    assert result.narrowed_cases == ()
    assert result.max_uncertainty_reduction == pytest.approx(0.05)
    assert "PRUNE_RECOMMENDED" in result.decision_note


def test_ablation_keeps_layer_when_decision_state_changes() -> None:
    cases = (
        AblationTestCase(
            case_id="case-unchanged",
            core_decision_state="Not separated: within uncertainty",
            frontier_decision_state="Not separated: within uncertainty",
            core_interval=(1.0, 2.0),
            frontier_interval=(1.0, 2.0),
        ),
        AblationTestCase(
            case_id="case-flipped",
            core_decision_state="Not separated: within uncertainty",
            frontier_decision_state="Robust preference",
            core_interval=(1.0, 2.0),
            frontier_interval=(1.0, 2.0),
        ),
    )
    result = evaluate_layer_ablation("F-06-enkf", cases, min_delta=0.1)
    assert result.prune_recommended is False
    assert result.any_state_changed is True
    assert result.any_uncertainty_narrowed is False
    assert result.state_changed_cases == ("case-flipped",)
    assert "KEEP_LAYER" in result.decision_note


def test_ablation_keeps_layer_when_uncertainty_narrows_beyond_min_delta() -> None:
    cases = (
        AblationTestCase(
            case_id="case-narrowed",
            core_decision_state="Not separated: within uncertainty",
            frontier_decision_state="Not separated: within uncertainty",
            core_interval=(0.0, 2.0),  # width 2.0
            frontier_interval=(0.5, 1.9),  # width 1.4 -> reduction 0.6 > 0.25
        ),
    )
    result = evaluate_layer_ablation("F-14-conformal", cases, min_delta=0.25)
    assert result.prune_recommended is False
    assert result.any_state_changed is False
    assert result.any_uncertainty_narrowed is True
    assert result.narrowed_cases == ("case-narrowed",)
    assert result.max_uncertainty_reduction == pytest.approx(0.6)


def test_ablation_preserves_missing_intervals_without_zero_fill() -> None:
    cases = (
        AblationTestCase(
            case_id="case-missing",
            core_decision_state="Not separated: uncertainty missing",
            frontier_decision_state="Not separated: uncertainty missing",
            core_interval=Missing(reason="MISSING_INPUT", detail="soil depth missing"),
            frontier_interval=(1.0, 2.0),
        ),
    )
    result = evaluate_layer_ablation("F-07-ptf", cases, min_delta=0.05)
    assert result.prune_recommended is True
    assert result.missing_interval_cases == ("case-missing",)
    assert isinstance(result.case_evaluations[0].uncertainty_reduction, Missing)
    assert result.case_evaluations[0].uncertainty_reduction.reason == "MISSING_INPUT"
    assert isinstance(result.max_uncertainty_reduction, Missing)
    assert result.max_uncertainty_reduction.reason == "NOT_COMPUTABLE"


def test_ablation_input_guards() -> None:
    valid_case = AblationTestCase(
        case_id="c1",
        core_decision_state="Identical",
        frontier_decision_state="Identical",
        core_interval=(1.0, 2.0),
        frontier_interval=(1.0, 2.0),
    )
    with pytest.raises(ValueError, match="at least one"):
        evaluate_layer_ablation("F-01", [], min_delta=0.1)
    with pytest.raises(TypeError, match="min_delta"):
        evaluate_layer_ablation("F-01", [valid_case], min_delta=True)
    with pytest.raises(ValueError, match="min_delta"):
        evaluate_layer_ablation("F-01", [valid_case], min_delta=-0.01)
    with pytest.raises(ValueError, match="low <= high"):
        AblationTestCase(
            case_id="bad",
            core_decision_state="Identical",
            frontier_decision_state="Identical",
            core_interval=(3.0, 1.0),
            frontier_interval=(1.0, 2.0),
        )
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_layer_ablation("F-01", [valid_case, valid_case], min_delta=0.1)


# ---------------------------------------------------------------------------
# 3. National Cell-Grid Runner & Emulator Recalculation Gate (§§5.7, 6)
# ---------------------------------------------------------------------------


def test_national_grid_separates_horizons_and_normative_vs_exploratory() -> None:
    cells = (
        NationalGridCellInput(
            cell_id="cell-001",
            horizon="historical",
            evaluation_mode="FULL_PHYSICS",
            decision_state="Robust preference",
            normative_a_over_t=1.35,  # > 1.0, still pre_evaluation
            exploratory_exceedance_years=4,
            exploratory_total_years=20,
            is_finalist=True,
        ),
        NationalGridCellInput(
            cell_id="cell-001",
            horizon="2030-2060",
            evaluation_mode="EMULATOR",
            decision_state="Not robust across scenarios",
            normative_a_over_t=Missing(
                reason="NOT_APPLICABLE",
                detail="future climate is exploratory only",
            ),
            exploratory_exceedance_years=7,
            exploratory_total_years=31,
            recalculated_with_full_physics=False,
            is_finalist=False,
        ),
    )
    report = run_national_grid_cells(cells)
    assert report.gate_passed is True
    assert report.approved_finalists == ("cell-001",)
    assert report.emulator_approximation_cells == ("cell-001",)
    assert report.control_failed_cells == ()
    assert set(report.horizon_summaries.keys()) == {"historical", "2030-2060"}

    hist_out, fut_out = report.cells
    assert hist_out.evaluation_tag == "FULL_PHYSICS"
    assert hist_out.normative.a_over_t == pytest.approx(1.35)
    assert hist_out.normative.pre_evaluation is True
    assert hist_out.normative.counts_legal_noncompliance is False
    assert hist_out.exploratory.exceedance_years == 4
    assert hist_out.exploratory.total_years == 20
    assert hist_out.exploratory.counts_legal_noncompliance is False
    assert hist_out.exploratory.counts_voluntary_target is True

    assert fut_out.evaluation_tag == "EMULATOR_APPROXIMATION"
    assert fut_out.normative.valid_for_normative_erosion is False
    assert fut_out.normative.counts_legal_noncompliance is False
    assert isinstance(fut_out.normative.a_over_t, Missing)
    assert fut_out.exploratory.exceedance_years == 7


def test_emulator_finalist_without_full_physics_triggers_control_failed() -> None:
    unverified_finalist = NationalGridCellInput(
        cell_id="cell-approx",
        horizon="historical",
        evaluation_mode="EMULATOR",
        decision_state="Robust preference",
        normative_a_over_t=0.8,
        exploratory_exceedance_years=1,
        exploratory_total_years=20,
        recalculated_with_full_physics=False,
        is_finalist=True,
    )
    verified_finalist = NationalGridCellInput(
        cell_id="cell-recalc",
        horizon="historical",
        evaluation_mode="EMULATOR",
        decision_state="Robust preference",
        normative_a_over_t=0.7,
        exploratory_exceedance_years=0,
        exploratory_total_years=20,
        recalculated_with_full_physics=True,
        is_finalist=True,
    )

    report = run_national_grid_cells((unverified_finalist, verified_finalist))
    assert report.gate_passed is False
    assert report.control_failed_cells == ("cell-approx",)
    assert report.approved_finalists == ("cell-recalc",)
    assert report.emulator_approximation_cells == ("cell-approx",)

    approx_out, recalc_out = report.cells
    assert approx_out.evaluation_tag == "EMULATOR_APPROXIMATION"
    assert approx_out.control_status == "CONTROL_FAILED"
    assert approx_out.promoted_as_finalist is False
    assert isinstance(approx_out.control_missing, Missing)
    assert approx_out.control_missing.reason == "CONTROL_FAILED"

    assert recalc_out.evaluation_tag == "EMULATOR_RECALCULATED_FULL_PHYSICS"
    assert recalc_out.control_status == "PASSED"
    assert recalc_out.promoted_as_finalist is True
    assert recalc_out.control_missing is None

    with pytest.raises(ControlFailedError, match="CONTROL_FAILED"):
        run_national_grid_cells(
            (unverified_finalist,),
            raise_on_control_failed=True,
        )


def test_refuses_inventing_findings_when_all_cells_are_uniformly_robust() -> None:
    cells = tuple(
        NationalGridCellInput(
            cell_id=f"cell-{i:03d}",
            horizon="historical",
            evaluation_mode="FULL_PHYSICS",
            decision_state="Robust preference",
            normative_a_over_t=0.5,
            exploratory_exceedance_years=0,
            exploratory_total_years=20,
        )
        for i in range(5)
    )
    report = run_national_grid_cells(cells)
    assert report.finding_summary == "UNIFORM_ROBUST"
    assert report.uniform_robust_detected is True
    assert report.invented_findings_refused is True
    assert report.horizon_summaries["historical"].spatial_contrast_detected is False
    assert report.horizon_summaries["historical"].invented_findings_refused is True

    uniform_non_robust = report_uniform_robust_if_all_robust(
        ["Not separated: within uncertainty", "Not separated: within uncertainty"]
    )
    assert uniform_non_robust.finding_summary.startswith("UNIFORM_NON_ROBUST:")
    assert uniform_non_robust.uniform_robust_detected is False
    assert uniform_non_robust.spatial_contrast_detected is False

    mixed = report_uniform_robust_if_all_robust(
        ["Robust preference", "Not robust across scenarios"]
    )
    assert mixed.finding_summary == "HETEROGENEOUS_STATES"
    assert mixed.spatial_contrast_detected is True


def test_national_grid_input_guards() -> None:
    with pytest.raises(ValueError, match="exceed"):
        NationalGridCellInput(
            cell_id="bad-counts",
            horizon="historical",
            evaluation_mode="FULL_PHYSICS",
            decision_state="Robust preference",
            normative_a_over_t=0.5,
            exploratory_exceedance_years=21,
            exploratory_total_years=20,
        )
    with pytest.raises(ValueError, match="2030-2060"):
        NationalGridCellInput(
            cell_id="bad-future-norm",
            horizon="2030-2060",
            evaluation_mode="FULL_PHYSICS",
            decision_state="Robust preference",
            normative_a_over_t=0.5,
            exploratory_exceedance_years=1,
            exploratory_total_years=10,
            normative_pre_evaluation=False,
        )
    with pytest.raises(ValueError, match="at least one"):
        run_national_grid_cells([])


# ---------------------------------------------------------------------------
# 4. Documentation Consistency (docs/FRONTIER_VISION_REV13.md)
# ---------------------------------------------------------------------------


def test_frontier_vision_doc_matches_inventory_and_has_no_broken_links() -> None:
    doc_path = REPO_ROOT / "docs" / "FRONTIER_VISION_REV13.md"
    assert doc_path.is_file()
    text = doc_path.read_text(encoding="utf-8")

    assert STATUS_PROPOSED in text
    assert not re.search(r"[A-Za-z]:\\", text)
    for entry in FRONTIER_INVENTORY:
        assert entry.line_id in text
    for index in range(1, 26):
        assert f"F-{index:02d}" in text

    # Verify every relative markdown link points to an existing file in the repo.
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    assert links
    assert "../engine/erosion/dynamic_surface_routing.py" in links
    assert "../engine/water/soil_structure_feedback.py" in links
    for target in links:
        assert not target.startswith(("http://", "https://"))
        resolved = (doc_path.parent / target).resolve()
        assert resolved.is_file(), f"broken markdown link in doc: {target}"
