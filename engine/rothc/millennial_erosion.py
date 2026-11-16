"""Millennial POM/MAOM soil carbon partitioning and lateral erosional SOC coupling.

Frontier Unit F-13 (``27_PLAN_DE_FRONTERA.md`` §§5.3, 14).
Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

This module implements two standalone, opt-in frontier mechanisms as pure
functions (G1) without modifying baseline RothC:

1. **Measurable-fraction soil carbon partitioning (PROPOSED):**
   Soil organic carbon is tracked in two physical fractions: particulate organic
   carbon (``pom``) and mineral-associated organic carbon (``maom``), with a
   mineral sorption capacity ceiling ``maom_max_t_c_ha`` (in ``t C ha-1``).
   When MAOM sorption demand exceeds available mineral headroom
   (``maom_max_t_c_ha - maom_retained``), MAOM is bounded by
   ``maom <= maom_max_t_c_ha`` and the excess carbon is partitioned explicitly
   between POM retention and respiration via ``excess_maom_to_pom_fraction``.

2. **Lateral erosional SOC coupling (``coupled_erosion_status="HYPOTHESIS"``):**
   Strictly opt-in (``coupled_erosion=False`` by default) so baseline runs are
   never silently altered. When enabled, lateral carbon export per step is
   ``c_eroded = soil_loss_Mg_ha * topsoil_soc_fraction * enrichment_ratio``
   (units: ``t C ha-1``, since ``1 Mg == 1 t``). Whenever ``soil_loss_Mg_ha``,
   ``topsoil_soc_fraction``, or ``enrichment_ratio`` is ``Missing`` or
   non-finite, lateral C loss returns typed ``Missing(reason="MISSING_INPUT")``
   rather than silently defaulting to ``0.0``.

All biological, partitioning, and capacity parameters are caller-supplied
through ``MillennialErosionParams`` with zero hardcoded method defaults.
Every computed step enforces strict mass conservation via ``math.fsum``:
``delta_pom + delta_maom == c_input - c_respired - c_eroded``.

Pure Python 3.12 stdlib + ``contracts.*`` only (G1): no file I/O, no network,
no clock, no environment variables, and inputs are never mutated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.common import Missing as InputMissing
from contracts.results.models import Missing as ResultMissing

__all__ = [
    "COUPLED_EROSION_STATUS",
    "PROPOSED_STATUS",
    "LateralCarbonLoss",
    "LateralErosionInput",
    "MillennialErosionParams",
    "MillennialPoolState",
    "MillennialRunResult",
    "MillennialStepInput",
    "MillennialStepResult",
    "compute_lateral_c_loss",
    "run_millennial_erosion",
    "step_millennial_erosion",
]

PROPOSED_STATUS: Literal["PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"] = (
    "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
)
COUPLED_EROSION_STATUS: Literal["HYPOTHESIS"] = "HYPOTHESIS"

_MISSING_SHAPES = (InputMissing, ResultMissing)
_AUDIT_TERM_LABELS = (
    "pom_start",
    "maom_start",
    "c_input",
    "c_respired",
    "c_eroded",
    "pom_end",
    "maom_end",
    "residual",
)

Number = int | float
NumberOrMissing = int | float | InputMissing | ResultMissing
AnyMissing = InputMissing | ResultMissing


def _is_missing(item: object) -> bool:
    return isinstance(item, _MISSING_SHAPES)


def _is_number(item: object) -> bool:
    return isinstance(item, (int, float)) and not isinstance(item, bool)


def _finite(item: Number) -> float | None:
    try:
        number = float(item)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _describe_missing(name: str, missing: AnyMissing) -> str:
    text = f"{name} is missing, reason {missing.reason}"
    if missing.detail is not None:
        text += f": {missing.detail}"
    return text


def _check_numbers(items: Mapping[str, object]) -> None:
    for name, item in items.items():
        if _is_missing(item) or _is_number(item):
            continue
        raise TypeError(
            f"{name}: expected int, float, or Missing; got {type(item).__name__}"
        )


def _check_strict_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name}: expected bool, got {type(value).__name__}")


def _extract_finite(
    items: Mapping[str, NumberOrMissing],
    *,
    non_finite_reason: Literal["MISSING_INPUT", "NOT_COMPUTABLE"],
) -> dict[str, float] | ResultMissing:
    missing_parts = [
        _describe_missing(name, item)
        for name, item in items.items()
        if _is_missing(item)
    ]
    if missing_parts:
        return ResultMissing(reason="MISSING_INPUT", detail="; ".join(missing_parts))

    values: dict[str, float] = {}
    non_finite_names: list[str] = []
    for name, item in items.items():
        assert _is_number(item)
        converted = _finite(item)
        if converted is None:
            non_finite_names.append(name)
        else:
            values[name] = converted

    if non_finite_names:
        detail = "; ".join(
            f"{name} is not a finite number" for name in non_finite_names
        )
        return ResultMissing(reason=non_finite_reason, detail=detail)
    return values


def _is_fraction(value: float) -> bool:
    return 0.0 <= value <= 1.0


def _is_non_negative(value: float) -> bool:
    return value >= 0.0


@dataclass(frozen=True)
class MillennialPoolState:
    """Measurable soil organic carbon pools in ``t C ha-1``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    pom: float
    maom: float

    @property
    def total(self) -> float:
        """Total soil organic carbon (``pom + maom``) via ``math.fsum``."""
        return math.fsum((self.pom, self.maom))


