import rawClimate from '../data/PLACEHOLDER_site_climate.json'
import rawSoilSlope from '../data/PLACEHOLDER_site_soil_slope.json'
import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'

/**
 * The site data of the site sheet: the two contract examples, copied unchanged
 * from contracts/inputs/examples/ into web/src/data/ (issue #108). The files
 * are the accepted examples of "site_data_climate" and
 * "site_data_soil_slope"; their values are placeholders that describe no real
 * field, and both carry example_data: true, which drives the example banner.
 *
 * The parser below reads exactly the parts the sheet renders, the climate
 * monthly series (the daily series and the point are not rendered by this
 * unit) and the soil-and-slope values, and enforces, on those parts, the
 * rules of the contracts that the value display relies on:
 *
 * - an item holds a value or a missing part with its reason, never both,
 *   never neither (C3.1); zero is a real value, never a stand-in;
 * - a value that is not missing carries a provenance label and a source or
 *   the assumption mark (C4.1, C4.2); a missing one carries neither;
 * - a value holds a range or the reason it has none, never both (C2.2).
 *
 * Pure: value in, typed site data out, or an Error naming what is wrong. The
 * errors are technical codes without wording; nothing user-visible lives here.
 */

/** One month of a monthly series: its calendar position and its value item. */
export interface MonthlyValue {
  year: number
  month: number // C5.1: January is 1 and December is 12
  value: number | null
  missing?: MissingPart
}

/**
 * A monthly climate series. What the series states once for all its present
 * values, unit, provenance, source or assumption mark, and the reason its
 * values carry no range, travels here, on the header (C2.2, C4.1).
 */
export interface MonthlySeries {
  quantity: string
  unit: string
  provenance?: ProvenanceLabel
  source?: string
  assumption?: boolean
  range_missing?: MissingPart
  months: MonthlyValue[]
}

/** The climate example, reduced to the parts the sheet renders. */
export interface SiteClimate {
  example_data: true
  field_id: string
  monthly_series: MonthlySeries[]
}

/** One soil property: a value item identified by its quantity identifier. */
export type SoilProperty = ValueItem & { quantity: string }

/** The soil-and-slope example, reduced to the parts the sheet renders. */
export interface SiteSoilSlope {
  example_data: true
  field_id: string
  slope_length: ValueItem
  slope_steepness: ValueItem
  soil_properties: SoilProperty[]
}

// --- small guards -------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

const REASON_CODES: readonly ReasonCode[] = [
  'NOT_DECLARED',
  'SOURCE_UNAVAILABLE',
  'NO_COVERAGE',
  'MISSING_INPUT',
  'NOT_COMPUTABLE',
  'CONTROL_FAILED',
  'NOT_AVAILABLE',
  'NOT_APPLICABLE',
]

const PROVENANCE_LABELS: readonly ProvenanceLabel[] = [
  'DECLARED',
  'OBSERVED',
  'DERIVED',
  'SIMULATED',
]

function isReasonCode(value: unknown): value is ReasonCode {
  return typeof value === 'string' && (REASON_CODES as readonly string[]).includes(value)
}

function isProvenanceLabel(value: unknown): value is ProvenanceLabel {
  return (
    typeof value === 'string' && (PROVENANCE_LABELS as readonly string[]).includes(value)
  )
}

// --- the missing part (C3.1, C3.2) ----------------------------------------------

function parseMissing(value: unknown, what: string): MissingPart {
  if (!isRecord(value)) {
    throw new Error(`${what}:missing-not-an-object`)
  }
  if (!isReasonCode(value.reason)) {
    throw new Error(`${what}:reason-not-a-code`)
  }
  const missing: MissingPart = { reason: value.reason }
  if (value.detail !== undefined) {
    if (typeof value.detail !== 'string' || value.detail.length === 0) {
      throw new Error(`${what}:detail-empty`)
    }
    missing.detail = value.detail
  }
  return missing
}

// --- the uncertainty range (C2.1) ------------------------------------------------

function parseRange(value: unknown, what: string): UncertaintyRange {
  if (!isRecord(value)) {
    throw new Error(`${what}:range-not-an-object`)
  }
  if (!isFiniteNumber(value.low) || !isFiniteNumber(value.high)) {
    throw new Error(`${what}:range-bounds-not-finite`)
  }
  if (value.low > value.high) {
    throw new Error(`${what}:range-low-above-high`)
  }
  if (typeof value.kind !== 'string' || value.kind.length === 0) {
    throw new Error(`${what}:range-kind-empty`)
  }
  return { low: value.low, high: value.high, kind: value.kind }
}

