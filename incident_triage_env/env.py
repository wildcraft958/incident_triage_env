"""Main RL environment for SRE incident triage."""

from .grader import grade_diagnosis
from .models import ActionType, IncidentAction, IncidentObservation
from .scenarios import get_scenario

_VALID_ACTION_TYPES = {a.value for a in ActionType}


class IncidentTriageEnv:
    """RL environment that simulates SRE incident triage across microservices.

    An agent investigates a production incident by querying logs, metrics,
    topology, traces, and alerts, then submits a root-cause diagnosis for grading.
    """

    def __init__(self, task: str = "easy", max_steps: int = 15) -> None:
        self.task = task
        self.max_steps = max_steps

        self.scenario: dict = {}
        self.step_count: int = 0
        self.done: bool = False
        self.score: float = 0.0
        self.history: list[dict] = []
        self.queried_actions: set[tuple] = set()

    def reset(self) -> IncidentObservation:
        """Load a fresh scenario and reset all episode state.

        Raises:
            ValueError: If self.task is not a recognised difficulty level.
        """
        self.scenario = get_scenario(self.task)
        self.step_count = 0
        self.done = False
        self.score = 0.0
        self.history = []
        self.queried_actions = set()

        return IncidentObservation(
            incident_id=self.scenario["id"],
            summary=self.scenario["incident_summary"],
            available_services=self.scenario["services"],
            step=0,
            done=False,
            score=0.0,
        )

    def step(
        self, action: IncidentAction
    ) -> tuple[IncidentObservation, float, bool, dict]:
        """Execute one action and return (observation, reward, done, info).

        If the episode is already done, returns an error observation immediately.
        """
        if self.done:
            obs = self._make_obs("", error="episode_already_done")
            return obs, 0.0, True, {"error": "episode_already_done"}

        atype = action.action_type
        info: dict = {}

        if atype not in _VALID_ACTION_TYPES:
            self.step_count += 1
            obs = self._make_obs(f"Unknown action type: {atype!r}")
            info = {"error": f"unknown_action_type: {atype}"}
            return obs, -0.02, False, info

        if atype in ("query_logs", "query_metrics") and action.target_service is None:
            self.step_count += 1
            obs = self._make_obs("target_service is required for this action.")
            info = {"error": "target_service_required"}
            return obs, -0.02, False, info

        if atype == "check_topology":
            response, reward = self._do_check_topology()
            done = False
        elif atype == "query_logs":
            response, reward = self._do_query_logs(action.target_service)
            done = False
            if reward == -0.02:
                info = {"error": f"service_not_found: {action.target_service}"}
        elif atype == "query_metrics":
            response, reward = self._do_query_metrics(action.target_service)
            done = False
            if reward == -0.02:
                info = {"error": f"service_not_found: {action.target_service}"}
        elif atype == "trace_request":
            response, reward = self._do_trace_request(action.target_service)
            done = False
        elif atype == "check_alerts":
            response, reward = self._do_check_alerts()
            done = False
        elif atype == "diagnose":
            response, reward, done = self._do_diagnose(
                action.target_service, action.fault_type, action.remediation
            )

        self.step_count += 1
        self.history.append({"step": self.step_count, "action": atype, "reward": reward})

        if self.step_count >= self.max_steps and not done:
            done = True

        self.done = done
        obs = self._make_obs(response)
        return obs, reward, done, info

    def state(self) -> dict:
        """Return the full current episode state."""
        return {
            "task": self.task,
            "scenario_id": self.scenario.get("id", ""),
            "step": self.step_count,
            "done": self.done,
            "score": self.score,
            "history": self.history,
        }

    def close(self) -> None:
        """No-op cleanup hook for API compatibility."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_obs(self, response: str, error: str = "") -> IncidentObservation:
        summary = error if error else self.scenario.get("incident_summary", "")
        return IncidentObservation(
            incident_id=self.scenario.get("id", ""),
            summary=summary,
            available_services=self.scenario.get("services", []),
            response=response,
            step=self.step_count,
            done=self.done,
            score=self.score,
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _do_check_topology(self) -> tuple[str, float]:
        key = ("check_topology", None)
        if key in self.queried_actions:
            return "Topology already retrieved.", -0.01

        self.queried_actions.add(key)
        topology: dict = self.scenario.get("topology", {})
        lines = []
        for svc, deps in topology.items():
            if deps:
                lines.append(f"{svc} -> {', '.join(deps)}")
            else:
                lines.append(f"{svc} -> (no dependencies)")
        response = "\n".join(lines) if lines else "No topology data available."
        return response, 0.02

    def _do_query_logs(self, service: str) -> tuple[str, float]:
        if service not in self.scenario.get("services", []):
            return f"Error: service '{service}' not found.", -0.02

        key = ("query_logs", service)
        if key in self.queried_actions:
            logs = self.scenario.get("logs", {}).get(service, [])
            return "\n".join(logs) if logs else f"No logs for {service}.", -0.01

        self.queried_actions.add(key)
        logs = self.scenario.get("logs", {}).get(service, [])
        response = "\n".join(logs) if logs else f"No logs available for {service}."

        causal_chain = self.scenario.get("causal_chain", [])
        reward = 0.05 if service in causal_chain else 0.0
        return response, reward

    def _do_query_metrics(self, service: str) -> tuple[str, float]:
        if service not in self.scenario.get("services", []):
            return f"Error: service '{service}' not found.", -0.02

        key = ("query_metrics", service)
        if key in self.queried_actions:
            metrics = self.scenario.get("metrics", {}).get(service, {})
            response = _format_metrics(service, metrics)
            return response, -0.01

        self.queried_actions.add(key)
        metrics = self.scenario.get("metrics", {}).get(service, {})
        response = _format_metrics(service, metrics)

        causal_chain = self.scenario.get("causal_chain", [])
        reward = 0.03 if service in causal_chain else 0.0
        return response, reward

    def _do_trace_request(self, service: str | None) -> tuple[str, float]:
        key = ("trace_request", service)
        if key in self.queried_actions:
            return "Trace already retrieved for this target.", -0.01

        self.queried_actions.add(key)
        traces: dict = self.scenario.get("traces", {})

        if traces:
            lines = []
            for tid, trace in traces.items():
                lines.append(f"Trace {tid}: {trace.get('request', '')} -> {trace.get('outcome', '')}")
                for span in trace.get("spans", []):
                    lines.append(
                        f"  {span['service']}: {span['duration_ms']}ms [{span['status']}]"
                    )
            response = "\n".join(lines)
        else:
            response = f"No traces available{' for ' + service if service else ''}."

        causal_chain = self.scenario.get("causal_chain", [])
        reward = 0.04 if (service and service in causal_chain) else 0.0
        return response, reward

    def _do_check_alerts(self) -> tuple[str, float]:
        key = ("check_alerts", None)
        if key in self.queried_actions:
            return "Alerts already retrieved.", -0.01

        self.queried_actions.add(key)
        alerts: list[dict] = self.scenario.get("alerts", [])
        if not alerts:
            return "No active alerts.", 0.03

        lines = []
        for alert in alerts:
            lines.append(
                f"[{alert.get('severity', '?')}] {alert.get('name', '?')}: "
                f"{alert.get('message', '')} (fired: {alert.get('fired_at', '?')})"
            )
        return "\n".join(lines), 0.03

    def _do_diagnose(
        self,
        service: str | None,
        fault_type: str | None,
        remediation: str | None,
    ) -> tuple[str, float, bool]:
        result = grade_diagnosis(
            service,
            fault_type,
            remediation,
            self.scenario["root_cause"],
            self.scenario["causal_chain"],
        )
        score: float = result["score"]

        if score > 0 and self.step_count <= self.max_steps / 2:
            score = min(1.0, score + 0.05)

        self.score = score
        self.done = True
        return result["message"], score, True


def _format_metrics(service: str, metrics: dict) -> str:
    if not metrics:
        return f"No metrics available for {service}."
    lines = [f"Metrics for {service}:"]
    for key, val in metrics.items():
        lines.append(f"  {key}: {val}")
    return "\n".join(lines)