@dataclass(frozen=True)
class MillennialErosionParams:
    """Caller-supplied parameters for POM/MAOM partitioning and sorption.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    No biological, rate, or capacity parameter carries a hardcoded default.
    """

    pom_input_fraction: NumberOrMissing
    pom_decay_fraction: NumberOrMissing
    pom_to_maom_fraction: NumberOrMissing
    maom_decay_fraction: NumberOrMissing
    maom_max_t_c_ha: NumberOrMissing
    excess_maom_to_pom_fraction: NumberOrMissing


@dataclass(frozen=True)
class LateralErosionInput:
    """Inputs for HYPOTHESIS lateral erosional SOC loss calculation.

    ``soil_loss_Mg_ha`` is eroded soil mass in ``Mg ha-1`` (``t ha-1``);
    ``topsoil_soc_fraction`` is dimensionless bulk topsoil SOC mass fraction;
    ``enrichment_ratio`` is the dimensionless carbon enrichment ratio.
    """

    soil_loss_Mg_ha: NumberOrMissing
    topsoil_soc_fraction: NumberOrMissing
    enrichment_ratio: NumberOrMissing


@dataclass(frozen=True)
class LateralCarbonLoss:
    """Computed lateral erosional SOC export in ``t C ha-1``."""

    c_eroded_t_c_ha: float
    soil_loss_Mg_ha: float
    topsoil_soc_fraction: float
    enrichment_ratio: float
    status: Literal["HYPOTHESIS"]


@dataclass(frozen=True)
class MillennialStepInput:
    """Inputs for one step of ``run_millennial_erosion``."""

    c_input: NumberOrMissing
    erosion_input: LateralErosionInput | AnyMissing | None = None


@dataclass(frozen=True)
class MillennialStepResult:
    """Result of one Millennial POM/MAOM + optional erosion step.

    Enforces ``delta_pom + delta_maom == c_input - c_respired - c_eroded``
    and ``end.maom <= maom_max_t_c_ha``.
    """

    start: MillennialPoolState
    end: MillennialPoolState
    c_input: float
    c_respired: float
    c_eroded: float
    delta_pom: float
    delta_maom: float
    pom_respired: float
    maom_respired: float
    excess_respired: float
    maom_sorption_excess: float
    eroded_from_pom: float
    eroded_from_maom: float
    mass_balance_residual: float
    coupled_erosion_applied: bool
    coupled_erosion_status: Literal["HYPOTHESIS"]
    status: Literal["PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"]


