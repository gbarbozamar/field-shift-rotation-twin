"""Acceptance tests of the mapping to "Site data: climate" (PROPOSED cases 16 to 23).

Run with ``uv run pytest adapters/`` from the repository root.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import get_args

import pytest

from adapters._fakes import (
    PLACEHOLDER_FILL,
    full_document,
    make_request,
    make_settings,
    power_document,
)
from adapters.power_mapping import DETAIL_NO_RANGE, UnusableResponse, to_site_climate
from contracts.inputs import SiteClimate
from contracts.inputs.common import ReasonCode

SETTINGS = make_settings()
REQUEST = make_request()  # 1900-01-01 to 1900-01-03


def series_by_quantity(document):
    return {series["quantity"]: series for series in document["daily_series"]}


def two_series(values_a: dict, values_b: dict | None = None):
    return power_document(
        {
            "PLACEHOLDER_PARAMETER_A": values_a,
            "PLACEHOLDER_PARAMETER_B": values_b
            if values_b is not None
            else {"19000101": 1.0, "19000102": 2.0, "19000103": 3.0},
        }
    )


# 16
def test_full_response():
    document = to_site_climate(
        full_document(REQUEST.start_date, REQUEST.end_date), REQUEST, SETTINGS
    )
    assert document["contract"] == "site_data_climate"
    assert document["example_data"] is False
    assert document["case_id"] == "placeholder_case"
    assert document["field_id"] == "placeholder_field"
    assert document["monthly_series"] == []
    assert [s["quantity"] for s in document["daily_series"]] == [
        "placeholder_quantity_a",
        "placeholder_quantity_b",
    ]
    for series in document["daily_series"]:
        assert series["unit"] == "PLACEHOLDER_unit"
        assert series["provenance"] == "OBSERVED"
        assert series["source"] == "placeholder_source"
        assert series["time_zone"] == "UTC"
        assert series["start_date"] == "1900-01-01"
        assert series["end_date"] == "1900-01-03"
        assert series["range_missing"] == {
            "reason": "NOT_AVAILABLE",
            "detail": DETAIL_NO_RANGE,
        }
        assert series["days"] == [
            {"date": "1900-01-01", "value": 1.0},
            {"date": "1900-01-02", "value": 2.0},
            {"date": "1900-01-03", "value": 3.0},
        ]
    json.dumps(document, allow_nan=False)  # JSON-ready


# 17
def test_fill_value_becomes_missing_never_zero():
    raw = two_series({"19000101": 1.0, "19000102": PLACEHOLDER_FILL, "19000103": 3.0})
    days = series_by_quantity(to_site_climate(raw, REQUEST, SETTINGS))[
        "placeholder_quantity_a"
    ]["days"]
    assert days[1]["date"] == "1900-01-02"
    assert days[1]["value"] is None
    assert days[1]["value"] != 0
    assert days[1]["missing"]["reason"] == "NO_COVERAGE"
    assert days[1]["missing"]["detail"]
    assert "missing" not in days[0] and "missing" not in days[2]


def test_fill_value_given_as_an_integer_is_still_the_fill_value():
    settings = make_settings(fill_value=-7)
    raw = power_document(
        {
            "PLACEHOLDER_PARAMETER_A": {"19000101": -7},
            "PLACEHOLDER_PARAMETER_B": {"19000101": -7.0},
        },
        fill_value=-7,
    )
    request = make_request(dt.date(1900, 1, 1), dt.date(1900, 1, 1))
    for series in to_site_climate(raw, request, settings)["daily_series"]:
        assert series["days"][0]["value"] is None


def test_configured_reason_is_the_one_written():
    settings = make_settings(fill_reason="NOT_AVAILABLE")
    raw = two_series({"19000101": PLACEHOLDER_FILL})
    days = series_by_quantity(to_site_climate(raw, REQUEST, settings))[
        "placeholder_quantity_a"
    ]["days"]
    assert {day["missing"]["reason"] for day in days} == {"NOT_AVAILABLE"}


# 18
@pytest.mark.parametrize("zero", [0, 0.0, -0.0])
def test_real_zero_stays_a_value(zero):
    raw = two_series({"19000101": zero, "19000102": 2.0, "19000103": 3.0})
    day = series_by_quantity(to_site_climate(raw, REQUEST, SETTINGS))[
        "placeholder_quantity_a"
    ]["days"][0]
    assert day == {"date": "1900-01-01", "value": 0.0}
    assert isinstance(day["value"], float)


# 19
def test_day_absent_from_the_response_becomes_missing():
    raw = two_series({"19000101": 1.0, "19000103": 3.0})
    days = series_by_quantity(to_site_climate(raw, REQUEST, SETTINGS))[
        "placeholder_quantity_a"
    ]["days"]
    assert [day["date"] for day in days] == ["1900-01-01", "1900-01-02", "1900-01-03"]
    assert days[1]["value"] is None
    assert days[1]["missing"]["reason"] == "NO_COVERAGE"
    assert days[1]["missing"]["detail"] != days[0].get("missing", {}).get("detail")


def test_days_outside_the_period_are_not_reported():
    raw = two_series({"18991231": 9.0, "19000101": 1.0, "19000104": 9.0})
    days = series_by_quantity(to_site_climate(raw, REQUEST, SETTINGS))[
        "placeholder_quantity_a"
    ]["days"]
    assert [day["date"] for day in days] == ["1900-01-01", "1900-01-02", "1900-01-03"]


# 20
@pytest.mark.parametrize(
    "values", [{}, {"19000101": PLACEHOLDER_FILL, "19000103": PLACEHOLDER_FILL}]
)
def test_all_missing_series_has_no_provenance_source_or_range(values):
    document = to_site_climate(two_series(values), REQUEST, SETTINGS)
    series = series_by_quantity(document)
    empty = series["placeholder_quantity_a"]
    assert "provenance" not in empty
    assert "source" not in empty
    assert "range_missing" not in empty
    assert empty["unit"] == "PLACEHOLDER_unit"
    assert empty["time_zone"] == "UTC"
    assert len(empty["days"]) == 3
    assert all(day["value"] is None for day in empty["days"])
    assert "provenance" in series["placeholder_quantity_b"]


# 21
def test_one_day_period():
    request = make_request(dt.date(1900, 6, 15), dt.date(1900, 6, 15))
    document = to_site_climate(
        full_document(request.start_date, request.end_date), request, SETTINGS
    )
    for series in document["daily_series"]:
        assert series["start_date"] == series["end_date"] == "1900-06-15"
        assert series["days"] == [{"date": "1900-06-15", "value": 1.0}]


def test_period_crossing_a_month_and_a_year_boundary():
    request = make_request(dt.date(1900, 12, 30), dt.date(1901, 1, 2))
    document = to_site_climate(
        full_document(request.start_date, request.end_date), request, SETTINGS
    )
    for series in document["daily_series"]:
        assert [day["date"] for day in series["days"]] == [
            "1900-12-30",
            "1900-12-31",
            "1901-01-01",
            "1901-01-02",
        ]
        assert [day["value"] for day in series["days"]] == [1.0, 2.0, 3.0, 4.0]


def test_period_crossing_the_end_of_february():
    # 1900 is not a leap year: no 29 February.
    request = make_request(dt.date(1900, 2, 27), dt.date(1900, 3, 2))
    document = to_site_climate(
        full_document(request.start_date, request.end_date), request, SETTINGS
    )
    dates = [day["date"] for day in document["daily_series"][0]["days"]]
    assert dates == ["1900-02-27", "1900-02-28", "1900-03-01", "1900-03-02"]


# 22
@pytest.mark.parametrize(
    "bad_key", ["1900-01-01", "190011", "19000229", "19001301", "1900010a", ""]
)
def test_unparseable_date_makes_the_response_unusable(bad_key):
    raw = two_series({"19000101": 1.0, bad_key: 2.0})
    with pytest.raises(UnusableResponse):
        to_site_climate(raw, REQUEST, SETTINGS)


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {},
        {"properties": {}},
        {"properties": {"parameter": []}},
        power_document({"PLACEHOLDER_PARAMETER_A": {"19000101": 1.0}}),
        two_series({"19000101": "1.0"}),
        two_series({"19000101": None}),
        two_series({"19000101": True}),
        two_series({"19000101": float("inf")}),
        dict(full_document(dt.date(1900, 1, 1), dt.date(1900, 1, 3)), header=[]),
        dict(
            full_document(dt.date(1900, 1, 1), dt.date(1900, 1, 3)),
            header={"fill_value": 1.0},
        ),
    ],
)
def test_response_without_the_expected_layout_is_unusable(raw):
    with pytest.raises(UnusableResponse):
        to_site_climate(raw, REQUEST, SETTINGS)


def test_header_without_fill_value_is_accepted():
    raw = dict(full_document(REQUEST.start_date, REQUEST.end_date), header={})
    assert to_site_climate(raw, REQUEST, SETTINGS)["daily_series"]


def test_mapping_does_not_change_its_input():
    raw = full_document(REQUEST.start_date, REQUEST.end_date)
    before = json.dumps(raw, sort_keys=True)
    to_site_climate(raw, REQUEST, SETTINGS)
    assert json.dumps(raw, sort_keys=True) == before


# 23
def test_drop_in_against_the_contract_model():
    """The mapper's document loads into the contract model, through JSON."""
    raw = two_series(
        {"19000101": 0.0, "19000102": PLACEHOLDER_FILL},
        {"19000101": PLACEHOLDER_FILL},
    )
    document = to_site_climate(raw, REQUEST, SETTINGS)
    # Through JSON, as the document travels.
    SiteClimate.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("code", get_args(ReasonCode))
