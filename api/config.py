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

The parameter catalogue is not a variable: contracts/ENTRYPOINTS.md names its
folder, ``params/records/`` of the repository, found from the location of the
``params`` package (never from the working directory). ``load_config`` loads
it once with ``params.catalogue.load_folder`` and checks it with
``params.catalogue.check_catalogue``; any problem of either is a
``ConfigError`` naming the folder and listing the problems, one per line. An
empty catalogue is not a problem (Q3, D46, D56 of issue #77).

``KINDS_OF_YEAR_RECORD_FILE`` (PROPOSED, unit ``l2/plant-layer-by-name``,
S-031) names the ONI record the plant route classifies the kinds of year on,
such as ``kinds_of_year/records/oni_v6.json``. Unset or blank: no record (the
plant answer gives every kind of year missing ``NOT_AVAILABLE``), and
``kinds_of_year`` is not imported. Set: the file is read once, here, the
fields the plant layer reads are checked (``RECORD_FIELDS``) and the record
is classified once by ``kinds_of_year.classify_agricultural_years``; a file
that does not exist, is not JSON, is not an object, lacks one of them or is
refused by the classification, or a ``kinds_of_year`` that cannot be
imported, is a ``ConfigError`` naming the variable.
``build_app`` passes the record to ``create_app``; it is never read again on
a request.

``RAIN_STRESS_TEST`` (PROPOSED, unit ``l2/rain-stress-switch``, S-032,
decision R25) switches the heavier-rain stress test of the plant route on.
Unset or blank: off (a declared factor is echoed not applied, with its
reason). The only accepted value is exactly ``on`` (after stripping spaces);
any other value is a ``ConfigError`` naming the variable, never repeating the
value.

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

import params
from adapters.cache import FileCache
from adapters.example_soil_slope import ExampleSoilSlopeSource
from adapters.power import PowerClimateSource, PowerSettings
from adapters.soil_tables import (
    SoilFileError,
    SoilTableSource,
    check_tables,
    load_soil_groups,
    load_soil_table,
)
from api.app import create_app, parse_origins
from api.ports import RunSettings
from contracts.inputs import SiteSoilSlope
from params.catalogue import RECORDS_FOLDER, check_catalogue, load_folder

# --- the variables (PROPOSED names) -------------------------------------------

CORS_ORIGINS = "CORS_ORIGINS"
POWER_SETTINGS_FILE = "POWER_SETTINGS_FILE"
CLIMATE_CACHE_DIR = "CLIMATE_CACHE_DIR"
CLIMATE_START_DATE = "CLIMATE_START_DATE"
CLIMATE_END_DATE = "CLIMATE_END_DATE"
SOIL_SLOPE_EXAMPLE_FILE = "SOIL_SLOPE_EXAMPLE_FILE"
SOIL_TABLE_FILES = "SOIL_TABLE_FILES"
SOIL_GROUPS_FILE = "SOIL_GROUPS_FILE"
KINDS_OF_YEAR_RECORD_FILE = "KINDS_OF_YEAR_RECORD_FILE"
RAIN_STRESS_TEST = "RAIN_STRESS_TEST"
# PROPOSED (S-032): the one value of RAIN_STRESS_TEST that switches it on.
SWITCHED_ON = "on"

VARIABLES: tuple[str, ...] = (
    CORS_ORIGINS,
    POWER_SETTINGS_FILE,
    CLIMATE_CACHE_DIR,
    CLIMATE_START_DATE,
    CLIMATE_END_DATE,
    SOIL_SLOPE_EXAMPLE_FILE,
    SOIL_TABLE_FILES,
    SOIL_GROUPS_FILE,
    KINDS_OF_YEAR_RECORD_FILE,
    RAIN_STRESS_TEST,
)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# The folder of the parameter catalogue (contracts/ENTRYPOINTS.md, Q3):
# ``params/records/``, resolved from the ``params`` package.
PARAMETERS_FOLDER = Path(params.__file__).resolve().parent / RECORDS_FOLDER

ClientFactory = Callable[[PowerSettings], httpx.Client]


class ConfigError(Exception):
    """The configuration is wrong: the server must not start. Names the variable."""


@dataclass(frozen=True)
class ClimateConfig:
    """The climate source: its settings and the folder of its cache."""

    settings: PowerSettings
    cache_dir: Path


@dataclass(frozen=True)
class SoilTablesConfig:
    """The soil-table source: its tables, in order, and the soil-groups declaration."""

    table_files: tuple[Path, ...]
    groups_file: Path


@dataclass(frozen=True)
class AppConfig:
    """What the environment configures. ``None``: not configured (an absence)."""

    cors_origins: tuple[str, ...] = ()
    climate: ClimateConfig | None = None
    run_settings: RunSettings = field(default_factory=RunSettings)
    soil_slope_example_file: Path | None = None
    soil_tables: SoilTablesConfig | None = None
    # The parameter catalogue as loaded and checked; ``{}`` when it is empty.
    parameters: dict[str, dict] = field(default_factory=dict)
    # PROPOSED (S-031): the ONI record KINDS_OF_YEAR_RECORD_FILE names, read
    # and checked once; ``None`` when the variable is not set.
    kinds_of_year_record: Mapping[str, Any] | None = None
    # PROPOSED (S-032): RAIN_STRESS_TEST=on; off when the variable is not set.
    rain_stress_switched_on: bool = False


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


def _soil_tables(environ: Mapping[str, str]) -> SoilTablesConfig | None:
    """``SOIL_TABLE_FILES`` and ``SOIL_GROUPS_FILE``: both or neither. PROPOSED.

    Every file is loaded and the tables are checked together at start-up, so a
    wrong file stops the server; the source reads them again on each call.
    """
    tables_value = _value(environ, SOIL_TABLE_FILES)
    groups_value = _value(environ, SOIL_GROUPS_FILE)
    if tables_value is None and groups_value is None:
        return None
    if tables_value is None or groups_value is None:
        given, absent = (
            (SOIL_TABLE_FILES, SOIL_GROUPS_FILE)
            if tables_value is not None
            else (SOIL_GROUPS_FILE, SOIL_TABLE_FILES)
        )
        raise ConfigError(f"{given} is set without {absent}: set both or neither")
    if _value(environ, SOIL_SLOPE_EXAMPLE_FILE) is not None:
        raise ConfigError(
            f"{SOIL_SLOPE_EXAMPLE_FILE} is set together with {SOIL_TABLE_FILES} "
            f"and {SOIL_GROUPS_FILE}: one soil-and-slope source at a time"
        )
    parts = [part.strip() for part in tables_value.split(",")]
    if any(not part for part in parts):
        raise ConfigError(f"{SOIL_TABLE_FILES} has an empty item in its list")
    table_files = tuple(Path(part) for part in parts)
    if len(set(table_files)) != len(table_files):
        raise ConfigError(f"{SOIL_TABLE_FILES} names one file twice")
    tables = []
    for path in table_files:
        _read_file(SOIL_TABLE_FILES, path)
        try:
            tables.append(load_soil_table(path))
        except SoilFileError as error:
            raise ConfigError(
                f"{SOIL_TABLE_FILES}: the file '{path}' is rejected: {error}"
            ) from None
    try:
        check_tables(tables)
    except SoilFileError as error:
        raise ConfigError(f"{SOIL_TABLE_FILES}: {error}") from None
    groups_file = Path(groups_value)
    _read_file(SOIL_GROUPS_FILE, groups_file)
    try:
        load_soil_groups(groups_file)
    except SoilFileError as error:
        raise ConfigError(
            f"{SOIL_GROUPS_FILE}: the file '{groups_file}' is rejected: {error}"
        ) from None
    return SoilTablesConfig(table_files=table_files, groups_file=groups_file)


# PROPOSED (S-031): the fields of the ONI record the plant layer reads (the
# source row and the kinds of year: ``economics.plant`` and
# ``kinds_of_year.classify``). Their presence is checked here; then the
# record is read once the way the classification reads it
# (``_check_by_classifying``), so a rule or a season row the classification
# would refuse stops the server here, not on a request (fix round 1, F3).
RECORD_TEXT_FIELDS = ("id", "reference", "date_read")
RECORD_FIELDS = (*RECORD_TEXT_FIELDS, "threshold", "min_consecutive_seasons", "seasons")
# PROPOSED (fix round 1, F3): the start month the start-up check classifies
# on. Any month reads the same rule and the same season rows; January (C5.1:
# January = 1) is only the first.
RECORD_CHECK_START_MONTH = 1


def _check_by_classifying(path: Path, record: dict[str, Any]) -> None:
    """Classify every agricultural year the record's seasons name. PROPOSED (F3).

    ``kinds_of_year.classify_agricultural_years`` checks the threshold, the
    run length and every season row before it classifies; a ``ValueError``,
    ``TypeError`` or ``KeyError`` it raises is a ``ConfigError`` naming
    ``KINDS_OF_YEAR_RECORD_FILE``. ``kinds_of_year`` absent or failing to
    import is a ``ConfigError`` too (F4), its cause chained.
    """
    try:
        from kinds_of_year import classify_agricultural_years
    except ImportError as error:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE} is set but the kinds_of_year package "
            "that reads the record cannot be imported"
        ) from error
    years = [
        row["year"]
        for row in record["seasons"]
        if isinstance(row, Mapping)
        and isinstance(row.get("year"), int)
        and not isinstance(row.get("year"), bool)
    ]
    if not years:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: in the record in '{path}', no row of "
            "seasons has an integer year"
        )
    try:
        classify_agricultural_years(
            record, min(years), max(years), RECORD_CHECK_START_MONTH
        )
    except (ValueError, TypeError, KeyError) as error:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: the record in '{path}' is rejected by "
            f"the classification of the kinds of year: {error}"
        ) from None


