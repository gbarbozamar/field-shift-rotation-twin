import { getPlan, planBaseRequest, planFieldId } from '../board/planStore'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import rawAnswer from '../data/PLACEHOLDER_plant_answer.json'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import PlantScreen, {
  PlantNoServiceView,
  PlantScreenView,
  PlantView,
  initialPlantState,
  plantScreenReducer,
  priceKeyOf,
  serviceRequestOf,
  servicePhaseOf,
} from './PlantScreen'
import type { PlantScreenState, ServicePhase } from './PlantScreen'
import { plantExamples } from './plantData'
import {
  PlantNotAvailableError,
  plantQueryOptions,
  plantRequestFor,
  readBaseRequest,
  readPlantServiceAnswer,
  runPlant,
} from './plantRoute'

/**
 * Acceptance test of "Ask the service" on the screen "What should I plant?"
 * (S-021). PROPOSED, designed before the code. The screen is rendered with
 * the pure server renderer (no DOM environment, no new dependency): the
 * container's whole behaviour is its reducer, the request it derives and the
 * pure view of each state. fetch is stubbed in every case: never a real
 * network call. Every expected value is read from the example files, every
 * expected text from strings.ts.
 *
 * (1) no backend configured: the example answers, the banner, no fetch, no
 *     "Ask the service", heavier rain disabled with its reason;
 * (3) a 200 with the contract example answer: rendered, its sources named,
 *     the origin line names the service;
 * (4) a 422 ROTATION_INVALID: the error panel with that code's text, no
 *     option row, "Back to the saved example" restores the example;
 * (5) a failed connection: UNEXPECTED's text;
 * (6) a 200 body that is not a plant answer: UNEXPECTED, never the body;
 * (7) changing strictness in service mode gives a request with it (the call
 *     itself is in plantRoute.test.ts).
 * (2) and the fetcher side are in plantRoute.test.ts.
 */

const BASE = 'http://service.invalid'

