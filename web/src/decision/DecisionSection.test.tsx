import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToString } from 'react-dom/server'
import rawDecisionOutput from '../data/PLACEHOLDER_decision_output.json'
import rawDemoRotations from '../data/demo_rotations_d128.json'
import rawSavedCase from '../data/saved_case.json'
import { missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { rotationDefinition } from '../seam/rotationDefinition'
import type { RotationDefinitionExample } from '../seam/rotationDefinition'
import { ApiError } from '../seam/runRotationApi'
import { strings } from '../strings'
import DecisionSection, {
  DecisionPanel,
  HELD_ROTATIONS,
  filterCountsByYear,
  filterScenarioYearDifferences,
  notCalledReason,
  sectionStateOf,
} from './DecisionSection'
import type { DecisionSectionState, YearSelection } from './DecisionSection'
import {
  agriculturalYearsOf,
  decisionExample,
  parseDecisionOutput,
  samePair,
} from './decisionData'
import { demoRotationsD128, parseDemoRotations } from './demoRotations'
import {
  decisionRequestOf,
  parseRunDecision,
  runDecision,
  runDecisionUrl,
} from './decisionRoute'

/**
 * Acceptance test of the decision section (issues #241, #354, and Block 4
 * "Measure first" with its field and named-years selector). The panel is a
 * pure function of its state (with optional controlled year selection for
 * tests), so its whole behaviour is its static markup, rendered with the pure
 * server renderer of react-dom. Every expected text below is the supplied
 * wording of strings.ts filled with the values of the data, written out in
 * full.
 *
 * The bundled example (issue #241), the fallback of the section:
 * (a) one block per rotation pair of the example, named by its two
 *     rotations through decision.pair_of;
 * (b) the state of a pair renders verbatim from the data, with its reason;
 * (c) the two counts render under their own headings, apart, never summed;
 * (d) the coverage and the years-within summary render from the data;
 * (e) the example banner is visible;
 * (f) nothing the section does not render is invented;
 * (g) Block 4: measure_first (D4) renders ranked items with field_id or
 *     NOT_DECLARED when empty, and the named-years selector discovers
 *     distinct agricultural years from the data and filters counts_by_year
 *     and scenario-year rows.
 *
 * The route's document (issue #354), with the route mocked: no real
 * network. The fetch boundary is stubbed with the shapes of api/decisions.py
 * and api/errors.py, and the states a browser reaches through the query are
 * produced by running the real fetcher and the real parser against the
 * stub, then handing the outcome to the panel, the same path the container
 * takes:
 * - a document is shown, from the route, with its absences and reasons;
 * - a null decision shows the route's reason, then the bundled example,
 *   labelled;
 * - an error, or a failed connection, falls back to the bundled example,
 *   labelled, after the message and code of the error.
 */

/** How many times a data-testid appears in a server-rendered markup. */
function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

/** How many times an exact text appears in a markup. */
function countText(html: string, text: string): number {
  return html.split(text).length - 1
}

/** The whole visible text of a markup, tags dropped, runs of spaces joined. */
function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** The section with the bundled example: the state of a field with no call. */
function renderExample(): string {
  return renderToString(<DecisionPanel state={{ phase: 'not-called', missing: null }} />)
}

function renderState(state: DecisionSectionState, selectedYear?: YearSelection): string {
  return renderToString(<DecisionPanel state={state} selectedYear={selectedYear} />)
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

const PAIRS = decisionExample.pair_states

describe('DecisionSection: the bundled example', () => {
  // -- the section, the pairs heading and the example banner (e) -------------------

  it('renders the section title and the rotation-pairs heading', () => {
    const html = renderExample()
    expect(html).toContain(strings['decision.title'])
    expect(html).toContain(strings['decision.pairs'])
  })

  it('labels the example data with the example banner (e)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(html).toContain(strings['example.banner'])
    expect(html).toContain('data-source="example"')
  })

  // -- (a) one block per pair, named by its two rotations ---------------------------

  it('renders one block per pair the example carries, named by decision.pair_of (a)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-pair')).toBe(PAIRS.length)
    for (const state of PAIRS) {
      expect(html).toContain(
        formatString(strings['decision.pair_of'], {
          first: state.pair[0],
          second: state.pair[1],
        }),
      )
    }
    expect(html).toContain('example-rotation-1 against example-rotation-2')
  })

  // -- (b) the state renders verbatim, with its reason -------------------------------

  it('renders the state of each pair verbatim from the data, under the state label (b)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-state-heading')).toBe(PAIRS.length)
    expect(countTestIds(html, 'decision-state-value')).toBe(PAIRS.length)
    expect(html).toContain(strings['decision.state'])
    expect(html).toContain('Not separated: uncertainty missing')
  })

  it('renders the reason of the state verbatim from the data (b)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-state-reason')).toBe(1)
    expect(html).toContain('a difference without its range')
    // the example names no preferred rotation, and none is rendered
    expect(countTestIds(html, 'decision-state-preferred')).toBe(0)
  })

  it('renders the coverage of each pair from the data (d)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-coverage')).toBe(PAIRS.length)
    expect(html).toContain('2 of 5 cells compared')
  })

  // -- (c) the two counts apart, under their headings, never summed ------------------

  it('renders one counts group per counted cell of the pair, labelled by its identifiers (c)', () => {
    const html = renderExample()
    const counts = decisionExample.pair_cell_counts.filter((count) =>
      samePair(count.pair, PAIRS[0].pair),
    )
    expect(countTestIds(html, 'decision-counts-group')).toBe(counts.length)
    expect(html).toContain(strings['decision.counts'])
    for (const count of counts) {
      expect(html).toContain(`${count.indicator} ${count.scenario_id}`)
    }
  })

  it('renders the two counts of every group under their own headings (c)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-counts-by-point-heading')).toBe(3)
    expect(countTestIds(html, 'decision-counts-by-range-heading')).toBe(3)
    expect(html).toContain(strings['decision.counts_by_point'])
    expect(html).toContain(strings['decision.counts_by_range'])
  })

  it('renders the counts by point value under the approved labels, with the numbers of the example (c)', () => {
    const html = renderExample()
    // Only soil_loss has the tolerance of "equal"; its four counts render.
    expect(countTestIds(html, 'decision-counts-by-point')).toBe(1)
    const text = visibleText(html)
    expect(text).toContain('Better 1')
    expect(text).toContain('Worse 0')
    expect(text).toContain('Equal 0')
    expect(text).toContain('Missing side 1')
  })

  it('renders the counts by range under the identifiers of the contract, with the numbers of the example (c)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-counts-by-range')).toBe(3)
    const text = visibleText(html)
    expect(text).toContain('strict_improvement 0')
    expect(text).toContain('deterioration 0')
    expect(text).toContain('not_separated 1')
  })

  it('renders a count without the tolerance of equal as missing with its reason, never zeros (c)', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-counts-by-point-missing')).toBe(2)
    // The full missing pattern of the example, in its apostrophe-free parts
    // (the server renderer escapes the apostrophes of the detail as entities).
    expect(countText(html, 'By point value: not declared for this case')).toBe(2)
    expect(countText(html, 'is set for this indicator (D87)')).toBe(2)
  })

  it('never sums the counts: every count row shows the number of the data, and no total (c)', () => {
    const html = renderExample()
    // 4 rows of the point-value count of soil_loss, 3 range rows per group.
    expect(countTestIds(html, 'decision-count-row')).toBe(4 + 3 * 3)
    // The sums the two counts must never produce (2 = 1 better + 1 missing
    // side; 1 = 0 + 0 + 1 of the range count) appear as no count number.
    expect(countText(html, '>2<')).toBe(0)
    const text = visibleText(html)
    expect(text).not.toContain('Better 2')
    expect(text).not.toContain('Total')
  })

  // -- (d) the years-within summary ----------------------------------------------------

  it('renders the years-within summary of each rotation of the pair, from the data (d)', () => {
    const html = renderExample()
    const years = decisionExample.range_across_scenarios.filter((entry) =>
      PAIRS[0].pair.includes(entry.rotation_id),
    )
    expect(countTestIds(html, 'decision-years-within')).toBe(years.length)
    expect(html).toContain('example-rotation-1 soil_loss')
    expect(html).toContain('example-rotation-2 soil_loss')
    const sentence = formatString(strings['decision.years_within'], {
      min: 0,
      max: 0,
      scenario: 'PLACEHOLDER_scenario_one',
    })
    expect(html).toContain('Years within the limit: 0 to 0, minimum at PLACEHOLDER_scenario_one')
    expect(countText(html, sentence)).toBe(years.length)
  })

  // -- the state of the decision (#354) ----------------------------------------------

  it('renders the state of the decision verbatim, with its reasons as data', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-overall-heading')).toBe(1)
    expect(countTestIds(html, 'decision-overall-value')).toBe(1)
    expect(html).toContain('OPEN: exact wording by the science reviewers')
    expect(countTestIds(html, 'decision-overall-reason')).toBe(1)
    expect(html).toContain('PLACEHOLDER reason: the wording of a reason comes from deterministic templates')
  })

  // -- (f) no invented field -----------------------------------------------------------

  it('renders nothing for the parts it does not render: no limits, no tolerances, no paired-difference method or rotation-basis differences (f)', () => {
    const html = renderExample()
    // The limit value and its reason (limits).
    expect(html).not.toContain('the user declared the limit without a range')
    expect(html).not.toContain('no limit is declared for this indicator')
    // The rotation-basis paired differences and the paired-difference method.
    expect(html).not.toContain('end_minus_start')
    expect(html).not.toContain('paired-difference method')
    // The tolerance of soil_loss and other indicators.
    expect(html).not.toContain('the designer of the case set the tolerance without a range')
    expect(html).not.toContain('the designer of the case set no tolerance')
    // No raw contract field names leaked into visible markup.
    expect(html).not.toContain('years_evaluated')
    // No reason line: no call was attempted and no reason was given.
    expect(countTestIds(html, 'decision-not-called')).toBe(0)
    expect(countTestIds(html, 'decision-route-missing')).toBe(0)
    expect(countTestIds(html, 'decision-route-error')).toBe(0)
  })
})