def _kinds_of_year_record(environ: Mapping[str, str]) -> Mapping[str, Any] | None:
    """``KINDS_OF_YEAR_RECORD_FILE``: the ONI record, read once. PROPOSED (S-031).

    Unset or blank: ``None``, and ``kinds_of_year`` is not imported. Set: the
    file must exist and be read as UTF-8 text holding a JSON object, the
    fields of ``RECORD_FIELDS`` must be there (the three of
    ``RECORD_TEXT_FIELDS`` non-blank text, ``seasons`` a non-empty list), and
    the classification of the kinds of year must accept it
    (``_check_by_classifying``); otherwise ``ConfigError`` naming the
    variable, and the server does not start (F9 of review-whole-4: checked
    here, never per request).
    """
    value = _value(environ, KINDS_OF_YEAR_RECORD_FILE)
    if value is None:
        return None
    path = Path(value)
    text = _read_file(KINDS_OF_YEAR_RECORD_FILE, path)
    try:
        record: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: the file '{path}' is not valid JSON "
            f"(line {error.lineno}, column {error.colno})"
        ) from None
    if not isinstance(record, dict):
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: the file '{path}' is not a JSON object"
        )
    absent = [name for name in RECORD_FIELDS if name not in record]
    if absent:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: the record in '{path}' has no field "
            + ", ".join(absent)
        )
    blank = [
        name
        for name in RECORD_TEXT_FIELDS
        if not isinstance(record[name], str) or not record[name].strip()
    ]
    if blank:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: in the record in '{path}', "
            + ", ".join(blank)
            + " is not a non-blank text"
        )
    if not isinstance(record["seasons"], list) or not record["seasons"]:
        raise ConfigError(
            f"{KINDS_OF_YEAR_RECORD_FILE}: in the record in '{path}', seasons is "
            "not a non-empty list"
        )
    _check_by_classifying(path, record)
    return record


