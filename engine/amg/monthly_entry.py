"""Experimental monthly AMG entry point ``run_amg_monthly`` (D80 AMG-M). PROPOSED.

Steps AMGv2 month-by-month over a ``CarbonForcing`` and returns a
``CarbonBalance`` of carbon model ``amg``, variant ``amg_m``::

    run_amg_monthly(forcing: CarbonForcing, *, parameters: dict[str, dict]) -> CarbonBalance

Design and boundaries:

- **AMG-M (experimental, D80):** uses the monthly ``climate`` and monthly
  ``carbon_inputs`` of ``CarbonForcing`` (never ``annual_climate`` or
  ``annual_carbon_inputs``), stepping one calendar month at a time
  (``start`` equals ``end`` on each ``StepValue``) with ``duration = 1 / 12``
  in ``STEP_UNIT`` (``yr``) and the exact exponential scheme (``SCHEME``).
  Under uniform forcing over an agricultural year, twelve monthly steps agree
  with one annual step of ``run_amg`` (blueprint section 8).
- **No parameter values or defaults here:** every constant is read from
  ``parameters`` with ``entry._Catalogue`` (``params.catalogue`` readers; G1,
  D46, D56). Only zero and one appear as numeric constants in this module.
- **Reuses the core and entry helpers:** ``pools.py``, ``modifiers.py``,
  ``trend.py``, and constants/catalogue helpers from ``entry.py``.
- **Missingness (G4) and caller checks (G5):** what is not computed is missing
  with its reason, never zero; once a month is missing, every later month is
  missing. Raises ``TypeError`` when ``forcing`` is not a ``CarbonForcing`` or
  ``parameters`` is not ``dict[str, dict]``. Pure (G1): no I/O, no clock, no
  argument is mutated.
"""

from __future__ import annotations

from collections.abc import Sequence

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

from ._numbers import NumberOrMissing, describe_missing, is_missing
from .entry import (
    CARBON_MODEL,
    DIMENSIONLESS,
    FLOW_QUANTITIES,
    MODIFIERS,
    MONTHS,
    NO_CYCLES,
    ORIGIN_SCOPE_KEY,
    PARAMETERS,
    POOL_QUANTITIES,
    SCHEME,
    STEP_UNIT,
    STOCK_UNIT,
    _Catalogue,
    _check_arguments,
    _index,
    _input_missing,
    _month,
    _number,
    _of_steps,
)
from .modifiers import (
    carbonate_modifier,
    clay_modifier,
    cn_ratio_modifier,
    moisture_modifier,
    ph_modifier,
    rate_coefficient,
    temperature_modifier,
)
from .pools import PoolState, StepInput, humified_input, initial_state, run
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
    "run_amg_monthly",
]

# --- identifiers and choices, each PROPOSED -----------------------------------

VARIANT = "amg_m"  # AMG-M experimental monthly variant of D80

# D210 method label adapted for the experimental monthly step (D80).
METHOD_LABEL = (
    "AMGv2 soil carbon model (Clivot et al. 2019, Environmental Modelling & "
    "Software 118:99-113, https://doi.org/10.1016/j.envsoft.2019.04.004), monthly "
    "step (experimental AMG-M adaptation, D80). Parameters: the defaults of the "
    "AMGv2 parameters dataset v2.0 (https://doi.org/10.57745/MEQQIX), for average "
    "French arable crop conditions, not calibrated for the country of this site. "
    "The FAO-56 reference evapotranspiration stands in for the potential "
    "evapotranspiration (Penman 1948) of the source. Mean annual temperature of "
    "the calibration sites: 9.9 to 13.5 °C (Clivot et al. 2019, Table 1)."
)

# What run_amg_monthly reads from the forcing: (part of CarbonForcing, quantity).
FORCING_QUANTITIES: dict[str, tuple[str, str]] = {
    "starting_carbon": ("starting_state", "soil_organic_carbon"),
    "temperature": ("climate", "mean_temperature"),
    "water_balance": ("climate", "water_balance"),
    "clay_content": ("soil_properties", "clay_content"),
    "carbonate_content": ("soil_properties", "carbonate_content"),
    "ph": ("soil_properties", "ph"),
    "cn_ratio": ("soil_properties", "soil_cn_ratio"),
}

NO_RANGE = (
    "run_amg_monthly computes no uncertainty range "
    "(Q6 of contracts/ENTRYPOINTS.md, C2.3)"
)


