"""Frontier decision methods: Scenario Discovery (PRIM) and Dynamic Adaptive Policy Pathways (DAPP).

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13). This module is
standalone and is not wired into ``decision/output.py`` or any API route;
nothing here takes effect until people approve it.

Two pure-Python decision methods for deep uncertainty:

1. **Scenario Discovery (PRIM-style axis-aligned peeling, Bryant & Lempert
   2010):** ``discover_vulnerability_boxes`` iteratively peels top and bottom
   quantiles along single uncertain-factor dimensions to isolate compact,
   human-readable box rules (``VulnerableBoxRule``) that concentrate vulnerable
   outcomes while tracking ``coverage`` and ``density`` along the peeling
   trajectory. Scenarios carrying any ``Missing`` factor or ``Missing`` outcome
   are quarantined into ``unmodeled_scenarios`` and are never filled with zero
   or a default (C3.1, C3.3).

2. **Dynamic Adaptive Policy Pathways (DAPP, Haasnoot et al. 2013):**
   ``evaluate_adaptive_pathway`` evaluates an ``AdaptivePathway`` against an
   observed signpost time series, checking ``SignpostTrigger`` tipping-point
   exceedance, selecting the shortest valid transfer ``PathwayStep`` that
   satisfies the implementation ``lead_time`` check within the remaining
   horizon, and emitting typed ``Missing(reason="MISSING_INPUT")`` whenever a
   required signpost observation is missing (C3.1, C3.3).

Pure Python 3.12 standard library plus ``contracts.*``; zero numpy. Pure
functions (G1): no file access, no network call, no clock, no environment
variable, no global mutable state, and arguments are never modified. Holds no
hardcoded domain thresholds or parameter values (Blueprint §3.5).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from contracts.inputs.common import Missing as InputsMissing
from contracts.results.models import Missing

__all__ = [
    "AdaptivePathway",
    "PathwayEvaluation",
    "PathwayStep",
    "PathwayTransition",
    "PeelingStep",
    "RejectedTransfer",
    "ScenarioDiscoveryResult",
    "SignpostTrigger",
    "TippingEvent",
    "TriggerDirection",
    "UnmodeledScenario",
    "VulnerableBoxRule",
    "discover_vulnerability_boxes",
    "evaluate_adaptive_pathway",
]

TriggerDirection = Literal["above", "below", "at_or_above", "at_or_below"]
PathwayStatus = Literal[
    "NO_TRIGGER", "TRANSFERRED", "NO_VALID_TRANSFER", "MISSING_INPUT"
]
RejectionReason = Literal["lead_time_exceeded", "target_already_exceeded"]


def _is_missing(value: object) -> bool:
    return isinstance(value, (Missing, InputsMissing))


def _coerce_missing(value: Missing | InputsMissing) -> Missing:
    if isinstance(value, Missing):
        return value
    return Missing(reason=value.reason, detail=value.detail)


def _require_non_blank(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-blank string")
    return value


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{field_name} must be a finite real number, got {type(value).__name__}"
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    return numeric


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# 1. Scenario Discovery (PRIM-style axis-aligned peeling)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnmodeledScenario:
    """A scenario quarantined because one or more required inputs or its outcome
    is ``Missing`` (C3.1, C3.3). Never filled with zero."""

    scenario_id: str
    missing_factors: tuple[str, ...]
    reasons: Mapping[str, Missing]

    def __post_init__(self) -> None:
        _require_non_blank(self.scenario_id, "scenario_id")
        object.__setattr__(self, "missing_factors", tuple(self.missing_factors))
        object.__setattr__(
            self,
            "reasons",
            MappingProxyType({k: _coerce_missing(v) for k, v in self.reasons.items()}),
        )


@dataclass(frozen=True)
class PeelingStep:
    """One step on the PRIM peeling trajectory tracking ``coverage`` and
    ``density`` alongside restricted ``bounds``."""

    step: int
    bounds: Mapping[str, tuple[float, float]]
    support: float
    coverage: float
    density: float
    matched_count: int
    vulnerable_count: int
    peeled_factor: str | None = None
    peeled_side: Literal["low", "high"] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bounds", MappingProxyType(dict(self.bounds)))


@dataclass(frozen=True)
class VulnerableBoxRule:
    """An axis-aligned box rule describing when an option fails.

    ``bounds`` maps each restricted factor name to ``(low, high)`` inclusive.
    ``coverage`` is the fraction of all modeled vulnerable scenarios captured
    by this box; ``density`` is the fraction of matched scenarios that are
    vulnerable; ``matched_ids`` lists the modeled scenario identifiers inside
    the box.
    """

    bounds: Mapping[str, tuple[float, float]]
    coverage: float
    density: float
    matched_ids: tuple[str, ...]
    support: float = 0.0
    description: str = ""
    trajectory: tuple[PeelingStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bounds", MappingProxyType(dict(self.bounds)))
        object.__setattr__(self, "matched_ids", tuple(self.matched_ids))
        object.__setattr__(self, "trajectory", tuple(self.trajectory))


@dataclass(frozen=True)
class ScenarioDiscoveryResult:
    """Result of PRIM-style scenario discovery with quarantined scenarios."""

    boxes: tuple[VulnerableBoxRule, ...]
    unmodeled_scenarios: tuple[UnmodeledScenario, ...]
    total_scenarios: int
    modeled_scenarios: int
    vulnerable_scenarios: int
    total_coverage: float
    trajectory: tuple[PeelingStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "boxes", tuple(self.boxes))
        object.__setattr__(self, "unmodeled_scenarios", tuple(self.unmodeled_scenarios))
        object.__setattr__(self, "trajectory", tuple(self.trajectory))

    @property
    def unmodeled_ids(self) -> tuple[str, ...]:
        """Identifiers of scenarios quarantined with missing values."""
        return tuple(item.scenario_id for item in self.unmodeled_scenarios)


def _format_box_description(
    bounds: Mapping[str, tuple[float, float]],
    start_min: Mapping[str, float],
    start_max: Mapping[str, float],
) -> str:
    if not bounds:
        return "all modeled scenarios (unconstrained)"
    clauses: list[str] = []
    for factor in sorted(bounds):
        low, high = bounds[factor]
        trimmed_low = low > start_min[factor]
        trimmed_high = high < start_max[factor]
        if trimmed_low and trimmed_high:
            clauses.append(f"{low:g} <= {factor} <= {high:g}")
        elif trimmed_low:
            clauses.append(f"{factor} >= {low:g}")
        elif trimmed_high:
            clauses.append(f"{factor} <= {high:g}")
        else:
            clauses.append(f"{low:g} <= {factor} <= {high:g}")
    return " and ".join(clauses)


def _extract_box_bounds(
    ids: Sequence[str],
    data: Mapping[str, Mapping[str, float]],
    peeled_factors: set[str],
) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    for factor in sorted(peeled_factors):
        vals = [data[sid][factor] for sid in ids]
        bounds[factor] = (min(vals), max(vals))
    return bounds


def _peel_single_box(
    remaining_ids: Sequence[str],
    data: Mapping[str, Mapping[str, float]],
    outcomes_bool: Mapping[str, bool],
    factors: Sequence[str],
    *,
    alpha: float,
    min_support_fraction: float,
    total_modeled: int,
    total_vulnerable: int,
) -> tuple[VulnerableBoxRule | None, tuple[PeelingStep, ...]]:
    start_min = {
        factor: min(data[sid][factor] for sid in remaining_ids) for factor in factors
    }
    start_max = {
        factor: max(data[sid][factor] for sid in remaining_ids) for factor in factors
    }
    current_ids = list(remaining_ids)
    init_vuln = sum(1 for sid in current_ids if outcomes_bool[sid])
    init_density = init_vuln / len(current_ids)
    trajectory: list[PeelingStep] = [
        PeelingStep(
            step=0,
            bounds={},
            support=len(current_ids) / total_modeled,
            coverage=init_vuln / total_vulnerable,
            density=init_density,
            matched_count=len(current_ids),
            vulnerable_count=init_vuln,
        )
    ]

    min_support_count = max(1, math.ceil(min_support_fraction * total_modeled - 1e-12))
    peeled_factors: set[str] = set()
    step_index = 0
    while len(current_ids) > 1:
        current_vuln = sum(1 for sid in current_ids if outcomes_bool[sid])
        if current_vuln == 0 or current_vuln == len(current_ids):
            break
        m = len(current_ids)
        peel_count = min(m - 1, max(1, math.floor(alpha * m)))
        best_candidate: (
            tuple[
                tuple[float, int, int, int, int],
                list[str],
                str,
                Literal["low", "high"],
            ]
            | None
        ) = None

        for dim_rank, factor in enumerate(factors):
            vals = sorted(data[sid][factor] for sid in current_ids)
            min_v, max_v = vals[0], vals[-1]
            if min_v == max_v:
                continue

            # Bottom peel: raise lower bound to exclude bottom quantile without splitting ties.
            cand_low = vals[peel_count]
            if cand_low == min_v:
                cand_low = next(v for v in vals if v > min_v)
            kept_low = [sid for sid in current_ids if data[sid][factor] >= cand_low]
            if kept_low and len(kept_low) < m and len(kept_low) >= min_support_count:
                vuln_low = sum(1 for sid in kept_low if outcomes_bool[sid])
                density_low = vuln_low / len(kept_low)
                score_low = (
                    density_low,
                    vuln_low,
                    len(kept_low),
                    -dim_rank,
                    0,
                )
                if best_candidate is None or score_low > best_candidate[0]:
                    best_candidate = (score_low, kept_low, factor, "low")

            # Top peel: lower upper bound to exclude top quantile without splitting ties.
            idx_high = m - 1 - peel_count
            cand_high = vals[idx_high]
            if cand_high == max_v:
                cand_high = next(v for v in reversed(vals) if v < max_v)
            kept_high = [sid for sid in current_ids if data[sid][factor] <= cand_high]
            if kept_high and len(kept_high) < m and len(kept_high) >= min_support_count:
                vuln_high = sum(1 for sid in kept_high if outcomes_bool[sid])
                density_high = vuln_high / len(kept_high)
                score_high = (
                    density_high,
                    vuln_high,
                    len(kept_high),
                    -dim_rank,
                    -1,
                )
                if best_candidate is None or score_high > best_candidate[0]:
                    best_candidate = (score_high, kept_high, factor, "high")

        if best_candidate is None:
            break

        _, next_ids, peeled_factor, peeled_side = best_candidate
        step_index += 1
        current_ids = next_ids
        peeled_factors.add(peeled_factor)
        vuln_next = sum(1 for sid in current_ids if outcomes_bool[sid])
        step_bounds = _extract_box_bounds(current_ids, data, peeled_factors)
        trajectory.append(
            PeelingStep(
                step=step_index,
                bounds=step_bounds,
                support=len(current_ids) / total_modeled,
                coverage=vuln_next / total_vulnerable,
                density=vuln_next / len(current_ids),
                matched_count=len(current_ids),
                vulnerable_count=vuln_next,
                peeled_factor=peeled_factor,
                peeled_side=peeled_side,
            )
        )

    best_step = max(
        trajectory,
        key=lambda item: (
            item.density,
            item.vulnerable_count,
            item.matched_count,
            -item.step,
        ),
    )
    if best_step.vulnerable_count == 0:
        return None, tuple(trajectory)
    if best_step.matched_count < min_support_count:
        return None, tuple(trajectory)
    if best_step.density <= init_density < 1.0:
        return None, tuple(trajectory)

    # Reconstruct exact matched_ids for the chosen trajectory step.
    matched_ids = tuple(
        sid
        for sid in remaining_ids
        if all(
            low <= data[sid][factor] <= high
            for factor, (low, high) in best_step.bounds.items()
        )
    )
    description = _format_box_description(best_step.bounds, start_min, start_max)
    rule = VulnerableBoxRule(
        bounds=best_step.bounds,
        coverage=best_step.coverage,
        density=best_step.density,
        matched_ids=matched_ids,
        support=best_step.support,
        description=description,
        trajectory=tuple(trajectory),
    )
    return rule, tuple(trajectory)


def discover_vulnerability_boxes(
    scenarios: Mapping[str, Mapping[str, float | int | Missing | InputsMissing]],
    outcomes: Mapping[str, bool | Missing | InputsMissing],
    *,
    alpha: float,
    min_support_fraction: float,
) -> ScenarioDiscoveryResult:
    """Discover axis-aligned vulnerability boxes via PRIM-style peeling.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13); Bryant & Lempert (2010).

    Args:
        scenarios: Mapping ``scenario_id -> {factor_name -> finite float | Missing}``.
        outcomes: Mapping ``scenario_id -> bool | Missing`` (``True`` means the
            option fails / is vulnerable).
        alpha: Peeling quantile fraction per step in ``(0, 1)``.
        min_support_fraction: Minimum fraction of modeled scenarios a box must
            contain in ``(0, 1]``.

    Returns:
        ``ScenarioDiscoveryResult`` with discovered ``VulnerableBoxRule`` items,
        quarantined ``unmodeled_scenarios`` (never filled with zero), and the
        peeling ``trajectory``.
    """
    alpha_val = _require_finite_number(alpha, "alpha")
    if not (0.0 < alpha_val < 1.0):
        raise ValueError(f"alpha must lie strictly in (0, 1), got {alpha!r}")
    support_val = _require_finite_number(min_support_fraction, "min_support_fraction")
    if not (0.0 < support_val <= 1.0):
        raise ValueError(
            f"min_support_fraction must lie in (0, 1], got {min_support_fraction!r}"
        )

    if set(scenarios.keys()) != set(outcomes.keys()):
        raise ValueError(
            "scenarios and outcomes must share the exact same scenario_id keys"
        )

    all_factors_set: set[str] = set()
    for sid, factor_map in scenarios.items():
        _require_non_blank(sid, "scenario_id")
        if not isinstance(factor_map, Mapping):
            raise TypeError(f"scenario '{sid}' must map factor names to values")
        for factor_name in factor_map:
            _require_non_blank(factor_name, "factor_name")
            all_factors_set.add(factor_name)
    factors = tuple(sorted(all_factors_set))

    unmodeled: list[UnmodeledScenario] = []
    modeled_data: dict[str, dict[str, float]] = {}
    modeled_outcomes: dict[str, bool] = {}

    for sid, factor_map in scenarios.items():
        missing_reasons: dict[str, Missing] = {}
        clean_factors: dict[str, float] = {}

        for factor in factors:
            if factor not in factor_map:
                missing_reasons[factor] = Missing(
                    reason="MISSING_INPUT",
                    detail=f"factor '{factor}' is absent in scenario '{sid}'",
                )
                continue
            raw_val = factor_map[factor]
            if _is_missing(raw_val):
                missing_reasons[factor] = _coerce_missing(raw_val)
            else:
                clean_factors[factor] = _require_finite_number(
                    raw_val, f"scenarios[{sid!r}][{factor!r}]"
                )

        raw_outcome = outcomes[sid]
        if _is_missing(raw_outcome):
            missing_reasons["outcome"] = _coerce_missing(raw_outcome)
        elif not isinstance(raw_outcome, bool):
            raise ValueError(
                f"outcomes[{sid!r}] must be bool or Missing, "
                f"got {type(raw_outcome).__name__}"
            )

        if missing_reasons:
            unmodeled.append(
                UnmodeledScenario(
                    scenario_id=sid,
                    missing_factors=tuple(missing_reasons.keys()),
                    reasons=missing_reasons,
                )
            )
        else:
            modeled_data[sid] = clean_factors
            modeled_outcomes[sid] = raw_outcome  # type: ignore[assignment]

    total_scenarios = len(scenarios)
    modeled_ids = list(modeled_data.keys())
    total_modeled = len(modeled_ids)
    total_vulnerable = sum(1 for sid in modeled_ids if modeled_outcomes[sid])

    if total_modeled == 0 or total_vulnerable == 0:
        return ScenarioDiscoveryResult(
            boxes=(),
            unmodeled_scenarios=tuple(unmodeled),
            total_scenarios=total_scenarios,
            modeled_scenarios=total_modeled,
            vulnerable_scenarios=total_vulnerable,
            total_coverage=0.0,
            trajectory=(),
        )

    if not factors:
        if total_vulnerable == total_modeled:
            step0 = PeelingStep(
                step=0,
                bounds={},
                support=1.0,
                coverage=1.0,
                density=1.0,
                matched_count=total_modeled,
                vulnerable_count=total_vulnerable,
            )
            rule = VulnerableBoxRule(
                bounds={},
                coverage=1.0,
                density=1.0,
                matched_ids=tuple(modeled_ids),
                support=1.0,
                description="all modeled scenarios (unconstrained)",
                trajectory=(step0,),
            )
            return ScenarioDiscoveryResult(
                boxes=(rule,),
                unmodeled_scenarios=tuple(unmodeled),
                total_scenarios=total_scenarios,
                modeled_scenarios=total_modeled,
                vulnerable_scenarios=total_vulnerable,
                total_coverage=1.0,
                trajectory=(step0,),
            )
        return ScenarioDiscoveryResult(
            boxes=(),
            unmodeled_scenarios=tuple(unmodeled),
            total_scenarios=total_scenarios,
            modeled_scenarios=total_modeled,
            vulnerable_scenarios=total_vulnerable,
            total_coverage=0.0,
            trajectory=(),
        )

    min_support_count = max(1, math.ceil(support_val * total_modeled - 1e-12))
    boxes: list[VulnerableBoxRule] = []
    remaining_ids = list(modeled_ids)
    primary_trajectory: tuple[PeelingStep, ...] = ()

    while remaining_ids:
        if len(remaining_ids) < min_support_count:
            break
        remaining_vuln = sum(1 for sid in remaining_ids if modeled_outcomes[sid])
        if remaining_vuln == 0:
            break
        rule, traj = _peel_single_box(
            remaining_ids,
            modeled_data,
            modeled_outcomes,
            factors,
            alpha=alpha_val,
            min_support_fraction=support_val,
            total_modeled=total_modeled,
            total_vulnerable=total_vulnerable,
        )
        if not primary_trajectory:
            primary_trajectory = traj
        if rule is None:
            break
        boxes.append(rule)
        matched_set = set(rule.matched_ids)
        remaining_ids = [sid for sid in remaining_ids if sid not in matched_set]

    covered_vulnerable = {
        sid for box in boxes for sid in box.matched_ids if modeled_outcomes[sid]
    }
    total_coverage = len(covered_vulnerable) / total_vulnerable

    return ScenarioDiscoveryResult(
        boxes=tuple(boxes),
        unmodeled_scenarios=tuple(unmodeled),
        total_scenarios=total_scenarios,
        modeled_scenarios=total_modeled,
        vulnerable_scenarios=total_vulnerable,
        total_coverage=total_coverage,
        trajectory=primary_trajectory,
    )


# ---------------------------------------------------------------------------
# 2. Dynamic Adaptive Policy Pathways (DAPP)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignpostTrigger:
    """An observable signpost threshold defining an adaptation tipping point.

    ``threshold`` is supplied by the caller (Blueprint §3.5).
    """

    signpost_id: str
    threshold: float
    direction: TriggerDirection = "at_or_above"
    unit: str | None = None
    consecutive_periods: int = 1

    def __post_init__(self) -> None:
        _require_non_blank(self.signpost_id, "signpost_id")
        object.__setattr__(
            self,
            "threshold",
            _require_finite_number(self.threshold, "threshold"),
        )
        if self.direction not in ("above", "below", "at_or_above", "at_or_below"):
            raise ValueError(
                f"invalid trigger direction {self.direction!r}; expected one of "
                "'above', 'below', 'at_or_above', 'at_or_below'"
            )
        if self.unit is not None:
            _require_non_blank(self.unit, "unit")
        periods = _require_int(self.consecutive_periods, "consecutive_periods")
        if periods < 1:
            raise ValueError(
                f"consecutive_periods must be >= 1, got {self.consecutive_periods!r}"
            )

    def is_exceeded(self, observed: float) -> bool:
        """Return whether ``observed`` crosses this trigger's tipping point."""
        val = _require_finite_number(observed, "observed")
        if self.direction == "above":
            return val > self.threshold
        if self.direction == "below":
            return val < self.threshold
        if self.direction == "at_or_above":
            return val >= self.threshold
        return val <= self.threshold


