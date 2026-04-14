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

        subgraph GEN["Procedural Engine"]
            PROC["generator.py<br/>networkx DAGs<br/>12 fault patterns"]
            TEMP["temporal.py<br/>Sigmoid degradation<br/>Causal hop delays"]
        end

        subgraph SCORE["Scoring"]
            GR["grader.py<br/>Diagnosis + Evidence scoring"]
        end

        API --> ENV
        ENV --> GEN
        ENV --> SCORE
    end

    subgraph AGENT["inference.py - runs separately"]
        LLM["OpenAI Client -> LLM"]
        LOG["Stdout: START / STEP / END"]
    end

    AGENT -->|"HTTP or WebSocket"| API
```

## Research Grounding

The architecture is informed by three lines of research in microservice observability and root-cause analysis:

- **Graph-structured multi-modal RCA.** Frameworks like MicroHECL (Li et al., FSE 2022) and CHASE (Wang et al., 2023) localize faults by combining service call graphs with metrics, logs, and traces. Our environment mirrors this structure: agents receive DAG topology, temporal metrics, log evidence, alerts, and traces as separate observation modalities.
- **Production microservice trace analysis.** Studies of Alibaba-scale call graphs (Luo et al., ACM SoCC 2021) show heavy-tailed, tree-like DAGs with hotspot services. Our networkx generator produces topologies with these properties while remaining fully procedural and deterministic.
- **Temporal anomaly detection.** GCN+LSTM frameworks for trace anomaly detection operate on evolving metric streams over service graphs. Our TemporalSimulator produces sigmoid degradation with causal hop delays, creating the same "moving target" that temporal anomaly detectors are designed for.

## Episode Lifecycle

```mermaid
flowchart TD
    START(("Start")) --> RESET["reset(task)"]
    RESET -->|"generates fresh scenario"| GEN["ProceduralScenarioGenerator"]
    GEN --> TEMPORAL["TemporalSimulator initialized"]
    TEMPORAL --> RUNNING["Running"]
    RUNNING -->|"investigation action"| PROCESS["Process Action"]
    PROCESS --> DEGRADE["Temporal: compute metrics"]
    DEGRADE --> REWARD["Compute Reward"]
    REWARD --> UPDATE["Update State"]
    UPDATE --> OBS["Return Observation"]
    OBS -->|"done = false"| RUNNING
    RUNNING -->|"diagnose or max_steps"| DONE["Done"]
    DONE --> END(("End"))
```

## Procedural Generation

```mermaid
flowchart LR
    subgraph INPUT["Configuration"]
        DIFF["difficulty: easy/medium/hard"] --- SEED["optional seed for reproducibility"]
    end

    subgraph GENERATOR["ProceduralScenarioGenerator"]
        FP["Pick fault pattern (12 available)"] --> TOPO["Build networkx DAG (3-9 services)"]
        TOPO --> RC["Select root cause + causal chain"]
        RC --> SYNTH["Synthesize: logs, metrics, alerts, traces"]
    end

    subgraph OUTPUT["Scenario Dict"]
        SVC["services + topology"] --- BASELINE["metrics_baseline (healthy state)"]
        BASELINE --- CRISIS["metrics_crisis (full cascade)"]
        CRISIS --- LOGS["logs per service"]
        LOGS --- CHAIN["causal_chain + causal_distances"]
    end

    INPUT --> GENERATOR
    GENERATOR --> OUTPUT
```

## Temporal Degradation Model

```mermaid
flowchart TD
    A["Agent calls query_metrics(service)"] --> B["TemporalSimulator.compute_metrics()"]
    B --> C{"In causal chain?"}
    C -->|"No"| D["Return baseline (stable, healthy)"]
    C -->|"Yes"| E["Compute effective progress"]
    E --> F["progress = step / max_steps x 0.75"]
    F --> G["onset_delay = distance x 0.20"]
    G --> H["effective = (progress - delay) / (1 - delay)"]
    H --> I["sigmoid = 1 / (1 + exp(-10 x (t - 0.5)))"]
    I --> J["metric = baseline + (crisis - baseline) x sigmoid"]
    J --> K["Return metrics"]
    D --> K
