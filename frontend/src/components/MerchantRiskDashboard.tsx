/**
 * MerchantRiskDashboard Component — Risk Profiling Across Payment Dimensions
 *
 * Shows risk profiles for payment methods, currencies, and other entities
 * with risk scores, success rates, and key risk indicators.
 */

import { useEffect, useState } from 'react'
import {
  Shield,
  RefreshCw,
  AlertTriangle,
  CreditCard,
  Globe,
} from 'lucide-react'

interface MerchantRiskProfile {
  entity_id: string
  entity_type: string
  risk_score: number
  risk_level: string
  total_transactions: number
  success_rate: number
  avg_amount: number
  failure_rate: number
  conflict_rate: number
  fraud_signal_count: number
  key_risks: string[]
  recommendations: string[]
  evaluated_at: string
}

interface MerchantRiskDashboardData {
  evaluated_at: string
  profiles: MerchantRiskProfile[]
  total_entities: number
  high_risk_count: number
  methodology_version: string
}

function getRiskColor(score: number): string {
  if (score >= 76) return 'text-emerald-400'
  if (score >= 51) return 'text-amber-400'
  if (score >= 26) return 'text-orange-400'
  return 'text-rose-400'
}

function getRiskBg(score: number): string {
  if (score >= 76) return 'bg-emerald-500/15'
  if (score >= 51) return 'bg-amber-500/15'
  if (score >= 26) return 'bg-orange-500/15'
  return 'bg-rose-500/15'
}

export function MerchantRiskDashboard() {
  const [data, setData] = useState<MerchantRiskDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedProfile, setSelectedProfile] = useState<MerchantRiskProfile | null>(null)

  useEffect(() => {
    fetch('/api/v1/analytics/merchant-risk')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="neo-pressed p-2.5 rounded-xl bg-purple-500/10">
            <Shield className="w-5 h-5 text-purple-400" />
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Merchant Risk Profiling</h2>
        </div>
        <p className="text-slate-400 text-sm ml-12">
          Risk assessment across payment methods, currencies, and transaction patterns
        </p>
      </div>

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Total Entities</div>
            <div className="text-2xl font-extrabold text-indigo-400">{data.total_entities}</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">High Risk</div>
            <div className="text-2xl font-extrabold text-rose-400">{data.high_risk_count}</div>
          </div>
          <div className="metric-card">
            <div className="text-xs text-slate-400 mb-1">Low Risk</div>
            <div className="text-2xl font-extrabold text-emerald-400">{data.total_entities - data.high_risk_count}</div>
          </div>
        </div>
      )}

      {/* Profiles Grid */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {data.profiles.map(profile => (
            <div
              key={`${profile.entity_type}-${profile.entity_id}`}
              onClick={() => setSelectedProfile(
                selectedProfile?.entity_id === profile.entity_id ? null : profile
              )}
              className={`glass-card p-5 cursor-pointer transition-all hover:scale-[1.01] ${
                selectedProfile?.entity_id === profile.entity_id ? 'border-indigo-500/30' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  {profile.entity_type === 'PAYMENT_METHOD' ? (
                    <CreditCard className="w-4 h-4 text-indigo-400" />
                  ) : (
                    <Globe className="w-4 h-4 text-emerald-400" />
                  )}
                  <div>
                    <div className="text-sm font-bold text-slate-200 uppercase">{profile.entity_id}</div>
                    <div className="text-[10px] text-slate-500">{profile.entity_type.replace('_', ' ')}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-2xl font-extrabold ${getRiskColor(profile.risk_score)}`}>
                    {profile.risk_score.toFixed(0)}
                  </div>
                  <div className={`text-[10px] font-bold px-2 py-0.5 rounded ${getRiskBg(profile.risk_score)} ${
                    getRiskColor(profile.risk_score)
                  }`}>
                    {profile.risk_level.replace('_', ' ')}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 mb-3">
                <div className="neo-inset p-2 rounded-lg text-center">
                  <div className="text-lg font-bold text-slate-200">{profile.total_transactions}</div>
                  <div className="text-[9px] text-slate-500">Transactions</div>
                </div>
                <div className="neo-inset p-2 rounded-lg text-center">
                  <div className="text-lg font-bold text-emerald-400">{profile.success_rate}%</div>
                  <div className="text-[9px] text-slate-500">Success</div>
                </div>
                <div className="neo-inset p-2 rounded-lg text-center">
                  <div className="text-lg font-bold text-rose-400">{profile.failure_rate}%</div>
                  <div className="text-[9px] text-slate-500">Failure</div>
                </div>
              </div>

              {/* Key Risks */}
              <div className="space-y-1">
                {profile.key_risks.map((risk, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px] text-slate-400">
                    <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
                    {risk}
                  </div>
                ))}
              </div>

              {/* Expanded Details */}
              {selectedProfile?.entity_id === profile.entity_id && (
                <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Recommendations</div>
                  {profile.recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px] text-indigo-300">
                      <span>→</span> {rec}
                    </div>
                  ))}
                  <div className="grid grid-cols-2 gap-2 mt-2 text-[10px] text-slate-500">
                    <div>Avg Amount: ₹{profile.avg_amount.toFixed(2)}</div>
                    <div>Conflict Rate: {profile.conflict_rate}%</div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading merchant risk data...</span>
        </div>
      )}
    </div>
  )
}
