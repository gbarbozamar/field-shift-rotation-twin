"""Mutant-killing and boundary tests for ``contracts/inputs/``.

Covers ``common.py``, ``rotation_calendar.py``, ``site_climate.py``, and
``site_soil_slope.py`` using PLACEHOLDER test inputs only.
"""

from __future__ import annotations

import copy
import datetime as dt
import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from contracts.inputs import common, rotation_calendar, site_climate
from contracts.inputs.common import DateValue, Range, Value
from contracts.inputs.rotation_calendar import (
    AgYearStart,
    CalendarComponent,
    CalendarPeriod,
    Feasibility,
    RotationCalendar,
)
from contracts.inputs.site_climate import DailySeries, MonthlySeries, SiteClimate
from contracts.inputs.site_soil_slope import SiteSoilSlope, SoilProperty


def _val(
    value: float | None = 1.0,
    *,
    low: float | None = None,
    high: float | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    if value is None:
        item: dict[str, Any] = {
            "value": None,
            "unit": "PLACEHOLDER_unit",
            "missing": {"reason": "NO_COVERAGE", "detail": "PLACEHOLDER detail"},
        }
    else:
        item = {
            "value": value,
            "unit": "PLACEHOLDER_unit",
            "provenance": "OBSERVED",
            "source": "PLACEHOLDER source",
        }
        if low is not None and high is not None:
            item["range"] = {
                "low": low,
                "high": high,
                "kind": "PLACEHOLDER_range_kind",
            }
        else:
            item["range_missing"] = {
                "reason": "NOT_AVAILABLE",
                "detail": "PLACEHOLDER detail",
            }
    item.update(overrides)
    return item


def _date(text: str | None = "2001-01-01", **overrides: Any) -> dict[str, Any]:
    if text is None:
        item: dict[str, Any] = {
            "date": None,
            "missing": {"reason": "NOT_DECLARED"},
        }
    else:
        item = {
            "date": text,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        }
    item.update(overrides)
    return item


def _calendar(
    start_date: str = "2001-01-01",
    end_date: str = "2001-12-31",
    components: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract": "rotation_calendar",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "rotation_id": "PLACEHOLDER-rotation",
        "ag_year_start": {
            "month": 1,
            "provisional": True,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        },
        "start_date": start_date,
        "end_date": end_date,
        "feasibility": {"feasible": True, "violations": []},
        "components": components if components is not None else [],
    }
    doc.update(overrides)
    return doc


def _daily_series(
    quantity: str = "placeholder_daily",
    days: list[dict[str, Any]] | None = None,
    *,
    start_date: str = "2001-01-01",
    end_date: str = "2001-01-01",
    all_missing: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "quantity": quantity,
        "unit": "PLACEHOLDER_unit",
        "time_zone": "UTC",
        "start_date": start_date,
        "end_date": end_date,
        "days": (days if days is not None else [{"date": start_date, "value": 0.0}]),
    }
    if not all_missing:
        item.setdefault("provenance", "OBSERVED")
        item.setdefault("source", "PLACEHOLDER source")
        item.setdefault("range_missing", {"reason": "NOT_AVAILABLE"})
    item.update(overrides)
    return item


def _monthly_series(
    quantity: str = "placeholder_monthly",
    months: list[dict[str, Any]] | None = None,
    *,
    start: tuple[int, int] = (2001, 12),
    end: tuple[int, int] = (2001, 12),
    all_missing: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "quantity": quantity,
        "unit": "PLACEHOLDER_unit",
        "start": {"year": start[0], "month": start[1]},
        "end": {"year": end[0], "month": end[1]},
        "months": (
            months
            if months is not None
            else [{"year": start[0], "month": start[1], "value": 0.0}]
        ),
    }
    if not all_missing:
        item.setdefault("provenance", "OBSERVED")
        item.setdefault("source", "PLACEHOLDER source")
        item.setdefault("range_missing", {"reason": "NOT_AVAILABLE"})
    item.update(overrides)
    return item


def _climate(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract": "site_data_climate",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "point": {
            "latitude": _val(1.0),
            "longitude": _val(2.0),
            "elevation": _val(3.0),
        },
        "daily_series": [_daily_series()],
        "monthly_series": [_monthly_series()],
    }
    doc.update(overrides)
    return doc