# --- the forcing --------------------------------------------------------------


def _absent(name: str) -> ResultMissing:
    part, quantity = FORCING_QUANTITIES[name]
    return ResultMissing(
        reason="MISSING_INPUT",
        detail=f"quantity '{quantity}' has no item in {part} of the forcing",
    )


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
                        f"starting_state '{quantity}' is in '{item.unit}'; "
                        f"run_amg_monthly accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
            return _number(item.value, item.missing)
    return _absent("starting_carbon")


def _monthly_climate(
    forcing: CarbonForcing, name: str
) -> tuple[dict[tuple[int, int], NumberOrMissing] | ResultMissing, str]:
    """The values of a monthly climate series by (year, month), and its unit."""
    quantity = FORCING_QUANTITIES[name][1]
    for series in forcing.climate:
        if series.quantity == quantity:
            return (
                {
                    (item.year, item.month): _number(item.value, item.missing)
                    for item in series.months
                },
                series.unit,
            )
    return _absent(name), ""


def _at(
    values: dict[tuple[int, int], NumberOrMissing] | ResultMissing,
    month: YearMonth,
    name: str,
) -> NumberOrMissing:
    if is_missing(values):
        return values
    return values.get((month.year, month.month), _absent(name))


def _months(forcing: CarbonForcing) -> list[YearMonth]:
    """One calendar month per month of the horizon, in order."""
    start = _index(forcing.horizon.start)
    end = _index(forcing.horizon.end)
    return [_month(i) for i in range(start, end + 1)]


# --- the run ------------------------------------------------------------------


