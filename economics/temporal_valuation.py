"""Temporal valuation of crop rotations over a common horizon: NPV and Equivalent Annuity.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Specification: ``27_PLAN_DE_FRONTERA.md`` §13 and ``28_PLAN_INTEGRADO_REV13.md`` §4.

This module evaluates periodic timed cash flows ``CF_t`` over a common horizon
``n >= 1`` years at discount rate ``r > -1.0``, covering:
- initial investment ``CF_0`` at ``t = 0``,
- timed establishment or renovation flows,
- transition-year flows before steady rotation cycles begin,
- repeated rotation cycle cash flows across the horizon, and
- terminal residual value at ``t = n``.

Strict separation of quantities:
- ``annual_cash_flows``: per-year net cash flows ``CF_1 .. CF_n``,
- ``undiscounted_cycle_mean``: simple undiscounted arithmetic mean per year
  (never labelled VAN/NPV),
- ``npv``: discounted present value ``sum(cf_t / ((1 + r) ** t))`` for ``t = 0..n``,
- ``equivalent_annuity``: annualized equivalent of ``npv`` over ``n`` years
  (``npv * r / (1 - (1 + r) ** (-n))`` for ``r != 0``, ``npv / n`` for ``r == 0``),
- ``label_npv_as_discounted_present_value=True``.

Pure functions only: no network calls, no file access, no environment reads,
and no parameter constants.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictInt,
    model_validator,
)

from contracts.economic_facts import COST_UNIT, MARGIN_UNIT
from contracts.inputs.common import Missing as InputsMissing
from contracts.inputs.common import NonEmptyStr
from contracts.results.models import Missing

Basis = Literal["real", "nominal"]
ComparisonStatus = Literal["resolved", "tied", "not_resolved"]

DEFAULT_CASH_FLOW_UNIT = COST_UNIT
DEFAULT_ANNUAL_UNIT = MARGIN_UNIT
NPV_LABEL = "discounted_present_value"

__all__ = [
    "Basis",
    "CashFlowValue",
    "ComparisonStatus",
    "ComputedValue",
    "Missing",
    "RotationTemporalOption",
    "TemporalComparisonResult",
    "TemporalValuationInput",
    "TemporalValuationResult",
    "compare_rotations_common_horizon",
    "evaluate_temporal_valuation",
]


def _check_finite_if_number(value: object) -> object:
    """Reject non-finite numbers with an explicit NOT_COMPUTABLE message."""
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not math.isfinite(value)
    ):
        raise ValueError(f"NOT_COMPUTABLE: non-finite numeric value {value!r}")
    return value


FiniteNumber = Annotated[FiniteFloat, BeforeValidator(_check_finite_if_number)]
CashFlowValue = FiniteNumber | Missing | InputsMissing
ComputedValue = FiniteFloat | Missing


class _StrictModel(BaseModel):
    """Strict, frozen Pydantic base rejecting unknown fields and NaN/Inf."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


def _normalize_missing(value: CashFlowValue) -> float | Missing:
    """Convert numeric values to float and normalize Missing instances."""
    if isinstance(value, Missing):
        return value
    if isinstance(value, InputsMissing):
        return Missing(reason=value.reason, detail=value.detail)
    return float(value)


def _format_missing_detail(value: Missing) -> str:
    if value.detail is not None:
        return f"{value.reason}: {value.detail}"
    return value.reason


def _combine_missing_reason(
    label: str, items: Sequence[tuple[str, Missing]]
) -> Missing:
    """Build a MISSING_INPUT Missing summarizing all absent inputs."""
    parts = [f"{name} ({_format_missing_detail(miss)})" for name, miss in items]
    return Missing(
        reason="MISSING_INPUT",
        detail=f"{label} cannot be computed because input flow(s) are missing: "
        + "; ".join(parts),
    )


def _add_flow(
    a: float | Missing,
    b: float | Missing,
    label_a: str,
    label_b: str,
) -> float | Missing:
    """Add two cash-flow terms, propagating Missing as MISSING_INPUT."""
    missing_items: list[tuple[str, Missing]] = []
    if isinstance(a, Missing):
        missing_items.append((label_a, a))
    if isinstance(b, Missing):
        missing_items.append((label_b, b))
    if missing_items:
        return _combine_missing_reason("cash flow", missing_items)
    total = a + b
    if not math.isfinite(total):
        raise ValueError("NOT_COMPUTABLE: combined cash flow is not finite")
    return total


