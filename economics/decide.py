"""Which rotation to plant: the most margin within the soil-loss limit. PROPOSED.

One public pure function, ``choose_rotation``, built by unit
``l2/decision-rule`` (S-015). Among the rotations that meet the soil-loss
limit under the chosen strictness, the one with the most margin per hectare
and year is chosen. Erosion is a limit, not a cost: it never enters the
margin. The rules are arithmetic, not parameters; see ``README.md`` in this
folder.

When the data cannot separate the answer the result is "not resolved" with
its reason (C3.2 of contracts/CONVENTIONS.md). A ``MarginResult`` carries no
range today (OPEN), so only an exact tie or a missing value is unseparable.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, get_args

from contracts.economic_facts import MARGIN_UNIT
from contracts.inputs.common import ReasonCode

from .limit import LimitAssessment, LimitCheck, _reason_text
from .margin import MarginResult

Strictness = Literal["on_average", "every_kind"]
Answer = Literal["chosen", "none_meets", "not_resolved"]
OptionState = Literal["chosen", "meets", "does_not_meet", "not_resolved"]


@dataclass(frozen=True)
class RotationOption:
    """One rotation to choose from. PROPOSED.

    ``margin`` is the margin to rank by (the caller picks the average or a
    kind of year); ``limit`` is its assessment against the soil-loss limit.
    """

    rotation_id: str
    margin: MarginResult
    limit: LimitAssessment


@dataclass(frozen=True)
class OptionVerdict:
    """What the decision says of one rotation. PROPOSED.

    ``limit_check`` is the check of the strictness used.
    """

    rotation_id: str
    state: OptionState
    margin: MarginResult
    limit_check: LimitCheck


@dataclass(frozen=True)
class LimitCost:
    """What meeting the limit costs against the best rotation that does not.

    PROPOSED. ``value`` is set only when a rotation that does not meet the
    limit has more margin than the chosen one; ``against`` names it.
    ``costs_nothing`` is True when no such rotation exists. Otherwise
    ``reason`` and ``detail`` say why the cost is missing. Never a default zero.
    """

    value: float | None
    against: str | None
    costs_nothing: bool
    reason: ReasonCode | None
    detail: str | None
    unit: str = MARGIN_UNIT

    def __post_init__(self) -> None:
        if self.unit != MARGIN_UNIT:
            raise ValueError(f"unit: {MARGIN_UNIT!r}")
        if self.reason is not None and self.reason not in get_args(ReasonCode):
            raise ValueError("reason: a reason code of C3.2")
        if (self.value is None) != (self.against is None):
            raise ValueError(
                "a cost value is set exactly with the rotation it is against"
            )
        if self.value is not None and (
            self.costs_nothing or self.reason is not None or self.detail is not None
        ):
            raise ValueError("a cost value carries no costs_nothing, reason or detail")
        if self.costs_nothing and (self.reason is not None or self.detail is not None):
            raise ValueError("a cost of nothing carries no reason or detail")
        if (
            self.value is None
            and not self.costs_nothing
            and (self.reason is None or self.detail is None)
        ):
            raise ValueError("a missing cost carries a reason and a detail")


@dataclass(frozen=True)
class Decision:
    """The answer to "What should I plant?". PROPOSED.

    ``options`` keeps the input order; ``tied`` lists the rotations the data
    cannot separate, else it is empty.
    """

    answer: Answer
    strictness: Strictness
    chosen: str | None
    reason: ReasonCode | None
    detail: str | None
    tied: tuple[str, ...]
    options: tuple[OptionVerdict, ...]
    limit_cost: LimitCost

    def __post_init__(self) -> None:
        if self.answer not in get_args(Answer):
            raise ValueError(f"answer: one of {get_args(Answer)}")
        if self.strictness not in get_args(Strictness):
            raise ValueError(f"strictness: one of {get_args(Strictness)}")
        if self.reason is not None and self.reason not in get_args(ReasonCode):
            raise ValueError("reason: a reason code of C3.2")
        is_chosen = self.answer == "chosen"
        if is_chosen != (self.chosen is not None):
            raise ValueError("a rotation is named exactly when the answer is chosen")
        if is_chosen == (self.reason is not None) or is_chosen == (
            self.detail is not None
        ):
            raise ValueError(
                "a decision carries a reason and a detail exactly when nothing "
                "is chosen"
            )
        if self.tied and self.answer != "not_resolved":
            raise ValueError("tied rotations only when the answer is not resolved")


def _margin_text(margin: MarginResult) -> str:
    return _reason_text(margin.reason, margin.detail)


def _check_options(options: tuple[RotationOption, ...], strictness: object) -> None:
    """Refuse structural misuse before any comparison."""
    if strictness not in get_args(Strictness):
        raise ValueError(f"strictness: one of {get_args(Strictness)}")
    if not options:
        raise ValueError("options: at least one rotation to choose from")
    seen: set[str] = set()
    first, *_ = options
    first_limit = (first.limit.limit, first.limit.unit)
    for option in options:
        rotation_id = option.rotation_id
        if not isinstance(rotation_id, str) or not rotation_id:
            raise ValueError("rotation_id: a non-empty text")
        if rotation_id in seen:
            raise ValueError(f"rotation_id: duplicate {rotation_id!r}")
        seen.add(rotation_id)
        # PROPOSED: two missing limits (None) count as the same limit.
        if (option.limit.limit, option.limit.unit) != first_limit:
            raise ValueError(
                f"{rotation_id}: judged against another soil-loss limit than "
                f"{first.rotation_id}; every rotation is judged against one limit"
            )
        margin = option.margin
        if margin.unit != MARGIN_UNIT:
            raise ValueError(
                f"{rotation_id}: the margin has unit {margin.unit!r}, "
                f"not {MARGIN_UNIT!r}"
            )
        value = margin.value
        if value is None:
            continue
        # A boolean is not a margin, although Python treats it as a number.
        # ValueError, not TypeError: one exception type for every misuse.
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValueError(f"{rotation_id}: the margin is a real number")  # noqa: TRY004
        if not math.isfinite(value):
            raise ValueError(f"{rotation_id}: the margin is a finite number")


def _check_of(option: RotationOption, strictness: Strictness) -> LimitCheck:
    if strictness == "on_average":
        return option.limit.on_average
    return option.limit.every_kind


def _verdicts(
    pairs: list[tuple[RotationOption, LimitCheck]], chosen: str | None
) -> tuple[OptionVerdict, ...]:
    return tuple(
        OptionVerdict(
            rotation_id=option.rotation_id,
            state="chosen" if option.rotation_id == chosen else check.verdict,
            margin=option.margin,
            limit_check=check,
        )
        for option, check in pairs
    )


def _limit_cost(
    chosen: RotationOption, pairs: list[tuple[RotationOption, LimitCheck]]
) -> LimitCost:
    outside = [o for o, c in pairs if c.verdict == "does_not_meet"]
    unknown = [o for o in outside if o.margin.value is None]
    if unknown:
        # PROPOSED (fix round 1): a missing margin outside the limit could be
        # the largest, so no cost is given rather than a silent lower bound.
        return LimitCost(
            value=None,
            against=None,
            costs_nothing=False,
            reason="MISSING_INPUT",
            detail="the margin of a rotation that does not meet the limit is "
            "missing, so the cost of meeting it is not known: "
            + "; ".join(f"{o.rotation_id} ({_margin_text(o.margin)})" for o in unknown),
        )
    # max keeps the first in input order on an exact tie (PROPOSED).
    best = max(outside, key=lambda o: o.margin.value, default=None)
    if best is not None and best.margin.value > chosen.margin.value:
        return LimitCost(
            value=best.margin.value - chosen.margin.value,
            against=best.rotation_id,
            costs_nothing=False,
            reason=None,
            detail=None,
        )
    return LimitCost(
        value=None, against=None, costs_nothing=True, reason=None, detail=None
    )


def _no_cost(reason: ReasonCode, detail: str) -> LimitCost:
    return LimitCost(
        value=None, against=None, costs_nothing=False, reason=reason, detail=detail
    )


def _none_meets_detail(
    pairs: list[tuple[RotationOption, LimitCheck]], strictness: Strictness
) -> str:
    if strictness == "on_average":
        return "every rotation loses more soil than the limit on average"
    named = []
    for option, _ in pairs:
        kinds = option.limit.kinds_not_met
        named.append(
            f"{option.rotation_id} ({', '.join(kinds)})"
            if kinds
            else option.rotation_id
        )
    return (
        "every rotation loses more soil than the limit in at least one kind of "
        "year: " + "; ".join(named)
    )


def _blocking_text(option: RotationOption, check: LimitCheck, top: float) -> str:
    if option.margin.value is None:
        why = f"its margin is missing ({_margin_text(option.margin)})"
    else:
        why = (
            f"its margin {option.margin.value!r} is at least the best margin "
            f"that meets the limit, {top!r}"
        )
    return f"{option.rotation_id}: {why}; the limit check: {check.detail}"


def choose_rotation(
    options: Iterable[RotationOption], strictness: Strictness
) -> Decision:
    """The rotation to plant: the most margin within the limit. PROPOSED.

    ``options`` is any iterable of ``RotationOption`` (read once).
    ``strictness`` is ``"on_average"`` or ``"every_kind"`` and picks which
    check of each ``LimitAssessment`` counts. Raises ``ValueError`` on
    structural misuse (see README.md); a missing input is never an exception
    but an answer that is not resolved, with its reason.
    """
    options = tuple(options)
    _check_options(options, strictness)
    pairs = [(option, _check_of(option, strictness)) for option in options]
    candidates = [o for o, c in pairs if c.verdict == "meets"]
    unresolved = [(o, c) for o, c in pairs if c.verdict == "not_resolved"]

    def not_resolved(
        reason: ReasonCode, detail: str, tied: tuple[str, ...] = ()
    ) -> Decision:
        return Decision(
            answer="not_resolved",
            strictness=strictness,
            chosen=None,
            reason=reason,
            detail=detail,
            tied=tied,
            options=_verdicts(pairs, None),
            limit_cost=_no_cost(
                "NOT_COMPUTABLE",
                "no rotation is chosen (the answer is not resolved), so the "
                "cost of meeting the limit is not computed",
            ),
        )

    # (a) A candidate whose margin is missing.
    missing = [o for o in candidates if o.margin.value is None]
    if missing:
        return not_resolved(
            "MISSING_INPUT",
            "the margin of a rotation that meets the limit is missing: "
            + "; ".join(f"{o.rotation_id} ({_margin_text(o.margin)})" for o in missing),
        )

    if not candidates:
        if unresolved:
            return not_resolved(
                "MISSING_INPUT",
                "no rotation is known to meet the limit, and whether these "
                "meet it is not resolved: "
                + "; ".join(f"{o.rotation_id} ({c.detail})" for o, c in unresolved),
            )
        return Decision(
            answer="none_meets",
            strictness=strictness,
            chosen=None,
            reason="NOT_APPLICABLE",
            detail=_none_meets_detail(pairs, strictness),
            tied=(),
            options=_verdicts(pairs, None),
            limit_cost=_no_cost(
                "NOT_APPLICABLE",
                "no rotation meets the limit, so there is no cost of meeting it",
            ),
        )

    top = max(o.margin.value for o in candidates)

    # (b) An option not resolved on the limit that could be the answer.
    blocking = [
        (o, c) for o, c in unresolved if o.margin.value is None or o.margin.value >= top
    ]
    if blocking:
        return not_resolved(
            "MISSING_INPUT",
            "whether these rotations meet the limit is not resolved, and they "
            "could be the answer: "
            + " | ".join(_blocking_text(o, c, top) for o, c in blocking),
        )

    # (c) An exact tie at the best margin. PROPOSED: no new reason code (C3.2).
    chosen, *others = [o for o in candidates if o.margin.value == top]
    if others:
        tied = tuple(o.rotation_id for o in (chosen, *others))
        return not_resolved(
            "NOT_COMPUTABLE",
            "the data cannot separate these rotations, which meet the limit "
            "with the same margin: " + ", ".join(tied),
            tied,
        )

    return Decision(
        answer="chosen",
        strictness=strictness,
        chosen=chosen.rotation_id,
        reason=None,
        detail=None,
        tied=(),
        options=_verdicts(pairs, chosen.rotation_id),
        limit_cost=_limit_cost(chosen, pairs),
    )
