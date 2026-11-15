"""Soil degradation analytical valuation, incremental conservation cost,
financial tail risk, and monetary Value of Information (VoI).

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Built by Frontier Unit F-19 (``l2/economics-soil-degradation-voi``). Pure Python
3.12 stdlib + ``contracts.*`` + ``pydantic``: no network calls, no hardcoded
prices, bulk densities, nutrient costs, land values, or fictitious dollar
priors. All parameters are supplied explicitly by the caller; missing inputs
stay typed ``Missing`` values (C3.1, C3.2 of ``contracts/CONVENTIONS.md``)
rather than defaults or zero stand-ins.
"""

from __future__ import annotations

import math
import numbers
import operator
from collections.abc import Mapping, Sequence
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, FiniteFloat, model_validator

from contracts.inputs.common import Missing, ReasonCode

SPEC_STATUS = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"

# Exact SI geometric factor: 1 ha = 10,000 m^2 and 1 mm = 0.001 m, so a 1 mm
# soil layer over 1 ha has volume 10 m^3 ha-1 and mass 10 * bulk_density Mg ha-1.
MM_TO_MG_HA_FACTOR = 10.0

UNIT_MM_PER_YEAR = "mm yr-1"
UNIT_MG_PER_HA_YR = "Mg ha-1 yr-1"
UNIT_MG_PER_M3 = "Mg m-3"
UNIT_USD_PER_HA_YR = "USD ha-1 yr-1"
UNIT_USD_PER_MG = "USD Mg-1"
UNIT_USD_PER_T = "USD t-1"
UNIT_T_PER_HA = "t ha-1"
UNIT_USD_PER_HA = "USD ha-1"

ValuationMethod = Literal[
    "nutrient_replacement",
    "productivity_loss",
    "soil_years_land_value",
]
VALUATION_METHODS: tuple[ValuationMethod, ...] = get_args(ValuationMethod)
MethodMaturity = Literal["ANALYTICAL_PROXY", "HYPOTHESIS"]

DEFAULT_QUALITATIVE_VOI_PRIORITY = "QUALITATIVE_PRIORITY_FALLBACK"
_PROBABILITY_TOLERANCE = 1e-9
_FLOAT_NOISE_TOLERANCE = 1e-12


class _FrontierModel(BaseModel):
    """Strict, frozen Pydantic base model for F-19 economics structures."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


def _finite_real(value: object, what: str) -> float:
    """Validate a finite real number (rejecting booleans, text, NaN, inf)."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{what}: expected a finite real number")  # noqa: TRY004
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what}: expected a finite number")
    return number


def _non_negative_real(value: object, what: str) -> float:
    number = _finite_real(value, what)
    if number < 0.0:
        raise ValueError(f"{what}: must be non-negative")
    return number


def _positive_real(value: object, what: str) -> float:
    number = _finite_real(value, what)
    if number <= 0.0:
        raise ValueError(f"{what}: must be strictly positive")
    return number


def _positive_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{what}: expected a positive integer")  # noqa: TRY004
    number = operator.index(value)
    if number <= 0:
        raise ValueError(f"{what}: must be strictly positive")
    return number


