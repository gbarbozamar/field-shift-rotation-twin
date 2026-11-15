"""The bounded matrix of the demonstration, as a results table (unit
l2/bounded-matrix-decision, issue #269).

The case was approved by the producer on 15 November 2026 with one designer
call that governs every cell below: the real-or-missing rule. Every cell
comes from a real engine result where an engine runs, and is missing with
its reason where none does — no hand-made value exists in this table. The
demonstration set is the one the decisions of issue #77 build:

- the three rotation templates of D72, the identifiers R1, R2 and R3 of the
  brief travelling as the rows' ``rotation_id`` (the templates themselves —
  annual soybean; wheat / second-crop soybean, then maize; the same
  sequence followed by two years of pure alfalfa — stay documentation, in
  ``ROTATION_TEMPLATES``);
- the demonstration point of D83 (La Estanzuela) with the soil of D112 and
  the declared terrain of D100, whose accepted data file
  ``data/demo/la_estanzuela_soil_slope.json`` carries the case identifier
  reused below;
- the agricultural years of the climate record: D29 fixes the record
  (2001-01-01 to 2024-12-31), D73 the start month of the year (July, month
  7), and the agricultural years are every year with at least one day in
  the record — 2000 to 2024, twenty-five of them (D47 and point 1 of
  ``engine/calendar/repeat.py``; the two edge years are partial and their
  real values will arrive as ``NO_COVERAGE`` when a real run covers them,
  C5.5);
- the one admitted uncertainty: the residue-cover block of D75 at its two
  decided levels of D115 (``SCENARIOS``), carried beside the table as the
  data of ``COVER_AT_THE_UPPER_LEVEL`` and ``LOWER_LEVEL``.

The real-or-missing rule, applied today. The check the brief asks for —
whether ``demo/`` can build real EP1 cells — was made and the answer is no:

- EP1 (``engine.erosion.compute_soil_loss``) needs a ``SiteClimate`` of the
  point over the record. The repository holds no climate record of La
  Estanzuela: the one recorded response ever committed is the evidence of
  D17 and D32 (``docs/evidence/nasa-power-2026-11-14/``), ten days at a
  made-up point in the ocean, committed exactly because it is no producer's
  field; a session never calls the real service; and the tests of ``api/``
  and ``adapters/`` work through ``httpx.MockTransport`` placeholders, so
  no recorded-response fixture shape exists for the demonstration point
  either. Committing a recorded response of the point is not allowed under
  D17 ("Yes, one"), so no real EP1 output is obtainable here.
- Therefore every ``soil_loss`` cell is missing ``NOT_AVAILABLE``, "the
  engine's real outputs are not wired to the demo yet", and so is every
  ``water_deficit_exposure`` cell (EP3 needs the same climate). The carbon
  cells are missing for their own decided reason: D122 (the annual carbon
  inputs are missing in this release, EP4 not built, so AMG runs but its
  values are missing with that reason) and, for RothC, EP6 not built. No
  cell is ever zero and none is filled in (C3.1, C3.2).

The return path this unit documents: the row skeleton below is the one the
engines will fill — the agricultural years of the record for soil loss,
one water value per rotation, the trend of each mandatory carbon model
(D80) under each of the three computations of C1.6 — so when the runner's
outputs arrive the same cells carry real values and the same tests of
``demo/test_bounded.py`` assert them.

Two structures the decisions ask for and this table cannot carry today,
reported as gaps (never silently dropped):

- the phases of D109, nested inside each level by D117. R1 has one phase,
  R2 two, R3 four (one per year of the cycle), but the results contract
  requires every rotation of a table to hold the same cells, so per-phase
  scenarios cannot be written for rotations with different phase counts
  without inventing rows for phases a rotation does not have. The table
  carries one scenario per level, and the state at a level is the state
  over that scenario — the degenerate single-phase reading the machinery
  of ``decision/functions.py`` accepts and names as such. When the phases
  materialize, the scenarios of a pair are every combination of the
  phases of the two rotations, N x M of them, each named by the two
  phases it holds (D172).
- the uncertain input of the block, in the ``UncertainInput`` form of
  ``decision/functions.py``: the residue cover drives no cell of this
  table directly (it feeds the engines, D116), and its upper level holds
  no single admitted value — the caps of D115 are per sequence and missing
  for the fallows before a winter cereal, so no honest ``(value,
  scenario)`` mapping exists. The demo declares none and reports it; the
  tipping point of D3 is not computed and the priority list of D4 is the
  machinery's answer over no declared inputs.

One identifier is this unit's proposal, flagged for the designer of the
case: the ``field_id``. The demonstration's own field identifier is not
decided anywhere; the accepted data file names its field after the runoff
plots of a separate experiment (D71 keeps it separate), an identifier this
module does not copy into the demo's document. ``FIELD_ID`` below is
PROPOSED (blueprint section 3.7).

Pure data and pure builders only: no network, no file access, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.results.models import (
    Missing,
    ResultsTable,
    ResultsTableRow,
)

# --- the case of the demonstration ---------------------------------------------

# The case identifier of the accepted data file of the point
# (data/demo/la_estanzuela_soil_slope.json: the demonstration point of D83,
# the soil of D112, the declared terrain of D100).
CASE_ID = "la-estanzuela-demo"

# PROPOSED by this unit; see the module docstring.
FIELD_ID = "la-estanzuela-point"

# The three rotation templates of D72, as the brief of issue #269 ids them.
# The labels travel as documentation only; the rows carry R1, R2 and R3.
ROTATIONS: tuple[str, ...] = ("R1", "R2", "R3")
ROTATION_TEMPLATES: dict[str, str] = {
    "R1": "annual soybean (D72: 15 November to 5 May, repeating every year)",
    "R2": (
        "wheat / second-crop soybean, then maize (D72: wheat 25 May to 5 "
        "December, second-crop soybean 10 December to 10 May, maize 20 "
        "September to 20 April)"
    ),
    "R3": (
        "the sequence of R2 followed by two years of pure alfalfa (D72: "
        "sown 25 April after the maize, kept 24 months, before the wheat "
        "returns)"
    ),
}

# The agricultural years the engines list (D47, D29, D73): every
# agricultural year with at least one day inside the record. The record
# runs 2001-01-01 to 2024-12-31 and the year starts in July, so the first
# year is 2000 (covered from 1 January 2001) and the last is 2024 (covered
# to 31 December 2024): twenty-five years.
RECORD_START = "2001-01-01"  # D29
RECORD_END = "2024-12-31"  # D29
AG_YEAR_START_MONTH = 7  # D73: the agricultural year runs 1 July to 30 June
AG_YEARS: tuple[int, ...] = tuple(range(2000, 2025))

# The two carbon models of the demonstration (D80: both mandatory) and the
# three computations of the trend each carries (C1.6).
CARBON_MODELS: tuple[str, ...] = ("amg", "rothc")
TREND_COMPUTATIONS: tuple[str, ...] = (
    "end_minus_start",
    "fitted_slope",
    "mean_over_cycles",
)

# --- the residue-cover block of D75, at its two decided levels of D115 ----------

# The two levels are the two scenarios of the table: one set of values of
# the uncertain inputs is one scenario (contracts/results/README.md).
SCENARIOS: tuple[str, ...] = ("residue-cover-upper", "residue-cover-lower")
UPPER = SCENARIOS[0]
LOWER = SCENARIOS[1]


@dataclass(frozen=True)
class FallowCover:
    """The upper level of the residue-cover block for one kind of fallow of
    one rotation, as D115 decides it.

    ``upper_percent`` is the cap of the MGAP / Facultad de Agronomía table
    (technical update of the Uruguayan USLE/RUSLE model, hosted on gub.uy
    in January 2020, Table 1) for the sequence the fallow reads; where the
    table gives no cap or has no row, ``upper_percent`` is None and
    ``upper_missing`` carries the reason — only the 0 % level runs there
    (D115). The cover is constant over the fallow (D115, declared as a
    simplification: the table gives the cover at sowing). The lower level
    is 0 % for every fallow of every rotation and is not repeated here.
    """

    rotation_id: str
    fallow: str
    upper_percent: float | None
    upper_missing: Missing | None


# The caps of the table as D115 states them, with the rotations whose
# fallows read each row. The 70 % row ("winter cereal, second-crop soybean,
# then soybean") is read by no rotation of D72: soybean follows the wheat /
# second-crop-soybean year in none of the three templates. Whether the few
# days between the maize harvest (20 April) and the alfalfa sowing (25
# April) of R3 are a fallow whose cover D115 sets is not decided; this
# module fills nothing for them. The same holds for the few days between
# the wheat harvest (5 December) and the second-crop-soybean sowing
# (10 December) of R2 and R3: D115's table states no cap for them either.
COVER_AT_THE_UPPER_LEVEL: tuple[FallowCover, ...] = (
    FallowCover(
        rotation_id="R1",
        fallow="after soybean, before soybean (continuous annual soybean)",
        upper_percent=40.0,
        upper_missing=None,
    ),
    FallowCover(
        rotation_id="R2",
        fallow="after second-crop soybean, before maize",
        upper_percent=80.0,
        upper_missing=None,
    ),
    FallowCover(
        rotation_id="R3",
        fallow="after second-crop soybean, before maize",
        upper_percent=80.0,
        upper_missing=None,
    ),
    FallowCover(
        rotation_id="R2",
        fallow="after maize, before wheat",
        upper_percent=None,
        upper_missing=Missing(
            reason="NO_COVERAGE",
            detail=(
                "the MGAP / Facultad de Agronomía table gives no cap before "
                "a winter cereal, so the upper level of the residue-cover "
                "block is missing for this fallow and only the 0 % level "
                "runs (D115)"
            ),
        ),
    ),
    FallowCover(
        rotation_id="R3",
        fallow="after alfalfa, before wheat",
        upper_percent=None,
        upper_missing=Missing(
            reason="NO_COVERAGE",
            detail=(
                "the MGAP / Facultad de Agronomía table has no row after "
                "alfalfa, so the upper level of the residue-cover block is "
                "missing for this fallow and only the 0 % level runs (D115)"
            ),
        ),
    ),
)

# The cap of the table that no rotation of this demonstration reads: kept
# as data, so the block shows the whole row of D115 it comes from.
CAP_READ_BY_NO_ROTATION: FallowCover = FallowCover(
    rotation_id="",
    fallow="winter cereal, second-crop soybean, then soybean",
    upper_percent=70.0,
    upper_missing=None,
)

# The lower level of the block: bare soil for every fallow of every
# rotation (D115: 0 %, FAO-56 with no mulch).
LOWER_LEVEL_PERCENT = 0.0

# --- the missing parts every cell carries (the real-or-missing rule) ------------

# The canonical reason text of the rule, as the approved case states it.
NOT_WIRED = "the engine's real outputs are not wired to the demo yet"

MISSING_SOIL_LOSS = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        f"{NOT_WIRED}: the demonstration holds no climate record of the "
        "point (a session never calls the real service, and the one "
        "recorded response committed in the repository is the evidence of "
        "D17 and D32 of issue #77, a made-up point in the ocean, not the "
        "record of the point), so no real erosion output is obtainable and "
        "the real-or-missing rule forbids a hand-made value; when the "
        "runner's outputs arrive this cell fills with the engine's value"
    ),
)

MISSING_WATER = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        f"{NOT_WIRED}: the water engine needs the same climate record of "
        "the point the erosion engine needs, none is obtainable in the "
        "demo, and the real-or-missing rule forbids a hand-made value; "
        "when the runner's outputs arrive this cell fills with the "
        "engine's value"
    ),
)

MISSING_CARBON_AMG = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "the annual carbon inputs are missing in this release with "
        "NOT_AVAILABLE (EP4 not built; D122 of issue #77), so the AMG "
        "soil-carbon trend is missing with that reason, and the engine's "
        "real outputs are not wired to the demo yet in any case; when the "
        "inputs and the runner's outputs arrive this cell fills with the "
        "engine's value"
    ),
)

MISSING_CARBON_ROTHC = Missing(
    reason="NOT_AVAILABLE",
    detail=(
        "the RothC engine (EP6) is not built, so its trend is missing "
        "NOT_AVAILABLE, and the engine's real outputs are not wired to the "
        "demo yet in any case; when the engine is built and the runner's "
        "outputs arrive this cell fills with the engine's value"
    ),
)


# --- the builders ---------------------------------------------------------------


def soil_row(rotation_id: str, scenario_id: str, ag_year: int) -> ResultsTableRow:
    """One agricultural year of soil loss of one rotation: missing, with the
    reason of the real-or-missing rule (never zero)."""
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",
        ag_year=ag_year,
        indicator="soil_loss",
        direction="lower_is_better",
        value=None,
        unit="t ha-1 yr-1",
        missing=MISSING_SOIL_LOSS,
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


def carbon_row(
    rotation_id: str, scenario_id: str, carbon_model: str, computation: str
) -> ResultsTableRow:
    """The soil carbon trend of one rotation under one carbon model and one
    computation: missing, with its reason."""
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="rotation",
        indicator="soil_carbon_trend",
        direction="higher_is_better",
        value=None,
        unit="t C ha-1 yr-1",
        carbon_model=carbon_model,
        computation=computation,
        missing=MISSING_CARBON_AMG if carbon_model == "amg" else MISSING_CARBON_ROTHC,
    )


def bounded_matrix() -> ResultsTable:
    """The bounded matrix: 192 rows, one per rotation, level and cell, every
    value missing with its reason.

    Every rotation holds the same cells in every scenario (the contract
    asks for it): the twenty-five soil-loss years of the record, the one
    water value of the rotation and the trend of each carbon model under
    each computation.
    """
    rows: list[ResultsTableRow] = []
    for scenario_id in SCENARIOS:
        for rotation_id in ROTATIONS:
            for ag_year in AG_YEARS:
                rows.append(soil_row(rotation_id, scenario_id, ag_year))
            rows.append(water_row(rotation_id, scenario_id))
            for carbon_model in CARBON_MODELS:
                for computation in TREND_COMPUTATIONS:
                    rows.append(
                        carbon_row(rotation_id, scenario_id, carbon_model, computation)
                    )
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)
