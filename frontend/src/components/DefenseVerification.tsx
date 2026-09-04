/**
 * AI Verify — the interactive Track-02 deliverable.
 *
 * Runs a merchant defense statement through the AI semantic layer and then the
 * deterministic evaluator, showing what each side contributed, plus the
 * three-way evaluation (deterministic vs test-AI vs real LLM).
 */

import { useCallback, useEffect, useState } from 'react'
import {
  ArrowRight,
  BarChart3,
  Bot,
  Cpu,
  FlaskConical,
  Link2,
  Loader2,
  PlayCircle,
  ScanSearch,
  Shield,
  ShieldCheck,
} from 'lucide-react'

import { EmptyState, ErrorState, PageHeader, Panel, Pill, Stat } from './ui'
import { VERDICTS, VerdictBadge, VerdictHero, verdictMeta } from './defense/verdict'
import { markGuideStepDone } from '../lib/evaluatorProgress'

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

const RELATIONSHIP_TONE: Record<string, string> = {
  RELEVANT: 'var(--color-success)',
  NOT_RELEVANT: 'var(--color-danger)',
  UNCERTAIN: 'var(--color-warning)',
}

const DEMOS = [
  {
    caseId: 'GOLDEN_001',
    expect: 'SUPPORTED',
    text: 'The customer received the package on August 18 and signed for delivery.',
  },
  {
    caseId: 'GOLDEN_004',
    expect: 'INSUFFICIENT_EVIDENCE',
    text: 'The package was delivered to the customer address.',
  },
  {
    caseId: 'GOLDEN_007',
    expect: 'CONTRADICTED',
    text: 'The package was delivered successfully by our courier.',
  },
  {
    caseId: 'GOLDEN_015',
    expect: 'UNKNOWN',
    text: 'The customer definitely received the goods.',
  },
]

const PIPELINE = [
  { icon: Bot, label: 'Claim extraction', note: 'AI · semantic' },
  { icon: Link2, label: 'Evidence matching', note: 'AI · relevance' },
  { icon: ScanSearch, label: 'ID validation', note: 'rejects hallucinated IDs' },
  { icon: Cpu, label: 'Deterministic evaluation', note: 'EvidenceGraph' },
  { icon: ShieldCheck, label: 'Final verdict', note: 'deterministic authority' },
]

