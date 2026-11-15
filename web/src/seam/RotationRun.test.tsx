import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToString } from 'react-dom/server'
import rawRotation from '../data/rotation_definition.json'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId } from '../identity/selection'
import { strings } from '../strings'
import { rotationDefinition } from './rotationDefinition'
import { ApiError, runRotation, runRotationUrl } from './runRotationApi'
import type { SiteReference } from './runRotationApi'
import { parseRunRotation } from './runRotationResponse'
import RotationRun, { RotationRunPanel, siteReferenceOf } from './RotationRun'
import type { RotationRunState } from './RotationRun'

/**
 * Acceptance test of the CP1 seam (issue #119). No real network: the fetch
 * boundary is stubbed with the route's real shapes, read from api/rotations.py
 * and its own test — the success envelope (always 200, values missing with
 * their reason, never zero) and the one error shape of api/errors.py
 * ({ "error": { "code", "message", "details" } }). Every number and text of
 * the fixtures is a placeholder of the contract examples; no test asserts a
 * scientific value.
 *
 * The panel is a pure function of its state, so its whole behaviour is its
 * static markup, rendered with the pure server renderer of react-dom. The
 * states that a live browser reaches through the mutation are produced here
 * by running the real fetcher and the real parser against the stubbed fetch,
 * then handing the outcome to the panel — the same path the container takes.
 */

// --- the route's real shapes (placeholders of the contract examples) -----------

const CLIMATE_FRESH = {
  id: 'PLACEHOLDER_CLIMATE',
  contract: 'site_data_climate',
  state: 'fresh',
  retrieved_at: '1900-01-02T03:04:05Z',
  time_zone: 'UTC',
  request: { PLACEHOLDER_KEY: 'PLACEHOLDER_VALUE' },
  attribution: 'PLACEHOLDER_ATTRIBUTION',
  missing_reason: null,
  detail: null,
}

const SOIL_EXAMPLE = {
  id: 'PLACEHOLDER_SOIL',
  contract: 'site_data_soil_slope',
  state: 'example',
  retrieved_at: null,
  time_zone: null,
  request: null,
  attribution: null,
  missing_reason: null,
  detail: null,
}

const CLIMATE_UNAVAILABLE = {
  id: 'PLACEHOLDER_CLIMATE',
  contract: 'site_data_climate',
  state: 'unavailable',
  retrieved_at: null,
  time_zone: null,
  request: null,
  attribution: null,
  missing_reason: 'NOT_AVAILABLE',
  detail: null,
}

const SOURCE_TEXT = 'PLACEHOLDER source: written by hand, not the output of an engine'

