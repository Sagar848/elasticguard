'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useAppStore } from '@/lib/store'
import { getLiveMetrics } from '@/lib/api'
import { Database, HardDrive, Network, RefreshCw, ZoomIn, ZoomOut } from 'lucide-react'
import IndexTable from './IndexTable'

interface Node {
  id: string
  name: string
  type: 'master' | 'data' | 'ingest' | 'coordinating'
  health: 'green' | 'yellow' | 'red'
  cpu: number
  heap: number
  disk: number
  shards: number
  ip: string
  roles: string[]
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

interface TopoLink {
  source: string | Node
  target: string | Node
  type: 'shard' | 'replica'
  index?: string
}

interface TopoData {
  nodes: Node[]
  links: TopoLink[]
  indices: any[]
}

export default function TopologyView({ clusterId }: { clusterId: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [topoData, setTopoData] = useState<TopoData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const animRef = useRef<number>(0)
  const nodesRef = useRef<Node[]>([])
  const isDragging = useRef(false)
  const dragNode = useRef<Node | null>(null)
  const lastMouse = useRef({ x: 0, y: 0 })
  const isPanning = useRef(false)

  const fetchTopology = useCallback(async () => {
    setLoading(true)
    try {
      const metrics = await getLiveMetrics(clusterId)
      const rawNodes: any[] = metrics.nodes || []
      
      const nodes: Node[] = rawNodes.map((n: any, i: number) => {
        // Backend returns heap_used_pct (from nodes_stats) or heap_pct (from cat_nodes)
        const cpu  = n.cpu_pct  ?? n.cpu  ?? 0
        const heap = n.heap_used_pct ?? n.heap_pct ?? n.heap ?? 0
        const disk = n.disk_used_pct ?? n.disk_pct ?? n.disk ?? 0
        const health: 'red'|'yellow'|'green' =
          cpu > 90 || heap > 90 ? 'red' :
          cpu > 75 || heap > 75 || disk > 85 ? 'yellow' : 'green'
        return {
          id:     n.id || n.name,
          name:   n.name || `node-${i}`,
          type:   n.roles?.includes('master') ? 'master' : n.roles?.includes('data') ? 'data' : 'coordinating',
          health,
          cpu,
          heap,
          disk,
          shards: n.shard_count || 0,
          ip:     n.ip || '',
          roles:  n.roles || [],
        }
      })

      // Arrange nodes in circle
      const cx = 400, cy = 300, r = 180
      nodes.forEach((n, i) => {
        const angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2
        n.x = cx + r * Math.cos(angle)
        n.y = cy + r * Math.sin(angle)
        n.vx = 0
        n.vy = 0
      })

      // Backend now returns indices directly in the metrics response
      const indices: any[] = (metrics.indices || []).filter((idx: any) => idx.index && !idx.index.startsWith('.'))
      const links: TopoLink[] = []

      // Create links between nodes based on shard distribution
      if (nodes.length > 1) {
        nodes.forEach((n, i) => {
          const next = nodes[(i + 1) % nodes.length]
          links.push({ source: n.id, target: next.id, type: 'shard' })
        })
      }

      nodesRef.current = nodes
      setTopoData({ nodes, links, indices })
    } catch (e) {
      // Create demo topology if fetch fails
      const demo: Node[] = [
        { id: 'n1', name: 'master-1', type: 'master', health: 'green', cpu: 22, heap: 45, disk: 38, shards: 12, ip: '10.0.0.1', roles: ['master', 'data'], x: 400, y: 200, vx: 0, vy: 0 },
        { id: 'n2', name: 'data-1', type: 'data', health: 'green', cpu: 55, heap: 62, disk: 71, shards: 24, ip: '10.0.0.2', roles: ['data'], x: 280, y: 340, vx: 0, vy: 0 },
        { id: 'n3', name: 'data-2', type: 'data', health: 'yellow', cpu: 78, heap: 80, disk: 88, shards: 20, ip: '10.0.0.3', roles: ['data'], x: 520, y: 340, vx: 0, vy: 0 },
      ]
      nodesRef.current = demo
      setTopoData({ nodes: demo, links: [
        { source: 'n1', target: 'n2', type: 'shard' },
        { source: 'n1', target: 'n3', type: 'shard' },
        { source: 'n2', target: 'n3', type: 'replica' },
      ], indices: [] })
    } finally {
      setLoading(false)
    }
  }, [clusterId])

  useEffect(() => { fetchTopology() }, [fetchTopology])

  // Canvas rendering
  useEffect(() => {
    if (!topoData || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!

    const HEALTH_COLORS = { green: '#00FF88', yellow: '#FFD166', red: '#FF3860' }
    const TYPE_COLORS = { master: '#00D4FF', data: '#7C6FFB', ingest: '#FF6B35', coordinating: '#7A8FB5' }

    const draw = () => {
      const W = canvas.width, H = canvas.height
      ctx.clearRect(0, 0, W, H)

      ctx.save()
      ctx.translate(offset.x, offset.y)
      ctx.scale(zoom, zoom)

      const nodes = nodesRef.current
      const links = topoData.links

      // Resolve link endpoints
      const nodeMap = new Map(nodes.map(n => [n.id, n]))

      // Draw links
      links.forEach(link => {
        const src = typeof link.source === 'string' ? nodeMap.get(link.source) : link.source as Node
        const tgt = typeof link.target === 'string' ? nodeMap.get(link.target) : link.target as Node
        if (!src || !tgt || !src.x || !tgt.x) return

        ctx.beginPath()
        ctx.moveTo(src.x!, src.y!)
        ctx.lineTo(tgt.x!, tgt.y!)
        ctx.strokeStyle = link.type === 'replica' ? 'rgba(124,111,251,0.3)' : 'rgba(0,212,255,0.2)'
        ctx.lineWidth = link.type === 'replica' ? 1 : 1.5
        ctx.setLineDash(link.type === 'replica' ? [4, 4] : [])
        ctx.stroke()
        ctx.setLineDash([])
      })

      // Draw nodes
      nodes.forEach(node => {
        if (!node.x) return
        const x = node.x!, y = node.y!
        const r = node.type === 'master' ? 36 : 30
        const hColor = HEALTH_COLORS[node.health]
        const tColor = TYPE_COLORS[node.type]

        // Glow
        const grd = ctx.createRadialGradient(x, y, 0, x, y, r * 1.8)
        grd.addColorStop(0, `${hColor}22`)
        grd.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(x, y, r * 1.8, 0, Math.PI * 2)
        ctx.fillStyle = grd
        ctx.fill()

        // Circle
        ctx.beginPath()
        ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.fillStyle = '#141C35'
        ctx.fill()
        ctx.strokeStyle = selectedNode?.id === node.id ? hColor : tColor
        ctx.lineWidth = selectedNode?.id === node.id ? 3 : 1.5
        ctx.stroke()

        // Health ring
        const healthPct = node.cpu > node.heap ? node.cpu : node.heap
        ctx.beginPath()
        ctx.arc(x, y, r + 4, -Math.PI / 2, -Math.PI / 2 + (healthPct / 100) * 2 * Math.PI)
        ctx.strokeStyle = hColor
        ctx.lineWidth = 2
        ctx.stroke()

        // Icon / role
        ctx.fillStyle = tColor
        ctx.font = `bold ${node.type === 'master' ? 14 : 12}px monospace`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(node.type === 'master' ? 'M' : 'D', x, y - 4)

        // Name
        ctx.fillStyle = '#B8C5E0'
        ctx.font = '10px JetBrains Mono, monospace'
        ctx.fillText(node.name.length > 10 ? node.name.substring(0, 10) + '…' : node.name, x, y + 8)

        // Metrics below
        ctx.font = '9px monospace'
        ctx.fillStyle = node.cpu > 80 ? '#FF3860' : '#7A8FB5'
        ctx.fillText(`CPU ${Math.round(node.cpu)}%`, x, y + r + 14)
        ctx.fillStyle = node.heap > 80 ? '#FFD166' : '#7A8FB5'
        ctx.fillText(`JVM ${Math.round(node.heap)}%`, x, y + r + 26)
      })

      ctx.restore()
    }

    draw()

    const animate = () => {
      draw()
      animRef.current = requestAnimationFrame(animate)
    }
    animate()

    return () => cancelAnimationFrame(animRef.current)
  }, [topoData, selectedNode, zoom, offset])

  // Mouse interactions
  const getNodeAt = (ex: number, ey: number): Node | null => {
    const nodes = nodesRef.current
    const mx = (ex - offset.x) / zoom
    const my = (ey - offset.y) / zoom
    for (const n of nodes) {
      if (!n.x) continue
      const r = n.type === 'master' ? 36 : 30
      const d = Math.hypot(mx - n.x!, my - n.y!)
      if (d < r) return n
    }
    return null
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const node = getNodeAt(e.nativeEvent.offsetX, e.nativeEvent.offsetY)
    if (node) {
      isDragging.current = true
      dragNode.current = node
    } else {
      isPanning.current = true
    }
    lastMouse.current = { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const dx = e.nativeEvent.offsetX - lastMouse.current.x
    const dy = e.nativeEvent.offsetY - lastMouse.current.y
    if (isDragging.current && dragNode.current) {
      dragNode.current.x = (dragNode.current.x || 0) + dx / zoom
      dragNode.current.y = (dragNode.current.y || 0) + dy / zoom
    } else if (isPanning.current) {
      setOffset(o => ({ x: o.x + dx, y: o.y + dy }))
    }
    lastMouse.current = { x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY }
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDragging.current && !isPanning.current) return
    const moved = Math.abs(e.nativeEvent.offsetX - lastMouse.current.x) < 3
    if (moved && !isDragging.current) {
      const node = getNodeAt(e.nativeEvent.offsetX, e.nativeEvent.offsetY)
      setSelectedNode(node)
    }
    if (isDragging.current) {
      const node = getNodeAt(e.nativeEvent.offsetX, e.nativeEvent.offsetY)
      setSelectedNode(node)
    }
    isDragging.current = false
    isPanning.current = false
    dragNode.current = null
  }

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const node = getNodeAt(e.nativeEvent.offsetX, e.nativeEvent.offsetY)
    setSelectedNode(node)
  }

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Cluster Topology</h2>
          <p className="text-xs mt-0.5" style={{ color: '#7A8FB5' }}>
            Real-time node layout · drag nodes · click to inspect
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setZoom(z => Math.min(z + 0.2, 3))}
            className="p-1.5 rounded transition-all" style={{ border: '1px solid #1E2D50', color: '#7A8FB5' }}
            onMouseEnter={e => (e.currentTarget.style.color = '#00D4FF')}
            onMouseLeave={e => (e.currentTarget.style.color = '#7A8FB5')}>
            <ZoomIn size={14} />
          </button>
          <button onClick={() => setZoom(z => Math.max(z - 0.2, 0.3))}
            className="p-1.5 rounded transition-all" style={{ border: '1px solid #1E2D50', color: '#7A8FB5' }}
            onMouseEnter={e => (e.currentTarget.style.color = '#00D4FF')}
            onMouseLeave={e => (e.currentTarget.style.color = '#7A8FB5')}>
            <ZoomOut size={14} />
          </button>
          <button onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }) }}
            className="text-xs px-3 py-1.5 rounded transition-all" style={{ border: '1px solid #1E2D50', color: '#7A8FB5' }}>
            Reset
          </button>
          <button onClick={fetchTopology} disabled={loading}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded transition-all"
            style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: '#00D4FF' }}>
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Canvas */}
        <div className="col-span-2 rounded-xl overflow-hidden relative" style={{ background: '#0A0E1A', border: '1px solid #1E2D50', height: '520px' }}>
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center z-10" style={{ background: 'rgba(10,14,26,0.8)' }}>
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto mb-3" style={{ color: '#00D4FF' }} />
                <p className="text-xs" style={{ color: '#7A8FB5' }}>Loading topology...</p>
              </div>
            </div>
          )}
          <canvas
            ref={canvasRef}
            width={800}
            height={520}
            style={{ width: '100%', height: '100%', cursor: 'grab' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onClick={handleClick}
          />
          {/* Legend */}
          <div className="absolute bottom-3 left-3 flex gap-4 p-2 rounded-lg" style={{ background: 'rgba(10,14,26,0.85)', border: '1px solid #1E2D50' }}>
            {[
              { label: 'Master', color: '#00D4FF' },
              { label: 'Data', color: '#7C6FFB' },
              { label: 'Green', color: '#00FF88' },
              { label: 'Yellow', color: '#FFD166' },
              { label: 'Red', color: '#FF3860' },
            ].map(({ label, color }) => (
              <div key={label} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                <span className="text-xs" style={{ color: '#7A8FB5' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-3">
          {selectedNode ? (
            <NodeDetail node={selectedNode} />
          ) : (
            <div className="rounded-xl p-4" style={{ background: '#141C35', border: '1px solid #1E2D50' }}>
              <p className="text-xs text-center py-8" style={{ color: '#7A8FB5' }}>
                Click a node to inspect details
              </p>
            </div>
          )}

          {/* Node List */}
          <div className="rounded-xl overflow-hidden" style={{ background: '#141C35', border: '1px solid #1E2D50' }}>
            <div className="px-4 py-3" style={{ borderBottom: '1px solid #1E2D50' }}>
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: '#7A8FB5' }}>
                Nodes ({topoData?.nodes.length || 0})
              </span>
            </div>
            <div className="divide-y" style={{ borderColor: '#1E2D50' }}>
              {(topoData?.nodes || []).map(node => (
                <button key={node.id}
                  onClick={() => setSelectedNode(node)}
                  className="w-full px-4 py-3 text-left transition-all flex items-center gap-3"
                  style={{ background: selectedNode?.id === node.id ? 'rgba(0,212,255,0.05)' : 'transparent' }}>
                  <div className={`w-2 h-2 rounded-full shrink-0`}
                    style={{ background: node.health === 'green' ? '#00FF88' : node.health === 'yellow' ? '#FFD166' : '#FF3860', boxShadow: `0 0 6px ${node.health === 'green' ? '#00FF88' : node.health === 'yellow' ? '#FFD166' : '#FF3860'}` }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-white truncate">{node.name}</div>
                    <div className="text-xs" style={{ color: '#7A8FB5' }}>{node.type} · {node.shards} shards</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-mono" style={{ color: node.cpu > 80 ? '#FF3860' : '#7A8FB5' }}>
                      {Math.round(node.cpu)}%
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Index Table — paginated, sortable, filterable */}
          {(topoData?.indices?.length || 0) > 0 && (
            <IndexTable
              indices={topoData?.indices || []}
              title={`Indices (${topoData?.indices?.length || 0})`}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function NodeDetail({ node }: { node: Node }) {
  const healthColor = node.health === 'green' ? '#00FF88' : node.health === 'yellow' ? '#FFD166' : '#FF3860'
  
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: '#141C35', border: `1px solid ${healthColor}33` }}>
      <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid #1E2D50', background: `${healthColor}08` }}>
        <div className="w-2.5 h-2.5 rounded-full" style={{ background: healthColor, boxShadow: `0 0 8px ${healthColor}` }} />
        <span className="text-sm font-semibold text-white">{node.name}</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: `${healthColor}22`, color: healthColor }}>
          {node.type}
        </span>
      </div>
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'CPU', value: node.cpu, unit: '%', warn: 70, critical: 85 },
            { label: 'Heap (JVM)', value: node.heap, unit: '%', warn: 75, critical: 90 },
            { label: 'Disk', value: node.disk, unit: '%', warn: 80, critical: 90 },
          ].map(({ label, value, unit, warn, critical }) => {
            const color = value >= critical ? '#FF3860' : value >= warn ? '#FFD166' : '#00FF88'
            return (
              <div key={label} className="p-2 rounded" style={{ background: '#0A0E1A' }}>
                <div className="flex justify-between mb-1">
                  <span className="text-xs" style={{ color: '#7A8FB5' }}>{label}</span>
                  <span className="text-xs font-bold font-mono" style={{ color }}>{Math.round(value)}{unit}</span>
                </div>
                <div className="h-1.5 rounded-full" style={{ background: '#1E2D50' }}>
                  <div className="h-full rounded-full" style={{ width: `${Math.min(value, 100)}%`, background: color }} />
                </div>
              </div>
            )
          })}
          <div className="p-2 rounded" style={{ background: '#0A0E1A' }}>
            <div className="text-xs mb-1" style={{ color: '#7A8FB5' }}>Shards</div>
            <div className="text-lg font-bold font-mono" style={{ color: '#00D4FF' }}>{node.shards}</div>
          </div>
        </div>
        <div className="text-xs space-y-1" style={{ color: '#7A8FB5' }}>
          <div className="flex justify-between">
            <span>IP</span>
            <span className="font-mono text-white">{node.ip || 'n/a'}</span>
          </div>
          <div className="flex justify-between">
            <span>Roles</span>
            <span className="font-mono text-white">{node.roles.join(', ') || node.type}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
