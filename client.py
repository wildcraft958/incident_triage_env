"""Incident Triage Environment Client."""

from typing import Dict, Optional

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

try:
    from .models import IncidentAction, IncidentObservation
except ImportError:
    from models import IncidentAction, IncidentObservation  # type: ignore[no-redef]


class IncidentTriageEnvClient(EnvClient[IncidentAction, IncidentObservation, State]):
    """
    Client for the Incident Triage RL Environment.

    Maintains a persistent WebSocket connection for multi-step episode interactions.

    Example:
        >>> with IncidentTriageEnvClient(base_url="http://localhost:7860") as client:
        ...     result = client.reset(task="easy")
        ...     result = client.step(IncidentAction(
        ...         action_type="query_logs", target_service="api-gateway"
        ...     ))
        ...     result = client.step(IncidentAction(
        ...         action_type="diagnose",
        ...         target_service="api-gateway",
        ...         fault_type="oom",
        ...         remediation="restart",
        ...     ))

    Example with HuggingFace Space:
        >>> client = IncidentTriageEnvClient.from_env("bakasur958/incident-triage-env")
        >>> try:
        ...     result = client.reset(task="hard")
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: IncidentAction) -> Dict:
        return action.model_dump(exclude_none=True, exclude={"metadata"})

    def _parse_result(self, payload: Dict) -> StepResult[IncidentObservation]:
        obs_data = payload.get("observation", {})
        observation = IncidentObservation(
            incident_id=obs_data.get("incident_id", ""),
            summary=obs_data.get("summary", ""),
            available_services=obs_data.get("available_services", []),
            available_actions=obs_data.get("available_actions", []),
            response=obs_data.get("response", ""),
            step=obs_data.get("step", 0),
            score=obs_data.get("score", 0.0),
            done=payload.get("done", False),
            reward=payload.get("reward"),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step", 0),
        )
