"""
ElasticGuard API Routes - All endpoints
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio
import json
import structlog

from core.es_client import (
    ElasticsearchClient, ClusterConnection,
    get_es_client, register_cluster, remove_cluster
)
from core.persistence import (
    save_cluster as db_save_cluster,
    delete_cluster as db_delete_cluster,
    load_all_clusters,
    update_cluster_meta,
    save_ai_config as db_save_ai_config,
    load_ai_config as db_load_ai_config,
)
from core.diagnostics import DiagnosticsEngine
from agents.langgraph_agents import ElasticGuardAgentSystem, ClusterChatAgent
from notifications.manager import (
    notification_manager, ApprovalRequest, ApprovalStatus,
    get_approval, resolve_approval, list_pending_approvals
)
from core.config import settings

logger = structlog.get_logger()

# ─── Schemas ──────────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    cluster_id: str = "default"
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    verify_ssl: bool = False


class AIProviderConfig(BaseModel):
    provider: str  # openai | gemini | anthropic | ollama | custom
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ChatRequest(BaseModel):
    cluster_id: str
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None


class ExecuteAPIRequest(BaseModel):
    cluster_id: str
    method: str
    path: str
    body: Optional[Dict] = None
    approval_id: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    approval_id: str
    token: str
    action: str  # approve | reject
    note: Optional[str] = None


class NotificationConfig(BaseModel):
    discord_webhook_url: Optional[str] = None
    discord_bot_token: Optional[str] = None
    discord_channel_id: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    slack_bot_token: Optional[str] = None
    slack_channel_id: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    notification_emails: str = ""


class SimulateRequest(BaseModel):
    cluster_id: str
    simulation_type: str  # add_node | remove_node | rebalance | change_replicas
    parameters: Dict


# In-memory stores (in production: Redis)
_ai_configs: Dict[str, AIProviderConfig] = {}
_chat_agents: Dict[str, ClusterChatAgent] = {}
_diagnosis_cache: Dict[str, Dict] = {}


# ─── Cluster Routes ───────────────────────────────────────────────────────────

cluster_router = APIRouter()


@cluster_router.post("/connect")
async def connect_cluster(req: ConnectRequest):
    """Connect to an Elasticsearch cluster."""
    conn = ClusterConnection(
        url=req.url,
        username=req.username,
        password=req.password,
        api_key=req.api_key,
        verify_ssl=req.verify_ssl,
    )
    client = ElasticsearchClient(conn)
    success, message = await client.test_connection()

    if not success:
        raise HTTPException(status_code=400, detail=message)

    version = await client.get_version()
    conn.es_version = version
    register_cluster(req.cluster_id, client)

    # Get cluster name for display
    cluster_name = req.cluster_id
    try:
        health = await client.cluster_health()
        cluster_name = health.get("cluster_name", req.cluster_id)
    except Exception:
        pass

    # Persist to SQLite so connections survive backend restart
    db_save_cluster(
        cluster_id=req.cluster_id,
        url=req.url,
        username=req.username,
        password=req.password,
        api_key=req.api_key,
        verify_ssl=req.verify_ssl,
        es_version=version,
        cluster_name=cluster_name,
    )

    return {
        "success": True,
        "message": message,
        "cluster_id": req.cluster_id,
        "cluster_name": cluster_name,
        "es_version": version,
    }


@cluster_router.get("/list")
async def list_clusters():
    """List all connected clusters with their health status."""
    from core.es_client import _connections
    result = []
    for cid, client in list(_connections.items()):
        try:
            health = await client.cluster_health()
            info = await client.get("/")
            result.append({
                "cluster_id": cid,
                "cluster_name": health.get("cluster_name", cid),
                "status": health.get("status", "unknown"),
                "es_version": info.get("version", {}).get("number", "?"),
                "node_count": health.get("number_of_nodes", 0),
                "unassigned_shards": health.get("unassigned_shards", 0),
                "url": client.conn.url,
            })
        except Exception as e:
            result.append({
                "cluster_id": cid,
                "cluster_name": cid,
                "status": "error",
                "es_version": "?",
                "node_count": 0,
                "unassigned_shards": 0,
                "url": client.conn.url,
                "error": str(e)[:100],
            })
    return result


@cluster_router.delete("/{cluster_id}/disconnect")
async def disconnect_cluster(cluster_id: str):
    remove_cluster(cluster_id)
    db_delete_cluster(cluster_id)
    return {"success": True}


@cluster_router.get("/persisted")
async def get_persisted_clusters():
    """Return all clusters saved in the DB (for frontend auto-reconnect on reload)."""
    return load_all_clusters()


@cluster_router.get("/{cluster_id}/health")
async def get_cluster_health(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    health = await client.cluster_health()
    return health


@cluster_router.get("/{cluster_id}/stats")
async def get_cluster_stats(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    stats = await client.cluster_stats()
    return stats


@cluster_router.get("/{cluster_id}/nodes")
async def get_nodes(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    nodes_stats = await client.nodes_stats()
    cat_nodes = await client.cat_nodes()
    return {"stats": nodes_stats, "cat": cat_nodes}


@cluster_router.get("/{cluster_id}/indices")
async def get_indices(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    indices = await client.cat_indices()
    return indices


@cluster_router.get("/{cluster_id}/shards")
async def get_shards(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    shards = await client.cat_shards()
    return shards


@cluster_router.get("/{cluster_id}/allocation")
async def get_allocation(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    allocation = await client.cat_allocation()
    return allocation


@cluster_router.get("/{cluster_id}/thread_pool")
async def get_thread_pool(cluster_id: str):
    client = _get_client_or_404(cluster_id)
    tp = await client.cat_thread_pool()
    return tp


@cluster_router.post("/{cluster_id}/execute")
async def execute_api(cluster_id: str, req: ExecuteAPIRequest, background_tasks: BackgroundTasks):
    """Execute an Elasticsearch API call (requires approval for non-GET)."""
    client = _get_client_or_404(cluster_id)

    if req.method.upper() != "GET" and not req.approval_id:
        raise HTTPException(
            status_code=403,
            detail="Non-GET operations require an approval_id. Create an approval request first."
        )

    if req.approval_id:
        approval = get_approval(req.approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        if approval.status != ApprovalStatus.APPROVED:
            raise HTTPException(
                status_code=403,
                detail=f"Approval status is '{approval.status.value}', not approved"
            )
        approval.status = ApprovalStatus.EXECUTED

    try:
        method = req.method.upper()
        if method == "GET":
            result = await client.get(req.path)
        elif method == "POST":
            result = await client.post(req.path, req.body)
        elif method == "PUT":
            result = await client.put(req.path, req.body)
        elif method == "DELETE":
            result = await client.delete(req.path)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")

        return {"success": True, "result": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _auto_create_approvals(cluster_id: str, result: dict, client) -> None:
    """Auto-create approval requests for critical/high severity actionable issues."""
    from notifications.manager import ApprovalRequest, store_approval, _pending_approvals

    # Avoid duplicate approvals for the same issue in this cluster
    existing_titles = {
        a.issue_title for a in _pending_approvals.values()
        if a.cluster_id == cluster_id and a.status.value in ("pending", "approved")
    }

    issues    = result.get("issues", [])
    solutions = {s.get("issue_id"): s for s in result.get("solutions", [])}

    cluster_name = cluster_id
    try:
        health = await client.cluster_health()
        cluster_name = health.get("cluster_name", cluster_id)
    except Exception:
        pass

    for issue in issues:
        severity = issue.get("severity", "low")
        if severity not in ("critical", "high"):
            continue

        title = issue.get("title", "Unknown Issue")
        if title in existing_titles:
            continue

        sol       = solutions.get(issue.get("id", ""), {})
        api_calls = sol.get("apis") or issue.get("elasticsearch_apis") or []

        # Only queue issues that have write-API fixes
        has_write = any(a.get("method", "GET").upper() != "GET" for a in api_calls)
        if not api_calls or not has_write:
            continue

        action_desc = (sol.get("solution_steps") or [issue.get("solution_summary", "")])[0]

        req = ApprovalRequest(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            issue_title=title,
            issue_description=issue.get("description", "")[:500],
            action_description=action_desc,
            api_calls=api_calls[:5],
            cli_commands=sol.get("cli_commands") or issue.get("cli_commands") or [],
            risk_level=sol.get("risk_level") or severity,
            severity=severity,
        )
        store_approval(req)
        existing_titles.add(title)

        try:
            from notifications.manager import notification_manager
            await notification_manager.send_approval_request(req)
        except Exception:
            pass


# ─── Diagnostics Routes ───────────────────────────────────────────────────────

diagnostics_router = APIRouter()


@diagnostics_router.post("/{cluster_id}/run")
async def run_diagnostics(cluster_id: str, background_tasks: BackgroundTasks, use_ai: bool = True, provider: str = None, model: str = None):
    """Run full cluster diagnostics with AI analysis."""
    client = _get_client_or_404(cluster_id)

    # Run ES diagnostics
    engine = DiagnosticsEngine(client)
    report = await engine.run_full_diagnostics(cluster_id)

    if use_ai and report.issues:
        try:
            ai_config = _ai_configs.get(cluster_id)
            ai_provider = provider or (ai_config.provider if ai_config else None) or settings.DEFAULT_AI_PROVIDER
            ai_model = model or (ai_config.model if ai_config else None)

            agent_system = ElasticGuardAgentSystem(provider=ai_provider, model=ai_model)
            result = await agent_system.run(report)
            _diagnosis_cache[cluster_id] = result

            # Auto-create approvals for actionable solutions (critical/high only)
            await _auto_create_approvals(cluster_id, result, client)
            return result

        except ValueError as e:
            raw = _report_to_dict(report)
            raw["ai_error"] = str(e)
            raw["summary"] = (
                f"⚠ AI analysis skipped: {e}\n\n"
                "Raw diagnostics below — configure a valid AI provider in Settings."
            )
            # Still auto-create approvals from raw diagnostics
            await _auto_create_approvals(cluster_id, raw, client)
            return raw
        except Exception as e:
            logger.error("AI agent failed, returning raw diagnostics", error=str(e))
            raw = _report_to_dict(report)
            raw["summary"] = f"Found {len(report.issues)} issue(s). AI analysis unavailable."
            await _auto_create_approvals(cluster_id, raw, client)
            return raw
    else:
        raw = _report_to_dict(report)
        await _auto_create_approvals(cluster_id, raw, client)
        return raw


@diagnostics_router.get("/{cluster_id}/latest")
async def get_latest_diagnosis(cluster_id: str):
    """Get the latest cached diagnosis."""
    if cluster_id not in _diagnosis_cache:
        raise HTTPException(status_code=404, detail="No diagnosis found. Run /run first.")
    return _diagnosis_cache[cluster_id]


@diagnostics_router.get("/{cluster_id}/allocation-explain")
async def explain_allocation(cluster_id: str, index: str = None, shard: int = 0, primary: bool = True):
    client = _get_client_or_404(cluster_id)
    result = await client.cluster_allocation_explain(index, shard, primary)
    return result


# ─── Monitoring Routes ────────────────────────────────────────────────────────

monitoring_router = APIRouter()


@monitoring_router.get("/{cluster_id}/metrics")
async def get_live_metrics(cluster_id: str):
    """Get real-time cluster metrics snapshot including nodes (with IP) and indices."""
    client = _get_client_or_404(cluster_id)

    health, nodes_stats, cat_nodes, cat_indices = await asyncio.gather(
        client.cluster_health(),
        client.nodes_stats(),
        client.cat_nodes(),
        client.cat_indices(),
        return_exceptions=True,
    )

    # Build an ip lookup from cat_nodes (keyed by node name)
    ip_by_name: dict = {}
    if isinstance(cat_nodes, list):
        for cn in cat_nodes:
            name = cn.get("name", "")
            ip   = cn.get("ip", "")
            if name and ip:
                ip_by_name[name] = ip

    nodes_summary = []
    if isinstance(nodes_stats, dict):
        for node_id, nd in nodes_stats.get("nodes", {}).items():
            jvm      = nd.get("jvm", {}).get("mem", {})
            os_stats = nd.get("os", {})
            fs       = nd.get("fs", {}).get("total", {})
            name     = nd.get("name", node_id)
            nodes_summary.append({
                "id":           node_id,
                "name":         name,
                "ip":           nd.get("ip") or ip_by_name.get(name, ""),
                "roles":        nd.get("roles", []),
                "heap_used_pct": jvm.get("heap_used_percent", 0),
                "heap_used_gb": round(jvm.get("heap_used_in_bytes", 0) / 1e9, 2),
                "heap_max_gb":  round(jvm.get("heap_max_in_bytes", 1) / 1e9, 2),
                "cpu_pct":      os_stats.get("cpu", {}).get("percent", 0),
                "load_avg":     os_stats.get("cpu", {}).get("load_average", {}).get("1m", 0),
                "disk_used_gb": round((fs.get("total_in_bytes", 0) - fs.get("available_in_bytes", 0)) / 1e9, 2),
                "disk_total_gb":round(fs.get("total_in_bytes", 1) / 1e9, 2),
                "disk_used_pct":round(
                    ((fs.get("total_in_bytes", 0) - fs.get("available_in_bytes", 0))
                     / max(fs.get("total_in_bytes", 1), 1)) * 100, 1
                ),
                "gc_old_count":   nd.get("jvm", {}).get("gc", {}).get("collectors", {}).get("old", {}).get("collection_count", 0),
                "indexing_rate":  nd.get("indices", {}).get("indexing", {}).get("index_current", 0),
                "search_rate":    nd.get("indices", {}).get("search", {}).get("query_current", 0),
            })

    # Build indices list for topology view
    indices_list = []
    if isinstance(cat_indices, list):
        for idx in cat_indices:
            indices_list.append({
                "index":      idx.get("index", ""),
                "health":     idx.get("health", ""),
                "status":     idx.get("status", ""),
                "pri":        idx.get("pri", ""),
                "rep":        idx.get("rep", ""),
                "docs_count": idx.get("docs.count", ""),
                "store_size": idx.get("store.size", ""),
            })

    return {
        "health":  health if not isinstance(health, Exception) else {"status": "unknown"},
        "nodes":   nodes_summary,
        "indices": indices_list,
        "timestamp": asyncio.get_event_loop().time(),
    }


# ─── AI Agents Routes ─────────────────────────────────────────────────────────

agents_router = APIRouter()


@agents_router.post("/chat")
async def chat_with_agent(req: ChatRequest):
    """Chat with the AI agent about cluster issues."""
    _get_client_or_404(req.cluster_id)

    agent_key = f"{req.cluster_id}_{req.provider or 'default'}"
    if agent_key not in _chat_agents:
        try:
            _chat_agents[agent_key] = ClusterChatAgent(
                provider=req.provider or settings.DEFAULT_AI_PROVIDER,
                model=req.model,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Get cluster context
    client = get_es_client(req.cluster_id)
    context = None
    if client:
        try:
            health = await client.cluster_health()
            context = {
                "health_status": health.get("status"),
                "unassigned_shards": health.get("unassigned_shards", 0),
                "latest_diagnosis": _diagnosis_cache.get(req.cluster_id, {}).get("issues", [])[:5],
            }
        except Exception:
            pass

    try:
        response = await _chat_agents[agent_key].chat(req.message, context)
        return {"response": response}
    except ValueError as e:
        # API key became invalid mid-session — clear cached agent
        _chat_agents.pop(agent_key, None)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        err_msg = str(e)
        # Surface API key errors as 400 instead of 500
        if any(kw in err_msg.lower() for kw in ("api key", "invalid_api_key", "api_key_invalid", "invalid argument", "authentication")):
            _chat_agents.pop(agent_key, None)
            raise HTTPException(status_code=400, detail=f"AI provider error: {err_msg[:300]}")
        raise


@agents_router.post("/configure")
async def configure_ai(cluster_id: str, config: AIProviderConfig):
    """Configure AI provider — persisted to SQLite so it survives backend restarts."""
    _ai_configs[cluster_id] = config

    # Update in-memory settings
    if config.api_key:
        if config.provider == "openai":
            settings.OPENAI_API_KEY = config.api_key
        elif config.provider == "gemini":
            settings.GEMINI_API_KEY = config.api_key
        elif config.provider == "anthropic":
            settings.ANTHROPIC_API_KEY = config.api_key
        elif config.provider == "custom":
            settings.CUSTOM_AI_KEY = config.api_key

    if config.base_url and config.provider in ("custom", "ollama"):
        if config.provider == "custom":
            settings.CUSTOM_AI_BASE_URL = config.base_url
        elif config.provider == "ollama":
            settings.OLLAMA_BASE_URL = config.base_url

    if config.model:
        if config.provider == "openai":
            settings.OPENAI_DEFAULT_MODEL = config.model
        elif config.provider == "gemini":
            settings.GEMINI_DEFAULT_MODEL = config.model
        elif config.provider == "anthropic":
            settings.ANTHROPIC_DEFAULT_MODEL = config.model
        elif config.provider == "ollama":
            settings.OLLAMA_DEFAULT_MODEL = config.model

    settings.DEFAULT_AI_PROVIDER = config.provider

    # Persist to SQLite — survives backend restarts
    try:
        db_save_ai_config(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
        )
    except Exception as e:
        logger.warning("Could not persist AI config", error=str(e))

    return {"success": True, "provider": config.provider}


@agents_router.get("/config")
async def get_ai_config():
    """Return the currently active AI config (from DB if available)."""
    saved = db_load_ai_config()
    return {
        "provider": saved.get("provider") or settings.DEFAULT_AI_PROVIDER,
        "model":    saved.get("model"),
        "api_key":  saved.get("api_key"),   # returned so frontend can restore
        "base_url": saved.get("base_url"),
    }


@agents_router.get("/providers")
async def list_providers():
    """List available AI providers."""
    return {
        "providers": [
            {"id": "openai", "name": "OpenAI", "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"], "requires_key": True},
            {"id": "gemini", "name": "Google Gemini", "models": ["gemini-2.0-flash", "gemini-2.5-pro-preview-03-25", "gemini-1.5-flash-latest"], "requires_key": True},
            {"id": "anthropic", "name": "Anthropic Claude", "models": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"], "requires_key": True},
            {"id": "ollama", "name": "Ollama (Local)", "models": ["llama3.2", "mistral", "codellama", "phi3"], "requires_key": False},
            {"id": "custom", "name": "Custom OpenAI-Compatible", "models": [], "requires_key": False},
        ],
        "current": settings.DEFAULT_AI_PROVIDER,
    }


# ─── Notifications Routes ─────────────────────────────────────────────────────

notifications_router = APIRouter()


@notifications_router.post("/configure")
async def configure_notifications(config: NotificationConfig):
    """Configure notification channels."""
    if config.discord_webhook_url:
        settings.DISCORD_WEBHOOK_URL = config.discord_webhook_url
    if config.discord_bot_token:
        settings.DISCORD_BOT_TOKEN = config.discord_bot_token
    if config.discord_channel_id:
        settings.DISCORD_CHANNEL_ID = config.discord_channel_id
    if config.slack_webhook_url:
        settings.SLACK_WEBHOOK_URL = config.slack_webhook_url
    if config.slack_bot_token:
        settings.SLACK_BOT_TOKEN = config.slack_bot_token
    if config.slack_channel_id:
        settings.SLACK_CHANNEL_ID = config.slack_channel_id
    if config.smtp_host:
        settings.SMTP_HOST = config.smtp_host
        settings.SMTP_PORT = config.smtp_port
        settings.SMTP_USER = config.smtp_user
        settings.SMTP_PASS = config.smtp_pass
    if config.notification_emails:
        settings.NOTIFICATION_EMAILS = config.notification_emails

    return {"success": True}


@notifications_router.post("/test")
async def test_notification(channel: str = "discord"):
    """Send a test notification."""
    import uuid
    test_req = ApprovalRequest(
        cluster_id="test",
        cluster_name="Test Cluster",
        issue_title="Test Alert",
        issue_description="This is a test notification from ElasticGuard.",
        action_description="No action needed — this is a test.",
        api_calls=[{"method": "GET", "path": "/_cluster/health", "description": "Test API call"}],
        cli_commands=["echo 'test'"],
        risk_level="low",
        severity="low",
    )
    results = await notification_manager.send_approval_request(test_req)
    return {"success": True, "results": results}


# ─── Approval Routes ──────────────────────────────────────────────────────────

approval_router = APIRouter()


@approval_router.get("/pending")
async def get_pending_approvals():
    """Get all pending approval requests."""
    approvals = list_pending_approvals()
    return [a.to_dict() for a in approvals]


@approval_router.post("/create")
async def create_approval(
    cluster_id: str,
    issue_title: str,
    issue_description: str,
    action_description: str,
    api_calls: List[Dict],
    cli_commands: List[str] = [],
    risk_level: str = "medium",
    severity: str = "high",
):
    """Create an approval request and notify channels."""
    client = _get_client_or_404(cluster_id)

    # Get cluster info
    try:
        health = await client.cluster_health()
        cluster_name = health.get("cluster_name", cluster_id)
    except Exception:
        cluster_name = cluster_id

    req = ApprovalRequest(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        issue_title=issue_title,
        issue_description=issue_description,
        action_description=action_description,
        api_calls=api_calls,
        cli_commands=cli_commands,
        risk_level=risk_level,
        severity=severity,
    )

    results = await notification_manager.send_approval_request(req)

    return {
        "approval_id": req.id,
        "token": req.token,
        "notifications": results,
        "approve_url": req.approve_url,
        "reject_url": req.reject_url,
        "expires_at": req.expires_at.isoformat(),
    }


@approval_router.post("/resolve")
async def resolve_approval_endpoint(req: ApprovalActionRequest):
    """Approve or reject an action (works from UI without token, or with token from Discord/Slack/Email)."""
    status = ApprovalStatus.APPROVED if req.action == "approve" else ApprovalStatus.REJECTED
    # Pass token as empty string for UI-direct approvals — token check skipped when empty
    approval = resolve_approval(req.approval_id, status, req.token or "")

    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    execute_result = None

    # Auto-execute Elasticsearch API calls when approved
    if status == ApprovalStatus.APPROVED and approval.api_calls:
        client = get_es_client(approval.cluster_id)
        if client:
            results = []
            for api_call in approval.api_calls:
                try:
                    method = api_call.get("method", "GET").upper()
                    path   = api_call.get("path", "/")
                    body   = api_call.get("body")
                    if method == "GET":
                        r = await client.get(path)
                    elif method == "POST":
                        r = await client.post(path, body)
                    elif method == "PUT":
                        r = await client.put(path, body)
                    elif method == "DELETE":
                        r = await client.delete(path)
                    else:
                        r = {"error": f"Unsupported method: {method}"}
                    results.append({"path": path, "method": method, "result": r, "success": True})
                except Exception as e:
                    results.append({"path": api_call.get("path"), "method": api_call.get("method"), "error": str(e), "success": False})
            approval.status = ApprovalStatus.EXECUTED
            execute_result = results

    await notification_manager.send_resolution_notification(approval)

    return {
        "success": True,
        "approval_id": req.approval_id,
        "status": approval.status.value,
        "executed": execute_result,
    }


@approval_router.get("/{approval_id}")
async def get_approval_endpoint(approval_id: str):
    approval = get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval.to_dict()


# ─── Topology Routes ──────────────────────────────────────────────────────────

topology_router = APIRouter()


@topology_router.get("/{cluster_id}")
async def get_topology(cluster_id: str):
    """Get cluster topology for visualization."""
    client = _get_client_or_404(cluster_id)

    health, nodes_info, nodes_stats, cat_shards, cat_indices = await asyncio.gather(
        client.cluster_health(),
        client.nodes_info(),
        client.nodes_stats(),
        client.cat_shards(),
        client.cat_indices(),
        return_exceptions=True,
    )

    nodes = []
    if isinstance(nodes_info, dict) and isinstance(nodes_stats, dict):
        for node_id, node_info in nodes_info.get("nodes", {}).items():
            nstats = nodes_stats.get("nodes", {}).get(node_id, {})
            jvm = nstats.get("jvm", {}).get("mem", {})
            os_data = nstats.get("os", {})
            fs = nstats.get("fs", {}).get("total", {})

            heap_pct = jvm.get("heap_used_percent", 0)
            cpu_pct = os_data.get("cpu", {}).get("percent", 0)
            disk_used = fs.get("total_in_bytes", 0) - fs.get("available_in_bytes", 0)
            disk_total = max(fs.get("total_in_bytes", 1), 1)
            disk_pct = round(disk_used / disk_total * 100, 1)

            # Determine node health
            if heap_pct >= 90 or cpu_pct >= 90 or disk_pct >= 90:
                node_health = "red"
            elif heap_pct >= 80 or cpu_pct >= 80 or disk_pct >= 80:
                node_health = "yellow"
            else:
                node_health = "green"

            nodes.append({
                "id": node_id,
                "name": node_info.get("name", node_id),
                "ip": node_info.get("ip", ""),
                "roles": node_info.get("roles", []),
                "is_master": node_info.get("attributes", {}).get("master", "false") == "true",
                "health": node_health,
                "metrics": {
                    "heap_pct": heap_pct,
                    "cpu_pct": cpu_pct,
                    "disk_pct": disk_pct,
                    "disk_used_gb": round(disk_used / 1e9, 2),
                    "disk_total_gb": round(disk_total / 1e9, 2),
                },
                "shards": [],  # filled below
            })

    # Assign shards to nodes
    if isinstance(cat_shards, list):
        node_map = {n["name"]: n for n in nodes}
        for shard in cat_shards:
            node_name = shard.get("node", "")
            if node_name in node_map:
                node_map[node_name]["shards"].append({
                    "index": shard.get("index"),
                    "shard": shard.get("shard"),
                    "prirep": shard.get("prirep"),
                    "state": shard.get("state"),
                })

    indices_summary = []
    if isinstance(cat_indices, list):
        for idx in cat_indices[:50]:  # limit
            indices_summary.append({
                "name": idx.get("index"),
                "health": idx.get("health"),
                "status": idx.get("status"),
                "pri": idx.get("pri"),
                "rep": idx.get("rep"),
                "docs_count": idx.get("docs.count"),
                "store_size": idx.get("store.size"),
            })

    return {
        "cluster_name": health.get("cluster_name", cluster_id) if isinstance(health, dict) else cluster_id,
        "health_status": health.get("status", "unknown") if isinstance(health, dict) else "unknown",
        "nodes": nodes,
        "indices": indices_summary,
        "unassigned_shards": health.get("unassigned_shards", 0) if isinstance(health, dict) else 0,
    }


# ─── Simulator Routes ─────────────────────────────────────────────────────────

simulator_router = APIRouter()


@simulator_router.post("/simulate")
async def simulate_cluster_change(req: SimulateRequest):
    """Simulate a cluster change using the physics-based simulation engine."""
    from simulators.engine import ClusterSimulator
    client = _get_client_or_404(req.cluster_id)

    health, nodes_stats, cat_nodes, cat_shards, cat_allocation = await asyncio.gather(
        client.cluster_health(),
        client.nodes_stats(),
        client.cat_nodes(),
        client.cat_shards(),
        client.cat_allocation(),
        return_exceptions=True,
    )

    def safe(r, default):
        return r if not isinstance(r, Exception) else default

    sim = ClusterSimulator()
    snapshot = sim.build_snapshot_from_es(
        nodes_stats=safe(nodes_stats, {"nodes": {}}),
        cat_nodes=safe(cat_nodes, []),
        cat_shards=safe(cat_shards, []),
        cat_allocation=safe(cat_allocation, []),
        cluster_name=safe(health, {}).get("cluster_name", req.cluster_id),
    )

    p = req.parameters

    if req.simulation_type == "add_node":
        result = sim.simulate_add_node(
            snapshot,
            count=int(p.get("count", 1)),
            disk_gb=float(p["disk_gb"]) if "disk_gb" in p else None,
            heap_gb=float(p["heap_gb"]) if "heap_gb" in p else None,
        )
    elif req.simulation_type == "remove_node":
        result = sim.simulate_remove_node(snapshot, node_name=p.get("node_name"))
    elif req.simulation_type == "change_replicas":
        result = sim.simulate_change_replicas(
            snapshot,
            index_pattern=p.get("index", "*"),
            new_replicas=int(p.get("replicas", 1)),
        )
    elif req.simulation_type == "rebalance":
        result = sim.simulate_rebalance(snapshot)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown simulation_type: {req.simulation_type}")

    result["disclaimer"] = "Simulation only. Actual results depend on network speed, index patterns, and ES configuration."
    return result


# ─── Cost Optimizer Routes ────────────────────────────────────────────────────

cost_router = APIRouter()


@cost_router.get("/{cluster_id}/analysis")
async def get_cost_analysis(cluster_id: str):
    """Analyze cluster for cost optimization opportunities."""
    client = _get_client_or_404(cluster_id)

    cat_indices, nodes_stats, cat_shards = await asyncio.gather(
        client.cat_indices(),
        client.nodes_stats(),
        client.cat_shards(),
        return_exceptions=True,
    )

    recommendations = []

    if isinstance(cat_indices, list):
        for idx in cat_indices:
            index_name = idx.get("index", "?")
            if index_name.startswith("."):
                continue

            docs_count = int(idx.get("docs.count") or 0)
            pri = int(idx.get("pri") or 1)
            rep = int(idx.get("rep") or 0)
            store_gb = _parse_store_gb(idx.get("store.size", "0b"))

            # No replicas on single-node
            if rep == 0 and isinstance(nodes_stats, dict):
                node_count = len(nodes_stats.get("nodes", {}))
                if node_count > 1:
                    recommendations.append({
                        "type": "add_replicas",
                        "priority": "high",
                        "index": index_name,
                        "description": f"Index '{index_name}' has no replicas — data loss risk",
                        "savings": "N/A",
                        "action": f"PUT /{index_name}/_settings {{\"index.number_of_replicas\": 1}}",
                    })

            # Over-replicated tiny indices
            if rep > 1 and store_gb < 0.1 and docs_count < 10000:
                savings_gb = store_gb * (rep - 1)
                recommendations.append({
                    "type": "reduce_replicas",
                    "priority": "medium",
                    "index": index_name,
                    "description": f"Index '{index_name}' is tiny ({store_gb*1000:.0f}MB) but has {rep} replicas",
                    "savings": f"~{savings_gb*1000:.0f}MB disk",
                    "action": f"PUT /{index_name}/_settings {{\"index.number_of_replicas\": 1}}",
                })

            # Oversized shards
            shard_size = store_gb / max(pri, 1)
            if shard_size > 50:
                recommendations.append({
                    "type": "split_shards",
                    "priority": "medium",
                    "index": index_name,
                    "description": f"Index '{index_name}' shards are {shard_size:.0f}GB average (optimal: 10-50GB)",
                    "savings": "Better performance",
                    "action": f"Reindex with {max(pri*2, 3)} shards",
                })

            # Empty or near-empty indices
            if docs_count < 100 and store_gb < 0.01 and not index_name.startswith("."):
                recommendations.append({
                    "type": "delete_empty",
                    "priority": "low",
                    "index": index_name,
                    "description": f"Index '{index_name}' is nearly empty ({docs_count} docs)",
                    "savings": "Reduces shard count overhead",
                    "action": f"DELETE /{index_name}",
                })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))

    total_indices = len([i for i in (cat_indices if isinstance(cat_indices, list) else []) if not i.get("index", "").startswith(".")])
    node_count = len((nodes_stats or {}).get("nodes", {})) if isinstance(nodes_stats, dict) else 0

    return {
        "cluster_id": cluster_id,
        "total_recommendations": len(recommendations),
        "recommendations": recommendations[:50],
        "summary": {
            "total_indices_analyzed": total_indices,
            "node_count": node_count,
            "high_priority": len([r for r in recommendations if r["priority"] == "high"]),
            "medium_priority": len([r for r in recommendations if r["priority"] == "medium"]),
            "low_priority": len([r for r in recommendations if r["priority"] == "low"]),
        }
    }


# ─── Settings Routes ──────────────────────────────────────────────────────────

settings_router = APIRouter()


@settings_router.get("/")
async def get_settings():
    return {
        "ai_provider": settings.DEFAULT_AI_PROVIDER,
        "monitoring_interval": settings.MONITORING_INTERVAL_SECONDS,
        "alert_thresholds": {
            "cpu": settings.ALERT_CPU_THRESHOLD,
            "jvm": settings.ALERT_JVM_THRESHOLD,
            "disk": settings.ALERT_DISK_THRESHOLD,
        },
        "notifications_configured": {
            "discord": bool(settings.DISCORD_WEBHOOK_URL or settings.DISCORD_BOT_TOKEN),
            "slack": bool(settings.SLACK_WEBHOOK_URL or settings.SLACK_BOT_TOKEN),
            "email": bool(settings.SMTP_HOST and settings.NOTIFICATION_EMAILS),
        }
    }


# ─── WebSocket Routes ─────────────────────────────────────────────────────────

websocket_router = APIRouter()
_ws_connections: Dict[str, List[WebSocket]] = {}


@websocket_router.websocket("/metrics/{cluster_id}")
async def websocket_metrics(websocket: WebSocket, cluster_id: str):
    """Real-time metrics stream via WebSocket."""
    await websocket.accept()
    if cluster_id not in _ws_connections:
        _ws_connections[cluster_id] = []
    _ws_connections[cluster_id].append(websocket)

    async def safe_send(data: dict) -> bool:
        """Send JSON, return False if connection is already closed."""
        try:
            await websocket.send_json(data)
            return True
        except (WebSocketDisconnect, RuntimeError, Exception):
            return False

    try:
        while True:
            client = get_es_client(cluster_id)
            if client:
                try:
                    health, nodes_stats = await asyncio.gather(
                        client.cluster_health(),
                        client.nodes_stats(),
                        return_exceptions=True,
                    )

                    nodes_data = []
                    if isinstance(nodes_stats, dict):
                        for nd_id, nd in nodes_stats.get("nodes", {}).items():
                            jvm     = nd.get("jvm", {}).get("mem", {})
                            os_data = nd.get("os", {})
                            nodes_data.append({
                                "id":       nd_id,
                                "name":     nd.get("name"),
                                "heap_pct": jvm.get("heap_used_percent", 0),
                                "cpu_pct":  os_data.get("cpu", {}).get("percent", 0),
                            })

                    sent = await safe_send({
                        "type":        "metrics",
                        "health":      health.get("status") if isinstance(health, dict) else "unknown",
                        "unassigned":  health.get("unassigned_shards", 0) if isinstance(health, dict) else 0,
                        "nodes":       nodes_data,
                    })
                    if not sent:
                        break  # client disconnected — stop the loop

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    sent = await safe_send({"type": "error", "message": str(e)})
                    if not sent:
                        break

            await asyncio.sleep(settings.MONITORING_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        pass  # normal — client navigated away
    except Exception:
        pass  # swallow any other send errors on closed socket
    finally:
        # Always clean up the connection registry
        if cluster_id in _ws_connections:
            try:
                _ws_connections[cluster_id].remove(websocket)
            except ValueError:
                pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_client_or_404(cluster_id: str) -> ElasticsearchClient:
    client = get_es_client(cluster_id)
    if not client:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{cluster_id}' not connected. Connect first via POST /api/cluster/connect"
        )
    return client


def _report_to_dict(report) -> Dict:
    return {
        "report": {
            "cluster_id": report.cluster_id,
            "cluster_name": report.cluster_name,
            "es_version": report.es_version,
            "health_status": report.health_status,
            "node_count": report.node_count,
            "unassigned_shards": report.unassigned_shards,
        },
        "issues": [
            {
                "id": i.id,
                "category": i.category.value,
                "severity": i.severity.value,
                "title": i.title,
                "description": i.description,
                "affected_resource": i.affected_resource,
                "metrics": i.metrics,
                "solution_summary": i.solution_summary,
                "elasticsearch_apis": i.elasticsearch_apis,
                "cli_commands": i.cli_commands,
                "requires_approval": i.requires_approval,
            }
            for i in report.issues
        ],
        "solutions": [],
        "summary": f"Found {len(report.issues)} issues. Cluster status: {report.health_status}.",
    }


def _parse_store_gb(size_str: str) -> float:
    if not size_str:
        return 0.0
    s = str(size_str).lower().strip()
    try:
        if s.endswith("tb"): return float(s[:-2]) * 1024
        if s.endswith("gb"): return float(s[:-2])
        if s.endswith("mb"): return float(s[:-2]) / 1024
        if s.endswith("kb"): return float(s[:-2]) / (1024**2)
        if s.endswith("b"): return float(s[:-1]) / (1024**3)
    except ValueError:
        pass
    return 0.0
