import { useMemo, useReducer, useState } from 'react'
import type { ReactNode } from 'react'
import { QueryClient, keepPreviousData, useQuery } from '@tanstack/react-query'
import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { exampleCase } from '../identity/exampleCase'
import type { ExampleField } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import FieldsMap from '../map/FieldsMap'
import { barScale } from '../plant/optionBars'
import {
  SourcesNotice,
  StatusPanel,
  initialPlantState,
  plantScreenReducer,
  serviceRequestOf,
  servicePhaseOf,
} from '../plant/PlantScreen'
import type { PlantAction, PlantScreenState, ServicePhase, ServiceStatus } from '../plant/PlantScreen'
import { CropLegend } from '../plant/PlantVisuals'
import type { PlantAnswer, PlantOption, RainStressPart } from '../plant/plantData'
import { configuredApiBase, plantScreenQueryOptions, readBaseRequest } from '../plant/plantRoute'
import { buildRotationStrip, cropOrder, plantRotations, readPlantRotations } from '../plant/rotationStrip'
import type { PlantRotations } from '../plant/rotationStrip'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { answerChanges, boardColumns, cropName, isExampleCrop, optionLetter } from './boardModel'
import type { SortKey } from './boardModel'
import {
  AnswerBanner,
  AnswerLimits,
  BoardControls,
  ChangesNote,
  PriceTrackPanel,
  RainEcho,
  RecordRibbon,
} from './BoardParts'
import { CompareTable, SortPicker, optionTitle, orderNote } from './CompareTable'
import type { OptionInfo } from './CompareTable'
import { RotationBuilder } from './RotationBuilder'
import { exampleRotations, normalizeDraft } from './rotationDraft'
import type { DraftRotation } from './rotationDraft'

/**
 * The rotation board (PROPOSED, l3/board), at hash route #/board: one
 * screen where the map of the fields is the way in and the answer to "What
 * should I plant?" is laid out as a board.
 *
 * On one side, the map and the list of the fields of the case. On the other,
 * the board of the field picked: the questions as controls (the kind of
 * year, the limit rule, the rain), the banner of the answer, the soybean
 * price as a track, and the options side by side, one column per rotation,
 * in the order picked.
 *
 * Where the data comes from. Picking a field that the plant request
 * describes asks the service (POST /api/plant/run, the call and the state
 * of the screen "What should I plant?", reused unchanged); changing a
 * control asks again, one call per distinct request. The board computes
 * nothing and shows no example answer: with no service configured it says
 * so (D251 of #77). A field the request does not describe has no rotations
 * declared, and the board says so instead of borrowing another field's.
 *
 * Every detail line of the answer (each value with its source and check)
 * stays on the screen "What should I plant?", one link away.
 */

/** The field the plant request describes: the only one the board can ask for. */
const REQUEST_FIELD_ID: string = rawPlantRequest.site.field_id

const REQUEST_READ = readBaseRequest(rawPlantRequest)

/** The soil-loss limit the request declares, as declared; null when it has no value. */
const REQUEST_LIMIT: { value: number; unit: string } | null =
  typeof rawPlantRequest.soil_loss_limit.value === 'number'
    ? { value: rawPlantRequest.soil_loss_limit.value, unit: rawPlantRequest.soil_loss_limit.unit }
    : null

/** The board asks as soon as its field is picked: the state starts in service mode. */
export function initialBoardState(): PlantScreenState {
  return plantScreenReducer(initialPlantState(), { type: 'ask' })
}

function ignore() {}

/** The heading of a step of the plan: its number and what it is. */
function StepTitle({ n, title, children = null }: { n: number; title: string; children?: ReactNode }) {
  return (
    <div className="mb-2 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <h3 data-testid="board-step" className="flex items-center gap-2 text-xl font-bold">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-fs-text font-mono text-xs text-fs-surface">
          {n}
        </span>
        {title}
      </h3>
      {children}
    </div>
  )
}

