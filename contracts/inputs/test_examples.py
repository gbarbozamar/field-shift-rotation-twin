"""Acceptance test of unit l0/contracts-inputs.

Each PLACEHOLDER example loads into its model, and each invalid variant of an
example is rejected. The variants are PROPOSED (blueprint section 3.7) and are
listed in ``README.md`` under "PROPOSED cases"; a test checks that the two
lists agree.

Run from the repository root: ``python -m pytest contracts/inputs/``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from .rotation_calendar import RotationCalendar
from .site_climate import SiteClimate
from .site_soil_slope import SiteSoilSlope

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"

CONTRACTS = {
    "calendar": (RotationCalendar, "PLACEHOLDER_rotation_calendar.json"),
    "climate": (SiteClimate, "PLACEHOLDER_site_climate.json"),
    "soil": (SiteSoilSlope, "PLACEHOLDER_site_soil_slope.json"),
}

Mutation = Callable[[dict[str, Any]], None]


def load(contract: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / CONTRACTS[contract][1]).read_text(encoding="utf-8"))


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


def both(*mutations: Mutation) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(data)

    return mutate


A_REASON = {"reason": "NOT_AVAILABLE"}
RAIN = ["daily_series", 0]  # the series with numbers and one missing day
ALL_MISSING = ["daily_series", 1]  # the series whose days are all missing
MONTHLY = ["monthly_series", 0]
COMPONENT = ["components", 0]
PERIOD = ["components", 0, "periods", 0]

# (case identifier, contract, mutation, fragment of the expected error).
# The fragment shows that the variant is rejected for the intended reason.
INVALID: list[tuple[str, str, Mutation, str]] = [
    # --- Site data: climate -------------------------------------------------
    (
        "daily-series-without-time-zone",
        "climate",
        drop([*RAIN, "time_zone"]),
        "time_zone",
    ),
    (
        "daily-series-with-empty-time-zone",
        "climate",
        put([*RAIN, "time_zone"], ""),
        "time_zone",
    ),
    (
        "missing-day-written-as-zero",
        "climate",
        put([*RAIN, "days", 2, "value"], 0.0),
        "never both",
    ),
    (
        "missing-day-written-as-not-a-number",
        "climate",
        both(
            put([*RAIN, "days", 2, "value"], float("nan")),
            drop([*RAIN, "days", 2, "missing"]),
        ),
        "finite number",
    ),
    (
        "missing-day-dropped-from-the-series",
        "climate",
        drop([*RAIN, "days", 2]),
        "expected the day 2001-01-03",
    ),
    (
        "missing-day-without-reason",
        "climate",
        drop([*RAIN, "days", 2, "missing"]),
        "missing part with its reason",
    ),
    (
        "missing-part-without-reason-code",
        "climate",
        drop([*RAIN, "days", 2, "missing", "reason"]),
        "missing.reason",
    ),
    (
        "unknown-reason-code",
        "climate",
        put([*RAIN, "days", 2, "missing", "reason"], "UNKNOWN"),
        "missing.reason",
    ),
    ("series-without-unit", "climate", drop([*RAIN, "unit"]), "unit"),
    (
        "series-without-provenance-label",
        "climate",
        drop([*RAIN, "provenance"]),
        "provenance label",
    ),
    (
        "series-without-source-or-assumption-mark",
        "climate",
        drop([*RAIN, "source"]),
        "source or the assumption mark",
    ),
    (
        "series-without-range-and-without-its-reason",
        "climate",
        drop([*RAIN, "range_missing"]),
        "range_missing",
    ),
    (
        "all-missing-series-with-provenance-label",
        "climate",
        put([*ALL_MISSING, "provenance"], "OBSERVED"),
        "no provenance label",
    ),
    (
        "days-out-of-order",
        "climate",
        both(
            put([*RAIN, "days", 0, "date"], "2001-01-02"),
            put([*RAIN, "days", 1, "date"], "2001-01-01"),
        ),
        "expected the day 2001-01-01",
    ),
    (
        "days-stop-before-end-date",
        "climate",
        drop([*RAIN, "days", 4]),
        "stop before end_date",
    ),
    (
        "date-not-written-as-year-month-day",
        "climate",
        put([*RAIN, "start_date"], "2001-1-1"),
        "YYYY-MM-DD",
    ),
    (
        "date-with-a-time",
        "climate",
        put([*RAIN, "start_date"], "2001-01-01T00:00:00"),
        "YYYY-MM-DD",
    ),
    (
        "month-thirteen",
        "climate",
        put([*MONTHLY, "end", "month"], 13),
        "less than or equal to 12",
    ),
    (
        "month-as-a-name",
        "climate",
        put([*MONTHLY, "months", 0, "month"], "December"),
        "valid integer",
    ),
    (
        "month-without-its-year",
        "climate",
        drop([*MONTHLY, "months", 0, "year"]),
        "year",
    ),
    (
        "month-dropped-from-the-series",
        "climate",
        drop([*MONTHLY, "months", 1]),
        "every month",
    ),
    (
        "two-series-with-one-quantity",
        "climate",
        put([*ALL_MISSING, "quantity"], "precipitation"),
        "share one quantity",
    ),
    (
        "quantity-identifier-not-lower-case",
        "climate",
        put([*RAIN, "quantity"], "Precipitation"),
        "quantity",
    ),
    ("climate-unknown-extra-field", "climate", put(["note"], "x"), "Extra inputs"),
    (
        "day-unknown-extra-field",
        "climate",
        put([*RAIN, "days", 0, "filled"], True),
        "Extra inputs",
    ),
    (
        "climate-without-example-data-flag",
        "climate",
        drop(["example_data"]),
        "example_data",
    ),
    (
        "climate-with-another-contract-identifier",
        "climate",
        put(["contract"], "site_data_soil_slope"),
        "contract",
    ),
    # --- Site data: soil and slope ------------------------------------------
    ("value-without-unit", "soil", drop(["slope_length", "unit"]), "slope_length.unit"),
    (
        "value-with-empty-unit",
        "soil",
        put(["slope_length", "unit"], ""),
        "slope_length.unit",
    ),
    (
        "value-without-provenance-label",
        "soil",
        drop(["slope_length", "provenance"]),
        "provenance label",
    ),
    (
        "provenance-label-outside-the-four",
        "soil",
        put(["slope_length", "provenance"], "MEASURED"),
        "slope_length.provenance",
    ),
    (
        "provenance-label-in-lower-case",
        "soil",
        put(["slope_length", "provenance"], "observed"),
        "slope_length.provenance",
    ),
    (
        "value-without-source-or-assumption-mark",
        "soil",
        drop(["slope_length", "source"]),
        "source or the assumption mark",
    ),
    (
        "missing-value-without-reason",
        "soil",
        drop(["soil_properties", 1, "missing"]),
        "missing part with its reason",
    ),
    (
        "missing-value-written-as-zero",
        "soil",
        put(["soil_properties", 1, "value"], 0.0),
        "never both",
    ),
    (
        "missing-value-with-provenance-label",
        "soil",
        put(["soil_properties", 1, "provenance"], "OBSERVED"),
        "no provenance label",
    ),
    (
        "missing-value-with-range",
        "soil",
        put(["soil_properties", 1, "range_missing"], A_REASON),
        "a missing value has no range",
    ),
    (
        "missing-input-without-detail",
        "soil",
        put(["soil_properties", 1, "missing"], {"reason": "MISSING_INPUT"}),
        "names the input",
    ),
    (
        "value-without-range-and-without-its-reason",
        "soil",
        drop(["slope_length", "range_missing"]),
        "range_missing",
    ),
    (
        "value-with-range-and-reason-for-no-range",
        "soil",
        put(["slope_steepness", "range_missing"], A_REASON),
        "never both",
    ),
    (
        "range-with-one-bound",
        "soil",
        drop(["slope_steepness", "range", "high"]),
        "range.high",
    ),
    (
        "range-that-does-not-hold-its-value",
        "soil",
        put(["slope_steepness", "range", "low"], 2.5),
        "outside its bounds",
    ),
    (
        "range-with-low-above-high",
        "soil",
        put(["slope_steepness", "range", "low"], 3.5),
        "low is greater than high",
    ),
    (
        "range-without-kind",
        "soil",
        drop(["slope_steepness", "range", "kind"]),
        "range.kind",
    ),
    (
        "value-written-as-text",
        "soil",
        put(["slope_length", "value"], "1.0"),
        "valid number",
    ),
    (
        "two-soil-properties-with-one-quantity",
        "soil",
        put(["soil_properties", 1, "quantity"], "placeholder_soil_property_a"),
        "share one quantity",
    ),
    (
        "soil-without-slope-steepness",
        "soil",
        drop(["slope_steepness"]),
        "slope_steepness",
    ),
    ("soil-unknown-extra-field", "soil", put(["elevation"], 1.0), "Extra inputs"),
    (
        "value-unknown-extra-field",
        "soil",
        put(["slope_length", "comment"], "x"),
        "Extra inputs",
    ),
    # --- Rotation calendar --------------------------------------------------
    (
        "component-ends-before-it-starts",
        "calendar",
        put([*COMPONENT, "end", "date"], "2001-08-31"),
        "ends before it starts",
    ),
    (
        "period-ends-before-it-starts",
        "calendar",
        put([*PERIOD, "end", "date"], "2001-08-31"),
        "ends before it starts",
    ),
    (
        "period-outside-its-component",
        "calendar",
        put([*PERIOD, "end", "date"], "2002-03-15"),
        "outside the dates of its component",
    ),
    (
        "component-outside-the-calendar",
        "calendar",
        put(["components", 2, "end", "date"], "2003-07-31"),
        "outside the dates of the calendar",
    ),
    (
        "calendar-ends-before-it-starts",
        "calendar",
        both(put(["end_date"], "2001-06-30"), put(["components"], [])),
        "calendar: ends before it starts",
    ),
    (
        "two-components-with-one-identifier",
        "calendar",
        put(["components", 1, "component_id"], "PLACEHOLDER-component-1"),
        "share one component_id",
    ),
    (
        "component-without-crop-identifier",
        "calendar",
        drop([*COMPONENT, "crop_id"]),
        "crop_id",
    ),
    (
        "date-without-provenance-label",
        "calendar",
        drop([*COMPONENT, "start", "provenance"]),
        "provenance label",
    ),
    (
        "missing-date-without-reason",
        "calendar",
        put([*COMPONENT, "end"], {"date": None}),
        "missing part with its reason",
    ),
    (
        "date-written-as-day-of-year",
        "calendar",
        put([*COMPONENT, "start", "date"], "2001-244"),
        "YYYY-MM-DD",
    ),
    (
        "start-month-without-provisional-mark",
        "calendar",
        drop(["ag_year_start", "provisional"]),
        "provisional",
    ),
    (
        "start-month-zero",
        "calendar",
        put(["ag_year_start", "month"], 0),
        "greater than or equal to 1",
    ),
    (
        "start-month-without-provenance-label",
        "calendar",
        drop(["ag_year_start", "provenance"]),
        "provenance label",
    ),
    (
        "missing-start-month-without-reason",
        "calendar",
        put(["ag_year_start"], {"month": None}),
        "missing part with its reason",
    ),
    (
        "feasible-calendar-with-violations",
        "calendar",
        put(
            ["feasibility", "violations"],
            [
                {
                    "rule": "PLACEHOLDER-rule",
                    "component_ids": ["PLACEHOLDER-component-1"],
                }
            ],
        ),
        "lists no violations",
    ),
    (
        "infeasible-calendar-without-violations",
        "calendar",
        put(["feasibility", "feasible"], False),
        "at least one violation",
    ),
    (
        "violation-that-names-an-unknown-component",
        "calendar",
        put(
            ["feasibility"],
            {
                "feasible": False,
                "violations": [
                    {"rule": "PLACEHOLDER-rule", "component_ids": ["PLACEHOLDER-none"]}
                ],
            },
        ),
        "unknown component",
    ),
    ("calendar-unknown-extra-field", "calendar", put(["note"], "x"), "Extra inputs"),
    (
        "component-unknown-extra-field",
        "calendar",
        put([*COMPONENT, "yield"], 1.0),
        "Extra inputs",
    ),
    (
        "calendar-without-example-data-flag",
        "calendar",
        drop(["example_data"]),
        "example_data",
    ),
]

# Variants that stay valid. They show shapes the examples do not contain.
VALID: list[tuple[str, str, Mutation]] = [
    (
        "accepted-missing-date-with-reason",
        "calendar",
        put(
            [*COMPONENT, "end"],
            {
                "date": None,
                "missing": {"reason": "NOT_COMPUTABLE", "detail": "PLACEHOLDER"},
            },
        ),
    ),
    (
        "accepted-missing-start-month-with-reason",
        "calendar",
        put(["ag_year_start"], {"month": None, "missing": {"reason": "NOT_DECLARED"}}),
    ),
    (
        "accepted-infeasible-calendar-with-violation",
        "calendar",
        put(
            ["feasibility"],
            {
                "feasible": False,
                "violations": [
                    {
                        "rule": "PLACEHOLDER-rule",
                        "component_ids": ["PLACEHOLDER-component-2"],
                    }
                ],
            },
        ),
    ),
    # Overlap of two components is neither forbidden nor allowed by the
    # conventions or the blueprint: the question is OPEN in README.md. Until a
    # person answers it the model does not reject the overlap.
    (
        "accepted-while-open-overlapping-components",
        "calendar",
        put(["components", 1, "start", "date"], "2002-02-01"),
    ),
    (
        "accepted-missing-slope-with-reason",
        "soil",
        put(
            ["slope_length"],
            {
                "value": None,
                "unit": "PLACEHOLDER_unit",
                "missing": {"reason": "NO_COVERAGE"},
            },
        ),
    ),
    (
        "accepted-zero-as-a-value",
        "soil",
        both(
            put(["slope_steepness", "value"], 0.0),
            put(["slope_steepness", "range", "low"], 0.0),
        ),
    ),
]


@pytest.mark.parametrize("contract", sorted(CONTRACTS))
def test_example_loads_into_its_model(contract: str) -> None:
    model, filename = CONTRACTS[contract]
    text = (EXAMPLES / filename).read_text(encoding="utf-8")
    loaded = model.model_validate_json(text)
    # Nothing is added, dropped or changed on the way through the model.
    assert json.loads(loaded.model_dump_json(exclude_unset=True)) == json.loads(text)
    assert model.model_validate(json.loads(text)) == loaded


@pytest.mark.parametrize("contract", sorted(CONTRACTS))
def test_example_is_marked_as_example_data(contract: str) -> None:
    _, filename = CONTRACTS[contract]
    assert filename.startswith("PLACEHOLDER_")
    data = load(contract)
    assert data["example_data"] is True
    assert "PLACEHOLDER" in data["case_id"]
    assert "PLACEHOLDER" in data["field_id"]


def test_every_example_file_has_a_model() -> None:
    on_disk = sorted(path.name for path in EXAMPLES.iterdir())
    assert on_disk == sorted(filename for _, filename in CONTRACTS.values())


@pytest.mark.parametrize(
    ("contract", "mutation", "fragment"),
    [
        pytest.param(contract, mutation, fragment, id=case)
        for case, contract, mutation, fragment in INVALID
    ],
)
def test_invalid_variant_is_rejected(
    contract: str, mutation: Mutation, fragment: str
) -> None:
    model, _ = CONTRACTS[contract]
    data = load(contract)
    variant = copy.deepcopy(data)
    mutation(variant)
    assert variant != data, "the mutation changed nothing"
    with pytest.raises(ValidationError) as rejected:
        model.model_validate(variant)
    assert fragment in _describe(rejected.value)
    # The same variant is rejected when it arrives as JSON text.
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(variant))


@pytest.mark.parametrize(
    ("contract", "mutation"),
    [pytest.param(contract, mutation, id=case) for case, contract, mutation in VALID],
)
def test_valid_variant_is_accepted(contract: str, mutation: Mutation) -> None:
    model, _ = CONTRACTS[contract]
    variant = load(contract)
    mutation(variant)
    model.model_validate(variant)
    model.model_validate_json(json.dumps(variant))


def test_case_identifiers_are_unique() -> None:
    cases = [case for case, *_ in INVALID] + [case for case, *_ in VALID]
    assert len(cases) == len(set(cases))


def test_readme_lists_every_proposed_case() -> None:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert "## PROPOSED cases" in readme
    assert "## OPEN" in readme
    listed = readme.split("## PROPOSED cases", 1)[1].split("\n## ", 1)[0]
    for case in [case for case, *_ in INVALID] + [case for case, *_ in VALID]:
        assert f"`{case}`" in listed, f"README.md does not list the case {case}"


def _describe(error: ValidationError) -> str:
    """Location and message of every error, one per line."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"{location}: {item['msg']}")
    return "\n".join(lines)
