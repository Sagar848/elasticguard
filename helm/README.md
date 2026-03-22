# ElasticGuard Helm Chart

Deploy the full ElasticGuard AI-powered Elasticsearch diagnostics platform to Kubernetes in minutes.

## What's included

| Component  | Description                                      | Default |
|------------|--------------------------------------------------|---------|
| Backend    | FastAPI + LangGraph AI agents                    | Enabled |
| Frontend   | Next.js 14 UI                                    | Enabled |
| Ollama     | Local Llama LLM (no API key needed)              | Enabled |
| Prometheus | Metrics scraping from backend                    | Enabled |
| Grafana    | Pre-built cluster monitoring dashboards          | Enabled |

## Prerequisites

- Kubernetes 1.24+
- Helm 3.10+
- `kubectl` configured for your cluster
- Persistent Volume provisioner (for PVCs)
- (Optional) Ingress controller (nginx, ALB, Traefik)
- (Optional) cert-manager (for TLS)

---

## Quick Start

### 1. Add the chart (or use local)

```bash
# From local directory (after cloning the repo)
cd elasticsearch-ai-diagnostics

# Or install from OCI registry (after a release is published)
# helm pull oci://ghcr.io/your-org/helm-charts/elasticguard --version 1.0.0
```

### 2. Install with defaults (Ollama local LLM)

```bash
helm install elasticguard ./helm/elasticguard \
  --namespace monitoring \
  --create-namespace \
  --set app.secretKey=$(openssl rand -hex 32) \
  --set app.approvalWebhookSecret=$(openssl rand -hex 16)
```

### 3. Access the UI

```bash
kubectl port-forward -n monitoring \
  svc/elasticguard-frontend 3000:3000

# Open http://localhost:3000
```

---

## Configuration

All values are in `helm/elasticguard/values.yaml`. Override with `-f` or `--set`.

### AI Provider

```bash
# Use OpenAI (recommended for best results)
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ai.defaultProvider=openai \
  --set ai.openai.apiKey=sk-your-key-here

# Use Ollama (local, free — default)
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ai.defaultProvider=ollama

# Use Anthropic Claude
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ai.defaultProvider=anthropic \
  --set ai.anthropic.apiKey=sk-ant-your-key

# Use Google Gemini
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ai.defaultProvider=gemini \
  --set ai.gemini.apiKey=AIza-your-key
```

### Notifications

```bash
# Discord
helm upgrade --install elasticguard ./helm/elasticguard \
  --set notifications.discord.webhookUrl=https://discord.com/api/webhooks/...

# Slack
helm upgrade --install elasticguard ./helm/elasticguard \
  --set notifications.slack.webhookUrl=https://hooks.slack.com/services/...

# Email
helm upgrade --install elasticguard ./helm/elasticguard \
  --set notifications.smtp.host=smtp.gmail.com \
  --set notifications.smtp.user=you@gmail.com \
  --set notifications.smtp.password=app-password \
  --set notifications.smtp.notificationEmails=oncall@company.com
```

### Ingress

```bash
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set "ingress.hosts[0].host=elasticguard.example.com" \
  --set "ingress.hosts[0].paths[0].path=/" \
  --set "ingress.hosts[0].paths[0].pathType=Prefix" \
  --set "ingress.hosts[0].paths[0].service=frontend"
```

### Existing Secrets (recommended for production)

Instead of passing secrets as `--set` flags (which appear in shell history):

```bash
# Create the secret manually
kubectl create secret generic elasticguard-ai-keys \
  --from-literal=OPENAI_API_KEY=sk-... \
  --from-literal=DEFAULT_AI_PROVIDER=openai \
  -n monitoring

# Reference it in the chart
helm upgrade --install elasticguard ./helm/elasticguard \
  --set ai.existingSecret=elasticguard-ai-keys
```

---

## Deployment Scenarios

### Minimal (dev / local cluster)

```bash
helm install elasticguard ./helm/elasticguard \
  -n elasticguard --create-namespace \
  -f helm/values-minimal.yaml
```

### Production

```bash
helm install elasticguard ./helm/elasticguard \
  -n monitoring --create-namespace \
  -f helm/values-production.yaml \
  --set app.secretKey=$(openssl rand -hex 32) \
  --set app.approvalWebhookSecret=$(openssl rand -hex 16)
```

### AWS EKS

```bash
helm install elasticguard ./helm/elasticguard \
  -n monitoring --create-namespace \
  -f helm/values-cloud-aws.yaml \
  --set app.secretKey=$(openssl rand -hex 32)
```

### GKE

```bash
helm install elasticguard ./helm/elasticguard \
  -n monitoring --create-namespace \
  -f helm/values-cloud-gke.yaml \
  --set app.secretKey=$(openssl rand -hex 32)
```

### Disable Ollama (use cloud AI only)

```bash
helm install elasticguard ./helm/elasticguard \
  --set ollama.enabled=false \
  --set ai.defaultProvider=openai \
  --set ai.openai.apiKey=sk-...
```

### GPU-accelerated Ollama

