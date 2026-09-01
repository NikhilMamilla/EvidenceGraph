/**
 * RiskScoreGauge Component — Animated Risk Score Visualization
 *
 * Displays composite evidence integrity scores with animated gauges,
 * dimensional breakdowns, and risk level indicators.
 * Uses SVG for smooth gauge animations.
 */

import { useEffect, useState } from 'react'
import {
  Shield,
  AlertTriangle,
  RefreshCw,
  Target,
} from 'lucide-react'

interface DimensionScore {
  dimension: string
  score: number
  weight: number
  status: string
  explanation: string
  evidence_count: number
}

interface RiskScoreResponse {
  payment_id: string
  evaluated_at: string
  methodology_version: string
  composite_score: number
  risk_level: string
  dimensions: DimensionScore[]
  evidence_count: number
  source_count: number
  conflict_count: number
  open_conflict_count: number
  coverage_status: string
  freshness_status: string
  explanation_lines: string[]
  recommendations: string[]
}

interface PaymentRiskSummary {
  payment_id: string
  composite_score: number
  risk_level: string
  evidence_count: number
  conflict_count: number
  evaluated_at: string | null
}

function getRiskColor(score: number): { stroke: string; fill: string; text: string } {
  if (score >= 76) return { stroke: '#34d399', fill: 'rgba(52, 211, 153, 0.15)', text: 'text-emerald-400' }
  if (score >= 51) return { stroke: '#fbbf24', fill: 'rgba(251, 191, 36, 0.15)', text: 'text-amber-400' }
  if (score >= 26) return { stroke: '#fb923c', fill: 'rgba(251, 146, 60, 0.15)', text: 'text-orange-400' }
  return { stroke: '#fb7185', fill: 'rgba(251, 113, 133, 0.15)', text: 'text-rose-400' }
}

function getRiskLabel(level: string): string {
  switch (level) {
    case 'LOW_RISK': return 'Low Risk'
    case 'MEDIUM_RISK': return 'Medium Risk'
    case 'HIGH_RISK': return 'High Risk'
    case 'CRITICAL_RISK': return 'Critical Risk'
    default: return level
  }
}

