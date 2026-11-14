"""Contract "Site data: climate" (blueprint section 5). PROPOSED.

Producer: Platform, sub-lane L2a (adapters). Consumers: Lead, Engines, Interface.
The field list is a proposal of a builder session for the producer to correct;
see ``README.md`` in this folder for what is PROPOSED and what is OPEN.

No variable of any data source is named here. A series is identified by a
generic ``quantity`` identifier; which quantities exist, from which source and
in which unit is OPEN.

The record carries the point its series are valid for: latitude, longitude and
elevation (issue #77, decision D9). No unit, datum, provenance label or source
is fixed for them here and no bound is checked; those are OPEN in ``README.md``.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import FiniteFloat, model_validator

from .common import (
    ContractModel,
    IsoDate,
    Missing,
    MonthNumber,
    NonEmptyStr,
    Provenance,
    QuantityId,
    Value,
    check_source_or_assumption,
)


class _SeriesItem(ContractModel):
    """One value of a series: a number or a ``missing`` part (C3.1)."""

    value: (
        FiniteFloat | None
    )  # null when missing; zero is a real value, never a stand-in
    missing: Missing | None = None

    @model_validator(mode="after")
    def _number_or_missing(self) -> _SeriesItem:
        if self.value is not None and self.missing is not None:
            raise ValueError(
                "an item holds a value or a missing part, never both (C3.1)"
            )
        if self.value is None and self.missing is None:
            raise ValueError(
                "a missing value carries a missing part with its reason (C3.1)"
            )
        return self


class DailyValue(_SeriesItem):
    date: IsoDate  # the day in the time zone of the series (C6.1)


class MonthlyValue(_SeriesItem):
    year: int  # calendar year (C5.1)
    month: MonthNumber


class YearMonth(ContractModel):
    year: int
    month: MonthNumber


class _SeriesHeader(ContractModel):
    """What a series states once for all its values: unit, provenance, source, range."""

    quantity: QuantityId  # vocabulary OPEN
    unit: NonEmptyStr  # C1.1; which unit per quantity is OPEN
    provenance: Provenance | None = None  # of every value that is not missing
    source: NonEmptyStr | None = None
    assumption: bool = False
    range_missing: Missing | None = None  # C2.2: why the values have no range

    def _check_header(self, values: list[float | None]) -> None:
        present = any(value is not None for value in values)
        what = f"series {self.quantity!r}"
        check_source_or_assumption(
            present=present,
            provenance=self.provenance,
            source=self.source,
            assumption=self.assumption,
            what=what,
        )
        if present and self.range_missing is None:
            raise ValueError(
                f"{what}: values without a range carry the reason in range_missing (C2.2)"
            )
        if not present and self.range_missing is not None:
            raise ValueError(f"{what}: a missing value has no range (C2.2)")


class DailySeries(_SeriesHeader):
    """A daily series with one explicit time zone (C6.1) and one item per day."""

    time_zone: NonEmptyStr  # "UTC" for the NASA POWER adapter (C6.2)
    start_date: IsoDate
    end_date: IsoDate  # inclusive
    days: list[DailyValue]

    @model_validator(mode="after")
    def _consistent(self) -> DailySeries:
        what = f"series {self.quantity!r}"
        if self.end_date < self.start_date:
            raise ValueError(f"{what}: ends before it starts")
        expected = self.start_date
        for day in self.days:
            if day.date != expected:
                raise ValueError(
                    f"{what}: expected the day {expected.isoformat()} and found {day.date.isoformat()}; "
                    "every day from start_date to end_date appears once, in order, "
                    "and a day without data stays in the series as missing"
                )
            expected += dt.timedelta(days=1)
        if expected != self.end_date + dt.timedelta(days=1):
            raise ValueError(f"{what}: the days stop before end_date")
        self._check_header([day.value for day in self.days])
        return self


class MonthlySeries(_SeriesHeader):
    """A series with one item per calendar month, each with its year (C5.1)."""

    start: YearMonth
    end: YearMonth  # inclusive
    months: list[MonthlyValue]

    @model_validator(mode="after")
    def _consistent(self) -> MonthlySeries:
        what = f"series {self.quantity!r}"
        first = self.start.year * 12 + (self.start.month - 1)
        last = self.end.year * 12 + (self.end.month - 1)
        if last < first:
            raise ValueError(f"{what}: ends before it starts")
        expected = first
        for item in self.months:
            if item.year * 12 + (item.month - 1) != expected:
                raise ValueError(
                    f"{what}: every month from start to end appears once, in order, "
                    "and a month without data stays in the series as missing"
                )
            expected += 1
        if expected != last + 1:
            raise ValueError(f"{what}: the months stop before end")
        self._check_header([item.value for item in self.months])
        return self


def _unique_quantities(series: list[_SeriesHeader], what: str) -> None:
    quantities = [item.quantity for item in series]
    if len(quantities) != len(set(quantities)):
        raise ValueError(f"{what}: two series share one quantity identifier")


class ClimatePoint(ContractModel):
    """The point the series of one record are valid for (issue #77, D9).

    The field names are PROPOSED. Each of the three is a ``Value`` of
    ``common.py``, unchanged: a number with its unit string, its provenance
    label, its source or assumption mark and its range or the reason it has
    none; or missing with its reason, keeping its unit.

    Nothing is fixed here that a person has to choose: the unit strings, the
    datum, the provenance label and the source arrive with the document. No
    bound is checked on any of the three. All of it is OPEN in ``README.md``.
    """

    latitude: Value  # unit and datum OPEN
    longitude: Value  # unit and datum OPEN
    elevation: Value  # unit, vertical reference and which elevation OPEN


class SiteClimate(ContractModel):
    """Climate data of one field of one case."""

    contract: Literal["site_data_climate"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    point: ClimatePoint  # required; each of its values can be missing with its reason
    daily_series: list[DailySeries]
    monthly_series: list[MonthlySeries]

    @model_validator(mode="after")
    def _consistent(self) -> SiteClimate:
        _unique_quantities(self.daily_series, "daily_series")
        _unique_quantities(self.monthly_series, "monthly_series")
        return self
