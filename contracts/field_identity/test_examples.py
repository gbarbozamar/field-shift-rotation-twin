"""Acceptance test of unit l0/contracts-field-identity.

The PLACEHOLDER example loads into its model, and each invalid variant of
the example is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree.

Run from the repository root: ``python -m pytest contracts/field_identity/``.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from contracts.inputs.common import ReasonCode

from .field_identity import GEOMETRY_MISSING_REASON, FieldIdentity

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_field_identity.json"
README = HERE / "README.md"

# The example of issue #103, as the producer wrote it. Kept here only to show
# that the landed example differs from it in the points of README.md,
# "Differences from the producer's example", and in no other.
PRODUCER_EXAMPLE = """
{
  "contract": "field_identity",
  "example_data": true,
  "case_id": "example-case",
  "label": "Example case",
  "fields": [
    {
      "field_id": "example-field-1",
      "name": "North field",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-57.0100, -33.0100], [-57.0030, -33.0100],
          [-57.0030, -33.0160], [-57.0100, -33.0160],
          [-57.0100, -33.0100]
        ]]
      }
    }
  ]
}
"""

# The producer's example case file ``web/src/data/example_case.json`` as it
# is on main when this unit was cut (commit 7df4463). Copied, not read, so
# that this test does not depend on another lane's folder. D41 of issue #77:
# the example of this contract may carry the same synthetic shapes.
PRODUCER_CASE_FILE = """
{
  "example_data": true,
  "case_id": "example-case",
  "label": "Example case",
  "fields": [
    { "field_id": "example-field-1", "name": "North field",
      "geometry": { "type": "Polygon", "coordinates": [[[-57.0100, -33.0100], [-57.0030, -33.0100], [-57.0030, -33.0160], [-57.0100, -33.0160], [-57.0100, -33.0100]]] } },
    { "field_id": "example-field-2", "name": "Long field by the creek",
      "geometry": { "type": "Polygon", "coordinates": [[[-56.9980, -33.0110], [-56.9900, -33.0110], [-56.9900, -33.0130], [-56.9980, -33.0130], [-56.9980, -33.0110]]] } },
    { "field_id": "example-field-3", "name": "Small triangle field",
      "geometry": { "type": "Polygon", "coordinates": [[[-57.0060, -33.0190], [-57.0020, -33.0190], [-57.0040, -33.0230], [-57.0060, -33.0190]]] } }
  ]
}
"""

Mutation = Callable[[dict[str, Any]], None]


def load() -> dict[str, Any]:
    return json.loads((EXAMPLES / EXAMPLE).read_text(encoding="utf-8"))


def put(path: list[Any], value: Any) -> Mutation:
    """Set the item at ``path`` to ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = copy.deepcopy(value)

    return mutate


def drop(path: list[Any]) -> Mutation:
    """Remove the key or the list item at ``path``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def both(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


def reverse_ring(path: list[Any]) -> Mutation:
    """Write the ring at ``path`` in the opposite order; it stays closed."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = list(reversed(target[path[-1]]))

    return mutate