// --- one value item of the soil-and-slope contract -------------------------------

/** The source of a value, absent when the contract omits it; never empty. */
function readOptionalSource(value: unknown, what: string): string | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${what}:source-empty`)
  }
  return value
}

/**
 * Parse one Value of the contracts: a number with its unit, its provenance
 * label, its source or assumption mark and its range or range reason, or null
 * with a missing part, keeping its unit (C3.1). Every rule enforced here is a
 * rule the contract itself enforces; the example files satisfy all of them.
 */
function parseValueItem(value: unknown, what: string): ValueItem {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (typeof value.unit !== 'string' || value.unit.length === 0) {
    throw new Error(`${what}:unit-empty`)
  }
  const unit = value.unit
  if (value.value === null) {
    if (value.missing === undefined) {
      throw new Error(`${what}:missing-part-absent`)
    }
    if (value.range !== undefined || value.range_missing !== undefined) {
      throw new Error(`${what}:missing-with-range`)
    }
    if (value.provenance !== undefined || value.source !== undefined) {
      throw new Error(`${what}:missing-with-provenance`)
    }
    return { value: null, unit, missing: parseMissing(value.missing, what) }
  }
  if (!isFiniteNumber(value.value)) {
    throw new Error(`${what}:value-not-a-number`)
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:value-and-missing`)
  }
  if (!isProvenanceLabel(value.provenance)) {
    throw new Error(`${what}:provenance-not-a-label`)
  }
  if (value.assumption !== undefined && typeof value.assumption !== 'boolean') {
    throw new Error(`${what}:assumption-not-a-boolean`)
  }
  const source = readOptionalSource(value.source, what)
  const assumption = value.assumption === true
  if (source === undefined && !assumption) {
    throw new Error(`${what}:source-or-assumption-absent`)
  }
  if (value.range !== undefined && value.range_missing !== undefined) {
    throw new Error(`${what}:range-and-range-missing`)
  }
  const range = value.range === undefined ? undefined : parseRange(value.range, what)
  const rangeMissing =
    value.range_missing === undefined
      ? undefined
      : parseMissing(value.range_missing, `${what}:range-missing`)
  if (range === undefined && rangeMissing === undefined) {
    throw new Error(`${what}:range-or-range-missing-absent`)
  }
  return {
    value: value.value,
    unit,
    provenance: value.provenance,
    source,
    assumption: assumption ? true : undefined,
    range,
    range_missing: rangeMissing,
  }
}

// --- one month of a monthly series -------------------------------------------------

