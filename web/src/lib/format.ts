/**
 * Pure placeholder substitution for the string templates of strings.ts.
 *
 * A template carries placeholders in braces, for example "Source: {source}"
 * or "Current hash route: {route}". Placeholders may contain spaces, as in
 * the "{reason phrase}" of the missing-value pattern.
 *
 * A placeholder whose value is absent stays visible exactly as written.
 * Nothing is ever invented to fill a gap.
 */
export function formatString(
  template: string,
  params: Record<string, string | number>,
): string {
  return template.replace(/\{[^{}]+\}/g, (placeholder) => {
    const name = placeholder.slice(1, -1)
    return Object.hasOwn(params, name) ? String(params[name]) : placeholder
  })
}
