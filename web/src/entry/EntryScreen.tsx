import { missingPatternText } from '../components/ValueDisplay'
import { CardCount, CardHeader, KpiTile } from '../components/Card'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import FieldsMap from '../map/FieldsMap'
import { fieldAreaHa } from '../map/geometry'
import { MockBadge } from '../mockfill/MockPanel'
import { EXAMPLE_FACTS, usePlan } from '../board/planStore'
import { answerAttention, NO_ANSWER_ITEM } from '../board/attention'
import type { AttentionTarget } from '../board/attention'
import { changedFacts } from '../board/factsDraft'
import { AttentionPanel } from '../components/Attention'
import { BarList } from '../charts/BarList'
import heroPhoto from '../assets/images/soybean-field-ayotte-laval.jpg'
import type { Plan } from '../board/planStore'
import {
  IconArchive,
  IconArrowRight,
  IconChart,
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

function KpiNumber({ value }: { value: string }) {
  return <p className="font-fs-heading text-2xl font-bold leading-none">{value}</p>
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

/** Where the credit of the hero photo points: the file page and its licence (CC BY-SA 4.0 asks for both). */
const PHOTO_SOURCE_URL = 'https://commons.wikimedia.org/wiki/File:Glycine_max_15-p.bot-glyci.max-037.jpg'
const PHOTO_LICENCE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'

/**
 * The hero band of the overview: the photo chosen by the interface owner
 * (recorded in ATTRIBUTIONS.md), shown unaltered with a soft gradient over it
 * so the title stays readable, and its credit with the licence link beside it.
 */
function HeroBand() {
  return (
    <div data-testid="overview-hero" className="relative h-52 overflow-hidden rounded-fs-card border border-fs-border shadow-fs-card">
      <img src={heroPhoto} alt={strings['overview.photo.alt']} className="absolute inset-0 h-full w-full object-cover" />
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-r from-fs-text/85 via-fs-text/45 to-transparent" />
      <div className="relative flex h-full flex-col justify-end p-6 text-fs-surface">
        <h2 id="entry-screen-title" className="font-fs-heading text-3xl font-extrabold leading-tight">
          {strings['entry.title']}
        </h2>
        <p className="mt-1 text-sm opacity-90">
          {exampleCase.label} · {formatString(strings['entry.fields_count'], { n: exampleCase.fields.length })}
        </p>
      </div>
      <p data-testid="overview-photo-credit" className="absolute bottom-2 right-2 max-w-[60%] rounded-md bg-fs-text/70 px-2 py-1 text-[11px] leading-snug text-fs-surface">
        {strings['overview.photo.credit_lead']}{' '}
        <a href={PHOTO_SOURCE_URL} target="_blank" rel="noreferrer" className="underline underline-offset-2">
          {strings['overview.photo.credit_author']}
        </a>
        {', '}
        <a href={PHOTO_LICENCE_URL} target="_blank" rel="noreferrer" className="underline underline-offset-2">
          {strings['overview.photo.licence']}
        </a>
      </p>
    </div>
  )
}

/** Where an item of "Needs attention" leads from the overview: the full report for the sources, the board for the rest. */
function overviewLinkOf(target: AttentionTarget) {
  return { href: target === 'report' ? '#/plant' : '#/board' }
}

/** What needs attention in the case: the items of the last answer the board showed, or that there is none yet. */
function OverviewAttention({ plan }: { plan: Plan }) {
  const last = plan.lastAnswer
  if (last === null) {
    return <AttentionPanel items={[NO_ANSWER_ITEM]} linkOf={overviewLinkOf} />
  }
  const field = exampleCase.fields.find((each) => each.field_id === last.fieldId) ?? null
  const nameOf = (rotationId: string) => plan.sent.find((r) => r.rotation_id === rotationId)?.label ?? rotationId
  const items = answerAttention(last.answer, {
    mocked: last.mocked,
    exampleNumbers: changedFacts(plan.factsSent, EXAMPLE_FACTS) === 0,
    nameOf,
  })
  return (
    <AttentionPanel
      items={items}
      linkOf={overviewLinkOf}
      subtitle={formatString(strings['attention.from_last'], { field: field?.name ?? last.fieldId })}
    />
  )
}

/** The area of each field, as a bar list: the outlines measured, nothing modelled. */
function FieldAreas() {
  return (
    <section data-testid="overview-areas" aria-labelledby="overview-areas-title" className="fs-card p-4">
      <CardHeader id="overview-areas-title" icon={IconChart} title={strings['overview.areas.title']} />
      <BarList
        label={strings['overview.areas.label']}
        format={(ha) => formatString(strings['overview.areas.value'], { ha: ha.toFixed(1) })}
        items={exampleCase.fields.map((field) => ({ id: field.field_id, label: field.name, value: fieldAreaHa(field) }))}
      />
      <p className="mt-2 text-[11px] text-fs-muted">{strings['overview.areas.label']}</p>
    </section>
  )
}

/**
 * The entry screen: an overview of the case on example data, in the manner
 * of the home of a farm-management system (PROPOSED, l3/erp-shell, cards and
 * attention by l3/original-mock). A hero band with the case label and the
 * fields count, and the example-data banner; the map of the field outlines
 * beside a right column with the summary tiles, what needs attention and the
 * last answer the board showed; the list of fields, where the selected one
 * offers the open action that carries the selection to the fields screen,
 * beside the field areas and the next steps. Nothing scientific is computed
 * here.
 */
export default function EntryScreen() {
  const selectedFieldId = useSelectedFieldId()
  const plan = usePlan()

  return (
    <section aria-labelledby="entry-screen-title" className="mx-auto max-w-7xl">
      <HeroBand />

      {exampleCase.example_data && (
        <p
          role="note"
          className="mt-4 rounded-lg border border-fs-warning bg-fs-warning-bg px-4 py-3 text-sm text-fs-warning"
        >
          {strings['board.example_banner']}
        </p>
      )}

      <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-5">
        <section aria-labelledby="overview-map-title" className="fs-card p-4">
          <CardHeader id="overview-map-title" icon={IconMap} title={strings['overview.map']} />
          <p className="mb-2 text-[11px] text-fs-muted">
            {strings['map.select_hint']}
          </p>
          <FieldsMap compact />
        </section>
        <section aria-labelledby="overview-fields-title" className="fs-card p-4">
          <CardHeader
            id="overview-fields-title"
            icon={IconMap}
            title={strings['identity.title']}
            aside={<CardCount n={exampleCase.fields.length} />}
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
                        : ['border-fs-border', 'bg-fs-surface', 'shadow-fs-card', 'hover:-translate-y-0.5', 'hover:shadow-fs-card-hover']),
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
        </div>

        <div className="space-y-5">
          <section aria-labelledby="overview-summary-title">
            <h3 id="overview-summary-title" className="fs-eyebrow mb-2">
              {strings['overview.summary']}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <KpiTile icon={IconMap} label={strings['overview.kpi.fields']}>
                <KpiNumber value={String(exampleCase.fields.length)} />
              </KpiTile>
              <KpiTile icon={IconRotate} label={strings['overview.kpi.rotations']}>
                <KpiNumber value={String(plan.sent.length)} />
              </KpiTile>
              <KpiTile icon={IconRuler} label={strings['overview.kpi.hectares']} wide>
                <KpiNumber value={TOTAL_HA.toFixed(1)} />
              </KpiTile>
            </div>
          </section>

          <OverviewAttention plan={plan} />

          <LastAnswer plan={plan} />
        <FieldAreas />
        <nav aria-labelledby="overview-steps-title" className="fs-card p-4">
          <CardHeader id="overview-steps-title" icon={IconArrowRight} title={strings['overview.next_steps']} />
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
      </div>
    </section>
  )
}
