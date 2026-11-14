"""Raw NASA POWER daily point response -> "Site data: climate" document.

Pure function: no I/O, no clock. The layout read here is the JSON response
shape documented in the scout report (issue 15, section 1):
``properties.parameter.<NAME>.<YYYYMMDD>: <value>`` and
``header.fill_value``.

No unit conversion. The unit written is the configured one; whether the
source's unit equals it is a person's check (README, OPEN).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adapters.ports import ClimateRequest
    from adapters.power import PowerSettings

CONTRACT = "site_data_climate"
TIME_ZONE = "UTC"  # C6.2: series from this adapter are UTC

_SOURCE_DATE = re.compile(r"\d{8}")

# English detail of a missing day. Text for developers, not a claim.
DETAIL_FILL_VALUE = "the source gave its fill value for this day"
DETAIL_NOT_IN_RESPONSE = "the response holds no value for this day"
DETAIL_NO_RANGE = "the source gives no uncertainty range for this series"


class UnusableResponse(ValueError):
    """The response does not have the expected layout. Its text never echoes the body."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_source_date(text: str) -> dt.date:
    """Strict ``YYYYMMDD``. Anything else makes the response unusable."""
    if not isinstance(text, str) or not _SOURCE_DATE.fullmatch(text):
        raise UnusableResponse("a date key is not written YYYYMMDD")
    try:
        return dt.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        raise UnusableResponse("a date key is not a calendar date") from None


def _days(start: dt.date, end: dt.date) -> list[dt.date]:
    count = (end - start).days + 1
    return [start + dt.timedelta(days=offset) for offset in range(count)]


def _read_values(raw: Any, source_parameter: str) -> dict[dt.date, float]:
    properties = raw.get("properties")
    if not isinstance(properties, dict):
        raise UnusableResponse("the response has no 'properties' object")
    parameter = properties.get("parameter")
    if not isinstance(parameter, dict):
        raise UnusableResponse("the response has no 'properties.parameter' object")
    series = parameter.get(source_parameter)
    if not isinstance(series, dict):
        raise UnusableResponse(
            f"the response has no series for the configured parameter {source_parameter!r}"
        )
    values: dict[dt.date, float] = {}
    for key, value in series.items():
        day = _parse_source_date(key)
        if not _is_number(value) or not math.isfinite(value):
            raise UnusableResponse(
                f"a value of the configured parameter {source_parameter!r} is not a finite number"
            )
        values[day] = float(value)
    return values


def _check_declared_fill_value(raw: Any, fill_value: float) -> None:
    header = raw.get("header")
    if header is None:
        return
    if not isinstance(header, dict):
        raise UnusableResponse("the response 'header' is not an object")
    if "fill_value" not in header:
        return
    declared = header["fill_value"]
    if not _is_number(declared) or declared != fill_value:
        raise UnusableResponse(
            "the response declares a fill value other than the configured one"
        )


def to_site_climate(
    raw: Any, request: ClimateRequest, settings: PowerSettings
) -> dict[str, Any]:
    """Map a parsed response to a JSON-ready document in the shape of ``SiteClimate``.

    Every ``missing`` and ``range_missing`` part written carries a non-empty
    English ``detail``, so that every reason code of C3.2 loads (C3.2 asks a
    detail for ``MISSING_INPUT``).

    Raises ``UnusableResponse`` when the response lacks the expected layout or
    holds a date that cannot be parsed. Every day from ``start_date`` to
    ``end_date`` appears once, in order; a fill value or an absent day becomes
    a missing value with its reason, never zero.
    """
    if not isinstance(raw, dict):
        raise UnusableResponse("the response is not a JSON object")
    _check_declared_fill_value(raw, settings.fill_value)

    days = _days(request.start_date, request.end_date)
    daily_series: list[dict[str, Any]] = []
    for spec in settings.parameters:
        values = _read_values(raw, spec.source_parameter)
        items: list[dict[str, Any]] = []
        for day in days:
            value = values.get(day)
            if value is None:
                detail = DETAIL_NOT_IN_RESPONSE
            elif value == settings.fill_value:
                detail = DETAIL_FILL_VALUE
            else:
                items.append({"date": day.isoformat(), "value": value})
                continue
            items.append(
                {
                    "date": day.isoformat(),
                    "value": None,
                    "missing": {"reason": settings.fill_reason, "detail": detail},
                }
            )

        series: dict[str, Any] = {"quantity": spec.quantity, "unit": spec.unit}
        if any(item["value"] is not None for item in items):
            # C2.2, C4.1: only a series with at least one number carries these.
            series["provenance"] = spec.provenance
            series["source"] = settings.source_id
            series["range_missing"] = {
                "reason": settings.range_missing_reason,
                "detail": DETAIL_NO_RANGE,
            }
        series.update(
            {
                "time_zone": TIME_ZONE,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "days": items,
            }
        )
        daily_series.append(series)

    return {
        "contract": CONTRACT,
        "example_data": False,
        "case_id": request.case_id,
        "field_id": request.field_id,
        "daily_series": daily_series,
        "monthly_series": [],
    }
