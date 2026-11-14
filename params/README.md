# Parameter catalogue

Where crop and rotation parameters are stored, each with its unit, its uncertainty range, its citation and the two persons who transcribed and checked it.

**This folder holds no parameter yet.** It holds the layout, the record format and the check that rejects a malformed record.

> **Status: PROPOSED.** The record format, the scope keys and the test cases below were written by a builder session (blueprint section 3.7). They take effect only when a person approves the pull request. Items marked `OPEN` need an answer from a person.

Values, ranges and citations are science class (blueprint sections 3.5 and 3.6): a person writes them, a second person checks them against the source, and a science reviewer accepts them. A session never writes one.

## Layout

| Path | Content |
|---|---|
| `records/` | The catalogue: one JSON file per parameter record. Empty today |
| `examples/` | Two placeholder records that show the format. Never read as parameters |
| `catalogue.py` | The record checks. Standard library only |
| `test_layout.py` | The acceptance test. It also checks every file under `records/` |

Run the check from the repository root:

```bash
python -m pytest params/
```

Provisional environment: Python 3.12 and pytest; standard library otherwise.

### Files in `records/` (PROPOSED)

- One record per file, UTF-8, extension `.json`. Subfolders are allowed and carry no meaning.
- Convention, not enforced: name the file after the record, `<id>.json` or `<id>.<scope words>.json`.
- What identifies a record is its `id` and `scope`, not its path.
- A file with a repeated key, or with `NaN` or `Infinity`, is rejected.

## Record format (PROPOSED)

```json
{
  "id": "PLACEHOLDER_parameter",
  "scope": { "crop": "PLACEHOLDER_crop" },
  "value": 2.0,
  "unit": "PLACEHOLDER_unit",
  "range": {
    "low": 1.0,
    "high": 3.0,
    "basis": "PLACEHOLDER: what the range represents, as the source states it"
  },
  "citation": {
    "reference": "PLACEHOLDER reference. This is not a publication.",
    "locator": "PLACEHOLDER locator: the table, page or equation holding the value"
  },
  "transcribed_by": "PLACEHOLDER_person_one",
  "checked_by": "PLACEHOLDER_person_two"
}
```

| Field | Required | Rule |
|---|---|---|
| `id` | yes | Name of the quantity. Starts with a letter; letters, digits and `_` only |
| `scope` | yes | What the value applies to: an object using only the scope keys below, each with a non-empty string. `{}` means no restriction is stated |
| `value` | yes | A finite number, or `null` together with `value_missing_reason` |
| `value_missing_reason` | only when `value` is `null` | Non-empty text. Not allowed next to a value |
| `unit` | yes | Non-empty text. Also required when the value is missing: the unit the value would have |
| `range` | yes | The uncertainty range: an object with `low`, `high` and `basis`, or `null` together with `range_missing_reason` |
| `range.low`, `range.high` | yes | Finite numbers in the unit of the record, `low` ≤ `high`. A value that is present lies between them |
| `range.basis` | yes | Non-empty text: what the range represents, as the source states it |
| `range_missing_reason` | only when `range` is `null` | Non-empty text. Not allowed next to a range |
| `citation` | yes | An object with `reference` and `locator`. May be `null` only when `value` is `null` |
| `citation.reference` | yes | The full reference of the source, as text |
| `citation.locator` | yes | Where the value is in the source (table, page, equation), so the checker can find it |
| `citation.url` | no | Link or identifier of the source |
| `transcribed_by` | yes | The person who copied the value from the source |
| `checked_by` | yes | The person who checked it against the source. Not the transcriber: case and spacing are ignored in the comparison |
| `note` | no | Free text |

Any other field is rejected, so a misspelt field name cannot pass unnoticed.

### Scope keys (PROPOSED)

`crop`, `stage`, `management`, `soil`, `region`.

This unit defines the keys only. The words allowed under each key are `OPEN` (see below).

Two records are the same record when they have the same `id` and the same `scope`. The comparison ignores case, spacing and the order of the scope keys. A catalogue with two such records is rejected.

### Missing values

A missing value is written `"value": null` with its reason. It stays missing: `read_value` returns a `Missing` object that carries the reason, is not a number, is not equal to zero and fails in arithmetic. A record that leaves the `value` field out is rejected; it is not read as missing. A value of `0` is a value. The same holds for `range` and `read_range`.

### Placeholders

A number cannot carry the word PLACEHOLDER. So a placeholder number appears only inside a record whose identifier, unit, citation and persons all carry the word, and the catalogue check rejects any record that contains it anywhere. An example can be well-formed; it can never pass as a parameter.

A citation that says `CITATION NEEDED` is rejected: it marks an absence, it is not a citation.

## How to add a parameter

1. A person copies the value, its unit, its range and its citation from the source into a new file under `records/`, and signs `transcribed_by`.
2. A second person opens the source at `citation.locator`, checks every number and signs `checked_by`.
3. `python -m pytest params/` passes.
4. The pull request is labelled `science` and a science reviewer accepts it.

