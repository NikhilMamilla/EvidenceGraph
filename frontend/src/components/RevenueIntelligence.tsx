/**
 * RevenueIntelligence Component — Revenue Analytics Dashboard
 *
 * Displays GMV, average transaction value, success rates,
 * time-series trends, and revenue metrics.
 */

import { useEffect, useState } from 'react'
import {
  DollarSign,
  RefreshCw,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react'

interface RevenueMetric {
  label: string
  value: number
  unit: string
  change_pct: number | null
  trend: string
}

interface RevenueTimeSeries {
  timestamp: string
  label: string
  gmv: number
  success_count: number
  failure_count: number
  success_rate: number
}

interface RevenueData {
  evaluated_at: string
  metrics: RevenueMetric[]
  time_series: RevenueTimeSeries[]
  series_window: string
  total_gmv: number
  avg_transaction_value: number
  success_rate: number
  peak_hour: string | null
  methodology_version: string
}

function MetricCard({ metric }: { metric: RevenueMetric }) {
  const formatValue = (val: number, unit: string) => {
    if (unit === 'INR') return `₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    if (unit === 'PERCENT') return `${val.toFixed(1)}%`
    return val.toLocaleString()
  }

  const trendIcon = metric.trend === 'UP' ? ArrowUpRight :
    metric.trend === 'DOWN' ? ArrowDownRight : Minus

  const TrendIcon = trendIcon

  return (
    <div className="metric-card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">{metric.label}</span>
        <TrendIcon className={`w-4 h-4 ${
          metric.trend === 'UP' ? 'text-emerald-400' :
          metric.trend === 'DOWN' ? 'text-rose-400' : 'text-slate-500'
        }`} />
      </div>
      <div className={`text-2xl font-extrabold ${
        metric.trend === 'UP' ? 'text-emerald-400' :
        metric.trend === 'DOWN' ? 'text-rose-400' : 'text-indigo-400'
      }`}>
        {formatValue(metric.value, metric.unit)}
      </div>
    </div>
  )
}

export function RevenueIntelligence() {
  const [data, setData] = useState<RevenueData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/analytics/revenue')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated premium-ring p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="neo-pressed p-2.5 rounded-xl bg-emerald-500/10">
            <DollarSign className="w-5 h-5 text-emerald-400" />
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Revenue Intelligence</h2>
        </div>
        <p className="text-slate-400 text-sm ml-12">
          GMV analytics, transaction trends, and success rate monitoring
        </p>
      </div>

      {/* Metrics Grid */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {data.metrics.map(m => (
            <MetricCard key={m.label} metric={m} />
          ))}
        </div>
      )}

      {/* Revenue Time Series Chart */}
      {data && data.time_series.length > 0 && (() => {
        const series = data.time_series
        const window = data.series_window || 'Last 24 hours'
        const maxGmv = Math.max(...series.map(p => p.gmv))
        const hasActivity = series.some(p => p.gmv > 0 || p.success_count > 0 || p.failure_count > 0)
        // Only label a tick every Nth bucket so the axis never collides with itself.
        const step = Math.max(1, Math.ceil(series.length / 8))
        const tick = (p: RevenueTimeSeries) =>
          p.label || `${new Date(p.timestamp).getHours()}h`

        return (
          <div className="glass-card p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
              <div className="flex items-center gap-3">
                <div className="neo-pressed p-2 rounded-lg" style={{ background: 'var(--color-accent-glow)' }}>
                  <BarChart3 className="w-4 h-4" style={{ color: 'var(--color-text-accent)' }} />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-primary)' }}>
                  Revenue Trend
                </h3>
              </div>
              <span className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                    style={{ color: 'var(--color-text-tertiary)', border: '1px solid var(--color-border)' }}>
                {window}
              </span>
            </div>

            {!hasActivity ? (
              <div className="neo-inset rounded-xl px-6 py-10 text-center">
                <p className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                  No payment activity in this window
                </p>
                <p className="mt-1.5 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                  Ingest a Razorpay Test Mode webhook and the trend will populate.
                </p>
              </div>
            ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                {/* GMV */}
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
                    GMV (₹)
                  </div>
                  <div className="flex h-40 items-end gap-1">
                    {series.map((point, i) => {
                      const height = maxGmv > 0 ? (point.gmv / maxGmv) * 100 : 0
                      return (
                        <div key={i} className="group relative flex flex-1 flex-col items-center gap-1">
                          <div className="absolute -top-8 z-10 hidden whitespace-nowrap rounded px-2 py-1 text-[10px] group-hover:block"
                               style={{ background: 'var(--color-bg-elevated)', color: 'var(--color-text-primary)' }}>
                            {tick(point)} · ₹{point.gmv.toFixed(2)}
                          </div>
                          <div className="w-full flex-1 flex items-end">
                            <div
                              className="w-full rounded-t transition-colors"
                              style={{
                                height: `${point.gmv > 0 ? Math.max(4, height) : 2}%`,
                                background: point.gmv > 0
                                  ? 'color-mix(in srgb, var(--color-success) 55%, transparent)'
                                  : 'var(--color-border)',
                              }}
                            />
                          </div>
                          <span className="h-3 text-[8px]" style={{ color: 'var(--color-text-tertiary)' }}>
                            {i % step === 0 ? tick(point) : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Success rate */}
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
                    Success rate (%)
                  </div>
                  <div className="flex h-40 items-end gap-1">
                    {series.map((point, i) => {
                      const active = point.success_count + point.failure_count > 0
                      return (
                        <div key={i} className="group relative flex flex-1 flex-col items-center gap-1">
                          <div className="absolute -top-8 z-10 hidden whitespace-nowrap rounded px-2 py-1 text-[10px] group-hover:block"
                               style={{ background: 'var(--color-bg-elevated)', color: 'var(--color-text-primary)' }}>
                            {tick(point)} · {active ? `${point.success_rate.toFixed(0)}%` : 'no activity'}
                          </div>
                          <div className="w-full flex-1 flex items-end">
                            <div
                              className="w-full rounded-t transition-all duration-500"
                              style={{
                                height: active ? `${Math.max(4, point.success_rate)}%` : '2%',
                                background: !active
                                  ? 'var(--color-border)'
                                  : point.success_rate > 90
                                  ? 'color-mix(in srgb, var(--color-success) 55%, transparent)'
                                  : point.success_rate > 70
                                  ? 'color-mix(in srgb, var(--color-warning) 55%, transparent)'
                                  : 'color-mix(in srgb, var(--color-danger) 55%, transparent)',
                              }}
                            />
                          </div>
                          <span className="h-3 text-[8px]" style={{ color: 'var(--color-text-tertiary)' }}>
                            {i % step === 0 ? tick(point) : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading revenue data...</span>
        </div>
      )}
    </div>
  )
}
