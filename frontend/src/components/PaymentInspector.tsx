import { useState, useEffect } from 'react'
import { format } from 'date-fns'
import { CheckCircle, XCircle, Clock, CreditCard, DollarSign, RefreshCw, Receipt, Layers, ShieldCheck, GitCompare, Link2, AlertTriangle } from 'lucide-react'
import { EmptyState, LoadingState, PageHeader, Panel, SubTabs } from './ui'

type DetailTab = 'overview' | 'evidence' | 'integrity'

interface PaymentEvent {
  event_type: string
  event_timestamp: string
}

interface Payment {
  razorpay_payment_id: string
  amount_minor: number | null
  currency: string | null
  status: string
  payment_method_type: string | null
  payment_method_details: Record<string, any> | null
  captured: boolean
  first_observed_at: string
  last_observed_at: string
}

interface PaymentWithEvents extends Payment {
  events: PaymentEvent[]
}

interface GraphNode {
  evidence_id: number
  evidence_type: string
  subject_type: string
  subject_id: string
  value: string | null
  value_type: string
  source_type: string
  observed_at: string
  payment_event_id: number | null
  webhook_event_id: number | null
  extraction_version: string
}

interface GraphEdge {
  edge_id: number
  source_evidence_id: number
  target_evidence_id: number
  relationship_type: string
  relationship_source: string
  rule_version: string
  provenance_metadata: Record<string, any> | null
  created_at: string
}

interface PaymentGraph {
  payment_id: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

interface Evidence {
  internal_id: number
  evidence_type: string
  subject_type: string
  subject_id: string
  value: string | null
  value_type: string
  source_type: string
  observed_at: string
  extraction_method: string
}

interface QualitySnapshot {
  snapshot_id: number
  evidence_id: number
  evaluated_at: string
  age_seconds: number | null
  freshness_state: string
  freshness_policy_key: string
  freshness_methodology_version: string
  source_type: string
  source_directness: string
  source_authority_level: string
  source_methodology_version: string
  historical_reliability_status: string
  reliability_sample_count: number | null
  reliability_methodology_version: string
  snapshot_metadata: Record<string, any> | null
  created_at: string
}

interface EvidenceQualityItem {
  evidence_id: number
  evidence_type: string
  subject_id: string
  observed_at: string
  latest_snapshot: QualitySnapshot | null
  snapshot_count: number
}

interface PaymentQuality {
  payment_id: string
  evidence_quality: EvidenceQualityItem[]
  total_evidence_count: number
  snapshot_count: number
}

interface ClaimItem {
  internal_id: number
  subject_type: string
  subject_id: string
  claim_type: string
  claim_key: string
  canonical_value: string
  created_at: string
  supporting_evidence_count: number
}

interface EvidenceGroupItem {
  internal_id: number
  payment_id: string
  group_type: string
  grouping_key: string
  rule_version: string
  metadata: Record<string, any> | null
  created_at: string
  member_count: number
}

interface CorroborationItem {
  internal_id: number
  claim_id: number
  payment_id: string
  corroboration_type: string
  independence_status: string
  observation_count: number
  distinct_sources_count: number
  distinct_events_count: number
  methodology_version: string
  details: Record<string, any> | null
  created_at: string
}

interface StructureSnapshotItem {
  internal_id: number
  payment_id: string
  evaluated_at: string
  total_observations: number
  distinct_claims: number
  distinct_sources: number
  distinct_events: number
  distinct_groups: number
  largest_group_size: number
  group_hhi: number
  corroborated_claim_count: number
  multi_source_claim_count: number
  methodology_version: string
  structural_summary: Record<string, any> | null
  created_at: string
}

interface PaymentStructure {
  payment_id: string
  snapshot: StructureSnapshotItem | null
  claims: ClaimItem[]
  groups: EvidenceGroupItem[]
  corroborations: CorroborationItem[]
}

interface EvidenceTimelineEntry {
  payment_event_id: number
  event_type: string
  event_timestamp: string | null
  source_type: string
  evidence: Evidence[]
}

interface EvidenceTimeline {
  payment_id: string
  timeline: EvidenceTimelineEntry[]
  total_evidence_count: number
}

interface ConflictItem {
  internal_id: number
  payment_id: string
  claim_a_id: number
  claim_b_id: number
  conflict_type: string
  severity: string
  status: string
  detected_at: string
  rule_version: string
  explanation: Record<string, any> | null
  created_at: string
  resolutions: Array<{
    internal_id: number
    resolution_type: string
    explanation: string
    resolved_at: string
    rule_version: string
  }>
}

interface PaymentConsistency {
  payment_id: string
  is_consistent: boolean
  total_conflicts: number
  open_conflicts: number
  resolved_conflicts: number
  conflicts: ConflictItem[]
}

interface DimensionResult {
  status: string
  reason: string
  inputs: Record<string, any>
}

interface IntegritySnapshot {
  payment_id: string
  evaluated_at: string
  methodology_version: string
  overall_status: string
  evidence_count: number
  source_count: number
  conflict_count: number
  open_conflict_count: number
  freshness_result: DimensionResult | null
  source_result: DimensionResult | null
  independence_result: DimensionResult | null
  corroboration_result: DimensionResult | null
  consistency_result: DimensionResult | null
  explanation_lines: string[]
  limitations: string[]
  created_at: string
}

// Phase 11 — Evidence Evolution interfaces
interface StateSnapshot {
  snapshot_id: number
  payment_id: string
  evaluation_time: string
  overall_integrity_status: string
  evidence_count: number
  source_count: number
  claim_count: number
  conflict_count: number
  open_conflict_count: number
  corroboration_status: string
  independence_status: string
  freshness_status: string
  consistency_status: string
  methodology_version: string
  integrity_trace_id: string | null
  created_at: string
}

interface ChangeRecord {
  change_id: string
  payment_id: string
  detected_at: string
  change_type: string
  dimension: string
  previous_value: string | null
  current_value: string | null
  direct_cause: string | null
  causality: string | null
  explanation: string | null
  magnitude: string | null
  linked_evidence_id: number | null
  linked_conflict_id: number | null
  methodology_version: string | null
  previous_snapshot_id: number
  current_snapshot_id: number
}

interface StateHistoryResponse {
  payment_id: string
  history: StateSnapshot[]
  total: number
}

interface EvidenceChangesResponse {
  payment_id: string
  changes: ChangeRecord[]
  total: number
  dimension_filter: string | null
}

// Phase 13 — Multi-Source Evidence Reconciliation & Facts
interface EvidenceFact {
  internal_id: number
  payment_id: string
  fact_type: string
  canonical_value: string
  canonical_value_hash: string
  status: string
  first_observed_at: string
  last_observed_at: string
  observation_count: number
  distinct_source_count: number
  methodology_version: string
}

interface PaymentFactsResponse {
  payment_id: string
  total_facts: number
  active_facts_count: number
  facts: EvidenceFact[]
}

// Phase 14 — Evidence Lineage & Causal Explanation interfaces
interface LineageNode {
  node_id: string
  node_type: string
  entity_id: string
  label: string
  timestamp: string | null
  metadata: Record<string, any>
}

interface LineageEdge {
  source_node_id: string
  target_node_id: string
  edge_type: string
  causal_role: string
  linkage_type: string
  explanation: string
}

interface LineageGap {
  location: string
  expected_edge_type: string
  reason: string
  detected_at: string
}

interface LineageExplanation {
  summary: string
  detail_lines: string[]
}

interface LineageSummary {
  fact_count: number
  observation_count: number
  source_count: number
  conflict_count: number
  claim_count: number
  dimension_count: number
  affected_dimensions: string[]
  has_integrity_trace: boolean
  has_state_changes: boolean
}

interface LineageEvaluationContext {
  as_of: string | null
  methodology_version: string
  truncated: boolean
  node_count: number
  edge_count: number
  gap_count: number
}

interface PaymentLineageResponse {
  payment_id: string
  nodes: LineageNode[]
  edges: LineageEdge[]
  gaps: LineageGap[]
  completeness: string
  summary: LineageSummary
  explanation: LineageExplanation
  evaluation_context: LineageEvaluationContext
}

// Phase 15 — Evidence Completeness & Coverage interfaces
interface CoverageMetricSummary {
  total_applicable: number
  required_present: number
  required_missing: number
  expected_present: number
  expected_missing: number
  optional_present: number
  conflicted: number
  unknown: number
  not_applicable: number
}

interface CoverageRequirementResult {
  requirement_id: string
  requirement_type: string
  evidence_type: string
  fact_type: string
  expected_state: string
  observed_state: string
  matched_fact_id: number | null
  matched_observation_ids: number[] | null
  search_scope_summary: string
  explanation: string
}

interface MissingEvidenceItem {
  requirement_id: string
  requirement_type: string
  evidence_type: string
  fact_type: string
  why_expected: string
  search_scope: string
  search_result: string
  explanation: string
}

interface PaymentCoverageResponse {
  payment_id: string
  profile_id: string
  profile_version: string
  methodology_version: string
  overall_coverage_status: string
  evaluated_at: string
  metrics: CoverageMetricSummary
  results: CoverageRequirementResult[]
  missing_evidence: MissingEvidenceItem[]
  explanation: string
  evaluation_context: Record<string, any>
}

// Phase 16 — Evidence Reliability & Uncertainty Calibration interfaces
interface UncertaintyItem {
  boundary_type: string
  topic: string
  statement: string
  scope: string
}

interface FactReliabilityItem {
  fact_id: number
  fact_type: string
  canonical_value: string
  overall_state: string
  explanation: string
}

interface PaymentReliabilityResponse {
  payment_id: string
  methodology_version: string
  overall_state: string
  evaluated_at: string
  facts_assessed: number
  fact_assessments: FactReliabilityItem[]
  uncertainty_summary: UncertaintyItem[]
  coverage_summary: string | null
  conflicts_summary: string | null
  explanation: string
}

// Phase 18 — Decision Replay & Differential Analysis interfaces
interface DecisionReplayResponse {
  payment_id: string
  evaluation_time: string
  methodology_version: string
  profile_version: string
  overall_status: string
  evidence_count: number
  source_count: number
  conflict_count: number
  coverage_status: string
  integrity_dimensions: Record<string, string>
  input_fingerprint: string
  result_fingerprint: string
  verification_status: string
  verified_trace_id: string | null
  mismatch_details: Record<string, any> | null
  replay_metadata: Record<string, any>
}

interface FactDiff {
  fact_id: number
  fact_type: string
  canonical_value: string
  category: string
  from_state?: string
  to_state?: string
  change_type?: string
}

interface EvidenceDecisionDiffResponse {
  payment_id: string
  from_time: string
  to_time: string
  methodology_version: string
  profile_version: string
  overall_status_t1: string
  overall_status_t2: string
  coverage_status_t1: string
  coverage_status_t2: string
  evidence_count_t1: number
  evidence_count_t2: number
  source_count_t1: number
  source_count_t2: number
  conflict_count_t1: number
  conflict_count_t2: number
  fact_diffs: FactDiff[]
  integrity_dimension_diffs: Record<string, { t1: string; t2: string }>
  coverage_requirement_diffs: any[]
  conflict_diffs: any[]
  diff_summary: string[]
  diff_methodology_version: string
}

interface ChangeExplanationLine {
  category: string
  statement: string
}

interface DecisionChangeExplanationResponse {
  payment_id: string
  from_time: string
  to_time: string
  methodology_version: string
  what_changed: ChangeExplanationLine[]
  why_it_mattered: ChangeExplanationLine[]
  what_remains_uncertain: ChangeExplanationLine[]
  causal_summary: string
  explanation_methodology_version: string
}

// Phase 19 Operational interfaces
interface DownstreamLayerStatus {
  layer_name: string
  status: string
  latest_evaluation_at: string | null
  is_current: boolean
  details?: Record<string, any>
}

interface PaymentOperationalStatusResponse {
  payment_id: string
  latest_evidence_at: string | null
  latest_canonical_at: string | null
  overall_freshness: string
  is_analysis_current: boolean
  pipeline_lag_seconds: number | null
  layers: Record<string, DownstreamLayerStatus>
  summary: string
}

const formatCurrency = (amount: number | null, currency: string | null) => {
  if (amount === null || currency === null) return 'Unknown'
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount / 100)
  } catch {
    return `${currency} ${(amount / 100).toFixed(2)}`
  }
}

