"""Daily relative root-zone wetness and pairing against NASA POWER GWETROOT (CQ7).

Status: PROPOSED (blueprint section 3.7). Implements the engine-side
preparation for ``[H5]`` in ``docs/VALIDATION.md`` and ``CQ7`` in
``contracts/CLIMATE_QUANTITIES.md`` (decisions D107, D113, D114, D253).

Rules from D107, D114, and D253:

- ``GWETROOT`` is relative saturation of the root zone (0 to 100 cm,
  dimensionless fraction in ``[0, 1]``). It is never converted to mm, never
  used as an initial state, and never put into alternative rotations.
- Modelled daily relative root-zone wetness is ``storage / capacity_mm`` from
  an explicit daily storage series and an explicit finite positive
  ``capacity_mm`` with zero defaults.
- When ``capacity_mm`` is missing, the result is ``Missing(reason="MISSING_INPUT")``.
  When ``capacity_mm <= 0`` or non-finite, the result is
  ``Missing(reason="NOT_COMPUTABLE")``.
- When ``storage`` on a day is missing, the result is
  ``Missing(reason="MISSING_INPUT")``; when non-finite,
  ``Missing(reason="NOT_COMPUTABLE")``.
- Observed wetness from ``SiteClimate.daily_series`` uses PROPOSED quantity
  identifier ``ROOT_ZONE_WETNESS = "soil_wetness_root_zone"`` and PROPOSED unit
  string ``ROOT_ZONE_WETNESS_UNIT = "dimensionless"`` (``CQ7`` O15 remains OPEN
  in ``contracts/CLIMATE_QUANTITIES.md``).
- Unit strings are compared exactly as written (C1.1); no conversion is done.
- Observed daily wetness values outside ``[0, 1]`` or non-finite are rejected
  with ``Missing(reason="NOT_COMPUTABLE")``.
- No pass/fail rule, tolerance, or numeric threshold appears here (D253).

Pure functions (G1): no file access, no network call, no clock, no environment
variable, and arguments are never modified.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass

from contracts.inputs.site_climate import DailySeries, SiteClimate
from contracts.results.models import Missing

__all__ = [
    "PairedWetnessDay",
    "ROOT_ZONE_WETNESS",
    "ROOT_ZONE_WETNESS_UNIT",
    "WetnessPairing",
    "compute_daily_relative_wetness",
    "compute_day_relative_wetness",
    "pair_root_zone_wetness",
    "read_observed_root_zone_wetness",
]

# PROPOSED identifier and unit string for CQ7 (GWETROOT); O15 is OPEN in
# contracts/CLIMATE_QUANTITIES.md.
ROOT_ZONE_WETNESS = "soil_wetness_root_zone"
ROOT_ZONE_WETNESS_UNIT = "dimensionless"


@dataclass(frozen=True)
class PairedWetnessDay:
    """One calendar day pairing modelled and observed relative root-zone wetness."""

    date: dt.date
    modelled_wetness: float | Missing
    observed_wetness: float | Missing


@dataclass(frozen=True)
class WetnessPairing:
    """Daily pairing of modelled relative root-zone wetness against CQ7.

    ``series_missing`` holds a ``Missing`` when the CQ7 series itself cannot be
    read from ``SiteClimate`` (absent series or wrong unit), and ``None``
    otherwise.
    """

    days: tuple[PairedWetnessDay, ...]
    series_missing: Missing | None


def _is_number(value: object) -> bool:
    """True for ``int`` or ``float``; ``bool`` is rejected as a caller defect."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_date(value: object) -> bool:
    return isinstance(value, dt.date) and not isinstance(value, dt.datetime)


def _describe_missing(label: str, missing: Missing) -> str:
    if missing.detail is None:
        return f"{label} is missing (reason {missing.reason})"
    return f"{label} is missing (reason {missing.reason}: {missing.detail})"


def _validate_capacity(capacity_mm: object) -> float | Missing:
    if isinstance(capacity_mm, Missing):
        return Missing(
            reason="MISSING_INPUT",
            detail=_describe_missing("input 'capacity_mm'", capacity_mm),
        )
    if not _is_number(capacity_mm):
        raise TypeError(
            "capacity_mm: expected int, float, or Missing, "
            f"got {type(capacity_mm).__name__} (G5)"
        )
    assert isinstance(capacity_mm, (int, float))
    if not _is_finite(capacity_mm) or capacity_mm <= 0:
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="capacity_mm must be a finite positive number",
        )
    return float(capacity_mm)


def compute_day_relative_wetness(
    storage_mm: float | int | Missing,
    *,
    capacity_mm: float | int | Missing,
) -> float | Missing:
    """Compute relative root-zone wetness ``storage_mm / capacity_mm`` for one day.

    ``capacity_mm`` is a required keyword-only argument with no default.
    """
    if not isinstance(storage_mm, Missing) and not _is_number(storage_mm):
        raise TypeError(
            "storage_mm: expected int, float, or Missing, "
            f"got {type(storage_mm).__name__} (G5)"
        )
    validated_capacity = _validate_capacity(capacity_mm)
    if isinstance(validated_capacity, Missing):
        return validated_capacity
    if isinstance(storage_mm, Missing):
        return Missing(
            reason="MISSING_INPUT",
            detail=_describe_missing("input 'storage_mm'", storage_mm),
        )
    assert isinstance(storage_mm, (int, float))
    if not _is_finite(storage_mm):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="storage_mm is not a finite number",
        )
    ratio = float(storage_mm) / validated_capacity
    if not _is_finite(ratio):
        return Missing(
            reason="NOT_COMPUTABLE",
            detail="relative wetness storage_mm / capacity_mm is not finite",
        )
    return ratio


