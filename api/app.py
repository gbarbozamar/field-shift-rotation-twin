"""The application builder: ``create_app`` and the CORS origin parser.

``create_app`` is the one place the application is put together from its
implementations; tests pass fakes to it. ``api.config.build_app`` calls it with
the implementations named by configuration, and ``api/main.py`` holds the app
a server runs. Both names are re-exported by ``api/main.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, Literal

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from adapters.ports import ClimateSource
from api.decision_layer import DecisionLayer, DiscoveredDecisionLayer, import_named
from api.decisions import make_decision_router
from api.engines import (
    DEFAULT_CARBON_MODELS,
    EntryPointEngines,
    discover_engine_functions,
)
from api.errors import ErrorCode, error_response, install_error_handlers
from api.ports import RotationEngines, RotationValidator, RunSettings, SoilSlopeSource
from api.rotation_validator import RotationDefinitionValidator
from api.rotations import make_router
from api.standins import ClimateUnavailable, SoilSlopeNotLoaded

logger = logging.getLogger(__name__)

# PROPOSED (review of #310, point 2): the plant layer is found by name on each
# request, as the decision layer is (api/decision_layer.py), never imported
# when the app is built: a plant layer that fails to load never stops
# ``/health`` or another route. Not there: ``200`` with the answer ``null``
# and its reason ``NOT_AVAILABLE``.
PLANT_ROUTE = "/api/plant/run"
PLANT_MODULE = "api.plant"
PLANT_FUNCTION = "run_plant"
PLANT_NOT_BUILT = f"the plant layer is not built yet: {PLANT_MODULE}.{PLANT_FUNCTION}"

# Builds the engines of a rain-stress run from a parameter catalogue (the same
# type as ``api.plant.EnginesFactory``, written here so nothing of the plant
# layer is imported when the app is built).
EnginesFactory = Callable[[dict[str, dict]], RotationEngines]
PlantLayer = Callable[..., Any]


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
    plant_layer: PlantLayer | None = None,
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

    PROPOSED (unit ``l2/plant-route``, review of #310), for
    ``POST /api/plant/run`` only: ``plant_layer`` answers the route; ``None``
    means ``api.plant.run_plant`` found by name on each request
    (``PLANT_MODULE``, ``PLANT_FUNCTION``), never when the app is built.
    ``kinds_of_year_record`` is the ONI record the kinds of year are
    classified on, already read by the caller; ``None`` means no record is
    configured, and the answer gives every kind of year missing with its
    reason. No record is read here. ``engines_factory`` builds the engines of
    a rain-stress run from the catalogue whose erosivity is scaled; ``None``
    means, with the default engines, ``EntryPointEngines`` on the same engine
    functions, and with ``engines`` given, no factory (the answer says the
    factor was not applied, and why).
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

    # The catalogue the plant route scales for a rain-stress run is the one the
    # default engines use (``parameters``, or ``{}`` for None); with
    # ``engines`` given it is not known (None), and a factory is not called.
    plant_catalogue = None if engines is not None else (parameters or {})
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

    @app.post(PLANT_ROUTE, responses={400: {}, 422: {}, 500: {}})
    def run_plant(body: dict[str, Any] = Body(...)):  # noqa: B008
        """Answer "What should I plant?" for one field and three to five rotations."""
        try:
            layer = (
                plant_layer
                if plant_layer is not None
                else import_named(PLANT_MODULE, PLANT_FUNCTION)
            )
        except Exception:
            logger.exception("POST %s: the plant layer failed to load", PLANT_ROUTE)
            return error_response(ErrorCode.INTERNAL_ERROR)
        if layer is None:
            return JSONResponse(
                content={
                    "answer": None,
                    "answer_missing": {
                        "reason": "NOT_AVAILABLE",
                        "detail": PLANT_NOT_BUILT,
                    },
                }
            )
        return layer(
            body,
            **shared,
            kinds_of_year_record=kinds_of_year_record,
            engines_factory=engines_factory,
            parameters=plant_catalogue,
        )

    return app
