/**
 * EvidenceGraphViz Component — Interactive Force-Directed Graph Visualization
 *
 * Renders evidence nodes and relationship edges as an interactive
 * force-directed graph using HTML5 Canvas. Shows evidence flow,
 * relationships, and connections between payment entities.
 *
 * Pure Canvas implementation — no external graph libraries needed.
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import {
  GitBranch,
  Maximize2,
  Minimize2,
  Eye,
} from 'lucide-react'

interface GraphNode {
  id: string
  label: string
  type: string
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  color: string
  evidence_type?: string
  value?: string
}

interface GraphEdge {
  source: string
  target: string
  type: string
  color: string
}

interface PaymentGraph {
  payment_id: string
  nodes: Array<{
    evidence_id: number
    evidence_type: string
    subject_type: string
    subject_id: string
    value: string | null
    value_type: string
    source_type: string
    observed_at: string
  }>
  edges: Array<{
    source_evidence_id: number
    target_evidence_id: number
    relationship_type: string
  }>
  node_count: number
  edge_count: number
}

const NODE_COLORS: Record<string, string> = {
  PAYMENT_AMOUNT: '#818cf8',
  PAYMENT_STATUS: '#34d399',
  PAYMENT_METHOD: '#fbbf24',
  PAYMENT_ID: '#fb7185',
  CURRENCY: '#a78bfa',
  CAPTURED: '#10b981',
  AUTHORISED: '#6366f1',
  default: '#64748b',
}

const NODE_RADIUS: Record<string, number> = {
  PAYMENT_ID: 28,
  PAYMENT_AMOUNT: 24,
  PAYMENT_STATUS: 22,
  PAYMENT_METHOD: 20,
  default: 18,
}

function buildGraph(data: PaymentGraph): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []

  // Add a center node for the payment
  nodes.push({
    id: `payment-${data.payment_id}`,
    label: data.payment_id,
    type: 'PAYMENT_ID',
    x: 400 + (Math.random() - 0.5) * 100,
    y: 300 + (Math.random() - 0.5) * 100,
    vx: 0,
    vy: 0,
    radius: 32,
    color: '#fb7185',
  })

  // Add evidence nodes
  for (const node of data.nodes) {
    const id = `evidence-${node.evidence_id}`
    const color = NODE_COLORS[node.evidence_type] || NODE_COLORS.default
    const radius = NODE_RADIUS[node.evidence_type] || NODE_RADIUS.default

    nodes.push({
      id,
      label: node.evidence_type.replace('PAYMENT_', '').substring(0, 8),
      type: node.evidence_type,
      x: 400 + (Math.random() - 0.5) * 400,
      y: 300 + (Math.random() - 0.5) * 300,
      vx: 0,
      vy: 0,
      radius,
      color,
      evidence_type: node.evidence_type,
      value: node.value || undefined,
    })

    // Connect evidence to payment center
    edges.push({
      source: `payment-${data.payment_id}`,
      target: id,
      type: 'BELONGS_TO',
      color: 'rgba(99, 102, 241, 0.3)',
    })
  }

  // Add relationship edges
  for (const edge of data.edges) {
    const sourceId = `evidence-${edge.source_evidence_id}`
    const targetId = `evidence-${edge.target_evidence_id}`

    if (nodes.find(n => n.id === sourceId) && nodes.find(n => n.id === targetId)) {
      edges.push({
        source: sourceId,
        target: targetId,
        type: edge.relationship_type,
        color: 'rgba(168, 85, 247, 0.4)',
      })
    }
  }

  return { nodes, edges }
}

export function EvidenceGraphViz() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [payments, setPayments] = useState<Array<{ razorpay_payment_id: string }>>([])
  const [selectedPayment, setSelectedPayment] = useState<string>('')
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] })
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const animFrameRef = useRef<number>(0)
  const draggingRef = useRef<GraphNode | null>(null)
  const lastMouseRef = useRef({ x: 0, y: 0 })

  // Fetch payment list
  useEffect(() => {
    fetch('/api/v1/payments')
      .then(r => r.json())
      .then(data => {
        setPayments(data)
        if (data.length > 0) {
          setSelectedPayment(data[0].razorpay_payment_id)
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  // Fetch graph data for selected payment
  useEffect(() => {
    if (!selectedPayment) return

    fetch(`/api/v1/graph/payments/${selectedPayment}`)
      .then(r => r.json())
      .then((data: PaymentGraph) => {
        const g = buildGraph(data)
        setGraph(g)
      })
      .catch(() => setGraph({ nodes: [], edges: [] }))
  }, [selectedPayment])

  // Force-directed layout simulation
  useEffect(() => {
    if (graph.nodes.length === 0) return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let running = true

    const simulate = () => {
      if (!running) return

      const { nodes, edges } = graph
      const width = canvas.width
      const height = canvas.height

      // Apply forces
      for (const node of nodes) {
        // Center gravity
        node.vx += (width / 2 - node.x) * 0.001
        node.vy += (height / 2 - node.y) * 0.001

        // Node repulsion
        for (const other of nodes) {
          if (node === other) continue
          const dx = node.x - other.x
          const dy = node.y - other.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = 500 / (dist * dist)
          node.vx += (dx / dist) * force
          node.vy += (dy / dist) * force
        }
      }

      // Edge attraction
      for (const edge of edges) {
        const source = nodes.find(n => n.id === edge.source)
        const target = nodes.find(n => n.id === edge.target)
        if (!source || !target) continue

        const dx = target.x - source.x
        const dy = target.y - source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (dist - 100) * 0.005
        source.vx += (dx / dist) * force
        source.vy += (dy / dist) * force
        target.vx -= (dx / dist) * force
        target.vy -= (dy / dist) * force
      }

      // Update positions with damping
      for (const node of nodes) {
        if (draggingRef.current === node) continue
        node.vx *= 0.9
        node.vy *= 0.9
        node.x += node.vx
        node.y += node.vy
        // Keep in bounds
        node.x = Math.max(node.radius, Math.min(width - node.radius, node.x))
        node.y = Math.max(node.radius, Math.min(height - node.radius, node.y))
      }

      // Render
      ctx.clearRect(0, 0, width, height)

      // Draw edges
      for (const edge of edges) {
        const source = nodes.find(n => n.id === edge.source)
        const target = nodes.find(n => n.id === edge.target)
        if (!source || !target) continue

        ctx.beginPath()
        ctx.moveTo(source.x, source.y)
        ctx.lineTo(target.x, target.y)
        ctx.strokeStyle = edge.color
        ctx.lineWidth = 1.5
        ctx.stroke()

        // Arrow
        const angle = Math.atan2(target.y - source.y, target.x - source.x)
        const midX = (source.x + target.x) / 2
        const midY = (source.y + target.y) / 2
        ctx.beginPath()
        ctx.moveTo(midX, midY)
        ctx.lineTo(
          midX - 6 * Math.cos(angle - Math.PI / 6),
          midY - 6 * Math.sin(angle - Math.PI / 6)
        )
        ctx.moveTo(midX, midY)
        ctx.lineTo(
          midX - 6 * Math.cos(angle + Math.PI / 6),
          midY - 6 * Math.sin(angle + Math.PI / 6)
        )
        ctx.strokeStyle = edge.color
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      // Draw nodes
      for (const node of nodes) {
        // Glow
        const gradient = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, node.radius * 2)
        gradient.addColorStop(0, node.color + '30')
        gradient.addColorStop(1, 'transparent')
        ctx.fillStyle = gradient
        ctx.fillRect(node.x - node.radius * 2, node.y - node.radius * 2, node.radius * 4, node.radius * 4)

        // Node circle
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = node.color + '40'
        ctx.fill()
        ctx.strokeStyle = node.color
        ctx.lineWidth = 2
        ctx.stroke()

        // Label
        ctx.fillStyle = '#e2e8f0'
        ctx.font = `${node.radius > 24 ? 11 : 9}px Inter, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(node.label, node.x, node.y)
      }

      animFrameRef.current = requestAnimationFrame(simulate)
    }

    simulate()

    return () => {
      running = false
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [graph])

  // Canvas mouse handlers
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) * (canvas.width / rect.width)
    const y = (e.clientY - rect.top) * (canvas.height / rect.height)

    for (const node of graph.nodes) {
      const dx = x - node.x
      const dy = y - node.y
      if (Math.sqrt(dx * dx + dy * dy) < node.radius + 5) {
        draggingRef.current = node
        lastMouseRef.current = { x: e.clientX, y: e.clientY }
        break
      }
    }
  }, [graph.nodes])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!draggingRef.current) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) * (canvas.width / rect.width)
    const y = (e.clientY - rect.top) * (canvas.height / rect.height)
    draggingRef.current.x = x
    draggingRef.current.y = y
    draggingRef.current.vx = 0
    draggingRef.current.vy = 0
  }, [])

  const handleMouseUp = useCallback(() => {
    draggingRef.current = null
  }, [])

  const handleMouseHover = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) * (canvas.width / rect.width)
    const y = (e.clientY - rect.top) * (canvas.height / rect.height)

    for (const node of graph.nodes) {
      const dx = x - node.x
      const dy = y - node.y
      if (Math.sqrt(dx * dx + dy * dy) < node.radius + 5) {
        setHoveredNode(node)
        canvas.style.cursor = 'pointer'
        return
      }
    }
    setHoveredNode(null)
    canvas.style.cursor = 'default'
  }, [graph.nodes])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-card-elevated p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="neo-pressed p-2.5 rounded-xl bg-purple-500/10">
                <GitBranch className="w-5 h-5 text-purple-400" />
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">Evidence Graph Visualization</h2>
            </div>
            <p className="text-slate-400 text-sm ml-12">
              Interactive force-directed graph of evidence relationships for a payment
            </p>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs text-slate-400 block mb-1">Select Payment</label>
            <select
              value={selectedPayment}
              onChange={e => setSelectedPayment(e.target.value)}
              className="glass-input w-full text-sm"
            >
              {payments.map(p => (
                <option key={p.razorpay_payment_id} value={p.razorpay_payment_id}>
                  {p.razorpay_payment_id}
                </option>
              ))}
            </select>
          </div>
          <div className="text-xs text-slate-500 mt-5">
            {graph.nodes.length} nodes • {graph.edges.length} edges
          </div>
        </div>
      </div>

      {/* Graph Canvas */}
      <div
        ref={containerRef}
        className={`glass-card overflow-hidden relative ${expanded ? 'fixed inset-0 z-50 rounded-none' : ''}`}
      >
        <div className="absolute top-4 right-4 z-10 flex gap-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="neo-btn p-2 rounded-lg"
          >
            {expanded ? <Minimize2 className="w-4 h-4 text-slate-300" /> : <Maximize2 className="w-4 h-4 text-slate-300" />}
          </button>
        </div>

        {hoveredNode && (
          <div className="absolute top-4 left-4 z-10 neo-card p-3 max-w-xs">
            <div className="text-xs font-bold text-slate-200 mb-1">{hoveredNode.type}</div>
            <div className="text-[10px] text-slate-400">Label: {hoveredNode.label}</div>
            {hoveredNode.value && (
              <div className="text-[10px] text-slate-400">Value: {hoveredNode.value}</div>
            )}
          </div>
        )}

        <canvas
          ref={canvasRef}
          width={expanded ? window.innerWidth : 800}
          height={expanded ? window.innerHeight - 200 : 500}
          className="w-full bg-slate-950/50"
          onMouseDown={handleMouseDown}
          onMouseMove={(e) => { handleMouseMove(e); handleMouseHover(e) }}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        />

        {graph.nodes.length === 0 && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Eye className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">Select a payment to visualize its evidence graph</p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="glass-card p-4">
        <div className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-3">Node Legend</div>
        <div className="flex flex-wrap gap-3">
          {Object.entries(NODE_COLORS).filter(([k]) => k !== 'default').map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
              <span className="text-[11px] text-slate-400">{type.replace('PAYMENT_', '')}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
