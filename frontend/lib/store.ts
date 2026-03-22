import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface ClusterConnection {
  cluster_id: string
  url: string
  username?: string
  password?: string      // stored for auto-reconnect
  api_key?: string       // stored for auto-reconnect
  verify_ssl?: boolean
  es_version?: string
  connected: boolean
  connected_at?: string
  health_status?: 'green' | 'yellow' | 'red' | 'error' | 'unknown'
  node_count?: number
  cluster_name?: string
}

export interface AIConfig {
  provider: string
  model?: string
  api_key?: string
  base_url?: string
}

interface AppState {
  // Multi-cluster
  clusters: ClusterConnection[]
  activeClusterId: string | null
  addCluster: (conn: ClusterConnection) => void
  removeCluster: (cluster_id: string) => void
  setActiveCluster: (cluster_id: string) => void
  updateClusterStatus: (cluster_id: string, update: Partial<ClusterConnection>) => void

  // Legacy single-connection shim (derived)
  connection: ClusterConnection | null
  setConnection: (conn: ClusterConnection | null) => void

  // AI Config
  aiConfig: AIConfig
  setAIConfig: (config: AIConfig) => void

  // Diagnosis — keyed by cluster_id
  diagnosisResults: Record<string, any>
  setDiagnosisResult: (cluster_id: string, result: any) => void
  diagnosisRunning: boolean
  setDiagnosisRunning: (running: boolean) => void

  // Current view
  activeView: string
  setActiveView: (view: string) => void

  // Real-time metrics — keyed by cluster_id
  liveMetricsMap: Record<string, any>
  setLiveMetrics: (cluster_id: string, metrics: any) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      clusters: [],
      activeClusterId: null,

      addCluster: (conn) => set((state) => {
        const exists = state.clusters.find(c => c.cluster_id === conn.cluster_id)
        const updated = exists
          ? state.clusters.map(c => c.cluster_id === conn.cluster_id ? { ...c, ...conn } : c)
          : [...state.clusters, conn]
        return { clusters: updated, activeClusterId: conn.cluster_id }
      }),

      removeCluster: (cluster_id) => set((state) => {
        const remaining = state.clusters.filter(c => c.cluster_id !== cluster_id)
        const newActive = state.activeClusterId === cluster_id
          ? (remaining[0]?.cluster_id ?? null)
          : state.activeClusterId
        return { clusters: remaining, activeClusterId: newActive }
      }),

      setActiveCluster: (cluster_id) => set({ activeClusterId: cluster_id }),

      updateClusterStatus: (cluster_id, update) => set((state) => ({
        clusters: state.clusters.map(c =>
          c.cluster_id === cluster_id ? { ...c, ...update } : c
        ),
      })),

      // Legacy shim
      get connection() {
        const s = get()
        return s.clusters.find(c => c.cluster_id === s.activeClusterId) ?? null
      },
      setConnection: (conn) => {
        if (!conn) {
          const s = get()
          if (s.activeClusterId) get().removeCluster(s.activeClusterId)
        } else {
          get().addCluster(conn)
        }
      },

      aiConfig: { provider: 'openai' },
      setAIConfig: (config) => set({ aiConfig: config }),

      diagnosisResults: {},
      setDiagnosisResult: (cluster_id, result) => set((state) => ({
        diagnosisResults: result === null
          ? Object.fromEntries(Object.entries(state.diagnosisResults).filter(([k]) => k !== cluster_id))
          : { ...state.diagnosisResults, [cluster_id]: result },
      })),
      diagnosisRunning: false,
      setDiagnosisRunning: (running) => set({ diagnosisRunning: running }),

      activeView: 'dashboard',
      setActiveView: (view) => set({ activeView: view }),

      liveMetricsMap: {},
      setLiveMetrics: (cluster_id, metrics) => set((state) => ({
        liveMetricsMap: { ...state.liveMetricsMap, [cluster_id]: metrics },
      })),
    }),
    {
      name: 'elasticguard-store',
      partialize: (state) => ({
        clusters: state.clusters,
        activeClusterId: state.activeClusterId,
        aiConfig: state.aiConfig,
        activeView: state.activeView,
      }),
    }
  )
)
