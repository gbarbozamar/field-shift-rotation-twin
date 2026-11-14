/**
 * Base URL of the backend API.
 *
 * Resolved at build time from VITE_API_URL. When the variable is not set
 * (local development), the recorded default http://localhost:8000 is used.
 */
export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
