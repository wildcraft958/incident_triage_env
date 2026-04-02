"""
Scenario definitions for the incident triage RL environment.

Each scenario is a dict following the structure in GUIDELINES.md.
Logs are adapted from log_templates.py patterns to feel like real production output.
Incidents are grounded in real post-mortems tracked in real_incidents.py.
"""

from typing import Dict, List


# ----------------------------------------------------------------------
# EASY SCENARIOS
# ----------------------------------------------------------------------

_easy_oom_001: Dict = {
    "id": "easy-oom-001",
    "real_incident_ref": "common-java-oom",
    "incident_summary": (
        "ALERT: auth-service is DOWN. PagerDuty fired P1. "
        "Health check /health returning 503. Upstream api-gateway reporting "
        "connection refused to auth-service."
    ),
    "services": ["auth-service", "api-gateway", "user-db"],
    "topology": {
        "api-gateway": ["auth-service"],
        "auth-service": ["user-db"],
        "user-db": [],
    },
    "root_cause": {
        "service": "auth-service",
        "fault_type": "oom",
        "remediation": "restart",
    },
    "causal_chain": ["auth-service"],
    "logs": {
        "auth-service": [
            "2025-04-01T10:14:42Z [WARN] gc.GarbageCollector: GC pause (G1 Evacuation Pause) 4120ms -- heap 3.8GB/4.0GB",
            "2025-04-01T10:14:51Z [WARN] mem.HeapMonitor: Heap memory usage at 97% (3.88GB/4.0GB)",
            "2025-04-01T10:14:55Z [ERROR] java.lang.OutOfMemoryError: Java heap space",
            "2025-04-01T10:14:55Z [ERROR] java.lang.OutOfMemoryError: GC overhead limit exceeded",
            "2025-04-01T10:14:56Z [ERROR] mem.HeapMonitor: Failed to allocate 256MB for token-cache",
            "2025-04-01T10:14:57Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 1/3)",
            "2025-04-01T10:15:02Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 2/3)",
            "2025-04-01T10:15:10Z [ERROR] runtime.ServiceRunner: Restart failed -- insufficient memory",
        ],
        "api-gateway": [
            "2025-04-01T10:14:58Z [INFO] gateway.Router: Routing POST /api/v1/login -> auth-service",
            "2025-04-01T10:14:59Z [ERROR] gateway.Router: auth-service request timed out after 5000ms",
            "2025-04-01T10:15:00Z [WARN] gateway.CircuitBreaker: auth-service error rate above threshold: 100%",
            "2025-04-01T10:15:01Z [WARN] gateway.CircuitBreaker: auth-service circuit breaker OPEN",
            "2025-04-01T10:15:03Z [INFO] gateway.HealthCheck: Health check to auth-service: UNHEALTHY",
            "2025-04-01T10:15:05Z [ERROR] gateway.Router: Upstream auth-service returned 503",
        ],
        "user-db": [
            "2025-04-01T10:14:40Z [INFO] postgres: connection received: host=auth-service port=54312",
            "2025-04-01T10:14:41Z [INFO] postgres: connection authorized: user=auth database=users",
            "2025-04-01T10:14:50Z [INFO] postgres: Query executed in 3ms: SELECT * FROM sessions WHERE",
            "2025-04-01T10:15:00Z [INFO] postgres: Query executed in 4ms: SELECT * FROM users WHERE",
            "2025-04-01T10:15:10Z [INFO] postgres: connection received: host=auth-service port=54318",
            "2025-04-01T10:15:11Z [INFO] postgres: connection authorized: user=auth database=users",
        ],
    },
    "metrics": {
        "auth-service": {
            "cpu_pct": 12.0,
            "memory_pct": 99.1,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
        },
        "api-gateway": {
            "cpu_pct": 18.0,
            "memory_pct": 41.0,
            "error_rate_pct": 95.0,
            "latency_p99_ms": 5100.0,
            "requests_per_sec": 310.0,
        },
        "user-db": {
            "cpu_pct": 8.0,
            "memory_pct": 35.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 5.0,
            "requests_per_sec": 42.0,
        },
    },
    "alerts": [
        {
            "name": "AuthServiceDown",
            "severity": "P1",
            "service": "auth-service",
            "message": "auth-service health check failing -- 503 for >2 min",
            "fired_at": "2025-04-01T10:15:03Z",
        },
        {
            "name": "GatewayErrorRateHigh",
            "severity": "P2",
            "service": "api-gateway",
            "message": "api-gateway error rate 95% (threshold: 5%)",
            "fired_at": "2025-04-01T10:15:05Z",
        },
    ],
    "traces": {
        "trace-001": {
            "trace_id": "a1b2c3d4e5f6",
            "request": "POST /api/v1/login",
            "spans": [
                {"service": "api-gateway", "duration_ms": 5001, "status": "error"},
                {"service": "auth-service", "duration_ms": 5000, "status": "timeout"},
            ],
            "outcome": "timeout",
        }
    },
}