function decode(html: string): string {
  return html
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function visibleText(html: string): string {
  return decode(html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    .trim()
}

function count(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

function section(html: string, testid: string): string {
  const parts = html.split(`data-testid="${testid}"`)
  expect(parts.length, `testid ${testid}`).toBeGreaterThan(1)
  return parts[1]
}

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

function view(state: PlantScreenState, service: ServicePhase | null, apiBase: string | null = BASE) {
  return renderToString(<PlantScreenView state={state} apiBase={apiBase} service={service} />)
}

/** The service mode with heavier rain on, the questions of the contract example. */
function serviceState(): PlantScreenState {
  const asked = plantScreenReducer(initialPlantState(), { type: 'ask' })
  return plantScreenReducer(asked, { type: 'rain', on: true })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

/** The base request the report sends: the board's plan for the example request's field. */
function planRequest() {
  return planBaseRequest(getPlan(), planFieldId(null))!
}

describe('no backend configured (1)', () => {
  const fetch = vi.fn()

  it('says the service is not available, makes no call, and shows nothing of the example answers (D251)', () => {
    vi.stubGlobal('fetch', fetch)
    const html = renderToString(<PlantScreen apiBase={null} />)
    expect(fetch).not.toHaveBeenCalled()
    expect(html).toBe(renderToString(<PlantNoServiceView />))
    expect(visibleText(section(html, 'plant-service-not-available'))).toContain(
      strings['plant.service.not_available'],
    )
    for (const testid of [
      'plant-example-banner',
      'plant-origin',
      'plant-card',
      'plant-option',
      'plant-options',
      'plant-service-ask',
      'plant-q-price',
      'plant-q-rain',
    ]) {
      expect(count(html, testid), testid).toBe(0)
    }
  })

  it('with no service, no soil-loss figure, no margin and no rotation name of the examples is rendered', () => {
    const html = renderToString(<PlantScreen apiBase={null} />)
    const text = visibleText(html)
    expect(count(html, 'plant-value')).toBe(0)
    expect(count(html, 'plant-soil-loss-label')).toBe(0)
    expect(count(html, 'plant-bar-soil')).toBe(0)
    expect(count(html, 'plant-bar-margin')).toBe(0)
    for (const answer of plantExamples.answers) {
      for (const option of answer.options) {
        expect(text).not.toContain(option.rotation_id)
        for (const item of [...Object.values(option.margin), ...Object.values(option.soil_loss)]) {
          if (item.value !== null) {
            expect(text).not.toContain(`${displayNumber(item.value)} ${item.unit}`)
          }
        }
      }
    }
    for (const rotation of rawRequest.rotations as { label?: string }[]) {
      if (rotation.label !== undefined) expect(text).not.toContain(rotation.label)
    }
  })

  it('the example answers, injected into the card components, never say "Plant this rotation" (D245) and label every soil-loss figure (D148)', () => {
    const html = renderToString(
      <PlantView set={plantExamples} strictness="on_average" marginOf="average" price={rawAnswer.tipping_price.today} />,
    )
    const text = visibleText(html)
    expect(text).not.toContain('Plant this rotation')
    expect(text).toContain(strings['plant.answer.chosen'])
    expect(strings['plant.answer.chosen'].toLowerCase()).toContain(
      'the most margin within the limit you declared; water and soil carbon are not part of this answer',
    )
    const figures = (html.match(/data-testid="plant-value"[^>]*>[^<]*Soil loss/g) ?? []).length
    expect(figures).toBeGreaterThan(0)
    expect(count(html, 'plant-soil-loss-label')).toBe(figures)
  })

  it('the card components keep the heavier-rain control disabled with its reason by default', () => {
    const rain = section(
      renderToString(
        <PlantView set={plantExamples} strictness="on_average" marginOf="average" price={rawAnswer.tipping_price.today} />,
      ),
      'plant-q-rain',
    )
    expect(rain).toMatch(/disabled=""/)
    expect(visibleText(rain)).toContain(
      missingPatternText(strings['plant.q.rain_control'], {
        reason: 'NOT_AVAILABLE',
        detail: strings['plant.q.rain_unavailable_detail'],
      }),
    )
  })

  it('with a backend configured the screen opens on the questions and "Ask the service", no example answer, and calls nothing yet (D251)', () => {
    vi.stubGlobal('fetch', fetch)
    const html = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <PlantScreen apiBase={BASE} />
      </QueryClientProvider>,
    )
    expect(fetch).not.toHaveBeenCalled()
    expect(count(html, 'plant-example-banner')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
    expect(count(html, 'plant-option')).toBe(0)
    expect(visibleText(section(html, 'plant-origin'))).not.toContain('example answers')
    expect(visibleText(section(html, 'plant-service-ask'))).toContain(strings['plant.service.ask'])
    expect(visibleText(section(html, 'plant-service-not-asked'))).toContain(strings['plant.service.not_asked'])
    expect(visibleText(section(html, 'plant-example-inputs'))).toContain(strings['plant.q.example_inputs'])
    expect(count(html, 'plant-q-kind')).toBe(1)
    expect(count(html, 'plant-q-strict')).toBe(1)
    expect(count(html, 'plant-service-not-available')).toBe(0)
  })

  it('with a backend configured, before any answer, no soil-loss figure, margin or rotation name of the examples is rendered (D251)', () => {
    const html = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <PlantScreen apiBase={BASE} />
      </QueryClientProvider>,
    )
    const text = visibleText(html)
    expect(count(html, 'plant-value')).toBe(0)
    expect(count(html, 'plant-soil-loss-label')).toBe(0)
    expect(count(html, 'plant-bar-soil')).toBe(0)
    expect(count(html, 'plant-bar-margin')).toBe(0)
    expect(text).not.toContain(strings['plant.answer.chosen'])
    for (const answer of plantExamples.answers) {
      for (const option of answer.options) {
        expect(text).not.toContain(option.rotation_id)
        for (const item of [...Object.values(option.margin), ...Object.values(option.soil_loss)]) {
          if (item.value !== null) {
            expect(text).not.toContain(`${displayNumber(item.value)} ${item.unit}`)
          }
        }
      }
    }
    for (const rotation of rawRequest.rotations as { label?: string }[]) {
      if (rotation.label !== undefined) expect(text).not.toContain(rotation.label)
    }
  })

  it('after a mocked service answer, the answer is shown, with its origin and no example inputs line', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, rawAnswer)))
    const state = serviceState()
    const answered = await runPlant(BASE, serviceRequestOf(state)!)
    const phase: ServicePhase = { phase: 'answered', answer: answered }
    const html = view(state, phase)
    expect(count(html, 'plant-card')).toBe(1)
    expect(count(html, 'plant-option')).toBe(rawAnswer.options.length)
    expect(visibleText(section(html, 'plant-chosen'))).toContain(rawAnswer.chosen as string)
    expect(visibleText(section(html, 'plant-origin'))).toContain(
      formatString(strings['plant.service.origin_service'], { api: BASE }),
    )
    expect(count(html, 'plant-service-not-asked')).toBe(0)
    expect(count(html, 'plant-example-inputs')).toBe(0)
  })
})