class TemporalValuationInput(_StrictModel):
    """Validated inputs for evaluating one rotation's NPV and equivalent annuity.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    horizon_years: StrictInt = Field(ge=1)
    discount_rate: FiniteNumber
    price_basis: Basis
    rate_basis: Basis
    cf0_investment: CashFlowValue = 0.0
    annual_cash_flows: (
        Sequence[CashFlowValue] | Mapping[StrictInt, CashFlowValue] | None
    ) = None
    cycle_cash_flows: Sequence[CashFlowValue] | None = None
    transition_cash_flows: (
        Sequence[CashFlowValue] | Mapping[StrictInt, CashFlowValue] | None
    ) = None
    establishment_renovation_flows: Mapping[StrictInt, CashFlowValue] | None = None
    terminal_residual_value: CashFlowValue = 0.0
    includes_non_monetary_depreciation: bool = False
    rotation_id: NonEmptyStr | None = None
    cash_flow_unit: NonEmptyStr = DEFAULT_CASH_FLOW_UNIT
    annual_unit: NonEmptyStr = DEFAULT_ANNUAL_UNIT

    @model_validator(mode="after")
    def _validate_guards(self) -> TemporalValuationInput:
        if self.discount_rate <= -1.0:
            raise ValueError(
                "NOT_COMPUTABLE: discount_rate r must be > -1.0 "
                f"(got {self.discount_rate!r})"
            )
        if self.price_basis != self.rate_basis:
            raise ValueError(
                f"price_basis ({self.price_basis!r}) must match rate_basis "
                f"({self.rate_basis!r}) for real/nominal consistency"
            )
        self._check_double_deduction_guard()
        self._check_flow_schedule_structure()
        return self

    def _check_double_deduction_guard(self) -> None:
        if not self.includes_non_monetary_depreciation:
            return
        cf0 = _normalize_missing(self.cf0_investment)
        if isinstance(cf0, float) and cf0 != 0.0:
            raise ValueError(
                "double deduction guard: cannot combine "
                "includes_non_monetary_depreciation=True with cf0_investment != 0"
            )
        if isinstance(self.annual_cash_flows, Mapping) and 0 in self.annual_cash_flows:
            t0 = _normalize_missing(self.annual_cash_flows[0])
            if isinstance(t0, float) and t0 != 0.0:
                raise ValueError(
                    "double deduction guard: cannot combine "
                    "includes_non_monetary_depreciation=True with non-zero CF_0"
                )

    def _check_flow_schedule_structure(self) -> None:
        n = self.horizon_years
        if self.establishment_renovation_flows is not None:
            bad = sorted(
                t for t in self.establishment_renovation_flows if not (0 <= t <= n)
            )
            if bad:
                raise ValueError(
                    f"establishment_renovation_flows keys must be in 0..{n}, got {bad}"
                )

        if self.annual_cash_flows is not None:
            self._check_explicit_annual_flows(n)
            return

        self._check_cycle_and_transition_flows(n)

    def _check_explicit_annual_flows(self, n: int) -> None:
        if self.cycle_cash_flows is not None:
            raise ValueError(
                "provide either annual_cash_flows or cycle_cash_flows, not both"
            )
        if isinstance(self.transition_cash_flows, Sequence) and not isinstance(
            self.transition_cash_flows, (str, bytes)
        ):
            raise ValueError(  # noqa: TRY004
                "provide either annual_cash_flows or sequence transition_cash_flows, "
                "not both"
            )
        if isinstance(self.transition_cash_flows, Mapping):
            bad = sorted(t for t in self.transition_cash_flows if not (1 <= t <= n))
            if bad:
                raise ValueError(
                    f"transition_cash_flows keys must be in 1..{n}, got {bad}"
                )
        if isinstance(self.annual_cash_flows, Mapping):
            keys = set(self.annual_cash_flows)
            bad = sorted(t for t in keys if not (0 <= t <= n))
            if bad:
                raise ValueError(f"annual_cash_flows keys must be in 0..{n}, got {bad}")
            missing_years = [t for t in range(1, n + 1) if t not in keys]
            if missing_years:
                raise ValueError(
                    f"annual_cash_flows mapping must cover all years 1..{n}; "
                    f"missing keys {missing_years}"
                )
            if 0 in keys:
                cf0 = _normalize_missing(self.cf0_investment)
                if not (isinstance(cf0, float) and cf0 == 0.0):
                    raise ValueError(
                        "cannot specify t=0 in both cf0_investment and "
                        "annual_cash_flows[0]"
                    )
        else:
            assert self.annual_cash_flows is not None
            if len(self.annual_cash_flows) != n:
                raise ValueError(
                    f"annual_cash_flows sequence length ({len(self.annual_cash_flows)}) "
                    f"must equal horizon_years ({n})"
                )

    def _check_cycle_and_transition_flows(self, n: int) -> None:
        if self.cycle_cash_flows is not None and len(self.cycle_cash_flows) == 0:
            raise ValueError("cycle_cash_flows must contain at least one year")

        if isinstance(self.transition_cash_flows, Mapping):
            bad = sorted(t for t in self.transition_cash_flows if not (1 <= t <= n))
            if bad:
                raise ValueError(
                    f"transition_cash_flows keys must be in 1..{n}, got {bad}"
                )
            if self.cycle_cash_flows is None:
                raise ValueError(
                    "cycle_cash_flows is required when transition_cash_flows is a "
                    "year-adjustment mapping"
                )
            return

        if self.transition_cash_flows is not None:
            k = len(self.transition_cash_flows)
            if k > n:
                raise ValueError(
                    f"transition_cash_flows length ({k}) cannot exceed "
                    f"horizon_years ({n})"
                )
            if k < n and self.cycle_cash_flows is None:
                raise ValueError(
                    "cycle_cash_flows is required to fill years "
                    f"{k + 1}..{n} after transition_cash_flows"
                )
            return

        if self.cycle_cash_flows is None:
            raise ValueError("annual_cash_flows or cycle_cash_flows must be provided")


class TemporalValuationResult(_StrictModel):
    """Typed temporal valuation output separating undiscounted and discounted metrics.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    rotation_id: NonEmptyStr | None = None
    horizon_years: StrictInt = Field(ge=1)
    discount_rate: FiniteNumber
    price_basis: Basis
    rate_basis: Basis
    cf0_investment: ComputedValue
    annual_cash_flows: dict[StrictInt, ComputedValue]
    timed_cash_flows: dict[StrictInt, ComputedValue]
    terminal_residual_value: ComputedValue
    includes_non_monetary_depreciation: bool
    undiscounted_cycle_mean: ComputedValue
    npv: ComputedValue
    equivalent_annuity: ComputedValue
    label_npv_as_discounted_present_value: Literal[True] = True
    npv_label: Literal["discounted_present_value"] = NPV_LABEL
    cash_flow_unit: NonEmptyStr = DEFAULT_CASH_FLOW_UNIT
    annual_unit: NonEmptyStr = DEFAULT_ANNUAL_UNIT


