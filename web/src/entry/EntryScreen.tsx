import type { ReactNode } from 'react'
import { missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import FieldsMap from '../map/FieldsMap'
import { fieldAreaHa } from '../map/geometry'
import { MockBadge } from '../mockfill/MockPanel'
import { usePlan } from '../board/planStore'
import type { Plan } from '../board/planStore'
import {
  IconArchive,
  IconArrowRight,
  IconCheckCircle,
  IconMap,
  IconPrinter,
  IconReport,
  IconRotate,
  IconRuler,
  IconSprout,
} from '../shell/icons'
import type { Icon } from '../shell/icons'
import { strings } from '../strings'
import type { StringKey } from '../strings'

/**
 * Continue from the entry screen to the fields screen: the field becomes the
 * shared selection (the map and the list below read the same store) and the
 * hash route moves to "#/fields".
 */
export function openFieldOnFieldsScreen(fieldId: string): void {
  setSelectedFieldId(fieldId)
  window.location.hash = '#/fields'
}

/** The total of the field outlines, in hectares: a sum of the measured outlines, nothing modelled. */
const TOTAL_HA = exampleCase.fields.reduce((total, field) => total + fieldAreaHa(field), 0)

/** The next steps from the overview, in the order of the work. */
const NEXT_STEPS: { href: string; label: StringKey; hint: StringKey; icon: Icon; testId?: string }[] = [
  { href: '#/board', label: 'nav.board', hint: 'overview.step.board', icon: IconSprout, testId: 'entry-plan-link' },
  { href: '#/fields', label: 'identity.title', hint: 'overview.step.fields', icon: IconMap },
  { href: '#/plant', label: 'nav.report', hint: 'overview.step.report', icon: IconReport },
  { href: '#/print', label: 'print.open_link', hint: 'overview.step.print', icon: IconPrinter },
  { href: '#/saved', label: 'saved.open_case', hint: 'overview.step.saved', icon: IconArchive },
]

/** The header of an overview card: the icon, the small uppercase title, and an optional count on the right. */
function CardHeader({ id, icon: HeaderIcon, title, aside }: { id: string; icon: Icon; title: string; aside?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="text-fs-primary">
        <HeaderIcon />
      </span>
      <h3 id={id} className="fs-eyebrow flex-1">
        {title}
      </h3>
      {aside}
    </div>
  )
}

function KpiTile({ icon: TileIcon, value, label, wide }: { icon: Icon; value: string; label: string; wide?: boolean }) {
  return (
    <div className={['fs-card', 'flex', 'items-start', 'gap-3', 'p-3.5', ...(wide ? ['col-span-2'] : [])].join(' ')}>
      <span className="rounded-md bg-fs-brand-soft p-1.5 text-fs-primary">
        <TileIcon />
      </span>
      <div className="min-w-0">
        <p className="font-fs-heading text-xl font-semibold leading-tight tabular-nums">{value}</p>
        <p className="mt-0.5 text-[11px] leading-snug text-fs-muted">{label}</p>
      </div>
    </div>
  )
}

/** The last answer the board showed, read from the plan store as it stands; nothing is computed here. */
function LastAnswer({ plan }: { plan: Plan }) {
  const last = plan.lastAnswer
  const field = last === null ? null : (exampleCase.fields.find((each) => each.field_id === last.fieldId) ?? null)
  const nameOf = (rotationId: string) => plan.sent.find((r) => r.rotation_id === rotationId)?.label ?? rotationId
  return (
    <section data-testid="overview-last-answer" aria-labelledby="overview-last-answer-title" className="fs-card p-4">
      <CardHeader id="overview-last-answer-title" icon={IconCheckCircle} title={strings['overview.last_answer']} />
      {last === null ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <span className="text-fs-muted opacity-40">
            <IconCheckCircle className="h-6 w-6" />
          </span>
          <p className="max-w-xs text-xs text-fs-muted">{strings['overview.no_answer']}</p>
        </div>
      ) : (
        <div className="text-sm">
          <p className="font-medium">
            {last.answer.chosen !== null ? nameOf(last.answer.chosen) : strings[`plant.answer.${last.answer.answer}`]}
            {last.mocked && <MockBadge />}
          </p>
          {last.answer.missing !== null && (
            <p className="mt-0.5 text-xs text-fs-muted">{missingPatternText(strings['plan.answer'], last.answer.missing)}</p>
          )}
          <p className="mt-0.5 text-xs text-fs-muted">
            {formatString(strings['overview.asked_for'], { field: field?.name ?? last.fieldId })}
          </p>
        </div>
      )}
      <a
        href="#/board"
        className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-xs font-semibold text-fs-primary transition hover:bg-fs-faint"
      >
        {strings['overview.open_board']}
        <IconArrowRight className="h-3.5 w-3.5" />
      </a>
    </section>
  )
}

/**
 * The entry screen: an overview of the case on example data, in the manner
 * of the home of a farm-management system (PROPOSED, l3/erp-shell). The
 * case label and fields count with the example-data banner; a small map of
 * the field outlines beside the summary (fields, hectares measured on the
 * outlines, rotations on the planning board) and the last answer the board
 * showed; the list of fields, where the selected one offers the open action
 * that carries the selection to the fields screen; and the next steps.
 * Nothing scientific is computed here.
 */
