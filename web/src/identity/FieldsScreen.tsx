import { useState } from 'react'
import { exampleCase } from './exampleCase'
import { FIELDS_SCREEN_TEXT as T } from './literals'

/**
 * Multi-field identity screen on example data: a list of the fields of the
 * example case (no map yet), the example-data banner on every render, and a
 * selected-field state driven by clicking a field.
 */
export default function FieldsScreen() {
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null)
  const selectedField =
    exampleCase.fields.find((field) => field.field_id === selectedFieldId) ?? null

  return (
    <section aria-labelledby="fields-screen-title" className="max-w-2xl">
      <h2 id="fields-screen-title" className="text-lg font-semibold">
        {T.title}
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        {T.caseLabelPrefix}: {exampleCase.label}
      </p>

      {exampleCase.example_data && (
        <div
          role="note"
          aria-label={T.bannerTitle}
          className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
        >
          <p className="text-sm font-semibold text-amber-900">{T.bannerTitle}</p>
          <p className="mt-1 text-sm text-amber-800">{T.bannerText}</p>
        </div>
      )}

      <ul className="mt-6 space-y-3">
        {exampleCase.fields.map((field) => {
          const isSelected = field.field_id === selectedFieldId
          return (
            <li key={field.field_id}>
              <button
                type="button"
                aria-pressed={isSelected}
                onClick={() => setSelectedFieldId(field.field_id)}
                className={`w-full rounded-lg border px-4 py-3 text-left transition ${
                  isSelected
                    ? 'border-emerald-500 bg-emerald-50 ring-2 ring-emerald-500'
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="font-medium text-slate-900">{field.name}</span>
                  {isSelected && (
                    <span className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
                      {T.selectedLabel}
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-sm text-slate-500">
                  {T.fieldIdLabel}: {field.field_id}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {exampleCase.fields.length === 0 && (
        <p className="mt-6 text-sm text-slate-500">{T.emptyList}</p>
      )}


      <p aria-live="polite" className="sr-only">
        {selectedField ? `${T.selectedLabel}: ${selectedField.name}` : ''}
      </p>
    </section>
  )
}
