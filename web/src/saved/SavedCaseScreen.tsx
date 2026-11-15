import { useState } from 'react'
import type { ChangeEvent } from 'react'
import rawSavedCase from '../data/saved_case.json'
import { missingPatternText, ValueDisplay } from '../components/ValueDisplay'
import type {
  MissingPart,
  ProvenanceLabel,
  ReasonCode,
  UncertaintyRange,
  ValueItem,
} from '../components/ValueDisplay'
import { parseDecisionOutput, parseMissing } from '../decision/decisionData'
import type { DecisionOutput, PairState } from '../decision/decisionData'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type { StringKey } from '../strings'

/**
 * Offline saved-case viewer (Blueprint Block 3, D177, #/saved).
 *
 * Reads the bundled copy web/src/data/saved_case.json offline by default and
 * lets a person open any exported SavedCase JSON document via a local file
 * picker without calling any backend service. Every part is validated at
 * runtime against the SavedCase contract (contracts/saved_case/): absent
 * parts and missing values always render their typed reason via
 * missingPatternText or ValueDisplay — never zero or blank — and carbon
 * balances always keep each model and variant separate (C1.5, #297).
 */

export type IndicatorId = 'soil_loss' | 'water_deficit_exposure' | 'soil_carbon_trend'
export type CarbonModelId = 'amg' | 'rothc'
export type TimeBasis = 'ag_year' | 'rotation'

export interface SavedFieldSummary {
  field_id: string
  name: string
  geometry_missing: MissingPart | null
}

export interface SavedFieldIdentity {
  example_data: boolean
  case_id: string
  label: string
  fields: SavedFieldSummary[]
}

export interface SavedResultsRow {
  indicator: IndicatorId
  rotation_id: string
  scenario_id: string
  time_basis: TimeBasis
  ag_year?: number
  carbon_model?: CarbonModelId
  computation?: string
  item: ValueItem
}

export interface SavedResultsTable {
  case_id: string
  field_id: string
  rows: SavedResultsRow[]
}

export interface SavedCarbonTrendEntry {
  computation: string
  item: ValueItem
}

export interface SavedCarbonBalance {
  example_data: boolean
  case_id: string
  field_id: string
  rotation_id: string
  carbon_model: CarbonModelId
  variant: string
  horizon: {
    start: { year: number; month: number }
    end: { year: number; month: number }
  }
  soil_depth: ValueItem
  soil_carbon_trend: SavedCarbonTrendEntry[]
}

export interface SavedCarbonBalanceItem {
  rotation_id: string
  carbon_model: CarbonModelId
  variant: string
  carbon_balance: SavedCarbonBalance | null
  carbon_balance_missing: MissingPart | null
}

export interface SavedCase {
  contract: 'saved_case'
  example_data: boolean
  case_id: string
  field_id: string
  saved_on: string
  field_identity: SavedFieldIdentity | null
  field_identity_missing: MissingPart | null
  results_table: SavedResultsTable | null
  results_table_missing: MissingPart | null
  carbon_balances: SavedCarbonBalanceItem[]
  decision_output: DecisionOutput | null
  decision_output_missing: MissingPart | null
}

export type SavedCaseLoadResult =
  | { ok: true; data: SavedCase }
  | { ok: false; errorKey: StringKey }

const SAVED_ON_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})Z$/
const VARIANT_RE = /^[a-z][a-z0-9_]*$/
const PROVENANCE_LABELS: readonly ProvenanceLabel[] = [
  'DECLARED',
  'OBSERVED',
  'DERIVED',
  'SIMULATED',
]
const INDICATOR_IDS: readonly IndicatorId[] = [
  'soil_loss',
  'water_deficit_exposure',
  'soil_carbon_trend',
]
const CARBON_MODELS: readonly CarbonModelId[] = ['amg', 'rothc']
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