// --- Block 4: Measure first with its field & named-years selector --------------------

describe('Measure first (D4) with its field', () => {
  it('renders measure_first items with rank, scope and priority reason beside field_id on the bundled example', () => {
    const html = renderExample()
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-measure-first')).toBe(1)
    expect(text).toContain(strings['decision.measure_first'])
    expect(text).toContain('Field: example-field-1')
    expect(countTestIds(html, 'decision-measure-first-item')).toBe(1)
    expect(text).toContain('Rank 1')
    expect(text).toContain('residue cover at sowing')
    expect(text).toContain('illustrative: moves the soil-loss difference more than the evaluated inputs')
    expect(countTestIds(html, 'decision-measure-first-empty')).toBe(0)
  })

  it('renders tied-rank items from saved_case decision_output verbatim with its field', () => {
    const savedDecision = parseDecisionOutput(rawSavedCase.decision_output)
    const html = renderState({
      phase: 'answered',
      answer: { kind: 'decision', document: savedDecision, liveData: false },
    })
    const text = visibleText(html)

    expect(text).toContain(`Field: ${savedDecision.field_id}`)
    expect(countTestIds(html, 'decision-measure-first-item')).toBe(savedDecision.measure_first.length)
    expect(countText(text, 'Rank 2')).toBe(3)
    expect(text).toContain('&#x27;u&#x27; (the 2022 soil loss of rotations B and C, t ha-1 yr-1)')
    expect(text).toContain('the admitted values of')
  })

  it('shows NOT_DECLARED via the shared missing pattern when measure_first is empty, never inventing parameters', () => {
    const routeDoc = parseDecisionOutput(ROUTE_DOCUMENT)
    const html = renderState({
      phase: 'answered',
      answer: { kind: 'decision', document: routeDoc, liveData: true },
    })
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-measure-first-item')).toBe(0)
    expect(countTestIds(html, 'decision-measure-first-empty')).toBe(1)
    expect(text).toContain(`Field: ${routeDoc.field_id}`)
    expect(text).toContain(
      missingPatternText(strings['decision.measure_first'], {
        reason: 'NOT_DECLARED',
        detail: strings['decision.measure_first_not_declared'],
      }),
    )
  })
})

