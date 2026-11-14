# Methods

Which method each engine implements, and where it is published. This file names methods and sources. It holds **no parameter value, no coefficient, no threshold and no expected value**: those live in the parameter catalogue (`params/`), each one transcribed from its source by a person and checked by a second person, and in the validation protocol (`docs/VALIDATION.md`).

## How to read this file

- Every item has one status: `PROPOSED`, `DECIDED` or `OPEN`, with the meaning of blueprint section 3.7 and of `contracts/CONVENTIONS.md`.
- The items below were transcribed by an AI session from the planning notes of the lead developer, who approved them on 14 November 2026: they are `DECIDED`. They are science class: a science reviewer still has to accept them. A point marked `OPEN` inside a decided item is not decided.
- Two points that were `OPEN` here, the source of `K` in M1.3 and the units of `R` and `K` in M1.7, were decided by the lead developer on 14 November 2026 and recorded in issue #77 (decisions D10 and D11). An AI session transcribed them into this file. Like the other items of this file, a science reviewer still has to accept them.
- Section M2 (the water method) and the sub-factors of M1.5 hold decisions D44 and D45 of the lead developer, of 14 November 2026, recorded in [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346). A builder session wrote them into this file. Issue #77 says of them that where they are science class, a science reviewer may still review them; it does not say which of them are. This file reads both as science class, like its other items, so it marks acceptance by a science reviewer as pending.
- Decisions the lead developer accepted in explicit chat replies on 14 November 2026 (identifiers `USER-`), which are not yet in issue #77, and the findings of the AI pre-check of the same day, are listed in [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md) with where each acceptance is recorded. This file points to them where they touch a method. A finding of the pre-check is not a decision and not a person's check under D34.
- A citation here says where a method is published. The column "Read" says how far the planning notes got with the source: `read` (the abstract or the text was read), `fragments` (only fragments of the abstract), or `located` (the reference was found, nothing of it was read). A builder session never takes a number from memory of these sources: it reads it from the parameter catalogue, and returns a missing value with its reason when the catalogue does not have it.
- If an engine needs a method that is not in this file, that is an `OPEN` point for the lead developer, not something a session chooses.

## M1 Soil loss: `engine/erosion/`

Status of the whole section: `DECIDED`, except the points marked `OPEN`: in M1.3 the source of the soil-loss tolerance, in M1.5 the source of each input and the level of residue cover at sowing, and in M1.7 the confirmation of the units against the sources. Acceptance by a science reviewer is pending.

### M1.1 The method

The Revised Universal Soil Loss Equation (RUSLE). The long-term average annual soil loss is the product of five factors:

`A = R · K · LS · C · P`

| Factor | What it stands for | Changes with the rotation |
|---|---|---|
| `R` | Rainfall erosivity | No |
| `K` | Soil erodibility | No |
| `LS` | Slope length and steepness | No |
| `C` | Cover and management, weighted by when the erosive rain falls | **Yes: it is the main channel** |
| `P` | Support practices | Only if practices are added |

Sources: S1, S2.

What the result is used for: comparing rotations with each other and against the soil-loss tolerance of the soil, with ranges. The text on the limits of the method is a separate unit of blueprint section 8, written by people.

### M1.2 Factor R: level, monthly fraction and variation between years

Two parts, from two sources:

| Part | Method | Source |
|---|---|---|
| Mean annual level of `R` at the field | The published national values, interpolated to the field | S4 |
| Fraction of the annual erosivity that falls in each month, and variation between years | A daily erosivity index computed from daily precipitation, of the power-law family, used **in relative terms only**: the share of each month in the annual total, and the ratio between years. It is never used for the level | S5, S6 |
| Control of the monthly fraction | The regression of `R` on monthly precipitation | S7 |

- Daily precipitation comes from the platform adapter (blueprint section 8: IMERG precipitation).
- The exponent and the threshold of the daily index are parameters: `params/`, with their citation, before anything is computed.
- Known limit, from S8: erosivity computed from satellite precipitation needs the 30-minute data; that is why the daily index is used only in relative terms.

