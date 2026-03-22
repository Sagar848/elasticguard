'use client'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { CheckCircle, XCircle, Clock, AlertTriangle, Terminal, Globe } from 'lucide-react'

export default function ApprovePage({ params }: { params: { id: string } }) {
  const searchParams = useSearchParams()
  const token  = searchParams.get('token')  || ''
  const action = searchParams.get('action') || ''

  const [status,   setStatus]   = useState<'loading'|'confirming'|'success'|'error'>('loading')
  const [approval, setApproval] = useState<any>(null)
  const [message,  setMessage]  = useState('')
  const [resolving, setResolving] = useState(false)

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  useEffect(() => {
    fetch(`${API}/api/approval/${params.id}`)
      .then(r => r.json())
      .then(d => {
        setApproval(d)
        if (d.status !== 'pending') {
          setStatus('success')
          setMessage(`This request was already ${d.status}.`)
        } else if (action === 'approve' || action === 'reject') {
          setStatus('confirming')
        } else {
          setStatus('confirming')
        }
      })
      .catch(() => { setStatus('error'); setMessage('Could not load approval request.') })
  }, [params.id])

  const resolve = async (act: 'approve' | 'reject') => {
    setResolving(true)
    try {
      const res = await fetch(`${API}/api/approval/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: params.id, token, action: act }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed')
      setStatus('success')
      setMessage(act === 'approve'
        ? 'Action approved. ElasticGuard will execute the fix on your cluster.'
        : 'Action rejected. No changes will be made to the cluster.')
    } catch (e: any) {
      setStatus('error')
      setMessage(e.message)
    } finally {
      setResolving(false)
    }
  }

  const severityColor: Record<string, string> = {
    critical: '#F87171', high: '#FBBF24', medium: '#A78BFA', low: '#60A5FA'
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0D1117', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ width: '100%', maxWidth: 560 }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 13, color: '#8B949E', marginBottom: 6, letterSpacing: '.05em', textTransform: 'uppercase' }}>ElasticGuard</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#F0F6FC', letterSpacing: '-0.5px' }}>Cluster Action Approval</h1>
        </div>

        {/* Loading */}
        {status === 'loading' && (
          <div style={{ textAlign: 'center', color: '#8B949E', padding: 48 }}>
            <div style={{ width: 24, height: 24, border: '2px solid #21293A', borderTopColor: '#3B82F6', borderRadius: '50%', animation: 'spin .7s linear infinite', margin: '0 auto 12px' }} />
            Loading approval details…
          </div>
        )}

        {/* Confirming */}
        {status === 'confirming' && approval && (
          <div style={{ background: '#161B22', border: '1px solid rgba(255,255,255,.07)', borderRadius: 14, overflow: 'hidden' }}>
            {/* Status bar */}
            <div style={{ background: '#21293A', padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid rgba(255,255,255,.07)' }}>
              <Clock size={14} style={{ color: '#FBBF24' }} />
              <span style={{ fontSize: 12, color: '#FBBF24', fontWeight: 500 }}>PENDING APPROVAL</span>
              <span style={{ marginLeft: 'auto', fontSize: 11, color: '#484F58' }}>
                Expires {new Date(approval.expires_at).toLocaleString()}
              </span>
            </div>

            <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* Issue */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 99, background: `${severityColor[approval.severity] || '#60A5FA'}18`, color: severityColor[approval.severity] || '#60A5FA', border: `1px solid ${severityColor[approval.severity] || '#60A5FA'}30` }}>
                    {(approval.severity || 'unknown').toUpperCase()}
                  </span>
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#F0F6FC' }}>{approval.issue_title}</span>
                </div>
                <p style={{ fontSize: 13, color: '#8B949E', lineHeight: 1.65 }}>{approval.issue_description}</p>
              </div>

              {/* Cluster + risk */}
              <div style={{ display: 'flex', gap: 12 }}>
                <InfoChip label="Cluster" value={approval.cluster_name} />
                <InfoChip label="Risk Level" value={(approval.risk_level || '?').toUpperCase()} valueColor={approval.risk_level === 'high' ? '#F87171' : approval.risk_level === 'medium' ? '#FBBF24' : '#34D399'} />
              </div>

              {/* Proposed action */}
              <div>
                <div style={{ fontSize: 11, color: '#484F58', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Globe size={11} />Proposed Action
                </div>
                <div style={{ background: '#0D1117', border: '1px solid rgba(255,255,255,.07)', borderRadius: 8, padding: '10px 14px', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#F0F6FC', wordBreak: 'break-all' }}>
                  {approval.action_description}
                </div>
              </div>

              {/* API calls */}
              {approval.api_calls?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#484F58', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Globe size={11} />Elasticsearch API Calls
                  </div>
                  {approval.api_calls.map((api: any, i: number) => (
                    <div key={i} style={{ background: '#0D1117', border: '1px solid rgba(255,255,255,.07)', borderRadius: 8, padding: '10px 14px', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: api.body ? 6 : 0 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 99, background: api.method === 'GET' ? 'rgba(59,130,246,.15)' : 'rgba(251,191,36,.15)', color: api.method === 'GET' ? '#60A5FA' : '#FBBF24' }}>{api.method}</span>
                        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#F0F6FC' }}>{api.path}</span>
                      </div>
                      {api.body && <pre style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#8B949E', margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(api.body, null, 2)}</pre>}
                      {api.description && <div style={{ fontSize: 12, color: '#8B949E', marginTop: 4 }}>{api.description}</div>}
                    </div>
                  ))}
                </div>
              )}

              {/* CLI commands */}
              {approval.cli_commands?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#484F58', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Terminal size={11} />CLI Commands (run on server)
                  </div>
                  <div style={{ background: '#0D1117', border: '1px solid rgba(255,255,255,.07)', borderRadius: 8, padding: '10px 14px', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
                    {approval.cli_commands.map((cmd: string, i: number) => (
                      <div key={i} style={{ color: cmd.startsWith('#') ? '#484F58' : '#34D399' }}>
                        {!cmd.startsWith('#') && <span style={{ color: '#484F58', marginRight: 8 }}>$</span>}
                        {cmd}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 12, paddingTop: 4 }}>
                <button disabled={resolving} onClick={() => resolve('approve')} style={{ flex: 1, padding: '11px 16px', borderRadius: 8, background: resolving ? '#21293A' : '#16a34a', border: 'none', color: '#fff', fontSize: 14, fontWeight: 600, cursor: resolving ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'background .15s' }}>
                  <CheckCircle size={16} />
                  {resolving ? 'Processing…' : 'Approve & Execute'}
                </button>
                <button disabled={resolving} onClick={() => resolve('reject')} style={{ flex: 1, padding: '11px 16px', borderRadius: 8, background: 'transparent', border: '1px solid rgba(248,113,113,.3)', color: '#F87171', fontSize: 14, fontWeight: 600, cursor: resolving ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <XCircle size={16} />
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Success */}
        {status === 'success' && (
          <div style={{ background: '#161B22', border: '1px solid rgba(255,255,255,.07)', borderRadius: 14, padding: 40, textAlign: 'center' }}>
            <CheckCircle size={48} style={{ color: '#34D399', margin: '0 auto 16px' }} />
            <h2 style={{ fontSize: 18, fontWeight: 600, color: '#F0F6FC', marginBottom: 8 }}>Done</h2>
            <p style={{ fontSize: 14, color: '#8B949E', lineHeight: 1.65 }}>{message}</p>
            <a href="/" style={{ display: 'inline-block', marginTop: 24, padding: '9px 20px', borderRadius: 8, background: 'rgba(59,130,246,.15)', border: '1px solid rgba(59,130,246,.3)', color: '#60A5FA', fontSize: 13, textDecoration: 'none' }}>
              Open ElasticGuard →
            </a>
          </div>
        )}

        {/* Error */}
        {status === 'error' && (
          <div style={{ background: '#161B22', border: '1px solid rgba(248,113,113,.2)', borderRadius: 14, padding: 40, textAlign: 'center' }}>
            <AlertTriangle size={48} style={{ color: '#F87171', margin: '0 auto 16px' }} />
            <h2 style={{ fontSize: 18, fontWeight: 600, color: '#F0F6FC', marginBottom: 8 }}>Error</h2>
            <p style={{ fontSize: 14, color: '#8B949E' }}>{message}</p>
          </div>
        )}

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  )
}

function InfoChip({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ flex: 1, background: '#21293A', border: '1px solid rgba(255,255,255,.07)', borderRadius: 8, padding: '8px 12px' }}>
      <div style={{ fontSize: 10, color: '#484F58', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: valueColor || '#F0F6FC' }}>{value}</div>
    </div>
  )
}
