"""
ElasticGuard Query Analyser
Detects slow queries, profiles searches, analyses query patterns
"""
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from core.es_client import get_es_client

logger = structlog.get_logger()

query_analyser_router = APIRouter()


class ProfileRequest(BaseModel):
    cluster_id: str
    index: str
    query: Dict[str, Any]
    size: int = 10


class SlowlogConfig(BaseModel):
    cluster_id: str
    index: str
    query_warn_ms: int = 5000
    query_info_ms: int = 2000
    fetch_warn_ms: int = 1000
    index_warn_ms: int = 1000


@query_analyser_router.get("/{cluster_id}/slow-queries")
async def get_slow_query_stats(cluster_id: str):
    """Get slow query statistics across all indices."""
    client = _get_or_404(cluster_id)

    try:
        stats = await client.get("/_stats/indexing,search,query_cache,request_cache?level=indices")
        indices = stats.get("indices", {})

        slow_indices = []
        for idx_name, idx_data in indices.items():
            if idx_name.startswith("."):
                continue

            search = idx_data.get("total", {}).get("search", {})
            indexing = idx_data.get("total", {}).get("indexing", {})
            qcache = idx_data.get("total", {}).get("query_cache", {})
            rcache = idx_data.get("total", {}).get("request_cache", {})

            query_total = search.get("query_total", 0)
            query_time_ms = search.get("query_time_in_millis", 0)
            avg_query_ms = round(query_time_ms / max(query_total, 1), 2)

            fetch_total = search.get("fetch_total", 0)
            fetch_time_ms = search.get("fetch_time_in_millis", 0)
            avg_fetch_ms = round(fetch_time_ms / max(fetch_total, 1), 2)

            # Cache efficiency
            qcache_hits = qcache.get("hit_count", 0)
            qcache_misses = qcache.get("miss_count", 0)
            qcache_hit_rate = round(qcache_hits / max(qcache_hits + qcache_misses, 1) * 100, 1)

            rcache_hits = rcache.get("hit_count", 0)
            rcache_misses = rcache.get("miss_count", 0)
            rcache_hit_rate = round(rcache_hits / max(rcache_hits + rcache_misses, 1) * 100, 1)

            issues = []
            if avg_query_ms > 2000:
                issues.append(f"Avg query time {avg_query_ms}ms exceeds 2s")
            if avg_fetch_ms > 500:
                issues.append(f"Avg fetch time {avg_fetch_ms}ms is high")
            if qcache_hit_rate < 30 and qcache_hits + qcache_misses > 100:
                issues.append(f"Low query cache hit rate: {qcache_hit_rate}%")

            slow_indices.append({
                "index": idx_name,
                "query_total": query_total,
                "avg_query_ms": avg_query_ms,
                "avg_fetch_ms": avg_fetch_ms,
                "query_cache_hit_rate": qcache_hit_rate,
                "request_cache_hit_rate": rcache_hit_rate,
                "issues": issues,
                "severity": "high" if avg_query_ms > 5000 else "medium" if avg_query_ms > 1000 else "ok",
            })

        # Sort by avg query time desc
        slow_indices.sort(key=lambda x: x["avg_query_ms"], reverse=True)

        return {
            "cluster_id": cluster_id,
            "total_indices": len(slow_indices),
            "problematic_indices": [i for i in slow_indices if i["issues"]],
            "all_indices": slow_indices[:50],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@query_analyser_router.post("/profile")
async def profile_query(req: ProfileRequest):
    """Profile a specific query to identify performance bottlenecks."""
    client = _get_or_404(req.cluster_id)

    try:
        profiled_query = {**req.query, "profile": True, "size": req.size}
        result = await client.post(f"/{req.index}/_search", profiled_query)

        profile = result.get("profile", {})
        shards = profile.get("shards", [])

        analysis = []
        for shard in shards:
            shard_id = shard.get("id", "?")
            searches = shard.get("searches", [])
            for search in searches:
                queries = search.get("query", [])
                for q in queries:
                    _analyse_query_node(q, analysis, shard_id)

        # Sort by time desc
        analysis.sort(key=lambda x: x["time_ms"], reverse=True)

        total_ms = sum(a["time_ms"] for a in analysis)
        suggestions = _generate_query_suggestions(analysis)

        return {
            "total_time_ms": total_ms,
            "shard_count": len(shards),
            "query_breakdown": analysis[:20],
            "suggestions": suggestions,
            "hits_total": result.get("hits", {}).get("total", {}).get("value", 0),
            "raw_profile": profile if len(str(profile)) < 50000 else "Profile too large to return",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@query_analyser_router.post("/enable-slowlog")
async def enable_slowlog(req: SlowlogConfig):
    """Enable slow query logging on an index."""
    client = _get_or_404(req.cluster_id)

    try:
        result = await client.put(f"/{req.index}/_settings", {
            "index.search.slowlog.threshold.query.warn": f"{req.query_warn_ms}ms",
            "index.search.slowlog.threshold.query.info": f"{req.query_info_ms}ms",
            "index.search.slowlog.threshold.query.debug": "500ms",
            "index.search.slowlog.threshold.fetch.warn": f"{req.fetch_warn_ms}ms",
            "index.indexing.slowlog.threshold.index.warn": f"{req.index_warn_ms}ms",
            "index.indexing.slowlog.source": "1000",
        })
        return {"success": True, "index": req.index, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@query_analyser_router.get("/{cluster_id}/hot-threads")
async def get_hot_threads(cluster_id: str):
    """Get hot threads across all nodes."""
    client = _get_or_404(cluster_id)
    try:
        result = await client.nodes_hot_threads()
        return {"hot_threads": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@query_analyser_router.get("/{cluster_id}/tasks")
async def get_running_tasks(cluster_id: str):
    """Get all currently running tasks."""
    client = _get_or_404(cluster_id)
    try:
        result = await client.get("/_tasks", params={"detailed": "true", "human": "true"})
        tasks = []
        for node_id, node_data in result.get("nodes", {}).items():
            node_name = node_data.get("name", node_id)
            for task_id, task in node_data.get("tasks", {}).items():
                tasks.append({
                    "id": task_id,
                    "node": node_name,
                    "action": task.get("action", ""),
                    "description": task.get("description", "")[:200],
                    "running_time": task.get("running_time", ""),
                    "running_time_ms": task.get("running_time_in_nanos", 0) // 1_000_000,
                    "cancellable": task.get("cancellable", False),
                })

        tasks.sort(key=lambda x: x["running_time_ms"], reverse=True)
        long_running = [t for t in tasks if t["running_time_ms"] > 30_000]

        return {
            "total_tasks": len(tasks),
            "long_running": long_running,
            "all_tasks": tasks[:100],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@query_analyser_router.delete("/{cluster_id}/tasks/{task_id}")
async def cancel_task(cluster_id: str, task_id: str):
    """Cancel a running task."""
    client = _get_or_404(cluster_id)
    try:
        result = await client.post(f"/_tasks/{task_id}/_cancel")
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_or_404(cluster_id: str):
    client = get_es_client(cluster_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_id}' not connected")
    return client


def _analyse_query_node(node: dict, results: list, shard_id: str, depth: int = 0):
    """Recursively analyse profiled query nodes."""
    node_type = node.get("type", "unknown")
    desc = node.get("description", "")[:100]
    time_ns = node.get("time_in_nanos", 0)
    time_ms = round(time_ns / 1_000_000, 2)
    advance = node.get("breakdown", {}).get("advance", 0)
    score = node.get("breakdown", {}).get("score", 0)

    results.append({
        "type": node_type,
        "description": desc,
        "time_ms": time_ms,
        "depth": depth,
        "shard": shard_id,
        "advance_ns": advance,
        "score_ns": score,
    })

    for child in node.get("children", []):
        _analyse_query_node(child, results, shard_id, depth + 1)


def _generate_query_suggestions(analysis: list) -> List[str]:
    """Generate optimisation suggestions based on query profile."""
    suggestions = []
    types = [a["type"] for a in analysis]

    if any("wildcard" in t.lower() or "regexp" in t.lower() for t in types):
        suggestions.append("Wildcard/regex queries are slow. Consider n-gram tokenizer or edge_ngram for prefix searches.")

    if any("script" in t.lower() for t in types):
        suggestions.append("Script queries execute on every document. Use stored scripts or restructure to use filters (which are cached).")

    total_ms = sum(a["time_ms"] for a in analysis)
    if total_ms > 5000:
        suggestions.append(f"Total query time {total_ms:.0f}ms is very high. Consider adding filters to reduce document count before scoring.")

    score_time = sum(a.get("score_ns", 0) for a in analysis)
    if score_time > 500_000_000:  # 500ms
        suggestions.append("Scoring is taking a long time. Use filter context instead of query context where relevance scoring is not needed.")

    if not suggestions:
        suggestions.append("Query profile looks reasonable. Monitor for changes in data volume or query patterns.")

    return suggestions
