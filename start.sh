#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ElasticGuard — Start Script
#
#  Usage: ./start.sh [MODE]
#
#  Modes (WITH source code):
#    docker          Build Docker images from source and run
#    docker-private  Same, using a private/air-gapped registry
#    local           Run backend + frontend directly on this machine
#    ollama          Docker + local Llama LLM via Ollama
#
#  Modes (local builds, no Docker):
#    build           Build Next.js frontend + Python backend locally
#    run-local       Run the local build produced by 'build'
#
#  Modes (Docker Hub pre-built images, no source code needed):
#    push            Build Docker images and push to Docker Hub
#    run-docker      Pull images from Docker Hub and run with Docker
#
#  Utilities:
#    stop            Stop all running services / containers
#    logs            Tail Docker container logs
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'
R='\033[0;31m'; B='\033[1m';    N='\033[0m'

info()    { echo -e "${C}▶${N} $1"; }
ok()      { echo -e "${G}✓${N} $1"; }
warn()    { echo -e "${Y}⚠${N}  $1"; }
err()     { echo -e "${R}✗${N} $1" >&2; exit 1; }
div()     { echo -e "${C}────────────────────────────────────────────────────${N}"; }
ask()     { printf "${B}%s${N} " "$1" >&2; read -r _v; echo "$_v"; }
askpass() { printf "${B}%s${N} " "$1" >&2; read -rs _v; echo >&2; echo "$_v"; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

MODE="${1:-help}"

echo -e "${C}"
echo "  ┌───────────────────────────────────────────────┐"
echo "  │  ElasticGuard — AI Elasticsearch Diagnostics  │"
echo "  └───────────────────────────────────────────────┘"
echo -e "${N}"

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# ── Shared helpers ────────────────────────────────────────────────────────────
need_docker() {
  command -v docker &>/dev/null || err "Docker not found. Install from https://docker.com"
  docker info &>/dev/null       || err "Docker daemon is not running. Start Docker Desktop."
}

need_python() {
  command -v python3 &>/dev/null || command -v python &>/dev/null \
    || err "Python 3 not found. Install from https://python.org"
}

need_node() {
  command -v node &>/dev/null || err "Node.js not found. Install from https://nodejs.org"
  command -v npm  &>/dev/null || err "npm not found."
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
  info "Pre-pulling base images to avoid build timeouts..."
  for IMG in "python:3.11-slim" "node:20-alpine"; do
    N=0
    until docker pull "$IMG" 2>/dev/null; do
      N=$((N+1)); [ $N -ge 3 ] && { warn "Could not pull $IMG — using cache if available"; break; }
      warn "Retrying $IMG ($N/3)..."; sleep 5
    done
  done
}

browser_url() {
  # NEXT_PUBLIC_API_URL is baked into the JS bundle — must be the URL
  # the browser (not Docker) uses to reach the backend.
  if [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
    export NEXT_PUBLIC_API_URL="http://localhost:8000"
  fi
  info "Browser→Backend URL: ${B}${NEXT_PUBLIC_API_URL}${N}"
  echo -e "  ${Y}Override: NEXT_PUBLIC_API_URL=http://your-ip:8000 ./start.sh ...${N}"
  echo ""
}

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: docker  — build from source + run in Docker
# ═════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "docker" ] || [ "$MODE" = "d" ]; then
  need_docker; ensure_env; browser_url; pull_base_images

  info "Building and starting ElasticGuard..."
  docker compose up --build -d

  echo ""; ok "ElasticGuard is running!"; div
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Backend:   ${C}http://localhost:8000${N}"
  echo -e "  API Docs:  ${C}http://localhost:8000/docs${N}"; div
  echo -e "  Logs: ${Y}./start.sh logs${N}    Stop: ${Y}./start.sh stop${N}"

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: build  — compile frontend (Next.js) + backend (Python) locally
#                 Produces: frontend/.next/  backend/venv/
#                 Run with: ./start.sh run-local
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "build" ]; then
  need_python; need_node
  echo ""
  echo -e "${B}Local Build${N} — compiles frontend and backend without Docker."
  echo "Run the result with:  ${Y}./start.sh run-local${N}"
  div; echo ""

  # ── Backend: create venv + install deps ───────────────────────────────────
  info "Building backend (Python)..."
  cd backend

  # Find python executable
  PYTHON=""
  for P in python3 python python3.11 python3.12 python3.10; do
    command -v "$P" &>/dev/null && { PYTHON="$P"; break; }
  done
  [ -z "$PYTHON" ] && err "Python 3.10+ not found."

  PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  info "Using $PYTHON ($PY_VER)"

  if [ ! -d "venv" ]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv venv
    ok "Virtual environment created"
  else
    ok "Virtual environment already exists"
  fi

  # Activate venv (Git Bash / WSL / Linux / Mac)
  if [ -f "venv/Scripts/activate" ]; then
    # shellcheck source=/dev/null
    source venv/Scripts/activate
  else
    # shellcheck source=/dev/null
    source venv/bin/activate
  fi

  info "Installing Python dependencies..."
  pip install --upgrade pip -q
  pip install -r requirements.txt -q
  ok "Python dependencies installed"

  mkdir -p data/chroma data knowledge/docs

  if [ ! -f ".env" ]; then
    cp ../.env.example .env
    warn "Created backend/.env — edit with your API keys"
  fi

  cd ..

  # ── Frontend: npm install + next build ────────────────────────────────────
  info "Building frontend (Next.js)..."
  cd frontend

  if [ ! -d "node_modules" ]; then
    info "Installing Node.js dependencies..."
    npm install
    ok "Node.js dependencies installed"
  else
    ok "node_modules already present"
  fi

  # Write .env.local for the build
  echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

  info "Running Next.js production build (npm run build)..."
  npm run build
  ok "Next.js build complete (.next/)"

  cd ..

  echo ""
  ok "Build complete!"; div
  echo -e "  Backend:   venv + dependencies ready"
  echo -e "  Frontend:  ${C}.next/${N} production build ready"; div
  echo -e "  Now run:   ${Y}./start.sh run-local${N}"

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: run-local  — serve the local build (no Docker, no dev server)
#                     Requires: ./start.sh build has been run first
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "run-local" ]; then
  need_python; need_node

  echo ""
  echo -e "${B}Run Local Build${N} — serves the compiled frontend + backend."
  echo "Requires ${Y}./start.sh build${N} to have been run first."
  div; echo ""

  # ── Verify build artefacts exist ─────────────────────────────────────────
  [ -d "backend/venv" ] || err "backend/venv not found. Run './start.sh build' first."
  [ -d "frontend/.next" ] || err "frontend/.next not found. Run './start.sh build' first."

  # ── Activate backend venv ─────────────────────────────────────────────────
  cd backend
  if [ -f "venv/Scripts/activate" ]; then
    # shellcheck source=/dev/null
    source venv/Scripts/activate
  else
    # shellcheck source=/dev/null
    source venv/bin/activate
  fi

  mkdir -p data/chroma data knowledge/docs

  if [ ! -f ".env" ]; then
    cp ../.env.example .env
    warn "Created backend/.env — edit with your API keys"
  fi

  # Start backend (production mode, no --reload)
  info "Starting backend on :8000..."
  uvicorn main:app --host 0.0.0.0 --port 8000 &
  BACKEND_PID=$!
  cd ..

  # ── Start Next.js in production mode ─────────────────────────────────────
  cd frontend

  # next start serves the .next build directly (no re-compilation)
  info "Starting frontend on :3000..."
  npm run start -- --port 3000 &
  FRONTEND_PID=$!
  cd ..

  # ── Wait for backend to be ready ─────────────────────────────────────────
  info "Waiting for backend to be ready..."
  for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      ok "Backend is ready"; break
    fi
    sleep 1
  done

  echo ""; ok "ElasticGuard is running (local build)!"; div
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Backend:   ${C}http://localhost:8000${N}"
  echo -e "  API Docs:  ${C}http://localhost:8000/docs${N}"; div
  echo "  Press Ctrl+C to stop all services"

  trap "kill \$BACKEND_PID \$FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
  wait

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: push  — build Docker images and push to Docker Hub
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "push" ]; then
  need_docker

  echo ""
  echo -e "${B}Push to Docker Hub${N}"
  echo "Builds Docker images from source and pushes to your Docker Hub account."
  echo "Others can then run them with:  ${Y}./start.sh run-docker${N}"
  div; echo ""

  # Collect info — print to stderr so $() captures work correctly
  printf "${B}Docker Hub username:${N} " >&2; read -r DOCKER_HUB_USER
  printf "${B}Image tag [latest]:${N} "  >&2; read -r INPUT_TAG
  TAG="${INPUT_TAG:-latest}"
  printf "${B}Default backend URL [http://localhost:8000]:${N} " >&2; read -r INPUT_URL
  BUILD_API_URL="${INPUT_URL:-http://localhost:8000}"

  BACKEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-backend:${TAG}"
  FRONTEND_IMAGE="${DOCKER_HUB_USER}/elasticguard-frontend:${TAG}"

  echo ""
  echo "Will build and push:"
  echo -e "  ${C}${BACKEND_IMAGE}${N}"
  echo -e "  ${C}${FRONTEND_IMAGE}${N}"
  echo ""
  printf "${B}Proceed? (y/N):${N} " >&2; read -r CONFIRM
  [[ "${CONFIRM,,}" != "y" ]] && { info "Cancelled."; exit 0; }

  # Login — interactive, so we don't use $() here
  echo ""
  info "Logging in to Docker Hub as ${DOCKER_HUB_USER}..."
  docker login --username "$DOCKER_HUB_USER" \
    || err "Docker Hub login failed."

  pull_base_images

  echo ""
  info "Building backend: ${BACKEND_IMAGE}"
  docker build \
    --platform linux/amd64 \
    --tag "$BACKEND_IMAGE" \
    ./backend

  echo ""
  info "Building frontend: ${FRONTEND_IMAGE}"
  docker build \
    --platform linux/amd64 \
    --tag "$FRONTEND_IMAGE" \
    --build-arg "NEXT_PUBLIC_API_URL=${BUILD_API_URL}" \
    ./frontend

  if [ "$TAG" != "latest" ]; then
    docker tag "$BACKEND_IMAGE"  "${DOCKER_HUB_USER}/elasticguard-backend:latest"
    docker tag "$FRONTEND_IMAGE" "${DOCKER_HUB_USER}/elasticguard-frontend:latest"
  fi

  echo ""
  info "Pushing images..."
  docker push "$BACKEND_IMAGE"
  docker push "$FRONTEND_IMAGE"
  if [ "$TAG" != "latest" ]; then
    docker push "${DOCKER_HUB_USER}/elasticguard-backend:latest"
    docker push "${DOCKER_HUB_USER}/elasticguard-frontend:latest"
  fi

  # Save for run-docker
  printf "DOCKER_HUB_USER=%s\nTAG=%s\n" "$DOCKER_HUB_USER" "$TAG" > .env.hub

  echo ""; ok "Pushed to Docker Hub!"; div
  echo -e "  ${C}hub.docker.com/r/${DOCKER_HUB_USER}/elasticguard-backend${N}"
  echo -e "  ${C}hub.docker.com/r/${DOCKER_HUB_USER}/elasticguard-frontend${N}"; div
  echo ""
  echo "Others can now run without any code:"
  echo -e "  ${Y}DOCKER_HUB_USER=${DOCKER_HUB_USER} ./start.sh run-docker${N}"

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: run-docker  — pull pre-built images from Docker Hub and run
#                      No source code required
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "run-docker" ]; then
  need_docker

  echo ""
  echo -e "${B}Run from Docker Hub${N} — no source code needed."
  div; echo ""

  # Resolve Docker Hub user
  DOCKER_HUB_USER="${DOCKER_HUB_USER:-}"
  if [ -z "$DOCKER_HUB_USER" ] && [ -f ".env.hub" ]; then
    # shellcheck source=/dev/null
    source .env.hub
    info "Using saved config from .env.hub (user: ${DOCKER_HUB_USER}, tag: ${TAG:-latest})"
  fi
  if [ -z "$DOCKER_HUB_USER" ]; then
    printf "${B}Docker Hub username where images are published:${N} " >&2
    read -r DOCKER_HUB_USER
  fi
  TAG="${TAG:-latest}"

  ensure_env

  if [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
    export NEXT_PUBLIC_API_URL="http://localhost:8000"
  fi

  # Patch hub compose file with actual username
  if [ -f "docker-compose.hub.yml" ]; then
    sed -i.bak "s|yourdockerhubuser|${DOCKER_HUB_USER}|g" docker-compose.hub.yml 2>/dev/null \
      || sed "s|yourdockerhubuser|${DOCKER_HUB_USER}|g" docker-compose.hub.yml > docker-compose.hub.tmp \
         && mv docker-compose.hub.tmp docker-compose.hub.yml
    rm -f docker-compose.hub.yml.bak
  fi

  info "Pulling ${DOCKER_HUB_USER}/elasticguard-backend:${TAG}..."
  docker pull "${DOCKER_HUB_USER}/elasticguard-backend:${TAG}" \
    || err "Pull failed. Is the image public on hub.docker.com/u/${DOCKER_HUB_USER}?"

  info "Pulling ${DOCKER_HUB_USER}/elasticguard-frontend:${TAG}..."
  docker pull "${DOCKER_HUB_USER}/elasticguard-frontend:${TAG}" \
    || err "Pull failed."

  DOCKER_HUB_USER="$DOCKER_HUB_USER" TAG="$TAG" \
    docker compose -f docker-compose.hub.yml up -d

  echo ""; ok "ElasticGuard is running!"; div
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Backend:   ${C}http://localhost:8000${N}"
  echo -e "  Images:    ${C}hub.docker.com/u/${DOCKER_HUB_USER}${N}"; div
  echo -e "  Logs: ${Y}./start.sh logs --hub${N}    Stop: ${Y}./start.sh stop${N}"

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: local  — dev mode, hot reload (requires code + Python + Node)
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "local" ] || [ "$MODE" = "dev" ]; then
  need_python; need_node
  info "Starting local dev mode (hot reload)..."

  cd backend
  if [ -f "venv/Scripts/activate" ]; then source venv/Scripts/activate
  elif [ -f "venv/bin/activate" ];    then source venv/bin/activate
  else
    info "Creating virtual environment..."
    python3 -m venv venv && source venv/bin/activate
  fi

  pip install -r requirements.txt -q
  mkdir -p data/chroma data knowledge/docs
  [ ! -f ".env" ] && cp ../.env.example .env && warn "Created backend/.env"

  info "Starting backend on :8000 (with hot reload)..."
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  cd ..

  cd frontend
  [ ! -d "node_modules" ] && npm install
  echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
  info "Starting frontend on :3000 (dev server)..."
  npm run dev &
  FRONTEND_PID=$!
  cd ..

  echo ""; ok "ElasticGuard dev server running!"; div
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Backend:   ${C}http://localhost:8000${N}"; div
  echo "  Press Ctrl+C to stop"
  trap "kill \$BACKEND_PID \$FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
  wait

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: docker-private  — build from private/air-gapped registry
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "docker-private" ] || [ "$MODE" = "private" ]; then
  need_docker; ensure_env

  echo ""
  echo -e "${B}Private / Air-Gapped Registry${N}"
  div; echo ""
  echo "All base images will be pulled from your private registry."
  echo "The registry must proxy or cache these Docker Hub images:"
  echo "  python:3.11-slim    node:20-alpine"
  echo ""

  printf "${B}Registry URL (e.g. artifactory.corp.com):${N} " >&2; read -r REGISTRY_URL
  REGISTRY_URL="${REGISTRY_URL%/}"; REGISTRY_URL="${REGISTRY_URL#https://}"; REGISTRY_URL="${REGISTRY_URL#http://}"

  echo ""
  echo "Auth:  1) Username+Password  2) API Key/Token  3) None"
  printf "${B}Choose [1/2/3]:${N} " >&2; read -r AUTH_TYPE

  case "$AUTH_TYPE" in
    1)
      printf "${B}Username:${N} " >&2; read -r REG_USER
      printf "${B}Password:${N} " >&2; read -rs REG_PASS; echo >&2
      echo "$REG_PASS" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || err "Login failed."
      ;;
    2)
      printf "${B}API Key/Token:${N} " >&2; read -rs REG_TOKEN; echo >&2
      printf "${B}Username [token]:${N} " >&2; read -r REG_USER; REG_USER="${REG_USER:-token}"
      echo "$REG_TOKEN" | docker login "$REGISTRY_URL" -u "$REG_USER" --password-stdin \
        || err "Login failed."
      ;;
    3) info "Skipping auth." ;;
    *) err "Invalid choice." ;;
  esac

  echo ""
  printf "${B}Sub-path prefix? e.g. docker-hub/ (leave blank for none):${N} " >&2
  read -r REPO_PREFIX
  [ -n "$REPO_PREFIX" ] && REPO_PREFIX="${REPO_PREFIX%/}/"
  REGISTRY_PREFIX="${REGISTRY_URL}/${REPO_PREFIX}"
  info "Registry prefix: ${B}${REGISTRY_PREFIX}${N}"; echo ""

  for IMG in "python:3.11-slim" "node:20-alpine"; do
    FULL="${REGISTRY_PREFIX}${IMG}"; N=0
    until docker pull "$FULL"; do
      N=$((N+1)); [ $N -ge 3 ] && err "Could not pull $FULL"
      warn "Retrying ($N/3)..."; sleep 5
    done
    docker tag "${FULL}" "${IMG}" 2>/dev/null || true
    ok "Pulled ${FULL}"
  done

  browser_url
  printf "REGISTRY_PREFIX=%s\nREGISTRY_URL=%s\n" "$REGISTRY_PREFIX" "$REGISTRY_URL" > .env.airgap
  export REGISTRY_PREFIX
  docker compose -f docker-compose.airgap.yml up --build -d

  echo ""; ok "ElasticGuard running (air-gapped)!"; div
  echo -e "  Registry:  ${C}${REGISTRY_URL}${N}"
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Backend:   ${C}http://localhost:8000${N}"; div

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: ollama
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "ollama" ]; then
  need_docker; ensure_env; browser_url
  sed -i 's/DEFAULT_AI_PROVIDER=.*/DEFAULT_AI_PROVIDER=ollama/' .env 2>/dev/null || true
  info "Starting with Ollama local LLM..."
  docker compose --profile ollama up --build -d
  warn "Pulling llama3.2 (~2 GB, first run only)..."; sleep 12
  docker exec elasticguard-ollama ollama pull llama3.2 \
    || warn "Run manually: docker exec elasticguard-ollama ollama pull llama3.2"
  echo ""; ok "ElasticGuard + Ollama running!"
  echo -e "  Frontend:  ${C}http://localhost:3000${N}"
  echo -e "  Ollama:    ${C}http://localhost:11434${N}"

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: stop
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "stop" ]; then
  info "Stopping all ElasticGuard services..."
  docker compose                               down 2>/dev/null || true
  docker compose -f docker-compose.hub.yml    down 2>/dev/null || true
  docker compose -f docker-compose.airgap.yml down 2>/dev/null || true
  # Kill any local uvicorn/node if running
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "next.*3000"       2>/dev/null || true
  ok "All services stopped."

