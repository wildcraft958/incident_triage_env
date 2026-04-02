"""
Incident Triage Environment -- openenv Environment adapter.

Wraps IncidentTriageEnv in the standard Environment interface so create_app()
can serve it over HTTP and WebSocket.
"""

from typing import Any, Optional
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment, EnvironmentMetadata
from openenv.core.env_server.types import State

try:
    from ..models import IncidentAction, IncidentObservation
except ImportError:
    from models import IncidentAction, IncidentObservation

from incident_triage_env.env import IncidentTriageEnv
from incident_triage_env.models import IncidentAction as _InternalAction


class IncidentTriageEnvironment(Environment):
    """
    Adapter that wraps IncidentTriageEnv for the openenv server.

    WebSocket connections get one instance per session, so state is
    preserved across reset/step calls within the same connection.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        super().__init__()
        self._inner: Optional[IncidentTriageEnv] = None
        self._state = State(episode_id=str(uuid4()), step_count=0)

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task: str = "easy",
        **kwargs: Any,
    ) -> IncidentObservation:
        self._inner = IncidentTriageEnv(task=task)
        inner_obs = self._inner.reset()
        self._state = State(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
        )
        return IncidentObservation(
            incident_id=inner_obs.incident_id,
            summary=inner_obs.summary,
            available_services=inner_obs.available_services,
            available_actions=inner_obs.available_actions,
            response=inner_obs.response,
            step=inner_obs.step,
            score=inner_obs.score,
            done=False,
            reward=0.0,
        )

    def step(
        self,
        action: IncidentAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        if self._inner is None:
            raise RuntimeError("Call reset() before step()")

        inner_action = _InternalAction(
            action_type=action.action_type,
            target_service=action.target_service,
            fault_type=action.fault_type,
            remediation=action.remediation,
        )
        inner_obs, reward, done, _info = self._inner.step(inner_action)
        self._state.step_count += 1
        return IncidentObservation(
            incident_id=inner_obs.incident_id,
            summary=inner_obs.summary,
            available_services=inner_obs.available_services,
            available_actions=inner_obs.available_actions,
            response=inner_obs.response,
            step=inner_obs.step,
            score=inner_obs.score,
            done=done,
            reward=reward,
        )

    @property
    def state(self) -> State:
        return self._state

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name="incident-triage-env",
            description=(
                "SRE incident triage RL environment. Agents investigate production "
                "incidents by querying logs, metrics, topology, traces, and alerts "
                "across microservices, then submit a root-cause diagnosis."
            ),
            version="1.0.0",
        )
