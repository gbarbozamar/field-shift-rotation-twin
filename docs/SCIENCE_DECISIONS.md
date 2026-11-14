# Science decisions and pre-check findings

One place that lists the science decisions the lead developer has accepted, where each acceptance is recorded, what it changes in this repository and what is still missing; and, apart from them, the findings of the AI pre-check of 14 November 2026, which are **findings, not decisions**.

> **Status: PROPOSED** (blueprint section 3.7). Written by an AI integration session on 14 November 2026 from the lead developer's acceptance records and issue #77. It records decisions already taken; it takes none. It takes effect as a record when a person approves the pull request. The lead developer is also the science lead and the team reviews (D66); no external reviewer is waited for.

## How to read this file

Five kinds of statement are kept apart, and every row says which one it is:

| Kind | Meaning | What it is not |
|---|---|---|
| **Lead decision** | The lead developer chose it, in issue #77 (`D` numbers) or in an explicit chat reply recorded in the acceptance ledger (`USER-` identifiers) | Not a check of a published value (D34): accepting a method or a package does not mean a person opened the source at the locator and signed |
| **Research proposal** | A session proposed it from sources (records `RESEARCH_PROPOSAL`) | Not accepted until a lead decision says so |
| **AI transcription** | A session copied a value, form or text from an opened source, with locator and date | Not checked: under D34 a person checks it and signs `checked_by` |
| **Human check** | The lead developer (`gbarbozamar`, D66) opened the source at the locator and signed | **None exists yet.** No row of this file is signed |
| **Executed test** | A test of this repository ran and passed | A structural test or a test on PLACEHOLDER or synthetic data is not a scientific validation |

Values: this file repeats the values that are **declared** by the lead developer as scenario choices (dates, layer depths, sensitivity levels). It does **not** repeat values transcribed from a publication (crop coefficients, depletion fractions, available water, root anchors): those enter `params/records/` only after the lead developer checks them at the locator (D34, D66), and this file gives their locator only.

## Where the acceptances are recorded

1. **Issue #77**, decisions D1 to D70, each with its date. The repository's decision log.
2. **The acceptance ledger of the lead developer** (`accepted_by_user`, identifiers `USER-A` to `USER-AS`), explicit chat replies of 14 November 2026, kept in a local research folder that is **not versioned** and is not a primary source. They are not yet in issue #77. This file carries them so that they can be traced from the repository; recording them in #77 is for the lead developer (see "To record in issue #77" at the end).
3. **One later chat acceptance, not persisted in the ledger** (after `USER-AS`): both soybean sowing dates use the same soybean material, the one tied to the root reference of the accepted soil profile. It fixes no stage date: no R3 or R6 date is inferred from it.

The research folder also holds a file of `RESEARCH_PROPOSAL` records (the "science decisions" dossier of 14 November 2026). Those are proposals, not acceptances, and nothing below is taken from them unless a `USER-` row accepts it.

## Lead decisions from the acceptance ledger

Status words: `DECIDED` (in force), `DECIDED, provisional` (in force for the exploratory route, with its limits), `SUPERSEDED` (replaced by the row named; kept for the trace). "Repo" says where the decision lands; "Missing" what it still needs before it gives a number.

### Case, scenarios and comparison

