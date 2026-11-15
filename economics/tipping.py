"""At which soybean price the rotation to plant changes. PROPOSED.

One public pure function, ``find_tipping_price``, built by unit
``l2/tipping-price`` (S-016). Inside a price range the user declares, it finds
the nearest soybean price above today's and the nearest below at which the
answer of ``choose_rotation`` changes, with the rotation (or the answer) that
takes over and how far today's declared price is from it, in percent. A
tipping price, never a forecast. The rules are arithmetic, not parameters; see
``README.md`` in this folder.

The engines are reused, never copied: the margin of each rotation comes from
``compute_rotation_margin`` at the two ends of the range, on a copy of the
facts with the soybean price replaced, and is linear in that price between
them; the answer at a price comes from ``choose_rotation``. No network call,
no price, range or threshold in the code. A missing input gives a missing
tipping point with its reason (C3.2 of contracts/CONVENTIONS.md), never zero.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, get_args

from contracts.economic_facts import (
    KINDS_OF_YEAR,
    PRICE_UNIT,
    EconomicFacts,
    GrainCrop,
)
from contracts.inputs.common import ReasonCode

from .decide import Answer, Decision, RotationOption, Strictness, choose_rotation
from .limit import LimitAssessment, _reason_text
from .margin import MarginResult, compute_rotation_margin

Direction = Literal["up", "down"]

# The margins the ranking may read: the average of the record or one kind of
# year, as the route picks it for the kind-of-year question. PROPOSED.
MARGINS_OF: tuple[str, ...] = ("average", *KINDS_OF_YEAR)

NO_CHANGE = "no price in this range changes the answer"

# PROPOSED: a price tried by the search is written into the copy of the facts
# as a declared value, with a source that says what it is. "DECLARED" is the
# provenance that GrainCrop.price of contracts.economic_facts admits for a
# present value (C4.1).
_TRIED_PROVENANCE = "DECLARED"
_TRIED_SOURCE = (
    "a soybean price tried inside the price range the user declared "
    "(tipping price search, not a forecast)"
)
_TRIED_NO_RANGE = "a price tried by the tipping price search carries no range"


@dataclass(frozen=True)
class TippingOption:
    """One rotation to choose from at any soybean price. PROPOSED.

    ``years`` is what ``compute_rotation_margin`` takes; ``limit`` is the
    assessment of ``assess_limit``, which does not depend on the price.
    """

    rotation_id: str
    years: Sequence[Sequence[str]]
    limit: LimitAssessment


def _real(number: object, what: str) -> float:
    # A boolean is not a price, although Python treats it as a number.
    # ValueError, not TypeError: one exception type for every misuse.
    if isinstance(number, bool) or not isinstance(number, numbers.Real):
        raise ValueError(f"{what}: a real number")  # noqa: TRY004
    value = float(number)
    if not math.isfinite(value):
        raise ValueError(f"{what}: a finite number")
    return value


@dataclass(frozen=True)
class PriceRange:
    """The soybean price range the user declares, in ``USD t-1``. PROPOSED.

    ``low < high`` and both not below zero, else ``ValueError``. The bounds
    are stored as floats.
    """

    low: float
    high: float
    unit: str = PRICE_UNIT

    def __post_init__(self) -> None:
        if self.unit != PRICE_UNIT:
            raise ValueError(f"unit: {PRICE_UNIT!r}")
        low = _real(self.low, "low")
        high = _real(self.high, "high")
        if low < 0 or high < 0:
            raise ValueError("price range: a price is not negative")
        if not low < high:
            raise ValueError("price range: low is below high")
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "high", high)

    def text(self) -> str:
        return f"{self.low!r} to {self.high!r} {self.unit}"


@dataclass(frozen=True)
class TippingPoint:
    """The nearest price in one direction where the answer changes. PROPOSED.

    ``price`` None: ``reason`` and ``detail`` say why (``NOT_APPLICABLE`` when
    no price in the range changes the answer), and ``takes_over``,
    ``answer_after`` and ``distance_percent`` are None. ``price`` set:
    ``answer_after`` is the answer just past it, ``takes_over`` the rotation
    chosen there (None unless the answer there is ``chosen``), and
    ``distance_percent`` is ``(price - today) / today * 100``, or None with
    reason ``NOT_COMPUTABLE`` when today's price is zero.
    """

    direction: Direction
    price: float | None
    takes_over: str | None
    answer_after: Answer | None
    distance_percent: float | None
    reason: ReasonCode | None
    detail: str | None
    unit: str = PRICE_UNIT

    def __post_init__(self) -> None:
        if self.direction not in get_args(Direction):
            raise ValueError(f"direction: one of {get_args(Direction)}")
        if self.unit != PRICE_UNIT:
            raise ValueError(f"unit: {PRICE_UNIT!r}")
        if self.reason is not None and self.reason not in get_args(ReasonCode):
            raise ValueError("reason: a reason code of C3.2")
        if (self.reason is None) != (self.detail is None):
            raise ValueError("a reason travels with its detail")
        if self.price is None:
            if (
                self.takes_over is not None
                or self.answer_after is not None
                or self.distance_percent is not None
                or self.reason is None
            ):
                raise ValueError(
                    "a missing tipping price carries only a reason and a detail"
                )
            return
        if self.answer_after not in get_args(Answer):
            raise ValueError(f"answer_after: one of {get_args(Answer)}")
        if (self.answer_after == "chosen") != (self.takes_over is not None):
            raise ValueError(
                "takes_over names a rotation exactly when the answer is chosen"
            )
        if (self.distance_percent is None) != (self.reason is not None):
            raise ValueError("a missing distance carries a reason, a present one none")


@dataclass(frozen=True)
class TippingPrice:
    """The tipping price above and below today's soybean price. PROPOSED.

    ``decision`` is the answer at today's declared price. ``reason`` and
    ``detail`` are set when both tipping points are missing for one shared
    cause (today's price missing or outside the range).
    """

    today: float | None
    price_range: PriceRange
    decision: Decision
    up: TippingPoint
    down: TippingPoint
    reason: ReasonCode | None
    detail: str | None
    unit: str = PRICE_UNIT

    def __post_init__(self) -> None:
        if self.unit != PRICE_UNIT:
            raise ValueError(f"unit: {PRICE_UNIT!r}")
        if self.reason is not None and self.reason not in get_args(ReasonCode):
            raise ValueError("reason: a reason code of C3.2")
        if (self.reason is None) != (self.detail is None):
            raise ValueError("a reason travels with its detail")
        if self.up.direction != "up" or self.down.direction != "down":
            raise ValueError("up looks up and down looks down")


def _check_soybean_ids(
    soybean_crop_ids: Collection[str], facts: EconomicFacts
) -> dict[str, GrainCrop]:
    """The named grain crops by crop_id, in the order named, once each."""
    # A str is a Collection[str]: it would be read letter by letter.
    # ValueError, not TypeError: one exception type for every misuse.
    if isinstance(soybean_crop_ids, str):
        raise ValueError("soybean_crop_ids: a collection of crop_ids, not a text")  # noqa: TRY004
    try:
        named = list(soybean_crop_ids)
    except TypeError:
        raise ValueError("soybean_crop_ids: a collection of crop_ids") from None
    # Checked before any hashing, so an unhashable item is a ValueError too.
    for crop_id in named:
        if not isinstance(crop_id, str):
            raise ValueError("soybean_crop_ids: a crop_id is a text")  # noqa: TRY004
    ids = tuple(dict.fromkeys(named))
    if not ids:
        raise ValueError("soybean_crop_ids: at least one crop_id")
    crops = {crop.crop_id: crop for crop in facts.crops}
    matched: dict[str, GrainCrop] = {}
    for crop_id in ids:
        crop = crops.get(crop_id)
        if crop is None:
            raise ValueError(
                f"soybean_crop_ids: {crop_id!r} is not in the economic facts"
            )
        if not isinstance(crop, GrainCrop):
            # One exception type for every structural misuse, as the brief asks.
            raise ValueError(  # noqa: TRY004
                f"soybean_crop_ids: {crop_id!r} is a {crop.kind} crop, not a grain "
                "crop with a price"
            )
        matched[crop_id] = crop
    return matched


def _todays_price(
    soybeans: Mapping[str, GrainCrop],
) -> tuple[float | None, str | None]:
    """Today's soybean price, or None with the detail of what is missing."""
    prices = {crop_id: crop.price for crop_id, crop in soybeans.items()}
    present = {price.value for price in prices.values() if price.value is not None}
    if len(present) > 1:
        raise ValueError(
            "soybean_crop_ids: the named crops carry different prices; one "
            "soybean price is asked"
        )
    # PROPOSED: one named crop without a price makes today's price missing,
    # even when another named crop has one.
    missing = [
        f"the price of {crop_id!r} is missing ("
        + (
            _reason_text(price.missing.reason, price.missing.detail)
            if price.missing is not None
            else _reason_text(None, None)
        )
        + ")"
        for crop_id, price in prices.items()
        if price.value is None
    ]
    if missing:
        return None, "today's soybean price is not known: " + "; ".join(missing)
    (today,) = present
    return today, None


def _facts_at(
    facts: EconomicFacts, ids: Collection[str], price: float
) -> EconomicFacts:
    """A copy of ``facts`` with every named crop at ``price``; the input is kept."""
    data = facts.model_dump(mode="json")
    for crop in data["crops"]:
        if crop["crop_id"] in ids:
            crop["price"] = {
                "value": price,
                "unit": PRICE_UNIT,
                "provenance": _TRIED_PROVENANCE,
                "source": _TRIED_SOURCE,
                "range_missing": {
                    "reason": "NOT_APPLICABLE",
                    "detail": _TRIED_NO_RANGE,
                },
            }
    return EconomicFacts.model_validate(data)


def _margins(
    options: tuple[TippingOption, ...],
    facts: EconomicFacts,
    year_counts: Mapping[str, int | None] | None,
    margin_of: str,
) -> list[MarginResult]:
    picked = []
    for option in options:
        margin = compute_rotation_margin(option.years, facts, year_counts)
        picked.append(
            margin.average if margin_of == "average" else margin.by_kind[margin_of]
        )
    return picked


def _decide(
    options: tuple[TippingOption, ...],
    margins: list[MarginResult],
    strictness: Strictness,
) -> Decision:
    return choose_rotation(
        (
            RotationOption(rotation_id=o.rotation_id, margin=m, limit=o.limit)
            for o, m in zip(options, margins, strict=True)
        ),
        strictness,
    )


def _missing_point(
    direction: Direction, reason: ReasonCode, detail: str
) -> TippingPoint:
    return TippingPoint(
        direction=direction,
        price=None,
        takes_over=None,
        answer_after=None,
        distance_percent=None,
        reason=reason,
        detail=detail,
    )


def _found_point(
    direction: Direction, price: float, after: Decision, today: float
) -> TippingPoint:
    if today == 0:
        distance, reason, detail = (
            None,
            "NOT_COMPUTABLE",
            "today's soybean price is zero, so the distance in percent is not computed",
        )
    else:
        # PROPOSED: the distance of the tipping price from today's, in percent
        # of today's price (negative below today).
        distance, reason, detail = (price - today) / today * 100, None, None
    return TippingPoint(
        direction=direction,
        price=price,
        takes_over=after.chosen,
        answer_after=after.answer,
        distance_percent=distance,
        reason=reason,
        detail=detail,
    )


def find_tipping_price(
    options: Sequence[TippingOption],
    facts: EconomicFacts,
    year_counts: Mapping[str, int | None] | None,
    soybean_crop_ids: Collection[str],
    price_range: PriceRange,
    strictness: Strictness,
    margin_of: str = "average",
) -> TippingPrice:
    """The soybean prices nearest today's at which the answer changes. PROPOSED.

    ``options`` are the rotations to choose from; ``facts`` the declared
    economic facts; ``year_counts`` as ``compute_rotation_margin`` takes it;
    ``soybean_crop_ids`` the grain crops whose price is the soybean price;
    ``price_range`` the range the user declares; ``strictness`` as
    ``choose_rotation`` takes it; ``margin_of`` ``"average"`` or one kind of
    ``KINDS_OF_YEAR`` (the margin the ranking reads). Raises ``ValueError`` on
    structural misuse (see README.md); a missing input is never an exception
    but a missing tipping point with its reason.
    """
    options = tuple(options)
    if margin_of not in MARGINS_OF:
        raise ValueError(f"margin_of: one of {MARGINS_OF}")
    if not isinstance(price_range, PriceRange):
        raise ValueError("price_range: a PriceRange")  # noqa: TRY004
    soybeans = _check_soybean_ids(soybean_crop_ids, facts)
    today, today_missing = _todays_price(soybeans)
    # The decision at today's price: the real engine on the facts as declared.
    decision = _decide(
        options, _margins(options, facts, year_counts, margin_of), strictness
    )

    def shared(reason: ReasonCode, detail: str) -> TippingPrice:
        return TippingPrice(
            today=today,
            price_range=price_range,
            decision=decision,
            up=_missing_point("up", reason, detail),
            down=_missing_point("down", reason, detail),
            reason=reason,
            detail=detail,
        )

    if today is None:
        return shared("MISSING_INPUT", today_missing)
    low, high = price_range.low, price_range.high
    if not low <= today <= high:
        # PROPOSED: not a ValueError; the range is the user's to widen.
        return shared(
            "NOT_APPLICABLE",
            f"today's soybean price {today!r} {PRICE_UNIT} is outside the "
            f"declared range ({price_range.text()})",
        )

    # The only two engine evaluations on a copy of the facts: at both ends.
    at_low = _margins(options, _facts_at(facts, soybeans, low), year_counts, margin_of)
    at_high = _margins(
        options, _facts_at(facts, soybeans, high), year_counts, margin_of
    )

    # The margin is linear in the price (price * yield - cost, summed and
    # averaged): its intercept and slope from the two evaluations.
    # PROPOSED (fix round 1): a margin missing at an end is missing for a
    # reason other than the soybean price, so it is missing at every price.
    # It gets no line and travels unchanged into choose_rotation, whose own
    # rules say whether it blocks the answer.
    lines: list[tuple[float, float] | None] = []
    for m_low, m_high in zip(at_low, at_high, strict=True):
        if m_low.value is None or m_high.value is None:
            lines.append(None)
            continue
        slope = (m_high.value - m_low.value) / (high - low)
        lines.append((m_low.value - slope * low, slope))
    absent = [
        m_low if m_low.value is None else m_high
        for m_low, m_high in zip(at_low, at_high, strict=True)
    ]

    def answer_at(price: float) -> Decision:
        # The margin at a price from its line; no new copy of the facts.
        margins = [
            missing if line is None else MarginResult(value=line[0] + line[1] * price)
            for line, missing in zip(lines, absent, strict=True)
        ]
        return _decide(options, margins, strictness)

    present = [line for line in lines if line is not None]
    crossings = set()
    for i, (a_i, b_i) in enumerate(present):
        for a_j, b_j in present[i + 1 :]:
            if b_i != b_j:
                price = (a_j - a_i) / (b_i - b_j)
                if low < price < high:
                    crossings.add(price)
    breakpoints = sorted(crossings)
    here = (decision.answer, decision.chosen, decision.tied)
    no_change = f"{NO_CHANGE} ({price_range.text()})"

    def search(direction: Direction, beyond: list[float], end: float) -> TippingPoint:
        """The first edge, from today outwards, past which the answer differs.

        ``beyond`` holds the breakpoints strictly beyond today, nearest first.
        The answer is evaluated in the middle of each interval, never at a
        breakpoint (an exact tie there is not resolved by design). PROPOSED
        (fix round 1): the first interval starts at today itself, so when the
        answer right next to today differs from today's (today's price is on
        a crossing), the tipping point is today, distance 0. No breakpoint is
        compared with today for equality.
        """
        edges = [today, *beyond, end]
        for near, far in pairwise(edges):
            if near == far:
                continue  # today at the end of the range: nothing beyond it
            after = answer_at((near + far) / 2)
            if (after.answer, after.chosen, after.tied) != here:
                return _found_point(direction, near, after, today)
        return _missing_point(direction, "NOT_APPLICABLE", no_change)

    up = search("up", [b for b in breakpoints if b > today], high)
    down = search("down", [b for b in reversed(breakpoints) if b < today], low)
    return TippingPrice(
        today=today,
        price_range=price_range,
        decision=decision,
        up=up,
        down=down,
        reason=None,
        detail=None,
    )
