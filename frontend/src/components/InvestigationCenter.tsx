/**
 * InvestigationCenter Component — Investigation Command Center
 *
 * Provides full-text search across all entities, payment investigation
 * profiles, unified timelines, and actionable investigation recommendations.
 */

import { useEffect, useState } from 'react'
import {
  Search,
  Compass,
  Clock,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  FileText,
  GitBranch,
  Shield,
  Eye,
  Target,
} from 'lucide-react'

interface SearchResult {
  result_type: string
  entity_id: string
  title: string
  subtitle: string
  relevance_score: number
  metadata: Record<string, any>
  payment_id: string | null
  timestamp: string | null
}

interface SearchResponse {
  query: string
  results: SearchResult[]
  total_results: number
  search_time_ms: number
  suggestions: string[]
}

interface InvestigationProfile {
  payment_id: string
  payment_status: string
  amount_minor: number | null
  currency: string | null
  total_evidence: number
  distinct_sources: number
  distinct_events: number
  evidence_types: string[]
  risk_score: number | null
  risk_level: string | null
  total_conflicts: number
  open_conflicts: number
  coverage_status: string | null
  key_facts: Array<{
    fact_type: string
    canonical_value: string
    observation_count: number
    source_count: number
    status: string
  }>
  timeline_highlights: Array<{
    event_type: string
    timestamp: string | null
  }>
  investigation_steps: string[]
  anomaly_flags: string[]
  evaluated_at: string
}

interface TimelineEvent {
  timestamp: string
  event_type: string
  category: string
  severity: string
  title: string
  description: string
  entity_id: string | null
  metadata: Record<string, any>
}

interface InvestigationRecommendation {
  recommendation_id: string
  priority: string
  category: string
  title: string
  description: string
  payment_id: string | null
  generated_at: string
}

const CATEGORY_COLORS: Record<string, string> = {
  EVIDENCE: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/20',
  CONFLICT: 'bg-rose-500/15 text-rose-300 border-rose-500/20',
  INTEGRITY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20',
  FRAUD: 'bg-amber-500/15 text-amber-300 border-amber-500/20',
  SYSTEM: 'bg-slate-500/15 text-slate-300 border-slate-500/20',
}

const RESULT_TYPE_ICONS: Record<string, React.ElementType> = {
  PAYMENT: Shield,
  EVIDENCE: Eye,
  CONFLICT: AlertTriangle,
  FACT: GitBranch,
  TRACE: FileText,
}

