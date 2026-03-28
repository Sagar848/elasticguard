# ElasticGuard 🛡️
### AI-Powered Elasticsearch Diagnostic & Autonomous Healing Platform

> ES 7 / 8 / 9 compatible &nbsp;·&nbsp; OpenAI / Gemini / Claude / Ollama &nbsp;·&nbsp; Real-time monitoring &nbsp;·&nbsp; Approval-gated fixes

---

## What It Does

ElasticGuard connects to your Elasticsearch cluster and:

1. **Auto-diagnoses** 40+ issue types — cluster health, node pressure, shard problems, index config issues
2. **AI agents** (LangGraph) analyse issues and generate step-by-step fixes with exact Elasticsearch API calls
3. **Auto-queues approvals** — critical/high issues with write-API fixes are automatically sent to the Approvals panel (and optionally to Discord/Slack/Email)
4. **One-click execute** — click Approve in the UI (or in your notification channel) to run the fix instantly
5. **Monitors continuously** — background checks every 30 seconds, alerts on threshold breaches
6. **Visualises** cluster topology in real-time (interactive node graph, index table, metrics)

---

## Prerequisites

| Tool | Required for | Download |
|------|-------------|----------|
| Docker Desktop | `docker`, `run-docker` modes | https://docker.com |
| Python 3.10+ | `local`, `build`, `run-local` modes | https://python.org |
| Node.js 20+ | `local`, `build`, `run-local` modes | https://nodejs.org |
| Git | Cloning the repo | https://git-scm.com |

---

## Installation & Start

### Step 1 — Clone

```bash
git clone https://github.com/your-org/elasticguard.git
cd elasticguard
```

### Step 2 — Configure

```bash
cp .env.example .env
# Edit .env and set at least one AI provider key (see AI Provider Setup below)
# You can also configure everything from the Settings page in the UI
```

### Step 3 — Choose a start mode

---

## Start Modes

### Linux / macOS — `start.sh`
### Windows — `start.cmd`

Both scripts have identical modes. Use `./start.sh MODE` on Linux/Mac and `start.cmd MODE` on Windows.

---

### `run-docker-with-ollama` — Run pre-built images from Docker Hub with ollama *(recommended)*

Pulls pre-built images and starts the app. **No source code required** — just Docker and a `.env` file.

```bash
# Linux / macOS
DOCKER_HUB_USER=yourname ./start.sh run-docker-with-ollama

# Windows
start.cmd run-docker
# (prompts for username if not set, or reads from .env.hub)
```

This is the recommended way to distribute ElasticGuard to users who just want to run it with ollama.

---

### `run-docker` — Run pre-built images from Docker Hub

Pulls pre-built images and starts the app. **No source code required** — just Docker and a `.env` file.

```bash
# Linux / macOS
DOCKER_HUB_USER=yourname ./start.sh run-docker

# Windows
start.cmd run-docker
# (prompts for username if not set, or reads from .env.hub)
```

This is the recommended way to distribute ElasticGuard to users who just want to run it.

---

### `docker` — Build from source + run in Docker

Builds the backend and frontend images locally, then starts all services.

```bash
# Linux / macOS
./start.sh docker

# Windows
start.cmd docker
```

**Requires:** Docker Desktop running.  
**First run:** Downloads Python and Node base images (~200 MB), then builds. Takes 3–5 minutes.  
**Subsequent runs:** Uses Docker layer cache — starts in under 30 seconds.

Services started:

| Service | URL | Notes |
|---------|-----|-------|
| Frontend (Next.js) | http://localhost:3000 | Main UI |
| Backend (FastAPI) | http://localhost:8000 | REST API + WebSocket |
| API Docs (Swagger) | http://localhost:8000/docs | Auto-generated |

---

### `build` — Compile locally without Docker

Installs Python dependencies and compiles the Next.js frontend. No Docker needed.  
The output can then be served with `run-local`.

```bash
# Linux / macOS
./start.sh build

# Windows
start.cmd build
```

**What it produces:**
- `backend/venv/` — Python virtual environment with all dependencies installed
- `frontend/.next/` — compiled Next.js production bundle

**Requires:** Python 3.10+ and Node.js 20+.

---

### `run-local` — Serve the local build

Serves the output of `build` in production mode (no hot reload, no Docker).  
Run `build` at least once before using this mode.

```bash
# Linux / macOS
./start.sh run-local

# Windows
start.cmd run-local
```