function FieldList({ fields, selectedFieldId }: { fields: ExampleField[]; selectedFieldId: string | null }) {
  return (
    <ul data-testid="board-fields" className="grid gap-2 sm:grid-cols-3">
      {fields.map((field) => {
        const described = field.field_id === REQUEST_FIELD_ID
        return (
          <li key={field.field_id} className="relative">
            <div
              data-selected={String(field.field_id === selectedFieldId)}
              data-described={String(described)}
              className="rounded-xl border border-fs-border bg-fs-surface px-3 py-2 data-[described=false]:fs-fog data-[selected=true]:border-2 data-[selected=true]:border-fs-primary"
            >
              <p className="font-bold leading-tight">{field.name}</p>
              <p className="text-xs text-fs-muted">
                {described
                  ? strings['board.field.ready']
                  : missingPatternText(strings['board.rotations'], { reason: 'NOT_DECLARED' })}
              </p>
            </div>
            <button
              type="button"
              aria-pressed={field.field_id === selectedFieldId}
              aria-label={field.name}
              className="absolute inset-0 cursor-pointer rounded-xl"
              onClick={() => setSelectedFieldId(field.field_id)}
            />
          </li>
        )
      })}
    </ul>
  )
}

/** What the request says of each option, the colours of their crops and the scales of their bars. */
function useBoardInfo(answer: PlantAnswer, rotations: PlantRotations) {
  return useMemo(() => {
    const kind = answer.margin_of
    const byId = new Map<string, OptionInfo>()
    for (const option of answer.options) {
      const rotation = rotations.rotations?.find((r) => r.rotation_id === option.rotation_id) ?? null
      byId.set(option.rotation_id, { rotation, strip: rotation !== null ? buildRotationStrip(rotation) : null })
    }
    const strips = [...byId.values()].flatMap((each) => (each.strip !== null ? [each.strip] : []))
    return {
      info: (option: PlantOption): OptionInfo => byId.get(option.rotation_id) ?? { rotation: null, strip: null },
      order: cropOrder(strips),
      scales: {
        margin: barScale(answer.options.map((o) => o.margin[kind].value)),
        soilLoss: barScale([
          ...answer.options.map((o) => o.soil_loss[kind].value),
          ...answer.options.map((o) => o.limit),
        ]),
      },
    }
  }, [answer, rotations])
}

