"""Acceptance test of the contract "ResidueLedger" (unit l1/residue-ledger-ep4, #220).

The PLACEHOLDER example loads into ``ResidueLedger`` and each invalid variant
is rejected. The cases are PROPOSED (blueprint section 3.7) and are listed in
``README.md`` under "PROPOSED cases"; a test checks that the two lists agree.

Run from the repository root: ``python -m pytest contracts/residue_ledger/``.
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

from contracts.residue_ledger import CARBON_FIELDS, MASS_FIELDS, ResidueLedger

HERE = Path(__file__).parent
EXAMPLE = HERE / "examples" / "PLACEHOLDER_residue_ledger.json"
README = HERE / "README.md"
GONE = {"reason": "MISSING_INPUT", "detail": "PLACEHOLDER: the input named here"}


def load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def rejected(data: dict[str, Any], words: str) -> None:
    with pytest.raises(ValidationError) as caught:
        ResidueLedger.model_validate(data)
    assert words in str(caught.value), str(caught.value)


def test_example_loads():
    ledger = ResidueLedger.model_validate(load())
    assert ledger.carbon_input_unit != ledger.carbon_unit  # the series' own unit
    assert ledger.example_data is True
    assert (ledger.first_ag_year, ledger.last_ag_year) == (2001, 2002)
    assert [item.purpose for item in ledger.components] == ["grain", "cover", "grain"]
    assert ledger.components[1].ag_year is None


def test_example_round_trips_through_json():
    ledger = ResidueLedger.model_validate(load())
    again = ResidueLedger.model_validate(ledger.model_dump(mode="json"))
    assert again == ledger


def test_example_closes_mass_and_carbon():
    """The example is consistent: retained plus exported is produced."""
    for item in ResidueLedger.model_validate(load()).components:
        for kind in ("mass", "carbon"):
            produced = getattr(item, f"aboveground_{kind}_produced").value
            if produced is None:
                continue
            exported = getattr(item, f"aboveground_{kind}_exported").value
            retained = getattr(item, f"aboveground_{kind}_retained").value
            assert retained + exported == pytest.approx(produced)


def test_every_value_missing_loads():
    data = load()
    for item in data["components"]:
        for name in MASS_FIELDS + CARBON_FIELDS:
            unit = item[name]["unit"]
            item[name] = {"value": None, "unit": unit, "missing": dict(GONE)}
    for series in data["annual_carbon_inputs"]:
        for key in ("provenance", "source", "range_missing"):
            series.pop(key, None)
        for year in series["years"]:
            year["value"] = None
            year["missing"] = dict(GONE)
    ResidueLedger.model_validate(data)


def test_ledger_without_years_loads():
    data = load()
    data.update(
        first_ag_year=None,
        last_ag_year=None,
        years_missing={"reason": "NO_COVERAGE", "detail": "PLACEHOLDER: no year"},
        components=[],
        annual_carbon_inputs=[],
        monthly_carbon_inputs=[],  # D221: no years, no monthly series either
    )
    ResidueLedger.model_validate(data)
    data["monthly_carbon_inputs"] = load()["monthly_carbon_inputs"]
    rejected(data, "lists no component and no series")


def test_monthly_series_follow_d221():
    """D221 of #77: one monthly series per origin of D194, over every month of
    the agricultural years of the ledger, in carbon_input_unit; an explicit
    zero in a month without a harvest, missing with its reason never zero."""
    ledger = ResidueLedger.model_validate(load())
    by_origin = {s.origin: s for s in ledger.monthly_carbon_inputs}
    assert set(by_origin) == {
        "placeholder_crop_a_aboveground",
        "placeholder_crop_a_belowground",
        "placeholder_crop_b_aboveground",
        "placeholder_crop_b_belowground",
    }
    for series in ledger.monthly_carbon_inputs:
        assert series.quantity == f"{series.origin}_carbon_input"
        assert series.unit == ledger.carbon_input_unit
        assert len(series.months) == 12 * 2
    above = by_origin["placeholder_crop_a_aboveground"]
    assert [m.value for m in above.months].count(0.0) == 22  # explicit zeros
    below = by_origin["placeholder_crop_a_belowground"]
    may_2002 = [m for m in below.months if (m.year, m.month) == (2002, 5)][0]
    assert may_2002.value is None and may_2002.missing.reason == "MISSING_INPUT"


def test_monthly_series_rules_are_checked():
    cases = []
    data = load()
    data["monthly_carbon_inputs"][1]["origin"] = "placeholder_crop_a_aboveground"
    data["monthly_carbon_inputs"][1]["quantity"] = (
        "placeholder_crop_a_aboveground_carbon_input"
    )
    cases.append((data, "has more than one series"))
    data = load()
    data["monthly_carbon_inputs"][0]["origin"] = "placeholder_crop_a"
    data["monthly_carbon_inputs"][0]["quantity"] = "placeholder_crop_a_carbon_input"
    cases.append((data, "is not '<crop>_aboveground' or '<crop>_belowground'"))
    data = load()
    data["monthly_carbon_inputs"][0]["origin"] = "placeholder_crop_c_aboveground"
    data["monthly_carbon_inputs"][0]["quantity"] = (
        "placeholder_crop_c_aboveground_carbon_input"
    )
    cases.append((data, "is not '<crop>_aboveground' or '<crop>_belowground'"))
    data = load()
    data["monthly_carbon_inputs"][0]["quantity"] = "placeholder_other_quantity"
    cases.append((data, "its quantity is not its origin followed by"))
    data = load()
    data["monthly_carbon_inputs"][0]["unit"] = data["carbon_unit"]
    cases.append((data, "is not in the carbon_input_unit"))
    data = load()
    series = data["monthly_carbon_inputs"][0]
    series["end"] = {"year": 2002, "month": 11}
    series["months"].pop()
    cases.append((data, "runs over every month of the agricultural years"))
    data = load()
    for series in data["monthly_carbon_inputs"]:
        series["start"] = {"year": 2000, "month": 1}
        series["end"] = {"year": 2001, "month": 12}
        for item in series["months"]:
            item["year"] -= 1
    cases.append((data, "runs over every month of the agricultural years"))
    data = load()
    series = data["monthly_carbon_inputs"][3]
    series["start"] = {"year": 2001, "month": 2}
    series["end"] = {"year": 2003, "month": 1}
    for index, item in enumerate(series["months"]):
        item["year"], item["month"] = 2001 + (index + 1) // 12, (index + 1) % 12 + 1
    cases.append((data, "every series starts in the same month"))
    for data, words in cases:
        rejected(data, words)


def test_years_and_their_missing_reason_together_are_rejected():
    data = load()
    data["years_missing"] = dict(GONE)
    rejected(data, "never both")


def test_ledger_without_years_or_reason_is_rejected():
    data = load()
    data["first_ag_year"] = None
    rejected(data, "come together")
    data["last_ag_year"] = None
    rejected(data, "carries the reason in years_missing")


def test_ledger_without_years_listing_components_is_rejected():
    data = load()
    data.update(first_ag_year=None, last_ag_year=None, years_missing=dict(GONE))
    rejected(data, "lists no component and no series")


def test_years_out_of_order_are_rejected():
    data = load()
    data["first_ag_year"] = 2003
    rejected(data, "last_ag_year is before first_ag_year")


def test_component_twice_in_one_cycle_is_rejected():
    data = load()
    data["components"][2]["cycle"] = 0
    rejected(data, "appears twice in cycle 0")


def test_lead_in_cycle_is_admitted_and_nothing_lower():
    """Cycle -1 is the lead-in of D141 (point 13 of engine/calendar/repeat.py),
    admitted by D160; no cycle comes before it."""
    data = load()
    data["components"][0]["cycle"] = -1
    ledger = ResidueLedger.model_validate(data)
    assert [item.cycle for item in ledger.components] == [-1, 0, 1]
    assert ResidueLedger.model_validate(ledger.model_dump(mode="json")) == ledger
    twice = copy.deepcopy(data)
    twice["components"][2]["cycle"] = -1
    rejected(twice, "appears twice in cycle -1")
    data["components"][0]["cycle"] = -2
    rejected(data, "greater than or equal to -1")


def test_value_in_another_unit_than_the_ledger_is_rejected():
    data = load()
    data["components"][0]["root_mass"]["unit"] = "PLACEHOLDER_other_unit"
    rejected(data, "root_mass is not in the mass_unit")
    data = load()
    data["components"][0]["rhizodeposit_carbon"]["unit"] = "PLACEHOLDER_other_unit"
    rejected(data, "rhizodeposit_carbon is not in the carbon_unit")


def test_agricultural_year_without_harvest_date_is_rejected():
    data = load()
    data["components"][1]["ag_year"] = 2001
    rejected(data, "ag_year is given exactly when the harvest date is given")
    data = load()
    data["components"][0]["ag_year"] = None
    rejected(data, "ag_year is given exactly when the harvest date is given")


def test_unknown_purpose_or_residue_word_is_rejected():
    data = load()
    data["components"][0]["purpose"] = "placeholder_purpose"
    rejected(data, "purpose")
    data = load()
    data["components"][0]["residue_management"] = "PLACEHOLDER_word"
    rejected(data, "residue_management")


def test_series_rules_are_checked():
    data = load()
    data["annual_carbon_inputs"][1]["quantity"] = data["annual_carbon_inputs"][0][
        "quantity"
    ]
    rejected(data, "appears more than once")
    data = load()
    data["annual_carbon_inputs"][0]["last_ag_year"] = 2001
    data["annual_carbon_inputs"][0]["years"].pop()
    rejected(data, "are those of the ledger")
    data = load()
    data["annual_carbon_inputs"][0]["unit"] = "PLACEHOLDER_other_unit"
    rejected(data, "is not in the carbon_input_unit")
    data = load()
    data["annual_carbon_inputs"][0]["unit"] = data["carbon_unit"]
    rejected(data, "is not in the carbon_input_unit")
    data = load()
    data["annual_carbon_inputs"][0]["origin"] = "placeholder_unknown_crop_aboveground"
    rejected(data, "is not '<crop>_aboveground' for a crop of a component")


def test_series_origin_follows_the_part_group():
    """D194 of #77: the origin is <crop>_aboveground for the retained
    aboveground carbon and <crop>_belowground for root and rhizodeposit
    carbon, for a crop of a component of the ledger."""
    data = load()
    by_quantity = {s["quantity"]: s for s in data["annual_carbon_inputs"]}
    root = by_quantity["placeholder_crop_a_grain_root_carbon"]
    retained = by_quantity["placeholder_crop_a_grain_aboveground_carbon_retained"]
    assert root["origin"] == "placeholder_crop_a_belowground"
    assert retained["origin"] == "placeholder_crop_a_aboveground"
    ledger = ResidueLedger.model_validate(data)
    assert {s.origin for s in ledger.annual_carbon_inputs} == {
        "placeholder_crop_a_aboveground",
        "placeholder_crop_a_belowground",
        "placeholder_crop_b_aboveground",
    }
    for index, quantity, origin, words in (
        # the plain crop word is no longer an origin of a ledger series
        (1, "root_carbon", "placeholder_crop_a", "'<crop>_belowground'"),
        (0, "aboveground", "placeholder_crop_a", "'<crop>_aboveground'"),
        # the group that does not match the part at the end of the quantity
        (1, "root_carbon", "placeholder_crop_a_aboveground", "'<crop>_belowground'"),
        (2, "rhizodeposit", "placeholder_crop_a_aboveground", "'<crop>_belowground'"),
        (0, "aboveground", "placeholder_crop_a_belowground", "'<crop>_aboveground'"),
        # a crop that no component of the ledger has
        (1, "root_carbon", "placeholder_crop_c_belowground", "'<crop>_belowground'"),
    ):
        changed = load()
        assert quantity in changed["annual_carbon_inputs"][index]["quantity"]
        changed["annual_carbon_inputs"][index]["origin"] = origin
        rejected(changed, f"its origin is not {words}")
    changed = load()
    changed["annual_carbon_inputs"][0]["quantity"] = "placeholder_crop_a_grain_leaves"
    rejected(changed, "does not end in a part of the ledger")


def test_missing_value_without_reason_or_with_a_number_is_rejected():
    data = load()
    data["components"][0]["root_mass"]["value"] = None
    rejected(data, "missing part with its reason")
    data = load()
    data["components"][0]["root_mass"]["missing"] = copy.deepcopy(GONE)
    rejected(data, "never both")


def test_unknown_field_is_rejected():
    data = load()
    data["components"][0]["leaf_mass"] = data["components"][0]["root_mass"]
    rejected(data, "Extra inputs are not permitted")


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
