"""
FastAPI server for the Incident Triage RL Environment.

Exposes reset/step/state HTTP endpoints for agent interaction,
plus /metadata, /schema, and /mcp endpoints required by openenv validate.
"""

import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from incident_triage_env.env import IncidentTriageEnv
from incident_triage_env.models import IncidentAction, IncidentObservation

app = FastAPI(title="Incident Triage Environment", version="1.0.0")

_sessions: dict = {}
_VALID_TASKS = {"easy", "medium", "hard"}

_TASK_DESCRIPTIONS = [
    {"name": "easy", "description": "Single-service incident with clear error signals. One causal chain, logs and metrics point directly to the fault."},
    {"name": "medium", "description": "Multi-service incident with partial signals. Requires correlating logs, metrics, and topology to find the root cause."},
    {"name": "hard", "description": "Complex cascading failure across 5+ services with no direct error signals. Temporal reasoning and trace analysis required."},
]


class ResetRequest(BaseModel):
    task: str
    scenario_index: int = 0


class StepRequest(BaseModel):
    session_id: str
    action: IncidentAction


class StateRequest(BaseModel):
    session_id: str


@app.get("/")
def root() -> dict:
    return {"status": "ok", "name": "incident-triage-env", "version": "1.0"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "sessions": len(_sessions)}


@app.get("/metadata")
def metadata() -> dict:
    return {
        "name": "incident-triage-env",
        "description": (
            "SRE incident triage RL environment. Agents investigate production incidents "
            "by querying logs, metrics, topology, traces, and alerts across microservices, "
            "then submit a root-cause diagnosis. Based on real outages from Meta, AWS, "
            "CrowdStrike, and GitHub post-mortems."
        ),
        "version": "1.0.0",
        "tasks": [t["name"] for t in _TASK_DESCRIPTIONS],
    }


@app.get("/schema")
def schema() -> dict:
    return {
        "action": IncidentAction.model_json_schema(),
        "observation": IncidentObservation.model_json_schema(),
        "state": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "scenario_id": {"type": "string"},
                "step": {"type": "integer"},
                "done": {"type": "boolean"},
                "score": {"type": "number"},
                "history": {"type": "array"},
            },
        },
    }


@app.post("/mcp")
def mcp(request: dict = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "result": {
            "tools": [
                {"name": "reset", "description": "Reset the environment and start a new episode"},
                {"name": "step", "description": "Execute an action and advance the episode"},
                {"name": "state", "description": "Get current episode state"},
            ]
        },
    }


@app.get("/tasks")
def tasks() -> list[dict]:
    return _TASK_DESCRIPTIONS


@app.post("/reset")
def reset(req: ResetRequest) -> dict:
    if req.task not in _VALID_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid task: {req.task!r}. Must be one of: easy, medium, hard.")

    if len(_sessions) > 200:
        oldest = next(iter(_sessions))
        del _sessions[oldest]

    env = IncidentTriageEnv(task=req.task)
    obs = env.reset()
    session_id = str(uuid.uuid4())
    _sessions[session_id] = env

    return {"session_id": session_id, "observation": obs.model_dump()}


@app.post("/step")
def step(req: StepRequest) -> dict:
    env = _sessions.get(req.session_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {req.session_id!r}")

    obs, reward, done, info = env.step(req.action)
    return {"observation": obs.model_dump(), "reward": reward, "done": done, "info": info}


@app.post("/state")
def state(req: StateRequest) -> dict:
    env = _sessions.get(req.session_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {req.session_id!r}")

    return env.state()


def main(host: str = "0.0.0.0", port: int = 7860) -> None:
    import uvicorn
    uvicorn.run("server.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