function Answered({
  answer,
  rainStress,
  rotations,
  firstStep,
  previous,
  updating,
}: {
  answer: PlantAnswer
  rainStress: RainStressPart | null
  rotations: PlantRotations
  /** The number of the first step of the answer: the steps before it are numbered by the view. */
  firstStep: number
  /** The answer shown before this one, when there was one: what changed is said. */
  previous: PlantAnswer | null
  /** True while the answer shown is the one before and the new one is on its way. */
  updating: boolean
}) {
  const { info, order, scales } = useBoardInfo(answer, rotations)
  const [sort, setSort] = useState<SortKey>('rule')
  const columns = useMemo(() => boardColumns(answer, sort), [answer, sort])
  const chosen = answer.options.find((option) => option.rotation_id === answer.chosen) ?? null
  // A rotation named as its column is: its letter and its crops.
  const nameOf = (rotationId: string): string => {
    const option = answer.options.find((each) => each.rotation_id === rotationId)
    if (option === undefined) {
      return rotationId
    }
    return formatString(strings['board.option_title'], {
      letter: optionLetter(answer, option),
      title: optionTitle(option, info(option)),
    })
  }
  const note = orderNote(columns, sort)
  const againstText = answer.limit_cost.kind === 'value' ? nameOf(answer.limit_cost.against) : null
  // The sources an answer lacks are its root reason: said once, in the notice.
  const lacksSources = answer.sources.some((source) => source.state === 'unavailable' && source.missing_reason !== null)
  return (
    <div data-testid="board-answered" data-updating={String(updating)} className="space-y-6 data-[updating=true]:opacity-60">
      {updating ? (
        <p data-testid="board-updating" role="status" className="text-sm font-semibold text-fs-muted">
          {strings['board.updating']}
        </p>
      ) : null}
      <div className="space-y-3">
        <AnswerBanner
          answer={answer}
          label={chosen !== null ? nameOf(chosen.rotation_id) : null}
          showWhy={!lacksSources}
          against={againstText}
        />
        {previous !== null ? (
          <ChangesNote changes={answerChanges(previous, answer)} nameOf={nameOf} />
        ) : null}
        {rainStress !== null ? (
          <RainEcho part={rainStress} />
        ) : null}
        {answer.chosen === null ? (
          <SourcesNotice answer={answer} />
        ) : null}
      </div>
      <div>
        <StepTitle n={firstStep} title={strings['board.compare.title']}>
          <SortPicker sort={sort} onSort={setSort} />
        </StepTitle>
        {note !== null ? (
          <p data-testid="board-order-note" className="mb-2 text-sm font-semibold text-fs-warning">
            {note}
          </p>
        ) : null}
        <CompareTable answer={answer} columns={columns} info={info} order={order} scales={scales} sort={sort} />
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          <CropLegend order={order} nameOf={cropName} />
          {order.some(isExampleCrop) ? (
            <span data-testid="board-example-crops" className="rounded-full border border-fs-warning px-2 py-0.5 text-[11px] font-semibold text-fs-warning">
              {strings['board.example_crops']}
            </span>
          ) : null}
        </div>
      </div>
      <div>
        <StepTitle n={firstStep + 1} title={strings['board.step.holds']} />
        <div className="grid gap-4 xl:grid-cols-2">
          <PriceTrackPanel tipping={answer.tipping_price} nameOf={nameOf} />
          <RecordRibbon record={answer.kinds_of_year} marginOf={answer.margin_of} />
        </div>
      </div>
      <div>
        <StepTitle n={firstStep + 2} title={strings['board.step.keep']} />
        <AnswerLimits answer={answer} />
        <div className="mt-3 flex flex-wrap gap-3">
          <a
            data-testid="board-print"
            href="#/print"
            className="inline-flex min-h-11 items-center rounded-lg bg-fs-primary px-4 font-semibold text-white"
          >
            {strings['print.open_link']}
          </a>
          <a
            data-testid="board-report"
            href="#/plant"
            className="inline-flex min-h-11 items-center rounded-lg border border-fs-border bg-fs-surface px-4 font-semibold text-fs-primary"
          >
            {strings['board.report']}
          </a>
        </div>
      </div>
    </div>
  )
}

/** The side of the board: what to show for the field picked and the state of the call. */
function BoardSide({
  selectedFieldId,
  apiBase,
  service,
  rotations,
  firstStep,
  previous,
  updating,
}: {
  selectedFieldId: string | null
  apiBase: string | null
  service: ServicePhase | null
  rotations: PlantRotations
  firstStep: number
  previous: PlantAnswer | null
  updating: boolean
}) {
  if (selectedFieldId === null) {
    return (
      <p data-testid="board-pick" className="rounded-2xl border-2 border-dashed border-fs-border px-6 py-10 text-center text-lg text-fs-muted">
        {strings['map.select_hint']}
      </p>
    )
  }
  if (selectedFieldId !== REQUEST_FIELD_ID) {
    return (
      <p data-testid="board-not-declared" className="rounded-2xl border border-fs-border px-6 py-10 text-center text-lg text-fs-muted fs-fog">
        {missingPatternText(strings['board.rotations'], { reason: 'NOT_DECLARED' })}
      </p>
    )
  }
  if (apiBase === null) {
    return (
      <p data-testid="board-no-service" className="rounded-2xl border border-fs-border bg-fs-surface px-6 py-10 text-center text-lg">
        {strings['plant.service.not_available']}
      </p>
    )
  }
  if (service === null || service.phase !== 'answered') {
    const status: ServiceStatus =
      service === null || service.phase === 'pending'
        ? { kind: 'pending' }
        : service.phase === 'not_available'
          ? { kind: 'not_available', missing: service.missing }
          : { kind: 'failed', code: service.code }
    return (
      <StatusPanel status={status} />
    )
  }
  return (
    <Answered
      answer={service.answer.answer}
      rainStress={service.answer.rainStress}
      rotations={rotations}
      firstStep={firstStep}
      previous={previous}
      updating={updating}
    />
  )
}

