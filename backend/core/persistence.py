"""
ElasticGuard — Cluster Persistence
Saves/loads cluster connection configs to SQLite so they survive backend restarts.
"""
import json
import os
import sqlite3
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()

DB_PATH = os.environ.get("ELASTICGUARD_DB", "./data/elasticguard.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cluster_connections (
                cluster_id   TEXT PRIMARY KEY,
                url          TEXT NOT NULL,
                username     TEXT,
                password     TEXT,
                api_key      TEXT,
                verify_ssl   INTEGER DEFAULT 0,
                es_version   TEXT,
                cluster_name TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                last_used    TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    logger.info("Cluster DB initialised", path=DB_PATH)


def save_cluster(
    cluster_id: str,
    url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    verify_ssl: bool = False,
    es_version: Optional[str] = None,
    cluster_name: Optional[str] = None,
) -> None:
    """Upsert a cluster connection."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO cluster_connections
                (cluster_id, url, username, password, api_key, verify_ssl, es_version, cluster_name, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(cluster_id) DO UPDATE SET
                url          = excluded.url,
                username     = excluded.username,
                password     = excluded.password,
                api_key      = excluded.api_key,
                verify_ssl   = excluded.verify_ssl,
                es_version   = excluded.es_version,
                cluster_name = excluded.cluster_name,
                last_used    = datetime('now')
        """, (cluster_id, url, username, password, api_key, int(verify_ssl), es_version, cluster_name))
        conn.commit()
    logger.debug("Cluster saved", cluster_id=cluster_id)


def load_all_clusters() -> List[Dict]:
    """Return all saved cluster connections."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cluster_connections ORDER BY last_used DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_cluster(cluster_id: str) -> None:
    """Remove a cluster connection."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM cluster_connections WHERE cluster_id = ?", (cluster_id,))
        conn.commit()
    logger.debug("Cluster deleted", cluster_id=cluster_id)


def update_cluster_meta(cluster_id: str, es_version: str = None, cluster_name: str = None) -> None:
    """Update version/name after a successful connect."""
    with _get_conn() as conn:
        conn.execute("""
            UPDATE cluster_connections
            SET es_version = COALESCE(?, es_version),
                cluster_name = COALESCE(?, cluster_name),
                last_used = datetime('now')
            WHERE cluster_id = ?
        """, (es_version, cluster_name, cluster_id))
        conn.commit()


# ── AI Config Persistence ──────────────────────────────────────────────────────

def save_ai_config(
    provider: str,
    model: str = None,
    api_key: str = None,
    base_url: str = None,
) -> None:
    """Save AI provider config (single row — only one active config at a time)."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_config (
                id        INTEGER PRIMARY KEY CHECK (id = 1),
                provider  TEXT NOT NULL,
                model     TEXT,
                api_key   TEXT,
                base_url  TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO ai_config (id, provider, model, api_key, base_url, updated_at)
            VALUES (1, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                provider   = excluded.provider,
                model      = excluded.model,
                api_key    = excluded.api_key,
                base_url   = excluded.base_url,
                updated_at = datetime('now')
        """, (provider, model, api_key, base_url))
        conn.commit()
    logger.debug("AI config saved", provider=provider)


def load_ai_config() -> dict:
    """Load saved AI config. Returns empty dict if not saved yet."""
    try:
        with _get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_config (
                    id        INTEGER PRIMARY KEY CHECK (id = 1),
                    provider  TEXT NOT NULL,
                    model     TEXT,
                    api_key   TEXT,
                    base_url  TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            row = conn.execute("SELECT * FROM ai_config WHERE id = 1").fetchone()
        if row:
            return {
                "provider": row["provider"],
                "model":    row["model"],
                "api_key":  row["api_key"],
                "base_url": row["base_url"],
            }
    except Exception as e:
        logger.warning("Could not load AI config", error=str(e))
    return {}
