"""The two rotations of D128 that the interface holds for the demonstration.

Issue #354, PROPOSED (interface lane, under D159 and D161). The file
``web/src/data/demo_rotations_d128.json`` was added at the request of the
orchestrating session (D161), citing D128 and D72: the decision section sends
these two definitions to ``POST /api/decisions/run`` for ``example-field-1``.

This test checks the file against what it claims to be, without asserting a
single result of any engine:

- each definition validates against the contract
  (``contracts/rotation_definition``);
- the two are the pair ``DEMO_ROTATIONS`` of ``api/test_runner_residues.py``,
  crop for crop and date for date, on the same PLACEHOLDER years;
- the month and day of every date are those of row USER-AP (D72) of
  ``docs/SCIENCE_DECISIONS.md``;
- every crop id is a crop of the scopes of the parameter catalogue the
  service loads (``params/records``);
- the shared settings: the example case and field, the example mark, a
  repeating cycle, the agricultural-year start of the existing example, and
  dates declared by the user;
- each label names D128 and D72 and says the dates are scenario dates, not
  observed harvests;
- the existing ``web/src/data/rotation_definition.json`` is still the contract
  example, unchanged.

Run from the repository root:
``python -m pytest web/test_demo_rotations_d128.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from api.test_runner_residues import DEMO_ROTATIONS
from contracts.rotation_definition.rotation_definition import RotationDefinition

ROOT = Path(__file__).resolve().parent.parent
DEMO_FILE = ROOT / "web" / "src" / "data" / "demo_rotations_d128.json"
EXISTING_FILE = ROOT / "web" / "src" / "data" / "rotation_definition.json"
CONTRACT_EXAMPLE = (
    ROOT
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
SCIENCE_DECISIONS = ROOT / "docs" / "SCIENCE_DECISIONS.md"
RECORDS = ROOT / "params" / "records"

# The crops of each component, named as row USER-AP names them (D72).
USER_AP_NAMES = {
    "soybean-winter-fallow": ["annual soybean"],
    "wheat-soybean-maize": ["wheat", "second-crop soybean", "maize"],
}
MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        start=1,
    )
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo() -> list[dict]:
    return load(DEMO_FILE)


def user_ap_calendar() -> dict[str, tuple[str, str]]:
    """The nominal calendar of row USER-AP: crop name to (sowing, harvest) as MM-DD."""
    rows = [
        line
        for line in SCIENCE_DECISIONS.read_text(encoding="utf-8").splitlines()
        if line.startswith("| USER-AP (D72) |")
    ]
    assert len(rows) == 1
    found = re.findall(
        r"(annual soybean|second-crop soybean|wheat|maize) "
        r"(\d{1,2}) ([A-Z][a-z]{2}) to (\d{1,2}) ([A-Z][a-z]{2})",
        rows[0],
    )
    calendar = {
        name: (
            f"{MONTHS[sow_month]:02d}-{int(sow_day):02d}",
            f"{MONTHS[harvest_month]:02d}-{int(harvest_day):02d}",
        )
        for name, sow_day, sow_month, harvest_day, harvest_month in found
    }
    assert sorted(calendar) == [
        "annual soybean",
        "maize",
        "second-crop soybean",
        "wheat",
    ]
    return calendar


def catalogue_crops() -> set[str]:
    crops: set[str] = set()
    for path in RECORDS.rglob("*.json"):
        scope = load(path).get("scope")
        if isinstance(scope, dict) and isinstance(scope.get("crop"), str):
            crops.add(scope["crop"])
    return crops


def test_each_definition_validates_against_the_contract(demo):
    assert isinstance(demo, list)
    assert len(demo) == 2
    for document in demo:
        RotationDefinition.model_validate(document)


def test_the_pair_is_the_demo_pair_of_the_runner_test(demo):
    assert [document["rotation_id"] for document in demo] == list(DEMO_ROTATIONS)
    for document in demo:
        components = sorted(document["components"], key=lambda item: item["position"])
        assert [
            (item["crop_id"], item["sowing"]["date"], item["harvest"]["date"])
            for item in components
        ] == DEMO_ROTATIONS[document["rotation_id"]]


def test_the_month_and_day_of_every_date_are_those_of_user_ap(demo):
    calendar = user_ap_calendar()
    for document in demo:
        components = sorted(document["components"], key=lambda item: item["position"])
        names = USER_AP_NAMES[document["rotation_id"]]
        assert len(components) == len(names)
        for item, name in zip(components, names, strict=True):
            assert (
                item["sowing"]["date"][5:],
                item["harvest"]["date"][5:],
            ) == calendar[name]


def test_every_crop_is_a_crop_of_the_catalogue(demo):
    crops = catalogue_crops()
    for document in demo:
        for item in document["components"]:
            assert item["crop_id"] in crops


def test_the_shared_settings(demo):
    existing = load(EXISTING_FILE)
    for document in demo:
        assert document["case_id"] == "example-case"
        assert document["field_id"] == "example-field-1"
        assert document["example_data"] is True
        assert document["repeats"] is True
        assert document["ag_year_start"] == existing["ag_year_start"]
        for item in document["components"]:
            for event in (item["sowing"], item["harvest"]):
                assert event["provenance"] == "DECLARED"
                assert event["source"] == "user"


def test_each_label_names_d128_and_d72_and_says_scenario_dates(demo):
    for document in demo:
        label = document["label"]
        assert "D128" in label
        assert "D72" in label
        assert "scenario dates, not observed harvests" in label


def test_the_existing_rotation_definition_is_unchanged():
    assert load(EXISTING_FILE) == load(CONTRACT_EXAMPLE)
