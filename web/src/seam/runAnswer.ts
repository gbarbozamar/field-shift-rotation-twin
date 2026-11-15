import { useSyncExternalStore } from 'react'

/**
 * Shared answered state of the platform-route run. The seam's mutation and
 * the stage rail are parts of the same screen that both need to know
 * whether a run has answered, so instead of lifting the state between them
 * the flag lives here as a tiny store: the seam writes true through
 * setRunAnswered once its run has an answer, and every reader reads through
 * useRunAnswered, re-rendering on every change.
 */

let runAnswered = false
const listeners = new Set<() => void>()

/** Subscribe to answer changes; the returned function unsubscribes. */
export function subscribeToRunAnswer(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** True when the seam's run has an answer; false until then. */
export function getRunAnswered(): boolean {
  return runAnswered
}

/** Record whether the seam's run has an answer. */
export function setRunAnswered(answered: boolean): void {
  runAnswered = answered
  for (const listener of listeners) listener()
}

/** React binding: the shared answered flag, re-rendered on every change. */
export function useRunAnswered(): boolean {
  return useSyncExternalStore(subscribeToRunAnswer, getRunAnswered, getRunAnswered)
}
