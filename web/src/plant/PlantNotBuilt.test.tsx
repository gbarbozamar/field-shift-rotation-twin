import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawAnswer from '../data/PLACEHOLDER_plant_answer.json'
import { missingPatternText } from '../components/ValueDisplay'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import { PlantScreenView, initialPlantState, plantScreenReducer, serviceRequestOf, servicePhaseOf } from './PlantScreen'
import type { PlantScreenState, ServicePhase } from './PlantScreen'
import { parsePlantAnswer } from './plantData'
import { PlantNotBuiltError, readPlantNotBuilt, runPlant } from './plantRoute'

/**
 * Acceptance test of the screen side of the not-built plant layer (S-031,
 * adapted by R28 of S-035, PROPOSED). While the service's plant layer is not
 * built, POST /api/plant/run answers 200 with exactly {answer: null,
 * answer_missing: {reason: NOT_AVAILABLE, detail}} (the form of #427, R27:
 * main's contract has no not-built document). The reader recognises that
 * body and the screen shows a "not available" panel with the reason and the
 * service's detail from the strings file: never a crash, never an answer,
 * never zeros. fetch is stubbed in every case. The detail is the text of
 * PLANT_NOT_BUILT in api/app.py of #427, used here as test data only.
 */

const BASE = 'http://service.invalid'
const NOT_BUILT = {
  answer: null,
  answer_missing: {
    reason: 'NOT_AVAILABLE',
    detail: 'the plant layer is not built yet: api.plant.run_plant',
  },
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function caughtError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('the promise was expected to reject')
}

function visibleText(html: string): string {
  return html
    .replace(/<!-- -->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

function count(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

function serviceState(): PlantScreenState {
  return plantScreenReducer(initialPlantState(), { type: 'ask' })
}

function view(state: PlantScreenState, service: ServicePhase) {
  return renderToString(<PlantScreenView state={state} apiBase={BASE} service={service} />)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the not-built body of the plant route (S-031, R28)', () => {
  it('the reader reads its reason and detail', () => {
    expect(readPlantNotBuilt(NOT_BUILT)).toEqual({
      reason: 'NOT_AVAILABLE',
      detail: NOT_BUILT.answer_missing.detail,
    })
  })

  it('is not taken for an answer, and an answer is not taken for it', () => {
    expect(readPlantNotBuilt(rawAnswer)).toBeNull()
    expect(() => parsePlantAnswer(NOT_BUILT)).toThrow('contract-not-plant-answer')
  })

  it.each([
    ['another reason', { ...NOT_BUILT, answer_missing: { reason: 'NO_COVERAGE', detail: 'x' } }],
    ['no detail', { ...NOT_BUILT, answer_missing: { reason: 'NOT_AVAILABLE' } }],
    ['an empty detail', { ...NOT_BUILT, answer_missing: { reason: 'NOT_AVAILABLE', detail: '' } }],
    ['an extra member', { ...NOT_BUILT, example_data: true }],
    ['no answer_missing', { answer: null }],
  ])('a not-built body with %s is UNEXPECTED', (_, body) => {
    expect(() => readPlantNotBuilt(body)).toThrow(ApiError)
  })

  it('a 200 with it: the call rejects with the reason, the screen says not available, no answer, no zero', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, NOT_BUILT)))
    const state = serviceState()
    const error = await caughtError(runPlant(BASE, serviceRequestOf(state)!))
    expect(error).toBeInstanceOf(PlantNotBuiltError)
    const phase = servicePhaseOf({ isPending: false, isError: true, error, data: undefined })
    expect(phase).toEqual({
      phase: 'not_built',
      missing: { reason: 'NOT_AVAILABLE', detail: NOT_BUILT.answer_missing.detail },
    })
    const html = view(state, phase)
    const panel = visibleText(html.split('data-testid="plant-service-not-built"')[1])
    expect(panel).toContain(strings['plant.service.not_built_heading'])
    expect(panel).toContain(
      missingPatternText(strings['plant.service.not_built_what'], {
        reason: 'NOT_AVAILABLE',
        detail: NOT_BUILT.answer_missing.detail,
      }),
    )
    expect(count(html, 'plant-service-not-built')).toBe(1)
    expect(count(html, 'plant-service-error')).toBe(0)
    expect(count(html, 'plant-card')).toBe(0)
    expect(count(html, 'plant-option')).toBe(0)
    expect(count(html, 'plant-value')).toBe(0)
    expect(count(html, 'plant-service-back')).toBe(1)
  })
})
