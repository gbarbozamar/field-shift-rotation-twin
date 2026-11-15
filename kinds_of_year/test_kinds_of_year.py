"""Acceptance test of the unit l2/kinds-of-year (brief S-012). PROPOSED.

Run with ``uv run pytest kinds_of_year/``. Every threshold and run length used
here is read from the committed record; the record's own numbers are checked
against the quoted definition text, so the two cannot drift.
"""

import re
from typing import get_args

import pytest

from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode
from kinds_of_year import (
    SEASONS,
    KindOfYear,
    classify_agricultural_years,
    count_kinds,
    deciding_season,
    load_record,
)

EL_NINO, NEUTRAL, LA_NINA = KINDS_OF_YEAR

REQUIRED_MEMBERS = (
    "id",
    "reference",
    "url_table_page",
    "url_data_file",
    "locator",
    "date_read",
    "definition_text",
    "threshold",
    "min_consecutive_seasons",
    "transcribed_by",
    "checked_by",
    "data_header_line",
    "seasons",
)


@pytest.fixture(scope="module")
def record():
    return load_record()


@pytest.fixture(scope="module")
def threshold(record):
    return record["threshold"]


@pytest.fixture(scope="module")
def run_length(record):
    return record["min_consecutive_seasons"]


# 1. The record ------------------------------------------------------------


def test_record_loads_with_every_member_and_the_unsigned_mark(record):
    for member in REQUIRED_MEMBERS:
        assert member in record, member
        assert record[member] not in (None, "", []), member
    assert record["checked_by"] == "UNSIGNED_AI_PRECHECK"
    assert record["date_read"] == "2026-11-15"
    assert record["data_header_line"].split() == ["SEAS", "YR", "TOTAL", "ANOM"]


def test_seasons_are_the_twelve_names_in_order_with_no_gap(record):
    seasons = record["seasons"]
    years = sorted({item["year"] for item in seasons})
    assert years[0] == 2000
    assert years[-1] == 2025
    expected = [(name, year) for year in years for name in SEASONS]
    got = [(item["season"], item["year"]) for item in seasons]
    # Only the last year may stop early (seasons not yet published).
    assert got == expected[: len(got)]
    assert len(got) > len(expected) - len(SEASONS)
    for item in seasons:
        assert set(item) == {"season", "year", "anom"}
        assert isinstance(item["anom"], float)


# 2. The quoted text holds the machine fields --------------------------------


def test_definition_text_contains_threshold_and_run_length(record):
    text = record["definition_text"]
    threshold_match = re.search(r"threshold of \+/- ([0-9]+(?:\.[0-9]+)?)", text)
    run_match = re.search(r"minimum of ([0-9]+) consecutive overlapping seasons", text)
    assert threshold_match is not None
    assert run_match is not None
    assert float(threshold_match.group(1)) == record["threshold"]
    assert int(run_match.group(1)) == record["min_consecutive_seasons"]


# 3. Episode logic on SYNTHETIC series (not the real record) ------------------

SYN_FIRST, SYN_LAST = 2010, 2014


def synthetic(record, values):
    """A synthetic record: every season of 2010..2014 at 0.0 except ``values``.

    The threshold and run length are those of the real record.
    """
    seasons = []
    for year in range(SYN_FIRST, SYN_LAST + 1):
        for name in SEASONS:
            seasons.append(
                {"season": name, "year": year, "anom": values.get((name, year), 0.0)}
            )
    return {
        "threshold": record["threshold"],
        "min_consecutive_seasons": record["min_consecutive_seasons"],
        "seasons": seasons,
    }


def run_from_djf(year, length, value):
    """``length`` consecutive seasons starting at DJF of ``year``."""
    return {(SEASONS[i], year): value for i in range(length)}


def classify_2011_july(rec):
    # start_month 7: DJF 2012 decides agricultural year 2011.
    return classify_agricultural_years(rec, 2011, 2011, 7)[2011]


def test_run_one_season_short_is_not_an_episode(record, threshold, run_length):
    rec = synthetic(record, run_from_djf(2012, run_length - 1, threshold + 0.1))
    result = classify_2011_july(rec)
    assert result.kind == NEUTRAL
    assert result.missing_reason is None


def test_run_of_exactly_the_run_length_is_an_episode(record, threshold, run_length):
    rec = synthetic(record, run_from_djf(2012, run_length, threshold + 0.1))
    assert classify_2011_july(rec).kind == EL_NINO


def test_a_run_ending_at_the_deciding_season_counts(record, threshold, run_length):
    # The run is NDJ 2011 back over run_length seasons, plus DJF 2012.
    values = {("DJF", 2012): threshold + 0.1}
    for i in range(run_length - 1):
        values[(SEASONS[11 - i], 2011)] = threshold + 0.1
    assert classify_2011_july(synthetic(record, values)).kind == EL_NINO


def test_values_exactly_at_the_threshold_meet_it(record, threshold, run_length):
    # The quote: "when the threshold is met"; a value equal to it meets it.
    rec = synthetic(record, run_from_djf(2012, run_length, threshold))
    assert classify_2011_july(rec).kind == EL_NINO
    rec = synthetic(record, run_from_djf(2012, run_length, -threshold))
    assert classify_2011_july(rec).kind == LA_NINA


