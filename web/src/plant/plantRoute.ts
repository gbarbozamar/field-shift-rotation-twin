import { ApiError, postToRoute } from '../seam/runRotationApi'
import type { MissingPart } from '../components/ValueDisplay'
import { strings } from '../strings'
import { missingPart, parsePlantAnswer, parseRainStress } from './plantData'
import type { MarginOf, PlantAnswer, RainStressPart, Strictness } from './plantData'
import type { MockReport } from '../mockfill/mockFill'

/**
 * The service call of the screen "What should I plant?" (S-021, PROPOSED):
 * POST /api/plant/run (api/plant.py). The body is a PlantRequest and the 200
 * answer a PlantAnswer (contracts/plant_answer/); every 4xx/5xx carries the
 * one error shape of api/errors.py.
 *
 * - Whether a backend is configured is read from VITE_API_URL alone: unset or
 *   blank means no backend, and the screen calls nothing. The localhost
 *   fallback of lib/api.ts is not used here (it stays for the other screens).
 * - The request is the example plant request (example data) with the three
 *   questions the user chose: how strict, the kind of year, and heavier rain
 *   on (the example request's own declared factor, never a typed number) or
 *   off (null: no stress test).
 * - The call goes through postToRoute of the run seam; a 2xx body that the
 *   parser refuses, or an answer to other questions than those asked, is
 *   ApiError UNEXPECTED, never shown as an answer.
 * - A 2xx body with no answer and its reason (the plant layer not built) is
 *   PlantNotAvailableError: the screen shows the reason, not an error.
 *
 * No number: pure functions and the fetch boundary only; the one wording
 * used (the detail of an unreadable request) comes from strings.ts.
 */

/** The route path, with the /api prefix the backend serves under. */
export const PLANT_RUN_PATH = '/api/plant/run'

/** The environment the base address is read from (import.meta.env at build time). */
export interface ApiEnv {
  VITE_API_URL?: string
}

/**
 * The configured backend address, or null when none is configured: unset or
 * blank (only spaces) means no backend. Pure on its argument; the default is
 * the build-time environment.
 */
export function configuredApiBase(env: ApiEnv = import.meta.env): string | null {
  const value = env.VITE_API_URL
  if (value === undefined || value.trim() === '') {
    return null
  }
  return value.trim()
}

/** The full URL of the route on a base address, its trailing slash stripped. */
export function plantRunUrl(base: string): string {
  const trimmed = base.endsWith('/') ? base.slice(0, -1) : base
  return `${trimmed}${PLANT_RUN_PATH}`
}