@dataclass(frozen=True)
class MillennialRunResult:
    """Multi-step Millennial POM/MAOM + optional erosion run."""

    initial_state: MillennialPoolState | ResultMissing
    steps: tuple[MillennialStepResult | ResultMissing, ...]
    coupled_erosion_applied: bool
    coupled_erosion_status: Literal["HYPOTHESIS"]
    status: Literal["PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"]

    def total_stocks(self) -> tuple[float | ResultMissing, ...]:
        """Total SOC (``pom + maom``) at start and after each step."""
        first: float | ResultMissing = (
            self.initial_state
            if isinstance(self.initial_state, ResultMissing)
            else self.initial_state.total
        )
        return (first,) + tuple(
            item if isinstance(item, ResultMissing) else item.end.total
            for item in self.steps
        )


def _validate_state_arg(state: object) -> None:
    if _is_missing(state):
        return
    if not isinstance(state, MillennialPoolState):
        raise TypeError(
            "state: expected MillennialPoolState or Missing; "
            f"got {type(state).__name__}"
        )
    _check_numbers({"state.pom": state.pom, "state.maom": state.maom})


def _validate_params_arg(params: object) -> None:
    if not isinstance(params, MillennialErosionParams):
        raise TypeError(
            f"params: expected MillennialErosionParams; got {type(params).__name__}"
        )
    _check_numbers(
        {
            "params.pom_input_fraction": params.pom_input_fraction,
            "params.pom_decay_fraction": params.pom_decay_fraction,
            "params.pom_to_maom_fraction": params.pom_to_maom_fraction,
            "params.maom_decay_fraction": params.maom_decay_fraction,
            "params.maom_max_t_c_ha": params.maom_max_t_c_ha,
            "params.excess_maom_to_pom_fraction": params.excess_maom_to_pom_fraction,
        }
    )


def _validate_erosion_arg(erosion_input: object) -> None:
    if erosion_input is None or _is_missing(erosion_input):
        return
    if not isinstance(erosion_input, LateralErosionInput):
        raise TypeError(
            "erosion_input: expected LateralErosionInput, Missing, or None; "
            f"got {type(erosion_input).__name__}"
        )
    _check_numbers(
        {
            "erosion_input.soil_loss_Mg_ha": erosion_input.soil_loss_Mg_ha,
            "erosion_input.topsoil_soc_fraction": erosion_input.topsoil_soc_fraction,
            "erosion_input.enrichment_ratio": erosion_input.enrichment_ratio,
        }
    )


def compute_lateral_c_loss(
    *,
    soil_loss_Mg_ha: NumberOrMissing,
    topsoil_soc_fraction: NumberOrMissing,
    enrichment_ratio: NumberOrMissing,
) -> LateralCarbonLoss | ResultMissing:
    """Compute HYPOTHESIS lateral erosional SOC loss in ``t C ha-1``.

    Formula: ``c_eroded = soil_loss_Mg_ha * topsoil_soc_fraction * enrichment_ratio``.
    Whenever any of ``soil_loss_Mg_ha``, ``topsoil_soc_fraction``, or
    ``enrichment_ratio`` is ``Missing`` or non-finite, returns typed
    ``Missing(reason="MISSING_INPUT")`` rather than silently defaulting to ``0.0``.
    """
    raw = {
        "soil_loss_Mg_ha": soil_loss_Mg_ha,
        "topsoil_soc_fraction": topsoil_soc_fraction,
        "enrichment_ratio": enrichment_ratio,
    }
    _check_numbers(raw)
    values = _extract_finite(raw, non_finite_reason="MISSING_INPUT")
    if isinstance(values, ResultMissing):
        return values

    if not _is_non_negative(values["soil_loss_Mg_ha"]):
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="soil_loss_Mg_ha is negative"
        )
    if not _is_fraction(values["topsoil_soc_fraction"]):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="topsoil_soc_fraction is outside zero to one",
        )
    if not _is_non_negative(values["enrichment_ratio"]):
        return ResultMissing(
            reason="NOT_COMPUTABLE", detail="enrichment_ratio is negative"
        )

    product = _finite(
        values["soil_loss_Mg_ha"]
        * values["topsoil_soc_fraction"]
        * values["enrichment_ratio"]
    )
    if product is None:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="c_eroded is not a finite real number",
        )

    return LateralCarbonLoss(
        c_eroded_t_c_ha=product,
        soil_loss_Mg_ha=values["soil_loss_Mg_ha"],
        topsoil_soc_fraction=values["topsoil_soc_fraction"],
        enrichment_ratio=values["enrichment_ratio"],
        status=COUPLED_EROSION_STATUS,
    )


