import { useMemo, useReducer } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import rawPlantRequest from '../data/PLACEHOLDER_plant_request.json'
import { ApiError } from '../seam/runRotationApi'
import type { ApiErrorCode } from '../seam/runRotationApi'
import type { ProvenanceLabel } from '../components/ValueDisplay'
import {
  configuredApiBase,
  declaredRainFactor,
  plantQueryOptions,
  plantRequestFor,
} from './plantRoute'
import type { DeclaredFactor, PlantServiceAnswer } from './plantRoute'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import type { RotationDefinition } from '../rotation/exampleRotation'
import { barScale, drawnSoilVerdict } from './optionBars'
import { MarginBar, SoilLossBar, StripBlock } from './PlantOptionParts'
import { buildRotationStrip, cropOrder, plantRotations } from './rotationStrip'
import type { PlantRotations, RotationStrip } from './rotationStrip'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import {
  KINDS_OF_YEAR,
  MARGINS_OF,
  STRICTNESSES,
  answerAtPrice,
  plantExamples,
  selectAnswer,
  selectQuestions,
  startPrice,
} from './plantData'
import type {
  AnswerKind,
  KindOfYear,
  LimitCheck,
  MarginOf,
  Measured,
  PlantAnswer,
  PlantAnswerSet,
  PlantOption,
  RainStressPart,
  SoilLossItem,
  Strictness,
  TippingPoint,
  TippingPrice,
} from './plantData'

/**
 * The screen "What should I plant?" (S-019, PROPOSED), at hash route #/plant.
 *
 * Four questions on one side (the soybean price, the kind of year, heavier
 * rain, how strict); on the other, the answer at the price of today (the
 * chosen rotation with its margin, its soil loss against the limit and its
 * margin in each kind of year, or "none meets" / "not resolved" with the
 * reason), what meeting the limit costs, the tipping price with its distance
 * from the price of today, the answer at the price looked at, and the state
 * of each option in plain words.
 *
 * The screen computes nothing. The kind of year and how strict select one of
 * the example answers (plantData.ts says where they come from: every number
 * is example data). The price slider moves inside the answer's price range:
 * at the price of today the answer is shown; past a tipping point the screen
 * shows that point's answer_after and takes_over, as the tipping price
 * function computed them, and says that further changes are not computed;
 * a direction whose tipping point is missing for another reason says so.
 * Heavier rain needs the service (S-021): without a backend the control is
 * disabled and the stress test is not available, with its reason.
 *
 * Ask the service (S-021, PROPOSED). When a backend address is configured
 * (VITE_API_URL set and not blank, plantRoute.ts), the screen still opens on
 * the saved example answers and also offers "Ask the service": the example
 * plant request, with the questions chosen (how strict, the kind of year,
 * heavier rain on or off), goes to POST /api/plant/run, one call per distinct
 * request (cached, no retry, no refetch on focus). In that mode heavier rain
 * is an enabled checkbox that sends the example request's own declared
 * factor, shown with its unit and its provenance; the answer's rain-stress
 * part is shown. While the call is on its way a pending line, and when it
 * fails an error panel with its code in plain words, are shown in place of an
 * answer: no example answer is rendered then. "Back to the saved example"
 * goes back. A line says where the answer shown comes from.
 *
 * Each option is a row (S-020, PROPOSED): its rotation label from the
 * definition in the request, the strip of its crops year by year
 * (rotationStrip.ts), a margin bar and a soil-loss bar with the limit line
 * (widths only, optionBars.ts), and its state in plain words from the fields
 * the answer carries.
 *
 * A missing value shows its reason, never 0 or a blank. All wording lives in
 * strings.ts; rotation ids and the details of the answer render as data.
 */

/** "Price looked at" and the rest of the screen agree on one number form. */
function num(value: number): string {
  return displayNumber(value)
}

function kindLabel(kind: MarginOf): string {
  return strings[`plant.kind.${kind}`]
}

function kindsText(kinds: KindOfYear[]): string {
  return kinds.length === 0 ? strings['plant.kinds.none'] : kinds.map(kindLabel).join(', ')
}

function afterText(answer: AnswerKind, takesOver: string | null): string {
  if (answer === 'chosen' && takesOver !== null) {
    return formatString(strings['plant.after.chosen'], { rotation: takesOver })
  }
  return strings[`plant.after.${answer === 'chosen' ? 'not_resolved' : answer}`]
}

function MissingLine({ what, missing }: { what: string; missing: MissingPart }) {
  return (
    <p data-testid="plant-missing" className="text-sm italic text-slate-500">
      {missingPatternText(what, missing)}
    </p>
  )
}

/** One measured value: "{what}: {value} {unit}", or the missing pattern with its reason. */
function MeasuredLine({ what, item }: { what: string; item: Measured }) {
  if (item.missing !== null) {
    return <MissingLine what={what} missing={item.missing} />
  }
  return (
    <p data-testid="plant-value" className="text-sm" title={String(item.value)}>
      {formatString(strings['plant.value_line'], { what, value: num(item.value), unit: item.unit })}
    </p>
  )
}

