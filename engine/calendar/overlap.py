"""Component overlap rule for rotation definitions (D72 / USER-Z). PROPOSED.

Decision D72 (USER-Z in ``docs/SCIENCE_DECISIONS.md``): initial executable
calendars reject crops overlapping on the same area. Because ``RULES`` in
``rules.py`` and ``build_rotation_calendar`` in ``build.py`` keep EP2's existing
contract unchanged until wired into the route, this module exposes the opt-in
overlap rule and feasibility helper without modifying ``RULES`` or ``build.py``.

Pure functions: no file, no network, no clock.
"""

from __future__ import annotations

from contracts.inputs.rotation_calendar import Feasibility
from contracts.rotation_definition.common import IsoDate
from contracts.rotation_definition.rotation_definition import (
    RotationComponent,
    RotationDefinition,
)

from .rules import (
    RULES,
    CalendarRule,
    Finding,
    check_feasibility,
)

NO_OVERLAPPING_COMPONENTS = "no_overlapping_components"

__all__ = [
    "NO_OVERLAPPING_COMPONENTS",
    "OVERLAP_RULE",
    "RULES_WITH_OVERLAP",
    "check_feasibility_with_overlap",
    "find_overlapping_components",
    "make_overlap_rule",
]


def _require_rotation_definition(rotation: RotationDefinition) -> None:
    if not isinstance(rotation, RotationDefinition):
        raise TypeError(
            "rotation: expected a RotationDefinition "
            "(contracts.rotation_definition.rotation_definition), "
            f"got {type(rotation).__name__}"
        )


def _placed_span(component: RotationComponent) -> tuple[IsoDate, IsoDate] | None:
    """Return ``(sowing, harvest)`` when both are present and ``harvest >= sowing``."""
    start = component.sowing.date
    end = component.harvest.date
    if start is None or end is None or end < start:
        return None
    return start, end


def _spans_overlap(
    first_start: IsoDate,
    first_end: IsoDate,
    second_start: IsoDate,
    second_end: IsoDate,
    *,
    allow_same_day_handoff: bool,
) -> bool:
    """Return True when two valid inclusive spans ``[start, end]`` overlap."""
    if first_end < second_start or second_end < first_start:
        return False
    if not allow_same_day_handoff:
        return True
    if first_start == first_end == second_start == second_end:
        return True
    return first_start < second_end and second_start < first_end


def find_overlapping_components(
    rotation: RotationDefinition, *, allow_same_day_handoff: bool = False
) -> list[Finding]:
    """Find every pair of components whose placed dates overlap.

    Only components with both ``sowing.date`` and ``harvest.date`` present and
    ``harvest.date >= sowing.date`` are compared; undated components and
    components whose harvest precedes sowing are skipped. When
    ``allow_same_day_handoff`` is true, a harvest on the same day as another
    component's sowing is permitted (unless both collapse to that single day).
    """
    _require_rotation_definition(rotation)
    dated: list[tuple[RotationComponent, IsoDate, IsoDate]] = []
    for component in rotation.components:
        span = _placed_span(component)
        if span is not None:
            dated.append((component, span[0], span[1]))

    findings: list[Finding] = []
    for index, (first, first_start, first_end) in enumerate(dated):
        for second, second_start, second_end in dated[index + 1 :]:
            if _spans_overlap(
                first_start,
                first_end,
                second_start,
                second_end,
                allow_same_day_handoff=allow_same_day_handoff,
            ):
                findings.append(
                    Finding(
                        component_ids=(first.component_id, second.component_id),
                        detail=(
                            f"component {first.component_id!r} "
                            f"({first_start.isoformat()} to "
                            f"{first_end.isoformat()}) overlaps component "
                            f"{second.component_id!r} "
                            f"({second_start.isoformat()} to "
                            f"{second_end.isoformat()})"
                        ),
                    )
                )
    return findings


def make_overlap_rule(*, allow_same_day_handoff: bool = False) -> CalendarRule:
    """Build a ``CalendarRule`` checking for overlapping components."""

    def _find(rotation: RotationDefinition) -> list[Finding]:
        return find_overlapping_components(
            rotation, allow_same_day_handoff=allow_same_day_handoff
        )

    return CalendarRule(rule_id=NO_OVERLAPPING_COMPONENTS, find=_find)


OVERLAP_RULE: CalendarRule = make_overlap_rule(allow_same_day_handoff=False)
RULES_WITH_OVERLAP: tuple[CalendarRule, ...] = (*RULES, OVERLAP_RULE)


def check_feasibility_with_overlap(
    rotation: RotationDefinition, *, allow_same_day_handoff: bool = False
) -> Feasibility:
    """Check ``rotation`` against ``RULES`` plus ``NO_OVERLAPPING_COMPONENTS``."""
    _require_rotation_definition(rotation)
    rules = (
        RULES_WITH_OVERLAP
        if not allow_same_day_handoff
        else (*RULES, make_overlap_rule(allow_same_day_handoff=True))
    )
    return check_feasibility(rotation, rules)
