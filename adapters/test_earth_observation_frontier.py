"""Acceptance tests for Frontier EO adapters and proposal envelopes (Unit F-24).

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).
Zero live network calls: every HTTP test uses ``httpx.MockTransport``.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from pydantic import ValidationError

from adapters.earth_observation_frontier import (
    EMIT_SCENE_ROLE,
    EMIT_SCOPE_TAG,
    NISAR_SME2_MATURITY_PROVISIONAL,
    SPL2SMAP_S_GUARD_CODE,
    EcostressEtSource,
    EcostressSettings,
    EmitFractionalCoverSource,
    EoRequest,
    FoundationCropProposal,
    FoundationCropProposalSource,
    FrontierSourceSettings,
    GreennessBaselineComparison,
    NisarSme2Source,
    Spl2SmapSSource,
)

FIXED_NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.UTC)


def _settings(**overrides) -> FrontierSourceSettings:
    fields = {
        "base_url": "https://eo-frontier.invalid/v1/query",
        "source_id": "frontier_eo_placeholder",
        "attribution": "PLACEHOLDER_ATTRIBUTION",
        "timeout_seconds": 5.0,
    }
    fields.update(overrides)
    return FrontierSourceSettings(**fields)


def _ecostress_settings(**overrides) -> EcostressSettings:
    fields = {
        "base_url": "https://eo-frontier.invalid/v1/ecostress",
        "source_id": "frontier_ecostress_placeholder",
        "attribution": "PLACEHOLDER_ATTRIBUTION",
        "timeout_seconds": 5.0,
        "accepted_qa_flags": ("BEST", "GOOD"),
    }
    fields.update(overrides)
    return EcostressSettings(**fields)


def _request(**overrides) -> EoRequest:
    fields = {
        "case_id": "case_001",
        "field_id": "field_a",
        "latitude": -34.5,
        "longitude": -56.2,
        "start_date": dt.date(2026, 5, 1),
        "end_date": dt.date(2026, 6, 15),
        "query_mode": "operational",
    }
    fields.update(overrides)
    return EoRequest(**fields)


class RecordingHandler:
    """MockTransport callback that records every outgoing HTTP request."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def _mock_client(handler) -> tuple[httpx.Client, RecordingHandler]:
    recorder = RecordingHandler(handler)
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    return client, recorder


# ---------------------------------------------------------------------------
# Constructor & settings guards (no-default httpx.Client)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_cls", "settings_factory"),
    [
        (Spl2SmapSSource, _settings),
        (EcostressEtSource, _ecostress_settings),
        (NisarSme2Source, _settings),
        (EmitFractionalCoverSource, _settings),
        (FoundationCropProposalSource, _settings),
    ],
)
def test_adapters_require_explicit_httpx_client(source_cls, settings_factory):
    settings = settings_factory()
    with pytest.raises(TypeError):
        source_cls(settings)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        source_cls(settings, None)  # type: ignore[arg-type]


def test_settings_reject_insecure_or_invalid_values():
    with pytest.raises(ValueError, match="https"):
        _settings(base_url="http://eo-frontier.invalid/v1")
    with pytest.raises(ValueError, match="greater than zero"):
        _settings(timeout_seconds=0.0)
    with pytest.raises(ValueError, match="accepted_qa_flags"):
        _ecostress_settings(accepted_qa_flags=())


def test_source_exposes_readonly_identity_without_network_call():
    client, recorder = _mock_client(lambda _req: httpx.Response(200, json={}))
    source = Spl2SmapSSource(_settings(source_id="smap_sentinel_3km"), client)
    assert source.source_id == "smap_sentinel_3km"
    assert source.contract == "frontier_eo_spl2smap_s_v003"
    assert recorder.requests == []


# ---------------------------------------------------------------------------
# 1. Spl2SmapSSource (SPL2SMAP_S v003, 3 km)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        (dt.date(2026, 6, 20), dt.date(2026, 7, 1)),
        (dt.date(2026, 7, 1), dt.date(2026, 7, 15)),
        (dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
    ],
)
def test_spl2smap_s_operational_cutoff_2026_07_01_blocks_without_network(
    start_date, end_date
):
    client, recorder = _mock_client(
        lambda _req: httpx.Response(
            200,
            json={
                "metadata": {"temporal_extent": "2015-04-01 to present"},
                "records": [
                    {
                        "date": "2026-07-05",
                        "soil_moisture": 0.25,
                        "unit": "m3 m-3",
                    }
                ],
            },
        )
    )
    source = Spl2SmapSSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(
        _request(start_date=start_date, end_date=end_date, query_mode="operational")
    )

    assert recorder.requests == []
    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NO_COVERAGE"
    assert result.missing is not None
    assert result.missing.reason == "NO_COVERAGE"
    assert result.guard_code == SPL2SMAP_S_GUARD_CODE
    assert SPL2SMAP_S_GUARD_CODE in (result.source.detail or "")


