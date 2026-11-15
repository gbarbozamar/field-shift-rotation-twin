"""The simple margin of one rotation per hectare and agricultural year. PROPOSED.

One public pure function, ``compute_rotation_margin``, built by unit
``l2/economics-margin``. It reads the economic facts a producer declares
(``contracts.economic_facts``) and adds the margin of every crop cycle of one
cycle of the rotation, in each kind of year and on the average of the record.
The rules are arithmetic, not parameters; see ``README.md`` in this folder.

No network call, no parameter value, no price forecast, no price on lost soil,
no discounting, no uncertainty range (OPEN, README.md). A missing fact gives a
missing margin with its reason (C3.2 of contracts/CONVENTIONS.md), never zero.
"""

from __future__ import annotations

import numbers
import operator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from contracts.economic_facts import (
    KINDS_OF_YEAR,
    MARGIN_UNIT,
    CoverCrop,
    DeclaredMarginCrop,
    EconomicFacts,
    GrainCrop,
)
from contracts.inputs.common import ReasonCode, Value


@dataclass(frozen=True)
class MarginResult:
    """One margin: a value, or missing with its reason. PROPOSED.

    Exactly one of ``value`` and ``reason`` is set; ``detail`` travels with
    ``reason`` and says what is missing.
    """

    value: float | None
    unit: str = MARGIN_UNIT
    reason: ReasonCode | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.reason is None):
            raise ValueError(
                "a margin holds a value or a reason, never both or neither"
            )
        if self.reason is None and self.detail is not None:
            raise ValueError("a present margin carries no missing detail")


@dataclass(frozen=True)
class RotationMargin:
    """The margin of one rotation in each kind of year and on average. PROPOSED.

    ``by_kind`` is stored as a read-only mapping, so the result cannot be
    changed after it is computed.
    """

    by_kind: Mapping[str, MarginResult]
    average: MarginResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))


def _missing(reason: ReasonCode, detail: str) -> MarginResult:
    return MarginResult(value=None, reason=reason, detail=detail)


def _describe_absent(crop_id: str, member: str, kind: str, value: Value) -> str:
    """The detail of one missing input, naming the crop, member, kind and reason."""
    # The contract (C3.1) guarantees a missing value carries its missing part.
    assert value.missing is not None
    text = (
        f"crop_id {crop_id!r}: {member} in the {kind} kind of year is missing "
        f"{value.missing.reason}"
    )
    if value.missing.detail is not None:
        text += f" ({value.missing.detail})"
    return text


def _absent(crop_id: str, kind: str, values: Mapping[str, Value]) -> list[str]:
    return [
        _describe_absent(crop_id, member, kind, value)
        for member, value in values.items()
        if value.value is None
    ]


def _cycle_margin(crop, kind: str) -> tuple[float | None, list[str]]:
    """The margin of one crop cycle in ``kind``, or the details of what is missing."""
    if isinstance(crop, GrainCrop):
        price = crop.price
        yield_ = getattr(crop.yield_, kind)
        cost = crop.cost
        absent = _absent(
            crop.crop_id, kind, {"price": price, f"yield.{kind}": yield_, "cost": cost}
        )
        if absent:
            return None, absent
        # PROPOSED rule: price * yield in this kind of year - cost of the cycle.
        return price.value * yield_.value - cost.value, []
    if isinstance(crop, CoverCrop):
        absent = _absent(crop.crop_id, kind, {"cost": crop.cost})
        if absent:
            return None, absent
        # PROPOSED rule: a cover crop is not sold; its cycle costs its cost.
        return -crop.cost.value, []
    if isinstance(crop, DeclaredMarginCrop):
        margin = getattr(crop.declared_margin, kind)
        absent = _absent(crop.crop_id, kind, {f"declared_margin.{kind}": margin})
        if absent:
            return None, absent
        # PROPOSED rule: the declared margin, per hectare and agricultural year.
        return margin.value, []
    raise TypeError(  # pragma: no cover - the contract admits only the three kinds
        f"unknown kind of crop: {type(crop).__name__}"
    )


def _margin_in_kind(
    years: Sequence[Sequence[str]],
    crops: Mapping[str, object],
    kind: str,
) -> MarginResult:
    total = 0.0
    problems: list[str] = []
    for entry in years:
        for crop_id in entry:
            crop = crops.get(crop_id)
            if crop is None:
                problems.append(
                    f"crop_id {crop_id!r} is in the rotation but not in the "
                    "economic facts"
                )
                continue
            margin, absent = _cycle_margin(crop, kind)
            if margin is None:
                problems.extend(absent)
            else:
                total += margin
    if problems:
        # Never zero: a margin with a missing input is missing (C3.2).
        return _missing("MISSING_INPUT", "; ".join(dict.fromkeys(problems)))
    # "The field is divided in as many parts as the rotation has years": the
    # margin per hectare and year is the sum of every cycle over len(years).
    return MarginResult(value=total / len(years))


