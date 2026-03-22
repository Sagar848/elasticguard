"""
ElasticGuard Knowledge Base
Loads Elasticsearch troubleshooting knowledge into ChromaDB for RAG
"""
import os
import structlog

logger = structlog.get_logger()

# ── Elasticsearch Troubleshooting Knowledge Documents ─────────────────────────
# Each document is a focused chunk of knowledge the AI agents can retrieve

KNOWLEDGE_DOCS = [
    {
        "id": "cluster_red_status",
        "title": "Cluster Red Status - Primary Shard Unassigned",
        "content": """
Cluster RED status means one or more PRIMARY shards are unassigned.
This causes data unavailability for affected indices.

Root Causes:
1. Node failure/restart - node holding primary shard left the cluster
2. Disk full - disk watermark reached, ES refuses to allocate shards
3. Allocation failures - repeated failed allocation attempts
4. Index corruption - shard data is corrupted or missing
5. Missing node attributes - routing allocation filter mismatch

Diagnosis Steps:
1. GET /_cluster/allocation/explain - explains exactly why a shard is unassigned
2. GET /_cat/shards?v&h=index,shard,prirep,state,unassigned.reason - list unassigned shards
3. GET /_cat/nodes?v - check if all nodes are present
4. GET /_cluster/settings - check allocation filters

Solutions:
- Retry failed allocation: POST /_cluster/reroute?retry_failed=true
- Manually allocate primary: POST /_cluster/reroute with allocate_stale_primary command (DATA LOSS RISK - only if no replica available)
- Fix disk: Free space, then POST /_cluster/reroute
- Restore from snapshot if shard is corrupted

ES Version Notes:
- ES 7+: Use /_cluster/allocation/explain for detailed reasons
- ES 8+: Index lifecycle management may block allocation
""",
        "category": "cluster_health",
        "tags": ["red", "primary", "unassigned", "critical"],
    },
    {
        "id": "cluster_yellow_status",
        "title": "Cluster Yellow Status - Replica Shards Unassigned",
        "content": """
Cluster YELLOW means all primary shards are active but one or more REPLICA shards are unassigned.
Data is available but there is no redundancy for affected indices.

Root Causes:
1. Single node cluster - cannot allocate replicas to same node as primary
2. Not enough nodes for replica count - need N+1 nodes for N replicas
3. Disk watermark - not enough free space on remaining nodes
4. Node attribute filters - routing.allocation.require/include/exclude mismatch

Quick Fix for Development (single node):
PUT /_all/_settings
{"index": {"number_of_replicas": 0}}

Production Fix:
- Add more nodes to the cluster
- Or reduce replica count: PUT /index/_settings {"index.number_of_replicas": 1}
- Check: GET /_cluster/allocation/explain?level=shards

ES 7/8/9 Compatible: All above APIs work across versions.
""",
        "category": "cluster_health",
        "tags": ["yellow", "replica", "unassigned", "single-node"],
    },
    {
        "id": "jvm_heap_pressure",
        "title": "JVM Heap Pressure and GC Thrashing",
        "content": """
High JVM heap usage (>85%) causes frequent garbage collection, degrading performance.
At >95%, the JVM may enter full GC loop (GC thrashing), making the node unresponsive.

Symptoms:
- Slow search/indexing responses
- Circuit breaker exceptions (429 errors)
- Node dropping out of cluster (heartbeat timeout due to GC pause)
- Log messages: "GC overhead limit exceeded"

Root Causes:
1. Field data cache too large - aggregations on text fields load all values into heap
2. Shard count too high - each shard has fixed overhead (~1.5KB heap per shard)
3. Query cache too large - frequently cached queries filling heap
4. Segment memory - too many small segments
5. Heap set too low - insufficient for data volume

Immediate Relief:
POST /_cache/clear  (clears all caches)
POST /_cache/clear?fielddata=true  (targets fielddata specifically)

Heap Configuration:
- Set Xms = Xmx (avoid heap resizing pauses)
- DO NOT exceed 30GB (compressed OOPs boundary)
- Recommended: 50% of available RAM, max 30GB
- Set in jvm.options: -Xms16g -Xmx16g

Long-term Fixes:
- Reduce field data usage: use keyword fields for aggregations
- Set fielddata circuit breaker: indices.breaker.fielddata.limit: 40%
- Reduce shard count: merge small indices, use shrink API
- Enable doc_values on fields used in aggregations (default on keyword)

Monitor:
GET /_nodes/stats/jvm
GET /_nodes/stats/breaker
""",
        "category": "performance",
        "tags": ["jvm", "heap", "gc", "memory", "circuit-breaker"],
    },
    {
        "id": "disk_watermarks",
        "title": "Disk Watermark Thresholds",
        "content": """
Elasticsearch has three disk watermark levels that control shard allocation:

LOW watermark (default 85%):
- ES stops allocating NEW shards to this node
- Existing shards stay, no new ones come in
- Alert: plan for more storage

HIGH watermark (default 90%):
- ES attempts to RELOCATE shards away from this node
- Causes shard movement across cluster (high I/O)
- Alert: urgent action needed

FLOOD STAGE watermark (default 95%):
- ES sets ALL indices on this node to READ-ONLY (index.blocks.read_only_allow_delete: true)
- No new data can be written - ingestion STOPS
- Critical: immediate action required

Fix for flood stage:
1. Free disk space (delete old indices, snapshots, or expand storage)
2. Remove the read-only block:
   PUT /_all/_settings
   {"index.blocks.read_only_allow_delete": null}
3. Verify: GET /_cat/allocation?v

Temporary override (emergency only):
PUT /_cluster/settings
{"transient": {
  "cluster.routing.allocation.disk.watermark.flood_stage": "97%",
  "cluster.routing.allocation.disk.watermark.high": "95%",
  "cluster.routing.allocation.disk.watermark.low": "93%"
}}

Check biggest indices by size:
GET /_cat/indices?s=store.size:desc&v&h=index,health,docs.count,store.size,pri.store.size

Best Practice:
- Keep disk usage below 70% to leave headroom for merges and replicas
- Use ILM to automatically delete old indices
- Set up monitoring alerts at 75% disk usage
""",
        "category": "disk",
        "tags": ["disk", "watermark", "flood", "read-only", "storage"],
    },
    {
        "id": "shard_allocation_explain",
        "title": "Diagnosing Shard Allocation Failures",
        "content": """
The allocation explain API is the single most useful tool for diagnosing why shards are unassigned.

Usage:
GET /_cluster/allocation/explain
(returns explanation for first unassigned shard)

For specific shard:
GET /_cluster/allocation/explain
{
  "index": "my-index",
  "shard": 0,
  "primary": true
}

Common Decisions and Meanings:
- NO: This node cannot hold this shard (reason given)
- THROTTLED: Allocation throttled, will retry
- YES: This node CAN hold this shard
- AWAITING_INFO: Waiting for node info
- ALLOCATION_DELAYED: Delayed after node left (index.unassigned.node_left.delayed_timeout)

Common NO reasons:
1. "the shard cannot be allocated to the same node as a replica of the same shard"
   → Need more nodes or reduce replicas
2. "the node is above the high disk watermark"
   → Free disk space
3. "max shard per node limit exceeded"
   → Increase cluster.routing.allocation.total_shards_per_node
4. "filter not matching"
   → Check index.routing.allocation.require/include/exclude settings
5. "no data nodes available"
   → Start data nodes

After fixing: POST /_cluster/reroute?retry_failed=true
""",
        "category": "shards",
        "tags": ["allocation", "explain", "unassigned", "diagnosis"],
    },
    {
        "id": "index_lifecycle_management",
        "title": "Index Lifecycle Management (ILM)",
        "content": """
ILM automates index management through phases: Hot → Warm → Cold → Frozen → Delete

Basic ILM policy for logs:
PUT /_ilm/policy/logs_policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {"max_size": "50gb", "max_age": "1d"},
          "set_priority": {"priority": 100}
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "shrink": {"number_of_shards": 1},
          "forcemerge": {"max_num_segments": 1},
          "set_priority": {"priority": 50}
        }
      },
      "cold": {
        "min_age": "30d",
        "actions": {
          "freeze": {},
          "set_priority": {"priority": 0}
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {"delete": {}}
      }
    }
  }
}

Apply policy to an index template:
PUT /_index_template/logs_template
{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": {
      "index.lifecycle.name": "logs_policy",
      "index.lifecycle.rollover_alias": "logs"
    }
  }
}

Check ILM status:
GET /logs-*/_ilm/explain
GET /_ilm/status

ES 7 Note: Use index.lifecycle.name in settings
ES 8+: Supports data streams (preferred over index+alias pattern)
""",
        "category": "indices",
        "tags": ["ilm", "lifecycle", "rollover", "hot-warm-cold"],
    },
    {
        "id": "thread_pool_rejections",
        "title": "Thread Pool Rejections",
        "content": """
Thread pool rejections mean Elasticsearch is overloaded - requests are being dropped.

Key Thread Pools:
- write: Bulk indexing, single document index/update/delete
- search: Search requests, aggregations
- get: Real-time GET operations
- analyze: Text analysis requests
- snapshot: Snapshot/restore operations

Checking rejections:
GET /_cat/thread_pool?v&h=node_name,name,active,rejected,completed,queue,queue_size

High rejections indicate:
1. write pool: Indexing too fast for cluster capacity
2. search pool: Too many concurrent searches or expensive queries
3. get pool: High real-time GET load

Fixes:
1. Reduce indexing rate / use bulk indexing
2. Increase queue size (temporary):
   PUT /_cluster/settings
   {"transient": {"thread_pool.write.queue_size": 1000}}
3. Add more data nodes
4. Use async bulk indexing with backpressure
5. Optimize slow queries (use profile API)

Bulk indexing best practices:
- Batch 5-15MB per bulk request
- Use refresh_interval=30s during bulk loads
- Disable replicas during initial load, re-enable after

Monitor continuously:
GET /_nodes/stats/thread_pool
""",
        "category": "performance",
        "tags": ["thread-pool", "rejections", "bulk", "indexing", "search"],
    },
    {
        "id": "shard_sizing",
        "title": "Shard Sizing Best Practices",
        "content": """
Shard sizing is critical for Elasticsearch performance and stability.

Recommended Shard Size: 10-50 GB per shard (optimal ~20-40 GB)

Too many small shards (< 1GB) cause:
- High heap overhead (each shard ~few KB heap minimum)
- Master node overload (manages shard routing table)
- Slow searches (overhead per shard)
- Poor segment merging efficiency

Too few large shards (> 60GB) cause:
- Slow recovery after node failure
- Slow rebalancing
- Long forcemerge operations
- Poor parallel search performance

Calculating optimal shard count:
target_shards = ceil(expected_index_size_GB / 30)

Fixing over-sharded indices:
# Shrink (must set read-only first)
PUT /source-index/_settings {"settings": {"index.blocks.write": true}}
POST /source-index/_shrink/target-index
{"settings": {"index.number_of_shards": 2}}

Fixing under-sharded (too large) indices:
# Split (target must have multiple of source shards)
POST /source-index/_split/target-index
{"settings": {"index.number_of_shards": 6}}

# Or reindex with new shard count
POST /_reindex
{
  "source": {"index": "old-index"},
  "dest": {"index": "new-index"}
}

Shard count per node guideline:
- Max 20 shards per GB of heap
- 30GB heap = max ~600 shards per node
""",
        "category": "shards",
        "tags": ["shards", "sizing", "shrink", "split", "reindex"],
    },
    {
        "id": "circuit_breakers",
        "title": "Circuit Breakers",
        "content": """
Circuit breakers prevent out-of-memory errors by limiting memory usage for specific operations.

Types of Circuit Breakers:
1. Parent breaker: total memory limit (default 95% heap)
2. Fielddata breaker: fielddata cache (default 40% heap)
3. Request breaker: per-request memory (default 60% heap)
4. In-flight requests: network transport (default 100% heap)
5. Script compilation: scripts per minute limit

Checking breakers:
GET /_nodes/stats/breaker

When tripped (HTTP 429 with circuit_breaking_exception):
- Fielddata: Aggregations on text fields using too much memory
  Fix: POST /_cache/clear?fielddata=true
  Long-term: Use keyword fields, enable eager_global_ordinals
  
- Request: Single query using too much memory  
  Fix: Reduce result size, use scroll API, optimize aggregations
  
- Parent: Total heap near limit
  Fix: Clear all caches, reduce heap consumers, increase heap

Adjusting limits:
PUT /_cluster/settings
{
  "persistent": {
    "indices.breaker.fielddata.limit": "40%",
    "indices.breaker.request.limit": "60%",
    "indices.breaker.total.limit": "70%"
  }
}

ES 8+ note: indices.breaker.total.use_real_memory defaults to true
which uses actual JVM memory accounting (more accurate).
""",
        "category": "memory",
        "tags": ["circuit-breaker", "oom", "fielddata", "memory", "429"],
    },
    {
        "id": "slow_queries",
        "title": "Slow Query Detection and Optimization",
        "content": """
Slow queries degrade cluster performance and consume thread pool capacity.

Enable slow query logging:
PUT /my-index/_settings
{
  "index.search.slowlog.threshold.query.warn": "5s",
  "index.search.slowlog.threshold.query.info": "2s",
  "index.search.slowlog.threshold.fetch.warn": "1s"
}

Check slow logs: /var/log/elasticsearch/*_index_search_slowlog.log

Profile a specific query:
POST /my-index/_search
{
  "profile": true,
  "query": {"match": {"field": "value"}}
}

Common slow query causes and fixes:
1. Wildcard queries at start of pattern: "query": {"wildcard": {"field": "*value"}}
   Fix: Use n-gram tokenizer or edge n-gram for prefix searches
   
2. Script queries running on every document:
   Fix: Use stored scripts, or restructure to use filters (cached)
   
3. Deep pagination: from + size > 10000
   Fix: Use search_after for pagination, or scroll API
   
4. Large aggregations on high-cardinality fields:
   Fix: Use sampler aggregation, limit cardinality with filter
   
5. Unfiltered wildcard on large indices:
   Fix: Always include date range or other filters

Hot threads (which queries are using CPU now):
GET /_nodes/hot_threads

Task management (long running tasks):
GET /_tasks?detailed&actions=*search
POST /_tasks/{task_id}/_cancel
""",
        "category": "performance",
        "tags": ["slow-query", "profile", "hotthreads", "optimization"],
    },
    {
        "id": "node_roles",
        "title": "Node Roles and Cluster Architecture",
        "content": """
Elasticsearch node roles determine what functions a node performs.

Node Roles (ES 7.9+):
- master: Eligible to be elected cluster master
- data: Stores data and performs CRUD/search
- data_content: Stores non-time-series data
- data_hot: Stores hot/recent data (ILM)
- data_warm: Stores warm data (ILM)
- data_cold: Stores cold data (ILM)
- data_frozen: Stores frozen data with searchable snapshots
- ingest: Pre-processes documents via pipelines
- ml: Machine learning nodes
- remote_cluster_client: Cross-cluster search
- transform: Transforms
- coordinating only: No role set, routes requests only

Recommended Production Architecture (3+ nodes minimum):
- 3 dedicated master nodes (no data role): Prevent master instability
- N data nodes: Scale for storage/search requirements
- Optional: coordinating-only nodes for large clusters

Setting node roles in elasticsearch.yml:
node.roles: [ master ]       # dedicated master
node.roles: [ data, ingest ] # data + ingest
node.roles: [ ]              # coordinating only

Split-brain prevention:
- Always use odd number of master-eligible nodes
- Set discovery.zen.minimum_master_nodes = ceil(N/2) + 1 (ES 6 only)
- ES 7+: Automatic via cluster.initial_master_nodes (set once at bootstrap)

Check node roles:
GET /_cat/nodes?v&h=name,ip,roles,heap.percent,cpu,load_1m
""",
        "category": "architecture",
        "tags": ["node-roles", "master", "data", "architecture", "split-brain"],
    },
    {
        "id": "snapshot_restore",
        "title": "Snapshots and Disaster Recovery",
        "content": """
Snapshots are the primary backup mechanism for Elasticsearch.

Register a repository:
# Filesystem repository
PUT /_snapshot/my_backup
{
  "type": "fs",
  "settings": {
    "location": "/mount/backups/my_backup",
    "compress": true
  }
}

# S3 repository (requires repository-s3 plugin)
PUT /_snapshot/s3_backup
{
  "type": "s3",
  "settings": {
    "bucket": "my-es-backup-bucket",
    "region": "us-east-1"
  }
}

Create a snapshot:
PUT /_snapshot/my_backup/snapshot_1?wait_for_completion=true
{
  "indices": "my-index-*",
  "ignore_unavailable": true,
  "include_global_state": false
}

Restore from snapshot:
POST /_snapshot/my_backup/snapshot_1/_restore
{
  "indices": "my-index",
  "rename_pattern": "my-(.+)",
  "rename_replacement": "restored-$1"
}

SLM (Snapshot Lifecycle Management, ES 7.4+):
PUT /_slm/policy/daily-snapshots
{
  "schedule": "0 30 1 * * ?",
  "name": "<daily-snap-{now/d}>",
  "repository": "my_backup",
  "config": {"include_global_state": false},
  "retention": {"expire_after": "30d", "min_count": 5}
}

Recovery: GET /_snapshot/my_backup/snapshot_1
Status: GET /_snapshot/my_backup/snapshot_1/_status
""",
        "category": "backup",
        "tags": ["snapshot", "backup", "restore", "disaster-recovery", "SLM"],
    },
    {
        "id": "index_mapping_explosion",
        "title": "Mapping Explosion - Too Many Fields",
        "content": """
Mapping explosion occurs when an index has too many fields, causing master node overload
and degraded performance. Default limit is 1000 fields per index.

Symptoms:
- Master node high CPU and memory
- Slow cluster state updates
- "Limit of total fields exceeded" errors
- Large cluster state (GET /_cluster/state size)

Causes:
1. Dynamic mapping with user-controlled field names
2. Nested objects with high cardinality keys
3. Metrics with per-metric field names instead of keyword+value pairs

Prevention:
PUT /my-index/_settings  
{
  "index.mapping.total_fields.limit": 500
}

Disable dynamic mapping:
PUT /my-index/_mapping
{"dynamic": "strict"}  # Only pre-defined fields allowed
or
{"dynamic": false}     # Extra fields ignored, not indexed

Best pattern for dynamic key-value data:
Use flattened field type (ES 7.3+):
{
  "mappings": {
    "properties": {
      "labels": {"type": "flattened"}
    }
  }
}

Or use the ECS (Elastic Common Schema) pattern with labels.* as flattened.

Check current field count:
GET /my-index/_mapping | python3 -c "import json,sys; m=json.load(sys.stdin); print(len(m[list(m.keys())[0]]['mappings']['properties']))"
""",
        "category": "indices",
        "tags": ["mapping", "fields", "explosion", "dynamic", "flattened"],
    },
    {
        "id": "cross_cluster_search",
        "title": "Cross-Cluster Search and Replication",
        "content": """
Cross-Cluster Search (CCS) allows querying multiple ES clusters from one query.
Cross-Cluster Replication (CCR) replicates indices between clusters.

Setup Cross-Cluster Search:
PUT /_cluster/settings
{
  "persistent": {
    "cluster.remote.cluster_two.seeds": ["remote-host:9300"],
    "cluster.remote.cluster_two.skip_unavailable": false
  }
}

Query across clusters:
GET /cluster_two:index-pattern,local-index/_search
{"query": {"match_all": {}}}

ES 8+ API key-based CCS:
PUT /_cluster/settings
{
  "persistent": {
    "cluster.remote.remote1.mode": "proxy",
    "cluster.remote.remote1.proxy_address": "remote-host:9443"
  }
}

Cross-Cluster Replication (requires Platinum license):
PUT /<follower-index>/_ccr/follow
{
  "remote_cluster": "leader_cluster",
  "leader_index": "leader-index"
}

Check CCS remote clusters:
GET /_remote/info

Security note: ES 8+ requires TLS for remote connections by default.
""",
        "category": "architecture",
        "tags": ["ccs", "ccr", "cross-cluster", "replication", "federation"],
    },
    {
        "id": "performance_tuning",
        "title": "Elasticsearch Performance Tuning Guide",
        "content": """
Comprehensive performance tuning checklist for Elasticsearch.

INDEXING PERFORMANCE:
1. Use bulk API - batch 5-15MB per request
2. Increase refresh interval during bulk load:
   PUT /my-index/_settings {"index.refresh_interval": "30s"}
3. Disable replicas during initial load, re-enable after
4. Use multiple indexing threads (but don't overwhelm)
5. Set index.translog.durability: async (risk: data loss on crash)
   For safety keep: request (default)
6. Increase indexing buffer: indices.memory.index_buffer_size: 20%

SEARCH PERFORMANCE:
1. Use filter context where possible (cached, no scoring):
   "filter": [{"term": {"status": "active"}}]
2. Avoid leading wildcards
3. Use doc_values for sorting and aggregations
4. Set routing for known partition queries
5. Warm up shards with warming queries after restart
6. Use request cache for repetitive aggregations:
   GET /my-index/_search?request_cache=true

OS/HARDWARE TUNING:
1. Disable swap: swapoff -a or vm.swappiness=1
2. Increase file descriptors: ulimit -n 65535
3. vm.max_map_count=262144 (required for ES)
4. Use SSDs for data nodes
5. Separate data and log paths
6. Network: 10GbE between nodes minimum

SEGMENT MERGING:
- Let ES auto-merge (default is good for most cases)
- For static indices: POST /my-index/_forcemerge?max_num_segments=1
- Schedule forcemerge during low-traffic periods

QUERY CACHE:
GET /_stats/query_cache  - check cache hit rate
High miss rate: increase indices.queries.cache.size (default 10%)
""",
        "category": "performance",
        "tags": ["tuning", "indexing", "search", "bulk", "optimization"],
    },
    {
        "id": "security_setup",
        "title": "Elasticsearch Security Configuration",
        "content": """
Elasticsearch security has been free (basic license) since ES 6.8/7.1.

ES 8.x: Security enabled by default (breaking change from 7.x)
ES 7.x: Must explicitly enable security

Enable security in elasticsearch.yml (ES 7):
xpack.security.enabled: true
xpack.security.transport.ssl.enabled: true
xpack.security.transport.ssl.keystore.path: elastic-certificates.p12
xpack.security.http.ssl.enabled: true

Generate certificates (ES 7/8):
bin/elasticsearch-certutil cert --silent --pem -out config/certs/certs.zip
unzip config/certs/certs.zip -d config/certs

Setup passwords (ES 7):
bin/elasticsearch-setup-passwords auto

ES 8 auto-configuration:
First startup generates passwords and enrolls Kibana automatically.
Check: /var/log/elasticsearch/elasticsearch.log for enrollment token

Create users and roles:
POST /_security/role/app_reader
{
  "indices": [{"names": ["app-*"], "privileges": ["read"]}]
}
POST /_security/user/app_user
{
  "password": "secure_password",
  "roles": ["app_reader"]
}

API Keys (preferred for applications):
POST /_security/api_key
{
  "name": "my-app-key",
  "role_descriptors": {
    "app_role": {
      "indices": [{"names": ["app-*"], "privileges": ["read", "write"]}]
    }
  }
}
""",
        "category": "security",
        "tags": ["security", "tls", "authentication", "api-key", "roles"],
    },
]


