import { useCallback, useRef, useState } from 'react'
import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'
import { formatString } from './lib/format'
import { strings } from './strings'
import EntryScreen from './entry/EntryScreen'
import FieldsScreen from './identity/FieldsScreen'
import PlantScreen from './plant/PlantScreen'
import BoardScreen from './board/BoardScreen'
import PrintSheetScreen from './print/PrintSheetScreen'
import SavedCaseScreen from './saved/SavedCaseScreen'
import Sidebar from './shell/Sidebar'
import { IconMenu } from './shell/icons'
import { navItemOf } from './shell/nav'

/**
 * The application shell (PROPOSED, l3/erp-shell): the sidebar with the
 * sections on the left, a compact top bar over the content naming the
 * section shown, and the content on the field background. The entry screen
 * opens the case at "/"; the fields screen (map above the list) is at
 * "/fields"; the rotation board at "/board"; the full report at "/plant";
 * the printable field sheet at "/print"; the saved case at "/saved". Other
 * routes keep the placeholder page.
 */
export default function App() {
  const route = useHashRoute()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement | null>(null)
  const current = navItemOf(route)

  const closeMenu = useCallback(() => {
    setMenuOpen(false)
    menuButtonRef.current?.focus()
  }, [])

  return (
    <div className="min-h-dvh bg-fs-bg text-fs-text md:flex print:block print:bg-white">
      <Sidebar
        route={route}
        open={menuOpen}
        onClose={closeMenu}
        title={<h1 className="font-fs-heading text-sm font-extrabold leading-tight">{strings['app.title']}</h1>}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex min-h-14 items-center gap-3 border-b border-fs-border bg-fs-surface/95 px-4 py-2 backdrop-blur sm:px-6 print:hidden">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label={strings['shell.menu_open']}
            aria-expanded={menuOpen}
            aria-controls="app-sidebar"
            className="-ml-1 grid h-10 w-10 shrink-0 place-items-center rounded-md text-fs-text transition hover:bg-fs-faint md:hidden"
          >
            <IconMenu className="h-5 w-5" />
          </button>
          <div className="min-w-0 flex-1">
            {current !== null && (
              <p className="truncate font-fs-heading text-base font-semibold leading-tight">{strings[current.label]}</p>
            )}
            <p className="hidden truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-fs-muted sm:block">
              {strings['app.subtitle']}
            </p>
          </div>
        </header>

        <main className="fs-field-bg flex-1 px-4 py-6 sm:px-6 lg:px-8 print:bg-none print:p-0">
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
          ) : route === '/saved' ? (
            <SavedCaseScreen />
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
    </div>
  )
}
