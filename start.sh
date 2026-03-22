#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  ElasticGuard — Start Script
#  Usage:
#    ./start.sh              → Docker Compose (recommended)
#    ./start.sh local        → Local dev (Python venv + npm dev)
#    ./start.sh docker       → Docker Compose
#    ./start.sh stop         → Stop all services
# ═══════════════════════════════════════════════════════════════
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'

banner() {
  echo -e "${CYAN}${BOLD}"
  echo "  ┌─────────────────────────────────────────┐"
  echo "  │   ElasticGuard  —  AI ES Diagnostics    │"
  echo "  └─────────────────────────────────────────┘"
  echo -e "${NC}"
}

info()    { echo -e "${CYAN}▶${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

MODE="${1:-docker}"

# ─── Stop ─────────────────────────────────────────────────────
if [ "$MODE" = "stop" ]; then
  info "Stopping ElasticGuard..."
  if [ -f "docker-compose.yml" ]; then docker-compose down; fi
  # Kill local processes if running
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "next dev"         2>/dev/null || true
  success "Stopped"
  exit 0
fi

banner

# ─── Create .env if missing ───────────────────────────────────
if [ ! -f ".env" ]; then
  warn ".env not found — creating from .env.example"
  if [ -f ".env.example" ]; then
    cp .env.example .env
    success "Created .env — edit it with your API keys"
  else
    cat > .env << 'EOF'
DEFAULT_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2
SECRET_KEY=change-me-to-random-string-32chars
APPROVAL_WEBHOOK_SECRET=change-me-approval-secret
MONITORING_INTERVAL_SECONDS=30
ALERT_CPU_THRESHOLD=80
ALERT_JVM_THRESHOLD=85
ALERT_DISK_THRESHOLD=85
EOF
    success "Created .env with Ollama defaults"
  fi
fi

# ─── Docker Mode ──────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null 2>&1 || error "Docker not found. Install from https://docker.com"
  command -v docker-compose >/dev/null 2>&1 || \
    docker compose version >/dev/null 2>&1   || error "Docker Compose not found."

  info "Starting with Docker Compose..."
  docker-compose up -d --build

  echo ""
  success "ElasticGuard is running!"
  echo ""
  echo -e "  ${BOLD}Frontend:${NC}  http://localhost:3000"
  echo -e "  ${BOLD}Backend:${NC}   http://localhost:8000"
  echo -e "  ${BOLD}API Docs:${NC}  http://localhost:8000/docs"
  echo -e "  ${BOLD}Metrics:${NC}   http://localhost:8000/metrics/prometheus/metrics"
  echo ""
  warn "First run: Ollama will pull llama3.2 (~2GB). This takes a few minutes."
  echo ""
  echo -e "  ${CYAN}Logs:${NC}  docker-compose logs -f backend"
  echo -e "  ${CYAN}Stop:${NC}  ./start.sh stop"
  exit 0
fi

# ─── Local Mode ───────────────────────────────────────────────
if [ "$MODE" = "local" ]; then
  PIDS=()
  cleanup() {
    echo ""
    info "Stopping services..."
    for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
    success "Stopped"
  }
  trap cleanup SIGINT SIGTERM EXIT

  # ── Backend ────────────────────────────────────────────────
  info "Setting up backend..."
  cd "$SCRIPT_DIR/backend"

  if [ ! -d "venv" ]; then
    python3 -m venv venv
    info "Created Python virtual environment"
  fi

  # Activate venv
  if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate   # Windows Git Bash
  else
    source venv/bin/activate
  fi

  pip install -q -r requirements.txt

  # Create data dirs
  mkdir -p data/chroma

  # Copy .env
  [ -f "../.env" ] && cp "../.env" ".env"

  info "Starting backend on :8000..."
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  PIDS+=($!)

  # ── Frontend ──────────────────────────────────────────────
  cd "$SCRIPT_DIR/frontend"
  info "Setting up frontend..."

  if [ ! -d "node_modules" ]; then
    npm install
  fi

  # Create .env.local
  cat > .env.local << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
EOF

  info "Starting frontend on :3000..."
  npm run dev &
  PIDS+=($!)

  echo ""
  success "ElasticGuard is running!"
  echo ""
  echo -e "  ${BOLD}Frontend:${NC}  http://localhost:3000"
  echo -e "  ${BOLD}Backend:${NC}   http://localhost:8000"
  echo -e "  ${BOLD}API Docs:${NC}  http://localhost:8000/docs"
  echo ""
  echo "  Press Ctrl+C to stop all services"
  echo ""

  # Wait for both processes
  wait
fi
