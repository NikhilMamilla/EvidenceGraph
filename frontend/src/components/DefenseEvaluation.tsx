/**
 * Defense Eval — the measured Track-02 result.
 *
 * Seeds/inspects the frozen golden dataset, runs the deterministic reference
 * evaluator over it, and reports accuracy, macro-F1, per-class precision/recall
 * and the confusion matrix. No AI runs here — that lives in AI Verify.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  Database,
  FileText,
  Grid3x3,
  History,
  Layers,
  Lock,
  LockOpen,
  Loader2,
  Play,
  Scale,
  Sprout,
  Target,
  X,
} from 'lucide-react'

import { EmptyState, LoadingState, PageHeader, Panel, Pill, Stat, SubTabs } from './ui'
import { VERDICTS, VerdictBadge, verdictMeta } from './defense/verdict'
import { ConfusionMatrix } from './DefenseVerification'

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

type TabKey = 'overview' | 'cases' | 'runs' | 'matrix'

const TABS: { key: TabKey; label: string; icon: typeof Target }[] = [
  { key: 'overview', label: 'Overview', icon: Target },
  { key: 'cases', label: 'Golden cases', icon: FileText },
  { key: 'runs', label: 'Runs', icon: History },
  { key: 'matrix', label: 'Confusion matrix', icon: Grid3x3 },
]

export default function DefenseEvaluation() {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
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
    } catch {
      /* panels fall back to empty states */
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

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
        setLastEvalResult(await res.json())
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
  const accuracy = latestRun?.metrics?.accuracy ?? latestRun?.accuracy ?? null
  const macroF1 = latestRun?.metrics?.macro_f1 ?? latestRun?.macro_f1 ?? null

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Scale}
        title="Defense Verification Evaluation"
        subtitle="Deterministic reference evaluator over the frozen golden set"
        actions={
          <>
            <button
              onClick={seedDataset}
              disabled={seeding}
              className="neo-btn flex items-center gap-2 text-xs disabled:opacity-50"
            >
              {seeding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sprout className="h-3.5 w-3.5" />}
              {seeding ? 'Seeding…' : 'Seed golden cases'}
            </button>
            <button
              onClick={runEvaluation}
              disabled={evaluating || !ds}
              className="neo-btn-primary flex items-center gap-2 text-xs disabled:opacity-50"
            >
              {evaluating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {evaluating ? 'Evaluating…' : 'Run evaluation'}
            </button>
          </>
        }
      />

      {/* Headline metrics — always visible, so the result is never buried */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Accuracy"
          value={accuracy !== null ? `${(accuracy * 100).toFixed(1)}%` : '—'}
          hint={latestRun ? `${latestRun.evaluated_cases ?? 0} cases evaluated` : 'run an evaluation'}
          tone="success"
          icon={Target}
        />
        <Stat
          label="Macro F1"
          value={macroF1 !== null ? `${(macroF1 * 100).toFixed(1)}%` : '—'}
          hint="balanced across all four classes"
          tone="accent"
          icon={Layers}
        />
        <Stat
          label="Dataset"
          value={ds?.total_cases ?? '—'}
          hint={ds?.dataset_version ?? 'not seeded'}
          icon={Database}
        />
        <Stat
          label="Split protocol"
          value={ds?.is_frozen ? 'Frozen' : 'Open'}
          hint={ds?.is_frozen ? 'held-out, immutable' : 'not yet frozen'}
          tone={ds?.is_frozen ? 'success' : 'warning'}
          icon={ds?.is_frozen ? Lock : LockOpen}
        />
      </div>

      <SubTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'overview' && (
        <OverviewTab ds={ds} latestRun={latestRun} />
      )}

      {activeTab === 'cases' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <CasesList onSelectCase={loadCase} selectedId={selectedCase?.case_id} />
          {selectedCase ? (
            <CaseDetailView caseData={selectedCase} onClose={() => setSelectedCase(null)} />
          ) : (
            <Panel title="Case detail" icon={FileText}>
              <EmptyState icon={FileText} title="Select a case" hint="Pick a golden case to see its claims, evidence links and human ground-truth label." />
            </Panel>
          )}
        </div>
      )}

      {activeTab === 'runs' && <RunsTab runs={runs} />}

      {activeTab === 'matrix' && (
        <Panel title="Confusion matrix" icon={Grid3x3}>
          {latestRun?.confusion_matrix ? (
            <ConfusionMatrix matrix={latestRun.confusion_matrix} />
          ) : (
            <EmptyState icon={Grid3x3} title="No evaluation results yet" hint="Run an evaluation to populate the matrix." />
          )}
        </Panel>
      )}

      <Panel title="Methodology" icon={Scale}>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetaItem label="Evaluator" value={ds?.methodology_version ?? 'REF_EVAL_V2'} />
          <MetaItem label="Scope" value="DELIVERY_NOT_RECEIVED" />
          <MetaItem label="AI layer" value="Not used here — see AI Verify" />
          <MetaItem
            label="Dataset fingerprint"
            value={ds?.dataset_fingerprint ? `${ds.dataset_fingerprint.slice(0, 16)}…` : '—'}
          />
        </dl>
      </Panel>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-tertiary)' }}>
        {label}
      </dt>
      <dd className="truncate text-xs" style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {value}
      </dd>
    </div>
  )
}

