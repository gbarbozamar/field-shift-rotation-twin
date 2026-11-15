import { ApiError, postToRoute } from '../seam/runRotationApi'
import { parsePlantAnswer, parseRainStress } from './plantData'
import type { MarginOf, PlantAnswer, RainStressPart, Strictness } from './plantData'

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
 *
 * No number, no wording: pure functions and the fetch boundary only.
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

function isRecord(value: unknown): value is Record<string, unknown> {
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
 * The rain-stress factor the base request declares, or null when it declares
 * none with a value (null, or a factor missing with its reason): then the
 * heavier-rain control has nothing to send.
 */
export function declaredRainFactor(baseRequest: unknown): DeclaredFactor | null {
  const factor = questionsOf(baseRequest).rain_stress_factor
  if (!isRecord(factor)) {
    return null
  }
  const { value, unit, provenance } = factor
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    typeof unit !== 'string' ||
    typeof provenance !== 'string'
  ) {
    return null
  }
  return { value, unit, provenance }
}

/** What the service answered: the answer, and its rain-stress part. */
export interface PlantServiceAnswer {
  answer: PlantAnswer
  rainStress: RainStressPart | null
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
 * Read a 2xx body as the answer to this request. The questions it echoes must
 * be those asked (strictness, margin_of and the factor, as
 * check_answer_against_request requires); otherwise, or when the parser
 * refuses it, ApiError UNEXPECTED.
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
    return { answer, rainStress: parseRainStress(raw.rain_stress ?? null) }
  } catch {
    throw new ApiError('UNEXPECTED')
  }
}

/** Call the route with one request; resolves with the answer read, rejects with an ApiError. */
export async function runPlant(base: string, request: Record<string, unknown>): Promise<PlantServiceAnswer> {
  const body = await postToRoute(plantRunUrl(base), request)
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
