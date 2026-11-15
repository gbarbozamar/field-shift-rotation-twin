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
  plantScreenQueryOptions,
  readBaseRequest,
  readPlantServiceAnswer,
  readRainFactor,
  runPlant,
} from './plantRoute'
import { strings } from '../strings'

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

/**
 * Fix round 1 of S-021 (PROPOSED). Every expected value is read from the
 * example files; the only literals are a reason code of the contract list and
 * a marker text that stands for a detail.
 */
// A copy of example JSON, edited in place for one case.
type Json = Record<string, any>

function clone<T>(value: T): T {
  return structuredClone(value)
}

/** The example request with its factor declared missing, with this reason and detail. */
function requestWithMissingFactor(reason: string, detail: string): Json {
  const request = clone(rawRequest) as Json
  request.questions.rain_stress_factor = {
    value: null,
    unit: rawRequest.questions.rain_stress_factor.unit,
    missing: { reason, detail },
  }
  return request
}

describe('fix 1: readRainFactor tells a declared-missing factor from no factor', () => {
  it('a present factor is read as declared', () => {
    const factor = rawRequest.questions.rain_stress_factor
    expect(readRainFactor(rawRequest)).toEqual({
      kind: 'present',
      factor: { value: factor.value, unit: factor.unit, provenance: factor.provenance },
    })
  })

  it('a factor declared missing keeps its own reason and detail, never NOT_DECLARED', () => {
    const request = requestWithMissingFactor('NOT_APPLICABLE', 'DECLARED_DETAIL_MARKER')
    expect(readRainFactor(request)).toEqual({
      kind: 'declared_missing',
      missing: { reason: 'NOT_APPLICABLE', detail: 'DECLARED_DETAIL_MARKER' },
    })
    expect(declaredRainFactor(request)).toBeNull()
  })

  it('no factor object at all (null or absent) is none', () => {
    const none = clone(rawRequest) as Json
    none.questions.rain_stress_factor = null
    expect(readRainFactor(none)).toEqual({ kind: 'none' })
    delete none.questions.rain_stress_factor
    expect(readRainFactor(none)).toEqual({ kind: 'none' })
  })

  it('a request that cannot be read is MISSING_INPUT with its detail key, never an exception', () => {
    const unreadable = {
      kind: 'unreadable',
      missing: { reason: 'MISSING_INPUT', detail: strings['plant.service.rain_request_invalid_detail'] },
    }
    expect(readRainFactor({ contract: 'something_else' })).toEqual(unreadable)
    expect(readRainFactor(null)).toEqual(unreadable)
    const badReason = requestWithMissingFactor('NOT_A_REASON_CODE', 'DECLARED_DETAIL_MARKER')
    expect(readRainFactor(badReason)).toEqual(unreadable)
    expect(readBaseRequest({ contract: 'something_else' })).toEqual({ readable: false, rain: unreadable })
    expect(readBaseRequest(rawRequest).readable).toBe(true)
  })
})