function oneOf<T extends string>(value: unknown, list: readonly T[]): value is T {
  return typeof value === 'string' && (list as readonly string[]).includes(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonBlankString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function parseSavedOn(value: unknown): string {
  if (typeof value !== 'string') {
    throw new Error('invalid-saved-case:saved-on-not-string')
  }
  const match = SAVED_ON_RE.exec(value)
  if (!match) {
    throw new Error('invalid-saved-case:saved-on-format')
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) {
    throw new Error('invalid-saved-case:saved-on-out-of-range')
  }
  const utc = new Date(Date.UTC(year, month - 1, day, hour, minute))
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() + 1 !== month ||
    utc.getUTCDate() !== day ||
    utc.getUTCHours() !== hour ||
    utc.getUTCMinutes() !== minute
  ) {
    throw new Error('invalid-saved-case:saved-on-invalid-calendar-date')
  }
  return value
}

function parseMissingStrict(raw: unknown, what: string): MissingPart {
  const parsed = parseMissing(raw, what)
  if (!oneOf(parsed.reason, REASON_CODES)) {
    throw new Error(`${what}:reason-invalid`)
  }
  if (parsed.reason === 'MISSING_INPUT' && !isNonBlankString(parsed.detail)) {
    throw new Error(`${what}:missing-input-without-detail`)
  }
  if (parsed.detail !== undefined && !isNonBlankString(parsed.detail)) {
    throw new Error(`${what}:detail-blank`)
  }
  return parsed
}

function parseOptionalMissing(raw: unknown, what: string): MissingPart | null {
  if (raw === undefined || raw === null) {
    return null
  }
  return parseMissingStrict(raw, what)
}

function parseRangeStrict(raw: unknown, what: string): UncertaintyRange {
  if (!isRecord(raw)) {
    throw new Error(`${what}:range-not-an-object`)
  }
  if (!isFiniteNumber(raw.low) || !isFiniteNumber(raw.high)) {
    throw new Error(`${what}:range-bounds-not-finite`)
  }
  if (raw.low > raw.high) {
    throw new Error(`${what}:range-low-above-high`)
  }
  if (!isNonBlankString(raw.kind)) {
    throw new Error(`${what}:range-kind-empty`)
  }
  return { low: raw.low, high: raw.high, kind: raw.kind }
}

function parseValueItemStrict(raw: unknown, what: string): ValueItem {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-an-object`)
  }
  if (!isNonBlankString(raw.unit)) {
    throw new Error(`${what}:unit-empty`)
  }
  if (!Object.hasOwn(raw, 'value')) {
    throw new Error(`${what}:value-absent`)
  }
  const unit = raw.unit
  const missing = parseOptionalMissing(raw.missing, `${what}:missing`)
  const range = raw.range === undefined || raw.range === null ? undefined : parseRangeStrict(raw.range, what)
  const rangeMissing = parseOptionalMissing(raw.range_missing, `${what}:range-missing`) ?? undefined
  const provenance = raw.provenance === undefined || raw.provenance === null ? undefined : raw.provenance
  const source = raw.source === undefined || raw.source === null ? undefined : raw.source
  const assumption = raw.assumption === undefined || raw.assumption === null ? false : raw.assumption

  if (typeof assumption !== 'boolean') {
    throw new Error(`${what}:assumption-not-boolean`)
  }

  if (raw.value === null) {
    if (missing === null) {
      throw new Error(`${what}:value-null-without-missing`)
    }
    if (range !== undefined || rangeMissing !== undefined) {
      throw new Error(`${what}:missing-with-range`)
    }
    if (provenance !== undefined || source !== undefined || assumption) {
      throw new Error(`${what}:missing-with-provenance`)
    }
    return { value: null, unit, missing }
  }

  if (!isFiniteNumber(raw.value)) {
    throw new Error(`${what}:value-not-finite-number`)
  }
  if (missing !== null) {
    throw new Error(`${what}:value-and-missing`)
  }
  if (!oneOf(provenance, PROVENANCE_LABELS)) {
    throw new Error(`${what}:provenance-not-a-label`)
  }
  let parsedSource: string | undefined
  if (source !== undefined) {
    if (!isNonBlankString(source)) {
      throw new Error(`${what}:source-empty`)
    }
    parsedSource = source
  }
  if (parsedSource === undefined && !assumption) {
    throw new Error(`${what}:source-or-assumption-absent`)
  }
  if (range !== undefined && rangeMissing !== undefined) {
    throw new Error(`${what}:range-and-range-missing`)
  }
  if (range === undefined && rangeMissing === undefined) {
    throw new Error(`${what}:range-or-range-missing-absent`)
  }
  return {
    value: raw.value,
    unit,
    provenance,
    source: parsedSource,
    assumption: assumption ? true : undefined,
    range,
    range_missing: rangeMissing,
  }
}

function parseFieldIdentity(
  raw: unknown,
  caseId: string,
  fieldId: string,
  savedExampleData: boolean,
): SavedFieldIdentity {
  if (!isRecord(raw)) {
    throw new Error('invalid-saved-case:field-identity-not-object')
  }
  if (raw.contract !== 'field_identity') {
    throw new Error('invalid-saved-case:field-identity-contract')
  }
  if (typeof raw.example_data !== 'boolean') {
    throw new Error('invalid-saved-case:field-identity-example-data')
  }
  if (!savedExampleData && raw.example_data) {
    throw new Error('invalid-saved-case:example-data-mismatch-field-identity')
  }
  if (!isNonBlankString(raw.case_id) || raw.case_id !== caseId) {
    throw new Error('invalid-saved-case:field-identity-case-id-mismatch')
  }
  if (!isNonBlankString(raw.label)) {
    throw new Error('invalid-saved-case:field-identity-label-empty')
  }
  if (!Array.isArray(raw.fields) || raw.fields.length === 0) {
    throw new Error('invalid-saved-case:field-identity-fields-empty')
  }
  const seen = new Set<string>()
  const fields: SavedFieldSummary[] = raw.fields.map((entry, index) => {
    if (!isRecord(entry)) {
      throw new Error(`invalid-saved-case:field[${index}]-not-object`)
    }
    if (!isNonBlankString(entry.field_id)) {
      throw new Error(`invalid-saved-case:field[${index}]-id-empty`)
    }
    if (seen.has(entry.field_id)) {
      throw new Error(`invalid-saved-case:field[${index}]-duplicate-id`)
    }
    seen.add(entry.field_id)
    if (!isNonBlankString(entry.name)) {
      throw new Error(`invalid-saved-case:field[${index}]-name-empty`)
    }
    if (!Object.hasOwn(entry, 'geometry')) {
      throw new Error(`invalid-saved-case:field[${index}]-geometry-absent`)
    }
    const geometryMissing = parseOptionalMissing(
      entry.geometry_missing,
      `invalid-saved-case:field[${index}]:geometry-missing`,
    )
    if (entry.geometry === null) {
      if (geometryMissing === null) {
        throw new Error(`invalid-saved-case:field[${index}]-geometry-null-without-missing`)
      }
    } else {
      if (!isRecord(entry.geometry) || entry.geometry.type !== 'Polygon') {
        throw new Error(`invalid-saved-case:field[${index}]-geometry-not-polygon`)
      }
      if (geometryMissing !== null) {
        throw new Error(`invalid-saved-case:field[${index}]-geometry-and-missing`)
      }
    }
    return {
      field_id: entry.field_id,
      name: entry.name,
      geometry_missing: geometryMissing,
    }
  })
  if (!seen.has(fieldId)) {
    throw new Error('invalid-saved-case:field-id-not-in-field-identity')
  }
  return {
    example_data: raw.example_data,
    case_id: raw.case_id,
    label: raw.label,
    fields,
  }
}

function parseResultsTable(raw: unknown, caseId: string, fieldId: string): SavedResultsTable {
  if (!isRecord(raw)) {
    throw new Error('invalid-saved-case:results-table-not-object')
  }
  if (!isNonBlankString(raw.case_id) || raw.case_id !== caseId) {
    throw new Error('invalid-saved-case:results-table-case-id-mismatch')
  }
  if (!isNonBlankString(raw.field_id) || raw.field_id !== fieldId) {
    throw new Error('invalid-saved-case:results-table-field-id-mismatch')
  }
  if (!Array.isArray(raw.rows) || raw.rows.length === 0) {
    throw new Error('invalid-saved-case:results-table-rows-empty')
  }
  const rows: SavedResultsRow[] = raw.rows.map((entry, index) => {
    const what = `invalid-saved-case:results-row[${index}]`
    if (!isRecord(entry)) {
      throw new Error(`${what}:not-object`)
    }
    if (!oneOf(entry.indicator, INDICATOR_IDS)) {
      throw new Error(`${what}:indicator-invalid`)
    }
    if (entry.direction !== 'lower_is_better' && entry.direction !== 'higher_is_better') {
      throw new Error(`${what}:direction-invalid`)
    }
    if (!isNonBlankString(entry.rotation_id)) {
      throw new Error(`${what}:rotation-id-empty`)
    }
    if (!isNonBlankString(entry.scenario_id)) {
      throw new Error(`${what}:scenario-id-empty`)
    }
    if (entry.time_basis !== 'ag_year' && entry.time_basis !== 'rotation') {
      throw new Error(`${what}:time-basis-invalid`)
    }
    let agYear: number | undefined
    if (entry.time_basis === 'ag_year') {
      if (typeof entry.ag_year !== 'number' || !Number.isInteger(entry.ag_year)) {
        throw new Error(`${what}:ag-year-not-integer`)
      }
      agYear = entry.ag_year
    } else if (entry.ag_year !== undefined && entry.ag_year !== null) {
      throw new Error(`${what}:ag-year-with-rotation-basis`)
    }

    let carbonModel: CarbonModelId | undefined
    if (entry.carbon_model !== undefined && entry.carbon_model !== null) {
      if (!oneOf(entry.carbon_model, CARBON_MODELS)) {
        throw new Error(`${what}:carbon-model-invalid`)
      }
      carbonModel = entry.carbon_model
    }
    let computation: string | undefined
    if (entry.computation !== undefined && entry.computation !== null) {
      if (!isNonBlankString(entry.computation)) {
        throw new Error(`${what}:computation-empty`)
      }
      computation = entry.computation
    }

    return {
      indicator: entry.indicator,
      rotation_id: entry.rotation_id,
      scenario_id: entry.scenario_id,
      time_basis: entry.time_basis,
      ag_year: agYear,
      carbon_model: carbonModel,
      computation,
      item: parseValueItemStrict(entry, what),
    }
  })
  return { case_id: raw.case_id, field_id: raw.field_id, rows }
}

function parseYearMonth(raw: unknown, what: string): { year: number; month: number } {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-object`)
  }
  if (typeof raw.year !== 'number' || !Number.isInteger(raw.year)) {
    throw new Error(`${what}:year-not-integer`)
  }
  if (
    typeof raw.month !== 'number' ||
    !Number.isInteger(raw.month) ||
    raw.month < 1 ||
    raw.month > 12
  ) {
    throw new Error(`${what}:month-out-of-range`)
  }
  return { year: raw.year, month: raw.month }
}

