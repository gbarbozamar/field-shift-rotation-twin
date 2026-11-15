"""The RothC soil carbon model as pure functions (decision D1 of issue #77). PROPOSED.

Unit ``l2/rothc-common-forcings`` (issue #176) built this folder on the
person-transcribed model description of that issue ("RothC -- Model
Description", February 2024, Rothamsted Research; transcribed by Martin on
14 November 2026, checked by the lead developer on 15 November 2026 under
D63 and D134; in force per D34). The core holds the five pools and their
monthly step (``pools.py``), the rate modifying factors (``modifiers.py``)
the trend measures of C1.6 (``trend.py``) and the equilibrium
initialisation of D218 (``equilibrium.py``); ``entry.py`` adds the entry
point EP6 of contracts/ENTRYPOINTS.md, ``run_rothc(forcing, *, parameters)
-> CarbonBalance``, over the common forcing. No value of the method appears
in this package (README.md of this folder): every constant is a record of
the parameter catalogue the entry point receives.
"""

from .entry import run_rothc
from .equilibrium import cycle_fixed_point, equilibrium_state
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
    MONTHS_PER_YEAR,
    InputSplit,
    MonthInput,
    PoolState,
    Run,
    StepResult,
    initial_state,
    input_additions,
    inert_organic_matter,
    plant_fractions,
    run,
    step,
)
from .trend import (
    TrendMeasures,
    end_minus_start,
    fitted_slope,
    mean_over_cycles,
    trend_measures,
)

__all__ = [
    "MONTHS_PER_YEAR",
    "InputSplit",
    "MonthInput",
    "PoolState",
    "Run",
    "StepResult",
    "TrendMeasures",
    "advance_deficit",
    "bare_soil_deficit",
    "clay_partition",
    "cover_modifier",
    "cycle_fixed_point",
    "end_minus_start",
    "equilibrium_state",
    "fitted_slope",
    "initial_state",
    "input_additions",
    "inert_organic_matter",
    "maximum_tsmd",
    "mean_over_cycles",
    "moisture_modifier",
    "plant_fractions",
    "rate_modifying_factor",
    "run",
    "run_rothc",
    "step",
    "temperature_modifier",
    "trend_measures",
]