export default function EntryScreen() {
  const selectedFieldId = useSelectedFieldId()
  const plan = usePlan()

  return (
    <section aria-labelledby="entry-screen-title" className="mx-auto max-w-7xl">
      <h2 id="entry-screen-title" className="font-fs-heading text-2xl font-bold">
        {strings['entry.title']}
      </h2>
      <p className="mt-1 text-sm text-fs-muted">
        {exampleCase.label} · {formatString(strings['entry.fields_count'], { n: exampleCase.fields.length })}
      </p>

      {exampleCase.example_data && (
        <p
          role="note"
          className="mt-4 rounded-lg border border-fs-warning bg-fs-warning-bg px-4 py-3 text-sm text-fs-warning"
        >
          {strings['board.example_banner']}
        </p>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="overview-map-title" className="fs-card p-4">
          <CardHeader id="overview-map-title" icon={IconMap} title={strings['overview.map']} />
          <p className="mb-2 text-[11px] text-fs-muted">
            {strings['map.select_hint']}
          </p>
          <FieldsMap compact />
        </section>

        <div className="space-y-4">
          <section aria-labelledby="overview-summary-title">
            <h3 id="overview-summary-title" className="fs-eyebrow mb-2">
              {strings['overview.summary']}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <KpiTile icon={IconMap} value={String(exampleCase.fields.length)} label={strings['overview.kpi.fields']} />
              <KpiTile icon={IconRotate} value={String(plan.sent.length)} label={strings['overview.kpi.rotations']} />
              <KpiTile icon={IconRuler} value={TOTAL_HA.toFixed(1)} label={strings['overview.kpi.hectares']} wide />
            </div>
          </section>

          <LastAnswer plan={plan} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="overview-fields-title" className="fs-card p-4">
          <CardHeader
            id="overview-fields-title"
            icon={IconMap}
            title={strings['identity.title']}
            aside={
              <span className="rounded-full bg-fs-faint px-2 py-0.5 text-[11px] font-semibold tabular-nums text-fs-muted">
                {exampleCase.fields.length}
              </span>
            }
          />
          <p className="mb-3 text-xs text-fs-muted">{strings['overview.pick_field']}</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {exampleCase.fields.map((field) => {
              const isSelected = field.field_id === selectedFieldId
              return (
                <li key={field.field_id} className="space-y-2">
                  <button
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => setSelectedFieldId(field.field_id)}
                    className={[
                      'w-full', 'rounded-lg', 'border', 'px-3', 'py-2.5', 'text-left', 'transition',
                      ...(isSelected
                        ? ['border-fs-primary', 'bg-fs-selection', 'ring-1', 'ring-fs-primary']
                        : ['border-fs-border', 'bg-fs-surface', 'hover:bg-fs-faint']),
                    ].join(' ')}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="font-medium text-fs-text">{field.name}</span>
                      {isSelected && (
                        <span className="rounded bg-fs-primary px-2 py-0.5 text-[11px] font-semibold text-fs-surface">
                          {strings['identity.selected']}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-fs-muted">
                      {strings['identity.field_id_label']}: {field.field_id}
                    </span>
                    <span className="block text-xs tabular-nums text-fs-muted">
                      {formatString(strings['field.area'], { ha: fieldAreaHa(field).toFixed(1) })}
                    </span>
                  </button>
                  {isSelected && (
                    <button
                      type="button"
                      onClick={() => openFieldOnFieldsScreen(field.field_id)}
                      className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-fs-primary px-4 text-sm font-semibold text-fs-surface transition hover:opacity-90"
                    >
                      {strings['entry.open_field']}
                      <IconArrowRight />
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
          {exampleCase.fields.length === 0 && (
            <p className="text-sm text-fs-muted">{strings['identity.empty_list']}</p>
          )}
        </section>

        <nav aria-labelledby="overview-steps-title" className="fs-card p-4">
          <h3 id="overview-steps-title" className="fs-eyebrow mb-2">
            {strings['overview.next_steps']}
          </h3>
          <ul className="space-y-1">
            {NEXT_STEPS.map((step, index) => {
              const StepIcon = step.icon
              return (
                <li key={step.href}>
                  <a
                    href={step.href}
                    data-testid={step.testId}
                    className={[
                      'group', 'flex', 'min-h-12', 'items-center', 'gap-3', 'rounded-md', 'px-2', 'py-2', 'transition-colors',
                      ...(index === 0 ? ['bg-fs-selection', 'hover:bg-fs-brand-soft'] : ['hover:bg-fs-faint']),
                    ].join(' ')}
                  >
                    <span className="rounded-md bg-fs-brand-soft p-1.5 text-fs-primary">
                      <StepIcon />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-fs-text">{strings[step.label]}</span>
                      <span className="block text-xs text-fs-muted">{strings[step.hint]}</span>
                    </span>
                    <span className="text-fs-muted transition-transform group-hover:translate-x-0.5 group-hover:text-fs-primary">
                      <IconArrowRight />
                    </span>
                  </a>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>
    </section>
  )
}
