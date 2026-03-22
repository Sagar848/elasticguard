"""
ElasticGuard Diagnostics Engine
Detects all known Elasticsearch issues across cluster, nodes, indices, shards
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import structlog

from core.es_client import ElasticsearchClient

logger = structlog.get_logger()


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(str, Enum):
    CLUSTER = "cluster"
    NODE = "node"
    INDEX = "index"
    SHARD = "shard"
    PERFORMANCE = "performance"
    DISK = "disk"
    MEMORY = "memory"
    NETWORK = "network"
    SECURITY = "security"
    CONFIGURATION = "configuration"


@dataclass
class DiagnosticIssue:
    id: str
    category: IssueCategory
    severity: Severity
    title: str
    description: str
    affected_resource: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    solution_summary: str = ""
    elasticsearch_apis: List[Dict] = field(default_factory=list)  # {method, path, body, description}
    cli_commands: List[str] = field(default_factory=list)
    requires_approval: bool = True
    docs_url: str = ""


@dataclass
class DiagnosticsReport:
    cluster_id: str
    cluster_name: str
    es_version: str
    health_status: str  # green / yellow / red
    issues: List[DiagnosticIssue] = field(default_factory=list)
    node_count: int = 0
    index_count: int = 0
    shard_count: int = 0
    unassigned_shards: int = 0
    raw_data: Dict = field(default_factory=dict)

    @property
    def has_critical(self) -> bool:
        return any(i.severity == Severity.CRITICAL for i in self.issues)

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class DiagnosticsEngine:
    """
    Comprehensive Elasticsearch diagnostics engine.
    Checks cluster, nodes, indices, shards for all known issue patterns.
    """

    def __init__(self, client: ElasticsearchClient):
        self.client = client

    async def run_full_diagnostics(self, cluster_id: str) -> DiagnosticsReport:
        """Run all diagnostic checks and return a full report."""
        logger.info("Starting full diagnostics", cluster_id=cluster_id)

        # Gather all raw data in parallel
        import asyncio
        results = await asyncio.gather(
            self.client.get("/"),
            self.client.cluster_health(),
            self.client.cluster_stats(),
            self.client.nodes_stats(),
            self.client.cat_indices(),
            self.client.cat_shards(),
            self.client.cat_nodes(),
            self.client.cat_allocation(),
            self.client.cat_thread_pool(),
            self.client.cluster_settings(),
            self.client.cluster_pending_tasks(),
            return_exceptions=True,
        )

        (
            info, health, cluster_stats, nodes_stats,
            cat_indices, cat_shards, cat_nodes,
            cat_allocation, thread_pool, cluster_settings,
            pending_tasks,
        ) = results

        # Handle exceptions in gathered results
        def safe(r, default={}):
            return r if not isinstance(r, Exception) else default

        info = safe(info)
        health = safe(health)
        cluster_stats = safe(cluster_stats)
        nodes_stats = safe(nodes_stats)
        cat_indices = safe(cat_indices, [])
        cat_shards = safe(cat_shards, [])
        cat_nodes = safe(cat_nodes, [])
        cat_allocation = safe(cat_allocation, [])
        thread_pool = safe(thread_pool, [])
        cluster_settings = safe(cluster_settings)
        pending_tasks = safe(pending_tasks)

        raw_data = {
            "info": info, "health": health, "cluster_stats": cluster_stats,
            "nodes_stats": nodes_stats, "cat_indices": cat_indices,
            "cat_shards": cat_shards, "cat_nodes": cat_nodes,
            "cat_allocation": cat_allocation, "thread_pool": thread_pool,
            "cluster_settings": cluster_settings, "pending_tasks": pending_tasks,
        }

        report = DiagnosticsReport(
            cluster_id=cluster_id,
            cluster_name=health.get("cluster_name", info.get("cluster_name", "unknown")),
            es_version=info.get("version", {}).get("number", "unknown"),
            health_status=health.get("status", "unknown"),
            node_count=health.get("number_of_nodes", 0),
            index_count=health.get("active_primary_shards", 0),
            shard_count=health.get("active_shards", 0),
            unassigned_shards=health.get("unassigned_shards", 0),
            raw_data=raw_data,
        )

        # Run all diagnostic checks
        issues = []
        issues.extend(self._check_cluster_health(health))
        issues.extend(self._check_unassigned_shards(health, cat_shards))
        issues.extend(self._check_node_performance(cat_nodes, nodes_stats))
        issues.extend(self._check_disk_watermarks(cat_allocation, cat_nodes, nodes_stats, cluster_settings))
        issues.extend(self._check_jvm_heap(cat_nodes, nodes_stats))
        issues.extend(self._check_circuit_breakers(nodes_stats))
        issues.extend(self._check_thread_pools(thread_pool, nodes_stats))
        issues.extend(self._check_index_issues(cat_indices, nodes_stats))
        issues.extend(self._check_shard_balance(cat_allocation, cat_shards, cat_nodes))
        issues.extend(self._check_pending_tasks(pending_tasks))
        issues.extend(self._check_recovery(cat_shards))
        issues.extend(self._check_large_indices(cat_indices))
        issues.extend(self._check_index_lifecycle(cat_indices))

        # Sort by severity
        severity_order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1,
            Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4
        }
        issues.sort(key=lambda x: severity_order[x.severity])
        report.issues = issues

        logger.info("Diagnostics complete", issues=len(issues), status=report.health_status)
        return report

    # ─── Cluster Health ──────────────────────────────────────────────────────

    def _check_cluster_health(self, health: Dict) -> List[DiagnosticIssue]:
        issues = []
        status = health.get("status", "unknown")

        if status == "red":
            issues.append(DiagnosticIssue(
                id="cluster_health_red",
                category=IssueCategory.CLUSTER,
                severity=Severity.CRITICAL,
                title="Cluster Health is RED",
                description=(
                    f"The cluster is RED which means one or more PRIMARY shards are unassigned. "
                    f"Active shards: {health.get('active_shards', 0)}, "
                    f"Unassigned: {health.get('unassigned_shards', 0)}, "
                    f"Primary unassigned: {health.get('unassigned_primary_shards', 0)}. "
                    "Data is currently unavailable for affected indices."
                ),
                affected_resource="cluster",
                metrics={
                    "active_shards": health.get("active_shards", 0),
                    "unassigned_shards": health.get("unassigned_shards", 0),
                    "unassigned_primary_shards": health.get("unassigned_primary_shards", 0),
                    "relocating_shards": health.get("relocating_shards", 0),
                },
                solution_summary="Identify and fix unassigned primary shards immediately",
                elasticsearch_apis=[
                    {
                        "method": "GET",
                        "path": "/_cluster/allocation/explain",
                        "body": None,
                        "description": "Explain why shards are unassigned"
                    },
                    {
                        "method": "POST",
                        "path": "/_cluster/reroute?retry_failed=true",
                        "body": None,
                        "description": "Retry failed shard allocations"
                    }
                ],
                docs_url="https://www.elastic.co/guide/en/elasticsearch/reference/current/red-yellow-cluster-status.html"
            ))

        elif status == "yellow":
            issues.append(DiagnosticIssue(
                id="cluster_health_yellow",
                category=IssueCategory.CLUSTER,
                severity=Severity.HIGH,
                title="Cluster Health is YELLOW",
                description=(
                    f"The cluster is YELLOW which means replica shards are unassigned. "
                    f"Primary shards are all active, but no replicas exist for some. "
                    f"Unassigned shards: {health.get('unassigned_shards', 0)}. "
                    "Data is available but cluster has no redundancy for affected indices."
                ),
                affected_resource="cluster",
                metrics={
                    "unassigned_shards": health.get("unassigned_shards", 0),
                    "active_primary_shards": health.get("active_primary_shards", 0),
                },
                solution_summary="Fix unassigned replica shards or reduce replica count if single-node",
                elasticsearch_apis=[
                    {
                        "method": "GET",
                        "path": "/_cluster/allocation/explain",
                        "body": None,
                        "description": "Explain why replica shards are unassigned"
                    },
                    {
                        "method": "PUT",
                        "path": "/_all/_settings",
                        "body": {"index": {"number_of_replicas": 0}},
                        "description": "Set replicas to 0 (single-node clusters only)"
                    }
                ],
            ))

        if health.get("timed_out", False):
            issues.append(DiagnosticIssue(
                id="cluster_health_timeout",
                category=IssueCategory.CLUSTER,
                severity=Severity.HIGH,
                title="Cluster Health Check Timed Out",
                description="The cluster health check timed out, indicating the cluster is under heavy load or has a split-brain scenario.",
                affected_resource="cluster",
                metrics={},
                solution_summary="Investigate cluster load, GC pressure, and network connectivity between nodes",
            ))

        return issues

    # ─── Unassigned Shards ───────────────────────────────────────────────────

    def _check_unassigned_shards(self, health: Dict, cat_shards: list) -> List[DiagnosticIssue]:
        issues = []
        unassigned = [s for s in cat_shards if s.get("state") == "UNASSIGNED"]

        if not unassigned:
            return issues

        # Group by reason
        by_reason = {}
        for shard in unassigned:
            reason = shard.get("unassigned.reason", "UNKNOWN")
            by_reason.setdefault(reason, []).append(shard)

        for reason, shards in by_reason.items():
            affected = ", ".join(set(s.get("index", "?") for s in shards[:5]))
            if len(shards) > 5:
                affected += f" and {len(shards) - 5} more"

            reason_explanations = {
                "NODE_LEFT": "shards were on a node that left the cluster",
                "ALLOCATION_FAILED": "shard allocation has repeatedly failed",
                "INDEX_CREATED": "newly created index has unassigned shards (normal briefly)",
                "CLUSTER_RECOVERED": "cluster recovered from restart",
                "REINITIALIZED": "shard re-initialization failed",
                "DANGLING_INDEX_IMPORTED": "dangling index was imported",
                "NO_ATTEMPT": "allocation has not been attempted yet",
            }

            explanation = reason_explanations.get(reason, f"reason code: {reason}")

            severity = Severity.CRITICAL if any(s.get("prirep") == "p" for s in shards) else Severity.HIGH

            issues.append(DiagnosticIssue(
                id=f"unassigned_shard_{reason.lower()}",
                category=IssueCategory.SHARD,
                severity=severity,
                title=f"Unassigned Shards: {reason}",
                description=(
                    f"{len(shards)} shard(s) are unassigned because {explanation}. "
                    f"Affected indices: {affected}."
                ),
                affected_resource=affected,
                metrics={"count": len(shards), "reason": reason, "shards": [
                    {"index": s.get("index"), "shard": s.get("shard"), "prirep": s.get("prirep")}
                    for s in shards[:10]
                ]},
                solution_summary=self._unassigned_shard_solution(reason),
                elasticsearch_apis=[
                    {
                        "method": "GET",
                        "path": "/_cluster/allocation/explain",
                        "body": {
                            "index": shards[0].get("index"),
                            "shard": int(shards[0].get("shard", 0)),
                            "primary": shards[0].get("prirep") == "p"
                        },
                        "description": f"Explain allocation failure for {shards[0].get('index')}"
                    },
                    {
                        "method": "POST",
                        "path": "/_cluster/reroute?retry_failed=true",
                        "body": None,
                        "description": "Retry all failed shard allocations"
                    }
                ],
            ))

        return issues

    def _unassigned_shard_solution(self, reason: str) -> str:
        solutions = {
            "NODE_LEFT": "Add the missing node back or wait for re-allocation. Run reroute to retry.",
            "ALLOCATION_FAILED": "Check node disk space, JVM heap. Run reroute with retry_failed=true.",
            "NO_ATTEMPT": "Run cluster reroute to trigger allocation attempt.",
            "REINITIALIZED": "Check node logs for errors. Try reroute to force re-allocation.",
        }
        return solutions.get(reason, "Run /_cluster/allocation/explain to diagnose the specific cause.")

    # ─── Node Performance ────────────────────────────────────────────────────

    def _check_node_performance(self, cat_nodes: list, nodes_stats: Dict) -> List[DiagnosticIssue]:
        issues = []

        for node in cat_nodes:
            name = node.get("name", "unknown")

            # CPU check
            cpu = self._parse_float(node.get("cpu", "0"))
            if cpu >= 95:
                issues.append(DiagnosticIssue(
                    id=f"cpu_critical_{name}",
                    category=IssueCategory.PERFORMANCE,
                    severity=Severity.CRITICAL,
                    title=f"Critical CPU Usage on Node {name}",
                    description=f"Node '{name}' CPU is at {cpu:.1f}%. The node is overloaded and may cause search/indexing timeouts.",
                    affected_resource=f"node/{name}",
                    metrics={"cpu_percent": cpu, "load_1m": node.get("load_1m", "?")},
                    solution_summary="Reduce indexing rate, scale up node, or add more nodes to the cluster",
                    elasticsearch_apis=[
                        {"method": "GET", "path": f"/_nodes/{name}/hot_threads", "body": None,
                         "description": "Identify hot threads on this node"},
                        {"method": "GET", "path": f"/_nodes/{name}/stats/thread_pool", "body": None,
                         "description": "Check thread pool rejection counts"},
                    ],
                    cli_commands=[
                        f"# SSH to node {name} and check processes:",
                        "top -b -n1 | head -20",
                        "jstack <elasticsearch_pid> | grep -A 5 'BLOCKED\\|WAITING'"
                    ],
                    requires_approval=False,
                ))
            elif cpu >= 80:
                issues.append(DiagnosticIssue(
                    id=f"cpu_high_{name}",
                    category=IssueCategory.PERFORMANCE,
                    severity=Severity.HIGH,
                    title=f"High CPU Usage on Node {name}",
                    description=f"Node '{name}' CPU is at {cpu:.1f}%. Performance may degrade if load continues.",
                    affected_resource=f"node/{name}",
                    metrics={"cpu_percent": cpu},
                    solution_summary="Monitor for sustained CPU spikes, check for expensive queries or bulk indexing",
                    requires_approval=False,
                ))

            # RAM check
            ram = self._parse_float(node.get("ramPercent", "0"))
            if ram >= 95:
                issues.append(DiagnosticIssue(
                    id=f"ram_critical_{name}",
                    category=IssueCategory.MEMORY,
                    severity=Severity.HIGH,
                    title=f"Critical RAM Usage on Node {name}",
                    description=f"Node '{name}' RAM is at {ram:.1f}%. Risk of OOM errors and JVM pressure.",
                    affected_resource=f"node/{name}",
                    metrics={"ram_percent": ram},
                    solution_summary="Reduce heap size, disable field data caching, or add RAM to the node",
                    cli_commands=["free -h", "cat /proc/meminfo | grep -E 'MemTotal|MemFree|Cached'"],
                    requires_approval=False,
                ))

        return issues

    # ─── Disk Watermarks ─────────────────────────────────────────────────────

    def _check_disk_watermarks(self, cat_allocation: list, cat_nodes: list, nodes_stats: Dict, cluster_settings: Dict) -> List[DiagnosticIssue]:
        issues = []

        # Get watermark settings
        transient = cluster_settings.get("transient", {})
        persistent = cluster_settings.get("persistent", {})
        defaults = cluster_settings.get("defaults", {})

        def get_watermark(key):
            for settings_level in [transient, persistent, defaults]:
                val = settings_level.get("cluster", {}).get("routing", {}).get("allocation", {}).get("disk", {}).get(key)
                if val:
                    return val
            return None

        low_wm = get_watermark("watermark.low") or "85%"
        high_wm = get_watermark("watermark.high") or "90%"
        flood_wm = get_watermark("watermark.flood_stage") or "95%"

        def parse_wm(wm_str: str) -> float:
            if isinstance(wm_str, str) and wm_str.endswith("%"):
                return float(wm_str.rstrip("%"))
            return 85.0

        low_thresh = parse_wm(str(low_wm))
        high_thresh = parse_wm(str(high_wm))
        flood_thresh = parse_wm(str(flood_wm))

        for alloc in cat_allocation:
            node = alloc.get("node", "unknown")
            disk_percent_str = alloc.get("disk.percent", "0")
            disk_percent = self._parse_float(disk_percent_str)
            disk_used = alloc.get("disk.used", "?")
            disk_total = alloc.get("disk.total", "?")
            disk_avail = alloc.get("disk.avail", "?")

            if disk_percent >= flood_thresh:
                issues.append(DiagnosticIssue(
                    id=f"disk_flood_{node}",
                    category=IssueCategory.DISK,
                    severity=Severity.CRITICAL,
                    title=f"Disk FLOOD STAGE on Node {node}",
                    description=(
                        f"Node '{node}' disk usage is {disk_percent:.1f}% (flood_stage threshold: {flood_thresh}%). "
                        f"Used: {disk_used} / {disk_total}. "
                        "ALL indices on this node have been set to READ-ONLY. No new data can be indexed."
                    ),
                    affected_resource=f"node/{node}",
                    metrics={"disk_percent": disk_percent, "disk_used": disk_used, "disk_avail": disk_avail},
                    solution_summary="Free disk space immediately, then reset read-only block on indices",
                    elasticsearch_apis=[
                        {
                            "method": "PUT",
                            "path": "/_all/_settings",
                            "body": {"index.blocks.read_only_allow_delete": None},
                            "description": "Remove read-only block from all indices (after freeing disk space)"
                        },
                        {
                            "method": "PUT",
                            "path": "/_cluster/settings",
                            "body": {"transient": {"cluster.routing.allocation.disk.watermark.flood_stage": "97%"}},
                            "description": "Temporarily raise flood stage watermark (emergency only)"
                        }
                    ],
                    cli_commands=[
                        f"# SSH to node {node}:",
                        "df -h /var/lib/elasticsearch",
                        "du -sh /var/lib/elasticsearch/indices/* | sort -rh | head -10",
                        "# Delete old snapshots, logs, or add disk",
                    ],
                ))

            elif disk_percent >= high_thresh:
                issues.append(DiagnosticIssue(
                    id=f"disk_high_{node}",
                    category=IssueCategory.DISK,
                    severity=Severity.HIGH,
                    title=f"High Disk Usage on Node {node}",
                    description=(
                        f"Node '{node}' disk usage is {disk_percent:.1f}% (high watermark: {high_thresh}%). "
                        f"Elasticsearch will attempt to move shards away from this node. "
                        f"Available: {disk_avail}."
                    ),
                    affected_resource=f"node/{node}",
                    metrics={"disk_percent": disk_percent, "disk_avail": disk_avail},
                    solution_summary="Free disk space or add a new node. Consider ILM to delete old indices.",
                    elasticsearch_apis=[
                        {
                            "method": "GET",
                            "path": "/_cat/indices?s=store.size:desc&h=index,health,docs.count,store.size&format=json",
                            "body": None,
                            "description": "Find largest indices by disk size"
                        },
                    ],
                ))

            elif disk_percent >= low_thresh:
                issues.append(DiagnosticIssue(
                    id=f"disk_low_wm_{node}",
                    category=IssueCategory.DISK,
                    severity=Severity.MEDIUM,
                    title=f"Disk Approaching Watermark on Node {node}",
                    description=(
                        f"Node '{node}' disk usage is {disk_percent:.1f}% (low watermark: {low_thresh}%). "
                        "Elasticsearch will not allocate new shards to this node."
                    ),
                    affected_resource=f"node/{node}",
                    metrics={"disk_percent": disk_percent},
                    solution_summary="Plan for disk expansion or index cleanup before reaching high watermark",
                    requires_approval=False,
                ))

        return issues

    # ─── JVM Heap ────────────────────────────────────────────────────────────

    def _check_jvm_heap(self, cat_nodes: list, nodes_stats: Dict) -> List[DiagnosticIssue]:
        issues = []
        nodes_data = nodes_stats.get("nodes", {})

        for node_id, node_data in nodes_data.items():
            name = node_data.get("name", node_id)
            jvm = node_data.get("jvm", {})
            mem = jvm.get("mem", {})

            heap_used_pct = mem.get("heap_used_percent", 0)
            heap_used = mem.get("heap_used_in_bytes", 0)
            heap_max = mem.get("heap_max_in_bytes", 1)
            heap_used_gb = heap_used / (1024**3)
            heap_max_gb = heap_max / (1024**3)

            gc_collectors = jvm.get("gc", {}).get("collectors", {})
            old_gc = gc_collectors.get("old", {})
            young_gc = gc_collectors.get("young", {})
            old_gc_time_ms = old_gc.get("collection_time_in_millis", 0)
            old_gc_count = old_gc.get("collection_count", 0)

            if heap_used_pct >= 95:
                issues.append(DiagnosticIssue(
                    id=f"jvm_critical_{name}",
                    category=IssueCategory.MEMORY,
                    severity=Severity.CRITICAL,
                    title=f"Critical JVM Heap on Node {name}",
                    description=(
                        f"Node '{name}' JVM heap is {heap_used_pct}% used "
                        f"({heap_used_gb:.2f}GB / {heap_max_gb:.2f}GB). "
                        f"Old GC runs: {old_gc_count}, time: {old_gc_time_ms}ms. "
                        "Node may perform full GC and become unresponsive (GC thrashing)."
                    ),
                    affected_resource=f"node/{name}",
                    metrics={
                        "heap_used_pct": heap_used_pct,
                        "heap_used_gb": round(heap_used_gb, 2),
                        "heap_max_gb": round(heap_max_gb, 2),
                        "old_gc_count": old_gc_count,
                        "old_gc_time_ms": old_gc_time_ms,
                    },
                    solution_summary="Clear caches, reduce field data, or increase JVM heap (-Xmx). Avoid exceeding 32GB heap.",
                    elasticsearch_apis=[
                        {
                            "method": "POST",
                            "path": "/_cache/clear",
                            "body": None,
                            "description": "Clear all caches to reduce heap pressure"
                        },
                        {
                            "method": "GET",
                            "path": f"/_nodes/{name}/stats/breaker",
                            "body": None,
                            "description": "Check circuit breaker status"
                        },
                    ],
                    cli_commands=[
                        f"# On node {name}:",
                        "# Check current heap in elasticsearch.yml or jvm.options:",
                        "grep -E 'Xmx|Xms' /etc/elasticsearch/jvm.options",
                        "# Recommended: set Xms=Xmx, max 26-30GB for compressed OOPs",
                    ],
                ))

            elif heap_used_pct >= 85:
                issues.append(DiagnosticIssue(
                    id=f"jvm_high_{name}",
                    category=IssueCategory.MEMORY,
                    severity=Severity.HIGH,
                    title=f"High JVM Heap on Node {name}",
                    description=(
                        f"Node '{name}' JVM heap is {heap_used_pct}% used. "
                        "Monitor closely; heavy GC may impact performance."
                    ),
                    affected_resource=f"node/{name}",
                    metrics={"heap_used_pct": heap_used_pct, "old_gc_count": old_gc_count},
                    solution_summary="Clear caches, check for field data accumulation, monitor GC activity",
                    elasticsearch_apis=[
                        {
                            "method": "POST",
                            "path": "/_cache/clear",
                            "body": None,
                            "description": "Clear all caches"
                        }
                    ],
                ))

        return issues

    # ─── Circuit Breakers ────────────────────────────────────────────────────

    def _check_circuit_breakers(self, nodes_stats: Dict) -> List[DiagnosticIssue]:
        issues = []
        nodes_data = nodes_stats.get("nodes", {})

        for node_id, node_data in nodes_data.items():
            name = node_data.get("name", node_id)
            breakers = node_data.get("breakers", {})

            tripped_breakers = []
            for breaker_name, breaker_data in breakers.items():
                tripped = breaker_data.get("tripped", 0)
                if tripped > 0:
                    limit_pct = breaker_data.get("overhead", 1.0)
                    estimated = breaker_data.get("estimated_size_in_bytes", 0)
                    limit = breaker_data.get("limit_size_in_bytes", 1)
                    usage_pct = (estimated / limit * 100) if limit > 0 else 0
                    tripped_breakers.append({
                        "name": breaker_name,
                        "tripped": tripped,
                        "usage_pct": round(usage_pct, 1),
                    })

            if tripped_breakers:
                issues.append(DiagnosticIssue(
                    id=f"circuit_breaker_{name}",
                    category=IssueCategory.MEMORY,
                    severity=Severity.HIGH,
                    title=f"Circuit Breakers Tripped on Node {name}",
                    description=(
                        f"Node '{name}' has {len(tripped_breakers)} tripped circuit breaker(s): "
                        + ", ".join(f"{b['name']} ({b['tripped']} trips, {b['usage_pct']}% used)"
                                    for b in tripped_breakers)
                        + ". This causes HTTP 429 errors for queries that would exceed memory limits."
                    ),
                    affected_resource=f"node/{name}",
                    metrics={"tripped_breakers": tripped_breakers},
                    solution_summary="Reduce query/aggregation complexity, clear field data cache, increase breaker limits",
                    elasticsearch_apis=[
                        {
                            "method": "POST",
                            "path": "/_cache/clear?fielddata=true",
                            "body": None,
                            "description": "Clear fielddata cache to free memory"
                        },
                        {
                            "method": "PUT",
                            "path": "/_cluster/settings",
                            "body": {"transient": {"indices.breaker.fielddata.limit": "60%"}},
                            "description": "Reduce fielddata circuit breaker limit (forces eviction earlier)"
                        }
                    ],
                ))

        return issues

    # ─── Thread Pools ────────────────────────────────────────────────────────

    def _check_thread_pools(self, thread_pool: list, nodes_stats: Dict) -> List[DiagnosticIssue]:
        issues = []
        nodes_data = nodes_stats.get("nodes", {})

        for node_id, node_data in nodes_data.items():
            name = node_data.get("name", node_id)
            pools = node_data.get("thread_pool", {})

            for pool_name, pool_data in pools.items():
                rejected = pool_data.get("rejected", 0)
                queue = pool_data.get("queue", 0)
                active = pool_data.get("active", 0)

                if rejected > 0:
                    severity = Severity.HIGH if rejected > 100 else Severity.MEDIUM
                    issues.append(DiagnosticIssue(
                        id=f"thread_pool_rejected_{name}_{pool_name}",
                        category=IssueCategory.PERFORMANCE,
                        severity=severity,
                        title=f"Thread Pool Rejections: {pool_name} on {name}",
                        description=(
                            f"Thread pool '{pool_name}' on node '{name}' has rejected {rejected} tasks. "
                            f"Queue size: {queue}, Active threads: {active}. "
                            "Rejections cause 429 errors and data loss for indexing operations."
                        ),
                        affected_resource=f"node/{name}/thread_pool/{pool_name}",
                        metrics={
                            "rejected": rejected, "queue": queue, "active": active, "pool": pool_name
                        },
                        solution_summary=f"Reduce {pool_name} load, increase queue size, or scale nodes",
                        elasticsearch_apis=[
                            {
                                "method": "PUT",
                                "path": "/_cluster/settings",
                                "body": {"transient": {f"thread_pool.{pool_name}.queue_size": 1000}},
                                "description": f"Increase {pool_name} thread pool queue size"
                            }
                        ],
                    ))

        return issues

    # ─── Index Issues ────────────────────────────────────────────────────────

    def _check_index_issues(self, cat_indices: list, nodes_stats: Dict) -> List[DiagnosticIssue]:
        issues = []

        for idx in cat_indices:
            index_name = idx.get("index", "?")
            health = idx.get("health", "green")
            docs_count = self._parse_int(idx.get("docs.count", "0"))
            docs_deleted = self._parse_int(idx.get("docs.deleted", "0"))
            store_size = idx.get("store.size", "0b")
            pri = self._parse_int(idx.get("pri", "0"))
            rep = self._parse_int(idx.get("rep", "0"))

            # High delete ratio — causes merge pressure
            if docs_count > 0 and docs_deleted > 0:
                delete_ratio = docs_deleted / max(docs_count, 1)
                if delete_ratio > 0.5 and docs_count > 10000:
                    issues.append(DiagnosticIssue(
                        id=f"index_delete_ratio_{index_name}",
                        category=IssueCategory.INDEX,
                        severity=Severity.MEDIUM,
                        title=f"High Delete Ratio in Index {index_name}",
                        description=(
                            f"Index '{index_name}' has {docs_deleted:,} deleted docs vs {docs_count:,} live docs "
                            f"(ratio: {delete_ratio:.1%}). This wastes disk space and slows down searches."
                        ),
                        affected_resource=f"index/{index_name}",
                        metrics={"docs_count": docs_count, "docs_deleted": docs_deleted, "delete_ratio": delete_ratio},
                        solution_summary="Force merge the index to reclaim disk space from deleted documents",
                        elasticsearch_apis=[
                            {
                                "method": "POST",
                                "path": f"/{index_name}/_forcemerge?max_num_segments=1",
                                "body": None,
                                "description": f"Force merge {index_name} to 1 segment (only for closed/static indices)"
                            }
                        ],
                    ))

            # Too many shards per index relative to size
            store_gb = self._parse_store_size_gb(store_size)
            if pri > 0 and store_gb > 0:
                shard_size_gb = store_gb / pri
                if shard_size_gb < 0.001 and pri > 5:  # tiny shards
                    issues.append(DiagnosticIssue(
                        id=f"index_overshareded_{index_name}",
                        category=IssueCategory.INDEX,
                        severity=Severity.LOW,
                        title=f"Over-Sharded Index: {index_name}",
                        description=(
                            f"Index '{index_name}' has {pri} primary shards but only {store_gb:.3f}GB total. "
                            f"Average shard size: {shard_size_gb*1000:.1f}MB. "
                            "Recommendation: 10-50GB per shard for optimal performance."
                        ),
                        affected_resource=f"index/{index_name}",
                        metrics={"primary_shards": pri, "store_gb": store_gb, "avg_shard_size_gb": shard_size_gb},
                        solution_summary="Reduce shard count by shrinking or reindexing with fewer shards",
                        elasticsearch_apis=[
                            {
                                "method": "POST",
                                "path": f"/{index_name}/_shrink/shrunk-{index_name}",
                                "body": {"settings": {"index.number_of_shards": max(1, pri // 2)}},
                                "description": f"Shrink {index_name} to {max(1, pri // 2)} shards"
                            }
                        ],
                    ))

                elif shard_size_gb > 60:  # oversized shards
                    issues.append(DiagnosticIssue(
                        id=f"index_large_shards_{index_name}",
                        category=IssueCategory.INDEX,
                        severity=Severity.MEDIUM,
                        title=f"Oversized Shards in Index {index_name}",
                        description=(
                            f"Index '{index_name}' average shard size is {shard_size_gb:.1f}GB "
                            f"(total: {store_gb:.1f}GB across {pri} shards). "
                            "Large shards slow rebalancing and recovery."
                        ),
                        affected_resource=f"index/{index_name}",
                        metrics={"avg_shard_size_gb": shard_size_gb, "total_gb": store_gb},
                        solution_summary="Reindex with more shards or use ILM rollover to manage index size",
                        elasticsearch_apis=[
                            {
                                "method": "POST",
                                "path": f"/{index_name}/_split/split-{index_name}",
                                "body": {"settings": {"index.number_of_shards": pri * 2}},
                                "description": f"Split index to {pri * 2} shards"
                            }
                        ],
                    ))

        return issues

    # ─── Shard Balance ───────────────────────────────────────────────────────

    def _check_shard_balance(self, cat_allocation: list, cat_shards: list, cat_nodes: list) -> List[DiagnosticIssue]:
        issues = []

        if len(cat_allocation) < 2:
            return issues

        shard_counts = {a.get("node"): self._parse_int(a.get("shards", "0")) for a in cat_allocation}
        if not shard_counts:
            return issues

        max_shards = max(shard_counts.values())
        min_shards = min(shard_counts.values())
        avg_shards = sum(shard_counts.values()) / len(shard_counts)

        if max_shards > 0 and (max_shards - min_shards) / max(avg_shards, 1) > 0.5:
            heaviest_node = max(shard_counts, key=shard_counts.get)
            lightest_node = min(shard_counts, key=shard_counts.get)

            issues.append(DiagnosticIssue(
                id="shard_imbalance",
                category=IssueCategory.SHARD,
                severity=Severity.MEDIUM,
                title="Shard Imbalance Across Nodes",
                description=(
                    f"Shards are unevenly distributed. Node '{heaviest_node}' has {max_shards} shards "
                    f"while '{lightest_node}' has only {min_shards} shards. "
                    "This causes hot spots and uneven resource usage."
                ),
                affected_resource="cluster",
                metrics={"distribution": shard_counts, "max": max_shards, "min": min_shards},
                solution_summary="Trigger a cluster reroute to rebalance, or adjust rebalancing throttle settings",
                elasticsearch_apis=[
                    {
                        "method": "POST",
                        "path": "/_cluster/reroute",
                        "body": None,
                        "description": "Trigger shard rebalancing"
                    },
                    {
                        "method": "PUT",
                        "path": "/_cluster/settings",
                        "body": {"transient": {"cluster.routing.rebalance.enable": "all"}},
                        "description": "Enable all rebalancing"
                    }
                ],
            ))

        return issues

    # ─── Pending Tasks ───────────────────────────────────────────────────────

    def _check_pending_tasks(self, pending_tasks: Dict) -> List[DiagnosticIssue]:
        issues = []
        tasks = pending_tasks.get("tasks", [])

        if len(tasks) > 100:
            issues.append(DiagnosticIssue(
                id="pending_tasks_high",
                category=IssueCategory.CLUSTER,
                severity=Severity.HIGH,
                title=f"High Pending Task Queue ({len(tasks)} tasks)",
                description=(
                    f"Cluster master has {len(tasks)} pending tasks. "
                    "This indicates the master is overloaded or cluster state changes are overwhelming it."
                ),
                affected_resource="cluster/master",
                metrics={"pending_tasks": len(tasks)},
                solution_summary="Reduce operations, check master node CPU/memory, avoid bulk mapping changes",
                requires_approval=False,
            ))
        elif len(tasks) > 20:
            issues.append(DiagnosticIssue(
                id="pending_tasks_medium",
                category=IssueCategory.CLUSTER,
                severity=Severity.MEDIUM,
                title=f"Elevated Pending Task Queue ({len(tasks)} tasks)",
                description=f"Cluster master has {len(tasks)} pending tasks. Monitor for increase.",
                affected_resource="cluster/master",
                metrics={"pending_tasks": len(tasks)},
                solution_summary="Monitor trend; if growing, investigate master node load",
                requires_approval=False,
            ))

        return issues

    # ─── Recovery ────────────────────────────────────────────────────────────

    def _check_recovery(self, cat_shards: list) -> List[DiagnosticIssue]:
        issues = []
        recovering = [s for s in cat_shards if s.get("state") in ["INITIALIZING", "RELOCATING"]]

        if len(recovering) > 50:
            issues.append(DiagnosticIssue(
                id="mass_shard_recovery",
                category=IssueCategory.SHARD,
                severity=Severity.MEDIUM,
                title=f"Mass Shard Recovery in Progress ({len(recovering)} shards)",
                description=(
                    f"{len(recovering)} shards are currently recovering or relocating. "
                    "This puts high I/O and network load on the cluster."
                ),
                affected_resource="cluster",
                metrics={"recovering_shards": len(recovering)},
                solution_summary="Throttle recovery speed if impacting search performance",
                elasticsearch_apis=[
                    {
                        "method": "PUT",
                        "path": "/_cluster/settings",
                        "body": {
                            "transient": {
                                "indices.recovery.max_bytes_per_sec": "50mb",
                                "cluster.routing.allocation.node_concurrent_recoveries": 2,
                            }
                        },
                        "description": "Throttle recovery to reduce cluster load"
                    }
                ],
            ))

        return issues

    # ─── Large Indices ───────────────────────────────────────────────────────

    def _check_large_indices(self, cat_indices: list) -> List[DiagnosticIssue]:
        issues = []

        for idx in cat_indices:
            index_name = idx.get("index", "?")
            store_size = idx.get("store.size", "0b")
            store_gb = self._parse_store_size_gb(store_size)

            if store_gb > 500:
                issues.append(DiagnosticIssue(
                    id=f"index_very_large_{index_name}",
                    category=IssueCategory.INDEX,
                    severity=Severity.MEDIUM,
                    title=f"Very Large Index: {index_name} ({store_size})",
                    description=(
                        f"Index '{index_name}' is {store_gb:.1f}GB. "
                        "Extremely large indices are hard to rebalance, backup, and recover from."
                    ),
                    affected_resource=f"index/{index_name}",
                    metrics={"store_gb": store_gb},
                    solution_summary="Use ILM rollover to keep indices under 50GB, or split into time-based indices",
                    elasticsearch_apis=[
                        {
                            "method": "PUT",
                            "path": f"/{index_name}/_settings",
                            "body": {
                                "index": {
                                    "lifecycle.name": "my-ilm-policy",
                                    "lifecycle.rollover_alias": index_name
                                }
                            },
                            "description": "Apply ILM policy to this index"
                        }
                    ],
                ))

        return issues

    # ─── Index Lifecycle ─────────────────────────────────────────────────────

    def _check_index_lifecycle(self, cat_indices: list) -> List[DiagnosticIssue]:
        issues = []

        # Find indices without ILM (heuristic: time-based names with no lifecycle)
        # This is advisory only
        old_indices = []
        import re
        date_pattern = re.compile(r'[-_](\d{4}[.\-]\d{2}[.\-]\d{2}|\d{4}[.\-]\d{2})')

        for idx in cat_indices:
            index_name = idx.get("index", "?")
            if index_name.startswith("."):
                continue
            if date_pattern.search(index_name):
                store_gb = self._parse_store_size_gb(idx.get("store.size", "0b"))
                if store_gb > 5:
                    old_indices.append(index_name)

        if len(old_indices) > 20:
            issues.append(DiagnosticIssue(
                id="no_ilm_policy",
                category=IssueCategory.CONFIGURATION,
                severity=Severity.LOW,
                title=f"Many Time-Based Indices Without ILM ({len(old_indices)} detected)",
                description=(
                    f"Found {len(old_indices)} time-based indices (e.g., {', '.join(old_indices[:3])}). "
                    "Without ILM, old indices accumulate and waste disk space."
                ),
                affected_resource="cluster/indices",
                metrics={"count": len(old_indices)},
                solution_summary="Set up Index Lifecycle Management (ILM) to auto-rollover and delete old data",
                requires_approval=False,
                docs_url="https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html"
            ))

        return issues

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _parse_float(self, value) -> float:
        try:
            return float(str(value).rstrip("%"))
        except (ValueError, TypeError):
            return 0.0

    def _parse_int(self, value) -> int:
        try:
            return int(str(value).replace(",", ""))
        except (ValueError, TypeError):
            return 0

    def _parse_store_size_gb(self, size_str: str) -> float:
        """Parse ES size strings like '10.5gb', '512mb', '1.2tb' to GB."""
        if not size_str:
            return 0.0
        size_str = str(size_str).lower().strip()
        try:
            if size_str.endswith("tb"):
                return float(size_str[:-2]) * 1024
            elif size_str.endswith("gb"):
                return float(size_str[:-2])
            elif size_str.endswith("mb"):
                return float(size_str[:-2]) / 1024
            elif size_str.endswith("kb"):
                return float(size_str[:-2]) / (1024 * 1024)
            elif size_str.endswith("b"):
                return float(size_str[:-1]) / (1024 ** 3)
        except ValueError:
            pass
        return 0.0
