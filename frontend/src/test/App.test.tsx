/**
 * Frontend tests for EvidenceGraph Phase 1.
 *
 * These tests mock the API layer (not the production application code).
 * They verify rendering behaviour in connected, degraded, and backend-down
 * states.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import App from '../App'

// ---------------------------------------------------------------------------
// Mock the entire lib/api module so no real HTTP calls are made
// ---------------------------------------------------------------------------
vi.mock('../lib/api', () => ({
  fetchLiveness: vi.fn(),
  fetchReadiness: vi.fn(),
  fetchRazorpayStatus: vi.fn(),
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
  fetchOperationalMetrics: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      timestamp: new Date().toISOString(),
      ingestion: {
        total_received: 10,
        total_verified: 10,
        total_rejected: 0,
        total_duplicates: 0,
        total_processed: 10,
        total_failed: 0,
        last_received_at: new Date().toISOString(),
        last_verified_at: new Date().toISOString(),
        last_processed_at: new Date().toISOString(),
        recent_events_count_1h: 10,
      },
      queue: {
        queue_name: 'evidencegraph:webhook_events',
        queue_depth: 0,
        oldest_event_age_seconds: null,
        is_backlogged: false,
      },
      lag: {
        average_lag_seconds: 0.1,
        latest_lag_seconds: 0.1,
        max_recent_lag_seconds: 0.2,
      },
      stuck_events_count: 0,
      failed_events_count: 0,
      active_payments_count: 1,
      active_facts_count: 5,
    },
  }),
  fetchPipelineStatus: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      timestamp: new Date().toISOString(),
      pipeline_watermark_timestamp: new Date().toISOString(),
      stages: [],
      is_pipeline_caught_up: true,
      summary: 'Pipeline caught up',
    },
  }),
  fetchOperationalIncidents: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      timestamp: new Date().toISOString(),
      active_incidents_count: 0,
      incidents: [],
    },
  }),
  runSystemVerification: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      timestamp: new Date().toISOString(),
      overall_status: 'PASS',
      total_checks: 10,
      passed_count: 10,
      warn_count: 0,
      failed_count: 0,
      checks: [],
    },
  }),
}))

import { fetchLiveness, fetchReadiness, fetchRazorpayStatus } from '../lib/api'

const mockFetchLiveness = vi.mocked(fetchLiveness)
const mockFetchReadiness = vi.mocked(fetchReadiness)
const mockFetchRazorpayStatus = vi.mocked(fetchRazorpayStatus)

const mockRazorpayData = {
  configured: true,
  mode: 'test',
  key_id_prefix: 'rzp_test_',
  last_verified_event_at: null,
  events_received: 0,
  events_processed: 0,
  events_rejected: 0,
  events_duplicate: 0,
}

describe('App', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the EvidenceGraph title', async () => {
    mockFetchLiveness.mockResolvedValue({ ok: true, data: { status: 'ok', service: 'evidencegraph-api' } })
    mockFetchReadiness.mockResolvedValue({
      ok: true,
      data: { status: 'ready', database: 'connected', redis: 'connected' },
    })
    mockFetchRazorpayStatus.mockResolvedValue({ ok: true, data: mockRazorpayData })

    render(<App />)
    // The h1 contains "Evidence" and "Graph" split across a span.
    // Match the h1 element itself by querying its partial text content.
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toBeInTheDocument()
    expect(heading.textContent).toMatch(/EvidenceGraph/i)
  })

  it('shows loading state before API responds', () => {
    // Never resolves during this test
    mockFetchLiveness.mockReturnValue(new Promise(() => {}))
    mockFetchReadiness.mockReturnValue(new Promise(() => {}))
    mockFetchRazorpayStatus.mockReturnValue(new Promise(() => {}))

    render(<App />)
    expect(screen.getAllByText(/Checking/i).length).toBeGreaterThan(0)
  })
})

describe('SystemStatus — connected state', () => {
  beforeEach(() => {
    mockFetchLiveness.mockResolvedValue({
      ok: true,
      data: { status: 'ok', service: 'evidencegraph-api' },
    })
    mockFetchReadiness.mockResolvedValue({
      ok: true,
      data: { status: 'ready', database: 'connected', redis: 'connected' },
    })
    mockFetchRazorpayStatus.mockResolvedValue({ ok: true, data: mockRazorpayData })
  })

  it('renders Connected for all services when healthy', async () => {
    render(<App />)
    await waitFor(() => {
      const badges = screen.getAllByText('Connected')
      // Backend API, PostgreSQL, Redis — 3 Connected badges
      expect(badges.length).toBe(3)
    })
  })

  it('shows PostgreSQL row', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('PostgreSQL')).toBeInTheDocument()
    })
  })

  it('shows Redis row', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('Redis')).toBeInTheDocument()
    })
  })
})

describe('SystemStatus — backend unavailable', () => {
  it('shows Backend Unreachable when liveness fails', async () => {
    mockFetchLiveness.mockResolvedValue({
      ok: false,
      error: 'Network error: Failed to fetch',
    })
    mockFetchReadiness.mockResolvedValue({
      ok: true,
      data: { status: 'ready', database: 'connected', redis: 'connected' },
    })
    mockFetchRazorpayStatus.mockResolvedValue({ ok: true, data: mockRazorpayData })

    render(<App />)
    await waitFor(() => {
      expect(screen.getByText(/Backend Unreachable/i)).toBeInTheDocument()
    })
  })

  it('shows error message when backend is down', async () => {
    mockFetchLiveness.mockResolvedValue({
      ok: false,
      error: 'Request timed out. Is the backend running?',
    })
    mockFetchReadiness.mockResolvedValue({ ok: false, error: 'timeout' })
    mockFetchRazorpayStatus.mockResolvedValue({ ok: false, error: 'timeout' })

    render(<App />)
    await waitFor(() => {
      expect(
        screen.getByText(/Request timed out/i)
      ).toBeInTheDocument()
    })
  })
})

describe('SystemStatus — degraded state', () => {
  it('shows Unavailable when readiness returns degraded', async () => {
    mockFetchLiveness.mockResolvedValue({
      ok: true,
      data: { status: 'ok', service: 'evidencegraph-api' },
    })
    mockFetchReadiness.mockResolvedValue({
      ok: false,
      error: 'Service unavailable',
      statusCode: 503,
    })
    mockFetchRazorpayStatus.mockResolvedValue({ ok: true, data: mockRazorpayData })

    render(<App />)
    await waitFor(() => {
      const unavailable = screen.getAllByText('Unavailable')
      expect(unavailable.length).toBeGreaterThan(0)
    })
  })
})
