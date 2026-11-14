"""Soil properties by soil group, from tables a person supplies, served as a source.

Implements ``adapters.ports.SoilSlopeSource``. Decisions D48 and D49 of issue
#77 bring the soil values of the demonstration from public data, by soil group
(``K`` from the open dataset of source S9 of docs/METHODS.md; the available
water from the table by soil group of the national soil map). This module is
the machinery only: which tables, which soil groups, which quantities, units,
provenance labels and sources are all in the files a person supplies. Nothing
scientific is decided here; the code checks shape and consistency only.

Two kinds of file, both JSON (layout in adapters/README.md):

- a **soil table** (one or more): a ``source`` naming the dataset, an
  ``example_data`` flag, and per soil group a list of soil properties in the
  shape of ``contracts.inputs.SoilProperty``;
- one **soil-groups declaration**: an ``example_data`` flag and, per field of a
  case, the identifier of its soil group (declared by a person; later by the
  user, through the interface).

For a ``case_id`` and ``field_id`` the source looks up the declared soil group
and returns ``contracts.inputs.SiteSoilSlope`` with the properties every table
lists for that group, unchanged and in the order of the tables, then of their
rows. It never fills, averages or converts a value. Slope from an elevation
model is not built (D48: the elevation model and how a polygon becomes one
point are OPEN), so ``slope_length`` and ``slope_steepness`` are always missing
with ``NOT_AVAILABLE``.

The files are read again on each call. A file that is absent, cannot be read
or is malformed, or tables that disagree, give ``data=None``, ``unavailable``,
``NOT_AVAILABLE`` and a ``detail``; ``api/config.py`` checks the same files at
start-up and refuses to start on any of these. A field that is not declared
gives ``unavailable``, ``NOT_DECLARED``; a soil group that no table lists gives
``unavailable``, ``NO_COVERAGE``. A group that only some tables list gets what
those tables list, and ``SourceInfo.detail`` says how many tables do not.
It never raises for a file.

Status: PROPOSED (blueprint section 3.7), including the file layout, the
source identifier, the state reported and every ``detail`` text.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, get_args

from pydantic import ValidationError

from adapters.ports import SoilSlopeResult, SourceInfo
from contracts.inputs import SiteSoilSlope
from contracts.inputs.site_soil_slope import SoilProperty

# The contract identifier, read from the model so the two cannot differ.
CONTRACT: str = get_args(SiteSoilSlope.model_fields["contract"].annotation)[0]

# PROPOSED: the source identifier, written as ``SourceInfo.id``.
SOIL_TABLES_ID = "soil_tables"

# PROPOSED: the reasons of C3.2 this source answers with.
FILE_REASON = "NOT_AVAILABLE"  # a file absent or malformed, as the example source
NOT_DECLARED_REASON = "NOT_DECLARED"  # the field's soil group is not declared
NO_COVERAGE_REASON = "NO_COVERAGE"  # no table lists the declared soil group
SLOPE_REASON = "NOT_AVAILABLE"  # slope from an elevation model is not built

# The contract keeps the unit of a missing value (C3.1). No slope unit is
# decided (D48), so the missing slope values say so in their unit string.
SLOPE_UNIT = "OPEN"
SLOPE_DETAIL = (
    "slope from an elevation model is not built: the elevation model and how a "
    "field polygon becomes one point are OPEN (decision D48 of issue #77)"
)

DETAIL_FIELD_NOT_DECLARED = (
    "the field of the request (its case_id and field_id) has no soil group in "
    "the soil-groups declaration"
)
# The soil group is never repeated in a detail: it will be a value submitted
# by the user (OPEN 26). It travels only in ``SourceInfo.request``.
DETAIL_GROUP_NOT_LISTED = (
    "the soil group declared for the field is listed by no soil table"
)
DETAIL_IDENTIFIERS_REFUSED = (
    "the requested case_id or field_id is refused by the contract model SiteSoilSlope"
)

TABLE_KEYS = frozenset({"source", "example_data", "groups"})
GROUP_KEYS = frozenset({"soil_group", "soil_properties"})
DECLARATION_KEYS = frozenset({"example_data", "declarations"})
DECLARED_FIELD_KEYS = frozenset({"case_id", "field_id", "soil_group"})


class SoilFileError(ValueError):
    """A soil table or a declaration file is unusable. Never repeats file content."""


@dataclass(frozen=True)
class SoilTable:
    """One soil table: its dataset reference and the properties of each soil group."""

    source: str
    example_data: bool
    groups: Mapping[str, tuple[SoilProperty, ...]]


@dataclass(frozen=True)
class SoilGroupDeclarations:
    """Which soil group each field of a case belongs to (declared by a person)."""

    example_data: bool
    groups: Mapping[tuple[str, str], str]  # (case_id, field_id) -> soil group


# --- reading the files --------------------------------------------------------


def _read_json(path: Path, what: str) -> Any:
    if not path.is_file():
        raise SoilFileError(f"the {what} file does not exist")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise SoilFileError(f"the {what} file cannot be read as UTF-8 text") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SoilFileError(
            f"the {what} file is not valid JSON "
            f"(line {error.lineno}, column {error.colno})"
        ) from None


def _check_keys(document: Any, keys: frozenset[str], what: str) -> None:
    if not isinstance(document, dict):
        raise SoilFileError(f"{what} is not a JSON object")
    absent = sorted(keys - document.keys())
    if absent:
        raise SoilFileError(f"{what} has no key {', '.join(absent)}")
    unknown = len(document.keys() - keys)
    if unknown:
        # The unknown keys are content of the file: counted, never repeated.
        raise SoilFileError(f"{what} has {unknown} unknown key(s)")


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SoilFileError(f"{what} is not non-empty text")
    return value


def _flag(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise SoilFileError(f"{what} is not true or false")
    return value


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise SoilFileError(f"{what} is not a list")
    return value


def load_soil_table(path: str | os.PathLike[str]) -> SoilTable:
    """Load and check one soil table. Raises ``SoilFileError``."""
    document = _read_json(Path(path), "soil table")
    _check_keys(document, TABLE_KEYS, "the soil table")
    source = _text(document["source"], "source of the soil table")
    example_data = _flag(document["example_data"], "example_data of the soil table")
    groups: dict[str, tuple[SoilProperty, ...]] = {}
    for number, group in enumerate(_list(document["groups"], "groups"), start=1):
        where = f"group number {number} of the soil table"
        _check_keys(group, GROUP_KEYS, where)
        name = _text(group["soil_group"], f"soil_group of {where}")
        if name in groups:
            raise SoilFileError(f"{where} repeats the soil group of an earlier group")
        rows = _list(group["soil_properties"], f"soil_properties of {where}")
        if not rows:
            raise SoilFileError(f"soil_properties of {where} is empty")
        properties: list[SoilProperty] = []
        for row_number, row in enumerate(rows, start=1):
            try:
                properties.append(SoilProperty.model_validate(row))
            except ValidationError:
                raise SoilFileError(
                    f"item {row_number} of soil_properties of {where} does not "
                    "load into the contract model SoilProperty"
                ) from None
        quantities = [item.quantity for item in properties]
        if len(quantities) != len(set(quantities)):
            raise SoilFileError(f"two soil properties of {where} share one quantity")
        groups[name] = tuple(properties)
    return SoilTable(
        source=source, example_data=example_data, groups=MappingProxyType(groups)
    )


def load_soil_groups(path: str | os.PathLike[str]) -> SoilGroupDeclarations:
    """Load and check the soil-groups declaration. Raises ``SoilFileError``."""
    document = _read_json(Path(path), "soil-groups declaration")
    _check_keys(document, DECLARATION_KEYS, "the soil-groups declaration")
    example_data = _flag(
        document["example_data"], "example_data of the soil-groups declaration"
    )
    groups: dict[tuple[str, str], str] = {}
    entries = _list(document["declarations"], "declarations")
    for number, entry in enumerate(entries, start=1):
        where = f"declaration number {number}"
        _check_keys(entry, DECLARED_FIELD_KEYS, where)
        key = (
            _text(entry["case_id"], f"case_id of {where}"),
            _text(entry["field_id"], f"field_id of {where}"),
        )
        if key in groups:
            raise SoilFileError(f"{where} declares a field already declared")
        groups[key] = _text(entry["soil_group"], f"soil_group of {where}")
    return SoilGroupDeclarations(
        example_data=example_data, groups=MappingProxyType(groups)
    )


def check_tables(tables: Sequence[SoilTable]) -> None:
    """Two tables never give the same quantity for one soil group. Raises ``SoilFileError``."""
    seen: dict[tuple[str, str], int] = {}
    for number, table in enumerate(tables, start=1):
        for group, properties in table.groups.items():
            for item in properties:
                earlier = seen.setdefault((group, item.quantity), number)
                if earlier != number:
                    raise SoilFileError(
                        f"soil tables number {earlier} and {number} give the same "
                        "quantity for one soil group"
                    )


def load_soil_tables(
    paths: Iterable[str | os.PathLike[str]],
) -> tuple[SoilTable, ...]:
    """Load every table, in order, and check them together. Raises ``SoilFileError``.

    The message of a table's own problem starts with its position in ``paths``.
    """
    tables: list[SoilTable] = []
    for number, path in enumerate(paths, start=1):
        try:
            tables.append(load_soil_table(path))
        except SoilFileError as error:
            raise SoilFileError(f"soil table number {number}: {error}") from None
    if not tables:
        raise SoilFileError("no soil table is given")
    check_tables(tables)
    return tuple(tables)


# --- the source ---------------------------------------------------------------


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class SoilTableSource:
    """Soil properties of a field from its declared soil group; slope not built."""

    def __init__(
        self,
        table_paths: Sequence[str | os.PathLike[str]],
        groups_path: str | os.PathLike[str],
        *,
        source_id: str = SOIL_TABLES_ID,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if isinstance(table_paths, (str, os.PathLike)):
            raise TypeError("SoilTableSource needs a sequence of soil table paths")
        try:
            paths = tuple(table_paths)  # copied first: a generator is read once
        except TypeError:
            raise TypeError(
                "SoilTableSource needs a sequence of soil table paths"
            ) from None
        if not all(isinstance(p, (str, os.PathLike)) for p in paths):
            raise TypeError("SoilTableSource needs a sequence of soil table paths")
        if not paths:
            raise ValueError("SoilTableSource needs at least one soil table")
        if not isinstance(groups_path, (str, os.PathLike)):
            raise TypeError("SoilTableSource needs the path of the soil-groups file")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is non-empty text")
        self._table_paths = tuple(Path(p) for p in paths)
        self._groups_path = Path(groups_path)
        self._source_id = source_id
        self._now = now

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def contract(self) -> str:
        return CONTRACT

    def _info(self, request: Mapping[str, str], **fields: Any) -> SourceInfo:
        return SourceInfo(
            id=self._source_id,
            contract=CONTRACT,
            request=MappingProxyType(dict(request)),
            **fields,
        )

    def _unavailable(
        self, request: Mapping[str, str], reason: str, detail: str
    ) -> SoilSlopeResult:
        return SoilSlopeResult(
            data=None,
            source=self._info(
                request, state="unavailable", missing_reason=reason, detail=detail
            ),
        )

    def _retrieved_now(self) -> dt.datetime:
        moment = self._now()
        if not isinstance(moment, dt.datetime) or moment.utcoffset() is None:
            raise ValueError("the clock returns a timezone-aware datetime")
        return moment.astimezone(dt.UTC)

    def get_soil_slope(self, case_id: str, field_id: str) -> SoilSlopeResult:
        """The soil properties of the field's declared soil group (D48, D49)."""
        request: dict[str, str] = {"case_id": case_id, "field_id": field_id}
        try:
            declarations = load_soil_groups(self._groups_path)
        except SoilFileError as error:
            return self._unavailable(
                request, FILE_REASON, f"soil-groups declaration: {error}"
            )
        try:
            tables = load_soil_tables(self._table_paths)
        except SoilFileError as error:
            return self._unavailable(request, FILE_REASON, str(error))
        group = declarations.groups.get((case_id, field_id))
        if group is None:
            return self._unavailable(
                request, NOT_DECLARED_REASON, DETAIL_FIELD_NOT_DECLARED
            )
        request["soil_group"] = group
        listing = [table for table in tables if group in table.groups]
        if not listing:
            return self._unavailable(
                request, NO_COVERAGE_REASON, DETAIL_GROUP_NOT_LISTED
            )
        # Only the files the answer is built from: the declaration and the
        # tables that list the group.
        example_data = declarations.example_data or any(
            table.example_data for table in listing
        )
        not_listing = len(tables) - len(listing)
        detail = (
            f"{not_listing} of the {len(tables)} soil tables do not list the soil "
            "group declared for the field; their properties are not in the answer"
            if not_listing
            else None
        )
        slope = {
            "value": None,
            "unit": SLOPE_UNIT,
            "missing": {"reason": SLOPE_REASON, "detail": SLOPE_DETAIL},
        }
        try:
            data = SiteSoilSlope.model_validate(
                {
                    "contract": CONTRACT,
                    "example_data": example_data,
                    "case_id": case_id,
                    "field_id": field_id,
                    "slope_length": slope,
                    "slope_steepness": slope,
                    "soil_properties": [
                        item.model_dump()
                        for table in listing
                        for item in table.groups[group]
                    ],
                }
            )
        except ValidationError:
            return self._unavailable(request, FILE_REASON, DETAIL_IDENTIFIERS_REFUSED)
        # The dataset reference of each table that lists the group, in order.
        attribution = "; ".join(table.source for table in listing)
        if example_data:
            info = self._info(
                request, state="example", attribution=attribution, detail=detail
            )
        else:
            info = self._info(
                request,
                state="fresh",
                retrieved_at=self._retrieved_now(),
                attribution=attribution,
                detail=detail,
            )
        return SoilSlopeResult(data=data, source=info)
