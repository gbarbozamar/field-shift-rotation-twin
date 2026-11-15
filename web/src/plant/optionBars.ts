/**
 * The widths of the bars of the option rows (S-020, PROPOSED). Display only:
 * nothing is computed but the share of a bar, from values the answer carries.
 *
 * A bar is drawn only for a value that is present; a missing value gives no
 * bar (its reason is shown instead), and is never read as 0. The scale of a
 * set of bars is the largest absolute value present in it; with no value
 * present there is no scale, hence no bar.
 */

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
