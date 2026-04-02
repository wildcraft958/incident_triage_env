"""Temporal simulation engine for dynamic metric degradation.

Computes time-varying metrics, logs, and alerts based on episode step.
Metrics degrade along a sigmoid curve as the incident cascades through
the service graph. Services further from the root cause degrade later.
"""

import math


HEALTHY_BASELINES: dict[str, float] = {
    "cpu_pct": 15.0,
    "memory_pct": 35.0,
    "error_rate_pct": 0.0,
    "latency_p99_ms": 25.0,
    "requests_per_sec": 100.0,
    "disk_usage_pct": 50.0,
}


class TemporalSimulator:
    """Computes dynamic scenario state based on episode step number.

    Metrics are mathematically interpolated between baseline (healthy) and
    crisis (full cascade) values using a sigmoid degradation curve. Each
    service's degradation onset is delayed proportionally to its distance
    from the root cause in the causal chain.
    """

    def __init__(self, scenario: dict, max_steps: int):
        self._scenario = scenario
        self._max_steps = max_steps
        self._causal_distances = scenario.get("causal_distances", {})
        self._causal_set = set(scenario.get("causal_chain", []))
        self._baselines = scenario.get("metrics_baseline", {})
        self._crisis = scenario.get("metrics_crisis", scenario.get("metrics", {}))

    def compute_metrics(self, service: str, current_step: int) -> dict:
        """Dynamically compute metrics via sigmoid interpolation.

        Non-causal services return stable baseline values.
        Causal services degrade from baseline toward crisis values.
        """
        baseline = self._baselines.get(service, self._crisis.get(service, {}))
        crisis = self._crisis.get(service, baseline)

        if service not in self._causal_set:
            return dict(baseline)

        effective = self._effective_progress(service, current_step)
        if effective <= 0:
            return dict(baseline)

        t = max(0.0, min(1.0, effective))
        sigmoid = 1.0 / (1.0 + math.exp(-10 * (t - 0.5)))

        result = {}
        all_keys = set(list(baseline.keys()) + list(crisis.keys()))
        for key in all_keys:
            b = baseline.get(key, HEALTHY_BASELINES.get(key, 0))
            c = crisis.get(key, b)
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                result[key] = round(b + (c - b) * sigmoid, 1)
            else:
                result[key] = c if effective > 0.5 else b
        return result

    def compute_logs(self, service: str, current_step: int) -> list[str]:
        """Return logs appropriate for this time step.

        Non-causal services return all logs (healthy noise) immediately.
        Causal services reveal logs progressively based on cascade timing.
        """
        all_logs = self._scenario.get("logs", {}).get(service, [])
        n = len(all_logs)
        if n == 0:
            return []

        if service not in self._causal_set:
            return list(all_logs)

        effective = self._effective_progress(service, current_step)
        distance = self._causal_distances.get(service, 999)

        if effective <= 0 and distance > 0:
            return all_logs[:min(2, n)]

        visible = max(1, int(n * min(1.0, effective * 1.5)))
        return all_logs[:min(visible, n)]

    def compute_alerts(self, current_step: int) -> list[dict]:
        """Return alerts that have fired by this step.

        Noise/resolved alerts are always visible. Real alerts fire progressively.
        """
        all_alerts = self._scenario.get("alerts", [])
        if not all_alerts:
            return []

        progress = min(1.0, current_step / (self._max_steps * 0.75)) if self._max_steps > 0 else 1.0
        visible = []
        for i, alert in enumerate(all_alerts):
            if alert.get("status") == "resolved" or alert.get("severity") in ("warning", "P3"):
                visible.append(alert)
            else:
                fire_threshold = (i + 1) / (len(all_alerts) + 1)
                if progress >= fire_threshold:
                    visible.append(alert)
        return visible

    def compute_traces(self, current_step: int) -> dict:
        """Return trace data. Available from step 0."""
        return dict(self._scenario.get("traces", {}))

    def _effective_progress(self, service: str, current_step: int) -> float:
        """Compute effective degradation progress for a service.

        Combines global time progress with per-service onset delay.
        """
        if self._max_steps <= 0:
            return 1.0

        progress = min(1.0, current_step / (self._max_steps * 0.75))
        distance = self._causal_distances.get(service, 999)
        onset_delay = distance * 0.20

        if onset_delay >= 1.0:
            return 0.0
        return max(0.0, (progress - onset_delay) / (1.0 - onset_delay))
