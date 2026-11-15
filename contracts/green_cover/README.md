# Green-cover strip contract

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the platform developer (sub-lane L2a, producer of the adapter payload), the science reviewers (readers of the strip under the Blueprint section 8 gate), and the lead developer (owner of `contracts/`).

This folder holds strict Pydantic v2 models and one synthetic example of the "green-cover strip" contract for Blueprint Section 8 Gated Extra #2:

| Contract | Producer → consumers | Models | Example |
|---|---|---|---|
| Green-cover strip | Platform adapter (sub-lane L2a, Landsat/Sentinel-2 HLS or MODIS) → Science reviewers / diagnostic views | `models.GreenCoverStrip`, `models.GreenCoverObservation` | `examples/PLACEHOLDER_green_cover.json` |

## Blueprint Section 8 Gate

In `docs/DEVELOPMENT_BLUEPRINT.md` (Section 8, *Gated extras*):

> Started only when the core of the lane is accepted. If not reached, shown as "not available", never with sample values.
>
> **Green-cover strip from Landsat and Sentinel-2 (HLS) or MODIS** — L2 Platform, read by science reviewers — Gate: Sunday 10:00: does the series add evidence?

Accordingly, in the default live flow this contract travels in its gated state (`strip_missing` with reason `NOT_AVAILABLE`, empty `observations`, empty `sources`, never sample values) until science reviewers confirm evidence value and the adapter is enabled.

**The shipped example is PLACEHOLDER data.** All identifiers, dates, indices, and values in `examples/PLACEHOLDER_green_cover.json` are synthetic (`"example_data": true`) and describe no real parcel, satellite pass, or farm.

Acceptance tests, from the repository root:

```bash
python -m pytest contracts/green_cover/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations. Shared parts (`ContractModel`, `IsoDate`, `Missing`, `NonEmptyStr`, `Provenance`, `QuantityId`, `Range`) are imported from `contracts.inputs.common`, never copied.

## Layout

| Path | Content |
|---|---|
| `__init__.py` | Package export of `GreenCoverObservation` and `GreenCoverStrip` |
| `models.py` | `GreenCoverObservation` and `GreenCoverStrip` |
| `examples/PLACEHOLDER_green_cover.json` | Synthetic PLACEHOLDER example |
| `test_examples.py` | Acceptance and README sync tests |
| `test_green_cover_mutants.py` | Validator boundary, round-trip, and mutant-killing tests |

## Field list

All PROPOSED. Every model inherits from `contracts.inputs.common.ContractModel` with `extra="forbid"`, `strict=True`, `frozen=True`, and `allow_inf_nan=False`: unknown fields, type coercion, `NaN`, and `+/-inf` are rejected.

### `GreenCoverStrip`: the green-cover strip of one field of one case

| Field | Type | Rule |
|---|---|---|
| `contract` | `"green_cover_strip"` | Required literal |
| `example_data` | `bool` | Required (`true` for shipped PLACEHOLDER example) |
| `case_id` | `NonEmptyStr` | Required, non-blank |
| `field_id` | `NonEmptyStr` | Required, non-blank |
| `observations` | `tuple[GreenCoverObservation, ...]` | Required; sorted and unique by `(date, sensor_source, quantity_id)`; empty iff `strip_missing` is set |
| `strip_missing` | `Missing \| None` | Optional (default `None`); required when `observations` is empty (C3.1), e.g. `NOT_AVAILABLE` under the Blueprint section 8 gate; `observations` and `sources` must be empty when set |
| `sources` | `tuple[NonEmptyStr, ...]` | Required; sorted, unique, and equal to the distinct `sensor_source` values in `observations` (empty when `strip_missing` is set) |

### `GreenCoverObservation`: one satellite observation

| Field | Type | Rule |
|---|---|---|
| `date` | `IsoDate` | Required `YYYY-MM-DD` Gregorian date (C5.2); datetimes rejected |
| `quantity_id` | `QuantityId` | Required C1.1 identifier (`^[a-z][a-z0-9_]*$`), e.g. `ndvi`, `evi`, `fvc` |
| `value` | `FiniteFloat \| None` | Required key; finite float when present, `null` when missing (never `NaN`/`inf`, never `0` as stand-in, C3.1) |
| `missing` | `Missing \| None` | Present iff `value` is `null` (C3.1); never both and never neither |
| `unit` | `NonEmptyStr` | Required; must equal `"dimensionless"` (C1.1), kept when `value` is `null` (C3.1) |
| `range` | `Range \| None` | Uncertainty range (`low`, `high`, `kind`) in `"dimensionless"` with `low <= value <= high` (C2.1). Present iff `value` is present and `range_missing` is `null`; forbidden when `value` is `null` (C2.2) |
| `range_missing` | `Missing \| None` | Reason the uncertainty range is absent (C2.2). Present iff `value` is present and `range` is `null`; forbidden when `value` is `null` (C2.2) |
| `provenance` | `Provenance \| None` | Required in `{"OBSERVED", "DERIVED"}` when `value` is present (C4.1, C4.3, C4.4); must be `null`/omitted when `value` is `null` (C4.1) |
| `sensor_source` | `NonEmptyStr` | Required, non-blank sensor/product name (e.g. `"Sentinel-2 (HLS)"`, `"Landsat-8 (HLS)"`, `"MODIS (MOD13Q1)"`) |
| `cloud_fraction` | `FiniteFloat \| None` | Optional (default `None`); finite float in `[0.0, 1.0]` when present |
| `cloud_fraction_missing` | `Missing \| None` | Optional explicit `Missing` reason when `cloud_fraction` is `null`; never set together with `cloud_fraction` (C3.1) |

## PROPOSED cases

Every case below mutates `examples/PLACEHOLDER_green_cover.json` in memory and is checked as both Python objects and JSON text in `test_examples.py`.

### Rejected

| Case | The variant |
|---|---|
| `contract-of-another-name` | `contract` is `"field_identity"` |
| `example-data-as-text` | `example_data` is `"true"` |
| `case-id-blank` | `case_id` is only white space |
| `field-id-blank` | `field_id` is empty |
| `unknown-member-of-strip` | Top-level object carries an unknown member |
| `empty-strip-without-strip-missing` | `observations` and `sources` are empty with no `strip_missing` (C3.1) |
| `observations-and-strip-missing-both` | `observations` and `strip_missing` are both set (C3.1) |
| `sources-and-strip-missing-both` | `sources` is non-empty while `strip_missing` is set (C3.1) |
| `observations-unsorted-by-date` | Observations are not sorted by `(date, sensor_source, quantity_id)` |
| `duplicate-observation-same-date-sensor-index` | Two observations share `(date, sensor_source, quantity_id)` |
| `sources-unsorted` | `sources` is not sorted alphabetically |
| `sources-duplicate` | `sources` repeats an entry |
| `sources-mismatch-missing-sensor` | `sources` omits a `sensor_source` present in `observations` |
| `sources-mismatch-extra-sensor` | `sources` includes a source not present in `observations` |
| `observation-unknown-member` | Observation carries an unknown member |
| `observation-datetime-instead-of-date` | `date` carries a time component (C5.2) |
| `observation-quantity-uppercase` | `quantity_id` uses uppercase letters (C1.1) |
| `observation-quantity-hyphenated` | `quantity_id` uses a hyphen instead of underscore (C1.1) |
| `observation-wrong-unit` | `unit` is not `"dimensionless"` (C1.1) |
| `observation-value-as-text` | `value` is text `"0.42"` (no coercion) |
| `observation-value-as-boolean` | `value` is boolean `true` (no coercion) |
| `observation-value-nan` | `value` is `NaN` |
| `observation-value-inf` | `value` is `+inf` |
| `observation-value-and-missing-both` | `value` and `missing` are both present (C3.1) |
| `observation-null-without-missing` | `value` is `null` without `missing` (C3.1) |
| `observation-missing-with-provenance` | Missing observation carries a `provenance` label (C4.1) |
| `observation-present-without-provenance` | Present observation omits `provenance` (C4.1) |
| `observation-present-with-declared-provenance` | Present observation uses `"DECLARED"` |
| `observation-present-with-simulated-provenance` | Present observation uses `"SIMULATED"` |
| `observation-present-without-range-or-range-missing` | Present observation has neither `range` nor `range_missing` (C2.2) |
| `observation-present-with-range-and-range-missing-both` | Present observation has both `range` and `range_missing` (C2.2) |
| `observation-value-outside-range-below-low` | Present observation `value` is below `range.low` (C2.1) |
| `observation-value-outside-range-above-high` | Present observation `value` is above `range.high` (C2.1) |
| `observation-range-low-greater-than-high` | `range.low` is greater than `range.high` (C2.1) |
| `observation-missing-with-range` | Missing observation carries `range` (C2.2) |
| `observation-missing-with-range-missing` | Missing observation carries `range_missing` (C2.2) |
| `observation-sensor-source-blank` | `sensor_source` is blank |
| `observation-cloud-fraction-below-zero` | `cloud_fraction` is `-0.01` |
| `observation-cloud-fraction-above-one` | `cloud_fraction` is `1.01` |
| `observation-cloud-fraction-nan` | `cloud_fraction` is `NaN` |
| `observation-cloud-fraction-and-missing-both` | `cloud_fraction` and `cloud_fraction_missing` are both set (C3.1) |
| `observation-missing-input-without-detail` | `MISSING_INPUT` without `detail` (C3.2) |

### Accepted

| Case | The variant |
|---|---|
| `accepted-gated-not-available-strip` | Gated strip with `observations: []`, `sources: []`, and `strip_missing: {"reason": "NOT_AVAILABLE", ...}` |
| `accepted-not-example-data` | `example_data` is `false` |
| `accepted-same-date-same-sensor-different-indices` | Two indices (`evi`, `ndvi`) from one sensor on one date |
| `accepted-same-date-different-sensors-same-index` | Two sensors on one date for the same index |
| `accepted-cloud-fraction-boundaries` | `cloud_fraction` at exact `0.0` and `1.0` bounds |
| `accepted-value-at-exact-range-bounds` | Present observation `value` equal to `range.low` and to `range.high` (C2.1) |
| `accepted-all-observations-missing-keeps-unit-and-sources` | Every observation missing with `NO_COVERAGE`, keeping `unit: "dimensionless"`, `sensor_source`, and no `range`/`range_missing` |

## OPEN

1. **Evidence gate (Blueprint Section 8).** Does the Landsat/Sentinel-2 (HLS) or MODIS green-cover strip add evidence for the demonstration? For the science reviewers.
2. **Closed index vocabulary.** `quantity_id` currently accepts any C1.1 identifier (`^[a-z][a-z0-9_]*$`), with `ndvi`, `evi`, `fvc` as suggested candidates. Should the vocabulary be closed by the contract? For the science reviewers.
3. **Spatial aggregation and cloud-masking rules.** How a field polygon (`contracts/field_identity/`) is sampled from HLS/MODIS pixels and which cloud-fraction threshold masks an observation stay outside this contract. For the science reviewers and platform developer.
