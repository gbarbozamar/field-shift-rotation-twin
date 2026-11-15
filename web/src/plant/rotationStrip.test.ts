import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import { parseRotationDefinition } from '../rotation/exampleRotation'
import type { RotationDefinition } from '../rotation/exampleRotation'
import { missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type { StringKey } from '../strings'
import {
  buildRotationStrip,
  cropOrder,
  cropText,
  parsePlantRequestRotations,
  plantRotations,
  readPlantRotations,
  stripText,
} from './rotationStrip'

// Fix round 1 of S-020: plantRotations is now a typed read (definitions or a
// missing part); the example request parses, so its definitions are here.
const exampleRotations: RotationDefinition[] = plantRotations.rotations!

/**
 * Acceptance test of the strip of crops of each option (S-020). PROPOSED,
 * designed before the code.
 *
 * (1) the strip of each example rotation lists its crops per agricultural
 *     year, and its text alternative reads them year by year. Every expected
 *     year and month is read from the example's own dates and its start
 *     month (C5.3: an agricultural year begins at the start month and is
 *     named by the calendar year it begins in), never typed here;
 * (2) a pasture kept over several agricultural years appears in each of
 *     them; a component whose sowing date is missing is listed with its
 *     reason and placed in no year;
 * (7) the copied request equals the contract file.
 * Cases (3) to (6) are in PlantOptions.test.tsx.
 */

const here = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(here, '..', '..')
const contractFile = resolve(
  webRoot,
  '..',
  'contracts',
  'plant_answer',
  'examples',
  'PLACEHOLDER_plant_request.json',
)
const copyFile = resolve(webRoot, 'src', 'data', 'PLACEHOLDER_plant_request.json')

/** A deep copy of one rotation of the example request, to change in memory. */
function rotationCopy(index: number): Record<string, any> {
  return JSON.parse(JSON.stringify(rawRequest.rotations[index]))
}

/** The test's own reading of C5.3: the agricultural year a date lies in. */
function agYearOf(date: string, startMonth: number): number {
  const [year, month] = date.split('-').map(Number)
  return month >= startMonth ? year : year - 1
}

function monthOf(date: string): number {
  return Number(date.split('-')[1])
}

function monthName(month: number): string {
  return strings[`plant.month.${month}` as StringKey]
}

describe('the copied request (7)', () => {
  it('equals the contract file', () => {
    expect(readFileSync(copyFile, 'utf8')).toBe(readFileSync(contractFile, 'utf8'))
  })

  it('gives one rotation definition per rotation of the request, in request order', () => {
    expect(plantRotations.missing).toBeNull()
    expect(exampleRotations.map((r) => r.rotation_id)).toEqual(
      rawRequest.rotations.map((r) => r.rotation_id),
    )
  })

  it('refuses what is not a plant request', () => {
    expect(() => parsePlantRequestRotations({ contract: 'plant_answer', rotations: [] })).toThrow()
    expect(() => parsePlantRequestRotations({ contract: 'plant_request' })).toThrow()
  })

  // PROPOSED (fix round 1 of S-020): a request that does not parse is a typed
  // absence, never an exception that would take down the route.
  it('reads a request that does not parse as missing, with its reason, never throwing', () => {
    const broken = JSON.parse(JSON.stringify(rawRequest))
    broken.rotations[0].ag_year_start = null
    for (const value of [broken, { contract: 'plant_answer', rotations: [] }, null]) {
      expect(readPlantRotations(value)).toEqual({
        rotations: null,
        missing: { reason: 'MISSING_INPUT', detail: strings['plant.strip.request_invalid_detail'] },
      })
    }
    expect(readPlantRotations(rawRequest)).toEqual({ rotations: exampleRotations, missing: null })
  })
})

describe('the strip of each example rotation (1)', () => {
  for (const raw of rawRequest.rotations) {
    describe(raw.rotation_id, () => {
      const rotation = parseRotationDefinition(raw)
      const strip = buildRotationStrip(rotation)
      const start = raw.ag_year_start.month
      const sown = raw.components.filter((c) => c.sowing.date !== null)
      const first = Math.min(...sown.map((c) => agYearOf(c.sowing.date!, start)))

      it('keeps the rotation id and the label of the definition', () => {
        expect(strip.rotation_id).toBe(raw.rotation_id)
        expect(strip.label).toBe(raw.label)
      })

      it('places every sown crop in the agricultural year of its sowing date', () => {
        for (const component of sown) {
          const index = agYearOf(component.sowing.date!, start) - first + 1
          const year = strip.years.find((y) => y.index === index)!
          expect(year, `${component.component_id} in year ${index}`).toBeDefined()
          expect(year.ag_year).toBe(agYearOf(component.sowing.date!, start))
          const crop = year.crops.find((c) => c.component_id === component.component_id)!
          expect(crop.crop_id).toBe(component.crop_id)
          expect(crop.purpose).toBe(component.purpose)
          expect(crop.sowing.month).toBe(monthOf(component.sowing.date!))
          expect(crop.kept).toBe(false)
        }
        expect(strip.unplaced).toEqual([])
      })

      it('lists the crops of a year in sowing order', () => {
        for (const year of strip.years) {
          const dates = year.crops.map(
            (c) => raw.components.find((r) => r.component_id === c.component_id)!.sowing.date!,
          )
          expect(dates).toEqual([...dates].sort())
        }
      })

      it('reads every year in its text alternative, from the dates of the example', () => {
        const byYear = new Map<number, string[]>()
        for (const component of sown) {
          const index = agYearOf(component.sowing.date!, start) - first + 1
          const harvest = component.harvest
          const text =
            harvest.date !== null
              ? formatString(strings['plant.strip.crop'], {
                  crop: component.crop_id,
                  sowing: monthName(monthOf(component.sowing.date!)),
                  harvest: monthName(monthOf(harvest.date)),
                })
              : formatString(strings['plant.strip.crop_harvest_missing'], {
                  crop: component.crop_id,
                  sowing: monthName(monthOf(component.sowing.date!)),
                  harvest: missingPatternText(strings['plant.strip.harvest'], {
                    reason: harvest.missing!.reason as 'NOT_APPLICABLE',
                    detail: harvest.missing!.detail,
                  }),
                })
          // Fix round 1 of S-020: the text alternative reads each crop with
          // its purpose, as the strip shows it.
          const withPurpose = formatString(strings['plant.strip.crop_alt'], {
            crop: text,
            purpose: formatString(strings['plant.strip.purpose'], { purpose: component.purpose }),
          })
          byYear.set(index, [...(byYear.get(index) ?? []), withPurpose])
        }
        const expected = [...byYear.keys()]
          .sort((a, b) => a - b)
          .map((n) =>
            formatString(strings['plant.strip.year'], {
              n,
              crops: byYear.get(n)!.join(strings['plant.strip.crop_join']),
            }),
          )
          .join(strings['plant.strip.year_join'])
        expect(stripText(strip)).toBe(expected)
      })

      // PROPOSED (fix round 1 of S-020): the year numbers depend on the start
      // month, so the strip keeps it with its provisional mark and provenance,
      // and the provenance of the dates it places.
      it('keeps the start of the agricultural year and the provenance of its dates', () => {
        expect(strip.ag_year_start).toEqual(raw.ag_year_start)
        const pairs: { provenance: string; source: string }[] = []
        for (const component of sown) {
          for (const part of [component.sowing, component.harvest]) {
            if (part.date === null) continue
            const mark = part as { provenance: string; source: string }
            if (!pairs.some((p) => p.provenance === mark.provenance && p.source === mark.source)) {
              pairs.push({ provenance: mark.provenance, source: mark.source })
            }
          }
        }
        expect(strip.date_marks).toEqual(pairs)
      })
    })
  }
})

describe('a pasture kept over years, and a sowing date missing (2)', () => {
  it('a pasture harvested after the next start shows in each agricultural year from sowing to harvest', () => {
    const raw = rotationCopy(2)
    const pasture = raw.components.find((c: { purpose: string }) => c.purpose === 'pasture')
    const sowing: string = pasture.sowing.date
    // Harvested one calendar year after its sowing date: the same day of the
    // next calendar year lies in the next agricultural year, whatever the
    // start month.
    const [y, m, d] = sowing.split('-')
    const harvest = `${Number(y) + 1}-${m}-${d}`
    pasture.harvest = { date: harvest, provenance: 'DECLARED', source: 'user' }
    const start: number = raw.ag_year_start.month
    const strip = buildRotationStrip(parseRotationDefinition(raw))
    const firstSown = Math.min(
      ...raw.components.map((c: { sowing: { date: string } }) => agYearOf(c.sowing.date, start)),
    )
    const from = agYearOf(sowing, start) - firstSown + 1
    const to = agYearOf(harvest, start) - firstSown + 1
    expect(to).toBeGreaterThan(from)
    const holding = strip.years
      .filter((year) => year.crops.some((c) => c.component_id === pasture.component_id))
      .map((year) => year.index)
    const span = Array.from({ length: to - from + 1 }, (_, i) => from + i)
    expect(holding).toEqual(span)
    const last = strip.years.find((year) => year.index === to)!
    const kept = last.crops.find((c) => c.component_id === pasture.component_id)!
    expect(kept.kept).toBe(true)
    // The text alternative reads it in the later year as kept.
    expect(stripText(strip)).toContain(
      formatString(strings['plant.strip.year'], {
        n: to,
        crops: formatString(strings['plant.strip.crop_kept'], {
          crop: pasture.crop_id,
          sowing: formatString(strings['plant.strip.month_of_year'], {
            month: monthName(monthOf(sowing)),
            n: from,
          }),
          harvest: monthName(monthOf(harvest)),
        }),
      }),
    )
  })

  // PROPOSED (fix round 1 of S-020): pins the rule of the module comment on
  // the example itself, whose pasture travels with its harvest missing.
  it('a crop whose harvest date is missing appears only in its sowing year, with the reason of the harvest', () => {
    const raw = rawRequest.rotations[2]
    const pasture = raw.components.find((c) => c.purpose === 'pasture')!
    expect(pasture.harvest.date).toBeNull()
    const missing = pasture.harvest.missing!
    const start = raw.ag_year_start.month
    const sown = raw.components.filter((c) => c.sowing.date !== null)
    const first = Math.min(...sown.map((c) => agYearOf(c.sowing.date!, start)))
    const from = agYearOf(pasture.sowing.date!, start) - first + 1
    const strip = buildRotationStrip(parseRotationDefinition(raw))
    const holding = strip.years
      .filter((year) => year.crops.some((c) => c.component_id === pasture.component_id))
      .map((year) => year.index)
    expect(holding).toEqual([from])
    const crop = strip.years
      .find((year) => year.index === from)!
      .crops.find((c) => c.component_id === pasture.component_id)!
    expect(crop.harvest).toEqual({ kind: 'missing', missing })
    expect(crop.kept).toBe(false)
    expect(cropText(crop, from)).toContain(
      missingPatternText(strings['plant.strip.harvest'], missing as { reason: 'NOT_APPLICABLE' }),
    )
  })

  it('a component whose sowing date is missing is listed with its reason and placed in no year', () => {
    const raw = rotationCopy(1)
    const cover = raw.components[1]
    cover.sowing = { date: null, missing: { reason: 'NOT_DECLARED' } }
    const strip = buildRotationStrip(parseRotationDefinition(raw))
    expect(strip.unplaced).toEqual([
      {
        component_id: cover.component_id,
        position: cover.position,
        crop_id: cover.crop_id,
        purpose: cover.purpose,
        missing: { reason: 'NOT_DECLARED' },
      },
    ])
    for (const year of strip.years) {
      expect(year.crops.map((c) => c.component_id)).not.toContain(cover.component_id)
    }
    expect(stripText(strip)).not.toContain(cover.crop_id)
  })

  it('a rotation with no sowing date at all has no year, every crop unplaced, never a guessed year', () => {
    const raw = rotationCopy(0)
    raw.components[0].sowing = { date: null, missing: { reason: 'NOT_DECLARED' } }
    const rotation: RotationDefinition = parseRotationDefinition(raw)
    const strip = buildRotationStrip(rotation)
    expect(strip.years).toEqual([])
    expect(strip.unplaced.map((c) => c.component_id)).toEqual([raw.components[0].component_id])
  })
})

describe('the crop colours: by order of first appearance', () => {
  it('lists each crop once, in the order it first appears in the strips shown', () => {
    const strips = exampleRotations.map(buildRotationStrip)
    const seen: string[] = []
    for (const strip of strips) {
      for (const year of strip.years) {
        for (const crop of year.crops) {
          if (!seen.includes(crop.crop_id)) seen.push(crop.crop_id)
        }
      }
    }
    expect(cropOrder(strips)).toEqual(seen)
  })
})
