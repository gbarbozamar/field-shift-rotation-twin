# Validation protocol

**Skeleton, partly filled. The E and H entries are not defined yet. The D entries have their logic decided by the lead developer (14 November 2026); their OPEN items and their acceptance by a science reviewer are still pending.**

This file holds the acceptance tests that `docs/DEVELOPMENT_BLUEPRINT.md` refers to by codes in square brackets. It has one entry per code named in section 8 of the blueprint. No entry has a numeric value, threshold, numeric tolerance, expected value of the science, source or citation yet.

## Owner

The science reviewers own this file (blueprint sections 2 and 10). Under section 3.6, the values of an entry are transcribed from their source as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says, and one person checks them against the source. Section 3.5 of the blueprint states D34. Under section 10, the science reviewers check each transcribed value against its source, as decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) says (one person checks it, stated in section 3.5 of the blueprint), and a science reviewer accepts the entry.

## Status of this skeleton

This skeleton is a proposal under blueprint section 3.7. It was laid out by an AI builder session and takes effect only when a person approves the pull request. It is a science-class change, so that pull request also needs a science reviewer.

The session supplied the layout and copied the blueprint's wording. It supplied no definition, value, tolerance, data source or citation.

Later change (#138): an AI session proposed the definitions of the D entries as logic on hand-made results tables, and the lead developer approved that logic on 14 November 2026. That change wrote no value, threshold, tolerance, expected value of the science, data source or citation; those stay `OPEN` or `CITATION NEEDED` for the science reviewers.

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
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data and a declared limit per indicator. For each rotation and indicator, years evaluated is the number of agricultural-year rows that hold a value, and years within the limit is the number of those on the preferred side of the limit, judged by the row's `direction` (C1.1). A row with a missing value is never counted as within or outside the limit: it is reported as not evaluated, with its reason (C3). Pass: both counts equal the counts made by hand on the table, and every missing row appears as not evaluated with its reason. OPEN for the science reviewers: whether a value equal to the limit counts as within (the source of a limit says so); the function takes it as an argument.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

### D2

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: paired differences between two rotations. PROPOSED by an AI session; DECIDED by the lead developer, 14 November 2026
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. A difference is computed only between the two rows of a pair, that is rows of two rotations with the same cell (`scenario_id`, `indicator`, `time_basis`, `ag_year`, `carbon_model`, `computation`), never across cells. It is the second rotation of the pair minus the first. Rows whose units differ are refused, with no conversion (C1.1). If either value is missing, the difference is missing with reason `MISSING_INPUT`, naming the missing side (C3.3). Swapping the two rotations changes only the sign. Pass: each of these properties holds on the table, and each computed difference equals the one written by hand. OPEN for the science reviewers: the paired-difference method and the range of a difference (until then the range is missing with its reason, as in #96).
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: OPEN: the numerical tolerance for comparing a computed difference with the one written by hand, set by the person who designs the case.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

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
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. The decision reads the `direction` of each row and never assumes it. A rotation that is no worse than another in every cell and better in at least one is never preferred less than that other rotation. Dominance between two rotations is judged only over the cells where both rotations hold a value: a cell where either side is missing counts neither for nor against either rotation, consistent with D6, under which a missing value does not enter the state (DECIDED by the lead developer, 14 November 2026). Reordering the rows or the rotations of the table does not change the result. Pass: the three properties hold on tables built by hand, including one where one indicator is `lower_is_better` and another `higher_is_better`.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

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
- Definition (PROPOSED by an AI session; logic DECIDED by the lead developer, 14 November 2026): Input: a hand-made `ResultsTable` (`contracts/results/`), labelled example data. When the data cannot separate two rotations, the state is "not resolved" and names the indicators that are not resolved. Two rotations with identical rows are never resolved. A paired difference whose range is missing is never resolved. Pass: on tables built by hand, each of these properties holds. OPEN for the science reviewers: the rule that says when the data separate two rotations (it lives in the test plan, blueprint section 5), the exact state names and wording (#96), and how the state treats the two carbon models when they disagree.
- Expected value: the outcome stated as logic in the definition. Any count, difference, order or bracket that a test compares is read off the hand-made table by the person who designs the case; this file writes no expected value of the science.
- Tolerance: not applicable to the logic: counts, states, ranks and brackets are compared exactly.
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: logic DECIDED (lead developer, 14 November 2026); the OPEN items in the definition are for the science reviewers; acceptance by a science reviewer pending

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
