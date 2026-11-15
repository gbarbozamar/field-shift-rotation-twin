import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import { parseRotationDefinition } from '../rotation/exampleRotation'
import type { AgYearStart, RotationDefinition } from '../rotation/exampleRotation'
import { missingPatternText } from '../components/ValueDisplay'
import type { MissingPart, ProvenanceLabel } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type { StringKey } from '../strings'

/**
 * The strip of crops of one rotation, year by year (S-020, PROPOSED).
 *
 * Where the data comes from. The plant answer carries no crops; the plant
 * request carries the rotations. data/PLACEHOLDER_plant_request.json is the
 * contract example (contracts/plant_answer/examples/), copied unchanged; a
 * test keeps the copy equal to the contract file. Every date in it is example
 * data.
 *
 * What the strip is. One cycle of the declared dates, laid out in
 * agricultural years numbered per C5.3 of contracts/CONVENTIONS.md: an
 * agricultural year begins at the start month of the rotation
 * (ag_year_start.month) and is named by the calendar year it begins in. Year
 * 1 is the agricultural year of the earliest declared sowing date. In each
 * year: the crops sown in it, in sowing order, each with its crop_id, its
 * purpose and the months of its sowing and harvest; a crop whose harvest
 * lies in a later agricultural year (a pasture kept over years) is shown in
 * every year from its sowing through its harvest, marked kept after the
 * first. A crop whose harvest date is missing is shown in its sowing year
 * only, with the reason of the harvest: its end is not guessed. A crop whose
 * sowing date is missing is placed in no year and listed apart with its
 * reason.
 *
 * Not here (OPEN): no crop is called winter or summer, and no bare soil is
 * drawn, because which season a month is depends on the hemisphere. The
 * strip shows the months.
 *
 * Pure: a definition in, a strip out. The text alternative is built from the
 * wording of strings.ts and reads each crop with its purpose; crop ids and
 * purposes render as they travel (they are data). The strip keeps the start
 * of the agricultural year (its month, provisional mark and provenance) and
 * the provenance of its dates, which the screen shows beside it, since the
 * year numbers depend on them.
 */

/** A month of the strip, and the strip year (1, 2, ...) it lies in. */
export interface StripMonth {
  month: number
  year_index: number
}

/** One crop in one year of the strip. */
export interface StripCrop {
  component_id: string
  position: number
  crop_id: string
  purpose: string
  sowing: StripMonth
  harvest: { kind: 'date'; at: StripMonth } | { kind: 'missing'; missing: MissingPart }
  /** True in the years after the year of its sowing (a crop kept over years). */
  kept: boolean
}

export interface StripYear {
  /** 1 for the first agricultural year of the cycle. */
  index: number
  /** The agricultural year (C5.3): the calendar year it begins in. */
  ag_year: number
  crops: StripCrop[]
}

/** A crop whose sowing date is missing: listed with its reason, in no year. */
export interface UnplacedCrop {
  component_id: string
  position: number
  crop_id: string
  purpose: string
  missing: MissingPart
}

/** Where the dates of the strip come from: a provenance label and its source (C4.1). */
export interface DateMark {
  provenance: ProvenanceLabel
  source: string
}

export interface RotationStrip {
  rotation_id: string
  label: string
  repeats: boolean
  /**
   * The start of the agricultural year the strip's years are numbered by
   * (C5.3), with its provisional mark (C5.4) and its provenance.
   */
  ag_year_start: AgYearStart
  /** The provenance of the dates placed in the strip, each pair once, in order of first use. */
  date_marks: DateMark[]
  years: StripYear[]
  unplaced: UnplacedCrop[]
}

// Not imported (fix round 1 of S-020): no module of web/src exports an
// equivalent guard; plantData.ts, exampleRotation.ts and the other parsers
// each keep a private copy. Sharing one would change modules of other units.
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * The rotations of a plant request, each parsed as a rotation definition.
 * Pure: value in, the definitions in request order out, or an Error with a
 * technical code.
 */