class RotationTemporalOption(_StrictModel):
    """One rotation option submitted to ``compare_rotations_common_horizon``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    rotation_id: NonEmptyStr
    valuation: TemporalValuationResult | TemporalValuationInput


class TemporalComparisonResult(_StrictModel):
    """Comparison of rotations over an equal common horizon and identical discount basis.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    horizon_years: StrictInt = Field(ge=1)
    discount_rate: FiniteNumber
    price_basis: Basis
    rate_basis: Basis
    cash_flow_unit: NonEmptyStr
    annual_unit: NonEmptyStr
    status: ComparisonStatus
    best_rotation_id: NonEmptyStr | None
    ranked_rotation_ids: tuple[NonEmptyStr, ...]
    tied_rotation_ids: tuple[NonEmptyStr, ...]
    options: dict[NonEmptyStr, TemporalValuationResult]
    missing: Missing | None = None
    label_npv_as_discounted_present_value: Literal[True] = True


def _build_cash_flow_schedule(
    spec: TemporalValuationInput,
) -> tuple[float | Missing, dict[int, float | Missing]]:
    """Expand CF_0 and annual CF_1..CF_n from the validated input specification."""
    n = spec.horizon_years

    cf0: float | Missing = _normalize_missing(spec.cf0_investment)
    if isinstance(spec.annual_cash_flows, Mapping) and 0 in spec.annual_cash_flows:
        cf0 = _normalize_missing(spec.annual_cash_flows[0])

    annual: dict[int, float | Missing] = {}
    if spec.annual_cash_flows is not None:
        if isinstance(spec.annual_cash_flows, Mapping):
            for t in range(1, n + 1):
                annual[t] = _normalize_missing(spec.annual_cash_flows[t])
        else:
            for t, raw in enumerate(spec.annual_cash_flows, start=1):
                annual[t] = _normalize_missing(raw)
    elif isinstance(spec.transition_cash_flows, Sequence):
        k = len(spec.transition_cash_flows)
        for t in range(1, k + 1):
            annual[t] = _normalize_missing(spec.transition_cash_flows[t - 1])
        if k < n:
            assert spec.cycle_cash_flows is not None
            cycle_len = len(spec.cycle_cash_flows)
            for t in range(k + 1, n + 1):
                annual[t] = _normalize_missing(
                    spec.cycle_cash_flows[(t - k - 1) % cycle_len]
                )
    else:
        assert spec.cycle_cash_flows is not None
        cycle_len = len(spec.cycle_cash_flows)
        for t in range(1, n + 1):
            annual[t] = _normalize_missing(spec.cycle_cash_flows[(t - 1) % cycle_len])

    if isinstance(spec.transition_cash_flows, Mapping):
        for t, raw in spec.transition_cash_flows.items():
            annual[t] = _add_flow(
                annual[t],
                _normalize_missing(raw),
                f"year {t} base flow",
                f"year {t} transition flow",
            )

    if spec.establishment_renovation_flows is not None:
        for t, raw in spec.establishment_renovation_flows.items():
            norm = _normalize_missing(raw)
            if t == 0:
                cf0 = _add_flow(
                    cf0, norm, "CF_0", "year 0 establishment/renovation flow"
                )
            else:
                annual[t] = _add_flow(
                    annual[t],
                    norm,
                    f"year {t} flow",
                    f"year {t} establishment/renovation flow",
                )

    residual = _normalize_missing(spec.terminal_residual_value)
    if not (isinstance(residual, float) and residual == 0.0):
        annual[n] = _add_flow(
            annual[n],
            residual,
            f"year {n} flow",
            "terminal_residual_value",
        )

    return cf0, annual


