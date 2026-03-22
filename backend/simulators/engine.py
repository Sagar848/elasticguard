"""
ElasticGuard Cluster Simulation Engine
Simulates the impact of cluster changes before applying them.
Models shard distribution, disk usage, recovery time, and performance.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import structlog

logger = structlog.get_logger()


@dataclass
class SimNode:
    id: str
    name: str
    roles: List[str]
    disk_total_gb: float
    disk_used_gb: float
    heap_gb: float
    cpu_count: int
    shards: List[str] = field(default_factory=list)

    @property
    def disk_free_gb(self) -> float:
        return max(0.0, self.disk_total_gb - self.disk_used_gb)

    @property
    def disk_used_pct(self) -> float:
        return round(self.disk_used_gb / max(self.disk_total_gb, 0.001) * 100, 1)

    @property
    def shard_count(self) -> int:
        return len(self.shards)

    @property
    def is_data(self) -> bool:
        return any(r in self.roles for r in ["data", "data_hot", "data_warm", "data_cold"])


@dataclass
class SimShard:
    id: str
    index: str
    shard_num: int
    is_primary: bool
    size_gb: float
    node_id: Optional[str] = None


@dataclass
class ClusterSnapshot:
    nodes: List[SimNode]
    shards: List[SimShard]
    cluster_name: str = "cluster"

    @property
    def data_nodes(self) -> List[SimNode]:
        return [n for n in self.nodes if n.is_data]

    @property
    def total_shards(self) -> int:
        return len(self.shards)

    @property
    def unassigned_shards(self) -> int:
        return len([s for s in self.shards if s.node_id is None])

    @property
    def total_data_gb(self) -> float:
        return round(sum(s.size_gb for s in self.shards if s.is_primary), 2)

    def node_by_id(self, node_id: str) -> Optional[SimNode]:
        return next((n for n in self.nodes if n.id == node_id), None)

    def avg_shards_per_node(self) -> float:
        dn = self.data_nodes
        if not dn:
            return 0.0
        return round(self.total_shards / len(dn), 1)

    def shard_balance_score(self) -> float:
        """0 = perfect balance, higher = more imbalanced."""
        counts = [n.shard_count for n in self.data_nodes]
        if not counts or max(counts) == 0:
            return 0.0
        avg = sum(counts) / len(counts)
        variance = sum((c - avg) ** 2 for c in counts) / len(counts)
        return round(math.sqrt(variance) / max(avg, 1) * 100, 1)

    def health_status(self) -> str:
        if self.unassigned_shards > 0:
            primaries_unassigned = [s for s in self.shards if s.node_id is None and s.is_primary]
            return "red" if primaries_unassigned else "yellow"
        for node in self.data_nodes:
            if node.disk_used_pct >= 95:
                return "red"
            if node.disk_used_pct >= 85:
                return "yellow"
        return "green"


class ClusterSimulator:
    """
    Physics-based cluster simulator.
    Builds a model from live ES data, then runs what-if scenarios.
    """

    def build_snapshot_from_es(
        self,
        nodes_stats: Dict,
        cat_nodes: List[Dict],
        cat_shards: List[Dict],
        cat_allocation: List[Dict],
        cluster_name: str = "cluster",
    ) -> ClusterSnapshot:
        """Convert live ES API data into a simulation snapshot."""
        nodes: List[SimNode] = []
        node_name_to_id: Dict[str, str] = {}

        # Build nodes from nodes_stats (most complete)
        for node_id, nd in nodes_stats.get("nodes", {}).items():
            fs = nd.get("fs", {}).get("total", {})
            jvm = nd.get("jvm", {}).get("mem", {})
            os_data = nd.get("os", {})

            disk_total = fs.get("total_in_bytes", 100 * 1024**3) / 1024**3
            disk_avail = fs.get("available_in_bytes", 20 * 1024**3) / 1024**3
            disk_used = disk_total - disk_avail
            heap_gb = jvm.get("heap_max_in_bytes", 8 * 1024**3) / 1024**3
            cpu_count = os_data.get("available_processors", 4)

            sim_node = SimNode(
                id=node_id,
                name=nd.get("name", node_id),
                roles=nd.get("roles", ["data", "master"]),
                disk_total_gb=round(disk_total, 2),
                disk_used_gb=round(disk_used, 2),
                heap_gb=round(heap_gb, 2),
                cpu_count=cpu_count,
            )
            nodes.append(sim_node)
            node_name_to_id[sim_node.name] = node_id

        # Build shards
        shards: List[SimShard] = []
        node_shards: Dict[str, List[str]] = {n.id: [] for n in nodes}

        for s in cat_shards:
            shard_id = f"{s.get('index')}/{s.get('shard')}/{s.get('prirep')}"
            store_bytes_str = s.get("store", "0b")
            size_gb = self._parse_size_gb(store_bytes_str)
            node_name = s.get("node")
            node_id = node_name_to_id.get(node_name) if node_name else None

            sim_shard = SimShard(
                id=shard_id,
                index=s.get("index", "?"),
                shard_num=int(s.get("shard", 0)),
                is_primary=s.get("prirep") == "p",
                size_gb=size_gb,
                node_id=node_id,
            )
            shards.append(sim_shard)
            if node_id and node_id in node_shards:
                node_shards[node_id].append(shard_id)

        for node in nodes:
            node.shards = node_shards.get(node.id, [])

        return ClusterSnapshot(nodes=nodes, shards=shards, cluster_name=cluster_name)

    # ── Simulations ────────────────────────────────────────────────────────────

    def simulate_add_node(
        self, snapshot: ClusterSnapshot, count: int = 1, disk_gb: float = None, heap_gb: float = None
    ) -> Dict:
        """Simulate adding N new nodes to the cluster."""
        import copy
        sim = copy.deepcopy(snapshot)
        data_nodes = sim.data_nodes

        # Default new node specs = avg of existing
        avg_disk = sum(n.disk_total_gb for n in data_nodes) / max(len(data_nodes), 1) if data_nodes else 500.0
        avg_heap = sum(n.heap_gb for n in data_nodes) / max(len(data_nodes), 1) if data_nodes else 8.0
        new_disk = disk_gb or avg_disk
        new_heap = heap_gb or avg_heap

        new_nodes = []
        for i in range(count):
            new_node = SimNode(
                id=f"simulated-node-{i+1}",
                name=f"simulated-node-{i+1}",
                roles=["data"],
                disk_total_gb=new_disk,
                disk_used_gb=0.0,
                heap_gb=new_heap,
                cpu_count=8,
            )
            sim.nodes.append(new_node)
            new_nodes.append(new_node)

        # Rebalance shards across all data nodes
        before_balance = snapshot.shard_balance_score()
        self._rebalance_shards(sim)
        after_balance = sim.shard_balance_score()

        # Estimate recovery time (shards moved * avg shard size / 100 MB/s network)
        old_data_count = len(snapshot.data_nodes)
        new_data_count = len(sim.data_nodes)
        shards_to_move = int(snapshot.total_shards * count / max(new_data_count, 1))
        avg_shard_gb = snapshot.total_data_gb / max(snapshot.total_shards, 1)
        recovery_secs = shards_to_move * avg_shard_gb * 1024 / 100  # assume 100 MB/s

        before_health = snapshot.health_status()
        after_health = sim.health_status()

        return {
            "simulation_type": "add_node",
            "before": self._snapshot_summary(snapshot),
            "after": self._snapshot_summary(sim),
            "changes": {
                "nodes_added": count,
                "new_node_disk_gb": round(new_disk, 1),
                "new_node_heap_gb": round(new_heap, 1),
            },
            "impact": {
                "health_before": before_health,
                "health_after": after_health,
                "health_improved": self._health_improved(before_health, after_health),
                "shards_to_move": shards_to_move,
                "balance_score_before": before_balance,
                "balance_score_after": after_balance,
                "balance_improved": after_balance < before_balance,
                "estimated_recovery_minutes": round(recovery_secs / 60, 1),
                "disk_relief_pct": round(100 / max(new_data_count, 1) * count, 1),
            },
            "recommendation": self._add_node_recommendation(snapshot, sim, count),
        }

    def simulate_remove_node(
        self, snapshot: ClusterSnapshot, node_name: str = None
    ) -> Dict:
        """Simulate removing a node (or the most loaded one if none specified)."""
        import copy
        sim = copy.deepcopy(snapshot)
        data_nodes = sim.data_nodes

        if len(data_nodes) <= 1:
            return {"error": "Cannot remove the only data node", "simulation_type": "remove_node"}

        # Pick the node to remove (most loaded by disk, or by name)
        if node_name:
            target = next((n for n in data_nodes if n.name == node_name), None)
        else:
            target = max(data_nodes, key=lambda n: n.disk_used_pct)

        if not target:
            return {"error": f"Node '{node_name}' not found", "simulation_type": "remove_node"}

        # Orphan shards from removed node
        orphaned_shards = [s for s in sim.shards if s.node_id == target.id]
        for s in orphaned_shards:
            s.node_id = None

        sim.nodes.remove(target)

        # Check if we can reallocate
        remaining_data = sim.data_nodes
        total_disk_needed = sum(s.size_gb for s in orphaned_shards)
        total_free = sum(n.disk_free_gb for n in remaining_data)
        can_reallocate = total_free > total_disk_needed * 1.2  # 20% headroom

        if can_reallocate:
            self._rebalance_shards(sim)

        recovery_secs = len(orphaned_shards) * (snapshot.total_data_gb / max(snapshot.total_shards, 1)) * 1024 / 100

        risk = "critical" if len(remaining_data) < 2 else "high" if len(remaining_data) < 3 else "medium"

        return {
            "simulation_type": "remove_node",
            "node_removed": target.name,
            "before": self._snapshot_summary(snapshot),
            "after": self._snapshot_summary(sim),
            "impact": {
                "health_before": snapshot.health_status(),
                "health_after": sim.health_status(),
                "orphaned_shards": len(orphaned_shards),
                "can_reallocate": can_reallocate,
                "free_disk_after_gb": round(total_free - total_disk_needed, 1),
                "estimated_recovery_minutes": round(recovery_secs / 60, 1),
                "risk_level": risk,
            },
            "warnings": self._remove_node_warnings(snapshot, target, sim),
            "recommendation": (
                "Safe to proceed — cluster has sufficient capacity." if can_reallocate and risk != "critical"
                else "WARNING: Insufficient disk space or too few nodes. Do NOT proceed without adding capacity."
            ),
        }

    def simulate_change_replicas(
        self, snapshot: ClusterSnapshot, index_pattern: str = "*", new_replicas: int = 1
    ) -> Dict:
        """Simulate changing replica count for matching indices."""
        import copy, fnmatch
        sim = copy.deepcopy(snapshot)

        matched_indices = set()
        for s in sim.shards:
            if index_pattern == "*" or fnmatch.fnmatch(s.index, index_pattern):
                matched_indices.add(s.index)

        current_primaries: Dict[str, int] = {}
        current_replicas: Dict[str, int] = {}
        for s in sim.shards:
            if s.index in matched_indices:
                if s.is_primary:
                    current_primaries[s.index] = current_primaries.get(s.index, 0) + 1
                else:
                    current_replicas[s.index] = current_replicas.get(s.index, 0) + 1

        total_primary_size = sum(
            s.size_gb for s in sim.shards if s.index in matched_indices and s.is_primary
        )
        total_old_replica_size = sum(
            s.size_gb for s in sim.shards if s.index in matched_indices and not s.is_primary
        )

        # Avg current replicas
        avg_old = sum(current_replicas.values()) / max(len(matched_indices), 1) / max(sum(current_primaries.values()) / max(len(matched_indices), 1), 1)
        avg_old = round(avg_old)

        disk_delta_gb = total_primary_size * (new_replicas - avg_old)
        data_nodes = sim.data_nodes

        # Can the cluster hold the new replica count?
        total_free = sum(n.disk_free_gb for n in data_nodes)
        can_hold = disk_delta_gb <= 0 or total_free > disk_delta_gb * 1.2

        min_nodes_needed = new_replicas + 1  # need at least 1 primary + N replicas on different nodes
        has_enough_nodes = len(data_nodes) >= min_nodes_needed

        return {
            "simulation_type": "change_replicas",
            "index_pattern": index_pattern,
            "matched_indices": len(matched_indices),
            "old_replica_count": avg_old,
            "new_replica_count": new_replicas,
            "impact": {
                "health_before": snapshot.health_status(),
                "health_after": "green" if has_enough_nodes and can_hold else "yellow",
                "disk_change_gb": round(disk_delta_gb, 2),
                "disk_change_direction": "increase" if disk_delta_gb > 0 else "decrease" if disk_delta_gb < 0 else "no change",
                "can_hold_replicas": can_hold,
                "has_enough_nodes": has_enough_nodes,
                "min_nodes_needed": min_nodes_needed,
                "redundancy_level": "none" if new_replicas == 0 else "standard" if new_replicas == 1 else "high",
            },
            "warnings": [
                w for w in [
                    "No redundancy — single point of failure for all matched indices." if new_replicas == 0 else None,
                    f"Need at least {min_nodes_needed} nodes for {new_replicas} replica(s). Currently have {len(data_nodes)}." if not has_enough_nodes else None,
                    f"Insufficient disk space. Need ~{disk_delta_gb:.1f} GB more free space." if not can_hold and disk_delta_gb > 0 else None,
                ] if w
            ],
            "elasticsearch_api": {
                "method": "PUT",
                "path": f"/{index_pattern}/_settings",
                "body": {"index": {"number_of_replicas": new_replicas}},
                "description": f"Set replicas to {new_replicas} for {index_pattern}",
            },
        }

    def simulate_rebalance(self, snapshot: ClusterSnapshot) -> Dict:
        """Simulate cluster rebalancing to achieve even shard distribution."""
        import copy
        sim = copy.deepcopy(snapshot)

        before_balance = snapshot.shard_balance_score()
        before_dist = {n.name: n.shard_count for n in snapshot.data_nodes}

        self._rebalance_shards(sim)

        after_balance = sim.shard_balance_score()
        after_dist = {n.name: n.shard_count for n in sim.data_nodes}

        shards_moved = sum(
            abs(after_dist.get(name, 0) - before_dist.get(name, 0))
            for name in set(list(before_dist.keys()) + list(after_dist.keys()))
        ) // 2  # each move counted twice

        avg_shard_gb = snapshot.total_data_gb / max(snapshot.total_shards, 1)
        recovery_secs = shards_moved * avg_shard_gb * 1024 / 100

        return {
            "simulation_type": "rebalance",
            "before": {
                "balance_score": before_balance,
                "distribution": before_dist,
                "health": snapshot.health_status(),
            },
            "after": {
                "balance_score": after_balance,
                "distribution": after_dist,
                "health": sim.health_status(),
            },
            "impact": {
                "shards_to_move": shards_moved,
                "balance_improvement_pct": round((before_balance - after_balance) / max(before_balance, 1) * 100, 1),
                "estimated_recovery_minutes": round(recovery_secs / 60, 1),
                "io_impact": "high" if shards_moved > 50 else "medium" if shards_moved > 10 else "low",
            },
            "elasticsearch_api": {
                "method": "PUT",
                "path": "/_cluster/settings",
                "body": {"transient": {"cluster.routing.rebalance.enable": "all"}},
                "description": "Enable shard rebalancing",
            },
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _rebalance_shards(self, sim: ClusterSnapshot) -> None:
        """Distribute shards as evenly as possible across data nodes."""
        data_nodes = sim.data_nodes
        if not data_nodes:
            return

        # Collect all assigned shards and unassign them
        all_shards = [s for s in sim.shards if s.node_id is not None]
        for s in all_shards:
            node = sim.node_by_id(s.node_id)
            if node:
                node.shards = []
            s.node_id = None

        # Also include currently unassigned
        all_shards = sim.shards[:]

        # Sort nodes by shard count (ascending) for round-robin
        data_nodes.sort(key=lambda n: n.disk_used_pct)

        # Assign shards round-robin, respecting disk watermarks
        for i, shard in enumerate(all_shards):
            # Find best node (least loaded by shard count, enough disk)
            candidates = [
                n for n in data_nodes
                if n.disk_free_gb > shard.size_gb * 1.1 and n.disk_used_pct < 85
            ]
            if not candidates:
                candidates = data_nodes  # fall back even if disk is tight

            target = min(candidates, key=lambda n: len(n.shards))
            shard.node_id = target.id
            target.shards.append(shard.id)
            target.disk_used_gb = min(
                target.disk_used_gb + shard.size_gb,
                target.disk_total_gb
            )

    def _snapshot_summary(self, snap: ClusterSnapshot) -> Dict:
        data_nodes = snap.data_nodes
        return {
            "node_count": len(snap.nodes),
            "data_node_count": len(data_nodes),
            "total_shards": snap.total_shards,
            "unassigned_shards": snap.unassigned_shards,
            "avg_shards_per_node": snap.avg_shards_per_node(),
            "total_data_gb": snap.total_data_gb,
            "avg_disk_used_pct": round(sum(n.disk_used_pct for n in data_nodes) / max(len(data_nodes), 1), 1),
            "health": snap.health_status(),
            "balance_score": snap.shard_balance_score(),
        }

    def _health_improved(self, before: str, after: str) -> bool:
        order = {"green": 0, "yellow": 1, "red": 2}
        return order.get(after, 3) <= order.get(before, 3)

    def _add_node_recommendation(self, before: ClusterSnapshot, after: ClusterSnapshot, count: int) -> str:
        parts = []
        if before.health_status() in ("red", "yellow") and after.health_status() == "green":
            parts.append("Adding nodes will restore cluster to GREEN health.")
        avg_disk_before = sum(n.disk_used_pct for n in before.data_nodes) / max(len(before.data_nodes), 1)
        avg_disk_after = sum(n.disk_used_pct for n in after.data_nodes) / max(len(after.data_nodes), 1)
        if avg_disk_after < 70:
            parts.append(f"Average disk drops from {avg_disk_before:.0f}% to {avg_disk_after:.0f}% — good headroom.")
        elif avg_disk_after > 80:
            parts.append(f"Warning: average disk will still be {avg_disk_after:.0f}%. Consider adding more nodes.")
        if before.shard_balance_score() > after.shard_balance_score():
            parts.append("Shard balance will improve after rebalancing.")
        return " ".join(parts) if parts else f"Adding {count} node(s) recommended to improve cluster capacity."

    def _remove_node_warnings(self, before: ClusterSnapshot, removed: SimNode, after: ClusterSnapshot) -> List[str]:
        warnings = []
        remaining = after.data_nodes
        if len(remaining) < 3:
            warnings.append(f"Only {len(remaining)} data node(s) remaining — cluster loses fault tolerance.")
        max_disk = max((n.disk_used_pct for n in remaining), default=0)
        if max_disk > 85:
            warnings.append(f"Disk usage will exceed 85% on some nodes after removal ({max_disk:.0f}%).")
        if removed.shard_count > 50:
            warnings.append(f"Node has {removed.shard_count} shards — recovery will put significant I/O load on cluster.")
        return warnings

    @staticmethod
    def _parse_size_gb(size_str: str) -> float:
        s = str(size_str).lower().strip()
        try:
            if s.endswith("tb"): return float(s[:-2]) * 1024
            if s.endswith("gb"): return float(s[:-2])
            if s.endswith("mb"): return float(s[:-2]) / 1024
            if s.endswith("kb"): return float(s[:-2]) / (1024 ** 2)
            if s.endswith("b"):  return float(s[:-1]) / (1024 ** 3)
        except ValueError:
            pass
        return 0.0
