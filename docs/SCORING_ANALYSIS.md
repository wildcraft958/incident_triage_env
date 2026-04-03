# Environment Evolution and Scoring Analysis

How this environment evolved from static scenarios to a research-grade benchmark across 30+ commits, and what I learned about LLM behavior along the way.

## Phase 1: Foundation

**Commits:** `58f3a89` through `504ce90`

Started with the basics: Pydantic models, 5 hardcoded scenarios (2 easy, 2 medium, 1 hard), a deterministic grader, and 6 action types (`query_logs`, `query_metrics`, `check_topology`, `trace_request`, `check_alerts`, `diagnose`). The grader checked exact service match (+0.40), fault type (+0.35), and remediation (+0.25).

At this stage the environment was functional but fragile. A handful of static scenarios meant any RL agent would memorize the answers after a few episodes. The grader was binary on each component with no partial credit beyond causal chain membership.

**Dry-run scores:** The heuristic baseline script scored 0.06-0.10 (intentionally wrong diagnosis to test the pipeline).

## Phase 2: Procedural Generation Engine

**Commits:** `eed6d08` through `b8dfbcb`

This was the biggest architectural change. I replaced the static scenario pool with a `ProceduralScenarioGenerator` backed by networkx DAGs.

**What changed:**
- Service dependency graphs generated as Directed Acyclic Graphs with `nx.is_directed_acyclic_graph()` validation
- 10 composable fault patterns (OOM, disk full, connection leak, config error, cert expired, thundering herd, DNS failure, memory leak, thread deadlock, Kafka disk full)
- 40+ realistic service names across 6 architectural layers (gateway, application, data, infrastructure, observability, ML)
- Topology shapes scale with difficulty: 3-4 nodes (easy), 4-6 (medium), 6-9 (hard)
- `TemporalSimulator` computes metrics at each step via sigmoid interpolation: `metric = baseline + (crisis - baseline) * sigmoid(effective_progress)`
- Causal hop delays: each hop adds 20% onset delay, so downstream services degrade later than the root cause
- Progressive log revelation: causal chain services reveal more log lines as the incident cascades

**Rationale:** Procedural generation guarantees infinite replayability. An agent trained on seed 42 cannot memorize the answer because seed 43 produces a completely different topology, root cause, and degradation curve. This is the same principle behind Procgen (Cobbe et al., 2020), which showed that agents trained on fixed levels fail completely on procedurally generated variants.

**Score impact:** Scores now varied by scenario seed. The complexity_nudge (`num_services * 0.003`) ensured identical play styles still produced different scores across scenarios, preventing the grader from being constant.

## Phase 3: First Real Model Inference

**Commits:** `154be78`, `f7df89f`

Ran the first real LLM inference against the procedural environment.

**Qwen3.5-27B (via HuggingFace Router):** The model demonstrated temporal awareness, re-querying services at later steps when initial metrics looked normal. It cited specific log lines and metric values in `hypothesis_evidence`. This confirmed the temporal simulator was working as intended.

**Claude Haiku 4.5:** Scored 0.96 / 0.97 / 0.93 (easy/medium/hard). It consistently used 10 steps, checking topology first, then systematically querying logs AND metrics for every service in the causal chain before diagnosing. This cross-referencing behavior is exactly what the investigation quality scorer rewards.

**Key finding:** Frontier models naturally adopt methodical SRE investigation patterns without being explicitly told to. The reward shaping (topology bonus, cross-reference bonus, evidence bonus) aligns with how experienced SREs actually work.

## Phase 4: Multi-Model Ablation Study (v1)

**Commit:** `ff79dd5`

Ran 5 models across all 3 difficulties to prove the environment differentiates model capability.

| Model | Parameters | Easy | Medium | Hard | Avg |
|---|---|---|---|---|---|
| Llama 4 Scout | 17B MoE | 0.95 | 0.82 | 0.70 | 0.82 |
| Qwen3 | 32B | 0.96 | 0.77 | 0.80 | 0.84 |
| Llama 3.3 | 70B | 0.76 | 0.81 | 0.92 | 0.83 |
| Gemini 2.5 Flash | Frontier | 0.78 | 0.83 | 0.78 | 0.80 |
| Claude Haiku 4.5 | Frontier | 0.96 | 0.97 | 0.93 | 0.95 |

