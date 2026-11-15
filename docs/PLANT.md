# "What should I plant?": the plant layer

Status: **PROPOSED** (blueprint section 3.7), unit `l2/docs-plant-layer` (brief S-023). This document describes the plant layer as the code stands at the head of its branch; it does not decide anything. Where it and the code disagree, the code and the decisions it cites hold, and this file is the one to correct. Every statement below names the file it was read from.

Decisions named with a `D` and a number are those of issue #77; the economic layer is [D235 to D251](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893552817), the link `docs/METHODS.md` uses. Codes such as C3.2 or C4.1 refer to `contracts/CONVENTIONS.md`.

## 1. What the screen answers

One field and three to five rotations of it (`PlantRequest.rotations`, `contracts/plant_answer/plant_answer.py`; the count is checked there). The route is `POST /api/plant/run` (`api/plant.py`, `run_plant`), found by name on each request by `api/app.py` (`PLANT_MODULE`, `PLANT_FUNCTION`). The screen is at hash route `#/plant` (`web/src/App.tsx`, `web/src/plant/PlantScreen.tsx`).

The rule (D245, `economics/decide.py`, `choose_rotation`): among the rotations that meet the soil-loss limit the user declared, the one with the most margin per hectare and agricultural year. Erosion is a limit, not a cost: soil loss never enters the margin. It is not the admissibility of D89 nor the robust preference of D74 (`docs/METHODS.md`). The answer is one of three (`Answer` in `economics/decide.py`):

- `chosen`: one rotation meets the limit with the most margin;
- `none_meets`: every rotation loses more soil than the limit, under the strictness chosen;
- `not_resolved`: the data cannot pick one, because a value that could change the answer is missing, or two candidates have exactly the same margin (`tied`).

The answer says what it is in the words of D245, `ANSWER_SCOPE` of `contracts/plant_answer/plant_answer.py`: the most margin within the declared limit, with water and soil carbon not part of it. The screen shows that text (`plant.answer.chosen` in `web/src/strings.ts`) in place of "Plant this rotation", and states the rule under its title (`plant.rule`).

## 2. The four questions the user can change

The request carries them in `Questions` (`contracts/plant_answer/plant_answer.py`); the screen shows them under "Four questions" (`plant.questions`).

1. **What is soybean worth?** The declared soybean price is today's price, read from the economic facts of the crops named in `soybean_crop_ids` (`economics/tipping.py`, `find_tipping_price`). The user also declares a price range (`soybean_price_range`, `DECLARED`). The answer gives the tipping price (D246): the nearest soybean price above and below today's, inside the range, at which the answer changes, and how far it is from today's in percent. It is a tipping price, never a forecast (`plant.q.price_hint`). Each margin is a straight line in the price (price times yield minus cost), so the crossings of those lines are the only places the answer can change (`economics/tipping.py`). It is not the tipping point of D3, D103 and D117 (`docs/METHODS.md`). On the screen the price is a slider over the declared range (`Questions` in `PlantScreen.tsx`): it does not send a new request; it reads the tipping points of the answer already given and says what the answer becomes past them (`plant.price.same`, `plant.price.past`).
2. **Which kind of year?** `margin_of`: the average of the record, El Nino, neutral or La Nina (`MARGINS_OF` of `economics/tipping.py`; labels `plant.kind.*`). It picks the margin the decision ranks by (`economics/plant.py`, `assemble_answer`, `margin[margin_of]`). The kind of each agricultural year comes from the NOAA CPC Oceanic Nino Index with its episode rule (D240, `kinds_of_year/classify.py`, `kinds_of_year/README.md`). The record is read only from the file `KINDS_OF_YEAR_RECORD_FILE` names, once at start-up (`api/config.py`, `_kinds_of_year_record`). Unset, every kind of year is missing `NOT_AVAILABLE` with the text `NO_RECORD` of `api/plant.py`, which says the record waits for a person's signature.
3. **And if the rain is heavier?** A declared dimensionless factor (`rain_stress_factor`) that multiplies only the rainfall erosivity record EP1 reads (`rusle_r_factor` with the empty scope), in a copy of the parameter catalogue (D244; `api/rain_stress.py`, `scale_erosivity`). The answer echoes it labelled "stress test", "not a forecast" (`STRESS_TEST_LABEL`, `_applied_detail`). It is off unless `RAIN_STRESS_TEST=on` (`api/config.py`, `_rain_stress_switched_on`; any other value stops the server with a `ConfigError`). Off, a declared factor is echoed with `applied` false and the sentence `NOT_SWITCHED_ON` of `api/plant.py`, and the engines are not rebuilt (`stressed_run`). On the screen it is a checkbox that sends the factor the example request declares, not a slider (`rainControlOf` in `PlantScreen.tsx`); without a configured service the screen shows no questions at all (section 8).
4. **How strict?** `strictness`: meet the limit on average (`on_average`) or in every kind of year in the record (`every_kind`) (`economics/limit.py`, `assess_limit`; labels `plant.strict.*`). A kind of year with no year in the record is left out of the every-kind check and listed in `kinds_not_in_record`, when the counts of the record are known (`economics/plant.py`).

