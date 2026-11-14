# Validation protocol

**Skeleton, partly filled. The E and H entries are not defined yet. The D entries have their logic decided by the lead developer (14 November 2026); their OPEN items and their acceptance by a science reviewer are still pending.**

This file holds the acceptance tests that `docs/DEVELOPMENT_BLUEPRINT.md` refers to by codes in square brackets. It has one entry per code named in section 8 of the blueprint. No entry has a numeric value, threshold, numeric tolerance, expected value of the science, source or citation yet.

## Owner

The science reviewers own this file (blueprint sections 2 and 10). Under section 3.6, the values of an entry are transcribed from their source as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says, and one person checks them against the source. Section 3.5 of the blueprint states D34. Under section 10, the science reviewers check each transcribed value against its source, as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (one person checks it, stated in section 3.5 of the blueprint), and a science reviewer accepts the entry.

## Status of this skeleton

This skeleton is a proposal under blueprint section 3.7. It was laid out by an AI builder session and takes effect only when a person approves the pull request. It is a science-class change, so that pull request also needs a science reviewer.

The session supplied the layout and copied the blueprint's wording. It supplied no definition, value, tolerance, data source or citation.

Later change (#138): an AI session proposed the definitions of the D entries as logic on hand-made results tables, and the lead developer approved that logic on 14 November 2026. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation; those stay `OPEN` or `CITATION NEEDED` for the science reviewers.

Later change (`l0/validation-d74-d96`): an AI session wrote into entries D1, D2, D5 and D7 the lead developer's decisions D74 and D85 to D96 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77), each restated with a link to its comment. Where two of those decisions do not fit, or may not fit, together as written, the session chose neither: each such case is an OPEN item (K1 to K7, under entries D5 and D7) that quotes both texts for the lead developer. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation.

## How an entry gets completed

- **Section 3.5.** A threshold is never delegated to a session. A value, a unit, a range, an expected result or a citation is transcribed under decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622), which section 3.5 of the blueprint states in full: a reference, a locator, the verbatim text and the date read travel with the transcription, and one person checks it against the source.
- **Section 3.6.** The content of an entry is a science-class change: the values are transcribed under decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622), one person checks them against the source, and a science reviewer accepts them.
- **Section 3.7.** For conventions, definitions, contract field lists and the design of test cases, a builder session may write a proposal. Every proposed item is marked `PROPOSED`, and anything the builder cannot responsibly propose is marked `OPEN`, with the question a person has to answer. A proposal takes effect only when a person approves the pull request. This never covers the list in section 3.5: where a parameter value, a threshold, a range, an expected test value or a citation is needed, the builder writes `OPEN` or `CITATION NEEDED` and stops there.
- **Section 10.** The science reviewers fix thresholds and uncertainty ranges before results are seen, and check each transcribed value against its source, as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (one person checks it, stated in section 3.5 of the blueprint). Nobody approves their own values.

**A pull request that fills or changes an entry is labelled `science` and cannot merge without the approval of a science reviewer.**

## How to read an entry

Text in quotation marks is copied from section 8 of the blueprint without change, including the bracketed codes. A name of a method, a publication, a program or a data product inside a quotation is the blueprint's wording. It is not a source chosen by this file and it is not a citation.

| Field | Content | Question a person has to answer while it is open |
|---|---|---|
| What it checks | The blueprint's wording that carries the code | — |
| Lane, Block, Unit it gates | Where section 8 places the code | — |
| Class | Class of change under blueprint section 3.6; `PROPOSED` until a person confirms it | Is the proposed class right? |
| Definition | `OPEN` | What exactly is computed, compared or asserted, and on which inputs? |
| Expected value | `OPEN` | What result counts as correct? |
| Tolerance | `OPEN` | How far from the expected value may the result be and still pass? |
| Source | `CITATION NEEDED` | Which published or reference source gives the expected value? It is also recorded in `ATTRIBUTIONS.md` when first used. |
| Transcribed by | `OPEN` | Who transcribed the values from the source (D34)? |
| Checked by | `OPEN` | Which person checked the values against the source (D34)? |
| Status | `not defined` | — |

