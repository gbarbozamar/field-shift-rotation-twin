import { KINDS_OF_YEAR, answerAtPrice } from '../plant/plantData'
import { strings } from '../strings'
import type { StringKey } from '../strings'
import type {
  AnswerKind,
  KindOfYear,
  OptionState,
  PlantAnswer,
  PlantOption,
  TippingPoint,
  TippingPrice,
} from '../plant/plantData'

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

/** What the options are ordered by on the board. */
export type SortKey = 'rule' | 'margin' | 'soil' | 'worst' | 'kinds_over' | 'yours'

export const SORT_KEYS: readonly SortKey[] = ['rule', 'margin', 'soil', 'worst', 'kinds_over', 'yours']

/** One option as a column of the comparison. */
export interface BoardColumn {
  option: PlantOption
  /** Its letter, by its order in the answer: stable whatever the options are ordered by. */
  letter: string
  /** Its position in the order shown, from 1; options with the same value share it. Null when the order cannot place it. */
  position: number | null
  /** True when another option has the same value, so they share a position. */
  tied: boolean
}

const FIRST_LETTER = 65

/** The letter of an option: A for the first of the answer, B for the second, and so on. */
export function optionLetter(answer: PlantAnswer, option: PlantOption): string {
  return String.fromCharCode(FIRST_LETTER + answer.options.indexOf(option))
}

/**
 * The kind of year in which an option has its smallest margin, among the
 * kinds the record holds (a count above zero). Null when the record is not
 * classified, or a margin of one of those kinds is missing: a worst kind is
 * not named from part of the kinds. A selection among values the answer
 * carries; no number is computed.
 */
export function worstKind(answer: PlantAnswer, option: PlantOption): KindOfYear | null {
  const counts = answer.kinds_of_year.counts
  const kinds = KINDS_OF_YEAR.filter((kind) => counts[kind] !== null && counts[kind]! > 0)
  if (kinds.length === 0 || kinds.some((kind) => option.margin[kind].value === null)) {
    return null
  }
  return kinds.reduce((worst, kind) =>
    option.margin[kind].value! < option.margin[worst].value! ? kind : worst,
  )
}

/**
 * The value an order compares, with its direction (1: the smaller first,
 * -1: the larger first); null when the option cannot be placed in it.
 *
 * - margin: its margin, the larger first.
 * - soil: its soil loss, the smaller first.
 * - worst: its margin in its worst kind of year (worstKind), the larger first.
 * - kinds_over: the number of kinds of year the answer says are over the
 *   limit, the fewer first; not placed while a kind is not resolved.
 */
function sortValue(answer: PlantAnswer, option: PlantOption, sort: SortKey): number | null {
  const kind = answer.margin_of
  switch (sort) {
    case 'margin':
      return option.margin[kind].value
    case 'soil':
      return option.soil_loss[kind].value
    case 'worst': {
      const worst = worstKind(answer, option)
      return worst !== null ? option.margin[worst].value : null
    }
    case 'kinds_over':
      return option.kinds_not_resolved.length === 0 ? option.kinds_not_met.length : null
    default:
      return null
  }
}

const SMALLER_FIRST: readonly SortKey[] = ['soil', 'kinds_over']

/**
 * The options as columns, in the order asked for. Display order only: the
 * values compared are those the answer carries, and no score is computed.
 *
 * - rule: the order of the answer (boardCards): the chosen rotation, the
 *   others within the limit by margin, those not resolved, those over the
 *   limit. A position is a place the answer gives.
 * - yours: the order of the request, with no position.
 * - margin, soil, worst, kinds_over: by the value of sortValue. Options with
 *   the same value share a position and are marked tied; an option whose
 *   value is missing comes last, in the order of the answer, with no
 *   position: a missing value is not ranked.
 */
export function boardColumns(answer: PlantAnswer, sort: SortKey): BoardColumn[] {
  if (sort === 'rule') {
    return boardCards(answer).map((card) => ({
      option: card.option,
      letter: optionLetter(answer, card.option),
      position: card.rank,
      tied: false,
    }))
  }
  if (sort === 'yours') {
    return answer.options.map((option) => ({
      option,
      letter: optionLetter(answer, option),
      position: null,
      tied: false,
    }))
  }
  const direction = SMALLER_FIRST.includes(sort) ? 1 : -1
  const ordered = answer.options
    .map((option, index) => ({ option, index, value: sortValue(answer, option, sort) }))
    .sort((a, b) => {
      if (a.value !== null && b.value !== null && a.value !== b.value) return direction * (a.value - b.value)
      if (a.value === null && b.value !== null) return 1
      if (a.value !== null && b.value === null) return -1
      return a.index - b.index
    })
  return ordered.map(({ option, value }) => {
    const first = ordered.findIndex((each) => each.value === value)
    return {
      option,
      letter: optionLetter(answer, option),
      position: value !== null ? first + 1 : null,
      tied: value !== null && ordered.filter((each) => each.value === value).length > 1,
    }
  })
}

const PLACEHOLDER_PREFIX = /^PLACEHOLDER_/

/** True for a crop id that is a placeholder of the example data, not a crop. */
export function isExampleCrop(cropId: string): boolean {
  return PLACEHOLDER_PREFIX.test(cropId)
}

/**
 * A crop id as a name to read (PROPOSED): the marker of a placeholder id is
 * dropped and its underscores become spaces. A display form only: wherever a
 * name read from a placeholder id is shown, the mark of example crops is
 * shown beside it (isExampleCrop), so the name never passes for a real crop.
 */
export function cropName(cropId: string): string {
  return cropId.replace(PLACEHOLDER_PREFIX, '').replaceAll('_', ' ')
}

/** What differs between two answers of the service, as the user would name it. */
export type AnswerChange =
  /** The rotation chosen, or the answer when none is, is another. */
  | { kind: 'answer'; before: { answer: AnswerKind; chosen: string | null }; after: { answer: AnswerKind; chosen: string | null } }
  /** An option is in another state. */
  | { kind: 'state'; rotation_id: string; before: OptionState; after: OptionState }

/**
 * What changed from one answer to the next (PROPOSED): the answer itself,
 * then each option whose state is another, in the order of the new answer.
 * Only what the service said is compared (its answer, its chosen rotation,
 * the state of each option); no number is compared and none is computed. An
 * option that is in one answer only is not a change of state.
 */
export function answerChanges(before: PlantAnswer, after: PlantAnswer): AnswerChange[] {
  const changes: AnswerChange[] = []
  if (before.answer !== after.answer || before.chosen !== after.chosen) {
    changes.push({
      kind: 'answer',
      before: { answer: before.answer, chosen: before.chosen },
      after: { answer: after.answer, chosen: after.chosen },
    })
  }
  for (const option of after.options) {
    const was = before.options.find((each) => each.rotation_id === option.rotation_id)
    if (was !== undefined && was.state !== option.state) {
      changes.push({ kind: 'state', rotation_id: option.rotation_id, before: was.state, after: option.state })
    }
  }
  return changes
}

/**
 * A unit as it is read on the board (PROPOSED): the unit of the contract
 * written with a slash ("t/ha/yr" for "t ha-1 yr-1"). A display form only:
 * the wording is in strings.ts under "unit." followed by the unit of the
 * contract, and a unit with no entry there is shown as it travels. The
 * values and the units sent and received do not change.
 */
export function unitText(unit: string): string {
  const key = `unit.${unit}`
  return key in strings ? strings[key as StringKey] : unit
}
