import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import rawDemoRotations from '../data/demo_rotations_d128.json'

/**
 * The rotations a user puts together on the board (PROPOSED, l3/board):
 * "duplicate and edit". Pure functions on the rotation definitions of a plant
 * request, as plain data.
 *
 * What the user can do, and why it is honest. A rotation is a grid of years
 * by two sowing windows (winter crops: sown March to June; summer crops: sown
 * July to February), each slot a crop of the catalogue or nothing. Every crop of the
 * catalogue comes with the dates and management a rotation of this
 * repository already declares for it (the example plant request, the
 * demonstration rotations of D128), moved to the year of its slot; the user
 * can still set each date (DECLARED, source user). A crop the request
 * declares no economic facts for (wheat, maize) needs the user's own price,
 * cost and yields before it can be compared: no number is invented.
 *
 * What is checked here is what the plant request refuses (three to five
 * rotations, the soybean crop sown by one of them) and what makes no
 * rotation (no crop, no name). Everything else is checked by the service,
 * which answers ROTATION_INVALID.
 */

export const MIN_ROTATIONS = 3
export const MAX_ROTATIONS = 5

/** One dated part of a component: a date, or missing with its reason. */
export interface DraftDate {
  date: string | null
  [key: string]: unknown
}

export interface DraftComponent {
  component_id: string
  position: number
  crop_id: string
  purpose: string
  sowing: DraftDate
  harvest: DraftDate
  [key: string]: unknown
}

export interface DraftRotation {
  rotation_id: string
  label: string
  components: DraftComponent[]
  [key: string]: unknown
}

const USER_ROTATION_PREFIX = 'user-rotation-'

/** True for a rotation the user made on the board: it is named by the user. */
export function isUserRotation(rotationId: string): boolean {
  return rotationId.startsWith(USER_ROTATION_PREFIX)
}

function copy<T>(value: T): T {
  return structuredClone(value)
}

/** The rotations of the example request, as a draft to start from. */
export function exampleRotations(): DraftRotation[] {
  return copy(rawPlantRequest.rotations) as unknown as DraftRotation[]
}

/** The crops the tipping price is asked for: the soybean crops of the request. */
export function soybeanCropIds(): string[] {
  return [...rawPlantRequest.questions.soybean_crop_ids]
}

/** The components in sowing order (a missing date last), renumbered from 1. */
function ordered(components: DraftComponent[]): DraftComponent[] {
  return [...components]
    .sort((a, b) => {
      if (a.sowing.date === b.sowing.date) return 0
      if (a.sowing.date === null) return 1
      if (b.sowing.date === null) return -1
      return a.sowing.date < b.sowing.date ? -1 : 1
    })
    .map((component, index) => ({ ...component, position: index + 1, component_id: `c${index + 1}` }))
}

function replaced(rotations: DraftRotation[], index: number, rotation: DraftRotation): DraftRotation[] {
  return rotations.map((each, i) => (i === index ? rotation : each))
}

/** A copy of a rotation as a new rotation of the user, named as given; unchanged at the limit of five. */
export function duplicateRotation(rotations: DraftRotation[], index: number, label: string): DraftRotation[] {
  if (rotations.length >= MAX_ROTATIONS) {
    return rotations
  }
  let n = 1
  while (rotations.some((each) => each.rotation_id === `${USER_ROTATION_PREFIX}${n}`)) n += 1
  return [...rotations, { ...copy(rotations[index]), rotation_id: `${USER_ROTATION_PREFIX}${n}`, label }]
}

/**
 * An example rotation the user changed becomes the user's: a new identifier
 * and the name given, so an example label never names crops it no longer
 * holds. A rotation of the user is left as it is.
 */
export function asUserRotation(rotations: DraftRotation[], index: number, label: string): DraftRotation[] {
  if (isUserRotation(rotations[index].rotation_id)) return rotations
  let n = 1
  while (rotations.some((each) => each.rotation_id === `${USER_ROTATION_PREFIX}${n}`)) n += 1
  return replaced(rotations, index, { ...rotations[index], rotation_id: `${USER_ROTATION_PREFIX}${n}`, label })
}

export function removeRotation(rotations: DraftRotation[], index: number): DraftRotation[] {
  return rotations.filter((_, i) => i !== index)
}

export function renameRotation(rotations: DraftRotation[], index: number, label: string): DraftRotation[] {
  return replaced(rotations, index, { ...rotations[index], label })
}

/**
 * Sets the sowing or harvest date of a component, as the user declares it.
 * Only a part that already carries a date can be set: a harvest that is
 * missing with its reason (a cover crop, a pasture) stays so.
 */
export function setComponentDate(
  rotations: DraftRotation[],
  index: number,
  componentId: string,
  part: 'sowing' | 'harvest',
  date: string,
): DraftRotation[] {
  const rotation = rotations[index]
  const components = rotation.components.map((component) =>
    component.component_id === componentId && component[part].date !== null && date !== ''
      ? { ...component, [part]: { ...component[part], date } }
      : component,
  )
  // Not put in sowing order here: the user may be typing the date, and a
  // crop that moved under the cursor would take the next keystroke.
  // normalizeDraft orders them when the draft is compared.
  return replaced(rotations, index, { ...rotation, components })
}