## Open questions about this file

- OPEN: the blueprint does not say what the first letter of a code stands for. Entries are grouped by that letter and the groups are not named.
- OPEN: several codes share one bracket in the blueprint. What each of those codes covers on its own is for the science reviewers to state; the entries say where this applies. Where the blueprint gives a code its own words inside a longer sentence, the entry quotes those words and gives the sentence as context.
- OPEN: which values the Status field can take after `not defined`, and who sets each.
- OPEN: whether an expected value and its citation are written in this file or kept in `validation/` with a pointer from here. The layout of `validation/` is a separate unit.
- Section 8 is the only source of the codes below. A code that section 8 does not name has no entry. If the protocol has more codes, the science reviewers add them.

## Codes in this file

- E: E0, E1a, E1b, E2, E3, E7, E8, E9
- H: H0, H1, H2, H5, H7, H8, H10
- D: D0, D1, D2, D3, D4, D5, D6, D7, D10, D12

## E codes

### E0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E1a

- What it checks (blueprint wording): "A person, not a session, runs the same rotations in the official national erosion program for the comparison [E1a]."
- Lane: OPEN. The blueprint states this code in a sentence below the table of the block, not in the row of a lane
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: OPEN. The blueprint gives no builder unit for this code; it says a person, not a session, runs it
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E1b

- What it checks (blueprint wording): "plausibility against published plot ratios [E1b]"
- Lane: L0 Core
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "plausibility against published plot ratios [E1b]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E2

- What it checks (blueprint wording): "order between systems [E2]"
- Lane: L0 Core
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "order between systems [E2]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E3

- What it checks (blueprint wording): "slope length and steepness equations [E3]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "slope length and steepness equations [E3]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E7

- What it checks (blueprint wording): "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 3 — the full decision on real data, until CP3"
- Unit it gates: "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E8

