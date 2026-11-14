"""Shared builders for the tests of adapters/. Placeholders only; not used at run time.

Every parameter code, quantity, unit and number here is a placeholder. Dates
are in the year 1900 so that no test can look like a real record. The URL is
under ``.invalid``, a name that never resolves; no test reaches a network.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from adapters.ports import ClimateRequest
from adapters.power import ParameterSpec, PowerSettings

PLACEHOLDER_FILL = -1.0e9  # a placeholder fill value, not the source's


def settings_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "base_url": "https://power.invalid/daily/point",
        "community": "PLACEHOLDER_community",
        "parameters": (
            ParameterSpec(
                source_parameter="PLACEHOLDER_PARAMETER_A",
                quantity="placeholder_quantity_a",
                unit="PLACEHOLDER_unit",
                provenance="OBSERVED",
            ),
            ParameterSpec(
                source_parameter="PLACEHOLDER_PARAMETER_B",
                quantity="placeholder_quantity_b",
                unit="PLACEHOLDER_unit",
                provenance="OBSERVED",
            ),
        ),
        "optional_arguments": {},
        "fill_value": PLACEHOLDER_FILL,
        "fill_reason": "NO_COVERAGE",
        "range_missing_reason": "NOT_AVAILABLE",
        "attribution": "PLACEHOLDER_attribution",
        "source_id": "placeholder_source",
        "timeout_seconds": 1.0,
    }
    fields.update(overrides)
    return fields


def make_settings(**overrides: Any) -> PowerSettings:
    return PowerSettings(**settings_fields(**overrides))


def make_request(
    start: dt.date = dt.date(1900, 1, 1),
    end: dt.date = dt.date(1900, 1, 3),
    **overrides: Any,
) -> ClimateRequest:
    fields: dict[str, Any] = {
        "case_id": "placeholder_case",
        "field_id": "placeholder_field",
        "latitude": 1.5,
        "longitude": -2.5,
        "start_date": start,
        "end_date": end,
    }
    fields.update(overrides)
    return ClimateRequest(**fields)


def source_key(day: dt.date) -> str:
    return day.strftime("%Y%m%d")


def power_document(
    series: dict[str, dict[str, Any]], fill_value: Any = PLACEHOLDER_FILL
) -> dict[str, Any]:
    """A response in the layout of the scout report (issue 15, section 1)."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-2.5, 1.5, 0.0]},
        "properties": {"parameter": series},
        "header": {"fill_value": fill_value},
        "messages": [],
        "parameters": {
            name: {"units": "PLACEHOLDER_unit", "longname": "PLACEHOLDER"}
            for name in series
        },
    }


def full_document(start: dt.date, end: dt.date) -> dict[str, Any]:
    """Both placeholder parameters with values 1.0, 2.0, 3.0, ... per day."""
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    return power_document(
        {
            "PLACEHOLDER_PARAMETER_A": {
                source_key(day): float(i + 1) for i, day in enumerate(days)
            },
            "PLACEHOLDER_PARAMETER_B": {
                source_key(day): float(i + 1) for i, day in enumerate(days)
            },
        }
    )
