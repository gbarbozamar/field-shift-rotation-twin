"""The running app, assembled from configuration (environment variables).

``load_config(environ)`` reads the variables below from the mapping it is
given (never from ``os.environ`` itself) and returns an ``AppConfig``.
``build_app(config)`` turns it into the application with ``create_app``.

Two rules carry the design:

- A piece that is **not configured** stays a typed absence: the stand-ins of
  ``api/standins.py``, or no climate record period. That is the app of today.
- A piece that is **configured wrongly** is a deploy defect: ``ConfigError``,
  whose message names the variable and what is wrong, so the server does not
  start. A message never contains the content of a file, only its path and
  the reason.

Every value a person decides arrives as configuration; nothing here has a
default. An empty or blank value counts as unset.

Status: PROPOSED (blueprint section 3.7), including the variable names, the
rules above and the message texts.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import ValidationError

from adapters.cache import FileCache
from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.power import PowerClimateSource, PowerSettings
from api.app import create_app, parse_origins
from api.ports import RunSettings
from contracts.inputs import SiteSoilSlope

# --- the variables (PROPOSED names) -------------------------------------------

CORS_ORIGINS = "CORS_ORIGINS"
POWER_SETTINGS_FILE = "POWER_SETTINGS_FILE"
CLIMATE_CACHE_DIR = "CLIMATE_CACHE_DIR"
CLIMATE_START_DATE = "CLIMATE_START_DATE"
CLIMATE_END_DATE = "CLIMATE_END_DATE"
SOIL_SLOPE_EXAMPLE_FILE = "SOIL_SLOPE_EXAMPLE_FILE"

VARIABLES: tuple[str, ...] = (
    CORS_ORIGINS,
    POWER_SETTINGS_FILE,
    CLIMATE_CACHE_DIR,
    CLIMATE_START_DATE,
    CLIMATE_END_DATE,
    SOIL_SLOPE_EXAMPLE_FILE,
)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

ClientFactory = Callable[[PowerSettings], httpx.Client]


class ConfigError(Exception):
    """The configuration is wrong: the server must not start. Names the variable."""


@dataclass(frozen=True)
class ClimateConfig:
    """The climate source: its settings and the folder of its cache."""

    settings: PowerSettings
    cache_dir: Path


@dataclass(frozen=True)
class AppConfig:
    """What the environment configures. ``None``: not configured (an absence)."""

    cors_origins: tuple[str, ...] = ()
    climate: ClimateConfig | None = None
    run_settings: RunSettings = field(default_factory=RunSettings)
    soil_slope_example_file: Path | None = None


# --- reading the variables ----------------------------------------------------


def _value(environ: Mapping[str, str], name: str) -> str | None:
    """The value of one variable, stripped; ``None`` when unset, empty or blank."""
    value = environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _read_file(name: str, path: Path) -> str:
    if not path.is_file():
        raise ConfigError(f"{name}: the file '{path}' does not exist")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise ConfigError(
            f"{name}: the file '{path}' cannot be read as UTF-8 text"
        ) from None


def _load_power_settings(path: Path) -> PowerSettings:
    text = _read_file(POWER_SETTINGS_FILE, path)
    try:
        document: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"{POWER_SETTINGS_FILE}: the file '{path}' is not valid JSON "
            f"(line {error.lineno}, column {error.colno})"
        ) from None
    try:
        return PowerSettings.from_mapping(document)
    except (TypeError, ValueError) as error:
        raise ConfigError(
            f"{POWER_SETTINGS_FILE}: the settings in '{path}' are rejected: {error}"
        ) from None


def _climate(environ: Mapping[str, str]) -> ClimateConfig | None:
    settings_file = _value(environ, POWER_SETTINGS_FILE)
    if settings_file is None:
        return None  # CLIMATE_CACHE_DIR alone is harmless: ignored
    cache_dir = _value(environ, CLIMATE_CACHE_DIR)
    if cache_dir is None:
        raise ConfigError(
            f"{CLIMATE_CACHE_DIR} is required when {POWER_SETTINGS_FILE} is set"
        )
    return ClimateConfig(
        settings=_load_power_settings(Path(settings_file)), cache_dir=Path(cache_dir)
    )


def _date(environ: Mapping[str, str], name: str) -> dt.date | None:
    value = _value(environ, name)
    if value is None:
        return None
    if not _DATE.fullmatch(value):
        raise ConfigError(f"{name} is not a date in the form YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ConfigError(f"{name} is not a calendar date (YYYY-MM-DD)") from None


def _run_settings(environ: Mapping[str, str]) -> RunSettings:
    start = _date(environ, CLIMATE_START_DATE)
    end = _date(environ, CLIMATE_END_DATE)
    if (start is None) != (end is None):
        given, absent = (
            (CLIMATE_START_DATE, CLIMATE_END_DATE)
            if start is not None
            else (CLIMATE_END_DATE, CLIMATE_START_DATE)
        )
        raise ConfigError(f"{given} is set without {absent}: set both or neither")
    if start is not None and end is not None and start > end:
        raise ConfigError(f"{CLIMATE_START_DATE} is after {CLIMATE_END_DATE}")
    return RunSettings(start_date=start, end_date=end)


def _soil_slope_example(environ: Mapping[str, str]) -> Path | None:
    value = _value(environ, SOIL_SLOPE_EXAMPLE_FILE)
    if value is None:
        return None
    path = Path(value)
    text = _read_file(SOIL_SLOPE_EXAMPLE_FILE, path)
    try:
        data = SiteSoilSlope.model_validate_json(text)
    except ValidationError:
        raise ConfigError(
            f"{SOIL_SLOPE_EXAMPLE_FILE}: the file '{path}' does not load into "
            "the contract model SiteSoilSlope"
        ) from None
    if not data.example_data:
        raise ConfigError(
            f"{SOIL_SLOPE_EXAMPLE_FILE}: the file '{path}' is not marked as "
            "example data (example_data is false)"
        )
    return path


def load_config(environ: Mapping[str, str]) -> AppConfig:
    """Read the configuration from ``environ`` only. Raises ``ConfigError``."""
    return AppConfig(
        cors_origins=tuple(parse_origins(_value(environ, CORS_ORIGINS))),
        climate=_climate(environ),
        run_settings=_run_settings(environ),
        soil_slope_example_file=_soil_slope_example(environ),
    )


# --- assembly -----------------------------------------------------------------


def default_client(settings: PowerSettings) -> httpx.Client:
    """A plain ``httpx.Client`` with the configured timeout."""
    return httpx.Client(timeout=settings.timeout_seconds)


def _close_on_shutdown(app: FastAPI, client: httpx.Client) -> None:
    """Close ``client`` when the app shuts down, after its own lifespan."""
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: Any) -> AsyncIterator[Any]:
        try:
            async with inner(application) as state:
                yield state
        finally:
            client.close()

    app.router.lifespan_context = lifespan


def build_app(
    config: AppConfig, *, client_factory: ClientFactory | None = None
) -> FastAPI:
    """The application ``config`` describes. Nothing configured: today's app.

    ``client_factory`` makes the HTTP client of the climate source from its
    settings (default: ``default_client``); the client is closed when the app
    shuts down. Engines and the rotation validator are the defaults of
    ``create_app``.
    """
    if not isinstance(config, AppConfig):
        raise TypeError("build_app needs an AppConfig")
    climate = None
    client = None
    if config.climate is not None:
        factory = client_factory if client_factory is not None else default_client
        client = factory(config.climate.settings)
        climate = PowerClimateSource(
            config.climate.settings, FileCache(config.climate.cache_dir), client
        )
    soil_slope = (
        ExampleSoilSlopeSource(config.soil_slope_example_file)
        if config.soil_slope_example_file is not None
        else None
    )
    app = create_app(
        list(config.cors_origins),
        climate=climate,
        soil_slope=soil_slope,
        settings=config.run_settings,
    )
    if client is not None:
        _close_on_shutdown(app, client)
    return app
