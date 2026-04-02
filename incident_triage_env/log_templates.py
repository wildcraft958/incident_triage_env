"""
Realistic log line templates based on LogHub (Zhu et al., ICSE 2023)
and real production system patterns.

These templates make our synthetic logs feel like actual production logs
instead of toy examples. Each template is parameterized with timestamps,
service names, and contextual values.
"""

from typing import Dict, List


# ----------------------------------------------------------------------
# Log templates by category (adapted from LogHub HDFS, OpenStack, Spark)
# ----------------------------------------------------------------------

JAVA_OOM_LOGS = [
    "{ts} [WARN] gc.GarbageCollector: GC pause (G1 Evacuation Pause) {pause_ms}ms -- heap {used_gb}GB/{max_gb}GB",
    "{ts} [WARN] mem.HeapMonitor: Heap memory usage at {pct}% ({used_gb}GB/{max_gb}GB)",
    "{ts} [ERROR] java.lang.OutOfMemoryError: Java heap space",
    "{ts} [ERROR] java.lang.OutOfMemoryError: GC overhead limit exceeded",
    "{ts} [ERROR] mem.HeapMonitor: Failed to allocate {alloc_mb}MB for {component}",
    "{ts} [FATAL] runtime.ServiceRunner: Service crash -- attempting restart (attempt {n}/{max})",
    "{ts} [ERROR] runtime.ServiceRunner: Restart failed -- insufficient memory",
]

POSTGRES_LOGS = [
    "{ts} [INFO] postgres: connection received: host={host} port={port}",
    "{ts} [INFO] postgres: connection authorized: user={user} database={db}",
    "{ts} [WARN] postgres: Connection count: {count}/{max} -- approaching max_connections",
    "{ts} [ERROR] postgres: FATAL: too many connections for role '{user}'",
    "{ts} [ERROR] postgres: FATAL: remaining connection slots are reserved for superuser",
    "{ts} [WARN] postgres: Client {client} holding {count} connections ({idle} IDLE)",
    "{ts} [INFO] postgres: Query executed in {ms}ms: {query_prefix}",
    "{ts} [ERROR] postgres: PANIC: could not write to file '{file}': No space left on device",
    "{ts} [ERROR] postgres: Disk usage: {pct}% ({used}/{total})",
    "{ts} [FATAL] postgres: Database entering read-only mode",
]

KAFKA_LOGS = [
    "{ts} [INFO] kafka.server.KafkaServer: Kafka version: {version}",
    "{ts} [INFO] kafka.log.LogManager: Recovering {count} unflushed segments",
    "{ts} [WARN] kafka.server.BrokerServer: Disk usage: {pct}% ({path}: {used}/{total})",
    "{ts} [ERROR] kafka.log.LogManager: Failed to flush log segment: No space left on device",
    "{ts} [FATAL] kafka.server.BrokerServer: Disk full: unable to write to log segment",
    "{ts} [ERROR] kafka.server.BrokerServer: Broker entering degraded mode",
    "{ts} [ERROR] kafka.server.BrokerServer: Rejecting produce requests: disk full",
    "{ts} [ERROR] kafka.server.BrokerServer: Consumer fetch requests failing: log segment corrupt",
    "{ts} [ERROR] kafka.server.BrokerServer: Broker offline -- all partitions unavailable",
]

KAFKA_CONSUMER_LOGS = [
    "{ts} [INFO] consumer.ConsumerCoordinator: Consumed {count} messages from topic '{topic}'",
    "{ts} [WARN] consumer.ConsumerCoordinator: Consumer lag increasing: {lag} messages behind",
    "{ts} [ERROR] consumer.ConsumerCoordinator: Failed to fetch from broker: BrokerNotAvailable",
    "{ts} [ERROR] consumer.ConsumerCoordinator: Retrying connection to broker (attempt {n}/{max})",
    "{ts} [ERROR] consumer.ConsumerCoordinator: All retry attempts failed -- broker unreachable",
    "{ts} [ERROR] consumer.ConsumerCoordinator: Consumer stopped -- no messages being processed",
    "{ts} [ERROR] consumer.ConsumerCoordinator: Consumer lag: {lag} messages",
]

HTTP_GATEWAY_LOGS = [
    "{ts} [INFO] gateway.Router: Routing {method} {path} -> {upstream}",
    "{ts} [INFO] gateway.Router: {upstream} response: {status} ({latency_ms}ms)",
    "{ts} [ERROR] gateway.Router: Upstream {upstream} returned {status}",
    "{ts} [ERROR] gateway.Router: {upstream} request timed out after {timeout}ms",
    "{ts} [WARN] gateway.CircuitBreaker: {upstream} error rate above threshold: {rate}%",
    "{ts} [WARN] gateway.CircuitBreaker: {upstream} circuit breaker OPEN",
    "{ts} [INFO] gateway.HealthCheck: Health check to {upstream}: {state}",
]

