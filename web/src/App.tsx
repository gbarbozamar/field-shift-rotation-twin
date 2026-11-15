import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'
import { formatString } from './lib/format'
import { strings } from './strings'
import EntryScreen from './entry/EntryScreen'
import FieldsScreen from './identity/FieldsScreen'
import PlantScreen from './plant/PlantScreen'

export default function App() {
  const route = useHashRoute()
  // The entry screen opens the case as the default view at "/"; the fields
  // screen (map above the list) follows at "/fields"; the plant screen
  // is at "/plant" (S-019, PROPOSED). Other routes keep the placeholder page.

  return (
    <div className="min-h-screen bg-fs-bg text-fs-text">
      <header className="border-b border-slate-200 px-6 py-4">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-xl font-semibold">{strings['app.title']}</h1>
          <p className="text-sm text-slate-500">{strings['app.subtitle']}</p>
        </div>
      </header>
      <main className="px-6 py-8">
        {route === '/' ? (
          <EntryScreen />
        ) : route === '/fields' ? (
          <FieldsScreen />
        ) : route === '/plant' ? (
          <PlantScreen />
        ) : (
          <>
            <p>{strings['home.shell']}</p>
            <p className="mt-2 text-sm text-slate-500">
              {formatString(strings['home.route'], { route })}
            </p>
            <p className="text-sm text-slate-500">
              {formatString(strings['home.backend'], { api: API_URL })}
            </p>
          </>
        )}
      </main>
    </div>
  )
}
