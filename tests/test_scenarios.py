"""Tests for scenario data integrity (procedurally generated)."""

import pytest
from incident_triage_env.scenarios import get_scenario, EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS


class TestScenarioStructure:
    """Every scenario must have required fields."""

    REQUIRED_KEYS = [
        "id", "incident_summary", "services", "topology",
        "root_cause", "causal_chain", "logs", "metrics",
    ]

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_all_scenarios_have_required_keys(self, pool, name):
        for i, scenario in enumerate(pool):
            for key in self.REQUIRED_KEYS:
                assert key in scenario, f"{name}[{i}] missing key: {key}"

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_root_cause_in_services(self, pool, name):
        for i, s in enumerate(pool):
            assert s["root_cause"]["service"] in s["services"], \
                f"{name}[{i}]: root cause '{s['root_cause']['service']}' not in services"

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_causal_chain_subset_of_services(self, pool, name):
        for i, s in enumerate(pool):
            for svc in s["causal_chain"]:
                assert svc in s["services"], \
                    f"{name}[{i}]: causal chain service '{svc}' not in services"

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_all_services_have_logs(self, pool, name):
        for i, s in enumerate(pool):
            for svc in s["services"]:
                assert svc in s["logs"], f"{name}[{i}]: no logs for '{svc}'"
                assert len(s["logs"][svc]) > 0, f"{name}[{i}]: empty logs for '{svc}'"

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_all_services_have_metrics(self, pool, name):
        for i, s in enumerate(pool):
            for svc in s["services"]:
                assert svc in s["metrics"], f"{name}[{i}]: no metrics for '{svc}'"

    @pytest.mark.parametrize("pool,name", [
        (EASY_SCENARIOS, "easy"),
        (MEDIUM_SCENARIOS, "medium"),
        (HARD_SCENARIOS, "hard"),
    ])
    def test_topology_references_valid_services(self, pool, name):
        for i, s in enumerate(pool):
            for svc, deps in s["topology"].items():
                assert svc in s["services"], f"{name}[{i}]: topology key '{svc}' not in services"
                for dep in deps:
                    assert dep in s["services"], f"{name}[{i}]: topology dep '{dep}' not in services"


class TestScenarioPools:
    """Must have minimum scenario counts."""

    def test_minimum_easy_scenarios(self):
        assert len(EASY_SCENARIOS) >= 3

    def test_minimum_medium_scenarios(self):
        assert len(MEDIUM_SCENARIOS) >= 3

    def test_minimum_hard_scenarios(self):
        assert len(HARD_SCENARIOS) >= 2

    def test_get_scenario_valid(self):
        for task in ["easy", "medium", "hard"]:
            s = get_scenario(task, 0)
            assert s is not None
            assert "id" in s

    def test_get_scenario_invalid(self):
        with pytest.raises(ValueError):
            get_scenario("impossible", 0)

    def test_get_scenario_deterministic_with_index(self):
        s1 = get_scenario("easy", 5)
        s2 = get_scenario("easy", 5)
        assert s1["id"] == s2["id"]
        assert s1["services"] == s2["services"]


class TestDifficultyProgression:
    """Hard scenarios must be harder than easy ones."""

    def test_hard_has_more_services(self):
        easy = get_scenario("easy", 0)
        hard = get_scenario("hard", 0)
        assert len(hard["services"]) > len(easy["services"])

    def test_hard_has_longer_causal_chain(self):
        easy = get_scenario("easy", 0)
        hard = get_scenario("hard", 0)
        assert len(hard["causal_chain"]) > len(easy["causal_chain"])
