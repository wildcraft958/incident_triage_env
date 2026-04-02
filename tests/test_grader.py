"""Tests for grading logic -- must be deterministic and in [0.0, 1.0]."""

import pytest
from incident_triage_env.grader import grade_diagnosis


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