def _compute_undiscounted_cycle_mean(
    spec: TemporalValuationInput,
    annual: Mapping[int, float | Missing],
) -> float | Missing:
    """Compute the simple undiscounted annual mean without discounting or CF_0."""
    if spec.cycle_cash_flows is not None:
        cycle_vals = [_normalize_missing(v) for v in spec.cycle_cash_flows]
        missing_cycle = [
            (f"cycle[{idx}]", val)
            for idx, val in enumerate(cycle_vals)
            if isinstance(val, Missing)
        ]
        if missing_cycle:
            return _combine_missing_reason("undiscounted_cycle_mean", missing_cycle)
        mean = math.fsum(val for val in cycle_vals if isinstance(val, float)) / len(
            cycle_vals
        )
    else:
        n = spec.horizon_years
        missing_years = [
            (f"year {t}", annual[t])
            for t in range(1, n + 1)
            if isinstance(annual[t], Missing)
        ]
        if missing_years:
            return _combine_missing_reason("undiscounted_cycle_mean", missing_years)
        mean = (
            math.fsum(
                val for t in range(1, n + 1) if isinstance((val := annual[t]), float)
            )
            / n
        )
    if not math.isfinite(mean):
        raise ValueError("NOT_COMPUTABLE: undiscounted_cycle_mean is not finite")
    return mean


