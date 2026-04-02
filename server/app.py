"""
FastAPI server for the Incident Triage RL Environment.

Uses openenv's create_app() which provides:
  - HTTP: /reset, /step, /state, /health, /metadata, /schema, /mcp
  - WebSocket: /ws (persistent multi-step sessions)
  - MCP WebSocket: /mcp (tool-calling protocol)
  - Docs: /docs, /redoc, /openapi.json
"""

try:
    from openenv.core.env_server.http_server import create_app
except ImportError as e:
    raise ImportError(
        "openenv is required for the server. Install with 'uv sync'"
    ) from e

try:
    from ..models import IncidentAction, IncidentObservation
    from .incident_triage_environment import IncidentTriageEnvironment
except ImportError:
    from models import IncidentAction, IncidentObservation
    from server.incident_triage_environment import IncidentTriageEnvironment

app = create_app(
    IncidentTriageEnvironment,
    IncidentAction,
    IncidentObservation,
    env_name="incident_triage_env",
    max_concurrent_envs=10,
)


@app.get("/")
def root() -> dict:
    return {"status": "ok", "name": "incident-triage-env", "version": "1.0"}


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run("server.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
