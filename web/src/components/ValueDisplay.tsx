/**
 * The shared value display of the interface.
 *
 * One component shows one value item in every form the conventions allow
 * (contracts/CONVENTIONS.md):
 *
 * - a value with its unit, its provenance label (C4.1) and its source, or
 *   the explicit assumption mark (C4.2, C4.5);
 * - its uncertainty range (C2.1), when one travels with the value;
 * - a missing value (C3.1): the display names what is missing and why,
 *   with the reason phrase of its reason code (C3.2).
 *
 * The component is pure and invents nothing: no zero, no blank and no
 * bounds are ever written in place of an absence. A value whose range is
 * absent with a reason (C2.2, range_missing) is rendered without a range
 * and without invented bounds; the reason travels in the item, for the
 * parts of the interface that report it.
 *
 * All user-visible wording lives in strings.ts; the placeholders of its
 * templates are filled by the pure helper in lib/format.ts. The unit
 * string is rendered as plain text, exactly as it travels (C1.1).
 *
 * Two display-only rules of the display-polish unit complete the render,
 * and neither touches a value that travels: the source of a value is the
 * engine's derivation trace, often a full paragraph, so its line renders
 * collapsed to one clipped line inside a disclosure that carries the exact
 * trace unchanged; and a measured value displays rounded to three decimals,
 * with the exact value kept in the element for inspection (D80: formatting
 * of the display only, never of the computation).
 */
import { formatString } from '../lib/format'
import { REASON_PHRASE_PLACEHOLDER, strings } from '../strings'

/** The four provenance labels of the conventions (C4.1). */
export type ProvenanceLabel = 'DECLARED' | 'OBSERVED' | 'DERIVED' | 'SIMULATED'

/**
 * The eight reason codes of the conventions (C3.2). The list is closed:
 * a new code is a contract change.
 */
export type ReasonCode =
  | 'NOT_DECLARED'
  | 'SOURCE_UNAVAILABLE'
  | 'NO_COVERAGE'
  | 'MISSING_INPUT'
  | 'NOT_COMPUTABLE'
  | 'CONTROL_FAILED'
  | 'NOT_AVAILABLE'
  | 'NOT_APPLICABLE'

/**
 * An uncertainty range: absolute bounds in the unit of the value, and the
 * label naming what the range represents (C2.1, C2.3).
 */
export interface UncertaintyRange {
  low: number
  high: number
  kind: string
}

/**
 * Why a value, or a range, is absent: a reason code and, for
 * MISSING_INPUT, the free-text detail naming the missing input (C3.1, C3.2).
 */
export interface MissingPart {
  reason: ReasonCode
  detail?: string
}

/**
 * One value item, as it travels in the results contracts: either a number
 * with its provenance label, its source or assumption mark, and its range
 * or the reason its range is absent, or null with a missing part, keeping
 * its unit so a consumer knows what is missing (C3.1). An item never holds
 * a number and a missing part together, and never holds neither.
 */
export type ValueItem =
  | {
      value: number
      unit: string
      provenance: ProvenanceLabel
      source?: string
      assumption?: boolean
      range?: UncertaintyRange
      range_missing?: MissingPart
      missing?: undefined
    }
  | {
      value: null
      unit: string
      missing: MissingPart
      provenance?: undefined
      source?: undefined
      assumption?: undefined
      range?: undefined
      range_missing?: undefined
    }

/** Props of the value display: the display name of the item, and the item. */
export interface ValueDisplayProps {
  what: string
  item: ValueItem
}

/**
 * The reason phrase of a missing part, from the strings file. The detail of
 * MISSING_INPUT fills its place in the phrase; a detail that is absent
 * stays visible as its placeholder, exactly as written. A detail that
 * travels with any other reason code is shown too, appended in parentheses
 * after the phrase, so an absence keeps naming its cause in full (for
 * example the NOT_APPLICABLE harvest of a cover crop).
 */
function reasonPhrase(missing: MissingPart): string {
  const params: Record<string, string> = {}
  if (missing.detail !== undefined) {
    params.detail = missing.detail
  }
  const template = strings[`missing.${missing.reason}`]
  const phrase = formatString(template, params)
  if (missing.detail !== undefined && !template.includes('{detail}')) {
    return `${phrase} ${formatString(strings['missing.detail_suffix'], params)}`
  }
  return phrase
}

/**
 * The one-line missing render of the conventions (C3.1): "{what}: {reason
 * phrase}". Exported for the displays that are not value items and still owe
 * a missing part the same pattern, such as the dated events of the rotation
 * ribbon. Pure: it invents no phrase and fills no gap.
 */
export function missingPatternText(what: string, missing: MissingPart): string {
  // Same render as missingPattern (the seam's name for it); two names, one
  // pattern, so every absence in the interface reads identically.
  return missingPattern(what, missing)
}

/**
 * The missing-value pattern of C3.1 for a missing part that travels outside a
 * value item (a whole result, a dated event): the supplied pattern with the
 * reason phrase of its reason code. Exported so other parts of the interface
 * render an absence with exactly the wording of the value display.
 */
export function missingPattern(what: string, missing: MissingPart): string {
  return formatString(strings['missing.pattern'], {
    what,
    [REASON_PHRASE_PLACEHOLDER]: reasonPhrase(missing),
  })
}

/**
 * The displayed form of a measured value: rounded to three decimals, with
 * no forced trailing zeros (2.1 renders "2.1", not "2.100"). Display-only
 * (D80): the value that travels is never rounded — the exact number stays
 * in the item and in the element, for inspection.
 */
function displayNumber(value: number): string {
  return value
    .toFixed(3)
    .replace(/(\.\d*?)0+$/, '$1')
    .replace(/\.$/, '')
}

export function ValueDisplay({ what, item }: ValueDisplayProps) {
  if (item.missing) {
    return (
      <div className="text-sm leading-5">
        <p data-testid="missing-line" className="italic text-slate-500">
          {missingPattern(what, item.missing)}
        </p>
      </div>
    )
  }

  return (
    <div className="text-sm leading-5">
      <p data-testid="value-line">
        <span data-testid="value-number" className="font-medium" title={String(item.value)}>
          {displayNumber(item.value)}
        </span>{' '}
        <span data-testid="value-unit" className="text-slate-500">
          {item.unit}
        </span>{' '}
        <span data-testid="value-label" className="text-slate-500">
          {strings[`provenance.${item.provenance}`]}
        </span>
      </p>
      {item.source !== undefined ? (
        <details data-testid="source-details" className="text-slate-500">
          <summary data-testid="source-line" className="truncate">
            {formatString(strings['value.source'], { source: item.source })}
          </summary>
          <p data-testid="source-full" className="mt-1 whitespace-normal break-words">
            {item.source}
          </p>
        </details>
      ) : null}
      {item.assumption === true ? (
        <p data-testid="assumption-line" className="text-slate-500">
          {strings['assumption.mark']}
        </p>
      ) : null}
      {item.range !== undefined ? (
        <p data-testid="range-line" className="text-slate-500">
          {formatString(strings['value.range'], {
            low: item.range.low,
            high: item.range.high,
            kind: item.range.kind,
          })}
        </p>
      ) : null}
    </div>
  )
}
