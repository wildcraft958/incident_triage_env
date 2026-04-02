"""Tests for grading logic -- must be deterministic and in [0.0, 1.0]."""

import pytest
from incident_triage_env.grader import grade_diagnosis, grade_investigation_quality


class TestGraderDeterminism:
    """Same inputs must always produce same outputs."""

    def test_perfect_score(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        chain = ["auth-service"]
        r = grade_diagnosis("auth-service", "oom", "restart", gt, chain)
        assert r["score"] == 1.0

    def test_perfect_score_deterministic(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        chain = ["auth-service"]
        scores = [grade_diagnosis("auth-service", "oom", "restart", gt, chain)["score"] for _ in range(100)]
        assert all(s == 1.0 for s in scores)

    def test_zero_score(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        r = grade_diagnosis("wrong-svc", "wrong-fault", "wrong-fix", gt, ["auth-service"])
        assert r["score"] == 0.0

    def test_zero_score_deterministic(self):
        gt = {"service": "x", "fault_type": "y", "remediation": "z"}
        scores = [grade_diagnosis("a", "b", "c", gt, [])["score"] for _ in range(100)]
        assert all(s == 0.0 for s in scores)


class TestGraderPartialCredit:
    """Partial credit must work correctly."""

    def test_causal_chain_partial(self):
        gt = {"service": "kafka-broker", "fault_type": "disk_full", "remediation": "clear_disk"}
        chain = ["kafka-broker", "kafka-consumer", "feature-store"]
        r = grade_diagnosis("kafka-consumer", "disk_full", "clear_disk", gt, chain)
        assert 0.0 < r["score"] < 1.0
        assert r["breakdown"].get("service_partial") == 0.15

    def test_correct_service_wrong_fault(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        r = grade_diagnosis("auth-service", "cpu_saturated", "restart", gt, ["auth-service"])
        assert r["score"] == 0.65  # 0.40 + 0.00 + 0.25

    def test_correct_service_wrong_remediation(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        r = grade_diagnosis("auth-service", "oom", "scale_up", gt, ["auth-service"])
        assert r["score"] == 0.75  # 0.40 + 0.35 + 0.00


class TestGraderRange:
    """All possible scores must be in [0.0, 1.0]."""

    def test_score_range(self):
        gt = {"service": "svc", "fault_type": "oom", "remediation": "restart"}
        fault_types = ["oom", "cpu_saturated", "disk_full", "config_error", "wrong"]
        remediations = ["restart", "scale_up", "clear_disk", "wrong"]
        services = ["svc", "other", "chain-svc"]
        chain = ["svc", "chain-svc"]

        for svc in services:
            for ft in fault_types:
                for rem in remediations:
                    r = grade_diagnosis(svc, ft, rem, gt, chain)
                    assert 0.0 <= r["score"] <= 1.0, f"Score {r['score']} out of range for {svc}/{ft}/{rem}"

    def test_none_inputs(self):
        gt = {"service": "svc", "fault_type": "oom", "remediation": "restart"}
        r = grade_diagnosis(None, None, None, gt, [])
        assert 0.0 <= r["score"] <= 1.0


class TestInvestigationQuality:
    """Investigation quality scoring must reward good methodology."""

    TOPOLOGY = {
        "api-gateway": ["auth-service"],
        "auth-service": ["user-db"],
        "user-db": [],
    }
    CHAIN = ["auth-service"]
    SERVICES = ["api-gateway", "auth-service", "user-db"]

    def test_empty_history_returns_zero(self):
        r = grade_investigation_quality([], self.CHAIN, self.SERVICES, self.TOPOLOGY)
        assert r["score"] == 0.0

    def test_topology_first_gets_bonus(self):
        history = [
            {"action_type": "check_topology", "target_service": None},
            {"action_type": "query_logs", "target_service": "auth-service"},
        ]
        r = grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)
        assert r["breakdown"].get("topology_timing", 0) > 0

    def test_causal_chain_coverage_rewarded(self):
        history = [
            {"action_type": "query_logs", "target_service": "auth-service"},
        ]
        r = grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)
        assert r["breakdown"].get("causal_chain_coverage", 0) > 0

    def test_cross_referencing_rewarded(self):
        history = [
            {"action_type": "query_logs", "target_service": "auth-service"},
            {"action_type": "query_metrics", "target_service": "auth-service"},
        ]
        r = grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)
        assert r["breakdown"].get("cross_reference_depth", 0) > 0

    def test_focused_investigation_rewarded(self):
        # Only investigate relevant services
        history = [
            {"action_type": "query_logs", "target_service": "auth-service"},
        ]
        r1 = grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)

        # Waste time on irrelevant services
        history_noisy = [
            {"action_type": "query_logs", "target_service": "auth-service"},
            {"action_type": "query_logs", "target_service": "user-db"},
            {"action_type": "query_logs", "target_service": "api-gateway"},
        ]
        r2 = grade_investigation_quality(history_noisy, self.CHAIN, self.SERVICES, self.TOPOLOGY)

        assert r1["breakdown"].get("investigation_focus", 0) >= r2["breakdown"].get("investigation_focus", 0)

    def test_score_capped_at_030(self):
        # Even with perfect investigation, score caps at 0.30
        history = [
            {"action_type": "check_topology", "target_service": None},
            {"action_type": "query_logs", "target_service": "auth-service"},
            {"action_type": "query_metrics", "target_service": "auth-service"},
        ]
        r = grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)
        assert r["score"] <= 0.30

    def test_deterministic(self):
        history = [
            {"action_type": "check_topology", "target_service": None},
            {"action_type": "query_logs", "target_service": "auth-service"},
        ]
        scores = [
            grade_investigation_quality(history, self.CHAIN, self.SERVICES, self.TOPOLOGY)["score"]
            for _ in range(100)
        ]
        assert len(set(scores)) == 1


