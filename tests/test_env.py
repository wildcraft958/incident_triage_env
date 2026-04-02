"""Tests for core environment logic."""

import pytest
from incident_triage_env import IncidentTriageEnv, IncidentAction
from incident_triage_env.temporal import TemporalSimulator


class TestReset:
    """reset() must produce clean state."""

    @pytest.mark.parametrize("task", ["easy", "medium", "hard"])
    def test_reset_returns_observation(self, task):
        env = IncidentTriageEnv(task=task)
        obs = env.reset()
        assert obs.incident_id != ""
        assert obs.summary != ""
        assert len(obs.available_services) >= 3
        assert obs.step == 0
        assert obs.done is False
        assert obs.score == 0.0

    def test_reset_clears_state(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        env.step(IncidentAction(action_type="check_topology"))
        assert env.step_count == 1
        obs = env.reset()
        assert env.step_count == 0
        assert env.done is False
        assert obs.step == 0

    def test_invalid_task(self):
        env = IncidentTriageEnv(task="nonexistent")
        with pytest.raises(ValueError):
            env.reset()


class TestStep:
    """step() must handle all action types correctly."""

    def setup_method(self):
        self.env = IncidentTriageEnv(task="easy")
        self.env.reset()

    def test_check_topology(self):
        obs, r, done, info = self.env.step(IncidentAction(action_type="check_topology"))
        assert ">" in obs.response or "dependencies" in obs.response.lower() or "->" in obs.response
        assert r >= 0
        assert done is False

    def test_query_logs_valid(self):
        services = self.env.scenario["services"]
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="query_logs", target_service=services[0])
        )
        assert obs.response != ""
        assert done is False

    def test_query_logs_invalid_service(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="query_logs", target_service="nonexistent-svc")
        )
        assert "error" in obs.response.lower() or "not found" in obs.response.lower()
        assert info.get("error") is not None

    def test_query_metrics_valid(self):
        services = self.env.scenario["services"]
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="query_metrics", target_service=services[0])
        )
        assert obs.response != ""

    def test_diagnose_ends_episode(self):
        obs, r, done, info = self.env.step(IncidentAction(
            action_type="diagnose",
            target_service="auth-service",
            fault_type="oom",
            remediation="restart",
        ))
        assert done is True

    def test_step_after_done(self):
        self.env.step(IncidentAction(
            action_type="diagnose", target_service="x",
            fault_type="oom", remediation="restart",
        ))
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="check_topology")
        )
        assert done is True
        assert info.get("error") == "episode_already_done"

    def test_unknown_action_type(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="fly_to_moon")
        )
        assert info.get("error") is not None
        assert r < 0

    def test_missing_target_service(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="query_logs")
        )
        assert info.get("error") is not None

    def test_max_steps_reached(self):
        env = IncidentTriageEnv(task="easy", max_steps=3)
        env.reset()
        for _ in range(3):
            obs, r, done, info = env.step(IncidentAction(action_type="check_topology"))
            if done:
                break
        assert done is True


class TestState:
    """state() must return complete state dict."""

    def test_state_keys(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        s = env.state()
        assert "task" in s
        assert "scenario_id" in s
        assert "step" in s
        assert "done" in s
        assert "score" in s
        assert "history" in s


class TestRewardSignals:
    """Rewards must vary meaningfully."""

    def test_causal_chain_service_gives_reward(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        root_svc = env.scenario["root_cause"]["service"]
        _, r, _, _ = env.step(
            IncidentAction(action_type="query_logs", target_service=root_svc)
        )
        assert r > 0

    def test_irrelevant_service_no_reward(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        # Find a service NOT in causal chain
        chain = set(env.scenario["causal_chain"])
        irrelevant = [s for s in env.scenario["services"] if s not in chain]
        if irrelevant:
            _, r, _, _ = env.step(
                IncidentAction(action_type="query_logs", target_service=irrelevant[0])
            )
            assert r == 0.0

    def test_perfect_diagnosis_after_investigation(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        # Investigate first (avoids blind diagnosis penalty)
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="query_logs", target_service=gt["service"]))
        env.step(IncidentAction(action_type="query_metrics", target_service=gt["service"]))
        _, r, done, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))
        assert r > 0.85
        assert done is True

    def test_wrong_diagnosis_low_score(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        _, r, done, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service="nonexistent",
            fault_type="wrong",
            remediation="wrong",
        ))
        assert r < 0.05
        assert done is True