def test_negative_run_gives_la_nina(record, threshold, run_length):
    rec = synthetic(record, run_from_djf(2012, run_length, -threshold - 0.1))
    result = classify_2011_july(rec)
    assert result.kind == LA_NINA
    assert (result.season, result.season_year) == ("DJF", 2012)


def test_a_run_that_changes_sign_is_not_one_run(record, threshold, run_length):
    values = run_from_djf(2012, run_length, threshold + 0.1)
    values[(SEASONS[1], 2012)] = -threshold - 0.1
    assert classify_2011_july(synthetic(record, values)).kind == NEUTRAL


def test_run_that_cannot_be_judged_at_the_record_edge_is_missing(record, threshold):
    # NDJ 2014 is the last season of the synthetic record and meets the
    # threshold; whether its run reaches the length needs later seasons.
    rec = synthetic(record, {("NDJ", 2014): threshold + 0.1})
    # start_month 6: the season centred on December, NDJ of the same year.
    result = classify_agricultural_years(rec, 2014, 2014, 6)[2014]
    assert result.kind is None
    assert result.missing_reason == "NO_COVERAGE"
    assert result.detail


# 4. Season choice, by hand arithmetic --------------------------------------


@pytest.mark.parametrize(
    ("start_month", "expected"),
    [
        # start 7: 7 + 6 = 13 -> month 1 of Y+1 -> season centred on January.
        (7, ("DJF", 2001)),
        # start 1: 1 + 6 = 7 -> July of Y -> JJA.
        (1, ("JJA", 2000)),
        # start 6: 6 + 6 = 12 -> December of Y -> NDJ.
        (6, ("NDJ", 2000)),
        # start 12: 12 + 6 = 18 -> month 6 of Y+1 -> MJJ.
        (12, ("MJJ", 2001)),
        # start 3: 3 + 6 = 9 -> September of Y -> ASO.
        (3, ("ASO", 2000)),
        # start 10: 10 + 6 = 16 -> month 4 of Y+1 -> MAM.
        (10, ("MAM", 2001)),
    ],
)
def test_deciding_season(start_month, expected):
    assert deciding_season(2000, start_month) == expected


def test_classification_records_the_season_used(record):
    result = classify_agricultural_years(record, 2005, 2005, 1)[2005]
    assert (result.season, result.season_year) == ("JJA", 2005)


# 5. Outside the record -------------------------------------------------------


def test_year_outside_the_record_is_missing(record):
    result = classify_agricultural_years(record, 1990, 1990, 7)[1990]
    assert isinstance(result, KindOfYear)
    assert result.kind is None
    assert result.missing_reason == "NO_COVERAGE"
    assert result.missing_reason in get_args(ReasonCode)
    assert result.detail


def test_count_kinds_is_none_when_a_year_is_missing(record):
    classified = classify_agricultural_years(record, 2023, 2026, 7)
    counts = count_kinds(classified)
    assert set(counts) == set(KINDS_OF_YEAR)
    assert all(value is None for value in counts.values())


# 6. The real record, internal consistency only -----------------------------


def test_real_record_2001_to_2023_july(record):
    classified = classify_agricultural_years(record, 2001, 2023, 7)
    assert sorted(classified) == list(range(2001, 2024))
    for year, result in classified.items():
        assert (result.kind is None) != (result.missing_reason is None), year
        if result.kind is not None:
            assert result.kind in KINDS_OF_YEAR
            assert result.season == "DJF"
            assert result.season_year == year + 1
    counts = count_kinds(classified)
    assert set(counts) == set(KINDS_OF_YEAR)
    assert all(isinstance(value, int) for value in counts.values())
    assert sum(counts.values()) == len(classified)


# 7. ValueError ------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "last", "month"),
    [(2005, 2004, 7), (2005, 2005, 0), (2005, 2005, 13)],
)
def test_value_errors(record, first, last, month):
    with pytest.raises(ValueError):
        classify_agricultural_years(record, first, last, month)


def test_deciding_season_rejects_a_bad_month():
    with pytest.raises(ValueError):
        deciding_season(2000, 13)


@pytest.mark.parametrize("month", [True, False])
def test_start_month_rejects_a_bool(record, month):
    with pytest.raises(ValueError, match="start_month"):
        classify_agricultural_years(record, 2005, 2005, month)
    with pytest.raises(ValueError, match="start_month"):
        deciding_season(2000, month)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("threshold", 0),
        ("threshold", -0.5),
        ("threshold", float("nan")),
        ("threshold", float("inf")),
        ("threshold", True),
        ("threshold", "0.5"),
        ("threshold", None),
        ("min_consecutive_seasons", 0),
        ("min_consecutive_seasons", True),
        ("min_consecutive_seasons", 2.0),
        ("min_consecutive_seasons", None),
    ],
)
def test_invalid_rule_fields_are_rejected(record, field, bad):
    rec = synthetic(record, {})
    rec[field] = bad
    with pytest.raises(ValueError, match=field):
        classify_agricultural_years(rec, 2011, 2011, 7)