**Linux/macOS:** Both services run in the foreground. Press `Ctrl+C` to stop.  
**Windows:** Opens two separate command windows (Backend + Frontend). Close them or run `start.cmd stop`.  
Logs on Windows are written to `logs\backend.log` and `logs\frontend.log`.

---

### `local` — Dev mode with hot reload

Runs the development server with live code reloading. Use this for development.

```bash
# Linux / macOS
./start.sh local

# Windows
start.cmd local
```

**Linux/macOS:** Ctrl+C stops both services.  
**Windows:** Opens two `cmd` windows. Run `start.cmd stop` to close them.

---

### `ollama` — Local LLM, no API key needed

Starts everything via Docker and also runs Ollama locally with `llama3.2`.  
No AI API key required — completely free and private.

```bash
# Linux / macOS
./start.sh ollama

# Windows
start.cmd ollama
```

**First run:** Downloads the llama3.2 model (~2 GB). Subsequent starts use the cached model.  
**Requirements:** Docker Desktop, ~8 GB free disk space.

---

### `push` — Build and publish to Docker Hub

Builds Docker images and pushes them to your Docker Hub account.  
Anyone can then run ElasticGuard with `run-docker` without needing the source code.

```bash
# Linux / macOS
./start.sh push

# Windows
start.cmd push
```

The script prompts for:
- Your Docker Hub username
- An image tag (default: `latest`, or a version like `1.0.0`)
- The default backend URL to bake into the frontend image

After pushing, config is saved to `.env.hub` for use by `run-docker`.

---

### `docker-private` — Air-gapped / private registry

For environments without internet access. Pulls all base images from your internal registry (Artifactory, Nexus, Harbor, etc.) instead of Docker Hub.

```bash
# Linux / macOS
./start.sh docker-private

# Windows
start.cmd docker-private
```

The script prompts for:
- Registry URL (e.g. `artifactory.corp.com`)
- Authentication: Username+Password, API Key/Token, or None
- Optional sub-path (e.g. `docker-hub/`)

Config is saved to `.env.airgap` for quick re-runs:
```bash
# Re-run without re-entering credentials
source .env.airgap && docker compose -f docker-compose.airgap.yml up -d
```

---

### `stop` — Stop all services

```bash
./start.sh stop    # Linux / macOS
start.cmd stop     # Windows
```

Stops all Docker containers across all compose files, and kills any local uvicorn/node processes started by `local` or `run-local`.

---

### `logs` — Tail Docker logs

```bash
./start.sh logs              # standard compose
./start.sh logs --hub        # hub compose
./start.sh logs --airgap     # air-gapped compose
```

---

## Accessing from a Different Machine on Your Network

