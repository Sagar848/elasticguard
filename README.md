# ElasticGuard 🛡️
### AI-Powered Elasticsearch Diagnostic & Autonomous Healing Platform

> 100% local · ES 7/8/9 compatible · OpenAI / Gemini / Claude / Ollama

---

## What It Does

ElasticGuard connects to your Elasticsearch cluster and:
1. **Auto-diagnoses** all issues: cluster health, node resource pressure, shard problems, index config issues
2. **AI agents** (LangGraph) analyze issues and generate step-by-step solutions with exact Elasticsearch API calls
3. **Asks your approval** before running any fix — via the UI, Discord, Slack, or Email
4. **Monitors** continuously and alerts you when thresholds are exceeded
5. **Visualizes** cluster topology in real-time (interactive node graph)

---

## Quick Start

### Option A: Docker Compose (Recommended)

```bash
git clone <repo> elasticguard && cd elasticguard

# Configure
cp .env.example .env
# Edit .env — set at least one AI provider key

# Start
./start.sh docker

# Open browser
open http://localhost:3000
```

### Option B: Fully Local with Ollama (No API Keys)

```bash
# 1. Install Ollama: https://ollama.ai
ollama pull llama3.2

# 2. Start app
cp .env.example .env
# Set: DEFAULT_AI_PROVIDER=ollama
./start.sh ollama

open http://localhost:3000
```

### Option C: Local Dev (No Docker)

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # edit with your keys
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

---

## AI Provider Setup

Configure in Settings UI or `.env`:

| Provider | .env Key | Free Tier |
|---|---|---|
| OpenAI | `OPENAI_API_KEY=sk-...` | No |
| Google Gemini | `GEMINI_API_KEY=AIza...` | Yes (1M tokens/day) |
| Anthropic | `ANTHROPIC_API_KEY=sk-ant-...` | No |
| Ollama (local) | `OLLAMA_BASE_URL=http://localhost:11434` | Yes (fully local) |
| Custom OpenAI-compatible | `CUSTOM_AI_BASE_URL=...` | Depends |

---

## URLS


| Name | URL | 
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger API | http://localhost:8000/docs |
| Prometheus metrics | http://localhost:8000/metrics/prometheus/metrics |

---

## Notification & Approval Setup

When AI suggests a fix, you'll be notified with **[Approve] / [Reject]** buttons.

### Discord
```bash
# Simple webhook (alerts only)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TOKEN

# Full interactive approval (bot)
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_CHANNEL_ID=your-channel-id
```

**Create Discord Bot:** discord.com/developers → New App → Bot → Copy token → Invite with Send Messages + Embed Links scope

### Slack
```bash
# Webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...

# Interactive bot
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C1234567890
```

**Create Slack App:** api.slack.com/apps → Create App → Incoming Webhooks or Bot Token

### Email (Gmail)
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=your-gmail-app-password   # Not your login password!
NOTIFICATION_EMAILS=ops@company.com,admin@company.com
```

**Gmail App Password:** myaccount.google.com → Security → 2-Step Verification → App passwords

---

## Connecting to Elasticsearch

After opening http://localhost:3000, enter:
- **URL**: e.g. `http://localhost:9200` or `https://mycluster.es.io:9243`
- **Username**: `elastic` (or leave blank for no auth)
- **Password**: your ES password
- **API Key**: alternative to username/password (Base64 key)

**If connecting from Docker to local ES:**
Use `http://host.docker.internal:9200` instead of `http://localhost:9200`

---

## Detected Issues (40+ rules)

- **Cluster**: Red/yellow health, too few masters, split-brain risk, circuit breakers
- **Nodes**: High CPU/heap/disk, hot node imbalance, thread pool rejections, GC pressure
- **Indices**: Write-blocked, no ILM policy, dynamic mapping issues, oversized/tiny shards
- **Shards**: Unassigned primaries/replicas, allocation failures, stuck recovery, corruption
- **Performance**: Slow queries, field data evictions, indexing queue buildup

---

## Docker Reference

```bash
docker compose up -d                    # Start
docker compose up -d --profile ollama  # Start with local LLM
docker compose logs -f                 # View logs
docker compose restart backend         # Restart backend
docker compose down                    # Stop
docker compose down -v                 # Stop + wipe data
docker compose up --build -d          # Rebuild after code changes
```

---

## Project Structure

```
elasticguard/
├── backend/               # FastAPI Python
│   ├── agents/            # LangGraph AI agents (multi-agent system)
│   ├── api/routes.py      # All REST + WebSocket endpoints
│   ├── core/
│   │   ├── es_client.py   # HTTP ES client (ES 7/8/9 compatible)
│   │   └── diagnostics.py # 40+ issue detection rules
│   ├── knowledge/         # ChromaDB RAG knowledge base
│   ├── monitoring/        # Background monitoring (30s interval)
│   ├── notifications/     # Discord/Slack/Email + approval system
│   └── simulators/        # Cluster change simulator
├── frontend/              # Next.js 14 TypeScript
│   ├── components/        # All UI components
│   └── lib/               # API client, Zustand store
├── docker-compose.yml
├── .env.example
└── start.sh
```
