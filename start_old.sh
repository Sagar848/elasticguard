#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ElasticGuard — Start Script
#  Usage: ./start.sh [docker | docker-private | local | ollama | stop | logs]
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
RED='\033[0;31m';   BOLD='\033[1m';       NC='\033[0m'

info()    { echo -e "${CYAN}▶${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }
ask()     { echo -en "${BOLD}$1${NC} "; read -r REPLY; echo "$REPLY"; }
ask_pass(){ echo -en "${BOLD}$1${NC} "; read -rs REPLY; echo; echo "$REPLY"; }
banner()  { echo -e "${CYAN}"; echo "$1"; echo -e "${NC}"; }

# ── Banner ─────────────────────────────────────────────────────────────────────
banner "
  ┌─────────────────────────────────────────────┐
  │   ElasticGuard — AI Elasticsearch Diagnostics │
  └─────────────────────────────────────────────┘"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

MODE="${1:-docker}"

# ── Helpers ────────────────────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker &>/dev/null; then
    error "Docker not found. Install Docker Desktop from https://docker.com"
  fi
  if ! docker info &>/dev/null; then
    error "Docker daemon is not running. Start Docker Desktop and try again."
  fi
}

ensure_env() {
  if [ ! -f ".env" ]; then
    warn "No .env found — creating from .env.example"
    cp .env.example .env
    warn "Edit .env with your API keys before using AI features."
    echo ""
  fi
}

# Enable BuildKit for faster, more reliable builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# ── MODE: docker ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ] || [ "$MODE" = "d" ]; then
  check_docker
  ensure_env

  info "Building images and starting services (this may take a few minutes on first run)..."
  echo ""

  # Pull base images first with retries — this prevents the CANCELED error
  # caused by network timeouts during multi-layer builds
  info "Pulling base images (with retry on failure)..."
  for IMAGE in "python:3.11-slim" "node:20-alpine"; do
    ATTEMPTS=0
    until docker pull "$IMAGE" 2>/dev/null; do
      ATTEMPTS=$((ATTEMPTS+1))
      if [ $ATTEMPTS -ge 3 ]; then
        warn "Could not pull $IMAGE after 3 attempts — will use cached version if available"
        break
      fi
      warn "Pull failed for $IMAGE, retrying ($ATTEMPTS/3)..."
      sleep 5
    done
  done

  docker compose up --build -d

  echo ""
  success "ElasticGuard is running!"
  echo ""
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  echo -e "  API Docs:  ${CYAN}http://localhost:8000/docs${NC}"
  echo ""
  echo -e "  Logs:   ${YELLOW}./start.sh logs${NC}"
  echo -e "  Stop:   ${YELLOW}./start.sh stop${NC}"

# ── MODE: docker-private (air-gapped / private registry) ──────────────────────
elif [ "$MODE" = "docker-private" ] || [ "$MODE" = "private" ]; then
  check_docker
  ensure_env

  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   Private / Air-Gapped Registry Setup               ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo "  ElasticGuard will pull all base images from your private"
  echo "  registry (Artifactory, Nexus, Harbor, etc.) instead of"
  echo "  Docker Hub. Your registry must proxy or cache:"
  echo ""
  echo "    python:3.11-slim     node:20-alpine"
  echo "    ollama/ollama:latest (optional, for local LLM)"
  echo ""

  # ── Collect registry details ─────────────────────────────────────────────
  REGISTRY_URL=$(ask "Registry URL (e.g. artifactory.corp.com or registry.corp.com:5000):")

  # Normalise: strip trailing slash, strip https://
  REGISTRY_URL="${REGISTRY_URL%/}"
  REGISTRY_URL="${REGISTRY_URL#https://}"
  REGISTRY_URL="${REGISTRY_URL#http://}"

  echo ""
  echo "  Authentication options:"
  echo "    1) Username + Password"
  echo "    2) API Key / Token"
  echo "    3) No authentication (open registry)"
  echo ""
  AUTH_TYPE=$(ask "Choose [1/2/3]:")

  case "$AUTH_TYPE" in
    1)
      REG_USER=$(ask "Registry username:")
      REG_PASS=$(ask_pass "Registry password:")
      echo ""
      info "Logging in to ${REGISTRY_URL}..."
      echo "$REG_PASS" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || error "Login failed. Check credentials and registry URL."
      ;;
    2)
      REG_TOKEN=$(ask_pass "API Key / Token:")
      echo ""
      # Many registries accept token as username or as password with a fixed username
      REG_USER=$(ask "Username for token auth (leave blank for 'token' default):")
      REG_USER="${REG_USER:-token}"
      info "Logging in to ${REGISTRY_URL}..."
      echo "$REG_TOKEN" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || error "Login failed. Check token and registry URL."
      ;;
    3)
      info "Skipping authentication (open registry)"
      ;;
    *)
      error "Invalid choice. Run ./start.sh docker-private again."
      ;;
  esac

  # ── Optional: custom image names (if registry stores them under different paths)
  echo ""
  echo "  By default, images are referenced as:"
  echo "    ${REGISTRY_URL}/python:3.11-slim"
  echo "    ${REGISTRY_URL}/node:20-alpine"
  echo ""
  USE_CUSTOM=$(ask "Use a sub-path or repository prefix in your registry? (y/N):")

  REPO_PREFIX=""
  if [[ "${USE_CUSTOM,,}" == "y" ]]; then
    REPO_PREFIX=$(ask "Repository sub-path (e.g. 'docker-hub' or 'proxy' — leave blank for none):")
    if [ -n "$REPO_PREFIX" ]; then
      REPO_PREFIX="${REPO_PREFIX%/}/"
    fi
  fi

  # Build the full REGISTRY_PREFIX used in docker-compose
  # Result examples:
  #   artifactory.corp.com/                      → prepended to every image
  #   artifactory.corp.com/docker-hub/           → with sub-path
  REGISTRY_PREFIX="${REGISTRY_URL}/${REPO_PREFIX}"

  echo ""
  info "Registry prefix: ${BOLD}${REGISTRY_PREFIX}${NC}"
  echo ""
  echo "  Images will be pulled as:"
  echo "    ${REGISTRY_PREFIX}python:3.11-slim"
  echo "    ${REGISTRY_PREFIX}node:20-alpine"
  echo ""

  # ── Optional: save to .env.airgap for future runs ─────────────────────────
  cat > .env.airgap << ENVEOF