```

### Sigmoid Curve

At each step, the effective degradation follows a sigmoid:

- Steps 0-3: slow onset (metrics near baseline)
- Steps 4-8: rapid escalation (metrics climbing fast)
- Steps 9-12: plateau near crisis values

Services further from root cause start degrading later (20% delay per hop).

## Request Flow

```mermaid
sequenceDiagram
    participant Agent as Agent - inference.py
    participant Server as FastAPI Server
    participant Env as IncidentTriageEnv
    participant Gen as ProceduralScenarioGenerator
    participant Temp as TemporalSimulator
    participant Grader as grader.py

    Agent->>Server: POST /reset task=hard
    Server->>Env: reset()
    Env->>Gen: generate("hard")
    Gen-->>Env: scenario (networkx DAG + data)
    Env->>Temp: TemporalSimulator(scenario, 15)
    Env-->>Server: IncidentObservation
    Server-->>Agent: observation, reward=0, done=false

    loop Investigation - up to 15 steps
        Agent->>Server: POST /step action=query_metrics
        Server->>Env: step(action)
        Env->>Temp: compute_metrics(service, step)
        Note over Temp: Sigmoid interpolation<br/>between baseline and crisis
        Env-->>Server: IncidentObservation + reward
        Server-->>Agent: observation, reward=0.03, done=false
    end

    Agent->>Server: POST /step action=diagnose + evidence
    Server->>Env: step(action)
    Env->>Grader: grade_diagnosis + hypothesis_evidence
    Grader-->>Env: score=0.85, evidence_bonus=0.07
    Env-->>Server: IncidentObservation + score
    Server-->>Agent: observation, reward=0.85, done=true
```

## Grading Logic

Final score = 70% diagnosis + 30% investigation quality + complexity nudge - blind penalty

Anti-reward-hacking: evidence grounding (must have queried cited service), keyword stuffing detection (3+ fault type keywords halves bonus), input validation (invalid fault_type/remediation rejected with -0.02).

```mermaid
flowchart TD
    A["Agent submits diagnose action"] --> B{"Service matches root cause?"}
    B -->|"Exact match +0.40"| F{"Fault type correct?"}
    B -->|"In causal chain +0.15"| F
    B -->|"Wrong +0.00"| P
    F -->|"Yes +0.35"| I{"Remediation correct?"}
    F -->|"No +0.00"| I
    I -->|"Yes +0.25"| EV{"Evidence cites root service?"}
    I -->|"No +0.00"| P
    EV -->|"Yes up to +0.10"| P
    EV -->|"No +0.00"| P
    P["Apply blind penalty and investigation quality"] --> O["Final score 0.01 - 0.99"]
```

## Difficulty Progression

```mermaid
flowchart LR
    EA["Easy<br/>3-4 services, 1-2 deep chain<br/>Clear error logs<br/>OOM / disk full / cert expiry"]
    MD["Medium<br/>4-6 services, 2-4 deep chain<br/>Red herrings and noise alerts<br/>Connection leak / config push / thundering herd"]
    HD["Hard<br/>6-9 services, 3-5 deep chain<br/>Monitoring blindness, stale metrics<br/>Kafka staleness / DNS failure / deadlock"]
    EA --> MD --> HD
```

## File Responsibilities

| File | Role | Key Constraint |
|------|------|---------------|
| `models.py` | Pydantic models extending openenv types | Fully typed, includes hypothesis_evidence |
| `incident_triage_env/env.py` | Core environment with reset/step/state | Integrates generator + temporal simulator |
| `incident_triage_env/generator.py` | Procedural scenario generation | networkx DAGs, 12 fault patterns, 40+ service names |
| `incident_triage_env/temporal.py` | Dynamic metric degradation | Sigmoid curves, causal hop delays |
| `incident_triage_env/grader.py` | Diagnosis + evidence + criticality + investigation scoring | Deterministic, range (0.01, 0.99), partial credit |
| `incident_triage_env/scenarios.py` | Scenario accessor (delegates to generator) | Backward compat pool lists |
| `incident_triage_env/log_templates.py` | Realistic log generators from LogHub | Timestamps, thread IDs, stack traces |
| `server/app.py` | FastAPI server via create_app() | HTTP + WebSocket + MCP |
| `server/incident_triage_environment.py` | OpenEnv Environment adapter | Bridges env.py to openenv interface |
| `inference.py` | Baseline LLM agent | Temporal-aware prompting, evidence citation |
| `scripts/chaos_evaluator.py` | Stress test harness | Hallucination detection, loop tracking |
