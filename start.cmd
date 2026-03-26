@echo off
setlocal EnableDelayedExpansion
:: ═══════════════════════════════════════════════════════════════════════════════
::  ElasticGuard — Windows Start Script
::  Usage: start.cmd [MODE]
::
::  Modes (WITH source code):
::    docker          Build Docker images from source and run
::    docker-private  Same, using a private/air-gapped registry
::    local           Run backend + frontend directly (dev, hot reload)
::    ollama          Docker + local Llama LLM via Ollama
::
::  Modes (local builds, no Docker):
::    build           Build Next.js frontend + install Python backend deps
::    run-local       Run the local build produced by 'build'
::
::  Modes (Docker Hub pre-built images, no source code needed):
::    push            Build Docker images and push to Docker Hub
::    run-docker      Pull images from Docker Hub and run
::
::  Utilities:
::    stop            Stop all running services / containers
::    logs            Tail Docker container logs
:: ═══════════════════════════════════════════════════════════════════════════════

:: ── Change to script directory ───────────────────────────────────────────────
cd /d "%~dp0"

:: ── Banner ───────────────────────────────────────────────────────────────────
echo.
echo   +---------------------------------------------------+
echo   ^|   ElasticGuard -- AI Elasticsearch Diagnostics   ^|
echo   +---------------------------------------------------+
echo.

:: ── Mode argument ────────────────────────────────────────────────────────────
set "MODE=%~1"
if "%MODE%"=="" set "MODE=help"

:: ── Enable Docker BuildKit ───────────────────────────────────────────────────
set "DOCKER_BUILDKIT=1"
set "COMPOSE_DOCKER_CLI_BUILD=1"

:: ── Route to mode ────────────────────────────────────────────────────────────
if /i "%MODE%"=="docker"         goto :mode_docker
if /i "%MODE%"=="d"              goto :mode_docker
if /i "%MODE%"=="build"          goto :mode_build
if /i "%MODE%"=="run-local"      goto :mode_run_local
if /i "%MODE%"=="push"           goto :mode_push
if /i "%MODE%"=="run-docker"     goto :mode_run_docker
if /i "%MODE%"=="local"          goto :mode_local
if /i "%MODE%"=="dev"            goto :mode_local
if /i "%MODE%"=="docker-private" goto :mode_docker_private
if /i "%MODE%"=="private"        goto :mode_docker_private
if /i "%MODE%"=="ollama"         goto :mode_ollama
if /i "%MODE%"=="stop"           goto :mode_stop
if /i "%MODE%"=="logs"           goto :mode_logs
goto :mode_help


:: ═════════════════════════════════════════════════════════════════════════════
:mode_docker
:: Build from source + run in Docker
:: ═════════════════════════════════════════════════════════════════════════════
call :need_docker
call :ensure_env
call :browser_url
call :pull_base_images

echo [INFO] Building and starting ElasticGuard
docker compose up --build -d
if errorlevel 1 ( call :err "docker compose failed" & goto :eof )

echo.
call :ok "ElasticGuard is running!"
call :div
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
call :div
echo   Logs:  start.cmd logs      Stop:  start.cmd stop
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_build
:: Compile Next.js frontend + install Python backend deps locally.
:: No Docker needed. Run with:  start.cmd run-local
:: ═════════════════════════════════════════════════════════════════════════════
call :need_python
call :need_node
echo.
echo [BUILD] Local Build -- compiles frontend and backend without Docker.
echo         Run the result with:  start.cmd run-local
call :div
echo.

:: ── Backend: venv + pip install ──────────────────────────────────────────────
echo [INFO] Building backend (Python)
cd backend

:: Find Python
set "PYTHON="
for %%P in (python python3 py) do (
    if "!PYTHON!"=="" (
        where %%P >nul 2>&1 && set "PYTHON=%%P"
    )
)
if "!PYTHON!"=="" ( call :err "Python not found. Install from https://python.org" & goto :eof )

