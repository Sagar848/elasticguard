# ElasticGuard — Complete Setup Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Quick Start — Docker (Recommended)](#quick-start--docker)
3. [Local Development Setup](#local-development)
4. [AI Provider Configuration](#ai-providers)
5. [Notification Setup](#notifications)
6. [Grafana Dashboards](#grafana)
7. [Connecting to Elasticsearch](#connecting)
8. [Understanding the UI](#understanding-the-ui)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Docker setup (recommended)
- Docker Desktop 4.x+ — https://docker.com/products/docker-desktop
- 4 GB RAM minimum (8 GB recommended if using Ollama local LLM)
- 10 GB disk space (Ollama models are ~2 GB each)

### Local setup
- Python 3.11+
- Node.js 20+
- (Optional) Ollama — https://ollama.ai

---

## Quick Start — Docker

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/elasticsearch-ai-diagnostics
cd elasticsearch-ai-diagnostics

# 2. Configure environment
cp .env.example .env
# Edit .env — at minimum set DEFAULT_AI_PROVIDER
# For zero-config: leave DEFAULT_AI_PROVIDER=ollama (local LLM, no API key needed)

# 3. Start everything
docker-compose up -d

# 4. Watch startup logs
docker-compose logs -f backend

# 5. Open the app
open http://localhost:3000
```

### Services started by docker-compose

| Service    | URL                         | Purpose                        |
|------------|-----------------------------|--------------------------------|
| Frontend   | http://localhost:3000       | Next.js UI                     |
| Backend    | http://localhost:8000       | FastAPI + AI agents            |
| API Docs   | http://localhost:8000/docs  | Swagger/OpenAPI                |
| Ollama     | http://localhost:11434      | Local LLM inference            |
| Prometheus | http://localhost:9090       | Metrics database               |
| Grafana    | http://localhost:3001       | Dashboards (admin/elasticguard)|

> **First run note:** Ollama will download `llama3.2` (~2 GB) and `nomic-embed-text` (~270 MB).
> This happens in the background — the app works immediately, AI features activate once models are ready.
> Check progress: `docker-compose logs -f ollama-init`

---

## Local Development

### Windows (PowerShell or Git Bash)

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate          # PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\\.env .env
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

### macOS / Linux

```bash
./start.sh local
```

### Ollama for local AI (free, no API key)

```bash
# Install
curl -fsSL https://ollama.ai/install.sh | sh    # Linux/Mac
# Windows: download from https://ollama.ai

# Pull models
ollama pull llama3.2           # Main AI model (~2GB)
ollama pull nomic-embed-text   # Embeddings for RAG (~270MB)

# Start (if not already running as service)
ollama serve
```

---

## AI Providers

Set in **Settings → AI Provider** in the UI, or in `.env`:

### OpenAI (GPT-4o)
```env
DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4o
```

### Google Gemini
```env
DEFAULT_AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...
GEMINI_DEFAULT_MODEL=gemini-2.0-flash-lite
```

### Anthropic Claude
```env
DEFAULT_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_DEFAULT_MODEL=claude-3-5-sonnet-20241022
```

### Ollama (Local — Free)
```env
DEFAULT_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2    # or mistral, phi3, codellama
```

### Custom OpenAI-Compatible (LM Studio, vLLM, Together AI, etc.)
```env
DEFAULT_AI_PROVIDER=custom
CUSTOM_AI_BASE_URL=http://localhost:1234/v1
CUSTOM_AI_KEY=not-needed
CUSTOM_AI_MODEL=my-model-name
```

---

## Notifications

Notifications are sent when ElasticGuard detects issues **and** when it proposes a fix that needs your approval.

### Discord (Easiest)

1. Open Discord → Server Settings → Integrations → Webhooks
2. Click **New Webhook** → Copy URL
3. Add to `.env`:
   ```env
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
4. Test: Settings → Notifications → Send Test

### Slack

1. Go to https://api.slack.com/apps → Create New App → From Scratch
2. Enable **Incoming Webhooks** → Add New Webhook to Workspace
3. Add to `.env`:
   ```env
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
   ```

### Email (Gmail)

1. Enable 2FA on Gmail
2. Go to myaccount.google.com/apppasswords → Create app password
3. Add to `.env`:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASS=xxxx-xxxx-xxxx-xxxx   # 16 char app password
   NOTIFICATION_EMAILS=you@company.com
   ```

### Approval Flow

When ElasticGuard proposes a fix:
1. Notification sent to all configured channels with **Approve** and **Reject** links
2. Links open `http://localhost:3000/approve/[id]` — works from any device on your network
3. Click **Approve & Execute** → ElasticGuard runs the Elasticsearch API call
4. Click **Reject** → Nothing is changed on the cluster
5. Approvals expire after 60 minutes (configurable via `APPROVAL_TIMEOUT_MINUTES`)

> **External access:** If approving from outside your network, set up a reverse proxy (nginx/Caddy) or use a tunnel (ngrok) pointing to port 3000.

---

## Grafana

Grafana is automatically provisioned with the ElasticGuard dashboard.

1. Open http://localhost:3001
2. Login: `admin` / `elasticguard`
3. Dashboard: **ElasticGuard — Elasticsearch Monitoring** (auto-loaded)

The dashboard shows:
- Cluster health status (green/yellow/red)
- CPU, JVM heap, disk usage per node (time series + gauges)
- GC old-gen collection rate
- Unassigned shard count
- Active shard count

**Custom alerts in Grafana:**
1. Open a panel → Edit → Alert tab
2. Set condition (e.g. JVM heap > 85% for 5 minutes)
3. Configure notification channel (Slack, email, PagerDuty, etc.)

**Prometheus metrics exposed at:**
```
http://localhost:8000/metrics/prometheus/metrics
```

---

## Connecting to Elasticsearch

### Local ES (no auth)
```
URL: http://localhost:9200
Auth: None
```

### ES with Basic Auth
```
URL: https://my-cluster:9200
Username: elastic
Password: your-password
```

### ES Cloud (Elastic Cloud)
```
URL: https://your-deployment.es.us-east-1.aws.elastic-cloud.com
Username: elastic
Password: your-cloud-password
```
or use API Key:
```
URL: https://your-deployment.es.us-east-1.aws.elastic-cloud.com
API Key: your-base64-encoded-api-key
```

### Docker ES (same docker-compose network)
```
URL: http://elasticsearch:9200
```

### ES Version Compatibility
ElasticGuard uses raw HTTP (not the ES SDK) so it works with **ES 7.x, 8.x, and 9.x** automatically. Version-specific differences are handled by the AI agents when generating solutions.

---

## Understanding the UI

### Overview
Shows cluster health banner, issue count KPIs, AI analysis summary, top 5 issues, and per-node health bars.

### Issues
Full list of all detected issues, sorted by severity. Expand any issue to see:
- Exact metrics that triggered the alert
- Step-by-step solution from the AI
- Elasticsearch API calls to run (with Approve/Execute buttons)
- CLI commands to run on the server

### Topology
Interactive cluster graph showing nodes, shard distribution, and health. Click any node for detailed metrics.

### Metrics
Real-time charts for CPU, JVM heap, disk usage (updates via WebSocket, falls back to polling). Auto-refreshes every 15 seconds.

### Query Analyser
- **Slow Queries tab**: Per-index query performance statistics and cache hit rates
- **Query Profiler tab**: Paste any query JSON and get a detailed breakdown of where time is spent
- **Running Tasks tab**: See all active tasks with option to cancel long-running ones

### AI Chat
Interactive chat with the AI agent. It has full context of your cluster state. Ask anything:
- "Why is my cluster yellow?"
- "What's causing the JVM heap spike on node-1?"
- "How do I set up ILM for my logs-* indices?"
- "Show me the Elasticsearch API to add a replica to production-index"

### Approvals
All pending and historical approval requests. Approve or reject actions directly in the UI (same as clicking links in Discord/Slack/Email).

### Cost Optimizer
AI-generated recommendations to reduce disk usage, fix over/under-replicated indices, and clean up empty indices.

### Simulator
Model the impact of cluster changes **before** applying them:
- Add/remove nodes with predicted shard redistribution
- Change replica counts with disk impact calculation
- Rebalance shards with estimated recovery time

### Settings
- Switch AI provider and configure API keys
- Configure Discord/Slack/Email notification channels
- Send test notifications

---

## Troubleshooting

### "Module not found: @/lib/store"
Add `tsconfig.json` to `frontend/` with:
```json
{ "compilerOptions": { "paths": { "@/*": ["./*"] } } }
```

### Backend won't start — pip dependency errors
The warnings about `pydantic`, `spacy`, etc. are from **other packages** on your system, not ElasticGuard. The app works correctly. Run:
```bash
pip install -r requirements.txt --upgrade
```
If errors persist, use a fresh virtualenv:
```bash
python -m venv fresh-venv && fresh-venv/Scripts/activate && pip install -r requirements.txt
```

### Can't connect to Elasticsearch
- Verify the URL is reachable: `curl http://localhost:9200`
- For HTTPS with self-signed cert: disable SSL verification in the connect form
- For Docker ES: use `http://host.docker.internal:9200` when backend is in Docker

### AI features not working
1. Check Settings → AI Provider is configured
2. For Ollama: ensure `ollama serve` is running and models are pulled
3. Check backend logs: `docker-compose logs backend` or `uvicorn` terminal output
4. AI diagnosis falls back to raw diagnostics if LLM is unavailable — issues still show, just without AI summaries

### Approval links not working from outside localhost
The approval page is at `http://localhost:3000/approve/[id]`. To access from other devices:
- Use your machine's LAN IP: `http://192.168.x.x:3000/approve/[id]`
- Or set `NEXT_PUBLIC_APP_URL=http://your-ip:3000` in `.env.local`

### WebSocket shows "Polling" instead of "WS Live"
This is expected if the backend isn't reachable via WebSocket. The app falls back to HTTP polling every 30 seconds automatically. No data is lost.

### Grafana shows "No data"
1. Check Prometheus is scraping: http://localhost:9090/targets
2. Verify backend is healthy: http://localhost:8000/health
3. Connect a cluster in ElasticGuard first — metrics only appear once a cluster is connected

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Next.js 14)                  │
│  ConnectScreen → Dashboard → Issues/Topology/Metrics/…  │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP + WebSocket
┌──────────────────▼──────────────────────────────────────┐
│                FastAPI Backend (:8000)                    │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Diagnostics  │  │ LangGraph    │  │ Notifications │  │
│  │ Engine       │  │ AI Agents    │  │ Discord/Slack │  │
│  │              │  │ Triage →     │  │ Email         │  │
│  │ 30+ checks   │  │ Diagnose →   │  │               │  │
│  │              │  │ Solution →   │  │ Approval flow │  │
│  │              │  │ Safety check │  │               │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                               │
│  ┌──────▼─────────────────▼───────┐  ┌───────────────┐  │
│  │    Elasticsearch Client         │  │  ChromaDB RAG │  │
│  │    ES 7/8/9 compatible          │  │  Knowledge    │  │
│  │    Raw HTTP (no SDK)            │  │  Base         │  │
│  └────────────────────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                   │
        ┌──────────▼──────────┐
        │  Elasticsearch       │
        │  Cluster (external)  │
        │  v7.x / v8.x / v9.x │
        └─────────────────────┘

┌──────────────────┐    ┌──────────────────┐
│    Prometheus    │───▶│     Grafana       │
│    (:9090)       │    │    (:3001)        │
│  Scrapes /metrics│    │  Dashboards       │
└──────────────────┘    └──────────────────┘

┌──────────────────┐
│     Ollama       │
│    (:11434)      │
│  Local Llama3.2  │
│  (optional)      │
└──────────────────┘
```