def _non_blank_str(value: object, what: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{what}: expected a non-blank string")
    return value


def _strict_bool(value: object, what: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{what}: expected a boolean")  # noqa: TRY004
    return value


# ---------------------------------------------------------------------------
# 1. Soil-depth conversion helpers
# ---------------------------------------------------------------------------


def mass_per_mm_Mg_ha(bulk_density_Mg_m3: float) -> float:
    """Return the soil mass (Mg ha-1) of a 1 mm layer at ``bulk_density_Mg_m3``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    1 mm over 1 ha equals 10 m^3 ha-1, so mass = ``10 * rho_b`` Mg ha-1.
    """
    rho_b = _positive_real(bulk_density_Mg_m3, "bulk_density_Mg_m3")
    return MM_TO_MG_HA_FACTOR * rho_b


def erosion_mm_per_year(
    soil_loss_Mg_ha_yr: float,
    bulk_density_Mg_m3: float,
) -> float:
    """Convert annual soil loss (Mg ha-1 yr-1) to surface lowering (mm yr-1).

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """
    loss = _non_negative_real(soil_loss_Mg_ha_yr, "soil_loss_Mg_ha_yr")
    return loss / mass_per_mm_Mg_ha(bulk_density_Mg_m3)


# ---------------------------------------------------------------------------
# 2. Mutually exclusive, non-additive soil degradation analytical valuations
# ---------------------------------------------------------------------------


class SoilDegradationValuation(_FrontierModel):
    """Single-method analytical soil degradation valuation.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Kept strictly separate from observed financial cash flow
    (``not_observed_cash_outflow=True``). The three analytical methods
    (``nutrient_replacement``, ``productivity_loss``, ``soil_years_land_value``)
    are mutually exclusive and non-additive; attempting to add instances raises
    ``ValueError``.
    """

    method: ValuationMethod
    method_maturity: MethodMaturity
    value_usd_ha_yr: FiniteFloat
    unit: str = UNIT_USD_PER_HA_YR
    not_observed_cash_outflow: Literal[True] = True
    fertilizer_does_not_restore_structure_or_soc: Literal[True] = True
    mutually_exclusive_non_additive: Literal[True] = True
    already_deducted_in_revenue: Literal[False] = False
    erosion_rate_mm_yr: FiniteFloat | None = None
    remaining_soil_years: FiniteFloat | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> SoilDegradationValuation:
        if self.unit != UNIT_USD_PER_HA_YR:
            raise ValueError(f"unit: expected {UNIT_USD_PER_HA_YR!r}")
        if self.value_usd_ha_yr < 0.0:
            raise ValueError("value_usd_ha_yr: must be non-negative")
        if (
            self.method == "soil_years_land_value"
            and self.method_maturity != "HYPOTHESIS"
        ):
            raise ValueError(
                "soil_years_land_value must carry method_maturity='HYPOTHESIS'"
            )
        if (
            self.method != "soil_years_land_value"
            and self.method_maturity != "ANALYTICAL_PROXY"
        ):
            raise ValueError(
                f"{self.method} must carry method_maturity='ANALYTICAL_PROXY'"
            )
        if self.erosion_rate_mm_yr is not None and self.erosion_rate_mm_yr < 0.0:
            raise ValueError("erosion_rate_mm_yr: must be non-negative")
        if self.remaining_soil_years is not None and self.remaining_soil_years <= 0.0:
            raise ValueError("remaining_soil_years: must be strictly positive")
        return self

    def __add__(self, other: object) -> SoilDegradationValuation:
        raise ValueError(
            "Soil degradation analytical valuation methods are mutually exclusive "
            "and non-additive; summing valuation methods is prohibited"
        )

    def __radd__(self, other: object) -> SoilDegradationValuation:
        raise ValueError(
            "Soil degradation analytical valuation methods are mutually exclusive "
            "and non-additive; summing valuation methods is prohibited"
        )


def sum_valuation_methods(valuations: Sequence[SoilDegradationValuation]) -> float:
    """Explicitly refuse summing soil degradation valuation methods.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """
    _ = valuations
    raise ValueError(
        "Soil degradation analytical valuation methods are mutually exclusive "
        "and non-additive; summing or combining methods is prohibited"
    )


def value_nutrient_replacement(
    *,
    soil_loss_Mg_ha_yr: float,
    nutrient_kg_per_Mg: Mapping[str, float],
    nutrient_price_usd_per_kg: Mapping[str, float],
    enrichment_ratio: float = 1.0,
) -> SoilDegradationValuation:
    """Analytical replacement cost of N/P/K lost in eroded soil.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Always notes ``not_observed_cash_outflow=True`` and
    ``fertilizer_does_not_restore_structure_or_soc=True``.
    """
    loss = _non_negative_real(soil_loss_Mg_ha_yr, "soil_loss_Mg_ha_yr")
    er = _positive_real(enrichment_ratio, "enrichment_ratio")
    if not isinstance(nutrient_kg_per_Mg, Mapping) or len(nutrient_kg_per_Mg) == 0:
        raise ValueError("nutrient_kg_per_Mg: must be a non-empty mapping")
    if not isinstance(nutrient_price_usd_per_kg, Mapping):
        raise ValueError("nutrient_price_usd_per_kg: must be a mapping")  # noqa: TRY004

    per_Mg_cost = 0.0
    for nutrient, raw_kg in nutrient_kg_per_Mg.items():
        name = _non_blank_str(nutrient, "nutrient name")
        kg_per_Mg = _non_negative_real(raw_kg, f"nutrient_kg_per_Mg[{name!r}]")
        if name not in nutrient_price_usd_per_kg:
            raise ValueError(
                f"nutrient_price_usd_per_kg: missing price for nutrient {name!r}"
            )
        price = _non_negative_real(
            nutrient_price_usd_per_kg[name], f"nutrient_price_usd_per_kg[{name!r}]"
        )
        per_Mg_cost += kg_per_Mg * price

    value = loss * er * per_Mg_cost
    return SoilDegradationValuation(
        method="nutrient_replacement",
        method_maturity="ANALYTICAL_PROXY",
        value_usd_ha_yr=value,
    )


def value_productivity_loss(
    *,
    annual_yield_loss_t_ha_yr: float,
    crop_price_usd_per_t: float,
    additional_input_cost_usd_ha_yr: float = 0.0,
    already_deducted_in_revenue: bool = False,
) -> SoilDegradationValuation:
    """Analytical productivity-loss valuation from soil degradation.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Refuses (``ValueError``) when ``already_deducted_in_revenue=True`` to
    prevent double-counting yield decline already subtracted from revenues.
    """
    if _strict_bool(already_deducted_in_revenue, "already_deducted_in_revenue"):
        raise ValueError(
            "cannot apply productivity_loss valuation when yield decline is "
            "already deducted in crop revenues (already_deducted_in_revenue=True)"
        )
    yield_loss = _non_negative_real(
        annual_yield_loss_t_ha_yr, "annual_yield_loss_t_ha_yr"
    )
    price = _non_negative_real(crop_price_usd_per_t, "crop_price_usd_per_t")
    extra_cost = _non_negative_real(
        additional_input_cost_usd_ha_yr, "additional_input_cost_usd_ha_yr"
    )

    value = yield_loss * price + extra_cost
    return SoilDegradationValuation(
        method="productivity_loss",
        method_maturity="ANALYTICAL_PROXY",
        value_usd_ha_yr=value,
    )


def value_soil_years_land_value(
    *,
    soil_loss_Mg_ha_yr: float,
    bulk_density_Mg_m3: float,
    measured_soil_depth_mm: float | None,
    land_value_usd_ha: float,
    minimum_functional_depth_mm: float = 0.0,
    already_deducted_in_revenue: bool = False,
) -> SoilDegradationValuation | Missing:
    """HYPOTHESIS capitalization of remaining productive soil-years into land value.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Requires measured soil depth (returns ``Missing(reason="MISSING_INPUT")`` if
    ``measured_soil_depth_mm is None``). Refuses (``ValueError``) if
    ``already_deducted_in_revenue=True`` to prevent double-counting.
    """
    if _strict_bool(already_deducted_in_revenue, "already_deducted_in_revenue"):
        raise ValueError(
            "cannot apply soil_years_land_value capitalization when yield decline "
            "is already deducted in crop revenues (already_deducted_in_revenue=True)"
        )
    mm_per_yr = erosion_mm_per_year(soil_loss_Mg_ha_yr, bulk_density_Mg_m3)
    land_value = _non_negative_real(land_value_usd_ha, "land_value_usd_ha")
    min_depth = _non_negative_real(
        minimum_functional_depth_mm, "minimum_functional_depth_mm"
    )

    if measured_soil_depth_mm is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                "measured_soil_depth_mm is required for soil_years_land_value "
                "(HYPOTHESIS)"
            ),
        )

    depth = _positive_real(measured_soil_depth_mm, "measured_soil_depth_mm")
    if depth <= min_depth:
        raise ValueError(
            "measured_soil_depth_mm must exceed minimum_functional_depth_mm"
        )

    if mm_per_yr == 0.0:
        return SoilDegradationValuation(
            method="soil_years_land_value",
            method_maturity="HYPOTHESIS",
            value_usd_ha_yr=0.0,
            erosion_rate_mm_yr=0.0,
            remaining_soil_years=None,
        )

    usable_depth_mm = depth - min_depth
    remaining_years = usable_depth_mm / mm_per_yr
    annual_cost = land_value / remaining_years
    return SoilDegradationValuation(
        method="soil_years_land_value",
        method_maturity="HYPOTHESIS",
        value_usd_ha_yr=annual_cost,
        erosion_rate_mm_yr=mm_per_yr,
        remaining_soil_years=remaining_years,
    )


