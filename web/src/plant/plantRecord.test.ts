import { describe, expect, it } from 'vitest'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import { parsePlantAnswer } from './plantData'

/**
 * Acceptance test of what the parser keeps of the record (l3/board):
 * the kinds of year of the answer and the agricultural years behind each
 * soil-loss mean. PROPOSED. Every expected value is read from the contract
 * example; the refusals are the rules of KindsOfYearRecord and of the
 * soil-loss item of contracts/plant_answer/.
 */

function copy(): Record<string, any> {
  return JSON.parse(JSON.stringify(rawExample))
}

describe('the kinds of year of the answer', () => {
  it('keeps the source, each year with its kind, and the count of each kind', () => {
    const record = parsePlantAnswer(rawExample).kinds_of_year
    expect(record.source).toBe(rawExample.kinds_of_year.source)
    expect(record.years).toEqual(rawExample.kinds_of_year.years.map((y) => ({ ag_year: y.ag_year, kind: y.kind })))
    expect(record.counts).toEqual(rawExample.kinds_of_year.counts)
  })

  it('refuses counts that are not the years of each kind', () => {
    const raw = copy()
    raw.kinds_of_year.counts.el_nino += 1
    expect(() => parsePlantAnswer(raw)).toThrow(/counts:el_nino-not-the-years-of-its-kind/)
  })

  it('a record with a year that has no kind has every count null, and is read so', () => {
    const raw = copy()
    raw.kinds_of_year.years[0].kind = null
    raw.kinds_of_year.counts = { el_nino: null, neutral: null, la_nina: null }
    const record = parsePlantAnswer(raw).kinds_of_year
    expect(record.years[0].kind).toBeNull()
    expect(record.counts).toEqual({ el_nino: null, neutral: null, la_nina: null })
  })

  it('refuses a count beside a year without a kind: a missing count is never filled', () => {
    const raw = copy()
    raw.kinds_of_year.years[0].kind = null
    expect(() => parsePlantAnswer(raw)).toThrow(/not-the-years-of-its-kind/)
  })

  it('refuses years that are not sorted and unique', () => {
    const raw = copy()
    raw.kinds_of_year.years.reverse()
    expect(() => parsePlantAnswer(raw)).toThrow(/years-not-sorted-and-unique/)
  })
})

describe('the years behind a soil-loss mean', () => {
  it('keeps the agricultural years and their number', () => {
    const raw = rawExample.options[0].soil_loss.average
    const item = parsePlantAnswer(rawExample).options[0].soil_loss.average
    expect(item.ag_years).toEqual(raw.ag_years)
    expect(item.n_years).toBe(raw.n_years)
  })

  it('refuses a number of years that is not the number of the years listed', () => {
    const raw = copy()
    raw.options[0].soil_loss.average.n_years += 1
    expect(() => parsePlantAnswer(raw)).toThrow(/n-years-not-the-number-of-ag-years/)
  })
})