describe('named-years selector and year filtering', () => {
  it('discovers distinct agricultural years strictly from counts_by_year and paired_differences, sorted ascending', () => {
    expect(agriculturalYearsOf(decisionExample)).toEqual([2001, 2002])
    expect(agriculturalYearsOf(parseDecisionOutput(ROUTE_DOCUMENT))).toEqual([])
    expect(agriculturalYearsOf(parseDecisionOutput(rawSavedCase.decision_output))).toEqual([
      2020, 2021, 2022, 2023,
    ])
  })

  it('renders the selector with All years plus discovered agricultural years on the bundled example', () => {
    const html = renderExample()
    expect(countTestIds(html, 'decision-named-years')).toBe(1)
    expect(html).toContain(strings['decision.named_years'])
    expect(html).toContain(`<option value="all" selected="">${strings['decision.named_years_all']}</option>`)
    expect(html).toContain('<option value="2001">2001</option>')
    expect(html).toContain('<option value="2002">2002</option>')
    expect(countTestIds(html, 'decision-named-years-none')).toBe(0)
  })

  it('renders a disabled selector with no invented years when the document carries no agricultural years', () => {
    const routeDoc = parseDecisionOutput(ROUTE_DOCUMENT)
    const html = renderState({
      phase: 'answered',
      answer: { kind: 'decision', document: routeDoc, liveData: true },
    })
    expect(html).toContain('disabled=""')
    expect(countTestIds(html, 'decision-named-years-none')).toBe(1)
    expect(html).toContain(strings['decision.named_years_none'])
    expect(countTestIds(html, 'decision-counts-by-year-empty')).toBe(1)
    expect(countTestIds(html, 'decision-scenario-years-empty')).toBe(1)
  })

  it('shows all counts_by_year and scenario-year rows when All years is selected', () => {
    const html = renderExample()
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-count-by-year-item')).toBe(2)
    expect(countTestIds(html, 'decision-not-evaluated-row')).toBe(2)
    expect(text).toContain('1 evaluated, 0 within the limit')
    expect(text).toContain('Not evaluated 2002: no coverage for this place or period')
    expect(countTestIds(html, 'decision-scenario-year-row')).toBe(2)
    expect(text).toContain('example-rotation-1 against example-rotation-2 PLACEHOLDER_scenario_one soil_loss 2001')
    expect(text).toContain('-4 t ha-1 yr-1 Derived')
    expect(text).toContain('-14 to 6 (PLACEHOLDER_range_kind)')
    expect(text).toContain('soil_loss 2002: missing input:')
  })

  it('filters counts_by_year not-evaluated rows and scenario-year rows when a specific year is selected', () => {
    const html2001 = renderState({ phase: 'not-called', missing: null }, 2001)
    const text2001 = visibleText(html2001)
    expect(html2001).toContain('<option value="2001" selected="">2001</option>')
    expect(countTestIds(html2001, 'decision-not-evaluated-row')).toBe(0)
    expect(text2001).not.toContain('Not evaluated 2002')
    expect(countTestIds(html2001, 'decision-scenario-year-row')).toBe(1)
    expect(text2001).toContain('soil_loss 2001')
    expect(text2001).toContain('-4 t ha-1 yr-1 Derived')
    expect(text2001).not.toContain('soil_loss 2002: missing input')

    const html2002 = renderState({ phase: 'not-called', missing: null }, 2002)
    const text2002 = visibleText(html2002)
    expect(html2002).toContain('<option value="2002" selected="">2002</option>')
    expect(countTestIds(html2002, 'decision-not-evaluated-row')).toBe(2)
    expect(text2002).toContain('Not evaluated 2002')
    expect(countTestIds(html2002, 'decision-scenario-year-row')).toBe(1)
    expect(text2002).toContain('soil_loss 2002: missing input')
    expect(text2002).not.toContain('-14 to 6')
  })

  it('handles unjudged counts_by_year (years_within_limits null) with NOT_DECLARED and filters by year', () => {
    const docWithUnjudged = parseDecisionOutput({
      ...ROUTE_DOCUMENT,
      counts_by_year: [
        {
          rotation_id: PAIR[0],
          scenario_id: 'phase_1+phase_1',
          indicator: 'soil_loss',
          carbon_model: null,
          computation: null,
          years_evaluated: 0,
          years_within_limits: null,
          not_evaluated: [
            {
              time_basis: 'ag_year',
              ag_year: 2020,
              carbon_model: null,
              computation: null,
              missing: { reason: 'NOT_DECLARED', detail: 'no limit declared' },
            },
            {
              time_basis: 'ag_year',
              ag_year: 2021,
              carbon_model: null,
              computation: null,
              missing: { reason: 'NO_COVERAGE', detail: 'missing climate' },
            },
          ],
        },
      ],
    })

    const htmlAll = renderState({
      phase: 'answered',
      answer: { kind: 'decision', document: docWithUnjudged, liveData: false },
    })
    const textAll = visibleText(htmlAll)
    expect(textAll).toContain('0 evaluated')
    expect(textAll).toContain('Years within the limit: not declared for this case')
    expect(countTestIds(htmlAll, 'decision-not-evaluated-row')).toBe(2)

    const html2021 = renderState(
      { phase: 'answered', answer: { kind: 'decision', document: docWithUnjudged, liveData: false } },
      2021,
    )
    const text2021 = visibleText(html2021)
    expect(countTestIds(html2021, 'decision-not-evaluated-row')).toBe(1)
    expect(text2021).toContain('Not evaluated 2021: no coverage for this place or period')
    expect(text2021).not.toContain('Not evaluated 2020')
  })

  it('falls back to All years if a selected year is not present in the document', () => {
    const html = renderState({ phase: 'not-called', missing: null }, 2099)
    expect(html).toContain(`<option value="all" selected="">${strings['decision.named_years_all']}</option>`)
    expect(countTestIds(html, 'decision-scenario-year-row')).toBe(2)
  })

  it('filterCountsByYear and filterScenarioYearDifferences filter purely without mutating inputs', () => {
    expect(filterCountsByYear(decisionExample.counts_by_year, 'all')).toHaveLength(2)
    expect(filterCountsByYear(decisionExample.counts_by_year, 2001).map((c) => c.notEvaluated)).toEqual([
      [],
      [],
    ])
    expect(filterCountsByYear(decisionExample.counts_by_year, 2002).map((c) => c.notEvaluated.length)).toEqual([
      1, 1,
    ])
    expect(filterScenarioYearDifferences(decisionExample.paired_differences, 'all')).toHaveLength(2)
    expect(filterScenarioYearDifferences(decisionExample.paired_differences, 2001)).toHaveLength(1)
    expect(filterScenarioYearDifferences(decisionExample.paired_differences, 2002)).toHaveLength(1)
  })
})

