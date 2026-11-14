# Parameter catalogue

Where crop and rotation parameters are stored, each with its unit, its uncertainty range, its citation, who transcribed it and the person who checked it.

It holds the layout, the record format, the check that rejects a malformed record, and in `records/` the first parameters: the 26 records of the soil-loss value at the demonstration point La Estanzuela (unit l0/first-number), checked by the lead developer under D34 and D66.

> **Status: PROPOSED.** The record format, the scope keys and the test cases below were written by a builder session (blueprint section 3.7). They take effect only when a person approves the pull request. Items marked `OPEN` need an answer from a person.

Values, ranges and citations are science class (blueprint sections 3.5 and 3.6), and a science reviewer accepts them. Who transcribes them is decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622), stated in full in section 3.5 of the blueprint: An AI session may transcribe a value, a unit, a range, an expected result or a citation from a published source, and one person checks it against that source. The transcription is valid only if it carries the full reference, the locator (page, table, equation or example number, or URL with anchor), the verbatim text it comes from, and the date it was read. The person who checks opens the source at the locator, checks every number, and signs the check. A value written by an AI session from memory, without a source opened and quoted, is still a defect.

## Layout

| Path | Content |
|---|---|
| `records/` | The catalogue: one JSON file per parameter record. Today: the records of the demonstration point La Estanzuela |
| `examples/` | Two placeholder records that show the format. Never read as parameters |
| `catalogue.py` | The record checks. Standard library only |
| `test_layout.py` | The acceptance test. It also checks the whole folder: every file under `records/`, and that no record file lies anywhere else |

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
- Nothing is skipped without a message. Every file under `records/` is read: a file that is not a `.json` file is reported, and so is a folder whose name ends in `.json`. The only exception is `records/README.md`.
- A `.json` file anywhere else under `params/`, other than under `examples/`, is reported: it would never be checked or read.
- A file that cannot be read is one problem, and the rest of the folder still loads.

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
| `value` | yes | A finite number, or `null` together with `value_missing_reason`. An integer must be one that a float holds exactly |
| `value_missing_reason` | only when `value` is `null` | Non-empty text. Not allowed next to a value, not even as `null` |
| `unit` | yes | Non-empty text. Also required when the value is missing: the unit the value would have |
| `range` | yes | The uncertainty range: an object with `low`, `high` and `basis`, or `null` together with `range_missing_reason` |
| `range.low`, `range.high` | yes | Finite numbers in the unit of the record, `low` ≤ `high`. An integer must be one that a float holds exactly. A value that is present lies between them |
| `range.basis` | yes | Non-empty text: what the range represents, as the source states it |
| `range_missing_reason` | only when `range` is `null` | Non-empty text. Not allowed next to a range, not even as `null` |
| `citation` | yes | An object with `reference` and `locator`. May be `null` only when `value` and `range` are both `null`: a number needs a citation |
| `citation.reference` | yes | The full reference of the source, as text |
| `citation.locator` | yes | Where the value is in the source (table, page, equation), so the checker can find it |
| `citation.url` | no | Link or identifier of the source |
| `transcribed_by` | yes | Who transcribed the value from the source (D34). What identifies an AI session here is `OPEN` (question 3) |
| `checked_by` | yes | The person who checked it against the source (D34). Not the transcriber: case and spacing are ignored in the comparison |
| `note` | no | Free text |

Any other field is rejected, so a misspelt field name cannot pass unnoticed.

### Scope keys (PROPOSED)

`crop`, `stage`, `management`, `soil`, `region`.

This unit defines the keys only. The words allowed under each key are `OPEN` (see below).

Two records are the same record when they have the same `id` and the same `scope`. The comparison ignores case, spacing and the order of the scope keys. A catalogue with two such records is rejected.

### Missing values

A missing value is written `"value": null` with its reason. It stays missing: `read_value` returns a `Missing` object that carries the reason, is not a number, is not equal to zero and fails in arithmetic. A record that leaves the `value` field out is rejected; it is not read as missing. A value of `0` is a value. The same holds for `range` and `read_range`.

### How numbers are read

The reading functions return floats.

