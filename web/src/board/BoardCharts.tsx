import { CardHeader } from '../components/Card'
import { displayNumber, missingPatternText } from '../components/ValueDisplay'
import { ChartLegend, GroupedBarChart } from '../charts/BarChart'
import type { ChartGroup, ChartSeries, ChartValue } from '../charts/BarChart'
import { formatString } from '../lib/format'
import { drawnSoilVerdict, verdictTone } from '../plant/optionBars'
import { MARGINS_OF } from '../plant/plantData'
import type { MarginOf, Measured, PlantAnswer, PlantOption } from '../plant/plantData'
import { IconChart, IconLayers } from '../shell/icons'
import { strings } from '../strings'
import { unitText } from './boardModel'

/**
 * The answer in charts (l3/original-mock, PROPOSED): the margin of each
 * option by kind of year, and its soil loss by kind of year against the
 * user's limit. Display only: every bar is a value of the answer, exactly;
 * a missing value is a hatched slot with its reason; whether a soil loss is
 * over the limit is read from the answer (drawnSoilVerdict), never compared
 * here. Values filled from the example answer are marked mock.
 */

/** The colour tokens of the series, in order. */
const SERIES_COLORS = ['--fs-chart-1', '--fs-chart-2', '--fs-chart-3', '--fs-chart-4', '--fs-chart-5', '--fs-chart-6']

function kindName(kind: MarginOf): string {
  return kind === 'average' ? strings['board.kind.average'] : strings[`plant.kind.${kind}`]
}

function valueText(value: number, unit: string): string {
  return formatString(strings['chart.value_unit'], { value: displayNumber(value), unit: unitText(unit) })
}

function chartValue(item: Measured, notes: string[], flagged = false): ChartValue {
  if (item.value === null) {
    return { value: null, missingText: missingPatternText(strings['plant.table.no_value'], item.missing), notes }
  }
  return { value: item.value, notes, flagged }
}

/** The notes the soil loss of a kind carries: what the answer says of it against the limit. */
function soilNotes(option: PlantOption, kind: MarginOf): { notes: string[]; flagged: boolean } {
  const tone = verdictTone(drawnSoilVerdict(option, kind))
  if (tone === 'over') return { notes: [strings['plant.table.over_limit']], flagged: true }
  if (tone === 'open') return { notes: [strings['plant.pill.not_resolved']], flagged: false }
  if (tone === 'none') return { notes: [strings['board.kind.not_in_record']], flagged: false }
  return { notes: [], flagged: false }
}

export function BoardCharts({
  answer,
  options,
  nameOf,
  mockMarginKinds,
  mockSoilKinds,
}: {
  answer: PlantAnswer
  /** The options in the order of the columns of the table. */
  options: readonly PlantOption[]
  nameOf: (rotationId: string) => string
  mockMarginKinds: readonly string[]
  mockSoilKinds: readonly string[]
}) {
  const series: ChartSeries[] = options.map((option, index) => ({
    id: option.rotation_id,
    label: nameOf(option.rotation_id),
    color: `var(${SERIES_COLORS[index % SERIES_COLORS.length]})`,
  }))
  const mock = strings['mock.badge']
  const first = options[0]
  const marginUnit = first.margin[answer.margin_of].unit
  const soilUnit = first.soil_loss[answer.margin_of].unit
  const marginGroups: ChartGroup[] = MARGINS_OF.map((kind) => {
    const mocked = mockMarginKinds.includes(kind)
    return {
      id: kind,
      label: kindName(kind),
      emphasis: kind === answer.margin_of,
      tag: mocked ? mock : undefined,
      values: options.map((option) => chartValue(option.margin[kind], mocked ? [mock] : [])),
    }
  })
  const soilGroups: ChartGroup[] = MARGINS_OF.map((kind) => {
    const mocked = mockSoilKinds.includes(kind)
    return {
      id: kind,
      label: kindName(kind),
      emphasis: kind === answer.margin_of,
      tag: mocked ? mock : undefined,
      values: options.map((option) => {
        const { notes, flagged } = soilNotes(option, kind)
        return chartValue(option.soil_loss[kind], mocked ? [...notes, mock] : notes, flagged)
      }),
    }
  })
  // Every option is judged against one limit (a rule of the contract): the first that carries it speaks for the chart.
  const limited = options.find((option) => option.limit !== null)
  const reference =
    limited !== undefined && limited.limit !== null
      ? { value: limited.limit, label: formatString(strings['board.charts.limit'], { value: valueText(limited.limit, limited.limit_unit) }) }
      : null
  return (
    <div data-testid="board-charts">
      <div className="grid gap-4 xl:grid-cols-2">
        <section data-testid="board-chart-margin" className="fs-card px-5 py-4">
          <CardHeader icon={IconChart} title={strings['board.charts.margin']} aside={<span className="text-xs text-fs-muted">{unitText(marginUnit)}</span>} />
          <ChartLegend series={series} />
          <div className="mt-3">
            <GroupedBarChart label={strings['board.charts.margin']} series={series} groups={marginGroups} format={(v) => valueText(v, marginUnit)} />
          </div>
        </section>
        <section data-testid="board-chart-soil" className="fs-card px-5 py-4">
          <CardHeader icon={IconLayers} title={strings['board.charts.soil']} aside={<span className="text-xs text-fs-muted">{unitText(soilUnit)}</span>} />
          <ChartLegend series={series} />
          <div className="mt-3">
            <GroupedBarChart
              label={strings['board.charts.soil']}
              series={series}
              groups={soilGroups}
              format={(v) => valueText(v, soilUnit)}
              reference={reference}
            />
          </div>
        </section>
      </div>
      <p className="mt-2 text-xs text-fs-muted">{strings['board.charts.note']}</p>
    </div>
  )
}