- What it checks (blueprint wording): "unit guard [E8]"
- Context (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### E9

- What it checks (blueprint wording): "invariants [E9]"
- Context (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Lane: L0 Core
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

## H codes

### H0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H1

- What it checks (blueprint wording): "public reference case [H1]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H2

- What it checks (blueprint wording): "reference evapotranspiration against a worked FAO-56 example [H2]"
- Lane: L1 Engines
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "reference evapotranspiration against a worked FAO-56 example [H2], in `engine/water/et0/`"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H5

- What it checks (blueprint wording): "regional soil-moisture contrast with SMAP [H5]"
- Lane: L1 Engines
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "regional soil-moisture contrast with SMAP [H5]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H7

- What it checks (blueprint wording): "mass closure [H7]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H8

- What it checks (blueprint wording): "invariants [H8]"
- Context (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Lane: L1 Engines
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### H10

- What it checks (blueprint wording): "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L0 Core
- Block: "Block 3 — the full decision on real data, until CP3"
- Unit it gates: "Contrast case from published runoff plots: modelled next to measured [E7, H10]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

## D codes

Section 3.6 of the blueprint lists "decision" among its examples of the class "Logic with a known answer". The class proposed in the D entries is the class of the entry's own content. Whether the gated unit is of another class is OPEN.

### D0

- What it checks (blueprint wording): "trivial comparators [E0, H0, D0]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the trivial comparator of the decision, and the statement of whether it gives the same order as the full decision. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L0 Core
- Block: "Block 4 — Sunday until CP4"
- Unit it gates: "trivial comparators [E0, H0, D0]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. The trivial comparator orders the rotations, per indicator, by the mean over agricultural years of the values, read in the direction of each row (C1.1), ignoring ranges. The test checks that (a) on the hand-made table the comparator returns the order counted by hand, and (b) the report states, per indicator, whether the comparator's order equals the order of the full decision. Pass: (a) and (b) hold. OPEN for the science reviewers: which trivial comparator is used (the mean over agricultural years is the proposal the lead developer approved; under blueprint section 10 the science reviewers read the trivial comparators).
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D1

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: counts by year against a declared limit. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data and a declared limit per indicator. For each rotation, scenario, indicator, carbon model and computation (D94 below), years evaluated is the number of agricultural-year rows that hold a value, and years within the limit is the number of those on the preferred side of the limit, judged by the row's `direction` (C1.1). A row with a missing value is never counted as within or outside the limit: it is reported as not evaluated, with its reason (C3). Pass: both counts equal the counts made by hand on the table, and every missing row appears as not evaluated with its reason. A value equal to the limit counts as within (D90 below).
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 November 2026):
  - [D85](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): when no paired difference of a pair holds a value (every input missing), the pair is "not evaluated", with no state, consistent with D6 (a missing value does not enter the state) and with the wording of this entry. `identical_rows` is true only when at least one difference holds a value and every difference is equal to zero; a pair with a missing difference is never "identical". The state of a pair is entry D7.
  - [D89](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review it): the limit a user declares and the verified T of D74 live separately. Admissibility is decided only by D74: mean erosion at or below a verified T, with its source. The count of years within a limit (this entry) is descriptive, against the limit the user declares (`DECLARED`), and is shown apart. An official tolerance never edits the user's limit, and the user's limit never decides admissibility.
  - [D90](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review it): a value equal to the limit counts as within (inclusive), consistent with the wording of D74 ("at or below" T and "at or above" zero). The counting function keeps its required argument `equal_to_limit_counts_as_within`, with no default; callers pass `True`.
  - [D94](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): one count per rotation, scenario, indicator, carbon model and computation. Nothing is counted across scenarios or across carbon models.
  - [D95](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): years are counted only over rows whose `time_basis` is `ag_year`. An indicator on another time basis (the soil carbon trend; the water ratio when it is per rotation) has no count of years: it is judged only by the admissibility of D74 (D89), once per scenario and carbon model. A limit a user declares for such an indicator is not used in the counts.
  - [D96](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885583300) (logic): the only summary of the counts over many scenarios (D75) is the range, from minimum to maximum, of the years within the limit across the admitted scenarios, naming the scenario of the minimum. No mean, share or percentage of scenarios. How the screen shows it is for the interface developer.
- OPEN (not decided by D74 or D85 to D96): which scenarios are "admitted" (D96 and D74 both say "admitted scenarios"; D74 states admissibility for erosion, net stock change and the water ratio, not for scenarios), and who admits them. For the lead developer.
- OPEN (two decisions that may not fit as written): whether an indicator on another time basis enters the separation rule of entry D7 cell by cell (D93) or is judged only by admissibility (D95). Both texts are quoted under entry D7, item K5.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D85, D89, D90 and D94 to D96 of #77; the OPEN items of this entry are for the lead developer and the science reviewers; acceptance by a science reviewer pending

### D2

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: paired differences between two rotations. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. A difference is computed only between the two rows of a pair, that is rows of two rotations with the same cell (`scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation`), never across cells. It is the second rotation of the pair minus the first. Rows whose units differ are refused, with no conversion (C1.1). If either value is missing, the difference is missing with reason `MISSING_INPUT`, naming the missing side (C3.3). Swapping the two rotations changes only the sign. Pass: each of these properties holds on the table, and each computed difference equals the one written by hand. The range of a difference is D92 below. OPEN for the science reviewers: the paired-difference method (issue #96, OPEN 2), apart from the range of a difference, which D92 decides.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 November 2026):
  - [D87](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): for each pair, scenario and indicator, the output shows the count of paired cells where the second rotation is better, worse or equal, and of cells with a missing side, read in the direction of each row (C1.1). It is a count of this entry's differences: it never resolves a pair, and no statistic or p-value is attached. "Equal" uses the tolerance set by the designer of the case.
  - [D92](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885546548) (science; a science reviewer may still review it): the range of a paired difference is computed by interval arithmetic, worst case. For a pair with values A in `[a_low, a_high]` and B in `[b_low, b_high]`, the range of the difference B − A is `[b_low − a_high, b_high − a_low]`. It assumes no distribution and no independence between the two values. Both ranges must carry the same `kind` (C2.3); if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing" (entry D7).
- OPEN (not decided by D87 or D94): the counts of D87 are keyed by pair, scenario and indicator; D94 keys the counts of entry D1 also by carbon model and computation. Whether the counts of D87 are also split by carbon model and computation is not decided. For the lead developer.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: OPEN: the numerical tolerance for comparing a computed difference with the one written by hand, set by the person who designs the case.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D87 and D92 of #77; the OPEN items of this entry are for the lead developer and the science reviewers; acceptance by a science reviewer pending

### D3

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the tipping point of an uncertain input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data whose scenarios vary one uncertain input. If the state of the decision is the same for every scenario value of that input, no tipping point is reported, with that reason. If the state changes, the tipping point is reported as the bracket between the two adjacent scenario values where it changes, with the name and unit of the input; no value inside the bracket is interpolated. Pass: on tables built by hand with and without a change of state, the function reports no tipping point, or the bracket chosen by the designer of the table. OPEN for the science reviewers: whether, and by which method, a value inside the bracket may be interpolated.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D4

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the measurement priority ("measure first"). PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data whose scenarios vary several uncertain inputs. The priority is given only when the state is not resolved. An input whose scenario values never change the state ranks below an input whose values do. Inputs that tie share a rank. Each item is qualitative: rank, what to measure and why, with no monetary value (#96). Pass: on tables built by hand, the ranks equal the ones the designer of the table wrote, and a resolved state gives no priority list. OPEN for the science reviewers: the measure of how much an input moves the decision, which orders inputs that all change the state.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D5

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: direction of each indicator and dominance between rotations. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. The decision reads the `direction` of each row and never assumes it. A rotation that is no worse than another in every cell and better in at least one is never preferred less than that other rotation. Dominance between two rotations is judged only over the cells where both rotations hold a value: a cell where either side is missing counts neither for nor against either rotation, consistent with D6, under which a missing value does not enter the state (DECIDED by the lead developer, 14 November 2026; [D59](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6883698940) of #77). Reordering the rows or the rotations of the table does not change the result. Pass: the three properties hold on tables built by hand, including one where one indicator is `lower_is_better` and another `higher_is_better`.
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 November 2026):
  - [D91](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): when dominance is judged only over cells with a value on both sides (D59), the output carries the coverage: cells compared, out of the cells of the pair ("k of N"). No minimum coverage is set: D74 already gives no integral winner while an engine is unavailable.
  - [D93](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885578537) (science; a science reviewer may still review it), the part about a single cell: read in the direction of the indicator (C1.1), a paired cell with a difference range is a "strict improvement" only when the whole range of the difference lies on the better side of zero; a "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell. D93 states this for the separation rule of entry D7 (D74); its follow-up names this entry among those that record it. The rest of D93 is in entry D7.
- OPEN (two decisions that may not fit as written), for the lead developer:
  - K7 (D59 and D91 with D93). This entry judges dominance by cells that are "no worse" and "better", over the cells with a value on both sides (D59), and reports their coverage "k of N" (D91). D93 classes a cell by the range of its difference. D93 does not say whether "no worse" and "better" here are read as its "no deterioration" and "strict improvement", or stay comparisons of the two values. If they are read by range, a cell with a value on both sides but no range of its difference (D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason") is counted among the cells compared by D59 and D91 and yet cannot be classed by D93. D59 on #77: "Dominance is judged only on the cells that have a value on both sides." D93 on #77: "Read in the direction of the indicator (C1.1): "strict improvement" only when the whole range of the difference lies on the better side of zero; "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell."
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D59, D91 and the cell part of D93 of #77; the OPEN items of this entry are for the lead developer and the science reviewers; acceptance by a science reviewer pending

### D6

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: missing values and modules not built in the decision. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data with missing values. When every value of an indicator is missing, the decision gives no ranking for that indicator, with the reasons carried through. A missing value, or an indicator that is `NOT_AVAILABLE` (C3.2, D12 of #77), is never counted as zero, as within a limit, or as best or worst, and does not enter the state. The descriptive-only water measures (C1.4, and D50 of #77) never change the state. Pass: on tables built by hand, each of these properties holds, and changing a descriptive-only measure leaves the state unchanged.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D7

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the state "not resolved". PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. When the data cannot separate two rotations, the state is "not resolved" and names the indicators that are not resolved. Two rotations with identical rows are never resolved. A paired difference whose range is missing is never resolved. Pass: on tables built by hand, each of these properties holds. The rule that says when the data separate two rotations is D74 below, with D93 for a cell that carries a difference range (blueprint section 5 places this rule in the test plan; the follow-ups on #77 write D74 into this entry). The state names are those of D88 below. OPEN for the science reviewers: how the state treats the two carbon models when they disagree (see also K6 below).
- Decisions of the lead developer on [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77) recorded in this entry (14 November 2026):
  - [D74](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885437753) (science), the separation rule of this entry, as the follow-ups of [D85 to D91](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) and the comment of [D92](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885546548) record: paired scenarios and years, explicit trade-offs; scenario coverage is not a probability of success. A robust preference needs paired non-deterioration on every indicator in every admitted scenario with at least one strict improvement. No integral winner while erosion, dual-coefficient water, AMG or RothC is unavailable or has a failed control. Admissibility: mean erosion at or below a verified T; net stock change at or above zero in each of AMG and RothC over a common horizon; water ratio without a universal cut-off; no regulatory certification.
  - [D86](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (logic): a state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74). The names are those of D88.
  - [D88](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885512624) (science; a science reviewer may still review the wording): the names of the states of a pair are "Not evaluated" (D85) · "Identical" · "Not separated: uncertainty missing" · "Not robust across scenarios" · "Robust preference" (D74). Each name says why.
  - [D93](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6885578537) (science; a science reviewer may still review it): read in the direction of the indicator (C1.1), a paired cell with a difference range is a "strict improvement" only when the whole range of the difference lies on the better side of zero; a "deterioration" only when the whole range lies on the worse side; a range that touches or crosses zero is "not separated" for that cell. A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario; a cell that is not separated gives no strict improvement, and a pair whose only cells are not separated is "Not separated: uncertainty missing" or not robust (D86, D88).
  - Also recorded elsewhere and used here: D85 ("not evaluated", with no state, and when `identical_rows` is true) in entry D1; D92 (the range of a difference, and the state of a pair whose difference range is missing) in entry D2.
- OPEN (two decisions that do not fit, or may not fit, as written), for the lead developer. Each item quotes both texts from #77, without its bold:
  - K1 (D85 and D88). D85 gives the pair no state; D88 lists "Not evaluated" among the names of the states, and D86 lists no reason for it. D85: "The pair is "not evaluated", with no state, consistent with D6 (a missing value does not enter the state) and with the wording of D1." D88: ""Not evaluated" (D85) · "Identical" · "Not separated: uncertainty missing" · "Not robust across scenarios" · "Robust preference" (D74)." Question: is "Not evaluated" a state, or the absence of a state?
  - K2 (D92 with D85, D86 and D88). No decision says which state a pair takes when the conditions of two states hold. Example: every difference of a pair holds a value equal to zero and the ranges of those differences are missing. By D85 and D88 the pair is "Identical"; by D92 it is "Not separated: uncertainty missing". A second example: one cell has no difference range and another cell is a deterioration (D93). D85: "`identical_rows` is true only when at least one difference holds a value and every difference is equal to zero". D92: "if either range is missing or the kinds differ, the range of the difference is missing with its reason, and D86 / D88 give that pair the state "Not separated: uncertainty missing"". D86: "A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74)." Question: which state, and which reason, comes first?
  - K3 (D93 with D86, D88 and D92). D93 leaves two states open for a pair whose cells all carry a difference range that touches or crosses zero, and none of D86's reasons is written for that case (the uncertainty is not missing and there may be one scenario only). D93: "a pair whose only cells are not separated is "Not separated: uncertainty missing" or not robust (D86, D88)." D86: "A state that is not a robust preference carries its reason: identical rows; a difference without its range; not robust across the admitted scenarios (D74)." D92 gives "Not separated: uncertainty missing" to a pair whose difference range is missing. Question: which state and reason does such a pair take?
  - K4 (D93 and D74). D74 can be read as one strict improvement over the whole pair; D93 can be read as one strictly improving cell in each indicator and each admitted scenario. D74: "A robust preference needs paired non-deterioration on every indicator in every admitted scenario with at least one strict improvement (USER-R)." D93: "A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario". Question: is one strictly improving cell needed in the whole pair, or in each indicator and each admitted scenario?
  - K5 (D93 and D95, with D74). D93 puts every indicator into the separation rule cell by cell; D95 says an indicator whose `time_basis` is not `ag_year` is judged only by admissibility; and D74 sets no universal cut-off for the water ratio, so a water ratio per rotation would have no judgement under D95 alone. D93: "A robust preference (D74) needs no deteriorating cell and at least one strictly improving cell, in every indicator and every admitted scenario". D95: "An indicator on another time basis has no count of years: it is judged only by the admissibility of D74 (D89), once per scenario and carbon model." D74: "water ratio without a universal cut-off". Question: does a cell of the soil carbon trend, or of a water ratio per rotation, enter the separation rule of D93, or does D95's "judged only by the admissibility" apply only to the counts of entry D1?
  - K6 (D93 and D94, with D74). D94 keeps the two carbon models apart and D74 asks admissibility in each of them; D93 names indicators and scenarios but not carbon models, so the cells of AMG and RothC of one indicator could be read together (one strictly improving cell in either model satisfying the indicator). D94: "One count per rotation, scenario, indicator, carbon model and computation. Nothing is counted across scenarios or across carbon models." D74: "net stock change at or above zero in each of AMG and RothC over a common horizon". D93: "at least one strictly improving cell, in every indicator and every admitted scenario". Question: is D93 applied per carbon model? This is the OPEN item of the definition on carbon models that disagree.
  - K7 is under entry D5 (dominance and D93).
- OPEN (not decided by D74 or D85 to D96): which scenarios are "admitted" (D74, D86, D93 and D96), as under entry D1.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026), with D74, D86, D88 and D93 of #77; the OPEN items of this entry (K1 to K6 for the lead developer, carbon models for the science reviewers) are still pending; acceptance by a science reviewer pending

### D10

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: the measurement input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data and a value entered by the user for an input of the priority list. The value enters with label `OBSERVED` (C4.1), its unit, and its range or `range_missing` (C2). A blank value, or a value in a unit other than the expected one, is refused and never taken as zero (C3.1). The decision is recomputed with that input fixed at the measured value; no other input changes. Pass: on tables built by hand, each of these properties holds.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D12

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: consistency of tipping point, priority and measurement input. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data with a tipping point (D3) and a measured value (D10). A measured value on one side of the tipping point gives the state of that side. If the state becomes resolved after the measurement, the priority list is empty (D4). Pass: on tables built by hand, a value on each side of the bracket gives the state of that side, and the priority list empties when the state is resolved.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending
