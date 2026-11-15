"""EP5 ``run_amg``: the AMG core run on a ``CarbonForcing``, returned as a ``CarbonBalance``. PROPOSED.

Unit ``l1/amg-ep5`` (issue #192). The entry point of contracts/ENTRYPOINTS.md
EP5::

    run_amg(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance

What it builds (README.md of this folder, section "EP5 run_amg"):

- **AMG-A only**, the annual reference that takes part in the selection
  (decision D80 of issue #77). One step per agricultural year of the
  horizon (C5.3), of length one ``yr`` (C1.1). AMG-M, the monthly variant,
  is experimental under D80 and is not built (README.md, OPEN).
- Inputs from the forcing: the starting soil carbon (``starting_state``),
  the annual carbon inputs by origin (``annual_carbon_inputs``), the annual
  temperature and water balance (``annual_climate``) and the clay,
  carbonate, pH and C:N ratio of the soil (``soil_properties``; the C:N
  ratio by decision D193 of issue #77). Their identifiers are
  PROPOSED in ``FORCING_QUANTITIES``; the vocabulary of the forcing is OPEN
  (contracts/carbon_forcing/README.md).
- Every constant is read from ``parameters`` with the pure readers of
  ``params.catalogue`` (``identity``, ``read_value``; G1, D46, D56). The
  identifiers are those the core proposes (README.md, "Constants a person
  has to transcribe"). No value of the method is written here.
- The core of ``pools.py``, ``modifiers.py`` and ``trend.py`` does every
  computation. This module only looks values up, checks their units, lays
  out the steps and writes the contract.

What is not computed is missing with its reason (G4), never zero: a
parameter without a record, or whose record holds no value, is
``MISSING_INPUT`` naming its ``id`` and scope (D56); a quantity the forcing
does not carry is ``MISSING_INPUT`` naming it; a unit that is not accepted is
``NOT_COMPUTABLE`` naming it (Q11 is OPEN; the core makes the same choice).
Once a step is missing every later step is missing (the core's ``run``).

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
from .modifiers import (
    carbonate_modifier,
    clay_modifier,
    cn_ratio_modifier,
    moisture_modifier,
    ph_modifier,
    rate_coefficient,
    temperature_modifier,
)
from .pools import PoolState, StepInput, StepResult, humified_input, initial_state, run
from .trend import trend_measures

__all__ = [
    "CARBON_MODEL",
    "FORCING_QUANTITIES",
    "METHOD_LABEL",
    "MODIFIERS",
    "PARAMETERS",
    "POOL_QUANTITIES",
    "SCHEME",
    "STEP_UNIT",
    "STOCK_UNIT",
    "VARIANT",
    "run_amg",
]

# --- identifiers and choices, each PROPOSED (README.md, "EP5 run_amg") ----------

CARBON_MODEL = "amg"  # D1 of issue #77
VARIANT = "amg_a"  # AMG-A of D80; the vocabulary of ``variant`` is OPEN

# The label of the method (decision D210 of issue #77, which completes D192),
# word for word as brief #313 gives it. It opens the ``source`` of every value
# of the balance that is a number, then "; " and the rest of the source text,
# as D162 does for the water label. A missing value carries no source. It says
# only what is true of the method: what is true of one site (the transferred
# soil C:N ratio and clay content, D182, D193) travels in the source of the
# site's own records. It is a quotation of the source, printed for a reader:
# no number is read out of it and it is used nowhere but in source texts
# (README.md, "EP5 run_amg", item 5 of "What it builds").
METHOD_LABEL = (
    "AMGv2 soil carbon model (Clivot et al. 2019, Environmental Modelling & "
    "Software 118:99-113, https://doi.org/10.1016/j.envsoft.2019.04.004), yearly "
    "step. Parameters: the defaults of the AMGv2 parameters dataset v2.0 "
    "(https://doi.org/10.57745/MEQQIX), for average French arable crop conditions, "
    "not calibrated for the country of this site. The FAO-56 reference "
    "evapotranspiration stands in for the potential evapotranspiration (Penman "
    "1948) of the source. Mean annual temperature of the calibration sites: 9.9 "
    "to 13.5 °C (Clivot et al. 2019, Table 1)."
)
# The scheme of the annual step: the exact exponential solution over the year
# (decision D192 of issue #77; OPEN 2 of README.md).
SCHEME = "exponential"
STEP_UNIT = "yr"  # C1.1: one agricultural year; the length of every step is one
_PER = "-1"  # C1.1 writes "per X" as "X-1", as in "t ha-1 yr-1"
# The unit of every stock and flow: the unit of C1.5 without "per year", so
# that a trend over steps of one ``yr`` is in the unit of C1.5. Nothing is
# converted: an input in another unit is NOT_COMPUTABLE.
STOCK_UNIT = UNIT_SOIL_CARBON_TREND.removesuffix(f" {STEP_UNIT}{_PER}")
DIMENSIONLESS = "dimensionless"  # C1.1
# Calendar months in an agricultural year (C5.3), counted, not written as a number.
MONTHS = len(calendar.month_name[1:])

# What run_amg reads from the forcing: (part of CarbonForcing, quantity).
FORCING_QUANTITIES: dict[str, tuple[str, str]] = {
    "starting_carbon": ("starting_state", "soil_organic_carbon"),
    "temperature": ("annual_climate", "mean_temperature"),
    "water_balance": ("annual_climate", "water_balance"),
    "clay_content": ("soil_properties", "clay_content"),
    "carbonate_content": ("soil_properties", "carbonate_content"),
    "ph": ("soil_properties", "ph"),
    # D193 of issue #77: the soil C:N ratio, a quantity of the forcing.
    "cn_ratio": ("soil_properties", "soil_cn_ratio"),
}

# The parameters, with the identifiers the core proposes (README.md) and how
# the unit of each record is used: "dimensionless" (must be that text, C1.1),
# "per" (written "X-1"; X is passed to the core, which compares it), or
# "unit" (passed to the core as it is).
PARAMETERS: dict[str, tuple[str, str]] = {
    "humification_coefficient": ("amg_humification_coefficient", "dimensionless"),
    "stable_fraction": ("amg_stable_fraction", "dimensionless"),
    "potential_rate": ("amg_potential_mineralisation_rate", "per"),
    "temperature_reference": ("amg_temperature_reference", "unit"),
    "temperature_shape": ("amg_temperature_shape", "dimensionless"),
    "temperature_sensitivity": ("amg_temperature_sensitivity", "per"),
    "moisture_shape": ("amg_moisture_shape", "dimensionless"),
    "moisture_sensitivity": ("amg_moisture_sensitivity", "per"),
    "clay_sensitivity": ("amg_clay_sensitivity", "per"),
    "carbonate_sensitivity": ("amg_carbonate_sensitivity", "per"),
    "ph_optimum": ("amg_ph_optimum", "dimensionless"),
    "ph_sensitivity": ("amg_ph_sensitivity", "dimensionless"),
    # The three constants of the C:N modifier (D192; the minimum, D199).
    "cn_ratio_sensitivity": ("amg_cn_ratio_sensitivity", "dimensionless"),
    "cn_ratio_optimum": ("amg_cn_ratio_optimum", "dimensionless"),
    "cn_ratio_minimum": ("amg_cn_ratio_minimum", "dimensionless"),
}
# The humification coefficient has one record per origin of a carbon input;
# the origin is written under this scope key (OPEN 7 of README.md).
ORIGIN_SCOPE_KEY = "crop"
# The modifiers the rate coefficient of AMG-A multiplies: the six of the
# source (decision D192 of issue #77; OPEN 4 of README.md).
MODIFIERS: tuple[str, ...] = (
    "temperature",
    "moisture",
    "clay",
    "carbonate",
    "ph",
    "cn_ratio",
)

# The series of the balance.
POOL_QUANTITIES = {
    "total": "soil_organic_carbon",
    "active": "amg_active_pool",
    "stable": "amg_stable_pool",
}
FLOW_QUANTITIES = {
    "humified_input": "amg_humified_input",
    "mineralised": "amg_mineralised_carbon",
}

NO_RANGE = (
    "run_amg computes no uncertainty range (Q6 of contracts/ENTRYPOINTS.md, C2.3)"
)
NO_CYCLES = (
    "the positions of the whole rotation cycles in the series of stocks: "
    "CarbonForcing carries no rotation cycle, so mean_over_cycles has no input "
    "(engine/amg/README.md, OPEN)"
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

    def read(self, name: str, scope: Scope = ()) -> _Parameter:
        parameter_id, how = PARAMETERS[name]
        if parameter_id not in self.used:
            self.used.append(parameter_id)
        named = _named(parameter_id, scope)
        if self._malformed:
            return self._missing(
                f"{named}: it cannot be looked up: the record(s) "
                + ", ".join(repr(key) for key in self._malformed)
                + " have no well-formed 'id' and 'scope' (F3c of params/README.md)"
            )
        found = self._index.get(
            identity({"id": parameter_id, "scope": dict(scope)}), []
        )
        if not found:
            return self._missing(f"{named}: no record in parameters (D56)")
        if len(found) != 1:
            return self._missing(f"{named}: two records share this id and scope")
        (record,) = found
        try:
            value = read_value(record)
        except ValueError as error:
            return self._missing(f"{named}: the record is not read: {error}")
        if isinstance(value, CatalogueMissing):
            return self._missing(f"{named}: the record holds no value: {value.reason}")
        return self._unit(named, value, record["unit"], how)

    @staticmethod
    def _missing(detail: str) -> _Parameter:
        return _Parameter(ResultMissing(reason="MISSING_INPUT", detail=detail), "")

    @staticmethod
    def _unit(named: str, value: float, unit: str, how: str) -> _Parameter:
        if how == "unit":
            return _Parameter(value, unit)
        if how == "dimensionless":
            if unit == DIMENSIONLESS:
                return _Parameter(value, unit)
            expected = f"'{DIMENSIONLESS}' (C1.1)"
        else:
            if unit.endswith(_PER) and unit != _PER:
                return _Parameter(value, unit.removesuffix(_PER))
            expected = f"per a unit, written 'X{_PER}' (C1.1)"
        return _Parameter(
            ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=f"{named}: its unit '{unit}' is not accepted: expected {expected}",
            ),
            "",
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


def _soil(forcing: CarbonForcing, name: str) -> tuple[NumberOrMissing, str]:
    """A soil property: its value (or why not) and its unit."""
    quantity = FORCING_QUANTITIES[name][1]
    for item in forcing.soil_properties:
        if item.quantity == quantity:
            return _number(item.value, item.missing), item.unit
    return _absent(name), ""


def _starting_carbon(forcing: CarbonForcing) -> NumberOrMissing:
    quantity = FORCING_QUANTITIES["starting_carbon"][1]
    for item in forcing.starting_state:
        if item.quantity == quantity:
            if item.unit != STOCK_UNIT:
                return ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"starting_state '{quantity}' is in '{item.unit}'; run_amg "
                        f"accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
            return _number(item.value, item.missing)
    return _absent("starting_carbon")


def _annual_climate(
    forcing: CarbonForcing, name: str
) -> tuple[dict[int, NumberOrMissing] | ResultMissing, str]:
    """The values of an annual climate series by agricultural year, and its unit."""
    quantity = FORCING_QUANTITIES[name][1]
    for series in forcing.annual_climate:
        if series.quantity == quantity:
            return (
                {
                    item.ag_year: _number(item.value, item.missing)
                    for item in series.years
                },
                series.unit,
            )
    return _absent(name), ""


@dataclass(frozen=True)
class _Step:
    start: YearMonth
    end: YearMonth
    whole: bool  # twelve months: one agricultural year (C5.3)


def _index(month: YearMonth) -> int:
    return month.year * MONTHS + month.month - 1


def _month(index: int) -> YearMonth:
    return YearMonth(year=index // MONTHS, month=index % MONTHS + 1)


def _steps(forcing: CarbonForcing) -> list[_Step]:
    """One step per agricultural year from the start of the horizon (C5.3).

    Months after the last whole agricultural year make one more step, which
    is not a whole year and so is not computed by the annual variant.
    """
    start = _index(forcing.horizon.start)
    end = _index(forcing.horizon.end)
    steps = [
        _Step(_month(first), _month(first + MONTHS - 1), True)
        for first in range(start, end + 1 - (MONTHS - 1), MONTHS)
    ]
    covered = start + MONTHS * len(steps)
    if covered <= end:
        steps.append(_Step(_month(covered), _month(end), False))
    return steps


# --- the run -----------------------------------------------------------------------------


def _modifiers(
    forcing: CarbonForcing, catalogue: _Catalogue
) -> tuple[dict[str, NumberOrMissing], dict[int, dict[str, NumberOrMissing]]]:
    """The soil modifiers (one value) and the climate modifiers by agricultural year."""
    clay, clay_unit = _soil(forcing, "clay_content")
    carbonate, carbonate_unit = _soil(forcing, "carbonate_content")
    ph, ph_unit = _soil(forcing, "ph")
    cn_ratio, cn_ratio_unit = _soil(forcing, "cn_ratio")
    clay_sensitivity = catalogue.read("clay_sensitivity")
    carbonate_sensitivity = catalogue.read("carbonate_sensitivity")
    ph_optimum = catalogue.read("ph_optimum")
    ph_sensitivity = catalogue.read("ph_sensitivity")
    cn_ratio_optimum = catalogue.read("cn_ratio_optimum")
    cn_ratio_sensitivity = catalogue.read("cn_ratio_sensitivity")
    cn_ratio_minimum = catalogue.read("cn_ratio_minimum")
    if not is_missing(ph) and ph_unit != DIMENSIONLESS:
        ph = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=f"soil property 'ph' is in '{ph_unit}'; expected '{DIMENSIONLESS}' (C1.1)",
        )
    if not is_missing(cn_ratio) and cn_ratio_unit != DIMENSIONLESS:
        quantity = FORCING_QUANTITIES["cn_ratio"][1]
        cn_ratio = ResultMissing(
            reason="NOT_COMPUTABLE",
            detail=(
                f"soil property '{quantity}' is in '{cn_ratio_unit}'; expected "
                f"'{DIMENSIONLESS}' (C1.1)"
            ),
        )
    soil = {
        "clay": clay_modifier(
            clay_content=clay,
            clay_content_unit=clay_unit,
            sensitivity_coefficient=clay_sensitivity.value,
            sensitivity_coefficient_per_unit=clay_sensitivity.unit,
        ),
        "carbonate": carbonate_modifier(
            carbonate_content=carbonate,
            carbonate_content_unit=carbonate_unit,
            sensitivity_coefficient=carbonate_sensitivity.value,
            sensitivity_coefficient_per_unit=carbonate_sensitivity.unit,
        ),
        "ph": ph_modifier(
            ph=ph,
            optimum_ph=ph_optimum.value,
            sensitivity_coefficient=ph_sensitivity.value,
        ),
        "cn_ratio": cn_ratio_modifier(
            cn_ratio=cn_ratio,
            optimum_cn_ratio=cn_ratio_optimum.value,
            sensitivity_coefficient=cn_ratio_sensitivity.value,
            minimum=cn_ratio_minimum.value,
        ),
    }
    temperatures, temperature_unit = _annual_climate(forcing, "temperature")
    balances, balance_unit = _annual_climate(forcing, "water_balance")
    reference = catalogue.read("temperature_reference")
    t_shape = catalogue.read("temperature_shape")
    t_sensitivity = catalogue.read("temperature_sensitivity")
    w_shape = catalogue.read("moisture_shape")
    w_sensitivity = catalogue.read("moisture_sensitivity")

    def at(values: dict[int, NumberOrMissing] | ResultMissing, ag_year: int, name: str):
        if is_missing(values):
            return values
        if ag_year in values:
            return values[ag_year]
        return _absent(name)

    climate: dict[int, dict[str, NumberOrMissing]] = {}
    for step in _steps(forcing):
        ag_year = step.start.year
        climate[ag_year] = {
            "temperature": temperature_modifier(
                temperature=at(temperatures, ag_year, "temperature"),
                temperature_unit=temperature_unit,
                reference_temperature=reference.value,
                reference_temperature_unit=reference.unit,
                shape_coefficient=t_shape.value,
                sensitivity_coefficient=t_sensitivity.value,
                sensitivity_coefficient_per_unit=t_sensitivity.unit,
            ),
            "moisture": moisture_modifier(
                water_balance=at(balances, ag_year, "water_balance"),
                water_balance_unit=balance_unit,
                shape_coefficient=w_shape.value,
                sensitivity_coefficient=w_sensitivity.value,
                sensitivity_coefficient_per_unit=w_sensitivity.unit,
            ),
        }
    return soil, climate


def _carbon_inputs(
    forcing: CarbonForcing, catalogue: _Catalogue
) -> tuple[dict[int, dict[str, NumberOrMissing]], dict[str, NumberOrMissing]]:
    """The carbon inputs by agricultural year and series, and the coefficient of each series.

    Keyed by the quantity of the series, so two series of one origin are two
    inputs with the coefficient of that origin.
    """
    by_year: dict[int, dict[str, NumberOrMissing]] = {}
    coefficients: dict[str, NumberOrMissing] = {}
    for series in forcing.annual_carbon_inputs:
        coefficients[series.quantity] = catalogue.read(
            "humification_coefficient", ((ORIGIN_SCOPE_KEY, series.origin),)
        ).value
        for item in series.years:
            value: NumberOrMissing = _number(item.value, item.missing)
            if series.unit != STOCK_UNIT and not is_missing(value):
                value = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"annual_carbon_inputs '{series.quantity}' is in '{series.unit}'; "
                        f"run_amg accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
            by_year.setdefault(item.ag_year, {})[series.quantity] = value
    return by_year, coefficients


def _step_inputs(
    forcing: CarbonForcing,
    catalogue: _Catalogue,
    steps: Sequence[_Step],
    potential_rate: NumberOrMissing,
) -> list[StepInput]:
    soil, climate = _modifiers(forcing, catalogue)
    inputs, coefficients = _carbon_inputs(forcing, catalogue)
    result = []
    for step in steps:
        if not step.whole:
            not_whole = ResultMissing(
                reason="NOT_COMPUTABLE",
                detail=(
                    f"the step from {step.start.year}-{step.start.month:02d} to "
                    f"{step.end.year}-{step.end.month:02d} is not a whole agricultural "
                    "year, and AMG-A steps by agricultural year (D80, C5.3)"
                ),
            )
            result.append(StepInput(not_whole, not_whole, not_whole))
            continue
        ag_year = step.start.year
        modifiers = {**climate[ag_year], **soil}
        result.append(
            StepInput(
                humified_input=humified_input(
                    carbon_inputs=inputs.get(ag_year, {}),
                    humification_coefficients=coefficients,
                ),
                rate_coefficient=rate_coefficient(
                    potential_rate=potential_rate,
                    modifiers={name: modifiers[name] for name in MODIFIERS},
                ),
                duration=1,  # one yr (STEP_UNIT)
            )
        )
    return result


# --- the contract ----------------------------------------------------------------------


def _input_missing(missing: ResultMissing | InputMissing) -> InputMissing:
    return InputMissing(reason=missing.reason, detail=missing.detail)


def _initial(value: float | ResultMissing, source: str) -> Value:
    if is_missing(value):
        return Value(value=None, unit=STOCK_UNIT, missing=_input_missing(value))
    return Value(
        value=value,
        unit=STOCK_UNIT,
        provenance="DERIVED",  # C4.3: a fixed formula of declared values
        source=source,
        range_missing=InputMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def _step_values(
    steps: Sequence[_Step], values: Sequence[float | ResultMissing]
) -> list[StepValue]:
    return [
        StepValue(
            start=step.start, end=step.end, value=None, missing=_input_missing(value)
        )
        if is_missing(value)
        else StepValue(start=step.start, end=step.end, value=value)
        for step, value in zip(steps, values, strict=True)
    ]


def _header(
    quantity: str, values: Sequence[float | ResultMissing], source: str
) -> dict:
    present = any(not is_missing(value) for value in values)
    header: dict = {"quantity": quantity, "unit": STOCK_UNIT}
    if present:
        header.update(
            provenance="SIMULATED",  # C4.1: produced by running a model through time steps
            source=source,
            range_missing=InputMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
        )
    return header


def _of_steps(
    results: Sequence[StepResult | ResultMissing], read
) -> list[float | ResultMissing]:
    return [item if is_missing(item) else read(item) for item in results]


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
        source=f"{source}; computation '{computation}' of engine/amg/trend.py",
        range_missing=ResultMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def run_amg(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance:
    """EP5: AMG-A over the horizon of ``forcing``, every constant from ``parameters``.

    Returns a ``CarbonBalance`` of carbon model ``amg``, variant ``amg_a``:
    the total stock, the active and the stable pool at the start of the
    horizon and at the end of each agricultural year, the humified input and
    the mineralised carbon of each year, and the three trend values of C1.6.
    Every value that is not computed is missing with its reason (G4).
    """
    _check_arguments(forcing, parameters)
    catalogue = _Catalogue(parameters)
    steps = _steps(forcing)

    stable_fraction = catalogue.read("stable_fraction").value
    start = initial_state(
        total_carbon=_starting_carbon(forcing), stable_fraction=stable_fraction
    )
    potential_rate = catalogue.read("potential_rate")
    step_inputs = _step_inputs(forcing, catalogue, steps, potential_rate.value)
    the_run = run(
        initial_state=start,
        steps=step_inputs,
        # When the rate is missing its unit is never compared (the core reports
        # the missing value first), so the step unit stands in for the text.
        rate_coefficient_per_unit=potential_rate.unit or STEP_UNIT,
        duration_unit=STEP_UNIT,
        scheme=SCHEME,
    )
    measures = dict(
        trend_measures(
            run=the_run,
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
    # D210: every source text of a number opens with the label of the method.
    simulated = (
        f"{METHOD_LABEL}; "
        f"simulated by engine.amg.run_amg, variant '{VARIANT}', scheme '{SCHEME}', "
        f"from the forcing ({quantities}, and every series of annual_carbon_inputs) "
        f"and the parameter records {records}"
    )
    derived = (
        f"{METHOD_LABEL}; "
        f"derived by engine.amg.run_amg from starting_state "
        f"'{FORCING_QUANTITIES['starting_carbon'][1]}' of the forcing and the "
        f"parameter record '{PARAMETERS['stable_fraction'][0]}'"
    )

    def initial_of(read) -> float | ResultMissing:
        return start if is_missing(start) else read(start)

    def stock(name: str, read) -> StockSeries:
        values = _of_steps(the_run.steps, lambda item: read(item.end))
        return StockSeries(
            **_header(POOL_QUANTITIES[name], values, simulated),
            initial=_initial(initial_of(read), derived),
            steps=_step_values(steps, values),
        )

    def flow(name: str, read) -> FlowSeries:
        values = _of_steps(the_run.steps, read)
        return FlowSeries(
            **_header(FLOW_QUANTITIES[name], values, simulated),
            steps=_step_values(steps, values),
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
        total_stock=stock("total", total),
        pools=[
            stock("active", lambda state: state.active),
            stock("stable", lambda state: state.stable),
        ],
        flows=[
            flow("humified_input", lambda item: item.humified_input),
            flow("mineralised", lambda item: item.mineralised),
        ],
        soil_carbon_trend=[
            _trend(name, measures[name], simulated) for name in TREND_COMPUTATIONS
        ],
    )
