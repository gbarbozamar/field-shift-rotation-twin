import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { renderToString } from 'react-dom/server'
import rawSavedCase from '../data/saved_case.json'
import { missingPatternText } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import SavedCaseScreen, {
  bundledSavedCase,
  loadSavedCaseText,
  parseSavedCase,
  SavedCaseView,
} from './SavedCaseScreen'

const thisDir = dirname(fileURLToPath(import.meta.url))
const placeholderSavedCasePath = resolve(
  thisDir,
  '../../../contracts/saved_case/examples/PLACEHOLDER_saved_case.json',
)

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

function cloneRawSavedCase(): Record<string, unknown> {
  return JSON.parse(JSON.stringify(rawSavedCase)) as Record<string, unknown>
}

describe('SavedCaseScreen offline viewer', () => {
  it('renders bundled saved_case.json with saved_on UTC timestamp, example banner, field identity, results summary, carbon balances, and decision output', () => {
    const html = renderToString(<SavedCaseScreen />)
    const text = visibleText(html)

    expect(html).toContain('data-testid="saved-file-input"')
    expect(html).toContain('type="file"')
    expect(html).toContain('accept=".json"')

    expect(text).toContain(strings['saved.title'])
    expect(text).toContain(formatString(strings['saved.case_id'], { id: bundledSavedCase.case_id }))
    expect(text).toContain(
      formatString(strings['saved.field_id'], { id: bundledSavedCase.field_id }),
    )
    expect(text).toContain(
      formatString(strings['saved.saved_on'], { timestamp: '2026-11-15T12:02Z' }),
    )
    expect(text).toContain(strings['example.banner'])
    expect(text).toContain(strings['saved.source_bundled'])

    expect(text).toContain('Example case')
    expect(text).toContain('North field')
    expect(text).toContain('Long field by the creek')
    expect(text).toContain('Small triangle field')
    expect(text).toContain(strings['saved.run_field_badge'])

    const expectedRows = bundledSavedCase.results_table!.rows
    const expectedPresent = expectedRows.filter((row) => row.item.value !== null).length
    const expectedMissing = expectedRows.length - expectedPresent
    expect(expectedRows.length).toBe(54)
    expect(expectedPresent).toBe(42)
    expect(expectedMissing).toBe(12)

    expect(text).toContain(formatString(strings['saved.results_rows_count'], { n: 54 }))
    expect(text).toContain(
      formatString(strings['saved.results_availability'], { present: 42, missing: 12 }),
    )
    expect(text).toContain(
      formatString(strings['saved.results_rotations'], { rotations: 'A, B, C' }),
    )
    expect(text).toContain(
      formatString(strings['saved.results_scenarios'], { scenarios: 's1, s2, s3' }),
    )

    // Missing rows in results_table use missingPatternText, never 0
    expect(text).toContain(strings['missing.NO_COVERAGE'])
    expect(text).toContain(strings['missing.NOT_AVAILABLE'])

    // Carbon balances show all 6 items with explicit model + variant and typed missing reasons
    const carbonItems = html.split('data-testid="saved-carbon-item"').slice(1)
    expect(carbonItems.length).toBe(6)
    expect(text).toContain(formatString(strings['cards.model_label'], { model: 'amg' }))
    expect(text).toContain(formatString(strings['cards.model_label'], { model: 'rothc' }))
    expect(text).toContain(formatString(strings['saved.carbon_variant'], { variant: 'amg_a' }))
    expect(text).toContain(formatString(strings['saved.carbon_variant'], { variant: 'rothc_26_3' }))
    for (const item of bundledSavedCase.carbon_balances) {
      const itemLabel = formatString(strings['saved.carbon_item_label'], {
        rotation: item.rotation_id,
        model: item.carbon_model,
        variant: item.variant,
      })
      expect(text).toContain(missingPatternText(itemLabel, item.carbon_balance_missing!))
    }

    // Decision output state missing + 3 pairs with coverage
    const decisionState = bundledSavedCase.decision_output!.state
    expect(decisionState.value).toBeNull()
    if (decisionState.value === null) {
      expect(text).toContain(missingPatternText(strings['decision.state'], decisionState.missing))
    }
    expect(text).toContain(formatString(strings['decision.pair_of'], { first: 'A', second: 'B' }))
    expect(text).toContain(formatString(strings['decision.pair_of'], { first: 'A', second: 'C' }))
    expect(text).toContain(formatString(strings['decision.pair_of'], { first: 'B', second: 'C' }))
    expect(text).toContain('Not robust across scenarios')
    expect(text).toContain(formatString(strings['decision.coverage'], { k: 12, n: 18 }))
    expect(text).toContain(formatString(strings['decision.coverage'], { k: 15, n: 18 }))
  })

  it('hides the example banner when example_data is false and renders a present carbon balance', () => {
    const placeholderText = readFileSync(placeholderSavedCasePath, 'utf8')
    const placeholder = JSON.parse(placeholderText) as Record<string, unknown>
    placeholder.example_data = false
    ;(placeholder.field_identity as Record<string, unknown>).example_data = false
    const balances = placeholder.carbon_balances as Array<Record<string, unknown>>
    ;((balances[0].carbon_balance as Record<string, unknown>)).example_data = false
    ;(placeholder.decision_output as Record<string, unknown>).example_data = false

    const parsed = parseSavedCase(placeholder)
    const html = renderToString(<SavedCaseView savedCase={parsed} sourceName="exported.json" />)
    const text = visibleText(html)

    expect(html).not.toContain('data-testid="saved-example-banner"')
    expect(text).not.toContain(strings['example.banner'])
    expect(text).toContain(formatString(strings['saved.source_file'], { name: 'exported.json' }))
    expect(html).toContain('data-testid="saved-reset-button"')
    expect(html).toContain('data-testid="saved-carbon-present"')
    expect(text).toContain(
      formatString(strings['saved.carbon_horizon'], { start: '2001-01', end: '2002-12' }),
    )
    expect(text).toContain('11.1')
  })

  it('renders typed Missing reasons for absent top-level parts and empty carbon_balances without inventing zeros', () => {
    const raw = cloneRawSavedCase()
    raw.field_identity = null
    raw.field_identity_missing = {
      reason: 'NOT_DECLARED',
      detail: 'no field identity exported',
    }
    raw.results_table = null
    raw.results_table_missing = {
      reason: 'NOT_AVAILABLE',
      detail: 'no engine run recorded',
    }
    raw.carbon_balances = []
    raw.decision_output = null
    raw.decision_output_missing = {
      reason: 'MISSING_INPUT',
      detail: 'results_table',
    }

    const parsed = parseSavedCase(raw)
    const html = renderToString(<SavedCaseView savedCase={parsed} />)
    const text = visibleText(html)

    expect(text).toContain(
      missingPatternText(strings['saved.field_identity_heading'], parsed.field_identity_missing!),
    )
    expect(text).toContain(
      missingPatternText(strings['saved.results_heading'], parsed.results_table_missing!),
    )
    expect(text).toContain(strings['saved.carbon_empty'])
    expect(text).toContain(
      missingPatternText(strings['decision.title'], parsed.decision_output_missing!),
    )
  })

  it('renders clean error alerts for invalid JSON and invalid SavedCase documents', () => {
    const jsonErrHtml = renderToString(
      <SavedCaseView savedCase={bundledSavedCase} errorKey="saved.error_invalid_json" />,
    )
    expect(visibleText(jsonErrHtml)).toContain(strings['saved.error_invalid_json'])
    expect(jsonErrHtml).toContain('role="alert"')

    const schemaErrHtml = renderToString(
      <SavedCaseView savedCase={bundledSavedCase} errorKey="saved.error_invalid_case" />,
    )
    expect(visibleText(schemaErrHtml)).toContain(strings['saved.error_invalid_case'])
    expect(schemaErrHtml).toContain('role="alert"')
  })
})