const RESULT_PRESENT = {
  case_id: 'example-case',
  field_id: 'example-field-1',
  rotation_id: 'example-rotation-1',
  soil_loss: {
    annual: [
      {
        ag_year: 2001,
        indicator: 'soil_loss',
        direction: 'lower_is_better',
        value: 12.0,
        unit: 't ha-1 yr-1',
        range: { low: 6.0, high: 18.0, kind: 'PLACEHOLDER_range_kind' },
        provenance: 'DERIVED',
        source: SOURCE_TEXT,
      },
      {
        ag_year: 2002,
        indicator: 'soil_loss',
        direction: 'lower_is_better',
        value: null,
        unit: 't ha-1 yr-1',
        missing: {
          reason: 'NO_COVERAGE',
          detail: 'PLACEHOLDER detail: the example series ends before this agricultural year does',
        },
      },
    ],
    monthly: [
      {
        year: 2001,
        month: 7,
        ag_year: 2001,
        indicator: 'soil_loss',
        direction: 'lower_is_better',
        value: 1.0,
        unit: 't ha-1 month-1',
        range_missing: {
          reason: 'NOT_AVAILABLE',
          detail: 'PLACEHOLDER detail: this example gives no range for a monthly value',
        },
        provenance: 'DERIVED',
        source: SOURCE_TEXT,
      },
      {
        year: 2002,
        month: 1,
        ag_year: 2001,
        indicator: 'soil_loss',
        direction: 'lower_is_better',
        value: null,
        unit: 't ha-1 month-1',
        missing: {
          reason: 'NO_COVERAGE',
          detail: 'PLACEHOLDER detail: the example series ends before this month',
        },
      },
    ],
  },
  water_deficit_exposure: [
    {
      time_basis: 'rotation',
      indicator: 'water_deficit_exposure',
      direction: 'higher_is_better',
      value: null,
      unit: 'dimensionless',
      missing: {
        reason: 'NOT_AVAILABLE',
        detail: 'PLACEHOLDER detail: the definition of this indicator is incomplete (conventions C1.4), so it is reported as missing',
      },
    },
  ],
  soil_carbon_trend: [
    {
      carbon_model: 'amg',
      computation: 'end_minus_start',
      indicator: 'soil_carbon_trend',
      direction: 'higher_is_better',
      value: 0.5,
      unit: 't C ha-1 yr-1',
      range: { low: -0.5, high: 1.5, kind: 'PLACEHOLDER_range_kind' },
      provenance: 'SIMULATED',
      source: SOURCE_TEXT,
    },
    {
      carbon_model: 'rothc',
      computation: 'mean_over_cycles',
      indicator: 'soil_carbon_trend',
      direction: 'higher_is_better',
      value: null,
      unit: 't C ha-1 yr-1',
      missing: {
        reason: 'NOT_COMPUTABLE',
        detail: 'PLACEHOLDER detail: the example horizon holds no whole rotation cycle',
      },
    },
  ],
}

/** A 200 answer with a result: the shape of api/rotations.py, values of the results example. */
// The route serializes the contract without exclude_none: every pydantic
// default travels as an explicit null ("missing": null, "range": null, ...,
// "assumption": false). These helpers turn the hand-shaped fixtures above into
// the exact wire shape, so the suite pins what the route really sends.
function wireItem(item: Record<string, unknown>): Record<string, unknown> {
  return {
    ...item,
    missing: (item.missing ?? null) as unknown,
    range: (item.range ?? null) as unknown,
    range_missing: (item.range_missing ?? null) as unknown,
    provenance: (item.provenance ?? null) as unknown,
    source: (item.source ?? null) as unknown,
    assumption: (item.assumption ?? false) as unknown,
  }
}

function wireResult(result: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...result }
  for (const [key, value] of Object.entries(result)) {
    if (Array.isArray(value)) {
      out[key] = value.map((item) =>
        item !== null && typeof item === 'object' && 'indicator' in (item as Record<string, unknown>)
          ? wireItem(item as Record<string, unknown>)
          : item,
      )
    } else if (value !== null && typeof value === 'object' && 'indicator' in (value as Record<string, unknown>)) {
      out[key] = wireItem(value as Record<string, unknown>)
    }
  }
  return out
}

const RESULT_PRESENT_WIRE = wireResult(RESULT_PRESENT)

const ENVELOPE_200 = {
  outcome: 'partial',
  calendar: null,
  result: RESULT_PRESENT_WIRE,
  result_missing: null,
  modules: [
    { id: 'PLACEHOLDER_MODULE_A', state: 'available', reason: null, detail: null },
    {
      id: 'PLACEHOLDER_MODULE_B',
      state: 'degraded',
      reason: 'MISSING_INPUT',
      detail: 'PLACEHOLDER_DETAIL',
    },
  ],
  sources: [CLIMATE_FRESH, SOIL_EXAMPLE],
}

/** A 200 answer with no result: the shape the default app answers with. */
const ENVELOPE_200_NO_RESULT = {
  outcome: 'no_result',
  calendar: null,
  result: null,
  result_missing: { reason: 'NOT_AVAILABLE', detail: null },
  modules: [
    { id: 'PLACEHOLDER_MODULE', state: 'not_available', reason: 'NOT_AVAILABLE', detail: null },
  ],
  sources: [CLIMATE_UNAVAILABLE, SOIL_EXAMPLE],
}