@pytest.mark.parametrize("setting", ["fill_reason", "range_missing_reason"])
def test_every_reason_code_gives_a_document_that_loads(setting, code):
    """Every missing and range_missing part carries a detail, so every C3.2 code loads."""
    settings = make_settings(**{setting: code})
    raw = two_series({"19000101": 0.0, "19000102": PLACEHOLDER_FILL})  # one day absent
    document = to_site_climate(raw, REQUEST, settings)
    loaded = SiteClimate.model_validate_json(json.dumps(document))
    series = loaded.daily_series[0]
    assert series.range_missing.reason == settings.range_missing_reason
    assert series.range_missing.detail
    missing = [day.missing for day in series.days if day.value is None]
    assert len(missing) == 2
    assert all(part.reason == settings.fill_reason and part.detail for part in missing)


# --- the point of the series (issue 77, D9 and D18) --------------------------


def point_of(raw):
    return to_site_climate(raw, REQUEST, SETTINGS)["point"]


def document_with_coordinates(coordinates):
    raw = full_document(REQUEST.start_date, REQUEST.end_date)
    raw["geometry"] = {"type": "Point", "coordinates": coordinates}
    return raw


def test_point_is_read_from_the_response_in_geojson_order():
    # GeoJSON: longitude, latitude, elevation.
    point = point_of(document_with_coordinates([10.0, 20.0, 30.0]))
    assert point["longitude"]["value"] == 10.0
    assert point["latitude"]["value"] == 20.0
    assert point["elevation"]["value"] == 30.0


