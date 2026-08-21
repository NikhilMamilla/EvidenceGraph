/**
 * API client configuration.
 *
 * The base URL is read from the VITE_API_BASE_URL environment variable.
 * In local dev, Vite proxies /api/* to the backend, so BASE_URL can be empty.
 * In Docker / production builds, VITE_API_BASE_URL is set at build time.
 */

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? ''

export const API_TIMEOUT_MS = 8_000