for /f "tokens=*" %%V in ('!PYTHON! -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%V"
echo [INFO] Using !PYTHON! (!PY_VER!)

if not exist venv (
    echo [INFO] Creating virtual environment
    !PYTHON! -m venv venv
    if errorlevel 1 ( call :err "Failed to create venv" & goto :eof )
    call :ok "Virtual environment created"
) else (
    call :ok "Virtual environment already exists"
)

echo [INFO] Activating virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 ( call :err "Failed to activate venv" & goto :eof )

echo [INFO] Installing Python dependencies
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt
if errorlevel 1 ( call :err "pip install failed" & goto :eof )
call :ok "Python dependencies installed"

if not exist data mkdir data
if not exist data\chroma mkdir data\chroma
if not exist knowledge\docs mkdir knowledge\docs

if not exist .env (
    copy ..\\.env.example .env >nul
    echo [WARN] Created backend\.env -- edit with your API keys
)

cd ..

:: ── Frontend: npm install + next build ───────────────────────────────────────
echo.
echo [INFO] Building frontend (Next.js)
cd frontend

if not exist node_modules (
    echo [INFO] Installing Node.js dependencies
    npm install
    if errorlevel 1 ( call :err "npm install failed" & goto :eof )
    call :ok "Node.js dependencies installed"
) else (
    call :ok "node_modules already present"
)

echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local

echo [INFO] Running Next.js production build
npm run build
if errorlevel 1 ( call :err "npm run build failed" & goto :eof )
call :ok "Next.js build complete (.next\)"

cd ..

echo.
call :ok "Build complete!"
call :div
echo   Backend:   venv\ + dependencies ready
echo   Frontend:  .next\ production build ready
call :div
echo   Now run:   start.cmd run-local
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_run_local
:: Serve the compiled local build. Requires:  start.cmd build
:: ═════════════════════════════════════════════════════════════════════════════
call :need_python
call :need_node
echo.
echo [RUN-LOCAL] Serving compiled frontend + backend (no Docker, no hot reload).
echo            Requires:  start.cmd build  to have been run first.
call :div
echo.

if not exist backend\venv (
    call :err "backend\venv not found. Run 'start.cmd build' first."
    goto :eof
)
if not exist frontend\.next (
    call :err "frontend\.next not found. Run 'start.cmd build' first."
    goto :eof
)

:: ── Start backend ────────────────────────────────────────────────────────────
cd backend
call venv\Scripts\activate.bat

if not exist data mkdir data
if not exist data\chroma mkdir data\chroma
if not exist knowledge\docs mkdir knowledge\docs

if not exist .env (
    copy ..\\.env.example .env >nul
    echo [WARN] Created backend\.env -- edit with your API keys
)

echo [INFO] Starting backend on :8000
start "ElasticGuard Backend" /b cmd /c "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8000 > ..\logs\backend.log 2>&1"

cd ..

:: ── Start frontend ────────────────────────────────────────────────────────────
cd frontend
echo [INFO] Starting frontend on :3000
start "ElasticGuard Frontend" /b cmd /c "npm run start -- --port 3000 > ..\logs\frontend.log 2>&1"
cd ..

:: ── Wait for backend ──────────────────────────────────────────────────────────
if not exist logs mkdir logs
echo [INFO] Waiting for backend to be ready
set "READY=0"
for /l %%i in (1,1,30) do (
    if "!READY!"=="0" (
        curl -sf http://localhost:8000/health >nul 2>&1 && set "READY=1"
        if "!READY!"=="0" ( timeout /t 1 /nobreak >nul )
    )
)
if "!READY!"=="1" (
    call :ok "Backend is ready"
) else (
    echo [WARN] Backend may still be starting -- check logs\backend.log
)

echo.
call :ok "ElasticGuard is running (local build)!"
call :div
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
call :div
echo   Logs:     logs\backend.log  /  logs\frontend.log
echo   To stop:  start.cmd stop
echo.
echo   [Press any key to exit this window -- services keep running]
pause >nul
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_push
:: Build Docker images and push to Docker Hub
:: ═════════════════════════════════════════════════════════════════════════════
call :need_docker
echo.
echo [PUSH] Build and Push to Docker Hub
echo        Builds Docker images from source and pushes them.
echo        Others can run them with:  start.cmd run-docker
call :div
echo.

set /p "DOCKER_HUB_USER=Docker Hub username: "
if "!DOCKER_HUB_USER!"=="" ( call :err "Username cannot be empty" & goto :eof )

set "TAG=latest"
set /p "INPUT_TAG=Image tag [latest]: "
if not "!INPUT_TAG!"=="" set "TAG=!INPUT_TAG!"

set "BUILD_API_URL=http://localhost:8000"
echo.
echo The frontend image needs a default backend URL baked in.
echo   For localhost use:  http://localhost:8000
echo   For a server:       http://your-server-ip:8000
echo.
set /p "INPUT_URL=Default backend URL [http://localhost:8000]: "
if not "!INPUT_URL!"=="" set "BUILD_API_URL=!INPUT_URL!"

set "BACKEND_IMAGE=!DOCKER_HUB_USER!/elasticguard-backend:!TAG!"
set "FRONTEND_IMAGE=!DOCKER_HUB_USER!/elasticguard-frontend:!TAG!"

echo.
echo Will build and push:
echo   !BACKEND_IMAGE!
echo   !FRONTEND_IMAGE!
echo.
set /p "CONFIRM=Proceed? (y/N): "
if /i not "!CONFIRM!"=="y" ( echo Cancelled. & goto :eof )

echo.
echo [INFO] Logging in to Docker Hub as !DOCKER_HUB_USER!
docker login --username "!DOCKER_HUB_USER!"
if errorlevel 1 ( call :err "Docker Hub login failed" & goto :eof )

call :pull_base_images

echo.
echo [INFO] Building backend image: !BACKEND_IMAGE!
docker build --platform linux/amd64 --tag "!BACKEND_IMAGE!" ./backend
if errorlevel 1 ( call :err "Backend build failed" & goto :eof )

echo.
echo [INFO] Building frontend image: !FRONTEND_IMAGE!
docker build --platform linux/amd64 --tag "!FRONTEND_IMAGE!" --build-arg "NEXT_PUBLIC_API_URL=!BUILD_API_URL!" ./frontend
if errorlevel 1 ( call :err "Frontend build failed" & goto :eof )

if not "!TAG!"=="latest" (
    docker tag "!BACKEND_IMAGE!"  "!DOCKER_HUB_USER!/elasticguard-backend:latest"
    docker tag "!FRONTEND_IMAGE!" "!DOCKER_HUB_USER!/elasticguard-frontend:latest"
)

echo.
echo [INFO] Pushing images to Docker Hub
docker push "!BACKEND_IMAGE!"
docker push "!FRONTEND_IMAGE!"
if not "!TAG!"=="latest" (
    docker push "!DOCKER_HUB_USER!/elasticguard-backend:latest"
    docker push "!DOCKER_HUB_USER!/elasticguard-frontend:latest"
)

:: Save for run-docker
(
    echo DOCKER_HUB_USER=!DOCKER_HUB_USER!
    echo TAG=!TAG!
) > .env.hub

echo.
call :ok "Pushed to Docker Hub!"
call :div
echo   hub.docker.com/r/!DOCKER_HUB_USER!/elasticguard-backend
echo   hub.docker.com/r/!DOCKER_HUB_USER!/elasticguard-frontend
call :div
echo   Others can run:  start.cmd run-docker
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_run_docker
:: Pull pre-built images from Docker Hub and run. No source code needed.
:: ═════════════════════════════════════════════════════════════════════════════
call :need_docker
echo.
echo [RUN-DOCKER] Pull from Docker Hub and run. No source code needed.
call :div
echo.

set "DOCKER_HUB_USER="
set "TAG=latest"

:: Load from .env.hub if exists
if exist .env.hub (
    for /f "tokens=1,2 delims==" %%A in (.env.hub) do (
        if "%%A"=="DOCKER_HUB_USER" set "DOCKER_HUB_USER=%%B"
        if "%%A"=="TAG" set "TAG=%%B"
    )
    if not "!DOCKER_HUB_USER!"=="" (
        echo [INFO] Using saved config: user=!DOCKER_HUB_USER! tag=!TAG!
    )
)

if "!DOCKER_HUB_USER!"=="" (
    set /p "DOCKER_HUB_USER=Docker Hub username where images are published: "
    if "!DOCKER_HUB_USER!"=="" ( call :err "Username cannot be empty" & goto :eof )
)

call :ensure_env

if not defined NEXT_PUBLIC_API_URL set "NEXT_PUBLIC_API_URL=http://localhost:8000"

:: Patch hub compose file with real username
if exist docker-compose.hub.yml (
    powershell -Command "(Get-Content docker-compose.hub.yml) -replace 'yourdockerhubuser', '!DOCKER_HUB_USER!' | Set-Content docker-compose.hub.yml" 2>nul
)

echo [INFO] Pulling !DOCKER_HUB_USER!/elasticguard-backend:!TAG!
docker pull "!DOCKER_HUB_USER!/elasticguard-backend:!TAG!"
if errorlevel 1 ( call :err "Pull failed. Is the image public on Docker Hub?" & goto :eof )

echo [INFO] Pulling !DOCKER_HUB_USER!/elasticguard-frontend:!TAG!
docker pull "!DOCKER_HUB_USER!/elasticguard-frontend:!TAG!"
if errorlevel 1 ( call :err "Frontend pull failed" & goto :eof )

set "DOCKER_HUB_USER=!DOCKER_HUB_USER!" && set "TAG=!TAG!" && docker compose -f docker-compose.hub.yml up -d
if errorlevel 1 ( call :err "docker compose up failed" & goto :eof )

echo.
call :ok "ElasticGuard is running!"
call :div
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   Images:    hub.docker.com/u/!DOCKER_HUB_USER!
call :div
echo   Logs:  start.cmd logs --hub      Stop:  start.cmd stop
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_local
:: Dev mode with hot reload. Requires Python + Node.js.
:: ═════════════════════════════════════════════════════════════════════════════
call :need_python
call :need_node
echo [INFO] Starting local dev mode (hot reload)

cd backend

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo [INFO] Creating virtual environment
    python -m venv venv
    call venv\Scripts\activate.bat
)