# ---------------------------------------------------------------------------
# 3. Incremental conservation cost
# ---------------------------------------------------------------------------


class SoilConservationCost(_FrontierModel):
    """Incremental margin foregone per tonne of soil loss avoided.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Tagged ``incremental_indicator_not_universal_soil_price=True``.
    """

    cost_usd_per_Mg: FiniteFloat
    unit: str = UNIT_USD_PER_MG
    margin_delta_usd_ha_yr: FiniteFloat
    soil_loss_delta_Mg_ha_yr: FiniteFloat
    horizon_years: int
    incremental_indicator_not_universal_soil_price: Literal[True] = True
    is_win_win: bool

    @model_validator(mode="after")
    def _check_fields(self) -> SoilConservationCost:
        if self.unit != UNIT_USD_PER_MG:
            raise ValueError(f"unit: expected {UNIT_USD_PER_MG!r}")
        if self.horizon_years <= 0:
            raise ValueError("horizon_years: must be strictly positive")
        if self.soil_loss_delta_Mg_ha_yr == 0.0:
            raise ValueError("soil_loss_delta_Mg_ha_yr: must be non-zero")
        return self


def soil_conservation_cost(
    margin_a: float,
    margin_b: float,
    loss_a: float,
    loss_b: float,
    horizon_a: int,
    horizon_b: int,
) -> SoilConservationCost | Missing:
    """Incremental conservation cost ``(margin_a - margin_b) / (loss_a - loss_b)``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Requires ``horizon_a == horizon_b`` (else ``ValueError``). Returns
    ``Missing(reason="NOT_COMPUTABLE")`` when ``abs(loss_a - loss_b) == 0``.
    """
    m_a = _finite_real(margin_a, "margin_a")
    m_b = _finite_real(margin_b, "margin_b")
    l_a = _non_negative_real(loss_a, "loss_a")
    l_b = _non_negative_real(loss_b, "loss_b")
    h_a = _positive_int(horizon_a, "horizon_a")
    h_b = _positive_int(horizon_b, "horizon_b")

    if h_a != h_b:
        raise ValueError(
            f"horizon_a ({h_a}) and horizon_b ({h_b}) must be equal for "
            "incremental conservation cost comparison"
        )

    loss_delta = l_a - l_b
    if abs(loss_delta) == 0.0:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                "abs(loss_a - loss_b) == 0: incremental conservation cost per "
                "tonne is undefined when both rotations have identical soil loss"
            ),
        )

    margin_delta = m_a - m_b
    cost = margin_delta / loss_delta
    return SoilConservationCost(
        cost_usd_per_Mg=cost,
        margin_delta_usd_ha_yr=margin_delta,
        soil_loss_delta_Mg_ha_yr=loss_delta,
        horizon_years=h_a,
        is_win_win=cost < 0.0,
    )


