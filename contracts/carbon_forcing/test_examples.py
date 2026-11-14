"""Acceptance test of unit l2/carbon-forcing.

The PLACEHOLDER example loads into ``CarbonForcing``, and each invalid variant
of it is rejected. The variants are PROPOSED (blueprint section 3.7) and are
listed in ``README.md`` under "PROPOSED cases"; a test checks that the two
lists agree.

Run from the repository root: ``uv run pytest contracts/carbon_forcing/``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.carbon_forcing import CarbonForcing

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
EXAMPLE = EXAMPLES / "PLACEHOLDER_carbon_forcing.json"

Mutation = Callable[[dict[str, Any]], None]

CLIMATE = ["climate", 0]  # the series with one missing month
CARBON = ["carbon_inputs", 0]
ANNUAL = ["annual_climate", 0]  # the annual series with a value
ANNUAL_MISSING = ["annual_climate", 1]  # the annual series whose year is missing
ANNUAL_CARBON = ["annual_carbon_inputs", 0]
LAST_MONTH = {"year": 2001, "month": 11}  # one month before the end of the horizon


def load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def put(path: list[Any], value: Any) -> Mutation:
    """Set the item at ``path`` to ``value``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def drop(path: list[Any]) -> Mutation:
    """Remove the key or the list item at ``path``."""

    def mutate(data: dict[str, Any]) -> None:
        target = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def apply(change: Callable[[dict[str, Any]], None]) -> Mutation:
    return change


def _duplicate_month(data: dict[str, Any]) -> None:
    months = data["climate"][0]["months"]
    months[1] = copy.deepcopy(months[0])


def _swap_months(data: dict[str, Any]) -> None:
    months = data["climate"][0]["months"]
    months[0], months[1] = months[1], months[0]


def _duplicate_climate_quantity(data: dict[str, Any]) -> None:
    data["climate"][1]["quantity"] = data["climate"][0]["quantity"]


def _duplicate_soil_quantity(data: dict[str, Any]) -> None:
    data["soil_properties"][1]["quantity"] = data["soil_properties"][0]["quantity"]


def _series_shorter_than_horizon(data: dict[str, Any]) -> None:
    """A series consistent in itself that stops one month before the horizon."""
    series = data["climate"][1]
    series["months"].pop()
    series["end"] = LAST_MONTH


def _two_years(series: dict[str, Any]) -> None:
    """Extend an annual series, consistent in itself, to a second year."""
    second = copy.deepcopy(series["years"][0])
    second["ag_year"] += 1
    series["years"].append(second)
    series["last_ag_year"] += 1


def _annual_gap(data: dict[str, Any]) -> None:
    series = data["annual_climate"][0]
    _two_years(series)
    series["years"][1]["ag_year"] += 1


def _annual_duplicate_year(data: dict[str, Any]) -> None:
    series = data["annual_climate"][0]
    _two_years(series)
    series["years"][1]["ag_year"] = series["years"][0]["ag_year"]


def _annual_out_of_order(data: dict[str, Any]) -> None:
    series = data["annual_climate"][0]
    _two_years(series)
    series["years"].reverse()


def _annual_beyond_horizon(data: dict[str, Any]) -> None:
    _two_years(data["annual_climate"][0])


def _annual_carbon_shifted(data: dict[str, Any]) -> None:
    series = data["annual_carbon_inputs"][0]
    series["first_ag_year"] += 1
    series["last_ag_year"] += 1
    series["years"][0]["ag_year"] += 1


def _horizon_not_whole_years(data: dict[str, Any]) -> None:
    """Horizon and monthly series shortened by one month, annual series kept."""
    data["horizon"]["end"] = LAST_MONTH
    for series in data["climate"] + data["carbon_inputs"]:
        series["months"].pop()
        series["end"] = LAST_MONTH


def _short_horizon_without_annual(data: dict[str, Any]) -> None:
    """A horizon of four months, not a whole agricultural year, no annual series."""
    end = {"year": 2001, "month": 4}
    data["horizon"]["end"] = end
    for series in data["climate"] + data["carbon_inputs"]:
        del series["months"][4:]
        series["end"] = end
    data["annual_climate"] = []
    data["annual_carbon_inputs"] = []


def _duplicate_annual_quantity(data: dict[str, Any]) -> None:
    data["annual_climate"][1]["quantity"] = data["annual_climate"][0]["quantity"]


