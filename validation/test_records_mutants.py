"""Targeted mutant-killing tests for ``validation/records.py`` and ``validation/h10_runoff.py``.

Covers boundary conditions, type/exactness checks, placeholder detection,
cross-record references, store loading edge cases, summary accounting, and
exact rational/boundary arithmetic in H10 runoff comparison.

Every record, text, and number here is PLACEHOLDER test data only.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from contracts.results.models import Missing
from validation import h10_runoff, records
from validation.h10_runoff import compare_h10_runoff

PERSON_A = "PLACEHOLDER person alpha"
PERSON_B = "PLACEHOLDER person beta"


def _expected_number() -> dict:
    return {
        "format_version": 1,
        "kind": "expected_value",
        "id": "PLACEHOLDER-exp-num",
        "test_code": "E101",
        "quantity": "PLACEHOLDER quantity",
        "value": {"number": 111.5, "unit": "PLACEHOLDER unit"},
        "tolerance": {"absolute": 12.5},
        "citation": {
            "reference": "PLACEHOLDER reference",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": PERSON_A,
        "checked_by": PERSON_B,
    }


def _expected_missing() -> dict:
    rec = _expected_number()
    rec["id"] = "PLACEHOLDER-exp-miss"
    rec["test_code"] = "H101"
    rec["value"] = {"missing_reason": "PLACEHOLDER missing value"}
    del rec["tolerance"]
    return rec


def _protocol_run() -> dict:
    return {
        "format_version": 1,
        "kind": "protocol_run",
        "id": "PLACEHOLDER-run-1",
        "protocol": "PLACEHOLDER protocol",
        "code_version": "PLACEHOLDER sha",
        "run_at": "2026-11-15T12:00:00Z",
        "run_by": PERSON_A,
        "test_codes": ["E101", "H101", "D101"],
    }


def _result_passed() -> dict:
    return {
        "format_version": 1,
        "kind": "result",
        "id": "PLACEHOLDER-res-pass",
        "run_id": "PLACEHOLDER-run-1",
        "test_code": "E101",
        "expected": {"id": "PLACEHOLDER-exp-num"},
        "outcome": "passed",
        "observed": {"number": 111.5, "unit": "PLACEHOLDER unit"},
    }


def _result_failed() -> dict:
    rec = _result_passed()
    rec["id"] = "PLACEHOLDER-res-fail"
    rec["test_code"] = "D101"
    rec["expected"] = {"missing_reason": "PLACEHOLDER invariant"}
    rec["outcome"] = "failed"
    rec["observed"] = {"text": "PLACEHOLDER failed text"}
    return rec


def _result_not_evaluated() -> dict:
    rec = _result_passed()
    rec["id"] = "PLACEHOLDER-res-ne"
    rec["test_code"] = "H101"
    rec["expected"] = {"id": "PLACEHOLDER-exp-miss"}
    rec["outcome"] = "not_evaluated"
    rec["observed"] = {"missing_reason": "PLACEHOLDER not computed"}
    rec["reason"] = "PLACEHOLDER expected value missing"
    return rec


def _write_placeholder(path: Path, text: str) -> Path:
    assert "PLACEHOLDER" in text, f"test fixture must contain PLACEHOLDER: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _write_record(
    root: Path, record: dict, *, folder: str | None = None, name: str | None = None
) -> Path:
    target_folder = folder or records.FOLDER_BY_KIND[record["kind"]]
    target_name = name or f"{record['id']}.json"
    return _write_placeholder(
        root / target_folder / target_name, json.dumps(record, indent=2)
    )


def _write_base_store(root: Path) -> None:
    for builder in (
        _expected_number,
        _expected_missing,
        _protocol_run,
        _result_passed,
        _result_failed,
        _result_not_evaluated,
    ):
        _write_record(root, builder())


# --- 1. validation/records.py: predicates, formatting & is_placeholder --------


def test_records_format_version_rejects_bool_true_and_float_one():
    # Kills `type(version) is not int` -> `not isinstance(version, int)` or `version != 1`.
    for bad_version in (True, 1.0, 0):
        rec = _expected_number()
        rec["format_version"] = bad_version
        problems = records.check_record(rec, allow_placeholders=True)
        assert any("format_version:" in p for p in problems), (bad_version, problems)


def test_records_tolerance_zero_accepted_while_non_finite_and_bool_rejected():
    # Kills `tolerance[form] < 0` -> `<= 0` and non-finite / bool guards.
    for slot in ("absolute", "relative"):
        rec = _expected_number()
        rec["tolerance"] = {slot: 0.0}
        assert records.check_record(rec, allow_placeholders=True) == []

        rec_int = _expected_number()
        rec_int["tolerance"] = {slot: 0}
        assert records.check_record(rec_int, allow_placeholders=True) == []

        for bad in (True, False, float("inf"), float("-inf"), float("nan"), -1e-12):
            rec_bad = _expected_number()
            rec_bad["tolerance"] = {slot: bad}
            problems = records.check_record(rec_bad, allow_placeholders=True)
            assert any(f"tolerance.{slot}:" in p for p in problems), (slot, bad)


def test_records_value_zero_and_negative_accepted_while_inf_rejected():
    for num in (0, 0.0, -42.5):
        rec = _expected_number()
        rec["value"] = {"number": num, "unit": "PLACEHOLDER unit"}
        assert records.check_record(rec, allow_placeholders=True) == []

    for bad in (float("inf"), float("-inf"), False):
        rec = _expected_number()
        rec["value"] = {"number": bad, "unit": "PLACEHOLDER unit"}
        problems = records.check_record(rec, allow_placeholders=True)
        assert any("value.number:" in p for p in problems)


def test_records_test_code_and_id_regex_fullmatch_boundaries():
    # Kills `fullmatch` -> `match` (trailing newline/extra chars) and digit-start id.
    for good_code in ("E0", "H12a", "D999z"):
        rec = _expected_number()
        rec["test_code"] = good_code
        assert records.check_record(rec, allow_placeholders=True) == []

    for bad_code in ("E1\n", "E1ab", "E1A", "Ea", "E", " E1"):
        rec = _expected_number()
        rec["test_code"] = bad_code
        problems = records.check_record(rec, allow_placeholders=True)
        assert any("test_code:" in p for p in problems), (bad_code, problems)

    rec_digit_id = _expected_number()
    rec_digit_id["id"] = "0.PLACEHOLDER_a-b"
    assert records.check_record(rec_digit_id, allow_placeholders=True) == []

    for bad_id in (".PLACEHOLDER", "-PLACEHOLDER", "_PLACEHOLDER", "PLACEHOLDER\n"):
        rec_bad_id = _expected_number()
        rec_bad_id["id"] = bad_id
        problems = records.check_record(rec_bad_id, allow_placeholders=True)
        assert any(p.startswith("id:") for p in problems), (bad_id, problems)


def test_records_run_at_fullmatch_leap_year_and_newline_rejection():
    # Kills `fullmatch` -> `match` on run_at and leap-day validation.
    leap = _protocol_run()
    leap["run_at"] = "2024-02-29T23:59:59Z"
    assert records.check_record(leap, allow_placeholders=True) == []

    for bad_ts in (
        "2026-02-29T00:00:00Z",
        "2026-11-15T24:00:00Z",
        "2026-11-15t00:00:00z",
        "2026-11-15T00:00:00Z\n",
    ):
        rec = _protocol_run()
        rec["run_at"] = bad_ts
        problems = records.check_record(rec, allow_placeholders=True)
        assert any("run_at:" in p for p in problems), (bad_ts, problems)


def test_records_citation_url_extra_field_and_normalised_citation_needed():
    rec = _expected_number()
    rec["citation"]["url"] = "   "
    problems = records.check_record(rec, allow_placeholders=True)
    assert any("citation.url:" in p for p in problems)

    rec2 = _expected_number()
    rec2["citation"]["url"] = "  citation   needed  PLACEHOLDER "
    problems2 = records.check_record(rec2, allow_placeholders=True)
    assert any("CITATION NEEDED" in p for p in problems2)

    rec3 = _expected_number()
    rec3["citation"]["extra_key"] = "PLACEHOLDER"
    problems3 = records.check_record(rec3, allow_placeholders=True)
    assert any("unknown field 'extra_key'" in p for p in problems3)


def test_records_notes_and_result_combinations():
    rec = _expected_number()
    rec["notes"] = "   "
    assert any(
        "notes: must be a non-empty string" in p
        for p in records.check_record(rec, allow_placeholders=True)
    )

    # Not-evaluated result MAY hold a numeric observed value when reason is given.
    ne = _result_not_evaluated()
    ne["observed"] = {"number": 10.0, "unit": "PLACEHOLDER unit"}
    assert records.check_record(ne, allow_placeholders=True) == []

    # Not-evaluated result with whitespace-only reason is rejected.
    ne["reason"] = " \t "
    assert any(
        "reason:" in p for p in records.check_record(ne, allow_placeholders=True)
    )

    # Expected id with blank string is rejected.
    res = _result_passed()
    res["expected"] = {"id": "   "}
    assert any(
        "expected.id:" in p for p in records.check_record(res, allow_placeholders=True)
    )


def test_records_is_placeholder_case_keys_and_cyclic_dict():
    assert records.is_placeholder("placeholder") is True
    assert records.is_placeholder("pLaCeHoLdEr") is True
    assert records.is_placeholder({"nested": [{"PLACEHOLDER_key": 1}]}) is True

    cyclic_dict: dict = {}
    cyclic_dict["self"] = cyclic_dict
    assert records.is_placeholder(cyclic_dict) is False

    cyclic_with_marker: dict = {"inner": []}
    cyclic_with_marker["self"] = cyclic_with_marker
    cyclic_with_marker["inner"].append("placeholder")
    assert records.is_placeholder(cyclic_with_marker) is True


def test_records_changed_number_and_shown_edge_lengths():
    short_cn = records._ChangedNumber(1.0, "1" * 40)
    long_cn = records._ChangedNumber(1.0, "1" * 41)
    assert records._exactness_problem(short_cn).endswith(
        f"{'1' * 40}, which would change when read as a number"
    )
    assert "..." in records._exactness_problem(long_cn)

    # Negative inexact integer -(2**53 + 1) is caught, while -(2**53) is exact.
    assert records._exactness_problem(-(2**53)) is None
    assert records._exactness_problem(-(2**53 + 1)) == records._INEXACT_INTEGER
    assert records._exactness_problem(0.1) is None

    # _shown truncates strictly above 60 chars and handles oversized integers.
    assert records._shown("x" * 60) == repr("x" * 60)
    assert records._shown("x" * 61).endswith("...'")
    huge = 10 ** (sys.get_int_max_str_digits() + 10) - 1
    assert records._shown(huge) == "an integer too long to print"


# --- 2. check_references, load_store, summarise -------------------------------


def test_records_check_references_allows_missing_expected_for_not_evaluated_only():
    expected = {"PLACEHOLDER-exp-miss": _expected_missing()}
    runs = {"PLACEHOLDER-run-1": _protocol_run()}
    ok = {"PLACEHOLDER-res-ne": _result_not_evaluated()}
    assert records.check_references(expected, runs, ok) == {}

    for bad_outcome in ("passed", "failed"):
        bad = _result_not_evaluated()
        bad["outcome"] = bad_outcome
        bad["observed"] = {"number": 1.0, "unit": "PLACEHOLDER unit"}
        del bad["reason"]
        found = records.check_references(expected, runs, {"PLACEHOLDER-res-ne": bad})
        assert any(
            "can only be 'not_evaluated'" in m for m in found["PLACEHOLDER-res-ne"]
        )


def test_records_check_references_reports_both_broken_run_and_broken_expected():
    res = _result_passed()
    res["run_id"] = "PLACEHOLDER-missing-run"
    res["expected"] = {"id": "PLACEHOLDER-missing-exp"}
    found = records.check_references({}, {}, {"PLACEHOLDER-res-pass": res})
    msgs = found["PLACEHOLDER-res-pass"]
    assert any("no accepted protocol run" in m for m in msgs)
    assert any("no accepted expected value" in m for m in msgs)


def test_records_load_store_placeholder_rejection_marks_failed_malformed(tmp_path):
    _write_base_store(tmp_path)
    store = records.load_store(tmp_path, allow_placeholders=False)
    assert store.expected == {}
    assert store.runs == {}
    assert store.results == {}
    assert "results/PLACEHOLDER-res-fail.json" in store.failed_malformed
    summary = records.summarise(store)
    assert summary["failed_malformed"] == ["results/PLACEHOLDER-res-fail.json"]
    assert summary["counts"] == {"passed": 0, "failed": 1, "not_evaluated": 0}


def test_records_load_store_outside_extensions_unreadable_utf8_and_infinity(tmp_path):
    _write_base_store(tmp_path)
    # Non-json file at root is ignored; uppercase .JSON outside folders is reported.
    _write_placeholder(tmp_path / "PLACEHOLDER.txt", "PLACEHOLDER text")
    _write_placeholder(
        tmp_path / "stray" / "PLACEHOLDER.JSON", json.dumps(_protocol_run())
    )
    # Invalid UTF-8 bytes in expected/ do not stop the rest from loading.
    invalid = tmp_path / "expected" / "PLACEHOLDER-bad-utf8.json"
    invalid.write_bytes(b"\xff\xfePLACEHOLDER")
    # Infinity literal in JSON is rejected by _reject_constant.
    inf_text = json.dumps(_expected_number()).replace("111.5", "Infinity")
    _write_placeholder(tmp_path / "expected" / "PLACEHOLDER-exp-num.json", inf_text)

    store = records.load_store(tmp_path, allow_placeholders=True)
    by_path = {p: m for p, m in store.problems}
    assert "PLACEHOLDER.txt" not in by_path
    assert "outside" in by_path["stray/PLACEHOLDER.JSON"]
    assert (
        "cannot be read as UTF-8 text" in by_path["expected/PLACEHOLDER-bad-utf8.json"]
    )
    assert "Infinity is not a number" in by_path["expected/PLACEHOLDER-exp-num.json"]
    assert "PLACEHOLDER-run-1" in store.runs


def test_records_load_store_root_as_str_and_scalar_json_rejected(tmp_path):
    _write_placeholder(
        tmp_path / "runs" / "PLACEHOLDER-scalar.json", '"PLACEHOLDER scalar"'
    )
    store = records.load_store(str(tmp_path), allow_placeholders=True)
    assert store.problems == (
        ("runs/PLACEHOLDER-scalar.json", "record: must be a JSON object"),
    )


def test_records_summarise_unresolved_failed_counts_and_clears_no_result(tmp_path):
    _write_base_store(tmp_path)
    # Break expected reference for the failed result by removing expected-missing
    # and pointing failed result to missing expected id.
    bad_fail = _result_failed()
    bad_fail["expected"] = {"id": "PLACEHOLDER-does-not-exist"}
    _write_record(tmp_path, bad_fail)

    store = records.load_store(tmp_path, allow_placeholders=True)
    assert "PLACEHOLDER-res-fail" in store.unresolved
    summary = records.summarise(store)
    assert summary["failed"] == ["PLACEHOLDER-res-fail"]
    assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}
    assert summary["results_total"] == 3
    # Failed unresolved result still satisfies (run_id, D101) in no_result.
    assert summary["no_result"] == []
    assert summary["broken_references"] == [
        {"id": "PLACEHOLDER-res-fail", "outcome": "failed"}
    ]


def test_records_summarise_malformed_failed_with_whitespace_case_does_not_clear_no_result(
    tmp_path,
):
    _write_base_store(tmp_path)
    malformed = _result_failed()
    malformed["outcome"] = "  Failed  "
    _write_record(tmp_path, malformed)

    store = records.load_store(tmp_path, allow_placeholders=True)
    summary = records.summarise(store)
    assert summary["failed"] == []
    assert summary["failed_malformed"] == ["results/PLACEHOLDER-res-fail.json"]
    assert summary["counts"] == {"passed": 1, "failed": 1, "not_evaluated": 1}
    # Malformed record's run/test_code is untrusted, so D101 remains in no_result.
    assert summary["no_result"] == [
        {"run_id": "PLACEHOLDER-run-1", "test_code": "D101"}
    ]


def test_records_summarise_rejects_corrupt_store_fields():
    base = records.Store(
        expected={},
        runs={"PLACEHOLDER-run-1": _protocol_run()},
        results={},
        problems=(),
    )
    # Non-2-tuple in problems -> ValueError.
    with pytest.raises(ValueError, match="store.problems"):
        records.summarise(
            records.Store(
                expected=base.expected,
                runs=base.runs,
                results=base.results,
                problems=(("PLACEHOLDER-only-one",),),  # type: ignore[arg-type]
            )
        )
    # Non-dict runs -> ValueError.
    with pytest.raises(ValueError, match="store.runs"):
        records.summarise(
            records.Store(
                expected={},
                runs=[],  # type: ignore[arg-type]
                results={},
                problems=(),
            )
        )


# --- 3. validation/h10_runoff.py ----------------------------------------------


def test_h10_zero_pbias_bound_and_zero_event_cap_accepted():
    # Kills `< 0` -> `<= 0` in `_argument` for both pbias_bound_percent and event_cap_mm.
    measured = {2017: 10.0, 2018: 30.0, 2019: 20.0}
    exact_match = compare_h10_runoff(
        measured,
        dict(measured),
        pbias_bound_percent=0.0,
        event_cap_mm=0.0,
        modelled_daily={dt.date(2017, 1, 1): 0.0},
    )
    assert exact_match.pbias_condition.verdict == "pass"
    assert exact_match.h10.verdict == "pass"
    assert exact_match.large_events.flagged is False

    tiny_excess = compare_h10_runoff(
        measured,
        {2017: 9.0, 2018: 30.0, 2019: 20.0},
        pbias_bound_percent=0.0,
        event_cap_mm=0.0,
        modelled_daily={dt.date(2017, 1, 1): 0.001},
    )
    assert tiny_excess.pbias_condition.verdict == "fail"
    assert tiny_excess.large_events.flagged is True
    assert tiny_excess.large_events.days_above_cap == ((dt.date(2017, 1, 1), 0.001),)


def test_h10_booleans_rejected_in_arguments_and_values():
    # Kills dropping `isinstance(value, bool)` check in `_number`.
    measured = {2017: 10.0, 2018: 30.0, 2019: 20.0}
    with pytest.raises(ValueError, match="pbias_bound_percent"):
        compare_h10_runoff(
            measured,
            measured,
            pbias_bound_percent=True,
            event_cap_mm=10.0,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="event_cap_mm"):
        compare_h10_runoff(
            measured,
            measured,
            pbias_bound_percent=10.0,
            event_cap_mm=False,  # type: ignore[arg-type]
        )

    res = compare_h10_runoff(
        measured,
        {2017: True, 2018: 30.0, 2019: 20.0},  # type: ignore[dict-item]
        pbias_bound_percent=25.0,
        event_cap_mm=100.0,
        modelled_daily={dt.date(2017, 1, 1): False},  # type: ignore[dict-item]
    )
    assert res.h10.verdict is None
    assert "not a finite number" in res.h10.reason
    assert res.large_events.flagged is None
    assert res.large_events.days_without_value == (
        (dt.date(2017, 1, 1), "not a finite number"),
    )


def test_h10_empty_daily_mapping_gives_false_not_none():
    # Kills `if modelled_daily is None` -> `if not modelled_daily` in `_large_events`.
    measured = {2017: 10.0, 2018: 30.0, 2019: 20.0}
    res = compare_h10_runoff(
        measured,
        dict(measured),
        pbias_bound_percent=25.0,
        event_cap_mm=100.0,
        modelled_daily={},
    )
    assert res.large_events.flagged is False
    assert res.large_events.days_above_cap == ()
    assert res.large_events.days_without_value == ()
    assert res.large_events.reason is None


def test_h10_one_zero_measured_year_keeps_pbias_and_other_year_errors():
    # Kills treating a single zero measured year as invalid PBIAS when total > 0.
    measured = {2017: 0.0, 2018: 300.0, 2019: 200.0}
    modelled = {2017: 10.0, 2018: 250.0, 2019: 190.0}
    res = compare_h10_runoff(
        measured, modelled, pbias_bound_percent=25.0, event_cap_mm=100.0
    )
    assert res.pbias_percent == pytest.approx(100 * 50 / 500)
    assert res.h10.verdict == "pass"
    by_year = {item.year: item for item in res.year_errors}
    assert by_year[2017].relative_error_percent is None
    assert "measured value is zero" in by_year[2017].reason
    assert by_year[2018].relative_error_percent == pytest.approx(100 * 50 / 300)
    assert by_year[2019].relative_error_percent == pytest.approx(100 * 10 / 200)


def test_h10_both_conditions_fail_and_missing_without_detail_formatting():
    measured = {2017: 100.0, 2018: 300.0, 2019: 200.0}
    both_fail = compare_h10_runoff(
        measured,
        {2017: 200.0, 2018: 40.0, 2019: 60.0},
        pbias_bound_percent=25.0,
        event_cap_mm=100.0,
    )
    assert both_fail.h10.verdict == "fail"
    assert "condition (1)" in both_fail.h10.reason
    assert "condition (2)" in both_fail.h10.reason

    no_detail = Missing(reason="NOT_AVAILABLE", detail=None)
    missing_res = compare_h10_runoff(
        measured,
        {2017: no_detail, 2018: 300.0, 2019: 200.0},
        pbias_bound_percent=25.0,
        event_cap_mm=100.0,
    )
    assert missing_res.h10.verdict is None
    assert "missing with the reason NOT_AVAILABLE" in missing_res.h10.reason
    assert "NOT_AVAILABLE:" not in missing_res.h10.reason


def test_h10_daily_events_and_orders_are_sorted_and_exact_fraction_breaks_tie():
    measured = {2017: 1.0, 2018: 1.0 + 1e-15, 2019: 2.0}
    modelled = {2017: 1, 2018: Fraction(1) + Fraction(1, 10**15), 2019: 2}
    # Pass out-of-order dates in modelled_daily; days_above_cap must be sorted.
    daily = {
        dt.date(2019, 3, 5): 150.0,
        dt.date(2018, 1, 2): 101.0,
    }
    res = compare_h10_runoff(
        measured,
        {k: float(v) for k, v in modelled.items()},
        pbias_bound_percent=25.0,
        event_cap_mm=100.0,
        modelled_daily=daily,
    )
    assert res.measured_order.order == (2019, 2018, 2017)
    assert res.modelled_order.order == (2019, 2018, 2017)
    assert res.h10.verdict == "pass"
    assert res.large_events.days_above_cap == (
        (dt.date(2018, 1, 2), 101.0),
        (dt.date(2019, 3, 5), 150.0),
    )
    assert h10_runoff.PERCENT == 100
