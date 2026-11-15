import { useState } from 'react'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
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
} from './plantData'
import type {
  PlantQuestions,
  AnswerKind,
  KindOfYear,
  LimitCheck,
  MarginOf,
  Measured,
  PlantAnswer,
  PlantAnswerSet,
  PlantOption,
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
function SoilLossLine({ kind, item }: { kind: MarginOf; item: SoilLossItem }) {
  const what = formatString(strings['plant.soil_loss_of'], { kind: kindLabel(kind) })
  return (
    <div>
      <MeasuredLine what={what} item={item} />
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

function CheckLine({ strictness, check }: { strictness: Strictness; check: LimitCheck }) {
  const label = strings[`plant.check.${strictness}`]
  if (check.verdict === 'not_resolved') {
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

function OptionBlock({ answer, option }: { answer: PlantAnswer; option: PlantOption }) {
  return (
    <article data-testid="plant-option" className="border-t border-slate-200 py-3">
      <p className="font-mono text-sm font-semibold">{option.rotation_id}</p>
      <p data-testid="plant-option-state" className="text-sm">
        {strings[`plant.state.${option.state}`]}
      </p>
      <MeasuredLine
        what={formatString(strings['plant.margin_of'], { kind: kindLabel(answer.margin_of) })}
        item={option.margin[answer.margin_of]}
      />
      <SoilLossLine kind="average" item={option.soil_loss.average} />
      {answer.margin_of !== 'average' ? (
        <SoilLossLine kind={answer.margin_of} item={option.soil_loss[answer.margin_of]} />
      ) : null}
      <CheckLine strictness={answer.strictness} check={option.limit_check} />
      {answer.strictness === 'every_kind' ? (
        <KindsLines option={option} />
      ) : null}
    </article>
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
  onStrictness?: (strictness: Strictness) => void
  onMarginOf?: (marginOf: MarginOf) => void
  onPrice?: (price: number) => void
}

function ignore() {}

type QuestionsProps = Omit<PlantViewProps, 'set'> & { answer: PlantAnswer | null }

function Questions({
  answer,
  strictness,
  marginOf,
  price,
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

      <fieldset data-testid="plant-q-rain">
        <legend className="font-semibold">{strings['plant.q.rain']}</legend>
        <label className="inline-flex items-center gap-1 text-sm text-slate-400">
          <input type="checkbox" disabled />
          {strings['plant.q.rain_control']}
        </label>
        <MissingLine
          what={strings['plant.q.rain_control']}
          missing={{ reason: 'NOT_AVAILABLE', detail: strings['plant.q.rain_unavailable_detail'] }}
        />
      </fieldset>

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
  const { set, strictness, marginOf, price } = props
  const answer = selectAnswer(set, strictness, marginOf)
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

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Questions answer={answer} {...props} />
        <div className="space-y-4 md:col-span-2">
          {answer === null ? (
            <MissingLine
              what={strings['plant.answer.missing_what']}
              missing={{ reason: 'NOT_AVAILABLE', detail: strings['plant.answer.missing_detail'] }}
            />
          ) : (
            <div className="space-y-4">
              <PriceAnswer answer={answer} price={price} />
              <AnswerCard answer={answer} />
              <section data-testid="plant-options" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <h3 className="text-base font-semibold">{strings['plant.options.heading']}</h3>
                {answer.options.map((option) => (
                  <OptionBlock key={option.rotation_id} answer={answer} option={option} />
                ))}
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

/** The screen at #/plant, on the example answers, with the questions in its state. */
export default function PlantScreen() {
  // One state for the three questions: selecting another answer (how strict,
  // the kind of year) resets the price looked at to that answer's price of
  // today, inside its range (selectQuestions).
  const [questions, setQuestions] = useState<PlantQuestions>(() =>
    selectQuestions(plantExamples, FIRST_STRICTNESS, FIRST_MARGIN_OF),
  )
  return (
    <PlantView
      set={plantExamples}
      strictness={questions.strictness}
      marginOf={questions.marginOf}
      price={questions.price}
      onStrictness={(strictness) =>
        setQuestions((q) => selectQuestions(plantExamples, strictness, q.marginOf))
      }
      onMarginOf={(marginOf) =>
        setQuestions((q) => selectQuestions(plantExamples, q.strictness, marginOf))
      }
      onPrice={(price) => setQuestions((q) => ({ ...q, price }))}
    />
  )
}
