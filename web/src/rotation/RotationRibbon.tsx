import { formatString } from '../lib/format'
import { missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import type {
  DatedPart,
  GrazingPart,
  ResiduePart,
  RotationComponent,
  RotationDefinition,
  TerminationPart,
} from './exampleRotation'
import { strings } from '../strings'

/**
 * The rotation ribbon: the components of one rotation laid out along a
 * timeline, left to right in position order. Each card carries the crop and
 * its purpose, the sowing and harvest dates, and the management block. The
 * unit is display-only: it renders what the rotation_definition contract
 * travels and decides nothing — editing is a later unit, and feasibility
 * belongs to the calendar engine.
 *
 * Dates are not value items (they carry no number and no unit), so they
 * render as text with their provenance label (C4.1) and source, not through
 * the value display. A date or a management part that travels as missing
 * keeps the missing pattern of the conventions (C3.1): it is named with its
 * reason, never left as an unexplained gap. Crop ids, purposes, residues,
 * intensities and methods are contract identifiers: they render exactly as
 * they travel, without translation.
 *
 * The lines above the timeline carry what the definition says about the
 * year and the cycle: the start month keeps its provisional mark (C5.4)
 * and a rotation that does not repeat says so, in place of the repeats
 * line.
 *
 * All user-visible wording lives in strings.ts. Class lists follow the
 * strings rule of the repo: arrays of single-word tokens joined at runtime.
 */

/** One missing part rendered as the conventions pattern: "{what}: {reason phrase}". */
function MissingRow({ label, missing }: { label: string; missing: MissingPart }) {
  return (
    <p
      data-testid="ribbon-missing"
      className={['mt-1', 'text-sm', 'italic', 'text-fs-muted'].join(' ')}
    >
      {missingPatternText(label, missing)}
    </p>
  )
}

/** A dated event (sowing, harvest): the date with its provenance, or the missing pattern. */
function DatedRow({ label, part }: { label: string; part: DatedPart }) {
  if (part.missing) {
    return <MissingRow label={label} missing={part.missing} />
  }
  return (
    <div className="mt-2">
      <p className="text-sm">
        <span className="text-fs-muted">{label}:</span>{' '}
        <span data-testid="ribbon-date" className="font-medium">
          {part.date}
        </span>{' '}
        <span className="text-fs-muted">{strings[`provenance.${part.provenance}`]}</span>
      </p>
      <p className="text-xs text-fs-muted">
        {formatString(strings['value.source'], { source: part.source })}
      </p>
    </div>
  )
}

/** The residue of the management block: its value, or the missing pattern. */
function ResidueRow({ residue }: { residue: ResiduePart }) {
  if (typeof residue !== 'string') {
    return <MissingRow label={strings['ribbon.mgmt_residue']} missing={residue.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_residue']}:</span>{' '}
      <span className="font-medium">{residue}</span>
    </p>
  )
}

/** The grazing of the management block: its intensity, or the missing pattern. */
function GrazingRow({ grazing }: { grazing: GrazingPart }) {
  if ('missing' in grazing) {
    return <MissingRow label={strings['ribbon.mgmt_grazing']} missing={grazing.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_grazing']}:</span>{' '}
      <span className="font-medium">{grazing.intensity}</span>
    </p>
  )
}

/** The termination of the management block: its dated method, or the missing pattern. */
function TerminationRow({ termination }: { termination: TerminationPart }) {
  if ('missing' in termination) {
    return <MissingRow label={strings['ribbon.mgmt_termination']} missing={termination.missing} />
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-fs-muted">{strings['ribbon.mgmt_termination']}:</span>{' '}
      <span data-testid="ribbon-date" className="font-medium">
        {termination.date}
      </span>{' '}
      <span className="font-medium">{termination.method}</span>
    </p>
  )
}

/** One component of the timeline: a card with crop, purpose, dates and management. */
function ComponentCard({ component }: { component: RotationComponent }) {
  return (
    <li
      data-testid="rotation-component"
      className={[
        'min-w-48',
        'flex-1',
        'rounded-lg',
        'border',
        'border-fs-border',
        'bg-fs-surface',
        'p-4',
      ].join(' ')}
    >
      <h4 className="text-sm font-semibold">
        {formatString(strings['ribbon.component'], { position: component.position })}
      </h4>
      <p className="mt-2 text-sm">
        <span className="text-fs-muted">{strings['ribbon.crop']}:</span>{' '}
        <span data-testid="ribbon-crop" className="font-medium">
          {component.crop_id}
        </span>
      </p>
      <p className="mt-1 text-sm">
        <span className="text-fs-muted">{strings['ribbon.purpose']}:</span>{' '}
        <span className="font-medium">{component.purpose}</span>
      </p>
      <DatedRow label={strings['ribbon.sowing']} part={component.sowing} />
      <DatedRow label={strings['ribbon.harvest']} part={component.harvest} />
      <div className={['mt-3', 'border-t', 'border-fs-faint', 'pt-2'].join(' ')}>
        <p className="text-xs font-semibold uppercase text-fs-muted">
          {strings['ribbon.management']}
        </p>
        <div className="mt-1">
          <ResidueRow residue={component.management.residue} />
          <GrazingRow grazing={component.management.grazing} />
          <TerminationRow termination={component.management.termination} />
        </div>
      </div>
    </li>
  )
}

/**
 * The rotation timeline of the selected field. The components render left to
 * right in position order, whatever order the file lists them in; the ribbon
 * itself invents no dates and no order of its own.
 */
export function RotationRibbon({ rotation }: { rotation: RotationDefinition }) {
  const components = [...rotation.components].sort((a, b) => a.position - b.position)

  return (
    <section aria-labelledby="rotation-ribbon-title">
      <h3 id="rotation-ribbon-title" className="text-base font-semibold">
        {strings['ribbon.title']}
      </h3>
      {rotation.example_data && (
        <p
          role="note"
          className={[
            'mt-2',
            'rounded',
            'border',
            'border-fs-warning',
            'bg-fs-warning-bg',
            'px-3',
            'py-2',
            'text-sm',
            'text-fs-warning',
          ].join(' ')}
        >
          {strings['example.banner']}
        </p>
      )}
      <p className="mt-3 text-sm font-medium">
        {formatString(strings['ribbon.rotation_of'], { label: rotation.label })}
      </p>
      <p data-testid="ag-year-line" className="mt-1 text-sm text-fs-muted">
        {formatString(strings['ribbon.ag_year_start'], { month: rotation.ag_year_start.month })}
        {rotation.ag_year_start.provisional && (
          <>
            {' '}
            {strings['ribbon.provisional']}
          </>
        )}
      </p>
      <p data-testid="repeats-line" className="mt-1 text-sm text-fs-muted">
        {rotation.repeats ? strings['ribbon.repeats'] : strings['ribbon.not_repeating']}
      </p>
      <ol className={['mt-4', 'flex', 'list-none', 'gap-4', 'overflow-x-auto', 'pb-2'].join(' ')}>
        {components.map((component) => (
          <ComponentCard key={component.component_id} component={component} />
        ))}
      </ol>
    </section>
  )
}

export default RotationRibbon