describe('the service answers 200 with the contract example answer (3)', () => {
  it('renders the answer, names its sources and says it came from the service', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, rawAnswer)))
    const state = serviceState()
    const request = serviceRequestOf(state)!
    expect(request).toEqual(
      plantRequestFor(rawRequest, { strictness: state.strictness, marginOf: state.marginOf, rain: true }),
    )
    const answered = await runPlant(BASE, request)
    const html = view(state, { phase: 'answered', answer: answered })
    const text = visibleText(html)

    expect(visibleText(section(html, 'plant-chosen'))).toContain(rawAnswer.chosen)
    expect(count(html, 'plant-option')).toBe(rawAnswer.options.length)
    expect(count(html, 'plant-source')).toBe(rawAnswer.sources.length)
    for (const source of rawAnswer.sources) {
      expect(text).toContain(source.id)
    }
    expect(visibleText(section(html, 'plant-origin'))).toContain(
      formatString(strings['plant.service.origin_service'], { api: BASE }),
    )
    // The answer says example_data: the banner shows.
    expect(rawAnswer.example_data).toBe(true)
    expect(count(html, 'plant-example-banner')).toBe(1)
    expect(count(html, 'plant-service-back')).toBe(1)
  })

  it('shows the declared factor sent, with its unit and mark, and the stress echo of the answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, rawAnswer)))
    const state = serviceState()
    const answered = await runPlant(BASE, serviceRequestOf(state)!)
    const html = view(state, { phase: 'answered', answer: answered })
    const rain = section(html, 'plant-q-rain')
    expect(rain).not.toMatch(/disabled=""/)
    const factor = rawRequest.questions.rain_stress_factor
    expect(visibleText(section(html, 'plant-rain-factor'))).toContain(
      formatString(strings['plant.service.rain_factor'], {
        value: displayNumber(factor.value),
        unit: factor.unit,
        provenance: strings['provenance.DECLARED'],
      }),
    )
    expect(visibleText(rain)).toContain(strings['plant.declared'])
    expect(visibleText(section(html, 'plant-rain-stress'))).toContain(rawAnswer.rain_stress.detail)
  })
})