REDIS_LOGS = [
    "{ts} [INFO] redis.Server: Memory usage: {used}/{max} ({pct}%)",
    "{ts} [INFO] redis.Server: Operations/sec: {ops}",
    "{ts} [INFO] redis.Keyspace: GET {key} -- {result}",
    "{ts} [INFO] redis.Keyspace: SET {key} -- OK (TTL: {ttl}s)",
    "{ts} [INFO] redis.Stats: Hit rate: {rate}%",
    "{ts} [WARN] redis.Stats: Low cache hit rate detected: {rate}% (normal: {normal}%)",
    "{ts} [INFO] redis.Connection: Connection from {client} {action}",
]

ML_SERVICE_LOGS = [
    "{ts} [INFO] ml.ModelServer: Inference request for {entity_type} {entity_id}",
    "{ts} [INFO] ml.ModelServer: Fetching features from feature-store",
    "{ts} [INFO] ml.ModelServer: Feature vector received (dim={dim})",
    "{ts} [WARN] ml.ModelServer: Feature staleness: last_updated={age} (threshold: {threshold})",
    "{ts} [WARN] ml.ModelServer: Using stale features for prediction -- results may be degraded",
    "{ts} [INFO] ml.ModelServer: Prediction completed in {ms}ms",
    "{ts} [WARN] ml.ModelServer: Stale feature rate: {pct}% of requests using outdated features",
]

FEATURE_STORE_LOGS = [
    "{ts} [INFO] features.Store: Feature update batch received (batch_id={batch_id})",
    "{ts} [INFO] features.Store: Updated {count} feature vectors",
    "{ts} [INFO] features.Store: Next expected batch: ~{interval} min",
    "{ts} [WARN] features.Store: Expected feature batch not received",
    "{ts} [WARN] features.Store: Feature batch overdue by {delay} min",
    "{ts} [WARN] features.Store: No feature updates in {duration} min -- serving stale features",
    "{ts} [ERROR] features.Store: Feature freshness SLA breached: last update {age} ago",
    "{ts} [INFO] features.Store: Serving feature request for {entity} (stale: {staleness})",
]

GENERIC_SERVICE_LOGS = [
    "{ts} [INFO] service.{name}: Processing request req_id={req_id}",
    "{ts} [INFO] service.{name}: Request completed in {ms}ms",
    "{ts} [INFO] service.{name}: Service healthy -- all nominal",
    "{ts} [INFO] service.{name}: Health check: OK",
    "{ts} [WARN] service.{name}: Slow response from {dep}: {ms}ms",
    "{ts} [ERROR] service.{name}: {dep} timed out after {timeout}ms",
    "{ts} [ERROR] service.{name}: Failed to process request: {error}",
    "{ts} [WARN] service.{name}: {pct}% of requests failing due to {reason}",
]

CONNECTION_LEAK_LOGS = [
    "{ts} [INFO] pool.ConnectionPool: Connection acquired -- pool: {active}/{max}",
    "{ts} [INFO] pool.ConnectionPool: Connection released -- pool: {active}/{max}",
    "{ts} [WARN] pool.ConnectionPool: Waiting for connection from pool...",
    "{ts} [ERROR] pool.ConnectionPool: Connection pool wait timeout: {ms}ms",
    "{ts} [WARN] pool.ConnectionPool: Acquired connection after {ms}ms wait",
    "{ts} [ERROR] pool.ConnectionPool: Connection pool exhausted: {active}/{max} connections in use",
    "{ts} [ERROR] pool.ConnectionPool: Cannot acquire connection -- pool full",
    "{ts} [WARN] pool.ConnectionPool: {count} connections idle for >{threshold}s (possible connection leak)",
]


def get_templates(category: str) -> List[str]:
    """Get log templates by category name."""
    categories = {
        "java_oom": JAVA_OOM_LOGS,
        "postgres": POSTGRES_LOGS,
        "kafka": KAFKA_LOGS,
        "kafka_consumer": KAFKA_CONSUMER_LOGS,
        "http_gateway": HTTP_GATEWAY_LOGS,
        "redis": REDIS_LOGS,
        "ml_service": ML_SERVICE_LOGS,
        "feature_store": FEATURE_STORE_LOGS,
        "generic": GENERIC_SERVICE_LOGS,
        "connection_leak": CONNECTION_LEAK_LOGS,
    }
    return categories.get(category, GENERIC_SERVICE_LOGS)