- **An integer** is read from the file exactly. An integer that a float cannot hold exactly, as `value` or as a range bound, is rejected by the record check: reading it would change it silently.
- **A number written with a fraction or an exponent** is read as the nearest float, as JSON readers do. Writing more digits than a float keeps is accepted; the extra digits are not kept.
- At the limits of a float this means: such a number too large for a float is read as infinity and rejected by the record check as not finite; one too small for a float is read as zero and accepted.

### Placeholders

A number cannot carry the word PLACEHOLDER. So a placeholder number appears only inside a record whose identifier, unit, citation and persons all carry the word, and the catalogue check rejects any record that contains it anywhere. An example can be well-formed; it can never pass as a parameter: `read_value` and `read_range` refuse a record that contains the word.

### Unchecked input

Every public function of `catalogue.py` accepts any argument. A function that returns problems reports a bad argument as a problem. `read_value`, `read_range`, `identity` and `parse_record_text` raise `ValueError` and nothing else.

A citation that says `CITATION NEEDED` is rejected: it marks an absence, it is not a citation.

## How to add a parameter

1. The value, its unit, its range and its citation are transcribed from the source into a new file under `records/`, and `transcribed_by` is filled. Decision D34 of [issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622) lets an AI session do it, with the full reference, the locator, the verbatim text and the date read (blueprint section 3.5). `citation.reference` and `citation.locator` hold the first two; the record has no field yet for the verbatim text or the date read (question 13).
2. One person opens the source at `citation.locator`, checks every number and signs `checked_by`.
3. `python -m pytest params/` passes.
4. The pull request is labelled `science` and a science reviewer accepts it.

## PROPOSED cases

Each case is a test in `test_layout.py` with the same code. All records in the tests are placeholders: their numbers mean nothing. No case contains an expected value of the science.

The reading functions refuse a placeholder (F5b). To reach their accepting path, cases A1 to A4 and F2 read a copy of a placeholder fixture in which the word is replaced by `UNMARKED_TEST_ONLY`. The copy exists only in memory while the test runs; no fixture is written without the word (F7).

### Accepted

| Code | Case |
|---|---|
| A1 | A well-formed record with value, range, citation and two different persons is accepted; its value and range are read back unchanged |
| A2 | A record whose value is `null` with a reason is accepted. It is read as `Missing` with that reason: not a number, not equal to zero, and arithmetic on it fails |
| A3 | A record whose range is `null` with a reason is accepted, and the range is read as `Missing` |
| A4 | A value of `0` is accepted and read as the number zero, not as missing |
| A5 | A record whose value and range are both missing may have `"citation": null` (narrowed by F4) |
| A6 | The same `id` with a different scope, or with the empty scope, is a different record |
| A7 | The optional fields `note` and `citation.url` are accepted |
| A8 | The files in `examples/` are well-formed, are all placeholders, and are rejected as a catalogue |
| A9 | The whole `params/` folder of this repository passes the layout check (widened by F3a and F5c), records included |

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
| R7 | A folder check reports the unreadable file, the file that is not an object and the malformed record, each with its path; a folder that does not exist is a problem. The earlier clause "other file types are ignored" is withdrawn: see F3b |

### Fixes (issue 21)

One code per defect of issue 21. Each case failed on the code before the fix.

