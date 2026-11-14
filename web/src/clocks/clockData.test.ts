import { describe, expect, it } from 'vitest'
import { parseResultsTable, resultsTable, rotationsOfTable } from './clockData'

/**
 * Acceptance test of the two-clocks data module. The module is pure, so its
 * behaviour is: the accepted contract example parses into the rotations and
 * values it carries, and a row that breaks a rule the value display relies
 * on is rejected with an error naming what is wrong. The fixture rows below
 * are hand-made minimal rows of the results-table contract; their numbers
 * are placeholders, illustrative only.
 */

/** A minimal well-formed soil-loss row, changed one field at a time below. */
function baseRow(): Record<string, unknown> {
  return {
    rotation_id: 'PLACEHOLDER_rotation',
    scenario_id: 'PLACEHOLDER_scenario',
    time_basis: 'ag_year',
    ag_year: 2001,
    indicator: 'soil_loss',
    direction: 'lower_is_better',
    value: 1.5,
    unit: 't ha-1 yr-1',
    range: { low: 1.0, high: 2.0, kind: 'PLACEHOLDER_kind' },
    provenance: 'DERIVED',
    source: 'PLACEHOLDER_source',
  }
}

function tableWith(rows: unknown[]): unknown {
  return { case_id: 'PLACEHOLDER_case', field_id: 'PLACEHOLDER_field', rows }
}

describe('clockData: the results-table example', () => {
  it('parses the accepted example shipped in web/src/data', () => {
    expect(resultsTable.case_id).toBe('PLACEHOLDER_case')
    expect(resultsTable.field_id).toBe('PLACEHOLDER_field')
    expect(resultsTable.rows.length).toBe(10)
  })

  it('reads every rotation of the example, in table order', () => {
    const rotations = rotationsOfTable(resultsTable)
    expect(rotations.map((rotation) => rotation.rotation_id)).toEqual([
      'PLACEHOLDER_rotation_a',
      'PLACEHOLDER_rotation_b',
    ])
  })

  it('keeps the soil clock per rotation, one row per agricultural year in year order', () => {
    for (const rotation of rotationsOfTable(resultsTable)) {
      expect(rotation.soil.map((row) => row.ag_year)).toEqual([2001, 2002])
      expect(rotation.soil.every((row) => row.indicator === 'soil_loss')).toBe(true)
    }
  })

  it('keeps the water clock per rotation, as the rotation-basis row of the example', () => {
    for (const rotation of rotationsOfTable(resultsTable)) {
      expect(rotation.water.length).toBe(1)
      expect(rotation.water[0]?.indicator).toBe('water_deficit_exposure')
      expect(rotation.water[0]?.time_basis).toBe('rotation')
      expect(rotation.water[0]?.ag_year).toBeUndefined()
    }
  })

  it('leaves the carbon-trend rows out of the clocks, not hidden as zero', () => {
    const rotations = rotationsOfTable(resultsTable)
    const clockRows = rotations.flatMap((rotation) => [...rotation.soil, ...rotation.water])
    expect(clockRows.some((row) => row.indicator === 'soil_carbon_trend')).toBe(false)
    // the carbon rows are in the table, only not in a clock
    expect(resultsTable.rows.filter((row) => row.indicator === 'soil_carbon_trend').length).toBe(4)
  })
})

describe('clockData: a table the clocks can read', () => {
  it('orders the soil rows of a rotation by agricultural year', () => {
    const rows = [baseRow(), baseRow()]
    rows[1]!.ag_year = 1999
    const table = parseResultsTable(tableWith(rows))
    expect(rotationsOfTable(table)[0]?.soil.map((row) => row.ag_year)).toEqual([1999, 2001])
  })

  it('reads a water row per agricultural year on the ag_year basis', () => {
    const row = baseRow()
    row.indicator = 'water_deficit_exposure'
    row.direction = 'higher_is_better'
    row.unit = 'dimensionless'
    const table = parseResultsTable(tableWith([row]))
    const water = rotationsOfTable(table)[0]?.water ?? []
    expect(water.length).toBe(1)
    expect(water[0]?.time_basis).toBe('ag_year')
    expect(water[0]?.ag_year).toBe(2001)
  })

  it('reads a missing water row with its reason and its detail', () => {
    const row = baseRow()
    row.indicator = 'water_deficit_exposure'
    row.direction = 'higher_is_better'
    row.unit = 'dimensionless'
    row.value = null
    delete row.range
    delete row.provenance
    delete row.source
    row.missing = { reason: 'NOT_AVAILABLE', detail: 'PLACEHOLDER_detail' }
    const table = parseResultsTable(tableWith([row]))
    const water = rotationsOfTable(table)[0]?.water ?? []
    expect(water[0]?.value).toBeNull()
    expect(water[0]?.missing).toEqual({ reason: 'NOT_AVAILABLE', detail: 'PLACEHOLDER_detail' })
  })
})

describe('clockData: a row the value display cannot trust is rejected', () => {
  type Case = [name: string, mutate: (row: Record<string, unknown>) => void, expected: string]

  const cases: Case[] = [
    [
      'a missing value without a missing part',
      (row) => {
        row.value = null
        delete row.range
        delete row.provenance
        delete row.source
      },
      'invalid-row[0]:missing-part-absent',
    ],
    [
      'a number next to a missing part',
      (row) => {
        row.missing = { reason: 'NOT_APPLICABLE' }
      },
      'invalid-row[0]:value-and-missing',
    ],
    [
      'a number without a provenance label',
      (row) => {
        delete row.provenance
      },
      'invalid-row[0]:provenance-not-a-label',
    ],
    [
      'a number with neither a source nor the assumption mark',
      (row) => {
        delete row.source
      },
      'invalid-row[0]:source-or-assumption-absent',
    ],
    [
      'a number with a range and a reason for a missing range together',
      (row) => {
        row.range_missing = { reason: 'NOT_AVAILABLE' }
      },
      'invalid-row[0]:range-and-range-missing',
    ],
    [
      'a number with neither a range nor a reason for its absence',
      (row) => {
        delete row.range
      },
      'invalid-row[0]:range-or-range-missing-absent',
    ],
    [
      'a missing value that carries a source',
      (row) => {
        row.value = null
        delete row.range
        delete row.provenance
        row.missing = { reason: 'NO_COVERAGE' }
      },
      'invalid-row[0]:missing-with-provenance',
    ],
    [
      'a row on the rotation basis that carries an agricultural year',
      (row) => {
        row.indicator = 'water_deficit_exposure'
        row.direction = 'higher_is_better'
        row.unit = 'dimensionless'
        row.time_basis = 'rotation'
      },
      'invalid-row[0]:ag-year-on-rotation-basis',
    ],
    [
      'a row on the ag_year basis without its agricultural year',
      (row) => {
        delete row.ag_year
      },
      'invalid-row[0]:ag-year-not-an-integer',
    ],
    [
      'soil loss for the whole rotation',
      (row) => {
        row.time_basis = 'rotation'
        delete row.ag_year
      },
      'invalid-row[0]:soil-loss-not-per-ag-year',
    ],
    [
      'a carbon trend for one agricultural year',
      (row) => {
        row.indicator = 'soil_carbon_trend'
        row.direction = 'higher_is_better'
        row.unit = 't C ha-1 yr-1'
        row.carbon_model = 'amg'
        row.computation = 'end_minus_start'
        row.provenance = 'SIMULATED'
      },
      'invalid-row[0]:carbon-trend-not-per-rotation',
    ],
    [
      'an indicator the sheet does not define',
      (row) => {
        row.indicator = 'crop_yield'
      },
      'invalid-row[0]:indicator-not-an-id',
    ],
    [
      'a time basis that is not one of the two',
      (row) => {
        row.time_basis = 'month'
      },
      'invalid-row[0]:time-basis-not-a-basis',
    ],
  ]

  for (const [name, mutate, expected] of cases) {
    it(`rejects ${name}`, () => {
      const row = baseRow()
      mutate(row)
      expect(() => parseResultsTable(tableWith([row]))).toThrowError(expected)
    })
  }

  it('rejects a table without rows', () => {
    expect(() => parseResultsTable(tableWith([]))).toThrowError('invalid-table:rows-not-a-list')
  })
})