/**
 * The board for a state: a pure function of the field picked, the questions,
 * the configured backend and the phase of the call. The map is passed in so
 * the view renders without it in tests.
 */
export function BoardView({
  selectedFieldId,
  state,
  apiBase,
  service,
  dispatch = ignore,
  map = null,
  mapOpen = true,
  onToggleMap,
  rotations = plantRotations,
  builder = null,
  previous = null,
  updating = false,
}: {
  selectedFieldId: string | null
  state: PlantScreenState
  apiBase: string | null
  service: ServicePhase | null
  dispatch?: (action: PlantAction) => void
  map?: ReactNode
  /** Whether the map is shown; the list of the fields is always shown. */
  mapOpen?: boolean
  /** Given when the map can be shown or hidden. */
  onToggleMap?: () => void
  /** The rotations compared, as the request holds them; those of the example request by default. */
  rotations?: PlantRotations
  /** The step of the candidates (the rotation builder), when the rotations can be edited. */
  builder?: ReactNode
  /** The answer shown before the one of the service now, when there was one. */
  previous?: PlantAnswer | null
  /** True while the answer shown is the one before and the new one is on its way. */
  updating?: boolean
}) {
  // The steps are numbered as shown: the candidates are a step only for the
  // field whose rotations can be edited.
  const hasCandidates = builder !== null && selectedFieldId === REQUEST_FIELD_ID
  const scenarioStep = hasCandidates ? 3 : 2
  return (
    <section aria-labelledby="board-title" className="mx-auto max-w-[100rem] space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <h2 id="board-title" className="text-4xl font-extrabold leading-tight">
            {strings['board.title']}
          </h2>
        </div>
        {exampleCase.example_data ? (
          <p data-testid="board-example" role="note" className="rounded-full border border-fs-warning bg-fs-warning-bg px-3 py-1 text-sm text-fs-warning">
            {strings['example.banner']}
          </p>
        ) : null}
      </div>

      <div>
        <StepTitle n={1} title={strings['board.step.field']}>
          {onToggleMap !== undefined ? (
            <button
              type="button"
              data-testid="board-map-toggle"
              aria-expanded={mapOpen}
              className="min-h-9 cursor-pointer rounded-lg border border-fs-border bg-fs-surface px-3 text-sm font-semibold"
              onClick={onToggleMap}
            >
              {strings[mapOpen ? 'board.map.hide' : 'board.map.show']}
            </button>
          ) : null}
        </StepTitle>
        <div className="grid items-stretch gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
          <FieldList fields={exampleCase.fields} selectedFieldId={selectedFieldId} />
          {REQUEST_LIMIT !== null ? (
            <div data-testid="board-your-limit" className="rounded-xl border-2 border-fs-text bg-fs-surface px-4 py-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-fs-muted">{strings['board.limit.yours']}</p>
              <p className="tabular-nums">
                <span className="font-fs-heading text-2xl font-extrabold leading-none">{displayNumber(REQUEST_LIMIT.value)}</span>{' '}
                <span className="text-xs text-fs-muted">{REQUEST_LIMIT.unit}</span>
              </p>
              <p className="text-[11px] text-fs-muted">{strings['plant.declared']}</p>
            </div>
          ) : null}
        </div>
        {mapOpen && map !== null ? (
          <div data-testid="board-map" className="mt-3">
            {map}
          </div>
        ) : null}
      </div>

      {hasCandidates ? (
        <details data-testid="board-candidates" className="group">
          <summary className="cursor-pointer list-none">
            <StepTitle n={2} title={strings['board.step.candidates']}>
              <span className="rounded-lg border border-fs-border bg-fs-surface px-3 py-1.5 text-sm font-semibold group-open:hidden">
                {strings['board.builder.open']}
              </span>
            </StepTitle>
          </summary>
          {builder}
        </details>
      ) : null}

      <div>
        <StepTitle n={scenarioStep} title={strings['board.step.scenario']} />
        <BoardControls
          marginOf={state.marginOf}
          strictness={state.strictness}
          rain={state.rain && REQUEST_READ.rain.kind === 'present'}
          rainFactor={REQUEST_READ.rain.kind === 'present' ? REQUEST_READ.rain.factor : null}
          record={service !== null && service.phase === 'answered' ? service.answer.answer.kinds_of_year : null}
          limit={REQUEST_LIMIT}
          onMarginOf={(value) => dispatch({ type: 'margin_of', value })}
          onStrictness={(value) => dispatch({ type: 'strictness', value })}
          onRain={(on) => dispatch({ type: 'rain', on })}
        />
      </div>

      <BoardSide
        selectedFieldId={selectedFieldId}
        apiBase={apiBase}
        service={service}
        rotations={rotations}
        firstStep={scenarioStep + 1}
        previous={previous}
        updating={updating}
      />

      <p data-testid="board-disclaimer" className="text-xs text-fs-muted">
        {strings['disclaimer.full']}
      </p>
    </section>
  )
}

