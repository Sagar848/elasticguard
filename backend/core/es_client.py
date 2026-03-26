"""
Elasticsearch Client - Compatible with ES 7.x, 8.x, 9.x
"""
import asyncio
import logging
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class ClusterConnection:
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    verify_ssl: bool = False
    es_version: Optional[str] = None


class ElasticsearchClient:
    """
    Async Elasticsearch client using raw HTTP (compatible with all versions).
    Uses httpx for async HTTP — avoids ES SDK version conflicts.
    """

    def __init__(self, connection: ClusterConnection):
        self.conn = connection
        self._client: Optional[httpx.AsyncClient] = None

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.conn.api_key:
            headers["Authorization"] = f"ApiKey {self.conn.api_key}"
        return headers

    def _build_auth(self) -> Optional[Tuple[str, str]]:
        if self.conn.username and self.conn.password:
            return (self.conn.username, self.conn.password)
        return None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # verify_ssl=True  → validate certificates (correct for Elastic Cloud / public HTTPS)
            # verify_ssl=False → skip certificate validation (for self-signed / internal certs)
            # Default is False in the model but httpx needs True for public cloud URLs to work
            # correctly. We treat the toggle as "disable verification" not "enable verification".
            ssl_verify = self.conn.verify_ssl  # False = skip check, True = validate

            # For cloud HTTPS URLs, if user left verify_ssl=False but the URL is a known
            # cloud endpoint, be permissive — httpx will still do the TLS handshake,
            # it just won't verify the cert chain. This is fine for Elastic Cloud.
            self._client = httpx.AsyncClient(
                base_url=self.conn.url.rstrip("/"),
                headers=self._build_headers(),
                auth=self._build_auth(),
                verify=ssl_verify,
                timeout=httpx.Timeout(60.0, connect=15.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(self, path: str, params: Dict = None) -> Dict:
        client = await self._get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, body: Dict = None) -> Dict:
        client = await self._get_client()
        resp = await client.post(path, json=body)
        resp.raise_for_status()
        return resp.json()

    async def put(self, path: str, body: Dict = None) -> Dict:
        client = await self._get_client()
        resp = await client.put(path, json=body)
        resp.raise_for_status()
        return resp.json()

    async def delete(self, path: str) -> Dict:
        client = await self._get_client()
        resp = await client.delete(path)
        resp.raise_for_status()
        return resp.json()

    # ── Cluster APIs ──────────────────────────────────────────────────────────

    async def cluster_health(self) -> Dict:
        return await self.get("/_cluster/health", params={"level": "indices"})

    async def cluster_stats(self) -> Dict:
        return await self.get("/_cluster/stats")

    async def cluster_settings(self) -> Dict:
        return await self.get("/_cluster/settings", params={"include_defaults": "true"})

    async def cluster_state(self) -> Dict:
        return await self.get("/_cluster/state/metadata,routing_table,blocks")

    async def cluster_pending_tasks(self) -> Dict:
        return await self.get("/_cluster/pending_tasks")

    async def cluster_allocation_explain(self, index: str = None, shard: int = None, primary: bool = None) -> Dict:
        body = {}
        if index:
            body["index"] = index
            body["shard"] = shard or 0
            body["primary"] = primary if primary is not None else True
        return await self.post("/_cluster/allocation/explain", body if body else None)

    # ── Node APIs ─────────────────────────────────────────────────────────────

    async def nodes_info(self) -> Dict:
        return await self.get("/_nodes")

    async def nodes_stats(self) -> Dict:
        return await self.get("/_nodes/stats")

    async def nodes_hot_threads(self) -> str:
        client = await self._get_client()
        resp = await client.get("/_nodes/hot_threads")
        return resp.text

    # ── Index APIs ────────────────────────────────────────────────────────────

    async def indices_stats(self, index: str = "_all") -> Dict:
        return await self.get(f"/{index}/_stats")

    async def indices_settings(self, index: str = "_all") -> Dict:
        return await self.get(f"/{index}/_settings", params={"include_defaults": "true"})

    async def indices_mappings(self, index: str = "_all") -> Dict:
        return await self.get(f"/{index}/_mapping")

    async def cat_indices(self) -> list:
        return await self.get("/_cat/indices", params={"format": "json", "v": "true", "s": "health,index"})

    async def cat_shards(self) -> list:
        return await self.get("/_cat/shards", params={"format": "json", "v": "true"})

    async def cat_nodes(self) -> list:
        return await self.get("/_cat/nodes", params={"format": "json", "v": "true", "h": "name,ip,heapPercent,ramPercent,cpu,load_1m,diskUsedPercent,role,master"})

    async def cat_allocation(self) -> list:
        return await self.get("/_cat/allocation", params={"format": "json", "v": "true"})

    async def cat_recovery(self) -> list:
        return await self.get("/_cat/recovery", params={"format": "json", "v": "true"})

    async def cat_tasks(self) -> list:
        return await self.get("/_tasks", params={"actions": "*", "detailed": "true"})

    async def cat_thread_pool(self) -> list:
        return await self.get("/_cat/thread_pool", params={"format": "json", "v": "true"})

    async def ilm_explain(self, index: str = "*") -> Dict:
        try:
            return await self.get(f"/{index}/_ilm/explain")
        except Exception:
            return {}

    async def get_version(self) -> str:
        info = await self.get("/")
        version = info.get("version", {}).get("number", "unknown")
        return version

    async def test_connection(self) -> Tuple[bool, str]:
        try:
            info = await self.get("/")
            version = info.get("version", {}).get("number", "unknown")
            cluster_name = info.get("cluster_name", "unknown")
            return True, f"Connected to cluster '{cluster_name}' (ES {version})"
        except httpx.ConnectError as e:
            err = str(e)
            if "CERTIFICATE_VERIFY_FAILED" in err or "SSL" in err.upper():
                return False, (
                    "SSL certificate error. "
                    "If this is an internal cluster with a self-signed cert, "
                    "the backend container may need the CA cert trusted. "
                    f"Detail: {err}"
                )
            return False, f"Cannot reach cluster — connection refused or DNS failed: {err}"
        except httpx.TimeoutException:
            return False, (
                "Connection timed out. Check that the cluster URL is reachable "
                "from the backend container and no firewall is blocking port 9200/443."
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return False, "Authentication failed — check your API key or username/password"
            if e.response.status_code == 403:
                return False, "Access denied — the credentials do not have sufficient permissions"
            return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            return False, f"Connection error: {type(e).__name__}: {str(e)}"


# Global connection registry
_connections: Dict[str, ElasticsearchClient] = {}


def get_es_client(cluster_id: str) -> Optional[ElasticsearchClient]:
    return _connections.get(cluster_id)


def register_cluster(cluster_id: str, client: ElasticsearchClient):
    _connections[cluster_id] = client


def remove_cluster(cluster_id: str):
    if cluster_id in _connections:
        asyncio.create_task(_connections[cluster_id].close())
        del _connections[cluster_id]
