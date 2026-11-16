"""Frontier research inventory, layer-ablation gate, and national grid governance.

Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).

Implements the three governance primitives specified by ``27_PLAN_DE_FRONTERA.md``
(§§5.7, 6, 7, 14, 15) and ``28_PLAN_INTEGRADO_REV13.md``:

1. **46-line Frontier Research Inventory Registry** (``FRONTIER_INVENTORY``):
   tracks all 46 Rev13 §14 items across 10 domains (``Erosion``, ``Water``,
   ``Soil``, ``Carbon``, ``Yield``, ``Climate``, ``Observation``, ``Twin``,
   ``Decision``, ``Economics``) using four strictly independent state axes:
   ``method_maturity``, ``implementation_status``, ``data_availability``, and
   ``local_validation_status``. Enforces the Rev13 rule that ``ESTABLISHED``
   method maturity never auto-grants ``local_validation_status == "VALIDATED"``.
2. **Layer-Ablation Decision Gate** (``evaluate_layer_ablation``, §7 rule):
   compares core-only vs core+frontier decision states and uncertainty
   intervals across test cases and recommends pruning (``prune_recommended=True``)
   when adding the frontier layer neither changes any decision state nor narrows
   uncertainty beyond the caller-supplied ``min_delta``.
3. **National Cell-Grid Runner & Emulator Recalculation Gate**
   (``run_national_grid_cells``, §§5.7, 6): processes cells for ``historical``
   and ``2030-2060`` horizons, keeps ``normative_a_over_t`` (``pre_evaluation``,
   never counted as legal noncompliance) strictly separate from exploratory year
   counts, tags unverified emulator cells as ``"EMULATOR_APPROXIMATION"``,
   enforces ``recalculated_with_full_physics=True`` for finalists
   (flagging or raising ``CONTROL_FAILED`` otherwise), and refuses to invent
   spatial findings when all evaluated cells are uniformly robust
   (``report_uniform_robust_if_all_robust``).

Pure Python stdlib + ``contracts.results.models.Missing`` only. Holds no
fabricated science values, thresholds, or network/file I/O.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from contracts.results.models import Missing

__all__ = [
    "DATA_AVAILABILITIES",
    "EVALUATION_MODES",
    "EXPECTED_INVENTORY_SIZE",
    "FRONTIER_DOMAINS",
    "FRONTIER_INVENTORY",
    "HORIZON_KINDS",
    "IMPLEMENTATION_STATUSES",
    "LOCAL_VALIDATION_STATUSES",
    "METHOD_MATURITIES",
    "STATUS_PROPOSED",
    "AblationCaseEvaluation",
    "AblationTestCase",
    "ControlFailedError",
    "DataAvailability",
    "EvaluationMode",
    "ExploratoryCellCompartment",
    "FrontierDomain",
    "FrontierLineEntry",
    "HorizonGridSummary",
    "HorizonKind",
    "ImplementationStatus",
    "LayerAblationResult",
    "LocalValidationStatus",
    "MethodMaturity",
    "NationalGridCellInput",
    "NationalGridCellOutput",
    "NationalGridRunReport",
    "NormativeCellCompartment",
    "UniformFindingAssessment",
    "assert_maturity_validation_independence",
    "evaluate_layer_ablation",
    "get_inventory_by_unit",
    "report_uniform_robust_if_all_robust",
    "run_national_grid_cells",
    "summarize_inventory_by_domain",
    "validate_frontier_inventory",
]

STATUS_PROPOSED: Final[str] = "PROPOSED (Blueprint §3.7 — Frontier Vision Rev13)"
EXPECTED_INVENTORY_SIZE: Final[int] = 46

FrontierDomain = Literal[
    "Erosion",
    "Water",
    "Soil",
    "Carbon",
    "Yield",
    "Climate",
    "Observation",
    "Twin",
    "Decision",
    "Economics",
]
MethodMaturity = Literal["ESTABLISHED", "FRONTIER", "HYPOTHESIS"]
ImplementationStatus = Literal[
    "CORE_IMPLEMENTED",
    "FRONTIER_IMPLEMENTED",
    "PARTIAL",
    "PROPOSED",
    "NOT_IMPLEMENTED",
]
DataAvailability = Literal[
    "AVAILABLE_PUBLIC",
    "SITE_DECLARED_REQUIRED",
    "LOCAL_MEASUREMENT_REQUIRED",
    "PROVISIONAL_OR_PAUSED",
    "RESTRICTED_OR_ABSENT",
]
LocalValidationStatus = Literal[
    "VALIDATED",
    "PARTIAL",
    "EXPLORATORY_ONLY",
    "UNVALIDATED",
    "BLOCKED_NOT_EVALUATED",
]
HorizonKind = Literal["historical", "2030-2060"]
EvaluationMode = Literal["FULL_PHYSICS", "EMULATOR"]

FRONTIER_DOMAINS: Final[tuple[FrontierDomain, ...]] = (
    "Erosion",
    "Water",
    "Soil",
    "Carbon",
    "Yield",
    "Climate",
    "Observation",
    "Twin",
    "Decision",
    "Economics",
)
METHOD_MATURITIES: Final[tuple[MethodMaturity, ...]] = (
    "ESTABLISHED",
    "FRONTIER",
    "HYPOTHESIS",
)
IMPLEMENTATION_STATUSES: Final[tuple[ImplementationStatus, ...]] = (
    "CORE_IMPLEMENTED",
    "FRONTIER_IMPLEMENTED",
    "PARTIAL",
    "PROPOSED",
    "NOT_IMPLEMENTED",
)
DATA_AVAILABILITIES: Final[tuple[DataAvailability, ...]] = (
    "AVAILABLE_PUBLIC",
    "SITE_DECLARED_REQUIRED",
    "LOCAL_MEASUREMENT_REQUIRED",
    "PROVISIONAL_OR_PAUSED",
    "RESTRICTED_OR_ABSENT",
)
LOCAL_VALIDATION_STATUSES: Final[tuple[LocalValidationStatus, ...]] = (
    "VALIDATED",
    "PARTIAL",
    "EXPLORATORY_ONLY",
    "UNVALIDATED",
    "BLOCKED_NOT_EVALUATED",
)
HORIZON_KINDS: Final[tuple[HorizonKind, ...]] = ("historical", "2030-2060")
EVALUATION_MODES: Final[tuple[EvaluationMode, ...]] = ("FULL_PHYSICS", "EMULATOR")


class ControlFailedError(ValueError):
    """Raised when strict finalist recalculation governance fails."""


def _require_non_empty_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    if value.strip() == "":
        raise ValueError(f"{name} must not be empty or blank")
    return value


def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool, got {type(value).__name__}")
    return value


def _require_finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be a finite number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return result


def _require_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _require_choice(value: object, allowed: tuple[str, ...], name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}, got {value!r}")
    return value


# ---------------------------------------------------------------------------
# 1. 46-line Frontier Research Inventory Registry (§14, Rev13 4-axis state)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontierLineEntry:
    """Single row of the Rev13 §14 Frontier research inventory.

    Stores four independent state axes so ``method_maturity`` never conflates
    with ``implementation_status``, ``data_availability``, or
    ``local_validation_status``.
    """

    line_id: str
    domain: FrontierDomain
    title: str
    unit_ids: tuple[str, ...]
    method_maturity: MethodMaturity
    implementation_status: ImplementationStatus
    data_availability: DataAvailability
    local_validation_status: LocalValidationStatus
    auto_validated_by_maturity: bool = False
    local_evidence_verified: bool = False
    validation_evidence_ref: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _require_non_empty_str(self.line_id, "line_id")
        _require_choice(self.domain, FRONTIER_DOMAINS, "domain")
        _require_non_empty_str(self.title, "title")
        if not isinstance(self.unit_ids, tuple) or not self.unit_ids:
            raise ValueError("unit_ids must be a non-empty tuple of identifiers")
        for uid in self.unit_ids:
            _require_non_empty_str(uid, "unit_ids item")
        _require_choice(self.method_maturity, METHOD_MATURITIES, "method_maturity")
        _require_choice(
            self.implementation_status,
            IMPLEMENTATION_STATUSES,
            "implementation_status",
        )
        _require_choice(
            self.data_availability, DATA_AVAILABILITIES, "data_availability"
        )
        _require_choice(
            self.local_validation_status,
            LOCAL_VALIDATION_STATUSES,
            "local_validation_status",
        )
        _require_bool(self.auto_validated_by_maturity, "auto_validated_by_maturity")
        _require_bool(self.local_evidence_verified, "local_evidence_verified")
        if self.validation_evidence_ref is not None:
            _require_non_empty_str(
                self.validation_evidence_ref, "validation_evidence_ref"
            )
        if not isinstance(self.notes, str):
            raise TypeError(f"notes must be a str, got {type(self.notes).__name__}")
        assert_maturity_validation_independence(self)


def assert_maturity_validation_independence(entry: FrontierLineEntry) -> None:
    """Enforce Rev13 rule: ``ESTABLISHED`` maturity does not grant local validation."""
    if entry.auto_validated_by_maturity:
        raise ValueError(
            f"{entry.line_id}: method_maturity={entry.method_maturity} must never "
            "auto-grant local_validation_status='VALIDATED'"
        )
    if entry.local_validation_status == "VALIDATED" and (
        not entry.local_evidence_verified or entry.validation_evidence_ref is None
    ):
        raise ValueError(
            f"{entry.line_id}: local_validation_status='VALIDATED' requires explicit "
            "local_evidence_verified=True and non-empty validation_evidence_ref; "
            f"method_maturity={entry.method_maturity} is insufficient"
        )


def _entry(
    line_id: str,
    domain: FrontierDomain,
    title: str,
    unit_ids: tuple[str, ...],
    method_maturity: MethodMaturity,
    implementation_status: ImplementationStatus,
    data_availability: DataAvailability,
    local_validation_status: LocalValidationStatus,
    *,
    notes: str = "",
) -> FrontierLineEntry:
    return FrontierLineEntry(
        line_id=line_id,
        domain=domain,
        title=title,
        unit_ids=unit_ids,
        method_maturity=method_maturity,
        implementation_status=implementation_status,
        data_availability=data_availability,
        local_validation_status=local_validation_status,
        notes=notes,
    )


FRONTIER_INVENTORY: Final[tuple[FrontierLineEntry, ...]] = (
    # --- Erosion (L01-L06) ---------------------------------------------------
    _entry(
        "L01",
        "Erosion",
        "Normative vs exploratory erosion separation (pre_evaluation A/T guard)",
        ("F-01",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "BLOCKED_NOT_EVALUATED",
        notes="Official national erosion parity [E1a] unverified; pre_evaluation=True",
    ),
    _entry(
        "L02",
        "Erosion",
        "Sub-hourly 30-min storm separation and EI30 with official R anchoring",
        ("F-02",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "PROVISIONAL_OR_PAUSED",
        "UNVALIDATED",
        notes="Requires local 30-min pluviograph calibration in Uruguay",
    ),
    _entry(
        "L03",
        "Erosion",
        "D8 topographic routing and Index of Connectivity (IC relative hotspot)",
        ("F-03",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "EXPLORATORY_ONLY",
        notes="Relative connectivity only; never multiplied into normative A",
    ),
    _entry(
        "L04",
        "Erosion",
        "Observed satellite dry residue cover (EMIT NPV / calibrated HLS NDTI)",
        ("F-04",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Requires local transect calibration; never overwrites normative C",
    ),
    _entry(
        "L05",
        "Erosion",
        "Static AH703 LS, GloREDa monthly R climatology, and declared C baseline",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "PARTIAL",
        notes="Equations [E3]/[E8]/[E9] verified; computed C withdrawn under D148",
    ),
    _entry(
        "L06",
        "Erosion",
        "Full RUSLE2 dynamic LS, roughness, consolidation, and channel sediment export",
        ("F-01", "F-03"),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes=(
            "Standalone dynamic_surface_routing.py; IC does not provide channel export mass"
        ),
    ),
    # --- Water (L07-L12) -----------------------------------------------------
    _entry(
        "L07",
        "Water",
        "Daily FAO-56 Penman-Monteith ET0 and dual-Kc root-zone water balance",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "PARTIAL",
        notes="[H1]/[H2]/[H7] verified; plot runoff [H10] remains not_evaluated",
    ),
    _entry(
        "L08",
        "Water",
        "Water Cloud Model (WCM) 0-5 cm surface soil moisture inversion",
        ("F-05",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Surface 0-5 cm estimator only; SMAP self-validation forbidden",
    ),
    _entry(
        "L09",
        "Water",
        "Ensemble Kalman Filter (EnKF) state assimilation with holdout split",
        ("F-06",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Tracks analysis increment separate from precipitation",
    ),
    _entry(
        "L10",
        "Water",
        "Seeded two-state Markov conditional resampling synthetic daily weather",
        ("F-08",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "EXPLORATORY_ONLY",
        notes="Tagged SIMULATED; cannot replace observed normative series",
    ),
    _entry(
        "L11",
        "Water",
        "Daily thermal-photoperiod-vernalization crop phenology simulator",
        ("F-10",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Requires observed local flowering dates for calibration",
    ),
    _entry(
        "L12",
        "Water",
        "Multi-year candidate sowing-window frost/heat/water risk sweep",
        ("F-11",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "EXPLORATORY_ONLY",
        notes="Orientation only; keeps historical/synthetic/future horizons apart",
    ),
    # --- Soil (L13-L16) ------------------------------------------------------
    _entry(
        "L13",
        "Soil",
        "Parametric pedotransfer functions (FC, PWP, AWC) with 3-tier provenance",
        ("F-07",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Distinguishes measured, derived PTF, and regional prior maps",
    ),
    _entry(
        "L14",
        "Soil",
        "SoilGrids 2.0 / CONEAT regional prior mapping with effective-depth guard",
        ("F-07",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Missing effective depth returns MISSING_INPUT; never guessed",
    ),
    _entry(
        "L15",
        "Soil",
        "Documented 0.90 m station hydraulic profile vs 0.60 m national reference",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "PARTIAL",
        notes="Kept separate per D77; same-soil REW sensitivity declared per D102",
    ),
    _entry(
        "L16",
        "Soil",
        "Dynamic bulk density, structural crusting, and compaction feedback",
        ("F-07",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes=(
            "Standalone soil_structure_feedback.py; requires time-series pedon measurements"
        ),
    ),
    # --- Carbon (L17-L20) ----------------------------------------------------
    _entry(
        "L17",
        "Carbon",
        "AMG-A (EP5) and RothC-26.3 (EP6) SOC balance on shared CarbonForcing",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="AMG-M excluded from carbon vote (D80); LEELP1 records unsigned",
    ),
    _entry(
        "L18",
        "Carbon",
        "Carbon model trajectory comparator and structural-dependence guard",
        ("F-12",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "UNVALIDATED",
        notes="Blocks unverified AMG-A/AMG-M equal voting; checks stock continuity",
    ),
    _entry(
        "L19",
        "Carbon",
        "Measurable POM/MAOM mineral sorption capacity partition",
        ("F-13",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Requires measured soil fraction initialization and local rates",
    ),
    _entry(
        "L20",
        "Carbon",
        "Coupled lateral erosional SOC export hypothesis",
        ("F-13",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Opt-in hypothesis; missing erosion/SOC fields stay typed Missing",
    ),
    # --- Yield (L21-L24) -----------------------------------------------------
    _entry(
        "L21",
        "Yield",
        "FAO-33 seasonal and stagewise water-limited crop yield response (Ky)",
        ("F-09",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Caller supplies Ky and Ym; zero hardcoded crop parameters",
    ),
    _entry(
        "L22",
        "Yield",
        "Multi-model yield contrast bundle (Declared, FAO-Ky, AquaCrop-OSPy)",
        ("F-09",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Side-by-side min/max spread only; cross-model averaging forbidden",
    ),
    _entry(
        "L23",
        "Yield",
        "GECROS-class mechanistic crop hypothesis envelope",
        ("F-09",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "RESTRICTED_OR_ABSENT",
        "UNVALIDATED",
        notes="Marked license_verified=False and HYPOTHESIS",
    ),
    _entry(
        "L24",
        "Yield",
        "Water-dependent annual forage-to-beef yield proxy",
        ("F-18",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Tagged HYPOTHESIS_UNVALIDATED; never inferred solely from water",
    ),
    # --- Climate (L25-L28) ---------------------------------------------------
    _entry(
        "L25",
        "Climate",
        "Historical daily meteorology and reanalysis context (NASA POWER / IMERG)",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "PARTIAL",
        notes="UTC cached daily record; GWETROOT restricted to qualitative context",
    ),
    _entry(
        "L26",
        "Climate",
        "NEX-GDDP-CMIP6 downscaled daily future climate projections",
        ("F-23",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "EXPLORATORY_ONLY",
        notes="Future outputs set valid_for_normative_erosion=False",
    ),
    _entry(
        "L27",
        "Climate",
        "ISIMIP3b bias-adjusted 5-model contrast ensembles (SSP1-2.6/3-7.0/5-8.5)",
        ("F-23",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "EXPLORATORY_ONLY",
        notes="Reported strictly separate from NEX-GDDP-CMIP6 without averaging",
    ),
    _entry(
        "L28",
        "Climate",
        "GEOS-S2S-3 / NMME seasonal tercile and member forecast subset",
        ("F-23",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Seasonal exploratory forecast subset; typed unavailability on gaps",
    ),
    # --- Observation (L29-L33) -----------------------------------------------
    _entry(
        "L29",
        "Observation",
        "SPL2SMAP_S v003 (3 km) archive with 2026-07-01 forward-pause guard",
        ("F-24",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "PROVISIONAL_OR_PAUSED",
        "UNVALIDATED",
        notes="Non-archive queries on/after 2026-07-01 return NO_COVERAGE",
    ),
    _entry(
        "L30",
        "Observation",
        "ECOSTRESS (70 m) QA-filtered thermal evapotranspiration observations",
        ("F-24",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Requires QA filtering and local flux-tower validation",
    ),
    _entry(
        "L31",
        "Observation",
        "NISAR SME2 (200 m) L-band soil moisture (PROVISIONAL_PRE_2027)",
        ("F-24",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "PROVISIONAL_OR_PAUSED",
        "UNVALIDATED",
        notes="Records from June 2026 onward tagged PROVISIONAL_PRE_2027",
    ),
    _entry(
        "L32",
        "Observation",
        "EMIT (60 m) hyperspectral PV/NPV/bare fractional cover",
        ("F-24",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "PROVISIONAL_OR_PAUSED",
        "UNVALIDATED",
        notes="Tagged SPARSE_OPPORTUNISTIC_CALIBRATION_ONLY; not farm monitoring",
    ),
    _entry(
        "L33",
        "Observation",
        "EO foundation-model crop/date proposals (Prithvi-EO-2.0/Galileo/Presto)",
        ("F-24",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "AVAILABLE_PUBLIC",
        "UNVALIDATED",
        notes="Requires human_confirmed gate and greenness-index baseline check",
    ),
    # --- Twin (L34-L37) ------------------------------------------------------
    _entry(
        "L34",
        "Twin",
        "Forward-mode Dual automatic differentiation parameter sensitivity",
        ("F-14",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "EXPLORATORY_ONLY",
        notes="Exact derivatives; derivatives_guarantee_physical_accuracy=False",
    ),
    _entry(
        "L35",
        "Twin",
        "Knowledge-guided ML (KGML) mass-conserving residual validation gate",
        ("F-14",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Rejects non-conservative learned residuals with CONTROL_FAILED",
    ),
    _entry(
        "L36",
        "Twin",
        "Split-conformal prediction calibration with disjoint reserved holdout",
        ("F-14",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Enforces holdout disjointness; unconditional_field_guarantee=False",
    ),
    _entry(
        "L37",
        "Twin",
        "Discrete Bayesian updater and emulator finalist full-physics gate",
        ("F-14", "F-25"),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Unverified emulator finalists flagged CONTROL_FAILED",
    ),
    # --- Decision (L38-L41) --------------------------------------------------
    _entry(
        "L38",
        "Decision",
        "Core robust dominance, paired cell counts, tipping, and VoI priority",
        ("CORE",),
        "ESTABLISHED",
        "CORE_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "PARTIAL",
        notes="Decision logic [D0..D12] verified on tables; real limits user-supplied",
    ),
    _entry(
        "L39",
        "Decision",
        "Pure-Python constrained multi-objective NSGA-II portfolio search",
        ("F-20",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "EXPLORATORY_ONLY",
        notes="Quarantines Missing objective candidates in unrankable_missing",
    ),
    _entry(
        "L40",
        "Decision",
        "PRIM scenario discovery boxes and DAPP signpost adaptive pathways",
        ("F-21",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "EXPLORATORY_ONLY",
        notes="Quarantines unmodeled scenarios; Missing signposts stay typed",
    ),
    _entry(
        "L41",
        "Decision",
        "Deterministic grounded explainer and hypothesis-mode output verifier",
        ("F-22",),
        "FRONTIER",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "PARTIAL",
        notes="Rejects ungrounded numbers, advice, or false approval with CONTROL_FAILED",
    ),
    # --- Economics (L42-L46) -------------------------------------------------
    _entry(
        "L42",
        "Economics",
        "Three separate Rev13 economic accounts (gross margin, accounting, cash)",
        ("F-15",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "UNVALIDATED",
        notes="Enforces gross/net price and non-monetary depreciation guards",
    ),
    _entry(
        "L43",
        "Economics",
        "Eight-rubric farm input cost ledger and NPK/S nutrient balance",
        ("F-16",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "UNVALIDATED",
        notes="Marks unloaded rubrics pending with Missing; no invented prices",
    ),
    _entry(
        "L44",
        "Economics",
        "Common-horizon temporal NPV and Equivalent Annuity (AE) evaluator",
        ("F-17",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "UNVALIDATED",
        notes="Enforces real-vs-nominal consistency and equal comparison horizons",
    ),
    _entry(
        "L45",
        "Economics",
        "Forage-to-beef enterprise evaluator with pasture completeness guard",
        ("F-18",),
        "ESTABLISHED",
        "FRONTIER_IMPLEMENTED",
        "SITE_DECLARED_REQUIRED",
        "UNVALIDATED",
        notes="Missing livestock inputs keep pasture incomplete (MISSING_INPUT)",
    ),
    _entry(
        "L46",
        "Economics",
        "Non-additive soil degradation valuation, CVaR tail risk, and EVPI/EVSI",
        ("F-19",),
        "HYPOTHESIS",
        "FRONTIER_IMPLEMENTED",
        "LOCAL_MEASUREMENT_REQUIRED",
        "UNVALIDATED",
        notes="Refuses summing valuation methods; missing priors fall back to qualitative VoI",
    ),
)


def validate_frontier_inventory(
    entries: Sequence[FrontierLineEntry] = FRONTIER_INVENTORY,
) -> None:
    """Validate completeness, uniqueness, domain coverage, and independence."""
    if len(entries) != EXPECTED_INVENTORY_SIZE:
        raise ValueError(
            f"FRONTIER_INVENTORY must contain exactly {EXPECTED_INVENTORY_SIZE} "
            f"entries, got {len(entries)}"
        )
    expected_ids = tuple(f"L{idx:02d}" for idx in range(1, EXPECTED_INVENTORY_SIZE + 1))
    actual_ids = tuple(entry.line_id for entry in entries)
    if len(set(actual_ids)) != EXPECTED_INVENTORY_SIZE:
        raise ValueError("FRONTIER_INVENTORY line_ids must be unique")
    if actual_ids != expected_ids:
        raise ValueError(
            f"FRONTIER_INVENTORY line_ids must be sequential L01..L46, got {actual_ids}"
        )
    domains_present = {entry.domain for entry in entries}
    missing_domains = set(FRONTIER_DOMAINS) - domains_present
    if missing_domains:
        raise ValueError(
            f"FRONTIER_INVENTORY is missing required domains: {sorted(missing_domains)}"
        )
    for entry in entries:
        assert_maturity_validation_independence(entry)


def summarize_inventory_by_domain(
    entries: Sequence[FrontierLineEntry] = FRONTIER_INVENTORY,
) -> dict[FrontierDomain, int]:
    """Return ordered per-domain entry counts across the inventory."""
    counts = Counter(entry.domain for entry in entries)
    return {domain: counts.get(domain, 0) for domain in FRONTIER_DOMAINS}


def get_inventory_by_unit(
    unit_id: str,
    entries: Sequence[FrontierLineEntry] = FRONTIER_INVENTORY,
) -> tuple[FrontierLineEntry, ...]:
    """Return all inventory lines referencing ``unit_id`` (e.g. ``'F-01'``)."""
    _require_non_empty_str(unit_id, "unit_id")
    return tuple(entry for entry in entries if unit_id in entry.unit_ids)


validate_frontier_inventory(FRONTIER_INVENTORY)


# ---------------------------------------------------------------------------
# 2. Layer-Ablation Decision Gate (§7 rule)
# ---------------------------------------------------------------------------


def _validate_interval(interval: object, name: str) -> tuple[float, float] | Missing:
    if isinstance(interval, Missing):
        return interval
    if not isinstance(interval, tuple) or len(interval) != 2:
        raise TypeError(
            f"{name} must be a (low, high) tuple or Missing, got {type(interval).__name__}"
        )
    low = _require_finite_float(interval[0], f"{name}[0]")
    high = _require_finite_float(interval[1], f"{name}[1]")
    if low > high:
        raise ValueError(f"{name} must satisfy low <= high, got ({low}, {high})")
    return (low, high)


@dataclass(frozen=True)
class AblationTestCase:
    """One paired core-only vs core+frontier comparison case for §7 ablation."""

    case_id: str
    core_decision_state: str
    frontier_decision_state: str
    core_interval: tuple[float, float] | Missing
    frontier_interval: tuple[float, float] | Missing

    def __post_init__(self) -> None:
        _require_non_empty_str(self.case_id, "case_id")
        _require_non_empty_str(self.core_decision_state, "core_decision_state")
        _require_non_empty_str(self.frontier_decision_state, "frontier_decision_state")
        _validate_interval(self.core_interval, "core_interval")
        _validate_interval(self.frontier_interval, "frontier_interval")


@dataclass(frozen=True)
class AblationCaseEvaluation:
    """Per-case outcome of adding a frontier layer on top of core."""

    case_id: str
    state_changed: bool
    core_width: float | Missing
    frontier_width: float | Missing
    uncertainty_reduction: float | Missing
    narrowed_beyond_min_delta: bool


@dataclass(frozen=True)
class LayerAblationResult:
    """Aggregated §7 layer-ablation gate verdict."""

    layer_id: str
    min_delta: float
    total_cases: int
    case_evaluations: tuple[AblationCaseEvaluation, ...]
    state_changed_cases: tuple[str, ...]
    narrowed_cases: tuple[str, ...]
    missing_interval_cases: tuple[str, ...]
    max_uncertainty_reduction: float | Missing
    any_state_changed: bool
    any_uncertainty_narrowed: bool
    prune_recommended: bool
    decision_note: str
    status: str = STATUS_PROPOSED


def evaluate_layer_ablation(
    layer_id: str,
    cases: Sequence[AblationTestCase],
    *,
    min_delta: float,
) -> LayerAblationResult:
    """Evaluate §7 layer-ablation gate for a frontier layer.

    Sets ``prune_recommended=True`` when adding the frontier layer neither
    changes any decision state nor narrows uncertainty interval width beyond
    ``min_delta`` (``core_width - frontier_width > min_delta``).
    """
    _require_non_empty_str(layer_id, "layer_id")
    min_delta_val = _require_finite_float(min_delta, "min_delta")
    if min_delta_val < 0.0:
        raise ValueError(f"min_delta must be >= 0, got {min_delta_val}")
    if not cases:
        raise ValueError("cases must contain at least one AblationTestCase")

    seen_ids: set[str] = set()
    evaluations: list[AblationCaseEvaluation] = []
    state_changed_cases: list[str] = []
    narrowed_cases: list[str] = []
    missing_interval_cases: list[str] = []
    finite_reductions: list[Fraction] = []
    min_delta_exact = Fraction(str(min_delta_val))

    for case in cases:
        if not isinstance(case, AblationTestCase):
            raise TypeError(
                f"each case must be AblationTestCase, got {type(case).__name__}"
            )
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate ablation case_id: {case.case_id!r}")
        seen_ids.add(case.case_id)

        state_changed = case.core_decision_state != case.frontier_decision_state
        if state_changed:
            state_changed_cases.append(case.case_id)

        if isinstance(case.core_interval, Missing):
            core_width_exact: Fraction | None = None
            core_width: float | Missing = case.core_interval
        else:
            core_width_exact = Fraction(str(case.core_interval[1])) - Fraction(
                str(case.core_interval[0])
            )
            core_width = float(core_width_exact)

        if isinstance(case.frontier_interval, Missing):
            frontier_width_exact: Fraction | None = None
            frontier_width: float | Missing = case.frontier_interval
        else:
            frontier_width_exact = Fraction(str(case.frontier_interval[1])) - Fraction(
                str(case.frontier_interval[0])
            )
            frontier_width = float(frontier_width_exact)

        if core_width_exact is None or frontier_width_exact is None:
            reason = (
                core_width.reason
                if isinstance(core_width, Missing)
                else frontier_width.reason
            )
            detail_parts = []
            if isinstance(core_width, Missing):
                detail_parts.append(f"core_interval ({core_width.reason})")
            if isinstance(frontier_width, Missing):
                detail_parts.append(f"frontier_interval ({frontier_width.reason})")
            reduction: float | Missing = Missing(
                reason="MISSING_INPUT" if reason == "MISSING_INPUT" else reason,
                detail=f"uncertainty interval missing for {case.case_id}: "
                + ", ".join(detail_parts),
            )
            narrowed = False
            missing_interval_cases.append(case.case_id)
        else:
            reduction_exact = core_width_exact - frontier_width_exact
            reduction = float(reduction_exact)
            finite_reductions.append(reduction_exact)
            narrowed = reduction_exact > min_delta_exact
            if narrowed:
                narrowed_cases.append(case.case_id)

        evaluations.append(
            AblationCaseEvaluation(
                case_id=case.case_id,
                state_changed=state_changed,
                core_width=core_width,
                frontier_width=frontier_width,
                uncertainty_reduction=reduction,
                narrowed_beyond_min_delta=narrowed,
            )
        )

    any_state_changed = bool(state_changed_cases)
    any_uncertainty_narrowed = bool(narrowed_cases)
    prune_recommended = (not any_state_changed) and (not any_uncertainty_narrowed)
    max_reduction: float | Missing = (
        float(max(finite_reductions))
        if finite_reductions
        else Missing(
            reason="NOT_COMPUTABLE",
            detail="no ablation case provided both core and frontier intervals",
        )
    )

    if prune_recommended:
        note = (
            f"PRUNE_RECOMMENDED: layer {layer_id!r} changed 0/{len(cases)} decision "
            f"states and narrowed 0/{len(cases)} intervals beyond min_delta={min_delta_val}"
        )
    else:
        note = (
            f"KEEP_LAYER: layer {layer_id!r} changed {len(state_changed_cases)}/{len(cases)} "
            f"decision state(s) and narrowed {len(narrowed_cases)}/{len(cases)} interval(s) "
            f"beyond min_delta={min_delta_val}"
        )

    return LayerAblationResult(
        layer_id=layer_id,
        min_delta=min_delta_val,
        total_cases=len(cases),
        case_evaluations=tuple(evaluations),
        state_changed_cases=tuple(state_changed_cases),
        narrowed_cases=tuple(narrowed_cases),
        missing_interval_cases=tuple(missing_interval_cases),
        max_uncertainty_reduction=max_reduction,
        any_state_changed=any_state_changed,
        any_uncertainty_narrowed=any_uncertainty_narrowed,
        prune_recommended=prune_recommended,
        decision_note=note,
    )


# ---------------------------------------------------------------------------
# 3. National Cell-Grid Runner & Emulator Recalculation Gate (§§5.7, 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniformFindingAssessment:
    """Result of checking whether all evaluated cells share one uniform state."""

    finding_summary: str
    uniform_robust_detected: bool
    spatial_contrast_detected: bool
    invented_findings_refused: bool


def report_uniform_robust_if_all_robust(
    decision_states: Sequence[str],
    *,
    robust_state: str = "Robust preference",
) -> UniformFindingAssessment:
    """Refuse inventing spatial findings when all evaluated cells are uniform.

    If every cell exhibits ``robust_state``, reports ``"UNIFORM_ROBUST"`` with
    ``spatial_contrast_detected=False`` and ``invented_findings_refused=True``.
    """
    _require_non_empty_str(robust_state, "robust_state")
    if not decision_states:
        raise ValueError("decision_states must not be empty")
    cleaned = tuple(
        _require_non_empty_str(s, "decision_state") for s in decision_states
    )
    distinct = set(cleaned)
    if distinct == {robust_state}:
        return UniformFindingAssessment(
            finding_summary="UNIFORM_ROBUST",
            uniform_robust_detected=True,
            spatial_contrast_detected=False,
            invented_findings_refused=True,
        )
    if len(distinct) == 1:
        sole_state = next(iter(distinct))
        return UniformFindingAssessment(
            finding_summary=f"UNIFORM_NON_ROBUST:{sole_state}",
            uniform_robust_detected=False,
            spatial_contrast_detected=False,
            invented_findings_refused=True,
        )
    return UniformFindingAssessment(
        finding_summary="HETEROGENEOUS_STATES",
        uniform_robust_detected=False,
        spatial_contrast_detected=True,
        invented_findings_refused=True,
    )


@dataclass(frozen=True)
class NationalGridCellInput:
    """Input record for one national grid cell under one climate horizon."""

    cell_id: str
    horizon: HorizonKind
    evaluation_mode: EvaluationMode
    decision_state: str
    normative_a_over_t: float | Missing
    exploratory_exceedance_years: int | Missing
    exploratory_total_years: int | Missing
    recalculated_with_full_physics: bool = False
    is_finalist: bool = False
    normative_pre_evaluation: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        _require_non_empty_str(self.cell_id, "cell_id")
        _require_choice(self.horizon, HORIZON_KINDS, "horizon")
        _require_choice(self.evaluation_mode, EVALUATION_MODES, "evaluation_mode")
        _require_non_empty_str(self.decision_state, "decision_state")
        _require_bool(
            self.recalculated_with_full_physics, "recalculated_with_full_physics"
        )
        _require_bool(self.is_finalist, "is_finalist")
        _require_bool(self.normative_pre_evaluation, "normative_pre_evaluation")
        if not isinstance(self.notes, str):
            raise TypeError(f"notes must be a str, got {type(self.notes).__name__}")

        if not isinstance(self.normative_a_over_t, Missing):
            a_over_t = _require_finite_float(
                self.normative_a_over_t, "normative_a_over_t"
            )
            if a_over_t < 0.0:
                raise ValueError(f"normative_a_over_t must be >= 0, got {a_over_t}")

        if not isinstance(self.exploratory_exceedance_years, Missing):
            exc = _require_non_negative_int(
                self.exploratory_exceedance_years, "exploratory_exceedance_years"
            )
        else:
            exc = None
        if not isinstance(self.exploratory_total_years, Missing):
            tot = _require_non_negative_int(
                self.exploratory_total_years, "exploratory_total_years"
            )
        else:
            tot = None
        if exc is not None and tot is not None and exc > tot:
            raise ValueError(
                f"exploratory_exceedance_years ({exc}) cannot exceed "
                f"exploratory_total_years ({tot})"
            )
        if self.horizon == "2030-2060" and not self.normative_pre_evaluation:
            raise ValueError(
                "2030-2060 future horizon cannot disable normative_pre_evaluation"
            )


@dataclass(frozen=True)
class NormativeCellCompartment:
    """Strictly isolated normative A/T slot (never conflated with exploratory years)."""

    a_over_t: float | Missing
    pre_evaluation: bool
    valid_for_normative_erosion: bool
    counts_legal_noncompliance: bool


@dataclass(frozen=True)
class ExploratoryCellCompartment:
    """Strictly isolated exploratory exceedance-year count slot."""

    horizon: HorizonKind
    exceedance_years: int | Missing
    total_years: int | Missing
    counts_legal_noncompliance: bool
    counts_voluntary_target: bool


@dataclass(frozen=True)
class NationalGridCellOutput:
    """Governed national grid output for one (cell_id, horizon) evaluation."""

    cell_id: str
    horizon: HorizonKind
    evaluation_mode: EvaluationMode
    evaluation_tag: str
    recalculated_with_full_physics: bool
    is_finalist: bool
    promoted_as_finalist: bool
    control_status: Literal["PASSED", "CONTROL_FAILED"]
    control_missing: Missing | None
    decision_state: str
    normative: NormativeCellCompartment
    exploratory: ExploratoryCellCompartment
    notes: str = ""


@dataclass(frozen=True)
class HorizonGridSummary:
    """Per-horizon summary so historical and 2030-2060 horizons stay separated."""

    horizon: HorizonKind
    cell_count: int
    emulator_approximation_count: int
    control_failed_count: int
    approved_finalist_count: int
    decision_state_counts: dict[str, int]
    finding_summary: str
    spatial_contrast_detected: bool
    invented_findings_refused: bool


@dataclass(frozen=True)
class NationalGridRunReport:
    """Complete output of ``run_national_grid_cells`` with finalist gate verdict."""

    cells: tuple[NationalGridCellOutput, ...]
    horizon_summaries: dict[HorizonKind, HorizonGridSummary]
    emulator_approximation_cells: tuple[str, ...]
    control_failed_cells: tuple[str, ...]
    approved_finalists: tuple[str, ...]
    gate_passed: bool
    finding_summary: str
    uniform_robust_detected: bool
    invented_findings_refused: bool
    status: str = STATUS_PROPOSED


def run_national_grid_cells(
    cells: Sequence[NationalGridCellInput],
    *,
    raise_on_control_failed: bool = False,
    robust_state: str = "Robust preference",
) -> NationalGridRunReport:
    """Run national grid governance and emulator-recalculation gate (§§5.7, 6).

    - Separates ``historical`` and ``2030-2060`` horizons cleanly.
    - Separates ``normative_a_over_t`` (``pre_evaluation``, never counted as
      legal noncompliance) from exploratory exceedance-year counts.
    - Tags emulator-evaluated cells without full-physics recalculation as
      ``"EMULATOR_APPROXIMATION"``.
    - Enforces ``recalculated_with_full_physics=True`` for finalists; unverified
      emulator finalists are rejected from ``approved_finalists`` and flagged
      (or raised when ``raise_on_control_failed=True``) as ``CONTROL_FAILED``.
    - Refuses inventing findings when all evaluated cells are uniformly robust.
    """
    _require_bool(raise_on_control_failed, "raise_on_control_failed")
    _require_non_empty_str(robust_state, "robust_state")
    if not cells:
        raise ValueError("cells must contain at least one NationalGridCellInput")

    seen_keys: set[tuple[str, HorizonKind]] = set()
    outputs: list[NationalGridCellOutput] = []
    emulator_approx_ids: list[str] = []
    control_failed_ids: list[str] = []
    approved_finalist_ids: list[str] = []

    for cell in cells:
        if not isinstance(cell, NationalGridCellInput):
            raise TypeError(
                f"each cell must be NationalGridCellInput, got {type(cell).__name__}"
            )
        key = (cell.cell_id, cell.horizon)
        if key in seen_keys:
            raise ValueError(
                f"duplicate (cell_id, horizon) entry: {cell.cell_id!r}, {cell.horizon!r}"
            )
        seen_keys.add(key)

        if cell.evaluation_mode == "EMULATOR":
            if cell.recalculated_with_full_physics:
                evaluation_tag = "EMULATOR_RECALCULATED_FULL_PHYSICS"
            else:
                evaluation_tag = "EMULATOR_APPROXIMATION"
                emulator_approx_ids.append(cell.cell_id)
        else:
            evaluation_tag = "FULL_PHYSICS"

        unverified_emulator_finalist = (
            cell.is_finalist
            and cell.evaluation_mode == "EMULATOR"
            and not cell.recalculated_with_full_physics
        )

        if unverified_emulator_finalist:
            detail = (
                f"CONTROL_FAILED: finalist cell {cell.cell_id!r} ({cell.horizon}) "
                "was evaluated as EMULATOR_APPROXIMATION without "
                "recalculated_with_full_physics=True"
            )
            if raise_on_control_failed:
                raise ControlFailedError(detail)
            control_status: Literal["PASSED", "CONTROL_FAILED"] = "CONTROL_FAILED"
            control_missing: Missing | None = Missing(
                reason="CONTROL_FAILED", detail=detail
            )
            promoted = False
            control_failed_ids.append(cell.cell_id)
        else:
            control_status = "PASSED"
            control_missing = None
            promoted = cell.is_finalist
            if promoted:
                approved_finalist_ids.append(cell.cell_id)

        valid_for_normative = (
            cell.horizon == "historical" and not cell.normative_pre_evaluation
        )
        # Pre-evaluation and future horizons never count as legal noncompliance.
        counts_legal = False

        normative = NormativeCellCompartment(
            a_over_t=cell.normative_a_over_t,
            pre_evaluation=cell.normative_pre_evaluation,
            valid_for_normative_erosion=valid_for_normative,
            counts_legal_noncompliance=counts_legal,
        )
        exploratory = ExploratoryCellCompartment(
            horizon=cell.horizon,
            exceedance_years=cell.exploratory_exceedance_years,
            total_years=cell.exploratory_total_years,
            counts_legal_noncompliance=False,
            counts_voluntary_target=True,
        )

        outputs.append(
            NationalGridCellOutput(
                cell_id=cell.cell_id,
                horizon=cell.horizon,
                evaluation_mode=cell.evaluation_mode,
                evaluation_tag=evaluation_tag,
                recalculated_with_full_physics=cell.recalculated_with_full_physics,
                is_finalist=cell.is_finalist,
                promoted_as_finalist=promoted,
                control_status=control_status,
                control_missing=control_missing,
                decision_state=cell.decision_state,
                normative=normative,
                exploratory=exploratory,
                notes=cell.notes,
            )
        )

    horizon_summaries: dict[HorizonKind, HorizonGridSummary] = {}
    for horizon in HORIZON_KINDS:
        h_cells = [out for out in outputs if out.horizon == horizon]
        if not h_cells:
            continue
        h_assessment = report_uniform_robust_if_all_robust(
            [c.decision_state for c in h_cells], robust_state=robust_state
        )
        state_counts = dict(Counter(c.decision_state for c in h_cells))
        horizon_summaries[horizon] = HorizonGridSummary(
            horizon=horizon,
            cell_count=len(h_cells),
            emulator_approximation_count=sum(
                1 for c in h_cells if c.evaluation_tag == "EMULATOR_APPROXIMATION"
            ),
            control_failed_count=sum(
                1 for c in h_cells if c.control_status == "CONTROL_FAILED"
            ),
            approved_finalist_count=sum(1 for c in h_cells if c.promoted_as_finalist),
            decision_state_counts=state_counts,
            finding_summary=h_assessment.finding_summary,
            spatial_contrast_detected=h_assessment.spatial_contrast_detected,
            invented_findings_refused=h_assessment.invented_findings_refused,
        )

    overall_assessment = report_uniform_robust_if_all_robust(
        [out.decision_state for out in outputs], robust_state=robust_state
    )

    return NationalGridRunReport(
        cells=tuple(outputs),
        horizon_summaries=horizon_summaries,
        emulator_approximation_cells=tuple(emulator_approx_ids),
        control_failed_cells=tuple(control_failed_ids),
        approved_finalists=tuple(approved_finalist_ids),
        gate_passed=len(control_failed_ids) == 0,
        finding_summary=overall_assessment.finding_summary,
        uniform_robust_detected=overall_assessment.uniform_robust_detected,
        invented_findings_refused=overall_assessment.invented_findings_refused,
    )