def test_spl2smap_s_rejects_to_present_metadata_and_smap_self_validation():
    payload = {
        "metadata": {
            "temporal_extent": "2015-04-01 to present",
            "validation_source": "SMAP_L2_self_validation",
            "self_validated": True,
        },
        "records": [
            {"date": "2026-05-10", "soil_moisture": 0.28, "unit": "m3 m-3"},
            {"date": "2026-06-25", "soil_moisture": 0.22, "unit": "m3 m-3"},
        ],
    }
    client, recorder = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = Spl2SmapSSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(
        _request(
            start_date=dt.date(2026, 5, 1),
            end_date=dt.date(2026, 6, 30),
            query_mode="archive",
        )
    )

    assert len(recorder.requests) == 1
    assert result.source.state == "fresh"
    assert result.data is not None
    assert result.data.product == "SPL2SMAP_S"
    assert result.data.version == "v003"
    assert result.data.spatial_resolution_km == 3.0
    assert result.data.continuous_operational_proof is False
    assert result.data.to_present_metadata_rejected is True
    assert result.data.smap_self_validation_allowed is False
    assert result.data.smap_self_validation_rejected is True
    assert result.data.requires_independent_local_validation is True
    assert result.data.local_validation_status == "UNVALIDATED"
    assert len(result.data.observations) == 2