@dataclass(frozen=True)
class PathwayStep:
    """One policy/management action node in an ``AdaptivePathway``."""

    step_id: str
    action: str
    trigger: SignpostTrigger | None = None
    lead_time: int = 0
    transfer_to: tuple[str, ...] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.step_id, "step_id")
        _require_non_blank(self.action, "action")
        lead = _require_int(self.lead_time, "lead_time")
        if lead < 0:
            raise ValueError(f"lead_time must be >= 0, got {self.lead_time!r}")
        transfers = tuple(self.transfer_to)
        for target in transfers:
            _require_non_blank(target, "transfer_to item")
        object.__setattr__(self, "transfer_to", transfers)


@dataclass(frozen=True)
class AdaptivePathway:
    """A Dynamic Adaptive Policy Pathway plan (Haasnoot et al. 2013)."""

    pathway_id: str
    initial_step_id: str
    steps: tuple[PathwayStep, ...]
    horizon_end: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.pathway_id, "pathway_id")
        _require_non_blank(self.initial_step_id, "initial_step_id")
        steps_tuple = tuple(self.steps)
        if not steps_tuple:
            raise ValueError("AdaptivePathway.steps must not be empty")
        by_id: dict[str, PathwayStep] = {}
        for step in steps_tuple:
            if step.step_id in by_id:
                raise ValueError(f"duplicate step_id {step.step_id!r}")
            by_id[step.step_id] = step
        if self.initial_step_id not in by_id:
            raise ValueError(
                f"initial_step_id {self.initial_step_id!r} is not in steps"
            )
        for step in steps_tuple:
            for target_id in step.transfer_to:
                if target_id == step.step_id:
                    raise ValueError(
                        f"step {step.step_id!r} cannot list itself in transfer_to"
                    )
                if target_id not in by_id:
                    raise ValueError(
                        f"step {step.step_id!r} references unknown transfer target "
                        f"{target_id!r}"
                    )
        if self.horizon_end is not None:
            _require_int(self.horizon_end, "horizon_end")
        object.__setattr__(self, "steps", steps_tuple)

    def step_map(self) -> dict[str, PathwayStep]:
        """Return a lookup mapping ``step_id -> PathwayStep``."""
        return {step.step_id: step for step in self.steps}


