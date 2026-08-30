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

export interface RazorpayStatus {
  configured: boolean
  mode: string
  key_id_prefix: string
  last_verified_event_at: string | null
  events_received: number
  events_processed: number
  events_rejected: number
  events_duplicate: number
}

export interface ApiError {
  code: string
  message: string
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; statusCode?: number }

// Phase 19 Operations Types
export type HealthState = 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY' | 'UNKNOWN'
export type ProcessingFreshnessState = 'CURRENT' | 'STALE' | 'PROCESSING' | 'UNKNOWN'
export type VerificationStatus = 'PASS' | 'WARN' | 'FAIL' | 'UNKNOWN'

export interface ComponentHealth {
  component: string
  state: HealthState
  reason: string
  checked_at: string
  metrics?: Record<string, any>
  methodology_version?: string
}

export interface SystemHealthResponse {
  overall_state: HealthState
  summary: string
  checked_at: string
  components: Record<string, ComponentHealth>
  methodology_version: string
}

export interface IngestionOperationalMetrics {
  total_received: number
  total_verified: number
  total_rejected: number
  total_duplicates: number
  total_processed: number
  total_failed: number
  last_received_at: string | null
  last_verified_at: string | null
  last_processed_at: string | null
  recent_events_count_1h: number
}

export interface QueueMetrics {
  queue_name: string
  queue_depth: number
  oldest_event_age_seconds: number | null
  is_backlogged: boolean
}

export interface ProcessingLagMetrics {
  average_lag_seconds: number | null
  latest_lag_seconds: number | null
  max_recent_lag_seconds: number | null
}

export interface SystemOperationalMetricsResponse {
  timestamp: string
  ingestion: IngestionOperationalMetrics
  queue: QueueMetrics
  lag: ProcessingLagMetrics
  stuck_events_count: number
  failed_events_count: number
  active_payments_count: number
  active_facts_count: number
}

export interface PipelineStageStatus {
  stage_name: string
  component: string
  state: HealthState
  freshness: ProcessingFreshnessState
  last_processed_at: string | null
  details?: Record<string, any>
}

export interface PipelineWatermarkResponse {
  timestamp: string
  pipeline_watermark_timestamp: string | null
  stages: PipelineStageStatus[]
  is_pipeline_caught_up: boolean
  summary: string
}

export interface DownstreamLayerStatus {
  layer_name: string
  status: ProcessingFreshnessState
  latest_evaluation_at: string | null
  is_current: boolean
  details?: Record<string, any>
}

export interface PaymentOperationalStatusResponse {
  payment_id: string
  latest_evidence_at: string | null
  latest_canonical_at: string | null
  overall_freshness: ProcessingFreshnessState
  is_analysis_current: boolean
  pipeline_lag_seconds: number | null
  layers: Record<string, DownstreamLayerStatus>
  summary: string
}

export interface VerificationCheckResult {
  check_id: string
  invariant_name: string
  status: VerificationStatus
  reason: string
  checked_at: string
  affected_scope: string
  metrics?: Record<string, any>
}

export interface VerificationRunResponse {
  timestamp: string
  overall_status: VerificationStatus
  total_checks: number
  passed_count: number
  warn_count: number
  failed_count: number
  checks: VerificationCheckResult[]
}

export interface OperationalIncident {
  incident_id: string
  category: string
  severity: string
  component: string
  detected_at: string
  description: string
  evidence: Record<string, any>
  resolved: boolean
  resolved_at: string | null
}

export interface IncidentTimelineResponse {
  timestamp: string
  active_incidents_count: number
  incidents: OperationalIncident[]
}
