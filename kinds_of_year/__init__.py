"""Kinds of year (el_nino, neutral, la_nina) from the Oceanic Nino Index. PROPOSED.

See ``README.md`` in this folder. Nothing is read at import: the ONI record is
read only by ``load_record``, from the path a caller gives. The record is not
in the repository until a person checks and signs it (D240 (5), D34, D66).
"""

import json
from pathlib import Path
from typing import Any

from .aggregate import (
    KindMean,
    MeansByKind,
    YearValue,
    mean_by_kind,
    series_from_results,
)
from .classify import (
    SEASONS,
    KindOfYear,
    classify_agricultural_years,
    count_kinds,
    deciding_season,
)


def load_record(path: Path | str) -> dict[str, Any]:
    """Read an ONI record JSON from ``path``.

    There is no default record: the record waits for a person's signature
    (D34, D66), so the caller names the file it means.
    """
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


__all__ = [
    "SEASONS",
    "KindMean",
    "KindOfYear",
    "MeansByKind",
    "YearValue",
    "classify_agricultural_years",
    "count_kinds",
    "deciding_season",
    "load_record",
    "mean_by_kind",
    "series_from_results",
]