@dataclass(frozen=True)
class TippingEvent:
    """Record of an observed tipping-point exceedance on an active step."""

    time: int
    step_id: str
    signpost_id: str
    observed_value: float
    threshold: float
    direction: TriggerDirection


@dataclass(frozen=True)
class RejectedTransfer:
    """A candidate transfer action rejected during pathway evaluation."""

    time: int
    from_step_id: str
    to_step_id: str
    reason: RejectionReason
    detail: str


@dataclass(frozen=True)
class PathwayTransition:
    """A selected transfer action triggered by a tipping-point exceedance."""

    time: int
    from_step_id: str
    to_step_id: str
    signpost_id: str
    observed_value: float
    threshold: float
    lead_time: int
    effective_time: int


@dataclass(frozen=True)
class PathwayEvaluation:
    """Result of evaluating an ``AdaptivePathway`` over observed signposts."""

    pathway_id: str
    status: PathwayStatus
    active_step_id: str | None
    transitions: tuple[PathwayTransition, ...]
    tipping_events: tuple[TippingEvent, ...]
    rejected_transfers: tuple[RejectedTransfer, ...]
    missing: Missing | None = None
    evaluated_times: tuple[int, ...] = ()


SignpostObservation = float | int | Missing | InputsMissing
ObservedSignpostSeries = (
    Mapping[int, Mapping[str, SignpostObservation]]
    | Mapping[str, Mapping[int, SignpostObservation]]
    | Mapping[str, Sequence[tuple[int, SignpostObservation]]]
    | Sequence[tuple[int, Mapping[str, SignpostObservation]]]
)