def _rain_stress_switched_on(environ: Mapping[str, str]) -> bool:
    """``RAIN_STRESS_TEST``: exactly ``on``, or unset. PROPOSED (S-032, R25).

    The message of a wrong value names the variable, never the value.
    """
    value = _value(environ, RAIN_STRESS_TEST)
    if value is None:
        return False
    if value != SWITCHED_ON:
        raise ConfigError(
            f"{RAIN_STRESS_TEST} has a value other than '{SWITCHED_ON}': set it "
            f"to '{SWITCHED_ON}' to switch the heavier-rain stress test on, or "
            "leave it unset"
        )
    return True


def load_parameters(folder: Path) -> dict[str, dict]:
    """The parameter catalogue under ``folder``, loaded and checked.

    Returns exactly what ``load_folder`` returned, never edited, filled or
    filtered. Raises ``ConfigError`` when ``load_folder`` or
    ``check_catalogue`` reports any problem; the message names the folder and
    lists the problems as those functions wrote them, one per line. An empty
    catalogue is returned as ``{}``. PROPOSED.
    """
    records, problems = load_folder(folder)
    if not problems:
        problems = check_catalogue(records)
    if problems:
        listed = "\n".join(problems)
        raise ConfigError(
            f"the parameter catalogue in '{folder}' has {len(problems)} "
            f"problem(s):\n{listed}"
        )
    return records


def load_config(
    environ: Mapping[str, str], *, parameters_folder: Path = PARAMETERS_FOLDER
) -> AppConfig:
    """Read the configuration from ``environ`` only. Raises ``ConfigError``.

    The parameter catalogue is read from ``parameters_folder``, by default
    ``params/records/`` of the repository; tests give another folder.
    """
    return AppConfig(
        cors_origins=tuple(parse_origins(_value(environ, CORS_ORIGINS))),
        climate=_climate(environ),
        run_settings=_run_settings(environ),
        soil_slope_example_file=_soil_slope_example(environ),
        soil_tables=_soil_tables(environ),
        parameters=load_parameters(parameters_folder),
        kinds_of_year_record=_kinds_of_year_record(environ),
        rain_stress_switched_on=_rain_stress_switched_on(environ),
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
    ``create_app``; the engines get the parameter catalogue of ``config``.
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
    if config.soil_slope_example_file is not None and config.soil_tables is not None:
        raise ConfigError("one soil-and-slope source at a time")
    soil_slope: ExampleSoilSlopeSource | SoilTableSource | None = None
    if config.soil_slope_example_file is not None:
        soil_slope = ExampleSoilSlopeSource(config.soil_slope_example_file)
    elif config.soil_tables is not None:
        soil_slope = SoilTableSource(
            config.soil_tables.table_files, config.soil_tables.groups_file
        )
    app = create_app(
        list(config.cors_origins),
        climate=climate,
        soil_slope=soil_slope,
        settings=config.run_settings,
        parameters=config.parameters,
        kinds_of_year_record=config.kinds_of_year_record,
        rain_stress_switched_on=config.rain_stress_switched_on,
    )
    if client is not None:
        _close_on_shutdown(app, client)
    return app
