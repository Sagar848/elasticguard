"""
ElasticGuard Backend - Main FastAPI Application
"""
import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from core.config import settings
from core.persistence import init_db as init_persistence_db
from api.routes import (
    cluster_router, diagnostics_router, monitoring_router,
    agents_router, notifications_router, settings_router,
    topology_router, simulator_router, cost_router,
    approval_router, websocket_router,
)
from api.query_analyser import query_analyser_router
from api.prometheus import prometheus_router
from monitoring.scheduler import MonitoringScheduler
from knowledge.knowledge_base import init_knowledge_base

logger = structlog.get_logger()
monitoring_scheduler = MonitoringScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ElasticGuard backend...")

    # Init SQLite for cluster persistence
    try:
        init_persistence_db()
    except Exception as e:
        logger.warning("DB init failed (non-fatal)", error=str(e))

    # Auto-restore previously connected clusters from DB
    asyncio.create_task(_restore_ai_config())
    asyncio.create_task(_restore_clusters())

    await monitoring_scheduler.start()

    # Init RAG knowledge base in background (non-blocking)
    asyncio.create_task(_init_kb())

    logger.info("ElasticGuard backend started successfully")
    yield
    logger.info("Shutting down...")
    await monitoring_scheduler.stop()


async def _restore_ai_config():
    """Restore AI provider config from SQLite on startup."""
    try:
        from core.persistence import load_ai_config
        cfg = load_ai_config()
        if not cfg:
            return
        provider = cfg.get("provider")
        api_key  = cfg.get("api_key")
        model    = cfg.get("model")
        base_url = cfg.get("base_url")

        if provider:
            settings.DEFAULT_AI_PROVIDER = provider
        if api_key:
            if provider == "openai":
                settings.OPENAI_API_KEY = api_key
            elif provider == "gemini":
                settings.GEMINI_API_KEY = api_key
            elif provider == "anthropic":
                settings.ANTHROPIC_API_KEY = api_key
            elif provider == "custom":
                settings.CUSTOM_AI_KEY = api_key
        # Migrate deprecated Gemini model names
        _gemini_deprecated = {
            "gemini-1.5-pro", "gemini-2.0-flash-lite",
            "gemini-pro", "gemini-1.0-pro",
        }
        if provider == "gemini" and model in _gemini_deprecated:
            model = "gemini-2.0-flash"
            logger.info("Migrated deprecated Gemini model to gemini-2.0-flash")

        if model:
            if provider == "openai":
                settings.OPENAI_DEFAULT_MODEL = model
            elif provider == "gemini":
                settings.GEMINI_DEFAULT_MODEL = model
            elif provider == "anthropic":
                settings.ANTHROPIC_DEFAULT_MODEL = model
            elif provider == "ollama":
                settings.OLLAMA_DEFAULT_MODEL = model
        if base_url:
            if provider == "ollama":
                settings.OLLAMA_BASE_URL = base_url
            elif provider == "custom":
                settings.CUSTOM_AI_BASE_URL = base_url

        logger.info("AI config restored from DB", provider=provider)
    except Exception as e:
        logger.warning("Could not restore AI config", error=str(e))


async def _restore_clusters():
    """Re-register clusters from SQLite on startup."""
    import asyncio as _asyncio
    await _asyncio.sleep(1)  # brief delay to let app finish starting
    try:
        from core.persistence import load_all_clusters
        from core.es_client import ElasticsearchClient, ClusterConnection, register_cluster
        clusters = load_all_clusters()
        for c in clusters:
            try:
                conn = ClusterConnection(
                    url=c["url"],
                    username=c.get("username"),
                    password=c.get("password"),
                    api_key=c.get("api_key"),
                    verify_ssl=bool(c.get("verify_ssl", False)),
                )
                client = ElasticsearchClient(conn)
                ok, _ = await client.test_connection()
                if ok:
                    register_cluster(c["cluster_id"], client)
                    logger.info("Cluster restored from DB", cluster_id=c["cluster_id"])
                else:
                    logger.info("Cluster unavailable (will reconnect when frontend loads)", cluster_id=c["cluster_id"])
            except Exception as e:
                logger.warning("Could not restore cluster", cluster_id=c.get("cluster_id"), error=str(e))
    except Exception as e:
        logger.warning("Cluster restore failed", error=str(e))


async def _init_kb():
    try:
        await init_knowledge_base(
            persist_dir=settings.CHROMA_PERSIST_DIR,
            ollama_base=settings.OLLAMA_BASE_URL,
        )
    except Exception as e:
        logger.info("Knowledge base init skipped", error=str(e))


app = FastAPI(
    title="ElasticGuard API",
    description="AI-Powered Elasticsearch Diagnostic & Monitoring Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(cluster_router,        prefix="/api/cluster",     tags=["Cluster"])
app.include_router(diagnostics_router,    prefix="/api/diagnostics", tags=["Diagnostics"])
app.include_router(monitoring_router,     prefix="/api/monitoring",  tags=["Monitoring"])
app.include_router(agents_router,         prefix="/api/agents",      tags=["AI Agents"])
app.include_router(notifications_router,  prefix="/api/notifications",tags=["Notifications"])
app.include_router(settings_router,       prefix="/api/settings",    tags=["Settings"])
app.include_router(topology_router,       prefix="/api/topology",    tags=["Topology"])
app.include_router(simulator_router,      prefix="/api/simulator",   tags=["Simulator"])
app.include_router(cost_router,           prefix="/api/cost",        tags=["Cost Optimizer"])
app.include_router(approval_router,       prefix="/api/approval",    tags=["Approval"])
app.include_router(websocket_router,      prefix="/ws",              tags=["WebSocket"])
app.include_router(query_analyser_router, prefix="/api/query",       tags=["Query Analyser"])
app.include_router(prometheus_router,     prefix="/metrics/prometheus", tags=["Prometheus"])


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"name": "ElasticGuard", "description": "AI-Powered Elasticsearch Diagnostic Platform", "docs": "/docs"}