def _validate_observation_value(
    value: object, signpost_id: str, time: int
) -> float | Missing:
    if _is_missing(value):
        return _coerce_missing(value)  # type: ignore[arg-type]
    return _require_finite_number(
        value, f"observed_signpost_series[{time}][{signpost_id!r}]"
    )


def _normalize_signpost_series(
    series: ObservedSignpostSeries,
) -> dict[int, dict[str, float | Missing]]:
    if isinstance(series, (str, bytes)):
        raise TypeError("observed_signpost_series must not be a string or bytes")
    normalized: dict[int, dict[str, float | Missing]] = {}

    if isinstance(series, Mapping):
        if not series:
            return {}
        keys = list(series.keys())
        all_int = all(isinstance(k, int) and not isinstance(k, bool) for k in keys)
        all_str = all(isinstance(k, str) for k in keys)
        if all_int:
            for time_key, obs_map in series.items():
                t = _require_int(time_key, "time")
                if not isinstance(obs_map, Mapping):
                    raise TypeError(f"observations at time {t} must be a mapping")
                bucket = normalized.setdefault(t, {})
                for sid, raw_val in obs_map.items():
                    _require_non_blank(sid, "signpost_id")
                    bucket[sid] = _validate_observation_value(raw_val, sid, t)
            return normalized
        if all_str:
            for sid, time_entries in series.items():
                _require_non_blank(sid, "signpost_id")
                if isinstance(time_entries, Mapping):
                    items = time_entries.items()
                elif isinstance(time_entries, Sequence) and not isinstance(
                    time_entries, (str, bytes)
                ):
                    items = time_entries
                else:
                    raise TypeError(
                        f"signpost '{sid}' series must be a mapping or sequence of (time, value)"
                    )
                for entry in items:
                    if not isinstance(entry, tuple) or len(entry) != 2:
                        raise ValueError(
                            f"signpost '{sid}' entry must be a (time, value) pair"
                        )
                    t_raw, raw_val = entry
                    t = _require_int(t_raw, "time")
                    bucket = normalized.setdefault(t, {})
                    bucket[sid] = _validate_observation_value(raw_val, sid, t)
            return normalized
        raise ValueError(
            "observed_signpost_series mapping keys must be all int (times) or all str (signposts)"
        )

    if isinstance(series, Sequence):
        for entry in series:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ValueError(
                    "sequence entries in observed_signpost_series must be (time, mapping)"
                )
            t_raw, obs_map = entry
            t = _require_int(t_raw, "time")
            if not isinstance(obs_map, Mapping):
                raise TypeError(f"observations at time {t} must be a mapping")
            bucket = normalized.setdefault(t, {})
            for sid, raw_val in obs_map.items():
                _require_non_blank(sid, "signpost_id")
                bucket[sid] = _validate_observation_value(raw_val, sid, t)
        return normalized

    raise TypeError(
        "observed_signpost_series must be a mapping or sequence of (time, mapping)"
    )


