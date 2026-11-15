"""The approved thin matrix, as a results table (unit l2/thin-matrix-decision).

Every value, range, missing reason, limit and scenario level below is the
matrix approved by the producer on 14 November 2026, issue #240,
verbatim: rotations A, B, C of ``example-case`` / ``example-field-1`,
agricultural years 2020 to 2023, ``soil_loss`` DERIVED with a range on
every value, ``soil_carbon_trend`` SIMULATED (amg, end_minus_start) with
a range, ``water_deficit_exposure`` all missing ``NOT_AVAILABLE`` (D61),
one uncertain input ``u`` — the 2022 soil loss of rotations B and C, the
same value — at three levels s1, s2, s3, and the declared limit
``soil_loss <= 7.0`` inclusive (D89, D90). Nothing here is invented,
nothing missing is filled in, and no missing value is ever zero.

Two labels the matrix does not name, and this module must give to build
contract-valid rows, are carried as the repository's placeholders and
flagged for the person:

- the ``kind`` of the ranges (C2.3: the closed list of kinds is OPEN):
  ``PLACEHOLDER_kind``, the label the decided cases of ``decision/`` use;
- the ``source`` texts of the values: they name the approval itself.

The tolerance of "equal" (D87: set by the designer of the case) is not
part of the matrix. The demo reads "equal" as exact point equality
(``EQUAL_TOLERANCE = 0.0``): the expected point-sign counts of the brief
(equal 0 at the differences -2.1, -0.5 and -4.1 of A vs B at s1) hold
for every tolerance below 0.5, and 0.0 adds no number the brief does not
carry. It is flagged for the designer of the case to confirm or replace.

Pure data and pure builders only: no network, no file access, no clock.
"""

from __future__ import annotations

from contracts.results.models import (
    Missing,
    Range,
    ResultsTable,
    ResultsTableRow,
)
from decision.functions import DeclaredLimit, UncertainInput

CASE_ID = "example-case"
FIELD_ID = "example-field-1"

# The rotations and the scenario levels of the uncertain input, in the
# person's order. The labels A, B, C are documentation only (annual
# soybean; wheat / second-crop soybean then maize; the same sequence plus
# two years of alfalfa).
ROTATIONS: tuple[str, ...] = ("A", "B", "C")
SCENARIOS: tuple[str, ...] = ("s1", "s2", "s3")
AG_YEARS: tuple[int, ...] = (2020, 2021, 2022, 2023)

# The kind of every range of the matrix (C2.3 OPEN; placeholder, as in
# the decided cases of decision/test_decision.py).
RANGE_KIND = "PLACEHOLDER_kind"

# What every value names as its source: the approval itself.
SOURCE = "the thin matrix approved by the designer of the case, 14 November 2026 (issue #240)"

# The soil loss of every rotation and agricultural year, as
# (value, low, high); 2022 of B and C is the uncertain input u, per
# scenario; A holds no 2023 value (missing NO_COVERAGE).
SOIL_LOSS: dict[str, dict[int, tuple[float, float, float]]] = {
    "A": {
        2020: (8.2, 7.8, 8.6),
        2021: (7.0, 6.6, 7.4),
        2022: (9.1, 8.7, 9.5),
    },
    "B": {
        2020: (6.1, 5.8, 6.4),
        2021: (6.5, 6.2, 6.8),
        2023: (6.8, 6.5, 7.1),
    },
    "C": {
        2020: (6.1, 5.8, 6.4),
        2021: (6.5, 6.2, 6.8),
        2023: (6.8, 6.5, 7.1),
    },
}

# The uncertain input u: the 2022 soil loss of rotations B and C (the
# same value), one level per scenario, as (value, low, high).
U_2022: dict[str, tuple[float, float, float]] = {
    "s1": (5.0, 4.7, 5.3),
    "s2": (7.0, 6.6, 7.4),
    "s3": (9.0, 8.6, 9.4),
}

# The soil carbon trend of every rotation, amg / end_minus_start, one
# value per rotation (the same in every scenario: u drives soil loss
# only), as (value, low, high).
SOIL_CARBON_TREND: dict[str, tuple[float, float, float]] = {
    "A": (-0.4, -0.5, -0.3),
    "B": (0.3, 0.2, 0.4),
    "C": (0.5, 0.4, 0.6),
}

