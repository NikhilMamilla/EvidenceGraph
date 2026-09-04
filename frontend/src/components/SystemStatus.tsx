/**
 * SystemStatus component — Glassmorphism + Neomorphism Design
 *
 * Shows live status for:
 *   Backend API, PostgreSQL, Redis, Razorpay, Webhook Ingestion
 *
 * All values come from the backend API — nothing is hardcoded.
 */

import { useEffect, useState } from 'react'
import { fetchLiveness, fetchRazorpayStatus, fetchReadiness } from '../lib/api'
import type { RazorpayStatus, ReadinessResponse } from '../lib/api'
import { Server, Database, Zap, CreditCard, Webhook, RefreshCw } from 'lucide-react'
import { markGuideStepDone } from '../lib/evaluatorProgress'

const POLL_INTERVAL_MS = 15_000

type Phase =
  | { phase: 'loading' }
  | { phase: 'backend_down'; error: string }
  | {
      phase: 'ready'
      readiness: ReadinessResponse
      razorpay: RazorpayStatus | null
    }

/* ── Animated Pulse Dot ──────────────────────────────────────────── */
function StatusDot({ state }: { state: 'good' | 'warn' | 'bad' }) {
  const color =
    state === 'good'
      ? 'bg-emerald-400'
      : state === 'warn'
      ? 'bg-amber-400'
      : 'bg-rose-400'
  const glow =
    state === 'good'
      ? 'shadow-[0_0_8px_rgba(52,211,153,0.6)]'
      : state === 'warn'
      ? 'shadow-[0_0_8px_rgba(251,191,36,0.6)]'
      : 'shadow-[0_0_8px_rgba(251,113,133,0.6)]'

  return (
    <span className="relative flex items-center justify-center">
      <span className={`h-2.5 w-2.5 rounded-full ${color} ${glow}`} />
      <span className={`absolute h-2.5 w-2.5 rounded-full ${color} animate-ping opacity-40`} />
    </span>
  )
}

