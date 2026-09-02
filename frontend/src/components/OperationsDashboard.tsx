/**
 * OperationsDashboard Component — Glassmorphism + Neomorphism Design
 *
 * Real-Time Operational Intelligence & Continuous Verification:
 * - System & Dependency Health (DB, Redis, Worker, Pipeline)
 * - Live Ingestion & Processing Metrics (Queue depth, lag, error rate)
 * - End-to-End Pipeline Visualization & Watermark
 * - Continuous System Invariant Verification (10 formal invariant checks)
 * - Operational Incidents Timeline
 *
 * 100% Real Runtime State — Zero Fabricated Data.
 */

import { useEffect, useState } from 'react'
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import {
  fetchOperationalHealth,
  fetchOperationalIncidents,
  fetchOperationalMetrics,
  fetchPipelineStatus,
  runSystemVerification,
} from '../lib/api'
import type {
  HealthState,
  IncidentTimelineResponse,
  PipelineWatermarkResponse,
  SystemHealthResponse,
  SystemOperationalMetricsResponse,
  VerificationRunResponse,
} from '../lib/api'

const POLL_INTERVAL_MS = 8_000

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return s > 0 ? `${m}m ${s}s` : `${m}m`
  }
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600)
    const m = Math.round((seconds % 3600) / 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }
  const d = Math.floor(seconds / 86400)
  const h = Math.round((seconds % 86400) / 3600)
  return h > 0 ? `${d}d ${h}h` : `${d}d`
}

/* ── Metric Card with Neomorphism ────────────────────────────────── */
function MetricCard({
  label,
  value,
  subtext,
  accent,
}: {
  label: string
  value: string | number
  subtext?: string
  accent: string
}) {
  // The icon box used to sit beside the label in a flex row. At lg:grid-cols-6
  // that left the label roughly 90px and it wrapped mid-word. Dropping the icon
  // gives the label the full card width, so nothing breaks.
  const accentVar: Record<string, string> = {
    indigo: 'var(--color-accent-primary)',
    emerald: 'var(--color-success)',
    amber: 'var(--color-warning)',
    rose: 'var(--color-danger)',
    slate: 'var(--color-text-primary)',
  }
  const color = accentVar[accent] || accentVar.slate

  return (
    <div className="metric-card group flex flex-col justify-between gap-2 p-4">
      <span
        className="text-[10px] font-semibold uppercase leading-tight tracking-[0.08em]"
        style={{ color: 'var(--color-text-tertiary)' }}
      >
        {label}
      </span>
      <div
        className="text-xl font-extrabold leading-none tracking-tight sm:text-2xl"
        style={{ color, fontFamily: 'var(--font-display)' }}
      >
        {value}
      </div>
      {subtext && (
        <span className="text-[10px] leading-tight" style={{ color: 'var(--color-text-tertiary)' }}>
          {subtext}
        </span>
      )}
    </div>
  )
}

