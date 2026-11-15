"""Acceptance test of the unit l2/kinds-of-year (brief S-012; brought to main by
brief #386 under D240). PROPOSED.

Run with ``uv run pytest kinds_of_year/``.

EXAMPLE DATA. The ONI record is not in the repository until a person checks
and signs it (D240 (5), D34, D66). Every record here is written by hand: the
rule of D240 (1) as the v6 page states it, and anomalies that mean nothing,
chosen so that each case can be read off by hand. None is an ONI value.
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest

import kinds_of_year
from contracts.economic_facts import KINDS_OF_YEAR
from contracts.inputs.common import ReasonCode
from kinds_of_year import (
    SEASONS,
    KindOfYear,
    classify_agricultural_years,
    count_kinds,
    deciding_season,
    load_record,
    table_value,
)

EL_NINO, NEUTRAL, LA_NINA = KINDS_OF_YEAR
ROOT = Path(__file__).resolve().parent.parent

# The rule of D240 (1), as the v6 page states it: a threshold of +/- 0.5 degC
# met for a minimum of 5 consecutive overlapping seasons. It is written here
# only to make hand-made records; the code reads it from the record it is given.
RULE = {"threshold": 0.5, "min_consecutive_seasons": 5}


@pytest.fixture(scope="module")
def record():
    """A hand-made record (example data): the rule, every season of 2010..2014 at 0.0."""
    return synthetic(RULE, {})


@pytest.fixture(scope="module")
def threshold(record):
    return record["threshold"]


@pytest.fixture(scope="module")
def run_length(record):
    return record["min_consecutive_seasons"]


# 1. The record is read only from the path a caller gives ---------------------


def test_load_record_reads_the_file_it_is_given(tmp_path, record):
    path = tmp_path / "example_record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert load_record(path) == record
    assert load_record(str(path)) == record


def test_load_record_has_no_default_record():
    # The record waits for a person's signature (D34, D66): no path, no record.
    parameter = inspect.signature(load_record).parameters["path"]
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        load_record()
    assert not hasattr(kinds_of_year, "DEFAULT_RECORD")


def test_nothing_is_read_at_import():
    """Importing the package opens no file of a record (brief #386 (c))."""
    probe = (
        "import builtins, io, json\n"
        "opened = []\n"
        "real = builtins.open\n"
        "def watching(file, *args, **kwargs):\n"
        "    opened.append(str(file))\n"
        "    return real(file, *args, **kwargs)\n"
        "builtins.open = io.open = watching\n"
        "import kinds_of_year\n"
        "print(json.dumps(opened))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    opened = json.loads(done.stdout.strip().splitlines()[-1])
    assert [name for name in opened if name.endswith(".json")] == []


# 2. Episode logic on hand-made records -----------------------------------------

SYN_FIRST, SYN_LAST = 2010, 2014


def synthetic(rule, values, first=SYN_FIRST, last=SYN_LAST):
    """A hand-made record: every season of ``first``..``last`` at 0.0 except
    ``values``, with the threshold and run length of ``rule``."""
    seasons = []
    for year in range(first, last + 1):
        for name in SEASONS:
            seasons.append(
                {"season": name, "year": year, "anom": values.get((name, year), 0.0)}
            )
    return {
        "threshold": rule["threshold"],
        "min_consecutive_seasons": rule["min_consecutive_seasons"],
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
    result = classify_agricultural_years(record, 2011, 2011, 1)[2011]
    assert (result.season, result.season_year) == ("JJA", 2011)


# 5. Outside the record -------------------------------------------------------


def test_year_outside_the_record_is_missing(record):
    result = classify_agricultural_years(record, 1990, 1990, 7)[1990]
    assert isinstance(result, KindOfYear)
    assert result.kind is None
    assert result.missing_reason == "NO_COVERAGE"
    assert result.missing_reason in get_args(ReasonCode)
    assert result.detail


def test_count_kinds_is_none_when_a_year_is_missing(record):
    # Agricultural year 2014 is decided by DJF 2015, after the hand-made record.
    classified = classify_agricultural_years(record, 2012, 2014, 7)
    counts = count_kinds(classified)
    assert set(counts) == set(KINDS_OF_YEAR)
    assert all(value is None for value in counts.values())


# 6. A covered period, internal consistency only -----------------------------


def test_every_year_of_a_covered_period_has_a_kind(record):
    # Agricultural years 2010 to 2013, decided by DJF 2011 to DJF 2014, all in
    # the hand-made record.
    classified = classify_agricultural_years(record, 2010, 2013, 7)
    assert sorted(classified) == list(range(2010, 2014))
    for year, result in classified.items():
        assert (result.kind is None) != (result.missing_reason is None), year
        assert result.kind in KINDS_OF_YEAR
        assert result.season == "DJF"
        assert result.season_year == year + 1
    counts = count_kinds(classified)
    assert set(counts) == set(KINDS_OF_YEAR)
    assert all(isinstance(value, int) for value in counts.values())
    assert sum(counts.values()) == len(classified)


# 6b. D240: the threshold is applied to the one-decimal table values ---------


def run_ending_at(season, year, length, value):
    """``length`` consecutive seasons ending at ``season`` of ``year``."""
    end = SEASONS.index(season)
    return {
        (SEASONS[(end - back) % len(SEASONS)], year + (end - back) // len(SEASONS)): (
            value
        )
        for back in range(length)
    }


@pytest.mark.parametrize(
    ("anom", "table"),
    [(0.45, "0.5"), (-0.45, "-0.5"), (-0.46, "-0.5"), (0.44, "0.4"), (-0.44, "-0.4")],
)
def test_table_value_has_one_decimal_rounded_half_away_from_zero(anom, table):
    assert str(table_value(anom)) == table


@pytest.mark.parametrize(
    ("anom", "kind"),
    [
        (0.5, EL_NINO),  # prints 0.5: meets the threshold
        (-0.5, LA_NINA),
        (0.45, EL_NINO),  # two decimals below the threshold, prints 0.5
        (-0.46, LA_NINA),  # prints -0.5
        (0.44, NEUTRAL),  # prints 0.4: does not meet it
        (-0.44, NEUTRAL),
    ],
)
def test_the_threshold_is_met_on_the_one_decimal_value(anom, kind):
    # D240 (2): a run of the rule's length, every season at ``anom``.
    rec = synthetic(RULE, run_from_djf(2012, RULE["min_consecutive_seasons"], anom))
    assert classify_2011_july(rec).kind == kind


# The five seasons D240 names, where the two-decimal and the one-decimal
# readings part: each with the start month whose deciding season it is (start
# months 1, 2, 11 and 12, as D240 says). The anomaly of the season is a
# hand-made two-decimal value below the threshold that prints at it with one
# decimal; the four seasons before it carry a hand-made value beyond the
# threshold. EXAMPLE DATA: none of these numbers is a value of the record.
D240_SEASONS = [
    # (season, year, start month, agricultural year, two-decimal value, kind)
    ("JJA", 2000, 1, 2000, 0.45, EL_NINO),
    ("MJJ", 2002, 12, 2001, -0.46, LA_NINA),
    ("JJA", 2007, 1, 2007, 0.46, EL_NINO),
    ("JAS", 2021, 2, 2021, -0.45, LA_NINA),
    ("AMJ", 2023, 11, 2022, 0.47, EL_NINO),
]


@pytest.mark.parametrize(
    ("season", "year", "start_month", "ag_year", "value", "kind"),
    D240_SEASONS,
    ids=[f"{season} {year}" for season, year, *_ in D240_SEASONS],
)
def test_the_five_seasons_of_d240_are_read_on_one_decimal(
    season, year, start_month, ag_year, value, kind
):
    assert deciding_season(ag_year, start_month) == (season, year)
    threshold = RULE["threshold"]
    assert abs(value) < threshold  # the two-decimal value alone does not meet it
    assert abs(table_value(value)) == table_value(threshold)  # the printed one does
    beyond = threshold + 0.1 if value > 0 else -threshold - 0.1
    values = run_ending_at(season, year, RULE["min_consecutive_seasons"], beyond)
    values[(season, year)] = value
    rec = synthetic(RULE, values, first=year - 1, last=year + 1)
    result = classify_agricultural_years(rec, ag_year, ag_year, start_month)[ag_year]
    assert (result.kind, result.season, result.season_year) == (kind, season, year)
    # A hand-made value that prints one tenth short of the threshold (0.44 is
    # 0.4): the run is broken at the deciding season, and the year is neutral.
    short = 0.44 if value > 0 else -0.44
    assert abs(table_value(short)) < table_value(threshold)
    values[(season, year)] = short
    rec = synthetic(RULE, values, first=year - 1, last=year + 1)
    result = classify_agricultural_years(rec, ag_year, ag_year, start_month)[ag_year]
    assert result.kind == NEUTRAL


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
    # S-027 R2: a hand-made record over a period that holds present and
    # missing years builds every KindOfYear without a ValueError.
    classified = classify_agricultural_years(record, 2011, 2015, 7)
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
