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

/** How a crop the request declares no facts for is priced: a grain (price, cost, yields) or a declared margin (a forage). */
export type ExtraKind = 'grain' | 'declared_margin'

/** A crop the rotations sow that the request declares no facts for, and how it is priced. */
export interface ExtraCropRef {
  id: string
  kind: ExtraKind
}

/** The numbers of a crop the request declares no facts for (wheat, maize, alfalfa): all the user's. */
export interface ExtraCrop {
  kind: ExtraKind
  price: string
  cost: string
  yields: Record<FactKind, string>
  /** The margin by kind of year, for a declared-margin crop. */
  margins: Record<FactKind, string>
}

export interface FactsDraft {
  price: string
  cost: string
  yields: Record<FactKind, string>
  coverCost: string
  pasture: Record<FactKind, string>
  limit: string
  /** The soybean prices the tipping price is searched between (the request's soybean_price_range). */
  priceLow: string
  priceHigh: string
  /** The rain factor of the stress test, or null when the request declares none to send. */
  rain: string | null
  /** Grain crops the rotations sow that the request declares no facts for, by crop id. */
  extra: Record<string, ExtraCrop>
}

export type FactKey =
  | 'price'
  | 'cost'
  | 'coverCost'
  | 'limit'
  | 'priceLow'
  | 'priceHigh'
  | 'rain'
  | `yields.${FactKind}`
  | `pasture.${FactKind}`
  | `extra.${string}.price`
  | `extra.${string}.cost`
  | `extra.${string}.yields.${FactKind}`
  | `extra.${string}.margins.${FactKind}`

export interface FactProblem {
  key: FactKey
  kind: 'not_a_number' | 'negative' | 'not_positive' | 'range_order' | 'price_outside_range'
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
    priceLow: String(((req.questions as Json).soybean_price_range as Json).low),
    priceHigh: String(((req.questions as Json).soybean_price_range as Json).high),
    rain: ((req.questions as Json).rain_stress_factor as Json | null) === null ? null : valueText((req.questions as Json).rain_stress_factor),
    extra: {},
  }
}

/** The crop ids a request declares economic facts for. */
export function declaredCropIds(request: unknown): string[] {
  const facts = (request as Json).economic_facts as Json
  return (facts.crops as Json[]).map((crop) => crop.crop_id as string)
}

function emptyExtra(kind: ExtraKind): ExtraCrop {
  const none = { el_nino: '', neutral: '', la_nina: '' }
  return { kind, price: '', cost: '', yields: { ...none }, margins: { ...none } }
}

/**
 * The draft with an entry for each of these crops (empty fields for a crop new
 * to it, the user's numbers kept for one already there), and no entry for any
 * other crop. Nothing is filled in: an empty field is a problem until typed.
 */
export function withExtraCrops(draft: FactsDraft, crops: readonly ExtraCropRef[]): FactsDraft {
  const extra: Record<string, ExtraCrop> = {}
  for (const { id, kind } of crops) extra[id] = draft.extra[id]?.kind === kind ? draft.extra[id] : emptyExtra(kind)
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
    ['priceLow', draft.priceLow],
    ['priceHigh', draft.priceHigh],
    ...(draft.rain === null ? [] : [['rain', draft.rain] as [FactKey, string]]),
    ...Object.entries(draft.extra).flatMap(([id, crop]): [FactKey, string][] =>
      crop.kind === 'grain'
        ? [
            [`extra.${id}.price`, crop.price],
            [`extra.${id}.cost`, crop.cost],
            ...FACT_KINDS.map((k): [FactKey, string] => [`extra.${id}.yields.${k}`, crop.yields[k]]),
          ]
        : FACT_KINDS.map((k): [FactKey, string] => [`extra.${id}.margins.${k}`, crop.margins[k]]),
    ),
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
    } else if ((key === 'limit' || key === 'rain') && value <= 0) {
      problems.push({ key, kind: 'not_positive' })
    } else if (!key.startsWith('pasture.') && !key.includes('.margins.') && key !== 'limit' && value < 0) {
      problems.push({ key, kind: 'negative' })
    }
  }
  // The tipping price is searched between the two prices: they must be in order, around today's price.
  const [low, high, price] = [Number(draft.priceLow), Number(draft.priceHigh), Number(draft.price)]
  if ([low, high, price].every(Number.isFinite) && !problems.some((p) => ['priceLow', 'priceHigh', 'price'].includes(p.key))) {
    if (low >= high) problems.push({ key: 'priceHigh', kind: 'range_order' })
    else if (price < low || price > high) problems.push({ key: 'price', kind: 'price_outside_range' })
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
  rain: string
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
    rain: ((req.questions as Json).rain_stress_factor as Json | null) === null ? '' : unitOf((req.questions as Json).rain_stress_factor),
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
  const questions = copy.questions as Json
  const range = questions.soybean_price_range as Json
  range.low = Number(draft.priceLow)
  range.high = Number(draft.priceHigh)
  if (draft.rain !== null && questions.rain_stress_factor !== null && questions.rain_stress_factor !== undefined) {
    setValue(questions.rain_stress_factor, draft.rain)
  }
  // Each extra crop is written as the request's crop of its kind is shaped (units, provenance), with the user's numbers.
  const crops = (copy.economic_facts as Json).crops as Json[]
  for (const [id, extra] of Object.entries(draft.extra)) {
    const entry = structuredClone(extra.kind === 'grain' ? grain : pasture)
    entry.crop_id = id
    if (extra.kind === 'grain') {
      setValue(entry.price, extra.price)
      setValue(entry.cost, extra.cost)
      for (const k of FACT_KINDS) setValue((entry.yield as Json)[k], extra.yields[k])
    } else {
      for (const k of FACT_KINDS) setValue((entry.declared_margin as Json)[k], extra.margins[k])
    }
    crops.push(entry)
  }
  return copy
}
