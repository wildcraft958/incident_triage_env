from enum import Enum

from pydantic import BaseModel, field_validator


class ActionType(str, Enum):
    """All valid action types an agent can take during an episode."""

    query_logs = "query_logs"
    query_metrics = "query_metrics"
    check_topology = "check_topology"
    trace_request = "trace_request"
    check_alerts = "check_alerts"
    diagnose = "diagnose"


class FaultType(str, Enum):
    """All valid fault types that can be the root cause of an incident."""

    oom = "oom"
    cpu_saturated = "cpu_saturated"
    connection_leak = "connection_leak"
    disk_full = "disk_full"
    config_error = "config_error"
    network_partition = "network_partition"
    dependency_timeout = "dependency_timeout"
    certificate_expired = "certificate_expired"
    memory_leak = "memory_leak"
    thread_deadlock = "thread_deadlock"
    dns_failure = "dns_failure"


class Remediation(str, Enum):
    """All valid remediations an agent can prescribe for a diagnosed fault."""

    restart = "restart"
    scale_up = "scale_up"
    fix_config = "fix_config"
    clear_disk = "clear_disk"
    rollback = "rollback"
    failover = "failover"
    increase_pool = "increase_pool"
    renew_certificate = "renew_certificate"
    kill_threads = "kill_threads"
    flush_dns = "flush_dns"
    update_routes = "update_routes"
    resize_volume = "resize_volume"


class IncidentAction(BaseModel):
    """A single action submitted by the agent to the environment."""

    action_type: str
    target_service: str | None = None
    fault_type: str | None = None
    remediation: str | None = None

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        """Reject any action_type not in the ActionType enum."""
        valid = {a.value for a in ActionType}
        if v not in valid:
            raise ValueError(f"action_type must be one of {sorted(valid)}, got {v!r}")
        return v


class IncidentObservation(BaseModel):
    """The observation returned to the agent after reset() or step()."""

    incident_id: str
    summary: str
    available_services: list[str]
    response: str = ""
    step: int = 0
    done: bool = False
    score: float = 0.0


class IncidentReward(BaseModel):
    """The reward signal returned alongside an observation after each step."""

    score: float
    breakdown: dict[str, float]
    message: str = ""
