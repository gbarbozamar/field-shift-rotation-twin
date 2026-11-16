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

/** The result document of the seam's last answered run, with the field it was run for. */
export interface RunResult {
  fieldId: string
  /** The envelope's result exactly as the route answered it (a results-per-rotation document), or null with none. */
  result: unknown
}

let runResult: RunResult | null = null

/** The last run's result; null before any run has answered. */
export function getRunResult(): RunResult | null {
  return runResult
}

/** Record the result of the run that just answered (the seam writes it, the result cards read it). */
export function setRunResult(value: RunResult | null): void {
  runResult = value
  for (const listener of listeners) listener()
}

/** React binding: the last run's result, re-rendered on every change. */
export function useRunResult(): RunResult | null {
  return useSyncExternalStore(subscribeToRunAnswer, getRunResult, getRunResult)
}
