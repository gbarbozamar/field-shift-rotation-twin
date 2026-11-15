import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'

/**
 * The rotations a user puts together on the board (PROPOSED, l3/board):
 * "duplicate and edit". Pure functions on the rotation definitions of a plant
 * request, as plain data.
 *
 * What the user can do, and why it is honest. A rotation is built from the
 * crops the request already declares economic facts for: no price, cost or
 * yield is added, so no number is invented. The user duplicates a rotation,
 * names it, takes crops in or out, and declares its sowing and harvest dates;
 * a date the user sets is a declaration of the user (DECLARED, source user,
 * as the dates of the request already are). A crop comes in with the dates
 * and the management the request declares for it.
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

/**
 * The crops a rotation can be built from: each crop the rotations of the
 * example request sow, once, with the dates and the management declared for
 * its first occurrence. They are the crops the request declares economic
 * facts for.
 */
export function cropLibrary(): DraftComponent[] {
  const library: DraftComponent[] = []
  for (const rotation of exampleRotations()) {
    for (const component of rotation.components) {
      if (!library.some((each) => each.crop_id === component.crop_id)) {
        library.push(component)
      }
    }
  }
  return library
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

export function removeRotation(rotations: DraftRotation[], index: number): DraftRotation[] {
  return rotations.filter((_, i) => i !== index)
}

export function renameRotation(rotations: DraftRotation[], index: number, label: string): DraftRotation[] {
  return replaced(rotations, index, { ...rotations[index], label })
}

/** Takes a crop out of a rotation, or brings it in as the library declares it. */
export function toggleCrop(rotations: DraftRotation[], index: number, cropId: string): DraftRotation[] {
  const rotation = rotations[index]
  const has = rotation.components.some((component) => component.crop_id === cropId)
  const template = cropLibrary().find((component) => component.crop_id === cropId)
  if (!has && template === undefined) {
    return rotations
  }
  const components = has
    ? rotation.components.filter((component) => component.crop_id !== cropId)
    : [...rotation.components, copy(template!)]
  return replaced(rotations, index, { ...rotation, components: ordered(components) })
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
  })
  return problems
}

/** True when two drafts are the same rotations in the same order. */
export function sameDraft(a: DraftRotation[], b: DraftRotation[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
