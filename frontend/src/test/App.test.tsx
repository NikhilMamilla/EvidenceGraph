/**
 * App shell smoke tests.
 *
 * The app is a multi-tab dashboard; these verify it mounts without crashing,
 * shows its identity, and exposes the Track-02 defense tabs. The API layer is
 * mocked so nothing hits the network.
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import App from '../App'

vi.mock('../lib/api', () => ({
  fetchLiveness: vi.fn().mockResolvedValue({
    ok: true,
    data: { status: 'ok', service: 'evidencegraph-api' },
  }),
  fetchReadiness: vi.fn().mockResolvedValue({
    ok: true,
    data: { status: 'ready', database: 'connected', redis: 'connected' },
  }),
  fetchRazorpayStatus: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      configured: true,
      mode: 'test',
      key_id_prefix: 'rzp_test_',
      last_verified_event_at: null,
      events_received: 0,
      events_processed: 0,
      events_rejected: 0,
      events_duplicate: 0,
    },
  }),
  fetchOperationalHealth: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      overall_state: 'HEALTHY',
      summary: 'All system components healthy',
      checked_at: new Date().toISOString(),
      components: {},
      methodology_version: 'EOI-1.0',
    },
  }),
  fetchOperationalMetrics: vi.fn().mockResolvedValue({ ok: true, data: {} }),
  fetchPipelineStatus: vi.fn().mockResolvedValue({ ok: true, data: { stages: [] } }),
  fetchOperationalIncidents: vi.fn().mockResolvedValue({
    ok: true,
    data: { incidents: [], active_incidents_count: 0 },
  }),
  runSystemVerification: vi.fn().mockResolvedValue({
    ok: true,
    data: { overall_status: 'PASS', checks: [] },
  }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  // Components fire fetch() on mount. Return an empty array by default so the
  // list-rendering paths (`.map`) don't throw; object consumers just see
  // `undefined` fields, which they already guard.
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
  ) as unknown as typeof fetch
})

describe('App shell', () => {
  it('renders the EvidenceGraph title', () => {
    render(<App />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toMatch(/EvidenceGraph/i)
  })

  it('shows the buildathon badge', () => {
    render(<App />)
    expect(screen.getByText(/Razorpay AI Builder/i)).toBeInTheDocument()
  })

  it('exposes the Track-02 defense tabs', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /Defense Eval/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /AI Verify/i })).toBeInTheDocument()
  })

  it('switching to a tab updates the active tab control', () => {
    render(<App />)
    const defenseTab = screen.getByRole('button', { name: /Defense Eval/i })
    fireEvent.click(defenseTab)
    expect(defenseTab.className).toMatch(/tab-glass-active/)
  })
})
