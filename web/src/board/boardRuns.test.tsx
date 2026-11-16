import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import rawExample from '../data/PLACEHOLDER_plant_answer.json'
import rawRequest from '../data/PLACEHOLDER_plant_request.json'
import rawResult from '../data/PLACEHOLDER_results_per_rotation.json'
import rawResultNotBuilt from '../data/PLACEHOLDER_results_per_rotation_not_built.json'
import { missingPatternText } from '../components/ValueDisplay'
import { parsePlantAnswer } from '../plant/plantData'
import type { ServicePhase } from '../plant/PlantScreen'
import { parseResultsPerRotation } from '../results/resultsData'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import { BoardView, initialBoardState } from './BoardScreen'
import { boardRunOf, boardRunQueryOptions, boardRunRequests, boardRunUrl, readRunEnvelope } from './boardRuns'
import type { BoardRun } from './boardRuns'

/**
 * Water and carbon on the board (PROPOSED, l3/original-mock): each compared
 * rotation run through the rotation route, its result shown in two rows of
 * the comparison. The view is rendered from given run phases; every
 * expected text is the wording of strings.ts or a value of the fixtures.
 */

vi.mock('../map/FieldsMap', () => ({
  default: () => null,
}))

const FIELD = rawRequest.site.field_id
const BASE = 'http://service.invalid'
const answer = parsePlantAnswer(rawExample)
const ids = answer.options.map((option) => option.rotation_id)

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

function count(html: string, needle: string): number {
  return html.split(needle).length - 1
}

function view(runs: ReadonlyMap<string, BoardRun> | null): string {
  const service: ServicePhase = { phase: 'answered', answer: { answer, rainStress: null } }
  return renderToString(
    <BoardView selectedFieldId={FIELD} state={initialBoardState()} apiBase={BASE} service={service} runs={runs} />,
  )
}

function allRuns(run: BoardRun): Map<string, BoardRun> {
  return new Map(ids.map((id) => [id, run]))
}

const result = parseResultsPerRotation(rawResult)

/** The example result with its water per agricultural year: two years, one value, one missing. */
const perYear = parseResultsPerRotation({
  ...rawResult,
  water_deficit_exposure: [
    {
      time_basis: 'ag_year',
      ag_year: 2001,
      indicator: 'water_deficit_exposure',
      direction: 'higher_is_better',
      value: 0.4,
      unit: 'dimensionless',
      range_missing: { reason: 'NOT_AVAILABLE' },
      provenance: 'DERIVED',
      source: 'PLACEHOLDER source of the test',
    },
    {
      time_basis: 'ag_year',
      ag_year: 2002,
      indicator: 'water_deficit_exposure',
      direction: 'higher_is_better',
      value: null,
      unit: 'dimensionless',
      missing: { reason: 'NO_COVERAGE' },
    },
  ],
})

describe('the runs the board asks for', () => {
  it('runs every rotation of the plant request once, with the request site', () => {
    const requests = boardRunRequests(rawRequest as unknown as Record<string, unknown>)
    expect(requests.map((run) => run.rotation_id)).toEqual(rawRequest.rotations.map((r) => r.rotation_id))
    for (const run of requests) {
      expect(run.body.site).toEqual(rawRequest.site)
    }
    expect(boardRunRequests(null)).toEqual([])
  })

  it('posts to the rotation route of the configured base, no retry, never stale, only when enabled', () => {
    expect(boardRunUrl('http://x.invalid/')).toBe('http://x.invalid/api/rotations/run')
    const [first] = boardRunRequests(rawRequest as unknown as Record<string, unknown>)
    const options = boardRunQueryOptions(BASE, first, true)
    expect(options.retry).toBe(false)
    expect(options.staleTime).toBe(Infinity)
    expect(options.enabled).toBe(true)
    expect(boardRunQueryOptions(BASE, first, false).enabled).toBe(false)
    expect(boardRunQueryOptions(null, first, true).enabled).toBe(false)
  })

  it('reads the envelope: a result, the reason it has none, or unreadable', () => {
    const missing = { reason: 'MISSING_INPUT', detail: 'climate' }
    expect(readRunEnvelope({ outcome: 'no_result', sources: [], result: null, result_missing: missing })).toEqual({
      phase: 'no_result',
      missing,
    })
    const read = readRunEnvelope({ outcome: 'complete', sources: [], result: rawResult, result_missing: null })
    expect(read.phase).toBe('result')
    expect(readRunEnvelope({ outcome: 'complete' })).toEqual({ phase: 'unreadable' })
  })

  it('reads a result as the route serializes it, with unset fields as explicit nulls', () => {
    const withNulls = JSON.parse(JSON.stringify(rawResult)) as Record<string, unknown>
    for (const item of withNulls.soil_carbon_trend as Record<string, unknown>[]) {
      for (const key of ['range', 'range_missing', 'missing', 'provenance', 'source']) {
        if (!(key in item)) item[key] = null
      }
    }
    for (const item of withNulls.water_deficit_exposure as Record<string, unknown>[]) {
      item.ag_year = null
    }
    const read = readRunEnvelope({ outcome: 'partial', sources: [], result: withNulls, result_missing: null })
    expect(read.phase).toBe('result')
  })

  it('a query on its way is pending; a failed one carries the route error code', () => {
    expect(boardRunOf({ isError: false, error: null, data: undefined })).toEqual({ phase: 'pending' })
    expect(boardRunOf({ isError: true, error: new ApiError('INTERNAL_ERROR'), data: undefined })).toEqual({
      phase: 'failed',
      code: 'INTERNAL_ERROR',
    })
    expect(boardRunOf({ isError: true, error: new Error('x'), data: undefined })).toEqual({
      phase: 'failed',
      code: 'UNEXPECTED',
    })
  })
})

