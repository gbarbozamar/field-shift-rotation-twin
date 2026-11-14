import { useEffect, useState } from 'react'

/** Current path from the URL hash, normalized to start with "/". */
function currentPath(): string {
  const raw = window.location.hash.replace(/^#/, '')
  return raw.startsWith('/') ? raw : `/${raw}`
}

/**
 * Minimal hash-based router: returns the current route ("#/rotation" ->
 * "/rotation") and re-renders on "hashchange" events.
 *
 * Hash routing is used because GitHub Pages has no index.html fallback for
 * client-side paths.
 */
export function useHashRoute(): string {
  const [path, setPath] = useState<string>(currentPath)

  useEffect(() => {
    const onChange = () => setPath(currentPath())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return path
}
