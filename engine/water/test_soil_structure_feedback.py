"""Tests for ``engine/water/soil_structure_feedback.py`` (Frontier Line L16).

Covers:
- Dynamic topsoil bulk density step (``step_bulk_density_state``): additive
  axle/traffic compaction increments (scalar and multi-event sequences),
  tillage loosening, biological relaxation toward baseline, boundary clamping
  within ``[min_bulk_density, max_bulk_density]``, and total porosity
  conservation ``bulk_density + porosity * particle_density == particle_density``.
- Surface structural crusting multiplier (``compute_surface_crusting_factor``):
  monotonic attenuation with cumulative rainfall kinetic energy since last
  tillage event, bounded in ``[min_crust_factor, 1.0]``.
- Coupled feedback series (``evaluate_soil_structure_feedback``): per-step
  ``bulk_density``, ``porosity``, ``crusting_factor``, effective
  ``infiltrability_ratio``, tillage kinetic-energy reset, and exploratory
  ``cn_delta_estimate`` diagnostics marked ``"EXPLORATORY"`` / ``"PROPOSED"``
  with ``normative_ep3_wired=False``.
- Typed ``Missing(reason="MISSING_INPUT" | "NOT_AVAILABLE")`` propagation
  (never ``0.0``), ``CONTROL_FAILED`` domain bounds, and ``NOT_COMPUTABLE``
  non-finite guards.
- G1 purity, immutability, determinism, G5 caller defect checks, and strict
  AST hygiene (stdlib + ``Missing`` only, zero hardcoded scientific literals
  or numeric defaults).

All parameters and forcing values in this file are synthetic PLACEHOLDER test
values, not from any field dataset or calibration study.
"""

from __future__ import annotations

import ast
import copy
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts.results.models import Missing
from engine.water import soil_structure_feedback
from engine.water.soil_structure_feedback import (
    DATA_AVAILABILITY_TAG,
    DIAGNOSTIC_TIER,
    FRONTIER_LINE,
    MATURITY_TAG,
    NORMATIVE_EP3_WIRED,
    STATUS_TAG,
    BulkDensityState,
    SoilStructureFeedbackSeries,
    SoilStructureFeedbackSpec,
    SoilStructureStepInput,
    compute_surface_crusting_factor,
    evaluate_soil_structure_feedback,
    step_bulk_density_state,
)

# Synthetic PLACEHOLDER test parameters (not physical recommendations).
PLACEHOLDER_PARTICLE_DENSITY = 2.5
PLACEHOLDER_MIN_BD = 1.0
PLACEHOLDER_MAX_BD = 1.75
PLACEHOLDER_BASELINE_BD = 1.25
PLACEHOLDER_BIO_RATE = 0.2
PLACEHOLDER_CRUST_DECAY = 0.01
PLACEHOLDER_MIN_CRUST = 0.25
PLACEHOLDER_POROSITY_EXP = 2.0
PLACEHOLDER_CN_SENS = 10.0


def _placeholder_spec(
    *,
    model_id: str = "placeholder_l16",
    particle_density: float | Missing = PLACEHOLDER_PARTICLE_DENSITY,
    min_bulk_density: float | Missing = PLACEHOLDER_MIN_BD,
    max_bulk_density: float | Missing = PLACEHOLDER_MAX_BD,
    baseline_bulk_density: float | Missing = PLACEHOLDER_BASELINE_BD,
    biological_relaxation_rate: float | Missing = PLACEHOLDER_BIO_RATE,
    crust_decay_rate: float | Missing = PLACEHOLDER_CRUST_DECAY,
    min_crust_factor: float | Missing = PLACEHOLDER_MIN_CRUST,
    porosity_infiltrability_exponent: float | Missing = PLACEHOLDER_POROSITY_EXP,
    cn_sensitivity: float | Missing = PLACEHOLDER_CN_SENS,
) -> SoilStructureFeedbackSpec:
    return SoilStructureFeedbackSpec(
        model_id=model_id,
        particle_density=particle_density,
        min_bulk_density=min_bulk_density,
        max_bulk_density=max_bulk_density,
        baseline_bulk_density=baseline_bulk_density,
        biological_relaxation_rate=biological_relaxation_rate,
        crust_decay_rate=crust_decay_rate,
        min_crust_factor=min_crust_factor,
        porosity_infiltrability_exponent=porosity_infiltrability_exponent,
        cn_sensitivity=cn_sensitivity,
    )


