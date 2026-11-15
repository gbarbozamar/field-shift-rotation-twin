import { describe, expect, it } from 'vitest'
import type { RotationStrip, StripCrop } from './rotationStrip'
import { buildTimeline, monthsFrom } from './timeline'

/**
 * Acceptance test of the timeline of a rotation (l3/plant-redesign).
 * PROPOSED. The strips are built by hand here: layout cases only (which
 * column and lane a bar takes), with made-up crop ids; no date of a real
 * rotation and no number of the science.
 */

function crop(
  id: string,
  sowing: [month: number, year: number],
  harvest: [month: number, year: number] | null,
  kept = false,
): StripCrop {
  return {
    component_id: id,
    position: 1,
    crop_id: `crop-${id}`,
    purpose: 'grain',
    sowing: { month: sowing[0], year_index: sowing[1] },
    harvest:
      harvest === null
        ? { kind: 'missing', missing: { reason: 'NOT_APPLICABLE' } }
        : { kind: 'date', at: { month: harvest[0], year_index: harvest[1] } },
    kept,
  }
}

function strip(startMonth: number, years: StripCrop[][]): RotationStrip {
  return {
    rotation_id: 'r',
    label: 'r',
    repeats: true,
    ag_year_start: { month: startMonth, provisional: false, provenance: 'DECLARED', source: 'user' },
    date_marks: [],
    years: years.map((crops, i) => ({ index: i + 1, ag_year: 2000 + i, crops })),
    unplaced: [],
  }
}

describe('monthsFrom', () => {
  it('lists the twelve calendar months from the start month of the agricultural year', () => {
    expect(monthsFrom(7)).toEqual([7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6])
    expect(monthsFrom(1)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
  })
})

describe('buildTimeline', () => {
  it('a crop takes the columns from its sowing month through its harvest month, counted from the start month', () => {
    // Year starts in July: November is column 4, April is column 9.
    const timeline = buildTimeline(strip(7, [[crop('a', [11, 1], [4, 1])]]))
    expect(timeline.years).toBe(1)
    expect(timeline.lanes).toBe(1)
    expect(timeline.bars).toEqual([
      { component_id: 'a', crop_id: 'crop-a', from: 4, to: 9, lane: 0, open_end: false },
    ])
  })

  it('a crop whose harvest is missing takes its sowing month only and is open-ended: its end is not guessed', () => {
    const timeline = buildTimeline(strip(7, [[crop('a', [8, 1], null)]]))
    expect(timeline.bars[0]).toMatchObject({ from: 1, to: 1, open_end: true })
  })

  it('crops that share a month go on separate lanes; crops that do not share one lane', () => {
    const shared = buildTimeline(strip(7, [[crop('a', [11, 1], [4, 1]), crop('b', [4, 1], [6, 1])]]))
    expect(shared.lanes).toBe(2)
    expect(shared.bars.map((bar) => bar.lane)).toEqual([0, 1])

    const apart = buildTimeline(strip(7, [[crop('a', [8, 1], [10, 1]), crop('b', [11, 1], [4, 1])]]))
    expect(apart.lanes).toBe(1)
    expect(apart.bars.map((bar) => bar.lane)).toEqual([0, 0])
  })

  it('a crop kept over years is one bar across them, twelve columns per year', () => {
    const kept = crop('p', [8, 1], [3, 2])
    const timeline = buildTimeline(strip(7, [[kept], [{ ...kept, kept: true }]]))
    expect(timeline.years).toBe(2)
    expect(timeline.bars).toEqual([
      { component_id: 'p', crop_id: 'crop-p', from: 1, to: 12 + 8, lane: 0, open_end: false },
    ])
  })

  it('a strip with no year has no bar and no lane', () => {
    expect(buildTimeline(strip(7, []))).toEqual({ months: monthsFrom(7), years: 0, bars: [], lanes: 0 })
  })
})
