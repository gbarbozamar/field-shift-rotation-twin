"""Contract "Field identity". PROPOSED (blueprint section 3.7).

The fields of one case: their identifiers, their names and their geometry.

Producer: Interface (issue #103). Consumers: the map and site sheet of the
interface, the site reference of the route (``api/``, which keeps its own
``SiteReference`` until it takes this contract: D19 of issue #77) and, through
it, the adapters and the engines. Landed by a builder session of lane L0
(D41 of issue #77). See ``README.md`` in this folder for what is PROPOSED,
what differs from the producer's example and what is OPEN.

The geometry is checked for its structure only: see ``PolygonGeometry``.
Nothing here turns a polygon into a point or computes an area: how a polygon
becomes one point is OPEN for the science reviewers (``adapters/README.md``
OPEN 10, D41 of issue #77).

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from contracts.inputs.common import ContractModel, Missing, NonEmptyStr

# The ranges that define WGS 84 longitude and latitude in degrees; the same
# bounds as ``SiteReference`` in ``api/rotations.py``.
LONGITUDE_RANGE = (-180.0, 180.0)
LATITUDE_RANGE = (-90.0, 90.0)

# A ring is closed and holds at least four positions (the first one repeated
# at the end of three).
MIN_RING_POSITIONS = 4

# D41 of issue #77: a field without geometry has its geometry missing with
# this reason.
GEOMETRY_MISSING_REASON = "NOT_DECLARED"

Coordinate = Annotated[float, Field(allow_inf_nan=False)]


def _check_position(position: list[float]) -> list[float]:
    """A position is two numbers: longitude, then latitude, in WGS 84 degrees."""
    if len(position) != 2:
        raise ValueError(
            "a position is two numbers, longitude then latitude; "
            f"this one has {len(position)}"
        )
    longitude, latitude = position
    low, high = LONGITUDE_RANGE
    if not low <= longitude <= high:
        raise ValueError(f"longitude is outside {low:g} to {high:g} degrees")
    low, high = LATITUDE_RANGE
    if not low <= latitude <= high:
        raise ValueError(f"latitude is outside {low:g} to {high:g} degrees")
    return position


Position = Annotated[list[Coordinate], AfterValidator(_check_position)]


def _check_ring(ring: list[list[float]]) -> list[list[float]]:
    """A ring holds at least four positions and ends where it starts."""
    if len(ring) < MIN_RING_POSITIONS:
        raise ValueError(
            f"a ring holds at least {MIN_RING_POSITIONS} positions; "
            f"this one has {len(ring)}"
        )
    if ring[0] != ring[-1]:
        raise ValueError(
            "a ring is closed: its last position repeats its first position"
        )
    return ring


LinearRing = Annotated[list[Position], AfterValidator(_check_ring)]


class PolygonGeometry(ContractModel):
    """A GeoJSON Polygon in WGS 84 longitude and latitude. PROPOSED.

    Checked: ``type`` is ``"Polygon"``; ``coordinates`` is a list of at least
    one ring; each ring holds at least four positions and its last position
    equals its first; each position is exactly two finite numbers, longitude
    between -180 and 180 and latitude between -90 and 90. No other member is
    accepted.

    Not checked: anything else. In particular the winding order of a ring,
    whether a ring crosses itself, repeated positions inside a ring, whether
    a second ring lies inside the first, the area and the size of the shape.
    """

    type: Literal["Polygon"]
    coordinates: Annotated[list[LinearRing], Field(min_length=1)]


class CaseField(ContractModel):
    """One field of the case: its identifier, its name and its geometry.

    The geometry is a polygon, or null with ``geometry_missing`` beside it
    holding the reason ``NOT_DECLARED`` (D41 of issue #77; C3.1): never both
    and never neither.
    """

    field_id: NonEmptyStr  # the identifier the other contracts use
    name: NonEmptyStr  # display name, shown by the interface
    geometry: PolygonGeometry | None  # null when missing (C3.1)
    geometry_missing: Missing | None = None

    @model_validator(mode="after")
    def _geometry_or_missing(self) -> CaseField:
        if self.geometry is not None:
            if self.geometry_missing is not None:
                raise ValueError(
                    "geometry: a field holds a geometry or a missing part, "
                    "never both (C3.1)"
                )
            return self
        if self.geometry_missing is None:
            raise ValueError(
                "geometry: a missing geometry carries geometry_missing with its "
                "reason (C3.1)"
            )
        if self.geometry_missing.reason != GEOMETRY_MISSING_REASON:
            raise ValueError(
                f"geometry: a missing geometry has the reason "
                f"{GEOMETRY_MISSING_REASON} (D41)"
            )
        return self


class FieldIdentity(ContractModel):
    """The fields of one case, with their names and geometry."""

    contract: Literal["field_identity"]
    example_data: bool
    case_id: NonEmptyStr  # the identifier the other contracts use
    label: NonEmptyStr  # display label of the case
    fields: Annotated[list[CaseField], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_field_ids(self) -> FieldIdentity:
        ids = [field.field_id for field in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("case: two fields share one field_id")
        return self
