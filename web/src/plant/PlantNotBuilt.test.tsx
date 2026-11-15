import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { renderToString } from 'react-dom/server'
import rawAnswer from '../data/PLACEHOLDER_plant_answer.json'
import { missingPatternText } from '../components/ValueDisplay'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import { PlantScreenView, initialPlantState, plantScreenReducer, serviceRequestOf, servicePhaseOf } from './PlantScreen'
import type { PlantScreenState, ServicePhase } from './PlantScreen'
import { parsePlantAnswer } from './plantData'
import { PLANT_NOT_BUILT_CONTRACT, PlantNotBuiltError, readPlantNotBuilt, runPlant } from './plantRoute'

/**
 * Acceptance test of the screen side of unit l2/plant-layer-by-name (S-031).
 * PROPOSED. While the service's plant layer is not built, POST
 * /api/plant/run answers 200 with exactly {contract: plant_answer_not_built,
 * answer_missing: {reason: NOT_AVAILABLE, detail}}. The parser recognises
 * that body and the screen shows a "not available" sentence from the
 * strings file: never a crash, never an answer, never zeros. fetch is
 * stubbed in every case. The body is the contract's own example, read from
 * contracts/plant_answer/examples_not_built/.
 */

const BASE = 'http://service.invalid'
const here = dirname(fileURLToPath(import.meta.url))
const notBuiltFile = resolve(
  here,
  '..',
  '..',
  '..',
  'contracts',
  'plant_answer',
  'examples_not_built',
  'PLACEHOLDER_plant_answer_not_built.json',
)
const NOT_BUILT = JSON.parse(readFileSync(notBuiltFile, 'utf8')) as {
  contract: string
  answer_missing: { reason: string; detail: string }
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

describe('the not-built body of the plant route (S-031)', () => {
  it('is the contract example, and the parser reads its reason and detail', () => {
    expect(NOT_BUILT.contract).toBe(PLANT_NOT_BUILT_CONTRACT)
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
    ['no answer_missing', { contract: PLANT_NOT_BUILT_CONTRACT }],
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

describe('the source state transcribed (S-031)', () => {
  it('is read from the contract example, whose record row has it', () => {
    const answer = parsePlantAnswer(rawAnswer)
    expect(answer.sources.map((s) => s.state)).toContain('transcribed')
  })

  it('a state outside the list is still refused', () => {
    const copy = JSON.parse(JSON.stringify(rawAnswer))
    copy.sources[1].state = 'stored'
    expect(() => parsePlantAnswer(copy)).toThrow('state-not-in-the-list')
  })
})
