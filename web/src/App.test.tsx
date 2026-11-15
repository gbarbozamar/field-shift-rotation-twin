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

  it('renders the entry screen, without the map, at the root route', () => {
    const html = renderAppAtHash('')
    expect(html).toContain(strings['entry.title'])
    expect(html).toContain(
      formatString(strings['entry.fields_count'], { n: exampleCase.fields.length }),
    )
    expect(html).not.toContain('data-testid="fields-map"')
  })

  it('renders the fields screen, with the map above the list, at #/fields', () => {
    const html = renderAppAtHash('#/fields')
    expect(html).toContain('data-testid="fields-map"')
    expect(html).toContain(strings['map.select_hint'])
    expect(html).toContain(strings['identity.banner_title'])
  })
})
