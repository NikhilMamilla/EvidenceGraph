import { httpGet, httpPost } from './client'
import type {
  ApiResult,
  IncidentTimelineResponse,
  PaymentOperationalStatusResponse,
  PipelineWatermarkResponse,
  SystemHealthResponse,
  SystemOperationalMetricsResponse,
  VerificationRunResponse,
} from './types'

export const fetchOperationalHealth = (): Promise<ApiResult<SystemHealthResponse>> =>
  httpGet<SystemHealthResponse>('/api/v1/operations/health')

export const fetchOperationalMetrics = (): Promise<ApiResult<SystemOperationalMetricsResponse>> =>
  httpGet<SystemOperationalMetricsResponse>('/api/v1/operations/metrics')

export const fetchPipelineStatus = (): Promise<ApiResult<PipelineWatermarkResponse>> =>
  httpGet<PipelineWatermarkResponse>('/api/v1/operations/pipeline')

export const runSystemVerification = (): Promise<ApiResult<VerificationRunResponse>> =>
  httpPost<VerificationRunResponse, {}>('/api/v1/operations/verify', {})

export const fetchOperationalIncidents = (windowHours: number = 24): Promise<ApiResult<IncidentTimelineResponse>> =>
  httpGet<IncidentTimelineResponse>(`/api/v1/operations/incidents?window_hours=${windowHours}`)

export const fetchPaymentOperationalStatus = (
  paymentId: string
): Promise<ApiResult<PaymentOperationalStatusResponse>> =>
  httpGet<PaymentOperationalStatusResponse>(`/api/v1/payments/${paymentId}/operational-status`)
