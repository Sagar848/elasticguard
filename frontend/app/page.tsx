'use client'
import { useEffect, useState, useCallback } from 'react'
import { useAppStore } from '@/lib/store'
import Dashboard from '@/components/Dashboard'
import ClusterManager from '@/components/ClusterManager'
import { connectCluster } from '@/lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function Home() {
  const { clusters, activeClusterId, addCluster, updateClusterStatus, setAIConfig } = useAppStore()
  const [mounted,       setMounted]       = useState(false)
  const [reconnecting,  setReconnecting]  = useState(false)
  const [reconnectDone, setReconnectDone] = useState(false)

  useEffect(() => { setMounted(true) }, [])

  const reconnectAll = useCallback(async () => {
    if (reconnectDone) return
    setReconnecting(true)

    // ── Step 1: Merge backend-persisted clusters into frontend store ──────────
    try {
      const persisted: any[] = await fetch(`${API}/api/cluster/persisted`)
        .then(r => r.ok ? r.json() : [])
        .catch(() => [])

      for (const c of persisted) {
        addCluster({
          cluster_id:   c.cluster_id,
          url:          c.url,
          username:     c.username  ?? undefined,
          password:     c.password  ?? undefined,
          api_key:      c.api_key   ?? undefined,
          verify_ssl:   Boolean(c.verify_ssl),
          es_version:   c.es_version   ?? undefined,
          cluster_name: c.cluster_name ?? undefined,
          connected:    false,
        })
      }
    } catch { /* ignore */ }

    // ── Step 2: Re-register all clusters with the backend ─────────────────────
    const toConnect = useAppStore.getState().clusters
    await Promise.allSettled(
      toConnect.map(async (cluster) => {
        try {
          const res = await connectCluster({
            cluster_id: cluster.cluster_id,
            url:        cluster.url,
            username:   cluster.username,
            password:   cluster.password,
            api_key:    cluster.api_key,
            verify_ssl: cluster.verify_ssl ?? false,
          })
          updateClusterStatus(cluster.cluster_id, {
            connected:    true,
            es_version:   res.es_version,
            cluster_name: res.cluster_name ?? cluster.cluster_name,
          })
        } catch {
          updateClusterStatus(cluster.cluster_id, { connected: false, health_status: 'error' })
        }
      })
    )

    // ── Step 3: Restore AI config ─────────────────────────────────────────────
    // Priority: backend DB (most authoritative) > frontend localStorage store
    try {
      const backendAI = await fetch(`${API}/api/agents/config`)
        .then(r => r.ok ? r.json() : null)
        .catch(() => null)

      if (backendAI?.provider) {
        // Backend has a saved config — use it and sync to frontend store
        setAIConfig({
          provider: backendAI.provider,
          model:    backendAI.model    ?? undefined,
          api_key:  backendAI.api_key  ?? undefined,
          base_url: backendAI.base_url ?? undefined,
        })
      } else {
        // Backend has no saved config — push the frontend store's value to backend
        const { aiConfig } = useAppStore.getState()
        if (aiConfig.provider) {
          const activeId = useAppStore.getState().activeClusterId || 'default'
          await fetch(`${API}/api/agents/configure?cluster_id=${activeId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              provider: aiConfig.provider,
              model:    aiConfig.model,
              api_key:  aiConfig.api_key,
              base_url: aiConfig.base_url,
            }),
          }).catch(() => {})
        }
      }
    } catch { /* non-fatal */ }

    setReconnecting(false)
    setReconnectDone(true)
  }, [reconnectDone, addCluster, updateClusterStatus, setAIConfig])

  useEffect(() => {
    if (mounted && !reconnectDone) reconnectAll()
  }, [mounted, reconnectDone, reconnectAll])

  if (!mounted) return null

  if (reconnecting) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-app)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 14 }}>
        <div style={{ width: 22, height: 22, border: '2px solid var(--border-mid)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />
        <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Connecting…</p>
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    )
  }

  const { clusters: cls, activeClusterId: aid } = useAppStore.getState()
  if (cls.length === 0 || !aid) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-app)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <div style={{ width: '100%', maxWidth: 560 }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '.1em', textTransform: 'uppercase', marginBottom: 8 }}>ElasticGuard</div>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.5px' }}>AI Elasticsearch Diagnostics</h1>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 6 }}>Connect to any ES 7, 8, or 9 cluster to get started</p>
          </div>
          <ClusterManager />
        </div>
      </div>
    )
  }

  return <Dashboard />
}
