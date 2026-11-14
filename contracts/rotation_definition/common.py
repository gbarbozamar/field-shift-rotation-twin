"""Shared shapes of the rotation definition contract. PROPOSED (blueprint section 3.7).

The date value, its ``missing`` part, the month number and the provenance label, as
``contracts/CONVENTIONS.md`` defines them: section 3 (missing values),
section 4 (provenance and source), C5.1 (months) and C5.2 (dates).

These shapes repeat the ones of ``contracts/inputs/common.py`` on purpose.
This folder imports from no other contract folder until question Q1 of
``contracts/ENTRYPOINTS.md`` (the import path of the contract packages) is
answered; see ``README.md`` in this folder, under OPEN.

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
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

# Text that is not empty and not only white space.
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]

# C5.1: a calendar month is an integer, January 1 to December 12.
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


class DateValue(ContractModel):
    """A date (C5.2) with its provenance and source; or missing with its reason.

    The item holds a date or a ``missing`` part, never both and never
    neither (C3.1). The ``missing`` part travels inside the item, next to
    the null date.
    """

    date: IsoDate | None  # null when missing (C3.1)
    missing: Missing | None = None
    provenance: Provenance | None = None
    source: NonEmptyStr | None = None
    assumption: bool = False

    @model_validator(mode="after")
    def _date_or_missing(self) -> DateValue:
        if self.date is not None:
            if self.missing is not None:
                raise ValueError(
                    "date: an item holds a value or a missing part, never both (C3.1)"
                )
            if self.provenance is None:
                raise ValueError(
                    "date: a value that is not missing carries a provenance label (C4.1)"
                )
            if self.source is None and not self.assumption:
                raise ValueError(
                    "date: a value carries a reference to its source or the assumption mark (C4.2)"
                )
            return self
        if self.missing is None:
            raise ValueError(
                "date: a missing value carries a missing part with its reason (C3.1)"
            )
        if self.provenance is not None:
            raise ValueError("date: a missing value carries no provenance label (C4.1)")
        if self.assumption:
            raise ValueError("date: a missing value is not an assumption")
        return self
