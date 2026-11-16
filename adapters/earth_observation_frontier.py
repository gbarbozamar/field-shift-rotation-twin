"""Frontier Earth-Observation adapters and proposal envelopes.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements no-default ``httpx.Client`` adapters (tested solely with
``httpx.MockTransport``, zero live network calls) and strict
scientific-availability guards per ``27_PLAN_DE_FRONTERA.md`` §§5.2, 5.6, 11
and ``28_PLAN_INTEGRADO_REV13.md`` §3:

1. ``Spl2SmapSSource`` (``SPL2SMAP_S v003``, 3 km): hard date cutoff guard on
   ``2026-07-01`` (NSIDC paused forward processing on ``S1A`` end). Any
   non-archive/operational query on or after ``2026-07-01`` returns
   ``NO_COVERAGE`` (``forward_processing_paused_2026_07_01``) without network
   calls, never treats ``"to present"`` metadata as continuous operational
   proof, and never permits SMAP self-validation.
2. ``EcostressEtSource`` (``ECOSTRESS``, 70 m): QA-filtered evapotranspiration
   observations rejecting low-quality or cloudy scenes.
3. ``NisarSme2Source`` (``NISAR SME2``, 200 m): tags soil moisture records from
   June 2026 onward with ``product_maturity="PROVISIONAL_PRE_2027"`` requiring
   independent local validation.
4. ``EmitFractionalCoverSource`` (``EMIT``, 60 m PV/NPV/bare cover): tags every
   scene with ``role="SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY"`` and
   ``not_farm_monitoring=True``.
5. ``FoundationCropProposal`` (``Prithvi-EO-2.0``, ``Galileo``, ``Presto``
   metadata envelope) and ``FoundationCropProposalSource``: enforces the
   ``human_confirmed`` gate and benchmark comparison against a simple
   greenness-index baseline before promoting crop/date proposals, and never
   returns unconfirmed AI predictions as ``OBSERVED`` facts.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

import httpx
from pydantic import Field, FiniteFloat, ValidationError, model_validator

from adapters.ports import SourceInfo, SourceState
from contracts.inputs.common import (
    ContractModel,
    IsoDate,
    Missing,
    NonEmptyStr,
    Provenance,
    ReasonCode,
)

FRONTIER_STATUS = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"

# Guard constants (27_PLAN_DE_FRONTERA.md §§5.2, 5.6, 11; 28_PLAN_INTEGRADO_REV13.md §3).
SPL2SMAP_S_PRODUCT = "SPL2SMAP_S"
SPL2SMAP_S_VERSION = "v003"
SPL2SMAP_S_RESOLUTION_KM = 3.0
SPL2SMAP_S_PAUSE_DATE = dt.date(2026, 7, 1)
SPL2SMAP_S_GUARD_CODE = "forward_processing_paused_2026_07_01"

ECOSTRESS_PRODUCT = "ECOSTRESS"
ECOSTRESS_RESOLUTION_M = 70

NISAR_SME2_PRODUCT = "NISAR_SME2"
NISAR_SME2_RESOLUTION_M = 200
NISAR_SME2_PROVISIONAL_FROM = dt.date(2026, 6, 1)
NISAR_SME2_MATURITY_PROVISIONAL = "PROVISIONAL_PRE_2027"

EMIT_PRODUCT = "EMIT"
EMIT_RESOLUTION_M = 60
EMIT_SCENE_ROLE: Literal["SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY"] = (
    "SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY"
)
EMIT_SCOPE_TAG: Literal["not_farm_monitoring"] = "not_farm_monitoring"

FoundationModelName = Literal["Prithvi-EO-2.0", "Galileo", "Presto"]
QueryMode = Literal["operational", "archive"]
LocalValidationStatus = Literal["UNVALIDATED", "VALIDATED"]

_PROVENANCE_VALUES = ("DECLARED", "OBSERVED", "DERIVED", "SIMULATED")
_TO_PRESENT_TOKENS = ("to present", "present", "ongoing")
_SMAP_SELF_VALIDATION_TOKENS = ("smap", "spl2smap", "spl2smp", "self")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"setting {name!r} is required and must be non-empty text")
    return value


def _require_finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"setting {name!r} is required and must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"setting {name!r} must be a finite number")
    return float(value)


def _reject_json_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _parse_json(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_json_constant)


def _parse_iso_date(value: Any, field_name: str) -> dt.date:
    if isinstance(value, dt.datetime) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO YYYY-MM-DD date string")
    if len(value) != 10:
        raise ValueError(f"{field_name} must be formatted YYYY-MM-DD")
    return dt.date.fromisoformat(value)


def _format_coordinate(value: float) -> str:
    return repr(float(value))


@dataclass(frozen=True, kw_only=True)
class EoRequest:
    """Point-and-period Earth observation query for one field of one case."""

    case_id: str
    field_id: str
    latitude: float
    longitude: float
    start_date: dt.date
    end_date: dt.date
    query_mode: QueryMode = "operational"

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.field_id, "field_id")
        for name, limit in (("latitude", 90.0), ("longitude", 180.0)):
            val = getattr(self, name)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise TypeError(f"request {name} must be a finite number")
            if not math.isfinite(val) or not -limit <= val <= limit:
                raise ValueError(f"request {name} must be within -{limit}..{limit}")
        for name in ("start_date", "end_date"):
            val = getattr(self, name)
            if isinstance(val, dt.datetime) or not isinstance(val, dt.date):
                raise TypeError(f"request {name} must be a date without a time")
        if self.end_date < self.start_date:
            raise ValueError("request end_date is before start_date")
        if self.query_mode not in ("operational", "archive"):
            raise ValueError("request query_mode must be 'operational' or 'archive'")


@dataclass(frozen=True, kw_only=True)
class FrontierSourceSettings:
    """Configuration for a frontier EO adapter. No field has a default."""

    base_url: str
    source_id: str
    attribution: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        _require_text(self.base_url, "base_url")
        url = httpx.URL(self.base_url)
        if url.scheme != "https" or not url.host or url.query or url.fragment:
            raise ValueError(
                "setting 'base_url' must be an https URL without query or fragment"
            )
        _require_text(self.source_id, "source_id")
        _require_text(self.attribution, "attribution")
        timeout = _require_finite(self.timeout_seconds, "timeout_seconds")
        if timeout <= 0:
            raise ValueError("setting 'timeout_seconds' must be greater than zero")
        object.__setattr__(self, "timeout_seconds", timeout)


@dataclass(frozen=True, kw_only=True)
class EcostressSettings(FrontierSourceSettings):
    """Configuration for ``EcostressEtSource``. No field has a default."""

    accepted_qa_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            not isinstance(self.accepted_qa_flags, (tuple, list))
            or not self.accepted_qa_flags
        ):
            raise ValueError(
                "setting 'accepted_qa_flags' must be a non-empty sequence of QA flags"
            )
        cleaned = tuple(
            _require_text(flag, "accepted_qa_flags[]")
            for flag in self.accepted_qa_flags
        )
        object.__setattr__(self, "accepted_qa_flags", cleaned)


# ---------------------------------------------------------------------------
# Result payloads (Pydantic ContractModels)
# ---------------------------------------------------------------------------


class Spl2SmapSObservation(ContractModel):
    """One 3 km SPL2SMAP_S v003 soil-moisture observation."""

    date: IsoDate
    soil_moisture: FiniteFloat
    unit: NonEmptyStr
    provenance: Provenance = "DERIVED"
    local_validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"
    requires_independent_local_validation: Literal[True] = True


class Spl2SmapSCollection(ContractModel):
    """Collection of SPL2SMAP_S v003 records with strict availability guards."""

    status: NonEmptyStr = FRONTIER_STATUS
    product: Literal["SPL2SMAP_S"] = "SPL2SMAP_S"
    version: Literal["v003"] = "v003"
    spatial_resolution_km: float = SPL2SMAP_S_RESOLUTION_KM
    query_mode: QueryMode
    observations: tuple[Spl2SmapSObservation, ...]
    continuous_operational_proof: Literal[False] = False
    to_present_metadata_rejected: bool
    smap_self_validation_allowed: Literal[False] = False
    smap_self_validation_rejected: bool
    requires_independent_local_validation: Literal[True] = True
    local_validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"


class EcostressEtObservation(ContractModel):
    """One QA-filtered 70 m ECOSTRESS evapotranspiration observation."""

    date: IsoDate
    et_value: FiniteFloat = Field(ge=0.0)
    unit: NonEmptyStr
    qa_flag: NonEmptyStr
    qa_passed: Literal[True] = True
    provenance: Provenance = "DERIVED"
    overpass_utc: NonEmptyStr | None = None


class EcostressEtCollection(ContractModel):
    """QA-filtered ECOSTRESS 70 m ET observation set."""

    status: NonEmptyStr = FRONTIER_STATUS
    product: Literal["ECOSTRESS"] = "ECOSTRESS"
    spatial_resolution_m: int = ECOSTRESS_RESOLUTION_M
    observation_cadence: Literal["INTERMITTENT_OVERPASS"] = "INTERMITTENT_OVERPASS"
    observations: tuple[EcostressEtObservation, ...]
    total_raw_count: int = Field(ge=0)
    rejected_qa_count: int = Field(ge=0)


class NisarSme2Observation(ContractModel):
    """One 200 m NISAR SME2 soil-moisture observation."""

    date: IsoDate
    soil_moisture: FiniteFloat
    unit: NonEmptyStr
    product_maturity: NonEmptyStr
    requires_independent_local_validation: Literal[True] = True
    local_validation_status: Literal["UNVALIDATED"] = "UNVALIDATED"
    provenance: Provenance = "DERIVED"


class NisarSme2Collection(ContractModel):
    """Collection of NISAR SME2 200 m soil-moisture observations."""

    status: NonEmptyStr = FRONTIER_STATUS
    product: Literal["NISAR_SME2"] = "NISAR_SME2"
    spatial_resolution_m: int = NISAR_SME2_RESOLUTION_M
    provisional_from_date: IsoDate = NISAR_SME2_PROVISIONAL_FROM
    observations: tuple[NisarSme2Observation, ...]


class EmitScene(ContractModel):
    """One 60 m EMIT fractional-cover scene (calibration only, not farm monitoring)."""

    scene_id: NonEmptyStr
    date: IsoDate
    pv_fraction: FiniteFloat = Field(ge=0.0, le=1.0)
    npv_fraction: FiniteFloat = Field(ge=0.0, le=1.0)
    bare_fraction: FiniteFloat = Field(ge=0.0, le=1.0)
    role: Literal["SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY"] = EMIT_SCENE_ROLE
    not_farm_monitoring: Literal[True] = True
    usage_scope: Literal["not_farm_monitoring"] = EMIT_SCOPE_TAG
    provenance: Provenance = "DERIVED"


class EmitFractionalCoverCollection(ContractModel):
    """EMIT 60 m PV/NPV/bare scenes tagged for sparse calibration only."""

    status: NonEmptyStr = FRONTIER_STATUS
    product: Literal["EMIT"] = "EMIT"
    spatial_resolution_m: int = EMIT_RESOLUTION_M
    role: Literal["SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY"] = EMIT_SCENE_ROLE
    not_farm_monitoring: Literal[True] = True
    scenes: tuple[EmitScene, ...]


class GreennessBaselineComparison(ContractModel):
    """Benchmark comparison of a foundation model against a greenness-index baseline."""

    baseline_name: NonEmptyStr
    metric_name: NonEmptyStr
    metric_direction: Literal["higher_is_better", "lower_is_better"]
    foundation_score: FiniteFloat
    baseline_score: FiniteFloat

    @property
    def beats_baseline(self) -> bool:
        if self.metric_direction == "higher_is_better":
            return self.foundation_score > self.baseline_score
        return self.foundation_score < self.baseline_score


class ProposalPromotionDecision(ContractModel):
    """Result of gating a foundation crop/date proposal for downstream promotion."""

    status: NonEmptyStr = FRONTIER_STATUS
    promoted: bool
    gate_status: Literal[
        "PROMOTED_HUMAN_CONFIRMED",
        "REJECTED_UNCONFIRMED",
        "REJECTED_NO_BASELINE_BENCHMARK",
        "REJECTED_DID_NOT_BEAT_BASELINE",
    ]
    provenance: Literal["DECLARED", "DERIVED"]
    model_name: FoundationModelName
    proposed_crop: NonEmptyStr
    proposed_sowing_date: IsoDate | None = None
    proposed_harvest_date: IsoDate | None = None
    missing: Missing | None = None


class FoundationCropProposal(ContractModel):
    """Metadata envelope for Prithvi-EO-2.0, Galileo, or Presto crop/date proposals.

    Enforces two mandatory gates before promotion:
    1. ``human_confirmed`` must be ``True``.
    2. ``baseline_comparison`` against a simple greenness-index baseline must be
       present and outperformed by the foundation model.

    Unconfirmed AI predictions are never allowed to carry ``provenance="OBSERVED"``.
    """

    status: NonEmptyStr = FRONTIER_STATUS
    proposal_id: NonEmptyStr
    model_name: FoundationModelName
    model_version: NonEmptyStr
    case_id: NonEmptyStr
    field_id: NonEmptyStr
    proposed_crop: NonEmptyStr
    proposed_sowing_date: IsoDate | None = None
    proposed_harvest_date: IsoDate | None = None
    confidence: FiniteFloat = Field(ge=0.0, le=1.0)
    human_confirmed: bool = False
    confirmed_by_role: NonEmptyStr | None = None
    baseline_comparison: GreennessBaselineComparison | None = None
    provenance: Provenance = "DERIVED"
    source: NonEmptyStr

    @model_validator(mode="after")
    def _enforce_scientific_gates(self) -> FoundationCropProposal:
        if self.provenance == "OBSERVED":
            raise ValueError(
                "foundation model crop/date proposals are never OBSERVED facts"
            )
        if self.provenance == "DECLARED" and not self.human_confirmed:
            raise ValueError(
                "unconfirmed foundation model proposal cannot carry provenance DECLARED"
            )
        if (
            self.proposed_sowing_date is not None
            and self.proposed_harvest_date is not None
            and self.proposed_harvest_date < self.proposed_sowing_date
        ):
            raise ValueError(
                "proposed_harvest_date cannot be earlier than proposed_sowing_date"
            )
        return self

    def evaluate_promotion(self) -> ProposalPromotionDecision:
        """Apply human-confirmation and greenness-baseline gates before promotion."""
        if not self.human_confirmed:
            return ProposalPromotionDecision(
                promoted=False,
                gate_status="REJECTED_UNCONFIRMED",
                provenance="DERIVED",
                model_name=self.model_name,
                proposed_crop=self.proposed_crop,
                proposed_sowing_date=self.proposed_sowing_date,
                proposed_harvest_date=self.proposed_harvest_date,
                missing=Missing(
                    reason="NOT_DECLARED",
                    detail=(
                        "human_confirmed is False: unconfirmed AI proposal cannot be "
                        "promoted or treated as OBSERVED"
                    ),
                ),
            )
        if self.baseline_comparison is None:
            return ProposalPromotionDecision(
                promoted=False,
                gate_status="REJECTED_NO_BASELINE_BENCHMARK",
                provenance="DERIVED",
                model_name=self.model_name,
                proposed_crop=self.proposed_crop,
                proposed_sowing_date=self.proposed_sowing_date,
                proposed_harvest_date=self.proposed_harvest_date,
                missing=Missing(
                    reason="MISSING_INPUT",
                    detail=(
                        "greenness_index_baseline benchmark comparison is required "
                        "before promoting proposal"
                    ),
                ),
            )
        if not self.baseline_comparison.beats_baseline:
            return ProposalPromotionDecision(
                promoted=False,
                gate_status="REJECTED_DID_NOT_BEAT_BASELINE",
                provenance="DERIVED",
                model_name=self.model_name,
                proposed_crop=self.proposed_crop,
                proposed_sowing_date=self.proposed_sowing_date,
                proposed_harvest_date=self.proposed_harvest_date,
                missing=Missing(
                    reason="CONTROL_FAILED",
                    detail=(
                        "foundation model proposal did not outperform the simple "
                        "greenness-index baseline"
                    ),
                ),
            )
        return ProposalPromotionDecision(
            promoted=True,
            gate_status="PROMOTED_HUMAN_CONFIRMED",
            provenance="DECLARED",
            model_name=self.model_name,
            proposed_crop=self.proposed_crop,
            proposed_sowing_date=self.proposed_sowing_date,
            proposed_harvest_date=self.proposed_harvest_date,
            missing=None,
        )


class FoundationProposalCollection(ContractModel):
    """Collection of foundation-model crop/date proposal envelopes."""

    status: NonEmptyStr = FRONTIER_STATUS
    proposals: tuple[FoundationCropProposal, ...]


@dataclass(frozen=True)
class EoAdapterResult:
    """Uniform result envelope returned by frontier EO adapters."""

    data: Any | None
    source: SourceInfo
    missing: Missing | None = None
    guard_code: str | None = None


# ---------------------------------------------------------------------------
# Shared HTTP adapter base (no-default httpx.Client)
# ---------------------------------------------------------------------------


class _BaseHttpEoAdapter:
    """Shared HTTP fetch, query construction, and error-to-Result mapping."""

    _contract: str = ""
    _settings_cls: type[FrontierSourceSettings] = FrontierSourceSettings

    def __init__(
        self,
        settings: FrontierSourceSettings,
        client: httpx.Client,
        *,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not isinstance(settings, self._settings_cls):
            raise TypeError(
                f"{type(self).__name__} requires {self._settings_cls.__name__}"
            )
        if not isinstance(client, httpx.Client):
            raise TypeError(f"{type(self).__name__} requires an httpx.Client")
        self._settings = settings
        self._client = client
        self._now = now

    @property
    def source_id(self) -> str:
        return self._settings.source_id

    @property
    def contract(self) -> str:
        return self._contract

    def _retrieved_now(self) -> dt.datetime:
        moment = self._now()
        if not isinstance(moment, dt.datetime) or moment.utcoffset() is None:
            raise ValueError("the clock must return a timezone-aware datetime")
        return moment.astimezone(dt.UTC)

    def _build_query(self, request: EoRequest) -> dict[str, str]:
        if not isinstance(request, EoRequest):
            raise TypeError("fetch takes an EoRequest")
        return {
            "case_id": request.case_id,
            "field_id": request.field_id,
            "latitude": _format_coordinate(request.latitude),
            "longitude": _format_coordinate(request.longitude),
            "start": request.start_date.isoformat(),
            "end": request.end_date.isoformat(),
            "query_mode": request.query_mode,
        }

    def _info(
        self,
        query: Mapping[str, str],
        state: SourceState,
        *,
        retrieved_at: dt.datetime | None = None,
        missing_reason: ReasonCode | None = None,
        detail: str | None = None,
    ) -> SourceInfo:
        return SourceInfo(
            id=self._settings.source_id,
            contract=self._contract,
            state=state,
            retrieved_at=retrieved_at,
            time_zone="UTC",
            request=MappingProxyType(dict(query)),
            attribution=self._settings.attribution,
            missing_reason=missing_reason,
            detail=detail,
        )

    def _unavailable(
        self,
        query: Mapping[str, str],
        reason: ReasonCode,
        detail: str,
        *,
        guard_code: str | None = None,
    ) -> EoAdapterResult:
        return EoAdapterResult(
            data=None,
            source=self._info(
                query,
                "unavailable",
                missing_reason=reason,
                detail=detail,
            ),
            missing=Missing(reason=reason, detail=detail),
            guard_code=guard_code,
        )

    def _fetch_json(
        self, query: Mapping[str, str]
    ) -> tuple[Any, dt.datetime] | EoAdapterResult:
        try:
            response = self._client.get(
                self._settings.base_url,
                params=list(query.items()),
                timeout=self._settings.timeout_seconds,
            )
        except httpx.TimeoutException:
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "the source did not answer in time"
            )
        except httpx.TransportError:
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "the source could not be reached"
            )
        except httpx.HTTPError:
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "the request to the source failed"
            )

        retrieved_at = self._retrieved_now()
        if not response.is_success:
            return self._unavailable(
                query,
                "SOURCE_UNAVAILABLE",
                f"the source answered with HTTP status {response.status_code}",
            )
        try:
            raw = _parse_json(response.text)
        except ValueError:
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "the response body is not valid JSON"
            )
        if not isinstance(raw, dict):
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "the response JSON root must be an object"
            )
        return raw, retrieved_at


# ---------------------------------------------------------------------------
# 1. Spl2SmapSSource (SPL2SMAP_S v003, 3 km)
# ---------------------------------------------------------------------------


def _contains_to_present_claim(metadata: Mapping[str, Any]) -> bool:
    for key in ("temporal_extent", "temporal_coverage", "coverage_end", "status"):
        val = metadata.get(key)
        if isinstance(val, str):
            lowered = val.casefold()
            if any(token in lowered for token in _TO_PRESENT_TOKENS):
                return True
    return False


def _claims_smap_self_validation(metadata: Mapping[str, Any]) -> bool:
    if metadata.get("self_validated") is True:
        return True
    if metadata.get("smap_self_validated") is True:
        return True
    val_source = metadata.get("validation_source")
    if isinstance(val_source, str):
        lowered = val_source.casefold()
        if any(token in lowered for token in _SMAP_SELF_VALIDATION_TOKENS):
            return True
    return False


class Spl2SmapSSource(_BaseHttpEoAdapter):
    """SPL2SMAP_S v003 (3 km) adapter with hard forward-processing cutoff guard.

    NSIDC paused ``SPL2SMAP_S v003`` forward processing from ``2026-07-01``
    (``S1A`` end). Any non-archive/operational query on or after ``2026-07-01``
    returns ``NO_COVERAGE`` (``forward_processing_paused_2026_07_01``) without
    contacting the network. Metadata claiming ``"to present"`` is never treated
    as continuous operational proof, and SMAP self-validation is never accepted.
    """

    _contract = "frontier_eo_spl2smap_s_v003"

    def fetch(self, request: EoRequest) -> EoAdapterResult:
        query = self._build_query(request)
        if (
            request.query_mode != "archive"
            and request.end_date >= SPL2SMAP_S_PAUSE_DATE
        ):
            detail = (
                f"{SPL2SMAP_S_GUARD_CODE}: NSIDC paused SPL2SMAP_S v003 forward "
                f"processing from {SPL2SMAP_S_PAUSE_DATE.isoformat()} (S1A end); "
                "operational queries on or after this date have NO_COVERAGE"
            )
            return self._unavailable(
                query,
                "NO_COVERAGE",
                detail,
                guard_code=SPL2SMAP_S_GUARD_CODE,
            )

        fetched = self._fetch_json(query)
        if isinstance(fetched, EoAdapterResult):
            return fetched
        raw, retrieved_at = fetched

        raw_metadata = raw.get("metadata", {})
        if not isinstance(raw_metadata, Mapping):
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "SPL2SMAP_S metadata must be a mapping"
            )
        to_present_rejected = _contains_to_present_claim(raw_metadata)
        self_val_rejected = _claims_smap_self_validation(raw_metadata)

        raw_records = raw.get("records")
        if not isinstance(raw_records, list):
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "SPL2SMAP_S response must include records"
            )

        observations: list[Spl2SmapSObservation] = []
        for item in raw_records:
            if not isinstance(item, Mapping):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "each SPL2SMAP_S record must be an object",
                )
            try:
                obs_date = _parse_iso_date(item.get("date"), "record.date")
            except (TypeError, ValueError) as exc:
                return self._unavailable(query, "SOURCE_UNAVAILABLE", str(exc))
            if obs_date >= SPL2SMAP_S_PAUSE_DATE:
                return self._unavailable(
                    query,
                    "NO_COVERAGE",
                    (
                        f"{SPL2SMAP_S_GUARD_CODE}: record dated {obs_date.isoformat()} "
                        "rejected because forward processing paused on 2026-07-01"
                    ),
                    guard_code=SPL2SMAP_S_GUARD_CODE,
                )
            try:
                observations.append(
                    Spl2SmapSObservation(
                        date=obs_date,
                        soil_moisture=item.get("soil_moisture"),
                        unit=item.get("unit"),
                    )
                )
            except (ValidationError, ValueError):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "SPL2SMAP_S record failed contract validation",
                )

        if not observations:
            return self._unavailable(
                query, "NO_COVERAGE", "no SPL2SMAP_S observations covered the request"
            )

        collection = Spl2SmapSCollection(
            query_mode=request.query_mode,
            observations=tuple(observations),
            to_present_metadata_rejected=to_present_rejected,
            smap_self_validation_rejected=self_val_rejected,
        )
        return EoAdapterResult(
            data=collection,
            source=self._info(query, "fresh", retrieved_at=retrieved_at),
        )


# ---------------------------------------------------------------------------
# 2. EcostressEtSource (ECOSTRESS, 70 m QA-filtered ET)
# ---------------------------------------------------------------------------


class EcostressEtSource(_BaseHttpEoAdapter):
    """ECOSTRESS 70 m QA-filtered evapotranspiration observations adapter."""

    _contract = "frontier_eo_ecostress_et"
    _settings_cls = EcostressSettings

    def fetch(self, request: EoRequest) -> EoAdapterResult:
        query = self._build_query(request)
        fetched = self._fetch_json(query)
        if isinstance(fetched, EoAdapterResult):
            return fetched
        raw, retrieved_at = fetched

        raw_obs = raw.get("observations")
        if not isinstance(raw_obs, list):
            return self._unavailable(
                query,
                "SOURCE_UNAVAILABLE",
                "ECOSTRESS response must include observations",
            )
        if not raw_obs:
            return self._unavailable(
                query,
                "NO_COVERAGE",
                "no ECOSTRESS overpasses found for the requested period",
            )

        settings = self._settings
        assert isinstance(settings, EcostressSettings)
        accepted_flags = frozenset(settings.accepted_qa_flags)

        accepted: list[EcostressEtObservation] = []
        rejected_count = 0
        for item in raw_obs:
            if not isinstance(item, Mapping):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "each ECOSTRESS observation must be an object",
                )
            qa_passed = item.get("qa_passed")
            qa_flag = item.get("qa_flag")
            cloud_free = item.get("cloud_free", True)
            et_val = item.get("et_value")
            if (
                qa_passed is not True
                or not isinstance(qa_flag, str)
                or qa_flag not in accepted_flags
                or cloud_free is False
                or isinstance(et_val, bool)
                or not isinstance(et_val, (int, float))
                or not math.isfinite(et_val)
            ):
                rejected_count += 1
                continue
            try:
                obs_date = _parse_iso_date(item.get("date"), "observation.date")
                accepted.append(
                    EcostressEtObservation(
                        date=obs_date,
                        et_value=float(et_val),
                        unit=item.get("unit"),
                        qa_flag=qa_flag,
                        overpass_utc=item.get("overpass_utc"),
                    )
                )
            except (ValidationError, TypeError, ValueError):
                rejected_count += 1

        if not accepted:
            return self._unavailable(
                query,
                "CONTROL_FAILED",
                "all ECOSTRESS observations failed QA filtering",
            )

        collection = EcostressEtCollection(
            observations=tuple(accepted),
            total_raw_count=len(raw_obs),
            rejected_qa_count=rejected_count,
        )
        return EoAdapterResult(
            data=collection,
            source=self._info(query, "fresh", retrieved_at=retrieved_at),
        )


# ---------------------------------------------------------------------------
# 3. NisarSme2Source (NISAR SME2, 200 m soil moisture)
# ---------------------------------------------------------------------------


class NisarSme2Source(_BaseHttpEoAdapter):
    """NISAR SME2 200 m soil-moisture adapter with provisional pre-2027 guard."""

    _contract = "frontier_eo_nisar_sme2"

    def fetch(self, request: EoRequest) -> EoAdapterResult:
        query = self._build_query(request)
        fetched = self._fetch_json(query)
        if isinstance(fetched, EoAdapterResult):
            return fetched
        raw, retrieved_at = fetched

        raw_records = raw.get("records")
        if not isinstance(raw_records, list):
            return self._unavailable(
                query,
                "SOURCE_UNAVAILABLE",
                "NISAR SME2 response must include records",
            )
        if not raw_records:
            return self._unavailable(
                query,
                "NO_COVERAGE",
                "no NISAR SME2 observations covered the request",
            )

        observations: list[NisarSme2Observation] = []
        for item in raw_records:
            if not isinstance(item, Mapping):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "each NISAR SME2 record must be an object",
                )
            try:
                obs_date = _parse_iso_date(item.get("date"), "record.date")
            except (TypeError, ValueError) as exc:
                return self._unavailable(query, "SOURCE_UNAVAILABLE", str(exc))

            if obs_date >= NISAR_SME2_PROVISIONAL_FROM:
                maturity = NISAR_SME2_MATURITY_PROVISIONAL
            else:
                upstream_maturity = item.get("product_maturity")
                maturity = (
                    upstream_maturity
                    if isinstance(upstream_maturity, str)
                    and upstream_maturity.strip()
                    and upstream_maturity.strip().upper() != "VALIDATED"
                    else "PRE_OPERATIONAL_COMMISSIONING"
                )

            try:
                observations.append(
                    NisarSme2Observation(
                        date=obs_date,
                        soil_moisture=item.get("soil_moisture"),
                        unit=item.get("unit"),
                        product_maturity=maturity,
                    )
                )
            except (ValidationError, ValueError):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "NISAR SME2 record failed contract validation",
                )

        collection = NisarSme2Collection(observations=tuple(observations))
        return EoAdapterResult(
            data=collection,
            source=self._info(query, "fresh", retrieved_at=retrieved_at),
        )


# ---------------------------------------------------------------------------
# 4. EmitFractionalCoverSource (EMIT, 60 m PV/NPV/bare)
# ---------------------------------------------------------------------------


class EmitFractionalCoverSource(_BaseHttpEoAdapter):
    """EMIT 60 m PV/NPV/bare fractional cover adapter for sparse calibration only."""

    _contract = "frontier_eo_emit_fractional_cover"

    def fetch(self, request: EoRequest) -> EoAdapterResult:
        query = self._build_query(request)
        fetched = self._fetch_json(query)
        if isinstance(fetched, EoAdapterResult):
            return fetched
        raw, retrieved_at = fetched

        raw_scenes = raw.get("scenes")
        if not isinstance(raw_scenes, list):
            return self._unavailable(
                query, "SOURCE_UNAVAILABLE", "EMIT response must include scenes"
            )
        if not raw_scenes:
            return self._unavailable(
                query, "NO_COVERAGE", "no EMIT scenes covered the request"
            )

        scenes: list[EmitScene] = []
        for item in raw_scenes:
            if not isinstance(item, Mapping):
                return self._unavailable(
                    query, "SOURCE_UNAVAILABLE", "each EMIT scene must be an object"
                )
            try:
                obs_date = _parse_iso_date(item.get("date"), "scene.date")
                scenes.append(
                    EmitScene(
                        scene_id=item.get("scene_id"),
                        date=obs_date,
                        pv_fraction=item.get("pv_fraction"),
                        npv_fraction=item.get("npv_fraction"),
                        bare_fraction=item.get("bare_fraction"),
                    )
                )
            except (ValidationError, TypeError, ValueError):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "EMIT scene failed contract validation",
                )

        collection = EmitFractionalCoverCollection(scenes=tuple(scenes))
        return EoAdapterResult(
            data=collection,
            source=self._info(query, "fresh", retrieved_at=retrieved_at),
        )


# ---------------------------------------------------------------------------
# 5. FoundationCropProposalSource (Prithvi-EO-2.0, Galileo, Presto)
# ---------------------------------------------------------------------------


class FoundationCropProposalSource(_BaseHttpEoAdapter):
    """Fetches foundation-model crop/date proposals as unconfirmed DERIVED envelopes."""

    _contract = "frontier_eo_foundation_crop_proposal"

    def fetch(self, request: EoRequest) -> EoAdapterResult:
        query = self._build_query(request)
        fetched = self._fetch_json(query)
        if isinstance(fetched, EoAdapterResult):
            return fetched
        raw, retrieved_at = fetched

        raw_proposals = raw.get("proposals")
        if not isinstance(raw_proposals, list):
            return self._unavailable(
                query,
                "SOURCE_UNAVAILABLE",
                "foundation proposal response must include proposals",
            )
        if not raw_proposals:
            return self._unavailable(
                query,
                "NO_COVERAGE",
                "no foundation crop proposals returned for the request",
            )

        proposals: list[FoundationCropProposal] = []
        for item in raw_proposals:
            if not isinstance(item, Mapping):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "each foundation proposal must be an object",
                )
            raw_baseline = item.get("baseline_comparison")
            baseline: GreennessBaselineComparison | None = None
            if raw_baseline is not None:
                if not isinstance(raw_baseline, Mapping):
                    return self._unavailable(
                        query,
                        "SOURCE_UNAVAILABLE",
                        "baseline_comparison must be an object",
                    )
                try:
                    baseline = GreennessBaselineComparison.model_validate(raw_baseline)
                except ValidationError:
                    return self._unavailable(
                        query,
                        "SOURCE_UNAVAILABLE",
                        "baseline_comparison failed contract validation",
                    )

            try:
                # Raw AI inference from an endpoint is NEVER pre-confirmed and NEVER OBSERVED.
                proposal = FoundationCropProposal(
                    proposal_id=item.get("proposal_id"),
                    model_name=item.get("model_name"),
                    model_version=item.get("model_version"),
                    case_id=request.case_id,
                    field_id=request.field_id,
                    proposed_crop=item.get("proposed_crop"),
                    proposed_sowing_date=item.get("proposed_sowing_date"),
                    proposed_harvest_date=item.get("proposed_harvest_date"),
                    confidence=item.get("confidence"),
                    human_confirmed=False,
                    baseline_comparison=baseline,
                    provenance="DERIVED",
                    source=self._settings.source_id,
                )
            except (ValidationError, ValueError):
                return self._unavailable(
                    query,
                    "SOURCE_UNAVAILABLE",
                    "foundation crop proposal failed contract validation",
                )
            proposals.append(proposal)

        collection = FoundationProposalCollection(proposals=tuple(proposals))
        return EoAdapterResult(
            data=collection,
            source=self._info(query, "fresh", retrieved_at=retrieved_at),
        )