export function InvestigationCenter() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null)
  const [searching, setSearching] = useState(false)

  const [payments, setPayments] = useState<Array<{ razorpay_payment_id: string }>>([])
  const [selectedPayment, setSelectedPayment] = useState('')
  const [profile, setProfile] = useState<InvestigationProfile | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [recommendations, setRecommendations] = useState<InvestigationRecommendation[]>([])

  const [activeTab, setActiveTab] = useState<'search' | 'profile' | 'timeline' | 'recommendations'>('search')

  useEffect(() => {
    fetch('/api/v1/payments')
      .then(r => r.json())
      .then(data => setPayments(data))
      .catch(() => {})

    fetch('/api/v1/investigate/recommendations')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) setRecommendations(data.recommendations || [])
      })
      .catch(() => {})
  }, [])

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const res = await fetch(`/api/v1/investigate/search?q=${encodeURIComponent(searchQuery)}`)
      if (res.ok) setSearchResults(await res.json())
    } catch (err) {
      console.error('Search failed', err)
    } finally {
      setSearching(false)
    }
  }

  const loadPaymentProfile = async (paymentId: string) => {
    setSelectedPayment(paymentId)
    setActiveTab('profile')

    try {
      const [profileRes, timelineRes] = await Promise.all([
        fetch(`/api/v1/investigate/payments/${paymentId}/profile`),
        fetch(`/api/v1/investigate/payments/${paymentId}/timeline`),
      ])

      if (profileRes.ok) setProfile(await profileRes.json())
      if (timelineRes.ok) {
        const data = await timelineRes.json()
        setTimeline(data.events || [])
      }
    } catch (err) {
      console.error('Failed to load profile', err)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-purple-500/10">
                <Compass className="w-5 h-5 text-purple-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Investigation Command Center</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Search, investigate, and analyze payment evidence with guided workflows
            </p>
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Search payments, evidence, conflicts, facts..."
              className="glass-input w-full pl-10 pr-4"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="neo-btn-indigo flex items-center gap-2 disabled:opacity-50"
          >
            {searching ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            Search
          </button>
        </div>

        {/* Suggestions */}
        {searchResults?.suggestions && searchResults.suggestions.length > 0 && (
          <div className="flex gap-2 mt-3 flex-wrap">
            <span className="text-[10px] text-slate-500">Suggestions:</span>
            {searchResults.suggestions.map(s => (
              <button
                key={s}
                onClick={() => { setSearchQuery(s); }}
                className="text-[10px] bg-indigo-500/10 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {[
          { key: 'search' as const, label: 'Search Results', icon: Search },
          { key: 'profile' as const, label: 'Payment Profile', icon: FileText },
          { key: 'timeline' as const, label: 'Timeline', icon: Clock },
          { key: 'recommendations' as const, label: 'Recommendations', icon: Target },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === t.key ? 'tab-glass-active' : 'tab-glass text-slate-400 hover:text-slate-200'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Search Results Tab */}
      {activeTab === 'search' && searchResults && (
        <div className="space-y-4">
          <div className="glass-card p-4 flex items-center justify-between">
            <span className="text-sm text-slate-300">
              {searchResults.total_results} results for "<span className="text-indigo-300">{searchResults.query}</span>"
            </span>
            <span className="text-[10px] text-slate-500">{searchResults.search_time_ms.toFixed(1)}ms</span>
          </div>

          <div className="space-y-3">
            {searchResults.results.map((result, i) => {
              const Icon = RESULT_TYPE_ICONS[result.result_type] || Eye
              return (
                <div
                  key={`${result.entity_id}-${i}`}
                  onClick={() => result.payment_id && loadPaymentProfile(result.payment_id)}
                  className={`neo-card p-4 ${result.payment_id ? 'cursor-pointer hover:border-indigo-500/20' : ''}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="neo-pressed p-2 rounded-lg shrink-0">
                      <Icon className="w-4 h-4 text-indigo-400" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-bold text-slate-200">{result.title}</span>
                        <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full border border-slate-700">
                          {result.result_type}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{result.subtitle}</p>
                      {result.timestamp && (
                        <span className="text-[10px] text-slate-500 mt-1 block">
                          {new Date(result.timestamp).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-lg font-extrabold text-indigo-400">
                        {(result.relevance_score * 100).toFixed(0)}
                      </div>
                      <div className="text-[9px] text-slate-500">relevance</div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="space-y-4">
          {/* Payment selector */}
          <div className="glass-card p-4">
            <label className="text-xs text-slate-400 block mb-1">Select Payment to Investigate</label>
            <select
              value={selectedPayment}
              onChange={e => loadPaymentProfile(e.target.value)}
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

          {profile && (
            <div className="space-y-4">
              {/* Profile Header */}
              <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">{profile.payment_id}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      profile.payment_status === 'captured' ? 'bg-emerald-500/15 text-emerald-300' :
                      'bg-slate-500/15 text-slate-300'
                    }`}>
                      {profile.payment_status}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="neo-inset p-3 rounded-xl text-center">
                    <div className="text-2xl font-extrabold text-indigo-400">{profile.total_evidence}</div>
                    <div className="text-[10px] text-slate-400">Evidence</div>
                  </div>
                  <div className="neo-inset p-3 rounded-xl text-center">
                    <div className="text-2xl font-extrabold text-emerald-400">{profile.distinct_sources}</div>
                    <div className="text-[10px] text-slate-400">Sources</div>
                  </div>
                  <div className="neo-inset p-3 rounded-xl text-center">
                    <div className="text-2xl font-extrabold text-rose-400">{profile.open_conflicts}</div>
                    <div className="text-[10px] text-slate-400">Open Conflicts</div>
                  </div>
                  <div className="neo-inset p-3 rounded-xl text-center">
                    <div className="text-2xl font-extrabold text-purple-400">{profile.distinct_events}</div>
                    <div className="text-[10px] text-slate-400">Events</div>
                  </div>
                </div>
              </div>

              {/* Anomaly Flags */}
              {profile.anomaly_flags.length > 0 && (
                <div className="glass-card p-4 border-l-2 border-l-amber-500">
                  <h4 className="text-xs font-bold text-amber-300 uppercase tracking-wider mb-2">⚠ Anomaly Flags</h4>
                  <div className="flex gap-2 flex-wrap">
                    {profile.anomaly_flags.map(flag => (
                      <span key={flag} className="text-[10px] bg-amber-500/15 text-amber-300 px-2 py-0.5 rounded-full border border-amber-500/20 font-bold">
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Investigation Steps */}
              <div className="glass-card p-6">
                <h4 className="text-sm font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Target className="w-4 h-4 text-indigo-400" />
                  Investigation Steps
                </h4>
                <div className="space-y-2">
                  {profile.investigation_steps.map((step, i) => (
                    <div key={i} className="flex items-start gap-3 neo-card p-3">
                      <div className="neo-pressed p-1.5 rounded-lg shrink-0">
                        <span className="text-xs font-bold text-indigo-400">{i + 1}</span>
                      </div>
                      <span className="text-xs text-slate-300">{step}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Key Facts */}
              {profile.key_facts.length > 0 && (
                <div className="glass-card p-6">
                  <h4 className="text-sm font-bold text-white uppercase tracking-wider mb-3">Key Facts</h4>
                  <div className="space-y-2">
                    {profile.key_facts.map((fact, i) => (
                      <div key={i} className="neo-card p-3 flex items-center justify-between">
                        <div>
                          <span className="text-xs font-bold text-slate-200">{fact.fact_type}</span>
                          <span className="text-xs text-emerald-400 ml-2 font-mono">{fact.canonical_value}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500">
                          <span>{fact.observation_count} obs</span>
                          <span>{fact.source_count} src</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Timeline Tab */}
      {activeTab === 'timeline' && (
        <div className="space-y-4">
          {!selectedPayment ? (
            <div className="glass-card p-8 text-center">
              <Clock className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Select a payment in the Profile tab first</p>
            </div>
          ) : timeline.length === 0 ? (
            <div className="glass-card p-8 text-center">
              <Clock className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400 text-sm">No timeline events for this payment</p>
            </div>
          ) : (
            <div className="glass-card p-6">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4">
                Investigation Timeline — {selectedPayment}
              </h3>
              <div className="relative">
                {/* Vertical line */}
                <div className="absolute left-4 top-0 bottom-0 w-px bg-slate-700" />

                <div className="space-y-4">
                  {timeline.map((event, i) => (
                    <div key={i} className="relative pl-10">
                      {/* Dot */}
                      <div className={`absolute left-2.5 top-2 w-3 h-3 rounded-full border-2 ${
                        event.severity === 'ALERT' ? 'bg-rose-500 border-rose-400' :
                        event.severity === 'WARNING' ? 'bg-amber-500 border-amber-400' :
                        'bg-indigo-500 border-indigo-400'
                      }`} />

                      <div className="neo-card p-3">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                              CATEGORY_COLORS[event.category] || CATEGORY_COLORS.SYSTEM
                            }`}>
                              {event.category}
                            </span>
                            <span className="text-xs font-medium text-slate-200">{event.title}</span>
                          </div>
                          <span className="text-[10px] text-slate-500 font-mono shrink-0">
                            {new Date(event.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400">{event.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recommendations Tab */}
      {activeTab === 'recommendations' && (
        <div className="space-y-4">
          <div className="glass-card p-6">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
              <Target className="w-4 h-4 text-amber-400" />
              Investigation Recommendations
            </h3>
            {recommendations.length === 0 ? (
              <div className="neo-inset rounded-xl p-8 text-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                <p className="text-slate-400 text-sm">No recommendations — system operating normally</p>
              </div>
            ) : (
              <div className="space-y-3">
                {recommendations.map(rec => (
                  <div
                    key={rec.recommendation_id}
                    onClick={() => rec.payment_id && loadPaymentProfile(rec.payment_id)}
                    className={`neo-card p-4 border-l-2 ${
                      rec.priority === 'URGENT' ? 'border-l-rose-500' :
                      rec.priority === 'HIGH' ? 'border-l-orange-500' :
                      rec.priority === 'MEDIUM' ? 'border-l-amber-500' :
                      'border-l-slate-500'
                    } ${rec.payment_id ? 'cursor-pointer' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold text-slate-200">{rec.title}</span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        rec.priority === 'URGENT' ? 'bg-rose-500/15 text-rose-300' :
                        rec.priority === 'HIGH' ? 'bg-orange-500/15 text-orange-300' :
                        rec.priority === 'MEDIUM' ? 'bg-amber-500/15 text-amber-300' :
                        'bg-slate-500/15 text-slate-300'
                      }`}>
                        {rec.priority}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mb-2">{rec.description}</p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full">
                        {rec.category}
                      </span>
                      {rec.payment_id && (
                        <span className="text-[10px] text-indigo-300 font-mono">{rec.payment_id}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
