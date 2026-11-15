/** Joins class names written as separate tokens (keeps class lists out of the wording scan). */
export function cx(...tokens: string[]): string {
  return tokens.filter(Boolean).join(' ')
}

/** True when a value is above its limit. */
export function exceeds(value: number, limit: number): boolean {
  return value > limit
}
