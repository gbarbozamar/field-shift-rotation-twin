"""Acceptance and unit tests for ``decision/multi_objective_nsga2.py``.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Tests deterministic pure-Python NSGA-II non-dominated sorting, crowding
distance assignment, constrained dominance, missingness quarantine (zero
coercion to 0.0), validator hooks, and seeded evolutionary search over both
discrete crop/rotation sequences and continuous/integer decision vectors.

Run from the repository root:
    ``python -m pytest decision/test_multi_objective_nsga2.py -q``
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import FrozenInstanceError

import pytest

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing
from decision.multi_objective_nsga2 import (
    CandidateEvaluation,
    CandidateInput,
    ConstraintSpec,
    EvaluatedCandidate,
    ObjectiveSpec,
    UnrankableCandidate,
    VectorBound,
    constrained_dominates,
    crowding_distance_assignment,
    fast_non_dominated_sort,
    nsga2_search,
    partition_candidates,
    sequence_one_point_crossover,
    sequence_point_mutation,
    vector_polynomial_mutation,
    vector_sbx_crossover,
)

TWO_OBJECTIVES = (
    ObjectiveSpec(name="soil_loss", direction="minimize"),
    ObjectiveSpec(name="soil_carbon_trend", direction="maximize"),
)

THREE_OBJECTIVES = (
    ObjectiveSpec(name="soil_loss", direction="minimize"),
    ObjectiveSpec(name="water_deficit_exposure", direction="maximize"),
    ObjectiveSpec(name="soil_carbon_trend", direction="maximize"),
)


def _cand(
    cid: str,
    objectives: dict[str, float],
    *,
    total_violation: float = 0.0,
    genome: object = None,
) -> EvaluatedCandidate[object]:
    return EvaluatedCandidate(
        candidate_id=cid,
        genome=cid if genome is None else genome,
        objectives=objectives,
        total_violation=total_violation,
        is_feasible=(total_violation == 0.0),
    )


# --- Specification validation & immutability -----------------------------------


def test_objective_and_constraint_spec_validation():
    with pytest.raises(ValueError, match="non-empty"):
        ObjectiveSpec(name="  ", direction="minimize")
    with pytest.raises(ValueError, match="direction"):
        ObjectiveSpec(name="soil_loss", direction="lower")  # type: ignore[arg-type]

    assert ObjectiveSpec("soil_loss", "minimize").to_minimized(4.5) == 4.5
    assert ObjectiveSpec("soil_carbon_trend", "maximize").to_minimized(0.3) == -0.3

    with pytest.raises(ValueError, match="finite"):
        ConstraintSpec(name="soil_loss", limit=float("nan"))
    with pytest.raises(ValueError, match="tolerated_violation"):
        ConstraintSpec(name="soil_loss", limit=7.0, tolerated_violation=-0.1)
    with pytest.raises(ValueError, match="weight"):
        ConstraintSpec(name="soil_loss", limit=7.0, weight=0.0)
    with pytest.raises(ValueError, match="low"):
        VectorBound(low=5.0, high=2.0)


def test_constraint_spec_tolerated_violation_for_both_senses():
    upper = ConstraintSpec(
        name="soil_loss",
        limit=7.0,
        sense="<=",
        tolerated_violation=0.5,
        weight=2.0,
    )
    assert upper.violation(6.8) == 0.0
    assert upper.violation(7.5) == 0.0  # within tolerated 0.5
    assert upper.violation(8.0) == pytest.approx(1.0)  # (1.0 - 0.5) * 2.0

    lower = ConstraintSpec(
        name="water_deficit_exposure",
        limit=0.75,
        sense=">=",
        tolerated_violation=0.05,
    )
    assert lower.violation(0.80) == 0.0
    assert lower.violation(0.70) == pytest.approx(0.0)  # within tolerated 0.05
    assert lower.violation(0.60) == pytest.approx(0.10)


def test_evaluated_candidate_rejects_non_finite_and_is_frozen():
    with pytest.raises(ValueError, match="must be finite"):
        EvaluatedCandidate(
            candidate_id="bad",
            genome=("soy",),
            objectives={"soil_loss": float("nan")},
        )
    with pytest.raises(ValueError, match="must be finite"):
        EvaluatedCandidate(
            candidate_id="bad_bool",
            genome=("soy",),
            objectives={"soil_loss": True},  # type: ignore[dict-item]
        )
    with pytest.raises(ValueError, match="at least one Missing"):
        UnrankableCandidate(
            candidate_id="empty",
            genome=("soy",),
            missing_reasons={},
        )

    cand = _cand("c1", {"soil_loss": 3.0, "soil_carbon_trend": 0.2})
    with pytest.raises(FrozenInstanceError):
        cand.rank = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        cand.objectives["soil_loss"] = 0.0  # type: ignore[index]


# --- Missingness & quarantine (never coerce to 0.0) ---------------------------


def test_missing_none_nan_inf_never_coerced_to_zero_and_quarantined():
    # If None/NaN were coerced to 0.0 on a minimization objective, it would
    # falsely beat finite_good (soil_loss=1.5). Quarantine must prevent that.
    raw = [
        CandidateInput(
            "finite_good",
            ("wheat", "soy"),
            CandidateEvaluation({"soil_loss": 1.5, "soil_carbon_trend": 0.4}),
        ),
        CandidateInput(
            "finite_zero",
            ("cover", "wheat"),
            CandidateEvaluation({"soil_loss": 0.0, "soil_carbon_trend": 0.1}),
        ),
        CandidateInput(
            "none_obj",
            ("soy", "soy"),
            CandidateEvaluation({"soil_loss": None, "soil_carbon_trend": 0.9}),
        ),
        CandidateInput(
            "typed_missing_results",
            ("maize", "soy"),
            CandidateEvaluation(
                {
                    "soil_loss": Missing(
                        reason="NO_COVERAGE", detail="no station record"
                    ),
                    "soil_carbon_trend": 0.8,
                }
            ),
        ),
        CandidateInput(
            "typed_missing_inputs",
            ("maize", "wheat"),
            CandidateEvaluation(
                {
                    "soil_loss": 0.5,
                    "soil_carbon_trend": InputMissing(
                        reason="SOURCE_UNAVAILABLE", detail="model offline"
                    ),
                }
            ),
        ),
        CandidateInput(
            "nan_obj",
            ("f1",),
            CandidateEvaluation({"soil_loss": float("nan"), "soil_carbon_trend": 0.5}),
        ),
        CandidateInput(
            "inf_obj",
            ("f2",),
            CandidateEvaluation({"soil_loss": float("-inf"), "soil_carbon_trend": 0.5}),
        ),
        CandidateInput(
            "missing_key",
            ("f3",),
            CandidateEvaluation({"soil_loss": 0.2}),
        ),
        CandidateInput(
            "missing_constraint",
            ("f4",),
            CandidateEvaluation(
                objectives={"soil_loss": 0.4, "soil_carbon_trend": 0.9},
                constraint_values={"nitrate": None},
            ),
        ),
    ]
    constraints = (ConstraintSpec(name="nitrate", limit=20.0, sense="<="),)
    # Provide finite constraint for finite candidates so only missing_constraint lacks it.
    patched = []
    for item in raw:
        if "nitrate" not in item.evaluation.constraint_values:
            patched.append(
                CandidateInput(
                    item.candidate_id,
                    item.genome,
                    CandidateEvaluation(
                        objectives=item.evaluation.objectives,
                        constraint_values={"nitrate": 10.0},
                    ),
                )
            )
        else:
            patched.append(item)

    quarantined: list[UnrankableCandidate[object]] = []
    fronts = fast_non_dominated_sort(
        patched, TWO_OBJECTIVES, constraints, unrankable_out=quarantined
    )

    ranked_ids = {c.candidate_id for front in fronts for c in front}
    # Actual finite 0.0 stays rankable; all 7 missing/non-finite are quarantined.
    assert ranked_ids == {"finite_good", "finite_zero"}
    assert len(quarantined) == 7

    by_id = {u.candidate_id: u for u in quarantined}
    assert by_id["none_obj"].missing_reasons["soil_loss"].reason == "MISSING_INPUT"
    assert (
        by_id["typed_missing_results"].missing_reasons["soil_loss"].reason
        == "NO_COVERAGE"
    )
    assert (
        by_id["typed_missing_inputs"].missing_reasons["soil_carbon_trend"].reason
        == "SOURCE_UNAVAILABLE"
    )
    assert by_id["nan_obj"].missing_reasons["soil_loss"].reason == "NOT_COMPUTABLE"
    assert by_id["inf_obj"].missing_reasons["soil_loss"].reason == "NOT_COMPUTABLE"
    assert by_id["missing_key"].missing_reasons["soil_carbon_trend"].reason == (
        "MISSING_INPUT"
    )
    assert (
        by_id["missing_constraint"].missing_reasons["constraint:nitrate"].reason
        == "MISSING_INPUT"
    )


def test_all_missing_population_returns_empty_fronts():
    result = nsga2_search(
        objectives=TWO_OBJECTIVES,
        evaluator=lambda _g: CandidateEvaluation(
            {
                "soil_loss": Missing(reason="NOT_AVAILABLE", detail="engine off"),
                "soil_carbon_trend": None,
            }
        ),
        initial_population=[("a", "b"), ("b", "a")],
        crossover=sequence_one_point_crossover,
        mutate=lambda g, rng: sequence_point_mutation(g, ("a", "b"), rng),
        generations=3,
        seed=11,
    )
    assert result.pareto_fronts == ()
    assert result.best_front == ()
    assert result.feasible_count == 0
    assert result.infeasible_count == 0
    assert len(result.unrankable_missing) == 2


# --- Constrained dominance & non-dominated sorting ---------------------------


def test_constrained_dominance_rules():
    feasible_mediocre = _cand(
        "feas_mediocre",
        {"soil_loss": 6.5, "soil_carbon_trend": 0.05},
        total_violation=0.0,
    )
    infeasible_great_obj = _cand(
        "infeas_low_viol",
        {"soil_loss": 1.0, "soil_carbon_trend": 1.5},
        total_violation=0.4,
    )
    infeasible_high_viol = _cand(
        "infeas_high_viol",
        {"soil_loss": 0.1, "soil_carbon_trend": 3.0},
        total_violation=1.2,
    )
    infeasible_tie_viol = _cand(
        "infeas_tie_viol",
        {"soil_loss": 2.0, "soil_carbon_trend": 0.8},
        total_violation=0.4,
    )

    # Feasible strictly dominates infeasible regardless of objective values.
    assert constrained_dominates(
        feasible_mediocre, infeasible_great_obj, TWO_OBJECTIVES
    )
    assert not constrained_dominates(
        infeasible_great_obj, feasible_mediocre, TWO_OBJECTIVES
    )

    # Among infeasible, strictly lower violation dominates regardless of objectives.
    assert constrained_dominates(
        infeasible_great_obj, infeasible_high_viol, TWO_OBJECTIVES
    )
    assert not constrained_dominates(
        infeasible_high_viol, infeasible_great_obj, TWO_OBJECTIVES
    )

    # Equal infeasible violation: neither dominates the other.
    assert not constrained_dominates(
        infeasible_great_obj, infeasible_tie_viol, TWO_OBJECTIVES
    )
    assert not constrained_dominates(
        infeasible_tie_viol, infeasible_great_obj, TWO_OBJECTIVES
    )

    fronts = fast_non_dominated_sort(
        [
            infeasible_high_viol,
            infeasible_tie_viol,
            feasible_mediocre,
            infeasible_great_obj,
        ],
        TWO_OBJECTIVES,
    )
    assert [[c.candidate_id for c in f] for f in fronts] == [
        ["feas_mediocre"],
        ["infeas_low_viol", "infeas_tie_viol"],
        ["infeas_high_viol"],
    ]
    assert [c.rank for f in fronts for c in f] == [0, 1, 1, 2]


def test_fast_non_dominated_sort_three_objectives_and_tolerated_violation():
    constraints = (
        ConstraintSpec(
            name="soil_loss",
            limit=7.0,
            sense="<=",
            tolerated_violation=0.2,
        ),
    )
    raw = [
        # Front 0: feasible non-dominated trade-offs (soil_loss <= 7.2 tolerated)
        CandidateInput(
            "A",
            "A",
            CandidateEvaluation(
                {
                    "soil_loss": 2.0,
                    "water_deficit_exposure": 0.70,
                    "soil_carbon_trend": 0.10,
                }
            ),
        ),
        CandidateInput(
            "B",
            "B",
            CandidateEvaluation(
                {
                    "soil_loss": 7.1,
                    "water_deficit_exposure": 0.90,
                    "soil_carbon_trend": 0.45,
                }
            ),
        ),
        CandidateInput(
            "C",
            "C",
            CandidateEvaluation(
                {
                    "soil_loss": 4.0,
                    "water_deficit_exposure": 0.85,
                    "soil_carbon_trend": 0.25,
                }
            ),
        ),
        # Front 1: dominated by C (worse on all three)
        CandidateInput(
            "D",
            "D",
            CandidateEvaluation(
                {
                    "soil_loss": 4.5,
                    "water_deficit_exposure": 0.80,
                    "soil_carbon_trend": 0.20,
                }
            ),
        ),
        # Front 2: infeasible (soil_loss=7.8 > 7.2 -> violation 0.6)
        CandidateInput(
            "E",
            "E",
            CandidateEvaluation(
                {
                    "soil_loss": 7.8,
                    "water_deficit_exposure": 0.99,
                    "soil_carbon_trend": 0.90,
                }
            ),
        ),
    ]
    fronts = fast_non_dominated_sort(raw, THREE_OBJECTIVES, constraints)
    assert [[c.candidate_id for c in f] for f in fronts] == [
        ["A", "B", "C"],
        ["D"],
        ["E"],
    ]
    assert all(c.is_feasible for c in fronts[0])
    assert fronts[2][0].is_feasible is False
    assert fronts[2][0].total_violation == pytest.approx(0.6)


# --- Crowding distance assignment ---------------------------------------------


def test_crowding_distance_edge_and_exact_analytical_values():
    assert crowding_distance_assignment((), TWO_OBJECTIVES) == ()

    single = crowding_distance_assignment(
        (_cand("only", {"soil_loss": 2.0, "soil_carbon_trend": 0.3}),),
        TWO_OBJECTIVES,
    )
    assert math.isinf(single[0].crowding_distance)

    pair = crowding_distance_assignment(
        (
            _cand("p1", {"soil_loss": 1.0, "soil_carbon_trend": 0.1}),
            _cand("p2", {"soil_loss": 5.0, "soil_carbon_trend": 0.5}),
        ),
        TWO_OBJECTIVES,
    )
    assert all(math.isinf(c.crowding_distance) for c in pair)

    # 4 non-dominated points:
    # soil_loss (min): 1.0, 2.0, 4.0, 5.0 -> span = 4.0
    # soil_carbon_trend (max, min=-val): 0.1 (-0.1), 0.2 (-0.2), 0.7 (-0.7), 0.9 (-0.9) -> span = 0.8
    p0 = _cand("p0", {"soil_loss": 1.0, "soil_carbon_trend": 0.1})
    p1 = _cand("p1", {"soil_loss": 2.0, "soil_carbon_trend": 0.2})
    p2 = _cand("p2", {"soil_loss": 4.0, "soil_carbon_trend": 0.7})
    p3 = _cand("p3", {"soil_loss": 5.0, "soil_carbon_trend": 0.9})
    crowded = crowding_distance_assignment((p2, p0, p3, p1), TWO_OBJECTIVES)
    by_id = {c.candidate_id: c.crowding_distance for c in crowded}
    # Preserve input order
    assert [c.candidate_id for c in crowded] == ["p2", "p0", "p3", "p1"]
    assert math.isinf(by_id["p0"])
    assert math.isinf(by_id["p3"])
    # p1: (4.0 - 1.0)/4.0 + (-0.1 - -0.7)/0.8 = 0.75 + 0.75 = 1.5
    assert by_id["p1"] == pytest.approx(1.5)
    # p2: (5.0 - 2.0)/4.0 + (-0.2 - -0.9)/0.8 = 0.75 + 0.875 = 1.625
    assert by_id["p2"] == pytest.approx(1.625)


def test_crowding_distance_handles_zero_span_and_ties_deterministically():
    # Identical objective values on both objectives -> zero span, no division by zero
    tied = tuple(
        _cand(f"c{i}", {"soil_loss": 3.0, "soil_carbon_trend": 0.2}) for i in range(4)
    )
    res1 = crowding_distance_assignment(tied, TWO_OBJECTIVES)
    res2 = crowding_distance_assignment(tied, TWO_OBJECTIVES)
    assert [c.crowding_distance for c in res1] == [c.crowding_distance for c in res2]
    assert math.isinf(res1[0].crowding_distance)
    assert math.isinf(res1[3].crowding_distance)
    assert res1[1].crowding_distance == 0.0
    assert res1[2].crowding_distance == 0.0


# --- Deterministic seeded evolution: discrete rotation sequences --------------


def test_discrete_crop_rotation_search_determinism_validator_and_tradeoffs():
    crops = ("soybean", "maize", "wheat", "cover_rye")
    # Synthetic toy agronomic scoring purely for structural search verification.
    erosion_score = {"soybean": 4.2, "maize": 2.4, "wheat": 1.3, "cover_rye": 0.5}
    carbon_delta = {"soybean": -0.25, "maize": 0.15, "wheat": 0.20, "cover_rye": 0.45}
    water_score = {"soybean": 0.65, "maize": 0.60, "wheat": 0.85, "cover_rye": 0.90}

    evaluated_invalid_log: list[tuple[str, ...]] = []

    def validator(seq: tuple[str, ...]) -> tuple[bool, str | None]:
        # Forbid consecutive soybean monoculture
        for a, b in itertools.pairwise(seq):
            if a == "soybean" and b == "soybean":
                return False, "consecutive soybean forbidden"
        return True, None

    def evaluator(seq: tuple[str, ...]) -> CandidateEvaluation:
        if any(a == "soybean" and b == "soybean" for a, b in itertools.pairwise(seq)):
            evaluated_invalid_log.append(seq)
        n = len(seq)
        return CandidateEvaluation(
            objectives={
                "soil_loss": sum(erosion_score[c] for c in seq) / n,
                "soil_carbon_trend": sum(carbon_delta[c] for c in seq) / n,
                "water_deficit_exposure": sum(water_score[c] for c in seq) / n,
            }
        )

    init_rng = random.Random(101)
    initial_pop: list[tuple[str, ...]] = [
        ("soybean", "soybean", "maize", "wheat"),  # intentionally invalid for validator
        ("soybean", "maize", "wheat", "cover_rye"),
        ("maize", "wheat", "soybean", "maize"),
        ("wheat", "cover_rye", "maize", "soybean"),
        ("soybean", "wheat", "soybean", "wheat"),
        ("maize", "maize", "soybean", "wheat"),
        ("cover_rye", "wheat", "maize", "wheat"),
        ("soybean", "cover_rye", "maize", "wheat"),
    ]
    # Add extra deterministic initial candidates
    for _ in range(4):
        initial_pop.append(tuple(init_rng.choice(crops) for _ in range(4)))

    constraints = (ConstraintSpec(name="soil_loss", limit=2.3, sense="<="),)

    # Perturb global random state to verify zero reliance on global RNG
    random.seed(99999)
    before_global_state = random.getstate()
    res_a = nsga2_search(
        objectives=THREE_OBJECTIVES,
        evaluator=evaluator,
        initial_population=initial_pop,
        crossover=sequence_one_point_crossover,
        mutate=lambda g, r: sequence_point_mutation(g, crops, r, mutation_rate=0.3),
        constraints=constraints,
        validator=validator,
        generations=12,
        population_size=12,
        seed=42,
        deduplicate_genomes=True,
    )
    after_global_state = random.getstate()
    assert before_global_state == after_global_state

    res_b = nsga2_search(
        objectives=THREE_OBJECTIVES,
        evaluator=evaluator,
        initial_population=initial_pop,
        crossover=sequence_one_point_crossover,
        mutate=lambda g, r: sequence_point_mutation(g, crops, r, mutation_rate=0.3),
        constraints=constraints,
        validator=validator,
        generations=12,
        population_size=12,
        seed=42,
        deduplicate_genomes=True,
    )

    # Bit-for-bit identical under same seed
    assert res_a == res_b
    # Validator-rejected rotations were NEVER passed to evaluator
    assert evaluated_invalid_log == []
    # Invalid initial candidate was quarantined cleanly
    assert any(
        u.genome == ("soybean", "soybean", "maize", "wheat")
        and u.missing_reasons["validator"].detail == "consecutive soybean forbidden"
        for u in res_a.unrankable_missing
    )
    # Best front exists, is non-dominated, and respects feasibility limit
    assert len(res_a.best_front) >= 1
    assert all(c.is_feasible for c in res_a.best_front)
    assert all(c.objectives["soil_loss"] <= 2.3 for c in res_a.best_front)
    for idx, c_i in enumerate(res_a.best_front):
        for jdx, c_j in enumerate(res_a.best_front):
            if idx != jdx:
                assert not constrained_dominates(c_i, c_j, THREE_OBJECTIVES)


# --- Continuous and integer vector search (SBX + polynomial mutation) ---------


def test_continuous_vector_search_recovers_non_dominated_pareto_front():
    bounds = (
        VectorBound(0.0, 1.0, is_integer=False),
        VectorBound(0.0, 1.0, is_integer=False),
        VectorBound(0.0, 1.0, is_integer=False),
    )
    objectives = (
        ObjectiveSpec("f1", "minimize"),
        ObjectiveSpec("f2", "minimize"),
    )

    def evaluator(vec: tuple[float, ...]) -> dict[str, float]:
        x0, x1, x2 = vec
        g = 1.0 + 4.5 * (x1 + x2)
        f1 = x0
        f2 = g * (1.0 - math.sqrt(max(0.0, f1 / g)))
        return {"f1": f1, "f2": f2}

    rng = random.Random(7)
    init_pop = [tuple(rng.uniform(b.low, b.high) for b in bounds) for _ in range(24)]

    result = nsga2_search(
        objectives=objectives,
        evaluator=evaluator,
        initial_population=init_pop,
        crossover=lambda a, b, r: vector_sbx_crossover(a, b, bounds, r),
        mutate=lambda g, r: vector_polynomial_mutation(g, bounds, r),
        generations=35,
        population_size=24,
        seed=17,
    )

    assert result.generations_completed == 35
    assert len(result.best_front) >= 5
    # Verify convergence near true Pareto front (g -> 1, so f2 ~ 1 - sqrt(f1))
    mean_err = sum(
        abs(c.objectives["f2"] - (1.0 - math.sqrt(c.objectives["f1"])))
        for c in result.best_front
    ) / len(result.best_front)
    assert mean_err < 0.05
    # Verify all decision vectors stay inside closed bounds
    for cand in result.all_ranked:
        for val, b in zip(cand.genome, bounds, strict=True):
            assert b.low <= val <= b.high


def test_integer_vector_operators_and_zero_generations_mode():
    bounds = (
        VectorBound(1, 5, is_integer=True),
        VectorBound(0, 10, is_integer=True),
    )
    rng = random.Random(3)
    c1, c2 = vector_sbx_crossover((1, 2), (5, 9), bounds, rng)
    m1 = vector_polynomial_mutation(c1, bounds, rng, mutation_rate=1.0)
    assert all(isinstance(v, int) for v in c1 + c2 + m1)
    for val, b in zip(m1, bounds, strict=True):
        assert b.low <= val <= b.high

    res_zero = nsga2_search(
        objectives=TWO_OBJECTIVES,
        evaluator=lambda vec: {
            "soil_loss": float(vec[0]),
            "soil_carbon_trend": float(vec[1]) * 0.1,
        },
        initial_population=[(1, 2), (2, 8), (3, 5)],
        crossover=lambda a, b, r: vector_sbx_crossover(a, b, bounds, r),
        mutate=lambda g, r: vector_polynomial_mutation(g, bounds, r),
        generations=0,
        seed=5,
    )
    assert res_zero.generations_completed == 0
    assert res_zero.evaluations_count == 3
    assert [c.genome for c in res_zero.best_front] in (
        [(1, 2), (2, 8)],
        [(2, 8), (1, 2)],
    )


def test_partition_candidates_reports_all_missing_reasons_and_input_validation():
    cands = [
        CandidateInput(
            "bad_both",
            ("a",),
            CandidateEvaluation({"soil_loss": None, "soil_carbon_trend": float("inf")}),
        )
    ]
    rankable, unrankable = partition_candidates(cands, TWO_OBJECTIVES)
    assert rankable == ()
    assert len(unrankable) == 1
    assert set(unrankable[0].missing_reasons) == {"soil_loss", "soil_carbon_trend"}

    with pytest.raises(ValueError, match="duplicate objective"):
        fast_non_dominated_sort(
            [],
            (
                ObjectiveSpec("soil_loss", "minimize"),
                ObjectiveSpec("soil_loss", "maximize"),
            ),
        )