def _compute_npv_and_ae(
    timed_flows: Mapping[int, float | Missing],
    horizon_years: int,
    discount_rate: float,
) -> tuple[float | Missing, float | Missing]:
    """Compute discounted NPV and Equivalent Annuity (AE) over horizon n."""
    missing_flows = [
        (f"year {t}", flow)
        for t, flow in timed_flows.items()
        if isinstance(flow, Missing)
    ]
    if missing_flows:
        missing_out = _combine_missing_reason("temporal valuation", missing_flows)
        return missing_out, missing_out

    base = 1.0 + discount_rate
    if base <= 0.0 or not math.isfinite(base):
        raise ValueError(f"NOT_COMPUTABLE: invalid discount factor (1 + r)={base!r}")

    discounted_terms: list[float] = []
    try:
        for t, flow in timed_flows.items():
            assert isinstance(flow, float)
            denom = base**t
            if denom == 0.0 or not math.isfinite(denom):
                raise ValueError(
                    f"NOT_COMPUTABLE: non-finite discount denominator at year {t}"
                )
            term = flow / denom
            if not math.isfinite(term):
                raise ValueError(
                    f"NOT_COMPUTABLE: non-finite discounted cash flow at year {t}"
                )
            discounted_terms.append(term)
    except OverflowError as exc:
        raise ValueError(
            "NOT_COMPUTABLE: arithmetic overflow while discounting cash flows"
        ) from exc

    npv = math.fsum(discounted_terms)
    if not math.isfinite(npv):
        raise ValueError("NOT_COMPUTABLE: npv is not finite")

    if discount_rate == 0.0:
        ae = npv / horizon_years
    else:
        try:
            annuity_denom = 1.0 - (base ** (-horizon_years))
        except OverflowError as exc:
            raise ValueError(
                "NOT_COMPUTABLE: arithmetic overflow computing equivalent annuity"
            ) from exc
        if annuity_denom == 0.0:
            annuity_denom = -math.expm1(-horizon_years * math.log1p(discount_rate))
        if annuity_denom == 0.0 or not math.isfinite(annuity_denom):
            raise ValueError(
                "NOT_COMPUTABLE: equivalent annuity denominator is zero or non-finite"
            )
        ae = npv * discount_rate / annuity_denom

    if not math.isfinite(ae):
        raise ValueError("NOT_COMPUTABLE: equivalent_annuity is not finite")

    return npv, ae


def evaluate_temporal_valuation(
    spec: TemporalValuationInput | None = None,
    /,
    *,
    horizon_years: int | None = None,
    discount_rate: float | None = None,
    price_basis: Basis | None = None,
    rate_basis: Basis | None = None,
    cf0_investment: CashFlowValue = 0.0,
    annual_cash_flows: (
        Sequence[CashFlowValue] | Mapping[int, CashFlowValue] | None
    ) = None,
    cycle_cash_flows: Sequence[CashFlowValue] | None = None,
    transition_cash_flows: (
        Sequence[CashFlowValue] | Mapping[int, CashFlowValue] | None
    ) = None,
    establishment_renovation_flows: Mapping[int, CashFlowValue] | None = None,
    terminal_residual_value: CashFlowValue = 0.0,
    includes_non_monetary_depreciation: bool = False,
    rotation_id: str | None = None,
    cash_flow_unit: str = DEFAULT_CASH_FLOW_UNIT,
    annual_unit: str = DEFAULT_ANNUAL_UNIT,
) -> TemporalValuationResult:
    """Evaluate NPV and Equivalent Annuity over a common horizon ``n``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Accepts either a ``TemporalValuationInput`` instance positionally or the
    equivalent keyword arguments. Raises ``ValueError`` on real/nominal basis
    mismatch, double-deduction guard violation, ``r <= -1.0``, non-finite
    values, or structural misuse. A missing year cash flow propagates
    ``Missing(reason="MISSING_INPUT", detail=...)`` without raising.
    """
    if spec is None:
        missing_req = [
            name
            for name, val in (
                ("horizon_years", horizon_years),
                ("discount_rate", discount_rate),
                ("price_basis", price_basis),
                ("rate_basis", rate_basis),
            )
            if val is None
        ]
        if missing_req:
            raise ValueError("missing required argument(s): " + ", ".join(missing_req))
        spec = TemporalValuationInput(
            horizon_years=horizon_years,
            discount_rate=discount_rate,
            price_basis=price_basis,
            rate_basis=rate_basis,
            cf0_investment=cf0_investment,
            annual_cash_flows=annual_cash_flows,
            cycle_cash_flows=cycle_cash_flows,
            transition_cash_flows=transition_cash_flows,
            establishment_renovation_flows=establishment_renovation_flows,
            terminal_residual_value=terminal_residual_value,
            includes_non_monetary_depreciation=includes_non_monetary_depreciation,
            rotation_id=rotation_id,
            cash_flow_unit=cash_flow_unit,
            annual_unit=annual_unit,
        )
    elif not isinstance(spec, TemporalValuationInput):
        raise ValueError(
            f"spec must be a TemporalValuationInput instance, got {type(spec).__name__}"
        )

    cf0, annual = _build_cash_flow_schedule(spec)
    timed_flows: dict[int, float | Missing] = {0: cf0, **annual}
    undiscounted_mean = _compute_undiscounted_cycle_mean(spec, annual)
    npv, ae = _compute_npv_and_ae(
        timed_flows, spec.horizon_years, float(spec.discount_rate)
    )

    return TemporalValuationResult(
        rotation_id=spec.rotation_id,
        horizon_years=spec.horizon_years,
        discount_rate=float(spec.discount_rate),
        price_basis=spec.price_basis,
        rate_basis=spec.rate_basis,
        cf0_investment=cf0,
        annual_cash_flows=annual,
        timed_cash_flows=timed_flows,
        terminal_residual_value=_normalize_missing(spec.terminal_residual_value),
        includes_non_monetary_depreciation=spec.includes_non_monetary_depreciation,
        undiscounted_cycle_mean=undiscounted_mean,
        npv=npv,
        equivalent_annuity=ae,
        cash_flow_unit=spec.cash_flow_unit,
        annual_unit=spec.annual_unit,
    )


