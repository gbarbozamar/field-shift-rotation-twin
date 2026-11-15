import rawTable from '../data/PLACEHOLDER_results_table.json'
import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'

/**
 * The data of the two clocks: the results-table contract example, copied
 * unchanged from contracts/results/examples/ into web/src/data/ (issue #140).
 * Its values are placeholders written by hand; no engine produced them, and
 * its field is not a field of the example case. The example file carries no
 * example_data flag (the contract has none), so the clocks treat everything
 * in it as example data by construction and always show it under the example
 * banner, which carries that honesty.
 *
 * The parser below reads exactly the parts the clocks render — the rows of
 * the soil-loss and water-deficit-exposure indicators, placed on a rotation
 * and, for an agricultural-year row, on its year — and enforces, on those
 * parts, the rules of the contract that the shared value display relies on:
 *
 * - a row holds a value or a missing part with its reason, never both,
 *   never neither (C3.1); zero is a real value, never a stand-in for an
 *   absence;
 * - a value that is not missing carries a provenance label and a source or
 *   the assumption mark (C4.1, C4.2); a missing one carries neither;
 * - a value holds a range or the reason it has none, never both (C2.2);
 * - a row on the time basis ag_year carries its agricultural year, a row on
 *   the time basis rotation carries none (W1); soil loss travels per
 *   agricultural year and the carbon trend per rotation (T3).
 *
 * The monthly breakdown of results per rotation, the carbon rows of the
 * table and the wholly-missing not-built form are not rendered by this
 * unit; their example files sit beside this one for the units that will.
 *
 * Pure: value in, typed table out, or an Error naming what is wrong. The
 * errors are technical codes without wording; nothing user-visible lives
 * here.
 */

/** The time bases a row of the table can sit on (contract "Results table"). */
export type TimeBasis = 'ag_year' | 'rotation'

/** The three indicators of the results contracts (C1.1). */
export type IndicatorId = 'soil_loss' | 'water_deficit_exposure' | 'soil_carbon_trend'

/**
 * One row of the results table: a value item placed on a rotation and a
 * scenario, on the time basis ag_year (with its year) or rotation. The
 * carbon fields of a soil_carbon_trend row are read only enough to know
 * they are well formed; this unit renders none of them.
 */
export type ClockRow = ValueItem & {
  rotation_id: string
  scenario_id: string
  indicator: IndicatorId
  time_basis: TimeBasis
  ag_year?: number
}

/** The results-table example, reduced to the parts the clocks render. */
export interface ResultsTableExample {
  case_id: string
  field_id: string
  rows: ClockRow[]
}

/**
 * The two clocks of one rotation: the soil-loss rows of the rotation, one
 * per agricultural year in year order, and the water-deficit-exposure rows
 * in table order (the contract fixes one time basis for all of them).
 */
export interface RotationClocks {
  rotation_id: string
  soil: ClockRow[]
  water: ClockRow[]
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

const TIME_BASES: readonly TimeBasis[] = ['ag_year', 'rotation']

const INDICATOR_IDS: readonly IndicatorId[] = [
  'soil_loss',
  'water_deficit_exposure',
  'soil_carbon_trend',
]

function isReasonCode(value: unknown): value is ReasonCode {
  return typeof value === 'string' && (REASON_CODES as readonly string[]).includes(value)
}

function isProvenanceLabel(value: unknown): value is ProvenanceLabel {
  return (
    typeof value === 'string' && (PROVENANCE_LABELS as readonly string[]).includes(value)
  )
}

function isTimeBasis(value: unknown): value is TimeBasis {
  return typeof value === 'string' && (TIME_BASES as readonly string[]).includes(value)
}

function isIndicatorId(value: unknown): value is IndicatorId {
  return typeof value === 'string' && (INDICATOR_IDS as readonly string[]).includes(value)
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

// --- one value item of a row -----------------------------------------------------

/** The source of a value, absent when the row omits it; never empty. */
function readOptionalSource(value: unknown, what: string): string | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${what}:source-empty`)
  }
  return value
}

/**
 * Parse the IndicatorValue part of a row: a number with its unit, its
 * provenance label, its source or assumption mark and its range or range
 * reason, or null with a missing part, keeping its unit (C3.1). Every rule
 * enforced here is a rule the contract itself enforces; the example file
 * satisfies all of them.
 */
function parseValuePart(value: Record<string, unknown>, what: string): ValueItem {
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

// --- one row of the table ----------------------------------------------------------

/**
 * Read an optional non-blank string field (carbon_model, computation): a
 * carbon row names them, the clocks render neither, so they are only checked
 * well formed and then dropped.
 */
function readOptionalName(value: unknown, what: string, field: string): void {
  if (value === undefined || value === null) return
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${what}:${field}-empty`)
  }
}