python -m pip install -r requirements.txt -q
if not exist data mkdir data
if not exist data\chroma mkdir data\chroma
if not exist knowledge\docs mkdir knowledge\docs
if not exist .env ( copy ..\\.env.example .env >nul & echo [WARN] Created backend\.env )

echo [INFO] Starting backend on :8000 (hot reload)
start "ElasticGuard Backend" cmd /k "call venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
cd ..

cd frontend
if not exist node_modules ( npm install )
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
echo [INFO] Starting frontend on :3000 (dev server)
start "ElasticGuard Frontend" cmd /k "npm run dev"
cd ..

echo.
call :ok "ElasticGuard dev server starting!"
call :div
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
call :div
echo   Two new windows opened -- close them to stop.
echo   Or run:  start.cmd stop
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_docker_private
:: Build from source using a private/air-gapped registry
:: ═════════════════════════════════════════════════════════════════════════════
call :need_docker
call :ensure_env
echo.
echo [PRIVATE] Private / Air-Gapped Registry
call :div
echo.
echo All base images will be pulled from your private registry.
echo The registry must proxy or cache:  python:3.11-slim  node:20-alpine
echo.

set /p "REGISTRY_URL=Registry URL (e.g. artifactory.corp.com): "
:: Strip trailing slash and protocol
set "REGISTRY_URL=!REGISTRY_URL:/=!"
for /f "tokens=2 delims=/" %%A in ("!REGISTRY_URL!") do set "REGISTRY_URL=%%A"
:: Simple strip of https: or http: prefix
set "REGISTRY_URL=!REGISTRY_URL:https:=!"
set "REGISTRY_URL=!REGISTRY_URL:http:=!"
set "REGISTRY_URL=!REGISTRY_URL:~0,-0!"