def _soil(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract": "site_data_soil_slope",
        "example_data": True,
        "case_id": "PLACEHOLDER-case",
        "field_id": "PLACEHOLDER-field",
        "slope_length": _val(1.0),
        "slope_steepness": _val(2.0, low=1.0, high=3.0),
        "soil_properties": [
            {"quantity": "placeholder_prop_a", **_val(4.0)},
        ],
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


# --- common.py: QuantityId, Range, Value, StatedValue ------------------------


def test_quantity_id_pattern_boundaries() -> None:
    SoilProperty.model_validate({"quantity": "a", **_val(1.0)})
    SoilProperty.model_validate({"quantity": "placeholder_0_a", **_val(1.0)})
    for bad in ("", "1a", "_a", "A", "a-b", "a b"):
        with pytest.raises(ValidationError):
            SoilProperty.model_validate({"quantity": bad, **_val(1.0)})


def test_range_degenerate_and_off_by_epsilon_boundaries() -> None:
    # Degenerate point range low == value == high == 0.0 is valid
    Value.model_validate(_val(0.0, low=0.0, high=0.0))
    # Exact boundary hits low and high
    Value.model_validate(_val(1.0, low=1.0, high=3.0))
    Value.model_validate(_val(3.0, low=1.0, high=3.0))

    # Off-by-epsilon outside bounds rejected
    for bad_val in (0.999999, 3.000001):
        with pytest.raises(ValidationError, match="outside its bounds"):
            Value.model_validate(_val(bad_val, low=1.0, high=3.0))

    # low > high by tiny epsilon rejected
    with pytest.raises(ValidationError, match="low is greater than high"):
        Range.model_validate({"low": 1.000001, "high": 1.0, "kind": "PLACEHOLDER"})

    # Non-finite and boolean range bounds rejected
    for bad_bound in (math.nan, math.inf, -math.inf, True, False):
        with pytest.raises(ValidationError):
            Range.model_validate({"low": bad_bound, "high": 2.0, "kind": "PLACEHOLDER"})
        with pytest.raises(ValidationError):
            Range.model_validate({"low": 0.0, "high": bad_bound, "kind": "PLACEHOLDER"})


def test_value_missing_range_exclusivity_and_source_rules() -> None:
    # Missing value cannot carry range or range_missing
    with pytest.raises(ValidationError, match="missing value has no range"):
        Value.model_validate(
            _val(None, range={"low": 0.0, "high": 1.0, "kind": "PLACEHOLDER"})
        )
    with pytest.raises(ValidationError, match="missing value has no range"):
        Value.model_validate(_val(None, range_missing={"reason": "NOT_AVAILABLE"}))

    # Present value cannot have both or neither
    both = _val(2.0, low=1.0, high=3.0)
    both["range_missing"] = {"reason": "NOT_AVAILABLE"}
    with pytest.raises(ValidationError, match="never both"):
        Value.model_validate(both)

    neither = _val(2.0)
    del neither["range_missing"]
    with pytest.raises(ValidationError, match="range_missing"):
        Value.model_validate(neither)

    # Missing value cannot have assumption=True
    with pytest.raises(ValidationError, match="not an assumption"):
        Value.model_validate(_val(None, assumption=True))


# --- rotation_calendar.py: ag_year_start, date ordering, feasibility ---------


def test_calendar_ag_year_start_provisional_and_month_boundaries() -> None:
    # Month 1 and 12 with provisional False/True accepted
    AgYearStart.model_validate(
        {
            "month": 1,
            "provisional": False,
            "provenance": "DECLARED",
            "assumption": True,
        }
    )
    AgYearStart.model_validate(
        {
            "month": 12,
            "provisional": True,
            "provenance": "DECLARED",
            "source": "PLACEHOLDER source",
        }
    )

    # Missing month with provisional=False (not just True!) must still be rejected
    for prov in (True, False):
        with pytest.raises(ValidationError, match="no provisional mark"):
            AgYearStart.model_validate(
                {
                    "month": None,
                    "provisional": prov,
                    "missing": {"reason": "NOT_DECLARED"},
                }
            )

    # Present month without provisional rejected
    with pytest.raises(ValidationError, match="whether it is provisional"):
        AgYearStart.model_validate(
            {"month": 7, "provenance": "DECLARED", "source": "PLACEHOLDER source"}
        )

    for bad_month in (0, 13, True, False, 1.0):
        with pytest.raises(ValidationError):
            AgYearStart.model_validate(
                {
                    "month": bad_month,
                    "provisional": True,
                    "provenance": "DECLARED",
                    "source": "PLACEHOLDER source",
                }
            )


def test_calendar_and_component_and_period_inclusive_date_boundaries() -> None:
    # Single-day calendar, component, and period (start == end) is accepted
    comp = {
        "component_id": "PLACEHOLDER-c1",
        "crop_id": "PLACEHOLDER-crop",
        "start": _date("2001-05-10"),
        "end": _date("2001-05-10"),
        "periods": [
            {
                "period_type": "PLACEHOLDER-period",
                "start": _date("2001-05-10"),
                "end": _date("2001-05-10"),
            }
        ],
    }
    RotationCalendar.model_validate(
        _calendar(start_date="2001-05-10", end_date="2001-05-10", components=[comp])
    )

    # Calendar off by 1 day
    with pytest.raises(ValidationError, match="calendar: ends before it starts"):
        RotationCalendar.model_validate(
            _calendar(start_date="2001-05-10", end_date="2001-05-09")
        )

    # Period starts 1 day before component start (even when period.end is missing)
    bad_period_comp = copy.deepcopy(comp)
    bad_period_comp["periods"][0]["start"] = _date("2001-05-09")
    bad_period_comp["periods"][0]["end"] = _date(None)
    with pytest.raises(ValidationError, match="outside the dates of its component"):
        CalendarComponent.model_validate(bad_period_comp)

    # Period ends 1 day after component end
    bad_period_end = copy.deepcopy(comp)
    bad_period_end["periods"][0]["end"] = _date("2001-05-11")
    with pytest.raises(ValidationError, match="outside the dates of its component"):
        CalendarComponent.model_validate(bad_period_end)

    # Component starts 1 day before calendar start
    bad_comp_cal = _calendar(
        start_date="2001-05-10",
        end_date="2001-05-15",
        components=[
            {
                "component_id": "PLACEHOLDER-c1",
                "crop_id": "PLACEHOLDER-crop",
                "start": _date("2001-05-09"),
                "end": _date("2001-05-10"),
                "periods": [],
            }
        ],
    )
    with pytest.raises(ValidationError, match="outside the dates of the calendar"):
        RotationCalendar.model_validate(bad_comp_cal)


def test_calendar_feasibility_and_unique_component_ids() -> None:
    # Calendar-level violation with empty component_ids is accepted
    RotationCalendar.model_validate(
        _calendar(
            feasibility={
                "feasible": False,
                "violations": [{"rule": "PLACEHOLDER-rule", "component_ids": []}],
            }
        )
    )
    # Violation naming unknown component rejected
    with pytest.raises(ValidationError, match="unknown component"):
        RotationCalendar.model_validate(
            _calendar(
                feasibility={
                    "feasible": False,
                    "violations": [
                        {
                            "rule": "PLACEHOLDER-rule",
                            "component_ids": ["PLACEHOLDER-unknown"],
                        }
                    ],
                }
            )
        )
    # Non-adjacent duplicate component_id rejected
    c1 = {
        "component_id": "PLACEHOLDER-c1",
        "crop_id": "PLACEHOLDER-crop",
        "start": _date("2001-02-01"),
        "end": _date("2001-03-01"),
        "periods": [],
    }
    c2 = copy.deepcopy(c1)
    c2["component_id"] = "PLACEHOLDER-c2"
    with pytest.raises(ValidationError, match="share one component_id"):
        RotationCalendar.model_validate(_calendar(components=[c1, c2, c1]))


# --- site_climate.py: daily/monthly series, leap years, zero vs missing ------


def test_daily_series_single_day_leap_year_and_zero_value_rules() -> None:
    # Single-day series with value 0.0 requires provenance/source/range_missing
    DailySeries.model_validate(_daily_series())
    zero_no_prov = _daily_series()
    del zero_no_prov["provenance"]
    with pytest.raises(ValidationError, match="provenance label"):
        DailySeries.model_validate(zero_no_prov)

    # All-missing series forbids provenance, assumption=True, AND range_missing
    all_miss_days = [
        {"date": "2001-01-01", "value": None, "missing": {"reason": "NO_COVERAGE"}}
    ]
    DailySeries.model_validate(_daily_series(days=all_miss_days, all_missing=True))
    with pytest.raises(ValidationError, match="no range"):
        DailySeries.model_validate(
            _daily_series(
                days=all_miss_days,
                all_missing=True,
                range_missing={"reason": "NOT_AVAILABLE"},
            )
        )
    with pytest.raises(ValidationError, match="not an assumption"):
        DailySeries.model_validate(
            _daily_series(days=all_miss_days, all_missing=True, assumption=True)
        )

    # Leap-year sequence accepted; skipping Feb 29 rejected
    leap_days = [
        {"date": "2004-02-28", "value": 1.0},
        {"date": "2004-02-29", "value": 2.0},
        {"date": "2004-03-01", "value": 3.0},
    ]
    DailySeries.model_validate(
        _daily_series(start_date="2004-02-28", end_date="2004-03-01", days=leap_days)
    )
    with pytest.raises(ValidationError, match="2004-02-29"):
        DailySeries.model_validate(
            _daily_series(
                start_date="2004-02-28",
                end_date="2004-03-01",
                days=[leap_days[0], leap_days[2]],
            )
        )

    # Extra day past end_date rejected; end_date < start_date rejected
    with pytest.raises(ValidationError, match="the days stop before end_date"):
        DailySeries.model_validate(
            _daily_series(
                start_date="2001-01-01",
                end_date="2001-01-01",
                days=[
                    {"date": "2001-01-01", "value": 1.0},
                    {"date": "2001-01-02", "value": 2.0},
                ],
            )
        )
    with pytest.raises(ValidationError, match="ends before it starts"):
        DailySeries.model_validate(
            _daily_series(start_date="2001-01-02", end_date="2001-01-01", days=[])
        )
    # Whitespace-only time_zone rejected
    with pytest.raises(ValidationError):
        DailySeries.model_validate(_daily_series(time_zone="  \t"))


def test_monthly_series_rollover_and_site_climate_uniqueness() -> None:
    # Single month and year rollover accepted
    MonthlySeries.model_validate(_monthly_series())
    MonthlySeries.model_validate(
        _monthly_series(
            start=(2001, 12),
            end=(2002, 2),
            months=[
                {"year": 2001, "month": 12, "value": 0.0},
                {
                    "year": 2002,
                    "month": 1,
                    "value": None,
                    "missing": {"reason": "NO_COVERAGE"},
                },
                {"year": 2002, "month": 2, "value": 1.0},
            ],
        )
    )

    # end < start across year boundary rejected
    with pytest.raises(ValidationError, match="ends before it starts"):
        MonthlySeries.model_validate(
            _monthly_series(start=(2002, 1), end=(2001, 12), months=[])
        )

    # Extra month past end rejected
    with pytest.raises(ValidationError, match="the months stop before end"):
        MonthlySeries.model_validate(
            _monthly_series(
                start=(2001, 12),
                end=(2001, 12),
                months=[
                    {"year": 2001, "month": 12, "value": 1.0},
                    {"year": 2002, "month": 1, "value": 2.0},
                ],
            )
        )

    # Same quantity in daily_series AND monthly_series is allowed
    SiteClimate.model_validate(
        _climate(
            daily_series=[_daily_series(quantity="placeholder_shared")],
            monthly_series=[_monthly_series(quantity="placeholder_shared")],
        )
    )
    # Duplicate inside monthly_series rejected
    with pytest.raises(ValidationError, match="share one quantity"):
        SiteClimate.model_validate(
            _climate(
                monthly_series=[
                    _monthly_series(quantity="placeholder_dup"),
                    _monthly_series(quantity="placeholder_dup"),
                ]
            )
        )


# --- site_soil_slope.py: uniqueness and empty list ---------------------------


def test_soil_slope_unique_quantities_non_adjacent_and_empty_list() -> None:
    SiteSoilSlope.model_validate(_soil(soil_properties=[]))
    with pytest.raises(ValidationError, match="share one quantity"):
        SiteSoilSlope.model_validate(
            _soil(
                soil_properties=[
                    {"quantity": "placeholder_a", **_val(1.0)},
                    {"quantity": "placeholder_b", **_val(2.0)},
                    {"quantity": "placeholder_a", **_val(3.0)},
                ]
            )
        )


# --- injected mutants proving guards fail when weakened ----------------------


def test_mutant_weakened_iso_date_and_source_check_in_common() -> None:
    compact = {"date": "20010101", "provenance": "DECLARED", "source": "PLACEHOLDER"}
    with pytest.raises(ValidationError):
        DateValue.model_validate(compact)
    with patch.object(common, "_ISO_DATE", re.compile(r".*")):
        assert DateValue.model_validate(compact).date == dt.date(2001, 1, 1)

    no_prov = _val(1.0)
    del no_prov["provenance"]
    with pytest.raises(ValidationError):
        Value.model_validate(no_prov)
    with patch.object(common, "check_source_or_assumption", lambda **kw: None):
        assert Value.model_validate(no_prov).value == 1.0


def test_mutant_weakened_dates_in_order_in_rotation_calendar() -> None:
    bad_period = {
        "period_type": "PLACEHOLDER-p",
        "start": _date("2001-05-10"),
        "end": _date("2001-05-09"),
    }
    with pytest.raises(ValidationError, match="ends before it starts"):
        CalendarPeriod.model_validate(bad_period)
    with patch.object(rotation_calendar, "check_dates_in_order", lambda *args: None):
        CalendarPeriod.model_validate(bad_period)


def test_mutant_weakened_provisional_and_feasibility_validators() -> None:
    bad_start = {
        "month": None,
        "provisional": False,
        "missing": {"reason": "NOT_DECLARED"},
    }
    with pytest.raises(ValidationError, match="no provisional mark"):
        AgYearStart.model_validate(bad_start)
    with _weaken_model_validator(AgYearStart, "_provisional_mark", lambda self: self):
        AgYearStart.model_validate(bad_start)

    bad_feas = {
        "feasible": True,
        "violations": [{"rule": "PLACEHOLDER-r", "component_ids": []}],
    }
    with pytest.raises(ValidationError, match="lists no violations"):
        Feasibility.model_validate(bad_feas)
    with _weaken_model_validator(Feasibility, "_consistent", lambda self: self):
        Feasibility.model_validate(bad_feas)


def test_mutant_weakened_climate_and_soil_guards() -> None:
    no_prov_series = _daily_series()
    del no_prov_series["provenance"]
    with pytest.raises(ValidationError):
        DailySeries.model_validate(no_prov_series)
    with patch.object(site_climate, "check_source_or_assumption", lambda **kw: None):
        DailySeries.model_validate(no_prov_series)

    dup_climate = _climate(
        daily_series=[
            _daily_series(quantity="placeholder_dup"),
            _daily_series(quantity="placeholder_dup"),
        ]
    )
    with pytest.raises(ValidationError, match="share one quantity"):
        SiteClimate.model_validate(dup_climate)
    with patch.object(site_climate, "_unique_quantities", lambda s, w: None):
        SiteClimate.model_validate(dup_climate)

    dup_soil = _soil(
        soil_properties=[
            {"quantity": "placeholder_a", **_val(1.0)},
            {"quantity": "placeholder_a", **_val(2.0)},
        ]
    )
    with pytest.raises(ValidationError, match="share one quantity"):
        SiteSoilSlope.model_validate(dup_soil)
    with _weaken_model_validator(
        SiteSoilSlope, "_unique_quantities", lambda self: self
    ):
        SiteSoilSlope.model_validate(dup_soil)
