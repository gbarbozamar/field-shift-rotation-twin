/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. Falls back to http://localhost:8000. */
  readonly VITE_API_URL?: string
  readonly VITE_MOCK_FILL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