`DECIDED` for the first release (decided by the lead developer on 14 November 2026, [issue #77, D69](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6884997091), and USER-G of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md)), while S5 and S6 stay behind paywalls and are requested:

| Part | Method of the first release | Source |
|---|---|---|
| Fraction of the annual erosivity in each month | The monthly erosivity of a published climatology at the point: the fraction of a month is that month's value over the sum of the twelve | GloREDa (Panagos et al. 2023, Zenodo record 8036998), named by D69 |
| Variation between years | **Deferred** (USER-G): the same twelve fractions hold for every agricultural year. The climatology gives none; this is declared as a limit of the method (D69) | — |

- `OPEN` under D69: which licence governs the climatology (one distributor's copy states conditions that contradict the licence of the Zenodo record). The team confirms it before any value is committed; until then the monthly values stay `NOT_AVAILABLE` and `C` is a single declared value.
- The form is built in `engine/erosion/r_factor/climatology.py` (PROPOSED); it holds no value of the climatology.
- `OPEN`: how the mean annual level of S4 reaches the field. D68 of issue #77 and a later instruction of the lead developer that keeps the choice pending are being reconciled; see "Pending" in [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md).
- Finding of the AI pre-check (F16, not a decision): S4 prints regressions of the **annual** `R` only and gives no monthly distribution in pages 92 to 93, so the control of the third row of the first table has no published monthly form among the pages read (`engine/erosion/r_factor/README.md`, OPEN 7).

### M1.3 Factor K and soil-loss tolerance

The question was: which source the event repository may use.

- `DECIDED` for the source of `K` (decided by the lead developer on 14 November 2026, issue #77, D10; acceptance by a science reviewer pending): **the open dataset of source S9**.
- `OPEN` for the soil-loss tolerance: which source the event repository may use. As far as the planning notes record, the dataset of S9 carries `K` and not the tolerance (issue #77).

What the planning notes say, unchanged:

- The planning notes name two: the official values by soil group of the national soil map, and the open dataset of S9.
- The licence of the official tables for an open repository is not established. S9 is published as open data.
- The soil identity is confirmed by the user: one soil group can hold several soils, and `K`, the tolerance and the available water change together with it.
- `K` is not computed from a global soil grid with a nomograph as the main value.

For the lead developer and the science reviewers: which source for the soil-loss tolerance, and under which licence. Issue #77 names the source of `K` and names no licence for it.

- Finding of the AI pre-check (not a decision): the only mention found, "7 t ha-1" in Carrasco-Letelier and Beretta-Blanco (2017), is secondary, cites no primary norm and is **not adopted** as the tolerance of the soil.
- USER-Q of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md) admits a rotation on erosion only against a **verified** tolerance; without one, erosion admissibility is reported "not evaluated" (D60).

### M1.4 Factor LS

The slope steepness and slope length equations of RUSLE: steepness with two branches according to the slope, and length with an exponent that depends on the ratio of rill to interrill erosion. Sources: S2, S3.

- Every coefficient of these equations is a parameter in `params/`.
- Steepness and length are proposed from the terrain data and **confirmed or corrected by the user**. The interface shows how the result moves with both.

`DECIDED` as the target (USER-I and USER-L of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md), 14 November 2026): the classical daily route of RUSLE2 (S1), built in stages starting with **dynamic LS**, explicitly partial while other components stay simplified. Dynamic LS is not built: `engine/erosion/ls.py` holds the static forms above. D66 plans the check of the LS rows of S2 for the demonstration point first; read together, the static LS stands in for the demonstration as a declared partial stage.

### M1.5 Factor C by period

`C` for a rotation is the sum, over the months of the rotation, of the fraction of annual erosivity of the month (M1.2) times the soil-loss ratio of the month, divided by the number of years of the rotation. Source: S1.

The soil-loss ratio of a period comes from the sub-factor equations of RUSLE (canopy, surface cover, and the other sub-factors of S1). Blueprint section 8 places this unit in Block 2.

`DECIDED` for the sub-factors (decided by the lead developer on 14 November 2026, [issue #77, D45](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346); acceptance by a science reviewer pending). Before this decision they were `OPEN` here.

- Two sub-factors are used: **canopy cover**, and **surface residue cover, with residue decay by residue type**. Both come from the equations of source S1.
- The other sub-factors (roughness, soil biomass, consolidation, prior land use) are set to one. This is declared as a limit of the method. The text on the limits of the method is the separate unit named in M1.1.
- Every coefficient of these equations is to be a parameter in `params/`, transcribed and checked under decision D34 of issue #77. The decision names no equation, coefficient or value, and this file names none.

`OPEN`, for the lead developer and the science reviewers, not answered by D45:

- The source of each input (residue cover at sowing, canopy cover and fall height by stage, the residue type of each crop). Whether the erosion engine takes residue cover from the residue ledger is Q12 of `contracts/ENTRYPOINTS.md`.
- The level of residue cover at sowing. The share of the soil covered by residue at sowing is the most sensitive input: it is explicit, and the result is shown for more than one level. The generic levels proposed for it were withdrawn (USER-AA of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md)): local published evidence is needed first.

Findings of the AI pre-check against S1 (not decisions; findings 1 to 3 of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md)): S1 uses the effective canopy cover; its ground-cover sub-factor has a roughness term and takes the cover in percent; it multiplies seven daily sub-factors and integrates daily; and it modifies residue decay by daily moisture and temperature. The forms built in `engine/erosion/c_factor/` are a partial reading of S1. Which simplifications are declared as limits is for the lead developer (questions P16 and P17 of the validation package; `engine/erosion/c_factor/README.md` OPEN 1 to 3, 16, 17).

### M1.6 Factor P

`P` is one by default under no-till. It changes only when the user declares a support practice.

### M1.7 Units

The engine works in the International System and converts at the edge. The unit string of the result is fixed by convention C1.2.

`DECIDED` for the unit strings of `R` and `K` (decided by the lead developer on 14 November 2026, issue #77, D11; acceptance by a science reviewer pending). Before this decision they were `OPEN` here, "until a person writes them in the parameter catalogue with their source". The decision fixes the two strings; it puts nothing in the parameter catalogue.

- International System: `R` in `MJ mm ha-1 h-1 yr-1`, `K` in `t ha h ha-1 MJ-1 mm-1`.
- With `LS`, `C` and `P` without unit, the result is in `t ha-1 yr-1` (convention C1.2).
- Conversion happens at the edge.

`OPEN`, for a science reviewer: **are the published values of `R` and `K` in these units?** A science reviewer confirms it against the sources before any value is transcribed.

## M2 Water deficit exposure: `engine/water/`

Status of the whole section: `DECIDED` (decided by the lead developer on 14 November 2026, [issue #77, D44](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882268346)), except the points marked `OPEN`: the citation of S10, the source of the Curve Number method, and where the result says that the fallback of M2.3 was used. Acceptance by a science reviewer is pending.

This section names the method of the reference evapotranspiration and of the daily water balance. The indicator computed from the balance, and its descriptive measures, are defined in C1.4 of `contracts/CONVENTIONS.md`, not here. D44 names no parameter value, coefficient or expected result: each comes from a source, transcribed and checked under decision D34 of issue #77, into `params/`.

### M2.1 Reference evapotranspiration

The daily **FAO-56 Penman-Monteith** method. Source: S10.

It is checked against the worked example of the manual: test H2 of `docs/VALIDATION.md`, whose definition, expected value and tolerance are still `OPEN` there.

- USER-F of [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md): the comparison is at the published precision, and the internal daily state is never rounded. Which printed figure and which tolerance are still for the lead developer; the rounding oddities of the worked example do not supply a tolerance (finding 9).
- Findings of the AI pre-check (not decisions): the list of symbols of Eq. 39 bounds Rs/Rso at 1, and chapter 3 bounds the wind speed used in Eq. 6; the code applies neither (finding 4, question P21). The image of Eq. 9 prints a minus sign that the text, Box 11 and Example 18 contradict; the code takes the mean and keeps it (finding 5).

### M2.2 Daily water balance

As D44 states it:

- **Daily and continuous** over the whole rotation and all years, **never reset** between crops or years.
- **A single column per field, rain-fed, no water table, no lateral exchange.**
- Actual evapotranspiration: `ETa = (Ks · Kcb + Ke) · ET0`, the dual crop coefficient of FAO-56, chapters 7 and 8 (S10).
- Water stress `Ks` from the depletion, with the readily available fraction of the crop.
- Soil evaporation `Ke` from the daily balance of the surface layer of FAO-56 (S10).
- Runoff by the **Curve Number**.
- Daily mass closure: `ΔS = P − Q − E − T − D`.

D44 does not spell out the symbols of the closure. `engine/water/balance/README.md` (rule R1) reads them as the change of storage in the column over the day (`ΔS`), precipitation (`P`), runoff (`Q`), evaporation (`E`), transpiration (`T`) and drainage (`D`).

`OPEN`, for the lead developer and the science reviewers: **the source of the Curve Number method.** D44 names the method and no source, and S10 is not cited for it. Finding of the AI pre-check (not a decision; finding 8): the forms built match the National Engineering Handbook Part 630, chapter 10 (NRCS 2004); its 2025 edition says that using the method as a loss in continuous simulation is outside its intended use, so admitting it in this continuous balance would be a declared adaptation.

`DECIDED` for the exploratory water case (lead developer, 14 November 2026; [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md), section Water). Each value comes from its source under D34; none is written here:

- **Soil:** the full hydraulic profile of Capurro (2017) at the La Estanzuela station, documented to 0.90 m (USER-AE). The station's average available-water reference of the national agroclimate service is a separate reference, not the principal profile. Neither is identified as the soil of another experiment of the case.
- **Surface layer:** evaporation-layer depth 0.10 m, and 0.15 m in sensitivity (USER-AG); readily evaporable water explored at 8, 9, 10, 11 and 12 mm, the 10 mm reference being an assumption, not a calibration (USER-AL, provisional). Water evaporable below the wilting point stays in the same storage and never reaches the roots (USER-AF).
- **Crops:** basal crop coefficients of FAO-56 Table 17 and depletion fractions of Table 22 as a transferred reference, with climatic adjustment and sensitivity (USER-AR); provisional crop-specific root growth of FAO-56 Annex 8 (USER-AO), and for soybean a provisional local curve inferred from Capurro (2016) (USER-AK). No local calibration is claimed.
- **Initial state:** depletion zero and depletion equal to TAW, the same for every rotation (USER-P).
- **Agricultural year of the demonstration:** 1 July to 30 June (USER-K), the start month of the case under C5.4.
- Finding of the AI pre-check (not a decision; finding 6): FAO-56 chapter 7, Eq. 77, carries the transpiration from the surface layer (Tew), which the built step leaves out; the manual allows leaving it out in some cases, and the scope of that simplification is for the lead developer.

### M2.3 Fallback to the single crop coefficient

If the crop parameters of the dual coefficient or the values of the surface layer do not arrive, the engine falls back to the **single crop coefficient and one layer, and says so in the result** (D44).

`OPEN`, for the lead developer, who owns the results contract, and the interface developer, who shows it: **where the result says that the fallback was used.** No field of `contracts/results/models.py` is named for it.

### M2.4 What is built today

No value of the water axis is reported today: EP3 chains the four parts day by day, but convention C1.4 is incomplete, so every year is missing with its reason (D61), and `params/records/` holds no parameter.

| Part | Where | State |
|---|---|---|
| Reference evapotranspiration (M2.1) | `engine/water/et0/`, pull request #121 | The forms of the equations are written and PROPOSED: a builder session wrote them without the method's text, and a person checks each one against its equation before any number of the folder is used (OPEN 2 of its README). Every constant is an argument the caller supplies, with no default. The test of H2 is written and skipped. As its README says, it waits for the inputs, intermediate results and final value of the worked example, transcribed and checked under D34; the tolerance and printed precision, set by the science reviewers; the constants; and a person's check of the forms. The README lists what else is still `OPEN` |
| Daily water balance (M2.2) | `engine/water/balance/`, pull request #116 | One layer, as in the fallback of M2.3. Every coefficient is an argument with no default |
| Curve Number runoff (M2.2) | `engine/water/runoff/`, pull request #150 | The forms of finding 8; its source is still `OPEN` |
| Surface-layer evaporation `Ke` (M2.2) | `engine/water/evaporation/`, pull request #151 | The daily balance of the surface layer; Tew left out (finding 6) |
| Entry point EP3 of `contracts/ENTRYPOINTS.md` | `engine/water/exposure.py`, pull requests #135 and #165 | Chains the reference evapotranspiration, runoff, `Ke` and the balance day by day with `parameters` (D44, D46, D56); crop parameters are one value per crop, with no curve by stage (`engine/water/EXPOSURE.md`, OPEN 4). It reports no number while C1.4 is incomplete (D61) |

## Sources

| Id | Reference | Read |
|---|---|---|
| S1 | USDA Agricultural Research Service (2013). *Science Documentation: Revised Universal Soil Loss Equation Version 2 (RUSLE2)*. Washington, D.C. https://www.ars.usda.gov/ARSUserFiles/60600505/RUSLE/RUSLE2_Science_Doc.pdf | read |
| S2 | Renard, K.G., Foster, G.R., Weesies, G.A., McCool, D.K., Yoder, D.C. (1997). *Predicting Soil Erosion by Water: A Guide to Conservation Planning with the Revised Universal Soil Loss Equation (RUSLE)*. USDA Agriculture Handbook 703 | located (scanned copy, text not read) |
| S3 | McCool, D.K., et al. (1989). *Transactions of the ASAE* 32:1571. https://doi.org/10.13031/2013.31192 | located |
| S4 | Pérez Bidegain, M., Piaggio, J.M., Baethgen, W., García Préchac, F. (2017). Actualización del factor erosividad de la lluvia en Uruguay. *Agrociencia Uruguay* 21(2):91–99. https://doi.org/10.31285/agro.21.2.11 (English: https://doi.org/10.31285/agro.26.1074) | read |
| S5 | Richardson, C.W., et al. (1983). *Transactions of the ASAE* 26:153. https://doi.org/10.13031/2013.33893 | read (abstract at most) |
| S6 | Yu, B., Rosewell, C.J. (1996). *Australian Journal of Soil Research* 34:139. https://doi.org/10.1071/SR9960139 | read (abstract at most) |
| S7 | Renard, K.G., Freimund, J.R. (1994). Using monthly precipitation data to estimate the R-factor in the revised USLE. *Journal of Hydrology* 157:287–306. https://doi.org/10.1016/0022-1694(94)90110-4 | fragments; its equation was taken from S4 |
| S8 | Emberson, R. (2023). Dynamic rainfall erosivity estimates derived from IMERG data. *Hydrology and Earth System Sciences* 27:3547–3563. https://doi.org/10.5194/hess-27-3547-2023 | read |
| S9 | Beretta-Blanco, A., Carrasco-Letelier, L. (2017). USLE/RUSLE K-factors allocated through a linear mixed model for Uruguayan soils. *Ciencia e Investigación Agraria* 44(1):100–112. https://doi.org/10.7764/rcia.v44i1.1622 | read |
| S10 | FAO-56. Reference: `OPEN`, `CITATION NEEDED`: a person composes it, as item 17 of the OPEN list of `engine/water/et0/README.md` asks. Issue #13 records how the contents page identifies the document: title line "Crop evapotranspiration - Guidelines for computing crop water requirements - FAO Irrigation and drainage paper 56"; authors R.G. Allen, L.S. Pereira, D. Raes, M. Smith; FAO, Rome, 1998; series mark M-56; ISBN 92-5-104219-5. https://www.fao.org/4/X0490E/x0490e00.htm. Locators used in this file: chapter 4, Example 18, the daily worked example that issue #13 locates for H2 (the definition of H2 is `OPEN` in `docs/VALIDATION.md`, so which example H2 uses is for the science reviewers); chapters 7 and 8, the dual crop coefficient, as D44 names them | located (issue #13 read the online pages on 14 November 2026; the session that wrote this row did not read the source) |

For the science reviewers: check every row not marked `read` against the source before a parameter is transcribed from it, and complete the author lists and titles of S3, S5 and S6.

`OPEN` for S10, what a person still has to do under decision D34 of issue #77, for the lead developer and the science reviewers:

- Compose the full citation of S10, and its row in `ATTRIBUTIONS.md`.
- Confirm in the source that chapters 7 and 8 are the chapters of the dual crop coefficient.
- Confirm that H2 uses Example 18 of chapter 4.
- Decide which terms govern the reuse of the text: the contents page says "All rights reserved", and the FAO site-wide terms allow some reuse with acknowledgement (issue #13).

## Not in this file yet

`OPEN`, for the lead developer:

- The methods of the residue ledger and of the two carbon models. The lead developer's carbon decisions of 14 November 2026 (AMG-A and RothC mandatory for an integral comparison, AMG-M experimental, standard RothC as reference with a separate local evaluation, the variant with monthly FAO-56 ET0 as demand identified as an adaptation) are listed in [SCIENCE_DECISIONS.md](SCIENCE_DECISIONS.md), section Carbon.
- The correction of soil loss for soil water, if any is applied.
- The name of the official program that a person runs for the comparison of blueprint section 8.
