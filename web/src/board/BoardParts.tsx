import type { ReactNode } from 'react'
import type { DeclaredFactor } from '../plant/plantRoute'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { MARGINS_OF, STRICTNESSES } from '../plant/plantData'
import { KINDS_OF_YEAR } from '../plant/plantData'
import type {
  KindOfYear,
  KindsOfYearRecord,
  MarginOf,
  Measured,
  PlantAnswer,
  RainStressPart,
  Strictness,
  TippingPrice,
} from '../plant/plantData'
import { priceTrack } from './boardModel'
import type { TrackSide } from './boardModel'

/**
 * The parts of the rotation board (PROPOSED, l3/board): the controls of the
 * questions, the banner of the answer and the price track. The options side
 * by side are in CompareTable.tsx.
 *
 * Display only. Every number is one the answer carries; a missing number is
 * a hatched track and "no value", never 0. Whether a soil loss is over the
 * limit is read from the answer (drawnSoilVerdict). Colour is never the only
 * carrier: a state is also a word, a soil loss over the limit says so.
 * Variants are styled through data attributes, so every class list stays a
 * plain attribute.
 */

// --- controls -------------------------------------------------------------------

/** A group of radio buttons drawn as one segmented control, on the dark bar. */
function Segmented({
  name,
  legend,
  labels,
  selected,
  onSelect,
}: {
  name: string
  legend: string
  /** The label of each choice, in order. */
  labels: string[]
  /** The index of the choice that is on. */
  selected: number
  onSelect: (index: number) => void
}) {
  return (
    <fieldset data-testid={name} className="min-w-0">
      <legend className="font-mono text-[10px] uppercase tracking-widest opacity-70">{legend}</legend>
      <div className="mt-1 inline-flex flex-wrap gap-1 rounded-lg bg-white/10 p-1">
        {labels.map((label, index) => (
          <label
            key={label}
            className="cursor-pointer rounded-md px-3 py-1 text-sm has-[:checked]:bg-fs-surface has-[:checked]:font-bold has-[:checked]:text-fs-text has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-white"
          >
            <input
              type="radio"
              className="sr-only"
              name={name}
              checked={index === selected}
              onChange={() => onSelect(index)}
            />
            {label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

/**
 * The label of a kind of year as a choice: with the number of agricultural
 * years of the record behind it, when the answer carries them. The average
 * is the mean over all the years of the record, weighted by those numbers.
 */
function kindChoiceLabel(kind: MarginOf, record: KindsOfYearRecord | null): string {
  const name = kind === 'average' ? strings['board.kind.average'] : strings[`plant.kind.${kind}`]
  if (record === null) {
    return name
  }
  const years = kind === 'average' ? record.years.length : record.counts[kind]
  return years === null ? name : formatString(strings['board.kind.years'], { kind: name, n: years })
}

/**
 * The bar of the questions: the kind of year, the limit rule and the rain.
 * The stress test of rain erosivity is offered only when the request
 * declares a factor to send, and names that factor.
 */
export function BoardControls({
  marginOf,
  strictness,
  rain,
  rainFactor,
  record,
  limit,
  onMarginOf,
  onStrictness,
  onRain,
}: {
  marginOf: MarginOf
  strictness: Strictness
  rain: boolean
  /** The factor the request declares for the stress test; null when it declares none to send. */
  rainFactor: DeclaredFactor | null
  /** The kinds of year of the record, once an answer carries them: the years behind each choice. */
  record: KindsOfYearRecord | null
  /** The soil-loss limit the request declares, with its unit; null when it declares none. */
  limit: { value: number; unit: string } | null
  onMarginOf: (value: MarginOf) => void
  onStrictness: (value: Strictness) => void
  onRain: (on: boolean) => void
}) {
  return (
    <div
      data-testid="board-controls"
      className="flex flex-wrap items-end gap-x-8 gap-y-3 rounded-2xl bg-fs-text px-5 py-3 text-fs-surface"
    >
      <Segmented
        name="board-kind"
        legend={strings['board.hud.year']}
        labels={MARGINS_OF.map((kind) => kindChoiceLabel(kind, record))}
        selected={MARGINS_OF.indexOf(marginOf)}
        onSelect={(index) => onMarginOf(MARGINS_OF[index])}
      />
      <Segmented
        name="board-rule"
        legend={strings['board.hud.rule']}
        labels={STRICTNESSES.map((value) =>
          limit !== null
            ? formatString(strings[`board.rule.${value}.limit`], { limit: displayNumber(limit.value), unit: limit.unit })
            : strings[`board.rule.${value}`],
        )}
        selected={STRICTNESSES.indexOf(strictness)}
        onSelect={(index) => onStrictness(STRICTNESSES[index])}
      />
      {rainFactor !== null ? (
        <Segmented
          name="board-rain"
          legend={strings['board.hud.rain']}
          labels={[
            strings['board.rain.recorded'],
            formatString(strings['board.rain.factor'], { factor: displayNumber(rainFactor.value) }),
          ]}
          selected={rain ? 1 : 0}
          onSelect={(index) => onRain(index === 1)}
        />
      ) : null}
    </div>
  )
}

// --- the answer -------------------------------------------------------------------

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div data-testid="board-tile" className="rounded-xl bg-white/10 px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-widest opacity-70">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  )
}

function TileNumber({ item }: { item: Measured }) {
  if (item.value === null) {
    return <p className="font-fs-heading text-xl font-bold italic opacity-70">{strings['plant.table.no_value']}</p>
  }
  return (
    <p className="tabular-nums" title={String(item.value)}>
      <span className="font-fs-heading text-3xl font-extrabold leading-none">{displayNumber(item.value)}</span>{' '}
      <span className="text-xs opacity-70">{item.unit}</span>
    </p>
  )
}

/**
 * The banner of the answer: the rotation chosen with its three headline
 * numbers (margin, soil loss against the limit, what meeting the limit
 * costs), or that none meets the limit or the data cannot pick one, with the
 * reason the answer gives.
 */
export function AnswerBanner({
  answer,
  label,
  showWhy,
  against = null,
}: {
  answer: PlantAnswer
  label: string | null
  /** False when a notice beside the banner already says what the answer lacks. */
  showWhy: boolean
  /** How the board names the rotation the cost is measured against; its id when not given. */
  against?: string | null
}) {
  const chosen = answer.options.find((option) => option.rotation_id === answer.chosen) ?? null
  const cost = answer.limit_cost
  return (
    <section
      data-testid="board-answer"
      data-answer={answer.answer}
      data-tone={answer.answer === 'chosen' ? 'chosen' : answer.answer === 'none_meets' ? 'over' : 'open'}
      className="rounded-2xl bg-fs-primary px-6 py-5 text-white data-[tone=open]:bg-fs-text data-[tone=over]:bg-fs-error"
    >
      {chosen !== null ? (
        <div>
          <p className="font-mono text-[11px] uppercase tracking-widest opacity-80">{strings['plant.answer.heading']}</p>
          <p data-testid="board-chosen" className="mt-1 font-fs-heading text-3xl font-extrabold leading-tight">
            {label ?? chosen.rotation_id}
          </p>
          <p data-testid="board-scope" className="mt-1 max-w-[80ch] text-sm opacity-90">
            {answer.scope}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Tile label={formatString(strings['plant.margin_of'], { kind: strings[`plant.kind.${answer.margin_of}`] })}>
              <TileNumber item={chosen.margin[answer.margin_of]} />
            </Tile>
            <Tile label={strings['plant.table.soil_loss']}>
              <TileNumber item={chosen.soil_loss[answer.margin_of]} />
              {chosen.limit !== null ? (
                <p data-testid="board-limit" className="text-xs opacity-80">
                  {formatString(strings['board.limit_is'], {
                    limit: displayNumber(chosen.limit),
                    unit: chosen.limit_unit,
                  })}
                </p>
              ) : null}
            </Tile>
            <Tile label={strings['plant.cost.what']}>
              {cost.kind === 'value' ? (
                <div>
                  <TileNumber item={{ value: cost.value, unit: cost.unit, missing: null, labels: cost.labels }} />
                  <p data-testid="board-cost-against" className="text-xs opacity-80">
                    {formatString(strings['board.cost.against'], { rotation: against ?? cost.against })}
                  </p>
                </div>
              ) : cost.kind === 'nothing' ? (
                <p className="font-fs-heading text-3xl font-extrabold leading-none">{strings['board.cost.none']}</p>
              ) : (
                <p className="font-fs-heading text-xl font-bold italic opacity-70">{strings['plant.table.no_value']}</p>
              )}
            </Tile>
          </div>
        </div>
      ) : (
        <div>
          <p data-testid="board-not-chosen" className="font-fs-heading text-3xl font-extrabold leading-tight">
            {strings[`plant.answer.${answer.answer === 'none_meets' ? 'none_meets' : 'not_resolved'}`]}
          </p>
          {showWhy && answer.missing !== null ? (
            <p data-testid="board-why" className="mt-2 max-w-[80ch] text-sm opacity-80">
              {missingPatternText(strings['plant.answer.why'], answer.missing)}
            </p>
          ) : null}
        </div>
      )}
    </section>
  )
}

// --- the price track ---------------------------------------------------------------

function sideText(side: TrackSide, tipping: TippingPrice, end: number): string {
  if (side.kind === 'tips') {
    return formatString(strings['board.price.tips'], {
      price: displayNumber(side.point.price),
      unit: tipping.unit,
    })
  }
  if (side.kind === 'unknown') {
    return strings['board.price.unknown']
  }
  return formatString(strings['board.price.holds_to'], { price: displayNumber(end), unit: tipping.unit })
}

/**
 * The soybean price as a track over the range the user declared: the price
 * of today, the stretch where the answer stays the one of today, and where
 * it changes. A stretch whose answer is not computed is hatched.
 */
export function PriceTrackPanel({ tipping }: { tipping: TippingPrice }) {
  const track = priceTrack(tipping)
  if (track === null) {
    const missing: MissingPart = tipping.missing ?? { reason: 'NOT_AVAILABLE' }
    return (
      <section data-testid="board-price" className="rounded-2xl border border-fs-border bg-fs-surface px-5 py-4">
        <h3 className="text-lg font-bold">{strings['board.price.title']}</h3>
        <p className="text-sm italic text-fs-muted">{missingPatternText(strings['board.price.title'], missing)}</p>
      </section>
    )
  }
  return (
    <section data-testid="board-price" className="rounded-2xl border border-fs-border bg-fs-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h3 className="text-lg font-bold">{strings['board.price.title']}</h3>
        <p className="text-sm text-fs-muted">
          {formatString(strings['plant.q.price_today'], { price: displayNumber(tipping.today!), unit: tipping.unit })}
        </p>
      </div>
      <div aria-hidden="true" className="relative mt-6 h-3 overflow-hidden rounded-full bg-fs-faint">
        <span
          data-side={track.down.kind}
          className="absolute inset-y-0 left-0 data-[side=tips]:bg-fs-warning data-[side=unknown]:fs-fog"
          style={{ width: `${track.holdsFrom}%` }}
        />
        <span
          data-side={track.up.kind}
          className="absolute inset-y-0 right-0 data-[side=tips]:bg-fs-warning data-[side=unknown]:fs-fog"
          style={{ width: `${100 - track.holdsTo}%` }}
        />
        <span
          data-testid="board-price-holds"
          className="absolute inset-y-0 bg-fs-primary"
          style={{ left: `${track.holdsFrom}%`, width: `${track.holdsTo - track.holdsFrom}%` }}
        />
      </div>
      <div aria-hidden="true" className="relative -mt-5 h-7">
        <span
          data-testid="board-price-today"
          className="absolute -top-2 h-7 w-1 -translate-x-1/2 rounded bg-fs-text"
          style={{ left: `${track.today}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[11px] text-fs-muted">
        <span>{displayNumber(tipping.low)}</span>
        <span>{displayNumber(tipping.high)}</span>
      </div>
      <ul className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <li data-testid="board-price-down" data-side={track.down.kind}>
          <span className="font-semibold">{strings['plant.tip.down']}</span>{' '}
          <span className="text-fs-muted">{sideText(track.down, tipping, tipping.low)}</span>
        </li>
        <li data-testid="board-price-up" data-side={track.up.kind}>
          <span className="font-semibold">{strings['plant.tip.up']}</span>{' '}
          <span className="text-fs-muted">{sideText(track.up, tipping, tipping.high)}</span>
        </li>
      </ul>
    </section>
  )
}

// --- the record, the rain echo, the limits of the answer ------------------------------

/** The tone a kind of year is drawn in: one word, so that a style can select it. */
function kindTone(kind: KindOfYear): string {
  return kind === 'el_nino' ? 'nino' : kind === 'la_nina' ? 'nina' : 'neutral'
}

/**
 * The record year by year: one cell per agricultural year, in the colour of
 * its kind, and the number of years of each kind. A year the record does not
 * classify is hatched. The past record, not a forecast.
 */
export function RecordRibbon({ record, marginOf }: { record: KindsOfYearRecord; marginOf: MarginOf }) {
  const first = record.years[0].ag_year
  const last = record.years[record.years.length - 1].ag_year
  return (
    <section data-testid="board-record" className="rounded-2xl border border-fs-border bg-fs-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h3 className="text-lg font-bold">{strings['board.record.title']}</h3>
        <p className="text-sm text-fs-muted">
          {formatString(strings['board.record.span'], { first, last, n: record.years.length })}
        </p>
      </div>
      <ol className="mt-3 flex gap-1">
        {record.years.map((year) => (
          <li
            key={year.ag_year}
            data-testid="board-record-year"
            data-tone={year.kind !== null ? kindTone(year.kind) : 'open'}
            data-dim={String(marginOf !== 'average' && year.kind !== marginOf)}
            title={year.kind !== null ? strings[`plant.kind.${year.kind}`] : strings['plant.table.no_value']}
            className="min-w-0 flex-1 data-[dim=true]:opacity-30"
          >
            <span
              data-tone={year.kind !== null ? kindTone(year.kind) : 'open'}
              className="block h-4 rounded-sm data-[tone=neutral]:bg-fs-neutral data-[tone=nina]:bg-fs-nina data-[tone=nino]:bg-fs-nino data-[tone=open]:fs-fog"
            />
            <span className="block text-center font-mono text-[9px] text-fs-muted">{year.ag_year}</span>
          </li>
        ))}
      </ol>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {KINDS_OF_YEAR.map((kind) => (
          <li key={kind} data-testid="board-record-count" className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              data-tone={kindTone(kind)}
              className="inline-block h-3 w-3 rounded-sm data-[tone=neutral]:bg-fs-neutral data-[tone=nina]:bg-fs-nina data-[tone=nino]:bg-fs-nino"
            />
            {record.counts[kind] !== null
              ? formatString(strings['board.record.count'], {
                  kind: strings[`plant.kind.${kind}`],
                  n: record.counts[kind],
                  total: record.years.length,
                })
              : formatString(strings['board.record.count_missing'], { kind: strings[`plant.kind.${kind}`] })}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-fs-muted">
        {strings['board.record.note']} {formatString(strings['value.source'], { source: record.source })}
      </p>
    </section>
  )
}

/**
 * What the service says of the rain stress test it was asked for: applied or
 * not, with its own detail, or missing with its reason. Shown so that a
 * stress test that is switched off is never read as applied.
 */
export function RainEcho({ part }: { part: RainStressPart }) {
  const applied = part.kind === 'applied' && part.applied
  return (
    <p
      data-testid="board-rain-echo"
      data-applied={String(applied)}
      role="note"
      className="rounded-xl border border-fs-border bg-fs-surface px-4 py-2 text-sm data-[applied=false]:border-fs-warning data-[applied=false]:bg-fs-warning-bg data-[applied=false]:text-fs-warning"
    >
      {part.kind === 'applied'
        ? formatString(strings[part.applied ? 'plant.service.rain_applied' : 'plant.service.rain_not_applied'], {
            label: part.label,
            detail: part.detail,
          })
        : missingPatternText(formatString(strings['plant.service.rain_what'], { label: part.label }), part.missing)}
    </p>
  )
}

/**
 * The limits of the answer, as it declares them (D250), and the label every
 * soil-loss figure shown carries (D148).
 */
export function AnswerLimits({ answer }: { answer: PlantAnswer }) {
  const showsSoilLoss = answer.options.some((option) => option.soil_loss[answer.margin_of].value !== null)
  if (answer.declared_limits.length === 0 && !showsSoilLoss) {
    return null
  }
  return (
    <section data-testid="board-limits" className="rounded-2xl border border-fs-border px-5 py-3 text-sm text-fs-muted">
      <h3 className="font-mono text-[10px] uppercase tracking-widest">{strings['board.limits.heading']}</h3>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        {answer.declared_limits.map((limit) => (
          <li key={limit} data-testid="board-declared-limit">
            {formatString(strings['plant.declared_limit'], { limit })}
          </li>
        ))}
        {showsSoilLoss ? (
          <li data-testid="board-soil-label">{strings['soil_loss.headline_label']}</li>
        ) : null}
      </ul>
    </section>
  )
}
