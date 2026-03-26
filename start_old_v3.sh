#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ElasticGuard — Start / Build / Run Script
#
#  Usage: ./start.sh [MODE] [OPTIONS]
#
#  Modes:
#    docker          Build images from source and run (recommended for devs)
#    docker-private  Same but pulls base images from a private/air-gapped registry
#    build           Build and push images to Docker Hub (for publishing)
#    run             Pull and run pre-built images from Docker Hub (no code needed)
#    local           Run backend + frontend directly on this machine (dev mode)
#    ollama          Docker + local Llama LLM via Ollama
#    stop            Stop all containers
#    logs            Tail logs
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
RED='\033[0;31m';   BOLD='\033[1m';       NC='\033[0m'

info()    { echo -e "${CYAN}▶${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }
ask()     { echo -en "${BOLD}$1${NC} "; read -r REPLY; echo "$REPLY"; }
ask_pass(){ echo -en "${BOLD}$1${NC} "; read -rs REPLY; echo; echo "$REPLY"; }
divider() { echo -e "${CYAN}────────────────────────────────────────────────────${NC}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
echo "  ┌───────────────────────────────────────────────┐"
echo "  │  ElasticGuard — AI Elasticsearch Diagnostics  │"
echo "  └───────────────────────────────────────────────┘"
echo -e "${NC}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

MODE="${1:-help}"

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# ── Helpers ───────────────────────────────────────────────────────────────────
check_docker() {
  command -v docker &>/dev/null || error "Docker not found. Install from https://docker.com"
  docker info &>/dev/null       || error "Docker daemon is not running. Start Docker Desktop."
}

ensure_env() {
  if [ ! -f ".env" ]; then
    warn "No .env found — creating from .env.example"
    cp .env.example .env
    warn "Edit .env with your API keys before using AI features."
    echo ""
  fi
}

pull_base_images() {
  info "Pre-pulling base images to avoid mid-build timeouts..."
  for IMAGE in "python:3.11-slim" "node:20-alpine"; do
    ATTEMPTS=0
    until docker pull "$IMAGE" 2>/dev/null; do
      ATTEMPTS=$((ATTEMPTS+1))
      [ $ATTEMPTS -ge 3 ] && { warn "Could not pull $IMAGE — will use cache if available"; break; }
      warn "Retrying $IMAGE ($ATTEMPTS/3)..."; sleep 5
    done
  done
}

get_api_url() {
  # NEXT_PUBLIC_API_URL must be the URL the BROWSER uses to reach the backend.
  # localhost works when the user opens the app on the same machine as Docker.
  if [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
    export NEXT_PUBLIC_API_URL="http://localhost:8000"
  fi
  info "Browser → Backend URL: ${BOLD}${NEXT_PUBLIC_API_URL}${NC}"
  echo -e "  ${YELLOW}(Override: NEXT_PUBLIC_API_URL=http://your-ip:8000 ./start.sh ...)${NC}"
  echo ""
}

# ── MODE: docker ──────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ] || [ "$MODE" = "d" ]; then
  check_docker
  ensure_env
  get_api_url
  pull_base_images

  info "Building and starting ElasticGuard..."
  docker compose up --build -d

  echo ""
  success "ElasticGuard is running!"
  divider
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  echo -e "  API Docs:  ${CYAN}http://localhost:8000/docs${NC}"
  divider
  echo -e "  Logs:  ${YELLOW}./start.sh logs${NC}    Stop: ${YELLOW}./start.sh stop${NC}"

# ── MODE: build ───────────────────────────────────────────────────────────────
# Builds images from source and pushes to Docker Hub.
# Anyone can then run them with ./start.sh run (no code needed).
elif [ "$MODE" = "build" ]; then
  check_docker

  echo ""
  echo -e "${BOLD}Build & Push to Docker Hub${NC}"
  echo "Builds the backend and frontend images and pushes them to"
  echo "your Docker Hub account so others can use them without the code."
  divider
  echo ""

  # ── Get Docker Hub details ─────────────────────────────────────────────────
  DOCKER_HUB_USER="${DOCKER_HUB_USER:-}"
  echo "Docker Hub username is needed to tag and push the images."
  if [ -z "$DOCKER_HUB_USER" ]; then
  echo "Docker Hub username (e.g. johndoe), If you don't have one, create a free account at https://hub.docker.com/signup"
    DOCKER_HUB_USER=$(ask "Docker Hub username (e.g. johndoe):")
  fi
  
  TAG="${TAG:-latest}"
  echo "Image tag [${TAG}] (press Enter to keep, or type e.g. 1.0.0):"
  CUSTOM_TAG=$(ask "Image tag [${TAG}] (press Enter to keep, or type e.g. 1.0.0):")
  [ -n "$CUSTOM_TAG" ] && TAG="$CUSTOM_TAG"

  BACKEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-backend:${TAG}"
  FRONTEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-frontend:${TAG}"

  echo ""
  echo "Will build and push:"
  echo -e "  ${CYAN}${BACKEND_IMAGE}${NC}"
  echo -e "  ${CYAN}${FRONTEND_IMAGE}${NC}"
  echo ""

  # ── NEXT_PUBLIC_API_URL for the image ─────────────────────────────────────
  echo "The frontend image has the backend URL baked in at build time."
  echo "Users can override it at runtime via NEXT_PUBLIC_API_URL env var,"
  echo "but the default inside the image must be set now."
  echo ""
  echo -e "  ${YELLOW}For Docker Hub images used on localhost: http://localhost:8000${NC}"
  echo -e "  ${YELLOW}For a hosted server: http://your-server-ip:8000${NC}"
  echo ""
  echo "Default backend URL for this image [http://localhost:8000]:"
  echo ""
  BUILD_API_URL=$(ask "Default backend URL for this image [http://localhost:8000]:")
  BUILD_API_URL="${BUILD_API_URL:-http://localhost:8000}"

  echo ""
  echo "Proceed with build and push? (y/N):"
  CONFIRM=$(ask "Proceed with build and push? (y/N):")
  [[ "${CONFIRM,,}" != "y" ]] && { info "Cancelled."; exit 0; }

  # ── Login ─────────────────────────────────────────────────────────────────
  echo ""
  info "Logging in to Docker Hub..."
  docker login -u "$DOCKER_HUB_USER" \
    || error "Docker Hub login failed. Check your credentials."

  # ── Pre-pull base images ───────────────────────────────────────────────────
  pull_base_images

  # ── Build backend ─────────────────────────────────────────────────────────
  echo ""
  info "Building backend image: ${BACKEND_IMAGE}"
  docker build \
    --platform linux/amd64 \
    --tag "$BACKEND_IMAGE" \
    --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --label "org.opencontainers.image.title=ElasticGuard Backend" \
    --label "org.opencontainers.image.description=AI-Powered Elasticsearch Diagnostics API" \
    ./backend

  # ── Build frontend ────────────────────────────────────────────────────────
  echo ""
  info "Building frontend image: ${FRONTEND_IMAGE}"
  docker build \
    --platform linux/amd64 \
    --tag "$FRONTEND_IMAGE" \
    --build-arg "NEXT_PUBLIC_API_URL=${BUILD_API_URL}" \
    --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --label "org.opencontainers.image.title=ElasticGuard Frontend" \
    --label "org.opencontainers.image.description=AI-Powered Elasticsearch Diagnostics UI" \
    ./frontend

  # ── Also tag as latest if versioned ────────────────────────────────────────
  if [ "$TAG" != "latest" ]; then
    docker tag "$BACKEND_IMAGE"  "${DOCKER_HUB_USER}/elasticguard-backend:latest"
    docker tag "$FRONTEND_IMAGE" "${DOCKER_HUB_USER}/elasticguard-frontend:latest"
  fi

  # ── Push ──────────────────────────────────────────────────────────────────
  echo ""
  info "Pushing to Docker Hub..."
  docker push "$BACKEND_IMAGE"
  docker push "$FRONTEND_IMAGE"

  if [ "$TAG" != "latest" ]; then
    docker push "${DOCKER_HUB_USER}/elasticguard-backend:latest"
    docker push "${DOCKER_HUB_USER}/elasticguard-frontend:latest"
  fi

  # ── Save config for future runs ────────────────────────────────────────────
  cat > .env.hub << ENVEOF
# Auto-generated by ./start.sh build
# Used by ./start.sh run
DOCKER_HUB_USER=${DOCKER_HUB_USER}
TAG=${TAG}
ENVEOF

  echo ""
  success "Images pushed to Docker Hub!"
  divider
  echo -e "  Backend:   ${CYAN}https://hub.docker.com/r/${DOCKER_HUB_USER}/elasticguard-backend${NC}"
  echo -e "  Frontend:  ${CYAN}https://hub.docker.com/r/${DOCKER_HUB_USER}/elasticguard-frontend${NC}"
  divider
  echo ""
  echo "Anyone can now run ElasticGuard without the code:"
  echo ""
  echo -e "  ${BOLD}Quick start for users:${NC}"
  echo -e "  ${YELLOW}DOCKER_HUB_USER=${DOCKER_HUB_USER} docker compose -f docker-compose.hub.yml up -d${NC}"
  echo ""
  echo -e "  Or with start.sh:  ${YELLOW}DOCKER_HUB_USER=${DOCKER_HUB_USER} ./start.sh run${NC}"
  echo ""
  echo -e "  ${BOLD}To update docker-compose.hub.yml with your username:${NC}"
  echo -e "  ${YELLOW}sed -i 's/yourdockerhubuser/${DOCKER_HUB_USER}/g' docker-compose.hub.yml${NC}"

# ── MODE: run ─────────────────────────────────────────────────────────────────
# Pulls pre-built images from Docker Hub and runs them.
# No code or build step required.
elif [ "$MODE" = "run" ]; then
  check_docker

  echo ""
  echo -e "${BOLD}Run ElasticGuard from Docker Hub (no code needed)${NC}"
  divider
  echo ""

  # ── Determine Docker Hub user ──────────────────────────────────────────────
  DOCKER_HUB_USER="${DOCKER_HUB_USER:-}"

  # Check .env.hub first (set by ./start.sh build)
  if [ -z "$DOCKER_HUB_USER" ] && [ -f ".env.hub" ]; then
    # shellcheck source=/dev/null
    source .env.hub
    info "Using Docker Hub config from .env.hub (user: ${DOCKER_HUB_USER})"
  fi

  # Still empty? Ask.
  if [ -z "$DOCKER_HUB_USER" ]; then
    DOCKER_HUB_USER=$(ask "Docker Hub username where images are published:")
  fi

  TAG="${TAG:-latest}"

  # ── Update docker-compose.hub.yml with the real username ─────────────────
  if grep -q "yourdockerhubuser" docker-compose.hub.yml 2>/dev/null; then
    info "Setting Docker Hub user in docker-compose.hub.yml..."
    # Use a temp file for portability (sed -i differs between macOS and Linux)
    sed "s/yourdockerhubuser/${DOCKER_HUB_USER}/g" docker-compose.hub.yml > docker-compose.hub.tmp \
      && mv docker-compose.hub.tmp docker-compose.hub.yml
  fi

  # ── NEXT_PUBLIC_API_URL ───────────────────────────────────────────────────
  if [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
    export NEXT_PUBLIC_API_URL="http://localhost:8000"
  fi

  # ── Create .env if missing ─────────────────────────────────────────────────
  ensure_env

  # ── Pull images ────────────────────────────────────────────────────────────
  echo ""
  info "Pulling images from Docker Hub..."
  BACKEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-backend:${TAG}"
  FRONTEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-frontend:${TAG}"

  docker pull "$BACKEND_IMAGE"  || error "Could not pull ${BACKEND_IMAGE}. Check the username and that the image is public."
  docker pull "$FRONTEND_IMAGE" || error "Could not pull ${FRONTEND_IMAGE}."

  success "Images pulled."

  # ── Start ─────────────────────────────────────────────────────────────────
  echo ""
  info "Starting ElasticGuard..."
  DOCKER_HUB_USER="$DOCKER_HUB_USER" TAG="$TAG" \
    docker compose -f docker-compose.hub.yml up -d

  echo ""
  success "ElasticGuard is running!"
  divider
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  echo -e "  API Docs:  ${CYAN}http://localhost:8000/docs${NC}"
  divider
  echo -e "  Images from: ${CYAN}hub.docker.com/u/${DOCKER_HUB_USER}${NC}"
  echo -e "  Logs:  ${YELLOW}./start.sh logs --hub${NC}    Stop: ${YELLOW}./start.sh stop${NC}"
  echo ""
  echo -e "  ${YELLOW}Note: AI features need an API key. Edit .env and restart:${NC}"
  echo -e "  ${YELLOW}  ./start.sh stop && ./start.sh run${NC}"

# ── MODE: docker-private ──────────────────────────────────────────────────────
elif [ "$MODE" = "docker-private" ] || [ "$MODE" = "private" ]; then
  check_docker
  ensure_env

  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   Private / Air-Gapped Registry Setup               ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo "  All base images will be pulled from your private registry."
  echo "  Your registry must proxy or cache Docker Hub images:"
  echo ""
  echo "    python:3.11-slim    node:20-alpine    (build deps)"
  echo ""

  REGISTRY_URL=$(ask "Registry URL (e.g. artifactory.corp.com):")
  REGISTRY_URL="${REGISTRY_URL%/}"; REGISTRY_URL="${REGISTRY_URL#https://}"; REGISTRY_URL="${REGISTRY_URL#http://}"

  echo ""
  echo "  Authentication:"
  echo "    1) Username + Password"
  echo "    2) API Key / Token"
  echo "    3) None (open registry)"
  echo ""
  AUTH_TYPE=$(ask "Choose [1/2/3]:")

  case "$AUTH_TYPE" in
    1)
      REG_USER=$(ask "Registry username:")
      REG_PASS=$(ask_pass "Registry password:")
      echo "$REG_PASS" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || error "Login failed."
      ;;
    2)
      REG_TOKEN=$(ask_pass "API Key / Token:")
      REG_USER=$(ask "Username for token auth [token]:")
      REG_USER="${REG_USER:-token}"
      echo "$REG_TOKEN" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || error "Login failed."
      ;;
    3) info "Skipping auth." ;;
    *) error "Invalid choice." ;;
  esac

  echo ""
  USE_CUSTOM=$(ask "Does your registry use a sub-path prefix? e.g. docker-hub/ (y/N):")
  REPO_PREFIX=""
  if [[ "${USE_CUSTOM,,}" == "y" ]]; then
    REPO_PREFIX=$(ask "Sub-path (e.g. docker-hub — leave blank for none):")
    [ -n "$REPO_PREFIX" ] && REPO_PREFIX="${REPO_PREFIX%/}/"
  fi

  REGISTRY_PREFIX="${REGISTRY_URL}/${REPO_PREFIX}"
  echo ""
  info "Registry prefix: ${BOLD}${REGISTRY_PREFIX}${NC}"
  echo ""

  for IMAGE in "python:3.11-slim" "node:20-alpine"; do
    FULL="${REGISTRY_PREFIX}${IMAGE}"
    ATTEMPTS=0
    until docker pull "$FULL"; do
      ATTEMPTS=$((ATTEMPTS+1))
      [ $ATTEMPTS -ge 3 ] && error "Could not pull $FULL. Fix registry config and retry."
      warn "Retrying ($ATTEMPTS/3)..."; sleep 5
    done
    docker tag "${FULL}" "${IMAGE}" 2>/dev/null || true
    success "Pulled ${FULL}"
  done

  get_api_url

  cat > .env.airgap << ENVEOF