def _normalize_comparison_options(
    options: (
        Mapping[str, TemporalValuationResult | TemporalValuationInput]
        | Iterable[
            RotationTemporalOption | TemporalValuationResult | TemporalValuationInput
        ]
    ),
) -> list[tuple[str, TemporalValuationResult]]:
    """Normalize comparison inputs into ordered (rotation_id, result) pairs."""
    if isinstance(options, (str, bytes, bytearray)):
        raise ValueError(  # noqa: TRY004
            "options must be a collection or mapping, not text or bytes"
        )

    items: list[tuple[str, TemporalValuationResult]] = []
    seen_ids: set[str] = set()

    def _add_entry(
        rotation_id: object,
        val: TemporalValuationResult | TemporalValuationInput,
    ) -> None:
        if not isinstance(rotation_id, str) or not rotation_id.strip():
            raise ValueError("each option requires a non-empty string rotation_id")
        if rotation_id in seen_ids:
            raise ValueError(f"duplicate rotation_id in comparison: {rotation_id!r}")
        seen_ids.add(rotation_id)
        if isinstance(val, TemporalValuationInput):
            if val.rotation_id is not None and val.rotation_id != rotation_id:
                raise ValueError(
                    f"rotation_id mismatch: {rotation_id!r} vs {val.rotation_id!r}"
                )
            evaluated = evaluate_temporal_valuation(val)
            if evaluated.rotation_id is None:
                evaluated = evaluated.model_copy(update={"rotation_id": rotation_id})
            items.append((rotation_id, evaluated))
        elif isinstance(val, TemporalValuationResult):
            if val.rotation_id is not None and val.rotation_id != rotation_id:
                raise ValueError(
                    f"rotation_id mismatch: {rotation_id!r} vs {val.rotation_id!r}"
                )
            bound = (
                val
                if val.rotation_id == rotation_id
                else val.model_copy(update={"rotation_id": rotation_id})
            )
            items.append((rotation_id, bound))
        else:
            raise ValueError(  # noqa: TRY004
                "option valuation must be TemporalValuationResult or "
                f"TemporalValuationInput, got {type(val).__name__}"
            )

    if isinstance(options, Mapping):
        for rid, val in options.items():
            _add_entry(rid, val)
    else:
        for entry in options:
            if isinstance(entry, RotationTemporalOption):
                _add_entry(entry.rotation_id, entry.valuation)
            elif isinstance(entry, (TemporalValuationResult, TemporalValuationInput)):
                _add_entry(entry.rotation_id, entry)
            else:
                raise ValueError(  # noqa: TRY004
                    "comparison option must be RotationTemporalOption, "
                    "TemporalValuationResult, or TemporalValuationInput, got "
                    f"{type(entry).__name__}"
                )

    if not items:
        raise ValueError(
            "compare_rotations_common_horizon requires at least one option"
        )
    return items


