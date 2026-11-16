/**
 * The user's own numbers on the board (PROPOSED, l3/original-mock): the
 * soybean price, cost and yield by kind of year, the cover-crop cost, the
 * pasture margin by kind of year, and the soil-loss limit. They are
 * declarations of the user (DECLARED, source "user"), sent to the service in
 * the plant request exactly as typed; the board computes nothing from them.
 *
 * Pure functions only: read the numbers of a request, check a draft, and
 * write a draft into a copy of a request.
 */

export const FACT_KINDS = ['el_nino', 'neutral', 'la_nina'] as const
export type FactKind = (typeof FACT_KINDS)[number]

export interface FactsDraft {
  price: string
  cost: string
  yields: Record<FactKind, string>
  coverCost: string
  pasture: Record<FactKind, string>
  limit: string
}

export type FactKey =
  | 'price'
  | 'cost'
  | 'coverCost'
  | 'limit'
  | `yields.${FactKind}`
  | `pasture.${FactKind}`

export interface FactProblem {
  key: FactKey
  kind: 'not_a_number' | 'negative' | 'not_positive'
}

type Json = Record<string, unknown>

function cropOf(request: Json, kind: string): Json {
  const facts = request.economic_facts as Json
  const crop = (facts.crops as Json[]).find((each) => each.kind === kind)
  if (crop === undefined) throw new Error(`invalid-plant-request:no-${kind}-crop`)
  return crop
}

function valueText(item: unknown): string {
  const value = (item as Json | undefined)?.value
  return typeof value === 'number' ? String(value) : ''
}

/** The numbers a request declares, as text for the fields. Throws on a request without them. */
export function readFacts(request: unknown): FactsDraft {
  const req = request as Json
  const grain = cropOf(req, 'grain')
  const cover = cropOf(req, 'cover')
  const pasture = cropOf(req, 'declared_margin')
  const yields = grain.yield as Json
  const margins = pasture.declared_margin as Json
  return {
    price: valueText(grain.price),
    cost: valueText(grain.cost),
    yields: { el_nino: valueText(yields.el_nino), neutral: valueText(yields.neutral), la_nina: valueText(yields.la_nina) },
    coverCost: valueText(cover.cost),
    pasture: { el_nino: valueText(margins.el_nino), neutral: valueText(margins.neutral), la_nina: valueText(margins.la_nina) },
    limit: valueText(req.soil_loss_limit),
  }
}

function entries(draft: FactsDraft): [FactKey, string][] {
  return [
    ['price', draft.price],
    ['cost', draft.cost],
    ...FACT_KINDS.map((k): [FactKey, string] => [`yields.${k}`, draft.yields[k]]),
    ['coverCost', draft.coverCost],
    ...FACT_KINDS.map((k): [FactKey, string] => [`pasture.${k}`, draft.pasture[k]]),
    ['limit', draft.limit],
  ]
}

/**
 * What keeps a draft from being sent: a field that is not a number; a price,
 * cost or yield below zero; a limit that is not above zero. A pasture margin
 * may be negative (a loss is a margin).
 */
export function factsProblems(draft: FactsDraft): FactProblem[] {
  const problems: FactProblem[] = []
  for (const [key, text] of entries(draft)) {
    const value = Number(text)
    if (text.trim() === '' || !Number.isFinite(value)) {
      problems.push({ key, kind: 'not_a_number' })
    } else if (key === 'limit' && value <= 0) {
      problems.push({ key, kind: 'not_positive' })
    } else if (!key.startsWith('pasture.') && key !== 'limit' && value < 0) {
      problems.push({ key, kind: 'negative' })
    }
  }
  return problems
}

export function sameFacts(a: FactsDraft, b: FactsDraft): boolean {
  return entries(a).every(([key, text], i) => key === entries(b)[i][0] && Number(text) === Number(entries(b)[i][1]))
}

/** The number of fields whose value differs between two drafts. */
export function changedFacts(a: FactsDraft, b: FactsDraft): number {
  const other = entries(b)
  return entries(a).filter(([, text], i) => Number(text) !== Number(other[i][1])).length
}

/** The units the request declares for each number, shown beside its field. */
export interface FactUnits {
  price: string
  cost: string
  yield: string
  margin: string
  limit: string
}

function unitOf(item: unknown): string {
  const unit = (item as Json | undefined)?.unit
  if (typeof unit !== 'string') throw new Error('invalid-plant-request:fact-without-unit')
  return unit
}

/** The declared units of a request's numbers. Throws on a request without them. */
export function readFactUnits(request: unknown): FactUnits {
  const req = request as Json
  const grain = cropOf(req, 'grain')
  const pasture = cropOf(req, 'declared_margin')
  return {
    price: unitOf(grain.price),
    cost: unitOf(grain.cost),
    yield: unitOf((grain.yield as Json).neutral),
    margin: unitOf((pasture.declared_margin as Json).neutral),
    limit: unitOf(req.soil_loss_limit),
  }
}

function setValue(item: unknown, text: string): void {
  ;(item as Json).value = Number(text)
}

/**
 * A copy of the request with the draft's numbers written in. Every other part
 * (units, provenance, ranges, the questions) is copied unchanged; the request
 * given is not changed. Call only with a draft that has no problems.
 */
export function applyFacts(request: unknown, draft: FactsDraft): Json {
  const copy = structuredClone(request) as Json
  const grain = cropOf(copy, 'grain')
  const cover = cropOf(copy, 'cover')
  const pasture = cropOf(copy, 'declared_margin')
  setValue(grain.price, draft.price)
  setValue(grain.cost, draft.cost)
  for (const k of FACT_KINDS) {
    setValue((grain.yield as Json)[k], draft.yields[k])
    setValue((pasture.declared_margin as Json)[k], draft.pasture[k])
  }
  setValue(cover.cost, draft.coverCost)
  setValue(copy.soil_loss_limit, draft.limit)
  return copy
}
