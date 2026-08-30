import { httpGet } from './client'
import type { ApiResult, LivenessResponse, RazorpayStatus, ReadinessResponse } from './types'

export const fetchLiveness = (): Promise<ApiResult<LivenessResponse>> =>
  httpGet<LivenessResponse>('/api/v1/health/live')

export const fetchReadiness = (): Promise<ApiResult<ReadinessResponse>> =>
  httpGet<ReadinessResponse>('/api/v1/health/ready')

export const fetchRazorpayStatus = (): Promise<ApiResult<RazorpayStatus>> =>
  httpGet<RazorpayStatus>('/api/v1/integrations/razorpay/status')
