import mock from './mock.json'

export const M = mock

export type Risk = 'low' | 'medium' | 'high'

/** Display rule of the showcase: frost and heat-stress days of the month. */
export function monthRisk(month: number): Risk {
  const n = M.clocks.frost[month] + M.clocks.heat[month]
  return n >= 3 ? 'high' : n >= 1 ? 'medium' : 'low'
}

const ORDER: Risk[] = ['low', 'medium', 'high']

/** Worst flowering risk across the flowering months of a rotation. */
export function rotationRisk(rotationIndex: number): Risk {
  let worst = 0
  for (const year of M.rotations[rotationIndex].years) {
    for (const seg of year) {
      const flower = seg[4] as number
      if (flower >= 0) worst = Math.max(worst, ORDER.indexOf(monthRisk(flower)))
    }
  }
  return ORDER[worst]
}

export type Verdict = 'robust' | 'conditional' | 'abstain'

const P = M.price
const BASE = M.base.margin

function marginAt(i: 0 | 1, price: number, scale: number): number {
  return BASE[i] * scale + P.slope[i] * (price - P.ref)
}

/** Price at which rotations 1 and 2 earn the same margin. */
export function tippingPrice(extreme: boolean): number {
  const s0 = extreme ? P.extremeScale[0] : 1
  const s1 = extreme ? P.extremeScale[1] : 1
  return P.ref + (BASE[1] * s1 - BASE[0] * s0) / (P.slope[0] - P.slope[1])
}

export interface View {
  leader: 0 | 1 | null
  gap: number
}

export function viewAt(price: number, extreme: boolean): View {
  const s0 = extreme ? P.extremeScale[0] : 1
  const s1 = extreme ? P.extremeScale[1] : 1
  const gap = marginAt(0, price, s0) - marginAt(1, price, s1)
  if (Math.abs(price - tippingPrice(extreme)) <= P.band) return { leader: null, gap }
  return { leader: gap > 0 ? 0 : 1, gap }
}

export function verdictAt(price: number): Verdict {
  const a = viewAt(price, false)
  const e = viewAt(price, true)
  if (a.leader === null && e.leader === null) return 'abstain'
  if (a.leader !== null && a.leader === e.leader) return 'robust'
  return 'conditional'
}

/** Value of information of a measure, recalculated from the tried price. */
export function voiAt(base: number, price: number): number {
  const d = (Math.abs(price - tippingPrice(false)) + Math.abs(price - tippingPrice(true))) / 2
  const f = Math.max(0.15, 1 - d / (P.band * 4))
  return Math.round(base * f * 10) / 10
}

/** The centre of the bounding box of an SVG points list, where a field's name is drawn. */
export function labelPoint(points: string): [number, number] {
  const xy = points.split(' ').map((pair) => pair.split(',').map(Number))
  const xs = xy.map((p) => p[0])
  const ys = xy.map((p) => p[1])
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]
}
