'use client'
import { useState } from 'react'
import { simulateChange } from '@/lib/api'
import toast from 'react-hot-toast'
import { GitBranch, Play, Info, CheckCircle, AlertTriangle, XCircle } from 'lucide-react'

const SIM_TYPES = [
  { id: 'add_node',        label: 'Add Node',          desc: 'Predict impact of adding nodes — disk relief, shard rebalance, recovery time' },
  { id: 'remove_node',     label: 'Remove Node',       desc: 'Simulate decommissioning a node — shard redistribution & risk assessment' },
  { id: 'rebalance',       label: 'Rebalance Shards',  desc: 'Model full shard rebalance — how many shards move and estimated I/O impact' },
  { id: 'change_replicas', label: 'Change Replicas',   desc: 'Disk and redundancy impact of changing replica counts on an index pattern' },
]

export default function SimulatorPanel({ clusterId }: { clusterId: string }) {
  const [type,   setType]   = useState('add_node')
  const [params, setParams] = useState<Record<string, any>>({ count: 1, index: '*', replicas: 1 })
  const [result, setResult] = useState<any>(null)
  const [busy,   setBusy]   = useState(false)

  const run = async () => {
    setBusy(true); setResult(null)
    try {
      const r = await simulateChange(clusterId, { simulation_type: type, parameters: params })
      setResult(r)
    } catch (e: any) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Cluster Simulator</h1>
          <p className="eg-page-sub">Physics-based model — preview changes before applying them to your cluster</p>
        </div>
      </div>

      <div className="eg-grid2" style={{ alignItems: 'start' }}>
        {/* Config */}
        <div className="eg-card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label className="eg-label">Simulation Type</label>
            <div className="eg-stack" style={{ gap: 6 }}>
              {SIM_TYPES.map(s => (
                <button key={s.id} onClick={() => setType(s.id)} style={{
                  textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', transition: 'all .15s',
                  background: type === s.id ? 'var(--accent-soft)' : 'var(--bg-raised)',
                  border: `1px solid ${type === s.id ? 'var(--accent)' : 'var(--border)'}`,
                }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: type === s.id ? 'var(--accent)' : 'var(--text-primary)' }}>{s.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{s.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {(type === 'add_node' || type === 'remove_node') && (
            <div>
              <label className="eg-label">Node Count</label>
              <input className="eg-input" type="number" min={1} max={20} value={params.count}
                onChange={e => setParams(p => ({ ...p, count: parseInt(e.target.value) || 1 }))} />
            </div>
          )}

          {type === 'remove_node' && (
            <div>
              <label className="eg-label">Node Name (optional — omit to auto-select most loaded)</label>
              <input className="eg-input eg-mono" value={params.node_name || ''}
                onChange={e => setParams(p => ({ ...p, node_name: e.target.value || undefined }))}
                placeholder="e.g. node-1 (leave blank for auto)" />
            </div>
          )}

          {type === 'add_node' && (
            <div className="eg-grid2" style={{ gap: 10 }}>
              <div>
                <label className="eg-label">Disk per new node (GB, optional)</label>
                <input className="eg-input" type="number" min={50} placeholder="auto (avg of existing)"
                  value={params.disk_gb || ''}
                  onChange={e => setParams(p => ({ ...p, disk_gb: e.target.value ? parseFloat(e.target.value) : undefined }))} />
              </div>
              <div>
                <label className="eg-label">Heap per new node (GB, optional)</label>
                <input className="eg-input" type="number" min={1} max={32} placeholder="auto"
                  value={params.heap_gb || ''}
                  onChange={e => setParams(p => ({ ...p, heap_gb: e.target.value ? parseFloat(e.target.value) : undefined }))} />
              </div>
            </div>
          )}

          {type === 'change_replicas' && (
            <>
              <div>
                <label className="eg-label">Index Pattern</label>
                <input className="eg-input eg-mono" value={params.index}
                  onChange={e => setParams(p => ({ ...p, index: e.target.value }))}
                  placeholder="logs-* or my-index or * (all)" />
              </div>
              <div>
                <label className="eg-label">New Replica Count</label>
                <input className="eg-input" type="number" min={0} max={10} value={params.replicas}
                  onChange={e => setParams(p => ({ ...p, replicas: parseInt(e.target.value) }))} />
                {params.replicas === 0 && (
                  <p style={{ fontSize: 12, color: 'var(--red)', marginTop: 4 }}>
                    ⚠ Zero replicas means no redundancy — data loss if a node fails
                  </p>
                )}
              </div>
            </>
          )}

          <button className="eg-btn eg-btn-primary" onClick={run} disabled={busy}>
            <Play size={13} />{busy ? 'Simulating…' : 'Run Simulation'}
          </button>
        </div>

        {/* Results */}
        <div>
          {!result && !busy && (
            <div className="eg-empty" style={{ border: '1px dashed var(--border)', borderRadius: 12, padding: 40 }}>
              <GitBranch size={32} style={{ color: 'var(--text-muted)', opacity: .5 }} />
              <p>Configure and run a simulation</p>
              <p style={{ fontSize: 12 }}>Results are based on live cluster data — no changes are made</p>
            </div>
          )}
          {busy && <div className="eg-center-screen"><div className="eg-spinner" /><span style={{ marginLeft: 10 }}>Simulating…</span></div>}
          {result && <SimResult result={result} />}
        </div>
      </div>
    </div>
  )
}

function SimResult({ result }: { result: any }) {
  const impact = result.impact || {}
  const before = result.before || {}
  const after  = result.after  || {}

  const healthColor = (h: string) => h === 'green' ? 'var(--green)' : h === 'yellow' ? 'var(--yellow)' : h === 'red' ? 'var(--red)' : 'var(--text-muted)'
  const healthDot   = (h: string) => h === 'green' ? 'health-dot-green' : h === 'yellow' ? 'health-dot-yellow' : h === 'red' ? 'health-dot-red' : 'health-dot-unknown'

  return (
    <div className="eg-card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Health change */}
      {(impact.health_before || impact.health_after) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 8, background: 'var(--bg-raised)', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className={`health-dot ${healthDot(impact.health_before)}`} />
            <span style={{ fontSize: 13, fontWeight: 600, color: healthColor(impact.health_before) }}>{(impact.health_before || '?').toUpperCase()}</span>
          </div>
          <span style={{ color: 'var(--text-muted)', fontSize: 18 }}>→</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className={`health-dot ${healthDot(impact.health_after)}`} />
            <span style={{ fontSize: 13, fontWeight: 600, color: healthColor(impact.health_after) }}>{(impact.health_after || '?').toUpperCase()}</span>
          </div>
          {impact.health_improved !== undefined && (
            impact.health_improved
              ? <span className="eg-badge eg-badge-green" style={{ marginLeft: 'auto' }}>✓ Improves health</span>
              : <span className="eg-badge eg-badge-yellow" style={{ marginLeft: 'auto' }}>No health change</span>
          )}
        </div>
      )}

      {/* Before / After comparison */}
      {before.node_count !== undefined && after.node_count !== undefined && (
        <div>
          <p className="eg-section-title">Before / After</p>
          <div className="eg-grid2" style={{ gap: 8 }}>
            <SnapshotCard label="Before" snap={before} />
            <SnapshotCard label="After"  snap={after}  highlight />
          </div>
        </div>
      )}

      {/* Impact metrics */}
      {Object.keys(impact).length > 0 && (
        <div>
          <p className="eg-section-title">Impact Analysis</p>
          <div className="eg-grid2" style={{ gap: 8 }}>
            {Object.entries(impact)
              .filter(([k]) => !['health_before','health_after','health_improved'].includes(k))
              .map(([k, v]) => {
                const isRisk  = typeof v === 'string' && ['high','critical'].includes(v as string)
                const isWarn  = typeof v === 'string' && v === 'medium'
                const isGood  = typeof v === 'boolean' && v === true
                const isBad   = typeof v === 'boolean' && v === false
                const color   = isRisk ? 'var(--red)' : isWarn ? 'var(--yellow)' : isGood ? 'var(--green)' : isBad ? 'var(--red)' : 'var(--text-primary)'
                return (
                  <div key={k} style={{ padding: '8px 12px', borderRadius: 8, background: 'var(--bg-raised)', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 3 }}>
                      {k.replace(/_/g, ' ')}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color }}>{String(v)}</div>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* Warnings */}
      {result.warnings?.length > 0 && (
        <div className="eg-stack" style={{ gap: 6 }}>
          {result.warnings.map((w: string, i: number) => (
            <div key={i} className="eg-banner eg-banner-warn" style={{ display: 'flex', gap: 8, fontSize: 12 }}>
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Recommendation */}
      {result.recommendation && (
        <div className="eg-banner eg-banner-ok" style={{ fontSize: 12 }}>
          <CheckCircle size={13} style={{ display: 'inline', marginRight: 6 }} />
          {result.recommendation}
        </div>
      )}

      {/* Elasticsearch API */}
      {result.elasticsearch_api && (
        <div>
          <p className="eg-section-title">Elasticsearch API to Apply</p>
          <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--bg-base)' }}>
              <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 8px', borderRadius: 99, background: 'rgba(251,191,36,.15)', color: 'var(--yellow)' }}>
                {result.elasticsearch_api.method}
              </span>
              <span className="eg-mono" style={{ fontSize: 12, color: 'var(--text-primary)' }}>{result.elasticsearch_api.path}</span>
            </div>
            {result.elasticsearch_api.description && (
              <div style={{ padding: '4px 12px 6px', fontSize: 12, color: 'var(--text-secondary)' }}>{result.elasticsearch_api.description}</div>
            )}
            {result.elasticsearch_api.body && (
              <pre className="eg-code-block" style={{ margin: 0, borderRadius: 0, border: 'none', borderTop: '1px solid var(--border)' }}>
                {JSON.stringify(result.elasticsearch_api.body, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      {result.disclaimer && (
        <div style={{ display: 'flex', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
          <Info size={12} style={{ flexShrink: 0, marginTop: 1 }} />
          {result.disclaimer}
        </div>
      )}
    </div>
  )
}

function SnapshotCard({ label, snap, highlight = false }: { label: string; snap: any; highlight?: boolean }) {
  const fields = [
    { k: 'node_count',          l: 'Nodes' },
    { k: 'data_node_count',     l: 'Data nodes' },
    { k: 'total_shards',        l: 'Total shards' },
    { k: 'unassigned_shards',   l: 'Unassigned' },
    { k: 'avg_shards_per_node', l: 'Avg shards/node' },
    { k: 'avg_disk_used_pct',   l: 'Avg disk used %' },
    { k: 'balance_score',       l: 'Balance score' },
  ]
  return (
    <div style={{ padding: '12px 14px', borderRadius: 8, background: highlight ? 'var(--accent-soft)' : 'var(--bg-raised)', border: `1px solid ${highlight ? 'rgba(59,130,246,.25)' : 'var(--border)'}` }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.07em', color: highlight ? 'var(--accent)' : 'var(--text-muted)', marginBottom: 10 }}>{label}</div>
      {fields.map(({ k, l }) => snap[k] !== undefined && (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 12 }}>
          <span style={{ color: 'var(--text-muted)' }}>{l}</span>
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{String(snap[k])}</span>
        </div>
      ))}
    </div>
  )
}