# Auto-generated by ./start.sh docker-private
# Re-run ./start.sh docker-private to update credentials
REGISTRY_PREFIX=${REGISTRY_PREFIX}
REGISTRY_URL=${REGISTRY_URL}
ENVEOF
  info "Saved registry config to .env.airgap (re-use with ./start.sh docker-private --saved)"

  # ── Pull base images from private registry first ──────────────────────────
  echo ""
  info "Pulling base images from private registry..."
  for IMAGE in "python:3.11-slim" "node:20-alpine"; do
    FULL_IMAGE="${REGISTRY_PREFIX}${IMAGE}"
    ATTEMPTS=0
    until docker pull "$FULL_IMAGE"; do
      ATTEMPTS=$((ATTEMPTS+1))
      if [ $ATTEMPTS -ge 3 ]; then
        warn "Could not pull $FULL_IMAGE after 3 attempts."
        warn "Make sure your registry proxies Docker Hub and the image exists."
        error "Aborting. Fix the image reference and try again."
      fi
      warn "Retrying pull ($ATTEMPTS/3)..."
      sleep 5
    done
    # Tag locally so the Dockerfile FROM line resolves without the prefix
    # This means even if the Dockerfile uses 'python:3.11-slim', Docker
    # finds the locally-tagged image from your registry
    docker tag "${FULL_IMAGE}" "${IMAGE}" 2>/dev/null || true
    success "Pulled ${FULL_IMAGE}"
  done

  # ── Build and start using air-gap compose file ────────────────────────────
  echo ""
  info "Building ElasticGuard images using private registry..."
  export REGISTRY_PREFIX

  DOCKER_BUILDKIT=1 docker compose \
    -f docker-compose.airgap.yml \
    up --build -d

  echo ""
  success "ElasticGuard is running (air-gapped mode)!"
  echo ""
  echo -e "  Registry used: ${CYAN}${REGISTRY_URL}${NC}"
  echo -e "  Frontend:      ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:       ${CYAN}http://localhost:8000${NC}"
  echo -e "  API Docs:      ${CYAN}http://localhost:8000/docs${NC}"
  echo ""
  echo -e "  To re-run without re-entering credentials:"
  echo -e "    ${YELLOW}REGISTRY_PREFIX=${REGISTRY_PREFIX} docker compose -f docker-compose.airgap.yml up -d${NC}"
  echo ""
  echo -e "  Logs:   ${YELLOW}./start.sh logs --airgap${NC}"
  echo -e "  Stop:   ${YELLOW}./start.sh stop${NC}"

