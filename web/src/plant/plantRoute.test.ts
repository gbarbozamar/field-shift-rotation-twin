import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import rawAnswer from '../data/PLACEHOLDER_plant_answer.json'
import rawAnswers from '../data/PLACEHOLDER_plant_answers.json'
import { ApiError } from '../seam/runRotationApi'
import {
  PLANT_RUN_PATH,
  configuredApiBase,
  declaredRainFactor,
  plantQueryOptions,
  plantRequestFor,
  plantRunUrl,
  runPlant,
} from './plantRoute'

/**
 * Acceptance test of the service call of "What should I plant?" (S-021).
 * PROPOSED, designed before the code. fetch is replaced with a stub in every
 * case: never a real network call, never the deployed service. Every expected
 * value is read from the example files (example data), never typed here.
 *
 * Cases of the brief covered here: (2) plantRequestFor; the fetcher side of
 * (3), (4), (5), (6); (7) a new call for each distinct request, cached by
 * request. The screen side is in PlantService.test.tsx.
 */

const BASE = 'http://service.invalid/'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function caughtError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('the promise was expected to reject')
}

/** The example answer of the generated set that echoes these questions. */
function answerFor(body: { questions: { strictness: string; margin_of: string } }): unknown {
  const found = rawAnswers.answers.find(
    (a) =>
      a.questions.strictness === body.questions.strictness &&
      a.questions.margin_of === body.questions.margin_of,
  )
  if (found === undefined) throw new Error('no example answer for these questions')
  return found
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('configuredApiBase: a backend is configured only when VITE_API_URL is set and not blank', () => {
  it('unset or blank means no backend', () => {
    expect(configuredApiBase({})).toBeNull()
    expect(configuredApiBase({ VITE_API_URL: undefined })).toBeNull()
    expect(configuredApiBase({ VITE_API_URL: '' })).toBeNull()
    expect(configuredApiBase({ VITE_API_URL: '   ' })).toBeNull()
  })

  it('a set address is the base, and the route URL strips its trailing slash', () => {
    expect(configuredApiBase({ VITE_API_URL: BASE })).toBe(BASE)
    expect(plantRunUrl(BASE)).toBe(`${BASE.slice(0, -1)}${PLANT_RUN_PATH}`)
    expect(plantRunUrl(BASE.slice(0, -1))).toBe(`${BASE.slice(0, -1)}${PLANT_RUN_PATH}`)
    expect(PLANT_RUN_PATH).toBe('/api/plant/run')
  })
})

describe('plantRequestFor (2)', () => {
  const choices = { strictness: 'every_kind', marginOf: 'la_nina' } as const

  it('keeps every part of the example request but the three questions', () => {
    const request = plantRequestFor(rawRequest, { ...choices, rain: true }) as typeof rawRequest
    const { questions, ...rest } = request
    const { questions: baseQuestions, ...baseRest } = rawRequest
    expect(rest).toEqual(baseRest)
    expect(questions.soybean_crop_ids).toEqual(baseQuestions.soybean_crop_ids)
    expect(questions.soybean_price_range).toEqual(baseQuestions.soybean_price_range)
    expect(questions.strictness).toBe(choices.strictness)
    expect(questions.margin_of).toBe(choices.marginOf)
    expect(Object.keys(questions).sort()).toEqual(Object.keys(baseQuestions).sort())
  })

  it("rain on gives the example's own factor object; rain off gives null", () => {
    const on = plantRequestFor(rawRequest, { ...choices, rain: true }) as typeof rawRequest
    expect(on.questions.rain_stress_factor).toEqual(rawRequest.questions.rain_stress_factor)
    const off = plantRequestFor(rawRequest, { ...choices, rain: false }) as {
      questions: { rain_stress_factor: unknown }
    }
    expect(off.questions.rain_stress_factor).toBeNull()
  })

  it('never changes the example request it copies', () => {
    const before = JSON.stringify(rawRequest)
    plantRequestFor(rawRequest, { ...choices, rain: false })
    expect(JSON.stringify(rawRequest)).toBe(before)
  })

  it('reads the declared factor of the example request, as declared', () => {
    const factor = rawRequest.questions.rain_stress_factor
    expect(declaredRainFactor(rawRequest)).toEqual({
      value: factor.value,
      unit: factor.unit,
      provenance: factor.provenance,
    })
    const none = structuredClone(rawRequest) as { questions: { rain_stress_factor: unknown } }
    none.questions.rain_stress_factor = null
    expect(declaredRainFactor(none)).toBeNull()
  })
})

describe('runPlant: the route, with fetch stubbed', () => {
  const request = plantRequestFor(rawRequest, {
    strictness: 'on_average',
    marginOf: 'average',
    rain: true,
  })

  it('(3) POSTs the request to /api/plant/run and reads the contract example answer', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      calls.push({ url: String(input), init: init ?? {} })
      return Promise.resolve(jsonResponse(200, rawAnswer))
    })
    const answered = await runPlant(BASE, request)
    expect(calls).toHaveLength(1)
    expect(calls[0].url.endsWith('/api/plant/run')).toBe(true)
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual(request)
    expect(answered.answer.chosen).toBe(rawAnswer.chosen)
    expect(answered.answer.example_data).toBe(rawAnswer.example_data)
    expect(answered.answer.sources.map((s) => s.id)).toEqual(rawAnswer.sources.map((s) => s.id))
    expect(answered.rainStress).toEqual({
      kind: 'applied',
      factor: rawAnswer.rain_stress.factor,
      unit: rawAnswer.rain_stress.declared.unit,
      detail: rawAnswer.rain_stress.detail,
      label: rawAnswer.rain_stress.label,
      applied: rawAnswer.rain_stress.applied,
    })
  })

  it('(4) a 422 with the error shape rejects with its code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(422, { error: { code: 'ROTATION_INVALID', message: 'm', details: [] } }),
      ),
    )
    const error = await caughtError(runPlant(BASE, request))
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('ROTATION_INVALID')
  })

  it('(5) a failed connection rejects with UNEXPECTED', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )
    const error = await caughtError(runPlant(BASE, request))
    expect((error as ApiError).code).toBe('UNEXPECTED')
  })

  it('(6) a 200 body that is not a plant answer rejects with UNEXPECTED, never an answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, { contract: 'something_else' })))
    const error = await caughtError(runPlant(BASE, request))
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('UNEXPECTED')
  })

  it('(6) an answer to other questions than those asked rejects with UNEXPECTED', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, rawAnswer)))
    const other = plantRequestFor(rawRequest, {
      strictness: 'every_kind',
      marginOf: 'average',
      rain: true,
    })
    expect(((await caughtError(runPlant(BASE, other))) as ApiError).code).toBe('UNEXPECTED')
    const noRain = plantRequestFor(rawRequest, {
      strictness: 'on_average',
      marginOf: 'average',
      rain: false,
    })
    expect(((await caughtError(runPlant(BASE, noRain))) as ApiError).code).toBe('UNEXPECTED')
  })
})

