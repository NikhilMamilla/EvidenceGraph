/**
 * SectionIntro — a compact "what / how / why" panel shown at the top of every tab.
 *
 * Collapsible; the collapsed/expanded choice is remembered per section in
 * localStorage so a returning viewer isn't nagged. Purely presentational.
 */

import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'

export type IntroKind = 'deliverable' | 'platform'

export interface SectionIntroProps {
  /** stable key used for the localStorage collapse memory */
  id: string
  title: string
  /** one-liner shown next to the title, always visible */
  tagline: string
  what: string
  how: string
  why: string
  kind?: IntroKind
}

const KIND_LABEL: Record<IntroKind, string> = {
  deliverable: 'Track-02 deliverable',
  platform: 'Platform context',
}

function readCollapsed(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

export function SectionIntro({ id, title, tagline, what, how, why, kind = 'platform' }: SectionIntroProps) {
  const storageKey = `eg:intro:${id}:collapsed`
  const [collapsed, setCollapsed] = useState<boolean>(() => readCollapsed(storageKey))

  useEffect(() => {
    setCollapsed(readCollapsed(storageKey))
  }, [storageKey])

  const toggle = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev
      try {
        localStorage.setItem(storageKey, next ? '1' : '0')
      } catch {
        /* private mode — fine, just don't persist */
      }
      return next
    })
  }, [storageKey])

  return (
    <div className="glass-card premium-ring mb-6 overflow-hidden animate-rise">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={!collapsed}
        className="w-full flex items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-white/[0.02]"
      >
        <span
          className="neo-pressed shrink-0 rounded-lg p-1.5"
          style={{ background: 'var(--color-accent-glow)' }}
        >
          <Info className="h-3.5 w-3.5" style={{ color: 'var(--color-text-accent)' }} />
        </span>

        <span className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:gap-2">
          <span
            className="text-sm font-bold tracking-tight"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {title}
          </span>
          <span className="truncate text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {tagline}
          </span>
        </span>

        <span
          className="hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider sm:inline-block"
          style={{
            color: kind === 'deliverable' ? 'var(--color-text-accent)' : 'var(--color-text-tertiary)',
            border: `1px solid ${kind === 'deliverable' ? 'var(--color-border-accent)' : 'var(--color-border)'}`,
          }}
        >
          {KIND_LABEL[kind]}
        </span>

        <ChevronDown
          className={`h-4 w-4 shrink-0 transition-transform duration-300 ${collapsed ? '' : 'rotate-180'}`}
          style={{ color: 'var(--color-text-tertiary)' }}
        />
      </button>

      {!collapsed && (
        <div
          className="grid gap-4 px-5 pb-5 pt-1 sm:grid-cols-3"
          style={{ borderTop: '1px solid var(--color-border)' }}
        >
          <IntroBlock label="What it is" body={what} />
          <IntroBlock label="How it works" body={how} />
          <IntroBlock label="Why it matters" body={why} />
        </div>
      )}
    </div>
  )
}

function IntroBlock({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div
        className="mb-1.5 mt-3 text-[10px] font-bold uppercase tracking-[0.14em] sm:mt-0"
        style={{ color: 'var(--color-text-accent)' }}
      >
        {label}
      </div>
      <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
        {body}
      </p>
    </div>
  )
}
