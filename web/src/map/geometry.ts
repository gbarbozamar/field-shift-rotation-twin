import type { ExampleField } from '../identity/exampleCase'
import { strings } from '../strings'

/**
 * Pure helpers of the map screen. They hold no map library import, so the
 * tests can check them in the node environment (leaflet needs a real
 * browser window).
 */

/** Leaflet bounds literal of a bounding box: [[south, west], [north, east]]. */
export type BoundsLiteral = [[number, number], [number, number]]

/** One GeoJSON ring ([lng, lat] positions) as Leaflet [lat, lng] positions. */
export function ringToPositions(ring: number[][]): [number, number][] {
  return ring.map((position): [number, number] => [position[1], position[0]])
}

/** All rings of a field geometry as leaflet polygon positions. */
export function fieldPositions(field: ExampleField): [number, number][][] {
  return field.geometry.coordinates.map(ringToPositions)
}

/**
 * Bounding box of every position of every ring of every field, as Leaflet
 * bounds. Derived from the data alone (no hand-picked center or zoom);
 * null when there is no field to show.
 */
export function fieldsBounds(fields: ExampleField[]): BoundsLiteral | null {
  if (fields.length === 0) return null
  let south = Infinity
  let west = Infinity
  let north = -Infinity
  let east = -Infinity
  for (const field of fields) {
    for (const ring of field.geometry.coordinates) {
      for (const [lng, lat] of ring) {
        if (lat < south) south = lat
        if (lat > north) north = lat
        if (lng < west) west = lng
        if (lng > east) east = lng
      }
    }
  }
  return [
    [south, west],
    [north, east],
  ]
}

/**
 * Visible attribution of the base layer: the supplied wording of the strings
 * file, linked to its copyright page. Leaflet renders the attribution of a
 * tile layer as HTML in the corner of the map.
 */
export function attributionMarkup(): string {
  const copyrightUrl = 'https://www.openstreetmap.org/copyright'
  return [
    '<a',
    `href="${copyrightUrl}"`,
    'target="_blank"',
    'rel="noreferrer">',
    strings['map.layer.attribution'],
    '</a>',
  ].join(' ')
}

/**
 * The mean Earth radius in metres (IUGG mean radius R1), the sphere the area
 * below is measured on: the usual choice of geographic area helpers.
 */
const EARTH_MEAN_RADIUS_M = 6371008.8

/** Area of one closed GeoJSON ring on the sphere, in square metres (always positive). */
function ringAreaM2(ring: number[][]): number {
  const rad = Math.PI / 180
  let sum = 0
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon1, lat1] = ring[i]
    const [lon2, lat2] = ring[i + 1]
    sum += (lon2 - lon1) * rad * (2 + Math.sin(lat1 * rad) + Math.sin(lat2 * rad))
  }
  return Math.abs((sum * EARTH_MEAN_RADIUS_M * EARTH_MEAN_RADIUS_M) / 2)
}

/**
 * The area of a field measured on its outline, in hectares: the exterior ring
 * less any holes, on the sphere of mean Earth radius. A measurement of the
 * outline as declared, not of the cultivated surface.
 */
export function fieldAreaHa(field: ExampleField): number {
  const [outer, ...holes] = field.geometry.coordinates
  const m2 = ringAreaM2(outer) - holes.reduce((total, hole) => total + ringAreaM2(hole), 0)
  return m2 / 10000
}