function parseMonthlyValue(value: unknown, what: string): MonthlyValue {
  if (!isRecord(value)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (typeof value.year !== 'number' || !Number.isInteger(value.year)) {
    throw new Error(`${what}:year-not-an-integer`)
  }
  if (
    typeof value.month !== 'number' ||
    !Number.isInteger(value.month) ||
    value.month < 1 ||
    value.month > 12
  ) {
    throw new Error(`${what}:month-not-in-1-to-12`)
  }
  if (value.value === null) {
    if (value.missing === undefined) {
      throw new Error(`${what}:missing-part-absent`)
    }
    return {
      year: value.year,
      month: value.month,
      value: null,
      missing: parseMissing(value.missing, what),
    }
  }
  if (!isFiniteNumber(value.value)) {
    throw new Error(`${what}:value-not-a-number`)
  }
  if (value.missing !== undefined) {
    throw new Error(`${what}:value-and-missing`)
  }
  return { year: value.year, month: value.month, value: value.value }
}

// --- a monthly climate series --------------------------------------------------------

function parseMonthlySeries(value: unknown): MonthlySeries {
  if (!isRecord(value)) {
    throw new Error('invalid-site-climate:series-not-an-object')
  }
  if (typeof value.quantity !== 'string' || value.quantity.length === 0) {
    throw new Error('invalid-site-climate:quantity-empty')
  }
  const quantity = value.quantity
  const what = `invalid-series[${quantity}]`
  if (typeof value.unit !== 'string' || value.unit.length === 0) {
    throw new Error(`${what}:unit-empty`)
  }
  const provenance = isProvenanceLabel(value.provenance) ? value.provenance : undefined
  const source =
    typeof value.source === 'string' && value.source.length > 0 ? value.source : undefined
  const assumption = value.assumption === true ? true : undefined
  const range_missing =
    value.range_missing === undefined
      ? undefined
      : parseMissing(value.range_missing, `${what}:range-missing`)
  if (!Array.isArray(value.months) || value.months.length === 0) {
    throw new Error(`${what}:months-not-a-list`)
  }
  const months = value.months.map((month, index) =>
    parseMonthlyValue(month, `${what}:month[${index}]`),
  )
  // What the header states, it states for its present values only: a series
  // with a value carries the label and the source (or the assumption mark)
  // and the reason its values have no range; an all-missing series carries
  // none of them (C2.2, C4.1, C4.2).
  const hasValue = months.some((month) => month.value !== null)
  if (hasValue) {
    if (provenance === undefined) {
      throw new Error(`${what}:provenance-absent`)
    }
    if (source === undefined && assumption !== true) {
      throw new Error(`${what}:source-or-assumption-absent`)
    }
    if (range_missing === undefined) {
      throw new Error(`${what}:range-missing-absent`)
    }
  } else if (provenance !== undefined || assumption !== undefined || range_missing !== undefined) {
    throw new Error(`${what}:header-on-missing-series`)
  }
  return { quantity, unit: value.unit, provenance, source, assumption, range_missing, months }
}

// --- the two examples ------------------------------------------------------------------

/**
 * Parse the climate example. The point and the daily series of the contract
 * are not rendered by this unit, so they are not parsed; the field_id is
 * kept, and the example_data flag must be true, the sheet never shows data
 * that is not labelled as example data.
 */
export function parseSiteClimate(value: unknown): SiteClimate {
  if (!isRecord(value)) {
    throw new Error('invalid-site-climate:not-an-object')
  }
  if (value.contract !== 'site_data_climate') {
    throw new Error('invalid-site-climate:contract-not-site-data-climate')
  }
  if (value.example_data !== true) {
    throw new Error('invalid-site-climate:example-data-not-true')
  }
  if (typeof value.field_id !== 'string' || value.field_id.length === 0) {
    throw new Error('invalid-site-climate:field-id-empty')
  }
  if (!Array.isArray(value.monthly_series)) {
    throw new Error('invalid-site-climate:monthly-series-not-a-list')
  }
  const monthly_series = value.monthly_series.map(parseMonthlySeries)
  const quantities = monthly_series.map((series) => series.quantity)
  if (new Set(quantities).size !== quantities.length) {
    throw new Error('invalid-site-climate:quantity-not-unique')
  }
  return { example_data: true, field_id: value.field_id, monthly_series }
}

/** Parse the soil-and-slope example, on the same terms as the climate one. */
export function parseSiteSoilSlope(value: unknown): SiteSoilSlope {
  if (!isRecord(value)) {
    throw new Error('invalid-site-soil-slope:not-an-object')
  }
  if (value.contract !== 'site_data_soil_slope') {
    throw new Error('invalid-site-soil-slope:contract-not-site-data-soil-slope')
  }
  if (value.example_data !== true) {
    throw new Error('invalid-site-soil-slope:example-data-not-true')
  }
  if (typeof value.field_id !== 'string' || value.field_id.length === 0) {
    throw new Error('invalid-site-soil-slope:field-id-empty')
  }
  if (!Array.isArray(value.soil_properties)) {
    throw new Error('invalid-site-soil-slope:soil-properties-not-a-list')
  }
  const soil_properties = value.soil_properties.map((property): SoilProperty => {
    if (!isRecord(property)) {
      throw new Error('invalid-site-soil-slope:property-not-an-object')
    }
    if (typeof property.quantity !== 'string' || property.quantity.length === 0) {
      throw new Error('invalid-site-soil-slope:property-quantity-empty')
    }
    return {
      quantity: property.quantity,
      ...parseValueItem(property, `invalid-soil[${property.quantity}]`),
    }
  })
  const quantities = soil_properties.map((property) => property.quantity)
  if (new Set(quantities).size !== quantities.length) {
    throw new Error('invalid-site-soil-slope:quantity-not-unique')
  }
  return {
    example_data: true,
    field_id: value.field_id,
    slope_length: parseValueItem(value.slope_length, 'invalid-soil-slope:slope-length'),
    slope_steepness: parseValueItem(value.slope_steepness, 'invalid-soil-slope:slope-steepness'),
    soil_properties,
  }
}

/**
 * The site data of the sheet: the two contract examples, the only site data
 * there is. Their field_id ("PLACEHOLDER-field") is the field of the example
 * contract, not a field of the example case, so it differs from every
 * selection; the sheet therefore shows them under the example banner, which
 * their example_data flag drives, the honest label for example data, for
 * whichever field is selected. When the examples come to carry a field of
 * the example case, the same flag keeps the banner on, as it should.
 */
export const siteClimate: SiteClimate = parseSiteClimate(rawClimate)
export const siteSoilSlope: SiteSoilSlope = parseSiteSoilSlope(rawSoilSlope)