_easy_disk_001: Dict = {
    "id": "easy-disk-001",
    "real_incident_ref": "common-disk-full",
    "incident_summary": (
        "ALERT: user-db write failures detected. auth-service reporting database "
        "errors. Postgres disk usage alarm triggered. Writes failing across the board."
    ),
    "services": ["user-db", "auth-service", "api-gateway"],
    "topology": {
        "api-gateway": ["auth-service"],
        "auth-service": ["user-db"],
        "user-db": [],
    },
    "root_cause": {
        "service": "user-db",
        "fault_type": "disk_full",
        "remediation": "clear_disk",
    },
    "causal_chain": ["user-db", "auth-service"],
    "logs": {
        "user-db": [
            "2025-04-01T09:50:10Z [INFO] postgres: connection received: host=auth-service port=52210",
            "2025-04-01T09:50:11Z [INFO] postgres: connection authorized: user=auth database=users",
            "2025-04-01T09:51:00Z [WARN] postgres: Disk usage: 88% (440GB/500GB)",
            "2025-04-01T09:58:22Z [WARN] postgres: Disk usage: 96% (480GB/500GB)",
            "2025-04-01T10:03:15Z [ERROR] postgres: PANIC: could not write to file 'pg_wal/000000010000003700000001': No space left on device",
            "2025-04-01T10:03:15Z [ERROR] postgres: Disk usage: 100% (500GB/500GB)",
            "2025-04-01T10:03:16Z [FATAL] postgres: Database entering read-only mode",
            "2025-04-01T10:03:20Z [ERROR] postgres: FATAL: remaining connection slots are reserved for superuser",
        ],
        "auth-service": [
            "2025-04-01T10:03:17Z [INFO] service.auth-service: Processing request req_id=req-9812",
            "2025-04-01T10:03:18Z [ERROR] service.auth-service: user-db timed out after 5000ms",
            "2025-04-01T10:03:19Z [ERROR] service.auth-service: Failed to process request: could not persist session token",
            "2025-04-01T10:03:20Z [WARN] service.auth-service: 100% of requests failing due to database write errors",
            "2025-04-01T10:03:21Z [ERROR] service.auth-service: Failed to process request: database is in read-only mode",
            "2025-04-01T10:03:25Z [ERROR] service.auth-service: Failed to process request: database is in read-only mode",
            "2025-04-01T10:03:30Z [WARN] service.auth-service: Slow response from user-db: 5012ms",
        ],
        "api-gateway": [
            "2025-04-01T10:03:18Z [INFO] gateway.Router: Routing POST /api/v1/login -> auth-service",
            "2025-04-01T10:03:22Z [ERROR] gateway.Router: Upstream auth-service returned 500",
            "2025-04-01T10:03:23Z [WARN] gateway.CircuitBreaker: auth-service error rate above threshold: 80%",
            "2025-04-01T10:03:25Z [INFO] gateway.HealthCheck: Health check to auth-service: DEGRADED",
            "2025-04-01T10:03:28Z [INFO] gateway.Router: Routing GET /api/v1/profile -> auth-service",
            "2025-04-01T10:03:29Z [ERROR] gateway.Router: Upstream auth-service returned 500",
        ],
    },
    "metrics": {
        "user-db": {
            "cpu_pct": 45.0,
            "memory_pct": 60.0,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
            "disk_usage_pct": 100.0,
        },
        "auth-service": {
            "cpu_pct": 22.0,
            "memory_pct": 48.0,
            "error_rate_pct": 98.0,
            "latency_p99_ms": 5020.0,
            "requests_per_sec": 85.0,
        },
        "api-gateway": {
            "cpu_pct": 17.0,
            "memory_pct": 39.0,
            "error_rate_pct": 85.0,
            "latency_p99_ms": 5100.0,
            "requests_per_sec": 290.0,
        },
    },
    "alerts": [
        {
            "name": "PostgresDiskFull",
            "severity": "P1",
            "service": "user-db",
            "message": "user-db disk usage at 100% -- database entering read-only mode",
            "fired_at": "2025-04-01T10:03:16Z",
        },
        {
            "name": "AuthServiceErrorRate",
            "severity": "P2",
            "service": "auth-service",
            "message": "auth-service error rate 98% (threshold: 5%)",
            "fired_at": "2025-04-01T10:03:22Z",
        },
    ],
    "traces": {
        "trace-001": {
            "trace_id": "b2c3d4e5f6a1",
            "request": "POST /api/v1/login",
            "spans": [
                {"service": "api-gateway", "duration_ms": 5050, "status": "error"},
                {"service": "auth-service", "duration_ms": 5010, "status": "error"},
                {"service": "user-db", "duration_ms": 5000, "status": "error"},
            ],
            "outcome": "error: database write failed",
        }
    },
}