# (case, mutation, fragment of the error message)
INVALID: list[tuple[str, Mutation, str]] = [
    ("unknown-field", put(["unknown_part"], 1), "unknown_part: Extra inputs"),
    (
        "unknown-field-in-series",
        put([*CLIMATE, "unknown_part"], 1),
        "unknown_part: Extra inputs",
    ),
    (
        "number-written-as-text",
        put([*CLIMATE, "months", 0, "value"], "1.0"),
        "months.0.value: Input should be a valid number",
    ),
    (
        "soil-depth-number-written-as-text",
        put(
            ["soil_depth"],
            {
                "value": "1.0",
                "unit": "PLACEHOLDER_unit",
                "provenance": "DECLARED",
                "assumption": True,
                "range_missing": {"reason": "NOT_AVAILABLE"},
            },
        ),
        "soil_depth.value: Input should be a valid number",
    ),
    (
        "month-written-as-text",
        put(["horizon", "start", "month"], "1"),
        "horizon.start.month: Input should be a valid integer",
    ),
    ("contract-left-out", drop(["contract"]), "contract: Field required"),
    (
        "contract-of-another-document",
        put(["contract"], "site_data_climate"),
        "contract: Input should be 'carbon_forcing'",
    ),
    ("example-data-left-out", drop(["example_data"]), "example_data: Field required"),
    ("horizon-left-out", drop(["horizon"]), "horizon: Field required"),
    ("soil-depth-left-out", drop(["soil_depth"]), "soil_depth: Field required"),
    (
        "series-one-month-short",
        drop([*CLIMATE, "months", 11]),
        "the months stop before end",
    ),
    (
        "series-shorter-than-horizon",
        apply(_series_shorter_than_horizon),
        "start and end are those of the horizon",
    ),
    (
        "carbon-inputs-shorter-than-horizon",
        apply(
            lambda data: (
                data["carbon_inputs"][0]["months"].pop(),
                data["carbon_inputs"][0].update(end=LAST_MONTH),
            )
        ),
        "carbon_inputs 'placeholder_carbon_input_a': start and end are those of the horizon",
    ),
    (
        "duplicate-month",
        apply(_duplicate_month),
        "every month from start to end appears once, in order",
    ),
    (
        "month-out-of-order",
        apply(_swap_months),
        "every month from start to end appears once, in order",
    ),
    (
        "duplicate-climate-quantity",
        apply(_duplicate_climate_quantity),
        "climate: the quantity identifier 'placeholder_climate_quantity_a' appears",
    ),
    (
        "duplicate-soil-property-quantity",
        apply(_duplicate_soil_quantity),
        "soil_properties: the quantity identifier 'placeholder_soil_property_a'",
    ),
    (
        "quantity-not-an-identifier",
        put([*CLIMATE, "quantity"], "PLACEHOLDER_quantity"),
        "quantity: String should match pattern",
    ),
    (
        "origin-left-out",
        drop([*CARBON, "origin"]),
        "origin: Field required",
    ),
    (
        "missing-month-written-as-zero",
        put([*CLIMATE, "months", 2, "value"], 0.0),
        "an item holds a value or a missing part, never both",
    ),
    (
        "missing-month-without-reason",
        drop([*CLIMATE, "months", 2, "missing"]),
        "a missing value carries a missing part with its reason",
    ),
    (
        "missing-soil-depth-written-as-zero",
        put(["soil_depth", "value"], 0.0),
        "soil_depth: Value error, value: an item holds a value or a missing part",
    ),
    (
        "missing-soil-depth-without-unit",
        drop(["soil_depth", "unit"]),
        "soil_depth.unit: Field required",
    ),
    (
        "series-without-unit",
        drop([*CLIMATE, "unit"]),
        "unit: Field required",
    ),
    (
        "horizon-ends-before-it-starts",
        put(["horizon", "end"], {"year": 2000, "month": 12}),
        "horizon: ends before it starts",
    ),
    (
        "annual-climate-left-out",
        drop(["annual_climate"]),
        "annual_climate: Field required",
    ),
    (
        "annual-carbon-inputs-left-out",
        drop(["annual_carbon_inputs"]),
        "annual_carbon_inputs: Field required",
    ),
    (
        "annual-year-gap",
        apply(_annual_gap),
        "every agricultural year from first_ag_year to last_ag_year appears once",
    ),
    (
        "annual-duplicate-year",
        apply(_annual_duplicate_year),
        "every agricultural year from first_ag_year to last_ag_year appears once",
    ),
    (
        "annual-year-out-of-order",
        apply(_annual_out_of_order),
        "every agricultural year from first_ag_year to last_ag_year appears once",
    ),
    (
        "annual-series-one-year-short",
        put([*ANNUAL, "last_ag_year"], 2002),
        "the years stop before last_ag_year",
    ),
    (
        "annual-series-ends-before-it-starts",
        put([*ANNUAL, "last_ag_year"], 2000),
        "series 'placeholder_annual_climate_quantity_a': ends before it starts",
    ),
    (
        "annual-series-beyond-horizon",
        apply(_annual_beyond_horizon),
        (
            "annual_climate 'placeholder_annual_climate_quantity_a': first_ag_year "
            "and last_ag_year are the agricultural years of the horizon"
        ),
    ),
    (
        "annual-carbon-inputs-not-the-horizon-years",
        apply(_annual_carbon_shifted),
        "annual_carbon_inputs 'placeholder_annual_carbon_input_a': first_ag_year",
    ),
    (
        "annual-series-with-horizon-not-whole-years",
        apply(_horizon_not_whole_years),
        "horizon: with annual series, the horizon is a whole number of agricultural",
    ),
    (
        "duplicate-annual-quantity",
        apply(_duplicate_annual_quantity),
        (
            "annual_climate: the quantity identifier "
            "'placeholder_annual_climate_quantity_a'"
        ),
    ),
    (
        "annual-missing-year-without-reason",
        drop([*ANNUAL_MISSING, "years", 0, "missing"]),
        "a missing value carries a missing part with its reason",
    ),
    (
        "annual-missing-year-written-as-zero",
        put([*ANNUAL_MISSING, "years", 0, "value"], 0.0),
        "an item holds a value or a missing part, never both",
    ),
    (
        "annual-year-written-as-text",
        put([*ANNUAL, "years", 0, "ag_year"], "2001"),
        "ag_year: Input should be a valid integer",
    ),
    (
        "annual-carbon-inputs-origin-left-out",
        drop([*ANNUAL_CARBON, "origin"]),
        "origin: Field required",
    ),
]