def test_spl2smap_s_archive_rejects_records_on_or_after_2026_07_01():
    payload = {
        "metadata": {"temporal_extent": "2015-04-01 to present"},
        "records": [
            {"date": "2026-06-30", "soil_moisture": 0.21, "unit": "m3 m-3"},
            {"date": "2026-07-01", "soil_moisture": 0.19, "unit": "m3 m-3"},
        ],
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = Spl2SmapSSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(
        _request(
            start_date=dt.date(2026, 6, 1),
            end_date=dt.date(2026, 7, 10),
            query_mode="archive",
        )
    )

    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "NO_COVERAGE"
    assert result.guard_code == SPL2SMAP_S_GUARD_CODE


# ---------------------------------------------------------------------------
# 2. EcostressEtSource (ECOSTRESS, 70 m QA-filtered ET)
# ---------------------------------------------------------------------------


def test_ecostress_filters_out_low_qa_and_cloudy_observations():
    payload = {
        "observations": [
            {
                "date": "2026-05-05",
                "et_value": 4.2,
                "unit": "mm day-1",
                "qa_flag": "BEST",
                "qa_passed": True,
                "cloud_free": True,
                "overpass_utc": "2026-05-05T14:20:00Z",
            },
            {
                "date": "2026-05-09",
                "et_value": 3.1,
                "unit": "mm day-1",
                "qa_flag": "BEST",
                "qa_passed": True,
                "cloud_free": False,
            },
            {
                "date": "2026-05-12",
                "et_value": 5.0,
                "unit": "mm day-1",
                "qa_flag": "SUSPECT",
                "qa_passed": True,
                "cloud_free": True,
            },
            {
                "date": "2026-05-16",
                "et_value": 2.9,
                "unit": "mm day-1",
                "qa_flag": "GOOD",
                "qa_passed": False,
                "cloud_free": True,
            },
            {
                "date": "2026-05-20",
                "et_value": 3.8,
                "unit": "mm day-1",
                "qa_flag": "GOOD",
                "qa_passed": True,
                "cloud_free": True,
            },
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = EcostressEtSource(_ecostress_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.source.state == "fresh"
    assert result.data is not None
    assert result.data.spatial_resolution_m == 70
    assert result.data.observation_cadence == "INTERMITTENT_OVERPASS"
    assert result.data.total_raw_count == 5
    assert result.data.rejected_qa_count == 3
    assert [obs.date for obs in result.data.observations] == [
        dt.date(2026, 5, 5),
        dt.date(2026, 5, 20),
    ]


def test_ecostress_returns_control_failed_when_all_observations_fail_qa():
    payload = {
        "observations": [
            {
                "date": "2026-05-05",
                "et_value": 4.2,
                "unit": "mm day-1",
                "qa_flag": "POOR",
                "qa_passed": False,
            }
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = EcostressEtSource(_ecostress_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "CONTROL_FAILED"


# ---------------------------------------------------------------------------
# 3. NisarSme2Source (NISAR SME2, 200 m soil moisture)
# ---------------------------------------------------------------------------


def test_nisar_sme2_tags_june_2026_onward_as_provisional_pre_2027():
    payload = {
        "records": [
            {
                "date": "2026-05-28",
                "soil_moisture": 0.24,
                "unit": "m3 m-3",
                "product_maturity": "VALIDATED",
            },
            {
                "date": "2026-06-01",
                "soil_moisture": 0.27,
                "unit": "m3 m-3",
                "product_maturity": "OPERATIONAL",
            },
            {
                "date": "2026-09-10",
                "soil_moisture": 0.31,
                "unit": "m3 m-3",
                "product_maturity": "VALIDATED",
            },
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = NisarSme2Source(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(
        _request(start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 9, 30))
    )

    assert result.source.state == "fresh"
    assert result.data is not None
    assert result.data.spatial_resolution_m == 200
    obs_by_date = {obs.date: obs for obs in result.data.observations}

    # Pre-June 2026 cannot be marked VALIDATED either.
    pre = obs_by_date[dt.date(2026, 5, 28)]
    assert pre.product_maturity == "PRE_OPERATIONAL_COMMISSIONING"
    assert pre.requires_independent_local_validation is True
    assert pre.local_validation_status == "UNVALIDATED"

    # June 2026 onward strictly forced to PROVISIONAL_PRE_2027.
    for post_date in (dt.date(2026, 6, 1), dt.date(2026, 9, 10)):
        rec = obs_by_date[post_date]
        assert rec.product_maturity == NISAR_SME2_MATURITY_PROVISIONAL
        assert rec.requires_independent_local_validation is True
        assert rec.local_validation_status == "UNVALIDATED"


# ---------------------------------------------------------------------------
# 4. EmitFractionalCoverSource (EMIT, 60 m PV/NPV/bare)
# ---------------------------------------------------------------------------


def test_emit_forces_sparse_opportunistic_calibration_only_role():
    payload = {
        "scenes": [
            {
                "scene_id": "EMIT_L2B_001",
                "date": "2026-05-14",
                "pv_fraction": 0.45,
                "npv_fraction": 0.30,
                "bare_fraction": 0.25,
                "role": "FARM_MONITORING",
                "not_farm_monitoring": False,
            }
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = EmitFractionalCoverSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.source.state == "fresh"
    assert result.data is not None
    assert result.data.spatial_resolution_m == 60
    assert result.data.role == EMIT_SCENE_ROLE
    assert result.data.not_farm_monitoring is True
    scene = result.data.scenes[0]
    assert scene.role == EMIT_SCENE_ROLE
    assert scene.not_farm_monitoring is True
    assert scene.usage_scope == EMIT_SCOPE_TAG


def test_emit_rejects_out_of_range_fractions():
    payload = {
        "scenes": [
            {
                "scene_id": "EMIT_L2B_BAD",
                "date": "2026-05-14",
                "pv_fraction": 1.25,
                "npv_fraction": 0.1,
                "bare_fraction": 0.0,
            }
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = EmitFractionalCoverSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "SOURCE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 5. FoundationCropProposal (Prithvi-EO-2.0, Galileo, Presto)
# ---------------------------------------------------------------------------


def _proposal(**overrides) -> FoundationCropProposal:
    fields = {
        "proposal_id": "prop_001",
        "model_name": "Prithvi-EO-2.0",
        "model_version": "2.0.0",
        "case_id": "case_001",
        "field_id": "field_a",
        "proposed_crop": "soybean",
        "proposed_sowing_date": dt.date(2026, 11, 1),
        "proposed_harvest_date": dt.date(2027, 4, 15),
        "confidence": 0.87,
        "human_confirmed": False,
        "baseline_comparison": GreennessBaselineComparison(
            baseline_name="ndvi_greenness_threshold",
            metric_name="macro_f1",
            metric_direction="higher_is_better",
            foundation_score=0.84,
            baseline_score=0.76,
        ),
        "provenance": "DERIVED",
        "source": "foundation_proposal_endpoint",
    }
    fields.update(overrides)
    return FoundationCropProposal(**fields)


@pytest.mark.parametrize("model_name", ["Prithvi-EO-2.0", "Galileo", "Presto"])
def test_foundation_proposal_supports_three_model_families_and_never_observed(
    model_name,
):
    proposal = _proposal(model_name=model_name)
    assert proposal.model_name == model_name
    assert proposal.provenance == "DERIVED"

    with pytest.raises(ValidationError, match="OBSERVED"):
        _proposal(model_name=model_name, provenance="OBSERVED")
    with pytest.raises(ValidationError, match="OBSERVED"):
        _proposal(model_name=model_name, human_confirmed=True, provenance="OBSERVED")
    with pytest.raises(ValidationError, match="DECLARED"):
        _proposal(model_name=model_name, human_confirmed=False, provenance="DECLARED")


def test_foundation_proposal_enforces_human_confirm_and_greenness_baseline_gates():
    # Gate 1: unconfirmed even when beating greenness baseline -> blocked.
    unconfirmed = _proposal(human_confirmed=False)
    decision_unconfirmed = unconfirmed.evaluate_promotion()
    assert decision_unconfirmed.promoted is False
    assert decision_unconfirmed.gate_status == "REJECTED_UNCONFIRMED"
    assert decision_unconfirmed.provenance == "DERIVED"
    assert decision_unconfirmed.missing is not None
    assert decision_unconfirmed.missing.reason == "NOT_DECLARED"

    # Gate 2a: confirmed without greenness baseline comparison -> blocked.
    no_baseline = _proposal(human_confirmed=True, baseline_comparison=None)
    decision_no_baseline = no_baseline.evaluate_promotion()
    assert decision_no_baseline.promoted is False
    assert decision_no_baseline.gate_status == "REJECTED_NO_BASELINE_BENCHMARK"
    assert decision_no_baseline.missing is not None
    assert decision_no_baseline.missing.reason == "MISSING_INPUT"

    # Gate 2b: confirmed but fails to beat greenness baseline -> blocked.
    worse_than_baseline = _proposal(
        human_confirmed=True,
        baseline_comparison=GreennessBaselineComparison(
            baseline_name="ndvi_greenness_threshold",
            metric_name="sowing_mae_days",
            metric_direction="lower_is_better",
            foundation_score=9.5,
            baseline_score=8.0,
        ),
    )
    decision_worse = worse_than_baseline.evaluate_promotion()
    assert decision_worse.promoted is False
    assert decision_worse.gate_status == "REJECTED_DID_NOT_BEAT_BASELINE"
    assert decision_worse.missing is not None
    assert decision_worse.missing.reason == "CONTROL_FAILED"

    # Both gates satisfied -> promoted as DECLARED (never OBSERVED).
    confirmed = _proposal(human_confirmed=True, confirmed_by_role="agronomist")
    decision_ok = confirmed.evaluate_promotion()
    assert decision_ok.promoted is True
    assert decision_ok.gate_status == "PROMOTED_HUMAN_CONFIRMED"
    assert decision_ok.provenance == "DECLARED"
    assert decision_ok.missing is None


def test_foundation_proposal_source_strips_upstream_preconfirmation_or_observed():
    payload = {
        "proposals": [
            {
                "proposal_id": "p1",
                "model_name": "Galileo",
                "model_version": "1.0",
                "proposed_crop": "maize",
                "proposed_sowing_date": "2026-10-10",
                "proposed_harvest_date": "2027-03-20",
                "confidence": 0.91,
                "human_confirmed": True,
                "provenance": "OBSERVED",
                "baseline_comparison": {
                    "baseline_name": "evi_greenness_index",
                    "metric_name": "macro_f1",
                    "metric_direction": "higher_is_better",
                    "foundation_score": 0.88,
                    "baseline_score": 0.79,
                },
            }
        ]
    }
    client, _ = _mock_client(lambda _req: httpx.Response(200, json=payload))
    source = FoundationCropProposalSource(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.source.state == "fresh"
    assert result.data is not None
    prop = result.data.proposals[0]
    assert prop.human_confirmed is False
    assert prop.provenance == "DERIVED"
    assert prop.evaluate_promotion().promoted is False


# ---------------------------------------------------------------------------
# Transport & malformed JSON resilience
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=req)),
        lambda req: (_ for _ in ()).throw(httpx.ConnectError("down", request=req)),
        lambda _req: httpx.Response(503, text="unavailable"),
        lambda _req: httpx.Response(200, text="<html>not json</html>"),
        lambda _req: httpx.Response(200, text='{"records": NaN}'),
    ],
)
def test_http_and_payload_failures_return_source_unavailable_without_raising(handler):
    client, _ = _mock_client(handler)
    source = NisarSme2Source(_settings(), client, now=lambda: FIXED_NOW)
    result = source.fetch(_request())

    assert result.data is None
    assert result.source.state == "unavailable"
    assert result.source.missing_reason == "SOURCE_UNAVAILABLE"
    assert result.missing is not None
    assert result.missing.reason == "SOURCE_UNAVAILABLE"
