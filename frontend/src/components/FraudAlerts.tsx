/**
 * FraudAlerts Component — Fraud Pattern Detection Dashboard
 *
 * Displays fraud signals, severity breakdowns, pattern analysis,
 * and cross-payment fraud patterns detected by the rule-based engine.
 */

import { useEffect, useState } from 'react'
import {
  ShieldAlert,
  AlertTriangle,
  AlertOctagon,
  Eye,
  RefreshCw,
  Activity,
  Layers,
  CheckCircle2,
  Search,
  Lightbulb,
} from 'lucide-react'

interface FraudSignal {
  signal_id: string
  signal_type: string
  severity: string
  confidence: number
  payment_id: string
  detected_at: string
  description: string
  evidence: Record<string, any>
  recommendation: string
  methodology_version: string
}

interface FraudDashboardResponse {
  evaluated_at: string
  total_payments_analyzed: number
  total_signals: number
  signals_by_severity: Record<string, number>
  signals_by_type: Record<string, number>
  recent_signals: FraudSignal[]
  methodology_version: string
}

interface FraudAlertResponse {
  payment_id: string
  signals: FraudSignal[]
  overall_risk: string
  signal_count: number
  critical_count: number
  high_count: number
  evaluated_at: string
  methodology_version: string
}

interface FraudPatternItem {
  pattern_id: string
  pattern_type: string
  severity: string
  affected_payment_count: number
  affected_payment_ids: string[]
  description: string
  detected_at: string
}

const SEVERITY_CONFIG: Record<string, { bg: string; text: string; icon: React.ElementType }> = {
  CRITICAL: { bg: 'bg-rose-500/15', text: 'text-rose-300', icon: AlertOctagon },
  HIGH: { bg: 'bg-orange-500/15', text: 'text-orange-300', icon: AlertTriangle },
  MEDIUM: { bg: 'bg-amber-500/15', text: 'text-amber-300', icon: Eye },
  LOW: { bg: 'bg-slate-500/15', text: 'text-slate-300', icon: CheckCircle2 },
}

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  AMOUNT_ANOMALY: 'Amount Anomaly',
  VELOCITY_BURST: 'Velocity Burst',
  SOURCE_CONCENTRATION: 'Source Concentration',
  STATUS_CONTRADICTION: 'Status Contradiction',
  TIMESTAMP_INVERSION: 'Timestamp Inversion',
  MISSING_EVIDENCE_GAPS: 'Missing Evidence',
  CONFLICT_CLUSTER: 'Conflict Cluster',
  HIGH_AMOUNT: 'High Value',
}

