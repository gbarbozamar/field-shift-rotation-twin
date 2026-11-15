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
  PlantScreenView,
  initialPlantState,
  plantScreenReducer,
  serviceRequestOf,
  servicePhaseOf,
} from './PlantScreen'
import type { PlantScreenState, ServicePhase } from './PlantScreen'
import { plantRequestFor, runPlant } from './plantRoute'

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

describe('no backend configured (1)', () => {
  const fetch = vi.fn()

  it('opens on the example answers with the banner, makes no call, offers no service', () => {
    vi.stubGlobal('fetch', fetch)
    const html = renderToString(<PlantScreen apiBase={null} />)
    expect(fetch).not.toHaveBeenCalled()
    expect(count(html, 'plant-example-banner')).toBe(1)
    expect(count(html, 'plant-card')).toBe(1)
    expect(count(html, 'plant-option')).toBe(rawAnswer.options.length)
    expect(count(html, 'plant-service-ask')).toBe(0)
    expect(visibleText(section(html, 'plant-origin'))).toContain(strings['plant.service.origin_example'])
  })

  it('keeps the heavier-rain control disabled with its reason', () => {
    const rain = section(renderToString(<PlantScreen apiBase={null} />), 'plant-q-rain')
    expect(rain).toMatch(/disabled=""/)
    expect(visibleText(rain)).toContain(
      missingPatternText(strings['plant.q.rain_control'], {
        reason: 'NOT_AVAILABLE',
        detail: strings['plant.q.rain_unavailable_detail'],
      }),
    )
  })

  it('with a backend configured the screen still opens on the example, offers the service, and calls nothing yet', () => {
    vi.stubGlobal('fetch', fetch)
    const html = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <PlantScreen apiBase={BASE} />
      </QueryClientProvider>,
    )
    expect(fetch).not.toHaveBeenCalled()
    expect(count(html, 'plant-example-banner')).toBe(1)
    expect(count(html, 'plant-card')).toBe(1)
    expect(visibleText(section(html, 'plant-service-ask'))).toContain(strings['plant.service.ask'])
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
    const restored = view(back, null)
    expect(count(restored, 'plant-option')).toBe(rawAnswer.options.length)
    expect(count(restored, 'plant-service-error')).toBe(0)
    expect(visibleText(section(restored, 'plant-origin'))).toContain(strings['plant.service.origin_example'])
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