# ---------------------------------------------------------------------------
# 4. Financial tail-risk metrics (CVaR & break-even price / yield)
# ---------------------------------------------------------------------------


class CvarResult(_FrontierModel):
    """Empirical Conditional Value at Risk (expected shortfall) of worst years.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    cvar_usd_ha_yr: FiniteFloat
    var_threshold_usd_ha_yr: FiniteFloat
    worst_year_margin_usd_ha_yr: FiniteFloat
    mean_margin_usd_ha_yr: FiniteFloat
    tail_fraction: FiniteFloat
    year_count: int
    effective_tail_years: FiniteFloat
    unit: str = UNIT_USD_PER_HA_YR
    not_a_probability_forecast: Literal[True] = True

    @model_validator(mode="after")
    def _check_fields(self) -> CvarResult:
        if self.unit != UNIT_USD_PER_HA_YR:
            raise ValueError(f"unit: expected {UNIT_USD_PER_HA_YR!r}")
        if not (0.0 < self.tail_fraction <= 1.0):
            raise ValueError("tail_fraction: must lie in (0, 1]")
        if self.year_count <= 0:
            raise ValueError("year_count: must be strictly positive")
        return self


def compute_cvar_worst_years(
    annual_margins: Sequence[float],
    tail_fraction: float,
) -> CvarResult:
    """Compute empirical CVaR over the worst ``tail_fraction`` of annual margins.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Uses exact empirical expected shortfall weighting over the sorted ascending
    annual margins: when ``tail_fraction * N`` is an integer ``k``, CVaR equals
    the arithmetic mean of the ``k`` worst years; for fractional ``tail_fraction * N``,
    uses exact piecewise-linear tail weighting so monotonicity holds for all ``N``.
    """
    if isinstance(annual_margins, (str, bytes, bytearray)) or not isinstance(
        annual_margins, Sequence
    ):
        raise ValueError(  # noqa: TRY004
            "annual_margins: must be a sequence of finite real numbers"
        )
    if len(annual_margins) == 0:
        raise ValueError("annual_margins: must be non-empty")

    alpha = _finite_real(tail_fraction, "tail_fraction")
    if not (0.0 < alpha <= 1.0):
        raise ValueError("tail_fraction: must lie in (0, 1]")

    margins = [
        _finite_real(val, f"annual_margins[{idx}]")
        for idx, val in enumerate(annual_margins)
    ]
    margins.sort()
    n = len(margins)
    effective_k = alpha * n
    whole = math.floor(effective_k)
    rem = effective_k - whole

    if effective_k <= 1.0:
        # When tail covers at most one observation, expected shortfall is the worst year.
        cvar = margins[0]
        var_idx = 0
    else:
        weighted_sum = sum(margins[:whole])
        if rem > 0.0 and whole < n:
            weighted_sum += rem * margins[whole]
        cvar = weighted_sum / effective_k
        var_idx = min(n - 1, math.ceil(effective_k) - 1)

    return CvarResult(
        cvar_usd_ha_yr=cvar,
        var_threshold_usd_ha_yr=margins[var_idx],
        worst_year_margin_usd_ha_yr=margins[0],
        mean_margin_usd_ha_yr=sum(margins) / n,
        tail_fraction=alpha,
        year_count=n,
        effective_tail_years=effective_k,
    )


class BreakEvenPrice(_FrontierModel):
    """Break-even crop price (USD t-1) for a declared cost, yield, and target margin.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    break_even_price_usd_per_t: FiniteFloat
    target_margin_usd_ha: FiniteFloat
    unit: str = UNIT_USD_PER_T