/* ── Overview ───────────────────────────────────────────────────── */

function OverviewTab({ ds, latestRun }: { ds?: Dataset; latestRun: any }) {
  if (!ds) {
    return (
      <Panel title="Dataset" icon={Database}>
        <EmptyState
          icon={Sprout}
          title="No dataset seeded yet"
          hint="Seed the 20 golden delivery-dispute cases to begin. Seeding is idempotent — running it twice changes nothing."
        />
      </Panel>
    )
  }

  return (
    <div className="space-y-6">
      <Panel title="Label distribution" icon={Layers} footnote="Human-labelled ground truth across the frozen set.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {VERDICTS.map(label => {
            const count = ds.label_counts?.[label] ?? 0
            const m = verdictMeta(label)
            const Icon = m.icon
            const pct = ds.total_cases ? Math.round((count / ds.total_cases) * 100) : 0
            return (
              <div
                key={label}
                className="rounded-xl p-4"
                style={{
                  background: `color-mix(in srgb, ${m.color} 7%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${m.color} 22%, transparent)`,
                }}
              >
                <Icon className="mb-2 h-4 w-4" style={{ color: m.color }} />
                <div
                  className="text-2xl font-extrabold leading-none"
                  style={{ color: m.color, fontFamily: 'var(--font-display)' }}
                >
                  {count}
                </div>
                <div className="mt-1.5 text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  {m.short}
                </div>
                <div className="mt-2 h-1 overflow-hidden rounded-full" style={{ background: 'var(--color-bg-surface)' }}>
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: m.color }} />
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Source distribution" icon={Database}>
          <DistributionList counts={ds.source_counts} total={ds.total_cases} />
        </Panel>
        <Panel title="Split distribution" icon={Layers}>
          <DistributionList counts={ds.split_counts} total={ds.total_cases} />
        </Panel>
      </div>

      {latestRun?.metrics?.per_class && (
        <Panel
          title="Per-class performance"
          icon={Target}
          footnote={`Small-N evaluation on ${latestRun.total_cases ?? latestRun.evaluated_cases ?? 0} controlled cases — confidence intervals are wide. This does not prove production performance.`}
        >
          <div className="space-y-2.5">
            {VERDICTS.filter(l => latestRun.metrics.per_class[l]).map(label => {
              const d = latestRun.metrics.per_class[label]
              const m = verdictMeta(label)
              return (
                <div key={label} className="neo-inset rounded-xl p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <VerdictBadge label={label} />
                    <div className="flex items-center gap-3 text-[11px] tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>
                      <span>P {fmtPct(d.precision)}</span>
                      <span>R {fmtPct(d.recall)}</span>
                      <span style={{ color: 'var(--color-text-primary)', fontWeight: 700 }}>F1 {fmtPct(d.f1)}</span>
                      <span style={{ color: 'var(--color-text-tertiary)' }}>n={d.support}</span>
                    </div>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full" style={{ background: 'var(--color-bg-surface)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${(d.f1 || 0) * 100}%`, background: m.color }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </Panel>
      )}
    </div>
  )
}

function fmtPct(v: number | null | undefined) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`
}

function DistributionList({ counts, total }: { counts?: Record<string, number>; total: number }) {
  const entries = Object.entries(counts ?? {})
  if (entries.length === 0) {
    return <EmptyState title="No breakdown available" />
  }
  return (
    <ul className="space-y-2.5">
      {entries.map(([key, count]) => {
        const pct = total ? Math.round((count / total) * 100) : 0
        return (
          <li key={key}>
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="truncate text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {key.replace(/_/g, ' ')}
              </span>
              <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: 'var(--color-text-primary)' }}>
                {count}
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full" style={{ background: 'var(--color-bg-surface)' }}>
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--color-accent-primary)' }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/* ── Cases ──────────────────────────────────────────────────────── */

function CasesList({
  onSelectCase,
  selectedId,
}: {
  onSelectCase: (id: string) => void
  selectedId?: string
}) {
  const [cases, setCases] = useState<
    { case_id: string; dispute_reason: string; case_source: string; status: string }[]
  >([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/defense/evaluation/datasets/EG-DEFENSE-1.0')
      .then(r => r.json())
      .then(d => setCases(d.cases || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <Panel title={`Golden cases (${cases.length})`} icon={FileText} bodyClassName="p-3">
      {loading ? (
        <LoadingState label="Loading cases…" />
      ) : cases.length === 0 ? (
        <EmptyState icon={Sprout} title="No cases" hint="Seed the golden dataset first." />
      ) : (
        <ul className="max-h-[560px] space-y-1.5 overflow-y-auto pr-1">
          {cases.map(c => {
            const active = c.case_id === selectedId
            return (
              <li key={c.case_id}>
                <button
                  onClick={() => onSelectCase(c.case_id)}
                  className="w-full rounded-xl p-3 text-left transition-all"
                  style={{
                    background: active ? 'var(--color-accent-glow)' : 'var(--color-bg-surface)',
                    border: `1px solid ${active ? 'var(--color-border-accent)' : 'var(--color-border)'}`,
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="text-xs font-bold"
                      style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}
                    >
                      {c.case_id}
                    </span>
                    <Pill tone="neutral">{c.case_source.replace(/_/g, ' ')}</Pill>
                  </div>
                  <p className="mt-1 truncate text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                    {c.dispute_reason}
                  </p>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}

function CaseDetailView({ caseData, onClose }: { caseData: CaseDetail; onClose: () => void }) {
  return (
    <Panel
      title={caseData.case_id}
      icon={FileText}
      actions={
        <button onClick={onClose} className="neo-btn flex items-center gap-1 text-[11px]">
          <X className="h-3 w-3" /> Close
        </button>
      }
    >
      <div className="space-y-4">
        <dl className="grid gap-4 sm:grid-cols-2">
          <MetaItem label="Dispute reason" value={caseData.dispute_reason} />
          <MetaItem label="Source" value={caseData.case_source.replace(/_/g, ' ')} />
        </dl>

        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-tertiary)' }}>
            Description
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
            {caseData.case_description}
          </p>
        </div>

        {caseData.ground_truth && (
          <div
            className="rounded-xl p-3"
            style={{
              background: `color-mix(in srgb, ${verdictMeta(caseData.ground_truth.label).color} 8%, transparent)`,
              border: `1px solid color-mix(in srgb, ${verdictMeta(caseData.ground_truth.label).color} 24%, transparent)`,
            }}
          >
            <div className="mb-1.5 flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-tertiary)' }}>
                Ground truth
              </span>
              <VerdictBadge label={caseData.ground_truth.label} />
            </div>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {caseData.ground_truth.rationale}
            </p>
          </div>
        )}

        <div>
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-tertiary)' }}>
            Claims ({caseData.claims.length})
          </div>
          <ul className="space-y-2">
            {caseData.claims.map(claim => (
              <li key={claim.claim_id} className="neo-inset rounded-xl p-3">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-bold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-accent)' }}>
                    {claim.claim_type}
                  </span>
                </div>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                  {claim.claim_text}
                </p>
                {claim.evidence_links.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {claim.evidence_links.map((l, i) => (
                      <Pill key={i} tone={l.link_type === 'SUPPORTING' ? 'success' : 'danger'}>
                        {l.link_type.toLowerCase()}
                      </Pill>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Panel>
  )
}

/* ── Runs ───────────────────────────────────────────────────────── */

function RunsTab({ runs }: { runs: EvalRun[] }) {
  if (runs.length === 0) {
    return (
      <Panel title="Evaluation runs" icon={History}>
        <EmptyState icon={Play} title="No runs yet" hint="Run an evaluation to record accuracy, macro-F1 and a results fingerprint." />
      </Panel>
    )
  }

  return (
    <Panel title={`Evaluation runs (${runs.length})`} icon={History} bodyClassName="p-3">
      <ul className="space-y-2">
        {runs.map(run => (
          <li key={run.run_id} className="neo-inset rounded-xl p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-xs font-bold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}>
                    {run.run_id}
                  </span>
                  <Pill tone={run.status === 'COMPLETED' ? 'success' : 'warning'}>{run.status}</Pill>
                </div>
                <p className="mt-1 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  {run.evaluated_cases} evaluated · {run.correct_predictions} correct · {run.dataset_version}
                </p>
              </div>
              <div className="flex items-center gap-4 text-right">
                <div>
                  <div className="text-sm font-extrabold tabular-nums" style={{ color: 'var(--color-success)' }}>
                    {(run.accuracy * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-tertiary)' }}>
                    Accuracy
                  </div>
                </div>
                {run.macro_f1 !== null && (
                  <div>
                    <div className="text-sm font-extrabold tabular-nums" style={{ color: 'var(--color-text-accent)' }}>
                      {(run.macro_f1 * 100).toFixed(1)}%
                    </div>
                    <div className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-tertiary)' }}>
                      Macro F1
                    </div>
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