## 3. What the answer holds

The answer is a `PlantAnswer` (`contracts/plant_answer/plant_answer.py`, field list in `contracts/plant_answer/README.md`). The screen renders it in `AnswerCard`, `PriceAnswer`, `OptionRows` and `Sources` of `web/src/plant/PlantScreen.tsx`.

- **The chosen rotation** (`chosen`), or, when nothing is chosen, `none_meets` or `not_resolved` with its `reason`, `detail` and any `tied` rotations.
- **Its margin**, in `USD ha-1 yr-1`, for the kind of year asked, and its margin in each kind of year (El Nino, neutral, La Nina; `plant.by_kind`). **No kind of year is called "dry"** in the code or on the screen: which kind is dry is OPEN (`contracts/plant_answer/README.md`, OPEN 3; comment above `plant.title` in `web/src/strings.ts`). There is therefore no "margin in a dry year"; the margin of each of the three kinds is shown instead.
- **Its soil loss against the limit**: the mean soil loss on the record and in each kind of year, in `t ha-1 yr-1` (`kinds_of_year/aggregate.py`, `mean_by_kind`, as called by `economics/plant.py`, `soil_loss_means`), the declared limit, and the check of the strictness used (`limit_check`). With `every_kind`, the kinds of year over the limit, not resolved, and not in the record (`plant.kinds.*`).
- **The cost of meeting the limit** (`limit_cost`, `LimitCost` of `economics/decide.py`): the margin of the best rotation that does not meet the limit minus the chosen margin, and which rotation that is; or "costs nothing" when no rotation outside the limit has more margin; or missing with its reason.
- **The tipping price** (`tipping_price`): today's price, the declared range, and for each direction the price, the rotation (or answer) that takes over, and the distance from today in percent; or missing with its reason, for example `NOT_APPLICABLE` when no price in the range changes the answer (`economics/tipping.py`).
- **The state of each option** (`options[].state`): `chosen`, `meets`, `does_not_meet` or `not_resolved`, shown in plain words (`plant.state.*`), with a strip of its crops year by year (`web/src/plant/rotationStrip.ts`) and a margin bar and a soil-loss bar with the limit line (`web/src/plant/optionBars.ts`, widths only).
- **The rain-stress echo** (`rain_stress`), **the erosivity used** (`erosivity`, only `"mean_annual"` in this release, `EROSIVITY` of `economics/plant.py`), **the kinds of year** of the record with their counts (`kinds_of_year`), **the sources** (the climate, the soil and slope, the ONI record) and **the declared limits** of this release (`declared_limits`, which always holds `PHASE_ONE_ONLY`; the screen shows each as "Limit of this release", `plant.declared_limit`).

## 4. Who brings what

