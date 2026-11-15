import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import DecisionSection from './DecisionSection'
import { decisionExample, parseDecisionOutput, samePair } from './decisionData'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/**
 * Acceptance test of the decision section (issue #241). The section is a
 * pure function of the accepted decision-output example, so its whole
 * behaviour is its static markup, rendered with the pure server renderer of
 * react-dom. Every expected text below is the supplied wording of
 * strings.ts filled with the values of the accepted contract example,
 * written out in full.
 *
 * The acceptance cases of the unit brief:
 * (a) one block per rotation pair of the example, named by its two
 *     rotations through decision.pair_of;
 * (b) the state of a pair renders verbatim from the data, with its reason;
 * (c) the two counts render under their own headings, apart, never summed;
 * (d) the coverage and the years-within summary render from the data;
 * (e) the example banner is visible;
 * (f) nothing the example does not carry is rendered — no invented field.
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

const PAIRS = decisionExample.pair_states

describe('DecisionSection', () => {
  // -- the section, the pairs heading and the example banner (e) -------------------

  it('renders the section title and the rotation-pairs heading', () => {
    const html = renderToString(<DecisionSection />)
    expect(html).toContain(strings['decision.title'])
    expect(html).toContain(strings['decision.pairs'])
  })

  it('labels the example data with the example banner (e)', () => {
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-example-banner')).toBe(1)
    expect(html).toContain(strings['example.banner'])
  })

  // -- (a) one block per pair, named by its two rotations ---------------------------

  it('renders one block per pair the example carries, named by decision.pair_of (a)', () => {
    const html = renderToString(<DecisionSection />)
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
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-state-heading')).toBe(PAIRS.length)
    expect(countTestIds(html, 'decision-state-value')).toBe(PAIRS.length)
    expect(html).toContain(strings['decision.state'])
    expect(html).toContain('Not separated: uncertainty missing')
  })

  it('renders the reason of the state verbatim from the data (b)', () => {
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-state-reason')).toBe(1)
    expect(html).toContain('a difference without its range')
  })

  it('renders the coverage of each pair from the data (d)', () => {
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-coverage')).toBe(PAIRS.length)
    expect(html).toContain('2 of 5 cells compared')
  })

  // -- (c) the two counts apart, under their headings, never summed ------------------

  it('renders one counts group per counted cell of the pair, labelled by its identifiers (c)', () => {
    const html = renderToString(<DecisionSection />)
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
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-counts-by-point-heading')).toBe(3)
    expect(countTestIds(html, 'decision-counts-by-range-heading')).toBe(3)
    expect(html).toContain(strings['decision.counts_by_point'])
    expect(html).toContain(strings['decision.counts_by_range'])
  })

  it('renders the counts by point value under the approved labels, with the numbers of the example (c)', () => {
    const html = renderToString(<DecisionSection />)
    // Only soil_loss has the tolerance of "equal"; its four counts render.
    expect(countTestIds(html, 'decision-counts-by-point')).toBe(1)
    const text = visibleText(html)
    expect(text).toContain('Better 1')
    expect(text).toContain('Worse 0')
    expect(text).toContain('Equal 0')
    expect(text).toContain('Missing side 1')
  })

  it('renders the counts by range under the identifiers of the contract, with the numbers of the example (c)', () => {
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-counts-by-range')).toBe(3)
    const text = visibleText(html)
    expect(text).toContain('strict_improvement 0')
    expect(text).toContain('deterioration 0')
    expect(text).toContain('not_separated 1')
  })

  it('renders a count without the tolerance of equal as missing with its reason, never zeros (c)', () => {
    const html = renderToString(<DecisionSection />)
    expect(countTestIds(html, 'decision-counts-by-point-missing')).toBe(2)
    // The full missing pattern of the example, in its apostrophe-free parts
    // (the server renderer escapes the apostrophes of the detail as entities).
    expect(countText(html, 'By point value: not declared for this case')).toBe(2)
    expect(countText(html, 'is set for this indicator (D87)')).toBe(2)
  })

  it('never sums the counts: every count row shows the number of the data, and no total (c)', () => {
    const html = renderToString(<DecisionSection />)
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
    const html = renderToString(<DecisionSection />)
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

  // -- (f) no invented field -----------------------------------------------------------

  it('renders nothing for the fields the brief does not name: no limits, no paired differences, no tolerances, no counts by year, no overall state, no measurement priority (f)', () => {
    const html = renderToString(<DecisionSection />)
    // The limit value and its unit (limits).
    expect(html).not.toContain('t ha-1 yr-1')
    expect(html).not.toContain('the user declared the limit without a range')
    // The paired differences, their cells and their method.
    expect(html).not.toContain('end_minus_start')
    expect(html).not.toContain('-14')
    expect(html).not.toContain('paired-difference method')
    // The tolerance of soil_loss.
    expect(html).not.toContain('the designer of the case set the tolerance without a range')
    // The counts by year and their rows not evaluated.
    expect(html).not.toContain('years_evaluated')
    expect(html).not.toContain('the example series ends before this agricultural year does')
    // The state of the whole decision and the measurement priority.
    expect(html).not.toContain('OPEN: exact wording by the science reviewers')
    expect(html).not.toContain('residue cover at sowing')
    expect(html).not.toContain('illustrative: moves the soil-loss difference')
  })
})

describe('parseDecisionOutput', () => {
  /** A deep copy of the example, so one rule can be broken at a time. */
  function broken(mutate: (doc: Record<string, unknown>) => void): unknown {
    const doc = parseDecisionOutput(decisionExample) as unknown as Record<string, unknown>
    const copy = structuredClone(doc)
    mutate(copy)
    return copy
  }

  it('accepts the example of the contract', () => {
    expect(decisionExample.pair_states).toHaveLength(1)
    expect(decisionExample.pair_cell_counts).toHaveLength(3)
    expect(decisionExample.range_across_scenarios).toHaveLength(2)
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
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/value-null-without-missing-part/)
  })

  it('rejects a count by point value that holds counts and a missing part together (C3.1)', () => {
    const doc = broken((copy) => {
      const count = (copy.pair_cell_counts as Record<string, unknown>[])[1]
      count.by_sign_of_point_value = { better: 0, worse: 0, equal: 0, missing_side: 0 }
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/by-sign-of-point-value-and-missing-part/)
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

  it('rejects data that is not marked example data', () => {
    const doc = broken((copy) => {
      copy.example_data = false
    })
    expect(() => parseDecisionOutput(doc)).toThrow(/example-data-not-true/)
  })
})