class BreakEvenYield(_FrontierModel):
    """Break-even crop yield (t ha-1) for a declared cost, price, and target margin.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    """

    break_even_yield_t_ha: FiniteFloat
    target_margin_usd_ha: FiniteFloat
    unit: str = UNIT_T_PER_HA


def compute_break_even_price(
    cost_usd_ha: float,
    yield_t_ha: float,
    *,
    target_margin_usd_ha: float = 0.0,
) -> BreakEvenPrice | Missing:
    """Compute break-even price ``(cost + target_margin) / yield``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Returns ``Missing(reason="NOT_COMPUTABLE")`` when ``yield_t_ha == 0``.
    """
    cost = _finite_real(cost_usd_ha, "cost_usd_ha")
    yld = _non_negative_real(yield_t_ha, "yield_t_ha")
    target = _finite_real(target_margin_usd_ha, "target_margin_usd_ha")

    if yld == 0.0:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="yield_t_ha == 0: break-even price is undefined for zero yield",
        )
    return BreakEvenPrice(
        break_even_price_usd_per_t=(cost + target) / yld,
        target_margin_usd_ha=target,
    )


def compute_break_even_yield(
    cost_usd_ha: float,
    price_usd_t: float,
    *,
    target_margin_usd_ha: float = 0.0,
) -> BreakEvenYield | Missing:
    """Compute break-even yield ``(cost + target_margin) / price``.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
    Returns ``Missing(reason="NOT_COMPUTABLE")`` when ``price_usd_t == 0``.
    """
    cost = _finite_real(cost_usd_ha, "cost_usd_ha")
    price = _non_negative_real(price_usd_t, "price_usd_t")
    target = _finite_real(target_margin_usd_ha, "target_margin_usd_ha")

    if price == 0.0:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="price_usd_t == 0: break-even yield is undefined for zero price",
        )
    return BreakEvenYield(
        break_even_yield_t_ha=(cost + target) / price,
        target_margin_usd_ha=target,
    )


