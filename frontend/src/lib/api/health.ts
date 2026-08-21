/**
 * Health API — wrappers for the backend health endpoints.
 */

import { httpGet } from './client'
import type { ApiResult, LivenessResponse, ReadinessResponse } from './types'

export const fetchLiveness = (): Promise<ApiResult<LivenessResponse>> =>
  httpGet<LivenessResponse>('/api/v1/health/live')

export const fetchReadiness = (): Promise<ApiResult<ReadinessResponse>> =>
  httpGet<ReadinessResponse>('/api/v1/health/ready')