/** The one error shape of api/errors.py. */
const ERROR_ROTATION_INVALID = {
  error: {
    code: 'ROTATION_INVALID',
    message: 'The rotation of the request is not valid.',
    details: [
      {
        path: 'rotation.components.0.purpose',
        code: 'literal_error',
        message: 'The value breaks a rule of the rotation definition contract.',
      },
    ],
  },
}

// --- helpers -------------------------------------------------------------------

const SITE: SiteReference = {
  case_id: 'example-case',
  field_id: 'example-field-1',
  latitude: -33.013,
  longitude: -57.0065,
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function renderPanel(state: RotationRunState): string {
  return renderToString(
    <RotationRunPanel state={state} onRun={() => {}} runName={rotationDefinition.label} />,
  )
}

async function caughtError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('the promise was expected to reject')
}

// --- the fetcher ----------------------------------------------------------------

describe('runRotation: the platform-route call', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs the site and the rotation document unchanged, and resolves the 200 envelope', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    vi.stubGlobal(
      'fetch',
      (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        calls.push({ url: String(input), init: init ?? {} })
        return Promise.resolve(jsonResponse(200, ENVELOPE_200))
      },
    )

    const body = await runRotation(SITE, rotationDefinition.document)

    expect(body).toEqual(ENVELOPE_200)
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(runRotationUrl())
    expect(calls[0].url).toContain('/api/rotations/run')
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      site: SITE,
      rotation: rotationDefinition.document,
    })
    // the rotation travels as the contract example, unedited
    expect(rotationDefinition.document).toEqual(rawRotation)
  })

  it('rejects with the code of a 4xx error shape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(422, ERROR_ROTATION_INVALID)),
    )

    const error = await caughtError(runRotation(SITE, rotationDefinition.document))

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('ROTATION_INVALID')
  })

  it('rejects with UNEXPECTED when the connection fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )

    const error = await caughtError(runRotation(SITE, rotationDefinition.document))

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('UNEXPECTED')
  })

  it('rejects with UNEXPECTED when an error body carries no code of the closed list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('bad gateway', { status: 502 })),
    )

    const error = await caughtError(runRotation(SITE, rotationDefinition.document))

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('UNEXPECTED')
  })
})

// --- the envelope parser ---------------------------------------------------------

