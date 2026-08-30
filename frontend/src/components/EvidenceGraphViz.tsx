/**
 * EvidenceGraphViz — HD force-directed evidence graph.
 *
 * A dependency-free canvas engine:
 *   • DPR-aware rendering (crisp on retina / 4K)
 *   • d3-style force simulation with alpha cooling + node collision
 *   • gradient bezier edges with animated "evidence flow" particles
 *   • sphere-shaded nodes, additive glow, a pulsing core on the payment node
 *   • hover → highlight the neighbourhood, dim the rest
 *   • drag to pin, click to release, fullscreen, theme-aware palette
 *   • respects prefers-reduced-motion (settles, then freezes; no particles)
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { GitBranch, Maximize2, Minimize2, Eye, Pin, RotateCcw } from 'lucide-react'

/* ─────────────────────────────  types  ───────────────────────────── */

interface ApiNode {
  evidence_id: number
  evidence_type: string
  subject_type: string
  subject_id: string
  value: string | null
  value_type: string
  source_type: string
  observed_at: string
}
interface ApiEdge {
  source_evidence_id: number
  target_evidence_id: number
  relationship_type: string
}
interface PaymentGraph {
  payment_id: string
  nodes: ApiNode[]
  edges: ApiEdge[]
  node_count: number
  edge_count: number
}

interface SimNode {
  id: string
  label: string
  full: string
  kind: string
  value?: string
  source?: string
  x: number
  y: number
  vx: number
  vy: number
  r: number
  baseR: number
  pinned: boolean
  depth: number // 0 = payment core, 1 = evidence, 2 = related
}
interface SimEdge {
  a: string
  b: string
  kind: string
  strong: boolean // relationship edge vs structural "belongs-to"
  rest: number
}

/* ───────────────────────────  palette  ──────────────────────────── */

type Palette = {
  core: string
  amount: string
  status: string
  method: string
  currency: string
  neutral: string
  edge: string
  edgeStrong: string
  text: string
  textDim: string
  panel: string
  bgInner: string
}

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement)
  const v = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb
  return {
    core: v('--color-danger', '#ff6b81'),
    amount: v('--color-info', '#74b9ff'),
    status: v('--color-success', '#00d2a0'),
    method: v('--color-warning', '#ffc048'),
    currency: v('--color-accent-secondary', '#a29bfe'),
    neutral: v('--color-text-tertiary', '#5a6480'),
    edge: v('--color-border-hover', 'rgba(255,255,255,0.12)'),
    edgeStrong: v('--color-accent-primary', '#6c5ce7'),
    text: v('--color-text-primary', '#f0f2f8'),
    textDim: v('--color-text-secondary', '#8892b0'),
    panel: v('--color-bg-elevated', '#1c2340'),
    bgInner: v('--color-bg-primary', '#080b14'),
  }
}

function nodeColor(kind: string, p: Palette): string {
  const k = kind.toUpperCase()
  if (k.includes('PAYMENT_ID') || k === 'PAYMENT') return p.core
  if (k.includes('AMOUNT')) return p.amount
  if (k.includes('STATUS') || k === 'CAPTURED' || k === 'AUTHORISED') return p.status
  if (k.includes('METHOD')) return p.method
  if (k.includes('CURRENCY')) return p.currency
  return p.neutral
}

const LEGEND: [string, keyof Palette][] = [
  ['Payment', 'core'],
  ['Amount', 'amount'],
  ['Status', 'status'],
  ['Method', 'method'],
  ['Currency', 'currency'],
  ['Other', 'neutral'],
]

/* ────────────────────────  colour helpers  ──────────────────────── */