# ---------------------------------------------------------------------------
# Bulk density state step & porosity conservation


def test_step_bulk_density_exact_arithmetic_and_porosity_conservation() -> None:
    # Start at baseline 1.25, apply compaction 0.15 -> 1.40, bio_rate 0.2 relaxes
    # toward 1.25: 1.40 + 0.2 * (1.25 - 1.40) = 1.37
    state = step_bulk_density_state(
        1.25,
        compaction_increment=0.15,
        tillage_loosening=0.0,
        biological_relaxation_rate=0.2,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert isinstance(state, BulkDensityState)
    assert state.bulk_density == pytest.approx(1.37)
    assert state.porosity == pytest.approx(1.0 - 1.37 / 2.5)
    assert state.delta_bulk_density == pytest.approx(0.12)
    assert state.clamped_low is False
    assert state.clamped_high is False
    assert state.unit_bulk_density == "g cm-3"
    assert state.unit_porosity == "m3 m-3"
    assert state.status == "PROPOSED"
    assert state.frontier_line == "L16"
    assert state.data_availability == "LOCAL_MEASUREMENT_REQUIRED"

    # Conservation identity: bulk_density + porosity * particle_density == particle_density
    assert isinstance(state.bulk_density, float)
    assert isinstance(state.porosity, float)
    assert state.bulk_density + state.porosity * 2.5 == pytest.approx(2.5)


def test_step_bulk_density_multi_event_axle_sequence_and_tillage() -> None:
    state = step_bulk_density_state(
        1.40,
        compaction_increment=(0.04, 0.06),  # +0.10 -> 1.50
        tillage_loosening=0.20,  # -0.20 -> 1.30
        biological_relaxation_rate=0.0,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert state.bulk_density == pytest.approx(1.30)
    assert state.porosity == pytest.approx(1.0 - 1.30 / 2.5)

    # Empty event sequence adds 0.0 compaction; bio_rate=1.0 jumps to baseline.
    relaxed = step_bulk_density_state(
        1.50,
        compaction_increment=(),
        tillage_loosening=0.0,
        biological_relaxation_rate=1.0,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert relaxed.bulk_density == pytest.approx(1.25)


def test_step_bulk_density_boundary_clamping() -> None:
    # Upper bound clamp
    high = step_bulk_density_state(
        1.60,
        compaction_increment=0.50,
        tillage_loosening=0.0,
        biological_relaxation_rate=0.0,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert high.bulk_density == 1.75
    assert high.porosity == pytest.approx(1.0 - 1.75 / 2.5)
    assert high.clamped_high is True
    assert high.clamped_low is False

    # Lower bound clamp
    low = step_bulk_density_state(
        1.10,
        compaction_increment=0.0,
        tillage_loosening=0.50,
        biological_relaxation_rate=0.0,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert low.bulk_density == 1.0
    assert low.porosity == pytest.approx(1.0 - 1.0 / 2.5)
    assert low.clamped_low is True
    assert low.clamped_high is False


def test_step_bulk_density_monotonic_with_compaction_and_relaxation() -> None:
    compactions = (0.0, 0.05, 0.15, 0.30, 0.60)
    bds = []
    porosities = []
    for inc in compactions:
        st = step_bulk_density_state(
            1.25,
            compaction_increment=inc,
            tillage_loosening=0.0,
            biological_relaxation_rate=0.1,
            baseline_bulk_density=1.25,
            min_bulk_density=1.0,
            max_bulk_density=1.75,
            particle_density=2.5,
        )
        assert isinstance(st.bulk_density, float)
        assert isinstance(st.porosity, float)
        bds.append(st.bulk_density)
        porosities.append(st.porosity)

    assert all(bds[i] <= bds[i + 1] for i in range(len(bds) - 1))
    assert all(porosities[i] >= porosities[i + 1] for i in range(len(porosities) - 1))

    # Biological relaxation from compacted state decreases monotonically toward baseline.
    curr = 1.65
    for _ in range(10):
        nxt = step_bulk_density_state(
            curr,
            compaction_increment=0.0,
            tillage_loosening=0.0,
            biological_relaxation_rate=0.25,
            baseline_bulk_density=1.25,
            min_bulk_density=1.0,
            max_bulk_density=1.75,
            particle_density=2.5,
        )
        assert isinstance(nxt.bulk_density, float)
        assert 1.25 <= nxt.bulk_density < curr
        curr = nxt.bulk_density


# ---------------------------------------------------------------------------
# Surface crusting factor


def test_surface_crusting_factor_exact_values_and_monotonicity() -> None:
    f0 = compute_surface_crusting_factor(
        0.0,
        crust_decay_rate=0.01,
        min_crust_factor=0.25,
    )
    assert f0 == pytest.approx(1.0)

    f100 = compute_surface_crusting_factor(
        100.0,
        crust_decay_rate=0.01,
        min_crust_factor=0.25,
    )
    expected_100 = 0.25 + 0.75 * math.exp(-1.0)
    assert f100 == pytest.approx(expected_100)

    # Monotonically decreasing with cumulative kinetic energy and bounded below.
    energies = (0.0, 20.0, 100.0, 500.0, 1e6)
    factors = [
        compute_surface_crusting_factor(
            ke, crust_decay_rate=0.01, min_crust_factor=0.25
        )
        for ke in energies
    ]
    assert all(isinstance(f, float) for f in factors)
    float_factors = [float(f) for f in factors]  # type: ignore[arg-type]
    assert all(
        float_factors[i] >= float_factors[i + 1] for i in range(len(float_factors) - 1)
    )
    assert float_factors[-1] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Coupled feedback time series & exploratory diagnostics


def test_coupled_feedback_series_and_tillage_reset() -> None:
    spec = _placeholder_spec(
        biological_relaxation_rate=0.0,
        crust_decay_rate=0.01,
        min_crust_factor=0.20,
        porosity_infiltrability_exponent=2.0,
        cn_sensitivity=12.0,
    )
    steps = (
        # Day 1: baseline state, no traffic, no rain -> infiltrability=1.0, cn_delta=0.0
        SoilStructureStepInput(
            step_id="d1",
            compaction_increment=0.0,
            tillage_event=False,
            tillage_loosening=0.0,
            rainfall_kinetic_energy=0.0,
        ),
        # Day 2: traffic compaction + rainfall kinetic energy -> lower infiltrability, +cn_delta
        SoilStructureStepInput(
            step_id="d2",
            compaction_increment=0.25,
            tillage_event=False,
            tillage_loosening=0.0,
            rainfall_kinetic_energy=100.0,
        ),
        # Day 3: tillage loosens back to baseline and resets crusting kinetic energy
        SoilStructureStepInput(
            step_id="d3",
            compaction_increment=0.0,
            tillage_event=True,
            tillage_loosening=0.25,
            rainfall_kinetic_energy=0.0,
        ),
    )

    series = evaluate_soil_structure_feedback(
        steps,
        spec,
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert isinstance(series, SoilStructureFeedbackSeries)
    assert series.series_missing is None
    assert series.status == "PROPOSED"
    assert series.frontier_line == "L16"
    assert series.maturity == "FRONTIER"
    assert series.data_availability == "LOCAL_MEASUREMENT_REQUIRED"
    assert series.cn_delta_diagnostic_tier == "EXPLORATORY"
    assert series.normative_ep3_wired is False

    s1, s2, s3 = series.steps
    assert s1.bulk_density == pytest.approx(1.25)
    assert s1.porosity == pytest.approx(0.50)
    assert s1.crusting_factor == pytest.approx(1.0)
    assert s1.infiltrability_ratio == pytest.approx(1.0)
    assert s1.cn_delta_estimate == pytest.approx(0.0)
    assert s1.cn_delta_diagnostic_tier == "EXPLORATORY"
    assert s1.normative_ep3_wired is False

    # Day 2: bd=1.50 -> porosity = 1 - 1.5/2.5 = 0.40; ratio = (0.4/0.5)^2 = 0.64
    expected_crust_2 = 0.20 + 0.80 * math.exp(-1.0)
    expected_infilt_2 = expected_crust_2 * (0.40 / 0.50) ** 2
    expected_cn_2 = 12.0 * (1.0 - expected_infilt_2)
    assert s2.bulk_density == pytest.approx(1.50)
    assert s2.porosity == pytest.approx(0.40)
    assert s2.cumulative_kinetic_energy == pytest.approx(100.0)
    assert s2.crusting_factor == pytest.approx(expected_crust_2)
    assert s2.infiltrability_ratio == pytest.approx(expected_infilt_2)
    assert s2.cn_delta_estimate == pytest.approx(expected_cn_2)
    assert s2.cn_delta_estimate > 0.0

    # Day 3: tillage resets both bd and cumulative KE
    assert s3.bulk_density == pytest.approx(1.25)
    assert s3.porosity == pytest.approx(0.50)
    assert s3.cumulative_kinetic_energy == pytest.approx(0.0)
    assert s3.crusting_factor == pytest.approx(1.0)
    assert s3.infiltrability_ratio == pytest.approx(1.0)
    assert s3.cn_delta_estimate == pytest.approx(0.0)
    assert series.final_bulk_density == pytest.approx(1.25)
    assert series.final_cn_delta_estimate == pytest.approx(0.0)


def test_not_wired_into_normative_ep3_or_exposure_or_curve_number() -> None:
    water_dir = Path(soil_structure_feedback.__file__).parent
    for rel in ("__init__.py", "exposure.py", "runoff/curve_number.py"):
        text = (water_dir / rel).read_text(encoding="utf-8")
        assert "soil_structure_feedback" not in text
    assert NORMATIVE_EP3_WIRED is False
    assert FRONTIER_LINE == "L16"
    assert STATUS_TAG == "PROPOSED"
    assert MATURITY_TAG == "FRONTIER"
    assert DATA_AVAILABILITY_TAG == "LOCAL_MEASUREMENT_REQUIRED"
    assert DIAGNOSTIC_TIER == "EXPLORATORY"


# ---------------------------------------------------------------------------
# Missing propagation & domain control checks


def test_missing_inputs_and_parameters_propagate_never_zero() -> None:
    # Missing in step_bulk_density_state
    bd_missing = step_bulk_density_state(
        Missing(reason="NOT_AVAILABLE", detail="no initial pedon core"),
        compaction_increment=0.05,
        tillage_loosening=0.0,
        biological_relaxation_rate=0.1,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert isinstance(bd_missing.bulk_density, Missing)
    assert bd_missing.bulk_density.reason == "NOT_AVAILABLE"
    assert bd_missing.bulk_density != 0.0
    assert isinstance(bd_missing.porosity, Missing)

    # Missing inside compaction event sequence
    seq_missing = step_bulk_density_state(
        1.25,
        compaction_increment=(
            0.02,
            Missing(reason="MISSING_INPUT", detail="no axle load"),
        ),
        tillage_loosening=0.0,
        biological_relaxation_rate=0.1,
        baseline_bulk_density=1.25,
        min_bulk_density=1.0,
        max_bulk_density=1.75,
        particle_density=2.5,
    )
    assert isinstance(seq_missing.bulk_density, Missing)
    assert seq_missing.bulk_density.reason == "MISSING_INPUT"

    # Missing in compute_surface_crusting_factor
    crust_missing = compute_surface_crusting_factor(
        Missing(reason="MISSING_INPUT", detail="no rainfall energy"),
        crust_decay_rate=0.01,
        min_crust_factor=0.25,
    )
    assert isinstance(crust_missing, Missing)
    assert crust_missing.reason == "MISSING_INPUT"

    # Missing spec parameter in evaluate_soil_structure_feedback
    step = SoilStructureStepInput(
        step_id="d1",
        compaction_increment=0.0,
        tillage_event=False,
        tillage_loosening=0.0,
        rainfall_kinetic_energy=10.0,
    )
    res_spec = evaluate_soil_structure_feedback(
        [step],
        _placeholder_spec(
            crust_decay_rate=Missing(reason="NOT_AVAILABLE", detail="uncalibrated")
        ),
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert isinstance(res_spec.series_missing, Missing)
    assert res_spec.series_missing.reason == "NOT_AVAILABLE"
    assert isinstance(res_spec.final_bulk_density, Missing)
    assert res_spec.final_bulk_density != 0.0

    # Missing pedon measurement on step 2 propagates to step 3 and series_missing
    s1 = step
    s2 = SoilStructureStepInput(
        step_id="d2",
        compaction_increment=0.0,
        tillage_event=False,
        tillage_loosening=0.0,
        rainfall_kinetic_energy=10.0,
        measured_bulk_density=Missing(reason="NOT_AVAILABLE", detail="core missing"),
    )
    s3 = SoilStructureStepInput(
        step_id="d3",
        compaction_increment=0.0,
        tillage_event=False,
        tillage_loosening=0.0,
        rainfall_kinetic_energy=10.0,
    )
    res_step = evaluate_soil_structure_feedback(
        [s1, s2, s3],
        _placeholder_spec(),
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert isinstance(res_step.steps[0].bulk_density, float)
    assert isinstance(res_step.steps[1].bulk_density, Missing)
    assert res_step.steps[1].bulk_density.reason == "NOT_AVAILABLE"
    assert isinstance(res_step.steps[2].bulk_density, Missing)
    assert isinstance(res_step.series_missing, Missing)

    # Empty steps -> MISSING_INPUT
    res_empty = evaluate_soil_structure_feedback(
        [],
        _placeholder_spec(),
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert isinstance(res_empty.series_missing, Missing)
    assert res_empty.series_missing.reason == "MISSING_INPUT"


@pytest.mark.parametrize(
    ("kwargs", "expected_reason"),
    [
        ({"particle_density": 0.0}, "CONTROL_FAILED"),
        ({"min_bulk_density": 0.0}, "CONTROL_FAILED"),
        ({"min_bulk_density": 1.8, "max_bulk_density": 1.75}, "CONTROL_FAILED"),
        ({"max_bulk_density": 2.5}, "CONTROL_FAILED"),
        ({"baseline_bulk_density": 0.9}, "CONTROL_FAILED"),
        ({"current_bulk_density": 1.8}, "CONTROL_FAILED"),
        ({"compaction_increment": -0.01}, "CONTROL_FAILED"),
        ({"tillage_loosening": -0.01}, "CONTROL_FAILED"),
        ({"biological_relaxation_rate": 1.1}, "CONTROL_FAILED"),
        ({"current_bulk_density": math.nan}, "NOT_COMPUTABLE"),
        ({"compaction_increment": math.inf}, "NOT_COMPUTABLE"),
    ],
)
def test_bulk_density_step_domain_and_finiteness_controls(
    kwargs: dict[str, float], expected_reason: str
) -> None:
    params: dict[str, object] = {
        "current_bulk_density": 1.25,
        "compaction_increment": 0.05,
        "tillage_loosening": 0.0,
        "biological_relaxation_rate": 0.1,
        "baseline_bulk_density": 1.25,
        "min_bulk_density": 1.0,
        "max_bulk_density": 1.75,
        "particle_density": 2.5,
    }
    params.update(kwargs)
    res = step_bulk_density_state(
        params["current_bulk_density"],  # type: ignore[arg-type]
        compaction_increment=params["compaction_increment"],  # type: ignore[arg-type]
        tillage_loosening=params["tillage_loosening"],  # type: ignore[arg-type]
        biological_relaxation_rate=params["biological_relaxation_rate"],  # type: ignore[arg-type]
        baseline_bulk_density=params["baseline_bulk_density"],  # type: ignore[arg-type]
        min_bulk_density=params["min_bulk_density"],  # type: ignore[arg-type]
        max_bulk_density=params["max_bulk_density"],  # type: ignore[arg-type]
        particle_density=params["particle_density"],  # type: ignore[arg-type]
    )
    assert isinstance(res.bulk_density, Missing)
    assert res.bulk_density.reason == expected_reason


def test_crusting_and_series_domain_controls() -> None:
    assert (
        compute_surface_crusting_factor(
            -1.0, crust_decay_rate=0.01, min_crust_factor=0.2
        ).reason  # type: ignore[union-attr]
        == "CONTROL_FAILED"
    )
    assert (
        compute_surface_crusting_factor(
            10.0, crust_decay_rate=-0.01, min_crust_factor=0.2
        ).reason  # type: ignore[union-attr]
        == "CONTROL_FAILED"
    )
    assert (
        compute_surface_crusting_factor(
            10.0, crust_decay_rate=0.01, min_crust_factor=1.1
        ).reason  # type: ignore[union-attr]
        == "CONTROL_FAILED"
    )
    assert (
        compute_surface_crusting_factor(
            math.nan, crust_decay_rate=0.01, min_crust_factor=0.2
        ).reason  # type: ignore[union-attr]
        == "NOT_COMPUTABLE"
    )

    # Tillage loosening > 0 without tillage_event=True -> CONTROL_FAILED
    bad_tillage = SoilStructureStepInput(
        step_id="d1",
        compaction_increment=0.0,
        tillage_event=False,
        tillage_loosening=0.10,
        rainfall_kinetic_energy=0.0,
    )
    res = evaluate_soil_structure_feedback(
        [bad_tillage],
        _placeholder_spec(),
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert isinstance(res.series_missing, Missing)
    assert res.series_missing.reason == "CONTROL_FAILED"


# ---------------------------------------------------------------------------
# G1 purity, immutability, AST hygiene, and G5 caller checks


def test_frozen_pure_deterministic_non_mutating() -> None:
    spec = _placeholder_spec()
    steps = (
        SoilStructureStepInput(
            step_id="d1",
            compaction_increment=(0.05,),
            tillage_event=False,
            tillage_loosening=0.0,
            rainfall_kinetic_energy=25.0,
        ),
    )
    spec_copy = copy.deepcopy(spec)
    steps_copy = copy.deepcopy(steps)

    r1 = evaluate_soil_structure_feedback(
        steps,
        spec,
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    r2 = evaluate_soil_structure_feedback(
        steps,
        spec,
        initial_bulk_density=1.25,
        initial_cumulative_kinetic_energy=0.0,
    )
    assert r1 == r2
    assert spec == spec_copy
    assert steps == steps_copy

    with pytest.raises(FrozenInstanceError):
        r1.final_bulk_density = 1.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        steps[0].tillage_loosening = 0.5  # type: ignore[misc]


def test_ast_hygiene_zero_science_constants_no_defaults_pure_imports() -> None:
    module_path = Path(soil_structure_feedback.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    allowed_import_roots = {
        "__future__",
        "math",
        "collections",
        "dataclasses",
        "contracts",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, f"unexpected import: {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root in allowed_import_roots, f"unexpected import: {node.module}"
            if root == "contracts":
                assert node.module == "contracts.results.models"
                assert [alias.name for alias in node.names] == ["Missing"]

    # Zero scientific numeric literals: only structural 0/0.0/1/1.0 allowed.
    allowed_numbers = {0, 0.0, 1, 1.0}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                continue
            assert node.value in allowed_numbers, (
                f"unexpected numeric literal {node.value!r} in soil_structure_feedback.py"
            )

    # Zero numeric defaults in any function signature or dataclass field.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default_node in [*node.args.defaults, *node.args.kw_defaults]:
                if isinstance(default_node, ast.Constant) and isinstance(
                    default_node.value, (int, float)
                ):
                    if not isinstance(default_node.value, bool):
                        raise AssertionError(
                            f"numeric default {default_node.value!r} in {node.name}"
                        )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, (int, float)) and not isinstance(
                node.value.value, bool
            ):
                # Module-level _ZERO/_ONE structural constants are allowed; class fields are not.
                if isinstance(node.target, ast.Name) and node.target.id not in {
                    "_ZERO",
                    "_ONE",
                }:
                    raise AssertionError(
                        f"numeric default {node.value.value!r} on {node.target.id}"
                    )


def test_g5_caller_defects_raise_type_or_value_error() -> None:
    with pytest.raises(TypeError):
        step_bulk_density_state(
            True,  # type: ignore[arg-type]
            compaction_increment=0.0,
            tillage_loosening=0.0,
            biological_relaxation_rate=0.1,
            baseline_bulk_density=1.25,
            min_bulk_density=1.0,
            max_bulk_density=1.75,
            particle_density=2.5,
        )
    with pytest.raises(TypeError):
        compute_surface_crusting_factor(
            "10.0",  # type: ignore[arg-type]
            crust_decay_rate=0.01,
            min_crust_factor=0.2,
        )
    with pytest.raises(TypeError):
        evaluate_soil_structure_feedback(
            "not a sequence",  # type: ignore[arg-type]
            _placeholder_spec(),
            initial_bulk_density=1.25,
            initial_cumulative_kinetic_energy=0.0,
        )
    with pytest.raises(ValueError):
        evaluate_soil_structure_feedback(
            [],
            _placeholder_spec(model_id="   "),
            initial_bulk_density=1.25,
            initial_cumulative_kinetic_energy=0.0,
        )
    with pytest.raises(ValueError):
        evaluate_soil_structure_feedback(
            [
                SoilStructureStepInput(
                    step_id="  ",
                    compaction_increment=0.0,
                    tillage_event=False,
                    tillage_loosening=0.0,
                    rainfall_kinetic_energy=0.0,
                )
            ],
            _placeholder_spec(),
            initial_bulk_density=1.25,
            initial_cumulative_kinetic_energy=0.0,
        )
