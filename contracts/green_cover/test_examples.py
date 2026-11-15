"""Acceptance test of unit l0/contracts-green-cover.

The PLACEHOLDER example loads into its model, and each invalid variant of
the example is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree.

Run from the repository root: ``python -m pytest contracts/green_cover/``.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from .models import GreenCoverStrip

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_green_cover.json"
README = HERE / "README.md"

Mutation = Callable[[dict[str, Any]], None]


def load() -> dict[str, Any]:
    return json.loads((EXAMPLES / EXAMPLE).read_text(encoding="utf-8"))


def put(path: list[Any], value: Any) -> Mutation:
    """Set the item at ``path`` to ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = copy.deepcopy(value)

    return mutate


def drop(path: list[Any]) -> Mutation:
    """Remove the key or list item at ``path``."""

    def mutate(data: dict[str, Any]) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def both(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


def swap_observations(i: int, j: int) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        obs = data["observations"]
        obs[i], obs[j] = obs[j], obs[i]

    return mutate


def all_observations_missing() -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for obs in data["observations"]:
            obs["value"] = None
            obs["missing"] = {"reason": "NO_COVERAGE"}
            obs.pop("provenance", None)
            obs.pop("range", None)
            obs.pop("range_missing", None)

    return mutate


OBS0 = ["observations", 0]
OBS1 = ["observations", 1]
OBS2 = ["observations", 2]
OBS3 = ["observations", 3]

INVALID: list[tuple[str, Mutation, str]] = [
    # --- Strip level ----------------------------------------------------------
    ("contract-of-another-name", put(["contract"], "field_identity"), "contract"),
    ("example-data-as-text", put(["example_data"], "true"), "example_data"),
    ("case-id-blank", put(["case_id"], "   "), "case_id"),
    ("field-id-blank", put(["field_id"], ""), "field_id"),
    ("unknown-member-of-strip", put(["extra_key"], "unexpected"), "extra_key"),
    (
        "empty-strip-without-strip-missing",
        both(put(["observations"], []), put(["sources"], [])),
        "strip_missing with its reason",
    ),
    (
        "observations-and-strip-missing-both",
        put(
            ["strip_missing"],
            {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER: gated"},
        ),
        "must be empty when strip_missing is set",
    ),
    (
        "sources-and-strip-missing-both",
        both(
            put(["observations"], []),
            put(
                ["strip_missing"],
                {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER: gated"},
            ),
        ),
        "sources must be empty when strip_missing is set",
    ),
    (
        "observations-unsorted-by-date",
        swap_observations(0, 2),
        "sorted by (date, sensor_source, quantity_id)",
    ),
    (
        "duplicate-observation-same-date-sensor-index",
        put(OBS1, copy.deepcopy(load()["observations"][0])),
        "duplicate entry",
    ),
    (
        "sources-unsorted",
        put(["sources"], ["Sentinel-2 (HLS)", "Landsat-8 (HLS)"]),
        "sorted and unique",
    ),
    (
        "sources-duplicate",
        put(["sources"], ["Landsat-8 (HLS)", "Landsat-8 (HLS)", "Sentinel-2 (HLS)"]),
        "sorted and unique",
    ),
    (
        "sources-mismatch-missing-sensor",
        put(["sources"], ["Sentinel-2 (HLS)"]),
        "distinct sensor_source values",
    ),
    (
        "sources-mismatch-extra-sensor",
        put(["sources"], ["Landsat-8 (HLS)", "MODIS", "Sentinel-2 (HLS)"]),
        "distinct sensor_source values",
    ),
    # --- Observation level ----------------------------------------------------
    ("observation-unknown-member", put([*OBS0, "extra"], 1), "observations.0.extra"),
    (
        "observation-datetime-instead-of-date",
        put([*OBS0, "date"], "2024-01-05T00:00:00Z"),
        "YYYY-MM-DD",
    ),
    (
        "observation-quantity-uppercase",
        put([*OBS0, "quantity_id"], "NDVI"),
        "observations.0.quantity_id",
    ),
    (
        "observation-quantity-hyphenated",
        put([*OBS0, "quantity_id"], "ndvi-1"),
        "observations.0.quantity_id",
    ),
    ("observation-wrong-unit", put([*OBS0, "unit"], "%"), "dimensionless"),
    (
        "observation-value-as-text",
        put([*OBS0, "value"], "0.42"),
        "observations.0.value",
    ),
    (
        "observation-value-as-boolean",
        put([*OBS0, "value"], True),
        "observations.0.value",
    ),
    ("observation-value-nan", put([*OBS0, "value"], math.nan), "observations.0.value"),
    ("observation-value-inf", put([*OBS0, "value"], math.inf), "observations.0.value"),
    (
        "observation-value-and-missing-both",
        put([*OBS0, "missing"], {"reason": "NOT_AVAILABLE"}),
        "never both",
    ),
    (
        "observation-null-without-missing",
        both(
            put([*OBS0, "value"], None),
            drop([*OBS0, "provenance"]),
            drop([*OBS0, "range"]),
        ),
        "missing part with its reason",
    ),
    (
        "observation-missing-with-provenance",
        put([*OBS3, "provenance"], "OBSERVED"),
        "no provenance label",
    ),
    (
        "observation-present-without-provenance",
        drop([*OBS0, "provenance"]),
        "carries a provenance label",
    ),
    (
        "observation-present-with-declared-provenance",
        put([*OBS0, "provenance"], "DECLARED"),
        "provenance must be one of",
    ),
    (
        "observation-present-with-simulated-provenance",
        put([*OBS0, "provenance"], "SIMULATED"),
        "provenance must be one of",
    ),
    (
        "observation-present-without-range-or-range-missing",
        drop([*OBS0, "range"]),
        "range_missing (C2.2)",
    ),
    (
        "observation-present-with-range-and-range-missing-both",
        put([*OBS0, "range_missing"], {"reason": "NOT_AVAILABLE"}),
        "never both (C2.2)",
    ),
    (
        "observation-value-outside-range-below-low",
        put([*OBS0, "range"], {"low": 0.5, "high": 0.6, "kind": "PLACEHOLDER"}),
        "outside its bounds (C2.1)",
    ),
    (
        "observation-value-outside-range-above-high",
        put([*OBS0, "range"], {"low": 0.1, "high": 0.3, "kind": "PLACEHOLDER"}),
        "outside its bounds (C2.1)",
    ),
    (
        "observation-range-low-greater-than-high",
        put([*OBS0, "range"], {"low": 0.6, "high": 0.4, "kind": "PLACEHOLDER"}),
        "low is greater than high (C2.1)",
    ),
    (
        "observation-missing-with-range",
        put([*OBS3, "range"], {"low": 0.0, "high": 0.5, "kind": "PLACEHOLDER"}),
        "missing value has no range (C2.2)",
    ),
    (
        "observation-missing-with-range-missing",
        put([*OBS3, "range_missing"], {"reason": "NOT_AVAILABLE"}),
        "missing value has no range (C2.2)",
    ),
    (
        "observation-sensor-source-blank",
        put([*OBS0, "sensor_source"], "   "),
        "observations.0.sensor_source",
    ),
    (
        "observation-cloud-fraction-below-zero",
        put([*OBS0, "cloud_fraction"], -0.01),
        "between 0 and 1",
    ),
    (
        "observation-cloud-fraction-above-one",
        put([*OBS0, "cloud_fraction"], 1.01),
        "between 0 and 1",
    ),
    (
        "observation-cloud-fraction-nan",
        put([*OBS0, "cloud_fraction"], math.nan),
        "observations.0.cloud_fraction",
    ),
    (
        "observation-cloud-fraction-and-missing-both",
        put([*OBS1, "cloud_fraction"], 0.2),
        "never both",
    ),
    (
        "observation-missing-input-without-detail",
        put([*OBS3, "missing"], {"reason": "MISSING_INPUT"}),
        "MISSING_INPUT needs a detail",
    ),
]

VALID: list[tuple[str, Mutation]] = [
    (
        "accepted-gated-not-available-strip",
        both(
            put(["observations"], []),
            put(["sources"], []),
            put(
                ["strip_missing"],
                {
                    "reason": "NOT_AVAILABLE",
                    "detail": "PLACEHOLDER: Blueprint section 8 gated extra not enabled",
                },
            ),
        ),
    ),
    ("accepted-not-example-data", put(["example_data"], False)),
    (
        "accepted-same-date-same-sensor-different-indices",
        both(
            put(
                ["observations"],
                [
                    {
                        "date": "2024-01-05",
                        "quantity_id": "evi",
                        "value": 0.31,
                        "unit": "dimensionless",
                        "range_missing": {"reason": "NOT_AVAILABLE"},
                        "provenance": "DERIVED",
                        "sensor_source": "Sentinel-2 (HLS)",
                    },
                    {
                        "date": "2024-01-05",
                        "quantity_id": "ndvi",
                        "value": 0.42,
                        "unit": "dimensionless",
                        "range_missing": {"reason": "NOT_AVAILABLE"},
                        "provenance": "DERIVED",
                        "sensor_source": "Sentinel-2 (HLS)",
                    },
                ],
            ),
            put(["sources"], ["Sentinel-2 (HLS)"]),
        ),
    ),
    (
        "accepted-same-date-different-sensors-same-index",
        both(
            put(
                ["observations"],
                [
                    {
                        "date": "2024-01-05",
                        "quantity_id": "ndvi",
                        "value": 0.40,
                        "unit": "dimensionless",
                        "range_missing": {"reason": "NOT_AVAILABLE"},
                        "provenance": "OBSERVED",
                        "sensor_source": "Landsat-8 (HLS)",
                    },
                    {
                        "date": "2024-01-05",
                        "quantity_id": "ndvi",
                        "value": 0.42,
                        "unit": "dimensionless",
                        "range_missing": {"reason": "NOT_AVAILABLE"},
                        "provenance": "DERIVED",
                        "sensor_source": "Sentinel-2 (HLS)",
                    },
                ],
            ),
            put(["sources"], ["Landsat-8 (HLS)", "Sentinel-2 (HLS)"]),
        ),
    ),
    (
        "accepted-cloud-fraction-boundaries",
        both(put([*OBS0, "cloud_fraction"], 0.0), put([*OBS2, "cloud_fraction"], 1.0)),
    ),
    (
        "accepted-value-at-exact-range-bounds",
        both(
            put([*OBS0, "value"], 0.37),
            put([*OBS2, "value"], 0.51),
            drop([*OBS2, "range_missing"]),
            put(
                [*OBS2, "range"],
                {"low": 0.45, "high": 0.51, "kind": "PLACEHOLDER_uncertainty"},
            ),
        ),
    ),
    (
        "accepted-all-observations-missing-keeps-unit-and-sources",
        all_observations_missing(),
    ),
]


def test_example_loads_into_its_model() -> None:
    text = (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    loaded = GreenCoverStrip.model_validate_json(text)
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert GreenCoverStrip.model_validate(json.loads(text)) == loaded


def test_example_is_marked_as_example_data() -> None:
    assert EXAMPLE.startswith("PLACEHOLDER_")
    assert load()["example_data"] is True


def test_the_folder_holds_one_example() -> None:
    assert [path.name for path in EXAMPLES.iterdir()] == [EXAMPLE]


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
        GreenCoverStrip.model_validate(variant)
    assert fragment in _describe(rejected.value)
    with pytest.raises(ValidationError):
        GreenCoverStrip.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    loaded = GreenCoverStrip.model_validate(variant)
    reloaded = GreenCoverStrip.model_validate_json(loaded.model_dump_json())
    assert reloaded == loaded


STRIP_REQUIRED_KEYS = (
    "contract",
    "example_data",
    "case_id",
    "field_id",
    "observations",
    "sources",
)
OBS_REQUIRED_KEYS = ("date", "quantity_id", "value", "unit", "sensor_source")


@pytest.mark.parametrize(
    "path",
    [pytest.param([key], id=f"strip-{key}") for key in STRIP_REQUIRED_KEYS]
    + [pytest.param([*OBS0, key], id=f"obs0-{key}") for key in OBS_REQUIRED_KEYS],
)
def test_no_required_member_can_be_left_out(path: list[Any]) -> None:
    data = load()
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        GreenCoverStrip.model_validate(data)
    location = ".".join(str(part) for part in path)
    assert f"{location}: " in _describe(rejected.value)


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in ("## PROPOSED cases", "## Blueprint Section 8 Gate", "## OPEN"):
        assert f"\n{heading}\n" in readme, f"README.md has no heading {heading!r}"
    listed = readme.split("\n## PROPOSED cases\n", 1)[1].split("\n## ", 1)[0]
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    for case in cases:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"
    in_readme = re.findall(r"^\| `([a-z0-9-]+)` \|", listed, re.MULTILINE)
    assert sorted(in_readme) == sorted(cases)


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
