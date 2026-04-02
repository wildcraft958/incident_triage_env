"""Tests for the procedural scenario generator."""

import networkx as nx
import pytest

from incident_triage_env.generator import ProceduralScenarioGenerator


REQUIRED_KEYS = [
    "id", "incident_summary", "services", "topology",
    "root_cause", "causal_chain", "logs", "metrics",
    "metrics_baseline", "metrics_crisis", "causal_distances",
    "alerts", "traces",
]

STANDARD_METRIC_KEYS = {"cpu_pct", "memory_pct", "error_rate_pct", "latency_p99_ms", "requests_per_sec"}


class TestGeneratorStructure:
    """Generated scenarios must have all required fields and valid relationships."""

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_has_required_keys(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for key in REQUIRED_KEYS:
            assert key in s, f"Missing key: {key}"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_root_cause_in_services(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        assert s["root_cause"]["service"] in s["services"]

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_causal_chain_subset_of_services(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for svc in s["causal_chain"]:
            assert svc in s["services"], f"Causal chain service '{svc}' not in services"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_all_services_have_logs(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for svc in s["services"]:
            assert svc in s["logs"], f"No logs for '{svc}'"
            assert len(s["logs"][svc]) > 0, f"Empty logs for '{svc}'"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_all_services_have_metrics_baseline(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for svc in s["services"]:
            assert svc in s["metrics_baseline"], f"No baseline metrics for '{svc}'"
            for key in STANDARD_METRIC_KEYS:
                assert key in s["metrics_baseline"][svc], f"Missing baseline metric '{key}' for '{svc}'"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_all_services_have_metrics_crisis(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for svc in s["services"]:
            assert svc in s["metrics_crisis"], f"No crisis metrics for '{svc}'"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_topology_is_valid_dag(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        G = nx.DiGraph()
        for svc, deps in s["topology"].items():
            for dep in deps:
                G.add_edge(svc, dep)
        assert nx.is_directed_acyclic_graph(G)

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_topology_references_valid_services(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for svc, deps in s["topology"].items():
            assert svc in s["services"], f"Topology key '{svc}' not in services"
            for dep in deps:
                assert dep in s["services"], f"Topology dep '{dep}' not in services"

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_alerts_have_required_fields(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        for alert in s["alerts"]:
            assert "name" in alert
            assert "severity" in alert
            assert "service" in alert
            assert "message" in alert
            assert "fired_at" in alert

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_traces_have_spans(self, difficulty):
        gen = ProceduralScenarioGenerator(seed=42)
        s = gen.generate(difficulty)
        assert len(s["traces"]) > 0
        for tid, trace in s["traces"].items():
            assert "request" in trace
            assert "spans" in trace
            assert len(trace["spans"]) > 0
            for span in trace["spans"]:
                assert "service" in span
                assert "duration_ms" in span
                assert "status" in span


class TestGeneratorDifficulty:
    """Difficulty levels produce appropriately sized scenarios."""

    def test_easy_service_count(self):
        gen = ProceduralScenarioGenerator(seed=42)
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("easy")
            assert 3 <= len(s["services"]) <= 4, f"Easy had {len(s['services'])} services (seed={seed})"

    def test_medium_service_count(self):
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("medium")
            assert 4 <= len(s["services"]) <= 6, f"Medium had {len(s['services'])} services (seed={seed})"

    def test_hard_service_count(self):
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("hard")
            assert 6 <= len(s["services"]) <= 9, f"Hard had {len(s['services'])} services (seed={seed})"

    def test_easy_causal_chain_length(self):
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("easy")
            assert 1 <= len(s["causal_chain"]) <= 2, f"Easy chain: {len(s['causal_chain'])} (seed={seed})"

    def test_medium_causal_chain_length(self):
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("medium")
            assert 2 <= len(s["causal_chain"]) <= 4, f"Medium chain: {len(s['causal_chain'])} (seed={seed})"

    def test_hard_causal_chain_length(self):
        for seed in range(10):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("hard")
            assert 3 <= len(s["causal_chain"]) <= 5, f"Hard chain: {len(s['causal_chain'])} (seed={seed})"

    def test_hard_has_more_services_than_easy(self):
        g = ProceduralScenarioGenerator(seed=42)
        easy = g.generate("easy")
        g2 = ProceduralScenarioGenerator(seed=42)
        hard = g2.generate("hard")
        assert len(hard["services"]) > len(easy["services"])

    def test_hard_has_longer_chain_than_easy(self):
        g = ProceduralScenarioGenerator(seed=42)
        easy = g.generate("easy")
        g2 = ProceduralScenarioGenerator(seed=42)
        hard = g2.generate("hard")
        assert len(hard["causal_chain"]) > len(easy["causal_chain"])

    def test_hard_has_blind_metrics(self):
        g = ProceduralScenarioGenerator(seed=42)
        s = g.generate("hard")
        assert "blind_metrics" in s

    def test_invalid_difficulty_raises(self):
        g = ProceduralScenarioGenerator(seed=42)
        with pytest.raises(ValueError):
            g.generate("impossible")


class TestGeneratorDeterminism:
    """Same seeds produce same scenarios, different seeds produce different ones."""

    def test_same_seed_same_output(self):
        g1 = ProceduralScenarioGenerator(seed=99)
        g2 = ProceduralScenarioGenerator(seed=99)
        s1 = g1.generate("easy")
        s2 = g2.generate("easy")
        assert s1["id"] == s2["id"]
        assert s1["services"] == s2["services"]
        assert s1["root_cause"] == s2["root_cause"]
        assert s1["causal_chain"] == s2["causal_chain"]

    def test_different_seeds_different_output(self):
        g1 = ProceduralScenarioGenerator(seed=1)
        g2 = ProceduralScenarioGenerator(seed=2)
        s1 = g1.generate("easy")
        s2 = g2.generate("easy")
        # At least one of these should differ
        assert s1["id"] != s2["id"] or s1["services"] != s2["services"]


class TestGeneratorScale:
    """Generator must produce thousands of unique scenarios."""

    def test_generate_100_unique_easy(self):
        ids = set()
        for seed in range(100):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("easy")
            ids.add(s["id"])
        assert len(ids) >= 90  # Allow some collisions from randint

    def test_generate_100_unique_medium(self):
        ids = set()
        for seed in range(100):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("medium")
            ids.add(s["id"])
        assert len(ids) >= 90

    def test_generate_100_unique_hard(self):
        ids = set()
        for seed in range(100):
            g = ProceduralScenarioGenerator(seed=seed)
            s = g.generate("hard")
            ids.add(s["id"])
        assert len(ids) >= 90
