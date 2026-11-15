"""Kinds of year (el_nino, neutral, la_nina) from the Oceanic Nino Index. PROPOSED.

See ``README.md`` in this folder.
"""

import json
from pathlib import Path
from typing import Any

from .classify import (
    SEASONS,
    KindOfYear,
    classify_agricultural_years,
    count_kinds,
    deciding_season,
)

DEFAULT_RECORD = Path(__file__).parent / "records" / "oni_v6.json"


def load_record(path: Path | str | None = None) -> dict[str, Any]:
    """Read the ONI record JSON (the committed one when ``path`` is None)."""
    with open(DEFAULT_RECORD if path is None else path, encoding="utf-8") as handle:
        return json.load(handle)


__all__ = [
    "DEFAULT_RECORD",
    "SEASONS",
    "KindOfYear",
    "classify_agricultural_years",
    "count_kinds",
    "deciding_season",
    "load_record",
]
