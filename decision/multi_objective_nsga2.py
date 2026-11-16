"""Deterministic pure-Python NSGA-II multi-objective search for rotation portfolios.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements Deb et al. (2002) fast non-dominated sorting, crowding distance
assignment, constrained dominance, and seeded evolutionary search for
agronomic rotation portfolios (Kasprzyk et al. 2013), using Python 3.12
standard library primitives only (zero external array or optimization
dependencies).

Governance and missingness rules:
- Pure function module (G1): no network calls, no file I/O, no system clock,
  no global mutable state. Determinism is governed solely by ``seed``.
- Explicit missingness (contracts/CONVENTIONS.md C3.1-C3.2): any candidate
  with ``None``, ``Missing``, non-numeric, or non-finite (``NaN`` / ``Inf``)
  objective or constraint metric values is never coerced to ``0.0``; it is
  quarantined in ``unrankable_missing`` with typed ``Missing`` reasons.
- Zero hardcoded agronomic thresholds or weights: all objectives, directions,
  feasibility limits, and tolerated violations are supplied by the caller.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing

__all__ = [
    "CandidateEvaluation",
    "CandidateInput",
    "ConstraintSense",
    "ConstraintSpec",
    "EvaluatedCandidate",
    "NSGA2Result",
    "ObjectiveDirection",
    "ObjectiveSpec",
    "UnrankableCandidate",
    "VectorBound",
    "constrained_dominates",
    "crowding_distance_assignment",
    "fast_non_dominated_sort",
    "nsga2_search",
    "partition_candidates",
    "sequence_one_point_crossover",
    "sequence_point_mutation",
    "vector_polynomial_mutation",
    "vector_sbx_crossover",
]

ObjectiveDirection = Literal["minimize", "maximize"]
ConstraintSense = Literal["<=", ">="]

_EMPTY_MAPPING: Mapping[str, Any] = MappingProxyType({})


def _freeze_mapping(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a read-only mapping copy for frozen dataclasses."""
    if not mapping:
        return _EMPTY_MAPPING
    if isinstance(mapping, MappingProxyType):
        return mapping
    return MappingProxyType(dict(mapping))


