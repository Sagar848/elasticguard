'use client'
import { useState } from 'react'
import { executeAPI } from '@/lib/api'
import toast from 'react-hot-toast'
import {
  ChevronDown, ChevronRight, Copy, Play, AlertCircle,
  CheckCircle, Terminal, Globe, Send, Check
} from 'lucide-react'

export default function IssuePanel({ issues, solutions, clusterId }: {
  issues: any[]; solutions: any[]; clusterId: string
}) {
  const [open,   setOpen]   = useState<string | null>(null)
  const [filter, setFilter] = useState('all')
  const solMap = Object.fromEntries(solutions.map((s: any) => [s.issue_id, s]))
  const shown  = filter === 'all' ? issues : issues.filter(i => i.severity === filter)

  return (
    <div className="eg-page">
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Issues</h1>
          <p className="eg-page-sub">
            {issues.length} issue(s) · critical/high issues are auto-queued in Approvals
          </p>
        </div>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {['all','critical','high','medium','low'].map(s => {
          const cnt = s === 'all' ? issues.length : issues.filter(i => i.severity === s).length
          return (
            <button key={s}
              className={`eg-btn ${filter === s ? 'eg-btn-primary' : 'eg-btn-ghost'}`}
              style={{ fontSize: 12, padding: '5px 12px' }}
              onClick={() => setFilter(s)}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
              {cnt > 0 && <span style={{ opacity: .65, marginLeft: 4 }}>({cnt})</span>}
            </button>
          )
        })}
      </div>

      {shown.length === 0 && (
        <div className="eg-empty">
          <CheckCircle size={36} style={{ color: 'var(--green)', opacity: .5 }} />
          <p>No {filter !== 'all' ? filter + ' ' : ''}issues found</p>
        </div>
      )}

      <div className="eg-stack">
        {shown.map(issue => (
          <IssueRow key={issue.id} issue={issue} solution={solMap[issue.id]}
            clusterId={clusterId}
            expanded={open === issue.id}
            onToggle={() => setOpen(open === issue.id ? null : issue.id)} />
        ))}
      </div>
    </div>
  )
}

