import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import { attributionMarkup, fieldPositions, fieldsBounds } from './geometry'
import { fieldOptions, selectedOptions } from './mapStyles'

// Static example data: the bounds never change, so the map is built once.
const FIELDS_BOUNDS = fieldsBounds(exampleCase.fields)

/**
 * Map of the fields of the example case on the OpenStreetMap base layer
 * (person decision of 14/11, no key, attribution stays visible on the map).
 * Plain leaflet, no React wrapper (person decision on the dependency set):
 * one L.polygon per field, clicking a polygon selects that field in the
 * shared selection store, and the selected polygon is highlighted. The view
 * is the bounding box of the fields, derived from the data alone — no
 * hand-picked center or zoom. Polygon styles and the viewport-based
 * container follow the design handoff package of 15 Nov 2026
 * (assets/map-styles.json, SHA256 20ab2acd...0b261d5d, and the handoff
 * manual section 5.2 for the container).
 */
export default function FieldsMap({ compact = false }: { compact?: boolean }) {
  const selectedFieldId = useSelectedFieldId()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const polygonsRef = useRef(new Map<string, L.Polygon>())

  useEffect(() => {
    const container = containerRef.current
    if (container === null || FIELDS_BOUNDS === null) return

    const map = L.map(container)
    map.fitBounds(FIELDS_BOUNDS, { padding: [12, 12] })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: attributionMarkup(),
    }).addTo(map)

    for (const field of exampleCase.fields) {
      const polygon = L.polygon(fieldPositions(field), fieldOptions).addTo(map)
      polygon.on('click', () => setSelectedFieldId(field.field_id))
      polygonsRef.current.set(field.field_id, polygon)
    }

    return () => {
      map.remove()
      polygonsRef.current.clear()
    }
  }, [])

  useEffect(() => {
    for (const field of exampleCase.fields) {
      const polygon = polygonsRef.current.get(field.field_id)
      if (polygon === undefined) continue
      polygon.setStyle(field.field_id === selectedFieldId ? selectedOptions : fieldOptions)
    }
  }, [selectedFieldId])

  if (FIELDS_BOUNDS === null) return null

  // The compact map is the small overview of the case on the entry screen.
  const size = compact ? ['h-72', 'sm:h-80', 'lg:h-[26rem]'] : ['h-[60dvh]', 'min-h-[24rem]', 'max-h-[80dvh]']
  return <div ref={containerRef} className={[...size, 'w-full', 'rounded-lg', 'border', 'border-fs-border'].join(' ')} />
}
