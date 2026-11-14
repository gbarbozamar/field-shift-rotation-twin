import { useHashRoute } from './lib/useHashRoute'
import { API_URL } from './lib/api'

export default function App() {
  const route = useHashRoute()

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 px-6 py-4">
        <h1 className="text-xl font-semibold">Field Shift Rotation Twin</h1>
        <p className="text-sm text-slate-500">Web interface — skeleton shell</p>
      </header>
      <main className="px-6 py-8">
        <p>Placeholder shell page. Screens will be added by later units.</p>
        <p className="mt-2 text-sm text-slate-500">Current hash route: {route}</p>
        <p className="text-sm text-slate-500">Backend: {API_URL}</p>
      </main>
    </div>
  )
}