describe('fix 2: the rain-stress part of the answer is the one the factor asked calls for', () => {
  const asked = { strictness: rawAnswer.questions.strictness, marginOf: rawAnswer.questions.margin_of } as {
    strictness: 'on_average'
    marginOf: 'average'
  }
  const rainOn = plantRequestFor(rawRequest, { ...asked, rain: true })
  const rainOff = plantRequestFor(rawRequest, { ...asked, rain: false })

  function expectUnexpected(body: unknown, request: unknown) {
    let caught: unknown = null
    try {
      readPlantServiceAnswer(body, request)
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).code).toBe('UNEXPECTED')
  }

  it('the contract example answer is read for its own request', () => {
    expect(readPlantServiceAnswer(rawAnswer, rainOn).rainStress?.kind).toBe('applied')
  })

  it('rain off: an answer with a rain-stress part is UNEXPECTED', () => {
    const body = clone(rawAnswer) as Json
    body.questions.rain_stress_factor = null
    expectUnexpected(body, rainOff)
    body.rain_stress = null
    expect(readPlantServiceAnswer(body, rainOff).rainStress).toBeNull()
  })

  it('rain on: an answer without a rain-stress part, or with none at all, is UNEXPECTED', () => {
    const body = clone(rawAnswer) as Json
    body.rain_stress = null
    expectUnexpected(body, rainOn)
    delete body.rain_stress
    expectUnexpected(body, rainOn)
  })

  it('rain on: an applied factor other than the one asked is UNEXPECTED', () => {
    const body = clone(rawAnswer) as Json
    const other = rawAnswer.rain_stress.factor * 2
    body.rain_stress.factor = other
    body.rain_stress.declared.value = other
    expectUnexpected(body, rainOn)
  })

  it('rain on: the missing form for a factor with a value is UNEXPECTED', () => {
    const body = clone(rawAnswer) as Json
    body.rain_stress = {
      missing: { reason: 'NOT_APPLICABLE' },
      detail: rawAnswer.rain_stress.detail,
      label: rawAnswer.rain_stress.label,
    }
    expectUnexpected(body, rainOn)
  })

  it('a factor declared missing: the missing form with the same reason is read, another reason is UNEXPECTED', () => {
    const request = requestWithMissingFactor('NOT_APPLICABLE', 'DECLARED_DETAIL_MARKER')
    const body = clone(rawAnswer) as Json
    body.questions.rain_stress_factor = clone(request.questions.rain_stress_factor)
    body.rain_stress = {
      missing: { reason: 'NOT_APPLICABLE', detail: 'DECLARED_DETAIL_MARKER' },
      detail: rawAnswer.rain_stress.detail,
      label: rawAnswer.rain_stress.label,
    }
    expect(readPlantServiceAnswer(body, request).rainStress).toEqual({
      kind: 'missing',
      missing: { reason: 'NOT_APPLICABLE', detail: 'DECLARED_DETAIL_MARKER' },
      detail: rawAnswer.rain_stress.detail,
      label: rawAnswer.rain_stress.label,
    })
    body.rain_stress.missing.reason = 'NOT_DECLARED'
    expectUnexpected(body, request)
  })
})

describe('fix 3: the answer is for the field of the request, and example data when the request is', () => {
  const request = plantRequestFor(rawRequest, {
    strictness: rawAnswer.questions.strictness as 'on_average',
    marginOf: rawAnswer.questions.margin_of as 'average',
    rain: true,
  })

  function code(body: unknown): string | null {
    try {
      readPlantServiceAnswer(body, request)
      return null
    } catch (error) {
      return (error as ApiError).code
    }
  }

  it('the example answer names the field of the example request', () => {
    expect(rawAnswer.case_id).toBe(rawRequest.site.case_id)
    expect(rawAnswer.field_id).toBe(rawRequest.site.field_id)
    expect(code(rawAnswer)).toBeNull()
  })

  it('another case_id or field_id is UNEXPECTED', () => {
    const otherCase = clone(rawAnswer) as Json
    otherCase.case_id = `${rawAnswer.case_id}-other`
    expect(code(otherCase)).toBe('UNEXPECTED')
    const otherField = clone(rawAnswer) as Json
    otherField.field_id = `${rawAnswer.field_id}-other`
    expect(code(otherField)).toBe('UNEXPECTED')
  })

  it('an answer to an example request that is not marked example data is UNEXPECTED', () => {
    expect(rawRequest.example_data).toBe(true)
    const body = clone(rawAnswer) as Json
    body.example_data = false
    expect(code(body)).toBe('UNEXPECTED')
  })
})

describe('fix 5 and 8: the query of the screen is enabled only with a backend and a request', () => {
  const request = plantRequestFor(rawRequest, { strictness: 'on_average', marginOf: 'average', rain: true })

  it('enabled with both, disabled without a backend or without a request', () => {
    expect(plantScreenQueryOptions(BASE, request).enabled).toBe(true)
    expect(plantScreenQueryOptions(null, request).enabled).toBe(false)
    expect(plantScreenQueryOptions(BASE, null).enabled).toBe(false)
    expect(plantScreenQueryOptions(BASE, request).queryKey).toEqual(plantQueryOptions(BASE, request).queryKey)
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