MISSING_2023_OF_A = Missing(
    reason="NO_COVERAGE",
    detail="the approved matrix holds no 2023 soil-loss value of rotation A",
)
MISSING_WATER = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "the approved matrix holds water_deficit_exposure missing on every "
        "rotation and scenario (D61)"
    ),
)

# The declared limit: soil_loss <= 7.0 inclusive (D89 descriptive, D90).
SOIL_LOSS_LIMIT = DeclaredLimit(
    indicator="soil_loss",
    limit=7.0,
    provenance="DECLARED",
    source=SOURCE,
)
LIMITS = {"soil_loss": SOIL_LOSS_LIMIT}

# The person's mapping of the uncertain input u (D103: each value is one
# admitted scenario). The cell names rotation B; the input drives the
# 2022 soil-loss cell of B and of C with the same value in every
# scenario, and the table itself carries both rows. The form of
# ``UncertainInput`` holds one cell: a gap this demo reports (the form is
# PROPOSED), since no single cell names both rotations the input drives.
UNCERTAIN_INPUT = UncertainInput(
    name="u",
    unit="t ha-1 yr-1",
    cell=("B", "soil_loss", "ag_year", 2022, None, None),
    values=tuple(
        (U_2022[scenario][0], scenario) for scenario in SCENARIOS
    ),
)
UNCERTAIN_INPUTS = (UNCERTAIN_INPUT,)

# The tolerance of "equal" of the point-sign counts (D87), see the module
# docstring: the demo's reading, not part of the approved matrix.
EQUAL_TOLERANCE = 0.0


def soil_row(
    rotation_id: str, scenario_id: str, ag_year: int, triple: tuple[float, float, float]
) -> ResultsTableRow:
    """One agricultural year of soil loss of one rotation."""
    value, low, high = triple
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=value,
        unit="t ha-1 yr-1",
        range=Range(low=low, high=high, kind=RANGE_KIND),
        provenance="DERIVED",
        source=SOURCE,
    )


def carbon_row(
    rotation_id: str, scenario_id: str, triple: tuple[float, float, float]
) -> ResultsTableRow:
    """The soil carbon trend of one rotation (amg, end_minus_start)."""
    value, low, high = triple
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="rotation",
        indicator="soil_carbon_trend",
        direction="higher_is_better",
        value=value,
        unit="t C ha-1 yr-1",
        range=Range(low=low, high=high, kind=RANGE_KIND),
        provenance="SIMULATED",
        source=SOURCE,
        carbon_model="amg",
        computation="end_minus_start",
    )


def water_row(rotation_id: str, scenario_id: str) -> ResultsTableRow:
    """The water deficit exposure of one rotation: missing, with its reason."""
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="rotation",
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=None,
        unit="dimensionless",
        missing=MISSING_WATER,
    )


def thin_matrix() -> ResultsTable:
    """The approved matrix: 54 rows, one per rotation, scenario and cell.

    Every rotation holds the same cells in every scenario (the contract
    asks for it): the four soil-loss years, the one carbon-trend cell of
    amg / end_minus_start and the one water cell per rotation.
    """
    rows: list[ResultsTableRow] = []
    for scenario_id in SCENARIOS:
        for rotation_id in ROTATIONS:
            for ag_year in AG_YEARS:
                if rotation_id in ("B", "C") and ag_year == 2022:
                    triple = U_2022[scenario_id]
                else:
                    triple = SOIL_LOSS[rotation_id].get(ag_year)
                if triple is None:
                    rows.append(
                        ResultsTableRow(
                            rotation_id=rotation_id,
                            scenario_id=scenario_id,
                            time_basis="ag_year",
                            ag_year=ag_year,
                            indicator="soil_loss",
                            direction="lower_is_better",
                            value=None,
                            unit="t ha-1 yr-1",
                            missing=MISSING_2023_OF_A,
                        )
                    )
                else:
                    rows.append(
                        soil_row(rotation_id, scenario_id, ag_year, triple)
                    )
            rows.append(
                carbon_row(
                    rotation_id, scenario_id, SOIL_CARBON_TREND[rotation_id]
                )
            )
            rows.append(water_row(rotation_id, scenario_id))
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)
