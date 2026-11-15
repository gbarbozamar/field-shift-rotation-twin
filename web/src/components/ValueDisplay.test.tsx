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
// A derivation trace of the length the engine writes: the provenance
// paragraph a value travels with once the seam is complete. Its render is
// the collapsed source line of case 4.
const FIXTURE_LONG_SOURCE =
  'PLACEHOLDER derivation: EP2 accumulated the water balance of the daily record of the example station over the agricultural year that starts in month 7, EP3 placed the FAO-56 stages from the catalogue stage lengths, and the value was summed over the months of the cycle'
const FIXTURE_RANGE: UncertaintyRange = { low: 5.9, high: 8.4, kind: 'PLACEHOLDER_kind' }
const FIXTURE_WHAT = 'Soil carbon trend'
const FIXTURE_DETAIL = 'critical period not defined'
const FIXTURE_NOT_APPLICABLE_DETAIL = 'cover crop is terminated, not harvested'

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
// The source line is a collapsed disclosure: the whole "Source: …" line in
// its summary, and the exact trace again as the disclosed paragraph.
const EXPECTED_SOURCE_TEXT = `${EXPECTED_SOURCE_LINE} ${FIXTURE_SOURCE}`
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
  const match = markup.match(
    new RegExp(`<(p|summary)[^>]*data-testid="${testid}"[^>]*>([\\s\\S]*?)</\\1>`),
  )
  if (match === null) return null
  return match[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
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
      expect(visibleText(markup)).toBe(`${EXPECTED_VALUE_LINE[label]} ${EXPECTED_SOURCE_TEXT}`)
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
      `${EXPECTED_VALUE_LINE.DERIVED} ${EXPECTED_SOURCE_TEXT} ${EXPECTED_RANGE_LINE}`,
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
    expect(visibleText(markup)).toBe(`${EXPECTED_VALUE_LINE.DERIVED} ${EXPECTED_SOURCE_TEXT}`)
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

// --- the detail of a missing part, for any reason code (display polish) ---------

describe('ValueDisplay: a missing part with a detail shows it for any reason code', () => {
  it('appends the NOT_APPLICABLE detail in parentheses, after the reason phrase', () => {
    const markup = markupOf({
      value: null,
      unit: FIXTURE_UNIT_OF_MISSING,
      missing: { reason: 'NOT_APPLICABLE', detail: FIXTURE_NOT_APPLICABLE_DETAIL },
    })
    expect(lineText(markup, 'missing-line')).toBe(
      `Soil carbon trend: not applicable (${FIXTURE_NOT_APPLICABLE_DETAIL})`,
    )
  })

  it('appends the detail of any other reason code the same way', () => {
    const markup = markupOf({
      value: null,
      unit: FIXTURE_UNIT_OF_MISSING,
      missing: { reason: 'NO_COVERAGE', detail: 'the example series ends before this year' },
    })
    expect(lineText(markup, 'missing-line')).toBe(
      'Soil carbon trend: no coverage for this place or period (the example series ends before this year)',
    )
  })

  it('renders no suffix when the missing part carries no detail', () => {
    const markup = markupOf({
      value: null,
      unit: FIXTURE_UNIT_OF_MISSING,
      missing: { reason: 'NOT_APPLICABLE' },
    })
    const line = lineText(markup, 'missing-line')
    expect(line).toBe(EXPECTED_MISSING_LINE.NOT_APPLICABLE)
    expect(line).not.toContain('(')
  })

  it('keeps MISSING_INPUT naming its detail inside the phrase, not twice in a suffix', () => {
    const markup = markupOf({
      value: null,
      unit: FIXTURE_UNIT_OF_MISSING,
      missing: { reason: 'MISSING_INPUT', detail: FIXTURE_DETAIL },
    })
    expect(visibleText(markup)).toBe(EXPECTED_MISSING_LINE.MISSING_INPUT)
  })
})

// --- the collapsed source line (display polish) ----------------------------------

describe('ValueDisplay: the source line collapses its trace', () => {
  it('renders the source as a closed disclosure clipped to one line', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DERIVED',
      source: FIXTURE_LONG_SOURCE,
    })
    const disclosure = markup.match(/<details[^>]*data-testid="source-details"[^>]*>/)?.[0]
    expect(disclosure).toBeDefined()
    expect(disclosure).not.toContain('open')
    // The clipped line is the whole source line, one line of text.
    expect(lineText(markup, 'source-line')).toBe(`Source: ${FIXTURE_LONG_SOURCE}`)
  })

  it('carries the exact trace unchanged inside the disclosure', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DERIVED',
      source: FIXTURE_LONG_SOURCE,
    })
    expect(lineText(markup, 'source-full')).toBe(FIXTURE_LONG_SOURCE)
    expect(markup).toContain(`>${FIXTURE_LONG_SOURCE}<`)
  })
})

// --- the display precision of a measured value (display polish) ------------------

describe('ValueDisplay: display precision of a measured value', () => {
  it('renders a long value rounded to three decimals, with the exact value in the title', () => {
    const exact = 2.3650713015276774
    const markup = markupOf({
      value: exact,
      unit: FIXTURE_UNIT,
      provenance: 'OBSERVED',
      source: FIXTURE_SOURCE,
    })
    expect(lineText(markup, 'value-line')).toBe(`2.365 ${FIXTURE_UNIT} Observed`)
    expect(markup).toContain(
      '<span data-testid="value-number" class="font-medium" title="2.3650713015276774">2.365</span>',
    )
  })

  it('renders a value that is exactly 2.1 as 2.1, without forced trailing zeros', () => {
    const markup = markupOf({
      value: 2.1,
      unit: FIXTURE_UNIT,
      provenance: 'DECLARED',
    })
    expect(markup).toContain(
      '<span data-testid="value-number" class="font-medium" title="2.1">2.1</span>',
    )
  })

  it('keeps every value it displays exact in its title attribute', () => {
    const markup = markupOf({
      value: FIXTURE_VALUE,
      unit: FIXTURE_UNIT,
      provenance: 'DECLARED',
      source: FIXTURE_SOURCE,
    })
    expect(markup).toContain(`title="${String(FIXTURE_VALUE)}"`)
  })
})
