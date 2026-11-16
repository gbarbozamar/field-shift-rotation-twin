"""The response of the route with the AMG engine of unit l1/amg-v2-complete-d192.

Brief in issue #299; decisions D192, D193 and D199 of issue #77. The unit adds
the C:N modifier and the cut of the temperature modifier, takes the exponential
yearly step, and adds the soil C:N ratio to the forcing the runner builds
(``api/carbon_forcing.py``, code that runs on every request). It must change
no value the service returns: every AMG row stays missing until the records
EP5 reads are signed by a person (D34, D66).

These tests go through the route ``POST /api/rotations/run`` with the engines
of the repository, found by the runner at their paths:

- the response of the example rotation is the response with the forms of
  ``main`` put back in memory (five modifiers, the explicit step, three soil
  properties), except the reason and the detail of the AMG rows and of the
  ``amg`` module; every AMG row is missing and holds no number;
- the forcing the runner gives EP5 carries the soil C:N ratio, missing with
  its reason, naming D193.

The cut of the temperature modifier cannot be put back in memory this way. It
changes a value only where a rate coefficient is computed, and none is: the
rows are missing.

PROPOSED cases (blueprint section 3.7). The file is in ``engine/amg/`` because
the unit owns that folder and does not own ``api/`` (the platform lane); its
place is PROPOSED. The inputs are the PLACEHOLDER chain examples of
contracts/inputs/; the climate source is that example, never a network call.
No number is written here.

Run from the repository root:
``py -3.12 -m pytest engine/amg/test_runner_response.py``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.ports import ClimateRequest, ClimateResult, SourceInfo
from api import carbon_forcing as producer
from api.engines import discover_engine_functions
from api.main import create_app
from api.ports import RunSettings
from contracts.carbon_balance import CarbonBalance
from contracts.carbon_forcing import CarbonForcing
from contracts.inputs import SiteClimate
from engine.amg import entry
from params.catalogue import check_catalogue, load_folder

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = ROOT / "contracts" / "inputs" / "examples"
ROTATION_EXAMPLE = (
    ROOT
    / "contracts"
    / "rotation_definition"
    / "examples"
    / "PLACEHOLDER_rotation_definition.json"
)
ROUTE = "/api/rotations/run"
AMG = "amg"

# What unit l1/amg-v2-complete-d192 changed, as it was on main.
MODIFIERS_BEFORE = tuple(name for name in entry.MODIFIERS if name != "cn_ratio")
SCHEME_BEFORE = "explicit"
SOIL_PROPERTIES_BEFORE = tuple(
    quantity
    for quantity in producer.SOIL_PROPERTIES
    if quantity != producer.SOIL_CN_RATIO
)


class ChainClimate:
    """The PLACEHOLDER chain climate example, served as the climate source."""

    source_id = "PLACEHOLDER_CLIMATE"
    contract = "site_data_climate"

    def __init__(self, data: SiteClimate) -> None:
        self.data = data

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        return ClimateResult(
            data=self.data,
            source=SourceInfo(
                id=self.source_id, contract=self.contract, state="example"
            ),
        )


def rotation(kind: str) -> dict[str, Any]:
    """The rotation definition example, or a two-year variant of it (two
    phases): its first component, and that component again one year later
    with the crop of the second (PLACEHOLDER dates)."""
    document = json.loads(ROTATION_EXAMPLE.read_text(encoding="utf-8"))
    if kind == "example":
        return document
    first = document["components"][0]
    again = copy.deepcopy(first)
    again["component_id"] = "c2"
    again["position"] = first["position"] + 1
    again["crop_id"] = document["components"][1]["crop_id"]
    again["sowing"]["date"] = "2028-11-15"
    again["harvest"]["date"] = "2029-04-10"
    document["components"] = [first, again]
    return document


def catalogue(name: str) -> dict[str, dict]:
    """``empty``: no record. ``service``: the catalogue the service loads."""
    if name == "empty":
        return {}
    records, problems = load_folder(ROOT / "params" / "records")
    assert problems == [] and check_catalogue(records) == []
    return records


def post(document: dict[str, Any], parameters: dict[str, dict]) -> dict[str, Any]:
    climate = SiteClimate.model_validate_json(
        (EXAMPLES / "PLACEHOLDER_chain_site_climate.json").read_text(encoding="utf-8")
    )
    series = climate.daily_series[0]
    app = create_app(
        [],
        climate=ChainClimate(climate),
        soil_slope=ExampleSoilSlopeSource(
            EXAMPLES / "PLACEHOLDER_chain_site_soil_slope.json"
        ),
        settings=RunSettings(start_date=series.start_date, end_date=series.end_date),
        parameters=parameters,
    )
    body = {
        "site": {
            "case_id": document["case_id"],
            "field_id": document["field_id"],
            "latitude": climate.point.latitude.value,
            "longitude": climate.point.longitude.value,
        },
        "rotation": document,
    }
    response = TestClient(app).post(ROUTE, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def results_of(answer: dict[str, Any]) -> list[dict[str, Any]]:
    """The top-level result and the result of each scenario, where there is one."""
    found = [answer["result"], *(s["result"] for s in answer["scenarios"])]
    return [result for result in found if result is not None]


def amg_rows(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for result in results_of(answer)
        for row in result["soil_carbon_trend"]
        if row["carbon_model"] == AMG
    ]


def amg_modules(answer: dict[str, Any]) -> list[dict[str, Any]]:
    lists = [answer["modules"], *(s["modules"] for s in answer["scenarios"])]
    return [module for modules in lists for module in modules if module["id"] == AMG]


def without_amg_reasons(answer: dict[str, Any]) -> dict[str, Any]:
    """The response with the reason and the detail of the AMG rows, and of
    the ``amg`` module, taken out. Nothing else is taken out."""
    answer = copy.deepcopy(answer)
    for row in amg_rows(answer):
        if row.get("missing") is not None:
            row["missing"] = {"reason": None, "detail": None}
    for module in amg_modules(answer):
        module["reason"] = None
        module["detail"] = None
    return answer


def numbers_in(value: Any) -> list[Any]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, int | float):
        return [value]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    return [n for v in value for n in numbers_in(v)]


def engines_or_skip() -> Any:
    found = discover_engine_functions()
    if found.build_rotation_calendar is None or found.run_amg is None:
        pytest.skip("the calendar engine or engine.amg.run_amg is not built")
    return found


@pytest.mark.parametrize("kind", ["example", "two_crops"])
@pytest.mark.parametrize("records", ["empty", "service"])
def test_the_response_is_the_one_of_the_forms_of_main_but_for_the_amg_reasons(
    kind, records, monkeypatch
):
    """D192, D193: the unit changes no value the service returns. With the
    sixth modifier, the exponential step and the fourth soil property, the
    response of the example rotation is the response with the forms of main
    put back in memory, except the reason and the detail of the AMG rows and
    of the ``amg`` module. Every AMG row is missing, with a reason and a
    detail, and holds no number."""
    engines_or_skip()
    parameters = catalogue(records)
    if records == "empty":
        assert not any(r["id"].startswith("amg_") for r in parameters.values())
    else:
        assert any(r["id"].startswith("amg_") for r in parameters.values())
    assert entry.SCHEME == "exponential" and "cn_ratio" in entry.MODIFIERS
    assert producer.SOIL_CN_RATIO in producer.SOIL_PROPERTIES
    now = post(rotation(kind), parameters)

    monkeypatch.setattr(entry, "MODIFIERS", MODIFIERS_BEFORE)
    monkeypatch.setattr(entry, "SCHEME", SCHEME_BEFORE)
    monkeypatch.setattr(producer, "SOIL_PROPERTIES", SOIL_PROPERTIES_BEFORE)
    before = post(rotation(kind), parameters)

    assert without_amg_reasons(now) == without_amg_reasons(before)
    for answer in (now, before):
        rows = amg_rows(answer)
        assert rows, "no AMG row in the response"
        for row in rows:
            assert row["value"] is None
            assert row["missing"]["reason"] and row["missing"]["detail"]
            assert numbers_in(row) == []
        modules = amg_modules(answer)
        assert modules and all(m["state"] == "not_available" for m in modules)
    # The same number of phases, each with its AMG rows.
    assert len(amg_rows(now)) == len(amg_rows(before))
    assert len(now["scenarios"]) == {"example": 1, "two_crops": 2}[kind]


@pytest.mark.parametrize("records", ["empty", "service"])
def test_the_forcing_the_runner_gives_ep5_carries_the_soil_cn_ratio(
    records, monkeypatch
):
    """D193 through the runner: the forcing EP5 receives carries
    ``soil_cn_ratio`` among its soil properties. The chain soil file holds no
    such item, so it is missing, ``NOT_AVAILABLE``, naming D193, never zero;
    and the balance EP5 returns holds no trend value."""
    found = engines_or_skip()
    real = found.run_amg
    seen: list[tuple[CarbonForcing, CarbonBalance]] = []

    def recording(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> Any:
        balance = real(forcing, parameters=parameters)
        seen.append((forcing, balance))
        return balance

    monkeypatch.setattr(
        "api.app.discover_engine_functions", lambda: replace(found, run_amg=recording)
    )
    answer = post(rotation("example"), catalogue(records))
    assert seen and len(seen) == len(answer["scenarios"])
    quantity = entry.FORCING_QUANTITIES["cn_ratio"][1]
    for forcing, balance in seen:
        assert [item.quantity for item in forcing.soil_properties] == list(
            producer.SOIL_PROPERTIES
        )
        (item,) = [p for p in forcing.soil_properties if p.quantity == quantity]
        assert item.value is None
        assert item.missing.reason == "NOT_AVAILABLE"
        assert "D193" in item.missing.detail
        assert all(row.value is None for row in balance.soil_carbon_trend)
        assert all(row.missing.reason for row in balance.soil_carbon_trend)
