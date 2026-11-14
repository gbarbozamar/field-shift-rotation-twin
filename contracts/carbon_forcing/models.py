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
from typing import Literal

from pydantic import model_validator

from contracts.inputs.common import ContractModel, NonEmptyStr, QuantityId, Value

# ``_SeriesItem`` and ``_SeriesHeader`` are private names of
# ``contracts/inputs/site_climate.py``; they are imported, not copied, so the
# rules of a series item and of a series header stay in one place. Lane L0
# may make them public later.
from contracts.inputs.site_climate import (
    MonthlySeries,
    YearMonth,
    _SeriesHeader,
    _SeriesItem,
)
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


class AnnualValue(_SeriesItem):
    """One value of an annual series: a number or missing with its reason (C3.1).

    ``ag_year`` is the agricultural year, identified by the calendar year in
    which it begins (C5.3).
    """

    ag_year: int


class AnnualSeries(_SeriesHeader):
    """A series with one item per agricultural year (C5.3), inclusive.

    The header (quantity, unit, provenance, source or assumption mark,
    ``range_missing``) is that of ``MonthlySeries``. How an annual value is
    made from the monthly values or the daily record, and what a year with
    missing months becomes, are OPEN; C5.5 says only that a year the data
    does not cover in full is missing with reason ``NO_COVERAGE``.
    """

    first_ag_year: int
    last_ag_year: int  # inclusive
    years: list[AnnualValue]

    @model_validator(mode="after")
    def _consistent(self) -> AnnualSeries:
        what = f"series {self.quantity!r}"
        if self.last_ag_year < self.first_ag_year:
            raise ValueError(f"{what}: ends before it starts")
        expected = self.first_ag_year
        for item in self.years:
            if item.ag_year != expected:
                raise ValueError(
                    f"{what}: every agricultural year from first_ag_year to "
                    "last_ag_year appears once, in order, and a year without data "
                    "stays in the series as missing"
                )
            expected += 1
        if expected != self.last_ag_year + 1:
            raise ValueError(f"{what}: the years stop before last_ag_year")
        self._check_header([item.value for item in self.years])
        return self


class AnnualCarbonInputSeries(AnnualSeries):
    """One annual series of carbon inputs, with ``origin`` as ``CarbonInputSeries``."""

    origin: QuantityId  # vocabulary OPEN


def _unique_quantities(
    items: Sequence[ClimateSeries | AnnualSeries | SoilProperty], what: str
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


def _ag_years_of(horizon: ForcingHorizon) -> tuple[int, int] | None:
    """First and last agricultural year of a horizon of whole agricultural years.

    C5.3: an agricultural year is twelve consecutive calendar months from the
    start month, identified by the calendar year in which it begins. The
    horizon starts at the start month. None when the horizon is not a whole
    number of agricultural years.
    """
    first = _month_index(horizon.start)
    months = _month_index(horizon.end) - first + 1
    if months % 12 != 0:
        return None
    return horizon.start.year, (first + months - 12) // 12


def _covers_ag_years(series: AnnualSeries, years: tuple[int, int], what: str) -> None:
    if (series.first_ag_year, series.last_ag_year) != years:
        raise ValueError(
            f"{what} {series.quantity!r}: first_ag_year and last_ag_year are the "
            "agricultural years of the horizon"
        )


class CarbonForcing(ContractModel):
    """What both carbon models receive for one rotation of one field."""

    contract: Literal["carbon_forcing"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr  # replaced by the field identity contract (D19 of #77)
    rotation_id: NonEmptyStr
    horizon: ForcingHorizon  # value OPEN (C1.6)
    soil_depth: Value  # value and unit OPEN (C1.6)
    climate: list[ClimateSeries]  # quantities and monthly aggregation OPEN
    carbon_inputs: list[CarbonInputSeries]  # quantities and origins OPEN (Q14 (b))
    annual_climate: list[AnnualSeries]  # quantities and annual aggregation OPEN
    annual_carbon_inputs: list[AnnualCarbonInputSeries]  # as carbon_inputs
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
        _unique_quantities(self.annual_climate, "annual_climate")
        _unique_quantities(self.annual_carbon_inputs, "annual_carbon_inputs")
        annual = [
            *(("annual_climate", s) for s in self.annual_climate),
            *(("annual_carbon_inputs", s) for s in self.annual_carbon_inputs),
        ]
        if annual:
            years = _ag_years_of(self.horizon)
            if years is None:
                raise ValueError(
                    "horizon: with annual series, the horizon is a whole number "
                    "of agricultural years, twelve consecutive months each (C5.3)"
                )
            for what, series in annual:
                _covers_ag_years(series, years, what)
        return self
