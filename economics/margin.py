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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
    """The margin of one rotation in each kind of year and on average. PROPOSED."""

    by_kind: dict[str, MarginResult]
    average: MarginResult


def _missing(reason: ReasonCode, detail: str) -> MarginResult:
    return MarginResult(value=None, reason=reason, detail=detail)


def _describe_absent(crop_id: str, member: str, kind: str, value: Value) -> str:
    """The detail of one missing input, naming the crop, member, kind and reason."""
    reason = value.missing.reason if value.missing is not None else "UNKNOWN"
    text = (
        f"crop_id {crop_id!r}: {member} in the {kind} kind of year is missing {reason}"
    )
    if value.missing is not None and value.missing.detail is not None:
        text += f" ({value.missing.detail})"
    return text


def _cycle_margin(crop, kind: str) -> tuple[float | None, list[str]]:
    """The margin of one crop cycle in ``kind``, or the details of what is missing."""
    needed: list[tuple[str, Value]]
    if isinstance(crop, GrainCrop):
        needed = [
            ("price", crop.price),
            (f"yield.{kind}", getattr(crop.yield_, kind)),
            ("cost", crop.cost),
        ]
    elif isinstance(crop, CoverCrop):
        needed = [("cost", crop.cost)]
    elif isinstance(crop, DeclaredMarginCrop):
        needed = [(f"declared_margin.{kind}", getattr(crop.declared_margin, kind))]
    else:  # pragma: no cover - the contract admits only the three kinds
        raise TypeError(f"unknown kind of crop: {type(crop).__name__}")

    absent = [
        _describe_absent(crop.crop_id, member, kind, value)
        for member, value in needed
        if value.value is None
    ]
    if absent:
        return None, absent

    if isinstance(crop, GrainCrop):
        # PROPOSED rule: price * yield in this kind of year - cost of the cycle.
        price, yield_, cost = (value.value for _, value in needed)
        return price * yield_ - cost, []
    if isinstance(crop, CoverCrop):
        # PROPOSED rule: a cover crop is not sold; its cycle costs its cost.
        return -crop.cost.value, []
    # PROPOSED rule: the declared margin, per hectare and agricultural year.
    return needed[0][1].value, []


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


def _check_years(years: Sequence[Sequence[str]]) -> None:
    if len(years) == 0:
        raise ValueError("years: the rotation has at least one agricultural year")
    for index, entry in enumerate(years):
        # PROPOSED: a bare fallow year has no declared fact, so it is refused.
        if len(entry) == 0:
            raise ValueError(
                f"years[{index}]: an agricultural year holds at least one crop_id"
            )


def _check_year_counts(year_counts: Mapping[str, int]) -> None:
    unknown = sorted(set(year_counts) - set(KINDS_OF_YEAR))
    if unknown:
        raise ValueError(
            f"year_counts: keys not in KINDS_OF_YEAR {KINDS_OF_YEAR}: {unknown}"
        )
    absent = [kind for kind in KINDS_OF_YEAR if kind not in year_counts]
    if absent:
        raise ValueError(f"year_counts: no count for {absent}")
    for kind in KINDS_OF_YEAR:
        count = year_counts[kind]
        if isinstance(count, bool) or not isinstance(count, int):
            # One exception type for every structural misuse (the brief of
            # l2/economics-margin names ValueError), hence no TypeError here.
            raise ValueError(f"year_counts[{kind!r}]: a count is an integer")  # noqa: TRY004
        if count < 0:
            raise ValueError(f"year_counts[{kind!r}]: a count is not negative")
    if sum(year_counts[kind] for kind in KINDS_OF_YEAR) == 0:
        raise ValueError("year_counts: at least one count is above zero")


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
    _check_years(years)
    if year_counts is not None:
        _check_year_counts(year_counts)
    crops = {crop.crop_id: crop for crop in facts.crops}
    by_kind = {kind: _margin_in_kind(years, crops, kind) for kind in KINDS_OF_YEAR}
    return RotationMargin(by_kind=by_kind, average=_average(by_kind, year_counts))