function AnimatedGauge({ score, size = 180 }: { score: number; size?: number }) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const colors = getRiskColor(score)

  useEffect(() => {
    // Animate from 0 to score
    const duration = 1500
    const start = performance.now()
    const animate = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      setAnimatedScore(score * eased)
      if (progress < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }, [score])

  const radius = (size - 20) / 2
  const circumference = Math.PI * radius // Half circle
  const progress = (animatedScore / 100) * circumference

  return (
    <div className="relative" style={{ width: size, height: size * 0.6 }}>
      <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`}>
        {/* Background arc */}
        <path
          d={`M ${10} ${size * 0.55} A ${radius} ${radius} 0 0 1 ${size - 10} ${size * 0.55}`}
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={8}
          strokeLinecap="round"
        />

        {/* Animated progress arc */}
        <path
          d={`M ${10} ${size * 0.55} A ${radius} ${radius} 0 0 1 ${size - 10} ${size * 0.55}`}
          fill="none"
          stroke={colors.stroke}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
          style={{ transition: 'stroke-dasharray 0.05s linear' }}
        />

        {/* Glow */}
        <path
          d={`M ${10} ${size * 0.55} A ${radius} ${radius} 0 0 1 ${size - 10} ${size * 0.55}`}
          fill="none"
          stroke={colors.stroke}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
          opacity={0.2}
          filter="blur(4px)"
        />
      </svg>

      {/* Score text */}
      <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
        <span className={`text-3xl font-extrabold ${colors.text}`}>
          {Math.round(animatedScore)}
        </span>
        <span className="text-[10px] text-slate-500">/ 100</span>
      </div>
    </div>
  )
}

function DimensionBar({ dimension }: { dimension: DimensionScore }) {
  const colors = getRiskColor(dimension.score)

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-300 capitalize">
          {dimension.dimension.replace(/_/g, ' ')}
        </span>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold ${colors.text}`}>{dimension.score.toFixed(0)}</span>
          <span className={`text-[9px] px-1.5 py-0.5 rounded ${
            dimension.status === 'STRONG' ? 'bg-emerald-500/15 text-emerald-300' :
            dimension.status === 'ADEQUATE' ? 'bg-amber-500/15 text-amber-300' :
            dimension.status === 'WEAK' ? 'bg-orange-500/15 text-orange-300' :
            'bg-rose-500/15 text-rose-300'
          }`}>
            {dimension.status}
          </span>
        </div>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${dimension.score}%`,
            backgroundColor: colors.stroke,
          }}
        />
      </div>
      <p className="text-[10px] text-slate-500">{dimension.explanation}</p>
    </div>
  )
}

export function RiskScoreGauge() {
  const [selectedPayment, setSelectedPayment] = useState('')
  const [riskData, setRiskData] = useState<RiskScoreResponse | null>(null)
  const [summaries, setSummaries] = useState<PaymentRiskSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/payments')
      .then(r => r.json())
      .then(() => setLoading(false))
      .catch(() => setLoading(false))

    fetch('/api/v1/risk-scores')
      .then(r => r.json())
      .then(data => setSummaries(data))
      .catch(() => {})
  }, [])

  const fetchRiskScore = async (paymentId: string) => {
    try {
      const res = await fetch(`/api/v1/payments/${paymentId}/risk-score`)
      if (res.ok) {
        setRiskData(await res.json())
      }
    } catch (err) {
      console.error('Failed to fetch risk score', err)
    }
  }

  useEffect(() => {
    if (selectedPayment) fetchRiskScore(selectedPayment)
  }, [selectedPayment])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated premium-ring p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-emerald-500/10">
                <Shield className="w-5 h-5 text-emerald-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Evidence Integrity Risk Score</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Multi-dimensional composite scoring — 0 (critical risk) to 100 (fully trustworthy)
            </p>
          </div>
        </div>
      </div>

      {/* Payment Risk Summary Grid */}
      {summaries.length > 0 && (
        <div className="glass-card p-6">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">All Payments Risk Overview</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {summaries.map(s => {
              const colors = getRiskColor(s.composite_score)
              return (
                <div
                  key={s.payment_id}
                  onClick={() => setSelectedPayment(s.payment_id)}
                  className={`neo-card p-4 cursor-pointer transition-all ${
                    selectedPayment === s.payment_id ? 'border-indigo-500/30 shadow-glow-indigo' : ''
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-xs text-slate-300 truncate">{s.payment_id}</span>
                    <span className={`text-lg font-extrabold ${colors.text}`}>{s.composite_score.toFixed(0)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                      s.risk_level === 'LOW_RISK' ? 'bg-emerald-500/15 text-emerald-300' :
                      s.risk_level === 'MEDIUM_RISK' ? 'bg-amber-500/15 text-amber-300' :
                      s.risk_level === 'HIGH_RISK' ? 'bg-orange-500/15 text-orange-300' :
                      'bg-rose-500/15 text-rose-300'
                    }`}>
                      {getRiskLabel(s.risk_level)}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {s.evidence_count} evidence • {s.conflict_count} conflicts
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Detailed Risk Score */}
      {riskData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Gauge */}
          <div className="glass-card p-6 flex flex-col items-center">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">
              Composite Score
            </h3>
            <AnimatedGauge score={riskData.composite_score} size={200} />
            <div className={`mt-4 text-lg font-bold ${getRiskColor(riskData.composite_score).text}`}>
              {getRiskLabel(riskData.risk_level)}
            </div>
            <div className="mt-2 text-xs text-slate-500 text-center">
              {riskData.evidence_count} evidence • {riskData.source_count} sources
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-2 gap-2 mt-4 w-full">
              <div className="neo-inset p-2 rounded-lg text-center">
                <div className="text-[10px] text-slate-400">Conflicts</div>
                <div className="text-sm font-bold text-slate-200">
                  {riskData.open_conflict_count}/{riskData.conflict_count}
                </div>
              </div>
              <div className="neo-inset p-2 rounded-lg text-center">
                <div className="text-[10px] text-slate-400">Coverage</div>
                <div className="text-sm font-bold text-slate-200">{riskData.coverage_status}</div>
              </div>
            </div>
          </div>

          {/* Dimensions */}
          <div className="glass-card p-6 lg:col-span-2">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">
              Dimensional Breakdown
            </h3>
            <div className="space-y-4">
              {riskData.dimensions.map(dim => (
                <DimensionBar key={dim.dimension} dimension={dim} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Explanation & Recommendations */}
      {riskData && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
              <Target className="w-4 h-4 text-indigo-400" />
              Analysis
            </h3>
            <div className="space-y-2">
              {riskData.explanation_lines.map((line, i) => (
                <div key={i} className="text-xs text-slate-300 flex items-start gap-2">
                  <span className="text-indigo-400 mt-0.5">•</span>
                  {line}
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              Recommendations
            </h3>
            <div className="space-y-2">
              {riskData.recommendations.map((rec, i) => (
                <div key={i} className="text-xs text-slate-300 flex items-start gap-2">
                  <span className="text-amber-400 mt-0.5">→</span>
                  {rec}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading risk scores...</span>
        </div>
      )}
    </div>
  )
}