REGISTRY_PREFIX=${REGISTRY_PREFIX}
REGISTRY_URL=${REGISTRY_URL}
ENVEOF

  export REGISTRY_PREFIX
  DOCKER_BUILDKIT=1 docker compose -f docker-compose.airgap.yml up --build -d

  echo ""
  success "ElasticGuard is running (air-gapped mode)!"
  divider
  echo -e "  Registry:  ${CYAN}${REGISTRY_URL}${NC}"
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  divider

# ── MODE: local ───────────────────────────────────────────────────────────────
elif [ "$MODE" = "local" ] || [ "$MODE" = "dev" ]; then
  info "Starting in local development mode..."
  command -v python3 &>/dev/null || error "Python 3 not found"
  command -v node    &>/dev/null || error "Node.js not found"

  cd backend
  [ ! -d "venv" ] && python3 -m venv venv && success "Created virtualenv"
  [ -f "venv/Scripts/activate" ] && source venv/Scripts/activate || source venv/bin/activate
  pip install -r requirements.txt -q
  mkdir -p data/chroma knowledge/docs
  [ ! -f ".env" ] && cp ../.env.example .env && warn "Created backend/.env — edit with your API keys"

  info "Starting backend on :8000..."
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  cd ..

  info "Setting up frontend..."
  cd frontend
  [ ! -d "node_modules" ] && npm install
  echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
  info "Starting frontend on :3000..."
  npm run dev &
  FRONTEND_PID=$!
  cd ..

  echo ""
  success "ElasticGuard is running!"
  divider
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Backend:   ${CYAN}http://localhost:8000${NC}"
  divider
  echo "  Press Ctrl+C to stop"
  trap "kill \$BACKEND_PID \$FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
  wait

