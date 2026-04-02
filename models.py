"""Data models for the Incident Triage environment."""

from enum import Enum
from typing import Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    query_logs = "query_logs"
    query_metrics = "query_metrics"
    check_topology = "check_topology"
    trace_request = "trace_request"
    check_alerts = "check_alerts"
    diagnose = "diagnose"


class FaultType(str, Enum):
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


class IncidentAction(Action):
    """An investigation or diagnosis action submitted by the agent."""

    action_type: str = Field(..., description="Action to take")
    target_service: Optional[str] = Field(None, description="Service to query or diagnose")
    fault_type: Optional[str] = Field(None, description="Fault type for diagnose action")
    remediation: Optional[str] = Field(None, description="Remediation for diagnose action")


class IncidentObservation(Observation):
    """Observation returned after reset() or step(). done and reward are inherited."""

    incident_id: str = Field(default="", description="Unique scenario identifier")
    summary: str = Field(default="", description="Alert text the on-call SRE received")
    available_services: list[str] = Field(default_factory=list, description="Services you can query")
    available_actions: list[str] = Field(default_factory=list, description="Available action signatures")
    response: str = Field(default="", description="Result of the last action")
    step: int = Field(default=0, description="Current step number")
    score: float = Field(default=0.0, description="Final diagnosis score after diagnose action")


class IncidentReward(BaseModel):
    """The reward signal returned alongside an observation after each step."""

    score: float
    breakdown: dict[str, float]
    message: str = ""
