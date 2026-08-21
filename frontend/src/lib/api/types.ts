/**
 * API response type definitions.
 * Mirror the Pydantic schemas defined on the backend.
 */

export interface LivenessResponse {
  status: string
  service: string
}

export type DependencyStatus = 'connected' | 'unavailable'

export interface ReadinessResponse {
  status: string
  database: DependencyStatus
  redis: DependencyStatus
}

export interface ApiError {
  code: string
  message: string
}

export interface ApiErrorResponse {
  error: ApiError
}

/**
 * Discriminated union — the result of any API call.
 */
export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; statusCode?: number }
