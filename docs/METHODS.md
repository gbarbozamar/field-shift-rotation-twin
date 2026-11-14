# Methods

Which method each engine implements, and where it is published. This file names methods and sources. It holds **no parameter value, no coefficient, no threshold and no expected value**: those live in the parameter catalogue (`params/`), each one transcribed from its source by a person and checked by a second person, and in the validation protocol (`docs/VALIDATION.md`).

## How to read this file

- Every item has one status: `PROPOSED`, `DECIDED` or `OPEN`, with the meaning of blueprint section 3.7 and of `contracts/CONVENTIONS.md`.
- The items below were transcribed by an AI session from the planning notes of the lead developer. They are `PROPOSED` until the lead developer approves them, and they are science class: a science reviewer still has to accept them.
- A citation here says where a method is published. The column "Read" says how far the planning notes got with the source: `read` (the abstract or the text was read), `fragments` (only fragments of the abstract), or `located` (the reference was found, nothing of it was read). A builder session never takes a number from memory of these sources: it reads it from the parameter catalogue, and returns a missing value with its reason when the catalogue does not have it.
- If an engine needs a method that is not in this file, that is an `OPEN` point for the lead developer, not something a session chooses.

## M1 Soil loss: `engine/erosion/`

Status of the whole section: `PROPOSED`.

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

### M1.3 Factor K and soil-loss tolerance

`OPEN`: which source the event repository may use.

- The planning notes name two: the official values by soil group of the national soil map, and the open dataset of S9.
- The licence of the official tables for an open repository is not established. S9 is published as open data.
- The soil identity is confirmed by the user: one soil group can hold several soils, and `K`, the tolerance and the available water change together with it.
- `K` is not computed from a global soil grid with a nomograph as the main value.

For the lead developer and the science reviewers: which source, and under which licence.

### M1.4 Factor LS

The slope steepness and slope length equations of RUSLE: steepness with two branches according to the slope, and length with an exponent that depends on the ratio of rill to interrill erosion. Sources: S2, S3.

- Every coefficient of these equations is a parameter in `params/`.
- Steepness and length are proposed from the terrain data and **confirmed or corrected by the user**. The interface shows how the result moves with both.

### M1.5 Factor C by period

`C` for a rotation is the sum, over the months of the rotation, of the fraction of annual erosivity of the month (M1.2) times the soil-loss ratio of the month, divided by the number of years of the rotation. Source: S1.

The soil-loss ratio of a period comes from the sub-factor equations of RUSLE (canopy, surface cover, and the other sub-factors of S1). Blueprint section 8 places this unit in Block 2.

`OPEN`, for the lead developer and the science reviewers: which sub-factors are used, and the source of each input (residue cover at sowing, canopy cover and fall height by stage). The share of the soil covered by residue at sowing is the most sensitive input: it is explicit, and the result is shown for more than one level.

### M1.6 Factor P

`P` is one by default under no-till. It changes only when the user declares a support practice.

### M1.7 Units

The engine works in the International System and converts at the edge. The unit string of the result is fixed by convention C1.2. The unit strings of `R` and `K` are `OPEN` until a person writes them in the parameter catalogue with their source.

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

For the science reviewers: check every row not marked `read` against the source before a parameter is transcribed from it, and complete the author lists and titles of S3, S5 and S6.

## Not in this file yet

`OPEN`, for the lead developer:

- The method of the daily water balance and of the reference evapotranspiration (blueprint section 8 names a worked FAO-56 example as the acceptance test of the second).
- The methods of the residue ledger and of the two carbon models.
- The correction of soil loss for soil water, if any is applied.
- The name of the official program that a person runs for the comparison of blueprint section 8.