EASY_SCENARIOS: List[Dict] = [_easy_oom_001, _easy_disk_001]


# ----------------------------------------------------------------------
# MEDIUM SCENARIOS
# ----------------------------------------------------------------------

_medium_connleak_001: Dict = {
    "id": "medium-connleak-001",
    "real_incident_ref": "github-connection-leak",
    "incident_summary": (
        "ALERT: order-service error rate spiking to 60%. Customers unable to "
        "complete checkout. api-gateway reporting upstream timeouts. inventory-service "
        "appears healthy. Issue started ~2 hours ago and is gradually worsening."
    ),
    "services": [
        "postgres-db",
        "inventory-service",
        "order-service",
        "api-gateway",
        "payment-service",
    ],
    "topology": {
        "api-gateway": ["order-service", "payment-service"],
        "order-service": ["postgres-db", "inventory-service"],
        "inventory-service": ["postgres-db"],
        "payment-service": ["postgres-db"],
        "postgres-db": [],
    },
    "root_cause": {
        "service": "postgres-db",
        "fault_type": "connection_leak",
        "remediation": "increase_pool",
    },
    "causal_chain": ["postgres-db", "inventory-service", "order-service", "api-gateway"],
    "logs": {
        "postgres-db": [
            "2025-04-01T08:10:05Z [INFO] postgres: connection received: host=order-service port=61001",
            "2025-04-01T08:10:05Z [INFO] postgres: connection authorized: user=orders database=shop",
            "2025-04-01T08:30:12Z [WARN] postgres: Connection count: 80/100 -- approaching max_connections",
            "2025-04-01T08:45:31Z [WARN] postgres: Client order-service holding 52 connections (48 IDLE)",
            "2025-04-01T09:00:44Z [WARN] postgres: Connection count: 95/100 -- approaching max_connections",
            "2025-04-01T09:15:02Z [WARN] postgres: Client order-service holding 71 connections (66 IDLE)",
            "2025-04-01T09:58:19Z [ERROR] postgres: FATAL: too many connections for role 'orders'",
            "2025-04-01T09:58:20Z [ERROR] postgres: FATAL: remaining connection slots are reserved for superuser",
            "2025-04-01T09:58:21Z [INFO] postgres: Query executed in 2ms: SELECT inventory_id FROM",
        ],
        "inventory-service": [
            "2025-04-01T09:55:00Z [INFO] service.inventory-service: Processing request req_id=req-7723",
            "2025-04-01T09:55:01Z [WARN] pool.ConnectionPool: Waiting for connection from pool...",
            "2025-04-01T09:55:04Z [WARN] pool.ConnectionPool: Acquired connection after 3012ms wait",
            "2025-04-01T09:58:15Z [WARN] pool.ConnectionPool: Waiting for connection from pool...",
            "2025-04-01T09:58:20Z [ERROR] pool.ConnectionPool: Connection pool wait timeout: 5000ms",
            "2025-04-01T09:58:20Z [ERROR] pool.ConnectionPool: Cannot acquire connection -- pool full",
            "2025-04-01T09:58:25Z [WARN] pool.ConnectionPool: 66 connections idle for >300s (possible connection leak)",
        ],
        "order-service": [
            "2025-04-01T09:55:05Z [INFO] service.order-service: Processing request req_id=req-4491",
            "2025-04-01T09:55:06Z [ERROR] service.order-service: inventory-service timed out after 5000ms",
            "2025-04-01T09:55:07Z [ERROR] service.order-service: Failed to process request: inventory unavailable",
            "2025-04-01T09:58:22Z [ERROR] pool.ConnectionPool: Connection pool exhausted: 100/100 connections in use",
            "2025-04-01T09:58:23Z [ERROR] pool.ConnectionPool: Cannot acquire connection -- pool full",
            "2025-04-01T09:58:24Z [ERROR] service.order-service: Failed to process request: connection pool exhausted",
            "2025-04-01T09:58:28Z [WARN] service.order-service: 60% of requests failing due to database connection errors",
        ],
        "api-gateway": [
            "2025-04-01T09:55:08Z [INFO] gateway.Router: Routing POST /api/v1/orders -> order-service",
            "2025-04-01T09:55:10Z [ERROR] gateway.Router: Upstream order-service returned 503",
            "2025-04-01T09:58:25Z [WARN] gateway.CircuitBreaker: order-service error rate above threshold: 62%",
            "2025-04-01T09:58:30Z [INFO] gateway.Router: Routing POST /api/v1/payment -> payment-service",
            "2025-04-01T09:58:31Z [INFO] gateway.Router: payment-service response: 200 (45ms)",
            "2025-04-01T09:58:35Z [INFO] gateway.HealthCheck: Health check to payment-service: HEALTHY",
            "2025-04-01T09:58:36Z [ERROR] gateway.Router: order-service request timed out after 5000ms",
        ],
        "payment-service": [
            "2025-04-01T09:55:00Z [INFO] service.payment-service: Processing request req_id=req-8810",
            "2025-04-01T09:55:01Z [INFO] service.payment-service: Request completed in 41ms",
            "2025-04-01T09:58:00Z [INFO] service.payment-service: Service healthy -- all nominal",
            "2025-04-01T09:58:10Z [INFO] service.payment-service: Request completed in 38ms",
            "2025-04-01T09:58:20Z [INFO] service.payment-service: Request completed in 43ms",
            "2025-04-01T09:58:30Z [INFO] service.payment-service: Health check: OK",
        ],
    },
    "metrics": {
        "postgres-db": {
            "cpu_pct": 55.0,
            "memory_pct": 70.0,
            "error_rate_pct": 40.0,
            "latency_p99_ms": 120.0,
            "requests_per_sec": 180.0,
        },
        "inventory-service": {
            "cpu_pct": 30.0,
            "memory_pct": 45.0,
            "error_rate_pct": 35.0,
            "latency_p99_ms": 5100.0,
            "requests_per_sec": 95.0,
        },
        "order-service": {
            "cpu_pct": 28.0,
            "memory_pct": 50.0,
            "error_rate_pct": 60.0,
            "latency_p99_ms": 5200.0,
            "requests_per_sec": 110.0,
        },
        "api-gateway": {
            "cpu_pct": 22.0,
            "memory_pct": 38.0,
            "error_rate_pct": 55.0,
            "latency_p99_ms": 5300.0,
            "requests_per_sec": 400.0,
        },
        "payment-service": {
            "cpu_pct": 18.0,
            "memory_pct": 32.0,
            "error_rate_pct": 0.2,
            "latency_p99_ms": 55.0,
            "requests_per_sec": 90.0,
        },
    },
    "alerts": [
        {
            "name": "OrderServiceErrorRate",
            "severity": "P1",
            "service": "order-service",
            "message": "order-service error rate 60% (threshold: 5%)",
            "fired_at": "2025-04-01T09:58:28Z",
        },
        {
            "name": "PostgresConnectionsHigh",
            "severity": "P2",
            "service": "postgres-db",
            "message": "postgres-db active connections 100/100 -- at max_connections",
            "fired_at": "2025-04-01T09:58:22Z",
        },
    ],
    "traces": {
        "trace-001": {
            "trace_id": "c3d4e5f6a1b2",
            "request": "POST /api/v1/orders",
            "spans": [
                {"service": "api-gateway", "duration_ms": 5050, "status": "error"},
                {"service": "order-service", "duration_ms": 5020, "status": "error"},
                {"service": "inventory-service", "duration_ms": 5000, "status": "error"},
                {"service": "postgres-db", "duration_ms": 0, "status": "rejected: too many connections"},
            ],
            "outcome": "error: connection pool exhausted",
        },
        "trace-002": {
            "trace_id": "d4e5f6a1b2c3",
            "request": "POST /api/v1/payment",
            "spans": [
                {"service": "api-gateway", "duration_ms": 50, "status": "ok"},
                {"service": "payment-service", "duration_ms": 42, "status": "ok"},
                {"service": "postgres-db", "duration_ms": 3, "status": "ok"},
            ],
            "outcome": "ok",
        },
    },
}