## PROPOSED cases

Each case is a test in `test_layout.py` with the same code. All records in the tests are placeholders: their numbers mean nothing. No case contains an expected value of the science.

### Accepted

| Code | Case |
|---|---|
| A1 | A well-formed record with value, range, citation and two different persons is accepted; its value and range are read back unchanged |
| A2 | A record whose value is `null` with a reason is accepted. It is read as `Missing` with that reason: not a number, not equal to zero, and arithmetic on it fails |
| A3 | A record whose range is `null` with a reason is accepted, and the range is read as `Missing` |
| A4 | A value of `0` is accepted and read as the number zero, not as missing |
| A5 | A record whose value is missing may have `"citation": null` |
| A6 | The same `id` with a different scope, or with the empty scope, is a different record |
| A7 | The optional fields `note` and `citation.url` are accepted |
| A8 | The files in `examples/` are well-formed, are all placeholders, and are rejected as a catalogue |
| A9 | Every file under `records/` passes the catalogue check. Today there is none |

### Rejected

| Code | Case |
|---|---|
| R1 | A record without a citation: field absent; `null` next to a value; empty object; plain text instead of an object; no `reference`; no `locator`; blank `reference`; field absent on a missing-value record |
| R1 | A citation that says `CITATION NEEDED`, in any case or spacing |
| R2 | Transcriber and checker are the same person: identical; differing only in case; differing only in spacing |
| R2 | `transcribed_by` or `checked_by` absent, `null`, empty, blank or not text |
| R3 | A value that is `null` without a reason: reason absent, `null`, empty, blank or not text. Reading such a record raises an error; it does not return zero |
| R3 | The `value` field left out. It is not read as missing |
| R3 | A value, zero included, given together with `value_missing_reason` |
| R3 | A value that is not a finite number: text, empty text, `"NA"`, `true`, `false`, NaN, infinity, a list, an object |
| R4 | Two records with the same `id` and the same scope; also when they differ only in the case of the `id`, in the case or spacing of a scope word, or in the order of the scope keys; also two records with the same `id` and the empty scope |
| R4 | A malformed `id`: absent, `null`, empty, starting with a digit, containing a space or `-`, not text |
| R4 | A malformed scope: absent, `null`, not an object, an unknown key, an empty or non-text word |
| R5 | No unit: absent, `null`, empty, blank or not text |
| R5 | A malformed range: `null` without a reason; given together with a reason; not an object; `low` above `high`; the value below `low` or above `high`; no `basis`; a bound that is not a number; a bound left out; an unknown field; the `range` field left out |
| R5 | An unknown field in the record or in the citation |
| R5 | A record that is not a JSON object; an empty `note` |
| R6 | A well-formed record that contains the word PLACEHOLDER is rejected from the catalogue. The word is found in any text of the record, in any case, including field names |
| R7 | A file that is empty, truncated, repeats a key, or holds NaN or Infinity |
| R7 | A folder check reports the unreadable file, the file that is not an object and the malformed record, each with its path; other file types are ignored; a folder that does not exist is a problem |

## OPEN

Questions for a person. None is answered by this unit.

1. **Unify with the conventions sheet** (pull request 8, not in `main`). This unit did not read it. Once accepted, align: how a unit is spelt and how "no unit" is written; how an uncertainty range travels and whether `range.basis` becomes a fixed list of kinds; how a missing value and its reason travel (free text here; a fixed list of reasons there?); whether a record carries a provenance label.
2. **Unify with the validation store** (pull request 9, not in `main`). This unit did not read it. Both record a citation and two persons. Once accepted, align the field names and the shape of the citation, and keep one shared check of "citation present" and "two different persons" instead of two.
3. **How a person is identified.** `transcribed_by` and `checked_by` hold any non-empty text. The repository is public and CI scans for personal names: which identifier is written here?
4. **Scope vocabularies.** Who lists the words allowed under `crop`, `stage`, `management`, `soil` and `region`, and where does the list live? Are these five keys the right ones, and is one missing (for example the model a value belongs to)?
5. **General against specific scope.** When one record has the empty scope and another names a crop, which one does an engine read? This unit only rejects exact duplicates.
6. **Citation on a missing value.** Proposed: optional, because there may be no source to cite. Confirm, or require it always.
7. **Source of a range.** Ranges are fixed by the science reviewers. May a range come from another source than the value, or from a reviewer's judgement? Then it needs its own citation or an explicit "assumption" mark (ground rule 7), which this format does not have.
8. **Value inside its range.** Proposed: a value outside `[low, high]` is rejected. Confirm that no accepted source reports it otherwise.
9. **Link to `ATTRIBUTIONS.md`.** Every publication is also recorded there (ground rule 5). Should `citation` point to that entry instead of repeating the reference?
10. **File names.** The naming convention is not enforced. Enforce it?
