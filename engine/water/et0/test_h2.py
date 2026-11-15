"""[H2] of docs/VALIDATION.md: the reference evapotranspiration against a worked FAO-56 example.

Run with ``python -m pytest engine/water/et0/`` from the repository root.

The worked example issue #13 identifies is EXAMPLE 18 of Chapter 4 of FAO-56
("Determination of ETo with daily data"). That example is given relative
humidity, hours of sunshine and wind at another height, while this engine
takes dew point, solar radiation and wind at 2 m (D25 to D27). So the test
enters the example's own rows for the actual vapour pressure (Eq. 17), the
solar radiation (Eq. 35) and the wind speed at 2 m (Eq. 47), and checks
every step this engine computes against the example's rows. Whether that is
an acceptable definition of [H2] is OPEN (engine/water/et0/README.md).

Decision D124 of issue #77 fixed the expected values and the tolerance before
any run (docs/VALIDATION.md, "Section 10"): the expected reference
evapotranspiration is the one of the Eq. 6 line of the example, and each step
is compared within half a unit of the last digit the example prints, the soil
heat flux exactly.

**This file holds no value of the example.** ``EXAMPLE_18``, ``CONSTANTS``
and ``BOUNDS`` are read from the signed fixture ``FIXTURE``
(validation/fixtures/h2_example18.json; path PROPOSED, format in
validation/fixtures/README.md). The test skips, naming the file and what is
not signed, while the file is absent or any value in it lacks ``checked_by``.
The fixture arrives in its own commit, signed by a person (D34, D66).

The other tests below run the loader and the comparison on a PLACEHOLDER
fixture written to a temporary folder. Their numbers come from the
PLACEHOLDER constants of test_equations.py: none is a value of the science.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from contracts.results.models import Missing
from engine.water.et0.constants import Et0Bounds, Et0Constants
from engine.water.et0.daily import Et0Steps, reference_evapotranspiration_day
from engine.water.exposure import ET0_BOUND_PARAMETERS, ET0_PARAMETERS
from params.catalogue import check_record

ROOT = Path(__file__).resolve().parents[3]

# PROPOSED path of the signed fixture (issue #225).
FIXTURE = ROOT / "validation" / "fixtures" / "h2_example18.json"
FIXTURE_NAME = FIXTURE.relative_to(ROOT).as_posix()

WAITS_FOR = (
    "[H2] waits for the signed fixture "
    f"{FIXTURE_NAME}: the inputs, intermediate results and final value of "
    "FAO-56 Chapter 4 EXAMPLE 18 with the tolerance of each step fixed by "
    "D124 of issue #77, and the constants of the table in "
    "engine/water/et0/README.md with the two bounds of D82, each transcribed "
    "and signed in checked_by by a person (D34 of issue #77)"
)

# The eight inputs of reference_evapotranspiration_day. The latitude is given
# in radians, or in degrees and converted by FAO-56 Eq. 22 (degrees times pi
# over 180), a definition and not a value of the example. PROPOSED.
INPUTS = (
    "day_of_year",
    "elevation",
    "temperature_max",
    "temperature_min",
    "actual_vapour_pressure",
    "wind_speed_2m",
    "solar_radiation",
)
LATITUDE_FORMS = ("latitude_radians", "latitude_degrees")

# The fields of Et0Steps that are quantities (the last two are tuples of names).
STEP_FIELDS = tuple(
    item.name
    for item in dataclasses.fields(Et0Steps)
    if item.name not in ("bounds_changed", "bounds_not_applied")
)

# D124: the soil heat flux is compared exactly.
EXACT_STEPS = ("soil_heat_flux",)
FINAL_STEP = "reference_evapotranspiration"

# The parameter identifiers EP3 reads (engine/water/exposure.py), by field.
CONSTANT_IDS = {
    group: {name: f"{group}_{name}" for name in names}
    for group, names in ET0_PARAMETERS.items()
}
BOUND_IDS = ET0_BOUND_PARAMETERS

# A number as the example prints it: digits, an optional point and decimals.
PRINTED = re.compile(r"-?\d+(\.\d+)?")

# Rounding of floating-point arithmetic only, used to compare a tolerance
# with the one D124 gives. Not a tolerance of the validation protocol.
FLOAT_NOISE = 1e-12


# --- reading the fixture -----------------------------------------------------


@dataclasses.dataclass(frozen=True)
class H2Case:
    """What the test needs, read from a signed fixture."""

    inputs: dict[str, float]
    steps: dict[str, float]
    printed: dict[str, str]
    tolerance: dict[str, float]
    constants: Et0Constants
    bounds: Et0Bounds


def _is_text(item: object) -> bool:
    return isinstance(item, str) and item.strip() != ""


def _records_by_id(fixture: dict, key: str) -> dict[str, Any]:
    records = fixture.get(key, [])
    assert isinstance(records, list), f"'{key}' must be a list of parameter records"
    by_id: dict[str, Any] = {}
    for record in records:
        assert isinstance(record, dict), f"'{key}': every item is a parameter record"
        identifier = record.get("id")
        assert identifier not in by_id, f"'{key}': '{identifier}' is given twice"
        by_id[identifier] = record
    return by_id


def _expected_ids() -> dict[str, list[str]]:
    return {
        "constants": [i for group in CONSTANT_IDS.values() for i in group.values()],
        "bounds": [i for group in BOUND_IDS.values() for i in group.values()],
    }


def unsigned(fixture: dict) -> list[str]:
    """Every part of the fixture that has no ``checked_by``, by name.

    The ``checked_by`` of the file signs its inputs, steps and tolerances;
    each constant and each bound is a parameter record with its own. A
    constant or a bound that is absent is not signed either.
    """
    missing = []
    if not _is_text(fixture.get("checked_by")):
        missing.append("checked_by of the file (inputs, steps, tolerance)")
    for key, identifiers in _expected_ids().items():
        by_id = _records_by_id(fixture, key)
        for identifier in identifiers:
            record = by_id.get(identifier)
            if record is None:
                missing.append(f"{key} record '{identifier}' (absent)")
            elif not _is_text(record.get("checked_by")):
                missing.append(f"checked_by of {key} record '{identifier}'")
    return missing


def skip_reason(path: Path) -> str | None:
    """Why the test cannot run on ``path``, or ``None`` when it can."""
    if not path.is_file():
        return f"{WAITS_FOR}. The file is absent, so nothing is signed (no checked_by)"
    missing = unsigned(read_fixture(path))
    if missing:
        return f"{WAITS_FOR}. Not signed yet: " + "; ".join(missing)
    return None


def read_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict), f"{path.name}: the fixture is one JSON object"
    return fixture


def _number(entry: object, where: str) -> float:
    assert isinstance(entry, dict), f"{where}: expected an object with 'value'"
    value = entry.get("value")
    assert isinstance(value, (int, float)) and not isinstance(value, bool), (
        f"{where}: 'value' must be a number"
    )
    assert math.isfinite(value), f"{where}: 'value' must be finite"
    return float(value)


def half_unit_of_last_printed_digit(printed: str) -> float:
    """D124: half a unit of the last digit the example prints."""
    assert PRINTED.fullmatch(printed), f"'{printed}' is not a printed number"
    decimals = len(printed.partition(".")[2])
    return 0.5 * 10.0**-decimals


def _parameter(record: dict, where: str) -> float:
    problems = check_record(record)
    assert not problems, f"{where}: " + "; ".join(problems)
    assert record["value"] is not None, f"{where}: the record has no value"
    return float(record["value"])


def load_case(fixture: dict) -> H2Case:
    """The case of a signed fixture; a malformed fixture fails, it is not skipped."""
    inputs_entry = fixture.get("inputs")
    assert isinstance(inputs_entry, dict), "'inputs' must be an object"
    latitude = [name for name in LATITUDE_FORMS if name in inputs_entry]
    assert len(latitude) == 1, f"'inputs' needs exactly one of {LATITUDE_FORMS}"
    assert set(inputs_entry) == set(INPUTS) | set(latitude), (
        f"'inputs' must hold {INPUTS} and the latitude, nothing else"
    )
    inputs = {name: _number(inputs_entry[name], f"inputs.{name}") for name in INPUTS}
    latitude_value = _number(inputs_entry[latitude[0]], f"inputs.{latitude[0]}")
    if latitude[0] == "latitude_degrees":
        latitude_value = math.radians(latitude_value)
    inputs["latitude_radians"] = latitude_value

    steps_entry = fixture.get("steps")
    assert isinstance(steps_entry, dict), "'steps' must be an object"
    unknown = set(steps_entry) - set(STEP_FIELDS)
    assert not unknown, f"'steps': not fields of Et0Steps: {sorted(unknown)}"
    assert FINAL_STEP in steps_entry, f"'steps' must hold {FINAL_STEP}"
    steps, printed = {}, {}
    for name, entry in steps_entry.items():
        steps[name] = _number(entry, f"steps.{name}")
        printed[name] = entry.get("printed")
        assert isinstance(printed[name], str), f"steps.{name}: 'printed' is text"
        assert float(printed[name]) == steps[name], (
            f"steps.{name}: 'value' is not the number of 'printed'"
        )

    tolerance = fixture.get("tolerance")
    assert isinstance(tolerance, dict), "'tolerance' must be an object"
    assert set(tolerance) == set(steps), "'tolerance' needs one entry per step"

    constants_by_id = _records_by_id(fixture, "constants")
    bounds_by_id = _records_by_id(fixture, "bounds")
    expected = _expected_ids()
    assert set(constants_by_id) == set(expected["constants"]), (
        "'constants' must hold exactly the parameters EP3 reads"
    )
    assert set(bounds_by_id) == set(expected["bounds"]), (
        "'bounds' must hold exactly the two bounds of D82"
    )
    constant_groups = get_type_hints(Et0Constants)
    bound_groups = get_type_hints(Et0Bounds)
    constants = Et0Constants(
        **{
            group: constant_groups[group](
                **{
                    name: _parameter(constants_by_id[identifier], identifier)
                    for name, identifier in names.items()
                }
            )
            for group, names in CONSTANT_IDS.items()
        }
    )
    bounds = Et0Bounds(
        **{
            group: bound_groups[group](
                **{
                    name: _parameter(bounds_by_id[identifier], identifier)
                    for name, identifier in names.items()
                }
            )
            for group, names in BOUND_IDS.items()
        }
    )
    return H2Case(
        inputs=inputs,
        steps=steps,
        printed=printed,
        tolerance={name: tolerance[name] for name in steps},
        constants=constants,
        bounds=bounds,
    )


# --- comparing ---------------------------------------------------------------


def tolerance_problems(case: H2Case) -> list[str]:
    """Each tolerance of the fixture that is not the one D124 gives."""
    problems = []
    for name, given in case.tolerance.items():
        if name in EXACT_STEPS:
            rule = 0.0
        else:
            rule = half_unit_of_last_printed_digit(case.printed[name])
        if not isinstance(given, (int, float)) or abs(given - rule) > FLOAT_NOISE:
            problems.append(
                f"tolerance.{name} is {given!r}; D124 gives {rule!r} for the printed "
                f"'{case.printed[name]}'"
            )
    return problems


def comparison_failures(case: H2Case) -> list[str]:
    """Each step the engine computes outside its tolerance, or does not compute."""
    computed_steps = reference_evapotranspiration_day(
        **case.inputs, constants=case.constants, bounds=case.bounds
    )
    failures = []
    for name, expected in case.steps.items():
        computed = getattr(computed_steps, name)
        if isinstance(computed, Missing):
            failures.append(
                f"{name}: not computed ({computed.reason}: {computed.detail})"
            )
            continue
        tolerance = 0.0 if name in EXACT_STEPS else case.tolerance[name]
        if computed != pytest.approx(expected, abs=tolerance, rel=0):
            failures.append(
                f"{name}: computed {computed!r}, expected {expected!r} within {tolerance!r}"
            )
    return failures


def run_h2(path: Path) -> list[str]:
    """Every problem of the H2 check on the signed fixture at ``path``."""
    case = load_case(read_fixture(path))
    return tolerance_problems(case) + comparison_failures(case)


# --- the check ---------------------------------------------------------------


def test_h2_worked_example_18_of_fao_56():
    reason = skip_reason(FIXTURE)
    if reason is not None:
        pytest.skip(reason)
    problems = run_h2(FIXTURE)
    assert not problems, "\n".join(problems)


def test_h2_the_skip_says_what_it_waits_for():
    assert "EXAMPLE 18" in WAITS_FOR
    assert "D34" in WAITS_FOR
    assert "D124" in WAITS_FOR
    assert "tolerance" in WAITS_FOR
    assert "D82" in WAITS_FOR
    assert FIXTURE_NAME in WAITS_FOR


# --- the loader and the comparison on a PLACEHOLDER fixture -----------------


def _placeholder_record(identifier: str, value: float, *, checked: bool) -> dict:
    return {
        "id": identifier,
        "scope": {},
        "value": value,
        "unit": "PLACEHOLDER unit",
        "range": None,
        "range_missing_reason": "PLACEHOLDER: no range",
        "citation": {
            "reference": "PLACEHOLDER reference, not a publication",
            "locator": "PLACEHOLDER locator",
        },
        "transcribed_by": "PLACEHOLDER person one",
        "checked_by": "PLACEHOLDER person two" if checked else "",
    }


def _printed(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def placeholder_fixture(*, checked: bool = True) -> dict:
    """A fixture in the documented format, with PLACEHOLDER numbers only.

    The inputs and constants are those of test_daily.py and test_equations.py.
    The expected steps are what this engine computes on them, printed with a
    PLACEHOLDER number of decimals, so the comparison passes by construction:
    the test exercises the reading and the comparison, not the science.
    """
    from engine.water.et0.test_daily import DAY
    from engine.water.et0.test_equations import (
        PLACEHOLDER_BOUNDS,
        PLACEHOLDER_CONSTANTS,
    )

    computed = reference_evapotranspiration_day(
        **DAY, constants=PLACEHOLDER_CONSTANTS, bounds=PLACEHOLDER_BOUNDS
    )
    names = ("mean_temperature", "slope", "net_radiation", "soil_heat_flux", FINAL_STEP)
    steps, tolerance = {}, {}
    for decimals, name in enumerate(names):
        printed = _printed(
            getattr(computed, name), 0 if name in EXACT_STEPS else decimals
        )
        steps[name] = {
            "value": float(printed),
            "unit": "PLACEHOLDER",
            "printed": printed,
        }
        tolerance[name] = (
            0.0 if name in EXACT_STEPS else half_unit_of_last_printed_digit(printed)
        )
    constants = [
        _placeholder_record(
            identifier,
            getattr(getattr(PLACEHOLDER_CONSTANTS, group), name),
            checked=checked,
        )
        for group, ids in CONSTANT_IDS.items()
        for name, identifier in ids.items()
    ]
    bounds = [
        _placeholder_record(
            identifier,
            getattr(getattr(PLACEHOLDER_BOUNDS, group), name),
            checked=checked,
        )
        for group, ids in BOUND_IDS.items()
        for name, identifier in ids.items()
    ]
    return {
        "test": "PLACEHOLDER fixture of the H2 machinery",
        "source": {
            "reference": "PLACEHOLDER, not a publication",
            "locator": "PLACEHOLDER",
        },
        "transcribed_by": "PLACEHOLDER person one",
        "checked_by": "PLACEHOLDER person two" if checked else "",
        "inputs": {
            name: {"value": value, "unit": "PLACEHOLDER"} for name, value in DAY.items()
        },
        "steps": steps,
        "tolerance": tolerance,
        "tolerance_rule": "PLACEHOLDER: D124",
        "constants": constants,
        "bounds": bounds,
    }


def write(tmp_path: Path, fixture: dict) -> Path:
    path = tmp_path / FIXTURE.name
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def test_h2_absent_fixture_skips_naming_the_file_and_the_signature(tmp_path):
    reason = skip_reason(tmp_path / FIXTURE.name)
    assert reason is not None
    assert FIXTURE_NAME in reason
    assert "absent" in reason
    assert "checked_by" in reason


def test_h2_unsigned_fixture_skips_naming_what_is_not_signed(tmp_path):
    reason = skip_reason(write(tmp_path, placeholder_fixture(checked=False)))
    assert reason is not None
    assert FIXTURE_NAME in reason
    assert "checked_by of the file" in reason
    assert "net_longwave_stefan_boltzmann" in reason
    assert "penman_monteith_minimum_wind_speed" in reason


def test_h2_one_unsigned_constant_is_enough_to_skip(tmp_path):
    fixture = placeholder_fixture()
    fixture["constants"][0]["checked_by"] = ""
    reason = skip_reason(write(tmp_path, fixture))
    assert reason is not None
    assert fixture["constants"][0]["id"] in reason
    assert "checked_by of the file" not in reason


def test_h2_absent_bound_is_not_signed(tmp_path):
    fixture = placeholder_fixture()
    gone = fixture["bounds"].pop()
    reason = skip_reason(write(tmp_path, fixture))
    assert reason is not None
    assert f"'{gone['id']}' (absent)" in reason


def test_h2_signed_placeholder_fixture_runs_and_passes(tmp_path):
    path = write(tmp_path, placeholder_fixture())
    assert skip_reason(path) is None
    assert run_h2(path) == []


def test_h2_latitude_in_degrees_is_converted(tmp_path):
    fixture = placeholder_fixture()
    radians = fixture["inputs"].pop("latitude_radians")["value"]
    fixture["inputs"]["latitude_degrees"] = {"value": math.degrees(radians)}
    case = load_case(fixture)
    assert case.inputs["latitude_radians"] == pytest.approx(radians, abs=FLOAT_NOISE)


def test_h2_value_outside_its_tolerance_fails(tmp_path):
    fixture = placeholder_fixture()
    step = fixture["steps"]["slope"]
    decimals = len(step["printed"].partition(".")[2])
    moved = _printed(step["value"] + 10.0**-decimals, decimals)
    step["value"], step["printed"] = float(moved), moved
    problems = run_h2(write(tmp_path, fixture))
    assert len(problems) == 1
    assert problems[0].startswith("slope:")


def test_h2_the_comparison_uses_the_tolerance_of_each_step():
    case = load_case(placeholder_fixture())
    computed = reference_evapotranspiration_day(
        **case.inputs, constants=case.constants, bounds=case.bounds
    ).net_radiation
    inside, outside = dict(case.steps), dict(case.steps)
    inside["net_radiation"] = computed + 0.9 * case.tolerance["net_radiation"]
    outside["net_radiation"] = computed + 1.1 * case.tolerance["net_radiation"]
    assert comparison_failures(dataclasses.replace(case, steps=inside)) == []
    failures = comparison_failures(dataclasses.replace(case, steps=outside))
    assert len(failures) == 1
    assert failures[0].startswith("net_radiation:")


def test_h2_soil_heat_flux_is_compared_exactly(tmp_path):
    fixture = placeholder_fixture()
    fixture["tolerance"]["soil_heat_flux"] = 0.5
    problems = run_h2(write(tmp_path, fixture))
    assert any(p.startswith("tolerance.soil_heat_flux") for p in problems)


def test_h2_a_tolerance_other_than_the_rule_of_d124_fails(tmp_path):
    fixture = placeholder_fixture()
    fixture["tolerance"][FINAL_STEP] *= 2
    problems = run_h2(write(tmp_path, fixture))
    assert len(problems) == 1
    assert problems[0].startswith(f"tolerance.{FINAL_STEP}")


def test_h2_value_that_is_not_its_printed_number_fails(tmp_path):
    fixture = placeholder_fixture()
    fixture["steps"]["slope"]["value"] += 1.0
    with pytest.raises(AssertionError, match="steps.slope"):
        load_case(fixture)


def test_h2_malformed_constant_fails_and_is_not_skipped(tmp_path):
    fixture = placeholder_fixture()
    del fixture["constants"][0]["citation"]
    path = write(tmp_path, fixture)
    assert skip_reason(path) is None
    with pytest.raises(AssertionError, match=fixture["constants"][0]["id"]):
        run_h2(path)


def test_h2_half_unit_of_the_last_printed_digit():
    # Arithmetic of the rule of D124 on PLACEHOLDER printed numbers.
    assert half_unit_of_last_printed_digit("7") == 0.5
    assert half_unit_of_last_printed_digit("7.7") == pytest.approx(0.05)
    assert half_unit_of_last_printed_digit("77.777") == pytest.approx(0.0005)
    with pytest.raises(AssertionError):
        half_unit_of_last_printed_digit("7,7")