export function parsePlantRequestRotations(value: unknown): RotationDefinition[] {
  if (!isRecord(value) || value.contract !== 'plant_request') {
    throw new Error('invalid-plant-request:contract-not-plant-request')
  }
  if (!Array.isArray(value.rotations)) {
    throw new Error('invalid-plant-request:rotations-not-a-list')
  }
  return value.rotations.map(parseRotationDefinition)
}

/**
 * The rotations of a request as the screen reads them: the definitions, or
 * the reason they cannot be shown (fix round 1 of S-020, PROPOSED). A request
 * that does not parse is a typed absence, never an exception at import: the
 * strips say so and the rest of the screen still renders.
 */
export type PlantRotations =
  | { rotations: RotationDefinition[]; missing: null }
  | { rotations: null; missing: MissingPart }

/**
 * Reads the rotations of a plant request. Pure: value in, the definitions or
 * the missing part out. PROPOSED: a request that does not parse is
 * MISSING_INPUT with the detail of strings key
 * plant.strip.request_invalid_detail (the technical code of the parser is not
 * shown: it is not interface wording).
 */
export function readPlantRotations(value: unknown): PlantRotations {
  try {
    return { rotations: parsePlantRequestRotations(value), missing: null }
  } catch {
    return {
      rotations: null,
      missing: { reason: 'MISSING_INPUT', detail: strings['plant.strip.request_invalid_detail'] },
    }
  }
}

/** The rotations of the example request (example data), or why they cannot be read. */
export const plantRotations: PlantRotations = readPlantRotations(rawPlantRequest)

function parts(date: string): { year: number; month: number } {
  const [year, month] = date.split('-').map(Number)
  return { year, month }
}

/** C5.3: the agricultural year a date lies in, for this start month. */
function agYearOf(date: string, startMonth: number): number {
  const { year, month } = parts(date)
  return month >= startMonth ? year : year - 1
}

/** The strip of one rotation definition (see the module comment). */
export function buildRotationStrip(rotation: RotationDefinition): RotationStrip {
  const start = rotation.ag_year_start.month
  const unplaced: UnplacedCrop[] = []
  const sown: { component: RotationDefinition['components'][number]; sowing: string }[] = []
  for (const component of rotation.components) {
    if (component.sowing.date === null) {
      unplaced.push({
        component_id: component.component_id,
        position: component.position,
        crop_id: component.crop_id,
        purpose: component.purpose,
        missing: component.sowing.missing,
      })
    } else {
      sown.push({ component, sowing: component.sowing.date })
    }
  }
  // Sowing order: by date (ISO dates sort as text), then by position.
  sown.sort((a, b) =>
    a.sowing === b.sowing
      ? a.component.position - b.component.position
      : a.sowing < b.sowing
        ? -1
        : 1,
  )
  const date_marks: DateMark[] = []
  for (const { component } of sown) {
    for (const part of [component.sowing, component.harvest]) {
      if (part.date === null) continue
      if (!date_marks.some((m) => m.provenance === part.provenance && m.source === part.source)) {
        date_marks.push({ provenance: part.provenance, source: part.source })
      }
    }
  }
  const head = {
    rotation_id: rotation.rotation_id,
    label: rotation.label,
    repeats: rotation.repeats,
    ag_year_start: { ...rotation.ag_year_start },
    date_marks,
  }
  if (sown.length === 0) {
    return { ...head, years: [], unplaced }
  }
  const first = Math.min(...sown.map((s) => agYearOf(s.sowing, start)))
  const indexOf = (date: string) => agYearOf(date, start) - first + 1
  const placed: { crop: Omit<StripCrop, 'kept'>; from: number; to: number }[] = sown.map(
    ({ component, sowing }) => {
      const from = indexOf(sowing)
      const harvest: StripCrop['harvest'] =
        component.harvest.date === null
          ? { kind: 'missing', missing: component.harvest.missing }
          : {
              kind: 'date',
              at: { month: parts(component.harvest.date).month, year_index: indexOf(component.harvest.date) },
            }
      return {
        crop: {
          component_id: component.component_id,
          position: component.position,
          crop_id: component.crop_id,
          purpose: component.purpose,
          sowing: { month: parts(sowing).month, year_index: from },
          harvest,
        },
        from,
        to: harvest.kind === 'date' ? Math.max(from, harvest.at.year_index) : from,
      }
    },
  )
  const last = Math.max(...placed.map((p) => p.to))
  const years: StripYear[] = []
  for (let index = 1; index <= last; index += 1) {
    years.push({
      index,
      ag_year: first + index - 1,
      crops: placed
        .filter((p) => p.from <= index && index <= p.to)
        .map((p) => ({ ...p.crop, kept: index > p.from })),
    })
  }
  return { ...head, years, unplaced }
}

