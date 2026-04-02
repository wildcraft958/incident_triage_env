import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from incident_triage_env.env import IncidentTriageEnv
from incident_triage_env.models import IncidentAction

app = FastAPI(title="Incident Triage Environment")

# In-memory session store: session_id -> IncidentTriageEnv
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


@app.get("/tasks")
def tasks() -> list[dict]:
    return _TASK_DESCRIPTIONS


@app.post("/reset")
def reset(req: ResetRequest) -> dict:
    if req.task not in _VALID_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid task: {req.task!r}. Must be one of: easy, medium, hard.")

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
