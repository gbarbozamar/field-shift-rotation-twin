"""The bounded matrix of the demonstration, as a results table (unit
l2/bounded-matrix-decision, issue #269).

The case was approved by the producer on 15 November 2026 with one designer
call that governs every cell below: the real-or-missing rule. Every cell
comes from a real engine result where an engine runs, and is missing with
its reason where none does - no hand-made value exists in this table. The
demonstration set is the one the decisions of issue #77 build:

- the three rotation templates of D72, the identifiers R1, R2 and R3 of
  the brief travelling as the rows' ``rotation_id`` (the templates
  themselves - annual soybean; wheat / second-crop soybean, then maize;
  the same sequence followed by two years of pure alfalfa - stay
  documentation, in ``ROTATION_TEMPLATES``);
- the demonstration point of D83 (La Estanzuela) with the soil of D112
  and the declared terrain of D100, whose accepted data file
  ``data/demo/la_estanzuela_soil_slope.json`` carries the case identifier
  reused below;
- the agricultural years of the climate record: D29 fixes the record
  (2001-01-01 to 2024-12-31), D73 the start month of the year (July,
  month 7), and the agricultural years are every year with at least one
  day in the record - 2000 to 2024, twenty-five of them (D47 and point 1
  of ``engine/calendar/repeat.py``; the two edge years are partial and
  their real values will arrive as ``NO_COVERAGE`` when a real run covers
  them, C5.5);
- the one admitted uncertainty: the residue-cover block of D75, whose
  admitted level (D115, D171) is the one scenario of the table, carried
  beside it as the data of ``COVER_AT_THE_UPPER_LEVEL`` and
  ``LOWER_LEVEL_PERCENT``.

The real-or-missing rule, applied today. The six engines are built and
the runner wires them: EP1 to EP6 are registered in ``api/engines.py``
(``DISCOVERED``; ``discover_engine_functions`` imports each one today,
and the carbon models the app configures by default are AMG and RothC,
``DEFAULT_CARBON_MODELS``), so no cell of this table is missing because
an engine is not built. What the demonstration holds no source of is the
climate of the point. The repository holds no climate record of La
Estanzuela: the one recorded response ever committed is the evidence of
D17 and D32 (``docs/evidence/nasa-power-2026-11-14/``), ten days at a
made-up point in the ocean, committed exactly because it is no producer's
field; a session never calls the real service; and the tests of ``api/``
and ``adapters/`` work through ``httpx.MockTransport`` placeholders, so
no recorded-response fixture shape exists for the demonstration point
either. Committing a recorded response of the point is not allowed under
D17 ("Yes, one"). The soil and slope of the point exist (the accepted
data file above), so the one absent site input is the climate, and the
runner's own answer then is what every cell of this table carries:
reason ``MISSING_INPUT``, the runner's detail "input not available:
climate (site data: climate)" (the text of ``_INPUT_NAMES`` of
``api/engines.py``, the same answer for EP1, EP3, EP4, EP5 and EP6
alike). No cell is ever zero and none is filled in (C3.1, C3.2).

The admitted set of the table under D171. An admitted scenario is one
value of each uncertain input that a person declared with its source -
the levels of the blocks of D75 as decisions such as D115 fix them - and
"a level that a decision leaves missing with its reason [...] is not run
and is not admitted; it is listed with that reason" (D171). D115 leaves
the upper level of the residue cover missing for R2 and R3 (the MGAP /
Facultad de Agronomia table gives no cap before a winter cereal and has
no row after alfalfa, ``COVER_AT_THE_UPPER_LEVEL``), so that level is not
run for them: no row of this table carries it, no pair is evaluated at
it, and it is never read as a tipping point of the cover (D176,
condition 2). The lower level (0 percent, bare soil) is declared for
every fallow of every rotation, so the admitted set of the table is the
one scenario ``residue-cover-lower``. The upper level is admitted for R1
alone - the cap of its one fallow, 40 percent - but the results contract
gives every rotation of one table the same cells, ``scenario_id``
included, and every pair of this demonstration holds R2 or R3; so no
table of the three rotations can carry the upper level. It stays listed
with its reason beside the table, a gap reported here and never
silently dropped.

The return path this unit documents: the row skeleton below is the one
the engines will fill - the agricultural years of the record for soil
loss and for the water deficit exposure (one value per agricultural
year, D157), the trend of each mandatory carbon model (D80) under each
of the three computations of C1.6 - so when a climate record of the
point is admitted the same cells carry real values and the same tests
of ``demo/test_bounded.py`` assert them.

Two structures the decisions ask for and this table cannot carry
today, reported as gaps (never silently dropped):

- the phases of D109, nested inside each level by D117. R1 has one
  phase, R2 two, R3 four (one per year of the cycle), but the results
  contract requires every rotation of a table to hold the same cells,
  so per-phase scenarios cannot be written for rotations with different
  phase counts without inventing rows for phases a rotation does not
  have. The table carries one scenario, and the state at that level is
  the state over that scenario - the degenerate single-phase reading
  the machinery of ``decision/functions.py`` accepts and names as such.
  When the phases materialize, the scenarios of a pair are every
  combination of the phases of the two rotations, N x M of them, each
  named by the two phases it holds (D172).
- the uncertain input of the block, in the ``UncertainInput`` form of
  ``decision/functions.py``: the residue cover drives no cell of this
  table directly (it feeds the engines, D116), and its upper level is
  not admitted at all for R2 and R3 (D171) and holds no single admitted
  value for R1 either - the caps of D115 are per sequence - so no honest
  ``(value, scenario)`` mapping exists. The demo declares none and
  reports it; the tipping point of D3 is not computed and the priority
  list of D4 is the machinery's answer over no declared inputs.

One identifier is this unit's proposal, flagged for the designer of the
case: the ``field_id``. The demonstration's own field identifier is not
decided anywhere; the accepted data file names its field after the runoff
plots of a separate experiment (D71 keeps it separate), an identifier
this module does not copy into the demo's document. ``FIELD_ID`` below
is PROPOSED (blueprint section 3.7).

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

# --- the residue-cover block of D75 at the levels of D115 -----------------------

# The two levels of the block as D115 decides them. The scenarios of the
# table are the admitted set of D171, and that set is the lower level
# alone: D115 leaves the upper level missing for R2 and R3 (no cap before
# a winter cereal, no row after alfalfa), and "a level that a decision
# leaves missing with its reason [...] is not run and is not admitted; it
# is listed with that reason" (D171). The upper level is admitted for R1
# alone, but every rotation of one table holds the same cells,
# scenario_id included (the contract), and every pair of this
# demonstration holds R2 or R3, so no table of the three rotations
# carries it (see the module docstring).
UPPER = "residue-cover-upper"
LOWER = "residue-cover-lower"
LEVELS: tuple[str, ...] = (UPPER, LOWER)
SCENARIOS: tuple[str, ...] = (LOWER,)  # D171: the admitted set


@dataclass(frozen=True)
class FallowCover:
    """The upper level of the residue-cover block for one kind of fallow of
    one rotation, as D115 decides it.

    ``upper_percent`` is the cap of the MGAP / Facultad de Agronomia table
    (technical update of the Uruguayan USLE/RUSLE model, hosted on gub.uy
    in January 2020, Table 1) for the sequence the fallow reads; where the
    table gives no cap or has no row, ``upper_percent`` is None and
    ``upper_missing`` carries the reason - only the 0 % level runs there
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
                "the MGAP / Facultad de Agronomia table gives no cap before "
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
                "the MGAP / Facultad de Agronomia table has no row after "
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

