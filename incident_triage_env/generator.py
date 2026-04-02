"""Procedural scenario generation engine.

Generates thousands of unique SRE incident scenarios at runtime using
composable fault patterns, networkx DAG topologies, and log template synthesis.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import networkx as nx

from .log_templates import get_templates


# ------------------------------------------------------------------
# Fault patterns
# ------------------------------------------------------------------

@dataclass
class FaultPattern:
    name: str
    fault_type: str
    remediation: str
    log_category: str
    root_metric_signature: dict
    cascade_effect: str
    summary_templates: list[str]
    root_service_layer: str
    extra_metric_keys: dict = field(default_factory=dict)


FAULT_PATTERNS: list[FaultPattern] = [
    FaultPattern(
        name="java-oom",
        fault_type="oom",
        remediation="restart",
        log_category="java_oom",
        root_metric_signature={"cpu_pct": 12.0, "memory_pct": 99.1, "error_rate_pct": 100.0, "latency_p99_ms": 0.0, "requests_per_sec": 0.0},
        cascade_effect="error_propagation",
        summary_templates=[
            "ALERT: {root_service} is DOWN. PagerDuty fired P1. Health check returning 503. OOM suspected.",
            "ALERT: {root_service} crashed. Memory exhaustion detected. Upstream services reporting connection refused.",
            "ALERT: P1 -- {root_service} unresponsive. Heap memory critical. Dependent services degrading.",
        ],
        root_service_layer="application",
    ),
    FaultPattern(
        name="disk-full-db",
        fault_type="disk_full",
        remediation="clear_disk",
        log_category="postgres",
        root_metric_signature={"cpu_pct": 8.0, "memory_pct": 55.0, "error_rate_pct": 100.0, "latency_p99_ms": 0.0, "requests_per_sec": 0.0, "disk_usage_pct": 100.0},
        cascade_effect="error_propagation",
        summary_templates=[
            "ALERT: {root_service} writes failing. Disk space exhausted. Dependent services returning errors.",
            "ALERT: P1 -- {root_service} in read-only mode. WAL accumulation filled disk.",
        ],
        root_service_layer="data",
        extra_metric_keys={"disk_usage_pct": 100.0},
    ),
    FaultPattern(
        name="disk-full-kafka",
        fault_type="disk_full",
        remediation="clear_disk",
        log_category="kafka",
        root_metric_signature={"cpu_pct": 25.0, "memory_pct": 60.0, "error_rate_pct": 100.0, "latency_p99_ms": 0.0, "requests_per_sec": 0.0, "disk_usage_pct": 100.0},
        cascade_effect="stale_data",
        summary_templates=[
            "ALERT: Data pipeline degradation detected. Recommendation quality dropping. No HTTP errors visible.",
            "ALERT: Business metrics declining. Feature freshness SLA breached. Investigation needed.",
        ],
        root_service_layer="infrastructure",
        extra_metric_keys={"disk_usage_pct": 100.0},
    ),
    FaultPattern(
        name="connection-leak",
        fault_type="connection_leak",
        remediation="increase_pool",
        log_category="connection_leak",
        root_metric_signature={"cpu_pct": 15.0, "memory_pct": 45.0, "error_rate_pct": 80.0, "latency_p99_ms": 8000.0, "requests_per_sec": 5.0},
        cascade_effect="connection_exhaust",
        summary_templates=[
            "ALERT: {root_service} connections approaching limit. Upstream services timing out.",
            "ALERT: P2 -- Intermittent timeouts across multiple services. Connection pool pressure detected.",
        ],
        root_service_layer="data",
    ),
    FaultPattern(
        name="config-push",
        fault_type="config_error",
        remediation="rollback",
        log_category="generic",
        root_metric_signature={"cpu_pct": 5.0, "memory_pct": 30.0, "error_rate_pct": 0.0, "latency_p99_ms": 20.0, "requests_per_sec": 50.0},
        cascade_effect="error_propagation",
        summary_templates=[
            "ALERT: Multiple services crashing simultaneously. Different errors per service. Config push suspected.",
            "ALERT: P1 -- Widespread service failures after deployment window. Investigating.",
        ],
        root_service_layer="infrastructure",
    ),
    FaultPattern(
        name="cert-expired",
        fault_type="certificate_expired",
        remediation="renew_certificate",
        log_category="generic",
        root_metric_signature={"cpu_pct": 5.0, "memory_pct": 25.0, "error_rate_pct": 100.0, "latency_p99_ms": 0.0, "requests_per_sec": 0.0},
        cascade_effect="error_propagation",
        summary_templates=[
            "ALERT: TLS handshake failures detected. {root_service} certificate may have expired.",
            "ALERT: P1 -- mTLS errors across service mesh. Certificate renewal failure suspected.",
        ],
        root_service_layer="infrastructure",
    ),
    FaultPattern(
        name="thundering-herd",
        fault_type="cpu_saturated",
        remediation="scale_up",
        log_category="generic",
        root_metric_signature={"cpu_pct": 100.0, "memory_pct": 70.0, "error_rate_pct": 85.0, "latency_p99_ms": 12000.0, "requests_per_sec": 2000.0},
        cascade_effect="timeout",
        summary_templates=[
            "ALERT: {root_service} CPU at 100%. Autoscaler triggered but new instances failing to start.",
            "ALERT: P1 -- Thundering herd detected. {root_service} overwhelmed by connection spike.",
        ],
        root_service_layer="infrastructure",
    ),
    FaultPattern(
        name="dns-failure",
        fault_type="dns_failure",
        remediation="flush_dns",
        log_category="generic",
        root_metric_signature={"cpu_pct": 10.0, "memory_pct": 30.0, "error_rate_pct": 45.0, "latency_p99_ms": 5000.0, "requests_per_sec": 20.0},
        cascade_effect="error_propagation",
        summary_templates=[
            "ALERT: DNS resolution failures across multiple services. Intermittent connectivity issues.",
            "ALERT: P1 -- Service discovery degraded. DNS SERVFAIL rate spiking.",
        ],
        root_service_layer="infrastructure",
    ),
    FaultPattern(
        name="memory-leak",
        fault_type="memory_leak",
        remediation="restart",
        log_category="java_oom",
        root_metric_signature={"cpu_pct": 35.0, "memory_pct": 95.0, "error_rate_pct": 40.0, "latency_p99_ms": 3000.0, "requests_per_sec": 50.0},
        cascade_effect="timeout",
        summary_templates=[
            "ALERT: {root_service} memory usage climbing steadily. Slow degradation over hours.",
            "ALERT: P2 -- Gradual latency increase in {root_service}. Memory pressure building.",
        ],
        root_service_layer="application",
    ),
    FaultPattern(
        name="thread-deadlock",
        fault_type="thread_deadlock",
        remediation="kill_threads",
        log_category="generic",
        root_metric_signature={"cpu_pct": 5.0, "memory_pct": 60.0, "error_rate_pct": 100.0, "latency_p99_ms": 30000.0, "requests_per_sec": 0.0},
        cascade_effect="timeout",
        summary_templates=[
            "ALERT: {root_service} completely unresponsive. All requests timing out. Thread pool exhausted.",
            "ALERT: P1 -- {root_service} hung. Zero throughput detected despite low CPU.",
        ],
        root_service_layer="application",
    ),
]

EASY_PATTERNS = [p for p in FAULT_PATTERNS if p.name in ("java-oom", "disk-full-db", "cert-expired")]
MEDIUM_PATTERNS = [p for p in FAULT_PATTERNS if p.name in ("connection-leak", "config-push", "thundering-herd")]
HARD_PATTERNS = [p for p in FAULT_PATTERNS if p.name in ("disk-full-kafka", "dns-failure", "memory-leak", "thread-deadlock")]


# ------------------------------------------------------------------
# Service name pools by architectural layer
# ------------------------------------------------------------------

SERVICE_POOLS: dict[str, list[str]] = {
    "gateway": ["api-gateway", "edge-proxy", "load-balancer", "grpc-gateway"],
    "application": [
        "auth-service", "user-service", "order-service", "payment-service",
        "search-service", "notification-service", "inventory-service",
        "billing-service", "catalog-service", "session-service",
        "profile-service", "analytics-service",
    ],
    "data": ["postgres-db", "mysql-db", "redis-cache", "elasticsearch", "cassandra-db", "mongo-db"],
    "infrastructure": [
        "kafka-broker", "kafka-consumer", "rabbitmq", "config-service",
        "cert-manager", "dns-resolver", "network-controller", "service-mesh",
    ],
    "observability": ["monitoring-pipeline", "metrics-collector", "log-aggregator"],
    "ml": ["ml-model-server", "feature-store", "recommendation-service", "prediction-gateway"],
}


# ------------------------------------------------------------------
# Cascade metric signatures for non-root-cause services
# ------------------------------------------------------------------

CASCADE_METRICS: dict[str, dict] = {
    "error_propagation": {
        "cpu_pct": 20.0, "memory_pct": 45.0, "error_rate_pct": 90.0,
        "latency_p99_ms": 5100.0, "requests_per_sec": 30.0,
    },
    "timeout": {
        "cpu_pct": 15.0, "memory_pct": 40.0, "error_rate_pct": 60.0,
        "latency_p99_ms": 10000.0, "requests_per_sec": 15.0,
    },
    "stale_data": {
        "cpu_pct": 10.0, "memory_pct": 35.0, "error_rate_pct": 0.0,
        "latency_p99_ms": 30.0, "requests_per_sec": 100.0,
    },
    "connection_exhaust": {
        "cpu_pct": 25.0, "memory_pct": 50.0, "error_rate_pct": 70.0,
        "latency_p99_ms": 8000.0, "requests_per_sec": 10.0,
    },
}


# ------------------------------------------------------------------
# Red herring log lines for bystander services
# ------------------------------------------------------------------

RED_HERRING_LOGS = [
    "{ts} [WARN] gc.G1: GC pause 175ms (within threshold)",
    "{ts} [INFO] cache.Redis: Cache miss rate 12% (normal range)",
    "{ts} [ERROR] http.Client: Connection reset by peer (retry 1/3 succeeded)",
    "{ts} [WARN] pool.ThreadPool: Thread pool utilization 78% -- monitoring",
    "{ts} [INFO] health.Check: Dependency check passed (latency: 45ms)",
    "{ts} [WARN] service.Metrics: Slow query detected: 250ms (threshold: 500ms)",
]


# ------------------------------------------------------------------
# Noise alert templates
# ------------------------------------------------------------------

NOISE_ALERTS = [
    {"name": "RoutineGC", "severity": "warning", "service": "{svc}", "message": "GC pause exceeded 200ms", "status": "resolved"},
    {"name": "CacheMissSpike", "severity": "warning", "service": "{svc}", "message": "Cache miss rate above 10%", "status": "resolved"},
    {"name": "HighLatencyP95", "severity": "P3", "service": "{svc}", "message": "P95 latency above threshold for 2 minutes", "status": "resolved"},
    {"name": "DiskUsageWarning", "severity": "warning", "service": "{svc}", "message": "Disk usage at 72%", "status": "resolved"},
    {"name": "BatchJobDelayed", "severity": "warning", "service": "{svc}", "message": "Scheduled batch 5m overdue", "status": "resolved"},
]


# ------------------------------------------------------------------
# ProceduralScenarioGenerator
# ------------------------------------------------------------------

class ProceduralScenarioGenerator:
    """Generates unique SRE incident scenarios using composable fault patterns and networkx DAGs."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def generate(self, difficulty: str) -> dict:
        """Generate a complete scenario dict for the given difficulty."""
        if difficulty not in ("easy", "medium", "hard"):
            raise ValueError(f"Unknown difficulty '{difficulty}'. Must be one of: easy, medium, hard")

        pattern = self._pick_fault_pattern(difficulty)
        graph, root_service, causal_chain, all_services = self._build_topology(difficulty, pattern)
        topology = {svc: list(graph.successors(svc)) for svc in graph.nodes}
        causal_distances = self._compute_causal_distances(graph, root_service, causal_chain)

        base_time = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        scenario_id = f"{difficulty}-gen-{pattern.fault_type}-{self._rng.randint(0, 0xFFFF):04x}"

        logs = self._synthesize_logs(all_services, root_service, causal_chain, pattern, base_time)
        metrics_baseline = self._generate_baseline_metrics(all_services)
        metrics_crisis = self._generate_crisis_metrics(all_services, root_service, causal_chain, pattern)
        alerts = self._generate_alerts(all_services, causal_chain, pattern, base_time)
        traces = self._generate_traces(causal_chain, pattern)
        summary = self._rng.choice(pattern.summary_templates).format(root_service=root_service)

        scenario = {
            "id": scenario_id,
            "real_incident_ref": f"procedural-{pattern.name}",
            "incident_summary": summary,
            "services": all_services,
            "topology": topology,
            "root_cause": {
                "service": root_service,
                "fault_type": pattern.fault_type,
                "remediation": pattern.remediation,
            },
            "causal_chain": causal_chain,
            "logs": logs,
            "metrics_baseline": metrics_baseline,
            "metrics_crisis": metrics_crisis,
            "metrics": metrics_crisis,
            "alerts": alerts,
            "traces": traces,
            "causal_distances": causal_distances,
        }

        if difficulty == "hard":
            scenario["blind_metrics"] = self._generate_blind_metrics(all_services, causal_chain)

        return scenario

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _pick_fault_pattern(self, difficulty: str) -> FaultPattern:
        pools = {"easy": EASY_PATTERNS, "medium": MEDIUM_PATTERNS, "hard": HARD_PATTERNS}
        return self._rng.choice(pools[difficulty])

    def _pick_services(self, layer: str, count: int, exclude: set[str] | None = None) -> list[str]:
        exclude = exclude or set()
        available = [s for s in SERVICE_POOLS.get(layer, []) if s not in exclude]
        count = min(count, len(available))
        return self._rng.sample(available, count)

    def _build_topology(self, difficulty: str, pattern: FaultPattern) -> tuple[nx.DiGraph, str, list[str], list[str]]:
        """Build a microservice DAG and select root cause + causal chain."""
        G = nx.DiGraph()
        used: set[str] = set()

        # Always have a gateway entry point
        gateway = self._pick_services("gateway", 1)[0]
        used.add(gateway)
        G.add_node(gateway)

        if difficulty == "easy":
            return self._build_easy_topology(G, gateway, used, pattern)
        elif difficulty == "medium":
            return self._build_medium_topology(G, gateway, used, pattern)
        else:
            return self._build_hard_topology(G, gateway, used, pattern)

    def _build_easy_topology(self, G: nx.DiGraph, gateway: str, used: set, pattern: FaultPattern) -> tuple[nx.DiGraph, str, list[str], list[str]]:
        """3-4 node linear chain."""
        root_service = self._pick_services(pattern.root_service_layer, 1, used)[0]
        used.add(root_service)
        G.add_node(root_service)

        # Gateway depends on an app service (or root if root is app layer)
        if pattern.root_service_layer in ("data", "infrastructure"):
            mid = self._pick_services("application", 1, used)[0]
            used.add(mid)
            G.add_node(mid)
            G.add_edge(gateway, mid)
            G.add_edge(mid, root_service)
            causal_chain = [root_service, mid] if self._rng.random() > 0.5 else [root_service]
        else:
            # Root is app layer -- add a data dependency to ensure >= 3 services
            G.add_edge(gateway, root_service)
            data_dep = self._pick_services("data", 1, used)
            if data_dep:
                used.add(data_dep[0])
                G.add_node(data_dep[0])
                G.add_edge(root_service, data_dep[0])
            causal_chain = [root_service]

        # Ensure minimum 3 services
        while len(G.nodes) < 3:
            layers = ["application", "data"]
            bystander = self._pick_services(self._rng.choice(layers), 1, used)
            if bystander:
                used.add(bystander[0])
                G.add_node(bystander[0])
                G.add_edge(gateway, bystander[0])
            else:
                break

        # Maybe add a 4th bystander
        if len(G.nodes) < 4 and self._rng.random() > 0.5:
            layers = ["application", "data"]
            bystander = self._pick_services(self._rng.choice(layers), 1, used)
            if bystander:
                used.add(bystander[0])
                G.add_node(bystander[0])
                G.add_edge(gateway, bystander[0])

        all_services = list(G.nodes)
        assert nx.is_directed_acyclic_graph(G)
        return G, root_service, causal_chain, all_services

    def _build_medium_topology(self, G: nx.DiGraph, gateway: str, used: set, pattern: FaultPattern) -> tuple[nx.DiGraph, str, list[str], list[str]]:
        """4-6 nodes, fanout with bottleneck."""
        root_service = self._pick_services(pattern.root_service_layer, 1, used)[0]
        used.add(root_service)
        G.add_node(root_service)

        # Build cascade path: gateway -> app1 -> app2 -> root (or gateway -> app1 -> root)
        app_services = self._pick_services("application", 2, used)
        for svc in app_services:
            used.add(svc)
            G.add_node(svc)

        if len(app_services) >= 2:
            G.add_edge(gateway, app_services[0])
            G.add_edge(gateway, app_services[1])
            G.add_edge(app_services[0], root_service)
            G.add_edge(app_services[1], root_service)
            causal_chain = [root_service, app_services[0], app_services[1]]
        else:
            G.add_edge(gateway, app_services[0])
            G.add_edge(app_services[0], root_service)
            causal_chain = [root_service, app_services[0]]

        # Add 1-2 bystanders
        for _ in range(self._rng.randint(1, 2)):
            layers = ["application", "data", "observability"]
            bystander = self._pick_services(self._rng.choice(layers), 1, used)
            if bystander:
                used.add(bystander[0])
                G.add_node(bystander[0])
                G.add_edge(gateway, bystander[0])

        all_services = list(G.nodes)
        assert nx.is_directed_acyclic_graph(G)
        return G, root_service, causal_chain, all_services

    def _build_hard_topology(self, G: nx.DiGraph, gateway: str, used: set, pattern: FaultPattern) -> tuple[nx.DiGraph, str, list[str], list[str]]:
        """6-9 nodes, deep tree with multiple paths."""
        root_service = self._pick_services(pattern.root_service_layer, 1, used)[0]
        used.add(root_service)
        G.add_node(root_service)

        # Build deep cascade: gateway -> app1 -> app2 -> infra -> root
        app_layer = self._pick_services("application", 3, used)
        for svc in app_layer:
            used.add(svc)
            G.add_node(svc)

        # Layer 1: gateway -> app services
        G.add_edge(gateway, app_layer[0])
        if len(app_layer) > 1:
            G.add_edge(gateway, app_layer[1])

        # Layer 2: app -> deeper app/infra
        infra = self._pick_services("infrastructure", 1, used)
        if infra:
            used.add(infra[0])
            G.add_node(infra[0])
            G.add_edge(app_layer[0], infra[0])
            if len(app_layer) > 1:
                G.add_edge(app_layer[1], infra[0])
            G.add_edge(infra[0], root_service)
            causal_chain = [root_service, infra[0], app_layer[0]]
            if len(app_layer) > 1:
                causal_chain.append(app_layer[1])
        else:
            G.add_edge(app_layer[0], root_service)
            causal_chain = [root_service, app_layer[0]]

        # Add deeper app connection
        if len(app_layer) > 2:
            G.add_edge(app_layer[0], app_layer[2])
            G.add_edge(app_layer[2], root_service)
            if app_layer[2] not in causal_chain:
                causal_chain.append(app_layer[2])

        # Add 2-3 bystanders
        for _ in range(self._rng.randint(2, 3)):
            layers = ["application", "data", "observability", "ml"]
            bystander = self._pick_services(self._rng.choice(layers), 1, used)
            if bystander:
                used.add(bystander[0])
                G.add_node(bystander[0])
                parent = self._rng.choice([gateway] + app_layer[:2])
                G.add_edge(parent, bystander[0])

        all_services = list(G.nodes)
        assert nx.is_directed_acyclic_graph(G)
        return G, root_service, causal_chain, all_services

    def _compute_causal_distances(self, G: nx.DiGraph, root_service: str, causal_chain: list[str]) -> dict[str, int]:
        """Compute hop distance from root cause for each service."""
        distances: dict[str, int] = {}
        for i, svc in enumerate(causal_chain):
            distances[svc] = i
        for svc in G.nodes:
            if svc not in distances:
                distances[svc] = len(causal_chain) + 1
        return distances

    def _synthesize_logs(self, all_services: list[str], root_service: str, causal_chain: list[str],
                         pattern: FaultPattern, base_time: datetime) -> dict[str, list[str]]:
        """Generate realistic log lines for each service."""
        logs: dict[str, list[str]] = {}
        causal_set = set(causal_chain)

        for svc in all_services:
            if svc == root_service:
                logs[svc] = self._root_cause_logs(svc, pattern, base_time)
            elif svc in causal_set:
                logs[svc] = self._cascade_logs(svc, root_service, pattern, base_time)
            else:
                logs[svc] = self._bystander_logs(svc, base_time)

        return logs

    def _root_cause_logs(self, service: str, pattern: FaultPattern, base_time: datetime) -> list[str]:
        templates = get_templates(pattern.log_category)
        lines: list[str] = []
        t = base_time + timedelta(minutes=self._rng.randint(10, 15))

        # Fill templates with realistic parameter values
        params = self._make_log_params(service, pattern)

        for template in templates[:self._rng.randint(5, min(8, len(templates)))]:
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                line = template.format(ts=ts, **params)
            except KeyError:
                line = f"{ts} [ERROR] {service}: Fault detected -- {pattern.fault_type}"
            lines.append(line)
            t += timedelta(seconds=self._rng.randint(1, 30))

        return lines

    def _cascade_logs(self, service: str, root_service: str, pattern: FaultPattern, base_time: datetime) -> list[str]:
        templates = get_templates("http_gateway") + get_templates("generic")
        lines: list[str] = []
        t = base_time + timedelta(minutes=self._rng.randint(14, 18))

        params = {
            "name": service.split("-")[0],
            "upstream": root_service,
            "dep": root_service,
            "method": self._rng.choice(["GET", "POST", "PUT"]),
            "path": self._rng.choice(["/api/v1/data", "/api/v1/health", "/internal/rpc"]),
            "status": self._rng.choice(["503", "504", "502"]),
            "latency_ms": str(self._rng.randint(5000, 15000)),
            "timeout": str(self._rng.randint(5000, 30000)),
            "rate": str(self._rng.randint(50, 100)),
            "state": "UNHEALTHY",
            "req_id": f"req-{self._rng.randint(1000, 9999)}",
            "ms": str(self._rng.randint(5000, 30000)),
            "error": f"connection to {root_service} refused",
            "pct": str(self._rng.randint(50, 100)),
            "reason": f"{root_service} unreachable",
        }

        selected = self._rng.sample(templates, min(self._rng.randint(5, 8), len(templates)))
        for template in selected:
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                line = template.format(ts=ts, **params)
            except KeyError:
                line = f"{ts} [ERROR] {service}: Upstream {root_service} unreachable"
            lines.append(line)
            t += timedelta(seconds=self._rng.randint(1, 20))

        return lines

    def _bystander_logs(self, service: str, base_time: datetime) -> list[str]:
        lines: list[str] = []
        t = base_time + timedelta(minutes=self._rng.randint(8, 12))

        # Normal operation logs
        for _ in range(self._rng.randint(3, 5)):
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            lines.append(f"{ts} [INFO] service.{service.split('-')[0]}: Health check: OK")
            t += timedelta(seconds=self._rng.randint(10, 60))

        # 1-2 red herrings
        for _ in range(self._rng.randint(1, 2)):
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            herring = self._rng.choice(RED_HERRING_LOGS).format(ts=ts)
            lines.append(herring)
            t += timedelta(seconds=self._rng.randint(5, 30))

        return lines

    def _make_log_params(self, service: str, pattern: FaultPattern) -> dict:
        """Generate realistic parameter values for log templates."""
        base = {
            "name": service.split("-")[0],
            "pause_ms": str(self._rng.randint(2000, 6000)),
            "used_gb": f"{self._rng.uniform(3.5, 3.9):.1f}",
            "max_gb": "4.0",
            "pct": str(self._rng.randint(95, 100)),
            "alloc_mb": str(self._rng.randint(128, 512)),
            "component": self._rng.choice(["token-cache", "session-store", "request-buffer"]),
            "n": str(self._rng.randint(1, 3)),
            "max": "3",
            "host": service,
            "port": str(self._rng.randint(50000, 60000)),
            "user": "app",
            "db": "production",
            "client": service,
            "count": str(self._rng.randint(90, 150)),
            "idle": str(self._rng.randint(40, 80)),
            "ms": str(self._rng.randint(1, 50)),
            "query_prefix": "SELECT * FROM",
            "file": "pg_wal/000000010000",
            "used": f"{self._rng.randint(90, 100)}GB",
            "total": "100GB",
            "version": "3.6.1",
            "path": "/var/lib/kafka/data",
            "topic": self._rng.choice(["events", "metrics", "features", "orders"]),
            "lag": str(self._rng.randint(10000, 500000)),
            "active": str(self._rng.randint(90, 100)),
            "threshold": "120",
        }
        return base

    def _generate_baseline_metrics(self, all_services: list[str]) -> dict[str, dict]:
        metrics: dict[str, dict] = {}
        for svc in all_services:
            metrics[svc] = {
                "cpu_pct": round(self._rng.uniform(10, 25), 1),
                "memory_pct": round(self._rng.uniform(30, 50), 1),
                "error_rate_pct": round(self._rng.uniform(0, 1.5), 1),
                "latency_p99_ms": round(self._rng.uniform(15, 50), 1),
                "requests_per_sec": round(self._rng.uniform(80, 200), 1),
            }
        return metrics

    def _generate_crisis_metrics(self, all_services: list[str], root_service: str,
                                  causal_chain: list[str], pattern: FaultPattern) -> dict[str, dict]:
        metrics: dict[str, dict] = {}
        causal_set = set(causal_chain)
        cascade = CASCADE_METRICS.get(pattern.cascade_effect, CASCADE_METRICS["error_propagation"])

        for svc in all_services:
            if svc == root_service:
                base = dict(pattern.root_metric_signature)
                base.update(pattern.extra_metric_keys)
                metrics[svc] = base
            elif svc in causal_set:
                m = dict(cascade)
                # Add some variance
                for k, v in m.items():
                    if isinstance(v, (int, float)):
                        m[k] = round(v * self._rng.uniform(0.8, 1.2), 1)
                metrics[svc] = m
            else:
                metrics[svc] = {
                    "cpu_pct": round(self._rng.uniform(10, 25), 1),
                    "memory_pct": round(self._rng.uniform(30, 50), 1),
                    "error_rate_pct": round(self._rng.uniform(0, 2), 1),
                    "latency_p99_ms": round(self._rng.uniform(15, 50), 1),
                    "requests_per_sec": round(self._rng.uniform(80, 200), 1),
                }
        return metrics

    def _generate_alerts(self, all_services: list[str], causal_chain: list[str],
                          pattern: FaultPattern, base_time: datetime) -> list[dict]:
        alerts: list[dict] = []
        fire_time = base_time + timedelta(minutes=self._rng.randint(14, 18))

        # Real alert for the incident
        alerts.append({
            "name": f"{pattern.fault_type.replace('_', '-').title()}Detected",
            "severity": "P1",
            "service": causal_chain[0] if causal_chain else all_services[0],
            "message": f"{pattern.fault_type.replace('_', ' ')} detected on {causal_chain[0]}",
            "fired_at": fire_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

        # Secondary alert for cascade
        if len(causal_chain) > 1:
            alerts.append({
                "name": "ServiceDegraded",
                "severity": "P2",
                "service": causal_chain[1],
                "message": f"Error rate elevated on {causal_chain[1]}",
                "fired_at": (fire_time + timedelta(minutes=self._rng.randint(1, 5))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        # Noise alerts from bystanders
        bystanders = [s for s in all_services if s not in set(causal_chain)]
        noise_count = min(self._rng.randint(1, 3), len(bystanders), len(NOISE_ALERTS))
        for i in range(noise_count):
            noise = dict(NOISE_ALERTS[i % len(NOISE_ALERTS)])
            svc = self._rng.choice(bystanders) if bystanders else all_services[0]
            noise["service"] = svc
            noise["message"] = noise["message"]
            noise["fired_at"] = (fire_time - timedelta(minutes=self._rng.randint(5, 30))).strftime("%Y-%m-%dT%H:%M:%SZ")
            alerts.append(noise)

        return alerts

    def _generate_traces(self, causal_chain: list[str], pattern: FaultPattern) -> dict:
        trace_id = f"trace-gen-{self._rng.randint(1000, 9999)}"
        spans: list[dict] = []

        for i, svc in enumerate(reversed(causal_chain)):
            if i == len(causal_chain) - 1:
                # Root cause service
                spans.append({
                    "service": svc,
                    "duration_ms": self._rng.randint(10000, 30000),
                    "status": f"ERROR: {pattern.fault_type.replace('_', ' ')}",
                })
            else:
                spans.append({
                    "service": svc,
                    "duration_ms": self._rng.randint(5000, 15000),
                    "status": self._rng.choice(["timeout", "502 Bad Gateway", "503 Service Unavailable"]),
                })

        return {
            trace_id: {
                "request": self._rng.choice(["GET /api/v1/data", "POST /api/v1/orders", "GET /api/v1/users"]),
                "spans": spans,
                "outcome": f"Failed: {pattern.cascade_effect.replace('_', ' ')}",
            }
        }

    def _generate_blind_metrics(self, all_services: list[str], causal_chain: list[str]) -> dict:
        """Generate blind (stale/unavailable) metrics for hard scenarios."""
        blind: dict[str, dict] = {}
        candidates = [s for s in all_services if s in set(causal_chain)]
        if candidates:
            svc = self._rng.choice(candidates)
            blind[svc] = {
                "cpu_pct": "N/A (scrape failed)",
                "memory_pct": "N/A (scrape failed)",
                "error_rate_pct": "N/A (scrape failed)",
                "_last_scrape": "2025-04-01T09:45:00Z",
            }
        return blind
