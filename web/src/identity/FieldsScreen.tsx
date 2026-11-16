import { exampleCase } from './exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from './selection'
import FieldsMap from '../map/FieldsMap'
import { fieldAreaHa } from '../map/geometry'
import { formatString } from '../lib/format'
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
 * Multi-field identity screen on example data. In order: the stage rail; the
 * example-data banner; the map of the fields and the field list below it,
 * which share the selected-field state through the selection module, so a
 * click on either selects the field on both. For a selected field, after the
 * list: the CP1 seam that runs the example rotation through the platform
 * route (issue #119; it renders nothing for any other field), the site sheet,
 * the example rotation as the display-only ribbon when it belongs to that
 * field, the two clocks and the result cards of the results example, and the
 * decision section (issues #241, #354): the document the decision route
 * returns for the two rotations the interface holds for that field, or the
 * bundled decision output example under its banner, after the reason it is
 * shown.
 */
export default function FieldsScreen() {
  const selectedFieldId = useSelectedFieldId()
  const selectedField =
    exampleCase.fields.find((field) => field.field_id === selectedFieldId) ?? null

  return (
    <section aria-labelledby="fields-screen-title">
      <h2 id="fields-screen-title" className="text-lg font-semibold">
        {strings['identity.title']}
      </h2>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-fs-muted">
          {strings['identity.case_label']}: {exampleCase.label}
        </p>
        <a
          href="#/print"
          data-testid="fields-print-link"
          className="inline-flex items-center rounded-lg border border-fs-border bg-fs-surface px-3 py-1.5 text-sm font-medium text-fs-primary transition hover:bg-fs-bg"
        >
          {strings['print.open_link']}
        </a>
      </div>

      <StageRail />

      {/* The workbench shell of issue #454: one source order, two columns
          from 1100px. The two wrappers below are plain block flow under
          1100px, so the small-screen stacking is exactly the order of this
          file; the grid variant places the first wrapper (the example-data
          banner, the map over the field list) in the flexible column and
          the second (the six inspector pieces, in their today order) in
          the fixed inspector column. The banner sits inside the map column
          at the developer's request (15 Nov 2026), so it spans the map's
          width, not the whole shell. Every component still mounts exactly
          once. */}
      <div className="min-[1100px]:grid min-[1100px]:grid-cols-[minmax(0,1fr)_520px] min-[1100px]:items-start min-[1100px]:gap-6">
        <div>
          {exampleCase.example_data && (
            <div
              role="note"
              aria-label={strings['identity.banner_title']}
              className="mt-4 rounded-lg border border-fs-warning bg-fs-warning-bg px-4 py-3"
            >
              <p className="text-sm font-semibold text-fs-warning">{strings['identity.banner_title']}</p>
              <p className="mt-1 text-sm text-fs-warning">{strings['identity.banner_text']}</p>
            </div>
          )}

          <div className="mt-6">
            <h3 className="text-base font-semibold">{strings['map.title']}</h3>
            <p className="mt-1 text-sm text-fs-muted">{strings['map.select_hint']}</p>
            <div className="mt-2 h-[60dvh] min-h-[24rem] max-h-[80dvh]">
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
                    isSelected ? 'border-fs-primary' : 'border-fs-border',
                    ...(isSelected
                      ? ['bg-fs-selection', 'ring-2', 'ring-fs-primary']
                      : ['bg-fs-surface', 'hover:border-fs-border', 'hover:bg-fs-bg']),
                  ].join(' ')}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-medium text-fs-text">{field.name}</span>
                    {isSelected && (
                      <span className="rounded bg-fs-primary px-2 py-0.5 text-xs font-semibold text-white">
                        {strings['identity.selected']}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-sm text-fs-muted">
                    {strings['identity.field_id_label']}: {field.field_id}
                  </span>
                  <span data-testid="field-area" className="block text-sm tabular-nums text-fs-muted">
                    {formatString(strings['field.area'], { ha: fieldAreaHa(field).toFixed(1) })}
                  </span>
                </button>
              </li>
            )
            })}
          </ul>

          {exampleCase.fields.length === 0 && (
            <p className="mt-6 text-sm text-fs-muted">{strings['identity.empty_list']}</p>
          )}
        </div>

        {/* The inspector column of issue #454, corrected after the
            developer's screen check of 15 Nov 2026: a grid item is as
            wide as its widest unbreakable content unless it may shrink
            (min-w-0 on the item and on every child, long words may
            break), and the six stacked pieces are far taller than the
            map-and-list column, so from 1100px the inspector stays
            beside the map as a panel with its own scroll (sticky, at
            most the viewport minus the main padding), instead of
            leaving the left column as empty space on the way down.
            Under 1100px this wrapper is plain block flow, unchanged. */}
        <div className="min-w-0 [&>*]:min-w-0 [&_*]:break-words min-[1100px]:sticky min-[1100px]:top-8 min-[1100px]:max-h-[calc(100dvh-4rem)] min-[1100px]:w-[520px] min-[1100px]:overflow-y-auto min-[1100px]:overscroll-contain">
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
        </div>
      </div>

      <p aria-live="polite" className="sr-only">
        {selectedField ? `${strings['identity.selected']}: ${selectedField.name}` : ''}
      </p>
    </section>
  )
}