def compute_daily_relative_wetness(
    storage_by_day: Mapping[dt.date, float | int | Missing],
    *,
    capacity_mm: float | int | Missing,
) -> dict[dt.date, float | Missing]:
    """Compute daily relative root-zone wetness over an explicit storage series.

    ``capacity_mm`` is a required keyword-only argument with no default.
    """
    if not isinstance(storage_by_day, Mapping):
        raise TypeError(
            "storage_by_day: expected Mapping[date, float | Missing], "
            f"got {type(storage_by_day).__name__} (G5)"
        )
    _validate_capacity(capacity_mm)
    validated_items: list[tuple[dt.date, float | int | Missing]] = []
    for day, storage in storage_by_day.items():
        if not _is_date(day):
            raise TypeError(
                f"storage_by_day keys must be datetime.date, got {type(day).__name__} (G5)"
            )
        if not isinstance(storage, Missing) and not _is_number(storage):
            raise TypeError(
                f"storage_by_day[{day.isoformat()}]: expected int, float, or Missing, "
                f"got {type(storage).__name__} (G5)"
            )
        validated_items.append((day, storage))
    validated_items.sort(key=lambda item: item[0])
    return {
        day: compute_day_relative_wetness(storage, capacity_mm=capacity_mm)
        for day, storage in validated_items
    }


def _find_wetness_series(climate: SiteClimate) -> DailySeries | None:
    for series in climate.daily_series:
        if series.quantity == ROOT_ZONE_WETNESS:
            return series
    return None


def read_observed_root_zone_wetness(
    climate: SiteClimate,
) -> dict[dt.date, float | Missing] | Missing:
    """Extract and validate ``CQ7`` daily root-zone wetness from ``SiteClimate``.

    Returns ``Missing(reason="MISSING_INPUT")`` when the series is absent or
    carries a unit other than ``ROOT_ZONE_WETNESS_UNIT`` (C1.1). Daily entries
    outside ``[0, 1]`` or non-finite become ``Missing(reason="NOT_COMPUTABLE")``,
    and missing daily entries become ``Missing(reason="MISSING_INPUT")``.
    """
    if not isinstance(climate, SiteClimate):
        raise TypeError(
            f"climate: expected SiteClimate, got {type(climate).__name__} (G5)"
        )
    series = _find_wetness_series(climate)
    if series is None:
        return Missing(
            reason="MISSING_INPUT",
            detail=f"the climate record has no daily series '{ROOT_ZONE_WETNESS}'",
        )
    if series.unit != ROOT_ZONE_WETNESS_UNIT:
        return Missing(
            reason="MISSING_INPUT",
            detail=(
                f"the daily series '{ROOT_ZONE_WETNESS}' is in the unit "
                f"'{series.unit}', not in the accepted unit "
                f"'{ROOT_ZONE_WETNESS_UNIT}' (C1.1)"
            ),
        )
    observed: dict[dt.date, float | Missing] = {}
    for item in sorted(series.days, key=lambda day: day.date):
        if item.missing is not None:
            detail_suffix = f": {item.missing.detail}" if item.missing.detail else ""
            observed[item.date] = Missing(
                reason="MISSING_INPUT",
                detail=(
                    f"observed '{ROOT_ZONE_WETNESS}' on {item.date.isoformat()} "
                    f"is missing ({item.missing.reason}{detail_suffix})"
                ),
            )
            continue
        value = item.value
        if not _is_number(value):
            raise TypeError(
                f"daily value for '{ROOT_ZONE_WETNESS}' on {item.date.isoformat()} "
                f"must be a number, not {type(value).__name__} (G5)"
            )
        assert isinstance(value, (int, float))
        if not _is_finite(value):
            observed[item.date] = Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"observed '{ROOT_ZONE_WETNESS}' on {item.date.isoformat()} "
                    "is not a finite number"
                ),
            )
            continue
        if value < 0 or value > 1:
            observed[item.date] = Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"observed '{ROOT_ZONE_WETNESS}' on {item.date.isoformat()} "
                    f"is outside [0, 1]: {value}"
                ),
            )
            continue
        observed[item.date] = float(value)
    return observed


def pair_root_zone_wetness(
    storage_by_day: Mapping[dt.date, float | int | Missing],
    climate: SiteClimate,
    *,
    capacity_mm: float | int | Missing,
) -> WetnessPairing:
    """Pair daily modelled relative wetness against ``SiteClimate`` CQ7."""
    modelled = compute_daily_relative_wetness(storage_by_day, capacity_mm=capacity_mm)
    observed = read_observed_root_zone_wetness(climate)
    if isinstance(observed, Missing):
        days = tuple(
            PairedWetnessDay(
                date=day,
                modelled_wetness=modelled[day],
                observed_wetness=observed,
            )
            for day in sorted(modelled)
        )
        return WetnessPairing(days=days, series_missing=observed)

    all_dates = sorted(set(modelled) | set(observed))
    paired_days = tuple(
        PairedWetnessDay(
            date=day,
            modelled_wetness=(
                modelled[day]
                if day in modelled
                else Missing(
                    reason="NO_COVERAGE",
                    detail=f"no modelled storage value on {day.isoformat()} (C5.5)",
                )
            ),
            observed_wetness=(
                observed[day]
                if day in observed
                else Missing(
                    reason="NO_COVERAGE",
                    detail=(
                        f"observed '{ROOT_ZONE_WETNESS}' has no coverage on "
                        f"{day.isoformat()} (C5.5)"
                    ),
                )
            ),
        )
        for day in all_dates
    )
    return WetnessPairing(days=paired_days, series_missing=None)
