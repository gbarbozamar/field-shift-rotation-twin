"""Contract "CarbonForcing" (blueprint section 5). PROPOSED (blueprint section 3.7).

Producer: Platform, sub-lane L2a. Consumers: Engines (AMG, ``engine/amg/``)
and Platform, sub-lane L2b (RothC, ``engine/rothc/``). Purpose, from the
blueprint: the same inputs, climate and horizon for both carbon models.

This module fixes structure only: which parts exist, what shape each takes
and how an absence travels. It names no quantity a carbon model needs, no
unit, no soil depth, no horizon and no rule for making a month from the
daily record. Those are OPEN in ``README.md`` in this folder.

The shared parts are imported from ``contracts.inputs``, never copied:
``Value`` and ``Missing`` (C1.1, C2, C3, C4), the monthly series of
``SiteClimate`` (one item per calendar month with its year, C5.1) and the
soil property item of ``SiteSoilSlope``.

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import model_validator

from contracts.inputs.common import ContractModel, NonEmptyStr, QuantityId, Value
from contracts.inputs.site_climate import MonthlySeries, YearMonth
from contracts.inputs.site_soil_slope import SoilProperty


def _month_index(month: YearMonth) -> int:
    return month.year * 12 + (month.month - 1)


class ForcingHorizon(ContractModel):
    """The months both carbon models are run over: first and last, inclusive.

    A month travels with its calendar year (C5.1). The value of the horizon
    is OPEN (C1.6).
    """

    start: YearMonth
    end: YearMonth  # inclusive

    @model_validator(mode="after")
    def _ordered(self) -> ForcingHorizon:
        if _month_index(self.end) < _month_index(self.start):
            raise ValueError("horizon: ends before it starts")
        return self


class ClimateSeries(MonthlySeries):
    """One monthly climate series of the forcing.

    The shape of ``SiteClimate.monthly_series``, unchanged: a ``quantity``
    identifier, the unit carried once by the series and kept when values are
    missing, provenance, source or assumption mark, ``range_missing``, and one
    item per month from ``start`` to ``end``, in order, each a number or
    missing with its reason. Which quantities, and how a month is made from
    the daily record, are OPEN.
    """


class CarbonInputSeries(MonthlySeries):
    """One monthly series of carbon inputs, with what it comes from.

    ``origin`` identifies what the series is taken from (for example the
    residue ledger); it is not the data reference of C4.2, which stays in
    ``source``. Its vocabulary, and whether the residue ledger is one, are
    OPEN (Q14 (b) of ``contracts/ENTRYPOINTS.md``).
    """

    origin: QuantityId  # vocabulary OPEN


def _unique_quantities(
    items: Sequence[ClimateSeries | SoilProperty], what: str
) -> None:
    repeated = sorted(q for q, n in Counter(i.quantity for i in items).items() if n > 1)
    if repeated:
        raise ValueError(
            f"{what}: the quantity identifier {repeated[0]!r} appears more than once"
        )


def _covers_horizon(series: MonthlySeries, horizon: ForcingHorizon, what: str) -> None:
    """A series runs over exactly the months of the horizon.

    ``MonthlySeries`` already checks one item per month from its ``start`` to
    its ``end``, in order, with no gap and no duplicate.
    """
    if series.start != horizon.start or series.end != horizon.end:
        raise ValueError(
            f"{what} {series.quantity!r}: start and end are those of the horizon, "
            "one item per month of the horizon"
        )


class CarbonForcing(ContractModel):
    """What both carbon models receive for one rotation of one field."""

    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr  # replaced by the field identity contract (D19 of #77)
    rotation_id: NonEmptyStr
    horizon: ForcingHorizon  # value OPEN (C1.6)
    soil_depth: Value  # value and unit OPEN (C1.6)
    climate: list[ClimateSeries]  # quantities and monthly aggregation OPEN
    carbon_inputs: list[CarbonInputSeries]  # quantities and origins OPEN (Q14 (b))
    soil_properties: list[SoilProperty]  # which properties OPEN

    @model_validator(mode="after")
    def _consistent(self) -> CarbonForcing:
        _unique_quantities(self.climate, "climate")
        _unique_quantities(self.carbon_inputs, "carbon_inputs")
        _unique_quantities(self.soil_properties, "soil_properties")
        for series in self.climate:
            _covers_horizon(series, self.horizon, "climate")
        for series in self.carbon_inputs:
            _covers_horizon(series, self.horizon, "carbon_inputs")
        return self