def _is_finite_number(value: Any) -> bool:
    """Return True only for finite int/float values (excluding booleans)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _coerce_missing(metric_name: str, raw: Any, *, kind_label: str) -> Missing | None:
    """Return a typed Missing if raw is not a finite number, else None."""
    if raw is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=f"{kind_label} '{metric_name}' is None (C3.1)",
        )
    if isinstance(raw, Missing):
        return raw
    if isinstance(raw, InputMissing):
        return Missing(reason=raw.reason, detail=raw.detail)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"{kind_label} '{metric_name}' has non-numeric value "
                f"of type {type(raw).__name__}"
            ),
        )
    if not math.isfinite(float(raw)):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=f"{kind_label} '{metric_name}' is non-finite ({raw})",
        )
    return None


@dataclass(frozen=True)
class ObjectiveSpec:
    """Named objective with explicit optimization direction."""

    name: str
    direction: ObjectiveDirection

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name.strip() == "":
            raise ValueError("objective name must be a non-empty string")
        if self.direction not in ("minimize", "maximize"):
            raise ValueError(
                f"objective '{self.name}' direction must be 'minimize' or "
                f"'maximize', got {self.direction!r}"
            )

    def to_minimized(self, value: float) -> float:
        """Transform a finite objective value into minimization space."""
        return float(value) if self.direction == "minimize" else -float(value)


@dataclass(frozen=True)
class ConstraintSpec:
    """Feasibility limit with optional tolerated violation for constrained dominance."""

    name: str
    limit: float
    sense: ConstraintSense = "<="
    tolerated_violation: float = 0.0
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name.strip() == "":
            raise ValueError("constraint name must be a non-empty string")
        if not _is_finite_number(self.limit):
            raise ValueError(f"constraint '{self.name}' limit must be a finite number")
        if self.sense not in ("<=", ">="):
            raise ValueError(
                f"constraint '{self.name}' sense must be '<=' or '>=', "
                f"got {self.sense!r}"
            )
        if (
            not _is_finite_number(self.tolerated_violation)
            or float(self.tolerated_violation) < 0.0
        ):
            raise ValueError(
                f"constraint '{self.name}' tolerated_violation must be finite and >= 0"
            )
        if not _is_finite_number(self.weight) or float(self.weight) <= 0.0:
            raise ValueError(f"constraint '{self.name}' weight must be finite and > 0")

    def violation(self, value: float) -> float:
        """Compute weighted excess violation beyond tolerated_violation."""
        val = float(value)
        limit = float(self.limit)
        raw = max(0.0, val - limit) if self.sense == "<=" else max(0.0, limit - val)
        if raw <= float(self.tolerated_violation):
            return 0.0
        return (raw - float(self.tolerated_violation)) * float(self.weight)


@dataclass(frozen=True)
class VectorBound:
    """Closed decision-variable bound for continuous or integer vector genomes."""

    low: float
    high: float
    is_integer: bool = False

    def __post_init__(self) -> None:
        if not _is_finite_number(self.low) or not _is_finite_number(self.high):
            raise ValueError("vector bounds must be finite numbers")
        if float(self.low) > float(self.high):
            raise ValueError(
                f"vector bound low ({self.low}) cannot exceed high ({self.high})"
            )


@dataclass(frozen=True)
class CandidateEvaluation:
    """Raw output from a caller-supplied evaluator before missingness gating."""

    objectives: Mapping[str, float | int | Missing | None]
    constraint_values: Mapping[str, float | int | Missing | None] = field(
        default_factory=dict
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "objectives", _freeze_mapping(self.objectives))
        object.__setattr__(
            self, "constraint_values", _freeze_mapping(self.constraint_values)
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class CandidateInput[GenomeT]:
    """Unvalidated candidate bundle for standalone partitioning or sorting."""

    candidate_id: str
    genome: GenomeT
    evaluation: CandidateEvaluation


@dataclass(frozen=True)
class EvaluatedCandidate[GenomeT]:
    """Rankable candidate with strictly finite objectives and computed violation."""

    candidate_id: str
    genome: GenomeT
    objectives: Mapping[str, float]
    constraint_values: Mapping[str, float] = field(default_factory=dict)
    constraint_violations: Mapping[str, float] = field(default_factory=dict)
    total_violation: float = 0.0
    is_feasible: bool = True
    rank: int = 0
    crowding_distance: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        frozen_obj = {k: float(v) for k, v in self.objectives.items()}
        for k, v in self.objectives.items():
            if not _is_finite_number(v):
                raise ValueError(
                    f"EvaluatedCandidate '{self.candidate_id}' objective '{k}' "
                    f"must be finite, got {v!r}"
                )
        for k, v in self.constraint_values.items():
            if not _is_finite_number(v):
                raise ValueError(
                    f"EvaluatedCandidate '{self.candidate_id}' constraint value "
                    f"'{k}' must be finite, got {v!r}"
                )
        for k, v in self.constraint_violations.items():
            if not _is_finite_number(v) or float(v) < 0.0:
                raise ValueError(
                    f"EvaluatedCandidate '{self.candidate_id}' constraint "
                    f"violation '{k}' must be finite and >= 0, got {v!r}"
                )
        if not _is_finite_number(self.total_violation) or self.total_violation < 0.0:
            raise ValueError("total_violation must be finite and >= 0")
        object.__setattr__(self, "objectives", _freeze_mapping(frozen_obj))
        object.__setattr__(
            self,
            "constraint_values",
            _freeze_mapping({k: float(v) for k, v in self.constraint_values.items()}),
        )
        object.__setattr__(
            self,
            "constraint_violations",
            _freeze_mapping(
                {k: float(v) for k, v in self.constraint_violations.items()}
            ),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class UnrankableCandidate[GenomeT]:
    """Candidate quarantined because at least one required metric is missing/invalid."""

    candidate_id: str
    genome: GenomeT
    missing_reasons: Mapping[str, Missing]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.missing_reasons:
            raise ValueError(
                "UnrankableCandidate must carry at least one Missing reason"
            )
        object.__setattr__(
            self, "missing_reasons", _freeze_mapping(self.missing_reasons)
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class NSGA2Result[GenomeT]:
    """Final output of ``nsga2_search`` with ranked fronts and quarantined candidates."""

    pareto_fronts: tuple[tuple[EvaluatedCandidate[GenomeT], ...], ...]
    unrankable_missing: tuple[UnrankableCandidate[GenomeT], ...]
    objectives: tuple[ObjectiveSpec, ...]
    constraints: tuple[ConstraintSpec, ...]
    seed: int
    generations_completed: int
    evaluations_count: int
    feasible_count: int
    infeasible_count: int

    @property
    def best_front(self) -> tuple[EvaluatedCandidate[GenomeT], ...]:
        """Return the rank-0 non-dominated Pareto front (empty if none rankable)."""
        return self.pareto_fronts[0] if self.pareto_fronts else ()

    @property
    def all_ranked(self) -> tuple[EvaluatedCandidate[GenomeT], ...]:
        """Return all ranked candidates flattened across fronts in front order."""
        return tuple(cand for front in self.pareto_fronts for cand in front)


def _validate_objectives_and_constraints(
    objectives: Sequence[ObjectiveSpec],
    constraints: Sequence[ConstraintSpec],
) -> tuple[tuple[ObjectiveSpec, ...], tuple[ConstraintSpec, ...]]:
    obj_tuple = tuple(objectives)
    if not obj_tuple:
        raise ValueError("at least one ObjectiveSpec is required")
    seen_names: set[str] = set()
    for spec in obj_tuple:
        if spec.name in seen_names:
            raise ValueError(f"duplicate objective name '{spec.name}'")
        seen_names.add(spec.name)
    return obj_tuple, tuple(constraints)


def _evaluate_candidate_record[GenomeT](
    candidate_id: str,
    genome: GenomeT,
    evaluation: CandidateEvaluation | Mapping[str, Any],
    objectives: Sequence[ObjectiveSpec],
    constraints: Sequence[ConstraintSpec],
) -> EvaluatedCandidate[GenomeT] | UnrankableCandidate[GenomeT]:
    """Validate finiteness and partition one evaluation without coercing missingness."""
    if isinstance(evaluation, Mapping):
        eval_obj = CandidateEvaluation(objectives=evaluation)
    elif isinstance(evaluation, CandidateEvaluation):
        eval_obj = evaluation
    else:
        raise TypeError(
            "evaluator must return CandidateEvaluation or Mapping, "
            f"got {type(evaluation).__name__}"
        )

    missing_reasons: dict[str, Missing] = {}
    finite_objectives: dict[str, float] = {}

    for spec in objectives:
        if spec.name not in eval_obj.objectives:
            missing_reasons[spec.name] = Missing(
                reason="MISSING_INPUT",
                detail=f"objective '{spec.name}' missing from evaluation (C3.1)",
            )
            continue
        raw_val = eval_obj.objectives[spec.name]
        missing = _coerce_missing(spec.name, raw_val, kind_label="objective")
        if missing is not None:
            missing_reasons[spec.name] = missing
        else:
            finite_objectives[spec.name] = float(raw_val)

    finite_constraint_vals: dict[str, float] = {}
    constraint_violations: dict[str, float] = {}
    total_violation = 0.0

    for c_spec in constraints:
        if c_spec.name in eval_obj.constraint_values:
            raw_c = eval_obj.constraint_values[c_spec.name]
        elif c_spec.name in eval_obj.objectives:
            raw_c = eval_obj.objectives[c_spec.name]
        else:
            missing_reasons.setdefault(
                f"constraint:{c_spec.name}",
                Missing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"constraint metric '{c_spec.name}' missing from evaluation"
                    ),
                ),
            )
            continue
        missing_c = _coerce_missing(c_spec.name, raw_c, kind_label="constraint metric")
        if missing_c is not None:
            missing_reasons.setdefault(f"constraint:{c_spec.name}", missing_c)
        else:
            c_val = float(raw_c)
            finite_constraint_vals[c_spec.name] = c_val
            viol = c_spec.violation(c_val)
            constraint_violations[c_spec.name] = (
                constraint_violations.get(c_spec.name, 0.0) + viol
            )
            total_violation += viol

    if missing_reasons:
        return UnrankableCandidate(
            candidate_id=candidate_id,
            genome=genome,
            missing_reasons=missing_reasons,
            metadata=eval_obj.metadata,
        )

    return EvaluatedCandidate(
        candidate_id=candidate_id,
        genome=genome,
        objectives=finite_objectives,
        constraint_values=finite_constraint_vals,
        constraint_violations=constraint_violations,
        total_violation=total_violation,
        is_feasible=(total_violation == 0.0),
        metadata=eval_obj.metadata,
    )


def partition_candidates[GenomeT](
    candidates: Sequence[CandidateInput[GenomeT] | EvaluatedCandidate[GenomeT]],
    objectives: Sequence[ObjectiveSpec],
    constraints: Sequence[ConstraintSpec] = (),
) -> tuple[
    tuple[EvaluatedCandidate[GenomeT], ...],
    tuple[UnrankableCandidate[GenomeT], ...],
]:
    """Separate finite rankable candidates from missing/non-finite candidates."""
    obj_tuple, con_tuple = _validate_objectives_and_constraints(objectives, constraints)
    rankable: list[EvaluatedCandidate[GenomeT]] = []
    unrankable: list[UnrankableCandidate[GenomeT]] = []

    for cand in candidates:
        if isinstance(cand, EvaluatedCandidate):
            if not con_tuple:
                # Preserve pre-computed feasibility/violation when no new
                # ConstraintSpec list is supplied, while still verifying every
                # requested objective is present and finite.
                missing_obj = {
                    spec.name: Missing(
                        reason="MISSING_INPUT",
                        detail=f"objective '{spec.name}' missing from evaluation (C3.1)",
                    )
                    for spec in obj_tuple
                    if spec.name not in cand.objectives
                }
                if missing_obj:
                    outcome: (
                        EvaluatedCandidate[GenomeT] | UnrankableCandidate[GenomeT]
                    ) = UnrankableCandidate(
                        candidate_id=cand.candidate_id,
                        genome=cand.genome,
                        missing_reasons=missing_obj,
                        metadata=cand.metadata,
                    )
                else:
                    outcome = cand
            else:
                eval_obj = CandidateEvaluation(
                    objectives=cand.objectives,
                    constraint_values=cand.constraint_values,
                    metadata=cand.metadata,
                )
                outcome = _evaluate_candidate_record(
                    cand.candidate_id,
                    cand.genome,
                    eval_obj,
                    obj_tuple,
                    con_tuple,
                )
        elif isinstance(cand, CandidateInput):
            outcome = _evaluate_candidate_record(
                cand.candidate_id,
                cand.genome,
                cand.evaluation,
                obj_tuple,
                con_tuple,
            )
        else:
            raise TypeError(
                "candidates must be EvaluatedCandidate or CandidateInput, "
                f"got {type(cand).__name__}"
            )
        if isinstance(outcome, UnrankableCandidate):
            unrankable.append(outcome)
        else:
            rankable.append(outcome)

    return tuple(rankable), tuple(unrankable)


def _constrained_dominates_raw(
    min_obj_a: tuple[float, ...],
    violation_a: float,
    min_obj_b: tuple[float, ...],
    violation_b: float,
) -> bool:
    """Deb et al. (2002) constrained dominance in pre-minimized objective space."""
    feasible_a = violation_a == 0.0
    feasible_b = violation_b == 0.0
    if feasible_a and not feasible_b:
        return True
    if not feasible_a and feasible_b:
        return False
    if not feasible_a and not feasible_b:
        return violation_a < violation_b
    # Both feasible: strict Pareto dominance in minimization space.
    at_least_one_better = False
    for a_val, b_val in zip(min_obj_a, min_obj_b, strict=True):
        if a_val > b_val:
            return False
        if a_val < b_val:
            at_least_one_better = True
    return at_least_one_better


def constrained_dominates(
    candidate_a: EvaluatedCandidate[Any],
    candidate_b: EvaluatedCandidate[Any],
    objectives: Sequence[ObjectiveSpec],
) -> bool:
    """Return True iff ``candidate_a`` constrained-dominates ``candidate_b``."""
    obj_tuple, _ = _validate_objectives_and_constraints(objectives, ())
    min_a = tuple(
        spec.to_minimized(candidate_a.objectives[spec.name]) for spec in obj_tuple
    )
    min_b = tuple(
        spec.to_minimized(candidate_b.objectives[spec.name]) for spec in obj_tuple
    )
    return _constrained_dominates_raw(
        min_a,
        candidate_a.total_violation,
        min_b,
        candidate_b.total_violation,
    )


def fast_non_dominated_sort[GenomeT](
    candidates: Sequence[EvaluatedCandidate[GenomeT] | CandidateInput[GenomeT]],
    objectives: Sequence[ObjectiveSpec],
    constraints: Sequence[ConstraintSpec] = (),
    *,
    unrankable_out: list[UnrankableCandidate[GenomeT]] | None = None,
) -> tuple[tuple[EvaluatedCandidate[GenomeT], ...], ...]:
    """Deb et al. (2002) O(M*N^2) fast non-dominated sort with constrained dominance.

    Any candidate missing a required objective/constraint value (or carrying a
    non-finite value) is quarantined rather than given a synthetic ``0.0``, and
    appended to ``unrankable_out`` when supplied.

    Returns fronts ordered from rank 0 (non-dominated) upward, with deterministic
    ``candidate_id`` ordering inside each front.
    """
    rankable, unrankable = partition_candidates(candidates, objectives, constraints)
    if unrankable_out is not None:
        unrankable_out.extend(unrankable)

    n = len(rankable)
    if n == 0:
        return ()

    obj_tuple, _ = _validate_objectives_and_constraints(objectives, constraints)
    min_vectors = [
        tuple(spec.to_minimized(cand.objectives[spec.name]) for spec in obj_tuple)
        for cand in rankable
    ]
    violations = [cand.total_violation for cand in rankable]

    dominates_list: list[list[int]] = [[] for _ in range(n)]
    domination_count: list[int] = [0] * n

    for p in range(n):
        for q in range(p + 1, n):
            if _constrained_dominates_raw(
                min_vectors[p], violations[p], min_vectors[q], violations[q]
            ):
                dominates_list[p].append(q)
                domination_count[q] += 1
            elif _constrained_dominates_raw(
                min_vectors[q], violations[q], min_vectors[p], violations[p]
            ):
                dominates_list[q].append(p)
                domination_count[p] += 1

    fronts_indices: list[list[int]] = []
    current_front = [i for i in range(n) if domination_count[i] == 0]

    while current_front:
        fronts_indices.append(current_front)
        next_front: list[int] = []
        for p in current_front:
            for q in dominates_list[p]:
                domination_count[q] -= 1
                if domination_count[q] == 0:
                    next_front.append(q)
        current_front = next_front

    fronts: list[tuple[EvaluatedCandidate[GenomeT], ...]] = []
    for rank, idx_group in enumerate(fronts_indices):
        ordered = sorted(
            (replace(rankable[i], rank=rank) for i in idx_group),
            key=lambda c: c.candidate_id,
        )
        fronts.append(tuple(ordered))
    return tuple(fronts)


def crowding_distance_assignment[GenomeT](
    front: Sequence[EvaluatedCandidate[GenomeT]],
    objectives: Sequence[ObjectiveSpec],
) -> tuple[EvaluatedCandidate[GenomeT], ...]:
    """Assign Deb et al. (2002) crowding distances within a single Pareto front.

    Boundary solutions along any objective receive ``math.inf``. Interior
    solutions accumulate normalized neighbor gaps across all objectives using
    deterministic ``(objective_value, candidate_id)`` sorting on ties.
    Preserves the input order of ``front`` with updated ``crowding_distance``.
    """
    obj_tuple, _ = _validate_objectives_and_constraints(objectives, ())
    n = len(front)
    if n == 0:
        return ()
    if n <= 2:
        return tuple(replace(cand, crowding_distance=math.inf) for cand in front)

    distances = [0.0] * n
    for spec in obj_tuple:
        # Sort by minimized value with deterministic candidate_id tie-breaker.
        order = sorted(
            range(n),
            key=lambda idx: (
                spec.to_minimized(front[idx].objectives[spec.name]),
                front[idx].candidate_id,
            ),
        )
        distances[order[0]] = math.inf
        distances[order[-1]] = math.inf
        f_min = spec.to_minimized(front[order[0]].objectives[spec.name])
        f_max = spec.to_minimized(front[order[-1]].objectives[spec.name])
        span = f_max - f_min
        if span <= 0.0:
            continue
        for pos in range(1, n - 1):
            idx = order[pos]
            if math.isinf(distances[idx]):
                continue
            prev_val = spec.to_minimized(front[order[pos - 1]].objectives[spec.name])
            next_val = spec.to_minimized(front[order[pos + 1]].objectives[spec.name])
            distances[idx] += (next_val - prev_val) / span

    return tuple(replace(front[i], crowding_distance=distances[i]) for i in range(n))


def _crowded_comparison_key(
    candidate: EvaluatedCandidate[Any],
) -> tuple[int, float, str]:
    """Total deterministic order: lower rank, higher crowding distance, smaller ID."""
    return (candidate.rank, -candidate.crowding_distance, candidate.candidate_id)


def _crowded_tournament[GenomeT](
    population: Sequence[EvaluatedCandidate[GenomeT]],
    rng: random.Random,
) -> EvaluatedCandidate[GenomeT]:
    """Deterministic binary tournament using the crowded comparison operator."""
    if len(population) == 1:
        return population[0]
    i, j = rng.randrange(len(population)), rng.randrange(len(population))
    cand_a, cand_b = population[i], population[j]
    return (
        cand_a
        if _crowded_comparison_key(cand_a) <= _crowded_comparison_key(cand_b)
        else cand_b
    )


def _interpret_validator_result(raw: Any) -> Missing | None:
    """Translate validator return value into None (valid) or Missing (invalid)."""
    if raw is True:
        return None
    if raw is False:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="candidate rejected by validator hook",
        )
    if isinstance(raw, Missing):
        return raw
    if isinstance(raw, InputMissing):
        return Missing(reason=raw.reason, detail=raw.detail)
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], bool):
        is_valid, detail = raw
        if is_valid:
            return None
        detail_str = (
            detail
            if isinstance(detail, str) and detail.strip()
            else "candidate rejected by validator hook"
        )
        return Missing(reason="NOT_COMPUTABLE", detail=detail_str)
    raise TypeError(
        "validator must return bool, Missing, or (bool, str | None), "
        f"got {type(raw).__name__}"
    )


def sequence_one_point_crossover(
    parent_a: Sequence[Any],
    parent_b: Sequence[Any],
    rng: random.Random,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Single-point crossover for discrete crop/rotation sequence genomes."""
    seq_a = tuple(parent_a)
    seq_b = tuple(parent_b)
    min_len = min(len(seq_a), len(seq_b))
    if min_len <= 1:
        return seq_a, seq_b
    cut = rng.randint(1, min_len - 1)
    return seq_a[:cut] + seq_b[cut:], seq_b[:cut] + seq_a[cut:]


