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
}))

import { fetchLiveness, fetchReadiness } from '../lib/api'

const mockFetchLiveness = vi.mocked(fetchLiveness)
const mockFetchReadiness = vi.mocked(fetchReadiness)

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

    render(<App />)
    await waitFor(() => {
      const unavailable = screen.getAllByText('Unavailable')
      expect(unavailable.length).toBeGreaterThan(0)
    })
  })
})
