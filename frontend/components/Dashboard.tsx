'use client'
import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '@/lib/store'
import { runDiagnostics, getLiveMetrics, disconnectCluster } from '@/lib/api'
import { useClusterWebSocket } from '@/lib/useWebSocket'
import toast from 'react-hot-toast'
import {
  Activity, Database, AlertTriangle, Settings, Cpu,
  HardDrive, Network, Zap, RefreshCw, LogOut,
  DollarSign, GitBranch, Bot, Shield, Search,
} from 'lucide-react'
import IssuePanel      from './IssuePanel'
import TopologyView    from './TopologyView'
import MetricsPanel    from './MetricsPanel'
import SettingsPanel   from './SettingsPanel'
import AIChat          from './AIChat'
import ApprovalsPanel  from './ApprovalsPanel'
import CostPanel       from './CostPanel'
import SimulatorPanel  from './SimulatorPanel'
import QueryAnalyser   from './QueryAnalyser'
import ClusterManager  from './ClusterManager'

const NAV = [
  { id: 'dashboard',  label: 'Overview',      icon: Activity },
  { id: 'clusters',   label: 'Clusters',       icon: Database },
  { id: 'issues',     label: 'Issues',         icon: AlertTriangle },
  { id: 'topology',   label: 'Topology',       icon: Network },
  { id: 'metrics',    label: 'Metrics',        icon: Cpu },
  { id: 'queries',    label: 'Query Analyser', icon: Search },
  { id: 'chat',       label: 'AI Chat',        icon: Bot },
  { id: 'approvals',  label: 'Approvals',      icon: Shield },
  { id: 'cost',       label: 'Cost',           icon: DollarSign },
  { id: 'simulator',  label: 'Simulator',      icon: GitBranch },
  { id: 'settings',   label: 'Settings',       icon: Settings },
]

