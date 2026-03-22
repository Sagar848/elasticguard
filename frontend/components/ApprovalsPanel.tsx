'use client'
import { useState, useEffect, useCallback } from 'react'
import { getPendingApprovals, resolveApproval } from '@/lib/api'
import toast from 'react-hot-toast'
import { RefreshCw, CheckCircle, XCircle, Clock, Shield, ChevronDown, ChevronRight, Copy } from 'lucide-react'

export default function ApprovalsPanel({ clusterId }: { clusterId: string }) {
  const [approvals, setApprovals] = useState<any[]>([])
  const [loading,   setLoading]   = useState(true)
  const [resolving, setResolving] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try { setApprovals(await getPendingApprovals()) } catch { setApprovals([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 15_000)
    return () => clearInterval(t)
  }, [load])

  const resolve = async (id: string, action: 'approve' | 'reject') => {
    setResolving(r => ({ ...r, [id]: true }))
    try {
      // token is empty — backend skips token check for direct UI approvals
      const result = await resolveApproval({ approval_id: id, token: '', action })
      if (action === 'approve') {
        const executed = result.executed || []
        const failed   = executed.filter((e: any) => !e.success)
        if (executed.length > 0 && failed.length === 0) {
          toast.success(`Approved & executed ${executed.length} API call(s) successfully`)
        } else if (failed.length > 0) {
          toast.error(`${failed.length} API call(s) failed after approval — check details`)
        } else {
          toast.success('Approved')
        }
      } else {
        toast('Action rejected — no changes made to cluster', { icon: '🚫' })
      }
      await load()
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setResolving(r => ({ ...r, [id]: false }))
    }
  }

  if (loading) return <div className="eg-center-screen"><div className="eg-spinner" /></div>

  const pending  = approvals.filter(a => a.status === 'pending')
  const resolved = approvals.filter(a => a.status !== 'pending')

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Approvals</h1>
          <p className="eg-page-sub">
            {pending.length > 0
              ? `${pending.length} pending — click Approve to execute immediately`
              : 'No pending approvals'}
          </p>
        </div>
        <button className="eg-btn eg-btn-ghost" onClick={load}><RefreshCw size={13} />Refresh</button>
      </div>

      {pending.length === 0 && resolved.length === 0 && (
        <div className="eg-empty">
          <Shield size={36} style={{ color: 'var(--green)', opacity: .5 }} />
          <p>No approval requests yet</p>
          <p style={{ fontSize: 12, maxWidth: 420, textAlign: 'center', color: 'var(--text-secondary)' }}>
            When a scan finds critical or high severity issues with fixable Elasticsearch APIs,
            they are automatically queued here. Click <strong>Approve &amp; Execute</strong> to run the fix instantly.
            Discord/Slack/Email channels (if configured in Settings) send the same approval request
            so you can approve remotely.
          </p>
        </div>
      )}

      {pending.length > 0 && (
        <section>
          <h2 className="eg-section-title">Pending ({pending.length})</h2>
          <div className="eg-stack">
            {pending.map(a => (
              <ApprovalCard key={a.id} a={a}
                resolving={!!resolving[a.id]}
                onApprove={() => resolve(a.id, 'approve')}
                onReject={() => resolve(a.id, 'reject')} />
            ))}
          </div>
        </section>
      )}

      {resolved.length > 0 && (
        <section>
          <h2 className="eg-section-title">History ({resolved.length})</h2>
          <div className="eg-stack">
            {resolved.slice(0, 30).map(a => (
              <ApprovalCard key={a.id} a={a} readOnly />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ApprovalCard({ a, resolving = false, onApprove, onReject, readOnly = false }: {
  a: any; resolving?: boolean; onApprove?: () => void; onReject?: () => void; readOnly?: boolean
}) {
  const [expanded, setExpanded] = useState(!readOnly && a.status === 'pending')

  const statusMeta: Record<string, any> = {
    pending:  { color: 'var(--yellow)',    label: 'Pending',             Icon: Clock },
    approved: { color: 'var(--green)',     label: 'Approved',            Icon: CheckCircle },
    rejected: { color: 'var(--red)',       label: 'Rejected',            Icon: XCircle },
    expired:  { color: 'var(--text-muted)', label: 'Expired',            Icon: Clock },
    executed: { color: 'var(--accent)',    label: 'Approved & Executed', Icon: CheckCircle },
  }
  const sm  = statusMeta[a.status] ?? statusMeta.pending
  const sevMap: Record<string, string> = {
    critical: 'sev-critical', high: 'sev-high', medium: 'sev-medium', low: 'sev-low'
  }

  const copy = (t: string) => { navigator.clipboard.writeText(t); toast.success('Copied') }
  const buildKibana = (api: any) => `${api.method} ${api.path}${api.body ? '\n' + JSON.stringify(api.body, null, 2) : ''}`

  return (
    <div className="eg-card" style={{ borderLeft: `3px solid ${sm.color}`, padding: 0, overflow: 'hidden' }}>
      {/* Header row */}
      <button onClick={() => setExpanded(e => !e)} style={{
        width: '100%', display: 'flex', alignItems: 'flex-start', gap: 12,
        padding: '14px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left'
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
            <span className={sevMap[a.severity] || 'sev-low'}>{a.severity}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{a.issue_title}</span>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
            {(a.issue_description || '').slice(0, 160)}{(a.issue_description || '').length > 160 ? '…' : ''}
          </p>
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
            <span>Cluster: <strong style={{ color: 'var(--text-secondary)' }}>{a.cluster_name}</strong></span>
            <span>Risk: <strong style={{ color: a.risk_level === 'high' || a.risk_level === 'critical' ? 'var(--red)' : a.risk_level === 'medium' ? 'var(--yellow)' : 'var(--green)' }}>{a.risk_level}</strong></span>
            {a.status === 'pending' && <span>Expires: {new Date(a.expires_at).toLocaleTimeString()}</span>}
            {a.resolved_at         && <span>Resolved: {new Date(a.resolved_at).toLocaleString()}</span>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <sm.Icon size={13} style={{ color: sm.color }} />
          <span style={{ fontSize: 12, color: sm.color, fontWeight: 500 }}>{sm.label}</span>
          {expanded ? <ChevronDown size={12} style={{ color: 'var(--text-muted)' }} /> : <ChevronRight size={12} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          <div className="eg-code-block">
            <span className="eg-code-label">Proposed action</span>
            <code>{a.action_description}</code>
          </div>

          {(a.api_calls || []).length > 0 && (
            <div>
              <p className="eg-section-title" style={{ marginBottom: 8 }}>Elasticsearch API Calls</p>
              <div className="eg-stack" style={{ gap: 8 }}>
                {(a.api_calls || []).map((api: any, i: number) => {
                  const mc = api.method === 'GET' ? 'var(--accent)' : api.method === 'DELETE' ? 'var(--red)' : 'var(--yellow)'
                  return (
                    <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', background: 'var(--bg-base)' }}>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 99, background: `color-mix(in srgb, ${mc} 15%, transparent)`, color: mc }}>
                          {api.method}
                        </span>
                        <span className="eg-mono" style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1 }}>{api.path}</span>
                        <button onClick={() => copy(buildKibana(api))} className="eg-btn eg-btn-ghost" style={{ fontSize: 10, padding: '2px 7px', gap: 3 }}>
                          <Copy size={9} />Kibana
                        </button>
                      </div>
                      {api.description && (
                        <div style={{ padding: '4px 12px', fontSize: 12, color: 'var(--text-secondary)', background: 'var(--bg-surface)' }}>
                          {api.description}
                        </div>
                      )}
                      {api.body && (
                        <pre className="eg-code-block" style={{ margin: 0, borderRadius: 0, border: 'none', borderTop: '1px solid var(--border)', fontSize: 11 }}>
                          {JSON.stringify(api.body, null, 2)}
                        </pre>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {(a.cli_commands || []).length > 0 && (
            <div>
              <p className="eg-section-title" style={{ marginBottom: 6 }}>CLI Commands (run on server)</p>
              <div style={{ position: 'relative' }}>
                <button onClick={() => copy((a.cli_commands || []).join('\n'))} className="eg-btn eg-btn-ghost"
                  style={{ position: 'absolute', top: 6, right: 6, fontSize: 10, padding: '2px 7px', zIndex: 1 }}>
                  <Copy size={9} />Copy
                </button>
                <div className="eg-code-block">
                  {(a.cli_commands || []).map((cmd: string, i: number) => (
                    <div key={i} style={{ color: cmd.startsWith('#') ? 'var(--text-muted)' : 'var(--green)' }}>
                      {!cmd.startsWith('#') && <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>$</span>}
                      {cmd}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!readOnly && a.status === 'pending' && (
            <div style={{ display: 'flex', gap: 8, paddingTop: 4, flexWrap: 'wrap' }}>
              <button className="eg-btn eg-btn-success" style={{ fontSize: 13, padding: '8px 20px' }}
                disabled={resolving} onClick={onApprove}>
                {resolving
                  ? <><div className="eg-spinner" style={{ width: 12, height: 12 }} />Executing…</>
                  : <><CheckCircle size={13} />Approve &amp; Execute</>
                }
              </button>
              <button className="eg-btn eg-btn-danger" style={{ fontSize: 13, padding: '8px 18px' }}
                disabled={resolving} onClick={onReject}>
                <XCircle size={13} />Reject
              </button>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', alignSelf: 'center' }}>
                Approve runs the API calls instantly on your cluster.
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