/** A soil-loss mean, with its sources or the assumption mark (C4.2). */
function SoilLossLine({
  kind,
  item,
  bar = null,
}: {
  kind: MarginOf
  item: SoilLossItem
  /** The soil-loss bar of an option row (S-020), drawn under the value line. */
  bar?: ReactNode
}) {
  const what = formatString(strings['plant.soil_loss_of'], { kind: kindLabel(kind) })
  return (
    <div>
      <MeasuredLine what={what} item={item} />
      {bar}
      {item.value !== null && item.sources.length !== 0 ? (
        <p className="text-xs text-slate-500">
          {formatString(strings['value.source'], { source: item.sources.join('; ') })}
        </p>
      ) : null}
      {item.value !== null && item.assumption ? (
        <p className="text-xs text-slate-500">{strings['assumption.mark']}</p>
      ) : null}
    </div>
  )
}

/** The mark of a value the user declares in the request (C4.2): its source. */
function DeclaredMark({ testid }: { testid: string }) {
  return (
    <p data-testid={testid} className="text-xs text-slate-500">
      {strings['plant.declared']}
    </p>
  )
}

function LimitLine({ option }: { option: PlantOption }) {
  if (option.limit === null) {
    // The parser keeps a reason on the check whenever the limit is missing.
    return <MissingLine what={strings['plant.limit']} missing={option.on_average.missing!} />
  }
  return (
    <div>
      <MeasuredLine
        what={strings['plant.limit']}
        item={{ value: option.limit, unit: option.limit_unit, missing: null }}
      />
      <DeclaredMark testid="plant-limit-declared" />
    </div>
  )
}

function CheckLine({
  strictness,
  check,
  reasonShown = false,
}: {
  strictness: Strictness
  check: LimitCheck
  /**
   * True when the row already shows the reason of this check (an option not
   * resolved: its state detail says why), so the line names the check and
   * its verdict only and the reason is shown once (fix round 1 of S-020).
   */
  reasonShown?: boolean
}) {
  const label = strings[`plant.check.${strictness}`]
  if (check.verdict === 'not_resolved' && !reasonShown) {
    return <MissingLine what={label} missing={check.missing!} />
  }
  return (
    <p data-testid="plant-check" className="text-sm">
      {formatString(strings['plant.check_line'], {
        check: label,
        verdict: strings[`plant.verdict.${check.verdict}`],
      })}
    </p>
  )
}

/** The kinds lists of the every-kind check, with the kinds not in the record beside it. */
function KindsLines({ option }: { option: PlantOption }) {
  return (
    <div className="text-xs text-slate-600">
      <p>{formatString(strings['plant.kinds.not_met'], { kinds: kindsText(option.kinds_not_met) })}</p>
      <p>
        {formatString(strings['plant.kinds.not_resolved'], {
          kinds: kindsText(option.kinds_not_resolved),
        })}
      </p>
      <p data-testid="plant-kinds-not-in-record">
        {formatString(strings['plant.kinds.not_in_record'], {
          kinds: kindsText(option.kinds_not_in_record),
        })}
      </p>
    </div>
  )
}

function EconomicsSource() {
  return (
    <p className="text-xs text-slate-500">
      {formatString(strings['value.source'], { source: strings['plant.source.economics'] })}
    </p>
  )
}

function TippingLine({ label, point }: { label: string; point: TippingPoint }) {
  if (point.price === null) {
    return <MissingLine what={label} missing={point.missing} />
  }
  return (
    <div data-testid="plant-tipping-point" className="text-sm">
      <p>
        <span className="font-medium">{label}</span>{' '}
        <span>
          {formatString(strings['plant.tip.point'], {
            price: num(point.price),
            unit: point.unit,
            after: afterText(point.answer_after, point.takes_over),
          })}
        </span>
      </p>
      {point.distance_percent !== null ? (
        <p>{formatString(strings['plant.tip.distance'], { distance: num(point.distance_percent) })}</p>
      ) : (
        <MissingLine what={strings['plant.tip.distance_what']} missing={point.distance_missing!} />
      )}
    </div>
  )
}

function TippingBlock({ tipping }: { tipping: TippingPrice }) {
  return (
    <div className="mt-3">
      <h4 className="text-sm font-semibold">{strings['plant.tip.heading']}</h4>
      <TippingLine label={strings['plant.tip.up']} point={tipping.up} />
      <TippingLine label={strings['plant.tip.down']} point={tipping.down} />
    </div>
  )
}

function CostBlock({ answer }: { answer: PlantAnswer }) {
  const cost = answer.limit_cost
  return (
    <div className="mt-3">
      <h4 className="text-sm font-semibold">{strings['plant.cost.heading']}</h4>
      {cost.kind === 'value' ? (
        <p className="text-sm">
          {formatString(strings['plant.cost.value'], {
            value: num(cost.value),
            unit: cost.unit,
            against: cost.against,
          })}
        </p>
      ) : cost.kind === 'nothing' ? (
        <p className="text-sm">{strings['plant.cost.nothing']}</p>
      ) : (
        <MissingLine what={strings['plant.cost.what']} missing={cost.missing} />
      )}
    </div>
  )
}

