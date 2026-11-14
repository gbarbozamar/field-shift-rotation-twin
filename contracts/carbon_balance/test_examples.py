"""Acceptance test of the contract "CarbonBalance" (unit l1/amg-ep5, issue #192).

The PLACEHOLDER example loads into ``CarbonBalance``, a monthly variant of it
(the shape EP6 would return) loads too, and each invalid variant is
rejected. The cases are PROPOSED (blueprint section 3.7) and are listed in
``README.md`` under "PROPOSED cases"; a test checks that the two lists agree.

Run from the repository root: ``python -m pytest contracts/carbon_balance/``.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.carbon_balance import CarbonBalance

HERE = Path(__file__).parent
EXAMPLE = HERE / "examples" / "PLACEHOLDER_carbon_balance.json"
README = HERE / "README.md"


def load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def rejected(data: dict[str, Any], words: str) -> None:
    with pytest.raises(ValidationError) as caught:
        CarbonBalance.model_validate(data)
    assert words in str(caught.value), str(caught.value)


def all_series(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [data["total_stock"], *data["pools"], *data["flows"]]


def test_example_loads():
    balance = CarbonBalance.model_validate(load())
    assert balance.example_data is True
    assert balance.carbon_model == "amg"
    assert [item.computation for item in balance.soil_carbon_trend] == [
        "end_minus_start",
        "fitted_slope",
        "mean_over_cycles",
    ]


def test_example_round_trips_through_json():
    balance = CarbonBalance.model_validate(load())
    again = CarbonBalance.model_validate(balance.model_dump(mode="json"))
    assert again == balance


def test_monthly_steps_load_for_the_other_carbon_model():
    """The shape EP6 would return: one step per month, carbon model ``rothc``."""
    data = load()
    data["carbon_model"] = "rothc"
    for trend in data["soil_carbon_trend"]:
        trend["carbon_model"] = "rothc"
    data["horizon"] = {
        "start": {"year": 2001, "month": 1},
        "end": {"year": 2001, "month": 2},
    }
    for series in all_series(data):
        for position, item in enumerate(series["steps"]):
            month = {"year": 2001, "month": position + 1}
            item["start"] = dict(month)
            item["end"] = dict(month)
    balance = CarbonBalance.model_validate(data)
    assert len(balance.total_stock.steps) == 2


def test_every_value_missing_loads():
    """A balance in which nothing is computed is valid: each value missing with its reason."""
    data = load()
    gone = {"reason": "MISSING_INPUT", "detail": "PLACEHOLDER: the input named here"}
    for series in all_series(data):
        for key in ("provenance", "source", "range_missing"):
            series.pop(key)
        for item in series["steps"]:
            item["value"] = None
            item["missing"] = dict(gone)
        if "initial" in series:
            series["initial"] = {
                "value": None,
                "unit": series["unit"],
                "missing": dict(gone),
            }
    for trend in data["soil_carbon_trend"]:
        for key in ("provenance", "source", "range_missing"):
            trend.pop(key, None)
        trend["value"] = None
        trend["missing"] = dict(gone)
    CarbonBalance.model_validate(data)


def test_steps_that_do_not_cover_the_horizon_are_rejected():
    data = load()
    data["horizon"]["end"] = {"year": 2003, "month": 12}
    rejected(data, "from the first month of the horizon to its last")


def test_steps_with_a_gap_are_rejected():
    data = load()
    for series in all_series(data):
        series["steps"][1]["start"] = {"year": 2002, "month": 2}
    rejected(data, "no gap and no overlap")


def test_series_with_other_steps_than_the_total_are_rejected():
    data = load()
    pool = data["pools"][0]
    pool["steps"][0]["end"] = {"year": 2001, "month": 11}
    pool["steps"][1]["start"] = {"year": 2001, "month": 12}
    rejected(data, "the same steps as total_stock")


def test_step_that_ends_before_it_starts_is_rejected():
    data = load()
    data["flows"][0]["steps"][0]["end"] = {"year": 2000, "month": 12}
    rejected(data, "ends before it starts")


def test_repeated_quantity_is_rejected():
    data = load()
    data["flows"][0]["quantity"] = data["pools"][0]["quantity"]
    rejected(data, "appears more than once")


def test_initial_in_another_unit_is_rejected():
    data = load()
    data["pools"][0]["initial"]["unit"] = "PLACEHOLDER_other_unit"
    rejected(data, "initial is in the unit of the series")


@pytest.mark.parametrize("drop", [0, 1, 2])
def test_trend_without_each_computation_once_is_rejected(drop):
    data = load()
    data["soil_carbon_trend"].pop(drop)
    rejected(data, "each of the three computations once")
    data = load()
    data["soil_carbon_trend"][drop] = copy.deepcopy(
        data["soil_carbon_trend"][(drop + 1) % 3]
    )
    rejected(data, "each of the three computations once")


def test_trend_of_another_carbon_model_is_rejected():
    data = load()
    data["soil_carbon_trend"][0]["carbon_model"] = "rothc"
    rejected(data, "never merged")


def test_trend_in_another_unit_is_rejected():
    data = load()
    data["soil_carbon_trend"][0]["unit"] = "PLACEHOLDER_unit"
    rejected(data, "is not the unit of 'soil_carbon_trend'")


def test_missing_step_without_reason_or_with_a_number_is_rejected():
    data = load()
    data["flows"][0]["steps"][0]["value"] = None
    rejected(data, "missing part with its reason")
    data = load()
    data["flows"][0]["steps"][0]["missing"] = {"reason": "NOT_AVAILABLE"}
    rejected(data, "never both")


def test_present_values_without_provenance_or_range_reason_are_rejected():
    data = load()
    data["pools"][0].pop("provenance")
    rejected(data, "provenance label")
    data = load()
    data["pools"][0].pop("range_missing")
    rejected(data, "range_missing")


def test_unknown_field_and_unknown_carbon_model_are_rejected():
    data = load()
    data["end_state"] = []
    rejected(data, "Extra inputs are not permitted")
    data = load()
    data["carbon_model"] = "placeholder_model"
    rejected(data, "carbon_model")


def test_series_without_steps_is_rejected():
    data = load()
    data["flows"][0]["steps"] = []
    rejected(data, "has no step")


def section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_readme_lists_the_cases_of_this_file():
    listed = set(re.findall(r"`(test_\w+)`", section("PROPOSED cases")))
    module = sys.modules[__name__]
    written = {
        name
        for name, item in vars(module).items()
        if name.startswith("test_") and inspect.isfunction(item)
    }
    assert listed == written