By default, ElasticGuard binds to `localhost` — it's only accessible from the machine it's running on. To access it from another machine (phone, laptop, colleague's PC):

### Step 1 — Find your machine's IP address

```bash
# Linux / macOS
ip route get 1 | awk '{print $7; exit}'
# or
hostname -I | awk '{print $1}'

# Windows (Command Prompt)
ipconfig
# Look for "IPv4 Address" under your active network adapter
```

Example result: `192.168.1.50`

### Step 2 — Rebuild with your IP as the backend URL

The frontend has the backend URL **baked in at build time** (`NEXT_PUBLIC_API_URL`). You must rebuild with your IP for cross-machine access:

```bash
# Linux / macOS
NEXT_PUBLIC_API_URL=http://192.168.1.50:8000 ./start.sh docker

# Windows (Command Prompt)
set NEXT_PUBLIC_API_URL=http://192.168.1.50:8000 && start.cmd docker

# Windows (PowerShell)
$env:NEXT_PUBLIC_API_URL="http://192.168.1.50:8000"; .\start.cmd docker
```

### Step 3 — Open the firewall (Windows)

Windows Firewall may block incoming connections on ports 3000 and 8000.  
Allow them in Windows Defender Firewall → Inbound Rules → New Rule → Port → TCP 3000, 8000.

### Step 4 — Access from the other machine

Open a browser on the other machine and go to:
```
http://192.168.1.50:3000
```

> **Note:** Replace `192.168.1.50` with your actual IP. The IP may change on restart unless you set a static IP on your machine.

### Accessing a hosted/server deployment

If ElasticGuard runs on a server with a hostname:

```bash
NEXT_PUBLIC_API_URL=http://elasticguard.corp.com:8000 ./start.sh docker
```

For HTTPS with a reverse proxy (nginx/Caddy), set:
```bash
NEXT_PUBLIC_API_URL=https://elasticguard-api.corp.com
```

---

## AI Provider Setup

Configure in **Settings → AI Provider** in the UI, or set in `.env`.  
Changes made in the UI are saved to the database and survive backend restarts.

| Provider | Key to set in `.env` | Models | Cost |
|----------|---------------------|--------|------|
| OpenAI | `OPENAI_API_KEY=sk-...` | gpt-4o, gpt-4o-mini | Paid |
| Google Gemini | `GEMINI_API_KEY=AIza...` | gemini-2.0-flash | Free tier available |
| Anthropic Claude | `ANTHROPIC_API_KEY=sk-ant-...` | claude-3-5-sonnet | Paid |
| Ollama (local) | `OLLAMA_BASE_URL=http://localhost:11434` | llama3.2, mistral, etc. | Free |
| Custom endpoint | `CUSTOM_AI_BASE_URL=http://...` | Any OpenAI-compatible | Depends |

**Getting API keys:**
- OpenAI: https://platform.openai.com/api-keys
- Gemini: https://aistudio.google.com/app/apikey
- Anthropic: https://console.anthropic.com/settings/keys

> **Security note:** API keys are passed as runtime environment variables and are **never baked into Docker images**. It is safe to push your images to Docker Hub.

---

## Connecting to Elasticsearch

After opening the UI, click **Clusters** → **Add Cluster**:

| Field | Example | Notes |
|-------|---------|-------|
| Nickname | `production` | Optional label |
| URL | `http://localhost:9200` | Full URL including port |
| Auth | Basic / API Key / None | |
| Verify SSL | Off | Turn on for valid TLS certs |

**Common URLs:**

```
Local ES (no auth):           http://localhost:9200
Local ES with auth:           http://localhost:9200  (username: elastic)
Docker ES (from host):        http://localhost:9200
Docker ES (backend in Docker):http://host.docker.internal:9200
Elastic Cloud:                https://xxx.us-central1.gcp.cloud.es.io
AWS OpenSearch:               https://xxx.us-east-1.es.amazonaws.com
```

**Connections are persisted** — they survive browser reloads and backend restarts. You can connect to multiple clusters and switch between them.

---

## Notifications & Approvals

### How it works

1. ElasticGuard scans your cluster and finds a critical/high issue with a fixable API call
2. An approval request is **automatically created** in the Approvals panel
3. If notification channels are configured, a message with Approve/Reject is sent there too
4. Click **Approve & Execute** — the Elasticsearch API call runs immediately
5. Click **Reject** — nothing changes on the cluster

The UI is always the primary way to approve. Discord/Slack/Email are optional remote alternatives.

### Discord

```bash
# In .env or Settings → Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TOKEN
```

Get webhook: Discord Server → Settings → Integrations → Webhooks → New Webhook

### Slack

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

Get webhook: https://api.slack.com/apps → Create App → Incoming Webhooks

### Email (Gmail)

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=xxxx-xxxx-xxxx-xxxx   # 16-char app password, NOT your login password
NOTIFICATION_EMAILS=ops@corp.com,admin@corp.com
```

Gmail app password: myaccount.google.com → Security → 2-Step Verification → App passwords

---

## Compose Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Standard build-from-source compose |
| `docker-compose.hub.yml` | Run pre-built images from Docker Hub |
| `docker-compose.airgap.yml` | Build using a private/internal registry |

### Useful Docker commands

```bash
# View running containers
docker compose ps

# View logs (follow)
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend

# Restart a single service
docker compose restart backend

# Rebuild after code changes
docker compose up --build -d

# Stop all containers
docker compose down

# Stop and delete all data volumes (DESTRUCTIVE)
docker compose down -v

# Force re-pull of all images (hub mode)
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d
```

---

## Project Structure

```
elasticguard/
├── backend/                        FastAPI Python backend
│   ├── agents/langgraph_agents.py  LangGraph multi-agent AI pipeline
│   ├── api/routes.py               All REST + WebSocket endpoints
│   ├── core/
│   │   ├── config.py               App settings (pydantic-settings)
│   │   ├── diagnostics.py          40+ issue detection rules
│   │   ├── es_client.py            Async HTTP ES client (ES 7/8/9)
│   │   └── persistence.py          SQLite store (clusters + AI config)
│   ├── knowledge/knowledge_base.py  ChromaDB RAG knowledge base
│   ├── monitoring/scheduler.py      Background health checks
│   ├── notifications/manager.py     Discord / Slack / Email + approvals
│   └── simulators/engine.py        Physics-based cluster simulator
│
├── frontend/                        Next.js 14 TypeScript UI
│   ├── app/                         Next.js app router pages
│   ├── components/
│   │   ├── ApprovalsPanel.tsx        Approve / reject AI fixes
│   │   ├── ClusterManager.tsx        Add / switch / remove clusters
│   │   ├── Dashboard.tsx             Main layout + routing
│   │   ├── IndexTable.tsx            Paginated sortable index table
│   │   ├── IssuePanel.tsx            Issues with run + copy buttons
│   │   ├── MetricsPanel.tsx          Real-time charts
│   │   ├── SettingsPanel.tsx         AI provider + notification config
│   │   ├── SimulatorPanel.tsx        What-if cluster simulator
│   │   └── TopologyView.tsx          Interactive cluster graph
│   └── lib/
│       ├── api.ts                    All API client functions
│       ├── store.ts                  Zustand global state (persisted)
│       └── useWebSocket.ts           Auto-reconnecting WS hook
│
├── docker-compose.yml               Standard (build from source)
├── docker-compose.hub.yml           Pre-built images from Docker Hub
├── docker-compose.airgap.yml        Private/air-gapped registry
├── start.sh                         Linux/macOS start script
├── start.cmd                        Windows start script
├── .env.example                     All config options with comments
└── SETUP.md                         Detailed setup guide
```

---

## Troubleshooting

### `Failed to fetch` when connecting to a cluster in Docker mode

The backend runs inside Docker. It cannot reach `localhost:9200` on your host machine.

**Fix:** Use `host.docker.internal` instead of `localhost`:
```
http://host.docker.internal:9200
```

`host.docker.internal` resolves to your host machine's IP from inside any Docker container (works on Windows, macOS, and Linux with Docker Desktop).

### `Failed to fetch` on page load after rebuilding

The frontend has `NEXT_PUBLIC_API_URL` baked in at build time. If you rebuilt without setting it, it defaults to `http://localhost:8000`. Verify the backend is running and accessible at that URL, then check the browser's Network tab for the failing request.

### AI chat returns 500 / "model not found"

Google deprecated `gemini-1.5-pro`. If you have that saved, update to `gemini-2.0-flash` in **Settings → AI Provider → Model**.

### Connections disappear after backend restart

Connections are saved to `backend/data/elasticguard.db` (SQLite). The page auto-reconnects on load. If the DB file is deleted (e.g. `docker compose down -v`), you'll need to re-add clusters.

### Docker build gets `CANCELED: context canceled`

This was caused by missing `.dockerignore` files — Docker was sending huge directories (`venv/`, `node_modules/`, `data/`) to the daemon. Both `.dockerignore` files are now included in the repo. If you still see this, verify `backend/.dockerignore` and `frontend/.dockerignore` exist.

### Cannot access UI from another machine

See [Accessing from a Different Machine](#accessing-from-a-different-machine-on-your-network) above. The short answer: rebuild with `NEXT_PUBLIC_API_URL=http://your-ip:8000`.

### Windows: `uvicorn` not found in `run-local`

The `venv\Scripts` folder must be on the PATH. Run `start.cmd build` first to create and populate the venv, then `start.cmd run-local` which activates it automatically.

### Port already in use

```bash
# Find what's using port 8000 (Linux/Mac)
lsof -i :8000

# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

---

## Environment Variables Reference

All variables can be set in `.env` (copy from `.env.example`) or passed at runtime.

```bash
# ── AI Providers ─────────────────────────────────────────────────────────────
DEFAULT_AI_PROVIDER=openai          # openai | gemini | anthropic | ollama | custom
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4o
GEMINI_API_KEY=AIza...
GEMINI_DEFAULT_MODEL=gemini-2.0-flash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_DEFAULT_MODEL=claude-3-5-sonnet-20241022
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2

# ── Notifications ─────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your-app-password
NOTIFICATION_EMAILS=admin@corp.com

# ── Monitoring ────────────────────────────────────────────────────────────────
MONITORING_INTERVAL_SECONDS=30
ALERT_CPU_THRESHOLD=80
ALERT_JVM_THRESHOLD=85
ALERT_DISK_THRESHOLD=85

# ── Network (Docker mode) ─────────────────────────────────────────────────────
# URL the browser uses to reach the backend — must be reachable from
# the end user's machine, not from inside Docker.
NEXT_PUBLIC_API_URL=http://localhost:8000
```
