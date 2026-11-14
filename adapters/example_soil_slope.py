"""The accepted soil-and-slope contract example, served as a source.

Implements ``adapters.ports.SoilSlopeSource``. It loads one JSON file into
``contracts.inputs.SiteSoilSlope`` and returns it with ``state="example"``, so
the interface shows it as example data next to the result (decision Q16 of
contracts/ENTRYPOINTS.md, issue 18).

Which file is "the accepted example" is a person's decision, so the path has
no default; the running app serves it only when ``SOIL_SLOPE_EXAMPLE_FILE``
names the file (api/config.py).

The example stands in for any field (decision D38 of issue #77): the document
served carries the ``case_id`` and ``field_id`` of the request, written into a
new model instance; ``example_data`` stays true and the state stays
``example``. Everything else is the file's: nothing is filled in, renamed or
converted, and the file is never written.

A file that is absent, cannot be read, does not load into the model, or is not
marked ``example_data: true`` gives ``data=None``, ``state="unavailable"`` and
``NOT_AVAILABLE`` with a detail. It never raises for the file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from adapters.ports import SoilSlopeResult, SourceInfo
from contracts.inputs import SiteSoilSlope

# The contract identifier, read from the model so the two cannot differ.
CONTRACT: str = get_args(SiteSoilSlope.model_fields["contract"].annotation)[0]

# PROPOSED: the source identifier of the example, written as ``SourceInfo.id``.
EXAMPLE_SOIL_SLOPE_ID = "soil_slope_example"

UNAVAILABLE_REASON = "NOT_AVAILABLE"  # the plan of unit l2/engine-runner, section 7

DETAIL_UNREADABLE = "the example file cannot be read"
DETAIL_NOT_LOADABLE = (
    "the example file does not load into the contract model SiteSoilSlope"
)
DETAIL_NOT_EXAMPLE = "the file is not marked as example data (example_data is false)"
DETAIL_IDENTIFIERS_REFUSED = (
    "the requested case_id or field_id is refused by the contract model SiteSoilSlope"
)


class ExampleSoilSlopeSource:
    """Soil and slope data from one contract example file, marked ``example``."""

    def __init__(
        self, path: str | os.PathLike[str], *, source_id: str = EXAMPLE_SOIL_SLOPE_ID
    ) -> None:
        if not isinstance(path, (str, os.PathLike)):
            raise TypeError("ExampleSoilSlopeSource needs the path of the example file")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is non-empty text")
        self._path = Path(path)
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def contract(self) -> str:
        return CONTRACT

    def _unavailable(self, detail: str) -> SoilSlopeResult:
        return SoilSlopeResult(
            data=None,
            source=SourceInfo(
                id=self._source_id,
                contract=CONTRACT,
                state="unavailable",
                missing_reason=UNAVAILABLE_REASON,
                detail=detail,
            ),
        )

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
        """The example, under the identifiers of the request (D38)."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return self._unavailable(DETAIL_UNREADABLE)
        try:
            data = SiteSoilSlope.model_validate_json(text)
        except ValidationError:
            return self._unavailable(DETAIL_NOT_LOADABLE)
        if not data.example_data:
            return self._unavailable(DETAIL_NOT_EXAMPLE)
        # A new instance, validated again, with the identifiers of the request.
        try:
            data = SiteSoilSlope.model_validate(
                {**data.model_dump(), "case_id": case_id, "field_id": field_id}
            )
        except ValidationError:
            return self._unavailable(DETAIL_IDENTIFIERS_REFUSED)
        return SoilSlopeResult(
            data=data,
            source=SourceInfo(id=self._source_id, contract=CONTRACT, state="example"),
        )
