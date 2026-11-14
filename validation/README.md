# Validation store

Where an expected value lives with its source, where a run of the validation protocol is recorded, and where each result is kept, **including the ones that fail**.

> **Status: PROPOSED.** The layout, the record fields, the outcome words and the test cases below were proposed by a builder session (blueprint, section 3.7). They take effect only when a person approves the pull request. The parts that touch how science-class values are recorded also need a science reviewer.
>
> This folder holds **no real expected value, tolerance or citation** yet. Those are written by people (blueprint, sections 3.5 and 3.6). Every example here is a placeholder and says so.

## Layout

| Path | Content |
|---|---|
| `validation/README.md` | This document: layout, record format, proposed cases, open questions |
| `validation/records.py` | The record format in code and the check that rejects a malformed record |
| `validation/test_layout.py` | Acceptance test. Run with `python -m pytest validation/` |
| `validation/test_chain_examples.py` | End-to-end chain on the examples (unit l0/chain-examples, issue #168): the rotation definition example and the chain examples of `contracts/inputs/examples/` through EP2, EP1 and EP3 and the real runner of `api/engines.py`, in process, no network. It shows that the chain is wired; it is not a result. Unlike the rest of this folder it imports the application (`api/`, `engine/`, `params/`), so it needs the project's dependencies, not only the standard library |
| `validation/expected/<id>.json` | One file per **expected value**, with its citation and the two persons who transcribed and checked it |
| `validation/runs/<id>.json` | One file per **protocol run** |
| `validation/results/<id>.json` | One file per **result** of one test in one run, whatever its outcome |
| `validation/examples/` | A second, separate store with the same three folders, holding placeholder records only |

`expected/`, `runs/` and `results/` do not exist yet: each is created by the first unit that stores a record in it. A folder that does not exist holds no record.

Each of the three folders holds only files named `<id>.json`. Anything else in them is reported as a problem, including a file whose name starts with a dot and a directory whose name ends in `.json`.

The extension is read without regard to case, so `<id>.JSON` is a record file too. The name before the extension is the id, letter for letter. Where a file system allows two files that carry the same id, such as `<id>.json` and `<id>.JSON`, both are rejected: neither replaces the other.

A `.json` file anywhere else below the root of a store is reported as a problem too, so a record saved in a misnamed folder such as `result/` is not lost. Exactly two things are not looked at:

- the folder `examples/` directly below the root, because it is a separate store;
- outside the three folders, files that are not `.json` files, such as this document and the Python files.

## Record format (PROPOSED)

A record is one JSON object in one UTF-8 file. The file name is the `id` of the record followed by `.json`. A file that starts with a byte-order mark, as editors on Windows write it by default, is read as valid.

Rules that hold for every record:

- A field that is not listed below is rejected, so a misspelt field cannot hide a missing one.
- A field written twice in the same file is rejected.
- `NaN` and `Infinity` are rejected.
- **An integer that would change when read is rejected** (PROPOSED). Engines and other readers of a JSON file hold a number as a float. An integer that a float cannot hold exactly, such as `9007199254740993` or `100000000000000000000000`, is reported as a problem in its field; it is never rounded silently. This rule is about integers only, that is, numbers written without a decimal point and without an exponent. A number written with a decimal point or an exponent is read as the float it denotes, as any JSON reader does, and is not checked for the digits it loses: `0.10000000000000001` is the same number as `0.1`, `1e23` and `12345678901234567890.0` are accepted, and `1e-400` is read as zero. A number that a float reads as infinity, such as `1e400`, is rejected like `Infinity`.
- **A missing value is always written `{"missing_reason": "<why>"}`.** It is never `null`, never left out and never zero.
- A record that contains the word `PLACEHOLDER` anywhere is rejected in the real store. Placeholders are accepted only where the caller asks for them, as the examples store and the tests do.

### Fields of every record

| Field | Type | Meaning |
|---|---|---|
| `format_version` | integer | `1` |
| `kind` | string | `expected_value`, `protocol_run` or `result` |
| `id` | string | Unique within its kind. Starts with a letter or a digit; only letters, digits, `.`, `_` and `-` |
| `notes` | string, optional | Free remarks |

### A value slot

Used by `value` of an expected value and by `observed` of a result. Exactly one of:

| Form | Meaning |
|---|---|
| `{"number": <finite number>, "unit": "<unit>"}` | A number always travels with its unit. The unit is a plain string for now (see OPEN 1) |
| `{"text": "<wording>"}` | A value that is not a number, such as a decision state or an order between systems |
| `{"missing_reason": "<why>"}` | The value is missing |

### Test codes

A test code is a family letter `E`, `H` or `D`, a number and an optional lower-case letter, as the codes appear in section 8 of the blueprint: `E3`, `E1b`, `H10`, `D12`. The check looks at the form only. It does not know which codes exist in `docs/VALIDATION.md` (see OPEN 4).

### (a) Expected value: `expected/<id>.json`

| Field | Type | Meaning |
|---|---|---|
| `test_code` | string | The test of the protocol this value belongs to |
| `quantity` | string | What the value is, in words |
| `value` | value slot | The expected value as written in the source |
| `tolerance` | object | Required when `value` is a number, not allowed otherwise. Exactly one of `{"absolute": <number ≥ 0>}`, in the unit of the value; `{"relative": <number ≥ 0>}`, as a fraction of the expected value; `{"missing_reason": "<why>"}`. A tolerance is never assumed |
| `citation` | object | `reference`: the source, written in full. `locator`: where in the source the value is found (page, table, equation, example). `url`: optional. A text marked `CITATION NEEDED` is not a citation and is rejected |
| `transcribed_by` | string | The person who wrote the value from the source |
| `checked_by` | string | The second person, who checked the value against the source. Must not be the same person: two spellings that differ only in upper or lower case or in spacing count as the same person |

A record without `checked_by` is not accepted: an expected value enters the store only when the second person has checked it.

Reminders that this check cannot enforce: the source also goes into `ATTRIBUTIONS.md` when it is first used; a value, a tolerance or a citation written by an AI session is a defect; a pull request that adds or changes an expected value is science-class and needs a science reviewer.

```json
{
  "format_version": 1,
  "kind": "expected_value",
  "id": "PLACEHOLDER-expected-number",
  "test_code": "E999",
  "quantity": "PLACEHOLDER quantity",
  "value": { "number": 123456789.0, "unit": "PLACEHOLDER unit" },
  "tolerance": { "absolute": 987654321.0 },
  "citation": {
    "reference": "PLACEHOLDER citation, not a real source",
    "locator": "PLACEHOLDER locator"
  },
  "transcribed_by": "PLACEHOLDER person A",
  "checked_by": "PLACEHOLDER person B"
}
```

### (b) Protocol run: `runs/<id>.json`

| Field | Type | Meaning |
|---|---|---|
| `protocol` | string | Which version of the protocol was run |
| `code_version` | string | The commit the run was made on |
| `run_at` | string | UTC time, written `YYYY-MM-DDTHH:MM:SSZ` |
| `run_by` | string | Who or what launched the run |
| `test_codes` | list of strings | The tests this run set out to execute. Not empty, no code twice |

```json
{
  "format_version": 1,
  "kind": "protocol_run",
  "id": "PLACEHOLDER-run",
  "protocol": "PLACEHOLDER protocol version",
  "code_version": "PLACEHOLDER commit",
  "run_at": "1900-01-01T00:00:00Z",
  "run_by": "PLACEHOLDER person A",
  "test_codes": ["E999", "H999", "D999"]
}
```

### (c) Result: `results/<id>.json`

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | The `id` of the protocol run this result belongs to |
| `test_code` | string | The test. Must be listed in `test_codes` of that run |
| `expected` | object | `{"id": "<id of an expected value>"}`, which must belong to the same test; or `{"missing_reason": "<why>"}` when the test has no external expected value, such as an invariant |
| `outcome` | string | `passed`, `failed` or `not_evaluated` |
| `observed` | value slot | What was obtained. Always present; when nothing was obtained it says why |
| `reason` | string | Required when the outcome is `not_evaluated`, not allowed otherwise |

Outcome words (PROPOSED):

| Word | Meaning | What the record must hold |
|---|---|---|
| `passed` | The test ran and the expectation held | An observed value that is not missing |
| `failed` | The test ran and the expectation did not hold, or the code under test stopped before giving a value | An observed value, or the reason why there is none |
| `not_evaluated` | The comparison was not made | `reason`. This is the only outcome allowed when the expected value it points to is missing |

A failed result is a well-formed record. It is stored like any other and it is reported as failed.

```json
{
  "format_version": 1,
  "kind": "result",
  "id": "PLACEHOLDER-result-failed",
  "run_id": "PLACEHOLDER-run",
  "test_code": "D999",
  "expected": { "id": "PLACEHOLDER-expected-text" },
  "outcome": "failed",
  "observed": { "text": "PLACEHOLDER observed wording" }
}
```

## The check

`validation/records.py`, standard library only, no network.

| Function | What it does |
|---|---|
| `check_record(record, allow_placeholders=False)` | Returns every problem of one record as a list of sentences. An empty list means the record is accepted. Accepts any object and never raises |
| `is_placeholder(record)` | Says whether the word PLACEHOLDER appears anywhere in a record. Accepts any object and never raises |
| `load_store(root, allow_placeholders=False)` | Reads the three folders below `root`, checks every file, then checks what each result points to. Returns the accepted records by id, every problem with its file path, and under `unresolved` the well-formed results whose references are broken. One file that cannot be read, such as one nested too deeply, is listed as a problem and the rest still loads. Raises `TypeError`, and nothing else, when `root` is not a path |
| `check_references(expected, runs, results)` | Checks what each result points to. Given a record that was not checked before, it reports a problem and does not raise. Raises `ValueError`, and nothing else, when one of its three arguments is not a dict |
| `summarise(store)` | Counts the results by outcome, lists the failed and the not-evaluated ones by id, lists under `broken_references` every well-formed result whose references are broken, lists under `failed_malformed` every rejected file that says its outcome is failed, lists under `no_result` every test that a run lists without a counted result, and lists under `rejected` every file that was rejected. Raises `ValueError`, and nothing else, when it is not given a store whose records are well-formed, as `load_store` returns it |

Nothing is dropped silently: a malformed record is left out of the accepted ones and is listed with its path and the reason; a failed result is counted and listed as failed.

A result whose references are broken (PROPOSED): a result can be well-formed on its own while the run or the expected value it points to is missing or was rejected. Such a result is not among the accepted ones, its file is listed under `rejected`, and it is listed under `broken_references` with its outcome. If its outcome is `failed`, it is **also counted and listed as failed**: a failure is never hidden by a broken reference. With any other outcome it is not counted: a pass that cannot be traced to its run and its expected value is not a pass. `results_total` is the number of results counted under an outcome.

A malformed record that says failed (PROPOSED): a file in any of the three folders that is rejected for any reason, and whose record says that its outcome is failed, is listed by its path under `failed_malformed` and is **counted as failed**, so `counts.failed` is the length of `failed` plus the length of `failed_malformed`. Upper or lower case and surrounding spaces do not matter for this: `FAILED` is still not an allowed outcome word and the record is still rejected, but it does not hide a failure. Nothing else of such a record is trusted, so its test stays under `no_result`. Two limits: a file that cannot be read as JSON cannot say anything, and a `.json` file outside the three folders is reported but not opened; both appear only under `rejected`.

`python -m pytest validation/` also checks the real store (case S05), so a malformed record added to `expected/`, `runs/` or `results/` makes the acceptance test fail.

Reading an expected value from a test of an engine, with the repository root as working directory:

```python
from validation import records

store = records.load_store(records.STORE_ROOT)
record = store.expected["<id>"]   # KeyError when the record is missing or was rejected
```

What this check does **not** do: it does not run any test of the protocol, it does not compare an observed value with an expected one, and it does not decide an outcome. It checks only that what is written is well-formed and consistent.

## PROPOSED cases

For a person to approve. The code in the first column is the start of the test id in `validation/test_layout.py`. Every record used by the cases is a placeholder.

### Accepted

| Case | A well-formed record that is accepted |
|---|---|
| A01 | Expected value, a number with an absolute tolerance |
| A02 | Expected value, a number with a relative tolerance |
| A03 | Expected value, a number whose tolerance is missing with its reason |
| A04 | Expected value, a text |
| A05 | Expected value whose value is missing with its reason; citation and both persons still required |
| A06 | Expected value with the optional `url` of the citation and `notes` |
| A07 | Protocol run |
| A08 | Result, passed |
| A09 | Result, failed, with an observed value |
| A10 | Result, failed, with the observed value missing and its reason |
| A11 | Result, not evaluated, with its reason |
| A12 | Result of a test without an external expected value, with the reason |

### Rejected

| Case | A malformed record that is rejected |
|---|---|
| R01 | Expected value without a citation |
| R02 | Expected value whose citation is `null` |
| R03 | Expected value whose citation reference is blank |
| R04 | Expected value whose citation is marked `CITATION NEEDED` |
| R05 | Expected value whose citation has no locator |
| R06 | Expected value whose transcriber and checker are the same person |
| R07 | The same, when the two names differ only in case and spacing |
| R08 | Expected value without a checker |
| R09 | Expected value without a transcriber |
| R10 | Expected value whose checker is an empty string |
| R11 | Expected number without a unit |
| R12 | Expected number written as a string |
| R13 | Expected number that is a boolean |
| R14 | Expected number that is not finite |
| R15 | Expected value that is `null` |
| R16 | Expected value that is a number and a text at once |
| R17 | Expected value that is missing without a reason |
| R18 | Expected number without a tolerance |
| R19 | Negative tolerance |
| R20 | Tolerance that is absolute and relative at once |
| R21 | Expected text that carries a tolerance |
| R22 | Test code outside the families E, H and D |
| R23 | Test code with a lower-case family letter |
| R24 | A field that the format does not have (a misspelt `citation`) |
| R25 | A kind that the format does not have |
| R26 | A format version other than 1 |
| R27 | An id that contains a path separator |
| R28 | Expected value without `quantity` |
| R29 | Run time without a time zone |
| R30 | Run time with an offset instead of UTC |
| R31 | Run time on a date that does not exist |
| R32 | Run with an empty list of test codes |
| R33 | Run that lists a test code twice |
| R34 | Run that lists a malformed test code |
| R35 | Run without a code version |
| R36 | Result whose outcome is a word that is not allowed (`ok`) |
| R37 | Result whose outcome is an allowed word in another case (`FAILED`) |
| R38 | Result without an outcome |
| R39 | Result marked passed without an observed value |
| R40 | Result without `observed` |
| R41 | Result not evaluated without a reason |
| R42 | Result passed that carries `reason` |
| R43 | Result whose `expected` is neither an id nor a reason |
| R44 | Result without a run id |
| R45 | A record that is a list, not an object |
| R46 | A placeholder record, unless placeholders are explicitly allowed |
| R47 | A record with two faults reports both, not only the first |
| R48 | `check_references` given records that were not checked (a result without `run_id`, `expected` or `outcome`, with a `run_id` that is not a text, that is not an object, or of another kind; a malformed run; a malformed expected value) reports a problem for each and does not raise |
| R49 | An integer too large for a float (10 to the power 400, positive or negative) as an expected number, an observed number, an absolute or a relative tolerance is reported as one problem in that field; the check does not raise |
| R50 | An integer that a float cannot hold exactly (2 to the power 53, plus 1) is reported in each of the same four fields; integers and numbers that a float holds exactly are accepted |
| R51 | `check_record` and `is_placeholder` accept anything without raising: every well-formed record with each field dropped or replaced by each of 27 unexpected values (among them `null`, numbers too long to print, lists 5 000 deep, a list that holds itself, objects that are not JSON), and those values on their own |
| R52 | `check_references` reports a problem for every such record and raises only `ValueError`, and only when one of its three arguments is not a dict |
| R53 | Every fixture that looks like a record carries the word PLACEHOLDER: the records built in the test file, every file under `examples/`, and every file a test writes, which all go through one helper that refuses a content without the word; the check that the helper refuses uses pytest's temporary folder |

### Store on disk

| Case | Behaviour |
|---|---|
| S01 | A failed result is stored, accepted and reported as failed; the counts add up to the number of results |
| S02 | A store with only failed results reports all of them |
| S03 | `validation/examples/` holds an accepted record of each kind and a result of each outcome |
| S04 | Every example is a placeholder, and the real store refuses all of them |
| S05 | The real store has no malformed record (it is empty today) |
| S06 | Folders that do not exist yet mean an empty store, not an error |
| S07 | A file that is not valid JSON is listed with its path, and the other records still load |
| S08 | A file that writes the same field twice is rejected |
| S09 | A file that writes `NaN` is rejected |
| S10 | A record in the folder of another kind is rejected |
| S11 | A file whose name differs from the id of its record is rejected |
| S12 | A file in a record folder that is not a `.json` file is listed |
| S13 | A result that points to a run that does not exist is rejected and listed |
| S14 | A result that points to an expected value that does not exist is rejected |
| S15 | A result for a test that its run does not list is rejected |
| S16 | A result that points to the expected value of another test is rejected |
| S17 | A result cannot be passed or failed against an expected value that is missing |
| S18 | A test that a run lists and that has no result is reported under `no_result` |
| S19 | A malformed failed result is rejected, and is still counted as failed and listed under `failed_malformed`; its test stays under `no_result` |
| S20 | A file that holds a list instead of an object is rejected |
| S21 | A failed result whose run record was rejected is still counted and listed as failed, and is listed under `broken_references` and `rejected` |
| S22 | A failed result whose expected-value record was rejected is still counted and listed as failed, and is listed under `broken_references` and `rejected` |
| S23 | A passed result with a broken reference is listed under `broken_references` with its outcome and is not counted as passed |
| S24 | A record in a misnamed folder (`result/` instead of `results/`) is listed as a problem |
| S25 | A file in a record folder whose name starts with a dot is listed as a problem, whether or not it ends in `.json` |
| S26 | A `.json` file at the root of the store or in any other folder is listed; `examples/` below the root and files that are not `.json` outside the three folders are not looked at |
| S27 | A deeply nested file (500, 5 000 and 100 000 levels) is listed as a problem, whether it is too deep to be read at all or is read and then rejected for its form; the rest of the store still loads |
| S28 | Every rejected file that says failed is counted as failed: an outcome written ` FAILED `, a failed result under a file name that is not its id, a failed result in the folder of another kind, a failed result with a deeply nested list where a wording is expected. A rejected result that says passed, and a file that is not valid JSON, are not counted |
| S29 | A file saved as UTF-8 with a byte-order mark is read as valid |
| S30 | A record file whose extension differs only in letter case (`.JSON`, `.Json`) is read as a record; the name before the extension must still be the id, letter for letter |
| S31 | Two files of one folder that carry the same id are both rejected, whichever is listed first; a failed result among them is still counted as failed |
| S32 | A directory whose name looks like a record file, in each of the three folders, is listed as a problem; the loader does not raise and the rest still loads |
| S33 | An integer in a file that would change when read (one above the last that a float holds exactly, one too large for a float, one with more digits than Python converts) is reported in its field, in a value, a tolerance and an observed value; integers that a float holds exactly are accepted and stay integers; a number written with a decimal point or an exponent is accepted as the float it denotes, whatever its digits; a failed result that holds such an integer is still counted as failed |
| S34 | `summarise` raises only `ValueError` when it is given anything that is not a store of well-formed records, a store object that was never initialised included, and works on a sound store built by hand; `load_store` raises only `TypeError` when `root` is not a path, and a path that does not exist is an empty store |
| S35 | A passed result whose observed number is written with more digits than a float keeps (`0.10000000000000001`, `1e23`, `12345678901234567890.0`) is accepted, counted as passed, and its test is not listed under `no_result` |

One more test, without a case code, checks that every case code above appears in this section.

### Chain of the examples (`test_chain_examples.py`)

The code is the start of the test name. Every number in the examples and in the test catalogue is PLACEHOLDER; no case holds an expected value of the science. The agricultural years are computed in the test, day by day, from the dates of the series and the start month of the rotation definition example (C5.3, D47). A test without a case code checks that every code below appears in this section.

| Case | What is checked |
|---|---|
| CH01 | Each chain example loads into its contract model with nothing added, dropped or changed, carries `example_data: true`, and names exactly the `case_id` and `field_id` of the rotation definition example |
| CH02 | The climate example covers every day of at least one whole agricultural year (D47, start month of the rotation definition example) for every daily quantity EP1 and EP3 read, with no day missing, all in one time zone (C6.3) |
| CH03 | The example values are plainly PLACEHOLDER: every daily series holds the same number on every day, every source starts with the word PLACEHOLDER, every point source says it is not a real place, and the point carries the unit strings of D55 (`degree`, `degree`, `m`), the ones EP3 accepts |
| CH04 | The runner finds EP2, EP1 and EP3 at their paths of `contracts/ENTRYPOINTS.md` (none is "not built"), calls them once each in that order on the calendar EP2 built and the two examples, and passes EP1 the catalogue object it was given; the calendar is feasible and names the rotation example's case and field |
| CH05 | With the empty catalogue `{}`: a `ResultsPerRotation` that survives a JSON round trip; soil loss and water exposure are each the engine's output, not the not-built form, with one item per agricultural year of the record; every value is missing with its reason, none is an identity absence (site data of another field), none is `NO_COVERAGE` in a covered year; the annual soil loss names every parameter EP1 reads; in each of CH05 and CH06 the water exposure of a covered year is `MISSING_INPUT` and not a unit refusal, naming every site parameter of EP3 as having no record (D56), the unknown crop of the day (Q5) and the incomplete definition of the indicator (C1.4, D61); the runner passes the output of EP1 and of EP3 unchanged |
| CH06 | With a complete PLACEHOLDER catalogue that passes `params.catalogue.check_catalogue` (and whose marked copy does not): every record the main route of EP1 reads, the twelve monthly erosivity records included. Through the runner (decisions D69 and D84 of issue #77, USER-G; `engine/erosion/SOIL_LOSS.md`): the annual soil loss of each covered year is a number equal to `engine/erosion/equation.py` applied to the mean annual level of R, K, LS through `engine/erosion/ls.py`, the declared C and P, provenance `DERIVED`, a source naming the records and `DECLARED`; each month of a covered year is the level times the share of its calendar month in the twelve monthly records, times K, LS, C and P, computed again in the test, and the twelve add up to the year (C1.2); the erosion module is `available`; the runner passes EP1's output unchanged. EP3 gives no number (C1.4, D61), so its reason is asserted instead: every item missing, not `NO_COVERAGE` in a covered year, not an identity absence, and equal to EP3's own output for the same arguments |
| CH07 | Through `POST /api/rotations/run` of `api.main.create_app` (its default engines, the catalogue passed as `parameters`), with each of the two catalogues: `200`, and the `result` loads into `ResultsPerRotation` and equals the runner's |

## OPEN

Questions a person has to answer. The builder session did not decide them.

1. **Units.** A unit is stored as a plain string and is not interpreted. Once `contracts/CONVENTIONS.md` is accepted: which unit strings are allowed, how "no unit" is written, and whether the check must refuse a result whose observed unit differs from the unit of its expected value.
2. **Other conventions to align once the sheet is accepted:** how a missing value and its reason travel (here `{"missing_reason": ...}`), how an uncertainty range travels with a value (this format has only `tolerance`), the provenance label of a value, and the time format (here UTC, `YYYY-MM-DDTHH:MM:SSZ`).
3. **How a person is identified** in `transcribed_by`, `checked_by` and `run_by`. Continuous integration scans for personal names, so a full name may not be acceptable: repository handle, initials or role? The check compares the two strings only; it cannot know that two different strings are one person, or that a string is a person at all.
4. **Test codes.** The check accepts any code of the form described above. Should it read the list of codes from `docs/VALIDATION.md` once the science reviewers have written it?
5. **Tolerance.** Is "absolute, in the unit of the value" and "relative, as a fraction of the expected value" the meaning the science reviewers want? Is a tolerance of exactly zero allowed? Should a text value be compared exactly?
6. **Recomputing the outcome.** Should the check recompute `passed` or `failed` from the observed value, the expected value and the tolerance, and reject a result that contradicts it? Not done here: it depends on questions 1 and 5.
7. **Inputs of a worked example.** An expected value usually holds for given inputs, which are also transcribed from the source. Where do they live: in the expected-value record, or in a contract example? This format has no field for them.
8. **Values that are not one number or one wording,** such as an order between several systems or a table. Is `text` enough or is a structured form needed?
9. **Outcome words.** Are three words enough? In this proposal, code that stops with an error counts as `failed`. Is a separate word needed for it?
10. **One file per result, in one flat folder.** Is this still workable when a full protocol run writes many results, or should results be grouped by run?
11. **Package name and working directory.** Tests import this folder as the package `validation`, which works when pytest runs from the repository root. A root dependency manifest, which this unit may not write, would fix this for every lane.

### Chain of the examples

Raised by unit l0/chain-examples (issue #168). The builder session did not decide them.

12. **The chain test imports the application.** This folder was standard library only; `test_chain_examples.py` imports `api/`, `engine/`, `params/`, pydantic and FastAPI, because the brief places it here. Should it stay here or move to a folder of end-to-end tests? *Lead developer; platform developer.*
13. **The length unit of the chain soil example, `example_length_unit`, does not carry the word PLACEHOLDER.** The catalogue refuses the word in a record, and `engine/erosion/ls.py` requires the unit-length record to carry exactly the slope length's unit string, so a marked string could never match a record that passes the check. Is an unmarked, unreal unit string acceptable in an example, or should both carry a decided length unit? *Lead developer; science reviewers.*
14. **The steepness unit of the chain soil example is `percent`**, the string EP1 reads as `ls.SlopeUnit.PERCENT` (EP1's PROPOSED reading; question 18 of `contracts/inputs/README.md` is open). *Science reviewers; lead developer.*
15. **The climate series of the chain example use the unit strings of `contracts/CLIMATE_QUANTITIES.md`** with plainly unreal numbers, so that a unit guard (EP3 of #165) does not stand in for the reason a value is missing. Should an example carry decided unit strings next to numbers that are not data? *Lead developer.*
16. **The calendar and the record do not overlap.** The calendar EP2 builds from the rotation definition example runs from 2027 to 2028; the climate example covers 2001 to 2002. EP1 and EP3 lay out the years of the record (D47) whatever the calendar's dates, and how the rotation is repeated over the years of the record is not decided (Q5 of `contracts/ENTRYPOINTS.md`, OPEN 2 of `engine/erosion/SOIL_LOSS.md`). Because of it EP3 knows no crop on any day of the record, so even a complete water catalogue would leave every year `MISSING_INPUT` and never reach `NOT_AVAILABLE` under D61. The chain test asserts that EP3 names this. *Lead developer.*
17. **No soil property in the chain soil example.** EP1 reads K from the catalogue, not from the soil data; whether K should come from the soil tables (D48) is OPEN 13 of `engine/erosion/SOIL_LOSS.md`. *Lead developer; platform developer.*
18. ~~The point of the chain climate example keeps the placeholder unit.~~ `DECIDED`: the point carries the unit strings of D55 (`degree`, `degree`, `m`), unit l0/fix-chain-test, at the orchestrator's request with the lead developer's authorization. The numbers stay 1.0, 2.0 and 3.0, so they now name a point at sea; whether other illustrative numbers are wanted is still open. *Lead developer.*
19. **Serving the chain soil example in the running app** (`SOIL_SLOPE_EXAMPLE_FILE`, D38) is not part of this unit; which file holds the demonstration values is a person's decision. *Platform developer; lead developer.*

## Environment

Provisional environment (blueprint, section 4): Python 3.12 and pytest; standard library otherwise. This folder adds no dependency.
