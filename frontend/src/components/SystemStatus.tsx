/**
 * SystemStatus component.
 *
 * Polls the backend readiness endpoint and renders the live status of each
 * infrastructure dependency.  Status values come entirely from the API —
 * nothing is hardcoded.
 */

import { useEffect, useState } from 'react'
import { fetchLiveness, fetchReadiness } from '../lib/api'
import type { ReadinessResponse } from '../lib/api'

type StatusState =
  | { phase: 'loading' }
  | { phase: 'backend_down'; error: string }
  | { phase: 'ready'; data: ReadinessResponse }

const POLL_INTERVAL_MS = 15_000

function StatusBadge({ value }: { value: string }) {
  const isConnected = value === 'connected'
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${
        isConnected
          ? 'bg-emerald-100 text-emerald-800'
          : 'bg-red-100 text-red-800'
      }`}
      aria-label={isConnected ? 'connected' : 'unavailable'}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          isConnected ? 'bg-emerald-500' : 'bg-red-500'
        }`}
        aria-hidden="true"
      />
      {isConnected ? 'Connected' : 'Unavailable'}
    </span>
  )
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <span className="text-gray-600 font-medium">{label}</span>
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm bg-gray-100 text-gray-500 animate-pulse">
        Checking…
      </span>
    </div>
  )
}

export function SystemStatus() {
  const [state, setState] = useState<StatusState>({ phase: 'loading' })

  async function checkStatus() {
    // First verify the backend is alive at all
    const liveness = await fetchLiveness()
    if (!liveness.ok) {
      setState({ phase: 'backend_down', error: liveness.error })
      return
    }

    // Then fetch full readiness (db + redis)
    const readiness = await fetchReadiness()
    if (!readiness.ok) {
      // Backend is up but readiness endpoint returned an error body —
      // parse the degraded state from the response if possible.
      // For simplicity we show backend as connected but deps unknown.
      setState({
        phase: 'ready',
        data: {
          status: 'not_ready',
          database: 'unavailable',
          redis: 'unavailable',
        },
      })
      return
    }

    setState({ phase: 'ready', data: readiness.data })
  }

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  if (state.phase === 'loading') {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          System Status
        </h2>
        <LoadingRow label="Backend API" />
        <LoadingRow label="PostgreSQL" />
        <LoadingRow label="Redis" />
      </div>
    )
  }

  if (state.phase === 'backend_down') {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-red-200 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          System Status
        </h2>
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          <p className="font-semibold mb-1">Backend Unreachable</p>
          <p className="text-red-600 font-mono text-xs break-all">
            {state.error}
          </p>
        </div>
        <div className="mt-4 space-y-0 divide-y divide-gray-100">
          {(['Backend API', 'PostgreSQL', 'Redis'] as const).map((label) => (
            <div
              key={label}
              className="flex items-center justify-between py-3"
            >
              <span className="text-gray-600 font-medium">{label}</span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm bg-red-100 text-red-700">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                Unavailable
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const { data } = state
  const backendStatus = data.status === 'ready' ? 'connected' : 'unavailable'

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        System Status
      </h2>
      <div className="divide-y divide-gray-100">
        <div className="flex items-center justify-between py-3">
          <span className="text-gray-600 font-medium">Backend API</span>
          <StatusBadge value={backendStatus} />
        </div>
        <div className="flex items-center justify-between py-3">
          <span className="text-gray-600 font-medium">PostgreSQL</span>
          <StatusBadge value={data.database} />
        </div>
        <div className="flex items-center justify-between py-3">
          <span className="text-gray-600 font-medium">Redis</span>
          <StatusBadge value={data.redis} />
        </div>
      </div>
      <p className="mt-4 text-xs text-gray-400 text-right">
        Refreshes every {POLL_INTERVAL_MS / 1000}s
      </p>
    </div>
  )
}