// --- the route's shapes (placeholders; api/decisions.py, api/errors.py) ------------

const FIELD = exampleCase.fields.find((f) => f.field_id === 'example-field-1')!
const OTHER_FIELD = exampleCase.fields.find((f) => f.field_id !== FIELD.field_id)!

/** The two rotations of D128 the interface holds for example-field-1. */
const TWO_HELD: readonly RotationDefinitionExample[] = demoRotationsD128

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

const PAIR = ['soybean-winter-fallow', 'wheat-soybean-maize']

/** A count of a pair's cells as the platform writes it: every null kept. */
function routeCount(
  scenario: string,
  indicator: string,
  carbonModel: string | null,
  computation: string | null,
  range: [number, number, number],
) {
  return {
    pair: PAIR,
    scenario_id: scenario,
    indicator,
    carbon_model: carbonModel,
    computation,
    by_difference_range: {
      strict_improvement: range[0],
      deterioration: range[1],
      not_separated: range[2],
    },
    by_sign_of_point_value: null,
    by_sign_of_point_value_missing: {
      reason: 'NOT_DECLARED',
      detail: 'no tolerance of equal is declared for this indicator (D87, D99)',
    },
  }
}

/** A range across scenarios that is not given, as the platform writes it. */
function routeRangeMissing(rotation: string, indicator: string) {
  return {
    rotation_id: rotation,
    indicator,
    carbon_model: null,
    computation: null,
    minimum: null,
    maximum: null,
    scenario_of_the_minimum: null,
    missing: {
      reason: 'NOT_DECLARED',
      detail: 'no limit is declared for this indicator, so no year is judged (D60)',
    },
  }
}

/** The decision document of the route: placeholders, nulls kept, no example mark. */
const ROUTE_DOCUMENT = {
  contract: 'decision_output',
  example_data: false,
  case_id: exampleCase.case_id,
  field_id: FIELD.field_id,
  rotations: PAIR,
  scenarios: ['phase_1+phase_1', 'phase_1+phase_2'],
  limits: [],
  counts_by_year: [],
  range_across_scenarios: [
    routeRangeMissing(PAIR[0], 'soil_loss'),
    routeRangeMissing(PAIR[1], 'soil_loss'),
  ],
  paired_differences: [],
  equal_tolerances: [],
  pair_cell_counts: [
    routeCount('phase_1+phase_1', 'soil_loss', null, null, [0, 0, 7]),
    routeCount('phase_1+phase_1', 'soil_carbon_trend', 'amg', 'end_minus_start', [1, 0, 0]),
    routeCount('phase_1+phase_1', 'soil_carbon_trend', 'rothc', 'end_minus_start', [0, 1, 0]),
  ],
  pair_states: [
    {
      pair: PAIR,
      value: 'Not robust across scenarios',
      missing: null,
      reason: 'not robust across the admitted scenarios',
      reason_missing: null,
      preferred_rotation_id: null,
      coverage: { cells_compared: 46, cells_of_the_pair: 112 },
    },
  ],
  state: {
    value: null,
    missing: {
      reason: 'NOT_AVAILABLE',
      detail: 'no decision says how the one state relates to the states of its pairs',
    },
    indicators_not_resolved: ['soil_loss'],
    reasons: [
      'in scenario phase_1+phase_1 the pair is Not separated: uncertainty missing',
      'in scenario phase_1+phase_2 the pair is Not separated: uncertainty missing',
    ],
  },
  measure_first: [],
}

