# Field Shift Rotation Twin

Open-source prototype built during the NASA Space Apps Challenge 2026, for the challenge "Field Shift: Adapting Farms with NASA Data".

The tool is built to compare crop rotations for a field against the observed climate record. For one rotation on one field, the deployed service repeats the rotation over the agricultural years of the daily climate record of the point, read from NASA POWER, takes soil and slope from a declared file, and reports three indicators: soil loss, exposure to water deficit and the trend of soil carbon. A value that cannot be computed is reported as missing with its reason, never as zero. Today soil loss is a number for every rotation, water-deficit exposure only for a rotation whose crops all have their water records in the catalogue (at this commit, soybean), and the soil-carbon trend for none. It carries no uncertainty range, and at the demonstration point it overestimates the loss measured on local runoff plots about 6 times (decision D148 of issue #77). The comparison between rotations is a separate decision layer: when the data cannot separate two rotations, it names the pair as not separated, with the reason, and lists what to measure first. The service has a route that runs that layer on the output of two rotations (PROPOSED, D198), and the decision section of the interface shows the document it returns for the two rotations of the demonstration.

## Status

This section describes `main` at commit `12f9008` (15 November 2026). The decisions cited as `D` and a number, such as D148, are in [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77). A code in square brackets, such as [H2] or [D1], is an entry of [docs/VALIDATION.md](docs/VALIDATION.md): an entry such as [D1] is a check of the decision layer, not decision D1 of the issue. The methods are in [docs/METHODS.md](docs/METHODS.md).

Three terms used below. An agricultural year is twelve consecutive calendar months beginning at the start month of the case; in the demonstration the start month is 7, July. `C` is the cover and management factor of the soil-loss equation: the declared `C` is one value, declared by the lead developer from a published measurement of continuous no-till cropping in Uruguay (D125), and the computed `C` is worked out for each agricultural year from canopy cover and residue cover. EP1 is the entry point of the soil-loss engine, the one function through which the service calls it (`contracts/ENTRYPOINTS.md`).

**Soil loss** (`engine/erosion/`). The engine computes the annual soil loss of the Revised Universal Soil Loss Equation, `A = R · K · LS · C · P`, for each agricultural year that the climate record covers whole. Its parameters are records of `params/records/`, each checked or declared by the lead developer and signed. For the demonstration point, La Estanzuela, with the single declared `C` of decision D125, the figure is 2.365 t ha-1 yr-1, "based on a Uruguayan no-till measurement; overestimates about 6 times the loss measured on the La Estanzuela plots in 2017–2019 (Grahmann et al. 2022)" (the label of decision D148). The comparison with the measured plots and its result are in [docs/VALIDATION.md](docs/VALIDATION.md#ep1-plausibility-against-the-la-estanzuela-runoff-plots-20172019), entry "EP1: plausibility against the La Estanzuela runoff plots (2017–2019)". Decision D213 keeps this single declared `C` for the release: no published source read gives a `C` for both rotations of the demonstration, so there is no `C` per rotation, and soil loss stays the same for every rotation (D158).

The engine also holds a route that computes `C` from canopy cover and residue cover. That route did not pass the same comparison, and D148 withdrew its values from the demonstration. The withdrawal is applied in the catalogue the service loads (D158, D164): the records that only the computed `C` reads are kept, signed and unchanged, in `params/withdrawn/`, which the service does not load. The service therefore gives the declared-`C` figure for every rotation. The interface does not show a value whose source says computed `C`.

**Water-deficit exposure** (`engine/water/`). Built: the daily FAO-56 Penman-Monteith reference evapotranspiration, runoff by the Curve Number, evaporation from the surface layer and a one-layer daily water balance, chained day by day over the whole record. Since #296 the engine reports the indicator that decision D157 defines, a ratio over the whole crop cycle. Since #417 the catalogue holds the 43 water records of D200 to D209 that the lead developer checked and signed (D34, D66), beside the FAO-56 constants and the basal crop coefficients: those of the site (runoff on a day with no crop, the surface layer, the soil column, the starting state) and those of soybean. Wheat, maize and alfalfa have only their basal crop coefficients. Run in process at this commit, with the catalogue the service loads, the demonstration soil file and a placeholder climate repeated over the record of D29 (no call to the climate service), EP3 gives a value for the rotation of soybean with winter fallow in every agricultural year that the record covers whole (2001 to 2023), and `NO_COVERAGE` for the two years it covers only in part. For the rotation of wheat, second-crop soybean and maize it gives no value in either phase: every covered year is `MISSING_INPUT`, naming the records of wheat and maize that the catalogue does not hold (crop height, curve number, root depth, depletion fraction, stage lengths and residue cover). The numbers of that run come from a placeholder climate: they are not those of the service and none is given here. Since #344 the engine follows decisions D214 to D217, which settle what a water value carries once one is computed: its reason when the water demanded is not above zero, its provenance label and the facts its source states, the reason code of its missing range, and one value per agricultural year over all its crops. Since #301 the surface layer keeps its depletion when a fallow starts with the layer drier than its limit under residue, instead of making the rest of the record missing (D185).

**Soil-carbon trend** (`engine/residues/`, `engine/amg/`, `engine/rothc/`). Built: the residue ledger, which gives the annual carbon inputs and, since #306, the aboveground and belowground origins of each crop (D194), and the two carbon models: AMG, in the form AMGv2 that D192 names (#305; each form is still to be compared with its source by a person), and RothC. Since #282 the service calls both carbon models on the same forcing. No value is reported: every carbon row of the response is missing. The AMG rows are `MISSING_INPUT`: the soil file carries no starting soil carbon and none of the soil properties the model reads (D120, D121), and the constants of the model have no record in the catalogue. The RothC rows are `MISSING_INPUT` too: the soil file carries no starting soil carbon, from which the engine derives its five pools (D218). Decisions D178 to D184 decide the pH, the clay content, the carbonate content, the starting soil carbon and the initial stable fraction of AMG for the demonstration point, and D181 settles the condition of D119 for the annual water balance. None of these values is on `main` at this commit, and each still needs one person to check it at its page and sign it (D34, D66). Decisions D218 to D224 settle what RothC still lacks to give a number at the demonstration point: how its five pools are initialised, its monthly climate, carbon inputs and soil cover, the bare-soil rule it does not apply, and the label of a shown value. All but one are built: the initialisation of the pools, the equilibrium, the bare-soil rule and the label in the engine (#339; D218, D219, D223, D224), and the monthly climate and carbon inputs in the forcing (#334, #350; D220, D221), the potential evapotranspiration of the month summed from the public daily reference evapotranspiration of EP3 (#396, #412, D256). The monthly soil cover of D222 is not built at this commit, and RothC has no record in the catalogue: its constants and the records those decisions add wait for a person's check and signature. RothC gives no number.

**Decision layer** (`decision/`, `demo/`). Built: pure functions for the D entries of `docs/VALIDATION.md`: the count of years within a declared limit, the paired differences between two rotations with their ranges, the state of a pair, dominance, the tipping point of an uncertain input, the measurement priority and the measurement input. `demo/` runs an approved matrix of example rotations through them. Since #309 the functions follow the readings of the decision rule that D165 to D176 settled. The trivial comparator of the decision, entry D0, is built (#298): it orders the rotations by the mean of each indicator and reports whether that order equals the order of the full decision. The service has a route, `POST /api/decisions/run` (#295, D198, PROPOSED), that runs two rotations of one field through the engines and returns the decision output of the pair; without the inputs it needs, it returns no decision and says which input is missing. Since #363 the decision section of the interface sends the two rotations of D128 to that route for the example field and shows the document it returns; when the route answers without a decision, or fails, it shows the reason and then the hand-written example of the decision output contract, under its example banner. Run in process with the demonstration soil file and a placeholder climate repeated over the record, the route answers for those two rotations a pair that is "Not robust across scenarios", with no preferred rotation and nothing to measure first. Since #341 `demo/` writes one saved case of the example case under the PROPOSED contract (#297, D177), with every carbon balance missing; the interface does not read it yet.

**Economics** (`economics/`, `contracts/economic_facts/`). PROPOSED (#392): the contract of the economic facts a producer declares, and `economics/`, whose one public function gives the simple margin per hectare and agricultural year of one rotation in each kind of year and on the average of the record, from those declared facts only. It holds no parameter value and no price forecast. Neither the service nor the interface calls it at this commit.

**Service and interface** (`api/`, `adapters/`, `web/`). The service has two product routes: `POST /api/rotations/run`, one rotation for one field, and `POST /api/decisions/run`, two rotations of one field and the decision output of the pair (PROPOSED). Every part that is absent comes back typed, with a reason code. The interface shows a synthetic example case, labelled as example data, and runs the example rotation through the service.

**Validation** ([docs/VALIDATION.md](docs/VALIDATION.md)).

- Three runs are recorded, each the suite without `ci/`, in `validation/runs/` with one result in `validation/results/` for each test that is the check of a code: at commit `3ced36f` (#302), 40 results, 37 passed and 3 not evaluated; at commit `b831602` (#345), 76 results, 73 passed and 3 not evaluated; at commit `9410a92` (#405), 498 results, 496 passed, 0 failed and 2 not evaluated ([H1] and [H8], whose named tests skip). Each record also states what did not pass (the plot check below).
- Run and pass:
  - [H2], the reference evapotranspiration against Example 18 of FAO-56, step by step, on a signed fixture. The tolerance of two steps was widened after the results of a run were seen (D138).
  - [E3], the slope length and steepness equations against Tables 4-2 and 4-5 of USDA Agriculture Handbook 703, on a signed fixture (D124).
  - The tests of the decision functions on tables written by hand, for the entries [D1] to [D7], [D10] and [D12]. In the second and third recorded runs (#345, #405) they pass on the functions brought in line with D165 to D176 (#309).
  - The order of the rotations by soil loss against an expected order, [E2] (#358, D225), on tables written by hand; the expected order on real data and its source are OPEN.
  - The three trivial comparators, on example data written by hand: of the decision, [D0] (#298); of soil loss, [E0], the erosivity-weighted share of the year without a living crop (#320, D211); of water-deficit exposure, [H0], precipitation over demanded transpiration on the days with a living crop (#321, D212). Each states whether its order of the rotations equals the order of the full method; none runs on the output of the service.
  - One month of RothC against the worked example of its model description. The designer of the case widened the tolerance of the comparison after printed pools were found to differ from the computation. The source of this is `engine/rothc/README.md`, section "The reference case of section 2.2".
  - The examples of every contract against their models, and a chain test from the rotation example to the route.
- Skipped, each waiting for something a person supplies and a person checks. The three tests of AMG against published examples say, as they skip, that they wait for a person to choose the source of AMG and to transcribe from it; D192 has since named the source, and the transcription and its check by a person are still to come. The test that names [H8] is skipped on purpose: D227 defines [H8] as a list of invariants that the tests its entry names check one by one, and that test has no criterion of its own. The others wait for a worked example or a reference case: the sub-factors of the computed `C`; the daily erosivity index and the regression for `R`; the reference case of the water balance [H1]; the evaporation of the surface layer; the Curve Number runoff. Each skipped test names what it waits for.
- Not passed: the computed `C` against the La Estanzuela runoff plots (D148). No tolerance was fixed before that run, and none has been chosen since.
- Context, not checks (#328): beside the plot check, `docs/VALIDATION.md` records the soil loss measured with ¹³⁷Cs in the long-term rotation experiment of La Estanzuela (averages over about six decades, past tillage included, on other plots than the demonstration point), and the carbon inputs of soybean and corn measured at another Uruguayan site, as a reference for the values the residue ledger will give once its records are signed. Neither is a check, a tolerance or an expected value, and no value of an engine is compared with them.
- Exploratory, not a check (#366, D234): AMG against the soil carbon measured in the long-term experiment LEELP1 of La Estanzuela, with the AMGv2 defaults, which are not signed for this project. The results were seen before D234 was taken, so the entry has no tolerance and no pass rule, and it is not a validation of the project.
- Every entry of `docs/VALIDATION.md` now has a definition or a status with its reason (#358, #365, #367, #376). Defined and run, by the tests their entries name: [E8], [E9], [H7] and [H8] (D226, D227), beside those above. Defined and not run: [H10], the runoff comparator (D230; its fixture and a run of EP3 on the plots do not exist), and [H5] (D253, no pass rule). [E7] is the plot check above, given its code by D252 after the result. [H1] waits for its signed fixture. [E1a] and [E1b] are not evaluated in this release (D254).
- No entry records an acceptance by a science reviewer.

## Where to see it

- The interface: https://gbarbozamar.github.io/field-shift-rotation-twin/
- The service: the page of its routes is https://api-production-86e398f8.up.railway.app/docs and its liveness route is https://api-production-86e398f8.up.railway.app/health. The address without a path has no route.

The service is a public test instance, without login. Both are published again on every push to `main`, so what they answer follows `main`. The two addresses are written in `.github/workflows/pages.yml` and `web/README.md`.

## How to run it

The commands below are those of [CLAUDE.md](CLAUDE.md) and of `.github/workflows/ci.yml`. Those two files and [api/README.md](api/README.md) say what each one needs. Run them from the repository root. [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) (#303) takes a clean clone through them step by step, with the output each one gave at the commit it names.

```bash
uv sync                                  # install, including the dev group
uv run pytest                            # all tests
uv run uvicorn api.main:app --reload     # backend on http://localhost:8000
docker compose watch                     # the whole app: backend on :8000 and frontend on :5173/field-shift-rotation-twin/
```

The backend started with `uvicorn` has no climate source and no soil file configured, and answers with typed absences. The stack started with `docker compose watch` needs the Docker daemon running, not only the `docker` command installed, and has the real climate source switched on, so a rotation request to it calls that source. To start it with the climate source off:

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
- The computed `C` did not pass the plot check. Its code and its signed records stay in the repository, outside the catalogue the service loads.
- Soil loss has no uncertainty range, and `R` is the same in every agricultural year: its variation between years is deferred (D69).
- No soil-loss tolerance is in the catalogue, so a rotation is not judged against one. D213 names 7 t ha-1 yr-1 for the soil of the La Estanzuela plots, from a published source; its record is drafted, unsigned and not on `main`, and until a person checks and signs it the admissibility of soil loss stays "not evaluated" (D60).
- Water-deficit exposure has a value only for a rotation whose crops all have their water records in the catalogue: at this commit soybean, so the rotation of wheat, second-crop soybean and maize has none (the reasons are in the section "Status"). The soil-carbon trend has no value: the soil values of the carbon models are decided (D178 to D184) and wait for a person to check and sign them (D34, D66).
- The three trivial comparators (D0, E0, H0) run only on example data written by hand. With soil loss the same for every rotation, the report of E0 can only state that the full method gives no order (D211).
- Soil and slope come from one declared file, served as example data for any field (D38). The file of the demonstration point is `data/demo/la_estanzuela_soil_slope.json`. The adapter for soil tables by soil group is built, and no tables have been supplied to it. No elevation model is decided, so it gives no slope.
- A field is one point. The interface requests the centre of the bounding box of a synthetic example field; how the point is chosen for a field is not decided.
- The decision route of the service and the decision section that shows its document are PROPOSED (D198, #363). Soil loss is the same for every rotation (D158), water has a value for only one of the two rotations of the demonstration, and carbon has none, so no cell of that pair carries a difference: in the in-process run above, none of its 50 water cells does. The saved case has a PROPOSED contract (D177); `demo/` writes one for the example case, and the interface does not read it.
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
