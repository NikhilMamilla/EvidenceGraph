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
  gmv: number
  success_count: number
  failure_count: number
  success_rate: number
}

interface RevenueData {
  evaluated_at: string
  metrics: RevenueMetric[]
  time_series: RevenueTimeSeries[]
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
      <div className="glass-card-elevated p-6 sm:p-8">
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
      {data && data.time_series.length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="neo-pressed p-2 rounded-lg bg-indigo-500/10">
              <BarChart3 className="w-4 h-4 text-indigo-400" />
            </div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Revenue Trend (24h)</h3>
          </div>

          {/* GMV Bar Chart */}
          <div className="mb-6">
            <div className="text-[10px] text-slate-500 mb-2">GMV by Hour (₹)</div>
            <div className="flex items-end gap-1 h-40">
              {data.time_series.map((point, i) => {
                const maxGmv = Math.max(...data.time_series.map(p => p.gmv), 1)
                const height = (point.gmv / maxGmv) * 100
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                    <div className="absolute -top-8 hidden group-hover:block bg-slate-800 text-[10px] text-white px-2 py-1 rounded z-10 whitespace-nowrap">
                      ₹{point.gmv.toFixed(2)}
                    </div>
                    <div
                      className="w-full bg-emerald-500/40 rounded-t hover:bg-emerald-500/60 transition-colors"
                      style={{ height: `${Math.max(2, height)}%` }}
                    />
                    {i % 6 === 0 && (
                      <span className="text-[8px] text-slate-600">
                        {new Date(point.timestamp).getHours()}h
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Success Rate Line */}
          <div>
            <div className="text-[10px] text-slate-500 mb-2">Success Rate by Hour (%)</div>
            <div className="flex items-end gap-1 h-24">
              {data.time_series.map((point, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t transition-all duration-500"
                    style={{
                      height: `${Math.max(2, point.success_rate)}%`,
                      backgroundColor: point.success_rate > 90 ? 'rgba(52,211,153,0.4)' :
                        point.success_rate > 70 ? 'rgba(251,191,36,0.4)' : 'rgba(251,113,133,0.4)',
                    }}
                  />
                  {i % 6 === 0 && (
                    <span className="text-[8px] text-slate-600">
                      {point.success_rate.toFixed(0)}%
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading revenue data...</span>
        </div>
      )}
    </div>
  )
}
