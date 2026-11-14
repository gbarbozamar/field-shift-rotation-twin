"""Tests of the seam rules that ``SourceInfo`` enforces (unit l2/engine-runner).

Run with ``uv run pytest adapters/``. Identifiers are placeholders and every
date is in the year 1900.
"""

from __future__ import annotations

import datetime as dt
from typing import get_args

import pytest

from adapters import ports
from contracts.inputs.common import ReasonCode as InputsReasonCode
from contracts.results.models import ReasonCode as ResultsReasonCode

MOMENT = dt.datetime(1900, 1, 2, 3, 4, 5, tzinfo=dt.UTC)


def info(**overrides):
    fields = {
        "id": "PLACEHOLDER_SOURCE",
        "contract": "PLACEHOLDER_CONTRACT",
        "state": "fresh",
        "retrieved_at": MOMENT,
    }
    fields.update(overrides)
    return ports.SourceInfo(**fields)


def test_a_well_built_source_info_is_accepted():
    assert info().state == "fresh"
    assert info(state="example", retrieved_at=None).retrieved_at is None
    other_zone = dt.timezone(dt.timedelta(hours=-3))
    assert info(retrieved_at=MOMENT.astimezone(other_zone)).retrieved_at == MOMENT
    unavailable = info(
        state="unavailable", retrieved_at=None, missing_reason="SOURCE_UNAVAILABLE"
    )
    assert unavailable.missing_reason == "SOURCE_UNAVAILABLE"


def test_retrieved_at_without_a_time_zone_is_rejected():
    with pytest.raises(ValueError, match="time zone"):
        info(retrieved_at=dt.datetime(1900, 1, 2, 3, 4, 5))


def test_retrieved_at_that_is_not_a_datetime_is_rejected():
    with pytest.raises(ValueError, match="time zone"):
        info(retrieved_at=dt.date(1900, 1, 2))


def test_unavailable_without_a_reason_is_rejected():
    with pytest.raises(ValueError, match="missing_reason"):
        info(state="unavailable", retrieved_at=None)


@pytest.mark.parametrize("state", ["fresh", "cached", "example"])
def test_a_reason_with_another_state_is_rejected(state):
    with pytest.raises(ValueError, match="missing_reason"):
        info(state=state, missing_reason="NOT_AVAILABLE")


def test_a_reason_outside_c3_2_is_rejected():
    with pytest.raises(ValueError, match="C3.2"):
        info(state="unavailable", retrieved_at=None, missing_reason="PLACEHOLDER")


def test_payloads_are_the_contract_models():
    from contracts.inputs import SiteClimate, SiteSoilSlope

    assert ports.ClimatePayload is SiteClimate
    assert ports.SoilSlopePayload is SiteSoilSlope


def test_the_two_reason_code_lists_of_the_contracts_agree():
    # The seam types missing_reason with the C3.2 list of contracts/inputs; the
    # API reports engine reasons with the one of contracts/results.
    assert get_args(InputsReasonCode) == get_args(ResultsReasonCode)