# --- the missing part every cell carries (the real-or-missing rule) -------------

# The runner's own detail when the climate of the point is absent
# (api/engines.py, ``_INPUT_NAMES``): the answer it gives for EP1, EP3,
# EP4, EP5 and EP6 alike, all built and wired, none called.
CLIMATE_MISSING_DETAIL = "input not available: climate (site data: climate)"

MISSING_CLIMATE = Missing(
    reason="MISSING_INPUT",
    detail=(
        "the engines are built and the runner wires them (EP1 to EP6, "
        "api/engines.py), but the demonstration holds no climate record "
        "of the point, so the runner calls none of them and every part "
        f"is missing with its own answer, {CLIMATE_MISSING_DETAIL!r}; "
        "the real-or-missing rule forbids a hand-made value, and when a "
        "climate record of the point is admitted this cell fills with "
        "the engine's value"
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
        missing=MISSING_CLIMATE,
    )


def water_row(rotation_id: str, scenario_id: str, ag_year: int) -> ResultsTableRow:
    """One agricultural year of the water deficit exposure of one rotation:
    missing, with its reason.

    D157: one value per agricultural year, the sums read over the
    agricultural year - never one value for the whole rotation.
    """
    return ResultsTableRow(
        rotation_id=rotation_id,
        scenario_id=scenario_id,
        time_basis="ag_year",  # D157
        ag_year=ag_year,
        indicator="water_deficit_exposure",
        direction="higher_is_better",
        value=None,
        unit="dimensionless",
        missing=MISSING_CLIMATE,
    )


def carbon_row(
    rotation_id: str, scenario_id: str, carbon_model: str, computation: str
) -> ResultsTableRow:
    """The soil carbon trend of one rotation under one carbon model and one
    computation: missing, with its reason (the same as every other part:
    the engine is built, the climate of the point is not there)."""
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
        missing=MISSING_CLIMATE,
    )


def bounded_matrix() -> ResultsTable:
    """The bounded matrix: 168 rows, one per rotation and cell of the
    admitted set, every value missing with its reason.

    Every rotation holds the same cells in the one admitted scenario (the
    contract asks for it): the twenty-five soil-loss years of the record,
    the twenty-five water years (D157) and the trend of each carbon model
    under each computation. The upper level of the block is not among
    them: D115 leaves it missing for R2 and R3, so it is not run and not
    admitted (D171) and is listed with its reason in
    ``COVER_AT_THE_UPPER_LEVEL``.
    """
    rows: list[ResultsTableRow] = []
    for scenario_id in SCENARIOS:
        for rotation_id in ROTATIONS:
            for ag_year in AG_YEARS:
                rows.append(soil_row(rotation_id, scenario_id, ag_year))
            for ag_year in AG_YEARS:
                rows.append(water_row(rotation_id, scenario_id, ag_year))
            for carbon_model in CARBON_MODELS:
                for computation in TREND_COMPUTATIONS:
                    rows.append(
                        carbon_row(rotation_id, scenario_id, carbon_model, computation)
                    )
    return ResultsTable(case_id=CASE_ID, field_id=FIELD_ID, rows=rows)
