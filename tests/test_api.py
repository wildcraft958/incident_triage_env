"""Tests for the FastAPI server (openenv create_app pattern)."""

import pytest
from fastapi.testclient import TestClient
from server.app import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoints:

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"


class TestMetadata:

    def test_metadata(self, client):
        r = client.get("/metadata")
        assert r.status_code == 200
        data = r.json()
        assert "name" in data
        assert "description" in data

    def test_schema(self, client):
        r = client.get("/schema")
        assert r.status_code == 200
        data = r.json()
        assert "action" in data
        assert "observation" in data


class TestResetEndpoint:

    @pytest.mark.parametrize("task", ["easy", "medium", "hard"])
    def test_reset_returns_observation(self, client, task):
        r = client.post("/reset", json={"task": task})
        assert r.status_code == 200
        data = r.json()
        assert "observation" in data
        assert data.get("done") is False
        obs = data["observation"]
        assert "incident_id" in obs or "summary" in obs

    def test_reset_default(self, client):
        r = client.post("/reset", json={})
        assert r.status_code == 200


class TestStepEndpoint:

    def test_step_endpoint_exists(self, client):
        """HTTP step is stateless (one-shot). Multi-step uses WebSocket /ws."""
        r = client.post("/step", json={
            "action": {"action_type": "check_topology"},
        })
        # Stateless step on unreset env returns 500; endpoint still exists.
        assert r.status_code in (200, 422, 500)


class TestMCPEndpoint:

    def test_mcp(self, client):
        r = client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
        })
        assert r.status_code == 200