/** The questions the user chooses on the screen. */
export interface PlantChoices {
  strictness: Strictness
  marginOf: MarginOf
  rain: boolean
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function questionsOf(request: unknown): Record<string, unknown> {
  if (!isRecord(request) || request.contract !== 'plant_request' || !isRecord(request.questions)) {
    throw new Error('invalid-plant-request:no-questions')
  }
  return request.questions
}

/**
 * A copy of the base request with questions.strictness and
 * questions.margin_of replaced, and questions.rain_stress_factor kept as the
 * base request declares it when rain is on, null when it is off. Every other
 * part is copied unchanged; the base request is not changed.
 */
export function plantRequestFor(baseRequest: unknown, choices: PlantChoices): Record<string, unknown> {
  const declared = questionsOf(baseRequest).rain_stress_factor
  const copy = structuredClone(baseRequest) as Record<string, unknown>
  const questions = copy.questions as Record<string, unknown>
  questions.strictness = choices.strictness
  questions.margin_of = choices.marginOf
  questions.rain_stress_factor = choices.rain ? structuredClone(declared ?? null) : null
  return copy
}

/** The rain-stress factor a request declares, as declared: value, unit, provenance. */
export interface DeclaredFactor {
  value: number
  unit: string
  provenance: string
}

/**
 * The rain-stress factor of a request as the screen reads it (fix round 1 of
 * S-021, PROPOSED):
 * - present: a value with its unit and provenance, which heavier rain sends;
 * - declared_missing: the request declares the factor missing, with its
 *   reason (and detail), shown as declared, never replaced by another reason;
 * - none: the request has no factor object at all (null or absent);
 * - unreadable: the request (or its factor) cannot be read, a typed absence
 *   (MISSING_INPUT with the detail of strings key
 *   plant.service.rain_request_invalid_detail), never an exception.
 */
export type RainFactorRead =
  | { kind: 'present'; factor: DeclaredFactor }
  | { kind: 'declared_missing'; missing: MissingPart }
  | { kind: 'none' }
  | { kind: 'unreadable'; missing: MissingPart }

function unreadableFactor(): RainFactorRead {
  return {
    kind: 'unreadable',
    missing: { reason: 'MISSING_INPUT', detail: strings['plant.service.rain_request_invalid_detail'] },
  }
}

/** Reads the rain-stress factor of a request. Pure, and never throws. */
export function readRainFactor(baseRequest: unknown): RainFactorRead {
  try {
    const factor = questionsOf(baseRequest).rain_stress_factor
    if (factor === null || factor === undefined) {
      return { kind: 'none' }
    }
    if (!isRecord(factor)) {
      return unreadableFactor()
    }
    const { value, unit, provenance } = factor
    if (value === null) {
      // As the contract's Value: a missing value carries its missing part.
      if (!isRecord(factor.missing)) {
        return unreadableFactor()
      }
      return {
        kind: 'declared_missing',
        missing: missingPart(factor.missing.reason, factor.missing.detail, 'invalid-rain-stress-factor'),
      }
    }
    if (
      typeof value !== 'number' ||
      !Number.isFinite(value) ||
      typeof unit !== 'string' ||
      typeof provenance !== 'string'
    ) {
      return unreadableFactor()
    }
    return { kind: 'present', factor: { value, unit, provenance } }
  } catch {
    return unreadableFactor()
  }
}

/**
 * The rain-stress factor the base request declares with a value, or null
 * otherwise (none, declared missing, or unreadable: readRainFactor tells
 * which). Never throws.
 */
export function declaredRainFactor(baseRequest: unknown): DeclaredFactor | null {
  const read = readRainFactor(baseRequest)
  return read.kind === 'present' ? read.factor : null
}

/** What the screen reads of its base request once: whether a request can be built, and its factor. */
export interface BaseRequestRead {
  /** False when the request cannot be read: nothing can be sent to the service. */
  readable: boolean
  rain: RainFactorRead
}

/** Reads a base request for the screen. Pure, and never throws. */
export function readBaseRequest(baseRequest: unknown): BaseRequestRead {
  let readable = true
  try {
    questionsOf(baseRequest)
  } catch {
    readable = false
  }
  return { readable, rain: readRainFactor(baseRequest) }
}

/** What the service answered: the answer, and its rain-stress part. */
export interface PlantServiceAnswer {
  answer: PlantAnswer
  rainStress: RainStressPart | null
  /** Present only when the board mixed this answer with example values (mockfill/mockFill.ts). */
  mock?: MockReport
}

/**
 * Whether an echoed factor is the factor asked: both null, or both with the
 * same value, unit and provenance. Compared field by field, not as text, since
 * the service may write the members in another order or add null members.
 */
function sameFactor(echoed: unknown, asked: unknown): boolean {
  if (asked === null || asked === undefined) {
    return echoed === null || echoed === undefined
  }
  if (!isRecord(echoed) || !isRecord(asked)) {
    return false
  }
  return (
    echoed.value === asked.value &&
    echoed.unit === asked.unit &&
    echoed.provenance === asked.provenance
  )
}

/**
 * Whether the rain-stress part of the answer is the one the factor asked
 * calls for, as PlantAnswer._questions of the contract: no factor asked, no
 * part; a factor with a value, the applied form whose factor is that value
 * and whose declared factor is the one asked; a factor declared missing, the
 * missing form with the same reason and detail.
 */
function rainStressMatches(part: RainStressPart | null, rawPart: unknown, asked: unknown): boolean {
  if (asked === null || asked === undefined) {
    return part === null
  }
  if (part === null || !isRecord(asked)) {
    return false
  }
  if (asked.value === null) {
    const missing = isRecord(asked.missing) ? asked.missing : null
    return (
      part.kind === 'missing' &&
      missing !== null &&
      part.missing.reason === missing.reason &&
      (part.missing.detail ?? null) === (missing.detail ?? null)
    )
  }
  return (
    part.kind === 'applied' &&
    part.factor === asked.value &&
    isRecord(rawPart) &&
    sameFactor(rawPart.declared, asked)
  )
}

/** The case_id and field_id of the request's site, or null when it has none. */
function siteOf(request: unknown): { case_id: unknown; field_id: unknown } | null {
  if (!isRecord(request) || !isRecord(request.site)) {
    return null
  }
  return { case_id: request.site.case_id, field_id: request.site.field_id }
}

/**
 * Read a 2xx body as the answer to this request. The questions it echoes must
 * be those asked (strictness, margin_of and the factor, as
 * check_answer_against_request requires), its rain-stress part the one the
 * factor asked calls for, its case_id and field_id those of the request's
 * site, and it is example data when the request is (fix round 1, PROPOSED,
 * as check_answer_against_request); otherwise, or when the parser refuses
 * it, ApiError UNEXPECTED.
 */
export function readPlantServiceAnswer(body: unknown, request: unknown): PlantServiceAnswer {
  try {
    const asked = questionsOf(request)
    const answer = parsePlantAnswer(body)
    const raw = body as Record<string, unknown>
    const echoed = raw.questions as Record<string, unknown>
    if (
      echoed.strictness !== asked.strictness ||
      echoed.margin_of !== asked.margin_of ||
      !sameFactor(echoed.rain_stress_factor, asked.rain_stress_factor)
    ) {
      throw new Error('invalid-plant-answer:questions-not-those-asked')
    }
    if (raw.rain_stress === undefined) {
      throw new Error('invalid-plant-answer:no-rain-stress')
    }
    const rainStress = parseRainStress(raw.rain_stress)
    if (!rainStressMatches(rainStress, raw.rain_stress, asked.rain_stress_factor)) {
      throw new Error('invalid-plant-answer:rain-stress-not-the-factor-asked')
    }
    const site = siteOf(request)
    if (site === null || raw.case_id !== site.case_id || raw.field_id !== site.field_id) {
      throw new Error('invalid-plant-answer:another-field')
    }
    if ((request as Record<string, unknown>).example_data === true && answer.example_data !== true) {
      throw new Error('invalid-plant-answer:example-request-not-example-answer')
    }
    return { answer, rainStress }
  } catch {
    throw new ApiError('UNEXPECTED')
  }
}

/**
 * The service answered 200 with no answer and the reason why (PROPOSED):
 * the route's `{answer: null, answer_missing}` form of api/app.py, sent when
 * the plant layer is not built. A typed absence, not a failure: the screen
 * shows the reason, never an error code.
 */
export class PlantNotAvailableError extends Error {
  readonly missing: MissingPart

