"""Tests for ``decision/grounded_explainer.py`` (Frontier Unit F-22).

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). Covers:
- ``GroundedFact`` and ``GroundedFactLedger`` contract validation (G5, C3.1,
  C3.2, C4.1, C4.2);
- ``render_deterministic_explanation`` deterministic formatting, provenance,
  source/assumption, example-data badges, and explicit ``Missing`` notices;
- ``verify_explanation_grounding`` strict hypothesis-mode rejection of
  hallucinated numbers, precision overflows, percentages, wrong units, wrong
  metric/rotation/provenance bindings, fabricated missing values, agronomic
  advice, prescriptive guarantees, false NASA/official endorsements, and
  leak-free withholding (``CONTROL_FAILED``, ``surfaced_text is None``);
- Round-trip integration with ``assemble_decision_output`` and ``demo.matrix``;
- Static AST check confirming zero LLM SDK or network imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Range as InputRange
from contracts.results.models import Missing as ResultsMissing
from contracts.results.models import Range as ResultsRange
from decision.grounded_explainer import (
    GroundedFact,
    GroundedFactLedger,
    GroundingVerificationResult,
    GroundingViolation,
    ledger_from_decision_output,
    render_deterministic_explanation,
    verify_explanation_grounding,
)
from decision.output import assemble_decision_output
from demo import matrix


def _sample_ledger(*, example_data: bool = True) -> GroundedFactLedger:
    return GroundedFactLedger(
        facts=(
            GroundedFact(
                metric_id="soil_loss",
                value=2.3654,
                unit="t ha-1 yr-1",
                provenance="DECLARED",
                source="PLACEHOLDER catalog record D125",
                precision=2,
                range=InputRange(low=1.90, high=2.80, kind="PLACEHOLDER_range"),
                rotation_id="rot_a",
            ),
            GroundedFact(
                metric_id="water_deficit_exposure",
                value=0.84,
                unit="dimensionless",
                provenance="SIMULATED",
                source="NASA POWER AG daily series (2001-2024)",
                precision=2,
                rotation_id="rot_a",
            ),
            GroundedFact(
                metric_id="soil_loss_reduction",
                value=12.5,
                unit="%",
                provenance="DERIVED",
                source="paired difference computation",
                precision=1,
                rotation_id="rot_b",
            ),
            GroundedFact(
                metric_id="soil_carbon_trend",
                value=None,
                unit="t C ha-1 yr-1",
                missing=ResultsMissing(reason="MISSING_INPUT", detail="amg_parameters"),
                rotation_id="rot_a",
            ),
        ),
        allowed_rotations=("rot_a", "rot_b"),
        decision_state="Not separated: within uncertainty",
        example_data=example_data,
        indicators_not_resolved=("soil_loss", "soil_carbon_trend"),
    )


# --- GroundedFact & GroundedFactLedger validation ----------------------------


def test_grounded_fact_enforces_c3_and_c4_invariants():
    with pytest.raises(ValueError, match="never both"):
        GroundedFact(
            metric_id="soil_loss",
            value=1.0,
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            source="PLACEHOLDER",
            missing=InputMissing(reason="NOT_DECLARED"),
        )

    with pytest.raises(ValueError, match="provenance"):
        GroundedFact(
            metric_id="soil_loss",
            value=1.0,
            unit="t ha-1 yr-1",
            provenance=None,
            source="PLACEHOLDER",
        )

    with pytest.raises(ValueError, match="source or assumption"):
        GroundedFact(
            metric_id="soil_loss",
            value=1.0,
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            source=None,
            assumption=False,
        )

    with pytest.raises(TypeError, match="Missing"):
        GroundedFact(
            metric_id="soil_loss",
            value=None,
            unit="t ha-1 yr-1",
            missing=None,
        )

    with pytest.raises(ValueError, match="no provenance"):
        GroundedFact(
            metric_id="soil_loss",
            value=None,
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            missing=InputMissing(reason="NOT_DECLARED"),
        )

    with pytest.raises(TypeError, match="float"):
        GroundedFact(
            metric_id="soil_loss",
            value=True,
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            source="PLACEHOLDER",
        )

    with pytest.raises(ValueError, match="finite"):
        GroundedFact(
            metric_id="soil_loss",
            value=float("nan"),
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            source="PLACEHOLDER",
        )

    with pytest.raises(ValueError, match="outside"):
        GroundedFact(
            metric_id="soil_loss",
            value=5.0,
            unit="t ha-1 yr-1",
            provenance="DECLARED",
            source="PLACEHOLDER",
            range=ResultsRange(low=1.0, high=3.0, kind="PLACEHOLDER"),
        )


def test_grounded_fact_ledger_enforces_rotations_and_immutability():
    with pytest.raises(ValueError, match="duplicate rotation"):
        GroundedFactLedger(
            facts=(),
            allowed_rotations=("rot_a", "rot_a"),
            decision_state="Identical",
        )

    with pytest.raises(ValueError, match="not in allowed_rotations"):
        GroundedFactLedger(
            facts=(
                GroundedFact(
                    metric_id="soil_loss",
                    value=2.0,
                    unit="t ha-1 yr-1",
                    provenance="DECLARED",
                    source="PLACEHOLDER",
                    rotation_id="rot_z",
                ),
            ),
            allowed_rotations=("rot_a", "rot_b"),
            decision_state="Identical",
        )

    with pytest.raises(ValueError, match="preferred_rotation_id"):
        GroundedFactLedger(
            facts=(),
            allowed_rotations=("rot_a", "rot_b"),
            decision_state="Robust preference",
            preferred_rotation_id="rot_c",
        )

    ledger = _sample_ledger()
    with pytest.raises(AttributeError):
        ledger.decision_state = "Identical"  # type: ignore[misc]


def test_verification_result_forbids_surfacing_withheld_text():
    with pytest.raises(ValueError, match="never be surfaced"):
        GroundingVerificationResult(
            verified=False,
            reason="CONTROL_FAILED",
            violations=(GroundingViolation(code="UNGROUNDED_NUMBER", detail="bad"),),
            surfaced_text="leaked candidate text",
        )

    with pytest.raises(ValueError, match="CONTROL_FAILED"):
        GroundingVerificationResult(
            verified=False,
            reason="NOT_AVAILABLE",
            violations=(GroundingViolation(code="UNGROUNDED_NUMBER", detail="bad"),),
        )


# --- render_deterministic_explanation ----------------------------------------


def test_render_deterministic_explanation_badges_missing_and_determinism():
    ledger = _sample_ledger(example_data=True)
    text_a = render_deterministic_explanation(ledger)
    text_b = render_deterministic_explanation(ledger)
    assert text_a == text_b
    assert "[EXAMPLE DATA" in text_a
    assert "Decision state: Not separated: within uncertainty" in text_a
    assert "Allowed rotations: rot_a, rot_b" in text_a
    assert "2.37 t ha-1 yr-1" in text_a
    assert "[PROVENANCE: DECLARED]" in text_a
    assert "[SOURCE: PLACEHOLDER catalog record D125]" in text_a
    assert "NASA POWER AG daily series (2001-2024)" in text_a
    assert "12.5%" in text_a
    assert "[MISSING: MISSING_INPUT] (amg_parameters)" in text_a

    non_example = _sample_ledger(example_data=False)
    non_example_text = render_deterministic_explanation(non_example)
    assert "[CASE DATA — non-example declaration]" in non_example_text
    assert "[EXAMPLE DATA" not in non_example_text

    # Rendered output must always pass the strict grounding verifier.
    check = verify_explanation_grounding(text_a, ledger)
    assert check.verified is True
    assert check.reason is None
    assert check.violations == ()
    assert check.surfaced_text == text_a


def test_render_and_verify_assumption_percentage_range_and_empty_ledger():
    pct_ledger = GroundedFactLedger(
        facts=(
            GroundedFact(
                metric_id="residue_cover_change",
                value=15.0,
                unit="%",
                provenance="DECLARED",
                assumption=True,
                precision=1,
                range=InputRange(low=10.0, high=20.0, kind="assumption_band"),
            ),
        ),
        allowed_rotations=("rot_a",),
        decision_state="Not evaluated",
    )
    rendered = render_deterministic_explanation(pct_ledger)
    assert "[10.0%, 20.0%]" in rendered
    assert "[ASSUMPTION]" in rendered
    assert verify_explanation_grounding(rendered, pct_ledger).verified is True

    empty_ledger = GroundedFactLedger(
        facts=(),
        allowed_rotations=("rot_a", "rot_b"),
        decision_state="Not evaluated",
    )
    empty_rendered = render_deterministic_explanation(empty_ledger)
    assert verify_explanation_grounding(empty_rendered, empty_ledger).verified is True


# --- verify_explanation_grounding: acceptance cases --------------------------


def test_verifier_accepts_grounded_prose_and_nasa_power_data_source():
    ledger = _sample_ledger()
    candidate = (
        "Decision state: Not separated: within uncertainty\n"
        "For rot_a, soil_loss is 2.37 t ha-1 yr-1 (DECLARED) using "
        "PLACEHOLDER catalog record D125, and water_deficit_exposure is "
        "0.84 dimensionless (SIMULATED) from NASA POWER AG daily series (2001-2024). "
        "For rot_b, soil_loss_reduction is 12.5% (DERIVED)."
    )
    result = verify_explanation_grounding(candidate, ledger)
    assert result.verified is True
    assert result.reason is None
    assert result.violations == ()
    assert result.surfaced_text == candidate


def test_verifier_accepts_negative_and_exact_and_comma_formatted_numbers():
    ledger = GroundedFactLedger(
        facts=(
            GroundedFact(
                metric_id="soil_carbon_trend",
                value=-0.45,
                unit="t C ha-1 yr-1",
                provenance="SIMULATED",
                source="EP5 AMG run",
                precision=2,
            ),
            GroundedFact(
                metric_id="margin_net",
                value=1250.5,
                unit="USD ha-1 yr-1",
                provenance="DERIVED",
                source="economic ledger",
                precision=1,
            ),
        ),
        allowed_rotations=("rot_a", "rot_b"),
        decision_state="Not evaluated",
    )
    candidate = (
        "soil_carbon_trend is -0.45 t C ha-1 yr-1 [PROVENANCE: SIMULATED]; "
        "margin_net is 1,250.5 USD ha-1 yr-1 [PROVENANCE: DERIVED]."
    )
    result = verify_explanation_grounding(candidate, ledger)
    assert result.verified is True


# --- verify_explanation_grounding: rejection cases ---------------------------


@pytest.mark.parametrize(
    ("candidate", "expected_code"),
    [
        ("", "EMPTY_CANDIDATE"),
        ("   \n\t  ", "EMPTY_CANDIDATE"),
        (
            "For rot_a, soil_loss is 9.99 t ha-1 yr-1 [PROVENANCE: DECLARED].",
            "UNGROUNDED_NUMBER",
        ),
        (
            "For rot_a, soil_loss is 2.38 t ha-1 yr-1 [PROVENANCE: DECLARED].",
            "UNGROUNDED_NUMBER",
        ),
        (
            "For rot_a, soil_loss is 2.369 t ha-1 yr-1 [PROVENANCE: DECLARED].",
            "UNGROUNDED_NUMBER",
        ),
        (
            "Rotation rot_b lowers erosion by 35%.",
            "UNGROUNDED_NUMBER",
        ),
        (
            "For rot_a, soil_loss is 2.37 kg ha-1 [PROVENANCE: DECLARED].",
            "UNIT_MISMATCH",
        ),
        (
            "For rot_a, soil_loss (bushels/acre): 2.37 [PROVENANCE: DECLARED].",
            "UNIT_MISMATCH",
        ),
        (
            "For rot_a, soil_loss is 2.37 bushels/acre [PROVENANCE: DECLARED].",
            "UNIT_MISMATCH",
        ),
        (
            "For rot_b, soil_loss_reduction is 12.5 [PROVENANCE: DERIVED].",
            "UNIT_MISMATCH",
        ),
        (
            "For rot_a, water_deficit_exposure is 2.37 dimensionless [PROVENANCE: SIMULATED].",
            "METRIC_PROVENANCE_MISMATCH",
        ),
        (
            "For rot_b, soil_loss is 2.37 t ha-1 yr-1 [PROVENANCE: DECLARED].",
            "METRIC_PROVENANCE_MISMATCH",
        ),
        (
            "For rot_a, soil_loss is 2.37 t ha-1 yr-1 [PROVENANCE: OBSERVED].",
            "PROVENANCE_MISMATCH",
        ),
        (
            "For rot_a, observed soil_loss is 2.37 t ha-1 yr-1.",
            "PROVENANCE_MISMATCH",
        ),
        (
            "For rot_a, soil_carbon_trend is 0.0 t C ha-1 yr-1.",
            "MISSING_VALUE_FABRICATED",
        ),
        (
            "For rot_a, soil_carbon_trend is 0.84 t C ha-1 yr-1.",
            "MISSING_VALUE_FABRICATED",
        ),
        (
            "Decision state: Robust preference\nPreferred rotation: rot_a",
            "DECISION_STATE_MISMATCH",
        ),
        (
            "For rotation 'rot_unknown', soil_loss is 2.37 t ha-1 yr-1.",
            "UNALLOWED_ROTATION",
        ),
        (
            "This is agronomic advice: you should plant rot_b next year.",
            "PROHIBITED_ADVICE",
        ),
        (
            "We recommend switching to rot_b immediately.",
            "PROHIBITED_ADVICE",
        ),
        (
            "Prescriptive guarantee: rot_b will definitely reduce soil loss with zero risk.",
            "PROHIBITED_GUARANTEE",
        ),
        (
            "This model provides a guaranteed yield outcome.",
            "PROHIBITED_GUARANTEE",
        ),
        (
            "This rotation is NASA endorsed and NASA validated for your field.",
            "PROHIBITED_ENDORSEMENT",
        ),
        (
            "Officially validated by NASA as the top option.",
            "PROHIBITED_ENDORSEMENT",
        ),
        (
            "This is not example data; it is a real producer field.",
            "EXAMPLE_DATA_MISMATCH",
        ),
    ],
)
def test_verifier_rejects_ungrounded_and_prohibited_candidates(
    candidate: str, expected_code: str
):
    ledger = _sample_ledger(example_data=True)
    secret_marker = "CANDIDATE_LEAK_GUARD_TOKEN"
    tagged_candidate = (
        candidate if candidate.strip() == "" else f"{candidate} {secret_marker}"
    )
    result = verify_explanation_grounding(tagged_candidate, ledger)

    assert result.verified is False
    assert result.reason == "CONTROL_FAILED"
    assert len(result.violations) >= 1
    assert any(v.code == expected_code for v in result.violations)
    assert result.surfaced_text is None
    assert secret_marker not in str(result)


def test_verifier_catches_parenthesized_wrong_unit_and_bracketed_pct_range():
    ledger = _sample_ledger()
    bad = "For rot_a, soil_loss (kg ha-1): 2.37 [PROVENANCE: DECLARED]."
    res_bad = verify_explanation_grounding(bad, ledger)
    assert res_bad.verified is False
    assert res_bad.reason == "CONTROL_FAILED"
    assert any(v.code == "UNIT_MISMATCH" for v in res_bad.violations)

    pct_ledger = GroundedFactLedger(
        facts=(
            GroundedFact(
                metric_id="cover_fraction",
                value=15.0,
                unit="%",
                provenance="DERIVED",
                source="synthetic band",
                precision=1,
                range=InputRange(low=10.0, high=20.0, kind="interval"),
            ),
        ),
        allowed_rotations=("rot_a",),
        decision_state="Not evaluated",
    )
    good = "cover_fraction is 15.0% (range [10.0, 20.0]%) [PROVENANCE: DERIVED]."
    assert verify_explanation_grounding(good, pct_ledger).verified is True


# --- Integration with DecisionOutput & static purity checks ------------------


def test_ledger_from_decision_output_round_trip():
    table = matrix.thin_matrix()
    document = assemble_decision_output(table, example_data=True)
    ledger = ledger_from_decision_output(document, table=table)

    assert ledger.example_data is True
    assert ledger.allowed_rotations == tuple(matrix.ROTATIONS)
    rendered = render_deterministic_explanation(ledger)
    verified = verify_explanation_grounding(rendered, ledger)
    assert verified.verified is True
    assert verified.surfaced_text == rendered


def test_module_has_zero_network_or_llm_sdk_imports():
    module_path = Path(__file__).with_name("grounded_explainer.py")
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    allowed_roots = frozenset(
        {"__future__", "collections", "contracts", "dataclasses", "math", "re"}
    )
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

    for name in imported:
        root_pkg = name.split(".", 1)[0]
        assert root_pkg in allowed_roots, f"non-allowlisted import: {name}"
