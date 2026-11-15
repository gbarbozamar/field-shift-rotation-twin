# Saved case contract

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the interface developer, as producer and consumer of the contract (D177 of issue #77; sub-lane L2b writes it, lane L3 reads it), and the lead developer, as owner of `contracts/`. The platform developer reviews it under D159 and may change any of it. **The producer approved it as PROPOSED on #297, accepting the field names, with three changes, brought in below ([The three changes of the approval](#the-three-changes-of-the-approval-297)).**

**Current status on `main` (`9f6c2a7`):** The three changes of `#297` landed in `#384` (`16a9d2b`). `demo/saved_case.py` writes and checks `demo/saved_cases/example-case.json` (`#341` `fa578d8`, updated in `#384` `16a9d2b`), and `web/src/data/saved_case.json` holds its byte-identical copy guarded by `web/src/data/saved_case.test.ts` (`#391` `880fdb0`). The contract remains `PROPOSED` until formal pull-request approval.

This folder holds a Pydantic model and one example of the "saved case" contract: one case and the run of one of its fields, in one JSON document.

| Contract | Producer → consumers | Model | Example |
|---|---|---|---|
| Saved case | Interface: `demo/` writes it (sub-lane L2b) → `web/` reads it (lane L3), offline | `saved_case.SavedCase` | `examples/PLACEHOLDER_saved_case.json` |

The lead developer decided its shape in issue #77, on 15 November 2026, while holding the platform lane for the night (D159):

- D177: "One JSON document per case, described by a new contract `contracts/saved_case/`, kept as a file in the repository under `demo/`. Nothing is stored in the service." The document carries, unchanged, the contract documents that already exist: the field identity of the case (which answers OPEN 3 of issue #103: absorbed, not referenced), the results table, one `CarbonBalance` per rotation and carbon model, and the decision output. A part that does not exist is null with its `missing` part beside it and a reason code of C3.2 (C3.1); it is never left out and never zero. The document says `example_data`, true when any part it carries is example data, and carries the date it was saved, given by whoever writes it. It is written with every null kept. There is one file per case; saving again replaces it, and the commit is its version. `demo/` writes it and checks it; the interface reads a byte-identical copy under `web/src/data/`.
- D177, how it lands: a lane L0 builder lands `contracts/saved_case/` as PROPOSED (model, README, one hand-written PLACEHOLDER example, test), as D41 did for the field identity, and it takes effect when the interface developer approves the pull request as producer and consumer.

A builder session of lane L0 landed it here (unit `l0/contracts-saved-case`, brief in issue #284). Identifiers such as C3.1 below refer to `contracts/CONVENTIONS.md`. The decisions are a person's, transcribed by a builder session.

## The three changes of the approval (#297)

The interface developer, producer and consumer of the saved case (D177), approved the contract of #297 as PROPOSED with three changes, in [his comment on #297](https://github.com/gbarbozamar/field-shift-rotation-twin/pull/297#issuecomment-6893675216) of 15 November 2026. A builder session of lane L0 brought them in (unit `l0/saved-case-review-297`, brief #370). As he wrote them:

1. "The carbon items are **complete**: one per rotation of the results table and per carbon model, absent ones travelling missing with their reason (NOT_AVAILABLE) — an empty list cannot say whether a model was broken or never ran, and C1.5/D74 need to know."
2. "Names accepted, **with `variant` added to the key of `CarbonBalanceItem`** — the experimental AMG variant (D80) is otherwise indistinguishable at the same model and rotation."
3. "`NOT_AVAILABLE` for RothC missing (consistent with D122), and **`saved_on` carries date and time to the minute** — two saves on one day are two cases."

How each lands here:

1. **Complete carbon items.** When the results table is present, every rotation it names has at least one carbon item for each carbon model (`amg`, `rothc`), and no item names a rotation the results table does not name. An absent balance is an item with `carbon_balance: null` and its `carbon_balance_missing`. An empty list, a rotation without its items, or one model of a rotation without its item, is rejected. When the results table is itself missing, there is no list of rotations to check against, and nothing is checked (OPEN 14).
2. **`variant` in the key.** `CarbonBalanceItem` has a required `variant`, an identifier like the `variant` of `CarbonBalance` (Q14 (d); its vocabulary is OPEN 2 of `contracts/carbon_balance/README.md`). The key of an item is its `rotation_id`, `carbon_model` and `variant`: two items equal but for `variant` are two items. When the balance is present, `variant` is its own.
3. **`NOT_AVAILABLE` for a missing RothC.** The reason a writer gives to a missing RothC balance. The model does not enforce it: any of the eight codes of C3.2 still says why a part is missing (OPEN 11). **`saved_on` with the time to the minute.** `saved_on` is written `YYYY-MM-DDTHH:MMZ`: the date, the time to the minute, in UTC. A date without a time is rejected.

**The example is PLACEHOLDER data.** Each part it carries is the example of its own folder, with the identifiers listed under [The example](#the-example) changed so that the parts name one case and one field. Its numbers mean nothing, it was written by hand from those examples (no engine and no run produced it), and it describes no real place, no real field and no real producer. It says `"example_data": true`.

Acceptance test, from the repository root:

```bash
python -m pytest contracts/saved_case/
```

Models and pure validation only. No network calls, no file access, no clock, no parameter values, no thresholds, no citations. The date and time the case was saved is a value of the document; no model reads a clock. The documents carried are loaded by the models of their own folders, imported as `contracts.<folder>` (the import path of question Q1 of `contracts/ENTRYPOINTS.md`), never copied or redefined: `FieldIdentity` from `contracts.field_identity`, `ResultsTable` from `contracts.results.models`, `CarbonBalance` from `contracts.carbon_balance`, `DecisionOutput` from `contracts.decision_output`. The `missing` part, the non-blank text, the date and the base model come from `contracts.inputs.common`; the carbon model identifiers from `contracts.results.models`.

## Layout

| Path | Content |
|---|---|
| `saved_case.py` | `SavedCase` and `CarbonBalanceItem` |
| `examples/PLACEHOLDER_saved_case.json` | The example |
| `test_examples.py` | The acceptance test |

## Field list

All PROPOSED. Every model rejects unknown members and does not coerce types: a boolean written as text is rejected. No member has a default except the four `missing` members, which may be left out when their part is present; D177 writes the document "with every null kept", so a writer writes them as `null`, as the example does.

### `SavedCase`: one case and the run of one of its fields

| Field | Type | Rule |
|---|---|---|
| `contract` | `"saved_case"` | Required |
| `example_data` | true or false | Required. True when any part the document carries says it is example data (D177): see the rules below |
| `case_id` | text | Required, not blank. The identifier the other contracts use |
| `field_id` | text | Required, not blank. The field whose run the document holds |
| `saved_on` | date and time, `YYYY-MM-DDTHH:MMZ` | Required, never null. The date and the time to the minute the case was saved, in UTC, given by whoever writes the document (D177; #297, change 3). No seconds; the time zone is always `Z` |
| `field_identity` | `FieldIdentity` or null | Required key. The field identity of the case, unchanged (D177). Null only when missing (C3.1) |
| `field_identity_missing` | `Missing` | Present when `field_identity` is null, absent or null otherwise: never both and never neither (C3.1) |
| `results_table` | `ResultsTable` or null | Required key. The results table of the run, unchanged. Null only when missing |
| `results_table_missing` | `Missing` | As `field_identity_missing`, for `results_table` |
| `carbon_balances` | list of `CarbonBalanceItem` | Required. Complete (#297, change 1): with a results table, every rotation it names has an item for each carbon model, and no item names another rotation. No two items for the same `rotation_id`, `carbon_model` and `variant` (D177; #297, change 2) |
| `decision_output` | `DecisionOutput` or null | Required key. The decision output of the run, unchanged. Null only when missing |
| `decision_output_missing` | `Missing` | As `field_identity_missing`, for `decision_output` |

### `CarbonBalanceItem`: one rotation, one carbon model and one variant

| Field | Type | Rule |
|---|---|---|
| `rotation_id` | text | Required, not blank. The rotation the balance is for, also when it is missing, so that a consumer knows what is missing (C3.1) |
| `carbon_model` | `"amg"` or `"rothc"` | Required. `CarbonModel` of `contracts/results/models.py` (D1 of issue #77) |
| `variant` | identifier (lower case, underscores) | Required. The variant of the balance, also when it is missing (#297, change 2): the `variant` of `CarbonBalance`, whose vocabulary is OPEN 2 of `contracts/carbon_balance/README.md`. The engines write `amg_a` (AMG-A, `engine/amg/entry.py`) and `rothc_26_3` (`engine/rothc/entry.py`) |
| `carbon_balance` | `CarbonBalance` or null | Required key. The balance, unchanged. Null only when missing |
| `carbon_balance_missing` | `Missing` | Present when `carbon_balance` is null, absent or null otherwise (C3.1) |

### `Missing`

The `missing` part of C3.1, from `contracts/inputs/common.py`, reused: `reason`, one of the eight codes of C3.2, and an optional `detail` in English; `MISSING_INPUT` needs a `detail` that names the input (C3.2). Any of the eight codes may say why a part is missing.

### The documents carried

| Part | Model | Folder | Says `example_data` |
|---|---|---|---|
| `field_identity` | `FieldIdentity` | `contracts/field_identity/` | Yes |
| `results_table` | `ResultsTable` | `contracts/results/` | **No**: the results table has no `example_data` and no `contract` member |
| `carbon_balances[].carbon_balance` | `CarbonBalance` | `contracts/carbon_balance/` | Yes |
| `decision_output` | `DecisionOutput` | `contracts/decision_output/` | Yes |

Each is validated by its own model, with every rule of its own README; nothing in this folder relaxes or repeats them.

## Rules the model checks

From the brief of issue #284, D177, C3.1 and the three changes of #297:

- Every part is its document, or null with its `missing` part beside it, named after it (`field_identity` and `field_identity_missing`, the pattern of `geometry` and `geometry_missing` in `contracts/field_identity/`): never both, never neither (C3.1). This holds for the three top-level parts and for the balance of each carbon item. A part is never left out: its key is required.
- The reason of a missing part is a code of C3.2.
- No two carbon items for the same rotation, carbon model and variant (D177: one per rotation and carbon model; #297, change 2: `variant` in the key).
- The carbon items are complete (#297, change 1): with a results table, each rotation it names has an item for each carbon model.
- `saved_on` is a date and a time to the minute, in UTC (#297, change 3).
- A carried document belongs to the case and field of the document: the `case_id` of the field identity, and the `case_id` and `field_id` of the results table, of each balance and of the decision output, are those of the saved case.
- `example_data` is true when a part it carries says it is example data (D177): a document that says `false` while the field identity, a balance or the decision output says `true` is rejected.

**Added by this contract**, asked for neither by the brief nor by a decision. Each needs the interface developer's acceptance:

1. **The document's field is a field of the case.** The field identity lists several fields and has no `field_id` of its own, so the brief's "a carried document whose `field_id` is not the document's" is read, for the field identity, as: the `field_id` of the saved case is one of its fields.
2. **A carbon item names the balance it holds.** When the balance is present, the `rotation_id`, `carbon_model` and `variant` of the item are those of the balance. Without it, the key of an item could contradict its content.
3. **`saved_on` is never missing.** D177 says the document "carries the date it was saved, given by whoever writes it"; the model requires it and gives it no `missing` part.
4. **No carbon item for a rotation the results table does not name** (unit `l0/saved-case-review-297`). Read from change 1, "one per rotation of the results table": the list of items is that of the rotations of the results table.
5. **The form of `saved_on`** (unit `l0/saved-case-review-297`). Change 3 asks for the date and the time to the minute and names no form: `YYYY-MM-DDTHH:MMZ`, in UTC (the time zone of C6.2), no seconds. C5.2 writes dates only; no convention writes a time yet.

## What is not checked

The model does not check what no decision asks for. Each item is a case "accepted only while a question is open" or an item under [OPEN](#open):

- That `example_data` is false when no part says it is example data (the converse of D177): the results table carries no flag, and a document whose parts are all missing has nothing to read it from.
- That the carbon items are complete when the results table is missing: there is no list of rotations to check them against (OPEN 14). The rotations of the decision output are not read for it.
- That a missing RothC balance has the reason `NOT_AVAILABLE` (#297, change 3): it is the writer's reason, not a rule of the model (OPEN 11).
- That values that travel twice agree: the trend of a `CarbonBalance` and the `soil_carbon_trend` rows of the results table; the rotations and scenarios of the decision output and those of the results table. In the example they do not agree, because each part comes from the example of its own folder (for `example-rotation-1`, AMG, `end_minus_start`: `11.1` in the balance and `0.5` in the table; both are placeholder numbers).
- That the date and time are plausible: any valid date and time is accepted, before or after the run.

## Writing and reading

- Write with `SavedCase.model_dump(mode="json")` (or `model_dump_json()`), **never with `exclude_none=True`**: it drops `"carbon_balance": null` and `"value": null`, which are required, and the document no longer loads (D177: "written with every null kept"; `test_a_document_written_without_its_nulls_does_not_load`).
- A document written by the model also writes the members that the carried documents leave to their defaults, such as `"assumption": false`, `"range": null` and `"missing": null` in each row of the results table. The example, copied from the examples of the folders, leaves them out. Both load into the same model; a reader accepts both. Measured on the example: 29 870 bytes as written by hand; 37 756 bytes written by `model_dump_json(indent=2)`; 23 567 bytes written by `model_dump_json()` on one line.
- `saved_on` is written as `YYYY-MM-DDTHH:MMZ` in JSON. From Python, a writer may also give an aware `datetime` in UTC with no seconds; the model writes it back in that form.
- Read with `SavedCase.model_validate_json(text)`. A reader of a part first checks whether the part is null and, if so, shows its `missing` reason (C3.3).

## The example

`examples/PLACEHOLDER_saved_case.json`: 29 870 bytes, 876 lines, UTF-8 with line feeds. Case `example-case`, field `example-field-1`, saved on `2026-11-15T11:56Z` (the time, in UTC, unit `l0/saved-case-review-297` rewrote the example; it stands for nothing else).

| Part | Comes from | Identifiers changed |
|---|---|---|
| `field_identity` | `contracts/field_identity/examples/PLACEHOLDER_field_identity.json` | None |
| `results_table` | `contracts/results/examples/PLACEHOLDER_results_table.json` | `PLACEHOLDER_case` → `example-case`; `PLACEHOLDER_field` → `example-field-1`; `PLACEHOLDER_rotation_a` → `example-rotation-1`; `PLACEHOLDER_rotation_b` → `example-rotation-2` |
| `carbon_balances[0].carbon_balance` (`example-rotation-1`, `amg`) | `contracts/carbon_balance/examples/PLACEHOLDER_carbon_balance.json` | `PLACEHOLDER-case` → `example-case`; `PLACEHOLDER-field` → `example-field-1`; `PLACEHOLDER-rotation` → `example-rotation-1` |
| `decision_output` | `contracts/decision_output/examples/PLACEHOLDER_decision_output.json` | None |

The identifiers are aligned to those of the field identity example (`example-case`, `example-field-1`). The rotations take the identifiers of the decision output example, `example-rotation-1` and `example-rotation-2`, and the results table is mapped to them exactly as `contracts/decision_output/test_examples.py` already maps it (`IDS_IN_THE_RESULTS_TABLE_EXAMPLE`). Only the members `case_id`, `field_id` and `rotation_id` changed; every other byte of each part is its example's text, indented to its place. The test rebuilds each part from its example with this list of changes and checks that it equals the part, so a change to one of those examples shows here.

Written here by hand: the header; the explicit `null` of each `missing` member of a present part; the `variant` of each carbon item, `placeholder_variant`, the variant of the balance example, for the item that holds it and for the three that do not (a PLACEHOLDER identifier, not the vocabulary of the engines); and the three carbon items whose balance is missing, each with reason `NOT_AVAILABLE` and a PLACEHOLDER detail. The four items are complete for the two rotations of the results table (#297, change 1). Two of them are the RothC balances of the two rotations, with the detail the results table example gives its RothC rows ("this carbon model is not enabled in the example"). The third is the AMG balance of `example-rotation-2`: only one balance example exists, so it is missing with the detail "the example carries one carbon balance, for the first rotation". Its reason code is placeholder, as the examples of `contracts/results/` and `contracts/carbon_balance/` already use `NOT_AVAILABLE` for "the example gives none".

## PROPOSED cases

Every case below is a change to the example, made in memory. The invalid ones must be rejected; the test checks that each is rejected for the stated reason, both as Python data and as JSON text. Each accepted one loads, from Python data and from JSON text, and loads back equal after `model_dump(mode="json")`. The identifiers are the test identifiers in `test_examples.py`.

### Rejected: the header

| Case | The variant |
|---|---|
| `unknown-member-of-the-document` | The document carries a `tipping_point`: where the tipping point travels is OPEN (D177) |
| `unknown-member-of-a-carbon-item` | A carbon item carries a `label` |
| `contract-of-another-name` | `contract` is `"field_identity"` |
| `example-data-as-text` | `example_data` is the text `"true"` |
| `case-id-blank` | `case_id` is only white space |
| `field-id-blank` | `field_id` is empty |
| `saved-on-not-a-date` | `saved_on` is `"15 November 2026 11:56"` |
| `saved-on-without-a-time` | `saved_on` is `"2026-11-15"`, a date without a time (#297, change 3) |
| `saved-on-with-seconds` | `saved_on` is `"2026-11-15T11:56:00Z"`: the time is to the minute (added rule 5) |
| `saved-on-without-its-time-zone` | `saved_on` is `"2026-11-15T11:56"` (added rule 5) |
| `saved-on-in-another-time-zone` | `saved_on` is `"2026-11-15T08:56-03:00"`: the time is in UTC (added rule 5) |
| `saved-on-not-a-time-of-the-day` | `saved_on` is `"2026-11-15T24:56Z"` |
| `saved-on-null` | `saved_on` is null |

### Rejected: a part and its missing part

| Case | The variant |
|---|---|
| `field-identity-null-without-missing-part` | `field_identity` is null and `field_identity_missing` is null (C3.1) |
| `results-table-null-without-missing-part` | The same for `results_table` |
| `decision-output-null-without-missing-part` | The same for `decision_output` |
| `carbon-balance-null-without-missing-part` | The balance of the first carbon item is null with no `carbon_balance_missing` |
| `field-identity-and-missing-part-both` | The field identity and a `field_identity_missing` together (C3.1) |
| `results-table-and-missing-part-both` | The same for `results_table` |
| `decision-output-and-missing-part-both` | The same for `decision_output` |
| `carbon-balance-and-missing-part-both` | The balance of the first carbon item and a `carbon_balance_missing` together |
| `missing-part-with-reason-not-in-the-sheet` | The field identity is missing with reason `NOT_SAVED`, which is not a code of C3.2 |
| `missing-part-with-reason-in-lower-case` | A missing balance with reason `not_available` |
| `missing-part-without-reason` | The results table is missing with a `detail` and no `reason` |
| `missing-input-without-detail` | The decision output is missing with `MISSING_INPUT` and no `detail` naming the input (C3.2) |

### Rejected: the carbon items

| Case | The variant |
|---|---|
| `two-carbon-items-for-one-rotation-model-and-variant` | The second item, RothC of `example-rotation-1`, becomes AMG with the variant of the first: two items for one rotation, carbon model and variant (D177; #297, change 2) |
| `no-carbon-item` | `carbon_balances` is an empty list while the results table names two rotations (#297, change 1) |
| `rotation-of-the-results-without-a-carbon-item` | `example-rotation-2`, which the results table names, has no carbon item (#297, change 1) |
| `carbon-model-of-a-rotation-without-an-item` | The RothC item of `example-rotation-1` is left out (#297, change 1) |
| `carbon-item-of-a-rotation-not-in-the-results` | A carbon item for `example-rotation-3`, which the results table does not name (added rule 4) |
| `carbon-item-of-another-variant-than-its-balance` | The first item says `placeholder_other_variant` and holds a balance of `placeholder_variant` (added rule 2) |
| `carbon-item-variant-not-an-identifier` | A carbon item says `RothC 26.3`, which is not an identifier |
| `carbon-item-of-another-rotation-than-its-balance` | The balance of the first item names `example-rotation-2`; the item names `example-rotation-1` (added rule 2) |
| `carbon-item-of-another-model-than-its-balance` | The first item says `rothc` and holds an AMG balance (added rule 2) |
| `carbon-model-not-decided` | A carbon item names `RothC`, which is not `amg` or `rothc` (D1 of issue #77) |

### Rejected: a carried document of another case or field

| Case | The variant |
|---|---|
| `field-identity-of-another-case` | The field identity names another `case_id` |
| `field-identity-without-the-field` | The field identity no longer lists `example-field-1`, the field of the document (added rule 1) |
| `results-table-of-another-case` | The results table names another `case_id` |
| `results-table-of-another-field` | The results table names `example-field-2`, another field of the case |
| `carbon-balance-of-another-case` | The balance names another `case_id` |
| `carbon-balance-of-another-field` | The balance names `example-field-2` |
| `decision-output-of-another-case` | The decision output names another `case_id` |
| `decision-output-of-another-field` | The decision output names `example-field-2` |

### Rejected: `example_data`

| Case | The variant |
|---|---|
| `example-data-false-while-the-field-identity-says-true` | Every flag is false except that of the field identity (D177) |
| `example-data-false-while-a-carbon-balance-says-true` | Every flag is false except that of the balance |
| `example-data-false-while-the-decision-output-says-true` | Every flag is false except that of the decision output |

### Accepted

| Case | The variant |
|---|---|
| `accepted-every-carbon-item-missing` | The balance of every carbon item is null with its `missing` part |
| `accepted-not-example-data` | The document and every part that carries the flag say `example_data: false` |
| `accepted-field-identity-with-one-field` | The field identity lists only `example-field-1` (the example lists three: a field identity with several fields) |
| `accepted-run-of-another-field-of-the-case` | The document, the results table, the balance and the decision output name `example-field-2`, the second field of the case |
| `accepted-field-identity-missing` | The field identity is null with its `missing` part |
| `accepted-results-table-missing` | The results table is null with its `missing` part |
| `accepted-decision-output-missing` | The decision output is null with its `missing` part |
| `accepted-every-part-missing` | The three parts and every balance are null with their `missing` parts |
| `accepted-missing-part-without-detail` | A `missing` part with a reason and no `detail` |
| `accepted-missing-input-with-detail` | The decision output is missing with `MISSING_INPUT` and a `detail` naming the input |
| `accepted-missing-members-left-out` | The `missing` members of the present parts are left out instead of written as `null` |
| `accepted-two-variants-of-one-model` | A second AMG item for `example-rotation-1`, equal to the first but for its variant, `placeholder_other_variant`, missing with its reason (#297, change 2) |
| `accepted-another-minute-of-the-same-day` | `saved_on` is `2026-11-15T11:57Z`, a minute after the example: a second save of the same day (#297, change 3) |

### Accepted only while a question is open

The model does not reject these variants **only** because no decision gives it a rule for them. No case here is a proposal to allow what it shows. If a person decides on a rule, the model gains it and the case becomes a rejected one.

| Case | The variant | Question under OPEN |
|---|---|---|
| `accepted-while-open-example-data-true-while-no-part-says-so` | Every part says `example_data: false` and the document says `true` | 8 |
| `accepted-while-open-no-carbon-item-without-a-results-table` | The results table is missing with its reason, and `carbon_balances` is an empty list | 14 |

### Checked without a case of their own

- The example loads, and nothing is added, dropped or changed on the way through the model.
- Each part the example carries loads into the model of its own contract, and is an instance of the class of that contract's folder.
- The example, written with `model_dump(mode="json")` and loaded back, equals itself, from Python data and from JSON text; written again, it gives the same data.
- A document written with `exclude_none=True` does not load.
- No member of the document and no member of a carbon item can be left out (except the `missing` members): the test leaves out each one in turn.
- Each of the eight codes of C3.2 is accepted as the reason of a missing part.
- Two saves of one day, a minute apart, are two different documents, and `saved_on` is written back exactly as it was written (#297, change 3).
- A `saved_on` given from Python as an aware `datetime` in UTC, with no seconds, is written as `YYYY-MM-DDTHH:MMZ`; one without a time zone, with seconds, in another time zone, or a date without a time, is rejected.
- Each part of the example equals the example of its folder with the identifiers above changed, and this README lists each of them.

## Differences from #251

Issue #251 is the brief draft of unit `l2/saved-case` (sub-lane L2b), whose second gate is "the storage shape of a saved case". D177 answers that gate; this contract is the shape. For the interface developer, to accept or to contest:

1. **Where the shape comes from.** #251: "the storage shape comes from the platform's decision — if no shape exists when this unit's gates clear, report and hold", and it lists storage design as out of scope. D177 is that decision, taken by the lead developer holding the platform lane (D159); the shape is this contract, and the file lives under `demo/`. Nothing is stored in the service.
2. **The field identity travels too.** #251 lists the two carbon balances, the results table and the decision output. D177 adds the field identity of the case, absorbed and not referenced (OPEN 3 of issue #103), as the part `field_identity`.
3. **One balance per rotation and carbon model, not two per case.** #251 says "both carbon models' balances (AMG and RothC over the same forcing)". A `CarbonBalance` is for one rotation of one field, so a run of several rotations has one per rotation and carbon model (D177). They travel as `carbon_balances`, each item keyed by `rotation_id` and `carbon_model`.
4. **A whole part may be missing, with its reason.** #251 asks for absences typed "throughout". This contract types whole parts the same way (C3.1): a balance that was not computed is an item with `carbon_balance: null` and `carbon_balance_missing`; `#297` (change 3, landed in `#384` `16a9d2b`) specifies `NOT_AVAILABLE` for a missing RothC balance. **On `main` (`9f6c2a7`):** the runner (`api/engines.py`) now discovers and calls EP6 `run_rothc` (`#282` `994978e`; monthly `soil_cover` wired in `#431` `9f6c2a7`), while `demo/saved_case.py` (`#341` `fa578d8`, `#384` `16a9d2b`) still writes `NOT_AVAILABLE` for RothC in `demo/saved_cases/example-case.json` (and its guarded copy `web/src/data/saved_case.json`, `#391` `880fdb0`) because the thin matrix has no `CarbonForcing`. *As first written:* for RothC while the runner does not call EP6, the reason would be `NOT_AVAILABLE`. Whether #251 may save the case that way is a question for the interface developer (D177, "Follow-ups"; OPEN 11).
5. **The run's outputs, not its inputs.** #251's acceptance test asks that "loading it back reproduces the run's outputs exactly". The document carries the outputs D177 names; loading it back gives the same documents (the round-trip test). The run's inputs (rotation definitions, calendars, site data) and the monthly results do not travel (OPEN 1).
6. **The date.** #251 does not mention it. D177 and blueprint section 5 ("with date and citation") ask for it: `saved_on`, with the time to the minute since #297 (change 3). The citation is OPEN (item 6).
7. **One field per document.** #251 speaks of one saved run. The document holds one case and the run of one of its fields (`field_id`); the field identity it carries may list several fields. Whether one document may hold the runs of several fields is OPEN (item 3).

## What the documents carried lack for a saved case

Listed, not changed: the brief forbids editing the other folders of `contracts/`.

- `ResultsTable` has no `contract` and no `example_data` member. The saved case cannot read from it whether it is example data, and a file holding only a results table does not say what it is.
- `ResultsTable` brings its own `Missing` class (`contracts/results/models.py`); this contract uses the one of `contracts/inputs/common.py`, as the brief asks. The two accept the same codes.
- `DecisionOutput` has no field for the tipping point (its README: "The tipping point is not here").
- `CarbonBalance` carries a `variant` (its README, OPEN 2). Since #297 (change 2) the key of a carbon item has it too, so two variants of one model for one rotation both travel; the vocabulary of `variant` is still OPEN there.
- No contract carries a version. Since #297 (change 3) `saved_on` carries the time to the minute, so two saves of one case on one day are told apart; two saves within one minute are not.
- `FieldIdentity` has no field of the run: the saved case adds `field_id` beside it.
- The `soil_carbon_trend` of a `CarbonBalance` and the `soil_carbon_trend` rows of `ResultsTable` carry the same quantity twice, and no contract says they agree.

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end of the item.

### Left open by D177

1. **Do rotation definitions, calendars, site data and the monthly results travel in the document?** Today they do not: the document carries the four kinds of document D177 names. For the interface developer, as producer and consumer, and the lead developer.
2. **Where does the tipping point travel?** The decision output contract has no field for it, and this contract rejects a `tipping_point` member (case `unknown-member-of-the-document`). For the lead developer and the interface developer.
3. **May one document hold the runs of several fields?** Today one: `field_id` names the field of the run, and every carried document names it. For the interface developer.
4. **How is a second saved version of one case told apart?** D177: "There is one file per case; saving again replaces it, and the commit is its version." **Answered in part by #297 (change 3):** `saved_on` carries the time to the minute, so two saves on one day are two cases. Two saves within one minute still look the same from inside the file, and the document carries no version. For the interface developer and the platform developer.

### Left for the platform developer by D177

5. **Does the service ever store or serve saved cases** (a folder on the volume of D42, a setting, a route), and how is a case saved from a real run of the route? Nothing in `api/`, `adapters/`, CI or the deployed service changes under D177 or under this contract. For the platform developer.

### Raised by the landing

6. **The citation.** Blueprint section 5: "Saved case | Platform → Interface | What is stored per case, with date and citation; opens offline". D177 names the date and no citation. The document carries no citation member; each value inside the carried documents carries its own source (C4.2). Does a saved case carry a citation of its own, and what is it? For the lead developer.
7. **Completeness of the carbon items.** **Answered by #297 (change 1):** one item per rotation of the results table and per carbon model, an absent balance missing with its reason. The model checks it when the results table is present, and rejects an item for a rotation the results table does not name (added rule 4). What remains is item 14.
8. **The converse of `example_data`.** May a document say `example_data: true` while no part it carries says so? Accepted today (case numbered 8): the results table carries no flag, and a document whose parts are all missing has nothing else to say it. For the interface developer.
9. **Agreement across parts.** Should the model check that values carried twice agree: the trend in a balance and in the results table; the rotations and scenarios of the decision output and of the results table? Not checked today; the example's parts do not agree, being placeholders from different examples. For the interface developer and the lead developer.
10. **The variant of a carbon model.** **Answered by #297 (change 2):** `variant` is in the key of a carbon item; the case is now `two-carbon-items-for-one-rotation-model-and-variant`. The vocabulary of `variant`, and whether AMG-M travels as a second `CarbonBalance` of AMG, stay OPEN 2 of `contracts/carbon_balance/README.md`. For the lead developer and the interface developer.
11. **RothC missing.** **Answered by #297 (change 3, landed in `#384` `16a9d2b`):** a missing RothC balance travels with `NOT_AVAILABLE` (consistent with D122). It is the writer's reason (used by `demo/saved_case.py`, `#341` `fa578d8` and `#384` `16a9d2b`); the model accepts any code of C3.2 for a missing part. Should the model reject a missing RothC balance with another reason? For the interface developer.
12. **`ResultsTable` without `contract` and `example_data`.** Adding them is a change to `contracts/results/`, outside this unit. For the lead developer, as owner of `contracts/`.
13. **The added rules.** The field names are accepted (#297, change 2: "Names accepted"). The rules listed under "Added by this contract", rules 4 and 5 among them, still need the interface developer's acceptance. For the interface developer.

### Raised by unit `l0/saved-case-review-297`

14. **Completeness without a results table.** When the results table is missing, the model has no list of rotations to check the carbon items against, and accepts any list, an empty one included (case `accepted-while-open-no-carbon-item-without-a-results-table`). Should the rotations of the decision output, or of something else, stand in for them? For the interface developer.
