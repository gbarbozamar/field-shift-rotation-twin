# Frontier Vision Rev13 — Technical Specification & Research Inventory

> **Status: PROPOSED (Blueprint §3.7 — Frontier Vision Rev13).**
>
> This specification is a proposed research-frontier architecture aligned with [DEVELOPMENT_BLUEPRINT.md](DEVELOPMENT_BLUEPRINT.md) §3.7. Nothing in this document alters core event (`P0`) claims, deployed defaults, signed parameter counts in `params/records/`, or active validation outcomes in [VALIDATION.md](VALIDATION.md). Every proposed item takes effect only upon maintainer pull-request review and, for science-class methods or inputs, science-reviewer sign-off.

Design references (external planning documents, cited by identifier only): `` `27_PLAN_DE_FRONTERA.md` `` (§§3, 5.1–5.8, 6, 7, 11–15) and `` `28_PLAN_INTEGRADO_REV13.md` `` (§§1–5, 17).

---

## 1. Separation from Core Event (`P0`) Claims

The core event system documented in [BLUEPRINT_TRACEABILITY.md](BLUEPRINT_TRACEABILITY.md), [METHODS.md](METHODS.md), and [MODEL_CARDS_AND_LIMITS.md](MODEL_CARDS_AND_LIMITS.md) remains strictly isolated from Frontier (`F-01`..`F-25`) capabilities:

1. **No silent overwrite of core outputs:** Frontier exploratory modules never replace normative `P0` erosion, water-deficit, or carbon outputs, never inject synthetic or future-climate records into `OBSERVED` baselines, and never invent parameters, prices, thresholds, or expected validation values.
2. **Typed absences everywhere:** Missing inputs, uncalibrated transformations, paused satellite streams, and incomplete modules propagate typed `Missing` reasons under [../contracts/CONVENTIONS.md](../contracts/CONVENTIONS.md) (`C3.1`–`C3.2`), never defaulting silently to `0.0`.
3. **Deterministic templates, no language model in the product:** Explanations are rendered deterministically from computed ledgers and verified against numeric/claim grounding gates (`F-22`).

---

## 2. Rev13 Four-Axis State Distinction

Under Rev13, every line in the 46-entry Frontier Research Inventory ([../validation/frontier_governance.py](../validation/frontier_governance.py)) tracks **four independent state axes**:

| Axis | Closed Vocabulary | What It Measures |
|---|---|---|
| `method_maturity` | `ESTABLISHED`, `FRONTIER`, `HYPOTHESIS` | Scientific maturity of the mathematical/physical method in literature |
| `implementation_status` | `CORE_IMPLEMENTED`, `FRONTIER_IMPLEMENTED`, `PARTIAL`, `PROPOSED`, `NOT_IMPLEMENTED` | Software implementation state in the repository |
| `data_availability` | `AVAILABLE_PUBLIC`, `SITE_DECLARED_REQUIRED`, `LOCAL_MEASUREMENT_REQUIRED`, `PROVISIONAL_OR_PAUSED`, `RESTRICTED_OR_ABSENT` | Operational availability and licensing of required forcing/input data |
| `local_validation_status` | `VALIDATED`, `PARTIAL`, `EXPLORATORY_ONLY`, `UNVALIDATED`, `BLOCKED_NOT_EVALUATED` | Independent local verification status against Uruguayan field/station evidence |

**Non-conflation invariant:** `method_maturity = "ESTABLISHED"` NEVER auto-grants `local_validation_status = "VALIDATED"`. Transitioning an entry to `"VALIDATED"` requires explicit `local_evidence_verified=True` backed by a non-empty `validation_evidence_ref`; `assert_maturity_validation_independence` rejects any entry violating this separation.

---

## 3. Governance Primitives (`validation/frontier_governance.py`)

Implemented in [../validation/frontier_governance.py](../validation/frontier_governance.py) and tested in [../validation/test_frontier_governance.py](../validation/test_frontier_governance.py):

