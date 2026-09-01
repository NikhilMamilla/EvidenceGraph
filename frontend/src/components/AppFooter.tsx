/**
 * AppFooter — three-column site footer.
 *
 * Left:   what this is and which track it targets
 * Middle: outbound links (repo, API docs, health)
 * Right:  live backend status + the versions the verdicts were produced under
 *
 * The status dot is real: it polls /health/live. Version strings are build-time
 * constants, not computed metrics.
 */

import { useEffect, useState } from 'react'
import { Scale, ExternalLink, BookOpen, GitBranch, Activity } from 'lucide-react'
import { fetchLiveness } from '../lib/api'

const REPO_URL = 'https://github.com/NikhilMamilla/EvidenceGraph'
const POLL_MS = 30_000

export function AppFooter() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      const res = await fetchLiveness()
      if (!cancelled) setOnline(res.ok)
    }
    check()
    const t = setInterval(check, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [])

  const dot =
    online === null
      ? { color: 'var(--color-text-tertiary)', label: 'Checking API' }
      : online
      ? { color: 'var(--color-success)', label: 'API online' }
      : { color: 'var(--color-danger)', label: 'API unreachable' }

  return (
    <footer className="mt-16 w-full max-w-6xl px-1 pb-10 sm:mt-20">
      <div className="glass-divider mb-8 w-full" />

      <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
        {/* Identity */}
        <div>
          <div className="mb-3 flex items-center gap-2.5">
            <span
              className="neo-pressed rounded-lg p-2"
              style={{ background: 'var(--color-accent-glow)' }}
            >
              <Scale className="h-4 w-4" style={{ color: 'var(--color-text-accent)' }} />
            </span>
            <span
              className="text-sm font-bold tracking-tight"
              style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-display)' }}
            >
              EvidenceGraph
            </span>
          </div>
          <p
            className="max-w-xs text-xs leading-relaxed"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            A pre-submission chargeback-defense verifier. Deterministic evidence
            verification with an optional, advisory AI layer.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <FooterTag>Track 02 · AI Risk Manager</FooterTag>
            <FooterTag>Defense-only</FooterTag>
          </div>
        </div>

        {/* Links */}
        <div>
          <FooterHeading>Resources</FooterHeading>
          <ul className="space-y-2.5">
            <FooterLink href={REPO_URL} icon={GitBranch}>
              Source repository
            </FooterLink>
            <FooterLink href="/docs" icon={BookOpen}>
              API reference (Swagger)
            </FooterLink>
            <FooterLink href="/api/v1/health/ready" icon={Activity}>
              Readiness probe
            </FooterLink>
          </ul>
        </div>

        {/* Status */}
        <div>
          <FooterHeading>Status</FooterHeading>
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{
                  background: dot.color,
                  boxShadow: `0 0 8px ${dot.color}`,
                }}
              />
              <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                {dot.label}
              </span>
            </div>
            <StatusLine label="Evaluator" value="REF_EVAL_V2" />
            <StatusLine label="Dataset" value="EG-DEFENSE-1.0 · 20 cases" />
            <StatusLine label="Scope" value="Delivery disputes" />
          </div>
        </div>
      </div>

      <div
        className="mt-8 flex flex-col items-center justify-between gap-2 pt-6 sm:flex-row"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        <p
          className="text-[11px] tracking-wide"
          style={{ color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}
        >
          Razorpay Buildathon 2026 · Track 02
        </p>
        <p className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
          Hackathon demonstration on Razorpay Test Mode data — not production-validated.
        </p>
      </div>
    </footer>
  )
}

function FooterHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3
      className="mb-3.5 text-[10px] font-bold uppercase tracking-[0.14em]"
      style={{ color: 'var(--color-text-accent)' }}
    >
      {children}
    </h3>
  )
}

function FooterTag({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2.5 py-1 text-[10px] font-semibold"
      style={{
        color: 'var(--color-text-tertiary)',
        border: '1px solid var(--color-border)',
      }}
    >
      {children}
    </span>
  )
}

function FooterLink({
  href,
  icon: Icon,
  children,
}: {
  href: string
  icon: React.ElementType
  children: React.ReactNode
}) {
  const external = href.startsWith('http')
  return (
    <li>
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noreferrer noopener' : undefined}
        className="group inline-flex items-center gap-2 text-xs transition-colors"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--color-text-tertiary)' }} />
        <span className="group-hover:underline">{children}</span>
        <ExternalLink
          className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-60"
          style={{ color: 'var(--color-text-tertiary)' }}
        />
      </a>
    </li>
  )
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
        {label}
      </span>
      <span
        className="truncate text-[11px] font-medium"
        style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}
      >
        {value}
      </span>
    </div>
  )
}
