# Architecture

## System Overview

```mermaid
graph TB
    subgraph HF["HuggingFace Space - Docker"]
        subgraph API["FastAPI Server - server/app.py"]
            R["POST /reset"]
            S["POST /step"]
            ST["GET /state"]
            H["GET /health"]
            M["GET /metadata"]
            WS["WS /ws"]
        end

        subgraph ENV["IncidentTriageEnv - env.py"]
            STATE["Episode State"]
            HANDLERS["Action Handlers"]
        end

        subgraph DATA["Scenario Data Layer"]
            SC["scenarios.py - 8 scenarios"]
            GR["grader.py - Deterministic scoring"]
        end

        API --> ENV
        ENV --> DATA
    end

    subgraph AGENT["inference.py - runs separately"]
        LLM["OpenAI Client -> LLM"]
        LOG["Stdout: START / STEP / END"]
    end

    AGENT -->|"HTTP or WebSocket"| API
```

## Episode Lifecycle

```mermaid
flowchart TD
    START(("Start")) --> RESET["reset(task)"]
    RESET -->|"Returns observation"| RUNNING["Running"]
    RUNNING -->|"query_logs / query_metrics\ncheck_topology / trace_request\ncheck_alerts"| PROCESS["Process Action"]
    PROCESS --> REWARD["Compute Reward"]
    REWARD --> UPDATE["Update State"]
    UPDATE --> OBS["Return Observation"]
    OBS -->|"done = false"| RUNNING
    RUNNING -->|"diagnose action\nor max_steps reached"| DONE["Done"]
    DONE -->|"Can reset"| RESET
    DONE --> END(("End"))
```

## Request Flow

```mermaid
sequenceDiagram
    participant Agent as Agent - inference.py
    participant Server as FastAPI Server
    participant Env as IncidentTriageEnv
    participant Grader as grader.py

    Agent->>Server: POST /reset task=easy
    Server->>Env: reset()
    Env->>Env: Load scenario from scenarios.py
    Env-->>Server: IncidentObservation
    Server-->>Agent: observation, reward=0, done=false

    loop Investigation - up to 15 steps
        Agent->>Server: POST /step action=query_logs
        Server->>Env: step(action)
        Env->>Env: Execute handler, check causal chain
        Env-->>Server: IncidentObservation + reward
        Server-->>Agent: observation, reward=0.05, done=false
    end

    Agent->>Server: POST /step action=diagnose
    Server->>Env: step(action)
    Env->>Grader: grade_diagnosis + grade_investigation_quality
    Grader-->>Env: score=0.85, breakdown
    Env-->>Server: IncidentObservation + score
    Server-->>Agent: observation, reward=0.85, done=true
```

## Scenario Data Model

```mermaid
flowchart LR
    subgraph SCENARIO["Scenario"]
        ID["id: easy-oom-001"]
        REF["ref: Meta 2021 BGP"]
        SUMMARY["summary: ALERT text"]
        SVCS["services: 3-8"]
    end

    subgraph ROOT["Root Cause"]
        RS["service: auth-service"]
        RF["fault_type: oom"]
        RR["remediation: restart"]
    end

    subgraph EVIDENCE["Evidence"]
        TOPO["topology: dependency graph"]
        LOGS["logs: per-service log lines"]
        METRICS["metrics: CPU, memory, errors"]
        ALERTS["alerts: active + noise"]
        TRACES["traces: request spans"]
        BLIND["blind_metrics: stale data"]
    end

    SCENARIO --> ROOT
    SCENARIO --> EVIDENCE
```

## Grading Logic

Final score = 70% diagnosis + 30% investigation quality + complexity nudge - blind penalty

```mermaid
flowchart TD
    A["Agent submits diagnose action"] --> B{"Service matches\nroot cause?"}
    B -->|"Exact match"| C["+0.40"]
    B -->|"In causal chain"| D["+0.15"]
    B -->|"Wrong"| E["0.00"]

    C --> F{"Fault type correct?"}
    D --> F
    F -->|"Yes"| G["+0.35"]
    F -->|"No"| H["+0.00"]

    G --> I{"Remediation correct?"}
    H --> I
    I -->|"Yes"| J["+0.25"]
    I -->|"No"| K["+0.00"]

    J --> L{"Fast diagnosis?"}
    C --> L
    L -->|"<= 50% steps"| M["+0.05 efficiency bonus"]
    L -->|"> 50% steps"| N["No bonus"]

    M --> P["Apply blind penalty\nand investigation quality"]
    N --> P
    K --> P
    E --> P
    P --> O["Final score 0.0 - 1.0"]
```

## Difficulty Progression

```mermaid
flowchart LR
    subgraph Easy["Easy"]
        E1["3-4 services"]
        E2["1-2 deep chain"]
        E3["Clear error logs"]
        E4["OOM, disk full, cert expiry"]
    end

    subgraph Medium["Medium"]
        M1["4-6 services"]
        M2["2-4 deep chain"]
        M3["Red herrings + noise alerts"]
        M4["Connection leak, config push, thundering herd"]
    end

    subgraph Hard["Hard"]
        H1["6-8 services"]
        H2["4-5 deep chain"]
        H3["Zero errors + blind metrics"]
        H4["Silent degradation, monitoring down"]
    end

    Easy --> Medium --> Hard
```

## File Responsibilities

| File | Role | Key Constraint |
|------|------|---------------|
| `models.py` | Pydantic models extending openenv types | Fully typed, all fields documented |
| `incident_triage_env/env.py` | Core environment with reset/step/state | Clean state management, proper episode boundaries |
| `incident_triage_env/scenarios.py` | 8 scenario definitions with logs, metrics, topology | Grounded in real post-mortems, randomized on reset |
| `incident_triage_env/grader.py` | Diagnosis + investigation quality scoring | Deterministic, range [0.0, 1.0], partial credit |
| `incident_triage_env/real_incidents.py` | Maps real outages to scenario structures | Source of truth for incident patterns |
| `incident_triage_env/log_templates.py` | Realistic log generators from LogHub | Timestamps, thread IDs, stack traces |
| `server/app.py` | FastAPI server via create_app() | HTTP + WebSocket + MCP |
| `server/incident_triage_environment.py` | OpenEnv Environment adapter | Bridges env.py to openenv interface |
| `inference.py` | Baseline LLM agent | Exact [START]/[STEP]/[END] stdout format |
| `client.py` | EnvClient for WebSocket sessions | Typed step/reset/state |
