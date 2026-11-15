import { missingPatternText } from '../components/ValueDisplay'
import type { MissingPart } from '../components/ValueDisplay'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import { barPercent } from './optionBars'
import type { DrawnVerdict } from './optionBars'
import { cropText, stripText, unplacedText, yearText } from './rotationStrip'
import type { RotationStrip } from './rotationStrip'

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
  'bg-fs-crop-1',
  'bg-fs-crop-2',
  'bg-fs-crop-3',
  'bg-fs-crop-4',
  'bg-fs-crop-5',
  'bg-fs-crop-6',
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

/**
 * The start of the agricultural year the strip's years are numbered by, with
 * its provisional mark and its provenance, and the provenance of the strip's
 * dates (fix round 1 of S-020, PROPOSED): the wording of the rotation ribbon
 * where it fits.
 */
function StripMarks({ strip }: { strip: RotationStrip }) {
  const start = strip.ag_year_start
  return (
    <div className="text-xs text-fs-muted">
      <p data-testid="plant-strip-ag-year">
        {formatString(strings['ribbon.ag_year_start'], { month: start.month })}
        {start.provisional ? (
          <>
            {' '}
            <span data-testid="plant-strip-provisional">{strings['ribbon.provisional']}</span>
          </>
        ) : null}{' '}
        {strings[`provenance.${start.provenance}`]}
      </p>
      <p>{formatString(strings['value.source'], { source: start.source })}</p>
      {strip.date_marks.map((mark) => (
        <div key={`${mark.provenance}:${mark.source}`} data-testid="plant-strip-dates-provenance">
          <p>
            {formatString(strings['plant.strip.dates_provenance'], {
              provenance: strings[`provenance.${mark.provenance}`],
            })}
          </p>
          <p>{formatString(strings['value.source'], { source: mark.source })}</p>
        </div>
      ))}
    </div>
  )
}