echo.
echo Auth:  1) Username+Password   2) API Key/Token   3) None
set /p "AUTH_TYPE=Choose [1/2/3]: "

if "!AUTH_TYPE!"=="1" (
    set /p "REG_USER=Username: "
    set /p "REG_PASS=Password: "
    echo !REG_PASS! | docker login "!REGISTRY_URL!" -u "!REG_USER!" --password-stdin
    if errorlevel 1 ( call :err "Login failed" & goto :eof )
) else if "!AUTH_TYPE!"=="2" (
    set /p "REG_TOKEN=API Key/Token: "
    set "REG_USER=token"
    set /p "REG_USER_INPUT=Username [token]: "
    if not "!REG_USER_INPUT!"=="" set "REG_USER=!REG_USER_INPUT!"
    echo !REG_TOKEN! | docker login "!REGISTRY_URL!" -u "!REG_USER!" --password-stdin
    if errorlevel 1 ( call :err "Login failed" & goto :eof )
) else (
    echo [INFO] Skipping authentication.
)

echo.
set "REPO_PREFIX="
set /p "REPO_PREFIX_INPUT=Sub-path prefix (e.g. docker-hub -- leave blank for none): "
if not "!REPO_PREFIX_INPUT!"=="" set "REPO_PREFIX=!REPO_PREFIX_INPUT!/"

