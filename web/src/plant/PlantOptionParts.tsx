import { missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { barPercent } from './optionBars'
import { cropText, stripText, unplacedText, yearText } from './rotationStrip'
import type { RotationStrip } from './rotationStrip'
import type { Verdict } from './plantData'

/**
 * The parts of an option row of the screen "What should I plant?" (S-020,
 * PROPOSED): the strip of crops year by year, the margin bar and the
 * soil-loss bar with its limit line. Pure display of what the answer and the
 * request carry; the widths come from optionBars.ts.
 *
 * Colour is never the only carrier: each swatch has its crop_id written
 * beside it, and each bar has its number and verdict in the text lines of the
 * row. The bars are hidden from assistive technology for that reason; the
 * strip is one image with the strip text as its text alternative.
 */

/**
 * A small fixed palette of swatches, given to the crops by order of first
 * appearance on the screen (cropOrder), and repeated past its end.
 */
const CROP_SWATCHES = [
  'bg-emerald-600',
  'bg-amber-500',
  'bg-sky-600',
  'bg-fuchsia-600',
  'bg-lime-500',
  'bg-orange-700',
] as const

export function swatchOf(cropId: string, order: readonly string[]): string {
  const index = order.indexOf(cropId)
  return CROP_SWATCHES[(index < 0 ? 0 : index) % CROP_SWATCHES.length]
}

function Swatch({ className }: { className: string }) {
  return (
    <span aria-hidden="true" className="inline-flex h-3 w-5 shrink-0 overflow-hidden rounded">
      <span className={className} style={{ flex: 1 }} />
    </span>
  )
}

/** The strip of a rotation, or its absence with the reason. */
export function StripBlock({
  strip,
  order,
}: {
  strip: RotationStrip | null
  order: readonly string[]
}) {
  if (strip === null) {
    const missing: MissingPart = {
      reason: 'MISSING_INPUT',
      detail: strings['plant.strip.no_definition_detail'],
    }
    return (
      <p data-testid="plant-strip-unavailable" className="mt-2 text-sm italic text-slate-500">
        {missingPatternText(strings['plant.strip.what'], missing)}
      </p>
    )
  }
  return (
    <div className="mt-2">
      {strip.years.length !== 0 ? (
        <div
          data-testid="plant-option-strip"
          role="img"
          aria-label={stripText(strip)}
          className="flex flex-wrap gap-2"
        >
          {strip.years.map((year) => (
            <div
              key={year.index}
              data-testid="plant-strip-year"
              className="rounded border border-slate-200 px-2 py-1"
            >
              <p className="text-xs font-semibold text-slate-600">
                {formatString(strings['plant.strip.year_label'], { n: year.index })}
              </p>
              {year.crops.length === 0 ? (
                <p className="text-xs text-slate-500">{yearText(year)}</p>
              ) : (
                <ul>
                  {year.crops.map((crop) => (
                    <li key={crop.component_id} className="flex items-center gap-1 text-xs">
                      <Swatch className={swatchOf(crop.crop_id, order)} />
                      <span>{cropText(crop, year.index)}</span>
                      <span className="text-slate-500">
                        {formatString(strings['plant.strip.purpose'], { purpose: crop.purpose })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : null}
      {strip.unplaced.map((crop) => (
        <p key={crop.component_id} data-testid="plant-strip-unplaced" className="text-xs italic text-slate-500">
          {unplacedText(crop)}
        </p>
      ))}
      <p className="text-xs text-slate-500">
        {strings[strip.repeats ? 'ribbon.repeats' : 'ribbon.not_repeating']}
      </p>
    </div>
  )
}

const FILL_POSITION = { position: 'absolute', top: 0, bottom: 0, left: 0 } as const

/** The margin bar: from zero, its share of the largest absolute margin shown. */
export function MarginBar({ value, scale }: { value: number; scale: number }) {
  const negative = value < 0
  return (
    <div data-testid="plant-bar-margin" aria-hidden="true" className="relative mt-1 h-3 rounded bg-slate-100">
      <span
        data-testid="plant-bar-margin-fill"
        data-negative={String(negative)}
        className={negative ? 'bg-rose-400' : 'bg-teal-600'}
        style={{ ...FILL_POSITION, width: `${barPercent(value, scale)}%` }}
      />
    </div>
  )
}

const VERDICT_FILL: { [verdict in Verdict]: string } = {
  meets: 'bg-emerald-600',
  does_not_meet: 'bg-rose-600',
  not_resolved: 'bg-amber-400',
}

/**
 * The soil-loss bar: its share of the largest of the soil losses shown and
 * the limit, coloured by the limit check of the option; a vertical line at
 * the limit, or no line and the reason when there is no limit.
 */
export function SoilLossBar({
  value,
  scale,
  limit,
  verdict,
  limitMissing,
}: {
  value: number
  scale: number
  limit: number | null
  verdict: Verdict
  limitMissing: MissingPart | null
}) {
  return (
    <div>
      <div data-testid="plant-bar-soil" aria-hidden="true" className="relative mt-1 h-3 rounded bg-slate-100">
        <span
          data-testid="plant-bar-soil-fill"
          data-verdict={verdict}
          className={VERDICT_FILL[verdict]}
          style={{ ...FILL_POSITION, width: `${barPercent(value, scale)}%` }}
        />
        {limit !== null ? (
          <span
            data-testid="plant-bar-limit"
            className="absolute -bottom-1 -top-1 w-0.5 bg-slate-900"
            style={{ left: `${barPercent(limit, scale)}%` }}
          />
        ) : null}
      </div>
      {limit === null && limitMissing !== null ? (
        <p data-testid="plant-bar-no-limit" className="text-xs italic text-slate-500">
          {missingPatternText(strings['plant.bar.limit_line'], limitMissing)}
        </p>
      ) : null}
    </div>
  )
}