def _check_years(years: Sequence[Sequence[str]], crops: Mapping[str, object]) -> None:
    # A str is a Sequence[str]: taken as years or as an entry it would be read
    # letter by letter, so it is refused. ValueError, not TypeError: one
    # exception type for every structural misuse (the brief names ValueError).
    if isinstance(years, str):
        raise ValueError("years: a list of agricultural years, not a text")  # noqa: TRY004
    if len(years) == 0:
        raise ValueError("years: the rotation has at least one agricultural year")
    for index, entry in enumerate(years):
        if isinstance(entry, str):
            raise ValueError(f"years[{index}]: a list of crop_ids, not a text")  # noqa: TRY004
        # PROPOSED: a bare fallow year has no declared fact, so it is refused.
        if len(entry) == 0:
            raise ValueError(
                f"years[{index}]: an agricultural year holds at least one crop_id"
            )
        # PROPOSED: a declared margin covers a whole agricultural year, so it
        # does not share its year with another crop (README.md, OPEN).
        if len(entry) > 1 and any(
            isinstance(crops.get(crop_id), DeclaredMarginCrop) for crop_id in entry
        ):
            raise ValueError(
                f"years[{index}]: a declared-margin crop covers the whole "
                "agricultural year and shares it with no other crop"
            )


def _check_year_counts(year_counts: Mapping[str, int]) -> dict[str, int]:
    """Check ``year_counts`` and give it back as plain integers."""
    unknown = sorted(set(year_counts) - set(KINDS_OF_YEAR))
    if unknown:
        raise ValueError(
            f"year_counts: keys not in KINDS_OF_YEAR {KINDS_OF_YEAR}: {unknown}"
        )
    absent = [kind for kind in KINDS_OF_YEAR if kind not in year_counts]
    if absent:
        raise ValueError(f"year_counts: no count for {absent}")
    counts: dict[str, int] = {}
    for kind in KINDS_OF_YEAR:
        count = year_counts[kind]
        # Any integral number (such as a numpy integer) is a count; a boolean
        # is not, although Python treats it as one.
        if isinstance(count, bool) or not isinstance(count, numbers.Integral):
            # One exception type for every structural misuse (the brief of
            # l2/economics-margin names ValueError), hence no TypeError here.
            raise ValueError(f"year_counts[{kind!r}]: a count is an integer")  # noqa: TRY004
        counts[kind] = operator.index(count)
        if counts[kind] < 0:
            raise ValueError(f"year_counts[{kind!r}]: a count is not negative")
    if sum(counts.values()) == 0:
        raise ValueError("year_counts: at least one count is above zero")
    return counts


def _average(
    by_kind: Mapping[str, MarginResult], year_counts: Mapping[str, int] | None
) -> MarginResult:
    if year_counts is None:
        return _missing(
            "NOT_AVAILABLE",
            "the kinds of year of the record are not classified, so the number "
            "of years of each kind is not known",
        )
    # PROPOSED: a kind with count 0 does not enter the average, so its missing
    # margin does not make the average missing.
    counted = [kind for kind in KINDS_OF_YEAR if year_counts[kind] > 0]
    missing = [kind for kind in counted if by_kind[kind].value is None]
    if missing:
        return _missing(
            "MISSING_INPUT",
            "the margin is missing in the kind of year "
            + ", ".join(missing)
            + ", which the record holds",
        )
    total_years = sum(year_counts[kind] for kind in counted)
    weighted = sum(by_kind[kind].value * year_counts[kind] for kind in counted)
    return MarginResult(value=weighted / total_years)


def compute_rotation_margin(
    years: Sequence[Sequence[str]],
    facts: EconomicFacts,
    year_counts: Mapping[str, int] | None,
) -> RotationMargin:
    """The simple margin per hectare and agricultural year of one rotation. PROPOSED.

    ``years`` holds one entry per agricultural year of one cycle of the
    rotation, each entry the crop_ids sown in that year. ``year_counts`` is
    how many agricultural years of the record fall in each kind of year, or
    None when that is not known. Raises ``ValueError`` on structural misuse
    (see README.md); a missing fact is never an exception but a missing
    margin with its reason.
    """
    crops = {crop.crop_id: crop for crop in facts.crops}
    _check_years(years, crops)
    if year_counts is not None:
        year_counts = _check_year_counts(year_counts)
    by_kind = {kind: _margin_in_kind(years, crops, kind) for kind in KINDS_OF_YEAR}
    return RotationMargin(by_kind=by_kind, average=_average(by_kind, year_counts))