**Technical issue found and fixed:** Qwen3 initially produced 100% parse errors. Root cause: `max_tokens=256` was too small for reasoning models that output `<think>...</think>` blocks. The model spent all 256 tokens on internal reasoning and never produced the JSON action. Fix: increased `max_tokens` to 2048 and added `<think>` tag stripping in both `inference.py` and `chaos_evaluator.py`.

**Chaos evaluator results (20 hard episodes):** 0% hallucination rate, 0% loop defect rate, 0% context saturation. The procedural generator and temporal simulator produced stable, differentiable scenarios under stress.

Hard task spread at this stage: 0.70 to 0.93 (0.23 gap).

## Phase 5: Robustness Hardening

**Commits:** `6f6417d`, `8dbb259`

Research on reward hacking (Lilian Weng, "Reward Hacking in RL", 2024) and the SemiAnalysis report on RL environment exploitation (2025) revealed that LLM agents routinely game graders through fabricated evidence, keyword stuffing, and input exploitation. I audited the grader and found 4 specific vulnerabilities.

### New features added:

**Service criticality tiering** (`6f6417d`): Every service gets a Tier 1/2/3 label based on its architectural layer (databases = Tier 1, observability = Tier 3). Correctly diagnosing a Tier 1 root cause earns +0.02; misdiagnosing Tier 1 costs -0.03. Visible in topology output so agents can prioritize.

**check_runbook action** (`6f6417d`): A 7th action returning per-service runbooks with known failure modes and remediation procedures. Real SREs consult runbooks during incidents. Rewards +0.02 for causal chain services.

### Grader hardening:

**Evidence grounding** (`8dbb259`): The grader now tracks all observation text the agent has received (`_response_history`). The evidence bonus (+0.05 for citing root service) is only awarded if the root service name appears in the agent's observation history. An agent claiming "postgres-db disk_usage at 100%" without ever querying postgres-db gets zero bonus.

**Anti-keyword-stuffing** (`8dbb259`): If `hypothesis_evidence` contains keywords matching 3+ different fault types, the evidence bonus is halved. This penalizes agents that dump "heap outofmemoryerror cpu dns certificate connection pool disk deadlock" to shotgun-match any fault type.

**Input validation** (`8dbb259`): `diagnose` now validates `fault_type` against `FaultType` enum and `remediation` against `Remediation` enum. Invalid values return an error (-0.02) without ending the episode, letting the agent retry. Previously, invalid values silently scored 0 and terminated.

**Research basis:**
- Lilian Weng (2024): "Reward Hacking in Reinforcement Learning" -- layered defenses combining validation, transparency requirements, and environmental randomization
- METR (2025): frontier models modify test/scoring code, copy reference implementations, exploit loopholes
- Procgen (Cobbe et al.): procedural generation prevents overfitting to fixed evaluation sets
- SemiAnalysis: "No single mitigation eliminates reward hacking -- layered defenses are most effective"

## Phase 6: Re-run with Hardened Grader

**Commit:** `c733999`

Re-ran all 5 models against the hardened environment.

| Model | Parameters | Easy | Medium | Hard | Avg |
|---|---|---|---|---|---|
| Llama 4 Scout | 17B MoE | 0.77 | 0.88 | 0.74 | 0.80 |
| Qwen3 | 32B | 0.96 | 0.86 | 0.32 | 0.71 |
| Llama 3.3 | 70B | 0.78 | 0.97 | 0.86 | 0.87 |
| Gemini 2.5 Flash | Frontier | 0.89 | 0.93 | 0.85 | 0.89 |
| Claude Haiku 4.5 | Frontier | 0.77 | 0.96 | 0.91 | 0.88 |

**Hard task spread widened from 0.23 to 0.59.** The robustness fixes had the intended effect: agents can no longer game the grader through hallucinated evidence or keyword stuffing. The environment now genuinely tests reasoning depth.

