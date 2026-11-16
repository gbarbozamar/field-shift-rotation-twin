import { missingPatternText } from '../components/ValueDisplay'
import type { PlantAnswer } from '../plant/plantData'
import { formatString } from '../lib/format'
import { strings } from '../strings'

/**
 * What needs the user's attention in an answer (l3/original-mock, PROPOSED):
 * the list the board's answer and the case overview show under "Needs
 * attention". One home, read by both. Every item is read from data the
 * screen already has (the answer as it travels, whether the board mixed mock
 * values in, whether the user's numbers are still the example's); nothing is
 * computed or judged here, and each item names what to do next and where.
 */

/** Where the next step of an item is done; the screen showing the list turns it into a link. */
export type AttentionTarget = 'board' | 'candidates' | 'numbers' | 'measure' | 'report' | 'mock'

export interface AttentionItem {
  id: string
  /** over: a value over the user's limit; open: the data cannot decide; info: something to know. */
  tone: 'over' | 'open' | 'info'
  title: string
  detail: string | null
  /** The words of the next step. */
  action: string
  target: AttentionTarget
}

export function answerAttention(
  answer: PlantAnswer,
  {
    mocked,
    exampleNumbers,
    nameOf,
  }: {
    /** True when some values of the answer are mock example data (the board mixing). */
    mocked: boolean
    /** True when the numbers the answer was asked with are the example's, unchanged. */
    exampleNumbers: boolean
    /** How the screen names a rotation. */
    nameOf: (rotationId: string) => string
  },
): AttentionItem[] {
  const items: AttentionItem[] = []
  const over = answer.options.filter((option) => option.state === 'does_not_meet')
  if (over.length !== 0) {
    items.push({
      id: 'over-limit',
      tone: 'over',
      title: formatString(strings['attention.over_limit'], { n: over.length, total: answer.options.length }),
      detail: over.map((option) => nameOf(option.rotation_id)).join(strings['chart.notes_join']),
      action: strings['attention.over_limit_do'],
      target: 'candidates',
    })
  }
  if (answer.answer === 'not_resolved') {
    items.push({
      id: 'not-resolved',
      tone: 'open',
      title: strings['plant.answer.not_resolved'],
      detail: answer.missing !== null ? missingPatternText(strings['plant.answer.why'], answer.missing) : null,
      action: strings['attention.not_resolved_do'],
      target: 'measure',
    })
  }
  for (const source of answer.sources) {
    if (source.state !== 'unavailable' || source.missing_reason === null) continue
    items.push({
      id: `source-${source.id}`,
      tone: 'open',
      title: strings['attention.source'],
      detail: missingPatternText(
        source.id,
        source.detail !== null ? { reason: source.missing_reason, detail: source.detail } : { reason: source.missing_reason },
      ),
      action: strings['attention.source_do'],
      target: 'report',
    })
  }
  if (exampleNumbers) {
    items.push({
      id: 'example-numbers',
      tone: 'info',
      title: strings['attention.example_numbers'],
      detail: strings['attention.example_numbers_detail'],
      action: strings['attention.example_numbers_do'],
      target: 'numbers',
    })
  }
  if (mocked) {
    items.push({
      id: 'mock',
      tone: 'info',
      title: strings['attention.mock'],
      detail: strings['attention.mock_detail'],
      action: strings['attention.mock_do'],
      target: 'mock',
    })
  }
  return items
}

/** The item of a case with no answer yet: compare on the board first. */
export const NO_ANSWER_ITEM: AttentionItem = {
  id: 'no-answer',
  tone: 'info',
  title: strings['attention.no_answer'],
  detail: strings['attention.no_answer_detail'],
  action: strings['attention.open_board'],
  target: 'board',
}