def _resolve_eroded_carbon(
    *,
    coupled_erosion: bool,
    erosion_input: LateralErosionInput | AnyMissing | None,
) -> float | ResultMissing:
    if not coupled_erosion:
        return 0.0
    if erosion_input is None:
        return ResultMissing(
            reason="MISSING_INPUT",
            detail="erosion_input is missing when coupled_erosion is enabled",
        )
    if _is_missing(erosion_input):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=_describe_missing("erosion_input", erosion_input),
        )
    assert isinstance(erosion_input, LateralErosionInput)
    lateral = compute_lateral_c_loss(
        soil_loss_Mg_ha=erosion_input.soil_loss_Mg_ha,
        topsoil_soc_fraction=erosion_input.topsoil_soc_fraction,
        enrichment_ratio=erosion_input.enrichment_ratio,
    )
    if isinstance(lateral, ResultMissing):
        return lateral
    return lateral.c_eroded_t_c_ha


def _validate_step_domain(values: Mapping[str, float]) -> ResultMissing | None:
    non_negative_fields = (
        "state.pom",
        "state.maom",
        "c_input",
        "params.maom_max_t_c_ha",
    )
    for field in non_negative_fields:
        if not _is_non_negative(values[field]):
            return ResultMissing(reason="NOT_COMPUTABLE", detail=f"{field} is negative")

    fraction_fields = (
        "params.pom_input_fraction",
        "params.pom_decay_fraction",
        "params.pom_to_maom_fraction",
        "params.maom_decay_fraction",
        "params.excess_maom_to_pom_fraction",
    )
    for field in fraction_fields:
        if not _is_fraction(values[field]):
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"{field} is outside zero to one",
            )

    if values["state.maom"] > values["params.maom_max_t_c_ha"]:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="state.maom exceeds params.maom_max_t_c_ha",
        )
    return None


def _allocate_erosion(
    *,
    c_eroded: float,
    pom_pre: float,
    maom_pre: float,
) -> tuple[float, float] | ResultMissing:
    total_pre = math.fsum((pom_pre, maom_pre))
    if c_eroded > total_pre:
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="c_eroded exceeds available topsoil SOC (pom + maom)",
        )
    if c_eroded == 0.0 or total_pre == 0.0:
        return 0.0, 0.0

    eroded_from_pom = min(c_eroded * (pom_pre / total_pre), pom_pre)
    eroded_from_maom = c_eroded - eroded_from_pom
    if eroded_from_maom > maom_pre:
        eroded_from_maom = maom_pre
        eroded_from_pom = c_eroded - eroded_from_maom
    eroded_from_pom = max(eroded_from_pom, 0.0)
    eroded_from_maom = max(eroded_from_maom, 0.0)
    return eroded_from_pom, eroded_from_maom


