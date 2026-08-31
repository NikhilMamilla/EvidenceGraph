import { useState, useEffect, useCallback } from 'react'

interface Dataset {
  dataset_version: string
  total_cases: number
  is_frozen: boolean
  source_counts: Record<string, number>
  label_counts: Record<string, number>
  split_counts: Record<string, number>
  dataset_fingerprint: string | null
  methodology_version: string | null
}

interface EvalRun {
  run_id: string
  dataset_version: string
  status: string
  total_cases: number
  evaluated_cases: number
  correct_predictions: number
  accuracy: number
  macro_f1: number | null
  results_fingerprint: string | null
  created_at: string | null
}

interface CaseDetail {
  case_id: string
  dispute_category: string
  dispute_reason: string
  case_description: string
  case_source: string
  status: string
  claims: {
    claim_id: string
    claim_text: string
    claim_type: string
    evidence_links: { evidence_observation_id: number; link_type: string }[]
  }[]
  ground_truth: { label: string; rationale: string } | null
}

const LABEL_COLORS: Record<string, string> = {
  SUPPORTED: '#22c55e',
  INSUFFICIENT_EVIDENCE: '#f59e0b',
  CONTRADICTED: '#ef4444',
  UNKNOWN: '#6b7280',
}

const LABEL_ICONS: Record<string, string> = {
  SUPPORTED: '✅',
  INSUFFICIENT_EVIDENCE: '⚠️',
  CONTRADICTED: '❌',
  UNKNOWN: '❓',
}