function withAlpha(color: string, a: number): string {
  const c = color.trim()
  const rgbMatch = c.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i)
  if (rgbMatch) {
    return `rgba(${rgbMatch[1]},${rgbMatch[2]},${rgbMatch[3]},${a})`
  }
  const h = c.replace('#', '')
  if (h.length === 3) {
    const r = parseInt(h[0] + h[0], 16)
    const g = parseInt(h[1] + h[1], 16)
    const b = parseInt(h[2] + h[2], 16)
    return `rgba(${r},${g},${b},${a})`
  }
  if (h.length >= 6) {
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${a})`
  }
  return c
}
function lighten(hex: string, amt: number): string {
  const h = hex.replace('#', '')
  if (h.length < 6) return hex
  const r = Math.min(255, parseInt(h.slice(0, 2), 16) + amt)
  const g = Math.min(255, parseInt(h.slice(2, 4), 16) + amt)
  const b = Math.min(255, parseInt(h.slice(4, 6), 16) + amt)
  return `rgb(${r},${g},${b})`
}

/* ─────────────────────────  build graph  ────────────────────────── */

function prettyKind(k: string): string {
  return k
    .replace(/^PAYMENT_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function buildGraph(data: PaymentGraph, w: number, h: number): { nodes: SimNode[]; edges: SimEdge[] } {
  const cx = w / 2
  const cy = h / 2
  const nodes: SimNode[] = []
  const edges: SimEdge[] = []

  nodes.push({
    id: `pay:${data.payment_id}`,
    label: data.payment_id,
    full: data.payment_id,
    kind: 'PAYMENT_ID',
    x: cx,
    y: cy,
    vx: 0,
    vy: 0,
    r: 30,
    baseR: 30,
    pinned: false,
    depth: 0,
  })

  const n = Math.max(1, data.nodes.length)
  data.nodes.forEach((node, i) => {
    const id = `ev:${node.evidence_id}`
    const ang = (i / n) * Math.PI * 2 - Math.PI / 2
    const ring = 150 + (i % 3) * 26
    const big = /AMOUNT|STATUS|METHOD/.test(node.evidence_type)
    nodes.push({
      id,
      label: prettyKind(node.evidence_type).split(' ')[0].slice(0, 9),
      full: prettyKind(node.evidence_type),
      kind: node.evidence_type,
      value: node.value ?? undefined,
      source: node.source_type,
      x: cx + Math.cos(ang) * ring + (Math.random() - 0.5) * 20,
      y: cy + Math.sin(ang) * ring + (Math.random() - 0.5) * 20,
      vx: 0,
      vy: 0,
      r: big ? 20 : 15,
      baseR: big ? 20 : 15,
      pinned: false,
      depth: 1,
    })
    edges.push({ a: `pay:${data.payment_id}`, b: id, kind: 'OBSERVED_ON', strong: false, rest: 132 })
  })

  const ids = new Set(nodes.map((x) => x.id))
  for (const e of data.edges) {
    const a = `ev:${e.source_evidence_id}`
    const b = `ev:${e.target_evidence_id}`
    if (ids.has(a) && ids.has(b)) {
      edges.push({ a, b, kind: e.relationship_type, strong: true, rest: 96 })
    }
  }
  return { nodes, edges }
}

/* ─────────────────────────  component  ──────────────────────────── */

export function EvidenceGraphViz() {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const [payments, setPayments] = useState<{ razorpay_payment_id: string }[]>([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [counts, setCounts] = useState({ n: 0, e: 0 })
  const [hover, setHover] = useState<{ node: SimNode; px: number; py: number } | null>(null)

  const reduceMotion = useMemo(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
    [],
  )

  // engine state (never triggers re-render)
  const engine = useRef({
    nodes: [] as SimNode[],
    edges: [] as SimEdge[],
    adj: new Map<string, Set<string>>(),
    byId: new Map<string, SimNode>(),
    palette: readPalette(),
    alpha: 1,
    hoverId: null as string | null,
    dragId: null as string | null,
    raf: 0,
    size: { w: 800, h: 520 },
    dpr: 1,
    t0: performance.now(),
    intro: 1, // 1 → 0 entry animation
  })

  /* fetch payment list */
  useEffect(() => {
    fetch('/api/v1/payments')
      .then((r) => r.json())
      .then((d) => {
        const list = Array.isArray(d) ? d : []
        setPayments(list)
        if (list.length) setSelected(list[0].razorpay_payment_id)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  /* fetch + build graph for the selected payment */
  const loadGraph = useCallback((paymentId: string) => {
    if (!paymentId) return
    fetch(`/api/v1/graph/payments/${paymentId}`)
      .then((r) => r.json())
      .then((data: PaymentGraph) => {
        const { w, h } = engine.current.size
        const { nodes, edges } = buildGraph(data, w, h)
        const byId = new Map(nodes.map((x) => [x.id, x]))
        const adj = new Map<string, Set<string>>()
        for (const n of nodes) adj.set(n.id, new Set())
        for (const e of edges) {
          adj.get(e.a)?.add(e.b)
          adj.get(e.b)?.add(e.a)
        }
        Object.assign(engine.current, { nodes, edges, byId, adj, alpha: 1, intro: 1 })
        setCounts({ n: nodes.length, e: edges.length })
      })
      .catch(() => {
        Object.assign(engine.current, { nodes: [], edges: [], byId: new Map(), adj: new Map() })
        setCounts({ n: 0, e: 0 })
      })
  }, [])

  useEffect(() => {
    loadGraph(selected)
  }, [selected, loadGraph])

  /* theme-aware palette */
  useEffect(() => {
    const obs = new MutationObserver(() => {
      engine.current.palette = readPalette()
    })
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])

  /* resize → DPR canvas + re-centre if graph is empty of motion */
  useEffect(() => {
    const cv = canvasRef.current
    const wrap = wrapRef.current
    if (!cv || !wrap) return
    const fit = () => {
      const rect = wrap.getBoundingClientRect()
      const w = Math.max(320, rect.width)
      const h = expanded ? Math.max(360, window.innerHeight - 96) : 520
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      cv.width = Math.round(w * dpr)
      cv.height = Math.round(h * dpr)
      cv.style.height = `${h}px`
      engine.current.size = { w, h }
      engine.current.dpr = dpr
      engine.current.alpha = Math.max(engine.current.alpha, 0.4)
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(wrap)
    window.addEventListener('resize', fit)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', fit)
    }
  }, [expanded])

  /* the simulation + render loop */
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const E = engine.current
    let alive = true

    const tick = () => {
      if (!alive) return
      const { w, h } = E.size
      const cx = w / 2
      const cy = h / 2
      const P = E.palette
      const nodes = E.nodes
      const edges = E.edges
      const now = performance.now()
      const time = (now - E.t0) / 1000

      /* ---- physics (cools via alpha) ---- */
      const settling = E.alpha > 0.02
      if (settling) {
        for (const n of nodes) {
          // centre gravity — stronger on the core so it stays put
          const g = n.depth === 0 ? 0.02 : 0.004
          n.vx += (cx - n.x) * g * E.alpha
          n.vy += (cy - n.y) * g * E.alpha
        }
        // repulsion (Fruchterman–Reingold-ish, capped)
        for (let i = 0; i < nodes.length; i++) {
          const a = nodes[i]
          for (let j = i + 1; j < nodes.length; j++) {
            const b = nodes[j]
            let dx = a.x - b.x
            let dy = a.y - b.y
            let d2 = dx * dx + dy * dy
            if (d2 < 1) {
              d2 = 1
              dx = Math.random() - 0.5
              dy = Math.random() - 0.5
            }
            const d = Math.sqrt(d2)
            const rep = Math.min(2600 / d2, 6) * E.alpha
            const ux = dx / d
            const uy = dy / d
            a.vx += ux * rep
            a.vy += uy * rep
            b.vx -= ux * rep
            b.vy -= uy * rep
            // soft collision
            const minD = a.r + b.r + 8
            if (d < minD) {
              const push = (minD - d) * 0.5
              a.vx += ux * push
              a.vy += uy * push
              b.vx -= ux * push
              b.vy -= uy * push
            }
          }
        }
        // springs
        for (const e of edges) {
          const a = E.byId.get(e.a)
          const b = E.byId.get(e.b)
          if (!a || !b) continue
          const dx = b.x - a.x
          const dy = b.y - a.y
          const d = Math.sqrt(dx * dx + dy * dy) || 1
          const k = (e.strong ? 0.012 : 0.006) * E.alpha
          const f = (d - e.rest) * k
          const ux = dx / d
          const uy = dy / d
          a.vx += ux * f
          a.vy += uy * f
          b.vx -= ux * f
          b.vy -= uy * f
        }
        // integrate
        for (const n of nodes) {
          if (n === E.byId.get(E.dragId ?? '') || n.pinned) {
            n.vx = 0
            n.vy = 0
            continue
          }
          n.vx *= 0.82
          n.vy *= 0.82
          const sp = Math.hypot(n.vx, n.vy)
          if (sp > 8) {
            n.vx = (n.vx / sp) * 8
            n.vy = (n.vy / sp) * 8
          }
          n.x += n.vx
          n.y += n.vy
          n.x = Math.max(n.r + 6, Math.min(w - n.r - 6, n.x))
          n.y = Math.max(n.r + 6, Math.min(h - n.r - 6, n.y))
        }
        E.alpha *= 0.985
        if (reduceMotion && E.alpha < 0.25) E.alpha = 0
      } else if (!reduceMotion) {
        // idle: whisper-slow orbital drift keeps the graph alive
        const spin = 0.0009
        for (const n of nodes) {
          if (n.depth === 0 || n.pinned || n === E.byId.get(E.dragId ?? '')) continue
          const dx = n.x - cx
          const dy = n.y - cy
          n.x = cx + dx * Math.cos(spin) - dy * Math.sin(spin)
          n.y = cy + dx * Math.sin(spin) + dy * Math.cos(spin)
        }
      }

      // intro reveal
      if (E.intro > 0) E.intro = Math.max(0, E.intro - 0.02)
      const reveal = 1 - E.intro * E.intro

      /* ---- render ---- */
      ctx.save()
      ctx.scale(E.dpr, E.dpr)
      ctx.clearRect(0, 0, w, h)

      // inner vignette + dot grid
      const vg = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.62)
      vg.addColorStop(0, withAlpha(P.edgeStrong, 0.07))
      vg.addColorStop(0.5, withAlpha(P.edgeStrong, 0.02))
      vg.addColorStop(1, 'transparent')
      ctx.fillStyle = vg
      ctx.fillRect(0, 0, w, h)
      ctx.fillStyle = withAlpha(P.textDim, 0.06)
      const gap = 34
      for (let gx = gap; gx < w; gx += gap)
        for (let gy = gap; gy < h; gy += gap) {
          ctx.beginPath()
          ctx.arc(gx, gy, 0.8, 0, Math.PI * 2)
          ctx.fill()
        }

      const hoverId = E.hoverId
      const near = hoverId ? E.adj.get(hoverId) : null
      const isLit = (id: string) => !hoverId || id === hoverId || !!near?.has(id)

      /* ---- edges ----
         Big graphs (SAME_EVENT meshes hit ~150 edges) stay readable and
         cheap: structural + relationship edges are each drawn as ONE batched
         faint stroke, a small rotating particle budget keeps it alive, and the
         hovered node's neighbourhood is redrawn richly on top. */
      ctx.lineCap = 'round'
      const ctrl = (a: SimNode, b: SimNode, bow: number) => {
        const dx = b.x - a.x
        const dy = b.y - a.y
        const len = Math.hypot(dx, dy) || 1
        return { x: (a.x + b.x) / 2 + (-dy / len) * bow, y: (a.y + b.y) / 2 + (dx / len) * bow }
      }

      // batched faint pass
      for (const strong of [false, true]) {
        ctx.beginPath()
        for (const e of edges) {
          if (e.strong !== strong) continue
          const a = E.byId.get(e.a)
          const b = E.byId.get(e.b)
          if (!a || !b) continue
          const c = ctrl(a, b, strong ? 16 : 6)
          ctx.moveTo(a.x, a.y)
          ctx.quadraticCurveTo(c.x, c.y, b.x, b.y)
        }
        ctx.strokeStyle = withAlpha(
          strong ? P.edgeStrong : P.edge,
          (hoverId ? 0.06 : strong ? 0.16 : 0.28) * reveal,
        )
        ctx.lineWidth = (strong ? 1.1 : 1) * reveal
        ctx.stroke()
      }

      // ambient flow — a rotating handful of strong edges, always alive
      if (!reduceMotion && !hoverId && reveal > 0.6) {
        const strongEdges = edges.filter((e) => e.strong)
        const budget = Math.min(12, strongEdges.length)
        const offset = Math.floor(time * 0.6) % Math.max(1, strongEdges.length)
        for (let i = 0; i < budget; i++) {
          const e = strongEdges[(offset + i * 3) % strongEdges.length]
          if (!e) continue
          const a = E.byId.get(e.a)
          const b = E.byId.get(e.b)
          if (!a || !b) continue
          const c = ctrl(a, b, 16)
          const t = (time * 0.4 + i / budget) % 1
          const it = 1 - t
          const px = it * it * a.x + 2 * it * t * c.x + t * t * b.x
          const py = it * it * a.y + 2 * it * t * c.y + t * t * b.y
          ctx.beginPath()
          ctx.arc(px, py, 1.7 * (0.5 + 0.5 * Math.sin(t * Math.PI)), 0, Math.PI * 2)
          ctx.fillStyle = withAlpha(lighten(nodeColor(b.kind, P), 40), 0.85)
          ctx.shadowColor = withAlpha(P.edgeStrong, 0.9)
          ctx.shadowBlur = 7
          ctx.fill()
          ctx.shadowBlur = 0
        }
      }

      // hovered neighbourhood — full treatment on top
      if (hoverId) {
        for (const e of edges) {
          if (e.a !== hoverId && e.b !== hoverId) continue
          const a = E.byId.get(e.a)
          const b = E.byId.get(e.b)
          if (!a || !b) continue
          const c = ctrl(a, b, e.strong ? 16 : 6)
          const cA = nodeColor(a.kind, P)
          const cB = nodeColor(b.kind, P)
          const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y)
          grad.addColorStop(0, withAlpha(cA, 0.7))
          grad.addColorStop(1, withAlpha(cB, 0.7))
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.quadraticCurveTo(c.x, c.y, b.x, b.y)
          ctx.strokeStyle = grad
          ctx.lineWidth = e.strong ? 2 : 1.4
          ctx.shadowColor = withAlpha(cB, 0.6)
          ctx.shadowBlur = 6
          ctx.stroke()
          ctx.shadowBlur = 0

          if (!reduceMotion) {
            for (let k = 0; k < (e.strong ? 3 : 2); k++) {
              const t = (time * 0.7 + k / 3) % 1
              const it = 1 - t
              const px = it * it * a.x + 2 * it * t * c.x + t * t * b.x
              const py = it * it * a.y + 2 * it * t * c.y + t * t * b.y
              ctx.beginPath()
              ctx.arc(px, py, 2 * (0.5 + 0.5 * Math.sin(t * Math.PI)), 0, Math.PI * 2)
              ctx.fillStyle = withAlpha(lighten(cB, 50), 0.95)
              ctx.shadowColor = withAlpha(cB, 1)
              ctx.shadowBlur = 9
              ctx.fill()
              ctx.shadowBlur = 0
            }
          }

          if (e.strong) {
            const ang = Math.atan2(b.y - c.y, b.x - c.x)
            const tx = b.x - Math.cos(ang) * (b.r + 3)
            const ty = b.y - Math.sin(ang) * (b.r + 3)
            ctx.beginPath()
            ctx.moveTo(tx, ty)
            ctx.lineTo(tx - 7 * Math.cos(ang - 0.42), ty - 7 * Math.sin(ang - 0.42))
            ctx.lineTo(tx - 7 * Math.cos(ang + 0.42), ty - 7 * Math.sin(ang + 0.42))
            ctx.closePath()
            ctx.fillStyle = withAlpha(cB, 0.85)
            ctx.fill()
          }
        }
      }

      /* nodes */
      for (const n of nodes) {
        const c = nodeColor(n.kind, P)
        const lit = isLit(n.id)
        const dim = hoverId && !lit
        const isHover = n.id === hoverId
        const target = n.baseR * (isHover ? 1.18 : 1)
        n.r += (target - n.r) * 0.2
        const R = n.r * reveal
        if (R < 0.5) continue

        // pulsing rings on the payment core
        if (n.depth === 0 && !reduceMotion && !dim) {
          for (let ring = 0; ring < 3; ring++) {
            const phase = (time * 0.5 + ring / 3) % 1
            ctx.beginPath()
            ctx.arc(n.x, n.y, R + phase * 46, 0, Math.PI * 2)
            ctx.strokeStyle = withAlpha(c, (1 - phase) * 0.35)
            ctx.lineWidth = 1.4
            ctx.stroke()
          }
        }

        // additive glow
        ctx.globalCompositeOperation = 'lighter'
        const glow = ctx.createRadialGradient(n.x, n.y, R * 0.2, n.x, n.y, R * (isHover ? 3.4 : 2.6))
        glow.addColorStop(0, withAlpha(c, dim ? 0.06 : isHover ? 0.4 : 0.26))
        glow.addColorStop(1, 'transparent')
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(n.x, n.y, R * 3.4, 0, Math.PI * 2)
        ctx.fill()
        ctx.globalCompositeOperation = 'source-over'

        // sphere body
        const body = ctx.createRadialGradient(
          n.x - R * 0.35,
          n.y - R * 0.4,
          R * 0.1,
          n.x,
          n.y,
          R,
        )
        body.addColorStop(0, withAlpha(lighten(c, 60), dim ? 0.25 : 0.9))
        body.addColorStop(0.55, withAlpha(c, dim ? 0.14 : 0.45))
        body.addColorStop(1, withAlpha(c, dim ? 0.08 : 0.16))
        ctx.beginPath()
        ctx.arc(n.x, n.y, R, 0, Math.PI * 2)
        ctx.fillStyle = body
        ctx.fill()

        // rim
        ctx.beginPath()
        ctx.arc(n.x, n.y, R, 0, Math.PI * 2)
        ctx.strokeStyle = withAlpha(c, dim ? 0.25 : isHover ? 1 : 0.75)
        ctx.lineWidth = isHover ? 2.4 : 1.6
        ctx.stroke()

        // top-left specular highlight
        if (!dim) {
          ctx.beginPath()
          ctx.arc(n.x, n.y, R * 0.82, Math.PI * 1.05, Math.PI * 1.6)
          ctx.strokeStyle = withAlpha('#ffffff', 0.5)
          ctx.lineWidth = 1.4
          ctx.stroke()
        }

        // pin marker
        if (n.pinned && !dim) {
          ctx.beginPath()
          ctx.arc(n.x + R * 0.7, n.y - R * 0.7, 2.4, 0, Math.PI * 2)
          ctx.fillStyle = P.text
          ctx.fill()
        }

        // label — core, hovered, or larger nodes
        const showLabel = n.depth === 0 || isHover || n.baseR >= 20
        if (showLabel && !dim && reveal > 0.7) {
          const txt = n.depth === 0 ? n.full : n.label
          ctx.font = `600 ${n.depth === 0 ? 12 : 10}px 'Space Grotesk', system-ui, sans-serif`
          const tw = ctx.measureText(txt).width
          const ly = n.y + R + (n.depth === 0 ? 16 : 13)
          ctx.fillStyle = withAlpha(P.bgInner, 0.72)
          const pad = 5
          roundRect(ctx, n.x - tw / 2 - pad, ly - 8, tw + pad * 2, 16, 5)
          ctx.fill()
          ctx.fillStyle = isHover ? P.text : P.textDim
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(txt, n.x, ly)
        }
      }

      ctx.restore()
      E.raf = requestAnimationFrame(tick)
    }

    tick()
    return () => {
      alive = false
      cancelAnimationFrame(E.raf)
    }
  }, [reduceMotion])

  /* ─────────  pointer handling  ───────── */

  const toLocal = (e: React.PointerEvent) => {
    const cv = canvasRef.current!
    const rect = cv.getBoundingClientRect()
    const { w, h } = engine.current.size
    return {
      x: ((e.clientX - rect.left) / rect.width) * w,
      y: ((e.clientY - rect.top) / rect.height) * h,
      px: e.clientX - rect.left,
      py: e.clientY - rect.top,
    }
  }
  const pick = (x: number, y: number): SimNode | null => {
    const ns = engine.current.nodes
    for (let i = ns.length - 1; i >= 0; i--) {
      if (Math.hypot(x - ns[i].x, y - ns[i].y) <= ns[i].r + 6) return ns[i]
    }
    return null
  }

  const dragMoved = useRef(false)

  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toLocal(e)
    const n = pick(x, y)
    if (n) {
      engine.current.dragId = n.id
      dragMoved.current = false
      canvasRef.current?.setPointerCapture(e.pointerId)
    }
  }
  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y, px, py } = toLocal(e)
    const E = engine.current
    if (E.dragId) {
      const n = E.byId.get(E.dragId)
      if (n) {
        if (Math.hypot(n.x - x, n.y - y) > 3) dragMoved.current = true
        n.x = x
        n.y = y
        n.vx = n.vy = 0
        E.alpha = Math.max(E.alpha, 0.35)
      }
      return
    }
    const n = pick(x, y)
    E.hoverId = n?.id ?? null
    if (canvasRef.current) canvasRef.current.style.cursor = n ? 'grab' : 'default'
    setHover(n ? { node: n, px, py } : null)
  }
  const onUp = () => {
    const E = engine.current
    const n = E.dragId ? E.byId.get(E.dragId) : null
    // a tap (no real drag) on a non-core node toggles its pin
    if (n && n.depth !== 0 && !dragMoved.current) {
      n.pinned = !n.pinned
      E.alpha = Math.max(E.alpha, 0.3)
    }
    E.dragId = null
  }
  const relayout = () => {
    for (const n of engine.current.nodes) n.pinned = false
    engine.current.alpha = 1
    engine.current.intro = 1
  }

  /* ─────────  render  ───────── */

  const P = engine.current.palette

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="glass-card-elevated p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="neo-pressed p-2.5 rounded-xl" style={{ background: withAlpha(P.edgeStrong, 0.12) }}>
            <GitBranch className="w-5 h-5" style={{ color: P.edgeStrong }} />
          </div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight" style={{ color: P.text }}>
            Evidence Graph Visualization
          </h2>
        </div>
        <p className="text-sm ml-12" style={{ color: P.textDim }}>
          Force-directed graph of evidence observations and the relationships between them, per payment.
        </p>
      </div>

      {/* controls */}
      <div className="glass-card p-4">
        <div className="flex items-end gap-4 flex-wrap">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs block mb-1.5 font-medium" style={{ color: P.textDim }}>
              Payment
            </label>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="glass-input w-full text-sm"
            >
              {payments.length === 0 && <option>No payments ingested yet</option>}
              {payments.map((p) => (
                <option key={p.razorpay_payment_id} value={p.razorpay_payment_id}>
                  {p.razorpay_payment_id}
                </option>
              ))}
            </select>
          </div>
          <div
            className="text-xs font-mono px-3 py-2 rounded-lg"
            style={{ background: withAlpha(P.textDim, 0.08), color: P.textDim }}
          >
            {counts.n} nodes · {counts.e} edges
          </div>
          <button onClick={relayout} className="neo-btn flex items-center gap-1.5 !py-2">
            <RotateCcw className="w-3.5 h-3.5" /> Re-layout
          </button>
        </div>
      </div>

      {/* canvas */}
      <div
        ref={wrapRef}
        className={`glass-card overflow-hidden relative ${
          expanded ? 'fixed inset-3 z-50 rounded-2xl' : ''
        }`}
      >
        <div className="absolute top-4 right-4 z-20 flex gap-2">
          <button onClick={() => setExpanded((v) => !v)} className="neo-btn !p-2">
            {expanded ? (
              <Minimize2 className="w-4 h-4" style={{ color: P.textDim }} />
            ) : (
              <Maximize2 className="w-4 h-4" style={{ color: P.textDim }} />
            )}
          </button>
        </div>

        <canvas
          ref={canvasRef}
          className="w-full block touch-none select-none"
          style={{ background: `radial-gradient(ellipse at 50% 40%, ${withAlpha(P.panel, 0.5)}, ${P.bgInner})` }}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerLeave={() => {
            engine.current.hoverId = null
            engine.current.dragId = null
            setHover(null)
          }}
        />

        {/* floating hover card */}
        {hover && (
          <div
            className="absolute z-20 pointer-events-none rounded-xl px-3 py-2 text-xs shadow-lg animate-scale-in"
            style={{
              left: Math.min(hover.px + 14, (wrapRef.current?.clientWidth ?? 800) - 200),
              top: hover.py + 14,
              background: withAlpha(P.panel, 0.95),
              border: `1px solid ${withAlpha(nodeColor(hover.node.kind, P), 0.5)}`,
              backdropFilter: 'blur(8px)',
            }}
          >
            <div className="font-bold" style={{ color: nodeColor(hover.node.kind, P) }}>
              {hover.node.full}
            </div>
            {hover.node.value != null && (
              <div className="font-mono mt-0.5" style={{ color: P.text }}>
                {hover.node.value}
              </div>
            )}
            {hover.node.source && (
              <div className="mt-0.5" style={{ color: P.textDim }}>
                source: {hover.node.source}
              </div>
            )}
            {hover.node.depth !== 0 && (
              <div className="mt-1 flex items-center gap-1" style={{ color: P.textDim }}>
                <Pin className="w-3 h-3" /> click to {hover.node.pinned ? 'release' : 'pin'}
              </div>
            )}
          </div>
        )}

        {counts.n === 0 && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Eye className="w-10 h-10 mx-auto mb-3" style={{ color: P.neutral }} />
              <p className="text-sm" style={{ color: P.textDim }}>
                {payments.length === 0
                  ? 'Ingest a payment webhook to build its evidence graph'
                  : 'No evidence graph for this payment yet'}
              </p>
            </div>
          </div>
        )}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: P.edgeStrong, borderTopColor: 'transparent' }} />
          </div>
        )}
      </div>

      {/* legend */}
      <div className="glass-card p-4">
        <div className="text-xs font-bold uppercase tracking-wider mb-3" style={{ color: P.textDim }}>
          Node types
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {LEGEND.map(([label, key]) => (
            <div key={label} className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ background: P[key], boxShadow: `0 0 8px ${withAlpha(P[key], 0.6)}` }}
              />
              <span className="text-[11px]" style={{ color: P.textDim }}>
                {label}
              </span>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <span className="inline-block w-5 h-px" style={{ background: P.edgeStrong }} />
            <span className="text-[11px]" style={{ color: P.textDim }}>
              relationship
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* small helper — rounded rect path */
function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}
