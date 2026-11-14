"""Interfaces the rotation route needs that are not in ``adapters/ports.py``.

The route in ``api/rotations.py`` depends only on these interfaces and on
``adapters.ports.ClimateSource``. It never imports a concrete adapter or
engine. Until the real implementations exist, ``api/standins.py`` supplies
stand-ins that return only typed absences.

Status: PROPOSED (blueprint section 3.7). The shapes below are a design of the
builder session of unit ``l2/api-one-rotation``.

Rules:

- An engine or a source that cannot produce a value says so by *returning* a
  typed absence (``None`` plus a reason code of contracts/CONVENTIONS.md
  C3.2). Any exception it raises is a defect and becomes ``INTERNAL_ERROR``.
- Nothing here names a parameter value, a threshold or a unit.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from adapters.ports import ClimateResult, SourceInfo

# --- payload aliases: one alias, one line to change later --------------------

# One item of the contract "Rotation definition", as submitted by the client.
# Replaced by the "Rotation definition" contract model when it is merged.
RotationPayload = Mapping[str, Any]

# The contract "Rotation calendar". Replaced by its contract model.
CalendarPayload = Mapping[str, Any]

# The contract "Results per rotation". Replaced by
# ``contracts.results.ResultsPerRotation`` when it is merged.
ResultsPayload = Mapping[str, Any]

# The contract "Site data: soil and slope". Replaced by
# ``contracts.inputs.SiteSoilSlope`` when it is merged.
SoilSlopePayload = Mapping[str, Any]

# PROPOSED: contract identifiers of the two site-data sources, as they appear
# in ``SourceInfo.contract``. The climate one follows the example in
# adapters/ports.py; the soil-and-slope one follows the unmerged proposal of
# contracts/inputs/.
CLIMATE_CONTRACT = "site_data_climate"
SOIL_SLOPE_CONTRACT = "site_data_soil_slope"

# --- closed vocabularies ------------------------------------------------------

# contracts/CONVENTIONS.md C3.2. Replaced by the ``ReasonCode`` of the
# contracts package when it is merged.
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

# PROPOSED: the state of one engine module for this run.
#   available      the module ran and produced its outputs
#   degraded       the module ran, some of its outputs are missing
#   not_available  the module produced nothing; ``reason`` says why
ModuleState = Literal["available", "degraded", "not_available"]


# --- engines ------------------------------------------------------------------


@dataclass(frozen=True)
class Missing:
    """Why a payload is absent (C3.1): a C3.2 reason code and optional detail."""

    reason: ReasonCode
    detail: str | None = None


@dataclass(frozen=True)
class ModuleStatus:
    """State of one engine module. ``reason`` is required unless available."""

    id: str
    state: ModuleState
    reason: ReasonCode | None = None
    detail: str | None = None


@dataclass(frozen=True)
class EnginesResult:
    """What the engines return for one rotation.

    ``result_missing`` is set exactly when ``result`` is ``None``.
    """

    calendar: CalendarPayload | None
    result: ResultsPayload | None
    result_missing: Missing | None
    modules: Sequence[ModuleStatus] = field(default_factory=tuple)


@dataclass(frozen=True)
class SoilSlopeResult:
    """The answer of a soil-and-slope source: the data, or None with the reason."""

    data: SoilSlopePayload | None
    source: SourceInfo


class RotationEngines(Protocol):
    """Runs every engine for one rotation and returns typed absences, never raises.

    The real implementation calls the engine entry points of
    contracts/ENTRYPOINTS.md.
    """

    def run(
        self,
        rotation: RotationPayload,
        climate: ClimateResult,
        soil_slope: SoilSlopeResult,
    ) -> EnginesResult: ...


# --- soil and slope -----------------------------------------------------------


class SoilSlopeSource(Protocol):
    """Anything that can supply the soil and slope data of a field.

    Same rules as ``adapters.ports.ClimateSource``: a source that does not
    answer is a result (``data=None``, ``state="unavailable"`` with a reason),
    never an exception.
    """

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult: ...


# --- rotation validation ------------------------------------------------------


@dataclass(frozen=True)
class ErrorDetail:
    """One problem found in the request.

    ``path`` is dotted (``components.0.crop``). A ``RotationValidator`` gives
    paths relative to the rotation object; the route prefixes ``rotation``.
    ``message`` is English text for developers, never shown to users.
    """

    path: str
    code: str
    message: str


class RotationValidator(Protocol):
    """Checks one rotation. An empty list means valid.

    The real implementation loads the rotation into the "Rotation definition"
    contract model.
    """

    def validate(self, rotation: RotationPayload) -> list[ErrorDetail]: ...


# --- settings -----------------------------------------------------------------


@dataclass(frozen=True)
class RunSettings:
    """What is not a client choice.

    There are no default dates: which years of the climate record are
    requested is OPEN for the science reviewers. When either date is ``None``
    the route does not call the climate source and reports it unavailable.
    """

    start_date: dt.date | None = None  # first day, inclusive
    end_date: dt.date | None = None  # last day, inclusive

    def __post_init__(self) -> None:
        if self.has_period and self.start_date > self.end_date:
            raise ValueError("RunSettings: start_date is after end_date")

    @property
    def has_period(self) -> bool:
        return self.start_date is not None and self.end_date is not None