/** The query client used when no backend is configured: the query is then disabled and never calls. */
const NO_SERVICE_CLIENT = new QueryClient()

/** The screen at #/board. The backend is the configured one (VITE_API_URL) unless given. */
export default function BoardScreen({ apiBase = configuredApiBase() }: { apiBase?: string | null }) {
  const selectedFieldId = useSelectedFieldId()
  const [state, dispatch] = useReducer(plantScreenReducer, null, initialBoardState)
  // The rotations compared (sent) and those being edited (draft): the
  // service is asked for the sent ones only, so an edit asks nothing until
  // the user compares.
  const [sent, setSent] = useState<DraftRotation[]>(exampleRotations)
  const [draft, setDraft] = useState<DraftRotation[]>(exampleRotations)
  const baseRequest = useMemo(() => ({ ...rawPlantRequest, rotations: sent }), [sent])
  const rotations = useMemo(() => readPlantRotations(baseRequest), [baseRequest])
  const asks = apiBase !== null && selectedFieldId === REQUEST_FIELD_ID
  const request = useMemo(
    () => (asks ? serviceRequestOf(state, baseRequest) : null),
    [asks, baseRequest, state.mode, state.strictness, state.marginOf, state.rain],
  )
  // While a new answer is on its way the one before stays on screen, marked
  // as updating, so a control does not blank the board.
  const query = useQuery(
    { ...plantScreenQueryOptions(apiBase, request), placeholderData: keepPreviousData },
    apiBase === null ? NO_SERVICE_CLIENT : undefined,
  )
  // The map opens the screen and steps aside once a field is picked, unless
  // the user shows or hides it: then their choice stays.
  // The answer shown and the one before it, so the board can say what a
  // control changed. Kept as the answers arrive (state derived while
  // rendering, the pattern React documents for it).
  const phase = request === null ? null : servicePhaseOf(query)
  const answerNow = phase !== null && phase.phase === 'answered' ? phase.answer.answer : null
  const [seen, setSeen] = useState<{ current: PlantAnswer | null; previous: PlantAnswer | null }>({
    current: null,
    previous: null,
  })
  if (answerNow !== null && answerNow !== seen.current) {
    setSeen({ current: answerNow, previous: seen.current })
  }
  const [mapChoice, setMapChoice] = useState<boolean | null>(null)
  const mapOpen = mapChoice ?? selectedFieldId === null
  return (
    <BoardView
      selectedFieldId={selectedFieldId}
      state={state}
      apiBase={apiBase}
      service={phase}
      updating={request !== null && query.isPlaceholderData}
      previous={answerNow !== null && answerNow === seen.current ? seen.previous : null}
      dispatch={dispatch}
      map={<FieldsMap />}
      mapOpen={mapOpen}
      onToggleMap={() => setMapChoice(!mapOpen)}
      rotations={rotations}
      builder={
        <RotationBuilder
          draft={draft}
          sent={sent}
          onChange={setDraft}
          onCompare={() => {
            const ordered = normalizeDraft(draft)
            setDraft(ordered)
            setSent(ordered)
          }}
          onReset={() => {
            const example = exampleRotations()
            setDraft(example)
            setSent(example)
          }}
        />
      }
    />
  )
}
