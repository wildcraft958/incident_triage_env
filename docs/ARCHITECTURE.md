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
            PROC["generator.py\nnetworkx DAGs\n12 fault patterns"]
            TEMP["temporal.py\nSigmoid degradation\nCausal hop delays"]
        end

        subgraph SCORE["Scoring"]
            GR["grader.py\nDiagnosis + Evidence scoring"]
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
    RESET -->|"Generator creates\nfresh scenario"| GEN["ProceduralScenarioGenerator"]
    GEN --> TEMPORAL["TemporalSimulator initialized"]
    TEMPORAL --> RUNNING["Running"]
    RUNNING -->|"query_logs / query_metrics\ncheck_topology / trace_request\ncheck_alerts"| PROCESS["Process Action"]
    PROCESS --> DEGRADE["Temporal: compute\nmetrics at current step"]
    DEGRADE --> REWARD["Compute Reward"]
    REWARD --> UPDATE["Update State"]
    UPDATE --> OBS["Return Observation"]
    OBS -->|"done = false"| RUNNING
    RUNNING -->|"diagnose action\nor max_steps reached"| DONE["Done"]
    DONE -->|"Can reset"| RESET
    DONE --> END(("End"))
```

## Procedural Generation

```mermaid
flowchart LR
    subgraph INPUT["Configuration"]
        DIFF["difficulty:\neasy/medium/hard"]
        SEED["optional seed\nfor reproducibility"]
    end

    subgraph GENERATOR["ProceduralScenarioGenerator"]
        FP["Pick fault pattern\n(10 available)"]
        TOPO["Build networkx DAG\n(3-9 services)"]
        RC["Select root cause\n+ causal chain"]
        SYNTH["Synthesize:\nlogs, metrics,\nalerts, traces"]
    end

    subgraph OUTPUT["Scenario Dict"]
        SVC["services + topology"]
        BASELINE["metrics_baseline\n(healthy state)"]
        CRISIS["metrics_crisis\n(full cascade)"]
        LOGS["logs per service"]
        CHAIN["causal_chain +\ncausal_distances"]
    end

    INPUT --> GENERATOR
    GENERATOR --> OUTPUT
```

## Temporal Degradation Model

```mermaid
flowchart TD
    A["Agent calls query_metrics(service)"] --> B["TemporalSimulator.compute_metrics()"]
    B --> C{"Is service in\ncausal chain?"}
    C -->|"No"| D["Return baseline\n(stable, healthy)"]
    C -->|"Yes"| E["Compute effective progress"]
    E --> F["progress = step / (max_steps * 0.75)"]
    F --> G["onset_delay = distance * 0.20"]
    G --> H["effective = (progress - delay) / (1 - delay)"]
    H --> I["sigmoid = 1 / (1 + exp(-10 * (t - 0.5)))"]
    I --> J["metric = baseline + (crisis - baseline) * sigmoid"]
    J --> K["Return degraded metrics"]
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

    J --> EV{"hypothesis_evidence\ncites root service\n+ signal keywords?"}
    C --> EV
    EV -->|"Yes"| EVB["up to +0.10"]
    EV -->|"No/empty"| EVN["+0.00"]

    EVB --> P["Apply blind penalty\nand investigation quality"]
    EVN --> P
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
        H1["6-9 services"]
        H2["3-5 deep chain"]
        H3["Monitoring blindness + stale metrics"]
        H4["Kafka staleness, DNS failure, memory leak, deadlock"]
    end

    Easy --> Medium --> Hard
```

## File Responsibilities

| File | Role | Key Constraint |
|------|------|---------------|
| `models.py` | Pydantic models extending openenv types | Fully typed, includes hypothesis_evidence |
| `incident_triage_env/env.py` | Core environment with reset/step/state | Integrates generator + temporal simulator |
| `incident_triage_env/generator.py` | Procedural scenario generation | networkx DAGs, 12 fault patterns, 40+ service names |
| `incident_triage_env/temporal.py` | Dynamic metric degradation | Sigmoid curves, causal hop delays |
| `incident_triage_env/grader.py` | Diagnosis + evidence + criticality + investigation scoring | Deterministic, range [0.0, 1.0], partial credit |
| `incident_triage_env/scenarios.py` | Scenario accessor (delegates to generator) | Backward compat pool lists |
| `incident_triage_env/log_templates.py` | Realistic log generators from LogHub | Timestamps, thread IDs, stack traces |
| `server/app.py` | FastAPI server via create_app() | HTTP + WebSocket + MCP |
| `server/incident_triage_environment.py` | OpenEnv Environment adapter | Bridges env.py to openenv interface |
| `inference.py` | Baseline LLM agent | Temporal-aware prompting, evidence citation |
| `scripts/chaos_evaluator.py` | Stress test harness | Hallucination detection, loop tracking |