/** The answer at the price of today: the chosen rotation, or none / not resolved with the reason. */
function AnswerCard({ answer }: { answer: PlantAnswer }) {
  const chosen = answer.options.find((o) => o.rotation_id === answer.chosen) ?? null
  return (
    <article
      data-testid="plant-card"
      className="rounded-lg border-2 border-teal-700 bg-white px-4 py-3"
    >
      <h3 className="text-xs font-semibold uppercase text-slate-500">{strings['plant.answer.heading']}</h3>
      {chosen !== null ? (
        <div>
          <p className="text-sm text-slate-600">{strings['plant.answer.chosen']}</p>
          <p data-testid="plant-chosen" className="font-mono text-lg font-semibold">
            {chosen.rotation_id}
          </p>
          <MeasuredLine
            what={formatString(strings['plant.margin_of'], { kind: kindLabel(answer.margin_of) })}
            item={chosen.margin[answer.margin_of]}
          />
          <SoilLossLine kind="average" item={chosen.soil_loss.average} />
          {answer.margin_of !== 'average' ? (
            <SoilLossLine kind={answer.margin_of} item={chosen.soil_loss[answer.margin_of]} />
          ) : null}
          <LimitLine option={chosen} />
          <CheckLine strictness={answer.strictness} check={chosen.limit_check} />
          {answer.strictness === 'every_kind' ? (
            <KindsLines option={chosen} />
          ) : null}
          <h4 className="mt-3 text-sm font-semibold">{strings['plant.by_kind']}</h4>
          {KINDS_OF_YEAR.map((kind) => (
            <MeasuredLine key={kind} what={kindLabel(kind)} item={chosen.margin[kind]} />
          ))}
        </div>
      ) : (
        <div>
          <p data-testid="plant-not-chosen" className="text-lg font-semibold">
            {strings[`plant.answer.${answer.answer === 'none_meets' ? 'none_meets' : 'not_resolved'}`]}
          </p>
          {answer.missing !== null ? (
            <MissingLine what={strings['plant.answer.why']} missing={answer.missing} />
          ) : null}
          {answer.tied.length !== 0 ? (
            <p className="text-sm">
              {formatString(strings['plant.answer.tied'], { rotations: answer.tied.join(', ') })}
            </p>
          ) : null}
        </div>
      )}
      <CostBlock answer={answer} />
      <TippingBlock tipping={answer.tipping_price} />
      <EconomicsSource />
    </article>
  )
}

/** What the answer says at the price looked at, as the tipping price function computed it. */
function PriceAnswer({ answer, price }: { answer: PlantAnswer; price: number | null }) {
  const tipping = answer.tipping_price
  // A price looked at that is not given is the price of today of this answer.
  const looked = price ?? tipping.today
  let content
  if (looked === null) {
    // No price of today: the parser keeps the shared reason of the tipping
    // price then; without one nothing is claimed.
    content =
      tipping.missing !== null ? (
        <MissingLine what={strings['plant.q.price']} missing={tipping.missing} />
      ) : null
  } else {
    const at = answerAtPrice(tipping, looked)
    if (at.kind === 'today') {
      content = <p className="text-sm">{strings['plant.price.today']}</p>
    } else if (at.kind === 'same') {
      content = <p className="text-sm">{strings['plant.price.same']}</p>
    } else if (at.kind === 'past') {
      content = (
        <div>
          <p className="text-sm font-medium">
            {formatString(strings['plant.price.past'], {
              price: num(at.point.price),
              unit: at.point.unit,
              after: afterText(at.point.answer_after, at.point.takes_over),
            })}
          </p>
          {/* The tipping price shown here carries its source. */}
          <EconomicsSource />
        </div>
      )
    } else {
      content = (
        <MissingLine
          what={formatString(strings['plant.price.unknown_what'], { price: num(looked), unit: tipping.unit })}
          missing={at.missing}
        />
      )
    }
  }
  return (
    <div data-testid="plant-price-answer" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      {content}
    </div>
  )
}

/**
 * The state of an option in plain words (S-020, PROPOSED), from the fields
 * the answer carries: never a verdict recomputed. Meets (or chosen): in every
 * kind of year, or on average but not in the kinds the every-kind check
 * names, or the every-kind check not resolved with its reason; the kinds not
 * in the record beside it. Out: the check of the strictness used that failed,
 * and the kinds over the limit. Not resolved: its reason.
 */
function StateDetail({ answer, option }: { answer: PlantAnswer; option: PlantOption }) {
  const lines: string[] = []
  if (option.state === 'chosen' || option.state === 'meets') {
    const everyKind = option.every_kind
    if (everyKind.verdict === 'meets') {
      lines.push(strings['plant.state.every_kind_meets'])
    } else if (everyKind.verdict === 'does_not_meet') {
      lines.push(formatString(strings['plant.state.on_average_only'], { kinds: kindsText(option.kinds_not_met) }))
    } else if (everyKind.missing !== null) {
      lines.push(missingPatternText(strings['plant.check.every_kind'], everyKind.missing))
    }
    if (answer.strictness === 'on_average') {
      // Under every kind of year the kinds lines of the row already name them.
      lines.push(
        formatString(strings['plant.kinds.not_in_record'], { kinds: kindsText(option.kinds_not_in_record) }),
      )
    }
  } else if (option.state === 'does_not_meet') {
    lines.push(formatString(strings['plant.state.out_by'], { check: strings[`plant.check.${answer.strictness}`] }))
    // Under every kind of year the kinds lines of the row already name them.
    if (answer.strictness === 'on_average' && option.kinds_not_met.length !== 0) {
      lines.push(formatString(strings['plant.kinds.not_met'], { kinds: kindsText(option.kinds_not_met) }))
    }
  } else if (option.limit_check.missing !== null) {
    lines.push(missingPatternText(strings['plant.state.why'], option.limit_check.missing))
  }
  return (
    <div data-testid="plant-option-state-detail" className="text-xs text-slate-600">
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  )
}

