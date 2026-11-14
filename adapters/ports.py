"""The seam between the API (api/) and the data adapters (adapters/).

This file is the contract between two units built in parallel:

- ``l2/power-adapter`` implements ``ClimateSource`` for NASA POWER;
- ``l2/api-one-rotation`` consumes ``ClimateSource`` and never looks inside it.

Neither unit edits this file. A change goes through the platform developer,
because it changes both sides at once.

Rules of the seam:

- ``get_climate`` never raises because the data source failed. A source that
  does not answer is a result: ``data`` is ``None`` and ``source.state`` is
  ``"unavailable"`` with a reason code of contracts/CONVENTIONS.md C3.2.
- It may raise only for a programming error (a defect), never for the weather
  of the network.
- The caller never passes or receives a file path, and never chooses a cache
  key. Caching is the adapter's private business.
- Nothing here names a variable, a unit or a source parameter: those are
  decisions of the science reviewers and arrive as settings of an adapter.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

# The climate data of one field, in the shape of the contract
# "Site data: climate". It is a plain JSON-ready mapping today. When
# contracts/inputs/ is merged (pull request #54) this alias becomes
# ``contracts.inputs.SiteClimate`` and nothing else in this file changes.
ClimatePayload = Mapping[str, Any]

# How the data of a source was obtained for this call.
#   fresh        fetched from the source during this call
#   cached       the stored first response was reused
#   unavailable  the source did not answer and nothing was stored
#   example      the accepted contract example, to be shown as example data
SourceState = Literal["fresh", "cached", "unavailable", "example"]


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
    """Where the data came from. Shown by the interface next to every value."""

    id: str  # identifier of the source, stable across calls
    contract: str  # the contract it fills, e.g. "site_data_climate"
    state: SourceState
    retrieved_at: dt.datetime | None = None  # UTC; None when unavailable or example
    time_zone: str | None = None  # of its daily series (C6.1)
    request: Mapping[str, Any] | None = None  # what was asked of the source
    attribution: str | None = None  # reference to the ATTRIBUTIONS.md entry
    missing_reason: str | None = None  # C3.2 code; required when state is unavailable
    detail: str | None = None  # optional English text for developers


@dataclass(frozen=True)
class ClimateResult:
    """The answer of a climate source: the data, or None with the reason in source."""

    data: ClimatePayload | None
    source: SourceInfo


class ClimateSource(Protocol):
    """Anything that can supply the climate data of a field."""

    def get_climate(self, request: ClimateRequest) -> ClimateResult: ...
