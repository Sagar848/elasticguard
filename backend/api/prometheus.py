"""
Prometheus metrics exporter for Elasticsearch cluster metrics.
Allows Grafana to scrape ElasticGuard for dashboards.
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
import time
import structlog

from core.es_client import _connections

logger = structlog.get_logger()

prometheus_router = APIRouter()


@prometheus_router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """
    Expose cluster metrics in Prometheus text format.
    Add this to your prometheus.yml:

    scrape_configs:
      - job_name: elasticguard
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: /metrics/prometheus/metrics
    """
    lines = [
        "# HELP elasticguard_up ElasticGuard is running",
        "# TYPE elasticguard_up gauge",
        f"elasticguard_up 1",
        "",
        "# HELP elasticguard_connected_clusters Number of connected clusters",
        "# TYPE elasticguard_connected_clusters gauge",
        f"elasticguard_connected_clusters {len(_connections)}",
        "",
    ]

    for cluster_id, client in list(_connections.items()):
        try:
            import asyncio
            health, nodes_stats = await asyncio.gather(
                client.cluster_health(),
                client.nodes_stats(),
                return_exceptions=True,
            )

            label = f'cluster="{cluster_id}"'

            if not isinstance(health, Exception):
                status_val = {"green": 0, "yellow": 1, "red": 2}.get(health.get("status", ""), 3)
                lines += [
                    f"# HELP elasticguard_cluster_status Cluster health (0=green,1=yellow,2=red)",
                    f"# TYPE elasticguard_cluster_status gauge",
                    f'elasticguard_cluster_status{{{label}}} {status_val}',
                    f'elasticguard_cluster_active_shards{{{label}}} {health.get("active_shards", 0)}',
                    f'elasticguard_cluster_unassigned_shards{{{label}}} {health.get("unassigned_shards", 0)}',
                    f'elasticguard_cluster_relocating_shards{{{label}}} {health.get("relocating_shards", 0)}',
                    f'elasticguard_cluster_nodes{{{label}}} {health.get("number_of_nodes", 0)}',
                    "",
                ]

            if not isinstance(nodes_stats, Exception):
                for node_id, nd in nodes_stats.get("nodes", {}).items():
                    name = nd.get("name", node_id).replace('"', '')
                    nlabel = f'{label},node="{name}"'
                    jvm = nd.get("jvm", {}).get("mem", {})
                    os_data = nd.get("os", {})
                    fs = nd.get("fs", {}).get("total", {})
                    gc = nd.get("jvm", {}).get("gc", {}).get("collectors", {})

                    heap_pct = jvm.get("heap_used_percent", 0)
                    cpu_pct = os_data.get("cpu", {}).get("percent", 0)
                    disk_total = fs.get("total_in_bytes", 1)
                    disk_avail = fs.get("available_in_bytes", 0)
                    disk_used_pct = round((disk_total - disk_avail) / disk_total * 100, 1)

                    old_gc_time = gc.get("old", {}).get("collection_time_in_millis", 0)
                    old_gc_count = gc.get("old", {}).get("collection_count", 0)

                    lines += [
                        f'elasticguard_node_heap_percent{{{nlabel}}} {heap_pct}',
                        f'elasticguard_node_cpu_percent{{{nlabel}}} {cpu_pct}',
                        f'elasticguard_node_disk_used_percent{{{nlabel}}} {disk_used_pct}',
                        f'elasticguard_node_jvm_gc_old_count{{{nlabel}}} {old_gc_count}',
                        f'elasticguard_node_jvm_gc_old_time_ms{{{nlabel}}} {old_gc_time}',
                        f'elasticguard_node_heap_used_bytes{{{nlabel}}} {jvm.get("heap_used_in_bytes", 0)}',
                        f'elasticguard_node_heap_max_bytes{{{nlabel}}} {jvm.get("heap_max_in_bytes", 0)}',
                        "",
                    ]

        except Exception as e:
            logger.warning("Prometheus metrics collection failed", cluster=cluster_id, error=str(e))

    lines.append(f"# scrape_time_unix {int(time.time())}")
    return "\n".join(lines)