```bash
helm install elasticguard ./helm/elasticguard \
  --set ollama.gpu.enabled=true \
  --set ollama.gpu.count=1 \
  --set "ollama.tolerations[0].key=nvidia.com/gpu" \
  --set "ollama.tolerations[0].operator=Exists" \
  --set "ollama.tolerations[0].effect=NoSchedule" \
  --set "ollama.nodeSelector.accelerator=nvidia-tesla-t4"
```

---

## Values Reference

### Global

| Key | Default | Description |
|-----|---------|-------------|
| `global.storageClass` | `""` | Storage class for all PVCs (cluster default if empty) |
| `global.imagePullSecrets` | `[]` | Image pull secrets for private registries |

### Backend

| Key | Default | Description |
|-----|---------|-------------|
| `backend.replicaCount` | `1` | Number of backend pods |
| `backend.image.repository` | `your-registry/elasticguard-backend` | Image repository |
| `backend.image.tag` | `1.0.0` | Image tag |
| `backend.resources.requests.cpu` | `250m` | CPU request |
| `backend.resources.requests.memory` | `512Mi` | Memory request |
| `backend.persistence.enabled` | `true` | Enable ChromaDB PVC |
| `backend.persistence.size` | `2Gi` | PVC size |
| `backend.autoscaling.enabled` | `false` | Enable HPA |

### AI

| Key | Default | Description |
|-----|---------|-------------|
| `ai.defaultProvider` | `ollama` | Default AI provider |
| `ai.openai.apiKey` | `""` | OpenAI API key |
| `ai.gemini.apiKey` | `""` | Google Gemini API key |
| `ai.anthropic.apiKey` | `""` | Anthropic API key |
| `ai.existingSecret` | `""` | Use pre-existing Secret for AI keys |

### Ollama

| Key | Default | Description |
|-----|---------|-------------|
| `ollama.enabled` | `true` | Deploy Ollama |
| `ollama.models` | `[llama3.2, nomic-embed-text]` | Models to pull |
| `ollama.persistence.size` | `20Gi` | Model storage PVC size |
| `ollama.gpu.enabled` | `false` | Enable GPU resources |

### Ingress

| Key | Default | Description |
|-----|---------|-------------|
| `ingress.enabled` | `false` | Enable Ingress |
| `ingress.className` | `nginx` | Ingress class |
| `ingress.hosts` | `[]` | Frontend host rules |
| `ingress.apiHosts` | `[]` | Backend API host rules |
| `ingress.tls` | `[]` | TLS configuration |

---

## Upgrade

```bash
# Upgrade to new version
helm upgrade elasticguard ./helm/elasticguard \
  -n monitoring \
  -f helm/values-production.yaml \
  --set app.secretKey=$SECRET_KEY \
  --reuse-values
```

## Uninstall

```bash
helm uninstall elasticguard -n monitoring

# Delete PVCs (WARNING: deletes all data)
kubectl delete pvc -n monitoring -l app.kubernetes.io/instance=elasticguard
```

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl get pods -n monitoring -l app.kubernetes.io/instance=elasticguard

# Describe failing pod
kubectl describe pod -n monitoring <pod-name>

# Check logs
kubectl logs -n monitoring -l app.kubernetes.io/component=backend
```

### Ollama model pull failing

```bash
# Check init job logs
kubectl logs -n monitoring -l app.kubernetes.io/component=ollama-init -f

# Re-trigger the job
kubectl delete job -n monitoring elasticguard-ollama-model-pull
helm upgrade elasticguard ./helm/elasticguard -n monitoring --reuse-values
```

### Backend can't connect to Elasticsearch

The backend connects to Elasticsearch clusters from inside the cluster.
- For in-cluster ES: use the Service DNS, e.g. `http://elasticsearch-master:9200`
- For external ES: ensure the cluster has outbound internet access (or use NetworkPolicy exceptions)
- For ES with self-signed certs: disable SSL verification in the UI connect form

### WebSocket not working behind ingress

Add these annotations to your Ingress:
```yaml
nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
nginx.ingress.kubernetes.io/proxy-http-version: "1.1"
nginx.ingress.kubernetes.io/configuration-snippet: |
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
```

---

## Architecture in Kubernetes

```
Namespace: monitoring
├── Deployment: elasticguard-frontend     (Next.js UI)
│     └── Service: ClusterIP :3000
├── Deployment: elasticguard-backend      (FastAPI)
│     └── Service: ClusterIP :8000
│     └── PVC: chroma-data (ChromaDB)
├── StatefulSet: elasticguard-ollama      (Llama LLM)
│     └── Service: Headless :11434
│     └── PVC: ollama-data (models)
│     └── Job: model-pull (post-install hook)
├── Deployment: elasticguard-prometheus   (Metrics)
│     └── Service: ClusterIP :9090
│     └── PVC: prometheus-data
├── Deployment: elasticguard-grafana      (Dashboards)
│     └── Service: ClusterIP :3000
│     └── PVC: grafana-data
├── Secret: elasticguard-secrets          (AI keys, SMTP)
├── ConfigMap: elasticguard-config        (Non-sensitive config)
├── ServiceAccount: elasticguard
└── Ingress: elasticguard-frontend        (Optional)
           elasticguard-backend          (Optional)
```
