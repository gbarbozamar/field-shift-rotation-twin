"""Interfaces the rotation route needs that are not in ``adapters/ports.py``.

The route in ``api/rotations.py`` depends only on these interfaces and on the
two source interfaces of ``adapters/ports.py``. It never imports a concrete
adapter or engine. ``api/engines.py`` implements ``RotationEngines`` on the
engine entry points of contracts/ENTRYPOINTS.md; ``api/standins.py`` supplies
the stand-ins of the interfaces that have no real implementation yet.

Status: PROPOSED (blueprint section 3.7). The shapes below are a design of the
builder sessions of units ``l2/api-one-rotation`` and ``l2/engine-runner``.

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
from typing import TYPE_CHECKING, Any, Literal, Protocol, get_args

from adapters.ports import (
    ClimateResult,
    SoilSlopePayload,
    SoilSlopeResult,
    SoilSlopeSource,
)
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.results.models import ReasonCode, ResultsPerRotation, ResultsTable

if TYPE_CHECKING:
    # Only for the annotation of ``DecisionLayer``: never imported at run time,
    # so the app imports nothing of the decision output at start-up.
    from contracts.decision_output import DecisionOutput

__all__ = [
    "CLIMATE_CONTRACT",
    "SOIL_SLOPE_CONTRACT",
    "CalendarPayload",
    "DecisionLayer",
    "EnginesResult",
    "ErrorDetail",
    "Missing",
    "ModuleState",
    "ModuleStatus",
    "PhaseResult",
    "PlantLayer",
    "PlantParts",
    "ReasonCode",
    "ResultsPayload",
    "RotationEngines",
    "RotationPayload",
    "RotationValidator",
    "RunSettings",
    "SoilSlopePayload",
    "SoilSlopeResult",
    "SoilSlopeSource",
]

# --- payload types: one line each --------------------------------------------

# One item of the contract "Rotation definition", as submitted by the client:
# a JSON object. The ``RotationValidator`` loads it into
# ``contracts.rotation_definition.RotationDefinition``, and the engine runner
# passes that instance to EP2.
RotationPayload = Mapping[str, Any]

# The contract "Rotation calendar".
CalendarPayload = RotationCalendar

# The contract "Results per rotation".
ResultsPayload = ResultsPerRotation

# ``SoilSlopePayload`` (the contract "Site data: soil and slope"),
# ``SoilSlopeResult`` and ``SoilSlopeSource`` live in adapters/ports.py, next
# to the climate ones, and are re-exported here.


# Contract identifiers of the two site-data sources, as they appear in
# ``SourceInfo.contract``: the ``contract`` value of each model.
def _contract_of(model: type) -> str:
    (value,) = get_args(model.model_fields["contract"].annotation)
    return value


CLIMATE_CONTRACT: str = _contract_of(SiteClimate)
SOIL_SLOPE_CONTRACT: str = _contract_of(SiteSoilSlope)

# --- closed vocabularies ------------------------------------------------------

# ``ReasonCode`` is the C3.2 list of contracts/results/models.py.

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

    ``result_missing`` is set exactly when ``result`` is ``None`` (checked by
    the route). ``values_present`` and ``values_missing`` count the indicator
    values inside ``result`` (``api.engines.count_values``), so the route can
    derive the outcome without reading the result: both are zero without a
    result, and with a result they count at least one value. A part in the
    not-built form (D12) counts as one missing value.
    """

    calendar: CalendarPayload | None
    result: ResultsPayload | None
    result_missing: Missing | None
    modules: Sequence[ModuleStatus] = field(default_factory=tuple)
    values_present: int = 0
    values_missing: int = 0
    # One item per phase of the rotation (D109, PROPOSED): the first is the
    # calendar unchanged and equals the fields above. Empty from an
    # implementation that gives no phases; the route then writes one.
    phases: Sequence[PhaseResult] = ()

    def __post_init__(self) -> None:
        for name in ("values_present", "values_missing"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"EnginesResult: {name} is a count")
        counted = self.values_present + self.values_missing
        if self.result is None and counted:
            raise ValueError("EnginesResult: values are counted only in a result")
        if self.result is not None and not counted:
            raise ValueError("EnginesResult: a result counts its values")
        if self.phases:
            first = self.phases[0].result
            if (first.calendar, first.result, first.result_missing) != (
                self.calendar,
                self.result,
                self.result_missing,
            ) or tuple(first.modules) != tuple(self.modules):
                raise ValueError("EnginesResult: the first phase is the run itself")


@dataclass(frozen=True)
class PhaseResult:
    """The run of one phase of the rotation (decision D109 of issue #77).

    ``scenario_id`` is the phase's identifier (``phase_1`` ... ``phase_N``,
    PROPOSED); ``first_ag_year`` the agricultural year (C5.3) of the calendar
    EP2 built that comes first in this phase, ``None`` when it cannot be told
    (no calendar, or no start month). ``result`` holds no phases itself.
    """

    scenario_id: str
    first_ag_year: int | None
    result: EnginesResult

    def __post_init__(self) -> None:
        if self.result.phases:
            raise ValueError("PhaseResult: the run of one phase holds no phases")


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

    The real implementation (``api/rotation_validator.py``) loads the rotation
    into the "Rotation definition" contract model.
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


# --- decision layer -----------------------------------------------------------


class DecisionLayer(Protocol):
    """Turns a results table into a decision output document, or says why not.

    PROPOSED (unit ``l2/decision-route``). The route ``POST /api/decisions/run``
    depends on this interface only. The default implementation
    (``api/decision_layer.py``) finds the function of sub-lane L2b by name on
    each request. ``Missing`` is a typed absence (C3.1); what an implementation
    raises is answered by the route as a typed absence too.
    """

    def decide(
        self, table: ResultsTable, *, example_data: bool
    ) -> DecisionOutput | Missing: ...


# --- plant layer --------------------------------------------------------------


@dataclass(frozen=True)
class PlantParts:
    """What the plant route needs of the plant layer. PROPOSED (S-031, R24).

    ``request_model`` is ``contracts.plant_answer.PlantRequest`` (the body is
    loaded into it), ``answer_model`` is ``contracts.plant_answer.PlantAnswer``
    (what ``answer_plant`` returns is checked to be one), and
    ``answer_plant`` is ``economics.plant.answer_plant``. Typed ``Any`` so
    this module imports nothing of the plant layer.
    """

    request_model: Any
    answer_model: Any
    answer_plant: Any


class PlantLayer(Protocol):
    """Gives the parts of the plant layer, or says why it is not built.

    PROPOSED (unit ``l2/plant-layer-by-name``). The route
    ``POST /api/plant/run`` depends on this interface only. The default
    implementation (``api/plant_layer.py``, ``DiscoveredPlantLayer``) finds
    the parts by name on each request. ``Missing`` (``NOT_AVAILABLE``) means
    "not built"; what an implementation raises is a defect, which the route
    answers ``500``.
    """

    def parts(self) -> PlantParts | Missing: ...
