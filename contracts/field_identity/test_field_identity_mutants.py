"""Mutant-killing and boundary tests for ``contracts/field_identity/``.

Every field, case, and geometry built here uses PLACEHOLDER test inputs only.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, get_args
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.field_identity import field_identity
from contracts.field_identity.field_identity import CaseField, FieldIdentity
from contracts.inputs.common import ReasonCode

UNIT_SQUARE = [
    [0.0, 0.0],
    [1.0, 0.0],
    [1.0, 1.0],
    [0.0, 1.0],
    [0.0, 0.0],
]
UNIT_TRIANGLE = [
    [0.0, 0.0],
    [1.0, 0.0],
    [0.5, 1.0],
    [0.0, 0.0],
]


def _field(
    field_id: str = "PLACEHOLDER-field-1",
    *,
    name: str = "PLACEHOLDER field",
    ring: list[list[float]] | None = None,
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "name": name,
        "geometry": {
            "type": "Polygon",
            "coordinates": [copy.deepcopy(ring if ring is not None else UNIT_SQUARE)],
        },
    }


def _case(
    fields: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract": "field_identity",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "label": "PLACEHOLDER label",
        "fields": fields if fields is not None else [_field()],
    }
    doc.update(overrides)
    return doc


@contextmanager
def _weaken_model_validator(
    cls: type[BaseModel], name: str, replacement: Any
) -> Iterator[None]:
    """Temporarily replace a Pydantic model_validator and rebuild the schema."""
    decorator = cls.__pydantic_decorators__.model_validators[name]
    with patch.object(decorator, "func", replacement):
        cls.model_rebuild(force=True)
        try:
            yield
        finally:
            pass
    cls.model_rebuild(force=True)


# --- coordinate bounds & strict types ----------------------------------------


@pytest.mark.parametrize(
    "position",
    [
        [-180.0, -90.0],
        [180.0, 90.0],
        [-180.0, 90.0],
        [180.0, -90.0],
    ],
    ids=["sw-corner", "ne-corner", "nw-corner", "se-corner"],
)
def test_exact_wgs84_corner_bounds_are_accepted(position: list[float]) -> None:
    ring = [position, [0.0, 0.0], [1.0, 1.0], position]
    loaded = FieldIdentity.model_validate(_case([_field(ring=ring)]))
    assert loaded.fields[0].geometry is not None
    assert loaded.fields[0].geometry.coordinates[0][0] == position


@pytest.mark.parametrize(
    ("position", "expected_fragment"),
    [
        ([-180.0001, 0.0], "longitude is outside -180 to 180"),
        ([180.0001, 0.0], "longitude is outside -180 to 180"),
        ([0.0, -90.0001], "latitude is outside -90 to 90"),
        ([0.0, 90.0001], "latitude is outside -90 to 90"),
    ],
    ids=["lon-below-min", "lon-above-max", "lat-below-min", "lat-above-max"],
)
def test_off_by_epsilon_coordinate_bounds_are_rejected(
    position: list[float], expected_fragment: str
) -> None:
    ring = [position, [0.0, 0.0], [1.0, 1.0], position]
    with pytest.raises(ValidationError) as exc_info:
        FieldIdentity.model_validate(_case([_field(ring=ring)]))
    assert expected_fragment in str(exc_info.value)


@pytest.mark.parametrize("bad_num", [math.nan, math.inf, -math.inf, True, False])
@pytest.mark.parametrize("axis", [0, 1], ids=["longitude", "latitude"])
def test_non_finite_and_boolean_coordinates_are_rejected_on_both_axes(
    bad_num: Any, axis: int
) -> None:
    pos = [0.0, 0.0]
    pos[axis] = bad_num
    ring = [pos, [1.0, 0.0], [1.0, 1.0], pos]
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case([_field(ring=ring)]))


@pytest.mark.parametrize(
    "bad_pos",
    [[], [0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]],
    ids=["empty-pos", "one-coord", "three-coords", "four-coords"],
)
def test_position_arity_must_be_exactly_two(bad_pos: list[float]) -> None:
    ring = [UNIT_SQUARE[0], bad_pos, UNIT_SQUARE[2], UNIT_SQUARE[0]]
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case([_field(ring=ring)]))


# --- ring closure, minimum length, and multi-ring checks ---------------------


def test_minimum_four_position_closed_triangle_accepted_and_three_rejected() -> None:
    FieldIdentity.model_validate(_case([_field(ring=UNIT_TRIANGLE)]))

    closed_three = [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]
    with pytest.raises(ValidationError, match="at least 4 positions"):
        FieldIdentity.model_validate(_case([_field(ring=closed_three)]))


@pytest.mark.parametrize(
    "unclosed_end",
    [[0.0001, 0.0], [0.0, 0.0001]],
    ids=["lon-mismatch", "lat-mismatch"],
)
def test_ring_closure_checks_both_axes(unclosed_end: list[float]) -> None:
    ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], unclosed_end]
    with pytest.raises(ValidationError, match="a ring is closed"):
        FieldIdentity.model_validate(_case([_field(ring=ring)]))


@pytest.mark.parametrize(
    "bad_inner_ring",
    [
        [[0.1, 0.1], [0.5, 0.1], [0.1, 0.1]],
        [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.2, 0.1]],
        [[0.1, 0.1], [181.0, 0.1], [0.5, 0.5], [0.1, 0.1]],
    ],
    ids=["inner-too-short", "inner-unclosed", "inner-out-of-bounds"],
)
def test_second_ring_is_validated_same_as_first(
    bad_inner_ring: list[list[float]],
) -> None:
    field = _field()
    field["geometry"]["coordinates"].append(bad_inner_ring)
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case([field]))


def test_empty_coordinates_list_is_rejected() -> None:
    field = _field()
    field["geometry"]["coordinates"] = []
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case([field]))


# --- geometry_or_missing, unique field IDs, and blank strings ----------------


def test_geometry_and_missing_mutually_exclusive_and_detail_validated() -> None:
    # Both present -> rejected
    both_field = _field()
    both_field["geometry_missing"] = {"reason": "NOT_DECLARED"}
    with pytest.raises(ValidationError, match="never both"):
        FieldIdentity.model_validate(_case([both_field]))

    # Neither present -> rejected
    neither_field = _field()
    neither_field["geometry"] = None
    with pytest.raises(ValidationError, match="geometry_missing with its reason"):
        FieldIdentity.model_validate(_case([neither_field]))

    # Blank detail on NOT_DECLARED -> rejected
    blank_detail = {
        "field_id": "PLACEHOLDER-field-1",
        "name": "PLACEHOLDER field",
        "geometry": None,
        "geometry_missing": {"reason": "NOT_DECLARED", "detail": " \t\n"},
    }
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case([blank_detail]))

    # Non-NOT_DECLARED reason codes rejected
    for code in get_args(ReasonCode):
        if code == "NOT_DECLARED":
            continue
        other_reason = {
            "field_id": "PLACEHOLDER-field-1",
            "name": "PLACEHOLDER field",
            "geometry": None,
            "geometry_missing": {"reason": code, "detail": "PLACEHOLDER detail"},
        }
        with pytest.raises(ValidationError, match=r"\(D41\)"):
            FieldIdentity.model_validate(_case([other_reason]))


def test_non_adjacent_duplicate_field_ids_are_rejected() -> None:
    doc = _case(
        [
            _field("PLACEHOLDER-field-a"),
            _field("PLACEHOLDER-field-b"),
            _field("PLACEHOLDER-field-a"),
        ]
    )
    with pytest.raises(ValidationError, match="share one field_id"):
        FieldIdentity.model_validate(doc)


@pytest.mark.parametrize(
    "overrides",
    [
        {"case_id": " \t "},
        {"label": ""},
        {"example_data": 1},
        {"fields": []},
    ],
    ids=["blank-case-id", "empty-label", "int-example-data", "empty-fields"],
)
def test_case_level_strict_types_and_non_empty_constraints(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(_case(**overrides))


# --- injected mutants proving guards fail when weakened ----------------------


def test_mutant_weakened_longitude_range_is_detected() -> None:
    bad = _case(
        [_field(ring=[[-180.0001, 0.0], [0.0, 0.0], [1.0, 1.0], [-180.0001, 0.0]])]
    )
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(bad)
    with patch.object(field_identity, "LONGITUDE_RANGE", (-181.0, 181.0)):
        loaded = FieldIdentity.model_validate(bad)
        assert loaded.fields[0].geometry is not None


def test_mutant_weakened_latitude_range_is_detected() -> None:
    bad = _case([_field(ring=[[0.0, 90.0001], [0.0, 0.0], [1.0, 1.0], [0.0, 90.0001]])])
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(bad)
    with patch.object(field_identity, "LATITUDE_RANGE", (-91.0, 91.0)):
        loaded = FieldIdentity.model_validate(bad)
        assert loaded.fields[0].geometry is not None


def test_mutant_weakened_min_ring_positions_is_detected() -> None:
    three = _case([_field(ring=[[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]])])
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(three)
    with patch.object(field_identity, "MIN_RING_POSITIONS", 3):
        loaded = FieldIdentity.model_validate(three)
        assert loaded.fields[0].geometry is not None


def test_mutant_weakened_geometry_missing_reason_is_detected() -> None:
    wrong_reason = _case(
        [
            {
                "field_id": "PLACEHOLDER-field-1",
                "name": "PLACEHOLDER field",
                "geometry": None,
                "geometry_missing": {"reason": "NOT_AVAILABLE"},
            }
        ]
    )
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(wrong_reason)
    with patch.object(field_identity, "GEOMETRY_MISSING_REASON", "NOT_AVAILABLE"):
        loaded = FieldIdentity.model_validate(wrong_reason)
        assert loaded.fields[0].geometry_missing is not None


def test_mutant_weakened_case_field_and_unique_id_validators_are_detected() -> None:
    neither = _case(
        [
            {
                "field_id": "PLACEHOLDER-field-1",
                "name": "PLACEHOLDER field",
                "geometry": None,
            }
        ]
    )
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(neither)
    with _weaken_model_validator(CaseField, "_geometry_or_missing", lambda self: self):
        CaseField.model_validate(neither["fields"][0])

    dup = _case([_field("PLACEHOLDER-field-a"), _field("PLACEHOLDER-field-a")])
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate(dup)
    with _weaken_model_validator(FieldIdentity, "_unique_field_ids", lambda self: self):
        FieldIdentity.model_validate(dup)