async def init_knowledge_base(persist_dir: str = "./data/chroma", embed_model: str = "nomic-embed-text", ollama_base: str = "http://localhost:11434"):
    """
    Initialize the ChromaDB knowledge base with ES troubleshooting docs.
    
    RAG is OPTIONAL — if no embedding provider is available the app works
    fully without it. AI agents fall back to their built-in knowledge.
    Failure here is logged at INFO level, not ERROR.
    """
    try:
        import chromadb
        from langchain_chroma import Chroma
    except ImportError:
        logger.info("ChromaDB not installed — RAG disabled (app works without it)")
        return False

    logger.info("Initialising knowledge base", persist_dir=persist_dir)

    embeddings = None

    # ── 1. Try Ollama first (local, free, no key needed) ──────────────────────
    try:
        from langchain_ollama import OllamaEmbeddings
        import httpx
        # Quick connectivity check before loading the model
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{ollama_base}/api/tags")
            resp.raise_for_status()
        embeddings = OllamaEmbeddings(model=embed_model, base_url=ollama_base)
        embeddings.embed_query("test")
        logger.info("RAG: using Ollama embeddings", model=embed_model)
    except Exception as e:
        logger.info("RAG: Ollama not available", reason=str(e)[:80])

    # ── 2. Try OpenAI if key is configured ────────────────────────────────────
    if not embeddings:
        try:
            from langchain_openai import OpenAIEmbeddings
            from core.config import settings
            # Only attempt if a real key is configured (not empty / placeholder)
            if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
                embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
                # Quick validation
                embeddings.embed_query("test")
                logger.info("RAG: using OpenAI embeddings")
            else:
                logger.info("RAG: no OpenAI key configured — skipping")
        except Exception as e:
            logger.info("RAG: OpenAI embeddings unavailable", reason=str(e)[:80])

    # ── 3. Try Google Gemini embeddings ───────────────────────────────────────
    if not embeddings:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            from core.config import settings
            if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("AIza..."):
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=settings.GEMINI_API_KEY,
                )
                embeddings.embed_query("test")
                logger.info("RAG: using Google Gemini embeddings")
        except Exception as e:
            logger.info("RAG: Gemini embeddings unavailable", reason=str(e)[:80])

    # ── No provider available — skip silently ─────────────────────────────────
    if not embeddings:
        logger.info(
            "RAG knowledge base disabled — no embedding provider available. "
            "Start Ollama or set OPENAI_API_KEY to enable. "
            "AI agents still work without RAG."
        )
        return False

    try:
        os.makedirs(persist_dir, exist_ok=True)

        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name="es_knowledge",
        )

        # Skip if already populated
        existing = vectorstore.get()
        if len(existing.get("ids", [])) >= len(KNOWLEDGE_DOCS):
            logger.info("RAG: knowledge base already populated", docs=len(existing["ids"]))
            return True

        # Load all documents
        from langchain_core.documents import Document
        docs = [
            Document(
                page_content=f"# {kd['title']}\n\n{kd['content']}",
                metadata={
                    "id": kd["id"],
                    "title": kd["title"],
                    "category": kd["category"],
                    "tags": ", ".join(kd["tags"]),
                }
            )
            for kd in KNOWLEDGE_DOCS
        ]

        vectorstore.add_documents(docs)
        logger.info("RAG: knowledge base ready", documents=len(docs))
        return True

    except Exception as e:
        logger.info("RAG: knowledge base setup failed (non-fatal)", error=str(e)[:120])
        return False


def get_all_knowledge() -> list:
    """Return all knowledge documents as plain dicts (no embedding needed)."""
    return KNOWLEDGE_DOCS
