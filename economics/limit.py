"""Whether one rotation meets the soil-loss limit the user declared. PROPOSED.

One public pure function, ``assess_limit``, built by unit
``l2/soil-loss-limit``. Erosion is a limit, not a cost: the soil loss of one
rotation is compared with the limit the user declared for the field, on the
average of the record and in every kind of year (``KINDS_OF_YEAR``). The rules
are arithmetic, not parameters; see ``README.md`` in this folder.

No network call, no parameter value and no limit of any kind in the code: the
limit is always a declared input (a contract ``Value``). A missing limit or a
missing soil-loss level gives "not resolved" with its reason (C3.2 of
contracts/CONVENTIONS.md), never a default.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol, get_args

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode, Value
from contracts.results.models import UNIT_SOIL_LOSS_ANNUAL

Verdict = Literal["meets", "does_not_meet", "not_resolved"]


class SoilLossLevel(Protocol):
    """A soil-loss level in t ha-1 yr-1, or missing with its reason. PROPOSED.

    Any object with these three attributes; for example the mean by kind of
    year of ``kinds_of_year.aggregate``, which this module does not import. An
    object that also has a ``unit`` attribute must say ``"t ha-1 yr-1"``.
    """

    value: float | None
    reason: ReasonCode | None
    detail: str | None


@dataclass(frozen=True)
class LimitCheck:
    """One check against the limit. PROPOSED.

    ``reason`` and ``detail`` are set exactly when the verdict is
    ``not_resolved``.
    """

    verdict: Verdict
    reason: ReasonCode | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.verdict not in get_args(Verdict):
            raise ValueError(f"verdict: one of {get_args(Verdict)}")
        if self.reason is not None and self.reason not in get_args(ReasonCode):
            raise ValueError("reason: a reason code of C3.2")
        unresolved = self.verdict == "not_resolved"
        if unresolved != (self.reason is not None) or unresolved != (
            self.detail is not None
        ):
            raise ValueError(
                "a check carries a reason and a detail exactly when it is not resolved"
            )


@dataclass(frozen=True)
class LimitAssessment:
    """One rotation against the declared soil-loss limit. PROPOSED.

    ``by_kind`` is stored as a read-only mapping, in ``KINDS_OF_YEAR`` order.
    """

    limit: float | None
    unit: str
    on_average: LimitCheck
    every_kind: LimitCheck
    by_kind: Mapping[str, LimitCheck]
    kinds_not_met: tuple[str, ...]
    kinds_not_resolved: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))


_MEETS = LimitCheck("meets")
_DOES_NOT_MEET = LimitCheck("does_not_meet")


def _reason_text(reason: str | None, detail: str | None) -> str:
    text = reason if reason is not None else "no reason given"
    if detail is not None:
        text += f": {detail}"
    return text


def _check_shape(level: SoilLossLevel, what: str) -> None:
    """Refuse a level that is not a soil-loss level in t ha-1 yr-1 (misuse)."""
    # The unit is the caller's job; an object that states one must state ours.
    if hasattr(level, "unit") and level.unit != UNIT_SOIL_LOSS_ANNUAL:
        raise ValueError(
            f"{what}: the soil-loss level has unit {level.unit!r}, "
            f"not {UNIT_SOIL_LOSS_ANNUAL!r} (C1.2)"
        )
    value = level.value
    if value is None:
        return
    # A boolean is not a soil loss, although Python treats it as a number.
    # ValueError, not TypeError: one exception type for every structural misuse.
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{what}: the soil-loss value is a real number")  # noqa: TRY004
    if not math.isfinite(value):
        raise ValueError(f"{what}: the soil-loss value is a finite number")
    if level.reason is not None:
        raise ValueError(
            f"{what}: a soil-loss level holds a value or a missing reason, "
            "never both (C3.1)"
        )


def _check_level(level: SoilLossLevel, declared: float, what: str) -> LimitCheck:
    if level.value is None:
        return LimitCheck(
            "not_resolved",
            "MISSING_INPUT",
            f"the soil loss {what} is missing "
            f"({_reason_text(level.reason, level.detail)})",
        )
    # PROPOSED: at the limit meets; compared as given, no rounding.
    return _MEETS if level.value <= declared else _DOES_NOT_MEET


def assess_limit(
    limit: Value,
    average: SoilLossLevel,
    by_kind: Mapping[str, SoilLossLevel],
) -> LimitAssessment:
    """Whether one rotation meets the declared soil-loss limit. PROPOSED.

    ``limit`` is the limit the user declared for the field, a contract
    ``Value`` in ``"t ha-1 yr-1"`` that may be missing with its reason.
    ``average`` is the soil loss on the average of the record; ``by_kind``
    the soil loss in each kind of year, with exactly the keys of
    ``KINDS_OF_YEAR``. Raises ``ValueError`` on structural misuse (see
    README.md); a missing input is never an exception but a check that is not
    resolved, with its reason.
    """
    if limit.unit != UNIT_SOIL_LOSS_ANNUAL:
        raise ValueError(
            f"limit: the unit is {limit.unit!r}, not {UNIT_SOIL_LOSS_ANNUAL!r} (C1.2)"
        )
    if limit.value is not None and limit.value < 0:
        raise ValueError("limit: a soil-loss limit is not negative")
    if set(by_kind) != set(KINDS_OF_YEAR):
        raise ValueError(
            f"by_kind: the keys are exactly KINDS_OF_YEAR {KINDS_OF_YEAR}, "
            f"got {sorted(by_kind)}"
        )
    _check_shape(average, "average")
    for kind in KINDS_OF_YEAR:
        _check_shape(by_kind[kind], f"by_kind[{kind!r}]")

    if limit.value is None:
        # The contract (C3.1) makes a missing value carry its missing part; a
        # Value built without validation may not, and that is misuse.
        if limit.missing is None:
            raise ValueError(
                "limit: a missing limit carries a missing part with its reason (C3.1)"
            )
        unresolved = LimitCheck(
            "not_resolved",
            "MISSING_INPUT",
            "the soil-loss limit of the field is not declared "
            f"({_reason_text(limit.missing.reason, limit.missing.detail)})",
        )
        return LimitAssessment(
            limit=None,
            unit=UNIT_SOIL_LOSS_ANNUAL,
            on_average=unresolved,
            every_kind=unresolved,
            by_kind={kind: unresolved for kind in KINDS_OF_YEAR},
            kinds_not_met=(),
            kinds_not_resolved=KINDS_OF_YEAR,
        )

    declared = limit.value
    on_average = _check_level(average, declared, "on average")
    checks = {
        kind: _check_level(by_kind[kind], declared, f"in the {kind} kind of year")
        for kind in KINDS_OF_YEAR
    }
    not_met = tuple(k for k in KINDS_OF_YEAR if checks[k].verdict == "does_not_meet")
    not_resolved = tuple(
        k for k in KINDS_OF_YEAR if checks[k].verdict == "not_resolved"
    )
    if not_met:
        # PROPOSED: one failing kind is enough, even if another is not resolved.
        every_kind = _DOES_NOT_MEET
    elif not_resolved:
        every_kind = LimitCheck(
            "not_resolved",
            "MISSING_INPUT",
            "the limit is not resolved in the kind of year "
            + ", ".join(not_resolved)
            + ": "
            + "; ".join(checks[k].detail for k in not_resolved),
        )
    else:
        every_kind = _MEETS
    return LimitAssessment(
        limit=declared,
        unit=UNIT_SOIL_LOSS_ANNUAL,
        on_average=on_average,
        every_kind=every_kind,
        by_kind=checks,
        kinds_not_met=not_met,
        kinds_not_resolved=not_resolved,
    )
