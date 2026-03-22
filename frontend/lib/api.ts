/**
 * ElasticGuard API Client
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ─── Cluster ──────────────────────────────────────────────────────────────────

export async function connectCluster(params: {
  cluster_id?: string
  url: string
  username?: string
  password?: string
  api_key?: string
  verify_ssl?: boolean
}) {
  return apiFetch('/api/cluster/connect', {
    method: 'POST',
    body: JSON.stringify({ cluster_id: 'default', ...params }),
  })
}

export async function disconnectCluster(clusterId: string) {
  return apiFetch(`/api/cluster/${clusterId}/disconnect`, { method: 'DELETE' })
}

export async function getClusterHealth(clusterId: string) {
  return apiFetch(`/api/cluster/${clusterId}/health`)
}

export async function getClusterNodes(clusterId: string) {
  return apiFetch(`/api/cluster/${clusterId}/nodes`)
}

export async function getClusterIndices(clusterId: string) {
  return apiFetch(`/api/cluster/${clusterId}/indices`)
}

export async function getClusterShards(clusterId: string) {
  return apiFetch(`/api/cluster/${clusterId}/shards`)
}

export async function executeAPI(clusterId: string, params: {
  method: string
  path: string
  body?: any
  approval_id?: string
}) {
  return apiFetch(`/api/cluster/${clusterId}/execute`, {
    method: 'POST',
    body: JSON.stringify({ cluster_id: clusterId, ...params }),
  })
}

// ─── Diagnostics ──────────────────────────────────────────────────────────────

export async function runDiagnostics(clusterId: string, options?: {
  use_ai?: boolean
  provider?: string
  model?: string
}) {
  const params = new URLSearchParams({
    use_ai: String(options?.use_ai ?? true),
    ...(options?.provider ? { provider: options.provider } : {}),
    ...(options?.model ? { model: options.model } : {}),
  })
  return apiFetch(`/api/diagnostics/${clusterId}/run?${params}`, { method: 'POST' })
}

export async function getLatestDiagnosis(clusterId: string) {
  return apiFetch(`/api/diagnostics/${clusterId}/latest`)
}

export async function explainAllocation(clusterId: string, index?: string) {
  const params = index ? `?index=${index}&shard=0&primary=true` : ''
  return apiFetch(`/api/diagnostics/${clusterId}/allocation-explain${params}`)
}

// ─── Monitoring ───────────────────────────────────────────────────────────────

export async function getLiveMetrics(clusterId: string) {
  return apiFetch(`/api/monitoring/${clusterId}/metrics`)
}

// ─── AI Agents ────────────────────────────────────────────────────────────────

export async function chatWithAgent(params: {
  cluster_id: string
  message: string
  provider?: string
  model?: string
}) {
  return apiFetch('/api/agents/chat', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export async function configureAI(clusterId: string, params: {
  provider: string
  model?: string
  api_key?: string
  base_url?: string
}) {
  return apiFetch(`/api/agents/configure?cluster_id=${clusterId}`, {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export async function getAIProviders() {
  return apiFetch('/api/agents/providers')
}

// ─── Topology ─────────────────────────────────────────────────────────────────

export async function getTopology(clusterId: string) {
  return apiFetch(`/api/topology/${clusterId}`)
}

// ─── Simulator ────────────────────────────────────────────────────────────────

export async function simulateChange(clusterId: string, params: {
  simulation_type: string
  parameters: Record<string, any>
}) {
  return apiFetch('/api/simulator/simulate', {
    method: 'POST',
    body: JSON.stringify({ cluster_id: clusterId, ...params }),
  })
}

// ─── Cost ─────────────────────────────────────────────────────────────────────

export async function getCostAnalysis(clusterId: string) {
  return apiFetch(`/api/cost/${clusterId}/analysis`)
}

// ─── Approvals ────────────────────────────────────────────────────────────────

export async function getPendingApprovals() {
  return apiFetch('/api/approval/pending')
}

export async function resolveApproval(params: {
  approval_id: string
  token: string
  action: 'approve' | 'reject'
}) {
  return apiFetch('/api/approval/resolve', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export async function createApproval(params: {
  cluster_id: string
  issue_title: string
  issue_description: string
  action_description: string
  api_calls: any[]
  cli_commands?: string[]
  risk_level?: string
  severity?: string
}) {
  const qs = new URLSearchParams({
    cluster_id: params.cluster_id,
    issue_title: params.issue_title,
    issue_description: params.issue_description,
    action_description: params.action_description,
    risk_level: params.risk_level || 'medium',
    severity: params.severity || 'high',
  })
  return apiFetch(`/api/approval/create?${qs}`, {
    method: 'POST',
    body: JSON.stringify({
      api_calls: params.api_calls,
      cli_commands: params.cli_commands || [],
    }),
  })
}

// ─── Notifications ────────────────────────────────────────────────────────────

export async function configureNotifications(config: any) {
  return apiFetch('/api/notifications/configure', {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

export async function testNotification(channel: string) {
  return apiFetch(`/api/notifications/test?channel=${channel}`, { method: 'POST' })
}

// ─── Settings ─────────────────────────────────────────────────────────────────

export async function getSettings() {
  return apiFetch('/api/settings/')
}

export async function getAIConfig() {
  return apiFetch('/api/agents/config')
}