/** The draft with the crops of each rotation in sowing order and renumbered: what is sent. */
export function normalizeDraft(rotations: DraftRotation[]): DraftRotation[] {
  return rotations.map((rotation) => ({ ...rotation, components: ordered(rotation.components) }))
}

/** What keeps a draft from being compared. */
export type DraftProblem =
  | { kind: 'too_few' }
  | { kind: 'too_many' }
  | { kind: 'no_soybean' }
  | { kind: 'no_crop'; index: number }
  | { kind: 'no_name'; index: number }
  /** A crop is harvested before it is sown: the rotation definition refuses it. */
  | { kind: 'harvest_before_sowing'; index: number; crop_id: string }
  /** A crop is sown before the crop before it is harvested. */
  | { kind: 'overlap'; index: number; crop_id: string; after: string }

/** The problems of a draft, in a fixed order; none means it can be sent. */
export function draftProblems(rotations: DraftRotation[]): DraftProblem[] {
  const problems: DraftProblem[] = []
  if (rotations.length < MIN_ROTATIONS) problems.push({ kind: 'too_few' })
  if (rotations.length > MAX_ROTATIONS) problems.push({ kind: 'too_many' })
  const soybean = soybeanCropIds()
  if (!rotations.some((rotation) => rotation.components.some((c) => soybean.includes(c.crop_id)))) {
    problems.push({ kind: 'no_soybean' })
  }
  rotations.forEach((rotation, index) => {
    if (rotation.components.length === 0) problems.push({ kind: 'no_crop', index })
    if (rotation.label.trim() === '') problems.push({ kind: 'no_name', index })
    for (const component of rotation.components) {
      const sown = component.sowing.date
      const harvested = component.harvest.date
      // ISO dates compare as text.
      if (sown !== null && harvested !== null && harvested < sown) {
        problems.push({ kind: 'harvest_before_sowing', index, crop_id: component.crop_id })
      }
    }
    const sorted = ordered(rotation.components)
    for (let i = 1; i < sorted.length; i++) {
      const before = sorted[i - 1].harvest.date
      const sown = sorted[i].sowing.date
      if (before !== null && sown !== null && sown < before) {
        problems.push({ kind: 'overlap', index, crop_id: sorted[i].crop_id, after: sorted[i - 1].crop_id })
      }
    }
  })
  return problems
}