def step_millennial_erosion(
    *,
    state: MillennialPoolState | AnyMissing,
    c_input: NumberOrMissing,
    params: MillennialErosionParams,
    coupled_erosion: bool = False,
    erosion_input: LateralErosionInput | AnyMissing | None = None,
) -> MillennialStepResult | ResultMissing:
    """Advance POM and MAOM by one step with optional lateral erosion coupling.

    - ``coupled_erosion`` defaults to ``False`` so lateral erosion never
      silently alters baseline runs without explicit opt-in.
    - Respects ``end.maom <= params.maom_max_t_c_ha`` via explicit partitioning
      of sorption overflow between POM and respiration.
    - Audits ``delta_pom + delta_maom == c_input - c_respired - c_eroded``
      with ``math.fsum``.
    """
    _validate_state_arg(state)
    _check_numbers({"c_input": c_input})
    _validate_params_arg(params)
    _check_strict_bool("coupled_erosion", coupled_erosion)
    _validate_erosion_arg(erosion_input)

    if _is_missing(state):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=_describe_missing("state", state),
        )
    assert isinstance(state, MillennialPoolState)

    number_args: dict[str, NumberOrMissing] = {
        "state.pom": state.pom,
        "state.maom": state.maom,
        "c_input": c_input,
        "params.pom_input_fraction": params.pom_input_fraction,
        "params.pom_decay_fraction": params.pom_decay_fraction,
        "params.pom_to_maom_fraction": params.pom_to_maom_fraction,
        "params.maom_decay_fraction": params.maom_decay_fraction,
        "params.maom_max_t_c_ha": params.maom_max_t_c_ha,
        "params.excess_maom_to_pom_fraction": params.excess_maom_to_pom_fraction,
    }
    values = _extract_finite(number_args, non_finite_reason="NOT_COMPUTABLE")
    if isinstance(values, ResultMissing):
        return values

    domain_error = _validate_step_domain(values)
    if domain_error is not None:
        return domain_error

    c_eroded_or_missing = _resolve_eroded_carbon(
        coupled_erosion=coupled_erosion,
        erosion_input=erosion_input,
    )
    if isinstance(c_eroded_or_missing, ResultMissing):
        return c_eroded_or_missing
    c_eroded = c_eroded_or_missing

    pom_start = values["state.pom"]
    maom_start = values["state.maom"]
    c_in = values["c_input"]
    maom_max = values["params.maom_max_t_c_ha"]

    input_to_pom = c_in * values["params.pom_input_fraction"]
    input_to_maom = c_in - input_to_pom

    pom_available = pom_start + input_to_pom
    pom_decomposed = pom_available * values["params.pom_decay_fraction"]
    pom_remaining = pom_available - pom_decomposed
    pom_to_maom = pom_decomposed * values["params.pom_to_maom_fraction"]
    pom_respired = pom_decomposed - pom_to_maom

    maom_respired = maom_start * values["params.maom_decay_fraction"]
    maom_retained = maom_start - maom_respired

    sorption_demand = math.fsum((input_to_maom, pom_to_maom))
    maom_headroom = max(maom_max - maom_retained, 0.0)

    if sorption_demand <= maom_headroom:
        maom_sorbed = sorption_demand
        sorption_excess = 0.0
    else:
        maom_sorbed = maom_headroom
        if maom_retained + maom_sorbed > maom_max and maom_sorbed > 0.0:
            maom_sorbed = math.nextafter(maom_sorbed, 0.0)
        sorption_excess = sorption_demand - maom_sorbed

    excess_to_pom = sorption_excess * values["params.excess_maom_to_pom_fraction"]
    excess_respired = sorption_excess - excess_to_pom

    pom_pre = math.fsum((pom_remaining, excess_to_pom))
    maom_pre = math.fsum((maom_retained, maom_sorbed))
    c_respired = math.fsum((pom_respired, maom_respired, excess_respired))

    eroded_split = _allocate_erosion(
        c_eroded=c_eroded,
        pom_pre=pom_pre,
        maom_pre=maom_pre,
    )
    if isinstance(eroded_split, ResultMissing):
        return eroded_split
    eroded_from_pom, eroded_from_maom = eroded_split

    pom_end = pom_pre - eroded_from_pom
    maom_end = maom_pre - eroded_from_maom

    if any(
        _finite(val) is None
        for val in (pom_end, maom_end, c_respired, c_eroded, sorption_excess)
    ):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="step_millennial_erosion produced non-finite pool or flux",
        )

    delta_pom = pom_end - pom_start
    delta_maom = maom_end - maom_start
    lhs = math.fsum((delta_pom, delta_maom))
    rhs = math.fsum((c_in, -c_respired, -c_eroded))
    residual = math.fsum((lhs, -rhs))
    scale = max(pom_start, maom_start, c_in, c_respired, c_eroded, pom_end, maom_end)
    abs_tol = len(_AUDIT_TERM_LABELS) * math.ulp(scale)
    rel_tol = len(_AUDIT_TERM_LABELS) * math.ulp(1.0)
    if not math.isclose(lhs, rhs, rel_tol=rel_tol, abs_tol=abs_tol):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail="mass conservation audit failed beyond machine precision",
        )

    return MillennialStepResult(
        start=MillennialPoolState(pom=pom_start, maom=maom_start),
        end=MillennialPoolState(pom=pom_end, maom=maom_end),
        c_input=c_in,
        c_respired=c_respired,
        c_eroded=c_eroded,
        delta_pom=delta_pom,
        delta_maom=delta_maom,
        pom_respired=pom_respired,
        maom_respired=maom_respired,
        excess_respired=excess_respired,
        maom_sorption_excess=sorption_excess,
        eroded_from_pom=eroded_from_pom,
        eroded_from_maom=eroded_from_maom,
        mass_balance_residual=residual,
        coupled_erosion_applied=coupled_erosion,
        coupled_erosion_status=COUPLED_EROSION_STATUS,
        status=PROPOSED_STATUS,
    )