const ROTATION_SUMMARIES = PAIR.map((rotation_id) => ({
  rotation_id,
  outcome: 'partial',
  result_missing: null,
  modules: [],
  phases: [],
}))

const ENVELOPE_DECISION = {
  decision: ROUTE_DOCUMENT,
  decision_missing: null,
  scenarios: [
    {
      scenario_id: 'phase_1+phase_1',
      phases: PAIR.map((rotation_id) => ({ rotation_id, phase: 'phase_1' })),
    },
    {
      scenario_id: 'phase_1+phase_2',
      phases: [
        { rotation_id: PAIR[0], phase: 'phase_1' },
        { rotation_id: PAIR[1], phase: 'phase_2' },
      ],
    },
  ],
  rotations: ROTATION_SUMMARIES,
  sources: [CLIMATE_FRESH, SOIL_EXAMPLE],
}

const DECISION_MISSING = {
  reason: 'NOT_AVAILABLE',
  detail: 'the decision layer failed (ValueError), so no decision is given; the failure is in the server log',
}

const ENVELOPE_NO_DECISION = {
  decision: null,
  decision_missing: DECISION_MISSING,
  scenarios: [],
  rotations: ROTATION_SUMMARIES,
  sources: [CLIMATE_FRESH, SOIL_EXAMPLE],
}

const ERROR_INTERNAL = {
  error: { code: 'INTERNAL_ERROR', message: 'PLACEHOLDER message', details: [] },
}

// --- the request ---------------------------------------------------------------------

describe('the rotations of D128 the interface holds', () => {
  it('holds the two definitions of the file, for example-field-1, unchanged', () => {
    expect(demoRotationsD128.map((rotation) => rotation.rotation_id)).toEqual([
      'soybean-winter-fallow',
      'wheat-soybean-maize',
    ])
    for (const rotation of demoRotationsD128) {
      expect(rotation.case_id).toBe('example-case')
      expect(rotation.field_id).toBe('example-field-1')
      expect(rotation.label).toContain('D128')
      expect(rotation.label).toContain('D72')
      expect(rotation.label).toContain('scenario dates, not observed harvests')
    }
    expect(demoRotationsD128.map((rotation) => rotation.document)).toEqual(rawDemoRotations)
  })

  it('are the rotations the section sends; the contract example of the seam is not one', () => {
    expect(HELD_ROTATIONS).toBe(demoRotationsD128)
    expect(HELD_ROTATIONS.map((rotation) => rotation.rotation_id)).not.toContain(
      rotationDefinition.rotation_id,
    )
  })

  it('rejects a file that is not a list of rotation definitions', () => {
    expect(() => parseDemoRotations({})).toThrow(/not-a-list/)
    expect(() => parseDemoRotations([{ contract: 'decision_output' }])).toThrow(
      /contract-not-rotation-definition/,
    )
  })
})

describe('decisionRequestOf: the pair the interface sends', () => {
  it('sends the site and the two rotations of D128 for example-field-1, unchanged and in order', () => {
    const request = decisionRequestOf(exampleCase.case_id, FIELD, HELD_ROTATIONS)
    expect(request).not.toBeNull()
    expect(request!.site.case_id).toBe(exampleCase.case_id)
    expect(request!.site.field_id).toBe(FIELD.field_id)
    expect(request!.rotations).toEqual(rawDemoRotations)
    expect(request!.rotations[0]).toBe(demoRotationsD128[0].document)
  })

  it('sends nothing for another field, and says the pair is not declared there', () => {
    expect(decisionRequestOf(exampleCase.case_id, OTHER_FIELD, HELD_ROTATIONS)).toBeNull()
    expect(notCalledReason(true, 0)).toEqual({ reason: 'NOT_DECLARED' })
    expect(notCalledReason(false, 0)).toBeNull()
  })

  it('sends nothing with one rotation of the field, nor with more than one pair', () => {
    expect(decisionRequestOf(exampleCase.case_id, FIELD, [rotationDefinition])).toBeNull()
    expect(notCalledReason(true, 1)).toEqual({ reason: 'NOT_DECLARED' })
    expect(
      decisionRequestOf(exampleCase.case_id, FIELD, [...HELD_ROTATIONS, rotationDefinition]),
    ).toBeNull()
    expect(notCalledReason(true, 3)).toBeNull()
  })
})

// --- the route, mocked ------------------------------------------------------------------

