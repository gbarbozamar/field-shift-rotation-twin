"""Acceptance tests for future climate & seasonal forecast adapters.

PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Zero live HTTP calls: every network test uses ``httpx.MockTransport`` against
``.invalid`` URLs, ``FileCache`` in ``tmp_path``, and a deterministic UTC clock.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from adapters.cache import FileCache
from adapters.future_climate_projections import (
    ISIMIP3B_CONTRAST_SCENARIOS,
    ISIMIP3B_ENSEMBLE_NAME,
    ISIMIP3B_MODEL_COUNT,
    NEX_GDDP_ENSEMBLE_NAME,
    EnsembleComparison,
    EnsembleCriterion,
    EnsembleModelRun,
    EnsembleSummary,
    FutureClimateRequest,
    FutureEnsemblePayload,
    FutureEnsembleSettings,
    FutureParameterSpec,
    Isimip3bSource,
    NexGddpCmip6Source,
    SeasonalForecastPayload,
    SeasonalForecastRequest,
    SeasonalForecastSettings,
    SeasonalForecastSubsetSource,
    compare_climate_ensembles,
)
from adapters.ports import ClimateRequest
from contracts.inputs.common import Missing
from contracts.inputs.site_climate import DailyValue

FIRST = dt.datetime(2026, 11, 15, 6, 0, tzinfo=dt.UTC)
LATER = dt.datetime(2026, 11, 15, 7, 0, tzinfo=dt.UTC)
PLACEHOLDER_FILL = -9999.0


class Clock:
    def __init__(self, *moments: dt.datetime) -> None:
        self._moments = list(moments)

    def __call__(self) -> dt.datetime:
        return self._moments.pop(0) if len(self._moments) > 1 else self._moments[0]


class FakeService:
    """Counts requests and responds via a test handler (no network)."""

    def __init__(self, handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def answer_with(document: dict[str, Any]):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    return handler


def _status(code: int, **kwargs: Any):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, **kwargs)

    return handler


def _raise(exc_type: type[Exception]):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("placeholder failure", request=request)

    return handler


def stored_files(folder):
    return sorted(folder.iterdir()) if folder.exists() else []


def _nex_settings_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "base_url": "https://projections.invalid/nex-gddp-cmip6/daily",
        "ensemble_name": NEX_GDDP_ENSEMBLE_NAME,
        "models": ("CMIP6_MODEL_A", "CMIP6_MODEL_B"),
        "scenarios": ("ssp245", "ssp585"),
        "parameters": (
            FutureParameterSpec(
                source_parameter="tasmax",
                quantity="air_temperature_max_2m",
                unit="degC",
                provenance="SIMULATED",
            ),
            FutureParameterSpec(
                source_parameter="tasmin",
                quantity="air_temperature_min_2m",
                unit="degC",
                provenance="SIMULATED",
            ),
            FutureParameterSpec(
                source_parameter="pr",
                quantity="precipitation",
                unit="mm day-1",
                provenance="DERIVED",
            ),
        ),
        "fill_value": PLACEHOLDER_FILL,
        "fill_reason": "NO_COVERAGE",
        "range_missing_reason": "NOT_AVAILABLE",
        "attribution": "PLACEHOLDER_NEX_GDDP_ATTRIBUTION",
        "source_id": "nex_gddp_cmip6",
        "timeout_seconds": 5.0,
    }
    fields.update(overrides)
    return fields


def _isimip_settings_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "base_url": "https://projections.invalid/isimip3b/daily",
        "ensemble_name": ISIMIP3B_ENSEMBLE_NAME,
        "models": tuple(
            f"ISIMIP_MODEL_{i}" for i in range(1, ISIMIP3B_MODEL_COUNT + 1)
        ),
        "scenarios": ISIMIP3B_CONTRAST_SCENARIOS,
        "parameters": (
            FutureParameterSpec(
                source_parameter="tasmax",
                quantity="air_temperature_max_2m",
                unit="degC",
                provenance="DERIVED",
            ),
            FutureParameterSpec(
                source_parameter="pr",
                quantity="precipitation",
                unit="mm day-1",
                provenance="DERIVED",
            ),
        ),
        "fill_value": PLACEHOLDER_FILL,
        "fill_reason": "NO_COVERAGE",
        "range_missing_reason": "NOT_AVAILABLE",
        "attribution": "PLACEHOLDER_ISIMIP3B_ATTRIBUTION",
        "source_id": "isimip3b",
        "timeout_seconds": 5.0,
    }
    fields.update(overrides)
    return fields


def _seasonal_settings_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "base_url": "https://projections.invalid/seasonal/subset",
        "forecast_system": "GEOS-S2S-3",
        "member_count": 4,
        "lead_months": (1, 2, 3),
        "tercile_labels": ("below_normal", "near_normal", "above_normal"),
        "parameters": (
            FutureParameterSpec(
                source_parameter="pr",
                quantity="precipitation",
                unit="mm month-1",
                provenance="SIMULATED",
            ),
        ),
        "fill_value": PLACEHOLDER_FILL,
        "fill_reason": "NO_COVERAGE",
        "range_missing_reason": "NOT_AVAILABLE",
        "attribution": "PLACEHOLDER_SEASONAL_ATTRIBUTION",
        "source_id": "geos_s2s_3",
        "timeout_seconds": 5.0,
    }
    fields.update(overrides)
    return fields


def _ensemble_doc(
    settings: FutureEnsembleSettings,
    start: dt.date,
    end: dt.date,
    *,
    base_offset: float = 0.0,
    inject_fill: bool = False,
) -> dict[str, Any]:
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    runs = []
    for m_idx, model in enumerate(settings.models):
        for s_idx, scenario in enumerate(settings.scenarios):
            param_map: dict[str, dict[str, float]] = {}
            for spec in settings.parameters:
                series: dict[str, float] = {}
                for d_idx, day in enumerate(days):
                    key = day.strftime("%Y%m%d")
                    if inject_fill and m_idx == 0 and d_idx == 0:
                        series[key] = PLACEHOLDER_FILL
                    elif spec.source_parameter == "pr" and d_idx == 0:
                        series[key] = 0.0  # real zero stays 0.0
                    else:
                        series[key] = (
                            base_offset + float(m_idx + 1) + 0.5 * s_idx + 0.1 * d_idx
                        )
                param_map[spec.source_parameter] = series
            runs.append(
                {
                    "model": model,
                    "scenario": scenario,
                    "parameters": param_map,
                }
            )
    return {
        "ensemble": settings.ensemble_name,
        "coverage": True,
        "time_zone": "UTC",
        "runs": runs,
    }


def _seasonal_doc(
    settings: SeasonalForecastSettings,
    init_date: dt.date,
    *,
    member_fill_at_first: bool = False,
) -> dict[str, Any]:
    subsets = []
    for spec in settings.parameters:
        for lead in settings.lead_months:
            members = [float(10 + lead + idx) for idx in range(settings.member_count)]
            if member_fill_at_first and lead == settings.lead_months[0]:
                members[0] = PLACEHOLDER_FILL
            subsets.append(
                {
                    "parameter": spec.source_parameter,
                    "lead_month": lead,
                    "tercile_probabilities": {
                        settings.tercile_labels[0]: 0.2,
                        settings.tercile_labels[1]: 0.3,
                        settings.tercile_labels[2]: 0.5,
                    },
                    "member_values": members,
                }
            )
    return {
        "forecast_system": settings.forecast_system,
        "coverage": True,
        "init_date": init_date.isoformat(),
        "subsets": subsets,
    }


def _build_nex(tmp_path, handler, settings=None, clock=None):
    cfg = settings or FutureEnsembleSettings(**_nex_settings_fields())
    service = FakeService(handler)
    client = httpx.Client(transport=httpx.MockTransport(service))
    cache_dir = tmp_path / "cache"
    source = NexGddpCmip6Source(
        cfg, FileCache(cache_dir), client, now=clock or Clock(FIRST, LATER)
    )
    return source, service, cache_dir


def _build_isimip(tmp_path, handler, settings=None, clock=None):
    cfg = settings or FutureEnsembleSettings(**_isimip_settings_fields())
    service = FakeService(handler)
    client = httpx.Client(transport=httpx.MockTransport(service))
    cache_dir = tmp_path / "cache"
    source = Isimip3bSource(
        cfg, FileCache(cache_dir), client, now=clock or Clock(FIRST, LATER)
    )
    return source, service, cache_dir


def _build_seasonal(tmp_path, handler, settings=None, clock=None):
    cfg = settings or SeasonalForecastSettings(**_seasonal_settings_fields())
    service = FakeService(handler)
    client = httpx.Client(transport=httpx.MockTransport(service))
    cache_dir = tmp_path / "cache"
    source = SeasonalForecastSubsetSource(
        cfg, FileCache(cache_dir), client, now=clock or Clock(FIRST, LATER)
    )
    return source, service, cache_dir


# --- 1. Settings validation (no defaults, https, exact-key from_mapping, C1.1, C4.1) ---


def test_no_setting_has_a_default():
    for cls in (FutureEnsembleSettings, SeasonalForecastSettings, FutureParameterSpec):
        for field in dataclasses.fields(cls):
            assert field.default is dataclasses.MISSING, f"{cls.__name__}.{field.name}"
            assert field.default_factory is dataclasses.MISSING, (
                f"{cls.__name__}.{field.name}"
            )


@pytest.mark.parametrize("name", sorted(_nex_settings_fields()))
def test_future_ensemble_settings_missing_field_raises(name):
    fields = _nex_settings_fields()
    del fields[name]
    with pytest.raises(TypeError, match=name):
        FutureEnsembleSettings(**fields)


@pytest.mark.parametrize("name", sorted(_seasonal_settings_fields()))
def test_seasonal_settings_missing_field_raises(name):
    fields = _seasonal_settings_fields()
    del fields[name]
    with pytest.raises(TypeError, match=name):
        SeasonalForecastSettings(**fields)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("base_url", ""),
        ("base_url", "http://projections.invalid/nex"),
        ("base_url", "https://projections.invalid/nex?x=1"),
        ("base_url", "https://projections.invalid/nex#frag"),
        ("base_url", "https:///no-host"),
        ("ensemble_name", "   "),
        ("models", ()),
        ("models", ("M1", "M1")),
        ("scenarios", ()),
        ("scenarios", ("ssp245", "ssp245")),
        ("parameters", ()),
        ("fill_value", float("nan")),
        ("fill_reason", "NOT_A_REASON"),
        ("range_missing_reason", ""),
        ("attribution", ""),
        ("source_id", ""),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", -2.0),
    ],
)
def test_future_ensemble_settings_invalid_values_raise(name, value):
    with pytest.raises(ValueError, match=name):
        FutureEnsembleSettings(**_nex_settings_fields(**{name: value}))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("base_url", "http://projections.invalid/seasonal"),
        ("base_url", "https://projections.invalid/seasonal?q=1"),
        ("forecast_system", ""),
        ("member_count", 0),
        ("lead_months", ()),
        ("lead_months", (1, 1)),
        ("lead_months", (0,)),
        ("lead_months", (13,)),
        ("tercile_labels", ("below", "near")),
        ("tercile_labels", ("below", "below", "above")),
        ("timeout_seconds", -1.0),
    ],
)
def test_seasonal_settings_invalid_values_raise(name, value):
    with pytest.raises(ValueError, match=name):
        SeasonalForecastSettings(**_seasonal_settings_fields(**{name: value}))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("source_parameter", ""),
        ("source_parameter", "tasmax,tasmin"),
        ("quantity", ""),
        ("quantity", "Air_Temperature"),
        ("quantity", "air-temp"),
        ("unit", "  "),
        ("provenance", "OBSERVED"),
        ("provenance", "DECLARED"),
        ("provenance", "simulated"),
    ],
)
def test_parameter_spec_rejects_non_c11_or_non_future_provenance(name, value):
    fields = {
        "source_parameter": "tasmax",
        "quantity": "air_temperature_max_2m",
        "unit": "degC",
        "provenance": "SIMULATED",
        name: value,
    }
    with pytest.raises(ValueError, match=name):
        FutureParameterSpec(**fields)


def test_settings_from_mapping_exact_keys():
    nex_raw = json.loads(
        json.dumps(
            dict(
                _nex_settings_fields(),
                models=list(_nex_settings_fields()["models"]),
                scenarios=list(_nex_settings_fields()["scenarios"]),
                parameters=[
                    dataclasses.asdict(p) for p in _nex_settings_fields()["parameters"]
                ],
            )
        )
    )
    assert FutureEnsembleSettings.from_mapping(nex_raw) == FutureEnsembleSettings(
        **_nex_settings_fields()
    )

    missing_doc = dict(nex_raw)
    del missing_doc["ensemble_name"]
    with pytest.raises(ValueError, match="ensemble_name"):
        FutureEnsembleSettings.from_mapping(missing_doc)

    extra_doc = dict(nex_raw, unknown_extra=123)
    with pytest.raises(ValueError, match="unknown_extra"):
        FutureEnsembleSettings.from_mapping(extra_doc)

    bad_param_doc = dict(
        nex_raw,
        parameters=[dict(nex_raw["parameters"][0], extra_field="x")],
    )
    with pytest.raises(ValueError, match="extra_field"):
        FutureEnsembleSettings.from_mapping(bad_param_doc)

    seasonal_raw = json.loads(
        json.dumps(
            dict(
                _seasonal_settings_fields(),
                lead_months=list(_seasonal_settings_fields()["lead_months"]),
                tercile_labels=list(_seasonal_settings_fields()["tercile_labels"]),
                parameters=[
                    dataclasses.asdict(p)
                    for p in _seasonal_settings_fields()["parameters"]
                ],
            )
        )
    )
    assert SeasonalForecastSettings.from_mapping(
        seasonal_raw
    ) == SeasonalForecastSettings(**_seasonal_settings_fields())

    del seasonal_raw["member_count"]
    with pytest.raises(ValueError, match="member_count"):
        SeasonalForecastSettings.from_mapping(seasonal_raw)


# --- 2. NexGddpCmip6Source & Isimip3bSource via MockTransport -----------------


def test_nex_gddp_fetches_caches_and_preserves_zero_and_fill(tmp_path):
    cfg = FutureEnsembleSettings(**_nex_settings_fields())
    start = dt.date(2050, 1, 1)
    end = dt.date(2050, 1, 3)
    doc = _ensemble_doc(cfg, start, end, base_offset=20.0, inject_fill=True)
    source, service, cache_dir = _build_nex(tmp_path, answer_with(doc), settings=cfg)

    req = FutureClimateRequest(
        case_id="case_f23",
        field_id="field_1",
        latitude=-34.6,
        longitude=-58.4,
        start_date=start,
        end_date=end,
    )
    first = source.get_projections(req)
    assert len(service.requests) == 1
    assert first.source.state == "fresh"
    assert first.source.retrieved_at == FIRST
    assert first.source.time_zone == "UTC"
    assert first.data is not None
    assert first.data.valid_for_normative_erosion is False
    assert first.data.ensemble_name == NEX_GDDP_ENSEMBLE_NAME
    # 2 models * 2 scenarios * 3 parameters (tasmax, tasmin, pr) = 12 runs
    assert len(first.data.runs) == 12
    assert all(r.valid_for_normative_erosion is False for r in first.data.runs)
    assert all(r.provenance in ("SIMULATED", "DERIVED") for r in first.data.runs)

    # Fill value stays None with reason; real 0.0 precipitation stays 0.0
    pr_model_a = next(
        r
        for r in first.data.runs
        if r.model_id == "CMIP6_MODEL_A"
        and r.scenario == "ssp245"
        and r.quantity == "precipitation"
    )
    assert pr_model_a.days[0].value is None
    assert pr_model_a.days[0].missing is not None
    assert pr_model_a.days[0].missing.reason == "NO_COVERAGE"

    pr_model_b = next(
        r
        for r in first.data.runs
        if r.model_id == "CMIP6_MODEL_B"
        and r.scenario == "ssp245"
        and r.quantity == "precipitation"
    )
    assert pr_model_b.days[0].value == 0.0
    assert pr_model_b.days[0].missing is None

    # No user-identifying params or auth headers
    (sent,) = service.requests
    assert "user" not in dict(sent.url.params.multi_items())
    assert "authorization" not in {k.lower() for k in sent.headers}

    # Second call uses cache
    second = source.get_projections(req)
    assert len(service.requests) == 1
    assert second.source.state == "cached"
    assert second.data == first.data
    assert len(stored_files(cache_dir)) == 1


def test_nex_gddp_also_accepts_port_climate_request(tmp_path):
    cfg = FutureEnsembleSettings(**_nex_settings_fields())
    start = dt.date(2050, 2, 1)
    end = dt.date(2050, 2, 2)
    doc = _ensemble_doc(cfg, start, end, base_offset=15.0)
    source, _, _ = _build_nex(tmp_path, answer_with(doc), settings=cfg)

    res = source.get_projections(
        ClimateRequest(
            case_id="case_port",
            field_id="field_port",
            latitude=10.0,
            longitude=-20.0,
            start_date=start,
            end_date=end,
        )
    )
    assert res.source.state == "fresh"
    assert res.data is not None
    assert res.data.valid_for_normative_erosion is False


def test_isimip3b_five_model_contrast_scenarios(tmp_path):
    cfg = FutureEnsembleSettings(**_isimip_settings_fields())
    start = dt.date(2050, 3, 1)
    end = dt.date(2050, 3, 3)
    doc = _ensemble_doc(cfg, start, end, base_offset=25.0)
    source, service, _ = _build_isimip(tmp_path, answer_with(doc), settings=cfg)

    req = FutureClimateRequest(
        case_id="case_isimip",
        field_id="field_2",
        latitude=-33.0,
        longitude=-60.0,
        start_date=start,
        end_date=end,
    )
    res = source.get_projections(req)
    assert len(service.requests) == 1
    assert res.source.state == "fresh"
    assert res.data is not None
    assert res.data.ensemble_name == ISIMIP3B_ENSEMBLE_NAME
    assert res.data.valid_for_normative_erosion is False
    # 5 models * 3 contrast scenarios * 2 parameters = 30 runs
    assert (
        len(res.data.runs)
        == ISIMIP3B_MODEL_COUNT * len(ISIMIP3B_CONTRAST_SCENARIOS) * 2
    )
    assert {r.scenario for r in res.data.runs} == set(ISIMIP3B_CONTRAST_SCENARIOS)
    assert len({r.model_id for r in res.data.runs}) == ISIMIP3B_MODEL_COUNT
    assert all(r.valid_for_normative_erosion is False for r in res.data.runs)


def test_ensemble_adapter_rejects_mismatched_ensemble_name(tmp_path):
    wrong_for_nex = FutureEnsembleSettings(
        **_nex_settings_fields(ensemble_name=ISIMIP3B_ENSEMBLE_NAME)
    )
    with pytest.raises(ValueError, match=NEX_GDDP_ENSEMBLE_NAME):
        _build_nex(tmp_path, answer_with({}), settings=wrong_for_nex)

    wrong_for_isimip = FutureEnsembleSettings(
        **_isimip_settings_fields(ensemble_name=NEX_GDDP_ENSEMBLE_NAME)
    )
    with pytest.raises(ValueError, match=ISIMIP3B_ENSEMBLE_NAME):
        _build_isimip(tmp_path, answer_with({}), settings=wrong_for_isimip)


# --- 3. SeasonalForecastSubsetSource via MockTransport -------------------------


@pytest.mark.parametrize("system", ["GEOS-S2S-3", "NMME"])
def test_seasonal_forecast_geos_and_nmme_subsets(tmp_path, system):
    cfg = SeasonalForecastSettings(
        **_seasonal_settings_fields(forecast_system=system, source_id=system.lower())
    )
    init_date = dt.date(2026, 11, 1)
    doc = _seasonal_doc(cfg, init_date, member_fill_at_first=True)
    source, service, _ = _build_seasonal(tmp_path, answer_with(doc), settings=cfg)

    req = SeasonalForecastRequest(
        case_id="case_s2s",
        field_id="field_3",
        latitude=-34.0,
        longitude=-59.0,
        init_date=init_date,
    )
    res = source.get_forecast_subset(req)
    assert len(service.requests) == 1
    assert res.source.state == "fresh"
    assert res.data is not None
    assert res.data.forecast_system == system
    assert res.data.valid_for_normative_erosion is False
    assert len(res.data.subsets) == 3

    first_subset = res.data.subsets[0]
    assert first_subset.valid_for_normative_erosion is False
    assert first_subset.provenance == "SIMULATED"
    assert sum(
        t.probability
        for t in first_subset.tercile_probabilities
        if t.probability is not None
    ) == pytest.approx(1.0)
    assert first_subset.member_values[0].value is None
    assert first_subset.member_values[0].missing is not None
    assert first_subset.member_values[0].missing.reason == "NO_COVERAGE"

    cached = source.get_forecast_subset(req)
    assert len(service.requests) == 1
    assert cached.source.state == "cached"
    assert cached.data == res.data


# --- 4. Typed failure modes without echoing raw response bodies ----------------


@pytest.mark.parametrize(
    ("kind", "handler", "expected_reason"),
    [
        ("timeout", _raise(httpx.ReadTimeout), "SOURCE_UNAVAILABLE"),
        ("connect-error", _raise(httpx.ConnectError), "SOURCE_UNAVAILABLE"),
        (
            "http-500",
            _status(500, text="PLACEHOLDER_SECRET_BODY"),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "http-404",
            _status(404, text="PLACEHOLDER_SECRET_BODY"),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "not-json",
            _status(200, text="<html>PLACEHOLDER_SECRET_BODY</html>"),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "json-nan",
            _status(200, text='{"runs": NaN, "secret": "PLACEHOLDER_SECRET_BODY"}'),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "json-list",
            _status(200, json=["PLACEHOLDER_SECRET_BODY"]),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "error-messages",
            _status(200, json={"messages": ["PLACEHOLDER_SECRET_BODY"]}),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "wrong-ensemble",
            _status(200, json={"ensemble": "PLACEHOLDER_SECRET_BODY", "runs": []}),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "coverage-false",
            _status(
                200,
                json={
                    "ensemble": NEX_GDDP_ENSEMBLE_NAME,
                    "coverage": False,
                    "runs": [],
                    "detail": "PLACEHOLDER_SECRET_BODY",
                },
            ),
            "NO_COVERAGE",
        ),
        (
            "empty-runs",
            _status(
                200,
                json={
                    "ensemble": NEX_GDDP_ENSEMBLE_NAME,
                    "runs": [],
                    "note": "PLACEHOLDER_SECRET_BODY",
                },
            ),
            "NO_COVERAGE",
        ),
        (
            "missing-model-run",
            _status(
                200,
                json={
                    "ensemble": NEX_GDDP_ENSEMBLE_NAME,
                    "runs": [
                        {
                            "model": "CMIP6_MODEL_A",
                            "scenario": "ssp245",
                            "parameters": {
                                "tasmax": {"20500101": 30.0},
                                "tasmin": {"20500101": 18.0},
                                "pr": {"20500101": 1.0},
                            },
                            "note": "PLACEHOLDER_SECRET_BODY",
                        }
                    ],
                },
            ),
            "MISSING_INPUT",
        ),
        (
            "missing-parameter",
            _status(
                200,
                json={
                    "ensemble": NEX_GDDP_ENSEMBLE_NAME,
                    "runs": [
                        {
                            "model": m,
                            "scenario": s,
                            "parameters": {
                                "tasmax": {"20500101": 30.0},
                                "tasmin": {"20500101": 18.0},
                                "secret": "PLACEHOLDER_SECRET_BODY",
                            },
                        }
                        for m in ("CMIP6_MODEL_A", "CMIP6_MODEL_B")
                        for s in ("ssp245", "ssp585")
                    ],
                },
            ),
            "MISSING_INPUT",
        ),
        (
            "bad-date-key",
            _status(
                200,
                json={
                    "ensemble": NEX_GDDP_ENSEMBLE_NAME,
                    "runs": [
                        {
                            "model": m,
                            "scenario": s,
                            "parameters": {
                                "tasmax": {"2050-01-01": 30.0},
                                "tasmin": {"20500101": 18.0},
                                "pr": {"20500101": 0.0},
                            },
                        }
                        for m in ("CMIP6_MODEL_A", "CMIP6_MODEL_B")
                        for s in ("ssp245", "ssp585")
                    ],
                },
            ),
            "SOURCE_UNAVAILABLE",
        ),
    ],
)
def test_ensemble_failures_are_typed_and_never_echo_body(
    tmp_path, kind, handler, expected_reason
):
    source, _, cache_dir = _build_nex(tmp_path, handler)
    req = FutureClimateRequest(
        case_id="case_err",
        field_id="field_err",
        latitude=1.0,
        longitude=2.0,
        start_date=dt.date(2050, 1, 1),
        end_date=dt.date(2050, 1, 1),
    )
    res = source.get_projections(req)
    assert res.data is None
    assert res.source.state == "unavailable"
    assert res.source.missing_reason == expected_reason
    assert res.source.detail
    assert "PLACEHOLDER_SECRET_BODY" not in res.source.detail
    assert stored_files(cache_dir) == []


@pytest.mark.parametrize(
    ("kind", "handler", "expected_reason"),
    [
        (
            "http-503",
            _status(503, text="PLACEHOLDER_SECRET_BODY"),
            "SOURCE_UNAVAILABLE",
        ),
        (
            "empty-subsets",
            _status(200, json={"forecast_system": "GEOS-S2S-3", "subsets": []}),
            "NO_COVERAGE",
        ),
        (
            "coverage-false",
            _status(
                200,
                json={
                    "forecast_system": "GEOS-S2S-3",
                    "coverage": False,
                    "subsets": [],
                },
            ),
            "NO_COVERAGE",
        ),
        (
            "missing-lead-month",
            _status(
                200,
                json={
                    "forecast_system": "GEOS-S2S-3",
                    "subsets": [
                        {
                            "parameter": "pr",
                            "lead_month": 1,
                            "tercile_probabilities": {
                                "below_normal": 0.2,
                                "near_normal": 0.3,
                                "above_normal": 0.5,
                            },
                            "member_values": [1.0, 2.0, 3.0, 4.0],
                        }
                    ],
                },
            ),
            "MISSING_INPUT",
        ),
        (
            "missing-tercile-key",
            _status(
                200,
                json={
                    "forecast_system": "GEOS-S2S-3",
                    "subsets": [
                        {
                            "parameter": "pr",
                            "lead_month": lead,
                            "tercile_probabilities": {
                                "below_normal": 0.5,
                                "near_normal": 0.5,
                            },
                            "member_values": [1.0, 2.0, 3.0, 4.0],
                        }
                        for lead in (1, 2, 3)
                    ],
                },
            ),
            "MISSING_INPUT",
        ),
        (
            "truncated-members",
            _status(
                200,
                json={
                    "forecast_system": "GEOS-S2S-3",
                    "subsets": [
                        {
                            "parameter": "pr",
                            "lead_month": lead,
                            "tercile_probabilities": {
                                "below_normal": 0.2,
                                "near_normal": 0.3,
                                "above_normal": 0.5,
                            },
                            "member_values": [1.0, 2.0],
                        }
                        for lead in (1, 2, 3)
                    ],
                },
            ),
            "MISSING_INPUT",
        ),
        (
            "terciles-do-not-sum-to-one",
            _status(
                200,
                json={
                    "forecast_system": "GEOS-S2S-3",
                    "subsets": [
                        {
                            "parameter": "pr",
                            "lead_month": lead,
                            "tercile_probabilities": {
                                "below_normal": 0.5,
                                "near_normal": 0.5,
                                "above_normal": 0.5,
                            },
                            "member_values": [1.0, 2.0, 3.0, 4.0],
                        }
                        for lead in (1, 2, 3)
                    ],
                },
            ),
            "SOURCE_UNAVAILABLE",
        ),
    ],
)
def test_seasonal_failures_are_typed_and_never_echo_body(
    tmp_path, kind, handler, expected_reason
):
    source, _, cache_dir = _build_seasonal(tmp_path, handler)
    req = SeasonalForecastRequest(
        case_id="case_s_err",
        field_id="field_s_err",
        latitude=1.0,
        longitude=2.0,
        init_date=dt.date(2026, 11, 1),
    )
    res = source.get_forecast_subset(req)
    assert res.data is None
    assert res.source.state == "unavailable"
    assert res.source.missing_reason == expected_reason
    assert res.source.detail
    assert "PLACEHOLDER_SECRET_BODY" not in res.source.detail
    assert stored_files(cache_dir) == []


def test_impossible_requests_fail_before_http_call(tmp_path):
    source, service, _ = _build_nex(tmp_path, answer_with({}))
    with pytest.raises(ValueError):
        source.get_projections(
            FutureClimateRequest(
                case_id="c",
                field_id="f",
                latitude=95.0,
                longitude=0.0,
                start_date=dt.date(2050, 1, 1),
                end_date=dt.date(2050, 1, 2),
            )
        )
    with pytest.raises(ValueError, match="unconfigured"):
        source.get_projections(
            FutureClimateRequest(
                case_id="c",
                field_id="f",
                latitude=0.0,
                longitude=0.0,
                start_date=dt.date(2050, 1, 1),
                end_date=dt.date(2050, 1, 2),
                scenarios=("unknown_ssp",),
            )
        )
    assert service.requests == []


# --- 5. Rev13 strict ensemble comparison & normative erosion guard ------------


def _make_run(
    *,
    ensemble_name: str,
    model_id: str,
    scenario: str,
    values: list[float | None],
    quantity: str = "air_temperature_max_2m",
    unit: str = "degC",
    provenance: str = "SIMULATED",
) -> EnsembleModelRun:
    start = dt.date(2050, 1, 1)
    days = []
    for idx, val in enumerate(values):
        day = start + dt.timedelta(days=idx)
        if val is None:
            days.append(
                DailyValue(
                    date=day,
                    value=None,
                    missing=Missing(reason="NO_COVERAGE", detail="placeholder missing"),
                )
            )
        else:
            days.append(DailyValue(date=day, value=val))
    return EnsembleModelRun(
        ensemble_name=ensemble_name,
        model_id=model_id,
        scenario=scenario,
        quantity=quantity,
        unit=unit,
        provenance=provenance,
        source=ensemble_name.lower(),
        range_missing=Missing(reason="NOT_AVAILABLE", detail="no uncertainty range"),
        time_zone="UTC",
        start_date=start,
        end_date=start + dt.timedelta(days=len(values) - 1),
        days=days,
        valid_for_normative_erosion=False,
    )


def test_compare_climate_ensembles_reports_strictly_separately_and_never_averages():
    nex_runs = [
        _make_run(
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            model_id="N1",
            scenario="SSP5-8.5",
            values=[30.0, 32.0],
        ),  # mean 31.0
        _make_run(
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            model_id="N2",
            scenario="SSP5-8.5",
            values=[33.0, 35.0],
        ),  # mean 34.0
        _make_run(
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            model_id="N3",
            scenario="SSP5-8.5",
            values=[35.0, 37.0],
        ),  # mean 36.0
    ]
    isimip_runs = [
        _make_run(
            ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
            model_id="I1",
            scenario="SSP5-8.5",
            values=[28.0, 30.0],
            provenance="DERIVED",
        ),  # mean 29.0
        _make_run(
            ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
            model_id="I2",
            scenario="SSP5-8.5",
            values=[30.0, 32.0],
            provenance="DERIVED",
        ),  # mean 31.0
        _make_run(
            ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
            model_id="I3",
            scenario="SSP5-8.5",
            values=[32.0, 34.0],
            provenance="DERIVED",
        ),  # mean 33.0
        _make_run(
            ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
            model_id="I4",
            scenario="SSP5-8.5",
            values=[36.0, 38.0],
            provenance="DERIVED",
        ),  # mean 37.0
        _make_run(
            ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
            model_id="I5",
            scenario="SSP5-8.5",
            values=[38.0, 40.0],
            provenance="DERIVED",
        ),  # mean 39.0
    ]
    criterion = EnsembleCriterion(
        name="heat_threshold_mean",
        quantity="air_temperature_max_2m",
        unit="degC",
        scenario="SSP5-8.5",
        statistic="mean",
        comparator=">=",
        threshold=33.0,
    )

    comp = compare_climate_ensembles(nex_runs, isimip_runs, criterion)
    assert isinstance(comp, EnsembleComparison)
    assert comp.cross_ensemble_averaged is False
    assert comp.valid_for_normative_erosion is False
    assert comp.provenance == "SIMULATED"  # C4.3: any SIMULATED input -> SIMULATED

    # NEX-GDDP-CMIP6 reported strictly separately
    assert comp.nex_gddp_cmip6.ensemble_name == NEX_GDDP_ENSEMBLE_NAME
    assert comp.nex_gddp_cmip6.agreeing_models == 2
    assert comp.nex_gddp_cmip6.total_models == 3
    assert comp.nex_gddp_cmip6.min_val == pytest.approx(31.0)
    assert comp.nex_gddp_cmip6.max_val == pytest.approx(36.0)
    assert comp.nex_gddp_cmip6.valid_for_normative_erosion is False

    # ISIMIP3b reported strictly separately
    assert comp.isimip3b.ensemble_name == ISIMIP3B_ENSEMBLE_NAME
    assert comp.isimip3b.agreeing_models == 3
    assert comp.isimip3b.total_models == 5
    assert comp.isimip3b.min_val == pytest.approx(29.0)
    assert comp.isimip3b.max_val == pytest.approx(39.0)
    assert comp.isimip3b.valid_for_normative_erosion is False


def test_compare_climate_ensembles_propagates_missing_days_and_empty_coverage():
    nex_runs = [
        _make_run(
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            model_id="N1",
            scenario="SSP5-8.5",
            values=[30.0, None],
            provenance="DERIVED",
        ),
        _make_run(
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            model_id="N2",
            scenario="SSP5-8.5",
            values=[34.0, 36.0],
            provenance="DERIVED",
        ),
    ]
    criterion = EnsembleCriterion(
        name="heat_max",
        quantity="air_temperature_max_2m",
        unit="degC",
        scenario="SSP5-8.5",
        statistic="max",
        comparator=">",
        threshold=35.0,
    )
    comp = compare_climate_ensembles(nex_runs, [], criterion)
    assert comp.provenance == "DERIVED"
    assert comp.nex_gddp_cmip6.total_models == 2
    assert comp.nex_gddp_cmip6.evaluated_models == 1
    assert comp.nex_gddp_cmip6.agreeing_models == 1
    assert comp.nex_gddp_cmip6.min_val == pytest.approx(36.0)
    assert comp.nex_gddp_cmip6.max_val == pytest.approx(36.0)
    assert comp.nex_gddp_cmip6.model_outcomes[0].value is None
    assert comp.nex_gddp_cmip6.model_outcomes[0].missing is not None
    assert comp.nex_gddp_cmip6.model_outcomes[0].missing.reason == "MISSING_INPUT"

    # Empty ISIMIP3b gives NO_COVERAGE
    assert comp.isimip3b.total_models == 0
    assert comp.isimip3b.agreeing_models == 0
    assert comp.isimip3b.min_val is None
    assert comp.isimip3b.max_val is None
    assert comp.isimip3b.missing is not None
    assert comp.isimip3b.missing.reason == "NO_COVERAGE"


def test_compare_climate_ensembles_rejects_cross_contamination_and_unit_mismatch():
    nex_run = _make_run(
        ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
        model_id="N1",
        scenario="SSP5-8.5",
        values=[30.0],
    )
    isimip_run = _make_run(
        ensemble_name=ISIMIP3B_ENSEMBLE_NAME,
        model_id="I1",
        scenario="SSP5-8.5",
        values=[30.0],
    )
    criterion = EnsembleCriterion(
        name="c",
        quantity="air_temperature_max_2m",
        unit="degC",
        scenario="SSP5-8.5",
        statistic="mean",
        comparator=">",
        threshold=25.0,
    )
    with pytest.raises(ValueError, match=NEX_GDDP_ENSEMBLE_NAME):
        compare_climate_ensembles([isimip_run], [isimip_run], criterion)
    with pytest.raises(ValueError, match=ISIMIP3B_ENSEMBLE_NAME):
        compare_climate_ensembles([nex_run], [nex_run], criterion)

    bad_unit_criterion = EnsembleCriterion(
        name="c",
        quantity="air_temperature_max_2m",
        unit="K",
        scenario="SSP5-8.5",
        statistic="mean",
        comparator=">",
        threshold=300.0,
    )
    with pytest.raises(ValueError, match="unit mismatch"):
        compare_climate_ensembles([nex_run], [isimip_run], bad_unit_criterion)


def test_normative_erosion_and_cross_ensemble_averaging_cannot_be_enabled():
    run = _make_run(
        ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
        model_id="N1",
        scenario="SSP5-8.5",
        values=[30.0],
    )
    with pytest.raises(ValidationError):
        EnsembleModelRun(**run.model_dump() | {"valid_for_normative_erosion": True})

    with pytest.raises(ValidationError):
        FutureEnsemblePayload(
            case_id="c",
            field_id="f",
            ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
            valid_for_normative_erosion=True,
            runs=[],
        )

    with pytest.raises(ValidationError):
        SeasonalForecastPayload(
            case_id="c",
            field_id="f",
            forecast_system="GEOS-S2S-3",
            init_date=dt.date(2026, 11, 1),
            valid_for_normative_erosion=True,
            subsets=[],
        )

    summary = EnsembleSummary(
        ensemble_name=NEX_GDDP_ENSEMBLE_NAME,
        scenario="SSP5-8.5",
        quantity="air_temperature_max_2m",
        unit="degC",
        agreeing_models=1,
        total_models=1,
        evaluated_models=1,
        min_val=30.0,
        max_val=30.0,
        model_outcomes=[],
        valid_for_normative_erosion=False,
    )
    with pytest.raises(ValidationError):
        EnsembleComparison(
            criterion_name="c",
            quantity="air_temperature_max_2m",
            unit="degC",
            provenance="SIMULATED",
            nex_gddp_cmip6=summary,
            isimip3b=summary.model_copy(
                update={"ensemble_name": ISIMIP3B_ENSEMBLE_NAME}
            ),
            cross_ensemble_averaged=True,
            valid_for_normative_erosion=False,
        )
