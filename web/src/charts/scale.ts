/**
 * The scales of the chart kit (l3/original-mock). Display only: where a
 * value falls on the plot and which round numbers mark the axis. Nothing
 * here computes a value of the answer.
 */

/** The step between two ticks: 1, 2, 2.5 or 5 times a power of ten, the smallest that gives at most `count` intervals. */
export function niceStep(span: number, count: number): number {
  if (!(span > 0) || !Number.isFinite(span)) {
    return 1
  }
  const raw = span / Math.max(1, count)
  const power = 10 ** Math.floor(Math.log10(raw))
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (factor * power >= raw - 1e-12) {
      return factor * power
    }
  }
  return 10 * power
}

/** Rounds away the binary noise of a multiple of the step (0.30000000000000004 to 0.3). */
function clean(value: number): number {
  return Number.parseFloat(value.toPrecision(12))
}

/**
 * Round ticks that cover [low, high] and always include zero: the bars of
 * the kit grow from zero, so zero is always on the axis.
 */
export function niceTicks(low: number, high: number, count = 5): number[] {
  const min = Math.min(0, low)
  const max = Math.max(0, high)
  if (min === max) {
    return [0, 1]
  }
  const step = niceStep(max - min, count)
  const first = Math.floor(min / step + 1e-9) * step
  const last = Math.ceil(max / step - 1e-9) * step
  const ticks: number[] = []
  for (let n = 0; first + n * step <= last + step * 1e-9; n++) {
    ticks.push(clean(first + n * step))
  }
  return ticks.map((tick) => (Object.is(tick, -0) ? 0 : tick))
}

/**
 * The ticks of a plot of these values and reference lines: missing values
 * (null) take no part, so a missing value never stretches or shrinks the
 * axis as a zero would.
 */
export function chartTicks(values: readonly (number | null)[], references: readonly number[] = [], count = 5): number[] {
  const present = [...values.filter((value): value is number => value !== null), ...references]
  if (present.length === 0) {
    return [0, 1]
  }
  return niceTicks(Math.min(...present), Math.max(...present), count)
}

/** A linear map from the domain [d0, d1] to the range [r0, r1]; a flat domain maps to r0. */
export function linearScale(domain: readonly [number, number], range: readonly [number, number]): (value: number) => number {
  const [d0, d1] = domain
  const [r0, r1] = range
  if (d1 === d0) {
    return () => r0
  }
  return (value) => r0 + ((value - d0) / (d1 - d0)) * (r1 - r0)
}

/** A tick as the axis prints it: thousands shortened (12k), otherwise the number as it is. */
export function tickText(tick: number): string {
  const size = Math.abs(tick)
  if (size >= 1_000_000) return `${clean(tick / 1_000_000)}M`
  if (size >= 10_000) return `${clean(tick / 1_000)}k`
  return String(clean(tick))
}
