import { useSyncExternalStore } from 'react'

/**
 * Shared selected-field state of the fields screen. The field list and the
 * map are siblings that show the same selection, so instead of lifting the
 * state between them the selection lives here as a tiny store: both write
 * through setSelectedFieldId and read through useSelectedFieldId, and every
 * change re-renders whichever of the two is on screen.
 */

let selectedFieldId: string | null = null
const listeners = new Set<() => void>()

/** Subscribe to selection changes; the returned function unsubscribes. */
export function subscribeToSelection(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Current selection: a field identifier, or null when nothing is selected. */
export function getSelectedFieldId(): string | null {
  return selectedFieldId
}

/** Select a field by its identifier, or clear the selection with null. */
export function setSelectedFieldId(fieldId: string | null): void {
  selectedFieldId = fieldId
  for (const listener of listeners) listener()
}

/** React binding: the shared selection, re-rendered on every change. */
export function useSelectedFieldId(): string | null {
  return useSyncExternalStore(subscribeToSelection, getSelectedFieldId, getSelectedFieldId)
}
