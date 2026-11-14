"""Calendar engine: from a rotation definition to a rotation calendar. PROPOSED.

Entry point EP2 of ``contracts/ENTRYPOINTS.md``. Every choice this file makes
where EP2 is silent is listed in ``README.md`` in this folder, marked PROPOSED,
with the OPEN question a person has to answer.

Pure functions: no file, no network, no clock. No date is invented: every
date of the calendar is a date the definition gives.
"""

from __future__ import annotations

from contracts.inputs.common import DateValue, Missing
from contracts.inputs.rotation_calendar import (
    AgYearStart,
    CalendarComponent,
    RotationCalendar,
)
from contracts.rotation_definition.common import DateValue as DeclaredDate
from contracts.rotation_definition.rotation_definition import (
    RotationComponent,
    RotationDefinition,
)

from .rules import (
    HARVEST_NOT_BEFORE_SOWING,
    RULES,
    CalendarRule,
    check_feasibility,
    harvest_before_sowing,
)


class NoValidCalendarForm(Exception):
    """The ``RotationCalendar`` model has no valid form for this definition.

    Not one of the caller defects of rule G5 of ``contracts/ENTRYPOINTS.md``
    and not a rule violation: a gap between the two contracts. The cases and
    the question for people are in ``README.md`` under "No valid form".
    """


def build_rotation_calendar(rotation: RotationDefinition) -> RotationCalendar:
    """Entry point EP2: the rotation calendar of one rotation definition.

    Returns a calendar, feasible or not. A rotation that breaks a rule gives
    a calendar with ``feasibility.feasible`` false and the violation named.

    Raises ``TypeError`` when ``rotation`` is not a ``RotationDefinition``
    (rule G5), and ``NoValidCalendarForm`` when the calendar model has no
    valid form for the definition.
    """
    return _build(rotation, RULES)


def _build(
    rotation: RotationDefinition, rules: tuple[CalendarRule, ...]
) -> RotationCalendar:
    if not isinstance(rotation, RotationDefinition):
        raise TypeError(
            "rotation: expected a RotationDefinition "
            "(contracts.rotation_definition.rotation_definition), "
            f"got {type(rotation).__name__}"
        )

    ids = [component.component_id for component in rotation.components]
    if len(ids) != len(set(ids)):
        raise NoValidCalendarForm(
            "two components share one component_id: a rotation calendar "
            "cannot list both"
        )

    components = [_place(component) for component in rotation.components]

    placed = [
        edge.date
        for component in components
        for edge in (component.start, component.end)
        if edge.date is not None
    ]
    if not placed:
        raise NoValidCalendarForm(
            "the definition gives no date that can be placed: a rotation "
            "calendar needs a start_date and an end_date and neither can be "
            "missing"
        )

    return RotationCalendar(
        contract="rotation_calendar",
        example_data=rotation.example_data,
        case_id=rotation.case_id,
        field_id=rotation.field_id,
        rotation_id=rotation.rotation_id,
        ag_year_start=AgYearStart(
            month=None,
            missing=Missing(
                reason="NOT_DECLARED",
                detail=(
                    "the rotation definition carries no start month of the "
                    "agricultural year (C5.4)"
                ),
            ),
        ),
        start_date=min(placed),
        end_date=max(placed),
        feasibility=check_feasibility(rotation, rules),
        components=components,
    )


def _place(component: RotationComponent) -> CalendarComponent:
    """One component of the definition as one component of the calendar."""
    if harvest_before_sowing(component):
        # The calendar model rejects a component that ends before it starts,
        # so neither date can be placed (EP2: a date that cannot be placed).
        start = _cannot_be_placed()
        end = _cannot_be_placed()
    else:
        start = _carry(component.sowing)
        end = _carry(component.harvest)
    return CalendarComponent(
        component_id=component.component_id,
        crop_id=component.crop_id,
        start=start,
        end=end,
        periods=[],
    )


def _carry(declared: DeclaredDate) -> DateValue:
    """The date as the definition gives it, in the date shape of the calendar.

    A date stays the same date with its label, source and assumption mark. A
    missing date stays missing with its reason and its detail.
    """
    missing = None
    if declared.missing is not None:
        missing = Missing(
            reason=declared.missing.reason, detail=declared.missing.detail
        )
    return DateValue(
        date=declared.date,
        missing=missing,
        provenance=declared.provenance,
        source=declared.source,
        assumption=declared.assumption,
    )


def _cannot_be_placed() -> DateValue:
    return DateValue(
        date=None,
        missing=Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                "the definition gives a harvest before the sowing "
                f"(rule {HARVEST_NOT_BEFORE_SOWING})"
            ),
        ),
    )
