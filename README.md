# Field Shift Rotation Twin

Open-source prototype built during the NASA Space Apps Challenge 2026, for the challenge "Field Shift: Adapting Farms with NASA Data".

The tool is built to compare crop rotations for a field against the observed climate record. For one rotation on one field, the deployed service repeats the rotation over the agricultural years of the daily climate record of the point, read from NASA POWER, takes soil and slope from a declared file, and reports three indicators: soil loss, exposure to water deficit and the trend of soil carbon. A value that cannot be computed is reported as missing with its reason, never as zero. Today only soil loss is a number. It carries no uncertainty range, and at the demonstration point it overestimates the loss measured on local runoff plots about 6 times (decision D148 of issue #77). The comparison between rotations is a separate decision layer: when the data cannot separate two rotations, it names the pair as not separated, with the reason, and lists what to measure first. That layer runs today on tables written by hand and on example data, not on the output of the service.

## Status

This section describes `main` at commit `6eeb79b` (15 November 2026). The decisions cited as `D` and a number, such as D148, are in [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77). A code in square brackets, such as [H2] or [D1], is an entry of [docs/VALIDATION.md](docs/VALIDATION.md): an entry such as [D1] is a check of the decision layer, not decision D1 of the issue. The methods are in [docs/METHODS.md](docs/METHODS.md).

Three terms used below. An agricultural year is twelve consecutive calendar months beginning at the start month of the case; in the demonstration the start month is 7, July. `C` is the cover and management factor of the soil-loss equation: the declared `C` is one value, declared by the lead developer from a published measurement of continuous no-till cropping in Uruguay (D125), and the computed `C` is worked out for each agricultural year from canopy cover and residue cover. EP1 is the entry point of the soil-loss engine, the one function through which the service calls it (`contracts/ENTRYPOINTS.md`).

**Soil loss** (`engine/erosion/`). The engine computes the annual soil loss of the Revised Universal Soil Loss Equation, `A = R · K · LS · C · P`, for each agricultural year that the climate record covers whole. Its parameters are records of `params/records/`, each checked or declared by the lead developer and signed. For the demonstration point, La Estanzuela, with the single declared `C` of decision D125, the figure is 2.365 t ha-1 yr-1, "based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)" (the label of decision D148). The comparison with the measured plots and its result are in [docs/VALIDATION.md](docs/VALIDATION.md#ep1-plausibility-against-the-la-estanzuela-runoff-plots-20172019), entry "EP1: plausibility against the La Estanzuela runoff plots (2017–2019)".

The engine also holds a route that computes `C` from canopy cover and residue cover. That route did not pass the same comparison, and D148 withdrew its values from the demonstration. At this commit the service still returns them for a rotation whose crops are written `soybean`, `wheat` or `maize`. It gives the declared-`C` figure for a rotation whose crops have no record of that route, such as the example rotation. Decisions D158 and D164 say where the withdrawal is applied; that change is not on `main` at this commit. The interface does not show a value whose source says computed `C`.

**Water-deficit exposure** (`engine/water/`). Built: the daily FAO-56 Penman-Monteith reference evapotranspiration, runoff by the Curve Number, evaporation from the surface layer and a one-layer daily water balance, chained day by day over the whole record. No value is reported: every agricultural year is missing with its reason. The service gives `NO_COVERAGE` for a year the record covers only in part, and `MISSING_INPUT` for every other year, naming the parameters that have no record in the catalogue. The catalogue holds the signed FAO-56 constants of the reference evapotranspiration and the basal crop coefficients. The parameters of runoff, the surface layer, root depth, the depletion fraction, the stage lengths and the soil column have no record in the catalogue. At this commit a year computed on every day would still be missing, with `NOT_AVAILABLE`, because the convention leaves the definition of the indicator incomplete (D61). Decision D157 lets the engine report the ratio over the whole crop cycle; it is not built on `main` at this commit.

**Soil-carbon trend** (`engine/residues/`, `engine/amg/`, `engine/rothc/`). Built: the residue ledger, which gives the annual carbon inputs, and the two carbon models, AMG and RothC. No value is reported: every carbon row of the response is missing. The AMG rows are `MISSING_INPUT`: the soil file carries no starting soil carbon and none of the soil properties the model reads (D120, D121), the annual water balance does not reach the model (D119), and the constants of the model have no record in the catalogue. Decisions D178 to D184 decide the pH, the clay content, the carbonate content, the starting soil carbon and the initial stable fraction of AMG for the demonstration point, and D181 settles the condition of D119 for the annual water balance. None of these values is on `main` at this commit, and each still needs one person to check it at its page. The RothC rows are `NOT_AVAILABLE`, with the detail "the runner does not call this engine yet": the engine is in the repository and the service does not call it.

**Decision layer** (`decision/`, `demo/`). Built: pure functions for the D entries of `docs/VALIDATION.md`: the count of years within a declared limit, the paired differences between two rotations with their ranges, the state of a pair, dominance, the tipping point of an uncertain input, the measurement priority and the measurement input. `demo/` runs an approved matrix of example rotations through them. The functions do not yet follow the decision rule as decided. Decisions D165, D166, D169 and D173 settled four readings of the rule after the functions were written, and in each one `decision/` does today what the decision did not take: it lets a cell whose difference range touches zero from the side that is not worse block a robust preference (D165); it reads the cells of several scenarios together, where the state is read in each single scenario (D166); it does not split the counts of the cells of a pair by carbon model and computation (D169); and it lets all three computations of the soil-carbon trend enter the state, where only the one used to compare rotations enters (D173). `decision/` has not been brought in line. The decision screens of the interface read the hand-written example of the decision output contract, labelled as example data. The service has no route that returns a decision output, so no decision is computed from the output of the engines.

**Service and interface** (`api/`, `adapters/`, `web/`). The service has one product route, `POST /api/rotations/run`: one rotation for one field. Every part that is absent comes back typed, with a reason code. At this commit a rotation whose first crop is sown before the start month of the agricultural year answers HTTP 500, for example wheat sown on 25 May with start month 7. Decision D160 records the cause and the correction, which is not on `main` at this commit. The interface shows a synthetic example case, labelled as example data, and runs the example rotation through the service.

**Validation** ([docs/VALIDATION.md](docs/VALIDATION.md)).

- Run and pass:
  - [H2], the reference evapotranspiration against Example 18 of FAO-56, step by step, on a signed fixture. The tolerance of two steps was widened after the results of a run were seen (D138).
  - [E3], the slope length and steepness equations against Tables 4-2 and 4-5 of USDA Agriculture Handbook 703, on a signed fixture (D124).
  - The tests of the decision functions on tables written by hand, for the entries [D1] to [D7], [D10] and [D12]. They pass on the readings `decision/` holds today, which are not those of D165, D166, D169 and D173 (see "Decision layer" above), so they do not show that the functions follow the decided rule.
  - One month of RothC against the worked example of its model description. The designer of the case widened the tolerance of the comparison after printed pools were found to differ from the computation. The source of this is `engine/rothc/README.md`, section "The reference case of section 2.2".
  - The examples of every contract against their models, and a chain test from the rotation example to the route.
  - `docs/VALIDATION.md` still describes [H2] and [E3] as skipped until their fixtures are committed. Both fixtures are committed and signed, and both tests run.
- Skipped, each waiting for something a person supplies and a person checks. The tests of the yearly step, the modifiers and the monthly form of AMG wait for a person to choose the source of AMG and to transcribe from it. The numeric criteria of [H7] and [H8] wait for their definition and their tolerances. The others wait for a worked example or a reference case: the sub-factors of the computed `C`; the daily erosivity index and the regression for `R`; the reference case of the water balance [H1]; the evaporation of the surface layer; the Curve Number runoff. Each skipped test names what it waits for.
- Not passed: the computed `C` against the La Estanzuela runoff plots (D148). No tolerance was fixed before that run, and none has been chosen since.
- Not defined: the entries E0, E1a, E1b, E2, E7, E8, E9, H0, H1, H5, H7, H8 and H10.
- No entry records an acceptance by a science reviewer.

## Where to see it

- The interface: https://gbarbozamar.github.io/field-shift-rotation-twin/
- The service: the page of its routes is https://api-production-86e398f8.up.railway.app/docs and its liveness route is https://api-production-86e398f8.up.railway.app/health. The address without a path has no route.

The service is a public test instance, without login. Both are published again on every push to `main`, so what they answer follows `main`. The two addresses are written in `.github/workflows/pages.yml` and `web/README.md`.

## How to run it

The commands below are those of [CLAUDE.md](CLAUDE.md) and of `.github/workflows/ci.yml`. Those two files and [api/README.md](api/README.md) say what each one needs. Run them from the repository root.

```bash
uv sync                                  # install, including the dev group
uv run pytest                            # all tests
uv run uvicorn api.main:app --reload     # backend on http://localhost:8000
docker compose watch                     # the whole app: backend on :8000 and frontend on :5173/field-shift-rotation-twin/
```

The backend started with `uvicorn` has no climate source and no soil file configured, and answers with typed absences. The stack started with `docker compose watch` has the real climate source switched on, so a rotation request to it calls that source. To start it with the climate source off:

```bash
POWER_SETTINGS_FILE= CLIMATE_START_DATE= CLIMATE_END_DATE= docker compose up
```

The frontend alone, as CI builds it, in `web/`:

```bash
npm ci
npm test
npm run build
```

## Known limits

- The soil-loss figure overestimates the loss measured on the La Estanzuela plots about 6 times, and 2.9 to 17.0 times by year (D148; the entry of `docs/VALIDATION.md` named in "Status"). The plots are on another soil than the soil of the demonstration; the entry records that using the soil of the plots explains at most a factor of 1.3. The engine was not calibrated or tuned.
- The declared `C` is one value for every rotation, so with it soil loss does not separate the rotations of the demonstration (D158).
- The computed `C` did not pass the plot check. Its code and its signed records stay in the repository. At this commit the service still returns its values for the crops that have records.
- Soil loss has no uncertainty range, and `R` is the same in every agricultural year: its variation between years is deferred (D69).
- No soil-loss tolerance has a verified source, so a rotation is not judged against one (`docs/METHODS.md`, M1.3).
- Water-deficit exposure and the soil-carbon trend have no value. The reasons are in the section "Status". The soil values of the carbon models at the demonstration point are decided (D178 to D184) and are not on `main` at this commit.
- The RothC engine is in the repository and the service does not call it.
- Soil and slope come from one declared file, served as example data for any field (D38). The file of the demonstration point is `data/demo/la_estanzuela_soil_slope.json`. The adapter for soil tables by soil group is built, and no tables have been supplied to it. No elevation model is decided, so it gives no slope.
- A field is one point. The interface requests the centre of the bounding box of a synthetic example field; how the point is chosen for a field is not decided.
- A rotation whose first crop is sown before the start month of the agricultural year answers HTTP 500 at this commit (D160).
- The decision layer runs on tables written by hand and on example data. Its functions do not yet follow four readings of the decision rule that D165, D166, D169 and D173 settled; the section "Status" lists them. The service returns no decision output, and the saved case of the blueprint is not built.
- No method and no validation entry records an acceptance by a science reviewer. Several items of `docs/METHODS.md` are `OPEN`, among them the table of curve numbers with its source and the full citation of FAO-56.
- The methods of the residue ledger and of the two carbon models are not written in `docs/METHODS.md` yet.

## Who owns what

| Person | Lane | Builds | Folders |
|---|---|---|---|
| **Gustavo** | L0 Core | Contracts and conventions, erosion engine, validation harness, integration into `main` | `contracts/`, `params/`, `engine/erosion/`, `validation/` |
| **Gustavo** | L1 Engines | Rotation calendar, daily water balance, residue ledger, AMG soil carbon | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` |
| **Enzo** | L2a Platform: data and service | Data adapters, API, CI and deploy | `adapters/`, `api/` |
| **Martín** | L2b Platform: decision and carbon | Decision layer, RothC soil carbon, saved case | `decision/`, `engine/rothc/`, `demo/` |
| **Martín** | L3 Interface | Multi-field map, rotation editor, results, printable sheet, demo path | `web/` |
| **Adrian** and **Leonardo** | Science review, no code | Calibration, uncertainty ranges, test design, validation, plan adaptation | `docs/VALIDATION.md`; review of values |

Gustavo is the lead developer and decides what enters `main`. Enzo is the platform developer and decides structure, dependencies and deploy for everyone. Martín is the interface developer and decides what is delivered and when. One lane, one set of folders: nobody edits another lane's folder.

## How we work

New to the repository? Start with [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md): access, a clean place to work, and the first steps of each lane.

Then read [docs/DEVELOPMENT_BLUEPRINT.md](docs/DEVELOPMENT_BLUEPRINT.md) before opening a branch. In short:

- English only, in code, documents and interface text.
- Every piece lands with its acceptance test.
- Every dataset, library, table and publication is recorded in [ATTRIBUTIONS.md](ATTRIBUTIONS.md) when it is first used.
- Every AI-assisted unit is recorded in [AI_USE_LOG.md](AI_USE_LOG.md).
- No secrets, no private data, no data from real producers.

## Lanes by role

The same table by role, as the blueprint names them.

Three developers write code across four lanes (the platform lane is split in two sub-lanes), each orchestrating several AI coding sessions in parallel. A developer can own more than one lane. Two science reviewers validate and never write code.

| Lane | Owner (role) | What it builds | Folders |
|---|---|---|---|
| L0 Core | Lead developer (Gustavo) | Contracts and conventions, erosion engine, validation harness, integration into `main` | `contracts/`, `params/`, `engine/erosion/`, `validation/` |
| L1 Engines | Engines developer (Gustavo) | Rotation calendar, daily water balance, residue ledger, AMG soil carbon | `engine/calendar/`, `engine/water/`, `engine/residues/`, `engine/amg/` |
| L2a Platform: data and service | Platform developer (Enzo) | Data adapters, API, CI and deploy | `adapters/`, `api/` |
| L2b Platform: decision and carbon | Interface developer (Martín) | Decision layer, RothC soil carbon, saved case | `decision/`, `engine/rothc/`, `demo/` |
| L3 Interface | Interface developer (Martín) | Multi-field map, rotation editor, results, printable sheet, demo path | `web/` |
| Science review | Science reviewers (Adrian and Leonardo) | Calibration, uncertainty ranges, test design, validation, plan adaptation | `docs/VALIDATION.md`; review of values |

One lane, one set of folders: nobody edits another lane's folder.

## AI use

AI coding assistants are used and declared: see [AI_USE_LOG.md](AI_USE_LOG.md). The product itself does not call a language model.

## Disclaimer

This is a research prototype made for a hackathon. It is not agronomic advice and it does not replace a professional soil-use plan. It is not affiliated with, nor endorsed by, NASA or any data provider.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
