'use client'
import { useState } from 'react'
import { useAppStore } from '@/lib/store'
import { connectCluster } from '@/lib/api'
import toast from 'react-hot-toast'
import { Zap, Eye, EyeOff, AlertCircle, ArrowRight } from 'lucide-react'

export default function ConnectScreen() {
  const { setConnection } = useAppStore()
  const [url,       setUrl]       = useState('http://localhost:9200')
  const [authType,  setAuthType]  = useState<'none'|'basic'|'apikey'>('none')
  const [username,  setUsername]  = useState('')
  const [password,  setPassword]  = useState('')
  const [apiKey,    setApiKey]    = useState('')
  const [showPw,    setShowPw]    = useState(false)
  const [verifySsl, setVerifySsl] = useState(false)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')

  const handleConnect = async () => {
    if (!url.trim()) { setError('Cluster URL is required'); return }
    setLoading(true); setError('')
    try {
      const res = await connectCluster({
        url: url.trim(),
        username:   authType === 'basic'  ? username  : undefined,
        password:   authType === 'basic'  ? password  : undefined,
        api_key:    authType === 'apikey' ? apiKey    : undefined,
        verify_ssl: verifySsl,
      })
      setConnection({ cluster_id: 'default', url: url.trim(), username, es_version: res.es_version, connected: true, connected_at: new Date().toISOString() })
      toast.success(`Connected · ES ${res.es_version}`)
    } catch (e: any) {
      setError(e.message || 'Connection failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: 'var(--bg-app)' }}>
      <div style={{ width: '100%', maxWidth: 480 }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 48, height: 48, borderRadius: 12, background: 'var(--accent-soft)', border: '1px solid rgba(59,130,246,0.3)', marginBottom: 14 }}>
            <Zap size={22} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.5px' }}>
            ElasticGuard
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            AI-powered Elasticsearch diagnostics · ES 7, 8, 9
          </p>
        </div>

        {/* Card */}
        <div className="eg-card" style={{ padding: 28 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20 }}>
            Connect to cluster
          </h2>

          {/* URL */}
          <div style={{ marginBottom: 16 }}>
            <label className="eg-label">Cluster URL</label>
            <input className="eg-input eg-mono"
              value={url} onChange={e => setUrl(e.target.value)}
              placeholder="http://localhost:9200"
              onKeyDown={e => e.key === 'Enter' && handleConnect()} />
          </div>

          {/* Auth type */}
          <div style={{ marginBottom: 16 }}>
            <label className="eg-label">Authentication</label>
            <div className="eg-tabs" style={{ width: '100%' }}>
              {(['none','basic','apikey'] as const).map(t => (
                <button key={t} className={`eg-tab${authType === t ? ' active' : ''}`}
                  style={{ flex: 1 }} onClick={() => setAuthType(t)}>
                  {t === 'none' ? 'None' : t === 'basic' ? 'Basic Auth' : 'API Key'}
                </button>
              ))}
            </div>
          </div>

          {authType === 'basic' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
              <div>
                <label className="eg-label">Username</label>
                <input className="eg-input" value={username} onChange={e => setUsername(e.target.value)} placeholder="elastic" />
              </div>
              <div>
                <label className="eg-label">Password</label>
                <div style={{ position: 'relative' }}>
                  <input className="eg-input" type={showPw ? 'text' : 'password'} value={password}
                    onChange={e => setPassword(e.target.value)} placeholder="••••••••"
                    style={{ paddingRight: 38 }} />
                  <button onClick={() => setShowPw(p => !p)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {authType === 'apikey' && (
            <div style={{ marginBottom: 16 }}>
              <label className="eg-label">API Key</label>
              <input className="eg-input eg-mono" type="password" value={apiKey}
                onChange={e => setApiKey(e.target.value)} placeholder="base64-encoded-api-key" />
            </div>
          )}

          {/* SSL toggle */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
            <div onClick={() => setVerifySsl(p => !p)}
              style={{ width: 36, height: 20, borderRadius: 99, background: verifySsl ? 'var(--accent)' : 'var(--bg-raised)', border: '1px solid var(--border-mid)', position: 'relative', cursor: 'pointer', transition: 'background .2s', flexShrink: 0 }}>
              <div style={{ position: 'absolute', top: 2, left: verifySsl ? 17 : 2, width: 14, height: 14, borderRadius: 99, background: '#fff', transition: 'left .2s', boxShadow: '0 1px 3px rgba(0,0,0,.4)' }} />
            </div>
            Verify SSL certificate
          </label>

          {error && (
            <div className="eg-banner eg-banner-err" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 16 }}>
              <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              {error}
            </div>
          )}

          <button className="eg-btn eg-btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '10px 16px', fontSize: 14 }}
            onClick={handleConnect} disabled={loading}>
            {loading
              ? <><div className="eg-spinner" style={{ width: 14, height: 14 }} /> Connecting…</>
              : <><span>Connect &amp; Run Diagnostics</span><ArrowRight size={14} /></>
            }
          </button>
        </div>

        {/* Feature pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 20 }}>
          {['Real-time monitoring','LangGraph AI agents','Discord/Slack alerts','Cost optimizer','Cluster simulator'].map(f => (
            <span key={f} style={{ fontSize: 11, padding: '3px 10px', borderRadius: 99, background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
              {f}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