describe('parseRunRotation: the success envelope', () => {
  it("parses a present value that carries the route's explicit nulls (wire shape)", () => {
    // model_dump without exclude_none: value present, "missing": null, "range": null, ...
    const view = parseRunRotation(ENVELOPE_200)
    const rows = view.parts.flatMap((part) => part.rows)
    const present = rows.find((row) => row.item.value !== null)
    expect(present).toBeDefined()
    expect(present?.item.provenance).toBe('DERIVED')
    expect(present?.item.missing).toBeUndefined()
  })

  it('reads the outcome, the live-data flag and one row per indicator item', () => {
    const view = parseRunRotation(ENVELOPE_200)

    expect(view.outcome).toBe('partial')
    expect(view.liveData).toBe(true)
    expect(view.resultMissing).toBe(null)
    expect(view.parts.map((part) => part.indicator)).toEqual([
      'soil_loss',
      'water_deficit_exposure',
      'soil_carbon_trend',
    ])
    expect(view.parts[0].rows.map((row) => row.what)).toEqual([
      'soil_loss 2001',
      'soil_loss 2002',
      'soil_loss 2001-07',
      'soil_loss 2002-01',
    ])
    expect(view.parts[1].rows.map((row) => row.what)).toEqual(['water_deficit_exposure'])
    expect(view.parts[2].rows.map((row) => row.what)).toEqual([
      'soil_carbon_trend amg end_minus_start',
      'soil_carbon_trend rothc mean_over_cycles',
    ])
    // a present value keeps its unit, provenance, source and range
    expect(view.parts[0].rows[0].item).toEqual({
      value: 12,
      unit: 't ha-1 yr-1',
      provenance: 'DERIVED',
      source: SOURCE_TEXT,
      assumption: undefined,
      range: { low: 6, high: 18, kind: 'PLACEHOLDER_range_kind' },
      range_missing: undefined,
    })
  })

  it('keeps a missing value missing, with its reason and its unit, never zero', () => {
    const view = parseRunRotation(ENVELOPE_200)

    expect(view.parts[0].rows[1].item).toEqual({
      value: null,
      unit: 't ha-1 yr-1',
      missing: {
        reason: 'NO_COVERAGE',
        detail: 'PLACEHOLDER detail: the example series ends before this agricultural year does',
      },
    })
  })

  it('carries the reason of a result that is absent altogether', () => {
    const view = parseRunRotation(ENVELOPE_200_NO_RESULT)

    expect(view.outcome).toBe('no_result')
    expect(view.liveData).toBe(false)
    expect(view.parts).toEqual([])
    expect(view.resultMissing).toEqual({ reason: 'NOT_AVAILABLE' })
  })

  it('renders a part whose engine is not built as one missing item per unit', () => {
    const view = parseRunRotation({
      ...ENVELOPE_200,
      result: {
        ...RESULT_PRESENT,
        soil_loss: {
          indicator: 'soil_loss',
          direction: 'lower_is_better',
          units: ['t ha-1 yr-1', 't ha-1 month-1'],
          missing: { reason: 'NOT_AVAILABLE', detail: null },
        },
      },
    })

    expect(view.parts[0].rows).toHaveLength(2)
    expect(view.parts[0].rows[0].item.value).toBe(null)
    expect(view.parts[0].rows[0].item.unit).toBe('t ha-1 yr-1')
    expect(view.parts[0].rows[1].item.unit).toBe('t ha-1 month-1')
  })

  it('refuses an envelope that is not the route\u2019s shape', () => {
    expect(() => parseRunRotation({ outcome: 'junk', sources: [] })).toThrow()
    expect(() => parseRunRotation(null)).toThrow()
    expect(() =>
      parseRunRotation({ ...ENVELOPE_200, result: null, result_missing: null }),
    ).toThrow()
  })
})

// --- the panel -------------------------------------------------------------------

describe('RotationRunPanel: idle and pending', () => {
  it('shows the run action with the live-data string, and nothing else', () => {
    const html = renderPanel({ phase: 'idle' })
    expect(html).toContain(strings['seam.with_real_data'])
    expect(html).not.toContain('data-testid="rotation-run-loading"')
    expect(html).not.toContain('data-testid="rotation-run-error"')
    expect(html).not.toContain('data-testid="rotation-run-response"')
    expect(html).not.toContain('disabled=""')
  })

  it('shows the shared loading string and disables the action while the run is pending', () => {
    const html = renderPanel({ phase: 'pending' })
    expect(html).toContain(strings['common.loading'])
    expect(html).toContain('disabled=""')
    expect(html).not.toContain('data-testid="rotation-run-response"')
  })
})

describe('RotationRunPanel: a failed run', () => {
  it('shows the string of the error code, with the raw code visible', () => {
    const html = renderPanel({ phase: 'error', error: new ApiError('ROTATION_INVALID') })
    expect(html).toContain(strings['api.ROTATION_INVALID'])
    expect(html).toContain('code: ROTATION_INVALID')
    expect(html).not.toContain('data-testid="rotation-run-response"')
  })

  it('shows the connection string for a network failure, through the real fetcher', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )
    const error = await caughtError(runRotation(SITE, rotationDefinition.document))
    vi.unstubAllGlobals()

    const html = renderPanel({ phase: 'error', error })
    expect(html).toContain(strings['api.UNEXPECTED'])
    expect(html).toContain('code: UNEXPECTED')
  })

  it('shows the shared error string for an error that is not of the route', () => {
    const html = renderPanel({ phase: 'error', error: new Error('defect') })
    expect(html).toContain(strings['common.error'])
  })
})