def sequence_point_mutation(
    genome: Sequence[Any],
    alphabet: Sequence[Any],
    rng: random.Random,
    *,
    mutation_rate: float | None = None,
) -> tuple[Any, ...]:
    """Per-position discrete substitution mutation over a crop/option alphabet."""
    options = tuple(alphabet)
    if not options:
        raise ValueError("alphabet must be non-empty")
    seq = list(genome)
    if not seq:
        return ()
    rate = (1.0 / len(seq)) if mutation_rate is None else float(mutation_rate)
    if not _is_finite_number(rate) or not (0.0 <= rate <= 1.0):
        raise ValueError("mutation_rate must be finite and in [0.0, 1.0]")
    for idx, current in enumerate(seq):
        if rng.random() < rate:
            alternatives = [item for item in options if item != current]
            if alternatives:
                seq[idx] = rng.choice(alternatives)
    return tuple(seq)


def vector_sbx_crossover(
    parent_a: Sequence[float | int],
    parent_b: Sequence[float | int],
    bounds: Sequence[VectorBound],
    rng: random.Random,
    *,
    eta_c: float = 15.0,
) -> tuple[tuple[float | int, ...], tuple[float | int, ...]]:
    """Deb et al. (2002) Simulated Binary Crossover (SBX) for bounded vectors."""
    if len(parent_a) != len(bounds) or len(parent_b) != len(bounds):
        raise ValueError("parent lengths must match bounds length")
    if not _is_finite_number(eta_c) or float(eta_c) < 0.0:
        raise ValueError("eta_c must be finite and >= 0")

    child_1: list[float | int] = []
    child_2: list[float | int] = []
    exponent = 1.0 / (float(eta_c) + 1.0)

    for val_a, val_b, bound in zip(parent_a, parent_b, bounds, strict=True):
        x1 = float(val_a)
        x2 = float(val_b)
        low = float(bound.low)
        high = float(bound.high)
        if low >= high or abs(x1 - x2) <= 1e-14 or rng.random() >= 0.5:
            c1, c2 = x1, x2
        else:
            y1, y2 = (x1, x2) if x1 < x2 else (x2, x1)
            span = y2 - y1
            u = rng.random()

            beta1 = 1.0 + (2.0 * (y1 - low) / span)
            alpha1 = 2.0 - beta1 ** (-(float(eta_c) + 1.0))
            if u <= 1.0 / alpha1:
                beta_q1 = (u * alpha1) ** exponent
            else:
                beta_q1 = (1.0 / max(1e-15, 2.0 - u * alpha1)) ** exponent
            c1 = 0.5 * ((y1 + y2) - beta_q1 * span)

            beta2 = 1.0 + (2.0 * (high - y2) / span)
            alpha2 = 2.0 - beta2 ** (-(float(eta_c) + 1.0))
            if u <= 1.0 / alpha2:
                beta_q2 = (u * alpha2) ** exponent
            else:
                beta_q2 = (1.0 / max(1e-15, 2.0 - u * alpha2)) ** exponent
            c2 = 0.5 * ((y1 + y2) + beta_q2 * span)

            c1 = min(high, max(low, c1))
            c2 = min(high, max(low, c2))
            if rng.random() < 0.5:
                c1, c2 = c2, c1

        if bound.is_integer:
            c1_out: float | int = min(int(high), max(int(low), round(c1)))
            c2_out: float | int = min(int(high), max(int(low), round(c2)))
        else:
            c1_out = min(high, max(low, c1))
            c2_out = min(high, max(low, c2))
        child_1.append(c1_out)
        child_2.append(c2_out)

    return tuple(child_1), tuple(child_2)


