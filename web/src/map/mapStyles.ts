import type { PathOptions } from 'leaflet'

/** Path style of a field polygon that is not selected (design handoff package of 15 Nov 2026, assets/map-styles.json, SHA256 20ab2acd...0b261d5d). */
export const fieldOptions: PathOptions = {
  color: '#52685d',
  fillColor: '#b9c8ae',
  fillOpacity: 0.22,
  weight: 2,
}

/** Path style of the selected field polygon (design handoff package of 15 Nov 2026, assets/map-styles.json, SHA256 20ab2acd...0b261d5d). */
export const selectedOptions: PathOptions = {
  color: '#3e7b2c',
  fillColor: '#5ba543',
  fillOpacity: 0.3,
  weight: 3,
}