function parseCarbonBalance(
  raw: unknown,
  expectedCaseId: string,
  expectedFieldId: string,
  expectedRotationId: string,
  expectedModel: CarbonModelId,
  expectedVariant: string,
  savedExampleData: boolean,
  what: string,
): SavedCarbonBalance {
  if (!isRecord(raw)) {
    throw new Error(`${what}:not-object`)
  }
  if (raw.contract !== 'carbon_balance') {
    throw new Error(`${what}:contract-invalid`)
  }
  if (typeof raw.example_data !== 'boolean') {
    throw new Error(`${what}:example-data-not-boolean`)
  }
  if (!savedExampleData && raw.example_data) {
    throw new Error(`${what}:example-data-mismatch`)
  }
  if (raw.case_id !== expectedCaseId || raw.field_id !== expectedFieldId) {
    throw new Error(`${what}:case-or-field-mismatch`)
  }
  if (
    raw.rotation_id !== expectedRotationId ||
    raw.carbon_model !== expectedModel ||
    raw.variant !== expectedVariant
  ) {
    throw new Error(`${what}:item-key-mismatch`)
  }
  if (!isRecord(raw.horizon)) {
    throw new Error(`${what}:horizon-not-object`)
  }
  const horizon = {
    start: parseYearMonth(raw.horizon.start, `${what}:horizon-start`),
    end: parseYearMonth(raw.horizon.end, `${what}:horizon-end`),
  }
  const soilDepth = parseValueItemStrict(raw.soil_depth, `${what}:soil-depth`)
  if (!Array.isArray(raw.soil_carbon_trend)) {
    throw new Error(`${what}:soil-carbon-trend-not-array`)
  }
  const trend: SavedCarbonTrendEntry[] = raw.soil_carbon_trend.map((entry, index) => {
    const entryWhat = `${what}:trend[${index}]`
    if (!isRecord(entry) || !isNonBlankString(entry.computation)) {
      throw new Error(`${entryWhat}:computation-empty`)
    }
    return {
      computation: entry.computation,
      item: parseValueItemStrict(entry, entryWhat),
    }
  })
  return {
    example_data: raw.example_data,
    case_id: expectedCaseId,
    field_id: expectedFieldId,
    rotation_id: expectedRotationId,
    carbon_model: expectedModel,
    variant: expectedVariant,
    horizon,
    soil_depth: soilDepth,
    soil_carbon_trend: trend,
  }
}