/** True when two drafts are the same rotations in the same order. */
export function sameDraft(a: DraftRotation[], b: DraftRotation[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

// --- the season grid -------------------------------------------------------------

export type Season = 'winter' | 'summer'
export const SEASONS: readonly Season[] = ['winter', 'summer']

/** The calendar year of the first row of the grid: the year of the example's first sowing. */
export const BASE_YEAR: number = Number(
  (rawPlantRequest.rotations[0].components[0].sowing.date as string).slice(0, 4),
)

/** A crop of the catalogue: a component as a rotation of the repository declares it, and its season. */
export interface CatalogueCrop {
  crop_id: string
  season: Season
  template: DraftComponent
}

/** The sowing window a date falls in: March to June is winter, July to February is summer. */
export function seasonOfDate(date: string): Season {
  const month = Number(date.slice(5, 7))
  return month >= 3 && month <= 6 ? 'winter' : 'summer'
}

/** The row of the grid a sowing date belongs to (a summer crop sown in January or February belongs to the row before). */
export function rowOfDate(date: string): number {
  const year = Number(date.slice(0, 4))
  const month = Number(date.slice(5, 7))
  return year - BASE_YEAR - (month <= 2 ? 1 : 0)
}

function templatesOf(rotations: DraftRotation[]): DraftComponent[] {
  return rotations.flatMap((rotation) => rotation.components)
}

/**
 * The catalogue: each crop the example request or the demonstration rotations
 * sow, once, with the first component that declares it a sowing date. A crop
 * the request declares economic facts for comes from the request.
 */
export function cropCatalogue(): CatalogueCrop[] {
  const sources = [...templatesOf(exampleRotations()), ...templatesOf(copy(rawDemoRotations) as unknown as DraftRotation[])]
  const catalogue: CatalogueCrop[] = []
  for (const component of sources) {
    if (component.sowing.date === null) continue
    if (catalogue.some((each) => each.crop_id === component.crop_id)) continue
    // The soybean of the demonstration rotations is the request's soybean under another id.
    if (component.crop_id === 'soybean') continue
    catalogue.push({ crop_id: component.crop_id, season: seasonOfDate(component.sowing.date), template: copy(component) })
  }
  return catalogue
}

/** The second-crop soybean of D128: the dates a soybean takes when sown after a winter grain of its row. */
function secondCropSoybean(): DraftComponent | null {
  for (const rotation of copy(rawDemoRotations) as unknown as DraftRotation[]) {
    const i = rotation.components.findIndex((c) => c.crop_id === 'soybean')
    if (i > 0 && rotation.components[i - 1].purpose === 'grain') return rotation.components[i]
  }
  return null
}

/** A date of a template moved so its sowing falls in the given row (the harvest keeps its distance in years). */
function shifted(date: string, rowShift: number): string {
  return `${Number(date.slice(0, 4)) + rowShift}${date.slice(4)}`
}

function placed(template: DraftComponent, row: number): DraftComponent {
  const sown = template.sowing.date as string
  const rowShift = row - rowOfDate(sown)
  const component = copy(template)
  component.sowing = { ...component.sowing, date: shifted(sown, rowShift) }
  if (component.harvest.date !== null) {
    component.harvest = { ...component.harvest, date: shifted(component.harvest.date, rowShift) }
  }
  return component
}

/** What a slot of the grid holds: a crop sown there, a crop still standing from before, or nothing. */
export type SlotContent =
  | { kind: 'sown'; crop_id: string; component_id: string }
  | { kind: 'continues'; crop_id: string }
  | { kind: 'empty' }

/** The month a slot starts, to tell what is still standing in it. */
function slotStart(row: number, season: Season): string {
  return season === 'winter' ? `${BASE_YEAR + row}-03-01` : `${BASE_YEAR + row}-07-01`
}

/** The grid of a rotation: for each row (as many as given, or as its crops need) and season, its content. */
export function gridOf(rotation: DraftRotation, minRows = 1): SlotContent[][] {
  const sorted = ordered(rotation.components)
  const needed = sorted.reduce((rows, c) => (c.sowing.date === null ? rows : Math.max(rows, rowOfDate(c.sowing.date) + 1)), 1)
  const rows = Math.max(minRows, needed)
  return Array.from({ length: rows }, (_, row) =>
    SEASONS.map((season): SlotContent => {
      const sown = rotation.components.find(
        (c) => c.sowing.date !== null && rowOfDate(c.sowing.date) === row && seasonOfDate(c.sowing.date) === season,
      )
      if (sown !== undefined) return { kind: 'sown', crop_id: sown.crop_id, component_id: sown.component_id }
      // A crop with no harvest date (a cover crop, a pasture) stands until the next sowing.
      const start = slotStart(row, season)
      const before = sorted.filter((c) => c.sowing.date !== null && (c.sowing.date as string) < start)
      const last = before[before.length - 1]
      if (last !== undefined && last.harvest.date === null) {
        const next = sorted.find((c) => c.sowing.date !== null && (c.sowing.date as string) > (last.sowing.date as string))
        if (next === undefined || (next.sowing.date as string) >= start) return { kind: 'continues', crop_id: last.crop_id }
      }
      return { kind: 'empty' }
    }),
  )
}

/**
 * Puts a crop of the catalogue in a slot (or nothing, with null): the crop
 * sown there before is taken out, the new one comes with its template's dates
 * moved to the slot's row. A soybean in the summer of a row with a winter
 * grain takes the second-crop dates of D128, and the soybean's own dates
 * otherwise (so a date the user typed on that soybean is reset by the change).
 */
export function setSlot(rotations: DraftRotation[], index: number, row: number, season: Season, cropId: string | null): DraftRotation[] {
  const rotation = rotations[index]
  const inSlot = (c: DraftComponent, r: number, s: Season) =>
    c.sowing.date !== null && rowOfDate(c.sowing.date) === r && seasonOfDate(c.sowing.date) === s
  let components = rotation.components.filter((c) => !inSlot(c, row, season))
  if (cropId !== null) {
    const crop = cropCatalogue().find((each) => each.crop_id === cropId && each.season === season)
    if (crop === undefined) return rotations
    components = [...components, placed(crop.template, row)]
  }
  // The soybean of the row's summer follows the row's winter: second-crop dates after a winter grain.
  const soybean = components.find((c) => inSlot(c, row, 'summer') && soybeanCropIds().includes(c.crop_id))
  if (soybean !== undefined) {
    const winterGrain = components.some((c) => inSlot(c, row, 'winter') && c.purpose === 'grain')
    const second = secondCropSoybean()
    const catalogueSoybean = cropCatalogue().find((each) => each.crop_id === soybean.crop_id)
    const template = winterGrain && second !== null ? { ...copy(second), crop_id: soybean.crop_id } : catalogueSoybean?.template
    if (template !== undefined) {
      components = [...components.filter((c) => c !== soybean), placed(template, row)]
    }
  }
  return replaced(rotations, index, { ...rotation, components: ordered(components) })
}

/** Takes the last row of a rotation away, with every crop sown in it. */
export function dropLastRow(rotations: DraftRotation[], index: number, rows: number): DraftRotation[] {
  const rotation = rotations[index]
  const last = rows - 1
  const kept = rotation.components.filter((c) => c.sowing.date === null || rowOfDate(c.sowing.date) < last)
  return replaced(rotations, index, { ...rotation, components: ordered(kept) })
}

/** The crops the rotations sow, once each, in order of first use. */
export function cropsUsed(rotations: DraftRotation[]): string[] {
  const used: string[] = []
  for (const rotation of rotations) for (const c of rotation.components) if (!used.includes(c.crop_id)) used.push(c.crop_id)
  return used
}
