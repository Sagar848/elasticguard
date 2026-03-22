"""
Background monitoring scheduler
"""
import asyncio
from typing import Dict
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.es_client import _connections
from core.diagnostics import DiagnosticsEngine
from notifications.manager import notification_manager, ApprovalRequest

logger = structlog.get_logger()


class MonitoringScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._alert_cooldowns: Dict[str, float] = {}

    async def start(self):
        self.scheduler.add_job(
            self._monitor_all_clusters,
            "interval",
            seconds=settings.MONITORING_INTERVAL_SECONDS,
            id="cluster_monitor",
        )
        self.scheduler.start()
        logger.info("Monitoring scheduler started", interval=settings.MONITORING_INTERVAL_SECONDS)

    async def stop(self):
        self.scheduler.shutdown(wait=False)

    async def _monitor_all_clusters(self):
        """Run monitoring checks on all connected clusters."""
        for cluster_id, client in list(_connections.items()):
            try:
                await self._check_cluster(cluster_id, client)
            except Exception as e:
                logger.warning("Monitor check failed", cluster_id=cluster_id, error=str(e))

    async def _check_cluster(self, cluster_id: str, client):
        """Quick health check - send alerts for critical issues."""
        health = await client.cluster_health()
        status = health.get("status", "green")
        unassigned = health.get("unassigned_shards", 0)

        if status == "red":
            alert_key = f"{cluster_id}_red"
            if self._should_alert(alert_key):
                await notification_manager.send_alert(
                    title=f"Cluster {cluster_id} is RED",
                    message=f"Unassigned primary shards: {health.get('unassigned_primary_shards', '?')}. Immediate action required!",
                    severity="critical",
                )

        # Check node thresholds
        try:
            nodes_stats = await client.nodes_stats()
            for node_id, nd in nodes_stats.get("nodes", {}).items():
                name = nd.get("name", node_id)
                heap_pct = nd.get("jvm", {}).get("mem", {}).get("heap_used_percent", 0)
                cpu_pct = nd.get("os", {}).get("cpu", {}).get("percent", 0)
                fs = nd.get("fs", {}).get("total", {})
                disk_used = fs.get("total_in_bytes", 0) - fs.get("available_in_bytes", 0)
                disk_total = max(fs.get("total_in_bytes", 1), 1)
                disk_pct = disk_used / disk_total * 100

                if heap_pct >= settings.ALERT_JVM_THRESHOLD:
                    alert_key = f"{cluster_id}_{name}_jvm"
                    if self._should_alert(alert_key):
                        await notification_manager.send_alert(
                            title=f"High JVM Heap: {name}",
                            message=f"JVM heap at {heap_pct:.1f}% on node {name} in cluster {cluster_id}",
                            severity="high",
                        )

                if cpu_pct >= settings.ALERT_CPU_THRESHOLD:
                    alert_key = f"{cluster_id}_{name}_cpu"
                    if self._should_alert(alert_key):
                        await notification_manager.send_alert(
                            title=f"High CPU: {name}",
                            message=f"CPU at {cpu_pct:.1f}% on node {name} in cluster {cluster_id}",
                            severity="high",
                        )

                if disk_pct >= settings.ALERT_DISK_THRESHOLD:
                    alert_key = f"{cluster_id}_{name}_disk"
                    if self._should_alert(alert_key):
                        await notification_manager.send_alert(
                            title=f"High Disk Usage: {name}",
                            message=f"Disk at {disk_pct:.1f}% on node {name} in cluster {cluster_id}",
                            severity="high",
                        )
        except Exception as e:
            logger.debug("Node stats check failed", error=str(e))

    def _should_alert(self, key: str, cooldown_minutes: int = 30) -> bool:
        """Rate-limit alerts to avoid spam."""
        import time
        now = time.time()
        last = self._alert_cooldowns.get(key, 0)
        if now - last > cooldown_minutes * 60:
            self._alert_cooldowns[key] = now
            return True
        return False
