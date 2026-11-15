import { strings } from '../strings'

/** Wording of the frontier showcase: keys are `frontier.<name>` in src/strings.ts. */
export type CopyKey =
  | (keyof typeof strings extends infer K ? (K extends `frontier.${infer N}` ? N : never) : never)

export function c(key: CopyKey): string {
  return strings[`frontier.${key}` as keyof typeof strings]
}
