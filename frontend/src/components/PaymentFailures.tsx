/**
 * PaymentFailures Component — Payment Failure Intelligence & Funnel Analytics
 *
 * Shows failure root cause analysis, payment funnel visualization,
 * and failure trend charts.
 */

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  TrendingDown,
  RefreshCw,
  Target,
  CheckCircle2,
} from 'lucide-react'

interface FailureCategory {
  category: string
  display_name: string
  count: number
  percentage: number
  severity: string
  explanation: string
  recommendation: string
}

interface FailureDashboard {
  evaluated_at: string
  total_payments: number
  total_captured: number
  total_failed: number
  total_pending: number
  success_rate: number
  failure_rate: number
  failure_categories: FailureCategory[]
  recent_failures: any[]
  hourly_failure_trend: Array<{ hour: string; failure_count: number }>
}

interface FunnelStage {
  stage_name: string
  stage_order: number
  count: number
  percentage: number
  drop_off_count: number
  drop_off_percentage: number
}

interface PaymentFunnel {
  evaluated_at: string
  total_initiated: number
  stages: FunnelStage[]
  overall_conversion_rate: number
  biggest_drop_off_stage: string
}

function FunnelVisualization({ funnel }: { funnel: PaymentFunnel }) {
  if (!funnel || funnel.stages.length === 0) return null

  const maxCount = Math.max(...funnel.stages.map(s => s.count), 1)

  return (
    <div className="glass-card-elevated premium-ring p-6 sm:p-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="neo-pressed p-2 rounded-lg bg-indigo-500/10">
            <Target className="w-4 h-4 text-indigo-400" />
          </div>
          <h3 className="text-lg font-bold text-white">Payment Funnel</h3>
        </div>
        <div className="text-right">
          <div className="text-2xl font-extrabold text-emerald-400">
            {funnel.overall_conversion_rate}%
          </div>
          <div className="text-[10px] text-slate-500">Conversion Rate</div>
        </div>
      </div>

      <div className="space-y-3">
        {funnel.stages.map((stage) => {
          const width = maxCount > 0 ? (stage.count / maxCount) * 100 : 0
          const isFailed = stage.stage_name === 'Failed'
          return (
            <div key={stage.stage_name}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-300">
                    Stage {stage.stage_order}: {stage.stage_name}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {stage.count} ({stage.percentage}%)
                  </span>
                </div>
                {stage.drop_off_count > 0 && (
                  <span className="text-[10px] text-rose-400">
                    ↓ {stage.drop_off_count} dropped ({stage.drop_off_percentage}%)
                  </span>
                )}
              </div>
              <div className="h-8 bg-slate-800/50 rounded-lg overflow-hidden relative">
                <div
                  className={`h-full rounded-lg transition-all duration-1000 ease-out ${
                    isFailed
                      ? 'bg-gradient-to-r from-rose-500/60 to-rose-500/30'
                      : 'bg-gradient-to-r from-indigo-500/60 to-indigo-500/30'
                  }`}
                  style={{ width: `${Math.max(2, width)}%` }}
                />
                <span className="absolute inset-0 flex items-center px-3 text-xs font-bold text-white/80">
                  {stage.count}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-white/5 text-xs text-slate-500">
        Biggest drop-off: <span className="text-amber-400 font-bold">{funnel.biggest_drop_off_stage}</span>
      </div>
    </div>
  )
}

export function PaymentFailures() {
  const [dashboard, setDashboard] = useState<FailureDashboard | null>(null)
  const [funnel, setFunnel] = useState<PaymentFunnel | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/analytics/failures').then(r => r.ok ? r.json() : null),
      fetch('/api/v1/analytics/funnel').then(r => r.ok ? r.json() : null),
    ]).then(([failData, funnelData]) => {
      if (failData) setDashboard(failData)
      if (funnelData) setFunnel(funnelData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="neo-pressed p-2.5 rounded-xl bg-rose-500/10">
            <AlertTriangle className="w-5 h-5 text-rose-400" />
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Payment Failure Intelligence</h2>
        </div>
        <p className="text-slate-400 text-sm ml-12">
          Root cause analysis, failure categorization, and payment funnel visualization
        </p>
      </div>

      {/* Stats */}
      {dashboard && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Total Payments</div>
            <div className="text-2xl font-extrabold text-indigo-400">{dashboard.total_payments}</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Captured</div>
            <div className="text-2xl font-extrabold text-emerald-400">{dashboard.total_captured}</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Failed</div>
            <div className="text-2xl font-extrabold text-rose-400">{dashboard.total_failed}</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Success Rate</div>
            <div className="text-2xl font-extrabold text-emerald-400">{dashboard.success_rate}%</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Failure Rate</div>
            <div className="text-2xl font-extrabold text-rose-400">{dashboard.failure_rate}%</div>
          </div>
        </div>
      )}

      {/* Funnel + Failure Categories side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {funnel && <FunnelVisualization funnel={funnel} />}

        {/* Failure Categories */}
        {dashboard && (
          <div className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="neo-pressed p-2 rounded-lg bg-amber-500/10">
                <TrendingDown className="w-4 h-4 text-amber-400" />
              </div>
              <h3 className="text-lg font-bold text-white">Failure Categories</h3>
            </div>

            {dashboard.failure_categories.length === 0 ? (
              <div className="neo-inset rounded-xl p-8 text-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                <p className="text-slate-400 text-sm">No failures recorded</p>
              </div>
            ) : (
              <div className="space-y-3">
                {dashboard.failure_categories.map(cat => (
                  <div key={cat.category} className="neo-card p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-200">{cat.display_name}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          cat.severity === 'HIGH' ? 'bg-rose-500/15 text-rose-300' :
                          cat.severity === 'MEDIUM' ? 'bg-amber-500/15 text-amber-300' :
                          'bg-slate-500/15 text-slate-300'
                        }`}>
                          {cat.severity}
                        </span>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-extrabold text-slate-200">{cat.count}</div>
                        <div className="text-[10px] text-slate-500">{cat.percentage}%</div>
                      </div>
                    </div>
                    <p className="text-xs text-slate-400 mb-1">{cat.explanation}</p>
                    <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mt-2">
                      <div
                        className="h-full bg-rose-500/50 rounded-full"
                        style={{ width: `${cat.percentage}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Failure Trend */}
      {dashboard && dashboard.hourly_failure_trend.length > 0 && (
        <div className="glass-card p-6">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">Failure Trend (24h)</h3>
          <div className="flex items-end gap-1 h-32">
            {dashboard.hourly_failure_trend.map((point, i) => {
              const maxVal = Math.max(...dashboard.hourly_failure_trend.map(p => p.failure_count), 1)
              const height = (point.failure_count / maxVal) * 100
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full bg-rose-500/40 rounded-t transition-all duration-500"
                    style={{ height: `${Math.max(2, height)}%` }}
                  />
                  {i % 6 === 0 && (
                    <span className="text-[8px] text-slate-600">
                      {new Date(point.hour).getHours()}h
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading failure analytics...</span>
        </div>
      )}
    </div>
  )
}
