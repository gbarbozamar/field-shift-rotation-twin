"""EP6 ``run_rothc``: the RothC monthly turnover run on a ``CarbonForcing``, returned as a ``CarbonBalance``. PROPOSED.

Unit ``l2/rothc-common-forcings`` (issue #176). The entry point of
contracts/ENTRYPOINTS.md EP6::

    run_rothc(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance

What it builds (README.md of this folder, section "EP6 run_rothc"):

- The standard RothC of D64 (the 1990 formulation), one step per calendar
  month of the horizon (``start`` equals ``end``), of length one over twelve
  of a ``yr`` (C1.1).
- Inputs from the forcing: the monthly rainfall, open-pan evaporation (or
  potential evapotranspiration, divided by the pan factor, when no pan
  series is given) and mean air temperature in ``climate``; the clay content
  in ``soil_properties``; the soil cover in ``soil_cover``; the five pools
  of the starting state in ``starting_state``; the soil depth of the
  forcing; every series of ``carbon_inputs``, by its ``origin``. Their
  identifiers are PROPOSED in ``FORCING_QUANTITIES``; the vocabulary of the
  forcing is OPEN (contracts/carbon_forcing/README.md).
- Every constant is read from ``parameters`` with the pure readers of
  ``params.catalogue`` (``identity``, ``read_value``; G1, D46, D56). The
  identifiers are those the core proposes (README.md, "Constants a person
  has to transcribe"; the values there are transcribed by a person and
  checked, in force under D34). No value of the method is written here.
- The core of ``pools.py``, ``modifiers.py`` and ``trend.py`` does every
  computation. This module only looks values up, checks the units the core
  cannot see, lays out the months and writes the contract.

What is not computed is missing with its reason (G4), never zero: a
parameter without a record, or whose record holds no value, is
``MISSING_INPUT`` naming its ``id`` and scope (D56); a quantity the forcing
does not carry is ``MISSING_INPUT`` naming it; a unit that is not accepted
is ``NOT_COMPUTABLE`` naming it (Q11 is OPEN; the core makes the same
choice). Once a month is missing every later month is missing (the core's
``run``).

Raises ``TypeError`` when ``forcing`` is not a ``CarbonForcing`` or
``parameters`` is not a ``dict[str, dict]`` (G5). Pure (G1): no file, no
network, no clock, no argument is changed.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contracts.carbon_balance import CarbonBalance, FlowSeries, StepValue, StockSeries
from contracts.carbon_forcing import CarbonForcing
from contracts.carbon_forcing.models import MonthlySeries
from contracts.inputs.common import Missing as InputMissing
from contracts.inputs.common import Value
from contracts.inputs.site_climate import YearMonth
from contracts.results.models import (
    DIRECTION_OF,
    TREND_COMPUTATIONS,
    UNIT_SOIL_CARBON_TREND,
    SoilCarbonTrend,
)
from contracts.results.models import Missing as ResultMissing
from params.catalogue import Missing as CatalogueMissing
from params.catalogue import identity, read_value

from ._numbers import NumberOrMissing, describe_missing, is_missing
from .equilibrium import equilibrium_state
from .modifiers import (
    advance_deficit,
    bare_soil_deficit,
    clay_partition,
    cover_modifier,
    maximum_tsmd,
    moisture_modifier,
    rate_modifying_factor,
    temperature_modifier,
)
from .pools import (
    InputSplit,
    MonthInput,
    PoolState,
    inert_organic_matter,
    initial_state,
    input_additions,
    plant_fractions,
    run,
)
from .trend import trend_measures

__all__ = [
    "CARBON_MODEL",
    "FORCING_QUANTITIES",
    "PARAMETERS",
    "POOL_QUANTITIES",
    "STOCK_UNIT",
    "VARIANT",
    "run_rothc",
]

# --- identifiers and choices, each PROPOSED (README.md, "EP6 run_rothc") ----------

CARBON_MODEL = "rothc"  # D1 of issue #77
# D64 names the reference: the 1990 standard formulation, "RothC-26.3". The
# vocabulary of ``variant`` is OPEN (Q14 (d) of contracts/ENTRYPOINTS.md).
VARIANT = "rothc_26_3"
STEP_UNIT = "yr"  # C1.1: one month is one over twelve of a year
_PER = "-1"
STOCK_UNIT = UNIT_SOIL_CARBON_TREND.removesuffix(f" {STEP_UNIT}{_PER}")  # t C ha-1
DIMENSIONLESS = "dimensionless"  # C1.1
MONTHS = len(calendar.month_name[1:])

# What run_rothc reads from the forcing: (part of CarbonForcing, quantity).
# The identifiers of the climate and soil quantities follow the reading of
# the nine data of the 2014 users guide (issue #176, the interface
# developer's comment); they stay PROPOSED until a person decides the
# vocabulary (contracts/carbon_forcing/README.md, items 1 and 8).
FORCING_QUANTITIES: dict[str, tuple[str, str]] = {
    "rainfall": ("climate", "rainfall"),
    "pan_evaporation": ("climate", "open_pan_evaporation"),
    "potential_evapotranspiration": ("climate", "potential_evapotranspiration"),
    "temperature": ("climate", "mean_temperature"),
    "clay_content": ("soil_properties", "clay_content"),
    "soil_cover": ("soil_cover", "soil_cover_state"),
    "dpm_pool": ("starting_state", "rothc_dpm_pool"),
    "rpm_pool": ("starting_state", "rothc_rpm_pool"),
    "bio_pool": ("starting_state", "rothc_bio_pool"),
    "hum_pool": ("starting_state", "rothc_hum_pool"),
    "iom_pool": ("starting_state", "rothc_iom_pool"),
    "total_carbon": ("starting_state", "soil_organic_carbon"),
}

# The parameters, with the identifiers the core proposes (README.md) and how
# the unit of each record is read: "dimensionless" (must be that text, C1.1),
# "unit" (passed to the core as it is, to be compared with the unit of an
# input), "per" (written "X-1"; X goes to the core, which compares it with
# the unit of an input) or "per:yr" (written "yr-1": the rate constants are
# per year and the monthly step divides them by the months of a year).
PARAMETERS: dict[str, tuple[str, str]] = {
    "dpm_rate_constant": ("rothc_dpm_rate_constant", "per:yr"),
    "rpm_rate_constant": ("rothc_rpm_rate_constant", "per:yr"),
    "bio_rate_constant": ("rothc_bio_rate_constant", "per:yr"),
    "hum_rate_constant": ("rothc_hum_rate_constant", "per:yr"),
    "temperature_maximum": ("rothc_temperature_modifier_maximum", "dimensionless"),
    "temperature_exponent_scale": ("rothc_temperature_exponent_scale", "unit"),
    "temperature_offset": ("rothc_temperature_offset", "unit"),
    "tsmd_intercept": ("rothc_tsmd_intercept", "unit"),
    "tsmd_clay_coefficient": ("rothc_tsmd_clay_coefficient", "unit"),
    "tsmd_clay_squared_coefficient": ("rothc_tsmd_clay_squared_coefficient", "unit"),
    "tsmd_reference_depth": ("rothc_tsmd_reference_depth", "unit"),
    "moisture_threshold": ("rothc_moisture_threshold_fraction", "dimensionless"),
    "moisture_minimum": ("rothc_moisture_minimum_factor", "dimensionless"),
    "pan_factor": ("rothc_pan_evaporation_factor", "dimensionless"),
    "cover_vegetated": ("rothc_cover_factor_vegetated", "dimensionless"),
    "cover_bare": ("rothc_cover_factor_bare", "dimensionless"),
    "partition_scale": ("rothc_partition_scale", "dimensionless"),
    "partition_intercept": ("rothc_partition_intercept", "dimensionless"),
    "partition_clay_coefficient": ("rothc_partition_clay_coefficient", "dimensionless"),
    "partition_clay_decay": ("rothc_partition_clay_decay", "per"),
    "bio_share": ("rothc_bio_share_of_formed", "dimensionless"),
    "iom_coefficient": ("rothc_iom_coefficient", "dimensionless"),
    "iom_exponent": ("rothc_iom_exponent", "dimensionless"),
    # D223 of issue #77: the divisor of the maximum deficit in a bare month
    # (BareSMD, p. 10 of the description), scope {}. Read only where a bare
    # month dries the soil (modifiers.bare_soil_deficit).
    "bare_tsmd_divisor": ("rothc_bare_tsmd_divisor", "dimensionless"),
}
# The composition of the incoming material, one set of records per origin of
# a carbon input, all dimensionless: the DPM:RPM ratio of plant material, or
# the three shares of an organic amendment (farmyard manure enters HUM as
# well). The origin is written under this scope key (PROPOSED; engine/amg/
# chooses the same key).
INPUT_PARAMETERS: dict[str, str] = {
    "input_dpm_rpm_ratio": "rothc_input_dpm_rpm_ratio",
    "input_dpm_fraction": "rothc_input_dpm_fraction",
    "input_rpm_fraction": "rothc_input_rpm_fraction",
    "input_hum_fraction": "rothc_input_hum_fraction",
}
ORIGIN_SCOPE_KEY = "crop"

# The series of the balance.
POOL_QUANTITIES = {
    "total": "soil_organic_carbon",
    "dpm": "rothc_dpm_pool",
    "rpm": "rothc_rpm_pool",
    "bio": "rothc_bio_pool",
    "hum": "rothc_hum_pool",
    "iom": "rothc_iom_pool",
}
FLOW_QUANTITIES = {
    "carbon_input": "rothc_carbon_input",
    "co2": "rothc_co2_carbon",
}
# The active pools of the turnover, in the order of pools.py.
ACTIVE_POOLS = ("dpm", "rpm", "bio", "hum")

NO_RANGE = (
    "run_rothc computes no uncertainty range (Q6 of contracts/ENTRYPOINTS.md, C2.3)"
)
# D224 of issue #77: the label of a RothC value, word for word as the decision
# gives it. The source of every value that holds a number starts with it.
LABEL = (
    "RothC-26.3, the 1990 standard formulation (D64); monthly FAO-56 reference "
    "evapotranspiration as the evaporative demand instead of open-pan "
    "evaporation × 0.75 (an adaptation, D80); Rothamsted parameters, not "
    "calibrated for the country of the site; starting pools from an equilibrium "
    "initialisation convention, with no claim that the soil is at equilibrium "
    "(D80); inert pool from Falloon et al. (1998), \"a very rough "
    "approximation\"; surface residue under no-till entered as a soil input."
)
EQUILIBRIUM = (
    "derived by engine.rothc.run_rothc by the inverse mode of D218 of issue #77: "
    "the inert pool from starting_state 'soil_organic_carbon' by the form of p. "
    "16 of the model description; the active pools as the state that the "
    "monthly forcing of this horizon, cycled, returns to (its analytic fixed "
    "point, D219), with every carbon input scaled once by (SOC - IOM) / "
    "(SOC_sim - IOM) (GSOCseq Technical Manual eq. 5.1, after Smith et al. "
    "2005) so that the five pools hold the starting total. An equilibrium "
    "initialisation convention, not a claim about the soil (D80)"
)
NO_CYCLES = (
    "the positions of the whole rotation cycles in the series of stocks: "
    "CarbonForcing carries no rotation cycle, so mean_over_cycles has no input "
    "(engine/rothc/README.md, OPEN)"
)

Scope = tuple[tuple[str, str], ...]


# --- checks of the caller (G5) ---------------------------------------------------


def _check_arguments(forcing: object, parameters: object) -> None:
    if not isinstance(forcing, CarbonForcing):
        raise TypeError(
            "forcing: expected a CarbonForcing of contracts.carbon_forcing, "
            f"got {type(forcing).__name__} (G3, G5)"
        )
    if not isinstance(parameters, dict) or not all(
        isinstance(key, str) and isinstance(record, dict)
        for key, record in parameters.items()
    ):
        raise TypeError(
            "parameters: expected dict[str, dict] (the catalogue as loaded): every "
            "key is the path of a record file and every value a record (G3, G5)"
        )


# --- the parameter catalogue (D46, D56) --------------------------------------------


def _scope_text(scope: Scope) -> str:
    return json.dumps(dict(scope), sort_keys=True)


def _named(parameter_id: str, scope: Scope) -> str:
    return f"parameter '{parameter_id}' with scope {_scope_text(scope)}"


def _not_computable_unit(detail: str) -> "_Parameter":
    return _Parameter(
        ResultMissing(reason="NOT_COMPUTABLE", detail=detail),
        "",
    )


@dataclass(frozen=True)
class _Parameter:
    value: float | ResultMissing
    unit: str  # the unit the core is given; empty when the value is missing


class _Catalogue:
    """The records of ``parameters``, found by ``id`` and ``scope`` (never by path).

    The lookup is exact, as in engine/water/_parameters.py: a record with the
    empty scope is not read for one that names a scope, nor the other way
    round (question 5 of params/README.md). A record without a well-formed
    ``id`` and ``scope`` could be a record of any parameter, so while there is
    one, no parameter is read (F3c of params/README.md).
    """

    def __init__(self, parameters: Mapping[str, dict]) -> None:
        self._index: dict[object, list[dict]] = {}
        self._malformed: list[str] = []
        for name in sorted(parameters):
            try:
                key = identity(parameters[name])
            except ValueError:
                self._malformed.append(name)
                continue
            self._index.setdefault(key, []).append(parameters[name])
        self.used: list[str] = []

    def _record(self, parameter_id: str, scope: Scope) -> dict | None | ResultMissing:
        if parameter_id not in self.used:
            self.used.append(parameter_id)
        named = _named(parameter_id, scope)
        if self._malformed:
            return ResultMissing(
                reason="MISSING_INPUT",
                detail=(
                    f"{named}: it cannot be looked up: the record(s) "
                    + ", ".join(repr(key) for key in self._malformed)
                    + " have no well-formed 'id' and 'scope' (F3c of params/README.md)"
                ),
            )
        found = self._index.get(identity({"id": parameter_id, "scope": dict(scope)}), [])
        if not found:
            return ResultMissing(
                reason="MISSING_INPUT", detail=f"{named}: no record in parameters (D56)"
            )
        if len(found) != 1:
            return ResultMissing(
                reason="MISSING_INPUT",
                detail=f"{named}: two records share this id and scope",
            )
        return found[0]

    def read(self, name: str, scope: Scope = ()) -> _Parameter:
        """A parameter of ``PARAMETERS``: its value and the unit the core is given."""
        parameter_id, how = PARAMETERS[name]
        record = self._record(parameter_id, scope)
        if isinstance(record, ResultMissing):
            return _Parameter(record, "")
        try:
            value = read_value(record)
        except ValueError as error:
            return _Parameter(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=f"{_named(parameter_id, scope)}: the record is not read: {error}",
                ),
                "",
            )
        if isinstance(value, CatalogueMissing):
            return _Parameter(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"{_named(parameter_id, scope)}: the record holds no value: "
                        f"{value.reason}"
                    ),
                ),
                "",
            )
        unit = record["unit"]
        named = _named(parameter_id, scope)
        if how == "unit":
            return _Parameter(value, unit)
        if how == "dimensionless":
            if unit == DIMENSIONLESS:
                return _Parameter(value, unit)
            return _not_computable_unit(
                f"{named}: its unit '{unit}' is not accepted: expected "
                f"'{DIMENSIONLESS}' (C1.1)"
            )
        # "per" or "per:yr": the unit is written "X-1" and X is what follows.
        if not unit.endswith(_PER) or unit == _PER:
            return _not_computable_unit(
                f"{named}: its unit '{unit}' is not accepted: expected a unit per a "
                f"unit, written 'X{_PER}' (C1.1)"
            )
        base = unit.removesuffix(_PER)
        if how == "per":
            return _Parameter(value, base)
        required = how.removeprefix("per:")  # "per:yr" -> "yr"
        if base == required:
            return _Parameter(value, base)
        return _not_computable_unit(
            f"{named}: its unit is per '{base}'; the monthly step divides the rate "
            f"constants by the months of a year, so it must be per '{required}' (C1.1)"
        )

    def read_input(self, name: str, scope: Scope) -> _Parameter:
        """A parameter of ``INPUT_PARAMETERS`` (the composition of an origin)."""
        parameter_id = INPUT_PARAMETERS[name]
        record = self._record(parameter_id, scope)
        if isinstance(record, ResultMissing):
            return _Parameter(record, "")
        try:
            value = read_value(record)
        except ValueError as error:
            return _Parameter(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=f"{_named(parameter_id, scope)}: the record is not read: {error}",
                ),
                "",
            )
        if isinstance(value, CatalogueMissing):
            return _Parameter(
                ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"{_named(parameter_id, scope)}: the record holds no value: "
                        f"{value.reason}"
                    ),
                ),
                "",
            )
        if record["unit"] == DIMENSIONLESS:
            return _Parameter(value, record["unit"])
        return _not_computable_unit(
            f"{_named(parameter_id, scope)}: its unit '{record['unit']}' is not "
            f"accepted: expected '{DIMENSIONLESS}' (C1.1)"
        )


# --- the forcing ----------------------------------------------------------------------


def _absent(name: str) -> ResultMissing:
    part, quantity = FORCING_QUANTITIES[name]
    return ResultMissing(
        reason="MISSING_INPUT",
        detail=f"quantity '{quantity}' has no item in {part} of the forcing",
    )


def _number(item_value: float | None, missing: InputMissing | None) -> NumberOrMissing:
    return missing if item_value is None else item_value


def _monthly(
    forcing: CarbonForcing, name: str
) -> tuple[dict[tuple[int, int], NumberOrMissing] | ResultMissing, str]:
    """The values of a monthly series by (year, month), and its unit."""
    part, quantity = FORCING_QUANTITIES[name]
    parts: dict[str, Sequence[MonthlySeries]] = {
        "climate": forcing.climate,
        "soil_cover": forcing.soil_cover,
    }
    for series in parts[part]:
        if series.quantity == quantity:
            return (
                {
                    (item.year, item.month): _number(item.value, item.missing)
                    for item in series.months
                },
                series.unit,
            )
    return _absent(name), ""


def _soil(forcing: CarbonForcing, name: str) -> tuple[NumberOrMissing, str]:
    """A soil property: its value (or why not) and its unit."""
    quantity = FORCING_QUANTITIES[name][1]
    for item in forcing.soil_properties:
        if item.quantity == quantity:
            return _number(item.value, item.missing), item.unit
    return _absent(name), ""


def _starting(forcing: CarbonForcing, name: str) -> NumberOrMissing:
    """A starting stock in ``STOCK_UNIT``, or why it is not accepted."""
    quantity = FORCING_QUANTITIES[name][1]
    for item in forcing.starting_state:
        if item.quantity == quantity:
            if item.unit != STOCK_UNIT:
                return ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"starting_state '{quantity}' is in '{item.unit}'; run_rothc "
                        f"accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
            return _number(item.value, item.missing)
    return _absent(name)


def _soil_depth(forcing: CarbonForcing) -> NumberOrMissing:
    depth = forcing.soil_depth
    if depth.value is None:
        if depth.missing is not None:
            return ResultMissing(
                reason="MISSING_INPUT",
                detail=describe_missing("the soil depth of the forcing", depth.missing),
            )
        return ResultMissing(
            reason="MISSING_INPUT",
            detail="the soil depth of the forcing is missing",
        )
    return depth.value


def _index(month: YearMonth) -> int:
    return month.year * MONTHS + month.month - 1


def _month(index: int) -> YearMonth:
    return YearMonth(year=index // MONTHS, month=index % MONTHS + 1)


def _months(forcing: CarbonForcing) -> list[YearMonth]:
    """One month per month of the horizon, in order."""
    start = _index(forcing.horizon.start)
    end = _index(forcing.horizon.end)
    return [_month(i) for i in range(start, end + 1)]


def _at(
    values: dict[tuple[int, int], NumberOrMissing] | ResultMissing,
    month: YearMonth,
    name: str,
) -> NumberOrMissing:
    if is_missing(values):
        return values
    return values.get((month.year, month.month), _absent(name))


# --- the run -----------------------------------------------------------------------------


def _composition(catalogue: _Catalogue, origin: str) -> InputSplit | ResultMissing:
    """The composition of the material of one origin of a carbon input.

    An origin with a DPM:RPM ratio record is plant material (the shares
    follow from the ratio, ``plant_fractions``); one with the three share
    records is an organic amendment that enters HUM as well (farmyard
    manure). When neither route is complete, every parameter of the two
    routes that is missing is named.
    """
    scope = ((ORIGIN_SCOPE_KEY, origin),)
    ratio = catalogue.read_input("input_dpm_rpm_ratio", scope)
    if not is_missing(ratio.value):
        return plant_fractions(dpm_rpm_ratio=ratio.value)
    shares = {
        name: catalogue.read_input(name, scope)
        for name in INPUT_PARAMETERS
        if name != "input_dpm_rpm_ratio"
    }
    if all(not is_missing(parameter.value) for parameter in shares.values()):
        return InputSplit(
            dpm=shares["input_dpm_fraction"].value,
            rpm=shares["input_rpm_fraction"].value,
            bio=0.0,
            hum=shares["input_hum_fraction"].value,
        )
    missing = [
        describe_missing(_named(INPUT_PARAMETERS[name], scope), parameter.value)
        for name, parameter in (
            (name, ratio if name == "input_dpm_rpm_ratio" else shares[name])
            for name in INPUT_PARAMETERS
        )
        if is_missing(parameter.value)
    ]
    return ResultMissing(reason="MISSING_INPUT", detail="; ".join(missing))


def _pan_values(
    forcing: CarbonForcing, pan_factor: NumberOrMissing
) -> tuple[dict[tuple[int, int], NumberOrMissing] | ResultMissing, str]:
    """The open-pan evaporation by month: the pan series, or PET over the pan factor.

    The description's route when pan evaporation is unavailable: potential
    evapotranspiration divided by the pan factor stands in for it (issue
    #176, row 11). A pan series that is given is used as it is.
    """
    pan, pan_unit = _monthly(forcing, "pan_evaporation")
    if not is_missing(pan):
        return pan, pan_unit
    pet, pet_unit = _monthly(forcing, "potential_evapotranspiration")
    if is_missing(pet) or is_missing(pan_factor):
        return pan, pan_unit
    return (
        {
            key: (
                value / pan_factor
                if not is_missing(value)
                else ResultMissing(
                    reason="MISSING_INPUT",
                    detail=(
                        f"the open-pan evaporation of {key[0]}-{key[1]:02d} stands in "
                        "by the potential evapotranspiration over the pan factor, and "
                        + describe_missing("that evapotranspiration", value)
                    ),
                )
            )
            for key, value in pet.items()
        },
        pet_unit,
    )


def _carries(forcing: CarbonForcing, name: str) -> bool:
    quantity = FORCING_QUANTITIES[name][1]
    return any(item.quantity == quantity for item in forcing.starting_state)


def _inverse_mode(forcing: CarbonForcing) -> bool:
    """D218: the starting state carries only the total soil organic carbon.

    Then the five pools come from the equilibrium of the cycle. When it
    carries any pool, the pools are read from it as before (a pool it does
    not carry is missing and named).
    """
    pools = ("dpm_pool", "rpm_pool", "bio_pool", "hum_pool", "iom_pool")
    return _carries(forcing, "total_carbon") and not any(
        _carries(forcing, name) for name in pools
    )


def _initial_iom(
    forcing: CarbonForcing, catalogue: _Catalogue
) -> tuple[NumberOrMissing, bool]:
    """The inert stock: measured (``starting_state``) or from the total carbon.

    The second item says whether the value was derived by the form of the
    description (p. 16; then the stock series carries ``DERIVED``) or taken
    from the forcing (then ``DECLARED``). When the forcing names neither the
    inert pool nor the total, both are named.
    """
    given = _starting(forcing, "iom_pool")
    if not is_missing(given):
        return given, False
    total = _starting(forcing, "total_carbon")
    if is_missing(total):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=(
                f"{describe_missing('the inert pool in starting_state', given)}; "
                f"{describe_missing('the total carbon to derive it from', total)}"
            ),
        ), False
    derived = inert_organic_matter(
        total_organic_carbon=total,
        coefficient=catalogue.read("iom_coefficient").value,
        exponent=catalogue.read("iom_exponent").value,
    )
    if is_missing(derived):
        return ResultMissing(
            reason="MISSING_INPUT",
            detail=(
                f"{describe_missing('the inert pool in starting_state', given)}; "
                + describe_missing("the form from the total organic carbon", derived)
            ),
        ), True
    return derived, True


def _month_inputs(
    forcing: CarbonForcing,
    catalogue: _Catalogue,
    months: list[YearMonth],
) -> list[MonthInput]:
    """The input of each month: its additions and its combined rate factor.

    Every parameter is read once; every quantity of the forcing is read
    once; the months then only combine them.
    """
    # The soil, once: clay content and depth.
    clay, clay_unit = _soil(forcing, "clay_content")
    depth = _soil_depth(forcing)
    maximum = maximum_tsmd(
        clay_content=clay,
        clay_content_unit=clay_unit,
        depth=depth,
        depth_unit=forcing.soil_depth.unit,
        intercept=catalogue.read("tsmd_intercept").value,
        intercept_unit=catalogue.read("tsmd_intercept").unit,
        clay_coefficient=catalogue.read("tsmd_clay_coefficient").value,
        clay_coefficient_unit=catalogue.read("tsmd_clay_coefficient").unit,
        clay_squared_coefficient=catalogue.read("tsmd_clay_squared_coefficient").value,
        clay_squared_coefficient_unit=catalogue.read(
            "tsmd_clay_squared_coefficient"
        ).unit,
        reference_depth=catalogue.read("tsmd_reference_depth").value,
        reference_depth_unit=catalogue.read("tsmd_reference_depth").unit,
    )
    # The climate series and the factors of the water balance, once.
    temperatures, temperature_unit = _monthly(forcing, "temperature")
    rainfall, rainfall_unit = _monthly(forcing, "rainfall")
    pan_factor = catalogue.read("pan_factor")
    pan, pan_unit = _pan_values(forcing, pan_factor.value)
    cover, cover_unit = _monthly(forcing, "soil_cover")
    if not is_missing(cover) and cover_unit != DIMENSIONLESS:
        cover = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"soil_cover '{FORCING_QUANTITIES['soil_cover'][1]}' is in "
                f"'{cover_unit}'; run_rothc expects '{DIMENSIONLESS}' (C1.1) and "
                "converts nothing"
            ),
        )
    maximum_unit = catalogue.read("tsmd_intercept").unit
    divisor = catalogue.read("bare_tsmd_divisor").value
    # The carbon inputs, once: every series of the forcing, its composition
    # by origin, and its values by month.
    compositions: dict[str, InputSplit | ResultMissing] = {
        series.quantity: _composition(catalogue, series.origin)
        for series in forcing.carbon_inputs
    }
    inputs: dict[str, dict[tuple[int, int], NumberOrMissing]] = {}
    for series in forcing.carbon_inputs:
        values = {
            (item.year, item.month): _number(item.value, item.missing)
            for item in series.months
        }
        if series.unit != STOCK_UNIT:
            values = {
                key: ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"carbon_inputs '{series.quantity}' is in '{series.unit}'; "
                        f"run_rothc accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
                for key in values
            }
        inputs[series.quantity] = values

    month_inputs: list[MonthInput] = []
    # The deficit starts at field capacity on the first month (p. 12).
    deficit: NumberOrMissing = 0.0
    for month in months:
        temperature_factor = temperature_modifier(
            temperature=_at(temperatures, month, "temperature"),
            temperature_unit=temperature_unit,
            maximum=catalogue.read("temperature_maximum").value,
            exponent_scale=catalogue.read("temperature_exponent_scale").value,
            exponent_scale_unit=catalogue.read("temperature_exponent_scale").unit,
            offset=catalogue.read("temperature_offset").value,
            offset_unit=catalogue.read("temperature_offset").unit,
        )
        if not is_missing(deficit):
            before = deficit
            deficit = advance_deficit(
                deficit=deficit,
                maximum=maximum,
                maximum_unit=maximum_unit,
                rainfall=_at(rainfall, month, "rainfall"),
                rainfall_unit=rainfall_unit,
                pan_evaporation=_at(pan, month, "pan_evaporation"),
                pan_evaporation_unit=pan_unit,
                pan_factor=pan_factor.value,
            )
            # D223: in a bare month the deficit is held at the bare limit.
            deficit = bare_soil_deficit(
                deficit_before=before,
                advanced=deficit,
                maximum=maximum,
                cover_state=_at(cover, month, "soil_cover"),
                divisor=divisor,
            )
        moisture_factor = moisture_modifier(
            deficit=deficit,
            maximum=maximum,
            threshold_fraction=catalogue.read("moisture_threshold").value,
            minimum=catalogue.read("moisture_minimum").value,
        )
        cover_factor = cover_modifier(
            cover_state=_at(cover, month, "soil_cover"),
            vegetated_factor=catalogue.read("cover_vegetated").value,
            bare_factor=catalogue.read("cover_bare").value,
        )
        additions = input_additions(
            # A series of the forcing covers every month of the horizon, so
            # the value of the month is always there (CarbonForcing checks it).
            carbon_inputs={
                quantity: values[(month.year, month.month)]
                for quantity, values in inputs.items()
            },
            compositions=compositions,
        )
        month_inputs.append(
            MonthInput(
                additions=additions,
                rate_modifying_factor=rate_modifying_factor(
                    temperature_factor=temperature_factor,
                    moisture_factor=moisture_factor,
                    cover_factor=cover_factor,
                ),
            )
        )
    return month_inputs


# --- the contract ----------------------------------------------------------------------


def _input_missing(missing: ResultMissing | InputMissing) -> InputMissing:
    return InputMissing(reason=missing.reason, detail=missing.detail)


def _initial(value: float | ResultMissing, provenance: str, source: str) -> Value:
    if is_missing(value):
        return Value(value=None, unit=STOCK_UNIT, missing=_input_missing(value))
    return Value(
        value=value,
        unit=STOCK_UNIT,
        provenance=provenance,
        source=source,
        range_missing=InputMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def _step_values(
    months: list[YearMonth], values: list[float | ResultMissing]
) -> list[StepValue]:
    return [
        StepValue(start=month, end=month, value=None, missing=_input_missing(value))
        if is_missing(value)
        else StepValue(start=month, end=month, value=value)
        for month, value in zip(months, values, strict=True)
    ]


def _header(quantity: str, values: list[float | ResultMissing], source: str) -> dict:
    present = any(not is_missing(value) for value in values)
    header: dict = {"quantity": quantity, "unit": STOCK_UNIT}
    if present:
        header.update(
            provenance="SIMULATED",  # C4.1: produced by running a model through time steps
            source=source,
            range_missing=InputMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
        )
    return header


def _trend(
    computation: str, value: float | ResultMissing, source: str
) -> SoilCarbonTrend:
    indicator = "soil_carbon_trend"
    common = {
        "indicator": indicator,
        "direction": DIRECTION_OF[indicator],
        "unit": UNIT_SOIL_CARBON_TREND,
        "carbon_model": CARBON_MODEL,
        "computation": computation,
    }
    if is_missing(value):
        return SoilCarbonTrend(**common, value=None, missing=value)
    return SoilCarbonTrend(
        **common,
        value=value,
        provenance="SIMULATED",  # C4.3: computed from simulated stocks
        source=f"{source}; computation '{computation}' of engine/rothc/trend.py",
        range_missing=ResultMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def run_rothc(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance:
    """EP6: the RothC monthly turnover over the horizon of ``forcing``.

    Returns a ``CarbonBalance`` of carbon model ``rothc``, variant
    ``rothc_26_3``: the total stock and the five pools at the start of the
    horizon and at the end of each month, the carbon input and the carbon
    lost as CO2 of each month, and the three trend values of C1.6. Every
    value that is not computed is missing with its reason (G4).
    """
    _check_arguments(forcing, parameters)
    catalogue = _Catalogue(parameters)
    months = _months(forcing)

    rate_constants = {
        pool: catalogue.read(f"{pool}_rate_constant").value
        for pool in ACTIVE_POOLS
    }
    clay, clay_unit = _soil(forcing, "clay_content")
    partition = clay_partition(
        clay_content=clay,
        clay_content_unit=clay_unit,
        scale=catalogue.read("partition_scale").value,
        intercept=catalogue.read("partition_intercept").value,
        clay_coefficient=catalogue.read("partition_clay_coefficient").value,
        clay_decay=catalogue.read("partition_clay_decay").value,
        clay_decay_unit=catalogue.read("partition_clay_decay").unit,
    )
    bio_share = catalogue.read("bio_share").value
    iom, iom_derived = _initial_iom(forcing, catalogue)
    month_inputs = _month_inputs(forcing, catalogue, months)
    inverse = _inverse_mode(forcing)
    if inverse:
        # D218: only the total is given; the pools are its equilibrium split.
        start = equilibrium_state(
            months=month_inputs,
            rate_constants=rate_constants,
            partition_ratio=partition,
            bio_share=bio_share,
            total_organic_carbon=_starting(forcing, "total_carbon"),
            inert_organic_matter=iom,
        )
    else:
        start = initial_state(
            dpm=_starting(forcing, "dpm_pool"),
            rpm=_starting(forcing, "rpm_pool"),
            bio=_starting(forcing, "bio_pool"),
            hum=_starting(forcing, "hum_pool"),
            iom=iom,
        )
    the_run = run(
        initial_state=start,
        months=month_inputs,
        rate_constants=rate_constants,
        partition_ratio=partition,
        bio_share=bio_share,
    )
    measures = dict(
        trend_measures(
            stocks=list(the_run.total_stocks()),
            times=list(the_run.elapsed_times()),
            cycle_boundaries=ResultMissing(reason="MISSING_INPUT", detail=NO_CYCLES),
        ).values
    )
    # The core names only the first input of mean_over_cycles that is missing,
    # the cycle boundaries. When stocks are missing too, both are named (C3.3).
    cycles = measures["mean_over_cycles"]
    stocks_missing = [item for item in the_run.total_stocks() if is_missing(item)]
    if is_missing(cycles) and stocks_missing:
        measures["mean_over_cycles"] = ResultMissing(
            reason="MISSING_INPUT",
            detail=f"{cycles.detail}; {describe_missing('a stock', stocks_missing[0])}",
        )

    quantities = ", ".join(
        f"{part} '{quantity}'" for part, quantity in FORCING_QUANTITIES.values()
    )
    records = ", ".join(f"'{pid}'" for pid in catalogue.used)
    simulated = (
        f"{LABEL} Simulated by engine.rothc.run_rothc, variant '{VARIANT}', from the "
        f"forcing ({quantities}, and every series of carbon_inputs with the "
        f"composition of its origin) and the parameter records {records}"
    )
    derived_iom = (
        f"{LABEL} Derived by engine.rothc.run_rothc from starting_state "
        f"'{FORCING_QUANTITIES['total_carbon'][1]}' and the parameter records "
        f"'{PARAMETERS['iom_coefficient'][0]}', '{PARAMETERS['iom_exponent'][0]}' "
        "(the form printed on p. 16 of the model description)"
    )

    def initial_of(read):
        return start if is_missing(start) else read(start)

    def stock(name: str, read, provenance: str, source: str) -> StockSeries:
        values = [
            item if is_missing(item) else read(item.end) for item in the_run.steps
        ]
        return StockSeries(
            **_header(POOL_QUANTITIES[name], values, simulated),
            initial=_initial(initial_of(read), provenance, source),
            steps=_step_values(months, values),
        )

    def flow(name: str, read) -> FlowSeries:
        values = [item if is_missing(item) else read(item) for item in the_run.steps]
        return FlowSeries(
            **_header(FLOW_QUANTITIES[name], values, simulated),
            steps=_step_values(months, values),
        )

    def taken(pool: str) -> tuple[str, str]:
        if pool == "iom" and iom_derived:
            return "DERIVED", derived_iom
        if inverse:
            return "DERIVED", f"{LABEL} {EQUILIBRIUM}"
        return (
            "DECLARED",
            f"{LABEL} Taken from starting_state "
            f"'{FORCING_QUANTITIES[f'{pool}_pool'][1]}' of the forcing",
        )

    def total(state: PoolState) -> float:
        return state.total

    return CarbonBalance(
        contract="carbon_balance",
        example_data=forcing.example_data,
        case_id=forcing.case_id,
        field_id=forcing.field_id,
        rotation_id=forcing.rotation_id,
        carbon_model=CARBON_MODEL,
        variant=VARIANT,
        horizon=forcing.horizon,
        soil_depth=forcing.soil_depth,
        total_stock=stock(
            "total",
            total,
            "DERIVED",
            f"{LABEL} The sum of the five pools of this balance",
        ),
        pools=[
            stock(
                pool,
                lambda state, pool=pool: getattr(state, pool),
                *taken(pool),
            )
            for pool in (*ACTIVE_POOLS, "iom")
        ],
        flows=[
            flow("carbon_input", lambda item: item.additions.total),
            flow("co2", lambda item: item.co2),
        ],
        soil_carbon_trend=[
            _trend(name, measures[name], simulated) for name in TREND_COMPUTATIONS
        ],
    )