def vector_polynomial_mutation(
    genome: Sequence[float | int],
    bounds: Sequence[VectorBound],
    rng: random.Random,
    *,
    mutation_rate: float | None = None,
    eta_m: float = 20.0,
) -> tuple[float | int, ...]:
    """Deb et al. (2002) bounded polynomial mutation for continuous/integer vectors."""
    if len(genome) != len(bounds):
        raise ValueError("genome length must match bounds length")
    if not _is_finite_number(eta_m) or float(eta_m) < 0.0:
        raise ValueError("eta_m must be finite and >= 0")
    n_vars = len(genome)
    if n_vars == 0:
        return ()
    rate = (1.0 / n_vars) if mutation_rate is None else float(mutation_rate)
    if not _is_finite_number(rate) or not (0.0 <= rate <= 1.0):
        raise ValueError("mutation_rate must be finite and in [0.0, 1.0]")

    mut_pow = 1.0 / (float(eta_m) + 1.0)
    out: list[float | int] = []
    for raw_val, bound in zip(genome, bounds, strict=True):
        y = float(raw_val)
        low = float(bound.low)
        high = float(bound.high)
        if low < high and rng.random() < rate:
            span = high - low
            delta1 = (y - low) / span
            delta2 = (high - y) / span
            u = rng.random()
            if u < 0.5:
                xy = 1.0 - delta1
                val = 2.0 * u + (1.0 - 2.0 * u) * (xy ** (float(eta_m) + 1.0))
                delta_q = (val**mut_pow) - 1.0
            else:
                xy = 1.0 - delta2
                val = 2.0 * (1.0 - u) + 2.0 * (u - 0.5) * (xy ** (float(eta_m) + 1.0))
                delta_q = 1.0 - (val**mut_pow)
            y = min(high, max(low, y + delta_q * span))
        if bound.is_integer:
            out.append(min(int(high), max(int(low), round(y))))
        else:
            out.append(min(high, max(low, y)))
    return tuple(out)


