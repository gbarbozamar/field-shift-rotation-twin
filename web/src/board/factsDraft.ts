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

/** The numbers of a grain crop the request declares no facts for (wheat, maize): all the user's. */
export interface ExtraCrop {
  price: string
  cost: string
  yields: Record<FactKind, string>
}

export interface FactsDraft {
  price: string
  cost: string
  yields: Record<FactKind, string>
  coverCost: string
  pasture: Record<FactKind, string>
  limit: string
  /** Grain crops the rotations sow that the request declares no facts for, by crop id. */
  extra: Record<string, ExtraCrop>
}

export type FactKey =
  | 'price'
  | 'cost'
  | 'coverCost'
  | 'limit'
  | `yields.${FactKind}`
  | `pasture.${FactKind}`
  | `extra.${string}.price`
  | `extra.${string}.cost`
  | `extra.${string}.yields.${FactKind}`

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
    extra: {},
  }
}

/** The crop ids a request declares economic facts for. */
export function declaredCropIds(request: unknown): string[] {
  const facts = (request as Json).economic_facts as Json
  return (facts.crops as Json[]).map((crop) => crop.crop_id as string)
}

const EMPTY_EXTRA: ExtraCrop = { price: '', cost: '', yields: { el_nino: '', neutral: '', la_nina: '' } }

/**
 * The draft with an entry for each of these crops (empty fields for a crop new
 * to it, the user's numbers kept for one already there), and no entry for any
 * other crop. Nothing is filled in: an empty field is a problem until typed.
 */
export function withExtraCrops(draft: FactsDraft, cropIds: readonly string[]): FactsDraft {
  const extra: Record<string, ExtraCrop> = {}
  for (const id of cropIds) extra[id] = draft.extra[id] ?? structuredClone(EMPTY_EXTRA)
  return { ...draft, extra }
}

function entries(draft: FactsDraft): [FactKey, string][] {
  return [
    ['price', draft.price],
    ['cost', draft.cost],
    ...FACT_KINDS.map((k): [FactKey, string] => [`yields.${k}`, draft.yields[k]]),
    ['coverCost', draft.coverCost],
    ...FACT_KINDS.map((k): [FactKey, string] => [`pasture.${k}`, draft.pasture[k]]),
    ['limit', draft.limit],
    ...Object.entries(draft.extra).flatMap(([id, crop]): [FactKey, string][] => [
      [`extra.${id}.price`, crop.price],
      [`extra.${id}.cost`, crop.cost],
      ...FACT_KINDS.map((k): [FactKey, string] => [`extra.${id}.yields.${k}`, crop.yields[k]]),
    ]),
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
  return changedFacts(a, b) === 0
}

/** The number of fields whose value differs between two drafts (a field only one of them has counts). */
export function changedFacts(a: FactsDraft, b: FactsDraft): number {
  const other = new Map(entries(b))
  const mine = entries(a)
  const differing = mine.filter(([key, text]) => !other.has(key) || Number(text) !== Number(other.get(key))).length
  const missing = [...other.keys()].filter((key) => !mine.some(([k]) => k === key)).length
  return differing + missing
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
  // Each extra grain crop is written as the soybean's entry is shaped (units, provenance), with the user's numbers.
  const crops = (copy.economic_facts as Json).crops as Json[]
  for (const [id, extra] of Object.entries(draft.extra)) {
    const entry = structuredClone(grain)
    entry.crop_id = id
    setValue(entry.price, extra.price)
    setValue(entry.cost, extra.cost)
    for (const k of FACT_KINDS) setValue((entry.yield as Json)[k], extra.yields[k])
    crops.push(entry)
  }
  return copy
}
