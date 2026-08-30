import { useState, useEffect } from 'react'
import { SystemStatus } from './components/SystemStatus'

import { OperationsDashboard } from './components/OperationsDashboard'
import { LiveEventFeed } from './components/LiveEventFeed'
import { EvidenceGraphViz } from './components/EvidenceGraphViz'
import { RiskScoreGauge } from './components/RiskScoreGauge'
import { FraudAlerts } from './components/FraudAlerts'
import { InvestigationCenter } from './components/InvestigationCenter'
import { PaymentFailures } from './components/PaymentFailures'
import { PaymentInspector } from './components/PaymentInspector'
import { NotificationCenter } from './components/NotificationCenter'
import { RevenueIntelligence } from './components/RevenueIntelligence'
import { MerchantRiskDashboard } from './components/MerchantRiskDashboard'
import DefenseEvaluation from './components/DefenseEvaluation'
import DefenseVerification from './components/DefenseVerification'
import {
  Activity,
  Shield,
  Sparkles,
  Radio,
  GitBranch,
  ShieldAlert,
  Compass,
  TrendingUp,
  AlertTriangle,
  Bell,
  DollarSign,
  BarChart3,
  Sun,
  Moon,
  Scale,
} from 'lucide-react'

type TabKey = 'live' | 'notifications' | 'risk' | 'graph' | 'fraud' | 'failures' | 'revenue' | 'merchant' | 'investigate' | 'payments' | 'operations' | 'defense' | 'defense-ai'

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('live')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const tabs = [
    { key: 'live' as TabKey, label: 'Live Stream', shortLabel: 'Live', icon: Radio },
    { key: 'notifications' as TabKey, label: 'Notifications', shortLabel: 'Alerts', icon: Bell },
    { key: 'risk' as TabKey, label: 'Risk Score', shortLabel: 'Risk', icon: TrendingUp },
    { key: 'graph' as TabKey, label: 'Evidence Graph', shortLabel: 'Graph', icon: GitBranch },
    { key: 'fraud' as TabKey, label: 'Fraud Detection', shortLabel: 'Fraud', icon: ShieldAlert },
    { key: 'failures' as TabKey, label: 'Failure Intel', shortLabel: 'Failures', icon: AlertTriangle },
    { key: 'revenue' as TabKey, label: 'Revenue', shortLabel: 'Revenue', icon: DollarSign },
    { key: 'merchant' as TabKey, label: 'Merchant Risk', shortLabel: 'Merchant', icon: BarChart3 },
    { key: 'investigate' as TabKey, label: 'Investigation', shortLabel: 'Investigate', icon: Compass },
    { key: 'payments' as TabKey, label: 'Payments', shortLabel: 'Payments', icon: Shield },
    { key: 'operations' as TabKey, label: 'Operations', shortLabel: 'Ops', icon: Activity },
    { key: 'defense' as TabKey, label: 'Defense Eval', shortLabel: 'Defense', icon: Scale },
    { key: 'defense-ai' as TabKey, label: 'AI Verify', shortLabel: 'AI Verify', icon: Shield },
  ]

  return (
    <div className="min-h-screen flex flex-col items-center px-4 sm:px-6 lg:px-8 py-6 sm:py-12 relative">
      {/* Aurora Background */}
      <div className="aurora-bg" />

      {/* Floating Orbs — Aurora Effect */}
      <div
        className="fixed top-20 left-10 w-80 h-80 rounded-full blur-[120px] pointer-events-none animate-float"
        style={{ background: 'var(--aurora-1)' }}
      />
      <div
        className="fixed bottom-20 right-10 w-96 h-96 rounded-full blur-[120px] pointer-events-none animate-float"
        style={{ background: 'var(--aurora-2)', animationDelay: '-3s' }}
      />
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full blur-[120px] pointer-events-none"
        style={{ background: 'var(--aurora-3)' }}
      />

      {/* Header */}
      <header className="text-center mb-8 sm:mb-12 w-full max-w-6xl animate-fade-in">
        {/* Top Bar: Badge + Theme Toggle */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex-1" />
          <div className="inline-flex items-center gap-2 px-5 py-2 rounded-full animate-scale-in"
            style={{
              background: 'var(--color-bg-surface)',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-md)',
            }}>
            <Sparkles className="w-3.5 h-3.5" style={{ color: 'var(--color-accent-primary)' }} />
            <span className="text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--color-text-accent)' }}>
              Razorpay AI Builder 2026
            </span>
          </div>
          <div className="flex-1 flex justify-end">
            {/* Theme Toggle */}
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="theme-toggle"
              aria-label="Toggle theme"
            >
              <div className="theme-toggle-knob flex items-center justify-center">
                {theme === 'dark' ? (
                  <Moon className="w-3 h-3 text-white" />
                ) : (
                  <Sun className="w-3 h-3 text-white" />
                )}
              </div>
            </button>
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight mb-4 animate-slide-up"
          style={{ fontFamily: "'Space Grotesk', sans-serif", letterSpacing: '-0.03em' }}
        >
          <span style={{ color: 'var(--color-text-primary)' }}>Evidence</span>
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage: 'var(--gradient-primary)',
              WebkitBackgroundClip: 'text',
            }}
          >
            Graph
          </span>
        </h1>

        <p
          className="text-base sm:text-lg max-w-2xl mx-auto leading-relaxed animate-slide-up"
          style={{ color: 'var(--color-text-secondary)', animationDelay: '0.1s' }}
        >
          Real-Time Payment-Risk Evidence Intelligence Platform
        </p>

        {/* Tab Switcher */}
        <div
          className="flex items-center justify-center gap-2 mt-8 animate-slide-up flex-wrap"
          style={{ animationDelay: '0.2s' }}
        >
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-xs font-semibold transition-all duration-300 ${
                activeTab === tab.key
                  ? 'tab-glass-active'
                  : 'tab-glass'
              }`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{tab.label}</span>
              <span className="sm:hidden">{tab.shortLabel}</span>
            </button>
          ))}
        </div>
      </header>

      {/* Main Content */}
      <main className="w-full max-w-6xl mx-auto animate-slide-up" style={{ animationDelay: '0.3s' }}>
        {activeTab === 'live' && <LiveEventFeed />}
        {activeTab === 'notifications' && <NotificationCenter />}
        {activeTab === 'risk' && <RiskScoreGauge />}
        {activeTab === 'graph' && <EvidenceGraphViz />}
        {activeTab === 'fraud' && <FraudAlerts />}
        {activeTab === 'failures' && <PaymentFailures />}
        {activeTab === 'revenue' && <RevenueIntelligence />}
        {activeTab === 'merchant' && <MerchantRiskDashboard />}
        {activeTab === 'investigate' && <InvestigationCenter />}
        {activeTab === 'payments' && <PaymentInspector />}
        {activeTab === 'operations' && (
          <div className="space-y-6">
            <div className="w-full flex flex-col lg:flex-row gap-6">
              <SystemStatus />
            </div>
            <OperationsDashboard />
          </div>
        )}
        {activeTab === 'defense' && <DefenseEvaluation />}
        {activeTab === 'defense-ai' && <DefenseVerification />}
      </main>

      {/* Footer */}
      <footer className="mt-12 sm:mt-16 pb-8 text-center animate-fade-in" style={{ animationDelay: '0.5s' }}>
        <div className="glass-divider w-32 mx-auto mb-4" />
        <p
          className="text-xs font-mono tracking-wider"
          style={{ color: 'var(--color-text-tertiary)', fontFamily: "'JetBrains Mono', monospace" }}
        >
          Phase 22 — AI Defense Verification & EvidenceGraph
        </p>
      </footer>
    </div>
  )
}

export default App
