"""The records EP4 reads from the parameter catalogue (D46, D56). PROPOSED.

Private to ``engine/residues/``. The catalogue reaches the entry point as the
argument ``parameters``: the records exactly as ``params.catalogue.load_folder``
returns them, keyed by the path of their file (contracts/ENTRYPOINTS.md, type
row of ``parameters``). A record is found by its ``id`` and its ``scope``
through ``params.catalogue.identity``, never by its path, and its value is read
with ``params.catalogue.read_value``, as in ``engine/water/_parameters.py`` and
``engine/amg/entry.py``. Nothing here reads a file (G1).

What a lookup returns (the rows of G4 of contracts/ENTRYPOINTS.md):

- the number of the record, when its unit is the one this engine accepts and
  the number lies within what the quantity can be;
- no record with that ``id`` and ``scope``, a record whose value is ``null``,
  a record that ``read_value`` refuses (malformed, or a placeholder), two
  records with the same ``id`` and ``scope``, or a record anywhere in
  ``parameters`` without a well-formed ``id`` and ``scope`` (F3c of
  params/README.md): ``MISSING_INPUT``, naming the record by its ``id`` and
  the scope looked for, and why;
- a record in another unit (nothing is converted) or with a number outside
  what the quantity can be (a fraction outside zero to one, a negative mass,
  ratio or carbon): ``NOT_COMPUTABLE``, naming the record (PROPOSED).

The lookup is exact: a record with the empty scope is not read in place of
one that names a crop (question 5 of params/README.md stays OPEN).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from contracts.inputs.common import Missing
from contracts.results.models import UNIT_SOIL_CARBON_TREND
from params.catalogue import Missing as CatalogueMissing
from params.catalogue import identity, read_value

__all__ = [
    "AMG_INPUT_UNIT",
    "CARBON_UNIT",
    "CROP_SCOPE_KEY",
    "DIMENSIONLESS",
    "MASS_UNIT",
    "RECORDS",
    "Catalogue",
    "Record",
    "named",
]

# The units of the ledger, as the orchestrating session of #220 set them: SI,
# kilograms of dry matter per hectare and kilograms of carbon per hectare, the
# unit the yield records arrive in, so nothing is converted. Written in the
# manner of C1.1 ("ha" the hectare, "C" for carbon, "dimensionless" for a value
# without a unit); C1.1 itself lists "t", not "kg" (OPEN 3 of README.md). A
# record in any other unit is not converted.
DIMENSIONLESS = "dimensionless"
MASS_UNIT = "kg ha-1"  # of dry matter
CARBON_UNIT = "kg C ha-1"
# The unit engine/amg/entry.py requires for an annual carbon input (its
# ``STOCK_UNIT``): the unit of C1.5 without "per year". The ledger is not in it
# (OPEN 3 of README.md); kept here so the test can show the difference.
AMG_INPUT_UNIT = UNIT_SOIL_CARBON_TREND.removesuffix(" yr-1")

# Every record of this engine is read by crop, under this scope key of
# params/README.md, with the ``crop_id`` of the calendar component.
CROP_SCOPE_KEY = "crop"

# What a number of a record can be: any number that is not negative, or a
# fraction from zero to one (both included). PROPOSED.
NOT_NEGATIVE = "not_negative"
FRACTION = "fraction"


@dataclass(frozen=True)
class Record:
    """One record the ledger reads: its identifier, its unit and its bounds."""

    parameter_id: str
    unit: str
    bounds: str
    what: str  # for the README and the details; never shown to users


# The records, by the name the engine uses for each. The last five identifiers
# are PROPOSED (brief #220). The first two are the records of D129 (c) for the
# computed C of #218, with the identifiers #218 fixed (PR #229), so the ledger
# and the computed C read the same records.
RECORDS: dict[str, Record] = {
    "rusle2_residue_yield_ratio": Record(
        "rusle2_residue_yield_ratio",
        DIMENSIONLESS,
        NOT_NEGATIVE,
        "mass of aboveground residue at harvest per mass of yield (D129 (c))",
    ),
    "rusle2_crop_yield": Record(
        "rusle2_crop_yield",
        MASS_UNIT,
        NOT_NEGATIVE,
        "yield of the crop per area, dry matter (D129 (c))",
    ),
    "residue_carbon_fraction": Record(
        "residue_carbon_fraction",
        DIMENSIONLESS,
        FRACTION,
        "mass of carbon per mass of aboveground residue",
    ),
    "residue_removed_fraction": Record(
        "residue_removed_fraction",
        DIMENSIONLESS,
        FRACTION,
        "share of the aboveground residue taken off the field when the "
        "component declares the residue 'removed'",
    ),
    "root_mass_at_harvest": Record(
        "root_mass_at_harvest",
        MASS_UNIT,
        NOT_NEGATIVE,
        "mass of roots per area at harvest, dry matter",
    ),
    "root_carbon_fraction": Record(
        "root_carbon_fraction",
        DIMENSIONLESS,
        FRACTION,
        "mass of carbon per mass of roots",
    ),
    "rhizodeposit_carbon": Record(
        "rhizodeposit_carbon",
        CARBON_UNIT,
        NOT_NEGATIVE,
        "carbon of rhizodeposits per area over the component",
    ),
}


def named(name: str, crop_id: str) -> str:
    """A record as a detail names it: its ``id`` and the scope looked for (D56)."""
    return (
        f"parameter {RECORDS[name].parameter_id!r} with scope "
        f"{{{CROP_SCOPE_KEY!r}: {crop_id!r}}}"
    )


class Catalogue:
    """The records of ``parameters``, found by ``id`` and ``scope``."""

    def __init__(self, parameters: Mapping[str, dict]) -> None:
        self._index: dict[object, list[dict]] = {}
        self._malformed: list[str] = []
        for key in sorted(parameters):
            record = parameters[key]
            try:
                found = identity(record)
            except ValueError:
                self._malformed.append(key)
                continue
            self._index.setdefault(found, []).append(record)
        self.read_ids: list[str] = []

    def value(self, name: str, crop_id: str) -> float | Missing:
        """The number of one record for one crop, or why there is none."""
        spec = RECORDS[name]
        if spec.parameter_id not in self.read_ids:
            self.read_ids.append(spec.parameter_id)
        what = named(name, crop_id)
        if self._malformed:
            return _missing(
                f"{what}: it cannot be looked up: the record(s) "
                + ", ".join(repr(key) for key in self._malformed)
                + " have no well-formed 'id' and 'scope' (F3c of params/README.md)"
            )
        found = self._index.get(
            identity({"id": spec.parameter_id, "scope": {CROP_SCOPE_KEY: crop_id}}),
            [],
        )
        if not found:
            return _missing(f"{what}: no record in parameters (D56)")
        if len(found) != 1:
            return _missing(f"{what}: two records share this id and scope")
        (record,) = found
        try:
            number = read_value(record)
        except ValueError as error:
            return _missing(f"{what}: the record is not read: {error}")
        if isinstance(number, CatalogueMissing):
            return _missing(f"{what}: the record holds no value: {number.reason}")
        if record["unit"] != spec.unit:
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"{what}: its unit {record['unit']!r} is not accepted: expected "
                    f"{spec.unit!r}; nothing is converted"
                ),
            )
        if number < 0 or (spec.bounds == FRACTION and number > 1):
            expected = (
                "a fraction from zero to one"
                if spec.bounds == FRACTION
                else "a number that is not negative"
            )
            return Missing(
                reason="NOT_COMPUTABLE",
                detail=f"{what}: its value is not {expected}",
            )
        return number


def _missing(detail: str) -> Missing:
    return Missing(reason="MISSING_INPUT", detail=detail)