class TestBlindPenaltyExploit:
    """Repeated identical actions must not bypass blind diagnosis penalty."""

    def test_repeated_topology_does_not_bypass_penalty(self):
        """Spamming check_topology 3x should still trigger blind penalty."""
        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        # Spam the same action 3 times -- only 1 unique investigation
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="check_topology"))
        _, score_spammed, _, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))

        # Proper investigation: 3 unique actions
        env2 = IncidentTriageEnv(task="easy")
        env2.scenario = env.scenario  # Same scenario for fair comparison
        env2._temporal = TemporalSimulator(env.scenario, env.max_steps)
        env2.step_count = 0
        env2.done = False
        env2.score = 0.0
        env2.history = []
        env2.queried_actions = set()
        env2.step(IncidentAction(action_type="check_topology"))
        env2.step(IncidentAction(action_type="query_logs", target_service=gt["service"]))
        env2.step(IncidentAction(action_type="query_metrics", target_service=gt["service"]))
        _, score_proper, _, _ = env2.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))

        # Proper investigation must score higher than spam exploit
        assert score_proper > score_spammed

    def test_spam_counted_as_single_unique_investigation(self):
        """3 identical check_topology calls = 1 unique investigation for blind penalty."""
        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]

        # Immediate diagnosis (0 investigation)
        env_zero = IncidentTriageEnv(task="easy")
        env_zero.scenario = env.scenario
        env_zero._temporal = TemporalSimulator(env.scenario, env.max_steps)
        env_zero.step_count = 0
        env_zero.done = False
        env_zero.score = 0.0
        env_zero.history = []
        env_zero.queried_actions = set()
        _, score_zero, _, _ = env_zero.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))

        # Spam topology 3x then diagnose (1 unique investigation)
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="check_topology"))
        _, score_spam, _, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))

        # Spam should score higher than zero (1 unique > 0 unique)
        # but the gap should be small since it's only 1 unique investigation
        assert score_spam > score_zero
        # Score difference between 0 and 1 unique investigation should be modest
        assert (score_spam - score_zero) < 0.15


class TestMonitoringBlindness:
    """Hard scenarios have stale/missing metrics (blind_metrics)."""

    def test_blind_metrics_show_warning(self):
        env = IncidentTriageEnv(task="hard")
        env.reset()
        if "blind_metrics" not in env.scenario or not env.scenario["blind_metrics"]:
            pytest.skip("This hard scenario has no blind_metrics")
        blind_svc = list(env.scenario["blind_metrics"].keys())[0]
        obs, _, _, _ = env.step(
            IncidentAction(action_type="query_metrics", target_service=blind_svc)
        )
        assert "stale" in obs.response.lower() or "N/A" in obs.response or "WARNING" in obs.response


class TestTraceRequest:
    """trace_request must filter by service or return all traces."""

    def setup_method(self):
        self.env = IncidentTriageEnv(task="easy")
        self.env.reset()

    def test_trace_request_no_service_returns_all(self):
        obs, r, done, info = self.env.step(IncidentAction(action_type="trace_request"))
        assert obs.response != ""
        assert "not found" not in obs.response.lower()
        assert done is False
        # All services should appear across the spans
        services = self.env.scenario["services"]
        assert any(svc in obs.response for svc in services)

    def test_trace_request_valid_service_filters_spans(self):
        # Use a service that appears in traces (causal chain services)
        causal = self.env.scenario["causal_chain"]
        target = causal[0]
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="trace_request", target_service=target)
        )
        assert obs.response != ""
        assert done is False
        # Every span line must belong to the target service
        for line in obs.response.splitlines():
            if line.startswith("  "):
                assert line.strip().startswith(target), (
                    f"Expected span for '{target}' but got: {line}"
                )

    def test_trace_request_invalid_service_returns_error(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="trace_request", target_service="nonexistent-svc")
        )
        assert r == -0.02
        assert "error" in obs.response.lower() or "not found" in obs.response.lower()
        assert info.get("error") is not None
        assert done is False

    def test_trace_request_causal_service_gives_reward(self):
        causal_chain = self.env.scenario["causal_chain"]
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="trace_request", target_service=causal_chain[0])
        )
        assert r == 0.04

    def test_trace_request_duplicate_penalized(self):
        services = self.env.scenario["services"]
        target = services[0]
        self.env.step(IncidentAction(action_type="trace_request", target_service=target))
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="trace_request", target_service=target)
        )
        assert r == -0.01


