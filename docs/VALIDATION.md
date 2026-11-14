# Validation protocol

**Skeleton. Nothing in this file is defined yet.**

This file will hold the acceptance tests that `docs/DEVELOPMENT_BLUEPRINT.md` refers to by codes in square brackets. It has one entry per code named in section 8 of the blueprint, and every scientific field of every entry is open.

## Owner

The science reviewers own this file (blueprint sections 2 and 10). They complete every entry. Developers and AI sessions read it; they do not fill it.

## Status of this skeleton

This skeleton is a proposal under blueprint section 3.7. It was laid out by an AI builder session and takes effect only when a person approves the pull request. It is a science-class change, so that pull request also needs a science reviewer.

The session supplied the layout and copied the blueprint's wording. It supplied no definition, value, tolerance, data source or citation.

## How an entry gets completed

- **Section 3.5.** The value of a parameter, a threshold or a range, the expected value of a test, and a citation are never delegated to a session. A citation produced by an AI session is a defect.
- **Section 3.6.** The content of an entry is a science-class change: a person writes the values, a second person checks them against the source, and a science reviewer accepts them.
- **Section 3.7.** A session may propose layout, and marks it `PROPOSED`. Where a value, a threshold, a range, an expected value or a citation is needed, it writes `OPEN` or `CITATION NEEDED` and stops there.
- **Section 10.** The science reviewers fix thresholds and uncertainty ranges before results are seen, and check each transcribed value against its source as the second person. Nobody approves their own values.

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
| Transcribed by | `OPEN` | Which person wrote the values from the source? |
| Checked by | `OPEN` | Which second person checked the values against the source? |
| Status | `not defined` | — |

## Open questions about this file

- OPEN: the blueprint does not say what the first letter of a code stands for. Entries are grouped by that letter and the groups are not named.
- OPEN: several codes share one wording in the blueprint. What each of those codes covers on its own is for the science reviewers to state; the entries say where this applies.
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

- What it checks (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
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

- What it checks (blueprint wording): "annual soil-loss equation with unit guard [E8] and invariants [E9]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
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

- What it checks (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
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

- What it checks (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
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

- What it checks (blueprint wording): "Continuous daily water balance: mass closure [H7], invariants [H8], public reference case [H1]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
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

### D1

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D2

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D3

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D4

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D5

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D6

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D7

- What it checks (blueprint wording): "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 1 — one rotation end to end, until CP1"
- Unit it gates: "decision functions on hand-made tables [D1, D2, D5, D6, D7]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D10

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined

### D12

- What it checks (blueprint wording): "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Shared wording: the blueprint gives this wording to more than one code. What this code covers on its own: OPEN
- Lane: L2 Platform
- Block: "Block 2 — two clocks and the decision, until CP2"
- Unit it gates: "tipping point, measurement priority and measurement input [D3, D4, D10, D12]"
- Class (blueprint section 3.6): Science — PROPOSED
- Definition: OPEN
- Expected value: OPEN
- Tolerance: OPEN
- Source: CITATION NEEDED
- Transcribed by: OPEN
- Checked by: OPEN
- Status: not defined