def compare_rotations_common_horizon(
    options: (
        Mapping[str, TemporalValuationResult | TemporalValuationInput]
        | Iterable[
            RotationTemporalOption | TemporalValuationResult | TemporalValuationInput
        ]
    ),
) -> TemporalComparisonResult:
    """Compare rotation valuations on an equal common horizon and identical discount basis.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Raises ``ValueError`` when compared options differ in common horizon ``n``,
    ``price_basis``, ``rate_basis``, ``discount_rate``, or units, or when
    ``options`` is empty or contains duplicate ``rotation_id``s.
    """
    normalized = _normalize_comparison_options(options)
    _, ref = normalized[0]

    for rid, res in normalized[1:]:
        if res.horizon_years != ref.horizon_years:
            raise ValueError(
                f"comparison requires equal common horizon n: option {rid!r} has "
                f"n={res.horizon_years}, expected n={ref.horizon_years}"
            )
        if res.price_basis != ref.price_basis or res.rate_basis != ref.rate_basis:
            raise ValueError(
                f"comparison requires identical discount basis: option {rid!r} has "
                f"({res.price_basis!r}, {res.rate_basis!r}), expected "
                f"({ref.price_basis!r}, {ref.rate_basis!r})"
            )
        if res.discount_rate != ref.discount_rate:
            raise ValueError(
                f"comparison requires identical discount rate r: option {rid!r} has "
                f"r={res.discount_rate!r}, expected r={ref.discount_rate!r}"
            )
        if (
            res.cash_flow_unit != ref.cash_flow_unit
            or res.annual_unit != ref.annual_unit
        ):
            raise ValueError(
                f"comparison requires identical units: option {rid!r} has "
                f"({res.cash_flow_unit!r}, {res.annual_unit!r}), expected "
                f"({ref.cash_flow_unit!r}, {ref.annual_unit!r})"
            )

    options_map = dict(normalized)
    missing_entries = [
        (rid, res.npv)
        for rid, res in normalized
        if isinstance(res.npv, Missing) or isinstance(res.equivalent_annuity, Missing)
    ]
    if missing_entries:
        details = []
        for rid, maybe_miss in missing_entries:
            if isinstance(maybe_miss, Missing):
                details.append(f"{rid} ({_format_missing_detail(maybe_miss)})")
            else:
                details.append(rid)
        return TemporalComparisonResult(
            horizon_years=ref.horizon_years,
            discount_rate=ref.discount_rate,
            price_basis=ref.price_basis,
            rate_basis=ref.rate_basis,
            cash_flow_unit=ref.cash_flow_unit,
            annual_unit=ref.annual_unit,
            status="not_resolved",
            best_rotation_id=None,
            ranked_rotation_ids=(),
            tied_rotation_ids=(),
            options=options_map,
            missing=Missing(
                reason="MISSING_INPUT",
                detail="temporal comparison cannot be resolved due to missing "
                "valuation(s): " + "; ".join(details),
            ),
        )

    ranked = sorted(
        enumerate(normalized),
        key=lambda pair: (-float(pair[1][1].npv), pair[0]),  # type: ignore[arg-type]
    )
    ranked_ids = tuple(rid for _, (rid, _) in ranked)
    best_npv = ranked[0][1][1].npv
    top_tied = tuple(rid for _, (rid, res) in ranked if res.npv == best_npv)

    if len(top_tied) > 1:
        return TemporalComparisonResult(
            horizon_years=ref.horizon_years,
            discount_rate=ref.discount_rate,
            price_basis=ref.price_basis,
            rate_basis=ref.rate_basis,
            cash_flow_unit=ref.cash_flow_unit,
            annual_unit=ref.annual_unit,
            status="tied",
            best_rotation_id=None,
            ranked_rotation_ids=ranked_ids,
            tied_rotation_ids=top_tied,
            options=options_map,
            missing=Missing(
                reason="NOT_COMPUTABLE",
                detail="rotations tie at equal NPV/equivalent annuity "
                f"({best_npv!r}): {', '.join(top_tied)}",
            ),
        )

    return TemporalComparisonResult(
        horizon_years=ref.horizon_years,
        discount_rate=ref.discount_rate,
        price_basis=ref.price_basis,
        rate_basis=ref.rate_basis,
        cash_flow_unit=ref.cash_flow_unit,
        annual_unit=ref.annual_unit,
        status="resolved",
        best_rotation_id=ranked_ids[0],
        ranked_rotation_ids=ranked_ids,
        tied_rotation_ids=(),
        options=options_map,
        missing=None,
    )
