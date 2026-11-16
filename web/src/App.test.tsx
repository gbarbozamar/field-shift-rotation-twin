import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToString } from 'react-dom/server'
import App from './App'
import { exampleCase } from './identity/exampleCase'
import { formatString } from './lib/format'
import { setSelectedFieldId } from './identity/selection'
import { strings } from './strings'

// leaflet needs a real browser window (importing it in node throws
// "window is not defined"), so the map component is stubbed for this
// routing check, as in the fields screen render test.
vi.mock('./map/FieldsMap', () => ({
  default: () => <div data-testid="fields-map" />,
}))

/** Render the app shell at the given URL hash (stubbed, node has no window). */
function renderAppAtHash(hash: string): string {
  vi.stubGlobal('window', { location: { hash } })
  // The query client comes from the shell in main.tsx; this standalone
  // render provides one, as the app does, for the screens that use it.
  return renderToString(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App routing', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    setSelectedFieldId(null)
  })

  it('renders the entry screen, with its small map, at the root route', () => {
    const html = renderAppAtHash('')
    expect(html).toContain(strings['entry.title'])
    expect(html).toContain(
      formatString(strings['entry.fields_count'], { n: exampleCase.fields.length }),
    )
    expect(html).toContain('href="#/saved"')
    expect(html).toContain(strings['saved.open_case'])
    expect(html).toContain('data-testid="fields-map"')
  })

  it('the sidebar links every section and marks the one shown', () => {
    for (const [hash, current] of [
      ['', '#/'],
      ['#/fields', '#/fields'],
      ['#/board', '#/board'],
      ['#/plant', '#/plant'],
      ['#/print', '#/print'],
      ['#/saved', '#/saved'],
    ] as const) {
      const links = renderAppAtHash(hash).split('data-testid="nav-link"').slice(1).map((part) => part.split('>')[0])
      expect(links.map((link) => link.match(/href="([^"]*)"/)![1])).toEqual(['#/', '#/fields', '#/board', '#/plant', '#/print', '#/saved'])
      const marked = links.filter((link) => link.includes('aria-current="page"'))
      expect(marked.length, hash).toBe(1)
      expect(marked[0], hash).toContain(`href="${current}"`)
    }
  })

  it('renders the board at #/board', () => {
    const html = renderAppAtHash('#/board')
    expect(html).toContain(strings['board.title'])
    expect(html).toContain(strings['map.select_hint'])
  })

  it('renders the fields screen, with the map above the list, at #/fields', () => {
    const html = renderAppAtHash('#/fields')
    expect(html).toContain('data-testid="fields-map"')
    expect(html).toContain(strings['map.select_hint'])
    expect(html).toContain(strings['identity.banner_title'])
    expect(html).toContain('href="#/print"')
    expect(html).toContain(strings['print.open_link'])
  })

  it('renders the printable field sheet at #/print for the selected field and without selection', () => {
    const unselectedHtml = renderAppAtHash('#/print')
    expect(unselectedHtml).toContain(strings['print.title'])
    expect(unselectedHtml).toContain(strings['print.select_hint'])
    expect(unselectedHtml).toContain('href="#/fields"')
    expect(unselectedHtml).toContain(strings['print.back_to_fields'])

    const selected = exampleCase.fields[0]
    setSelectedFieldId(selected.field_id)
    const selectedHtml = renderAppAtHash('#/print')
    expect(selectedHtml).toContain(strings['print.title'])
    expect(selectedHtml).toContain(selected.name)
    expect(selectedHtml).toContain(selected.field_id)
    expect(selectedHtml).toContain(exampleCase.label)
    expect(selectedHtml).toContain(strings['example.banner'])
    expect(selectedHtml).toContain('print:hidden')
  })

  it('renders the offline saved-case viewer at #/saved', () => {
    const html = renderAppAtHash('#/saved')
    expect(html).toContain(strings['saved.title'])
    expect(html).toContain('2026-11-15T12:02Z')
    expect(html).toContain(strings['saved.carbon_heading'])
  })
})
