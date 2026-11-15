"""The application builder: ``create_app`` and the CORS origin parser.

``create_app`` is the one place the application is put together from its
implementations; tests pass fakes to it. ``api.config.build_app`` calls it with
the implementations named by configuration, and ``api/main.py`` holds the app
a server runs. Both names are re-exported by ``api/main.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adapters.ports import ClimateSource
from api.decision_layer import DecisionLayer, DiscoveredDecisionLayer
from api.decisions import make_decision_router
from api.engines import (
    DEFAULT_CARBON_MODELS,
    EntryPointEngines,
    discover_engine_functions,
)
from api.errors import install_error_handlers
from api.plant import EnginesFactory, make_plant_router
from api.ports import RotationEngines, RotationValidator, RunSettings, SoilSlopeSource
from api.rotation_validator import RotationDefinitionValidator
from api.rotations import make_router
from api.standins import ClimateUnavailable, SoilSlopeNotLoaded
from kinds_of_year import load_record


class Health(BaseModel):
    """Response of the liveness route."""

    status: Literal["ok"]


def parse_origins(value: str | None) -> list[str]:
    """Split a comma-separated origin list; blanks and trailing slashes dropped."""
    if not value:
        return []
    return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]


def create_app(
    cors_origins: list[str],
    *,
    climate: ClimateSource | None = None,
    soil_slope: SoilSlopeSource | None = None,
    engines: RotationEngines | None = None,
    rotation_validator: RotationValidator | None = None,
    settings: RunSettings | None = None,
    parameters: dict[str, dict] | None = None,
    decision_layer: DecisionLayer | None = None,
    kinds_of_year_record: Mapping[str, Any] | None = None,
    engines_factory: EnginesFactory | None = None,
) -> FastAPI:
    """Build the application. ``None`` for an implementation means its default.

    The default engines are ``EntryPointEngines`` on the engine functions found
    at their paths of contracts/ENTRYPOINTS.md, with the carbon model
    identifiers ``DEFAULT_CARBON_MODELS``. The default rotation validator loads the item into
    ``RotationDefinition``. The two sources default to the stand-ins of
    ``api/standins.py``.
    ``settings=None`` means no climate record period is configured (OPEN for
    the science reviewers).
    ``parameters`` is the parameter catalogue the default engines pass to EP1
    and EP3 (Q3, D46, D56 of issue #77), already loaded and checked by the
    caller (``api.config.build_app`` does both at start-up). ``None`` is the
    empty catalogue ``{}``; no file is read here. It is not used when
    ``engines`` is given, so giving both is a ``TypeError``.
    ``decision_layer`` turns a results table into a decision output for
    ``POST /api/decisions/run``; ``None`` means ``DiscoveredDecisionLayer``,
    which looks the function of ``decision/`` up by name on each request,
    never when the app is built (``api/decision_layer.py``), and answers "not
    built" when it is not there. The three routes share the same sources,
    engines, validator and settings.

    PROPOSED (unit ``l2/plant-route``), both for ``POST /api/plant/run`` only:
    ``kinds_of_year_record`` is the ONI record the kinds of year are
    classified on; ``None`` loads the committed one
    (``kinds_of_year.load_record()``) once, here. ``engines_factory`` builds
    the engines of a run with a rain-stress factor from the catalogue whose
    erosivity is scaled (``parameters`` or ``{}``, through
    ``api.rain_stress.scale_erosivity``). ``None`` means: with the default
    engines, ``EntryPointEngines`` on the same engine functions; with
    ``engines`` given, no factory, and the answer says the factor was not
    applied, and why.
    """
    if engines is not None and parameters is not None:
        raise TypeError(
            "parameters is for the default engines; give it to the engines passed in"
        )
    app = FastAPI(title="Field Shift Rotation Twin")
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        """Liveness: the process is up and answering. Checks nothing else."""
        return Health(status="ok")

    if engines is None:
        functions = discover_engine_functions()

        def default_factory(catalogue: dict[str, dict]) -> RotationEngines:
            return EntryPointEngines(
                functions, carbon_models=DEFAULT_CARBON_MODELS, parameters=catalogue
            )

        engines = EntryPointEngines(
            functions, carbon_models=DEFAULT_CARBON_MODELS, parameters=parameters
        )
        if engines_factory is None:
            engines_factory = default_factory
    shared = {
        "climate": climate if climate is not None else ClimateUnavailable(),
        "soil_slope": soil_slope if soil_slope is not None else SoilSlopeNotLoaded(),
        "engines": engines,
        "rotation_validator": (
            rotation_validator
            if rotation_validator is not None
            else RotationDefinitionValidator()
        ),
        "settings": settings if settings is not None else RunSettings(),
    }
    app.include_router(make_router(**shared))
    app.include_router(
        make_decision_router(
            **shared,
            decision_layer=(
                decision_layer
                if decision_layer is not None
                else DiscoveredDecisionLayer()
            ),
        )
    )
    app.include_router(
        make_plant_router(
            **shared,
            kinds_of_year_record=(
                kinds_of_year_record
                if kinds_of_year_record is not None
                else load_record()
            ),
            engines_factory=engines_factory,
            parameters=parameters if parameters is not None else {},
        )
    )

    return app
