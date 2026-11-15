"""Acceptance test of the heavier-rain switch (S-032, decision R25).

Run with ``uv run pytest api/test_rain_stress_switch.py`` from the repository
root.

Status: PROPOSED test cases, ported from ``api/test_rain_stress_switch.py`` of
branch ``l2/rain-stress-switch`` (commits 624a12e, 29d07b6) to the structure
of this branch. Fakes only: the climate, the soil and slope and the engines
are the fakes of api/test_plant.py and api/test_rotations.py; no network and
no real service. Every expected value is read from the example files or from
the module under test, never typed here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import test_plant as plant_tests
from api.config import RAIN_STRESS_TEST, ConfigError, build_app, load_config
from api.main import create_app
from api.plant import NOT_SWITCHED_ON, stressed_run

ROUTE = plant_tests.ROUTE
REQUEST = plant_tests.REQUEST
FACTOR = REQUEST["questions"]["rain_stress_factor"]


def _client(**kwargs) -> TestClient:
    """The test_plant client, without its default switch: off unless given."""
    kwargs.setdefault("rain_stress_switched_on", False)
    return plant_tests.client(**kwargs)


def _soil_loss(data: dict) -> list:
    return [option["soil_loss"] for option in data["options"]]


# --- the variable ------------------------------------------------------------------


@pytest.mark.parametrize(
    "environ", [{}, {RAIN_STRESS_TEST: ""}, {RAIN_STRESS_TEST: "  "}]
)
def test_unset_or_blank_is_off(environ):
    assert load_config(environ).rain_stress_switched_on is False


@pytest.mark.parametrize("value", ["on", " on "])
def test_on_switches_it_on(value):
    assert load_config({RAIN_STRESS_TEST: value}).rain_stress_switched_on is True


@pytest.mark.parametrize("value", ["yes", "ON", "true", "1", "off"])
def test_any_other_value_is_a_config_error_that_never_repeats_it(value):
    with pytest.raises(ConfigError) as caught:
        load_config({RAIN_STRESS_TEST: value})
    message = str(caught.value)
    assert RAIN_STRESS_TEST in message
    assert f"'{value}'" not in message


# --- the plant route ---------------------------------------------------------------


def test_switched_off_a_declared_factor_is_not_applied_and_no_factory_runs():
    factory = plant_tests.Factory()
    data = plant_tests.answered(
        _client(engines_factory=factory).post(ROUTE, json=REQUEST)
    )
    plant_tests.checked(REQUEST, data)
    echo = data["rain_stress"]
    assert echo["applied"] is False
    assert NOT_SWITCHED_ON in echo["detail"]
    # The public detail names no server variable.
    assert RAIN_STRESS_TEST not in echo["detail"]
    assert factory.catalogues == []
    assert factory.engines.calls == []

    # The soil loss equals the one of the same request with no factor.
    plain_request = plant_tests.body(rain_stress_factor=None)
    plain = plant_tests.answered(_client().post(ROUTE, json=plain_request))
    assert plain["rain_stress"] is None
    assert _soil_loss(data) == _soil_loss(plain)


def test_create_app_default_is_off():
    """The PLACEHOLDER request on create_app with no switch: not applied."""
    factory = plant_tests.Factory()
    app = create_app(
        [],
        climate=plant_tests.FakeClimate(),
        soil_slope=plant_tests.FakeSoilSlope(),
        settings=plant_tests.PERIOD,
        parameters=plant_tests.CATALOGUE,
        engines_factory=factory,
        kinds_of_year_record=plant_tests.load_record(),
    )
    data = plant_tests.answered(TestClient(app).post(ROUTE, json=REQUEST))
    assert data["rain_stress"]["applied"] is False
    assert NOT_SWITCHED_ON in data["rain_stress"]["detail"]
    assert factory.catalogues == []


def test_create_app_default_never_calls_its_default_factory(monkeypatch):
    """With no factory given, the default one (EntryPointEngines on a scaled
    catalogue) is not built per request either."""
    import api.app as app_module

    built = []
    real = app_module.EntryPointEngines

    def counting(*args, **kwargs):
        built.append(kwargs.get("parameters"))
        return real(*args, **kwargs)

    monkeypatch.setattr(app_module, "EntryPointEngines", counting)
    app = create_app([], parameters=plant_tests.CATALOGUE)
    assert len(built) == 1  # the engines of the app, built once
    data = plant_tests.answered(TestClient(app).post(ROUTE, json=REQUEST))
    assert data["rain_stress"]["applied"] is False
    assert len(built) == 1


def test_switched_on_the_factor_is_applied_as_today():
    factory = plant_tests.Factory()
    data = plant_tests.answered(
        _client(engines_factory=factory, rain_stress_switched_on=True).post(
            ROUTE, json=REQUEST
        )
    )
    assert len(factory.catalogues) == 1
    assert len(factory.engines.calls) == len(REQUEST["rotations"])
    assert data["rain_stress"]["applied"] is True
    example = plant_tests.PlantAnswer.model_validate(plant_tests.ANSWER).model_dump(
        mode="json"
    )
    assert data["rain_stress"] == example["rain_stress"]


def test_switched_off_no_factor_gives_no_echo():
    request = plant_tests.body(rain_stress_factor=None)
    data = plant_tests.answered(_client().post(ROUTE, json=request))
    assert data["rain_stress"] is None


def test_switched_off_a_missing_factor_gives_the_missing_echo():
    factor = {
        "value": None,
        "unit": FACTOR["unit"],
        "missing": {"reason": "NOT_DECLARED"},
    }
    factory = plant_tests.Factory()
    request = plant_tests.body(rain_stress_factor=factor)
    data = plant_tests.answered(
        _client(engines_factory=factory).post(ROUTE, json=request)
    )
    assert data["rain_stress"]["missing"] == {"reason": "NOT_DECLARED", "detail": None}
    assert factory.catalogues == []


def test_stressed_run_switched_off_applies_nothing():
    factory, calls = plant_tests._counting_factory()
    engines = plant_tests.FakeEngines()
    request = plant_tests.PlantRequest.model_validate(REQUEST)
    run = stressed_run(
        request, engines, factory, plant_tests.CATALOGUE, rain_stress_switched_on=False
    )
    assert calls == []
    assert run.engines is engines
    assert run.echo.applied is False
    assert NOT_SWITCHED_ON in run.echo.detail
    assert RAIN_STRESS_TEST not in run.echo.detail


def test_stressed_run_needs_the_switch():
    """Only create_app keeps a default; a forgotten pass below it fails."""
    request = plant_tests.PlantRequest.model_validate(REQUEST)
    with pytest.raises(TypeError):
        stressed_run(  # type: ignore[call-arg]
            request, plant_tests.FakeEngines(), None, plant_tests.CATALOGUE
        )


# --- build_app follows the variable --------------------------------------------------


@pytest.mark.parametrize(
    ("environ", "applied"), [({}, False), ({RAIN_STRESS_TEST: "on"}, True)]
)
def test_build_app_passes_the_switch_to_the_plant_route(environ, applied):
    # No climate source configured: the stand-in, never a real service.
    app = build_app(load_config(environ))
    data = plant_tests.answered(TestClient(app).post(ROUTE, json=REQUEST))
    assert data["rain_stress"]["applied"] is applied
    if not applied:
        assert NOT_SWITCHED_ON in data["rain_stress"]["detail"]