function parseCarbonBalances(
  rawList: unknown,
  caseId: string,
  fieldId: string,
  savedExampleData: boolean,
  resultsTable: SavedResultsTable | null,
): SavedCarbonBalanceItem[] {
  if (!Array.isArray(rawList)) {
    throw new Error('invalid-saved-case:carbon-balances-not-array')
  }
  const seenKeys = new Set<string>()
  const items: SavedCarbonBalanceItem[] = rawList.map((entry, index) => {
    const what = `invalid-saved-case:carbon-balances[${index}]`
    if (!isRecord(entry)) {
      throw new Error(`${what}:not-object`)
    }
    if (!isNonBlankString(entry.rotation_id)) {
      throw new Error(`${what}:rotation-id-empty`)
    }
    if (!oneOf(entry.carbon_model, CARBON_MODELS)) {
      throw new Error(`${what}:carbon-model-invalid`)
    }
    if (!isNonBlankString(entry.variant) || !VARIANT_RE.test(entry.variant)) {
      throw new Error(`${what}:variant-invalid`)
    }
    const key = `${entry.rotation_id}\0${entry.carbon_model}\0${entry.variant}`
    if (seenKeys.has(key)) {
      throw new Error(`${what}:duplicate-key`)
    }
    seenKeys.add(key)

    if (!Object.hasOwn(entry, 'carbon_balance')) {
      throw new Error(`${what}:carbon-balance-absent`)
    }
    const missing = parseOptionalMissing(entry.carbon_balance_missing, `${what}:missing`)
    if (entry.carbon_balance === null) {
      if (missing === null) {
        throw new Error(`${what}:null-without-missing`)
      }
      return {
        rotation_id: entry.rotation_id,
        carbon_model: entry.carbon_model,
        variant: entry.variant,
        carbon_balance: null,
        carbon_balance_missing: missing,
      }
    }
    if (missing !== null) {
      throw new Error(`${what}:balance-and-missing-both`)
    }
    return {
      rotation_id: entry.rotation_id,
      carbon_model: entry.carbon_model,
      variant: entry.variant,
      carbon_balance: parseCarbonBalance(
        entry.carbon_balance,
        caseId,
        fieldId,
        entry.rotation_id,
        entry.carbon_model,
        entry.variant,
        savedExampleData,
        `${what}:carbon-balance`,
      ),
      carbon_balance_missing: null,
    }
  })

  if (resultsTable !== null) {
    const rotations = new Set(resultsTable.rows.map((row) => row.rotation_id))
    const foundPairs = new Set(items.map((item) => `${item.rotation_id}\0${item.carbon_model}`))
    for (const rotationId of rotations) {
      for (const model of CARBON_MODELS) {
        if (!foundPairs.has(`${rotationId}\0${model}`)) {
          throw new Error('invalid-saved-case:carbon-balances-incomplete')
        }
      }
    }
    for (const item of items) {
      if (!rotations.has(item.rotation_id)) {
        throw new Error('invalid-saved-case:carbon-balance-unknown-rotation')
      }
    }
  }

  return items
}