function IssueRow({ issue, solution, clusterId, expanded, onToggle }: any) {
  const [running, setRunning] = useState<Record<number, boolean>>({})
  const [ran,     setRan]     = useState<Record<number, boolean>>({})

  const apis    = solution?.apis || issue.elasticsearch_apis || []
  const cliCmds = solution?.cli_commands || issue.cli_commands || []
  const steps   = solution?.solution_steps || [issue.solution_summary].filter(Boolean)

  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const buildCurl = (api: any): string => {
    const body = api.body ? ` -d '${JSON.stringify(api.body)}'` : ''
    return `curl -X ${api.method} "http://localhost:9200${api.path}"${body} -H "Content-Type: application/json"`
  }

  const buildKibana = (api: any): string => {
    const bodyStr = api.body ? '\n' + JSON.stringify(api.body, null, 2) : ''
    return `${api.method} ${api.path}${bodyStr}`
  }

  const runApi = async (api: any, idx: number) => {
    const isWrite = api.method.toUpperCase() !== 'GET'
    if (isWrite) {
      const ok = window.confirm(
        `Run ${api.method} ${api.path}?\n\n` +
        `${api.description || ''}\n\n` +
        `This will modify the cluster. Proceed?`
      )
      if (!ok) return
    }
    setRunning(r => ({ ...r, [idx]: true }))
    try {
      await executeAPI(clusterId, { method: api.method, path: api.path, body: api.body })
      setRan(r => ({ ...r, [idx]: true }))
      toast.success(`${api.method} ${api.path} — executed successfully`)
    } catch (e: any) {
      toast.error(`Failed: ${e.message}`)
    } finally {
      setRunning(r => ({ ...r, [idx]: false }))
    }
  }

  return (
    <div className="eg-card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Header */}
      <button onClick={onToggle} style={{
        width: '100%', display: 'flex', alignItems: 'flex-start', gap: 12,
        padding: '14px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left'
      }}>
        <span className={`sev-${issue.severity}`} style={{ flexShrink: 0, marginTop: 1 }}>
          {issue.severity}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
            {issue.title}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: expanded ? 'normal' : 'nowrap' }}>
            {issue.description}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
            <span className="eg-badge" style={{ background: 'var(--bg-raised)', color: 'var(--text-muted)', border: '1px solid var(--border)', fontSize: 11 }}>
              {issue.category}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{issue.affected_resource}</span>
            {(issue.severity === 'critical' || issue.severity === 'high') && apis.some((a: any) => a.method?.toUpperCase() !== 'GET') && (
              <span className="eg-badge eg-badge-yellow" style={{ fontSize: 10 }}>Auto-queued in Approvals</span>
            )}
          </div>
        </div>
        <div style={{ flexShrink: 0, color: 'var(--text-muted)', paddingTop: 2 }}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </button>

      {/* Expanded */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '16px 16px 18px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Metrics */}
          {Object.keys(issue.metrics || {}).length > 0 && (
            <div>
              <p className="eg-section-title">Metrics</p>
              <div className="eg-grid3" style={{ gap: 8 }}>
                {Object.entries(issue.metrics).slice(0, 6).map(([k, v]: any) => (
                  <div key={k} className="eg-card-sm" style={{ padding: '8px 12px' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{k.replace(/_/g,' ')}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{String(v)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Solution steps */}
          {steps.length > 0 && (
            <div>
              <p className="eg-section-title">Solution</p>
              <ol style={{ paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {steps.map((s: string, i: number) => (
                  <li key={i} style={{ display: 'flex', gap: 10, fontSize: 13 }}>
                    <span style={{ flexShrink: 0, width: 20, height: 20, borderRadius: '50%', background: 'var(--accent-soft)', color: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, marginTop: 1 }}>{i + 1}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Elasticsearch API calls */}
          {apis.length > 0 && (
            <div>
              <p className="eg-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Globe size={11} />Elasticsearch APIs
              </p>
              <div className="eg-stack">
                {apis.map((api: any, i: number) => {
                  const isWrite = api.method?.toUpperCase() !== 'GET'
                  const methodColor = api.method === 'GET' ? 'var(--accent)' : api.method === 'DELETE' ? 'var(--red)' : 'var(--yellow)'
                  const kibanaSnippet = buildKibana(api)
                  const curlSnippet  = buildCurl(api)

                  return (
                    <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                      {/* Method + path bar */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--bg-base)' }}>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 8px', borderRadius: 99, background: `color-mix(in srgb, ${methodColor} 15%, transparent)`, color: methodColor }}>
                          {api.method}
                        </span>
                        <span className="eg-mono" style={{ flex: 1, fontSize: 12, color: 'var(--text-primary)' }}>{api.path}</span>
                        {/* Copy Kibana */}
                        <button onClick={() => copy(kibanaSnippet)} className="eg-btn eg-btn-ghost" style={{ fontSize: 11, padding: '2px 8px', gap: 4 }} title="Copy for Kibana Dev Tools">
                          <Copy size={10} />Kibana
                        </button>
                        {/* Copy cURL */}
                        <button onClick={() => copy(curlSnippet)} className="eg-btn eg-btn-ghost" style={{ fontSize: 11, padding: '2px 8px', gap: 4 }} title="Copy as cURL">
                          <Copy size={10} />cURL
                        </button>
                      </div>

                      {/* Description */}
                      {api.description && (
                        <div style={{ padding: '5px 12px', fontSize: 12, color: 'var(--text-secondary)', background: 'var(--bg-surface)' }}>
                          {api.description}
                        </div>
                      )}

                      {/* Body */}
                      {api.body && (
                        <pre className="eg-code-block" style={{ margin: 0, borderRadius: 0, border: 'none', borderTop: '1px solid var(--border)' }}>
                          {JSON.stringify(api.body, null, 2)}
                        </pre>
                      )}

                      {/* Kibana-ready snippet preview */}
                      <div className="eg-code-block" style={{ margin: 0, borderRadius: 0, border: 'none', borderTop: '1px solid var(--border)', fontSize: 11 }}>
                        <span className="eg-code-label">Kibana Dev Tools</span>
                        <code style={{ color: 'var(--green)' }}>{kibanaSnippet}</code>
                      </div>

                      {/* Action row */}
                      <div style={{ display: 'flex', gap: 8, padding: '8px 12px', background: 'var(--bg-app)', borderTop: '1px solid var(--border)', alignItems: 'center' }}>
                        {/* Run button — always present */}
                        {ran[i] ? (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--green)' }}>
                            <Check size={12} />Executed
                          </span>
                        ) : (
                          <button
                            className={`eg-btn ${isWrite ? 'eg-btn-warn' : 'eg-btn-success'}`}
                            style={{ fontSize: 12 }}
                            disabled={running[i]}
                            onClick={() => runApi(api, i)}>
                            {running[i]
                              ? <><div className="eg-spinner" style={{ width: 11, height: 11 }} />Running…</>
                              : <><Play size={11} />{isWrite ? 'Run (confirm)' : 'Run'}</>
                            }
                          </button>
                        )}
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {isWrite ? 'Will prompt for confirmation' : 'Read-only — safe to run anytime'}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* CLI Commands */}
          {cliCmds.length > 0 && (
            <div>
              <p className="eg-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Terminal size={11} />CLI Commands <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— run on server</span>
              </p>
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => copy(cliCmds.join('\n'))}
                  className="eg-btn eg-btn-ghost"
                  style={{ position: 'absolute', top: 6, right: 6, fontSize: 11, padding: '2px 8px', gap: 4, zIndex: 1 }}>
                  <Copy size={10} />Copy all
                </button>
                <div className="eg-code-block">
                  {cliCmds.map((cmd: string, i: number) => (
                    <div key={i} style={{ color: cmd.startsWith('#') ? 'var(--text-muted)' : 'var(--green)' }}>
                      {!cmd.startsWith('#') && <span style={{ color: 'var(--text-muted)', userSelect: 'none', marginRight: 8 }}>$</span>}
                      {cmd}
                    </div>
                  ))}
                </div>
              </div>
              <p style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                <AlertCircle size={10} />Run directly on Elasticsearch server node(s)
              </p>
            </div>
          )}

          {issue.docs_url && (
            <a href={issue.docs_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: 'var(--accent)' }}>
              📖 Elasticsearch Documentation →
            </a>
          )}
        </div>
      )}
    </div>
  )
}