class TestTemporalBehavior:
    """Metrics must evolve dynamically over steps."""

    def test_metrics_change_between_steps(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        root = env.scenario["root_cause"]["service"]
        obs1, _, _, _ = env.step(
            IncidentAction(action_type="query_metrics", target_service=root)
        )
        # Advance several steps
        for _ in range(8):
            env.step(IncidentAction(action_type="check_topology"))
        # Query same service again (repeated, but different temporal state)
        obs2, _, _, _ = env.step(
            IncidentAction(action_type="query_metrics", target_service=root)
        )
        # The responses should differ due to temporal degradation
        assert obs1.response != obs2.response

    def test_each_reset_generates_new_scenario(self):
        env = IncidentTriageEnv(task="easy")
        obs1 = env.reset()
        id1 = obs1.incident_id
        obs2 = env.reset()
        id2 = obs2.incident_id
        # Procedural generator should produce different scenarios
        # (extremely unlikely to collide)
        assert id1 != id2


class TestHypothesisEvidence:
    """hypothesis_evidence should provide bonus scoring."""

    def test_diagnose_with_evidence_scores_higher(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        root = gt["service"]

        # Investigate first
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="query_logs", target_service=root))
        env.step(IncidentAction(action_type="query_metrics", target_service=root))

        # Diagnose with evidence
        evidence = f"{root} showed OutOfMemoryError in logs, memory_pct at 99%"
        _, score_with, _, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=root,
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
            hypothesis_evidence=evidence,
        ))

        # Diagnose without evidence (separate env, same scenario)
        env2 = IncidentTriageEnv(task="easy")
        env2.scenario = env.scenario
        env2._temporal = TemporalSimulator(env.scenario, env.max_steps)
        env2.step_count = 0
        env2.done = False
        env2.score = 0.0
        env2.history = []
        env2.queried_actions = set()
        env2.step(IncidentAction(action_type="check_topology"))
        env2.step(IncidentAction(action_type="query_logs", target_service=root))
        env2.step(IncidentAction(action_type="query_metrics", target_service=root))
        _, score_without, _, _ = env2.step(IncidentAction(
            action_type="diagnose",
            target_service=root,
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))

        assert score_with >= score_without


class TestTopologyCriticality:
    """Topology output must show service criticality tiers."""

    def test_topology_shows_tier_labels(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        obs, _, _, _ = env.step(IncidentAction(action_type="check_topology"))
        assert "Tier" in obs.response


class TestCheckRunbook:
    """check_runbook action must return runbook content."""

    def setup_method(self):
        self.env = IncidentTriageEnv(task="easy")
        self.env.reset()

    def test_check_runbook_valid_service(self):
        svc = self.env.scenario["services"][0]
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="check_runbook", target_service=svc)
        )
        assert obs.response != ""
        assert len(obs.response) > 20
        assert done is False
        assert r >= 0

    def test_check_runbook_invalid_service(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="check_runbook", target_service="nonexistent-svc")
        )
        assert "error" in obs.response.lower() or "not found" in obs.response.lower()
        assert r == -0.02
        assert info.get("error") is not None

    def test_check_runbook_duplicate_penalized(self):
        svc = self.env.scenario["services"][0]
        self.env.step(IncidentAction(action_type="check_runbook", target_service=svc))
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="check_runbook", target_service=svc)
        )
        assert r == -0.01

    def test_check_runbook_causal_service_gives_reward(self):
        root = self.env.scenario["root_cause"]["service"]
        _, r, _, _ = self.env.step(
            IncidentAction(action_type="check_runbook", target_service=root)
        )
        assert r == 0.02

    def test_check_runbook_missing_target_service(self):
        obs, r, done, info = self.env.step(
            IncidentAction(action_type="check_runbook")
        )
        assert info.get("error") is not None
        assert r == -0.02