def test_duplicated_season_row_is_rejected(record):
    rec = synthetic(record, {})
    rec["seasons"].append({"season": "JJA", "year": 2012, "anom": 0.0})
    with pytest.raises(ValueError, match="duplicated season JJA 2012"):
        classify_agricultural_years(rec, 2011, 2011, 7)


# 8. S-027 (PROPOSED): record rows, years and the KindOfYear invariant -------


def _small_record(record):
    """A small hand-made record: the real rule, every season of 2010..2014 at 0.0."""
    return synthetic(record, {})


def test_record_without_a_seasons_list_is_rejected(record):
    rec = _small_record(record)
    del rec["seasons"]
    with pytest.raises(ValueError, match="seasons"):
        classify_agricultural_years(rec, 2011, 2011, 7)
    rec["seasons"] = {"season": "DJF", "year": 2012, "anom": 0.0}
    with pytest.raises(ValueError, match="seasons"):
        classify_agricultural_years(rec, 2011, 2011, 7)


@pytest.mark.parametrize("field", ["season", "year", "anom"])
def test_row_lacking_a_field_is_rejected(record, field):
    rec = _small_record(record)
    del rec["seasons"][4][field]
    with pytest.raises(ValueError, match=f"row 4: field '{field}'"):
        classify_agricultural_years(rec, 2011, 2011, 7)


@pytest.mark.parametrize("bad", ["djf", 1, None])
def test_row_with_a_season_not_in_seasons_is_rejected(record, bad):
    rec = _small_record(record)
    rec["seasons"][2]["season"] = bad
    with pytest.raises(ValueError, match="row 2: unknown season"):
        classify_agricultural_years(rec, 2011, 2011, 7)


@pytest.mark.parametrize("bad", [True, 2010.0, "2010", None])
def test_row_with_a_year_that_is_not_an_int_is_rejected(record, bad):
    rec = _small_record(record)
    rec["seasons"][5]["year"] = bad
    with pytest.raises(ValueError, match="row 5: field 'year'"):
        classify_agricultural_years(rec, 2011, 2011, 7)


@pytest.mark.parametrize(
    "bad", [True, None, "0.0", float("nan"), float("inf"), float("-inf")]
)
def test_row_with_an_anom_that_is_not_a_finite_number_is_rejected(record, bad):
    rec = _small_record(record)
    rec["seasons"][6]["anom"] = bad
    with pytest.raises(ValueError, match="row 6: field 'anom'"):
        classify_agricultural_years(rec, 2011, 2011, 7)


@pytest.mark.parametrize("bad", [True, False, 2011.0, "2011", None])
def test_years_that_are_not_ints_are_rejected(record, bad):
    with pytest.raises(ValueError, match="first_year"):
        classify_agricultural_years(record, bad, 2011, 7)
    with pytest.raises(ValueError, match="last_year"):
        classify_agricultural_years(record, 2011, bad, 7)


@pytest.mark.parametrize(
    ("kind", "reason"),
    [(EL_NINO, "NO_COVERAGE"), (None, None)],
    ids=["both", "neither"],
)
def test_kind_of_year_holds_a_kind_or_a_reason(kind, reason):
    with pytest.raises(ValueError, match="kind"):
        KindOfYear(
            kind=kind,
            missing_reason=reason,
            detail=None,
            season="DJF",
            season_year=2012,
        )


@pytest.mark.parametrize("bad", ["dry", "El_Nino", ""])
def test_kind_of_year_refuses_a_kind_not_in_kinds_of_year(bad):
    # S-027 R2 (PROPOSED).
    with pytest.raises(ValueError, match="KINDS_OF_YEAR"):
        KindOfYear(
            kind=bad, missing_reason=None, detail=None, season="DJF", season_year=2012
        )


def test_kind_of_year_refuses_a_detail_on_a_present_kind():
    # S-027 R2 (PROPOSED): classify_agricultural_years sets no detail on a
    # present kind, so one is refused.
    with pytest.raises(ValueError, match="no missing detail"):
        KindOfYear(
            kind=NEUTRAL,
            missing_reason=None,
            detail="some text",
            season="DJF",
            season_year=2012,
        )


def test_every_classified_year_satisfies_the_invariant(record):
    # S-027 R2: the real record over a period that holds present and missing
    # years builds every KindOfYear without a ValueError.
    classified = classify_agricultural_years(record, 2020, 2026, 7)
    for item in classified.values():
        if item.kind is not None:
            assert item.kind in KINDS_OF_YEAR
            assert item.detail is None
        else:
            assert item.missing_reason == "NO_COVERAGE"
            assert item.detail


def test_unknown_season_name_is_rejected(record):
    rec = synthetic(record, {})
    rec["seasons"][3] = {"season": "XYZ", "year": 2010, "anom": 0.0}
    with pytest.raises(ValueError, match="row 3.*XYZ"):
        classify_agricultural_years(rec, 2011, 2011, 7)