/** The strip of a rotation, or its absence with the reason. */
export function StripBlock({
  strip,
  order,
  missing,
}: {
  strip: RotationStrip | null
  order: readonly string[]
  /** Why there is no strip; read only when strip is null. */
  missing: MissingPart | null
}) {
  if (strip === null) {
    // A strip absent with no reason given is a rotation the request does not define.
    const why: MissingPart = missing ?? {
      reason: 'MISSING_INPUT',
      detail: strings['plant.strip.no_definition_detail'],
    }
    return (
      <p data-testid="plant-strip-unavailable" className="mt-2 text-sm italic text-fs-muted">
        {missingPatternText(strings['plant.strip.what'], why)}
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
              className="rounded border border-fs-border px-2 py-1"
            >
              <p className="text-xs font-semibold text-fs-muted">
                {formatString(strings['plant.strip.year_label'], { n: year.index })}
              </p>
              {year.crops.length === 0 ? (
                <p className="text-xs text-fs-muted">{yearText(year)}</p>
              ) : (
                <ul>
                  {year.crops.map((crop) => (
                    <li key={crop.component_id} className="flex items-center gap-1 text-xs">
                      <Swatch className={swatchOf(crop.crop_id, order)} />
                      <span>{cropText(crop, year.index)}</span>
                      <span className="text-fs-muted">
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
        <p key={crop.component_id} data-testid="plant-strip-unplaced" className="text-xs italic text-fs-muted">
          {unplacedText(crop)}
        </p>
      ))}
      <p className="text-xs text-fs-muted">
        {strings[strip.repeats ? 'ribbon.repeats' : 'ribbon.not_repeating']}
      </p>
      <StripMarks strip={strip} />
    </div>
  )
}

const FILL_POSITION = { position: 'absolute', top: 0, bottom: 0, left: 0 } as const

/**
 * The fill of a negative margin (fix round 1 of S-020, PROPOSED): a dashed
 * outline on a light fill, so that it differs from a positive one by its
 * form, not only by its colour; a text mark under the bar says it is a loss,
 * and the number keeps its minus sign.
 */
const NEGATIVE_FILL = ['bg-fs-error-bg', 'border-2', 'border-dashed', 'border-fs-error'].join(' ')

/** The margin bar: from zero, its share of the largest absolute margin shown. */
export function MarginBar({ value, scale }: { value: number; scale: number }) {
  const negative = value < 0
  return (
    <div>
      <div data-testid="plant-bar-margin" aria-hidden="true" className="relative mt-1 h-3 rounded bg-fs-faint">
        <span
          data-testid="plant-bar-margin-fill"
          data-negative={String(negative)}
          data-pattern={negative ? 'dashed' : 'solid'}
          className={negative ? NEGATIVE_FILL : 'bg-fs-primary'}
          style={{ ...FILL_POSITION, width: `${barPercent(value, scale)}%` }}
        />
      </div>
      {negative ? (
        <p data-testid="plant-bar-margin-loss" className="text-xs text-fs-error">
          {strings['plant.bar.margin_loss']}
        </p>
      ) : null}
    </div>
  )
}

/** The fill of the soil-loss bar by what it says; not in the record has no verdict colour. */
const DRAWN_FILL = {
  meets: 'bg-fs-ok',
  does_not_meet: 'bg-fs-error',
  not_resolved: 'bg-fs-warning',
  not_in_record: 'bg-fs-muted',
} as const

function drawnKey(drawn: DrawnVerdict): keyof typeof DRAWN_FILL {
  return drawn.kind === 'not_in_record' ? 'not_in_record' : drawn.verdict
}

/** The text verdict of the soil-loss bar: the quantity drawn, against the limit. */
export function drawnVerdictText(what: string, drawn: DrawnVerdict): string {
  const against = formatString(strings['plant.bar.soil_against'], { what })
  if (drawn.kind === 'not_in_record') {
    return formatString(strings['plant.check_line'], {
      check: against,
      verdict: strings['plant.bar.not_in_record'],
    })
  }
  if (drawn.missing !== null) {
    return missingPatternText(against, drawn.missing)
  }
  return formatString(strings['plant.check_line'], {
    check: against,
    verdict: strings[`plant.verdict.${drawn.verdict}`],
  })
}

/**
 * The soil-loss bar: its share of the largest of the soil losses shown and
 * the limit, coloured by what the answer says of the quantity drawn
 * (drawnSoilVerdict in optionBars.ts), with that verdict in text unless the
 * check line of the row already says it; a vertical line at the limit, or no
 * line and the reason when there is no limit.
 */
export function SoilLossBar({
  value,
  scale,
  limit,
  what,
  drawn,
  verdictInText,
  limitMissing,
}: {
  value: number
  scale: number
  limit: number | null
  /** The quantity drawn, as its value line names it. */
  what: string
  drawn: DrawnVerdict
  /** False when the check line of the row is the check of this same quantity. */
  verdictInText: boolean
  limitMissing: MissingPart | null
}) {
  const key = drawnKey(drawn)
  return (
    <div>
      <div data-testid="plant-bar-soil" aria-hidden="true" className="relative mt-1 h-3 rounded bg-fs-faint">
        <span
          data-testid="plant-bar-soil-fill"
          data-verdict={key}
          className={DRAWN_FILL[key]}
          style={{ ...FILL_POSITION, width: `${barPercent(value, scale)}%` }}
        />
        {limit !== null ? (
          <span
            data-testid="plant-bar-limit"
            className="absolute -bottom-1 -top-1 w-0.5 bg-fs-text"
            style={{ left: `${barPercent(limit, scale)}%` }}
          />
        ) : null}
      </div>
      {limit === null && limitMissing !== null ? (
        <p data-testid="plant-bar-no-limit" className="text-xs italic text-fs-muted">
          {missingPatternText(strings['plant.bar.limit_line'], limitMissing)}
        </p>
      ) : null}
      {verdictInText ? (
        <p data-testid="plant-bar-soil-verdict" className="text-xs text-fs-muted">
          {drawnVerdictText(what, drawn)}
        </p>
      ) : null}
    </div>
  )
}