/** The scales of the bars of the options shown: one per bar kind, shared by the rows. */
interface BarScales {
  margin: number | null
  soilLoss: number | null
}

function barScales(answer: PlantAnswer): BarScales {
  const kind = answer.margin_of
  return {
    margin: barScale(answer.options.map((o) => o.margin[kind].value)),
    soilLoss: barScale([
      ...answer.options.map((o) => o.soil_loss[kind].value),
      ...answer.options.map((o) => o.limit),
    ]),
  }
}

function OptionBlock({
  answer,
  option,
  rotation,
  strip,
  stripMissing,
  order,
  scales,
}: {
  answer: PlantAnswer
  option: PlantOption
  rotation: RotationDefinition | null
  strip: RotationStrip | null
  stripMissing: MissingPart | null
  order: readonly string[]
  scales: BarScales
}) {
  const margin = option.margin[answer.margin_of]
  const loss = option.soil_loss[answer.margin_of]
  // The bar says what the answer says of the quantity it draws (PROPOSED,
  // drawnSoilVerdict); its verdict is in text unless the check line of the
  // row is the check of that same quantity (the average, on average).
  const lossBar =
    loss.value !== null && scales.soilLoss !== null ? (
      <SoilLossBar
        value={loss.value}
        scale={scales.soilLoss}
        limit={option.limit}
        what={formatString(strings['plant.soil_loss_of'], { kind: kindLabel(answer.margin_of) })}
        drawn={drawnSoilVerdict(option, answer.margin_of)}
        verdictInText={!(answer.margin_of === 'average' && answer.strictness === 'on_average')}
        limitMissing={option.limit === null ? option.on_average.missing : null}
      />
    ) : null
  return (
    <article data-testid="plant-option" className="border-t border-slate-200 py-3">
      {rotation !== null ? (
        <h4 data-testid="plant-option-label" className="text-sm font-semibold">
          {rotation.label}
        </h4>
      ) : null}
      <p className="font-mono text-sm font-semibold">{option.rotation_id}</p>
      <p data-testid="plant-option-state" className="text-sm">
        {strings[`plant.state.${option.state}`]}
      </p>
      <StateDetail answer={answer} option={option} />
      <StripBlock strip={strip} order={order} missing={stripMissing} />
      <MeasuredLine
        what={formatString(strings['plant.margin_of'], { kind: kindLabel(answer.margin_of) })}
        item={margin}
      />
      {margin.value !== null && scales.margin !== null ? (
        <MarginBar value={margin.value} scale={scales.margin} />
      ) : null}
      <SoilLossLine
        kind="average"
        item={option.soil_loss.average}
        bar={answer.margin_of === 'average' ? lossBar : null}
      />
      {answer.margin_of !== 'average' ? (
        <SoilLossLine kind={answer.margin_of} item={loss} bar={lossBar} />
      ) : null}
      <CheckLine
        strictness={answer.strictness}
        check={option.limit_check}
        reasonShown={option.state === 'not_resolved' && option.limit_check.missing !== null}
      />
      {answer.strictness === 'every_kind' ? (
        <KindsLines option={option} />
      ) : null}
    </article>
  )
}

/** The rotations of the request as a typed read: a list given directly is read as present. */
function asPlantRotations(rotations: RotationDefinition[] | PlantRotations): PlantRotations {
  return Array.isArray(rotations) ? { rotations, missing: null } : rotations
}

/**
 * The rows of the options (S-020): each with the strip of its definition in
 * the request, or the strip not available, with its reason, when the request
 * has none or cannot be read; the crop colours by order of first appearance
 * across the rows; the bar scales shared by the rows. Built once per answer
 * and rotations (useMemo), not at each step of the price slider.
 */
function OptionRows({
  answer,
  rotations,
}: {
  answer: PlantAnswer
  rotations: RotationDefinition[] | PlantRotations
}) {
  const { rows, order, scales } = useMemo(() => {
    const read = asPlantRotations(rotations)
    const built = answer.options.map((option) => {
      const rotation = read.rotations?.find((r) => r.rotation_id === option.rotation_id) ?? null
      return {
        option,
        rotation,
        strip: rotation !== null ? buildRotationStrip(rotation) : null,
        // null: the request holds no definition of it (StripBlock says so).
        stripMissing: read.missing,
      }
    })
    return {
      rows: built,
      order: cropOrder(built.flatMap((row) => (row.strip !== null ? [row.strip] : []))),
      scales: barScales(answer),
    }
  }, [answer, rotations])
  return (
    <>
      {rows.map(({ option, rotation, strip, stripMissing }) => (
        <OptionBlock
          key={option.rotation_id}
          answer={answer}
          option={option}
          rotation={rotation}
          strip={strip}
          stripMissing={stripMissing}
          order={order}
          scales={scales}
        />
      ))}
    </>
  )
}

