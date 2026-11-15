/**
 * The widths of the bars of the option rows (S-020, PROPOSED). Display only:
 * nothing is computed but the share of a bar, from values the answer carries.
 *
 * A bar is drawn only for a value that is present; a missing value gives no
 * bar (its reason is shown instead), and is never read as 0. The scale of a
 * set of bars is the largest absolute value present in it; with no value
 * present there is no scale, hence no bar.
 */

import type { MissingPart } from '../components/ValueDisplay'
import type { MarginOf, PlantOption, Verdict } from './plantData'

/**
 * What the soil-loss bar says against the limit, for the quantity it draws
 * (fix round 1 of S-020, PROPOSED). Read only from the fields of the answer;
 * no number is compared with the limit here.
 *
 * - The average of the record: the option's on-average check, as it travels.
 * - A kind of year: named in kinds_not_met, it does not meet; in
 *   kinds_not_resolved, it is not resolved (with the reason of the every-kind
 *   check); in kinds_not_in_record, there is no verdict (not in the record).
 *   Named in none: it meets. The contract (LimitAssessmentOut in
 *   contracts/plant_answer/plant_answer.py) makes the lists exactly the kinds
 *   of the record whose check does not meet or is not resolved, and the kinds
 *   not in the record, so a not-resolved every-kind check is covered by the
 *   kinds those lists name. Only when the every-kind check is not resolved
 *   and neither kinds_not_resolved nor kinds_not_in_record names any kind do
 *   the fields not tell what its reason covers: then the bar is not
 *   resolved, with the every-kind reason.
 *
 * The lists are read in this order when a kind is named in more than one.
 * The per-kind checks of the contract (limit.by_kind) are not read by the
 * parser of the screen; this rule uses the lists it does read.
 */
export type DrawnVerdict =
  | { kind: 'verdict'; verdict: Verdict; missing: MissingPart | null }
  | { kind: 'not_in_record' }

export function drawnSoilVerdict(option: PlantOption, marginOf: MarginOf): DrawnVerdict {
  if (marginOf === 'average') {
    return { kind: 'verdict', verdict: option.on_average.verdict, missing: option.on_average.missing }
  }
  const everyKind = option.every_kind
  if (option.kinds_not_met.includes(marginOf)) {
    return { kind: 'verdict', verdict: 'does_not_meet', missing: null }
  }
  if (option.kinds_not_resolved.includes(marginOf)) {
    return { kind: 'verdict', verdict: 'not_resolved', missing: everyKind.missing }
  }
  if (option.kinds_not_in_record.includes(marginOf)) {
    return { kind: 'not_in_record' }
  }
  const covered = option.kinds_not_resolved.length !== 0 || option.kinds_not_in_record.length !== 0
  if (everyKind.verdict === 'not_resolved' && !covered) {
    return { kind: 'verdict', verdict: 'not_resolved', missing: everyKind.missing }
  }
  return { kind: 'verdict', verdict: 'meets', missing: null }
}

/** The largest absolute value present, or null when none is present. */
export function barScale(values: readonly (number | null)[]): number | null {
  const present = values.filter((v): v is number => v !== null).map(Math.abs)
  return present.length === 0 ? null : Math.max(...present)
}

/**
 * The share of the scale a value takes, as a percentage of the track, from
 * zero. A scale of zero (every value present is zero) gives an empty bar.
 */
export function barPercent(value: number, scale: number): number {
  if (scale === 0) {
    return 0
  }
  return Math.min(100, (Math.abs(value) / scale) * 100)
}
