/**
 * Acceptance test of the value display.
 *
 * The fixture items below are the person-supplied cases of the unit brief.
 * Their numbers, unit strings, source, range, display name and detail are
 * placeholders, illustrative only, and are not changed here. Every expected
 * render is exact: it is the supplied fixture filled into the supplied
 * string of strings.ts, written out in full.
 *
 * The component is a pure function of its props, so its whole behaviour is
 * its static markup: it is rendered with the pure server renderer of
 * react-dom, part of the existing dependencies. No DOM environment and no
 * new dependency.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ValueDisplay } from './ValueDisplay'
import type { ProvenanceLabel, ReasonCode, UncertaintyRange, ValueItem } from './ValueDisplay'

// --- fixture items (person-supplied; PLACEHOLDER numbers, illustrative) ------

const FIXTURE_VALUE = 7.1
const FIXTURE_UNIT = 't ha-1 yr-1'
const FIXTURE_SOURCE = 'PLACEHOLDER_source'
const FIXTURE_RANGE: UncertaintyRange = { low: 5.9, high: 8.4, kind: 'PLACEHOLDER_kind' }
const FIXTURE_WHAT = 'Soil carbon trend'
const FIXTURE_DETAIL = 'critical period not defined'

// The unit of the soil-carbon trend as it travels in the conventions (C1.5).
// A missing value keeps its unit (C3.1), here as in the contract; the
// missing render itself shows only "{what}: {reason phrase}".
const FIXTURE_UNIT_OF_MISSING = 't C ha-1 yr-1'

const ALL_LABELS: ProvenanceLabel[] = ['DECLARED', 'OBSERVED', 'DERIVED', 'SIMULATED']

const ALL_REASON_CODES: ReasonCode[] = [
  'NOT_DECLARED',
  'SOURCE_UNAVAILABLE',
  'NO_COVERAGE',
  'MISSING_INPUT',
  'NOT_COMPUTABLE',
  'CONTROL_FAILED',
  'NOT_AVAILABLE',
  'NOT_APPLICABLE',
]

// --- expected renders (fixture values in the supplied strings, exact) --------

/** The label names of C4.1, capitalized as the strings file writes them. */
const EXPECTED_VALUE_LINE: Record<ProvenanceLabel, string> = {
  DECLARED: '7.1 t ha-1 yr-1 Declared',
  OBSERVED: '7.1 t ha-1 yr-1 Observed',
  DERIVED: '7.1 t ha-1 yr-1 Derived',
  SIMULATED: '7.1 t ha-1 yr-1 Simulated',
}

const EXPECTED_SOURCE_LINE = 'Source: PLACEHOLDER_source'
const EXPECTED_RANGE_LINE = '5.9 to 8.4 (PLACEHOLDER_kind)'

/** "{what}: {reason phrase}" with the reason phrases of the strings file. */
const EXPECTED_MISSING_LINE: Record<ReasonCode, string> = {
  NOT_DECLARED: 'Soil carbon trend: not declared for this case',
  SOURCE_UNAVAILABLE: 'Soil carbon trend: source unavailable',
  NO_COVERAGE: 'Soil carbon trend: no coverage for this place or period',
  MISSING_INPUT: 'Soil carbon trend: missing input: critical period not defined',
  NOT_COMPUTABLE: 'Soil carbon trend: not computable for this case',
  CONTROL_FAILED: 'Soil carbon trend: a control failed and the value is withheld',
  NOT_AVAILABLE: 'Soil carbon trend: module not built or not enabled',
  NOT_APPLICABLE: 'Soil carbon trend: not applicable',
}

// --- helpers -----------------------------------------------------------------

function markupOf(item: ValueItem): string {
  return renderToStaticMarkup(<ValueDisplay what={FIXTURE_WHAT} item={item} />)
}