| What | Who brings it | Where in the code | Label |
|---|---|---|---|
| The crops sown, with their sowing and harvest dates | The producer declares them (the rotation definitions) | `PlantRequest.rotations`, `contracts.rotation_definition` | As the rotation contract carries them |
| Yields by kind of year, prices, costs, declared margins (pasture) | The producer declares them | `contracts/economic_facts/`, `EconomicFacts` | `DECLARED`, any other label refused |
| The soil-loss limit of the field | The producer declares it; it may be missing with its reason | `PlantRequest.soil_loss_limit` | `DECLARED` |
| The soybean price range, the soybean crops | The producer declares them | `Questions.soybean_price_range`, `soybean_crop_ids` | `DECLARED` |
| The rain-stress factor | The producer declares it, or leaves it null | `Questions.rain_stress_factor` | `DECLARED` |
| The agricultural years | The climate record period of the service (`CLIMATE_START_DATE`, `CLIMATE_END_DATE`), whole agricultural years only | `api/carbon_forcing.py`, `whole_ag_years`; `api/plant.py`, `classify_years` | |
| The kind of each year | The ONI record a person configures | `kinds_of_year/classify.py` | Missing with its reason when not known |
| Soil loss per agricultural year | Computed by EP1 on phase 1 of each rotation | `api/engines.py`, `engine/erosion/` | `DERIVED` (`PROVENANCE_OF_SOIL_LOSS`, C4.6) |
| Margins, soil-loss means, limit cost, tipping prices and distances | Computed by the pure functions of `economics/` and `kinds_of_year/` | `economics/plant.py`, `_d249`, `_tipping_d249` | `DERIVED`, with `range_missing` `NOT_AVAILABLE` (D249) |
| Today's price in the answer | Copied from the declared soybean price | `economics/plant.py`, `_tipping_d249` | The declared price's own labels |

A margin carries the source "computed from the declared economic facts" (`MARGIN_SOURCE`). On a real answer (`example_data` false), every present soil-loss mean carries the label of D148 (`D148_SOIL_LOSS_LABEL` of `contracts/plant_answer/plant_answer.py`; D250); an answer that is example data carries none, because its numbers are not values of the erosion engine (`economics/plant.py`, `assemble_answer`). The plant answer has no `SIMULATED` number: water and soil carbon are not part of it (`ANSWER_SCOPE`). The route computes no number itself; every number comes from `economics/` or `kinds_of_year/`, or is copied from an engine result or from the request (module text of `api/plant.py` and `economics/plant.py`).

## 5. Example data

These files are example data; no number in them comes from a source, and none may be taken as a value:

- `contracts/economic_facts/examples/PLACEHOLDER_economic_facts.json` (`"example_data": true`, every `crop_id` carries PLACEHOLDER; `contracts/economic_facts/README.md`).
- `contracts/plant_answer/examples/PLACEHOLDER_plant_request.json` and `PLACEHOLDER_plant_answer.json` (`contracts/plant_answer/README.md` lists which of their parts are example inputs and which were computed by the real functions on them).
- `web/src/data/PLACEHOLDER_plant_request.json`: the request the screen starts from and sends, with the user's choices of strictness, kind of year and heavier rain (`plantRequestFor` in `web/src/plant/plantRoute.ts`). The screen has no editor for its facts, its limit or its prices.
- `web/src/data/PLACEHOLDER_plant_answer.json` and `PLACEHOLDER_plant_answers.json`: example answers read by `web/src/plant/plantData.ts`. Under D251 they are not shown on the screen; they stay test fixtures (`PlantNoServiceView` and `PlantScreenView` in `PlantScreen.tsx`).
- `contracts/inputs/examples/PLACEHOLDER_site_soil_slope.json`: the soil and slope that `compose.yaml` serves through `SOIL_SLOPE_EXAMPLE_FILE`.

Where the screen says so: before an answer, the line `plant.q.example_inputs` says the questions start from the example request; an answer marked `example_data` shows the banner `example.banner`; the declared limit and prices carry the mark `plant.declared` ("Declared by the user in the request (example data)"). In the answer, a number with no range computed carries the detail "PLACEHOLDER: example data, no range is computed for this number" when the answer is example data (`NO_RANGE_EXAMPLE` of `economics/plant.py`). An answer to an example request is itself example data (`check_answer_against_request`; `readPlantServiceAnswer` in `plantRoute.ts` refuses one that is not).

## 6. What it assumes, and what is left out on purpose

### Assumptions

These are the assumptions of the operator's mock of the screen, each with what the code does with it.