def _rank_and_crowd_population[GenomeT](
    population: Sequence[EvaluatedCandidate[GenomeT]],
    objectives: Sequence[ObjectiveSpec],
    constraints: Sequence[ConstraintSpec],
) -> tuple[tuple[EvaluatedCandidate[GenomeT], ...], ...]:
    """Sort into non-dominated fronts, assign crowding distances, and order fronts."""
    raw_fronts = fast_non_dominated_sort(population, objectives, constraints)
    crowded_fronts: list[tuple[EvaluatedCandidate[GenomeT], ...]] = []
    for front in raw_fronts:
        crowded = crowding_distance_assignment(front, objectives)
        ordered = tuple(sorted(crowded, key=_crowded_comparison_key))
        crowded_fronts.append(ordered)
    return tuple(crowded_fronts)


def nsga2_search[GenomeT](
    *,
    objectives: Sequence[ObjectiveSpec],
    evaluator: Callable[
        [GenomeT], CandidateEvaluation | Mapping[str, float | int | Missing | None]
    ],
    initial_population: Sequence[GenomeT],
    crossover: Callable[[GenomeT, GenomeT, random.Random], tuple[GenomeT, GenomeT]],
    mutate: Callable[[GenomeT, random.Random], GenomeT],
    constraints: Sequence[ConstraintSpec] = (),
    validator: Callable[
        [GenomeT], bool | tuple[bool, str | None] | Missing | InputMissing
    ]
    | None = None,
    generations: int = 20,
    population_size: int | None = None,
    crossover_rate: float = 0.9,
    seed: int = 0,
    deduplicate_genomes: bool = False,
    max_repair_attempts: int = 8,
) -> NSGA2Result[GenomeT]:
    """Run deterministic seeded NSGA-II search over caller-defined genomes.

    Parameters
    ----------
    objectives:
        Non-empty sequence of ``ObjectiveSpec`` defining names and directions.
    evaluator:
        Pure caller-supplied evaluator returning ``CandidateEvaluation`` or a
        mapping of objective names to numeric / ``Missing`` / ``None`` values.
    initial_population:
        Non-empty sequence of initial candidate genomes.
    crossover, mutate:
        Deterministic variation operators receiving the local ``random.Random``.
    constraints:
        Optional ``ConstraintSpec`` sequence with tolerated max violations.
    validator:
        Optional pre-evaluation structural validator hook. Rejected genomes are
        quarantined in ``unrankable_missing`` and never passed to ``evaluator``.
    generations:
        Number of evolutionary generations (>= 0). ``0`` ranks the initial
        population without generating offspring.
    population_size:
        Target population size (defaults to ``len(initial_population)``).
    crossover_rate:
        Probability in ``[0.0, 1.0]`` of applying crossover to a parent pair.
    seed:
        Integer seed for a local ``random.Random(seed)`` instance.
    deduplicate_genomes:
        When True, hashable genomes already present in the combined pool or
        unrankable quarantine are not re-admitted as duplicates.
    max_repair_attempts:
        Maximum re-draws per offspring slot when ``validator`` rejects a child.
    """
    obj_tuple, con_tuple = _validate_objectives_and_constraints(objectives, constraints)
    if not initial_population:
        raise ValueError("initial_population must be non-empty")
    if generations < 0:
        raise ValueError("generations must be >= 0")
    target_pop_size = (
        len(initial_population) if population_size is None else int(population_size)
    )
    if target_pop_size < 1:
        raise ValueError("population_size must be >= 1")
    if not _is_finite_number(crossover_rate) or not (0.0 <= crossover_rate <= 1.0):
        raise ValueError("crossover_rate must be finite and in [0.0, 1.0]")
    if max_repair_attempts < 0:
        raise ValueError("max_repair_attempts must be >= 0")

    rng = random.Random(seed)
    eval_counter = 0
    cand_counter = 0
    unrankable: list[UnrankableCandidate[GenomeT]] = []
    seen_unrankable_genomes: set[Any] = set()

    def _genome_key(genome: GenomeT) -> tuple[bool, Any]:
        try:
            hash(genome)
            return True, genome
        except TypeError:
            return False, None

    def _record_unrankable(item: UnrankableCandidate[GenomeT]) -> None:
        if deduplicate_genomes:
            hashable, key = _genome_key(item.genome)
            if hashable:
                if key in seen_unrankable_genomes:
                    return
                seen_unrankable_genomes.add(key)
        unrankable.append(item)

    def _assess_genome(
        genome: GenomeT,
    ) -> EvaluatedCandidate[GenomeT] | UnrankableCandidate[GenomeT]:
        nonlocal cand_counter, eval_counter
        candidate_id = f"cand-{cand_counter:05d}"
        cand_counter += 1

        if validator is not None:
            v_missing = _interpret_validator_result(validator(genome))
            if v_missing is not None:
                return UnrankableCandidate(
                    candidate_id=candidate_id,
                    genome=genome,
                    missing_reasons={"validator": v_missing},
                )

        eval_counter += 1
        raw_eval = evaluator(genome)
        return _evaluate_candidate_record(
            candidate_id, genome, raw_eval, obj_tuple, con_tuple
        )

    valid_pool: list[EvaluatedCandidate[GenomeT]] = []
    seen_valid_genomes: set[Any] = set()

    for genome in initial_population:
        if deduplicate_genomes:
            hashable, key = _genome_key(genome)
            if hashable and key in seen_valid_genomes:
                continue
        assessed = _assess_genome(genome)
        if isinstance(assessed, UnrankableCandidate):
            _record_unrankable(assessed)
        else:
            if deduplicate_genomes:
                hashable, key = _genome_key(assessed.genome)
                if hashable:
                    seen_valid_genomes.add(key)
            valid_pool.append(assessed)

    if not valid_pool:
        return NSGA2Result(
            pareto_fronts=(),
            unrankable_missing=tuple(unrankable),
            objectives=obj_tuple,
            constraints=con_tuple,
            seed=seed,
            generations_completed=0,
            evaluations_count=eval_counter,
            feasible_count=0,
            infeasible_count=0,
        )

    fronts = _rank_and_crowd_population(valid_pool, obj_tuple, con_tuple)
    population: list[EvaluatedCandidate[GenomeT]] = []
    for front in fronts:
        if len(population) + len(front) <= target_pop_size:
            population.extend(front)
        else:
            needed = target_pop_size - len(population)
            population.extend(front[:needed])
            break

    generations_completed = 0
    for _gen in range(generations):
        offspring_valid: list[EvaluatedCandidate[GenomeT]] = []
        pool_seen_genomes: set[Any] = set()
        if deduplicate_genomes:
            for member in population:
                hashable, key = _genome_key(member.genome)
                if hashable:
                    pool_seen_genomes.add(key)

        offspring_target = target_pop_size
        produced_slots = 0
        while produced_slots < offspring_target:
            pair_children: list[GenomeT] = []
            for _attempt in range(max_repair_attempts + 1):
                parent_a = _crowded_tournament(population, rng)
                parent_b = _crowded_tournament(population, rng)
                if rng.random() < crossover_rate:
                    c1, c2 = crossover(parent_a.genome, parent_b.genome, rng)
                else:
                    c1, c2 = parent_a.genome, parent_b.genome
                m1 = mutate(c1, rng)
                m2 = mutate(c2, rng)
                if validator is None:
                    pair_children = [m1, m2]
                    break
                accepted: list[GenomeT] = []
                for child in (m1, m2):
                    v_res = _interpret_validator_result(validator(child))
                    if v_res is None:
                        accepted.append(child)
                if accepted:
                    pair_children = accepted
                    break
                if _attempt == max_repair_attempts:
                    # Exhausted repairs: quarantine the rejected children explicitly.
                    for child in (m1, m2):
                        v_res = _interpret_validator_result(validator(child))
                        if v_res is not None:
                            cid = f"cand-{cand_counter:05d}"
                            cand_counter += 1
                            _record_unrankable(
                                UnrankableCandidate(
                                    candidate_id=cid,
                                    genome=child,
                                    missing_reasons={"validator": v_res},
                                )
                            )
                    pair_children = []

            if not pair_children:
                produced_slots += 2
                continue

            for child_genome in pair_children:
                if produced_slots >= offspring_target:
                    break
                produced_slots += 1
                if deduplicate_genomes:
                    hashable, key = _genome_key(child_genome)
                    if hashable and key in pool_seen_genomes:
                        continue
                # Validator already verified above when validator is present.
                cid = f"cand-{cand_counter:05d}"
                cand_counter += 1
                eval_counter += 1
                raw_eval = evaluator(child_genome)
                assessed = _evaluate_candidate_record(
                    cid, child_genome, raw_eval, obj_tuple, con_tuple
                )
                if isinstance(assessed, UnrankableCandidate):
                    _record_unrankable(assessed)
                else:
                    if deduplicate_genomes:
                        hashable, key = _genome_key(assessed.genome)
                        if hashable:
                            pool_seen_genomes.add(key)
                    offspring_valid.append(assessed)

        combined = population + offspring_valid
        combined_fronts = _rank_and_crowd_population(combined, obj_tuple, con_tuple)
        next_population: list[EvaluatedCandidate[GenomeT]] = []
        for front in combined_fronts:
            if len(next_population) + len(front) <= target_pop_size:
                next_population.extend(front)
            else:
                needed = target_pop_size - len(next_population)
                next_population.extend(front[:needed])
                break
        population = next_population
        generations_completed += 1

    final_fronts = _rank_and_crowd_population(population, obj_tuple, con_tuple)
    feasible_count = sum(
        1 for front in final_fronts for cand in front if cand.is_feasible
    )
    infeasible_count = sum(
        1 for front in final_fronts for cand in front if not cand.is_feasible
    )

    return NSGA2Result(
        pareto_fronts=final_fronts,
        unrankable_missing=tuple(unrankable),
        objectives=obj_tuple,
        constraints=con_tuple,
        seed=seed,
        generations_completed=generations_completed,
        evaluations_count=eval_counter,
        feasible_count=feasible_count,
        infeasible_count=infeasible_count,
    )