1. **`FRONTIER_INVENTORY` (46 entries, `L01`–`L46`):** Complete frozen registry covering all 10 domains (`Erosion`, `Water`, `Soil`, `Carbon`, `Yield`, `Climate`, `Observation`, `Twin`, `Decision`, `Economics`), enforcing `validate_frontier_inventory` and `assert_maturity_validation_independence`. All **`46/46` (`100%`)** inventory lines are implemented (`40` `FRONTIER_IMPLEMENTED`, `6` `CORE_IMPLEMENTED`, `0` `NOT_IMPLEMENTED`), while **`0/46`** carry `local_validation_status = "VALIDATED"`.
2. **Layer-Ablation Decision Gate (`evaluate_layer_ablation`, §7 rule):** Compares core-only vs. core+frontier decision state and uncertainty interval `(low, high)` across paired test cases with a caller-supplied `min_delta >= 0`. Sets `prune_recommended=True` when adding the frontier layer neither changes any decision state nor narrows any uncertainty interval beyond `min_delta` (`core_width - frontier_width > min_delta`).
3. **National Cell-Grid Runner & Emulator Recalculation Gate (`run_national_grid_cells`, §§5.7, 6):**
   - Evaluates cells across strictly separated `historical` and `2030-2060` horizons (`HorizonGridSummary` per horizon).
   - Isolates `normative_a_over_t` (`pre_evaluation=True`, `counts_legal_noncompliance=False`) from exploratory exceedance-year counts (`counts_voluntary_target=True`, `counts_legal_noncompliance=False`).
   - Tags emulator-evaluated cells without full-physics verification as `"EMULATOR_APPROXIMATION"`.
   - Enforces `recalculated_with_full_physics=True` for finalists; promotes verified finalists only, and flags (or raises `ControlFailedError` when `raise_on_control_failed=True`) `CONTROL_FAILED` whenever an unverified emulator approximation is submitted as a finalist.
   - Refuses to invent spatial contrasts (`report_uniform_robust_if_all_robust`): when all evaluated cells share the robust state, reports `"UNIFORM_ROBUST"` with `spatial_contrast_detected=False` and `invented_findings_refused=True`.

---

## 4. Frontier Module Map (`F-01`..`F-25`)

Target module paths below are cited in plain backticks because sibling Frontier units live on separate `l0/`–`l2/` branches until merged.