_medium_config_001: Dict = {
    "id": "medium-config-001",
    "real_incident_ref": "crowdstrike-config-push",
    "incident_summary": (
        "ALERT: Multiple worker services crashing simultaneously. worker-service-a "
        "and worker-service-b both paging at 10:22 UTC. Errors appear unrelated. "
        "api-gateway healthy. monitoring-service healthy. Engineering investigating."
    ),
    "services": [
        "config-service",
        "worker-service-a",
        "worker-service-b",
        "api-gateway",
        "monitoring-service",
    ],
    "topology": {
        "api-gateway": ["worker-service-a", "worker-service-b"],
        "worker-service-a": ["config-service"],
        "worker-service-b": ["config-service"],
        "monitoring-service": ["config-service"],
        "config-service": [],
    },
    "root_cause": {
        "service": "config-service",
        "fault_type": "config_error",
        "remediation": "rollback",
    },
    "causal_chain": ["config-service", "worker-service-a", "worker-service-b"],
    "logs": {
        "config-service": [
            "2025-04-01T10:21:50Z [INFO] service.config-service: Health check: OK",
            "2025-04-01T10:21:55Z [INFO] service.config-service: Processing request req_id=req-config-push-001",
            "2025-04-01T10:22:00Z [INFO] service.config-service: Config push initiated: version=2.4.7 targets=[worker-service-a, worker-service-b]",
            "2025-04-01T10:22:01Z [INFO] service.config-service: Delivered config version=2.4.7 to worker-service-a",
            "2025-04-01T10:22:01Z [INFO] service.config-service: Delivered config version=2.4.7 to worker-service-b",
            "2025-04-01T10:22:10Z [INFO] service.config-service: Health check: OK",
            "2025-04-01T10:22:20Z [INFO] service.config-service: Service healthy -- all nominal",
        ],
        "worker-service-a": [
            "2025-04-01T10:21:58Z [INFO] service.worker-service-a: Processing request req_id=req-3391",
            "2025-04-01T10:21:59Z [INFO] service.worker-service-a: Request completed in 24ms",
            "2025-04-01T10:22:02Z [INFO] service.worker-service-a: Config reload triggered -- version=2.4.7",
            "2025-04-01T10:22:02Z [ERROR] service.worker-service-a: Config parse error: unexpected token at field 'thread_pool_size' -- value '-1' out of range",
            "2025-04-01T10:22:02Z [ERROR] service.worker-service-a: Failed to apply config version=2.4.7: validation failed",
            "2025-04-01T10:22:03Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 1/3)",
            "2025-04-01T10:22:08Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 2/3)",
            "2025-04-01T10:22:15Z [ERROR] runtime.ServiceRunner: Restart failed -- config still invalid",
        ],
        "worker-service-b": [
            "2025-04-01T10:21:58Z [INFO] service.worker-service-b: Processing request req_id=req-7712",
            "2025-04-01T10:21:59Z [INFO] service.worker-service-b: Request completed in 31ms",
            "2025-04-01T10:22:02Z [INFO] service.worker-service-b: Config reload triggered -- version=2.4.7",
            "2025-04-01T10:22:03Z [ERROR] service.worker-service-b: Assertion failed: max_retries must be > 0, got 0",
            "2025-04-01T10:22:03Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 1/3)",
            "2025-04-01T10:22:08Z [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt 2/3)",
            "2025-04-01T10:22:15Z [ERROR] runtime.ServiceRunner: Restart failed -- config still invalid",
        ],
        "api-gateway": [
            "2025-04-01T10:22:05Z [ERROR] gateway.Router: Upstream worker-service-a returned 503",
            "2025-04-01T10:22:06Z [ERROR] gateway.Router: Upstream worker-service-b returned 503",
            "2025-04-01T10:22:07Z [WARN] gateway.CircuitBreaker: worker-service-a circuit breaker OPEN",
            "2025-04-01T10:22:07Z [WARN] gateway.CircuitBreaker: worker-service-b circuit breaker OPEN",
            "2025-04-01T10:22:10Z [INFO] gateway.HealthCheck: Health check to config-service: HEALTHY",
            "2025-04-01T10:22:11Z [INFO] gateway.HealthCheck: Health check to monitoring-service: HEALTHY",
        ],
        "monitoring-service": [
            "2025-04-01T10:22:00Z [INFO] service.monitoring-service: Health check: OK",
            "2025-04-01T10:22:05Z [INFO] service.monitoring-service: Scraping metrics from all services",
            "2025-04-01T10:22:06Z [INFO] service.monitoring-service: Config reload triggered -- version=2.4.7",
            "2025-04-01T10:22:06Z [INFO] service.monitoring-service: Applied config version=2.4.7: no breaking changes",
            "2025-04-01T10:22:07Z [INFO] service.monitoring-service: Request completed in 18ms",
            "2025-04-01T10:22:20Z [INFO] service.monitoring-service: Service healthy -- all nominal",
        ],
    },
    "metrics": {
        "config-service": {
            "cpu_pct": 8.0,
            "memory_pct": 22.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 15.0,
            "requests_per_sec": 5.0,
        },
        "worker-service-a": {
            "cpu_pct": 0.0,
            "memory_pct": 0.0,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
        },
        "worker-service-b": {
            "cpu_pct": 0.0,
            "memory_pct": 0.0,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
        },
        "api-gateway": {
            "cpu_pct": 15.0,
            "memory_pct": 33.0,
            "error_rate_pct": 88.0,
            "latency_p99_ms": 5050.0,
            "requests_per_sec": 250.0,
        },
        "monitoring-service": {
            "cpu_pct": 11.0,
            "memory_pct": 28.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 22.0,
            "requests_per_sec": 12.0,
        },
    },
    "alerts": [
        {
            "name": "WorkerServiceADown",
            "severity": "P1",
            "service": "worker-service-a",
            "message": "worker-service-a crash loop detected -- 3 restarts in 2 min",
            "fired_at": "2025-04-01T10:22:10Z",
        },
        {
            "name": "WorkerServiceBDown",
            "severity": "P1",
            "service": "worker-service-b",
            "message": "worker-service-b crash loop detected -- 3 restarts in 2 min",
            "fired_at": "2025-04-01T10:22:10Z",
        },
    ],
    "traces": {
        "trace-001": {
            "trace_id": "e5f6a1b2c3d4",
            "request": "POST /api/v1/jobs",
            "spans": [
                {"service": "api-gateway", "duration_ms": 5010, "status": "error"},
                {"service": "worker-service-a", "duration_ms": 0, "status": "connection refused"},
            ],
            "outcome": "error: service unavailable",
        }
    },
}

