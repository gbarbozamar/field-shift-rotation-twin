import type { ReactNode } from 'react'
import PlanSummary from '../board/PlanSummary'
import { missingPatternText, ValueDisplay } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { demoRotationsD128 } from '../decision/demoRotations'
import { exampleCase } from '../identity/exampleCase'
import type { ExampleField } from '../identity/exampleCase'
import { useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { exampleRotation, parseRotationDefinition } from '../rotation/exampleRotation'
import type {
  DatedPart,
  GrazingPart,
  ResiduePart,
  RotationComponent,
  RotationDefinition,
  TerminationPart,
} from '../rotation/exampleRotation'
import { MonthlySeriesBlock } from '../site/SiteSheet'
import { siteClimate, siteSoilSlope } from '../site/siteData'
import type { SiteClimate, SiteSoilSlope } from '../site/siteData'
import { strings } from '../strings'

/**
 * Printable field sheet (PROPOSED, Blueprint Block 4), mounted at #/print.
 *
 * Reads the currently selected field from the shared selection store together
 * with the case metadata, geometry summary, site notes (climate monthly series
 * and soil/slope values), and declared rotations for that field.
 *
 * Every value travels through the shared ValueDisplay or missingPatternText so
 * no missing value is ever fabricated or replaced with zero or a blank. When
 * example_data is true, the declared example-data disclosure is shown.
 *
 * Interactive navigation (#/fields back link) and the window.print() button
 * carry print:hidden so they stay off printed output. All user-visible
 * wording lives in strings.ts.
 */

export interface PrintableCaseData {
  example_data: boolean
  case_id: string
  label: string
  fields: ExampleField[]
}

export interface GeometrySummary {
  type: ExampleField['geometry']['type']
  vertexCount: number
  south: number
  west: number
  north: number
  east: number
  centerLat: number
  centerLng: number
}

export interface PrintSheetViewProps {
  selectedFieldId: string | null
  /** The user's plan for the field (the board's), shown after the field; none in a bare view. */
  plan?: ReactNode
  caseData?: PrintableCaseData
  climate?: SiteClimate
  soilSlope?: SiteSoilSlope
  rotations?: RotationDefinition[]
}

const ALL_DECLARED_ROTATIONS: RotationDefinition[] = (() => {
  const byId = new Map<string, RotationDefinition>()
  for (const rotation of [
    exampleRotation,
    ...demoRotationsD128.map((item) => parseRotationDefinition(item.document)),
  ]) {
    if (!byId.has(rotation.rotation_id)) {
      byId.set(rotation.rotation_id, rotation)
    }
  }
  return [...byId.values()]
})()

/**
 * Pure bounding-box and vertex summary from a field's declared GeoJSON ring.
 * Returns null when no usable finite ring is declared.
 */
export function summarizeGeometry(field: ExampleField): GeometrySummary | null {
  const ring = field.geometry.coordinates[0]
  if (ring === undefined || ring.length === 0) return null
  let south = Infinity
  let north = -Infinity
  let west = Infinity
  let east = -Infinity
  for (const position of ring) {
    const lng = position[0]
    const lat = position[1]
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null
    if (lat < south) south = lat
    if (lat > north) north = lat
    if (lng < west) west = lng
    if (lng > east) east = lng
  }
  return {
    type: field.geometry.type,
    vertexCount: ring.length,
    south,
    west,
    north,
    east,
    centerLat: (south + north) / 2,
    centerLng: (west + east) / 2,
  }
}

function MissingLine({ label, missing }: { label: string; missing: MissingPart }) {
  return (
    <p
      data-testid="print-missing-line"
      className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
    >
      {missingPatternText(label, missing)}
    </p>
  )
}

function DatedSummary({ label, part }: { label: string; part: DatedPart }) {
  if (part.missing) {
    return <MissingLine label={label} missing={part.missing} />
  }
  return (
    <div className="mt-1">
      <p className="text-sm">
        <span className="text-fs-muted">{label}:</span>{' '}
        <span className="font-medium">{part.date}</span>{' '}
        <span className="text-fs-muted">{strings[`provenance.${part.provenance}`]}</span>
      </p>
      <p className="text-xs text-fs-muted">
        {formatString(strings['value.source'], { source: part.source })}
      </p>
    </div>
  )
}

function ResidueSummary({ residue }: { residue: ResiduePart }) {
  if (typeof residue !== 'string') {
    return <MissingLine label={strings['ribbon.mgmt_residue']} missing={residue.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_residue']}:</span>{' '}
      <span className="font-medium">{residue}</span>
    </p>
  )
}

function GrazingSummary({ grazing }: { grazing: GrazingPart }) {
  if ('missing' in grazing) {
    return <MissingLine label={strings['ribbon.mgmt_grazing']} missing={grazing.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_grazing']}:</span>{' '}
      <span className="font-medium">{grazing.intensity}</span>
    </p>
  )
}

function TerminationSummary({ termination }: { termination: TerminationPart }) {
  if ('missing' in termination) {
    return <MissingLine label={strings['ribbon.mgmt_termination']} missing={termination.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_termination']}:</span>{' '}
      <span className="font-medium">{termination.date}</span>{' '}
      <span className="font-medium">{termination.method}</span>
    </p>
  )
}

function ComponentSummary({ component }: { component: RotationComponent }) {
  return (
    <li
      data-testid="print-rotation-component"
      className={['print-avoid-break', 'rounded-lg', 'border', 'border-fs-border', 'p-3'].join(' ')}
    >
      <h5 className="text-sm font-semibold">
        {formatString(strings['ribbon.component'], { position: component.position })}
      </h5>
      <p className="mt-1 text-sm">
        <span className="text-fs-muted">{strings['ribbon.crop']}:</span>{' '}
        <span className="font-medium">{component.crop_id}</span>
      </p>
      <p className="mt-1 text-sm">
        <span className="text-fs-muted">{strings['ribbon.purpose']}:</span>{' '}
        <span className="font-medium">{component.purpose}</span>
      </p>
      <DatedSummary label={strings['ribbon.sowing']} part={component.sowing} />
      <DatedSummary label={strings['ribbon.harvest']} part={component.harvest} />
      <div className={['mt-2', 'border-t', 'border-fs-faint', 'pt-2'].join(' ')}>
        <p className="text-xs font-semibold uppercase text-fs-muted">
          {strings['ribbon.management']}
        </p>
        <ResidueSummary residue={component.management.residue} />
        <GrazingSummary grazing={component.management.grazing} />
        <TerminationSummary termination={component.management.termination} />
      </div>
    </li>
  )
}

function RotationSummaryCard({ rotation }: { rotation: RotationDefinition }) {
  const orderedComponents = [...rotation.components].sort((a, b) => a.position - b.position)
  return (
    <article
      data-testid="print-rotation-card"
      className={[
        'print-avoid-break',
        'mt-3',
        'rounded-lg',
        'border',
        'border-fs-border',
        'bg-white',
        'p-4',
      ].join(' ')}
    >
      <h4 className="text-base font-semibold">
        {formatString(strings['ribbon.rotation_of'], { label: rotation.label })}
      </h4>
      <p className="mt-1 text-sm text-fs-muted">
        {strings['print.rotation_id_label']}: <span className="font-mono">{rotation.rotation_id}</span>
      </p>
      <p className="mt-1 text-sm text-fs-muted">
        {formatString(strings['ribbon.ag_year_start'], { month: rotation.ag_year_start.month })}
        {rotation.ag_year_start.provisional ? (
          <>
            {' '}
            {strings['ribbon.provisional']}
          </>
        ) : null}
      </p>
      <p className="mt-1 text-sm text-fs-muted">
        {rotation.repeats ? strings['ribbon.repeats'] : strings['ribbon.not_repeating']}
      </p>
      <ol className={['mt-3', 'grid', 'list-none', 'gap-3', 'sm:grid-cols-2'].join(' ')}>
        {orderedComponents.map((component) => (
          <ComponentSummary key={component.component_id} component={component} />
        ))}
      </ol>
    </article>
  )
}

/** Invoke the browser print dialog for the printable field sheet. */
export function triggerPrintSheet(): void {
  window.print()
}

/**
 * Pure presentational view of the printable field sheet, exported so tests
 * can verify all states (including non-example or missing-geometry inputs).
 */
export function PrintSheetView({
  selectedFieldId,
  caseData = exampleCase,
  climate = siteClimate,
  soilSlope = siteSoilSlope,
  rotations = ALL_DECLARED_ROTATIONS,
  plan = null,
}: PrintSheetViewProps) {
  const selectedField =
    caseData.fields.find((field) => field.field_id === selectedFieldId) ?? null
  const geometry = selectedField === null ? null : summarizeGeometry(selectedField)
  const fieldRotations =
    selectedField === null
      ? []
      : rotations.filter(
          (rotation) =>
            rotation.case_id === caseData.case_id &&
            rotation.field_id === selectedField.field_id,
        )
  const isExampleData =
    caseData.example_data || climate.example_data || soilSlope.example_data

  return (
    <section aria-labelledby="print-sheet-title" className="mx-auto max-w-4xl">
      <div
        data-testid="print-controls"
        className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden"
      >
        <a
          href="#/fields"
          data-testid="print-back-link"
          className={[
            'inline-flex',
            'items-center',
            'rounded-lg',
            'border',
            'border-fs-border',
            'bg-fs-surface',
            'px-4',
            'py-2',
            'text-sm',
            'font-medium',
            'text-fs-text',
            'transition',
            'hover:bg-fs-bg',
            'print:hidden',
          ].join(' ')}
        >
          {strings['print.back_to_fields']}
        </a>
        <button
          type="button"
          data-testid="print-button"
          disabled={selectedField === null}
          onClick={triggerPrintSheet}
          className={[
            'inline-flex',
            'items-center',
            'rounded-lg',
            'bg-fs-primary',
            'px-4',
            'py-2',
            'text-sm',
            'font-semibold',
            'text-white',
            'transition',
            'hover:opacity-90',
            'disabled:cursor-not-allowed',
            'disabled:opacity-50',
            'print:hidden',
          ].join(' ')}
        >
          {strings['print.action']}
        </button>
      </div>

      <article
        data-testid="print-summary-card"
        className={[
          'fs-card',
          'p-6',
          'sm:p-8',
          'print:border-0',
          'print:p-0',
          'print:shadow-none',
        ].join(' ')}
      >
        <h2 id="print-sheet-title" className="text-xl font-semibold">
          {strings['print.title']}
        </h2>

        {selectedField === null ? (
          <p data-testid="print-select-hint" className="mt-4 text-sm text-fs-muted">
            {strings['print.select_hint']}
          </p>
        ) : (
          <div className="mt-4 space-y-6">
            {isExampleData && (
              <div
                role="note"
                data-testid="print-example-banner"
                aria-label={strings['identity.banner_title']}
                className="rounded-lg border border-fs-warning bg-fs-warning-bg px-4 py-3"
              >
                <p className="text-sm font-semibold text-fs-warning">{strings['example.banner']}</p>
                {caseData.example_data && (
                  <p className="mt-1 text-sm text-fs-warning">{strings['identity.banner_text']}</p>
                )}
              </div>
            )}

            <section aria-labelledby="print-field-heading" className="print-avoid-break">
              <h3 id="print-field-heading" className="text-base font-semibold">
                {strings['print.field_section']}
              </h3>
              <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-fs-muted">{strings['print.field_name_label']}</dt>
                  <dd data-testid="print-field-name" className="font-medium">
                    {selectedField.name}
                  </dd>
                </div>
                <div>
                  <dt className="text-fs-muted">{strings['identity.field_id_label']}</dt>
                  <dd data-testid="print-field-id" className="font-mono font-medium">
                    {selectedField.field_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-fs-muted">{strings['identity.case_label']}</dt>
                  <dd data-testid="print-case-label" className="font-medium">
                    {caseData.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-fs-muted">{strings['print.case_id_label']}</dt>
                  <dd data-testid="print-case-id" className="font-mono font-medium">
                    {caseData.case_id}
                  </dd>
                </div>
              </dl>
            </section>

            {plan}
            <section
              aria-labelledby="print-geometry-heading"
              className="print-avoid-break border-t border-fs-border pt-4"
            >
              <h3 id="print-geometry-heading" className="text-base font-semibold">
                {strings['print.geometry_section']}
              </h3>
              {geometry === null ? (
                <p
                  data-testid="print-geometry-missing"
                  className="mt-2 text-sm italic text-fs-muted"
                >
                  {missingPatternText(strings['print.geometry'], { reason: 'NOT_DECLARED' })}
                </p>
              ) : (
                <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-fs-muted">{strings['print.geometry_type']}</dt>
                    <dd className="font-medium">
                      {`${geometry.type}, ${formatString(strings['print.geometry_vertices'], {
                        count: geometry.vertexCount,
                      })}`}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-fs-muted">{strings['print.geometry_center']}</dt>
                    <dd data-testid="print-geometry-center" className="font-mono font-medium">
                      {`${geometry.centerLat.toFixed(4)}, ${geometry.centerLng.toFixed(4)}`}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-fs-muted">{strings['print.geometry_bounds']}</dt>
                    <dd data-testid="print-geometry-bounds" className="font-mono font-medium">
                      {`${geometry.south.toFixed(4)}, ${geometry.west.toFixed(4)} – ${geometry.north.toFixed(4)}, ${geometry.east.toFixed(4)}`}
                    </dd>
                  </div>
                </dl>
              )}
            </section>

            <section
              aria-labelledby="print-site-heading"
              className="border-t border-fs-border pt-4"
            >
              <h3 id="print-site-heading" className="text-base font-semibold">
                {strings['print.site_section']}
              </h3>
              {(soilSlope.field_id !== selectedField.field_id ||
                climate.field_id !== selectedField.field_id) && (
                <p data-testid="print-site-scope-note" className="mt-2 text-sm text-fs-muted">
                  {formatString(strings['print.site_example_scope'], {
                    field_id: soilSlope.field_id,
                    selected_field_id: selectedField.field_id,
                  })}
                </p>
              )}
              <div className="mt-3 print-avoid-break">
                <h4 className="text-sm font-semibold">{strings['site.soil_section']}</h4>
                <div className="mt-2 space-y-2">
                  <ValueDisplay what={strings['site.slope_length']} item={soilSlope.slope_length} />
                  <ValueDisplay
                    what={strings['site.slope_steepness']}
                    item={soilSlope.slope_steepness}
                  />
                  {soilSlope.soil_properties.map((property) => (
                    <ValueDisplay
                      key={property.quantity}
                      what={property.quantity}
                      item={property}
                    />
                  ))}
                </div>
              </div>
              <div className="mt-4 print-avoid-break">
                <h4 className="text-sm font-semibold">{strings['site.climate_section']}</h4>
                {climate.monthly_series.map((series) => (
                  <MonthlySeriesBlock key={series.quantity} series={series} />
                ))}
              </div>
            </section>

            <section
              aria-labelledby="print-rotations-heading"
              className="border-t border-fs-border pt-4"
            >
              <h3 id="print-rotations-heading" className="text-base font-semibold">
                {strings['print.rotations_section']}
              </h3>
              {fieldRotations.length === 0 ? (
                <p
                  data-testid="print-rotations-missing"
                  className="mt-2 text-sm italic text-fs-muted"
                >
                  {missingPatternText(strings['print.rotations'], { reason: 'NOT_DECLARED' })}
                </p>
              ) : (
                <div>
                  {fieldRotations.map((rotation) => (
                    <RotationSummaryCard key={rotation.rotation_id} rotation={rotation} />
                  ))}
                </div>
              )}
            </section>

            <footer className="border-t border-fs-border pt-4 text-xs text-fs-muted">
              {strings['disclaimer.full']}
            </footer>
          </div>
        )}
      </article>
    </section>
  )
}

/** Route wrapper at #/print reading the shared selected field store. */
export default function PrintSheetScreen() {
  const selectedFieldId = useSelectedFieldId()
  return <PrintSheetView selectedFieldId={selectedFieldId} plan={<PlanSummary selectedFieldId={selectedFieldId} />} />
}