describe('RotationRunPanel: a completed run, through the real fetcher and parser', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('labels the live data and renders every value through the value display', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_200)))
    const view = parseRunRotation(await runRotation(SITE, rotationDefinition.document))

    const html = renderPanel({ phase: 'success', view })
    const text = visibleText(html)

    // the live-data label shows beside real data, and the run is named
    expect(countTestIds(html, 'rotation-run-live')).toBe(1)
    expect(text).toContain(strings['seam.with_real_data'])
    expect(html).toContain(rotationDefinition.label)
    expect(html).toContain('partial')
    // present values: number, unit, provenance label, source, range
    expect(text).toContain('12 t ha-1 yr-1 Derived')
    expect(text).toContain('Source: ' + SOURCE_TEXT)
    expect(text).toContain('6 to 18 (PLACEHOLDER_range_kind)')
    expect(text).toContain('0.5 t C ha-1 yr-1 Simulated')
    expect(countTestIds(html, 'value-line')).toBe(3)
    // missing values keep their reason, never a zero
    expect(text).toContain('soil_loss 2002: no coverage for this place or period')
    expect(text).toContain('soil_loss 2002-01: no coverage for this place or period')
    expect(text).toContain('water_deficit_exposure: module not built or not enabled')
    expect(text).toContain('soil_carbon_trend rothc mean_over_cycles: not computable for this case')
    expect(countTestIds(html, 'missing-line')).toBe(4)
    expect(text).not.toContain(': 0')
  })

  it('keeps the live-data label off a run whose climate source did not answer, and names the absent result', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_200_NO_RESULT)))
    const view = parseRunRotation(await runRotation(SITE, rotationDefinition.document))

    const html = renderPanel({ phase: 'success', view })
    const text = visibleText(html)

    expect(html).not.toContain('data-testid="rotation-run-live"')
    expect(text).toContain('Illustrative rotation: module not built or not enabled')
    expect(countTestIds(html, 'missing-line')).toBe(0)
    expect(countTestIds(html, 'value-line')).toBe(0)
  })
})

// --- the container ----------------------------------------------------------------

describe('RotationRun on the fields view', () => {
  function renderSeam(): string {
    const client = new QueryClient()
    return renderToString(
      <QueryClientProvider client={client}>
        <RotationRun />
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    setSelectedFieldId(null)
  })

  afterEach(() => {
    setSelectedFieldId(null)
    vi.unstubAllGlobals()
  })

  it('shows nothing when no field is selected', () => {
    expect(renderSeam()).not.toContain('data-testid="rotation-run"')
  })

  it('shows nothing for a field the example rotation does not belong to', () => {
    setSelectedFieldId('example-field-2')
    expect(renderSeam()).not.toContain('data-testid="rotation-run"')
  })

  it('shows the run action for the field of the example rotation, idle', () => {
    setSelectedFieldId(rotationDefinition.field_id)
    const html = renderSeam()
    expect(html).toContain('data-testid="rotation-run-action"')
    expect(html).toContain(strings['seam.with_real_data'])
    expect(html).not.toContain('data-testid="rotation-run-loading"')
    expect(html).not.toContain('data-testid="rotation-run-response"')
  })
})

// --- the point that stands for the field -------------------------------------------

describe('siteReferenceOf: the point of the request', () => {
  it('derives the point of the rotation\u2019s field from its declared geometry', () => {
    const field = exampleCase.fields.find((f) => f.field_id === rotationDefinition.field_id)
    expect(field).toBeDefined()
    const site = siteReferenceOf(exampleCase.case_id, field!)

    expect(site).toEqual({
      case_id: exampleCase.case_id,
      field_id: rotationDefinition.field_id,
      latitude: expect.closeTo(-33.013, 10),
      longitude: expect.closeTo(-57.0065, 10),
    })
  })
})
