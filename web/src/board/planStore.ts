import { useSyncExternalStore } from 'react'
import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import { exampleCase } from '../identity/exampleCase'
import { initialPlantState, plantScreenReducer } from '../plant/PlantScreen'
import type { PlantScreenState } from '../plant/PlantScreen'
import { readBaseRequest } from '../plant/plantRoute'
import { siteReferenceOf } from '../seam/RotationRun'
import { applyFacts, declaredCropIds, readFactUnits, readFacts } from './factsDraft'
import type { FactsDraft } from './factsDraft'
import { cropsUsed, exampleRotations } from './rotationDraft'
import type { DraftRotation } from './rotationDraft'

/**
 * The user's plan on the board, kept for the whole visit (PROPOSED,
 * l3/original-mock): the questions, the rotations compared and being edited,
 * the numbers compared and being edited, and the rain factor. The board, the
 * full report and the print sheet read the same plan, so leaving the board
 * loses nothing and every screen speaks of the same question. A small store,
 * like the selected field of identity/selection.
 */

export const REQUEST_READ = readBaseRequest(rawPlantRequest)
export const EXAMPLE_FACTS: FactsDraft = readFacts(rawPlantRequest)
export const FACT_UNITS = readFactUnits(rawPlantRequest)
const DECLARED_CROPS = declaredCropIds(rawPlantRequest)

/** The rain factor the example request declares; null when it declares none to send. */
export const REQUEST_RAIN_VALUE: number | null = REQUEST_READ.rain.kind === 'present' ? REQUEST_READ.rain.factor.value : null

/** The crops these rotations sow that the request declares no economic facts for. */
export function extraCropIds(rotations: DraftRotation[]): string[] {
  return cropsUsed(rotations).filter((id) => !DECLARED_CROPS.includes(id))
}

export interface Plan {
  state: PlantScreenState
  sent: DraftRotation[]
  draft: DraftRotation[]
  factsSent: FactsDraft
  factsDraft: FactsDraft
  rainValue: number | null
}

/** The board asks as soon as a field is picked: the questions start in service mode. */
export function initialBoardState(): PlantScreenState {
  return plantScreenReducer(initialPlantState(), { type: 'ask' })
}

export function initialPlan(): Plan {
  return {
    state: initialBoardState(),
    sent: exampleRotations(),
    draft: exampleRotations(),
    factsSent: EXAMPLE_FACTS,
    factsDraft: EXAMPLE_FACTS,
    rainValue: REQUEST_RAIN_VALUE,
  }
}

// Built on first use: this module and the plant screen import each other.
let plan: Plan | null = null
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getPlan(): Plan {
  if (plan === null) plan = initialPlan()
  return plan
}

/** Changes the plan; every screen that reads it re-renders. */
export function updatePlan(change: (current: Plan) => Plan): void {
  plan = change(getPlan())
  for (const listener of listeners) listener()
}

/** Back to the example plan (tests, and the "back to the example" actions). */
export function resetPlan(): void {
  updatePlan(() => initialPlan())
}

export function usePlan(): Plan {
  return useSyncExternalStore(subscribe, getPlan, getPlan)
}

/** The field a plan is asked for: the one picked, or the example request's field when none is. */
export function planFieldId(selectedFieldId: string | null): string {
  return selectedFieldId ?? rawPlantRequest.site.field_id
}

/** The site of a field of the example case: the centre of its outline; null when it has none. */
export function siteOf(fieldId: string) {
  const field = exampleCase.fields.find((each) => each.field_id === fieldId) ?? null
  return field === null ? null : siteReferenceOf(exampleCase.case_id, field)
}

/** A copy of a request whose declared rain factor carries this value (kept as declared otherwise). */
function withRainFactor(request: Record<string, unknown>, value: number | null): Record<string, unknown> {
  if (value === null) return request
  const questions = request.questions as Record<string, unknown>
  const factor = questions.rain_stress_factor as Record<string, unknown> | null
  if (factor !== null && factor !== undefined) factor.value = value
  return request
}

/**
 * The plant request of a plan for a field: the example request with the
 * field's site (the centre of its outline), the compared rotations and
 * numbers, and the rain factor, every part naming that field. Null when the
 * field has no outline in the case.
 */
export function planBaseRequest(current: Plan, fieldId: string): Record<string, unknown> | null {
  const site = siteOf(fieldId)
  if (site === null) return null
  const rotations = current.sent.map((rotation) => ({ ...rotation, field_id: fieldId }))
  const request = applyFacts({ ...rawPlantRequest, site, rotations }, current.factsSent)
  ;(request.economic_facts as Record<string, unknown>).field_id = fieldId
  return withRainFactor(request, current.rainValue)
}
