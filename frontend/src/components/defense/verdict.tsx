/**
 * The four-class verdict vocabulary, in one place.
 *
 * Icons are lucide (never emoji) and colours come from the design tokens, so
 * verdicts read identically in Defense Eval, AI Verify, and anywhere else.
 */

import type { ElementType, ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'

export const VERDICTS = [
  'SUPPORTED',
  'INSUFFICIENT_EVIDENCE',
  'CONTRADICTED',
  'UNKNOWN',
] as const

export type Verdict = (typeof VERDICTS)[number]

interface VerdictMeta {
  icon: ElementType
  color: string
  short: string
  blurb: string
}

export const VERDICT_META: Record<string, VerdictMeta> = {
  SUPPORTED: {
    icon: CheckCircle2,
    color: 'var(--color-success)',
    short: 'Supported',
    blurb: 'Backed by authoritative, temporally valid, non-conflicting, independent evidence.',
  },
  INSUFFICIENT_EVIDENCE: {
    icon: AlertTriangle,
    color: 'var(--color-warning)',
    short: 'Insufficient',
    blurb: 'No contradiction, but a required evidence type is missing or all evidence shares one source.',
  },
  CONTRADICTED: {
    icon: XCircle,
    color: 'var(--color-danger)',
    short: 'Contradicted',
    blurb: 'An authoritative source materially conflicts with the claim.',
  },
  UNKNOWN: {
    icon: HelpCircle,
    color: 'var(--color-text-tertiary)',
    short: 'Unknown',
    blurb: 'Not enough information to determine support or contradiction.',
  },
}

export function verdictMeta(label: string | null | undefined): VerdictMeta {
  return VERDICT_META[label ?? ''] ?? VERDICT_META.UNKNOWN
}

export function humanVerdict(label: string): string {
  return label.replace(/_/g, ' ')
}

/** Inline verdict chip — for tables, lists and matrix headers. */
export function VerdictBadge({
  label,
  size = 'sm',
}: {
  label: string
  size?: 'sm' | 'md'
}) {
  const meta = verdictMeta(label)
  const Icon = meta.icon
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${
        size === 'md' ? 'px-3 py-1.5 text-xs' : 'px-2.5 py-1 text-[11px]'
      }`}
      style={{
        color: meta.color,
        background: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 30%, transparent)`,
      }}
    >
      <Icon className={size === 'md' ? 'h-3.5 w-3.5' : 'h-3 w-3'} />
      {humanVerdict(label)}
    </span>
  )
}

/** The large verdict statement shown after a verification run. */
export function VerdictHero({
  label,
  rationale,
  meta: extra,
}: {
  label: string
  rationale?: string
  meta?: ReactNode
}) {
  const m = verdictMeta(label)
  const Icon = m.icon
  return (
    <div
      className="glass-card-elevated relative overflow-hidden p-6 sm:p-8"
      style={{ border: `1px solid color-mix(in srgb, ${m.color} 26%, transparent)` }}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-50"
        style={{ background: `radial-gradient(60% 100% at 50% 0%, color-mix(in srgb, ${m.color} 22%, transparent), transparent)` }}
      />
      <div className="relative flex flex-col items-center gap-3 text-center">
        <span
          className="rounded-2xl p-3"
          style={{
            background: `color-mix(in srgb, ${m.color} 14%, transparent)`,
            border: `1px solid color-mix(in srgb, ${m.color} 28%, transparent)`,
          }}
        >
          <Icon className="h-7 w-7" style={{ color: m.color }} />
        </span>

        <div
          className="text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          Final verdict
        </div>

        <div
          className="text-2xl font-extrabold tracking-tight sm:text-3xl"
          style={{ color: m.color, fontFamily: 'var(--font-display)' }}
        >
          {humanVerdict(label)}
        </div>

        <p
          className="max-w-2xl text-xs leading-relaxed sm:text-sm"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {rationale || m.blurb}
        </p>

        {extra && <div className="mt-1">{extra}</div>}
      </div>
    </div>
  )
}