describe('parseSavedCase and loadSavedCaseText strict validation', () => {
  it('accepts bundled saved_case.json and contract PLACEHOLDER_saved_case.json', () => {
    const bundledResult = loadSavedCaseText(JSON.stringify(rawSavedCase))
    expect(bundledResult.ok).toBe(true)

    const placeholderText = readFileSync(placeholderSavedCasePath, 'utf8')
    const placeholderResult = loadSavedCaseText(placeholderText)
    expect(placeholderResult.ok).toBe(true)
  })

  it('returns saved.error_invalid_json on malformed JSON text', () => {
    const result = loadSavedCaseText('{not valid json')
    expect(result).toEqual({ ok: false, errorKey: 'saved.error_invalid_json' })
  })

  it('rejects missing required fields and wrong contract tag', () => {
    const wrongContract = cloneRawSavedCase()
    wrongContract.contract = 'field_identity'
    expect(loadSavedCaseText(JSON.stringify(wrongContract))).toEqual({
      ok: false,
      errorKey: 'saved.error_invalid_case',
    })

    const missingKey = cloneRawSavedCase()
    delete missingKey.results_table
    expect(() => parseSavedCase(missingKey)).toThrow()
  })

  it('enforces YYYY-MM-DDTHH:MMZ UTC minute timestamp format on saved_on', () => {
    for (const bad of [
      '2026-11-15',
      '2026-11-15T12:02:00Z',
      '2026-11-15T09:02-03:00',
      '2026-02-30T12:02Z',
      '2026-11-15T24:00Z',
      null,
    ]) {
      const mutated = cloneRawSavedCase()
      mutated.saved_on = bad
      expect(() => parseSavedCase(mutated)).toThrow()
    }
  })

  it('enforces C3.1 part-or-missing exclusivity and MISSING_INPUT detail', () => {
    const nullWithoutMissing = cloneRawSavedCase()
    nullWithoutMissing.field_identity = null
    nullWithoutMissing.field_identity_missing = null
    expect(() => parseSavedCase(nullWithoutMissing)).toThrow()

    const bothPresent = cloneRawSavedCase()
    bothPresent.decision_output_missing = { reason: 'NOT_AVAILABLE' }
    expect(() => parseSavedCase(bothPresent)).toThrow()

    const missingInputNoDetail = cloneRawSavedCase()
    missingInputNoDetail.results_table = null
    missingInputNoDetail.results_table_missing = { reason: 'MISSING_INPUT' }
    expect(() => parseSavedCase(missingInputNoDetail)).toThrow()
  })

  it('enforces carbon balance completeness, uniqueness, and example_data propagation', () => {
    const incompleteCarbon = cloneRawSavedCase()
    incompleteCarbon.carbon_balances = (
      incompleteCarbon.carbon_balances as Array<Record<string, unknown>>
    ).slice(0, 5)
    expect(() => parseSavedCase(incompleteCarbon)).toThrow()

    const duplicateCarbon = cloneRawSavedCase()
    const list = duplicateCarbon.carbon_balances as Array<Record<string, unknown>>
    list[1] = { ...list[0] }
    expect(() => parseSavedCase(duplicateCarbon)).toThrow()

    const falseExampleFlag = cloneRawSavedCase()
    falseExampleFlag.example_data = false
    expect(() => parseSavedCase(falseExampleFlag)).toThrow()
  })
})
