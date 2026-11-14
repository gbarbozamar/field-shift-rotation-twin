import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { exampleCase } from '../identity/exampleCase'
import { setSelectedFieldId, useSelectedFieldId } from '../identity/selection'
import { attributionMarkup, fieldPositions, fieldsBounds } from './geometry'

// Static example data: the bounds never change, so the map is built once.
const FIELDS_BOUNDS = fieldsBounds(exampleCase.fields)

/** Path style of a field polygon that is not selected (slate outline). */
const baseOptions = { color: '#475569', fillColor: '#94a3b8', fillOpacity: 0.25, weight: 2 }

/** Path style of the selected field polygon (emerald, like the list highlight). */
const selectedOptions = { color: '#059669', fillColor: '#10b981', fillOpacity: 0.45, weight: 3 }

/**
 * Map of the fields of the example case on the OpenStreetMap base layer
 * (person decision of 14/11, no key, attribution stays visible on the map).
 * Plain leaflet, no React wrapper (person decision on the dependency set):
 * one L.polygon per field, clicking a polygon selects that field in the
 * shared selection store, and the selected polygon is highlighted. The view
 * is the bounding box of the fields, derived from the data alone — no
 * hand-picked center or zoom.
 */
export default function FieldsMap() {
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
      const polygon = L.polygon(fieldPositions(field), baseOptions).addTo(map)
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
      polygon.setStyle(field.field_id === selectedFieldId ? selectedOptions : baseOptions)
    }
  }, [selectedFieldId])

  if (FIELDS_BOUNDS === null) return null

  return <div ref={containerRef} className="h-96 w-full rounded-lg border border-slate-200" />
}