| Unit | Lane | Target Module | Core Governance / Scientific Guard | §14 Lines |
|---|---|---|---|---|
| `F-01` | `L0` | `engine/erosion/normative_exploratory.py` | Separates `EROSION_NORMATIVA` (`pre_evaluation`) from `EROSION_EXPLORATORIA`; refuses single-year or future means as normative | `L01`, `L06` |
| `F-02` | `L0` | `engine/erosion/storm_erosivity.py` | 30-min storm separation & `EI30` with caller-supplied KE params; `EXPLORATORY_UNVALIDATED` when uncalibrated | `L02` |
| `F-03` | `L0` | `engine/erosion/sediment_connectivity.py` | D8 flow routing & Borselli `IC`; tagged `is_exported_sediment_mass=False`, never multiplied into `A_norm` | `L03`, `L06` |
| `F-04` | `L0` | `engine/erosion/observed_residue_cover.py` | `EMIT` NPV / calibrated `HLS` `NDTI` vs tabular `C`; uncalibrated `NDTI` returns `NOT_COMPUTABLE` | `L04` |
| `F-05` | `L1` | `engine/water/surface_moisture_wcm.py` | Sentinel-1/2 `WCM` `0-5 cm` inversion (`observes_root_zone=False`); blocks SMAP self-validation | `L08` |
| `F-06` | `L1` | `engine/water/enkf_assimilation.py` | Pure-Python `EnKF` with sample covariance `P_f`, explicit `analysis_increment_mm`, and disjoint `HoldoutSplit` | `L09` |
| `F-07` | `L1` | `engine/water/pedotransfer.py` | Parametric PTFs tracking 3 provenance tiers; missing effective depth returns `MISSING_INPUT` | `L13`, `L14`, `L16` |
| `F-08` | `L1` | `engine/water/synthetic_weather.py` | Seeded two-state Markov weather generator tagged `SIMULATED`; blocks mixing into `OBSERVED` records | `L10` |
| `F-09` | `L1` | `engine/water/fao_yield_response.py` | FAO-33 water-limited yield (`Ky`) and multi-model contrast bundle without cross-model averaging | `L21`, `L22`, `L23` |
| `F-10` | `L1` | `engine/calendar/thermal_phenology.py` | Daily thermal-photoperiod-vernalization phenology; tags `UNCALIBRATED` without local flowering data | `L11` |
| `F-11` | `L1` | `engine/calendar/sowing_window_sweep.py` | Multi-year sowing-date risk sweep (`orientation_only=True`); keeps climate horizons strictly separate | `L12` |
| `F-12` | `L1` | `engine/amg/model_comparison.py` | Side-by-side `AMG-A`/`AMG-M`/`RothC` comparator; blocks unverified `AMG-A`/`AMG-M` voting and checks continuity | `L18` |
| `F-13` | `L2b` | `engine/rothc/millennial_erosion.py` | Mass-conserving `POM`/`MAOM` partition and opt-in `HYPOTHESIS` lateral erosional SOC export | `L19`, `L20` |
| `F-14` | `L1` | `engine/water/twin_calibration.py` | Forward-mode `Dual` AD, KGML mass-conservation gate (`CONTROL_FAILED`), split-conformal, Bayesian updater | `L34`, `L35`, `L36`, `L37` |
| `F-15` | `L2b` | `economics/accounts.py` | Three separate accounts (`gross_margin`, `accounting_result`, `cash_flow`) with double-count guards | `L42` |
| `F-16` | `L2b` | `economics/input_cost_ledger.py` | 8-rubric cost ledger, `PriceBookEntry` provenance, NPK/S balance, explicit cover-crop savings guard | `L43` |
| `F-17` | `L2b` | `economics/temporal_valuation.py` | Common-horizon `NPV` & `AE` enforcing real-vs-nominal consistency and no non-monetary depreciation | `L44` |
| `F-18` | `L2b` | `economics/livestock.py` | `own_production` vs `buy_fatten_sell` livestock evaluator with pasture completeness (`MISSING_INPUT`) rule | `L24`, `L45` |
| `F-19` | `L2b` | `economics/soil_degradation.py` | Mutually exclusive soil valuation methods, `CVaR`, and exact `EVPI`/`EVSI` (qualitative fallback when inputs missing) | `L46` |
| `F-20` | `L2b` | `decision/multi_objective_nsga2.py` | Pure-Python constrained `NSGA-II` Pareto search quarantining `Missing` objectives in `unrankable_missing` | `L39` |
| `F-21` | `L2b` | `decision/scenario_discovery.py` | `PRIM`-style vulnerability boxes and `DAPP` adaptive pathways with signpost lead-time checks | `L40` |
| `F-22` | `L2b` | `decision/grounded_explainer.py` | Deterministic template explainer and strict numeric/claim grounding verifier (`CONTROL_FAILED`) | `L41` |
| `F-23` | `L2a` | `adapters/future_climate_projections.py` | `NEX-GDDP-CMIP6`, `ISIMIP3b`, `GEOS-S2S-3`/`NMME` adapters; keeps ensembles strictly separate (`cross_ensemble_averaged=False`) | `L26`, `L27`, `L28` |
| `F-24` | `L2a` | `adapters/earth_observation_frontier.py` | `SPL2SMAP_S` (`2026-07-01` cutoff), `ECOSTRESS`, `NISAR SME2` (`PROVISIONAL_PRE_2027`), `EMIT`, and gated EO proposals | `L29`, `L30`, `L31`, `L32`, `L33` |
| `F-25` | `L0` | `validation/frontier_governance.py` | 46-line §14 inventory registry, §7 layer-ablation gate, national cell-grid & emulator finalist gate, Rev13 spec | `L01`–`L46` |

Dedicated standalone line modules completing `46/46` (`100%`) §14 implementation coverage (strictly isolated from normative `EP1`/`EP3` and `local_validation_status = "UNVALIDATED"`):

| Line | Lane | Module | Core Governance / Scientific Guard |
|---|---|---|---|
| `L06` | `L0` | [../engine/erosion/dynamic_surface_routing.py](../engine/erosion/dynamic_surface_routing.py) | Post-tillage roughness & consolidation trajectories, dynamic segmented `LS`, and channel export guard refusing to equate `IC` with mass export (`NOT_AVAILABLE` when uncalibrated) |
| `L16` | `L1` | [../engine/water/soil_structure_feedback.py](../engine/water/soil_structure_feedback.py) | Dynamic topsoil bulk density, porosity, rainfall crusting attenuation, and exploratory `cn_delta_estimate` diagnostics (`normative_ep3_wired=False`) |