describe('the service fails', () => {
  it('(4) a 422 ROTATION_INVALID: the panel names the code, no option row; back restores the example', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(422, { error: { code: 'ROTATION_INVALID', message: 'm', details: [] } }),
      ),
    )
    const state = serviceState()
    const error = await caughtError(runPlant(BASE, serviceRequestOf(state)!))
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    expect(phase).toEqual({ phase: 'failed', code: 'ROTATION_INVALID' })
    const html = view(state, phase)
    expect(visibleText(section(html, 'plant-service-error'))).toContain(
      strings['plant.service.error.ROTATION_INVALID'],
    )
    expect(visibleText(section(html, 'plant-service-error-code'))).toContain('ROTATION_INVALID')
    expect(count(html, 'plant-option')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
    expect(visibleText(section(html, 'plant-service-back'))).toContain(strings['plant.service.back'])

    const back = plantScreenReducer(state, { type: 'back' })
    expect(back.mode).toBe('example')
    expect(serviceRequestOf(back)).toBeNull()
    // Back to the questions: no fallback to the example answers (D251).
    const restored = view(back, null)
    expect(count(restored, 'plant-option')).toBe(0)
    expect(count(restored, 'plant-card')).toBe(0)
    expect(count(restored, 'plant-service-error')).toBe(0)
    expect(count(restored, 'plant-service-not-asked')).toBe(1)
  })

  it('(5) a failed connection: the panel shows the text of UNEXPECTED', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )
    const error = await caughtError(runPlant(BASE, serviceRequestOf(serviceState())!))
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    const html = view(serviceState(), phase)
    expect(visibleText(section(html, 'plant-service-error'))).toContain(
      strings['plant.service.error.UNEXPECTED'],
    )
    expect(count(html, 'plant-option')).toBe(0)
  })

  it('(6) a 200 body that is not a plant answer: UNEXPECTED, never the body', async () => {
    const body = { contract: 'plant_answer', example_data: true, marker: 'NOT_AN_ANSWER_MARKER' }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, body)))
    const error = await caughtError(runPlant(BASE, serviceRequestOf(serviceState())!))
    expect(error).toBeInstanceOf(ApiError)
    const html = view(serviceState(), servicePhaseOf({ isPending: false, isError: true, error, data: undefined }))
    expect(visibleText(section(html, 'plant-service-error'))).toContain(
      strings['plant.service.error.UNEXPECTED'],
    )
    expect(html).not.toContain('NOT_AN_ANSWER_MARKER')
    expect(count(html, 'plant-card')).toBe(0)
  })

  it('a 200 with no answer and its reason: the reason is shown, not an error panel', async () => {
    const missing = { reason: 'NOT_AVAILABLE', detail: 'NOT_BUILT_DETAIL_MARKER' } as const
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, { answer: null, answer_missing: missing })))
    const state = serviceState()
    const error = await caughtError(runPlant(BASE, serviceRequestOf(state)!))
    expect(error).toBeInstanceOf(PlantNotAvailableError)
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    expect(phase).toEqual({ phase: 'not_available', missing })
    const html = view(state, phase)
    expect(visibleText(section(html, 'plant-answer-not-available'))).toContain(
      missingPatternText(strings['plant.answer.missing_what'], missing),
    )
    expect(count(html, 'plant-service-error')).toBe(0)
    expect(count(html, 'plant-service-error-code')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
    expect(count(html, 'plant-option')).toBe(0)
    expect(visibleText(section(html, 'plant-service-back'))).toContain(strings['plant.service.back'])
  })

  it('a 200 with no answer and no detail: the reason alone is shown', async () => {
    const missing = { reason: 'NOT_AVAILABLE' } as const
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, { answer: null, answer_missing: missing })))
    const error = await caughtError(runPlant(BASE, serviceRequestOf(serviceState())!))
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    expect(phase).toEqual({ phase: 'not_available', missing })
  })

  it.each([
    ['no reason at all', { answer: null }],
    ['a reason that is not a code of the conventions', { answer: null, answer_missing: { reason: 'NOT_A_CODE' } }],
    ['an empty detail', { answer: null, answer_missing: { reason: 'NOT_AVAILABLE', detail: '' } }],
  ])('a 200 with no answer and %s: UNEXPECTED, no reason is invented', async (_name, body) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, body)))
    const error = await caughtError(runPlant(BASE, serviceRequestOf(serviceState())!))
    expect(error).toBeInstanceOf(ApiError)
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    expect(phase).toEqual({ phase: 'failed', code: 'UNEXPECTED' })
    const html = view(serviceState(), phase)
    expect(count(html, 'plant-answer-not-available')).toBe(0)
    expect(count(html, 'plant-service-error')).toBe(1)
  })

  it('an error that is not an ApiError is UNEXPECTED too', () => {
    expect(
      servicePhaseOf({ isPending: false, isError: true, error: new Error('x'), data: undefined }),
    ).toEqual({ phase: 'failed', code: 'UNEXPECTED' })
  })

  it('while the call is on its way: a pending line, no example answer', () => {
    const phase = servicePhaseOf({ isPending: true, isError: false, error: null, data: undefined })
    expect(phase).toEqual({ phase: 'pending' })
    const html = view(serviceState(), phase)
    expect(visibleText(section(html, 'plant-service-pending'))).toContain(strings['plant.service.pending'])
    expect(count(html, 'plant-option')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
  })
})

describe('the questions change the request in service mode (7)', () => {
  it('changing strictness gives a request with the new strictness; example mode sends none', () => {
    expect(serviceRequestOf(initialPlantState())).toBeNull()
    const state = serviceState()
    const changed = plantScreenReducer(state, { type: 'strictness', value: 'every_kind' })
    const request = serviceRequestOf(changed) as { questions: { strictness: string } }
    expect(request.questions.strictness).toBe('every_kind')
    expect(serviceRequestOf(state)).not.toEqual(request)
  })

  it('heavier rain off sends no factor', () => {
    const off = plantScreenReducer(serviceState(), { type: 'rain', on: false })
    const request = serviceRequestOf(off) as { questions: { rain_stress_factor: unknown } }
    expect(request.questions.rain_stress_factor).toBeNull()
  })
})

/**
 * Fix round 1 of S-021 (PROPOSED). Expected values from the example files,
 * expected texts from strings.ts; the only literals are a reason code of the
 * contract list and a marker text that stands for a declared detail.
 */

function withFactorMissing(reason: string, detail: string): unknown {
  const request = structuredClone(rawRequest) as { questions: { rain_stress_factor: unknown } }
  request.questions.rain_stress_factor = {
    value: null,
    unit: rawRequest.questions.rain_stress_factor.unit,
    missing: { reason, detail },
  }
  return request
}

