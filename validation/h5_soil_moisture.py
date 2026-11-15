"""Descriptive [H5] root-zone soil-moisture contrast report (D107, D253).

Status: PROPOSED (blueprint section 3.7). Implements the qualitative contrast
summary for entry ``[H5]`` in ``docs/VALIDATION.md``:

- Decision D107 and D253: qualitative contrast of the timing of wetting and
  drying in the modelled balance against NASA POWER ``GWETROOT`` (``CQ7``),
  reported as ``QUALITATIVE_OBSERVATION_ONLY`` with **no pass/fail rule**,
  **no tolerance**, and **no numeric threshold**.
- ``mean_bias`` is reported as ``mean(modelled - observed)`` (PROPOSED:
  positive means modelled relative wetness exceeds observed).
- ``same_direction_step_fraction`` counts consecutive calendar-day pairs
  ``(d, d + 1 day)`` where both days are paired and the sign of the daily
  change matches between modelled and observed wetness (wetting together,
  drying together, or both steady).
- Absent ``CQ7`` series or wrong unit (C1.1) propagates
  ``Missing(reason="MISSING_INPUT")``; absent overlap or empty coverage
  propagates ``Missing(reason="NO_COVERAGE")``; invalid capacity, out-of-bounds
  wetness, or zero consecutive paired steps reports
  ``Missing(reason="NOT_COMPUTABLE")``.

Pure functions (G1): no file access, no network call, no clock, no environment
variable, and arguments are never modified.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from contracts.inputs.site_climate import SiteClimate
from contracts.results.models import Missing
from engine.water.root_zone_contrast import (
    PairedWetnessDay,
    WetnessPairing,
    pair_root_zone_wetness,
)

__all__ = [
    "H5ContrastReport",
    "H5_STATUS",
    "build_h5_contrast_report",
    "contrast_report_from_pairing",
]

H5_STATUS: Literal["QUALITATIVE_OBSERVATION_ONLY"] = "QUALITATIVE_OBSERVATION_ONLY"


@dataclass(frozen=True)
class H5ContrastReport:
    """Descriptive [H5] contrast between modelled wetness and CQ7 (D253).

    Carries no pass/fail boolean, no verdict, no tolerance, and no threshold.
    """

    paired_days: int
    skipped_days: int
    mean_modelled_wetness: float | Missing
    mean_observed_wetness: float | Missing
    mean_bias: float | Missing
    same_direction_step_fraction: float | Missing
    status: Literal["QUALITATIVE_OBSERVATION_ONLY"] = H5_STATUS

    def __post_init__(self) -> None:
        if self.status != H5_STATUS:
            raise ValueError(f"H5ContrastReport.status must be '{H5_STATUS}' (D253)")


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _step_sign(prev_value: float, curr_value: float) -> int:
    if curr_value > prev_value:
        return 1
    if curr_value < prev_value:
        return -1
    return 0


def _is_no_coverage(value: object) -> bool:
    return isinstance(value, Missing) and value.reason == "NO_COVERAGE"


def _missing_when_no_pairs(pairing: WetnessPairing) -> Missing:
    if pairing.series_missing is not None:
        return pairing.series_missing
    if not pairing.days:
        return Missing(
            reason="NO_COVERAGE",
            detail="no days available for [H5] root-zone soil-moisture contrast (C5.5)",
        )
    overlapping = [
        day
        for day in pairing.days
        if not (
            _is_no_coverage(day.modelled_wetness)
            or _is_no_coverage(day.observed_wetness)
        )
    ]
    if not overlapping:
        return Missing(
            reason="NO_COVERAGE",
            detail="no overlapping dates between modelled storage and observed CQ7 series (C5.5)",
        )
    for reason in ("MISSING_INPUT", "NOT_COMPUTABLE", "NO_COVERAGE"):
        for day in overlapping:
            for item in (day.modelled_wetness, day.observed_wetness):
                if isinstance(item, Missing) and item.reason == reason:
                    return item
    return Missing(
        reason="NOT_COMPUTABLE",
        detail="no paired days produced finite wetness values",
    )


def _same_direction_step_fraction(
    paired: list[tuple[dt.date, float, float]],
) -> float | Missing:
    step_count = 0
    same_direction_count = 0
    one_day = dt.timedelta(days=1)
    for index in range(len(paired) - 1):
        prev_date, prev_m, prev_o = paired[index]
        curr_date, curr_m, curr_o = paired[index + 1]
        if curr_date - prev_date != one_day:
            continue
        step_count += 1
        if _step_sign(prev_m, curr_m) == _step_sign(prev_o, curr_o):
            same_direction_count += 1
    if step_count == 0:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail=(
                "at least one consecutive pair of paired days is required to "
                "count step direction changes"
            ),
        )
    return same_direction_count / step_count


def contrast_report_from_pairing(pairing: WetnessPairing) -> H5ContrastReport:
    """Summarise an existing ``WetnessPairing`` into an ``H5ContrastReport``."""
    if not isinstance(pairing, WetnessPairing):
        raise TypeError(
            f"pairing: expected WetnessPairing, got {type(pairing).__name__} (G5)"
        )
    for day in pairing.days:
        if not isinstance(day, PairedWetnessDay):
            raise TypeError(
                "pairing.days entries must be PairedWetnessDay, "
                f"got {type(day).__name__} (G5)"
            )
    paired: list[tuple[dt.date, float, float]] = []
    for day in sorted(pairing.days, key=lambda item: item.date):
        m_val = day.modelled_wetness
        o_val = day.observed_wetness
        if _is_finite_number(m_val) and _is_finite_number(o_val):
            paired.append((day.date, float(m_val), float(o_val)))

    paired_days = len(paired)
    skipped_days = len(pairing.days) - paired_days
    if paired_days == 0:
        reason = _missing_when_no_pairs(pairing)
        return H5ContrastReport(
            paired_days=0,
            skipped_days=skipped_days,
            mean_modelled_wetness=reason,
            mean_observed_wetness=reason,
            mean_bias=reason,
            same_direction_step_fraction=reason,
            status=H5_STATUS,
        )

    mean_modelled = statistics.fmean(m_val for _, m_val, _ in paired)
    mean_observed = statistics.fmean(o_val for _, _, o_val in paired)
    mean_bias = statistics.fmean(m_val - o_val for _, m_val, o_val in paired)
    step_fraction = _same_direction_step_fraction(paired)
    return H5ContrastReport(
        paired_days=paired_days,
        skipped_days=skipped_days,
        mean_modelled_wetness=mean_modelled,
        mean_observed_wetness=mean_observed,
        mean_bias=mean_bias,
        same_direction_step_fraction=step_fraction,
        status=H5_STATUS,
    )


def build_h5_contrast_report(
    storage_by_day: Mapping[dt.date, float | int | Missing],
    climate: SiteClimate,
    *,
    capacity_mm: float | int | Missing,
) -> H5ContrastReport:
    """Build the descriptive [H5] contrast report from daily storage and climate.

    ``capacity_mm`` is a required keyword-only argument with no default.
    """
    pairing = pair_root_zone_wetness(
        storage_by_day,
        climate,
        capacity_mm=capacity_mm,
    )
    return contrast_report_from_pairing(pairing)
