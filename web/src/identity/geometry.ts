/**
 * Pure geometry helpers for the identity screen.
 *
 * The area shown per field is DERIVED data (contracts/CONVENTIONS.md C4.1):
 * it is computed from the polygon boundary in the app and never stored.
 */

/** A GeoJSON position: [longitude, latitude] in degrees (elevation ignored). */
export type Position = number[]

/** Minimal GeoJSON Polygon geometry: exterior ring first, then holes. */
export interface PolygonGeometry {
  type: 'Polygon'
  coordinates: Position[][]
}

/** Mean Earth radius in metres (spherical approximation). */
const EARTH_RADIUS_M = 6_371_000

const DEGREES_TO_RADIANS = Math.PI / 180

function toRadians(degrees: number): number {
  return degrees * DEGREES_TO_RADIANS
}

/**
 * Absolute spherical area of one closed ring, in square metres.
 *
 * Green's theorem on the sphere: area = R² · |∮ sin(latitude) dlongitude|.
 * The line integral is discretised with the trapezoid rule: each vertex is
 * weighted by the longitude span between its two neighbours. This is exact
 * for the small polygons of this prototype (no projection involved).
 */
function ringAreaSquareMetres(ring: Position[]): number {
  if (ring.length < 3) {
    return 0
  }
  const vertexCount = ring.length
  let integral = 0
  for (let i = 0; i < vertexCount; i++) {
    const previous = ring[(i - 1 + vertexCount) % vertexCount]
    const next = ring[(i + 1) % vertexCount]
    const longitudeSpan = toRadians(next[0]) - toRadians(previous[0])
    integral += longitudeSpan * Math.sin(toRadians(ring[i][1]))
  }
  return (Math.abs(integral) / 2) * EARTH_RADIUS_M ** 2
}

/** Area of a GeoJSON polygon (exterior ring minus holes) in square metres. */
export function polygonAreaSquareMetres(geometry: PolygonGeometry): number {
  const [exterior, ...holes] = geometry.coordinates
  if (!exterior) {
    return 0
  }
  let total = ringAreaSquareMetres(exterior)
  for (const hole of holes) {
    total -= ringAreaSquareMetres(hole)
  }
  return Math.max(total, 0)
}

/** Area of a GeoJSON polygon in hectares (1 ha = 10,000 m²). */
export function polygonAreaHectares(geometry: PolygonGeometry): number {
  return polygonAreaSquareMetres(geometry) / 10_000
}

/** Display form of an area in hectares, rounded to one decimal place. */
export function formatHectares(hectares: number): string {
  return hectares.toFixed(1)
}