describe('fix 1: a factor the request declares missing shows its declared reason', () => {
  const read = readBaseRequest(withFactorMissing('NOT_APPLICABLE', 'DECLARED_DETAIL_MARKER'))
  const declared = missingPatternText(strings['plant.q.rain_control'], {
    reason: 'NOT_APPLICABLE',
    detail: 'DECLARED_DETAIL_MARKER',
  })

  it('in example and in service mode, the control is disabled with the declared reason, never NOT_DECLARED', () => {
    for (const state of [initialPlantState(), serviceState()]) {
      const service: ServicePhase | null = state.mode === 'service' ? { phase: 'pending' } : null
      const html = renderToString(<PlantScreenView state={state} apiBase={BASE} service={service} read={read} />)
      const rain = section(html, 'plant-q-rain')
      expect(rain).toMatch(/disabled=""/)
      expect(visibleText(rain)).toContain(declared)
      expect(visibleText(rain)).not.toContain(strings['plant.service.rain_no_factor_detail'])
    }
  })

  it('a declared-missing factor is not sent: heavier rain on still sends null', () => {
    const request = serviceRequestOf(serviceState(), withFactorMissing('NOT_APPLICABLE', 'DECLARED_DETAIL_MARKER')) as {
      questions: { rain_stress_factor: unknown }
    }
    expect(request.questions.rain_stress_factor).toBeNull()
  })

  it('NOT_DECLARED stays for a request with no factor object at all', () => {
    const none = structuredClone(rawRequest) as { questions: { rain_stress_factor: unknown } }
    none.questions.rain_stress_factor = null
    const html = renderToString(
      <PlantScreenView state={initialPlantState()} apiBase={BASE} service={null} read={readBaseRequest(none)} />,
    )
    expect(visibleText(section(html, 'plant-q-rain'))).toContain(
      missingPatternText(strings['plant.q.rain_control'], {
        reason: 'NOT_DECLARED',
        detail: strings['plant.service.rain_no_factor_detail'],
      }),
    )
  })
})

describe('fix 4: the request is built once, and the price key is cheap', () => {
  it('the view copies no request, and the screen copies it once per render', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, rawAnswer)))
    const state = serviceState()
    const answered = await runPlant(BASE, serviceRequestOf(state, planRequest())!)
    const clones = vi.spyOn(globalThis, 'structuredClone')
    try {
      view(state, { phase: 'answered', answer: answered })
      expect(clones).not.toHaveBeenCalled()
      serviceRequestOf(state, planRequest())
      const perRequest = clones.mock.calls.length
      expect(perRequest).toBeGreaterThan(0)
      clones.mockClear()
      renderToString(
        <QueryClientProvider client={new QueryClient()}>
          <PlantScreen apiBase={BASE} initialState={state} />
        </QueryClientProvider>,
      )
      expect(clones).toHaveBeenCalledTimes(perRequest)
    } finally {
      clones.mockRestore()
    }
  })

  it('one price key per distinct request; the price looked at does not change it', () => {
    const state = serviceState()
    expect(priceKeyOf(state)).toBe(priceKeyOf(plantScreenReducer(state, { type: 'price', price: 0, key: null })))
    expect(priceKeyOf(state)).not.toBe(priceKeyOf(plantScreenReducer(state, { type: 'strictness', value: 'every_kind' })))
    expect(priceKeyOf(state)).not.toBe(priceKeyOf(plantScreenReducer(state, { type: 'margin_of', value: 'la_nina' })))
    expect(priceKeyOf(state)).not.toBe(priceKeyOf(plantScreenReducer(state, { type: 'rain', on: false })))
  })
})

