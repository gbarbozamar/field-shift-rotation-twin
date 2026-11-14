# Field identity contract

Status: **PROPOSED** (blueprint section 3.7). Nothing in this folder is in force until people approve the pull request: the interface developer, as producer of the contract, who accepts or contests the [differences from the producer's example](#differences-from-the-producers-example); the platform developer, whose `SiteReference` in `api/rotations.py` this contract is meant to replace later; and the lead developer, as owner of `contracts/`.

This folder holds a Pydantic model and one example of the "field identity" contract: the fields of one case, their names and their geometry.

| Contract | Producer → consumers | Model | Example |
|---|---|---|---|
| Field identity | Interface → the map and site sheet (interface), the site reference of the route (platform), and through it the adapters and the engines | `field_identity.FieldIdentity` | `examples/PLACEHOLDER_field_identity.json` |

The interface developer proposed the shape, the field list and three open questions in issue #103. The lead developer decided around it in issue #77, on 14 November 2026:

- D19: field identity becomes its own contract, proposed by the interface developer from the shape of the example case file, and landed under `contracts/` by a lane L0 builder. Until it is on `main`, the route's `site` stays `SiteReference` and the example case file lives in `web/`.
- D33: the example polygons are synthetic, obviously artificial shapes over a generic rural area; the interface developer confirmed in writing (issue #90) that none follows the boundary of a real parcel.
- D41: a lane L0 builder lands this contract under `contracts/field_identity/`. D33 covers its example too: the same synthetic shapes, with `example_data: true`. A field without geometry is allowed, its geometry missing with `NOT_DECLARED`. The centroid is the interface developer's proposal of a method for the science reviewers; how a polygon becomes one point stays theirs (`adapters/README.md` OPEN 10).

A builder session of lane L0 landed it here (unit `l0/contracts-field-identity`). The example of issue #103 and the example case file `web/src/data/example_case.json` are the source: their fields, names and design choices are kept, except where `contracts/CONVENTIONS.md` or a decision of issue #77 requires otherwise. Identifiers such as C3.1 below refer to that sheet. The decisions are a person's, transcribed by a builder session.

**The example is PLACEHOLDER data.** The three polygons are the synthetic shapes of the example case file in `web/` (D33, D41); every identifier, name and coordinate is illustrative. The example describes no real place, no real field and no real producer, and it says `"example_data": true`.

Acceptance test, from the repository root:

```bash
python -m pytest contracts/field_identity/
```

Models and pure validation only. No network calls, no parameter values, no thresholds, no citations. **No centroid, no area and no point**: nothing here turns a polygon into anything else. The model imports the base model, the `missing` part and the non-blank text from `contracts/inputs/common.py`, as `contracts.inputs.common` (the import path of question Q1 of `contracts/ENTRYPOINTS.md`, answered by `contracts/test_import_path.py`), so the `missing` part is not written a fourth time.

## Layout

| Path | Content |
|---|---|
| `field_identity.py` | `FieldIdentity`, `CaseField` and `PolygonGeometry` |
| `examples/PLACEHOLDER_field_identity.json` | The example |
| `test_examples.py` | The acceptance test |

## Field list

All PROPOSED. Every model rejects unknown members and does not coerce types: a number written as text is rejected. No member of the case, of a field or of its geometry has a default: each one that the example carries is required. The only member that may be left out is `geometry_missing`, which is present exactly when the geometry is null.

### `FieldIdentity`: the fields of one case

| Field | Type | Rule |
|---|---|---|
| `contract` | `"field_identity"` | Required |
| `example_data` | true or false | Required. True for example data |
| `case_id` | text | Required, not blank. The identifier the other contracts use |
| `label` | text | **Required, not blank.** Display label of the case. Issue #103 gives it no rule; see [difference 2](#2-label-and-name-are-required) |
| `fields` | list of `CaseField` | Required, **at least one field**. `field_id` is unique in the list |

### `CaseField`: one field of the case

| Field | Type | Rule |
|---|---|---|
| `field_id` | text | Required, not blank. The identifier the other contracts use |
| `name` | text | **Required, not blank.** Display name of the field, shown by the interface. Issue #103 gives it no rule; see [difference 2](#2-label-and-name-are-required) |
| `geometry` | `PolygonGeometry` or null | Required key. Null only when the geometry is missing (C3.1) |
| `geometry_missing` | `Missing` | Present when `geometry` is null, absent otherwise: never both and never neither (C3.1). Its `reason` is `NOT_DECLARED` (D41); every other code of C3.2 is rejected. `detail` is optional text. See [difference 3](#3-a-field-without-geometry-null-geometry-with-geometry_missing-beside-it) |

### `PolygonGeometry`: a GeoJSON Polygon in WGS 84

What the map draws. Issue #103 says the interface computes the area from it and shows it as `DERIVED`, and that the area is never stored here. On this pull request the producer reports that the interface no longer shows an area (D57 of issue #77: the area stays on screen only with a sourced Earth radius). Either way, no area travels in this contract.

**What is checked**, and nothing else:

- `type` is exactly `"Polygon"`;
- `coordinates` is a list of at least one ring;
- each ring holds at least four positions, and its last position equals its first (the ring is closed);
- each position is exactly two finite numbers: longitude, then latitude, in degrees; longitude between -180 and 180, latitude between -90 and 90, both ends included;
- no other member (`bbox`, `crs` or any other) is accepted.

**What is not checked**: anything else. In particular the winding order of a ring, whether a ring crosses itself, repeated positions inside a ring, a ring with no area, whether a second ring lies inside the first, whether two fields overlap, whether longitude and latitude were written in the wrong order (the example's latitudes, about -33, are valid longitudes too), and the size or the place of the shape. These are listed under [accepted only while a question is open](#accepted-only-while-a-question-is-open).

### `Missing`

The `missing` part of C3.1, from `contracts/inputs/common.py`: `reason` (one of the eight codes of C3.2) and an optional `detail`. Here the reason is restricted to `NOT_DECLARED` by `CaseField`.

### What carries no provenance label

Identifiers, the `example_data` flag, `label`, `name` and the geometry describe the record. They carry no provenance label, source or assumption mark: issue #103 says so, after the line drawn in `contracts/inputs/README.md`. An area derived from the geometry, if the interface shows one again (D57), is labelled `DERIVED` where it is shown. Whether the geometry, which the user draws or uploads, should carry a label is OPEN, question 7.

## PROPOSED cases

Every case below is a change to the example, made in memory. The invalid ones must be rejected; the test also checks that each is rejected for the stated reason, both as Python data and as JSON text. The identifiers are the test identifiers in `test_examples.py`.

### Rejected: the case

| Case | The variant |
|---|---|
| `contract-of-another-name` | `contract` is `"rotation_definition"` |
| `example-data-as-text` | `example_data` is the text `"true"` |
| `case-id-blank` | `case_id` is only white space |
| `label-blank` | `label` is empty |
| `label-null` | `label` is null |
| `case-without-a-field` | `fields` is an empty list |
| `two-fields-share-one-identifier` | The second field has the `field_id` of the first |
| `unknown-member-of-the-case` | The case carries a `centroid`: no point travels in this contract (D41) |

### Rejected: a field

| Case | The variant |
|---|---|
| `field-id-blank` | `field_id` is empty |
| `name-blank` | `name` is only white space |
| `name-null` | `name` is null |
| `unknown-member-of-a-field` | A field carries an `area`: the area is derived, never stored (issue #103) |

### Rejected: a geometry and its missing part

| Case | The variant |
|---|---|
| `geometry-null-without-missing-part` | `geometry` is null and there is no `geometry_missing` (C3.1) |
| `geometry-and-missing-part-both` | A polygon and a `geometry_missing` together (C3.1) |
| `geometry-missing-with-another-reason` | The geometry is missing with reason `NOT_AVAILABLE` (D41 names `NOT_DECLARED`) |
| `geometry-missing-part-without-reason` | `geometry_missing` has no `reason` |
| `geometry-missing-with-reason-code-not-in-the-sheet` | `geometry_missing` has a reason that is not a code of C3.2 |

### Rejected: the polygon

| Case | The variant |
|---|---|
| `geometry-of-another-type` | `type` is `"MultiPolygon"` |
| `geometry-type-in-lower-case` | `type` is `"polygon"` |
| `geometry-with-a-bbox-member` | The geometry carries a `bbox` |
| `geometry-with-a-crs-member` | The geometry carries a `crs` |
| `geometry-without-a-ring` | `coordinates` is an empty list |
| `coordinates-not-nested-in-a-ring` | `coordinates` is a list of positions, not a list of rings |
| `ring-not-closed` | The last position of a ring is removed, so the ring does not end where it starts |
| `ring-with-three-positions` | A position of the triangle is removed: three positions, still closed |
| `ring-empty` | A ring is an empty list |
| `position-with-three-numbers` | A position carries a third number |
| `position-with-one-number` | A position carries one number |
| `longitude-outside-its-range` | A longitude is -181 |
| `latitude-outside-its-range` | A latitude is 91 |
| `coordinate-as-text` | A longitude is written as text |
| `coordinate-as-boolean` | A longitude is `true` |
| `coordinate-not-finite` | A longitude is not a number (NaN) |

### Accepted

These variants stay valid. They show shapes the example does not contain.

| Case | The variant |
|---|---|
| `accepted-field-without-geometry` | The first field's geometry is null with `geometry_missing` `NOT_DECLARED` (D41) |
| `accepted-geometry-missing-with-a-detail` | The same, with a `detail` |
| `accepted-every-field-without-geometry` | Every field's geometry is missing with `NOT_DECLARED`: a case whose fields are registered and not drawn yet |
| `accepted-one-field` | The case holds only its first field (the example of issue #103) |
| `accepted-not-example-data` | `example_data` is false |
| `accepted-polygon-with-a-second-ring` | The first field's polygon has a second ring inside the first: the GeoJSON Polygon structure allows rings after the first, and each is checked like the first |
| `accepted-whole-number-coordinates` | The positions are written as whole numbers |

### Accepted only while a question is open

The model does not reject these variants **only** because it checks structure and nothing else. No case here is a proposal to allow what it shows. If a person decides on a rule, the model gains it and the case becomes a rejected one.

| Case | The variant | Question under OPEN |
|---|---|---|
| `accepted-while-open-ring-wound-the-other-way` | The ring of the first field is written in the opposite order | 5 |
| `accepted-while-open-ring-that-crosses-itself` | The ring of the first field joins its corners across, so it crosses itself | 5 |
| `accepted-while-open-ring-with-no-area` | The ring of the first field has its positions on one line | 5 |
| `accepted-while-open-position-repeated-inside-a-ring` | Two consecutive positions of a ring are the same | 5 |
| `accepted-while-open-second-ring-outside-the-first` | The first field's polygon has a second ring that lies outside the first | 5 |
| `accepted-while-open-longitude-and-latitude-swapped` | Every position of the first field is written latitude first; every number is still inside the range checked | 5 |
| `accepted-while-open-two-fields-with-one-name` | Two fields of the case have the same `name` | 6 |
| `accepted-while-open-overlapping-fields` | The second field has the same polygon as the first | 6 |

### Checked without a case of their own

- No member of the case, of a field or of its geometry can be left out: the test leaves out each one in turn and each variant is rejected.
- A missing geometry with any of the seven codes of C3.2 other than `NOT_DECLARED` is rejected, even with a `detail`.
- The ends of each range are accepted: longitude -180 and 180, latitude -90 and 90.
- The reason `NOT_DECLARED` is one of the codes of C3.2 as the model of `contracts/inputs/` lists them (that folder's test checks its list against the sheet).
- The example of issue #103, as the producer wrote it, is valid; the landed example equals it except for the two further fields of difference 1, and equals the example case file of `web/` with `"contract"` added.

## Differences from the producer's example

For the interface developer, to accept or to contest. The example of issue #103 loads into the model as the producer wrote it; the test holds it, and a copy of the example case file of `web/`, and checks the first difference and no other difference in the example. The other three are rules of the model.

### 1. The example carries the three fields of the example case file

Issue #103 shows one field, `example-field-1` "North field". The landed example carries the three fields of `web/src/data/example_case.json`, with their identifiers, names and polygons unchanged, so that it shows a case with more than one field and a ring of four positions (the triangle, the minimum). D41 allows it: D33 covers this example too. The file is that case file with `"contract": "field_identity"` added (as in issue #103) and laid out over more lines.

### 2. `label` and `name` are required

The field list of issue #103 gives `label` and `fields[].name` no rule, while every other field says "Required". The model requires both, not blank, like every other field. Reasons: the rotation definition requires its `label` (`contracts/rotation_definition/README.md`, field list); the producer's text describes both as what the interface shows; and nothing in the repository describes a case or a field without them. Nothing in the repository was found that argues for leaving either out. If one may be left out, a person says so and the model changes (OPEN, question 4).

### 3. A field without geometry: null `geometry` with `geometry_missing` beside it

Issue #103 proposes (OPEN 2) that a field without geometry is "allowed as missing `NOT_DECLARED`", and D41 decides it, without a shape. The model writes it as the sheet writes a missing value (C3.1: a null value with a `missing` part, never both, never neither), with the `missing` part in a member beside the null, named after the value it belongs to:

```json
{ "field_id": "example-field-1", "name": "North field",
  "geometry": null, "geometry_missing": { "reason": "NOT_DECLARED" } }
```

This follows `range` and `range_missing` in `contracts/inputs/` and `contracts/results/` (C2.2), and `result` and `result_missing` in the route's answer. It cannot travel inside the geometry, as the date of the rotation definition does, because a GeoJSON Polygon has no place for it. The key `geometry` stays, so a consumer knows what is missing (C3.1). The reason is restricted to `NOT_DECLARED`, the one code D41 names (OPEN, question 2).

### 4. No point, no area, no centroid

Issue #103 proposes (OPEN 1) a derived centroid as the point the route takes. D41 makes it a proposal of a method for the science reviewers; how a polygon becomes one point stays theirs (`adapters/README.md` OPEN 10). The model carries no point and computes none, and rejects a `centroid` member on the case and an `area` member on a field (cases `unknown-member-of-the-case`, `unknown-member-of-a-field`).

### Checked and kept

- **The identifiers** `example-case`, `example-field-1`, `example-field-2` and `example-field-3` stay as the producer wrote them, the same `case_id` and `field_id` as the rotation definition example. The examples of `contracts/inputs/` and `contracts/results/` put the word PLACEHOLDER in every identifier; the sheet does not ask for it, so this example was not changed. Here the word is in the file name.
- **The names and the label** stay as the producer wrote them.
- **The coordinates** stay as the producer wrote them. They are synthetic (D33).
- **No provenance label** on identifiers, names or geometry, as issue #103 proposes.

## OPEN

Each item is a question a person has to answer. The role that answers it is named at the end of the item.

### The three questions of issue #103

1. **How does a polygon become one point?** `DECIDED` as to who answers it (issue #77, D41): the centroid is the interface developer's proposal of a method; the question is the science reviewers' (`adapters/README.md` OPEN 10 for climate, OPEN 24 for the elevation model). Nothing in this folder computes a point. For the science reviewers.
2. **A field without geometry.** `DECIDED` (issue #77, D41): allowed, its geometry missing with `NOT_DECLARED`. In the model, with the shape of [difference 3](#3-a-field-without-geometry-null-geometry-with-geometry_missing-beside-it), which is PROPOSED. Still open: is `NOT_DECLARED` the only reason a geometry can be missing? The model rejects the other seven codes of C3.2. For the interface developer.
3. **Relationship to the saved case.** Issue #103 notes that the saved-case contract of sub-lane L2b absorbs or references this one, so the two do not diverge. Not answered here; no saved-case contract is in `contracts/` yet. For the interface developer, as holder of sub-lane L2b.

### Raised by the landing

4. **May `label` or `name` be left out?** The model requires both ([difference 2](#2-label-and-name-are-required)). For the interface developer.
5. **Which geometric rules does a polygon follow?** The model checks the structure listed under `PolygonGeometry` and nothing else. Winding order, rings that cross themselves, rings with no area, repeated positions, rings outside the first, and longitude and latitude in the wrong order are all accepted (the cases "accepted only while a question is open" numbered 5). The three example rings are written in one winding order; the model accepts both. Whether to reject any of these, and whether a position may carry a third number (elevation), which the model rejects, is a choice for the interface developer as producer and the science reviewers as users of the point.
6. **Rules across the fields of a case.** Two fields may have the same `name`, and two polygons may overlap; the model checks only that `field_id` is unique and that the case has at least one field. For the interface developer.
7. **Does the geometry carry a provenance label and a source?** Issue #103 says no, after `contracts/inputs/README.md`; C4.1 gives every value that is not missing a label. The geometry is drawn or uploaded by the user, so `DECLARED` would be its label if it took one. For the lead developer.
8. **Who replaces `SiteReference`, and with what?** D19: `site` stays `SiteReference` (`api/rotations.py`: `case_id`, `field_id`, `latitude`, `longitude`) until this contract is on `main`; replacing it is the platform developer's change in `api/`. Until question 1 is answered there is no rule to turn a field of this contract into the point `SiteReference` carries. For the platform developer.