/** The exact text of one line of the display, or null when it is not rendered. */
function lineText(markup: string, testid: string): string | null {
  const match = markup.match(new RegExp(`<p[^>]*data-testid="${testid}"[^>]*>([\\s\\S]*?)</p>`))
  if (match === null) return null
  return match[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

/** The whole visible text of the display, lines joined by one space. */
function visibleText(markup: string): string {
  return markup.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

// --- case 1: one value per provenance label -----------------------------------

describe('ValueDisplay: a value with unit, provenance label and source', () => {
  for (const label of ALL_LABELS) {
    it(`renders the ${label} label name of C4.1`, () => {
      const markup = markupOf({
        value: FIXTURE_VALUE,
        unit: FIXTURE_UNIT,
        provenance: label,
        source: FIXTURE_SOURCE,
      })
      expect(lineText(markup, 'value-line')).toBe(EXPECTED_VALUE_LINE[label])
      expect(lineText(markup, 'source-line')).toBe(EXPECTED_SOURCE_LINE)
      expect(visibleText(markup)).toBe(`${EXPECTED_VALUE_LINE[label]} ${EXPECTED_SOURCE_LINE}`)
    })
  }
})

// --- case 2: the uncertainty range ---------------------------------------------

describe('ValueDisplay: a value with its uncertainty range', () => {
  it('renders the range as {low} to {high} ({kind})', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DERIVED',
      source: FIXTURE_SOURCE,
      range: FIXTURE_RANGE,
    })
    expect(lineText(markup, 'value-line')).toBe(EXPECTED_VALUE_LINE.DERIVED)
    expect(lineText(markup, 'source-line')).toBe(EXPECTED_SOURCE_LINE)
    expect(lineText(markup, 'range-line')).toBe(EXPECTED_RANGE_LINE)
    expect(visibleText(markup)).toBe(
      `${EXPECTED_VALUE_LINE.DERIVED} ${EXPECTED_SOURCE_LINE} ${EXPECTED_RANGE_LINE}`,
    )
  })
})

// --- case 3: a value whose range is absent with a reason ------------------------

describe('ValueDisplay: a value whose range is absent with a reason', () => {
  it('renders the value without a range and invents no bounds', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DERIVED',
      source: FIXTURE_SOURCE,
      range_missing: { reason: 'NOT_AVAILABLE' },
    })
    expect(lineText(markup, 'value-line')).toBe(EXPECTED_VALUE_LINE.DERIVED)
    expect(lineText(markup, 'source-line')).toBe(EXPECTED_SOURCE_LINE)
    expect(lineText(markup, 'range-line')).toBe(null)
    // Nothing else is rendered: no bounds and no kind are invented for the
    // absent range.
    expect(visibleText(markup)).toBe(`${EXPECTED_VALUE_LINE.DERIVED} ${EXPECTED_SOURCE_LINE}`)
  })
})

// --- case 4: one missing item per reason code -----------------------------------

describe('ValueDisplay: a missing value names what is missing and why', () => {
  for (const code of ALL_REASON_CODES) {
    it(`renders ${code} with its reason phrase`, () => {
      const markup = markupOf({
        value: null,
        unit: FIXTURE_UNIT_OF_MISSING,
        missing:
          code === 'MISSING_INPUT' ? { reason: code, detail: FIXTURE_DETAIL } : { reason: code },
      })
      expect(lineText(markup, 'missing-line')).toBe(EXPECTED_MISSING_LINE[code])
      // The missing render is one line: no value, no zero, no blank.
      expect(visibleText(markup)).toBe(EXPECTED_MISSING_LINE[code])
    })
  }
})

// --- case 5: MISSING_INPUT names its input ---------------------------------------

describe('ValueDisplay: MISSING_INPUT names the missing input', () => {
  it('renders the detail of the missing input', () => {
    const markup = markupOf({
      value: null,
      unit: FIXTURE_UNIT_OF_MISSING,
      missing: { reason: 'MISSING_INPUT', detail: FIXTURE_DETAIL },
    })
    const line = lineText(markup, 'missing-line')
    expect(line).toBe(EXPECTED_MISSING_LINE.MISSING_INPUT)
    expect(line).toContain(FIXTURE_DETAIL)
    expect(lineText(markup, 'value-line')).toBe(null)
  })
})

// --- the assumption mark of a value without a source (C4.2, C4.5) ----------------

describe('ValueDisplay: a value marked as an assumption', () => {
  it('shows the assumption mark instead of a source line', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DECLARED',
      assumption: true,
    })
    expect(lineText(markup, 'assumption-line')).toBe('assumption')
    expect(lineText(markup, 'source-line')).toBe(null)
    expect(visibleText(markup)).toBe('7.1 t ha-1 yr-1 Declared assumption')
  })
})
