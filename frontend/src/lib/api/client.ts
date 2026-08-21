/**
 * Core HTTP client.
 *
 * All fetch calls go through this module — never use raw fetch() in components.
 * Handles: timeout, HTTP errors, JSON parsing errors, network errors.
 */

import { API_BASE_URL, API_TIMEOUT_MS } from './config'
import type { ApiResult } from './types'

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResult<T>> {
  const url = `${API_BASE_URL}${path}`
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
    })

    clearTimeout(timeoutId)

    let body: unknown
    try {
      body = await response.json()
    } catch {
      return {
        ok: false,
        error: 'Received a non-JSON response from the server.',
        statusCode: response.status,
      }
    }

    if (!response.ok) {
      const errBody = body as { error?: { message?: string } }
      const message =
        errBody?.error?.message ??
        `Request failed with status ${response.status}`
      return { ok: false, error: message, statusCode: response.status }
    }

    return { ok: true, data: body as T }
  } catch (err: unknown) {
    clearTimeout(timeoutId)

    if (err instanceof DOMException && err.name === 'AbortError') {
      return { ok: false, error: 'Request timed out. Is the backend running?' }
    }

    const message =
      err instanceof Error ? err.message : 'Unknown network error.'
    return { ok: false, error: `Network error: ${message}` }
  }
}

export const httpGet = <T>(path: string): Promise<ApiResult<T>> =>
  request<T>(path, { method: 'GET' })
