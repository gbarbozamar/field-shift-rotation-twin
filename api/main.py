"""Backend application: the app a server runs (``api.main:app``).

Run locally with ``uv run uvicorn api.main:app --reload`` from the
repository root, or in a container with ``docker compose watch``
(edits reload the server; http://localhost:8000/health).

The app is assembled from environment variables by ``api/config.py``
(see api/README.md, "Configuration"). An empty or blank value counts as unset.
A piece that is not configured is a typed absence; a piece that is configured
wrongly raises ``ConfigError`` naming the variable, and the server does not
start. No variable has a default.

- ``CORS_ORIGINS``: comma-separated origins allowed to call the API from a
  browser, e.g. ``http://localhost:5173,https://gbarbozamar.github.io``.
  Unset: no cross-origin access.
- ``POWER_SETTINGS_FILE``: path of the JSON settings file of the NASA POWER
  adapter (``PowerSettings.from_mapping``). Unset: the climate source is the
  stand-in (``unavailable`` / ``NOT_AVAILABLE``).
- ``CLIMATE_CACHE_DIR``: folder of the climate response cache. Required when
  ``POWER_SETTINGS_FILE`` is set; ignored otherwise.
- ``CLIMATE_START_DATE``, ``CLIMATE_END_DATE``: the climate record period,
  ``YYYY-MM-DD``, inclusive; both or neither. Unset: the climate source is not
  called.
- ``SOIL_SLOPE_EXAMPLE_FILE``: path of the accepted soil-and-slope contract
  example, served as ``example``. Unset: the soil-and-slope source is the
  stand-in.
- ``SOIL_TABLE_FILES`` (comma-separated paths of soil tables) and
  ``SOIL_GROUPS_FILE`` (the soil group of each field): both or neither, and
  never with ``SOIL_SLOPE_EXAMPLE_FILE``. Set: the soil-and-slope source is
  ``adapters.soil_tables.SoilTableSource`` (soil by soil group, D48, D49;
  slope not built).
- ``KINDS_OF_YEAR_RECORD_FILE``: path of the ONI record the plant route
  classifies the kinds of year on, read once at start-up. Unset: every kind
  of year of a plant answer is missing ``NOT_AVAILABLE``.
- ``RAIN_STRESS_TEST``: exactly ``on`` switches the heavier-rain stress test
  of ``POST /api/plant/run`` on; any other value stops start-up. Unset: off,
  a declared rain-stress factor is echoed not applied.

The parameter catalogue is not a variable: ``load_config`` loads it once from
``params/records/`` and checks it; a problem stops start-up, an empty
catalogue does not.

``create_app`` (in ``api/app.py``) stays the way tests inject fakes; it and
``parse_origins`` are re-exported here.
"""

from __future__ import annotations

import os

from api.app import Health, create_app, parse_origins
from api.config import build_app, load_config

__all__ = ["Health", "app", "create_app", "parse_origins"]

app = build_app(load_config(os.environ))