describe('fix 6: with a backend, heavier rain is enabled in example mode too', () => {
  it('the checkbox is enabled, a line says it applies to the next service answer, never "this page does not call"', () => {
    const html = renderToString(<PlantScreenView state={initialPlantState()} apiBase={BASE} service={null} />)
    const rain = section(html, 'plant-q-rain')
    expect(rain).not.toMatch(/disabled=""/)
    expect(visibleText(section(html, 'plant-rain-next-answer'))).toContain(strings['plant.service.rain_next_answer'])
    expect(visibleText(rain)).not.toContain(strings['plant.q.rain_unavailable_detail'])
    // No example answer is shown before the service answers (D251).
    expect(count(html, 'plant-card')).toBe(0)
  })

  it('the checkbox shows what will be sent: off, then on with the factor, and the request asked carries it', () => {
    const off = initialPlantState()
    const rainOf = (html: string) => section(html, 'plant-q-rain').split('</fieldset>')[0]
    const offRain = rainOf(renderToString(<PlantScreenView state={off} apiBase={BASE} service={null} />))
    expect(offRain).toContain('type="checkbox"')
    expect(offRain).not.toMatch(/checked=""/)
    const on = plantScreenReducer(off, { type: 'rain', on: true })
    const onHtml = renderToString(<PlantScreenView state={on} apiBase={BASE} service={null} />)
    expect(rainOf(onHtml)).toMatch(/checked=""/)
    expect(count(onHtml, 'plant-rain-factor')).toBe(1)
    const asked = serviceRequestOf(plantScreenReducer(on, { type: 'ask' })) as typeof rawRequest
    expect(asked.questions.rain_stress_factor).toEqual(rawRequest.questions.rain_stress_factor)
  })

  it('in service mode there is no next-answer line', () => {
    const html = view(serviceState(), { phase: 'pending' })
    expect(count(html, 'plant-rain-next-answer')).toBe(0)
  })

  it('without a backend: no rain control and no next-answer line, only the not-available view (D251)', () => {
    const html = renderToString(<PlantScreen apiBase={null} />)
    expect(count(html, 'plant-q-rain')).toBe(0)
    expect(count(html, 'plant-rain-next-answer')).toBe(0)
  })
})

describe('fix 7: a request that cannot be read is a typed absence on the rain control', () => {
  const unreadable = { contract: 'plant_request', questions: 'not-an-object' }
  const read = readBaseRequest(unreadable)
  const absence = missingPatternText(strings['plant.q.rain_control'], {
    reason: 'MISSING_INPUT',
    detail: strings['plant.service.rain_request_invalid_detail'],
  })

  it('with a backend: MISSING_INPUT with its detail, no "Ask the service", and no example answer (D251)', () => {
    expect(read.readable).toBe(false)
    const html = renderToString(<PlantScreenView state={initialPlantState()} apiBase={BASE} service={null} read={read} />)
    const rain = section(html, 'plant-q-rain')
    expect(rain).toMatch(/disabled=""/)
    expect(visibleText(rain)).toContain(absence)
    expect(count(html, 'plant-service-ask')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
    expect(count(html, 'plant-option')).toBe(0)
    expect(serviceRequestOf(serviceState(), unreadable)).toBeNull()
  })

  it('without a backend: the not-available view, whatever the request (D251)', () => {
    const html = renderToString(<PlantScreenView state={initialPlantState()} apiBase={null} service={null} read={read} />)
    expect(html).toBe(renderToString(<PlantNoServiceView />))
  })
})

describe('fix 8: the real screen in service mode reads the answer from its query', () => {
  it('with the cache pre-filled for the service request, the answer and the origin line are rendered, no call made', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const state = serviceState()
    const request = serviceRequestOf(state, planRequest())!
    const client = new QueryClient()
    client.setQueryData(plantQueryOptions(BASE, request).queryKey, readPlantServiceAnswer(rawAnswer, request))
    const html = renderToString(
      <QueryClientProvider client={client}>
        <PlantScreen apiBase={BASE} initialState={state} />
      </QueryClientProvider>,
    )
    expect(fetch).not.toHaveBeenCalled()
    expect(count(html, 'plant-service-pending')).toBe(0)
    expect(visibleText(section(html, 'plant-chosen'))).toContain(rawAnswer.chosen)
    expect(count(html, 'plant-source')).toBe(rawAnswer.sources.length)
    expect(visibleText(section(html, 'plant-origin'))).toContain(
      formatString(strings['plant.service.origin_service'], { api: BASE }),
    )
    expect(count(html, 'plant-rain-stress')).toBe(1)
  })

  it('a cache filled for another request leaves the screen pending: the key is the request sent', () => {
    vi.stubGlobal('fetch', vi.fn())
    const state = serviceState()
    const other = serviceRequestOf(plantScreenReducer(state, { type: 'rain', on: false }))!
    const client = new QueryClient()
    client.setQueryData(
      plantQueryOptions(BASE, other).queryKey,
      readPlantServiceAnswer(rawAnswer, serviceRequestOf(state)!),
    )
    const html = renderToString(
      <QueryClientProvider client={client}>
        <PlantScreen apiBase={BASE} initialState={state} />
      </QueryClientProvider>,
    )
    expect(count(html, 'plant-service-pending')).toBe(1)
    expect(count(html, 'plant-card')).toBe(0)
  })
})
