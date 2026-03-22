'use client'
import { useState, useEffect } from 'react'
import { useAppStore } from '@/lib/store'
import { connectCluster, disconnectCluster } from '@/lib/api'
import toast from 'react-hot-toast'
import { Plus, Trash2, CheckCircle, AlertCircle, RefreshCw, Eye, EyeOff, Database } from 'lucide-react'

interface AddFormState {
  url: string
  username: string
  password: string
  api_key: string
  authType: 'none' | 'basic' | 'apikey'
  verify_ssl: boolean
  cluster_id: string
}

const EMPTY_FORM: AddFormState = {
  url: 'http://localhost:9200',
  username: '',
  password: '',
  api_key: '',
  authType: 'none',
  verify_ssl: false,
  cluster_id: '',
}

export default function ClusterManager() {
  const { clusters, activeClusterId, addCluster, removeCluster, setActiveCluster } = useAppStore()
  const [showAdd, setShowAdd] = useState(clusters.length === 0)
  const [form, setForm]       = useState<AddFormState>(EMPTY_FORM)
  const [showPw, setShowPw]   = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  // Auto-open add form when no clusters connected
  useEffect(() => { if (clusters.length === 0) setShowAdd(true) }, [clusters.length])

  const handleConnect = async () => {
    if (!form.url.trim()) { setError('Cluster URL is required'); return }
    setLoading(true); setError('')
    try {
      // Generate a stable cluster_id from the URL if not given
      const clusterId = form.cluster_id.trim() ||
        form.url.replace(/https?:\/\//, '').replace(/[^a-zA-Z0-9-]/g, '-').replace(/-+/g, '-').slice(0, 40)

      const res = await connectCluster({
        cluster_id: clusterId,
        url: form.url.trim(),
        username:   form.authType === 'basic'  ? form.username  : undefined,
        password:   form.authType === 'basic'  ? form.password  : undefined,
        api_key:    form.authType === 'apikey' ? form.api_key   : undefined,
        verify_ssl: form.verify_ssl,
      })

      addCluster({
        cluster_id:   clusterId,
        url:          form.url.trim(),
        username:     form.authType === 'basic'  ? form.username  : undefined,
        password:     form.authType === 'basic'  ? form.password  : undefined,
        api_key:      form.authType === 'apikey' ? form.api_key   : undefined,
        verify_ssl:   form.verify_ssl,
        es_version:   res.es_version,
        connected:    true,
        connected_at: new Date().toISOString(),
        cluster_name: res.cluster_name,
      })

      toast.success(`Connected · ${res.message}`)
      setForm(EMPTY_FORM)
      setShowAdd(false)
    } catch (e: any) {
      setError(e.message || 'Connection failed')
    } finally {
      setLoading(false)
    }
  }

  const handleRemove = async (cluster_id: string) => {
    if (!confirm(`Disconnect cluster "${cluster_id}"?`)) return
    try {
      await disconnectCluster(cluster_id)
    } catch { /* silent — remove from UI regardless */ }
    removeCluster(cluster_id)
    toast.success('Cluster disconnected')
  }

  return (
    <div className="eg-page">
      {/* Header */}
      <div className="eg-page-header">
        <div>
          <h1 className="eg-page-title">Clusters</h1>
          <p className="eg-page-sub">{clusters.length} connected · click a cluster to switch to it</p>
        </div>
        <button className="eg-btn eg-btn-primary" onClick={() => setShowAdd(s => !s)}>
          <Plus size={13} />{showAdd ? 'Cancel' : 'Add Cluster'}
        </button>
      </div>

      {/* Add cluster form */}
      {showAdd && (
        <div className="eg-card" style={{ display: 'flex', flexDirection: 'column', gap: 16, borderColor: 'rgba(59,130,246,.3)' }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            {clusters.length === 0 ? 'Connect your first cluster' : 'Connect a new cluster'}
          </h2>

          {/* Cluster nickname */}
          <div>
            <label className="eg-label">Cluster Nickname (optional)</label>
            <input className="eg-input" value={form.cluster_id}
              onChange={e => setForm(f => ({ ...f, cluster_id: e.target.value }))}
              placeholder="e.g. production, staging (auto-generated if blank)" />
          </div>

          {/* URL */}
          <div>
            <label className="eg-label">Cluster URL</label>
            <input className="eg-input eg-mono" value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              placeholder="http://localhost:9200"
              onKeyDown={e => e.key === 'Enter' && handleConnect()} />
          </div>

          {/* Auth type */}
          <div>
            <label className="eg-label">Authentication</label>
            <div className="eg-tabs">
              {(['none', 'basic', 'apikey'] as const).map(t => (
                <button key={t} className={`eg-tab${form.authType === t ? ' active' : ''}`}
                  style={{ flex: 1 }} onClick={() => setForm(f => ({ ...f, authType: t }))}>
                  {t === 'none' ? 'None' : t === 'basic' ? 'Basic Auth' : 'API Key'}
                </button>
              ))}
            </div>
          </div>

          {form.authType === 'basic' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label className="eg-label">Username</label>
                <input className="eg-input" value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                  placeholder="elastic" />
              </div>
              <div>
                <label className="eg-label">Password</label>
                <div style={{ position: 'relative' }}>
                  <input className="eg-input" type={showPw ? 'text' : 'password'} value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    style={{ paddingRight: 38 }} placeholder="••••••••" />
                  <button onClick={() => setShowPw(p => !p)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                    {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {form.authType === 'apikey' && (
            <div>
              <label className="eg-label">API Key</label>
              <input className="eg-input eg-mono" type="password" value={form.api_key}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                placeholder="base64-encoded-api-key" />
            </div>
          )}

          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)' }}>
            <div onClick={() => setForm(f => ({ ...f, verify_ssl: !f.verify_ssl }))}
              style={{ width: 36, height: 20, borderRadius: 99, background: form.verify_ssl ? 'var(--accent)' : 'var(--bg-raised)', border: '1px solid var(--border-mid)', position: 'relative', cursor: 'pointer', transition: 'background .2s', flexShrink: 0 }}>
              <div style={{ position: 'absolute', top: 2, left: form.verify_ssl ? 17 : 2, width: 14, height: 14, borderRadius: 99, background: '#fff', transition: 'left .2s' }} />
            </div>
            Verify SSL
          </label>

          {error && (
            <div className="eg-banner eg-banner-err" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              {error}
            </div>
          )}

          <button className="eg-btn eg-btn-primary" onClick={handleConnect} disabled={loading}
            style={{ alignSelf: 'flex-start' }}>
            {loading
              ? <><div className="eg-spinner" style={{ width: 13, height: 13 }} />Connecting…</>
              : <><Plus size={13} />Connect</>
            }
          </button>
        </div>
      )}

      {/* Connected clusters list */}
      {clusters.length === 0 && !showAdd && (
        <div className="eg-empty">
          <Database size={36} style={{ color: 'var(--text-muted)', opacity: .5 }} />
          <p>No clusters connected</p>
          <button className="eg-btn eg-btn-primary" onClick={() => setShowAdd(true)}>
            <Plus size={13} />Add Cluster
          </button>
        </div>
      )}

      {clusters.length > 0 && (
        <div className="eg-stack">
          {clusters.map(cluster => {
            const isActive = cluster.cluster_id === activeClusterId
            const hc = cluster.health_status || 'unknown'
            const hColor = hc === 'green' ? 'var(--green)' : hc === 'yellow' ? 'var(--yellow)' : hc === 'red' ? 'var(--red)' : 'var(--text-muted)'

            return (
              <div key={cluster.cluster_id}
                className="eg-card"
                style={{
                  padding: '14px 16px',
                  border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
                  background: isActive ? 'var(--accent-soft)' : 'var(--bg-surface)',
                  cursor: 'pointer',
                  transition: 'all .15s',
                }}
                onClick={() => setActiveCluster(cluster.cluster_id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  {/* Health dot */}
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: hColor, boxShadow: `0 0 6px ${hColor}`, flexShrink: 0 }} />

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: isActive ? 'var(--accent)' : 'var(--text-primary)' }}>
                        {cluster.cluster_name || cluster.cluster_id}
                      </span>
                      {isActive && <span className="eg-badge eg-badge-blue" style={{ fontSize: 10 }}>Active</span>}
                      {cluster.es_version && (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>ES {cluster.es_version}</span>
                      )}
                    </div>
                    <div className="eg-mono" style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cluster.url}
                    </div>
                    <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
                      {cluster.node_count !== undefined && <span>{cluster.node_count} nodes</span>}
                      <span style={{ color: hColor, textTransform: 'uppercase', fontWeight: 600 }}>{hc}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                    {!isActive && (
                      <button className="eg-btn eg-btn-ghost" style={{ fontSize: 11, padding: '4px 10px' }}
                        onClick={() => setActiveCluster(cluster.cluster_id)}>
                        Switch
                      </button>
                    )}
                    <button className="eg-btn eg-btn-danger" style={{ fontSize: 11, padding: '4px 10px' }}
                      onClick={() => handleRemove(cluster.cluster_id)}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