def swap_axes(path: list[Any]) -> Mutation:
    """Write every position of the geometry at ``path`` as latitude, longitude."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path:
            target = target[key]
        target["coordinates"] = [
            [[latitude, longitude] for longitude, latitude in ring]
            for ring in target["coordinates"]
        ]

    return mutate


FIRST = ["fields", 0]  # North field, a rectangle
SECOND = ["fields", 1]  # Long field by the creek, a rectangle
THIRD = ["fields", 2]  # Small triangle field: four positions, the minimum
GEOMETRY = [*FIRST, "geometry"]
RING = [*GEOMETRY, "coordinates", 0]  # five positions
TRIANGLE = [*THIRD, "geometry", "coordinates", 0]  # four positions
NOT_DECLARED = {"geometry": None, "geometry_missing": {"reason": "NOT_DECLARED"}}

# A ring inside the North field, closed, four positions.
INNER_RING = [
    [-57.0080, -33.0120],
    [-57.0050, -33.0120],
    [-57.0050, -33.0140],
    [-57.0080, -33.0120],
]
# A ring well away from the North field, closed, four positions.
OUTER_RING = [
    [-56.9980, -33.0110],
    [-56.9900, -33.0110],
    [-56.9900, -33.0130],
    [-56.9980, -33.0110],
]
# Four corners of the North field joined across: the ring crosses itself.
CROSSING_RING = [
    [-57.0100, -33.0100],
    [-57.0030, -33.0160],
    [-57.0030, -33.0100],
    [-57.0100, -33.0160],
    [-57.0100, -33.0100],
]
# Three positions on one line, closed: a ring with no area.
FLAT_RING = [
    [-57.0100, -33.0100],
    [-57.0060, -33.0100],
    [-57.0030, -33.0100],
    [-57.0100, -33.0100],
]


def every_geometry_not_declared() -> Mutation:
    """Every field has its geometry missing with reason NOT_DECLARED."""

    def mutate(data: dict[str, Any]) -> None:
        for field in data["fields"]:
            field.update(copy.deepcopy(NOT_DECLARED))

    return mutate


def add_ring(ring: list[list[float]]) -> Mutation:
    """Add a second ring to the geometry of the first field."""

    def mutate(data: dict[str, Any]) -> None:
        data["fields"][0]["geometry"]["coordinates"].append(copy.deepcopy(ring))

    return mutate


# (case identifier, mutation, fragment of the expected error).
# The fragment shows that the variant is rejected for the intended reason.
INVALID: list[tuple[str, Mutation, str]] = [
    # --- The case -------------------------------------------------------------
    ("contract-of-another-name", put(["contract"], "rotation_definition"), "contract"),
    ("example-data-as-text", put(["example_data"], "true"), "example_data"),
    ("case-id-blank", put(["case_id"], "   "), "case_id"),
    ("label-blank", put(["label"], ""), "label"),
    ("label-null", put(["label"], None), "label"),
    ("case-without-a-field", put(["fields"], []), "fields"),
    (
        "two-fields-share-one-identifier",
        put([*SECOND, "field_id"], "example-field-1"),
        "share one field_id",
    ),
    ("unknown-member-of-the-case", put(["centroid"], [-57.0, -33.0]), "centroid"),
    # --- A field --------------------------------------------------------------
    ("field-id-blank", put([*FIRST, "field_id"], ""), "fields.0.field_id"),
    ("name-blank", put([*FIRST, "name"], " "), "fields.0.name"),
    ("name-null", put([*FIRST, "name"], None), "fields.0.name"),
    ("unknown-member-of-a-field", put([*FIRST, "area"], 1.0), "fields.0.area"),
    # --- A geometry and its missing part -------------------------------------
    (
        "geometry-null-without-missing-part",
        put(GEOMETRY, None),
        "geometry_missing with its reason",
    ),
    (
        "geometry-and-missing-part-both",
        put([*FIRST, "geometry_missing"], {"reason": "NOT_DECLARED"}),
        "never both",
    ),
    (
        "geometry-missing-with-another-reason",
        both(
            put(GEOMETRY, None),
            put([*FIRST, "geometry_missing"], {"reason": "NOT_AVAILABLE"}),
        ),
        "(D41)",
    ),
    (
        "geometry-missing-part-without-reason",
        both(put(GEOMETRY, None), put([*FIRST, "geometry_missing"], {})),
        "geometry_missing.reason",
    ),
    (
        "geometry-missing-with-reason-code-not-in-the-sheet",
        both(
            put(GEOMETRY, None),
            put([*FIRST, "geometry_missing"], {"reason": "NOT_DRAWN"}),
        ),
        "geometry_missing.reason",
    ),
    # --- The polygon ----------------------------------------------------------
    (
        "geometry-of-another-type",
        put([*GEOMETRY, "type"], "MultiPolygon"),
        "geometry.type",
    ),
    (
        "geometry-type-in-lower-case",
        put([*GEOMETRY, "type"], "polygon"),
        "geometry.type",
    ),
    (
        "geometry-with-a-bbox-member",
        put([*GEOMETRY, "bbox"], [-57.01, -33.016, -57.003, -33.01]),
        "geometry.bbox",
    ),
    (
        "geometry-with-a-crs-member",
        put([*GEOMETRY, "crs"], {"type": "name"}),
        "geometry.crs",
    ),
    (
        "geometry-without-a-ring",
        put([*GEOMETRY, "coordinates"], []),
        "geometry.coordinates",
    ),
    (
        "coordinates-not-nested-in-a-ring",
        put([*GEOMETRY, "coordinates"], [[-57.0100, -33.0100]] * 5),
        "geometry.coordinates",
    ),
    ("ring-not-closed", drop([*RING, 4]), "a ring is closed"),
    ("ring-with-three-positions", drop([*TRIANGLE, 1]), "at least 4 positions"),
    ("ring-empty", put(TRIANGLE, []), "at least 4 positions"),
    (
        "position-with-three-numbers",
        put([*RING, 1], [-57.0030, -33.0100, 0.0]),
        "two numbers",
    ),
    ("position-with-one-number", put([*RING, 1], [-57.0030]), "two numbers"),
    (
        "longitude-outside-its-range",
        put([*RING, 1], [-181.0, -33.0100]),
        "longitude is outside -180 to 180",
    ),
    (
        "latitude-outside-its-range",
        put([*RING, 1], [-57.0030, 91.0]),
        "latitude is outside -90 to 90",
    ),
    (
        "coordinate-as-text",
        put([*RING, 1], ["-57.0030", -33.0100]),
        "coordinates.0.1.0",
    ),
    ("coordinate-as-boolean", put([*RING, 1], [True, -33.0100]), "coordinates.0.1.0"),
    (
        "coordinate-not-finite",
        put([*RING, 1], [math.nan, -33.0100]),
        "coordinates.0.1.0",
    ),
]

VALID: list[tuple[str, Mutation]] = [
    (
        "accepted-field-without-geometry",
        both(
            put(GEOMETRY, None),
            put([*FIRST, "geometry_missing"], {"reason": "NOT_DECLARED"}),
        ),
    ),
    (
        "accepted-geometry-missing-with-a-detail",
        both(
            put(GEOMETRY, None),
            put(
                [*FIRST, "geometry_missing"],
                {"reason": "NOT_DECLARED", "detail": "PLACEHOLDER detail"},
            ),
        ),
    ),
    ("accepted-every-field-without-geometry", every_geometry_not_declared()),
    ("accepted-one-field", put(["fields"], load()["fields"][:1])),
    ("accepted-not-example-data", put(["example_data"], False)),
    (
        "accepted-polygon-with-a-second-ring",
        add_ring(INNER_RING),
    ),
    (
        "accepted-whole-number-coordinates",
        put(
            [*GEOMETRY, "coordinates"],
            [[[-57, -33], [-56, -33], [-56, -34], [-57, -33]]],
        ),
    ),
    # --- Accepted only while a question is open -------------------------------
    ("accepted-while-open-ring-wound-the-other-way", reverse_ring(RING)),
    ("accepted-while-open-ring-that-crosses-itself", put(RING, CROSSING_RING)),
    ("accepted-while-open-ring-with-no-area", put(RING, FLAT_RING)),
    (
        "accepted-while-open-position-repeated-inside-a-ring",
        put([*RING, 2], [-57.0030, -33.0100]),
    ),
    (
        "accepted-while-open-second-ring-outside-the-first",
        add_ring(OUTER_RING),
    ),
    ("accepted-while-open-longitude-and-latitude-swapped", swap_axes(GEOMETRY)),
    (
        "accepted-while-open-two-fields-with-one-name",
        put([*SECOND, "name"], "North field"),
    ),
    (
        "accepted-while-open-overlapping-fields",
        put([*SECOND, "geometry"], load()["fields"][0]["geometry"]),
    ),
]


def test_example_loads_into_its_model() -> None:
    text = (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    loaded = FieldIdentity.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert FieldIdentity.model_validate(json.loads(text)) == loaded


def test_example_is_marked_as_example_data() -> None:
    assert EXAMPLE.startswith("PLACEHOLDER_")
    assert load()["example_data"] is True


def test_the_folder_holds_one_example() -> None:
    assert [path.name for path in EXAMPLES.iterdir()] == [EXAMPLE]


def test_example_differs_from_the_producer_example_only_where_the_readme_says() -> None:
    """README.md, "Differences from the producer's example"."""
    produced = json.loads(PRODUCER_EXAMPLE)
    # The example of issue #103 is valid as the producer wrote it.
    FieldIdentity.model_validate(produced)
    landed = load()
    # Difference 1: the landed example carries the three fields of the
    # producer's case file; issue #103 shows the first one.
    assert {**landed, "fields": landed["fields"][:1]} == produced
    # And the landed example is that case file with "contract" added.
    case_file = json.loads(PRODUCER_CASE_FILE)
    assert "contract" not in case_file
    assert {"contract": "field_identity", **case_file} == landed


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [pytest.param(mutation, fragment, id=case) for case, mutation, fragment in INVALID],
)
def test_invalid_variant_is_rejected(mutation: Mutation, fragment: str) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    with pytest.raises(ValidationError) as rejected:
        FieldIdentity.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        FieldIdentity.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    FieldIdentity.model_validate(variant)
    FieldIdentity.model_validate_json(json.dumps(variant))


CASE_KEYS = ("contract", "example_data", "case_id", "label", "fields")
FIELD_KEYS = ("field_id", "name", "geometry")
GEOMETRY_KEYS = ("type", "coordinates")


@pytest.mark.parametrize(
    "path",
    [pytest.param([key], id=f"case-{key}") for key in CASE_KEYS]
    + [pytest.param([*FIRST, key], id=f"field-{key}") for key in FIELD_KEYS]
    + [pytest.param([*GEOMETRY, key], id=f"geometry-{key}") for key in GEOMETRY_KEYS],
)
def test_no_member_of_the_example_can_be_left_out(path: list[Any]) -> None:
    """No member of the case, of a field or of its geometry has a default."""
    data = load()
    assert set(data) == set(CASE_KEYS)
    for field in data["fields"]:
        assert set(field) == set(FIELD_KEYS)
        assert set(field["geometry"]) == set(GEOMETRY_KEYS)
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        FieldIdentity.model_validate(data)
    location = ".".join(str(part) for part in path)
    assert f"{location}: " in _describe(rejected.value)


def test_geometry_missing_reason_is_a_code_of_the_sheet() -> None:
    assert GEOMETRY_MISSING_REASON == "NOT_DECLARED"
    assert GEOMETRY_MISSING_REASON in get_args(ReasonCode)


@pytest.mark.parametrize(
    "reason", [code for code in get_args(ReasonCode) if code != "NOT_DECLARED"]
)
def test_a_missing_geometry_takes_no_other_reason_code(reason: str) -> None:
    """D41 of issue #77 names NOT_DECLARED; the other seven codes are rejected."""
    variant = load()
    put(GEOMETRY, None)(variant)
    put([*FIRST, "geometry_missing"], {"reason": reason, "detail": "PLACEHOLDER"})(
        variant
    )
    with pytest.raises(ValidationError) as rejected:
        FieldIdentity.model_validate(variant)
    assert "(D41)" in _describe(rejected.value)


@pytest.mark.parametrize(
    "position",
    [[-180.0, 0.0], [180.0, 0.0], [0.0, -90.0], [0.0, 90.0]],
    ids=[
        "longitude-180-west",
        "longitude-180-east",
        "latitude-90-south",
        "latitude-90-north",
    ],
)
def test_the_ends_of_each_range_are_accepted(position: list[float]) -> None:
    variant = load()
    put([*RING, 1], position)(variant)
    FieldIdentity.model_validate(variant)


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in (
        "## PROPOSED cases",
        "## Differences from the producer's example",
        "## OPEN",
    ):
        assert f"\n{heading}\n" in readme, f"README.md has no heading {heading!r}"
    listed = readme.split("\n## PROPOSED cases\n", 1)[1].split("\n## ", 1)[0]
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    for case in cases:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"
    # And the README lists no case that this file does not hold.
    in_readme = re.findall(r"^\| `([a-z0-9-]+)` \|", listed, re.MULTILINE)
    assert sorted(in_readme) == sorted(cases)


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
