"""Contract "ResidueLedger" (blueprint section 5). PROPOSED (blueprint section 3.7).

Producer: Engines (``engine/residues/``, EP4 ``build_residue_ledger``).
Consumer: Platform, sub-lane L2a, which copies ``annual_carbon_inputs`` into
``CarbonForcing.annual_carbon_inputs`` (``contracts/carbon_forcing/``).

What the blueprint asks the ledger to hold, as EP4 of
``contracts/ENTRYPOINTS.md`` quotes it: biomass and carbon closure, export
and retention, roots and cover kept apart. The ledger gives it per component
of the rotation and per agricultural year (C5.3):

- ``components``: one entry per component of the calendar in each cycle of
  the rotation repeated over the record (D47), the lead-in cycle of D141
  included, with the residue at harvest produced, exported and retained, as
  mass and as carbon, and the roots and the rhizodeposits apart from it;
- ``annual_carbon_inputs``: per crop, purpose and part, one series with one
  value per agricultural year, in the shape of
  ``contracts.carbon_forcing.AnnualCarbonInputSeries``, so the platform copies
  it without arithmetic of its own.

Every value can be missing with its reason (C3.1). This module fixes structure
only: it names no value, no record and no unit; the units each producer
writes are stated once in ``mass_unit`` and ``carbon_unit`` (the components)
and ``carbon_input_unit`` (the series, which may be in another unit than the
components: for EP4, D147 of #77).

The shared parts are imported, never copied: ``Value`` and ``Missing`` of
``contracts.inputs.common``, ``AnnualCarbonInputSeries`` of
``contracts.carbon_forcing`` and the closed lists ``Purpose`` and ``Residue``
of ``contracts.rotation_definition``.

Models and pure validation only. No network calls, no parameter values.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from contracts.carbon_forcing.models import AnnualCarbonInputSeries
from contracts.inputs.common import (
    ContractModel,
    DateValue,
    Missing,
    NonEmptyStr,
    Value,
)
from contracts.rotation_definition.rotation_definition import Purpose, Residue

# The values of an entry, by kind of unit. Their order is the order of the
# fields of ``LedgerComponent``.
MASS_FIELDS = (
    "aboveground_mass_produced",
    "aboveground_mass_exported",
    "aboveground_mass_retained",
    "root_mass",
)
CARBON_FIELDS = (
    "aboveground_carbon_produced",
    "aboveground_carbon_exported",
    "aboveground_carbon_retained",
    "root_carbon",
    "rhizodeposit_carbon",
)


class NotGiven(ContractModel):
    """A declared word of an entry that is not known: its ``missing`` part only.

    The same form as ``MissingManagementField`` of the rotation definition
    (D39 of #77): the key stays, so a consumer knows what is missing (C3.1).
    """

    missing: Missing


class LedgerComponent(ContractModel):
    """One component of the calendar, in one cycle of the repeated rotation.

    ``purpose`` and ``residue_management`` are copied from the rotation
    definition, so a cover crop stays apart from a grain crop. ``harvest`` is
    the end date of the component in this cycle and ``ag_year`` the
    agricultural year it falls in (C5.3); both are missing together.

    ``cycle`` is the index of the cycle: the first is 0. -1 is the lead-in,
    the cycle before the first, laid out when one of its components ends
    inside the record (D141 of #77; point 13 and ``LEAD_IN`` of
    ``engine/calendar/repeat.py``). The ledger admits it by D-LEAD-IN, and
    nothing lower: no cycle comes before the lead-in.
    """

    component_id: NonEmptyStr
    crop_id: NonEmptyStr
    cycle: int = Field(ge=-1)  # the first cycle is 0; -1 is the lead-in (D141)
    purpose: Purpose | NotGiven
    residue_management: Residue | NotGiven
    harvest: DateValue
    ag_year: int | None  # null exactly when the harvest date is missing
    aboveground_mass_produced: Value
    aboveground_mass_exported: Value
    aboveground_mass_retained: Value
    aboveground_carbon_produced: Value
    aboveground_carbon_exported: Value
    aboveground_carbon_retained: Value
    root_mass: Value
    root_carbon: Value
    rhizodeposit_carbon: Value

    @model_validator(mode="after")
    def _year_with_harvest(self) -> LedgerComponent:
        if (self.harvest.date is None) != (self.ag_year is None):
            raise ValueError(
                f"component {self.component_id!r} cycle {self.cycle}: ag_year is "
                "given exactly when the harvest date is given"
            )
        return self


class ResidueLedger(ContractModel):
    """The residue ledger of one rotation of one field."""

    contract: Literal["residue_ledger"]
    example_data: bool
    case_id: NonEmptyStr
    field_id: NonEmptyStr  # replaced by the field identity contract (D19 of #77)
    rotation_id: NonEmptyStr
    first_ag_year: int | None
    last_ag_year: int | None  # inclusive
    years_missing: Missing | None = None  # why no agricultural year is laid out
    mass_unit: NonEmptyStr  # every mass value of the ledger is in this unit
    carbon_unit: NonEmptyStr  # every carbon value of the components is in this unit
    carbon_input_unit: (
        NonEmptyStr  # every series of annual_carbon_inputs is in this unit
    )
    components: list[LedgerComponent]
    annual_carbon_inputs: list[AnnualCarbonInputSeries]

    @model_validator(mode="after")
    def _consistent(self) -> ResidueLedger:
        self._check_years()
        self._check_components()
        self._check_series()
        return self

    def _check_years(self) -> None:
        given = (self.first_ag_year is not None, self.last_ag_year is not None)
        if given == (True, True):
            if self.years_missing is not None:
                raise ValueError(
                    "years: the ledger holds its agricultural years or the reason "
                    "it has none, never both (C3.1)"
                )
            if self.last_ag_year < self.first_ag_year:  # type: ignore[operator]
                raise ValueError("years: last_ag_year is before first_ag_year")
            return
        if given != (False, False):
            raise ValueError("years: first_ag_year and last_ag_year come together")
        if self.years_missing is None:
            raise ValueError(
                "years: a ledger without agricultural years carries the reason "
                "in years_missing (C3.1)"
            )
        if self.components or self.annual_carbon_inputs:
            raise ValueError(
                "years: a ledger without agricultural years lists no component "
                "and no series"
            )

    def _check_components(self) -> None:
        keys = Counter((item.component_id, item.cycle) for item in self.components)
        repeated = sorted(key for key, count in keys.items() if count > 1)
        if repeated:
            component_id, cycle = repeated[0]
            raise ValueError(
                f"components: component {component_id!r} appears twice in cycle {cycle}"
            )
        for item in self.components:
            for fields, unit, kind in (
                (MASS_FIELDS, self.mass_unit, "mass_unit"),
                (CARBON_FIELDS, self.carbon_unit, "carbon_unit"),
            ):
                for name in fields:
                    if getattr(item, name).unit != unit:
                        raise ValueError(
                            f"component {item.component_id!r} cycle {item.cycle}: "
                            f"{name} is not in the {kind} of the ledger"
                        )

    def _check_series(self) -> None:
        quantities = Counter(series.quantity for series in self.annual_carbon_inputs)
        repeated = sorted(q for q, count in quantities.items() if count > 1)
        if repeated:
            raise ValueError(
                f"annual_carbon_inputs: the quantity identifier {repeated[0]!r} "
                "appears more than once"
            )
        crops = {item.crop_id for item in self.components}
        for series in self.annual_carbon_inputs:
            what = f"annual_carbon_inputs {series.quantity!r}"
            if (series.first_ag_year, series.last_ag_year) != (
                self.first_ag_year,
                self.last_ag_year,
            ):
                raise ValueError(
                    f"{what}: first_ag_year and last_ag_year are those of the ledger"
                )
            if series.unit != self.carbon_input_unit:
                raise ValueError(
                    f"{what}: is not in the carbon_input_unit of the ledger"
                )
            if series.origin not in crops:
                raise ValueError(
                    f"{what}: its origin is not the crop of any component of the ledger"
                )