describe('water and carbon rows of the comparison', () => {
  it('shows no such rows when no runs are given', () => {
    const html = view(null)
    expect(html).not.toContain(strings['indicator.water_deficit_exposure'])
    expect(html).not.toContain(strings['indicator.soil_carbon_trend'])
  })

  it('a run on its way: one pending line per option and row', () => {
    const html = view(allRuns({ phase: 'pending' }))
    expect(html).toContain(strings['indicator.water_deficit_exposure'])
    expect(html).toContain(strings['indicator.soil_carbon_trend'])
    expect(count(html, 'data-testid="board-run-pending"')).toBe(ids.length * 2)
    expect(html).toContain(strings['board.run.pending'])
  })

  it('a failed run: the route error text', () => {
    const html = view(allRuns({ phase: 'failed', code: 'INTERNAL_ERROR' }))
    expect(count(html, 'data-testid="board-run-failed"')).toBe(ids.length * 2)
    expect(visibleText(html)).toContain(strings['api.INTERNAL_ERROR'])
  })

  it('a run with no result: the missing pattern with its reason, never zero', () => {
    const missing = { reason: 'MISSING_INPUT' as const, detail: 'input not available: climate' }
    const text = visibleText(view(allRuns({ phase: 'no_result', missing })))
    expect(text).toContain(missingPatternText(strings['indicator.water_deficit_exposure'], missing))
    expect(text).toContain(missingPatternText(strings['indicator.soil_carbon_trend'], missing))
  })

  it('a result: water per year listed by year, carbon one line per model, each value as itself', () => {
    const html = view(allRuns({ phase: 'result', result: perYear }))
    const text = visibleText(html)
    // Water by agricultural year: the value of 2001, and 2002 missing with its reason.
    expect(count(html, 'data-testid="board-water-year"')).toBe(ids.length)
    expect(text).toContain('2001 0.4 dimensionless Derived')
    expect(text).toContain(`${strings['indicator.water_deficit_exposure']} 2002: ${strings['missing.NO_COVERAGE']}`)
    // Carbon: one group per model, one item per value, never averaged.
    const models = new Set(result.soil_carbon_trend.form === 'present' ? result.soil_carbon_trend.values.map((v) => v.carbon_model) : [])
    const items = result.soil_carbon_trend.form === 'present' ? result.soil_carbon_trend.values.length : 0
    expect(count(html, 'data-testid="board-carbon-model"')).toBe(ids.length * models.size)
    expect(count(html, 'data-testid="board-carbon-item"')).toBe(ids.length * items)
    expect(text).toContain('Model: AMG')
    expect(text).toContain('Model: RothC')
    expect(text).toContain('Computation: fitted_slope')
    expect(text).toContain('0.5 t C ha-1 yr-1 Simulated')
    expect(text).toContain('0.25 t C ha-1 yr-1 Simulated')
    expect(text).not.toContain('0.375')
  })

  it('a result on the rotation basis and parts not built: each absence with its reason', () => {
    const notBuilt = parseResultsPerRotation(rawResultNotBuilt)
    const runs = new Map<string, BoardRun>([
      [ids[0], { phase: 'result', result }],
      [ids[1], { phase: 'result', result: notBuilt }],
      [ids[2], { phase: 'unreadable' }],
    ])
    const html = view(runs)
    const text = visibleText(html)
    expect(count(html, 'data-testid="board-water-year"')).toBe(0)
    expect(text).toContain(`${strings['indicator.water_deficit_exposure']}: ${strings['missing.NOT_AVAILABLE']}`)
    expect(text).toContain(`${strings['indicator.soil_carbon_trend']}: ${strings['missing.NOT_AVAILABLE']}`)
    expect(count(html, 'data-testid="board-run-unreadable"')).toBe(2)
  })

  it('an option the request holds no rotation for has no run: no value', () => {
    const html = view(new Map())
    expect(count(html, 'data-testid="board-run-pending"')).toBe(0)
    expect(visibleText(html)).toContain(strings['plant.table.no_value'])
  })
})