---

## 5. Complete 46-Line Rev13 Frontier Inventory (§14)

All 46 entries below correspond 1-to-1 with `FRONTIER_INVENTORY` in [../validation/frontier_governance.py](../validation/frontier_governance.py). Four-axis totals across `L01`–`L46`:

- `method_maturity`: `23` `ESTABLISHED`, `16` `FRONTIER`, `7` `HYPOTHESIS`
- `implementation_status`: **`46/46` (`100%`) implemented** (`40` `FRONTIER_IMPLEMENTED`, `6` `CORE_IMPLEMENTED`, **`0` `NOT_IMPLEMENTED`**)
- `data_availability`: `15` `LOCAL_MEASUREMENT_REQUIRED`, `13` `SITE_DECLARED_REQUIRED`, `13` `AVAILABLE_PUBLIC`, `4` `PROVISIONAL_OR_PAUSED`, `1` `RESTRICTED_OR_ABSENT`
- `local_validation_status`: **`0` `VALIDATED`**, `31` `UNVALIDATED`, `8` `EXPLORATORY_ONLY`, `6` `PARTIAL`, `1` `BLOCKED_NOT_EVALUATED`

| ID | Domain | Capability / Research Line | Units | Method Maturity | Implementation | Data Availability | Local Validation |
|---|---|---|---|---|---|---|---|
| `L01` | `Erosion` | Normative vs exploratory erosion separation (`pre_evaluation` A/T guard) | `F-01` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `BLOCKED_NOT_EVALUATED` |
| `L02` | `Erosion` | Sub-hourly 30-min storm separation and `EI30` with official R anchoring | `F-02` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `PROVISIONAL_OR_PAUSED` | `UNVALIDATED` |
| `L03` | `Erosion` | D8 topographic routing and Index of Connectivity (`IC` relative hotspot) | `F-03` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `EXPLORATORY_ONLY` |
| `L04` | `Erosion` | Observed satellite dry residue cover (`EMIT` NPV / calibrated `HLS` `NDTI`) | `F-04` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L05` | `Erosion` | Static AH703 `LS`, GloREDa monthly `R` climatology, and declared `C` baseline | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `PARTIAL` |
| `L06` | `Erosion` | Full RUSLE2 dynamic `LS`, roughness, consolidation, and channel sediment export | `F-01`, `F-03` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L07` | `Water` | Daily FAO-56 Penman-Monteith `ET0` and dual-`Kc` root-zone water balance | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `PARTIAL` |
| `L08` | `Water` | Water Cloud Model (`WCM`) `0-5 cm` surface soil moisture inversion | `F-05` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L09` | `Water` | Ensemble Kalman Filter (`EnKF`) state assimilation with holdout split | `F-06` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L10` | `Water` | Seeded two-state Markov conditional resampling synthetic daily weather | `F-08` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `EXPLORATORY_ONLY` |
| `L11` | `Water` | Daily thermal-photoperiod-vernalization crop phenology simulator | `F-10` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L12` | `Water` | Multi-year candidate sowing-window frost/heat/water risk sweep | `F-11` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `EXPLORATORY_ONLY` |
| `L13` | `Soil` | Parametric pedotransfer functions (`FC`, `PWP`, `AWC`) with 3-tier provenance | `F-07` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L14` | `Soil` | SoilGrids 2.0 / CONEAT regional prior mapping with effective-depth guard | `F-07` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L15` | `Soil` | Documented `0.90 m` station hydraulic profile vs `0.60 m` national reference | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `PARTIAL` |
| `L16` | `Soil` | Dynamic bulk density, structural crusting, and compaction feedback | `F-07` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L17` | `Carbon` | `AMG-A` (`EP5`) and `RothC-26.3` (`EP6`) SOC balance on shared `CarbonForcing` | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L18` | `Carbon` | Carbon model trajectory comparator and structural-dependence guard | `F-12` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `UNVALIDATED` |
| `L19` | `Carbon` | Measurable `POM`/`MAOM` mineral sorption capacity partition | `F-13` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L20` | `Carbon` | Coupled lateral erosional SOC export hypothesis | `F-13` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L21` | `Yield` | FAO-33 seasonal and stagewise water-limited crop yield response (`Ky`) | `F-09` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L22` | `Yield` | Multi-model yield contrast bundle (`Declared`, `FAO-Ky`, `AquaCrop-OSPy`) | `F-09` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L23` | `Yield` | `GECROS`-class mechanistic crop hypothesis envelope | `F-09` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `RESTRICTED_OR_ABSENT` | `UNVALIDATED` |
| `L24` | `Yield` | Water-dependent annual forage-to-beef yield proxy | `F-18` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L25` | `Climate` | Historical daily meteorology and reanalysis context (`NASA POWER` / `IMERG`) | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `PARTIAL` |
| `L26` | `Climate` | `NEX-GDDP-CMIP6` downscaled daily future climate projections | `F-23` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `EXPLORATORY_ONLY` |
| `L27` | `Climate` | `ISIMIP3b` bias-adjusted 5-model contrast ensembles (`SSP1-2.6`/`3-7.0`/`5-8.5`) | `F-23` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `EXPLORATORY_ONLY` |
| `L28` | `Climate` | `GEOS-S2S-3` / `NMME` seasonal tercile and member forecast subset | `F-23` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L29` | `Observation` | `SPL2SMAP_S v003` (`3 km`) archive with `2026-07-01` forward-pause guard | `F-24` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `PROVISIONAL_OR_PAUSED` | `UNVALIDATED` |
| `L30` | `Observation` | `ECOSTRESS` (`70 m`) QA-filtered thermal evapotranspiration observations | `F-24` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L31` | `Observation` | `NISAR SME2` (`200 m`) L-band soil moisture (`PROVISIONAL_PRE_2027`) | `F-24` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `PROVISIONAL_OR_PAUSED` | `UNVALIDATED` |
| `L32` | `Observation` | `EMIT` (`60 m`) hyperspectral PV/NPV/bare fractional cover | `F-24` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `PROVISIONAL_OR_PAUSED` | `UNVALIDATED` |
| `L33` | `Observation` | EO foundation-model crop/date proposals (`Prithvi-EO-2.0`/`Galileo`/`Presto`) | `F-24` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `AVAILABLE_PUBLIC` | `UNVALIDATED` |
| `L34` | `Twin` | Forward-mode `Dual` automatic differentiation parameter sensitivity | `F-14` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `EXPLORATORY_ONLY` |
| `L35` | `Twin` | Knowledge-guided ML (`KGML`) mass-conserving residual validation gate | `F-14` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L36` | `Twin` | Split-conformal prediction calibration with disjoint reserved holdout | `F-14` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L37` | `Twin` | Discrete Bayesian updater and emulator finalist full-physics gate | `F-14`, `F-25` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
| `L38` | `Decision` | Core robust dominance, paired cell counts, tipping, and VoI priority | `CORE` | `ESTABLISHED` | `CORE_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `PARTIAL` |
| `L39` | `Decision` | Pure-Python constrained multi-objective `NSGA-II` portfolio search | `F-20` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `EXPLORATORY_ONLY` |
| `L40` | `Decision` | `PRIM` scenario discovery boxes and `DAPP` signpost adaptive pathways | `F-21` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `EXPLORATORY_ONLY` |
| `L41` | `Decision` | Deterministic grounded explainer and hypothesis-mode output verifier | `F-22` | `FRONTIER` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `PARTIAL` |
| `L42` | `Economics` | Three separate Rev13 economic accounts (`gross_margin`, `accounting`, `cash`) | `F-15` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `UNVALIDATED` |
| `L43` | `Economics` | Eight-rubric farm input cost ledger and NPK/S nutrient balance | `F-16` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `UNVALIDATED` |
| `L44` | `Economics` | Common-horizon temporal `NPV` and Equivalent Annuity (`AE`) evaluator | `F-17` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `UNVALIDATED` |
| `L45` | `Economics` | Forage-to-beef enterprise evaluator with pasture completeness guard | `F-18` | `ESTABLISHED` | `FRONTIER_IMPLEMENTED` | `SITE_DECLARED_REQUIRED` | `UNVALIDATED` |
| `L46` | `Economics` | Non-additive soil degradation valuation, `CVaR` tail risk, and `EVPI`/`EVSI` | `F-19` | `HYPOTHESIS` | `FRONTIER_IMPLEMENTED` | `LOCAL_MEASUREMENT_REQUIRED` | `UNVALIDATED` |