MEDIUM_SCENARIOS: List[Dict] = [_medium_connleak_001, _medium_config_001]


# ----------------------------------------------------------------------
# HARD SCENARIOS
# ----------------------------------------------------------------------

_hard_kafka_staleness_001: Dict = {
    "id": "hard-kafka-staleness-001",
    "real_incident_ref": "ml-pipeline-staleness",
    "incident_summary": (
        "ALERT: Business intelligence reports engagement drop of 18% over last 3 hours. "
        "On-call SRE investigating. All HTTP services returning 200 OK. Latencies normal. "
        "No error alerts from any service. Customer-facing recommendation feed may be degraded."
    ),
    "services": [
        "kafka-broker",
        "kafka-consumer",
        "feature-store",
        "ml-model-server",
        "recommendation-service",
        "api-gateway",
        "redis-cache",
        "user-service",
    ],
    "topology": {
        "api-gateway": ["recommendation-service", "user-service"],
        "recommendation-service": ["ml-model-server", "redis-cache"],
        "ml-model-server": ["feature-store"],
        "feature-store": ["kafka-consumer"],
        "kafka-consumer": ["kafka-broker"],
        "kafka-broker": [],
        "redis-cache": [],
        "user-service": [],
    },
    "root_cause": {
        "service": "kafka-broker",
        "fault_type": "disk_full",
        "remediation": "clear_disk",
    },
    "causal_chain": [
        "kafka-broker",
        "kafka-consumer",
        "feature-store",
        "ml-model-server",
        "recommendation-service",
    ],
    "logs": {
        "kafka-broker": [
            "2025-04-01T07:00:10Z [INFO] kafka.server.KafkaServer: Kafka version: 3.5.1",
            "2025-04-01T07:01:00Z [WARN] kafka.server.BrokerServer: Disk usage: 78% (/data/kafka: 390GB/500GB)",
            "2025-04-01T08:30:00Z [WARN] kafka.server.BrokerServer: Disk usage: 91% (/data/kafka: 455GB/500GB)",
            "2025-04-01T09:45:00Z [WARN] kafka.server.BrokerServer: Disk usage: 98% (/data/kafka: 490GB/500GB)",
            "2025-04-01T10:02:17Z [ERROR] kafka.log.LogManager: Failed to flush log segment: No space left on device",
            "2025-04-01T10:02:18Z [FATAL] kafka.server.BrokerServer: Disk full: unable to write to log segment",
            "2025-04-01T10:02:19Z [ERROR] kafka.server.BrokerServer: Broker entering degraded mode",
            "2025-04-01T10:02:20Z [ERROR] kafka.server.BrokerServer: Rejecting produce requests: disk full",
            "2025-04-01T10:02:21Z [ERROR] kafka.server.BrokerServer: Consumer fetch requests failing: log segment corrupt",
        ],
        "kafka-consumer": [
            "2025-04-01T10:00:00Z [INFO] consumer.ConsumerCoordinator: Consumed 4200 messages from topic 'user-events'",
            "2025-04-01T10:02:22Z [ERROR] consumer.ConsumerCoordinator: Failed to fetch from broker: BrokerNotAvailable",
            "2025-04-01T10:02:25Z [ERROR] consumer.ConsumerCoordinator: Retrying connection to broker (attempt 1/5)",
            "2025-04-01T10:02:30Z [ERROR] consumer.ConsumerCoordinator: Retrying connection to broker (attempt 2/5)",
            "2025-04-01T10:02:40Z [ERROR] consumer.ConsumerCoordinator: Retrying connection to broker (attempt 3/5)",
            "2025-04-01T10:03:00Z [ERROR] consumer.ConsumerCoordinator: All retry attempts failed -- broker unreachable",
            "2025-04-01T10:03:01Z [ERROR] consumer.ConsumerCoordinator: Consumer stopped -- no messages being processed",
            "2025-04-01T10:03:01Z [WARN] consumer.ConsumerCoordinator: Consumer lag: 0 messages (consumer is STOPPED)",
        ],
        "feature-store": [
            "2025-04-01T10:00:00Z [INFO] features.Store: Feature update batch received (batch_id=batch-19922)",
            "2025-04-01T10:00:01Z [INFO] features.Store: Updated 48200 feature vectors",
            "2025-04-01T10:05:00Z [WARN] features.Store: Expected feature batch not received",
            "2025-04-01T10:10:00Z [WARN] features.Store: Feature batch overdue by 10 min",
            "2025-04-01T10:15:00Z [WARN] features.Store: No feature updates in 15 min -- serving stale features",
            "2025-04-01T10:20:00Z [WARN] features.Store: Feature batch overdue by 20 min",
            "2025-04-01T10:25:00Z [ERROR] features.Store: Feature freshness SLA breached: last update 25 min ago",
            "2025-04-01T10:25:01Z [INFO] features.Store: Serving feature request for user-998812 (stale: 25 min)",
        ],
        "ml-model-server": [
            "2025-04-01T10:10:00Z [INFO] ml.ModelServer: Inference request for user 998812",
            "2025-04-01T10:10:00Z [INFO] ml.ModelServer: Fetching features from feature-store",
            "2025-04-01T10:10:01Z [INFO] ml.ModelServer: Feature vector received (dim=512)",
            "2025-04-01T10:15:00Z [WARN] ml.ModelServer: Feature staleness: last_updated=13 min ago (threshold: 5 min)",
            "2025-04-01T10:15:01Z [WARN] ml.ModelServer: Using stale features for prediction -- results may be degraded",
            "2025-04-01T10:15:01Z [INFO] ml.ModelServer: Prediction completed in 18ms",
            "2025-04-01T10:25:00Z [WARN] ml.ModelServer: Stale feature rate: 100% of requests using outdated features",
            "2025-04-01T10:25:01Z [WARN] ml.ModelServer: Feature staleness: last_updated=25 min ago (threshold: 5 min)",
        ],
        "recommendation-service": [
            "2025-04-01T10:10:00Z [INFO] service.recommendation-service: Processing request req_id=req-55901",
            "2025-04-01T10:10:02Z [INFO] service.recommendation-service: Request completed in 22ms",
            "2025-04-01T10:15:05Z [INFO] service.recommendation-service: Processing request req_id=req-55941",
            "2025-04-01T10:15:06Z [INFO] service.recommendation-service: Request completed in 19ms",
            "2025-04-01T10:20:05Z [INFO] service.recommendation-service: Processing request req_id=req-55998",
            "2025-04-01T10:20:06Z [INFO] service.recommendation-service: Request completed in 21ms",
            "2025-04-01T10:25:10Z [INFO] service.recommendation-service: Health check: OK",
            "2025-04-01T10:25:11Z [INFO] service.recommendation-service: Service healthy -- all nominal",
        ],
        "api-gateway": [
            "2025-04-01T10:10:00Z [INFO] gateway.Router: Routing GET /api/v1/recommendations -> recommendation-service",
            "2025-04-01T10:10:02Z [INFO] gateway.Router: recommendation-service response: 200 (23ms)",
            "2025-04-01T10:15:00Z [INFO] gateway.Router: Routing GET /api/v1/recommendations -> recommendation-service",
            "2025-04-01T10:15:02Z [INFO] gateway.Router: recommendation-service response: 200 (20ms)",
            "2025-04-01T10:20:00Z [INFO] gateway.Router: Routing GET /api/v1/user/profile -> user-service",
            "2025-04-01T10:20:01Z [INFO] gateway.Router: user-service response: 200 (12ms)",
            "2025-04-01T10:25:00Z [INFO] gateway.HealthCheck: Health check to recommendation-service: HEALTHY",
            "2025-04-01T10:25:01Z [INFO] gateway.HealthCheck: Health check to user-service: HEALTHY",
        ],
        "redis-cache": [
            "2025-04-01T10:10:00Z [INFO] redis.Server: Memory usage: 1.2GB/4.0GB (30%)",
            "2025-04-01T10:10:01Z [INFO] redis.Stats: Hit rate: 94%",
            "2025-04-01T10:15:00Z [INFO] redis.Keyspace: GET reco:user:998812 -- HIT",
            "2025-04-01T10:15:01Z [INFO] redis.Server: Operations/sec: 8200",
            "2025-04-01T10:20:00Z [INFO] redis.Keyspace: SET reco:user:112233 -- OK (TTL: 300s)",
            "2025-04-01T10:25:00Z [INFO] redis.Stats: Hit rate: 93%",
            "2025-04-01T10:25:01Z [INFO] redis.Connection: Connection from recommendation-service accepted",
        ],
        "user-service": [
            "2025-04-01T10:10:00Z [INFO] service.user-service: Processing request req_id=req-88112",
            "2025-04-01T10:10:01Z [INFO] service.user-service: Request completed in 11ms",
            "2025-04-01T10:15:00Z [INFO] service.user-service: Service healthy -- all nominal",
            "2025-04-01T10:15:01Z [INFO] service.user-service: Health check: OK",
            "2025-04-01T10:20:00Z [INFO] service.user-service: Processing request req_id=req-88201",
            "2025-04-01T10:20:01Z [INFO] service.user-service: Request completed in 9ms",
            "2025-04-01T10:25:00Z [INFO] service.user-service: Service healthy -- all nominal",
        ],
    },
    "metrics": {
        "kafka-broker": {
            "cpu_pct": 88.0,
            "memory_pct": 55.0,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
            "disk_usage_pct": 100.0,
        },
        "kafka-consumer": {
            "cpu_pct": 1.0,
            "memory_pct": 18.0,
            "error_rate_pct": 100.0,
            "latency_p99_ms": 0.0,
            "requests_per_sec": 0.0,
        },
        "feature-store": {
            "cpu_pct": 10.0,
            "memory_pct": 40.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 8.0,
            "requests_per_sec": 320.0,
        },
        "ml-model-server": {
            "cpu_pct": 42.0,
            "memory_pct": 60.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 25.0,
            "requests_per_sec": 290.0,
        },
        "recommendation-service": {
            "cpu_pct": 22.0,
            "memory_pct": 35.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 28.0,
            "requests_per_sec": 850.0,
        },
        "api-gateway": {
            "cpu_pct": 19.0,
            "memory_pct": 30.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 32.0,
            "requests_per_sec": 1200.0,
        },
        "redis-cache": {
            "cpu_pct": 8.0,
            "memory_pct": 30.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 1.2,
            "requests_per_sec": 8200.0,
        },
        "user-service": {
            "cpu_pct": 12.0,
            "memory_pct": 25.0,
            "error_rate_pct": 0.0,
            "latency_p99_ms": 14.0,
            "requests_per_sec": 310.0,
        },
    },
    "alerts": [
        {
            "name": "EngagementDropAlert",
            "severity": "P2",
            "service": "recommendation-service",
            "message": "Recommendation CTR dropped 18% over 3h (business metric, no technical error)",
            "fired_at": "2025-04-01T10:05:00Z",
        },
        {
            "name": "FeatureFreshnessSLABreach",
            "severity": "P3",
            "service": "feature-store",
            "message": "Feature freshness SLA breached: last update 25 min ago (SLA: 5 min)",
            "fired_at": "2025-04-01T10:25:00Z",
        },
    ],
    "traces": {
        "trace-001": {
            "trace_id": "f6a1b2c3d4e5",
            "request": "GET /api/v1/recommendations",
            "spans": [
                {"service": "api-gateway", "duration_ms": 30, "status": "200 OK"},
                {"service": "recommendation-service", "duration_ms": 22, "status": "200 OK"},
                {"service": "ml-model-server", "duration_ms": 20, "status": "200 OK"},
                {"service": "feature-store", "duration_ms": 7, "status": "200 OK (stale)"},
                {"service": "redis-cache", "duration_ms": 1, "status": "HIT"},
            ],
            "outcome": "200 OK -- but serving stale recommendations",
        }
    },
}

HARD_SCENARIOS: List[Dict] = [_hard_kafka_staleness_001]


# ----------------------------------------------------------------------
# Scenario accessor
# ----------------------------------------------------------------------

def get_scenario(task: str, index: int = 0) -> dict:
    """Return a scenario dict by difficulty task and index.

    Args:
        task: One of "easy", "medium", or "hard".
        index: Which scenario in the pool to return. Wraps around if out of range.

    Raises:
        ValueError: If task is not a known difficulty level.
    """
    pools = {"easy": EASY_SCENARIOS, "medium": MEDIUM_SCENARIOS, "hard": HARD_SCENARIOS}
    if task not in pools:
        raise ValueError(f"Unknown task '{task}'. Must be one of: easy, medium, hard")
    pool = pools[task]
    return pool[index % len(pool)]
