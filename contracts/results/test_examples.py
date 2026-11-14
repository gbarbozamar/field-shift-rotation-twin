"""Acceptance test of the results contracts.

Run with ``python -m pytest contracts/results/`` from the repository root.

Each example loads into its model, and each invalid variant is rejected.
A variant is an example with one thing changed, in memory only. The cases
are PROPOSED (blueprint section 3.7) and are listed with the same codes in
contracts/results/README.md under "PROPOSED cases". Every number here is a
placeholder: it means nothing and no case holds an expected value of the
science.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from contracts.results import models
from contracts.results.models import ResultsPerRotation, ResultsTable

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
README = HERE / "README.md"
CONVENTIONS = HERE.parent / "CONVENTIONS.md"

WORD = "PLACEHOLDER"
TABLE = "PLACEHOLDER_results_table.json"
ROTATION = "PLACEHOLDER_results_per_rotation.json"
NOT_BUILT = "PLACEHOLDER_results_per_rotation_not_built.json"
MODEL_OF = {
    TABLE: ResultsTable,
    ROTATION: ResultsPerRotation,
    NOT_BUILT: ResultsPerRotation,
}
BOTH = (TABLE, ROTATION)

SOURCE = "PLACEHOLDER source"
KIND = "PLACEHOLDER_range_kind"
NO_RANGE = {"reason": "NOT_AVAILABLE", "detail": "PLACEHOLDER detail"}


def example(name):
    """The parsed content of one example file."""
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def load(name, document):
    """Load a document into the model of its contract, from JSON text."""
    return MODEL_OF[name].model_validate_json(json.dumps(document))


def assert_rejected(name, document, expected):
    """The document is rejected, for one reason, and the reason is the expected one."""
    with pytest.raises(ValidationError) as caught:
        load(name, document)
    error = caught.value
    assert error.error_count() == 1, str(error)
    assert expected in str(error), f"expected '{expected}' in: {error}"


# --- what a case changes -----------------------------------------------------


def values_of(name, document):
    """Every indicator value of a document, as parsed JSON objects."""
    if name == TABLE:
        return document["rows"]
    values = []
    soil_loss = document["soil_loss"]
    if "missing" not in soil_loss:  # a part wholly missing holds no value (D12)
        values += [*soil_loss["annual"], *soil_loss["monthly"]]
    for part in ("water_deficit_exposure", "soil_carbon_trend"):
        if isinstance(document[part], list):
            values += document[part]
    return values


def first(name, document, condition):
    return next(item for item in values_of(name, document) if condition(item))


def whole(name, document):
    return document


def number_with_range(name, document):
    return first(name, document, lambda item: item.get("range") is not None)


def number_without_range(name, document):
    return first(name, document, lambda item: item.get("range_missing") is not None)


def missing_value(name, document):
    return first(name, document, lambda item: item["value"] is None)


def soil_loss_number(name, document):
    return first(
        name,
        document,
        lambda item: (
            item["indicator"] == "soil_loss"
            and item["value"] is not None
            and item["unit"] == models.UNIT_SOIL_LOSS_ANNUAL
        ),
    )


def water(name, document):
    return first(
        name, document, lambda item: item["indicator"] == "water_deficit_exposure"
    )


def carbon_number(name, document):
    return first(
        name,
        document,
        lambda item: (
            item["indicator"] == "soil_carbon_trend" and item["value"] is not None
        ),
    )


def the_range(name, document):
    return number_with_range(name, document)["range"]


def the_reason(name, document):
    return missing_value(name, document)["missing"]


def soil_loss_section(name, document):
    return document["soil_loss"]


def annual(name, document):
    return document["soil_loss"]["annual"]


def monthly(name, document):
    return document["soil_loss"]["monthly"]


def first_month(name, document):
    return document["soil_loss"]["monthly"][0]


def water_values(name, document):
    return document["water_deficit_exposure"]


def carbon_values(name, document):
    return document["soil_carbon_trend"]


def rows(name, document):
    return document["rows"]


def drop(*keys):
    def change(target):
        for key in keys:
            del target[key]

    return change


def put(**fields):
    def change(target):
        target.update(copy.deepcopy(fields))

    return change


def put_at(index, **fields):
    def change(items):
        items[index].update(copy.deepcopy(fields))

    return change


def drop_at(index, *keys):
    def change(items):
        for key in keys:
            del items[index][key]

    return change


def remove(index):
    def change(items):
        del items[index]

    return change


def repeat(index, **fields):
    """Append a copy of one item, with some fields replaced."""

    def change(items):
        items.append({**copy.deepcopy(items[index]), **copy.deepcopy(fields)})

    return change


def empty(items):
    items.clear()


def bounds_equal_to_the_value(item):
    item["range"].update(low=item["value"], high=item["value"])


def value_below_low(item):
    item["value"] = item["range"]["low"] - 1.0


def value_above_high(item):
    item["value"] = item["range"]["high"] + 1.0


def low_above_high(item):
    item["range"]["low"] = item["range"]["high"] + 1.0


def relabel_first_ag_year(document):
    """Call the first agricultural year by a calendar year it does not begin in."""
    old = document["soil_loss"]["annual"][0]["ag_year"]
    for item in [*document["soil_loss"]["annual"], *document["soil_loss"]["monthly"]]:
        if item["ag_year"] == old:
            item["ag_year"] = old - 2


def remove_months_of_last_year(document):
    last = document["soil_loss"]["annual"][-1]["ag_year"]
    document["soil_loss"]["monthly"] = [
        item for item in document["soil_loss"]["monthly"] if item["ag_year"] != last
    ]


def add_water_by_year_next_to_water_by_rotation(items):
    for item in [
        item for item in items if item["indicator"] == "water_deficit_exposure"
    ]:
        items.append({**copy.deepcopy(item), "time_basis": "ag_year", "ag_year": 2001})


# --- the invalid variants ----------------------------------------------------

FIELD_REQUIRED = "Field required"
NOT_A_NUMBER = "Input should be a valid number"
NOT_FINITE = "Input should be a finite number"
NOT_AN_INTEGER = "Input should be a valid integer"
NOT_TEXT = "Input should be a valid string"
NOT_AN_OBJECT = "Input should be an object"
BLANK = "must not be empty or blank"
EXTRA = "Extra inputs are not permitted"
AT_LEAST_ONE = "at least 1 item"
NOT_THE_UNIT = "is not the unit of"
NO_SUCH_INDICATOR = "Input should be 'soil_loss'"
NO_SUCH_DIRECTION = "Input should be 'lower_is_better' or 'higher_is_better'"
NO_SUCH_LABEL = "Input should be 'DECLARED', 'OBSERVED', 'DERIVED' or 'SIMULATED'"
NO_SUCH_REASON = "Input should be 'NOT_DECLARED', 'SOURCE_UNAVAILABLE', 'NO_COVERAGE'"
NO_SUCH_COMPUTATION = (
    "Input should be 'end_minus_start', 'fitted_slope' or 'mean_over_cycles'"
)
NO_SUCH_TIME_BASIS = "Input should be 'ag_year' or 'rotation'"
NEITHER = "neither a number nor a 'missing' part"
NUMBER_AND_REASON = "a number together with a 'missing' part"
THREE_COMPUTATIONS = "must carry each of the three computations once"
NO_SUCH_MODEL = "Input should be 'amg' or 'rothc'"


@dataclass(frozen=True)
class Case:
    code: str
    title: str
    pick: Callable
    change: Callable
    expected: str
    examples: tuple[str, ...] = BOTH


REJECTED = [
    # U: unit (C1.1 to C1.5)
    Case(
        "U1",
        "value without a unit: field absent",
        number_with_range,
        drop("unit"),
        FIELD_REQUIRED,
    ),
    Case(
        "U1",
        "missing value without a unit",
        missing_value,
        drop("unit"),
        FIELD_REQUIRED,
    ),
    Case("U2", "unit is null", number_with_range, put(unit=None), NOT_TEXT),
    Case("U2", "unit is empty", number_with_range, put(unit=""), NOT_THE_UNIT),
    Case(
        "U3",
        "unit spelt another way",
        soil_loss_number,
        put(unit="t/ha/yr"),
        NOT_THE_UNIT,
    ),
    Case(
        "U3",
        "unit in another letter case",
        water,
        put(unit="Dimensionless"),
        NOT_THE_UNIT,
    ),
    Case(
        "U4",
        "unit of another indicator",
        soil_loss_number,
        put(unit=models.UNIT_SOIL_CARBON_TREND),
        NOT_THE_UNIT,
    ),
    Case(
        "U5",
        "annual soil loss in the monthly unit",
        soil_loss_number,
        put(unit=models.UNIT_SOIL_LOSS_MONTHLY),
        "is in 't ha-1 yr-1', not in 't ha-1 month-1'",
    ),
    Case(
        "U5",
        "monthly soil loss in the annual unit",
        first_month,
        put(unit=models.UNIT_SOIL_LOSS_ANNUAL),
        "is in 't ha-1 month-1', not in 't ha-1 yr-1'",
        (ROTATION,),
    ),
    # P: provenance label and source (C4.1, C4.2, C4.6)
    Case(
        "P1",
        "value without a provenance label: field absent",
        number_with_range,
        drop("provenance"),
        "a value needs a provenance label",
    ),
    Case(
        "P1",
        "value without a provenance label: null",
        number_with_range,
        put(provenance=None),
        "a value needs a provenance label",
    ),
    Case(
        "P2",
        "label not in the list",
        number_with_range,
        put(provenance="MEASURED"),
        NO_SUCH_LABEL,
    ),
    Case(
        "P2",
        "label in lower case",
        number_with_range,
        put(provenance="derived"),
        NO_SUCH_LABEL,
    ),
    Case(
        "P3",
        "missing value with a provenance label",
        missing_value,
        put(provenance="DERIVED"),
        "a missing value carries no provenance label",
    ),
    Case(
        "P4",
        "soil loss with a label other than DERIVED",
        soil_loss_number,
        put(provenance="SIMULATED"),
        "(C4.6)",
    ),
    Case(
        "P5",
        "value without a source and without the assumption mark",
        number_with_range,
        drop("source"),
        "a value needs a source or the assumption mark",
    ),
    Case(
        "P5",
        "value with a source and the assumption mark",
        number_with_range,
        put(assumption=True),
        "not both",
    ),
    Case("P5", "blank source", number_with_range, put(source="  "), BLANK),
    Case(
        "P5",
        "assumption mark that is not true or false",
        number_with_range,
        put(assumption="yes"),
        "Input should be a valid boolean",
    ),
    Case(
        "P6",
        "missing value with a source",
        missing_value,
        put(source=SOURCE),
        "a missing value carries no source",
    ),
    # M: missing value and its reason (C3.1, C3.2)
    Case(
        "M1",
        "missing value without a reason: no 'missing' part",
        missing_value,
        drop("missing"),
        NEITHER,
    ),
    Case(
        "M1",
        "missing value without a reason: 'missing' is null",
        missing_value,
        put(missing=None),
        NEITHER,
    ),
    Case(
        "M1",
        "missing value without a reason: 'reason' absent",
        the_reason,
        drop("reason"),
        FIELD_REQUIRED,
    ),
    Case(
        "M1",
        "missing value without a reason: 'reason' is null",
        the_reason,
        put(reason=None),
        NO_SUCH_REASON,
    ),
    Case(
        "M1",
        "missing value without a reason: 'reason' is empty",
        the_reason,
        put(reason=""),
        NO_SUCH_REASON,
    ),
    Case(
        "M2",
        "reason code not in the list",
        the_reason,
        put(reason="UNKNOWN"),
        NO_SUCH_REASON,
    ),
    Case(
        "M2",
        "reason code in lower case",
        the_reason,
        put(reason="no_coverage"),
        NO_SUCH_REASON,
    ),
    Case(
        "M3",
        "missing value written as zero next to a reason",
        missing_value,
        put(value=0),
        NUMBER_AND_REASON,
    ),
    Case(
        "M3",
        "missing value written as 0.0 next to a reason",
        missing_value,
        put(value=0.0),
        NUMBER_AND_REASON,
    ),
    Case(
        "M3",
        "any number next to a reason",
        missing_value,
        put(value=1.0),
        NUMBER_AND_REASON,
    ),
    Case(
        "M4",
        "missing value written as an empty string",
        missing_value,
        put(value=""),
        NOT_A_NUMBER,
    ),
    Case(
        "M4",
        "missing value written as the text NA",
        missing_value,
        put(value="NA"),
        NOT_A_NUMBER,
    ),
    Case(
        "M4",
        "missing value written as not-a-number",
        missing_value,
        put(value=float("nan")),
        NOT_FINITE,
    ),
    Case(
        "M4",
        "value that is infinite",
        number_with_range,
        put(value=float("inf")),
        NOT_FINITE,
    ),
    Case(
        "M4",
        "number written as text",
        number_with_range,
        put(value="1.0"),
        NOT_A_NUMBER,
    ),
    Case(
        "M4",
        "true in place of a number",
        number_with_range,
        put(value=True),
        NOT_A_NUMBER,
    ),
    Case(
        "M5",
        "'value' field left out of a missing value",
        missing_value,
        drop("value"),
        FIELD_REQUIRED,
    ),
    Case(
        "M5",
        "'value' field left out of a number",
        number_with_range,
        drop("value"),
        FIELD_REQUIRED,
    ),
    Case(
        "M6",
        "reason MISSING_INPUT without a detail",
        the_reason,
        lambda reason: (reason.update(reason="MISSING_INPUT"), reason.pop("detail")),
        "needs a 'detail' naming the missing input",
    ),
    Case("M6", "blank detail", the_reason, put(detail=" "), BLANK),
    Case(
        "M7",
        "missing value with a range",
        missing_value,
        put(range={"low": 1.0, "high": 2.0, "kind": KIND}),
        "a missing value has no range",
    ),
    Case(
        "M7",
        "missing value with a reason for a missing range",
        missing_value,
        put(range_missing=NO_RANGE),
        "a missing value has no range",
    ),
    # R: uncertainty range (C2.1, C2.2, C2.3)
    Case(
        "R1",
        "range without its kind: field absent",
        the_range,
        drop("kind"),
        FIELD_REQUIRED,
    ),
    Case("R1", "range without its kind: null", the_range, put(kind=None), NOT_TEXT),
    Case("R1", "range without its kind: empty", the_range, put(kind=""), BLANK),
    Case(
        "R2",
        "range with one bound only: no high",
        the_range,
        drop("high"),
        FIELD_REQUIRED,
    ),
    Case(
        "R2",
        "range with one bound only: no low",
        the_range,
        drop("low"),
        FIELD_REQUIRED,
    ),
    Case("R2", "bound written as text", the_range, put(low="1.0"), NOT_A_NUMBER),
    Case("R2", "bound that is infinite", the_range, put(high=float("inf")), NOT_FINITE),
    Case(
        "R3",
        "low above high",
        number_with_range,
        low_above_high,
        "'low' is greater than 'high'",
    ),
    Case(
        "R4",
        "value below low",
        number_with_range,
        value_below_low,
        "outside its own range",
    ),
    Case(
        "R4",
        "value above high",
        number_with_range,
        value_above_high,
        "outside its own range",
    ),
    Case(
        "R5",
        "absent range written as two bounds equal to the value",
        number_with_range,
        bounds_equal_to_the_value,
        "two bounds equal to the value",
    ),
    Case(
        "R6",
        "value with no range and no reason",
        number_with_range,
        drop("range"),
        "a value without a range says so",
    ),
    Case(
        "R6",
        "value with no range and no reason: both null",
        number_without_range,
        put(range_missing=None, range=None),
        "a value without a range says so",
    ),
    Case(
        "R7",
        "range together with a reason for a missing range",
        number_with_range,
        put(range_missing=NO_RANGE),
        "keep only one",
    ),
    Case(
        "R8",
        "range written as a list",
        number_with_range,
        put(range=[1.0, 2.0]),
        NOT_AN_OBJECT,
    ),
    Case(
        "R8",
        "range written as text",
        number_with_range,
        put(range="1.0 to 2.0"),
        NOT_AN_OBJECT,
    ),
    # I: indicator identifier and direction (C1.1)
    Case(
        "I1",
        "indicator the conventions sheet does not define",
        number_with_range,
        put(indicator="PLACEHOLDER_indicator"),
        NO_SUCH_INDICATOR,
    ),
    Case(
        "I1",
        "indicator identifier in upper case",
        number_with_range,
        put(indicator="SOIL_LOSS"),
        NO_SUCH_INDICATOR,
    ),
    Case(
        "I1",
        "value without an indicator identifier",
        missing_value,
        drop("indicator"),
        FIELD_REQUIRED,
    ),
    Case(
        "I2",
        "direction the conventions sheet does not allow",
        number_with_range,
        put(direction="PLACEHOLDER_direction"),
        NO_SUCH_DIRECTION,
    ),
    Case(
        "I2",
        "direction in upper case",
        number_with_range,
        put(direction="LOWER_IS_BETTER"),
        NO_SUCH_DIRECTION,
    ),
    Case(
        "I2",
        "value without a direction",
        missing_value,
        drop("direction"),
        FIELD_REQUIRED,
    ),
    Case(
        "I3",
        "allowed direction that is not the one of soil loss",
        soil_loss_number,
        put(direction="higher_is_better"),
        "the direction of 'soil_loss' is 'lower_is_better'",
    ),
    Case(
        "I3",
        "allowed direction that is not the one of the water indicator",
        water,
        put(direction="lower_is_better"),
        "the direction of 'water_deficit_exposure' is 'higher_is_better'",
    ),
    Case(
        "I3",
        "allowed direction that is not the one of the carbon indicator",
        carbon_number,
        put(direction="lower_is_better"),
        "the direction of 'soil_carbon_trend' is 'higher_is_better'",
    ),
    Case(
        "I4",
        "value of another indicator among the annual soil-loss values",
        soil_loss_number,
        put(
            indicator="water_deficit_exposure",
            unit="dimensionless",
            direction="higher_is_better",
        ),
        NO_SUCH_INDICATOR,
        (ROTATION,),
    ),
    # X: unknown extra field
    Case("X1", "unknown field in the document", whole, put(PLACEHOLDER_field=1), EXTRA),
    Case(
        "X1",
        "unknown field in a value",
        number_with_range,
        put(PLACEHOLDER_field=1),
        EXTRA,
    ),
    Case(
        "X1",
        "misspelt field in a value",
        number_with_range,
        put(provenence="DERIVED"),
        EXTRA,
    ),
    Case("X1", "unknown field in a range", the_range, put(mid=1.0), EXTRA),
    Case(
        "X1",
        "unknown field in a 'missing' part",
        the_reason,
        put(PLACEHOLDER_field=1),
        EXTRA,
    ),
    Case(
        "X1",
        "unknown field in the soil-loss part",
        soil_loss_section,
        put(daily=[]),
        EXTRA,
        (ROTATION,),
    ),
    # D: identifiers of the document
    Case("D1", "no case identifier", whole, drop("case_id"), FIELD_REQUIRED),
    Case("D1", "blank field identifier", whole, put(field_id=" "), BLANK),
    Case("D1", "identifier that is not text", whole, put(case_id=7), NOT_TEXT),
    Case(
        "D1",
        "no rotation identifier",
        whole,
        drop("rotation_id"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "D1",
        "row without a rotation identifier",
        rows,
        drop_at(0, "rotation_id"),
        FIELD_REQUIRED,
        (TABLE,),
    ),
    Case(
        "D1",
        "row without a scenario identifier",
        rows,
        drop_at(0, "scenario_id"),
        FIELD_REQUIRED,
        (TABLE,),
    ),
    Case(
        "D1",
        "row with a blank scenario identifier",
        rows,
        put_at(0, scenario_id=""),
        BLANK,
        (TABLE,),
    ),
    # S: months and agricultural years of results per rotation (C5.1, C5.3, C5.4)
    Case(
        "S1",
        "month number zero",
        monthly,
        put_at(0, month=0),
        "greater than or equal to 1",
        (ROTATION,),
    ),
    Case(
        "S1",
        "month number thirteen",
        monthly,
        put_at(0, month=13),
        "less than or equal to 12",
        (ROTATION,),
    ),
    Case(
        "S1",
        "month without its calendar year",
        monthly,
        drop_at(0, "year"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "S1",
        "month without its agricultural year",
        monthly,
        drop_at(0, "ag_year"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "S2",
        "agricultural year written as text",
        annual,
        put_at(0, ag_year="2001"),
        NOT_AN_INTEGER,
        (ROTATION,),
    ),
    Case(
        "S2",
        "agricultural year with a fraction",
        annual,
        put_at(0, ag_year=2001.5),
        NOT_AN_INTEGER,
        (ROTATION,),
    ),
    Case(
        "S2",
        "annual value without its agricultural year",
        annual,
        drop_at(0, "ag_year"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "S3",
        "agricultural year with eleven months",
        monthly,
        remove(0),
        "not twelve",
        (ROTATION,),
    ),
    Case(
        "S3",
        "calendar month given twice",
        monthly,
        put_at(1, month=7),
        "repeats a calendar month",
        (ROTATION,),
    ),
    Case(
        "S4",
        "month outside the twelve consecutive months",
        monthly,
        put_at(0, year=2000),
        "not twelve consecutive calendar months",
        (ROTATION,),
    ),
    Case(
        "S4",
        "agricultural year named after a year it does not begin in",
        whole,
        relabel_first_ag_year,
        "not twelve consecutive calendar months",
        (ROTATION,),
    ),
    Case(
        "S5",
        "agricultural years that begin in different months",
        monthly,
        put_at(0, year=2002),
        "do not all begin in the same calendar month",
        (ROTATION,),
    ),
    Case(
        "S6",
        "annual value whose months are left out",
        whole,
        remove_months_of_last_year,
        "do not cover the same agricultural years",
        (ROTATION,),
    ),
    Case(
        "S6",
        "months whose annual value is left out",
        annual,
        remove(1),
        "do not cover the same agricultural years",
        (ROTATION,),
    ),
    Case("S6", "no annual value at all", annual, empty, AT_LEAST_ONE, (ROTATION,)),
    Case(
        "S6",
        "monthly breakdown left out",
        soil_loss_section,
        drop("monthly"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "S7",
        "agricultural year given twice",
        annual,
        put_at(1, ag_year=2001),
        "'annual' repeats",
        (ROTATION,),
    ),
    # W: time basis of the water indicator (C1.3)
    Case(
        "W1",
        "time basis 'rotation' with an agricultural year",
        water,
        put(ag_year=2001),
        "carries no 'ag_year'",
    ),
    Case(
        "W1",
        "time basis 'ag_year' without an agricultural year",
        water,
        put(time_basis="ag_year"),
        "needs an 'ag_year'",
    ),
    Case(
        "W1",
        "time basis not in the list",
        water,
        put(time_basis="month"),
        NO_SUCH_TIME_BASIS,
    ),
    Case("W1", "value without a time basis", water, drop("time_basis"), FIELD_REQUIRED),
    Case(
        "W2",
        "two values for the whole rotation",
        water_values,
        repeat(0),
        "more than one value on the time basis 'rotation'",
        (ROTATION,),
    ),
    Case(
        "W2",
        "values on both time bases",
        water_values,
        repeat(0, time_basis="ag_year", ag_year=2001),
        "mixes the time bases",
        (ROTATION,),
    ),
    Case(
        "W2",
        "values on both time bases, in the table",
        rows,
        add_water_by_year_next_to_water_by_rotation,
        "mixes the time bases",
        (TABLE,),
    ),
    Case(
        "W2",
        "agricultural year given twice",
        water_values,
        lambda items: (
            items[0].update(time_basis="ag_year", ag_year=2001),
            repeat(0)(items),
        ),
        "'water_deficit_exposure' repeats agricultural year(s)",
        (ROTATION,),
    ),
    Case("W2", "no value at all", water_values, empty, AT_LEAST_ONE, (ROTATION,)),
    # K: carbon model and computation (C1.5, C1.6)
    Case(
        "K1",
        "carbon value without its model",
        carbon_values,
        drop_at(0, "carbon_model"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "K1",
        "carbon value with a blank model",
        carbon_values,
        put_at(0, carbon_model=""),
        NO_SUCH_MODEL,
        (ROTATION,),
    ),
    Case(
        "K1",
        "carbon value without its computation",
        carbon_values,
        drop_at(0, "computation"),
        FIELD_REQUIRED,
        (ROTATION,),
    ),
    Case(
        "K1",
        "carbon row without its model",
        carbon_number,
        drop("carbon_model"),
        "names its carbon model and its computation",
        (TABLE,),
    ),
    Case(
        "K1",
        "carbon row without its computation",
        carbon_number,
        drop("computation"),
        "names its carbon model and its computation",
        (TABLE,),
    ),
    Case(
        "K4",
        "carbon model not in the list (D1)",
        carbon_number,
        put(carbon_model="PLACEHOLDER_carbon_model"),
        NO_SUCH_MODEL,
    ),
    Case(
        "K4",
        "carbon model written in upper case",
        carbon_number,
        put(carbon_model="AMG"),
        NO_SUCH_MODEL,
    ),
    Case(
        "K2",
        "computation not in the list",
        carbon_number,
        put(computation="PLACEHOLDER_computation"),
        NO_SUCH_COMPUTATION,
    ),
    Case(
        "K3",
        "model without one of the three computations",
        carbon_values,
        remove(1),
        THREE_COMPUTATIONS,
        (ROTATION,),
    ),
    Case(
        "K3",
        "model with one computation twice",
        carbon_values,
        put_at(1, computation="end_minus_start"),
        THREE_COMPUTATIONS,
        (ROTATION,),
    ),
    Case(
        "K3", "no carbon value at all", carbon_values, empty, AT_LEAST_ONE, (ROTATION,)
    ),
    # T: rows of the results table
    Case(
        "T1",
        "same cell of a rotation in two rows",
        rows,
        repeat(0),
        "has the same cell in two rows",
        (TABLE,),
    ),
    Case(
        "T2",
        "row left out for one rotation",
        rows,
        remove(1),
        "do not have the same cells",
        (TABLE,),
    ),
    Case(
        "T2",
        "rotations with different agricultural years",
        rows,
        put_at(1, ag_year=2003),
        "do not have the same cells",
        (TABLE,),
    ),
    Case(
        "T2",
        "rotations with different scenarios",
        rows,
        put_at(1, scenario_id="PLACEHOLDER_scenario_two"),
        "do not have the same cells",
        (TABLE,),
    ),
    Case("T2", "table without rows", rows, empty, AT_LEAST_ONE, (TABLE,)),
    Case(
        "T3",
        "soil loss for the whole rotation",
        soil_loss_number,
        lambda row: (row.update(time_basis="rotation"), row.pop("ag_year")),
        "'soil_loss' is one value per agricultural year",
        (TABLE,),
    ),
    Case(
        "T3",
        "soil loss without its agricultural year",
        soil_loss_number,
        drop("ag_year"),
        "needs an 'ag_year'",
        (TABLE,),
    ),
    Case(
        "T3",
        "carbon trend for one agricultural year",
        carbon_number,
        put(time_basis="ag_year", ag_year=2001),
        "'soil_carbon_trend' is one value per rotation",
        (TABLE,),
    ),
    Case(
        "T4",
        "soil loss that names a carbon model",
        soil_loss_number,
        put(carbon_model="amg"),
        "belong to 'soil_carbon_trend' only",
        (TABLE,),
    ),
    Case(
        "T4",
        "water indicator that names a computation",
        water,
        put(computation="end_minus_start"),
        "belong to 'soil_carbon_trend' only",
        (TABLE,),
    ),
]


def _parameters():
    for case in REJECTED:
        for name in case.examples:
            contract = "table" if name == TABLE else "per rotation"
            yield pytest.param(case, name, id=f"{case.code} {case.title} [{contract}]")


@pytest.mark.parametrize("case, name", _parameters())
def test_invalid_variant_is_rejected(case, name):
    document = example(name)
    case.change(case.pick(name, document))
    assert document != example(name), "the case changed nothing"
    assert_rejected(name, document, case.expected)


# --- A: accepted -------------------------------------------------------------


@pytest.mark.parametrize("name", BOTH)
def test_a1_example_loads_into_its_model(name):
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    loaded = MODEL_OF[name].model_validate_json(text)
    # The same content read as parsed JSON gives the same model.
    assert MODEL_OF[name].model_validate(json.loads(text)) == loaded


@pytest.mark.parametrize("name", BOTH)
def test_a2_model_written_back_as_json_loads_again_unchanged(name):
    loaded = load(name, example(name))
    assert MODEL_OF[name].model_validate_json(loaded.model_dump_json()) == loaded


@pytest.mark.parametrize("name", BOTH)
def test_a3_value_of_zero_is_a_value_and_not_a_missing_mark(name):
    document = example(name)
    item = number_with_range(name, document)
    item["value"] = 0
    item["range"].update(low=-1.0, high=1.0)
    load(name, document)

    loaded = number_with_range(name, json.loads(load(name, document).model_dump_json()))
    assert loaded["value"] == 0
    assert loaded["missing"] is None


@pytest.mark.parametrize("name", BOTH)
def test_a4_parts_that_do_not_apply_may_be_null_or_left_out(name):
    document = example(name)
    number_with_range(name, document).update(
        range_missing=None, missing=None, assumption=False
    )
    missing_value(name, document).update(
        range=None, range_missing=None, provenance=None, source=None, assumption=False
    )
    # Written as null or left out, a part that does not apply reads the same.
    assert load(name, document) == load(name, example(name))

    # The detail of a reason is optional (C3.1).
    del missing_value(name, document)["missing"]["detail"]
    load(name, document)


@pytest.mark.parametrize("name", BOTH)
def test_a5_assumption_mark_takes_the_place_of_the_source(name):
    document = example(name)
    item = number_with_range(name, document)
    del item["source"]
    item["assumption"] = True
    load(name, document)


@pytest.mark.parametrize("name", BOTH)
def test_a6_water_indicator_can_be_carried_as_a_number(name):
    """The model can carry the number; the examples do not (case E2)."""
    document = example(name)
    item = water(name, document)
    del item["missing"]
    item.update(
        value=0.5, provenance="SIMULATED", source=SOURCE, range_missing=NO_RANGE
    )
    load(name, document)


@pytest.mark.parametrize("name", BOTH)
def test_a7_water_indicator_can_be_carried_by_agricultural_year(name):
    document = example(name)
    for item in values_of(name, document):
        if item["indicator"] == "water_deficit_exposure":
            item.update(time_basis="ag_year", ag_year=2001)
    load(name, document)


def test_a8_table_with_one_rotation_is_accepted():
    document = example(TABLE)
    kept = document["rows"][0]["rotation_id"]
    document["rows"] = [row for row in document["rows"] if row["rotation_id"] == kept]
    load(TABLE, document)


# --- E: the examples ---------------------------------------------------------

VOCABULARY = {
    *get_args(models.IndicatorId),
    *get_args(models.Direction),
    *get_args(models.ProvenanceLabel),
    *get_args(models.ReasonCode),
    *get_args(models.TrendComputation),
    *get_args(models.CarbonModel),
    *get_args(models.TimeBasis),
    *(unit for units in models.UNITS_OF.values() for unit in units),
}


def texts_of(item):
    if isinstance(item, str):
        yield item
    elif isinstance(item, dict):
        for inner in item.values():
            yield from texts_of(inner)
    elif isinstance(item, list):
        for inner in item:
            yield from texts_of(inner)


def test_e1_examples_cannot_be_mistaken_for_results():
    names = sorted(path.name for path in EXAMPLES.iterdir())
    assert names == sorted(MODEL_OF)
    for name in names:
        assert name.startswith(WORD)
        # Every text that is not a word of a closed list carries the marker.
        for text in texts_of(example(name)):
            assert text in VOCABULARY or WORD in text, f"{name}: '{text}'"
        # Every number travels with a source that carries the marker.
        for item in values_of(name, example(name)):
            if item["value"] is not None:
                assert WORD in item["source"], name


@pytest.mark.parametrize("name", BOTH)
def test_e2_examples_show_the_water_indicator_missing_with_its_reason(name):
    shown = [
        item
        for item in values_of(name, example(name))
        if item["indicator"] == "water_deficit_exposure"
    ]
    assert shown
    for item in shown:
        assert item["value"] is None
        assert item["missing"]["reason"] in get_args(models.ReasonCode)
        assert item["unit"] == "dimensionless"


@pytest.mark.parametrize("name", BOTH)
def test_e3_examples_name_the_model_and_the_computation_of_each_carbon_value(name):
    shown = [
        item
        for item in values_of(name, example(name))
        if item["indicator"] == "soil_carbon_trend"
    ]
    assert shown
    by_model = {}
    for item in shown:
        by_model.setdefault(item["carbon_model"], set()).add(item["computation"])
    assert len(by_model) >= 2
    for computations in by_model.values():
        assert models.DEFAULT_TREND_COMPUTATION in computations


@pytest.mark.parametrize("name", BOTH)
def test_e4_examples_show_every_way_a_value_can_travel(name):
    shown = values_of(name, example(name))
    assert any(item.get("range") for item in shown)
    assert any(item.get("range_missing") for item in shown)
    assert any(item["value"] is None for item in shown)
    assert {item["indicator"] for item in shown} == set(get_args(models.IndicatorId))


def test_e5_example_of_parts_not_built_loads():
    text = (EXAMPLES / NOT_BUILT).read_text(encoding="utf-8")
    loaded = ResultsPerRotation.model_validate_json(text)
    assert ResultsPerRotation.model_validate(json.loads(text)) == loaded
    for part in PARTS:
        assert isinstance(getattr(loaded, part), models.PartNotBuilt), part
        assert getattr(loaded, part).missing.reason == "NOT_AVAILABLE"


# --- N: a part whose engine is not built (decision D12) ----------------------
#
# D12 is decided: a part may be wholly missing only with reason
# NOT_AVAILABLE. The form these cases write (``indicator``, ``direction``,
# ``units``, ``missing``) is PROPOSED.

PARTS = ("soil_loss", "water_deficit_exposure", "soil_carbon_trend")
OTHER_REASONS = [
    reason
    for reason in get_args(models.ReasonCode)
    if reason != models.REASON_OF_A_PART_NOT_BUILT
]
ONLY_NOT_AVAILABLE = "only when its engine is not built"
CARRIES_VALUES = "a part that is wholly missing carries no values"


def not_built(part, reason="NOT_AVAILABLE"):
    """The wholly missing form of one part, as parsed JSON (PROPOSED form)."""
    return {
        "indicator": part,
        "direction": models.DIRECTION_OF[part],
        "units": list(models.UNITS_OF[part]),
        "missing": {"reason": reason, "detail": "PLACEHOLDER detail: not built"},
    }


def with_parts_not_built(*parts, reason="NOT_AVAILABLE"):
    """The per-rotation example with the named parts wholly missing."""
    document = example(ROTATION)
    for part in parts:
        document[part] = not_built(part, reason)
    return document


ACCEPTED_NOT_BUILT = [pytest.param((part,), id=f"{part} only") for part in PARTS] + [
    pytest.param(PARTS, id="all three")
]


@pytest.mark.parametrize("parts", ACCEPTED_NOT_BUILT)
def test_n1_part_wholly_missing_with_not_available_loads(parts):
    loaded = load(ROTATION, with_parts_not_built(*parts))
    for part in PARTS:
        is_missing = isinstance(getattr(loaded, part), models.PartNotBuilt)
        assert is_missing == (part in parts), part


def test_n1_detail_of_a_part_not_built_may_be_left_out():
    document = with_parts_not_built("soil_loss")
    del document["soil_loss"]["missing"]["detail"]
    load(ROTATION, document)


@pytest.mark.parametrize("parts", ACCEPTED_NOT_BUILT)
def test_n2_accepted_document_written_back_as_json_loads_again(parts):
    loaded = load(ROTATION, with_parts_not_built(*parts))
    dumped = loaded.model_dump(mode="json")
    assert ResultsPerRotation.model_validate(dumped) == loaded
    assert ResultsPerRotation.model_validate_json(json.dumps(dumped)) == loaded


def test_n2_example_of_parts_not_built_written_back_loads_again():
    loaded = load(NOT_BUILT, example(NOT_BUILT))
    assert ResultsPerRotation.model_validate(loaded.model_dump(mode="json")) == loaded


@pytest.mark.parametrize("parts", ACCEPTED_NOT_BUILT)
@pytest.mark.parametrize("reason", OTHER_REASONS)
def test_n3_part_wholly_missing_with_another_reason_is_rejected(parts, reason):
    with pytest.raises(ValidationError) as caught:
        load(ROTATION, with_parts_not_built(*parts, reason=reason))
    error = caught.value
    # One error per part, each for the reason only.
    assert error.error_count() == len(parts), str(error)
    for detail in error.errors():
        assert ONLY_NOT_AVAILABLE in detail["msg"], str(error)


def _present(part, key):
    def content():
        return example(ROTATION)[part][key]

    return content


def _fixed(content):
    return lambda: copy.deepcopy(content)


CARRYING_VALUES = [
    ("soil_loss", "annual", _present("soil_loss", "annual")),
    ("soil_loss", "monthly", _present("soil_loss", "monthly")),
    ("soil_loss", "value", _fixed(1.0)),
    ("soil_loss", "ag_year", _fixed(2001)),
    ("water_deficit_exposure", "value", _fixed(0.5)),
    ("water_deficit_exposure", "time_basis", _fixed("rotation")),
    ("water_deficit_exposure", "ag_year", _fixed(2001)),
    ("soil_carbon_trend", "carbon_model", _fixed("amg")),
    ("soil_carbon_trend", "computation", _fixed("end_minus_start")),
    ("soil_carbon_trend", "unit", _fixed(models.UNIT_SOIL_CARBON_TREND)),
]


@pytest.mark.parametrize(
    "part, key, content",
    [pytest.param(*case, id=f"{case[0]} with {case[1]}") for case in CARRYING_VALUES],
)
def test_n4_part_wholly_missing_that_carries_values_is_rejected(part, key, content):
    document = with_parts_not_built(part)
    document[part][key] = content()
    assert_rejected(ROTATION, document, CARRIES_VALUES)


@pytest.mark.parametrize("part", ["water_deficit_exposure", "soil_carbon_trend"])
def test_n4_list_holding_a_part_not_built_is_rejected(part):
    """The wholly missing form replaces the list; it is not an item of it."""
    document = example(ROTATION)
    document[part] = [not_built(part)]
    with pytest.raises(ValidationError):
        load(ROTATION, document)


def _set(key, content):
    def change(item):
        item[key] = copy.deepcopy(content)

    return change


def _drop(key):
    def change(item):
        del item[key]

    return change


def _reason(code):
    def change(item):
        item["missing"]["reason"] = code

    return change


KEEPING_WHAT_IS_MISSING = [
    (
        "soil_loss",
        "direction of the other kind",
        _set("direction", "higher_is_better"),
        "the direction of 'soil_loss' is",
    ),
    (
        "water_deficit_exposure",
        "without a direction",
        _drop("direction"),
        FIELD_REQUIRED,
    ),
    (
        "soil_loss",
        "only one of its two units",
        _set("units", [models.UNIT_SOIL_LOSS_ANNUAL]),
        "the units of a wholly missing 'soil_loss'",
    ),
    (
        "soil_loss",
        "its two units in the other order",
        _set("units", [models.UNIT_SOIL_LOSS_MONTHLY, models.UNIT_SOIL_LOSS_ANNUAL]),
        "the units of a wholly missing 'soil_loss'",
    ),
    (
        "water_deficit_exposure",
        "the unit of another indicator",
        _set("units", [models.UNIT_SOIL_CARBON_TREND]),
        "the units of a wholly missing 'water_deficit_exposure'",
    ),
    (
        "soil_carbon_trend",
        "an empty list of units",
        _set("units", []),
        "the units of a wholly missing 'soil_carbon_trend'",
    ),
    ("soil_carbon_trend", "without its units", _drop("units"), FIELD_REQUIRED),
    (
        "water_deficit_exposure",
        "indicator of another part",
        _set("indicator", "soil_carbon_trend"),
        "Input should be 'water_deficit_exposure'",
    ),
    ("soil_carbon_trend", "without its indicator", _drop("indicator"), FIELD_REQUIRED),
    (
        "water_deficit_exposure",
        "without its missing part",
        _drop("missing"),
        FIELD_REQUIRED,
    ),
    (
        "soil_carbon_trend",
        "reason code not in the list",
        _reason("PLACEHOLDER_REASON"),
        NO_SUCH_REASON,
    ),
    ("soil_loss", "unknown field", _set("PLACEHOLDER_field", 1), EXTRA),
]


@pytest.mark.parametrize(
    "part, title, change, expected",
    [
        pytest.param(*case, id=f"{case[0]} {case[1]}")
        for case in KEEPING_WHAT_IS_MISSING
    ],
)
def test_n5_part_wholly_missing_keeps_its_identifier_direction_and_units(
    part, title, change, expected
):
    document = with_parts_not_built(part)
    change(document[part])
    assert_rejected(ROTATION, document, expected)


def test_n6_present_form_of_each_part_is_unchanged():
    """The per-rotation example still loads into the present form of each part."""
    loaded = load(ROTATION, example(ROTATION))
    assert isinstance(loaded.soil_loss, models.SoilLossResults)
    assert isinstance(loaded.water_deficit_exposure, list)
    assert isinstance(loaded.soil_carbon_trend, list)


# --- C: the models say what the conventions sheet says -----------------------


def convention(identifier):
    """The text of one convention of the sheet, from its heading to the next."""
    text = CONVENTIONS.read_text(encoding="utf-8")
    start = text.index(f"### {identifier} ")
    end = text.find("\n#", start + 1)
    return text[start:] if end == -1 else text[start:end]


def table_row(text, aspect):
    return re.search(rf"^\| {aspect} \| (.+) \|$", text, re.MULTILINE).group(1)


def code_words(text):
    return re.findall(r"`([^`]+)`", text)


@pytest.mark.parametrize(
    "identifier, indicator",
    [
        ("C1.2", "soil_loss"),
        ("C1.3", "water_deficit_exposure"),
        ("C1.5", "soil_carbon_trend"),
    ],
)
def test_c1_identifier_unit_and_direction_are_those_of_the_sheet(identifier, indicator):
    text = convention(identifier)
    assert code_words(table_row(text, "Identifier")) == [indicator]
    assert code_words(table_row(text, "Direction")) == [models.DIRECTION_OF[indicator]]
    units = code_words(table_row(text, "Unit")) + code_words(
        table_row(text, "Time basis")
    )
    assert set(models.UNITS_OF[indicator]) == set(units) - {"OPEN"}


def test_c1_lists_of_indicators_and_directions_are_those_of_the_sheet():
    words = code_words(convention("C1.1"))
    assert set(get_args(models.IndicatorId)) == {
        word for word in words if "_" in word
    } - set(get_args(models.Direction))
    assert set(get_args(models.Direction)) <= set(words)
    assert (
        set(models.DIRECTION_OF)
        == set(models.UNITS_OF)
        == set(get_args(models.IndicatorId))
    )


def test_c2_reason_codes_are_those_of_the_sheet():
    codes = re.findall(r"^\| `([A-Z_]+)` \|", convention("C3.2"), re.MULTILINE)
    assert codes == list(get_args(models.ReasonCode))


def test_c3_provenance_labels_are_those_of_the_sheet():
    labels = re.findall(r"^\| `([A-Z_]+)` \|", convention("C4.1"), re.MULTILINE)
    assert labels == list(get_args(models.ProvenanceLabel))
    assert code_words(convention("C4.6")) == [models.PROVENANCE_OF_SOIL_LOSS]


def test_c4_default_computation_is_one_of_the_three():
    assert len(models.TREND_COMPUTATIONS) == 3
    assert models.DEFAULT_TREND_COMPUTATION == models.TREND_COMPUTATIONS[0]


# --- Z: the list of cases ----------------------------------------------------


def test_z1_readme_lists_the_cases_of_this_file():
    text = README.read_text(encoding="utf-8")
    start = text.index("## PROPOSED cases")
    end = text.find("\n## ", start + 1)
    listed = re.findall(r"^\| ([A-Z]\d+) \|", text[start:end], re.MULTILINE)
    assert len(listed) == len(set(listed)), "a code is listed twice"

    tested = {case.code for case in REJECTED}
    for name in globals():
        match = re.match(r"test_([a-z]\d+)_", name)
        if match:
            tested.add(match.group(1).upper())
    assert set(listed) == tested