# ---------------------------------------------------------------------------
# 5. Monetary Value of Information (EVPI & EVSI)
# ---------------------------------------------------------------------------


class VoiResult(_FrontierModel):
    """Monetary Value of Information (EVPI, EVSI, net EVSI) or typed Missing fallback.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Numeric ``evpi_usd_ha``, ``evsi_usd_ha``, and ``net_evsi_usd_ha`` are
    populated ONLY when all five explicit Bayesian decision inputs are
    provided; otherwise all dollar outputs remain ``None`` with
    ``missing=Missing(reason="MISSING_INPUT", ...)`` and a qualitative fallback
    in ``qualitative_priority`` (never fictitious dollars).
    """

    evpi_usd_ha: FiniteFloat | None
    evsi_usd_ha: FiniteFloat | None
    net_evsi_usd_ha: FiniteFloat | None
    measurement_cost_usd_ha: FiniteFloat | None
    expected_utility_without_info_usd_ha: FiniteFloat | None = None
    optimal_prior_action: str | None = None
    measurement_worthwhile: bool | None = None
    qualitative_priority: str | None = None
    missing: Missing | None = None
    unit: str = UNIT_USD_PER_HA

    @property
    def reason(self) -> ReasonCode | None:
        return self.missing.reason if self.missing is not None else None

    @property
    def detail(self) -> str | None:
        return self.missing.detail if self.missing is not None else None

    @model_validator(mode="after")
    def _check_consistency(self) -> VoiResult:
        if self.unit != UNIT_USD_PER_HA:
            raise ValueError(f"unit: expected {UNIT_USD_PER_HA!r}")
        if (
            self.measurement_cost_usd_ha is not None
            and self.measurement_cost_usd_ha < 0.0
        ):
            raise ValueError("measurement_cost_usd_ha: must be non-negative")

        monetary_fields = (self.evpi_usd_ha, self.evsi_usd_ha, self.net_evsi_usd_ha)
        all_none = all(v is None for v in monetary_fields)
        all_present = all(v is not None for v in monetary_fields)
        if not (all_none or all_present):
            raise ValueError(
                "evpi_usd_ha, evsi_usd_ha, and net_evsi_usd_ha must be all set or all None"
            )
        if all_none:
            if self.missing is None:
                raise ValueError(
                    "missing monetary VoI must carry Missing(reason=...) (C3.1)"
                )
            if (
                self.qualitative_priority is None
                or self.qualitative_priority.strip() == ""
            ):
                raise ValueError(
                    "missing monetary VoI must provide a qualitative_priority fallback"
                )
            return self

        if self.missing is not None:
            raise ValueError("present monetary VoI cannot carry a missing part")
        if self.measurement_cost_usd_ha is None:
            raise ValueError("present monetary VoI requires measurement_cost_usd_ha")
        assert self.evpi_usd_ha is not None
        assert self.evsi_usd_ha is not None
        assert self.net_evsi_usd_ha is not None
        if self.evpi_usd_ha < 0.0 or self.evsi_usd_ha < 0.0:
            raise ValueError("EVPI and EVSI must be non-negative")
        if self.evsi_usd_ha > self.evpi_usd_ha + _PROBABILITY_TOLERANCE:
            raise ValueError("EVSI cannot exceed EVPI")
        expected_net = self.evsi_usd_ha - self.measurement_cost_usd_ha
        if abs(self.net_evsi_usd_ha - expected_net) > _PROBABILITY_TOLERANCE:
            raise ValueError(
                "net_evsi_usd_ha must equal evsi_usd_ha - measurement_cost"
            )
        return self