def test_point_comes_from_the_response_not_from_the_request():
    assert (REQUEST.latitude, REQUEST.longitude) != (20.0, 10.0)
    point = point_of(document_with_coordinates([10.0, 20.0, 30.0]))
    assert point["latitude"]["value"] != REQUEST.latitude
    assert point["longitude"]["value"] != REQUEST.longitude


def test_each_point_value_carries_unit_label_source_and_the_reason_it_has_no_range():
    point = point_of(document_with_coordinates([10.0, 20.0, 30.0]))
    for name in ("latitude", "longitude", "elevation"):
        value = point[name]
        assert value["unit"] == getattr(SETTINGS.point, f"{name}_unit")
        assert value["provenance"] == SETTINGS.point.provenance
        assert value["source"] == SETTINGS.source_id
        assert value["range_missing"]["reason"] == SETTINGS.range_missing_reason
        assert value["range_missing"]["detail"]
        assert "missing" not in value


def test_a_zero_elevation_is_a_real_value():
    elevation = point_of(document_with_coordinates([10.0, 20.0, 0.0]))["elevation"]
    assert elevation["value"] == 0.0
    assert "missing" not in elevation


def test_a_fill_value_elevation_is_missing_never_zero():
    elevation = point_of(document_with_coordinates([10.0, 20.0, PLACEHOLDER_FILL]))[
        "elevation"
    ]
    assert elevation["value"] is None
    assert elevation["missing"]["reason"] == SETTINGS.fill_reason
    assert elevation["missing"]["detail"]
    assert elevation["unit"] == SETTINGS.point.elevation_unit
    assert "provenance" not in elevation and "range_missing" not in elevation


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        "PLACEHOLDER",
        {},
        {"type": "Point"},
        {"type": "Point", "coordinates": "PLACEHOLDER"},
        {"type": "Point", "coordinates": []},
    ],
)
def test_a_response_without_a_point_gives_three_missing_values(geometry):
    raw = full_document(REQUEST.start_date, REQUEST.end_date)
    if geometry is None:
        del raw["geometry"]
    else:
        raw["geometry"] = geometry
    point = point_of(raw)
    for name in ("latitude", "longitude", "elevation"):
        assert point[name]["value"] is None
        assert point[name]["missing"]["reason"] == SETTINGS.fill_reason
        assert point[name]["unit"]


def test_a_point_without_elevation_keeps_its_coordinates():
    point = point_of(document_with_coordinates([10.0, 20.0]))
    assert point["longitude"]["value"] == 10.0
    assert point["latitude"]["value"] == 20.0
    assert point["elevation"]["value"] is None


@pytest.mark.parametrize("bad", ["PLACEHOLDER", None, True, float("nan")])
def test_a_part_that_is_not_a_finite_number_is_missing(bad):
    point = point_of(document_with_coordinates([bad, 20.0, 30.0]))
    assert point["longitude"]["value"] is None
    assert point["latitude"]["value"] == 20.0


@pytest.mark.parametrize(
    "coordinates",
    [[10.0, 20.0, 30.0], [10.0, 20.0], [], [10.0, 20.0, PLACEHOLDER_FILL]],
)
def test_the_document_with_its_point_loads_into_the_contract_model(coordinates):
    document = to_site_climate(
        document_with_coordinates(coordinates), REQUEST, SETTINGS
    )
    model = SiteClimate.model_validate_json(json.dumps(document))
    assert model.point.latitude.unit == SETTINGS.point.latitude_unit