const getStatusBadge = (status: string) => {
  switch (status.toLowerCase()) {
    case 'captured':
    case 'paid':
      return <span className="badge-glass-success"><CheckCircle className="w-3 h-3" /> Captured</span>
    case 'failed':
      return <span className="badge-glass-danger"><XCircle className="w-3 h-3" /> Failed</span>
    case 'authorized':
      return <span className="badge-glass-info"><Clock className="w-3 h-3" /> Authorized</span>
    default:
      return <span className="badge-glass text-slate-400">{status}</span>
  }
}

export function PaymentInspector() {
  const [payments, setPayments] = useState<Payment[]>([])
  const [selectedPayment, setSelectedPayment] = useState<PaymentWithEvents | null>(null)
  const [selectedTimeline, setSelectedTimeline] = useState<EvidenceTimeline | null>(null)
  const [selectedGraph, setSelectedGraph] = useState<PaymentGraph | null>(null)
  const [selectedQuality, setSelectedQuality] = useState<PaymentQuality | null>(null)
  const [selectedStructure, setSelectedStructure] = useState<PaymentStructure | null>(null)
  const [selectedConsistency, setSelectedConsistency] = useState<PaymentConsistency | null>(null)
  const [selectedIntegrity, setSelectedIntegrity] = useState<IntegritySnapshot | null>(null)
  const [selectedFacts, setSelectedFacts] = useState<EvidenceFact[]>([])
  const [selectedLineage, setSelectedLineage] = useState<PaymentLineageResponse | null>(null)
  const [selectedCoverage, setSelectedCoverage] = useState<PaymentCoverageResponse | null>(null)
  const [selectedOperationalStatus, setSelectedOperationalStatus] = useState<PaymentOperationalStatusResponse | null>(null)
  const [selectedReliability, setSelectedReliability] = useState<PaymentReliabilityResponse | null>(null)
  // Phase 18 state
  const [replayResult, setReplayResult] = useState<DecisionReplayResponse | null>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [diffResult, setDiffResult] = useState<EvidenceDecisionDiffResponse | null>(null)
  const [diffExplanation, setDiffExplanation] = useState<DecisionChangeExplanationResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffFromTime, setDiffFromTime] = useState('')
  const [diffToTime, setDiffToTime] = useState('')
  const [replayTab, setReplayTab] = useState<'replay' | 'diff'>('replay')

  const [reconciliationLoading, setReconciliationLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [stateHistory, setStateHistory] = useState<StateSnapshot[]>([])
  const [evolutionChanges, setEvolutionChanges] = useState<ChangeRecord[]>([])
  const [dimensionFilter, setDimensionFilter] = useState<string>('ALL')
  const [recomputeLoading, setRecomputeLoading] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('overview')

  useEffect(() => {
    fetchPayments()
  }, [])

  const fetchPayments = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/payments')
      if (res.ok) {
        const data = await res.json()
        setPayments(data)
      }
    } catch (error) {
      console.error('Failed to fetch payments', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchPaymentDetails = async (paymentId: string) => {
    setLoadingDetails(true)
    try {
      const [resDetails, resTimeline, resGraph, resQuality, resStructure, resConsistency, resIntegrity, resStateHistory, resChanges, resFacts, resLineage, resCoverage, resReliability, resOps] = await Promise.all([
        fetch(`/api/v1/payments/${paymentId}/events`),
        fetch(`/api/v1/payments/${paymentId}/evidence/timeline`),
        fetch(`/api/v1/graph/payments/${paymentId}`),
        fetch(`/api/v1/quality/payments/${paymentId}`),
        fetch(`/api/v1/payments/${paymentId}/structure`),
        fetch(`/api/v1/payments/${paymentId}/consistency`),
        fetch(`/api/v1/payments/${paymentId}/integrity`),
        fetch(`/api/v1/payments/${paymentId}/state-history`),
        fetch(`/api/v1/payments/${paymentId}/changes`),
        fetch(`/api/v1/payments/${paymentId}/facts`),
        fetch(`/api/v1/payments/${paymentId}/lineage`),
        fetch(`/api/v1/payments/${paymentId}/coverage`),
        fetch(`/api/v1/payments/${paymentId}/reliability`),
        fetch(`/api/v1/payments/${paymentId}/operational-status`),
      ])
      
      if (resDetails.ok) setSelectedPayment(await resDetails.json())
      if (resTimeline.ok) setSelectedTimeline(await resTimeline.json())
      if (resGraph.ok) setSelectedGraph(await resGraph.json())
      if (resOps.ok) setSelectedOperationalStatus(await resOps.json())
      else setSelectedOperationalStatus(null)
      if (resQuality.ok) setSelectedQuality(await resQuality.json())
      else setSelectedQuality(null)
      if (resStructure.ok) setSelectedStructure(await resStructure.json())
      else setSelectedStructure(null)
      if (resConsistency.ok) setSelectedConsistency(await resConsistency.json())
      else setSelectedConsistency(null)
      if (resIntegrity.ok) setSelectedIntegrity(await resIntegrity.json())
      else setSelectedIntegrity(null)
      if (resStateHistory.ok) {
        const stateData: StateHistoryResponse = await resStateHistory.json()
        setStateHistory(stateData.history || [])
      } else {
        setStateHistory([])
      }
      if (resChanges.ok) {
        const changesData: EvidenceChangesResponse = await resChanges.json()
        setEvolutionChanges(changesData.changes || [])
      } else {
        setEvolutionChanges([])
      }
      if (resFacts.ok) {
        const factsData: PaymentFactsResponse = await resFacts.json()
        setSelectedFacts(factsData.facts || [])
      } else {
        setSelectedFacts([])
      }
      if (resLineage.ok) {
        const lineageData: PaymentLineageResponse = await resLineage.json()
        setSelectedLineage(lineageData)
      } else {
        setSelectedLineage(null)
      }
      if (resCoverage.ok) {
        const coverageData: PaymentCoverageResponse = await resCoverage.json()
        setSelectedCoverage(coverageData)
      } else {
        setSelectedCoverage(null)
      }
      if (resReliability.ok) {
        const reliabilityData: PaymentReliabilityResponse = await resReliability.json()
        setSelectedReliability(reliabilityData)
      } else {
        setSelectedReliability(null)
      }
    } catch (error) {
      console.error('Failed to fetch payment details or timeline', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const triggerReconciliation = async (paymentId: string) => {
    setReconciliationLoading(true)
    try {
      const res = await fetch(`/api/v1/payments/${paymentId}/reconcile`, { method: 'POST' })
      if (res.ok) {
        const data: PaymentFactsResponse = await res.json()
        setSelectedFacts(data.facts || [])
      }
    } catch (err) {
      console.error('Reconciliation failed', err)
    } finally {
      setReconciliationLoading(false)
    }
  }


  const recomputeEvolution = async (paymentId: string) => {
    setRecomputeLoading(true)
    try {
      const res = await fetch(`/api/v1/payments/${paymentId}/integrity/recompute`, { method: 'POST' })
      if (res.ok) {
        const [resHistory, resChanges] = await Promise.all([
          fetch(`/api/v1/payments/${paymentId}/state-history`),
          fetch(`/api/v1/payments/${paymentId}/changes`),
        ])
        if (resHistory.ok) {
          const d: StateHistoryResponse = await resHistory.json()
          setStateHistory(d.history || [])
        }
        if (resChanges.ok) {
          const d: EvidenceChangesResponse = await resChanges.json()
          setEvolutionChanges(d.changes || [])
        }
      }
    } catch (err) {
      console.error('Recompute failed', err)
    } finally {
      setRecomputeLoading(false)
    }
  }

  const triggerReplay = async (paymentId: string) => {
    setReplayLoading(true)
    try {
      const res = await fetch(`/api/v1/payments/${paymentId}/replay`, { method: 'POST' })
      if (res.ok) setReplayResult(await res.json())
    } catch (err) {
      console.error('Replay failed', err)
    } finally {
      setReplayLoading(false)
    }
  }

  const triggerDiff = async (paymentId: string) => {
    if (!diffFromTime || !diffToTime) return
    setDiffLoading(true)
    try {
      const from = encodeURIComponent(diffFromTime)
      const to = encodeURIComponent(diffToTime)
      const [resDiff, resExpl] = await Promise.all([
        fetch(`/api/v1/payments/${paymentId}/diff?from=${from}&to=${to}`),
        fetch(`/api/v1/payments/${paymentId}/diff/explanation?from=${from}&to=${to}`),
      ])
      if (resDiff.ok) setDiffResult(await resDiff.json())
      if (resExpl.ok) setDiffExplanation(await resExpl.json())
    } catch (err) {
      console.error('Diff failed', err)
    } finally {
      setDiffLoading(false)
    }
  }


  const tabs = [
    { key: 'overview' as DetailTab, label: 'Overview', icon: Receipt },
    { key: 'evidence' as DetailTab, label: 'Evidence', icon: Layers },
    { key: 'integrity' as DetailTab, label: 'Integrity & Replay', icon: ShieldCheck },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        icon={CreditCard}
        title="Payment Inspector"
        subtitle="Canonical record, evidence, and the verification trail for one payment"
        actions={
          <button onClick={fetchPayments} className="neo-btn flex items-center gap-1.5 text-xs">
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
        }
      />

      {/* ── Canonical payments — horizontal selector row ─────────────── */}
      <Panel title={`Canonical payments (${payments.length})`} icon={DollarSign} bodyClassName="p-3">
        {loading ? (
          <LoadingState label="Loading payments…" />
        ) : payments.length === 0 ? (
          <EmptyState
            icon={CreditCard}
            title="No payments captured yet"
            hint="Ingest a Razorpay Test Mode webhook and the canonical payment will appear here."
          />
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1">
            {payments.map((p) => {
              const active = selectedPayment?.razorpay_payment_id === p.razorpay_payment_id
              return (
                <button
                  key={p.razorpay_payment_id}
                  onClick={() => fetchPaymentDetails(p.razorpay_payment_id)}
                  className="shrink-0 rounded-xl p-4 text-left transition-all duration-300"
                  style={{
                    minWidth: 232,
                    background: active ? 'var(--color-accent-glow)' : 'var(--color-bg-surface)',
                    border: `1px solid ${active ? 'var(--color-border-accent)' : 'var(--color-border)'}`,
                  }}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                      {p.razorpay_payment_id}
                    </span>
                    {getStatusBadge(p.status)}
                  </div>
                  <div
                    className="text-lg font-bold tracking-tight"
                    style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-display)' }}
                  >
                    {formatCurrency(p.amount_minor, p.currency)}
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                    <Clock className="h-3 w-3" />
                    {format(new Date(p.first_observed_at), 'MMM d, HH:mm:ss')}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </Panel>

      {loadingDetails ? (
        <Panel><LoadingState label="Loading payment detail…" /></Panel>
      ) : !selectedPayment ? (
        <Panel>
          <EmptyState
            icon={Receipt}
            title="Select a payment"
            hint="Pick a payment above to inspect its canonical record, evidence graph, integrity assessment and decision replay."
          />
        </Panel>
      ) : (
        <>
          <SubTabs tabs={tabs} active={detailTab} onChange={setDetailTab} />

          {/* ══ OVERVIEW ═════════════════════════════════════════════ */}
          {detailTab === 'overview' && (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="glass-card p-5 lg:col-span-2">
              <div className="flex justify-between items-center pb-4 border-b border-white/5">
                <div>
                  <h3 className="text-2xl font-bold text-white mb-1">{formatCurrency(selectedPayment.amount_minor, selectedPayment.currency)}</h3>
                  <div className="font-mono text-sm text-slate-400">{selectedPayment.razorpay_payment_id}</div>
                </div>
                {getStatusBadge(selectedPayment.status)}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="neo-inset p-4 rounded-xl">
                  <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">Method</div>
                  <div className="text-sm text-slate-200 capitalize">
                    {selectedPayment.payment_method_type || 'Unknown'}
                  </div>
                  {selectedPayment.payment_method_details && (
                    <div className="mt-2 pt-2 border-t border-slate-800 text-xs text-slate-400 font-mono">
                      {Object.entries(selectedPayment.payment_method_details).map(([k, v]) => (
                        <div key={k} className="truncate">
                          <span className="text-slate-500">{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="neo-inset p-4 rounded-xl">
                  <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">Lifecycle</div>
                  <div className="text-xs text-slate-400 space-y-1">
                    <div><span className="text-slate-500">First Seen:</span> {format(new Date(selectedPayment.first_observed_at), 'MMM d, HH:mm:ss')}</div>
                    <div><span className="text-slate-500">Last Seen:</span> {format(new Date(selectedPayment.last_observed_at), 'MMM d, HH:mm:ss')}</div>
                    <div><span className="text-slate-500">Captured:</span> {selectedPayment.captured ? 'Yes' : 'No'}</div>
                  </div>
                </div>
              </div>
              </div>

              {/* Phase 19 — Operational Processing & Freshness Status */}
              {selectedOperationalStatus && (
                <div className="section-panel space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-indigo-400" />
                      <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">Processing & Freshness Status</span>
                    </div>
                    <span
                      className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full ${
                        selectedOperationalStatus.overall_freshness === 'CURRENT'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : selectedOperationalStatus.overall_freshness === 'STALE'
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                          : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                      }`}
                    >
                      {selectedOperationalStatus.overall_freshness}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{selectedOperationalStatus.summary}</p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800/80">
                    {Object.entries(selectedOperationalStatus.layers).map(([key, layer]) => (
                      <div key={key} className="bg-slate-950/40 p-2 rounded-lg border border-slate-800/50 flex flex-col justify-between">
                        <span className="text-[10px] text-slate-400 font-medium truncate">{layer.layer_name}</span>
                        <div className="flex items-center justify-between mt-1">
                          <span
                            className={`text-[9px] font-bold px-1.5 py-0.2 rounded ${
                              layer.status === 'CURRENT'
                                ? 'text-emerald-400'
                                : layer.status === 'STALE'
                                ? 'text-amber-400'
                                : 'text-slate-400'
                            }`}
                          >
                            {layer.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}


              {selectedTimeline && (
                <div className="glass-card p-5">
                  <div className="flex justify-between items-center mb-4">
                    <h4 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-indigo-400"></span>
                      Evidence Timeline
                    </h4>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                      {selectedTimeline.total_evidence_count} observations
                    </span>
                  </div>
                  <div className="space-y-4">
                    {selectedTimeline.timeline.map((entry, idx) => (
                      <div key={idx} className="neo-card p-4">
                        <div className="flex items-center justify-between mb-3 pb-3 border-b border-slate-800">
                          <div className="flex items-center gap-2">
                            <div className="font-mono text-sm text-indigo-400">{entry.event_type}</div>
                            <span className="text-[10px] uppercase tracking-wider bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">
                              {entry.source_type}
                            </span>
                          </div>
                          <div className="text-xs text-slate-500">
                            {entry.event_timestamp ? format(new Date(entry.event_timestamp), 'MMM d, yyyy HH:mm:ss.SSS') : 'Unknown'}
                          </div>
                        </div>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {entry.evidence.map(obs => (
                            <div key={obs.internal_id} className="flex flex-col p-2 bg-slate-800/60 rounded border border-slate-700/50">
                              <div className="text-[10px] text-slate-500 mb-1 font-mono">{obs.evidence_type}</div>
                              <div className="flex items-baseline gap-2">
                                <span className="text-sm font-medium text-slate-200">
                                  {obs.value_type === 'INTEGER_MINOR_UNITS' && obs.evidence_type.includes('AMOUNT') 
                                    ? formatCurrency(parseInt(obs.value || '0', 10), 'INR') // Simplify for display
                                    : obs.value}
                                </span>
                                <span className="text-[10px] text-slate-500">{obs.value_type}</span>
                              </div>
                            </div>
                          ))}
                          {(entry.evidence ?? []).length === 0 && (
                            <div className="text-xs text-slate-500 col-span-2 italic">No evidence extracted.</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}


              {selectedConsistency !== null && (
                <div className="glass-card p-5 lg:col-span-2">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h3 className="flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.08em]"
                        style={{ color: 'var(--color-text-primary)' }}>
                      <GitCompare className="h-4 w-4" style={{ color: 'var(--color-text-accent)' }} />
                      Temporal consistency
                    </h3>
                    <span className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                          style={{
                            color: selectedConsistency.is_consistent ? 'var(--color-success)' : 'var(--color-warning)',
                            background: selectedConsistency.is_consistent
                              ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
                              : 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
                          }}>
                      {selectedConsistency.is_consistent ? 'Consistent lifecycle' : 'Conflicts detected'}
                    </span>
                  </div>
            {/* Metrics row */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Total Observations', value: selectedConsistency.total_conflicts, accent: 'slate' },
                { label: 'Open Conflicts', value: selectedConsistency.open_conflicts, accent: selectedConsistency.open_conflicts > 0 ? 'amber' : 'green' },
                { label: 'Resolved', value: selectedConsistency.resolved_conflicts, accent: 'blue' },
              ].map(({ label, value, accent }) => (
                <div key={label} className={`bg-slate-900/60 rounded-lg p-3 border border-slate-700/50 text-center`}>
                  <div className={`text-xl font-mono font-bold text-${accent}-400`}>{value}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{label}</div>
                </div>
              ))}
            </div>

            {/* No conflicts message */}
            {selectedConsistency.total_conflicts === 0 && (
              <div className="flex items-center gap-3 p-4 rounded-lg bg-green-500/5 border border-green-500/20 text-green-400 text-sm">
                <CheckCircle className="w-4 h-4 shrink-0" />
                <div>
                  <div className="font-medium">No contradictions detected</div>
                  <div className="text-xs text-green-500/70 mt-0.5">All observations are temporally and semantically consistent.</div>
                </div>
              </div>
            )}

            {/* Conflict cards */}
            {selectedConsistency.conflicts.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs uppercase tracking-widest text-slate-500 font-medium">Conflict Observations</h4>
                {selectedConsistency.conflicts.map((conflict) => {
                  const severityStyles: Record<string, string> = {
                    HIGH: 'border-red-500/30 bg-red-500/5',
                    MEDIUM: 'border-amber-500/30 bg-amber-500/5',
                    LOW: 'border-yellow-500/30 bg-yellow-500/5',
                    INFO: 'border-blue-500/30 bg-blue-500/5',
                  }
                  const severityBadge: Record<string, string> = {
                    HIGH: 'bg-red-500/10 text-red-400 border-red-500/20',
                    MEDIUM: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                    LOW: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
                    INFO: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                  }
                  const statusBadge: Record<string, string> = {
                    OPEN: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                    RESOLVED: 'bg-green-500/10 text-green-400 border-green-500/20',
                    SUPERSEDED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
                    UNRESOLVED: 'bg-red-500/10 text-red-400 border-red-500/20',
                  }
                  const cardStyle = severityStyles[conflict.severity] || 'border-slate-700/50 bg-slate-900/40'
                  const badgeStyle = severityBadge[conflict.severity] || 'bg-slate-500/10 text-slate-400'
                  const statusStyle = statusBadge[conflict.status] || 'bg-slate-500/10 text-slate-400'

                  return (
                    <div key={conflict.internal_id} className={`rounded-lg border p-4 ${cardStyle}`}>
                      {/* Header row */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono font-medium border uppercase ${badgeStyle}`}>
                            {conflict.conflict_type.replace(/_/g, ' ')}
                          </span>
                          <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border ${statusStyle}`}>
                            {conflict.status}
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono">
                          Rule v{conflict.rule_version} · #{conflict.internal_id}
                        </div>
                      </div>

                      {/* Claims involved */}
                      <div className="flex items-center gap-2 mb-3 text-xs font-mono">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400">Claim #{conflict.claim_a_id}</span>
                        <span className="text-slate-600">↔</span>
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400">Claim #{conflict.claim_b_id}</span>
                      </div>

                      {/* Explanation */}
                      {conflict.explanation && (
                        <div className="space-y-2 text-xs">
                          {conflict.explanation.what && (
                            <div>
                              <span className="text-slate-500 uppercase text-[10px] tracking-wider">What</span>
                              <p className="text-slate-300 mt-0.5">{conflict.explanation.what}</p>
                            </div>
                          )}
                          {conflict.explanation.why && (
                            <div>
                              <span className="text-slate-500 uppercase text-[10px] tracking-wider">Why</span>
                              <p className="text-slate-300 mt-0.5">{conflict.explanation.why}</p>
                            </div>
                          )}
                          <div className="grid grid-cols-2 gap-2 mt-2">
                            {conflict.explanation.timestamp_a && (
                              <div className="bg-slate-900/60 rounded p-2 border border-slate-800">
                                <div className="text-[10px] text-slate-500 uppercase">Observation A</div>
                                <div className="font-mono text-slate-400 text-[10px] mt-0.5">{new Date(conflict.explanation.timestamp_a).toLocaleTimeString()}</div>
                                {conflict.explanation.sources_a?.length > 0 && (
                                  <div className="text-[10px] text-slate-500 mt-0.5">{conflict.explanation.sources_a.join(', ')}</div>
                                )}
                              </div>
                            )}
                            {conflict.explanation.timestamp_b && (
                              <div className="bg-slate-900/60 rounded p-2 border border-slate-800">
                                <div className="text-[10px] text-slate-500 uppercase">Observation B</div>
                                <div className="font-mono text-slate-400 text-[10px] mt-0.5">{new Date(conflict.explanation.timestamp_b).toLocaleTimeString()}</div>
                                {conflict.explanation.sources_b?.length > 0 && (
                                  <div className="text-[10px] text-slate-500 mt-0.5">{conflict.explanation.sources_b.join(', ')}</div>
                                )}
                              </div>
                            )}
                          </div>
                          {conflict.explanation.rule && (
                            <div className="mt-1 text-[10px] text-slate-600 font-mono">
                              rule: {conflict.explanation.rule}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Resolutions */}
                      {conflict.resolutions?.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-slate-700/50">
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Resolution</div>
                          {conflict.resolutions.map((r) => (
                            <div key={r.internal_id} className="text-xs text-green-400/80">
                              {r.resolution_type.replace(/_/g, ' ')}: {r.explanation}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

                </div>
              )}
            </div>
          )}

          {/* ══ EVIDENCE ═════════════════════════════════════════════ */}
          {detailTab === 'evidence' && (
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Phase 13 — Reconciled Evidence Facts Layer */}
              <div className="glass-card p-5 lg:col-span-2">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      Reconciled Evidence Facts
                    </h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Canonical real-world facts normalized across observations
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => selectedPayment && triggerReconciliation(selectedPayment.razorpay_payment_id)}
                      disabled={reconciliationLoading}
                      className="text-xs bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 px-2.5 py-1 rounded border border-emerald-500/30 disabled:opacity-50 transition-colors"
                    >
                      {reconciliationLoading ? 'Reconciling...' : 'Reconcile'}
                    </button>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                      {selectedFacts.length} facts
                    </span>
                  </div>
                </div>

                {selectedFacts.length === 0 ? (
                  <div className="p-4 rounded-lg border border-dashed border-slate-700 bg-slate-900/20 text-center text-xs text-slate-500">
                    No reconciled facts recorded yet. Click Reconcile to evaluate observations.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {selectedFacts.map((fact) => (
                      <div key={fact.internal_id} className="neo-card p-4 border-emerald-500/10">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                              FACT #{fact.internal_id}
                            </span>
                            <span className="font-mono text-xs font-semibold text-slate-200">
                              {fact.fact_type}
                            </span>
                          </div>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                            {fact.status}
                          </span>
                        </div>

                        <div className="flex items-baseline gap-2 mb-2">
                          <span className="text-xs text-slate-400">Canonical Value:</span>
                          <span className="text-sm font-mono font-medium text-emerald-300">
                            {fact.canonical_value}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400">
                          <div>
                            <span className="text-slate-500">Observations:</span>{' '}
                            <span className="font-semibold text-slate-200">{fact.observation_count}</span>
                          </div>
                          <div>
                            <span className="text-slate-500">Distinct Sources:</span>{' '}
                            <span className="font-semibold text-slate-200">{fact.distinct_source_count}</span>
                          </div>
                          <div>
                            <span className="text-slate-500">First Seen:</span>{' '}
                            <span>{fact.first_observed_at ? format(new Date(fact.first_observed_at), 'HH:mm:ss') : '—'}</span>
                          </div>
                          <div>
                            <span className="text-slate-500">Last Seen:</span>{' '}
                            <span>{fact.last_observed_at ? format(new Date(fact.last_observed_at), 'HH:mm:ss') : '—'}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {selectedQuality && selectedQuality.evidence_quality.length > 0 && (
                <div className="glass-card p-5">
                  <div className="flex justify-between items-center mb-4">
                    <h4 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-pink-400"></span>
                      Evidence Quality
                    </h4>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                      {selectedQuality.snapshot_count} snapshots · {selectedQuality.total_evidence_count} evidence
                    </span>
                  </div>

                  <div className="space-y-4">
                    {selectedQuality.evidence_quality.map((item) => (
                      <div key={item.evidence_id} className="neo-card p-4">
                        <div className="flex justify-between items-center mb-2">
                          <div className="font-mono text-xs text-slate-400">
                            Evidence ID: {item.evidence_id} <span className="text-slate-500">· {item.evidence_type}</span>
                          </div>
                          {item.latest_snapshot && (
                            <div className="text-[10px] text-slate-500 font-mono">
                              v{item.latest_snapshot.freshness_methodology_version} · {item.snapshot_count} snapshots
                            </div>
                          )}
                        </div>

                        {!item.latest_snapshot ? (
                          <div className="text-xs text-slate-500 italic">No quality snapshot recorded yet.</div>
                        ) : (
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex flex-col p-2 rounded border overflow-hidden" style={{ background: 'var(--color-bg-surface)', borderColor: 'var(--color-border)' }}>
                              <span className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-tertiary)' }}>Freshness</span>
                              <span className="text-xs font-semibold truncate" style={{ color: item.latest_snapshot.freshness_state === 'CURRENT' ? 'var(--color-success)' : item.latest_snapshot.freshness_state === 'STALE' ? 'var(--color-danger)' : 'var(--color-warning)' }}>
                                {item.latest_snapshot.freshness_state}
                              </span>
                            </div>
                            <div className="flex flex-col p-2 rounded border overflow-hidden" style={{ background: 'var(--color-bg-surface)', borderColor: 'var(--color-border)' }}>
                              <span className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-tertiary)' }}>Authority</span>
                              <span className="text-xs font-semibold truncate" style={{ color: item.latest_snapshot.source_authority_level === 'PRIMARY' ? 'var(--color-info)' : 'var(--color-text-secondary)' }}>
                                {item.latest_snapshot.source_authority_level}
                              </span>
                            </div>
                            <div className="flex flex-col p-2 rounded border overflow-hidden" style={{ background: 'var(--color-bg-surface)', borderColor: 'var(--color-border)' }}>
                              <span className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-tertiary)' }}>Directness</span>
                              <span className="text-xs font-semibold truncate" style={{ color: item.latest_snapshot.source_directness === 'DIRECT' ? 'var(--color-success)' : 'var(--color-accent-primary)' }}>
                                {item.latest_snapshot.source_directness}
                              </span>
                            </div>
                            <div className="flex flex-col p-2 rounded border overflow-hidden" style={{ background: 'var(--color-bg-surface)', borderColor: 'var(--color-border)' }}>
                              <span className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-tertiary)' }}>Reliability</span>
                              <span className="text-xs font-semibold truncate" style={{ color: item.latest_snapshot.historical_reliability_status === 'VERIFIED' ? 'var(--color-success)' : item.latest_snapshot.historical_reliability_status === 'CONTRADICTED' ? 'var(--color-danger)' : 'var(--color-text-secondary)' }}>
                                {item.latest_snapshot.historical_reliability_status?.replace(/_/g, ' ') || 'Unknown'}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedGraph && selectedGraph.edge_count > 0 && (
                <div className="glass-card p-5">
                  <div className="flex justify-between items-center mb-4">
                    <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <Link2 className="w-4 h-4 text-indigo-400" /> Evidence Relationships
                    </h4>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                      {selectedGraph.edge_count} edges
                    </span>
                  </div>
                  
                  <div className="space-y-2">
                    {/* Group edges by type for easier reading */}
                    {Array.from(new Set(selectedGraph.edges.map(e => e.relationship_type))).sort().map(edgeType => {
                      const edgesOfType = selectedGraph.edges.filter(e => e.relationship_type === edgeType)
                      
                      // Style badges differently based on type
                      let badgeStyle = "bg-slate-700/50 text-slate-300 border-slate-600"
                      if (edgeType === 'INDEPENDENCE_CANDIDATE') badgeStyle = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      if (edgeType === 'SAME_SOURCE') badgeStyle = "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      if (edgeType === 'DERIVED_FROM') badgeStyle = "bg-blue-500/10 text-blue-400 border-blue-500/20"
                      
                      return (
                        <div key={edgeType} className="mb-4">
                          <div className="mb-2">
                            <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border uppercase tracking-wider ${badgeStyle}`}>
                              {edgeType}
                            </span>
                          </div>
                          <div className="space-y-1">
                            {edgesOfType.map(edge => {
                              const sourceNode = selectedGraph.nodes.find(n => n.evidence_id === edge.source_evidence_id)
                              const targetNode = selectedGraph.nodes.find(n => n.evidence_id === edge.target_evidence_id)
                              
                              return (
                                <div key={edge.edge_id} className="text-xs flex items-center gap-2 bg-slate-900/40 p-2 rounded border border-slate-800">
                                  <div className="truncate flex-1 font-mono text-slate-400">
                                    [#{sourceNode?.evidence_id}] {sourceNode?.evidence_type}
                                  </div>
                                  <div className="text-slate-600">→</div>
                                  <div className="truncate flex-1 font-mono text-slate-400">
                                    [#{targetNode?.evidence_id}] {targetNode?.evidence_type}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}


              {selectedStructure && selectedStructure.snapshot && (
                <div className="glass-card p-5 lg:col-span-2">
                  <div className="flex justify-between items-center mb-4">
                    <h4 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                      Evidence Structure & Concentration
                    </h4>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700 font-mono">
                      v{selectedStructure.snapshot.methodology_version}
                    </span>
                  </div>

                  {/* Concentration Metrics Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-6">
                    <div className="metric-card flex flex-col">
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider">Observations</span>
                      <span className="text-lg font-bold text-slate-200 mt-1">
                        {selectedStructure.snapshot.total_observations}
                      </span>
                      <span className="text-[10px] text-slate-500">across {selectedStructure.snapshot.distinct_sources} sources</span>
                    </div>

                    <div className="metric-card flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Canonical Claims</span>
                      <span className="text-lg font-bold text-cyan-400 mt-1">
                        {selectedStructure.snapshot.distinct_claims}
                      </span>
                      <span className="text-[10px] text-slate-500">{selectedStructure.snapshot.corroborated_claim_count} corroborated</span>
                    </div>

                    <div className="metric-card flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Provider Events</span>
                      <span className="text-lg font-bold text-indigo-400 mt-1">
                        {selectedStructure.snapshot.distinct_events}
                      </span>
                      <span className="text-[10px] text-slate-500">largest: {selectedStructure.snapshot.largest_group_size} obs</span>
                    </div>

                    <div className="metric-card flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Concentration (HHI)</span>
                      <span className="text-lg font-bold text-amber-400 mt-1 font-mono">
                        {selectedStructure.snapshot.group_hhi.toFixed(2)}
                      </span>
                      <span className="text-[10px] text-slate-500">Herfindahl Index</span>
                    </div>
                  </div>

                  {/* Canonical Claims List */}
                  <div className="mb-6">
                    <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Canonical Claims & Corroboration</h5>
                    <div className="space-y-2">
                      {selectedStructure.claims.map((claim) => {
                        const corrob = selectedStructure.corroborations.find(c => c.claim_id === claim.internal_id)
                        return (
                          <div key={claim.internal_id} className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                            <div>
                              <div className="text-[10px] text-slate-500 font-mono uppercase">{claim.claim_type} ({claim.claim_key})</div>
                              <div className="text-sm font-medium text-slate-200 font-mono mt-0.5">{claim.canonical_value}</div>
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                                {claim.supporting_evidence_count} obs
                              </span>
                              {corrob && (
                                <>
                                  <span className={`text-[10px] px-2 py-0.5 rounded border font-mono ${
                                    corrob.corroboration_type === 'MULTI_SOURCE_CORROBORATION' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                    corrob.corroboration_type === 'TEMPORAL_CORROBORATION' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                    corrob.corroboration_type === 'SAME_SOURCE_CORROBORATION' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                    'bg-slate-800 text-slate-400 border-slate-700'
                                  }`}>
                                    {corrob.corroboration_type}
                                  </span>
                                  <span className={`text-[10px] px-2 py-0.5 rounded border font-mono ${
                                    corrob.independence_status === 'INDEPENDENT_CANDIDATE' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                    corrob.independence_status === 'DEPENDENT' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                    corrob.independence_status === 'SAME_SOURCE' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                    'bg-slate-800 text-slate-400 border-slate-700'
                                  }`}>
                                    {corrob.independence_status}
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* Evidence Groups */}
                  <div>
                    <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Evidence Origin Groups</h5>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {selectedStructure.groups.map((group) => (
                        <div key={group.internal_id} className="p-2.5 rounded-lg bg-slate-900/30 border border-slate-800 flex justify-between items-center">
                          <div className="truncate mr-2">
                            <span className="text-[10px] text-slate-500 uppercase font-mono block">{group.group_type}</span>
                            <span className="text-xs text-slate-300 font-mono truncate block">{group.grouping_key}</span>
                          </div>
                          <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-1 rounded font-mono border border-slate-700 whitespace-nowrap">
                            {group.member_count} members
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}




            {/* ── Phase 15 — Evidence Completeness & Coverage Analysis ────── */}
            {selectedCoverage && (
              <div className="glass-card p-5 lg:col-span-2">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                      Evidence Coverage & Completeness
                    </h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Deterministic evaluation of expected vs observed lifecycle evidence
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-semibold uppercase tracking-wider border ${
                      selectedCoverage.overall_coverage_status === 'COMPLETE'
                        ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                        : selectedCoverage.overall_coverage_status === 'SUBSTANTIALLY_COMPLETE'
                        ? 'bg-teal-500/15 text-teal-400 border-teal-500/30'
                        : selectedCoverage.overall_coverage_status === 'PARTIAL'
                        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                        : selectedCoverage.overall_coverage_status === 'INSUFFICIENT'
                        ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                        : 'bg-slate-700/40 text-slate-400 border-slate-600/30'
                    }`}>
                      {selectedCoverage.overall_coverage_status.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                      {selectedCoverage.profile_id} (v{selectedCoverage.profile_version})
                    </span>
                  </div>
                </div>

                {/* Metrics Bar */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
                    <div className="text-[10px] text-slate-500 uppercase">Applicable</div>
                    <div className="text-sm font-bold text-slate-200">{selectedCoverage.metrics.total_applicable}</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
                    <div className="text-[10px] text-slate-500 uppercase">Required Present</div>
                    <div className="text-sm font-bold text-emerald-400">{selectedCoverage.metrics.required_present}</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
                    <div className="text-[10px] text-slate-500 uppercase">Required Missing</div>
                    <div className={`text-sm font-bold ${selectedCoverage.metrics.required_missing > 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                      {selectedCoverage.metrics.required_missing}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center">
                    <div className="text-[10px] text-slate-500 uppercase">Conflicted</div>
                    <div className={`text-sm font-bold ${selectedCoverage.metrics.conflicted > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
                      {selectedCoverage.metrics.conflicted}
                    </div>
                  </div>
                </div>

                {/* Explanation Banner */}
                <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 mb-4 text-xs text-slate-300">
                  <span className="font-semibold text-blue-400">Coverage Summary: </span>
                  {selectedCoverage.explanation}
                </div>

                {/* Requirement Matrix Table */}
                <div className="mb-4 overflow-x-auto">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Requirement Matrix</div>
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-[10px] text-slate-500 uppercase">
                        <th className="py-2 px-2">Evidence Requirement</th>
                        <th className="py-2 px-2">Priority</th>
                        <th className="py-2 px-2">Observed State</th>
                        <th className="py-2 px-2">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {selectedCoverage.results.map((r) => (
                        <tr key={r.requirement_id} className="hover:bg-slate-900/30">
                          <td className="py-2 px-2">
                            <div className="font-medium text-slate-200">{r.requirement_id.replace('REQ_', '')}</div>
                            <div className="text-[10px] text-slate-500 font-mono">{r.fact_type}</div>
                          </td>
                          <td className="py-2 px-2">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                              r.requirement_type === 'REQUIRED' ? 'bg-indigo-500/20 text-indigo-300' :
                              r.requirement_type === 'EXPECTED' ? 'bg-blue-500/20 text-blue-300' :
                              r.requirement_type === 'OPTIONAL' ? 'bg-slate-700/40 text-slate-400' :
                              'bg-slate-800 text-slate-500'
                            }`}>
                              {r.requirement_type}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-[11px] text-slate-300">
                            {r.observed_state === 'PRESENT' && r.matched_fact_id ? (
                              <span className="text-emerald-400 font-mono">Fact #{r.matched_fact_id}</span>
                            ) : r.observed_state === 'PARTIAL' ? (
                              <span className="text-amber-400">Partial Observations</span>
                            ) : r.observed_state === 'CONFLICTED' ? (
                              <span className="text-rose-400">Conflicted Claims</span>
                            ) : (
                              <span className="text-slate-500">Not Observed</span>
                            )}
                          </td>
                          <td className="py-2 px-2">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                              r.observed_state === 'PRESENT' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/40' :
                              r.observed_state === 'PARTIAL' ? 'bg-amber-950 text-amber-400 border border-amber-800/40' :
                              r.observed_state === 'CONFLICTED' ? 'bg-rose-950 text-rose-400 border border-rose-800/40' :
                              r.observed_state === 'NOT_APPLICABLE' ? 'bg-slate-800 text-slate-500' :
                              'bg-slate-800/80 text-slate-400 border border-slate-700'
                            }`}>
                              {r.observed_state}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Evidence Not Observed Section */}
                {selectedCoverage.missing_evidence.length > 0 && (
                  <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Evidence Not Observed ({selectedCoverage.missing_evidence.length})
                    </div>
                    <div className="space-y-2">
                      {selectedCoverage.missing_evidence.map((m) => (
                        <div key={m.requirement_id} className="p-2.5 rounded bg-slate-900/80 border border-slate-800 text-xs">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-slate-300 font-semibold">{m.requirement_id}</span>
                            <span className="text-[10px] text-slate-500 font-mono">{m.requirement_type}</span>
                          </div>
                          <div className="text-[11px] text-slate-400 mb-1">{m.explanation}</div>
                          <div className="text-[10px] text-slate-500 font-mono">Scope: {m.search_scope}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}


            {/* ── Phase 14 — End-to-End Evidence Lineage & Causal Chain ───── */}
            {selectedLineage && (
              <div className="glass-card p-5 lg:col-span-2">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                      Evidence Lineage & Causal Graph
                    </h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Deterministic audit trail connecting provider events to integrity results
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-semibold uppercase tracking-wider border ${
                      selectedLineage.completeness === 'COMPLETE'
                        ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                        : selectedLineage.completeness === 'PARTIAL'
                        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                        : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                    }`}>
                      {selectedLineage.completeness}
                    </span>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                      {selectedLineage.evaluation_context.node_count} nodes · {selectedLineage.evaluation_context.edge_count} edges
                    </span>
                  </div>
                </div>

                {/* Causal Explanation Summary */}
                <div className="p-3.5 rounded-lg bg-cyan-950/20 border border-cyan-500/20 mb-4">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 mb-1">
                    Causal Reasoning
                  </div>
                  <div className="text-xs text-slate-200 leading-relaxed mb-2 font-mono">
                    {selectedLineage.explanation.summary}
                  </div>
                  <div className="space-y-1 border-t border-cyan-900/40 pt-2">
                    {selectedLineage.explanation.detail_lines.map((line, idx) => (
                      <div key={idx} className="text-[11px] text-slate-400 flex items-start gap-1.5">
                        <span className="text-cyan-400/80">▸</span>
                        <span>{line}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Lineage Gaps (if any) */}
                {selectedLineage.gaps.length > 0 && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-950/20 border border-amber-500/25">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 mb-2 flex items-center gap-1.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Lineage Gaps Detected ({selectedLineage.evaluation_context.gap_count})</span>
                    </div>
                    <div className="space-y-2">
                      {selectedLineage.gaps.map((gap, idx) => (
                        <div key={`${gap.location}:${gap.expected_edge_type}:${idx}`} className="p-2 rounded bg-slate-900/60 border border-amber-900/30 text-xs">
                          <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono mb-1">
                            <span>Location: {gap.location}</span>
                          </div>
                          <div className="text-slate-300 text-[11px]">{gap.reason}</div>
                          <div className="text-[10px] text-slate-500 mt-1 font-mono">
                            Expected: {gap.expected_edge_type}
                            {gap.detected_at && <> · Detected: {format(new Date(gap.detected_at), 'MMM d, yyyy HH:mm')}</>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Lineage Traversal Nodes */}
                <div className="space-y-2 mb-4">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Traversed Entities</div>
                  <div className="grid grid-cols-1 gap-2 max-h-60 overflow-y-auto pr-1">
                    {selectedLineage.nodes.map((node) => (
                      <div key={node.node_id} className="p-2.5 rounded-lg bg-slate-900/40 border border-slate-800 flex items-start justify-between">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                              node.node_type === 'WEBHOOK_EVENT' ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' :
                              node.node_type === 'OBSERVATION' ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30' :
                              node.node_type === 'FACT' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                              node.node_type === 'CLAIM' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' :
                              node.node_type === 'INTEGRITY_SNAPSHOT' ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' :
                              node.node_type === 'INTEGRITY_TRACE' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' :
                              'bg-slate-700/40 text-slate-300'
                            }`}>
                              {node.node_type}
                            </span>
                            <span className="text-xs font-semibold text-slate-200">{node.label}</span>
                          </div>
                          <div className="text-[10px] font-mono text-slate-500">ID: {node.entity_id}</div>
                        </div>
                        {node.timestamp && (
                          <div className="text-[10px] text-slate-500 font-mono">
                            {format(new Date(node.timestamp), 'HH:mm:ss')}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Lineage Edges (Authoritative Links) */}
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Authoritative & Derived Links ({selectedLineage.evaluation_context.edge_count})</div>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {selectedLineage.edges.map((edge) => (
                      <div key={`${edge.source_node_id}->${edge.edge_type}->${edge.target_node_id}`} className="p-2 rounded bg-slate-900/30 border border-slate-800 text-xs">
                        <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                          <span className="text-slate-400">{edge.source_node_id} ➔ {edge.target_node_id}</span>
                          <span className={`px-1 rounded ${
                            edge.linkage_type === 'FOREIGN_KEY'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/40'
                              : 'bg-indigo-950 text-indigo-400 border border-indigo-800/40'
                          }`}>
                            {edge.linkage_type}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-300">{edge.explanation}</div>
                        <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-500 font-mono">
                          <span>Role: {edge.causal_role}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            </div>
          )}

          {/* ══ INTEGRITY & REPLAY ═══════════════════════════════════ */}
          {detailTab === 'integrity' && (
            <div className="grid gap-6 lg:grid-cols-2">
            {/* ── Phase 9 — Evidence Integrity Panel ─────────────────────── */}
            {selectedIntegrity && (
              <div className="glass-card p-5">
                <div className="flex justify-between items-center mb-4">
                  <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Evidence Integrity</h4>
                  <span className="text-[10px] bg-violet-500/10 text-violet-400 px-2 py-1 rounded-full border border-violet-500/20 font-mono">
                    {selectedIntegrity.methodology_version}
                  </span>
                </div>

                {/* Overall status banner */}
                <div className={`mb-4 p-4 rounded-lg border flex items-center justify-between ${
                  selectedIntegrity.overall_status === 'VERY_STRONG' ? 'bg-emerald-500/10 border-emerald-500/30' :
                  selectedIntegrity.overall_status === 'STRONG'      ? 'bg-green-500/10 border-green-500/30' :
                  selectedIntegrity.overall_status === 'LIMITED'     ? 'bg-yellow-500/10 border-yellow-500/30' :
                  selectedIntegrity.overall_status === 'WEAK'        ? 'bg-orange-500/10 border-orange-500/30' :
                  selectedIntegrity.overall_status === 'UNRESOLVED'  ? 'bg-red-500/10 border-red-500/30' :
                  'bg-slate-700/30 border-slate-600/30'
                }`}>
                  <span className={`text-lg font-bold tracking-wide ${
                    selectedIntegrity.overall_status === 'VERY_STRONG' ? 'text-emerald-400' :
                    selectedIntegrity.overall_status === 'STRONG'      ? 'text-green-400' :
                    selectedIntegrity.overall_status === 'LIMITED'     ? 'text-yellow-400' :
                    selectedIntegrity.overall_status === 'WEAK'        ? 'text-orange-400' :
                    selectedIntegrity.overall_status === 'UNRESOLVED'  ? 'text-red-400' :
                    'text-slate-400'
                  }`}>
                    {selectedIntegrity.overall_status.replace(/_/g, ' ')}
                  </span>
                  <div className="text-right text-xs text-slate-400 space-y-0.5">
                    <div>{selectedIntegrity.evidence_count} observation{selectedIntegrity.evidence_count !== 1 ? 's' : ''}</div>
                    <div>{selectedIntegrity.source_count} source{selectedIntegrity.source_count !== 1 ? 's' : ''}</div>
                    {selectedIntegrity.open_conflict_count > 0 && (
                      <div className="text-red-400">{selectedIntegrity.open_conflict_count} open conflict{selectedIntegrity.open_conflict_count !== 1 ? 's' : ''}</div>
                    )}
                  </div>
                </div>

                {/* Dimensions table */}
                <div className="space-y-2 mb-4">
                  {([
                    ['Freshness',      selectedIntegrity.freshness_result],
                    ['Source',         selectedIntegrity.source_result],
                    ['Independence',   selectedIntegrity.independence_result],
                    ['Corroboration',  selectedIntegrity.corroboration_result],
                    ['Consistency',    selectedIntegrity.consistency_result],
                  ] as [string, DimensionResult | null][]).map(([label, dim]) => (
                    <div key={label} className="flex items-start gap-3 p-3 rounded-lg bg-slate-900/40 border border-slate-700/50">
                      <div className="w-28 shrink-0 text-xs text-slate-400 font-medium pt-0.5">{label}</div>
                      {dim ? (
                        <div className="flex-1">
                          <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded mb-1 ${
                            ['STRONG','STRONGLY_CORROBORATED','NO_DETECTED_CONFLICT','HIGH_SOURCE_DIVERSITY','CURRENT'].some(s => dim.status.includes(s))
                              ? 'bg-green-500/15 text-green-400 border border-green-500/20'
                              : ['WEAK','HAS_OPEN_CONFLICTS','TERTIARY','UNRESOLVABLE'].some(s => dim.status.includes(s))
                              ? 'bg-red-500/15 text-red-400 border border-red-500/20'
                              : ['LIMITED','SINGLE_SOURCE','STALE','ORDERING_AMBIGUITY','PARTIAL'].some(s => dim.status.includes(s))
                              ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/20'
                              : 'bg-slate-700/40 text-slate-400 border border-slate-600/30'
                          }`}>
                            {dim.status.replace(/_/g, ' ')}
                          </span>
                          <div className="text-[11px] text-slate-500">{dim.reason}</div>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* Why section */}
                {selectedIntegrity.explanation_lines.length > 0 && (
                  <div className="mb-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Why this assessment</div>
                    <div className="space-y-1">
                      {selectedIntegrity.explanation_lines.map((line, i) => {
                        const isWarning = line.toLowerCase().includes('single') ||
                          line.toLowerCase().includes('limited') ||
                          line.toLowerCase().includes('only one') ||
                          line.toLowerCase().includes('conflict')
                        return (
                          <div key={i} className={`flex items-start gap-2 text-xs ${
                            isWarning ? 'text-yellow-400/80' : 'text-slate-300'
                          }`}>
                            {isWarning
                              ? <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                              : <CheckCircle className="w-3 h-3 mt-0.5 shrink-0" />}
                            <span>{line}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Limitations */}
                {selectedIntegrity.limitations.length > 0 && (
                  <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-700/40">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Limitations</div>
                    <div className="space-y-1">
                      {selectedIntegrity.limitations.map((lim, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-slate-500">
                          <span className="shrink-0 mt-0.5">•</span>
                          <span>{lim}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-3 text-[10px] text-slate-600">
                  Evaluated at {format(new Date(selectedIntegrity.evaluated_at), 'MMM d, HH:mm:ss')} UTC
                </div>
              </div>
            )}


            {/* ── Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries ───── */}
            {selectedReliability && (
              <div className="glass-card p-5">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-violet-400"></span>
                      Evidence Reliability & Uncertainty Calibration
                    </h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Categorical reliability rating · Methodology: {selectedReliability.methodology_version}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2.5 py-1 rounded-md font-bold uppercase tracking-wider border shadow-sm ${
                      selectedReliability.overall_state === 'HIGH'
                        ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                        : selectedReliability.overall_state === 'MODERATE'
                        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                        : selectedReliability.overall_state === 'LIMITED'
                        ? 'bg-orange-500/15 text-orange-400 border-orange-500/30'
                        : selectedReliability.overall_state === 'UNRELIABLE'
                        ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                        : 'bg-slate-700/30 text-slate-400 border-slate-600/30'
                    }`}>
                      {selectedReliability.overall_state} RELIABILITY
                    </span>
                    <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded border border-slate-700 font-mono">
                      {selectedReliability.facts_assessed} Facts Assessed
                    </span>
                  </div>
                </div>

                {/* Explanation Summary */}
                <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 mb-4">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                    Reliability Assessment Synthesis
                  </div>
                  <div className="text-xs text-slate-300 leading-relaxed font-sans">
                    {selectedReliability.explanation}
                  </div>
                  {selectedReliability.coverage_summary && (
                    <div className="mt-2 pt-2 border-t border-slate-800 text-[11px] text-slate-400">
                      <span className="text-slate-500">Coverage: </span>{selectedReliability.coverage_summary}
                    </div>
                  )}
                  {selectedReliability.conflicts_summary && (
                    <div className="mt-1 text-[11px] text-slate-400">
                      <span className="text-slate-500">Conflicts: </span>{selectedReliability.conflicts_summary}
                    </div>
                  )}
                </div>

                {/* Fact Assessments */}
                {(selectedReliability.fact_assessments ?? []).length > 0 && (
                  <div className="mb-4">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                      Fact Reliability Assessments ({selectedReliability.fact_assessments.length})
                    </div>
                    <div className="space-y-2">
                      {selectedReliability.fact_assessments.map((fa, i) => (
                        <div key={i} className="p-3 rounded-lg bg-slate-900/50 border border-slate-800 text-xs">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-slate-300">Fact #{fa.fact_id} · {fa.fact_type}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold uppercase ${
                              fa.overall_state === 'HIGH' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : fa.overall_state === 'MODERATE' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            }`}>
                              {fa.overall_state}
                            </span>
                          </div>
                          <div className="text-slate-400 font-mono mb-1">{fa.canonical_value}</div>
                          {fa.explanation && <div className="text-[11px] text-slate-500">{fa.explanation}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Uncertainty Boundaries */}
                {(selectedReliability.uncertainty_summary ?? []).length > 0 && (
                  <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center justify-between">
                      <span>Uncertainty Boundaries ({selectedReliability.uncertainty_summary.length})</span>
                      <span className="text-[10px] text-slate-500 font-normal">Defensive Epistemic Boundaries</span>
                    </div>
                    <div className="space-y-2">
                      {selectedReliability.uncertainty_summary.map((item, idx) => (
                        <div key={idx} className="p-2.5 rounded bg-slate-900/80 border border-slate-800 text-xs flex items-start gap-2.5">
                          <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded uppercase mt-0.5 ${
                            item.boundary_type === 'ESTABLISHED'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : item.boundary_type === 'SUPPORTED'
                              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                              : item.boundary_type === 'UNCERTAIN'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : item.boundary_type === 'CONTRADICTED'
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              : 'bg-slate-700/40 text-slate-400 border border-slate-600/30'
                          }`}>
                            {item.boundary_type}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-slate-200 font-semibold text-xs">{item.topic}</span>
                              <span className="text-[10px] text-slate-500 font-mono">Scope: {item.scope}</span>
                            </div>
                            <div className="text-[11px] text-slate-400 leading-relaxed">{item.statement}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

              {/* Evidence Evolution — Phase 11 */}
              <div className="glass-card p-5 lg:col-span-2">
                <div className="flex justify-between items-center mb-4">
                  <h4 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <Clock className="w-4 h-4 text-purple-400" /> Evidence Evolution
                  </h4>                    <button
                      onClick={() => recomputeEvolution(selectedPayment.razorpay_payment_id)}
                      disabled={recomputeLoading}
                      className="neo-btn text-xs text-purple-300 px-3 py-1.5 disabled:opacity-50 transition-all duration-200"
                  >
                    {recomputeLoading ? 'Recomputing...' : 'Recompute Now'}
                  </button>
                </div>

                {/* Dimension filter bar */}
                <div className="flex flex-wrap gap-1 mb-4">
                  {['ALL', 'EVIDENCE', 'CORROBORATION', 'INDEPENDENCE', 'FRESHNESS', 'CONSISTENCY', 'INTEGRITY', 'METHODOLOGY'].map(dim => (
                    <button
                      key={dim}
                      onClick={() => setDimensionFilter(dim)}
                      className={`text-[10px] px-2 py-1 rounded border transition-colors ${
                        dimensionFilter === dim
                          ? 'bg-purple-500/20 text-purple-300 border-purple-500/30'
                          : 'bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600'
                      }`}
                    >
                      {dim}
                    </button>
                  ))}
                </div>

                {stateHistory.length === 0 ? (
                  <div className="text-center py-8 text-slate-500 text-sm">
                    No material evidence-state change detected.
                  </div>
                ) : (
                  <div className="relative">
                    {/* Vertical timeline */}
                    <div className="absolute left-3 top-0 bottom-0 w-px bg-slate-700" />
                    <div className="space-y-0">
                      {stateHistory.map((snap) => {
                        const snapChanges = evolutionChanges.filter(c => {
                          const matchesPair = c.current_snapshot_id === snap.snapshot_id
                          const matchesDim = dimensionFilter === 'ALL' || c.dimension === dimensionFilter
                          return matchesPair && matchesDim
                        })

                        const integrityColor =
                          snap.overall_integrity_status === 'VERY_STRONG' ? 'text-emerald-400' :
                          snap.overall_integrity_status === 'STRONG' ? 'text-green-400' :
                          snap.overall_integrity_status === 'LIMITED' ? 'text-amber-400' :
                          snap.overall_integrity_status === 'WEAK' ? 'text-orange-400' :
                          snap.overall_integrity_status === 'UNRESOLVED' ? 'text-red-400' :
                          'text-slate-400'

                        return (
                          <div key={snap.snapshot_id} className="pl-8 pb-4">
                            {/* Timeline node */}
                            <div className="absolute left-1 w-5 h-5 rounded-full bg-slate-800 border-2 border-purple-500/60 flex items-center justify-center" style={{ marginTop: '2px' }}>
                              <div className="w-2 h-2 rounded-full bg-purple-500" />
                            </div>

                            {/* Snapshot card */}
                            <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs text-slate-400 font-mono">
                                  {format(new Date(snap.evaluation_time), 'MMM d, HH:mm:ss')}
                                </span>
                                <span className={`text-xs font-semibold ${integrityColor}`}>
                                  {snap.overall_integrity_status}
                                </span>
                              </div>
                              <div className="flex gap-3 text-[10px] text-slate-500">
                                <span>{snap.evidence_count} evidence</span>
                                <span>{snap.conflict_count} conflicts</span>
                                <span>v{snap.methodology_version}</span>
                              </div>
                            </div>

                            {/* Change cards between previous and this snapshot */}
                            {snapChanges.length > 0 && (
                              <div className="mt-2 space-y-2">
                                {snapChanges.map(change => (
                                  <div key={change.change_id} className="ml-2 p-3 rounded-lg bg-purple-500/5 border border-purple-500/20">
                                    <div className="flex items-start justify-between mb-1">
                                      <div>
                                        <span className="text-[10px] font-semibold text-purple-300 uppercase tracking-wider">
                                          {change.change_type.replace(/_/g, ' ')}
                                        </span>
                                        <span className="ml-2 text-[10px] text-slate-500">{change.dimension}</span>
                                      </div>
                                      <span className="text-[10px] text-slate-500 font-mono">
                                        {format(new Date(change.detected_at), 'HH:mm:ss')}
                                      </span>
                                    </div>

                                    {change.explanation && (
                                      <p className="text-[11px] text-slate-300 mb-1">{change.explanation}</p>
                                    )}

                                    <div className="flex items-center gap-2 flex-wrap">
                                      {change.previous_value && change.current_value && (
                                        <span className="text-[10px] font-mono">
                                          <span className="text-slate-500">{change.previous_value}</span>
                                          <span className="text-slate-600 mx-1">→</span>
                                          <span className="text-slate-200">{change.current_value}</span>
                                        </span>
                                      )}
                                      {change.direct_cause && (
                                        <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700">
                                          {change.direct_cause.replace(/_/g, ' ')}
                                        </span>
                                      )}
                                      {change.magnitude && (
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                          change.magnitude === 'MAJOR' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                          change.magnitude === 'MODERATE' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                          'bg-slate-800 text-slate-400 border-slate-700'
                                        }`}>
                                          {change.magnitude}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

      {/* Phase 18 — Decision Replay & Differential Analysis */}
      {selectedPayment && (
        <div className="col-span-1 lg:col-span-2 glass-card overflow-hidden animate-slide-up">
          <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
            <h3
              className="flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.08em]"
              style={{ color: 'var(--color-text-primary)' }}
            >
              <GitCompare className="h-4 w-4" style={{ color: 'var(--color-text-accent)' }} />
              Decision replay &amp; differential analysis
            </h3>
            <div className="flex gap-2">
              <button
                onClick={() => setReplayTab('replay')}
                className={`text-xs px-3 py-1.5 rounded-lg transition-all duration-200 ${
                  replayTab === 'replay'
                    ? 'neo-btn-indigo'
                    : 'neo-btn text-slate-400'
                }`}
              >
                Replay
              </button>
              <button
                onClick={() => setReplayTab('diff')}
                className={`text-xs px-3 py-1.5 rounded-lg transition-all duration-200 ${
                  replayTab === 'diff'
                    ? 'neo-btn-indigo'
                    : 'neo-btn text-slate-400'
                }`}
              >
                Compare States
              </button>
            </div>
          </div>

          <div className="p-5">
            {replayTab === 'replay' ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-400 max-w-xl">
                    Reconstruct the exact integrity decision that would have been made for this payment using
                    pinned methodology <span className="font-mono text-violet-400">EDR-1.0</span>. A canonical
                    input fingerprint and result fingerprint are produced for auditability.
                  </p>
                  <button
                    onClick={() => triggerReplay(selectedPayment.razorpay_payment_id)}
                    disabled={replayLoading}
                    className="text-xs bg-violet-500/20 hover:bg-violet-500/30 disabled:opacity-50 text-violet-300 px-4 py-2 rounded-md transition-colors border border-violet-500/30 font-medium whitespace-nowrap"
                  >
                    {replayLoading ? 'Replaying…' : '↺ Run Replay'}
                  </button>
                </div>

                {replayResult && (
                  <div className="space-y-3">
                    {/* Verification Badge */}
                    <div className={`flex items-center gap-3 p-3 rounded-lg border text-sm ${
                      replayResult.verification_status === 'MATCH'
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : replayResult.verification_status === 'REPLAY_MISMATCH'
                        ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                        : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                    }`}>
                      <span className="font-mono font-bold text-xs">{replayResult.verification_status}</span>
                      <span className="text-xs opacity-80">
                        {replayResult.verification_status === 'MATCH'
                          ? 'Replay matches historical record — decision is reproducible.'
                          : replayResult.verification_status === 'REPLAY_MISMATCH'
                          ? 'Replay diverges from historical record — world has changed or record was altered.'
                          : 'No historical trace to compare against; replay succeeded with no baseline.'}
                      </span>
                    </div>

                    {/* Core Metrics Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[
                        { label: 'Overall Status', value: replayResult.overall_status },
                        { label: 'Coverage', value: replayResult.coverage_status },
                        { label: 'Evidence', value: String(replayResult.evidence_count) },
                        { label: 'Conflicts', value: String(replayResult.conflict_count) },
                      ].map(({ label, value }) => (
                        <div key={label} className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
                          <div className="text-sm font-mono font-semibold text-slate-200">{value}</div>
                        </div>
                      ))}
                    </div>

                    {/* Integrity Dimensions */}
                    {Object.keys(replayResult.integrity_dimensions).length > 0 && (
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Integrity Dimensions</div>
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                          {Object.entries(replayResult.integrity_dimensions).map(([dim, st]) => (
                            <div key={dim} className="p-2 rounded bg-slate-900/80 border border-slate-800 text-center">
                              <div className="text-[9px] text-slate-500 uppercase mb-1">{dim}</div>
                              <div className={`text-[10px] font-mono font-bold ${
                                st === 'STRONG' || st === 'VERY_STRONG' ? 'text-emerald-400'
                                : st === 'LIMITED' ? 'text-amber-400'
                                : 'text-rose-400'
                              }`}>{st}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Fingerprints */}
                    <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Canonical Fingerprints</div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-500 w-14 shrink-0">Input</span>
                        <span className="font-mono text-[10px] text-violet-400 truncate">{replayResult.input_fingerprint}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-500 w-14 shrink-0">Result</span>
                        <span className="font-mono text-[10px] text-violet-400 truncate">{replayResult.result_fingerprint}</span>
                      </div>
                    </div>

                    {replayResult.mismatch_details && (
                      <div className="p-3 rounded-lg bg-rose-900/20 border border-rose-500/30">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-rose-400 mb-2 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Mismatch Details</div>
                        <pre className="text-[10px] text-rose-300 font-mono overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(replayResult.mismatch_details, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {/* Diff Time Range Input */}
                <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
                  <div className="flex-1">
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">From (T1)</label>
                    <input
                      type="datetime-local"
                      value={diffFromTime}
                      onChange={e => setDiffFromTime(e.target.value)}
                      className="w-full bg-slate-900/70 border border-slate-700 rounded-md text-slate-200 text-xs px-2.5 py-1.5 focus:outline-none focus:border-violet-500/60"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">To (T2)</label>
                    <input
                      type="datetime-local"
                      value={diffToTime}
                      onChange={e => setDiffToTime(e.target.value)}
                      className="w-full bg-slate-900/70 border border-slate-700 rounded-md text-slate-200 text-xs px-2.5 py-1.5 focus:outline-none focus:border-violet-500/60"
                    />
                  </div>
                  <button
                    onClick={() => triggerDiff(selectedPayment.razorpay_payment_id)}
                    disabled={diffLoading || !diffFromTime || !diffToTime}
                    className="text-xs bg-violet-500/20 hover:bg-violet-500/30 disabled:opacity-50 text-violet-300 px-4 py-2 rounded-md transition-colors border border-violet-500/30 font-medium whitespace-nowrap"
                  >
                    {diffLoading ? 'Comparing…' : '⇄ Compare'}
                  </button>
                </div>

                {diffResult && (
                  <div className="space-y-3">
                    {/* Status Transition */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[
                        { label: 'Integrity T1', value: diffResult.overall_status_t1 },
                        { label: 'Integrity T2', value: diffResult.overall_status_t2 },
                        { label: 'Evidence T1→T2', value: `${diffResult.evidence_count_t1} → ${diffResult.evidence_count_t2}` },
                        { label: 'Conflicts T1→T2', value: `${diffResult.conflict_count_t1} → ${diffResult.conflict_count_t2}` },
                      ].map(({ label, value }) => (
                        <div key={label} className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
                          <div className="text-sm font-mono font-semibold text-slate-200">{value}</div>
                        </div>
                      ))}
                    </div>

                    {/* Fact Diffs */}
                    {diffResult.fact_diffs.length > 0 && (
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                          Fact Lifecycle Changes ({diffResult.fact_diffs.length})
                        </div>
                        <div className="space-y-1.5">
                          {diffResult.fact_diffs.map((fd, i) => (
                            <div key={i} className="flex items-center gap-2.5 p-2 rounded bg-slate-900/80 border border-slate-800 text-xs">
                              <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded uppercase shrink-0 ${
                                fd.category === 'ADDED' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : fd.category === 'REMOVED' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                                : fd.category === 'CHANGED' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                : fd.category === 'SUPERSEDED' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30'
                                : 'bg-slate-700/40 text-slate-400 border border-slate-600/30'
                              }`}>{fd.category}</span>
                              <span className="text-slate-300 font-medium shrink-0">{fd.fact_type}</span>
                              <span className="text-slate-500 font-mono truncate">{fd.canonical_value}</span>
                              {fd.from_state && fd.to_state && (
                                <span className="text-slate-500 text-[10px] shrink-0">{fd.from_state} → {fd.to_state}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Dimension Diffs */}
                    {Object.keys(diffResult.integrity_dimension_diffs).length > 0 && (
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Integrity Dimension Shifts</div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                          {Object.entries(diffResult.integrity_dimension_diffs).map(([dim, { t1, t2 }]) => (
                            <div key={dim} className="p-2 rounded bg-slate-900/80 border border-slate-800">
                              <div className="text-[9px] text-slate-500 uppercase mb-1">{dim}</div>
                              <div className="text-xs font-mono">
                                <span className="text-slate-400">{t1}</span>
                                <span className="text-slate-600 mx-1">→</span>
                                <span className={t2 === t1 ? 'text-slate-400' : 'text-amber-400 font-bold'}>{t2}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Diff Summary */}
                    {diffResult.diff_summary.length > 0 && (
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Diff Summary</div>
                        <ul className="space-y-1">
                          {diffResult.diff_summary.map((line, i) => (
                            <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                              <span className="text-slate-600 mt-0.5">•</span>{line}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Change Explanation */}
                {diffExplanation && (
                  <div className="space-y-3 mt-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Deterministic Change Explanation</div>

                    {[
                      { label: 'What Changed', items: diffExplanation.what_changed, color: 'violet' },
                      { label: 'Why It Mattered', items: diffExplanation.why_it_mattered, color: 'amber' },
                      { label: 'What Remains Uncertain', items: diffExplanation.what_remains_uncertain, color: 'rose' },
                    ].filter(({ items }) => items.length > 0).map(({ label, items, color }) => (
                      <div key={label} className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        <div className={`text-[10px] font-semibold uppercase tracking-wider text-${color}-400 mb-2`}>{label}</div>
                        <ul className="space-y-1">
                          {items.map((item, i) => (
                            <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                              <span className={`text-[9px] font-mono font-bold text-${color}-500 mt-0.5 shrink-0`}>{item.category}</span>
                              <span>{item.statement}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}

                    {diffExplanation.causal_summary && (
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-violet-500/20">
                        <div className="text-[10px] font-semibold uppercase tracking-wider text-violet-400 mb-1">Causal Summary</div>
                        <p className="text-xs text-slate-300 leading-relaxed italic">{diffExplanation.causal_summary}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