describe('the query: one call per distinct request, cached by request, no retry (7)', () => {
  it('changing strictness makes a new call whose body carries the new strictness', async () => {
    const bodies: { questions: { strictness: string; margin_of: string } }[] = []
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body))
      bodies.push(body)
      return jsonResponse(200, answerFor(body))
    }))
    const client = new QueryClient()
    const first = plantRequestFor(rawRequest, { strictness: 'on_average', marginOf: 'average', rain: true })
    const second = plantRequestFor(rawRequest, { strictness: 'every_kind', marginOf: 'average', rain: true })

    await client.fetchQuery(plantQueryOptions(BASE, first))
    await client.fetchQuery(plantQueryOptions(BASE, first))
    expect(bodies).toHaveLength(1)
    const answered = await client.fetchQuery(plantQueryOptions(BASE, second))
    expect(bodies).toHaveLength(2)
    expect(bodies[1].questions.strictness).toBe('every_kind')
    expect(answered.answer.strictness).toBe('every_kind')
  })

  it('does not retry a failed call and does not refetch on focus', async () => {
    const fetch = vi.fn(async () => jsonResponse(500, { error: { code: 'INTERNAL_ERROR', message: 'm', details: [] } }))
    vi.stubGlobal('fetch', fetch)
    const options = plantQueryOptions(BASE, plantRequestFor(rawRequest, { strictness: 'on_average', marginOf: 'average', rain: false }))
    expect(options.retry).toBe(false)
    expect(options.refetchOnWindowFocus).toBe(false)
    const client = new QueryClient()
    const error = await caughtError(client.fetchQuery(options))
    expect((error as ApiError).code).toBe('INTERNAL_ERROR')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