function parseSavedDecisionOutput(
  raw: unknown,
  caseId: string,
  fieldId: string,
  savedExampleData: boolean,
): DecisionOutput {
  if (!isRecord(raw)) {
    throw new Error('invalid-saved-case:decision-output-not-object')
  }
  if (raw.contract !== 'decision_output') {
    throw new Error('invalid-saved-case:decision-output-contract')
  }
  if (raw.case_id !== caseId || raw.field_id !== fieldId) {
    throw new Error('invalid-saved-case:decision-output-case-or-field-mismatch')
  }
  const parsed = parseDecisionOutput(raw)
  if (!savedExampleData && parsed.example_data) {
    throw new Error('invalid-saved-case:example-data-mismatch-decision')
  }
  return parsed
}

/**
 * Parse and strictly validate one SavedCase document against contracts/saved_case/.
 * Pure: unknown value in, typed SavedCase out, or an Error with a technical code.
 */
export function parseSavedCase(value: unknown): SavedCase {
  if (!isRecord(value)) {
    throw new Error('invalid-saved-case:not-an-object')
  }
  if (value.contract !== 'saved_case') {
    throw new Error('invalid-saved-case:contract-not-saved-case')
  }
  if (typeof value.example_data !== 'boolean') {
    throw new Error('invalid-saved-case:example-data-not-boolean')
  }
  if (!isNonBlankString(value.case_id)) {
    throw new Error('invalid-saved-case:case-id-empty')
  }
  if (!isNonBlankString(value.field_id)) {
    throw new Error('invalid-saved-case:field-id-empty')
  }
  const savedOn = parseSavedOn(value.saved_on)

  if (!Object.hasOwn(value, 'field_identity')) {
    throw new Error('invalid-saved-case:field-identity-key-absent')
  }
  const fieldIdentityMissing = parseOptionalMissing(
    value.field_identity_missing,
    'invalid-saved-case:field-identity-missing',
  )
  let fieldIdentity: SavedFieldIdentity | null = null
  if (value.field_identity === null) {
    if (fieldIdentityMissing === null) {
      throw new Error('invalid-saved-case:field-identity-null-without-missing')
    }
  } else {
    if (fieldIdentityMissing !== null) {
      throw new Error('invalid-saved-case:field-identity-and-missing-both')
    }
    fieldIdentity = parseFieldIdentity(
      value.field_identity,
      value.case_id,
      value.field_id,
      value.example_data,
    )
  }

  if (!Object.hasOwn(value, 'results_table')) {
    throw new Error('invalid-saved-case:results-table-key-absent')
  }
  const resultsTableMissing = parseOptionalMissing(
    value.results_table_missing,
    'invalid-saved-case:results-table-missing',
  )
  let resultsTable: SavedResultsTable | null = null
  if (value.results_table === null) {
    if (resultsTableMissing === null) {
      throw new Error('invalid-saved-case:results-table-null-without-missing')
    }
  } else {
    if (resultsTableMissing !== null) {
      throw new Error('invalid-saved-case:results-table-and-missing-both')
    }
    resultsTable = parseResultsTable(value.results_table, value.case_id, value.field_id)
  }

  const carbonBalances = parseCarbonBalances(
    value.carbon_balances,
    value.case_id,
    value.field_id,
    value.example_data,
    resultsTable,
  )

  if (!Object.hasOwn(value, 'decision_output')) {
    throw new Error('invalid-saved-case:decision-output-key-absent')
  }
  const decisionOutputMissing = parseOptionalMissing(
    value.decision_output_missing,
    'invalid-saved-case:decision-output-missing',
  )
  let decisionOutput: DecisionOutput | null = null
  if (value.decision_output === null) {
    if (decisionOutputMissing === null) {
      throw new Error('invalid-saved-case:decision-output-null-without-missing')
    }
  } else {
    if (decisionOutputMissing !== null) {
      throw new Error('invalid-saved-case:decision-output-and-missing-both')
    }
    decisionOutput = parseSavedDecisionOutput(
      value.decision_output,
      value.case_id,
      value.field_id,
      value.example_data,
    )
  }

  return {
    contract: 'saved_case',
    example_data: value.example_data,
    case_id: value.case_id,
    field_id: value.field_id,
    saved_on: savedOn,
    field_identity: fieldIdentity,
    field_identity_missing: fieldIdentityMissing,
    results_table: resultsTable,
    results_table_missing: resultsTableMissing,
    carbon_balances: carbonBalances,
    decision_output: decisionOutput,
    decision_output_missing: decisionOutputMissing,
  }
}

/**
 * Parse JSON text from an offline file and validate it strictly as a SavedCase.
 * Returns a typed load result with a strings.ts error key on failure.
 */
export function loadSavedCaseText(text: string): SavedCaseLoadResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { ok: false, errorKey: 'saved.error_invalid_json' }
  }
  try {
    return { ok: true, data: parseSavedCase(parsed) }
  } catch {
    return { ok: false, errorKey: 'saved.error_invalid_case' }
  }
}

export const bundledSavedCase: SavedCase = parseSavedCase(rawSavedCase)