def _validate_probability_distribution(
    dist: Mapping[str, float],
    what: str,
) -> dict[str, float]:
    if not isinstance(dist, Mapping) or len(dist) == 0:
        raise ValueError(f"{what}: must be a non-empty mapping")
    cleaned: dict[str, float] = {}
    total = 0.0
    for key, raw_prob in dist.items():
        name = _non_blank_str(key, f"{what} key")
        prob = _non_negative_real(raw_prob, f"{what}[{name!r}]")
        if prob > 1.0:
            raise ValueError(f"{what}[{name!r}]: probability cannot exceed 1.0")
        cleaned[name] = prob
        total += prob
    if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
        raise ValueError(f"{what}: probabilities must sum to 1.0 (got {total})")
    return cleaned


def compute_evpi_and_evsi(
    economic_utility_matrix: Mapping[str, Mapping[str, float]] | None = None,
    state_prior: Mapping[str, float] | None = None,
    measurement_error_likelihood: Mapping[str, Mapping[str, float]] | None = None,
    admissible_actions: Sequence[str] | None = None,
    measurement_cost_usd_ha: float | None = None,
    *,
    qualitative_priority: str | None = None,
) -> VoiResult:
    """Compute exact Bayesian EVPI, EVSI, and net EVSI in USD ha-1.

    PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

    Returns numeric ``evpi_usd_ha``, ``evsi_usd_ha``, and ``net_evsi_usd_ha``
    ONLY when all five inputs (``economic_utility_matrix``, ``state_prior``,
    ``measurement_error_likelihood``, ``admissible_actions``, and
    ``measurement_cost_usd_ha``) are explicitly provided. If any is ``None``,
    returns a ``VoiResult`` carrying ``Missing(reason="MISSING_INPUT")`` and a
    ``qualitative_priority`` fallback (never fictitious dollars).
    """
    if qualitative_priority is not None:
        _non_blank_str(qualitative_priority, "qualitative_priority")

    validated_cost: float | None = None
    if measurement_cost_usd_ha is not None:
        validated_cost = _non_negative_real(
            measurement_cost_usd_ha, "measurement_cost_usd_ha"
        )

    missing_inputs: list[str] = []
    if economic_utility_matrix is None:
        missing_inputs.append("economic_utility_matrix")
    if state_prior is None:
        missing_inputs.append("state_prior")
    if measurement_error_likelihood is None:
        missing_inputs.append("measurement_error_likelihood")
    if admissible_actions is None:
        missing_inputs.append("admissible_actions")
    if measurement_cost_usd_ha is None:
        missing_inputs.append("measurement_cost_usd_ha")

    if missing_inputs:
        return VoiResult(
            evpi_usd_ha=None,
            evsi_usd_ha=None,
            net_evsi_usd_ha=None,
            measurement_cost_usd_ha=validated_cost,
            qualitative_priority=(
                qualitative_priority
                if qualitative_priority is not None
                else DEFAULT_QUALITATIVE_VOI_PRIORITY
            ),
            missing=Missing(
                reason="MISSING_INPUT",
                detail=(
                    "cannot compute monetary VoI without explicit inputs: "
                    + ", ".join(missing_inputs)
                ),
            ),
        )

    assert economic_utility_matrix is not None
    assert state_prior is not None
    assert measurement_error_likelihood is not None
    assert admissible_actions is not None
    assert validated_cost is not None

    if isinstance(admissible_actions, (str, bytes, bytearray)) or not isinstance(
        admissible_actions, Sequence
    ):
        raise ValueError(  # noqa: TRY004
            "admissible_actions: must be a sequence of action names"
        )
    if len(admissible_actions) == 0:
        raise ValueError("admissible_actions: must be non-empty")
    actions: list[str] = []
    seen_actions: set[str] = set()
    for idx, raw_action in enumerate(admissible_actions):
        action = _non_blank_str(raw_action, f"admissible_actions[{idx}]")
        if action in seen_actions:
            raise ValueError(f"admissible_actions: duplicate action {action!r}")
        seen_actions.add(action)
        actions.append(action)

    prior = _validate_probability_distribution(state_prior, "state_prior")
    states = tuple(prior)

    if not isinstance(economic_utility_matrix, Mapping):
        raise ValueError("economic_utility_matrix: must be a mapping")  # noqa: TRY004
    utility: dict[str, dict[str, float]] = {}
    for action in actions:
        if action not in economic_utility_matrix:
            raise ValueError(
                f"economic_utility_matrix: missing row for action {action!r}"
            )
        row = economic_utility_matrix[action]
        if not isinstance(row, Mapping):
            raise ValueError(  # noqa: TRY004
                f"economic_utility_matrix[{action!r}]: must be a state mapping"
            )
        cleaned_row: dict[str, float] = {}
        for state in states:
            if state not in row:
                raise ValueError(
                    f"economic_utility_matrix[{action!r}]: missing state {state!r}"
                )
            cleaned_row[state] = _finite_real(
                row[state], f"economic_utility_matrix[{action!r}][{state!r}]"
            )
        utility[action] = cleaned_row

    if not isinstance(measurement_error_likelihood, Mapping):
        raise ValueError(  # noqa: TRY004
            "measurement_error_likelihood: must be a mapping"
        )
    if set(measurement_error_likelihood) != set(states):
        raise ValueError(
            "measurement_error_likelihood: state keys must match state_prior"
        )
    likelihood: dict[str, dict[str, float]] = {}
    signals_seen: dict[str, None] = {}
    for state in states:
        signal_dist = _validate_probability_distribution(
            measurement_error_likelihood[state],
            f"measurement_error_likelihood[{state!r}]",
        )
        likelihood[state] = signal_dist
        for signal in signal_dist:
            signals_seen.setdefault(signal, None)
    signals = tuple(signals_seen)

    # Prior expected utility per action and optimal prior action.
    eu_by_action = {
        action: sum(prior[state] * utility[action][state] for state in states)
        for action in actions
    }
    optimal_action = max(actions, key=lambda a: eu_by_action[a])
    eu_prior = eu_by_action[optimal_action]

    # Expected utility with perfect information.
    eu_perfect = sum(
        prior[state] * max(utility[action][state] for action in actions)
        for state in states
    )
    evpi = eu_perfect - eu_prior
    if -_FLOAT_NOISE_TOLERANCE <= evpi < 0.0:
        evpi = 0.0

    # Expected utility with sample information: sum_z max_a sum_s P(z|s) P(s) U(a, s).
    eu_sample = 0.0
    for signal in signals:
        best_signal_contribution = max(
            sum(
                likelihood[state].get(signal, 0.0)
                * prior[state]
                * utility[action][state]
                for state in states
            )
            for action in actions
        )
        eu_sample += best_signal_contribution

    evsi = eu_sample - eu_prior
    if -_FLOAT_NOISE_TOLERANCE <= evsi < 0.0:
        evsi = 0.0
    if evpi < evsi <= evpi + _FLOAT_NOISE_TOLERANCE:
        evsi = evpi

    net_evsi = evsi - validated_cost
    return VoiResult(
        evpi_usd_ha=evpi,
        evsi_usd_ha=evsi,
        net_evsi_usd_ha=net_evsi,
        measurement_cost_usd_ha=validated_cost,
        expected_utility_without_info_usd_ha=eu_prior,
        optimal_prior_action=optimal_action,
        measurement_worthwhile=net_evsi > 0.0,
        qualitative_priority=qualitative_priority,
        missing=None,
    )
