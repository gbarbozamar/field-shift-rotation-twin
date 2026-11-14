"""The engine runner: ``RotationEngines`` on the entry points of contracts/ENTRYPOINTS.md.

``EntryPointEngines`` calls the engine entry points in the accepted order and
assembles one ``ResultsPerRotation`` (decision Q15 a, issue 18):

1. EP2 ``build_rotation_calendar(load_rotation(rotation))``;
2. EP1 ``compute_soil_loss`` and EP3 ``compute_water_deficit_exposure`` with
   the keyword arguments ``calendar``, ``climate`` and ``soil_slope`` (G3),
   also when the calendar is infeasible: the engine writes the missing values
   and their reason (G4), but only when the climate and soil-and-slope data carry the calendar's
   ``case_id`` and ``field_id``; otherwise neither is called and the result
   is absent, ``MISSING_INPUT`` (PROPOSED). Each of the two also gets the
   parameter catalogue as the keyword argument ``parameters`` (Q3, D46, D56
   of issue #77), always, as contracts/ENTRYPOINTS.md states; EP2 never does.
   An engine that does not take it is a defect (``TypeError``, ``500``);
3. ``ResultsPerRotation`` from the identifiers of the calendar, the two engine
   results unchanged, and ``soil_carbon_trend`` written here as missing,
   because no carbon engine is built (decision Q15 c). A part whose engine is
   not built is written in the not-built form of the contract (decision D12
   of issue #77): ``SoilLossNotBuilt`` or ``WaterDeficitExposureNotBuilt``,
   reason ``NOT_AVAILABLE``, built from the constants of
   contracts/results/models.py. Only an engine that is not built gives that
   form; every other absence keeps ``result=None`` with its reason.

Each engine function is injected (``EngineFunctions``). ``None`` means "this
engine is not built". ``discover_engine_functions`` imports each one by the
module path and name that contracts/ENTRYPOINTS.md gives, so when a lane lands
an engine nothing in ``api/`` changes.

The runner computes nothing scientific, converts no unit, fills no gap and
never builds a number. When a part is absent it writes a typed absence, never
a stand-in value and never an invented identifier. It catches nothing an
engine raises (G5, Q7): the route answers ``500``. An engine that returns
something other than the type its signature names is a defect: ``TypeError``.

Status: PROPOSED (blueprint section 3.7), including every rule of the table in
api/README.md, the detail texts and the counting rule. Decided: the module
identifiers (D13), the comparison of identifiers by the runner (D14) and the
not-built form of a part (D12), all of issue #77.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, get_args

from adapters.ports import ClimateResult, SoilSlopeResult
from api.ports import EnginesResult, Missing, ModuleStatus, ReasonCode
from api.rotation_validator import load_rotation_definition
from contracts.inputs import RotationCalendar
from contracts.results.models import (
    DIRECTION_OF,
    REASON_OF_A_PART_NOT_BUILT,
    TREND_COMPUTATIONS,
    UNIT_SOIL_CARBON_TREND,
    UNITS_OF,
    IndicatorValue,
    PartNotBuilt,
    ResultsPerRotation,
    SoilCarbonTrend,
    SoilLossNotBuilt,
    SoilLossResults,
    WaterDeficitExposure,
    WaterDeficitExposureNotBuilt,
)
from contracts.results.models import Missing as ResultsMissing

# --- the entry points ---------------------------------------------------------


@dataclass(frozen=True)
class EntryPoint:
    """Where an engine function lives, as contracts/ENTRYPOINTS.md names it."""

    entry: str  # EP1 ... EP6
    module_id: str  # the id of its module in ``EnginesResult.modules``
    module: str  # import path from the repository root (decision Q1)
    function: str


CALENDAR = EntryPoint("EP2", "calendar", "engine.calendar", "build_rotation_calendar")
EROSION = EntryPoint("EP1", "erosion", "engine.erosion", "compute_soil_loss")
WATER = EntryPoint("EP3", "water", "engine.water", "compute_water_deficit_exposure")
DISCOVERED: tuple[EntryPoint, ...] = (CALENDAR, EROSION, WATER)

# PROPOSED: the module identifiers, one per entry of contracts/ENTRYPOINTS.md
# (EP1 to EP6), in the order the runner reports them.
CARBON_MODULE_IDS: tuple[str, ...] = ("residues", "amg", "rothc")
MODULE_IDS: tuple[str, ...] = (
    CALENDAR.module_id,
    EROSION.module_id,
    WATER.module_id,
    *CARBON_MODULE_IDS,
)

# The identifiers of the two carbon models, decided by the lead developer
# (issue #18, 17:29 UTC; decision D1 of #77; question 7 of
# contracts/results/README.md). The default of the app built by
# ``api.main.create_app``; ``EntryPointEngines`` itself takes them as an argument.
DEFAULT_CARBON_MODELS: tuple[str, ...] = ("amg", "rothc")

# PROPOSED detail texts: English for developers, never shown to users.
NOT_BUILT = "the module is not built yet"
CARBON_NOT_BUILT = "no carbon engine is built yet"
CARBON_MODELS_NOT_CONFIGURED = (
    "the identifiers of the carbon models are not configured "
    "(question 7 of contracts/results/README.md), so soil_carbon_trend cannot be written"
)

# PROPOSED: the start of the detail when site data belong to another field.
# The detail names the input and the identifier fields that differ, never
# their values.
OTHER_FIELD = "site data of another field than the calendar"
IDENTITY_FIELDS: tuple[str, ...] = ("case_id", "field_id")

_INPUT_NAMES = {
    "climate": "site data: climate",
    "soil_slope": "site data: soil and slope",
}


def _name(point: EntryPoint) -> str:
    return f"{point.module}.{point.function}"


@dataclass(frozen=True)
class EngineFunctions:
    """The engine entry points the runner calls. ``None``: the engine is not built."""

    # EP2
    build_rotation_calendar: Callable[..., RotationCalendar] | None = None
    # EP1
    compute_soil_loss: Callable[..., SoilLossResults | ResultsMissing] | None = None
    # EP3
    compute_water_deficit_exposure: Callable[..., list[WaterDeficitExposure]] | None = (
        None
    )


def _import_function(point: EntryPoint) -> Callable[..., Any] | None:
    """The function of one entry point, or ``None`` when it does not exist.

    Only the absence of the module itself (or of a package above it) or of the
    function means "not built". Any other import error, including a module
    that imports something absent, is a defect and propagates.
    """
    try:
        module = importlib.import_module(point.module)
    except ModuleNotFoundError as error:
        parts = point.module.split(".")
        own = {".".join(parts[: i + 1]) for i in range(len(parts))}
        if error.name in own:
            return None
        raise
    function = getattr(module, point.function, None)
    if function is None:
        return None
    if not callable(function):
        raise TypeError(f"{_name(point)} exists and is not a function")
    return function


def discover_engine_functions() -> EngineFunctions:
    """Import each engine function by its exact module path and name."""
    return EngineFunctions(
        **{point.function: _import_function(point) for point in DISCOVERED}
    )


def takes_parameters(function: Callable[..., Any]) -> bool:
    """Whether ``function`` has a parameter named ``parameters`` that a keyword can fill.

    The runner no longer uses this: it always passes ``parameters=`` to EP1 and
    EP3 (D46, D56). It is kept because ``validation/test_chain_examples.py``
    (lane L0) imports it; lane L0 may drop that use, and then this goes.
    """
    parameter = inspect.signature(function).parameters.get("parameters")
    return parameter is not None and parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


# --- counting values ----------------------------------------------------------


@dataclass(frozen=True)
class ValueCount:
    """How many indicator values are present and missing, and the first missing one."""

    present: int
    missing: int
    first_missing: ResultsMissing | None  # the ``missing`` part of the first one


def count_values(values: Iterable[IndicatorValue | PartNotBuilt]) -> ValueCount:
    """Count present and missing values, in the order given. Pure. PROPOSED.

    A part whose engine is not built (``PartNotBuilt``, D12) carries no value
    and counts as one missing value, with its own ``missing`` part.
    """
    present = missing = 0
    first: ResultsMissing | None = None
    for item in values:
        if isinstance(item, PartNotBuilt):
            missing += 1
            if first is None:
                first = item.missing
            continue
        if not isinstance(item, IndicatorValue):
            raise TypeError("count_values counts indicator values only")
        if item.value is None:
            missing += 1
            if first is None:
                first = item.missing
        else:
            present += 1
    return ValueCount(present=present, missing=missing, first_missing=first)


def _part_values(
    part: PartNotBuilt | Sequence[IndicatorValue],
) -> list[IndicatorValue | PartNotBuilt]:
    """The items of a list part, or the not-built part itself as one item."""
    if isinstance(part, PartNotBuilt):
        return [part]
    return list(part)


def soil_loss_values(
    soil_loss: SoilLossResults | SoilLossNotBuilt,
) -> list[IndicatorValue | PartNotBuilt]:
    """The annual values, then the monthly values; a not-built part as one item."""
    if isinstance(soil_loss, PartNotBuilt):
        return [soil_loss]
    return [*soil_loss.annual, *soil_loss.monthly]


def result_values(result: ResultsPerRotation) -> list[IndicatorValue | PartNotBuilt]:
    """Every indicator value of a result: soil loss, water, then carbon.

    A part in the not-built form (D12) is one item, counted as one missing
    value by ``count_values``.
    """
    return [
        *soil_loss_values(result.soil_loss),
        *_part_values(result.water_deficit_exposure),
        *_part_values(result.soil_carbon_trend),
    ]


def module_status_of(module_id: str, count: ValueCount) -> ModuleStatus:
    """The state of a module that ran, from the values of its output (PROPOSED).

    No value missing: ``available``. Some missing: ``degraded`` with the
    reason of the first missing one. All missing: ``not_available`` with it.
    """
    if count.missing == 0:
        return ModuleStatus(id=module_id, state="available")
    assert count.first_missing is not None
    total = count.present + count.missing
    state = "degraded" if count.present else "not_available"
    return ModuleStatus(
        id=module_id,
        state=state,
        reason=count.first_missing.reason,
        detail=f"{count.missing} of {total} values are missing",
    )


def calendar_status(calendar: RotationCalendar) -> ModuleStatus:
    """``available`` when feasible; ``degraded`` / ``NOT_COMPUTABLE`` otherwise."""
    if calendar.feasibility.feasible:
        return ModuleStatus(id=CALENDAR.module_id, state="available")
    return ModuleStatus(
        id=CALENDAR.module_id,
        state="degraded",
        reason="NOT_COMPUTABLE",
        detail=(
            "the calendar is not feasible: "
            f"{len(calendar.feasibility.violations)} rule violation(s)"
        ),
    )


# --- the runner ---------------------------------------------------------------


def _status(
    module_id: str, state: str, reason: ReasonCode | None, detail: str | None
) -> ModuleStatus:
    return ModuleStatus(id=module_id, state=state, reason=reason, detail=detail)  # type: ignore[arg-type]


def _not_built(point: EntryPoint) -> ModuleStatus:
    return _status(
        point.module_id,
        "not_available",
        "NOT_AVAILABLE",
        f"{NOT_BUILT}: {_name(point)}",
    )


def _missing_input(module_id: str, detail: str) -> ModuleStatus:
    return _status(module_id, "not_available", "MISSING_INPUT", detail)


def part_not_built(
    model: type[SoilLossNotBuilt | WaterDeficitExposureNotBuilt],
    point: EntryPoint,
) -> PartNotBuilt:
    """A whole part whose engine is not built, in the not-built form of D12.

    The indicator is read from the model's own field, its direction and units
    from ``DIRECTION_OF`` and ``UNITS_OF``, and the reason is the contract's
    ``REASON_OF_A_PART_NOT_BUILT``. The detail names the engine function.
    """
    (indicator,) = get_args(model.model_fields["indicator"].annotation)
    return model(
        indicator=indicator,
        direction=DIRECTION_OF[indicator],  # type: ignore[arg-type]
        units=list(UNITS_OF[indicator]),
        missing=ResultsMissing(
            reason=REASON_OF_A_PART_NOT_BUILT,  # type: ignore[arg-type]
            detail=f"{NOT_BUILT}: {_name(point)}",
        ),
    )


def _carbon_modules() -> tuple[ModuleStatus, ...]:
    return tuple(
        _status(module_id, "not_available", "NOT_AVAILABLE", CARBON_NOT_BUILT)
        for module_id in CARBON_MODULE_IDS
    )


class EntryPointEngines:
    """``RotationEngines`` on the engine entry points of contracts/ENTRYPOINTS.md.

    - ``functions``: the engine functions; usually ``discover_engine_functions()``.
    - ``load_rotation``: turns the request item ``rotation`` into the argument
      of EP2 (decision Q9). Default: ``RotationDefinition.model_validate``, so
      EP2 receives a model instance, passed on unchanged.
    - ``carbon_models``: the identifiers of the carbon models. The argument has
      no default beyond the empty tuple, and with it no ``ResultsPerRotation``
      can be written; the app uses ``DEFAULT_CARBON_MODELS``.
    - ``parameters``: the parameter catalogue, as ``params.catalogue.load_folder``
      returned it and after ``params.catalogue.check_catalogue`` reported no
      problem (the app loads and checks it at start-up, ``api/config.py``).
      Passed by keyword, the same object on every call and never copied,
      edited or filtered, to EP1 and EP3 always.
      ``None`` (the default) is the empty catalogue ``{}``, today's state of
      ``params/records/``; it reads no file (PROPOSED).
    """

    def __init__(
        self,
        functions: EngineFunctions,
        *,
        load_rotation: Callable[[Mapping[str, Any]], Any] = load_rotation_definition,
        carbon_models: Sequence[str] = (),
        parameters: dict[str, dict] | None = None,
    ) -> None:
        if not isinstance(functions, EngineFunctions):
            raise TypeError("EntryPointEngines needs EngineFunctions")
        if not callable(load_rotation):
            raise TypeError("load_rotation is a function")
        if isinstance(carbon_models, str):
            raise TypeError("carbon_models is a sequence of identifiers, not one text")
        models = tuple(carbon_models)
        if not all(isinstance(m, str) and m.strip() for m in models):
            raise ValueError("carbon_models holds non-empty identifiers")
        if len(set(models)) != len(models):
            raise ValueError("carbon_models names one model twice")
        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict):
            raise TypeError("parameters is the catalogue as loaded: a dict")
        self._functions = functions
        self._parameters = parameters
        self._load_rotation = load_rotation
        self._carbon_models = models

    @property
    def parameters(self) -> dict[str, dict]:
        """The parameter catalogue this runner passes, the object it was given."""
        return self._parameters

    def run(
        self,
        rotation: Mapping[str, Any],
        climate: ClimateResult,
        soil_slope: SoilSlopeResult,
    ) -> EnginesResult:
        functions = self._functions
        build_calendar = functions.build_rotation_calendar
        soil_loss_function = functions.compute_soil_loss
        water_function = functions.compute_water_deficit_exposure

        # 1. EP2 first.
        if build_calendar is None:
            calendar_input = f"the rotation calendar: {NOT_BUILT}: {_name(CALENDAR)}"
            return EnginesResult(
                calendar=None,
                result=None,
                result_missing=Missing(
                    reason="NOT_AVAILABLE",
                    detail=f"the calendar engine is not built: {_name(CALENDAR)}",
                ),
                modules=(
                    _not_built(CALENDAR),
                    _dependent(EROSION, soil_loss_function, calendar_input),
                    _dependent(WATER, water_function, calendar_input),
                    *_carbon_modules(),
                ),
            )
        calendar = build_calendar(self._load_rotation(rotation))
        if not isinstance(calendar, RotationCalendar):
            raise TypeError(
                f"{_name(CALENDAR)} returned {type(calendar).__name__}, not RotationCalendar"
            )
        calendar_module = calendar_status(calendar)

        # 2. The site data must be there: EP1 and EP3 take model instances (G3).
        absent = [
            name
            for name, data in (
                ("climate", climate.data),
                ("soil_slope", soil_slope.data),
            )
            if data is None
        ]
        if absent:
            detail = "input not available: " + "; ".join(
                f"{name} ({_INPUT_NAMES[name]})" for name in absent
            )
            return EnginesResult(
                calendar=calendar,
                result=None,
                result_missing=Missing(reason="MISSING_INPUT", detail=detail),
                modules=(
                    calendar_module,
                    _dependent(EROSION, soil_loss_function, detail),
                    _dependent(WATER, water_function, detail),
                    *_carbon_modules(),
                ),
            )

        # 3. The site data must belong to the calendar's field (G5): otherwise
        # the engines would raise. PROPOSED: a typed absence instead.
        other = other_field_inputs(
            calendar, climate=climate.data, soil_slope=soil_slope.data
        )
        if other:
            detail = (
                OTHER_FIELD
                + ": "
                + "; ".join(
                    f"{name} ({_INPUT_NAMES[name]}) differs in {' and '.join(fields)}"
                    for name, fields in other
                )
            )
            return EnginesResult(
                calendar=calendar,
                result=None,
                result_missing=Missing(reason="MISSING_INPUT", detail=detail),
                modules=(
                    calendar_module,
                    _dependent(EROSION, soil_loss_function, detail),
                    _dependent(WATER, water_function, detail),
                    *_carbon_modules(),
                ),
            )

        # 4. EP1 and EP3, also for an infeasible calendar (G4), each with the
        # parameter catalogue by keyword (Q3, D46, D56).
        arguments = {
            "calendar": calendar,
            "climate": climate.data,
            "soil_slope": soil_slope.data,
            "parameters": self._parameters,
        }
        soil_loss: SoilLossResults | ResultsMissing | None = None
        if soil_loss_function is None:
            erosion_module = _not_built(EROSION)
        else:
            soil_loss = soil_loss_function(**arguments)
            if isinstance(soil_loss, SoilLossResults):
                erosion_module = module_status_of(
                    EROSION.module_id, count_values(soil_loss_values(soil_loss))
                )
            elif isinstance(soil_loss, ResultsMissing):
                erosion_module = _status(
                    EROSION.module_id,
                    "not_available",
                    soil_loss.reason,
                    soil_loss.detail,
                )
            else:
                raise TypeError(
                    f"{_name(EROSION)} returned {type(soil_loss).__name__}, "
                    "not SoilLossResults or Missing"
                )

        water: list[WaterDeficitExposure] | None = None
        if water_function is None:
            water_module = _not_built(WATER)
        else:
            water = water_function(**arguments)
            if not isinstance(water, list) or not all(
                isinstance(item, WaterDeficitExposure) for item in water
            ):
                raise TypeError(
                    f"{_name(WATER)} returned {type(water).__name__}, "
                    "not a list of WaterDeficitExposure"
                )
            water_module = module_status_of(WATER.module_id, count_values(water))

        modules = (calendar_module, erosion_module, water_module, *_carbon_modules())

        def without_result(reason: ReasonCode, detail: str | None) -> EnginesResult:
            return EnginesResult(
                calendar=calendar,
                result=None,
                result_missing=Missing(reason=reason, detail=detail),
                modules=modules,
            )

        # 5. What ResultsPerRotation cannot hold.
        if isinstance(soil_loss, ResultsMissing):
            return without_result(soil_loss.reason, soil_loss.detail)
        if not self._carbon_models:
            return without_result("NOT_AVAILABLE", CARBON_MODELS_NOT_CONFIGURED)

        # 6. Assemble. A part whose engine is not built takes the not-built
        # form (D12); a part whose engine ran is its output, unchanged.
        result = ResultsPerRotation(
            case_id=calendar.case_id,
            field_id=calendar.field_id,
            rotation_id=calendar.rotation_id,
            soil_loss=(
                soil_loss
                if soil_loss is not None
                else part_not_built(SoilLossNotBuilt, EROSION)
            ),
            water_deficit_exposure=(
                water
                if water is not None
                else part_not_built(WaterDeficitExposureNotBuilt, WATER)
            ),
            soil_carbon_trend=missing_carbon_trend(self._carbon_models),
        )
        count = count_values(result_values(result))
        return EnginesResult(
            calendar=calendar,
            result=result,
            result_missing=None,
            modules=modules,
            values_present=count.present,
            values_missing=count.missing,
        )


def other_field_inputs(
    calendar: RotationCalendar, **inputs: Any
) -> list[tuple[str, tuple[str, ...]]]:
    """Each input whose ``case_id`` or ``field_id`` differs from the calendar's.

    Returns ``(input name, identifier fields that differ)`` in the order given.
    Pure; compares the identifiers only. PROPOSED.
    """
    other = []
    for name, data in inputs.items():
        fields = tuple(
            field
            for field in IDENTITY_FIELDS
            if getattr(data, field) != getattr(calendar, field)
        )
        if fields:
            other.append((name, fields))
    return other


def _dependent(
    point: EntryPoint, function: Callable[..., Any] | None, missing_input: str
) -> ModuleStatus:
    """A module that was not called: not built, or one of its inputs is missing."""
    if function is None:
        return _not_built(point)
    return _missing_input(point.module_id, missing_input)


def missing_carbon_trend(carbon_models: Sequence[str]) -> list[SoilCarbonTrend]:
    """For each carbon model, the three computations of C1.6, missing ``NOT_AVAILABLE``.

    The identifier, the direction and the unit are kept (C3.1); they come from
    contracts/results/models.py.
    """
    indicator = "soil_carbon_trend"
    return [
        SoilCarbonTrend(
            indicator=indicator,
            direction=DIRECTION_OF[indicator],  # type: ignore[arg-type]
            value=None,
            unit=UNIT_SOIL_CARBON_TREND,
            missing=ResultsMissing(reason="NOT_AVAILABLE", detail=CARBON_NOT_BUILT),
            carbon_model=carbon_model,
            computation=computation,  # type: ignore[arg-type]
        )
        for carbon_model in carbon_models
        for computation in TREND_COMPUTATIONS
    ]