# (case, mutation): variants the model accepts.
VALID: list[tuple[str, Mutation]] = [
    (
        "series-all-months-missing-keeps-unit",
        apply(
            lambda data: data["climate"][1].update(
                months=[
                    {
                        "year": item["year"],
                        "month": item["month"],
                        "value": None,
                        "missing": {"reason": "SOURCE_UNAVAILABLE"},
                    }
                    for item in data["climate"][1]["months"]
                ],
                provenance=None,
                source=None,
                range_missing=None,
            )
        ),
    ),
    ("zero-is-a-real-value", put([*CLIMATE, "months", 0, "value"], 0.0)),
    (
        "empty-lists",
        apply(
            lambda data: data.update(climate=[], carbon_inputs=[], soil_properties=[])
        ),
    ),
    (
        "empty-annual-lists-with-horizon-not-whole-years",
        apply(_short_horizon_without_annual),
    ),
    (
        "empty-annual-lists-with-whole-year-horizon",
        apply(lambda data: data.update(annual_climate=[], annual_carbon_inputs=[])),
    ),
    (
        "same-quantity-in-two-lists",
        put([*CARBON, "quantity"], "placeholder_climate_quantity_a"),
    ),
]


def test_example_loads_into_its_model() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    loaded = CarbonForcing.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert CarbonForcing.model_validate(json.loads(text)) == loaded


def test_example_is_marked_as_example_data() -> None:
    data = load()
    assert data["example_data"] is True
    for key in ("case_id", "field_id", "rotation_id"):
        assert data[key].startswith("PLACEHOLDER")


def test_example_shows_the_absence_form() -> None:
    """At least one missing month and a missing soil depth, each with its reason."""
    data = load()
    assert data["soil_depth"]["value"] is None
    assert data["soil_depth"]["missing"]["reason"]
    assert data["soil_depth"]["unit"] == "PLACEHOLDER_unit"
    missing_months = [
        item
        for series in data["climate"] + data["carbon_inputs"]
        for item in series["months"]
        if item["value"] is None
    ]
    assert missing_months
    assert all(item["missing"]["reason"] for item in missing_months)
    missing_years = [
        item
        for series in data["annual_climate"] + data["annual_carbon_inputs"]
        for item in series["years"]
        if item["value"] is None
    ]
    assert missing_years
    assert all(item["missing"]["reason"] for item in missing_years)


def test_example_horizon_is_one_agricultural_year() -> None:
    """Twelve months from the start month (C5.3), so the annual series apply."""
    horizon = load()["horizon"]
    assert horizon["start"] == {"year": 2001, "month": 1}
    assert horizon["end"] == {"year": 2001, "month": 12}


def test_example_holds_placeholders_only() -> None:
    data = load()
    units = [data["soil_depth"]["unit"]]
    every_series = (
        data["climate"]
        + data["carbon_inputs"]
        + data["annual_climate"]
        + data["annual_carbon_inputs"]
    )
    for series in every_series:
        units.append(series["unit"])
        assert series["quantity"].startswith("placeholder_")
        if "source" in series:
            assert series["source"].startswith("PLACEHOLDER")
    for item in data["soil_properties"]:
        units.append(item["unit"])
        assert item["quantity"].startswith("placeholder_")
    for series in data["carbon_inputs"] + data["annual_carbon_inputs"]:
        assert series["origin"].startswith("placeholder_")
    assert set(units) == {"PLACEHOLDER_unit"}


def test_every_example_file_is_checked() -> None:
    assert sorted(path.name for path in EXAMPLES.iterdir()) == [EXAMPLE.name]


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
        CarbonForcing.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        CarbonForcing.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    "mutation",
    [pytest.param(mutation, id=case) for case, mutation in VALID],
)
def test_valid_variant_is_accepted(mutation: Mutation) -> None:
    variant = load()
    mutation(variant)
    CarbonForcing.model_validate(variant)
    CarbonForcing.model_validate_json(json.dumps(variant))


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, _ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert "## PROPOSED cases" in readme
    assert "## OPEN" in readme
    listed = readme.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    for case in [case for case, *_ in INVALID] + [case for case, _ in VALID]:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