- **Today's prices are the producer's.** The prices are declared economic facts (`contracts/economic_facts/`), editable in the request. The screen does not yet offer a way to edit them: it sends the example request's (section 5).
- **The field is divided in as many parts as the rotation has years, so every year there is a bit of everything.** The margin per hectare and year is the sum of the margins of every crop cycle of one cycle of the rotation, divided by the number of agricultural years of that cycle (`economics/margin.py`, `compute_rotation_margin`; `economics/README.md`). Which crops fall in which year is read from the sowing dates (`economics/plant.py`, `cycle_years`).
- **A tipping price instead of a forecast.** The answer gives the soybean price at which it changes, inside the range the user declares (D246, `economics/tipping.py`); no price is predicted.
- **The climate is the real record of the point, plus a heavier-rain test, instead of synthetic years, forecasts or future climate models.** The years are the whole agricultural years of the configured climate record period, classified on the observed ONI record (section 4). Heavier rain is a declared factor on the erosivity, a stress test (D244), and on the screen a checkbox rather than a slider (section 2). No synthetic year, forecast or climate projection enters the code.
- **The tool does not predict prices and does not put a price on soil lost over the decades.** No price forecast and no money value of soil appear anywhere in `economics/` (`economics/README.md`: "no price forecast, no price on lost soil, no discounting").

### Left out on purpose

- **No price forecast** (above).
- **No price on lost soil.** Erosion is a limit, not a cost (D245).
- **No discounting.** Every margin is per hectare and agricultural year, not discounted (`economics/README.md`).
- **The year after a drought.** A dry year leaves little residue, so the soil is bare at the next rains. This is a hypothesis; nothing in the plant layer builds it.
- **No uncertainty range on the margin** (OPEN; D245, D249). `MarginResult` carries no range, so only an exact tie or a missing value makes two rotations not separable (`economics/README.md`, OPEN of `choose_rotation`); every computed number says `range_missing` `NOT_AVAILABLE`.
- **Currency: USD only** (OPEN; D239). The contract accepts `"USD"` only (`contracts/economic_facts/README.md`, OPEN 2).
- **Only phase 1 enters the answer** (D250; OPEN: every phase). Each rotation runs once and the top-level answer of the run, phase 1, is read (`api/plant.py`, step 3; `economics/plant.py`). The answer says so in `declared_limits` (`PHASE_ONE_ONLY`).
- **The declared C gives the same soil loss for every rotation and every year** (D243 note, D148, D158). With the declared cover factor, no per-rotation factor (D213) and a climatological erosivity (`erosivity` `"mean_annual"`), soil loss is the same in every year and for every rotation (`docs/METHODS.md`, D243). So the limit cannot separate rotations in this release, and a mean by kind of year shows no difference between kinds.
- **Heavier rain therefore never separates rotations.** The factor moves every rotation's soil loss in the same proportion (D244, `docs/METHODS.md`); it can move them all across the limit together, never one past another.

## 7. Decisions that changed its behaviour

All are in the comment linked at the top ([D235 to D251](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6893552817)) and are PROPOSED. `docs/METHODS.md` says that D235 to D239, D241, D242 and D247 to D251 are engineering decisions of lane L2a, taken by its lead, that the method choices were taken by the orchestrating session on the lead's proposal, and that all were taken before any real result. One line each, as `docs/METHODS.md` and the code state them:

- **D235, D238, D241, D242, D247, D248:** engineering decisions of the lane. Neither `docs/METHODS.md` nor the code at this head restates what they change; read them in the linked comment.
- **D236:** superseded (`docs/METHODS.md`).
- **D237:** about D181: it put next the unit that builds the annual water balance of AMG (pull request #371; `docs/METHODS.md`). It does not change the plant answer.
- **D239:** leaves OPEN the currency and the unit strings of the economic facts (`USD` only today).
- **D240:** the kind of an agricultural year is the episode state of the NOAA CPC ONI (ERSST v6, its episode rule applied to the values the v6 table prints), on the season the decision names, a modelling choice marked CITATION NEEDED; switching to the Relative ONI is OPEN; the record stays unsigned until a person signs it (`kinds_of_year/README.md`).
- **D243:** a mean by kind of year is the arithmetic mean of that kind's years, with an absent range `NOT_AVAILABLE` (D216) and the label `DERIVED` for soil loss; with the declared C, soil loss is the same in every year and for every rotation.
- **D244:** "heavier rain" multiplies only the erosivity record EP1 reads, in a copy of the catalogue; the screen says the erosivity, not the rain, is multiplied.
- **D245:** the answer is the most margin per hectare and year among the rotations that meet the declared soil-loss limit; the screen shows `ANSWER_SCOPE` in place of "Plant this rotation". OPEN: the margin range and any tolerance for "equal".
- **D246:** the tipping price: each margin is a straight line in the soybean price, and the answer changes only where two lines cross. OPEN: a tolerance for near-coincident crossings.
- **D249:** every number of the answer carries its provenance and its range or `range_missing`, and a margin its source (`economics/plant.py`, `_d249`; `contracts/plant_answer/README.md`).
- **D250:** only phase 1 enters the answer, and the answer says so (`PHASE_ONE_ONLY`); every real soil-loss value carries the label of D148.
- **D251:** without a configured service the screen says the service is not available and shows no example values in place of an answer; read strictly, no example answer is shown before the service answers (`web/src/strings.ts`, comments of `plant.service.*`; `PlantScreen.tsx`).

A later decision touches the kinds of year: [D258](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6895728653) (the printed values come from the record, not from a rounding rule; `kinds_of_year/README.md`).

The lane's local decisions R1 to R32 are in the body of pull request #310; they are not copied here. The code cites some of them by number (for example R10 and R25 in `api/plant.py`).

## 8. What is not built or not signed

- **The ONI record waits for a person's signature** (D240, D34, D66). It is not in the repository at this head: `kinds_of_year/records/` does not exist, and `kinds_of_year/README.md` says the record is brought in only once a person adds the printed values and signs it. (`contracts/plant_answer/README.md` still names a committed `kinds_of_year/records/oni_v6.json`, which is not present at this head.) Without it, `api/plant.py` (`classify_years`) gives every year missing `NOT_AVAILABLE`, `economics/plant.py` (`soil_loss_means`) then gives every soil-loss mean missing with that reason, every limit check is not resolved, and the answer is `not_resolved`; the margins by kind are still computed, and the average margin is missing `NOT_AVAILABLE` (the years are not classified, so they are not counted; `economics/margin.py`).
- **Neither switch is set on the deployed service** as its settings are recorded: the table "Variables of the deployed service" of `api/README.md` lists `KINDS_OF_YEAR_RECORD_FILE` unset until a person signs the record and `RAIN_STRESS_TEST` unset (off).
  `compose.yaml` sets neither (comments there). This document cannot see the host's own settings; it repeats `api/README.md`.
- **The screen when there is no answer.** With no service configured (`VITE_API_URL` unset or blank), the screen is `PlantNoServiceView`: the title, the rule, "The service is not available: no answer can be shown." (`plant.service.not_available`) and the disclaimer, and nothing else. With a service, before the first call, it shows the questions and "Ask the service" with the line `plant.service.not_asked`; while the call runs, a pending line; on an error, the panel of its code (`plant.service.error.*`). When the plant layer is not found, the route answers `200` with `answer: null` and `answer_missing` `NOT_AVAILABLE` (`api/app.py`); the screen's parser refuses a body that is not a `plant_answer` (`parsePlantAnswer` in `web/src/plant/plantData.ts`, called by `readPlantServiceAnswer`), so the screen shows the error panel `UNEXPECTED`, never an answer. It does not show the reason `answer_missing` carries.
- **Per-year erosivity** is not built (`erosivity` is `"mean_annual"` only; S-026 may add `"per_year"`, `contracts/plant_answer/README.md`, OPEN 4).
- **One start month per answer**: every rotation of a request must share `ag_year_start.month` (`PlantRequest`; OPEN 6 of `contracts/plant_answer/README.md`).
- **The route was never run against the real engines** before D235 to D251 were taken (`docs/METHODS.md`).