function formatYearMonth(ym: { year: number; month: number }): string {
  return `${ym.year}-${String(ym.month).padStart(2, '0')}`
}

function formatRowLabel(row: SavedResultsRow): string {
  return [
    row.rotation_id,
    row.scenario_id,
    row.indicator,
    row.ag_year !== undefined ? String(row.ag_year) : undefined,
    row.carbon_model,
    row.computation,
  ]
    .filter((part): part is string => part !== undefined)
    .join(' · ')
}

function uniqueInOrder(values: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const v of values) {
    if (!seen.has(v)) {
      seen.add(v)
      out.push(v)
    }
  }
  return out
}

function PairStateCard({ state }: { state: PairState }) {
  const pairName = formatString(strings['decision.pair_of'], {
    first: state.pair[0],
    second: state.pair[1],
  })
  return (
    <article
      data-testid="saved-decision-pair"
      className="mt-3 rounded-lg border border-fs-border bg-fs-surface px-4 py-3"
    >
      <h4 className="text-sm font-semibold text-fs-text">{pairName}</h4>
      {state.value !== null ? (
        <div className="mt-1 space-y-1">
          <p data-testid="saved-decision-pair-state" className="text-sm font-medium text-fs-text">
            {state.value}
          </p>
          {state.preferred_rotation_id !== undefined ? (
            <p className="font-mono text-sm text-fs-primary">{state.preferred_rotation_id}</p>
          ) : null}
          {state.reason !== undefined ? (
            <p className="text-sm text-fs-muted">{state.reason}</p>
          ) : null}
          {state.reason_missing !== undefined ? (
            <p className="text-sm italic text-fs-muted">
              {missingPatternText(state.value, state.reason_missing)}
            </p>
          ) : null}
        </div>
      ) : (
        <p data-testid="saved-decision-pair-missing" className="mt-1 text-sm italic text-fs-muted">
          {missingPatternText(pairName, state.missing)}
        </p>
      )}
      <p data-testid="saved-decision-pair-coverage" className="mt-2 text-sm text-fs-muted">
        {formatString(strings['decision.coverage'], {
          k: state.coverage.cells_compared,
          n: state.coverage.cells_of_the_pair,
        })}
      </p>
    </article>
  )
}

export interface SavedCaseViewProps {
  savedCase?: SavedCase
  sourceName?: string | null
  errorKey?: StringKey | null
  onFileChange?: (event: ChangeEvent<HTMLInputElement>) => void
  onReset?: () => void
}

