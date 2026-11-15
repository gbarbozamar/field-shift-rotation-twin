"""Agricultural-year and cycle summaries of a RothC ``CarbonBalance``. PROPOSED.

Blueprint Block 3 ("RothC by month, year and cycle"), built without modifying
``contracts/carbon_balance/``. Consumes an immutable ``CarbonBalance`` returned
by ``engine.rothc.run_rothc`` and aggregates its monthly steps into:

- agricultural years starting at ``ag_year_start.month`` (C5.3, C5.4);
- contiguous multi-year rotation cycles of ``cycle_years`` full agricultural
  years.

Conventions and ground rules:

- G1 (purity): no file, no network, no clock, no environment variable, and
  arguments are never modified.
- G4 / C3.3 / C5.5: incomplete periods emit typed ``Missing(reason="NO_COVERAGE")``
  and never fill or zero missing data; any missing monthly step within a
  complete period propagates ``Missing`` with the first missing step's reason.
- G5: caller errors raise ``TypeError`` or ``ValueError``.
- D34 / D66: holds no method constants or hardcoded domain parameters.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.carbon_balance import CarbonBalance, FlowSeries, StepValue, StockSeries
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import Missing as ResultMissing
from engine.rothc.entry import (
    ACTIVE_POOLS,
    CARBON_MODEL,
    FLOW_QUANTITIES,
    POOL_QUANTITIES,
)
from engine.rothc.pools import MONTHS_PER_YEAR

__all__ = [
    "POOL_KEYS",
    "RothcPeriodSummary",
    "summarize_rothc_ag_years",
    "summarize_rothc_cycles",
]

POOL_KEYS: tuple[str, ...] = (*ACTIVE_POOLS, "iom")


@dataclass(frozen=True)
class RothcPeriodSummary:
    """Summary of one agricultural year or multi-year cycle from a RothC ``CarbonBalance``.

    - ``period_label``: identifier of the period (agricultural year or cycle).
    - ``start``, ``end``: first and last calendar month of the period, inclusive.
    - ``total_stock``: end-of-period total soil organic carbon, or ``Missing``.
    - ``pool_stocks``: end-of-period stocks keyed by ``dpm``, ``rpm``, ``bio``,
      ``hum``, ``iom``, each a finite float or ``Missing``.
    - ``carbon_input_sum``: total carbon input over the period, or ``Missing``.
    - ``co2_sum``: total CO2 carbon respired over the period, or ``Missing``.
    """

    period_label: str
    start: YearMonth
    end: YearMonth
    total_stock: float | ResultMissing
    pool_stocks: Mapping[str, float | ResultMissing]
    carbon_input_sum: float | ResultMissing
    co2_sum: float | ResultMissing


@dataclass(frozen=True)
class _RothcSeries:
    total_stock: StockSeries
    pools: dict[str, StockSeries]
    carbon_input: FlowSeries
    co2: FlowSeries


@dataclass(frozen=True)
class _YearSlice:
    ag_year: int
    start_index: int
    end_index: int
    complete: bool


def _ym_text(month: YearMonth) -> str:
    return f"{month.year}-{month.month:02d}"


def _ag_year_of(month: YearMonth, start_month: int) -> int:
    """The agricultural year a calendar month belongs to (C5.3)."""
    return month.year if month.month >= start_month else month.year - 1


def _validate_inputs(balance: object, ag_year_start: object) -> _RothcSeries:
    if not isinstance(balance, CarbonBalance):
        raise TypeError(
            "balance: expected a CarbonBalance of contracts.carbon_balance, "
            f"got {type(balance).__name__} (G3, G5)"
        )
    if not isinstance(ag_year_start, YearMonth):
        raise TypeError(
            "ag_year_start: expected a YearMonth of contracts.inputs.site_climate, "
            f"got {type(ag_year_start).__name__} (G3, G5)"
        )
    if balance.carbon_model != CARBON_MODEL:
        raise ValueError(
            f"balance: expected carbon_model {CARBON_MODEL!r}, "
            f"got {balance.carbon_model!r} (G5)"
        )
    non_monthly = [
        index
        for index, step in enumerate(balance.total_stock.steps)
        if step.start != step.end
    ]
    if non_monthly:
        first_bad = balance.total_stock.steps[non_monthly[0]]
        raise ValueError(
            "balance: expected monthly steps (start == end), got step "
            f"{non_monthly[0]} from {_ym_text(first_bad.start)} to "
            f"{_ym_text(first_bad.end)} (G5)"
        )

    pools_by_qty = {series.quantity: series for series in balance.pools}
    missing_pools = [
        POOL_QUANTITIES[key]
        for key in POOL_KEYS
        if POOL_QUANTITIES[key] not in pools_by_qty
    ]
    if missing_pools:
        raise ValueError(
            "balance: missing expected RothC pool series: "
            + ", ".join(repr(q) for q in missing_pools)
        )

    flows_by_qty = {series.quantity: series for series in balance.flows}
    missing_flows = [
        FLOW_QUANTITIES[key]
        for key in ("carbon_input", "co2")
        if FLOW_QUANTITIES[key] not in flows_by_qty
    ]
    if missing_flows:
        raise ValueError(
            "balance: missing expected RothC flow series: "
            + ", ".join(repr(q) for q in missing_flows)
        )

    return _RothcSeries(
        total_stock=balance.total_stock,
        pools={key: pools_by_qty[POOL_QUANTITIES[key]] for key in POOL_KEYS},
        carbon_input=flows_by_qty[FLOW_QUANTITIES["carbon_input"]],
        co2=flows_by_qty[FLOW_QUANTITIES["co2"]],
    )


def _partition_ag_years(
    steps: Sequence[StepValue], start_month: int
) -> list[_YearSlice]:
    """Partition contiguous monthly steps into agricultural-year slices."""
    slices: list[_YearSlice] = []
    start_index = 0
    current_ag_year = _ag_year_of(steps[0].start, start_month)
    for index, step in enumerate(steps):
        ag_year = _ag_year_of(step.start, start_month)
        if ag_year != current_ag_year:
            slices.append(
                _YearSlice(
                    ag_year=current_ag_year,
                    start_index=start_index,
                    end_index=index,
                    complete=(index - start_index == MONTHS_PER_YEAR),
                )
            )
            start_index = index
            current_ag_year = ag_year
    end_index = len(steps)
    slices.append(
        _YearSlice(
            ag_year=current_ag_year,
            start_index=start_index,
            end_index=end_index,
            complete=(end_index - start_index == MONTHS_PER_YEAR),
        )
    )
    return slices


def _no_coverage(
    label: str,
    start: YearMonth,
    end: YearMonth,
    *,
    actual_months: int,
    expected_months: int,
) -> ResultMissing:
    return ResultMissing(
        reason="NO_COVERAGE",
        detail=(
            f"{label}: covers {actual_months} of {expected_months} required "
            f"calendar months ({_ym_text(start)} to {_ym_text(end)}) (C5.5)"
        ),
    )


def _first_missing_in_steps(
    steps: Sequence[StepValue], quantity: str, label: str
) -> ResultMissing | None:
    missing_steps = [
        (step.start, step.missing) for step in steps if step.value is None
    ]
    if not missing_steps:
        return None
    first_month, first_missing = missing_steps[0]
    assert isinstance(first_missing, InputMissing)
    first_detail = f": {first_missing.detail}" if first_missing.detail else ""
    return ResultMissing(
        reason=first_missing.reason,
        detail=(
            f"{label}: '{quantity}' is not computed: {len(missing_steps)} "
            f"month(s) missing, first at {_ym_text(first_month)} "
            f"({first_missing.reason}{first_detail})"
        ),
    )


def _period_stock(
    series: StockSeries,
    start_index: int,
    end_index: int,
    label: str,
) -> float | ResultMissing:
    steps = series.steps[start_index:end_index]
    missing = _first_missing_in_steps(steps, series.quantity, label)
    if missing is not None:
        return missing
    last_value = steps[-1].value
    if last_value is None or not math.isfinite(last_value):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{label}: '{series.quantity}' end stock is not a finite number",
        )
    return float(last_value)


def _period_flow_sum(
    series: FlowSeries,
    start_index: int,
    end_index: int,
    label: str,
) -> float | ResultMissing:
    steps = series.steps[start_index:end_index]
    missing = _first_missing_in_steps(steps, series.quantity, label)
    if missing is not None:
        return missing
    values: list[float] = []
    for step in steps:
        if step.value is None or not math.isfinite(step.value):
            return ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{label}: '{series.quantity}' has a non-finite value at "
                    f"{_ym_text(step.start)}"
                ),
            )
        values.append(float(step.value))
    total = math.fsum(values)
    if not math.isfinite(total):
        return ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"{label}: sum of '{series.quantity}' is not a finite number",
        )
    return total


def _build_incomplete_summary(
    series: _RothcSeries,
    *,
    label: str,
    start_index: int,
    end_index: int,
    expected_months: int,
) -> RothcPeriodSummary:
    steps = series.total_stock.steps
    start = steps[start_index].start
    end = steps[end_index - 1].end
    no_cov = _no_coverage(
        label,
        start,
        end,
        actual_months=end_index - start_index,
        expected_months=expected_months,
    )
    return RothcPeriodSummary(
        period_label=label,
        start=start,
        end=end,
        total_stock=no_cov,
        pool_stocks={pool: no_cov for pool in POOL_KEYS},
        carbon_input_sum=no_cov,
        co2_sum=no_cov,
    )


def _build_complete_summary(
    series: _RothcSeries,
    *,
    label: str,
    start_index: int,
    end_index: int,
) -> RothcPeriodSummary:
    steps = series.total_stock.steps
    start = steps[start_index].start
    end = steps[end_index - 1].end
    return RothcPeriodSummary(
        period_label=label,
        start=start,
        end=end,
        total_stock=_period_stock(series.total_stock, start_index, end_index, label),
        pool_stocks={
            pool: _period_stock(series.pools[pool], start_index, end_index, label)
            for pool in POOL_KEYS
        },
        carbon_input_sum=_period_flow_sum(
            series.carbon_input, start_index, end_index, label
        ),
        co2_sum=_period_flow_sum(series.co2, start_index, end_index, label),
    )


def summarize_rothc_ag_years(
    balance: CarbonBalance,
    *,
    ag_year_start: YearMonth,
) -> tuple[RothcPeriodSummary, ...]:
    """Summarize a RothC ``CarbonBalance`` by agricultural year starting at ``ag_year_start.month``.

    - Full 12-calendar-month agricultural years read end-of-year stocks (the
      12th month's step end) and sum monthly ``carbon_input`` and ``co2`` flows.
    - Incomplete leading or trailing agricultural years emit typed
      ``Missing(reason="NO_COVERAGE")`` (C5.5).
    - Any missing monthly step within a complete year propagates ``Missing``
      with the first missing step's reason (never zero).

    Raises ``TypeError`` for wrong argument types and ``ValueError`` if
    ``balance`` is not a monthly RothC ``CarbonBalance`` (G5).
    """
    series = _validate_inputs(balance, ag_year_start)
    slices = _partition_ag_years(series.total_stock.steps, ag_year_start.month)
    summaries: list[RothcPeriodSummary] = []
    for item in slices:
        label = f"ag_year_{item.ag_year}"
        if not item.complete:
            summaries.append(
                _build_incomplete_summary(
                    series,
                    label=label,
                    start_index=item.start_index,
                    end_index=item.end_index,
                    expected_months=MONTHS_PER_YEAR,
                )
            )
        else:
            summaries.append(
                _build_complete_summary(
                    series,
                    label=label,
                    start_index=item.start_index,
                    end_index=item.end_index,
                )
            )
    return tuple(summaries)


def summarize_rothc_cycles(
    balance: CarbonBalance,
    *,
    ag_year_start: YearMonth,
    cycle_years: int,
) -> tuple[RothcPeriodSummary, ...]:
    """Summarize a RothC ``CarbonBalance`` into contiguous ``cycle_years``-year rotation cycles.

    Each complete cycle spans ``cycle_years`` contiguous full agricultural years
    (``cycle_years * 12`` calendar months) starting at ``ag_year_start.month``,
    reading cycle-end stocks and summing monthly flows. Any incomplete leading
    months or partial tail cycle emits typed ``Missing(reason="NO_COVERAGE")``.
    Any missing monthly step within a complete cycle propagates ``Missing`` with
    the first missing step's reason (never zero).

    Raises ``TypeError`` for wrong argument types and ``ValueError`` when
    ``cycle_years < 1`` or ``balance`` is not a monthly RothC ``CarbonBalance`` (G5).
    """
    series = _validate_inputs(balance, ag_year_start)
    if isinstance(cycle_years, bool) or not isinstance(cycle_years, int):
        raise TypeError(
            "cycle_years: expected an integer >= 1, got "
            f"{type(cycle_years).__name__} (G3, G5)"
        )
    if cycle_years < 1:
        raise ValueError(
            f"cycle_years: expected an integer >= 1, got {cycle_years} (G5)"
        )

    slices = _partition_ag_years(series.total_stock.steps, ag_year_start.month)
    expected_cycle_months = cycle_years * MONTHS_PER_YEAR
    summaries: list[RothcPeriodSummary] = []

    first_step_month = series.total_stock.steps[slices[0].start_index].start.month
    if not slices[0].complete and first_step_month != ag_year_start.month:
        leading = slices[0]
        summaries.append(
            _build_incomplete_summary(
                series,
                label=f"ag_year_{leading.ag_year}",
                start_index=leading.start_index,
                end_index=leading.end_index,
                expected_months=expected_cycle_months,
            )
        )
        remaining = slices[1:]
    else:
        remaining = slices

    complete_years = [item for item in remaining if item.complete]
    trailing_incomplete = [item for item in remaining if not item.complete]

    full_cycles = len(complete_years) // cycle_years
    for index in range(full_cycles):
        offset = index * cycle_years
        chunk = complete_years[offset : offset + cycle_years]
        summaries.append(
            _build_complete_summary(
                series,
                label=f"cycle_{index + 1}",
                start_index=chunk[0].start_index,
                end_index=chunk[-1].end_index,
            )
        )

    tail_slices = [*complete_years[full_cycles * cycle_years :], *trailing_incomplete]
    if tail_slices:
        summaries.append(
            _build_incomplete_summary(
                series,
                label=f"cycle_{full_cycles + 1}",
                start_index=tail_slices[0].start_index,
                end_index=tail_slices[-1].end_index,
                expected_months=expected_cycle_months,
            )
        )

    return tuple(summaries)