# ── MODE: --saved (re-use last saved air-gap config) ──────────────────────────
elif [ "$MODE" = "docker-private" ] && [ "${2:-}" = "--saved" ]; then
  check_docker
  if [ ! -f ".env.airgap" ]; then
    error "No saved config found. Run ./start.sh docker-private first."
  fi
  # shellcheck source=/dev/null
  source .env.airgap
  info "Re-using saved registry: ${REGISTRY_URL}"
  export REGISTRY_PREFIX
  docker compose -f docker-compose.airgap.yml up --build -d
  success "ElasticGuard started using saved registry config."

# ── MODE: local ────────────────────────────────────────────────────────────────
elif [ "$MODE" = "local" ] || [ "$MODE" = "dev" ]; then
  info "Starting in local development mode..."

  command -v python3 &>/dev/null || error "Python 3 not found"
  command -v node    &>/dev/null || error "Node.js not found"

  # Backend
  info "Setting up backend..."
  cd backend
  if [ ! -d "venv" ]; then
    python3 -m venv venv
    success "Created virtual environment"
  fi

  # Activate venv (works on Linux/Mac; Windows users use Git Bash)
  # shellcheck source=/dev/null
  if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate   # Windows Git Bash
  else
    source venv/bin/activate       # Linux / macOS
  fi

  pip install -r requirements.txt -q
  mkdir -p data/chroma knowledge/docs

  if [ ! -f ".env" ]; then
    cp ../.env.example .env
    warn "Created backend/.env — edit with your API keys"
  fi

  info "Starting backend on :8000..."
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  cd ..

  # Frontend
  info "Setting up frontend..."
  cd frontend
  if [ ! -d "node_modules" ]; then
    npm install
  fi

  echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

  info "Starting frontend on :3000..."
  npm run dev &
  FRONTEND_PID=$!
  cd ..

  echo ""
  success "ElasticGuard is running!"
  echo ""
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  echo -e "  API Docs:  ${CYAN}http://localhost:8000/docs${NC}"
  echo ""
  echo "  Press Ctrl+C to stop all services"

  trap "kill \$BACKEND_PID \$FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
  wait

# ── MODE: ollama ───────────────────────────────────────────────────────────────
elif [ "$MODE" = "ollama" ]; then
  check_docker
  ensure_env
  sed -i 's/DEFAULT_AI_PROVIDER=.*/DEFAULT_AI_PROVIDER=ollama/' .env 2>/dev/null || true

  info "Starting with Ollama local LLM..."
  docker compose --profile ollama up --build -d

  echo ""
  warn "Pulling llama3.2 model (first run: ~2 GB download)..."
  sleep 12
  docker exec elasticguard-ollama ollama pull llama3.2 \
    || warn "Pull manually: docker exec elasticguard-ollama ollama pull llama3.2"

  echo ""
  success "ElasticGuard + Ollama running!"
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Ollama:    ${CYAN}http://localhost:11434${NC}"

# ── MODE: stop ─────────────────────────────────────────────────────────────────
elif [ "$MODE" = "stop" ]; then
  info "Stopping all ElasticGuard services..."
  docker compose down             2>/dev/null || true
  docker compose -f docker-compose.airgap.yml down 2>/dev/null || true
  success "All services stopped."

# ── MODE: logs ─────────────────────────────────────────────────────────────────
elif [ "$MODE" = "logs" ]; then
  COMPOSE_FILE="docker-compose.yml"
  if [ "${2:-}" = "--airgap" ] || [ "${2:-}" = "-a" ]; then
    COMPOSE_FILE="docker-compose.airgap.yml"
  fi
  docker compose -f "$COMPOSE_FILE" logs -f --tail=100

# ── Help ───────────────────────────────────────────────────────────────────────
else
  echo -e "${BOLD}Usage:${NC}  ./start.sh [MODE]"
  echo ""
  echo -e "${BOLD}Modes:${NC}"
  echo "  docker          Build and run with Docker Compose (recommended)"
  echo "  docker-private  Air-gapped/private registry mode — prompts for"
  echo "                  registry URL, username/password or API key"
  echo "  local           Run backend + frontend locally (dev mode, no Docker)"
  echo "  ollama          Docker Compose + Ollama local LLM (llama3.2)"
  echo "  stop            Stop all running containers"
  echo "  logs            Tail container logs (add --airgap for private mode)"
  echo ""
  echo -e "${BOLD}Examples:${NC}"
  echo "  ./start.sh docker"
  echo "  ./start.sh docker-private"
  echo "  ./start.sh local"
  echo "  ./start.sh stop"
  echo ""
  echo -e "${BOLD}Air-gapped quick re-run (after first setup):${NC}"
  echo "  source .env.airgap && docker compose -f docker-compose.airgap.yml up -d"
fi
