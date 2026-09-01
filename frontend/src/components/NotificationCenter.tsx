/**
 * NotificationCenter Component — Real-Time Alert & Notification System
 *
 * Displays system notifications, fraud alerts, failure alerts,
 * and milestone notifications with severity-based color coding.
 */

import { useEffect, useState } from 'react'
import {
  Bell,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  Info,
  Shield,
  Zap,
  Trophy,
  X,
} from 'lucide-react'

interface NotificationItem {
  notification_id: string
  category: string
  severity: string
  title: string
  description: string
  payment_id: string | null
  created_at: string
  read: boolean
  metadata: Record<string, any>
}

interface NotificationCenterData {
  notifications: NotificationItem[]
  total_count: number
  unread_count: number
  critical_count: number
  evaluated_at: string
}

const SEVERITY_CONFIG: Record<string, { bg: string; text: string; border: string; icon: React.ElementType }> = {
  CRITICAL: { bg: 'bg-rose-500/10', text: 'text-rose-300', border: 'border-l-rose-500', icon: AlertOctagon },
  WARNING: { bg: 'bg-amber-500/10', text: 'text-amber-300', border: 'border-l-amber-500', icon: AlertTriangle },
  INFO: { bg: 'bg-indigo-500/10', text: 'text-indigo-300', border: 'border-l-indigo-500', icon: Info },
}

const CATEGORY_CONFIG: Record<string, { icon: React.ElementType; color: string }> = {
  FRAUD: { icon: Shield, color: 'text-rose-400' },
  FAILURE: { icon: X, color: 'text-amber-400' },
  SYSTEM: { icon: Zap, color: 'text-indigo-400' },
  ANOMALY: { icon: AlertTriangle, color: 'text-orange-400' },
  MILESTONE: { icon: Trophy, color: 'text-emerald-400' },
}

export function NotificationCenter() {
  const [data, setData] = useState<NotificationCenterData | null>(null)
  const [filter, setFilter] = useState<string>('ALL')

  const loadData = async () => {
    try {
      const res = await fetch('/api/v1/analytics/notifications')
      if (res.ok) setData(await res.json())
    } catch (err) {
      console.error('Failed to load notifications', err)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 10000) // Poll every 10s
    return () => clearInterval(interval)
  }, [])

  const filtered = data?.notifications.filter(n =>
    filter === 'ALL' || n.severity === filter || n.category === filter
  ) || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated premium-ring p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-amber-500/10 relative">
                <Bell className="w-5 h-5 text-amber-400" />
                {data && data.critical_count > 0 && (
                  <div className="absolute -top-1 -right-1 w-4 h-4 bg-rose-500 rounded-full flex items-center justify-center">
                    <span className="text-[8px] text-white font-bold">{data.critical_count}</span>
                  </div>
                )}
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Notification Center</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Real-time alerts for failures, fraud signals, anomalies, and system milestones
            </p>
          </div>

          {data && (
            <div className="flex items-center gap-4 ml-12 sm:ml-0">
              <div className="text-center">
                <div className="text-2xl font-extrabold text-amber-400">{data.unread_count}</div>
                <div className="text-[10px] text-slate-500">Unread</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-extrabold text-rose-400">{data.critical_count}</div>
                <div className="text-[10px] text-slate-500">Critical</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 flex-wrap">
        {['ALL', 'CRITICAL', 'WARNING', 'INFO'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              filter === f ? 'tab-glass-active' : 'tab-glass text-slate-400 hover:text-slate-200'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Notifications List */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="glass-card p-12 text-center">
            <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No notifications</p>
            <p className="text-slate-500 text-xs mt-1">System operating normally</p>
          </div>
        ) : (
          filtered.map(n => {
            const sevConfig = SEVERITY_CONFIG[n.severity] || SEVERITY_CONFIG.INFO
            const catConfig = CATEGORY_CONFIG[n.category] || CATEGORY_CONFIG.SYSTEM
            const CatIcon = catConfig.icon

            return (
              <div
                key={n.notification_id}
                className={`glass-card p-4 border-l-4 ${sevConfig.border} ${sevConfig.bg} transition-all hover:scale-[1.005]`}
              >
                <div className="flex items-start gap-3">
                  <div className="neo-pressed p-2 rounded-lg shrink-0">
                    <CatIcon className={`w-4 h-4 ${catConfig.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-sm font-bold text-slate-200">{n.title}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          n.severity === 'CRITICAL' ? 'bg-rose-500/20 text-rose-300' :
                          n.severity === 'WARNING' ? 'bg-amber-500/20 text-amber-300' :
                          'bg-indigo-500/20 text-indigo-300'
                        }`}>
                          {n.severity}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {new Date(n.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                    <p className="text-xs text-slate-400">{n.description}</p>
                    {n.payment_id && (
                      <span className="inline-block mt-2 text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                        {n.payment_id}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
