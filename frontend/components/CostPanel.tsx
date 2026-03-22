'use client'
import { useState, useEffect, useCallback } from 'react'
import { getCostAnalysis } from '@/lib/api'
import { TrendingDown, RefreshCw, Zap, Archive, Trash2, Layers } from 'lucide-react'

interface Recommendation {
  type: string
  priority: 'high' | 'medium' | 'low'
  index: string
  description: string
  savings: string
  action: string
}

interface CostData {
  cluster_id: string
  total_recommendations: number
  recommendations: Recommendation[]
  summary: {
    total_indices_analyzed: number
    node_count: number
    high_priority: number
    medium_priority: number
    low_priority: number
  }
}

const P = {
  high:   { color: 'var(--red)',    bg: 'var(--red-soft)',    border: 'rgba(248,113,113,.22)', label: 'High' },
  medium: { color: 'var(--yellow)', bg: 'var(--yellow-soft)', border: 'rgba(251,191,36,.22)',  label: 'Medium' },
  low:    { color: 'var(--accent)', bg: 'var(--accent-soft)', border: 'rgba(59,130,246,.22)',  label: 'Low' },
}

const ICON: Record<string, any> = {
  add_replicas: Layers, reduce_replicas: Layers,
  split_shards: Zap, delete_empty: Trash2,
}

export default function CostPanel({ clusterId }: { clusterId: string }) {
  const [data,    setData]    = useState<CostData | null>(null)
  const [loading, setLoading] = useState(true)
  const [warn,    setWarn]    = useState('')

  const load = useCallback(async () => {
    setLoading(true); setWarn('')
    try {
      const r: CostData = await getCostAnalysis(clusterId)
      setData(r)
    } catch (e: any) {
      setWarn(e.message + ' — showing demo data')
      setData({
        cluster_id: clusterId,
        total_recommendations: 4,
        recommendations: [
          { type: 'add_replicas',    priority: 'high',   index: 'production-logs',   description: 'No replicas — single point of failure in a multi-node cluster.',    savings: 'Data safety',    action: 'PUT /production-logs/_settings {"index.number_of_replicas":1}' },
          { type: 'split_shards',   priority: 'medium', index: 'metrics-2024',       description: 'Average shard size is 72 GB — above the recommended 50 GB ceiling.', savings: 'Better balance', action: 'Reindex with 4 primary shards' },
          { type: 'reduce_replicas',priority: 'medium', index: 'archive-2022-*',     description: 'Cold archive with 2 replicas but < 1 query/min.',                    savings: '~18 GB disk',    action: 'PUT /archive-2022-*/_settings {"index.number_of_replicas":1}' },
          { type: 'delete_empty',   priority: 'low',    index: 'test-temp-idx',      description: '0 documents — wastes shard slots on the master.',                    savings: 'Shard overhead', action: 'DELETE /test-temp-idx' },
        ],
        summary: { total_indices_analyzed: 34, node_count: 3, high_priority: 1, medium_priority: 2, low_priority: 1 },
      })
    } finally { setLoading(false) }
  }, [clusterId])

  useEffect(() => { load() }, [load])

  if (loading) return (
    <div className="eg-center-screen">
      <div className="eg-spinner" />
      <span style={{ marginLeft: 10 }}>Analysing costs…</span>
    </div>
  )

  const recs   = data?.recommendations ?? []
  const summ   = data?.summary
  const high   = recs.filter(r => r.priority === 'high').length
  const medium = recs.filter(r => r.priority === 'medium').length
  const low    = recs.filter(r => r.priority === 'low').length

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Cost Optimizer</h1>
          <p className="eg-page-sub">
            AI-powered storage &amp; resource recommendations
            {summ ? ` · ${summ.total_indices_analyzed} indices · ${summ.node_count} node(s)` : ''}
          </p>
        </div>
        <button className="eg-btn eg-btn-ghost" onClick={load}>
          <RefreshCw size={13} />Refresh
        </button>
      </div>

      {warn && <div className="eg-banner eg-banner-warn">{warn}</div>}

      {/* KPIs */}
      <div className="eg-kpi-row">
        <Kpi label="Total"  value={String(recs.length)} color="var(--purple)" />
        <Kpi label="High"   value={String(high)}        color="var(--red)"    />
        <Kpi label="Medium" value={String(medium)}      color="var(--yellow)" />
        <Kpi label="Low"    value={String(low)}         color="var(--accent)" />
      </div>

      {/* Recommendations */}
      <section>
        <h2 className="eg-section-title">Recommendations ({recs.length})</h2>
        {recs.length === 0 ? (
          <div className="eg-empty">
            <TrendingDown size={36} style={{ color: 'var(--green)', opacity: .5 }} />
            <p>No recommendations — cluster looks well-optimised!</p>
          </div>
        ) : (
          <div className="eg-stack">
            {recs.map((rec, i) => {
              const meta = P[rec.priority] ?? P.low
              const Icon = ICON[rec.type] ?? Archive
              return (
                <div key={i} className="eg-card eg-rec-card" style={{ borderLeftColor: meta.color }}>
                  <div className="eg-rec-left">
                    <div className="eg-rec-icon" style={{ background: meta.bg, border: `1px solid ${meta.border}` }}>
                      <Icon size={15} style={{ color: meta.color }} />
                    </div>
                  </div>
                  <div className="eg-rec-body">
                    <div className="eg-rec-header">
                      <span className="eg-rec-title">{rec.description}</span>
                      <span className="eg-badge" style={{ background: meta.bg, color: meta.color, border: `1px solid ${meta.border}` }}>
                        {meta.label}
                      </span>
                    </div>
                    <div className="eg-rec-meta">
                      <span className="eg-mono" style={{ color: 'var(--text-muted)' }}>
                        index: <span style={{ color: 'var(--text-secondary)' }}>{rec.index}</span>
                      </span>
                      {rec.savings && rec.savings !== 'N/A' && (
                        <span className="eg-badge eg-badge-green">Save {rec.savings}</span>
                      )}
                    </div>
                    <div className="eg-code-block">
                      <span className="eg-code-label">Suggested action</span>
                      <code>{rec.action}</code>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

function Kpi({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="eg-kpi" style={{ borderTop: `2px solid ${color}` }}>
      <span className="eg-kpi-value" style={{ color }}>{value}</span>
      <span className="eg-kpi-label">{label} Priority</span>
    </div>
  )
}