def _soil_modifiers(
    forcing: CarbonForcing, catalogue: _Catalogue
) -> dict[str, NumberOrMissing]:
    """The four soil modifiers, constant over the horizon."""
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
            detail=(
                f"soil property 'ph' is in '{ph_unit}'; expected "
                f"'{DIMENSIONLESS}' (C1.1)"
            ),
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
    return {
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


def _climate_modifiers(
    forcing: CarbonForcing,
    catalogue: _Catalogue,
    months: Sequence[YearMonth],
) -> dict[tuple[int, int], dict[str, NumberOrMissing]]:
    """The temperature and moisture modifiers by (year, month)."""
    temperatures, temperature_unit = _monthly_climate(forcing, "temperature")
    balances, balance_unit = _monthly_climate(forcing, "water_balance")
    reference = catalogue.read("temperature_reference")
    t_shape = catalogue.read("temperature_shape")
    t_sensitivity = catalogue.read("temperature_sensitivity")
    w_shape = catalogue.read("moisture_shape")
    w_sensitivity = catalogue.read("moisture_sensitivity")
    return {
        (month.year, month.month): {
            "temperature": temperature_modifier(
                temperature=_at(temperatures, month, "temperature"),
                temperature_unit=temperature_unit,
                reference_temperature=reference.value,
                reference_temperature_unit=reference.unit,
                shape_coefficient=t_shape.value,
                sensitivity_coefficient=t_sensitivity.value,
                sensitivity_coefficient_per_unit=t_sensitivity.unit,
            ),
            "moisture": moisture_modifier(
                water_balance=_at(balances, month, "water_balance"),
                water_balance_unit=balance_unit,
                shape_coefficient=w_shape.value,
                sensitivity_coefficient=w_sensitivity.value,
                sensitivity_coefficient_per_unit=w_sensitivity.unit,
            ),
        }
        for month in months
    }


def _carbon_inputs(
    forcing: CarbonForcing, catalogue: _Catalogue
) -> tuple[
    dict[tuple[int, int], dict[str, NumberOrMissing]],
    dict[str, NumberOrMissing],
]:
    """The monthly carbon inputs by (year, month) and series, and each series's coefficient.

    Keyed by the quantity of the series, so two series of one origin are two
    inputs with the coefficient of that origin.
    """
    by_month: dict[tuple[int, int], dict[str, NumberOrMissing]] = {}
    coefficients: dict[str, NumberOrMissing] = {}
    for series in forcing.carbon_inputs:
        coefficients[series.quantity] = catalogue.read(
            "humification_coefficient", ((ORIGIN_SCOPE_KEY, series.origin),)
        ).value
        for item in series.months:
            value: NumberOrMissing = _number(item.value, item.missing)
            if series.unit != STOCK_UNIT and not is_missing(value):
                value = ResultMissing(
                    reason="NOT_COMPUTABLE",
                    detail=(
                        f"carbon_inputs '{series.quantity}' is in '{series.unit}'; "
                        f"run_amg_monthly accepts '{STOCK_UNIT}' and converts nothing"
                    ),
                )
            by_month.setdefault((item.year, item.month), {})[series.quantity] = value
    return by_month, coefficients


def _step_inputs(
    forcing: CarbonForcing,
    catalogue: _Catalogue,
    months: Sequence[YearMonth],
    potential_rate: NumberOrMissing,
) -> list[StepInput]:
    soil = _soil_modifiers(forcing, catalogue)
    climate = _climate_modifiers(forcing, catalogue, months)
    inputs, coefficients = _carbon_inputs(forcing, catalogue)
    duration = 1 / MONTHS  # one month in STEP_UNIT ("yr")
    result: list[StepInput] = []
    for month in months:
        key = (month.year, month.month)
        modifiers = {**climate[key], **soil}
        result.append(
            StepInput(
                humified_input=humified_input(
                    carbon_inputs=inputs.get(key, {}),
                    humification_coefficients=coefficients,
                ),
                rate_coefficient=rate_coefficient(
                    potential_rate=potential_rate,
                    modifiers={name: modifiers[name] for name in MODIFIERS},
                ),
                duration=duration,
            )
        )
    return result


# --- the contract -------------------------------------------------------------


def _initial(value: float | ResultMissing, source: str) -> Value:
    if is_missing(value):
        return Value(value=None, unit=STOCK_UNIT, missing=_input_missing(value))
    return Value(
        value=value,
        unit=STOCK_UNIT,
        provenance="DERIVED",
        source=source,
        range_missing=InputMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def _step_values(
    months: Sequence[YearMonth], values: Sequence[float | ResultMissing]
) -> list[StepValue]:
    return [
        StepValue(
            start=month, end=month, value=None, missing=_input_missing(value)
        )
        if is_missing(value)
        else StepValue(start=month, end=month, value=value)
        for month, value in zip(months, values, strict=True)
    ]


def _header(
    quantity: str, values: Sequence[float | ResultMissing], source: str
) -> dict:
    present = any(not is_missing(value) for value in values)
    header: dict = {"quantity": quantity, "unit": STOCK_UNIT}
    if present:
        header.update(
            provenance="SIMULATED",
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
        provenance="SIMULATED",
        source=f"{source}; computation '{computation}' of engine/amg/trend.py",
        range_missing=ResultMissing(reason="NOT_AVAILABLE", detail=NO_RANGE),
    )


def run_amg_monthly(
    forcing: CarbonForcing, *, parameters: dict[str, dict]
) -> CarbonBalance:
    """Experimental AMG-M: monthly AMGv2 over the horizon of ``forcing``.

    Returns a ``CarbonBalance`` of carbon model ``amg``, variant ``amg_m``:
    the total stock, the active and the stable pool at the start of the
    horizon and at the end of each calendar month, the humified input and the
    mineralised carbon of each month, and the three trend values of C1.6.
    Every value that is not computed is missing with its reason (G4).
    """
    _check_arguments(forcing, parameters)
    catalogue = _Catalogue(parameters)
    months = _months(forcing)

    stable_fraction = catalogue.read("stable_fraction").value
    start = initial_state(
        total_carbon=_starting_carbon(forcing), stable_fraction=stable_fraction
    )
    potential_rate = catalogue.read("potential_rate")
    step_inputs = _step_inputs(forcing, catalogue, months, potential_rate.value)
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
        f"{METHOD_LABEL}; "
        f"simulated by engine.amg.monthly_entry.run_amg_monthly, variant '{VARIANT}', "
        f"scheme '{SCHEME}', from the forcing ({quantities}, and every series of "
        f"carbon_inputs) and the parameter records {records}"
    )
    derived = (
        f"{METHOD_LABEL}; "
        f"derived by engine.amg.monthly_entry.run_amg_monthly from starting_state "
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
            steps=_step_values(months, values),
        )

    def flow(name: str, read) -> FlowSeries:
        values = _of_steps(the_run.steps, read)
        return FlowSeries(
            **_header(FLOW_QUANTITIES[name], values, simulated),
            steps=_step_values(months, values),
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
