import { exampleCase } from './exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from './selection'
import FieldsMap from '../map/FieldsMap'
import SiteSheet from '../site/SiteSheet'
import { RotationRibbon } from '../rotation/RotationRibbon'
import { exampleRotation } from '../rotation/exampleRotation'
import ClocksScreen from '../clocks/ClocksScreen'
import ResultCards from '../results/ResultCards'
import DecisionSection from '../decision/DecisionSection'
import StageRail from '../rail/StageRail'
import RotationRun from '../seam/RotationRun'
import { strings } from '../strings'

/**
 * Multi-field identity screen on example data: the example-data banner on
 * every render, the map of the fields and the field list below it, the
 * site sheet of the selected field after the list, and the rotation of the
 * selected field as the display-only rotation ribbon when the example
 * rotation belongs to that field. The list, the map and the sheet share the
 * selected-field state through the selection module.
 * every render, the map of the fields and the field list below it, and the
 * site sheet of the selected field after the list. The list, the map and the
 * sheet share the selected-field state through the selection module, so a
 * click on either selects the field on all three.
 * two clocks of the results example after the list, under their own example
 * banner. The list and the map share the selected-field state through the
 * selection module, so a click on either selects the field on both.
 * every render, the map of the fields and the field list below it, and the
 * result cards of the results example after the list. The list and the map
 * share the selected-field state through the selection module, so a click on
 * either selects the field on both.
 * click on either selects the field on all three. After the list hangs the
 * CP1 seam: for the selected field that matches the example rotation's
 * field, the action that runs that rotation through the platform route
 * (issue #119); it decides itself whether it shows, and renders nothing for
 * every other field. The decision section follows the result cards for a
 * selected field (issues #241, #354): the document the decision route
 * returns for the two rotations the interface holds for that field, or the
 * bundled decision output example under its banner, after the reason it is
 * shown.
 */
export default function FieldsScreen() {
  const selectedFieldId = useSelectedFieldId()
  const selectedField =
    exampleCase.fields.find((field) => field.field_id === selectedFieldId) ?? null

  return (
    <section aria-labelledby="fields-screen-title" className="max-w-2xl">
      <h2 id="fields-screen-title" className="text-lg font-semibold">
        {strings['identity.title']}
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        {strings['identity.case_label']}: {exampleCase.label}
      </p>

      <StageRail />

      {exampleCase.example_data && (
        <div
          role="note"
          aria-label={strings['identity.banner_title']}
          className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
        >
          <p className="text-sm font-semibold text-amber-900">{strings['identity.banner_title']}</p>
          <p className="mt-1 text-sm text-amber-800">{strings['identity.banner_text']}</p>
        </div>
      )}

      <div className="mt-6">
        <h3 className="text-base font-semibold">{strings['map.title']}</h3>
        <p className="mt-1 text-sm text-slate-500">{strings['map.select_hint']}</p>
        <div className="mt-2">
          <FieldsMap />
        </div>
      </div>

      <ul className="mt-6 space-y-3">
        {exampleCase.fields.map((field) => {
          const isSelected = field.field_id === selectedFieldId
          return (
            <li key={field.field_id}>
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
            </li>
          )
        })}
      </ul>

      {exampleCase.fields.length === 0 && (
        <p className="mt-6 text-sm text-slate-500">{strings['identity.empty_list']}</p>
      )}

      <RotationRun />

      <SiteSheet />

      {selectedFieldId === exampleRotation.field_id && (
        <div className="mt-8">
          <RotationRibbon rotation={exampleRotation} />
        </div>
      )}
      {selectedFieldId !== null && <ClocksScreen />}

      {selectedFieldId !== null && <ResultCards />}

      {selectedFieldId !== null && <DecisionSection />}

      <p aria-live="polite" className="sr-only">
        {selectedField ? `${strings['identity.selected']}: ${selectedField.name}` : ''}
      </p>
    </section>
  )
}
