import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import FieldsScreen from './FieldsScreen'
import { exampleCase } from './exampleCase'
import { setSelectedFieldId } from './selection'
import { exampleRotation } from '../rotation/exampleRotation'
import { strings } from '../strings'

// leaflet needs a real browser window (importing it in node throws
// "window is not defined"), so the map component is stubbed for this
// render check. The map itself is compiled by the build, and its pure
// helpers are checked in map/geometry.test.ts.
vi.mock('../map/FieldsMap', () => ({
  default: () => <div data-testid="fields-map" />,
}))

describe('FieldsScreen', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
  })

  it('renders the map section texts from the strings file', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain(strings['map.title'])
    expect(html).toContain(strings['map.select_hint'])
  })

  it('renders the map component between the banner and the field list', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain('data-testid="fields-map"')
    expect(html.indexOf('data-testid="fields-map"')).toBeGreaterThan(
      html.indexOf(strings['identity.banner_title']),
    )
  })

  it('renders the example-data banner and every field of the example case', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain(strings['identity.banner_title'])
    expect(html).toContain(strings['identity.banner_text'])
    for (const field of exampleCase.fields) {
      expect(html).toContain(field.name)
      expect(html).toContain(field.field_id)
    }
  })

  it('marks the field selected through the shared store as the pressed one', () => {
    const selected = exampleCase.fields[1]
    setSelectedFieldId(selected.field_id)
    const html = renderToString(<FieldsScreen />)
    const pressed = html
      .split('<button')
      .filter((chunk) => chunk.includes('aria-pressed="true"'))
    expect(pressed.length).toBe(1)
    expect(pressed[0]).toContain(selected.name)
  })

  it('marks no field as pressed when nothing is selected', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).not.toContain('aria-pressed="true"')
  })

  it('shows the site sheet select hint when no field is selected', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain(strings['site.title'])
    expect(html).toContain(strings['site.select_hint'])
    expect(html).not.toContain(strings['example.banner'])
  })

  it('shows the site sheet of the selected field after the field list', () => {
    const selected = exampleCase.fields[0]
    setSelectedFieldId(selected.field_id)
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain(strings['site.title'])
    expect(html).toContain(strings['example.banner'])
    const lastField = exampleCase.fields[exampleCase.fields.length - 1]
    expect(html.indexOf(strings['site.title'])).toBeGreaterThan(html.indexOf(lastField.field_id))
  })

  it('shows the rotation ribbon below the field list for the field of the example rotation', () => {
    setSelectedFieldId(exampleRotation.field_id)
    const html = renderToString(<FieldsScreen />)
    expect(html).toContain(strings['ribbon.title'])
    expect(html.indexOf(strings['ribbon.title'])).toBeGreaterThan(
      html.lastIndexOf(exampleCase.fields[exampleCase.fields.length - 1].field_id),
    )
  })

  it('shows no rotation ribbon when the selected field has no rotation', () => {
    const withoutRotation = exampleCase.fields.find(
      (field) => field.field_id !== exampleRotation.field_id,
    )
    if (withoutRotation === undefined) throw new Error('fixture: a field without a rotation exists')
    setSelectedFieldId(withoutRotation.field_id)
    const html = renderToString(<FieldsScreen />)
    expect(html).not.toContain(strings['ribbon.title'])
  })

  it('shows no rotation ribbon when nothing is selected', () => {
    const html = renderToString(<FieldsScreen />)
    expect(html).not.toContain(strings['ribbon.title'])
  })
})