# ── MODE: ollama ──────────────────────────────────────────────────────────────
elif [ "$MODE" = "ollama" ]; then
  check_docker; ensure_env; get_api_url
  sed -i 's/DEFAULT_AI_PROVIDER=.*/DEFAULT_AI_PROVIDER=ollama/' .env 2>/dev/null || true
  info "Starting with Ollama local LLM..."
  docker compose --profile ollama up --build -d
  echo ""
  warn "Pulling llama3.2 model (~2 GB on first run)..."
  sleep 12
  docker exec elasticguard-ollama ollama pull llama3.2 \
    || warn "Run manually: docker exec elasticguard-ollama ollama pull llama3.2"
  echo ""
  success "ElasticGuard + Ollama running!"
  echo -e "  Frontend:  ${CYAN}http://localhost:3000${NC}"
  echo -e "  Ollama:    ${CYAN}http://localhost:11434${NC}"

# ── MODE: stop ────────────────────────────────────────────────────────────────
elif [ "$MODE" = "stop" ]; then
  info "Stopping all ElasticGuard services..."
  docker compose                              down 2>/dev/null || true
  docker compose -f docker-compose.hub.yml   down 2>/dev/null || true
  docker compose -f docker-compose.airgap.yml down 2>/dev/null || true
  success "All services stopped."