export default function DefenseEvaluation() {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'cases' | 'runs' | 'matrix'>('overview')
  const [seeding, setSeeding] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [lastEvalResult, setLastEvalResult] = useState<any>(null)

  const fetchData = useCallback(async () => {
    try {
      const [dsRes, runRes] = await Promise.all([
        fetch('/api/v1/defense/evaluation/datasets'),
        fetch('/api/v1/defense/evaluation/runs'),
      ])
      if (dsRes.ok) setDatasets(await dsRes.json())
      if (runRes.ok) setRuns(await runRes.json())
    } catch {}
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const seedDataset = async () => {
    setSeeding(true)
    try {
      await fetch('/api/v1/defense/evaluation/seed', { method: 'POST' })
      await fetchData()
    } finally {
      setSeeding(false)
    }
  }

  const runEvaluation = async () => {
    setEvaluating(true)
    try {
      const res = await fetch('/api/v1/defense/evaluation/run', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setLastEvalResult(data)
        await fetchData()
      }
    } finally {
      setEvaluating(false)
    }
  }

  const loadCase = async (caseId: string) => {
    const res = await fetch(`/api/v1/defense/evaluation/cases/${caseId}`)
    if (res.ok) setSelectedCase(await res.json())
  }

  const ds = datasets[0]
  const latestRun = lastEvalResult || (runs.length > 0 ? runs[0] : null)

  return (
    <div className="min-h-screen p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight"
              style={{ fontFamily: 'var(--font-display)' }}>
            🛡️ Defense Verification Evaluation
          </h1>
          <p className="text-sm mt-1 opacity-70">
            Phase 21 — Deterministic Reference Baseline | No AI Implemented
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={seedDataset}
            disabled={seeding}
            className="px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {seeding ? '⏳ Seeding...' : '🌱 Seed Golden Cases'}
          </button>
          <button
            onClick={runEvaluation}
            disabled={evaluating || !ds}
            className="px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'var(--accent-secondary, #8b5cf6)', color: '#fff' }}
          >
            {evaluating ? '⏳ Evaluating...' : '🔬 Run Evaluation'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl w-fit"
           style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.05))' }}>
        {(['overview', 'cases', 'runs', 'matrix'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-all capitalize"
            style={{
              background: activeTab === tab ? 'var(--accent)' : 'transparent',
              color: activeTab === tab ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {tab === 'overview' ? '📊 Overview' : tab === 'cases' ? '📋 Cases' : tab === 'runs' ? '🔬 Runs' : '🧮 Confusion Matrix'}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Dataset info */}
          {ds ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCard label="Dataset Version" value={ds.dataset_version} icon="📦" />
              <MetricCard label="Total Cases" value={String(ds.total_cases)} icon="📋" />
              <MetricCard label="Frozen" value={ds.is_frozen ? '🔒 Yes' : '🔓 No'} icon="❄️" />
            </div>
          ) : (
            <div className="glass-card p-8 text-center">
              <p className="text-lg opacity-70">No dataset found. Click "Seed Golden Cases" to create one.</p>
            </div>
          )}

          {/* Label Distribution */}
          {ds && ds.label_counts && (
            <div className="glass-card p-6">
              <h3 className="text-lg font-bold mb-4" style={{ fontFamily: 'var(--font-display)' }}>
                Label Distribution
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(ds.label_counts).map(([label, count]) => (
                  <div key={label} className="p-3 rounded-xl text-center"
                       style={{ background: `${LABEL_COLORS[label]}15`, border: `1px solid ${LABEL_COLORS[label]}30` }}>
                    <div className="text-2xl mb-1">{LABEL_ICONS[label]}</div>
                    <div className="text-2xl font-bold" style={{ color: LABEL_COLORS[label] }}>{count}</div>
                    <div className="text-xs opacity-70 mt-1">{label.replace(/_/g, ' ')}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Source & Split Distribution */}
          {ds && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="glass-card p-6">
                <h3 className="text-lg font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
                  📁 Source Distribution
                </h3>
                {ds.source_counts && Object.entries(ds.source_counts).map(([src, count]) => (
                  <div key={src} className="flex justify-between items-center py-2 border-b"
                       style={{ borderColor: 'var(--border)' }}>
                    <span className="text-sm">{src.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-bold">{count}</span>
                  </div>
                ))}
              </div>
              <div className="glass-card p-6">
                <h3 className="text-lg font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
                  🔀 Split Distribution
                </h3>
                {ds.split_counts && Object.entries(ds.split_counts).map(([split, count]) => (
                  <div key={split} className="flex justify-between items-center py-2 border-b"
                       style={{ borderColor: 'var(--border)' }}>
                    <span className="text-sm">{split}</span>
                    <span className="text-sm font-bold">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Latest Evaluation Results */}
          {latestRun && latestRun.metrics && (
            <div className="glass-card p-6">
              <h3 className="text-lg font-bold mb-4" style={{ fontFamily: 'var(--font-display)' }}>
                📊 Latest Evaluation Results
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricCard label="Accuracy" value={`${((latestRun.metrics?.accuracy || latestRun.accuracy || 0) * 100).toFixed(1)}%`} icon="🎯" />
                <MetricCard label="Macro F1" value={`${((latestRun.metrics?.macro_f1 || latestRun.macro_f1 || 0) * 100).toFixed(1)}%`} icon="📊" />
                <MetricCard label="Evaluated" value={String(latestRun.evaluated_cases || latestRun.correct_predictions || 0)} icon="✅" />
                <MetricCard label="Run ID" value={latestRun.run_id || 'N/A'} icon="🔬" />
              </div>

              {/* Per-class metrics */}
              {latestRun.metrics?.per_class && (
                <div className="mt-4 space-y-2">
                  <h4 className="text-sm font-bold opacity-70">Per-Class Metrics</h4>
                  {Object.entries(latestRun.metrics.per_class).map(([label, data]: [string, any]) => (
                    <div key={label} className="flex items-center gap-3 p-2 rounded-lg"
                         style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.03))' }}>
                      <span className="text-lg">{LABEL_ICONS[label]}</span>
                      <span className="text-sm font-medium w-48">{label.replace(/_/g, ' ')}</span>
                      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--surface)' }}>
                        <div className="h-full rounded-full transition-all"
                             style={{ width: `${(data.f1 || 0) * 100}%`, background: LABEL_COLORS[label] }} />
                      </div>
                      <span className="text-xs w-16 text-right">
                        P: {data.precision !== null ? `${(data.precision * 100).toFixed(0)}%` : 'N/A'}
                      </span>
                      <span className="text-xs w-16 text-right">
                        R: {data.recall !== null ? `${(data.recall * 100).toFixed(0)}%` : 'N/A'}
                      </span>
                      <span className="text-xs w-16 text-right">
                        F1: {data.f1 !== null ? `${(data.f1 * 100).toFixed(0)}%` : 'N/A'}
                      </span>
                      <span className="text-xs w-12 text-right opacity-50">
                        n={data.support}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Data source warning */}
              <div className="mt-4 p-3 rounded-xl text-xs"
                   style={{ background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
                ⚠️ <strong>Statistical Honesty:</strong> This evaluation uses {latestRun.total_cases || latestRun.evaluated_cases || 0} controlled/synthetic cases.
                This does NOT prove production performance. Confidence intervals are wide with small N.
                No AI has been implemented — this is the deterministic reference baseline.
              </div>
            </div>
          )}

          {/* Dataset Fingerprint */}
          {ds?.dataset_fingerprint && (
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 text-xs opacity-60">
                <span>🔐 Dataset Fingerprint:</span>
                <code className="font-mono">{ds.dataset_fingerprint.substring(0, 32)}...</code>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Cases Tab */}
      {activeTab === 'cases' && (
        <div className="space-y-4">
          {!ds ? (
            <div className="glass-card p-8 text-center">
              <p className="opacity-70">No dataset. Seed golden cases first.</p>
            </div>
          ) : (
            <>
              <CasesList onSelectCase={loadCase} />
              {selectedCase && (
                <CaseDetailView caseData={selectedCase} onClose={() => setSelectedCase(null)} />
              )}
            </>
          )}
        </div>
      )}

      {/* Runs Tab */}
      {activeTab === 'runs' && (
        <div className="space-y-4">
          {runs.length === 0 ? (
            <div className="glass-card p-8 text-center">
              <p className="opacity-70">No evaluation runs yet. Click "Run Evaluation" to start one.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {runs.map(run => (
                <div key={run.run_id} className="glass-card p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-mono text-sm">{run.run_id}</span>
                      <span className="ml-2 text-xs px-2 py-1 rounded-full"
                            style={{ background: run.status === 'COMPLETED' ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)' }}>
                        {run.status}
                      </span>
                    </div>
                    <div className="text-right text-sm">
                      <div>Accuracy: <strong>{(run.accuracy * 100).toFixed(1)}%</strong></div>
                      {run.macro_f1 && <div>F1: <strong>{(run.macro_f1 * 100).toFixed(1)}%</strong></div>}
                    </div>
                  </div>
                  <div className="text-xs opacity-50 mt-1">
                    {run.evaluated_cases} cases | {run.correct_predictions} correct | {run.dataset_version}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Confusion Matrix Tab */}
      {activeTab === 'matrix' && (
        <div>
          {latestRun?.confusion_matrix ? (
            <ConfusionMatrixView matrix={latestRun.confusion_matrix} />
          ) : (
            <div className="glass-card p-8 text-center">
              <p className="opacity-70">No evaluation results yet. Run an evaluation to see the confusion matrix.</p>
            </div>
          )}
        </div>
      )}

      {/* Methodology Note */}
      <div className="glass-card p-4 text-xs opacity-50 space-y-1">
        <div>Methodology: DEFENSE_VERIFICATION_METHODOLOGY_V1</div>
        <div>Scope: DELIVERY_NOT_RECEIVED disputes only</div>
        <div>This tab: deterministic reference baseline. AI semantic layer + three-way eval → AI Verify tab.</div>
        <div>Domain: EvidenceGraph — Pre-Submission Chargeback Defense Verifier</div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className="glass-card p-4 text-center">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-xl font-bold" style={{ fontFamily: 'var(--font-display)' }}>{value}</div>
      <div className="text-xs opacity-60 mt-1">{label}</div>
    </div>
  )
}

function CasesList({ onSelectCase }: { onSelectCase: (id: string) => void }) {
  const [cases, setCases] = useState<{ case_id: string; dispute_reason: string; case_source: string; status: string }[]>([])

  useEffect(() => {
    fetch('/api/v1/defense/evaluation/datasets/EG-DEFENSE-1.0')
      .then(r => r.json())
      .then(data => setCases(data.cases || []))
      .catch(() => {})
  }, [])

  return (
    <div className="glass-card p-4">
      <h3 className="text-lg font-bold mb-3" style={{ fontFamily: 'var(--font-display)' }}>
        📋 Golden Test Cases ({cases.length})
      </h3>
      <div className="space-y-2 max-h-[60vh] overflow-y-auto">
        {cases.map(c => (
          <button
            key={c.case_id}
            onClick={() => onSelectCase(c.case_id)}
            className="w-full text-left p-3 rounded-xl transition-all hover:scale-[1.01]"
            style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.03))' }}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold">{c.case_id}</span>
              <span className="text-xs px-2 py-1 rounded-full"
                    style={{ background: 'var(--accent)20', color: 'var(--accent)' }}>
                {c.case_source.replace(/_/g, ' ')}
              </span>
            </div>
            <div className="text-xs opacity-70 mt-1">{c.dispute_reason}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function CaseDetailView({ caseData, onClose }: { caseData: CaseDetail; onClose: () => void }) {
  return (
    <div className="glass-card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold" style={{ fontFamily: 'var(--font-display)' }}>
          {caseData.case_id}
        </h3>
        <button onClick={onClose} className="text-sm opacity-60 hover:opacity-100">✕ Close</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <div>
          <div className="opacity-60 text-xs mb-1">Dispute Reason</div>
          <div>{caseData.dispute_reason}</div>
        </div>
        <div>
          <div className="opacity-60 text-xs mb-1">Source</div>
          <div>{caseData.case_source.replace(/_/g, ' ')}</div>
        </div>
        <div className="md:col-span-2">
          <div className="opacity-60 text-xs mb-1">Description</div>
          <div>{caseData.case_description}</div>
        </div>
      </div>

      {/* Ground Truth */}
      {caseData.ground_truth && (
        <div className="p-3 rounded-xl"
             style={{ background: `${LABEL_COLORS[caseData.ground_truth.label]}15`, border: `1px solid ${LABEL_COLORS[caseData.ground_truth.label]}30` }}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">{LABEL_ICONS[caseData.ground_truth.label]}</span>
            <span className="font-bold" style={{ color: LABEL_COLORS[caseData.ground_truth.label] }}>
              Ground Truth: {caseData.ground_truth.label}
            </span>
          </div>
          <div className="text-xs opacity-80">{caseData.ground_truth.rationale}</div>
        </div>
      )}

      {/* Claims */}
      <div className="space-y-3">
        <h4 className="text-sm font-bold opacity-70">Claims ({caseData.claims.length})</h4>
        {caseData.claims.map(claim => (
          <div key={claim.claim_id} className="p-3 rounded-xl"
               style={{ background: 'var(--surface-secondary, rgba(255,255,255,0.03))' }}>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold">{claim.claim_id}</span>
              <span className="text-xs px-2 py-0.5 rounded-full opacity-70">{claim.claim_type}</span>
            </div>
            <div className="text-sm mt-1">{claim.claim_text}</div>
            <div className="text-xs opacity-50 mt-1">
              Evidence links: {claim.evidence_links.length}
              {claim.evidence_links.map((l, i) => (
                <span key={i} className="ml-1 px-1 rounded"
                      style={{ background: l.link_type === 'SUPPORTING' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}>
                  {l.link_type}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ConfusionMatrixView({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const labels = Object.keys(matrix)
  const maxVal = Math.max(...labels.flatMap(a => labels.map(b => matrix[a]?.[b] || 0)))

  return (
    <div className="glass-card p-6">
      <h3 className="text-lg font-bold mb-4" style={{ fontFamily: 'var(--font-display)' }}>
        🧮 Confusion Matrix
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="p-2 text-left text-xs opacity-60">Actual ↓ / Predicted →</th>
              {labels.map(l => (
                <th key={l} className="p-2 text-center text-xs" style={{ color: LABEL_COLORS[l] }}>
                  {LABEL_ICONS[l]} {l.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map(actual => (
              <tr key={actual}>
                <td className="p-2 text-xs font-medium" style={{ color: LABEL_COLORS[actual] }}>
                  {LABEL_ICONS[actual]} {actual.replace(/_/g, ' ')}
                </td>
                {labels.map(predicted => {
                  const val = matrix[actual]?.[predicted] || 0
                  const isDiag = actual === predicted
                  const intensity = maxVal > 0 ? val / maxVal : 0
                  return (
                    <td key={predicted} className="p-2 text-center">
                      <div
                        className="rounded-lg py-2 font-bold text-lg"
                        style={{
                          background: isDiag
                            ? `rgba(34, 197, 94, ${0.1 + intensity * 0.4})`
                            : val > 0
                              ? `rgba(239, 68, 68, ${0.1 + intensity * 0.4})`
                              : 'transparent',
                        }}
                      >
                        {val}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 text-xs opacity-50">
        Diagonal = correct predictions | Off-diagonal = errors | Green = correct | Red = incorrect
      </div>
    </div>
  )
}
