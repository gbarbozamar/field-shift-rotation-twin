import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/**
 * Continue from the entry screen to the fields screen: the field becomes the
 * shared selection (the map and the list below read the same store) and the
 * hash route moves to "#/fields".
 */
export function openFieldOnFieldsScreen(fieldId: string): void {
  setSelectedFieldId(fieldId)
  window.location.hash = '#/fields'
}

/**
 * Entry screen of the workflow on example data: a compact welcome that opens
 * the case — the case label, the fields count, the example-data banner and
 * the list of fields. Each field is selectable; the selected one offers the
 * open action, which carries the selection to the fields screen. A link to
 * the fields screen closes the screen for the no-selection path.
 */
export default function EntryScreen() {
  const selectedFieldId = useSelectedFieldId()

  return (
    <section aria-labelledby="entry-screen-title" className="mx-auto max-w-2xl">
      <h2 id="entry-screen-title" className="text-lg font-semibold">
        {strings['entry.title']}
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        {exampleCase.label} · {formatString(strings['entry.fields_count'], { n: exampleCase.fields.length })}
      </p>

      {exampleCase.example_data && (
        <p
          role="note"
          className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          {strings['example.banner']}
        </p>
      )}

      <ul className="mt-6 space-y-3">
        {exampleCase.fields.map((field) => {
          const isSelected = field.field_id === selectedFieldId
          return (
            <li key={field.field_id} className="space-y-2">
              <button
                type="button"
                aria-pressed={isSelected}
                onClick={() => setSelectedFieldId(field.field_id)}
                className={[
                  'w-full', 'rounded-lg', 'border', 'px-4', 'py-3', 'text-left', 'transition',
                  isSelected ? 'border-emerald-500' : 'border-slate-200',
                  ...(isSelected
                    ? ['bg-emerald-50', 'ring-2', 'ring-emerald-500']
                    : ['bg-white', 'hover:border-slate-300', 'hover:bg-slate-50']),
                ].join(' ')}
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="font-medium text-slate-900">{field.name}</span>
                  {isSelected && (
                    <span className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
                      {strings['identity.selected']}
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-sm text-slate-500">
                  {strings['identity.field_id_label']}: {field.field_id}
                </span>
              </button>
              {isSelected && (
                <button
                  type="button"
                  onClick={() => openFieldOnFieldsScreen(field.field_id)}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
                >
                  {strings['entry.open_field']}
                </button>
              )}
            </li>
          )
        })}
      </ul>

      {exampleCase.fields.length === 0 && (
        <p className="mt-6 text-sm text-slate-500">{strings['identity.empty_list']}</p>
      )}

      <nav className="mt-6 flex flex-wrap gap-4 text-sm">
        <a
          href="#/fields"
          className="font-medium text-emerald-700 underline transition hover:text-emerald-800"
        >
          {strings['identity.title']}
        </a>
        <a
          href="#/saved"
          className="font-medium text-emerald-700 underline transition hover:text-emerald-800"
        >
          {strings['saved.open_case']}
        </a>
      </nav>
    </section>
  )
}
