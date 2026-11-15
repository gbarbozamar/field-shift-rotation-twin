import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'
import { formatString } from './lib/format'
import { strings } from './strings'
import EntryScreen from './entry/EntryScreen'
import FieldsScreen from './identity/FieldsScreen'
import PlantScreen from './plant/PlantScreen'
import BoardScreen from './board/BoardScreen'
import PrintSheetScreen from './print/PrintSheetScreen'

/**
 * The sections of the app, in the order of the work: the case, its fields,
 * the plan of a field, and the report with every detail line (PROPOSED,
 * l3/board; a navigation entry is the lane owner's decision).
 */
const NAV = [
  { route: '/', label: 'nav.case' },
  { route: '/fields', label: 'nav.fields' },
  { route: '/board', label: 'nav.board' },
  { route: '/plant', label: 'nav.report' },
] as const

export default function App() {
  const route = useHashRoute()
  // The entry screen opens the case as the default view at "/"; the fields
  // screen (map above the list) follows at "/fields"; the plant screen
  // is at "/plant" (S-019, PROPOSED); the rotation board is at "/board"
  // (l3/board, PROPOSED); the printable field sheet is at "/print"
  // (PROPOSED). Other routes keep the placeholder page.

  return (
    <div className="min-h-screen bg-fs-bg text-fs-text print:bg-white">
      <header className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-b border-fs-border bg-fs-surface px-6 py-3">
        <div>
          <h1 className="text-xl font-extrabold leading-tight">{strings['app.title']}</h1>
          <p className="text-sm text-fs-muted">{strings['app.subtitle']}</p>
        </div>
        <nav aria-label={strings['nav.label']} className="print:hidden">
          <ul className="flex flex-wrap gap-1">
            {NAV.map((item) => (
              <li key={item.route}>
                <a
                  data-testid="nav-link"
                  href={`#${item.route}`}
                  aria-current={route === item.route ? 'page' : undefined}
                  className="inline-flex min-h-10 items-center rounded-lg px-3 text-sm font-semibold text-fs-muted aria-[current=page]:bg-fs-text aria-[current=page]:text-fs-surface"
                >
                  {strings[item.label]}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="px-6 py-8">
        {route === '/' ? (
          <EntryScreen />
        ) : route === '/fields' ? (
          <FieldsScreen />
        ) : route === '/plant' ? (
          <PlantScreen />
        ) : route === '/board' ? (
          <BoardScreen />
        ) : route === '/print' ? (
          <PrintSheetScreen />
        ) : (
          <>
            <p>{strings['home.shell']}</p>
            <p className="mt-2 text-sm text-fs-muted">
              {formatString(strings['home.route'], { route })}
            </p>
            <p className="text-sm text-fs-muted">
              {formatString(strings['home.backend'], { api: API_URL })}
            </p>
          </>
        )}
      </main>
    </div>
  )
}
