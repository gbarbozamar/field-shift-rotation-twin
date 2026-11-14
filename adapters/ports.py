"""The seam between the API (api/) and the data adapters (adapters/).

This file is the contract between the units that build adapters and the units
that consume them:

- ``l2/power-adapter`` implements ``ClimateSource`` for NASA POWER;
- ``l2/api-one-rotation`` consumes ``ClimateSource`` and ``SoilSlopeSource``
  and never looks inside them.

A unit edits this file only when it owns both sides at once, as unit
``l2/engine-runner`` did; otherwise a change goes through the platform
developer.

Rules of the seam:

- ``get_climate`` and ``get_soil_slope`` never raise because the data source
  failed. A source that does not answer is a result: ``data`` is ``None`` and
  ``source.state`` is ``"unavailable"`` with a reason code of
  contracts/CONVENTIONS.md C3.2.
- They may raise only for a programming error (a defect), never for the
  weather of the network.
- A source says who it is without being called: ``source_id`` and
  ``contract`` are read-only attributes, the same values it writes as
  ``SourceInfo.id`` and ``SourceInfo.contract``.
- The caller never passes or receives a file path, and never chooses a cache
  key. Caching is the adapter's private business.
- Nothing here names a variable, a unit or a source parameter: those are
  decisions of the science reviewers and arrive as settings of an adapter.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, get_args

from contracts.inputs import SiteClimate, SiteSoilSlope
from contracts.inputs.common import ReasonCode

# The climate data of one field: the contract "Site data: climate".
ClimatePayload = SiteClimate

# The soil and slope data of one field: the contract "Site data: soil and slope".
SoilSlopePayload = SiteSoilSlope

# How the data of a source was obtained for this call.
#   fresh        fetched from the source during this call
#   cached       the stored first response was reused
#   unavailable  the source did not answer and nothing was stored
#   example      the accepted contract example, to be shown as example data
SourceState = Literal["fresh", "cached", "unavailable", "example"]

_REASON_CODES = get_args(ReasonCode)


@dataclass(frozen=True)
class ClimateRequest:
    """What the API asks for: one field of one case, one point, one period."""

    case_id: str
    field_id: str
    latitude: float  # decimal degrees; how the point is chosen for a field is OPEN
    longitude: float  # decimal degrees
    start_date: dt.date  # first day, inclusive
    end_date: dt.date  # last day, inclusive


@dataclass(frozen=True)
class SourceInfo:
    """Where the data came from. Shown by the interface next to every value.

    Construction fails (``ValueError``) when ``retrieved_at`` has no time zone,
    when ``state`` is ``"unavailable"`` without a ``missing_reason``, or when a
    ``missing_reason`` is given with any other state.
    """

    id: str  # identifier of the source, stable across calls
    contract: str  # the contract it fills, e.g. "site_data_climate"
    state: SourceState
    # With its time zone; None when unavailable or example.
    retrieved_at: dt.datetime | None = None
    time_zone: str | None = None  # of its daily series (C6.1)
    request: Mapping[str, Any] | None = None  # what was asked of the source
    attribution: str | None = None  # reference to the ATTRIBUTIONS.md entry
    missing_reason: ReasonCode | None = None  # C3.2; exactly when unavailable
    detail: str | None = None  # optional English text for developers

    def __post_init__(self) -> None:
        if self.retrieved_at is not None and (
            not isinstance(self.retrieved_at, dt.datetime)
            or self.retrieved_at.utcoffset() is None
        ):
            raise ValueError(
                f"source {self.id!r}: retrieved_at is a datetime with its time zone"
            )
        if self.state == "unavailable":
            if self.missing_reason is None:
                raise ValueError(
                    f"source {self.id!r}: an unavailable source needs a missing_reason"
                )
        elif self.missing_reason is not None:
            raise ValueError(
                f"source {self.id!r}: missing_reason is given only when the state is "
                f"'unavailable', not {self.state!r}"
            )
        if self.missing_reason is not None and self.missing_reason not in _REASON_CODES:
            raise ValueError(
                f"source {self.id!r}: missing_reason is a reason code of C3.2"
            )


@dataclass(frozen=True)
class ClimateResult:
    """The answer of a climate source: the data, or None with the reason in source."""

    data: ClimatePayload | None
    source: SourceInfo


class ClimateSource(Protocol):
    """Anything that can supply the climate data of a field."""

    @property
    def source_id(self) -> str: ...  # the ``SourceInfo.id`` it writes

    @property
    def contract(self) -> str: ...  # the ``SourceInfo.contract`` it writes

    def get_climate(self, request: ClimateRequest) -> ClimateResult: ...


@dataclass(frozen=True)
class SoilSlopeResult:
    """The answer of a soil-and-slope source: the data, or None with the reason in source."""

    data: SoilSlopePayload | None
    source: SourceInfo


class SoilSlopeSource(Protocol):
    """Anything that can supply the soil and slope data of a field."""

    @property
    def source_id(self) -> str: ...  # the ``SourceInfo.id`` it writes

    @property
    def contract(self) -> str: ...  # the ``SourceInfo.contract`` it writes

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult: ...