def _missing_input_detail(
    signpost_id: str, time: int, source_missing: Missing | None = None
) -> Missing:
    if source_missing is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=(f"required signpost '{signpost_id}' is missing at time {time}"),
        )
    detail_suffix = f": {source_missing.detail}" if source_missing.detail else ""
    return Missing(
        reason="MISSING_INPUT",
        detail=(
            f"required signpost '{signpost_id}' is missing at time {time} "
            f"(source reason {source_missing.reason}{detail_suffix})"
        ),
    )


def _read_signpost_at(
    timeline: Mapping[int, Mapping[str, float | Missing]],
    time: int,
    signpost_id: str,
) -> tuple[float | None, Missing | None]:
    obs_at_t = timeline.get(time)
    if obs_at_t is None or signpost_id not in obs_at_t:
        return None, _missing_input_detail(signpost_id, time)
    raw = obs_at_t[signpost_id]
    if isinstance(raw, Missing):
        return None, _missing_input_detail(signpost_id, time, raw)
    return raw, None


def evaluate_adaptive_pathway(
    plan: AdaptivePathway,
    observed_signpost_series: ObservedSignpostSeries,
) -> PathwayEvaluation:
    """Evaluate a Dynamic Adaptive Policy Pathway against observed signposts.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13); Haasnoot et al. (2013).

    Checks tipping-point exceedance along the active ``PathwayStep``'s
    ``SignpostTrigger``, selects the shortest valid transfer action (minimum
    ``lead_time``) that satisfies the lead time check within the remaining
    horizon and is not already past its own tipping point, and emits typed
    ``Missing(reason="MISSING_INPUT")`` whenever a required signpost
    observation is absent or ``Missing``.
    """
    if not isinstance(plan, AdaptivePathway):
        raise TypeError("plan must be an AdaptivePathway instance")
    timeline = _normalize_signpost_series(observed_signpost_series)
    steps_by_id = plan.step_map()
    times = sorted(timeline.keys())
    current_step = steps_by_id[plan.initial_step_id]

    transitions: list[PathwayTransition] = []
    tipping_events: list[TippingEvent] = []
    rejected_transfers: list[RejectedTransfer] = []
    evaluated_times: list[int] = []

    if not times:
        if current_step.trigger is not None:
            return PathwayEvaluation(
                pathway_id=plan.pathway_id,
                status="MISSING_INPUT",
                active_step_id=None,
                transitions=(),
                tipping_events=(),
                rejected_transfers=(),
                missing=Missing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"required signpost '{current_step.trigger.signpost_id}' "
                        "has no observations in observed_signpost_series"
                    ),
                ),
                evaluated_times=(),
            )
        return PathwayEvaluation(
            pathway_id=plan.pathway_id,
            status="NO_TRIGGER",
            active_step_id=current_step.step_id,
            transitions=(),
            tipping_events=(),
            rejected_transfers=(),
            missing=None,
            evaluated_times=(),
        )

    last_observed_time = times[-1]
    horizon_end = (
        plan.horizon_end if plan.horizon_end is not None else last_observed_time
    )

    idx = 0
    consecutive = 0
    while idx < len(times):
        t = times[idx]
        evaluated_times.append(t)
        trigger = current_step.trigger
        if trigger is None:
            idx += 1
            continue

        obs_val, obs_missing = _read_signpost_at(timeline, t, trigger.signpost_id)
        if obs_missing is not None or obs_val is None:
            return PathwayEvaluation(
                pathway_id=plan.pathway_id,
                status="MISSING_INPUT",
                active_step_id=None,
                transitions=tuple(transitions),
                tipping_events=tuple(tipping_events),
                rejected_transfers=tuple(rejected_transfers),
                missing=obs_missing,
                evaluated_times=tuple(evaluated_times),
            )

        if not trigger.is_exceeded(obs_val):
            consecutive = 0
            idx += 1
            continue

        consecutive += 1
        if consecutive < trigger.consecutive_periods:
            idx += 1
            continue

        # Tipping point exceeded at time t.
        tipping_events.append(
            TippingEvent(
                time=t,
                step_id=current_step.step_id,
                signpost_id=trigger.signpost_id,
                observed_value=obs_val,
                threshold=trigger.threshold,
                direction=trigger.direction,
            )
        )
        available_time = horizon_end - t
        valid_candidates: list[tuple[int, int, PathwayStep]] = []

        for order, target_id in enumerate(current_step.transfer_to):
            candidate = steps_by_id[target_id]
            if candidate.lead_time > available_time:
                rejected_transfers.append(
                    RejectedTransfer(
                        time=t,
                        from_step_id=current_step.step_id,
                        to_step_id=candidate.step_id,
                        reason="lead_time_exceeded",
                        detail=(
                            f"transfer to '{candidate.step_id}' requires lead_time="
                            f"{candidate.lead_time}, exceeding remaining window "
                            f"{available_time} at time {t}"
                        ),
                    )
                )
                continue

            effective_time = t + candidate.lead_time
            if candidate.trigger is not None:
                check_time = effective_time if effective_time in timeline else t
                cand_val, cand_missing = _read_signpost_at(
                    timeline, check_time, candidate.trigger.signpost_id
                )
                if cand_missing is not None or cand_val is None:
                    return PathwayEvaluation(
                        pathway_id=plan.pathway_id,
                        status="MISSING_INPUT",
                        active_step_id=None,
                        transitions=tuple(transitions),
                        tipping_events=tuple(tipping_events),
                        rejected_transfers=tuple(rejected_transfers),
                        missing=cand_missing,
                        evaluated_times=tuple(evaluated_times),
                    )
                if candidate.trigger.is_exceeded(cand_val):
                    rejected_transfers.append(
                        RejectedTransfer(
                            time=t,
                            from_step_id=current_step.step_id,
                            to_step_id=candidate.step_id,
                            reason="target_already_exceeded",
                            detail=(
                                f"transfer target '{candidate.step_id}' already "
                                f"exceeds trigger '{candidate.trigger.signpost_id}' "
                                f"at time {check_time} ({cand_val} vs "
                                f"{candidate.trigger.threshold})"
                            ),
                        )
                    )
                    continue

            valid_candidates.append((candidate.lead_time, order, candidate))

        if not valid_candidates:
            return PathwayEvaluation(
                pathway_id=plan.pathway_id,
                status="NO_VALID_TRANSFER",
                active_step_id=None,
                transitions=tuple(transitions),
                tipping_events=tuple(tipping_events),
                rejected_transfers=tuple(rejected_transfers),
                missing=None,
                evaluated_times=tuple(evaluated_times),
            )

        # Select shortest valid transfer action (minimum lead_time, tie-break by order).
        _, _, chosen = min(valid_candidates, key=lambda item: (item[0], item[1]))
        effective_time = t + chosen.lead_time
        transitions.append(
            PathwayTransition(
                time=t,
                from_step_id=current_step.step_id,
                to_step_id=chosen.step_id,
                signpost_id=trigger.signpost_id,
                observed_value=obs_val,
                threshold=trigger.threshold,
                lead_time=chosen.lead_time,
                effective_time=effective_time,
            )
        )
        current_step = chosen
        consecutive = 0

        if chosen.lead_time == 0:
            idx += 1
        else:
            while idx < len(times) and times[idx] < effective_time:
                idx += 1

    final_status: PathwayStatus = "TRANSFERRED" if transitions else "NO_TRIGGER"
    return PathwayEvaluation(
        pathway_id=plan.pathway_id,
        status=final_status,
        active_step_id=current_step.step_id,
        transitions=tuple(transitions),
        tipping_events=tuple(tipping_events),
        rejected_transfers=tuple(rejected_transfers),
        missing=None,
        evaluated_times=tuple(evaluated_times),
    )
