"""Mean of one indicator by kind of year and over the whole record. PROPOSED.

Unit ``l2/by-kind-of-year`` (brief S-013). Aggregation only: the arithmetic
mean of the values of the agricultural years of each kind, with no weighting
and no new science. Pure functions; inputs are never mutated. The types below
are new and PROPOSED; the results contract is not edited. Ranges are not
combined into a range of the mean (OPEN, README.md).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import get_args

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode
from contracts.results.models import AnnualSoilLoss, WaterDeficitExposure

from .classify import KindOfYear, _is_finite_real, _is_int

_REASON_CODES: frozenset[str] = frozenset(get_args(ReasonCode))
# C3.2: "NO_COVERAGE | The data source has no data for this place or this period".
_NO_COVERAGE: ReasonCode = "NO_COVERAGE"
# C3.2: MISSING_INPUT, a value this one is built from is missing.
_MISSING_INPUT: ReasonCode = "MISSING_INPUT"


def _require(condition: bool, message: str) -> None:
    """ValueError, not TypeError, for every misuse of the inputs, also of a
    type: one exception type, as classify.py does (README.md)."""
    if not condition:
        raise ValueError(message)


def _check_one_of(value: object, reason: object, what: str) -> None:
    if (value is None) == (reason is None):
        raise ValueError(f"{what} holds a value or a reason, never both or neither")
    if value is not None and not _is_finite_real(value):
        raise ValueError(f"the value of {what} must be a finite number, not a bool")
    if reason is not None and reason not in _REASON_CODES:
        raise ValueError(f"the reason of {what} must be a reason code of C3.2")


def _is_text(text: object) -> bool:
    return isinstance(text, str) and text.strip() != ""


def _check_years(years: object, what: str) -> None:
    """A sorted tuple of unique int years (a bool is not a year)."""
    if not isinstance(years, tuple) or not all(_is_int(year) for year in years):
        raise ValueError(f"{what} must be a tuple of integer years")
    if list(years) != sorted(set(years)):
        raise ValueError(f"{what} must be sorted and unique")


@dataclass(frozen=True)
class YearValue:
    """The value of one indicator in one agricultural year, or its reason.

    PROPOSED: ``detail`` belongs to a missing value only; ``source`` and
    ``assumption`` (the provenance of C4.2) to a present value only.
    """

    value: float | None
    reason: ReasonCode | None
    detail: str | None
    source: str | None = None
    assumption: bool = False

    def __post_init__(self) -> None:
        _check_one_of(self.value, self.reason, "a year value")
        if self.detail is not None and not _is_text(self.detail):
            raise ValueError("the detail of a year value must be a non-blank string")
        if self.source is not None and not _is_text(self.source):
            raise ValueError("the source of a year value must be a non-blank string")
        _require(
            isinstance(self.assumption, bool),
            "the assumption mark of a year value must be a bool",
        )
        if self.value is not None and self.detail is not None:
            raise ValueError("a present year value carries no missing detail")
        if self.value is None and (self.source is not None or self.assumption):
            raise ValueError(
                "a missing year value carries no source and no assumption mark"
            )


@dataclass(frozen=True)
class KindMean:
    """The mean of one group of years, or missing with its reason.

    ``n_years`` and ``ag_years`` name the years whose values entered the mean
    (only years with a value, also when the mean is missing). ``sources`` are
    the sorted unique sources of those years and ``assumption`` is true when
    any of them carries the assumption mark. No range (OPEN, README.md).
    """

    value: float | None
    unit: str
    n_years: int
    ag_years: tuple[int, ...]
    reason: ReasonCode | None
    detail: str | None
    sources: tuple[str, ...] = ()
    assumption: bool = False

    def __post_init__(self) -> None:
        _check_one_of(self.value, self.reason, "a kind mean")
        if not _is_text(self.unit):
            raise ValueError("the unit of a kind mean must be a non-blank string")
        _check_years(self.ag_years, "ag_years")
        if not _is_int(self.n_years) or self.n_years != len(self.ag_years):
            raise ValueError("n_years is the number of ag_years")
        if self.value is not None and self.n_years < 1:
            raise ValueError("a present kind mean needs at least one year")
        if not isinstance(self.sources, tuple) or not all(
            _is_text(source) for source in self.sources
        ):
            raise ValueError("sources must be a tuple of non-blank strings")
        if list(self.sources) != sorted(set(self.sources)):
            raise ValueError("sources must be sorted and unique")
        _require(
            isinstance(self.assumption, bool),
            "the assumption mark of a kind mean must be a bool",
        )


@dataclass(frozen=True)
class MeansByKind:
    """The mean of each kind of year and of the whole record, for one indicator."""

    indicator: str
    unit: str
    by_kind: Mapping[str, KindMean]
    record: KindMean
    unclassified_years: tuple[int, ...]

    def __post_init__(self) -> None:
        if not _is_text(self.indicator) or not _is_text(self.unit):
            raise ValueError("indicator and unit must be non-blank strings")
        if (
            not isinstance(self.by_kind, Mapping)
            or tuple(self.by_kind) != KINDS_OF_YEAR
        ):
            raise ValueError(
                f"by_kind holds every kind of KINDS_OF_YEAR {KINDS_OF_YEAR}, in order"
            )
        for item in (*self.by_kind.values(), self.record):
            if not isinstance(item, KindMean) or item.unit != self.unit:
                raise ValueError(
                    "every mean of by_kind and record must be a KindMean in the unit"
                )
        _check_years(self.unclassified_years, "unclassified_years")
        # PROPOSED: a plain dict copy, so dataclasses.asdict and copy.deepcopy
        # work; the caller's mapping is not kept.
        object.__setattr__(self, "by_kind", dict(self.by_kind))


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
    sources = tuple(
        sorted(
            {
                series[year].source
                for year in with_value
                if series[year].source is not None
            }
        )
    )
    assumption = any(series[year].assumption for year in with_value)
    without = [year for year in years if series[year].value is None]
    if without:
        named = ", ".join(_name_missing(year, series[year]) for year in without)
        detail = f"agricultural year(s) {named} of {group} have no value"
        return KindMean(
            None,
            unit,
            len(with_value),
            with_value,
            _MISSING_INPUT,
            detail,
            sources,
            assumption,
        )
    total = sum(float(series[year].value) for year in with_value)
    return KindMean(
        total / len(with_value),
        unit,
        len(with_value),
        with_value,
        None,
        None,
        sources,
        assumption,
    )


def _name_missing(year: int, item: YearValue) -> str:
    """``2003 (MISSING_INPUT: precipitation of June missing)``, or without detail."""
    if item.detail is None:
        return f"{year} ({item.reason})"
    return f"{year} ({item.reason}: {item.detail})"


def _empty_detail(name: str, unclassified: Sequence[int]) -> str:
    """Detail of a kind with no classified year (PROPOSED, fix round 1)."""
    if not unclassified:
        return f"no agricultural year of the record is {name}"
    listed = ", ".join(str(year) for year in unclassified)
    return (
        f"no agricultural year of the record is classified {name}; "
        f"agricultural year(s) {listed} have no kind of year"
    )


def mean_by_kind(
    indicator: str,
    unit: str,
    series: Mapping[int, YearValue],
    kinds: Mapping[int, KindOfYear],
) -> MeansByKind:
    """The mean of ``series`` for each kind of year and for the whole record.

    A kind with no year of the series is missing ``NO_COVERAGE`` (the detail
    names the unclassified years, if any); a group with a year whose value is
    missing is missing ``MISSING_INPUT``, naming those years with their reasons
    and details. A year whose kind is missing, or that is not in ``kinds``,
    enters the record mean only and is listed in ``unclassified_years``. A year
    of ``kinds`` absent from ``series`` is ignored. An empty series, a year that
    is not an int, or an entry of the wrong type is a ValueError.
    """
    for name, text in (("indicator", indicator), ("unit", unit)):
        if not _is_text(text):
            raise ValueError(f"{name} must be a non-blank string")
    if not series:
        raise ValueError("the series holds at least one agricultural year")
    for year, item in series.items():
        _require(_is_int(year), "an agricultural year of the series must be an integer")
        _require(
            isinstance(item, YearValue),
            f"agricultural year {year} of the series must be a YearValue",
        )
    for year, item in kinds.items():
        _require(_is_int(year), "an agricultural year of kinds must be an integer")
        _require(
            isinstance(item, KindOfYear),
            f"agricultural year {year} of kinds must be a KindOfYear",
        )

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
            _empty_detail(name, unclassified),
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

    The value with its ``source`` and ``assumption`` mark, or the reason and
    detail of its ``missing`` part, is copied unchanged. A water-deficit
    exposure on the time basis ``rotation``, an item of another type, mixed
    indicators or units, a repeated agricultural year or an empty sequence is
    a ValueError.
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
        else:
            _require(
                isinstance(item, AnnualSoilLoss),
                "each item must be an AnnualSoilLoss or a WaterDeficitExposure",
            )
        if (item.indicator, item.unit) != (items[0].indicator, items[0].unit):
            raise ValueError("the items mix indicators or units")
        if item.ag_year in series:
            raise ValueError(f"agricultural year {item.ag_year} is repeated")
        if item.value is not None:
            series[item.ag_year] = YearValue(
                item.value, None, None, item.source, item.assumption
            )
        else:
            series[item.ag_year] = YearValue(
                None, item.missing.reason, item.missing.detail
            )
    return series