function parseRow(value: unknown, index: number): ClockRow {
  if (!isRecord(value)) {
    throw new Error(`invalid-row[${index}]:not-an-object`)
  }
  const what = `invalid-row[${index}]`
  if (typeof value.rotation_id !== 'string' || value.rotation_id.length === 0) {
    throw new Error(`${what}:rotation-id-empty`)
  }
  if (typeof value.scenario_id !== 'string' || value.scenario_id.length === 0) {
    throw new Error(`${what}:scenario-id-empty`)
  }
  if (!isIndicatorId(value.indicator)) {
    throw new Error(`${what}:indicator-not-an-id`)
  }
  if (
    value.direction !== 'lower_is_better' &&
    value.direction !== 'higher_is_better'
  ) {
    throw new Error(`${what}:direction-not-a-direction`)
  }
  if (!isTimeBasis(value.time_basis)) {
    throw new Error(`${what}:time-basis-not-a-basis`)
  }
  // W1: an agricultural-year row carries its year, a rotation row carries
  // none. T3: soil loss travels per agricultural year, the carbon trend per
  // rotation; the water indicator may sit on either basis.
  let agYear: number | undefined
  if (value.time_basis === 'ag_year') {
    if (typeof value.ag_year !== 'number' || !Number.isInteger(value.ag_year)) {
      throw new Error(`${what}:ag-year-not-an-integer`)
    }
    agYear = value.ag_year
  } else if (value.ag_year !== undefined && value.ag_year !== null) {
    throw new Error(`${what}:ag-year-on-rotation-basis`)
  }
  if (value.indicator === 'soil_loss' && value.time_basis !== 'ag_year') {
    throw new Error(`${what}:soil-loss-not-per-ag-year`)
  }
  if (value.indicator === 'soil_carbon_trend' && value.time_basis !== 'rotation') {
    throw new Error(`${what}:carbon-trend-not-per-rotation`)
  }
  readOptionalName(value.carbon_model, what, 'carbon-model')
  readOptionalName(value.computation, what, 'computation')
  const item = parseValuePart(value, what)
  return {
    ...item,
    rotation_id: value.rotation_id,
    scenario_id: value.scenario_id,
    indicator: value.indicator,
    time_basis: value.time_basis,
    ...(agYear !== undefined ? { ag_year: agYear } : {}),
  }
}

/**
 * Parse the results-table example. Pure: value in, typed table out, or an
 * Error naming what is wrong. Only the shape the clocks render is required;
 * cross-row rules of the contract (each cell once, the same cells for every
 * rotation) belong to the contract's own tests, not to a consumer.
 */
export function parseResultsTable(value: unknown): ResultsTableExample {
  if (!isRecord(value)) {
    throw new Error('invalid-table:not-an-object')
  }
  if (typeof value.case_id !== 'string' || value.case_id.length === 0) {
    throw new Error('invalid-table:case-id-empty')
  }
  if (typeof value.field_id !== 'string' || value.field_id.length === 0) {
    throw new Error('invalid-table:field-id-empty')
  }
  if (!Array.isArray(value.rows) || value.rows.length === 0) {
    throw new Error('invalid-table:rows-not-a-list')
  }
  return {
    case_id: value.case_id,
    field_id: value.field_id,
    rows: value.rows.map((row, index) => parseRow(row, index)),
  }
}

/**
 * The two clocks of each rotation of a table, in the order the rotations
 * first appear in it: the soil-loss rows sorted by agricultural year, the
 * water rows in table order. The carbon-trend rows are not a clock; they are
 * left out here, not hidden as zero.
 */
export function rotationsOfTable(table: ResultsTableExample): RotationClocks[] {
  const byOrder: string[] = []
  const soil = new Map<string, ClockRow[]>()
  const water = new Map<string, ClockRow[]>()
  for (const row of table.rows) {
    if (!byOrder.includes(row.rotation_id)) {
      byOrder.push(row.rotation_id)
      soil.set(row.rotation_id, [])
      water.set(row.rotation_id, [])
    }
    if (row.indicator === 'soil_loss') {
      soil.get(row.rotation_id)?.push(row)
    } else if (row.indicator === 'water_deficit_exposure') {
      water.get(row.rotation_id)?.push(row)
    }
  }
  return byOrder.map((rotationId) => ({
    rotation_id: rotationId,
    soil: [...(soil.get(rotationId) ?? [])].sort((a, b) => compareAgYear(a, b)),
    water: water.get(rotationId) ?? [],
  }))
}

function compareAgYear(a: ClockRow, b: ClockRow): number {
  // The parser guarantees a soil row carries its year; the narrowing is for
  // the reader as much as for the compiler.
  if (a.ag_year === undefined || b.ag_year === undefined) {
    throw new Error(`invalid-rotation[${a.rotation_id}]:soil-row-without-ag-year`)
  }
  return a.ag_year - b.ag_year
}

/** The results-table example: hand-written placeholder values, no engine output. */
export const resultsTable: ResultsTableExample = parseResultsTable(rawTable)
