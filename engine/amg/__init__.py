"""The AMG soil carbon model as pure functions (decision D1 of issue #77). PROPOSED.

Unit ``l1/amg-core`` (issue #174) built the model core: the two pools and
their step (``pools.py``), the rate coefficient and its modifiers
(``modifiers.py``) and the trend measures of C1.6 (``trend.py``). Unit
``l1/amg-ep5`` (issue #192) adds the entry point EP5 of
contracts/ENTRYPOINTS.md, ``run_amg(forcing, *, parameters) -> CarbonBalance``
(``entry.py``): AMG-A, the annual variant of decision D80, on the core. Unit
``l1/amg-v2-complete-d192`` (issue #299) makes it AMGv2 as decision D192 of
issue #77 names it: six modifiers, the C:N modifier among them (D193, D199),
the cut of the temperature modifier, and the exponential yearly step. Every
form is PROPOSED and still to be compared with its source by a person, and no
value of the method appears in this package (README.md of this folder).
"""

from .entry import run_amg
from .modifiers import (
    carbonate_modifier,
    clay_modifier,
    cn_ratio_modifier,
    moisture_modifier,
    ph_modifier,
    rate_coefficient,
    temperature_modifier,
)
from .pools import (
    SCHEMES,
    PoolState,
    Run,
    StepInput,
    StepResult,
    humified_input,
    initial_state,
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
    "SCHEMES",
    "PoolState",
    "Run",
    "StepInput",
    "StepResult",
    "TrendMeasures",
    "carbonate_modifier",
    "clay_modifier",
    "cn_ratio_modifier",
    "end_minus_start",
    "fitted_slope",
    "humified_input",
    "initial_state",
    "mean_over_cycles",
    "moisture_modifier",
    "ph_modifier",
    "rate_coefficient",
    "run",
    "run_amg",
    "step",
    "temperature_modifier",
    "trend_measures",
]