class TestEvidenceScoring:
    """hypothesis_evidence must produce bonus points."""

    def test_no_evidence_no_bonus(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        chain = ["auth-service"]
        r = grade_diagnosis("auth-service", "oom", "restart", gt, chain)
        assert r["breakdown"]["evidence_bonus"] == 0.0

    def test_evidence_mentioning_root_service_gives_bonus(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        chain = ["auth-service"]
        r = grade_diagnosis(
            "auth-service", "oom", "restart", gt, chain,
            hypothesis_evidence="auth-service showed OutOfMemoryError",
        )
        assert r["breakdown"]["evidence_bonus"] > 0

    def test_evidence_with_signal_keywords_gives_more_bonus(self):
        gt = {"service": "auth-service", "fault_type": "oom", "remediation": "restart"}
        chain = ["auth-service"]
        r = grade_diagnosis(
            "auth-service", "oom", "restart", gt, chain,
            hypothesis_evidence="auth-service heap at 99%, OutOfMemoryError in logs, GC overhead",
        )
        assert r["breakdown"]["evidence_bonus"] >= 0.05

    def test_evidence_bonus_capped(self):
        gt = {"service": "svc", "fault_type": "oom", "remediation": "restart"}
        chain = ["svc"]
        r = grade_diagnosis(
            "svc", "oom", "restart", gt, chain,
            hypothesis_evidence="svc heap outofmemoryerror gc overhead memory_pct all keywords",
        )
        assert r["breakdown"]["evidence_bonus"] <= 0.10


class TestBlindDiagnosisPenalty:
    """Agents that diagnose without investigating should be penalized."""

    def test_immediate_diagnosis_penalized(self):
        """Diagnosing on step 0 with no investigation gets penalty."""
        from incident_triage_env.env import IncidentTriageEnv
        from models import IncidentAction

        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        _, score, done, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))
        # Perfect diagnosis with 0 investigation should score < 1.0
        assert score < 1.0
        assert done is True

    def test_investigated_diagnosis_not_penalized(self):
        """Proper investigation before diagnosis gets full score."""
        from incident_triage_env.env import IncidentTriageEnv
        from models import IncidentAction

        env = IncidentTriageEnv(task="easy")
        env.reset()
        gt = env.scenario["root_cause"]
        env.step(IncidentAction(action_type="check_topology"))
        env.step(IncidentAction(action_type="query_logs", target_service=gt["service"]))
        env.step(IncidentAction(action_type="query_metrics", target_service=gt["service"]))
        _, score, done, _ = env.step(IncidentAction(
            action_type="diagnose",
            target_service=gt["service"],
            fault_type=gt["fault_type"],
            remediation=gt["remediation"],
        ))
        # Good investigation + perfect diagnosis should score high
        assert score > 0.85
        assert done is True


class TestCriticalityScoring:
    """Criticality tiering must affect diagnosis scoring."""

    def test_tier1_wrong_diagnosis_penalized_more(self):
        gt = {"service": "postgres-db", "fault_type": "disk_full", "remediation": "clear_disk"}
        chain = ["postgres-db"]
        crit_tier1 = {"postgres-db": 1}
        crit_tier3 = {"postgres-db": 3}
        r1 = grade_diagnosis("wrong-svc", "oom", "restart", gt, chain, service_criticality=crit_tier1)
        r3 = grade_diagnosis("wrong-svc", "oom", "restart", gt, chain, service_criticality=crit_tier3)
        # Tier 1 wrong diagnosis should score lower (bigger penalty)
        assert r1["score"] <= r3["score"]

    def test_tier1_correct_diagnosis_gets_bonus(self):
        gt = {"service": "postgres-db", "fault_type": "disk_full", "remediation": "clear_disk"}
        chain = ["postgres-db"]
        crit = {"postgres-db": 1}
        no_crit = None
        r_crit = grade_diagnosis("postgres-db", "disk_full", "clear_disk", gt, chain, service_criticality=crit)
        r_none = grade_diagnosis("postgres-db", "disk_full", "clear_disk", gt, chain, service_criticality=no_crit)
        assert r_crit["score"] >= r_none["score"]
