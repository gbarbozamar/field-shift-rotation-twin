"""Acceptance test of ``POST /api/rotations/run``, the interfaces and the stand-ins.

Run with ``uv run pytest api/`` from the repository root.

Status: PROPOSED test cases (blueprint section 3.7). Every number is an
obvious placeholder, every date is in year 1900 and every identifier is
``PLACEHOLDER_...``. No test asserts a scientific value.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapters.ports import ClimateRequest, ClimateResult, ClimateSource, SourceInfo
from api.main import create_app
from api.ports import (
    EnginesResult,
    ErrorDetail,
    Missing,
    ModuleStatus,
    RunSettings,
    SoilSlopeResult,
    SoilSlopeSource,
)
from api.rotations import derive_outcome
from api.standins import (
    ClimateUnavailable,
    SoilSlopeNotLoaded,
)
from contracts.inputs import RotationCalendar, SiteClimate, SiteSoilSlope
from contracts.results.models import ResultsPerRotation

CONTRACTS = Path(__file__).parent.parent / "contracts"


def load_example(model, folder: str, name: str):
    text = (CONTRACTS / folder / "examples" / name).read_text(encoding="utf-8")
    return model.model_validate(json.loads(text))


CLIMATE_EXAMPLE = load_example(SiteClimate, "inputs", "PLACEHOLDER_site_climate.json")
SOIL_SLOPE_EXAMPLE = load_example(
    SiteSoilSlope, "inputs", "PLACEHOLDER_site_soil_slope.json"
)
CALENDAR_EXAMPLE = load_example(
    RotationCalendar, "inputs", "PLACEHOLDER_rotation_calendar.json"
)
RESULT_EXAMPLE = load_example(
    ResultsPerRotation, "results", "PLACEHOLDER_results_per_rotation.json"
)

ROUTE = "/api/rotations/run"
ORIGIN = "http://localhost:5173"
PERIOD = RunSettings(start_date=dt.date(1900, 1, 1), end_date=dt.date(1900, 12, 31))
RETRIEVED = dt.datetime(1900, 1, 2, 3, 4, 5, tzinfo=dt.UTC)

SITE = {
    "case_id": "PLACEHOLDER_CASE",
    "field_id": "PLACEHOLDER_FIELD",
    "latitude": 1.0,
    "longitude": 2.0,
}
# A valid rotation: the PLACEHOLDER example of the rotation definition.
ROTATION = json.loads(
    (
        Path(__file__).parent.parent
        / "contracts"
        / "rotation_definition"
        / "examples"
        / "PLACEHOLDER_rotation_definition.json"
    ).read_text(encoding="utf-8")
)
BODY = {"site": SITE, "rotation": ROTATION}


# --- fakes --------------------------------------------------------------------


class FakeClimate:
    """Counts calls and answers fresh, cached or unavailable."""

    source_id = "PLACEHOLDER_CLIMATE"
    contract = "site_data_climate"

    def __init__(self, state: str = "fresh") -> None:
        self.state = state
        self.requests: list[ClimateRequest] = []

    def get_climate(self, request: ClimateRequest) -> ClimateResult:
        self.requests.append(request)
        if self.state == "unavailable":
            return ClimateResult(
                data=None,
                source=SourceInfo(
                    id="PLACEHOLDER_CLIMATE",
                    contract="site_data_climate",
                    state="unavailable",
                    missing_reason="SOURCE_UNAVAILABLE",
                ),
            )
        return ClimateResult(
            data=CLIMATE_EXAMPLE,
            source=SourceInfo(
                id="PLACEHOLDER_CLIMATE",
                contract="site_data_climate",
                state=self.state,  # type: ignore[arg-type]
                retrieved_at=RETRIEVED,
                time_zone="UTC",
                request={"PLACEHOLDER_KEY": "PLACEHOLDER_VALUE"},
                attribution="PLACEHOLDER_ATTRIBUTION",
            ),
        )


class FakeSoilSlope:
    source_id = "PLACEHOLDER_SOIL"
    contract = "site_data_soil_slope"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
        self.calls.append((case_id, field_id))
        return SoilSlopeResult(
            data=SOIL_SLOPE_EXAMPLE,
            source=SourceInfo(
                id="PLACEHOLDER_SOIL", contract="site_data_soil_slope", state="example"
            ),
        )


AVAILABLE = (
    ModuleStatus(id="PLACEHOLDER_MODULE_A", state="available"),
    ModuleStatus(
        id="PLACEHOLDER_MODULE_B",
        state="degraded",
        reason="MISSING_INPUT",
        detail="PLACEHOLDER_DETAIL",
    ),
)
# The route reads only the counts, never the result: a fake may declare them.
WITH_RESULT = EnginesResult(
    calendar=CALENDAR_EXAMPLE,
    result=RESULT_EXAMPLE,
    result_missing=None,
    modules=AVAILABLE,
    values_present=1,
    values_missing=1,
)


class FakeEngines:
    def __init__(self, answer: EnginesResult | None = None, raises: bool = False):
        self.answer = answer if answer is not None else WITH_RESULT
        self.raises = raises
        self.calls: list[tuple[Any, ClimateResult, SoilSlopeResult]] = []

    def run(self, rotation, climate, soil_slope) -> EnginesResult:
        self.calls.append((rotation, climate, soil_slope))
        if self.raises:
            raise RuntimeError("PLACEHOLDER_SECRET_EXCEPTION_TEXT")
        return self.answer


class FakeValidator:
    def validate(self, rotation) -> list[ErrorDetail]:
        return [
            ErrorDetail(
                path="PLACEHOLDER_FIELD.0", code="PLACEHOLDER_CODE", message="m"
            )
        ]


def client(**kwargs: Any) -> TestClient:
    kwargs.setdefault("settings", PERIOD)
    return TestClient(create_app([ORIGIN], **kwargs))


def numbers_in(value: Any) -> list[Any]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, int | float):
        return [value]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    return []


# --- the route ----------------------------------------------------------------


def test_valid_request_with_answering_fakes():
    climate, soil, engines = FakeClimate(), FakeSoilSlope(), FakeEngines()
    response = client(climate=climate, soil_slope=soil, engines=engines).post(
        ROUTE, json=BODY
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "partial"  # one module is degraded
    assert [s["id"] for s in body["sources"]] == [
        "PLACEHOLDER_CLIMATE",
        "PLACEHOLDER_SOIL",
    ]
    assert body["modules"] == [
        {
            "id": "PLACEHOLDER_MODULE_A",
            "state": "available",
            "reason": None,
            "detail": None,
        },
        {
            "id": "PLACEHOLDER_MODULE_B",
            "state": "degraded",
            "reason": "MISSING_INPUT",
            "detail": "PLACEHOLDER_DETAIL",
        },
    ]
    assert body["result_missing"] is None
    # Copied unchanged: nothing added, renamed or converted.
    assert body["result"] == RESULT_EXAMPLE.model_dump(mode="json")
    assert body["calendar"] == CALENDAR_EXAMPLE.model_dump(mode="json")
    assert ResultsPerRotation.model_validate_json(json.dumps(body["result"])) == (
        RESULT_EXAMPLE
    )
    assert RotationCalendar.model_validate_json(json.dumps(body["calendar"])) == (
        CALENDAR_EXAMPLE
    )
    assert soil.calls == [("PLACEHOLDER_CASE", "PLACEHOLDER_FIELD")]
    rotation, climate_result, soil_result = engines.calls[0]
    assert rotation == ROTATION
    assert climate_result.source.id == "PLACEHOLDER_CLIMATE"
    assert soil_result.source.id == "PLACEHOLDER_SOIL"


def test_complete_when_all_available_and_no_source_unavailable():
    engines = FakeEngines(
        EnginesResult(
            calendar=None,
            result=RESULT_EXAMPLE,
            values_present=1,
            result_missing=None,
            modules=(ModuleStatus(id="PLACEHOLDER_MODULE", state="available"),),
        )
    )
    response = client(
        climate=FakeClimate(), soil_slope=FakeSoilSlope(), engines=engines
    ).post(ROUTE, json=BODY)
    assert response.json()["outcome"] == "complete"


def test_default_app_answers_with_typed_absences_only(engines_hidden):
    # Built here, not at import: the engines are looked for when the app is built.
    response = TestClient(create_app([])).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_result"
    assert body["result"] is None
    assert body["calendar"] is None
    assert body["result_missing"]["reason"] == "NOT_AVAILABLE"
    assert body["modules"]
    assert all(m["state"] == "not_available" for m in body["modules"])
    assert all(s["state"] == "unavailable" for s in body["sources"])
    assert numbers_in(body) == []


def test_cached_answer_keeps_its_state_and_retrieval_time():
    response = client(climate=FakeClimate("cached"), engines=FakeEngines()).post(
        ROUTE, json=BODY
    )
    entry = response.json()["sources"][0]
    assert entry["state"] == "cached"
    assert entry["retrieved_at"] == "1900-01-02T03:04:05Z"


def test_retrieved_at_is_serialised_in_utc():
    other_zone = dt.timezone(dt.timedelta(hours=1))

    class OffsetClimate(FakeClimate):
        def get_climate(self, request):
            result = super().get_climate(request)
            source = SourceInfo(
                **{
                    **result.source.__dict__,
                    "retrieved_at": dt.datetime(1900, 1, 2, 4, 4, 5, tzinfo=other_zone),
                }
            )
            return ClimateResult(data=result.data, source=source)

    response = client(climate=OffsetClimate(), engines=FakeEngines()).post(
        ROUTE, json=BODY
    )
    assert response.json()["sources"][0]["retrieved_at"] == "1900-01-02T03:04:05Z"


def test_unavailable_climate_is_still_200_and_not_complete():
    response = client(
        climate=FakeClimate("unavailable"),
        soil_slope=FakeSoilSlope(),
        engines=FakeEngines(
            EnginesResult(
                calendar=None,
                result=RESULT_EXAMPLE,
                values_present=1,
                result_missing=None,
                modules=(ModuleStatus(id="PLACEHOLDER_MODULE", state="available"),),
            )
        ),
    ).post(ROUTE, json=BODY)
    assert response.status_code == 200
    body = response.json()
    entry = body["sources"][0]
    assert entry["state"] == "unavailable"
    assert entry["missing_reason"] == "SOURCE_UNAVAILABLE"
    assert body["outcome"] != "complete"


def test_no_period_configured_does_not_call_the_climate_source():
    climate = FakeClimate()
    response = client(climate=climate, settings=RunSettings()).post(ROUTE, json=BODY)
    assert response.status_code == 200
    assert climate.requests == []
    entry = response.json()["sources"][0]
    # The source describes itself; the route invents no identifier.
    assert entry["id"] == climate.source_id
    assert entry["contract"] == climate.contract
    assert entry["state"] == "unavailable"
    assert entry["missing_reason"] == "NOT_AVAILABLE"
    assert entry["detail"]


def test_climate_request_carries_site_and_period():
    climate = FakeClimate()
    client(climate=climate).post(ROUTE, json=BODY)
    assert climate.requests == [
        ClimateRequest(
            case_id="PLACEHOLDER_CASE",
            field_id="PLACEHOLDER_FIELD",
            latitude=1.0,
            longitude=2.0,
            start_date=dt.date(1900, 1, 1),
            end_date=dt.date(1900, 12, 31),
        )
    ]


def test_engine_exception_is_500_with_cors_and_no_exception_text(caplog):
    response = client(engines=FakeEngines(raises=True)).post(
        ROUTE, json=BODY, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" not in response.text
    assert "Traceback" not in response.text
    assert "PLACEHOLDER_SECRET_EXCEPTION_TEXT" in caplog.text


@pytest.mark.parametrize(
    "answer",
    [
        # A module that is not available without a reason.
        EnginesResult(
            calendar=None,
            result=None,
            result_missing=Missing(reason="NOT_AVAILABLE"),
            modules=(ModuleStatus(id="PLACEHOLDER_MODULE", state="not_available"),),
        ),
        # No result and no reason for it.
        EnginesResult(calendar=None, result=None, result_missing=None),
        # A result and a reason for its absence at once.
        EnginesResult(
            calendar=None,
            result=RESULT_EXAMPLE,
            values_present=1,
            result_missing=Missing(reason="NOT_AVAILABLE"),
        ),
    ],
)
def test_engine_answer_breaking_the_envelope_rules_is_a_defect(answer):
    response = client(engines=FakeEngines(answer)).post(ROUTE, json=BODY)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_unavailable_source_without_reason_is_a_defect():
    # SourceInfo itself now refuses it, inside the call: still a defect.
    class NoReason:
        def get_soil_slope(self, case_id, field_id):
            return SoilSlopeResult(
                data=None,
                source=SourceInfo(
                    id="PLACEHOLDER_SOIL",
                    contract="site_data_soil_slope",
                    state="unavailable",
                ),
            )

    response = client(soil_slope=NoReason()).post(ROUTE, json=BODY)
    assert response.status_code == 500


def test_validator_problem_is_rotation_invalid_under_rotation():
    response = client(rotation_validator=FakeValidator()).post(ROUTE, json=BODY)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ROTATION_INVALID"
    assert error["details"]
    assert all(d["path"].startswith("rotation.") for d in error["details"])
    assert error["details"][0]["path"] == "rotation.PLACEHOLDER_FIELD.0"


def test_rotation_invalid_does_not_consult_sources_or_engines():
    climate, engines = FakeClimate(), FakeEngines()
    client(climate=climate, engines=engines, rotation_validator=FakeValidator()).post(
        ROUTE, json=BODY
    )
    assert climate.requests == []
    assert engines.calls == []


def test_preflight_for_the_run_route():
    response = client().options(
        ROUTE,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ORIGIN


# --- outcome ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result_present", "present", "missing", "modules", "sources", "expected"),
    [
        (False, 0, 0, ["available"], ["fresh"], "no_result"),
        (False, 0, 0, [], [], "no_result"),
        # A result in which no value is present: an infeasible calendar.
        (True, 0, 3, ["available"], ["fresh"], "no_result"),
        (True, 2, 0, ["available"], ["fresh", "cached"], "complete"),
        (True, 2, 0, ["available"], ["example"], "complete"),
        (True, 2, 0, [], [], "complete"),
        (True, 2, 1, ["available"], ["fresh"], "partial"),
        (True, 2, 0, ["available", "degraded"], ["fresh"], "partial"),
        (True, 2, 0, ["not_available"], ["fresh"], "partial"),
        (True, 2, 0, ["available"], ["fresh", "unavailable"], "partial"),
    ],
)
def test_derive_outcome(result_present, present, missing, modules, sources, expected):
    assert (
        derive_outcome(result_present, present, missing, modules, sources) == expected
    )


# --- stand-ins ----------------------------------------------------------------

PLACEHOLDER_REQUEST = ClimateRequest(
    case_id="PLACEHOLDER_CASE",
    field_id="PLACEHOLDER_FIELD",
    latitude=1.0,
    longitude=2.0,
    start_date=dt.date(1900, 1, 1),
    end_date=dt.date(1900, 12, 31),
)


def test_climate_standin():
    source: ClimateSource = ClimateUnavailable()
    result = source.get_climate(PLACEHOLDER_REQUEST)
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NOT_AVAILABLE"
    assert result.source.retrieved_at is None


def test_soil_slope_standin():
    source: SoilSlopeSource = SoilSlopeNotLoaded()
    result = source.get_soil_slope("PLACEHOLDER_CASE", "PLACEHOLDER_FIELD")
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NOT_AVAILABLE"


def test_run_settings_reject_a_reversed_period():
    with pytest.raises(ValueError):
        RunSettings(start_date=dt.date(1900, 12, 31), end_date=dt.date(1900, 1, 1))
    assert not RunSettings().has_period
    assert not RunSettings(start_date=dt.date(1900, 1, 1)).has_period
    assert PERIOD.has_period