/** The name of a calendar month (C5.1: month names are interface text). */
export function monthName(month: number): string {
  return strings[`plant.month.${month}` as StringKey]
}

/** A month read from a year of the strip: its name, with its year when it is another. */
function monthText(at: StripMonth, inYear: number): string {
  const name = monthName(at.month)
  return at.year_index === inYear
    ? name
    : formatString(strings['plant.strip.month_of_year'], { month: name, n: at.year_index })
}

/** How one crop reads in one year of the strip. */
export function cropText(crop: StripCrop, inYear: number): string {
  const sowing = monthText(crop.sowing, inYear)
  if (crop.harvest.kind === 'missing') {
    return formatString(strings['plant.strip.crop_harvest_missing'], {
      crop: crop.crop_id,
      sowing,
      harvest: missingPatternText(strings['plant.strip.harvest'], crop.harvest.missing),
    })
  }
  return formatString(strings[crop.kept ? 'plant.strip.crop_kept' : 'plant.strip.crop'], {
    crop: crop.crop_id,
    sowing,
    harvest: monthText(crop.harvest.at, inYear),
  })
}

/**
 * How one crop reads in the text alternative: as cropText, with its purpose,
 * which the strip shows beside it (fix round 1 of S-020, PROPOSED).
 */
export function cropAltText(crop: StripCrop, inYear: number): string {
  return formatString(strings['plant.strip.crop_alt'], {
    crop: cropText(crop, inYear),
    purpose: formatString(strings['plant.strip.purpose'], { purpose: crop.purpose }),
  })
}

/** How one year of the strip reads in its text alternative. */
export function yearText(year: StripYear): string {
  if (year.crops.length === 0) {
    return formatString(strings['plant.strip.year_empty'], { n: year.index })
  }
  return formatString(strings['plant.strip.year'], {
    n: year.index,
    crops: year.crops.map((c) => cropAltText(c, year.index)).join(strings['plant.strip.crop_join']),
  })
}

/** The text alternative of the strip: every year, in order. */
export function stripText(strip: RotationStrip): string {
  return strip.years.map(yearText).join(strings['plant.strip.year_join'])
}

/** How a crop placed in no year reads: what is missing and why. */
export function unplacedText(crop: UnplacedCrop): string {
  return missingPatternText(formatString(strings['plant.strip.unplaced'], { crop: crop.crop_id }), crop.missing)
}

/**
 * The crops of the strips shown, each once, by order of first appearance:
 * the order of the colour palette. Colour is never the only carrier: the
 * crop_id is written beside each swatch.
 */
export function cropOrder(strips: RotationStrip[]): string[] {
  const seen: string[] = []
  for (const strip of strips) {
    for (const year of strip.years) {
      for (const crop of year.crops) {
        if (!seen.includes(crop.crop_id)) seen.push(crop.crop_id)
      }
    }
    for (const crop of strip.unplaced) {
      if (!seen.includes(crop.crop_id)) seen.push(crop.crop_id)
    }
  }
  return seen
}
