"""Shared parts of the input contracts. PROPOSED (blueprint section 3.7).

Everything here follows ``contracts/CONVENTIONS.md``: how a value carries its
unit (C1.1), its uncertainty range (section 2), its missing state and reason
(section 3) and its provenance label and source (section 4), and how months
and dates are written (section 5).

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    model_validator,
)

# C4.1: the four provenance labels, upper case, exactly as in the sheet.
Provenance = Literal["DECLARED", "OBSERVED", "DERIVED", "SIMULATED"]

# C3.2: the closed list of reason codes.
ReasonCode = Literal[
    "NOT_DECLARED",
    "SOURCE_UNAVAILABLE",
    "NO_COVERAGE",
    "MISSING_INPUT",
    "NOT_COMPUTABLE",
    "CONTROL_FAILED",
    "NOT_AVAILABLE",
    "NOT_APPLICABLE",
]

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]

# C1.1: identifiers are lower case with underscores.
QuantityId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]

# C5.1: January is month 1 and December is month 12.
MonthNumber = Annotated[int, Field(ge=1, le=12)]

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_iso_date(value: Any) -> Any:
    """C5.2: a date is written YYYY-MM-DD and nothing else."""
    if isinstance(value, dt.datetime):
        raise ValueError("a date is written YYYY-MM-DD, without a time (C5.2)")
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        return dt.date.fromisoformat(value)
    raise ValueError("a date is written YYYY-MM-DD (C5.2)")


IsoDate = Annotated[dt.date, BeforeValidator(_parse_iso_date)]


class ContractModel(BaseModel):
    """Base of every model: unknown fields are rejected, types are not coerced."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Missing(ContractModel):
    """C3.1: the ``missing`` part of a value, with its reason code."""

    reason: ReasonCode
    detail: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _missing_input_names_the_input(self) -> Missing:
        if self.reason == "MISSING_INPUT" and self.detail is None:
            raise ValueError(
                "reason MISSING_INPUT needs a detail that names the input (C3.2)"
            )
        return self


class Range(ContractModel):
    """C2.1: an uncertainty range, in the unit of the value it travels with."""

    low: FiniteFloat
    high: FiniteFloat
    kind: NonEmptyStr  # C2.3: the closed list of labels is OPEN

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.low > self.high:
            raise ValueError("range: low is greater than high (C2.1)")
        return self


def check_source_or_assumption(
    *,
    present: bool,
    provenance: str | None,
    source: str | None,
    assumption: bool,
    what: str,
) -> None:
    """Sections 3 and 4: what a present or a missing value must and must not carry.

    Shared by single values and by the header of a series.
    """
    if present:
        if provenance is None:
            raise ValueError(
                f"{what}: a value that is not missing carries a provenance label (C4.1)"
            )
        if source is None and not assumption:
            raise ValueError(
                f"{what}: a value carries a reference to its source or the assumption mark (C4.2)"
            )
    else:
        if provenance is not None:
            raise ValueError(
                f"{what}: a missing value carries no provenance label (C4.1)"
            )
        if assumption:
            raise ValueError(f"{what}: a missing value is not an assumption")


class StatedValue(ContractModel):
    """One item that holds either a payload or a ``missing`` part, never both, never neither.

    Subclasses add the payload field (a number, a date, a month) and name it
    in ``payload_field``.
    """

    payload_field: ClassVar[str] = "value"

    missing: Missing | None = None
    provenance: Provenance | None = None
    source: NonEmptyStr | None = None
    assumption: bool = False

    @model_validator(mode="after")
    def _payload_or_missing(self) -> StatedValue:
        name = self.payload_field
        present = getattr(self, name) is not None
        if present and self.missing is not None:
            raise ValueError(
                f"{name}: an item holds a value or a missing part, never both (C3.1)"
            )
        if not present and self.missing is None:
            raise ValueError(
                f"{name}: a missing value carries a missing part with its reason (C3.1)"
            )
        check_source_or_assumption(
            present=present,
            provenance=self.provenance,
            source=self.source,
            assumption=self.assumption,
            what=name,
        )
        return self


class Value(StatedValue):
    """A number with its unit, range, provenance and source; or missing with its reason."""

    value: FiniteFloat | None  # null when missing; never zero as a stand-in (C3.1)
    unit: NonEmptyStr  # C1.1; kept when the value is missing (C3.1)
    range: Range | None = None
    range_missing: Missing | None = None  # C2.2: why there is no range

    @model_validator(mode="after")
    def _range_rules(self) -> Value:
        if self.value is None:
            if self.range is not None or self.range_missing is not None:
                raise ValueError("a missing value has no range (C2.2)")
            return self
        if self.range is not None and self.range_missing is not None:
            raise ValueError(
                "a value holds a range or the reason it has none, never both (C2.2)"
            )
        if self.range is None and self.range_missing is None:
            raise ValueError(
                "a value without a range carries the reason in range_missing (C2.2)"
            )
        if self.range is not None and not (
            self.range.low <= self.value <= self.range.high
        ):
            raise ValueError("range: the value is outside its bounds (C2.1)")
        return self


class DateValue(StatedValue):
    """A date (C5.2) with its provenance and source; or missing with its reason."""

    payload_field: ClassVar[str] = "date"

    date: IsoDate | None


def check_dates_in_order(start: DateValue, end: DateValue, what: str) -> None:
    """An interval does not end before it starts. Checked only when both dates are present."""
    if start.date is not None and end.date is not None and end.date < start.date:
        raise ValueError(f"{what}: ends before it starts")