| Id | Decision, as accepted | Status | Repo | Missing |
|---|---|---|---|---|
| USER-C | The La Estanzuela station is the base of the demonstration. The runoff plots of Grahmann et al. (2022) and the carbon of the long-term experiment LEELP1 stay **separate experiments**: an erosion or carbon contrast from one is never merged with the other | `DECIDED` | Demonstration case (`demo/`, lane L2b); `docs/VALIDATION.md` E7, H10 | The example soil-and-slope file of D67 |
| USER-E | Three scenarios: continuous annual cropping, diversified annual crops, crop-pasture rotation | `DECIDED`, made concrete by USER-AM, USER-AN, USER-AQ | — | — |
| USER-AM | Three exploratory templates: (1) annual soybean; (2) wheat / second-crop soybean, then maize; (3) the same agricultural sequence followed by two years of pasture | `DECIDED` | Rotation definitions of the demonstration (D3, D5: explicit components) | Rotation definition files with the dates of USER-AP and USER-AQ |
| USER-AN | The pasture of template 3 is pure alfalfa. The water profile is limited to its documented 0.90 m, with no claim of a physical root barrier | `DECIDED`, detailed by USER-AQ | — | — |
| USER-AP | Declared nominal management calendar: annual soybean 15 Nov to 5 May; wheat 25 May to 5 Dec; second-crop soybean 10 Dec to 10 May; maize 20 Sep to 20 Apr. **Scenario choices, not observed or predicted harvests**; phenology is separate; incompatibilities are flagged; date sensitivity is required | `DECIDED` | Rotation definitions; calendar engine (EP2) | The date sensitivity design; no agronomic calendar rule is built (`engine/calendar/README.md`) |
| USER-AQ | Commercial pure alfalfa (the cultivar named in the ledger): sown 25 Apr after maize, kept 24 months to 24 Apr, before wheat on 25 May; nominal cuts from 15 Oct every 45 days to mid-April, with an explicit winter pause; **harvested biomass removed**. A declared project scenario, not an observed treatment. The returned-biomass benchmark of LEELP1 stays separate | `DECIDED` | Rotation definition (management fields, D4, D39); residue ledger and carbon forcing | Dry matter of the cuts (`null` in the ledger); stubble, litter, roots and rhizodeposition as explicit inputs |
| USER-H | The LEELP1 benchmark keeps the mown pasture material; commercial grazing or export is a separate scenario that inherits no validation | `DECIDED` | `docs/VALIDATION.md` carbon entries | — |
| USER-Z | Initial executable calendars reject crops overlapping on the same area. Published relay dates are kept unchanged, and no direct reproduction is claimed until competition or intercropping is represented | `DECIDED` | Calendar engine (EP2) | An overlap rule in `engine/calendar/` (lane L1). The ledger's own check of the three templates found no overlap (an AI check, not a repository test) |
| USER-K | Agricultural year of the demonstration: **1 July to 30 June**; no state is reset | `DECIDED` | The start month of the case (C5.4, D7) is 7; D44 already forbids resets | The case file of the demonstration |
| USER-J | Paired scenarios and paired years; trade-offs explicit; the share of scenarios covered is not a probability of success | `DECIDED` | Decision layer (`decision/`), decision output contract (#170) | — |
| USER-R | A robust preference needs paired non-deterioration on every indicator in every admitted scenario, with at least one strict improvement; reversals or trade-offs give no robust preferred rotation | `DECIDED` | `docs/VALIDATION.md` D5 (D59), `decision/` | — |
| USER-M | An integral comparison needs erosion, dual-coefficient water, AMG and RothC with their controls passed; **no integral winner while any required component is unavailable** | `DECIDED` | Decision layer; results (D12) | Every axis |
| USER-A | Water by the dual coefficient of FAO-56; no complete ranking if water is unavailable | `DECIDED`; consistent with D44 | `docs/METHODS.md` M2 | — |
| USER-Q | Prototype admissibility: mean erosion at or below a **verified** soil-loss tolerance T; net stock change at or above zero in each of AMG and RothC over a common horizon; the water ratio compared without a universal cut-off; no regulatory certification | `DECIDED` | `docs/VALIDATION.md` D1 (D60) | T has no verified source (M1.3; finding 10 below), so erosion admissibility is "not evaluated" (D60) |
| USER-S | Several uncertain inputs are varied **jointly** from the first sensitivity matrix, not residue cover alone | `DECIDED` | Test plan contract | — |
| USER-T | Initial joint design: residue cover, coherent soil profile, termination date where it applies, and terrain; up to three levels per block, 81 combinations per rotation before years and initial-state controls | `DECIDED` for the blocks; its generic levels withdrawn by USER-AA | Test plan contract | Levels with local published evidence |
| USER-AA | The generic levels of residue cover, of a capacity multiplier and of termination date are **withdrawn**; local published evidence is required before the numerical matrix is fixed. The capacity multiplier was a proposal, never water above capacity, and is not approved | `DECIDED`; supersedes the levels of USER-T | — | Local evidence per block |
| USER-AD | Initial termination sensitivity: 30 and 60 days before soybean sowing (trials at the station). Other trials' levels are excluded from the initial matrix; biomass and cover stay conditional on management; no arbitrary level is filled | `DECIDED` | Rotation definition (termination, D4, D50) | Termination travelling in the rotation definition (D50) |
| USER-B | The lead developer accepts packages with evidence; independent validation stays pending | `DECIDED`; under D66 the team reviews | — | — |

### Erosion

| Id | Decision, as accepted | Status | Repo | Missing |
|---|---|---|---|---|
| USER-G | First release: mean annual national erosivity and a **verified published monthly distribution**; the variation of erosion between years is deferred. Water stays daily and historical | `DECIDED`; D69 names the distribution | `docs/METHODS.md` M1.2; `engine/erosion/r_factor/climatology.py` | The licence of D69; the twelve values at the point, checked (D34) |
| USER-I | RUSLE2 is prioritised over the RUSLE1 LS package that was proposed; scope and version of the implementation to be specified | `DECIDED` | `docs/METHODS.md` M1.4; `engine/erosion/ls.py` | See USER-L |
| USER-L | The classical daily route of RUSLE2, built in stages starting with **dynamic LS**; explicitly partial while other components stay simplified | `DECIDED` | `engine/erosion/` | Dynamic LS is not built: `ls.py` holds the static two-branch steepness and length forms (S2 Eq. 4-1 to 4-5, S1 Eq. 2.10 to 2.13, 5.3, 5.4). D66, later the same day, plans the check of the LS rows of S2 for the demonstration point; this file reads that as the static LS standing in until the dynamic stage exists, declared as partial (see "Reconciliation") |

D10, D11, D45, D67, D69 of issue #77 stay as they are written there. **D68 and D70** (how R and K reach the point) are not applied here: see "Pending, not to be resolved here".

### Water

| Id | Decision, as accepted | Status | Repo | Missing |
|---|---|---|---|---|
| USER-AE | The executable water case uses the **full hydraulic profile of Capurro (2017) at the station, documented to 0.90 m**. The station's average available-water reference of the national agroclimate service (0.60 m) is kept as a **separate** reference. Neither profile is identified as the soil of LEELP1 or of the Grahmann plots | `DECIDED`; supersedes USER-AC as the principal profile | EP3 parameters `column_capacity`, `column_depth`, `total_evaporable_water` (`engine/water/EXPOSURE.md` OPEN 7, 13) | The profile's values, transcribed and checked (D34); the licence question of D49 for the national table |
| USER-AC | The national agroclimate service's average available water at the station as provisional reference; generic capacity multipliers withdrawn | `SUPERSEDED` by USER-AE as principal profile; kept as a separate reference | — | — |
| USER-AF | Water evaporable below the permanent wilting point is accounted inside the same physical storage and never becomes available to roots; a conservative mass ledger; the evaporation layer is not counted twice | `DECIDED` | `engine/water/balance/`, `evaporation/` (lane L1) | A check that the two layers share one storage |
| USER-AG | Evaporation-layer depth Ze: **0.10 m** principal, **0.15 m** in sensitivity, for the accepted profile | `DECIDED` | EP3 (`total_evaporable_water` read directly today: EXPOSURE.md choice 8) | Computing TEW from Ze and the profile |
| USER-AL | Provisional REW sensitivity without waiting for local data: **8, 9, 10, 11, 12 mm** crossed with Ze 0.10 and 0.15 m. The reference 10 mm is an **assumption**, not a local calibration. Sensitivity and preference reversals are reported | `DECIDED, provisional`; supersedes the waiting requirement of USER-AH and USER-AJ **for this exploratory route only** | EP3 `readily_evaporable_water` | Same-soil REW stays the calibration target |
| USER-AH, USER-AJ | Local, same-soil REW required before executing the water case; the generic FAO 8/10/12 mm fallback rejected; another site's calibrated REW not transferred | Waiting requirement `SUPERSEDED` for the exploratory route by USER-AL; still the target for a calibrated claim | — | — |
| USER-AI | Local crop-specific root curves required before execution; the initial depth of the FAO bean example not transferred | Waiting requirement `SUPERSEDED` for the exploratory route by USER-AO and USER-AK | — | — |
| USER-AO | Provisional crop-specific root-growth curves of FAO-56 (Annex 8), with explicit initial-depth assumptions and sensitivity, for exploratory comparison. Local validation stays pending | `DECIDED, provisional` | EP3 `root_depth` (one value per crop today: EXPOSURE.md choice 6, OPEN 4) | Stage dates and the daily construction of the curve; a part that builds it |
| USER-AK | Provisional local soybean root curve inferred from Capurro (2016): an initial depth assumed, later anchors inferred from water extraction by stage; access capped at 0.90 m, raw evidence kept; no direct root validation claimed; not transferred to other crops | `DECIDED, provisional` | As USER-AO | Stage dates (see USER-AS and the soybean-material acceptance) |
| USER-AR | FAO-56 Table 17 basal crop coefficients and Table 22 depletion fractions as a **transferred reference** for soybean, wheat, dry-grain maize and alfalfa (individual cuts); climatic adjustment and sensitivity kept; Uruguayan evidence compared separately; no local calibration claimed | `DECIDED` | EP3 `basal_crop_coefficient`, `readily_available_fraction` | The values, transcribed at FAO-56 Table 17 and Table 22 and checked by the lead developer (D34, D66); the curve of Kcb by stage (OPEN 4) |
| USER-P | Initial water state in sensitivity: depletion zero and depletion equal to TAW, applied the same way to every rotation; no robust claim if the conclusion depends on the unknown initial state | `DECIDED` | EP3 `initial_storage`, `initial_depletion` (EXPOSURE.md OPEN 14) | — |
| USER-X | Water decision summary: the sum of actual transpiration over the sum of potential transpiration over the supported analysis windows; crop details and the worst crop ratio are shown, not weighted | `DECIDED` | `contracts/CONVENTIONS.md` C1.4 (question 4 of `contracts/results/README.md`; D61) | The supported windows (critical periods, USER-U, USER-AS) |
| USER-Y | Pasture water use stays in the continuous balance and is reported descriptively; the decision ratio uses only crops with supported critical windows, keeping the pasture's carry-over on the next crop | `DECIDED` | C1.4; EP3 | As USER-X |
| USER-U | INIA phenology-tool estimates with recorded inputs and outputs are preferred; missing stages stay missing for the water indicator they affect | `DECIDED`, refined by USER-AS | — | — |
| USER-AS | Traceable phenology estimates are sought first in public publications, with explicit uncertainty; no account is registered on a phenology service for this route | `DECIDED` | — | Stage dates for each crop and sowing date |
| Later, not persisted | Both soybean sowing dates use the same soybean material, the one tied to the Capurro root reference | `DECIDED` (chat; to be written into the ledger and #77) | — | No R3 or R6 date follows from it |
| USER-F | The FAO reference package is accepted, and the comparison is made at the **published precision**; the internal daily state is never rounded | `DECIDED` | `engine/water/et0/test_h2.py` (H2) | Which printed figure H2 compares with, and the tolerance: P20, lead developer (finding 9 below) |

### Carbon

| Id | Decision, as accepted | Status | Repo | Missing |
|---|---|---|---|---|
| USER-D | The carbon benchmark of LEELP1 is 0 to 20 cm; AMG and RothC are compared on the same support | `DECIDED` | `docs/VALIDATION.md` carbon entries | — |
| USER-AB | AMG-A, the annual published reference, takes part in the selection. AMG-M is experimental, checked against AMG-A under uniform forcing, and casts no separate carbon vote. RothC stays mandatory | `DECIDED` | `engine/amg/` (#181), `engine/rothc/` | — |
| USER-V | Standard RothC decomposition constants not fixed until another published parametrisation is compared | `SUPERSEDED` by USER-W | — | — |
| USER-W | After the comparison, standard RothC is the implementation reference and is evaluated locally with LEELP1; rates calibrated elsewhere are not transferred automatically | `DECIDED`; consistent with D64 | `engine/rothc/` | The local evaluation |
| USER-N | The demonstration uses an explicit RothC variant with monthly FAO-56 ET0 as evaporative demand, **identified as an adaptation**; the standard open-pan mode is kept for the manual reference tests; local validation of the variant pending | `DECIDED` | `engine/rothc/`, carbon forcing (D65) | — |
| USER-O | Scenario comparisons start from a common total soil organic carbon; a documented, model-specific spin-up splits the pools, with sensitivity; the real soil is not claimed to be in equilibrium | `DECIDED` | Carbon forcing (D65: starting state inside `CarbonForcing`) | — |

## Reconciliation of earlier and later decisions

Later decisions that relaxed an earlier restriction are applied as relaxed, for the scope they name, and the earlier requirement is **not** restored:

- REW: USER-AH and USER-AJ asked for same-soil REW before running; USER-AL authorises the provisional 8 to 12 mm grid for the exploratory route. Same-soil REW stays the target of any calibrated claim.
- Roots: USER-AI asked for local curves before running; USER-AO (FAO provisional, all crops) and USER-AK (soybean, local inferred) authorise the exploratory route.
- Soil profile: USER-AC gave the 0.60 m average reference; USER-AE makes the 0.90 m profile the principal one and keeps the other as a separate reference.
- Sensitivity levels: USER-T fixed the blocks; USER-AA withdrew the generic levels; USER-AD set termination at 30 and 60 days.
- RothC: USER-V deferred the constants; USER-W closes it with standard RothC as reference.
- LS: USER-I and USER-L make the dynamic LS of RUSLE2 the first stage of the erosion route. D66, recorded later the same day, has the lead developer check the LS rows of S2 first for the demonstration point. Read together (this file's reading, not a new decision): the static LS that exists stands in for the demonstration, declared as a partial stage, until dynamic LS is built.

## Pending, not to be resolved here

- **How R and K reach the demonstration point.** D68 (nearest locality of S4 Cuadro 2) and D70 (mean K of the soil class of S9 Table 1) are recorded in issue #77. A later instruction of the lead developer to the pre-check session keeps blocks B3 and B4 (rows 1 to 76 of the check sheet) and questions P09 and P10 pending, choosing no locality, method, class or unit. Which one holds is being confirmed with the lead developer by the coordinating session. This file applies neither and undoes neither; the 76 rows stay pending.
- **The licence of the climatology of D69.** Until the team confirms it, no monthly value is committed and the monthly values stay `NOT_AVAILABLE`.

## Findings of the AI pre-check (14 November 2026)

**Findings, not decisions.** An AI session opened the sources and compared them with the code (snapshot `7df4463`, then `ac7184c`; the forms checked did not change between the two). No person has checked these readings under D34. "Recommendation" is the AI's, marked as such, and is not a decision.

| # | Finding | Source and locator | What the code does | Choice it opens |
|---|---|---|---|---|
| 1 | **Effective canopy cover (F09) and the roughness term and units of ground cover (F10)** | S1 p. 138 (PDF 163) Eq. 6.2; p. 140 (PDF 165) Eq. 6.5; pp. 140 to 141 (PDF 165 to 166) Eq. 6.6 | `canopy_subfactor` takes the canopy cover itself, not the effective cover; `surface_cover_subfactor` takes a fraction, has no roughness term, and its coefficient is not the coefficient of S1 in percent to the minus one | P16 (`engine/erosion/c_factor/README.md` OPEN 1, 3) |
| 2 | **Seven daily sub-factors and daily integration (F11, F15)** | S1 p. 138 (PDF 163) Eq. 6.1; S1 p. 9 (PDF 34) | Two sub-factors and a monthly weighting by the erosivity fraction; D45 names four sub-factors set to one, not ridge height and antecedent moisture | Completing the list set to one; declaring monthly weighting a partial stage under USER-L (`c_factor/README.md` OPEN 16, 17) |
| 3 | **Decay modified by moisture and temperature (F13, F14)**; S1 also calibrates against a daily climate disaggregated from monthly means, which is not the observed daily rain of D23 | S1 pp. 248 to 249 (PDF 273 to 274) Eq. 10.3 to 10.6; p. 250 (PDF 275) | A constant rate by residue type and elapsed time | P17 (`c_factor/README.md` OPEN 2) |
| 4 | **Bound Rs/Rso at most 1 (F33)**; the wind bound for using Eq. 6 is also not applied (F36) | FAO-56 ch. 3, Eq. 39, list of symbols; ch. 3, "Missing wind speed data" | `net_longwave_radiation` applies no bound (OPEN 10 of `engine/water/et0/README.md`) | P21 |
| 5 | **Erratum in the image of FAO-56 Eq. 9 (F19)**: the image prints a minus sign; the text, Box 11 and Example 18 use the mean | FAO-56 ch. 3, Eq. 9 image; ch. 4 Box 11, Example 18 | `mean_temperature` takes the mean. **No subtraction is to be introduced** | None: keep the code; record the erratum |
| 6 | **Tew left out of the surface-layer balance (F52)**; FAO-56 allows ignoring it in some cases, whose scope must be stated | FAO-56 ch. 7, Eq. 77 | The step omits Tew (and irrigation, which is out of scope: rain-fed, D44) | Scope of the simplification |
| 7 | **Control of the monthly fraction (F16, P23)**: S4 prints regressions of **annual** R (Eq. 1 on precipitation, Eq. 2 on the modified Fournier index); pp. 92 to 93 neither print the formula of the Fournier index nor give a monthly distribution. Eq. 2 prints a squared P, kept as printed | S4 p. 92 (PDF 2), p. 93 Cuadro 1 | `r_factor/control.py` applies a power of the monthly precipitation: no source among the pages read | Status of the control under D69 (`r_factor/README.md` OPEN 7) |
| 8 | **Curve Number (F42 to F44, P18)**: the algebraic forms match NRCS (2004), National Engineering Handbook Part 630, ch. 10, Eq. 10-9 to 10-13 (pp. 10-3, 10-4); the 2025 edition, section 630.113G, p. 21, says that using it as a loss in continuous simulation is outside its intended use | As stated | The forms of `engine/water/runoff/` | Whether CN is admitted in the continuous balance of D44, declared as an adaptation (P18); the CN table is not chosen |
| 9 | **Rounding oddities of FAO-56 Example 18** (the row of es printed without the halving, a printed deficit that differs from the difference shown, rounded intermediates) do **not** authorise inventing a tolerance | FAO-56 ch. 4, Example 18 | `test_h2.py` is skipped | The printed figure and the tolerance of H2 (P20), lead developer |
| 10 | **The secondary mention of 7 t ha-1** is not adopted as the tolerance T of the soil: it cites no primary norm and prints no per-year unit in that passage | Carrasco-Letelier and Beretta-Blanco (2017), *Ciencia e Investigación Agraria* 44(2), p. 190 | No tolerance is read | T stays `OPEN` (M1.3); erosion admissibility "not evaluated" (D60, USER-Q) |

## Pending human signature (D34, D66)

Counts of the AI pre-check, from the copies of the check sheets (the originals of the lead developer are unchanged). **No row is signed.** A value enters `params/records/` only after `gbarbozamar` checks it at its locator (D66).

| Block | Rows | AI reading | Signature |
|---|---|---|---|
| B1 LS coefficients | 78 to 87 (10) | 10 match | Pending |
| B2 tables for E3 | 88 to 119 (32) | 32 match | Pending; cells and tolerance of E3 with the lead developer |
| B3 R | 1 to 52 | **Pending by the lead developer's choice**, not a failure to open | Pending |
| B4 K | 53 to 76 | **Pending by the lead developer's choice** | Pending |
| B5 tolerance mention | 77 (1) | Matches as a secondary citation | Pending; not T |
| B6 C | 52, with derived row 315 | 52 match | Pending |
| B7 FAO-56 constants | 145 to 186 (42) | 42 match | Pending |
| B8 Example 18 | 187 to 237 (51) | 51 match as transcriptions | Pending |
| B9 residues of other crops | 260 to 292 (33) | 33 match | Pending |
| B10 calendar rules | 297 to 314 (18) | 14 match, 1 differs literally (row 297), 3 not opened | Pending |
| Forms | 55 | 42 match, 10 do not, 3 without an identified source | Pending |

## To record in issue #77

The `USER-` decisions above, with the later soybean-material acceptance, are not in issue #77. Recording them there (with the next free `D` numbers) is the lead developer's or the coordinating session's act; this session publishes nothing.