export function SavedCaseView({
  savedCase = bundledSavedCase,
  sourceName = null,
  errorKey = null,
  onFileChange,
  onReset,
}: SavedCaseViewProps) {
  const resultsTable = savedCase.results_table
  const presentRows = resultsTable
    ? resultsTable.rows.filter((row) => row.item.value !== null).length
    : 0
  const missingRows = resultsTable ? resultsTable.rows.length - presentRows : 0
  const resultRotations = resultsTable
    ? uniqueInOrder(resultsTable.rows.map((row) => row.rotation_id))
    : []
  const resultScenarios = resultsTable
    ? uniqueInOrder(resultsTable.rows.map((row) => row.scenario_id))
    : []

  return (
    <section aria-labelledby="saved-screen-title" className="mx-auto max-w-3xl">
      <nav className="mb-4 flex flex-wrap gap-4 text-sm">
        <a
          href="#/"
          className="font-medium text-fs-primary underline transition hover:opacity-80"
        >
          {strings['saved.back_entry']}
        </a>
        <a
          href="#/fields"
          className="font-medium text-fs-primary underline transition hover:opacity-80"
        >
          {strings['identity.title']}
        </a>
      </nav>

      <h2 id="saved-screen-title" className="text-lg font-semibold text-fs-text">
        {strings['saved.title']}
      </h2>

      <div className="mt-2 space-y-1 text-sm text-fs-muted">
        <p data-testid="saved-case-id">
          {formatString(strings['saved.case_id'], { id: savedCase.case_id })}
        </p>
        <p data-testid="saved-field-id">
          {formatString(strings['saved.field_id'], { id: savedCase.field_id })}
        </p>
        <p data-testid="saved-on-timestamp">
          {formatString(strings['saved.saved_on'], { timestamp: savedCase.saved_on })}
        </p>
      </div>

      {savedCase.example_data && (
        <p
          role="note"
          data-testid="saved-example-banner"
          className="mt-4 rounded-lg border border-amber-300 bg-[var(--fs-warning-bg)] px-4 py-3 text-sm text-fs-warning"
        >
          {strings['example.banner']}
        </p>
      )}

      <div className="mt-4 rounded-lg border border-fs-border bg-fs-surface px-4 py-3">
        <label htmlFor="saved-case-file-input" className="block text-sm font-medium text-fs-text">
          {strings['saved.load_file']}
        </label>
        <input
          id="saved-case-file-input"
          data-testid="saved-file-input"
          type="file"
          accept=".json"
          onChange={onFileChange}
          className="mt-2 block w-full text-sm text-fs-text file:mr-4 file:rounded-lg file:border file:border-fs-border file:bg-fs-bg file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-fs-text"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-fs-muted">
          <span data-testid="saved-source-status">
            {sourceName !== null
              ? formatString(strings['saved.source_file'], { name: sourceName })
              : strings['saved.source_bundled']}
          </span>
          {(sourceName !== null || errorKey !== null) && (
            <button
              type="button"
              data-testid="saved-reset-button"
              onClick={onReset}
              className="font-medium text-fs-primary underline transition hover:opacity-80"
            >
              {strings['saved.reset_bundled']}
            </button>
          )}
        </div>
        {errorKey !== null && (
          <p
            role="alert"
            data-testid="saved-file-error"
            className="mt-3 rounded-lg border border-red-300 bg-[var(--fs-error-bg)] px-3 py-2 text-sm text-fs-error"
          >
            {strings[errorKey]}
          </p>
        )}
      </div>

      <section aria-labelledby="saved-field-identity-title" className="mt-6">
        <h3 id="saved-field-identity-title" className="text-base font-semibold text-fs-text">
          {strings['saved.field_identity_heading']}
        </h3>
        {savedCase.field_identity !== null ? (
          <div
            data-testid="saved-field-identity"
            className="mt-2 rounded-lg border border-fs-border bg-fs-surface px-4 py-3"
          >
            <p className="text-sm font-medium text-fs-text">
              {savedCase.field_identity.label}
            </p>
            <p className="mt-0.5 text-xs text-fs-muted">
              {formatString(strings['entry.fields_count'], {
                n: savedCase.field_identity.fields.length,
              })}
            </p>
            <ul className="mt-3 space-y-2">
              {savedCase.field_identity.fields.map((field) => {
                const isRunField = field.field_id === savedCase.field_id
                return (
                  <li
                    key={field.field_id}
                    data-testid="saved-identity-field"
                    className="rounded border border-fs-border bg-fs-bg px-3 py-2 text-sm"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-fs-text">{field.name}</span>
                      {isRunField && (
                        <span className="rounded bg-fs-primary px-2 py-0.5 text-xs font-semibold text-white">
                          {strings['saved.run_field_badge']}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 font-mono text-xs text-fs-muted">
                      {strings['identity.field_id_label']}: {field.field_id}
                    </p>
                    {field.geometry_missing !== null && (
                      <p className="mt-1 text-xs italic text-fs-muted">
                        {missingPatternText(field.name, field.geometry_missing)}
                      </p>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : (
          <p
            data-testid="saved-field-identity-missing"
            className="mt-2 text-sm italic text-fs-muted"
          >
            {missingPatternText(
              strings['saved.field_identity_heading'],
              savedCase.field_identity_missing!,
            )}
          </p>
        )}
      </section>

      <section aria-labelledby="saved-results-title" className="mt-6">
        <h3 id="saved-results-title" className="text-base font-semibold text-fs-text">
          {strings['saved.results_heading']}
        </h3>
        {resultsTable !== null ? (
          <div
            data-testid="saved-results-table"
            className="mt-2 rounded-lg border border-fs-border bg-fs-surface px-4 py-3"
          >
            <div className="space-y-1 text-sm text-fs-muted">
              <p data-testid="saved-results-rows-count">
                {formatString(strings['saved.results_rows_count'], { n: resultsTable.rows.length })}
              </p>
              <p data-testid="saved-results-availability">
                {formatString(strings['saved.results_availability'], {
                  present: presentRows,
                  missing: missingRows,
                })}
              </p>
              <p data-testid="saved-results-rotations">
                {formatString(strings['saved.results_rotations'], {
                  rotations: resultRotations.join(', '),
                })}
              </p>
              <p data-testid="saved-results-scenarios">
                {formatString(strings['saved.results_scenarios'], {
                  scenarios: resultScenarios.join(', '),
                })}
              </p>
            </div>
            <ul className="mt-4 space-y-2 border-t border-fs-border pt-3">
              {resultsTable.rows.map((row, index) => {
                const label = formatRowLabel(row)
                return (
                  <li
                    key={`${label}-${index}`}
                    data-testid="saved-results-row"
                    className="flex flex-wrap gap-3 border-b border-fs-border pb-2 last:border-b-0 last:pb-0"
                  >
                    {row.item.value !== null && (
                      <span className="font-mono text-xs text-fs-muted">{label}</span>
                    )}
                    <div className="min-w-0 flex-1">
                      <ValueDisplay what={label} item={row.item} />
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : (
          <p data-testid="saved-results-missing" className="mt-2 text-sm italic text-fs-muted">
            {missingPatternText(
              strings['saved.results_heading'],
              savedCase.results_table_missing!,
            )}
          </p>
        )}
      </section>

      <section aria-labelledby="saved-carbon-title" className="mt-6">
        <h3 id="saved-carbon-title" className="text-base font-semibold text-fs-text">
          {strings['saved.carbon_heading']}
        </h3>
        {savedCase.carbon_balances.length === 0 ? (
          <p data-testid="saved-carbon-empty" className="mt-2 text-sm italic text-fs-muted">
            {strings['saved.carbon_empty']}
          </p>
        ) : (
          <ul className="mt-2 space-y-3">
            {savedCase.carbon_balances.map((item) => {
              const itemLabel = formatString(strings['saved.carbon_item_label'], {
                rotation: item.rotation_id,
                model: item.carbon_model,
                variant: item.variant,
              })
              return (
                <li
                  key={`${item.rotation_id}:${item.carbon_model}:${item.variant}`}
                  data-testid="saved-carbon-item"
                  className="rounded-lg border border-fs-border bg-fs-surface px-4 py-3"
                >
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
                    <span className="font-semibold text-fs-text">
                      {formatString(strings['cards.per_rotation'], { id: item.rotation_id })}
                    </span>
                    <span data-testid="saved-carbon-model" className="font-mono text-xs text-fs-muted">
                      {formatString(strings['cards.model_label'], { model: item.carbon_model })}
                    </span>
                    <span data-testid="saved-carbon-variant" className="font-mono text-xs text-fs-muted">
                      {formatString(strings['saved.carbon_variant'], { variant: item.variant })}
                    </span>
                  </div>
                  {item.carbon_balance === null ? (
                    <p
                      data-testid="saved-carbon-missing"
                      className="mt-2 text-sm italic text-fs-muted"
                    >
                      {missingPatternText(itemLabel, item.carbon_balance_missing!)}
                    </p>
                  ) : (
                    <div data-testid="saved-carbon-present" className="mt-2 space-y-2 text-sm">
                      <p className="text-xs text-fs-muted">
                        {formatString(strings['saved.carbon_horizon'], {
                          start: formatYearMonth(item.carbon_balance.horizon.start),
                          end: formatYearMonth(item.carbon_balance.horizon.end),
                        })}
                      </p>
                      <ValueDisplay
                        what={strings['saved.carbon_depth']}
                        item={item.carbon_balance.soil_depth}
                      />
                      <div className="pt-1">
                        <p className="text-xs font-semibold text-fs-muted">
                          {strings['saved.carbon_trend_heading']}
                        </p>
                        <ul className="mt-1 space-y-2">
                          {item.carbon_balance.soil_carbon_trend.map((trend) => (
                            <li key={trend.computation} className="space-y-0.5">
                              <p className="font-mono text-xs text-fs-muted">
                                {formatString(strings['cards.computation_label'], {
                                  computation: trend.computation,
                                })}
                              </p>
                              <ValueDisplay what={trend.computation} item={trend.item} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="saved-decision-title" className="mt-6">
        <h3 id="saved-decision-title" className="text-base font-semibold text-fs-text">
          {strings['decision.title']}
        </h3>
        {savedCase.decision_output === null ? (
          <p data-testid="saved-decision-missing" className="mt-2 text-sm italic text-fs-muted">
            {missingPatternText(strings['decision.title'], savedCase.decision_output_missing!)}
          </p>
        ) : (
          <div data-testid="saved-decision-output" className="mt-2 space-y-3">
            <div className="rounded-lg border border-fs-border bg-fs-surface px-4 py-3">
              <h4 className="text-sm font-semibold text-fs-text">{strings['decision.state']}</h4>
              {savedCase.decision_output.state.value !== null ? (
                <p
                  data-testid="saved-decision-state"
                  className="mt-1 text-sm font-medium text-fs-text"
                >
                  {savedCase.decision_output.state.value}
                </p>
              ) : (
                <p
                  data-testid="saved-decision-state-missing"
                  className="mt-1 text-sm italic text-fs-muted"
                >
                  {missingPatternText(
                    strings['decision.state'],
                    savedCase.decision_output.state.missing,
                  )}
                </p>
              )}
              {savedCase.decision_output.state.reasons.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {savedCase.decision_output.state.reasons.map((reason, index) => (
                    <li
                      key={index}
                      data-testid="saved-decision-reason"
                      className="text-sm text-fs-muted"
                    >
                      {reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h4 className="text-sm font-semibold text-fs-text">{strings['decision.pairs']}</h4>
              {savedCase.decision_output.pair_states.map((pairState) => (
                <PairStateCard
                  key={`${pairState.pair[0]}:${pairState.pair[1]}`}
                  state={pairState}
                />
              ))}
            </div>
          </div>
        )}
      </section>
    </section>
  )
}

export default function SavedCaseScreen({
  initialCase = bundledSavedCase,
}: {
  initialCase?: SavedCase
}) {
  const [savedCase, setSavedCase] = useState<SavedCase>(initialCase)
  const [sourceName, setSourceName] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState<StringKey | null>(null)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0]
    if (!file) return
    const text = await file.text()
    const result = loadSavedCaseText(text)
    if (result.ok) {
      setSavedCase(result.data)
      setSourceName(file.name)
      setErrorKey(null)
    } else {
      setErrorKey(result.errorKey)
    }
    event.target.value = ''
  }

  function handleReset(): void {
    setSavedCase(initialCase)
    setSourceName(null)
    setErrorKey(null)
  }

  return (
    <SavedCaseView
      savedCase={savedCase}
      sourceName={sourceName}
      errorKey={errorKey}
      onFileChange={(event) => {
        void handleFileChange(event)
      }}
      onReset={handleReset}
    />
  )
}