  constructor(missing: MissingPart) {
    super('plant-answer-not-available')
    this.name = 'PlantNotAvailableError'
    this.missing = missing
  }
}

/**
 * The reason of a 2xx body that carries no answer, or null when the body is
 * not of that form (it is then read as an answer). A body whose answer is
 * null without a readable reason (a reason code of the conventions, an
 * optional non-empty detail) is ApiError UNEXPECTED: no reason is invented.
 */
export function readAnswerMissing(body: unknown): MissingPart | null {
  if (!isRecord(body) || body.answer !== null) {
    return null
  }
  const missing = body.answer_missing
  if (!isRecord(missing)) {
    throw new ApiError('UNEXPECTED')
  }
  try {
    return missingPart(missing.reason, missing.detail, 'invalid-plant-answer-missing')
  } catch {
    throw new ApiError('UNEXPECTED')
  }
}

/**
 * Call the route with one request; resolves with the answer read, rejects
 * with PlantNotAvailableError when the service has no answer and says why,
 * and with an ApiError otherwise.
 */
export async function runPlant(base: string, request: Record<string, unknown>): Promise<PlantServiceAnswer> {
  const body = await postToRoute(plantRunUrl(base), request)
  const missing = readAnswerMissing(body)
  if (missing !== null) {
    throw new PlantNotAvailableError(missing)
  }
  return readPlantServiceAnswer(body, request)
}

/**
 * The TanStack Query options of one call: cached by base and request (a new
 * call for each distinct request), no retry, no refetch on focus.
 */
export function plantQueryOptions(base: string, request: Record<string, unknown>) {
  return {
    queryKey: ['plant-run', base, request] as const,
    queryFn: (): Promise<PlantServiceAnswer> => runPlant(base, request),
    retry: false as const,
    staleTime: Infinity,
    refetchOnWindowFocus: false as const,
  }
}

/**
 * The query of the screen (fix round 1 of S-021, PROPOSED): the options of
 * one call, enabled only with a backend configured and a request to send
 * (service mode). Disabled, it never calls.
 */
export function plantScreenQueryOptions(base: string | null, request: Record<string, unknown> | null) {
  return {
    ...plantQueryOptions(base ?? '', request ?? {}),
    enabled: base !== null && request !== null,
  }
}
