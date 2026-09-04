/**
 * EvaluatorGuide — the landing tab.
 *
 * A self-paced, ordered checklist for a Razorpay evaluator opening this app
 * cold: what to check, in what order, and what "good" looks like at each
 * step. Progress is a per-viewer convenience only (localStorage) — it never
 * gates anything and resets freely.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircle2,
  Circle,
  RotateCcw,
  ArrowRight,
  ExternalLink,
  Activity,
  Shield,
  Scale,
  ShieldCheck,
  GitBranch,
  BookOpen,
  Sparkles,
  PartyPopper,
} from 'lucide-react'
import { PageHeader, Panel, Pill } from './ui'
import type { TabKey } from '../App'

const REPO_URL = 'https://github.com/NikhilMamilla/EvidenceGraph'
const STORAGE_KEY = 'eg:evaluator-checklist:v1'

type Step = {
  id: string
  title: string
  body: string
  lookFor: string
  nav?: { tab: TabKey; label: string }
  external?: { href: string; label: string }
}

const STEPS: Step[] = [
  {
    id: 'health',
    title: 'Confirm the stack is actually up',
    body: 'Before anything else — check that the backend, database, Redis, and the webhook worker are real and healthy, not mocked for the demo.',
    lookFor: 'All services green. The webhook counter reads a persisted count from the database, so it survives a restart — it is not an in-process number that resets to zero.',
    nav: { tab: 'operations', label: 'Open Operations' },
  },
  {
    id: 'headline-case',
    title: 'Run the one case that explains the whole project',
    body: "Open the demo dropdown and run GOLDEN_007. The merchant's claim: \"The package was delivered successfully by our courier.\" Payment ID matches. Order ID matches — two signals agree with the story. But the carrier's own API says the delivery failed, and that one authoritative contradiction overrides both agreeing signals.",
    lookFor: 'Verdict: CONTRADICTED — not a blended "mostly fine." Watch the five-stage pipeline run (claim extraction → evidence matching → ID validation → deterministic evaluation → final verdict), then check the supporting/contradicting evidence IDs and the SHA-256 decision trace under the verdict.',
    nav: { tab: 'defense-ai', label: 'Open AI Verify' },
  },
  {
    id: 'ai-never-wins',
    title: 'Confirm the AI never overrides the rules',
    body: 'Same tab — scroll down to the three-way comparison. It runs the full golden set through three independent pipelines: deterministic-only, a deterministic stub "AI," and (if enabled) a real LLM.',
    lookFor: 'The "False SUPPORTED" and "Contradiction miss" rows read 0% on every track, regardless of which AI provider is behind it — because the deterministic engine has final authority no matter what the AI proposes.',
    nav: { tab: 'defense-ai', label: 'Open AI Verify' },
  },
  {
    id: 'scale',
    title: 'See it hold up at scale, not just on one case',
    body: 'One convincing example is not a proof. This is: a 50-case frozen golden set, held out from all development, with two independent label passes checked against each other.',
    lookFor: 'Accuracy, macro-F1, a "0" on False-SUPPORTED, Cohen\'s κ (~0.87, "almost perfect" agreement), and the confusion matrix. Click "Run evaluation" if the numbers are not already there.',
    nav: { tab: 'defense', label: 'Open Defense Eval' },
  },
  {
    id: 'platform',
    title: 'See the platform underneath it',
    body: 'The verifier is not standalone — it sits on a real evidence-ingestion pipeline: Razorpay webhooks in, canonical entities out, cross-checked and reconciled. Open a real payment and look at its evidence.',
    lookFor: 'Real evidence facts, provenance, and an integrity score computed from actual ingested data — not placeholder numbers.',
    nav: { tab: 'payments', label: 'Open Payments' },
  },
  {
    id: 'scope',
    title: 'Check the scope discipline',
    body: 'This is defense-only, by design. No fraud probability or risk score anywhere in this app feeds the verdict — the Fraud, Risk, Revenue, and Merchant Risk tabs are read-only analytics, never inputs to the verifier. Nothing here auto-submits to a card network.',
    lookFor: 'The verdict path only ever depends on the evidence graph for the case being checked.',
  },
  {
    id: 'source',
    title: 'Check the code and the numbers yourself',
    body: 'Everything above is reproducible from a clean clone: one command brings up the whole stack, seeds the golden set, and freezes it.',
    lookFor: 'docker compose up --build — Postgres, Redis, backend, and this frontend, together.',
    external: { href: REPO_URL, label: 'View source on GitHub' },
  },
]

function readDone(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function EvaluatorGuide({ onNavigate }: { onNavigate: (tab: TabKey) => void }) {
  const [done, setDone] = useState<Record<string, boolean>>(() => readDone())

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(done))
    } catch {
      /* private mode — fine, just don't persist */
    }
  }, [done])

  const toggle = useCallback((id: string) => {
    setDone(prev => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const markDone = useCallback((id: string) => {
    setDone(prev => (prev[id] ? prev : { ...prev, [id]: true }))
  }, [])

  const reset = useCallback(() => setDone({}), [])

  const completedCount = STEPS.filter(s => done[s.id]).length
  const allDone = completedCount === STEPS.length

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Sparkles}
        title="Start here — evaluator checklist"
        subtitle="A pre-submission chargeback-defense verifier for Razorpay Track 02: AI Risk Manager. Seven steps, in order, so you see everything that matters in one pass."
        actions={
          <>
            <Pill tone={allDone ? 'success' : 'accent'} icon={CheckCircle2}>
              {completedCount} / {STEPS.length} complete
            </Pill>
            {completedCount > 0 && (
              <button
                type="button"
                onClick={reset}
                className="tab-glass flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
              </button>
            )}
          </>
        }
      />

      <div
        className="h-1.5 w-full overflow-hidden rounded-full"
        style={{ background: 'var(--color-bg-surface)' }}
        role="progressbar"
        aria-valuenow={completedCount}
        aria-valuemin={0}
        aria-valuemax={STEPS.length}
      >
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{
            width: `${(completedCount / STEPS.length) * 100}%`,
            background: allDone ? 'var(--color-success)' : 'var(--gradient-primary)',
          }}
        />
      </div>

      {allDone && (
        <div
          className="glass-card premium-ring flex animate-scale-in items-center gap-3.5 p-5"
          style={{
            background: 'color-mix(in srgb, var(--color-success) 8%, transparent)',
            border: '1px solid color-mix(in srgb, var(--color-success) 28%, transparent)',
          }}
        >
          <span className="neo-pressed shrink-0 rounded-xl p-2.5" style={{ background: 'color-mix(in srgb, var(--color-success) 18%, transparent)' }}>
            <PartyPopper className="h-5 w-5" style={{ color: 'var(--color-success)' }} />
          </span>
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--color-text-primary)' }}>
              All seven checks complete.
            </p>
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              You've seen the deterministic verdict, the safety guarantee, the measured accuracy, and the platform underneath it. That's the whole project.
            </p>
          </div>
        </div>
      )}

      <Panel title="The one-sentence version" icon={ShieldCheck}>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
          Payment systems can tell you how risky a transaction looks. They don't necessarily tell
          you how trustworthy the evidence behind that risk assessment actually is. This app reads
          a merchant's defense statement and evidence for a delivery dispute, and answers —
          deterministically, with a full audit trail — whether that evidence actually supports the
          claim, before it ever reaches Razorpay or the bank.
        </p>
      </Panel>

      <div className="space-y-4">
        {STEPS.map((step, i) => {
          const isDone = !!done[step.id]
          const autoMarks = !!(step.nav || step.external)
          return (
            <div
              key={step.id}
              className="glass-card flex flex-col gap-4 p-5 transition-all duration-300 sm:flex-row sm:items-start"
              style={{
                opacity: isDone ? 0.65 : 1,
                borderColor: isDone
                  ? 'color-mix(in srgb, var(--color-success) 30%, var(--color-border))'
                  : undefined,
              }}
            >
              <button
                type="button"
                onClick={() => toggle(step.id)}
                aria-pressed={isDone}
                aria-label={isDone ? 'Mark step incomplete' : 'Mark step complete'}
                className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-center"
              >
                <span
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs font-bold tabular-nums"
                  style={{
                    background: 'var(--color-accent-glow)',
                    color: 'var(--color-text-accent)',
                  }}
                >
                  {i + 1}
                </span>
                {isDone ? (
                  <CheckCircle2 key="done" className="h-5 w-5 animate-scale-in" style={{ color: 'var(--color-success)' }} />
                ) : (
                  <Circle className="h-5 w-5" style={{ color: 'var(--color-text-tertiary)' }} />
                )}
              </button>

              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3
                    className="text-sm font-bold tracking-tight"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {step.title}
                  </h3>
                  {autoMarks && !isDone && (
                    <span
                      className="text-[10px] font-medium italic"
                      style={{ color: 'var(--color-text-tertiary)' }}
                    >
                      auto-checks when you open it
                    </span>
                  )}
                </div>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                  {step.body}
                </p>
                <div
                  className="neo-inset rounded-lg px-3 py-2.5 text-[11px] leading-relaxed"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  <span className="font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-text-accent)' }}>
                    Look for —{' '}
                  </span>
                  {step.lookFor}
                </div>

                {step.nav && (
                  <button
                    type="button"
                    onClick={() => {
                      onNavigate(step.nav!.tab)
                      markDone(step.id)
                    }}
                    className="tab-glass-active mt-1 inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
                  >
                    {step.nav.label}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                )}
                {step.external && (
                  <a
                    href={step.external.href}
                    target="_blank"
                    rel="noreferrer noopener"
                    onClick={() => markDone(step.id)}
                    className="tab-glass mt-1 inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {step.external.label}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <Panel title="Everything else" icon={Scale}>
        <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
          The remaining tabs — Live Stream, Notifications, Evidence Graph, Fraud Detection, Failure
          Intel, Revenue, Merchant Risk, Investigation — are the evidence platform this verifier is
          built on top of. Real ingestion and reconciliation, not part of the graded Track-02
          deliverable, but there to show the verifier isn't a standalone script.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer noopener"
            className="tab-glass inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
          >
            <BookOpen className="h-3.5 w-3.5" />
            API reference (Swagger)
            <ExternalLink className="h-3 w-3 opacity-60" />
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="tab-glass inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
          >
            <GitBranch className="h-3.5 w-3.5" />
            Source on GitHub
            <ExternalLink className="h-3 w-3 opacity-60" />
          </a>
          <a
            href="/api/v1/health/ready"
            target="_blank"
            rel="noreferrer noopener"
            className="tab-glass inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
          >
            <Activity className="h-3.5 w-3.5" />
            Raw health probe
            <ExternalLink className="h-3 w-3 opacity-60" />
          </a>
          <a
            href={`${REPO_URL}/blob/main/docs/limitations.md`}
            target="_blank"
            rel="noreferrer noopener"
            className="tab-glass inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold"
          >
            <Shield className="h-3.5 w-3.5" />
            Known limitations
            <ExternalLink className="h-3 w-3 opacity-60" />
          </a>
        </div>
      </Panel>
    </div>
  )
}