set "REGISTRY_PREFIX=!REGISTRY_URL!/!REPO_PREFIX!"
echo [INFO] Registry prefix: !REGISTRY_PREFIX!
echo.

for %%I in ("python:3.11-slim" "node:20-alpine") do (
    set "FULL=!REGISTRY_PREFIX!%%~I"
    set "ATTEMPT=0"
    :retry_private_%%I
    docker pull "!FULL!"
    if errorlevel 1 (
        set /a ATTEMPT+=1
        if !ATTEMPT! geq 3 ( call :err "Could not pull !FULL!" & goto :eof )
        echo [WARN] Retrying !ATTEMPT!/3
        timeout /t 5 /nobreak >nul
        goto :retry_private_%%I
    )
    docker tag "!FULL!" "%%~I" 2>nul
    call :ok "Pulled !FULL!"
)

if not defined NEXT_PUBLIC_API_URL set "NEXT_PUBLIC_API_URL=http://localhost:8000"

(
    echo REGISTRY_PREFIX=!REGISTRY_PREFIX!
    echo REGISTRY_URL=!REGISTRY_URL!
) > .env.airgap

set "REGISTRY_PREFIX=!REGISTRY_PREFIX!"
docker compose -f docker-compose.airgap.yml up --build -d
if errorlevel 1 ( call :err "docker compose failed" & goto :eof )

echo.
call :ok "ElasticGuard running (air-gapped)!"
call :div
echo   Registry:  !REGISTRY_URL!
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
call :div
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_ollama
:: ═════════════════════════════════════════════════════════════════════════════
call :need_docker
call :ensure_env
if not defined NEXT_PUBLIC_API_URL set "NEXT_PUBLIC_API_URL=http://localhost:8000"

powershell -Command "(Get-Content .env) -replace 'DEFAULT_AI_PROVIDER=.*', 'DEFAULT_AI_PROVIDER=ollama' | Set-Content .env" 2>nul

echo [INFO] Starting with Ollama local LLM
docker compose --profile ollama up --build -d
if errorlevel 1 ( call :err "docker compose failed" & goto :eof )

echo [WARN] Pulling llama3.2 (~2 GB on first run)
timeout /t 12 /nobreak >nul
docker exec elasticguard-ollama ollama pull llama3.2
if errorlevel 1 echo [WARN] Pull manually: docker exec elasticguard-ollama ollama pull llama3.2