| Code | Case |
|---|---|
| F1a | A file nested deeply enough to exhaust the parser is one problem for that file, and the other files still load. The placeholder check reads an item of any depth, and an item that contains itself, without failing |
| F1b | A folder whose name ends in `.json` inside the catalogue is one problem; the files inside it and beside it still load |
| F1c | An integer too large for a float, as `value`, `range.low` or `range.high`, is a problem of the record; the checks and the reading functions do not fail on it |
| F2 | An integer that cannot be read back unchanged is rejected: one that a float cannot hold exactly, as `value` or as a range bound. An integer that a float holds exactly, and ordinary number text, are accepted |
| F2b | A decimal written with more digits than a float keeps is accepted and read as the nearest float, in the text of a file and in a whole record file that is loaded, checked and read |
| F3a | A `.json` file directly in `params/`, or in a folder other than `records/` and `examples/`, in any letter case of the extension, is reported |
| F3b | A file inside the catalogue that is not a `.json` file is reported: other extensions, an upper-case extension, no extension, a README in a subfolder. Only the README at the top of the folder is skipped |
| F3c | The duplicate check reports a record it cannot compare (not an object, malformed `id`, malformed `scope`) instead of skipping it. The catalogue check reports such a record once, with the reason |
| F4 | A record whose value is missing and whose citation is `null` is rejected when it carries a numeric range: a range needs a citation. The same record with a citation is accepted. When the range is not an object, only that problem is reported |
| F5a | `value_missing_reason` next to a value, zero included, and `range_missing_reason` next to a range, are rejected even when given as `null` |
| F5b | `read_value` and `read_range` refuse any record that contains the word PLACEHOLDER, with or without a value, in any letter case; no file in `examples/` can be read as a parameter |
| F5c | The check run by the acceptance test reads every file under `records/`: a file that is not a record fails it; a `params/` folder without `records/` is a problem |
| F6 | Every public function, given input it did not check (not an object, wrong types, keys that are not text, huge numbers, a record that contains itself, deep nesting, a path that is not a path), reports a problem or raises `ValueError`, and nothing else. The list of public functions in the test is complete |
| F7 | In `test_layout.py`, every object literal with a field name of the format, every text holding such a field name in quotes, and every call passing a field name to anything but the placeholder builders, carries the word PLACEHOLDER. So does every file in `examples/` |

## OPEN

Questions for a person. None is answered by this unit.

1. **Unify with the conventions sheet** (pull request 8, not in `main`). This unit did not read it. Once accepted, align: how a unit is spelt and how "no unit" is written; how an uncertainty range travels and whether `range.basis` becomes a fixed list of kinds; how a missing value and its reason travel (free text here; a fixed list of reasons there?); whether a record carries a provenance label.
2. **Unify with the validation store** (pull request 9, not in `main`). This unit did not read it. Both record a citation, who transcribed and who checked. Once accepted, align the field names and the shape of the citation, and keep one shared check of "citation present" and "two different persons" instead of two.
3. **How a person, or an AI session, is identified.** `transcribed_by` and `checked_by` hold any non-empty text. The repository is public and CI scans for personal names: which identifier is written here, and what does `transcribed_by` hold when an AI session transcribed the value (D34)?
4. **Scope vocabularies.** Who lists the words allowed under `crop`, `stage`, `management`, `soil` and `region`, and where does the list live? Are these five keys the right ones, and is one missing (for example the model a value belongs to)?
5. **General against specific scope.** When one record has the empty scope and another names a crop, which one does an engine read? This unit only rejects exact duplicates.
6. **Citation on a missing value.** Proposed: optional when the range is missing too, because there may be no source to cite. Confirm, or require it always.
7. **Source of a range.** Ranges are fixed by the science reviewers. May a range come from another source than the value, or from a reviewer's judgement? Then it needs its own citation or an explicit "assumption" mark (ground rule 7), which this format does not have.
8. **Value inside its range.** Proposed: a value outside `[low, high]` is rejected. Confirm that no accepted source reports it otherwise.
9. **Link to `ATTRIBUTIONS.md`.** Every publication is also recorded there (ground rule 5). Should `citation` point to that entry instead of repeating the reference?
10. **File names.** The naming convention is not enforced. Enforce it?
11. **Files that a system or an editor leaves in `records/`.** They are reported like any other file that is not a record (F3b), so the acceptance test fails on a machine that has one. Keep it that way, or name the files that may be skipped?
12. **Testing the readers.** The readers refuse a placeholder and every fixture must carry the word, so the tests read an in-memory copy without it (see "PROPOSED cases"). Accept this, or decide another way to test the accepting path.
13. **Where do the verbatim text and the date read of D34 live?** D34 ([issue #77](https://github.com/gbarbozamar/field-shift-rotation-twin/issues/77#issuecomment-6882095622)) makes a transcription valid only with the full reference, the locator, the verbatim text and the date it was read. The record format has `citation.reference` and `citation.locator` (and `citation.url`, `note`), and no field for the verbatim text or the date. Adding one changes `catalogue.py`, which is not part of this documentation unit. For the lead developer.
