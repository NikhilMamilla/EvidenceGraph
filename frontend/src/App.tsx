import { SystemStatus } from './components/SystemStatus'

function App() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col items-center justify-center px-4 py-12">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-semibold px-3 py-1 rounded-full mb-4 uppercase tracking-widest">
          Razorpay AI Builder 2026
        </div>
        <h1 className="text-5xl font-extrabold text-white tracking-tight mb-3">
          Evidence<span className="text-indigo-400">Graph</span>
        </h1>
        <p className="text-slate-400 text-lg max-w-lg mx-auto">
          Real-Time Payment-Risk Evidence Intelligence
        </p>
        <p className="text-slate-500 text-sm mt-2 max-w-xl mx-auto">
          Analyzes the trustworthiness, independence, freshness, and consistency
          of evidence behind every payment-risk decision.
        </p>
      </div>

      {/* System Status Card */}
      <div className="w-full max-w-sm">
        <SystemStatus />
      </div>

      {/* Phase Badge */}
      <div className="mt-8 text-slate-600 text-xs font-mono">
        Phase 1 — Production Foundation
      </div>
    </div>
  )
}

export default App