export default function Dashboard() {
  const {
    connection, setConnection,
    clusters, activeClusterId, setActiveCluster,
    activeView, setActiveView,
    diagnosisResults, setDiagnosisResult,
    diagnosisRunning, setDiagnosisRunning,
    liveMetricsMap, setLiveMetrics,
    aiConfig,
  } = useAppStore()

  // Derived from active cluster
  const diagnosisResult = diagnosisResults[activeClusterId ?? ''] ?? null
  const liveMetrics     = liveMetricsMap[activeClusterId ?? '']   ?? null
  const [live, setLive] = useState(true)
  const clusterId = activeClusterId ?? ''

  // Real-time WebSocket metrics stream
  const { status: wsStatus } = useClusterWebSocket(clusterId, {
    enabled: live,
    onMessage: (data) => {
      if (data.type === 'metrics') {
        setLiveMetrics(clusterId, {
          health: { status: data.health, unassigned_shards: data.unassigned },
          nodes: data.nodes || [],
        })
      }
    },
  })

  const runDiag = useCallback(async () => {
    if (!clusterId) return
    setDiagnosisRunning(true)
    try {
      const r = await runDiagnostics(clusterId, { use_ai: true, provider: aiConfig.provider, model: aiConfig.model })
      setDiagnosisResult(clusterId, r)
      const n = (r.issues || []).length
      const crit = (r.issues || []).filter((i: any) => i.severity === 'critical').length
      if (crit > 0)   toast.error(`${crit} critical issue(s) found`)
      else if (n > 0) toast(`${n} issue(s) detected`, { icon: '⚠️' })
      else            toast.success('Cluster is healthy')
    } catch (e: any) { toast.error(e.message) }
    finally { setDiagnosisRunning(false) }
  }, [clusterId, aiConfig, setDiagnosisResult, setDiagnosisRunning])

  const fetchMetrics = useCallback(async () => {
    if (!clusterId) return
    try { setLiveMetrics(clusterId, await getLiveMetrics(clusterId)) } catch { /* silent */ }
  }, [clusterId, setLiveMetrics])

  // Re-run diagnosis when switching active cluster
  useEffect(() => {
    if (activeClusterId) {
      fetchMetrics()
      // Only auto-diagnose if no cached result for this cluster
      if (!diagnosisResults[activeClusterId]) {
        runDiag()
      }
    }
  }, [activeClusterId])  // eslint-disable-line react-hooks/exhaustive-deps

  // Fallback polling when WebSocket not connected
  useEffect(() => {
    if (!live || wsStatus === 'connected') return
    const t = setInterval(fetchMetrics, 30_000)
    return () => clearInterval(t)
  }, [live, fetchMetrics, wsStatus])

  const handleDisconnect = async () => {
    if (clusterId) await disconnectCluster(clusterId).catch(() => {})
    setConnection(null)
  }

  const issues    = diagnosisResult?.issues || []
  const solutions = diagnosisResult?.solutions || []
  const health    = diagnosisResult?.report?.health_status || liveMetrics?.health?.status || 'unknown'
  const critical  = issues.filter((i: any) => i.severity === 'critical').length
  const high      = issues.filter((i: any) => i.severity === 'high').length

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg-app)' }}>

      {/* ── Sidebar ── */}
      <aside style={{ width: 212, flexShrink: 0, display: 'flex', flexDirection: 'column', background: 'var(--bg-base)', borderRight: '1px solid var(--border)', overflow: 'hidden' }}>

        {/* Logo */}
        <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent-soft)', border: '1px solid rgba(59,130,246,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Zap size={14} style={{ color: 'var(--accent)' }} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>ElasticGuard</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>ES {connection?.es_version || '?'}</div>
          </div>
        </div>

        {/* Cluster health pill */}
        <div style={{ margin: '10px 10px 4px', padding: '10px 12px', background: 'var(--bg-surface)', borderRadius: 8, border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
            <div className={`health-dot health-dot-${health === 'green' ? 'green' : health === 'yellow' ? 'yellow' : health === 'red' ? 'red' : 'unknown'}`} />
            <span style={{ fontSize: 12, fontWeight: 600, color: health === 'green' ? 'var(--green)' : health === 'yellow' ? 'var(--yellow)' : health === 'red' ? 'var(--red)' : 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>{health}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {connection?.url?.replace(/https?:\/\//, '') || '—'}
          {clusters.length > 1 && (
            <div style={{ fontSize: 10, color: 'var(--accent)', marginTop: 3 }}>
              {clusters.length} clusters connected
            </div>
          )}
          </div>
          {(critical > 0 || high > 0) && (
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              {critical > 0 && <span className="eg-badge eg-badge-red">{critical} critical</span>}
              {high > 0     && <span className="eg-badge eg-badge-yellow">{high} high</span>}
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '6px 8px', overflowY: 'auto' }}>
          {NAV.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`eg-nav-item${activeView === id ? ' active' : ''}`}
              onClick={() => setActiveView(id)}>
              <Icon size={14} />
              <span style={{ flex: 1 }}>{label}</span>
              {id === 'issues' && issues.length > 0 && (
                <span className={critical > 0 ? 'eg-badge eg-badge-red' : 'eg-badge eg-badge-yellow'} style={{ fontSize: 10, padding: '1px 6px' }}>
                  {issues.length}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Bottom */}
        <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <button className="eg-btn eg-btn-ghost" style={{ width: '100%', justifyContent: 'center', fontSize: 12 }}
            onClick={runDiag} disabled={diagnosisRunning}>
            <RefreshCw size={12} style={{ animation: diagnosisRunning ? 'spin .7s linear infinite' : 'none' }} />
            {diagnosisRunning ? 'Scanning…' : 'Re-scan'}
          </button>
          <button className="eg-btn eg-btn-danger" style={{ width: '100%', justifyContent: 'center', fontSize: 12 }}
            onClick={handleDisconnect}>
            <LogOut size={12} />Disconnect
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

        {/* Topbar */}
        <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-base)', position: 'sticky', top: 0, zIndex: 10 }}>
          <div>
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', textTransform: 'capitalize' }}>{activeView}</span>
            {diagnosisResult?.report?.cluster_name && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 10 }}>{diagnosisResult.report.cluster_name}</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {diagnosisRunning && (
              <span style={{ fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <div className="eg-spinner" style={{ width: 12, height: 12 }} />AI analysing…
              </span>
            )}
            <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color: wsStatus==='connected' ? 'var(--green)' : 'var(--text-muted)' }}>
              <div style={{ width:6, height:6, borderRadius:'50%', background: wsStatus==='connected' ? 'var(--green)' : wsStatus==='connecting' ? 'var(--yellow)' : 'var(--text-muted)', boxShadow: wsStatus==='connected' ? '0 0 6px var(--green)' : 'none' }} />
              {wsStatus === 'connected' ? 'WS Live' : wsStatus === 'connecting' ? 'Connecting…' : 'Polling'}
            </div>
            <button className={`eg-btn ${live ? 'eg-btn-success' : 'eg-btn-ghost'}`} style={{ fontSize: 12 }}
              onClick={() => setLive(p => !p)}>
              <Activity size={12} />{live ? 'Live' : 'Paused'}
            </button>
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: 24, flex: 1 }}>
          {activeView === 'dashboard'  && <OverviewPanel diagnosisResult={diagnosisResult} liveMetrics={liveMetrics} onNavigate={setActiveView} />}
          {activeView === 'clusters'   && <ClusterManager />}
          {activeView === 'issues'     && <IssuePanel issues={issues} solutions={solutions} clusterId={clusterId} />}
          {activeView === 'topology'   && <TopologyView clusterId={clusterId} />}
          {activeView === 'metrics'    && <MetricsPanel clusterId={clusterId} liveMetrics={liveMetrics} />}
          {activeView === 'queries'    && <QueryAnalyser clusterId={clusterId} />}
          {activeView === 'chat'       && <AIChat clusterId={clusterId} />}
          {activeView === 'approvals'  && <ApprovalsPanel clusterId={clusterId} />}
          {activeView === 'cost'       && <CostPanel clusterId={clusterId} />}
          {activeView === 'simulator'  && <SimulatorPanel clusterId={clusterId} />}
          {activeView === 'settings'   && <SettingsPanel />}
        </div>
      </main>
    </div>
  )
}

/* ── Overview ──────────────────────────────────────────────────────────────── */
function OverviewPanel({ diagnosisResult, liveMetrics, onNavigate }: { diagnosisResult: any; liveMetrics: any; onNavigate: (v: string) => void }) {
  const issues  = diagnosisResult?.issues || []
  const report  = diagnosisResult?.report || {}
  const nodes   = liveMetrics?.nodes   || []
  const health  = report.health_status || liveMetrics?.health?.status || 'unknown'

  const sev = (s: string) => issues.filter((i: any) => i.severity === s).length

  return (
    <div className="eg-page">
      {/* Health banner */}
      <div style={{
        padding: '16px 20px',
        borderRadius: 12,
        background: health === 'green' ? 'var(--green-soft)' : health === 'yellow' ? 'var(--yellow-soft)' : health === 'red' ? 'var(--red-soft)' : 'var(--bg-surface)',
        border: `1px solid ${health === 'green' ? 'rgba(52,211,153,.2)' : health === 'yellow' ? 'rgba(251,191,36,.2)' : health === 'red' ? 'rgba(248,113,113,.2)' : 'var(--border)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className={`health-dot health-dot-${health === 'green' ? 'green' : health === 'yellow' ? 'yellow' : health === 'red' ? 'red' : 'unknown'}`} style={{ width: 12, height: 12 }} />
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: health === 'green' ? 'var(--green)' : health === 'yellow' ? 'var(--yellow)' : health === 'red' ? 'var(--red)' : 'var(--text-secondary)' }}>
              Cluster is {health.toUpperCase()}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
              {issues.length === 0 ? 'All systems operational' : `${issues.length} issue(s) detected — AI analysis complete`}
            </div>
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-1px' }}>{report.node_count ?? '—'}</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>nodes</div>
        </div>
      </div>

      {/* KPIs */}
      <div className="eg-kpi-row">
        <KpiCard label="Critical" value={sev('critical')} color="var(--red)"    onClick={() => onNavigate('issues')} />
        <KpiCard label="High"     value={sev('high')}     color="var(--yellow)" onClick={() => onNavigate('issues')} />
        <KpiCard label="Medium"   value={sev('medium')}   color="var(--purple)" onClick={() => onNavigate('issues')} />
        <KpiCard label="Low"      value={sev('low')}      color="var(--accent)" onClick={() => onNavigate('issues')} />
      </div>

      {/* AI Summary */}
      {diagnosisResult?.summary && (
        <div className="eg-card" style={{ borderLeft: '3px solid var(--accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Bot size={14} style={{ color: 'var(--accent)' }} />
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.07em', color: 'var(--accent)' }}>AI Analysis Summary</span>
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{diagnosisResult.summary}</p>
        </div>
      )}

      {/* Top issues */}
      {issues.length > 0 && (
        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <h2 className="eg-section-title" style={{ margin: 0 }}>Top Issues</h2>
            <button onClick={() => onNavigate('issues')} style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>View all →</button>
          </div>
          <div className="eg-stack">
            {issues.slice(0, 5).map((issue: any) => (
              <button key={issue.id} onClick={() => onNavigate('issues')}
                className="eg-card" style={{ display: 'flex', alignItems: 'flex-start', gap: 12, textAlign: 'left', cursor: 'pointer', padding: '12px 16px' }}>
                <span className={`sev-${issue.severity}`}>{issue.severity}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>{issue.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.description}</div>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>{issue.category}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Node grid */}
      {nodes.length > 0 && (
        <section>
          <h2 className="eg-section-title">Node Health</h2>
          <div className="eg-grid3">
            {nodes.slice(0, 6).map((n: any) => (
              <div key={n.id} className="eg-card-sm">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Database size={12} style={{ color: 'var(--text-muted)' }} />
                  <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.name}</span>
                </div>
                {[
                  { label: 'CPU',  val: n.cpu_pct || 0 },
                  { label: 'JVM',  val: n.heap_pct || 0 },
                  { label: 'Disk', val: n.disk_used_pct || n.disk_pct || 0 },
                ].map(({ label, val }) => {
                  const c = val >= 90 ? 'var(--red)' : val >= 75 ? 'var(--yellow)' : 'var(--green)'
                  return (
                    <div key={label} style={{ marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 11 }}>
                        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                        <span style={{ color: c, fontWeight: 600 }}>{Math.round(val)}%</span>
                      </div>
                      <div className="eg-progress-track">
                        <div className="eg-progress-fill" style={{ width: `${Math.min(val,100)}%`, background: c }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function KpiCard({ label, value, color, onClick }: { label: string; value: number; color: string; onClick: () => void }) {
  return (
    <button className="eg-kpi" style={{ borderTop: `2px solid ${color}`, cursor: 'pointer', textAlign: 'left' }} onClick={onClick}>
      <span className="eg-kpi-value" style={{ color }}>{value}</span>
      <span className="eg-kpi-label">{label} Issues</span>
    </button>
  )
}
