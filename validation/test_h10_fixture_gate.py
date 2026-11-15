"""Fixture schema and human-gate tests for [H10] (Grahmann et al. 2022 Table 5).

Verifies that ``validation/fixtures/h10_grahmann2022_runoff.json`` parses
cleanly, carries the signed numeric transcription (``checked_by``), and
enforces the separate ``year_basis_checked_by`` and plot-input gates so [H10]
remains ``not evaluated`` (``BLOCKED_NOT_EVALUATED``) until all open human
decisions are resolved.

Run from the repository root:
``python -m pytest validation/test_h10_fixture_gate.py``.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from contracts.results.models import Missing
from validation.h10_runoff import H10Result, compare_h10_runoff

ROOT = Path(__file__).resolve().parents[1]
H10_FIXTURE = ROOT / "validation" / "fixtures" / "h10_grahmann2022_runoff.json"

SIGNED_STATUS = "SIGNED_TRANSCRIPTION_BY_EXPLICIT_USER_AUTHORIZATION"
EXPECTED_CHECKED_BY = "gbarbozamar"
EXPECTED_TRANSCRIBED_BY = "AI session, 2026-11-15"
EXPECTED_YEAR_BASIS = "calendar_year_PER_D230_TO_BE_CHECKED"
EXPECTED_PBIAS_BOUND = 25
EXPECTED_EVENT_CAP = 100

EXPECTED_TABLE_5_ROWS = (
    {"year": 2017, "runoff_mm": 209.0, "printed": "209", "rainfall_mm": 1095.0},
    {"year": 2018, "runoff_mm": 579.0, "printed": "579", "rainfall_mm": 1197.0},
    {"year": 2019, "runoff_mm": 320.0, "printed": "320", "rainfall_mm": 1064.0},
)


@dataclass(frozen=True)
class H10GateEvaluation:
    """Outcome of evaluating the [H10] fixture and human gates."""

    status: str
    outcome: str
    issues: tuple[str, ...]
    comparison: H10Result | None
    measured: dict[int, float]
    pbias_bound_percent: float | None
    event_cap_mm: float | None


def _is_non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _read_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: fixture must be one JSON object")
    return data


def _extract_measured_and_criteria(
    fixture: dict,
) -> tuple[dict[int, float], float, float]:
    rows = fixture.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows must be a non-empty list")

    measured: dict[int, float] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"rows[{index}] must be an object")
        year = row.get("year")
        runoff = row.get("runoff_mm")
        printed = row.get("printed")
        rainfall = row.get("rainfall_mm")
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError(f"rows[{index}].year must be an int")
        if not _is_finite_number(runoff):
            raise ValueError(f"rows[{index}].runoff_mm must be a finite number")
        if not _is_finite_number(rainfall):
            raise ValueError(f"rows[{index}].rainfall_mm must be a finite number")
        if not _is_non_empty_text(printed) or float(printed) != float(runoff):
            raise ValueError(f"rows[{index}].printed must match runoff_mm")
        if not _is_non_empty_text(row.get("locator")):
            raise ValueError(f"rows[{index}].locator must be non-empty text")
        if year in measured:
            raise ValueError(f"duplicate year {year} in rows")
        measured[year] = float(runoff)

    criteria = fixture.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("criteria must be an object")
    pbias_bound = criteria.get("pbias_bound_percent")
    event_cap = criteria.get("event_cap_mm")
    if not _is_finite_number(pbias_bound) or pbias_bound < 0:
        raise ValueError("criteria.pbias_bound_percent must be a finite number >= 0")
    if not _is_finite_number(event_cap) or event_cap < 0:
        raise ValueError("criteria.event_cap_mm must be a finite number >= 0")
    return measured, float(pbias_bound), float(event_cap)


def evaluate_h10_fixture_gate(
    path: Path,
    *,
    plot_inputs_confirmed: bool = False,
    modelled_yearly: Mapping[int, float | Missing] | None = None,
    modelled_daily: Mapping[dt.date, float | Missing] | None = None,
) -> H10GateEvaluation:
    """Evaluate [H10] fixture signatures and open human gates.

    Even when numeric values are signed in ``checked_by``, an empty
    ``year_basis_checked_by``, unconfirmed plot inputs, or a missing EP3 run
    keeps [H10] ``not evaluated`` (``BLOCKED_NOT_EVALUATED``).
    """
    if not path.is_file():
        return H10GateEvaluation(
            status="BLOCKED_NOT_EVALUATED",
            outcome="not_evaluated",
            issues=(f"Fixture file is absent: {path.name}",),
            comparison=None,
            measured={},
            pbias_bound_percent=None,
            event_cap_mm=None,
        )

    fixture = _read_fixture(path)
    measured, pbias_bound, event_cap = _extract_measured_and_criteria(fixture)

    issues: list[str] = []
    if fixture.get("status") != SIGNED_STATUS:
        issues.append(f"Fixture status is not {SIGNED_STATUS}")
    if not _is_non_empty_text(fixture.get("checked_by")):
        issues.append("Numeric transcription checked_by is empty or missing")
    if not _is_non_empty_text(fixture.get("year_basis_checked_by")):
        issues.append("Calendar-year interpretation has not been checked")
    if not plot_inputs_confirmed:
        issues.append(
            "Plot-specific HSG/CN, soil profile, calendar, and climate are not confirmed"
        )
    if modelled_yearly is None:
        issues.append("No actual EP3 plot run supplied")

    if issues:
        detail = "; ".join(issues)
        missing_modelled = {
            year: Missing(reason="MISSING_INPUT", detail=detail) for year in measured
        }
        comparison = compare_h10_runoff(
            measured,
            missing_modelled,
            pbias_bound_percent=pbias_bound,
            event_cap_mm=event_cap,
            modelled_daily=modelled_daily,
        )
        return H10GateEvaluation(
            status="BLOCKED_NOT_EVALUATED",
            outcome="not_evaluated",
            issues=tuple(issues),
            comparison=comparison,
            measured=measured,
            pbias_bound_percent=pbias_bound,
            event_cap_mm=event_cap,
        )

    comparison = compare_h10_runoff(
        measured,
        modelled_yearly,
        pbias_bound_percent=pbias_bound,
        event_cap_mm=event_cap,
        modelled_daily=modelled_daily,
    )
    verdict = comparison.h10.verdict
    if verdict == "pass":
        outcome = "passed"
    elif verdict == "fail":
        outcome = "failed"
    else:
        outcome = "not_evaluated"
    return H10GateEvaluation(
        status="EVALUATED" if verdict in ("pass", "fail") else "BLOCKED_NOT_EVALUATED",
        outcome=outcome,
        issues=(),
        comparison=comparison,
        measured=measured,
        pbias_bound_percent=pbias_bound,
        event_cap_mm=event_cap,
    )


def test_h10_signed_fixture_parses_and_matches_table_5_structure():
    assert H10_FIXTURE.is_file()
    fixture = _read_fixture(H10_FIXTURE)

    assert fixture["status"] == SIGNED_STATUS
    assert fixture["checked_by"] == EXPECTED_CHECKED_BY
    assert fixture["transcribed_by"] == EXPECTED_TRANSCRIBED_BY
    assert fixture["year_basis"] == EXPECTED_YEAR_BASIS
    assert fixture["year_basis_checked_by"] == ""

    source = fixture["source"]
    assert "Grahmann et al. (2022)" in source["reference"]
    assert source["url"].startswith("https://")
    assert "Table 5" in source["locator"]

    rows = fixture["rows"]
    assert len(rows) == len(EXPECTED_TABLE_5_ROWS)
    for actual, expected in zip(rows, EXPECTED_TABLE_5_ROWS, strict=True):
        assert actual["year"] == expected["year"]
        assert actual["runoff_mm"] == expected["runoff_mm"]
        assert actual["printed"] == expected["printed"]
        assert float(actual["printed"]) == actual["runoff_mm"]
        assert actual["rainfall_mm"] == expected["rainfall_mm"]
        assert _is_non_empty_text(actual["locator"])

    criteria = fixture["criteria"]
    assert criteria["pbias_bound_percent"] == EXPECTED_PBIAS_BOUND
    assert criteria["event_cap_mm"] == EXPECTED_EVENT_CAP
    assert "D230" in criteria["source"]


def test_h10_fixture_gate_keeps_h10_not_evaluated_while_year_basis_unchecked():
    gate = evaluate_h10_fixture_gate(H10_FIXTURE)
    assert gate.status == "BLOCKED_NOT_EVALUATED"
    assert gate.outcome == "not_evaluated"
    assert "Calendar-year interpretation has not been checked" in gate.issues
    assert (
        "Plot-specific HSG/CN, soil profile, calendar, and climate are not confirmed"
        in gate.issues
    )
    assert "No actual EP3 plot run supplied" in gate.issues
    assert gate.comparison is not None
    assert gate.comparison.years == (2017, 2018, 2019)
    assert gate.comparison.pbias_condition.verdict is None
    assert gate.comparison.order_condition.verdict is None
    assert gate.comparison.h10.verdict is None
    assert gate.comparison.large_events.flagged is None

    # Even if synthetic plot inputs and modelled values were supplied, empty
    # year_basis_checked_by alone still keeps [H10] not evaluated.
    synthetic_modelled = {2017: 200.0, 2018: 550.0, 2019: 310.0}  # PLACEHOLDER
    still_blocked = evaluate_h10_fixture_gate(
        H10_FIXTURE,
        plot_inputs_confirmed=True,
        modelled_yearly=synthetic_modelled,
    )
    assert still_blocked.status == "BLOCKED_NOT_EVALUATED"
    assert still_blocked.outcome == "not_evaluated"
    assert still_blocked.issues == (
        "Calendar-year interpretation has not been checked",
    )
    assert still_blocked.comparison is not None
    assert still_blocked.comparison.h10.verdict is None


def test_tmp_path_missing_fixture_file_blocks_h10(tmp_path: Path):
    gate = evaluate_h10_fixture_gate(tmp_path / "missing_h10.json")
    assert gate.status == "BLOCKED_NOT_EVALUATED"
    assert gate.outcome == "not_evaluated"
    assert gate.comparison is None


@pytest.mark.parametrize("bad_checked_by", ["", "   ", None])
def test_tmp_path_unsigned_checked_by_blocks_h10(
    tmp_path: Path, bad_checked_by: str | None
):
    fixture = copy.deepcopy(_read_fixture(H10_FIXTURE))
    fixture["year_basis_checked_by"] = "PLACEHOLDER_CHECKER"
    if bad_checked_by is None:
        del fixture["checked_by"]
    else:
        fixture["checked_by"] = bad_checked_by

    path = tmp_path / "h10_unsigned_checked_by.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    gate = evaluate_h10_fixture_gate(
        path,
        plot_inputs_confirmed=True,
        modelled_yearly={2017: 200.0, 2018: 550.0, 2019: 310.0},  # PLACEHOLDER
    )
    assert gate.status == "BLOCKED_NOT_EVALUATED"
    assert gate.outcome == "not_evaluated"
    assert "Numeric transcription checked_by is empty or missing" in gate.issues
    assert gate.comparison is not None
    assert gate.comparison.h10.verdict is None


@pytest.mark.parametrize("bad_year_basis_checked_by", ["", "   ", None])
def test_tmp_path_empty_year_basis_checked_by_blocks_h10(
    tmp_path: Path, bad_year_basis_checked_by: str | None
):
    fixture = copy.deepcopy(_read_fixture(H10_FIXTURE))
    if bad_year_basis_checked_by is None:
        del fixture["year_basis_checked_by"]
    else:
        fixture["year_basis_checked_by"] = bad_year_basis_checked_by

    path = tmp_path / "h10_unchecked_year_basis.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    gate = evaluate_h10_fixture_gate(
        path,
        plot_inputs_confirmed=True,
        modelled_yearly={2017: 200.0, 2018: 550.0, 2019: 310.0},  # PLACEHOLDER
    )
    assert gate.status == "BLOCKED_NOT_EVALUATED"
    assert gate.outcome == "not_evaluated"
    assert gate.issues == ("Calendar-year interpretation has not been checked",)
    assert gate.comparison is not None
    assert gate.comparison.h10.verdict is None


def test_tmp_path_wrong_status_blocks_h10(tmp_path: Path):
    fixture = copy.deepcopy(_read_fixture(H10_FIXTURE))
    fixture["status"] = "UNSIGNED_DRAFT"
    fixture["year_basis_checked_by"] = "PLACEHOLDER_CHECKER"

    path = tmp_path / "h10_wrong_status.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    gate = evaluate_h10_fixture_gate(
        path,
        plot_inputs_confirmed=True,
        modelled_yearly={2017: 200.0, 2018: 550.0, 2019: 310.0},  # PLACEHOLDER
    )
    assert gate.status == "BLOCKED_NOT_EVALUATED"
    assert gate.outcome == "not_evaluated"
    assert f"Fixture status is not {SIGNED_STATUS}" in gate.issues


def test_tmp_path_all_gates_signed_allows_placeholder_comparator_run(tmp_path: Path):
    # Synthetic PLACEHOLDER fixture values only; tests gate clearance behaviour.
    placeholder_fixture = {
        "status": SIGNED_STATUS,
        "checked_by": "PLACEHOLDER_PERSON_A",
        "transcribed_by": "PLACEHOLDER_SESSION",
        "year_basis": "PLACEHOLDER_CALENDAR_YEAR",
        "year_basis_checked_by": "PLACEHOLDER_PERSON_B",
        "rows": [
            {
                "year": 2017,
                "runoff_mm": 100.0,
                "printed": "100",
                "rainfall_mm": 500.0,
                "locator": "PLACEHOLDER row 2017",
            },
            {
                "year": 2018,
                "runoff_mm": 300.0,
                "printed": "300",
                "rainfall_mm": 700.0,
                "locator": "PLACEHOLDER row 2018",
            },
            {
                "year": 2019,
                "runoff_mm": 200.0,
                "printed": "200",
                "rainfall_mm": 600.0,
                "locator": "PLACEHOLDER row 2019",
            },
        ],
        "criteria": {"pbias_bound_percent": 25, "event_cap_mm": 100},
    }
    path = tmp_path / "placeholder_h10_all_signed.json"
    path.write_text(json.dumps(placeholder_fixture), encoding="utf-8")

    gate = evaluate_h10_fixture_gate(
        path,
        plot_inputs_confirmed=True,
        modelled_yearly={2017: 90.0, 2018: 280.0, 2019: 190.0},  # PLACEHOLDER
    )
    assert gate.status == "EVALUATED"
    assert gate.outcome == "passed"
    assert gate.issues == ()
    assert gate.comparison is not None
    assert gate.comparison.h10.verdict == "pass"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda f: f.update({"rows": []}),
        lambda f: f["rows"][0].update({"printed": "999"}),
        lambda f: f["criteria"].update({"pbias_bound_percent": -1}),
        lambda f: f["criteria"].update({"event_cap_mm": "bad"}),
    ],
)
def test_tmp_path_malformed_fixture_raises(tmp_path: Path, mutator):
    fixture = copy.deepcopy(_read_fixture(H10_FIXTURE))
    mutator(fixture)
    path = tmp_path / "h10_malformed.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError):
        evaluate_h10_fixture_gate(path)
