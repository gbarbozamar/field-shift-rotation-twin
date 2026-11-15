import { useMemo, useReducer, useState } from 'react'
import type { ReactNode } from 'react'
import { QueryClient, useQuery } from '@tanstack/react-query'
import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import { missingPatternText } from '../components/ValueDisplay'
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
import type { PlantAnswer, PlantOption } from '../plant/plantData'
import { configuredApiBase, plantScreenQueryOptions, readBaseRequest } from '../plant/plantRoute'
import { buildRotationStrip, cropOrder, plantRotations } from '../plant/rotationStrip'
import { strings } from '../strings'
import { boardColumns } from './boardModel'
import type { SortKey } from './boardModel'
import { AnswerBanner, BoardControls, PriceTrackPanel } from './BoardParts'
import { CompareTable, SortPicker, cropsText } from './CompareTable'
import type { OptionInfo } from './CompareTable'

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

/** The board asks as soon as its field is picked: the state starts in service mode. */
export function initialBoardState(): PlantScreenState {
  return plantScreenReducer(initialPlantState(), { type: 'ask' })
}

function ignore() {}

function FieldList({ fields, selectedFieldId }: { fields: ExampleField[]; selectedFieldId: string | null }) {
  return (
    <ul data-testid="board-fields" className="mt-3 grid gap-2">
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
function useBoardInfo(answer: PlantAnswer) {
  return useMemo(() => {
    const kind = answer.margin_of
    const byId = new Map<string, OptionInfo>()
    for (const option of answer.options) {
      const rotation = plantRotations.rotations?.find((r) => r.rotation_id === option.rotation_id) ?? null
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
  }, [answer])
}

function Answered({ answer }: { answer: PlantAnswer }) {
  const { info, order, scales } = useBoardInfo(answer)
  const [sort, setSort] = useState<SortKey>('rule')
  const columns = useMemo(() => boardColumns(answer, sort), [answer, sort])
  const chosen = answer.options.find((option) => option.rotation_id === answer.chosen) ?? null
  // The sources an answer lacks are its root reason: said once, in the notice.
  const lacksSources = answer.sources.some((source) => source.state === 'unavailable' && source.missing_reason !== null)
  return (
    <div className="space-y-4">
      <AnswerBanner
        answer={answer}
        label={chosen !== null ? cropsText(info(chosen).strip) : null}
        showWhy={!lacksSources}
      />
      {answer.chosen === null ? (
        <SourcesNotice answer={answer} />
      ) : null}
      <PriceTrackPanel tipping={answer.tipping_price} />
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h3 className="text-xl font-bold">{strings['board.compare.title']}</h3>
        <SortPicker sort={sort} onSort={setSort} />
      </div>
      <CompareTable answer={answer} columns={columns} info={info} order={order} scales={scales} />
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <CropLegend order={order} />
        <a data-testid="board-report" href="#/plant" className="text-sm font-semibold text-fs-primary underline">
          {strings['board.report']}
        </a>
      </div>
    </div>
  )
}

/** The side of the board: what to show for the field picked and the state of the call. */
function BoardSide({
  selectedFieldId,
  apiBase,
  service,
}: {
  selectedFieldId: string | null
  apiBase: string | null
  service: ServicePhase | null
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
    <Answered answer={service.answer.answer} />
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
}: {
  selectedFieldId: string | null
  state: PlantScreenState
  apiBase: string | null
  service: ServicePhase | null
  dispatch?: (action: PlantAction) => void
  map?: ReactNode
}) {
  return (
    <section aria-labelledby="board-title" className="mx-auto max-w-[110rem]">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <h2 id="board-title" className="text-4xl font-extrabold leading-tight">
            {strings['board.title']}
          </h2>
          <p className="mt-1 max-w-[70ch] text-fs-muted">{strings['plant.rule']}</p>
        </div>
        {exampleCase.example_data ? (
          <p data-testid="board-example" role="note" className="rounded-full border border-fs-warning bg-fs-warning-bg px-3 py-1 text-sm text-fs-warning">
            {strings['example.banner']}
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        <BoardControls
          marginOf={state.marginOf}
          strictness={state.strictness}
          rain={state.rain && REQUEST_READ.rain.kind === 'present'}
          rainFactor={REQUEST_READ.rain.kind === 'present' ? REQUEST_READ.rain.factor : null}
          onMarginOf={(value) => dispatch({ type: 'margin_of', value })}
          onStrictness={(value) => dispatch({ type: 'strictness', value })}
          onRain={(on) => dispatch({ type: 'rain', on })}
        />
      </div>

      <div className="mt-4 grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="lg:sticky lg:top-4">
          <h3 className="mb-2 text-xl font-bold">{strings['map.title']}</h3>
          {map}
          <FieldList fields={exampleCase.fields} selectedFieldId={selectedFieldId} />
        </div>
        <div className="min-w-0">
          <BoardSide selectedFieldId={selectedFieldId} apiBase={apiBase} service={service} />
        </div>
      </div>

      <p data-testid="board-disclaimer" className="mt-6 text-xs text-fs-muted">
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
  const asks = apiBase !== null && selectedFieldId === REQUEST_FIELD_ID
  const request = useMemo(
    () => (asks ? serviceRequestOf(state) : null),
    [asks, state.mode, state.strictness, state.marginOf, state.rain],
  )
  const query = useQuery(
    plantScreenQueryOptions(apiBase, request),
    apiBase === null ? NO_SERVICE_CLIENT : undefined,
  )
  return (
    <BoardView
      selectedFieldId={selectedFieldId}
      state={state}
      apiBase={apiBase}
      service={request === null ? null : servicePhaseOf(query)}
      dispatch={dispatch}
      map={<FieldsMap />}
    />
  )
}