function SignalCard({ signal }: { signal: FraudSignal }) {
  const config = SEVERITY_CONFIG[signal.severity] || SEVERITY_CONFIG.LOW
  const Icon = config.icon

  return (
    <div className={`neo-card p-4 border-l-2 ${
      signal.severity === 'CRITICAL' ? 'border-l-rose-500' :
      signal.severity === 'HIGH' ? 'border-l-orange-500' :
      signal.severity === 'MEDIUM' ? 'border-l-amber-500' :
      'border-l-slate-500'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${config.bg} ${config.text}`}>
              <Icon className="w-3 h-3" />
              {signal.severity}
            </span>
            <span className="text-xs text-slate-300 font-medium">
              {SIGNAL_TYPE_LABELS[signal.signal_type] || signal.signal_type}
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              {(signal.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>

          <p className="text-sm text-slate-200 mb-2">{signal.description}</p>

          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] bg-indigo-500/15 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/20 font-mono">
              {signal.payment_id}
            </span>
            <span className="text-[10px] text-slate-500">
              {new Date(signal.detected_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="text-[11px] text-amber-300/80 bg-amber-500/5 rounded-lg p-2 border border-amber-500/10">
            <span className="flex items-start gap-1.5">
              <Lightbulb className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{signal.recommendation}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export function FraudAlerts() {
  const [dashboard, setDashboard] = useState<FraudDashboardResponse | null>(null)
  const [payments, setPayments] = useState<Array<{ razorpay_payment_id: string }>>([])
  const [selectedPayment, setSelectedPayment] = useState('')
  const [paymentAlert, setPaymentAlert] = useState<FraudAlertResponse | null>(null)
  const [patterns, setPatterns] = useState<FraudPatternItem[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'dashboard' | 'payment' | 'patterns'>('dashboard')

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/fraud/dashboard').then(r => r.ok ? r.json() : null),
      fetch('/api/v1/payments').then(r => r.json()),
      fetch('/api/v1/fraud/patterns').then(r => r.ok ? r.json() : null),
    ]).then(([dashData, payData, patData]) => {
      if (dashData) setDashboard(dashData)
      setPayments(payData)
      if (patData) setPatterns(patData.patterns || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedPayment) return
    fetch(`/api/v1/payments/${selectedPayment}/fraud-check`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setPaymentAlert(data))
      .catch(() => setPaymentAlert(null))
  }, [selectedPayment])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated premium-ring p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-rose-500/10">
                <ShieldAlert className="w-5 h-5 text-rose-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Fraud Pattern Detection</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Deterministic rule-based fraud signal detection — no ML, pure evidence-based analysis
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-3">
        {[
          { key: 'dashboard' as const, label: 'Dashboard', icon: Activity },
          { key: 'payment' as const, label: 'Payment Check', icon: Search },
          { key: 'patterns' as const, label: 'Cross-Payment Patterns', icon: Layers },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              tab === t.key ? 'tab-glass-active' : 'tab-glass text-slate-400 hover:text-slate-200'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Dashboard Tab */}
      {tab === 'dashboard' && dashboard && (
        <div className="space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="metric-card">
              <div className="text-xs text-slate-400 mb-1">Payments Analyzed</div>
              <div className="text-2xl font-extrabold text-indigo-400">{dashboard.total_payments_analyzed}</div>
            </div>
            <div className="metric-card">
              <div className="text-xs text-slate-400 mb-1">Total Signals</div>
              <div className="text-2xl font-extrabold text-rose-400">{dashboard.total_signals}</div>
            </div>
            <div className="metric-card">
              <div className="text-xs text-slate-400 mb-1">Critical Signals</div>
              <div className="text-2xl font-extrabold text-rose-400">
                {dashboard.signals_by_severity.CRITICAL || 0}
              </div>
            </div>
            <div className="metric-card">
              <div className="text-xs text-slate-400 mb-1">High Signals</div>
              <div className="text-2xl font-extrabold text-orange-400">
                {dashboard.signals_by_severity.HIGH || 0}
              </div>
            </div>
          </div>

          {/* Severity Breakdown */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">Signals by Type</h3>
            <div className="space-y-3">
              {Object.entries(dashboard.signals_by_type).map(([type, count]) => (
                <div key={type} className="flex items-center gap-3">
                  <span className="text-xs text-slate-300 w-48 truncate">
                    {SIGNAL_TYPE_LABELS[type] || type}
                  </span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500/50 rounded-full"
                      style={{ width: `${Math.min(100, (count / Math.max(1, dashboard.total_signals)) * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-bold text-slate-300 w-8 text-right">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Signals */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">Recent Signals</h3>
            <div className="space-y-3">
              {dashboard.recent_signals.length === 0 ? (
                <div className="neo-inset rounded-xl p-8 text-center">
                  <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                  <p className="text-slate-400 text-sm">No fraud signals detected</p>
                </div>
              ) : (
                dashboard.recent_signals.map(sig => (
                  <SignalCard key={sig.signal_id} signal={sig} />
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Payment Check Tab */}
      {tab === 'payment' && (
        <div className="space-y-6">
          <div className="glass-card p-4">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <label className="text-xs text-slate-400 block mb-1">Select Payment to Analyze</label>
                <select
                  value={selectedPayment}
                  onChange={e => setSelectedPayment(e.target.value)}
                  className="glass-input w-full text-sm"
                >
                  <option value="">Choose a payment...</option>
                  {payments.map(p => (
                    <option key={p.razorpay_payment_id} value={p.razorpay_payment_id}>
                      {p.razorpay_payment_id}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {paymentAlert && (
            <div className="space-y-4">
              <div className="glass-card p-4 flex items-center justify-between">
                <div>
                  <span className="text-sm font-bold text-white">{paymentAlert.payment_id}</span>
                  <span className="ml-3 text-xs text-slate-400">{paymentAlert.signal_count} signals</span>
                </div>
                <span className={`text-sm font-bold px-3 py-1 rounded-full ${
                  paymentAlert.overall_risk === 'CLEAR' ? 'bg-emerald-500/15 text-emerald-300' :
                  paymentAlert.overall_risk === 'ELEVATED' ? 'bg-amber-500/15 text-amber-300' :
                  paymentAlert.overall_risk === 'SUSPICIOUS' ? 'bg-orange-500/15 text-orange-300' :
                  'bg-rose-500/15 text-rose-300'
                }`}>
                  {paymentAlert.overall_risk}
                </span>
              </div>

              {paymentAlert.signals.length === 0 ? (
                <div className="glass-card p-8 text-center">
                  <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
                  <p className="text-slate-400 text-sm">No fraud signals detected for this payment</p>
                </div>
              ) : (
                paymentAlert.signals.map(sig => (
                  <SignalCard key={sig.signal_id} signal={sig} />
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Patterns Tab */}
      {tab === 'patterns' && (
        <div className="space-y-4">
          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">Cross-Payment Fraud Patterns</h3>
            {patterns.length === 0 ? (
              <div className="neo-inset rounded-xl p-8 text-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                <p className="text-slate-400 text-sm">No cross-payment fraud patterns detected</p>
              </div>
            ) : (
              <div className="space-y-3">
                {patterns.map(p => (
                  <div key={p.pattern_id} className="neo-card p-4 border-l-2 border-l-amber-500">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold text-slate-200">{p.pattern_type}</span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        p.severity === 'HIGH' ? 'bg-rose-500/15 text-rose-300' :
                        p.severity === 'MEDIUM' ? 'bg-amber-500/15 text-amber-300' :
                        'bg-slate-500/15 text-slate-300'
                      }`}>
                        {p.severity}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 mb-2">{p.description}</p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-500">
                        Affecting {p.affected_payment_count} payment(s)
                      </span>
                      {p.affected_payment_ids.length > 0 && (
                        <div className="flex gap-1 flex-wrap">
                          {p.affected_payment_ids.slice(0, 3).map(id => (
                            <span key={id} className="text-[9px] font-mono bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">
                              {id}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card p-8 flex items-center justify-center gap-4">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-slate-400 text-sm">Loading fraud detection data...</span>
        </div>
      )}
    </div>
  )
}