export function OperationsDashboard() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [metrics, setMetrics] = useState<SystemOperationalMetricsResponse | null>(null)
  const [pipeline, setPipeline] = useState<PipelineWatermarkResponse | null>(null)
  const [incidents, setIncidents] = useState<IncidentTimelineResponse | null>(null)
  const [verification, setVerification] = useState<VerificationRunResponse | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const [hRes, mRes, pRes, iRes] = await Promise.all([
        fetchOperationalHealth(),
        fetchOperationalMetrics(),
        fetchPipelineStatus(),
        fetchOperationalIncidents(24),
      ])

      if (hRes.ok) setHealth(hRes.data)
      if (mRes.ok) setMetrics(mRes.data)
      if (pRes.ok) setPipeline(pRes.data)
      if (iRes.ok) setIncidents(iRes.data)
    } catch (err) {
      console.error('Error fetching operational data', err)
    } finally {
      setLoading(false)
    }
  }

  const handleRunVerification = async () => {
    setVerifying(true)
    try {
      const res = await runSystemVerification()
      if (res.ok) {
        setVerification(res.data)
      }
    } catch (err) {
      console.error('Verification error', err)
    } finally {
      setVerifying(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  const getHealthBadge = (state: HealthState) => {
    switch (state) {
      case 'HEALTHY':
        return (
          <span className="badge-glass-success">
            <CheckCircle2 className="w-3 h-3" /> HEALTHY
          </span>
        )
      case 'DEGRADED':
        return (
          <span className="badge-glass-warning">
            <AlertTriangle className="w-3 h-3" /> DEGRADED
          </span>
        )
      case 'UNHEALTHY':
        return (
          <span className="badge-glass-danger">
            <AlertOctagon className="w-3 h-3" /> UNHEALTHY
          </span>
        )
      default:
        return (
          <span className="badge-glass text-slate-400">
            UNKNOWN
          </span>
        )
    }
  }

  if (loading && !health) {
    return (
      <div className="glass-card p-8 flex items-center justify-center gap-4 animate-fade-in">
        <div className="neo-pressed p-3 rounded-xl">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
        </div>
        <span className="text-slate-400 text-sm font-medium">Loading Live Operational Intelligence...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header Banner — Glassmorphism */}
      <div className="glass-card-elevated p-6 sm:p-8 animate-slide-up">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl">
                <Activity className="w-5 h-5 text-indigo-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">System Operational Intelligence</h2>
            </div>
            {health && (
              <div className="flex items-center gap-3 ml-12">
                {getHealthBadge(health.overall_state)}
              </div>
            )}
            <p className="text-slate-400 text-sm mt-3 ml-12">{health?.summary || 'Authoritative pipeline health'}</p>
          </div>

          <div className="flex items-center gap-3 ml-12 sm:ml-0">
            <button
              onClick={loadData}
              className="neo-btn flex items-center gap-2 text-slate-300"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span className="text-xs">Refresh</span>
            </button>
            <button
              onClick={handleRunVerification}
              disabled={verifying}
              className="neo-btn-indigo flex items-center gap-2 disabled:opacity-50"
            >
              <PlayCircle className="w-3.5 h-3.5" />
              <span className="text-xs">{verifying ? 'Verifying...' : 'Run Verification'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Real-Time Metrics Grid — Neomorphism */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4 items-stretch">
        <MetricCard
          label="Webhooks"
          value={metrics?.ingestion.total_received ?? 0}
          subtext={`${metrics?.ingestion.total_verified ?? 0} Verified`}
          accent="emerald"
        />
        <MetricCard
          label="Queue Depth"
          value={metrics?.queue.queue_depth ?? 0}
          subtext={
            metrics?.queue.oldest_event_age_seconds != null
              ? `Oldest: ${formatDuration(metrics.queue.oldest_event_age_seconds)}`
              : 'Idle'
          }
          accent="indigo"
        />
        <MetricCard
          label="Processing Lag"
          value={
            metrics?.lag.latest_lag_seconds != null
              ? formatDuration(metrics.lag.latest_lag_seconds)
              : '0.0s'
          }
          subtext={`Avg: ${metrics?.lag.average_lag_seconds ? formatDuration(metrics.lag.average_lag_seconds) : '0.0s'}`}
          accent="slate"
        />
        <MetricCard
          label="Stuck Events"
          value={metrics?.stuck_events_count ?? 0}
          subtext="> 60s in queue"
          accent={metrics?.stuck_events_count ? 'amber' : 'slate'}
        />
        <MetricCard
          label="Failures"
          value={metrics?.failed_events_count ?? 0}
          subtext="Observable errors"
          accent={metrics?.failed_events_count ? 'rose' : 'slate'}
        />
        <MetricCard
          label="Canonical Facts"
          value={metrics?.active_facts_count ?? 0}
          subtext={`${metrics?.active_payments_count ?? 0} payments`}
          accent="emerald"
        />
      </div>

      {/* Pipeline View — Glassmorphism */}
      <div className="glass-card p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-1">
              <div className="neo-pressed p-2 rounded-lg">
                <Zap className="w-4 h-4 text-indigo-400" />
              </div>
              <h3 className="text-lg font-bold text-white">Live Evidence Processing Pipeline</h3>
            </div>
            <p className="text-slate-400 text-xs mt-2 ml-10">
              Pipeline Watermark: {pipeline?.pipeline_watermark_timestamp ? new Date(pipeline.pipeline_watermark_timestamp).toLocaleTimeString() : 'None'}
              <span className="mx-2">•</span>
              {pipeline?.summary}
            </p>
          </div>
          <span className={`badge-glass ${pipeline?.is_pipeline_caught_up ? 'badge-glass-success' : 'badge-glass-warning'}`}>
            {pipeline?.is_pipeline_caught_up ? 'Pipeline Caught Up' : 'Processing In Progress'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {pipeline?.stages.map((stg, idx) => (
            <div key={stg.stage_name} className="neo-card p-4 relative overflow-hidden group">
              {/* Stage Number Accent */}
              <div className="absolute -top-2 -right-2 text-[80px] font-black text-white/[0.02] leading-none pointer-events-none select-none">
                {idx + 1}
              </div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded-md border border-indigo-500/20">
                  Stage {idx + 1}
                </span>
                {getHealthBadge(stg.state)}
              </div>
              <p className="text-sm font-bold text-white mb-2">{stg.stage_name}</p>
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Clock className="w-3 h-3" />
                {stg.last_processed_at ? new Date(stg.last_processed_at).toLocaleTimeString() : stg.freshness === 'UNKNOWN' ? 'No data processed' : 'Awaiting first event'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Verification Results — Glassmorphism */}
      {verification && (
        <div className="glass-card p-6 sm:p-8 animate-scale-in">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
            <div className="flex items-center gap-3">
              <div className="neo-pressed p-2.5 rounded-xl bg-emerald-500/10">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
              </div>
              <h3 className="text-lg font-bold text-white">System Invariant Verification</h3>
            </div>
            <div className="flex items-center gap-3 text-xs font-bold">
              <span className="badge-glass-success">{verification.passed_count} PASS</span>
              <span className="badge-glass-warning">{verification.warn_count} WARN</span>
              <span className="badge-glass-danger">{verification.failed_count} FAIL</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {verification.checks.map((chk) => (
              <div key={chk.check_id} className="neo-card p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-xs text-indigo-300 font-bold bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                    {chk.check_id}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                      chk.status === 'PASS'
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                        : chk.status === 'WARN'
                        ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                        : 'bg-rose-500/15 text-rose-300 border border-rose-500/20'
                    }`}
                  >
                    {chk.status}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-200 mb-1">{chk.invariant_name}</p>
                <p className="text-xs text-slate-400">{chk.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Incidents — Glassmorphism */}
      <div className="glass-card p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-3">
            <div className="neo-pressed p-2.5 rounded-xl bg-amber-500/10">
              <AlertOctagon className="w-5 h-5 text-amber-400" />
            </div>
            <h3 className="text-lg font-bold text-white">Operational Incidents (24h)</h3>
          </div>
          <span className="badge-glass text-xs text-slate-400">
            {incidents?.active_incidents_count ? `${incidents.active_incidents_count} active` : 'No active incidents'}
          </span>
        </div>

        {!incidents?.incidents || incidents.incidents.length === 0 ? (
          <div className="neo-inset rounded-xl p-8 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="neo-pressed p-4 rounded-2xl bg-emerald-500/10">
                <CheckCircle2 className="w-8 h-8 text-emerald-400" />
              </div>
              <p className="text-slate-400 text-sm">All systems operating normally</p>
              <p className="text-slate-500 text-xs">No live operational incidents detected</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {incidents.incidents.map((inc) => (
              <div key={inc.incident_id} className="neo-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="font-mono text-xs text-slate-400">{inc.incident_id}</span>
                    <span className="badge-glass-danger text-[10px]">{inc.severity}</span>
                    <span className="badge-glass-info text-[10px]">{inc.category}</span>
                  </div>
                  <p className="text-sm font-medium text-slate-200">{inc.description}</p>
                </div>
                <div className="text-xs text-slate-500 font-mono self-end sm:self-center shrink-0">
                  {new Date(inc.detected_at).toLocaleTimeString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
