/**
 * Shared UI primitives.
 *
 * Every tab composes these so padding, heading hierarchy, gaps, badges and
 * empty states are identical across the app. Colours come from the CSS custom
 * properties in index.css, so everything is theme-aware for free.
 */

import type { ElementType, ReactNode } from 'react'
import { AlertCircle, Inbox, Loader2 } from 'lucide-react'

/* ── Page header ─────────────────────────────────────────────────────
   The single title block at the top of a tab. */
export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon: ElementType
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className="glass-card-elevated premium-ring p-6 sm:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3.5">
          <span
            className="neo-pressed shrink-0 rounded-xl p-2.5"
            style={{ background: 'var(--color-accent-glow)' }}
          >
            <Icon className="h-5 w-5" style={{ color: 'var(--color-text-accent)' }} />
          </span>
          <div className="min-w-0">
            <h2
              className="truncate text-lg font-bold tracking-tight sm:text-xl"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {title}
            </h2>
            {subtitle && (
              <p className="mt-0.5 text-xs sm:text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2.5">{actions}</div>}
      </div>
    </div>
  )
}

/* ── Panel ───────────────────────────────────────────────────────────
   The standard content card. One padding scale everywhere. */
export function Panel({
  title,
  icon: Icon,
  actions,
  footnote,
  children,
  className = '',
  bodyClassName = '',
}: {
  title?: string
  icon?: ElementType
  actions?: ReactNode
  footnote?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`glass-card flex flex-col overflow-hidden ${className}`}>
      {title && (
        <header
          className="flex items-center justify-between gap-3 px-5 py-3.5"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex min-w-0 items-center gap-2.5">
            {Icon && (
              <Icon className="h-4 w-4 shrink-0" style={{ color: 'var(--color-text-accent)' }} />
            )}
            <h3
              className="truncate text-[13px] font-bold uppercase tracking-[0.08em]"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {title}
            </h3>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`flex-1 p-5 ${bodyClassName}`}>{children}</div>
      {footnote && (
        <footer
          className="px-5 py-3 text-[11px]"
          style={{ borderTop: '1px solid var(--color-border)', color: 'var(--color-text-tertiary)' }}
        >
          {footnote}
        </footer>
      )}
    </section>
  )
}

/* ── Stat ────────────────────────────────────────────────────────────
   One metric tile. `tone` maps to the semantic palette. */
export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'

const TONE_VAR: Record<Tone, string> = {
  neutral: 'var(--color-text-primary)',
  accent: 'var(--color-text-accent)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  info: 'var(--color-info)',
}

export function Stat({
  label,
  value,
  hint,
  tone = 'neutral',
  icon: Icon,
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: Tone
  icon?: ElementType
}) {
  return (
    <div className="metric-card p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        {Icon && <Icon className="h-3 w-3" style={{ color: 'var(--color-text-tertiary)' }} />}
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.1em]"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-xl font-extrabold leading-none tracking-tight sm:text-2xl"
        style={{ color: TONE_VAR[tone], fontFamily: 'var(--font-display)' }}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-1.5 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
          {hint}
        </div>
      )}
    </div>
  )
}

/* ── Pill ────────────────────────────────────────────────────────────
   Small status/label chip. */
export function Pill({
  children,
  tone = 'neutral',
  icon: Icon,
  mono = false,
}: {
  children: ReactNode
  tone?: Tone
  icon?: ElementType
  mono?: boolean
}) {
  const color = TONE_VAR[tone]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
        mono ? 'font-mono' : ''
      }`}
      style={{
        color,
        background: tone === 'neutral' ? 'var(--color-bg-surface)' : `color-mix(in srgb, ${color} 12%, transparent)`,
        border: `1px solid ${tone === 'neutral' ? 'var(--color-border)' : `color-mix(in srgb, ${color} 28%, transparent)`}`,
      }}
    >
      {Icon && <Icon className="h-3 w-3 shrink-0" />}
      {children}
    </span>
  )
}

/* ── Sub-tabs ────────────────────────────────────────────────────────
   In-section navigation (Payments splits its panels across these). */
export function SubTabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: T; label: string; icon?: ElementType; count?: number }[]
  active: T
  onChange: (key: T) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tabs.map(t => {
        const isActive = t.key === active
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-current={isActive}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all duration-300 ${
              isActive ? 'tab-glass-active' : 'tab-glass'
            }`}
          >
            {t.icon && <t.icon className="h-3.5 w-3.5" />}
            {t.label}
            {typeof t.count === 'number' && (
              <span
                className="rounded-full px-1.5 py-0.5 text-[10px] font-bold"
                style={{
                  background: 'var(--color-bg-elevated, rgba(255,255,255,0.06))',
                  color: 'var(--color-text-tertiary)',
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ── Empty / loading / error states ──────────────────────────────────
   One look for "nothing here yet" across the whole app. */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  hint,
  action,
}: {
  icon?: ElementType
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="neo-inset flex flex-col items-center gap-3 rounded-xl px-6 py-12 text-center">
      <span className="neo-pressed rounded-2xl p-3.5" style={{ background: 'var(--color-accent-glow)' }}>
        <Icon className="h-6 w-6" style={{ color: 'var(--color-text-accent)' }} />
      </span>
      <p className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
        {title}
      </p>
      {hint && (
        <p className="max-w-md text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
          {hint}
        </p>
      )}
      {action}
    </div>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-12">
      <Loader2 className="h-4 w-4 animate-spin" style={{ color: 'var(--color-text-accent)' }} />
      <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </span>
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="flex items-start gap-3 rounded-xl p-4"
      style={{
        background: 'color-mix(in srgb, var(--color-danger) 10%, transparent)',
        border: '1px solid color-mix(in srgb, var(--color-danger) 25%, transparent)',
      }}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: 'var(--color-danger)' }} />
      <p className="text-xs leading-relaxed" style={{ color: 'var(--color-danger)' }}>
        {message}
      </p>
    </div>
  )
}

/* ── Key/value row ───────────────────────────────────────────────────
   Used heavily by the payment detail panels. */
export function Field({
  label,
  value,
  mono = false,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="min-w-0">
      <dt
        className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]"
        style={{ color: 'var(--color-text-tertiary)' }}
      >
        {label}
      </dt>
      <dd
        className={`truncate text-sm font-medium ${mono ? 'font-mono text-xs' : ''}`}
        style={{ color: 'var(--color-text-primary)' }}
      >
        {value ?? '—'}
      </dd>
    </div>
  )
}