describe('the decision route, mocked', () => {
  const request = decisionRequestOf(exampleCase.case_id, FIELD, TWO_HELD)!

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs the request to /api/decisions/run and resolves the 200 envelope', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      calls.push({ url: String(input), init: init ?? {} })
      return Promise.resolve(jsonResponse(200, ENVELOPE_DECISION))
    })

    const body = await runDecision(request)

    expect(body).toEqual(ENVELOPE_DECISION)
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(runDecisionUrl())
    expect(calls[0].url).toContain('/api/decisions/run')
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual(request)
  })

  it('shows the document of the route, not the example (a document is shown)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_DECISION)))

    const answer = parseRunDecision(await runDecision(request))
    expect(answer.kind).toBe('decision')
    const html = renderState({ phase: 'answered', answer })
    const text = visibleText(html)

    expect(html).toContain('data-source="route"')
    expect(html).not.toContain('data-source="example"')
    // the climate source answered fresh data: the seam's live-data label
    expect(countTestIds(html, 'decision-live')).toBe(1)
    expect(html).toContain(strings['seam.with_real_data'])
    // the document is not marked example data: no banner
    expect(countTestIds(html, 'decision-example-banner')).toBe(0)
    // the pair, its state and reason verbatim, its coverage
    expect(text).toContain('soybean-winter-fallow against wheat-soybean-maize')
    expect(text).toContain('Not robust across scenarios')
    expect(text).toContain('not robust across the admitted scenarios')
    expect(text).toContain('46 of 112 cells compared')
    expect(countTestIds(html, 'decision-state-preferred')).toBe(0)
    // the state of the decision: missing with its reason, and its reasons
    expect(text).toContain(
      missingPatternText(strings['decision.state'], {
        reason: 'NOT_AVAILABLE',
        detail: 'no decision says how the one state relates to the states of its pairs',
      }),
    )
    expect(countTestIds(html, 'decision-overall-reason')).toBe(2)
    expect(text).toContain('in scenario phase_1+phase_2 the pair is Not separated: uncertainty missing')
    // nothing of the bundled example
    expect(html).not.toContain('PLACEHOLDER_scenario_one')
    expect(html).not.toContain('OPEN: exact wording by the science reviewers')
  })

  it('shows the counts of soil carbon trend by carbon model and computation, never merged (D169)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_DECISION)))

    const html = renderState({
      phase: 'answered',
      answer: parseRunDecision(await runDecision(request)),
    })
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-counts-group')).toBe(3)
    expect(text).toContain('soil_loss phase_1+phase_1 By point value')
    expect(text).toContain('soil_carbon_trend phase_1+phase_1 amg end_minus_start')
    expect(text).toContain('soil_carbon_trend phase_1+phase_1 rothc end_minus_start')
    // each model's count as it travels: one strict improvement for AMG, one
    // deterioration for RothC; never one count of both
    expect(text).toContain('amg end_minus_start By point value')
    expect(countText(text, 'strict_improvement 1')).toBe(1)
    expect(countText(text, 'deterioration 1')).toBe(1)
    expect(text).toContain('not_separated 7')
  })

  it('shows every absence of the route with its reason, never a zero (C3.1)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_DECISION)))

    const html = renderState({
      phase: 'answered',
      answer: parseRunDecision(await runDecision(request)),
    })
    const text = visibleText(html)

    // the counts by point value are not given: missing with the reason, three times
    expect(countTestIds(html, 'decision-counts-by-point')).toBe(0)
    expect(countTestIds(html, 'decision-counts-by-point-missing')).toBe(3)
    expect(countText(text, 'By point value: not declared for this case')).toBe(3)
    expect(text).not.toContain('Better 0')
    // the years within the limit are not given: missing with the reason, no "0 to 0"
    expect(countTestIds(html, 'decision-years-missing')).toBe(2)
    expect(countTestIds(html, 'decision-years-sentence')).toBe(0)
    expect(text).toContain(
      'soybean-winter-fallow soil_loss soybean-winter-fallow soil_loss: not declared for this case',
    )
    expect(text).not.toContain('Years within the limit')
  })

  it('names the preferred rotation of a robust preference as data (D74)', () => {
    const document = structuredClone(ROUTE_DOCUMENT) as Record<string, unknown>
    const state = (document.pair_states as Record<string, unknown>[])[0]
    state.value = 'Robust preference'
    state.reason = null
    state.preferred_rotation_id = 'wheat-soybean-maize'

    const html = renderState({
      phase: 'answered',
      answer: parseRunDecision({ ...ENVELOPE_DECISION, decision: document }),
    })

    expect(countTestIds(html, 'decision-state-preferred')).toBe(1)
    expect(visibleText(html)).toContain('Robust preference wheat-soybean-maize')
  })

  it('marks a document of the route that is example data with the example banner', async () => {
    const document = { ...ROUTE_DOCUMENT, example_data: true }
    const example = { ...ENVELOPE_DECISION, decision: document, sources: [SOIL_EXAMPLE] }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, example)))

    const html = renderState({
      phase: 'answered',
      answer: parseRunDecision(await runDecision(request)),
    })

    expect(html).toContain('data-source="route"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(countTestIds(html, 'decision-live')).toBe(0)
  })

  it('shows the reason of a null decision, then the bundled example under its banner', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, ENVELOPE_NO_DECISION)))

    const answer = parseRunDecision(await runDecision(request))
    expect(answer).toEqual({ kind: 'missing', missing: DECISION_MISSING })
    const html = renderState({ phase: 'answered', answer })
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-route-missing')).toBe(1)
    expect(text).toContain(
      'Decision: module not built or not enabled (the decision layer failed (ValueError), so no decision is given; the failure is in the server log)',
    )
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(text).toContain('example-rotation-1 against example-rotation-2')
    expect(countTestIds(html, 'decision-live')).toBe(0)
  })

  it('falls back to the bundled example, labelled, after the message and code of an error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, ERROR_INTERNAL)))

    const error = await caughtError(runDecision(request))
    expect(error).toBeInstanceOf(ApiError)
    const html = renderState({ phase: 'error', error })
    const text = visibleText(html)

    expect(countTestIds(html, 'decision-route-error')).toBe(1)
    expect(text).toContain(strings['api.INTERNAL_ERROR'])
    expect(text).toContain('code: INTERNAL_ERROR')
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(text).toContain('Not separated: uncertainty missing')
  })

  it('falls back to the bundled example, labelled, when the connection fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )

    const error = await caughtError(runDecision(request))
    expect((error as ApiError).code).toBe('UNEXPECTED')
    const html = renderState({ phase: 'error', error })

    expect(visibleText(html)).toContain(strings['api.UNEXPECTED'])
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
  })

  it('treats an envelope that breaks its own rule as an error, never as a decision', () => {
    expect(() =>
      parseRunDecision({ ...ENVELOPE_NO_DECISION, decision_missing: null }),
    ).toThrow(/no-decision-without-missing-part/)
    expect(() =>
      parseRunDecision({ ...ENVELOPE_DECISION, decision_missing: DECISION_MISSING }),
    ).toThrow(/decision-and-missing-part/)
    const html = renderState({ phase: 'error', error: new Error('invalid-decision-envelope') })
    expect(visibleText(html)).toContain(strings['common.error'])
    expect(html).toContain('data-source="example"')
  })

  it('shows the loading line and no document while the route answers', () => {
    const html = renderState({ phase: 'pending' })
    expect(countTestIds(html, 'decision-loading')).toBe(1)
    expect(html).toContain(strings['common.loading'])
    expect(countTestIds(html, 'decision-document')).toBe(0)
  })

  it('says why no call is made for a field without a pair of rotations, then the example', () => {
    const html = renderState({ phase: 'not-called', missing: { reason: 'NOT_DECLARED' } })
    expect(countTestIds(html, 'decision-not-called')).toBe(1)
    expect(visibleText(html)).toContain('Rotation pairs: not declared for this case')
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
  })
})