/* ── Status Badge ────────────────────────────────────────────────── */
function StatusBadge({ value, label }: { value: string; label?: string }) {
  const isGood = ['connected', 'configured', 'receiving', 'active'].includes(value)
  const isWarn = ['waiting', 'not_configured', 'idle'].includes(value)
  const displayLabel = label ?? value.charAt(0).toUpperCase() + value.slice(1).replace('_', ' ')

  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-300 ${
        isGood
          ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 shadow-[0_0_12px_rgba(52,211,153,0.08)]'
          : isWarn
          ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20 shadow-[0_0_12px_rgba(251,191,36,0.08)]'
          : 'bg-rose-500/10 text-rose-300 border border-rose-500/20 shadow-[0_0_12px_rgba(251,113,133,0.08)]'
      }`}
    >
      <StatusDot state={isGood ? 'good' : isWarn ? 'warn' : 'bad'} />
      {displayLabel}
    </span>
  )
}

/* ── Loading Row ─────────────────────────────────────────────────── */
function LoadingRow({ label, icon: Icon }: { label: string; icon: React.ElementType }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3.5 border-b border-white/5 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="neo-pressed p-2 rounded-lg">
          <Icon className="w-3.5 h-3.5 text-slate-500" />
        </div>
        <span className="text-slate-400 font-medium text-sm">{label}</span>
      </div>
      <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs bg-white/5 text-slate-500 animate-pulse shrink-0 border border-white/5">
        <RefreshCw className="w-3 h-3 animate-spin" />
        Checking
      </span>
    </div>
  )
}

/* ── Status Row ──────────────────────────────────────────────────── */
function StatusRow({ label, icon: Icon, children }: { label: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3.5 border-b border-white/5 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="neo-pressed p-2 rounded-lg">
          <Icon className="w-3.5 h-3.5 text-slate-400" />
        </div>
        <span className="text-slate-300 font-medium text-sm">{label}</span>
      </div>
      {children}
    </div>
  )
}

const statusIcons = {
  'Backend API': Server,
  'PostgreSQL': Database,
  'Redis': Zap,
  'Razorpay': CreditCard,
  'Webhook Ingestion': Webhook,
} as const

/* ── Main Component ──────────────────────────────────────────────── */
export function SystemStatus() {
  const [state, setState] = useState<Phase>({ phase: 'loading' })

  async function checkStatus() {
    const liveness = await fetchLiveness()
    if (!liveness.ok) {
      setState({ phase: 'backend_down', error: liveness.error })
      return
    }

    const [readiness, razorpayResult] = await Promise.all([
      fetchReadiness(),
      fetchRazorpayStatus(),
    ])

    const readinessData: ReadinessResponse =
      readiness.ok
        ? readiness.data
        : { status: 'not_ready', database: 'unavailable', redis: 'unavailable' }

    const razorpayData: RazorpayStatus | null = razorpayResult.ok
      ? razorpayResult.data
      : null

    setState({ phase: 'ready', readiness: readinessData, razorpay: razorpayData })
    // Real signal for the evaluator checklist: health data actually loaded and
    // rendered, not just "the tab was opened."
    markGuideStepDone('health')
  }

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  const labels = ['Backend API', 'PostgreSQL', 'Redis', 'Razorpay', 'Webhook Ingestion'] as const

  /* ── Loading State ──────────────────────────────────────────────── */
  if (state.phase === 'loading') {
    return (
      <div className="glass-card p-6 sm:p-8 w-full">
        <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-3">
          <div className="neo-pressed p-2.5 rounded-xl">
            <Server className="w-5 h-5 text-indigo-400" />
          </div>
          System Status
        </h2>
        {labels.map((l) => (
          <LoadingRow key={l} label={l} icon={statusIcons[l]} />
        ))}
      </div>
    )
  }

  /* ── Backend Down State ─────────────────────────────────────────── */
  if (state.phase === 'backend_down') {
    return (
      <div className="glass-card p-6 sm:p-8 w-full border-rose-500/20">
        <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-3">
          <div className="neo-pressed p-2.5 rounded-xl bg-rose-500/10">
            <Server className="w-5 h-5 text-rose-400" />
          </div>
          System Status
        </h2>
        <div className="neo-inset rounded-xl p-4 mb-6 border border-rose-500/20">
          <p className="font-bold text-sm text-rose-300 mb-1">Backend Unreachable</p>
          <p className="text-rose-400/70 font-mono text-xs break-all">{state.error}</p>
        </div>
        {labels.map((l) => (
          <StatusRow key={l} label={l} icon={statusIcons[l]}>
            <StatusBadge value="unavailable" />
          </StatusRow>
        ))}
      </div>
    )
  }

  /* ── Ready State ────────────────────────────────────────────────── */
  const { readiness, razorpay } = state
  const backendOk = readiness.status === 'ready'
  const razorpayBadge = razorpay?.configured ? 'configured' : 'not_configured'

  // events_received is a persisted count, so it stays truthful across restarts.
  // "Active" = something arrived in the last 24h; "Idle" = ingested before, quiet now.
  const ingestedTotal = razorpay?.events_received ?? 0
  const lastEventMs = razorpay?.last_event_at ? Date.parse(razorpay.last_event_at) : NaN
  const isRecent = Number.isFinite(lastEventMs) && Date.now() - lastEventMs < 24 * 60 * 60 * 1000
  const webhookBadge = ingestedTotal === 0 ? 'waiting' : isRecent ? 'active' : 'idle'
  const webhookLabel =
    ingestedTotal === 0
      ? 'Waiting for first event'
      : `${isRecent ? 'Active' : 'Idle'} · ${ingestedTotal} event${ingestedTotal === 1 ? '' : 's'}`

  return (
    <div className="glass-card p-6 sm:p-8 w-full">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-bold text-white flex items-center gap-3">
          <div className="neo-pressed p-2.5 rounded-xl">
            <Server className="w-5 h-5 text-indigo-400" />
          </div>
          System Status
        </h2>
        <span className="badge-glass text-[10px] text-slate-500">
          Refreshes every {POLL_INTERVAL_MS / 1000}s
        </span>
      </div>

      <div className="space-y-0">
        <StatusRow label="Backend API" icon={Server}>
          <StatusBadge value={backendOk ? 'connected' : 'unavailable'} />
        </StatusRow>
        <StatusRow label="PostgreSQL" icon={Database}>
          <StatusBadge value={readiness.database} />
        </StatusRow>
        <StatusRow label="Redis" icon={Zap}>
          <StatusBadge value={readiness.redis} />
        </StatusRow>
        <StatusRow label="Razorpay" icon={CreditCard}>
          <StatusBadge
            value={razorpayBadge}
            label={razorpay?.configured ? `Configured (${razorpay.mode})` : 'Not Configured'}
          />
        </StatusRow>
        <StatusRow label="Webhook Ingestion" icon={Webhook}>
          <StatusBadge value={webhookBadge} label={webhookLabel} />
        </StatusRow>
      </div>
    </div>
  )
}
