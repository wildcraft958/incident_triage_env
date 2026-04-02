"""Data models for the Incident Triage environment."""

from typing import Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


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
