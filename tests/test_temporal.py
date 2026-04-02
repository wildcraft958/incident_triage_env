"""Tests for the temporal simulation engine."""

import pytest

from incident_triage_env.generator import ProceduralScenarioGenerator
from incident_triage_env.temporal import TemporalSimulator


def _make_scenario(seed=42, difficulty="easy"):
    gen = ProceduralScenarioGenerator(seed=seed)
    return gen.generate(difficulty)


class TestMetricDegradation:
    """Metrics must mathematically degrade over time for causal chain services."""

    def test_root_cause_degrades_over_steps(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]

        m_early = sim.compute_metrics(root, 1)
        m_late = sim.compute_metrics(root, 12)

        # Error rate should climb
        assert m_late["error_rate_pct"] > m_early["error_rate_pct"]

    def test_error_rate_climbs_from_baseline_to_crisis(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]

        m0 = sim.compute_metrics(root, 0)
        m_mid = sim.compute_metrics(root, 7)
        m_full = sim.compute_metrics(root, 12)

        # Should monotonically increase (or stay same if already at crisis)
        assert m0["error_rate_pct"] <= m_mid["error_rate_pct"] <= m_full["error_rate_pct"]

    def test_distant_service_degrades_later(self):
        scenario = _make_scenario(seed=42, difficulty="medium")
        sim = TemporalSimulator(scenario, max_steps=15)
        chain = scenario["causal_chain"]
        if len(chain) < 2:
            pytest.skip("Need at least 2 services in chain")

        root = chain[0]
        distant = chain[-1]

        # At step 2, root should be more degraded than distant
        m_root = sim.compute_metrics(root, 2)
        m_distant = sim.compute_metrics(distant, 2)

        root_crisis = scenario["metrics_crisis"].get(root, {}).get("error_rate_pct", 0)
        dist_crisis = scenario["metrics_crisis"].get(distant, {}).get("error_rate_pct", 0)

        if root_crisis > 0 and dist_crisis > 0:
            root_progress = m_root["error_rate_pct"] / max(root_crisis, 1)
            dist_progress = m_distant["error_rate_pct"] / max(dist_crisis, 1)
            assert root_progress >= dist_progress

    def test_healthy_service_stays_stable(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        causal_set = set(scenario["causal_chain"])
        bystanders = [s for s in scenario["services"] if s not in causal_set]
        if not bystanders:
            pytest.skip("No bystander services")

        svc = bystanders[0]
        m_early = sim.compute_metrics(svc, 1)
        m_late = sim.compute_metrics(svc, 12)

        # Metrics should not change for non-causal services
        assert m_early["cpu_pct"] == m_late["cpu_pct"]
        assert m_early["memory_pct"] == m_late["memory_pct"]

    def test_sigmoid_shape(self):
        """Degradation should follow sigmoid: slow start, rapid middle, plateau."""
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]

        values = [sim.compute_metrics(root, step)["error_rate_pct"] for step in range(15)]
        # Check that the middle portion shows the most change
        early_delta = abs(values[3] - values[0])
        mid_delta = abs(values[8] - values[5])
        late_delta = abs(values[14] - values[11])
        # Mid change should be >= early change (sigmoid property)
        assert mid_delta >= early_delta or values[14] == values[0]  # Allow flat if crisis == baseline

    def test_full_degradation_at_late_step(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]

        m_final = sim.compute_metrics(root, 15)
        crisis = scenario["metrics_crisis"].get(root, {})

        # At max steps, should be near crisis values
        for key in ["error_rate_pct", "cpu_pct"]:
            if key in crisis and isinstance(crisis[key], (int, float)):
                assert abs(m_final[key] - crisis[key]) < crisis[key] * 0.1 + 1.0

    def test_metrics_keys_always_present(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        for svc in scenario["services"]:
            m = sim.compute_metrics(svc, 5)
            assert "cpu_pct" in m
            assert "memory_pct" in m
            assert "error_rate_pct" in m


class TestLogEvolution:
    """Logs must reveal progressively for causal services."""

    def test_root_cause_logs_visible_early(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]
        logs = sim.compute_logs(root, 1)
        assert len(logs) >= 1

    def test_more_logs_at_later_steps(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]
        logs_early = sim.compute_logs(root, 1)
        logs_late = sim.compute_logs(root, 12)
        assert len(logs_late) >= len(logs_early)

    def test_healthy_service_all_logs_immediately(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        causal_set = set(scenario["causal_chain"])
        bystanders = [s for s in scenario["services"] if s not in causal_set]
        if not bystanders:
            pytest.skip("No bystander services")

        svc = bystanders[0]
        logs_step0 = sim.compute_logs(svc, 0)
        all_logs = scenario["logs"].get(svc, [])
        assert len(logs_step0) == len(all_logs)

    def test_minimum_visibility_guarantee(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        for svc in scenario["services"]:
            logs = sim.compute_logs(svc, 0)
            all_logs = scenario["logs"].get(svc, [])
            if all_logs:
                assert len(logs) >= 1


class TestAlertProgression:
    """Alerts must fire progressively."""

    def test_noise_alerts_always_visible(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        alerts_step0 = sim.compute_alerts(0)
        noise = [a for a in alerts_step0 if a.get("status") == "resolved" or a.get("severity") in ("warning", "P3")]
        all_noise = [a for a in scenario["alerts"] if a.get("status") == "resolved" or a.get("severity") in ("warning", "P3")]
        assert len(noise) == len(all_noise)

    def test_more_alerts_at_later_steps(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        alerts_early = sim.compute_alerts(1)
        alerts_late = sim.compute_alerts(12)
        assert len(alerts_late) >= len(alerts_early)


class TestDeterminism:
    """Same step number must produce identical results."""

    def test_same_step_same_metrics(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]
        m1 = sim.compute_metrics(root, 5)
        m2 = sim.compute_metrics(root, 5)
        assert m1 == m2

    def test_same_step_same_logs(self):
        scenario = _make_scenario()
        sim = TemporalSimulator(scenario, max_steps=15)
        root = scenario["root_cause"]["service"]
        l1 = sim.compute_logs(root, 5)
        l2 = sim.compute_logs(root, 5)
        assert l1 == l2
