"""Contract "CarbonBalance" (blueprint section 5). PROPOSED (blueprint section 3.7).

What one carbon model returns for one rotation of one field: the carbon
stocks over the horizon, the flows of each step, and the three trend values
of C1.6 for ``soil_carbon_trend``. EP5 ``run_amg`` and EP6 ``run_rothc``
return it (contracts/ENTRYPOINTS.md); the same model serves both.

Producers: Engines (AMG, ``engine/amg/``) and Platform, sub-lane L2b (RothC,
``engine/rothc/``). Consumers: the runner (``api/``) and the interface.

This module fixes structure only: which parts exist, what shape each takes
and how an absence travels. It names no pool, no flow and no unit of a
carbon model; those arrive with the document and are listed in ``README.md``
in this folder. Every choice here is PROPOSED.

The shared parts are imported, never copied:

- from ``contracts.inputs``: ``Value`` and ``Missing`` (C1.1, C2, C3, C4),
  the series header and item of ``SiteClimate`` and ``YearMonth`` (C5.1);
- from ``contracts.carbon_forcing``: ``ForcingHorizon``, so the horizon of
  the balance is written as the horizon of the forcing it was run on;
- from ``contracts.results``: ``SoilCarbonTrend`` (C1.5, C1.6) and the
  identifiers of the carbon models (D1 of issue #77) and of the three
  computations.

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import model_validator

from contracts.carbon_forcing.models import ForcingHorizon
from contracts.inputs.common import ContractModel, NonEmptyStr, QuantityId, Value

# ``_SeriesItem`` and ``_SeriesHeader`` are private names of
# ``contracts/inputs/site_climate.py``; they are imported, not copied, as
# ``contracts/carbon_forcing/models.py`` does.
from contracts.inputs.site_climate import YearMonth, _SeriesHeader, _SeriesItem
from contracts.results.models import TREND_COMPUTATIONS, CarbonModel, SoilCarbonTrend


def _month_index(month: YearMonth) -> int:
    return month.year * 12 + (month.month - 1)


class StepValue(_SeriesItem):
    """One value of one step: a number or missing with its reason (C3.1).

    ``start`` and ``end`` are the first and the last month of the step,
    inclusive (C5.1). An annual step of AMG covers the twelve months of one
    agricultural year (C5.3); a monthly step of RothC covers one month
    (``start`` equals ``end``). For a stock, the value is the stock at the
    end of the step; for a flow, the amount over the step.
    """

    start: YearMonth
    end: YearMonth

    @model_validator(mode="after")
    def _ordered(self) -> StepValue:
        if _month_index(self.end) < _month_index(self.start):
            raise ValueError("step: ends before it starts")
        return self


def _check_steps(steps: list[StepValue], what: str) -> None:
    """The steps follow each other with no gap and no overlap."""
    for before, after in zip(steps, steps[1:], strict=False):
        if _month_index(after.start) != _month_index(before.end) + 1:
            raise ValueError(
                f"{what}: each step starts in the month after the step before ends, "
                "with no gap and no overlap"
            )


class FlowSeries(_SeriesHeader):
    """One flow of carbon, one value per step: the amount over the step.

    The header is that of ``MonthlySeries``: a ``quantity`` identifier, the
    unit kept when values are missing, provenance, source or assumption
    mark, ``range_missing``. Which flows a model reports, and their
    identifiers and units, are the producer's (README.md, OPEN 3).
    """

    steps: list[StepValue]

    @model_validator(mode="after")
    def _consistent(self) -> FlowSeries:
        if not self.steps:
            raise ValueError(f"series {self.quantity!r}: has no step")
        _check_steps(self.steps, f"series {self.quantity!r}")
        self._check_header([item.value for item in self.steps])
        return self


class StockSeries(FlowSeries):
    """One stock of carbon: its value at the start of the horizon and at the end of each step.

    ``initial`` is a ``Value`` of its own, with its own provenance, source
    and range (or the reason it has none), or missing with its reason. Its
    unit is the unit of the series. The values of ``steps`` take the header.
    """

    initial: Value

    @model_validator(mode="after")
    def _initial_in_the_unit_of_the_series(self) -> StockSeries:
        if self.initial.unit != self.unit:
            raise ValueError(
                f"series {self.quantity!r}: initial is in the unit of the series (C1.1)"
            )
        return self


def _covers_horizon(series: FlowSeries, horizon: ForcingHorizon, what: str) -> None:
    if series.steps[0].start != horizon.start or series.steps[-1].end != horizon.end:
        raise ValueError(
            f"{what} {series.quantity!r}: the steps run from the first month of the "
            "horizon to its last"
        )


def _bounds(series: FlowSeries) -> list[tuple[int, int]]:
    return [(_month_index(s.start), _month_index(s.end)) for s in series.steps]


class CarbonBalance(ContractModel):
    """What one carbon model returns for one rotation of one field."""

    contract: Literal["carbon_balance"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr  # as in the forcing (D19 of #77)
    rotation_id: NonEmptyStr
    carbon_model: CarbonModel  # D1 of #77
    variant: QuantityId  # PROPOSED label (Q14 (d)); vocabulary OPEN
    horizon: ForcingHorizon  # the horizon of the forcing, unchanged
    soil_depth: Value  # the soil depth of the forcing, unchanged (C1.6)
    total_stock: StockSeries  # the total soil carbon of the model
    pools: list[StockSeries]  # the pools of the model; identifiers OPEN
    flows: list[FlowSeries]  # the flows of each step; identifiers OPEN
    soil_carbon_trend: list[SoilCarbonTrend]  # the three computations of C1.6

    @model_validator(mode="after")
    def _consistent(self) -> CarbonBalance:
        series: list[tuple[str, FlowSeries]] = [
            ("total_stock", self.total_stock),
            *(("pools", s) for s in self.pools),
            *(("flows", s) for s in self.flows),
        ]
        repeated = sorted(
            q for q, n in Counter(s.quantity for _, s in series).items() if n > 1
        )
        if repeated:
            raise ValueError(
                f"the quantity identifier {repeated[0]!r} appears more than once "
                "among total_stock, pools and flows"
            )
        steps = _bounds(self.total_stock)
        for what, item in series:
            _covers_horizon(item, self.horizon, what)
            if _bounds(item) != steps:
                raise ValueError(
                    f"{what} {item.quantity!r}: every series has the same steps as "
                    "total_stock"
                )
        computations = sorted(item.computation for item in self.soil_carbon_trend)
        if computations != sorted(TREND_COMPUTATIONS):
            raise ValueError(
                "soil_carbon_trend carries each of the three computations once "
                f"({', '.join(TREND_COMPUTATIONS)}); it carries {computations} (C1.6)"
            )
        others = sorted(
            {
                item.carbon_model
                for item in self.soil_carbon_trend
                if item.carbon_model != self.carbon_model
            }
        )
        if others:
            raise ValueError(
                f"soil_carbon_trend names the carbon model {others[0]!r}, not the "
                f"model of the balance {self.carbon_model!r}: values of two models "
                "are never merged (C1.5)"
            )
        return self
