"""Acceptance test of unit l2/contracts-economic-facts.

The PLACEHOLDER example loads into its model, and each invalid variant of
the example is rejected. The variants are PROPOSED (blueprint section 3.7)
and are listed in ``README.md`` under "PROPOSED cases"; a test checks that
the two lists agree.

Run from the repository root: ``uv run pytest contracts/economic_facts/``.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from .economic_facts import KINDS_OF_YEAR, EconomicFacts, MarginByYear, YieldByYear

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = "PLACEHOLDER_economic_facts.json"
README = HERE / "README.md"

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


GRAIN = ["crops", 0]  # PLACEHOLDER_soybean, kind "grain"
COVER = ["crops", 1]  # PLACEHOLDER_cover_crop, kind "cover"
MARGIN = ["crops", 2]  # PLACEHOLDER_pasture, kind "declared_margin"
PRICE = [*GRAIN, "price"]
COST = [*GRAIN, "cost"]
YIELD = [*GRAIN, "yield"]

# Where pydantic reports an error inside each crop: the tag of the union is
# part of the location.
AT_GRAIN = "crops.0.grain"
AT_COVER = "crops.1.cover"
AT_MARGIN = "crops.2.declared_margin"

NOT_DECLARED = {"value": None, "missing": {"reason": "NOT_DECLARED"}}


def missing_not_declared(path: list[Any]) -> Mutation:
    """The value at ``path`` becomes missing NOT_DECLARED; its unit is kept (C3.1)."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path:
            target = target[key]
        unit = target["unit"]
        target.clear()
        target.update(copy.deepcopy(NOT_DECLARED))
        target["unit"] = unit

    return mutate


def a_value(unit: str) -> dict[str, Any]:
    """A present value of the example's form, in ``unit``. Example data."""
    return {
        "value": 1.0,
        "unit": unit,
        "provenance": "DECLARED",
        "source": "user",
        "range_missing": {"reason": "NOT_DECLARED"},
    }


def by_year(unit: str) -> dict[str, Any]:
    return {kind: a_value(unit) for kind in KINDS_OF_YEAR}


# (case identifier, mutation, fragment of the expected error).
# The fragment shows that the variant is rejected for the intended reason.
INVALID: list[tuple[str, Mutation, str]] = [
    # --- The record ---------------------------------------------------------
    ("contract-of-another-name", put(["contract"], "field_identity"), "contract"),
    ("example-data-as-text", put(["example_data"], "true"), "example_data"),
    ("case-id-blank", put(["case_id"], "   "), "case_id"),
    ("field-id-blank", put(["field_id"], ""), "field_id"),
    ("unknown-member-of-the-record", put(["margin"], 1.0), "margin"),
    ("currency-other-than-usd", put(["currency"], "EUR"), "currency"),
    ("record-without-a-crop", put(["crops"], []), "crops"),
    (
        "two-crops-share-one-identifier",
        put([*COVER, "crop_id"], "PLACEHOLDER_soybean"),
        "share one crop_id",
    ),
    ("crop-id-blank", put([*GRAIN, "crop_id"], " "), f"{AT_GRAIN}.crop_id"),
    # --- Units ----------------------------------------------------------------
    ("price-in-another-unit", put([*PRICE, "unit"], "USD kg-1"), "USD t-1"),
    ("cost-in-another-unit", put([*COST, "unit"], "USD/ha"), "USD ha-1"),
    (
        "cover-cost-in-another-unit",
        put([*COVER, "cost", "unit"], "USD ha-1 yr-1"),
        f"{AT_COVER}.cost",
    ),
    ("yield-in-another-unit", put([*YIELD, "neutral", "unit"], "kg ha-1"), "t ha-1"),
    (
        "declared-margin-in-another-unit",
        put([*MARGIN, "declared_margin", "el_nino", "unit"], "USD ha-1"),
        "USD ha-1 yr-1",
    ),
    # --- Kinds of year --------------------------------------------------------
    (
        "yield-without-one-kind-of-year",
        drop([*YIELD, "la_nina"]),
        f"{AT_GRAIN}.yield.la_nina",
    ),
    (
        "yield-under-a-kind-of-year-not-in-the-list",
        put([*YIELD, "dry"], a_value("t ha-1")),
        f"{AT_GRAIN}.yield.dry",
    ),
    (
        "declared-margin-without-one-kind-of-year",
        drop([*MARGIN, "declared_margin", "neutral"]),
        f"{AT_MARGIN}.declared_margin.neutral",
    ),
    # --- Missing and provenance -----------------------------------------------
    (
        "value-null-without-missing-part",
        put([*PRICE, "value"], None),
        "a missing value carries a missing part with its reason (C3.1)",
    ),
    (
        "value-present-without-provenance",
        drop([*PRICE, "provenance"]),
        "carries a provenance label (C4.1)",
    ),
    # --- Signs ----------------------------------------------------------------
    ("price-negative", put([*PRICE, "value"], -1.0), "not negative"),
    ("yield-negative", put([*YIELD, "el_nino", "value"], -0.5), "not negative"),
    ("cost-negative", put([*COST, "value"], -1.0), "not negative"),
    ("cover-cost-negative", put([*COVER, "cost", "value"], -1.0), "not negative"),
    # --- Members by kind of crop ----------------------------------------------
    ("grain-without-price", drop(PRICE), f"{AT_GRAIN}.price"),
    ("grain-without-yield", drop(YIELD), f"{AT_GRAIN}.yield"),
    (
        "grain-with-a-declared-margin",
        put([*GRAIN, "declared_margin"], by_year("USD ha-1 yr-1")),
        f"{AT_GRAIN}.declared_margin",
    ),
    (
        "declared-margin-crop-with-a-price",
        put([*MARGIN, "price"], a_value("USD t-1")),
        f"{AT_MARGIN}.price",
    ),
    (
        "declared-margin-crop-with-a-yield",
        put([*MARGIN, "yield"], by_year("t ha-1")),
        f"{AT_MARGIN}.yield",
    ),
    (
        "declared-margin-crop-with-a-cost",
        put([*MARGIN, "cost"], a_value("USD ha-1")),
        f"{AT_MARGIN}.cost",
    ),
    (
        "cover-with-a-price",
        put([*COVER, "price"], a_value("USD t-1")),
        f"{AT_COVER}.price",
    ),
    (
        "cover-with-a-yield",
        put([*COVER, "yield"], by_year("t ha-1")),
        f"{AT_COVER}.yield",
    ),
    (
        "cover-with-a-declared-margin",
        put([*COVER, "declared_margin"], by_year("USD ha-1 yr-1")),
        f"{AT_COVER}.declared_margin",
    ),
    ("crop-kind-not-in-the-list", put([*GRAIN, "kind"], "forage"), "kind"),
]

