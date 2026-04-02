"""Tests for core environment logic."""

import pytest
from incident_triage_env import IncidentTriageEnv, IncidentAction


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

    def test_perfect_diagnosis_easy(self):
        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        _, r, done, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))
        assert r == 1.0
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
        assert r == 0.0
        assert done is True
