"""Mean of one indicator by kind of year and over the whole record. PROPOSED.

Unit ``l2/by-kind-of-year`` (brief S-013). Aggregation only: the arithmetic
mean of the values of the agricultural years of each kind, with no weighting
and no new science. Pure functions; inputs are never mutated. The types below
are new and PROPOSED; the results contract is not edited.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import get_args

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode
from contracts.results.models import AnnualSoilLoss, WaterDeficitExposure

from .classify import KindOfYear

_REASON_CODES: frozenset[str] = frozenset(get_args(ReasonCode))
# C3.2: "NO_COVERAGE | The data source has no data for this place or this period".
_NO_COVERAGE: ReasonCode = "NO_COVERAGE"
# C3.2: MISSING_INPUT, a value this one is built from is missing.
_MISSING_INPUT: ReasonCode = "MISSING_INPUT"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_one_of(value: object, reason: object, what: str) -> None:
    if (value is None) == (reason is None):
        raise ValueError(f"{what} holds a value or a reason, never both or neither")
    if value is not None and (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"the value of {what} must be a finite number, not a bool")
    if reason is not None and reason not in _REASON_CODES:
        raise ValueError(f"the reason of {what} must be a reason code of C3.2")


@dataclass(frozen=True)
class YearValue:
    """The value of one indicator in one agricultural year, or its reason."""

    value: float | None
    reason: ReasonCode | None
    detail: str | None

    def __post_init__(self) -> None:
        _check_one_of(self.value, self.reason, "a year value")


@dataclass(frozen=True)
class KindMean:
    """The mean of one group of years, or missing with its reason.

    ``n_years`` and ``ag_years`` name the years whose values entered the mean
    (only years with a value, also when the mean is missing).
    """

    value: float | None
    unit: str
    n_years: int
    ag_years: tuple[int, ...]
    reason: ReasonCode | None
    detail: str | None

    def __post_init__(self) -> None:
        _check_one_of(self.value, self.reason, "a kind mean")
        if not _is_int(self.n_years) or self.n_years != len(self.ag_years):
            raise ValueError("n_years is the number of ag_years")
        if tuple(sorted(self.ag_years)) != tuple(self.ag_years):
            raise ValueError("ag_years are sorted")


@dataclass(frozen=True)
class MeansByKind:
    """The mean of each kind of year and of the whole record, for one indicator."""

    indicator: str
    unit: str
    by_kind: Mapping[str, KindMean]
    record: KindMean
    unclassified_years: tuple[int, ...]

    def __post_init__(self) -> None:
        if tuple(self.by_kind) != KINDS_OF_YEAR:
            raise ValueError(
                f"by_kind holds every kind of KINDS_OF_YEAR {KINDS_OF_YEAR}"
            )
        # A read-only view, so the result cannot be changed after it is built.
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))


def _check_text(name: str, text: object) -> None:
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"{name} must be a non-blank string")


def _mean_of(
    years: Sequence[int],
    series: Mapping[int, YearValue],
    unit: str,
    empty_detail: str,
    group: str,
) -> KindMean:
    """Arithmetic mean of the values of ``years``, or missing with its reason."""
    if not years:
        return KindMean(None, unit, 0, (), _NO_COVERAGE, empty_detail)
    with_value = tuple(year for year in years if series[year].value is not None)
    without = [year for year in years if series[year].value is None]
    if without:
        named = ", ".join(f"{year} ({series[year].reason})" for year in without)
        detail = f"agricultural year(s) {named} of {group} have no value"
        return KindMean(None, unit, len(with_value), with_value, _MISSING_INPUT, detail)
    total = sum(float(series[year].value) for year in with_value)
    return KindMean(
        total / len(with_value), unit, len(with_value), with_value, None, None
    )


def mean_by_kind(
    indicator: str,
    unit: str,
    series: Mapping[int, YearValue],
    kinds: Mapping[int, KindOfYear],
) -> MeansByKind:
    """The mean of ``series`` for each kind of year and for the whole record.

    A kind with no year of the series is missing ``NO_COVERAGE``; a group with
    a year whose value is missing is missing ``MISSING_INPUT``, naming those
    years and their reasons. A year whose kind is missing, or that is not in
    ``kinds``, enters the record mean only and is listed in
    ``unclassified_years``. A year of ``kinds`` absent from ``series`` is
    ignored. An empty series, or an entry of the wrong type, is a ValueError.
    """
    _check_text("indicator", indicator)
    _check_text("unit", unit)
    if not series:
        raise ValueError("the series holds at least one agricultural year")
    # ValueError, not TypeError: one exception type for every misuse of the
    # inputs, as classify.py does (README.md).
    for year, item in series.items():
        if not _is_int(year):
            raise ValueError("an agricultural year of the series must be an integer")
        if not isinstance(item, YearValue):
            raise ValueError(f"agricultural year {year} of the series is a YearValue")  # noqa: TRY004
    for year, item in kinds.items():
        if not isinstance(item, KindOfYear):
            raise ValueError(f"agricultural year {year} of kinds is a KindOfYear")  # noqa: TRY004

    years = sorted(series)
    groups: dict[str, list[int]] = {name: [] for name in KINDS_OF_YEAR}
    unclassified: list[int] = []
    for year in years:
        found = kinds.get(year)
        if found is None or found.kind is None:
            unclassified.append(year)
        else:
            groups[found.kind].append(year)

    by_kind = {
        name: _mean_of(
            groups[name],
            series,
            unit,
            f"no agricultural year of the record is {name}",
            f"kind {name}",
        )
        for name in KINDS_OF_YEAR
    }
    # The series is not empty, so the record mean is never NO_COVERAGE.
    record = _mean_of(years, series, unit, "the series is empty", "the record")
    return MeansByKind(indicator, unit, by_kind, record, tuple(unclassified))


def series_from_results(
    items: Sequence[AnnualSoilLoss | WaterDeficitExposure],
) -> dict[int, YearValue]:
    """A per-agricultural-year series from values of the results contract.

    The value, or the reason and detail of its ``missing`` part, is copied
    unchanged. A water-deficit exposure on the time basis ``rotation``, an item
    of another type, mixed indicators or units, a repeated agricultural year or
    an empty sequence is a ValueError.
    """
    if not items:
        raise ValueError("at least one value of the results contract is needed")
    series: dict[int, YearValue] = {}
    for item in items:
        if isinstance(item, WaterDeficitExposure):
            if item.time_basis != "ag_year":
                raise ValueError(
                    "a water-deficit exposure on the time basis 'rotation' is not a "
                    "per-agricultural-year value"
                )
        elif not isinstance(item, AnnualSoilLoss):
            raise ValueError("each item is an AnnualSoilLoss or a WaterDeficitExposure")  # noqa: TRY004
        if (item.indicator, item.unit) != (items[0].indicator, items[0].unit):
            raise ValueError("the items mix indicators or units")
        if item.ag_year in series:
            raise ValueError(f"agricultural year {item.ag_year} is repeated")
        if item.value is not None:
            series[item.ag_year] = YearValue(item.value, None, None)
        else:
            series[item.ag_year] = YearValue(
                None, item.missing.reason, item.missing.detail
            )
    return series
