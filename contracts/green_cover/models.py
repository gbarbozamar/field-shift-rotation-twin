"""Contract "GreenCoverStrip". PROPOSED (blueprint section 3.7, section 8 gated extra #2).

A time-ordered strip of satellite green-cover observations from Landsat and
Sentinel-2 (HLS) or MODIS for one field of one case.

Blueprint section 8 marks this capability as a gated extra ("Green-cover strip
from Landsat and Sentinel-2 (HLS) or MODIS", L2 Platform, read by science
reviewers; gate: Sunday 10:00 — does the series add evidence?). Until the gate
is passed and the capability is enabled, the default live flow emits the strip
in its gated ``NOT_AVAILABLE`` state (``strip_missing`` with reason
``NOT_AVAILABLE`` and empty ``observations``, never sample values).

Shared parts are imported from ``contracts.inputs.common``, never copied:
``ContractModel``, ``IsoDate``, ``Missing``, ``NonEmptyStr``, ``Provenance``,
``QuantityId``.

Models and pure validation only. No network calls, no parameter values, no
thresholds.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, ConfigDict, FiniteFloat, model_validator

from contracts.inputs.common import (
    ContractModel,
    IsoDate,
    Missing,
    NonEmptyStr,
    Provenance,
    QuantityId,
)

CONTRACT_ID = "green_cover_strip"
DIMENSIONLESS_UNIT = "dimensionless"  # C1.1: unitless indices and fractions
ALLOWED_PROVENANCES: tuple[str, ...] = ("OBSERVED", "DERIVED")  # C4.1, C4.3, C4.4
CLOUD_FRACTION_RANGE: tuple[float, float] = (0.0, 1.0)
GATED_MISSING_REASON = "NOT_AVAILABLE"  # Blueprint section 8 / C3.2

# Candidate C1.1 quantity identifiers for green-cover indices (vocabulary OPEN).
SUGGESTED_QUANTITIES: tuple[str, ...] = ("ndvi", "evi", "fvc")


def _coerce_sequence_to_tuple(value: Any) -> Any:
    """Accept JSON arrays (Python lists) or tuples, rejecting all other types."""
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise ValueError("must be a sequence (tuple or list)")


ObservationTuple = Annotated[
    tuple["GreenCoverObservation", ...], BeforeValidator(_coerce_sequence_to_tuple)
]
SourceTuple = Annotated[
    tuple[NonEmptyStr, ...], BeforeValidator(_coerce_sequence_to_tuple)
]


def _check_observation_order_and_uniqueness(
    observations: tuple[GreenCoverObservation, ...],
) -> None:
    """Observations are sorted by (date, sensor_source, quantity_id) with no duplicates."""
    seen: set[tuple[Any, str, str]] = set()
    prev_key: tuple[Any, str, str] | None = None
    for obs in observations:
        key = (obs.date, obs.sensor_source, obs.quantity_id)
        if key in seen:
            raise ValueError(
                f"observations: duplicate entry for date {obs.date.isoformat()}, "
                f"sensor {obs.sensor_source!r}, quantity {obs.quantity_id!r}"
            )
        if prev_key is not None and key < prev_key:
            raise ValueError(
                "observations: entries must be sorted by (date, sensor_source, quantity_id)"
            )
        seen.add(key)
        prev_key = key


def _check_sources_match_observations(
    sources: tuple[NonEmptyStr, ...],
    observations: tuple[GreenCoverObservation, ...],
) -> None:
    """Sources are sorted, unique, and match the sensor_source values in observations."""
    if list(sources) != sorted(set(sources)):
        raise ValueError("sources: must be sorted and unique")
    observed_sources = {obs.sensor_source for obs in observations}
    if set(sources) != observed_sources:
        raise ValueError(
            "sources: must match the distinct sensor_source values of observations"
        )


class GreenCoverObservation(ContractModel):
    """One satellite green-cover observation for one date, sensor, and index.

    Follows C3.1 and C4.1: ``value`` and ``missing`` are mutually exclusive,
    ``unit`` is ``"dimensionless"`` (kept even when missing), a present value
    carries ``provenance`` in ``{"OBSERVED", "DERIVED"}``, and a missing value
    carries no provenance label. ``cloud_fraction`` is optional in [0, 1] or
    absent with an explicit ``cloud_fraction_missing`` reason.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )

    date: IsoDate
    quantity_id: QuantityId
    value: FiniteFloat | None
    missing: Missing | None = None
    unit: NonEmptyStr
    provenance: Provenance | None = None
    sensor_source: NonEmptyStr
    cloud_fraction: FiniteFloat | None = None
    cloud_fraction_missing: Missing | None = None

    @model_validator(mode="after")
    def _validate_observation(self) -> GreenCoverObservation:
        if self.unit != DIMENSIONLESS_UNIT:
            raise ValueError(
                f"observation: unit must be {DIMENSIONLESS_UNIT!r}, not {self.unit!r} (C1.1)"
            )

        if self.value is not None and self.missing is not None:
            raise ValueError(
                "observation: holds a value or a missing part, never both (C3.1)"
            )
        if self.value is None and self.missing is None:
            raise ValueError(
                "observation: a missing value carries a missing part with its reason (C3.1)"
            )

        if self.value is None:
            if self.provenance is not None:
                raise ValueError(
                    "observation: a missing value carries no provenance label (C4.1)"
                )
        else:
            if self.provenance is None:
                raise ValueError(
                    "observation: a present value carries a provenance label (C4.1)"
                )
            if self.provenance not in ALLOWED_PROVENANCES:
                raise ValueError(
                    f"observation: provenance must be one of {ALLOWED_PROVENANCES}, "
                    f"not {self.provenance!r} (C4.1, C4.3, C4.4)"
                )

        if self.cloud_fraction is not None and self.cloud_fraction_missing is not None:
            raise ValueError(
                "cloud_fraction: holds a value or cloud_fraction_missing, never both (C3.1)"
            )
        if self.cloud_fraction is not None:
            low, high = CLOUD_FRACTION_RANGE
            if not low <= self.cloud_fraction <= high:
                raise ValueError(
                    f"cloud_fraction: must be between {low:g} and {high:g} (dimensionless fraction)"
                )
        return self


class GreenCoverStrip(ContractModel):
    """Green-cover strip for one field of one case.

    Either carries at least one ``GreenCoverObservation`` (with ``strip_missing``
    null and matching ``sources``), or carries ``strip_missing`` (for example
    ``NOT_AVAILABLE`` under the Blueprint section 8 gate) with empty
    ``observations`` and empty ``sources``.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )

    contract: Literal["green_cover_strip"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    observations: ObservationTuple
    strip_missing: Missing | None = None
    sources: SourceTuple

    @model_validator(mode="after")
    def _validate_strip(self) -> GreenCoverStrip:
        if self.strip_missing is not None:
            if self.observations:
                raise ValueError(
                    "strip: observations must be empty when strip_missing is set (C3.1)"
                )
            if self.sources:
                raise ValueError(
                    "strip: sources must be empty when strip_missing is set (C3.1)"
                )
            return self

        if not self.observations:
            raise ValueError(
                "strip: an empty strip must carry strip_missing with its reason (C3.1)"
            )
        _check_observation_order_and_uniqueness(self.observations)
        _check_sources_match_observations(self.sources, self.observations)
        return self
