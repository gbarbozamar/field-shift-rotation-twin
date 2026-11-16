import rawExamples from '../data/PLACEHOLDER_plant_answers.json'
import exampleRequest from '../data/PLACEHOLDER_plant_request.json'
import { postToRoute } from '../seam/runRotationApi'
import {
  PlantNotAvailableError,
  isRecord,
  plantRunUrl,
  plantScreenQueryOptions,
  readAnswerMissing,
  readPlantServiceAnswer,
} from '../plant/plantRoute'
import type { PlantServiceAnswer } from '../plant/plantRoute'

/**
 * Mixed answers (l3/original-mock, PROPOSED): the board asks the real backend
 * and, only where the backend answers "missing", shows the matching part of
 * the repository's example answer instead, marked as mock on screen.
 *
 * - Off unless VITE_MOCK_FILL is exactly "on"; off, nothing here runs.
 * - The fill works on the raw JSON body, before the screen's own parser reads
 *   it, so a filled body still has to pass every check of the contract.
 * - It fills only when the example belongs to the same question: the request
 *   is the example request (same site, rotations, economic facts and limit),
 *   and every margin and soil loss the backend did compute is the example's
 *   number. Otherwise nothing is filled and the report says why (refused).
 * - What follows from a filled value (the limit verdicts, the answer, its
 *   cost, the tipping price) is taken from the example too, and reported, so
 *   no real verdict is ever shown next to a mock soil loss.
 */

export interface MockReport {
  /** The whole answer is the example: the backend had no plant answer. */
  whole: boolean
  /** The kinds of year (or average) whose soil loss was filled (the backend computed the others). */
  soilKinds: string[]
  /** The kinds of year of the record were filled. */
  record: boolean
  /** The kinds of year whose margin was filled (the backend computed the others). */
  marginKinds: string[]
  /** The verdicts, the answer, its cost and the tipping price were taken from the example. */
  verdicts: boolean
  /** Why nothing was filled although the backend left values missing; null when not refused. */
  refused: 'incoherent' | 'no_example' | null
}

export type MixedServiceAnswer = PlantServiceAnswer & { mock: MockReport }

export interface MockEnv {
  VITE_MOCK_FILL?: string
}

export function mockFillOn(env: MockEnv = import.meta.env): boolean {
  return env.VITE_MOCK_FILL === 'on'
}

type Json = Record<string, unknown>

/** A measured value the backend could not compute: no value, a reason. */
function isMissingValue(value: unknown): boolean {
  return isRecord(value) && value.value === null && typeof value.reason === 'string'
}

/** A fresh report with nothing filled (a new object each time: reports are never shared). */
function nothingFilled(refused: MockReport['refused'] = null): MockReport {
  return { whole: false, soilKinds: [], record: false, marginKinds: [], verdicts: false, refused }
}

const SAME_AS_EXAMPLE = ['site', 'rotations', 'economic_facts', 'soil_loss_limit'] as const

/** True when the request asks about exactly the example request's field, rotations, facts and limit. */
export function isExampleRequest(request: unknown): boolean {
  if (!isRecord(request)) return false
  const example = exampleRequest as Json
  return SAME_AS_EXAMPLE.every((key) => JSON.stringify(request[key]) === JSON.stringify(example[key]))
}

/** The example answer to the same questions as a request, or null when the examples hold none. */
export function exampleFor(request: unknown): Json | null {
  if (!isRecord(request) || !isRecord(request.questions)) return null
  const q = request.questions
  const rainOn = q.rain_stress_factor !== null && q.rain_stress_factor !== undefined
  const found = (rawExamples as { answers: Json[] }).answers.find((answer) => {
    const aq = answer.questions as Json
    const exampleRain = aq.rain_stress_factor !== null && aq.rain_stress_factor !== undefined
    return aq.strictness === q.strictness && aq.margin_of === q.margin_of && exampleRain === rainOn
  })
  return found === undefined ? null : structuredClone(found)
}

function optionsOf(body: Json): Json[] {
  return Array.isArray(body.options) ? (body.options as Json[]) : []
}

/** True when every value the backend computed in this block equals the example's at the same kind. */
function sameComputed(block: unknown, exampleBlock: unknown): boolean {
  if (!isRecord(block) || !isRecord(exampleBlock)) return false
  return Object.keys(block).every((kind) => {
    const value = (block[kind] as Json | null)?.value
    return value === null || value === undefined || value === (exampleBlock[kind] as Json | null)?.value
  })
}

/** Same rotations in the same order, and every margin and soil loss the backend computed equal to the example's. */
function coherent(real: Json, example: Json): boolean {
  const a = optionsOf(real)
  const b = optionsOf(example)
  if (a.length === 0 || a.length !== b.length) return false
  return a.every((option, i) => {
    const other = b[i]
    if (option.rotation_id !== other.rotation_id) return false
    return sameComputed(option.margin, other.margin) && sameComputed(option.soil_loss, other.soil_loss)
  })
}