export default function DefenseVerification() {
  const [cases, setCases] = useState<DefenseCase[]>([])
  const [selectedCase, setSelectedCase] = useState('')
  const [defenseText, setDefenseText] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [aiStatus, setAiStatus] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingStatement, setLoadingStatement] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [dsRes, statusRes] = await Promise.all([
        fetch('/api/v1/defense/evaluation/datasets/EG-DEFENSE-1.0'),
        fetch('/api/v1/defense/ai/status'),
      ])
      if (dsRes.ok) setCases((await dsRes.json()).cases || [])
      if (statusRes.ok) setAiStatus(await statusRes.json())
    } catch {
      /* status panel simply stays unknown */
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const run = async (caseId: string, text: string) => {
    if (!caseId || !text.trim()) return
    setVerifying(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/defense/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId, defense_text: text }),
      })
      if (res.ok) {
        const data: VerificationResult = await res.json()
        setResult(data)
        // Real signal for the evaluator checklist: GOLDEN_007 specifically was
        // actually run and returned a verdict — not just that this tab was opened.
        if (data.case_id === 'GOLDEN_007') markGuideStepDone('headline-case')
      } else {
        setError(`Verification failed (HTTP ${res.status}). Is the case seeded?`)
      }
    } catch (e) {
      setError(`Could not reach the API: ${(e as Error).message}`)
    } finally {
      setVerifying(false)
    }
  }

  const runDemo = (caseId: string, text: string) => {
    setSelectedCase(caseId)
    setDefenseText(text)
    run(caseId, text)
  }

  // Selecting a case pulls its real claim text from the golden dataset and
  // drops it straight into the statement box — the merchant's actual wording
  // for that case, not something typed up to match.
  const selectCase = async (caseId: string) => {
    setSelectedCase(caseId)
    setResult(null)
    setError(null)
    if (!caseId) {
      setDefenseText('')
      return
    }
    setLoadingStatement(true)
    try {
      const res = await fetch(`/api/v1/defense/evaluation/cases/${caseId}`)
      if (res.ok) {
        const data = await res.json()
        const claims: { claim_text: string }[] = data.claims || []
        setDefenseText(claims.map(c => c.claim_text).join(' '))
      } else {
        setError(`Could not load case ${caseId} (HTTP ${res.status}).`)
      }
    } catch (e) {
      setError(`Could not reach the API: ${(e as Error).message}`)
    } finally {
      setLoadingStatement(false)
    }
  }

  const aiEnabled = Boolean(aiStatus?.enabled)
  const relevantCount = result?.evidence_matches.filter(m => m.relationship === 'RELEVANT').length ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Shield}
        title="AI Defense Verifier"
        subtitle="The model reads the language. The deterministic engine decides."
        actions={
          <Pill tone={aiEnabled ? 'success' : 'warning'} icon={Bot}>
            {aiStatus?.provider_name || aiStatus?.provider || 'test'} · {aiStatus?.status || 'checking'}
          </Pill>
        }
      />

      {/* Pipeline */}
      <Panel title="Verification pipeline" icon={ArrowRight}>
        <div className="flex flex-wrap items-stretch gap-2">
          {PIPELINE.map((step, i) => (
            <div key={step.label} className="flex flex-1 items-center gap-2" style={{ minWidth: 160 }}>
              <div className="neo-inset flex-1 rounded-xl px-3 py-2.5">
                <div className="mb-1 flex items-center gap-1.5">
                  <step.icon className="h-3.5 w-3.5" style={{ color: 'var(--color-text-accent)' }} />
                  <span
                    className="text-[11px] font-bold"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {step.label}
                  </span>
                </div>
                <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  {step.note}
                </div>
              </div>
              {i < PIPELINE.length - 1 && (
                <ArrowRight
                  className="hidden h-3.5 w-3.5 shrink-0 lg:block"
                  style={{ color: 'var(--color-text-tertiary)' }}
                />
              )}
            </div>
          ))}
        </div>
      </Panel>

      {/* Input: demos + custom, side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Demo scenarios" icon={PlayCircle}>
          <p className="mb-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            One statement per verdict class. Each runs the full pipeline.
          </p>
          <div className="space-y-2">
            {DEMOS.map(demo => {
              const m = verdictMeta(demo.expect)
              return (
                <button
                  key={demo.caseId}
                  onClick={() => runDemo(demo.caseId, demo.text)}
                  disabled={verifying}
                  className="w-full rounded-xl p-3 text-left transition-all hover:translate-y-[-1px] disabled:opacity-50"
                  style={{
                    background: `color-mix(in srgb, ${m.color} 7%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${m.color} 22%, transparent)`,
                  }}
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <VerdictBadge label={demo.expect} />
                    <span
                      className="font-mono text-[10px]"
                      style={{ color: 'var(--color-text-tertiary)' }}
                    >
                      {demo.caseId}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    “{demo.text}”
                  </p>
                </button>
              )
            })}
          </div>
        </Panel>

        <Panel title="Custom statement" icon={FlaskConical}>
          <div className="space-y-3">
            <div>
              <label
                className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                Dispute case
              </label>
              <select
                value={selectedCase}
                onChange={e => selectCase(e.target.value)}
                className="glass-input w-full rounded-xl p-2.5 text-sm"
              >
                <option value="">Select a case…</option>
                {cases.map(c => (
                  <option key={c.case_id} value={c.case_id}>
                    {c.case_id} — {c.dispute_reason}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <label
                  className="block text-[10px] font-semibold uppercase tracking-[0.1em]"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  Merchant defense statement
                </label>
                {loadingStatement && (
                  <span
                    className="flex items-center gap-1 text-[10px]"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    <Loader2 className="h-3 w-3 animate-spin" />
                    filling from case…
                  </span>
                )}
                {!loadingStatement && selectedCase && defenseText && (
                  <span
                    className="text-[10px] italic"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    auto-filled from {selectedCase} · editable
                  </span>
                )}
              </div>
              <textarea
                value={defenseText}
                onChange={e => setDefenseText(e.target.value)}
                placeholder="Select a case above to auto-fill its claim, or type your own statement here."
                rows={5}
                className="glass-input w-full resize-none rounded-xl p-3 text-sm"
              />
            </div>

            <button
              onClick={() => run(selectedCase, defenseText)}
              disabled={!selectedCase || !defenseText.trim() || verifying}
              className="neo-btn-primary flex w-full items-center justify-center gap-2 text-sm disabled:opacity-50"
            >
              {verifying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Verifying…
                </>
              ) : (
                <>
                  <ShieldCheck className="h-4 w-4" /> Run verification
                </>
              )}
            </button>

            {error && <ErrorState message={error} />}
          </div>
        </Panel>
      </div>

      {/* Result */}
      {result && (
        <div className="space-y-6">
          <VerdictHero
            label={result.final_decision}
            rationale={result.decision_rationale}
            meta={
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Pill tone="neutral" mono>
                  {result.case_id}
                </Pill>
                <Pill tone={result.deterministic_status === 'OK' ? 'success' : 'warning'}>
                  deterministic {result.deterministic_status}
                </Pill>
                <Pill tone={result.ai_semantic_status === 'OK' ? 'info' : 'warning'}>
                  AI {result.ai_semantic_status}
                </Pill>
              </div>
            }
          />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Claims extracted" value={result.claims_extracted.length} tone="info" icon={Bot} />
            <Stat label="Relevant evidence" value={relevantCount} tone="accent" icon={Link2} />
            <Stat
              label="Claims evaluated"
              value={result.deterministic_result?.claim_results?.length ?? 0}
              tone="neutral"
              icon={Cpu}
            />
            <Stat
              label="Deterministic label"
              value={
                <span style={{ color: verdictMeta(result.deterministic_result?.case_label).color }}>
                  {verdictMeta(result.deterministic_result?.case_label).short}
                </span>
              }
              icon={ShieldCheck}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel
              title={`AI extracted claims (${result.claims_extracted.length})`}
              icon={Bot}
              footnote="The AI decides what the merchant is claiming — never whether it is true."
            >
              {result.claims_extracted.length === 0 ? (
                <EmptyState icon={Bot} title="No claims extracted" hint="The statement carried no recognisable delivery claim." />
              ) : (
                <ul className="space-y-2">
                  {result.claims_extracted.map((claim, i) => (
                    <li key={i} className="neo-inset rounded-xl p-3">
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span
                          className="font-mono text-[11px] font-bold"
                          style={{ color: 'var(--color-text-accent)' }}
                        >
                          {claim.claim_type}
                        </span>
                        <ConfidenceBar value={claim.confidence} />
                      </div>
                      <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                        {claim.claim_text}
                      </p>
                      {claim.normalized_value !== null && claim.normalized_value !== undefined && (
                        <p className="mt-1.5 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                          normalised ·{' '}
                          <span style={{ fontFamily: 'var(--font-mono)' }}>
                            {String(claim.normalized_value)}
                          </span>
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel
              title={`Evidence matches (${result.evidence_matches.length})`}
              icon={Link2}
              footnote="Every evidence ID is validated against the real candidate set before use."
            >
              {result.evidence_matches.length === 0 ? (
                <EmptyState icon={Link2} title="No evidence matched" hint="Nothing in the case was proposed as semantically relevant." />
              ) : (
                <ul className="space-y-2">
                  {result.evidence_matches.map((match, i) => {
                    const tone = RELATIONSHIP_TONE[match.relationship] ?? 'var(--color-text-tertiary)'
                    return (
                      <li key={i} className="neo-inset rounded-xl p-3">
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <span
                            className="font-mono text-[11px] font-bold"
                            style={{ color: 'var(--color-text-primary)' }}
                          >
                            EV-{match.evidence_id}
                          </span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                            style={{
                              color: tone,
                              background: `color-mix(in srgb, ${tone} 14%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${tone} 28%, transparent)`,
                            }}
                          >
                            {match.relationship}
                          </span>
                        </div>
                        {match.reason && (
                          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                            {match.reason}
                          </p>
                        )}
                        <p className="mt-1.5 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                          {match.claim_id} · {(match.confidence * 100).toFixed(0)}% confidence
                        </p>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Panel>
          </div>

          <Panel title="Why this is safe" icon={ShieldCheck}>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              The AI layer proposed <strong>{result.claims_extracted.length}</strong> claims and{' '}
              <strong>{relevantCount}</strong> relevant evidence links. The verdict above was produced
              entirely by the deterministic evaluator under{' '}
              <span style={{ fontFamily: 'var(--font-mono)' }}>{result.methodology_version}</span> — the
              model cannot reach <strong>SUPPORTED</strong>, overturn a contradiction, or be steered by
              instructions hidden in the statement. Same inputs, same verdict, every time.
            </p>
          </Panel>
        </div>
      )}

      <ThreeWayComparison aiEnabled={aiEnabled} />
    </div>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="h-1 w-12 overflow-hidden rounded-full"
        style={{ background: 'var(--color-bg-surface)' }}
      >
        <span
          className="block h-full rounded-full"
          style={{ width: `${pct}%`, background: 'var(--color-accent-primary)' }}
        />
      </span>
      <span className="text-[10px] tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
        {pct}%
      </span>
    </span>
  )
}

/* ── Three-way evaluation ───────────────────────────────────────── */

function ThreeWayComparison({ aiEnabled }: { aiEnabled: boolean }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const runEval = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/defense/ai/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      if (res.ok) {
        setData(await res.json())
        // Real signal for the evaluator checklist: the three-way comparison
        // was actually run and returned, not just that the tab was opened.
        markGuideStepDone('ai-never-wins')
      }
    } finally {
      setLoading(false)
    }
  }

  if (!data) {
    return (
      <Panel title="Three-way evaluation" icon={BarChart3}>
        <EmptyState
          icon={BarChart3}
          title="Compare deterministic vs test-AI vs real LLM"
          hint="Runs the whole golden set through all three tracks and reports accuracy, macro-F1 and the safety metrics that matter — false-SUPPORTED rate and contradiction-miss rate."
          action={
            <div className="flex flex-col items-center gap-2.5">
              <button
                onClick={runEval}
                disabled={loading}
                className="neo-btn-primary mt-1 flex items-center gap-2 text-sm disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Evaluating…
                  </>
                ) : (
                  <>
                    <FlaskConical className="h-4 w-4" /> Run three-way evaluation
                  </>
                )}
              </button>
              {aiEnabled ? (
                <p
                  className="max-w-sm text-center text-[11px] leading-relaxed"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  {loading
                    ? 'Track C is calling a real LLM for each of the 50 cases, in parallel — expect roughly 30–60 seconds. The spinner staying up is normal, not a hang.'
                    : 'A real LLM provider is enabled, so this makes actual network calls for all 50 cases — expect roughly 30–60 seconds, not instant.'}
                </p>
              ) : (
                <p
                  className="max-w-sm text-center text-[11px] leading-relaxed"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  No real LLM is enabled right now, so this runs the deterministic engine and a stub AI only — a few seconds.
                </p>
              )}
            </div>
          }
        />
      </Panel>
    )
  }

  const tracks = [
    { label: 'Deterministic', sub: 'EvidenceGraph only', track: data.track_a_deterministic || {}, tone: 'var(--color-text-secondary)' },
    { label: 'Test AI', sub: 'stub + EvidenceGraph', track: data.track_b_test_ai || {}, tone: 'var(--color-accent-primary)' },
    { label: 'Real LLM', sub: 'model + EvidenceGraph', track: data.track_c_real_llm || {}, tone: 'var(--color-info)' },
  ]

  const baseline = data.track_a_deterministic || {}

  return (
    <div className="space-y-6">
      <Panel
        title="Three-way evaluation"
        icon={BarChart3}
        actions={
          <button onClick={runEval} disabled={loading} className="neo-btn flex items-center gap-1.5 text-xs">
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <FlaskConical className="h-3 w-3" />}
            Re-run
          </button>
        }
        footnote={`Dataset ${data.dataset_version ?? '—'} · ${data.total_cases ?? 0} cases`}
      >
        <div className="grid gap-4 md:grid-cols-3">
          {tracks.map(({ label, sub, track, tone }) => {
            const notConfigured = track.status === 'REAL_LLM_NOT_CONFIGURED'
            const fsr = track.safety?.false_supported_rate ?? 0
            const cmr = track.safety?.contradiction_miss_rate ?? 0
            return (
              <div
                key={label}
                className="rounded-xl p-4"
                style={{
                  background: `color-mix(in srgb, ${tone} 6%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${tone} 22%, transparent)`,
                }}
              >
                <div className="mb-3">
                  <div className="text-xs font-bold" style={{ color: tone }}>
                    {label}
                  </div>
                  <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                    {sub}
                  </div>
                </div>

                {notConfigured ? (
                  <div className="py-4 text-center">
                    <Pill tone="warning">Not configured</Pill>
                    <p className="mt-2 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                      Set AI_ENABLED=true and a provider key to run this track.
                    </p>
                  </div>
                ) : (
                  <>
                    <div
                      className="text-3xl font-extrabold leading-none tracking-tight"
                      style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-display)' }}
                    >
                      {((track.accuracy || 0) * 100).toFixed(0)}
                      <span className="text-base">%</span>
                    </div>
                    <div className="mb-3 text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-tertiary)' }}>
                      Accuracy · macro-F1 {((track.macro_f1 || 0) * 100).toFixed(0)}%
                    </div>
                    <SafetyRow label="False SUPPORTED" rate={fsr} />
                    <SafetyRow label="Contradiction miss" rate={cmr} />
                  </>
                )}
              </div>
            )
          })}
        </div>
      </Panel>

      {baseline.confusion_matrix && (
        <Panel title="Confusion matrix — deterministic baseline" icon={BarChart3}>
          <ConfusionMatrix matrix={baseline.confusion_matrix} />
        </Panel>
      )}

      {baseline.false_supported_cases?.length > 0 && (
        <Panel title="False-supported cases — safety review" icon={Shield}>
          <ul className="space-y-2">
            {baseline.false_supported_cases.map((c: any, i: number) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-2 rounded-xl p-3 text-xs"
                style={{
                  background: 'color-mix(in srgb, var(--color-danger) 8%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--color-danger) 22%, transparent)',
                }}
              >
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}>
                  {c.case_id}
                </span>
                <span style={{ color: 'var(--color-text-tertiary)' }}>expected</span>
                <VerdictBadge label={c.expected} />
                <span style={{ color: 'var(--color-text-tertiary)' }}>got</span>
                <VerdictBadge label={c.predicted} />
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  )
}

function SafetyRow({ label, rate }: { label: string; rate: number }) {
  const safe = rate === 0
  const color = safe ? 'var(--color-success)' : 'var(--color-danger)'
  return (
    <div
      className="mt-1.5 flex items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px]"
      style={{ background: `color-mix(in srgb, ${color} 10%, transparent)` }}
    >
      <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <span className="font-bold tabular-nums" style={{ color }}>
        {(rate * 100).toFixed(0)}%
      </span>
    </div>
  )
}

export function ConfusionMatrix({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const labels = VERDICTS.filter(l => l in matrix)
  const max = Math.max(1, ...labels.flatMap(a => labels.map(b => matrix[a]?.[b] || 0)))

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th
              className="px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-[0.1em]"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              Actual ↓ / Predicted →
            </th>
            {labels.map(l => (
              <th key={l} className="px-1 py-1 text-center">
                <span
                  className="text-[10px] font-bold uppercase tracking-wide"
                  style={{ color: verdictMeta(l).color }}
                >
                  {verdictMeta(l).short}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map(actual => (
            <tr key={actual}>
              <td className="px-2 py-1">
                <span
                  className="text-[11px] font-semibold"
                  style={{ color: verdictMeta(actual).color }}
                >
                  {verdictMeta(actual).short}
                </span>
              </td>
              {labels.map(pred => {
                const val = matrix[actual]?.[pred] || 0
                const diag = actual === pred
                const tone = diag ? 'var(--color-success)' : 'var(--color-danger)'
                return (
                  <td key={pred} className="p-0">
                    <div
                      className="rounded-lg py-2.5 text-center text-sm font-bold tabular-nums"
                      style={{
                        background:
                          val > 0
                            ? `color-mix(in srgb, ${tone} ${8 + (val / max) * 32}%, transparent)`
                            : 'var(--color-bg-surface)',
                        color: val > 0 ? tone : 'var(--color-text-tertiary)',
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
      <p className="mt-3 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
        Diagonal cells are correct predictions; everything off-diagonal is an error.
      </p>
    </div>
  )
}
