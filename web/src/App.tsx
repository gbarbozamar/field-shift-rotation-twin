import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'
import { formatString } from './lib/format'
import { strings } from './strings'

export default function App() {
  const route = useHashRoute()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 px-6 py-4">
        <h1 className="text-xl font-semibold">{strings['app.title']}</h1>
        <p className="text-sm text-slate-500">{strings['app.subtitle']}</p>
      </header>
      <main className="px-6 py-8">
        <p>{strings['home.shell']}</p>
        <p className="mt-2 text-sm text-slate-500">
          {formatString(strings['home.route'], { route })}
        </p>
        <p className="text-sm text-slate-500">
          {formatString(strings['home.backend'], { api: API_URL })}
        </p>
      </main>
    </div>
  )
}