VALID: list[tuple[str, Mutation]] = [
    ("accepted-price-missing-not-declared", missing_not_declared(PRICE)),
    (
        "accepted-yield-in-one-kind-of-year-missing-not-declared",
        missing_not_declared([*YIELD, "la_nina"]),
    ),
    (
        "accepted-negative-declared-margin",
        put([*MARGIN, "declared_margin", "la_nina", "value"], -50.0),
    ),
    ("accepted-not-example-data", put(["example_data"], False)),
    ("accepted-one-crop", put(["crops"], load()["crops"][:1])),
    ("accepted-zero-price", put([*PRICE, "value"], 0.0)),
    (
        "accepted-value-with-a-range",
        both(
            drop([*PRICE, "range_missing"]),
            put(
                [*PRICE, "range"],
                {"low": 300.0, "high": 500.0, "kind": "PLACEHOLDER_kind"},
            ),
        ),
    ),
]


def test_example_loads_into_its_model() -> None:
    text = (EXAMPLES / EXAMPLE).read_text(encoding="utf-8")
    loaded = EconomicFacts.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert EconomicFacts.model_validate(json.loads(text)) == loaded


def test_example_is_marked_as_example_data() -> None:
    assert EXAMPLE.startswith("PLACEHOLDER_")
    data = load()
    assert data["example_data"] is True
    for crop in data["crops"]:
        assert "PLACEHOLDER" in crop["crop_id"]


def test_the_folder_holds_one_example() -> None:
    assert [path.name for path in EXAMPLES.iterdir()] == [EXAMPLE]


def test_the_example_holds_one_crop_of_each_kind() -> None:
    assert [crop["kind"] for crop in load()["crops"]] == [
        "grain",
        "cover",
        "declared_margin",
    ]


def test_kinds_of_year_are_the_members_of_each_by_year_model() -> None:
    assert KINDS_OF_YEAR == ("el_nino", "neutral", "la_nina")
    assert tuple(YieldByYear.model_fields) == KINDS_OF_YEAR
    assert tuple(MarginByYear.model_fields) == KINDS_OF_YEAR


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
        EconomicFacts.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        EconomicFacts.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    data = load()
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    EconomicFacts.model_validate(variant)
    EconomicFacts.model_validate_json(json.dumps(variant))


RECORD_KEYS = ("contract", "example_data", "case_id", "field_id", "currency", "crops")
GRAIN_KEYS = ("crop_id", "kind", "price", "cost", "yield")
COVER_KEYS = ("crop_id", "kind", "cost")
MARGIN_KEYS = ("crop_id", "kind", "declared_margin")

# (path dropped, location the error names). Dropping ``kind`` leaves the
# union without its tag, so pydantic names the crop itself.
REQUIRED: list[tuple[list[Any], str]] = (
    [([key], key) for key in RECORD_KEYS]
    + [
        ([*GRAIN, key], "crops.0" if key == "kind" else f"{AT_GRAIN}.{key}")
        for key in GRAIN_KEYS
    ]
    + [
        ([*COVER, key], "crops.1" if key == "kind" else f"{AT_COVER}.{key}")
        for key in COVER_KEYS
    ]
    + [
        ([*MARGIN, key], "crops.2" if key == "kind" else f"{AT_MARGIN}.{key}")
        for key in MARGIN_KEYS
    ]
    + [([*YIELD, kind], f"{AT_GRAIN}.yield.{kind}") for kind in KINDS_OF_YEAR]
    + [
        ([*MARGIN, "declared_margin", kind], f"{AT_MARGIN}.declared_margin.{kind}")
        for kind in KINDS_OF_YEAR
    ]
)


def test_the_example_has_exactly_the_members_listed() -> None:
    data = load()
    assert set(data) == set(RECORD_KEYS)
    grain, cover, margin = data["crops"]
    assert set(grain) == set(GRAIN_KEYS)
    assert set(cover) == set(COVER_KEYS)
    assert set(margin) == set(MARGIN_KEYS)
    assert set(grain["yield"]) == set(KINDS_OF_YEAR)
    assert set(margin["declared_margin"]) == set(KINDS_OF_YEAR)


@pytest.mark.parametrize(
    ("path", "location"),
    [
        pytest.param(path, location, id=".".join(str(part) for part in path))
        for path, location in REQUIRED
    ],
)
def test_no_member_of_the_example_can_be_left_out(
    path: list[Any], location: str
) -> None:
    """No required member has a default."""
    data = load()
    drop(path)(data)
    with pytest.raises(ValidationError) as rejected:
        EconomicFacts.model_validate(data)
    assert f"{location}: " in _describe(rejected.value)


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = README.read_text(encoding="utf-8")
    for heading in ("## PROPOSED cases", "## OPEN"):
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
