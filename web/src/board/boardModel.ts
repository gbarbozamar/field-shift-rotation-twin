import { answerAtPrice } from '../plant/plantData'
import type { PlantAnswer, PlantOption, TippingPoint, TippingPrice } from '../plant/plantData'

/**
 * The layout rules of the rotation board (PROPOSED, l3/board). Display only:
 * the order of the cards and where the marks of the price track fall, from
 * values the answer carries. No verdict is computed here and no number of
 * the answer is changed.
 */

/** A card of the board: an option and its place, when the answer ranks it. */
export interface BoardCard {
  option: PlantOption
  /** 1 for the chosen rotation, then 2, 3... for the others within the limit; null otherwise. */
  rank: number | null
}

const GROUP_ORDER = { chosen: 0, meets: 1, not_resolved: 2, does_not_meet: 3 } as const

/** The margin the answer was asked for, or null when it is missing. */
function marginOf(answer: PlantAnswer, option: PlantOption): number | null {
  return option.margin[answer.margin_of].value
}

/**
 * The cards in board order: the chosen rotation, the others within the
 * limit, those not resolved, then those over the limit; inside a group, the
 * larger margin first and a missing margin last, the order of the answer
 * kept between equals.
 *
 * A place is given only when the answer chose a rotation: then the chosen is
 * first and the others within the limit follow by margin. An answer that is
 * not resolved or where none meets gives no place to any card.
 */
export function boardCards(answer: PlantAnswer): BoardCard[] {
  const ordered = answer.options
    .map((option, index) => ({ option, index }))
    .sort((a, b) => {
      const group = GROUP_ORDER[a.option.state] - GROUP_ORDER[b.option.state]
      if (group !== 0) return group
      const ma = marginOf(answer, a.option)
      const mb = marginOf(answer, b.option)
      if (ma !== null && mb !== null && ma !== mb) return mb - ma
      if (ma === null && mb !== null) return 1
      if (ma !== null && mb === null) return -1
      return a.index - b.index
    })
  let place = 0
  return ordered.map(({ option }) => {
    const ranked = answer.answer === 'chosen' && (option.state === 'chosen' || option.state === 'meets')
    if (ranked) place += 1
    return { option, rank: ranked ? place : null }
  })
}

/** One side of the price track, from the price of today to an end of the range. */
export type TrackSide =
  /** The answer is the one of today all the way to the end of the range. */
  | { kind: 'holds' }
  /** The answer changes at this tipping point. */
  | { kind: 'tips'; percent: number; point: Extract<TippingPoint, { price: number }> }
  /** What the answer is on this side is not computed. */
  | { kind: 'unknown' }

export interface PriceTrack {
  /** Where the price of today falls on the track, in percent of the range. */
  today: number
  down: TrackSide
  up: TrackSide
  /** The part of the track where the answer is known to be the one of today, in percent. */
  holdsFrom: number
  holdsTo: number
}

/**
 * The price track of a tipping price: the range the user declared as a track
 * from 0 to 100, with the price of today and each tipping point on it.
 * What each side says is read with answerAtPrice at the end of the range, so
 * the rules of the tipping price stay in one place. Null when there is no
 * price of today or the range has no width: nothing is drawn then.
 */
export function priceTrack(tipping: TippingPrice): PriceTrack | null {
  if (tipping.today === null || tipping.missing !== null || tipping.high <= tipping.low) {
    return null
  }
  const percent = (price: number) => ((price - tipping.low) / (tipping.high - tipping.low)) * 100
  const today = percent(tipping.today)
  const side = (end: number): TrackSide => {
    if (end === tipping.today) return { kind: 'holds' }
    const at = answerAtPrice(tipping, end)
    if (at.kind === 'past') return { kind: 'tips', percent: percent(at.point.price), point: at.point }
    return at.kind === 'unknown' ? { kind: 'unknown' } : { kind: 'holds' }
  }
  const down = side(tipping.low)
  const up = side(tipping.high)
  return {
    today,
    down,
    up,
    holdsFrom: down.kind === 'tips' ? down.percent : down.kind === 'holds' ? 0 : today,
    holdsTo: up.kind === 'tips' ? up.percent : up.kind === 'holds' ? 100 : today,
  }
}
