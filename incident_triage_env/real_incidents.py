"""
Real-world incident mappings.

Each entry maps a documented production outage to the parameters
we use in our scenario definitions. This bridges the gap between
"inspired by real incidents" and actual implementation.

Sources:
  - Meta 2021 BGP outage (engineering.fb.com)
  - AWS 2021 us-east-1 (aws.amazon.com/message/12721/)
  - CrowdStrike 2024 Channel File 291
  - GitHub Actions DB connection leaks
  - Google Cloud 2019 network outage
  - Real ML pipeline staleness patterns
"""

from typing import Dict, List, Any


REAL_INCIDENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # --- EASY: Single service, clear signals ---
    "common-java-oom": {
        "real_source": "Industry-wide pattern (Spring Boot, Kafka Streams, Elasticsearch)",
        "frequency": "Multiple times per week across industry",
        "description": "Java service exhausts heap memory due to unbounded cache, "
                       "large query results, or memory leak. Logs show OutOfMemoryError. "
                       "Service crashes and fails to restart if memory isn't freed.",
        "fault_type": "oom",
        "remediation": "restart",
        "detection_difficulty": "easy",
        "signals": ["OutOfMemoryError in logs", "memory_pct > 95%", "restarts > 3"],
        "red_herrings": [],
    },

    "common-disk-full": {
        "real_source": "PostgreSQL WAL accumulation, Docker overlay2 growth",
        "frequency": "Weekly across industry",
        "description": "Database or storage service fills disk with WAL logs, temp files, "
                       "or application logs. Writes fail, service enters read-only mode.",
        "fault_type": "disk_full",
        "remediation": "clear_disk",
        "detection_difficulty": "easy",
        "signals": ["No space left on device", "disk_usage_pct = 100%", "write_ops = 0"],
        "red_herrings": [],
    },

    # --- MEDIUM: Cascading failures ---
    "github-connection-leak": {
        "real_source": "GitHub Actions outages 2023-2024",
        "frequency": "Monthly at large companies",
        "description": "Service acquires database connections on certain error paths "
                       "but doesn't release them. Pool gradually fills over hours. "
                       "When max_connections is hit, dependent services start failing.",
        "fault_type": "connection_leak",
        "remediation": "increase_pool",
        "detection_difficulty": "medium",
        "signals": [
            "Connection count approaching max in DB logs",
            "Idle connections from specific client",
            "Timeout errors in dependent services",
        ],
        "red_herrings": [
            "Other services using same DB work fine (different pool)",
            "The leaking service shows no errors in its own logs",
        ],
    },

    "crowdstrike-config-push": {
        "real_source": "CrowdStrike Channel File 291 (July 19, 2024)",
        "frequency": "Rare but catastrophic",
        "description": "Configuration management service pushes bad config to multiple "
                       "downstream services simultaneously. Each downstream crashes with "
                       "its own error (OOM, segfault, assertion), masking that the root "
                       "cause is the config push, not the individual service failures.",
        "fault_type": "config_error",
        "remediation": "rollback",
        "detection_difficulty": "medium",
        "signals": [
            "Multiple services crashing at same timestamp",
            "Config-service logs show recent push",
            "Each crash has different error but same timing",
        ],
        "red_herrings": [
            "Each service's error looks like an independent issue",
            "No errors in the config-service itself",
        ],
    },

    "slack-thundering-herd": {
        "real_source": "Slack outage May 2020",
        "frequency": "During scale events",
        "description": "Traffic spike causes autoscaler to provision new instances. "
                       "All new instances simultaneously request config from config-service, "
                       "overwhelming it. Config-service goes down, preventing new instances "
                       "from starting, creating a death spiral.",
        "fault_type": "cpu_saturated",
        "remediation": "scale_up",
        "detection_difficulty": "medium",
        "signals": [
            "Config-service CPU at 100%",
            "Spike in connection count to config-service",
            "Autoscaler events showing rapid scaling",
        ],
        "red_herrings": [
            "Individual application services look like they're failing to start",
            "Autoscaler appears to be working correctly (it IS scaling up)",
        ],
    },

    # --- HARD: Subtle degradation, no errors ---
    "ml-pipeline-staleness": {
        "real_source": "Composite: Uber Michelangelo, industry ML ops patterns",
        "frequency": "Common in ML-heavy systems",
        "description": "Kafka broker disk fills up -> consumer can't fetch -> feature "
                       "pipeline stops updating -> feature store serves stale features -> "
                       "ML model predictions degrade -> recommendation quality drops. "
                       "NO service returns errors. All latencies normal. Only signal is "
                       "business metric decline (CTR/engagement drop).",
        "fault_type": "disk_full",
        "remediation": "clear_disk",
        "detection_difficulty": "hard",
        "signals": [
            "Feature staleness warnings (WARN, not ERROR) in model-server",
            "Feature-store shows SLA breach for freshness",
            "Kafka-consumer lag growing (consumer is STOPPED)",
            "Kafka-broker disk at 100% (FATAL in broker logs)",
        ],
        "red_herrings": [
            "All HTTP services return 200 OK",
            "All service latencies are normal",
            "redis-cache, user-service, api-gateway all perfectly healthy",
            "recommendation-service shows no errors",
        ],
    },

    "meta-bgp-outage": {
        "real_source": "Meta/Facebook October 4, 2021",
        "frequency": "Rare",
        "description": "Network configuration change during maintenance withdraws BGP "
                       "routes. DNS resolvers lose connectivity to authoritative servers. "
                       "All services fail DNS resolution. Monitoring tools also fail "
                       "(circular dependency). From the outside, everything is down. "
                       "From the inside, monitoring shows stale/missing data.",
        "fault_type": "config_error",
        "remediation": "rollback",
        "detection_difficulty": "hard",
        "signals": [
            "network-controller logs show config change timestamp",
            "dns-resolver errors: upstream unreachable",
            "Some metrics show 'N/A' or last-updated timestamps are old",
            "All services show connection errors but not the root cause",
        ],
        "red_herrings": [
            "Every service looks broken (symptom, not cause)",
            "Monitoring gaps make it hard to see what happened first",
            "DNS failure looks like it could be the root cause",
        ],
    },

    "aws-internal-network": {
        "real_source": "AWS us-east-1 December 7, 2021",
        "frequency": "Rare",
        "description": "Automated network scaling overloads internal network devices. "
                       "Internal service communication degrades. Kinesis (event streaming) "
                       "fails first. CloudWatch (monitoring) depends on Kinesis and also "
                       "fails. With monitoring down, autoscaling can't read metrics and "
                       "makes random decisions. Multiple services appear to fail independently.",
        "fault_type": "cpu_saturated",
        "remediation": "scale_up",
        "detection_difficulty": "hard",
        "signals": [
            "Event streaming service has highest error rate",
            "Monitoring service ingestion stopped",
            "Multiple services appear to fail at similar timestamps",
            "Autoscaler events show erratic behavior",
        ],
        "red_herrings": [
            "Each service failure looks independent",
            "Monitoring data is unreliable (it's part of the failure)",
            "Some services recovered briefly then failed again",
        ],
    },
}


def get_incident_metadata(incident_key: str) -> Dict[str, Any]:
    """Get metadata for a real incident by key."""
    if incident_key not in REAL_INCIDENT_REGISTRY:
        raise ValueError(
            f"Unknown incident '{incident_key}'. "
            f"Available: {list(REAL_INCIDENT_REGISTRY.keys())}"
        )
    return REAL_INCIDENT_REGISTRY[incident_key]


def list_incidents_by_difficulty(difficulty: str) -> List[str]:
    """List incident keys by detection difficulty."""
    return [
        key for key, meta in REAL_INCIDENT_REGISTRY.items()
        if meta["detection_difficulty"] == difficulty
    ]