const VERDICT_KEYS = ['answer', 'chosen', 'reason', 'detail', 'tied', 'limit_cost', 'tipping_price'] as const
const OPTION_VERDICT_KEYS = ['state', 'limit', 'limit_check'] as const

/**
 * The body with its missing parts filled from the example, and the report of
 * what was filled. Pure: neither argument is changed.
 */
export function fillPlantBody(
  realBody: unknown,
  example: Json | null,
  request: unknown,
): { body: unknown; mock: MockReport } {
  if (!isRecord(realBody)) return { body: realBody, mock: nothingFilled() }
  const real = structuredClone(realBody)
  const soilMissing = optionsOf(real).some((option) =>
    isRecord(option.soil_loss) && Object.values(option.soil_loss).some(isMissingValue),
  )
  const recordMissing =
    isRecord(real.kinds_of_year) &&
    Array.isArray(real.kinds_of_year.years) &&
    real.kinds_of_year.years.length !== 0 &&
    (real.kinds_of_year.years as Json[]).every((year) => year.kind === null)
  if (!soilMissing && !recordMissing) return { body: real, mock: nothingFilled() }
  if (example === null) return { body: real, mock: nothingFilled('no_example') }
  if (!isExampleRequest(request) || !coherent(real, example)) {
    return { body: real, mock: nothingFilled('incoherent') }
  }

  const mock = nothingFilled()
  const exampleOptions = optionsOf(example)
  optionsOf(real).forEach((option, i) => {
    const losses = option.soil_loss as Json
    const exampleLosses = exampleOptions[i].soil_loss as Json
    for (const kind of Object.keys(losses)) {
      if (isMissingValue(losses[kind]) && isRecord(exampleLosses[kind]) && exampleLosses[kind].value !== null) {
        losses[kind] = exampleLosses[kind]
        if (!mock.soilKinds.includes(kind)) mock.soilKinds.push(kind)
      }
    }
  })
  optionsOf(real).forEach((option, i) => {
    const margins = option.margin as Json
    const exampleMargins = exampleOptions[i].margin as Json
    for (const kind of Object.keys(margins)) {
      if (isMissingValue(margins[kind]) && isRecord(exampleMargins[kind]) && exampleMargins[kind].value !== null) {
        margins[kind] = exampleMargins[kind]
        if (!mock.marginKinds.includes(kind)) mock.marginKinds.push(kind)
      }
    }
  })
  if (recordMissing && isRecord(example.kinds_of_year)) {
    real.kinds_of_year = example.kinds_of_year
    mock.record = true
  }
  if (mock.soilKinds.length !== 0 || mock.record || mock.marginKinds.length !== 0) {
    for (const key of VERDICT_KEYS) real[key] = example[key]
    optionsOf(real).forEach((option, i) => {
      for (const key of OPTION_VERDICT_KEYS) option[key] = exampleOptions[i][key]
    })
    mock.verdicts = true
  }
  return { body: real, mock }
}

/**
 * The board's call with mixing on: the real route first; a missing plant
 * answer is replaced whole by the example (reported), missing parts are
 * filled; then the screen's own parser reads the result.
 */
export async function runPlantMixed(base: string, request: Record<string, unknown>): Promise<MixedServiceAnswer> {
  const body = await postToRoute(plantRunUrl(base), request)
  const example = exampleFor(request)
  const missing = readAnswerMissing(body)
  if (missing !== null) {
    // The whole example stands in only for the example request itself: for
    // other rotations or facts the example would answer another question.
    if (example === null || !isExampleRequest(request)) throw new PlantNotAvailableError(missing)
    const whole: MockReport = { ...nothingFilled(), whole: true, record: true, verdicts: true }
    return { ...readPlantServiceAnswer(example, request), mock: whole }
  }
  const { body: filled, mock } = fillPlantBody(body, example, request)
  return { ...readPlantServiceAnswer(filled, request), mock }
}

/** The query options of the board with mixing on: the screen's call options, another key and query function. */
export function mixedQueryOptions(base: string | null, request: Record<string, unknown> | null) {
  return {
    ...plantScreenQueryOptions(base, request),
    queryKey: ['plant-run-mixed', base ?? '', request ?? {}] as const,
    queryFn: (): Promise<PlantServiceAnswer> => runPlantMixed(base ?? '', request ?? {}),
  }
}

/** The report a service answer carries, or null when it was not mixed. */
export function mockReportOf(answer: PlantServiceAnswer): MockReport | null {
  return answer.mock ?? null
}
