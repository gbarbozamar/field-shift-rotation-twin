"""Contract "Rotation calendar" (blueprint section 5). PROPOSED.

Producer: Engines (calendar engine). Consumer: Lead (erosion engine).
The field list is a proposal of a builder session for the producer to correct;
see ``README.md`` in this folder for what is PROPOSED and what is OPEN.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import model_validator

from .common import (
    ContractModel,
    DateValue,
    IsoDate,
    MonthNumber,
    NonEmptyStr,
    StatedValue,
    check_dates_in_order,
)


class AgYearStart(StatedValue):
    """C5.4: the calendar month in which the agricultural year of the case begins.

    Declared by a person per case and marked provisional until the
    determination from imagery replaces it.
    """

    payload_field: ClassVar[str] = "month"

    month: MonthNumber | None
    provisional: bool | None = None

    @model_validator(mode="after")
    def _provisional_mark(self) -> AgYearStart:
        if self.month is not None and self.provisional is None:
            raise ValueError("a start month says whether it is provisional (C5.4)")
        if self.month is None and self.provisional is not None:
            raise ValueError("a missing start month carries no provisional mark")
        return self


class CalendarPeriod(ContractModel):
    """A dated period inside a component, for cover management by period.

    What a period is depends on the soil-loss method, which is OPEN.
    """

    period_type: NonEmptyStr  # vocabulary OPEN
    start: DateValue
    end: DateValue  # inclusive

    @model_validator(mode="after")
    def _in_order(self) -> CalendarPeriod:
        check_dates_in_order(self.start, self.end, f"period {self.period_type!r}")
        return self


class CalendarComponent(ContractModel):
    """One component of the rotation, placed on the calendar."""

    component_id: NonEmptyStr
    crop_id: NonEmptyStr  # vocabulary OPEN
    start: DateValue
    end: DateValue  # inclusive
    periods: list[CalendarPeriod]

    @model_validator(mode="after")
    def _dates(self) -> CalendarComponent:
        what = f"component {self.component_id!r}"
        check_dates_in_order(self.start, self.end, what)
        for period in self.periods:
            for edge in (period.start.date, period.end.date):
                if edge is None:
                    continue
                if self.start.date is not None and edge < self.start.date:
                    raise ValueError(
                        f"{what}: a period lies outside the dates of its component"
                    )
                if self.end.date is not None and edge > self.end.date:
                    raise ValueError(
                        f"{what}: a period lies outside the dates of its component"
                    )
        return self


class RuleViolation(ContractModel):
    """One calendar rule that the calendar breaks."""

    rule: (
        NonEmptyStr  # identifier of a rule of the rotation definition; vocabulary OPEN
    )
    component_ids: list[
        NonEmptyStr
    ]  # empty when the rule concerns the calendar as a whole
    detail: NonEmptyStr | None = None


class Feasibility(ContractModel):
    """Result of the feasibility check of the calendar engine (blueprint section 8)."""

    feasible: bool
    violations: list[RuleViolation]

    @model_validator(mode="after")
    def _consistent(self) -> Feasibility:
        if self.feasible and self.violations:
            raise ValueError("a feasible calendar lists no violations")
        if not self.feasible and not self.violations:
            raise ValueError("an infeasible calendar lists at least one violation")
        return self


class RotationCalendar(ContractModel):
    """The dated calendar of one rotation on one field."""

    contract: Literal["rotation_calendar"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    rotation_id: NonEmptyStr
    ag_year_start: AgYearStart
    start_date: IsoDate  # first day the calendar is laid out for
    end_date: IsoDate  # last day, inclusive
    feasibility: Feasibility
    components: list[CalendarComponent]

    @model_validator(mode="after")
    def _consistent(self) -> RotationCalendar:
        if self.end_date < self.start_date:
            raise ValueError("calendar: ends before it starts")
        ids = [component.component_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("calendar: two components share one component_id")
        for component in self.components:
            for edge in (component.start.date, component.end.date):
                if edge is not None and not (self.start_date <= edge <= self.end_date):
                    raise ValueError(
                        f"component {component.component_id!r}: lies outside the dates of the calendar"
                    )
        for violation in self.feasibility.violations:
            for component_id in violation.component_ids:
                if component_id not in ids:
                    raise ValueError(
                        f"violation of rule {violation.rule!r}: names an unknown component {component_id!r}"
                    )
        return self
