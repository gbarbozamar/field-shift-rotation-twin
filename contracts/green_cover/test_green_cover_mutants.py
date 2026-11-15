"""Boundary, round-trip, and mutant-killing tests for ``contracts/green_cover/``.

All fixtures and records built here use PLACEHOLDER test inputs only.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, get_args
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.green_cover import models as gc_models
from contracts.green_cover.models import GreenCoverObservation, GreenCoverStrip
from contracts.inputs.common import ReasonCode

EXAMPLE = Path(__file__).parent / "examples" / "PLACEHOLDER_green_cover.json"


def _load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _obs(
    date: str = "2024-03-01",
    *,
    quantity_id: str = "ndvi",
    value: float | None = 0.55,
    missing: dict[str, Any] | None = None,
    unit: str = "dimensionless",
    provenance: str | None = "DERIVED",
    sensor_source: str = "Sentinel-2 (HLS)",
    cloud_fraction: float | None = 0.1,
    cloud_fraction_missing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "date": date,
        "quantity_id": quantity_id,
        "value": value,
        "unit": unit,
        "sensor_source": sensor_source,
    }
    if missing is not None:
        doc["missing"] = missing
    if provenance is not None:
        doc["provenance"] = provenance
    if cloud_fraction is not None:
        doc["cloud_fraction"] = cloud_fraction
    if cloud_fraction_missing is not None:
        doc["cloud_fraction_missing"] = cloud_fraction_missing
    return doc


def _strip(
    observations: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    obs_list = observations if observations is not None else [_obs()]
    sources = sorted({item["sensor_source"] for item in obs_list})
    doc: dict[str, Any] = {
        "contract": "green_cover_strip",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "observations": obs_list,
        "sources": sources,
    }
    doc.update(overrides)
    return doc


@contextmanager
def _weaken_model_validator(
    cls: type[BaseModel], name: str, replacement: Any
) -> Iterator[None]:
    """Temporarily replace a Pydantic model_validator and rebuild the schema."""
    decorator = cls.__pydantic_decorators__.model_validators[name]
    with patch.object(decorator, "func", replacement):
        cls.model_rebuild(force=True)
        try:
            yield
        finally:
            pass
    cls.model_rebuild(force=True)


# --- 1. C3.1 / C3.2 missingness & provenance invariants ---------------------


@pytest.mark.parametrize("reason", get_args(ReasonCode))
def test_all_c3_reason_codes_supported_on_observation_and_strip_missing(
    reason: str,
) -> None:
    missing_obj: dict[str, Any] = {"reason": reason}
    if reason == "MISSING_INPUT":
        with pytest.raises(ValidationError):
            GreenCoverStrip.model_validate(
                _strip(
                    observations=[],
                    sources=[],
                    strip_missing=copy.deepcopy(missing_obj),
                )
            )
        missing_obj["detail"] = "PLACEHOLDER_input"

    # Observation-level missing
    obs = _obs(value=None, provenance=None, missing=copy.deepcopy(missing_obj))
    loaded_obs = GreenCoverStrip.model_validate(_strip([obs]))
    assert loaded_obs.observations[0].missing is not None
    assert loaded_obs.observations[0].missing.reason == reason

    # Cloud fraction missing
    obs_cf = _obs(
        cloud_fraction=None, cloud_fraction_missing=copy.deepcopy(missing_obj)
    )
    loaded_cf = GreenCoverStrip.model_validate(_strip([obs_cf]))
    assert loaded_cf.observations[0].cloud_fraction_missing is not None
    assert loaded_cf.observations[0].cloud_fraction_missing.reason == reason

    # Strip-level missing
    loaded_strip = GreenCoverStrip.model_validate(
        _strip(observations=[], sources=[], strip_missing=copy.deepcopy(missing_obj))
    )
    assert loaded_strip.strip_missing is not None
    assert loaded_strip.strip_missing.reason == reason


@pytest.mark.parametrize("bad_reason", ["UNKNOWN", "not_available", ""])
def test_invalid_reason_codes_rejected(bad_reason: str) -> None:
    with pytest.raises(ValidationError):
        GreenCoverStrip.model_validate(
            _strip(observations=[], sources=[], strip_missing={"reason": bad_reason})
        )


def test_zero_is_valid_value_never_treated_as_missing() -> None:
    obs = _obs(value=0.0, cloud_fraction=0.0)
    loaded = GreenCoverStrip.model_validate(_strip([obs]))
    assert loaded.observations[0].value == 0.0
    assert loaded.observations[0].missing is None
    assert loaded.observations[0].cloud_fraction == 0.0


# --- 2. Strict types, finite floats, immutability, tuple round-trip ---------


@pytest.mark.parametrize(
    "bad_float", [math.nan, math.inf, -math.inf, True, False, "0.5"]
)
def test_non_finite_and_coercible_values_rejected_on_value_and_cloud_fraction(
    bad_float: Any,
) -> None:
    with pytest.raises(ValidationError):
        GreenCoverObservation.model_validate(_obs(value=bad_float))
    with pytest.raises(ValidationError):
        GreenCoverObservation.model_validate(_obs(cloud_fraction=bad_float))


@pytest.mark.parametrize(
    ("cloud_fraction", "accepted"),
    [
        (0.0, True),
        (1.0, True),
        (-1e-6, False),
        (1.0 + 1e-6, False),
    ],
)
def test_cloud_fraction_exact_boundaries(
    cloud_fraction: float, *, accepted: bool
) -> None:
    doc = _obs(cloud_fraction=cloud_fraction)
    if accepted:
        assert (
            GreenCoverObservation.model_validate(doc).cloud_fraction == cloud_fraction
        )
    else:
        with pytest.raises(ValidationError, match="between 0 and 1"):
            GreenCoverObservation.model_validate(doc)


def test_datetime_and_invalid_sequence_types_rejected() -> None:
    with pytest.raises(ValidationError):
        GreenCoverObservation.model_validate(
            {**_obs(), "date": dt.datetime(2024, 3, 1, 12, 0)}
        )
    for bad_seq in ("not-a-sequence", {"a": 1}, 123, {_obs()["sensor_source"]}):
        with pytest.raises(ValidationError):
            GreenCoverStrip.model_validate({**_strip(), "observations": bad_seq})
        with pytest.raises(ValidationError):
            GreenCoverStrip.model_validate({**_strip(), "sources": bad_seq})


def test_models_are_frozen_and_hold_tuples_across_json_roundtrip() -> None:
    loaded = GreenCoverStrip.model_validate(_load())
    assert isinstance(loaded.observations, tuple)
    assert isinstance(loaded.sources, tuple)

    with pytest.raises(ValidationError):
        loaded.case_id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        loaded.observations[0].value = 0.99  # type: ignore[misc]

    reloaded = GreenCoverStrip.model_validate_json(loaded.model_dump_json())
    assert reloaded == loaded
    assert isinstance(reloaded.observations, tuple)
    assert isinstance(reloaded.sources, tuple)

    gated = GreenCoverStrip.model_validate(
        _strip(
            observations=[],
            sources=[],
            strip_missing={
                "reason": "NOT_AVAILABLE",
                "detail": "PLACEHOLDER: gated section 8 extra",
            },
        )
    )
    gated_rt = GreenCoverStrip.model_validate_json(gated.model_dump_json())
    assert gated_rt == gated
    assert gated_rt.observations == ()
    assert gated_rt.sources == ()


# --- 3. Ordering & uniqueness tie-breakers ----------------------------------


def test_tie_breaking_order_and_non_adjacent_duplicate_rejected() -> None:
    # Same date, sorted by sensor_source then quantity_id
    valid = _strip(
        [
            _obs("2024-03-01", sensor_source="Landsat-8 (HLS)", quantity_id="ndvi"),
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="evi"),
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
        ]
    )
    GreenCoverStrip.model_validate(valid)

    # Same date, unsorted sensor_source
    bad_sensor_order = _strip(
        [
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
            _obs("2024-03-01", sensor_source="Landsat-8 (HLS)", quantity_id="ndvi"),
        ]
    )
    with pytest.raises(ValidationError, match="sorted by"):
        GreenCoverStrip.model_validate(bad_sensor_order)

    # Same date & sensor, unsorted quantity_id
    bad_qty_order = _strip(
        [
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="evi"),
        ]
    )
    with pytest.raises(ValidationError, match="sorted by"):
        GreenCoverStrip.model_validate(bad_qty_order)

    # Non-adjacent duplicate
    non_adjacent_dup = _strip(
        [
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
            _obs("2024-03-02", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
            _obs("2024-03-01", sensor_source="Sentinel-2 (HLS)", quantity_id="ndvi"),
        ]
    )
    with pytest.raises(ValidationError, match="duplicate entry"):
        GreenCoverStrip.model_validate(non_adjacent_dup)


# --- 4. Injected mutants proving every validator guard kills -----------------


def test_mutant_weakened_cloud_fraction_range_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _obs(cloud_fraction=1.25)
    with pytest.raises(ValidationError, match="between 0 and 1"):
        GreenCoverObservation.model_validate(bad)
    monkeypatch.setattr(gc_models, "CLOUD_FRACTION_RANGE", (0.0, 2.0))
    assert GreenCoverObservation.model_validate(bad).cloud_fraction == 1.25


def test_mutant_weakened_dimensionless_unit_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _obs(unit="percent")
    with pytest.raises(ValidationError, match="dimensionless"):
        GreenCoverObservation.model_validate(bad)
    monkeypatch.setattr(gc_models, "DIMENSIONLESS_UNIT", "percent")
    assert GreenCoverObservation.model_validate(bad).unit == "percent"


def test_mutant_weakened_allowed_provenances_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _obs(provenance="DECLARED")
    with pytest.raises(ValidationError, match="provenance must be one of"):
        GreenCoverObservation.model_validate(bad)
    monkeypatch.setattr(
        gc_models, "ALLOWED_PROVENANCES", ("OBSERVED", "DERIVED", "DECLARED")
    )
    assert GreenCoverObservation.model_validate(bad).provenance == "DECLARED"


def test_mutant_weakened_observation_order_check_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _strip([_obs("2024-03-10"), _obs("2024-03-01")])
    with pytest.raises(ValidationError, match="sorted by"):
        GreenCoverStrip.model_validate(bad)
    monkeypatch.setattr(
        gc_models, "_check_observation_order_and_uniqueness", lambda obs: None
    )
    loaded = GreenCoverStrip.model_validate(bad)
    assert len(loaded.observations) == 2


def test_mutant_weakened_sources_check_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _strip([_obs("2024-03-01")], sources=["MODIS"])
    with pytest.raises(ValidationError, match="distinct sensor_source"):
        GreenCoverStrip.model_validate(bad)
    monkeypatch.setattr(
        gc_models, "_check_sources_match_observations", lambda s, o: None
    )
    loaded = GreenCoverStrip.model_validate(bad)
    assert loaded.sources == ("MODIS",)


def test_mutant_weakened_model_validators_are_detected() -> None:
    neither_obs = _obs(value=None, provenance=None)
    with pytest.raises(ValidationError, match="missing part with its reason"):
        GreenCoverObservation.model_validate(neither_obs)
    with _weaken_model_validator(
        GreenCoverObservation, "_validate_observation", lambda self: self
    ):
        assert GreenCoverObservation.model_validate(neither_obs).value is None

    neither_strip = _strip(observations=[], sources=[])
    with pytest.raises(ValidationError, match="strip_missing with its reason"):
        GreenCoverStrip.model_validate(neither_strip)
    with _weaken_model_validator(GreenCoverStrip, "_validate_strip", lambda self: self):
        assert GreenCoverStrip.model_validate(neither_strip).observations == ()
