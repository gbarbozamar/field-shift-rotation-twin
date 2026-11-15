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
    )
    ResidueLedger.model_validate(data)


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
    rejected(data, "is not in the carbon_unit")
    data = load()
    data["annual_carbon_inputs"][0]["origin"] = "placeholder_unknown_crop"
    rejected(data, "not the crop of any component")


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
