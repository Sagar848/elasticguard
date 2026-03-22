'use client'
import { useState, useCallback } from 'react'
import { Search, RefreshCw, Play, Zap, Clock, AlertCircle, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`) }
  return res.json()
}

export default function QueryAnalyser({ clusterId }: { clusterId: string }) {
  const [tab,         setTab]         = useState<'slowqueries'|'profile'|'tasks'>('slowqueries')
  const [slowData,    setSlowData]    = useState<any>(null)
  const [profileRes,  setProfileRes]  = useState<any>(null)
  const [tasks,       setTasks]       = useState<any>(null)
  const [loading,     setLoading]     = useState(false)

  // Profile form state
  const [profIndex, setProfIndex]   = useState('*')
  const [profQuery, setProfQuery]   = useState('{\n  "query": {\n    "match_all": {}\n  }\n}')
  const [profError, setProfError]   = useState('')

  const loadSlow = useCallback(async () => {
    setLoading(true)
    try { setSlowData(await apiFetch(`/api/query/${clusterId}/slow-queries`)) }
    catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }, [clusterId])

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try { setTasks(await apiFetch(`/api/query/${clusterId}/tasks`)) }
    catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }, [clusterId])

  const runProfile = async () => {
    setProfError('')
    let parsed: any
    try { parsed = JSON.parse(profQuery) } catch { setProfError('Invalid JSON'); return }
    setLoading(true)
    try {
      const r = await apiFetch('/api/query/profile', { method: 'POST', body: JSON.stringify({ cluster_id: clusterId, index: profIndex, query: parsed }) })
      setProfileRes(r)
    } catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  const cancelTask = async (taskId: string) => {
    try {
      await apiFetch(`/api/query/${clusterId}/tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' })
      toast.success('Task cancelled')
      loadTasks()
    } catch (e: any) { toast.error(e.message) }
  }

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Query Analyser</h1>
          <p className="eg-page-sub">Detect slow queries, profile searches, inspect running tasks</p>
        </div>
      </div>

      <div className="eg-tabs">
        <button className={`eg-tab${tab === 'slowqueries' ? ' active' : ''}`} onClick={() => { setTab('slowqueries'); if (!slowData) loadSlow() }}>
          <Clock size={12} style={{ display: 'inline', marginRight: 5 }} />Slow Queries
        </button>
        <button className={`eg-tab${tab === 'profile' ? ' active' : ''}`} onClick={() => setTab('profile')}>
          <Zap size={12} style={{ display: 'inline', marginRight: 5 }} />Query Profiler
        </button>
        <button className={`eg-tab${tab === 'tasks' ? ' active' : ''}`} onClick={() => { setTab('tasks'); if (!tasks) loadTasks() }}>
          <Search size={12} style={{ display: 'inline', marginRight: 5 }} />Running Tasks
        </button>
      </div>

      {/* ── Slow Queries ── */}
      {tab === 'slowqueries' && (
        <div className="eg-page" style={{ gap: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="eg-btn eg-btn-ghost" onClick={loadSlow} disabled={loading}>
              <RefreshCw size={13} style={{ animation: loading ? 'spin .7s linear infinite' : 'none' }} />Refresh
            </button>
          </div>
          {!slowData && !loading && (
            <div className="eg-empty">
              <Clock size={32} style={{ color: 'var(--text-muted)', opacity: .5 }} />
              <p>Click Refresh to analyse query performance</p>
            </div>
          )}
          {loading && <div className="eg-center-screen"><div className="eg-spinner" /></div>}
          {slowData && (
            <>
              {/* Summary KPIs */}
              <div className="eg-kpi-row">
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--accent)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--accent)' }}>{slowData.total_indices}</span>
                  <span className="eg-kpi-label">Indices Analysed</span>
                </div>
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--red)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--red)' }}>{slowData.problematic_indices?.length || 0}</span>
                  <span className="eg-kpi-label">With Issues</span>
                </div>
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--yellow)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--yellow)' }}>
                    {slowData.all_indices?.[0]?.avg_query_ms ?? 0}ms
                  </span>
                  <span className="eg-kpi-label">Slowest Avg Query</span>
                </div>
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--green)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--green)' }}>
                    {slowData.all_indices?.[0]?.query_cache_hit_rate ?? 0}%
                  </span>
                  <span className="eg-kpi-label">Best Cache Rate</span>
                </div>
              </div>

              {/* Problematic indices */}
              {slowData.problematic_indices?.length > 0 && (
                <section>
                  <h2 className="eg-section-title">Indices with Issues</h2>
                  <div className="eg-stack">
                    {slowData.problematic_indices.map((idx: any) => (
                      <div key={idx.index} className="eg-card" style={{ borderLeft: `3px solid ${idx.severity === 'high' ? 'var(--red)' : 'var(--yellow)'}`, padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span className="eg-mono" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{idx.index}</span>
                          <span className={`sev-${idx.severity === 'high' ? 'high' : 'medium'}`}>{idx.severity}</span>
                          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>{idx.query_total.toLocaleString()} queries</span>
                        </div>
                        <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                          <span>Avg query: <strong style={{ color: idx.avg_query_ms > 2000 ? 'var(--red)' : 'var(--text-primary)' }}>{idx.avg_query_ms}ms</strong></span>
                          <span>Avg fetch: <strong style={{ color: 'var(--text-primary)' }}>{idx.avg_fetch_ms}ms</strong></span>
                          <span>Cache hit: <strong style={{ color: idx.query_cache_hit_rate < 30 ? 'var(--yellow)' : 'var(--green)' }}>{idx.query_cache_hit_rate}%</strong></span>
                        </div>
                        <ul style={{ paddingLeft: 16, margin: 0 }}>
                          {idx.issues.map((issue: string, i: number) => (
                            <li key={i} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* All indices table */}
              <section>
                <h2 className="eg-section-title">All Indices (sorted by avg query time)</h2>
                <div className="eg-card" style={{ padding: 0, overflow: 'hidden' }}>
                  <table className="eg-table">
                    <thead>
                      <tr>
                        <th>Index</th><th>Queries</th><th>Avg Query</th><th>Avg Fetch</th><th>Query Cache Hit</th><th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {slowData.all_indices?.slice(0, 30).map((idx: any) => (
                        <tr key={idx.index}>
                          <td className="eg-mono" style={{ color: 'var(--text-primary)', fontSize: 12 }}>{idx.index}</td>
                          <td>{idx.query_total.toLocaleString()}</td>
                          <td style={{ color: idx.avg_query_ms > 2000 ? 'var(--red)' : idx.avg_query_ms > 500 ? 'var(--yellow)' : 'var(--green)' }}>
                            <span className="eg-mono">{idx.avg_query_ms}ms</span>
                          </td>
                          <td><span className="eg-mono">{idx.avg_fetch_ms}ms</span></td>
                          <td style={{ color: idx.query_cache_hit_rate < 30 ? 'var(--yellow)' : 'var(--green)' }}>
                            <span className="eg-mono">{idx.query_cache_hit_rate}%</span>
                          </td>
                          <td>
                            {idx.severity === 'ok'
                              ? <span className="eg-badge eg-badge-green">OK</span>
                              : <span className={`sev-${idx.severity}`}>{idx.severity}</span>
                            }
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      )}

      {/* ── Profiler ── */}
      {tab === 'profile' && (
        <div className="eg-grid2" style={{ alignItems: 'start', gap: 16 }}>
          {/* Form */}
          <div className="eg-card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <h2 className="eg-page-title" style={{ fontSize: 15 }}>Profile a Query</h2>
            <div>
              <label className="eg-label">Index Pattern</label>
              <input className="eg-input eg-mono" value={profIndex} onChange={e => setProfIndex(e.target.value)} placeholder="my-index or logs-*" />
            </div>
            <div>
              <label className="eg-label">Query Body (JSON)</label>
              <textarea className="eg-input eg-mono" rows={10} value={profQuery} onChange={e => setProfQuery(e.target.value)}
                style={{ resize: 'vertical', lineHeight: 1.55 }} />
              {profError && <p style={{ color: 'var(--red)', fontSize: 12, marginTop: 4 }}>{profError}</p>}
            </div>
            <button className="eg-btn eg-btn-primary" onClick={runProfile} disabled={loading}>
              <Play size={13} />{loading ? 'Profiling…' : 'Run Profile'}
            </button>
          </div>

          {/* Results */}
          <div>
            {!profileRes && (
              <div className="eg-empty" style={{ border: '1px dashed var(--border)', borderRadius: 12, padding: 40 }}>
                <Zap size={32} style={{ color: 'var(--text-muted)', opacity: .5 }} />
                <p>Profile results will appear here</p>
              </div>
            )}
            {profileRes && (
              <div className="eg-card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {/* Summary */}
                <div className="eg-grid2" style={{ gap: 8 }}>
                  <div className="eg-kpi" style={{ borderTop: '2px solid var(--accent)', padding: '12px 14px' }}>
                    <span className="eg-kpi-value" style={{ fontSize: 22, color: 'var(--accent)' }}>{profileRes.total_time_ms}ms</span>
                    <span className="eg-kpi-label">Total Time</span>
                  </div>
                  <div className="eg-kpi" style={{ borderTop: '2px solid var(--green)', padding: '12px 14px' }}>
                    <span className="eg-kpi-value" style={{ fontSize: 22, color: 'var(--green)' }}>{profileRes.hits_total?.toLocaleString()}</span>
                    <span className="eg-kpi-label">Hits</span>
                  </div>
                </div>

                {/* Suggestions */}
                {profileRes.suggestions?.length > 0 && (
                  <div>
                    <h3 className="eg-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <AlertCircle size={11} />Optimisation Suggestions
                    </h3>
                    <div className="eg-stack" style={{ gap: 6 }}>
                      {profileRes.suggestions.map((s: string, i: number) => (
                        <div key={i} className="eg-banner eg-banner-warn" style={{ fontSize: 12 }}>{s}</div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Query breakdown */}
                {profileRes.query_breakdown?.length > 0 && (
                  <div>
                    <h3 className="eg-section-title">Query Breakdown (by time)</h3>
                    <div className="eg-card" style={{ padding: 0, overflow: 'hidden' }}>
                      <table className="eg-table">
                        <thead>
                          <tr><th>Type</th><th>Description</th><th style={{ textAlign: 'right' }}>Time (ms)</th></tr>
                        </thead>
                        <tbody>
                          {profileRes.query_breakdown.slice(0, 15).map((b: any, i: number) => (
                            <tr key={i}>
                              <td className="eg-mono" style={{ color: 'var(--accent)', fontSize: 11 }}>{b.type}</td>
                              <td style={{ fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.description}</td>
                              <td style={{ textAlign: 'right' }}>
                                <span className="eg-mono" style={{ color: b.time_ms > 1000 ? 'var(--red)' : b.time_ms > 200 ? 'var(--yellow)' : 'var(--green)' }}>
                                  {b.time_ms}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tasks ── */}
      {tab === 'tasks' && (
        <div className="eg-page" style={{ gap: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="eg-btn eg-btn-ghost" onClick={loadTasks} disabled={loading}>
              <RefreshCw size={13} style={{ animation: loading ? 'spin .7s linear infinite' : 'none' }} />Refresh
            </button>
          </div>
          {!tasks && !loading && (
            <div className="eg-empty">
              <Search size={32} style={{ color: 'var(--text-muted)', opacity: .5 }} />
              <p>Click Refresh to load running tasks</p>
            </div>
          )}
          {loading && <div className="eg-center-screen"><div className="eg-spinner" /></div>}
          {tasks && (
            <>
              <div className="eg-kpi-row">
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--accent)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--accent)' }}>{tasks.total_tasks}</span>
                  <span className="eg-kpi-label">Total Tasks</span>
                </div>
                <div className="eg-kpi" style={{ borderTop: '2px solid var(--yellow)' }}>
                  <span className="eg-kpi-value" style={{ color: 'var(--yellow)' }}>{tasks.long_running?.length || 0}</span>
                  <span className="eg-kpi-label">Long Running (&gt;30s)</span>
                </div>
              </div>

              {tasks.long_running?.length > 0 && (
                <section>
                  <h2 className="eg-section-title">Long Running Tasks</h2>
                  <div className="eg-stack">
                    {tasks.long_running.map((t: any) => (
                      <div key={t.id} className="eg-card" style={{ borderLeft: '3px solid var(--yellow)', padding: '12px 16px', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 3 }}>{t.action}</div>
                          <div className="eg-mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{t.description}</div>
                          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                            <span>Node: {t.node}</span>
                            <span>Running: <strong style={{ color: 'var(--yellow)' }}>{t.running_time}</strong></span>
                          </div>
                        </div>
                        {t.cancellable && (
                          <button className="eg-btn eg-btn-danger" style={{ fontSize: 11, flexShrink: 0 }} onClick={() => cancelTask(t.id)}>
                            <XCircle size={11} />Cancel
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section>
                <h2 className="eg-section-title">All Running Tasks</h2>
                <div className="eg-card" style={{ padding: 0, overflow: 'hidden' }}>
                  <table className="eg-table">
                    <thead>
                      <tr><th>Action</th><th>Node</th><th>Running Time</th><th></th></tr>
                    </thead>
                    <tbody>
                      {tasks.all_tasks?.slice(0, 40).map((t: any) => (
                        <tr key={t.id}>
                          <td style={{ fontSize: 12, color: 'var(--text-primary)' }}>{t.action}</td>
                          <td style={{ fontSize: 12 }}>{t.node}</td>
                          <td><span className="eg-mono" style={{ fontSize: 12, color: t.running_time_ms > 30000 ? 'var(--yellow)' : 'var(--text-secondary)' }}>{t.running_time}</span></td>
                          <td>
                            {t.cancellable && (
                              <button className="eg-btn eg-btn-ghost" style={{ fontSize: 11, padding: '3px 10px' }} onClick={() => cancelTask(t.id)}>
                                Cancel
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      )}
    </div>
  )
}