# ═════════════════════════════════════════════════════════════════════════════
#  MODE: logs
# ═════════════════════════════════════════════════════════════════════════════
elif [ "$MODE" = "logs" ]; then
  case "${2:-}" in
    --hub|-h)    CF="docker-compose.hub.yml" ;;
    --airgap|-a) CF="docker-compose.airgap.yml" ;;
    *)           CF="docker-compose.yml" ;;
  esac
  info "Tailing logs from ${CF}..."
  docker compose -f "$CF" logs -f --tail=100

# ═════════════════════════════════════════════════════════════════════════════
#  Help
# ═════════════════════════════════════════════════════════════════════════════
else
  echo -e "${B}Usage:${N}  ./start.sh [MODE]"; echo ""
  div
  echo -e "${B}With source code (requires Python + Node.js or Docker):${N}"; echo ""
  echo "  docker          Build Docker images from source and run"
  echo "  local           Run dev server with hot reload (no Docker)"
  echo "  ollama          Docker + local Llama LLM (no AI key needed)"
  echo "  docker-private  Build from a private/air-gapped Docker registry"
  echo ""
  div
  echo -e "${B}Local builds (no Docker — distributable binary-like output):${N}"; echo ""
  echo "  build           Compile frontend (Next.js .next/) + install"
  echo "                  backend deps into venv/. No Docker needed."
  echo "  run-local       Serve the compiled build from 'build'."
  echo "                  Production mode, no hot reload."
  echo ""
  div
  echo -e "${B}Docker Hub (no source code required):${N}"; echo ""
  echo "  push            Build Docker images and push to Docker Hub"
  echo "  run-docker      Pull images from Docker Hub and run"
  echo ""
  div
  echo -e "${B}Utilities:${N}"; echo ""
  echo "  stop            Stop everything (Docker + local processes)"
  echo "  logs            Tail logs (--hub or --airgap for other compose files)"
  echo ""
  div
  echo -e "${B}Typical flows:${N}"; echo ""
  echo -e "  Dev:        ${Y}./start.sh local${N}"
  echo -e "  Production: ${Y}./start.sh docker${N}"
  echo -e "  No Docker:  ${Y}./start.sh build${N}  then  ${Y}./start.sh run-local${N}"
  echo -e "  Share:      ${Y}./start.sh push${N}   then  ${Y}DOCKER_HUB_USER=x ./start.sh run-docker${N}"
  div
fi