function Sources({ answer }: { answer: PlantAnswer }) {
  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold">{strings['plant.sources.heading']}</h3>
      <ul className="text-xs text-slate-500">
        {answer.sources.map((source) => (
          <li key={source.id} data-testid="plant-source">
            {source.state === 'unavailable' && source.missing_reason !== null ? (
              <p>
                {missingPatternText(
                  source.id,
                  source.detail !== null
                    ? { reason: source.missing_reason, detail: source.detail }
                    : { reason: source.missing_reason },
                )}
              </p>
            ) : (
              <p>
                {source.detail !== null
                  ? formatString(strings['plant.source_line'], { id: source.id, detail: source.detail })
                  : source.id}
              </p>
            )}
            {source.attribution !== null ? (
              <p data-testid="plant-source-attribution">
                {formatString(strings['plant.source.attribution'], { attribution: source.attribution })}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export interface PlantViewProps {
  set: PlantAnswerSet
  strictness: Strictness
  marginOf: MarginOf
  /** The soybean price looked at; null when the answer has no price of today. */
  price: number | null
  /**
   * The rotation definitions of the request (S-020), or the typed read of
   * them (readPlantRotations), which may be missing with its reason; the
   * example request's by default.
   */
  rotations?: RotationDefinition[] | PlantRotations
  onStrictness?: (strictness: Strictness) => void
  onMarginOf?: (marginOf: MarginOf) => void
  onPrice?: (price: number) => void
  /** The heavier-rain control (S-021); unavailable, with its reason, by default. */
  rain?: RainControl
  /** Where the answer shown comes from (S-021); the saved example answers by default. */
  origin?: AnswerOrigin
  /** Given when a backend is configured, in example mode: the "Ask the service" button. */
  onAskService?: () => void
  /** Given in service mode: the "Back to the saved example" button. */
  onBackToExample?: () => void
  /** In service mode, a call on its way or failed: shown in place of an answer. */
  status?: ServiceStatus
  /** The rain-stress part of a service answer (S-021), shown beside it. */
  rainStress?: RainStressPart | null
}

/** The heavier-rain control: unavailable without the service, or the factor the request declares. */
export type RainControl =
  | { kind: 'unavailable' }
  | { kind: 'no_factor' }
  | { kind: 'available'; on: boolean; factor: DeclaredFactor; onRain?: (on: boolean) => void }

const RAIN_UNAVAILABLE: RainControl = { kind: 'unavailable' }

/** Where the answer shown comes from. */
export type AnswerOrigin = { kind: 'example' } | { kind: 'service'; api: string }

const ORIGIN_EXAMPLE: AnswerOrigin = { kind: 'example' }

/** A service call without an answer to show. */
export type ServiceStatus = { kind: 'pending' } | { kind: 'failed'; code: ApiErrorCode }

function ignore() {}

/** The line that says where the answer comes from, with the button that switches. */
function OriginLine({
  origin,
  onAskService,
  onBackToExample,
}: {
  origin: AnswerOrigin
  onAskService?: () => void
  onBackToExample?: () => void
}) {
  return (
    <div data-testid="plant-origin" className="mt-3 flex flex-wrap items-center gap-3">
      <p className="text-sm text-slate-600">
        {origin.kind === 'service'
          ? formatString(strings['plant.service.origin_service'], { api: origin.api })
          : strings['plant.service.origin_example']}
      </p>
      {onAskService !== undefined ? (
        <button
          type="button"
          data-testid="plant-service-ask"
          className="rounded border border-teal-700 px-3 py-1 text-sm font-medium text-teal-800"
          onClick={onAskService}
        >
          {strings['plant.service.ask']}
        </button>
      ) : null}
      {onBackToExample !== undefined ? (
        <button
          type="button"
          data-testid="plant-service-back"
          className="rounded border border-slate-400 px-3 py-1 text-sm font-medium text-slate-700"
          onClick={onBackToExample}
        >
          {strings['plant.service.back']}
        </button>
      ) : null}
    </div>
  )
}

/** The pending line, or the error panel with the code in plain words and the raw code. */
function StatusPanel({ status }: { status: ServiceStatus }) {
  if (status.kind === 'pending') {
    return (
      <p data-testid="plant-service-pending" className="text-sm text-slate-500">
        {strings['plant.service.pending']}
      </p>
    )
  }
  return (
    <div
      data-testid="plant-service-error"
      role="alert"
      className="rounded-lg border border-red-300 bg-red-50 px-4 py-3"
    >
      <h3 className="text-sm font-semibold text-red-800">{strings['plant.service.error_heading']}</h3>
      <p className="text-sm text-red-700">{strings[`plant.service.error.${status.code}`]}</p>
      <p data-testid="plant-service-error-code" className="text-xs text-slate-500">
        {formatString(strings['api.code.shown'], { code: status.code })}
      </p>
    </div>
  )
}

/** The rain-stress part of a service answer: applied or not with its detail, or missing with its reason. */
function RainStressBlock({ part }: { part: RainStressPart }) {
  return (
    <div data-testid="plant-rain-stress" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      {part.kind === 'applied' ? (
        <p className="text-sm">
          {formatString(strings[part.applied ? 'plant.service.rain_applied' : 'plant.service.rain_not_applied'], {
            label: part.label,
            detail: part.detail,
          })}
        </p>
      ) : (
        <div>
          <MissingLine
            what={formatString(strings['plant.service.rain_what'], { label: part.label })}
            missing={part.missing}
          />
          <p className="text-xs text-slate-500">{part.detail}</p>
        </div>
      )}
    </div>
  )
}

type QuestionsProps = Omit<PlantViewProps, 'set'> & { answer: PlantAnswer | null }

const PROVENANCE_LABELS: readonly ProvenanceLabel[] = ['DECLARED', 'OBSERVED', 'DERIVED', 'SIMULATED']

/** The provenance label of a factor in words; an unknown label renders as data. */
function provenanceText(provenance: string): string {
  return (PROVENANCE_LABELS as readonly string[]).includes(provenance)
    ? strings[`provenance.${provenance as ProvenanceLabel}`]
    : provenance
}

/**
 * The heavier-rain question (S-021): disabled with its reason without the
 * service (as before S-021) or when the request declares no factor; in
 * service mode an enabled checkbox, and when on, the factor it sends as the
 * request declares it, with its unit, provenance and the declared mark.
 */
function RainQuestion({ rain }: { rain: RainControl }) {
  return (
    <fieldset data-testid="plant-q-rain">
      <legend className="font-semibold">{strings['plant.q.rain']}</legend>
      {rain.kind === 'available' ? (
        <div>
          <label className="inline-flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={rain.on}
              onChange={(event) => (rain.onRain ?? ignore)(event.target.checked)}
            />
            {strings['plant.q.rain_control']}
          </label>
          {rain.on ? (
            <div>
              <p data-testid="plant-rain-factor" className="text-sm">
                {formatString(strings['plant.service.rain_factor'], {
                  value: num(rain.factor.value),
                  unit: rain.factor.unit,
                  provenance: provenanceText(rain.factor.provenance),
                })}
              </p>
              <DeclaredMark testid="plant-rain-declared" />
            </div>
          ) : null}
        </div>
      ) : (
        <div>
          <label className="inline-flex items-center gap-1 text-sm text-slate-400">
            <input type="checkbox" disabled />
            {strings['plant.q.rain_control']}
          </label>
          <MissingLine
            what={strings['plant.q.rain_control']}
            missing={
              rain.kind === 'no_factor'
                ? { reason: 'NOT_DECLARED', detail: strings['plant.service.rain_no_factor_detail'] }
                : { reason: 'NOT_AVAILABLE', detail: strings['plant.q.rain_unavailable_detail'] }
            }
          />
        </div>
      )}
    </fieldset>
  )
}

function Questions({
  answer,
  strictness,
  marginOf,
  price,
  rain = RAIN_UNAVAILABLE,
  onStrictness = ignore,
  onMarginOf = ignore,
  onPrice = ignore,
}: QuestionsProps) {
  const tipping = answer?.tipping_price ?? null
  const usable = tipping !== null && tipping.today !== null && price !== null
  return (
    <section className="space-y-5 rounded-lg border border-slate-200 bg-white px-4 py-4">
      <h3 className="text-base font-semibold">{strings['plant.questions']}</h3>

      <div data-testid="plant-q-price">
        <label htmlFor="plant-price" className="font-semibold">
          {strings['plant.q.price']}
        </label>
        {usable ? (
          <div>
            <p className="text-sm">
              {formatString(strings['plant.q.price_looked_at'], { price: num(price), unit: tipping.unit })}
            </p>
            <input
              id="plant-price"
              type="range"
              className="w-full"
              min={tipping.low}
              max={tipping.high}
              step="any"
              value={price}
              onChange={(event) => onPrice(Number(event.target.value))}
            />
            <p className="text-xs text-slate-500">
              {formatString(strings['plant.q.price_range'], {
                low: num(tipping.low),
                high: num(tipping.high),
                unit: tipping.unit,
              })}
            </p>
            <p className="text-xs text-slate-500">
              {formatString(strings['plant.q.price_today'], { price: num(tipping.today!), unit: tipping.unit })}
            </p>
            {/* Today's price and the range are declared by the user; the
                tipping prices carry the economics source in the card. */}
            <DeclaredMark testid="plant-price-declared" />
          </div>
        ) : (
          <input id="plant-price" type="range" className="w-full" disabled />
        )}
        <p className="text-xs text-slate-500">{strings['plant.q.price_hint']}</p>
      </div>

      <fieldset data-testid="plant-q-kind">
        <legend className="font-semibold">{strings['plant.q.kind']}</legend>
        {MARGINS_OF.map((kind) => (
          <label key={kind} className="mr-3 inline-flex items-center gap-1 text-sm">
            <input
              type="radio"
              name="plant-kind"
              value={kind}
              checked={kind === marginOf}
              onChange={() => onMarginOf(kind)}
            />
            {kindLabel(kind)}
          </label>
        ))}
      </fieldset>

      <RainQuestion rain={rain} />

      <fieldset data-testid="plant-q-strict">
        <legend className="font-semibold">{strings['plant.q.strict']}</legend>
        {STRICTNESSES.map((value) => (
          <label key={value} className="mr-3 inline-flex items-center gap-1 text-sm">
            <input
              type="radio"
              name="plant-strict"
              value={value}
              checked={value === strictness}
              onChange={() => onStrictness(value)}
            />
            {strings[`plant.strict.${value}`]}
          </label>
        ))}
      </fieldset>
    </section>
  )
}

/** The screen for given questions: a pure function of the answers and the questions asked. */
export function PlantView(props: PlantViewProps) {
  const {
    set,
    strictness,
    marginOf,
    price,
    rotations = plantRotations,
    origin = ORIGIN_EXAMPLE,
    onAskService,
    onBackToExample,
    status,
    rainStress = null,
  } = props
  const answer = status === undefined ? selectAnswer(set, strictness, marginOf) : null
  return (
    <section aria-labelledby="plant-title" className="mx-auto max-w-5xl">
      <h2 id="plant-title" className="text-2xl font-semibold">
        {strings['plant.title']}
      </h2>
      <p className="mt-1 text-sm text-slate-600">{strings['plant.rule']}</p>

      {set.example_data ? (
        <div role="note" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <p data-testid="plant-example-banner" className="text-sm text-amber-900">
            {strings['example.banner']}
          </p>
        </div>
      ) : null}

      <OriginLine origin={origin} onAskService={onAskService} onBackToExample={onBackToExample} />

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Questions answer={answer} {...props} />
        <div className="space-y-4 md:col-span-2">
          {status !== undefined ? (
            <StatusPanel status={status} />
          ) : answer === null ? (
            <MissingLine
              what={strings['plant.answer.missing_what']}
              missing={{ reason: 'NOT_AVAILABLE', detail: strings['plant.answer.missing_detail'] }}
            />
          ) : (
            <div className="space-y-4">
              <PriceAnswer answer={answer} price={price} />
              {rainStress !== null ? (
                <RainStressBlock part={rainStress} />
              ) : null}
              <AnswerCard answer={answer} />
              <section data-testid="plant-options" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <h3 className="text-base font-semibold">{strings['plant.options.heading']}</h3>
                <OptionRows answer={answer} rotations={rotations} />
                <EconomicsSource />
              </section>
              <Sources answer={answer} />
            </div>
          )}
        </div>
      </div>

      <p data-testid="plant-disclaimer" className="mt-6 text-xs text-slate-500">
        {strings['disclaimer.full']}
      </p>
    </section>
  )
}

/** The first questions: the contract example's (on average, average of the record), at the price of today. */
const FIRST_STRICTNESS: Strictness = 'on_average'
const FIRST_MARGIN_OF: MarginOf = 'average'

/**
 * The state of the screen (S-021, PROPOSED): the mode (the saved example
 * answers, or the service), the questions chosen, and the price looked at.
 * In service mode the price belongs to the request it was moved on
 * (priceKey); an answer to another request starts at its own price of today.
 */
export interface PlantScreenState {
  mode: 'example' | 'service'
  strictness: Strictness
  marginOf: MarginOf
  /** Heavier rain on: the request sends the example request's declared factor. */
  rain: boolean
  price: number | null
  /** The request the price was moved on, in service mode; null otherwise. */
  priceKey: string | null
}

export type PlantAction =
  | { type: 'ask' }
  | { type: 'back' }
  | { type: 'strictness'; value: Strictness }
  | { type: 'margin_of'; value: MarginOf }
  | { type: 'rain'; on: boolean }
  | { type: 'price'; price: number; key: string | null }

/**
 * The first state: the example answers, the questions of the contract
 * example, at the price of today; heavier rain off (PROPOSED: the stress
 * test is asked for, not assumed).
 */
export function initialPlantState(): PlantScreenState {
  const questions = selectQuestions(plantExamples, FIRST_STRICTNESS, FIRST_MARGIN_OF)
  return {
    mode: 'example',
    strictness: questions.strictness,
    marginOf: questions.marginOf,
    rain: false,
    price: questions.price,
    priceKey: null,
  }
}

/** The state with the example answer of these questions selected, at its price of today. */
function onExample(state: PlantScreenState, strictness: Strictness, marginOf: MarginOf): PlantScreenState {
  const questions = selectQuestions(plantExamples, strictness, marginOf)
  return { ...state, mode: 'example', strictness, marginOf, price: questions.price, priceKey: null }
}

/**
 * The transitions of the screen. Pure. In example mode, selecting another
 * answer resets the price looked at to that answer's price of today
 * (selectQuestions), as before S-021; in service mode the questions change
 * the request, and the price follows the answer to it.
 */
export function plantScreenReducer(state: PlantScreenState, action: PlantAction): PlantScreenState {
  switch (action.type) {
    case 'ask':
      return { ...state, mode: 'service', priceKey: null }
    case 'back':
      return onExample(state, state.strictness, state.marginOf)
    case 'strictness':
      return state.mode === 'example'
        ? onExample(state, action.value, state.marginOf)
        : { ...state, strictness: action.value }
    case 'margin_of':
      return state.mode === 'example'
        ? onExample(state, state.strictness, action.value)
        : { ...state, marginOf: action.value }
    case 'rain':
      return { ...state, rain: action.on }
    case 'price':
      return { ...state, price: action.price, priceKey: action.key }
  }
}

/** The request the screen sends: the example request with the questions chosen, in service mode only. */
export function serviceRequestOf(
  state: PlantScreenState,
  baseRequest: unknown = rawPlantRequest,
): Record<string, unknown> | null {
  if (state.mode !== 'service') {
    return null
  }
  return plantRequestFor(baseRequest, {
    strictness: state.strictness,
    marginOf: state.marginOf,
    rain: state.rain,
  })
}

/** The state of a service call, as the view renders it. */
export type ServicePhase =
  | { phase: 'pending' }
  | { phase: 'failed'; code: ApiErrorCode }
  | { phase: 'answered'; answer: PlantServiceAnswer }

/** The phase of the call, from the query. An error that is not an ApiError is UNEXPECTED. */
export function servicePhaseOf(query: {
  isPending: boolean
  isError: boolean
  error: unknown
  data: PlantServiceAnswer | undefined
}): ServicePhase {
  if (query.isError) {
    return { phase: 'failed', code: query.error instanceof ApiError ? query.error.code : 'UNEXPECTED' }
  }
  if (query.isPending || query.data === undefined) {
    return { phase: 'pending' }
  }
  return { phase: 'answered', answer: query.data }
}

/** The factor the example request declares (example data), or null. */
const DECLARED_FACTOR: DeclaredFactor | null = declaredRainFactor(rawPlantRequest)

/**
 * The screen for a state: a pure function of the state, the configured
 * backend (null: none) and, in service mode, the phase of the call.
 */
export function PlantScreenView({
  state,
  apiBase,
  service,
  dispatch = ignore,
}: {
  state: PlantScreenState
  apiBase: string | null
  service: ServicePhase | null
  dispatch?: (action: PlantAction) => void
}) {
  const handlers = {
    strictness: state.strictness,
    marginOf: state.marginOf,
    onStrictness: (value: Strictness) => dispatch({ type: 'strictness', value }),
    onMarginOf: (value: MarginOf) => dispatch({ type: 'margin_of', value }),
  }
  if (state.mode === 'example' || apiBase === null || service === null) {
    return (
      <PlantView
        set={plantExamples}
        price={state.price}
        onPrice={(price) => dispatch({ type: 'price', price, key: null })}
        onAskService={apiBase !== null ? () => dispatch({ type: 'ask' }) : undefined}
        {...handlers}
      />
    )
  }
  const key = JSON.stringify(serviceRequestOf(state))
  const rain: RainControl =
    DECLARED_FACTOR === null
      ? { kind: 'no_factor' }
      : {
          kind: 'available',
          on: state.rain,
          factor: DECLARED_FACTOR,
          onRain: (on) => dispatch({ type: 'rain', on }),
        }
  const common = {
    ...handlers,
    rain,
    origin: { kind: 'service', api: apiBase } as const,
    onBackToExample: () => dispatch({ type: 'back' }),
  }
  if (service.phase !== 'answered') {
    // No answer to show: the request itself says whether it is example data.
    const set: PlantAnswerSet = { example_data: rawPlantRequest.example_data, answers: [] }
    const status: ServiceStatus =
      service.phase === 'pending' ? { kind: 'pending' } : { kind: 'failed', code: service.code }
    return (
      <PlantView set={set} price={null} status={status} {...common} />
    )
  }
  const answer = service.answer.answer
  const set: PlantAnswerSet = { example_data: answer.example_data, answers: [answer] }
  return (
    <PlantView
      set={set}
      price={state.priceKey === key ? state.price : startPrice(answer)}
      onPrice={(price) => dispatch({ type: 'price', price, key })}
      rainStress={service.answer.rainStress}
      {...common}
    />
  )
}

/** Without a backend: the example answers only, nothing called. */
function PlantScreenWithoutService() {
  const [state, dispatch] = useReducer(plantScreenReducer, undefined, initialPlantState)
  return <PlantScreenView state={state} apiBase={null} service={null} dispatch={dispatch} />
}

/** With a backend: the example answers first, and the call of the route in service mode. */
function PlantScreenWithService({ apiBase }: { apiBase: string }) {
  const [state, dispatch] = useReducer(plantScreenReducer, undefined, initialPlantState)
  const request = serviceRequestOf(state)
  const query = useQuery({
    ...plantQueryOptions(apiBase, request ?? {}),
    enabled: request !== null,
  })
  return (
    <PlantScreenView
      state={state}
      apiBase={apiBase}
      service={request === null ? null : servicePhaseOf(query)}
      dispatch={dispatch}
    />
  )
}

/**
 * The screen at #/plant. The backend is the configured one (VITE_API_URL,
 * configuredApiBase) unless given: null means none, and the screen shows the
 * example answers only and calls nothing, as before S-021.
 */
export default function PlantScreen({ apiBase = configuredApiBase() }: { apiBase?: string | null }) {
  return apiBase === null ? <PlantScreenWithoutService /> : <PlantScreenWithService apiBase={apiBase} />
}
