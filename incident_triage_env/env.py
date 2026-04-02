"""Main RL environment for SRE incident triage."""

from .grader import grade_diagnosis, grade_investigation_quality
from .models import ActionType, IncidentAction, IncidentObservation
from .scenarios import get_scenario

_VALID_ACTION_TYPES = {a.value for a in ActionType}

_AVAILABLE_ACTIONS = [
    "query_logs(service)",
    "query_metrics(service)",
    "check_topology()",
    "trace_request(service)",
    "check_alerts()",
    "diagnose(service, fault_type, remediation)",
]

_ACTION_GUIDE = """\
Investigate the incident by using any of these actions:
  query_logs(service)                          — fetch recent logs for a service
  query_metrics(service)                       — fetch CPU, memory, error rate metrics
  check_topology()                             — show service dependency graph
  trace_request(service)                       — trace a request through the service mesh
  check_alerts()                               — list active alerts
  diagnose(service, fault_type, remediation)   — submit your root cause analysis

Valid fault_type values: oom, cpu_saturated, connection_leak, disk_full, config_error, \
network_partition, dependency_timeout, certificate_expired, memory_leak, thread_deadlock, dns_failure

Valid remediation values: restart, scale_up, fix_config, clear_disk, rollback, failover, \
increase_pool, renew_certificate, kill_threads, flush_dns, update_routes, resize_volume

Services in this incident: {services}"""


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

        services = self.scenario["services"]
        return IncidentObservation(
            incident_id=self.scenario["id"],
            summary=self.scenario["incident_summary"],
            available_services=services,
            available_actions=_AVAILABLE_ACTIONS,
            response=_ACTION_GUIDE.format(services=", ".join(services)),
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
            if reward == -0.02:
                info = {"error": f"service_not_found: {action.target_service}"}
        elif atype == "check_alerts":
            response, reward = self._do_check_alerts()
            done = False
        elif atype == "diagnose":
            response, reward, done = self._do_diagnose(
                action.target_service, action.fault_type, action.remediation
            )

        self.step_count += 1
        self.history.append({
            "step": self.step_count,
            "action": atype,
            "target_service": action.target_service,
            "reward": reward,
        })

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
            response = _format_metrics(service, metrics, self.scenario.get("blind_metrics", {}))
            return response, -0.01

        self.queried_actions.add(key)
        metrics = self.scenario.get("metrics", {}).get(service, {})
        response = _format_metrics(service, metrics, self.scenario.get("blind_metrics", {}))

        causal_chain = self.scenario.get("causal_chain", [])
        reward = 0.03 if service in causal_chain else 0.0
        return response, reward

    def _do_trace_request(self, service: str | None) -> tuple[str, float]:
        if service is not None and service not in self.scenario.get("services", []):
            return f"Error: service '{service}' not found.", -0.02

        key = ("trace_request", service)
        if key in self.queried_actions:
            return "Trace already retrieved for this target.", -0.01

        self.queried_actions.add(key)
        traces: dict = self.scenario.get("traces", {})

        if traces:
            lines = []
            for tid, trace in traces.items():
                spans = trace.get("spans", [])
                if service is not None:
                    spans = [s for s in spans if s["service"] == service]
                if service is not None and not spans:
                    continue
                lines.append(f"Trace {tid}: {trace.get('request', '')} -> {trace.get('outcome', '')}")
                for span in spans:
                    lines.append(
                        f"  {span['service']}: {span['duration_ms']}ms [{span['status']}]"
                    )
            response = "\n".join(lines) if lines else f"No traces found for {service}."
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
        diag_result = grade_diagnosis(
            service,
            fault_type,
            remediation,
            self.scenario["root_cause"],
            self.scenario["causal_chain"],
        )
        diag_score: float = diag_result["score"]

        # Efficiency bonus for fast correct diagnosis
        if diag_score > 0 and self.step_count <= self.max_steps / 2:
            diag_score = min(1.0, diag_score + 0.05)

        # Blind diagnosis penalty: penalize agents that skip investigation
        investigation_steps = sum(
            1 for h in self.history
            if h["action"] in ("query_logs", "query_metrics", "trace_request",
                               "check_alerts", "check_topology")
        )
        blind_penalty = 0.0
        if investigation_steps == 0:
            blind_penalty = 0.30
        elif investigation_steps == 1:
            blind_penalty = 0.15
        elif investigation_steps == 2:
            blind_penalty = 0.05

        diag_score = max(0.0, diag_score - blind_penalty)

        # Investigation quality scoring (25% weight)
        invest_history = [
            {"action_type": h["action"], "target_service": h.get("target_service")}
            for h in self.history
        ]
        invest_result = grade_investigation_quality(
            invest_history,
            self.scenario["causal_chain"],
            self.scenario["services"],
            self.scenario["topology"],
        )

        # Combined: 75% diagnosis + 25% investigation quality (normalized)
        # Max invest score is 0.30, so normalize: 0.30 -> 1.0
        invest_normalized = invest_result["score"] / 0.30 if invest_result["score"] > 0 else 0.0
        combined = (diag_score * 0.75) + (invest_normalized * 0.25)
        combined = min(1.0, round(combined, 3))

        self.score = combined
        self.done = True

        message = diag_result["message"]
        if blind_penalty > 0:
            message += f" Investigation penalty: -{blind_penalty:.2f} ({investigation_steps} investigation steps)."
        if invest_result["score"] > 0:
            message += f" Investigation quality: +{invest_result['score']:.3f}."

        return message, combined, True


def _format_metrics(service: str, metrics: dict, blind_metrics: dict | None = None) -> str:
    if not metrics:
        return f"No metrics available for {service}."

    blind = (blind_metrics or {}).get(service, {})
    if blind:
        last_scrape = blind.get("_last_scrape", "unknown")
        lines = [
            f"Metrics for {service}:",
            f"  WARNING: some metrics may be stale (last scrape: {last_scrape})",
        ]
        for key, val in metrics.items():
            if key in blind:
                lines.append(f"  {key}: {blind[key]}")
            else:
                lines.append(f"  {key}: {val}")
    else:
        lines = [f"Metrics for {service}:"]
        for key, val in metrics.items():
            lines.append(f"  {key}: {val}")

    return "\n".join(lines)
