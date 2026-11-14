import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import EntryScreen, { openFieldOnFieldsScreen } from './EntryScreen'
import { exampleCase } from '../identity/exampleCase'
import { getSelectedFieldId, setSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/** Text of the rendered markup with every tag and React marker stripped. */
function visibleText(html: string): string {
  return html
    .replace(/<!--.*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

describe('EntryScreen', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens the case: title, case label and every field name of the example case', () => {
    const html = renderToString(<EntryScreen />)
    expect(html).toContain(strings['entry.title'])
    expect(html).toContain(exampleCase.label)
    for (const field of exampleCase.fields) {
      expect(html).toContain(field.name)
      expect(html).toContain(field.field_id)
    }
  })

  it('shows the example-data banner', () => {
    const html = renderToString(<EntryScreen />)
    expect(html).toContain(strings['example.banner'])
  })

  it('shows the fields count of the example case', () => {
    const html = renderToString(<EntryScreen />)
    expect(html).toContain(
      formatString(strings['entry.fields_count'], { n: exampleCase.fields.length }),
    )
  })

  it('renders its visible wording from the strings file, with and without a selection', () => {
    const fieldsCount = formatString(strings['entry.fields_count'], {
      n: exampleCase.fields.length,
    })
    const plain = visibleText(renderToString(<EntryScreen />))
    for (const text of [strings['entry.title'], fieldsCount, strings['example.banner']]) {
      expect(plain).toContain(text)
    }

    setSelectedFieldId(exampleCase.fields[0].field_id)
    const withSelection = visibleText(renderToString(<EntryScreen />))
    for (const text of [
      strings['entry.title'],
      fieldsCount,
      strings['example.banner'],
      strings['entry.open_field'],
      strings['identity.selected'],
      strings['identity.field_id_label'],
      strings['identity.title'],
    ]) {
      expect(withSelection).toContain(text)
    }
  })

  it('marks the field selected through the shared store as the pressed one', () => {
    const selected = exampleCase.fields[1]
    setSelectedFieldId(selected.field_id)
    const html = renderToString(<EntryScreen />)
    const pressed = html
      .split('<button')
      .filter((chunk) => chunk.includes('aria-pressed="true"'))
    expect(pressed.length).toBe(1)
    expect(pressed[0]).toContain(selected.name)
  })

  it('offers the open action on the selected field only, inside its list item', () => {
    const html = renderToString(<EntryScreen />)
    expect(html).not.toContain(strings['entry.open_field'])

    const selected = exampleCase.fields[2]
    setSelectedFieldId(selected.field_id)
    const withSelection = renderToString(<EntryScreen />)
    const items = withSelection.split('<li').slice(1)
    const withOpenAction = items.filter((item) => item.includes(strings['entry.open_field']))
    expect(withOpenAction.length).toBe(1)
    expect(withOpenAction[0]).toContain(selected.name)
  })

  it('the open action selects the field in the shared store and routes to the fields screen', () => {
    vi.stubGlobal('window', { location: { hash: '' } })
    const selected = exampleCase.fields[1]
    openFieldOnFieldsScreen(selected.field_id)
    expect(getSelectedFieldId()).toBe(selected.field_id)
    expect(window.location.hash).toBe('#/fields')
  })

  it('links to the fields screen for the no-selection path', () => {
    const html = renderToString(<EntryScreen />)
    expect(html).toContain('href="#/fields"')
    expect(html).toContain(strings['identity.title'])
  })
})