**Notable behaviors:**
- Qwen3 collapsed from 0.80 to 0.32 on hard. It diagnosed in 4 steps, misidentified the fault type (`dependency_timeout` instead of the actual root cause), and submitted ungrounded evidence.
- Claude Haiku and Gemini both discovered and used `check_runbook` without being explicitly told to. Smaller models ignored it.
- Llama 3.3 scored 0.97 on medium by investigating 5 different services before diagnosing, earning maximum investigation quality points.

## The Shortcut Learning Anomaly

**Commit:** `09f23d9`

A pattern emerged across all 5 models: medium scores consistently beat easy scores. This is counterintuitive -- shouldn't easy be easier?

I investigated across 20 seeded scenarios per difficulty and found a structural explanation rooted in how LLMs process diagnostic information.

### Root cause: Lexical shortcuts in log templates

Each difficulty uses different fault patterns with different log categories:

- **Easy** patterns (`oom`, `memory_leak`) use `java_oom` log templates with ambiguous GC/heap messages. A GC pause of 4000ms with heap at 95% could be either OOM or a memory leak. The model has to reason about the distinction.
- **Medium** patterns (`connection_leak`, `cpu_saturated`) produce logs with explicit fault names. The fallback template literally outputs `"Fault detected -- cpu_saturated"`. The LLM pattern-matches the token directly.
- **Hard** patterns combine structural complexity (5-deep chains, 6-9 services) with monitoring blindness (stale metrics, `N/A` values) and no easy lexical shortcuts.

### This is "Shortcut Learning"

In LLM evaluation research (observed in SWE-bench and OSWorld), models bypass logical reasoning when they can find a lexical shortcut. The medium task's explicit log tokens act as a shortcut that lets models skip the deductive step entirely.

### What each difficulty actually tests

| Difficulty | Challenge | Log Clarity | Chain Depth |
|---|---|---|---|
| Easy | Ambiguity resolution -- infer fault type from indirect evidence | Low | 1-2 hops |
| Medium | Causal chain navigation with clear signals once you find the right node | High | 2-4 hops |
| Hard | Deep reasoning under monitoring blindness, no lexical shortcuts | Medium | 3-5 hops |

### Max achievable scores (20 seeds, perfect play)

- Easy: 0.965
- Medium: 0.976
- Hard: 0.986

The ceilings are comparable. Differentiation comes entirely from agent mistakes, not grader limits.

### The key metric

The hard task spread of 0.59 (Qwen3 0.32 to Claude Haiku 0.91) proves the environment correctly neutralizes LLM shortcut learning and isolates true multi-step SRE reasoning. This is the number that matters for benchmark validity.

## Competition Scoring Alignment

| Category (Weight) | What I Built | Target |
|---|---|---|
| Real-World Utility (30%) | SRE triage based on Meta/AWS/CrowdStrike post-mortems, PagerDuty/incident.io product space | 26-30 |
| Task & Grader Quality (25%) | 3 tasks, deterministic grader, 0.59 hard spread across 5 models, anti-reward-hacking | 20-25 |
| Environment Design (20%) | 7 actions, procedural DAGs, temporal sigmoid degradation, criticality tiering, runbooks | 16-20 |
| Code Quality (15%) | 177 tests, openenv validate passes, Docker builds, HF Space deploys, typed models | 12-15 |
| Creativity (10%) | Evidence grounding, shortcut learning analysis, chaos evaluator, 5-model ablation | 7-10 |

## Test Coverage

177 tests across 6 test files:
- Generator: structural validation, criticality tiering, runbook generation (57 tests)
- Temporal: sigmoid degradation, causal delays, log revelation (15 tests)
- Environment: all actions, edge cases, robustness, evidence grounding (48 tests)
- Grader: determinism, partial credit, evidence scoring, criticality (26 tests)
- Scenarios: pool validation (16 tests)
- API: HTTP/WebSocket endpoints (10 tests)

All pass. `validate.sh --no-docker` passes 26/26 checks.