def run_millennial_erosion(
    *,
    initial_state: MillennialPoolState | AnyMissing,
    steps: Sequence[MillennialStepInput],
    params: MillennialErosionParams,
    coupled_erosion: bool = False,
) -> MillennialRunResult:
    """Run ``step_millennial_erosion`` across a sequence of steps.

    Once a step returns ``Missing``, every subsequent step returns
    ``Missing(reason="MISSING_INPUT")`` naming the failure rather than
    resetting pools or defaulting to zero.
    """
    _validate_state_arg(initial_state)
    _validate_params_arg(params)
    _check_strict_bool("coupled_erosion", coupled_erosion)
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise TypeError(
            f"steps: expected a sequence of MillennialStepInput, got {type(steps).__name__}"
        )
    for idx, item in enumerate(steps):
        if not isinstance(item, MillennialStepInput):
            raise TypeError(
                f"steps[{idx}]: expected MillennialStepInput, got {type(item).__name__}"
            )
        _check_numbers({f"steps[{idx}].c_input": item.c_input})
        _validate_erosion_arg(item.erosion_input)

    resolved_initial: MillennialPoolState | ResultMissing
    if _is_missing(initial_state):
        resolved_initial = ResultMissing(
            reason="MISSING_INPUT",
            detail=_describe_missing("initial_state", initial_state),
        )
        first_failure: str | None = _describe_missing("initial_state", initial_state)
    else:
        assert isinstance(initial_state, MillennialPoolState)
        checked = _extract_finite(
            {
                "initial_state.pom": initial_state.pom,
                "initial_state.maom": initial_state.maom,
            },
            non_finite_reason="NOT_COMPUTABLE",
        )
        if isinstance(checked, ResultMissing):
            resolved_initial = checked
            first_failure = checked.detail
        elif not _is_non_negative(checked["initial_state.pom"]) or not _is_non_negative(
            checked["initial_state.maom"]
        ):
            resolved_initial = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail="initial_state pools must be non-negative",
            )
            first_failure = resolved_initial.detail
        else:
            resolved_initial = MillennialPoolState(
                pom=checked["initial_state.pom"],
                maom=checked["initial_state.maom"],
            )
            first_failure = None

    results: list[MillennialStepResult | ResultMissing] = []
    current_state: MillennialPoolState | ResultMissing = resolved_initial

    for idx, step_input in enumerate(steps):
        if first_failure is not None:
            results.append(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=f"step {idx}: start state is missing; {first_failure}",
                )
            )
            continue

        step_result = step_millennial_erosion(
            state=current_state,
            c_input=step_input.c_input,
            params=params,
            coupled_erosion=coupled_erosion,
            erosion_input=step_input.erosion_input,
        )
        if isinstance(step_result, ResultMissing):
            first_failure = f"step {idx} failed, reason {step_result.reason}"
            if step_result.detail is not None:
                first_failure += f": {step_result.detail}"
            tagged = (
                ResultMissing(
                    reason=step_result.reason,
                    detail=f"step {idx}: {step_result.detail}",
                )
                if step_result.detail is not None
                else step_result
            )
            results.append(tagged)
            continue

        results.append(step_result)
        current_state = step_result.end

    return MillennialRunResult(
        initial_state=resolved_initial,
        steps=tuple(results),
        coupled_erosion_applied=coupled_erosion,
        coupled_erosion_status=COUPLED_EROSION_STATUS,
        status=PROPOSED_STATUS,
    )
