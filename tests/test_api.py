"""Tests for the FastAPI server."""

import pytest
from fastapi.testclient import TestClient
from app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoints:

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200


class TestResetEndpoint:

    @pytest.mark.parametrize("task", ["easy", "medium", "hard"])
    def test_reset_returns_session(self, client, task):
        r = client.post("/reset", json={"task": task})
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data
        assert "observation" in data
        assert data["observation"]["done"] is False


class TestStepEndpoint:

    def test_step_flow(self, client):
        # Reset
        r = client.post("/reset", json={"task": "easy"})
        sid = r.json()["session_id"]

        # Step
        r = client.post("/step", json={
            "session_id": sid,
            "action": {"action_type": "check_topology"},
        })
        assert r.status_code == 200
        data = r.json()
        assert "observation" in data
        assert "reward" in data
        assert "done" in data

    def test_step_invalid_session(self, client):
        r = client.post("/step", json={
            "session_id": "nonexistent",
            "action": {"action_type": "check_topology"},
        })
        assert r.status_code == 404


class TestStateEndpoint:

    def test_state(self, client):
        r = client.post("/reset", json={"task": "easy"})
        sid = r.json()["session_id"]
        r = client.post("/state", json={"session_id": sid})
        assert r.status_code == 200
        data = r.json()
        assert "task" in data
        assert "step" in data

    def test_tasks_endpoint(self, client):
        r = client.get("/tasks")
        if r.status_code == 200:
            data = r.json()
            assert "easy" in str(data)
