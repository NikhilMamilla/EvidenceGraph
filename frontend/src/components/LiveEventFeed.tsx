/**
 * LiveEventFeed Component — Real-Time Payment Event Streaming
 *
 * Connects to the backend SSE endpoint and displays real-time
 * payment events, evidence observations, facts, and conflicts
 * as they flow through the pipeline.
 *
 * Uses Server-Sent Events for efficient real-time updates.
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Activity,
  Zap,
  AlertTriangle,
  Eye,
  GitBranch,
  Radio,
  Pause,
  Play,
  Trash2,
  Signal,
} from 'lucide-react'

interface StreamEvent {
  id: string
  type: string
  data: Record<string, any>
  receivedAt: Date
}

const EVENT_COLORS: Record<string, { bg: string; border: string; icon: React.ElementType; label: string }> = {
  webhook_event: { bg: 'bg-blue-500/10', border: 'border-blue-500/20', icon: Zap, label: 'Webhook Event' },
  evidence_observed: { bg: 'bg-indigo-500/10', border: 'border-indigo-500/20', icon: Eye, label: 'Evidence Observed' },
  fact_reconciled: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', icon: GitBranch, label: 'Fact Reconciled' },
  conflict_detected: { bg: 'bg-rose-500/10', border: 'border-rose-500/20', icon: AlertTriangle, label: 'Conflict Detected' },
  heartbeat: { bg: 'bg-slate-500/10', border: 'border-slate-500/20', icon: Signal, label: 'Heartbeat' },
  error: { bg: 'bg-red-500/10', border: 'border-red-500/20', icon: AlertTriangle, label: 'Error' },
}

function EventCard({ event }: { event: StreamEvent }) {
  const config = EVENT_COLORS[event.type] || EVENT_COLORS.heartbeat
  const Icon = config.icon

  return (
    <div
      className={`${config.bg} border ${config.border} rounded-xl p-3 animate-slide-up transition-all duration-300 hover:scale-[1.01]`}
      style={{ animationDuration: '0.3s' }}
    >
      <div className="flex items-start gap-3">
        <div className="neo-pressed p-2 rounded-lg shrink-0 mt-0.5">
          <Icon className="w-3.5 h-3.5 text-slate-300" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              {config.label}
            </span>
            <span className="text-[10px] text-slate-500 font-mono shrink-0">
              {event.receivedAt.toLocaleTimeString()}
            </span>
          </div>

          {event.type === 'webhook_event' && (
            <div className="space-y-1">
              <div className="text-sm font-medium text-slate-200">{event.data.event_type}</div>
              <div className="flex gap-2 flex-wrap">
                {event.data.payment_id && (
                  <span className="text-[10px] bg-blue-500/15 text-blue-300 px-2 py-0.5 rounded-full border border-blue-500/20 font-mono">
                    {event.data.payment_id}
                  </span>
                )}
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                  event.data.status === 'PROCESSED'
                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                    : event.data.status === 'FAILED'
                    ? 'bg-rose-500/15 text-rose-300 border border-rose-500/20'
                    : 'bg-slate-500/15 text-slate-300 border border-slate-500/20'
                }`}>
                  {event.data.status}
                </span>
              </div>
            </div>
          )}

          {event.type === 'evidence_observed' && (
            <div className="space-y-1">
              <div className="text-sm font-medium text-slate-200">{event.data.evidence_type}</div>
              <div className="flex gap-2 flex-wrap">
                <span className="text-[10px] bg-indigo-500/15 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/20 font-mono">
                  {event.data.subject_id}
                </span>
                {event.data.value && (
                  <span className="text-[10px] text-slate-400 font-mono">
                    = {event.data.value}
                  </span>
                )}
                <span className="text-[10px] text-slate-500">
                  via {event.data.source_type}
                </span>
              </div>
            </div>
          )}

          {event.type === 'fact_reconciled' && (
            <div className="space-y-1">
              <div className="text-sm font-medium text-slate-200">{event.data.fact_type}</div>
              <div className="flex gap-2 flex-wrap">
                <span className="text-[10px] bg-emerald-500/15 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-500/20 font-mono">
                  {event.data.canonical_value}
                </span>
                <span className="text-[10px] text-slate-500">
                  {event.data.observation_count} observations
                </span>
              </div>
            </div>
          )}

          {event.type === 'conflict_detected' && (
            <div className="space-y-1">
              <div className="text-sm font-medium text-slate-200">{event.data.conflict_type}</div>
              <div className="flex gap-2 flex-wrap">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                  event.data.severity === 'CRITICAL'
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    : event.data.severity === 'HIGH'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    : 'bg-slate-500/15 text-slate-300 border border-slate-500/20'
                }`}>
                  {event.data.severity}
                </span>
                <span className="text-[10px] text-slate-500">
                  {event.data.payment_id}
                </span>
              </div>
            </div>
          )}

          {event.type === 'heartbeat' && (
            <div className="text-xs text-slate-500">
              System alive • {event.data.recent_count} events in buffer
            </div>
          )}

          {event.type === 'error' && (
            <div className="text-xs text-rose-400 font-mono">
              {event.data.error}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function LiveEventFeed() {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [paused, setPaused] = useState(false)
  const [stats, setStats] = useState({ total: 0, byType: {} as Record<string, number> })
  const [lastPing, setLastPing] = useState<Date | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const eventSourceRef = useRef<EventSource | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)

  // 1s ticker so the "synced Ns ago" label stays current
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const pingAge = lastPing ? Math.max(0, Math.round((now - lastPing.getTime()) / 1000)) : null
  // stream is healthy if the SSE socket is open AND we've heard from it recently
  const live = connected && pingAge !== null && pingAge < 20

  const connectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = new EventSource('/api/v1/stream/events')
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      setLastPing(new Date())
    }

    // Heartbeats are keep-alive only — they never become feed cards, they just
    // prove the stream is still flowing when nothing else is happening.
    es.addEventListener('heartbeat', (() => {
      setConnected(true)
      setLastPing(new Date())
    }) as EventListener)

    const handleEvent = (eventType: string) => {
      es.addEventListener(eventType, ((e: MessageEvent) => {
        setLastPing(new Date())
        if (paused) return
        try {
          const data = JSON.parse(e.data)
          const streamEvent: StreamEvent = {
            id: `${eventType}-${Date.now()}-${Math.random()}`,
            type: eventType,
            data,
            receivedAt: new Date(),
          }

          setEvents(prev => {
            const next = [streamEvent, ...prev].slice(0, 200) // Keep last 200
            return next
          })

          setStats(prev => ({
            total: prev.total + 1,
            byType: {
              ...prev.byType,
              [eventType]: (prev.byType[eventType] || 0) + 1,
            },
          }))
        } catch (err) {
          console.error('Failed to parse SSE event:', err)
        }
      }) as EventListener)
    }

    handleEvent('webhook_event')
    handleEvent('evidence_observed')
    handleEvent('fact_reconciled')
    handleEvent('conflict_detected')
    handleEvent('error')

    es.onerror = () => {
      setConnected(false)
      // Reconnect after 3 seconds
      setTimeout(() => {
        if (eventSourceRef.current?.readyState === EventSource.CLOSED) {
          connectSSE()
        }
      }, 3000)
    }
  }, [paused])

  useEffect(() => {
    connectSSE()
    return () => {
      eventSourceRef.current?.close()
    }
  }, [connectSSE])

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (autoScrollRef.current && containerRef.current) {
      containerRef.current.scrollTop = 0
    }
  }, [events])

  const clearEvents = () => {
    setEvents([])
    setStats({ total: 0, byType: {} })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated premium-ring p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-indigo-500/10">
                <Radio className="w-5 h-5 text-indigo-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Live Event Stream</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Real-time payment events as they flow through the EvidenceGraph pipeline
            </p>
          </div>

          <div className="flex items-center gap-3 ml-12 sm:ml-0">
            {/* Connection Status */}
            <div className={`flex items-center gap-2 text-xs font-semibold ${
              live ? 'text-emerald-400' : connected ? 'text-amber-400' : 'text-rose-400'
            }`}>
              <div className={`w-2 h-2 rounded-full ${
                live ? 'bg-emerald-400 animate-pulse' : connected ? 'bg-amber-400' : 'bg-rose-400'
              }`} />
              {live ? 'Live' : connected ? 'Idle' : 'Reconnecting…'}
              {pingAge !== null && (
                <span className="text-slate-500 font-normal">
                  · synced {pingAge < 1 ? 'now' : `${pingAge}s ago`}
                </span>
              )}
            </div>

            <button
              onClick={() => setPaused(!paused)}
              className={`neo-btn flex items-center gap-2 text-xs ${
                paused ? 'text-amber-300' : 'text-slate-300'
              }`}
            >
              {paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
              {paused ? 'Resume' : 'Pause'}
            </button>

            <button onClick={clearEvents} className="neo-btn flex items-center gap-2 text-xs text-slate-400">
              <Trash2 className="w-3.5 h-3.5" />
              Clear
            </button>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="metric-card">
          <div className="text-xs text-slate-400 mb-1">Total Events</div>
          <div className="text-2xl font-extrabold text-indigo-400">{stats.total}</div>
        </div>
        <div className="metric-card">
          <div className="text-xs text-slate-400 mb-1">Webhooks</div>
          <div className="text-2xl font-extrabold text-blue-400">{stats.byType.webhook_event || 0}</div>
        </div>
        <div className="metric-card">
          <div className="text-xs text-slate-400 mb-1">Evidence</div>
          <div className="text-2xl font-extrabold text-indigo-400">{stats.byType.evidence_observed || 0}</div>
        </div>
        <div className="metric-card">
          <div className="text-xs text-slate-400 mb-1">Facts</div>
          <div className="text-2xl font-extrabold text-emerald-400">{stats.byType.fact_reconciled || 0}</div>
        </div>
        <div className="metric-card">
          <div className="text-xs text-slate-400 mb-1">Conflicts</div>
          <div className="text-2xl font-extrabold text-rose-400">{stats.byType.conflict_detected || 0}</div>
        </div>
      </div>

      {/* Event Feed */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Event Stream</h3>
          {paused && (
            <span className="text-[10px] bg-amber-500/15 text-amber-300 px-2 py-0.5 rounded-full border border-amber-500/20 font-bold">
              PAUSED
            </span>
          )}
        </div>

        <div
          ref={containerRef}
          className="space-y-3 max-h-[600px] overflow-y-auto pr-2"
        >
          {events.length === 0 ? (
            <div className="neo-inset rounded-xl p-12 text-center">
              <div className="flex flex-col items-center gap-3">
                <div className="neo-pressed p-4 rounded-2xl bg-indigo-500/10">
                  <Radio className="w-8 h-8 text-indigo-400 animate-pulse" />
                </div>
                <p className="text-slate-400 text-sm">
                  {connected ? 'Waiting for events...' : 'Connecting to event stream...'}
                </p>
                <p className="text-slate-500 text-xs">
                  Events will appear here in real-time as they flow through the pipeline
                </p>
              </div>
            </div>
          ) : (
            events.map((event) => (
              <EventCard key={event.id} event={event} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}
