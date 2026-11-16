import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import PrintSheetScreen, {
  PrintSheetView,
  summarizeGeometry,
  triggerPrintSheet,
} from './PrintSheetScreen'
import { missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import type { ExampleField } from '../identity/exampleCase'
import { setSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { exampleRotation } from '../rotation/exampleRotation'
import { siteClimate, siteSoilSlope } from '../site/siteData'
import { strings } from '../strings'

function visibleText(html: string): string {
  return html
    .replace(/<!--.*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function countTestIds(html: string, testid: string): number {
  return html.split(`data-testid="${testid}"`).length - 1
}

describe('PrintSheetScreen', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
  })

  afterEach(() => {
    setSelectedFieldId(null)
    vi.unstubAllGlobals()
  })

  it('shows the select hint and print:hidden controls when no field is selected', () => {
    const html = renderToString(<PrintSheetScreen />)
    expect(html).toContain(strings['print.title'])
    expect(html).toContain(strings['print.select_hint'])
    expect(html).toContain('href="#/fields"')
    expect(html).toContain(strings['print.back_to_fields'])
    expect(html).toContain(strings['print.action'])
    expect(html).toContain('print:hidden')
    expect(html).not.toContain('data-testid="print-example-banner"')
    expect(html).not.toContain('data-testid="print-field-name"')
    // The print button is disabled when no field is selected.
    const buttonAt = html.indexOf('data-testid="print-button"')
    expect(buttonAt).toBeGreaterThan(-1)
    const buttonStart = html.lastIndexOf('<button', buttonAt)
    const buttonTag = html.slice(buttonStart, html.indexOf('>', buttonAt))
    expect(buttonTag).toMatch(/\sdisabled(?:=|>)/)
    expect(buttonTag).toContain('print:hidden')
  })

  it('shows the select hint and invents nothing when the selected field id is unknown', () => {
    setSelectedFieldId('non-existent-field')
    const html = renderToString(<PrintSheetScreen />)
    expect(html).toContain(strings['print.select_hint'])
    expect(html).not.toContain('non-existent-field')
    expect(html).not.toContain('data-testid="print-field-name"')
  })

  it('renders the selected field identity, case label, example disclosure, and disclaimer', () => {
    const field = exampleCase.fields[0]
    setSelectedFieldId(field.field_id)
    const html = renderToString(<PrintSheetScreen />)
    expect(html).toContain(field.field_id)
    expect(html).toContain(field.name)
    expect(html).toContain(exampleCase.label)
    expect(html).toContain(exampleCase.case_id)
    expect(html).toContain('data-testid="print-example-banner"')
    expect(html).toContain(strings['example.banner'])
    expect(html).toContain(strings['identity.banner_text'])
    expect(html).toContain(strings['disclaimer.full'])
    // Back link and print button carry print:hidden; print button is enabled.
    const backAt = html.indexOf('data-testid="print-back-link"')
    const backStart = html.lastIndexOf('<a', backAt)
    const backTag = html.slice(backStart, html.indexOf('>', backAt))
    expect(backTag).toContain('href="#/fields"')
    expect(backTag).toContain('print:hidden')
    const buttonAt = html.indexOf('data-testid="print-button"')
    const buttonStart = html.lastIndexOf('<button', buttonAt)
    const buttonTag = html.slice(buttonStart, html.indexOf('>', buttonAt))
    expect(buttonTag).toContain('print:hidden')
    expect(buttonTag).not.toMatch(/\sdisabled(?:=|>)/)
  })

  it('renders geometry summary and site notes without fabricating missing values', () => {
    const field = exampleCase.fields[0]
    setSelectedFieldId(field.field_id)
    const html = renderToString(<PrintSheetScreen />)
    const text = visibleText(html)

    // Geometry summary for Field 1: 26 vertices, center -34.3481, -57.6927
    expect(html).toContain(strings['print.geometry_section'])
    expect(text).toContain('Polygon')
    expect(text).toContain(formatString(strings['print.geometry_vertices'], { count: 26 }))
    expect(text).toContain('-34.3481, -57.6927')
    expect(text).toContain('-34.3639, -57.7039 – -34.3322, -57.6815')

    // Site notes: scope note when site data field_id differs from selected field_id
    expect(text).toContain(
      formatString(strings['print.site_example_scope'], {
        field_id: siteSoilSlope.field_id,
        selected_field_id: field.field_id,
      }),
    )
    // Present values and missing soil property rendered via shared ValueDisplay
    expect(text).toContain('1 PLACEHOLDER_unit Observed')
    expect(text).toContain('2 PLACEHOLDER_unit Declared')
    expect(text).toContain(strings['assumption.mark'])
    expect(text).toContain('placeholder_soil_property_b: no coverage for this place or period')
    expect(text).not.toContain('placeholder_soil_property_b: 0')
    // Climate monthly series rendered
    expect(text).toContain('placeholder_monthly_quantity (PLACEHOLDER_unit)')
    expect(text).toContain('3 months')
  })

  it('renders all declared rotations for the rotation field and preserves missing patterns', () => {
    setSelectedFieldId(exampleRotation.field_id)
    const html = renderToString(<PrintSheetScreen />)
    const text = visibleText(html)

    // Illustrative rotation + the two D128 demo rotations on example-field-1
    expect(countTestIds(html, 'print-rotation-card')).toBe(3)
    expect(text).toContain(exampleRotation.label)
    expect(text).toContain(exampleRotation.rotation_id)
    expect(text).toContain('soybean-winter-fallow')
    expect(text).toContain('wheat-soybean-maize')

    // Missing harvest / grazing / termination patterns render with reason, never blank/zero
    expect(text).toContain(
      `${strings['ribbon.harvest']}: ${strings['missing.NOT_APPLICABLE']} (cover crop is terminated, not harvested)`,
    )
    expect(text).toContain(
      `${strings['ribbon.mgmt_grazing']}: ${strings['missing.NOT_DECLARED']}`,
    )
    expect(text).toContain(
      `${strings['ribbon.mgmt_termination']}: ${strings['missing.NOT_DECLARED']}`,
    )
  })

  it('renders the missing pattern when the selected field has no declared rotations', () => {
    const withoutRotation = exampleCase.fields.find(
      (field) => field.field_id !== exampleRotation.field_id,
    )
    if (withoutRotation === undefined) throw new Error('fixture: a field without rotations exists')
    setSelectedFieldId(withoutRotation.field_id)
    const html = renderToString(<PrintSheetScreen />)
    expect(countTestIds(html, 'print-rotation-card')).toBe(0)
    expect(html).toContain(
      missingPatternText(strings['print.rotations'], { reason: 'NOT_DECLARED' }),
    )
  })

  it('triggerPrintSheet delegates to window.print()', () => {
    const printSpy = vi.fn()
    vi.stubGlobal('window', { print: printSpy })
    triggerPrintSheet()
    expect(printSpy).toHaveBeenCalledTimes(1)
  })
})

describe('PrintSheetView and summarizeGeometry', () => {
  it('returns null and renders missing geometry pattern when ring is empty or non-finite', () => {
    const emptyField: ExampleField = {
      field_id: 'empty-geom',
      name: 'Empty ring field',
      geometry: { type: 'Polygon', coordinates: [[]] },
    }
    expect(summarizeGeometry(emptyField)).toBeNull()

    const badCoordField: ExampleField = {
      field_id: 'bad-coord',
      name: 'Non-finite field',
      geometry: { type: 'Polygon', coordinates: [[[Number.NaN, -33.0]]] },
    }
    expect(summarizeGeometry(badCoordField)).toBeNull()

    const html = renderToString(
      <PrintSheetView
        selectedFieldId={emptyField.field_id}
        caseData={{
          example_data: false,
          case_id: 'real-case',
          label: 'Real case',
          fields: [emptyField],
        }}
        climate={{ ...siteClimate, example_data: false as unknown as true, field_id: emptyField.field_id }}
        soilSlope={{ ...siteSoilSlope, example_data: false as unknown as true, field_id: emptyField.field_id }}
        rotations={[]}
      />,
    )
    expect(html).toContain(
      missingPatternText(strings['print.geometry'], { reason: 'NOT_DECLARED' }),
    )
    // When example_data is false everywhere, the example disclosure is omitted.
    expect(html).not.toContain('data-testid="print-example-banner"')
    // When site data field_id matches the selected field, the scope mismatch note is omitted.
    expect(html).not.toContain('data-testid="print-site-scope-note"')
  })
})
