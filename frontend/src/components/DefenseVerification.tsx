import { useState, useEffect, useCallback } from 'react'

interface ClaimExtraction {
  claim_type: string
  claim_text: string
  normalized_value: string | boolean | null
  confidence: number
}

interface EvidenceMatch {
  claim_id: string
  evidence_id: number
  relationship: string
  confidence: number
  reason: string
}

interface VerificationResult {
  case_id: string
  defense_text: string
  claims_extracted: ClaimExtraction[]
  evidence_matches: EvidenceMatch[]
  deterministic_result: any
  final_decision: string
  decision_rationale: string
  ai_semantic_status: string
  deterministic_status: string
  methodology_version: string
}

interface DefenseCase {
  case_id: string
  dispute_reason: string
  case_description: string
  case_source: string
}

const DECISION_COLORS: Record<string, string> = {
  SUPPORTED: '#22c55e',
  INSUFFICIENT_EVIDENCE: '#f59e0b',
  CONTRADICTED: '#ef4444',
  UNKNOWN: '#6b7280',
}

const RELATIONSHIP_COLORS: Record<string, string> = {
  RELEVANT: '#22c55e',
  NOT_RELEVANT: '#ef4444',
  UNCERTAIN: '#f59e0b',
}

function ThreeWayComparison() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const fetchEvaluation = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/defense/ai/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      if (res.ok) setData(await res.json())
    } finally { setLoading(false) }
  }

  if (!data) return (
    <div className="glass-card p-6">
      <h3 className="text-lg font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>📊 Three-Way Evaluation</h3>
      <p className="text-xs opacity-60 mb-3">Compare: Deterministic baseline vs Test AI vs Real LLM</p>
      <button onClick={fetchEvaluation} disabled={loading} className="px-4 py-2 rounded-xl text-sm font-semibold" style={{ background: 'var(--accent)', color: '#fff' }}>
        {loading ? '⏳ Evaluating...' : '🔬 Run Three-Way Evaluation'}
      </button>
    </div>
  )

  const ta = data.track_a_deterministic || {}
  const tb = data.track_b_test_ai || {}
  const tc = data.track_c_real_llm || {}

  return (
    <div className="space-y-4">
      <div className="glass-card p-6">
        <h3 className="text-lg font-bold mb-4" style={{ fontFamily: 'var(--font-display)' }}>📊 Three-Way Evaluation Results</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[{ label: 'Deterministic', track: ta, color: '#6b7280' }, { label: 'Test AI', track: tb, color: '#6c5ce7' }, { label: 'Real LLM', track: tc, color: tc.status === 'REAL_LLM_NOT_CONFIGURED' ? '#f59e0b' : '#22c55e' }].map(({ label, track, color }) => (
            <div key={label} className="p-4 rounded-xl text-center" style={{ background: `${color}10`, border: `1px solid ${color}30` }}>
              <div className="text-xs font-bold mb-2" style={{ color }}>{label}</div>
              {track.status === 'REAL_LLM_NOT_CONFIGURED' ? (
                <div className="text-xs opacity-60">NOT CONFIGURED</div>
              ) : (
                <>
                  <div className="text-2xl font-bold" style={{ fontFamily: 'var(--font-display)' }}>{((track.accuracy || 0) * 100).toFixed(0)}%</div>
                  <div className="text-xs opacity-60">Accuracy</div>
                  <div className="text-sm font-bold mt-1">F1: {((track.macro_f1 || 0) * 100).toFixed(0)}%</div>
                  <div className="text-xs mt-2 p-2 rounded" style={{ background: (track.safety?.false_supported_rate || 0) > 0 ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)' }}>
                    False Supported: {((track.safety?.false_supported_rate || 0) * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs mt-1 p-2 rounded" style={{ background: (track.safety?.contradiction_miss_rate || 0) > 0 ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)' }}>
                    Contradiction Miss: {((track.safety?.contradiction_miss_rate || 0) * 100).toFixed(0)}%
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
      {/* Confusion Matrix Comparison */}
      {ta.confusion_matrix && (
        <div className="glass-card p-6">
          <h4 className="text-sm font-bold mb-3">Confusion Matrix — Deterministic Baseline</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr><th className="p-1 text-left opacity-60">Actual \ Pred</th>
                {ALL_LABELS.map(l => <th key={l} className="p-1 text-center" style={{ color: LABEL_COLORS[l] }}>{l.replace(/_/g, ' ')}</th>)}</tr></thead>
              <tbody>
                {ALL_LABELS.map(actual => (
                  <tr key={actual}><td className="p-1 font-medium" style={{ color: LABEL_COLORS[actual] }}>{actual.replace(/_/g, ' ')}</td>
                    {ALL_LABELS.map(pred => {
                      const val = ta.confusion_matrix[actual]?.[pred] || 0
                      return <td key={pred} className="p-1 text-center" style={{ background: actual === pred && val > 0 ? 'rgba(34,197,94,0.15)' : val > 0 ? 'rgba(239,68,68,0.1)' : 'transparent' }}>{val}</td>
                    })}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {/* False Supported Cases */}
      {ta.false_supported_cases && ta.false_supported_cases.length > 0 && (
        <div className="glass-card p-4">
          <h4 className="text-sm font-bold mb-2" style={{ color: '#ef4444' }}>⚠️ False-Supported Cases (Safety Review Required)</h4>
          {ta.false_supported_cases.map((c: any, i: number) => (
            <div key={i} className="text-xs p-2 rounded mb-1" style={{ background: 'rgba(239,68,68,0.1)' }}>
              {c.case_id}: Expected {c.expected}, Predicted {c.predicted}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const ALL_LABELS = ['SUPPORTED', 'INSUFFICIENT_EVIDENCE', 'CONTRADICTED', 'UNKNOWN']
const LABEL_COLORS: Record<string, string> = { SUPPORTED: '#22c55e', INSUFFICIENT_EVIDENCE: '#f59e0b', CONTRADICTED: '#ef4444', UNKNOWN: '#6b7280' }

export default function DefenseVerification() {
  const [cases, setCases] = useState<DefenseCase[]>([])
  const [selectedCase, setSelectedCase] = useState<string>('')
  const [defenseText, setDefenseText] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [aiStatus, setAiStatus] = useState<any>(null)
  const [, setShowDemo] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [dsRes, statusRes] = await Promise.all([
        fetch('/api/v1/defense/evaluation/datasets/EG-DEFENSE-1.0'),
        fetch('/api/v1/defense/ai/status'),
      ])
      if (dsRes.ok) {
        const ds = await dsRes.json()
        setCases(ds.cases || [])
      }
      if (statusRes.ok) setAiStatus(await statusRes.json())
    } catch {}
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const verifyDefense = async () => {
    if (!selectedCase || !defenseText.trim()) return
    setVerifying(true)
    try {
      const res = await fetch('/api/v1/defense/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: selectedCase,
          defense_text: defenseText,
        }),
      })
      if (res.ok) setResult(await res.json())
    } finally {
      setVerifying(false)
    }
  }

  const runDemo = async (caseId: string, text: string) => {
    setSelectedCase(caseId)
    setDefenseText(text)
    setShowDemo(true)
    setVerifying(true)
    try {
      const res = await fetch('/api/v1/defense/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId, defense_text: text }),
      })
      if (res.ok) setResult(await res.json())
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="min-h-screen p-4 md:p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight"
            style={{ fontFamily: 'var(--font-display)' }}>
          🛡️ AI Defense Verification
        </h1>
        <p className="text-sm mt-1 opacity-70">
          Phase 22 — AI Semantic Layer + Deterministic EvidenceGraph
        </p>
      </div>

      {/* AI Status */}
      <div className="glass-card p-3 flex items-center gap-3 text-xs">
        <span className="font-bold">AI Provider:</span>
        <span className="px-2 py-0.5 rounded-full"
              style={{
                background: aiStatus?.enabled ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)',
                color: aiStatus?.enabled ? '#22c55e' : '#f59e0b',
              }}>
          {aiStatus?.status || 'CHECKING'}
        </span>
        {aiStatus?.provider && <span className="opacity-60">{aiStatus.provider}</span>}
      </div>

      {/* Architecture Diagram */}
      <div className="glass-card p-4 text-xs font-mono space-y-1 opacity-70">
        <div className="font-bold mb-2" style={{ fontFamily: 'var(--font-display)' }}>
          🔗 Verification Pipeline
        </div>
        <div>Merchant Defense Text</div>
        <div>  → 🤖 AI Claim Understanding (semantic parsing)</div>
        <div>  → 🤖 AI Evidence Matching (relevance ranking)</div>
        <div>  → 🔍 ID Validation (reject hallucinated IDs)</div>
        <div>  → 📐 EvidenceGraph Deterministic Verification</div>
        <div>  → ✅ Final Decision (deterministic authority)</div>
      </div>

      {/* Demo Scenarios */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-bold mb-4" style={{ fontFamily: 'var(--font-display)' }}>
          🎬 Interactive Demo
        </h3>
        <p className="text-xs opacity-60 mb-4">
          Click a scenario to see the full AI + EvidenceGraph verification pipeline.
        </p>
        <div className="space-y-2">
          {[
            {
              caseId: 'GOLDEN_001',
              text: 'The customer received the package on August 18 and signed for delivery.',
              label: '✅ Fully Supported',
              color: '#22c55e',
            },
            {
              caseId: 'GOLDEN_004',
              text: 'The package was delivered to the customer address.',
              label: '⚠️ Missing Evidence',
              color: '#f59e0b',
            },
            {
              caseId: 'GOLDEN_007',
              text: 'The package was delivered successfully by our courier.',
              label: '❌ Contradicted',
              color: '#ef4444',
            },
            {
              caseId: 'GOLDEN_015',
              text: 'The customer definitely received the goods.',
              label: '❓ No Evidence',
              color: '#6b7280',
            },
          ].map(demo => (
            <button
              key={demo.caseId}
              onClick={() => runDemo(demo.caseId, demo.text)}
              className="w-full text-left p-3 rounded-xl transition-all hover:scale-[1.01] border"
              style={{ borderColor: `${demo.color}30`, background: `${demo.color}08` }}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{demo.label}</span>
                <span className="text-xs opacity-50 font-mono">{demo.caseId}</span>
              </div>
              <div className="text-xs opacity-60 mt-1 italic">"{demo.text}"</div>
            </button>
          ))}
        </div>
      </div>

      {/* Custom Input */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
          ✍️ Custom Defense Statement
        </h3>
        <div className="space-y-3">
          <select
            value={selectedCase}
            onChange={e => setSelectedCase(e.target.value)}
            className="w-full p-3 rounded-xl text-sm"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
          >
            <option value="">Select a defense case...</option>
            {cases.map(c => (
              <option key={c.case_id} value={c.case_id}>
                {c.case_id} — {c.dispute_reason}
              </option>
            ))}
          </select>
          <textarea
            value={defenseText}
            onChange={e => setDefenseText(e.target.value)}
            placeholder="Enter merchant's defense statement...&#10;Example: The customer received the package on August 18 and signed for delivery."
            rows={3}
            className="w-full p-3 rounded-xl text-sm resize-none"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
          />
          <button
            onClick={verifyDefense}
            disabled={!selectedCase || !defenseText.trim() || verifying}
            className="px-6 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {verifying ? '⏳ Verifying...' : '🔍 Run Verification'}
          </button>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Final Decision */}
          <div className="glass-card p-6 text-center">
            <div className="text-sm opacity-60 mb-2">FINAL DECISION</div>
            <div
              className="text-3xl font-bold mb-2"
              style={{
                color: DECISION_COLORS[result.final_decision] || '#6b7280',
                fontFamily: 'var(--font-display)',
              }}
            >
              {result.final_decision}
            </div>
            <div className="text-xs opacity-50 max-w-xl mx-auto">
              {result.decision_rationale}
            </div>
          </div>

          {/* Two-column: AI + Deterministic */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* AI Claims */}
            <div className="glass-card p-4">
              <h4 className="text-sm font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
                🤖 AI Extracted Claims ({result.claims_extracted.length})
              </h4>
              {result.claims_extracted.length === 0 ? (
                <div className="text-xs opacity-50">No claims extracted</div>
              ) : (
                <div className="space-y-2">
                  {result.claims_extracted.map((claim, i) => (
                    <div key={i} className="p-3 rounded-xl text-xs"
                         style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.03))' }}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono font-bold" style={{ color: 'var(--accent)' }}>
                          {claim.claim_type}
                        </span>
                        <span className="opacity-60">{(claim.confidence * 100).toFixed(0)}%</span>
                      </div>
                      <div className="opacity-70">{claim.claim_text}</div>
                      {claim.normalized_value && (
                        <div className="mt-1 opacity-50">
                          Normalized: <span className="font-mono">{String(claim.normalized_value)}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Evidence Matches */}
            <div className="glass-card p-4">
              <h4 className="text-sm font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
                🔗 AI Evidence Matches ({result.evidence_matches.length})
              </h4>
              {result.evidence_matches.length === 0 ? (
                <div className="text-xs opacity-50">No evidence matched</div>
              ) : (
                <div className="space-y-2">
                  {result.evidence_matches.map((match, i) => (
                    <div key={i} className="p-3 rounded-xl text-xs"
                         style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.03))' }}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono font-bold">
                          EV-{match.evidence_id}
                        </span>
                        <span
                          className="px-2 py-0.5 rounded-full text-[10px] font-bold"
                          style={{
                            background: `${RELATIONSHIP_COLORS[match.relationship]}20`,
                            color: RELATIONSHIP_COLORS[match.relationship],
                          }}
                        >
                          {match.relationship}
                        </span>
                      </div>
                      <div className="opacity-60">{match.reason}</div>
                      <div className="opacity-40 mt-1">
                        Claim: {match.claim_id} | Confidence: {(match.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Deterministic Result */}
          <div className="glass-card p-4">
            <h4 className="text-sm font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
              📐 EvidenceGraph Deterministic Verification
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-xl text-center"
                   style={{ background: 'var(--surface-secondary)' }}>
                <div className="opacity-50 mb-1">Case Label</div>
                <div className="font-bold" style={{
                  color: DECISION_COLORS[result.deterministic_result?.case_label] || '#6b7280'
                }}>
                  {result.deterministic_result?.case_label || 'N/A'}
                </div>
              </div>
              <div className="p-3 rounded-xl text-center"
                   style={{ background: 'var(--surface-secondary)' }}>
                <div className="opacity-50 mb-1">Claims Evaluated</div>
                <div className="font-bold">
                  {result.deterministic_result?.claim_results?.length || 0}
                </div>
              </div>
              <div className="p-3 rounded-xl text-center"
                   style={{ background: 'var(--surface-secondary)' }}>
                <div className="opacity-50 mb-1">AI Status</div>
                <div className="font-bold">{result.ai_semantic_status}</div>
              </div>
              <div className="p-3 rounded-xl text-center"
                   style={{ background: 'var(--surface-secondary)' }}>
                <div className="opacity-50 mb-1">Methodology</div>
                <div className="font-mono text-[10px]">{result.methodology_version}</div>
              </div>
            </div>
          </div>

          {/* Key Insight */}
          <div className="glass-card p-4 text-xs"
               style={{ background: 'rgba(108, 92, 231, 0.08)', border: '1px solid rgba(108, 92, 231, 0.2)' }}>
            <div className="font-bold mb-1" style={{ color: '#6c5ce7' }}>
              🔑 Key Insight
            </div>
            <div className="opacity-80">
              The AI layer identified {result.claims_extracted.length} claims and {result.evidence_matches.filter(m => m.relationship === 'RELEVANT').length} relevant evidence links.
              But the <strong>final decision</strong> was made entirely by EvidenceGraph's deterministic verification — not by AI.
              This means the result is reproducible, auditable, and cannot be manipulated by prompt injection.
            </div>
          </div>
        </div>
      )}

      {/* Three-Way Evaluation */}
      <ThreeWayComparison />

      {/* Methodology */}
      <div className="glass-card p-4 text-xs opacity-50 space-y-1">
        <div>AI Prompt Version: DEFENSE_CLAIM_EXTRACTION_PROMPT_V1</div>
        <div>Evidence Matching Version: EVIDENCE_MATCHING_PROMPT_V1</div>
        <div>Methodology: DEFENSE_VERIFICATION_METHODOLOGY_V2_AI_ENHANCED</div>
        <div>AI Authority: SEMANTIC LAYER ONLY — NOT FINAL AUTHORITY</div>
      </div>
    </div>
  )
}
