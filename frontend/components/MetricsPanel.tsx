'use client'
import { useState, useEffect, useCallback } from 'react'
import { getLiveMetrics } from '@/lib/api'
import { RefreshCw, Cpu, HardDrive, Activity, GitBranch } from 'lucide-react'
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

interface Pt { time: string; [k: string]: any }

const NODE_COLORS = ['#3B82F6','#A78BFA','#34D399','#FBBF24','#F87171','#60A5FA']

export default function MetricsPanel({ clusterId, liveMetrics }: { clusterId: string; liveMetrics: any }) {
  const [history,   setHistory]   = useState<Pt[]>([])
  const [nodes,     setNodes]     = useState<any[]>([])
  const [loading,   setLoading]   = useState(false)

  const append = useCallback((m: any) => {
    const t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    const ns: any[] = m.nodes || []
    const pt: Pt = { time: t }
    ns.forEach(n => {
      pt[`${n.name}_cpu`]  = Math.round(n.cpu_pct  || 0)
      pt[`${n.name}_heap`] = Math.round(n.heap_pct || 0)
    })
    if (ns.length) {
      pt.avg_cpu  = Math.round(ns.reduce((s,n) => s + (n.cpu_pct  || 0), 0) / ns.length)
      pt.avg_heap = Math.round(ns.reduce((s,n) => s + (n.heap_pct || 0), 0) / ns.length)
      pt.avg_disk = Math.round(ns.reduce((s,n) => s + (n.disk_used_pct || n.disk_pct || 0), 0) / ns.length)
    }
    setHistory(p => [...p.slice(-29), pt])
    setNodes(ns)
  }, [])

  useEffect(() => { if (liveMetrics) append(liveMetrics) }, [liveMetrics, append])

  const refresh = useCallback(async () => {
    setLoading(true)
    try { append(await getLiveMetrics(clusterId)) } finally { setLoading(false) }
  }, [clusterId, append])

  useEffect(() => { const t = setInterval(refresh, 15_000); return () => clearInterval(t) }, [refresh])

  const last = history[history.length - 1] ?? {}

  const Tip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null
    return (
      <div style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
        <p style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</p>
        {payload.map((p: any) => (
          <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: p.color }} />
            <span style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
            <span style={{ fontWeight: 600, color: p.color, marginLeft: 'auto', paddingLeft: 12 }}>{p.value}%</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Real-Time Metrics</h1>
          <p className="eg-page-sub">Auto-refresh every 15 s · {history.length} data points</p>
        </div>
        <button className="eg-btn eg-btn-ghost" onClick={refresh} disabled={loading}>
          <RefreshCw size={13} style={{ animation: loading ? 'spin .7s linear infinite' : 'none' }} />Refresh
        </button>
      </div>

      {/* KPIs */}
      <div className="eg-kpi-row">
        {[
          { label: 'Avg CPU',   key: 'avg_cpu',  icon: Cpu,      color: '#3B82F6', warn: 70, crit: 85 },
          { label: 'Avg Heap',  key: 'avg_heap', icon: Activity, color: '#A78BFA', warn: 75, crit: 90 },
          { label: 'Avg Disk',  key: 'avg_disk', icon: HardDrive,color: '#34D399', warn: 80, crit: 90 },
          { label: 'Nodes',     key: '_nodes',   icon: GitBranch,color: '#FBBF24', warn: 9999, crit: 9999 },
        ].map(({ label, key, icon: Icon, color, warn, crit }) => {
          const val  = key === '_nodes' ? nodes.length : (typeof last[key] === 'number' ? last[key] : 0)
          const c    = val >= crit ? 'var(--red)' : val >= warn ? 'var(--yellow)' : color
          return (
            <div key={label} className="eg-kpi" style={{ borderTop: `2px solid ${c}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="eg-kpi-value" style={{ color: c }}>{Math.round(val as number)}{key !== '_nodes' ? '%' : ''}</span>
                <Icon size={16} style={{ color: c, opacity: .6 }} />
              </div>
              <span className="eg-kpi-label">{label}</span>
              {key !== '_nodes' && (
                <div className="eg-progress-track" style={{ marginTop: 6 }}>
                  <div className="eg-progress-fill" style={{ width: `${Math.min(val as number, 100)}%`, background: c }} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* CPU chart */}
      <div className="eg-card">
        <h3 className="eg-section-title">CPU Usage per Node</h3>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={history} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
            <defs>
              {nodes.slice(0,6).map((n, i) => (
                <linearGradient key={n.name} id={`cg${i}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor={NODE_COLORS[i]} stopOpacity={.25} />
                  <stop offset="100%" stopColor={NODE_COLORS[i]} stopOpacity={0}   />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
            <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} />
            <YAxis domain={[0,100]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} tickFormatter={v => `${v}%`} />
            <Tooltip content={<Tip />} />
            {nodes.slice(0,6).map((n, i) => (
              <Area key={n.name} type="monotone" dataKey={`${n.name}_cpu`} name={`${n.name} CPU`}
                stroke={NODE_COLORS[i]} fill={`url(#cg${i})`} strokeWidth={1.5} dot={false} />
            ))}
            {nodes.length === 0 && <Area type="monotone" dataKey="avg_cpu" name="Avg CPU" stroke="#3B82F6" fill="url(#cg0)" strokeWidth={2} dot={false} />}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* JVM chart */}
      <div className="eg-card">
        <h3 className="eg-section-title">JVM Heap Usage per Node</h3>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={history} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
            <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} />
            <YAxis domain={[0,100]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} tickFormatter={v => `${v}%`} />
            <Tooltip content={<Tip />} />
            {nodes.slice(0,6).map((n, i) => (
              <Line key={n.name} type="monotone" dataKey={`${n.name}_heap`} name={`${n.name} JVM`}
                stroke={NODE_COLORS[i]} strokeWidth={2} dot={false} />
            ))}
            {nodes.length === 0 && <Line type="monotone" dataKey="avg_heap" name="Avg Heap" stroke="#A78BFA" strokeWidth={2} dot={false} />}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Disk per node */}
      {nodes.length > 0 && (
        <div className="eg-card">
          <h3 className="eg-section-title">Disk Usage per Node</h3>
          <div className="eg-stack">
            {nodes.map((n, i) => {
              const d = n.disk_used_pct || n.disk_pct || 0
              const c = d >= 90 ? 'var(--red)' : d >= 80 ? 'var(--yellow)' : 'var(--green)'
              return (
                <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', width: 130, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.name}</span>
                  <div className="eg-progress-track" style={{ flex: 1 }}>
                    <div className="eg-progress-fill" style={{ width: `${Math.min(d, 100)}%`, background: c }} />
                  </div>
                  <span className="eg-mono" style={{ fontSize: 12, fontWeight: 600, color: c, width: 40, textAlign: 'right' }}>{Math.round(d)}%</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