echo.
call :ok "ElasticGuard + Ollama running!"
echo   Frontend:  http://localhost:3000
echo   Ollama:    http://localhost:11434
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_stop
:: ═════════════════════════════════════════════════════════════════════════════
echo [INFO] Stopping all ElasticGuard services
docker compose down 2>nul
docker compose -f docker-compose.hub.yml down 2>nul
docker compose -f docker-compose.airgap.yml down 2>nul
:: Kill local processes by window title
taskkill /fi "WindowTitle eq ElasticGuard Backend" /f 2>nul
taskkill /fi "WindowTitle eq ElasticGuard Frontend" /f 2>nul
:: Kill by process name (run-local uses background cmd)
for /f "tokens=2" %%P in ('tasklist /fi "IMAGENAME eq uvicorn.exe" /fo csv /nh 2^>nul') do taskkill /pid %%~P /f 2>nul
call :ok "All services stopped."
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_logs
:: ═════════════════════════════════════════════════════════════════════════════
set "CF=docker-compose.yml"
if "%~2"=="--hub"    set "CF=docker-compose.hub.yml"
if "%~2"=="-h"       set "CF=docker-compose.hub.yml"
if "%~2"=="--airgap" set "CF=docker-compose.airgap.yml"
if "%~2"=="-a"       set "CF=docker-compose.airgap.yml"
echo [INFO] Tailing logs from %CF%
docker compose -f "%CF%" logs -f --tail=100
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:mode_help
:: ═════════════════════════════════════════════════════════════════════════════
echo Usage:  start.cmd [MODE]
echo.
call :div
echo With source code (requires Python + Node.js or Docker):
echo.
echo   docker          Build Docker images from source and run
echo   local           Run dev server with hot reload (no Docker)
echo   ollama          Docker + local Llama LLM (no AI key needed)
echo   docker-private  Build from a private/air-gapped Docker registry
echo.
call :div
echo Local builds (no Docker):
echo.
echo   build           Compile frontend (.next\) + install Python deps (venv\)
echo   run-local       Serve the compiled build from 'build'
echo.
call :div
echo Docker Hub (no source code required):
echo.
echo   push            Build Docker images and push to Docker Hub
echo   run-docker      Pull images from Docker Hub and run
echo.
call :div
echo Utilities:
echo.
echo   stop            Stop all services (Docker + local processes)
echo   logs            Tail logs  (--hub  or  --airgap  for other files)
echo.
call :div
echo Typical flows:
echo.
echo   Dev:        start.cmd local
echo   Production: start.cmd docker
echo   No Docker:  start.cmd build   then   start.cmd run-local
echo   Share:      start.cmd push    then   start.cmd run-docker
call :div
goto :eof


:: ═════════════════════════════════════════════════════════════════════════════
:: Shared helper subroutines
:: ═════════════════════════════════════════════════════════════════════════════

:need_docker
where docker >nul 2>&1
if errorlevel 1 ( call :err "Docker not found. Install from https://docker.com" & exit /b 1 )
docker info >nul 2>&1
if errorlevel 1 ( call :err "Docker daemon is not running. Start Docker Desktop." & exit /b 1 )
exit /b 0

:need_python
where python >nul 2>&1 || where python3 >nul 2>&1 || where py >nul 2>&1
if errorlevel 1 ( call :err "Python not found. Install from https://python.org" & exit /b 1 )
exit /b 0

:need_node
where node >nul 2>&1
if errorlevel 1 ( call :err "Node.js not found. Install from https://nodejs.org" & exit /b 1 )
where npm >nul 2>&1
if errorlevel 1 ( call :err "npm not found. Reinstall Node.js." & exit /b 1 )
exit /b 0

:ensure_env
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [WARN] Created .env from .env.example -- edit with your API keys
    ) else (
        echo [WARN] No .env found and no .env.example to copy from
    )
)
exit /b 0

:pull_base_images
echo [INFO] Pre-pulling base images to avoid build timeouts
for %%I in ("python:3.11-slim" "node:20-alpine") do (
    set "PULL_OK=0"
    for /l %%A in (1,1,3) do (
        if "!PULL_OK!"=="0" (
            docker pull "%%~I" >nul 2>&1 && set "PULL_OK=1"
            if "!PULL_OK!"=="0" (
                echo [WARN] Could not pull %%~I (attempt %%A/3)
                timeout /t 5 /nobreak >nul
            )
        )
    )
    if "!PULL_OK!"=="0" echo [WARN] Using cached %%~I if available
)
exit /b 0

:browser_url
if not defined NEXT_PUBLIC_API_URL set "NEXT_PUBLIC_API_URL=http://localhost:8000"
echo [INFO] Browser-to-Backend URL: %NEXT_PUBLIC_API_URL%
echo        Override: set NEXT_PUBLIC_API_URL=http://your-ip:8000 ^&^& start.cmd docker
echo.
exit /b 0

:ok
echo [OK] %~1
exit /b 0

:err
echo [ERROR] %~1 >&2
exit /b 1

:div
echo ----------------------------------------------------
exit /b 0