// --- the state of the section ---------------------------------------------------------

describe('sectionStateOf', () => {
  const idle = { isPending: false, isError: false, error: null, data: undefined }
  const request = decisionRequestOf(exampleCase.case_id, FIELD, TWO_HELD)

  it('is not called without a request, with the reason given', () => {
    expect(sectionStateOf(null, { reason: 'NOT_DECLARED' }, idle)).toEqual({
      phase: 'not-called',
      missing: { reason: 'NOT_DECLARED' },
    })
  })

  it('follows the query once a request exists', () => {
    expect(sectionStateOf(request, null, { ...idle, isPending: true })).toEqual({ phase: 'pending' })
    const error = new ApiError('UNEXPECTED')
    expect(sectionStateOf(request, null, { ...idle, isError: true, error })).toEqual({
      phase: 'error',
      error,
    })
    const answer = parseRunDecision(ENVELOPE_NO_DECISION)
    expect(sectionStateOf(request, null, { ...idle, data: answer })).toEqual({
      phase: 'answered',
      answer,
    })
  })
})

// --- the container on the fields view ---------------------------------------------------

describe('DecisionSection on the fields view', () => {
  function renderSection(held?: readonly RotationDefinitionExample[]): string {
    return renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <DecisionSection held={held} />
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

  it('for example-field-1, with the rotations of D128: the call is on its way', () => {
    setSelectedFieldId(FIELD.field_id)

    const html = renderSection()

    expect(countTestIds(html, 'decision-loading')).toBe(1)
    expect(countTestIds(html, 'decision-document')).toBe(0)
    expect(countTestIds(html, 'decision-not-called')).toBe(0)
  })

  it('for another field: no call, the reason, the example under its banner', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    setSelectedFieldId(OTHER_FIELD.field_id)

    const html = renderSection()

    expect(visibleText(html)).toContain('Rotation pairs: not declared for this case')
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(countTestIds(html, 'decision-loading')).toBe(0)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('for example-field-1 with one rotation only: no call, the reason, the example', () => {
    setSelectedFieldId(FIELD.field_id)

    const html = renderSection([rotationDefinition])

    expect(visibleText(html)).toContain('Rotation pairs: not declared for this case')
    expect(html).toContain('data-source="example"')
    expect(countTestIds(html, 'decision-loading')).toBe(0)
  })
})

// --- the parser ---------------------------------------------------------------------------

describe('parseDecisionOutput', () => {
  /** A deep copy of the example, so one rule can be broken at a time. */
  function broken(mutate: (doc: Record<string, unknown>) => void): unknown {
    const copy = structuredClone(rawDecisionOutput) as unknown as Record<string, unknown>
    mutate(copy)
    return copy
  }

  it('accepts the example of the contract', () => {
    expect(decisionExample.example_data).toBe(true)
    expect(decisionExample.pair_states).toHaveLength(1)
    expect(decisionExample.pair_cell_counts).toHaveLength(3)
    expect(decisionExample.range_across_scenarios).toHaveLength(2)
    expect(decisionExample.state.value).toBe('OPEN: exact wording by the science reviewers')
  })

  it('accepts a document of the route: its explicit nulls are read as absent', () => {
    const document = parseDecisionOutput(ROUTE_DOCUMENT)
    expect(document.example_data).toBe(false)
    expect(document.state).toEqual({
      value: null,
      missing: ROUTE_DOCUMENT.state.missing,
      reasons: ROUTE_DOCUMENT.state.reasons,
    })
    const state = document.pair_states[0]
    expect(state.value).toBe('Not robust across scenarios')
    expect(state).not.toHaveProperty('reason_missing')
    expect(state).not.toHaveProperty('preferred_rotation_id')
    const carbon = document.pair_cell_counts.filter((c) => c.indicator === 'soil_carbon_trend')
    expect(carbon.map((c) => [c.carbon_model, c.computation])).toEqual([
      ['amg', 'end_minus_start'],
      ['rothc', 'end_minus_start'],
    ])
    expect(document.pair_cell_counts[0].carbon_model).toBeUndefined()
    expect(document.range_across_scenarios[0].minimum).toBeNull()
  })

  it('reads a missing detail written as null as absent', () => {
    const document = parseDecisionOutput({
      ...ROUTE_DOCUMENT,
      state: { ...ROUTE_DOCUMENT.state, missing: { reason: 'NOT_AVAILABLE', detail: null } },
    })
    expect(document.state).toEqual({
      value: null,
      missing: { reason: 'NOT_AVAILABLE' },
      reasons: ROUTE_DOCUMENT.state.reasons,
    })
  })

  it('rejects a state that holds a value and a missing part together (C3.1)', () => {
    const doc = broken((copy) => {
      const state = (copy.pair_states as Record<string, unknown>[])[0]
      state.missing = { reason: 'NOT_AVAILABLE' }
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/value-and-missing-part/)
  })

  it('rejects a state that is not evaluated without a missing part (D85)', () => {
    const doc = broken((copy) => {
      const state = (copy.pair_states as Record<string, unknown>[])[0]
      state.value = null
      delete state.missing
      delete state.reason
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/value-null-without-missing-part/)
  })

  it('rejects a preferred rotation that is not one of the pair (D74)', () => {
    const doc = broken((copy) => {
      const state = (copy.pair_states as Record<string, unknown>[])[0]
      state.preferred_rotation_id = 'example-rotation-3'
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/preferred-rotation-not-of-the-pair/)
  })

  it('rejects a pair that is not evaluated and names a preferred rotation (D85)', () => {
    const doc = broken((copy) => {
      const state = (copy.pair_states as Record<string, unknown>[])[0]
      state.value = null
      state.missing = { reason: 'NOT_COMPUTABLE' }
      delete state.reason
      state.preferred_rotation_id = 'example-rotation-1'
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/not-evaluated-with-a-preferred-rotation/)
  })

  it('rejects a count by point value that holds counts and a missing part together (C3.1)', () => {
    const doc = broken((copy) => {
      const count = (copy.pair_cell_counts as Record<string, unknown>[])[1]
      count.by_sign_of_point_value = { better: 0, worse: 0, equal: 0, missing_side: 0 }
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/by-sign-of-point-value-and-missing-part/)
  })

  it('rejects a count by point value written as null without its missing part, never zeros (C3.1)', () => {
    const doc = broken((copy) => {
      const count = (copy.pair_cell_counts as Record<string, unknown>[])[1]
      count.by_sign_of_point_value_missing = null
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/by-sign-of-point-value-null-without-missing-part/)
  })

  it('rejects a coverage whose compared cells exceed the cells of the pair (D91)', () => {
    const doc = broken((copy) => {
      const state = (copy.pair_states as Record<string, unknown>[])[0]
      ;(state.coverage as Record<string, unknown>).cells_compared = 6
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/coverage-compared-above-the-pair/)
  })

  it('rejects a range across scenarios given without its scenario of the minimum (D96)', () => {
    const doc = broken((copy) => {
      const range = (copy.range_across_scenarios as Record<string, unknown>[])[0]
      delete range.scenario_of_the_minimum
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/scenario-of-the-minimum-empty/)
  })

  it('rejects a state of the decision written as null without its missing part (C3.1)', () => {
    const doc = broken((copy) => {
      copy.state = { value: null, indicators_not_resolved: [], reasons: [] }
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/state:value-null-without-missing-part/)
  })

  it('rejects an example mark that is not a boolean', () => {
    const doc = broken((copy) => {
      copy.example_data = 'yes'
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/example-data-not-a-boolean/)
  })

  it('rejects an empty or missing field_id', () => {
    const doc = broken((copy) => {
      copy.field_id = ''
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/field-id-empty/)
  })

  it('rejects invalid measure_first entries and out-of-order ranks (D4)', () => {
    const zeroRank = broken((copy) => {
      copy.measure_first = [{ rank: 0, what: 'input', why: 'reason' }]
    })
    expect(() => parseDecisionOutput(zeroRank)).toThrow(/rank-not-positive-integer/)

    const emptyWhy = broken((copy) => {
      copy.measure_first = [{ rank: 1, what: 'input', why: '' }]
    })
    expect(() => parseDecisionOutput(emptyWhy)).toThrow(/why-empty/)

    const outOfOrder = broken((copy) => {
      copy.measure_first = [
        { rank: 2, what: 'a', why: 'b' },
        { rank: 1, what: 'c', why: 'd' },
      ]
    })
    expect(() => parseDecisionOutput(outOfOrder)).toThrow(/not-in-rank-order/)
  })

  it('rejects invalid counts_by_year and paired_differences entries', () => {
    const withinAbove = broken((copy) => {
      const count = (copy.counts_by_year as Record<string, unknown>[])[0]
      count.years_within_limits = 5
    })
    expect(() => parseDecisionOutput(withinAbove)).toThrow(/within-greater-than-evaluated/)

    const carbonCount = broken((copy) => {
      const count = (copy.counts_by_year as Record<string, unknown>[])[0]
      count.indicator = 'soil_carbon_trend'
    })
    expect(() => parseDecisionOutput(carbonCount)).toThrow(/soil-carbon-trend-has-no-count-by-year/)

    const missingAgYear = broken((copy) => {
      const diff = (copy.paired_differences as Record<string, unknown>[])[0]
      delete diff.ag_year
    })
    expect(() => parseDecisionOutput(missingAgYear)).toThrow(/ag-year-not-an-integer/)

    const rotationWithAgYear = broken((copy) => {
      const diff = (copy.paired_differences as Record<string, unknown>[])[2]
      diff.ag_year = 2001
    })
    expect(() => parseDecisionOutput(rotationWithAgYear)).toThrow(/rotation-basis-with-ag-year/)
  })

  it('leaves the document passed in unchanged', () => {
    const copy = structuredClone(ROUTE_DOCUMENT)
    parseDecisionOutput(copy)
    expect(copy).toEqual(ROUTE_DOCUMENT)
  })
})
