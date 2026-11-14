import { ValueDisplay } from '../components/ValueDisplay'
import type { ValueItem } from '../components/ValueDisplay'
import { useSelectedFieldId } from '../identity/selection'
import { formatString } from '../lib/format'
import { strings } from '../strings'
import type { MonthlySeries, MonthlyValue } from './siteData'
import { siteClimate, siteSoilSlope } from './siteData'

/**
 * The site sheet of the selected field (issue #108): the climate monthly
 * series and the soil-and-slope values of the site-data contract examples,
 * every value through the shared value display — its unit, provenance label
 * and source, its range or the assumption mark — and every absence as a
 * missing value with its reason, never zero or blank.
 *
 * The sheet hangs under the fields screen, after the field list, and follows
 * the shared selection: no field selected shows the select hint, a selected
 * field shows the site data. The examples are the only site data there is
 * and describe their own placeholder field, so they are shown under the
 * example banner, driven by their example_data flag (see siteData.ts).
 *
 * All user-visible wording lives in strings.ts; the year-month label of a
 * month row is the calendar position of the value in the contract (C5.1),
 * rendered as data, not wording.
 */

/** The identity of one month of a series: the calendar position C5.1 defines. */
function monthLabel(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

/**
 * The value item of one month: the month's number, or its missing part, on
 * the unit of its series. What the series states once for all its present
 * values — provenance label, source or assumption mark, and the reason the
 * values carry no range — travels with the item (C2.2, C4.1, C4.2); the
 * parser of siteData.ts guarantees it is there when a value is.
 */
function monthItem(series: MonthlySeries, month: MonthlyValue): ValueItem {
  if (month.value === null) {
    if (month.missing === undefined) {
      throw new Error(`invalid-month[${monthLabel(month.year, month.month)}]:missing-part-absent`)
    }
    return { value: null, unit: series.unit, missing: month.missing }
  }
  if (series.provenance === undefined) {
    throw new Error(`invalid-series[${series.quantity}]:provenance-absent`)
  }
  return {
    value: month.value,
    unit: series.unit,
    provenance: series.provenance,
    source: series.source,
    assumption: series.assumption === true ? true : undefined,
    range_missing: series.range_missing,
  }
}

/** One monthly series: its heading, its month count, and one row per month. */
export function MonthlySeriesBlock({ series }: { series: MonthlySeries }) {
  return (
    <div data-testid="monthly-series" className="mt-3">
      <h4 data-testid="series-heading" className="text-sm font-semibold">
        {formatString(strings['site.series_heading'], {
          quantity: series.quantity,
          unit: series.unit,
        })}
      </h4>
      <p data-testid="series-months-count" className="mt-1 text-xs text-slate-500">
        {formatString(strings['site.months_count'], { count: series.months.length })}
      </p>
      <ul className="mt-2 space-y-2">
        {series.months.map((month) => {
          const label = monthLabel(month.year, month.month)
          return (
            <li key={label} data-testid="month-row" className="flex gap-3">
              <span data-testid="month-label" className="font-mono text-sm text-slate-500">
                {label}
              </span>
              <ValueDisplay what={`${series.quantity} ${label}`} item={monthItem(series, month)} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** The site sheet: the select hint when nothing is selected, the data when a field is. */
export default function SiteSheet() {
  const selectedFieldId = useSelectedFieldId()

  return (
    <section aria-labelledby="site-sheet-title" className="mt-8">
      <h3 id="site-sheet-title" className="text-base font-semibold">
        {strings['site.title']}
      </h3>
      {selectedFieldId === null ? (
        <p data-testid="site-select-hint" className="mt-1 text-sm text-slate-500">
          {strings['site.select_hint']}
        </p>
      ) : (
        <div className="mt-3">
          {(siteClimate.example_data || siteSoilSlope.example_data) && (
            <div
              role="note"
              className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
            >
              <p data-testid="site-example-banner" className="text-sm text-amber-900">
                {strings['example.banner']}
              </p>
            </div>
          )}

          <div className="mt-4">
            <h4 className="text-sm font-semibold">{strings['site.climate_section']}</h4>
            {siteClimate.monthly_series.map((series) => (
              <MonthlySeriesBlock key={series.quantity} series={series} />
            ))}
          </div>

          <div className="mt-4">
            <h4 className="text-sm font-semibold">{strings['site.soil_section']}</h4>
            <div className="mt-2 space-y-2">
              <ValueDisplay
                what={strings['site.slope_length']}
                item={siteSoilSlope.slope_length}
              />
              <ValueDisplay
                what={strings['site.slope_steepness']}
                item={siteSoilSlope.slope_steepness}
              />
              {siteSoilSlope.soil_properties.map((property) => (
                <ValueDisplay key={property.quantity} what={property.quantity} item={property} />
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
