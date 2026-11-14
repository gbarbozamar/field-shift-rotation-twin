"""Feasibility check of the calendar engine: the mechanism and the rules. PROPOSED.

The mechanism: a rule has an identifier and a function that reads a rotation
definition and returns the places where the rotation breaks the rule. A
violation names the rule and the components (``RuleViolation`` of
``contracts/inputs/rotation_calendar.py``).

The rules: only the ones the rotation definition contract itself states.
The repository defines no agronomic calendar rule (sowing windows, minimum
intervals, crop sequences) and this file holds none: each of those is an OPEN
question for people. See ``README.md`` in this folder.

Pure functions: no file, no network, no clock.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from contracts.inputs.rotation_calendar import Feasibility, RuleViolation
from contracts.rotation_definition.rotation_definition import (
    RotationComponent,
    RotationDefinition,
)


@dataclass(frozen=True)
class Finding:
    """One place where a rotation breaks a rule."""

    # Empty when the rule concerns the rotation as a whole.
    component_ids: tuple[str, ...]
    detail: str | None = None


@dataclass(frozen=True)
class CalendarRule:
    """One calendar rule: its identifier and the function that checks it."""

    rule_id: str
    find: Callable[[RotationDefinition], list[Finding]]


def check_feasibility(
    rotation: RotationDefinition, rules: tuple[CalendarRule, ...]
) -> Feasibility:
    """Check ``rotation`` against ``rules``, in the order of ``rules``.

    A rotation that breaks no rule is feasible. Every finding of every rule
    becomes one violation that names the rule and the components.
    """
    violations = [
        RuleViolation(
            rule=rule.rule_id,
            component_ids=list(finding.component_ids),
            detail=finding.detail,
        )
        for rule in rules
        for finding in rule.find(rotation)
    ]
    return Feasibility(feasible=not violations, violations=violations)


def harvest_before_sowing(component: RotationComponent) -> bool:
    """True when both dates are present and the harvest is before the sowing."""
    return (
        component.sowing.date is not None
        and component.harvest.date is not None
        and component.harvest.date < component.sowing.date
    )


def _find_harvest_before_sowing(rotation: RotationDefinition) -> list[Finding]:
    return [
        Finding(
            component_ids=(component.component_id,),
            detail=(
                f"harvest {component.harvest.date.isoformat()} is before "
                f"sowing {component.sowing.date.isoformat()}"
            ),
        )
        for component in rotation.components
        if harvest_before_sowing(component)
    ]


def _find_positions_not_numbered_from_one(
    rotation: RotationDefinition,
) -> list[Finding]:
    positions = sorted(component.position for component in rotation.components)
    if positions == list(range(1, len(positions) + 1)):
        return []
    return [
        Finding(
            component_ids=(),
            detail=(
                "the positions are not the numbers from 1 to the number of "
                "components, none repeated and none skipped"
            ),
        )
    ]


# The rules this engine checks. PROPOSED, both the rules and their identifiers.
# Each one repeats a rule that the model of the rotation definition contract
# (contracts/rotation_definition/rotation_definition.py) enforces when a
# definition is loaded, so a definition that was loaded and not changed
# afterwards breaks none of them.
HARVEST_NOT_BEFORE_SOWING = "harvest_not_before_sowing"
POSITIONS_NUMBER_THE_COMPONENTS = "positions_number_the_components"

RULES: tuple[CalendarRule, ...] = (
    CalendarRule(HARVEST_NOT_BEFORE_SOWING, _find_harvest_before_sowing),
    CalendarRule(
        POSITIONS_NUMBER_THE_COMPONENTS, _find_positions_not_numbered_from_one
    ),
)