# ── MODE: logs ────────────────────────────────────────────────────────────────
elif [ "$MODE" = "logs" ]; then
  COMPOSE_FILE="docker-compose.yml"
  case "${2:-}" in
    --hub|-h)    COMPOSE_FILE="docker-compose.hub.yml" ;;
    --airgap|-a) COMPOSE_FILE="docker-compose.airgap.yml" ;;
  esac
  info "Tailing logs from ${COMPOSE_FILE}..."
  docker compose -f "$COMPOSE_FILE" logs -f --tail=100

# ── Help ──────────────────────────────────────────────────────────────────────
else
  echo -e "${BOLD}Usage:${NC}  ./start.sh [MODE]"
  echo ""
  echo -e "${BOLD}Modes for users WITH the code:${NC}"
  echo ""
  echo "  docker          Build images from source and run"
  echo "  docker-private  Build from source using a private/air-gapped registry"
  echo "  local           Run backend + frontend directly (no Docker, dev mode)"
  echo "  ollama          Docker + local Llama LLM via Ollama (free, no API key)"
  echo ""
  echo -e "${BOLD}Modes for publishing and distributing:${NC}"
  echo ""
  echo "  build           Build images and push to Docker Hub"
  echo "                  → Prompts for your Docker Hub username and tag"
  echo "                  → Anyone can then run with './start.sh run'"
  echo ""
  echo "  run             Pull pre-built images from Docker Hub and start"
  echo "                  → No code needed — just Docker and a .env file"
  echo "                  → Prompts for Docker Hub username if not set"
  echo ""
  echo -e "${BOLD}Utilities:${NC}"
  echo ""
  echo "  stop            Stop all running containers (all compose files)"
  echo "  logs            Tail logs  (--hub for hub mode, --airgap for airgap)"
  echo ""
  divider
  echo -e "${BOLD}Quick examples:${NC}"
  echo ""
  echo "  # Developer: build and run from source"
  echo "  ./start.sh docker"
  echo ""
  echo "  # Publisher: build and push to Docker Hub"
  echo "  ./start.sh build"
  echo ""
  echo "  # End user: run without any code"
  echo "  DOCKER_HUB_USER=myorg ./start.sh run"
  echo ""
  echo "  # Air-gapped environment:"
  echo "  ./start.sh docker-private"
  echo ""
  divider
fi
