# Architecture

## System Overview

```mermaid
graph TB
    subgraph HF["HuggingFace Space (Docker)"]
        subgraph API["FastAPI Server (server/app.py)"]
            R["POST /reset"]
            S["POST /step"]
            ST["GET /state"]
            H["GET /health"]
            M["GET /metadata"]
            WS["WS /ws"]
        end

        subgraph ENV["IncidentTriageEnv (env.py)"]
            STATE["Episode State\n- scenario\n- step_count\n- done / score\n- history\n- queried_actions"]
            HANDLERS["Action Handlers\n- query_logs\n- query_metrics\n- check_topology\n- trace_request\n- check_alerts\n- diagnose"]
        end

        subgraph DATA["Scenario Data Layer"]
            SC["scenarios.py\n5 scenarios"]
            RI["real_incidents.py\nPost-mortem mappings"]
            LT["log_templates.py\nLogHub patterns"]
            GR["grader.py\nDeterministic scoring"]
        end

        subgraph MODELS["Pydantic Models (models.py)"]
            IA["IncidentAction"]
            IO["IncidentObservation"]
            IR["IncidentReward"]
        end

        API --> ENV
        ENV --> DATA
        ENV --> MODELS
    end

    subgraph AGENT["inference.py (runs separately)"]
        LLM["OpenAI Client\n-> LLM (Qwen)"]
        LOOP["Episode Loop\nreset -> step -> step -> ... -> done"]
        LOG["Stdout Logger\n[START] [STEP] [END]"]
    end

    AGENT -->|"HTTP / WebSocket"| API
```

## Episode Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Reset: reset(task="easy|medium|hard")
    Reset --> Running: Returns initial observation

    Running --> Running: step(query_logs / query_metrics / check_topology / trace_request / check_alerts)
    Running --> Done: step(diagnose) or max_steps reached

    Done --> Reset: Can reset for new episode
    Done --> [*]: close()

    state Running {
        [*] --> ProcessAction
        ProcessAction --> ComputeReward
        ComputeReward --> UpdateState
        UpdateState --> ReturnObservation
    }
```

## Request Flow

```mermaid
sequenceDiagram
    participant Agent as Agent (inference.py)
    participant Server as FastAPI Server
    participant Env as IncidentTriageEnv
    participant Grader as grader.py

    Agent->>Server: POST /reset {"task": "easy"}
    Server->>Env: reset()
    Env->>Env: Load scenario from scenarios.py
    Env-->>Server: IncidentObservation
    Server-->>Agent: {observation, reward=0, done=false}

    loop Investigation (up to 15 steps)
        Agent->>Server: POST /step {"action": {"action_type": "query_logs", "target_service": "auth-service"}}
        Server->>Env: step(action)
        Env->>Env: Execute handler, check causal chain
        Env-->>Server: IncidentObservation + reward
        Server-->>Agent: {observation, reward=0.05, done=false}
    end

    Agent->>Server: POST /step {"action": {"action_type": "diagnose", ...}}
    Server->>Env: step(action)
    Env->>Grader: grade_diagnosis(service, fault, remediation)
    Grader-->>Env: {score: 0.85, breakdown: {...}}
    Env-->>Server: IncidentObservation + score
    Server-->>Agent: {observation, reward=0.85, done=true}
```

## Scenario Data Model

```mermaid
erDiagram
    SCENARIO {
        string id "easy-oom-001"
        string real_incident_ref "Meta 2021 BGP"
        string incident_summary "ALERT: auth-service is DOWN"
        list services "auth-service, api-gateway, user-db"
    }
    ROOT_CAUSE {
        string service "auth-service"
        string fault_type "oom"
        string remediation "restart"
    }
    TOPOLOGY {
        string service "api-gateway"
        list dependencies "auth-service"
    }
    LOGS {
        string service "auth-service"
        list log_lines "2025-04-01T10:14:55Z [ERROR] OutOfMemoryError"
    }
    METRICS {
        string service "auth-service"
        float cpu_pct "12.0"
        float memory_pct "99.1"
        float error_rate_pct "100.0"
    }

    SCENARIO ||--|| ROOT_CAUSE : has
    SCENARIO ||--|{ TOPOLOGY : defines
    SCENARIO ||--|{ LOGS : contains
    SCENARIO ||--|{ METRICS : contains
```

## Grading Logic

Final score = 75% diagnosis + 25% investigation quality - blind penalty

```mermaid
flowchart TD
    A[Agent submits diagnose action] --> B{Service matches root cause?}
    B -->|Exact match| C[+0.40]
    B -->|In causal chain| D[+0.15]
    B -->|Wrong| E[0.00 - stop]

    C --> F{Fault type correct?}
    D --> F
    F -->|Yes| G[+0.35]
    F -->|No| H[+0.00]

    G --> I{Remediation correct?}
    H --> I
    I -->|Yes| J[+0.25]
    I -->|No| K[+0.00]

    J --> L{Diagnosed in <= 50% steps?}
    C --> L
    L -->|Yes| M[+0.05 efficiency bonus]
    L -->|No| N[No bonus]

    M --> O["Final score = min(1.0, sum)"]
    N --> O
    K --> O
```

## Difficulty Progression

```mermaid
graph TB
    subgraph Easy["Easy: Single-Service Failure"]
        E1["3 services"]
        E2["1-2 deep causal chain"]
        E3["Clear error logs"]
        E4["OOM, disk full"]
        E5["Expected: 0.75+ for competent agent"]
    end

    subgraph Medium["Medium: Cascading Failure"]
        M1["4-6 services"]
        M2["2-4 deep causal chain"]
        M3["Red herrings in logs"]
        M4["Connection leak, config push"]
        M5["Expected: 0.40-0.75"]
    end

    subgraph Hard["Hard: Silent Degradation"]
        H1["6-8 services"]
        H2["4-5 deep causal chain"]
        H3["Zero application errors"]
        H4["Business metric is only signal"]
        H5["Expected: 0.15-0.50"]
    end
```

## File Responsibilities

| File | Role | Key Constraint |
|------|------|---------------|
| `models.py` | Pydantic models extending openenv types | Fully typed, all fields documented |
| `incident_triage_env/env.py` | Core environment with reset/step/state | Clean state management, proper episode boundaries |
| `incident_triage_env/scenarios.py` | 5 scenario definitions with logs, metrics, topology | Grounded in real post-mortems |
| `incident_triage_env/grader.py` | Deterministic scoring | Same inputs always produce same outputs, range [0.0, 1.0] |
| `incident_triage_env/real_incidents.py` | Maps real outages to scenario structures | Source of truth for incident patterns |
| `incident_triage_env/log_templates.py` | Realistic log generators from LogHub | Timestamps, thread IDs, stack traces |
| `server/app.py` | FastAPI server via create_app() | HTTP + WebSocket + MCP |
| `server/incident_triage_environment.py` | OpenEnv Environment adapter | Bridges env.py to openenv interface |
| `inference.py` | Baseline LLM agent | Exact [START]/[STEP]/[END] stdout format |
| `client.py` | EnvClient for WebSocket sessions | Typed step/reset/state |
