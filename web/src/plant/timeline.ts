import type { RotationStrip, StripCrop, StripMonth } from './rotationStrip'

/**
 * The timeline of one rotation (PROPOSED, l3/plant-redesign): the crops of a
 * strip laid on a row of months, twelve per agricultural year, so that a
 * rotation reads as seasons and years at a glance.
 *
 * Display only, from what the strip already holds (rotationStrip.ts): the
 * month and strip year of each sowing and harvest. Nothing is computed about
 * the crops. A column is one month; the first column of each year is the
 * start month of the agricultural year (C5.3). A crop takes the columns from
 * its sowing month through its harvest month. A crop whose harvest date is
 * missing takes its sowing month only and is marked open-ended: its end is
 * not guessed. Months with no crop are left empty; they are not called bare
 * soil, and no month is called winter or summer (both OPEN in
 * rotationStrip.ts).
 *
 * Crops that share a month are drawn on separate lanes, so none hides
 * another. Pure: a strip in, a timeline out.
 */

export interface TimelineBar {
  component_id: string
  crop_id: string
  /** First column, from 0. */
  from: number
  /** Last column, inclusive. */
  to: number
  /** The lane it is drawn on, from 0. */
  lane: number
  /** True when the harvest date is missing: the bar ends at its sowing month. */
  open_end: boolean
}

export interface Timeline {
  /** The calendar months (1 to 12) of one agricultural year, in column order. */
  months: number[]
  /** The number of agricultural years drawn. */
  years: number
  bars: TimelineBar[]
  /** The number of lanes used; 0 when no crop is placed. */
  lanes: number
}

const MONTHS_IN_YEAR = 12

/** The calendar months of an agricultural year that starts in this month. */
export function monthsFrom(startMonth: number): number[] {
  return Array.from({ length: MONTHS_IN_YEAR }, (_, i) => ((startMonth - 1 + i) % MONTHS_IN_YEAR) + 1)
}

function columnOf(at: StripMonth, startMonth: number): number {
  const inYear = (at.month - startMonth + MONTHS_IN_YEAR) % MONTHS_IN_YEAR
  return (at.year_index - 1) * MONTHS_IN_YEAR + inYear
}

/** The timeline of a strip (see the module comment). */
export function buildTimeline(strip: RotationStrip): Timeline {
  const start = strip.ag_year_start.month
  // A crop kept over years appears in each of them; it is one bar.
  const crops = new Map<string, StripCrop>()
  for (const year of strip.years) {
    for (const crop of year.crops) {
      if (!crops.has(crop.component_id)) crops.set(crop.component_id, crop)
    }
  }
  const spans = [...crops.values()]
    .map((crop) => {
      const from = columnOf(crop.sowing, start)
      const to = crop.harvest.kind === 'date' ? Math.max(from, columnOf(crop.harvest.at, start)) : from
      return {
        component_id: crop.component_id,
        crop_id: crop.crop_id,
        from,
        to,
        open_end: crop.harvest.kind === 'missing',
      }
    })
    .sort((a, b) => a.from - b.from || a.to - b.to)
  // Greedy lanes: the first lane whose last bar ends before this one starts.
  const laneEnds: number[] = []
  const bars: TimelineBar[] = spans.map((span) => {
    let lane = laneEnds.findIndex((end) => end < span.from)
    if (lane === -1) {
      lane = laneEnds.length
      laneEnds.push(span.to)
    } else {
      laneEnds[lane] = span.to
    }
    return { ...span, lane }
  })
  return { months: monthsFrom(start), years: strip.years.length, bars, lanes: laneEnds.length }
}
